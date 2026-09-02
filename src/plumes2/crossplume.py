"""The cross-plume concentration profile, and the centreline dilution it implies.

A plume is a volume, not a line. The solver carries **flux-averaged** quantities -- one
dilution for the whole element -- but a mixing-zone limit is usually quoted against the worst
place in the cross-section, and a figure that draws the plume as a line throws away the thing a
reader most wants to see. Both need the shape of the profile across the plume.

**The exe offers three profiles, and its default is parabolic.** Both halves are measured
(case48, 2026-08-25). The peak-to-mean ratio of a shape `phi(u)`, `u = r/b`, at uniform velocity
is the reciprocal of its area-average, and the exe prints both `Dilutn` (flux-averaged) and
`CL-Dil` (centreline), so their ratio *is* the peak-to-mean, directly readable off every trace:

| `SimilarityProfile` | shape | round | slab | exe option (measured plateau) |
|---|---|---|---|---|
| **`PARABOLIC`** | `1 - u^2` | **2.0000** | **1.5000** | `Default Profile` (**2.00000**) |
| `THREE_HALVES` | `[1 - u^1.5]^2` | 3.8889 (= 35/9) | 2.2222 | `3/2 Power law` (**3.88997**) |
| `EXE_GAUSSIAN` | `exp(-k u^2)`, `k` ~ 3.57 | 3.6700 | 2.148 | `Gaussian Profile` (**3.66998**) |
| `GAUSSIAN` | `exp(-2 u^2)` | 2.3130 | 1.6718 | -- (the jet-and-plume literature's) |

The default option is what every other archived trace was run under: exactly **2.0000** while
the plume is round -- 8 617 rows, zero exceptions -- and exactly **1.5000** once deeply merged.
The 3/2 option is the profile the 1994 reference derives its 3.89 from, so the exe ships its
manual's profile and *defaults away from it*.

⚠️⚠️ **The exe's Gaussian is not the literature's Gaussian.** `exp(-2 u^2)` is the Gaussian whose
top-hat-equivalent radius is `b` (`b = sqrt(2) b_gauss`), and truncated at the printed edge it
puts the centreline 2.31x the mean. The exe's `Gaussian Profile` puts it **3.67x** -- a Gaussian
whose `1/e` radius is `b / 1.9`, i.e. one that reads the printed diameter as the ~2.8 % visible
edge rather than the top-hat width. Same shape, different meaning of `b`, and a 59 % difference
in the centreline. Adopting one is not adopting the other (PLAN 8.4).

⭐ **The round ratio alone cannot tell a parabola from a Gaussian; the slab ratio can.** An
*untruncated* `exp(-2 u^2)` integrates to a peak-to-mean of exactly **2.0** over the plane --
the same as the parabola -- so row 198's 8 617 round rows are consistent with either. What
identifies the parabola is the merged limit: **1.5000** measured, where the Gaussian gives
1.672 truncated or 1.596 untruncated.

**Between the two limits the exe interpolates linearly**, not geometrically -- see `peak_to_mean`.
That law is measured under the default profile only; for the other three the same blend is
applied between their own two anchors and is an *assumption* (case48's geometry never merges).

⚠️ **Dilution and concentration run opposite ways.** The peak *concentration* is 2x the mean, so
the centreline *dilution* is the mean divided by 2. Everything here is phrased as a
concentration ratio and `centreline_dilution` does the inversion once.
"""

from __future__ import annotations

import math
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "EXE_GAUSSIAN_K",
    "EXE_GAUSSIAN_PEAK_TO_MEAN",
    "MERGED_DIAMETERS",
    "PEAK_TO_MEAN_ROUND",
    "PEAK_TO_MEAN_SLAB",
    "SimilarityProfile",
    "centreline_dilution",
    "exact_peak_to_mean",
    "parabolic_weight",
    "peak_to_mean",
    "peak_to_mean_round",
    "peak_to_mean_slab",
    "profile_weight",
]


