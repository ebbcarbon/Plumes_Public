"""Ambient interpolation, and what happens outside the tabulated range.

The extrapolation tests carry the weight. Every archived-diffuser project has a seabed 2 m below the
bottom of its ambient profile, and case09's transport broke after its plume rose above the
top of the chemistry profile -- so the out-of-range policy is a real modelling decision
rather than a corner case.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from plumes2.ambient import AmbientProfileView, ExtrapolationPolicy
from plumes2.config import AmbientChemistryLevel, AmbientDOLevel, AmbientLevel, AmbientProfile
from plumes2.io.project import load_project
from plumes2.seawater import density
from tests.conftest import ALL_PRJ_PATHS, REFERENCE_CASES


def archive_profile() -> AmbientProfile:
    """case01's ambient, plus case03's chemistry and a two-level DO profile."""
    rows = [
        (0.0, 30.9, 11.2),
        (3.0, 31.2, 10.4),
        (6.0, 31.2, 9.69),
        (9.0, 31.7, 9.44),
        (12.0, 31.8, 9.34),
        (15.0, 31.9, 9.22),
    ]
    return AmbientProfile(
        levels=[
            AmbientLevel(
                depth=d, salinity=s, temperature=t, current_speed=0.02, current_direction=90.0
            )
            for d, s, t in rows
        ],
        chemistry=[
            AmbientChemistryLevel(depth=1.0, total_alkalinity=3000.0, dic=2500.0),
            AmbientChemistryLevel(depth=2.0, total_alkalinity=2900.0, dic=2500.0),
            AmbientChemistryLevel(depth=4.0, total_alkalinity=2850.0, dic=2450.0),
        ],
        dissolved_oxygen=[
            AmbientDOLevel(depth=0.0, dissolved_oxygen=10.0),
            AmbientDOLevel(depth=15.0, dissolved_oxygen=5.0),
        ],
    )


class TestInterpolation:
    def test_hits_tabulated_levels_exactly(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert float(view.salinity(3.0)) == pytest.approx(31.2)
        assert float(view.temperature(15.0)) == pytest.approx(9.22)

    def test_midpoint_is_the_mean(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert float(view.salinity(1.5)) == pytest.approx((30.9 + 31.2) / 2)

    def test_vectorises(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert view.temperature([0.0, 3.0, 15.0]) == pytest.approx([11.2, 10.4, 9.22])

    def test_density_follows_from_salinity_and_temperature(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert float(view.density(3.0)) == pytest.approx(float(density(31.2, 10.4)))

    def test_density_increases_with_depth_in_this_profile(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert np.all(np.diff(view.density(np.linspace(0.0, 15.0, 31))) > 0)

    def test_sample_returns_every_field(self) -> None:
        sample = AmbientProfileView(archive_profile()).sample(3.0)
        assert sample.depth == pytest.approx(3.0)
        assert sample.salinity == pytest.approx(31.2)
        assert sample.current_direction == pytest.approx(90.0)
        assert sample.dispersion_alpha == pytest.approx(3.0e-4)
        assert sample.density == pytest.approx(float(density(31.2, 10.4)))
        assert not sample.extrapolated


class TestExtrapolation:
    def test_clamp_is_the_default_and_holds_the_endpoint(self) -> None:
        """The archived diffuser's seabed is 2 m below the profile, so this path is always taken."""
        view = AmbientProfileView(archive_profile())
        assert float(view.salinity(17.0)) == pytest.approx(31.9)
        assert float(view.salinity(-1.0)) == pytest.approx(30.9)
        assert view.extrapolation_seen

    def test_in_range_queries_do_not_flag_extrapolation(self) -> None:
        view = AmbientProfileView(archive_profile())
        view.salinity([0.0, 7.5, 15.0])
        assert not view.extrapolation_seen

    def test_sample_reports_extrapolation(self) -> None:
        assert AmbientProfileView(archive_profile()).sample(17.0).extrapolated

    def test_linear_continues_the_gradient(self) -> None:
        view = AmbientProfileView(archive_profile(), policy=ExtrapolationPolicy.LINEAR)
        # The last gradient is (31.9 - 31.8) / 3 per metre.
        assert float(view.salinity(18.0)) == pytest.approx(31.9 + 0.1, abs=1e-9)

    def test_linear_can_produce_nonsense_which_is_why_clamp_is_default(self) -> None:
        """case09's transport broke exactly this way, off the top of a profile."""
        steep = AmbientProfile(
            levels=[
                AmbientLevel(depth=0.0, salinity=1.0, temperature=10.0),
                AmbientLevel(depth=1.0, salinity=30.0, temperature=10.0),
            ]
        )
        assert (
            float(AmbientProfileView(steep, policy=ExtrapolationPolicy.LINEAR).salinity(-2.0)) < 0
        )
        assert float(AmbientProfileView(steep).salinity(-2.0)) == pytest.approx(1.0)

    def test_raise_policy_refuses(self) -> None:
        view = AmbientProfileView(archive_profile(), policy=ExtrapolationPolicy.RAISE)
        with pytest.raises(ValueError, match="outside the tabulated range"):
            view.salinity(17.0)

    def test_single_level_profile_is_uniform(self) -> None:
        view = AmbientProfileView(
            AmbientProfile(levels=[AmbientLevel(depth=0.0, salinity=32.0, temperature=8.0)])
        )
        assert float(view.salinity(100.0)) == pytest.approx(32.0)
        assert not view.extrapolation_seen


