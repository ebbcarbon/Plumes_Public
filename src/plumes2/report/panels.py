"""The report's panels: a figure, what it shows, and what to read from it.

> It is always easy down the road to add more plotting features; what's important at this
> stage is for the data to be **organised, accessible, and traceable**.

So this is not a plot library. It is a fixed set of panels that answer the questions the model
exists to answer, each one carrying its own explanation and its own table of values -- because a
figure dump is not a report, and a figure whose numbers cannot be read off is not accessible.

Every panel is built from a `PlotFrame`, never from `Results`, so an exe `.dat` drives the same
panels as one of our runs (see `plumes2.plotframe`). Every panel converts on the way out through a
`UnitSystem`, so the solver stays SI (see `plumes2.display`).

**Design rules taken from the house data-viz standard, and why each applies here:**

* **Series take palette slots in order and are never cycled**, so a line keeps its colour when a
  panel gains a neighbour. Four slots is the ceiling; a fifth series gets its own panel.
* **No dual axes, ever.** Two quantities of different units are two panels -- which is why `pCO2`
  is not drawn beside the carbonate species and the far field's width is not drawn beside its
  dilution. A shared y-scale invents a correlation that is not in the data.
* **Direct labels at the line ends**, never a number on every point, plus a legend whenever there
  is more than one series. Two of the four slots sit below 3:1 contrast against the surface, and
  direct labelling is the documented relief for exactly that.
* **Where lines converge, the legend carries identity instead.** Nudging collided end-labels apart
  detaches them from their lines; that is why the cross-plume panel has a legend and no end labels.
* **Emphasis over decoration.** A single-series panel gets one colour and no legend box -- the
  title already says what is plotted, and a one-swatch legend just restates it.
"""

from __future__ import annotations

import dataclasses
import io
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import matplotlib

matplotlib.use("Agg")  # must precede pyplot; the report never opens a window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from plumes2.crossplume import profile_weight
from plumes2.display import SI, DisplayUnit, UnitSystem
from plumes2.report.palette import (
    AXIS,
    FILL_ALPHA,
    GRID,
    INK_MUTED,
    INK_PRIMARY,
    INK_SECONDARY,
    SERIES,
    SURFACE,
    blend,
    matplotlib_style,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure, FigureBase

    from plumes2.config import Case
    from plumes2.plotframe import PlotFrame

__all__ = [
    "MAX_OVERLAY_RUNS",
    "PANEL_WIDTH",
    "TABLE_ROWS",
    "Drawing",
    "Panel",
    "TooManyRunsError",
    "build_overlay_panels",
    "build_panels",
    "figure_to_svg",
]

#: Rows in a panel's table. Enough to read the shape off, few enough to scan; both endpoints are
#: always among them, and the run's CSV carries every row at full precision.
TABLE_ROWS = 12

#: A surface-coloured backing for a label that has to sit on a colour field and stay legible.
_BACKING: dict[str, Any] = {
    "boxstyle": "round,pad=0.2",
    "facecolor": SURFACE,
    "edgecolor": "none",
    "alpha": 0.85,
}

#: Width of a panel figure, inches. Each drawing declares its own height against this width, and
#: the PDF composer reserves a band of the same proportions, so a panel keeps its shape whichever
#: renderer serves it.
PANEL_WIDTH = 7.2


@dataclass(frozen=True, slots=True)
class Drawing:
    """A panel's figure as a *procedure*: how to draw it onto axes someone else made.

    Two renderers share every panel. The HTML page wants an inline SVG of a figure sized here;
    the PDF composer wants the same picture drawn into a band it has reserved on a letter page.
    Serialising once and pasting the result cannot serve both -- matplotlib has no way to nest a
    finished figure inside another -- so a panel carries the drawing procedure and each renderer
    supplies the figure. `svg()` is the first renderer's entry point, `into()` the second's.
    """

    #: Draws the panel onto `axes`, which belong to `figure`. Everything the panel needs is
    #: already closed over; the figure is passed for the panels that add a colorbar.
    draw: Callable[[FigureBase, Axes], None]
    #: Figure height in inches at `PANEL_WIDTH`.
    height: float = 3.4
    #: Axes projection -- `"3d"` for the trajectory panel, `None` for everything else.
    projection: str | None = None

    def into(self, figure: FigureBase) -> Axes:
        """Draw onto fresh axes in `figure` -- a figure or a subfigure -- and return them."""
        axes = figure.add_subplot(projection=self.projection)
        self.draw(figure, axes)
        return axes

    def svg(self) -> str:
        """The drawing as a standalone figure, serialised to an inline SVG fragment.

        The style context is held open until the SVG is written -- see `_styled` for the rcParams
        that are read at legend and save time rather than when the axes are made.
        """
        with _styled():
            figure = plt.figure(figsize=(PANEL_WIDTH, self.height))
            self.into(figure)
            return figure_to_svg(figure)


@dataclass(frozen=True, slots=True)
class Panel:
    """One section of the report: a figure, its explanation, and its values as text."""

    #: Stable anchor id, so a panel can be linked to.
    key: str
    title: str
    #: What the panel shows and what to read from it. Prose, not a caption.
    explanation: str
    #: The figure, already serialised. Inline SVG keeps the report one file. **Empty for a
    #: panel whose content is its table** -- the validation report is made of those.
    svg: str
    #: The plotted values. Every panel has one: a figure whose numbers cannot be read is not
    #: accessible, and two of the palette's slots are below the contrast floor.
    table: pd.DataFrame
    #: Anything true of this panel that a reader could otherwise be misled by.
    notes: tuple[str, ...] = field(default_factory=tuple)
    #: How to draw the figure again, for a renderer that lays out its own pages. `None` for a
    #: table-only panel, whose `svg` is empty too.
    drawing: Drawing | None = None


def figure_to_svg(figure: Figure) -> str:
    """Serialise a figure to an inline SVG fragment, dropping the XML preamble.

    The `<?xml?>` declaration and DOCTYPE are illegal mid-document, so they are stripped and the
    `<svg>` element handed back for direct embedding. No base64 and no separate files: the report
    stays one thing you can email. The dpi only reaches artists that asked to be rasterised -- the
    chemistry section's colour field -- and everything else stays vector.
    """
    buffer = io.StringIO()
    figure.savefig(buffer, format="svg", bbox_inches="tight", dpi=200)
    plt.close(figure)
    markup = buffer.getvalue()
    return markup[markup.index("<svg") :].strip()


# --------------------------------------------------------------------------- shared machinery


def _downstream(frame: pd.DataFrame) -> np.ndarray:
    """Horizontal distance from the diffuser, m. The x-axis of every quantitative panel.

    The diffuser is the origin -- `x_m` and `y_m` are already measured from it -- so this is the
    radius in the horizontal plane. Distance rather than time, because a mixing-zone limit is
    written as a distance and nobody regulates seconds.
    """
    return np.hypot(frame["x_m"].to_numpy(dtype=float), frame["y_m"].to_numpy(dtype=float))


def _short(value: float) -> str:
    """A number for a direct label: readable at a glance, and never in exponent form by surprise.

    `:,.3g` looks tidy until a dilution of 3320 comes out as `3.32e+03`, which nobody reads as
    three thousand. So the format follows the magnitude, and the exponent is reserved for the
    values that genuinely need it -- a brucite saturation of 0.0142, say.
    """
    magnitude = abs(value)
    if magnitude >= 1000.0:
        return f"{value:,.0f}"
    if magnitude >= 10.0:
        return f"{value:,.1f}"
    if magnitude >= 0.01:
        return f"{value:,.3g}"
    return f"{value:.1e}"


def _axis_label(name: str, unit_label: str) -> str:
    return f"{name} ({unit_label})" if unit_label else name


def _styled() -> AbstractContextManager[None]:
    """`rc_context` under the report's style -- the one place the stub mismatch is handled.

    matplotlib types `rc_context`'s argument with a `Literal` of every valid key; ours is a plain
    `dict[str, Any]` built in `palette.py`. Narrowing it here keeps the cast to a single line, and
    `warn_unused_ignores` will flag it if the stubs ever widen.
    """
    return plt.rc_context(matplotlib_style())  # type: ignore[arg-type]


def _line(axes: Axes, x: np.ndarray, y: np.ndarray, slot: int, label: str) -> None:
    """One series, in its assigned slot colour, carrying its own legend label."""
    axes.plot(x, y, color=SERIES[slot], linewidth=1.6, label=label)


def _legend(axes: Axes, *, outside: bool, title: str | None = None) -> None:
    """The legend, which is always present for two or more series.

    `outside` puts it clear of the axes on the right, which is the reliable answer for three or
    more series: an inside legend has to be placed somewhere, and with four converging lines every
    corner is somewhere a line goes. Two well-separated series can keep it inside, where it costs
    no width.
    """
    if outside:
        axes.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), borderaxespad=0.0, title=title)
    else:
        axes.legend(loc="upper left", title=title)


def _end_labels(
    axes: Axes,
    entries: list[tuple[np.ndarray, np.ndarray, str, int]],
    *,
    minimum_gap: float = 0.055,
) -> None:
    """Label each line at its right-hand end, dropping any that would collide.

    Text never wears the series colour: a light hue is illegible as text, and identity comes from
    the coloured mark the label sits against. So the label is ink and the dot is the swatch, with a
    2px surface ring so it stays legible where it crosses another line.

    ⚠️ **Collisions are dropped, not nudged.** Moving a label off its own line to make room
    detaches it from what it names and reads as noise; the legend and the table already carry the
    identity, so a dropped label loses nothing. `minimum_gap` is in axes fractions.

    ⚠️ Every artist here is kept out of the legend. They would otherwise be picked up as unnamed
    entries and shift every legend label onto the wrong series.
    """
    # The limits must be final before y is converted to axes fractions. Asking for them is what
    # finalises them -- the view limits are autoscaled lazily on first read -- and it costs nothing,
    # where drawing the figure to the same end cost a quarter of a second per panel on a PDF page.
    axes.get_xlim()
    axes.get_ylim()
    transform = axes.transLimits
    placed: list[float] = []
    for x, y, text, slot in entries:
        if not len(x):
            continue
        end_x, end_y = float(x[-1]), float(y[-1])
        fraction = float(transform.transform((end_x, end_y))[1])
        axes.plot(
            [end_x],
            [end_y],
            marker="o",
            markersize=5,
            color=SERIES[slot],
            markeredgecolor=SURFACE,
            markeredgewidth=1.6,
            linestyle="none",
            zorder=5,
            label="_nolegend_",
        )
        if any(abs(fraction - other) < minimum_gap for other in placed):
            continue
        placed.append(fraction)
        axes.annotate(
            text,
            xy=(end_x, end_y),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=8,
            color=INK_SECONDARY,
            annotation_clip=False,
        )


