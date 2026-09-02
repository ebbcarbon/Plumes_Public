"""The standard report: one self-contained file, with the explanation and the numbers in it."""

from __future__ import annotations

import re
import warnings
from html import escape
from pathlib import Path

import pandas as pd
import pytest

from plumes2.comparison import Comparison
from plumes2.config import EffluentChemistry
from plumes2.display import SI, US
from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.plotframe import from_dat, from_results
from plumes2.report import (
    build_comparison_report,
    build_report,
    render_comparison,
    render_report,
    report_from_dat,
)
from plumes2.report.page import Header, render_page
from plumes2.report.palette import SERIES, SURFACE
from plumes2.report.panels import MAX_OVERLAY_RUNS, Panel, TooManyRunsError, build_panels
from plumes2.results import run
from tests.conftest import EXAMPLE_PROJECT, REFERENCE_CASES

CARBONATE = REFERENCE_CASES / "case03_macoma_carbonate"


def _case(path: Path):  # type: ignore[no-untyped-def]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_project(path, warn_on_drift=False).to_case()


@pytest.fixture(scope="module")
def dosed():  # type: ignore[no-untyped-def]
    """A run with chemistry, so every panel the report can build is exercised."""
    base = _case(CARBONATE / "test.prj")
    case = base.model_copy(
        update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(case, samples=40)


def _sections(html: str) -> list[str]:
    return re.findall(r"<section id='([^']+)'", html)


# ------------------------------------------------------------------ the page contract


@pytest.mark.slow
def test_a_report_is_one_self_contained_file(dosed, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """No server, no fonts, no sidecar images -- it has to survive being forwarded."""
    target = build_report(dosed, tmp_path / "report.html")
    html = target.read_text(encoding="utf-8")

    assert html.startswith("<!doctype html>")
    assert "<svg" in html, "figures are inline SVG, not linked images"
    assert "<script" not in html, "no JavaScript: it must render from the file alone"
    # Nothing may be fetched: no external stylesheet, font, or image.
    assert not re.search(r'<(link|img|iframe)\b', html), "no external references"
    assert "base64" not in html, "SVG is embedded as markup, not re-encoded"
    assert [target.name] == [p.name for p in tmp_path.iterdir()], "one file, no sidecars"


@pytest.mark.slow
def test_every_panel_carries_an_explanation_and_a_table(dosed) -> None:  # type: ignore[no-untyped-def]
    """A figure dump is not a report, and a figure whose values cannot be read is not accessible."""
    panels = build_panels(from_results(dosed), units=SI, farfield=dosed.farfield)
    assert len(panels) >= 8
    for panel in panels:
        assert panel.svg.startswith("<svg"), panel.key
        # Prose, not a caption: it has to say what to read from the panel.
        assert len(panel.explanation.split()) >= 25, panel.key
        assert len(panel.table), panel.key
        assert panel.key == panel.key.strip().lower()


@pytest.mark.slow
def test_the_report_covers_what_the_specification_asked_for(dosed) -> None:  # type: ignore[no-untyped-def]
    """PLAN section 6b's table, panel by panel."""
    html = render_report(dosed)
    sections = _sections(html)
    # 3-D in space relative to the diffuser, and 2-D for everything quantitative.
    assert "trajectory-3d" in sections
    assert "diffuser" in html
    # Centreline, edges, and the cross-plume gradient.
    assert "elevation" in sections and "gradient" in sections
    assert "centreline" in html
    # The quantities of concern.
    for section in ("ph", "saturation", "carbonate", "pco2", "temperature"):
        assert section in sections, section
    assert "brucite" in html, "the quantity the exe cannot report at all"


@pytest.mark.slow
def test_the_report_is_traceable(dosed) -> None:  # type: ignore[no-untyped-def]
    """Section 7b's rule does not stop at file formats: a figure needs its provenance too."""
    html = render_report(dosed)
    stamp = re.search(r'class="stamp">([^<]+)<', html)
    assert stamp is not None
    text = stamp.group(1)
    assert dosed.provenance.case_digest[:12] in text
    assert dosed.provenance.generated_at in text
    assert "plumes2" in text
    assert text.count("plumes2") == 1, "the version must not be printed twice"


def test_untrusted_text_from_a_project_file_is_escaped() -> None:
    """A case description is typed into a GUI, so it is untrusted: a tag would eat the page."""
    nasty = "</style><script>alert(1)</script>"
    page = render_page(
        Header(title=nasty, subtitle=nasty, stamp=nasty, kpis=((nasty, nasty, nasty),),
               caveats=(nasty,)),
        [Panel(key="k", title=nasty, explanation=nasty, svg="<svg/>", table=pd.DataFrame(),
               notes=(nasty,))],
        footer=nasty,
    )
    assert "<script>" not in page
    assert escape(nasty) in page


def test_the_page_paints_its_own_surface_rather_than_inheriting_a_theme() -> None:
    """Figures have their colours baked in, so a dark page would make them unreadable."""
    page = render_page(
        Header(title="t", subtitle="s", stamp="p"), [], footer="f"
    )
    assert "color-scheme: light" in page
    assert SURFACE in page and SERIES[0] in page
    assert "prefers-color-scheme" not in page, "a half-done dark mode is worse than none"


# ------------------------------------------------------------------ units


@pytest.mark.slow
def test_display_units_reach_the_figures_and_the_tables(dosed) -> None:  # type: ignore[no-untyped-def]
    """Units are independent of the solver: the same run, reported twice."""
    metric = render_report(dosed, units=SI)
    imperial = render_report(dosed, units=US)

    assert "depth (m)" in metric and "depth (ft)" in imperial
    assert "units: SI" in metric and "units: US" in imperial
    # The trapping depth tile is the same physical depth, so the numbers must differ by the factor.
    def tile(html: str, label: str) -> float:
        found = re.search(rf"{label}</span><span class='value'>([0-9.,]+)", html)
        assert found is not None, label
        return float(found.group(1).replace(",", ""))

    # Both tiles are printed to one decimal, so the comparison has to allow for each side's own
    # rounding: 0.05 ft on the imperial tile plus 0.05 m (0.16 ft) carried through the conversion.
    assert tile(imperial, "Trapping depth") == pytest.approx(
        tile(metric, "Trapping depth") / 0.3048, abs=0.25
    )


# ------------------------------------------------------------------ the exe path


@pytest.mark.golden
def test_an_exe_trace_reports_with_its_caveats(tmp_path: Path) -> None:
    """⭐ Every archived trace is reportable, and the report says what a `.dat` cannot tell it."""
    target = report_from_dat(
        CARBONATE / "test2_TxtOutputs.dat",
        tmp_path / "dat.html",
        case_path=CARBONATE / "test.prj",
    )
    html = target.read_text(encoding="utf-8")
    assert "Read these first" in html, "the .dat caveats must appear before the figures"
    assert html.index("Read these first") < html.index("<section")
    assert "three printed decimals" in html
    assert "carries no provenance" in html
    # And it reaches the quantity the exe could never produce.
    assert "saturation" in _sections(html)
    assert "brucite" in html


@pytest.mark.golden
def test_a_bare_trace_still_reports_its_trajectory(tmp_path: Path) -> None:
    """Five columns and no chemistry: the chemistry panels are skipped, not emitted empty."""
    plot = from_dat(
        read_dat(EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat"), "example", secondaries=False
    )
    sections = _sections(render_report(plot))
    assert {"trajectory-3d", "elevation", "dilution", "gradient"} <= set(sections)
    assert not {"ph", "saturation", "carbonate", "pco2"} & set(sections)


def test_a_frame_with_nothing_to_draw_is_refused() -> None:
    plot = from_dat(
        read_dat(EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat"), "example", secondaries=False
    )
    bare = type(plot)(frame=plot.frame[["dilution"]], source="bare", origin="dat")
    with pytest.raises(ValueError, match="nothing to report"):
        render_report(bare)


# ------------------------------------------------------------------ several runs, one set of axes


@pytest.fixture(scope="module")
def spacing_runs():  # type: ignore[no-untyped-def]
    """Three configurations differing only in the diffuser, which is the working comparison."""
    base = _case(REFERENCE_CASES / "case18_zero_current_pair" / "test21.prj")
    runs = []
    for ports, spacing in ((1, 0.0), (25, 1.0), (25, 3.0)):
        case = base.model_copy(
            update={
                "diffuser": base.diffuser.model_copy(
                    update={"n_ports": ports, "port_spacing": spacing, "horizontal_angle": 90.0}
                ),
                "effluent": base.effluent.model_copy(update={"flow": 0.005}),
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            runs.append(run(case, samples=30))
    return Comparison(tuple(runs))


@pytest.mark.slow
def test_an_overlay_puts_the_runs_on_shared_axes_with_a_derived_legend(spacing_runs) -> None:  # type: ignore[no-untyped-def]
    html = render_comparison(spacing_runs)
    sections = _sections(html)
    assert "overlay-dilution" in sections
    assert "overlay-depth-m" in sections
    # The legend text is derived from the cases, so the fields that differ appear verbatim.
    for label in spacing_runs.labels():
        assert escape(label) in html
    assert "n_ports" in html and "port_spacing" in html
    assert "derived from a comparison of the resolved cases" in html


@pytest.mark.slow
def test_an_overlay_of_identical_cases_is_refused(spacing_runs) -> None:  # type: ignore[no-untyped-def]
    """A figure of one line drawn three times in three colours is worse than an error."""
    single = spacing_runs.runs[0]
    with pytest.raises(ValueError, match="identical"):
        render_comparison(Comparison((single, single)))


@pytest.mark.slow
def test_more_runs_than_palette_slots_is_refused(spacing_runs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Generating a hue is the one thing the standard forbids outright."""
    from plumes2.report.panels import build_overlay_panels

    frames = [(f"run {n}", spacing_runs.runs[0].nearfield) for n in range(MAX_OVERLAY_RUNS + 1)]
    with pytest.raises(TooManyRunsError, match="palette slots"):
        build_overlay_panels(frames)
    assert MAX_OVERLAY_RUNS == len(SERIES)


@pytest.mark.slow
def test_a_comparison_report_writes_one_file(spacing_runs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    target = build_comparison_report(spacing_runs, tmp_path / "compare.html")
    assert target.exists()
    assert [target.name] == [p.name for p in tmp_path.iterdir()]
