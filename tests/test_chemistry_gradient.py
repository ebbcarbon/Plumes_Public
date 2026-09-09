"""The chemistry section panels: the plume drawn from the side, coloured by pH or saturation.

These figures are the "above and beyond" reporting feature -- the flux-averaged pH and saturation
panels answer the budget question, and these answer the limit question, which is asked against the
centreline (the worst, least-diluted point) and needs the spread across the plume to be honest.
The tests hold the claims the feature rests on: the field is the *model* evaluated across the
section rather than an interpolation, the centreline is never below the average it is drawn to
supersede, and the body is drawn where the plume is -- its own diameter, its own depth -- with any
vertical stretch stated.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from plumes2.config import EffluentChemistry
from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.plotframe import from_dat, from_results
from plumes2.report.chemistry_gradient import (
    QUANTITIES,
    build_chemistry_gradient_panels,
    cross_plume_field,
    write_chemistry_gradient_figures,
)
from plumes2.results import run
from tests.conftest import REFERENCE_CASES

CARBONATE = REFERENCE_CASES / "case03_carbonate"


def _case(path: Path):  # type: ignore[no-untyped-def]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_project(path, warn_on_drift=False).to_case()


@pytest.fixture(scope="module")
def dosed():  # type: ignore[no-untyped-def]
    """A run with an alkalinity-elevated discharge, so every quantity has a gradient to draw."""
    base = _case(CARBONATE / "test.prj")
    case = base.model_copy(
        update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(case, samples=48)


@pytest.fixture(scope="module")
def dosed_plot(dosed):  # type: ignore[no-untyped-def]
    return from_results(dosed)


# --------------------------------------------------------------- the field is the model, evaluated


@pytest.mark.slow
def test_the_centreline_is_never_below_the_flux_average(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """The whole reason to draw the band: the average understates the worst point.

    An alkalinity-elevated discharge sits above the ambient in every quantity, and the centreline
    is the least diluted point, so its value is the extreme and the flux average sits below it --
    at every station, for every quantity. If this inverts, the band is drawn upside down.
    """
    for quantity in QUANTITIES:
        field = cross_plume_field(dosed_plot, quantity.column)
        assert field is not None, quantity.column
        assert np.all(field.centreline >= field.flux_average - 1e-9), quantity.column
        assert np.all(field.flux_average >= field.ambient - 1e-9), quantity.column


@pytest.mark.slow
def test_the_interior_is_ordered_by_dilution_from_centreline_to_edge(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """Each offset is more diluted than the one inside it, and the chemistry follows.

    The interior is stacked centreline-first and dilution grows monotonically outward, so pH and
    brucite -- monotone in dilution for this discharge -- fall from the centreline to the ambient
    edge without a crossing; one would mean the local-dilution formula is wrong.

    ⚠️ The carbonate saturation states are **not** monotone in dilution here, and the test says so
    rather than pretending: a high-pH, low-DIC effluent gains carbonate ion from the first seawater
    it entrains, so aragonite and calcite *rise* over the first few offsets before they fall. The
    claim for them is that the rise is confined to the least-diluted third of the section and
    that everything outward of the peak is monotone -- which is what the colour field shows as a
    darkest band a little off the centreline.
    """
    for quantity in QUANTITIES:
        field = cross_plume_field(dosed_plot, quantity.column)
        assert field is not None
        assert np.array_equal(field.interior[0], field.centreline)
        steps = np.diff(field.interior, axis=0)
        if quantity.column in ("ph_total", "omega_brucite"):
            assert np.all(steps <= 1e-9), f"{quantity.column}: interior not monotone centre->edge"
        else:
            peak = int(np.argmax(field.interior, axis=0).max())
            assert peak <= field.interior.shape[0] // 3, f"{quantity.column}: peak too far out"
            assert np.all(steps[peak:] <= 1e-9), f"{quantity.column}: not monotone past its peak"
        assert np.all(field.interior[-1] >= field.ambient - 1e-9), quantity.column


@pytest.mark.slow
def test_the_interior_is_re_solved_not_interpolated(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """pH and saturation are non-linear in dilution, so the middle is not the mean of the ends.

    This is the claim that makes the band worth computing rather than shading between two lines.
    A straight interpolation between the centreline and the edge would put the mid-area curve at
    their average; the re-solved field departs from that, and near the port -- where the dilution
    gradient is steepest -- it departs by a lot. Measured on pH, where "a lot" is unambiguous.
    """
    field = cross_plume_field(dosed_plot, "ph_total")
    assert field is not None
    mid = field.interior[field.interior.shape[0] // 2]
    linear = 0.5 * (field.centreline + field.ambient)
    # Near the port the dilution gradient is steepest and pH is most curved, so the re-solved
    # mid-area curve departs from the straight-line average of the two ends by a clear margin.
    assert float(np.max(np.abs(mid - linear))) > 0.05


def test_a_bare_trace_has_no_gradient(tmp_path: Path) -> None:
    """Without a case there is nothing to re-solve across the section, so the field is None.

    A `.dat` carries the flux-averaged trace but not the effluent endmember or the ambient
    profile the cross-plume solve needs, so the feature declines rather than inventing them --
    and the report keeps its flux-averaged pH and saturation panels instead.
    """
    trace = CARBONATE / "test2_TxtOutputs.dat"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # No case, and no secondaries: the trace carries neither the endmember nor the plume
        # salinity a cross-plume solve needs, which is exactly the bare-trace condition.
        plot = from_dat(read_dat(trace), trace, secondaries=False)
    assert cross_plume_field(plot, "ph_total") is None
    assert build_chemistry_gradient_panels(plot) == []
    assert write_chemistry_gradient_figures(plot, tmp_path) == []
    assert not list(tmp_path.iterdir()), "nothing should be written when there is no field"


# ------------------------------------------------------------------------------- the panels


@pytest.mark.slow
def test_a_panel_is_built_for_each_quantity(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """pH, aragonite, calcite and brucite, each a self-contained panel with figure and table."""
    panels = build_chemistry_gradient_panels(dosed_plot)
    keys = [panel.key for panel in panels]
    assert keys == [
        "gradient-ph-total",
        "gradient-omega-aragonite",
        "gradient-omega-calcite",
        "gradient-omega-brucite",
    ]
    for panel in panels:
        assert panel.svg.startswith("<svg"), panel.key
        assert panel.drawing is not None, "the PDF redraws it into a page band"
        # The three named curves are all read off the table, which is the relief for a colour
        # field -- a figure whose numbers cannot be read is not accessible.
        assert "centreline (worst case)" in panel.table.columns
        assert "plume average" in panel.table.columns
        assert "plume edge (ambient)" in panel.table.columns
        assert panel.explanation and panel.notes


@pytest.mark.slow
def test_the_gradient_panels_reach_the_report(dosed) -> None:  # type: ignore[no-untyped-def]
    """The report picks the panels up through `build_panels`, one section each."""
    from plumes2.report import render_report

    html = render_report(dosed)
    for quantity in QUANTITIES:
        anchor = "gradient-" + quantity.column.replace("_", "-")
        assert f"id='{anchor}'" in html, anchor


@pytest.mark.slow
def test_the_brucite_panel_states_its_upper_bound_caveat(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """Brucite has no reference and no ion pairing, and the panel must say so -- PLAN.md 8b."""
    panels = {panel.key: panel for panel in build_chemistry_gradient_panels(dosed_plot)}
    notes = " ".join(panels["gradient-omega-brucite"].notes).lower()
    assert "upper bound" in notes and "ion pairing" in notes


# ------------------------------------------------------------------------- standalone figures


@pytest.mark.slow
def test_both_spans_are_written_for_each_quantity(dosed, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """ "Both" was the answer to how far along: a near-field figure and a full one, PNG and SVG.

    The near-field span is where the band is legible; the full span carries it to the mixing zone
    on a log-distance axis. Every quantity gets both, in both formats.
    """
    written = write_chemistry_gradient_figures(dosed, tmp_path)
    names = {path.name for path in written}
    for slug in ("ph", "aragonite", "calcite", "brucite"):
        for span in ("nearfield", "full"):
            for extension in ("svg", "png"):
                assert f"chem_{slug}_{span}.{extension}" in names
    assert all(path.exists() and path.stat().st_size > 0 for path in written)


@pytest.mark.slow
def test_the_cli_writes_gradient_figures(tmp_path: Path) -> None:
    """`plumes2 report --gradient-dir` writes the standalone figures beside the report."""
    from plumes2.cli import main

    project = tmp_path / "dosed.yaml"
    from plumes2.io.yaml_case import dump_case

    base = _case(CARBONATE / "test.prj")
    case = base.model_copy(
        update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
    )
    dump_case(case, project)

    gradients = tmp_path / "figures"
    code = main(
        ["report", str(project), "-o", str(tmp_path / "r.html"), "--gradient-dir", str(gradients)]
    )
    assert code == 0
    written = {path.name for path in gradients.iterdir()}
    assert "chem_ph_nearfield.svg" in written
    assert "chem_brucite_full.png" in written


# ------------------------------------------------------------------------ the section geometry


@pytest.mark.slow
def test_the_body_is_drawn_to_the_plumes_own_diameter(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """The mesh is the plume: symmetric about the centreline, one radius thick each side, and the
    receiving water at both edges."""
    from plumes2.display import SI
    from plumes2.report.chemistry_gradient import _section_mesh

    field = cross_plume_field(dosed_plot, "ph_total")
    assert field is not None
    x, y, values = _section_mesh(field, SI.length)
    middle = x.shape[0] // 2
    np.testing.assert_allclose(x[middle], field.distance_m)
    np.testing.assert_allclose(y[middle], field.depth_m)
    for edge in (0, -1):
        offset = np.hypot(x[edge] - field.distance_m, y[edge] - field.depth_m)
        np.testing.assert_allclose(offset, field.half_width_m, rtol=1e-9, atol=1e-12)
        np.testing.assert_array_equal(values[edge], field.ambient)
    np.testing.assert_array_equal(values[middle], field.centreline)
    # Mirrored: the same value the same distance either side of the centreline.
    np.testing.assert_array_equal(values[middle - 3], values[middle + 3])


@pytest.mark.slow
def test_the_section_mesh_is_cut_at_the_surface(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """Lift the plume so its upper edge is in the air: the mesh is clamped to z = 0, the field's own
    arrays are untouched, and the panel note says the body was cut."""
    import dataclasses

    from plumes2.display import SI
    from plumes2.report.chemistry_gradient import _panel, _section_mesh

    field = cross_plume_field(dosed_plot, "ph_total")
    assert field is not None
    lifted = dataclasses.replace(
        field, depth_m=field.half_width_m * 0.5
    )  # centreline half a radius down
    _x, y, _values = _section_mesh(lifted, SI.length)
    assert float(y.min()) == 0.0 and float(y.max()) > 0.0
    middle = y.shape[0] // 2
    np.testing.assert_allclose(y[middle], lifted.depth_m)  # the centreline itself is under water
    assert (lifted.depth_m - lifted.half_width_m < 0.0).all()  # the data still says it breached
    panel = _panel(lifted, dosed_plot.case, SI)
    assert "cut at the surface plane" in " ".join(panel.notes)


def test_the_vertical_stretch_is_a_round_number_or_none() -> None:
    """A stretched drawing says so with a factor the reader can undo, never `x2.37`."""
    from plumes2.report.chemistry_gradient import _EXAGGERATIONS, _exaggeration

    assert _exaggeration(1.0, 1.0) == 1.0
    assert _exaggeration(3.0, 1.5) == 1.0, "nearly square already: left at true scale"
    for x_span, y_span in ((10.0, 1.0), (300.0, 0.6), (5.0, 0.02)):
        factor = _exaggeration(x_span, y_span)
        assert factor in _EXAGGERATIONS
        assert factor > 1.0


@pytest.mark.slow
def test_the_panel_states_the_stretch_and_the_water_column(dosed_plot) -> None:  # type: ignore[no-untyped-def]
    """What the figure did to the geometry is in the notes, so it cannot be missed."""
    from plumes2.display import SI
    from plumes2.report.chemistry_gradient import _frame

    field = cross_plume_field(dosed_plot, "ph_total")
    assert field is not None
    frame = _frame(field, dosed_plot.case, SI.length, fixed_aspect=True)
    panels = build_chemistry_gradient_panels(dosed_plot)
    panel = next(p for p in panels if p.key == "gradient-ph-total")
    notes = " ".join(panel.notes)
    if frame.exaggeration is not None and frame.exaggeration > 1.0:
        assert "stretched" in notes
    else:
        assert "true scale" in notes
    # The surface is either inside the frame or named with its distance above it; same for the bed.
    if frame.surface_gap is None:
        assert frame.y_lo <= 0.0
    else:
        assert frame.surface_gap > 0.0 and "above its top" in notes
    assert frame.seabed is not None, "the case says where the bed is"
    if frame.seabed_gap is None:
        assert frame.y_hi >= frame.seabed
    else:
        assert frame.seabed_gap > 0.0 and "below its bottom" in notes
    assert frame.figure_height > 0.0
