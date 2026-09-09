"""The chemistry section panels: pH and mineral saturation drawn on the plume itself.

The report's `_panel_ph` and `_panel_saturation` draw one value per station -- the flux-averaged
one the model carries -- against distance. That is the right number for a budget, and the wrong
picture for a limit: a plume is a volume, its centreline is both the least diluted and the last
place to relax, so the worst pH or the highest brucite saturation sits there, above the average.
A mixing-zone limit is written against the worst point, not the mean, and it is written in space.

So this module draws the **section**: the plume as it would be seen from the side, distance from
the diffuser along the bottom and depth down the side, its outline the plume's own diameter, and
the quantity filled in as a colour field across the whole body. At each station the plume runs
from the centreline (least diluted) out to its edge (the receiving water), and every point between
has its own dilution and therefore its own chemistry -- pH and Omega are not linear in dilution,
so the interior is not a straight interpolation of the two ends. The field is computed the honest
way: the cross-plume profile gives the local dilution at each offset, and the carbonate system is
**re-solved** at that dilution, salinity and temperature (`chem.transport.mix` then
`chem.speciation`), exactly as the trajectory itself is solved. Nothing here is a shortcut over
the model; it is the model evaluated across the section instead of only on its flux average.

Reading the figure: the dark end of the colour scale is the discharge and sits on the centreline
by the port; the body fades to the receiving water's shade at its edge and along its length, and
where it has become one flat shade the plume *is* the receiving water. The colour bar carries the
values, with the ambient marked on it, and the table under each panel carries the centreline,
average and edge at a dozen stations for anyone who needs the numbers rather than the picture.

Two things about the geometry are stated on the figure rather than left to be noticed. A plume is
metres long and decimetres thick, so the vertical scale is usually stretched to give it visible
thickness -- by a round factor, printed in the corner, chosen so the reader can undo it. And the
surface and the seabed are drawn when they are near, and named with their distance from the frame
when they are not, so a section that shows neither cannot be misread as a plume in open water.

⚠️ **The section needs the case, not just the trace.** Re-solving across the section needs the
effluent endmember, the ambient profile and the constant selections -- none of which a `.dat`
carries. Given a `PlotFrame` without a case (a bare exe trace), `cross_plume_field` returns
`None` and the report keeps the flux-averaged pH and saturation panels instead. Given a run, or a
`.dat` with its case supplied, it produces the full field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize

from plumes2.ambient import AmbientProfileView
from plumes2.chem.constants import resolve_constants, solubility_brucite
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.chem.transport import effluent_endmember, mix
from plumes2.crossplume import profile_weight
from plumes2.display import SI, DisplayUnit, UnitSystem
from plumes2.plotframe import PlotFrame
from plumes2.report.palette import (
    AXIS,
    GRID,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    SERIES,
    SURFACE,
    blend,
)
from plumes2.report.panels import (
    PANEL_WIDTH,
    Drawing,
    Panel,
    _axis_label,
    _cut_at_surface,
    _downstream,
    _merge_start,
    _scale,
    _styled,
    _surface_crossing,
    _table,
)

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes
    from matplotlib.collections import QuadMesh
    from matplotlib.colors import Colormap
    from matplotlib.figure import Figure, FigureBase
    from numpy.typing import NDArray

    from plumes2.config import Case
    from plumes2.results import Results

__all__ = [
    "QUANTITIES",
    "CrossPlumeField",
    "Quantity",
    "build_chemistry_gradient_panels",
    "cross_plume_field",
    "write_chemistry_gradient_figures",
]


@dataclass(frozen=True, slots=True)
class Quantity:
    """One thing the section can be drawn for, and how to draw it."""

    #: The frame column carrying the flux-averaged value.
    column: str
    #: Short filename slug for the standalone figures -- `chem_<slug>_nearfield.svg`.
    slug: str
    #: Short name for titles and the anchor key.
    name: str
    #: Colour-bar label.
    axis_label: str
    #: Log colour scale -- true for the saturation states, which span decades, false for pH.
    log: bool
    #: Which palette slot this quantity's ramp is built from. The three minerals keep the slots
    #: the combined saturation panel gives them, so a reader moving between the two panels sees
    #: the same hue mean the same mineral.
    slot: int
    #: Sentences the panel must print for this quantity specifically.
    notes: tuple[str, ...] = ()


#: The four quantities, in the order the report draws them. pH first because it is the quantity
#: the module exists to predict; then the three saturation states, in the saturation panel's own
#: order so the colours line up between the two.
QUANTITIES: tuple[Quantity, ...] = (
    Quantity(
        column="ph_total",
        slug="ph",
        name="pH",
        axis_label="pH (total scale)",
        log=False,
        slot=0,
        notes=(
            "Total scale, which is what the model's default constant set reports on. The same "
            "water on the free or seawater scale is a different number.",
        ),
    ),
    Quantity(
        column="omega_aragonite",
        slug="aragonite",
        name="aragonite saturation",
        axis_label="aragonite saturation state",
        log=True,
        slot=0,
    ),
    Quantity(
        column="omega_calcite",
        slug="calcite",
        name="calcite saturation",
        axis_label="calcite saturation state",
        log=True,
        slot=1,
    ),
    Quantity(
        column="omega_brucite",
        slug="brucite",
        name="brucite saturation",
        axis_label="brucite saturation state",
        log=True,
        slot=2,
        notes=(
            "Brucite is an upper bound: it is computed without ion pairing, which would lower the "
            "free magnesium and hydroxide activities and so lower the ratio. It is also the one "
            "quantity here the original model cannot report at all, so it has no reference to "
            "check against. Read it as a trend.",
        ),
    ),
)

#: Offsets across the half-width the section is re-solved at, from the centreline (0) out to
#: just inside the edge, as a fraction of the plume radius. The edge itself, u = 1, is the
#: receiving water and is carried separately as `ambient`. Twelve steps is enough for the colour
#: field to read as continuous once it is shaded between vertices; more would multiply the
#: carbonate solves for no visible gain.
_OFFSETS: NDArray[np.float64] = np.linspace(0.0, 1.0, 13)[:-1]

#: Height of the two-axes near-and-far figure at its own width, inches. A single section figure
#: takes its height from the plume instead -- see `_frame`.
_FULL_HEIGHT = 3.9

#: What a section figure's plotting area may measure once the depth axis, the colour bar and their
#: labels have taken their share of `PANEL_WIDTH`: its width, and the least and most height it is
#: allowed. The figure's height follows from the plume's proportions within these bounds, so a
#: long thin plume gets a short wide figure and the band on the page fits it.
_PLOT_WIDTH = PANEL_WIDTH - 2.0
_PLOT_HEIGHT = (1.4, 3.2)
#: Vertical room a section figure needs beyond its plotting area: the title above, the distance
#: axis and its label below.
_CHROME_HEIGHT = 1.05

#: The width-to-height proportion of the tallest plotting area allowed -- what the vertical
#: exaggeration is chosen against. Approximate by design: the exaggeration is snapped to a round
#: number from `_EXAGGERATIONS` and printed on the figure, so the figure states exactly what was
#: applied whatever the axes finally measure.
_BOX_RATIO = _PLOT_WIDTH / _PLOT_HEIGHT[1]
_EXAGGERATIONS: tuple[float, ...] = (
    1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0, 75.0, 100.0, 150.0, 200.0,
    300.0, 500.0, 750.0, 1000.0,
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class CrossPlumeField:
    """The cross-plume chemistry field for one quantity, with the geometry to draw it on.

    Every array is in SI / native chemistry units and is indexed by near-field row. `interior` is
    stacked centreline-first: `interior[0]` is the centreline and equals `centreline`, and the
    outermost interior offset is followed by `ambient`, which is the plume edge.
    """

    quantity: Quantity
    #: Horizontal distance from the diffuser, m -- the section's x-axis.
    distance_m: NDArray[np.float64]
    #: Centreline depth, m, positive down -- the section's y-axis.
    depth_m: NDArray[np.float64]
    #: Plume radius, m: half the model's diameter, the half-thickness of the drawn body.
    half_width_m: NDArray[np.float64]
    #: The offsets `interior` is solved at, as fractions of the radius, centreline first.
    offsets: NDArray[np.float64]
    #: Value at each offset, shape `(len(offsets), n_rows)`, centreline first.
    interior: NDArray[np.float64]
    #: Value on the plume edge -- the ambient receiving water re-solved at that depth.
    ambient: NDArray[np.float64]
    #: The flux-averaged value the model carries, straight from the frame column.
    flux_average: NDArray[np.float64]
    #: Distance at which neighbouring plumes merge, m, or `None` if they never do mid-run.
    merge_at_m: float | None = None

    @property
    def centreline(self) -> NDArray[np.float64]:
        """The worst-case curve: chemistry at the centreline (least diluted) point."""
        return self.interior[0]


def _fields(plot: PlotFrame) -> dict[str, CrossPlumeField] | None:
    """Every quantity's cross-plume field, from one carbonate solve, or `None` if unavailable.

    Returns `None` -- rather than raising -- when the frame is a bare trace with no case, because
    that is the ordinary exe-`.dat` path and the report simply keeps its flux-averaged panels.
    """
    case = plot.case
    frame = plot.frame
    needed = {"centreline_dilution", "depth_m", "x_m", "y_m", "plume_diameter_m"}
    if case is None or case.effluent_chemistry is None or not case.ambient.has_chemistry:
        return None
    if not needed <= set(frame.columns) or "ph_total" not in frame.columns:
        return None

    view = AmbientProfileView(case.ambient)
    constants = resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
    endmember = effluent_endmember(
        case.effluent_chemistry,
        case.effluent.salinity,
        case.effluent.temperature,
        settings=case.carbonate,
        constants=constants,
    )

    depth = frame["depth_m"].to_numpy(dtype=np.float64)
    centreline_dilution = frame["centreline_dilution"].to_numpy(dtype=np.float64)
    ambient_salinity = view.salinity(depth)
    ambient_temperature = view.temperature(depth)
    ambient_alkalinity = view.total_alkalinity(depth)
    ambient_dic = view.dic(depth)

    # The local dilution at offset u: the profile shape phi runs from 1 on the centreline to 0 at
    # the edge, and the excess concentration is phi/centreline_dilution, so the local dilution is
    # centreline_dilution/phi. The profile is taken across the plume's thickness, which is the
    # direction the section cuts whether the plume is still round or has merged into a slab, so
    # the offsets need no mapping between the two regimes. phi is 1 on the centreline and never 0
    # over these offsets, so the divide is safe; the edge (phi -> 0, dilution -> infinity) is
    # carried separately as the ambient curve.
    levels = _OFFSETS
    shape = profile_weight(levels, plot.profile)
    local_dilution = centreline_dilution[None, :] / shape[:, None]

    flat_dilution = local_dilution.reshape(-1)
    tiled_salinity = np.tile(ambient_salinity, len(levels))
    tiled_temperature = np.tile(ambient_temperature, len(levels))
    tiled_alkalinity = np.tile(ambient_alkalinity, len(levels))
    tiled_dic = np.tile(ambient_dic, len(levels))
    interior_salinity = mix(case.effluent.salinity, tiled_salinity, flat_dilution)
    interior_temperature = mix(case.effluent.temperature, tiled_temperature, flat_dilution)
    interior_state = solve_from_alkalinity_dic(
        mix(endmember.total_alkalinity, tiled_alkalinity, flat_dilution),
        mix(endmember.dic, tiled_dic, flat_dilution),
        interior_salinity,
        interior_temperature,
        constants=constants,
        context="cross-plume chemistry section",
    )
    interior_brucite = interior_state.omega_brucite(
        solubility_brucite(interior_salinity, interior_temperature)
    )

    # The edge is the receiving water itself: the carbonate system of the ambient TA/DIC at each
    # row's depth. It is the limit the interior approaches as dilution runs away.
    edge_state = solve_from_alkalinity_dic(
        ambient_alkalinity,
        ambient_dic,
        ambient_salinity,
        ambient_temperature,
        constants=constants,
        context="cross-plume section plume edge",
    )
    edge_brucite = edge_state.omega_brucite(
        solubility_brucite(ambient_salinity, ambient_temperature)
    )

    shape2d = (len(levels), len(frame))
    interior_by_column: dict[str, NDArray[np.float64]] = {
        "ph_total": interior_state.ph_total.reshape(shape2d),
        "omega_aragonite": interior_state.omega_aragonite.reshape(shape2d),
        "omega_calcite": interior_state.omega_calcite.reshape(shape2d),
        "omega_brucite": interior_brucite.reshape(shape2d),
    }
    edge_by_column: dict[str, NDArray[np.float64]] = {
        "ph_total": edge_state.ph_total,
        "omega_aragonite": edge_state.omega_aragonite,
        "omega_calcite": edge_state.omega_calcite,
        "omega_brucite": edge_brucite,
    }

    distance = _downstream(frame)
    half_width = frame["plume_diameter_m"].to_numpy(dtype=np.float64) / 2.0
    merge_at = _merge_start(frame, distance)
    fields: dict[str, CrossPlumeField] = {}
    for quantity in QUANTITIES:
        if quantity.column not in frame.columns:
            continue
        fields[quantity.column] = CrossPlumeField(
            quantity=quantity,
            distance_m=distance,
            depth_m=depth,
            half_width_m=half_width,
            offsets=levels,
            interior=interior_by_column[quantity.column],
            ambient=edge_by_column[quantity.column],
            flux_average=frame[quantity.column].to_numpy(dtype=np.float64),
            merge_at_m=merge_at,
        )
    return fields


def cross_plume_field(plot: PlotFrame, column: str) -> CrossPlumeField | None:
    """The cross-plume field for one quantity `column`, or `None` if it cannot be built.

    A thin wrapper over the shared solve, for a caller who wants a single quantity. The panel
    builder uses `_fields` directly so the four panels share one carbonate solve.
    """
    fields = _fields(plot)
    return None if fields is None else fields.get(column)


# ------------------------------------------------------------------------------ the colour


def _palette(field: CrossPlumeField) -> tuple[Colormap, Normalize]:
    """The colour scale for one field: a single-hue sequential ramp and its normalisation.

    Sequential means one hue, light to dark, and the hue is the quantity's own palette slot --
    washed toward the chart surface at the light end and deepened toward the ink at the dark end,
    so the ramp stays inside the validated palette rather than introducing a colormap of its own.
    The **dark end is always the discharge**: for an alkalinity-elevated effluent that is the high
    end of the scale, for an acidic one it would be the low end, and the ramp is reversed so the
    plume never fades *into* the page on the side that matters. The colour bar carries the values
    either way.

    Log-normalised for the saturation states, which span decades; linear for pH. The range is the
    field's own, ambient included, so the receiving water always has a colour on the bar.
    """
    quantity = field.quantity
    base = SERIES[quantity.slot]
    stops = [
        blend(base, SURFACE, 0.9),
        blend(base, SURFACE, 0.5),
        base,
        blend(base, INK_PRIMARY, 0.4),
    ]
    if float(np.nanmean(field.centreline)) < float(np.nanmean(field.ambient)):
        stops.reverse()
    cmap = LinearSegmentedColormap.from_list(f"plumes2 {quantity.slug}", stops)

    values = np.concatenate([field.interior.reshape(-1), field.ambient])
    finite = values[np.isfinite(values)]
    if quantity.log:
        finite = finite[finite > 0.0]
    if not len(finite):
        return cmap, Normalize(0.0, 1.0)
    low, high = float(finite.min()), float(finite.max())
    if quantity.log:
        if high <= low:
            high = low * 10.0
        return cmap, LogNorm(low, high)
    if high <= low:
        high = low + 0.01
    return cmap, Normalize(low, high)


# ---------------------------------------------------------------------------- the geometry


def _normals(
    distance: NDArray[np.float64], depth: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Unit normals to the trajectory in the section plane, `(along-distance, along-depth)`.

    The plume's thickness is measured perpendicular to its own path, so the body is built by
    offsetting each station along its normal rather than straight up and down -- a bending jet
    keeps its thickness through the bend. Where two stations coincide the tangent is undefined
    and the normal falls back to vertical.
    """
    if len(distance) < 2:
        return np.zeros_like(distance), np.ones_like(distance)
    tangent_s = np.gradient(distance)
    tangent_z = np.gradient(depth)
    size = np.hypot(tangent_s, tangent_z)
    safe = np.where(size > 0.0, size, 1.0)
    return (
        np.where(size > 0.0, -tangent_z / safe, 0.0),
        np.where(size > 0.0, tangent_s / safe, 1.0),
    )