def _merge_start(frame: pd.DataFrame, distance: np.ndarray) -> float | None:
    """The distance at which merging begins, or `None` if the run never merges mid-way.

    `None` also for a run merged from the first row: there is no transition to mark, and the
    sentence about the curve changing slope would describe nothing on the figure.
    """
    if "merged" not in frame.columns:
        return None
    merged = frame["merged"].to_numpy(dtype=bool)
    if not merged.any() or merged.all():
        return None
    return float(distance[int(np.argmax(merged))])


def _merge_note(frame: pd.DataFrame, distance: np.ndarray) -> str | None:
    """The sentence that explains the merge hairline, or `None` when there is none to explain."""
    if _merge_start(frame, distance) is None:
        return None
    return (
        "The hairline marks where neighbouring plumes meet. Past it each plume entrains over "
        "less of its surface and the cross-plume profile flattens, so the curve changing slope "
        "there is the model rather than a numerical artefact."
    )


def _mark_merge(axes: Axes, frame: pd.DataFrame, distance: np.ndarray) -> None:
    """A hairline where merging begins. `_merge_note` carries the sentence that explains it.

    Worth marking on every panel drawn against distance: the entrainment terms and the
    concentration profile both change there, so a kink in the curve is physics rather than noise.
    """
    at = _merge_start(frame, distance)
    if at is None:
        return
    axes.axvline(at, color=AXIS, linewidth=0.8, zorder=0, label="_nolegend_")
    axes.annotate(
        "plumes merge",
        xy=(at, 0.98),
        xycoords=("data", "axes fraction"),
        xytext=(3, 0),
        textcoords="offset points",
        va="top",
        ha="left",
        fontsize=8,
        color=INK_MUTED,
    )


def _table(frame: pd.DataFrame, columns: dict[str, str], rows: int = TABLE_ROWS) -> pd.DataFrame:
    """`columns` of `frame`, downsampled to `rows` with both endpoints kept.

    Downsampled rather than truncated: the last row is the answer -- the dilution the far field
    starts from -- and a table that stops at row 12 of 200 hides exactly that.
    """
    if not len(frame):
        return pd.DataFrame(columns=list(columns.values()))
    if len(frame) <= rows:
        picked = np.arange(len(frame))
    else:
        picked = np.unique(np.linspace(0, len(frame) - 1, rows).round().astype(int))
    return frame.iloc[picked][list(columns)].rename(columns=columns).reset_index(drop=True)


def _scale(table: pd.DataFrame, unit: DisplayUnit, columns: tuple[str, ...]) -> pd.DataFrame:
    """Convert the named table columns from SI into `unit`.

    Tables are cut from the SI frame and *named* in display units by the caller, so this is what
    makes the names true. Naming and scaling in separate steps is deliberate: a forgotten scale
    shows up as a wrong number under a right label in the tests, rather than silently agreeing.
    """
    scaled = table.copy()
    for column in columns:
        scaled[column] = unit(scaled[column].to_numpy(dtype=float))
    return scaled


# --------------------------------------------------------------------------- the panels


def _equal_limits(
    *groups: tuple[np.ndarray, ...], floor: float = 0.12
) -> list[tuple[float, float]]:
    """Axis limits for a true-scale box: each axis spans its data, and none is thinner than `floor`
    of the longest.

    A true-scale box is what makes the wireframe honest -- a cone drawn on unequal axes states a
    width it does not have -- but a plume discharged along +y has an x extent of a few times
    1e-16, and a box with a zero-width side collapses. The floor keeps every side wide enough to
    read, and the padding keeps the tube off the panes.
    """
    ranges = [
        (min(float(a.min()) for a in group), max(float(a.max()) for a in group)) for group in groups
    ]
    longest = max(hi - lo for lo, hi in ranges) or 1.0
    limits = []
    for lo, hi in ranges:
        want = max((hi - lo) * 1.08, longest * floor)
        middle = 0.5 * (lo + hi)
        limits.append((middle - 0.5 * want, middle + 0.5 * want))
    return limits


# ------------------------------------------------------------- the free surface cuts the drawing
#
# With `stop_at_surface` off the integration continues past the contact, and rows with a negative
# depth are the model's continuation into the air (the operator's rule for the Macoma studies,
# PLAN section 2). Those rows stay in every table and CSV -- they are what the model did. The
# *figures* may not draw water where there is none: every body is cut at z = 0, the centreline
# stops where it crosses, and the panel says so (operator, 2026-09-09).


def _surface_crossing(depth: np.ndarray) -> int | None:
    """Index of the first row whose centreline is above the surface (depth < 0), or `None`."""
    above = np.flatnonzero(np.asarray(depth, dtype=float) < 0.0)
    return int(above[0]) if len(above) else None


def _cut_at_surface(depth: np.ndarray, *series: np.ndarray) -> tuple[np.ndarray, ...]:
    """`depth` and each companion series truncated where the centreline crosses the surface.

    The rows before the crossing are kept and one interpolated point is appended at depth 0, so a
    line ends exactly on the plane. Without a crossing everything comes back unchanged; a
    centreline already above the surface at its first row has nothing to draw and comes back empty.
    """
    depth = np.asarray(depth, dtype=float)
    cut = _surface_crossing(depth)
    if cut is None:
        return (depth, *(np.asarray(s, dtype=float) for s in series))
    if cut == 0:
        return (depth[:0], *(np.asarray(s, dtype=float)[:0] for s in series))
    fraction = depth[cut - 1] / (depth[cut - 1] - depth[cut])
    out = [np.append(depth[:cut], 0.0)]
    for values in series:
        values = np.asarray(values, dtype=float)
        out.append(
            np.append(values[:cut], values[cut - 1] + fraction * (values[cut] - values[cut - 1]))
        )
    return tuple(out)


def _surface_rim(mesh_x: np.ndarray, mesh_y: np.ndarray, mesh_z: np.ndarray) -> list[np.ndarray]:
    """Where the tube meets the surface plane: polylines of `(x, y)` along the run, at z = 0.

    Each ring is scanned for sign changes of depth between neighbouring spokes and the crossing
    interpolated; a ring that pierces the plane gives two crossings, one each side, and these are
    joined ring to ring into the two rims of the cut. Rings wholly above or below give nothing.
    """
    sides: list[list[tuple[float, float]]] = [[], []]
    for ring in range(mesh_z.shape[0]):
        z = mesh_z[ring]
        crossings: list[tuple[float, float]] = []
        for spoke in range(len(z) - 1):
            if (z[spoke] < 0.0) != (z[spoke + 1] < 0.0):
                fraction = z[spoke] / (z[spoke] - z[spoke + 1])
                crossings.append(
                    (
                        mesh_x[ring, spoke]
                        + fraction * (mesh_x[ring, spoke + 1] - mesh_x[ring, spoke]),
                        mesh_y[ring, spoke]
                        + fraction * (mesh_y[ring, spoke + 1] - mesh_y[ring, spoke]),
                    )
                )
        if len(crossings) >= 2:
            sides[0].append(crossings[0])
            sides[1].append(crossings[-1])
    return [np.array(side) for side in sides if len(side) >= 2]


def _surface_note(frame: pd.DataFrame, length: DisplayUnit) -> str | None:
    """The sentence a panel owes when the plume reaches the surface, or `None` when it does not."""
    depth = frame["depth_m"].to_numpy(dtype=float)
    top = depth - frame["plume_diameter_m"].to_numpy(dtype=float) / 2.0
    if not np.any(top < 0.0):
        return None
    distance = _downstream(frame)
    first_touch = int(np.flatnonzero(top < 0.0)[0])
    where = f"{float(length(distance[first_touch])):,.2f} {length.label} from the diffuser"
    if "time_s" in frame.columns:
        where += f" (t = {float(frame['time_s'].iloc[first_touch]):,.0f} s)"
    if _surface_crossing(depth) is None:
        return (
            f"The plume's upper edge reaches the surface at {where}. The figure cuts the body at "
            "the surface plane -- nothing is drawn above it -- and the table keeps every row."
        )
    _, cut_distance = _cut_at_surface(depth, distance)
    at = (
        f"{float(length(cut_distance[-1])):,.2f} {length.label}"
        if len(cut_distance)
        else "the port itself"
    )
    above = int(np.sum(depth < 0.0))
    return (
        f"The plume's upper edge reaches the surface at {where}, and its centreline crosses it at "
        f"{at}. The figure stops the centreline there and cuts the body at the surface plane; the "
        f"{above} rows with the centreline above the surface are the model's continuation with the "
        "surface stop off -- kept in the table and the CSV, not drawn."
    )


