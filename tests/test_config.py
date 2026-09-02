"""Semantic model validation.

Several of these encode facts the reference cases established rather than generic
schema checks -- the derived seabed depth, the exit velocity that broke case09, the
optional ambient pH, and the input-pair rule from case04.
"""

from __future__ import annotations

import math
import warnings

import pytest
from pydantic import ValidationError

from plumes2.config import (
    AmbientChemistryLevel,
    AmbientLevel,
    AmbientProfile,
    CarbonateSettings,
    Case,
    DesignWarning,
    Diffuser,
    Effluent,
    EffluentChemistry,
    ExeBuild,
    FarFieldSettings,
    GeometryWarning,
    MixingZone,
    NearFieldSettings,
    PHScale,
)


def macoma_diffuser(**overrides: object) -> Diffuser:
    defaults: dict[str, object] = {
        "port_diameter": 0.0127,
        "port_elevation": 1.0,
        "vertical_angle": 45.0,
        "horizontal_angle": 90.0,
        "n_ports": 25,
        "port_spacing": 0.60,
        "port_depth": 2.0,
    }
    return Diffuser(**{**defaults, **overrides})  # type: ignore[arg-type]


def macoma_ambient(max_depth: float = 15.0) -> AmbientProfile:
    return AmbientProfile(
        levels=[
            AmbientLevel(
                depth=d, current_speed=0.02, current_direction=90.0, salinity=s, temperature=t
            )
            for d, s, t in ((0.0, 30.9, 11.2), (3.0, 31.2, 10.4), (max_depth, 31.9, 9.22))
        ]
    )


def macoma_case(**overrides: object) -> Case:
    defaults: dict[str, object] = {
        "diffuser": macoma_diffuser(),
        "effluent": Effluent(flow=0.005, salinity=45.0, temperature=10.0, pollutant=1e5),
        "mixing_zone": MixingZone(acute_distance=20.7, chronic_distance=207.0),
        "ambient": macoma_ambient(),
    }
    return Case(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestDerivedGeometry:
    def test_bottom_depth_is_port_depth_plus_elevation(self) -> None:
        """case10: a 2.0 m port on a 1.0 m riser terminated against a 3.0 m seabed."""
        assert macoma_diffuser().bottom_depth == pytest.approx(3.0)

    def test_diffuser_length_and_single_port_degeneracy(self) -> None:
        assert macoma_diffuser().diffuser_length == pytest.approx(24 * 0.60)
        assert macoma_diffuser(n_ports=1).diffuser_length == 0.0

    def test_wastefield_width_matches_case10(self) -> None:
        """24 * 0.60 + 1.225 = 15.625, printed as 15.62. Discharge parallel to current."""
        assert macoma_diffuser().wastefield_width(1.225, 90.0) == pytest.approx(15.625)

    def test_wastefield_width_matches_case11_single_port(self) -> None:
        assert macoma_diffuser(n_ports=1).wastefield_width(1.451, 90.0) == pytest.approx(1.451)

    def test_wastefield_width_matches_case02(self) -> None:
        wide = macoma_diffuser(n_ports=25, port_spacing=2.0)
        assert wide.wastefield_width(0.558, 90.0) == pytest.approx(48.558)


class TestEffectiveSpacing:
    """The oblique-angle correction, decoded from a project we generated and ran."""

    def test_parallel_discharge_and_current_gives_full_spacing(self) -> None:
        """Every Macoma case: 90 degree ports into a 90 degree current."""
        assert macoma_diffuser().effective_spacing(90.0) == pytest.approx(0.60)

    def test_thirty_degrees_gives_the_cosine(self) -> None:
        """The upstream example geometry: 30 degree ports into a zero-degree current."""
        example = macoma_diffuser(n_ports=18, port_spacing=6.10, horizontal_angle=30.0)
        assert example.effective_spacing(0.0) == pytest.approx(6.10 * math.cos(math.radians(30)))
        # 17 * 6.10 * cos(30) + 6.481 = 96.288, printed 96.29 by the current exe build.
        assert example.wastefield_width(6.481, 0.0) == pytest.approx(96.288, abs=0.005)

    def test_perpendicular_collapses_the_spacing(self) -> None:
        """Unverified against the exe -- no run has a 90 degree offset."""
        example = macoma_diffuser(horizontal_angle=90.0)
        assert example.effective_spacing(0.0) == pytest.approx(0.0, abs=1e-12)

    def test_case_level_helper_uses_the_ambient_current(self) -> None:
        case = macoma_case()
        assert case.current_direction_at_port == pytest.approx(90.0)
        assert case.wastefield_width(1.225) == pytest.approx(15.625)

    def test_port_area(self) -> None:
        assert macoma_diffuser().port_area == pytest.approx(math.pi * (0.0127 / 2) ** 2)


class TestExitVelocity:
    def test_reproduces_the_case09_failure_condition(self) -> None:
        """39.5 m/s through one port -- the plume left the water surface."""
        diffuser = macoma_diffuser(n_ports=1)
        effluent = Effluent(flow=0.005, salinity=35.0, temperature=10.0)
        assert effluent.exit_velocity(diffuser) == pytest.approx(39.5, abs=0.5)

    def test_and_the_case11_fix(self) -> None:
        diffuser = macoma_diffuser(n_ports=1)
        assert Effluent(flow=5e-5).exit_velocity(diffuser) == pytest.approx(0.39, abs=0.01)

    def test_25_ports_share_the_flow(self) -> None:
        assert macoma_case().exit_velocity == pytest.approx(1.58, abs=0.02)


class TestValidation:
    def test_single_port_is_allowed(self) -> None:
        assert macoma_diffuser(n_ports=1).n_ports == 1

    def test_zero_ports_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            macoma_diffuser(n_ports=0)

    def test_negative_diameter_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            macoma_diffuser(port_diameter=-1.0)

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            macoma_diffuser(typo_field=1.0)

    def test_model_is_frozen(self) -> None:
        with pytest.raises(ValidationError):
            macoma_diffuser().port_depth = 5.0  # type: ignore[misc]

    def test_acute_beyond_chronic_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="farther than the"):
            MixingZone(acute_distance=300.0, chronic_distance=207.0)

    def test_ambient_depths_must_increase(self) -> None:
        with pytest.raises(ValidationError, match="must strictly increase"):
            AmbientProfile(levels=[AmbientLevel(depth=3.0), AmbientLevel(depth=1.0)])

    def test_duplicate_depths_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must strictly increase"):
            AmbientProfile(levels=[AmbientLevel(depth=1.0), AmbientLevel(depth=1.0)])

    def test_contraction_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NearFieldSettings(contraction_coefficient=1.5)

    def test_observed_settings_are_all_accepted(self) -> None:
        """0.61 and 1.0 contraction, max rise/fall 2 and 3, intervals 5 and 10."""
        for contraction, switch, interval in ((0.61, 3, 5), (1.0, 2, 10)):
            NearFieldSettings(
                contraction_coefficient=contraction,
                max_rise_or_fall=switch,
                output_interval=interval,
            )