class SimilarityProfile(StrEnum):
    """Which cross-plume shape the centreline is read through. **`PARABOLIC` is the default.**

    It is the exe's own default and the profile every archived comparison rests on (row 198), so
    it is the parity path -- the way `EquationOfState.EOS80` and `ExeBuild.CURRENT` are. The other
    three are there so the port can match a trace made under the exe's other two options, and so
    the literature's Gaussian is one setting away. ✅ PLAN 8.4 was decided 2026-08-26 (operator):
    the study quotes the parabola, and the setting stays per case so any option can be selected
    as a user needs, the way the exe's own selector allows. None of them changes
    the integration: the profile is layered on the flux-averaged solution after the fact, exactly
    as the exe does (case48's three traces share one `Dilutn` column).
    """

    #: `1 - u^2`. The exe's `Default Profile`; peak-to-mean 2.0 round, 1.5 slab.
    PARABOLIC = "parabolic"
    #: `[1 - u^1.5]^2`. The exe's `3/2 Power law Profile` and the 3rd edition's own; 35/9 round.
    THREE_HALVES = "three_halves"
    #: `exp(-k u^2)` with `k` solved from case48's plateau (3.66998). The exe's `Gaussian
    #: Profile`. ⚠️ Not the literature's Gaussian -- see the module docstring.
    EXE_GAUSSIAN = "exe_gaussian"
    #: `exp(-2 u^2)`, truncated at the edge: the top-hat-equivalent Gaussian of the jet-and-plume
    #: literature. No exe option produces it.
    GAUSSIAN = "gaussian"


#: Peak-to-mean concentration of `1 - u^2` over a circle: `1 / integral(1 - u^2) = 2`.
PEAK_TO_MEAN_ROUND = 2.0

#: The same parabola across a slab of half-width `b`, which is what a fully merged element
#: becomes: `1 / (1 - 1/3) = 1.5`.
PEAK_TO_MEAN_SLAB = 1.5

#: Diameters of nominal port spacing over which the exe walks from round to slab. Merging
#: starts when the plume is one spacing wide and the transition is complete at two.
MERGED_DIAMETERS = 2.0

#: The developed `Dilutn / CL-Dil` plateau of case48's `style_gaussian.dat`, mean over its 252
#: rows with `Dilutn > 5` (spread 3.66882-3.67129). Ledger row 278 re-measures it from the trace;
#: this constant is what the port reproduces it *with*.
EXE_GAUSSIAN_PEAK_TO_MEAN = 3.66998

#: The literature Gaussian's exponent: `exp(-2 u^2)` is `exp(-r^2 / b_g^2)` with `b = sqrt(2) b_g`.
_LITERATURE_GAUSSIAN_K = 2.0


def _gaussian_round(k: float) -> float:
    """Peak-to-mean of `exp(-k u^2)` over the unit disc: `1 / integral_0^1 2u e^{-ku^2} du`."""
    return k / (1.0 - math.exp(-k))


def _gaussian_slab(k: float) -> float:
    """Peak-to-mean of `exp(-k u^2)` across the unit slab: `1 / integral_0^1 e^{-ku^2} du`."""
    root = math.sqrt(k)
    return 2.0 * root / (math.sqrt(math.pi) * math.erf(root))


def _gaussian_k_for(peak_to_mean_round: float) -> float:
    """Solve `k / (1 - e^-k) = ratio` for `k` by Newton's method.

    The map is monotone (it is 1 at `k -> 0` and ~`k` for large `k`), so the iteration from any
    positive start converges; a dozen steps take it to machine precision.
    """
    if peak_to_mean_round <= 1.0:
        raise ValueError("a truncated Gaussian's peak-to-mean over the disc exceeds 1")
    k = peak_to_mean_round
    for _ in range(50):
        e = math.exp(-k)
        f = k / (1.0 - e) - peak_to_mean_round
        df = ((1.0 - e) - k * e) / (1.0 - e) ** 2
        step = f / df
        k -= step
        if abs(step) < 1e-14:
            break
    return k


