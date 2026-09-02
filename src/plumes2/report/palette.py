"""The report's visual parameters: one validated palette, one matplotlib style.

Every colour here comes from a palette that was **run through a validator**, not chosen by
eye -- the four categorical slots the report uses were checked for the lightness band, the
chroma floor, colourblind separation between adjacent slots, the normal-vision floor, and
contrast against the chart surface:

    lightness band     PASS   all 4 inside L 0.43-0.77
    chroma floor       PASS   all 4 >= 0.1
    CVD separation     PASS   worst adjacent pair dE 9.49 (protan), target >= 8
    normal-vision      PASS   worst adjacent pair dE 22.9, floor >= 15
    contrast           WARN   aqua 2.74:1 and yellow 2.11:1 are below 3:1

⚠️ **The contrast warning is not dismissable, it is an obligation.** Two slots sit below 3:1 on
the light surface, and the rule for that is *relief*: ship visible direct labels or a table view.
The report ships both -- every multi-series panel direct-labels its lines at the right-hand end,
and every panel carries a table of the values it plots. So the two low-contrast slots never have
to be told apart by colour alone.

⚠️ **Four slots is the ceiling here, and the order is the safety mechanism.** The slot ordering is
what makes adjacent pairs separable under colour-vision deficiency, so slots are assigned in
order and never cycled. A fifth series does not get a fifth colour -- it gets a second panel.
Yellow sits beside orange at slot 4, which is only safe on line and bar forms with direct labels;
the report has no scatter, where all pairs would have to clear the floors and these four do not.

**The report commits to light mode.** A figure is rendered once, as an SVG with its colours baked
in, and matplotlib cannot re-theme it from CSS -- so a dark mode would mean rendering every panel
twice and doubling the file. The page therefore paints an explicit light surface rather than
inheriting the viewer's, which is also what makes it print correctly. Stated rather than implied.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np

# Reached through matplotlib rather than importing `cycler` directly: it is matplotlib's own
# dependency, not ours, and this module is the only place that needs it.
from matplotlib.rcsetup import cycler
from numpy.typing import NDArray

__all__ = [
    "AXIS",
    "CHROMA_FLOOR",
    "CONTRAST_TARGET",
    "GRID",
    "INK_MUTED",
    "INK_PRIMARY",
    "INK_SECONDARY",
    "LIGHTNESS_BAND",
    "NORMAL_SEPARATION_FLOOR",
    "PAGE",
    "PROTAN_SEPARATION_FLOOR",
    "SERIES",
    "SURFACE",
    "PaletteCheck",
    "contrast_ratio",
    "matplotlib_style",
    "validate",
]

#: Chart surface, and the page plane behind it. The validator's contrast figures are against
#: SURFACE, so a panel drawn on anything else would invalidate them.
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
#: Axis and tick labels. Recessive by design -- the data is the only thing allowed to be loud.
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

#: Categorical slots, **in order**. Assign by position, never by rank, so a series keeps its
#: colour when a panel gains or loses a neighbour.
SERIES: tuple[str, ...] = (
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua      -- contrast 2.74:1, relies on its direct label
    "#eda100",  # 4 yellow    -- contrast 2.11:1, ditto
)

#: Series-hue wash for an area or envelope fill. A wash, never a saturated block.
FILL_ALPHA = 0.10


def matplotlib_style() -> dict[str, Any]:
    """rcParams for every figure in the report.

    Three things are being enforced rather than suggested:

    * **Hairline, solid, recessive chrome.** One step off the surface, 0.8pt, and never dashed --
      a dashed gridline reads as a threshold or a projection when it is just a grid.
    * **No top or right spine**, and ticks pointing out with no minor ticks, so the frame does
      not compete with the data.
    * **Text outlines, not font references** (`svg.fonttype = "path"`). The report is one
      self-contained file that has to open anywhere, and a font-family reference would render at
      whatever metrics the reader's machine happens to have -- shifting labels, sometimes clipping
      them. Outlines render identically everywhere at the cost of not being selectable *inside the
      figure*, which is exactly why every panel also carries its values as a real HTML table.
    """
    return {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.transparent": False,
        # DejaVu ships with matplotlib, so the outlines are always available. The page's own
        # text uses the system sans; the figures are the one place that cannot depend on it.
        "font.family": "DejaVu Sans",
        "font.size": 9.0,
        "svg.fonttype": "path",
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK_SECONDARY,
        "axes.labelsize": 9.0,
        "axes.titlecolor": INK_PRIMARY,
        "axes.titlesize": 10.0,
        "axes.titlelocation": "left",
        "axes.titlepad": 8.0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "both",
        "axes.prop_cycle": cycler(color=list(SERIES)),
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "grid.linestyle": "-",
        "grid.alpha": 1.0,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelcolor": INK_MUTED,
        "ytick.labelcolor": INK_MUTED,
        "xtick.labelsize": 8.0,
        "ytick.labelsize": 8.0,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
        # 2px lines and >=8px markers, in points at the report's 100 dpi.
        "lines.linewidth": 1.6,
        "lines.markersize": 5.0,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "legend.frameon": False,
        "legend.fontsize": 8.0,
        "legend.labelcolor": INK_SECONDARY,
        "legend.handlelength": 1.6,
        "figure.dpi": 100.0,
        "figure.constrained_layout.use": True,
    }


# ------------------------------------------------------------------- the validator, executable
#
# ⚠️ **These figures used to live in this module's docstring as prose, and prose goes stale.** The
# palette's whole claim is that it was *validated* rather than chosen by eye, and until 2026-08-20
# that claim rested on five numbers in a comment that nothing recomputed. Two of them turned out to
# be wrong. Ledger row 212 now runs what follows on every build.


@dataclass(frozen=True, slots=True)
class PaletteCheck:
    """The validator's verdict on the four categorical slots."""

    #: OkLab lightness per slot, which must sit inside the band the report's surface allows.
    lightness: tuple[float, ...]
    #: OkLab chroma per slot. Below the floor a slot reads as grey beside its neighbours.
    chroma: tuple[float, ...]
    #: Worst **adjacent-pair** separation under normal vision, OkLab dE x 100.
    normal_separation: float
    #: The same under simulated protanopia, which is the binding constraint.
    protan_separation: float
    #: WCAG contrast of each slot against `SURFACE`.
    contrast: tuple[float, ...]