class TestAmbientChemistry:
    def test_ph_may_be_omitted(self) -> None:
        """case03 leaves the pH column blank and the exe derives it."""
        level = AmbientChemistryLevel(depth=1.0, total_alkalinity=3000.0, dic=2500.0)
        assert level.ph is None

    def test_ph_is_not_coerced_to_zero(self) -> None:
        level = AmbientChemistryLevel(
            depth=1.0, total_alkalinity=3000.0, dic=2500.0, ph=None, calcium=100.0
        )
        assert level.ph is None
        assert level.calcium == pytest.approx(100.0)

    def test_out_of_range_ph_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AmbientChemistryLevel(depth=1.0, total_alkalinity=3000.0, dic=2500.0, ph=20.0)


class TestEffluentChemistryPairing:
    def test_ta_plus_dic(self) -> None:
        chem = EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)
        assert chem.dic == pytest.approx(1646.0)

    def test_ta_plus_ph_on_the_free_scale(self) -> None:
        """case03's actual entry."""
        chem = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE)
        assert chem.ph_scale is PHScale.FREE

    def test_both_is_rejected_rather_than_silently_preferring_one(self) -> None:
        """The exe takes DIC and ignores the pH without saying so (case04)."""
        with pytest.raises(ValidationError, match="exactly one of"):
            EffluentChemistry(total_alkalinity=4000.0, dic=1646.0, ph=11.0)

    def test_neither_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of"):
            EffluentChemistry(total_alkalinity=4000.0)

    def test_a_zero_dic_is_a_value_here_even_though_the_exe_reads_it_as_absent(self) -> None:
        """⚠️⚠️ **The one place Ebb's own convention does not map straight onto this model.**

        Ebb specifies a discharge as **(TA, DIC)**, and **(TA, pH) where DIC is 0** (operator,
        2026-08-25) -- which is the exe's rule too: case03 entered DIC 0 and the exe solved from
        TA + pH, case04 gave a real DIC and it discarded the pH (row 30).

        This model deliberately does **not** read 0 as a sentinel: `0.0` is a number, `None` is
        "not specified", and inferring the pairing from a magic value is how case03's entry style
        stayed ambiguous for a week. So a loader translating Ebb's feed must **omit** `dic`
        rather than pass 0 -- and passing both is refused loudly rather than silently preferring
        one, which is the whole point of the validator.
        """
        with pytest.raises(ValidationError, match="exactly one of"):
            EffluentChemistry(total_alkalinity=4000.0, dic=0.0, ph=10.5)

        # The translation, and it is the only correct one.
        translated = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE)
        assert translated.dic is None
        assert translated.ph == pytest.approx(10.5)

        # A zero DIC on its own is a legal, if unusual, statement: TA with no carbon at all.
        carbon_free = EffluentChemistry(total_alkalinity=4000.0, dic=0.0)
        assert carbon_free.dic == 0.0
        assert carbon_free.ph is None


