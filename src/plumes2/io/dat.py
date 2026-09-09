"""Reader for the PLUMES2.0 `.dat` output file.

This exists so the exe's own traces can be loaded as dataframes and compared
numerically -- it is the harness behind most of the validation ledger. The
byte-exact *writer* lands in Phase 6.

Layout: a banner rule, an echo of the ambient and diffuser input tables, then the
near-field step table, optionally followed by a far-field table. Event banners are
interleaved between step rows.

Several quirks matter and are all exercised by the reference cases:

* **Column sets vary per run.** The step table's columns are chosen by the `.prj`
  variable-name list (5 in the upstream example, 9 in case01, a different 9 in
  case02), with chemistry columns appended automatically when that module is on.
  So the header is parsed rather than assumed.
* **Header text varies between exe builds.** The Dec-2025 build in
  `reference_cases/case00_legacy_fps` writes ``Avg-Dil`` where 2026 builds
  write ``Dilutn``, uses bare unit rows instead of parenthesised ones, and emits a
  ``P-Temp`` column. Nothing keys on exact header strings.
* **The terminating step row is truncated.** It is printed off-interval and with
  only the five base variables -- no chemistry columns (case05 step 417, case06
  step 356). Short rows are padded with NaN rather than rejected.
* **The far-field may be absent entirely** (case01), or present with an unmerged
  advisory (case02).
* **A run can emit no steps at all.** The Dec-2025 artifact in case00 is header-only.
  That parses to an empty step table rather than raising, because its echoed input
  tables are what decoded the `.prj` unit flags -- check :attr:`DatFile.has_nearfield`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from plumes2.io.dat_format import FIELD_WIDTH

__all__ = [
    "DatFile",
    "DatFormatError",
    "Event",
    "format_dat",
    "parse_dat",
    "read_dat",
    "write_dat",
]

_RULE_RE = re.compile(r"^[*\-]{20,}\s*$")
#: Event banners are centred in a rule of dashes or dots, e.g.
#: '---------------------------- Plume traps -----------------------------'
_BANNER_RE = re.compile(r"^[-.]{4,}\s*(?P<text>.*?)\s*[-.]{4,}$")
_TABLE_HEADING_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z /]*):\s*$")
_STEP_ROW_RE = re.compile(r"^\s*\d+\s")
#: A run can go numerically bad and emit literal `NaN` in place of every value --
#: `reference_cases/case09_single_port` does, including its wastefield width
#: and its entire far-field table. Those rows are data (they record the failure), so
#: they are parsed rather than skipped.
_FLOAT_ROW_RE = re.compile(r"^\s*(?:-?\d+\.\d+|NaN)\s", re.IGNORECASE)
_WASTEFIELD_RE = re.compile(r"wastefield width of\s*:\s*(?P<width>-?[\d.]+|NaN)", re.IGNORECASE)
#: The far-field preamble names the law in one of three forms (case50): `4/3 Power Law based
#: Eddy Diffusivity is used:`, `Constant Eddy Diffusivity is used:`, `Linearly Varying Eddy
#: Diffusivity is used:`. Only the 4/3 form carries the word `based`; the law is the text before it.
_EDDY_RE = re.compile(r"^\s*(?P<law>.+?)\s+(?:based\s+)?Eddy Diffusivity is used", re.IGNORECASE)

#: Free-text notes the exe emits outside the banner form.
_NOTE_PREFIX = "Note:"


class DatFormatError(ValueError):
    """Raised when a `.dat` file cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class Event:
    """An event banner, tied to the step row that follows it.

    The exe prints a banner at the first *output* row after it detects the event,
    so `next_step` is the first step printed at or after the event, not the step
    the event physically occurred on.
    """

    text: str
    next_step: int | None
    line_number: int

    @property
    def is_note(self) -> bool:
        return self.text.startswith(_NOTE_PREFIX)


