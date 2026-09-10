"""A project bundle: a `.prj` plus the CSV tables that live beside it.

Two facts from the reference cases shape this module.

**The `.prj` wins.** case01's `.prj` and its ambient CSV disagree on the current at
15 m (0.050 vs 0.020 m/s) and the exe's own output echoes the `.prj` value. So the four
core tables -- diffuser, effluent, mixing zone, ambient -- are read from the `.prj`,
and any CSV that contradicts it produces a :class:`ProjectDriftWarning` rather than
being silently preferred or silently ignored.

**Chemistry is not in the `.prj` at all.** case03 ran with the carbonate module on and
its project file contains no chemistry values, no enable flag and no chem-CSV name. So
ambient chemistry and DO can only come from CSVs, and the effluent carbonate endmember
cannot come from the project at all -- it has to be supplied separately (via a YAML
case, or by hand). A `.prj` we write can never round-trip chemistry back into the exe.

CSV files are identified by *layout* rather than filename, because the names vary
freely across the cases we hold (`Ambient_example.csv`, `ambient.csv`,
`testambient.csv`). Where two files share a layout -- case01 has both
`effluent.csv` and `varios flows.csv` -- the one agreeing with the `.prj` is
preferred and the ambiguity is reported.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

from plumes2.config import (
    AmbientChemistryLevel,
    AmbientDOLevel,
    AmbientLevel,
    AmbientProfile,
    Case,
    Diffuser,
    Effluent,
    FarFieldSettings,
    MixingZone,
    NearFieldSettings,
)
from plumes2.io.csv_tables import CsvTable, TableKind, read_csv_table
from plumes2.io.fortran import format_e, parse_e
from plumes2.io.prj import TABLE_ROWS, PrjFile, PrjTable, read_prj
from plumes2.units import convert_row_to_si, evidenced_options, selector_for_column, unit_for

__all__ = [
    "Project",
    "ProjectAmbiguityWarning",
    "ProjectDriftWarning",
    "load_project",
    "prj_from_case",
]

#: Values differing by more than this fraction are treated as genuine drift rather
#: than a rounding artifact. The CSVs carry three significant figures, the `.prj`
#: three, so 0.1 % is comfortably above representation noise.
_DRIFT_TOLERANCE = 1e-3


class ProjectDriftWarning(UserWarning):
    """A CSV disagrees with the `.prj`, which is authoritative."""


class ProjectAmbiguityWarning(UserWarning):
    """Two CSVs share a layout and the project cannot say which is meant."""


@dataclass(slots=True)
class Project:
    """A `.prj` and the CSV tables found alongside it."""

    prj: PrjFile
    #: CSVs by layout. Only chemistry and DO are load-bearing; the rest are kept for
    #: drift reporting and for byte-exact rewriting.
    tables: dict[TableKind, CsvTable] = field(default_factory=dict)
    directory: Path | None = None

    @property
    def has_chemistry(self) -> bool:
        return TableKind.AMBIENT_CHEM in self.tables

    @property
    def has_dissolved_oxygen(self) -> bool:
        return TableKind.AMBIENT_DO in self.tables

    def si_row(self, kind: TableKind, table: PrjTable, row_index: int = 0) -> list[float]:
        """One `.prj` row converted to SI using that table's unit selectors."""
        return convert_row_to_si(kind, table.unit_flags, table.rows[row_index])

    def to_case(self, row_index: int = 0) -> Case:
        """Build a validated :class:`Case` from row `row_index` of each core table.

        Note the CSV `Yes`/`No` case column is **not** consulted, because its role is
        unresolved: the upstream example marks its diffuser row `No` and the exe ran it
        anyway. Row 0 is used by default; pass `row_index` to select another stored case.
        """
        diffuser_values = self.si_row(TableKind.DIFFUSER, self.prj.diffuser, row_index)
        effluent_values = self.si_row(TableKind.EFFLUENT, self.prj.effluent, row_index)
        mixing_values = self.si_row(TableKind.MIXING_ZONE, self.prj.mixing_zone, row_index)

        diffuser = Diffuser(
            port_diameter=diffuser_values[0],
            port_elevation=diffuser_values[1],
            vertical_angle=diffuser_values[2],
            horizontal_angle=diffuser_values[3],
            n_ports=round(diffuser_values[4]),
            port_spacing=diffuser_values[5],
            port_depth=diffuser_values[6],
            x_position=diffuser_values[7],
            y_position=diffuser_values[8],
        )
        effluent = Effluent(
            flow=effluent_values[0],
            salinity=effluent_values[1],
            temperature=effluent_values[2],
            pollutant=effluent_values[3],
        )
        mixing_zone = MixingZone(acute_distance=mixing_values[0], chronic_distance=mixing_values[1])

        levels = [
            AmbientLevel(
                **dict(
                    zip(
                        TableKind.AMBIENT.column_names,
                        self.si_row(TableKind.AMBIENT, self.prj.ambient, index),
                        strict=True,
                    )
                )
            )
            for index in range(len(self.prj.ambient.used_rows()))
        ]
        ambient = AmbientProfile(
            levels=levels,
            chemistry=self._chemistry_levels(),
            dissolved_oxygen=self._dissolved_oxygen_levels(),
        )

        near_field = NearFieldSettings(
            aspiration_coefficient=self.prj.aspiration_coefficient,
            contraction_coefficient=self.prj.contraction_coefficient,
            light_absorption=self.prj.light_absorption,
            # Position 4 (1-indexed) of the near-field flag block.
            max_rise_or_fall=self.prj.nearfield_flags[3],
            output_interval=self.prj.output_interval,
        )

        return Case(
            description=self.prj.description,
            diffuser=diffuser,
            effluent=effluent,
            mixing_zone=mixing_zone,
            ambient=ambient,
            near_field=near_field,
            # The far-field enable flag and its limits are not identified in the .prj,
            # so defaults stand; see PLAN.md section 7.
            far_field=FarFieldSettings(),
        )

    def _chemistry_levels(self) -> list[AmbientChemistryLevel]:
        table = self.tables.get(TableKind.AMBIENT_CHEM)
        if table is None:
            return []
        levels = []
        for row in table.used_rows():
            depth, alkalinity, dic, ph, calcium = row.values
            if depth is None or alkalinity is None or dic is None:
                continue
            levels.append(
                AmbientChemistryLevel(
                    depth=depth, total_alkalinity=alkalinity, dic=dic, ph=ph, calcium=calcium
                )
            )
        return levels

    def _dissolved_oxygen_levels(self) -> list[AmbientDOLevel]:
        table = self.tables.get(TableKind.AMBIENT_DO)
        if table is None:
            return []
        levels = []
        for row in table.used_rows():
            depth, oxygen, cbod5, nbod5 = row.values
            if depth is None or oxygen is None:
                continue
            levels.append(
                AmbientDOLevel(
                    depth=depth,
                    dissolved_oxygen=oxygen,
                    cbod5=cbod5 or 0.0,
                    nbod5=nbod5 or 0.0,
                )
            )
        return levels

    def drift(self) -> dict[str, list[str]]:
        """Cells where a CSV disagrees with the authoritative `.prj`.

        Returns a mapping of table name to human-readable descriptions. Empty when the
        project is self-consistent.
        """
        report: dict[str, list[str]] = {}
        pairs = (
            (TableKind.DIFFUSER, self.prj.diffuser),
            (TableKind.EFFLUENT, self.prj.effluent),
            (TableKind.MIXING_ZONE, self.prj.mixing_zone),
            (TableKind.AMBIENT, self.prj.ambient),
        )
        for kind, prj_table in pairs:
            csv_table = self.tables.get(kind)
            if csv_table is None:
                continue
            differences = _compare(kind, prj_table, csv_table)
            if differences:
                report[kind.name] = differences
        return report


