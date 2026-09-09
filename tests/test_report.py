"""The standard report: one file, PDF or HTML by suffix, with the explanation and the numbers."""

from __future__ import annotations

import re
import warnings
from html import escape
from pathlib import Path

import numpy as np
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
    write_document,
)
from plumes2.report.page import Header, render_page
from plumes2.report.palette import SERIES, SURFACE
from plumes2.report.panels import MAX_OVERLAY_RUNS, Panel, TooManyRunsError, build_panels
from plumes2.report.pdf import page_figures
from plumes2.results import run
from tests.conftest import EXAMPLE_PROJECT, REFERENCE_CASES

CARBONATE = REFERENCE_CASES / "case03_carbonate"


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
    # Nothing may be fetched: no external stylesheet, font, or image. The one raster the page
    # carries -- the chemistry section's colour field -- is an inline data URI inside its SVG.
    assert not re.search(r"<(link|img|iframe)\b", html), "no external references"
    assert not re.search(r"""href=["'](?!data:|#)""", html), "every href is inline or an anchor"
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
    # Centreline, edges, and the cross-plume gradient -- and the diffuser from above.
    assert "elevation" in sections and "gradient" in sections and "plan-view" in sections
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
        Header(
            title=nasty,
            subtitle=nasty,
            stamp=nasty,
            kpis=((nasty, nasty, nasty),),
            caveats=(nasty,),
        ),
        [
            Panel(
                key="k",
                title=nasty,
                explanation=nasty,
                svg="<svg/>",
                table=pd.DataFrame(),
                notes=(nasty,),
            )
        ],
        footer=nasty,
    )
    assert "<script>" not in page
    assert escape(nasty) in page


