"""CSV input table tests -- validation ledger rows 1 and 16.

Every exe-written CSV in the repo must read -> write back byte-identically, which
in particular means blanks stay blank. That last point is load-bearing: the ambient
chemistry table leaves pH blank on purpose, and a reader that turned blanks into
0.0 would both corrupt the file and hide how the exe picks its input pair.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumes2.io.csv_tables import (
    TABLE_ROWS,
    CsvTableError,
    TableKind,
    blank_table,
    parse_csv_table,
    read_csv_table,
    table_from_values,
    write_csv_table,
)
from tests.conftest import EXAMPLE_PROJECT, REFERENCE_CASES


class TestRoundTrip:
    def test_roundtrip_is_byte_identical(self, csv_path: Path) -> None:
        original = csv_path.read_bytes()
        assert read_csv_table(csv_path).to_text().encode("ascii") == original

    def test_write_then_read_is_stable(self, csv_path: Path, tmp_path: Path) -> None:
        first = read_csv_table(csv_path)
        out = tmp_path / csv_path.name
        write_csv_table(first, out)
        second = read_csv_table(out)
        assert second.kind == first.kind
        assert second.rows == first.rows

    def test_every_table_has_20_rows(self, csv_path: Path) -> None:
        assert len(read_csv_table(csv_path).rows) == TABLE_ROWS


class TestKindDetection:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("Ambient_example.csv", TableKind.AMBIENT),
            ("Diffuser_example.csv", TableKind.DIFFUSER),
            ("Effluent_example.csv", TableKind.EFFLUENT),
            ("Mixing_zone_example.csv", TableKind.MIXING_ZONE),
            ("AmbientDO_example.csv", TableKind.AMBIENT_DO),
            ("AmbientChem_example.csv", TableKind.AMBIENT_CHEM),
        ],
    )
    def test_all_six_layouts_are_identified(self, filename: str, expected: TableKind) -> None:
        assert read_csv_table(EXAMPLE_PROJECT / filename).kind is expected

    def test_ambient_and_diffuser_share_a_column_count(self) -> None:
        """Both have 10 fields; only the quoting of field 0 separates them."""
        ambient = read_csv_table(EXAMPLE_PROJECT / "Ambient_example.csv")
        diffuser = read_csv_table(EXAMPLE_PROJECT / "Diffuser_example.csv")
        assert ambient.kind.n_fields == diffuser.kind.n_fields == 10
        assert ambient.kind is not diffuser.kind

    def test_explicit_kind_overrides_inference(self) -> None:
        path = EXAMPLE_PROJECT / "AmbientDO_example.csv"
        assert read_csv_table(path, kind=TableKind.AMBIENT_DO).kind is TableKind.AMBIENT_DO

    def test_wrong_explicit_kind_is_rejected(self) -> None:
        with pytest.raises(CsvTableError, match="expects 3 fields, found 4"):
            read_csv_table(EXAMPLE_PROJECT / "AmbientDO_example.csv", kind=TableKind.MIXING_ZONE)


class TestValues:
    def test_example_diffuser_row(self) -> None:
        table = read_csv_table(EXAMPLE_PROJECT / "Diffuser_example.csv")
        row = table.rows[0]
        assert row.enabled is False
        assert row.values == pytest.approx([0.076, 0.31, 45.0, 30.0, 18.0, 6.10, 11.0, 0.0, 0.0])

    def test_port_count_is_an_unquoted_integer(self) -> None:
        raw = (EXAMPLE_PROJECT / "Diffuser_example.csv").read_bytes().decode("ascii")
        assert raw.startswith('No,"7.60E-02","3.10E-01","4.50E+01","3.00E+01",18,"6.10E+00"')

    def test_ambient_profile_columns(self) -> None:
        table = read_csv_table(EXAMPLE_PROJECT / "Ambient_example.csv")
        assert table.column("depth") == pytest.approx([0, 2, 4, 6, 8, 10, 12])
        assert table.column("salinity") == pytest.approx([32.0] * 7)
        assert table.column("dispersion_alpha") == pytest.approx([3e-4] * 7)

    def test_case_column_parsed(self) -> None:
        table = read_csv_table(REFERENCE_CASES / "case01_cms" / "diffuser.csv")
        assert table.rows[0].enabled is True
        assert [row.enabled for row in table.rows[1:]] == [False] * 19
        assert len(table.active_rows()) == 1

    def test_effluent_has_eight_stored_flow_cases(self) -> None:
        table = read_csv_table(REFERENCE_CASES / "case01_cms" / "effluent.csv")
        assert len(table.used_rows()) == 8
        assert len(table.active_rows()) == 1
        assert table.active_rows()[0].values[0] == pytest.approx(0.005)


class TestBlankFields:
    def test_ambient_chem_ph_column_is_blank_not_zero(self) -> None:
        """case03 leaves pH blank; that is how we know the exe derives it."""
        table = read_csv_table(REFERENCE_CASES / "case03_carbonate" / "testco2.csv")
        first = table.rows[0]
        assert first.values[0] == pytest.approx(1.0)  # depth
        assert first.values[1] == pytest.approx(3000.0)  # TA
        assert first.values[2] == pytest.approx(2500.0)  # DIC
        assert first.values[3] is None  # pH: deliberately blank
        assert first.values[4] == pytest.approx(100.0)  # Ca

    def test_blank_survives_a_roundtrip(self, tmp_path: Path) -> None:
        path = REFERENCE_CASES / "case03_carbonate" / "testco2.csv"
        out = tmp_path / "chem.csv"
        write_csv_table(read_csv_table(path), out)
        assert out.read_bytes() == path.read_bytes()
        assert read_csv_table(out).rows[0].values[3] is None

    def test_blank_diffuser_port_count_is_a_bare_field(self) -> None:
        """Unused diffuser rows write ,, for the integer column, not ,"",."""
        raw = (EXAMPLE_PROJECT / "Diffuser_example.csv").read_bytes().decode("ascii")
        assert 'No,"","","","",,"","","",""' in raw


class TestConstruction:
    def test_blank_table_is_padded_and_disabled(self) -> None:
        table = blank_table(TableKind.DIFFUSER)
        assert len(table.rows) == TABLE_ROWS
        assert all(row.is_blank for row in table.rows)
        assert table.used_rows() == []

    def test_blank_table_matches_an_empty_exe_table(self) -> None:
        table = blank_table(TableKind.MIXING_ZONE)
        assert table.to_text().split("\r\n")[0] == 'No,"",""'

    def test_table_from_values_enables_only_the_first_case(self) -> None:
        table = table_from_values(
            TableKind.EFFLUENT, [[0.005, 35.0, 10.0, 1e5], [0.01, 35.0, 10.0, 1e3]]
        )
        assert [row.enabled for row in table.rows[:3]] == [True, False, False]
        assert len(table.used_rows()) == 2

    def test_table_from_values_checks_width(self) -> None:
        with pytest.raises(CsvTableError, match="row 0 has 3 values, expected 2"):
            table_from_values(TableKind.MIXING_ZONE, [[1.0, 2.0, 3.0]])

    def test_too_many_rows_is_rejected(self) -> None:
        with pytest.raises(CsvTableError, match="at most 20 rows"):
            table_from_values(TableKind.MIXING_ZONE, [[1.0, 2.0]] * 21)


class TestErrors:
    def test_unknown_layout_is_rejected(self) -> None:
        with pytest.raises(CsvTableError, match="no known table has 7 fields"):
            parse_csv_table('"1","2","3","4","5","6","7"\r\n')

    def test_bad_case_flag_is_rejected(self) -> None:
        with pytest.raises(CsvTableError, match="case column is 'Maybe'"):
            parse_csv_table('Maybe,"1.00E+00","2.00E+00"\r\n')

    def test_ragged_row_is_rejected(self) -> None:
        text = 'No,"1.00E+00","2.00E+00"\r\nNo,"1.00E+00"\r\n'
        with pytest.raises(CsvTableError, match="line 2 has 2 fields"):
            parse_csv_table(text)

    def test_empty_file_is_rejected(self) -> None:
        with pytest.raises(CsvTableError, match="file is empty"):
            parse_csv_table("")