@dataclass(slots=True)
class DatFile:
    """A parsed `.dat` output file."""

    #: Echoed input tables, keyed by their heading ('Ambient', 'Diffuser').
    echoed_tables: dict[str, pd.DataFrame]
    #: Near-field step table. Index is the step number.
    nearfield: pd.DataFrame
    #: Far-field table, or None when the run produced no far-field section.
    farfield: pd.DataFrame | None
    #: Banners and notes, in file order.
    events: list[Event]
    #: Wastefield width echoed by the far-field header, in metres.
    wastefield_width: float | None = None
    #: Eddy-diffusivity law named in the far-field header: '4/3 Power Law', 'Constant' or
    #: 'Linearly Varying' -- the exe's three selector options as its header spells them (case50).
    eddy_diffusivity_law: str | None = None
    #: Unit row per table, keyed as `echoed_tables` plus 'Simulation Results' and 'farfield'.
    #: Retained because the writer regenerates the header rather than replaying text.
    units: dict[str, list[str]] = field(default_factory=dict)
    #: Column names per table, in file order -- the step table's includes 'Step'.
    columns: dict[str, list[str]] = field(default_factory=dict)
    #: `(table, position) -> field count` for rows that were printed short. The truncated
    #: terminating step prints six fields where its neighbours print thirteen, and `_frame`
    #: pads the rest with NaN -- which is indistinguishable from case09's genuine NaNs
    #: without this.
    row_widths: dict[tuple[str, int], int] = field(default_factory=dict)
    #: The document as an ordered list of `(kind, payload)` emissions, which is what lets
    #: `format_dat` rebuild the file from its parts instead of replaying raw lines. Nothing
    #: here is text: every entry is regenerated by `dat_format`.
    layout: list[tuple[str, object]] = field(default_factory=list)
    source_path: Path | None = field(default=None, compare=False)

    @property
    def merged(self) -> bool:
        """Whether the plumes merged, per the presence of the advisory note."""
        return not any("not merged" in event.text for event in self.events)

    @property
    def has_farfield(self) -> bool:
        return self.farfield is not None

    @property
    def echoed_port_spacing(self) -> float | None:
        """The diffuser echo's `Spacing`, in **metres**, or `None` without a diffuser echo.

        The echo prints the spacing in the unit it was *entered* in and flags the column: case55's
        feet-entered 2 ft echoes as `2.0` under `(ft)`, and the exe ran it as 0.6096 m (its banner
        width and its merge step both say so). Every reader of the echo that wants a length in
        metres should come through here rather than take the column raw.
        """
        table = self.echoed_tables.get("Diffuser")
        if table is None or "Spacing" not in table.columns or table.empty:
            return None
        value = float(table["Spacing"].iloc[0])
        units = self.units.get("Diffuser", [])
        column = list(table.columns).index("Spacing")
        if column < len(units) and "ft" in units[column]:
            value *= 0.3048
        return value

    def event_steps(self) -> dict[str, list[int]]:
        """Map each banner text to the step numbers it was printed before."""
        steps: dict[str, list[int]] = {}
        for event in self.events:
            if event.next_step is not None:
                steps.setdefault(event.text, []).append(event.next_step)
        return steps

    @property
    def has_nearfield(self) -> bool:
        """False for a header-only artifact that produced no steps (case00)."""
        return not self.nearfield.empty

    @property
    def final_step(self) -> int:
        if self.nearfield.empty:
            raise DatFormatError(
                f"{self.source_path or '<string>'}: the step table is empty, so there is "
                "no final step"
            )
        return int(self.nearfield.index[-1])


def _clean_unit(token: str) -> str:
    """Normalise a unit token: '(m/s)' and 'm/s' both become 'm/s'."""
    return token.strip().strip("()").strip()


def _split_units(line: str) -> list[str]:
    """Split a unit row, repairing tokens the exe writes with an interior space.

    The diffuser echo gives the dimensionless port count as ``( )`` in 2026 builds -- a
    parenthesis, a space, a parenthesis -- which naive whitespace splitting turns into two
    tokens. That made the unit row one token longer than the name row and tripped the
    staggered-header rule below, silently shifting every diffuser column by one. The
    Dec-2025 build writes ``()`` and was unaffected, which is why it went unnoticed.
    """
    tokens = line.split()
    merged: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] == "(" and index + 1 < len(tokens) and tokens[index + 1] == ")":
            merged.append("()")
            index += 2
        else:
            merged.append(tokens[index])
            index += 1
    return merged