def test_the_page_paints_its_own_surface_rather_than_inheriting_a_theme() -> None:
    """Figures have their colours baked in, so a dark page would make them unreadable."""
    page = render_page(Header(title="t", subtitle="s", stamp="p"), [], footer="f")
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
def test_a_combined_report_is_the_overlays_then_every_run(spacing_runs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """One file: overlay panels first, then each run's own panels under its given name."""
    from plumes2.report import build_combined_report

    names = tuple(f"run {n}" for n in range(len(spacing_runs)))
    path = build_combined_report(spacing_runs, tmp_path / "study.html", names=names)
    html = path.read_text(encoding="utf-8")
    sections = _sections(html)
    assert "overlay-dilution" in sections
    for index, name in enumerate(names, start=1):
        assert f"run-{index}-trajectory-3d" in sections
        assert escape(f"{name} \N{EM DASH} The plume in space") in html
    assert "followed by the full report" in html
    with pytest.raises(ValueError, match="one heading per run"):
        build_combined_report(spacing_runs, tmp_path / "bad.html", names=("only one",))
    # Explicit sections: more runs than the overlays carry, each under its own heading.
    first = spacing_runs.runs[0]
    sections = [("first, again", first), ("first, and again", first)]
    path = build_combined_report(
        spacing_runs, tmp_path / "sections.html", names=names, sections=sections
    )
    html = path.read_text(encoding="utf-8")
    assert escape("first, again \N{EM DASH} The plume in space") in html
    assert escape("first, and again \N{EM DASH} The plume in space") in html
    assert f"run-{len(names)}-trajectory-3d" not in _sections(html) or len(names) <= 2


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


# ------------------------------------------------------------------ the plume in space and in plan


@pytest.mark.slow
def test_the_plan_view_places_every_port_and_marks_the_merge(spacing_runs) -> None:  # type: ignore[no-untyped-def]
    """25 ports at 1 m: every jet drawn, the merge state as the model says, the wastefield width."""
    from plumes2.report.panels import _plan_outline

    multiport = spacing_runs.runs[1]  # 25 ports, 1.0 m spacing
    frame = multiport.nearfield
    panels = {p.key: p for p in build_panels(from_results(multiport), units=SI)}
    plan = panels["plan-view"]
    assert "25 ports" in plan.explanation
    notes = " ".join(plan.notes).lower()
    assert "wastefield width" in notes
    merged = frame["merged"].to_numpy(dtype=bool)
    if merged.all():
        assert "merged from the port" in notes
    elif merged.any():
        assert "dotted line" in notes
    # The footprint is a closed polygon as wide as the plume at every station.
    radius = frame["plume_diameter_m"].to_numpy(dtype=float) / 2.0
    outline = _plan_outline(
        frame["x_m"].to_numpy(dtype=float), frame["y_m"].to_numpy(dtype=float), radius
    )
    assert outline.shape[1] == 2 and np.allclose(outline[0], outline[-1])
    assert float(np.ptp(outline[:, 1])) >= float(radius.max())

    single = spacing_runs.runs[0]
    plan = {p.key: p for p in build_panels(from_results(single), units=SI)}["plan-view"]
    assert "a single port" in plan.explanation


@pytest.mark.slow
def test_the_receiving_water_opens_the_report(dosed) -> None:  # type: ignore[no-untyped-def]
    """Two ambient panels first -- hydrography, then chemistry -- from the case, not the trace.

    pH and the saturation states are derived, and derived the way the rest of the report derives
    them; the seabed below the profile's last row is stated; a frame with no case gets neither.
    """
    import dataclasses

    from plumes2.ambient import AmbientProfileView
    from plumes2.chem import resolve_constants, solve_from_alkalinity_dic

    panels = build_panels(from_results(dosed), units=SI, farfield=dosed.farfield)
    assert [p.key for p in panels][:2] == ["ambient-profile", "ambient-chemistry"]
    hydro, chem = panels[0], panels[1]
    case = dosed.case
    assert len(hydro.table) == len(case.ambient.levels)
    assert "density (kg/m³)" in hydro.table.columns
    assert case.diffuser.bottom_depth > case.ambient.levels[-1].depth
    assert "extends the profile" in " ".join(hydro.notes)

    row = case.ambient.chemistry[0]
    view = AmbientProfileView(case.ambient)
    constants = resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
    state = solve_from_alkalinity_dic(
        row.total_alkalinity,
        row.dic,
        float(view.salinity(row.depth)),
        float(view.temperature(row.depth)),
        constants=constants,
    )
    assert float(chem.table["pH (total)"].iloc[0]) == pytest.approx(float(state.ph_total), abs=1e-6)
    assert len(chem.table) == len(case.ambient.chemistry)
    assert "not inputs" in " ".join(chem.notes)

    bare = dataclasses.replace(from_results(dosed), case=None)
    assert not [p.key for p in build_panels(bare, units=SI) if p.key.startswith("ambient-")]
    assert "depth (ft)" in build_panels(from_results(dosed), units=US)[0].table.columns


@pytest.mark.slow
def test_the_far_field_plan_panel_carries_the_picture_to_the_mixing_zones(dosed) -> None:  # type: ignore[no-untyped-def]
    """Straight after the top-down view: the band starts at the hand-over width, accounts for every
    boundary the case names, and is not drawn at all without a far field."""
    import dataclasses

    farfield = dosed.farfield
    assert farfield is not None
    panels = build_panels(from_results(dosed), units=SI, farfield=farfield)
    keys = [p.key for p in panels]
    assert keys.index("plan-farfield") == keys.index("plan-view") + 1
    panel = panels[keys.index("plan-farfield")]
    notes = " ".join(panel.notes)

    # Brooks starts from the wastefield width the near field leaves; the table's first row is it.
    handover = dosed.case.wastefield_width(float(dosed.nearfield["plume_diameter_m"].iloc[-1]))
    assert float(panel.table["width (m)"].iloc[0]) == pytest.approx(handover, rel=1e-6)
    assert "hand-over" in notes and "one-dimensional" in notes

    # Every boundary is accounted for: read on the band, inside the near field, or beyond it.
    zone = dosed.case.mixing_zone
    first, last = float(farfield["distance_m"].iloc[0]), float(farfield["distance_m"].iloc[-1])
    for label, at in (("acute", zone.acute_distance), ("chronic", zone.chronic_distance)):
        if at <= 0.0:
            continue
        if first <= at <= last:
            expected = float(np.interp(at, farfield["distance_m"], farfield["dilution"]))
            assert (
                f"The {label} mixing-zone boundary at {at:,.1f} m reads dilution {expected:,.0f}"
                in notes
            )
        else:
            assert f"The {label} boundary at {at:,.1f} m" in notes

    # No far field, no panel -- skipped, not drawn empty.
    assert "plan-farfield" not in [p.key for p in build_panels(from_results(dosed), units=SI)]

    # A bare trace names no current: the band follows the plume's heading and the notes say so.
    bare = dataclasses.replace(from_results(dosed), case=None)
    bare_panel = {p.key: p for p in build_panels(bare, units=SI, farfield=farfield)}
    assert "names no current direction" in " ".join(bare_panel["plan-farfield"].notes)

    # Display units reach the table.
    us = {p.key: p for p in build_panels(from_results(dosed), units=US, farfield=farfield)}
    assert "width (ft)" in us["plan-farfield"].table.columns


@pytest.mark.slow
def test_the_surface_cuts_the_drawing_and_never_the_data() -> None:
    """A buoyant jet from a shallow port with the surface stop off runs into the air. The tables
    keep every row; no figure draws anything above z = 0; the notes say what was cut."""
    import matplotlib.pyplot as plt

    from plumes2 import load_case
    from plumes2.report.panels import (
        _cut_at_surface,
        _styled,
        _surface_crossing,
        _surface_rim,
        _tube,
        build_overlay_panels,
    )
    from tests.conftest import REPO_ROOT

    # The helpers first: the crossing is interpolated onto the plane.
    depth = np.array([2.0, 1.0, -1.0, -3.0])
    cut_depth, cut_x = _cut_at_surface(depth, np.array([0.0, 1.0, 2.0, 3.0]))
    assert cut_depth.tolist() == [2.0, 1.0, 0.0] and cut_x.tolist() == [0.0, 1.0, 1.5]
    assert _surface_crossing(depth) == 2 and _surface_crossing(np.array([1.0, 2.0])) is None
    whole = _cut_at_surface(np.array([1.0, 2.0]), np.array([5.0, 6.0]))
    assert whole[1].tolist() == [5.0, 6.0]

    base = load_case(REPO_ROOT / "studies" / "example_case.yaml")
    shallow = base.diffuser.model_copy(
        update={
            "port_depth": 1.0,
            "port_elevation": base.diffuser.port_depth + base.diffuser.port_elevation - 1.0,
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        results = run(base.model_copy(update={"diffuser": shallow}), samples=60)
    frame = results.nearfield
    assert (frame["depth_m"] < 0.0).any(), "the test needs a plume that leaves the water"

    panels = {
        p.key: p for p in build_panels(from_results(results), units=SI, farfield=results.farfield)
    }
    # The data keeps its rows above the surface.
    assert (panels["elevation"].table["centreline depth (m)"] < 0.0).any()
    assert (panels["trajectory-3d"].table["depth (m)"] < 0.0).any()
    # The drawings do not: every line and every filled band in the side view sits at or below
    # the surface (depth >= 0), and the surface line and the crossing marker are there.
    with _styled():
        figure = plt.figure(figsize=(7.2, 3.2))
        axes = panels["elevation"].drawing.into(figure)
        for line in axes.lines:
            assert float(np.nanmin(line.get_ydata())) >= -1e-9, "a line above the surface"
        for collection in axes.collections:
            for path in collection.get_paths():
                assert float(path.vertices[:, 1].min()) >= -1e-9, "a band above the surface"
        texts = " ".join(text.get_text() for text in axes.texts)
        assert "surface" in texts and "centreline surfaces" in texts
        plt.close(figure)
    # The rims of the cut: where rings of the tube pierce the plane. The shipped example's body
    # breaks the surface while its centreline stays 2 m under, so its rings straddle z = 0 (the
    # shallow variant's rings sit wholly above or below, and give no rim -- also correct).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        shipped = run(base, samples=60).nearfield
    x = shipped["x_m"].to_numpy(dtype=float)
    y = shipped["y_m"].to_numpy(dtype=float)
    z = shipped["depth_m"].to_numpy(dtype=float)
    radius = shipped["plume_diameter_m"].to_numpy(dtype=float) / 2.0
    assert (z - radius < 0.0).any() and not (z < 0.0).any()
    mesh_x, mesh_y, mesh_z = _tube(x, y, z, radius, rings=24, spokes=12)
    assert (mesh_z < 0.0).any()
    rims = _surface_rim(mesh_x, mesh_y, mesh_z)
    assert rims and all(rim.shape[1] == 2 for rim in rims)
    for (
        rim
    ) in rims:  # every rim point lies on a ring's segment, so it is inside the body's plan extent
        assert rim[:, 0].min() >= mesh_x.min() - 1e-9 and rim[:, 0].max() <= mesh_x.max() + 1e-9
    # Every panel that draws the plume says what it cut.
    for key in ("trajectory-3d", "elevation", "plan-view", "plan-farfield"):
        assert "surface" in " ".join(panels[key].notes).lower(), key
    # The overlays stop each depth line on the plane and say so.
    overlays = {
        p.key: p
        for p in build_overlay_panels([("shallow", frame), ("as shipped", frame)], units=SI)
    }
    depth_panel = overlays["overlay-depth-m"]
    assert "reach the surface" in " ".join(depth_panel.notes)
    with _styled():
        figure = plt.figure(figsize=(7.2, 3.4))
        axes = depth_panel.drawing.into(figure)
        for line in axes.lines:
            assert float(np.nanmin(line.get_ydata())) >= -1e-9
        plt.close(figure)


@pytest.mark.slow
def test_the_wireframe_is_the_plumes_own_diameter(dosed) -> None:  # type: ignore[no-untyped-def]
    """Every ring of the 3-D body sits one local radius from the centreline, square to the path."""
    from plumes2.report.panels import _tube

    frame = dosed.nearfield
    x = frame["x_m"].to_numpy(dtype=float)
    y = frame["y_m"].to_numpy(dtype=float)
    z = frame["depth_m"].to_numpy(dtype=float)
    radius = frame["plume_diameter_m"].to_numpy(dtype=float) / 2.0
    mesh_x, mesh_y, mesh_z = _tube(x, y, z, radius, rings=10, spokes=8)
    assert mesh_x.shape == (10, 9)
    picked = np.unique(np.linspace(0, len(x) - 1, 10).round().astype(int))
    centre = np.column_stack([x, y, z])[picked]
    for ring in range(10):
        points = np.column_stack([mesh_x[ring], mesh_y[ring], mesh_z[ring]])
        distance = np.linalg.norm(points - centre[ring], axis=1)
        np.testing.assert_allclose(distance, radius[picked][ring], rtol=1e-9, atol=1e-12)


# ------------------------------------------------------------------ the PDF


def _pdf_pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


@pytest.mark.slow
def test_a_pdf_is_written_when_the_path_says_pdf(dosed, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """The default deliverable: a real PDF, one file, a front page and at least a page per panel."""
    target = build_report(dosed, tmp_path / "report.pdf")
    data = target.read_bytes()
    assert data.startswith(b"%PDF-1.")
    panels = build_panels(from_results(dosed), units=SI, farfield=dosed.farfield)
    assert _pdf_pages(data) >= len(panels) + 1
    assert [target.name] == [p.name for p in tmp_path.iterdir()], "one file, no sidecars"
    # Document metadata, so a PDF that has lost its filename still says what it is.
    assert b"/Title" in data and b"/Author" in data


@pytest.mark.slow
def test_the_contents_rows_link_to_their_pages(dosed, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Every contents row is a clickable strip pointing at its section's page, the sidebar outline
    carries the same entries in order, and the document metadata survives the link pass."""
    from pypdf import PdfReader

    target = build_report(dosed, tmp_path / "report.pdf")
    panels = build_panels(from_results(dosed), units=SI, farfield=dosed.farfield)
    reader = PdfReader(str(target))

    # One outline entry per panel, in order, each landing on a page whose heading is that panel.
    outline = [item for item in reader.outline if not isinstance(item, list)]
    assert [item.title for item in outline] == [panel.title for panel in panels]
    landed = [reader.get_destination_page_number(item) for item in outline]
    assert landed == sorted(landed) and landed[0] >= 1, "sections follow the front matter"
    for item, panel, page_index in zip(outline, panels, landed, strict=True):
        text = reader.pages[page_index].extract_text()
        assert panel.title.split(":")[0] in text, item.title

    # The contents rows are link annotations on the front matter, one per panel, each a strip
    # inside the text column pointing at the same page as its outline entry.
    annotations = [
        (page_index, annotation.get_object())
        for page_index, page in enumerate(reader.pages)
        for annotation in page.get("/Annots", [])
    ]
    links = [(i, a) for i, a in annotations if a.get("/Subtype") == "/Link"]
    assert len(links) == len(panels)
    assert all(i < landed[0] for i, _ in links), "the contents live in the front matter"
    for (_, annotation), page_index in zip(links, landed, strict=True):
        destination = annotation["/Dest"]
        assert reader.get_page_number(destination[0].get_object()) == page_index
        x0, y0, x1, y1 = (float(v) for v in annotation["/Rect"])
        assert 0.0 < x0 < x1 < 8.5 * 72 and 0.0 < y0 < y1 < 11.0 * 72
    assert reader.metadata is not None and "Plume report" in str(reader.metadata.title)


def test_an_unknown_suffix_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    header = Header(title="t", subtitle="s", stamp="p")
    with pytest.raises(ValueError, match="suffix"):
        write_document(header, [], tmp_path / "report.docx", footer="f")
    assert not list(tmp_path.iterdir())


@pytest.mark.slow
def test_the_pdf_pages_carry_the_whole_document(dosed) -> None:  # type: ignore[no-untyped-def]
    """Every panel gets its heading, figure and table; the front page gets the title and contents.

    Inspected through the page figures rather than a PDF parser, so the check needs nothing the
    package does not already depend on.
    """
    import matplotlib.pyplot as plt

    panels = build_panels(from_results(dosed), units=SI, farfield=dosed.farfield)
    title = "A report whose title has a $ in it"
    header = Header(
        title=title,
        subtitle="one subtitle",
        stamp=dosed.provenance.case_digest,
        kpis=(("Near-field dilution", "534", ""), ("Trapping depth", "2.3", "m")),
        caveats=("one caveat",),
    )
    figures = page_figures(header, panels, footer="the footer")
    try:
        texts = [[text.get_text() for text in figure.texts] for figure in figures]
        front = " ".join(texts[0])
        assert title in front and "CONTENTS" in front and dosed.provenance.case_digest in front
        assert "READ THESE FIRST" in front and "one caveat" in front
        # Each section starts on a fresh page with its number and title, and carries its figure.
        headings = [text for page in texts for text in page]
        for index, panel in enumerate(panels, start=1):
            assert any(text.startswith(f"{index}. ") for text in headings), panel.key
        assert sum(len(figure.subfigs) for figure in figures) == len(panels)
        # Page numbers on every page, and the footer paragraph on the last.
        for number, page in enumerate(texts, start=1):
            assert f"page {number} of {len(figures)}" in page
        assert "the footer" in texts[-1]
        # A `$` in untrusted text is text, not the start of a formula -- on every page.
        assert all(not text.get_parse_math() for figure in figures for text in figure.texts)
    finally:
        for figure in figures:
            plt.close(figure)


@pytest.mark.slow
def test_a_comparison_writes_a_pdf_too(spacing_runs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    target = build_comparison_report(spacing_runs, tmp_path / "compare.pdf")
    assert target.read_bytes().startswith(b"%PDF-1.")
