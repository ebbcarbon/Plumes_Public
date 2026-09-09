"""Reader and writer for the PLUMES2.0 `.prj` project file.

The format is undocumented; this layout was reverse-engineered by diffing the
three `.prj` files in the repo (see PORTING_NOTES.md section 4 and
reference_cases/README.md). Record order is strictly sequential:

===========================  ==================================================
Records                      Meaning
===========================  ==================================================
1 text                       project description
9 int + 20x9 real            diffuser: unit selectors, then 20 case rows
5 int + 20x4 real            effluent
3 int + 20x2 real            mixing zone
11 int + 20x10 real          ambient
3 real                       aspiration, contraction, light absorption
6 int                        near-field flags (position 4 = max rise/fall)
1 int                        near-field output interval, in steps
1 text                       output filename stem
2 real                       shoreline vector
M int                        near-field plot flags (build-dependent: 1 or 4)
1 int + N text               near-field plot variable count, then N names
M int                        far-field plot flags (7 in every file seen)
1 int + N text               far-field plot variable count, then N names
===========================  ==================================================

That model predicts the exact line counts of every `.prj` we hold -- 144, 149, 143 and
the Dec-2025 build's 147 -- which is the main evidence it is right. Three consequences
for the reader:

* The integer blocks are **per-column unit selectors**, not case flags. The
  per-row case enable lives in the CSVs' leading ``No``/``Yes`` column. These
  selectors silently rescale physical values, so :mod:`plumes2.units` refuses to
  interpret one it does not recognise rather than defaulting to SI.
* The two trailing name lists are **count-prefixed and variable-length**, so the
  file cannot be parsed by fixed line offsets.
* The **number of plot flags is build-dependent** -- the Dec-2025 build writes one
  near-field plot flag where 2026 builds write four. Both blocks are therefore read
  greedily up to the next text record, making the last integer the name count. Hard
  coding four would reject `reference_cases/case00_legacy_fps/project.prj`.

This module is deliberately a *lossless, low-level* view: it keeps all 20 table
rows including the zero padding, and every flag whose meaning we have not yet
decoded. That is what makes byte-exact round-tripping possible. The semantic,
unit-resolved model is :class:`plumes2.config.Case`, built on top of this.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from plumes2.io.fortran import (
    format_int_record,
    format_real_record,
    parse_int_record,
    parse_real_record,
)

__all__ = [
    "LINE_TERMINATOR",
    "TABLE_ROWS",
    "PrjFile",
    "PrjTable",
    "read_prj",
    "write_prj",
]

#: The exe writes CRLF and terminates the final line. Byte-exact output requires both.
LINE_TERMINATOR = "\r\n"

#: Every table is padded to a fixed 20 rows regardless of how many are in use.
TABLE_ROWS = 20

#: (attribute name, number of unit selectors, number of data columns).
_TABLE_SPECS: tuple[tuple[str, int, int], ...] = (
    ("diffuser", 9, 9),
    ("effluent", 5, 4),
    ("mixing_zone", 3, 2),
    ("ambient", 11, 10),
)

_N_NEARFIELD_FLAGS = 6
_N_SHORELINE = 2


class PrjFormatError(ValueError):
    """Raised when a `.prj` does not match the expected record sequence."""


@dataclass(slots=True)
class PrjTable:
    """One input table: per-column unit selectors plus its fixed 20 rows.

    Rows beyond the ones in use are all-zero padding written by the exe; they are
    retained so the file round-trips.
    """

    unit_flags: list[int]
    rows: list[list[float]]

    @property
    def n_columns(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def used_rows(self) -> list[list[float]]:
        """The leading rows that are not all-zero padding.

        Only meaningful for tables whose first column is a depth or a diameter, i.e.
        where an all-zero row cannot be a real entry. The CSV `Yes`/`No` column is
        the authoritative case selector; this is a convenience for the ambient table.
        """
        used: list[list[float]] = []
        for row in self.rows:
            if all(value == 0.0 for value in row):
                break
            used.append(row)
        return used


@dataclass(slots=True)
class PrjFile:
    """A lossless in-memory representation of a `.prj` file."""

    description: str
    diffuser: PrjTable
    effluent: PrjTable
    mixing_zone: PrjTable
    ambient: PrjTable

    aspiration_coefficient: float
    contraction_coefficient: float
    light_absorption: float

    #: Six near-field flags, decoded by cases 46, 51 and 52 (rows 187, 281c, 282, 283).
    #: 1-indexed: **1 = the stop-at-bottom box** (1 = stop, case52), **2 = the stop-at-surface
    #: box** (1 = stop, case46), **3 = the stop-at-shoreline box** -- and ⚠️⚠️ **writing 1
    #: there against a zero shoreline vector makes the exe fail silently and truncate the
    #: project on rewrite** (row 282); **4 = the "No. of maximum plume rise or fall" count**;
    #: 5 and 6 are file-owned constants with no dialog control (recon checklist, case51),
    #: always 1, 1.
    nearfield_flags: list[int]
    #: Near-field output interval, in solver steps.
    output_interval: int
    #: Output filename stem, without the `_TxtOutputs.dat` suffix convention.
    output_filename: str
    #: Shoreline vector; the coordinate convention is not yet established.
    shoreline: list[float]

    nearfield_plot_flags: list[int]
    nearfield_plot_variables: list[str]
    #: Seven far-field flags. ✅ **Positions 2, 3 and 4 (1-indexed) are the eddy-diffusivity law
    #: selector, one-hot** -- decoded by case50 (2026-08-26), where the same project run under each
    #: option came back `1,1,0,0,1,1,0` (Constant), `1,0,1,0,1,1,0` (Linearly varying) and the
    #: archive's `1,0,0,1,1,1,0` (4/3 power law, the GUI default and the only value seen before).
    #: The far-field header names the same choice (`io.dat.DatFile.eddy_diffusivity_law`).
    #: The flag-decode suite (case51, rows 281/281b) settled the rest: **positions 1 and 5 each
    #: gate the whole far field** (0 = no far-field block; both file-owned, and *neither shows
    #: a dialog control* -- gates without checkboxes, recon checklist), position 6 is a
    #: file-owned bit with no dialog control, inert on that run, and position 7 is
    #: **exe-owned** -- written 1, the exe rewrites it to 0. Every archived project reads
    #: 1, ?, ?, ?, 1, 1, 0.
    farfield_flags: list[int]
    farfield_plot_variables: list[str]

    #: Populated by :func:`read_prj` so callers can report where a file came from.
    source_path: Path | None = field(default=None, compare=False)

    def to_text(self) -> str:
        """Serialise to the exact text the exe would write, CRLF-terminated."""
        lines: list[str] = [self.description]

        for name, n_flags, n_columns in _TABLE_SPECS:
            table: PrjTable = getattr(self, name)
            if len(table.unit_flags) != n_flags:
                raise PrjFormatError(
                    f"{name}: expected {n_flags} unit flags, got {len(table.unit_flags)}"
                )
            if len(table.rows) != TABLE_ROWS:
                raise PrjFormatError(f"{name}: expected {TABLE_ROWS} rows, got {len(table.rows)}")
            lines.extend(format_int_record(flag) for flag in table.unit_flags)
            for row in table.rows:
                if len(row) != n_columns:
                    raise PrjFormatError(f"{name}: expected {n_columns} columns per row")
                lines.append(format_real_record(row))

        lines.append(format_real_record([self.aspiration_coefficient]))
        lines.append(format_real_record([self.contraction_coefficient]))
        lines.append(format_real_record([self.light_absorption]))

        lines.extend(format_int_record(flag) for flag in self.nearfield_flags)
        lines.append(format_int_record(self.output_interval))
        lines.append(self.output_filename)
        lines.extend(format_real_record([value]) for value in self.shoreline)

        lines.extend(format_int_record(flag) for flag in self.nearfield_plot_flags)
        lines.append(format_int_record(len(self.nearfield_plot_variables)))
        lines.extend(self.nearfield_plot_variables)

        lines.extend(format_int_record(flag) for flag in self.farfield_flags)
        lines.append(format_int_record(len(self.farfield_plot_variables)))
        lines.extend(self.farfield_plot_variables)

        return LINE_TERMINATOR.join(lines) + LINE_TERMINATOR


class _RecordReader:
    """Sequential cursor over the file's lines, with locating error messages."""

    def __init__(self, lines: Sequence[str], source: str) -> None:
        self._lines = lines
        self._source = source
        self._index = 0

    @property
    def source(self) -> str:
        return self._source

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._lines)

    @property
    def remaining(self) -> int:
        return len(self._lines) - self._index

    def _next(self, what: str) -> str:
        if self.exhausted:
            raise PrjFormatError(
                f"{self._source}: file ended while reading {what} (after {self._index} records)"
            )
        line = self._lines[self._index]
        self._index += 1
        return line

    def _fail(self, what: str, error: Exception) -> PrjFormatError:
        return PrjFormatError(f"{self._source}: line {self._index} reading {what}: {error}")

    def text(self, what: str) -> str:
        return self._next(what)

    def integer(self, what: str) -> int:
        line = self._next(what)
        try:
            return parse_int_record(line)
        except ValueError as error:
            raise self._fail(what, error) from error

    def integers(self, count: int, what: str) -> list[int]:
        return [self.integer(f"{what}[{i}]") for i in range(count)]

    def peek_is_integer(self) -> bool:
        """Whether the next record parses as an integer (False at end of file)."""
        if self.exhausted:
            return False
        try:
            parse_int_record(self._lines[self._index])
        except ValueError:
            return False
        return True

    def integers_until_text(self, what: str) -> list[int]:
        """Consume integer records up to the next text record.

        The two trailing plot blocks are `flags..., count, name * count`, and the
        number of flags differs between exe builds -- the Dec-2025 build writes one
        near-field plot flag where 2026 builds write four. Reading greedily up to the
        first non-integer makes the count the last integer consumed, so both layouts
        parse without the reader having to know which build wrote the file.
        """
        values: list[int] = []
        while self.peek_is_integer():
            values.append(self.integer(f"{what}[{len(values)}]"))
        if not values:
            raise PrjFormatError(
                f"{self._source}: line {self._index + 1}: expected at least one integer for {what}"
            )
        return values

    def reals(self, count: int, what: str) -> list[float]:
        line = self._next(what)
        try:
            return parse_real_record(line, count)
        except ValueError as error:
            raise self._fail(what, error) from error

    def scalar(self, what: str) -> float:
        return self.reals(1, what)[0]