class TestCarbonateSettings:
    def test_defaults_match_case03(self) -> None:
        settings = CarbonateSettings()
        assert (settings.k1k2_option, settings.kso4_option) == (10, 1)

    def test_rate_constants_default_to_the_gui_values(self) -> None:
        settings = CarbonateSettings()
        assert settings.calcite_log_k == pytest.approx(-0.106)
        assert settings.calcite_exponent == pytest.approx(2.87)
        assert settings.aragonite_log_k == pytest.approx(1.11)
        assert settings.aragonite_exponent == pytest.approx(2.26)

    def test_the_undersaturated_nan_is_off_by_default(self) -> None:
        """We do not reproduce the exe's Omega < 1 NaN unless asked (case09)."""
        assert CarbonateSettings().reproduce_undersaturated_nan is False


class TestCaseLevelChecks:
    def test_chemistry_needs_both_endmembers(self) -> None:
        case = macoma_case()
        assert not case.chemistry_enabled

        with_chem = macoma_case(
            effluent_chemistry=EffluentChemistry(total_alkalinity=4000.0, dic=1646.0),
            ambient=AmbientProfile(
                levels=macoma_ambient().levels,
                chemistry=[
                    AmbientChemistryLevel(depth=1.0, total_alkalinity=3000.0, dic=2500.0),
                    AmbientChemistryLevel(depth=4.0, total_alkalinity=2850.0, dic=2450.0),
                ],
            ),
        )
        assert with_chem.chemistry_enabled

    def test_seabed_beyond_the_ambient_profile_warns(self) -> None:
        """The shape of every Macoma project: 2 m port on a 15 m riser, 15 m profile."""
        with pytest.warns(GeometryWarning, match="ambient profile"):
            macoma_case(diffuser=macoma_diffuser(port_elevation=15.0))

    def test_a_consistent_geometry_is_silent(self) -> None:
        import warnings as w

        with w.catch_warnings():
            w.simplefilter("error")
            macoma_case()  # bottom at 3.0 m, profile to 15 m

    def test_chemistry_profile_starting_below_the_port_warns(self) -> None:
        """Extrapolating past the shallow end is what broke case09's transport. The exe
        checks only the deep end, so this is a warning -- see TestChemistryDepthRule."""
        with pytest.warns(GeometryWarning, match="starts at"):
            macoma_case(
                effluent_chemistry=EffluentChemistry(total_alkalinity=4000.0, dic=1646.0),
                ambient=AmbientProfile(
                    levels=macoma_ambient().levels,
                    chemistry=[
                        AmbientChemistryLevel(depth=5.0, total_alkalinity=3000.0, dic=2500.0),
                        AmbientChemistryLevel(depth=9.0, total_alkalinity=2850.0, dic=2450.0),
                    ],
                ),
            )

    def test_far_field_defaults(self) -> None:
        settings = FarFieldSettings()
        assert settings.enabled
        assert settings.law.value == "four_thirds"
        assert settings.max_distance == pytest.approx(500.0)


