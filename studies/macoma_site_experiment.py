"""Generate the standalone Macoma reference case: the site's actual values, on both ambients.

The archive's `case00`-`case12` and `case24` were exe runs of an *earlier entry* of Ebb's Macoma
diffuser, and that entry carried slips the site does not: 2 m for 2 ft ports, a 35 psu / 10 C
effluent that made the plume sink, a flow of 0.219 L/s (7.5x low), mixing zones typed in metres
and a chemistry table that was the exe run's rather than the site's. Until 2026-09-09 those
folders carried `macoma` in their names and read as the site (operator: misleading). They were
renamed, and this module writes the case that *is* the site, as a pending exe experiment:

* 25 x 0.0127 m ports at **2 ft (0.6096 m)**, 45 degrees up, square to the current, 2 m deep on a
  15 m riser (seabed 17 m; the profile stops at 15 m -- intentional, operator 2026-09-01);
* **5900 L/h (98.3 L/min) of intake water, S 30.9 / T 11.2**, dosed to TA 6000 umol/kg at the
  intake DIC (the example's illustrative dose; the study sweeps the axis);
* ambient carbonate chemistry **TA 2146 / DIC 2092 umol/kg, uniform in depth** (operator,
  2026-09-09; no depth-resolved measurement exists), K1K2 option 10, KSO4 option 1;
* mixing zones **20.7 ft / 207 ft** (6.31 m / 63.09 m);
* two arms -- the **acute** ambient at 0.02 m/s and the **chronic** at 0.05 m/s, near and far
  field alike (the operator's baselines folder) -- because the exe runs one ambient per project.

The case is `examples/run_macoma.py`'s `build_case()` -- the public, suite-executed statement of the
site -- so the experiment cannot drift from the example. Each arm's folder carries the `.prj`, the
ambient side-tables (hydrography and the two-row chemistry table, with the pH column the GUI
demands filled by PyCO2SYS), the port's own `case.yaml`, and a README with the port's forecasts
registered before the run. When a run comes back it graduates to `reference_cases/caseNN_macoma_*`
-- the one place the word belongs.

⚠️ What the `.prj` cannot carry, and the note therefore lists: the effluent endmember (TA 6000 /
DIC 2092 as the **(TA, DIC)** pair, never TA at a pH), the constant options, the far-field stops
(500 m / 10 000x) and the rise/fall count (3). The surface-stop box is left as loaded: the Macoma
rule is that a surface hit does not stop the plume (operator, 2026-09-08).

Run from the repository root::

    .venv/Scripts/python studies/macoma_site_experiment.py

Writes `reference_cases/pending/macoma_acute/` and `reference_cases/pending/macoma_chronic/`.

⭐ Ran 2026-09-09, the morning it was written, and graduated as
`reference_cases/case55_macoma_site/` (ledger row 286). Re-running this module regenerates the
pending arms; the graduated folder is the record.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

from plumes2 import mixing_zone_values
from plumes2.config import Case
from plumes2.experiments import Experiment, write_experiment
from plumes2.io import dump_case
from plumes2.results import Results, run
from plumes2.sweep import brucite_extract

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"

sys.path.insert(0, str(ROOT / "examples"))
from run_macoma import DOSE_TA, INTAKE_DIC, build_case  # noqa: E402  -- the public site case

ACUTE_CURRENT = 0.02
CHRONIC_CURRENT = 0.05

BUILD_NOTE = (
    "WHICH EXE BUILD ran this: write down which executable was launched, and from where. Nothing "
    "in the .prj or the .dat records it, and the far-field wastefield width is the after-the-fact "
    "fingerprint (row 275). This case has chemistry, so it needs the 2026 build."
)


def site_case(current: float, label: str) -> Case:
    """The example's case, on one ambient current, with a description that says which."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the intentional 17 m seabed / 15 m profile warning
        base = build_case()
        levels = [
            level.model_copy(update={"current_speed": current, "farfield_speed": current})
            for level in base.ambient.levels
        ]
        ambient = base.ambient.model_copy(update={"levels": levels})
        case = base.model_copy(
            update={
                "description": (
                    f"Macoma site, {label} ambient ({current:g} m/s): 25 x 0.0127 m ports at 2 ft, "
                    f"5900 L/h of intake water (S 30.9 / T 11.2) at TA {DOSE_TA:.0f} / "
                    f"DIC {INTAKE_DIC:.0f}, ambient TA 2146 / DIC 2092 uniform, MZ 20.7 / 207 ft"
                ),
                "ambient": ambient,
            }
        )
        return Case.model_validate(case.model_dump())


def _forecast(case: Case) -> Results:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(case, samples=3000)


