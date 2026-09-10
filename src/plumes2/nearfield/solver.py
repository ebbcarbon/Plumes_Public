"""Integrate the LCV equations (manual eqs 2-5).

The right-hand sides are written in terms of the *conserved* quantities, which is what makes
them clean:

    d/dt [ m, m U_j, m T_j, m S_j, x ]
        = [ E, U_a E - m (rho_a - rho_j)/rho_j g, T_a E, S_a E, U_j ]

with `E = dm/dt` the total entrainment. Heat and salt need no extra work -- their fluxes are
just the ambient value times `E` -- so plume temperature and salinity come out of the
division `m T_j / m` automatically, and mixing is conservative by construction. That is
exactly what the traces show: `P-Sal` at step 1 of test23 is 34.924, which is
`(35 + 0.02 * 31.1) / 1.02`.

The element radius is **not** a state variable. It follows algebraically from
`h` proportional to `|U_j|` -- see `state.py` -- which is what keeps this a 9-vector.

**Integration is in time, with `scipy.solve_ivp` and dense output.** That is deliberate: the
exe prints a `Time` column, so a trajectory can be compared to a trace *at the exe's own
printed times*, which decouples validating the physics from reproducing the exe's step
controller. The controller (a 2 % mass-growth cap plus an unidentified second criterion, see
PLAN.md Phase 5) only matters for row alignment and byte-exact output, and is applied
separately in `steps.py` rather than being baked into the integration. Because LSODA picks its
own steps, run time is a question of tolerance and of the cost of one right-hand side -- see
`integrate` for the tolerance measurement -- and not of a step grid.

Termination follows the manual's four benchmarks (§2.3.1) plus the GUI's stop-at-surface
control; `terminate.py` will own the full rule set including the max-rise-or-fall switch.
What is here is the subset needed to stop an integration safely.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from plumes2.ambient import AmbientProfileView
from plumes2.config import Case
from plumes2.nearfield.entrainment import (
    ProjectedAreaEntrainment,
    Um3Entrainment,
    shear_speed,
    taylor_area,
    vertical_plane_frame,
)
from plumes2.nearfield.merging import (
    AS_THE_EXE_DOES,
    MergingChoices,
    MergingFactors,
    effective_half_spacing,
    merged_radius,
    merging_factors,
)
from plumes2.nearfield.state import (
    GRAVITY,
    LcvGeometry,
    LcvState,
    initial_state,
    unpack,
)
from plumes2.nearfield.terminate import (
    OscillationEvent,
    OscillationKind,
    TerminationReason,
    near_field_end,
)
from plumes2.seawater import EquationOfState, density_of

#: Every PAE weight set to zero -- forced entrainment switched off entirely.
#:
#: This was the default for a while, when the published unit weights integrated to a 121 %
#: overshoot at 0.10 m/s against 21 % for leaving the term out. That retreat is over: the
#: overshoot was the *Taylor* term, and with `relative_shear` the published closure is back
#: to being the best available (see `shear_speed`). Direct measurement now also shows the
#: forced term is unambiguously present and positive, so omitting it is a known error, not a
#: neutral choice.
#:
#: Kept because it is what isolates Taylor entrainment, which is how `alpha`, the thickness
#: law and the contraction were all measured.
NO_FORCED_ENTRAINMENT = ProjectedAreaEntrainment(growth=0.0, cylinder=0.0, curvature=0.0)

__all__ = [
    "NO_FORCED_ENTRAINMENT",
    "NearFieldSolution",
    "Trajectory",
    "integrate",
]


@dataclass(frozen=True, slots=True)
class Trajectory:
    """A solved near-field trajectory, sampled at whatever times were requested."""

    time: NDArray[np.float64]
    dilution: NDArray[np.float64]
    diameter: NDArray[np.float64]
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    #: Elevation, negative below the surface -- the sign of the `.dat` `Depth` column.
    z: NDArray[np.float64]
    salinity: NDArray[np.float64]
    temperature: NDArray[np.float64]
    plume_density: NDArray[np.float64]
    speed: NDArray[np.float64]
    #: Whether neighbouring plumes overlap at this sample. False everywhere for a single port.
    #: The cross-plume profile keys on it -- see `plumes2.crossplume`.
    merged: NDArray[np.bool_]

    def __len__(self) -> int:
        return int(self.time.size)


@dataclass(frozen=True, slots=True)
class NearFieldSolution:
    """The raw integration plus the geometry needed to interpret it."""

    #: Needed to re-derive the merged radius when sampling -- it depends on the diffuser.
    case: Case
    geometry: LcvGeometry
    #: scipy's dense-output solution over the packed state vector.
    solution: object
    reason: str
    events: dict[str, float] = field(default_factory=dict)
    #: Every turning point found, in order -- the trapping/reversal alternation the exe
    #: prints as banners. The switch counts these; see `terminate.py`.
    oscillations: tuple[OscillationEvent, ...] = ()
    #: When the **near field** ends, which is not the same as when the integration stopped:
    #: integration deliberately runs past the limit so the oscillations can be counted.
    end_time: float = float("inf")
    #: The merging angle choices this trajectory was **integrated** with. Carried so that
    #: `sample` cannot re-derive the radius under a different set -- a control run integrated
    #: one way and sampled another would disagree with itself and look like a physics result.
    merging: MergingChoices = AS_THE_EXE_DOES

    def sample(self, times: NDArray[np.float64]) -> Trajectory:
        """Evaluate the trajectory at arbitrary times, e.g. a trace's printed `Time`."""
        requested = np.asarray(times, dtype=np.float64)
        raw = self.solution.sol(requested)  # type: ignore[attr-defined]
        mass = raw[0]
        velocity = raw[1:4] / mass
        temperature = raw[4] / mass
        salinity = raw[5] / mass
        speed = np.linalg.norm(velocity, axis=0)
        # Plus the effluent's density-only tracer, diluted with the mass (`LcvState.density`).
        plume_density = (
            np.asarray(
                density_of(
                    salinity,
                    temperature,
                    equation_of_state=self.case.near_field.equation_of_state,
                ),
                dtype=np.float64,
            )
            + raw[9] / mass
        )
        geometry = [
            _merged_geometry(self.case, self.geometry, m, r, s, v, self.merging)
            for m, r, s, v in zip(mass, plume_density, speed, velocity.T, strict=True)
        ]
        radius = np.array([entry[0] for entry in geometry])
        return Trajectory(
            time=requested,
            # Floored at 1: the mass ratio at t = 0 evaluates to 1 within rounding, and the dense
            # output can hand back 0.9999999999999999 -- which `chem.transport.mix` rightly
            # refuses as sub-unity dilution. Found on Ebb's default case with a 5 m port
            # (2026-08-26), where every other depth happened to land on exactly 1.0.
            dilution=np.maximum(1.0, self.geometry.dilution(mass)),
            diameter=2.0 * radius,
            x=raw[6],
            y=raw[7],
            z=raw[8],
            salinity=salinity,
            temperature=temperature,
            plume_density=plume_density,
            speed=speed,
            merged=np.array([entry[2].merged for entry in geometry], dtype=bool),
        )