def _compare(kind: TableKind, prj_table: PrjTable, csv_table: CsvTable) -> list[str]:
    """Describe cells where the CSV differs from the `.prj`, in stored units."""
    differences: list[str] = []
    columns = kind.column_names
    for row_index, csv_row in enumerate(csv_table.rows):
        prj_row = prj_table.rows[row_index]
        for column_index, column in enumerate(columns):
            csv_value = csv_row.values[column_index]
            prj_value = prj_row[column_index]
            if csv_value is None:
                # A blank CSV cell against a zero .prj cell is padding, not drift.
                if prj_value != 0.0:
                    differences.append(
                        f"row {row_index} {column}: .prj has {prj_value:g}, CSV is blank"
                    )
                continue
            scale = max(abs(prj_value), abs(csv_value), 1.0)
            if abs(csv_value - prj_value) / scale > _DRIFT_TOLERANCE:
                differences.append(
                    f"row {row_index} {column}: .prj has {prj_value:g}, CSV has {csv_value:g}"
                )
    return differences


def _discover_tables(directory: Path, prj: PrjFile) -> dict[TableKind, CsvTable]:
    """Classify every CSV in `directory` by layout, resolving duplicates via the `.prj`."""
    candidates: dict[TableKind, list[CsvTable]] = {}
    for path in sorted(directory.glob("*.csv")):
        try:
            table = read_csv_table(path)
        except ValueError:
            # Not one of the six layouts; not ours to interpret.
            continue
        candidates.setdefault(table.kind, []).append(table)

    core = {
        TableKind.DIFFUSER: prj.diffuser,
        TableKind.EFFLUENT: prj.effluent,
        TableKind.MIXING_ZONE: prj.mixing_zone,
        TableKind.AMBIENT: prj.ambient,
    }
    chosen: dict[TableKind, CsvTable] = {}
    for kind, tables in candidates.items():
        if len(tables) == 1:
            chosen[kind] = tables[0]
            continue
        prj_table = core.get(kind)
        if prj_table is None:
            chosen[kind] = tables[0]
            names = ", ".join(t.source_path.name for t in tables if t.source_path)
            warnings.warn(
                f"{directory.name}: {len(tables)} files share the {kind.name} layout "
                f"({names}); using the first. The .prj does not store this table, so "
                "there is nothing to disambiguate against.",
                ProjectAmbiguityWarning,
                stacklevel=3,
            )
            continue
        # Prefer whichever agrees with the authoritative .prj.
        ranked = sorted(tables, key=lambda t: len(_compare(kind, prj_table, t)))
        chosen[kind] = ranked[0]
        if len(_compare(kind, prj_table, ranked[0])) < len(_compare(kind, prj_table, ranked[-1])):
            names = ", ".join(t.source_path.name for t in tables if t.source_path)
            warnings.warn(
                f"{directory.name}: {len(tables)} files share the {kind.name} layout "
                f"({names}); using {ranked[0].source_path.name if ranked[0].source_path else '?'} "
                "because it agrees with the .prj.",
                ProjectAmbiguityWarning,
                stacklevel=3,
            )
    return chosen


