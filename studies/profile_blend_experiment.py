"""Generate the `profile_merged_*` exe experiments: the similarity profile on a **merging** plume.

case48 (2026-08-25) enumerated the exe's three similarity profiles on case03's geometry, which never
merges, so it measured each option's **round** peak-to-mean and nothing else. The port now carries
all three (`crossplume.SimilarityProfile`, PLAN 8.4's rework, 2026-08-26) and, for the two
non-default options, *assumes* the exe walks from the round anchor to the slab anchor by the same
linear law it uses for the parabola:

    peak/mean = max( slab,  round + (round - slab) * (1 - d/L) )          (d = P-dia, L = spacing)

That is the one thing the rework could not measure, and it is what these runs settle. The base is
**case44's 0.60 m arm** (`spacing_0p6m.prj`, test79): 25 x 0.0127 m ports, 0.005 m3/s, 35 psu, 65
degree diffuser, interval 1 -- it merges at a dilution of ~70 and reaches `d/L` 4.95, so both
anchors and the whole walk between them sit inside one trace. test79 is the default-profile arm and
is already archived, so the experiment is two runs of the same project: one under `3/2 Power law
Profile`, one under `Gaussian Profile`. The trajectory (`Dilutn`, `P-dia`) is predicted
**bit-identical** to test79 on every row; only `CL-Dil` moves.

⚠️ The 65 degree bearing means the merge banner fires at an *effective* spacing (`d/L` ~ 0.93) while
the law runs on nominal `L`, so the parabola's ratio overshoots 2.0 at the banner and ramps into the
line (PLAN 6b). Whether the other two profiles overshoot and ramp the same way is a second thing
these runs show; the predictions below state the law they will be scored against, not the ramp.

Run from the repository root::

    .venv/Scripts/python studies/profile_blend_experiment.py

Writes `reference_cases/pending/profile_merged_three_halves/` and
`reference_cases/pending/profile_merged_gaussian/`.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from plumes2.config import Case
from plumes2.crossplume import SimilarityProfile, peak_to_mean_round, peak_to_mean_slab
from plumes2.experiments import Experiment, write_experiment
from plumes2.io import load_project

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reference_cases" / "case44_spacing_sweep" / "spacing_0p6m.prj"
PENDING = ROOT / "reference_cases" / "pending"

#: The GUI label of each option, as case48 recorded the selector.
GUI_LABEL = {
    SimilarityProfile.THREE_HALVES: "3/2 Power law Profile",
    SimilarityProfile.EXE_GAUSSIAN: "Gaussian Profile",
}

#: What case48 measured for each option's round plateau, and the closed form of its slab anchor.
MEASURED_ROUND = {
    SimilarityProfile.THREE_HALVES: "3.88997",
    SimilarityProfile.EXE_GAUSSIAN: "3.66998",
}
SLAB_FORM = {
    SimilarityProfile.THREE_HALVES: "20/9",
    SimilarityProfile.EXE_GAUSSIAN: "2 sqrt(k) / (sqrt(pi) erf(sqrt(k)))",
}

BUILD_NOTE = (
    "WHICH EXE BUILD did this run: write down which executable was launched, and from where. "
    "Nothing in the .prj or the .dat records it, and the two builds print different wastefield "
    "widths for the same project (ledger row 275). test79 was a legacy-build run."
)


def base_case(profile: SimilarityProfile) -> Case:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case = load_project(BASE, warn_on_drift=False).to_case()
    # The profile is GUI session state the .prj cannot carry; it goes in the case so the note,
    # the provenance digest and any later comparison all say which option this run was under.
    case = case.model_copy(
        update={"near_field": case.near_field.model_copy(update={"similarity_profile": profile})}
    )
    return Case.model_validate(case.model_dump())


def predictions(profile: SimilarityProfile, spacing: float) -> dict[str, str]:
    round_value = peak_to_mean_round(profile)
    slab_value = peak_to_mean_slab(profile)
    law = f"max({slab_value:.4f}, {round_value:.4f} + {round_value - slab_value:.4f} * (1 - d/L))"
    return {
        "`Dilutn` and `P-dia`, every row": (
            "bit-identical to case44's test79 (the profile is post-processing; case48's three "
            "traces shared one `Dilutn` column)"
        ),
        "`Dilutn / CL-Dil` before the merge banner, developed rows (`Dilutn` > 5)": (
            f"{round_value:.4f}, flat to five figures (case48 measured {MEASURED_ROUND[profile]} "
            "on the unmerged case03 geometry)"
        ),
        f"`Dilutn / CL-Dil` once `P-dia` >= 2 x {spacing:g} m (deep slab)": (
            f"{slab_value:.4f} -- the profile's own slab integral ({SLAB_FORM[profile]})"
        ),
        f"`Dilutn / CL-Dil` for {spacing:g} < `P-dia` < {2 * spacing:g} m": (
            f"**the assumption under test**: {law}, the parabola's linear walk applied between "
            "this profile's anchors. Alternatives to look for: no blend at all (flat at the round "
            "value), or a geometric blend that is not a straight line in d/L"
        ),
        "the banner row and the rows after it": (
            "the parabola overshoots 2.0 at the banner on this oblique diffuser and ramps into the "
            "line over a few rows (PLAN 6b); whether this profile shows the same overshoot/ramp "
            "shape is unmeasured -- record it either way"
        ),
    }


def main() -> None:
    PENDING.mkdir(parents=True, exist_ok=True)
    for profile, label in GUI_LABEL.items():
        case = base_case(profile)
        spacing = case.diffuser.port_spacing
        name = f"profile_merged_{profile.value.removeprefix('exe_')}"
        experiment = Experiment(
            name=name,
            case=case,
            question=(
                f"How does the exe walk its `{label}` from round to slab as neighbouring plumes "
                "merge -- and is it the same linear law in d/L the default parabola uses?"
            ),
            predictions=predictions(profile, spacing),
            settings=(
                "all output columns (Centerline-Dilution and Plume-Diameter are the two that "
                "matter)",
                "No. of maximum plume rise or fall = 3",
                "stop plume at bottom hit: ticked",
                f"**Similarity profile: select `{label}`** -- the selector opens on `Default "
                "Profile` every time (case48); check it before pressing run",
            ),
            notes=(
                "This is case44's `spacing_0p6m.prj` regenerated from the case, so the .prj here "
                "should load identically; test79 in case44 is the default-profile arm and is the "
                "control -- no default-profile rerun is needed unless the build differs.",
                f"Copy the trace aside as `{name}.dat` before any further run.",
                "One run per note, one option per run. The sibling directory asks for the other "
                "option on the same project.",
                BUILD_NOTE,
            ),
        )
        target = write_experiment(experiment, PENDING)
        print(f"wrote {target}")


if __name__ == "__main__":
    main()