def _parse_header_block(lines: list[str], start: int) -> tuple[list[str], list[str], int]:
    """Read a name row and an optional unit row, returning (names, units, next index).

    The unit row is recognised structurally -- no more tokens than the name row plus
    one, and not itself data -- so both the parenthesised 2026 style and the bare
    Dec-2025 style work without matching any literal header text.

    The step table staggers its header: the name row omits the step column, and the
    unit row carries it as a leading token::

                      Dilutn     P-dia    x-posn    y-posn     Depth
              Step (FluxAvg)       (m)       (m)       (m)       (m)

    So a unit row one token longer than the name row contributes that extra leading
    token as the first column name. Echoed input tables and the far-field table have
    matching counts and are unaffected.
    """
    names = lines[start].split()
    index = start + 1
    units: list[str] = []
    if index < len(lines):
        candidate = _split_units(lines[index])
        looks_like_data = bool(_STEP_ROW_RE.match(lines[index]))
        if candidate and not looks_like_data and len(candidate) <= len(names) + 1:
            # Only an unparenthesised extra token is a column name ('Step'); a leading
            # unit like '(m)' means the counts simply differ, not that a name is missing.
            if len(candidate) == len(names) + 1 and not candidate[0].startswith("("):
                names = [candidate[0], *names]
                candidate = candidate[1:]
            units = [_clean_unit(token) for token in candidate]
            index += 1
    return names, units, index


def _split_fixed_width(line: str) -> list[float]:
    """One printed row's values. **Fixed-width fields, not whitespace-separated.**

    ⚠️⚠️ **The exe's step table is fixed-width, and a value that fills its field leaves no
    separator at all.** Found 2026-08-25 on `pending/dose_parity`: at TA 20 000 / DIC 2500 the
    plume runs at pH 12 and `R_cal` reaches `105022.286` -- exactly `FIELD_WIDTH` characters -- so
    the row prints `    37.737105022.286` and a `str.split()` reader raises on the joined token.
    191 rows across the two highest-dose traces do it.

    ⭐ **The writer had this right all along**: `dat_format.format_row` right-justifies each value
    in a ten-column field and concatenates with no separator, which is why those rows round-trip
    byte-exactly once they can be read. Only the reader assumed whitespace.

    Measured before switching, over every archived `.dat` (167 514 step rows): fixed-width parses
    **all** of them and agrees with the whitespace split on all 167 323 where whitespace also
    works -- **zero disagreements**, NaN for NaN. So this is not a fallback bolted beside the old
    path, it is the format, and whitespace is the fallback for a line the fixed grid does not
    explain (none in the archive; kept so a malformed line degrades rather than raising).
    """
    if len(line) % FIELD_WIDTH == 0:
        fields = [line[start : start + FIELD_WIDTH] for start in range(0, len(line), FIELD_WIDTH)]
        try:
            return [float(field) for field in fields]
        except ValueError:
            pass
    return [float(token) for token in line.split()]


def _numeric_rows(
    lines: list[str], start: int, pattern: re.Pattern[str]
) -> tuple[list[list[float]], list[tuple[str, int]], int, list[tuple[str, object]]]:
    """Collect consecutive numeric rows, capturing banners encountered between them.

    Also returns `order`: the rows and banners as they interleave, each row carrying its
    **field count**. That count cannot be recovered afterwards, because `_frame` pads a short
    row with NaN and `NaN` is *also* real data -- case05's terminating step prints six fields
    where its neighbours print thirteen, while case09 prints genuine NaNs throughout. Without
    the count a writer cannot tell the two apart.
    """
    rows: list[list[float]] = []
    banners: list[tuple[str, int]] = []
    order: list[tuple[str, object]] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if pattern.match(line):
            values = _split_fixed_width(line)
            rows.append(values)
            order.append(("row", len(values)))
        elif _RULE_RE.match(line):
            # A rule closes the block. `_BANNER_RE` would otherwise match it as a banner with
            # empty text -- harmless while echo-table banners were discarded, but it put
            # phantom entries in the document layout the moment anything looked at them.
            break
        elif _BANNER_RE.match(line):
            text = _BANNER_RE.match(line).group("text")  # type: ignore[union-attr]
            banners.append((text, index))
            order.append(("banner", text))
        elif line.strip().startswith(_NOTE_PREFIX):
            banners.append((line.strip(), index))
            order.append(("note", line.strip()))
        elif not line.strip():
            pass
        else:
            break
        index += 1
    return rows, banners, index, order