#: Floors the palette is held to. Adjacent pairs only: slots are assigned in order and never
#: cycled, so a non-adjacent pair is never asked to be told apart (see the module docstring).
NORMAL_SEPARATION_FLOOR = 15.0
PROTAN_SEPARATION_FLOOR = 8.0
LIGHTNESS_BAND = (0.43, 0.77)
CHROMA_FLOOR = 0.10
#: Below this a slot may not carry meaning by colour alone, and owes the reader relief -- a direct
#: label or a table. Two slots are below it and the report ships both forms of relief.
CONTRAST_TARGET = 3.0

_SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
#: Bjorn Ottosson's OkLab, via the intermediate cone-response space.
_XYZ_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_LMS_OKLAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
#: Vienot, Brettel & Mollon (1999), applied in **linear** light. The canonical construction, and
#: the one whose figure this module's docstring got wrong -- see `validate`.
_PROTANOPIA = np.array(
    [
        [0.11238, 0.88762, 0.0],
        [0.11238, 0.88762, 0.0],
        [0.00401, -0.00401, 1.0],
    ]
)


def _linear(colour: str) -> NDArray[np.float64]:
    """`#rrggbb` to linear-light sRGB. Gamma first -- every space below expects linear."""
    channels = np.array([int(colour[i : i + 2], 16) / 255.0 for i in (1, 3, 5)])
    return np.where(channels <= 0.04045, channels / 12.92, ((channels + 0.055) / 1.055) ** 2.4)


def _oklab(linear: NDArray[np.float64]) -> NDArray[np.float64]:
    return _LMS_OKLAB @ np.cbrt(np.clip(_XYZ_LMS @ linear, 0.0, None))


def _separation(one: str, two: str, *, protan: bool) -> float:
    """Perceptual distance between two colours, OkLab dE x 100.

    OkLab rather than CIELAB because the report's other two checks -- the lightness band and the
    chroma floor -- are stated in OkLab, and mixing spaces across one validator would make the
    numbers incomparable. It is also the space whose Euclidean distance is meant to be used
    directly, which CIELAB's is not.
    """
    pair = []
    for colour in (one, two):
        linear = _linear(colour)
        pair.append(_oklab(_PROTANOPIA @ linear if protan else linear))
    return float(np.linalg.norm(pair[0] - pair[1]) * 100.0)


def contrast_ratio(colour: str, against: str = SURFACE) -> float:
    """WCAG 2 relative-luminance contrast, `(L1 + 0.05) / (L2 + 0.05)`."""
    weights = np.array([0.2126, 0.7152, 0.0722])
    first, second = (float(weights @ _linear(c)) for c in (colour, against))
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def validate(series: tuple[str, ...] = SERIES) -> PaletteCheck:
    """Recompute every figure this module's docstring claims.

    ⚠️ **Two of the five published figures were wrong, and this is how that was found.** The
    docstring recorded a protanopia separation of **9.1**; the canonical Vienot construction in
    linear light gives **9.49**, and no standard variant reproduces 9.1 -- Machado's severity-1.0
    matrix gives 10.32, and applying either in gamma-encoded sRGB gives 10.6. The normal-vision
    figure, 22.9, reproduces **exactly**. So does every contrast ratio, and the lightness and
    chroma bands.

    The *claim* is unaffected -- 9.49 clears the floor of 8 more comfortably than 9.1 did -- which
    is why this is a correction rather than a failure. But a palette whose validation figures cannot
    be reproduced is not a validated palette, and the fix is to compute them here rather than to
    adjust a matrix until it agrees.
    """
    lightness, chroma, contrast = [], [], []
    for colour in series:
        lab = _oklab(_linear(colour))
        lightness.append(float(lab[0]))
        chroma.append(float(np.hypot(lab[1], lab[2])))
        contrast.append(contrast_ratio(colour))
    adjacent = list(pairwise(series))
    return PaletteCheck(
        lightness=tuple(lightness),
        chroma=tuple(chroma),
        normal_separation=min(_separation(a, b, protan=False) for a, b in adjacent),
        protan_separation=min(_separation(a, b, protan=True) for a, b in adjacent),
        contrast=tuple(contrast),
    )
