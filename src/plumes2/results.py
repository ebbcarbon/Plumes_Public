"""Running a case, and writing results worth reading.

This is Phase 6 track B: the outputs the port exists to produce. The exe's `.dat` is a
fixed-width Fortran listing built for a line printer — three decimals on everything, columns
picked by a GUI checkbox, no units on the values, no record of what produced it, and inputs
rounded past recovery. Reproducing it byte for byte is worth doing, because it is how someone
who knows PLUMES2.0 can check us; it is not worth *using*.

So a run writes a directory:

    nearfield.csv     one row per sample, full precision, units in every column name
    provenance.yaml   what code ran, from what input, when -- see `plumes2.provenance`
    case.yaml         the complete resolved input, chemistry included

`pd.read_csv("nearfield.csv")` then gives typed columns needing no post-processing, and the
directory says what produced it without anyone having to remember.

⚠️ **Sampling is on time, and that is a choice.** The exe prints rows chosen by its step
controller — a 2 % mass-growth target — so its row *numbers* mean something to it and nothing
to anyone else. We integrate continuously and sample where asked. Comparing to a trace means
sampling at the trace's own printed `Time`, which is what the validation suite does; producing
output for a human means an even grid. The two are the same trajectory.

⚠️ **The near field ends before the integration does.** `integrate` deliberately runs past the
termination benchmark so the turning points can be counted (see `terminate.py`), so results are
truncated at `solution.end_time`. A row beyond it is not near-field output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from plumes2.ambient import AmbientProfileView
from plumes2.biochem.do_bod import near_field_oxygen_for
from plumes2.chem.constants import resolve_constants, solubility_brucite
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.chem.transport import effluent_endmember, plume_carbonate
from plumes2.config import Case
from plumes2.crossplume import centreline_dilution, peak_to_mean
from plumes2.farfield.brooks import BrooksParameters
from plumes2.io.yaml_case import dump_case
from plumes2.nearfield.solver import NearFieldSolution, integrate
from plumes2.provenance import Provenance, provenance

__all__ = [
    "CHEMISTRY_COLUMNS",
    "FARFIELD_COLUMNS",
    "NEARFIELD_COLUMNS",
    "OXYGEN_COLUMNS",
    "Results",
    "mixing_zone_values",
    "run",
    "sample_at_distance",
    "write_results",
]

#: Output column name -> what it is. The names carry their units so a reader never has to
#: look them up, and the order is fixed so diffing two runs lines up.
NEARFIELD_COLUMNS: dict[str, str] = {
    "time_s": "seconds since discharge",
    "dilution": "flux-averaged, the exe's `Dilutn`",
    # ⚠️ The pair matters: a mixing-zone limit is quoted against the worst place in the
    # cross-section, which is the centreline, while the flux average is what the solver carries.
    "centreline_dilution": "the exe's `CL-Dil`: flux-averaged over the peak-to-mean, floored at 1",
    "peak_to_mean": (
        "centreline over mean concentration under near_field.similarity_profile"
        " -- parabolic: 2 round, 1.5 merged slab"
    ),
    "merged": "whether neighbouring plumes overlap here",
    "plume_diameter_m": "2b, the merged vertical extent where merging applies",
    "depth_m": "below the surface, positive down",
    # The model's own frame, not a compass: the case's directions are angles counter-clockwise
    # from +x (the manual's convention), and nothing says which way +x points on the site.
    "x_m": "along the model's x axis from the port (the frame the angles are measured in)",
    "y_m": "along the model's y axis from the port",
    "speed_m_s": "plume element speed",
    "salinity_psu": "plume, practical salinity",
    "temperature_degC": "plume",
    "density_kg_m3": "plume, under near_field.equation_of_state, plus the excess_density tracer",
}

#: Appended when the case carries carbonate chemistry. TA and DIC mix conservatively and are
#: re-solved into everything else at every sample -- see `chem/transport.py`.
CHEMISTRY_COLUMNS: dict[str, str] = {
    "total_alkalinity_umol_kg": "conservative with mixing",
    "dic_umol_kg": "conservative with mixing",
    "ph_total": "total scale, which is what the exe reports on its default constants",
    "pco2_uatm": "partial pressure of CO2",
    "carbonate_umol_kg": "[CO3--]",
    "bicarbonate_umol_kg": "[HCO3-]",
    "omega_calcite": "[Ca2+][CO3--] / Ksp_calcite",
    "omega_aragonite": "[Ca2+][CO3--] / Ksp_aragonite",
    # ⭐ The column the exe cannot produce, and the reason this project exists -- see
    # PLAN.md §8b. An *upper bound*: ion pairing is not modelled.
    "omega_brucite": "[Mg2+][OH-]^2 / Ksp*, an upper bound (no ion pairing) -- PLAN.md 8b",
}

#: Appended when the case carries dissolved oxygen. One column, because DO is the only quantity
#: the module produces in the near field -- the BOD channels are provably inert there, so carrying
#: them would be columns of constants. See `biochem/do_bod.py`.
OXYGEN_COLUMNS: dict[str, str] = {
    "dissolved_oxygen_mg_l": "plume DO, from the path-integrated ambient -- biochem/do_bod.py",
}

#: The Brooks far field, once the plume has stopped rising and is spreading downstream.
#: When the case carries carbonate chemistry the frame also gets `CHEMISTRY_COLUMNS`, mixed
#: from the near-field endpoint toward the ambient at the trapping depth and re-solved --
#: see `_farfield_chemistry`. Before 2026-08-24 the far field carried no chemistry at all,
#: which meant pH and Omega could not be read at a chronic mixing zone that sits past the
#: transition -- which is nearly all of them (case03's is 207 m against a ~3 m transition).
FARFIELD_COLUMNS: dict[str, str] = {
    "distance_m": "from the diffuser, along the far-field current",
    "width_m": "wastefield width",
    "dilution": "total: the near-field value times the Brooks factor",
    "dilution_factor": "Brooks alone, 1 at the transition",
    "travel_time_hr": "from the transition, at the far-field current speed",
}


@dataclass(frozen=True, slots=True)
class Results:
    """A completed run: the inputs, the trajectory, and what produced them."""

    case: Case
    provenance: Provenance
    #: Near-field trajectory, one row per sample, truncated at the termination benchmark.
    nearfield: pd.DataFrame
    #: Whether the chemistry columns are present.
    has_chemistry: bool
    #: Whether the dissolved-oxygen column is present.
    has_oxygen: bool
    #: Brooks far field, or `None` when the case disables it or the current is zero.
    farfield: pd.DataFrame | None
    #: Why the near field ended, and when -- see `terminate.TerminationReason`.
    termination: str
    end_time: float
    #: The raw solution, for anyone who wants to resample or inspect the events.
    solution: NearFieldSolution

    @property
    def final_dilution(self) -> float:
        """Dilution at the end of the near field, which is what feeds the far field."""
        return float(self.nearfield["dilution"].iloc[-1])


def run(case: Case, *, samples: int = 200, source: str | Path | None = None) -> Results:
    """Integrate `case` and sample the near field on an even time grid.

    `samples` sets the output resolution only -- it does not touch the integration, which is
    adaptive and independent of it. Sampling evenly in *time* rather than reproducing the
    exe's step controller is deliberate: see the module docstring.
    """
    if samples < 2:
        raise ValueError("need at least two samples to describe a trajectory")

    # ⚠️ Re-checked here, not only in the `Case` validator: `model_copy` does not re-run
    # validators, and building a variant that way is this codebase's normal idiom. This is the
    # moment a number is produced, whatever route the case took.
    case.warn_if_outside_the_modelled_regime()

    solution = integrate(case)
    last = float(solution.solution.t[-1])  # type: ignore[attr-defined]
    end = min(solution.end_time, last)
    times = np.linspace(0.0, end, samples)
    trajectory = solution.sample(times)

    # The profile is a post-processing step over the trajectory, not part of the integration:
    # the solver carries flux-averaged quantities and the centreline follows from the geometry
    # and the case's declared similarity profile (the exe's default, unless a run says otherwise).
    peak = peak_to_mean(
        trajectory.diameter,
        case.diffuser.port_spacing,
        trajectory.merged,
        profile=case.near_field.similarity_profile,
    )

    frame = pd.DataFrame(
        {
            "time_s": trajectory.time,
            "dilution": trajectory.dilution,
            "centreline_dilution": centreline_dilution(trajectory.dilution, peak),
            "peak_to_mean": peak,
            "merged": trajectory.merged,
            "plume_diameter_m": trajectory.diameter,
            # `z` is elevation, negative down; depth is the friendlier way round and is what
            # the exe's own `Depth` column means despite its sign.
            "depth_m": -trajectory.z,
            "x_m": trajectory.x,
            "y_m": trajectory.y,
            "speed_m_s": trajectory.speed,
            "salinity_psu": trajectory.salinity,
            "temperature_degC": trajectory.temperature,
            "density_kg_m3": trajectory.plume_density,
        }
    )
    assert list(frame.columns) == list(NEARFIELD_COLUMNS), "column order is part of the format"

    chemistry = _chemistry(case, trajectory)
    if chemistry is not None:
        frame = pd.concat([frame, chemistry], axis=1)

    oxygen = _oxygen(case, solution, times)
    if oxygen is not None:
        frame = pd.concat([frame, oxygen], axis=1)

    return Results(
        case=case,
        provenance=provenance(case, source=source),
        nearfield=frame,
        has_chemistry=chemistry is not None,
        has_oxygen=oxygen is not None,
        farfield=_farfield(case, frame),
        termination=solution.reason,
        end_time=end,
        solution=solution,
    )


def _chemistry(case: Case, trajectory) -> pd.DataFrame | None:  # type: ignore[no-untyped-def]
    """Carbonate chemistry along the trajectory, or `None` when the case carries none.

    TA and DIC mix conservatively; everything else is re-solved from the mixed pair at every
    sample, which is what `chem/transport.py` establishes against case03 and case04.
    """
    if case.effluent_chemistry is None or not case.ambient.has_chemistry:
        return None

    view = AmbientProfileView(case.ambient)
    depth = -trajectory.z
    constants = resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
    endmember = effluent_endmember(
        case.effluent_chemistry,
        case.effluent.salinity,
        case.effluent.temperature,
        settings=case.carbonate,
        constants=constants,
    )
    state = plume_carbonate(
        endmember,
        view.total_alkalinity(depth),
        view.dic(depth),
        trajectory.dilution,
        trajectory.salinity,
        trajectory.temperature,
        constants=constants,
    )
    brucite = state.omega_brucite(solubility_brucite(state.salinity, state.temperature))
    frame = pd.DataFrame(
        {
            "total_alkalinity_umol_kg": state.total_alkalinity,
            "dic_umol_kg": state.dic,
            "ph_total": state.ph_total,
            "pco2_uatm": state.pco2,
            "carbonate_umol_kg": state.carbonate,
            "bicarbonate_umol_kg": state.bicarbonate,
            "omega_calcite": state.omega_calcite,
            "omega_aragonite": state.omega_aragonite,
            "omega_brucite": brucite,
        }
    )
    assert list(frame.columns) == list(CHEMISTRY_COLUMNS)
    return frame


#: How much finer than the output grid the DO path integral is evaluated on. The integral's
#: accuracy is its resolution, and a reported column should not depend on how many rows were asked
#: for -- so it is computed dense and interpolated down. Eight is ample and costs nothing.
_OXYGEN_REFINEMENT = 8


def _oxygen(case: Case, solution: NearFieldSolution, times) -> pd.DataFrame | None:  # type: ignore[no-untyped-def]
    """Plume DO along the trajectory, or `None` when the case carries no oxygen endmember.

    ⚠️ **Computed on a refined grid and interpolated down.** DO is a *path* integral over the
    entrained ambient (`biochem/do_bod.py`), so unlike every other column here its value at a
    sample depends on the samples before it. Evaluating it on the output grid would make a
    200-row run and a 20-row run disagree about the same plume.
    """
    if not case.oxygen_enabled:
        return None

    fine_count = (len(times) - 1) * _OXYGEN_REFINEMENT + 1
    dense = np.linspace(float(times[0]), float(times[-1]), fine_count)
    fine = solution.sample(dense)
    oxygen = near_field_oxygen_for(case, fine.dilution, -fine.z)
    frame = pd.DataFrame({"dissolved_oxygen_mg_l": np.interp(times, dense, oxygen)})
    assert list(frame.columns) == list(OXYGEN_COLUMNS)
    return frame


def _farfield(case: Case, nearfield: pd.DataFrame) -> pd.DataFrame | None:
    """Brooks downstream of the near-field endpoint, or `None` when it does not apply.

    The near field hands over three things: its final dilution, the plume diameter that sets
    the wastefield width, and the distance at which it stopped. Brooks then takes over as a
    1-D spreading problem, so `x` in its equations is measured **from the transition**, not
    from the diffuser -- while the reported `distance_m` is from the diffuser, which is what a
    mixing-zone limit is quoted against. The exe agrees: case02's far-field table opens at
    2.896 m with a dilution factor of 1.

    ⚠️ **The far field has its own current.** The ambient table carries `Far-spd` separately
    from the near-field current, and they differ across the archive. Using the near-field
    value would rescale `beta` and with it every dilution downstream.

    The grid follows the case's own `interval` and `max_distance`, and stops early if the
    dilution ceiling is reached. ⚠️ It is *not* the exe's grid row-for-row -- case02 ends on a
    1.611 m partial step whose origin is undecoded. Matching that belongs to the byte-exact
    writer (track A), not here, where a clean even grid is more useful.
    """
    if not case.far_field.enabled:
        return None

    view = AmbientProfileView(case.ambient)
    final = nearfield.iloc[-1]
    ambient = view.sample(float(final["depth_m"]))
    if ambient.farfield_speed <= 0.0:
        # Brooks divides by the current: with no advection there is no downstream axis at
        # all, and the exe declines to run it either.
        return None

    transition = float(np.hypot(final["x_m"], final["y_m"]))
    settings = case.far_field
    parameters = BrooksParameters(
        initial_width=case.wastefield_width(float(final["plume_diameter_m"])),
        initial_dilution=float(final["dilution"]),
        current_speed=ambient.farfield_speed,
        alpha=ambient.dispersion_alpha,
        law=settings.law,
        decay_per_day=ambient.decay_rate,
    )

    span = max(settings.max_distance - transition, settings.interval)
    downstream = np.arange(0.0, span + settings.interval, settings.interval)
    frame = pd.DataFrame(
        {
            "distance_m": transition + downstream,
            "width_m": parameters.width(downstream),
            "dilution": parameters.total_dilution(downstream),
            "dilution_factor": parameters.dilution_factor(downstream),
            "travel_time_hr": parameters.travel_time(downstream) / 3600.0,
        }
    )
    assert list(frame.columns) == list(FARFIELD_COLUMNS)
    # The exe stops at its dilution ceiling; keep the first row that reaches it so the
    # crossing is visible rather than implied.
    reached = frame.index[frame["dilution"] >= settings.max_dilution]
    if len(reached):
        frame = frame.loc[: reached[0]]

    chemistry = _farfield_chemistry(case, final, frame)
    if chemistry is not None:
        frame = pd.concat([frame, chemistry], axis=1)
    return frame


def _farfield_chemistry(case: Case, final, frame: pd.DataFrame) -> pd.DataFrame | None:  # type: ignore[no-untyped-def]
    """Carbonate chemistry along the far field, or `None` when the case carries none.

    The construction is the exe's own, decoded in two places: the far field entrains ambient
    from the **trapping depth** -- its printed TA asymptotes to the ambient there, not to a
    depth mean (ledger row 56) -- and every conservative quantity therefore relaxes from the
    near-field endpoint toward that ambient with the Brooks spreading factor:

        value(D) = ambient + (endpoint - ambient) / (D / D_transition)

    which is exact conservative mixing of `D_t` parts endpoint water with `D - D_t` parts
    trapping-depth ambient. TA, DIC, salinity and temperature all mix this way; pH and the
    saturation states are then **re-solved** from the mixed pair, exactly as the near field
    does (`chem/transport.py`). At the transition row the spreading factor is 1, so the far
    field's first chemistry row equals the near field's last **by construction** -- pinned by
    a test, because a seam between the two tables would be read as physics.

    ⚠️ The same isolation caveat as the near field: this is our Brooks dilution feeding our
    speciation. The exe's far-field dilution runs from a virtual origin (row 256) that
    `farfield/brooks.py` deliberately does not reproduce, so a row-for-row chemistry
    comparison against a trace inherits that dilution gap; the *solver* is measured
    separately against the exe's own printed TA/DIC (row 43's far-field companion).
    """
    if case.effluent_chemistry is None or not case.ambient.has_chemistry:
        return None
    if "total_alkalinity_umol_kg" not in final.index:
        return None

    view = AmbientProfileView(case.ambient)
    depth = float(final["depth_m"])
    ambient = view.sample(depth)
    ambient_ta = float(view.total_alkalinity(depth))
    ambient_dic = float(view.dic(depth))

    spreading = frame["dilution_factor"].to_numpy(dtype=np.float64)

    def mixed(endpoint: float, background: float) -> np.ndarray:
        return background + (endpoint - background) / spreading

    total_alkalinity = mixed(float(final["total_alkalinity_umol_kg"]), ambient_ta)
    dic = mixed(float(final["dic_umol_kg"]), ambient_dic)
    salinity = mixed(float(final["salinity_psu"]), ambient.salinity)
    temperature = mixed(float(final["temperature_degC"]), ambient.temperature)

    constants = resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
    state = solve_from_alkalinity_dic(
        total_alkalinity,
        dic,
        salinity,
        temperature,
        constants=constants,
        context="far-field plume",
    )
    brucite = state.omega_brucite(solubility_brucite(state.salinity, state.temperature))
    chemistry = pd.DataFrame(
        {
            "total_alkalinity_umol_kg": state.total_alkalinity,
            "dic_umol_kg": state.dic,
            "ph_total": state.ph_total,
            "pco2_uatm": state.pco2,
            "carbonate_umol_kg": state.carbonate,
            "bicarbonate_umol_kg": state.bicarbonate,
            "omega_calcite": state.omega_calcite,
            "omega_aragonite": state.omega_aragonite,
            "omega_brucite": brucite,
        },
        index=frame.index,
    )
    assert list(chemistry.columns) == list(CHEMISTRY_COLUMNS)
    return chemistry


def sample_at_distance(results: Results, distance_m: float) -> pd.Series:
    """Every reportable column at a horizontal distance from the diffuser, interpolated.

    Returns a Series carrying `region` (`"nearfield"`, `"farfield"`, or `"beyond"`),
    `distance_m`, and every numeric column the region's table holds, linearly interpolated
    at `distance_m`. `"beyond"` means the tables end before the asked distance -- the far
    field stopped on its dilution ceiling, was disabled, or has no current to advect it --
    and every value is NaN rather than an extrapolation.

    ⚠️ The near field's distance axis is `hypot(x, y)`, the straight-line distance the far
    field also starts from (ledger row 29). It is made monotone with a running maximum before
    interpolating, which is exact wherever the trajectory does not double back on itself.
    """
    near = results.nearfield
    far = results.farfield

    if far is not None and len(far) and distance_m >= float(far["distance_m"].iloc[0]):
        if distance_m <= float(far["distance_m"].iloc[-1]):
            axis = far["distance_m"].to_numpy(dtype=np.float64)
            values = {
                column: float(np.interp(distance_m, axis, far[column].to_numpy(np.float64)))
                for column in far.columns
                if column != "distance_m"
            }
            return pd.Series({"region": "farfield", "distance_m": distance_m, **values})
        return pd.Series({"region": "beyond", "distance_m": distance_m})

    axis = np.hypot(near["x_m"].to_numpy(np.float64), near["y_m"].to_numpy(np.float64))
    axis = np.maximum.accumulate(axis)
    if len(axis) and distance_m <= float(axis[-1]):
        numeric = near.select_dtypes(include=[np.number])
        values = {
            column: float(np.interp(distance_m, axis, numeric[column].to_numpy(np.float64)))
            for column in numeric.columns
        }
        return pd.Series({"region": "nearfield", "distance_m": distance_m, **values})
    return pd.Series({"region": "beyond", "distance_m": distance_m})


def mixing_zone_values(results: Results) -> pd.DataFrame:
    """The reportable columns at the case's own mixing-zone boundaries -- the study's quantity.

    One row per boundary (`acute`, `chronic`), each `sample_at_distance` at the distance the
    case declares. This is what a dose-response curve is a curve *of*: pH and Omega at the
    regulatory distances, not wherever the table happens to end. A boundary the tables do not
    reach comes back `region == "beyond"` with NaN values -- visibly missing rather than
    silently extrapolated (the same honesty rule as `ConstantRangeWarning`).
    """
    zone = results.case.mixing_zone
    rows = {
        "acute": sample_at_distance(results, zone.acute_distance),
        "chronic": sample_at_distance(results, zone.chronic_distance),
    }
    return pd.DataFrame(rows).T


def write_results(results: Results, directory: str | Path) -> Path:
    """Write `nearfield.csv`, `case.yaml` and `provenance.yaml` into `directory`.

    Full precision throughout: pandas' default `float_format` would round, and rounding is
    exactly what makes the exe's output unusable as an input to anything else.
    """
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)

    results.nearfield.to_csv(target / "nearfield.csv", index=False, lineterminator="\n")
    if results.farfield is not None:
        results.farfield.to_csv(target / "farfield.csv", index=False, lineterminator="\n")
    dump_case(results.case, target / "case.yaml")

    lines = [
        "# What produced the files in this directory.",
        "# Generated by plumes2 -- do not edit; regenerate the run instead.",
        *(f"{key}: {value!r}" for key, value in results.provenance.to_dict().items()),
        f"termination: {results.termination!r}",
        f"near_field_end_s: {results.end_time!r}",
        f"has_chemistry: {results.has_chemistry}",
        f"has_oxygen: {results.has_oxygen}",
        f"has_farfield: {results.farfield is not None}",
        "columns:",
        *(
            f"  {name}: {meaning!r}"
            for name, meaning in {
                **NEARFIELD_COLUMNS,
                **(CHEMISTRY_COLUMNS if results.has_chemistry else {}),
                **(OXYGEN_COLUMNS if results.has_oxygen else {}),
                **(FARFIELD_COLUMNS if results.farfield is not None else {}),
            }.items()
        ),
    ]
    (target / "provenance.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