#: Fixed-point sweeps resolving the implicit path derivatives. The coupling is weak -- the
#: forced term is a modest fraction of the total -- so this converges in two or three.
_PATH_DERIVATIVE_ITERATIONS = 6
_PATH_DERIVATIVE_TOLERANCE = 1e-12


def _density_partials(
    salinity: float,
    temperature: float,
    equation_of_state: EquationOfState = EquationOfState.EOS80,
) -> tuple[float, float]:
    """`(drho/dS, drho/dT)` by central difference on the equation of state.

    The salinity difference is **one-sided at the freshwater end**. EOS-80 is undefined for
    `S < 0`, so a centred step at `S = 0` evaluates it out of domain and raises -- which made
    every freshwater discharge unrunnable, case14 included. Municipal outfalls are routinely
    fresh, so this is a normal input rather than an edge case.

    ⛔ **Replacing this with analytic derivatives was proposed and rejected on 2026-08-21, on the
    measurement.** Knudsen is a closed-form polynomial so its two partials are exact in a dozen
    lines, and the one-sided step at `S = 0` looked like a real accuracy defect. Measured against
    the exact Knudsen derivatives, the finite difference is right to:

    | S, T | rel. error in `drho/dS` | in `drho/dT` |
    |---|---|---|
    | 35, 10 | 2.0e-10 | 2.3e-09 |
    | 2, 11 | 6.4e-10 | 3.4e-09 |
    | **0, 10** (one-sided) | **4.9e-08** | 6.1e-10 |
    | **0, 4** (one-sided) | **5.5e-08** | 2.5e-07 |
    | 45, 2.7 | 9.0e-13 | 7.7e-10 |

    So the worst case is **5e-8 relative**, six orders of magnitude below this port's 0.31 %
    accuracy floor, and the one-sided end costs 5e-8 rather than anything that matters. The
    remaining case for the change was a **1.10x** ceiling on solver speed -- against the cost of
    hand-differentiating *two* equations of state, EOS-80 included, and maintaining them. Not
    worth it. ⭐ Recorded here rather than in the ledger because there is no disagreement to
    measure: this is a rejected optimisation, not a finding.
    """
    step = 1e-4
    low = max(0.0, salinity - step)
    high = salinity + step

    def rho(sal: float, temp: float) -> float:
        return float(density_of(sal, temp, 0.0, equation_of_state=equation_of_state))

    by_salinity = (rho(high, temperature) - rho(low, temperature)) / (high - low)
    by_temperature = (rho(salinity, temperature + step) - rho(salinity, temperature - step)) / (
        2.0 * step
    )
    return by_salinity, by_temperature


