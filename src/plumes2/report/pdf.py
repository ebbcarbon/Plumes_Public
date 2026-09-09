"""Assembling the panels into a PDF: US Letter pages, real text, vector figures.

A report that goes to a regulator or into a permit file is a PDF. The HTML page (`page.py`) stays
for a browser tab; this module renders the same `Header` and `Panel`s to paper-shaped pages, and
does the typesetting with matplotlib alone -- the package already depends on it, its PDF backend
embeds vector figures and real, selectable text, and a second typesetting dependency with its own
font handling and platform quirks would have been more machinery than one report needs. The one
thing that backend cannot write is an **in-document link**: it knows external URLs only. So once
the pages are written, `pypdf` makes a single pass over the file to turn every contents row into a
link to its section's page and to give the document an outline (the bookmarks in a viewer's
sidebar) with the same entries (operator, 2026-09-09). Nothing on the page moves; the file gains
annotations and an outline tree.

**How a page is built.** Every page is a letter-sized matplotlib figure. Text -- headings, prose,
bullets, tables -- is placed with `Figure.text` from a cursor that runs down the page, wrapped
against the *measured* width of each line in the actual font, so a line never runs into the
margin. A panel's figure is drawn into a **subfigure** occupying a band the cursor has reserved:
the page uses constrained layout, so the panel's axes, tick labels, legend and colour bar are
fitted inside the band exactly as they are fitted inside a standalone figure. The panel's own
`Drawing` does the drawing (see `panels.Drawing`), so the PDF and the HTML show the same picture.

**Structure** is the HTML page's: title, provenance, what to be careful of, the headline numbers,
a contents list with page numbers, then one section per panel starting on a fresh page -- heading,
explanation, figure, notes, and the table of values. A table that does not fit continues on the
next page with its header repeated. A running footer with the page number goes on every page.

⚠️ **The page's text is never parsed as maths.** A case description is typed into a GUI; a `$` in
it would otherwise become a mathtext delimiter and swallow the rest of the line. Every text the
composer places is created with `parse_math=False` -- on the text itself, not through rcParams,
because the figures' log-axis tick labels *are* mathtext and must stay so. And the figures'
rasterised colour fields are written at 200 dpi, the same as the SVG path, so the two formats print
alike.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
from matplotlib.layout_engine import ConstrainedLayoutEngine
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.textpath import TextToPath
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ArrayObject, Fit, NameObject, NumberObject

from plumes2 import __version__
from plumes2.report.page import Header, format_value
from plumes2.report.palette import (
    AXIS,
    GRID,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    SERIES,
    SURFACE,
)
from plumes2.report.panels import PANEL_WIDTH, Drawing, Panel, _styled

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.figure import Figure, SubFigure

__all__ = ["PAGE_SIZE", "page_figures", "render_pdf"]

#: US Letter, inches. The audience is a permit file, and permit files are letter.
PAGE_SIZE: tuple[float, float] = (8.5, 11.0)
_PAGE_W, _PAGE_H = PAGE_SIZE
_MARGIN_LEFT = 0.85
_MARGIN_RIGHT = 0.85
_MARGIN_TOP = 0.75
_MARGIN_BOTTOM = 0.8
_TEXT_WIDTH = _PAGE_W - _MARGIN_LEFT - _MARGIN_RIGHT

#: The page's own typeface. DejaVu ships with matplotlib, so it is embedded identically on every
#: machine -- the same reason the figures use it -- and the PDF needs no font the reader may lack.
_SANS = "DejaVu Sans"
_MONO = "DejaVu Sans Mono"


@dataclass(frozen=True, slots=True)
class _Style:
    """A text style: size in points, ink, weight, face, and the line height as a multiple."""

    size: float
    color: str
    weight: str = "normal"
    family: str = _SANS
    leading: float = 1.4

    @property
    def line_height(self) -> float:
        """Advance per line, inches."""
        return self.size * self.leading / 72.0

    def props(self) -> FontProperties:
        return FontProperties(family=self.family, size=self.size, weight=self.weight)


_TITLE = _Style(17.0, INK_PRIMARY, "bold", leading=1.2)
_SUBTITLE = _Style(10.5, INK_SECONDARY)
_STAMP = _Style(7.5, INK_MUTED)
_HEADING = _Style(12.5, INK_PRIMARY, "bold", leading=1.25)
_LABEL = _Style(7.5, INK_MUTED, "bold")
_BODY = _Style(9.5, INK_PRIMARY, leading=1.45)
_NOTE = _Style(8.5, INK_SECONDARY)
_TABLE = _Style(7.0, INK_SECONDARY, family=_MONO, leading=1.55)
_TABLE_HEAD = _Style(7.0, INK_MUTED, "bold", family=_MONO, leading=1.55)
_FOOTER = _Style(7.5, INK_MUTED)
_CONTENTS = _Style(9.0, INK_SECONDARY, leading=1.5)
_KPI_LABEL = _Style(7.5, INK_MUTED)
_KPI_VALUE = _Style(15.0, INK_PRIMARY, "bold")
_KPI_UNIT = _Style(8.5, INK_SECONDARY)

#: Advance width of DejaVu Sans Mono, in em. Tables are laid out on this rather than measured
#: per cell, because a monospace table *is* a character grid.
_MONO_ADVANCE = 0.602

_measure = TextToPath()


@lru_cache(maxsize=8192)
def _width(text: str, size: float, weight: str, family: str) -> float:
    """Rendered width of `text` in inches, measured in the actual font with no renderer needed."""
    props = FontProperties(family=family, size=size, weight=weight)
    width, _height, _descent = _measure.get_text_width_height_descent(text, props, ismath=False)
    return float(width) / 72.0


def _text_width(text: str, style: _Style) -> float:
    """Width of a line, inches, as the sum of its words plus the spaces between them.

    Summed rather than measured whole so the wrap can lay out a report's worth of prose in a few
    hundred font calls instead of a few thousand: the words repeat, the cache holds them, and the
    kerning across a space that the sum ignores is below a tenth of a point in DejaVu.
    """
    words = text.split(" ")
    space = _width(" ", style.size, style.weight, style.family)
    return sum(_width(word, style.size, style.weight, style.family) for word in words) + space * (
        len(words) - 1
    )


#: Characters the notes use that DejaVu has no glyph for, and the glyph it does have that says the
#: same thing. The HTML page shows the emoji; on paper a missing glyph is an empty box.
_GLYPHS = {
    "\N{VARIATION SELECTOR-16}": "",  # the emoji presentation selector after a warning sign
    "\N{WHITE HEAVY CHECK MARK}": "\N{CHECK MARK}",
    "\N{HOURGLASS WITH FLOWING SAND}": "\N{HOURGLASS}",
    "\N{WHITE MEDIUM STAR}": "\N{BLACK STAR}",
    "\N{NO ENTRY}": "\N{CIRCLED DIVISION SLASH}",
}


def _clean(text: str) -> str:
    """Text as the page will print it.

    Emoji that DejaVu cannot draw are swapped for the symbol it can (see `_GLYPHS`), and the `**`
    emphasis some notes carry for the HTML, which reads as litter on paper, goes. Everything else
    is printed as written.
    """
    for emoji, glyph in _GLYPHS.items():
        text = text.replace(emoji, glyph)
    return text.replace("**", "")


def _wrap(text: str, style: _Style, width: float) -> list[str]:
    """Break `text` into lines no wider than `width` inches, measured rather than counted.

    Greedy by words, keeping explicit newlines. A single token wider than the line -- a digest, a
    path -- is broken by character, since a line that overruns the margin is worse than a split
    hash.
    """
    lines: list[str] = []
    for paragraph in _clean(text).split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if _text_width(candidate, style) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
            while _text_width(word, style) > width and len(word) > 1:
                cut = max(1, int(len(word) * width / _text_width(word, style)))
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines or [""]


class _Page:
    """One letter-sized figure and a cursor running down it, inches from the top edge."""

    def __init__(self) -> None:
        self.figure: Figure = plt.figure(
            figsize=PAGE_SIZE,
            layout=ConstrainedLayoutEngine(w_pad=0.06, h_pad=0.06, hspace=0.0, wspace=0.0),
            facecolor="white",
        )
        self.y = _MARGIN_TOP
        self.has_band = False

    @property
    def remaining(self) -> float:
        return _PAGE_H - _MARGIN_BOTTOM - self.y

    @staticmethod
    def _fx(x: float) -> float:
        return x / _PAGE_W

    @staticmethod
    def _fy(y_from_top: float) -> float:
        return 1.0 - y_from_top / _PAGE_H

    def text(self, text: str, style: _Style, *, x: float = _MARGIN_LEFT, ha: str = "left") -> None:
        """One line at the cursor, then advance."""
        self.figure.text(
            self._fx(x),
            self._fy(self.y),
            text,
            fontproperties=style.props(),
            color=style.color,
            ha=ha,
            va="top",
            parse_math=False,
        )
        self.y += style.line_height

    def text_at(self, text: str, style: _Style, x: float, y: float, *, ha: str = "left") -> None:
        """One line at an explicit position, without moving the cursor."""
        self.figure.text(
            self._fx(x),
            self._fy(y),
            text,
            fontproperties=style.props(),
            color=style.color,
            ha=ha,
            va="top",
            parse_math=False,
        )

    def space(self, inches: float) -> None:
        self.y += inches

    def rule(self, *, color: str = GRID, x0: float = _MARGIN_LEFT, x1: float | None = None) -> None:
        """A hairline across the text column at the cursor."""
        right = _PAGE_W - _MARGIN_RIGHT if x1 is None else x1
        self.figure.add_artist(
            Line2D(
                [self._fx(x0), self._fx(right)],
                [self._fy(self.y), self._fy(self.y)],
                transform=self.figure.transFigure,
                color=color,
                linewidth=0.8,
            )
        )

    def box(
        self, x: float, y: float, width: float, height: float, *, accent: str | None = None
    ) -> None:
        """A bordered card in page inches, optionally with a coloured bar down its left edge."""
        self.figure.add_artist(
            FancyBboxPatch(
                (self._fx(x), self._fy(y + height)),
                width / _PAGE_W,
                height / _PAGE_H,
                boxstyle="round,pad=0,rounding_size=0.006",
                transform=self.figure.transFigure,
                facecolor=SURFACE,
                edgecolor=GRID,
                linewidth=0.8,
            )
        )
        if accent:
            self.figure.add_artist(
                Rectangle(
                    (self._fx(x), self._fy(y + height)),
                    0.045 / _PAGE_W,
                    height / _PAGE_H,
                    transform=self.figure.transFigure,
                    facecolor=accent,
                    edgecolor="none",
                )
            )

    def band(self, height: float) -> SubFigure:
        """Reserve `height` inches across the text column for a figure, and return its subfigure.

        The band is a cell of a page-spanning gridspec whose ratios are the cursor's own numbers;
        constrained layout honours the ratios (it ignores gridspec margins), so this is what
        pins the subfigure to the band. One band per page: a second gridspec on the same figure
        is not something the layout engine promises to arbitrate.
        """
        assert not self.has_band, "one figure band per page"
        top, bottom = self.y, self.y + height
        grid = self.figure.add_gridspec(
            3,
            3,
            height_ratios=[top, height, max(_PAGE_H - bottom, 1e-3)],
            width_ratios=[_MARGIN_LEFT, _TEXT_WIDTH, _MARGIN_RIGHT],
            hspace=0.0,
            wspace=0.0,
        )
        sub = self.figure.add_subfigure(
            grid[1, 1], facecolor=SURFACE, edgecolor=GRID, linewidth=0.8, frameon=True
        )
        self.y = bottom
        self.has_band = True
        return sub


@dataclass(frozen=True, slots=True)
class _ContentsLink:
    """One contents row's place on its page, and the page it points at (1-based, or `None`)."""

    page: _Page
    #: Top and bottom of the row, inches from the top edge of the page.
    y_top: float
    y_bottom: float
    target: int | None
    title: str


