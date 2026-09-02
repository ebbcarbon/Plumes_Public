"""Phase 9's first dry run: the alkalinity-dose sweep, on case03, for what breaks (PLAN section 9).

⚠️ **A dry run, not the study.** The deliverable is the list of what the harness gets wrong
or cannot yet say, found by running it end to end on the one chemistry case the archive has.
Nothing here is Ebb's geometry or Ebb's dose; the curve is a shape on Macoma's outfall, and
PLAN 8.4 (the similarity profile) is unsettled, so no number from this run is publishable.

Three things the first pass found, each of which changed what this script runs:

* ⭐⭐ **"TA at fixed pH" is not a brucite dose axis.** The archive's only chemistry entry style
  is case03's -- TA plus a pH of 10.5 (free), DIC derived -- and under it Ω_brucite at the port
  is **131.4 at every dose from 3000 to 20000 µmol/kg**, because pH fixes [OH⁻] and salinity
  fixes [Mg²⁺]; the alkalinity only moves the derived DIC. A feedstock that *is* Mg(OH)₂ raises
  TA at the intake's DIC and lets pH float, so the study's axis is **TA at fixed DIC**, and the
  script now runs both: the archive's axis (`sweep.csv`) and the feedstock's (`mgoh2_axis.csv`).
* **Both of case03's mixing-zone boundaries are in the far field** (acute 20.7 m against a
  near field a few metres long), where Ω_brucite is ~0.009 at any dose. A study that reports
  only at the boundaries would report *no* brucite risk while the port sits above Ω = 100. So
  the extract also reads the near-field **peak** and the **extent** of supersaturation -- the
  dilution, time and distance at which Ω_brucite last exceeds 1. ⭐ Promoted to
  `sweep.brucite_extract` on 2026-08-25; this script now imports it.
* **The threshold reported is thermodynamic, not kinetic.** `chem/precipitation.py` has no
  brucite rate law and PLAN 8b forbids inferring alkalinity loss from Ω without one, so the
  "runaway threshold" of PLAN 8e item 2 is reported here as the dose at which Ω_brucite = 1
  at a given distance -- a necessary condition for precipitation, not a prediction of it.

Run from the repository root::

    .venv/Scripts/python studies/dose_dry_run.py            # ~4.5 min
    .venv/Scripts/python studies/dose_dry_run.py --replot   # redraw from the saved CSVs

Writes `studies/dose_dry_run/{sweep,mgoh2_axis,depth_probe}.csv` and two figures; the findings
are written up by hand in `studies/dose_dry_run/README.md` after looking at them.
"""

from __future__ import annotations

import logging
import sys
import time
import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from plumes2.config import Case, EffluentChemistry
from plumes2.io import load_project
from plumes2.report import palette
from plumes2.sweep import brucite_extract, sweep

ROOT = Path(__file__).resolve().parents[1]
CASE03 = ROOT / "reference_cases" / "case03_macoma_carbonate" / "test.prj"
OUT = ROOT / "studies" / "dose_dry_run"

#: case03's own effluent entry: TA 4000, pH 10.5 on the free scale, DIC derived (PLAN 7.6).
CASE03_DOSE_UMOL_KG = 4000.0
CASE03_PH_FREE = 10.5

#: The dose axis. Ambient TA here is 2850-3000, so 3000 is "no dose" and the top is ~7x
#: case03's.
DOSES = [3000.0, 4000.0, 5000.0, 6000.0, 8000.0, 10000.0, 15000.0, 20000.0]

#: The dose *rate* axis: case03's own flow, then ~5x and ~23x (the value case03's effluent
#: CSV carries, which the .prj overrides -- see the ProjectDriftWarning on load).
FLOWS = [0.00021906318194444445, 0.001, 0.005]

#: The feedstock axis: TA at the intake's DIC, pH floating. 2500 is case03's ambient DIC at
#: 1-3 m -- what a seawater-fed Mg(OH)2 slurry would carry.
INTAKE_DIC_UMOL_KG = 2500.0