def _merged_geometry(
    case: Case,
    geometry: LcvGeometry,
    mass: float,
    plume_density: float,
    speed: float,
    velocity: NDArray[np.float64],
    choices: MergingChoices = AS_THE_EXE_DOES,
) -> tuple[float, float, MergingFactors]:
    """`(radius, thickness, factors)` with merging applied.

    Three things move together once neighbouring plumes touch, and they have to stay
    consistent between the right-hand side, the termination events and the sampled output:

    * the **thickness** follows the *unmerged* radius, because eq 55 conserves the
      cross-sectional area `pi b_r^2` -- the element is confined transversely, not squeezed;
    * the **radius** is the merged vertical half-height of eq 56, which is what the entrainment
      areas and the surface/seabed contact tests need;
    * the **factors** decrement each entrainment term by its own share of lost surface.
    """
    unmerged = float(geometry.radius(mass, plume_density, speed))
    thickness = mass / (plume_density * math.pi * unmerged * unmerged)
    diffuser = case.diffuser
    if diffuser.n_ports <= 1 or diffuser.port_spacing <= 0.0:
        return unmerged, thickness, MergingFactors(1.0, 1.0, 1.0, 1.0)
    half_spacing = effective_half_spacing(
        diffuser.port_spacing, diffuser.horizontal_angle + 90.0, velocity
    )
    # ⚠️ The two halves take `phi` at **different** radii, which is measured rather than
    # assumed -- see `merged_radius` and `merging_factors`. The confined cross-section is
    # defined by its own half-width; the occluded surface is defined by the round element's
    # overlap with its neighbour.
    merged = merged_radius(
        unmerged,
        half_spacing,
        implicit=choices.implicit_inflation,
        faithful=choices.faithful_inflation,
    )
    # ⚠️ And that asymmetry is exactly what `choices.confined_decrements` exists to test: the
    # areas below are built from `merged`, so a decrement taken at `unmerged` lets eq 56's
    # inflation factor through un-opposed. See `ConfinedDecrements`.
    return (
        merged,
        thickness,
        merging_factors(
            unmerged,
            half_spacing,
            diffuser.n_ports,
            faithful=choices.faithful_decrements,
            confined_radius=merged,
            confined=choices.confined_decrements,
        ),
    )


