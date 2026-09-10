"""Display units: converting output on the way out, and never on the way in.

`units.py` is the input half of this -- it resolves the `.prj`'s per-column selectors into SI
before anything physical happens. This is the mirror image, and the asymmetry is deliberate:

    the solver is SI, always. A plot that converts is fine; a model that converts is a bug
    waiting to happen.

So nothing here is reachable from the integrator. A conversion happens once, at the boundary
where a number becomes something a person reads, and the converted frame is a *copy*.

**The unit travels in the column name**, exactly as it does in SI output: `depth_m` becomes
`depth_ft`, `temperature_degC` becomes `temperature_degF`. That is the same contract the tidy
CSV already makes -- a reader never has to look a unit up, and two frames in different systems
cannot be confused for each other or silently concatenated.

⚠️ **Every column must declare a dimension.** A column this module has never heard of raises
rather than passing through untouched, because a frame that is 'mostly converted' is worse than
one that is not converted at all: the names would disagree with the values in a way nothing
downstream could detect. Adding an output column therefore means adding one line here, which is
the point -- it is what keeps the units in the names honest.

⚠️ **Concentrations stay in SI.** mg/L was asked for and declined (PLAN.md §6b), which also
sidesteps the exe's own µmol/kg → µmol/L slip: it converts the effluent endmember by density and
the ambient not at all (PLAN.md §7.5). Offering mg/L here would mean picking a side in a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import overload

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from plumes2.units import (
    CUBIC_FEET_TO_CUBIC_METRES,
    FAHRENHEIT_OFFSET,
    FAHRENHEIT_SCALE,
    FEET_TO_METRES,
    MGD_TO_CUBIC_METRES_PER_SECOND,
)

__all__ = [
    "SI",
    "SYSTEMS",
    "US",
    "DisplayUnit",
    "UndeclaredColumnError",
    "UnitSystem",
    "convert_frame",
]


class UndeclaredColumnError(KeyError):
    """Raised for a column whose dimension is not declared in `_DIMENSIONS`.

    Deliberately fatal -- see the module docstring. One line of registration is the price of a
    frame whose names and values are guaranteed to agree.
    """


@dataclass(frozen=True, slots=True)
class DisplayUnit:
    """One unit a quantity can be displayed in, and how to reach it *from* SI.

    `from_si` and `offset` are the inverse of `units.Unit`'s pair and are derived from the same
    constants rather than restated, so the two directions cannot drift apart.
    """

    #: The suffix that replaces the SI one in a column name: `m` -> `ft`.
    suffix: str
    #: A displayed value is `si * from_si + offset`.
    from_si: float = 1.0
    offset: float = 0.0
    #: How the unit is written on an axis label, where the identifier-safe suffix reads badly:
    #: `m_s` is a fine column name and a poor axis. Falls back to the suffix.
    #:
    #: ⚠️ **This may carry non-ASCII** -- `°C` -- because it is for HTML and figures, never for
    #: the CLI, whose cp1252 constraint `plumes2.cli` documents. `suffix` stays ASCII.
    axis_label: str | None = None

    @overload
    def __call__(self, si: float) -> float: ...
    @overload
    def __call__(self, si: NDArray[np.float64]) -> NDArray[np.float64]: ...
    def __call__(self, si: float | NDArray[np.float64]) -> float | NDArray[np.float64]:
        """Convert one value, or a whole array of them, out of SI.

        Overloaded rather than widened so a scalar in gives a scalar out: a report labelling an
        axis with a single endpoint should not have to unwrap a zero-dimensional array.
        """
        return si * self.from_si + self.offset

    @property
    def label(self) -> str:
        """What to print on an axis. Empty for a dimensionless quantity."""
        return self.suffix if self.axis_label is None else self.axis_label


METRE = DisplayUnit("m")
FOOT = DisplayUnit("ft", 1.0 / FEET_TO_METRES)

METRES_PER_SECOND = DisplayUnit("m_s", axis_label="m/s")
FEET_PER_SECOND = DisplayUnit("ft_s", 1.0 / FEET_TO_METRES, axis_label="ft/s")

CELSIUS = DisplayUnit("degC", axis_label="\N{DEGREE SIGN}C")
#: degF = degC * 9/5 + 32, written as the exact inverse of the input-side pair.
FAHRENHEIT = DisplayUnit(
    "degF",
    1.0 / FAHRENHEIT_SCALE,
    -FAHRENHEIT_OFFSET / FAHRENHEIT_SCALE,
    axis_label="\N{DEGREE SIGN}F",
)

CUBIC_METRES_PER_SECOND = DisplayUnit("m3_s", axis_label="m\N{SUPERSCRIPT THREE}/s")
MGD = DisplayUnit("MGD", 1.0 / MGD_TO_CUBIC_METRES_PER_SECOND)
CUBIC_FEET_PER_SECOND = DisplayUnit(
    "ft3_s", 1.0 / CUBIC_FEET_TO_CUBIC_METRES, axis_label="ft\N{SUPERSCRIPT THREE}/s"
)


@dataclass(frozen=True, slots=True)
class UnitSystem:
    """The display unit chosen for each dimension the outputs carry.

    Only the four dimensions that were actually asked for are switchable. Density, time and the
    chemistry columns have one representation each and are listed in `_DIMENSIONS` as such --
    when a second is wanted, it becomes a field here and a preset below, not a special case at
    the call site.
    """

    name: str
    length: DisplayUnit
    speed: DisplayUnit
    temperature: DisplayUnit
    flow: DisplayUnit

    def unit_for(self, dimension: str) -> DisplayUnit:
        """The unit this system uses for `dimension`, or the fixed one where there is no choice."""
        switchable = {
            "length": self.length,
            "speed": self.speed,
            "temperature": self.temperature,
            "flow": self.flow,
        }
        return switchable.get(dimension) or _FIXED[dimension]


SI = UnitSystem(
    name="SI",
    length=METRE,
    speed=METRES_PER_SECOND,
    temperature=CELSIUS,
    flow=CUBIC_METRES_PER_SECOND,
)

#: ⚠️ Not a complete imperial system, and it does not pretend to be. Length, temperature and
#: flow are what a US permit is written in; density stays kg/m3 and the chemistry stays molal,
#: because nobody asked for slugs per cubic foot and inventing one would be busywork with a
#: rounding error attached.
US = UnitSystem(
    name="US",
    length=FOOT,
    speed=FEET_PER_SECOND,
    temperature=FAHRENHEIT,
    flow=MGD,
)

#: Selectable by name, for a CLI flag or a report parameter.
SYSTEMS: dict[str, UnitSystem] = {"SI": SI, "US": US}

#: Dimensions with exactly one representation, so no system can disagree about them.
_FIXED: dict[str, DisplayUnit] = {
    # Seconds and hours are already what the outputs use, and both read fine anywhere.
    "time_s": DisplayUnit("s"),
    "time_hr": DisplayUnit("hr"),
    # See the module docstring: kg/m3 and the molal chemistry are not switchable.
    "density": DisplayUnit("kg_m3", axis_label="kg/m\N{SUPERSCRIPT THREE}"),
    "concentration_molal": DisplayUnit("umol_kg", axis_label="\N{MICRO SIGN}mol/kg"),
    "pressure_uatm": DisplayUnit("uatm", axis_label="\N{MICRO SIGN}atm"),
    "concentration_mass": DisplayUnit("mg_l", axis_label="mg/L"),
    # Ratios, counts and flags: nothing to convert, and no suffix to rewrite.
    "dimensionless": DisplayUnit(""),
}

#: Every column any output frame can carry -> its dimension. Keyed on the full name rather than
#: parsed from the suffix, because `_m` is a suffix and `_m_s` is a different one, and a parser
#: that got that wrong would convert a speed as a length. An unknown name raises.
_DIMENSIONS: dict[str, str] = {
    # --- near field ---
    "time_s": "time_s",
    "dilution": "dimensionless",
    "centreline_dilution": "dimensionless",
    "peak_to_mean": "dimensionless",
    "merged": "dimensionless",
    "plume_diameter_m": "length",
    "depth_m": "length",
    "x_m": "length",
    "y_m": "length",
    "speed_m_s": "speed",
    "salinity_psu": "dimensionless",  # practical salinity is already a ratio
    "temperature_degC": "temperature",
    "density_kg_m3": "density",
    # --- chemistry ---
    "total_alkalinity_umol_kg": "concentration_molal",
    "dic_umol_kg": "concentration_molal",
    "ph_total": "dimensionless",
    "pco2_uatm": "pressure_uatm",
    "carbonate_umol_kg": "concentration_molal",
    "bicarbonate_umol_kg": "concentration_molal",
    "omega_calcite": "dimensionless",
    "omega_aragonite": "dimensionless",
    "omega_brucite": "dimensionless",
    "omega_brucite_phreeqc": "dimensionless",
    "ph_total_phreeqc": "dimensionless",
    "pco2_uatm_phreeqc": "pressure_uatm",
    "carbonate_umol_kg_phreeqc": "concentration_molal",
    "bicarbonate_umol_kg_phreeqc": "concentration_molal",
    "omega_calcite_phreeqc": "dimensionless",
    "omega_aragonite_phreeqc": "dimensionless",
    # --- dissolved oxygen ---
    # mg/L, and *not* switchable: it is the unit the exe prints and the unit a DO standard is
    # written in, so there is no second representation to offer.
    "dissolved_oxygen_mg_l": "concentration_mass",
    # --- far field ---
    "distance_m": "length",
    "width_m": "length",
    "dilution_factor": "dimensionless",
    "travel_time_hr": "time_hr",
    # --- the exe's own columns, when a frame came from a `.dat` (`plumes2.plotframe`) ---
    # They sit beside ours rather than replacing them, so a panel can show both, and all three
    # are dimensionless -- which is why an exe frame needs no unit handling of its own.
    "ph_exe": "dimensionless",
    "omega_calcite_exe": "dimensionless",
    "omega_aragonite_exe": "dimensionless",
}


def _renamed(column: str, si: DisplayUnit, display: DisplayUnit) -> str:
    """`depth_m` -> `depth_ft`, leaving a dimensionless name alone.

    Only the trailing SI suffix is replaced, so `travel_time_hr` keeps its `time` and
    `total_alkalinity_umol_kg` is not mangled by a substring match somewhere in the middle.
    """
    if not si.suffix or si.suffix == display.suffix:
        return column
    tail = f"_{si.suffix}"
    if not column.endswith(tail):
        raise UndeclaredColumnError(
            f"{column!r} is registered as carrying {si.suffix!r} but does not end in {tail!r}; "
            "plumes2.display._DIMENSIONS and the column name disagree"
        )
    return f"{column[: -len(tail)]}_{display.suffix}"


def convert_frame(frame: pd.DataFrame, system: UnitSystem | str) -> pd.DataFrame:
    """A copy of `frame` in `system`, with every column renamed to its new unit.

    `system` may be a `UnitSystem` or one of the names in `SYSTEMS`. Converting to `SI` is a
    well-defined no-op that still returns a copy, so a report can run one code path for both.

    Raises `UndeclaredColumnError` for any column not in `_DIMENSIONS` -- including a
    *previously converted* one, since `depth_ft` is not a registered SI column. Round-tripping is
    not supported by design: SI is the only source of truth, and a frame that has left it is for
    reading, not for computing on.
    """
    resolved = SYSTEMS[system] if isinstance(system, str) else system
    unknown = [name for name in frame.columns if name not in _DIMENSIONS]
    if unknown:
        raise UndeclaredColumnError(
            f"no display dimension declared for {unknown}. Add each to "
            "plumes2.display._DIMENSIONS -- a partly converted frame would have names that "
            "disagree with its values, which nothing downstream could detect."
        )

    converted = {}
    for name in frame.columns:
        dimension = _DIMENSIONS[name]
        si_unit = SI.unit_for(dimension)
        display = resolved.unit_for(dimension)
        column = frame[name]
        # Flags and ratios are copied untouched: multiplying a bool by 1.0 would silently
        # retype the column, and the report's merge flag has to stay a flag.
        if display is si_unit or dimension == "dimensionless":
            converted[_renamed(name, si_unit, display)] = column.copy()
        else:
            converted[_renamed(name, si_unit, display)] = column * display.from_si + display.offset
    return pd.DataFrame(converted, index=frame.index.copy())
