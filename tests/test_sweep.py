"""The sweep harness (PLAN Phase 8.3): axes in, one honest row per cell out."""

from __future__ import annotations

import warnings

import pytest

from plumes2.config import GeometryWarning
from plumes2.sweep import brucite_extract, mixing_zone_extract, sweep, with_updated
from tests.conftest import cheap_case


def _quiet_case():  # type: ignore[no-untyped-def]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cheap_case()


# --------------------------------------------------------------------------- with_updated


def test_a_dotted_path_replaces_the_nested_field_and_nothing_else() -> None:
    case = _quiet_case()
    updated = with_updated(case, "effluent.flow", 7.0e-5)
    assert updated.effluent.flow == 7.0e-5
    assert case.effluent.flow == 5.0e-5, "the original is frozen and untouched"
    assert updated.diffuser == case.diffuser


def test_a_path_through_none_names_the_fix() -> None:
    """A dose axis on a case with no chemistry must say what to add, not AttributeError."""
    case = _quiet_case()
    assert case.effluent_chemistry is None
    with pytest.raises(ValueError, match="effluent_chemistry"):
        with_updated(case, "effluent_chemistry.total_alkalinity", 4000.0)


def test_an_unknown_field_is_an_error_not_a_new_attribute() -> None:
    with pytest.raises(ValueError, match="no field"):
        with_updated(_quiet_case(), "effluent.flowrate", 1.0)


def test_the_rebuilt_case_is_revalidated() -> None:
    """`model_copy(update=)` skips validation; the harness must not.

    A sweep axis is exactly where an out-of-range value arrives mechanically, so a negative
    flow has to fail at the cell, not integrate into nonsense.
    """
    with pytest.raises(ValueError):
        with_updated(_quiet_case(), "effluent.flow", -1.0)


def test_revalidation_reraises_the_geometry_warning() -> None:
    """The warning a validator raises must fire inside the cell that owns it, so `sweep`
    can record it on that cell's row."""
    case = _quiet_case()
    # test21's geometry warns about its seabed; rebuilding it must warn again.
    with pytest.warns(GeometryWarning):
        with_updated(case, "effluent.flow", 6.0e-5)


# --------------------------------------------------------------------------- sweep


@pytest.fixture(scope="module")
def swept():  # type: ignore[no-untyped-def]
    """One 2x1 sweep for the whole module -- two integrations, the module's whole budget."""
    return sweep(
        _quiet_case(),
        {"effluent.flow": [5.0e-5, 6.0e-5], "diffuser.n_ports": [1]},
        samples=48,
    )


def test_one_row_per_cell_keyed_by_the_axis_values(swept) -> None:  # type: ignore[no-untyped-def]
    assert len(swept) == 2
    assert list(swept["effluent.flow"]) == [5.0e-5, 6.0e-5]
    assert list(swept["diffuser.n_ports"]) == [1, 1]


def test_the_default_extract_reports_the_mixing_zones(swept) -> None:  # type: ignore[no-untyped-def]
    for column in (
        "termination",
        "nearfield_end_dilution",
        "acute_region",
        "chronic_region",
        "acute_dilution",
        "chronic_dilution",
    ):
        assert column in swept.columns, column
    assert (swept["error"] == "").all()


def test_warnings_are_data_on_the_row_that_raised_them(swept) -> None:  # type: ignore[no-untyped-def]
    """test21's seabed warning must appear in the cell's own `warnings` column."""
    assert swept["warnings"].str.contains("GeometryWarning").all()


@pytest.mark.slow
def test_a_failing_cell_is_a_row_and_its_neighbours_survive() -> None:
    """The validation.measure rule: a dose that breaks the solver is a finding, not a crash."""
    frame = sweep(
        _quiet_case(),
        # flow: one good cell, one that fails validation outright
        {"effluent.flow": [5.0e-5, -1.0]},
        samples=48,
        extract=lambda results: {"end": float(results.nearfield["dilution"].iloc[-1])},
    )
    assert len(frame) == 2
    good, bad = frame.iloc[0], frame.iloc[1]
    assert good["error"] == "" and good["end"] > 1.0
    assert "ValidationError" in bad["error"], "pydantic names the axis and the bound"
    assert bad.isna()["end"], "a failed cell contributes NaN, not a stale or invented number"


def test_empty_axes_are_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        sweep(_quiet_case(), {})


def test_mixing_zone_extract_flattens_both_boundaries(cheap_run) -> None:  # type: ignore[no-untyped-def]
    out = mixing_zone_extract(cheap_run)
    assert {"acute_region", "chronic_region", "termination"} <= set(out)


def test_brucite_extract_refuses_a_run_without_chemistry(cheap_run) -> None:  # type: ignore[no-untyped-def]
    """The fix is in the message, not a KeyError from inside pandas."""
    assert not cheap_run.has_chemistry
    with pytest.raises(ValueError, match="effluent_chemistry"):
        brucite_extract(cheap_run)