def _frame(rows: list[list[float]], names: list[str], index_name: str | None) -> pd.DataFrame:
    """Build a frame, padding short rows with NaN (the truncated terminating row)."""
    width = len(names)
    padded = [
        row + [float("nan")] * (width - len(row)) if len(row) < width else row[:width]
        for row in rows
    ]
    frame = pd.DataFrame(padded, columns=names)
    if index_name and index_name in frame.columns:
        frame = frame.set_index(index_name)
        frame.index = frame.index.astype(int)
    return frame


def parse_dat(raw: str, source: str = "<string>") -> DatFile:
    """Parse `.dat` text."""
    lines = raw.replace("\r\n", "\n").split("\n")

    echoed: dict[str, pd.DataFrame] = {}
    nearfield: pd.DataFrame | None = None
    farfield: pd.DataFrame | None = None
    events: list[Event] = []
    wastefield_width: float | None = None
    eddy_law: str | None = None
    pending_banners: list[tuple[str, int]] = []

    units: dict[str, list[str]] = {}
    columns: dict[str, list[str]] = {}
    layout: list[tuple[str, object]] = []
    row_widths: dict[tuple[str, int], int] = {}

    def record(
        table: str, names: list[str], header_line: int, order: list[tuple[str, object]]
    ) -> None:
        """Note a table's header and how its rows and banners interleaved.

        Units are taken by **slicing** the raw line into ten-column fields, not by splitting
        on whitespace: the ambient row ends `(deg)(m0.67/s2)` with no space between them, and
        splitting merges the two into one token. They are kept as displayed, parentheses and
        all, because the writer re-emits them verbatim.
        """
        raw = lines[header_line] if header_line < len(lines) else ""
        sliced = [raw[j : j + 10].strip() for j in range(0, len(raw), 10)]
        columns[table], units[table] = names, [f for f in sliced if f]
        layout.append(("header", table))
        run = 0
        position = 0
        for kind, payload in order:
            if kind == "row":
                assert isinstance(payload, int)
                row_widths[table, position] = payload
                position += 1
                run += 1
                continue
            if run:
                layout.append(("rows", (table, run)))
                run = 0
            layout.append((kind, payload))
        if run:
            layout.append(("rows", (table, run)))

    index = 0
    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue
        if _RULE_RE.match(line):
            layout.append(("rule", line.strip()[0]))
            index += 1
            continue

        # Before the table-heading test: `Constant Eddy Diffusivity is used:` is letters and a
        # colon, exactly what a heading looks like, and was being read as one (case50). The 4/3
        # form only escaped because `4/3` is not letters.
        match = _EDDY_RE.match(line)
        if match:
            eddy_law = match.group("law").strip()
            layout.append(("eddy", eddy_law))
            index += 1
            continue

        heading = _TABLE_HEADING_RE.match(line)
        if heading:
            name = heading.group("name").strip()
            layout.append(("heading", name))
            header_line = index + 2
            names, _unit_row, index = _parse_header_block(lines, index + 1)
            if name.lower().startswith("simulation"):
                rows, banners, index, order = _numeric_rows(lines, index, _STEP_ROW_RE)
                # A run can emit the header and no steps at all -- the Dec-2025
                # artifact in case00 does. Its echoed input tables are still useful
                # (they decoded the unit flags), so this is not an error.
                nearfield = _frame(rows, names, "Step")
                pending_banners.extend(banners)
                record("Simulation Results", names, header_line, order)
            else:
                rows, _b, index, order = _numeric_rows(lines, index, _FLOAT_ROW_RE)
                table = name.removesuffix(" Table")
                echoed[table] = _frame(rows, names, None)
                record(table, names, header_line, order)
            continue

        banner = _BANNER_RE.match(line)
        if banner:
            pending_banners.append((banner.group("text"), index))
            layout.append(("banner", banner.group("text")))
            index += 1
            continue

        if line.strip().startswith(_NOTE_PREFIX):
            pending_banners.append((line.strip(), index))
            layout.append(("note", line.strip()))
            index += 1
            continue

        match = _WASTEFIELD_RE.search(line)
        if match:
            wastefield_width = float(match.group("width"))
            layout.append(("wastefield", wastefield_width))
            index += 1
            continue

        # An unheaded column block: the far-field table, which has no 'X:' heading.
        header_line = index + 1
        names, _unit_row, next_index = _parse_header_block(lines, index)
        rows, banners, next_index, order = _numeric_rows(lines, next_index, _FLOAT_ROW_RE)
        if rows:
            farfield = _frame(rows, names, None)
            pending_banners.extend(banners)
            record("farfield", names, header_line, order)
            index = next_index
            continue

        raise DatFormatError(f"{source}: line {index + 1}: unrecognised content {line!r}")

    if nearfield is None:
        raise DatFormatError(f"{source}: no 'Simulation Results' section found")

    steps = [int(step) for step in nearfield.index]
    for text, line_number in sorted(pending_banners, key=lambda item: item[1]):
        next_step = _first_step_after(lines, line_number, steps)
        events.append(Event(text=text, next_step=next_step, line_number=line_number + 1))

    return DatFile(
        echoed_tables=echoed,
        nearfield=nearfield,
        farfield=farfield,
        events=events,
        wastefield_width=wastefield_width,
        eddy_diffusivity_law=eddy_law,
        units=units,
        columns=columns,
        layout=layout,
        row_widths=row_widths,
    )


