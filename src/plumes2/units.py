"""Resolution of the `.prj` per-column unit selectors into SI.

Each input table in a `.prj` carries a block of integer unit selectors, one per
column, and they **silently rescale physical values**: the same stored `2.0` is
2 m or 0.61 m depending on one integer elsewhere in the file. Getting this wrong
produces plausible, wrong answers rather than an error, so this module is
deliberately strict -- an unrecognised selector raises rather than defaulting to SI.

The map was decoded from `reference_cases/case00_legacy_fps`, which is the only
matched `.prj` + `.dat` pair we have: the `.prj` stores raw values and the `.dat`
echoes converted ones, so the factors read straight off.

    flag 1  the primary unit    metres, MGD
    flag 2  the alternate unit  feet, m3/s

Directly evidenced there: diffuser spacing (stored 2.0 -> echoed 0.61 m), both
mixing-zone distances (20.7 / 207.0 -> 6.31 / 63.09 m), all exactly x0.3048; and
effluent flow, whose flag-2 column is labelled ``(m3/s)`` by that build and ``(cms)``
by 2026 builds, against ``(MGD)`` for flag 1.

**Flag-to-column alignment differs by table.** The diffuser's 9 selectors map 1:1 to
its 9 columns. Effluent (5 selectors / 4 columns), mixing zone (3 / 2) and ambient
(11 / 10) each carry one leading selector of unknown purpose and then map 1:1 -- so
effluent flow is column 0 but its selector is index 1. See :func:`selector_for_column`.

The full dropdown inventory, confirmed against the GUI (2026-08-12):

===============  ==========================================================
diffuser         every length in m or ft
effluent         flow MGD / cms / cfs; temperature degC or **degF**;
                 pollutant mg/L or **kg/kg**
ambient          depth m or ft; near-field velocity m/s or **ft/s**;
                 temperature degC or **degF**; pollutant mg/L or **kg/kg**;
                 decay **1/day or s-1**; far-field velocity m/s or **ft/s**
===============  ==========================================================

Two of these are not plain scale factors, and were left unregistered until the inventory
confirmed they are real, selectable options rather than manual speculation:

* **degF** is *affine*, so :class:`Unit` carries an ``offset`` applied after scaling.
* **kg/kg** is a mass fraction, so it needs a density. :class:`Unit` marks that with
  ``needs_density`` and :func:`convert_to_si` requires the caller to supply one -- it will
  not invent a seawater density, because the effluent's is what applies to the effluent
  column and it can differ by 3 %.

Everything on the alternate side is registered **unevidenced**: no archived `.prj` selects
any of them, so the factors follow from the unit names rather than from a matched pair. That
keeps :func:`evidenced_options` -- which is what the writer restricts itself to -- unchanged.

⚠️ **An unresolved label ambiguity, orthogonal to all of the above.** The Dec-2025 build
labels *flag-1* pollutant ``kg/kg`` and *flag-1* decay ``s-1``, where 2026 builds label the
same selectors ``mg/L`` and ``1/day``:

    Dec-2025 (case00)   Amb-pol  kg/kg     Decay  s-1     Ttl-flo  (m3/s)
    2026     (test21)   Amb-pol  mg/L      Decay  1/day   Ttl-flo  (cms)

Flow is the control: ``m3/s`` and ``cms`` are the same unit under two spellings, so that
build pair differs in label text alone. But ``kg/kg`` and ``mg/L`` are *not* the same unit,
nor are ``s-1`` and ``1/day`` -- they differ by ~10^6 and by 86400. So either the Dec-2025
build mislabels those two columns, or it genuinely reads the selector differently.

The reference data cannot separate the two: both builds echo the stored value **unchanged**
for flag 1, so nothing observable converts. This does not affect round-trip fidelity, which
is what Phase 1 promises -- only the physical interpretation of the number. Recorded in
PLAN.md §7 rather than guessed at; flag 1 is treated as the 2026 labelling throughout.
"""

from __future__ import annotations

from dataclasses import dataclass

from plumes2.io.csv_tables import TableKind

