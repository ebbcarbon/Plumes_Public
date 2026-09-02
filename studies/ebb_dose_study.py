"""Phase 9, the study proper: the fixed-DIC alkalinity dose sweep at Ebb's default profile.

**Ebb's default profile is the Macoma configuration** (operator, 2026-08-26): case03's geometry --
25 x 0.0127 m ports at 2 m on a 15 m riser (seabed 17 m), **0.6096 m (2 ft) spacing**, 45 degrees
up, square to a 0.02 m/s current -- its 35 psu / 10 C effluent at 0.219 L/s, its stratified
ambient to 15 m, and its carbonate constants (K1K2 10, KSO4 1).

⚠️ **The spacing is a 2026-09-01 correction** (operator): the site's ports sit at 2 *feet*, and
case03's 2026 project carries 2 *metres* -- "2.0" entered with the wrong unit. The original
Dec-2025 Macoma project stored 2.0 under the `.prj` feet flag, echoing 0.61 m (ledger row 49),
which is where the number came from. The archived case03 stays as entered (it is evidence of what
the exe was given); this study overrides the one field. At 0.61 m the plumes MERGE (case05 merged
at 0.60 m on this geometry), where at 2 m they never did.

Two things are added here, and both are stated because
they are the study's inputs rather than the archive's:

* **The ambient chemistry profile reaches the seabed.** case03's table stops at 4 m, which is why
  a port-depth axis could not run in the dry run (PLAN 8f) and why "a chemistry profile to the
  seabed" was the one missing input. Below 4 m the deepest measured row -- TA 2850, DIC 2450
  umol/kg -- is **held constant** to 17 m. That is an assumption, not a measurement; replace the
  rows in `ebb_macoma_default.yaml` with Ebb's own profile when there is one.
* **The effluent is TA at the intake's DIC**, 2500 umol/kg -- Ebb's own specification, (TA, DIC)
  (PLAN 8f finding 1). The archive's entry style (TA at a held pH) is not a brucite axis.

Three sweeps, each on `sweep.brucite_extract` plus the **centreline** extent under the profile
PLAN 8.4 decided (`parabolic`, centreline = 2x the flux-averaged excess) and the literature
Gaussian as the stated sensitivity (2.313x):

    dose_axis.csv       TA 3000-20 000 at DIC 2500, the default geometry           8 cells
    dose_x_depth.csv    TA x port depth 2 / 5 / 11 m, seabed held at 17 m         12 cells
    dose_x_flow.csv     TA x flow 0.22 / 1.0 / 5.0 L/s                            12 cells

Every Omega_brucite here is the **upper bound** PLAN 8b describes, and Omega = 1 is thermodynamic --
a necessary condition for brucite precipitation, not a rate (no brucite rate law exists in this
port). The extent is where the plume falls back through Omega = 1, so a *smaller* number is a
*shorter* supersaturated window.

Run from the repository root::

    .venv/Scripts/python studies/ebb_dose_study.py            # ~4 min
    .venv/Scripts/python studies/ebb_dose_study.py --replot   # redraw from the saved CSVs

Writes `studies/ebb_dose_study/` -- the YAML, three CSVs, two figures. The write-up is
`studies/ebb_dose_study/README.md`, by hand, after looking at them.
"""

from __future__ import annotations

import logging
import math
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plumes2.config import AmbientChemistryLevel, Case, EffluentChemistry
from plumes2.crossplume import SimilarityProfile, peak_to_mean_round
from plumes2.io import dump_case, load_project
from plumes2.report import palette
from plumes2.results import Results
from plumes2.sweep import brucite_extract, sweep

ROOT = Path(__file__).resolve().parents[1]
CASE03 = ROOT / "reference_cases" / "case03_macoma_carbonate" / "test.prj"
OUT = ROOT / "studies" / "ebb_dose_study"
DEFAULT_YAML = OUT / "ebb_macoma_default.yaml"

