"""Generate the `dose_parity` exe experiment: the chemistry parity check along the dose axis.

Phase 8's comparison-study bullet has been open since 2026-08-12: *"quantifying where the exe's
embedded CO2SYS departs from PyCO2SYS across the alkalinity-dose regime, not just on the two
archived cases."* Every chemistry parity row in the ledger (35, 41, 43, 128) was measured on
case03 and case04, both at TA 4000 -- one point on the axis the dose study sweeps. Phase 9's
exit criterion is that every number on the dose-response curve is *either parity-checked or
carries a named non-parity justification*, and pH and Ω_aragonite along the dose axis are
parity-checkable **only if the exe is run there**. This experiment is those runs.

⭐ **The axis is TA at fixed DIC, not TA at fixed pH.** The dry run (`dose_dry_run.py`) found
that under the archive's entry style -- TA plus pH 10.5, DIC derived -- the port pH is 10.44 at
*every* dose, so nothing about the exe's speciation at high pH would be learned by sweeping it.
Entering TA and DIC instead (the exe prefers that pair and discards the pH field, case04 / row
30) makes the exe's own CO2SYS *compute* the port pH from 9.5 up to ~12, which is exactly the
region where the two CO2SYS generations are expected to diverge most. It is also how an Mg(OH)₂
feedstock arrives: alkalinity added to intake seawater at the intake's DIC.

One project, four runs: the `.prj` carries no chemistry (PLAN 7b), so the dose is typed into
the carbonate dialog per run and the trace copied aside before the next. The predictions below
are the port's own numbers at each dose, registered here before the exe has run them.

Run from the repository root::

    .venv/Scripts/python studies/dose_parity_experiment.py

Writes `reference_cases/pending/dose_parity/`.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from plumes2.config import Case, EffluentChemistry
from plumes2.experiments import Experiment, write_experiment
from plumes2.io import load_project
from plumes2.results import run

ROOT = Path(__file__).resolve().parents[1]
CASE03 = ROOT / "reference_cases" / "case03_carbonate" / "test.prj"
PENDING = ROOT / "reference_cases" / "pending"

#: TA 4000 at DIC 2500 overlaps case03's pH range (its derived DIC was 1646 at pH 10.5); the
#: rest climb to 5x. In µmol/kg.
DOSES = [4000.0, 6000.0, 10000.0, 20000.0]
#: case03's ambient DIC at 1-3 m -- what a seawater-fed slurry carries.
INTAKE_DIC = 2500.0


def base_case() -> Case:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case = load_project(CASE03, warn_on_drift=False).to_case()
    case = case.model_copy(
        update={
            "effluent_chemistry": EffluentChemistry(total_alkalinity=DOSES[0], dic=INTAKE_DIC),
            # Interval 1 so the exe's rows can be aligned on step with everything else in the
            # archive that was run this way (case03's kso4_option3 rerun, case13's interval-1s).
            "near_field": case.near_field.model_copy(update={"output_interval": 1}),
        }
    )
    return Case.model_validate(case.model_dump())


def predictions(base: Case) -> dict[str, str]:
    out: dict[str, str] = {
        "hydrodynamics, every run": (
            "Dilutn, P-dia, Depth bit-identical to case03's kso4_option3.dat on every shared step "
            "-- chemistry rides on top of the plume and does not feed back (row 215). If this "
            "fails, nothing below is about chemistry"
        ),
        "TA and DIC columns, every run": (
            "conservative in dilution: TA_row = TA_amb + (TA_eff*rho/1000 - TA_amb)/Dilutn to the "
            "exe's printed precision, as case03 shows (row 40); DIC likewise from 2500*rho/1000. "
            "The exe prints mmol/m3, i.e. umol/kg x 1.02695 at this effluent (PLAN 7.5)"
        ),
        "the gap, and the reason for the runs": (
            "on case03/case04 (port pH ~10.0-10.4) the exe's pH sits 0.011-0.024 BELOW PyCO2SYS "
            "and its Omega 0.8-3.4 % above (rows 41/43), attributed to the speciation rather than "
            "the Ksp (row 123). These runs put the exe's port pH at ~9.5, ~10.6, ~11.4 and ~11.9. "
            "If the divergence is a constant offset the first-row gap stays 0.01-0.03 all the way "
            "up and the dose curve's pH is parity-checked to that; if it widens above pH 11 -- "
            "where borate, water and the carbonate alkalinity terms trade places -- the widening "
            "is the number the study must carry as a named non-parity justification"
        ),
        "OmegaA / OmegaC, every run": (
            "the exe reports both; the ratio OmegaC/OmegaA is Ksp_A/Ksp_C and must match case03's "
            "1.57 exactly (row 123). Any row where it does not is a Ksp change, not speciation"
        ),
    }
    for dose in DOSES:
        case = base.model_copy(
            update={
                "effluent_chemistry": EffluentChemistry(total_alkalinity=dose, dic=INTAKE_DIC),
            }
        )
        case = Case.model_validate(case.model_dump())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = run(case)
        near = results.nearfield
        first, last = near.iloc[0], near.iloc[-1]
        ta_end = last["total_alkalinity_umol_kg"]
        out[f"TA {dose:.0f}: first printed row (Dilutn ~1.0)"] = (
            f"pH(total) ~{first['ph_total']:.3f}, OmegaA ~{first['omega_aragonite']:.1f}, "
            f"OmegaC ~{first['omega_calcite']:.1f}; the exe 0.01-0.03 below on pH and a few "
            f"percent above on Omega if the gap is the constant offset measured at TA 4000"
        )
        out[f"TA {dose:.0f}: near-field end (Dilutn ~{last['dilution']:.0f})"] = (
            f"TA ~{ta_end:.0f} umol/kg (~{ta_end * 1.02695:.0f} mmol/m3 as printed), pH(total) "
            f"~{last['ph_total']:.3f}, OmegaA ~{last['omega_aragonite']:.2f} -- within 0.007 pH "
            f"and 2.2 % of the exe if row 36's far-field agreement holds"
        )
    return out


def main() -> None:
    base = base_case()
    experiment = Experiment(
        name="dose_parity",
        case=base,
        question=(
            "Does the exe's embedded CO2SYS stay within its measured 0.011-0.024 pH of PyCO2SYS "
            "as the effluent alkalinity rises from 4000 to 20000 umol/kg at a fixed DIC of 2500 "
            "-- port pH from ~9.5 to ~12 -- or does the gap grow with dose? Phase 9 cannot quote "
            "a parity-checked pH along the dose axis until the exe has been run along it."
        ),
        predictions=predictions(base),
        settings=(
            "all output columns",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked",
            "leave stop-plume-at-surface AS YOU FIND IT and say which way it was (it is "
            "surface_stop_pair_v2's subject; this geometry traps at ~2.3 m and never surfaces)",
            "carbonate module ON, KSO4 selector = 1 (case03's setting: Dickson bisulfate, Lee "
            "borate per row 128), K1K2 as case03 had it",
            "ambient chemistry: load AmbientChem_dose_parity.csv from this directory (it is "
            "case03's testco2.csv, 1-4 m, which reaches below the 2 m port, with the blank pH "
            "column filled by the solver because the GUI refuses a blank -- nothing to type)",
        ),
        notes=(
            "This is case03's geometry and ambient, unchanged; only the effluent chemistry moves. "
            "It is NOT case03's entry style: enter TA and DIC, not TA and pH. The dry run found "
            "that TA at a held pH gives the same port pH (10.44) at every dose, so nothing would "
            "be learned; TA at a held DIC makes the exe compute the port pH itself.",
            "One project serves all four runs because no .prj stores chemistry. For each dose, in "
            "order: open the carbonate dialog, enter effluent TA = <dose>, DIC = 2500, and leave "
            "the pH field at whatever it holds (the exe uses TA + DIC when both are given and "
            "discards the pH -- case04, row 30), run, then copy the trace to dose_<TA>.dat and "
            "the project to asrun_dose_<TA>.prj BEFORE the next run overwrites both.",
            "Doses, in umol/kg: 4000, 6000, 10000, 20000. If the exe refuses a value, prints NaN, "
            "or stops early at one of them, that is a finding -- say which and keep the others. "
            "TA 20000 / DIC 2500 is pH ~12 at the port and is the run most likely to break "
            "something.",
            "If the carbonate dialog shows any option besides KSO4 and K1K2 (a pH-scale selector, "
            "a borate selector, a calcium field), write down what it shows and what was selected. "
            "Nothing decoded so far records it.",
        ),
    )
    written = write_experiment(experiment, PENDING)
    print(written)
    for path in sorted(written.iterdir()):
        print("  ", path.name)


if __name__ == "__main__":
    main()