class _Composer:
    """Flows blocks onto pages, opening a new page whenever the next block will not fit."""

    def __init__(self) -> None:
        self.pages: list[_Page] = []
        self.page: _Page | None = None
        #: Where each contents row landed, for the link pass after the PDF is written.
        self.links: list[_ContentsLink] = []

    # ---------------------------------------------------------------- paging

    def new_page(self) -> _Page:
        self.page = _Page()
        self.pages.append(self.page)
        return self.page

    def current(self, needed: float = 0.0) -> _Page:
        """The page the next block goes on: the current one if `needed` inches fit, else new."""
        if self.page is None or self.page.remaining < needed:
            return self.new_page()
        return self.page

    # ---------------------------------------------------------------- blocks

    def paragraph(
        self, text: str, style: _Style, *, indent: float = 0.0, after: float = 0.1
    ) -> None:
        """Wrapped prose; a paragraph may break across pages, line by line."""
        for line in _wrap(text, style, _TEXT_WIDTH - indent):
            self.current(style.line_height).text(line, style, x=_MARGIN_LEFT + indent)
        if self.page is not None:
            self.page.space(after)

    def bullets(self, items: tuple[str, ...] | list[str], style: _Style) -> None:
        hang = 0.2
        for item in items:
            lines = _wrap(item, style, _TEXT_WIDTH - hang)
            page = self.current(style.line_height * min(len(lines), 2))
            page.text_at("\N{BULLET}", style, _MARGIN_LEFT + 0.04, page.y)
            for line in lines:
                self.current(style.line_height).text(line, style, x=_MARGIN_LEFT + hang)
            if self.page is not None:
                self.page.space(0.04)
        if self.page is not None:
            self.page.space(0.08)

    def heading(self, text: str) -> None:
        page = self.current(1.2)
        if page.y > _MARGIN_TOP + 0.01:
            page.space(0.1)
            page.rule()
            page.space(0.14)
        for line in _wrap(text, _HEADING, _TEXT_WIDTH):
            page.text(line, _HEADING)
        page.space(0.08)

    def label(self, text: str) -> None:
        """A small uppercase label, the HTML page's `h3`."""
        self.current(0.4).text(text.upper(), _LABEL)
        if self.page is not None:
            self.page.space(0.04)

    def figure(self, drawing: Drawing) -> None:
        """The panel's figure, in a band proportioned as the drawing declares."""
        height = drawing.height * (_TEXT_WIDTH / PANEL_WIDTH) + 0.12
        page = self.current(height)
        if page.has_band:
            page = self.new_page()
        drawing.into(page.band(height))
        page.space(0.14)

    def kpis(self, tiles: tuple[tuple[str, str, str], ...]) -> None:
        """The headline numbers as a grid of stat tiles, three across."""
        if not tiles:
            return
        columns = 3
        gap = 0.12
        tile_w = (_TEXT_WIDTH - gap * (columns - 1)) / columns
        tile_h = 0.72
        rows = [tiles[i : i + columns] for i in range(0, len(tiles), columns)]
        for row in rows:
            page = self.current(tile_h + gap)
            for index, (label, value, unit) in enumerate(row):
                x = _MARGIN_LEFT + index * (tile_w + gap)
                page.box(x, page.y, tile_w, tile_h)
                page.text_at(_clean(label), _KPI_LABEL, x + 0.12, page.y + 0.1)
                page.text_at(_clean(value), _KPI_VALUE, x + 0.12, page.y + 0.28)
                if unit:
                    offset = _text_width(_clean(value), _KPI_VALUE) + 0.06
                    page.text_at(_clean(unit), _KPI_UNIT, x + 0.12 + offset, page.y + 0.38)
            page.space(tile_h + gap)
        if self.page is not None:
            self.page.space(0.1)

    def caveats(self, items: tuple[str, ...]) -> None:
        """The "read these first" box: a card with an accent bar, kept whole on one page."""
        if not items:
            return
        inner = _TEXT_WIDTH - 0.5
        wrapped = [_wrap(item, _NOTE, inner - 0.2) for item in items]
        lines = sum(len(block) for block in wrapped)
        height = 0.42 + lines * _NOTE.line_height + 0.06 * len(items)
        page = self.current(height + 0.15)
        page.box(_MARGIN_LEFT, page.y, _TEXT_WIDTH, height, accent=SERIES[1])
        y = page.y + 0.12
        page.text_at("READ THESE FIRST", _LABEL, _MARGIN_LEFT + 0.25, y)
        y += 0.24
        for block in wrapped:
            page.text_at("\N{BULLET}", _NOTE, _MARGIN_LEFT + 0.25, y)
            for line in block:
                page.text_at(line, _NOTE, _MARGIN_LEFT + 0.45, y)
                y += _NOTE.line_height
            y += 0.06
        page.space(height + 0.2)

    def contents(self, entries: list[tuple[str, int | None]]) -> None:
        """The contents list, page numbers ranged right."""
        self.label("Contents")
        right = _PAGE_W - _MARGIN_RIGHT
        for index, (title, number) in enumerate(entries, start=1):
            page = self.current(_CONTENTS.line_height)
            self.links.append(
                _ContentsLink(page, page.y, page.y + _CONTENTS.line_height, number, title)
            )
            page.text_at(f"{index}.", _CONTENTS, _MARGIN_LEFT, page.y)
            page.text_at(
                _wrap(title, _CONTENTS, _TEXT_WIDTH - 1.0)[0],
                _CONTENTS,
                _MARGIN_LEFT + 0.32,
                page.y,
            )
            page.text_at(
                "\N{EM DASH}" if number is None else str(number),
                _CONTENTS,
                right,
                page.y,
                ha="right",
            )
            page.space(_CONTENTS.line_height)
        if self.page is not None:
            self.page.space(0.1)

    def table(self, frame: pd.DataFrame, *, label: str | None = None) -> None:
        """A monospace table that flows across pages, its header repeated on each.

        Columns are sized to their widest cell. If the grid is wider than the column the type is
        stepped down, and if it is still wider the widest columns are capped and their cells
        wrapped -- the validation report's `claim` column is a sentence, and a sentence wraps.

        A table that would fit on a page is kept whole: when the rest of the current page cannot
        hold it, it starts on the next, `label` and all, rather than leaving its last row alone
        on a page of its own.
        """
        if not len(frame):
            return
        headers = [_clean(str(name)) for name in frame.columns]
        cells = [
            [_clean(format_value(value)) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ]
        numeric = [
            pd.api.types.is_numeric_dtype(frame[column])
            and not pd.api.types.is_bool_dtype(frame[column])
            for column in frame.columns
        ]
        widths = [
            max(len(header), *(len(row[index]) for row in cells))
            for index, header in enumerate(headers)
        ]

        def total(size: float, capped: list[int]) -> float:
            characters = sum(capped) + 2 * (len(capped) - 1)
            return characters * size * _MONO_ADVANCE / 72.0

        size = _TABLE.size
        for candidate in (7.0, 6.5, 6.0):
            size = candidate
            if total(size, widths) <= _TEXT_WIDTH:
                break
        cap = max(widths)
        while total(size, widths) > _TEXT_WIDTH and cap > 10:
            cap -= 2
            widths = [min(width, cap) for width in widths]

        head_style = _Style(size, _TABLE_HEAD.color, "bold", _MONO, _TABLE_HEAD.leading)
        body_style = _Style(size, _TABLE.color, family=_MONO, leading=_TABLE.leading)

        def pad(text: str, width: int, right_align: bool) -> str:
            return text.rjust(width) if right_align else text.ljust(width)

        def split(text: str, width: int) -> list[str]:
            if len(text) <= width:
                return [text]
            words, lines, current = text.split(), [], ""
            for word in words:
                candidate = f"{current} {word}" if current else word
                if len(candidate) <= width:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                while len(word) > width:
                    lines.append(word[:width])
                    word = word[width:]
                current = word
            lines.append(current)
            return lines

        def header_lines() -> list[str]:
            pieces = [split(header, widths[i]) for i, header in enumerate(headers)]
            depth = max(len(piece) for piece in pieces)
            return [
                "  ".join(
                    pad(piece[line] if line < len(piece) else "", widths[i], numeric[i])
                    for i, piece in enumerate(pieces)
                )
                for line in range(depth)
            ]

        def emit_header(page: _Page) -> None:
            for line in header_lines():
                page.text(line, head_style)
            page.space(0.02)
            page.rule(color=AXIS)
            page.space(0.05)

        header_height = len(header_lines()) * head_style.line_height + 0.1
        row_heights = [
            max(len(split(cell, widths[i])) for i, cell in enumerate(row)) * body_style.line_height
            for row in cells
        ]
        label_height = _LABEL.line_height + 0.04 if label else 0.0
        whole = label_height + header_height + sum(row_heights) + 0.12
        usable = _PAGE_H - _MARGIN_TOP - _MARGIN_BOTTOM - 0.3
        page = self.current(min(whole, usable))
        if label:
            page.text(label.upper(), _LABEL)
            page.space(0.04)
        emit_header(page)
        for row in cells:
            pieces = [split(cell, widths[i]) for i, cell in enumerate(row)]
            depth = max(len(piece) for piece in pieces)
            needed = depth * body_style.line_height
            if page.remaining < needed:
                page = self.new_page()
                emit_header(page)
            for line in range(depth):
                page.text(
                    "  ".join(
                        pad(piece[line] if line < len(piece) else "", widths[i], numeric[i])
                        for i, piece in enumerate(pieces)
                    ),
                    body_style,
                )
        page.space(0.12)


# --------------------------------------------------------------------------- the document


def _section(composer: _Composer, index: int, panel: Panel) -> None:
    """One panel, starting on a fresh page: heading, explanation, figure, notes, table."""
    composer.new_page()
    composer.heading(f"{index}. {panel.title}")
    composer.paragraph(panel.explanation, _BODY)
    if panel.drawing is not None:
        composer.figure(panel.drawing)
    if panel.notes:
        composer.bullets(panel.notes, _NOTE)
    if len(panel.table):
        composer.table(
            panel.table,
            label="The values behind this figure" if panel.drawing is not None else None,
        )


def _front_matter(
    composer: _Composer, header: Header, entries: list[tuple[str, int | None]]
) -> None:
    composer.new_page()
    for line in _wrap(header.title, _TITLE, _TEXT_WIDTH):
        composer.current().text(line, _TITLE)
    composer.current().space(0.08)
    composer.paragraph(header.subtitle, _SUBTITLE, after=0.04)
    composer.paragraph(header.stamp, _STAMP, after=0.22)
    composer.caveats(header.caveats)
    composer.kpis(header.kpis)
    composer.contents(entries)


def _footers(pages: list[_Page], running: str) -> None:
    """Running title left, `page n of m` right, on every page."""
    total = len(pages)
    title = _clean(running)
    while _text_width(title, _FOOTER) > _TEXT_WIDTH - 1.4 and len(title) > 8:
        title = title[:-2].rstrip() + "\N{HORIZONTAL ELLIPSIS}"
    for number, page in enumerate(pages, start=1):
        y = _PAGE_H - _MARGIN_BOTTOM + 0.3
        page.text_at(title, _FOOTER, _MARGIN_LEFT, y)
        page.text_at(f"page {number} of {total}", _FOOTER, _PAGE_W - _MARGIN_RIGHT, y, ha="right")


def page_figures(header: Header, panels: list[Panel], *, footer: str) -> list[Figure]:
    """Every page of the report as a finished figure, in order. The caller closes them."""
    pages, _links = _compose(header, panels, footer=footer)
    return [page.figure for page in pages]


def _compose(
    header: Header, panels: list[Panel], *, footer: str
) -> tuple[list[_Page], list[_ContentsLink]]:
    """Every page of the report, in order, and where its contents rows are.

    The sections are laid out first so the contents list can carry real page numbers; the front
    matter is then laid out once to learn how many pages it takes, and again with the numbers
    shifted by that count. Both passes are cheap -- the front matter is text.
    """
    body = _Composer()
    starts: list[int] = []
    for index, panel in enumerate(panels, start=1):
        starts.append(len(body.pages) + 1)
        _section(body, index, panel)
    body.paragraph(footer, _STAMP, after=0.0)

    front_pages = 1
    for _attempt in range(3):
        front = _Composer()
        _front_matter(
            front,
            header,
            [
                (panel.title, front_pages + start)
                for panel, start in zip(panels, starts, strict=True)
            ],
        )
        if len(front.pages) == front_pages:
            break
        for page in front.pages:
            plt.close(page.figure)
        front_pages = len(front.pages)

    pages = front.pages + body.pages
    _footers(pages, header.title)
    return pages, front.links


def _link_pass(document: bytes, pages: list[_Page], links: list[_ContentsLink]) -> bytes:
    """Turn each contents row into a link to its page and give the document an outline.

    The pages matplotlib wrote are read back, every contents row gets a rectangular link
    annotation over the whole strip it occupies -- number, title and page number -- pointing at
    the top of its section's page, and the same rows become the outline a viewer shows in its
    sidebar. Coordinates: the composer works in inches from the top-left; PDF user space is points
    from the bottom-left, at 72 to the inch.
    """
    reader = PdfReader(io.BytesIO(document))
    writer = PdfWriter(clone_from=reader)
    index_of = {id(page): number for number, page in enumerate(pages)}
    x0, x1 = _MARGIN_LEFT * 72.0, (_PAGE_W - _MARGIN_RIGHT) * 72.0
    for link in links:
        if link.target is None:
            continue
        target = link.target - 1
        rect = (x0, (_PAGE_H - link.y_bottom) * 72.0, x1, (_PAGE_H - link.y_top) * 72.0)
        inserted = writer.add_annotation(
            page_number=index_of[id(link.page)],
            annotation=Link(
                rect=rect,
                border=ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0)]),
                target_page_index=target,
                fit=Fit.fit(),
            ),
        )
        # pypdf leaves the destination as a bare page *index*, which the PDF specification allows
        # only for remote go-to actions; an in-document destination names the page object. Point
        # it at the page itself so every viewer follows it.
        inserted[NameObject("/Dest")] = ArrayObject(
            [writer.pages[target].indirect_reference, NameObject("/Fit")]
        )
        writer.add_outline_item(_clean(link.title), target)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def render_pdf(header: Header, panels: list[Panel], path: str | Path, *, footer: str) -> Path:
    """Write the report to `path` as a PDF and return it.

    The document metadata carries the title, the version that produced it and the provenance
    stamp, so a PDF that has lost its filename still says what it is.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    page_style = {
        "pdf.fonttype": 42,  # TrueType, so the text is selectable and searchable
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        # Every page is open until the document is written, then closed; that is the design, not
        # a leak, so the warning at twenty open figures does not apply.
        "figure.max_open_warning": 0,
    }
    # The same stub mismatch `panels._styled` documents: rc_context is typed on a Literal of keys.
    with _styled(), plt.rc_context(page_style):  # type: ignore[arg-type]
        pages, links = _compose(header, panels, footer=footer)
        metadata = {
            "Title": _clean(header.title),
            "Author": f"plumes2 {__version__}",
            "Subject": _clean(header.subtitle),
            "Keywords": _clean(header.stamp),
            "Creator": f"plumes2 {__version__} (matplotlib PDF backend + pypdf links)",
        }
        buffer = io.BytesIO()
        with PdfPages(buffer, metadata=metadata) as pdf:
            for page in pages:
                pdf.savefig(page.figure, dpi=200)
                plt.close(page.figure)
    target.write_bytes(_link_pass(buffer.getvalue(), pages, links))
    return target
