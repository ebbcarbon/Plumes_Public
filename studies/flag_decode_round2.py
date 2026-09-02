"""Round 2 of the flag decode: name the controls, and test near-field flag 1 by output.

Round 1 (case51) settled *ownership* of every undecoded `.prj` flag but not *identity* -- the
reconnaissance step (note which GUI control differs on load) was not recorded, and the operator
does not recall (2026-09-01). This generates the second pass:

1. **`flagdecode2_bottomhit` / `flagdecode2_bottomhit_nf1`** -- a dense pair on the Macoma
   geometry with the port dropped to 10 m over an 11 m seabed, so the plume *hits the bottom*.
   If near-field flag 1 is the stop-at-bottom box (the natural candidate: ticked-by-default in
   every archived project, and position 2 is already the surface box), the flipped arm runs
   past seabed contact the way case06 runs past the surface. Recall not required: the traces
   answer.
2. **`flagdecode2_recon`** -- one folder of fresh flipped copies (every round-1 flip, plus an
   unflipped base), each cloned from case51's exe-blessed as-run base project, with a fill-in
   checklist. **Open, compare, write down, close. DO NOT RUN ANY OF THEM** -- opening writes
   nothing (the exe writes the `.prj` only on run), and the `nf3` copy in particular must not
   be run: the value 1 at that position made the exe fail silently and truncate the project
   (row 282). Loading it is safe -- round 1's flipped original loaded without error.

Run from the repository root::

    .venv/Scripts/python studies/flag_decode_round2.py
"""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

from plumes2.config import AmbientProfile
from plumes2.experiments import Experiment, write_experiment
from plumes2.io import load_case, read_prj
from plumes2.io.prj import write_prj
from plumes2.results import run
from plumes2.sweep import with_updated

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"
CASE51 = ROOT / "reference_cases" / "case51_flag_decode"

#: Round 1's flips, re-cut as reconnaissance copies -- `(name, PrjFile attribute, 0-indexed
#: position)`. ff7 is included even though the exe reclaims it on run (row 281b): the dialog
#: may still show what a loaded 1 means.
RECON_FLIPS = (
    ("nf1", "nearfield_flags", 0),
    ("nf3", "nearfield_flags", 2),
    ("nf5", "nearfield_flags", 4),
    ("nf6", "nearfield_flags", 5),
    ("ff1", "farfield_flags", 0),
    ("ff5", "farfield_flags", 4),
    ("ff6", "farfield_flags", 5),
    ("ff7", "farfield_flags", 6),
)

RECON_CHECKLIST = """# flagdecode2_recon -- a checklist, not a run

**DO NOT RUN ANY PROJECT IN THIS FOLDER.** Opening a project writes nothing; running rewrites
the `.prj` and, for `recon_nf3.prj`, reproduces the silent failure of ledger row 282. Loading
is safe -- round 1's flipped `nf3` loaded without error; only the *run* failed, and only the
*truncated* file it left behind crashes the loader.

Every file here is case51's as-run base project with exactly one flag flipped -- the same
flips as round 1, freshly cut. The question each answers: **which GUI control shows the flip?**

1. Open `recon_base.prj`. Write down the state of every control on the model-settings and
   far-field dialogs: the three stop boxes, the rise/fall count, the eddy-diffusivity
   selector, and any checkbox or dropdown not in that list.
2. Open each `recon_*.prj` in turn and fill the table: the ONE control that differs from base,
   and its state. "Nothing visible" is also an answer (then the flag is not a dialog control).
3. Close without running. Send this file back filled in.

| project | flipped flag (1-indexed) | control that differs from base | its state |
|---|---|---|---|
| `recon_nf1.prj` | near-field 1 (1 → 0) | | |
| `recon_nf3.prj` | near-field 3 (0 → 1) ⚠️ do not run | | |
| `recon_nf5.prj` | near-field 5 (1 → 0) | | |
| `recon_nf6.prj` | near-field 6 (1 → 0) | | |
| `recon_ff1.prj` | far-field 1 (1 → 0) | | |
| `recon_ff5.prj` | far-field 5 (1 → 0) | | |
| `recon_ff6.prj` | far-field 6 (1 → 0) | | |
| `recon_ff7.prj` | far-field 7 (0 → 1) | | |

Context: rows 281 (ff 1 and 5 gate the far field), 281b (ff 7 is exe-owned), 281c (nf 1/5/6
and ff 6 file-owned, inert on a surfacing run), 282 (nf 3 = 1 is fatal) -- all in
`reference_cases/case51_flag_decode/`.
"""