def _tube(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    radius: np.ndarray,
    *,
    rings: int = 28,
    spokes: int = 12,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The plume body as a wireframe surface: rings of the local radius around the centreline.

    Each ring lies in the plane normal to the trajectory at its station, so a bending jet keeps
    its round section through the bend; `rings` stations are picked evenly along the run and
    `spokes` longitudinal lines join them. The result is the cone-that-bends a plume actually is,
    drawn from the model's own diameter at every station rather than sketched.
    """
    count = len(x)
    picked = np.unique(np.linspace(0, count - 1, min(rings, count)).round().astype(int))
    centre = np.column_stack([x, y, z])
    if count > 1:
        tangent = np.gradient(centre, axis=0)
    else:
        tangent = np.tile([1.0, 0.0, 0.0], (count, 1))
    size = np.linalg.norm(tangent, axis=1, keepdims=True)
    tangent = tangent / np.where(size > 0.0, size, 1.0)
    # The first ring direction is horizontal and across the path; for a vertical jet, where that
    # is undefined, it falls back to +y and the second direction follows from the cross product.
    across = np.cross(tangent, np.array([0.0, 0.0, 1.0]))
    across_size = np.linalg.norm(across, axis=1, keepdims=True)
    across = np.where(
        across_size > 1e-9,
        across / np.where(across_size > 0.0, across_size, 1.0),
        np.tile([0.0, 1.0, 0.0], (count, 1)),
    )
    second = np.cross(tangent, across)
    theta = np.linspace(0.0, 2.0 * np.pi, spokes + 1)
    ring = radius[picked, None, None] * (
        np.cos(theta)[None, :, None] * across[picked, None, :]
        + np.sin(theta)[None, :, None] * second[picked, None, :]
    )
    points = centre[picked, None, :] + ring
    return points[..., 0], points[..., 1], points[..., 2]


def _view_azimuth(x: np.ndarray, y: np.ndarray, *, fallback: float = -58.0) -> float:
    """The camera azimuth that shows the plume from its own side.

    matplotlib's `azim` is where the camera stands in the x-y plane, degrees counter-clockwise
    from +x; screen-right is then `azim + 90`. Standing at `heading - 90` puts the run across
    the page left to right, and the 25 deg pulled back from that lets the near end come toward
    the reader so depth and width both read. Fixed by the plume's heading rather than by the
    axes, so the same discharge looks the same whichever way the case's frame is turned, and a
    straight run is seen as straight rather than foreshortened along the line of sight. A jet
    with no horizontal travel has no side; it keeps the default view.
    """
    dx, dy = float(x[-1] - x[0]), float(y[-1] - y[0])
    if float(np.hypot(dx, dy)) < 1e-9:
        return fallback
    return float(np.degrees(np.arctan2(dy, dx))) - 90.0 - 25.0


def _panel_trajectory_3d(plot: PlotFrame, units: UnitSystem) -> Panel:
    """The plume in space as a wireframe body, with the diffuser at the origin."""
    frame = plot.frame
    length = units.length
    x = length(frame["x_m"].to_numpy(dtype=float))
    y = length(frame["y_m"].to_numpy(dtype=float))
    depth = length(frame["depth_m"].to_numpy(dtype=float))
    radius = length(frame["plume_diameter_m"].to_numpy(dtype=float)) / 2.0
    # The surface plane cuts the body: nothing is drawn above z = 0. Rows after the centreline
    # crosses the surface leave the figure (they stay in the table); what is left is clamped to
    # the plane -- its cut face lies flat on the water -- and the rims where it pierces are drawn.
    cut = _surface_crossing(depth)
    shown = slice(None) if cut is None else slice(0, max(cut, 1))
    mesh_x, mesh_y, mesh_z_raw = _tube(x[shown], y[shown], depth[shown], radius[shown])
    breached = bool(np.any(mesh_z_raw < 0.0))
    mesh_z = np.maximum(mesh_z_raw, 0.0)
    rims = _surface_rim(mesh_x, mesh_y, mesh_z_raw) if breached else []
    line_z, line_x, line_y = _cut_at_surface(depth, x, y)
    if not len(line_x):  # above the surface from the first row: the port alone is in the water
        line_x, line_y, line_z = x[:1], y[:1], np.maximum(depth[:1], 0.0)
    limits = _equal_limits((line_x, mesh_x), (line_y, mesh_y), (line_z, mesh_z))
    azimuth = _view_azimuth(x, y)
    surfaced = _surface_note(frame, length)

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        # The drawing asks for the 3-D projection, so these axes carry the z methods; mpl_toolkits
        # ships no stubs to say so, hence the loosened type rather than a cast.
        space: Any = axes
        space.plot_wireframe(
            mesh_x, mesh_y, mesh_z, rstride=1, cstride=1, color=SERIES[0], linewidth=0.45,
            alpha=0.55,
        )  # fmt: skip
        space.plot(line_x, line_y, line_z, color=SERIES[0], linewidth=1.4, zorder=3)
        space.scatter([0.0], [0.0], [depth[0]], color=SERIES[1], s=28, zorder=5, depthshade=False)
        space.text(0.0, 0.0, depth[0], "  diffuser", fontsize=8, color=INK_SECONDARY)
        (x_lo, x_hi), (y_lo, y_hi), (z_lo, z_hi) = limits
        if breached:
            # The surface itself, as a translucent plane, with the rims of the cut on it.
            space.plot_surface(
                np.array([[x_lo, x_hi], [x_lo, x_hi]]), np.array([[y_lo, y_lo], [y_hi, y_hi]]),
                np.zeros((2, 2)), color=AXIS, alpha=0.18, linewidth=0, zorder=0, shade=False,
            )  # fmt: skip
            for rim in rims:
                space.plot(
                    rim[:, 0], rim[:, 1], np.zeros(len(rim)), color=INK_PRIMARY, linewidth=1.0,
                    zorder=4,
                )  # fmt: skip
            if _surface_crossing(depth) is not None:
                space.scatter(
                    [line_x[-1]], [line_y[-1]], [0.0], marker="x", color=INK_PRIMARY, s=30,
                    zorder=6, depthshade=False,
                )  # fmt: skip
                space.text(
                    line_x[-1], line_y[-1], 0.0, "  surfaces", fontsize=8, color=INK_SECONDARY
                )
        # The centreline's shadow in plan, on the floor of the box: the horizontal path with no
        # depth in it, so a straight run reads straight however the body above it bends. Only the
        # part of the run that is in the water casts one.
        floor = np.full_like(line_x, z_hi)
        space.plot(line_x, line_y, floor, color=INK_MUTED, linewidth=0.9, linestyle="--", zorder=1)
        space.plot([0.0], [0.0], [z_hi], marker="o", markersize=3, color=INK_MUTED, zorder=1)

        space.set_xlabel(_axis_label("x from the diffuser", length.label))
        space.set_ylabel(_axis_label("y from the diffuser", length.label))
        space.set_zlabel(_axis_label("depth", length.label))
        space.set_xlim(x_lo, x_hi)
        space.set_ylim(y_lo, y_hi)
        space.set_zlim(z_hi, z_lo)  # down is down
        # True scale: the box's sides are the axis spans, so the cone has its real proportions.
        space.set_box_aspect(tuple(hi - lo for lo, hi in limits), zoom=1.25)
        space.view_init(elev=22, azim=azimuth)
        for pane in (space.xaxis, space.yaxis, space.zaxis):
            pane.pane.set_facecolor(SURFACE)
            pane.pane.set_alpha(1.0)
            pane.pane.set_edgecolor(GRID)

    drawing = Drawing(draw, height=4.0, projection="3d")
    table = _table(
        frame.assign(_d=_downstream(frame)),
        {
            "_d": f"distance ({length.label})",
            "x_m": f"x ({length.label})",
            "y_m": f"y ({length.label})",
            "depth_m": f"depth ({length.label})",
            "plume_diameter_m": f"diameter ({length.label})",
        },
    )
    return Panel(
        key="trajectory-3d",
        title="The plume in space",
        explanation=(
            "Where the plume goes, positioned relative to the diffuser, which sits at the "
            "origin. What leaves the port is a jet that bends into the current, rises while it is "
            "still buoyant, and levels off when it stops being so. The wireframe is the plume's "
            "own body -- each ring is the model's diameter at that station, set square to the "
            "path -- so the cone widening as it goes is the entrainment happening. The view is "
            "taken from the plume's own side, so the run crosses the page; the dashed line on the "
            "floor is the centreline's shadow in plan. This panel is for orientation; the panels "
            "below carry every number."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, tuple(table.columns)),
        notes=(
            "Depth increases downward, matching how a water column is usually drawn. The exe's "
            "own `Depth` column is negative-down under the same name; this report has flipped it.",
            "The three axes are drawn to one scale, so the body has its true proportions: a "
            "plume is metres long and decimetres across, and that is how it looks here. A "
            "direction the plume does not travel in is given a little width so its axis can be "
            "read, which is why a straight run still sits in a box -- its shadow on the floor "
            "shows it straight.",
            "`x` and `y` are the model's frame, not east and north. The case's discharge and "
            "current directions are angles counter-clockwise from +x, as the PLUMES manual "
            "defines them, and nothing in the model says which way +x points on the site; turn "
            "the frame to the site yourself.",
            "One jet is drawn -- the representative plume the model integrates. For a multiport "
            "diffuser the top-down view below places every jet.",
            *((surfaced,) if surfaced else ()),
        ),
    )


def _plan_outline(x: np.ndarray, y: np.ndarray, radius: np.ndarray) -> np.ndarray:
    """The plume's footprint in plan as a closed polygon, `(m, 2)`.

    Each station is widened by its radius square to the horizontal path, one edge out and back
    along the other. A jet with no horizontal travel -- straight up in still water -- has no path
    to be square to, so its footprint is the disc of its widest station instead.
    """
    travel = float(np.hypot(np.ptp(x), np.ptp(y)))
    widest = float(radius.max()) if len(radius) else 0.0
    if travel < 0.05 * max(widest, 1e-12):
        theta = np.linspace(0.0, 2.0 * np.pi, 73)
        return np.column_stack(
            [float(x.mean()) + widest * np.cos(theta), float(y.mean()) + widest * np.sin(theta)]
        )
    dx, dy = np.gradient(x), np.gradient(y)
    size = np.hypot(dx, dy)
    safe = np.where(size > 0.0, size, 1.0)
    normal_x = np.where(size > 0.0, -dy / safe, 0.0)
    normal_y = np.where(size > 0.0, dx / safe, 1.0)
    left = np.column_stack([x + radius * normal_x, y + radius * normal_y])
    right = np.column_stack([x - radius * normal_x, y - radius * normal_y])
    return np.vstack([left, right[::-1], left[:1]])


def _panel_plan_view(plot: PlotFrame, units: UnitSystem) -> Panel:
    """The diffuser from above: every jet, where they merge, and the footprint they occupy."""
    from plumes2.nearfield.state import horizontal_unit

    frame = plot.frame
    length = units.length
    case = plot.case
    x = length(frame["x_m"].to_numpy(dtype=float))
    y = length(frame["y_m"].to_numpy(dtype=float))
    radius = length(frame["plume_diameter_m"].to_numpy(dtype=float)) / 2.0
    distance = length(_downstream(frame))
    # Footprints are drawn only while the centreline is in the water; where it surfaces the
    # footprint ends and the point is marked. The rows above stay in the table.
    depth = length(frame["depth_m"].to_numpy(dtype=float)) if "depth_m" in frame.columns else None
    cut = _surface_crossing(depth) if depth is not None else None
    if depth is not None and cut is not None:
        _, x_shown, y_shown, r_shown = _cut_at_surface(depth, x, y, radius)
        if not len(x_shown):
            x_shown, y_shown, r_shown = x[:1], y[:1], radius[:1]
        shown = frame.iloc[: max(cut, 1)]
        distance_shown = distance[: max(cut, 1)]
    else:
        x_shown, y_shown, r_shown, shown, distance_shown = x, y, radius, frame, distance
    outline = _plan_outline(x_shown, y_shown, r_shown)
    surfaced = _surface_note(frame, length) if depth is not None else None

    offsets, axis = _port_offsets(case, length)
    n_ports = len(offsets)

    merge_at = _merge_start(shown, distance_shown)
    merge_index = (
        int(np.argmin(np.abs(distance_shown - merge_at))) if merge_at is not None else None
    )

    # The wastefield width the far field starts from, drawn as a bracket square to the path at the
    # end of the near field. It is the extent the near field hands on, and for a multiport
    # diffuser it is much more than one jet's diameter.
    wastefield: float | None = None
    if case is not None and n_ports > 1:
        wastefield = float(length(case.wastefield_width(float(frame["plume_diameter_m"].iloc[-1]))))
    heading = np.array([np.gradient(x)[-1], np.gradient(y)[-1]]) if len(x) > 1 else axis[::-1]
    if float(np.hypot(*heading)) < 1e-12:
        heading = np.array([axis[1], -axis[0]])
    heading = heading / float(np.hypot(*heading))
    across = np.array([-heading[1], heading[0]])

    current: tuple[float, float] | None = None
    if case is not None:
        speeds = [level.current_speed for level in case.ambient.levels]
        if max(speeds) > 0.0:
            current = (case.current_direction_at_port, max(speeds))

    everything_x = np.concatenate([outline[:, 0] + ox for ox, _ in offsets] + [offsets[:, 0]])
    everything_y = np.concatenate([outline[:, 1] + oy for _, oy in offsets] + [offsets[:, 1]])
    x_span = float(np.ptp(everything_x)) or 1.0
    y_span = float(np.ptp(everything_y)) or 1.0
    plot_width = PANEL_WIDTH - 1.3
    height = min(max(plot_width * y_span / x_span, 1.5), 4.5) + 1.0

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.set_axisbelow(True)
        for ox, oy in offsets:
            axes.fill(outline[:, 0] + ox, outline[:, 1] + oy, color=SERIES[0], alpha=0.16, lw=0)
            axes.plot(outline[:, 0] + ox, outline[:, 1] + oy, color=INK_MUTED, linewidth=0.5)
            axes.plot(x_shown + ox, y_shown + oy, color=SERIES[0], linewidth=0.9, alpha=0.9)
        if cut is not None:
            at = offsets.mean(axis=0) + np.array([x_shown[-1], y_shown[-1]])
            axes.plot(
                [at[0]], [at[1]], marker="x", markersize=6, color=INK_PRIMARY, linestyle="none",
                zorder=6,
            )  # fmt: skip
            axes.annotate(
                "centreline surfaces", xy=(at[0], at[1]), xytext=(5, -5),
                textcoords="offset points", ha="left", va="top", fontsize=7.5,
                color=INK_SECONDARY,
            )  # fmt: skip
        if n_ports > 1:
            axes.plot(
                offsets[[0, -1], 0], offsets[[0, -1], 1], color=INK_SECONDARY, linewidth=1.4,
                zorder=4, solid_capstyle="butt",
            )  # fmt: skip
        axes.plot(
            offsets[:, 0], offsets[:, 1], marker="o", markersize=3.5, color=SERIES[1],
            markeredgecolor=SURFACE, markeredgewidth=0.8, linestyle="none", zorder=5,
        )  # fmt: skip
        axes.annotate(
            "diffuser" if n_ports == 1 else f"diffuser, {n_ports} ports",
            xy=(offsets[0, 0], offsets[0, 1]),
            xytext=(-4, -4),
            textcoords="offset points",
            ha="right",
            va="top",
            fontsize=7.5,
            color=INK_SECONDARY,
        )
        if merge_index is not None:
            points = offsets + np.array([x_shown[merge_index], y_shown[merge_index]])
            axes.plot(
                points[:, 0], points[:, 1], color=INK_PRIMARY, linewidth=0.8, linestyle=":",
                zorder=4,
            )  # fmt: skip
            axes.annotate(
                "plumes merge",
                xy=(points[-1, 0], points[-1, 1]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7.5,
                color=INK_SECONDARY,
            )
        if wastefield is not None:
            end = offsets.mean(axis=0) + np.array([x[-1], y[-1]])
            bracket = np.vstack([end - 0.5 * wastefield * across, end + 0.5 * wastefield * across])
            axes.plot(
                bracket[:, 0], bracket[:, 1], color=INK_PRIMARY, linewidth=1.0, linestyle="--",
                zorder=4,
            )  # fmt: skip
            # Centred just beyond the bracket, on the side the plume is heading -- clear of the
            # footprints below it and of the current arrow in the corner.
            axes.annotate(
                f"wastefield width {wastefield:,.1f} {length.label}",
                xy=(end[0] + 0.0, end[1]),
                xytext=(6.0 * heading[0], 6.0 * heading[1]),
                textcoords="offset points",
                ha="center",
                va="bottom" if heading[1] >= 0.0 else "top",
                fontsize=7.5,
                color=INK_SECONDARY,
            )
        if current is not None:
            direction = horizontal_unit(current[0])
            axes.annotate(
                "",
                xy=(0.96, 0.92),
                xycoords="axes fraction",
                xytext=(-26.0 * direction[0], -26.0 * direction[1]),
                textcoords="offset points",
                arrowprops={"arrowstyle": "->", "color": INK_SECONDARY, "linewidth": 1.0},
            )
            axes.annotate(
                "current",
                xy=(0.96, 0.92),
                xycoords="axes fraction",
                xytext=(-8, 0),
                textcoords="offset points",
                ha="right",
                va="center",
                fontsize=7.5,
                color=INK_MUTED,
            )
        # Room above the bracket for its label, and beside the diffuser for its own.
        axes.margins(x=0.04, y=0.2)
        axes.set_aspect("equal", adjustable="box")
        axes.set_xlabel(_axis_label("x from the diffuser", length.label))
        axes.set_ylabel(_axis_label("y from the diffuser", length.label))
        axes.set_title(
            "Top-down view: the plume's footprint"
            if n_ports == 1
            else f"Top-down view: {n_ports} jets, their merging and the plume's extent"
        )

    drawing = Drawing(draw, height=height)

    columns = {
        "_d": f"distance ({length.label})",
        "x_m": f"x ({length.label})",
        "y_m": f"y ({length.label})",
        "plume_diameter_m": f"width ({length.label})",
    }
    if "merged" in frame.columns:
        columns["merged"] = "merged"
    table = _table(frame.assign(_d=_downstream(frame)), columns)
    table = _scale(table, length, tuple(v for k, v in columns.items() if k != "merged"))

    ports = "a single port" if n_ports == 1 else f"{n_ports} ports"
    notes = [
        "The model integrates one representative jet and applies its merging correction to it; "
        "the others are that jet translated to their own ports. Exact for a straight diffuser of "
        "identical ports in a uniform current, an approximation otherwise.",
        "Horizontal extent only: how deep any of this sits is in the side view above.",
        "`x` and `y` are the model's frame (directions are angles counter-clockwise from +x, the "
        "PLUMES manual's convention), not east and north; the current arrow and the diffuser line "
        "are drawn in that frame, and orienting it to the site is the reader's step.",
    ]
    if merge_index is not None:
        notes.append(
            "The dotted line is where neighbouring jets meet and the model starts treating them "
            "as one confined slab: past it each entrains over less of its surface and the "
            "cross-plume profile flattens."
        )
    elif "merged" in frame.columns and bool(frame["merged"].all()):
        notes.append(
            "The jets are merged from the port onward -- the ports sit closer than a plume "
            "diameter -- so there is no merge line to draw: the whole footprint is one confined "
            "slab from the start."
        )
    if wastefield is not None:
        notes.append(
            "The dashed bracket at the end of the near field is the wastefield width the far "
            "field starts from -- the diffuser's span across the current plus one plume "
            "diameter -- and it is the extent the far-field panels grow from."
        )
    if case is None:
        notes.append(
            "A `.dat` carries no port count or spacing, so the trace is drawn as a single jet. "
            "Report it with `--case-file` to see the whole diffuser."
        )
    if surfaced:
        notes.append(surfaced)
        if cut is not None and wastefield is not None:
            notes.append(
                "The wastefield bracket still sits at the near-field end, which is above the "
                "surface here: the far field starts from the model's continuation, as the exe's "
                "does with the surface stop off."
            )
    return Panel(
        key="plan-view",
        title="Top-down view",
        explanation=(
            f"The discharge seen from above: {ports} along the diffuser, each jet drawn as the "
            "shaded footprint of the plume it makes -- as wide as the model says at every "
            "station -- with the centreline through it. Where the footprints overlap the jets have "
            "run into each other, and the dotted line marks where the model starts treating them "
            "as merged. Read the outline for the ground the plume covers in plan, and the bracket "
            "at the end of the near field for the width the far field carries on with."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=tuple(notes),
    )


def _port_offsets(case: Case | None, length: DisplayUnit) -> tuple[np.ndarray, np.ndarray]:
    """Every port as an offset from the representative one, `(n, 2)`, and the diffuser's axis.

    The diffuser line runs square to the port direction -- the convention the solver's merging
    law uses -- and the ports sit symmetrically about the origin, which is where the model puts
    its one jet. Without a case there is one port at the origin and the axis is +y.
    """
    from plumes2.nearfield.state import horizontal_unit

    n_ports = case.diffuser.n_ports if case is not None else 1
    spacing = float(length(case.diffuser.port_spacing)) if case is not None else 0.0
    axis = (
        horizontal_unit(case.diffuser.horizontal_angle + 90.0)
        if case is not None
        else np.array([0.0, 1.0])
    )
    offsets = np.array(
        [(k - (n_ports - 1) / 2.0) * spacing * axis for k in range(n_ports)], dtype=float
    ).reshape(n_ports, 2)
    return offsets, axis


def _panel_plan_farfield(plot: PlotFrame, units: UnitSystem, farfield: pd.DataFrame) -> Panel:
    """The plan view carried on: the wastefield from the near-field end out to the mixing zones.

    Drawn in the far field's own frame -- distance from the diffuser along the current across
    the page, offset across the current up the page -- because that is the axis Brooks
    integrates along and the axis a mixing-zone limit is quoted on. The near field is projected
    into the same frame so the two join where the model joins them.
    """
    from matplotlib.colors import LinearSegmentedColormap, Normalize

    from plumes2.ambient import AmbientProfileView
    from plumes2.nearfield.state import horizontal_unit

    frame = plot.frame
    case = plot.case
    length = units.length
    x = np.asarray(length(frame["x_m"].to_numpy(dtype=float)), dtype=float)
    y = np.asarray(length(frame["y_m"].to_numpy(dtype=float)), dtype=float)
    radius = np.asarray(length(frame["plume_diameter_m"].to_numpy(dtype=float)), dtype=float) / 2.0
    offsets, _axis = _port_offsets(case, length)
    n_ports = len(offsets)

    # The far field runs with the current at the depth the near field ended. A bare trace names
    # no current, so the plume's own final heading stands in and the notes say so.
    assumed_heading = case is None
    if case is not None:
        sample = AmbientProfileView(case.ambient).sample(float(frame["depth_m"].iloc[-1]))
        along = horizontal_unit(float(sample.current_direction))
    else:
        tail = max(len(x) - 5, 0)
        heading = np.array([x[-1] - x[tail], y[-1] - y[tail]])
        size = float(np.hypot(*heading))
        along = heading / size if size > 1e-12 else np.array([1.0, 0.0])
    across = np.array([-along[1], along[0]])

    def project(px: np.ndarray, py: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return px * along[0] + py * along[1], px * across[0] + py * across[1]

    distance = np.asarray(length(farfield["distance_m"].to_numpy(dtype=float)), dtype=float)
    width = np.asarray(length(farfield["width_m"].to_numpy(dtype=float)), dtype=float)
    dilution = farfield["dilution"].to_numpy(dtype=float)

    # The near field is placed so its end lands at the distance the far-field table quotes. The
    # table counts the near field's path from the diffuser (the exe's convention), the axis here
    # is the along-current projection; they agree exactly when the plume ran with the current, and
    # otherwise the near field sits `shift` downstream of the origin -- stated in the notes.
    end = offsets.mean(axis=0) + np.array([x[-1], y[-1]])
    end_s, end_t = project(np.array([end[0]]), np.array([end[1]]))
    shift = float(distance[0] - end_s[0])
    station_s = distance
    station_t = np.full_like(distance, float(end_t[0]))

    # Boundaries the case names, in display units, zero meaning "none".
    boundaries: list[tuple[str, float]] = []
    if case is not None:
        for label, metres in (
            ("acute", case.mixing_zone.acute_distance),
            ("chronic", case.mixing_zone.chronic_distance),
        ):
            if metres > 0.0:
                boundaries.append((label, float(length(metres))))
    # Drawn to a margin past the last boundary the far field reaches; the rest of the far field
    # is in its own panels. The whole far field when there is no boundary to stop at.
    reach = float(distance[-1])
    reached = [d for _, d in boundaries if distance[0] <= d <= distance[-1]]
    if reached and max(reached) * 1.15 < distance[-1]:
        reach = max(reached) * 1.15
    shown = distance <= reach
    if shown.sum() < 2:
        shown[:2] = True
    truncated = bool(reach < distance[-1])

    shown_s, shown_t, shown_w, shown_d = (a[shown] for a in (station_s, station_t, width, dilution))
    edge_low, edge_high = shown_t - shown_w / 2.0, shown_t + shown_w / 2.0

    # Sequential, one hue, the dark end the least diluted -- the wastefield fades toward the
    # receiving water downstream, never into the page where the discharge is.
    base = SERIES[0]
    near_fill = blend(base, INK_PRIMARY, 0.4)
    cmap = LinearSegmentedColormap.from_list(
        "plumes2 farfield dilution",
        [near_fill, base, blend(base, SURFACE, 0.5), blend(base, SURFACE, 0.85)],
    )
    low, high = float(shown_d.min()), float(shown_d.max())
    norm = Normalize(low, high if high > low else low * 1.01)

    # The near field, projected into this frame: each jet's footprint at its own port -- the part
    # of it that is in the water (the surface cuts the drawing, not the data).
    depth = np.asarray(length(frame["depth_m"].to_numpy(dtype=float)), dtype=float)
    _, x_shown, y_shown, r_shown = _cut_at_surface(depth, x, y, radius)
    if not len(x_shown):
        x_shown, y_shown, r_shown = x[:1], y[:1], radius[:1]
    outline = _plan_outline(x_shown, y_shown, r_shown)
    surfaced = _surface_note(frame, length)
    footprints = []
    for ox, oy in offsets:
        fs, ft = project(outline[:, 0] + ox, outline[:, 1] + oy)
        footprints.append((fs + shift, ft))
    port_s, port_t = project(offsets[:, 0], offsets[:, 1])
    port_s = port_s + shift

    boundary_marks: list[tuple[str, float, float]] = []  # label, distance, dilution there
    inside_nearfield: list[tuple[str, float]] = []
    beyond: list[tuple[str, float]] = []
    for label, d in boundaries:
        if d < distance[0]:
            inside_nearfield.append((label, d))
        elif d > distance[-1]:
            beyond.append((label, d))
        elif d <= reach:
            boundary_marks.append((label, d, float(np.interp(d, distance, dilution))))

    everything_s = np.concatenate([f[0] for f in footprints] + [shown_s])
    everything_t = np.concatenate([f[1] for f in footprints] + [edge_low, edge_high])
    s_span = float(np.ptp(everything_s)) or 1.0
    t_span = float(np.ptp(everything_t)) or 1.0
    plot_width = PANEL_WIDTH - 2.0  # the colour bar takes the rest
    natural = plot_width * t_span / s_span
    stretch = 1.0 if natural >= 1.7 else float(np.ceil(1.7 / natural))
    height = min(max(natural * stretch, 1.7), 3.6) + 1.0

    def draw(figure: FigureBase, axes: Axes) -> None:
        axes.set_axisbelow(True)
        mesh = axes.pcolormesh(
            np.vstack([shown_s, shown_s]),
            np.vstack([edge_low, edge_high]),
            np.vstack([shown_d, shown_d]),
            cmap=cmap, norm=norm, shading="gouraud", rasterized=True, zorder=2,
        )  # fmt: skip
        for edge in (edge_low, edge_high):
            axes.plot(shown_s, edge, color=INK_MUTED, linewidth=0.6, zorder=3)
        for fs, ft in footprints:
            axes.fill(fs, ft, color=near_fill, alpha=0.8, lw=0, zorder=2)
            axes.plot(fs, ft, color=INK_MUTED, linewidth=0.4, zorder=3)
        if n_ports > 1:
            axes.plot(
                port_s[[0, -1]], port_t[[0, -1]], color=INK_SECONDARY, linewidth=1.2, zorder=4,
                solid_capstyle="butt",
            )  # fmt: skip
        axes.plot(
            port_s, port_t, marker="o", markersize=2.5, color=SERIES[1], markeredgecolor=SURFACE,
            markeredgewidth=0.6, linestyle="none", zorder=5,
        )  # fmt: skip
        axes.annotate(
            "diffuser",
            xy=(float(port_s.mean()), float(port_t.min())),
            xytext=(0, -5),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=7.5,
            color=INK_SECONDARY,
        )
        # The hand-over: where the near field stops and Brooks starts, with what it starts from.
        axes.plot(
            [shown_s[0], shown_s[0]], [edge_low[0], edge_high[0]], color=INK_PRIMARY,
            linewidth=1.0, linestyle="--", zorder=4,
        )  # fmt: skip
        axes.annotate(
            f"near field ends: dilution {_short(float(shown_d[0]))}, "
            f"width {shown_w[0]:,.1f} {length.label}",
            xy=(float(shown_s[0]), float(edge_low[0])),
            xytext=(3, -4),
            textcoords="offset points",
            ha="left",
            va="top",
            fontsize=7.5,
            color=INK_SECONDARY,
            bbox=_BACKING,
        )
        _end_labels(axes, [(shown_s, edge_high, _short(float(shown_d[-1])), 0)])
        placed_at: list[float] = []
        for label, d, at_dilution in boundary_marks:
            # Two boundaries within a few percent of the axis print at different heights, and one
            # in the top-left corner starts below the current arrow that lives there.
            top = 0.96
            if (d - float(everything_s.min())) / s_span < 0.24:
                top = 0.80
            if any(abs(d - other) < 0.06 * s_span for other in placed_at):
                top -= 0.34
            placed_at.append(d)
            axes.axvline(d, color=AXIS, linewidth=0.8, linestyle=":", zorder=1)
            axes.annotate(
                f"{label} MZ, dilution {_short(at_dilution)}",
                xy=(d, top),
                xycoords=("data", "axes fraction"),
                xytext=(3, 0),
                textcoords="offset points",
                va="top",
                ha="left",
                fontsize=7.5,
                color=INK_MUTED,
                rotation=90,
                bbox=_BACKING,
            )
        # The current, top left: the one corner neither the band nor the footprints reach.
        axes.annotate(
            "",
            xy=(0.03, 0.94),
            xycoords="axes fraction",
            xytext=(26.0, 0.0),
            textcoords="offset points",
            arrowprops={"arrowstyle": "<-", "color": INK_SECONDARY, "linewidth": 1.0},
        )
        axes.annotate(
            "current",
            xy=(0.03, 0.94),
            xycoords="axes fraction",
            xytext=(30, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=7.5,
            color=INK_MUTED,
        )
        if stretch > 1.0:
            axes.annotate(
                f"across-current exaggeration \N{MULTIPLICATION SIGN}{stretch:g}",
                xy=(0.01, 0.02),
                xycoords="axes fraction",
                ha="left",
                va="bottom",
                fontsize=7,
                color=INK_MUTED,
            )
        axes.margins(x=0.03, y=0.18)
        axes.set_aspect(stretch, adjustable="box")
        axes.set_xlabel(_axis_label("distance from the diffuser, along the current", length.label))
        axes.set_ylabel(_axis_label("across the current", length.label))
        axes.set_title(
            "Top-down view, carried into the far field: the wastefield to the mixing zones"
        )
        bar = figure.colorbar(mesh, ax=axes, pad=0.03, fraction=0.05, aspect=18)
        bar.set_label("dilution (slab average across the wastefield)")
        bar.outline.set_edgecolor(AXIS)
        bar.outline.set_linewidth(0.8)

    drawing = Drawing(draw, height=height)

    columns = {
        "distance_m": f"distance ({length.label})",
        "width_m": f"width ({length.label})",
        "dilution": "dilution",
    }
    if "travel_time_hr" in farfield.columns:
        columns["travel_time_hr"] = "travel time (hr)"
    table = _scale(
        _table(farfield, columns), length, (f"distance ({length.label})", f"width ({length.label})")
    )

    notes = [
        "Brooks is one-dimensional: the band's width is the model's own statement of the "
        "wastefield's extent at each distance, and its shade is the slab average across it. The "
        "edges are where the model says the wastefield ends, not a concentration contour, and "
        "nothing is known about the distribution across the band.",
        "The near field is drawn as the plumes' footprints from the top-down panel, filled darker "
        "than any shade on the bar because everything in it is less dilute than the wastefield's "
        "first station; its own dilution is read in the panels above.",
        "The dashed line is the hand-over: the wastefield width the near field leaves -- the "
        "diffuser's span across the current plus one plume diameter -- is the width Brooks starts "
        "from, and the band grows from there under the eddy-diffusivity law.",
    ]
    if surfaced:
        notes.append(
            surfaced + " The band starts from the near-field end all the same, as the exe's far "
            "field does with the surface stop off."
        )
    if assumed_heading:
        notes.append(
            "A `.dat` names no current direction, so the band is laid along the plume's final "
            "heading. Report it with `--case-file` to lay it along the far-field current."
        )
    else:
        notes.append(
            "The band runs with the ambient current at the depth the near field ended, which is "
            "the current Brooks advects with. Where the near field's own path was not along the "
            "current, the band turns onto it at the hand-over -- the model's assumption, drawn."
        )
    if abs(shift) > 0.05:
        notes.append(
            f"The far-field table counts distance along the near field's path; here the near field "
            f"is projected onto the current and sits {shift:,.2f} {length.label} downstream of the "
            "origin so that its end lands at the distance the table quotes."
        )
    for label, d, at_dilution in boundary_marks:
        notes.append(
            f"The {label} mixing-zone boundary at {d:,.1f} {length.label} reads dilution "
            f"{at_dilution:,.0f} on the band."
        )
    for label, d in inside_nearfield:
        notes.append(
            f"The {label} boundary at {d:,.1f} {length.label} falls inside the near field, before "
            "the far field starts, so it is not on the band; read it in the near-field panels."
        )
    for label, d in beyond:
        notes.append(
            f"The {label} boundary at {d:,.1f} {length.label} lies past the end of the far field "
            f"({distance[-1]:,.0f} {length.label}), so the band does not reach it."
        )
    if truncated:
        notes.append(
            f"Drawn to {reach:,.0f} {length.label}, a margin past the last boundary; the far field "
            f"continues to {distance[-1]:,.0f} {length.label} (dilution {dilution[-1]:,.0f}) in "
            "the far-field panels below."
        )
    if stretch > 1.0:
        notes.append(
            f"The across-current axis is stretched {stretch:g}\N{MULTIPLICATION SIGN} so the band "
            "has visible width; the growth looks steeper than it is, and the factor is printed on "
            "the figure."
        )

    return Panel(
        key="plan-farfield",
        title="Top-down view: into the far field",
        explanation=(
            "The picture from above does not stop where the near field does. From the hand-over "
            "the wastefield is carried downstream by the current as a band the width the model "
            "gives it, spreading as eddy diffusion works on it and fading as it dilutes; the "
            "mixing-zone boundaries cross it at the distances the case names, with the dilution "
            "read off there. Read the band's width for the ground the wastefield covers at each "
            "distance, its shade for how dilute it is, and the dotted lines for what the "
            "regulatory boundaries see."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=tuple(notes),
    )


def _panel_elevation(plot: PlotFrame, units: UnitSystem) -> Panel:
    """Depth against downstream distance, with the plume's edges as well as its centre."""
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    centre = length(frame["depth_m"].to_numpy(dtype=float))
    radius = length(frame["plume_diameter_m"].to_numpy(dtype=float)) / 2.0
    # The surface plane cuts the body: rows after the centreline crosses the surface leave the
    # figure (they stay in the table), the band's edges are clamped to z = 0 and the centreline
    # stops on the plane.
    cut = _surface_crossing(centre)
    shown = slice(None) if cut is None else slice(0, max(cut, 1))
    top = np.maximum(centre[shown] - radius[shown], 0.0)
    bottom = np.maximum(centre[shown] + radius[shown], 0.0)
    line_z, line_d = _cut_at_surface(centre, distance)
    breached = bool(np.any(centre - radius < 0.0))
    crossed = cut is not None
    surfaced = _surface_note(frame, length)

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.fill_between(
            distance[shown],
            top,
            bottom,
            color=SERIES[0],
            alpha=FILL_ALPHA,
            linewidth=0,
            label="_nolegend_",
        )
        if len(line_d):
            axes.plot(line_d, line_z, color=SERIES[0], linewidth=1.6)
        if breached:
            axes.axhline(0.0, color=INK_SECONDARY, linewidth=1.0, zorder=3)
            axes.annotate(
                "surface", xy=(0.99, 0.0), xycoords=("axes fraction", "data"), xytext=(0, 3),
                textcoords="offset points", ha="right", va="bottom", fontsize=7.5,
                color=INK_SECONDARY,
            )  # fmt: skip
        if crossed and len(line_d):
            axes.plot(
                [line_d[-1]], [0.0], marker="x", markersize=6, color=INK_PRIMARY, linestyle="none",
                zorder=5,
            )  # fmt: skip
            axes.annotate(
                "centreline surfaces", xy=(line_d[-1], 0.0), xytext=(4, -4),
                textcoords="offset points", ha="left", va="top", fontsize=7.5,
                color=INK_SECONDARY,
            )  # fmt: skip
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("depth", length.label))
        axes.set_title("Side view: the centreline and the plume edges")
        axes.invert_yaxis()
        _mark_merge(axes, frame.iloc[shown], distance[shown])
        # One series, so no legend box -- the title says what is plotted.
        if len(line_d):
            _end_labels(axes, [(line_d, line_z, "centreline", 0)])

    drawing = Drawing(draw, height=3.2)
    merge_note = _merge_note(frame, distance)
    notes = [
        "The shaded band is the plume's own diameter, so its upper edge is what reaches the "
        "surface and its lower edge is what reaches the bed. The model tests contact against the "
        "edge, not the centreline, which is why a plume can surface while its centre is still "
        "well below.",
    ]
    if merge_note:
        notes.append(merge_note)
    if surfaced:
        notes.append(surfaced)

    table = _table(
        frame.assign(
            _d=_downstream(frame),
            _top=frame["depth_m"] - frame["plume_diameter_m"] / 2.0,
            _bottom=frame["depth_m"] + frame["plume_diameter_m"] / 2.0,
        ),
        {
            "_d": f"distance ({length.label})",
            "depth_m": f"centreline depth ({length.label})",
            "_top": f"upper edge ({length.label})",
            "_bottom": f"lower edge ({length.label})",
        },
    )
    return Panel(
        key="elevation",
        title="Side view",
        explanation=(
            "The same trajectory seen from the side, which is where the quantitative reading "
            "happens. The line is the centreline and the band around it is the plume's full "
            "vertical extent. Read off how far the plume rises, how wide it has become by then, "
            "and whether either edge reaches the surface or the seabed."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, tuple(table.columns)),
        notes=tuple(notes),
    )


