"""The neutral frame every figure is drawn from, and the two ways into it.

⭐ **A `.dat` written by the exe must be a valid input to the plotting layer.** That one
requirement is what this module exists to serve, and it is worth more than it looks: it means
every archived trace, and every run anyone has ever made in the GUI, can be plotted with our
outputs — including `Ω_brucite`, which the exe cannot produce at all. It also makes the figures
useful before the solver is trusted for a given case, because the exe's own numbers can drive
them.

What it forces on the design, and each of these is a *good* forcing:

1. **The plotting layer must not take `Results`.** It takes a `PlotFrame`, and there are two
   adapters into it — `from_results` and `from_dat`. Anything reaching into `Results` directly
   blocks the exe path, so nothing here may.
2. **An exe-column mapping**, in `_EXE_COLUMNS`, including the `Depth` sign flip and the two
   spellings of the dilution column across builds.
3. **Post-processing for the secondaries the exe never had.** Given TA and DIC plus salinity and
   temperature, `chem` re-solves the whole carbonate system per row — `pCO2`, carbonate,
   bicarbonate, and `Ω_brucite` — and the exe's own `OmegaA`/`OmegaC` come along beside ours,
   which doubles as a free check on our chemistry.

⚠️ **A `PlotFrame` carries its own caveats, and a figure must print them.** Three of them apply
to anything built from a `.dat` and to nothing built from a run, so they cannot live in the
plotting code or be remembered by a caller:

* **The `.dat` is rounded** to three decimals, so everything derived from it inherits that. A
  `pH` of 8.39 constrains `pCO2` only so far. A figure mixing the two sources must not imply
  equal quality.
* **The column set is a GUI choice.** An arbitrary `.dat` may lack salinity, temperature or the
  chemistry columns entirely — and the archive's chemistry traces lack *exactly* salinity and
  temperature, which is the pair the secondaries need. So `from_dat` names the missing column
  rather than emitting a half-filled frame, and takes an optional `case` to fill that gap
  honestly (see `derived`).
* **There is no provenance in a `.dat`** (PLAN.md §7b): no timestamp, no project name, no
  version. A figure from one can record the file it came from and must say exactly that, rather
  than implying the traceability our own runs carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from plumes2.ambient import AmbientProfileView
from plumes2.chem.constants import resolve_constants, solubility_brucite
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.chem.transport import mix
from plumes2.config import Case
from plumes2.crossplume import SimilarityProfile, centreline_dilution, peak_to_mean
from plumes2.io.dat import DatFile
from plumes2.results import CHEMISTRY_COLUMNS, Results

__all__ = [
    "EXE_CHEMISTRY_COLUMNS",
    "MissingColumnError",
    "PlotFrame",
    "from_dat",
    "from_results",
]

#: Exe column -> our neutral name. Both dilution spellings appear: 2026 builds print `Dilutn`,
#: the Dec-2025 build prints `Avg-Dil` for the same quantity (case00).
_EXE_COLUMNS: dict[str, str] = {
    "Dilutn": "dilution",
    "Avg-Dil": "dilution",
    "CL-Dil": "centreline_dilution",
    "P-dia": "plume_diameter_m",
    "x-posn": "x_m",
    "y-posn": "y_m",
    "P-Sal": "salinity_psu",
    "P-Temp": "temperature_degC",
    "P-Den": "density_kg_m3",
    "Time": "time_s",
    "TA": "total_alkalinity_umol_kg",
    "DIC": "dic_umol_kg",
    "pH": "ph_exe",
    "OmegaC": "omega_calcite_exe",
    "OmegaA": "omega_aragonite_exe",
    # The exe's own DO column, when the run had one (case24). Under our name, because unlike the
    # saturation states this is a quantity we compute the same way rather than differently -- the
    # comparison is a match, not a bounded disagreement.
    "DO": "dissolved_oxygen_mg_l",
}

#: `Depth` is the exception: the exe prints it negative-down under a positive-sounding name, so
#: it cannot go through the plain rename.
_EXE_DEPTH = "Depth"

#: The exe's own saturation states, kept beside ours rather than instead of them. Comparing the
#: two on one panel is a free check on our chemistry, which is why they are not overwritten.
EXE_CHEMISTRY_COLUMNS: tuple[str, ...] = ("ph_exe", "omega_calcite_exe", "omega_aragonite_exe")


class MissingColumnError(KeyError):
    """Raised when a `.dat` lacks a column something asked for depends on.

    Names the column and what it was needed for. Failing here is the point: a half-filled frame
    would put NaNs on a figure that a reader would take for data.
    """


@dataclass(frozen=True, slots=True)
class PlotFrame:
    """One trajectory, ready to draw, with everything a figure must state about it.

    The frame's column names are the tidy-CSV names -- `depth_m`, `dilution`,
    `plume_diameter_m` -- so a panel written against a run works unchanged against an exe trace.
    """

    frame: pd.DataFrame
    #: What this came from, in words, for the figure's footer. For a `.dat` it is the file and
    #: nothing more, because that is all a `.dat` carries.
    source: str
    #: `"run"` or `"dat"`. A figure overlaying both must not imply equal precision.
    origin: str
    #: Sentences a figure built on this frame is required to print. Never empty for a `.dat`.
    caveats: tuple[str, ...] = ()
    #: Columns computed rather than read -- from our chemistry, or from a supplied case. A
    #: reader has to be able to tell which numbers came out of the exe and which did not.
    derived: frozenset[str] = field(default_factory=frozenset)
    #: The case, when one is available. `None` for a bare `.dat`, which carries no inputs at all.
    case: Case | None = None
    #: The similarity profile the centreline and the gradient panel are drawn with. A run's is
    #: its case's; a `.dat`'s is whatever the caller declares, because the file does not say
    #: (case48: the selector is GUI session state) and the archive is the exe's default.
    profile: SimilarityProfile = SimilarityProfile.PARABOLIC

    @property
    def has_chemistry(self) -> bool:
        return "ph_total" in self.frame.columns

    @property
    def rounded(self) -> bool:
        """Whether the underlying numbers are the exe's three decimals."""
        return self.origin == "dat"