def _first_step_after(lines: list[str], line_number: int, steps: list[int]) -> int | None:
    """The step number of the first step row following `line_number`."""
    for line in lines[line_number + 1 :]:
        if _STEP_ROW_RE.match(line):
            candidate = int(line.split()[0])
            if candidate in steps:
                return candidate
    return None


def read_dat(path: str | Path) -> DatFile:
    """Read a `.dat` output file from disk."""
    file_path = Path(path)
    dat = parse_dat(file_path.read_bytes().decode("ascii"), source=str(file_path))
    dat.source_path = file_path
    return dat


def format_dat(dat: DatFile) -> str:
    """Rebuild the `.dat` text from a parsed file -- Phase 6 track A.

    Nothing here replays raw text. Every line is regenerated from `dat_format`'s measured
    primitives: rules from their fill character, headers from the retained names and units,
    rows from the parsed floats, banners from the per-message table. `DatFile.layout` supplies
    only the *order*, which is the one thing that cannot be derived.

    ⚠️ **Byte-exactness here tests the formatter, not the physics.** Feeding it the exe's own
    numbers reproduces the exe's file; feeding it ours would not, because our dilution differs
    by 0.3-1 %. That is the only sense in which a re-implementation can be byte-exact, and
    PLAN.md Phase 6 states the acceptance that way for exactly this reason.
    """
    from plumes2.io.dat_format import (
        ASTERISK_RULE,
        DASH_RULE,
        format_banner,
        format_eddy_law,
        format_header,
        format_row,
        format_wastefield_width,
    )

    frames = {"Simulation Results": dat.nearfield, "farfield": dat.farfield, **dat.echoed_tables}
    cursors = dict.fromkeys(frames, 0)
    lines: list[str] = []

    for kind, payload in dat.layout:
        match kind:
            case "rule":
                lines.append(ASTERISK_RULE if payload == "*" else DASH_RULE)
            case "heading":
                lines.append(f"{payload}:")
            case "header":
                table = str(payload)
                lines.extend(format_header(dat.columns[table], dat.units[table]))
            case "rows":
                assert isinstance(payload, tuple)
                table, count = str(payload[0]), int(payload[1])
                frame = frames[table]
                if frame is None:
                    continue
                columns = dat.columns[table]
                start = cursors[table]
                for position in range(start, start + count):
                    row = frame.iloc[position]
                    values = list(row.to_numpy(dtype=float))
                    if frame.index.name:
                        values = [float(frame.index[position]), *values]
                    # The retained field count is what distinguishes a genuinely short row
                    # -- the truncated terminating step -- from one padded with NaN.
                    width = dat.row_widths.get((table, position), len(values))
                    lines.append(format_row(values[:width], table, columns))
                cursors[table] = start + count
            case "banner":
                lines.append(format_banner(str(payload)))
            case "note":
                lines.append(str(payload))
            case "wastefield":
                assert isinstance(payload, float)
                lines.append(format_wastefield_width(payload))
            case "eddy":
                lines.append(format_eddy_law(str(payload)))
            case _:
                raise DatFormatError(f"unknown layout entry {kind!r}")

    # Every archived file ends with a single CRLF and contains no blank lines.
    return "\r\n".join(lines) + "\r\n"


def write_dat(dat: DatFile, path: str | Path) -> None:
    """Write a `.dat`, byte-for-byte as the exe would."""
    Path(path).write_bytes(format_dat(dat).encode("ascii"))