def load_project(prj_path: str | Path, *, warn_on_drift: bool = True) -> Project:
    """Load a `.prj` and the CSV tables beside it."""
    path = Path(prj_path)
    prj = read_prj(path)
    tables = _discover_tables(path.parent, prj)
    project = Project(prj=prj, tables=tables, directory=path.parent)

    if warn_on_drift:
        report = project.drift()
        if report:
            summary = "; ".join(f"{table}: {len(items)} cell(s)" for table, items in report.items())
            warnings.warn(
                f"{path.name}: CSV tables disagree with the project file ({summary}). "
                "The .prj is authoritative -- the exe echoes its values, not the CSVs' "
                "(reference_cases/case01). Call Project.drift() for details.",
                ProjectDriftWarning,
                stacklevel=2,
            )
    return project


# --------------------------------------------------------------------------------------
# Case -> .prj
# --------------------------------------------------------------------------------------

#: Values written for the flag positions whose meaning is still unknown. Taken from the
#: upstream example so a generated project resembles one the exe wrote itself. See
#: PLAN.md section 7 for the positions still to be identified.
_DEFAULT_NEARFIELD_FLAGS = (1, 1, 0, 2, 1, 1)
_DEFAULT_NEARFIELD_PLOT_FLAGS = (1, 1, 0, 0)
_DEFAULT_FARFIELD_FLAGS = (1, 0, 0, 1, 1, 1, 0)
_DEFAULT_NEARFIELD_VARIABLES = (
    "FluxAvg-Dilution",
    "Plume-Diameter",
    "Position-Xdir",
    "Position-Ydir",
    "Plume-Depth",
)
_DEFAULT_FARFIELD_VARIABLES = ("Dilution", "P-Width", "Distance", "Time")


