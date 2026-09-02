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

import io
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
    INK_SECONDARY,
    SERIES,
    SURFACE,
    matplotlib_style,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterator

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from plumes2.plotframe import PlotFrame

__all__ = [
    "MAX_OVERLAY_RUNS",
    "TABLE_ROWS",
    "Panel",
    "TooManyRunsError",
    "build_overlay_panels",
    "build_panels",
    "figure_to_svg",
]

#: Rows in a panel's table. Enough to read the shape off, few enough to scan; both endpoints are
#: always among them, and the run's CSV carries every row at full precision.
TABLE_ROWS = 12


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


def figure_to_svg(figure: Figure) -> str:
    """Serialise a figure to an inline SVG fragment, dropping the XML preamble.

    The `<?xml?>` declaration and DOCTYPE are illegal mid-document, so they are stripped and the
    `<svg>` element handed back for direct embedding. No base64 and no separate files: the report
    stays one thing you can email.
    """
    buffer = io.StringIO()
    figure.savefig(buffer, format="svg", bbox_inches="tight")
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


@contextmanager
def _panel_figure(width: float = 7.2, height: float = 3.4) -> Iterator[tuple[Figure, Axes]]:
    """A styled figure, with the style held open until the SVG has been written.

    ⚠️ **The context has to cover the whole panel, not just `subplots`.** Some rcParams are read
    when the axes are created (`axes.grid`, `figure.facecolor`) but others are read much later --
    `legend.frameon` when `legend()` is called, `savefig.facecolor` when the figure is serialised.
    An earlier revision closed the context straight after `subplots`, and the result was every
    legend drawing matplotlib's default framed white box, which then covered the data it was
    labelling. Nothing about the code looked wrong; the figures did.
    """
    with _styled():
        figure, axes = plt.subplots(figsize=(width, height))
        yield figure, axes


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
    axes.figure.canvas.draw()  # limits must be final before y is converted to axes fractions
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