__all__ = [
    "CUBIC_FEET_TO_CUBIC_METRES",
    "FAHRENHEIT_OFFSET",
    "FAHRENHEIT_SCALE",
    "FEET_TO_METRES",
    "KG_PER_KG_TO_MG_PER_LITRE_PER_DENSITY",
    "MGD_TO_CUBIC_METRES_PER_SECOND",
    "PER_SECOND_TO_PER_DAY",
    "DensityRequiredError",
    "Unit",
    "UnknownUnitFlagError",
    "convert_to_si",
    "evidenced_options",
    "selector_for_column",
    "unit_for",
]

#: Exact by definition.
FEET_TO_METRES = 0.3048
#: 1 US million gallons per day = 3785.411784 m3/day.
MGD_TO_CUBIC_METRES_PER_SECOND = 3785.411784 / 86400.0
#: Exact: (0.3048 m)^3.
CUBIC_FEET_TO_CUBIC_METRES = 0.3048**3
#: degC = degF * (5/9) - 32 * (5/9). Exact as a ratio.
FAHRENHEIT_SCALE = 5.0 / 9.0
FAHRENHEIT_OFFSET = -32.0 * 5.0 / 9.0
#: A mass fraction X in kg/kg is X * rho * 1000 in mg/L, for rho in kg/m3.
KG_PER_KG_TO_MG_PER_LITRE_PER_DENSITY = 1000.0
#: 1 per second = 86400 per day.
PER_SECOND_TO_PER_DAY = 86400.0

#: Tables whose selector block carries one leading entry before the per-column ones.
_OFFSET_TABLES = frozenset({TableKind.EFFLUENT, TableKind.MIXING_ZONE, TableKind.AMBIENT})


class UnknownUnitFlagError(ValueError):
    """Raised for a unit selector whose meaning is not established.

    Deliberately fatal. Guessing would silently rescale a physical input.
    """


class DensityRequiredError(ValueError):
    """Raised when a mass-fraction unit is converted without a density.

    Separate from :class:`UnknownUnitFlagError`: the selector *is* understood, the caller
    simply has not supplied the information the conversion needs.
    """


@dataclass(frozen=True, slots=True)
class Unit:
    """One unit option for a column, and how to reach SI from it.

    The conversion is `value * to_si + offset`, or `value * to_si * density` when
    `needs_density` is set. Only one of `offset` and `needs_density` is ever used.
    """

    name: str
    #: Multiply a value in this unit by this to obtain SI.
    to_si: float
    #: True when a reference case directly demonstrates the factor; False when it is
    #: inferred by analogy with a column that does, or from the unit's name alone.
    evidenced: bool = False
    #: Added *after* scaling, for affine units. Only degF uses this.
    offset: float = 0.0
    #: When set, `to_si` is per (kg/m3) and a density must be supplied. Mass fractions.
    needs_density: bool = False

    def to_si_value(self, value: float, *, density: float | None = None) -> float:
        if self.needs_density:
            if density is None:
                raise DensityRequiredError(
                    f"converting from {self.name} needs a density: it is a mass fraction, "
                    "so the result depends on the fluid it is dissolved in. Pass "
                    "density= (kg/m3) -- the effluent's for an effluent column, the "
                    "ambient's for an ambient one; they can differ by several percent."
                )
            return value * self.to_si * density
        return value * self.to_si + self.offset


_METRE = Unit("m", 1.0, evidenced=True)
_FOOT_EVIDENCED = Unit("ft", FEET_TO_METRES, evidenced=True)
#: Length columns other than spacing and the mixing-zone distances have never been
#: seen with flag 2. Feet is the only plausible alternate given the evidenced columns,
#: so it is registered -- but marked unevidenced so callers can audit the assumption.
_FOOT_INFERRED = Unit("ft", FEET_TO_METRES, evidenced=False)
_DEGREE = Unit("deg", 1.0, evidenced=True)
_DIMENSIONLESS = Unit("", 1.0, evidenced=True)

