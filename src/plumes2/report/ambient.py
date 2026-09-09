"""The receiving water, for reference: the ambient profiles the run was integrated against.

Two panels at the head of the report, before any result, because every number after them is
conditional on these inputs: the hydrography and current (temperature, salinity, density, the
near- and far-field currents, their direction) and, when the case carries it, the carbonate
chemistry (TA and DIC as entered; pH and the saturation states solved from them).

Each is a row of **small multiples sharing one depth axis** -- depth down the page, the value
across -- rather than several quantities on shared axes, which is the house rule against dual
axes applied to profiles: five quantities in five units are five panels with one common depth.
The rows the case entered are marked; the line between them is what the model interpolates. The
port, the seabed, the depth the plume trapped at and the stretch below the profile's last row
are all drawn, so the reader sees the profile *and* where the plume sat in it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

from plumes2.ambient import AmbientProfileView
from plumes2.chem.constants import resolve_constants, solubility_brucite
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.display import DisplayUnit, UnitSystem
from plumes2.report.palette import AXIS, GRID, INK_MUTED, INK_PRIMARY, INK_SECONDARY, SERIES
from plumes2.report.panels import Drawing, Panel, _axis_label, _table

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes
    from matplotlib.figure import FigureBase

    from plumes2.config import Case
    from plumes2.plotframe import PlotFrame

__all__ = ["build_ambient_panels"]


def _column(values: np.ndarray, depths: np.ndarray, label: str, *, log: bool = False) -> dict:
    return {"values": [values], "depths": depths, "label": label, "log": log, "names": [None]}


def _series_column(
    series: list[tuple[np.ndarray, str]], depths: np.ndarray, label: str, *, log: bool = False
) -> dict:
    return {
        "values": [values for values, _ in series],
        "depths": depths,
        "label": label,
        "log": log,
        "names": [name for _, name in series],
    }


def _marks(case: Case, plot: PlotFrame, length: DisplayUnit) -> dict[str, float]:
    """The depths worth a line across every column, in display units."""
    marks = {"port": float(length(case.diffuser.port_depth))}
    marks["seabed"] = float(length(case.diffuser.bottom_depth))
    if "depth_m" in plot.frame.columns and len(plot.frame):
        marks["plume traps"] = float(length(float(plot.frame["depth_m"].iloc[-1])))
    return marks


def _profile_drawing(
    columns: list[dict],
    marks: dict[str, float],
    *,
    extrapolated_from: float | None,
    bottom: float,
    depth_label: str,
) -> Drawing:
    """A row of small multiples on one inverted depth axis."""

    def draw(figure: FigureBase, axes: Axes) -> None:
        # The axes the renderer made become the host: invisible, its area split into columns.
        axes.set_axis_off()
        axes.patch.set_visible(False)
        spec = axes.get_subplotspec()
        assert spec is not None
        grid = spec.subgridspec(1, len(columns), wspace=0.12)
        first: Axes | None = None
        subs: list[Axes] = []
        for index, column in enumerate(columns):
            sub = figure.add_subplot(grid[0, index], sharey=first)
            first = first or sub
            subs.append(sub)
            depths = column["depths"]
            for slot, (values, name) in enumerate(
                zip(column["values"], column["names"], strict=True)
            ):
                sub.plot(
                    values, depths, color=SERIES[slot], linewidth=1.4, marker="o", markersize=3.2,
                    markeredgecolor="white", markeredgewidth=0.6, label=name, zorder=4,
                )  # fmt: skip
                if name is not None:
                    # Direct label at the deepest row, inside the frame; a second series stacks
                    # below the first so coincident lines still read as two.
                    sub.annotate(
                        name,
                        xy=(float(values[-1]), float(depths[-1])),
                        xytext=(4, -3 - 9 * slot),
                        textcoords="offset points",
                        ha="left",
                        va="top",
                        fontsize=7,
                        color=SERIES[slot],
                    )
            if column["log"]:
                sub.set_xscale("log")
            else:
                sub.xaxis.set_major_locator(MaxNLocator(3))
            sub.margins(x=0.2)
            sub.set_xlabel(column["label"], fontsize=8)
            if extrapolated_from is not None and bottom > extrapolated_from:
                sub.axhspan(extrapolated_from, bottom, color=GRID, alpha=0.6, lw=0, zorder=1)
            for name, depth in marks.items():
                style = {"seabed": (INK_PRIMARY, "-", 1.0), "port": (INK_SECONDARY, "--", 0.8)}.get(
                    name, (INK_SECONDARY, ":", 0.9)
                )
                sub.axhline(depth, color=style[0], linestyle=style[1], linewidth=style[2], zorder=3)
            if index:
                sub.tick_params(labelleft=False)
        assert first is not None
        first.set_ylabel(depth_label)
        first.set_ylim(bottom * 1.04, -0.02 * bottom)
        last = subs[-1]
        # Marks within a few percent of the axis print at different offsets, not on each other.
        placed: list[float] = []
        for name, depth in sorted(marks.items(), key=lambda item: item[1]):
            nudge = -8.0 * sum(1 for other in placed if abs(depth - other) < 0.05 * bottom)
            placed.append(depth)
            last.annotate(
                name,
                xy=(1.0, depth),
                xycoords=("axes fraction", "data"),
                xytext=(3, nudge),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=7,
                color=INK_MUTED,
                annotation_clip=False,
            )
        if extrapolated_from is not None and bottom > extrapolated_from:
            last.annotate(
                "below the profile",
                xy=(1.0, 0.5 * (extrapolated_from + bottom)),
                xycoords=("axes fraction", "data"),
                xytext=(3, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=7,
                color=AXIS,
                annotation_clip=False,
            )

    return Drawing(draw, height=3.2)


def _hydrography_panel(plot: PlotFrame, case: Case, units: UnitSystem) -> Panel:
    length, temperature, speed = units.length, units.temperature, units.speed
    levels = case.ambient.levels
    depth_si = np.array([level.depth for level in levels], dtype=float)
    depths = np.asarray(length(depth_si), dtype=float)
    view = AmbientProfileView(case.ambient, equation_of_state=case.near_field.equation_of_state)
    frame = pd.DataFrame(
        {
            "depth": depths,
            "temperature": np.asarray(
                temperature(np.array([level.temperature for level in levels])), dtype=float
            ),
            "salinity": np.array([level.salinity for level in levels], dtype=float),
            "density": np.asarray(view.density(depth_si), dtype=float),
            "current_speed": np.asarray(
                speed(np.array([level.current_speed for level in levels])), dtype=float
            ),
            "farfield_speed": np.asarray(
                speed(np.array([level.farfield_speed for level in levels])), dtype=float
            ),
            "current_direction": np.array([level.current_direction for level in levels]),
            "farfield_direction": np.array([level.farfield_direction for level in levels]),
        }
    )
    columns = [
        _column(
            frame["temperature"].to_numpy(), depths, _axis_label("temperature", temperature.label)
        ),
        _column(frame["salinity"].to_numpy(), depths, "salinity (psu)"),
        _column(frame["density"].to_numpy(), depths, "density (kg/m\N{SUPERSCRIPT THREE})"),
        _series_column(
            [
                (frame["current_speed"].to_numpy(), "near field"),
                (frame["farfield_speed"].to_numpy(), "far field"),
            ],
            depths,
            _axis_label("current", speed.label),
        ),
        _series_column(
            [
                (frame["current_direction"].to_numpy(), "near field"),
                (frame["farfield_direction"].to_numpy(), "far field"),
            ],
            depths,
            "direction (\N{DEGREE SIGN} from +x)",
        ),
    ]
    marks = _marks(case, plot, length)
    bottom = max([marks["seabed"], float(depths.max()), *marks.values()])
    last_row = float(depths.max())
    extrapolated = last_row if marks["seabed"] > last_row else None
    drawing = _profile_drawing(
        columns,
        marks,
        extrapolated_from=extrapolated,
        bottom=bottom,
        depth_label=_axis_label("depth", length.label),
    )

    table = _table(
        frame,
        {
            "depth": f"depth ({length.label})",
            "temperature": f"temperature ({temperature.label})",
            "salinity": "salinity (psu)",
            "density": "density (kg/m\N{SUPERSCRIPT THREE})",
            "current_speed": f"current ({speed.label})",
            "current_direction": "direction (\N{DEGREE SIGN})",
            "farfield_speed": f"far-field current ({speed.label})",
            "farfield_direction": "far-field direction (\N{DEGREE SIGN})",
        },
        rows=max(len(frame), 1),
    )
    notes = [
        "The dots are the rows the case entered; between them the model interpolates linearly, "
        "and the density is the model's own, under the case's equation of state "
        f"({case.near_field.equation_of_state.name}), at one atmosphere.",
        "The near field and the far field take separate currents -- Brooks advects with the "
        "far-field one at the depth the plume trapped -- so both are drawn, and they coincide "
        "when the case enters the same value for each.",
        "Directions are the model's frame: degrees counter-clockwise from +x (the PLUMES "
        "manual's convention), not compass bearings.",
    ]
    if extrapolated is not None:
        notes.append(
            f"The profile stops at {last_row:,.1f} {length.label} and the seabed is at "
            f"{marks['seabed']:,.1f} {length.label}; the shaded band is where the model extends "
            "the profile past its last row (the run's GeometryWarning)."
        )
    return Panel(
        key="ambient-profile",
        title="Receiving water: hydrography and current",
        explanation=(
            "The water the plume was integrated into, as the case entered it: temperature, "
            "salinity and the density they give, then the current the near field is bent by and "
            "the one the far field is carried by, with their directions. Depth runs down the page "
            "as it does in the side views; the port, the seabed and the depth the plume trapped at "
            "are drawn across every column so the profile can be read against where the plume "
            "actually sat. Every result later in the report is conditional on these rows."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=tuple(notes),
    )


def _chemistry_panel(plot: PlotFrame, case: Case, units: UnitSystem) -> Panel:
    length = units.length
    rows = case.ambient.chemistry
    depth_si = np.array([row.depth for row in rows], dtype=float)
    depths = np.asarray(length(depth_si), dtype=float)
    alkalinity = np.array([row.total_alkalinity for row in rows], dtype=float)
    dic = np.array([row.dic for row in rows], dtype=float)
    view = AmbientProfileView(case.ambient)
    salinity = view.salinity(depth_si)
    temperature = view.temperature(depth_si)
    constants = resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option)
    state = solve_from_alkalinity_dic(
        alkalinity, dic, salinity, temperature, constants=constants, context="ambient chemistry"
    )
    brucite = state.omega_brucite(solubility_brucite(salinity, temperature))
    frame = pd.DataFrame(
        {
            "depth": depths,
            "total_alkalinity": alkalinity,
            "dic": dic,
            "ph_total": np.asarray(state.ph_total, dtype=float),
            "omega_aragonite": np.asarray(state.omega_aragonite, dtype=float),
            "omega_brucite": np.asarray(brucite, dtype=float),
        }
    )
    columns = [
        _column(alkalinity, depths, "total alkalinity (\N{MICRO SIGN}mol/kg)"),
        _column(dic, depths, "DIC (\N{MICRO SIGN}mol/kg)"),
        _column(frame["ph_total"].to_numpy(), depths, "pH (total)"),
        _series_column(
            [
                (frame["omega_aragonite"].to_numpy(), "aragonite"),
                (frame["omega_brucite"].to_numpy(), "brucite"),
            ],
            depths,
            "saturation state \N{GREEK CAPITAL LETTER OMEGA}",
            log=True,
        ),
    ]
    table_columns = {
        "depth": f"depth ({length.label})",
        "total_alkalinity": "TA (\N{MICRO SIGN}mol/kg)",
        "dic": "DIC (\N{MICRO SIGN}mol/kg)",
        "ph_total": "pH (total)",
        "omega_aragonite": "\N{GREEK CAPITAL LETTER OMEGA} aragonite",
        "omega_brucite": "\N{GREEK CAPITAL LETTER OMEGA} brucite",
    }
    if case.ambient.dissolved_oxygen:
        oxygen = case.ambient.dissolved_oxygen
        oxygen_depths = np.asarray(length(np.array([row.depth for row in oxygen])), dtype=float)
        oxygen_values = np.array([row.dissolved_oxygen for row in oxygen], dtype=float)
        columns.append(_column(oxygen_values, oxygen_depths, "dissolved oxygen (mg/L)"))

    marks = _marks(case, plot, length)
    bottom = max([marks["seabed"], float(depths.max()), *marks.values()])
    last_row = float(depths.max())
    extrapolated = last_row if marks["seabed"] > last_row else None
    drawing = _profile_drawing(
        columns,
        marks,
        extrapolated_from=extrapolated,
        bottom=bottom,
        depth_label=_axis_label("depth", length.label),
    )
    table = _table(frame, table_columns, rows=max(len(frame), 1))

    uniform = bool(np.ptp(alkalinity) == 0.0 and np.ptp(dic) == 0.0)
    notes = [
        "Total alkalinity and DIC are the rows the case entered; pH and the saturation states "
        "are not inputs -- they are solved here from that pair at each row's salinity and "
        "temperature, with the case's constants (K1K2 option "
        f"{case.carbonate.k1k2_option}, KSO4 option {case.carbonate.kso4_option}).",
        "\N{GREEK CAPITAL LETTER OMEGA} brucite is the upper bound the rest of the report carries "
        "(no ion pairing); \N{GREEK CAPITAL LETTER OMEGA} = 1 is the saturation line, and the "
        "\N{GREEK CAPITAL LETTER OMEGA} axis is logarithmic because the two states sit decades "
        "apart.",
    ]
    if uniform:
        notes.append(
            f"The chemistry is entered uniform in depth: TA {alkalinity[0]:,.0f} and DIC "
            f"{dic[0]:,.0f} \N{MICRO SIGN}mol/kg on every row, so only the salinity and "
            "temperature move the derived quantities."
        )
    if extrapolated is not None:
        notes.append(
            f"The chemistry rows stop at {last_row:,.1f} {length.label}; below that the model "
            "holds the last row to the seabed (the shaded band)."
        )
    return Panel(
        key="ambient-chemistry",
        title="Receiving water: carbonate chemistry",
        explanation=(
            "The receiving water's carbonate system, for reference against every pH and "
            "saturation state the plume panels show: the total alkalinity and DIC the case "
            "entered at each depth, and the pH, aragonite and brucite saturation the model solves "
            "from them. The plume's chemistry panels fade to these values at their edges, and the "
            "mixing-zone rows are read against them, so a change here moves everything downstream."
        ),
        svg=drawing.svg(),
        drawing=drawing,
        table=table,
        notes=tuple(notes),
    )


def build_ambient_panels(plot: PlotFrame, *, units: UnitSystem) -> list[Panel]:
    """The receiving-water panels, or none for a frame with no case behind it.

    A bare `.dat` echoes its ambient table, but the `PlotFrame` built from it carries no case
    unless the caller supplied one, and it is the case -- with its equation of state and
    constants -- that these panels are drawn from.
    """
    case = plot.case
    if case is None or not case.ambient.levels:
        return []
    panels = [_hydrography_panel(plot, case, units)]
    if case.ambient.has_chemistry:
        panels.append(_chemistry_panel(plot, case, units))
    return panels
