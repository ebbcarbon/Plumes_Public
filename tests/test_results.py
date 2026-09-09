"""Running a case and writing usable output -- Phase 6 track B."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from plumes2.io.project import load_project
from plumes2.io.yaml_case import load_case
from plumes2.provenance import case_digest
from plumes2.results import NEARFIELD_COLUMNS, run, write_results

CASES = Path(__file__).resolve().parents[1] / "reference_cases"


def _case():  # type: ignore[no-untyped-def]
    base = load_project(
        CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
    ).to_case()
    return base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": base.effluent.model_copy(update={"flow": 5.0e-5}),
        }
    )


@pytest.fixture(scope="module")
def result(cheap_run):  # type: ignore[no-untyped-def]
    """The suite-wide cheap run -- see `tests/conftest.py`. Same case `_case()` builds."""
    return cheap_run


@pytest.fixture(scope="module")
def dosed():  # type: ignore[no-untyped-def]
    """One dosed run for the whole module.

    Seven tests below need a chemistry run and each used to integrate its own, at sample counts
    from 12 to 48 -- none of which changed the cost, since an integration is the ODE and `samples`
    only picks rows off the dense output. Sampling at the largest of them once serves all seven.
    """
    return run(_dosed_case(), samples=48)


@pytest.fixture(scope="module")
def archive_run():  # type: ignore[no-untyped-def]
    """One 25-port archived-diffuser run, which is the module's far-field case."""
    return run(_archive_case(), samples=60)


def test_the_trajectory_is_sampled_evenly_and_stops_at_the_benchmark(result) -> None:  # type: ignore[no-untyped-def]
    frame = result.nearfield
    assert len(frame) == 64
    assert frame["time_s"].iloc[0] == 0.0
    assert frame["time_s"].iloc[-1] == pytest.approx(result.end_time)
    # Even grid, and never past the point the near field ended.
    spacing = frame["time_s"].diff().dropna()
    assert spacing.std() < 1e-9
    assert result.end_time <= result.solution.solution.t[-1]


def test_every_column_carries_its_units(result) -> None:
    """The exe names a column `P-dia` and leaves you to find out it is metres."""
    assert list(result.nearfield.columns) == list(NEARFIELD_COLUMNS)
    for name in result.nearfield.columns:
        # Machine-friendly: usable as an identifier, so `df.depth_m` works and nothing has to
        # be quoted or renamed. Case is *not* forced -- `degC` is the unit symbol, and
        # `degc` would be a different and ambiguous thing.
        assert name.isidentifier(), name
        assert not name.startswith("_"), name
    for name in ("plume_diameter_m", "depth_m", "x_m", "y_m", "speed_m_s"):
        assert name in result.nearfield.columns


def test_depth_is_positive_downward(result) -> None:
    """Opposite in sign to the solver's `z`, and to the exe's mislabelled `Depth`."""
    frame = result.nearfield
    assert (frame["depth_m"] > 0).all(), "a submerged plume has positive depth"
    assert frame["depth_m"].iloc[0] == pytest.approx(result.case.diffuser.port_depth)


def test_the_physics_is_sane(result) -> None:
    frame = result.nearfield
    assert frame["dilution"].iloc[0] == pytest.approx(1.0, abs=0.05)
    assert frame["dilution"].is_monotonic_increasing, "entrainment only adds mass"
    assert (frame["plume_diameter_m"] > 0).all()
    assert (frame["salinity_psu"].between(0, 40)).all()


def test_the_centreline_is_the_less_dilute_of_the_pair(result) -> None:
    """The whole point of reporting it: a mixing-zone limit is quoted against the worst place.

    Except in the zone of flow establishment, where both are pinned at 1 -- see
    `plumes2.crossplume.centreline_dilution`.
    """
    frame = result.nearfield
    assert (frame["centreline_dilution"] <= frame["dilution"] + 1e-9).all()
    assert (frame["centreline_dilution"] >= 1.0).all()
    developed = frame[frame["centreline_dilution"] > 1.0]
    assert len(developed), "this case never leaves the ZFE"
    ratio = developed["dilution"] / developed["centreline_dilution"]
    assert ratio.to_numpy() == pytest.approx(developed["peak_to_mean"].to_numpy())


def test_the_peak_to_mean_tracks_the_merge_flag(result) -> None:
    frame = result.nearfield
    clear = frame[~frame["merged"]]
    assert (clear["peak_to_mean"] == 2.0).all(), "a round plume is exactly twice its mean"
    assert (frame["peak_to_mean"] >= 1.5).all()