def from_results(results: Results) -> PlotFrame:
    """The adapter from our own runs. Full precision, full provenance, no caveats.

    The frame is a copy: a figure that adds a column must not reach back into the run.
    """
    stamp = results.provenance
    where = f" from {stamp.source}" if stamp.source else ""
    dirty = " (dirty tree)" if stamp.git_dirty else ""
    commit = f", commit {stamp.git_commit[:12]}{dirty}" if stamp.git_commit else ""
    return PlotFrame(
        frame=results.nearfield.copy(),
        source=(
            f"plumes2 {stamp.port_version}{where} at {stamp.generated_at}"
            f", case {stamp.case_digest[:12]}{commit}"
        ),
        origin="run",
        case=results.case,
        profile=results.case.near_field.similarity_profile,
    )


def _exe_frame(dat: DatFile) -> pd.DataFrame:
    """The near-field table under our column names, with `Depth` flipped."""
    table = dat.nearfield
    renamed = {
        neutral: table[exe].to_numpy(dtype=np.float64)
        for exe, neutral in _EXE_COLUMNS.items()
        if exe in table.columns
    }
    if _EXE_DEPTH in table.columns:
        # ⚠️ The exe's `Depth` is negative below the surface despite its name -- the same trap
        # `results.run` documents. Flipping here is what lets one panel read both sources.
        renamed["depth_m"] = -table[_EXE_DEPTH].to_numpy(dtype=np.float64)
    frame = pd.DataFrame(renamed)
    frame.index = table.index.copy()
    return frame


