"""Project bundles and the YAML case format.

The load-bearing assertions are that every project in the repo converts to a validated
Case with the right physical numbers, that case01's known `.prj`-vs-CSV disagreement is
detected rather than glossed over, and that a Case survives a YAML round trip.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from plumes2.config import EffluentChemistry, GeometryWarning, PHScale
from plumes2.io.csv_tables import TableKind
from plumes2.io.project import ProjectDriftWarning, load_project
from plumes2.io.yaml_case import dump_case, dumps_case, load_case, loads_case
from plumes2.units import MGD_TO_CUBIC_METRES_PER_SECOND
from tests.conftest import ALL_PRJ_PATHS, REFERENCE_CASES, UPSTREAM

EXAMPLE_PRJ = UPSTREAM / "Example_project" / "Example_project.prj"
CASE01_PRJ = REFERENCE_CASES / "case01_macoma_cms" / "Macoma2.prj"
CASE03_PRJ = REFERENCE_CASES / "case03_macoma_carbonate" / "test.prj"
LEGACY_PRJ = REFERENCE_CASES / "case00_macoma_legacy_fps" / "Macoma.prj"


def _load(path: Path) -> object:
    """Load without the drift/geometry warnings turning into noise."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_project(path, warn_on_drift=False)


class TestEveryProjectConverts:
    @pytest.mark.parametrize("path", ALL_PRJ_PATHS, ids=lambda p: p.parent.name)
    def test_to_case(self, path: Path) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            case = load_project(path, warn_on_drift=False).to_case()
        assert case.diffuser.n_ports >= 1
        assert case.effluent.flow > 0
        assert len(case.ambient.levels) >= 1


class TestUpstreamExample:
    def test_physical_values_are_si(self) -> None:
        case = _load(EXAMPLE_PRJ).to_case()  # type: ignore[attr-defined]
        assert case.diffuser.port_diameter == pytest.approx(0.076)
        assert case.diffuser.n_ports == 18
        assert case.diffuser.port_spacing == pytest.approx(6.10)
        assert case.diffuser.port_depth == pytest.approx(11.0)
        # 8 MGD becomes m3/s.
        assert case.effluent.flow == pytest.approx(8.0 * MGD_TO_CUBIC_METRES_PER_SECOND)
        assert case.mixing_zone.chronic_distance == pytest.approx(102.0)

    def test_ambient_profile_has_seven_levels(self) -> None:
        case = _load(EXAMPLE_PRJ).to_case()  # type: ignore[attr-defined]
        assert [level.depth for level in case.ambient.levels] == pytest.approx(
            [0, 2, 4, 6, 8, 10, 12]
        )
        assert all(level.salinity == pytest.approx(32.0) for level in case.ambient.levels)

    def test_near_field_settings(self) -> None:
        case = _load(EXAMPLE_PRJ).to_case()  # type: ignore[attr-defined]
        assert case.near_field.aspiration_coefficient == pytest.approx(0.1)
        assert case.near_field.contraction_coefficient == pytest.approx(1.0)
        assert case.near_field.max_rise_or_fall == 2
        assert case.near_field.output_interval == 5

    def test_chemistry_and_do_csvs_are_picked_up(self) -> None:
        """The example ships both, though its .prj never ran them."""
        project = _load(EXAMPLE_PRJ)
        assert project.has_chemistry  # type: ignore[attr-defined]
        assert project.has_dissolved_oxygen  # type: ignore[attr-defined]
        case = project.to_case()  # type: ignore[attr-defined]
        assert len(case.ambient.chemistry) == 4
        assert len(case.ambient.dissolved_oxygen) == 4
        # The example's inconsistent pH is preserved rather than silently dropped.
        assert case.ambient.chemistry[0].ph == pytest.approx(7.80)