def _make_rhs(
    case: Case,
    geometry: LcvGeometry,
    ambient: AmbientProfileView,
    forced: ProjectedAreaEntrainment | Um3Entrainment,
    relative_shear: bool,
    choices: MergingChoices,
) -> Callable[[float, NDArray[np.float64]], NDArray[np.float64]]:
    alpha = case.near_field.aspiration_coefficient
    um3 = isinstance(forced, Um3Entrainment)
    # Read once. The plume, the ambient and the buoyancy partials must all use the same
    # equation of state -- mixing two would inject a spurious density difference directly into
    # the buoyancy term, which is the one quantity that cannot absorb it.
    eos = case.near_field.equation_of_state

    def rhs(_t: float, vector: NDArray[np.float64]) -> NDArray[np.float64]:
        state = unpack(vector)
        sample = ambient.sample(state.depth)
        ambient_density = float(sample.density)
        plume_density = state.density(equation_of_state=eos)
        speed = state.speed

        radius, thickness, factors = _merged_geometry(
            case, geometry, state.mass, plume_density, speed, state.velocity, choices
        )

        ambient_velocity = np.array(
            [
                sample.current_speed * np.cos(np.radians(sample.current_direction)),
                sample.current_speed * np.sin(np.radians(sample.current_direction)),
                0.0,
            ]
        )
        # eq 42: entrained momentum plus buoyancy. Positive z is up, so a plume lighter than
        # the ambient accelerates upward.
        buoyancy = np.array(
            [0.0, 0.0, state.mass * (ambient_density - plume_density) / plume_density * GRAVITY]
        )
        # The UM3 closure returns the *total*: its cylinder term is folded into the shear
        # velocity, where it cancels, so the two halves of eq 2 no longer separate. The
        # published path keeps them apart and sums, which is what the 1994 report describes.
        if um3:
            taylor = 0.0
        else:
            shear = shear_speed(state.velocity, ambient_velocity, relative=relative_shear)
            taylor = ambient_density * taylor_area(radius, thickness) * alpha * shear

        # The growth and curvature areas need db/ds and dtheta/ds, which depend on the
        # entrainment through the state derivatives -- an implicit algebraic loop. Every
        # dependence is linear in the entrainment rate, so a short fixed-point sweep
        # resolves it. The reference instead lags the derivatives across program steps
        # ("estimated from the difference in radius in successive program steps divided by
        # the distance traversed"); solving here is the same closure without the lag.
        # The local frame depends only on the two velocities, which are fixed for this
        # right-hand side, so it is built once here rather than once per fixed-point sweep.
        # Purely an optimisation -- `rate` builds an identical frame when not given one.
        local = vertical_plane_frame(state.velocity, ambient_velocity) if um3 else None

        def closure(radius_gradient: float, elevation_gradient: float) -> float:
            if isinstance(forced, Um3Entrainment):
                return forced.rate(
                    ambient_density,
                    ambient_velocity,
                    state.velocity,
                    radius,
                    thickness,
                    radius_gradient,
                    elevation_gradient,
                    alpha,
                    factors,
                    local,
                )
            return taylor + forced.rate(
                ambient_density,
                ambient_velocity,
                state.velocity,
                radius,
                thickness,
                radius_gradient,
                elevation_gradient,
            )

        by_salinity, by_temperature = _density_partials(state.salinity, state.temperature, eos)
        horizontal = float(np.hypot(state.velocity[0], state.velocity[1]))
        # Seed the sweep with the closure evaluated at zero path curvature, so the UM3 path
        # -- whose Taylor part lives inside `forced` -- does not start from zero.
        entrainment = taylor if not um3 else closure(0.0, 0.0)
        for _ in range(_PATH_DERIVATIVE_ITERATIONS):
            acceleration = (
                (ambient_velocity - state.velocity) * entrainment + buoyancy
            ) / state.mass
            speed_rate = float(np.dot(state.velocity, acceleration)) / speed
            salinity_rate = (sample.salinity - state.salinity) * entrainment / state.mass
            temperature_rate = (sample.temperature - state.temperature) * entrainment / state.mass
            # The excess-density tracer is conserved as m * excess, so it decays as entrainment/m.
            density_rate = (
                by_salinity * salinity_rate
                + by_temperature * temperature_rate
                - state.excess_density * entrainment / state.mass
            )
            # b = sqrt(k m / (rho |V|)), so db/b = (dm/m - drho/rho - d|V|/|V|) / 2.
            radius_rate = (
                0.5
                * radius
                * (entrainment / state.mass - density_rate / plume_density - speed_rate / speed)
            )
            # theta = atan2(Vz, |V_horizontal|), the trajectory's elevation angle.
            if horizontal > 1e-12:
                horizontal_rate = (
                    state.velocity[0] * acceleration[0] + state.velocity[1] * acceleration[1]
                ) / horizontal
                elevation_rate = (
                    horizontal * acceleration[2] - state.velocity[2] * horizontal_rate
                ) / (speed * speed)
            else:
                elevation_rate = 0.0

            updated = closure(radius_rate / speed, elevation_rate / speed)
            converged = abs(updated - entrainment) <= _PATH_DERIVATIVE_TOLERANCE * max(
                updated, 1e-30
            )
            entrainment = updated
            if converged:
                break

        derivative = np.empty_like(vector)
        derivative[0] = entrainment
        derivative[1:4] = ambient_velocity * entrainment + buoyancy
        derivative[4] = sample.temperature * entrainment
        derivative[5] = sample.salinity * entrainment
        derivative[6:9] = state.velocity
        # m * excess is conserved: the ambient brings none in, so the slot's rate is zero.
        derivative[9] = 0.0
        return derivative

    return rhs


