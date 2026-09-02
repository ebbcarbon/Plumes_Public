"""`.dat` reader tests.

These assert the specific numbers the reference cases established, so the reader
is pinned against the same facts the physics phases will be validated on.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plumes2.io.dat import DatFormatError, parse_dat, read_dat
from tests.conftest import ALL_DAT_PATHS, EXAMPLE_PROJECT, REFERENCE_CASES

CASE00 = REFERENCE_CASES / "case00_macoma_legacy_fps" / "ModelResults_Macoma1.dat"
CASE01 = REFERENCE_CASES / "case01_macoma_cms" / "ModelResults_TxtOutputs.dat"
CASE02 = REFERENCE_CASES / "case02_macoma_mgd" / "Macomatest1.dat"
CASE03 = REFERENCE_CASES / "case03_macoma_carbonate" / "test2_TxtOutputs.dat"
CASE05 = REFERENCE_CASES / "case05_macoma_merging" / "test4_TxtOutputs.dat"
CASE06 = REFERENCE_CASES / "case06_macoma_arag_s36" / "test5_TxtOutputs.dat"
EXAMPLE = EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat"

#: case00 is a header-only artifact from an older build with no step rows, so it
#: cannot satisfy the "every file parses into a step table" contract.
PARSEABLE = [path for path in ALL_DAT_PATHS if path != CASE00]


class TestEveryFileParses:
    @pytest.mark.parametrize("path", PARSEABLE, ids=lambda p: p.parent.name)
    def test_parses_with_a_step_table(self, path: Path) -> None:
        dat = read_dat(path)
        assert not dat.nearfield.empty
        assert dat.nearfield.index.name == "Step"

    @pytest.mark.parametrize("path", PARSEABLE, ids=lambda p: p.parent.name)
    def test_echoes_ambient_and_diffuser(self, path: Path) -> None:
        dat = read_dat(path)
        assert "Ambient" in dat.echoed_tables
        assert "Diffuser" in dat.echoed_tables


class TestUpstreamExample:
    def test_shape_and_headline_numbers(self) -> None:
        dat = read_dat(EXAMPLE)
        assert list(dat.nearfield.columns) == ["Dilutn", "P-dia", "x-posn", "y-posn", "Depth"]
        assert dat.final_step == 275
        # Ledger rows 5 and 6.
        assert dat.nearfield.loc[275, "Dilutn"] == pytest.approx(169.754)
        assert dat.wastefield_width == pytest.approx(109.59)
        assert dat.eddy_diffusivity_law == "4/3 Power Law"

    @pytest.mark.parametrize(
        ("trace", "law"),
        [
            ("eddy_law_constant.dat", "Constant"),
            ("eddy_law_linear.dat", "Linearly Varying"),
        ],
    )
    def test_the_other_two_eddy_law_headers_parse(self, trace: str, law: str) -> None:
        """case50: only the 4/3 header carries the word `based`; the reader used to require it.

        Before 2026-08-26 a trace headed `Constant Eddy Diffusivity is used:` parsed with
        `farfield=None` and no error -- the preamble fell through to the unheaded-table branch,
        which found no rows. Both non-default laws now parse, and the writer reproduces the
        preamble byte for byte (the archive-wide round trip covers the two traces).
        """
        from plumes2.io.dat_format import format_eddy_law

        dat = read_dat(f"reference_cases/case50_eddy_law_selector/{trace}")
        assert dat.eddy_diffusivity_law == law
        assert dat.farfield is not None and len(dat.farfield) > 200
        assert dat.farfield["Dilution"].iloc[0] == pytest.approx(562.633)
        assert format_eddy_law(law) == f"{law} Eddy Diffusivity is used:"
        assert format_eddy_law("4/3 Power Law") == "4/3 Power Law based Eddy Diffusivity is used:"
        with pytest.raises(ValueError, match="unknown eddy-diffusivity law"):
            format_eddy_law("Quadratic")

    def test_event_sequence(self) -> None:
        """Ledger row 4: trap 255, merge 260, surface 275."""
        steps = read_dat(EXAMPLE).event_steps()
        assert steps["Plume traps"] == [255]
        assert steps["merging happened"] == [260]
        assert steps["Plume surfaces"] == [275]

    def test_farfield_reaches_the_chronic_mixing_zone(self) -> None:
        """Ledger row 8: 178.408 at 104.435 m."""
        dat = read_dat(EXAMPLE)
        assert dat.farfield is not None
        assert len(dat.farfield) == 21
        last = dat.farfield.iloc[-1]
        assert last["Dilution"] == pytest.approx(178.408)
        assert last["Distance"] == pytest.approx(104.435)


class TestColumnSetsVary:
    def test_case01_has_nine_columns(self) -> None:
        assert list(read_dat(CASE01).nearfield.columns) == [
            "Dilutn",
            "P-dia",
            "x-posn",
            "y-posn",
            "Depth",
            "P-Den",
            "P-Con.",
            "CL-Dil",
            "Time",
        ]

    def test_case02_has_a_different_nine(self) -> None:
        assert list(read_dat(CASE02).nearfield.columns) == [
            "Dilutn",
            "P-dia",
            "x-posn",
            "y-posn",
            "Depth",
            "CL-Dil",
            "Amb-Curr",
            "Time",
            "Net-Dil",
        ]

    def test_chemistry_columns_are_appended(self) -> None:
        columns = list(read_dat(CASE03).nearfield.columns)
        assert columns[-7:] == ["TA", "DIC", "pH", "OmegaC", "OmegaA", "R_cal", "R_arg"]


class TestFarfieldPresence:
    def test_case01_has_no_farfield(self) -> None:
        """Ledger row 34: the section can be absent entirely."""
        dat = read_dat(CASE01)
        assert not dat.has_farfield
        assert not dat.merged
        assert dat.final_step == 420

    def test_case02_runs_farfield_while_unmerged(self) -> None:
        """Ledger row 33: the advisory is independent of whether Brooks runs."""
        dat = read_dat(CASE02)
        assert dat.has_farfield
        assert not dat.merged
        assert dat.farfield is not None
        assert dat.farfield.iloc[-1]["Distance"] == pytest.approx(501.611)

    def test_case05_merged_has_no_advisory(self) -> None:
        dat = read_dat(CASE05)
        assert dat.merged
        assert dat.has_farfield
        assert dat.wastefield_width == pytest.approx(16.83)


class TestTruncatedTerminationRow:
    def test_case05_final_row_is_off_interval_and_short(self) -> None:
        """Ledger row 54: step 417 carries only the five base variables."""
        dat = read_dat(CASE05)
        assert dat.final_step == 417
        row = dat.nearfield.loc[417]
        assert row["Dilutn"] == pytest.approx(198.986)
        assert row["P-dia"] == pytest.approx(2.428)
        # Chemistry columns are absent on this row.
        assert pd.isna(row["TA"])
        assert pd.isna(row["R_arg"])
        # The preceding on-interval row is complete.
        assert dat.nearfield.loc[415, "TA"] == pytest.approx(2938.511)

    def test_case06_also_truncates(self) -> None:
        dat = read_dat(CASE06)
        assert dat.final_step == 356
        assert pd.isna(dat.nearfield.loc[356, "OmegaA"])


class TestLegacyBuild:
    def test_header_only_file_parses_with_an_empty_step_table(self) -> None:
        """case00 emitted no steps; its echoed tables are still the useful part --
        they are what decoded the .prj unit flags."""
        dat = read_dat(CASE00)
        assert not dat.has_nearfield
        assert dat.nearfield.empty
        assert "Ambient" in dat.echoed_tables
        assert "Diffuser" in dat.echoed_tables
        with pytest.raises(DatFormatError, match="no final step"):
            _ = dat.final_step

    def test_bare_unit_row_style_is_handled(self) -> None:
        """The Dec-2025 build writes 'm/s' where 2026 writes '(m/s)'."""
        raw = CASE00.read_bytes().decode("ascii")
        assert "\n         m       m/s       deg" in raw.replace("\r\n", "\n")
        ambient = parse_dat(raw).echoed_tables["Ambient"]
        assert ambient["Amb-sal"].iloc[0] == pytest.approx(30.9)

    def test_legacy_feet_conversion_is_visible_in_the_echo(self) -> None:
        """Ledger row 49: spacing and both MZ distances rescaled by 0.3048."""
        text = CASE00.read_bytes().decode("ascii").replace("\r\n", "\n")
        row = next(line for line in text.split("\n") if line.strip().startswith("0.01"))
        values = [float(token) for token in row.split()]
        assert values[5] == pytest.approx(0.61, abs=0.01)  # 2.00 ft
        assert values[6] == pytest.approx(6.31, abs=0.01)  # 20.70 ft
        assert values[7] == pytest.approx(63.09, abs=0.01)  # 207.00 ft


class TestEchoedTables:
    def test_ambient_echo_matches_the_input_profile(self) -> None:
        ambient = read_dat(EXAMPLE).echoed_tables["Ambient"]
        assert len(ambient) == 7
        assert ambient["Depth"].tolist() == pytest.approx([0, 2, 4, 6, 8, 10, 12])
        assert ambient["Amb-sal"].tolist() == pytest.approx([32.0] * 7)

    def test_diffuser_echo_reveals_the_flow_unit(self) -> None:
        """The header text is how we decoded flag 1 -> MGD, flag 2 -> cms."""
        assert "(MGD)" in EXAMPLE.read_bytes().decode("ascii")
        assert "(cms)" in CASE01.read_bytes().decode("ascii")