class TestUnitsAreResolved:
    def test_case01_flow_is_cms_not_mgd(self) -> None:
        case = _load(CASE01_PRJ).to_case()  # type: ignore[attr-defined]
        assert case.effluent.flow == pytest.approx(0.005)

    def test_case03_same_stored_value_is_23x_smaller(self) -> None:
        case01 = _load(CASE01_PRJ).to_case()  # type: ignore[attr-defined]
        case03 = _load(CASE03_PRJ).to_case()  # type: ignore[attr-defined]
        assert case01.effluent.flow / case03.effluent.flow == pytest.approx(22.8, abs=0.1)

    def test_legacy_project_converts_feet_to_metres(self) -> None:
        """Macoma.prj stores spacing and both MZ distances in feet."""
        case = _load(LEGACY_PRJ).to_case()  # type: ignore[attr-defined]
        assert case.diffuser.port_spacing == pytest.approx(2.0 * 0.3048)
        assert case.mixing_zone.acute_distance == pytest.approx(20.7 * 0.3048)
        assert case.mixing_zone.chronic_distance == pytest.approx(207.0 * 0.3048)


class TestDriftDetection:
    def test_case01_disagreement_is_reported(self) -> None:
        """The .prj has 0.050 m/s at 15 m; the CSV has 0.020. The exe echoed 0.050."""
        project = _load(CASE01_PRJ)
        report = project.drift()  # type: ignore[attr-defined]
        assert "AMBIENT" in report
        assert any("current_speed" in item for item in report["AMBIENT"])

    def test_the_prj_value_is_the_one_used(self) -> None:
        case = _load(CASE01_PRJ).to_case()  # type: ignore[attr-defined]
        assert case.ambient.levels[-1].depth == pytest.approx(15.0)
        assert case.ambient.levels[-1].current_speed == pytest.approx(0.050)

    def test_loading_warns_by_default(self) -> None:
        with pytest.warns(ProjectDriftWarning, match="authoritative"):
            load_project(CASE01_PRJ)

    def test_a_consistent_project_does_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ProjectDriftWarning)
            load_project(EXAMPLE_PRJ)

    def test_duplicate_layout_resolves_towards_the_prj(self) -> None:
        """case01 has both macoma2effluent.csv and 'varios flows.csv'."""
        project = _load(CASE01_PRJ)
        chosen = project.tables[TableKind.EFFLUENT]  # type: ignore[attr-defined]
        assert chosen.source_path is not None
        assert chosen.source_path.name == "macoma2effluent.csv"


class TestDerivedGeometryFromRealProjects:
    def test_macoma_bottom_is_17_m_and_warns(self) -> None:
        """2 m port on a 15 m riser, against a 15 m ambient profile."""
        with pytest.warns(GeometryWarning, match="ambient profile"):
            case = load_project(CASE03_PRJ, warn_on_drift=False).to_case()
        assert case.diffuser.bottom_depth == pytest.approx(17.0)

    def test_example_geometry_is_consistent(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GeometryWarning)
            case = load_project(EXAMPLE_PRJ, warn_on_drift=False).to_case()
        # 11.0 + 0.31 = 11.31 m bottom, ambient profile to 12 m.
        assert case.diffuser.bottom_depth == pytest.approx(11.31)


