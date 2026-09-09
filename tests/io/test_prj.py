"""`.prj` reader/writer tests.

The load-bearing one is :func:`test_roundtrip_is_byte_identical` -- validation
ledger rows 1 and 16. Everything the exe wrote must come back out unchanged,
including the zero-padding rows and the flags whose meaning we have not decoded,
because a writer that quietly drops those would produce projects the exe mis-reads.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumes2.io.fortran import (
    format_e,
    format_real_record,
    parse_e,
    parse_real_record,
    real_record_width,
)
from plumes2.io.prj import (
    LINE_TERMINATOR,
    TABLE_ROWS,
    PrjFormatError,
    parse_prj,
    read_prj,
    write_prj,
)


class TestFortranFormat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.0, "0.000E+00"),
            (0.076, "0.760E-01"),
            (0.31, "0.310E+00"),
            (45.0, "0.450E+02"),
            (1.0, "0.100E+01"),
            (0.61, "0.610E+00"),
            (18.0, "0.180E+02"),
            (0.0003, "0.300E-03"),
            (100000.0, "0.100E+06"),
            (0.1, "0.100E+00"),
            (1000.0, "0.100E+04"),
            (-0.076, "-0.760E-01"),
        ],
    )
    def test_known_values(self, value: float, expected: str) -> None:
        assert format_e(value) == expected

    def test_rounding_carry_renormalises(self) -> None:
        # 0.9999 must not render as '1.000E+00'; the mantissa stays in [0.1, 1).
        assert format_e(0.99999) == "0.100E+01"

    @pytest.mark.parametrize("value", [0.0, 0.076, 45.0, 1e-4, 3.5e5, 0.0003])
    def test_roundtrip_through_text(self, value: float) -> None:
        # Three mantissa digits, so agreement is to a part in 1000.
        assert parse_e(format_e(value)) == pytest.approx(value, rel=1e-3)

    @pytest.mark.parametrize(("n", "width"), [(1, 10), (2, 22), (4, 46), (9, 106), (10, 118)])
    def test_record_widths_match_the_exe(self, n: int, width: int) -> None:
        """These five widths are the ones actually observed in the .prj files."""
        assert real_record_width(n) == width
        assert len(format_real_record([1.0] * n)) == width

    def test_d_exponent_marker_is_tolerated(self) -> None:
        assert parse_e("0.760D-01") == pytest.approx(0.076)


class TestRoundTrip:
    def test_roundtrip_is_byte_identical(self, prj_path: Path) -> None:
        """Ledger rows 1 and 16: read -> write -> compare bytes."""
        original = prj_path.read_bytes()
        rewritten = read_prj(prj_path).to_text().encode("ascii")
        assert rewritten == original

    def test_write_then_read_is_stable(self, prj_path: Path, tmp_path: Path) -> None:
        first = read_prj(prj_path)
        out = tmp_path / prj_path.name
        write_prj(first, out)
        assert read_prj(out).to_text() == first.to_text()

    def test_uses_crlf_and_terminates_final_line(self, prj_path: Path) -> None:
        raw = prj_path.read_bytes()
        assert raw.endswith(LINE_TERMINATOR.encode("ascii"))
        assert b"\n" not in raw.replace(b"\r\n", b"")

    def test_lf_input_is_accepted(self, prj_path: Path) -> None:
        """A file that lost its CRLF (e.g. to git normalisation) still parses."""
        lf_text = prj_path.read_bytes().decode("ascii").replace("\r\n", "\n")
        assert parse_prj(lf_text).to_text() == read_prj(prj_path).to_text()


class TestStructure:
    def test_example_project_fields(self, example_prj: Path) -> None:
        prj = read_prj(example_prj)
        assert prj.description == "Project Description"
        assert prj.output_filename == "ModelResults_TxtOutputs"
        assert prj.output_interval == 5
        # Visual Plumes parity defaults, PORTING_NOTES section 3.
        assert prj.aspiration_coefficient == pytest.approx(0.1)
        assert prj.contraction_coefficient == pytest.approx(1.0)
        assert prj.light_absorption == pytest.approx(0.16)
        # Position 4 is the max rise/fall switch.
        assert prj.nearfield_flags[3] == 2
        assert prj.nearfield_plot_variables == [
            "FluxAvg-Dilution",
            "Plume-Diameter",
            "Position-Xdir",
            "Position-Ydir",
            "Plume-Depth",
        ]
        assert prj.farfield_plot_variables == ["Dilution", "P-Width", "Distance", "Time"]

    def test_example_diffuser_row(self, example_prj: Path) -> None:
        prj = read_prj(example_prj)
        row = prj.diffuser.rows[0]
        # dia, elevation, vertical angle, horizontal angle, ports, spacing, depth, X, Y
        assert row == pytest.approx([0.076, 0.31, 45.0, 30.0, 18.0, 6.10, 11.0, 0.0, 0.0])

    def test_all_tables_are_padded_to_20_rows(self, prj_path: Path) -> None:
        prj = read_prj(prj_path)
        for table in (prj.diffuser, prj.effluent, prj.mixing_zone, prj.ambient):
            assert len(table.rows) == TABLE_ROWS

    def test_unit_flag_counts_are_per_column(self, prj_path: Path) -> None:
        """The integer blocks size with the columns -- that is why they are unit
        selectors rather than the 20 per-row case enables."""
        prj = read_prj(prj_path)
        assert len(prj.diffuser.unit_flags) == 9
        assert prj.diffuser.n_columns == 9
        assert len(prj.mixing_zone.unit_flags) == 3
        assert prj.mixing_zone.n_columns == 2
        assert len(prj.ambient.unit_flags) == 11
        assert prj.ambient.n_columns == 10

    def test_case01_flow_unit_flag_differs(self) -> None:
        """case01 stores flow in cms where the example uses MGD -- the flag that
        proved these blocks rescale physical values."""
        from tests.conftest import REFERENCE_CASES

        prj = read_prj(REFERENCE_CASES / "case01_cms" / "project.prj")
        assert prj.effluent.unit_flags == [1, 2, 1, 1, 1]
        assert prj.effluent.rows[0][0] == pytest.approx(0.005)

    def test_ambient_used_rows(self, example_prj: Path) -> None:
        used = read_prj(example_prj).ambient.used_rows()
        assert len(used) == 7
        assert [row[0] for row in used] == pytest.approx([0, 2, 4, 6, 8, 10, 12])

    def test_variable_length_name_lists(self) -> None:
        """Name lists are count-prefixed, so files differ in total line count."""
        from tests.conftest import REFERENCE_CASES

        case01 = read_prj(REFERENCE_CASES / "case01_cms" / "project.prj")
        case03 = read_prj(REFERENCE_CASES / "case03_carbonate" / "test.prj")
        assert len(case01.nearfield_plot_variables) == 9
        assert len(case03.nearfield_plot_variables) == 5
        assert "Plume-Density" in case01.nearfield_plot_variables


class TestErrors:
    def test_trailing_records_are_rejected(self, example_prj: Path) -> None:
        text = example_prj.read_bytes().decode("ascii") + "surprise\r\n"
        with pytest.raises(PrjFormatError, match="unexpected trailing record"):
            parse_prj(text)

    def test_truncated_file_is_rejected(self, example_prj: Path) -> None:
        lines = example_prj.read_bytes().decode("ascii").split("\r\n")[:40]
        with pytest.raises(PrjFormatError, match="file ended while reading"):
            parse_prj("\r\n".join(lines) + "\r\n")

    def test_error_message_locates_the_bad_record(self, example_prj: Path) -> None:
        lines = example_prj.read_bytes().decode("ascii").split("\r\n")
        lines[10] = "not a number at all"
        with pytest.raises(PrjFormatError, match="line 11 reading diffuser row 0"):
            parse_prj("\r\n".join(lines))


class TestNegativeReals:
    """The sign convention, which no archived project exercised until case22."""

    def test_a_negative_keeps_the_field_width(self) -> None:
        """The sign eats a leading space rather than widening the field.

        Every `.prj` in the archive was non-negative throughout until case22's -45 degree
        vertical angle, so the old formatter -- which padded the magnitude and then prepended
        the sign -- produced a field one character too wide and no round-trip test could see
        it. The exe still *loaded* the file; it just was not byte-exact.
        """
        positive = format_real_record([0.2, 15.0, 45.0])
        negative = format_real_record([0.2, 15.0, -45.0])
        # Identical length: the sign occupies a space that was already there, so the record
        # does not grow at all. The old formatter made this one character longer.
        assert len(negative) == len(positive)
        assert negative.endswith("-0.450E+02")
        assert positive.endswith(" 0.450E+02")
        # Both numbers end on the same column; only the start moves.
        assert negative.index("-0.450E+02") == positive.index("0.450E+02") - 1
        # Earlier fields are untouched.
        assert negative[:22] == positive[:22]

    def test_negative_reals_round_trip(self) -> None:
        for values in ([-45.0], [0.2, -45.0, 90.0], [-0.076, -1.0, 0.0]):
            assert parse_real_record(format_real_record(values)) == pytest.approx(values)