#: The port-depth probe. case03's ambient chemistry table stops at 4 m and the Case validator
#: requires it to reach below the port, so 5 m and 11 m are expected to fail the cell -- the
#: point is to see that they fail as rows, and what the error says.
PROBE_DEPTHS = [2.0, 5.0, 11.0]
PROBE_DOSES = [4000.0, 8000.0]

DOSE = "effluent_chemistry.total_alkalinity"
FLOW = "effluent.flow"


def base_case(chemistry: EffluentChemistry) -> Case:
    """case03 with an effluent endmember attached (the .prj cannot carry it, PLAN 7b)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the seabed GeometryWarning; recorded per cell instead
        project = load_project(CASE03, warn_on_drift=False)
        case = project.to_case()
    case = case.model_copy(update={"effluent_chemistry": chemistry})
    return Case.model_validate(case.model_dump())


def _series(
    ax: plt.Axes, x: np.ndarray, y: np.ndarray, slot: int, label: str | None, dy: float = 0.0
) -> None:
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
            xytext=(6, dy),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=palette.INK_SECONDARY,
        )


def figure_fixed_ph(frame: pd.DataFrame) -> plt.Figure:
    """The archive's axis: one series per flow, direct-labelled; the report's palette."""
    ok = frame[frame["error"].fillna("") == ""]
    flows = sorted(ok[FLOW].unique())
    with plt.rc_context(palette.matplotlib_style()):
        fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), constrained_layout=True)
        panels = [
            ("port_omega_brucite", "Ω_brucite at the port (t = 0) -- the same at every dose", True),
            ("omega1_dilution", "Dilution at which Ω_brucite falls to 1", False),
            ("acute_ph_total", "pH (total) at the acute boundary, 20.7 m", False),
            ("chronic_omega_aragonite", "Ω_aragonite at the chronic boundary, 207 m", False),
        ]
        for ax, (column, title, log) in zip(axes.flat, panels, strict=True):
            for slot, q in enumerate(flows):
                rows = ok[ok[FLOW] == q].sort_values(DOSE)
                x = rows[DOSE].to_numpy(np.float64) / 1000.0
                y = rows[column].to_numpy(np.float64)
                # The port value does not depend on the flow, so the three series coincide;
                # label once rather than stack three labels on one point.
                label: str | None = f"Q = {q * 1e3:.2f} L/s"
                if column == "port_omega_brucite":
                    label = "all three flows" if slot == 0 else None
                # The three flows nearly coincide on the crossing panel; fan the labels out.
                dy = (1 - slot) * 9.0 if column == "omega1_dilution" else 0.0
                _series(ax, x, y, slot, label, dy)
            ax.set_title(title)
            ax.set_xlabel("effluent total alkalinity, mmol/kg -- pH 10.5 (free) held, DIC derived")
            if log:
                ax.set_yscale("log")
                ax.axhline(1.0, color=palette.AXIS, linewidth=0.8)
                ax.annotate(
                    "Ω = 1",
                    (DOSES[0] / 1000.0, 1.0),
                    xytext=(0, 4),
                    textcoords="offset points",
                    fontsize=8,
                    color=palette.INK_MUTED,
                )
            ax.margins(x=0.2)
        fig.suptitle(
            "Dose dry run on case03, the archive's axis (TA at fixed pH): thermodynamic Ω only, "
            "upper bound, not publishable before PLAN 8.4",
            x=0.01,
            ha="left",
            fontsize=10,
            color=palette.INK_SECONDARY,
        )
    return fig


def figure_fixed_dic(frame: pd.DataFrame) -> plt.Figure:
    """The feedstock's axis: TA at the intake DIC, pH floating. One flow, four quantities."""
    ok = frame[frame["error"].fillna("") == ""].sort_values(DOSE)
    x = ok[DOSE].to_numpy(np.float64) / 1000.0
    with plt.rc_context(palette.matplotlib_style()):
        fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), constrained_layout=True)
        panels = [
            ("port_ph_total", "pH (total) at the port (t = 0)", False),
            ("port_omega_brucite", "Ω_brucite at the port (t = 0), upper bound", True),
            ("omega1_dilution", "Dilution at which Ω_brucite falls to 1", False),
            ("omega1_distance_m", "Distance from the port where Ω_brucite falls to 1 (m)", False),
        ]
        for ax, (column, title, log) in zip(axes.flat, panels, strict=True):
            _series(ax, x, ok[column].to_numpy(np.float64), 0, None)
            ax.set_title(title)
            ax.set_xlabel(f"effluent TA, mmol/kg -- DIC {INTAKE_DIC_UMOL_KG:.0f} held")
            if log:
                ax.set_yscale("log")
                ax.axhline(1.0, color=palette.AXIS, linewidth=0.8)
                ax.annotate(
                    "Ω = 1",
                    (x[0], 1.0),
                    xytext=(0, 4),
                    textcoords="offset points",
                    fontsize=8,
                    color=palette.INK_MUTED,
                )
            ax.margins(x=0.1)
        fig.suptitle(
            f"Dose dry run on case03, the feedstock's axis (TA at DIC {INTAKE_DIC_UMOL_KG:.0f}, "
            f"Q = {FLOWS[0] * 1e3:.2f} L/s): thermodynamic Ω only, upper bound",
            x=0.01,
            ha="left",
            fontsize=10,
            color=palette.INK_SECONDARY,
        )
    return fig


