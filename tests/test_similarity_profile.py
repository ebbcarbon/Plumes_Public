"""The selectable similarity profile -- PLAN 8.4's rework, against case48 and the closed forms.

case48 (2026-08-25) showed the exe's cross-plume profile is a *setting* with three options, and
that its `Gaussian Profile` is not the literature's. So the port now carries all four as
`SimilarityProfile`, with the exe's default -- the parabola every archived comparison rests on --
as its own default. Everything here holds the parity path fixed while checking that each other
profile reproduces the plateau the exe prints under it.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest
from pydantic import ValidationError

from plumes2.config import NearFieldSettings
from plumes2.crossplume import (
    EXE_GAUSSIAN_K,
    EXE_GAUSSIAN_PEAK_TO_MEAN,
    PEAK_TO_MEAN_ROUND,
    PEAK_TO_MEAN_SLAB,
    SimilarityProfile,
    parabolic_weight,
    peak_to_mean,
    peak_to_mean_round,
    peak_to_mean_slab,
    profile_weight,
)
from plumes2.io import dumps_case, load_project, loads_case, read_dat
from plumes2.plotframe import from_dat
from plumes2.results import run
from tests.conftest import REFERENCE_CASES

CASE48 = REFERENCE_CASES / "case48_similarity_profiles"


def _plateau(trace: str) -> float:
    """The developed `Dilutn / CL-Dil` of one case48 trace -- the same reading as ledger row 278."""
    frame = read_dat(CASE48 / trace).nearfield
    ratio = (frame["Dilutn"] / frame["CL-Dil"]).to_numpy(dtype=np.float64)
    developed = frame["Dilutn"].to_numpy(dtype=np.float64) > 5.0
    return float(np.mean(ratio[developed]))


# ------------------------------------------------------------------ against the exe's traces


@pytest.mark.golden
@pytest.mark.parametrize(
    ("profile", "trace", "tolerance"),
    [
        (SimilarityProfile.PARABOLIC, "style_default.dat", 1e-4),
        # 35/9 against the exe's 3.88997: a real +0.028 % residual (row 278), admitted and no more.
        (SimilarityProfile.THREE_HALVES, "style_threehalves.dat", 1.5e-3),
        (SimilarityProfile.EXE_GAUSSIAN, "style_gaussian.dat", 1e-4),
    ],
)
def test_each_exe_option_is_reproduced_by_its_own_profile(
    profile: SimilarityProfile, trace: str, tolerance: float
) -> None:
    assert abs(peak_to_mean_round(profile) - _plateau(trace)) < tolerance


@pytest.mark.golden
def test_the_literature_gaussian_matches_no_exe_option() -> None:
    """`exp(-2u^2)` sits between the exe's default and its Gaussian, and far from both."""
    literature = peak_to_mean_round(SimilarityProfile.GAUSSIAN)
    for trace in ("style_default.dat", "style_threehalves.dat", "style_gaussian.dat"):
        assert abs(literature - _plateau(trace)) > 0.3


# -------------------------------------------------------------------------- the closed forms


def test_the_three_halves_anchors_are_the_reference_s_own() -> None:
    """`[1 - u^1.5]^2` integrates to 9/35 over the disc and 0.45 across the slab."""
    assert peak_to_mean_round(SimilarityProfile.THREE_HALVES) == pytest.approx(35.0 / 9.0)
    assert peak_to_mean_slab(SimilarityProfile.THREE_HALVES) == pytest.approx(20.0 / 9.0)


def test_the_literature_gaussian_matches_plan_6b_s_table() -> None:
    assert peak_to_mean_round(SimilarityProfile.GAUSSIAN) == pytest.approx(2.3130, abs=1e-4)
    assert peak_to_mean_slab(SimilarityProfile.GAUSSIAN) == pytest.approx(1.6718, abs=1e-4)


def test_the_exe_gaussian_s_exponent_is_derived_from_the_plateau() -> None:
    """`k` solves `k / (1 - e^-k) = 3.66998`: about 3.57, and it reproduces the plateau exactly."""
    assert peak_to_mean_round(SimilarityProfile.EXE_GAUSSIAN) == pytest.approx(
        EXE_GAUSSIAN_PEAK_TO_MEAN, abs=1e-12
    )
    assert abs(EXE_GAUSSIAN_K - 3.566) < 2e-3
    # The truncation point in e-folding lengths, and what is left of the centreline there.
    assert math.exp(-EXE_GAUSSIAN_K) == pytest.approx(0.028, abs=1e-3)