def _split_lines(raw: str) -> list[str]:
    """Split on CRLF or LF, dropping exactly one trailing terminator."""
    text = raw.replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n")


def _read_table(reader: _RecordReader, name: str, n_flags: int, n_columns: int) -> PrjTable:
    flags = reader.integers(n_flags, f"{name} unit flags")
    rows = [reader.reals(n_columns, f"{name} row {row_index}") for row_index in range(TABLE_ROWS)]
    return PrjTable(unit_flags=flags, rows=rows)


def _iter_names(reader: _RecordReader, count: int, what: str) -> Iterator[str]:
    for index in range(count):
        yield reader.text(f"{what}[{index}]")


def _read_plot_block(reader: _RecordReader, what: str) -> tuple[list[int], list[str]]:
    """Read one `flags..., count, name * count` plot block.

    The flag count is build-dependent (1 near-field flag in the Dec-2025 build, 4 in
    2026 builds), so the block is read greedily: every integer up to the next text
    record, of which the last is the name count.
    """
    values = reader.integers_until_text(f"{what} flags")
    *flags, count = values
    if count < 0:
        raise PrjFormatError(f"{reader.source}: {what} variable count is negative: {count}")
    names = list(_iter_names(reader, count, f"{what} variable"))
    return flags, names


def parse_prj(raw: str, source: str = "<string>") -> PrjFile:
    """Parse `.prj` text into a :class:`PrjFile`."""
    reader = _RecordReader(_split_lines(raw), source)

    description = reader.text("description")
    tables = {
        name: _read_table(reader, name, n_flags, n_columns)
        for name, n_flags, n_columns in _TABLE_SPECS
    }

    aspiration = reader.scalar("aspiration coefficient")
    contraction = reader.scalar("contraction coefficient")
    light_absorption = reader.scalar("light absorption")

    nearfield_flags = reader.integers(_N_NEARFIELD_FLAGS, "near-field flags")
    output_interval = reader.integer("output interval")
    output_filename = reader.text("output filename")
    shoreline = [reader.scalar(f"shoreline[{i}]") for i in range(_N_SHORELINE)]

    nearfield_plot_flags, nearfield_names = _read_plot_block(reader, "near-field plot")
    farfield_flags, farfield_names = _read_plot_block(reader, "far-field plot")

    if not reader.exhausted:
        raise PrjFormatError(
            f"{source}: {reader.remaining} unexpected trailing record(s); "
            "the record sequence in this module does not match this file"
        )

    return PrjFile(
        description=description,
        diffuser=tables["diffuser"],
        effluent=tables["effluent"],
        mixing_zone=tables["mixing_zone"],
        ambient=tables["ambient"],
        aspiration_coefficient=aspiration,
        contraction_coefficient=contraction,
        light_absorption=light_absorption,
        nearfield_flags=nearfield_flags,
        output_interval=output_interval,
        output_filename=output_filename,
        shoreline=shoreline,
        nearfield_plot_flags=nearfield_plot_flags,
        nearfield_plot_variables=nearfield_names,
        farfield_flags=farfield_flags,
        farfield_plot_variables=farfield_names,
    )


def read_prj(path: str | Path) -> PrjFile:
    """Read a `.prj` file from disk."""
    file_path = Path(path)
    raw = file_path.read_bytes().decode("ascii")
    prj = parse_prj(raw, source=str(file_path))
    prj.source_path = file_path
    return prj


def write_prj(prj: PrjFile, path: str | Path) -> None:
    """Write a `.prj` file, byte-for-byte as the exe would."""
    Path(path).write_bytes(prj.to_text().encode("ascii"))