class TestYamlRoundTrip:
    def test_case_survives_a_round_trip(self) -> None:
        case = _load(EXAMPLE_PRJ).to_case()  # type: ignore[attr-defined]
        assert loads_case(dumps_case(case)) == case

    def test_file_round_trip(self, tmp_path: Path) -> None:
        case = _load(CASE03_PRJ).to_case()  # type: ignore[attr-defined]
        path = tmp_path / "case.yaml"
        dump_case(case, path)
        assert load_case(path) == case

    def test_yaml_is_readable_and_omits_defaults(self) -> None:
        case = _load(EXAMPLE_PRJ).to_case()  # type: ignore[attr-defined]
        text = dumps_case(case)
        assert "port_diameter: 0.076" in text
        assert "n_ports: 18" in text
        # Untouched defaults are not written out.
        assert "light_absorption" not in text
        assert "max_steps" not in text

    def test_chemistry_the_prj_cannot_store_survives(self) -> None:
        """The whole point of having our own format."""
        case = _load(CASE03_PRJ).to_case()  # type: ignore[attr-defined]
        with_chem = case.model_copy(
            update={
                "effluent_chemistry": EffluentChemistry(
                    total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE
                )
            }
        )
        restored = loads_case(dumps_case(with_chem))
        assert restored.effluent_chemistry is not None
        assert restored.effluent_chemistry.total_alkalinity == pytest.approx(4000.0)
        assert restored.effluent_chemistry.ph == pytest.approx(10.5)
        assert restored.effluent_chemistry.ph_scale is PHScale.FREE

    def test_empty_document_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty YAML"):
            loads_case("")

    def test_non_mapping_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="mapping at the top level"):
            loads_case("- a\n- b\n")


class TestPrjWriter:
    @pytest.mark.parametrize("path", ALL_PRJ_PATHS, ids=lambda p: p.parent.name)
    def test_case_to_prj_to_case_is_stable(self, path: Path, tmp_path: Path) -> None:
        """Physical values survive Case -> .prj -> Case within the format's precision."""
        from plumes2.io.prj import read_prj, write_prj
        from plumes2.io.project import prj_from_case

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            project = load_project(path, warn_on_drift=False)
            case = project.to_case()
            generated = prj_from_case(case, template=project.prj)
            out = tmp_path / "generated.prj"
            write_prj(generated, out)
            restored = load_project(out, warn_on_drift=False).to_case()

        assert read_prj(out).to_text() == generated.to_text()
        assert restored.diffuser == case.diffuser
        assert restored.mixing_zone == case.mixing_zone
        assert restored.ambient.levels == case.ambient.levels
        assert restored.near_field.max_rise_or_fall == case.near_field.max_rise_or_fall

    def test_flow_unit_is_chosen_to_preserve_precision(self, tmp_path: Path) -> None:
        """3-digit mantissas mean the unit matters: 8 MGD and 0.005 cms are both exact
        only if each is written in the unit it came from."""
        from plumes2.io.prj import write_prj
        from plumes2.io.project import prj_from_case

        for path, expected_selector in ((EXAMPLE_PRJ, 1), (CASE01_PRJ, 2)):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                project = load_project(path, warn_on_drift=False)
                case = project.to_case()
                generated = prj_from_case(case, template=project.prj)
                out = tmp_path / f"{path.stem}.prj"
                write_prj(generated, out)
                restored = load_project(out, warn_on_drift=False).to_case()
            assert generated.effluent.unit_flags[1] == expected_selector
            assert restored.effluent.flow == pytest.approx(case.effluent.flow, rel=1e-12)

    def test_generated_prj_has_the_expected_shape(self, tmp_path: Path) -> None:
        from plumes2.io.project import prj_from_case

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            case = load_project(EXAMPLE_PRJ, warn_on_drift=False).to_case()
        generated = prj_from_case(case, output_filename="MyRun")
        text = generated.to_text()
        assert text.endswith("\r\n")
        # 20 padded rows per table, as the exe writes.
        assert len(generated.ambient.rows) == 20
        assert generated.output_filename == "MyRun"
        # Without a template, the undecoded flags take the upstream example's values.
        assert generated.nearfield_plot_variables[0] == "FluxAvg-Dilution"

    def test_chemistry_is_not_written_and_that_is_documented(self, tmp_path: Path) -> None:
        """No .prj stores chemistry, so a generated one is hydrodynamics-only."""
        from plumes2.io.project import prj_from_case

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            case = load_project(CASE03_PRJ, warn_on_drift=False).to_case()
        with_chem = case.model_copy(
            update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)}
        )
        text = prj_from_case(with_chem).to_text()
        assert "4000" not in text
        assert "1646" not in text
