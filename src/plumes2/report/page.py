"""Assembling the panels into one self-contained HTML file.

**One file, no environment, opens anywhere.** That was the decision, and it drives everything
here: the figures are inline SVG rather than linked images, the CSS is a `<style>` block rather
than a stylesheet, and there is no JavaScript at all. A report that needs a server, a font
download or a notebook kernel to render is a report that stops working the moment it is forwarded.

⚠️ **Everything interpolated into the page is escaped.** A case description comes out of a `.prj`
that someone typed into a GUI, so it is untrusted text; a stray `<` in it would silently eat the
rest of the document. The one exception is the SVG, which this package generated itself.

⚠️ **The page paints its own light surface.** It does not inherit the reader's theme, because the
figures have their colours baked in and a light figure on a dark page is unreadable. See
`palette.py` for why a dark mode would mean rendering every panel twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

import pandas as pd

from plumes2.report.palette import (
    AXIS,
    GRID,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    PAGE,
    SERIES,
    SURFACE,
)
from plumes2.report.panels import Panel

__all__ = ["Header", "format_value", "render_page"]

_STYLE = f"""
:root {{
  color-scheme: light;
  --page: {PAGE};
  --surface: {SURFACE};
  --ink: {INK_PRIMARY};
  --ink-2: {INK_SECONDARY};
  --ink-muted: {INK_MUTED};
  --grid: {GRID};
  --axis: {AXIS};
  --accent: {SERIES[0]};
  --sans: system-ui, -apple-system, "Segoe UI", sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
}}
main {{ max-width: 60rem; margin: 0 auto; padding: 3rem 1.25rem 6rem; }}
h1 {{ font-size: 1.75rem; line-height: 1.25; margin: 0 0 .35rem; letter-spacing: -.01em; }}
h2 {{
  font-size: 1.15rem; margin: 3rem 0 .5rem; padding-top: 1.25rem;
  border-top: 1px solid var(--grid); letter-spacing: -.005em;
}}
h3 {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .06em;
      color: var(--ink-muted); margin: 1.5rem 0 .5rem; font-weight: 600; }}
p {{ margin: 0 0 1rem; max-width: 46rem; }}
a {{ color: var(--accent); }}
.lede {{ color: var(--ink-2); font-size: 1rem; }}
.stamp {{ font-size: .8rem; color: var(--ink-muted); margin: 0 0 2rem;
          font-variant-numeric: tabular-nums; }}
.stamp code {{ font-size: .78rem; }}

/* KPI row: the headline numbers, as stat tiles rather than a one-bar chart. */
.kpis {{ display: flex; flex-wrap: wrap; gap: .75rem; margin: 0 0 2rem;
          padding: 0; list-style: none; }}
.kpi {{ background: var(--surface); border: 1px solid var(--grid); border-radius: 8px;
        padding: .7rem .9rem; min-width: 9.5rem; flex: 1 1 9.5rem; }}
.kpi .label {{ font-size: .75rem; color: var(--ink-muted); display: block; }}
.kpi .value {{ font-size: 1.5rem; font-weight: 600; line-height: 1.2; }}
.kpi .unit {{ font-size: .85rem; font-weight: 400; color: var(--ink-2); }}

figure {{ margin: 1rem 0 .5rem; background: var(--surface); border: 1px solid var(--grid);
          border-radius: 8px; padding: .75rem; overflow-x: auto; }}
figure svg {{ display: block; max-width: 100%; height: auto; margin: 0 auto; }}

.notes {{ margin: .5rem 0 1rem; padding-left: 1.1rem; color: var(--ink-2); font-size: .9rem; }}
.notes li {{ margin: .3rem 0; }}
.notes li::marker {{ color: var(--ink-muted); }}

details {{ margin: .5rem 0 1rem; }}
summary {{ cursor: pointer; font-size: .85rem; color: var(--ink-2); }}
summary:hover {{ color: var(--ink); }}
.scroll {{ overflow-x: auto; margin-top: .6rem; }}
table {{ border-collapse: collapse; font-size: .82rem; font-variant-numeric: tabular-nums; }}
th, td {{ padding: .3rem .7rem; text-align: right; white-space: nowrap; }}
th {{ color: var(--ink-muted); font-weight: 600; border-bottom: 1px solid var(--axis); }}
td {{ border-bottom: 1px solid var(--grid); color: var(--ink-2); }}
tbody tr:last-child td {{ border-bottom: none; }}

.caveats {{ background: var(--surface); border: 1px solid var(--grid);
            border-left: 3px solid {SERIES[1]}; border-radius: 6px;
            padding: .8rem 1rem; margin: 0 0 2rem; font-size: .9rem; }}
