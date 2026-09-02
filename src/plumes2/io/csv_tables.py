"""Reader and writer for the six PLUMES2.0 CSV input tables.

All six share one shape: exactly 20 rows, numeric fields quoted and written in
``%.2E`` form, and unused rows left blank rather than zeroed. Three of them carry a
leading unquoted ``No``/``Yes`` **case enable** column -- that is the per-row
selector, distinct from the per-column *unit* selectors in the `.prj`.

There are two irregularities, both required for byte-exact output:

* The diffuser's port-count column is an **unquoted integer** (``18``), and blank
  in an unused row is a bare empty field rather than ``""``.
* An individual field may be blank while its neighbours are populated -- the
  ambient-chemistry pH column is left blank in `reference_cases/case03`, which is
  how we learned the exe derives pH from TA and DIC. So a value is
  ``float | None``, and ``None`` must not collapse to ``0.0``.

Table kinds are told apart by column count plus whether the first field is quoted,
which is unambiguous across all six::

    (10, quoted)   ambient          (10, unquoted) diffuser
    ( 5, quoted)   ambient_chem     ( 5, unquoted) effluent
    ( 4, quoted)   ambient_do       ( 3, unquoted) mixing_zone
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "CsvRow",
    "CsvTable",
    "CsvTableError",
    "TableKind",
    "read_csv_table",
    "write_csv_table",
]

#: The exe pads every table to this many rows.
TABLE_ROWS = 20
LINE_TERMINATOR = "\r\n"
_NUMBER_FORMAT = "{:.2E}"


class CsvTableError(ValueError):
    """Raised when a CSV table does not match any known layout."""


class TableKind(Enum):
    """The six table layouts, with their column names in file order.

    Names exclude the leading case-enable column, which is tracked separately.
    """

    AMBIENT = (
        "depth",
        "current_speed",
        "current_direction",
        "salinity",
        "temperature",
        "background_pollutant",
        "decay_rate",
        "farfield_speed",
        "farfield_direction",
        "dispersion_alpha",
    )
    DIFFUSER = (
        "port_diameter",
        "port_elevation",
        "vertical_angle",
        "horizontal_angle",
        "n_ports",
        "port_spacing",
        "port_depth",
        "x_position",
        "y_position",
    )
    EFFLUENT = ("flow", "salinity", "temperature", "pollutant")
    MIXING_ZONE = ("acute_distance", "chronic_distance")
    AMBIENT_DO = ("depth", "dissolved_oxygen", "cbod5", "nbod5")
    AMBIENT_CHEM = ("depth", "total_alkalinity", "dic", "ph", "calcium")

    @property
    def column_names(self) -> tuple[str, ...]:
        return self.value

    @property
    def has_case_column(self) -> bool:
        return self in (TableKind.DIFFUSER, TableKind.EFFLUENT, TableKind.MIXING_ZONE)

    @property
    def integer_column(self) -> int | None:
        """Index of the unquoted-integer column, if the layout has one."""
        return 4 if self is TableKind.DIFFUSER else None

    @property
    def n_fields(self) -> int:
        """Total comma-separated fields per line, including any case column."""
        return len(self.column_names) + (1 if self.has_case_column else 0)


#: (n_fields, first field is quoted) -> kind.
_LAYOUT_LOOKUP: dict[tuple[int, bool], TableKind] = {
    (10, True): TableKind.AMBIENT,
    (10, False): TableKind.DIFFUSER,
    (5, True): TableKind.AMBIENT_CHEM,
    (5, False): TableKind.EFFLUENT,
    (4, True): TableKind.AMBIENT_DO,
    (3, False): TableKind.MIXING_ZONE,
}


@dataclass(slots=True)
class CsvRow:
    """One table row. `enabled` is None for tables with no case column."""

    values: list[float | None]
    enabled: bool | None = None

    @property
    def is_blank(self) -> bool:
        return all(value is None for value in self.values)


@dataclass(slots=True)
class CsvTable:
    """A CSV input table: its layout plus 20 rows."""

    kind: TableKind
    rows: list[CsvRow]
    source_path: Path | None = field(default=None, compare=False)

    @property
    def column_names(self) -> tuple[str, ...]:
        return self.kind.column_names

    def used_rows(self) -> list[CsvRow]:
        """Rows that carry data, in file order."""
        return [row for row in self.rows if not row.is_blank]

    def active_rows(self) -> list[CsvRow]:
        """Rows the exe would actually run.

        For case tables that means ``Yes``; for the ambient/DO/chemistry profiles
        every populated row is part of the profile.
        """
        if not self.kind.has_case_column:
            return self.used_rows()
        return [row for row in self.rows if row.enabled and not row.is_blank]

    def column(self, name: str) -> list[float | None]:
        index = self.column_names.index(name)
        return [row.values[index] for row in self.used_rows()]

    def to_text(self) -> str:
        lines = [self._format_row(row) for row in self.rows]
        return LINE_TERMINATOR.join(lines) + LINE_TERMINATOR

    def _format_row(self, row: CsvRow) -> str:
        if len(row.values) != len(self.column_names):
            raise CsvTableError(
                f"{self.kind.name}: expected {len(self.column_names)} values, got {len(row.values)}"
            )
        fields: list[str] = []
        if self.kind.has_case_column:
            fields.append("Yes" if row.enabled else "No")
        for index, value in enumerate(row.values):
            fields.append(self._format_field(value, index))
        return ",".join(fields)

    def _format_field(self, value: float | None, index: int) -> str:
        if index == self.kind.integer_column:
            # Unquoted, and blank means an empty field rather than an empty string.
            return "" if value is None else str(round(value))
        return '""' if value is None else f'"{_NUMBER_FORMAT.format(value)}"'


def _parse_field(raw: str) -> float | None:
    """A field is either blank (meaning 'not supplied') or a number."""
    text = raw.strip()
    if not text:
        return None
    return float(text)


def parse_csv_table(raw: str, kind: TableKind | None = None, source: str = "<string>") -> CsvTable:
    """Parse CSV text. `kind` is inferred from the layout unless given."""
    # The exe quotes fields but never embeds commas or quotes, so csv handles it.
    rows_raw = [row for row in csv.reader(io.StringIO(raw, newline="")) if row]
    if not rows_raw:
        raise CsvTableError(f"{source}: file is empty")

    n_fields = len(rows_raw[0])
    if kind is None:
        first_quoted = raw.lstrip().startswith('"')
        try:
            kind = _LAYOUT_LOOKUP[(n_fields, first_quoted)]
        except KeyError:
            raise CsvTableError(
                f"{source}: no known table has {n_fields} fields with "
                f"first field {'quoted' if first_quoted else 'unquoted'}"
            ) from None
    elif n_fields != kind.n_fields:
        raise CsvTableError(
            f"{source}: {kind.name} expects {kind.n_fields} fields, found {n_fields}"
        )

    rows: list[CsvRow] = []
    for line_number, raw_row in enumerate(rows_raw, start=1):
        if len(raw_row) != kind.n_fields:
            raise CsvTableError(
                f"{source}: line {line_number} has {len(raw_row)} fields, expected {kind.n_fields}"
            )
        enabled: bool | None = None
        payload = raw_row
        if kind.has_case_column:
            flag = raw_row[0].strip().lower()
            if flag not in ("yes", "no"):
                raise CsvTableError(
                    f"{source}: line {line_number} case column is {raw_row[0]!r}, "
                    "expected 'Yes' or 'No'"
                )
            enabled = flag == "yes"
            payload = raw_row[1:]
        rows.append(CsvRow(values=[_parse_field(f) for f in payload], enabled=enabled))

    return CsvTable(kind=kind, rows=rows)


def read_csv_table(path: str | Path, kind: TableKind | None = None) -> CsvTable:
    """Read one CSV input table from disk."""
    file_path = Path(path)
    raw = file_path.read_bytes().decode("ascii")
    table = parse_csv_table(raw, kind=kind, source=str(file_path))
    table.source_path = file_path
    return table


def write_csv_table(table: CsvTable, path: str | Path) -> None:
    """Write a CSV input table, byte-for-byte as the exe would."""
    Path(path).write_bytes(table.to_text().encode("ascii"))


def blank_table(kind: TableKind) -> CsvTable:
    """An all-blank table of `kind`, padded to 20 rows, ready to fill in."""
    n_values = len(kind.column_names)
    enabled = False if kind.has_case_column else None
    return CsvTable(
        kind=kind,
        rows=[CsvRow(values=[None] * n_values, enabled=enabled) for _ in range(TABLE_ROWS)],
    )


def table_from_values(
    kind: TableKind, rows: Sequence[Sequence[float | None]], *, enable_first: bool = True
) -> CsvTable:
    """Build a table from data rows, padding to 20 and enabling the first case row."""
    table = blank_table(kind)
    if len(rows) > TABLE_ROWS:
        raise CsvTableError(f"{kind.name}: at most {TABLE_ROWS} rows, got {len(rows)}")
    for index, values in enumerate(rows):
        if len(values) != len(kind.column_names):
            raise CsvTableError(
                f"{kind.name}: row {index} has {len(values)} values, "
                f"expected {len(kind.column_names)}"
            )
        table.rows[index].values = list(values)
        if kind.has_case_column:
            table.rows[index].enabled = enable_first and index == 0
    return table