class TestChemistryDepthRule:
    """The exe refuses to run when the chemistry profile is shallower than the port.

    Discovered 2026-08-12 by loading a generated project: it opened cleanly but would
    not run, reporting "Please input the ambient chemistry conditions at a depth greater
    than port depth".
    """

    @staticmethod
    def _case_with_chemistry(depths: list[float], port_depth: float) -> Case:
        return macoma_case(
            diffuser=macoma_diffuser(port_depth=port_depth, port_elevation=1.0),
            effluent_chemistry=EffluentChemistry(total_alkalinity=4000.0, dic=1646.0),
            ambient=AmbientProfile(
                levels=macoma_ambient().levels,
                chemistry=[
                    AmbientChemistryLevel(depth=d, total_alkalinity=3000.0, dic=2500.0)
                    for d in depths
                ],
            ),
        )

    def test_shallower_than_the_port_is_rejected(self) -> None:
        """The exact situation the exe refused: 1-4 m chemistry, 11 m port."""
        with pytest.raises(ValidationError, match="depth greater than port depth"):
            self._case_with_chemistry([1.0, 2.0, 3.0, 4.0], port_depth=11.0)

    def test_exactly_at_the_port_is_rejected(self) -> None:
        """'greater than', so equality does not satisfy it."""
        with pytest.raises(ValidationError, match="must extend deeper than the port"):
            self._case_with_chemistry([1.0, 2.0], port_depth=2.0)

    def test_deeper_than_the_port_is_accepted(self) -> None:
        case = self._case_with_chemistry([1.0, 2.0, 3.0, 4.0], port_depth=2.0)
        assert case.chemistry_enabled

    def test_the_upstream_example_shape_passes(self) -> None:
        """0-15 m chemistry with an 11 m port, which is what we generated."""
        case = self._case_with_chemistry([0.0, 5.0, 10.0, 15.0], port_depth=11.0)
        assert case.ambient.chemistry[-1].depth == pytest.approx(15.0)

    def test_the_rule_only_applies_when_chemistry_is_enabled(self) -> None:
        """No effluent endmember means no chemistry run, so no constraint."""
        case = macoma_case(diffuser=macoma_diffuser(port_depth=11.0, port_elevation=1.0))
        assert not case.chemistry_enabled

    def test_shallow_end_still_only_warns(self) -> None:
        """The exe checks only the deep end; the shallow end broke case09 but is legal."""
        with pytest.warns(GeometryWarning, match="starts at"):
            self._case_with_chemistry([5.0, 9.0], port_depth=2.0)






# ------------------------------------------------------------------ the Froude design check


def _case_with(**overrides):  # type: ignore[no-untyped-def]
    """A minimal runnable case, so a test can move one quantity and hold the rest still."""
    from plumes2.config import Case

    spec = {
        "diffuser": {
            "port_diameter": 0.1, "port_elevation": 1.0, "vertical_angle": 0.0,
            "horizontal_angle": 90.0, "n_ports": 1, "port_spacing": 1.0, "port_depth": 10.0,
        },
        "effluent": {"flow": 0.5, "salinity": 0.0, "temperature": 20.0},
        "ambient": {
            "levels": [
                {"depth": 0.0, "salinity": 35.0, "temperature": 10.0},
                {"depth": 12.0, "salinity": 35.0, "temperature": 10.0},
            ]
        },
        "mixing_zone": {"acute_distance": 10.0, "chronic_distance": 100.0},
    }
    for key, value in overrides.items():
        spec[key] = {**spec[key], **value} if isinstance(value, dict) else value  # type: ignore[dict-item]
    return Case(**spec)  # type: ignore[arg-type]