class TestChemistryAndOxygen:
    def test_alkalinity_and_dic_interpolate(self) -> None:
        view = AmbientProfileView(archive_profile())
        assert float(view.total_alkalinity(1.5)) == pytest.approx(2950.0)
        assert float(view.dic(3.0)) == pytest.approx(2475.0)

    def test_chemistry_clamps_above_its_top_level(self) -> None:
        """case09's plume rose above 1 m; clamping is what keeps that physical."""
        view = AmbientProfileView(archive_profile())
        assert float(view.total_alkalinity(0.0)) == pytest.approx(3000.0)
        assert float(view.total_alkalinity(-0.5)) == pytest.approx(3000.0)

    def test_missing_chemistry_is_a_clear_error(self) -> None:
        view = AmbientProfileView(
            AmbientProfile(levels=[AmbientLevel(depth=0.0), AmbientLevel(depth=5.0)])
        )
        with pytest.raises(ValueError, match="no ambient chemistry"):
            view.total_alkalinity(1.0)

    def test_blank_ph_column_cannot_be_interpolated_and_says_why(self) -> None:
        profile = AmbientProfile(
            levels=[AmbientLevel(depth=0.0), AmbientLevel(depth=5.0)],
            chemistry=[
                AmbientChemistryLevel(depth=1.0, total_alkalinity=3000.0, dic=2500.0),
                AmbientChemistryLevel(depth=4.0, total_alkalinity=2850.0, dic=2450.0),
            ],
        )
        with pytest.raises(ValueError, match="derives pH from TA and DIC"):
            AmbientProfileView(profile)._chem_lookup("ph", 2.0)

    def test_dissolved_oxygen_interpolates(self) -> None:
        assert float(AmbientProfileView(archive_profile()).dissolved_oxygen(7.5)) == pytest.approx(
            7.5
        )

    def test_missing_oxygen_is_a_clear_error(self) -> None:
        view = AmbientProfileView(
            AmbientProfile(levels=[AmbientLevel(depth=0.0), AmbientLevel(depth=5.0)])
        )
        with pytest.raises(ValueError, match="no dissolved-oxygen"):
            view.dissolved_oxygen(1.0)


class TestAgainstRealProjects:
    def test_every_project_samples_at_its_port_depth(self) -> None:
        """A smoke test that the whole chain works on real inputs."""
        for path in ALL_PRJ_PATHS:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                case = load_project(path, warn_on_drift=False).to_case()
            sample = AmbientProfileView(case.ambient).sample(case.diffuser.port_depth)
            assert 1000.0 < sample.density < 1040.0
            assert sample.salinity >= 0.0

    def test_archive_seabed_is_below_the_profile_and_is_flagged(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            case = load_project(
                REFERENCE_CASES / "case03_carbonate" / "test.prj", warn_on_drift=False
            ).to_case()
        view = AmbientProfileView(case.ambient)
        assert case.diffuser.bottom_depth == pytest.approx(17.0)
        assert view.sample(case.diffuser.bottom_depth).extrapolated
