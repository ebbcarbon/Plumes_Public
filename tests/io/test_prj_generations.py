"""The `.prj` format varies between exe builds.

`reference_cases/case00_macoma_legacy_fps/Macoma.prj` (Dec 2025) writes one near-field
plot flag where every 2026 file writes four. Reading both plot blocks greedily up to
the next text record handles both, and these tests pin that plus the unit-flag mapping
that the case00 `.prj`/`.dat` pair decoded.
"""

from __future__ import annotations

import pytest

from plumes2.io.dat import read_dat
from plumes2.io.prj import read_prj
from tests.conftest import REFERENCE_CASES, UPSTREAM

LEGACY_PRJ = REFERENCE_CASES / "case00_macoma_legacy_fps" / "Macoma.prj"
LEGACY_DAT = REFERENCE_CASES / "case00_macoma_legacy_fps" / "ModelResults_Macoma1.dat"
MODERN_PRJ = REFERENCE_CASES / "case01_macoma_cms" / "Macoma2.prj"
FEET = 0.3048


class TestBuildGenerations:
    def test_legacy_has_one_nearfield_plot_flag(self) -> None:
        assert read_prj(LEGACY_PRJ).nearfield_plot_flags == [1]

    def test_modern_has_four(self) -> None:
        assert read_prj(MODERN_PRJ).nearfield_plot_flags == [1, 1, 0, 0]

    def test_both_have_seven_farfield_flags(self) -> None:
        assert len(read_prj(LEGACY_PRJ).farfield_flags) == 7
        assert len(read_prj(MODERN_PRJ).farfield_flags) == 7

    def test_line_counts_differ_as_the_layout_predicts(self) -> None:
        """147 vs 149: legacy has 3 fewer flags but one more variable name."""
        legacy_lines = LEGACY_PRJ.read_bytes().decode("ascii").rstrip("\r\n").count("\r\n") + 1
        modern_lines = MODERN_PRJ.read_bytes().decode("ascii").rstrip("\r\n").count("\r\n") + 1
        assert (legacy_lines, modern_lines) == (147, 149)

    def test_legacy_contributes_the_plume_temp_variable(self) -> None:
        """`Plume-Temp` appears in no 2026 project, and matches case00's P-Temp column."""
        names = read_prj(LEGACY_PRJ).nearfield_plot_variables
        assert names[6] == "Plume-Temp"
        assert len(names) == 10
        assert "P-Temp" in LEGACY_DAT.read_bytes().decode("ascii")

    def test_legacy_roundtrips_byte_exactly(self) -> None:
        assert read_prj(LEGACY_PRJ).to_text().encode("ascii") == LEGACY_PRJ.read_bytes()


class TestUnitFlagDecode:
    """The case00 pair reads the flag->unit map straight off: 1 = primary, 2 = alternate."""

    def test_diffuser_flags_map_directly_to_columns(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        # Only spacing (column index 5) carries the alternate-unit flag.
        assert prj.diffuser.unit_flags == [1, 1, 1, 1, 1, 2, 1, 1, 1]
        assert prj.diffuser.rows[0][5] == pytest.approx(2.0)

    def test_spacing_flag_2_means_feet(self) -> None:
        stored = read_prj(LEGACY_PRJ).diffuser.rows[0][5]
        echoed = read_dat(LEGACY_DAT).echoed_tables["Diffuser"]["Spacing"].iloc[0]
        assert echoed == pytest.approx(stored * FEET, abs=0.005)

    def test_mixing_zone_flags_are_offset_by_one(self) -> None:
        """3 flags for 2 columns; flags[1:] map to the columns, both in feet here."""
        prj = read_prj(LEGACY_PRJ)
        assert prj.mixing_zone.unit_flags == [1, 2, 2]
        stored_acute, stored_chronic = prj.mixing_zone.rows[0]
        diffuser = read_dat(LEGACY_DAT).echoed_tables["Diffuser"]
        assert diffuser["AcuteMZ"].iloc[0] == pytest.approx(stored_acute * FEET, abs=0.005)
        assert diffuser["ChrncMZ"].iloc[0] == pytest.approx(stored_chronic * FEET, abs=0.005)

    def test_effluent_flow_flag_is_the_second_flag(self) -> None:
        """Flow is column 0 but its unit selector is flags[1] -- offset by one."""
        prj = read_prj(LEGACY_PRJ)
        assert prj.effluent.unit_flags == [1, 2, 1, 1, 1]
        assert prj.effluent.rows[0][0] == pytest.approx(0.005)
        # Flag 2 on flow means volumetric, labelled (m3/s) by this build and (cms) later.
        assert "(m3/s)" in LEGACY_DAT.read_bytes().decode("ascii")

    def test_flag_1_columns_are_not_rescaled(self) -> None:
        prj = read_prj(LEGACY_PRJ)
        diffuser = read_dat(LEGACY_DAT).echoed_tables["Diffuser"]
        for column, index in (("P-elev", 1), ("V-angle", 2), ("H-angle", 3), ("P-depth", 6)):
            assert prj.diffuser.unit_flags[index] == 1
            assert diffuser[column].iloc[0] == pytest.approx(prj.diffuser.rows[0][index])

    def test_modern_files_use_the_same_flow_flag_convention(self) -> None:
        """case01 stores 0.005 with flag 2 and its .dat header says (cms)."""
        prj = read_prj(MODERN_PRJ)
        assert prj.effluent.unit_flags == [1, 2, 1, 1, 1]
        dat = REFERENCE_CASES / "case01_macoma_cms" / "ModelResults_TxtOutputs.dat"
        assert "(cms)" in dat.read_bytes().decode("ascii")
        example = UPSTREAM / "Example_project" / "ModelResults_TxtOutputs.dat"
        assert "(MGD)" in example.read_bytes().decode("ascii")


class TestShorelineIsStillInert:
    def test_no_prj_in_the_repo_has_a_nonzero_shoreline_vector(self) -> None:
        """The runs that set one were never saved, so the convention stays unknown."""
        from tests.conftest import ALL_PRJ_PATHS

        for path in ALL_PRJ_PATHS:
            assert read_prj(path).shoreline == [0.0, 0.0], path

    def test_enabled_shoreline_run_still_ends_on_trapping(self) -> None:
        """case12: checkbox on, 60 degrees, 5 m -- and the plume travels to y = 5.389 m."""
        dat = read_dat(
            REFERENCE_CASES / "case12_macoma_shoreline_enabled" / "test13_TxtOutputs.dat"
        )
        assert dat.final_step == 400
        assert set(dat.event_steps()) == {"Local maximum rise or fall", "Plume traps"}
        assert dat.nearfield["y-posn"].max() == pytest.approx(5.389)
        assert dat.wastefield_width == pytest.approx(49.76)