@pytest.mark.slow
def test_a_merging_run_flattens_its_profile_and_the_centreline_follows() -> None:
    """The merged branch end to end, on test32's geometry -- 25 ports at 1 m, square to the flow.

    The single-port fixture above can never exercise it, and a column that is only ever tested on
    its default value is not tested.
    """
    base = load_project(
        CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
    ).to_case()
    case = base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(
                update={"n_ports": 25, "port_spacing": 1.0, "horizontal_angle": 90.0}
            ),
            "effluent": base.effluent.model_copy(update={"flow": 0.005}),
        }
    )
    frame = run(case, samples=200).nearfield
    merged = frame[frame["merged"]]
    assert len(merged), "this geometry merges -- test32 does so at step 310"

    # Confinement flattens the profile, so the ratio leaves 2.0 and heads for 1.5.
    assert merged["peak_to_mean"].min() < 2.0
    assert merged["peak_to_mean"].min() >= 1.5
    # And the centreline rises towards the mean as it does: same dilution, less peaking.
    assert (merged["dilution"] / merged["centreline_dilution"]).to_numpy() == pytest.approx(
        merged["peak_to_mean"].to_numpy()
    )
    # The flag is a prefix-complement: once merged, always merged along a growing plume.
    assert frame["merged"].to_numpy().tolist() == sorted(frame["merged"].to_numpy().tolist())


def test_a_written_run_is_self_describing(result, tmp_path: Path) -> None:
    """The directory alone must say what it is, what made it, and from what."""
    target = write_results(result, tmp_path / "out")
    written = {p.name for p in target.iterdir()}
    assert {"nearfield.csv", "case.yaml", "provenance.yaml"} <= written
    # `farfield.csv` joins them whenever the case has a far-field current, which this one
    # does; the set is a superset rather than an equality so adding an output cannot break
    # an unrelated test.
    assert written <= {"nearfield.csv", "farfield.csv", "case.yaml", "provenance.yaml"}

    reloaded = pd.read_csv(target / "nearfield.csv")
    assert list(reloaded.columns) == list(NEARFIELD_COLUMNS)
    assert len(reloaded) == len(result.nearfield)
    # Typed on read, with no fixed-width parsing and no post-processing. `merged` is the one
    # flag rather than a measurement, and pandas reads it back as `bool` -- still typed, still
    # needing nothing done to it, which is what this asserts.
    for name, dtype in reloaded.dtypes.items():
        expected = pd.api.types.is_bool_dtype if name == "merged" else pd.api.types.is_float_dtype
        assert expected(dtype), f"{name} came back as {dtype}"

    record = yaml.safe_load((target / "provenance.yaml").read_text(encoding="utf-8"))
    assert record["case_digest"] == case_digest(result.case)
    assert record["termination"] == result.termination
    # Every column written is documented; the far field adds its own when present.
    assert set(NEARFIELD_COLUMNS) <= set(record["columns"])
    assert set(reloaded.columns) <= set(record["columns"])

    # The case round-trips, so the run can be repeated from its own output.
    assert case_digest(load_case(target / "case.yaml")) == case_digest(result.case)


def test_full_precision_survives_the_csv(result, tmp_path: Path) -> None:
    """The exe's three decimals are why its output cannot feed anything else.

    A dilution of 12.3456789 must come back as 12.3456789, not 12.346.
    """
    target = write_results(result, tmp_path / "out")
    reloaded = pd.read_csv(target / "nearfield.csv")
    for column in ("dilution", "plume_diameter_m", "depth_m"):
        pd.testing.assert_series_equal(
            reloaded[column], result.nearfield[column], check_exact=False, rtol=1e-12
        )


def test_a_trajectory_needs_more_than_one_point() -> None:
    with pytest.raises(ValueError, match="two samples"):
        run(_case(), samples=1)


# ---------------------------------------------------------------- chemistry columns


def _dosed_case():  # type: ignore[no-untyped-def]
    """case03's ambient with an alkalinity-elevated effluent -- the project's driver.

    The effluent chemistry has to be supplied here rather than loaded: **no `.prj` stores
    chemistry**, which is why case03 parses with an ambient profile and no endmember.
    """
    from plumes2.config import EffluentChemistry

    case = load_project(CASES / "case03_carbonate" / "test.prj", warn_on_drift=False).to_case()
    assert case.effluent_chemistry is None, "the .prj cannot carry it"
    assert case.ambient.has_chemistry
    return case.model_copy(
        update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
    )