def test_the_round_ratio_cannot_separate_a_parabola_from_a_gaussian_but_the_slab_can() -> None:
    """⭐ Why row 198's 8 617 rows identify the parabola through its *merged* limit.

    An untruncated `exp(-2u^2)` has a peak-to-mean of exactly 2 over the plane -- the parabola's
    value -- so the unmerged plateau is consistent with either shape. The slab limit is not: the
    parabola gives 1.5000 (measured, test32), the Gaussian 1.672 truncated or 1.596 untruncated.
    """
    untruncated_round = 1.0 / (1.0 / 2.0)  # 1 / integral_0^inf 2u e^{-2u^2} du
    assert untruncated_round == PEAK_TO_MEAN_ROUND
    untruncated_slab = 1.0 / (math.sqrt(math.pi) / (2.0 * math.sqrt(2.0)))
    assert untruncated_slab == pytest.approx(1.596, abs=1e-3)
    assert abs(untruncated_slab - PEAK_TO_MEAN_SLAB) > 0.09
    assert abs(peak_to_mean_slab(SimilarityProfile.GAUSSIAN) - PEAK_TO_MEAN_SLAB) > 0.17


@pytest.mark.parametrize("profile", list(SimilarityProfile))
def test_every_profile_is_one_on_the_axis_and_zero_past_the_edge(
    profile: SimilarityProfile,
) -> None:
    u = np.linspace(0.0, 1.0, 101)
    weight = profile_weight(u, profile)
    assert weight[0] == 1.0
    assert (np.diff(weight) <= 1e-12).all(), "the shape must fall monotonically to the edge"
    assert (profile_weight(np.array([1.01, 1.5, -1.2]), profile) == 0.0).all()
    # Symmetric: the offset's sign does not matter.
    assert profile_weight(-0.4, profile) == profile_weight(0.4, profile)


@pytest.mark.parametrize("profile", list(SimilarityProfile))
def test_the_reciprocal_area_mean_is_the_round_anchor(profile: SimilarityProfile) -> None:
    """`peak_to_mean_round` is `1 / integral_0^1 2u phi(u) du`, checked by quadrature."""
    u = np.linspace(0.0, 1.0, 200_001)
    mean = np.trapezoid(2.0 * u * profile_weight(u, profile), u)
    assert 1.0 / mean == pytest.approx(peak_to_mean_round(profile), rel=1e-6)
    slab_mean = np.trapezoid(profile_weight(u, profile), u)
    assert 1.0 / slab_mean == pytest.approx(peak_to_mean_slab(profile), rel=1e-6)


# ------------------------------------------------------------------- the parity path is fixed


def test_the_parabolic_path_is_unchanged() -> None:
    """The default arguments are the parabola, and the parabola's numbers are what they were."""
    u = np.linspace(-1.5, 1.5, 61)
    assert (parabolic_weight(u) == profile_weight(u)).all()
    assert peak_to_mean_round() == 2.0 and peak_to_mean_slab() == 1.5
    diameters = np.array([0.5, 1.0, 1.3, 2.0, 5.0])
    merged = np.array([False, True, True, True, True])
    default = peak_to_mean(diameters, 1.0, merged)
    explicit = peak_to_mean(diameters, 1.0, merged, SimilarityProfile.PARABOLIC)
    assert (default == explicit).all()
    assert default.tolist() == pytest.approx([2.0, 2.0, 1.85, 1.5, 1.5])


@pytest.mark.parametrize("profile", list(SimilarityProfile))
def test_the_blend_runs_between_each_profile_s_own_anchors(profile: SimilarityProfile) -> None:
    spacing = 1.5
    round_value, slab_value = peak_to_mean_round(profile), peak_to_mean_slab(profile)
    assert float(peak_to_mean(0.4 * spacing, spacing, False, profile)) == round_value
    assert float(peak_to_mean(5.0 * spacing, spacing, False, profile)) == round_value
    assert float(peak_to_mean(1.0 * spacing, spacing, True, profile)) == pytest.approx(round_value)
    assert float(peak_to_mean(2.0 * spacing, spacing, True, profile)) == pytest.approx(slab_value)
    assert float(peak_to_mean(9.0 * spacing, spacing, True, profile)) == pytest.approx(slab_value)
    halfway = float(peak_to_mean(1.5 * spacing, spacing, True, profile))
    assert halfway == pytest.approx((round_value + slab_value) / 2.0)
    # A single port never blends, whatever the profile.
    assert float(peak_to_mean(9.0, 0.0, True, profile)) == round_value


