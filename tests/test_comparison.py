"""Comparing several runs, with the legend derived rather than typed."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumes2.comparison import Comparison, Difference, differences, flatten_case
from plumes2.config import EffluentChemistry
from plumes2.io.project import load_project
from plumes2.results import run

CASES = Path(__file__).resolve().parents[1] / "reference_cases"
PROJECT = CASES / "case18_zero_current_pair" / "test21.prj"


def _base():  # type: ignore[no-untyped-def]
    base = load_project(PROJECT, warn_on_drift=False).to_case()
    # One port and a small flow keeps the integrations quick; the comparison logic is about the
    # cases, not the physics.
    return base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": base.effluent.model_copy(update={"flow": 5.0e-5}),
        }
    )


@pytest.fixture(scope="module")
def base():  # type: ignore[no-untyped-def]
    return _base()


@pytest.fixture(scope="module")
def warmer(base):  # type: ignore[no-untyped-def]
    """The same case at a higher effluent temperature -- one field, so the legend names it."""
    return base.model_copy(
        update={"effluent": base.effluent.model_copy(update={"temperature": 25.0})}
    )


@pytest.fixture(scope="module")
def pair(base, warmer):  # type: ignore[no-untyped-def]
    """Both runs, integrated **once** for the whole module.

    Three tests below need this pair. Integrating per test cost five integrations for two distinct
    trajectories, and an integration is ~8 s regardless of how many rows are sampled from it -- the
    cost is the ODE, not the output grid. Sharing them is worth about 25 s of suite time.
    """
    return run(base, samples=8), run(warmer, samples=12)


# ------------------------------------------------------------------ flattening a case


def test_a_flattened_case_is_dotted_paths_to_scalars(base) -> None:  # type: ignore[no-untyped-def]
    flat = flatten_case(base)
    assert flat["diffuser.port_spacing"] == base.diffuser.port_spacing
    assert flat["near_field.max_rise_or_fall"] == base.near_field.max_rise_or_fall
    # Resolved defaults are present, which is the point -- a changed default is a real difference.
    assert "far_field.law" in flat
    assert "carbonate.aragonite_exponent" in flat


def test_the_profile_tables_are_kept_whole(base) -> None:  # type: ignore[no-untyped-def]
    flat = flatten_case(base)
    assert "ambient.levels" in flat
    assert len(flat["ambient.levels"]) == len(base.ambient.levels)
    # Not exploded: a legend needs the name of the knob, not sixty scalars.
    assert not any(key.startswith("ambient.levels[") for key in flat)


# ------------------------------------------------------------------ what differs


def test_identical_cases_differ_in_nothing(base) -> None:  # type: ignore[no-untyped-def]
    assert differences([base, base.model_copy()]) == []


def test_one_changed_field_is_found_and_nothing_else_is(base) -> None:  # type: ignore[no-untyped-def]
    other = base.model_copy(
        update={"diffuser": base.diffuser.model_copy(update={"port_spacing": 7.5})}
    )
    found = differences([base, other])
    assert [d.field for d in found] == ["diffuser.port_spacing"]
    assert found[0].values == (base.diffuser.port_spacing, 7.5)
    assert found[0].name == "port_spacing"


def test_a_changed_profile_reports_as_the_table(base) -> None:  # type: ignore[no-untyped-def]
    levels = [level.model_copy() for level in base.ambient.levels]
    levels[0] = levels[0].model_copy(update={"temperature": levels[0].temperature + 1.0})
    other = base.model_copy(update={"ambient": base.ambient.model_copy(update={"levels": levels})})
    found = differences([base, other])
    assert [d.field for d in found] == ["ambient.levels"]


def test_fewer_than_two_cases_have_nothing_to_compare(base) -> None:  # type: ignore[no-untyped-def]
    assert differences([base]) == []
    assert differences([]) == []


def test_three_cases_report_one_difference_with_three_values(base) -> None:  # type: ignore[no-untyped-def]
    cases = [
        base.model_copy(update={"diffuser": base.diffuser.model_copy(update={"n_ports": n})})
        for n in (1, 5, 25)
    ]
    found = differences(cases)
    assert [d.field for d in found] == ["diffuser.n_ports"]
    assert found[0].values == (1, 5, 25)


# ------------------------------------------------------------------ labels


def test_a_label_names_the_field_and_this_run_s_value() -> None:
    difference = Difference("diffuser.port_spacing", (1.0, 2.5))
    assert difference.describe(0) == "port_spacing 1"
    assert difference.describe(1) == "port_spacing 2.5"


def test_a_whole_table_is_labelled_by_its_size() -> None:
    difference = Difference("ambient.levels", ((), ((("depth", 0.0),),)))
    assert difference.describe(0) == "levels (0 levels)"
    assert difference.describe(1) == "levels (1 levels)"


@pytest.mark.slow
def test_a_comparison_labels_its_runs_from_their_cases(pair) -> None:  # type: ignore[no-untyped-def]
    comparison = Comparison(pair)
    assert comparison.labels() == ("temperature 10", "temperature 25")
    assert len(comparison) == 2
    assert [result.case for result in comparison] == list(comparison.cases)


@pytest.mark.slow
def test_identical_runs_are_labelled_identical_rather_than_implying_a_difference(pair) -> None:  # type: ignore[no-untyped-def]
    result = pair[0]
    comparison = Comparison((result, result))
    assert comparison.labels() == ("identical", "identical")


def test_many_differences_are_bounded_and_the_remainder_is_stated() -> None:
    """A truncated legend must say it is truncated, or it misrepresents the comparison."""

    class _Fake:
        def __init__(self, case) -> None:  # type: ignore[no-untyped-def]
            self.case = case

    base = _base()
    other = base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(
                update={"port_spacing": 9.0, "n_ports": 3, "port_diameter": 0.2}
            ),
            "effluent": base.effluent.model_copy(update={"temperature": 30.0}),
        }
    )
    comparison = Comparison((_Fake(base), _Fake(other)))  # type: ignore[arg-type]
    labels = comparison.labels(max_fields=2)
    assert all("(+2 more)" in label for label in labels)
    assert labels[0] != labels[1]


def test_an_empty_comparison_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one run"):
        Comparison(())


# ------------------------------------------------------------------ the long frame


def test_a_uniform_table_column_that_differs_is_named_in_the_legend() -> None:
    """Two ambients, same profile, 0.02 against 0.05 m/s: the legend says 'current_speed', not
    'levels (6 levels)' twice."""
    base = _base()
    faster = base.model_copy(
        update={
            "ambient": base.ambient.model_copy(
                update={
                    "levels": [
                        level.model_copy(update={"current_speed": 0.05})
                        for level in base.ambient.levels
                    ]
                }
            )
        }
    )
    found = differences([base, faster])
    fields = [difference.field for difference in found]
    assert "ambient.levels.current_speed" in fields
    assert "ambient.levels" not in fields  # the whole table steps aside for its named column
    (difference,) = [d for d in found if d.field == "ambient.levels.current_speed"]
    assert difference.describe(0) != difference.describe(1)
    assert "current_speed 0.05" in difference.describe(1)


def test_labels_grow_past_the_bound_until_no_two_runs_share_one() -> None:
    """Four effluents: two are the same seawater, so the first two fields cannot tell them apart.

    The 2026-09-08 comparison report printed 'salinity 30.9, excess_density 0, (+2 more)' twice.
    The bound is a bound on clutter, not a licence to misidentify a line: fields are added until
    every label is distinct.
    """

    class _Fake:
        def __init__(self, case) -> None:  # type: ignore[no-untyped-def]
            self.case = case

    base = _base()

    def variant(salinity: float, excess: float, alkalinity: float, dic: float):  # type: ignore[no-untyped-def]
        return base.model_copy(
            update={
                "effluent": base.effluent.model_copy(
                    update={"salinity": salinity, "excess_density": excess}
                ),
                "effluent_chemistry": EffluentChemistry(total_alkalinity=alkalinity, dic=dic),
            }
        )

    runs = (
        _Fake(variant(30.9, 0.0, 4895.0, 2500.0)),
        _Fake(variant(0.0, 0.15, 3260.0, 0.0)),
        _Fake(variant(30.9, 0.0, 20582.0, 2500.0)),
        _Fake(variant(0.0, 4.66, 103098.0, 0.0)),
    )
    labels = Comparison(runs).labels()  # type: ignore[arg-type]
    assert len(set(labels)) == 4, labels
    # The two seawater runs are told apart by the field that actually differs between them.
    assert "total_alkalinity 4895" in labels[0] and "total_alkalinity 20582" in labels[2]
    # Two runs the bound already separates keep the short form.
    short = Comparison(runs[:2]).labels()  # type: ignore[arg-type]
    assert short[0].endswith("(+2 more)") and len(set(short)) == 2


@pytest.mark.slow
def test_the_long_frame_carries_the_label_and_keeps_each_run_s_own_grid(pair) -> None:  # type: ignore[no-untyped-def]
    """The runs terminate at different times; reindexing them would invent output."""
    first, second = pair
    frame = Comparison(pair).frame()

    assert "run" in frame.columns
    assert set(frame["run"]) == {"temperature 10", "temperature 25"}
    assert len(frame) == len(first.nearfield) + len(second.nearfield)
    # Each run keeps its own end time rather than being stretched onto a shared grid.
    ends = frame.groupby("run")["time_s"].max()
    assert ends["temperature 10"] != ends["temperature 25"]