def test_chemistry_columns_appear_only_when_the_case_has_chemistry(result, dosed) -> None:  # type: ignore[no-untyped-def]
    from plumes2.results import CHEMISTRY_COLUMNS

    assert not result.has_chemistry
    assert not set(CHEMISTRY_COLUMNS) & set(result.nearfield.columns)

    assert dosed.has_chemistry
    assert list(dosed.nearfield.columns) == [*NEARFIELD_COLUMNS, *CHEMISTRY_COLUMNS]


def test_alkalinity_mixes_conservatively_down_the_plume(dosed) -> None:  # type: ignore[no-untyped-def]
    """TA is conservative; pH and the saturation states are re-solved from it every sample."""
    frame = dosed.nearfield
    assert frame["total_alkalinity_umol_kg"].iloc[0] == pytest.approx(4000.0, rel=1e-6)
    assert frame["total_alkalinity_umol_kg"].is_monotonic_decreasing
    # Dilution-weighted mixing: TA -> the ambient value as D grows.
    assert frame["total_alkalinity_umol_kg"].iloc[-1] < 3000.0
    assert frame["ph_total"].iloc[0] > 10.0
    assert frame["ph_total"].iloc[-1] < 8.6


def test_brucite_flags_the_precipitation_window_the_exe_cannot_see(dosed) -> None:  # type: ignore[no-untyped-def]
    """⭐ The reason this column exists (PLAN.md §8b).

    An alkalinity-elevated discharge leaves the port strongly supersaturated in brucite and
    falls below saturation within seconds. The exe reports aragonite only, which never comes
    close to that swing -- so the risk window is invisible in its output.
    """
    frame = dosed.nearfield
    brucite, aragonite = frame["omega_brucite"], frame["omega_aragonite"]

    assert brucite.iloc[0] > 100.0, "supersaturated at the port"
    assert brucite.iloc[-1] < 1.0, "and safely below saturation once diluted"
    assert brucite.iloc[0] / brucite.iloc[-1] > 1000.0

    # Aragonite moves over a far narrower range across the same trajectory.
    assert aragonite.min() > 1.0, "never undersaturated here"
    assert aragonite.iloc[0] / aragonite.iloc[-1] < 10.0


