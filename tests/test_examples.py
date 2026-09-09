"""The examples/ folder, executed -- the same discipline test_docs applies to the docstring.

An example that is not run by the suite is a doc that rots: the landing page's own worked
example named a column that did not exist when first written (test_docs), and examples/ is
the first code a library-consuming collaborator will run.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from plumes2 import ambient_from_files
from plumes2.config import AmbientChemistryLevel, AmbientLevel

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_ambient_from_files_reads_the_example_tables() -> None:
    """The example CSVs parse into validated sections, blank/omitted fields defaulting."""
    profile = ambient_from_files(
        EXAMPLES / "ambient_levels.csv",
        chemistry=EXAMPLES / "ambient_chemistry.csv",
    )
    assert isinstance(profile.levels[0], AmbientLevel)
    assert profile.max_depth == 12.0
    assert profile.has_chemistry
    first = profile.chemistry[0]
    assert isinstance(first, AmbientChemistryLevel)
    assert first.ph is None  # column omitted entirely -> None, never 0.0 (case03's rule)


def test_unknown_column_is_fatal_and_names_the_valid_ones(tmp_path: Path) -> None:
    """A misspelled header would silently discard measured data, so it must refuse.

    `temprature` is the motivating case: accepted quietly, every level would sit at the
    20 degC default and the case would still run.
    """
    bad = tmp_path / "levels.csv"
    bad.write_text("depth,temprature\n0.0,12.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="temprature") as excinfo:
        ambient_from_files(bad)
    assert "temperature" in str(excinfo.value)  # the fix is in the message


@pytest.mark.slow
def test_run_from_files_executes() -> None:
    """`examples/run_from_files.py`, top to bottom, exactly as a collaborator would run it."""
    runpy.run_path(str(EXAMPLES / "run_from_files.py"), run_name="__main__")


@pytest.mark.slow
def test_run_macoma_reproduces_the_dose_study_row() -> None:
    """`examples/run_macoma.py` executes, and its case IS the study's TA 6000 cell.

    The example claims its output "reproduces the study's TA 6000 row exactly", which is only
    true while its hand-typed diffuser/effluent stay equal to `ebb_macoma_default.yaml` at
    that dose -- so the equality is asserted, not trusted. `pollutant` differs knowingly (the
    YAML carries case03's tracer; the example omits it) and pollutant does not feed chemistry
    or dynamics, so it is excluded from the comparison.
    """
    study_yaml = EXAMPLES.parent / "studies" / "ebb_dose_study" / "ebb_macoma_default.yaml"
    if not study_yaml.exists():
        pytest.skip(
            "the dose study is not in this checkout (it is withheld from the public export)"
        )
    macoma = runpy.run_path(str(EXAMPLES / "run_macoma.py"), run_name="__main__")

    from plumes2 import load_case
    from plumes2.sweep import with_updated

    study = load_case(study_yaml)
    study = with_updated(study, "effluent_chemistry.total_alkalinity", 6000.0)
    example = macoma["build_case"]()
    for section in ("diffuser", "mixing_zone", "ambient", "effluent_chemistry"):
        assert getattr(example, section) == getattr(study, section), section
    assert example.effluent.model_dump(exclude={"pollutant"}) == pytest.approx(
        study.effluent.model_dump(exclude={"pollutant"}), rel=1e-4
    )
    assert example.near_field.max_rise_or_fall == study.near_field.max_rise_or_fall