# ------------------------------------------------------------------------ as a case setting


def test_the_profile_is_a_case_setting_that_defaults_to_the_exe_s_default() -> None:
    assert NearFieldSettings().similarity_profile is SimilarityProfile.PARABOLIC
    settings = NearFieldSettings(similarity_profile="three_halves")  # type: ignore[arg-type]
    assert settings.similarity_profile is SimilarityProfile.THREE_HALVES
    with pytest.raises(ValidationError):
        NearFieldSettings(similarity_profile="top_hat")  # type: ignore[arg-type]


def test_the_profile_round_trips_through_yaml_and_the_default_is_omitted() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # case01's seabed GeometryWarning and its duplicate CSV
        case = load_project(
            REFERENCE_CASES / "case01_macoma_cms" / "Macoma2.prj", warn_on_drift=False
        ).to_case()
    assert "similarity_profile" not in dumps_case(case), "a default is not written"
    gaussian = case.model_copy(
        update={
            "near_field": case.near_field.model_copy(
                update={"similarity_profile": SimilarityProfile.GAUSSIAN}
            )
        }
    )
    text = dumps_case(gaussian)
    assert "similarity_profile: gaussian" in text
    assert loads_case(text).near_field.similarity_profile is SimilarityProfile.GAUSSIAN


@pytest.mark.golden
def test_a_dat_read_under_a_declared_profile_agrees_with_its_own_centreline() -> None:
    """`from_dat(..., profile=)` puts the declared profile on the frame and in `peak_to_mean`.

    case48's 3/2 trace prints its own `CL-Dil`, so the printed ratio can be checked against the
    derived column row by row once the profile has developed.
    """
    path = CASE48 / "style_threehalves.dat"
    plot = from_dat(read_dat(path), path, profile=SimilarityProfile.THREE_HALVES)
    assert plot.profile is SimilarityProfile.THREE_HALVES
    frame = plot.frame
    assert np.allclose(frame["peak_to_mean"].to_numpy(), 35.0 / 9.0)
    developed = frame[frame["dilution"] > 5.0]
    printed = developed["dilution"] / developed["centreline_dilution"]
    # The plateau spreads 3.88881-3.89119 around the exe's 3.88997 (row 278), so the worst row sits
    # ~0.0023 from 35/9; 3e-3 admits that and is a fifth of the gap to any other profile.
    assert np.abs(printed.to_numpy() - developed["peak_to_mean"].to_numpy()).max() < 3e-3
    # And the default reading of the same file would be the parabola, wrongly.
    assert from_dat(read_dat(path), path).profile is SimilarityProfile.PARABOLIC


@pytest.mark.slow
def test_a_run_under_the_literature_gaussian_moves_only_the_centreline(cheap_run) -> None:  # type: ignore[no-untyped-def]
    """The profile is post-processing: the trajectory is bit-identical, the centreline is not."""
    case = cheap_run.case
    gaussian = case.model_copy(
        update={
            "near_field": case.near_field.model_copy(
                update={"similarity_profile": SimilarityProfile.GAUSSIAN}
            )
        }
    )
    other = run(gaussian, samples=len(cheap_run.nearfield))
    for column in ("time_s", "dilution", "plume_diameter_m", "depth_m", "salinity_psu"):
        assert (other.nearfield[column].to_numpy() == cheap_run.nearfield[column].to_numpy()).all()
    assert (cheap_run.nearfield["peak_to_mean"] == 2.0).all()
    assert np.allclose(other.nearfield["peak_to_mean"].to_numpy(), 2.3130, atol=1e-4)
    expected = np.maximum(1.0, other.nearfield["dilution"] / other.nearfield["peak_to_mean"])
    assert other.nearfield["centreline_dilution"].to_numpy() == pytest.approx(expected.to_numpy())
    assert other.case.near_field.similarity_profile is SimilarityProfile.GAUSSIAN