SHOW = [
    DOSE,
    FLOW,
    "diffuser.port_depth",
    "termination",
    "warnings",
    "error",
    "port_ph_total",
    "port_dic_umol_kg",
    "port_omega_brucite",
    "omega1_dilution",
    "omega1_distance_m",
    "omega1_region",
    "nearfield_end_distance_m",
    "nearfield_end_ph_total",
    "nearfield_end_omega_brucite",
    "acute_region",
    "acute_ph_total",
    "acute_omega_brucite",
    "chronic_region",
    "chronic_ph_total",
    "chronic_omega_aragonite",
]


def _run(name: str, base: Case, axes: dict[str, list[float]]) -> pd.DataFrame:
    started = time.perf_counter()
    # Dense sampling: the Ω = 1 crossing sits a fraction of a second from the port, and at the
    # default 200 samples the log-interpolated crossing overstates the dilution (2.2 for 1.7).
    # Integration cost is independent of `samples` (conftest).
    frame = sweep(base, axes, extract=brucite_extract, samples=3000)
    elapsed = time.perf_counter() - started
    frame.to_csv(OUT / f"{name}.csv", index=False, lineterminator="\n")
    logging.info("%s: %d cells in %.0f s -> %s", name, len(frame), elapsed, OUT / f"{name}.csv")
    return frame


def _save_figures(frame: pd.DataFrame, mgoh2: pd.DataFrame) -> None:
    figures = (("figure", figure_fixed_ph(frame)), ("figure_mgoh2", figure_fixed_dic(mgoh2)))
    for stem, fig in figures:
        fig.savefig(OUT / f"{stem}.svg")
        fig.savefig(OUT / f"{stem}.png", dpi=130)
        logging.info("figure -> %s", OUT / f"{stem}.svg")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT.mkdir(parents=True, exist_ok=True)

    if "--replot" in sys.argv:  # redraw from the saved frames; no integration
        _save_figures(pd.read_csv(OUT / "sweep.csv"), pd.read_csv(OUT / "mgoh2_axis.csv"))
        return

    fixed_ph = base_case(EffluentChemistry(total_alkalinity=CASE03_DOSE_UMOL_KG, ph=CASE03_PH_FREE))
    fixed_dic = base_case(
        EffluentChemistry(total_alkalinity=CASE03_DOSE_UMOL_KG, dic=INTAKE_DIC_UMOL_KG)
    )

    frame = _run("sweep", fixed_ph, {DOSE: DOSES, FLOW: FLOWS})
    mgoh2 = _run("mgoh2_axis", fixed_dic, {DOSE: DOSES})
    probe = _run("depth_probe", fixed_ph, {DOSE: PROBE_DOSES, "diffuser.port_depth": PROBE_DEPTHS})

    _save_figures(frame, mgoh2)

    with pd.option_context("display.width", 320, "display.max_columns", 40):
        for table in (frame, mgoh2, probe):
            print(table[[c for c in SHOW if c in table.columns]].to_string(index=False))
            print()


if __name__ == "__main__":
    main()