#: The site's port spacing, m: **2 ft** (operator, 2026-09-01). case03's project says 2 m -- a
#: unit slip this study corrects without touching the archived evidence; see the module note.
PORT_SPACING = 0.6096
#: The intake's DIC, umol/kg -- case03's ambient at 1-3 m, what a seawater-fed feedstock carries.
INTAKE_DIC = 2500.0
#: The placeholder dose the default case is written with; every sweep overwrites it.
DEFAULT_DOSE = 4000.0
#: The dose axis, umol/kg. Ambient TA is 2850-3000, so 3000 is "no dose".
DOSES = [3000.0, 4000.0, 5000.0, 6000.0, 8000.0, 10000.0, 15000.0, 20000.0]
#: The coarser dose axis used against a second variable.
DOSES_COARSE = [4000.0, 6000.0, 10000.0, 20000.0]
#: Port depths, m, with the seabed held at case03's 17 m by moving the riser.
DEPTHS = [2.0, 5.0, 11.0]
SEABED = 17.0
#: Flows, m3/s: case03's own, then ~5x and ~23x.
FLOWS = [0.00021906318194444445, 0.001, 0.005]
#: Depths the held chemistry is written at below the last measured row.
EXTENSION_DEPTHS = [6.0, 9.0, 12.0, 15.0, 17.0]

DOSE = "effluent_chemistry.total_alkalinity"
FLOW = "effluent.flow"
DEPTH = "diffuser.port_depth"

#: The decided profile and the stated sensitivity (PLAN 8.4, 2026-08-26).
PROFILES = {
    "parabolic": SimilarityProfile.PARABOLIC,
    "gaussian": SimilarityProfile.GAUSSIAN,
}