def _section_mesh(
    field: CrossPlumeField, length: DisplayUnit
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """The body of the plume as a curvilinear mesh `(X, Y, C)` in display units.

    Rows run across the plume from one edge, through the centreline, to the other edge; columns
    run along it. The field is symmetric about the centreline, so the solved half-section is
    mirrored, and the edge rows carry the ambient.
    """
    # Rows after the centreline crosses the surface leave the figure (the table keeps them); what
    # is left is clamped to the plane below.
    cut = _surface_crossing(field.depth_m)
    rows = slice(None) if cut is None else slice(0, max(cut, 1))
    distance = np.asarray(length(field.distance_m[rows]), dtype=np.float64)
    depth = np.asarray(length(field.depth_m[rows]), dtype=np.float64)
    radius = np.asarray(length(field.half_width_m[rows]), dtype=np.float64)
    normal_s, normal_z = _normals(distance, depth)

    half_offsets = np.append(field.offsets, 1.0)
    half_values = np.vstack([field.interior[:, rows], field.ambient[None, rows]])
    offsets = np.concatenate([-half_offsets[::-1], half_offsets[1:]])
    values = np.vstack([half_values[::-1], half_values[1:]])

    x = distance[None, :] + offsets[:, None] * (radius * normal_s)[None, :]
    y = depth[None, :] + offsets[:, None] * (radius * normal_z)[None, :]
    # The surface plane cuts the body: nothing of the mesh sits above z = 0. The clamp folds the
    # part above onto the plane, where it has no thickness and draws nothing; the field's own
    # arrays are untouched.
    return x, np.maximum(y, 0.0), values


def _exaggeration(x_span: float, y_span: float) -> float:
    """The round vertical stretch that lets the plume fill the plotting area without overshooting.

    The factor that would fill the area exactly is `(x_span / y_span) / _BOX_RATIO`; the largest
    round number at or below it is chosen, so the body spans the width and sits a little short of
    the height. Below 1.25 the drawing is left at true scale -- a stretch that small would cost
    the reader an honest picture for a few millimetres of thickness.
    """
    if x_span <= 0.0 or y_span <= 0.0:
        return 1.0
    natural = (x_span / y_span) / _BOX_RATIO
    if natural <= 1.25:
        return 1.0
    fitting = [factor for factor in _EXAGGERATIONS if factor <= natural]
    return fitting[-1] if fitting else _EXAGGERATIONS[-1]


@dataclass(frozen=True, slots=True)
class _Frame:
    """What one section figure shows of the water column, decided once and stated in the prose.

    Computed before drawing so the panel's notes can describe exactly what the figure did: the
    limits, the vertical stretch, and whether the surface and the seabed made it into the frame.
    """

    x_lo: float
    x_hi: float
    #: Depth limits, display units, `y_lo` the shallower.
    y_lo: float
    y_hi: float
    #: Round vertical stretch applied, or `None` to leave the aspect to the axes and measure it
    #: after layout -- the two-axes far-field figure cannot fix its aspect without misaligning.
    exaggeration: float | None
    #: `None` when the surface is inside the frame and drawn; otherwise how far above the top of
    #: the frame it lies, display units.
    surface_gap: float | None
    #: Seabed depth, display units, or `None` without a case to say where it is.
    seabed: float | None
    #: `None` when the seabed is drawn or unknown; otherwise how far below the frame it lies.
    seabed_gap: float | None
    #: Figure height at `PANEL_WIDTH`, inches, following the plume's proportions at the chosen
    #: exaggeration -- so the band reserved for it on a page is the size of the picture.
    figure_height: float


def _frame(
    field: CrossPlumeField, case: Case | None, length: DisplayUnit, *, fixed_aspect: bool
) -> _Frame:
    """Fit the frame around the plume, then admit the surface and the seabed when they are near.

    "Near" is within three quarters of the plume's own vertical span: closer than that and the
    boundary is part of the picture, farther and admitting it would shrink the plume to a line to
    show a metre of empty water. What is left out is named on the figure with its distance.
    """
    x, y, _ = _section_mesh(field, length)
    x_lo, x_hi = min(0.0, float(x.min())), float(x.max())
    x_pad = 0.03 * (x_hi - x_lo) or 0.1
    y_lo, y_hi = float(y.min()), float(y.max())
    y_pad = 0.15 * (y_hi - y_lo) or 0.1
    x_lo, x_hi, y_lo, y_hi = x_lo - x_pad, x_hi + x_pad, y_lo - y_pad, y_hi + y_pad
    span = y_hi - y_lo

    surface_gap: float | None = None
    if 0.0 >= y_lo - 0.75 * span:
        y_lo = min(y_lo, 0.0) - 0.05 * span
    else:
        surface_gap = y_lo

    seabed = float(length(case.diffuser.bottom_depth)) if case is not None else None
    seabed_gap: float | None = None
    if seabed is not None:
        if seabed <= y_hi + 0.75 * span:
            y_hi = max(y_hi, seabed) + 0.05 * span
        else:
            seabed_gap = seabed - y_hi

    exaggeration: float | None = None
    figure_height = _FULL_HEIGHT
    if fixed_aspect:
        exaggeration = _exaggeration(x_hi - x_lo, y_hi - y_lo)
        plot_height = _PLOT_WIDTH * ((y_hi - y_lo) * exaggeration) / (x_hi - x_lo)
        figure_height = min(max(plot_height, _PLOT_HEIGHT[0]), _PLOT_HEIGHT[1]) + _CHROME_HEIGHT
    return _Frame(
        x_lo=x_lo,
        x_hi=x_hi,
        y_lo=y_lo,
        y_hi=y_hi,
        exaggeration=exaggeration,
        surface_gap=surface_gap,
        seabed=seabed,
        seabed_gap=seabed_gap,
        figure_height=figure_height,
    )


# ------------------------------------------------------------------------------ drawing


def _titled(name: str) -> str:
    """`name` as a title: capitalised, except `pH`, whose casing is meaning, not style."""
    return name if name.startswith("pH") else name[0].upper() + name[1:]


def _factor(value: float) -> str:
    """A stretch factor for a label: `2`, `7.5`, `150` -- never `2.0` or `1.5e+02`."""
    return f"{value:.1f}".rstrip("0").rstrip(".") if value < 10.0 else f"{value:.0f}"


def _label_exaggeration(axes: Axes, factor: float, *, measured: bool) -> None:
    """Print the vertical stretch in the corner, so a stretched drawing says it is one."""
    if factor <= 1.05:
        return
    about = "\N{ALMOST EQUAL TO} " if measured else ""
    axes.annotate(
        f"vertical exaggeration {about}\N{MULTIPLICATION SIGN}{_factor(factor)}",
        xy=(0.99, 0.02),
        xycoords="axes fraction",
        ha="right",
        va="bottom",
        fontsize=7,
        color=INK_MUTED,
    )


def _measured_exaggeration(axes: Axes) -> float:
    """The vertical stretch the axes actually ended up with, once the layout has run."""
    box = axes.get_window_extent()
    x0, x1 = axes.get_xlim()
    y0, y1 = axes.get_ylim()
    x_span, y_span = abs(x1 - x0), abs(y1 - y0)
    if not (x_span and y_span and box.width and box.height):
        return 1.0
    return float((box.height / y_span) / (box.width / x_span))


def _corner_note(axes: Axes, text: str, *, top: bool, right: bool = False) -> None:
    """A muted note in one corner of the axes, in axes fractions so the layout never moves it."""
    axes.annotate(
        text,
        xy=(0.99 if right else 0.01, 0.98 if top else 0.02),
        xycoords="axes fraction",
        ha="right" if right else "left",
        va="top" if top else "bottom",
        fontsize=7,
        color=INK_MUTED,
    )


def _draw_section(
    figure: FigureBase,
    axes: Axes,
    field: CrossPlumeField,
    units: UnitSystem,
    frame: _Frame,
    *,
    cmap: Colormap,
    norm: Normalize,
) -> QuadMesh:
    """The near-field section: the plume's body coloured by the field, in its water column.

    Returns the mesh so the caller can hang a colour bar on it -- the one thing a section cannot
    be read without.
    """
    del figure  # the colour bar is the caller's; everything here is on the axes
    length = units.length
    x, y, values = _section_mesh(field, length)
    axes.set_axisbelow(True)  # the grid stays under the body, not over it
    mesh = axes.pcolormesh(
        x, y, values, cmap=cmap, norm=norm, shading="gouraud", rasterized=True, zorder=2
    )
    for edge in (0, -1):
        axes.plot(x[edge], y[edge], color=INK_MUTED, linewidth=0.6, zorder=3)
    distance = np.asarray(length(field.distance_m), dtype=np.float64)
    depth = np.asarray(length(field.depth_m), dtype=np.float64)
    # The centreline stops where it crosses the surface; the body above is already cut.
    line_z, line_d = _cut_at_surface(depth, distance)
    if len(line_d):
        axes.plot(line_d, line_z, color=INK_PRIMARY, linewidth=0.7, alpha=0.5, zorder=4)
    if _surface_crossing(depth) is not None and len(line_d):
        axes.plot(
            [line_d[-1]], [0.0], marker="x", markersize=6, color=INK_PRIMARY, linestyle="none",
            zorder=5,
        )  # fmt: skip

    # The port, labelled on the side the plume is not heading for.
    rising = depth[-1] <= depth[0]
    axes.plot(
        [distance[0]],
        [depth[0]],
        marker="o",
        markersize=4.5,
        color=SERIES[1],
        markeredgecolor=SURFACE,
        markeredgewidth=1.0,
        linestyle="none",
        zorder=5,
    )
    axes.annotate(
        "diffuser",
        xy=(distance[0], depth[0]),
        xytext=(2, -7 if rising else 7),
        textcoords="offset points",
        ha="left",
        va="top" if rising else "bottom",
        fontsize=7.5,
        color=INK_SECONDARY,
    )

    if field.merge_at_m is not None:
        at = float(length(field.merge_at_m))
        axes.axvline(at, color=AXIS, linewidth=0.8, zorder=1)
        axes.annotate(
            "plumes merge",
            xy=(at, 0.98),
            xycoords=("data", "axes fraction"),
            xytext=(3, 0),
            textcoords="offset points",
            va="top",
            ha="left",
            fontsize=7.5,
            color=INK_MUTED,
        )

    # The water column: drawn when it is in the frame, named when it is not. The notes keep to
    # the right-hand corners at the top and the left at the bottom, clear of the diffuser label.
    if frame.surface_gap is None:
        axes.axhline(0.0, color=INK_SECONDARY, linewidth=1.0, zorder=1)
        _corner_note(axes, "surface", top=True, right=True)
    else:
        _corner_note(
            axes,
            f"surface {frame.surface_gap:.1f} {length.label} above frame",
            top=True,
            right=True,
        )
    if frame.seabed is not None:
        if frame.seabed_gap is None:
            axes.axhspan(frame.seabed, frame.y_hi, color=GRID, zorder=0, linewidth=0)
            axes.axhline(frame.seabed, color=INK_SECONDARY, linewidth=1.0, zorder=1)
            _corner_note(axes, "seabed", top=False)
        else:
            _corner_note(
                axes, f"seabed {frame.seabed_gap:.1f} {length.label} below frame", top=False
            )

    if frame.exaggeration is not None:
        axes.set_aspect(frame.exaggeration, adjustable="box")
        _label_exaggeration(axes, frame.exaggeration, measured=False)
    axes.set_xlim(frame.x_lo, frame.x_hi)
    axes.set_ylim(frame.y_hi, frame.y_lo)  # depth increases downward
    axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
    axes.set_ylabel(_axis_label("depth", length.label))
    return mesh


def _colorbar(
    figure: FigureBase, axes: Axes | list[Axes], mesh: QuadMesh, field: CrossPlumeField
) -> None:
    """The colour bar, with the receiving water -- and saturation, for an Omega -- marked on it.

    The marks are what let the eye calibrate the body: the shade the plume fades to *is* the
    ambient, and for a saturation state the line at 1 says which shades are supersaturated.
    """
    bar = figure.colorbar(mesh, ax=axes, pad=0.09, fraction=0.05, aspect=22)
    bar.set_label(field.quantity.axis_label)
    bar.outline.set_edgecolor(AXIS)
    bar.outline.set_linewidth(0.8)

    marks = [(float(np.nanmedian(field.ambient)), "ambient", "-")]
    if field.quantity.log:
        marks.append((1.0, "saturation", ":"))
    low = float(np.asarray(mesh.norm.vmin, dtype=np.float64))
    high = float(np.asarray(mesh.norm.vmax, dtype=np.float64))
    placed: list[float] = []
    for value, label, style in marks:
        if not low <= value <= high:
            continue
        bar.ax.axhline(value, color=INK_PRIMARY, linewidth=0.8, linestyle=style)
        fraction = float(np.asarray(mesh.norm(np.asarray([value])))[0])
        # Two marks within a few percent of the bar's height would print on top of each other; the
        # second keeps its line and loses its word, as the end labels on the line panels do.
        if any(abs(fraction - other) < 0.07 for other in placed):
            continue
        placed.append(fraction)
        bar.ax.annotate(
            label,
            xy=(0.0, value),
            xycoords=("axes fraction", "data"),
            xytext=(-3, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=7,
            color=INK_SECONDARY,
        )


def _section_drawing(
    field: CrossPlumeField, case: Case | None, units: UnitSystem, frame: _Frame, title: str
) -> Drawing:
    """The near-field section as a `Drawing`, for the report panel and the standalone figure."""
    cmap, norm = _palette(field)

    def draw(figure: FigureBase, axes: Axes) -> None:
        mesh = _draw_section(figure, axes, field, units, frame, cmap=cmap, norm=norm)
        _colorbar(figure, axes, mesh, field)
        axes.set_title(title)

    del case  # already folded into `frame`; kept in the signature so the two callers read alike
    return Drawing(draw, height=frame.figure_height)


def _draw_farfield(
    axes: Axes,
    field: CrossPlumeField,
    farfield: pd.DataFrame,
    units: UnitSystem,
    *,
    cmap: Colormap,
    norm: Normalize,
    mixing_zone: tuple[float, float] | None,
) -> None:
    """The far field as a band at the trapping depth, one shade across its thickness.

    Brooks carries a slab average and a constant thickness, so the band is uniform across and
    varies only along -- which is the truth of the model, and the figure's title says so.
    """
    length = units.length
    distance = np.asarray(length(farfield["distance_m"].to_numpy(dtype=np.float64)))
    values = farfield[field.quantity.column].to_numpy(dtype=np.float64)
    depth = float(length(field.depth_m[-1]))
    radius = float(length(field.half_width_m[-1]))
    x = np.vstack([distance, distance])
    # Clamped at the surface plane, like the near-field body: a slab whose top would sit in the
    # air is drawn from the surface down.
    y = np.vstack(
        [
            np.full_like(distance, max(depth - radius, 0.0)),
            np.full_like(distance, max(depth + radius, 0.0)),
        ]
    )
    axes.set_axisbelow(True)
    axes.pcolormesh(
        x, y, np.vstack([values, values]), cmap=cmap, norm=norm, shading="gouraud",
        rasterized=True, zorder=2,
    )  # fmt: skip
    for row in (0, 1):
        axes.plot(distance, y[row], color=INK_MUTED, linewidth=0.6, zorder=3)
    pad = 0.02 * (distance[-1] - distance[0]) or 0.1
    axes.set_xlim(distance[0] - pad, distance[-1] + pad)
    axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
    if mixing_zone is not None:
        # The two boundaries are often a decade apart on an axis spanning several hundred metres,
        # so their labels start at different heights rather than printing over each other.
        for (label, boundary), top in zip(
            zip(("acute MZ", "chronic MZ"), mixing_zone, strict=True), (0.98, 0.72), strict=True
        ):
            at = float(length(boundary))
            if distance[0] <= at <= distance[-1]:
                axes.axvline(at, color=AXIS, linewidth=0.8, linestyle=":", zorder=1)
                axes.annotate(
                    label,
                    xy=(at, top),
                    xycoords=("data", "axes fraction"),
                    xytext=(3, 0),
                    textcoords="offset points",
                    va="top",
                    ha="left",
                    fontsize=7.5,
                    color=INK_MUTED,
                    rotation=90,
                )


def _full_figure(
    field: CrossPlumeField,
    farfield: pd.DataFrame,
    case: Case | None,
    mixing_zone: tuple[float, float] | None,
    units: UnitSystem,
    title: str,
) -> Figure:
    """Near field and far field side by side, one depth axis, one colour scale.

    Two axes rather than one because the near field is metres and the far field hundreds of
    metres; on a single linear axis the near field is a sliver and on a log axis the plume's shape
    is a lie. Each axis carries its own distance scale and, once the layout has run, its own
    measured vertical exaggeration.
    """
    figure = plt.figure(figsize=(PANEL_WIDTH + 1.6, _FULL_HEIGHT))
    near, far = figure.subplots(1, 2, sharey=True, width_ratios=[1.0, 1.15])
    cmap, norm = _palette(field)
    frame = _frame(field, case, units.length, fixed_aspect=False)
    mesh = _draw_section(figure, near, field, units, frame, cmap=cmap, norm=norm)
    _draw_farfield(far, field, farfield, units, cmap=cmap, norm=norm, mixing_zone=mixing_zone)
    _colorbar(figure, [near, far], mesh, field)
    near.set_title(f"{title}: near field")
    far.set_title("far field to the mixing zone, slab average")
    figure.canvas.draw()  # the layout has to have run before the stretch can be measured
    for axes in (near, far):
        _label_exaggeration(axes, _measured_exaggeration(axes), measured=True)
    return figure


def _mixing_zone(plot: PlotFrame) -> tuple[float, float] | None:
    """The acute and chronic mixing-zone distances from the case, or `None` without one."""
    if plot.case is None:
        return None
    zone = plot.case.mixing_zone
    return (float(zone.acute_distance), float(zone.chronic_distance))


# ------------------------------------------------------------------------------- the panel


def _water_column_note(frame: _Frame, length: DisplayUnit) -> str | None:
    """One sentence on what the frame left out of the water column, or `None` if nothing."""
    missing = []
    if frame.surface_gap is not None:
        missing.append(f"the surface is {frame.surface_gap:.1f} {length.label} above its top")
    if frame.seabed_gap is not None:
        missing.append(f"the seabed is {frame.seabed_gap:.1f} {length.label} below its bottom")
    if not missing:
        return None
    return (
        "The frame is fitted to the plume, so " + " and ".join(missing) + " -- both stated in "
        "the corners of the figure. The side-view panel earlier carries the same geometry."
    )


def _panel(field: CrossPlumeField, case: Case | None, units: UnitSystem) -> Panel:
    """One section panel: the figure, its explanation, and its centreline/average/edge table."""
    length = units.length
    quantity = field.quantity
    frame = _frame(field, case, length, fixed_aspect=True)
    drawing = _section_drawing(
        field, case, units, frame, f"{_titled(quantity.name)} across the plume, from the side"
    )

    table = pd.DataFrame(
        {
            "_d": field.distance_m,
            "_z": field.depth_m,
            "centreline (worst case)": field.centreline,
            "plume average": field.flux_average,
            "plume edge (ambient)": field.ambient,
        }
    )
    table = _scale(
        _table(table, {c: c for c in table.columns}).rename(
            columns={"_d": f"distance ({length.label})", "_z": f"depth ({length.label})"}
        ),
        length,
        (f"distance ({length.label})", f"depth ({length.label})"),
    )

    notes = [
        "The plume is drawn to its own diameter, seen from the side, with the diffuser at the "
        f"left. The colour inside is {quantity.name} at each point of the section, re-solved "
        "from the local dilution there rather than interpolated between the centreline and the "
        "edge -- pH and saturation are not linear in dilution, so the middle of the body is a "
        "computed value, not a guess.",
        "The dark end of the scale is the discharge and the light end the receiving water; the "
        "hairline on the colour bar marks the ambient at the plume's depth. Where the body has "
        "faded to one flat shade the plume has become the receiving water. The centreline is the "
        "least diluted point and the last to relax, and it is what a limit is judged against.",
    ]
    # For a low-DIC, high-pH discharge the carbonate saturation states rise on first mixing --
    # the effluent gains carbonate ion from the seawater it entrains -- so the darkest colour sits
    # a little off the centreline rather than on it. Said when it happens, because a reader who
    # expects the centreline to be the extreme would otherwise take it for a drawing error.
    if bool(np.any(np.argmax(field.interior, axis=0) > 0)) and quantity.log:
        notes.append(
            "Where the colour is darkest a little off the centreline rather than on it, that is "
            "the chemistry, not the drawing: a low-DIC discharge gains carbonate ion from the "
            "first seawater it entrains, so the saturation state rises before it falls. The table "
            "reports the centreline value; the peak sits just inside it."
        )
    if frame.exaggeration is not None and frame.exaggeration > 1.0:
        notes.append(
            f"The vertical scale is stretched {_factor(frame.exaggeration)} times so the plume "
            "has visible thickness, and the figure says so in its corner. At true scale it would "
            "be a sliver: a plume is metres long and decimetres thick."
        )
    else:
        notes.append(
            "Drawn at true scale: a unit of depth is as long on the page as a unit of distance."
        )
    water = _water_column_note(frame, length)
    if water:
        notes.append(water)
    if bool(np.any(field.depth_m - field.half_width_m < 0.0)):
        crossed = bool(np.any(field.depth_m < 0.0))
        notes.append(
            "The plume reaches the surface. The body is cut at the surface plane -- nothing is "
            "drawn above it"
            + (
                " -- and the centreline stops where it crosses, marked; the rows above the surface "
                "are the model's continuation with the surface stop off, kept in the table."
                if crossed
                else " -- and the table keeps every row."
            )
        )
    notes.append(
        "This is the near field, where the plume still has an interior. "
        "`plumes2 report --gradient-dir` writes a companion figure per quantity that continues to "
        "the mixing-zone boundaries as a far-field slab average."
    )
    notes.extend(quantity.notes)

    return Panel(
        key=f"gradient-{quantity.column.replace('_', '-')}",
        title=f"{_titled(quantity.name)}: the plume in section",
        explanation=(
            f"Where {quantity.name} sits in the water, drawn on the plume itself: distance from "
            "the diffuser along the bottom, depth down the side, the outline the plume's own "
            "diameter, and the quantity filled in as colour across the whole body rather than "
            "reported as one number per station. Read the darkest colour along the centreline "
            "for the worst case a limit is judged against, read how quickly it fades along the "
            "plume for how fast the excursion closes, and read the outline for where in the "
            "water column all of this happens."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=tuple(notes),
    )


def build_chemistry_gradient_panels(
    plot: PlotFrame,
    *,
    units: UnitSystem = SI,
    farfield: pd.DataFrame | None = None,
) -> list[Panel]:
    """A near-field section panel per quantity (pH, aragonite, calcite, brucite), or `[]`.

    Empty when the frame carries no case to re-solve across the section -- a bare exe `.dat` --
    in which case the report keeps its flux-averaged pH and saturation panels. `farfield` is
    accepted for a uniform panel-builder signature but not drawn here: the far-field continuation
    has no cross-plume gradient and belongs on its own axis, which the standalone figures provide.
    """
    del farfield  # the near-field panel does not draw it; see the docstring
    fields = _fields(plot)
    if fields is None:
        return []
    return [
        _panel(fields[quantity.column], plot.case, units)
        for quantity in QUANTITIES
        if quantity.column in fields
    ]


# ------------------------------------------------------------------- standalone figures


def _save(figure: Figure, directory: Path, stem: str, written: list[Path]) -> None:
    for extension in ("svg", "png"):
        path = directory / f"{stem}.{extension}"
        figure.savefig(path, format=extension, bbox_inches="tight", dpi=200)
        written.append(path)
    plt.close(figure)


def write_chemistry_gradient_figures(
    source: Results | PlotFrame,
    out_dir: str | Path,
    *,
    units: UnitSystem | str = SI,
    stem: str = "chem",
) -> list[Path]:
    """Write PNG **and** SVG section figures per quantity into `out_dir`, and return the files.

    Two spans are written per quantity:

    * `<stem>_<quantity>_nearfield.{svg,png}` -- the near-field section, the same figure the
      report panel carries;
    * `<stem>_<quantity>_full.{svg,png}` -- the near field beside the far field, continued to the
      mixing-zone boundaries as a slab average. Written only when the source carried a far field
      with the chemistry column.

    `source` is a run or an already-adapted `PlotFrame`. Returns `[]` if the source carries no
    case to re-solve across the section (a bare `.dat`), the same gate the panels use.
    """
    from plumes2.display import SYSTEMS
    from plumes2.plotframe import from_results
    from plumes2.results import Results

    resolved = SYSTEMS[units] if isinstance(units, str) else units
    if isinstance(source, Results):
        plot: PlotFrame = from_results(source)
        farfield = source.farfield
    else:
        plot = source
        farfield = None

    fields = _fields(plot)
    if fields is None:
        return []
    mixing_zone = _mixing_zone(plot)
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for quantity in QUANTITIES:
        field = fields.get(quantity.column)
        if field is None:
            continue
        title = f"{_titled(quantity.name)} across the plume"
        with _styled():
            frame = _frame(field, plot.case, resolved.length, fixed_aspect=True)
            figure = plt.figure(figsize=(PANEL_WIDTH, frame.figure_height))
            _section_drawing(field, plot.case, resolved, frame, f"{title}, from the side").into(
                figure
            )
            _save(figure, directory, f"{stem}_{quantity.slug}_nearfield", written)
            if farfield is not None and quantity.column in farfield.columns and len(farfield):
                full = _full_figure(field, farfield, plot.case, mixing_zone, resolved, title)
                _save(full, directory, f"{stem}_{quantity.slug}_full", written)
    return written
