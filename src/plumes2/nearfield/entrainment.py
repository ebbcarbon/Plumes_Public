"""Entrainment: the two source terms of the continuity equation (manual eq 2).

    dm/dt = -rho_a A_p . U  +  rho_a A_T beta_T

Both are now fully specified. The PLUMES2.0 manual gives only the Taylor term and defers
`A_p` to Frick (1984), but the UM theory in **Baumgartner, Frick & Roberts (1994)**,
*Dilution Models for Effluent Discharges* 3rd ed., EPA/600/R-94/086 (archived under
`references/`) writes it out. Equation numbers below are that report's.

**Taylor (shear) entrainment**, eqs 34-35: `A_T = 2 pi b h` and `beta_T = alpha |V|`, with
`alpha` the aspiration coefficient. The report also derives the recommended value -- 0.082 on
a nominal Gaussian boundary, 0.116 converted to top-hat, 0.081 for jets, and "an average
value for alpha of 0.1 is thought to be slightly conservative". We measured 0.0967 +- 0.0006
and 0.0991 +- 0.0013 on the zero-current runs before reading any of that.

⚠️ **The shear velocity is relative to the ambient**: `beta_T = alpha |V - U_a|`, not the
`alpha |V|` the report writes. See `shear_speed`. This is the single most consequential
departure from the published text in this module, and it is what made the projected area
usable -- with `|V|` the measured residual left for the forced term was essentially zero,
which cannot be right. Zero-current runs cannot distinguish the two, since `|V| = |V - U_a|`
identically there, which is why it went unnoticed through three phases of validation.

**Projected Area Entrainment (PAE)**, eqs 36-41. The essential point, and the thing a
cylinder-only closure gets wrong, is that **each component of the ambient current acts on its
own area**. Working in a frame that follows the trajectory,

    e1   along the trajectory                    -> growth area      pi b db      eq 38
    e2   normal to it, in the vertical plane     -> cylinder  2 b h              eq 40
                                                 -> curvature -(pi/2) b^2 dth/ds h  eq 41
    e3   horizontal, out of that plane           -> dropped: two-dimensional only

with `db = (db/ds) h` (eq 39) and `dth/ds` the rate of change of the trajectory's elevation
angle. So

    forced = rho_a ( |u1| A_growth + |u2| (A_cyl + A_cur) )

The growth term carries `pi b db` rather than `2 pi b db` because "the assumption is made that
only the upstream portion of the area, half the circumference, has flow going through it. The
flow in the wake is altered and is assumed to flow parallel to the plume surface."

The curvature term is **signed**: "this area can be positive or negative depending on the sign
of `d(theta)/ds` ... positive curvature has the effect of reducing the total projected area."

⚠️ On the frame: the report first describes `e2` as "the horizontal normal to the trajectory",
which contradicts its own later statement that `u3`'s "cylinder and curvature contributions
are due to current flowing into the side of the plume element caused by **directional changes
with depth** in the ambient flow" -- i.e. `u3` is the *out-of-plane* component, which only
exists when the current veers. Only one assignment is self-consistent, and it is the second:
`e2` in the vertical plane, `e3` horizontal and out of it. That is what is implemented, since
it is the assignment the physics and the dropped term both require.

❌ **`local_frame` gets the working plane wrong, and this is now settled.** It spans the plane
with the trajectory *and the current*; UM3 uses the **vertical plane containing the
trajectory**, with the out-of-plane current driving the third term. The 4th edition
(EPA/600/R-03/025 §7.2.2, in `references/`) says so outright -- the added term is normal to
"the plane formed by the instantaneous direction of motion of the plume element and the
gravitational acceleration vector" -- and the Visual Plumes source computes exactly that,
`Nv = unit(V x g)`. The argument below for spanning with `U_a` needs replacing, not amending;
it is left here only so the reasoning is not silently rewritten. See PLAN.md Phase 5.

Why this could not be fitted instead of derived, and why it matters:

> Historically the growth and curvature terms have either not been recognized or have been
> thought to be small compared to the cylinder term (Schatzmann, 1979). However, in general,
> it can be shown that all three contributions to the total projected area are important. Any
> earlier perceived inadequacies in the projected area entrainment hypothesis can be
> attributed to the omission of the growth and curvature terms.

An earlier revision of this module had the cylinder term alone with a fitted angular factor.
The `case19` ambient-current sweep showed exactly the predicted failure: the best-fit
coefficient climbed 0.05 -> 0.25 -> 0.45 as the current went 0.01 -> 0.02 -> 0.05 m/s, and
the achievable error *grew* with the very quantity the term was supposed to capture. The
three-term form has **no free coefficients**, so that sweep is now a test rather than a fit.

Also settled, and unsettleable from data: projecting onto the plane perpendicular to the
relative velocity `U_a - V` versus perpendicular to `U_a` is an algebraic identity to leading
order in `|U_a|/|V|` -- both reduce to `2 b h |U_a,perp|`. The report uses `U_a`, "the ambient
current speed normal to the projected area", and that is what is implemented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from plumes2.nearfield.merging import MergingFactors

__all__ = [
    "LocalFrame",
    "ProjectedArea",
    "ProjectedAreaEntrainment",
    "Um3Entrainment",
    "aspiration_velocity",
    "local_frame",
    "shear_speed",
    "taylor_area",
    "taylor_entrainment",
    "vertical_plane_frame",
]

_VERTICAL = np.array([0.0, 0.0, 1.0])


def taylor_area(radius: float, thickness: float) -> float:
    """`A_T = 2 pi b h`, the cylindrical wrap area, m^2 (eq 35)."""
    return 2.0 * math.pi * radius * thickness


def shear_speed(
    plume_velocity: NDArray[np.float64],
    ambient_velocity: NDArray[np.float64],
    *,
    relative: bool = True,
) -> float:
    """The `|V|` that drives `beta_T` -- relative to the ambient by default.

    The report writes `beta_T = alpha |V|` with `|V|` "the average, or top hat, plume element
    velocity", read literally as the plume's speed in the fixed frame. That is almost
    certainly a loose reading of its own text, because shear entrainment is driven by the
    *velocity difference across the plume boundary*, and the fluid on the far side of that
    boundary is moving at `U_a`.

    The evidence is a measurement, and it is a *refutation* rather than a preference. Every
    entrainment term has the element thickness cancel in its specific rate, so each one is
    computable from a trace's printed columns alone:

        total/m   = d(ln D)/dt
        taylor/m  = 2 rho_a alpha |shear| / (rho b)
        growth/m  = rho_a (db/ds) |u1| / (rho b)
        cyl/m     = 2 rho_a |u2| / (pi rho b)
        cur/m     = -rho_a (dtheta/ds) |u2| / (2 rho)

    The residual `total/m - taylor/m` is then the forced entrainment the exe actually
    applied. **It is negative over the late jet when the shear is taken as `|V|`**, and the
    deficit deepens monotonically with the current -- reaching 6 %, 21 %, 49 % and 76 % of
    the Taylor term at 0.01, 0.02, 0.05 and 0.10 m/s. Forced entrainment is a gain by eq 28's
    sign convention and cannot be negative, so `alpha |V|` over-predicts the total on its own
    and is ruled out. Under `alpha |V - U_a|` the residual is positive across the whole late
    jet at every current. That the deficit scales with the current is itself the signature of
    a shear velocity that should have had `U_a` subtracted from it.

    The control that makes this trustworthy is test23, where `U_a = 0`: there the same
    measurement returns a residual of zero to within about 5 % of the Taylor term, which is
    the noise floor set by differencing positions printed to three decimals. At 0.01 m/s the
    forced term is barely outside that floor, so the 0.05 and 0.10 m/s runs carry the
    decisive signal -- as they should, being where the term is largest.

    It also explains the shape of the old failure. `|V|` over-estimates Taylor by more and
    more as the plume decelerates toward the current speed, which is exactly where the
    integrated overshoot grew.

    ⚠️ This fixes the *sign* of the forced term, not yet its magnitude -- the residual is
    consistently **smaller** than the published unit-weight PAE. See
    `ProjectedAreaEntrainment` for what is known about the gap.

    `relative=False` recovers the literal published form, for tests that need to show the two
    differ and for anyone re-deriving the above.
    """
    if relative:
        return float(np.linalg.norm(plume_velocity - ambient_velocity))
    return float(np.linalg.norm(plume_velocity))


def taylor_entrainment(
    ambient_density: float,
    radius: float,
    thickness: float,
    speed: float,
    alpha: float,
) -> float:
    """`rho_a A_T alpha |V|`, kg/s (eqs 33-35).

    `speed` is the shear speed driving the term, which callers should obtain from
    `shear_speed` rather than reading off the plume velocity -- see that function.
    """
    if alpha < 0.0:
        raise ValueError("the aspiration coefficient must be non-negative")
    return ambient_density * taylor_area(radius, thickness) * alpha * abs(speed)


@dataclass(frozen=True, slots=True)
class LocalFrame:
    """The trajectory-following orthonormal frame of eqs 36-37."""

    #: Along the trajectory.
    along: NDArray[np.float64]
    #: Normal to the trajectory, in the vertical plane containing it.
    in_plane: NDArray[np.float64]
    #: Horizontal, normal to that vertical plane. Its current component is dropped.
    out_of_plane: NDArray[np.float64]

    def components(self, vector: NDArray[np.float64]) -> tuple[float, float, float]:
        """`(u1, u2, u3)` -- resolve a vector onto the frame."""
        return (
            float(np.dot(vector, self.along)),
            float(np.dot(vector, self.in_plane)),
            float(np.dot(vector, self.out_of_plane)),
        )


def local_frame(
    velocity: NDArray[np.float64], ambient_velocity: NDArray[np.float64] | None = None
) -> LocalFrame:
    """Build the frame from the plume velocity and, when given, the ambient current.

    The working plane is the one spanned by the trajectory **and the current**, so `e3` is
    `normalize(V x U_a)` and `e2` follows as `e3 x e1` (eq 37 gives `e3 = e1 x e2`). That
    makes `u3` identically zero, which is precisely the two-dimensional restriction the
    reference imposes when it drops that component -- rather than leaving `u3` non-zero and
    then discarding a real contribution.

    It also matters more than it looks. Choosing instead the *vertical* plane through the
    trajectory alone leaves the frame undetermined for a **vertical** element, and the choice
    is not harmless: `u2` is the current resolved onto `e2`, so an arbitrary azimuth can send
    it to zero and silently delete the cylinder and curvature terms for a rising plume in a
    cross-flow. Spanning the plane with the current cannot do that.

    Falls back to the vertical plane through the trajectory when the two are parallel or the
    ambient is still -- in which case `u2` is genuinely zero and only the growth term acts.
    """
    speed = float(np.linalg.norm(velocity))
    if speed == 0.0:
        raise ValueError("the local frame is undefined for a motionless element")
    along = velocity / speed

    normal = np.zeros(3)
    if ambient_velocity is not None:
        normal = _cross3(along, ambient_velocity)
    if float(np.linalg.norm(normal)) < 1e-12:
        # No current, or current parallel to the trajectory: use the vertical plane.
        normal = _cross3(along, _VERTICAL)
    if float(np.linalg.norm(normal)) < 1e-12:
        # Vertical trajectory and no usable current: any plane will do.
        normal = np.array([1.0, 0.0, 0.0])
    out_of_plane = normal / float(np.linalg.norm(normal))
    in_plane = np.cross(out_of_plane, along)
    return LocalFrame(along=along, in_plane=in_plane, out_of_plane=out_of_plane)


@dataclass(frozen=True, slots=True)
class ProjectedArea:
    """The three components of `A_p`, m^2. `curvature` is signed."""

    growth: float
    cylinder: float
    curvature: float

    @property
    def in_plane_total(self) -> float:
        """`A_cyl + A_cur`, the area presented to `u2`. Clamped at zero.

        Strong positive curvature can drive the sum negative, which would make the term an
        entrainment *sink*. Physically the element's faces have overlapped by then -- the
        report's Figure 68b -- and the geometry no longer describes a real surface, so zero
        is the right floor rather than a negative area.
        """
        return max(0.0, self.cylinder + self.curvature)


def projected_area(
    radius: float,
    thickness: float,
    radius_gradient: float,
    elevation_gradient: float,
) -> ProjectedArea:
    """The three areas of eqs 38-41.

    `radius_gradient` is `db/ds` and `elevation_gradient` is `d(theta)/ds`, both per metre
    along the trajectory.
    """
    return ProjectedArea(
        growth=math.pi * radius * radius_gradient * thickness,
        cylinder=2.0 * radius * thickness,
        curvature=-0.5 * math.pi * radius * radius * elevation_gradient * thickness,
    )


@dataclass(frozen=True, slots=True)
class ProjectedAreaEntrainment:
    """Forced entrainment by the PAE hypothesis. **No free coefficients.**

    The weights exist only so a test can switch a term off and demonstrate that it matters;
    all three default to 1, which is the published formulation. They are not tuning knobs --
    see the module docstring for what happened the last time this had one.

    ⚠️ **This is not how UM3 applies the projected area, and the difference is structural.**
    The Visual Plumes source (`sfei/Visual-Plumes-Models`, `UMUnit.py::calc_entrainment`,
    GPL-3.0) shows the cylinder term being **exactly cancelled** by a matching reduction in
    the Taylor velocity: `veave` carries a `-u2/pi` whose specific rate,
    `2 rho_a u2 / (pi rho b)`, is identically `cyl/m`. A cross-current therefore contributes
    nothing net through the Taylor/cylinder pair -- only growth, curvature, the out-of-plane
    term and the along-track reduction of the shear survive.

    Reproducing that structure predicts the measured specific entrainment rate to 1.4-1.7 %
    at every current in the `case19` sweep, against a 1.64 % noise floor set by the
    zero-current control. Summing this closure onto an unreduced Taylor term instead
    over-predicts by 33-88 %.

    Nothing has been ported: the source is GPL-3.0 and this project is BSD-lineage. See
    PLAN.md Phase 5, "the licence question", which has to be settled first.

    An earlier reading of the same traces had the gap as a clean attenuation
    `f(|U_a| / |V|)`, tabulated and collapsing across a tenfold range of current. That
    measurement was sound and is still pinned by a test; the *interpretation* was wrong,
    because it differenced against this closure rather than against the cancelled one.
    """

    growth: float = 1.0
    cylinder: float = 1.0
    curvature: float = 1.0

    def area(
        self,
        radius: float,
        thickness: float,
        radius_gradient: float,
        elevation_gradient: float,
    ) -> ProjectedArea:
        raw = projected_area(radius, thickness, radius_gradient, elevation_gradient)
        return ProjectedArea(
            growth=self.growth * raw.growth,
            cylinder=self.cylinder * raw.cylinder,
            curvature=self.curvature * raw.curvature,
        )

    def rate(
        self,
        ambient_density: float,
        ambient_velocity: NDArray[np.float64],
        plume_velocity: NDArray[np.float64],
        radius: float,
        thickness: float,
        radius_gradient: float,
        elevation_gradient: float,
    ) -> float:
        """`rho_a ( |u1| A_growth + |u2| (A_cyl + A_cur) )`, kg/s.

        Non-negative by construction: eq 28's sign convention makes the term a gain, and the
        magnitudes of the current components are what drive fluid through each face.
        """
        frame = local_frame(plume_velocity, ambient_velocity)
        along, in_plane, _out_of_plane = frame.components(ambient_velocity)
        area = self.area(radius, thickness, radius_gradient, elevation_gradient)
        return ambient_density * (
            abs(along) * max(0.0, area.growth) + abs(in_plane) * area.in_plane_total
        )


# --------------------------------------------------------------------------- the UM3 closure


def _cross3(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    """`a x b` for 3-vectors, written out.

    ⚠️ **A performance fix, not a numerical one.** `np.cross` computes exactly these three
    differences, so this is bit-identical -- its cost is shape dispatch and broadcasting, which for
    a length-3 vector dwarfs the six multiplications. It was 32 % of total solver time at 160 000
    calls per integration (2026-08-17 audit); this and hoisting the frame out of the fixed-point
    loop together roughly halve a run.
    """
    return np.array(
        [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]
    )


def vertical_plane_frame(
    plume_velocity: NDArray[np.float64],
    ambient_velocity: NDArray[np.float64] | None = None,
) -> LocalFrame:
    """UM3's frame: the working plane is the **vertical plane containing the trajectory**.

    `e3` is `normalize(V x g)`, horizontal and normal to that plane, so the ambient current
    splits into an in-plane part -- which drives the growth, cylinder and curvature areas --
    and an out-of-plane part, which drives the third term UM3 adds when generalising PAE to
    three dimensions.

    This is *not* what `local_frame` does, and the difference is not a convention. The 4th
    edition (EPA/600/R-03/025 §7.2.2, in `references/`) states it outright: the added term
    represents entrainment through the side "represented by a vector pointing at right angles
    to the plane formed by the instantaneous direction of motion of the plume element and the
    gravitational acceleration vector". Only the current's *direction changes with depth* can
    put anything out of that plane, which is exactly what the 3rd edition says the dropped
    component is due to -- so the two reports agree once this one is read.

    ⚠️ For a **vertical** trajectory every vertical plane contains it, so the frame is
    degenerate and the choice is *not* harmless: it decides how the current splits between the
    in-plane and out-of-plane terms. Picking an arbitrary azimuth sends the whole current
    out-of-plane, leaving `u2 = 0` and no cross-flow reduction of the aspiration velocity at
    all -- in precisely the configuration where cross-flow entrainment is largest.

    So when the trajectory is vertical the plane is chosen to **contain the current**, which
    is the only choice that keeps `u2 = |U_a|` as it should be. UM3 reaches the same place by
    a different route: it carries the plane normal over from the previous step and refuses to
    update it while `V` is parallel to gravity, seeded with `y` at the port.

    No archived reference case discharges vertically -- every one is at 45 degrees -- so this
    path is exercised only by unit tests.
    """
    speed = float(np.linalg.norm(plume_velocity))
    if speed == 0.0:
        raise ValueError("the local frame is undefined for a motionless element")
    along = plume_velocity / speed

    normal = np.cross(along, _VERTICAL)
    if float(np.linalg.norm(normal)) < 1e-12 and ambient_velocity is not None:
        # Vertical trajectory: span the plane with the current so it stays in-plane.
        normal = np.cross(along, ambient_velocity)
    if float(np.linalg.norm(normal)) < 1e-12:
        normal = np.array([1.0, 0.0, 0.0])
    out_of_plane = normal / float(np.linalg.norm(normal))
    return LocalFrame(
        along=along, in_plane=_cross3(out_of_plane, along), out_of_plane=out_of_plane
    )


def aspiration_velocity(
    plume_velocity: NDArray[np.float64],
    ambient_velocity: NDArray[np.float64],
    alpha: float,
) -> float:
    """The effective Taylor velocity, **with the cylinder term already folded in**, m/s.

    This is the piece the published equations do not give, and the reason a faithful
    implementation of eqs 33-41 over-predicts by 33-88 % in a cross-flow. Two corrections:

    1. The shear velocity is `alpha | |V| - u1 |`, the plume speed less the **along-track**
       component of the current -- not `alpha |V|`. Shear entrainment is driven by the
       velocity difference across the boundary, and the fluid outside is moving too.
    2. The velocity is reduced again by `u2/pi`, and that reduction is *exactly* the
       published cylinder term: on `A_T = 2 pi b h` it contributes
       `-rho_a 2 b h u2`, while `A_cyl = 2 b h` driven by `u2` contributes `+rho_a 2 b h u2`.
       **They annihilate.** A cross-current entrains nothing net through this pair; what
       survives is growth, curvature, the out-of-plane term, and correction 1.

    When the cross-flow is strong enough to overwhelm the shear (`u2 > ven`) an angle
    `angl = arctan(sqrt(u2/ven - 1))` opens up and softens both reductions. Summing the pair
    gives a single effective velocity,

        ven    = alpha | |V| - u1 |
        angl   = arctan(sqrt(u2/ven - 1))   if u2 > ven else 0
        result = ven (1 - angl/pi) + (u2/pi) sin(angl)

    so the Taylor and cylinder terms together are just `rho_a A_T` times this.

    **Provenance.** Established by measuring the specific entrainment rate directly from the
    `case18`/`case19` traces, where it predicts the exe to 1.39-1.70 % MARE at every current
    against the 1.64 % noise floor the zero-current control sets -- i.e. exactly, with nothing
    left over. Corroborated by the Visual Plumes UM3 source
    (`sfei/Visual-Plumes-Models`, `UMUnit.py::calc_entrainment`), which is GPL-3.0 and
    therefore cited rather than copied; see PLAN.md Phase 5.

    Reduces to `alpha |V|` identically when the ambient is still, so no zero-current result
    can move.
    """
    if alpha < 0.0:
        raise ValueError("the aspiration coefficient must be non-negative")
    speed = float(np.linalg.norm(plume_velocity))
    if speed == 0.0:
        raise ValueError("the aspiration velocity is undefined for a motionless element")

    frame = vertical_plane_frame(plume_velocity, ambient_velocity)
    in_plane_current = ambient_velocity - float(
        np.dot(ambient_velocity, frame.out_of_plane)
    ) * frame.out_of_plane
    along = float(np.dot(in_plane_current, frame.along))
    # The cross-track component. The ambient is horizontal, so resolving it against the
    # trajectory is the same as scaling by the elevation angle's sine.
    across = float(np.linalg.norm(in_plane_current)) * abs(plume_velocity[2]) / speed

    shear = alpha * abs(speed - along)
    if shear <= 0.0:
        return 0.0
    angle = math.atan(math.sqrt(across / shear - 1.0)) if across > shear else 0.0
    return shear * (1.0 - angle / math.pi) + (across / math.pi) * math.sin(angle)


@dataclass(frozen=True, slots=True)
class Um3Entrainment:
    """Total entrainment as UM3 computes it -- Taylor and forced together.

    They cannot be separated any more: `aspiration_velocity` folds the cylinder term into the
    shear velocity, where it cancels. What remains beside it is the growth area driven by the
    along-track current, the signed curvature area, and the out-of-plane term.

    The weights are for tests and experiments, exactly as in `ProjectedAreaEntrainment`.

    ⚠️ **`curvature` defaults to 0, and that is a finding rather than a retreat.** Two
    independent lines say the exe applies no curvature entrainment at all:

    1. **The traces.** Switching it off improves the `case19` sweep at every current --
       jet-phase MARE 0.54/0.79/1.13/1.60 % with it, 0.34/0.36/0.52/0.88 % without -- and the
       improvement *grows* with the current, which is the signature of a term whose magnitude
       is wrong rather than one that is merely small.
    2. **The source.** UM3 drives the curvature area with `V . unit(Rc)`, and builds `Rc` as
       `V x (V x V_last)`. That is perpendicular to `V` by the vector triple product, so the
       dot product is **identically zero** -- confirmed to machine epsilon over random turns,
       and true of the initialisation branch's `V x g` too. The term cannot contribute.

    Almost certainly unintended upstream -- the migration's own comments say "not sure what
    `Rc` represents exactly" -- but parity with the exe is the goal, and the traces agree
    with the code. Eq 41's `-(pi/2) b^2 (dtheta/ds) h` is implemented and signed, so setting
    `curvature=1.0` recovers the published behaviour for anyone testing it.

    One caveat for Phase 5's merging work: UM3 adds an induced-current speed to that same dot
    product, so for **merged** plumes the curvature term stops being identically zero. This
    default is right for single plumes, which is every run validated so far.
    """

    growth: float = 1.0
    curvature: float = 0.0
    out_of_plane: float = 1.0

    def rate(
        self,
        ambient_density: float,
        ambient_velocity: NDArray[np.float64],
        plume_velocity: NDArray[np.float64],
        radius: float,
        thickness: float,
        radius_gradient: float,
        elevation_gradient: float,
        alpha: float,
        factors: MergingFactors | None = None,
        frame: LocalFrame | None = None,
    ) -> float:
        """Total `dm/dt`, kg/s -- the whole right-hand side of eq 2.

        `factors` carries the per-term merging decrements of eqs 51-54; omit it for a plume
        that is clear of its neighbours. They cannot be collapsed into one scalar on the
        total, because each term loses a different share of its area.

        `frame` is an optimisation with no physics in it: the frame depends only on the two
        velocities, which do not change across the solver's fixed-point sweep for the path
        derivatives, so `solver.rhs` builds it once and passes it in. Omit it and it is built
        here, identically. It was 40 % of solver time before the 2026-08-17 audit.
        """
        if factors is None:
            factors = MergingFactors(1.0, 1.0, 1.0, 1.0)
        speed = float(np.linalg.norm(plume_velocity))
        if frame is None:
            frame = vertical_plane_frame(plume_velocity, ambient_velocity)
        out_of_plane_current = float(np.dot(ambient_velocity, frame.out_of_plane))
        in_plane_current = ambient_velocity - out_of_plane_current * frame.out_of_plane
        along = float(np.dot(in_plane_current, frame.along))
        across = float(np.linalg.norm(in_plane_current)) * abs(plume_velocity[2]) / speed

        # ⚠️ The Taylor and cylinder halves of the cancelled pair carry **different** merging
        # factors -- `a_T` and `a_cyl` -- so merging breaks the cancellation and the two have
        # to be reassembled separately. `aspiration_velocity` returns the already-summed pair,
        # so undo the sum, weight each half, and re-add.
        shear = alpha * abs(speed - along)
        angle = math.atan(math.sqrt(across / shear - 1.0)) if across > shear > 0.0 else 0.0
        reduced = shear * (1.0 - angle / math.pi) - (across / math.pi) * (
            1.0 - math.sin(angle)
        )
        area = taylor_area(radius, thickness)
        paired = ambient_density * (
            factors.taylor * area * reduced
            + factors.cylinder * projected_area(radius, thickness, 0.0, 0.0).cylinder * across
        )
        areas = projected_area(radius, thickness, radius_gradient, elevation_gradient)
        # UM3 gates the growth term on the current and the radius change agreeing in sign:
        # an element that is shrinking presents no growth annulus to a following current.
        # `growth_factor` is `factors.taylor` -- the reference's "the same correction factor
        # applies to the growth entrainment term" -- unless `ConfinedDecrements.GROWTH` has
        # moved this one term's angle to the confined half-height. This is the only term whose
        # area is quadratic in the radius, so it is the only one that can run away.
        growth = (
            self.growth
            * factors.growth_factor
            * ambient_density
            * abs(along)
            * max(0.0, areas.growth)
            if (along > 0.0) == (radius_gradient > 0.0)
            else 0.0
        )
        # Curvature pairs with `u2` (eq 41) and stays **signed** -- positive curvature closes
        # area off. Only the cylinder half of the published `u2` pairing was cancelled into
        # the aspiration velocity, so this one still stands on its own.
        curvature = (
            self.curvature * factors.curvature * ambient_density * across * areas.curvature
        )
        sideways = (
            self.out_of_plane
            * factors.out_of_plane
            * ambient_density
            * abs(out_of_plane_current)
            * areas.cylinder
        )
        # Floor the total, not the individual terms: a signed term is allowed to subtract,
        # but the element cannot entrain negatively.
        return max(0.0, paired + growth + curvature + sideways)