def _panel_dilution(plot: PlotFrame, units: UnitSystem) -> Panel:
    """Flux-averaged and centreline dilution -- the pair a permit is argued over."""
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    average = frame["dilution"].to_numpy(dtype=float)

    columns = {"_d": f"distance ({length.label})", "dilution": "flux-averaged dilution"}
    centreline = (
        frame["centreline_dilution"].to_numpy(dtype=float)
        if "centreline_dilution" in frame.columns
        else None
    )
    if centreline is not None:
        columns["centreline_dilution"] = "centreline dilution"

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        _line(axes, distance, average, 0, "flux-average")
        ends = [(distance, average, _short(float(average[-1])), 0)]
        if centreline is not None:
            _line(axes, distance, centreline, 1, "centreline")
            ends.append((distance, centreline, _short(float(centreline[-1])), 1))
            _legend(axes, outside=False)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("dilution (parts ambient per part effluent)")
        axes.set_title("Dilution along the plume")
        _mark_merge(axes, frame, distance)
        # The legend names the series, so the end labels carry the values instead of repeating it.
        _end_labels(axes, ends)

    drawing = Drawing(draw)
    merge_note = _merge_note(frame, distance)
    notes = [
        "The two curves are not alternatives. The flux average is what the model integrates and "
        "what the far field starts from; the centreline is the least diluted water in the "
        "cross-section, and a mixing-zone limit is normally argued against that.",
        "Centreline dilution is pinned at 1 until the profile develops -- the zone of flow "
        "establishment. Where it leaves 1 is where that zone ends.",
    ]
    if merge_note:
        notes.append(merge_note)

    table = _table(frame.assign(_d=_downstream(frame)), columns)
    return Panel(
        key="dilution",
        title="Dilution",
        explanation=(
            "How much ambient water each part of effluent has mixed with, against distance from "
            "the diffuser. A dilution of 100 means one part discharge to ninety-nine parts "
            "receiving water. Read the endpoint as the near-field answer: it is the value the far "
            "field starts from, and the point past which no further mixing is credited to the jet."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=tuple(notes),
    )


def _panel_gradient(plot: PlotFrame, units: UnitSystem) -> Panel:
    """The cross-plume profile at three stations -- the panel that makes the volume readable."""
    frame = plot.frame
    length = units.length
    stations = np.unique(np.linspace(0, len(frame) - 1, 4).round().astype(int))[1:][:3]
    distance_si = _downstream(frame)
    offset = np.linspace(-1.0, 1.0, 201)
    weight = profile_weight(offset, plot.profile)

    # One station per row: its radius, its centreline dilution, and the excess concentration as
    # a fraction of the discharge -- 1/S on the centreline, tapering to zero at the edge. Plotting
    # dilution itself would run to infinity at the edge, where the excess has run out -- true,
    # and useless on an axis.
    picked = [
        (
            length(distance_si[index]),
            length(float(frame["plume_diameter_m"].iloc[index]) / 2.0),
            max(float(frame["centreline_dilution"].iloc[index]), 1e-12),
        )
        for index in stations
    ]
    rows = [
        {
            f"distance ({length.label})": at,
            f"plume radius ({length.label})": radius,
            "centreline dilution": centreline,
            "peak excess (fraction of discharge)": 1.0 / centreline,
        }
        for at, radius, centreline in picked
    ]

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        for slot, (at, radius, centreline) in enumerate(picked):
            _line(axes, offset * radius, weight / centreline, slot, f"{at:.0f} {length.label}")
        # All three curves land on zero at their own edges, so end labels would collide and
        # reading them would mean matching colours anyway. The legend is the honest channel.
        _legend(axes, outside=True, title="distance")
        axes.set_xlabel(_axis_label("offset from the centreline", length.label))
        axes.set_ylabel("excess concentration\n(fraction of the discharge)")
        axes.set_title("Across the plume: the gradient at three stations")

    drawing = Drawing(draw)
    return Panel(
        key="gradient",
        title="Across the plume",
        explanation=(
            "A plume is a volume, so one number per station understates the middle and overstates "
            "the edge. Each curve is a single cross-section: highest on the centreline, falling to "
            "zero at the edge, and wider further downstream. Read the width to see how far the "
            "influence extends laterally, and the height to see how concentrated the worst of it "
            "still is."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=pd.DataFrame(rows),
        notes=(
            "The shape is a parabola, and that is measured rather than assumed: it is the profile "
            "whose peak-to-mean ratio reproduces the model's own centreline exactly -- 2.0 for a "
            "round plume, and 1.5 once merging has confined it into a slab.",
            "Zero at the edge means zero *excess* over the ambient, not zero concentration. "
            "Salinity, temperature and alkalinity there are the receiving water's own.",
        ),
    )


def _panel_temperature(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length, degrees = units.length, units.temperature
    distance = length(_downstream(frame))
    temperature = degrees(frame["temperature_degC"].to_numpy(dtype=float))

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, temperature, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("plume temperature", degrees.label))
        axes.set_title("Temperature along the plume")
        _end_labels(axes, [(distance, temperature, f"{temperature[-1]:.1f}", 0)])

    drawing = Drawing(draw, height=3.0)
    table = _table(
        frame.assign(_d=_downstream(frame)),
        {
            "_d": f"distance ({length.label})",
            "temperature_degC": f"temperature ({degrees.label})",
            "salinity_psu": "salinity (psu)",
        },
    )
    table = _scale(table, length, (f"distance ({length.label})",))
    table = _scale(table, degrees, (f"temperature ({degrees.label})",))
    return Panel(
        key="temperature",
        title="Temperature",
        explanation=(
            "Temperature mixes conservatively, so this curve is the dilution curve in disguise and "
            "is here as a check on it: it must run monotonically from the discharge value toward "
            "the ambient at the depth the plume ends up at, with no excursion of its own. Salinity "
            "in the table behaves the same way."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=(
            "The ambient is stratified, so the value this approaches is the receiving water at "
            "the trapping depth, not at the port.",
        ),
    )


def _panel_ph(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    ph = frame["ph_total"].to_numpy(dtype=float)

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, ph, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("pH (total scale)")
        axes.set_title("pH along the plume")
        _mark_merge(axes, frame, distance)
        _end_labels(axes, [(distance, ph, f"{ph[-1]:.2f}", 0)])

    drawing = Drawing(draw, height=3.0)
    merge_note = _merge_note(frame, distance)
    notes = [
        "Total scale, which is what the model's default constant set reports on. The same water "
        "on the free or seawater scale is a different number.",
    ]
    if merge_note:
        notes.append(merge_note)

    table = _table(
        frame.assign(_d=_downstream(frame)),
        {
            "_d": f"distance ({length.label})",
            "dilution": "dilution",
            "ph_total": "pH (total scale)",
        },
    )
    return Panel(
        key="ph",
        title="pH",
        explanation=(
            "The quantity the carbonate module exists to predict. It starts at the discharge value "
            "and relaxes toward the receiving water as the plume entrains -- fast at first, "
            "because the first few metres do most of the mixing. Read the endpoint against "
            "whatever limit applies, and the steepness to see how quickly the excursion closes."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=tuple(notes),
    )


def _panel_saturation(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    wanted = [
        ("omega_aragonite", "aragonite"),
        ("omega_calcite", "calcite"),
        ("omega_brucite", "brucite"),
    ]
    present = [(column, name) for column, name in wanted if column in frame.columns]

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        ends = []
        for slot, (column, name) in enumerate(present):
            values = frame[column].to_numpy(dtype=float)
            _line(axes, distance, values, slot, name)
            ends.append((distance, values, _short(float(values[-1])), slot))
        # Log because brucite and the carbonates sit decades apart. One axis, not two.
        axes.set_yscale("log")
        axes.axhline(1.0, color=AXIS, linewidth=0.8, zorder=0, label="_nolegend_")
        axes.annotate(
            "saturation",
            xy=(0.02, 1.0),
            xycoords=("axes fraction", "data"),
            xytext=(0, 3),
            textcoords="offset points",
            fontsize=8,
            color=INK_MUTED,
        )
        _legend(axes, outside=True)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("saturation state")
        axes.set_title("Mineral saturation states")
        _end_labels(axes, ends)

    drawing = Drawing(draw)
    table = _table(
        frame.assign(_d=_downstream(frame)),
        {"_d": f"distance ({length.label})", **dict(present)},
    )
    return Panel(
        key="saturation",
        title="Saturation states",
        explanation=(
            "Whether the plume water is capable of precipitating each mineral. Above the "
            "saturation line the water is supersaturated and precipitation is thermodynamically "
            "possible; below it, dissolution is. The scale is logarithmic because brucite and the "
            "carbonate minerals sit decades apart, which is itself the reading that matters: a "
            "brucite excursion is short-lived, while the carbonates stay supersaturated "
            "throughout."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=(
            "Supersaturation is a possibility, not a rate. Whether anything precipitates depends "
            "on kinetics and on nucleation sites the model does not carry.",
            "Brucite is an upper bound: it is computed without ion pairing, which would lower the "
            "free magnesium and hydroxide activities and so lower the ratio. It is also the one "
            "quantity here with no reference implementation to check against, because the "
            "original model cannot report it at all. Read it as a trend.",
        ),
    )


def _panel_carbonate(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    wanted = [
        ("total_alkalinity_umol_kg", "alkalinity"),
        ("dic_umol_kg", "DIC"),
        ("bicarbonate_umol_kg", "bicarbonate"),
        ("carbonate_umol_kg", "carbonate"),
    ]
    present = [(column, name) for column, name in wanted if column in frame.columns]

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        ends = []
        for slot, (column, name) in enumerate(present):
            values = frame[column].to_numpy(dtype=float)
            _line(axes, distance, values, slot, name)
            ends.append((distance, values, _short(float(values[-1])), slot))
        _legend(axes, outside=True)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("concentration (\N{MICRO SIGN}mol/kg)")
        axes.set_title("The carbonate system")
        _end_labels(axes, ends)

    drawing = Drawing(draw)
    table = _table(
        frame.assign(_d=_downstream(frame)),
        {"_d": f"distance ({length.label})", **dict(present)},
    )
    return Panel(
        key="carbonate",
        title="The carbonate system",
        explanation=(
            "Alkalinity and dissolved inorganic carbon are the two the model actually transports: "
            "they mix conservatively, so they follow the dilution curve and nothing else. "
            "Bicarbonate and carbonate are re-solved from that pair at every step, which is why "
            "they do not simply track it -- the speciation shifts as pH falls toward the ambient. "
            "All four share one axis because they share one unit."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=(
            "Alkalinity and DIC are conservative under mixing; the speciation is not. That "
            "difference is the whole reason the two pairs of curves have different shapes.",
        ),
    )


def _panel_pco2(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    pco2 = frame["pco2_uatm"].to_numpy(dtype=float)

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, pco2, color=SERIES[0], linewidth=1.6)
        axes.set_yscale("log")
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("pCO\N{SUBSCRIPT TWO} (\N{MICRO SIGN}atm)")
        axes.set_title("Carbon dioxide partial pressure")
        _end_labels(axes, [(distance, pco2, _short(float(pco2[-1])), 0)])

    drawing = Drawing(draw, height=3.0)
    table = _table(
        frame.assign(_d=_downstream(frame)),
        {"_d": f"distance ({length.label})", "pco2_uatm": "pCO2 (\N{MICRO SIGN}atm)"},
    )
    return Panel(
        key="pco2",
        title="pCO\N{SUBSCRIPT TWO}",
        explanation=(
            "The partial pressure of CO\N{SUBSCRIPT TWO} the plume water would equilibrate with, "
            "which is what decides whether it takes up carbon from the atmosphere or gives it "
            "off. An alkalinity-elevated discharge starts far below atmospheric -- the excursion "
            "spans orders of magnitude, hence the logarithmic scale -- and climbs back toward the "
            "receiving water as it mixes."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=(
            "A partial pressure, not a flux. Turning it into uptake needs a gas-transfer velocity "
            "and a residence time at the surface, neither of which the near field carries -- and "
            "the plume is submerged for most of this trajectory in any case.",
        ),
    )


def _panel_oxygen(plot: PlotFrame, units: UnitSystem) -> Panel:
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    oxygen = frame["dissolved_oxygen_mg_l"].to_numpy(dtype=float)

    def draw(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, oxygen, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("dissolved oxygen (mg/L)")
        axes.set_title("Dissolved oxygen along the plume")
        _mark_merge(axes, frame, distance)
        _end_labels(axes, [(distance, oxygen, _short(float(oxygen[-1])), 0)])

    drawing = Drawing(draw, height=3.0)
    merge_note = _merge_note(frame, distance)
    notes = [
        "⚠️ This curve is **not** a simple mixing line, and that is the physics rather than a "
        "numerical artefact. The plume carries the oxygen of the water it actually entrained "
        "along its path, so where it rises through a stratified column the value reflects the "
        "depths it came from, not the depth it is at. The 1994 reference calls this forced "
        "upwelling: a plume leaving an oxygen-poor basin arrives near the surface still carrying "
        "the deep water's oxygen.",
        "Biochemical demand is absent here by design. Over the minutes an initial dilution takes, "
        "a per-day decay constant does nothing measurable -- confirmed by two archived runs that "
        "swap the carbonaceous and nitrogenous loads and produce byte-identical output. BOD acts "
        "on the far field.",
    ]
    if merge_note:
        notes.append(merge_note)

    table = _table(
        frame.assign(_d=_downstream(frame)),
        {
            "_d": f"distance ({length.label})",
            "dilution": "dilution",
            "dissolved_oxygen_mg_l": "DO (mg/L)",
        },
    )
    return Panel(
        key="oxygen",
        title="Dissolved oxygen",
        explanation=(
            "Oxygen in the plume, against distance from the diffuser. It starts at the discharge "
            "value less any immediate demand and climbs toward the receiving water as the plume "
            "entrains. Read the minimum rather than the endpoint: a DO standard is a floor, so the "
            "worst value along the path is the one that matters, and it is not always at the start."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=tuple(notes),
    )


def _panel_farfield(units: UnitSystem, farfield: pd.DataFrame) -> list[Panel]:
    """Two panels, not one with two axes: dilution and width do not share a unit."""
    length = units.length
    distance = length(farfield["distance_m"].to_numpy(dtype=float))
    panels = []

    dilution = farfield["dilution"].to_numpy(dtype=float)

    def draw_dilution(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, dilution, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("total dilution")
        axes.set_title("Far field: dilution downstream")
        _end_labels(axes, [(distance, dilution, _short(float(dilution[-1])), 0)])

    drawing_dilution = Drawing(draw_dilution, height=3.0)
    table = _table(
        farfield,
        {
            "distance_m": f"distance ({length.label})",
            "dilution": "total dilution",
            "dilution_factor": "Brooks factor",
            "travel_time_hr": "travel time (hr)",
        },
    )
    panels.append(
        Panel(
            key="farfield-dilution",
            title="Far field: dilution",
            explanation=(
                "Once the plume stops rising it spreads and mixes horizontally, which the Brooks "
                "model treats as a one-dimensional problem in distance downstream. The curve "
                "starts at the near-field answer -- so the two join at that value -- and grows "
                "much more slowly. Read the value at whatever distance the mixing zone is defined "
                "at."
            ),
            svg=drawing_dilution.svg(),
            drawing=drawing_dilution,
            table=_scale(table, length, (f"distance ({length.label})",)),
            notes=(
                "Distance is measured from the diffuser, which is what a mixing-zone limit is "
                "written against. The Brooks equations themselves count from where the near field "
                "ended, which is why the factor column is 1 at the first row.",
                "The far field has its own current speed, taken separately from the near-field "
                "one. They differ across real cases, and using the wrong one rescales everything "
                "downstream.",
            ),
        )
    )

    width = length(farfield["width_m"].to_numpy(dtype=float))

    def draw_width(figure: FigureBase, axes: Axes) -> None:
        del figure
        axes.plot(distance, width, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("wastefield width", length.label))
        axes.set_title("Far field: wastefield width")
        _end_labels(axes, [(distance, width, _short(float(width[-1])), 0)])

    drawing_width = Drawing(draw_width, height=2.6)
    table = _table(
        farfield,
        {"distance_m": f"distance ({length.label})", "width_m": f"width ({length.label})"},
    )
    panels.append(
        Panel(
            key="farfield-width",
            title="Far field: width",
            explanation=(
                "How wide the wastefield has spread at each distance. It is drawn separately from "
                "the dilution rather than sharing its axes, because the two have different units "
                "and putting them on one plot would suggest a relationship whose apparent "
                "strength is only a choice of scale."
            ),
            svg=drawing_width.svg(),
            drawing=drawing_width,
            table=_scale(table, length, tuple(table.columns)),
            notes=(),
        )
    )
    return panels


def build_panels(
    plot: PlotFrame,
    *,
    units: UnitSystem = SI,
    farfield: pd.DataFrame | None = None,
) -> list[Panel]:
    """Every panel the data supports, in reading order.

    A panel whose columns are absent is **skipped**, not emitted empty: an exe `.dat` may carry
    five columns or thirteen, and a blank axis reads as "zero" where the truth is "never printed".
    """
    have = set(plot.frame.columns)
    panels: list[Panel] = []

    # The receiving water first: every result below is conditional on it. Imported here for the
    # same reason as the gradient panels -- the module imports this one's helpers.
    from plumes2.report.ambient import build_ambient_panels

    panels.extend(build_ambient_panels(plot, units=units))
    if {"x_m", "y_m", "depth_m", "plume_diameter_m"} <= have:
        panels.append(_panel_trajectory_3d(plot, units))
        panels.append(_panel_elevation(plot, units))
        panels.append(_panel_plan_view(plot, units))
        if (
            farfield is not None
            and len(farfield)
            and {"distance_m", "width_m", "dilution"} <= set(farfield.columns)
        ):
            panels.append(_panel_plan_farfield(plot, units, farfield))
    if {"dilution", "x_m", "y_m"} <= have:
        panels.append(_panel_dilution(plot, units))
    if {"centreline_dilution", "plume_diameter_m", "x_m", "y_m"} <= have:
        panels.append(_panel_gradient(plot, units))
    if {"temperature_degC", "salinity_psu", "x_m", "y_m"} <= have:
        panels.append(_panel_temperature(plot, units))
    if {"ph_total", "x_m", "y_m"} <= have:
        panels.append(_panel_ph(plot, units))
    if {"omega_aragonite", "omega_calcite"} & have and {"x_m", "y_m"} <= have:
        panels.append(_panel_saturation(plot, units))
    # The centreline-and-spread panels, when the frame carries a case to re-solve across the
    # section (a run, or a `.dat` with its case). A bare trace returns none of these and keeps the
    # flux-averaged panels above. Imported here rather than at module top: `chemistry_gradient`
    # imports this module's helpers, so a top-level import each way would be a cycle.
    from plumes2.report.chemistry_gradient import build_chemistry_gradient_panels

    panels.extend(build_chemistry_gradient_panels(plot, units=units, farfield=farfield))
    if {"total_alkalinity_umol_kg", "x_m", "y_m"} <= have:
        panels.append(_panel_carbonate(plot, units))
    if {"pco2_uatm", "x_m", "y_m"} <= have:
        panels.append(_panel_pco2(plot, units))
    if {"dissolved_oxygen_mg_l", "x_m", "y_m"} <= have:
        panels.append(_panel_oxygen(plot, units))
    if farfield is not None and len(farfield):
        panels.extend(_panel_farfield(units, farfield))
    return panels


# ------------------------------------------------------------------- several runs, one set of axes

#: What an overlay can draw, as `(column, title, y-axis label, log y, x variable)`. Each becomes
#: one panel with one line per run -- never two quantities on one plot, whatever the temptation.
#: The geometry is drawn against distance; the chemistry against **dilution on a log axis**, the
#: variable it is a function of -- against distance every change sits in the first few
#: centimetres and four effluents are four spikes at the origin.
_OVERLAY: tuple[tuple[str, str, str, bool, str], ...] = (
    ("dilution", "Dilution", "dilution (parts ambient per part effluent)", False, "distance"),
    ("centreline_dilution", "Centreline dilution", "centreline dilution", False, "distance"),
    ("depth_m", "Centreline depth", "depth", False, "distance"),
    ("plume_diameter_m", "Plume diameter", "diameter", False, "distance"),
    ("ph_total", "pH", "pH (total scale)", False, "dilution"),
    (
        "omega_calcite",
        "Calcite saturation",
        "saturation state \N{GREEK CAPITAL LETTER OMEGA}",
        True,
        "dilution",
    ),
    (
        "omega_aragonite",
        "Aragonite saturation",
        "saturation state \N{GREEK CAPITAL LETTER OMEGA}",
        True,
        "dilution",
    ),
    (
        "omega_brucite",
        "Brucite saturation",
        "saturation state \N{GREEK CAPITAL LETTER OMEGA}",
        True,
        "dilution",
    ),
)

#: Runs an overlay can carry. The palette has four categorical slots and generating a fifth is the
#: one thing the standard forbids outright, because a generated hue is indistinguishable from an
#: existing one under colour-vision deficiency.
MAX_OVERLAY_RUNS = len(SERIES)


class TooManyRunsError(ValueError):
    """Raised when an overlay is asked to carry more runs than there are palette slots.

    Refusing rather than cycling colours: two runs sharing a hue is a figure that lies about which
    line is which, and folding runs into an "Other" bucket -- the usual answer for too many
    categories -- makes no sense when each category is a whole configuration.
    """


def build_overlay_panels(
    frames: list[tuple[str, pd.DataFrame]], *, units: UnitSystem = SI
) -> list[Panel]:
    """One panel per shared quantity, with one line per run and a legend naming what differs.

    `frames` is `(label, frame)` per run, and the labels come from `Comparison.labels()` -- derived
    from a diff of the resolved cases rather than typed, so a legend cannot disagree with its data.

    A quantity is only drawn when **every** run has it: a panel where one line is missing invites
    the reader to conclude that run was zero, when the truth is that it had no chemistry.

    ⚠️ **The runs do not share a distance grid.** They terminate at different points, so each line
    simply ends where its own run did -- no interpolation onto a common axis, and the differing
    line lengths are information rather than an artefact.
    """
    if len(frames) > MAX_OVERLAY_RUNS:
        raise TooManyRunsError(
            f"{len(frames)} runs is more than the {MAX_OVERLAY_RUNS} palette slots an overlay can "
            "tell apart. Split the comparison, or report the runs separately."
        )
    length = units.length
    shared = set.intersection(*(set(frame.columns) for _, frame in frames))
    panels: list[Panel] = []

    for column, title, y_label, log, against in _OVERLAY:
        if column not in shared or not {"x_m", "y_m", "dilution"} <= shared:
            continue
        is_length = column.endswith("_m")
        label = _axis_label(y_label, length.label) if is_length else y_label
        by_dilution = against == "dilution"
        series: list[tuple[str, np.ndarray, np.ndarray]] = []
        for name, frame in frames:
            values = frame[column].to_numpy(dtype=float)
            if is_length:
                values = length(values)
            if by_dilution:
                x = frame["dilution"].to_numpy(dtype=float)
            else:
                x = length(_downstream(frame))
            series.append((name, x, values))
        rows = {name: [float(values[-1]), float(x[-1])] for name, x, values in series}
        at_label = "at dilution" if by_dilution else f"at distance ({length.label})"

        def draw(
            figure: FigureBase,
            axes: Axes,
            *,
            series: list[tuple[str, np.ndarray, np.ndarray]] = series,
            label: str = label,
            title: str = title,
            log: bool = log,
            column: str = column,
            by_dilution: bool = by_dilution,
        ) -> None:
            # Bound as defaults rather than closed over: the loop rebinds every one of these on
            # its next pass, and a closure drawn later would show the last quantity on every panel.
            del figure
            ends = []
            any_cut = False
            for slot, (name, x, values) in enumerate(series):
                if column == "depth_m":
                    # The surface cuts the drawing: a centreline is drawn while it is in the
                    # water and stops on the plane. The table keeps the run's own end.
                    any_cut = any_cut or bool(np.any(values < 0.0))
                    values, x = _cut_at_surface(values, x)
                keep = np.isfinite(values) & (values > 0.0 if log else np.ones_like(values, bool))
                _line(axes, x[keep], values[keep], slot, name)
                if keep.any():
                    ends.append((x[keep], values[keep], _short(float(values[keep][-1])), slot))
            if column == "depth_m" and any_cut:
                axes.axhline(0.0, color=INK_SECONDARY, linewidth=1.0, zorder=3)
                axes.annotate(
                    "surface", xy=(0.99, 0.0), xycoords=("axes fraction", "data"), xytext=(0, 3),
                    textcoords="offset points", ha="right", va="bottom", fontsize=7.5,
                    color=INK_SECONDARY,
                )  # fmt: skip
            if log:
                axes.set_yscale("log")
            if column.startswith("omega_"):
                axes.axhline(1.0, color=AXIS, linewidth=0.8, zorder=1)
            _legend(axes, outside=True, title="run")
            if by_dilution:
                axes.set_xscale("log")
                axes.set_xlabel("flux-averaged dilution (log)")
            else:
                axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
            axes.set_ylabel(label)
            axes.set_title(f"{title}: {len(series)} configurations")
            if column == "depth_m":
                axes.invert_yaxis()
            _end_labels(axes, ends)

        drawing = Drawing(draw)
        surfacing = [
            name for name, _x, values in series if column == "depth_m" and np.any(values < 0.0)
        ]
        panels.append(
            Panel(
                key=f"overlay-{column.replace('_', '-')}",
                title=f"{title} compared",
                explanation=(
                    f"{title} for each configuration, on one set of axes. The legend names what "
                    "actually differs between the runs -- it is derived from a comparison of the "
                    "resolved cases, not written by hand, so it cannot drift out of step with the "
                    "lines. Each line ends where its own run ended, which is why they stop at "
                    + (
                        "different dilutions. Drawn against flux-averaged dilution on a log axis: "
                        "the chemistry is a function of dilution, and against distance every "
                        "change would sit in the first few centimetres."
                        if by_dilution
                        else "different distances."
                    )
                ),
                svg=drawing.svg(),
                drawing=drawing,
                table=pd.DataFrame(
                    [
                        {
                            "run": name,
                            f"final {y_label}": final,
                            at_label: at,
                        }
                        for name, (final, at) in rows.items()
                    ]
                ),
                notes=(
                    "Colour follows position in the comparison, not rank, so a run keeps its "
                    "colour across every panel here.",
                ),
            )
        )
        if surfacing:
            panels[-1] = dataclasses.replace(
                panels[-1],
                notes=(
                    *panels[-1].notes,
                    "The surface cuts the drawing: "
                    + ", ".join(surfacing)
                    + (" reaches" if len(surfacing) == 1 else " reach")
                    + " the surface with the surface stop off, so each of those lines stops on the "
                    "plane where its centreline crosses; the rows above it are the model's "
                    "continuation, kept in the run's own table.",
                ),
            )

    return panels
