"""Generate the flag-decode suite: nine projects that settle the undecoded `.prj` flags.

Two open items from PLAN §6, answered by designed runs rather than archaeology (operator,
2026-09-01):

* **The undecoded flag positions.** Every archived project reads the same constants at the
  unknown positions -- near-field ``[1, ?, 0, ?, 1, 1]`` (positions 1, 3, 5, 6 unknown,
  1-indexed; position 2 is the surface-stop box per case46, position 4 the rise/fall count)
  and far-field ``[1, ?, ?, ?, 1, 1, 0]`` (positions 1, 5, 6, 7 unknown; 2/3/4 are the eddy-law
  one-hot per case50). Nothing varying means nothing decodable from the archive, so each arm
  here flips exactly **one** unknown flag in an otherwise identical project. The read-out is
  cheap and comes *before* the run: open the project, and whichever GUI control differs from
  the base arm is what the flag carries. The run then shows whether the control does anything
  on this trajectory, and the as-run `.prj` shows whether the exe preserves or rewrites the bit.
* **Which exe build is in hand** (the case42-45 attribution, redirected). The base geometry is
  the upstream example -- discharge 30 degrees off the current -- so every arm's far-field
  **wastefield width is a build fingerprint** on its own: ``17 x 6.10 x cos30 + diameter``
  (~96-98 m) on the current build, ``17 x 6.10 + diameter`` (~110-112 m) on the legacy one
  (ledger row 275, case13/case14/case45). No run from this suite can come back build-anonymous.

Run from the repository root::

    .venv/Scripts/python studies/flag_decode_experiments.py

writes ``reference_cases/pending/flagdecode_*``. Chemistry and DO are stripped from the base
case on purpose: they are GUI-only state that costs typing on every one of nine runs and has
no bearing on a flag's identity.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from plumes2.config import AmbientProfile
from plumes2.experiments import Experiment, write_experiment
from plumes2.io import load_case, read_prj
from plumes2.io.prj import write_prj
from plumes2.sweep import with_updated

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"
BASE_CASE = ROOT / "studies" / "example_case.yaml"

#: (arm name, PrjFile attribute, 0-indexed position) -- one unknown flag each, `None` = base.
#: Names carry the 1-indexed position the docs use ("nf3" = near-field flags position 3).
FLIPS: tuple[tuple[str, str | None, int | None], ...] = (
    ("flagdecode_base", None, None),
    ("flagdecode_nf1", "nearfield_flags", 0),
    ("flagdecode_nf3", "nearfield_flags", 2),
    ("flagdecode_nf5", "nearfield_flags", 4),
    ("flagdecode_nf6", "nearfield_flags", 5),
    ("flagdecode_ff1", "farfield_flags", 0),
    ("flagdecode_ff5", "farfield_flags", 4),
    ("flagdecode_ff6", "farfield_flags", 5),
    ("flagdecode_ff7", "farfield_flags", 6),
)

#: The reconnaissance step, identical in every arm -- it is the primary observable and costs
#: no run.
RECON = (
    "RECONNAISSANCE FIRST, before running: open the project and write down the state of every "
    "control on the model-settings and far-field dialogs (the three stop boxes, the rise/fall "
    "count, the eddy-diffusivity selector, and any checkbox not yet in that list). Compare "
    "against `flagdecode_base` opened the same way: the flipped flag should show as EXACTLY ONE "
    "changed control. Name it. If nothing visible changed, that is also an answer -- the flag "
    "is not a dialog control, and the as-run `.prj` will say whether the exe preserves the bit "
    "or rewrites it."
)

BUILD = (
    "WHICH EXE BUILD: record which executable was launched and from where. The far-field "
    "header's wastefield width is the fingerprint regardless -- ~96-98 m is the current build "
    "(the cosine, row 275), ~110-112 m the legacy one. This suite doubles as the build "
    "discriminator PLAN section 6 used to ask for on case42-45: any future far-field run at "
    "this 30-degree offset identifies its own build."
)


def base_predictions() -> dict[str, str]:
    return {
        "wastefield width (build fingerprint)": (
            "17 x 6.10 x cos30 + final diameter = ~96-98 m on the current build; "
            "17 x 6.10 + final diameter = ~110-112 m on legacy (row 275; case13 measured "
            "96.29 m with chemistry on, case14 97.60 m without)"
        ),
        "near field": (
            "the upstream example's trajectory: surfaces near step 275; with rise/fall = 3 the "
            "run continues past it (case14 reached 476 steps)"
        ),
        "as-run flags": (
            "near-field [1, 1, 0, 3, 1, 1] and far-field [1, 0, 0, 1, 1, 1, 0] -- the archive's "
            "constants with the 4/3 law selected"
        ),
    }


def flip_predictions(block: str, position_1idx: int, before: int, after: int) -> dict[str, str]:
    where = "near-field" if block == "nearfield_flags" else "far-field"
    guesses = {
        ("nearfield_flags", 1): "a stop box is the natural candidate (bottom hit is ticked by "
        "default and position 2 is already the surface box, case46)",
        ("nearfield_flags", 3): "the shoreline checkbox is the natural candidate (0 in every "
        "archived project, and the box has never been saved ticked)",
        ("nearfield_flags", 5): "unknown -- no candidate",
        ("nearfield_flags", 6): "unknown -- no candidate",
        ("farfield_flags", 1): "unknown -- constant 1 in every archived project",
        ("farfield_flags", 5): "unknown -- constant 1 in every archived project",
        ("farfield_flags", 6): "unknown -- constant 1 in every archived project",
        ("farfield_flags", 7): "unknown -- constant 0 in every archived project",
    }[(block, position_1idx)]
    return {
        f"{where} flag {position_1idx} ({before} -> {after})": guesses,
        "GUI on load": (
            "exactly one control differs from flagdecode_base, or none (then the flag is not "
            "a dialog control)"
        ),
        "as-run flag value": (
            f"{after} if the flag is a control the exe respects and saves; {before} if the exe "
            "rewrites it from session state on run (either way the bit's ownership is decided)"
        ),
        "trace vs flagdecode_base": (
            "bit-identical unless the control gates an event that binds on this trajectory -- "
            "the plume surfaces (~step 275) and never hits bottom or shoreline, so a surface-"
            "gating control shows as truncation and a bottom/shoreline one shows as nothing"
        ),
    }


def main() -> None:
    case = load_case(BASE_CASE)
    # Strip GUI-only chemistry/DO (nothing to decode there, and it costs typing on nine runs);
    # pin rise/fall = 3 so the standing settings instruction and the .prj agree.
    case = case.model_copy(
        update={"ambient": AmbientProfile(levels=case.ambient.levels), "effluent_do": None}
    )
    case = with_updated(case, "near_field.max_rise_or_fall", 3)

    for name, block, index in FLIPS:
        if block is None:
            question = (
                "The reference arm: the unflipped project every flagdecode arm is compared "
                "against, and the build fingerprint for whichever exe runs it."
            )
            predictions = base_predictions()
        else:
            position = index + 1  # type: ignore[operator]  # flips always carry an index
            question = (
                f"Which GUI control does `.prj` {block} position {position} (1-indexed; python "
                f"[{index}]) carry? Undecoded in PLAN section 6; constant in every archived "
                "project, flipped here and nowhere else."
            )
            predictions = {}  # filled after the base value is read off the written file
        experiment = Experiment(
            name=name,
            case=case,
            question=question,
            predictions=predictions,
            notes=(RECON, BUILD) if block else (BUILD,),
        )
        target = write_experiment(experiment, PENDING)
        if block is None:
            continue
        # Flip the one flag on the written file, then regenerate the note with the real
        # before/after values so the prediction table cannot disagree with the bytes.
        prj_path = target / f"{name}.prj"
        prj = read_prj(prj_path)
        flags = list(getattr(prj, block))
        before = flags[index]
        flags[index] = 1 - before
        write_prj(dataclasses.replace(prj, **{block: flags}), prj_path)
        experiment = dataclasses.replace(
            experiment,
            predictions=flip_predictions(block, index + 1, before, 1 - before),
        )
        write_experiment(experiment, PENDING)  # rewrites README.md and CSVs, not the .prj
        write_prj(dataclasses.replace(prj, **{block: flags}), prj_path)  # re-apply the flip
        print(f"{name}: {block}[{index}] {before} -> {1 - before}")
    print(f"wrote {len(FLIPS)} experiments under {PENDING}")


if __name__ == "__main__":
    main()
