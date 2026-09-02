"""Regenerate the two open GUI experiments: `surface_stop_pair_v2` and `style_enumeration`.

⚠️ **Both were hand-written in August and both came back unusable, for different reasons.**
Recording them as generators fixes the class of problem rather than the instance -- the file on
disk can no longer drift from the case it claims to be, which is what `plumes2.experiments` exists
for (PLAN section 7b).

What went wrong, 2026-08-25, and what changed here:

* **`surface_stop_pair_v2`** asked for a *pair* of runs in one note, with the varying step buried
  in prose ("the one thing that varies: stop plume at surface hit -- see the procedure below").
  Run A (box ticked) came back on 2026-08-24; the 2026-08-25 attempt came back **as run A again**,
  because the box is ticked when the project opens and nothing in the note said, in the one place
  the operator was looking, to untick it. The regenerated note asks for **one run** and says
  untick in the settings list, where every other GUI instruction lives.
  ⛔ The generated `.prj` was also **truncated by the exe** -- 154 lines to 109, losing the whole
  output-selection tail (the 13 near-field and 6 far-field plot variables, the output filename and
  the flags) -- so the file on disk is not loadable and has to be rewritten regardless.
* **`style_enumeration`** asked for "one run per remaining option" without anyone having ever
  seen the dialog. The regenerated note makes step 1 a **reconnaissance step that costs no run**:
  write down what the control offers and which entry is selected. A list of options nobody can
  enumerate is not an experiment.

⭐ **And both notes now ask which exe build produced the run**, because 2026-08-25 showed the
answer is not constant: the same project, same box, same near field **bit-identical over 275
steps x 13 columns**, came back with a wastefield width of 109.59 m in August and **96.29 m**
yesterday -- `cos 30` exactly, the legacy arm of ledger row 275. The build is not recorded in any
file we hold, and it changes the far field.

Run from the repository root::

    .venv/Scripts/python studies/pending_experiments.py

⚠️⚠️ **Both experiments have since been run and graduated** -- to
`reference_cases/case46_surface_stop_flag` and `reference_cases/case48_similarity_profiles`
(2026-08-25). This module is kept because it is the *provenance* of those two cases: it says what
was asked, in what order, and with which predictions registered. Re-running it recreates the
pending directories from scratch, which is what you want only if a case needs re-running from its
original starting state.
"""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

from plumes2.config import Case
from plumes2.experiments import Experiment, write_experiment
from plumes2.io.project import load_project

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"

#: The build question, asked identically in both notes. Not a setting -- an observation to record.
BUILD_NOTE = (
    "WHICH EXE BUILD did this run: the far-field header's wastefield width says which arm of "
    "ledger row 275 you are on, but only after the fact -- write down which executable was "
    "launched, and from where. The 2026-08-25 rerun of surface_stop_pair_v2 came back with a "
    "near field bit-identical to August's over 275 steps and a wastefield width of 96.29 m "
    "against 109.59 m, which is the cos-30 legacy arm. Nothing in the .prj or the .dat records "
    "which binary ran."
)