def test_a_chemistry_run_writes_and_reloads(dosed, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from plumes2.results import CHEMISTRY_COLUMNS

    target = write_results(dosed, tmp_path / "dosed")
    reloaded = pd.read_csv(target / "nearfield.csv")
    assert list(reloaded.columns) == [*NEARFIELD_COLUMNS, *CHEMISTRY_COLUMNS]

    record = yaml.safe_load((target / "provenance.yaml").read_text(encoding="utf-8"))
    assert record["has_chemistry"] is True
    assert "omega_brucite" in record["columns"]
    assert "upper bound" in record["columns"]["omega_brucite"], "the caveat must travel"


# ------------------------------------------------------------------- the far field


def _archive_case():  # type: ignore[no-untyped-def]
    return load_project(CASES / "case01_cms" / "project.prj", warn_on_drift=False).to_case()


def test_the_wastefield_width_handoff_matches_the_exe() -> None:
    """The one number the near field hands the far field, checked against the exe's echo.

    case02 prints `wastefield width of : 48.56` and ends its near field at a plume diameter
    of 0.558 m. `(n-1) * effective spacing + diameter` = 24 * 2.0 + 0.558 = 48.558, which is
    48.56 to the two decimals it prints.
    """
    assert _archive_case().wastefield_width(0.558) == pytest.approx(48.558, abs=5e-4)


def test_the_far_field_starts_where_the_near_field_stopped(archive_run) -> None:  # type: ignore[no-untyped-def]
    """Brooks measures `x` from the transition, so its factor is 1 on the first row.

    The reported distance is from the *diffuser*, which is what a mixing-zone limit is quoted
    against -- and is how the exe prints it, opening case02's table at 2.896 m with a factor
    of 1.
    """
    result = archive_run
    assert result.farfield is not None
    first = result.farfield.iloc[0]
    assert first["dilution_factor"] == pytest.approx(1.0, abs=1e-6)
    assert first["dilution"] == pytest.approx(result.final_dilution, rel=1e-9)
    assert first["travel_time_hr"] == 0.0
    assert first["distance_m"] > 0.0, "measured from the diffuser, not the transition"


def test_the_far_field_spreads_and_dilutes_monotonically(archive_run) -> None:  # type: ignore[no-untyped-def]
    result = archive_run
    frame = result.farfield
    assert frame is not None
    assert frame["width_m"].is_monotonic_increasing
    assert frame["dilution"].is_monotonic_increasing
    assert frame["distance_m"].is_monotonic_increasing
    assert frame["width_m"].iloc[0] > result.nearfield["plume_diameter_m"].iloc[-1]


@pytest.mark.slow
def test_the_far_field_uses_its_own_current_not_the_near_field_one() -> None:
    """`Far-spd` is a separate ambient column, and using the wrong one rescales every row."""
    case = _archive_case()
    levels = [level.model_copy(update={"farfield_speed": 0.10}) for level in case.ambient.levels]
    faster = case.model_copy(update={"ambient": case.ambient.model_copy(update={"levels": levels})})

    base = run(case, samples=40).farfield
    quick = run(faster, samples=40).farfield
    assert base is not None and quick is not None
    # Same distances, but a faster current means less time to spread, so less dilution.
    assert quick["travel_time_hr"].iloc[-1] < base["travel_time_hr"].iloc[-1]
    assert quick["dilution"].iloc[-1] != pytest.approx(base["dilution"].iloc[-1])


@pytest.mark.slow
def test_no_far_field_without_a_current_or_when_disabled() -> None:
    """Brooks divides by the current; with none there is no downstream axis at all."""
    case = _archive_case()
    still = [level.model_copy(update={"farfield_speed": 0.0}) for level in case.ambient.levels]
    assert (
        run(
            case.model_copy(update={"ambient": case.ambient.model_copy(update={"levels": still})}),
            samples=20,
        ).farfield
        is None
    )

    disabled = case.model_copy(
        update={"far_field": case.far_field.model_copy(update={"enabled": False})}
    )
    assert run(disabled, samples=20).farfield is None


def test_the_far_field_is_written_and_declared(archive_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from plumes2.results import FARFIELD_COLUMNS

    result = archive_run
    target = write_results(result, tmp_path / "out")
    assert (target / "farfield.csv").exists()

    reloaded = pd.read_csv(target / "farfield.csv")
    assert list(reloaded.columns) == list(FARFIELD_COLUMNS)
    record = yaml.safe_load((target / "provenance.yaml").read_text(encoding="utf-8"))
    assert record["has_farfield"] is True
    assert "distance_m" in record["columns"]


def test_the_quantities_the_report_needs_are_all_written(dosed) -> None:  # type: ignore[no-untyped-def]
    """PLAN.md §6b names the outputs of concern; every one has to be a column.

    `pCO2`, carbonate and bicarbonate were computed and thrown away until the report spec
    asked for them -- the cheapest possible gap, and exactly the kind that blocks a figure
    later. The governing instruction there is data first, plots second.
    """
    from plumes2.results import CHEMISTRY_COLUMNS

    frame = dosed.nearfield
    for column in (
        "ph_total",
        "temperature_degC",
        "omega_aragonite",
        "omega_calcite",
        "omega_brucite",
        "total_alkalinity_umol_kg",
        "pco2_uatm",
        "carbonate_umol_kg",
        "bicarbonate_umol_kg",
    ):
        assert column in frame.columns, column
        assert frame[column].notna().all(), column
    assert set(CHEMISTRY_COLUMNS) <= set(frame.columns)


def test_the_carbonate_system_is_internally_consistent(dosed) -> None:  # type: ignore[no-untyped-def]
    """DIC is the sum of its three species, which is the cheapest check that they belong."""
    frame = dosed.nearfield
    # CO2(aq) is not written, so DIC must exceed CO3 + HCO3 by exactly that much -- small at
    # these pH values, and never negative.
    residual = frame["dic_umol_kg"] - frame["carbonate_umol_kg"] - frame["bicarbonate_umol_kg"]
    assert (residual >= -1e-6).all(), "CO3 + HCO3 cannot exceed DIC"
    assert (residual < 100.0).all(), "aqueous CO2 should be small at these pH values"


def test_pco2_collapses_as_alkalinity_is_added(dosed) -> None:  # type: ignore[no-untyped-def]
    """The headline of an alkalinity discharge: pCO2 is driven to almost nothing at the port."""
    frame = dosed.nearfield
    assert frame["pco2_uatm"].iloc[0] < 1.0, "essentially no CO2 demand at pH 10.4"
    assert 150.0 < frame["pco2_uatm"].iloc[-1] < 500.0, "and back toward ambient once mixed"
    assert frame["pco2_uatm"].is_monotonic_increasing


# --------------------------------------------------------------- far-field chemistry (8.3a)
#
# Before 2026-08-24 the far field carried no chemistry, so pH and Omega could not be read at a
# chronic mixing zone that sits past the transition -- which is nearly all of them (case03's is
# 207 m against a ~3 m transition). The construction is the exe's own: conservative quantities
# relax from the near-field endpoint toward the ambient at the trapping depth with the Brooks
# spreading factor (ledger row 56), and pH/Omega are re-solved from the mixed pair.


def test_the_far_field_carries_chemistry_and_the_seam_is_exact(dosed) -> None:  # type: ignore[no-untyped-def]
    """The far field's first chemistry row is the near field's last, by construction.

    A seam between the two tables would be read as physics -- a pH step at the transition looks
    like a process, and there is none.
    """
    from plumes2.results import CHEMISTRY_COLUMNS

    far, near = dosed.farfield, dosed.nearfield
    for column in CHEMISTRY_COLUMNS:
        assert column in far.columns, column
        first, last = float(far[column].iloc[0]), float(near[column].iloc[-1])
        assert first == pytest.approx(last, rel=1e-9), column


def test_the_far_field_chemistry_relaxes_to_the_trapping_depth_ambient(dosed) -> None:  # type: ignore[no-untyped-def]
    """TA follows `ambient + (endpoint - ambient) / spreading` exactly -- the row-56 law.

    Asserting the law itself, not just the asymptote: a wrong ambient endmember (a depth mean,
    say -- the defect shape row 246 found in the DO module) would still asymptote somewhere,
    just the wrong somewhere.
    """
    import numpy as np

    from plumes2.ambient import AmbientProfileView

    far, near = dosed.farfield, dosed.nearfield
    depth = float(near["depth_m"].iloc[-1])
    ambient_ta = float(AmbientProfileView(dosed.case.ambient).total_alkalinity(depth))
    endpoint = float(near["total_alkalinity_umol_kg"].iloc[-1])
    spreading = far["dilution_factor"].to_numpy(dtype=float)
    expected = ambient_ta + (endpoint - ambient_ta) / spreading
    assert np.allclose(far["total_alkalinity_umol_kg"].to_numpy(dtype=float), expected, rtol=1e-9)
    # and the residual against ambient shrinks monotonically as the plume spreads
    residual = np.abs(far["total_alkalinity_umol_kg"].to_numpy(dtype=float) - ambient_ta)
    assert np.all(np.diff(residual) <= 1e-12)


def test_mixing_zone_values_report_the_regulatory_distances(dosed) -> None:  # type: ignore[no-untyped-def]
    """One row per boundary, at the distances the case declares -- the dose study's quantity."""
    from plumes2.results import mixing_zone_values

    table = mixing_zone_values(dosed)
    assert list(table.index) == ["acute", "chronic"]
    zone = dosed.case.mixing_zone
    assert float(table.loc["acute", "distance_m"]) == zone.acute_distance
    assert float(table.loc["chronic", "distance_m"]) == zone.chronic_distance
    # case03's boundaries both sit past the ~3 m transition, in the far field
    assert (table["region"] == "farfield").all()
    assert float(table.loc["chronic", "dilution"]) > float(table.loc["acute", "dilution"])
    # and the chemistry arrives with them
    for column in ("ph_total", "omega_aragonite", "omega_brucite"):
        assert pd.notna(table.loc["chronic", column]), column


def test_sample_at_distance_names_its_region_and_refuses_to_extrapolate(dosed) -> None:  # type: ignore[no-untyped-def]
    """Near field before the transition, far field after, and NaN -- not a guess -- beyond."""
    from plumes2.results import sample_at_distance

    transition = float(dosed.farfield["distance_m"].iloc[0])
    inside = sample_at_distance(dosed, transition / 2.0)
    assert inside["region"] == "nearfield"
    assert inside["dilution"] < float(dosed.nearfield["dilution"].iloc[-1])

    past_everything = float(dosed.farfield["distance_m"].iloc[-1]) + 100.0
    beyond = sample_at_distance(dosed, past_everything)
    assert beyond["region"] == "beyond"
    assert "dilution" not in beyond.index, "beyond the tables there is no number to report"