def ebb_default_case(dose: float = DEFAULT_DOSE) -> Case:
    """case03 as Ebb's default: chemistry to the seabed, effluent as TA at the intake DIC."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # case03's seabed-below-profile GeometryWarning
        case = load_project(CASE03, warn_on_drift=False).to_case()
    measured = list(case.ambient.chemistry)
    deepest = measured[-1]
    extension = [
        deepest.model_copy(update={"depth": depth})
        for depth in EXTENSION_DEPTHS
        if depth > deepest.depth
    ]
    ambient = case.ambient.model_copy(update={"chemistry": measured + extension})
    case = case.model_copy(
        update={
            "description": "Ebb default profile: Macoma (case03) with the port spacing "
            "corrected to 2 ft (0.6096 m; the archived project says 2 m -- a unit slip), "
            "ambient chemistry held to the 17 m seabed below the 4 m measured row, and the "
            "effluent as TA at the intake DIC",
            "ambient": ambient,
            "diffuser": case.diffuser.model_copy(update={"port_spacing": PORT_SPACING}),
            "effluent_chemistry": EffluentChemistry(total_alkalinity=dose, dic=INTAKE_DIC),
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Case.model_validate(case.model_dump())


def _held_rows(case: Case) -> list[AmbientChemistryLevel]:
    return [level for level in case.ambient.chemistry if level.depth in EXTENSION_DEPTHS]


def ebb_extract(results: Results) -> dict[str, Any]:
    """`brucite_extract` plus the **centreline** Omega = 1 extent under each profile.

    The centreline excess is `peak/mean` times the flux-averaged excess, so the axis falls back to
    Omega = 1 where the flux-averaged dilution reaches `peak/mean x omega1_dilution`. The time and
    distance of that point are read off the same trajectory. A crossing past the near-field end is
    reported as NaN with `centreline_<profile>_region = "beyond_nearfield"` -- the far field has
    no centreline in this port (the Brooks wastefield is a slab average).
    """
    out = brucite_extract(results)
    near = results.nearfield
    dilution = near["dilution"].to_numpy(np.float64)
    time_s = near["time_s"].to_numpy(np.float64)
    distance = np.maximum.accumulate(
        np.hypot(near["x_m"].to_numpy(np.float64), near["y_m"].to_numpy(np.float64))
    )
    flux_crossing = float(out["omega1_dilution"])
    for label, profile in PROFILES.items():
        target = peak_to_mean_round(profile) * flux_crossing
        key = f"centreline_{label}"
        if out["omega1_region"] == "never" or not math.isfinite(target):
            out[f"{key}_dilution"] = math.nan
            out[f"{key}_time_s"] = math.nan
            out[f"{key}_distance_m"] = math.nan
            out[f"{key}_region"] = out["omega1_region"]
            continue
        if target > dilution[-1]:
            out[f"{key}_dilution"] = target
            out[f"{key}_time_s"] = math.nan
            out[f"{key}_distance_m"] = math.nan
            out[f"{key}_region"] = "beyond_nearfield"
            continue
        # `dilution` is monotone along the integrated trajectory, so interpolate on it directly.
        out[f"{key}_dilution"] = target
        out[f"{key}_time_s"] = float(np.interp(target, dilution, time_s))
        out[f"{key}_distance_m"] = float(np.interp(target, dilution, distance))
        out[f"{key}_region"] = "nearfield"
    return out


def _run(name: str, base: Case, axes: dict[str, list[float]]) -> pd.DataFrame:
    started = time.perf_counter()
    frame = sweep(base, axes, extract=ebb_extract, samples=3000)
    logging.info("%s: %d cells in %.0f s", name, len(frame), time.perf_counter() - started)
    return frame


def run_depth_sweep(doses: list[float]) -> pd.DataFrame:
    """Dose x port depth with the seabed held at 17 m -- so the riser shortens as the port sinks.

    `sweep` takes one field per axis and the seabed is `port_depth + port_elevation`, so a plain
    depth axis would move the seabed too. One base case per depth keeps the geometry honest.
    """
    pieces = []
    for depth in DEPTHS:
        base = ebb_default_case()
        diffuser = base.diffuser.model_copy(
            update={"port_depth": depth, "port_elevation": SEABED - depth}
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            base = Case.model_validate(base.model_copy(update={"diffuser": diffuser}).model_dump())
        piece = _run(f"dose_x_depth[{depth:g} m]", base, {DOSE: doses})
        piece.insert(1, DEPTH, depth)
        pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def _series(ax: plt.Axes, x: np.ndarray, y: np.ndarray, slot: int, label: str | None) -> None:
    ax.plot(
        x,
        y,
        color=palette.SERIES[slot],
        linewidth=2.0,
        marker="o",
        markersize=4.5,
        markeredgecolor=palette.SURFACE,
        markeredgewidth=1.0,
    )
    finite = np.isfinite(y)
    if label and finite.any():
        ax.annotate(
            label,
            (x[finite][-1], y[finite][-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=palette.INK_SECONDARY,
        )


def figure_dose_axis(frame: pd.DataFrame) -> plt.Figure:
    ok = frame[frame["error"].fillna("") == ""].sort_values(DOSE)
    x = ok[DOSE].to_numpy(np.float64) / 1000.0
    with plt.rc_context(palette.matplotlib_style()):
        fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), constrained_layout=True)
        ax = axes[0, 0]
        _series(ax, x, ok["port_ph_total"].to_numpy(np.float64), 0, "port")
        _series(ax, x, ok["acute_ph_total"].to_numpy(np.float64), 1, "acute MZ")
        ax.set_title("pH (total) at the port and at the acute boundary")
        ax = axes[0, 1]
        _series(ax, x, ok["port_omega_brucite"].to_numpy(np.float64), 0, None)
        ax.set_yscale("log")
        ax.axhline(1.0, color=palette.AXIS, linewidth=0.8)
        ax.set_title("Ω_brucite at the port (upper bound)")
        series = (
            ("omega1", 0, "flux-averaged"),
            ("centreline_parabolic", 1, "centreline, parabolic"),
            ("centreline_gaussian", 2, "centreline, Gaussian"),
        )
        ax = axes[1, 0]
        for prefix, slot, label in series:
            _series(ax, x, ok[f"{prefix}_dilution"].to_numpy(np.float64), slot, label)
        ax.set_title("Dilution at which Ω_brucite falls to 1")
        ax = axes[1, 1]
        for prefix, slot, label in series:
            _series(ax, x, ok[f"{prefix}_distance_m"].to_numpy(np.float64), slot, label)
        ax.set_title("Distance from the port where Ω_brucite falls to 1 (m)")
        for ax in axes.flat:
            ax.set_xlabel(f"effluent TA, mmol/kg -- DIC {INTAKE_DIC:.0f} held")
            ax.margins(x=0.15)
        fig.suptitle(
            "Ebb default profile (Macoma, case03), fixed-DIC dose axis: thermodynamic Ω, upper "
            "bound; centreline under the decided parabola, Gaussian as sensitivity",
            x=0.01,
            ha="left",
            fontsize=10,
            color=palette.INK_SECONDARY,
        )
    return fig


def figure_second_axes(depth: pd.DataFrame, flow: pd.DataFrame) -> plt.Figure:
    with plt.rc_context(palette.matplotlib_style()):
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True)
        ok = depth[depth["error"].fillna("") == ""]
        for slot, d in enumerate(sorted(ok[DEPTH].unique())):
            rows = ok[ok[DEPTH] == d].sort_values(DOSE)
            _series(
                axes[0],
                rows[DOSE].to_numpy(np.float64) / 1000.0,
                rows["centreline_parabolic_distance_m"].to_numpy(np.float64),
                slot,
                f"port at {d:g} m",
            )
        axes[0].set_title("Centreline Ω_brucite = 1 distance (m) by port depth, seabed 17 m")
        ok = flow[flow["error"].fillna("") == ""]
        for slot, q in enumerate(sorted(ok[FLOW].unique())):
            rows = ok[ok[FLOW] == q].sort_values(DOSE)
            _series(
                axes[1],
                rows[DOSE].to_numpy(np.float64) / 1000.0,
                rows["centreline_parabolic_distance_m"].to_numpy(np.float64),
                slot,
                f"Q = {q * 1e3:.2f} L/s",
            )
        axes[1].set_title("Centreline Ω_brucite = 1 distance (m) by flow")
        for ax in axes:
            ax.set_xlabel(f"effluent TA, mmol/kg -- DIC {INTAKE_DIC:.0f} held")
            ax.margins(x=0.2)
        fig.suptitle(
            "Ebb default profile: the supersaturated window against the two geometry knobs "
            "(parabolic centreline, upper bound)",
            x=0.01,
            ha="left",
            fontsize=10,
            color=palette.INK_SECONDARY,
        )
    return fig


SHOW = [
    DOSE,
    DEPTH,
    FLOW,
    "termination",
    "warnings",
    "error",
    "port_ph_total",
    "port_omega_brucite",
    "nearfield_peak_ph_total",
    "omega1_dilution",
    "omega1_time_s",
    "omega1_distance_m",
    "omega1_region",
    "centreline_parabolic_dilution",
    "centreline_parabolic_time_s",
    "centreline_parabolic_distance_m",
    "centreline_gaussian_distance_m",
    "nearfield_end_distance_m",
    "acute_region",
    "acute_ph_total",
    "acute_omega_aragonite",
    "chronic_ph_total",
    "chronic_omega_aragonite",
]


def _save_figures(dose: pd.DataFrame, depth: pd.DataFrame, flow: pd.DataFrame) -> None:
    for stem, fig in (
        ("figure_dose_axis", figure_dose_axis(dose)),
        ("figure_second_axes", figure_second_axes(depth, flow)),
    ):
        fig.savefig(OUT / f"{stem}.svg")
        fig.savefig(OUT / f"{stem}.png", dpi=130)
        logging.info("figure -> %s", OUT / f"{stem}.svg")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    if "--replot" in sys.argv:
        _save_figures(
            pd.read_csv(OUT / "dose_axis.csv"),
            pd.read_csv(OUT / "dose_x_depth.csv"),
            pd.read_csv(OUT / "dose_x_flow.csv"),
        )
        return

    base = ebb_default_case()
    dump_case(base, DEFAULT_YAML)
    logging.info(
        "Ebb default case -> %s (chemistry to %g m, %d held rows below %g m)",
        DEFAULT_YAML,
        base.ambient.chemistry[-1].depth,
        len(_held_rows(base)),
        EXTENSION_DEPTHS[0] - 2.0,
    )

    dose = _run("dose_axis", base, {DOSE: DOSES})
    dose.to_csv(OUT / "dose_axis.csv", index=False, lineterminator="\n")
    depth = run_depth_sweep(DOSES_COARSE)
    depth.to_csv(OUT / "dose_x_depth.csv", index=False, lineterminator="\n")
    flow = _run("dose_x_flow", base, {DOSE: DOSES_COARSE, FLOW: FLOWS})
    flow.to_csv(OUT / "dose_x_flow.csv", index=False, lineterminator="\n")
    _save_figures(dose, depth, flow)

    with pd.option_context("display.width", 360, "display.max_columns", 40):
        for table in (dose, depth, flow):
            print(table[[c for c in SHOW if c in table.columns]].to_string(index=False))
            print()


if __name__ == "__main__":
    main()