def _mark_merge(axes: Axes, frame: pd.DataFrame, distance: np.ndarray) -> str | None:
    """A hairline where merging begins, and the sentence that explains it.

    Worth marking on every panel drawn against distance: the entrainment terms and the
    concentration profile both change there, so a kink in the curve is physics rather than noise.
    """
    if "merged" not in frame.columns:
        return None
    merged = frame["merged"].to_numpy(dtype=bool)
    if not merged.any() or merged.all():
        return None
    at = float(distance[int(np.argmax(merged))])
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
    return (
        "The hairline marks where neighbouring plumes meet. Past it each plume entrains over "
        "less of its surface and the cross-plume profile flattens, so the curve changing slope "
        "there is the model rather than a numerical artefact."
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


def _widen_degenerate_axes(axes: Axes, *series: np.ndarray) -> None:
    """Give a flat axis a readable window instead of a floating-point one.

    A plume discharged due north has an east coordinate of a few times 1e-16, and matplotlib
    responds by labelling the axis `1e-16` with an offset -- which invites the reader to believe
    something happens in that direction. Widening the axis to a small fraction of the largest real
    span makes it read as flat, which is what it is.
    """
    spans = [float(np.ptp(values)) for values in series]
    scale = max(spans) if max(spans) > 0.0 else 1.0
    setters = (axes.set_xlim, axes.set_ylim, axes.set_zlim)  # type: ignore[attr-defined]
    for values, span, setter in zip(series, spans, setters, strict=True):
        if span >= 1e-6 * scale:
            continue
        centre = float(np.mean(values))
        margin = 0.05 * scale
        setter(centre - margin, centre + margin)


# --------------------------------------------------------------------------- the panels


def _panel_trajectory_3d(plot: PlotFrame, units: UnitSystem) -> Panel:
    """The plume in space, with the diffuser at the origin."""
    frame = plot.frame
    length = units.length
    x = length(frame["x_m"].to_numpy(dtype=float))
    y = length(frame["y_m"].to_numpy(dtype=float))
    depth = length(frame["depth_m"].to_numpy(dtype=float))

    with _styled():
        figure = plt.figure(figsize=(7.2, 4.6))
        axes = figure.add_subplot(projection="3d")
        axes.plot(x, y, depth, color=SERIES[0], linewidth=1.6, zorder=3)
        axes.scatter([0.0], [0.0], [depth[0]], color=SERIES[1], s=28, zorder=5, depthshade=False)
        axes.text(0.0, 0.0, depth[0], "  diffuser", fontsize=8, color=INK_SECONDARY)
        axes.scatter(
            [x[-1]], [y[-1]], [depth[-1]], color=SERIES[0], s=22, zorder=5, depthshade=False
        )
        axes.text(x[-1], y[-1], depth[-1], "  end of near field", fontsize=8, color=INK_SECONDARY)

        axes.set_xlabel(_axis_label("east of the diffuser", length.label))
        axes.set_ylabel(_axis_label("north of the diffuser", length.label))
        axes.set_zlabel(_axis_label("depth", length.label))
        _widen_degenerate_axes(axes, x, y, depth)
        axes.invert_zaxis()  # down is down
        axes.view_init(elev=22, azim=-58)
        axes.set_box_aspect((1.6, 1.0, 0.9))
        for pane in (axes.xaxis, axes.yaxis, axes.zaxis):
            pane.pane.set_facecolor(SURFACE)
            pane.pane.set_alpha(1.0)
            pane.pane.set_edgecolor(GRID)
        svg = figure_to_svg(figure)

    table = _table(
        frame.assign(_d=_downstream(frame)),
        {
            "_d": f"distance ({length.label})",
            "x_m": f"east ({length.label})",
            "y_m": f"north ({length.label})",
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
            "still buoyant, and levels off when it stops being so. This panel is for orientation "
            "-- which way the plume travels and how far -- and the panels below carry every "
            "number, including how wide it becomes."
        ),
        svg=svg,
        table=_scale(table, length, tuple(table.columns)),
        notes=(
            "Depth increases downward, matching how a water column is usually drawn. The exe's "
            "own `Depth` column is negative-down under the same name; this report has flipped it.",
            "The three axes are not equally scaled -- a plume is metres across and often tens of "
            "metres long, so an equal-scale box would collapse into a sliver. That is why only the "
            "centreline is drawn here: a plume outline on unequal axes would state a width it does "
            "not have. The side view and the table below give the real extent.",
        ),
    )


def _panel_elevation(plot: PlotFrame, units: UnitSystem) -> Panel:
    """Depth against downstream distance, with the plume's edges as well as its centre."""
    frame = plot.frame
    length = units.length
    distance = length(_downstream(frame))
    centre = length(frame["depth_m"].to_numpy(dtype=float))
    radius = length(frame["plume_diameter_m"].to_numpy(dtype=float)) / 2.0

    with _panel_figure(height=3.2) as (figure, axes):
        axes.fill_between(
            distance,
            centre - radius,
            centre + radius,
            color=SERIES[0],
            alpha=FILL_ALPHA,
            linewidth=0,
            label="_nolegend_",
        )
        axes.plot(distance, centre, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("depth", length.label))
        axes.set_title("Side view: the centreline and the plume edges")
        axes.invert_yaxis()
        merge_note = _mark_merge(axes, frame, distance)
        # One series, so no legend box -- the title says what is plotted.
        _end_labels(axes, [(distance, centre, "centreline", 0)])
        svg = figure_to_svg(figure)

    notes = [
        "The shaded band is the plume's own diameter, so its upper edge is what reaches the "
        "surface and its lower edge is what reaches the bed. The model tests contact against the "
        "edge, not the centreline, which is why a plume can surface while its centre is still "
        "well below.",
    ]
    if merge_note:
        notes.append(merge_note)

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
        svg=svg,
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
    with _panel_figure() as (figure, axes):
        _line(axes, distance, average, 0, "flux-average")
        ends = [(distance, average, _short(float(average[-1])), 0)]
        if "centreline_dilution" in frame.columns:
            centreline = frame["centreline_dilution"].to_numpy(dtype=float)
            _line(axes, distance, centreline, 1, "centreline")
            ends.append((distance, centreline, _short(float(centreline[-1])), 1))
            _legend(axes, outside=False)
            columns["centreline_dilution"] = "centreline dilution"
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("dilution (parts ambient per part effluent)")
        axes.set_title("Dilution along the plume")
        merge_note = _mark_merge(axes, frame, distance)
        # The legend names the series, so the end labels carry the values instead of repeating it.
        _end_labels(axes, ends)
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    rows = []
    with _panel_figure() as (figure, axes):
        for slot, index in enumerate(stations):
            radius_si = float(frame["plume_diameter_m"].iloc[index]) / 2.0
            centreline = max(float(frame["centreline_dilution"].iloc[index]), 1e-12)
            # Excess concentration as a fraction of the discharge: 1/S on the centreline,
            # tapering to zero at the edge. Plotting dilution itself would run to infinity at the
            # edge, where the excess has run out -- true, and useless on an axis.
            label = f"{length(distance_si[index]):.0f} {length.label}"
            _line(axes, length(offset * radius_si), weight / centreline, slot, label)
            rows.append(
                {
                    f"distance ({length.label})": length(distance_si[index]),
                    f"plume radius ({length.label})": length(radius_si),
                    "centreline dilution": centreline,
                    "peak excess (fraction of discharge)": 1.0 / centreline,
                }
            )
        # All three curves land on zero at their own edges, so end labels would collide and
        # reading them would mean matching colours anyway. The legend is the honest channel.
        _legend(axes, outside=True, title="distance")
        axes.set_xlabel(_axis_label("offset from the centreline", length.label))
        axes.set_ylabel("excess concentration\n(fraction of the discharge)")
        axes.set_title("Across the plume: the gradient at three stations")
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure(height=3.0) as (figure, axes):
        axes.plot(distance, temperature, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("plume temperature", degrees.label))
        axes.set_title("Temperature along the plume")
        _end_labels(axes, [(distance, temperature, f"{temperature[-1]:.1f}", 0)])
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure(height=3.0) as (figure, axes):
        axes.plot(distance, ph, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("pH (total scale)")
        axes.set_title("pH along the plume")
        merge_note = _mark_merge(axes, frame, distance)
        _end_labels(axes, [(distance, ph, f"{ph[-1]:.2f}", 0)])
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure() as (figure, axes):
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
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure() as (figure, axes):
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
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure(height=3.0) as (figure, axes):
        axes.plot(distance, pco2, color=SERIES[0], linewidth=1.6)
        axes.set_yscale("log")
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("pCO\N{SUBSCRIPT TWO} (\N{MICRO SIGN}atm)")
        axes.set_title("Carbon dioxide partial pressure")
        _end_labels(axes, [(distance, pco2, _short(float(pco2[-1])), 0)])
        svg = figure_to_svg(figure)

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
        svg=svg,
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

    with _panel_figure(height=3.0) as (figure, axes):
        axes.plot(distance, oxygen, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("dissolved oxygen (mg/L)")
        axes.set_title("Dissolved oxygen along the plume")
        merge_note = _mark_merge(axes, frame, distance)
        _end_labels(axes, [(distance, oxygen, _short(float(oxygen[-1])), 0)])
        svg = figure_to_svg(figure)

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
        svg=svg,
        table=_scale(table, length, (f"distance ({length.label})",)),
        notes=tuple(notes),
    )


def _panel_farfield(units: UnitSystem, farfield: pd.DataFrame) -> list[Panel]:
    """Two panels, not one with two axes: dilution and width do not share a unit."""
    length = units.length
    distance = length(farfield["distance_m"].to_numpy(dtype=float))
    panels = []

    dilution = farfield["dilution"].to_numpy(dtype=float)
    with _panel_figure(height=3.0) as (figure, axes):
        axes.plot(distance, dilution, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel("total dilution")
        axes.set_title("Far field: dilution downstream")
        _end_labels(axes, [(distance, dilution, _short(float(dilution[-1])), 0)])
        svg_dilution = figure_to_svg(figure)
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
            svg=svg_dilution,
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
    with _panel_figure(height=2.6) as (figure, axes):
        axes.plot(distance, width, color=SERIES[0], linewidth=1.6)
        axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
        axes.set_ylabel(_axis_label("wastefield width", length.label))
        axes.set_title("Far field: wastefield width")
        _end_labels(axes, [(distance, width, _short(float(width[-1])), 0)])
        svg_width = figure_to_svg(figure)
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
            svg=svg_width,
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

    if {"x_m", "y_m", "depth_m", "plume_diameter_m"} <= have:
        panels.append(_panel_trajectory_3d(plot, units))
        panels.append(_panel_elevation(plot, units))
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

#: What an overlay can draw, as `(column, title, y-axis label, log scale)`. Each becomes one panel
#: with one line per run -- never two quantities on one plot, whatever the temptation.
_OVERLAY: tuple[tuple[str, str, str, bool], ...] = (
    ("dilution", "Dilution", "dilution (parts ambient per part effluent)", False),
    ("centreline_dilution", "Centreline dilution", "centreline dilution", False),
    ("depth_m", "Centreline depth", "depth", False),
    ("plume_diameter_m", "Plume diameter", "diameter", False),
    ("ph_total", "pH", "pH (total scale)", False),
    ("omega_brucite", "Brucite saturation", "saturation state", True),
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

    for column, title, y_label, log in _OVERLAY:
        if column not in shared or not {"x_m", "y_m"} <= shared:
            continue
        is_length = column.endswith("_m")
        label = _axis_label(y_label, length.label) if is_length else y_label
        rows: dict[str, list[float]] = {}
        with _panel_figure() as (figure, axes):
            ends = []
            for slot, (name, frame) in enumerate(frames):
                distance = length(_downstream(frame))
                values = frame[column].to_numpy(dtype=float)
                if is_length:
                    values = length(values)
                _line(axes, distance, values, slot, name)
                ends.append((distance, values, _short(float(values[-1])), slot))
                rows[name] = [float(values[-1]), float(distance[-1])]
            if log:
                axes.set_yscale("log")
            _legend(axes, outside=True, title="run")
            axes.set_xlabel(_axis_label("distance from the diffuser", length.label))
            axes.set_ylabel(label)
            axes.set_title(f"{title}: {len(frames)} configurations")
            if column == "depth_m":
                axes.invert_yaxis()
            _end_labels(axes, ends)
            svg = figure_to_svg(figure)

        panels.append(
            Panel(
                key=f"overlay-{column.replace('_', '-')}",
                title=f"{title} compared",
                explanation=(
                    f"{title} for each configuration, on one set of axes. The legend names what "
                    "actually differs between the runs -- it is derived from a comparison of the "
                    "resolved cases, not written by hand, so it cannot drift out of step with the "
                    "lines. Each line ends where its own run ended, which is why they stop at "
                    "different distances."
                ),
                svg=svg,
                table=pd.DataFrame(
                    [
                        {
                            "run": name,
                            f"final {y_label}": final,
                            f"at distance ({length.label})": at,
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
    return panels
