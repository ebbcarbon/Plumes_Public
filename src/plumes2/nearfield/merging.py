"""Plume merging: the geometric corrections of eqs 51-56.

When adjacent plumes from a linear diffuser grow into each other they stop entraining across
the shared surface, and their cross-sections stop being round. The reference handles both:

> The basic approach to handling plume merging is to 1) reduce the entrainment areas, both
> Taylor and forced, to account for the loss of exposed surface area that occurs when
> neighboring plumes interfere with each other, and, 2) to confine the plume mass from each
> plume to the space between them that is known to be available from symmetry considerations.

**Each of the four entrainment terms is decremented by its own factor** -- "each of the four
entrainment terms is decremented to a different degree as merging proceeds" -- which is why
this cannot be one scalar multiplying `dm/dt`.

Everything follows from one angle. Two circles of radius `b` whose centres are `L` apart
overlap over a half-angle `phi` measured at the centre from the line of centres:

    phi = arccos( s / b ),   s = L/2                                          eq 52

    a_T   = (pi - 2 phi) / pi        Taylor, and the growth term takes the same   eqs 51, 52
    a_cyl = s / b            = cos(phi)                                           eq 53
    a_cur = a_T + sin(2 phi) / pi                                                 eq 54

`a_T` is just the exposed fraction of the circumference. All three are 1 at first contact
(`b = s`, `phi = 0`) and fall as the overlap deepens, which is the sanity check to hold onto.

⚠️ **Eq 52 is misprinted** in the archived scan as `arctan(sqrt(4b^2 - L^2) / L^2)`, which is
dimensionally impossible. The geometry gives `arctan(sqrt(4b^2 - L^2) / L)`, identical to
`arccos(L/2b)`, and that is what is implemented. Eq 56 is misprinted the other way -- it drops
a square root that eq 55 plainly requires, and the Visual Plumes source confirms the radical.

**The element stops being round.** A reflecting plane midway between ports caps its transverse
extent at `L`, so the cross-section becomes a rounded rectangle of width `L`, and conserving
area at fixed mass inflates the *vertical* half-height:

    pi b_r^2 = b^2 (pi - 2 phi + sin 2 phi)                                       eq 55
    b        = b_r sqrt( pi / (pi - 2 phi + sin 2 phi) )                          eq 56

with `b_r` the radius the element would have if it were still round. `b > b_r` always, since
`sin 2 phi < 2 phi`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "AS_THE_EXE_DOES",
    "MERGING_FLOOR_DEGREES",
    "ConfinedDecrements",
    "MergingChoices",
    "MergingFactors",
    "effective_half_spacing",
    "merged_radius",
    "merging_factors",
    "overlap_angle",
    "slab_fraction",
]

#: Floor on the diffuser-to-flow angle used for the effective spacing, degrees.
#:
#: A plume travelling along the diffuser axis would see the spacing collapse to zero, and with
#: it the merge criterion. UM3 refuses to go below 20 degrees. The 3rd edition instead declares
#: the method valid only "for angles between 45 and 135 degrees"; the 4th edition, which
#: documents UM3 rather than UM, states the floor outright -- "for angles of less than 20
#: degrees ... there is no further reduction in the effective spacing between adjacent plumes,
#: which would otherwise reduce to zero when currents are parallel to the orientation of
#: diffuser pipe".
MERGING_FLOOR_DEGREES = 20.0


class ConfinedDecrements(StrEnum):
    """Which of eqs 51-54's decrements take `phi` at the **confined** half-height of eq 56.

    ⚠️ **The only one of `MergingChoices`' fields whose default is *derived* rather than
    fitted.** The other three exist so the ledger can show a measured choice was discriminating;
    this one exists because `NONE` -- the port's default until 2026-08-21 -- carries a structural
    defect, and `ALL` is the reading UM3's own documentation supports. `GROWTH` and `WALK` are
    refuted attempts, kept as refutations.

    **The defect.** `merging_factors` takes `phi` at the round-equivalent `b_r`, while every
    entrainment area downstream is built from the *confined* `b` of eq 56. So eq 56's inflation
    factor `b/b_r` passes into the entrainment un-opposed, and the growth area -- `pi b db`,
    quadratic in `b` -- turns that into a positive feedback with nothing on the other side.
    Row 260c measures the result: our suppression crosses 1.0 at `d/L` 1.99 and *enhances*
    entrainment to 3.3 where the exe removes a flat 40 % (row 260).

    **Why the confined angle is a brake and not a coefficient.** Deep in the overlap the
    decremented growth area `a_T * pi * b` converges to a **constant** instead of diverging, so
    it stops depending on `b` at all. Taken at `b_r` the same product diverges linearly in
    `b_r/s`. Measured, at test63's half-spacing:

    | `d/L` | `a_T(b_r) pi b / L` | `a_T(b) pi b / L` |
    |---|---|---|
    | 1.05 | 1.494 | 1.481 |
    | 2.00 | 2.738 | 1.862 |
    | 5.00 | 7.614 | 1.996 |
    | 20.0 | **31.35** | **2.000** |

    That is why this is structural: PLAN's finite-time singularity argument says no constant can
    help, because multiplying `db/dt = k b^2` by one only reschedules `t_c = 1/(k b_0)`. A
    saturating area law removes the `b^2` instead.

    ⚠️⚠️ **The constant is a width only in the true geometry, and the shipped angle is not
    in it.** With `phi` from the true `arccos`, `a_T(b) -> (2/pi)(s/b)` and the product tends to
    `2s = L` exactly -- a slab of the diffuser's own width, which is the reading that motivated
    this. With `phi` from UM3's buggy `arctan(sqrt((b^2 - s^2)/s))`, which is what
    `faithful_decrements` selects and what the exe evaluates, the limit is **`2 sqrt(s)`**: a
    length in the square root of metres, so the bug's dimensional inconsistency survives into
    the asymptote. Both saturate, which is all the brake needs; only one of them is a width. The
    two coincide at `s = 1 m` and nowhere else, which is why one half-spacing could not tell
    them apart -- see
    `test_the_saturation_constant_is_a_width_only_in_the_true_geometry`.

    ⭐ **A lead on the residual offset** (row 264b): if the exe brakes this way, its plateau
    should scale as `sqrt(s)` rather than `s`. ⛔ **Refuted** -- case44's six spacings put the
    exe's level at 0.572 / 0.540 / 0.644 / 0.744 / 0.698 from 0.30 to 1.10 m, which rises with
    spacing where `sqrt(s)` would too but by nothing like the right amount; the residual's smooth
    sign change (row 276) is the live description.

    ## ⭐⭐⭐ `WALK`: neither reading is right throughout, and the exe says where the switch is

    `NONE` is the **round** reading and `ALL` the **slab** reading, and each is right in its own
    regime -- `NONE` holds test32's post-merge trajectory to 1.01 % where `ALL` blows it to
    5.24 %, while on case42 `ALL` reaches 0.98 % where `NONE` gives 35.53 % (rows 264c, 267,
    267b). What separates those cases is **how deep into overlap the run gets**: test32 stops at
    `d/L` 2.35 and case42 reaches 3.9, and across five runs `log` onset dilution and `log` max
    `d/L` correlate at **r = -0.973**, so "merges late" and "never gets deep" are one statement.

    ⭐⭐ **And the exe has already stated the schedule, on a different observable.** Its
    peak-to-mean concentration ratio walks from the round 2.0 at `d/L` = 1 to the slab 1.5 at
    `d/L` = 2 and stays there -- `max(1.5, 2.5 - 0.5 d/L)`, fitted on 944 rows (row 203) and
    exactly 1.5000 on 2 020 more past `d/L` 2 out to `d/L` 19.6 (row 199), confirmed again on
    case42 at a port diameter the law had never been fitted at. That is the exe saying, in its
    own output, when it stops treating a merged element as round and starts treating it as a slab.

    So `WALK` moves the decrement radius from `b_r` to the confined `b` on **that** schedule:

        w = (2.0 - peak_to_mean(d, L)) / (2.0 - 1.5)   =   clamp(d/L - 1, 0, 1)
        radius for eqs 51-54 = b_r + w (b - b_r)

    ⭐ **Parity rather than a fit.** The crossover is not a free parameter: it is
    `crossplume.peak_to_mean`, read out of the exe's own `CL-Dil` column, and `slab_fraction`
    *calls* that function rather than restating it, so the two cannot drift. There is nothing
    here to tune.

    ⚠️ **What walks is the radius, not the factors.** `b_r + w (b - b_r)` says the element's
    *shape* walks, which is what the peak-to-mean law describes; blending `f(b_r)` with `f(b)`
    would instead say its occlusion walks while its shape jumps. The two differ because eqs
    51-54 are non-linear in the radius, and only the first has a physical reading behind it.
    """

    #: eqs 51-54 all take `phi` at `b_r`. **The measured default**, and what every golden row
    #: in phases 5 and 6 was taken with. Carries the runaway.
    NONE = "none"
    #: Only the **growth** term's decrement moves to the confined `b`. The growth area is the
    #: only one quadratic in `b` -- `A_T` and `A_cyl` are linear -- so it is the whole of the
    #: singularity, and braking it alone leaves the Taylor and cylinder decrements that row 157
    #: measured at 1.01 % untouched. ⛔ Refuted -- row 264d.
    GROWTH = "growth"
    #: Every decrement moves. The **slab** reading: right once the element is a slab, and
    #: over-suppressing before it -- rows 264c, 267 and 267b.
    ALL = "all"
    #: The decrement radius **walks** from `b_r` to the confined `b` over `d/L` 1 to 2, on the
    #: exe's own measured schedule rather than a chosen one. See `slab_fraction` and the section
    #: above.
    WALK = "walk"


def slab_fraction(radius: float, half_spacing: float) -> float:
    """How far the element has walked from round to slab, 0 to 1 (`ConfinedDecrements.WALK`).

    0 at first contact and 1 once the plume is two spacings wide, on the schedule the exe states
    through its own peak-to-mean ratio -- `crossplume.peak_to_mean`, rows 199 and 203. **Called
    rather than restated**, so the law has one home and this cannot drift from the concentration
    profile that measured it.

    `radius` is the **confined** half-height, because `d/L` is built from the diameter the exe
    prints and that is the confined one.
    """
    from plumes2.crossplume import PEAK_TO_MEAN_ROUND, PEAK_TO_MEAN_SLAB, peak_to_mean

    if half_spacing <= 0.0 or radius <= half_spacing:
        return 0.0
    ratio = float(peak_to_mean(2.0 * radius, 2.0 * half_spacing, True))
    return (PEAK_TO_MEAN_ROUND - ratio) / (PEAK_TO_MEAN_ROUND - PEAK_TO_MEAN_SLAB)


@dataclass(frozen=True, slots=True)
class MergingChoices:
    """The choices in the merging correction. **The defaults are the port's best reading of UM3.**

    ⚠️ **Three of these four fields are trace-fitted conventions; the fourth is derived, and it
    is the one that changed on 2026-08-21.** The distinction matters when reading this class:

    * `faithful_decrements`, `implicit_inflation` and `faithful_inflation` are *measured* choices,
      and each non-default is a **control** -- there so the ledger can show the choice was
      discriminating, not because anyone would run with it. Rows 178, 179 and 180.
    * `confined_decrements` is not like that. Its default `ALL` follows from UM3's **documented**
      mechanism (see `ConfinedDecrements`), its non-default `NONE` is the port's *former* default
      rather than a control, and `GROWTH` and `WALK` are refuted candidates kept as refutations.
      Rows 264-274.

    ⚠️ **Two of these disagree with each other, and that is the finding.** Eqs 51-54 match the
    exe's buggy `arctan`; eq 56's inflation matches the true `arccos`. That is not a reading
    anyone would choose -- see row 180 -- and reproducing it means carrying both.
    """

    #: eqs 51-54 take `phi` from UM3's `arctan(sqrt((b^2-s^2)/s))` rather than `arccos(s/b)`.
    #: Row 179: post-merge dilution 1.01 % with it, 4.04 % with the true geometry.
    faithful_decrements: bool = True
    #: Eq 56 is **implicit** -- `phi` at the merged half-height `b`, solved for, rather than
    #: explicit at the round-equivalent `b_r`. Row 178: the measured inflation is 1.3106 at
    #: test32's step 410, where `phi(b)` gives 1.3131 and `phi(b_r)` gives 1.1652.
    implicit_inflation: bool = True
    #: Eq 56's own angle. `False` -- the **true** `arccos` -- is the default here precisely
    #: because it is *not* the default for the decrements above. Row 180.
    faithful_inflation: bool = False
    #: Which decrements take `phi` at the confined half-height.
    #:
    #: ⚠️⚠️ **`ALL` since 2026-08-21, and this is the one field whose default is not "what the
    #: port originally did".** It was `NONE` while the confined reading was a candidate. Four
    #: things moved it, and the first is the only one that could:
    #:
    #: 1. ⭐ **UM3's own documented mechanism selects it.** Aspiration entrainment is taken "only
    #:    over the surfaces still exposed to ambient fluid", and for eq 55's truncated circle that
    #:    exposed fraction *is* `a_T` at the confined `b` -- see `references/README.md` for the
    #:    derivation. `NONE` corresponds to no statement in any reference; it is how this port was
    #:    first written.
    #: 2. **Out-of-sample accuracy**: 0.98 % post-merge on case42, against `NONE`'s 35.53 %
    #:    (rows 267, 267b), on a case the brake had no part in designing.
    #: 3. **It is the only setting that respects a physical bound.** At two ports `NONE` predicts
    #:    a suppression of 1.017 -- *enhancement* -- where coalescing-plume theory bounds the
    #:    ratio below 1 by construction and the exe measures 0.733 (rows 270, 273).
    #: 4. **Its residual at fixed spacing is a constant** (row 272), where `NONE`'s is a function.
    #:
    #: ⚠️ The one run that preferred `NONE` is case20's test32, 1.01 % against `ALL`'s 5.24 %
    #: (row 264c) -- and that 1.01 % sits *below* its own unmerged control's 1.39 % (row 177),
    #: which is the signature of cancelling errors rather than of correctness. case44 replaces
    #: case20 for exactly that reason.
    #:
    #: ⚠️ `NONE` is kept, and every row it re-baselined says what it read before.
    confined_decrements: ConfinedDecrements = ConfinedDecrements.ALL


#: The measured combination, as a singleton, so nothing has to construct it in a default.
AS_THE_EXE_DOES = MergingChoices()


def effective_half_spacing(
    port_spacing: float,
    axis_bearing_degrees: float,
    plume_velocity: NDArray[np.float64],
    *,
    floor_degrees: float = MERGING_FLOOR_DEGREES,
) -> float:
    """`s = (L/2) |sin psi|`, m -- half the spacing seen across the plume's own path.

    `psi` is the angle between the diffuser axis and the plume's **instantaneous horizontal
    direction**, not the ambient current's. That distinction is the whole point, and it is
    what the reference means by "multiplying L by the factor sin psi where psi is the angle
    between U and the diffuser axis" once the plume has turned to face the flow -- but before
    it turns, the plume still presents its own aspect to its neighbours.

    It matters because merging fires *during* the turn. An earlier revision of this port fitted
    an ellipse `sqrt(cos^2 + 0.596^2 sin^2)` to the measured merge triggers because a static
    `cos(azimuth - current)` sat below every bracket; resolving `psi` against the live
    trajectory removes the need for a fitted constant, since the plume has only partly turned
    by the time it merges. See PLAN.md ledger row 118.

    The diffuser axis is taken perpendicular to the discharge azimuth -- ports fire normal to
    the pipe -- which is how UM3 seeds it, as the normal to the initial vertical plane through
    the discharge velocity.
    """
    horizontal = float(np.hypot(plume_velocity[0], plume_velocity[1]))
    if horizontal <= 0.0:
        # Straight up or straight down: no horizontal aspect, so nothing is foreshortened.
        sine = 1.0
    else:
        bearing = math.atan2(float(plume_velocity[1]), float(plume_velocity[0]))
        sine = abs(math.sin(bearing - math.radians(axis_bearing_degrees)))
    return 0.5 * port_spacing * max(sine, math.sin(math.radians(floor_degrees)))


def overlap_angle(radius: float, half_spacing: float, *, faithful: bool = True) -> float:
    """The overlap half-angle, radians (eq 52). Zero until the plumes touch.

    ⚠️ **The default reproduces an arithmetic bug in the exe.** The geometry says
    `phi = arccos(s/b)`, equivalently `arctan(sqrt(b^2 - s^2)/s)`. UM3 instead evaluates

        phi = arctan( sqrt( (b^2 - s^2) / s ) )

    with the division *inside* the radical. That is dimensionally inconsistent -- it agrees
    with the real thing only when `s = 1 m` -- and the Visual Plumes migration flags it in
    place as an original-code artefact rather than repairing it. It shrinks `phi`, so it
    **weakens** the suppression.

    The exe has it too, and on test32 the evidence is decisive once the merged radius is
    right (it was previously masked by that larger error):

    | | dilution MARE | post-merge | diameter MARE |
    |---|---|---|---|
    | **faithful** | **0.68 %** | **1.01 %** | **1.06 %** |
    | correct geometry | 1.50 % | 4.04 % | 1.66 % |

    The post-merge 1.01 % is the number that settles it: test31, the *unmerged* control, sits
    at 1.39 % over the same window, so with the faithful angle merging contributes **no
    detectable error at all** and the residual is just the common late-trajectory drift.

    `faithful=False` selects the real geometry, for anyone who wants the physics rather than
    parity with the exe. Everything else in this module is genuine geometry -- this is the one
    place the port deliberately reproduces someone else's mistake, on the same principle as
    the effluent-only unit conversion in `chem`: match the exe, flag it loudly, keep the
    corrected path one argument away.
    """
    if half_spacing <= 0.0 or radius <= half_spacing:
        return 0.0
    if faithful:
        return math.atan(math.sqrt((radius * radius - half_spacing * half_spacing) / half_spacing))
    return math.acos(max(-1.0, min(1.0, half_spacing / radius)))


@dataclass(frozen=True, slots=True)
class MergingFactors:
    """The four per-term decrements. All 1 when the plumes are clear of each other."""

    #: eq 51, `(pi - 2 phi)/pi`. Applies to Taylor **and** growth -- "the same correction
    #: factor applies to the growth entrainment term".
    taylor: float
    #: eq 53, `s / b`.
    cylinder: float
    #: eq 54, `a_T + sin(2 phi)/pi`.
    curvature: float
    #: `1 / n_ports`. Not in the 3rd edition -- it belongs to UM3's three-dimensional
    #: generalisation, which spreads the out-of-plane entrainment over the merged group:
    #: "after merging the sideway component of entrainment is distributed over all plumes".
    out_of_plane: float
    #: The growth term's own decrement, when it is not `taylor`'s. `None` means "share
    #: `taylor`", which is what the reference states -- "the same correction factor applies to
    #: the growth entrainment term" -- and is what every measured row was taken with. It stops
    #: being the same factor only under `ConfinedDecrements.GROWTH`, which evaluates eq 52 at
    #: the confined half-height for this term alone.
    growth: float | None = None

    @property
    def merged(self) -> bool:
        return self.taylor < 1.0

    @property
    def growth_factor(self) -> float:
        """The decrement the growth area actually carries -- `taylor` unless braked."""
        return self.taylor if self.growth is None else self.growth


def merging_factors(
    radius: float,
    half_spacing: float,
    n_ports: int,
    *,
    faithful: bool = True,
    confined_radius: float | None = None,
    confined: ConfinedDecrements = ConfinedDecrements.NONE,
) -> MergingFactors:
    """Eqs 51-54 plus UM3's out-of-plane share, from the overlap geometry.

    ⚠️ `radius` is the **unmerged** round-equivalent `b_r`, unlike `merged_radius`, which takes
    `phi` at the confined half-height. The split is not a guess -- it is the only one of the
    four combinations that improves the dilution *and* the diameter together on test32:

    ⚠️ **This table was wrong until 2026-08-20**, and `plumes2 validate` is what caught it: its
    first row carried the numbers belonging to row 179's *control* rather than to the default, so
    the docstring argued for the right choice with the wrong evidence. Re-measured, all four
    combinations against the exe, on test32:

    | eq 56 `phi` | eqs 51-54 | post-merge | diameter | max dia |
    |---|---|---|---|---|
    | **implicit at `b`, true** | **buggy** | **5.24 %** | **2.05 %** | **2.268 m** |
    | implicit at `b`, true | **true** | 8.17 % | 2.92 % | 2.138 m |
    | **explicit** at `b_r` | buggy | 5.75 % | 3.95 % | 1.955 m |
    | implicit at `b`, **buggy** | buggy | 6.03 % | 4.79 % | 1.869 m |

    Row 1 is the default; the other three are rows 179, 178 and 180's controls in that order. The
    default is best on **every** column, which is what makes the three controls discriminating.

    (the exe reaches 2.351 m, and its inflation factor is directly measured -- see
    `merged_radius`.)

    ⚠️⚠️ **Re-measured 2026-08-21, and this is the *third* time this table has carried the
    wrong evidence.** It first argued for the right choice with row 179's control numbers; that was
    corrected on 2026-08-20; and it then went stale again the moment `ConfinedDecrements.ALL`
    became the default, because all four rows had been measured with `NONE` and row 1 still read
    **1.01 %** while the shipped default gave 5.24 %. ⭐ **The ordering is what this table is for,
    and the ordering never changed** -- the argument was right through all three versions and the
    numbers were wrong in two of them, which is exactly the failure mode prose cannot expose.
    Every figure here is now produced by `_merging_error` on demand rather than transcribed.

    It also reads sensibly. Eqs 51-54 decrement the *round* element's areas by the share of
    its surface a neighbour occludes, and that occlusion is set by where two circles of radius
    `b_r`, centres `2s` apart, actually intersect. Eq 55 is a different statement -- about the
    shape mass is confined into once they do -- and is governed by the confined half-height.
    """
    if n_ports <= 1:
        return MergingFactors(1.0, 1.0, 1.0, 1.0)
    if confined is not ConfinedDecrements.NONE and confined_radius is None:
        raise ValueError(f"{confined} needs the confined half-height of eq 56")
    # `ALL` moves every decrement, which is the same thing as evaluating the whole function at
    # the confined half-height -- so do exactly that, and keep one code path for the angle.
    if confined is ConfinedDecrements.ALL and confined_radius is not None:
        radius = confined_radius
    elif confined is ConfinedDecrements.WALK and confined_radius is not None:
        # The element's shape walks from round to slab over `d/L` 1 to 2 on the exe's own
        # schedule, so the radius the decrements see walks with it.
        weight = slab_fraction(confined_radius, half_spacing)
        radius = radius + weight * (confined_radius - radius)
    phi = overlap_angle(radius, half_spacing, faithful=faithful)
    if phi <= 0.0:
        # Every factor is 1 until the plumes actually touch -- including the out-of-plane
        # share. It is "**after** merging the sideway component of entrainment is distributed
        # over all plumes", and an unmerged multiport diffuser behaves as independent single
        # plumes, which is the finding that licenses using the 25-port runs for single-plume
        # physics at all.
        return MergingFactors(1.0, 1.0, 1.0, 1.0)
    taylor = 1.0 - 2.0 * phi / math.pi
    growth: float | None = None
    if confined is ConfinedDecrements.GROWTH and confined_radius is not None:
        # eq 52 again, at the confined half-height, for the growth term alone. `radius` is
        # still `b_r` here, so `taylor` and `cylinder` keep the measured reading.
        confined_phi = overlap_angle(confined_radius, half_spacing, faithful=faithful)
        growth = 1.0 - 2.0 * confined_phi / math.pi
    return MergingFactors(
        taylor=taylor,
        cylinder=half_spacing / radius,
        curvature=taylor + math.sin(2.0 * phi) / math.pi,
        out_of_plane=1.0 / n_ports,
        growth=growth,
    )


def merged_radius(
    unmerged_radius: float,
    half_spacing: float,
    *,
    implicit: bool = True,
    faithful: bool = False,
) -> float:
    """`b` from `b_r`, m (eqs 55-56) -- the vertical half-height of the rounded rectangle.

    Returns the input unchanged while the plumes are clear. Once they overlap the element is
    confined transversely and has to grow vertically to hold the same volume, so `b > b_r`.

    `implicit=False` and `faithful=True` are the **controls** for rows 178 and 180; see
    `MergingChoices`, which is what threads them through the solver. Neither is a mode to run
    in -- they exist so the ledger can show each default was the discriminating choice.

    ⚠️ **The relation is implicit**, and that is not a detail. `phi` is the overlap half-angle,
    which is set by the element's *actual* half-width -- the merged `b` this equation solves
    for -- not by the round-equivalent `b_r`. Measured straight off test32, where `b_r` follows
    from the thickness law and `b` is the printed diameter, so the exe's own inflation factor
    is observable:

    | step | measured | `phi(b)` | `phi(b_r)` |
    |---|---|---|---|
    | 350 | 1.2149 | **1.2234** | 1.1268 |
    | 390 | 1.2964 | **1.2982** | 1.1583 |
    | 410 | 1.3106 | **1.3131** | 1.1652 |

    Evaluating `phi` at `b_r` instead under-inflates by 12 % deep into the overlap, which is
    what left our merged diameter sitting at the *unmerged* value.

    Solved as a root of eq 55 in `u = s/b`, which is better behaved than iterating eq 56 --
    the fixed point converges, but only linearly, and needs ~20 sweeps at deep overlap.

    The merge trigger is untouched: `b = b_r` exactly at first contact, so merging still fires
    at `b_r >= s`, which is the criterion measured to 0.7 % on this same run.
    """
    if half_spacing <= 0.0 or unmerged_radius <= half_spacing:
        return unmerged_radius

    def area_fraction(phi: float) -> float:
        """`(pi - 2 phi + sin 2 phi)`, eq 55's bracket."""
        return math.pi - 2.0 * phi + math.sin(2.0 * phi)

    if not implicit:
        # Row 178's control: eq 56 read as an explicit formula, `phi` at the round-equivalent
        # radius. Under-inflates by 12 % deep into the overlap, which is what left our merged
        # diameter sitting at its unmerged value.
        phi = overlap_angle(unmerged_radius, half_spacing, faithful=faithful)
        return unmerged_radius * math.sqrt(math.pi / area_fraction(phi))

    def residual(u: float) -> float:
        """Eq 55 rearranged: 1 when `u = s/b` is consistent with the confined area.

        This uses the true `arccos` geometry by default even though `overlap_angle` defaults to
        the exe's faithful variant, because the measured inflation matches the real angle -- see
        the table above. The exe is inconsistent between the two, and so, deliberately, are we;
        `faithful=True` is row 180's control for that.

        `u = s/b`, so the faithful angle's radical `(b^2 - s^2)/s` becomes `s (1/u^2 - 1)`.
        """
        if faithful:
            phi = math.atan(math.sqrt(max(0.0, 1.0 / (u * u) - 1.0) * half_spacing))
        else:
            phi = math.acos(max(-1.0, min(1.0, u)))
        return (half_spacing * half_spacing * area_fraction(phi)) / (
            math.pi * unmerged_radius * unmerged_radius * u * u
        ) - 1.0

    # `residual` rises without bound as u -> 0 and is negative at u = 1 whenever the plumes
    # overlap, so the bracket is guaranteed.
    low, high = 1e-12, 1.0
    for _ in range(200):
        middle = 0.5 * (low + high)
        if residual(middle) > 0.0:
            low = middle
        else:
            high = middle
        if high - low < 1e-15:
            break
    return half_spacing / (0.5 * (low + high))