def _plume_salinity_and_temperature(
    case: Case, dilution: np.ndarray, depth: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Plume S and T from the case, for a `.dat` that did not print them.

    Both are conservative under mixing, so one part effluent to `D - 1` parts ambient at the row's
    own depth reproduces what the exe carried internally. This is the same arithmetic the solver
    advects -- see `chem/transport.mix` -- rather than a new model, but it is *derived*, and
    `PlotFrame.derived` says so on the figure.
    """
    view = AmbientProfileView(case.ambient)
    return (
        mix(case.effluent.salinity, view.salinity(depth), dilution),
        mix(case.effluent.temperature, view.temperature(depth), dilution),
    )


def _merge_flag(dat: DatFile, frame: pd.DataFrame) -> np.ndarray:
    """Which rows the exe considered merged, from its own banner.

    Read off the `merging happened` event rather than re-derived from the geometry, and that is the
    whole point of having the exe's file: the trigger uses an *effective* spacing that depends on
    the plume's instantaneous bearing, so inferring it would mean re-running the model to explain
    its own output. The banner is the exe's answer, already written down.

    **No banner means not merged**, and that is a fact rather than an absence. The exe prints the
    banner whenever it merges, so a trace without one did not merge over the trajectory it printed.
    An earlier revision returned `None` here and skipped the whole profile block, which cost every
    unmerged trace its centreline -- for no reason, since an unmerged plume's peak-to-mean is
    exactly 2.0 and needs no spacing at all.
    """
    step = next(
        (e.next_step for e in dat.events if "merg" in e.text.lower() and e.next_step is not None),
        None,
    )
    if step is None:
        return np.zeros(len(frame), dtype=bool)
    return np.asarray(frame.index.to_numpy() >= step, dtype=bool)


def _nominal_spacing(dat: DatFile) -> float:
    """Port spacing from the echoed diffuser table, or 0 when merging cannot apply.

    Nominal, because that is what the profile law uses (PLAN.md row 204). Zero for a single port,
    because one plume has no neighbour to be confined by however wide it grows -- which the
    archive's single-port merges confirm by holding a peak-to-mean of exactly 2.0 -- and zero again
    when the echo is missing, where `peak_to_mean` treats it the same way and returns the round
    value. Both cases are "no confinement", which is why they share an answer.
    """
    echo = dat.echoed_tables.get("Diffuser")
    if echo is None or echo.empty or "Spacing" not in echo.columns:
        return 0.0
    if "Ports" in echo.columns and int(float(echo["Ports"].iloc[0])) <= 1:
        return 0.0
    return float(echo["Spacing"].iloc[0])


def from_dat(
    dat: DatFile,
    source: str | Path,
    *,
    case: Case | None = None,
    secondaries: bool = True,
    profile: SimilarityProfile = SimilarityProfile.PARABOLIC,
) -> PlotFrame:
    """The adapter from an exe trace, with the secondaries it never carried filled in.

    `source` is the file it came from, and becomes the whole of the frame's provenance -- a `.dat`
    has no timestamp, project name or version to offer.

    `case` is optional and does one job: a chemistry `.dat` in this archive prints `TA` and `DIC`
    but **not** `P-Sal` or `P-Temp`, which are exactly what re-solving the carbonate system needs.
    Given the case, both are derived from the printed dilution and the ambient profile and land in
    `PlotFrame.derived`. Without it, `secondaries=True` raises and names the missing column.

    `secondaries=False` returns the exe's own columns untouched, for anyone who wants to see the
    trace as the exe wrote it.
    """
    frame = _exe_frame(dat)
    if "dilution" not in frame.columns:
        raise MissingColumnError(
            f"{source}: no dilution column (looked for {' or '.join(_EXE_COLUMNS)}); "
            "a trajectory with no dilution cannot be plotted against anything"
        )

    caveats = [
        "Values are the exe's three printed decimals, so anything derived from them inherits "
        "that precision.",
        f"No provenance: a .dat records no timestamp, project name or version. Source: {source}.",
        "The column set was chosen in the GUI, so a quantity absent here was never printed "
        "rather than being zero.",
    ]
    derived: set[str] = set()

    if "plume_diameter_m" in frame.columns:
        merged = _merge_flag(dat, frame)
        frame = frame.assign(merged=merged)
        derived.add("merged")
        peak = peak_to_mean(
            frame["plume_diameter_m"].to_numpy(dtype=np.float64),
            _nominal_spacing(dat),
            merged,
            profile=profile,
        )
        # The exe prints a centreline only when the GUI asked for one. When it did not, ours
        # follows from the diameter and the spacing -- both of which the file already carries.
        new = {"peak_to_mean": peak}
        if "centreline_dilution" not in frame.columns:
            new["centreline_dilution"] = centreline_dilution(
                frame["dilution"].to_numpy(dtype=np.float64), peak
            )
        frame = frame.assign(**new)
        derived |= set(new)

    if secondaries and {"total_alkalinity_umol_kg", "dic_umol_kg"} <= set(frame.columns):
        frame, added = _add_secondaries(frame, source, case)
        derived |= added
        caveats.append(
            "Omega_brucite is our own upper bound (no ion pairing) and has no exe reference to "
            "check against -- PLAN.md 8b."
        )

    return PlotFrame(
        frame=frame,
        source=str(source),
        origin="dat",
        caveats=tuple(caveats),
        derived=frozenset(derived),
        case=case,
        profile=profile,
    )


def _add_secondaries(
    frame: pd.DataFrame, source: str | Path, case: Case | None
) -> tuple[pd.DataFrame, set[str]]:
    """Re-solve the carbonate system from the printed TA/DIC, adding what the exe never printed.

    Salinity and temperature are required and are the usual thing missing: the exe's chemistry
    column set does not include them. They come from the trace when it printed them and from the
    case when it did not -- and if neither offers them this raises, naming both the column and the
    alternative, because a carbonate system solved on a guessed salinity is worse than none.
    """
    derived: set[str] = set()
    have = set(frame.columns)
    if {"salinity_psu", "temperature_degC"} <= have:
        salinity = frame["salinity_psu"].to_numpy(dtype=np.float64)
        temperature = frame["temperature_degC"].to_numpy(dtype=np.float64)
    elif case is not None and "depth_m" in have:
        salinity, temperature = _plume_salinity_and_temperature(
            case,
            frame["dilution"].to_numpy(dtype=np.float64),
            frame["depth_m"].to_numpy(dtype=np.float64),
        )
        frame = frame.assign(salinity_psu=salinity, temperature_degC=temperature)
        derived |= {"salinity_psu", "temperature_degC"}
    else:
        missing = sorted({"P-Sal", "P-Temp"} - have)
        raise MissingColumnError(
            f"{source}: the carbonate secondaries need plume salinity and temperature, and this "
            f"trace prints neither ({', '.join(missing)} absent). Either select those columns in "
            "the GUI and rerun, or pass case= so they can be derived from the dilution and the "
            "ambient profile. Refusing to emit a half-filled frame."
        )

    # With no case there is nothing to read the selections off, so the exe's own defaults stand --
    # which is what `resolve_constants` defaults to, and what case03 selected.
    constants = (
        resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
        if case is not None
        else resolve_constants()
    )
    state = solve_from_alkalinity_dic(
        frame["total_alkalinity_umol_kg"].to_numpy(dtype=np.float64),
        frame["dic_umol_kg"].to_numpy(dtype=np.float64),
        salinity,
        temperature,
        constants=constants,
    )
    solved = {
        "ph_total": state.ph_total,
        "pco2_uatm": state.pco2,
        "carbonate_umol_kg": state.carbonate,
        "bicarbonate_umol_kg": state.bicarbonate,
        "omega_calcite": state.omega_calcite,
        "omega_aragonite": state.omega_aragonite,
        "omega_brucite": state.omega_brucite(solubility_brucite(salinity, temperature)),
    }
    assert set(solved) <= set(CHEMISTRY_COLUMNS), "the neutral names are the tidy-CSV names"
    return frame.assign(**solved), derived | set(solved)