def integrate(
    case: Case,
    *,
    forced: ProjectedAreaEntrainment | Um3Entrainment | None = None,
    relative_shear: bool = True,
    merging: MergingChoices | None = None,
    max_time: float = 3600.0,
    max_dilution: float | None = None,
    rtol: float = 1e-6,
    atol: float = 1e-9,
) -> NearFieldSolution:
    """Integrate eqs 2-5 from the port until a termination benchmark is reached.

    **Tolerances (2026-09-10).** LSODA is adaptive, so the step count -- and the run time, which
    is all in the right-hand side -- is set by `rtol`/`atol`, not by an output grid. The defaults
    were 1e-8 / 1e-11 until 2026-09-10; measured on the Macoma site case they cost 4 073 steps and
    8.6 s, and loosening to **1e-6 / 1e-9** cut that to 1 762 steps and 3.0 s while moving the
    dilution by at most 4e-6 relative anywhere on the trajectory and the end time by nothing
    (1e-5 / 1e-8: 985 steps, 1.6 s, 5e-5; 1e-4: 584 steps, 0.9 s, 4e-4). The parity rows resolve
    0.3 %, three orders coarser than the 1e-6 drift, and every ledger row was re-derived at the
    new default before it landed (PLAN.md section 7, item 8). Pass the old values back for a
    convergence check; the answer should not change in any printed digit.

    Stops on: the surface or the seabed being touched by the plume *edge* (the criterion
    measured in case06/case10, `depth - radius <= 0` and `depth + radius >= bottom`), the
    dilution limit, or `max_time`. Trapping and velocity reversal are recorded as events but
    do **not** stop the integration, because the exe's max-rise-or-fall switch decides that
    and the default of 2 allows the plume to overshoot and settle back.

    `forced` selects the closure. The default `Um3Entrainment()` is the one that reproduces
    the exe; passing a `ProjectedAreaEntrainment` instead selects the historical path, which
    sums the published eqs 33-41 onto a separate Taylor term and over-predicts in a
    cross-flow. `relative_shear` applies only to that path, and drives the Taylor term with
    `alpha |V|` when false. Neither knob changes anything without an ambient current.

    `merging` selects the three angle conventions of eqs 51-56. The default is what the exe
    does; every other setting is a **control** for rows 178-180 and not a mode to run in. It
    changes nothing on a single port, or before neighbouring plumes touch.
    """
    state0, geometry = initial_state(case)
    ambient = AmbientProfileView(case.ambient, equation_of_state=case.near_field.equation_of_state)
    forced = forced if forced is not None else Um3Entrainment()
    choices = merging if merging is not None else AS_THE_EXE_DOES
    rhs = _make_rhs(case, geometry, ambient, forced, relative_shear, choices)
    ceiling = max_dilution if max_dilution is not None else case.near_field.max_dilution
    bottom = case.diffuser.bottom_depth

    def _radius(state: LcvState) -> float:
        return _merged_geometry(
            case,
            geometry,
            state.mass,
            state.density(equation_of_state=case.near_field.equation_of_state),
            state.speed,
            state.velocity,
            choices,
        )[0]

    def surface(_t: float, vector: NDArray[np.float64]) -> float:
        state = unpack(vector)
        return state.depth - _radius(state)

    def seabed(_t: float, vector: NDArray[np.float64]) -> float:
        state = unpack(vector)
        return bottom - (state.depth + _radius(state))

    def dilution_limit(_t: float, vector: NDArray[np.float64]) -> float:
        return float(geometry.dilution(vector[0])) - ceiling

    def trapping(_t: float, vector: NDArray[np.float64]) -> float:
        """`rho_j - rho_a`, zero at neutral buoyancy -- the exe's "Plume traps"."""
        state = unpack(vector)
        return state.density(equation_of_state=case.near_field.equation_of_state) - float(
            ambient.sample(state.depth).density
        )

    def reversal(_t: float, vector: NDArray[np.float64]) -> float:
        """Vertical velocity, zero at a maximum rise **or** fall."""
        return float(vector[3] / vector[0])

    def nonphysical(_t: float, vector: NDArray[np.float64]) -> float:
        """Stop before the state becomes unusable, rather than failing in the EOS.

        A wrong entrainment closure can drive salinity negative within a few hundred
        steps -- weighting the projected area's end cap does exactly that. Catching it
        here turns a confusing "salinity must be non-negative" from deep inside the
        equation of state into a clear termination reason.
        """
        mass = vector[0]
        if mass <= 0.0:
            return -1.0
        return float(vector[5] / mass)

    for event in (surface, seabed, dilution_limit, nonphysical):
        event.terminal = True  # type: ignore[attr-defined]
        event.direction = -1.0  # type: ignore[attr-defined]
    dilution_limit.direction = 1.0  # type: ignore[attr-defined]
    # Surface contact stops the run only when the GUI's box is ticked. case14 sails straight
    # through its own surface hit and keeps oscillating; case13, the byte-identical project,
    # stops dead on it. See terminate.py -- the flag is not in the file.
    surface.terminal = case.near_field.stop_at_surface  # type: ignore[attr-defined]
    seabed.terminal = case.near_field.stop_at_bottom  # type: ignore[attr-defined]
    # Trapping and reversal are *counted*, not terminal: the switch decides which one ends
    # the run, and that cannot be known until enough of them have happened.
    for event in (trapping, reversal):
        event.terminal = False  # type: ignore[attr-defined]
        event.direction = 0.0  # type: ignore[attr-defined]

    solution = solve_ivp(
        rhs,
        (0.0, max_time),
        state0.pack(),
        method="LSODA",
        dense_output=True,
        events=(surface, seabed, dilution_limit, nonphysical, trapping, reversal),
        rtol=rtol,
        atol=atol,
    )
    if not solution.success:
        raise RuntimeError(f"near-field integration failed: {solution.message}")

    hard = (
        TerminationReason.SURFACE,
        TerminationReason.SEABED,
        TerminationReason.DILUTION,
        TerminationReason.NON_PHYSICAL,
    )
    events: dict[str, float] = {}
    for name, times in zip(hard, solution.t_events[:4], strict=True):
        if times.size:
            events[str(name)] = float(times[0])

    oscillations = sorted(
        [OscillationEvent(float(t), OscillationKind.TRAP) for t in solution.t_events[4]]
        + [OscillationEvent(float(t), OscillationKind.REVERSAL) for t in solution.t_events[5]]
    )
    # Every crossing is *reported*, but a surface crossing only *stops* the near field when
    # the flag is set -- and the archive shows the exe usually sailing straight through one.
    stopping = {
        name: when
        for name, when in events.items()
        if (name != str(TerminationReason.SURFACE) or case.near_field.stop_at_surface)
        and (name != str(TerminationReason.SEABED) or case.near_field.stop_at_bottom)
    }
    boundary_reason = min(stopping, key=lambda key: stopping[key]) if stopping else None
    end_time, reason = near_field_end(
        oscillations,
        case.near_field.max_rise_or_fall,
        boundary_time=stopping[boundary_reason] if boundary_reason else None,
        boundary_reason=TerminationReason(boundary_reason) if boundary_reason else None,
        fallback=float(solution.t[-1]),
        fallback_reason=TerminationReason.TIME_LIMIT,
    )
    return NearFieldSolution(
        case=case,
        geometry=geometry,
        solution=solution,
        reason=str(reason),
        events=events,
        oscillations=tuple(oscillations),
        end_time=end_time,
        merging=choices,
    )


def state_at(solution: NearFieldSolution, time: float) -> LcvState:
    """Unpack the state at one instant -- convenient in tests."""
    return unpack(np.asarray(solution.solution.sol(time), dtype=np.float64))  # type: ignore[attr-defined]