.caveats h3 {{ margin-top: 0; }}
.caveats ul {{ margin: 0; padding-left: 1.1rem; color: var(--ink-2); }}

nav {{ font-size: .88rem; margin: 0 0 2.5rem; }}
nav ol {{ margin: .4rem 0 0; padding-left: 1.3rem; color: var(--ink-2); }}
footer {{ margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid var(--grid);
          font-size: .8rem; color: var(--ink-muted); }}
@media print {{
  body {{ background: #fff; }}
  figure, .kpi, .caveats {{ break-inside: avoid; }}
  details {{ display: none; }}
}}
"""


@dataclass(frozen=True, slots=True)
class Header:
    """What the report says about itself before it says anything about the plume."""

    title: str
    #: One sentence naming the case.
    subtitle: str
    #: Provenance: which code, which input, which digest. §7b's rule applies to figures too.
    stamp: str
    #: `(label, value, unit)` triples -- the headline numbers, as stat tiles.
    kpis: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    #: Sentences the reader must see before the figures, or not at all.
    caveats: tuple[str, ...] = field(default_factory=tuple)


def format_value(value: object) -> str:
    """A table cell a person can read: four significant figures, and no `1.0000000000000002`.

    The full-precision values live in the CSVs. A table in a report is for reading, and fifteen
    digits of a float is not a number anyone reads. Shared by the HTML and the PDF renderers so
    the two tables agree to the digit; the HTML escapes the result on top.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value:  # NaN
            return "\N{EM DASH}"
        magnitude = abs(value)
        if magnitude and (magnitude >= 1e5 or magnitude < 1e-3):
            return f"{value:.3e}"
        return f"{value:,.4g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _format(value: object) -> str:
    return escape(format_value(value))


def _table_html(table: pd.DataFrame) -> str:
    head = "".join(f"<th scope='col'>{escape(str(name))}</th>" for name in table.columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_format(cell)}</td>" for cell in row) + "</tr>"
        for row in table.itertuples(index=False, name=None)
    )
    return (
        "<div class='scroll'><table>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody>"
        "</table></div>"
    )


def _panel_html(panel: Panel, index: int) -> str:
    parts = [
        f"<section id='{escape(panel.key)}'>",
        f"<h2>{index}. {escape(panel.title)}</h2>",
        f"<p>{escape(panel.explanation)}</p>",
    ]
    if panel.svg:
        # The figure is generated markup, not user text, so it is the one thing not escaped.
        parts.append(f"<figure role='img' aria-label='{escape(panel.title)}'>{panel.svg}</figure>")
    if panel.notes:
        items = "".join(f"<li>{escape(note)}</li>" for note in panel.notes)
        parts.append(f"<ul class='notes'>{items}</ul>")
    if len(panel.table):
        if panel.svg:
            parts.append(
                "<details><summary>The values behind this figure</summary>"
                + _table_html(panel.table)
                + "</details>"
            )
        else:
            # No figure means the table *is* the panel -- as in the validation report -- so it is
            # not hidden behind a disclosure the reader has to know to open.
            parts.append(_table_html(panel.table))
    parts.append("</section>")
    return "\n".join(parts)


def render_page(header: Header, panels: list[Panel], *, footer: str) -> str:
    """The whole report as one HTML string.

    Structure is deliberate: what produced this, then what to be careful of, then the headline
    numbers, then a contents list, then the panels in reading order. The caveats come *before* the
    figures because a caveat under a figure has already been skipped.
    """
    kpis = "".join(
        f"<li class='kpi'><span class='label'>{escape(label)}</span>"
        f"<span class='value'>{escape(value)}"
        + (f" <span class='unit'>{escape(unit)}</span>" if unit else "")
        + "</span></li>"
        for label, value, unit in header.kpis
    )
    caveats = ""
    if header.caveats:
        items = "".join(f"<li>{escape(note)}</li>" for note in header.caveats)
        caveats = f"<div class='caveats'><h3>Read these first</h3><ul>{items}</ul></div>"
    contents = "".join(
        f"<li><a href='#{escape(panel.key)}'>{escape(panel.title)}</a></li>" for panel in panels
    )
    body = "\n".join(_panel_html(panel, index) for index, panel in enumerate(panels, start=1))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(header.title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<h1>{escape(header.title)}</h1>
<p class="lede">{escape(header.subtitle)}</p>
<p class="stamp">{escape(header.stamp)}</p>
{caveats}
<ul class="kpis">{kpis}</ul>
<nav aria-label="Contents"><strong>Contents</strong><ol>{contents}</ol></nav>
{body}
<footer>{escape(footer)}</footer>
</main>
</body>
</html>
"""
