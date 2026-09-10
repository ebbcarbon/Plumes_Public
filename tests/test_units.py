"""Unit-selector resolution.

The decisive tests are the ones that reproduce case00's echoed values from its stored
ones, since that pair is the only direct evidence for the flag map, and the ones that
assert an unknown selector *raises*. Silently defaulting to SI is the failure mode this
module exists to prevent.
"""

from __future__ import annotations

import pytest

from plumes2.io.csv_tables import TableKind
from plumes2.io.dat import read_dat
from plumes2.io.prj import read_prj
from plumes2.units import (
    FEET_TO_METRES,
    MGD_TO_CUBIC_METRES_PER_SECOND,
    DensityRequiredError,
    UnknownUnitFlagError,
    convert_row_to_si,
    convert_to_si,
    describe,
    evidenced_options,
    selector_for_column,
    unit_for,
)
from tests.conftest import REFERENCE_CASES, UPSTREAM

LEGACY_PRJ = REFERENCE_CASES / "case00_legacy_fps" / "project.prj"
LEGACY_DAT = REFERENCE_CASES / "case00_legacy_fps" / "ModelResults_legacy1.dat"


class TestConstants:
    def test_feet(self) -> None:
        assert FEET_TO_METRES == 0.3048

    def test_mgd(self) -> None:
        assert MGD_TO_CUBIC_METRES_PER_SECOND == pytest.approx(0.0438126, rel=1e-6)
        # The upstream example's 8 MGD is a familiar 0.35 m3/s.
        assert 8.0 * MGD_TO_CUBIC_METRES_PER_SECOND == pytest.approx(0.3505, abs=1e-4)


class TestSelectorAlignment:
    def test_diffuser_maps_one_to_one(self) -> None:
        selectors = [1, 1, 1, 1, 1, 2, 1, 1, 1]
        # port_spacing is column index 5.
        assert selector_for_column(TableKind.DIFFUSER, selectors, 5) == 2
        assert selector_for_column(TableKind.DIFFUSER, selectors, 0) == 1

    def test_offset_tables_skip_a_leading_selector(self) -> None:
        # Effluent flow is column 0 but its selector is index 1.
        assert selector_for_column(TableKind.EFFLUENT, [1, 2, 1, 1, 1], 0) == 2
        assert selector_for_column(TableKind.MIXING_ZONE, [1, 2, 2], 0) == 2
        assert selector_for_column(TableKind.MIXING_ZONE, [1, 2, 2], 1) == 2

    def test_out_of_range_column_raises(self) -> None:
        with pytest.raises(UnknownUnitFlagError, match="only 3 selectors"):
            selector_for_column(TableKind.MIXING_ZONE, [1, 2, 2], 5)