_LENGTH_EVIDENCED = {1: _METRE, 2: _FOOT_EVIDENCED}
_LENGTH_INFERRED = {1: _METRE, 2: _FOOT_INFERRED}
_ANGLE_ONLY = {1: _DEGREE}
_COUNT_ONLY = {1: _DIMENSIONLESS}

# The alternate side of every dropdown the GUI offers. All unevidenced: no archived .prj
# selects any of them, so the factors come from the unit names, not from a matched pair.
_CELSIUS = Unit("degC", 1.0, evidenced=True)
_FAHRENHEIT = Unit("degF", FAHRENHEIT_SCALE, evidenced=False, offset=FAHRENHEIT_OFFSET)
_TEMPERATURE = {1: _CELSIUS, 2: _FAHRENHEIT}

_MG_PER_LITRE = Unit("mg/L", 1.0, evidenced=True)
_KG_PER_KG = Unit(
    "kg/kg", KG_PER_KG_TO_MG_PER_LITRE_PER_DENSITY, evidenced=False, needs_density=True
)
_CONCENTRATION = {1: _MG_PER_LITRE, 2: _KG_PER_KG}

_METRES_PER_SECOND = Unit("m/s", 1.0, evidenced=True)
_FEET_PER_SECOND = Unit("ft/s", FEET_TO_METRES, evidenced=False)
_VELOCITY = {1: _METRES_PER_SECOND, 2: _FEET_PER_SECOND}

_PER_DAY = Unit("1/day", 1.0, evidenced=True)
_PER_SECOND = Unit("s-1", PER_SECOND_TO_PER_DAY, evidenced=False)
_DECAY = {1: _PER_DAY, 2: _PER_SECOND}

#: (table, column name) -> {selector value: Unit}. A column absent from this registry,
#: or a selector absent from its mapping, raises.
_REGISTRY: dict[tuple[TableKind, str], dict[int, Unit]] = {
    # --- diffuser: selectors map 1:1 to columns ---
    (TableKind.DIFFUSER, "port_diameter"): _LENGTH_INFERRED,
    (TableKind.DIFFUSER, "port_elevation"): _LENGTH_INFERRED,
    (TableKind.DIFFUSER, "vertical_angle"): _ANGLE_ONLY,
    (TableKind.DIFFUSER, "horizontal_angle"): _ANGLE_ONLY,
    (TableKind.DIFFUSER, "n_ports"): _COUNT_ONLY,
    (TableKind.DIFFUSER, "port_spacing"): _LENGTH_EVIDENCED,
    (TableKind.DIFFUSER, "port_depth"): _LENGTH_INFERRED,
    (TableKind.DIFFUSER, "x_position"): _LENGTH_INFERRED,
    (TableKind.DIFFUSER, "y_position"): _LENGTH_INFERRED,
    # --- effluent ---
    # The manual (section 5.2.3) documents the dropdown as MGD / cms / cfs, in that
    # order, which matches the evidenced 1 -> MGD and 2 -> cms. cfs is therefore very
    # likely 3, but no file uses it, so it stays unevidenced.
    (TableKind.EFFLUENT, "flow"): {
        1: Unit("MGD", MGD_TO_CUBIC_METRES_PER_SECOND, evidenced=True),
        2: Unit("m3/s", 1.0, evidenced=True),
        3: Unit("ft3/s", CUBIC_FEET_TO_CUBIC_METRES, evidenced=False),
    },
    (TableKind.EFFLUENT, "salinity"): {1: Unit("psu", 1.0, evidenced=True)},
    (TableKind.EFFLUENT, "temperature"): _TEMPERATURE,
    # kg/kg is a mass fraction, so selector 2 needs the *effluent* density supplied.
    (TableKind.EFFLUENT, "pollutant"): _CONCENTRATION,
    # --- mixing zone ---
    (TableKind.MIXING_ZONE, "acute_distance"): _LENGTH_EVIDENCED,
    (TableKind.MIXING_ZONE, "chronic_distance"): _LENGTH_EVIDENCED,
    # --- ambient ---
    (TableKind.AMBIENT, "depth"): _LENGTH_INFERRED,
    (TableKind.AMBIENT, "current_speed"): _VELOCITY,
    (TableKind.AMBIENT, "current_direction"): _ANGLE_ONLY,
    (TableKind.AMBIENT, "salinity"): {1: Unit("psu", 1.0, evidenced=True)},
    (TableKind.AMBIENT, "temperature"): _TEMPERATURE,
    (TableKind.AMBIENT, "background_pollutant"): _CONCENTRATION,
    (TableKind.AMBIENT, "decay_rate"): _DECAY,
    (TableKind.AMBIENT, "farfield_speed"): _VELOCITY,
    (TableKind.AMBIENT, "farfield_direction"): _ANGLE_ONLY,
    (TableKind.AMBIENT, "dispersion_alpha"): {1: Unit("m^0.67/s^2", 1.0, evidenced=True)},
}