#: The exponent of the exe's Gaussian, `exp(-k u^2)`, derived from `EXE_GAUSSIAN_PEAK_TO_MEAN`
#: rather than typed: about **3.566**. Equivalently the Gaussian is cut off at ~1.89 e-folding
#: lengths, where it has fallen to ~2.8 % of the centreline. ⚠️ An inference from one plateau,
#: not a decoded formula -- an *untruncated* Gaussian with `a = 3.66998` reproduces the same number,
#: and no manual states which the exe evaluates.
EXE_GAUSSIAN_K = _gaussian_k_for(EXE_GAUSSIAN_PEAK_TO_MEAN)


def peak_to_mean_round(profile: SimilarityProfile = SimilarityProfile.PARABOLIC) -> float:
    """The unmerged (round) peak-to-mean concentration ratio of `profile`: `1 / integral 2u phi`."""
    match SimilarityProfile(profile):
        case SimilarityProfile.PARABOLIC:
            return PEAK_TO_MEAN_ROUND
        case SimilarityProfile.THREE_HALVES:
            # integral_0^1 2u (1 - u^1.5)^2 du = 2 (1/2 - 2/3.5 + 1/5) = 9/35
            return 35.0 / 9.0
        case SimilarityProfile.EXE_GAUSSIAN:
            return _gaussian_round(EXE_GAUSSIAN_K)
        case SimilarityProfile.GAUSSIAN:
            return _gaussian_round(_LITERATURE_GAUSSIAN_K)
    raise ValueError(f"unknown similarity profile {profile!r}")  # pragma: no cover


def peak_to_mean_slab(profile: SimilarityProfile = SimilarityProfile.PARABOLIC) -> float:
    """The fully merged (slab) peak-to-mean ratio of `profile`: `1 / integral_0^1 phi`."""
    match SimilarityProfile(profile):
        case SimilarityProfile.PARABOLIC:
            return PEAK_TO_MEAN_SLAB
        case SimilarityProfile.THREE_HALVES:
            # integral_0^1 (1 - u^1.5)^2 du = 1 - 2/2.5 + 1/4 = 0.45
            return 1.0 / 0.45
        case SimilarityProfile.EXE_GAUSSIAN:
            return _gaussian_slab(EXE_GAUSSIAN_K)
        case SimilarityProfile.GAUSSIAN:
            return _gaussian_slab(_LITERATURE_GAUSSIAN_K)
    raise ValueError(f"unknown similarity profile {profile!r}")  # pragma: no cover


def profile_weight(
    offset_fraction: NDArray[np.float64] | float,
    profile: SimilarityProfile = SimilarityProfile.PARABOLIC,
) -> NDArray[np.float64]:
    """`phi(u)` for the chosen profile: 1 on the centreline, 0 past the edge.

    `offset_fraction` is `u`: the distance from the centreline over the plume's half-width in
    that direction, so `u = r/b` radially and `u = y/(L/2)` across a merged slab. Values past
    the edge return 0 rather than going negative, because outside the plume there is no excess
    to weight.

    ⚠️ **This weights the excess over ambient, not the value.** A concentration is
    `ambient + weight * (centreline - ambient)`; applying the weight to the absolute value would
    drive salinity to zero at the plume edge. Dilution, being a reciprocal, is
    `centreline_dilution / weight` and is correctly infinite at the edge, where the excess has
    run out.

    ⚠️ The two Gaussians are **truncated** at `u = 1` and so step to zero there -- from 13.5 % of
    the centreline for `GAUSSIAN`, 2.8 % for `EXE_GAUSSIAN`. The parabola and the 3/2 power reach
    zero smoothly.
    """
    u = np.abs(np.asarray(offset_fraction, dtype=np.float64))
    inside = u <= 1.0
    match SimilarityProfile(profile):
        case SimilarityProfile.PARABOLIC:
            shape = 1.0 - u * u
        case SimilarityProfile.THREE_HALVES:
            shape = (1.0 - np.minimum(u, 1.0) ** 1.5) ** 2
        case SimilarityProfile.EXE_GAUSSIAN:
            shape = np.exp(-EXE_GAUSSIAN_K * u * u)
        case SimilarityProfile.GAUSSIAN:
            shape = np.exp(-_LITERATURE_GAUSSIAN_K * u * u)
    return np.where(inside, np.maximum(0.0, shape), 0.0)