def bottomhit_case():
    """The Macoma geometry, chemistry stripped, aimed down at a seabed one metre below.

    ⚠️ The first two cuts of this did not hit: fired 45 degrees up from 10 m over an 11 m
    seabed the plume traps (`oscillation limit`), and even aimed straight down at Ebb's gentle
    flow it creeps -- the edge reaches 10.86 m in 361 s and the oscillation counter fires
    first. At 0.3 m of elevation the port's integration reaches the seabed in ~21 s, which is
    the unambiguous contact this arm needs.
    """
    base = load_case(ROOT / "studies" / "ebb_dose_study" / "ebb_macoma_default.yaml")
    case = base.model_copy(
        update={
            "description": "flag decode round 2: a dense discharge aimed at the seabed",
            "ambient": AmbientProfile(levels=base.ambient.levels),
            "effluent_chemistry": None,
            "effluent_do": None,
        }
    )
    case = with_updated(case, "diffuser.port_elevation", 0.3)
    case = with_updated(case, "diffuser.port_depth", 10.0)
    return with_updated(case, "diffuser.vertical_angle", -45.0)


def main() -> None:
    case = bottomhit_case()
    # The port's own prediction, computed before the runs and quoted in both notes.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ours = run(case)
    forecast = (
        f"the port integrates this case to `{ours.termination}` at t = {ours.end_time:.0f} s, "
        f"flux-averaged dilution {ours.final_dilution:.0f} -- seabed contact is early and "
        "unambiguous (edge criterion `depth + radius >= 10.3 m`, the row 106 convention)"
    )
    for name, question, predictions, settings_extra in (
        (
            "flagdecode2_bottomhit",
            "The bottom-hitting reference arm: does this geometry stop on seabed contact "
            "with everything as loaded?",
            {
                "termination": "`Plume hits the bottom`, early in the run",
                "port's own integration": forecast,
                "build fingerprint": "record which exe was launched; the far-field width "
                "identifies the build regardless (row 263 vs row 96)",
            },
            "stop plume at bottom hit: **leave as loaded** -- its on-load state is data; "
            "write it down before running",
        ),
        (
            "flagdecode2_bottomhit_nf1",
            "Is near-field flag 1 the stop-at-bottom box? Same project, flag 1 flipped to 0: "
            "if it is the box, this arm runs past seabed contact the way case06 runs past the "
            "surface; if the traces are bit-identical, it is not.",
            {
                "if nf1 is the bottom box": "the run continues past contact to a later stop "
                "(rise/fall count, oscillation, or the step cap) -- trace differs from the "
                "base arm after the contact step",
                "if nf1 is not the bottom box": "bit-identical to `flagdecode2_bottomhit`",
                "GUI on load": "if nf1 is the box, it shows unticked; write down its state "
                "BEFORE running",
            },
            "⚠️ do NOT touch the bottom-hit box -- run exactly as loaded; the flipped flag "
            "may already have moved it, and that is the measurement",
        ),
    ):
        experiment = Experiment(
            name=name,
            case=case,
            question=question,
            predictions=predictions,
            settings=(
                "all output columns",
                "No. of maximum plume rise or fall = 3",
                settings_extra,
                "stop plume at surface hit: leave as loaded",
            ),
            notes=(
                "Part of the flag-decode round 2 (case51's open question). Legacy build is "
                "fine -- the operator prefers it for physics without chemistry.",
            ),
        )
        target = write_experiment(experiment, PENDING)
        if name.endswith("_nf1"):
            prj_path = target / f"{name}.prj"
            prj = read_prj(prj_path)
            flags = list(prj.nearfield_flags)
            assert flags[0] == 1, "expected the generated base value 1 at near-field flag 1"
            flags[0] = 0
            write_prj(dataclasses.replace(prj, nearfield_flags=flags), prj_path)
        print(f"wrote {target}")

    # The reconnaissance folder: fresh flips cut from case51's exe-blessed as-run base.
    recon = PENDING / "flagdecode2_recon"
    recon.mkdir(parents=True, exist_ok=True)
    template = read_prj(CASE51 / "asrun_flagdecode_base_legacy.prj")
    write_prj(template, recon / "recon_base.prj")
    for name, attribute, index in RECON_FLIPS:
        flags = list(getattr(template, attribute))
        flags[index] = 1 - flags[index]
        write_prj(
            dataclasses.replace(template, **{attribute: flags}), recon / f"recon_{name}.prj"
        )
    (recon / "README.md").write_text(RECON_CHECKLIST, encoding="utf-8")
    print(f"wrote {recon} (9 projects + checklist; NO RUNS)")


if __name__ == "__main__":
    main()