def _best_selector(kind: TableKind, column: str, value_si: float) -> tuple[int, float]:
    """Choose the unit that survives the `.prj`'s three significant figures best.

    Real records carry a 3-digit mantissa, so some precision is usually lost, and which
    unit loses less depends on the value: 8 MGD is exact as `0.800E+01` but becomes
    0.350 m3/s (0.14 % low), while 2.0 ft is exact but becomes 0.610 m (0.07 % high).
    Trying every candidate and keeping the closest makes a generated project as faithful
    as the format allows, and keeps any value that originated in a supported unit exact.

    Only selectors a reference case evidences are considered -- writing one whose meaning
    we merely infer would risk the exe reading the file differently than we wrote it.

    Returns `(selector, value expressed in that unit)`.
    """
    options = evidenced_options(kind, column)
    if not options:
        return 1, value_si

    best_selector, best_value, best_error = 1, value_si, float("inf")
    for selector, unit in sorted(options.items()):
        value = value_si / unit.to_si
        recovered = parse_e(format_e(value)) * unit.to_si
        error = abs(recovered - value_si)
        if error < best_error:
            best_selector, best_value, best_error = selector, value, error
    return best_selector, best_value


def _encode_row(kind: TableKind, values_si: list[float]) -> tuple[list[int], list[float]]:
    """Encode an SI row into stored values plus the selector block for its table.

    Selectors are chosen per column, then laid out with the leading entry that effluent,
    mixing-zone and ambient blocks carry and the diffuser does not.
    """
    columns = kind.column_names
    offset = 0 if kind is TableKind.DIFFUSER else 1
    selectors = [1] * (len(columns) + offset)
    stored: list[float] = []
    for index, (column, value) in enumerate(zip(columns, values_si, strict=True)):
        selector, encoded = _best_selector(kind, column, value)
        stored.append(encoded)
        selectors[index + offset] = selector
    return selectors, stored


def _padded(rows: list[list[float]], n_columns: int) -> list[list[float]]:
    """Pad to the fixed 20 rows the exe writes."""
    if len(rows) > TABLE_ROWS:
        raise ValueError(f"a .prj table holds at most {TABLE_ROWS} rows, got {len(rows)}")
    return rows + [[0.0] * n_columns for _ in range(TABLE_ROWS - len(rows))]


