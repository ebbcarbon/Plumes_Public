"""Ebb's default profile, as `studies/ebb_dose_study.py` writes it -- the study's one input, pinned.

The operator's answer on 2026-08-26 was that Ebb's default profile *is* the Macoma configuration
already in the archive. The two things the study adds to case03 -- an ambient chemistry profile
that reaches the seabed, and an effluent specified as TA at the intake's DIC -- are exactly the
two inputs PLAN 8f listed as missing, so they are asserted here rather than left to the script.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

from plumes2.config import Case
from plumes2.io import load_case, load_project
from tests.conftest import REFERENCE_CASES, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "studies"))

from ebb_dose_study import (
    DEFAULT_YAML,
    INTAKE_DIC,
    SEABED,
    ebb_default_case,
)


@pytest.fixture(scope="module")
def default() -> Case:
    return ebb_default_case()


def test_the_default_is_case03_with_the_spacing_corrected(default: Case) -> None:
    """case03's hydrodynamics with exactly one deliberate difference: the port spacing.

    The site's ports sit at 2 ft; case03's 2026 project carries 2 m -- "2.0" entered with the
    wrong unit (operator, 2026-09-01; the Dec-2025 project stored 2.0 under the feet flag,
    row 49). The archive stays as entered; the study corrects the one field, and this test
    holds the correction to that one field.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case03 = load_project(
            REFERENCE_CASES / "case03_macoma_carbonate" / "test.prj", warn_on_drift=False
        ).to_case()
    for section in ("effluent", "mixing_zone", "near_field", "far_field", "carbonate"):
        assert getattr(default, section) == getattr(case03, section), section
    assert default.diffuser.port_spacing == 0.6096  # 2 ft, the correction
    assert case03.diffuser.port_spacing == 2.0  # the archive, untouched, as entered
    assert default.diffuser.model_dump(exclude={"port_spacing"}) == case03.diffuser.model_dump(
        exclude={"port_spacing"}
    )
    assert default.ambient.levels == case03.ambient.levels
    assert default.diffuser.bottom_depth == SEABED


def test_the_ambient_chemistry_reaches_the_seabed(default: Case) -> None:
    """The input PLAN 8f said was missing. Held from the deepest measured row, and said so."""
    chemistry = default.ambient.chemistry
    assert chemistry[-1].depth >= default.diffuser.bottom_depth
    measured = [level for level in chemistry if level.depth <= 4.0]
    held = [level for level in chemistry if level.depth > 4.0]
    assert len(measured) == 4 and len(held) >= 1
    for level in held:
        assert level.total_alkalinity == measured[-1].total_alkalinity
        assert level.dic == measured[-1].dic
    assert "held" in default.description


def test_the_effluent_is_ta_at_the_intake_dic(default: Case) -> None:
    """Ebb's specification: (TA, DIC), never TA at a held pH -- PLAN 8f finding 1."""
    assert default.effluent_chemistry is not None
    assert default.effluent_chemistry.dic == INTAKE_DIC
    assert default.effluent_chemistry.ph is None
    assert default.chemistry_enabled


def test_a_port_anywhere_in_the_water_column_now_validates(default: Case) -> None:
    """The dry run's depth probe failed at 5 and 11 m because the chemistry stopped at 4 m."""
    for depth in (2.0, 5.0, 11.0, 16.0):
        diffuser = default.diffuser.model_copy(
            update={"port_depth": depth, "port_elevation": SEABED - depth}
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Case.model_validate(default.model_copy(update={"diffuser": diffuser}).model_dump())


@pytest.mark.slow
def test_a_five_metre_port_runs_with_chemistry(default: Case) -> None:
    """The study's first run failed every 5 m cell on a one-ULP dilution of 0.9999999999999999.

    The dense output's mass ratio at t = 0 is 1 within rounding, and `chem.transport.mix` rightly
    refuses a dilution below 1 -- so `NearFieldSolution.sample` now floors it. Every other depth
    happened to land on exactly 1.0, which is why nothing had ever tripped it.
    """
    from plumes2.results import run

    diffuser = default.diffuser.model_copy(
        update={"port_depth": 5.0, "port_elevation": SEABED - 5.0}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case = Case.model_validate(default.model_copy(update={"diffuser": diffuser}).model_dump())
        results = run(case, samples=200)
    assert results.has_chemistry
    assert float(results.nearfield["dilution"].min()) == 1.0
    assert float(results.nearfield["dilution"].iloc[0]) == 1.0


def test_the_written_yaml_is_the_same_case() -> None:
    """The file the study writes is what a reader will open; it must be the case the tests saw."""
    if not Path(DEFAULT_YAML).exists():
        pytest.skip("studies/ebb_dose_study.py has not been run in this checkout")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        written = load_case(DEFAULT_YAML)
    assert written == ebb_default_case()