def selector_for_column(kind: TableKind, selectors: list[int], column_index: int) -> int:
    """The unit selector governing `column_index` of `kind`.

    Accounts for the leading selector that effluent, mixing-zone and ambient blocks
    carry and the diffuser does not.
    """
    offset = 1 if kind in _OFFSET_TABLES else 0
    index = column_index + offset
    if not 0 <= index < len(selectors):
        raise UnknownUnitFlagError(
            f"{kind.name}: column {column_index} maps to selector index {index}, "
            f"but only {len(selectors)} selectors were supplied"
        )
    return selectors[index]


def unit_for(kind: TableKind, column: str, flag: int) -> Unit:
    """Look up the unit a selector denotes, or raise."""
    try:
        options = _REGISTRY[(kind, column)]
    except KeyError:
        raise UnknownUnitFlagError(
            f"no unit registry for {kind.name}.{column}; refusing to guess"
        ) from None
    try:
        return options[flag]
    except KeyError:
        known = ", ".join(
            f"{value}={unit.name or 'dimensionless'}" for value, unit in options.items()
        )
        raise UnknownUnitFlagError(
            f"{kind.name}.{column}: unit selector {flag} is not established "
            f"(known: {known}). Refusing to guess -- selectors silently rescale "
            f"physical inputs, so a wrong guess would produce plausible wrong answers. "
            f"If you know what {flag} means here, add it to plumes2.units."
        ) from None


def evidenced_options(kind: TableKind, column: str) -> dict[int, Unit]:
    """The selectors for a column whose meaning a reference case actually demonstrates.

    Writers should restrict themselves to these: emitting a selector whose meaning we
    only *infer* risks the exe reading the file differently than we wrote it.
    """
    return {
        flag: unit for flag, unit in _REGISTRY.get((kind, column), {}).items() if unit.evidenced
    }


def convert_to_si(
    kind: TableKind, column: str, flag: int, value: float, *, density: float | None = None
) -> float:
    """Convert one stored value to SI using its selector.

    `density` (kg/m3) is required only by mass-fraction units, and only the pollutant
    columns can select one. Supply the *effluent* density for an effluent column and the
    ambient density for an ambient one.
    """
    return unit_for(kind, column, flag).to_si_value(value, density=density)


def convert_row_to_si(
    kind: TableKind, selectors: list[int], row: list[float], *, density: float | None = None
) -> list[float]:
    """Convert a whole data row to SI, column by column."""
    columns = kind.column_names
    if len(row) != len(columns):
        raise UnknownUnitFlagError(f"{kind.name}: expected {len(columns)} values, got {len(row)}")
    return [
        convert_to_si(
            kind, column, selector_for_column(kind, selectors, index), value, density=density
        )
        for index, (column, value) in enumerate(zip(columns, row, strict=True))
    ]


def describe(kind: TableKind, selectors: list[int]) -> dict[str, str]:
    """Map each column of `kind` to the unit its selector names.

    Useful for reporting what a project file actually means, and for spotting an
    unevidenced assumption before trusting a converted value.
    """
    described: dict[str, str] = {}
    for index, column in enumerate(kind.column_names):
        flag = selector_for_column(kind, selectors, index)
        unit = unit_for(kind, column, flag)
        described[column] = unit.name or "dimensionless"
    return described