def prj_from_case(
    case: Case, *, template: PrjFile | None = None, output_filename: str = "ModelResults_TxtOutputs"
) -> PrjFile:
    """Build a `.prj` from a :class:`~plumes2.config.Case`.

    Everything the `.prj` can express is written from the case, in SI. The flag
    positions we have not decoded are copied from `template` when one is given, and
    otherwise take the upstream example's values -- so a generated project looks like
    one the exe produced.

    **Chemistry is not written**, because no `.prj` stores it (case03 ran with the
    carbonate module on and its project file contains none). A project generated from a
    case with chemistry will open in the exe as a hydrodynamics-only run; the chemistry
    has to be re-entered in the GUI.
    """
    diffuser = case.diffuser
    effluent = case.effluent

    diffuser_flags, diffuser_values = _encode_row(
        TableKind.DIFFUSER,
        [
            diffuser.port_diameter,
            diffuser.port_elevation,
            diffuser.vertical_angle,
            diffuser.horizontal_angle,
            float(diffuser.n_ports),
            diffuser.port_spacing,
            diffuser.port_depth,
            diffuser.x_position,
            diffuser.y_position,
        ],
    )
    diffuser_rows = _padded([diffuser_values], 9)
    effluent_flags, effluent_values = _encode_row(
        TableKind.EFFLUENT,
        [effluent.flow, effluent.salinity, effluent.temperature, effluent.pollutant],
    )
    effluent_rows = _padded([effluent_values], 4)
    mixing_flags, mixing_values = _encode_row(
        TableKind.MIXING_ZONE,
        [case.mixing_zone.acute_distance, case.mixing_zone.chronic_distance],
    )
    mixing_rows = _padded([mixing_values], 2)
    ambient_encoded = [
        _encode_row(
            TableKind.AMBIENT,
            [getattr(level, column) for column in TableKind.AMBIENT.column_names],
        )
        for level in case.ambient.levels
    ]
    ambient_flags = ambient_encoded[0][0] if ambient_encoded else [1] * 11
    ambient_rows = _padded([values for _flags, values in ambient_encoded], 10)

    near_field_flags = list(template.nearfield_flags if template else _DEFAULT_NEARFIELD_FLAGS)
    near_field_flags[3] = case.near_field.max_rise_or_fall

    return PrjFile(
        description=case.description,
        diffuser=PrjTable(unit_flags=diffuser_flags, rows=diffuser_rows),
        effluent=PrjTable(unit_flags=effluent_flags, rows=effluent_rows),
        mixing_zone=PrjTable(unit_flags=mixing_flags, rows=mixing_rows),
        ambient=PrjTable(unit_flags=ambient_flags, rows=ambient_rows),
        aspiration_coefficient=case.near_field.aspiration_coefficient,
        contraction_coefficient=case.near_field.contraction_coefficient,
        light_absorption=case.near_field.light_absorption,
        nearfield_flags=near_field_flags,
        output_interval=case.near_field.output_interval,
        output_filename=output_filename,
        shoreline=list(template.shoreline) if template else [0.0, 0.0],
        nearfield_plot_flags=list(
            template.nearfield_plot_flags if template else _DEFAULT_NEARFIELD_PLOT_FLAGS
        ),
        nearfield_plot_variables=list(
            template.nearfield_plot_variables if template else _DEFAULT_NEARFIELD_VARIABLES
        ),
        farfield_flags=list(template.farfield_flags if template else _DEFAULT_FARFIELD_FLAGS),
        farfield_plot_variables=list(
            template.farfield_plot_variables if template else _DEFAULT_FARFIELD_VARIABLES
        ),
    )


def written_units(prj: PrjFile) -> list[str]:
    """The unit each `.prj` column is *stored* in, for every column not in its primary unit.

    The selectors rescale silently, so a person opening the file in the GUI sees the stored
    number in the stored unit -- `2.00` under the feet flag where the case said 0.6096 m. This is
    the line that says so before the GUI does. `prj_from_case` picks, per value, the evidenced unit
    that survives the format's three significant figures best (`_best_selector`), so a metric case
    can legitimately come out in feet or MGD; the exe reads either as written (ledger row 290,
    case55), a reader may not. One entry per non-primary column, using the first row --
    `table.column: stored value unit (selector n)` -- and an empty list when every table is in its
    primary unit (m, MGD, degC, m/s, mg/L, 1/day). Printed by `plumes2 info` and in every
    experiment note.
    """
    out: list[str] = []
    for attribute, kind in (
        ("diffuser", TableKind.DIFFUSER),
        ("effluent", TableKind.EFFLUENT),
        ("mixing_zone", TableKind.MIXING_ZONE),
        ("ambient", TableKind.AMBIENT),
    ):
        table: PrjTable = getattr(prj, attribute)
        first = table.rows[0] if table.rows else []
        for index, column in enumerate(kind.column_names):
            selector = selector_for_column(kind, table.unit_flags, index)
            if selector == 1:
                continue
            unit = unit_for(kind, column, selector)
            value = f"{first[index]:g} " if index < len(first) else ""
            out.append(f"{attribute}.{column}: {value}{unit.name} (selector {selector})")
    return out