def parabolic_weight(
    offset_fraction: NDArray[np.float64] | float,
) -> NDArray[np.float64]:
    """`max(0, 1 - u^2)` -- the default profile's shape. `profile_weight(u, PARABOLIC)`."""
    return profile_weight(offset_fraction, SimilarityProfile.PARABOLIC)


def peak_to_mean(
    diameter: NDArray[np.float64] | float,
    port_spacing: float,
    merged: NDArray[np.bool_] | bool,
    profile: SimilarityProfile = SimilarityProfile.PARABOLIC,
) -> NDArray[np.float64]:
    """The exe's peak-to-mean concentration ratio, from the plume diameter and the spacing.

    Straight-line interpolation from the round value at `d = L` to the slab value at `d = 2L`,
    then flat -- for the default parabola:

        peak/mean = max( 1.5,  2.5 - 0.5 * d / L )

    and exactly 2.0 while the plumes are clear of each other. Measured against every merged row
    in the archive -- **1820** of them, across eleven runs at three spacings and five diffuser
    bearings -- it holds to what three printed decimals on `CL-Dil` can resolve on **1730** of them.
    The other 90 are the ramp described below.

    ⭐ The law was fitted on 944 rows from eight runs; case24's dissolved-oxygen traces then nearly
    doubled the merged archive and did not move it -- 876 further rows, every miss among them a ramp
    prefix starting at exactly 2.0000. Data that did not exist when a law was fitted is the
    strongest confirmation this project can get.

    ⚠️ **`profile` other than `PARABOLIC` applies the same linear blend between that profile's own
    round and slab anchors, and that is an assumption**: case48's geometry never merges, so how the
    exe walks its other two profiles from round to slab is unmeasured (PLAN 8.4). Unmerged rows are
    exact under every profile -- they are the measured plateaus.

    Three details are each load-bearing:

    * **The spacing is nominal.** Not the effective `L |sin psi|` that fires the merge flag and
      sets the entrainment decrements -- the plain number from the diffuser table. The same
      linear law holds across `L` = 1.0, 1.5 and 2.0 m with no angle factor anywhere.
    * **The interpolation is linear, not geometric.** Integrating the parabola over the *actual*
      rounded-rectangle cross-section gives a different curve between the same two endpoints --
      see `exact_peak_to_mean`, which the exe's blend undershoots by up to 0.13 (8 %) near
      `d = 2L`. The endpoints are exact integrals; the path between them is a shortcut.
    * **A single port never blends.** `limspc_shallow` and `limspc_gap` both print
      `merging happened` with one port (PLAN.md row 190) and hold 2.0000 for the rest of the
      trajectory at diameters up to 5.1 m. With no neighbour there is nothing to confine the
      element, so the flag moves the entrainment terms and leaves the profile round. Callers
      pass `merged=False` for a single port; the archive is what says so.

    ⚠️ **The ratio can exceed 2.0, and that is the exe being inconsistent with itself.** The
    merge flag fires when the plume is one *effective* spacing wide, `d = L |sin psi|`, while
    this law uses nominal `L` -- so an oblique diffuser is flagged as merged while `d < L`,
    where the straight line reads above 2.0. A profile more peaked than a round parabola has no
    geometric meaning; it is arithmetic running past its own domain. The size of the excess is
    predicted by the obliquity and nothing else:

    | H-angle | `abs(sin H)` | `d/L` at the banner | the law there |
    |---|---|---|---|
    | 90 (aligned) | 1.000 | 1.006 | 1.997 -- no excess at all |
    | 70 | 0.940 | 0.962 | 2.019 |
    | 45 *and* 135 | 0.707 | 0.843 *both* | 2.079 |
    | 175 | 0.087 | 0.60-0.78 | 2.11-2.20 |

    The 45/135 pair landing on the same `d/L` to four decimals is the confirmation: `|sin psi|`
    is symmetric about 90 degrees and `|cos psi|` is not.

    ⚠️ **The exe ramps into the law over a few steps; we do not.** At the banner the printed
    ratio is exactly 2.0000, and it then climbs monotonically until it meets the line -- 1 output
    row for test15, 3 for test20, 7 for test34, 15 for test35, 40 for test19 -- after which it
    tracks it to +/-0.0001 for every remaining row. The ramp is only ever present when the line
    starts above 2.0, i.e. only for an oblique diffuser, so it is the same inconsistency seen
    from the other side. Its rate is not a constant per step, per diameter or per unit dilution,
    and reproducing an unexplained transient is worse than not having it: we apply the law from
    the flag onward and are wrong by at most 0.2 in the ratio, over at most 40 steps, in a
    region where the exe is arguing with itself. PLAN.md row 202 recorded this as an
    unexplained post-merge overshoot; it is neither unexplained nor an overshoot.
    """
    diameters = np.asarray(diameter, dtype=np.float64)
    flags = np.asarray(merged, dtype=bool)
    round_value = peak_to_mean_round(profile)
    slab_value = peak_to_mean_slab(profile)
    if port_spacing <= 0.0:
        return np.broadcast_to(np.float64(round_value), diameters.shape).copy()
    slope = (round_value - slab_value) / (MERGED_DIAMETERS - 1.0)
    blended = np.maximum(
        slab_value,
        round_value + slope * (1.0 - diameters / port_spacing),
    )
    return np.where(flags, blended, round_value)