def _case_from(path: Path, *, from_git_head: bool = False) -> Case:
    """The case a pending project describes.

    `from_git_head` reads the committed copy instead of the working one -- needed for
    `surface_stop_pair_v2.prj`, which the exe truncated on disk (see the module docstring) and
    which therefore no longer parses.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if from_git_head:
            relative = path.relative_to(ROOT).as_posix()
            blob = subprocess.run(
                ["git", "show", f"HEAD:{relative}"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            scratch = path.with_suffix(".prj.head")
            scratch.write_bytes(blob)
            try:
                return load_project(scratch, warn_on_drift=False).to_case()
            finally:
                scratch.unlink()
        return load_project(path, warn_on_drift=False).to_case()


def surface_stop_pair_v2() -> Experiment:
    """Run B of the pair: the same geometry with the surface-stop box **unticked**."""
    case = _case_from(
        PENDING / "surface_stop_pair_v2" / "surface_stop_pair_v2.prj", from_git_head=True
    )
    return Experiment(
        name="surface_stop_pair_v2",
        case=case,
        question=(
            "Is nearfield_flags[1] the stop-at-surface checkbox? Run A (box TICKED) is already in "
            "this directory as surface_ON.dat/.prj -- it stops on `Plume surfaces` at step 275 "
            "with flags[1] = 1. This experiment is RUN B ONLY: the identical case with the box "
            "UNTICKED. If the flag is the box, run B comes back flags[1] = 0 and runs past the "
            "surface; if it comes back 1 again, the flag is something else and PLAN 8e debt 3 "
            "stays open."
        ),
        predictions={
            "nearfield_flags[1] in the as-run .prj": (
                "0. This is the whole question -- run A came back 1 with the box ticked, so a 0 "
                "here identifies the field and a second 1 refutes it"
            ),
            "where the near field stops": (
                "it does NOT stop at the surface: the `Plume surfaces` banner still prints around "
                "step 275, and the run continues to roughly step 476 on `Plume traps`, the way "
                "case31's surface_off did (572 rows there, on a longer interval). Registered "
                "2026-08-24, before run A came back"
            ),
            "the first 275 steps": (
                "bit-identical to surface_ON.dat on every shared step and column -- the box "
                "changes where the run STOPS, not what it computes. If these differ, the box "
                "is doing something to the physics, a bigger finding than the flag"
            ),
            "final dilution": (
                "higher than run A's 169.754, because the plume goes on entraining past the "
                "surface. case31's unticked run reached 246.607 on the same geometry"
            ),
        },
        settings=(
            "all output columns",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked",
            "⭐⭐ stop plume at surface hit: **UNTICK IT**. It is TICKED when the project opens "
            "and unticking it is the entire experiment -- if it is still ticked when you press "
            "run, the result is a duplicate of surface_ON.dat and settles nothing (this is what "
            "happened on 2026-08-25)",
        ),
        notes=(
            "ONE run. Everything else in this directory is already answered.",
            "Afterwards, copy the trace to `surface_OFF.dat` and the project to "
            "`surface_OFF.prj` -- both, before anything else is run, because the exe overwrites "
            "the trace and rewrites the project on every run.",
            "⛔ Do NOT run this from `surface_ON.prj`. That is August's as-run file; running from "
            "it is what produced the 2026-08-25 duplicate. Open `surface_stop_pair_v2.prj`, which "
            "this script has just rewritten -- the previous copy on disk was truncated by the exe "
            "from 154 lines to 109 and will not load.",
            BUILD_NOTE,
        ),
    )


def style_enumeration() -> Experiment:
    """Enumerate the exe's cross-plume distribution-style options. Reconnaissance first."""
    case = _case_from(PENDING / "style_enumeration" / "style_enumeration.prj")
    return Experiment(
        name="style_enumeration",
        case=case,
        question=(
            "What does each of the exe's three similarity-profile options do to the centreline? "
            "The options are now known (operator, 2026-08-25): **Default Profile** (selected on "
            "open), **3/2 Power law Profile**, **Gaussian Profile**. The default is measured -- "
            "style_default.dat gives Dilutn / CL-Dil = 2.0000 flat over 410 rows, the parabola. "
            "TWO RUNS REMAIN, one per unselected option. This gates PLAN 8.4, and 8.4 gates the "
            "dose study's headline, because Omega_brucite's risk window is a centreline quantity "
            "and the centreline is what a profile choice moves."
        ),
        predictions={
            "**3/2 Power law Profile** -> Dilutn / CL-Dil": (
                "**3.8889** unmerged -- the exact reciprocal of the area-average of "
                "`[1 - u^1.5]^2`, which is the profile the 3rd edition derives its own 3.89 from "
                "(PLAN 6b). If this option reads 3.889 the control is real, and the exe defaults "
                "away from the profile its own manual documents"
            ),
            "**Gaussian Profile** -> Dilutn / CL-Dil": (
                "the value identifies WHICH Gaussian, and that is the point of running it. A "
                "Gaussian truncated at the plume radius has no single peak-to-mean: `exp(-u^2)` "
                "gives **1.582**, `exp(-2u^2)` gives **2.313** (PLAN 6b's candidate), "
                "`exp(-3u^2)` gives **3.157**. Whatever it prints pins the decay constant"
            ),
            "if both come back 2.0000 anyway": (
                "the control is inert -- present in the dialog and not reaching CL-Dil. That is a "
                "finding in its own right, a user-facing option that does nothing, and it leaves "
                "PLAN 8.4's parabola standing unconditionally"
            ),
            "the direction, because the first issue of this note had it upside down": (
                "report **Dilutn / CL-Dil**, flux-average over centreline. The centreline is the "
                "LESS diluted of the pair, so the ratio is >= 1. CL-Dil / Dilutn reads 0.5000 and "
                "is the same measurement inverted"
            ),
            "merging": (
                "this geometry never merges -- the trace prints `Plumes not merged` -- so only "
                "the unmerged column above is testable here. The merged values would be 2.2222 "
                "for 3/2-power, 1.5000 parabolic and 1.6718 for exp(-2u^2)"
            ),
        },
        settings=(
            "⭐ the **similarity profile** selector -- enumerated 2026-08-25, and it offers "
            "exactly three: `Default Profile` (selected on open), `3/2 Power law Profile`, "
            "`Gaussian Profile`. Run the two that are not the default, one run each",
            "all output columns",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked",
            "leave stop-plume-at-surface AS YOU FIND IT and say which way it was -- it writes "
            "into nearfield_flags[1] and belongs to surface_stop_pair_v2, not to this experiment",
        ),
        notes=(
            "TWO runs, independent, either order. For each: select the option, run, then copy "
            "the trace to `style_threehalves.dat` or `style_gaussian.dat` and the project to "
            "`asrun_style_<same>.prj` BEFORE the next run, which overwrites both.",
            "⭐⭐ **Why this matters more than it looks.** PLAN 8.4 has been sitting on whether to "
            "move the port from the exe-matching parabola to the Gaussian the jet-and-plume "
            "literature favours for scalars, and the assumed cost of that move was LEAVING "
            "PARITY. If `Gaussian Profile` is a real setting there is no such cost: the port can "
            "be Gaussian and still reproduce a run the exe can produce. That is the single thing "
            "most likely to move the dose study's headline number.",
            "✅ The default option is already done: `style_default.dat` and "
            "`asrun_style_default.prj` are in this directory from 2026-08-24 and give 2.0000. Do "
            "not re-run it.",
            "The output interval is already 1 in the file and needs no typing.",
            BUILD_NOTE,
        ),
    )


def main() -> None:
    for build in (surface_stop_pair_v2, style_enumeration):
        experiment = build()
        written = write_experiment(experiment, PENDING)
        print(written)
        for path in sorted(written.iterdir()):
            print("   ", path.name)


if __name__ == "__main__":
    main()