def predictions(case: Case) -> dict[str, str]:
    """The port's forecasts for the observables the trace will print. Written before the run."""
    ours = _forecast(case)
    frame = ours.nearfield
    last = frame.iloc[-1]
    reach = float((last["x_m"] ** 2 + last["y_m"] ** 2) ** 0.5)
    zone = mixing_zone_values(ours)  # indexed by "acute" / "chronic"; `region` says which field
    extracted = brucite_extract(ours)
    out = {
        "termination": f"`{ours.termination}` at t = {ours.end_time:.0f} s",
        "near-field end: flux-averaged dilution": f"{ours.final_dilution:.0f}",
        "near-field end: distance from the diffuser": f"{reach:.2f} m",
        "trapping depth (centreline at the end)": f"{float(last['depth_m']):.2f} m",
        "plume diameter at the end": f"{float(last['plume_diameter_m']):.2f} m",
        "wastefield width handed to the far field": (
            f"{case.wastefield_width(float(last['plume_diameter_m'])):.1f} m"
        ),
        "merging": (
            "the jets merge in shallow overlap before the end (`merging happened` banner expected)"
            if "merged" in frame.columns and bool(frame["merged"].any())
            else "the jets never touch"
        ),
        "port pH (total)": f"{extracted['port_ph_total']:.3f}",
        "pH at the end of the near field (total)": f"{float(last['ph_total']):.3f}",
    }
    if extracted["omega1_region"] != "never":
        out["Omega_brucite falls back through 1 (flux-averaged; the exe cannot print it)"] = (
            f"dilution {extracted['omega1_dilution']:.2f}, {extracted['omega1_time_s']:.2f} s, "
            f"{100 * extracted['omega1_distance_m']:.1f} cm from the port"
        )
    for region in ("acute", "chronic"):
        if region in zone.index:
            row = zone.loc[region]
            out[
                f"{region} mixing-zone boundary ({float(row['distance_m']):.2f} m): dilution / pH"
            ] = f"{float(row['dilution']):.0f} / {float(row['ph_total']):.3f} ({row['region']})"
    if ours.farfield is not None and len(ours.farfield):
        far = ours.farfield.iloc[-1]
        out["far field at its last row"] = (
            f"{float(far['distance_m']):.0f} m, dilution {float(far['dilution']):.0f}, "
            f"width {float(far['width_m']):.1f} m"
        )
    return out


def experiments() -> tuple[Experiment, Experiment]:
    arms = []
    for label, current in (("acute", ACUTE_CURRENT), ("chronic", CHRONIC_CURRENT)):
        case = site_case(current, label)
        arms.append(
            Experiment(
                name=f"macoma_{label}",
                case=case,
                question=(
                    f"The site's actual values on the {label} ambient ({current:g} m/s): does the "
                    "exe reproduce the port's near field, boundaries and pH at 2 ft spacing, "
                    "5900 L/h of intake water and the site's uniform chemistry -- the "
                    "configuration the dose study is built on, which no archived run carries?"
                ),
                predictions=predictions(case),
                settings=(
                    *Experiment.__dataclass_fields__["settings"].default,  # type: ignore[attr-defined]
                    "Carbonate chemistry ON. Effluent entered as the (TA, DIC) pair: "
                    f"TA {DOSE_TA:.0f} / DIC {INTAKE_DIC:.0f} umol/kg -- never TA at a pH. "
                    "K1K2 option 10 (Lueker), KSO4 option 1. Ambient chemistry: load the CSV "
                    "written beside this note (TA 2146 / DIC 2092 on both rows; the pH column is "
                    "PyCO2SYS's value, which the GUI demands and ignores).",
                ),
                notes=(
                    BUILD_NOTE,
                    "The ambient chemistry CSV is in the exe's own table format, which carries "
                    "three significant figures: it loads as TA 2150 / DIC 2090, not 2146 / 2092. "
                    "The forecasts above were made at 2146 / 2092 (the difference is ~0.002 in "
                    "pH). If the dialog allows it, retype 2146 and 2092 into both rows after "
                    "loading; either way, record what the table held when it ran.",
                    "The port spacing in the .prj is 0.6096 m -- 2 ft in metres. Do not retype it "
                    "as 2.0: that is the slip the archived runs carry.",
                    "The seabed (17 m) sits below the profile's last row (15 m). Intentional "
                    "(operator, 2026-09-01); the exe runs this shape on every archived project.",
                    "Surface-stop box: leave as loaded. The Macoma rule is that a surface hit does "
                    "not stop the plume (operator, 2026-09-08); this case traps at ~1.5 m anyway.",
                    "Copy the returning .dat and the as-run .prj aside before the next run; the "
                    "other arm overwrites them.",
                    "`case.yaml` beside this note is the port's own statement of the case; "
                    "`plumes2 run case.yaml` reproduces every prediction above.",
                ),
            )
        )
    return arms[0], arms[1]


def main() -> None:
    for experiment in experiments():
        target = write_experiment(experiment, PENDING)
        dump_case(experiment.case, target / "case.yaml")
        print(f"wrote {target}")
        for key, value in experiment.predictions.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