def test_a_jetting_discharge_is_supercritical_and_silent() -> None:
    """Every archived case is here: the lowest in the whole archive is case22 at 2.01."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DesignWarning)
        case = _case_with()
    assert case.densimetric_froude_number() > 1.0


def test_a_buoyancy_dominated_port_warns_but_still_builds() -> None:
    """⚠️ Warns, never refuses. The exe runs these and a port of it has to reproduce them."""
    with pytest.warns(DesignWarning, match="Froude number"):
        case = _case_with(effluent={"flow": 0.01}, diffuser={"port_diameter": 0.5})
    assert case.densimetric_froude_number() < 1.0
    # The case is fully usable: warning, not rejection.
    assert case.effluent.flow == 0.01


def test_the_froude_number_is_the_ratio_of_momentum_to_buoyancy() -> None:
    """`U / sqrt(|g'| d)` -- checked against the definition rather than against itself."""
    from plumes2.seawater import density, reduced_gravity

    case = _case_with()
    ambient = float(density(35.0, 10.0))
    effluent = float(density(0.0, 20.0))
    expected = case.effluent.exit_velocity(case.diffuser) / math.sqrt(
        abs(float(reduced_gravity(effluent, ambient))) * case.diffuser.port_diameter
    )
    assert case.densimetric_froude_number() == pytest.approx(expected)


def test_a_dense_discharge_gets_a_real_froude_number() -> None:
    """⚠️ The manual's `s - 1` is negative for a sinking plume; the magnitude is what is meant.

    Half this archive is negatively buoyant -- case07's 45 psu effluent is 10 kg/m3 denser than
    its ambient -- so a literal reading would put a negative number under the root and produce
    nothing. A dense discharge is no less a jet for sinking.
    """
    dense = _case_with(effluent={"salinity": 45.0, "temperature": 10.0})
    froude = dense.densimetric_froude_number()
    assert math.isfinite(froude) and froude > 0.0


def test_a_neutrally_buoyant_discharge_is_pure_momentum() -> None:
    """No buoyancy to overcome, so the ratio is infinite -- correct, not a failure."""
    neutral = _case_with(effluent={"salinity": 35.0, "temperature": 10.0})
    assert math.isinf(neutral.densimetric_froude_number())


class TestTheExeBuildSelector:
    """The wastefield width differs between exe generations, and both are archived.

    ⚠️ The pre-2026 build applies **no** angular correction. The same project gives 96.29 m on a
    2026 build and 109.59 m on the legacy one -- a 13.30 m gap that is exactly the cosine on an
    18-port, 6.10 m, 30-degree diffuser. Far-field work uses the legacy build because it offers
    more output columns, so this is a live target rather than history.
    """

    def test_the_default_keeps_the_cosine(self) -> None:
        example = Diffuser(
            port_diameter=0.0762, port_elevation=0.31, vertical_angle=45.0,
            horizontal_angle=30.0, n_ports=18, port_spacing=6.10, port_depth=11.0,
        )
        assert example.wastefield_width(6.481, 0.0) == pytest.approx(96.288, abs=0.005)
        assert example.effective_spacing(0.0) == pytest.approx(
            6.10 * math.cos(math.radians(30))
        )

    def test_legacy_drops_it_entirely(self) -> None:
        """`(n-1) * L + diameter`, with no angular factor -- and the 13.30 m gap it explains."""
        example = Diffuser(
            port_diameter=0.0762, port_elevation=0.31, vertical_angle=45.0,
            horizontal_angle=30.0, n_ports=18, port_spacing=6.10, port_depth=11.0,
        )
        legacy = example.wastefield_width(6.481, 0.0, build=ExeBuild.LEGACY)
        assert legacy == pytest.approx(17 * 6.10 + 6.481)
        assert example.effective_spacing(0.0, build=ExeBuild.LEGACY) == pytest.approx(6.10)
        # The gap between the two laws is the correction itself, and it is what row 96 saw.
        assert legacy - example.wastefield_width(6.481, 0.0) == pytest.approx(13.89, abs=0.01)

    def test_the_two_agree_when_the_diffuser_faces_the_current(self) -> None:
        """At a zero offset the cosine is 1, so the selector is inert -- most of the archive."""
        square = Diffuser(
            port_diameter=0.0127, port_elevation=15.0, vertical_angle=45.0,
            horizontal_angle=90.0, n_ports=25, port_spacing=2.0, port_depth=2.0,
        )
        for build in ExeBuild:
            assert square.wastefield_width(0.558, 90.0, build=build) == pytest.approx(48.558)

    def test_a_case_follows_its_far_field_setting(self) -> None:
        """The selector is persisted, so a legacy comparison is a property of the case.

        Uses an oblique diffuser, because at the Macoma geometry's zero offset the two laws are
        identical and the test would pass without measuring anything.
        """
        case = macoma_case(
            diffuser=macoma_diffuser(horizontal_angle=30.0, n_ports=18, port_spacing=6.10)
        )
        legacy = case.model_copy(
            update={"far_field": case.far_field.model_copy(
                update={"exe_build": ExeBuild.LEGACY})}
        )
        assert case.far_field.exe_build is ExeBuild.CURRENT
        # The ambient current runs at 90 deg here, so the offset is 60 deg and the factor is 0.5.
        span = 17 * 6.10
        assert case.wastefield_width(6.481) == pytest.approx(span * 0.5 + 6.481, abs=1e-6)
        assert legacy.wastefield_width(6.481) == pytest.approx(span + 6.481, abs=1e-6)
