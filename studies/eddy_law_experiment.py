"""Generate the `eddy_law_*` exe experiments: decode the far-field eddy-diffusivity selector.

The exe's far-field dialog offers three eddy-diffusivity laws -- `Constant Eddy Diffusivity`,
`Linearly varying eddy diffusivity`, `4/3 power law based eddy diffusivity` (the default, operator
2026-08-26) -- and every one of the 54 archived projects with a far field reads the same seven
far-field flags, `1,0,0,1,1,1,0`, with every far-field header saying `4/3 Power Law`. So which
`.prj` position encodes the selection, and what the header prints for the other two, has never
been observed (case49 README; `io/prj.py`'s `farfield_flags` docstring). Two runs of one project
settle it: the same case under `Constant` and under `Linearly varying`, everything else as loaded.

Ebb's default profile (case03's configuration, `studies/ebb_dose_study.py`) is the base,
without chemistry -- the far field is what is being read, and a chemistry-free run needs nothing
typed into the carbonate dialog. The predictions below come from the port's own Brooks
implementation (`farfield.brooks`, confirmed to 5e-4 against the exe's standalone calculator on
the 4/3 law, ledger row 119): the near field is predicted **bit-identical** to case03's archived
interval-1 trace, and the far-field dilution at 100 m and at the 500 m stop is predicted per law.

Run from the repository root::

    .venv/Scripts/python studies/eddy_law_experiment.py

Writes `reference_cases/pending/eddy_law_constant/` and `reference_cases/pending/eddy_law_linear/`.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

from plumes2.config import Case, EddyDiffusivityLaw
from plumes2.experiments import EDDY_LAW_GUI_LABEL, Experiment, write_experiment
from plumes2.results import run

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"
sys.path.insert(0, str(ROOT / "studies"))

from ebb_dose_study import ebb_default_case  # noqa: E402

#: Distances the far-field dilution is predicted at, m from the diffuser.
STATIONS = (100.0, 200.0, 500.0)

BUILD_NOTE = (
    "WHICH EXE BUILD did this run: write down which executable was launched, and from where. "
    "Nothing in the .prj or the .dat records it (ledger row 275)."
)


def base_case(law: EddyDiffusivityLaw) -> Case:
    """Ebb's default profile without chemistry, with the far-field law set in the case."""
    case = ebb_default_case()
    case = case.model_copy(
        update={
            "effluent_chemistry": None,
            # No ambient chemistry either: a chemistry-free run writes no side table, so the
            # operator has nothing to load and the note's "carbonate off" is the whole story.
            "ambient": case.ambient.model_copy(update={"chemistry": []}),
            "far_field": case.far_field.model_copy(update={"law": law}),
            "near_field": case.near_field.model_copy(update={"output_interval": 1}),
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Case.model_validate(case.model_dump())


def farfield_predictions(law: EddyDiffusivityLaw) -> dict[str, str]:
    """Our Brooks far field under `law`, and under the default for contrast, at the stations."""
    out: dict[str, str] = {}
    frames = {}
    for candidate in (law, EddyDiffusivityLaw.FOUR_THIRDS):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = run(base_case(candidate), samples=200)
        assert results.farfield is not None
        frames[candidate] = results.farfield
    ours = frames[law]
    reference = frames[EddyDiffusivityLaw.FOUR_THIRDS]
    x = ours["distance_m"].to_numpy(np.float64)
    for station in STATIONS:
        d_law = float(np.interp(station, x, ours["dilution"].to_numpy(np.float64)))
        d_ref = float(
            np.interp(
                station,
                reference["distance_m"].to_numpy(np.float64),
                reference["dilution"].to_numpy(np.float64),
            )
        )
        w_law = float(np.interp(station, x, ours["width_m"].to_numpy(np.float64)))
        out[f"far-field `Dilution` at {station:g} m"] = (
            f"**{d_law:.1f}** under this law (the 4/3 default gives {d_ref:.1f} on the same near "
            "field); the port's Brooks is confirmed to 5e-4 against the exe's own standalone "
            "calculator on the 4/3 law (row 119), so a match here also confirms the other law's "
            "implementation"
        )
        out[f"far-field `Width` at {station:g} m"] = f"{w_law:.2f} m"
    out["far-field first row"] = (
        f"dilution {float(ours['dilution'].iloc[0]):.3f} at {x[0]:.3f} m -- the near-field end, "
        "identical under every law"
    )
    return out


def main() -> None:
    PENDING.mkdir(parents=True, exist_ok=True)
    for law in (EddyDiffusivityLaw.CONSTANT, EddyDiffusivityLaw.LINEAR):
        case = base_case(law)
        label = EDDY_LAW_GUI_LABEL[law]
        name = f"eddy_law_{law.value}"
        predictions = {
            "near field, every column": (
                "bit-identical to case03's interval-1 trace "
                "(`case03_carbonate/kso4_option3.dat`, hydrodynamic columns) -- the law is "
                "a far-field input and nothing upstream of the transition reads it"
            ),
            "the seven far-field flags in the as-run `.prj`": (
                "**one position changes** from the archive's `1,0,0,1,1,1,0`. Position 4 "
                "(1-indexed) is the standing guess for the law; whichever position moves, and to "
                "what, is the decoding this run exists for"
            ),
            "the far-field header's law line": (
                "prints something other than `4/3 Power Law` -- record the exact string; the "
                "reader (`io/dat.py`) stores it as `eddy_diffusivity_law` and has only ever seen "
                "one value"
            ),
            **farfield_predictions(law),
        }
        experiment = Experiment(
            name=name,
            case=case,
            question=(
                f"Which `.prj` flag encodes the far-field eddy-diffusivity selector, what does the "
                f"header print for `{label}`, and does the exe's {label.split(' eddy')[0].lower()} "
                "law match the port's?"
            ),
            predictions=predictions,
            settings=(
                "all output columns",
                "No. of maximum plume rise or fall = 3",
                "stop plume at bottom hit: ticked",
                "stop plume at surface hit: **leave as loaded** -- do not untick by habit",
                f"**far-field eddy diffusivity: select `{label}`** -- the selector opens on the "
                "4/3 law; this run exists to see what selecting another option does",
                "carbonate module: **off** -- nothing to type in the chemistry dialog for this run",
            ),
            notes=(
                "Ebb's default profile (case03's configuration) without chemistry, interval 1.",
                f"Copy the trace aside as `{name}.dat` and the rewritten project as "
                f"`asrun_{name}.prj` before any further run.",
                "One run per note, one law per run. The sibling directory asks for the other "
                "non-default law on the same project.",
                BUILD_NOTE,
            ),
        )
        target = write_experiment(experiment, PENDING)
        print(f"wrote {target}")


if __name__ == "__main__":
    main()