def exact_peak_to_mean(diameter: float, port_spacing: float) -> float:
    """The peak-to-mean a **parabola** really has over the confined cross-section.

    The merged element is a circle of radius `b` cut by the reflecting planes midway to each
    neighbour, at `+/-s = +/-L/2` -- the rounded rectangle of eq 55. Integrating `1 - (r/b)^2`
    over that region, in units of `b` with `u = s/b`:

        area     = pi - 2 arccos(u) + 2 u sqrt(1 - u^2)                        (eq 55)
        integral = pi/2 - (8/3) [ 3 pi/16 - (u(5 - 2u^2) sqrt(1-u^2) + 3 arcsin u) / 8 ]

    and the ratio of the two is the peak-to-mean. It returns exactly 2.0 at first contact
    (`u = 1`, no truncation) and approaches exactly 1.5 as `u -> 0` (the slab limit), so it
    reproduces both measured anchors from geometry alone with nothing fitted.

    ⚠️ **This is not what the exe does**, and it is offered for the same reason the corrected
    overlap angle is: so the physics is one call away from the parity path. `peak_to_mean`
    interpolates linearly between the same endpoints, which sits up to 0.024 above this curve
    around `d = 1.3 L` and 0.131 below it at `d = 2 L`. A figure drawing the parabola over the
    real cross-section and labelling the exe's `CL-Dil` on it is therefore inconsistent by up to
    8 % once deeply merged, and should say which of the two it used. Parabolic only: the closed
    form does not exist for the other profiles and nobody has needed it.
    """
    if port_spacing <= 0.0 or diameter <= port_spacing:
        return PEAK_TO_MEAN_ROUND
    u = port_spacing / diameter  # = s/b, both halved
    root = math.sqrt(1.0 - u * u)
    area = math.pi - 2.0 * math.acos(u) + 2.0 * u * root
    # The two circular caps the reflecting planes remove, weighted by the profile.
    caps = 3.0 * math.pi / 16.0 - (u * (5.0 - 2.0 * u * u) * root + 3.0 * math.asin(u)) / 8.0
    integral = math.pi / 2.0 - (8.0 / 3.0) * caps
    return area / integral


def centreline_dilution(
    dilution: NDArray[np.float64] | float,
    peak: NDArray[np.float64] | float,
) -> NDArray[np.float64]:
    """The exe's `CL-Dil`: the flux-averaged dilution divided by the peak-to-mean, floored at 1.

    The floor is the zone of flow establishment. Until the flux-averaged dilution reaches the
    peak-to-mean ratio the arithmetic would report a centreline *less* diluted than the
    discharge, which cannot happen -- the profile has not developed yet, and the exe prints a
    flat 1.000 through the first ~37 steps of every trace (PLAN.md row 22). Clamping reproduces
    that exactly, and the step where it lets go is where the exe's ZFE ends.
    """
    return np.maximum(1.0, np.asarray(dilution, dtype=np.float64) / np.asarray(peak, np.float64))