class TestCase00ReproducesItsOwnEchoedValues:
    """The only direct evidence for the map: stored -> SI must match the .dat echo."""

    def test_spacing_and_mixing_zone_distances(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        echo = read_dat(LEGACY_DAT).echoed_tables["Diffuser"].iloc[0]

        spacing_flag = selector_for_column(TableKind.DIFFUSER, prj.diffuser.unit_flags, 5)
        spacing = convert_to_si(
            TableKind.DIFFUSER, "port_spacing", spacing_flag, prj.diffuser.rows[0][5]
        )
        assert spacing == pytest.approx(echo["Spacing"], abs=0.005)

        for index, column, echoed in (
            (0, "acute_distance", "AcuteMZ"),
            (1, "chronic_distance", "ChrncMZ"),
        ):
            flag = selector_for_column(TableKind.MIXING_ZONE, prj.mixing_zone.unit_flags, index)
            value = convert_to_si(
                TableKind.MIXING_ZONE, column, flag, prj.mixing_zone.rows[0][index]
            )
            assert value == pytest.approx(echo[echoed], abs=0.005)

    def test_flag_1_columns_pass_through(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        echo = read_dat(LEGACY_DAT).echoed_tables["Diffuser"].iloc[0]
        row = convert_row_to_si(TableKind.DIFFUSER, prj.diffuser.unit_flags, prj.diffuser.rows[0])
        # elevation, angles, port count and depth are all flag 1 here.
        assert row[1] == pytest.approx(echo["P-elev"])
        assert row[2] == pytest.approx(echo["V-angle"])
        assert row[4] == pytest.approx(echo["Ports"])
        assert row[6] == pytest.approx(echo["P-depth"])

    def test_flow_flag_2_is_volumetric(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        flag = selector_for_column(TableKind.EFFLUENT, prj.effluent.unit_flags, 0)
        assert flag == 2
        flow = convert_to_si(TableKind.EFFLUENT, "flow", flag, prj.effluent.rows[0][0])
        assert flow == pytest.approx(0.005)  # already m3/s, no rescale

    def test_describe_reports_the_feet_columns(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        assert describe(TableKind.DIFFUSER, prj.diffuser.unit_flags)["port_spacing"] == "ft"
        assert describe(TableKind.MIXING_ZONE, prj.mixing_zone.unit_flags) == {
            "acute_distance": "ft",
            "chronic_distance": "ft",
        }


class TestModernFiles:
    def test_upstream_example_flow_is_mgd(self) -> None:
        prj = read_prj(UPSTREAM / "Example_project" / "Example_project.prj")
        flag = selector_for_column(TableKind.EFFLUENT, prj.effluent.unit_flags, 0)
        assert flag == 1
        flow = convert_to_si(TableKind.EFFLUENT, "flow", flag, prj.effluent.rows[0][0])
        assert flow == pytest.approx(8.0 * MGD_TO_CUBIC_METRES_PER_SECOND)

    def test_case01_flow_is_cms_and_23x_larger(self) -> None:
        """The finding that started all this: the same stored 0.005 differs 23x."""
        case01 = read_prj(REFERENCE_CASES / "case01_cms" / "project.prj")
        case03 = read_prj(REFERENCE_CASES / "case03_carbonate" / "test.prj")
        as_cms = convert_to_si(
            TableKind.EFFLUENT,
            "flow",
            selector_for_column(TableKind.EFFLUENT, case01.effluent.unit_flags, 0),
            case01.effluent.rows[0][0],
        )
        as_mgd = convert_to_si(
            TableKind.EFFLUENT,
            "flow",
            selector_for_column(TableKind.EFFLUENT, case03.effluent.unit_flags, 0),
            case03.effluent.rows[0][0],
        )
        assert case01.effluent.rows[0][0] == case03.effluent.rows[0][0] == pytest.approx(0.005)
        assert as_cms == pytest.approx(0.005)
        assert as_cms / as_mgd == pytest.approx(22.8, abs=0.1)

    def test_every_repo_prj_resolves_without_guessing(self) -> None:
        """No file in the repo should need an unevidenced or unknown selector."""
        from tests.conftest import ALL_PRJ_PATHS

        for path in ALL_PRJ_PATHS:
            prj = read_prj(path)
            for kind, table in (
                (TableKind.DIFFUSER, prj.diffuser),
                (TableKind.EFFLUENT, prj.effluent),
                (TableKind.MIXING_ZONE, prj.mixing_zone),
                (TableKind.AMBIENT, prj.ambient),
            ):
                convert_row_to_si(kind, table.unit_flags, table.rows[0])


class TestStrictness:
    def test_unknown_selector_raises_not_defaults(self) -> None:
        with pytest.raises(UnknownUnitFlagError, match="selector 7 is not established"):
            convert_to_si(TableKind.DIFFUSER, "port_spacing", 7, 1.0)

    def test_the_message_says_why_guessing_is_refused(self) -> None:
        with pytest.raises(UnknownUnitFlagError, match="silently rescale"):
            convert_to_si(TableKind.DIFFUSER, "port_spacing", 3, 1.0)

    def test_unregistered_column_raises(self) -> None:
        with pytest.raises(UnknownUnitFlagError, match="no unit registry"):
            convert_to_si(TableKind.AMBIENT_CHEM, "total_alkalinity", 1, 1.0)

    def test_temperature_flag_2_is_fahrenheit(self) -> None:
        """Was refused until the GUI inventory confirmed degF is a real option.

        Affine, so it cannot be a bare multiplier: 50 degF is 10 degC, and 32 degF is 0.
        """
        assert convert_to_si(TableKind.EFFLUENT, "temperature", 2, 50.0) == pytest.approx(10.0)
        assert convert_to_si(TableKind.EFFLUENT, "temperature", 2, 32.0) == pytest.approx(0.0)
        assert convert_to_si(TableKind.AMBIENT, "temperature", 2, -40.0) == pytest.approx(-40.0)
        # Still unevidenced -- no archived .prj selects it, so the writer must not emit it.
        assert not unit_for(TableKind.EFFLUENT, "temperature", 2).evidenced
        assert 2 not in evidenced_options(TableKind.EFFLUENT, "temperature")

    def test_mass_fraction_needs_a_density(self) -> None:
        """kg/kg is not a scale factor: the answer depends on the fluid it is dissolved in."""
        with pytest.raises(DensityRequiredError, match="needs a density"):
            convert_to_si(TableKind.EFFLUENT, "pollutant", 2, 1e-6)
        # 1 mg/kg in water of 1000 kg/m3 is 1 mg/L; in seawater it is 1.027.
        assert convert_to_si(
            TableKind.EFFLUENT, "pollutant", 2, 1e-6, density=1000.0
        ) == pytest.approx(1.0)
        assert convert_to_si(
            TableKind.EFFLUENT, "pollutant", 2, 1e-6, density=1026.952
        ) == pytest.approx(1.026952)
        # And a density is not needed when the selector does not call for one.
        assert convert_to_si(TableKind.EFFLUENT, "pollutant", 1, 5.0) == pytest.approx(5.0)

    def test_decay_flag_2_is_per_second(self) -> None:
        """1/day is the primary unit, so a per-second rate scales up by 86400."""
        assert convert_to_si(TableKind.AMBIENT, "decay_rate", 2, 1.0) == pytest.approx(86400.0)
        assert not unit_for(TableKind.AMBIENT, "decay_rate", 2).evidenced

    def test_velocity_flag_2_is_feet_per_second(self) -> None:
        for column in ("current_speed", "farfield_speed"):
            assert convert_to_si(TableKind.AMBIENT, column, 2, 1.0) == pytest.approx(0.3048)
            assert not unit_for(TableKind.AMBIENT, column, 2).evidenced

    def test_a_whole_row_can_carry_a_mass_fraction(self) -> None:
        """The density threads through `convert_row_to_si` too."""
        selectors = [1] * 11
        selectors[6] = 2  # ambient background_pollutant -> kg/kg (leading selector offset)
        row = [0.0, 0.02, 90.0, 31.0, 10.0, 1e-6, 0.0, 0.02, 90.0, 3e-4]
        converted = convert_row_to_si(TableKind.AMBIENT, selectors, row, density=1024.0)
        assert converted[5] == pytest.approx(1.024)
        with pytest.raises(DensityRequiredError):
            convert_row_to_si(TableKind.AMBIENT, selectors, row)

    def test_angle_flag_2_is_refused(self) -> None:
        with pytest.raises(UnknownUnitFlagError):
            convert_to_si(TableKind.DIFFUSER, "vertical_angle", 2, 45.0)

    def test_evidenced_flag_is_marked(self) -> None:
        assert unit_for(TableKind.DIFFUSER, "port_spacing", 2).evidenced
        # Feet on other length columns is an inference, and says so.
        assert not unit_for(TableKind.DIFFUSER, "port_depth", 2).evidenced

    def test_row_width_is_checked(self) -> None:
        with pytest.raises(UnknownUnitFlagError, match="expected 2 values"):
            convert_row_to_si(TableKind.MIXING_ZONE, [1, 1, 1], [1.0, 2.0, 3.0])


def test_written_units_names_every_column_stored_off_its_primary_unit() -> None:
    """`plumes2 info` and the experiment note print this, so a `.prj` in feet cannot surprise.

    case55's as-run project carries the site's spacing and both mixing-zone distances in feet --
    the writer's precision-first choice (2.00 ft is exact, 0.610 m is not) -- and nothing else off
    its primary unit; the upstream example is all-metric and yields nothing.
    """
    from plumes2.io.project import written_units

    stored = written_units(
        read_prj(REFERENCE_CASES / "case55_macoma_site" / "asrun_macoma_acute.prj")
    )
    assert stored == [
        "diffuser.port_spacing: 2 ft (selector 2)",
        "mixing_zone.acute_distance: 20.7 ft (selector 2)",
        "mixing_zone.chronic_distance: 207 ft (selector 2)",
    ]
    assert written_units(read_prj(UPSTREAM / "Example_project" / "Example_project.prj")) == []
