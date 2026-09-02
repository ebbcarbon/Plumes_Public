"""The Lagrangian Control Volume state, its geometry, and the port initial conditions.

The manual (§2.3.1) integrates four conservation laws over a control volume that moves with
the plume, with top-hat properties inside and ambient outside:

    eq 2  dm/dt        = -rho_a A_p . U_a  +  rho_a A_T beta_T      (continuity)
    eq 3  d(m U_j)/dt  =  U_a dm/dt  -  m (rho_a - rho_j)/rho_j g   (momentum, no drag)
    eq 4  d(m T_j)/dt  =  T_a dm/dt                                 (heat)
    eq 5  d(m S_j)/dt  =  S_a dm/dt                                 (salt)

so the natural integration variables are the *conserved* quantities `m`, `m U_j`, `m T_j`
and `m S_j`, plus position. This module holds that vector and the geometry needed to
evaluate the right-hand sides; `entrainment.py` supplies `A_p` and `beta_T`, and
`solver.py` steps it.

Geometry: the element is a cylinder of radius `b` and thickness `h`, so
`m = rho_j pi b^2 h`. That leaves `b` and `h` underdetermined by `m` alone, and the manual
flags the gap explicitly -- "it is necessary to express mathematically how the length of the
element changes in response to changes in other plume properties" -- then defers to Frick
(1984), which is not in the repo.

**Measured instead, from `case16/test19`** (494 consecutive steps at output interval 1, the
only trace with `Time`, `P-Den` and position together):

    h  proportional to  |U_j|

i.e. the steady-plume stretching relation, where each element takes the same time to pass a
station so its length scales with how fast it is going. The test is that
`b^2 rho_j |U_j| / D` should then be constant along a run. It is, to a coefficient of
variation of 2-4 %, with the mean stable to 2 % across the whole pre-merge trajectory
(6.345, 6.342, 6.395, 6.475 e-2 over four consecutive windows) -- and the residual scatter
is dominated by differencing positions printed to three decimals. The alternative, constant
`h`, varies by a factor of **15** over the same span.

The consequence is worth stating plainly: **`b` is derived, not integrated.** Given `m`,
`rho_j` and `|U_j|`,

    b = sqrt( m |U_0| / (rho_j pi h_0 |U_j|) )

with `h_0` and the effluent mass `m_e` fixed together by the port conditions. Only their
ratio enters, so the arbitrary choice of element length at the port cancels.

**The Taylor coefficient is confirmed to be the value entered.** With the ambient current
set to zero, eq 2's forced term `-rho_a A_p . U_a` vanishes identically, leaving only Taylor
entrainment -- which the manual fully specifies. Reducing eq 2 to a specific rate, in which
the element thickness cancels,

    d(ln D)/dt = 2 alpha (rho_a / rho_j) |U_j| / b

and solving for `alpha` on the zero-current runs gives **0.0967 +- 0.0006** (test22, 25
ports) and **0.0991 +- 0.0013** (test23, single port) against the 0.1 in the project file.
Over the same rows the measured thickness constant sits within 1 % of its closed form. So
Taylor entrainment, the `h` law, the initial radius and the equation of state are all
validated together, with `A_p` excluded by construction.

**The contraction coefficient sets the vena contracta**, measured from test23 against
test25, which differ only in it:

    initial jet area = c * port area,   so   b_0 = (d_port / 2) sqrt(c),  |U_0| = Q/(n c A)

    c = 1.00  ->  step-1 diameter 0.013     (0.0127)
    c = 0.61  ->  step-1 diameter 0.010     (0.0127 * 0.781)

Those two combine to leave `b_0^2 rho_e |U_0| = rho_e Q / (n pi)` **independent of `c`** --
which is exactly what the pair shows, their measured constants agreeing to 0.25 % across a
64 % change in `c`. Read the other way, that closed form recovers each archived run's flow
rate to about 1 %, and it is how the two rounding traps below were caught.

⚠️ **The `.dat` diffuser echo rounds to two decimals.** Its `P-dia` of "0.01" is 0.0127 and
its `Ttl-flo` of "0.01" in (cms) is 0.005 -- both the Macoma baseline. Only the *simulation
results* table prints three decimals. Read inputs from the `.prj`, never from the echo.

Coordinates, confirmed against the traces:

- `x`, `y` horizontal, `z` **elevation** -- negative below the surface, matching the sign of
  the `.dat` `Depth` column (a 2 m port prints -2.000). The seabed is at
  `-(port_depth + port_elevation)`.
- Bearings are `(cos theta, sin theta)`, **not** compass bearings. test19's ambient current
  at 90 deg drives the plume to +y while its 175 deg jet drives it to -x, which fixes both
  the axis convention and the rotation sense.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from plumes2.config import Case
from plumes2.seawater import GRAVITY as _GRAVITY
from plumes2.seawater import EquationOfState, density_of

__all__ = [
    "GRAVITY",
    "STATE_SIZE",
    "LcvGeometry",
    "LcvState",
    "exit_speed",
    "horizontal_unit",
    "initial_radius",
    "initial_state",
    "unpack",
    "velocity_vector",
]

#: Standard gravity, m/s^2. **Re-exported, not redefined** -- `seawater` owns it, because it is
#: the lower-level module and its equation of state is where the value first matters. Two
#: independent definitions of the same constant is the classic way for two modules to drift apart
#: while every test still passes.
GRAVITY = _GRAVITY

#: Length of the packed state vector: m, m*U (3), m*T, m*S, position (3).
STATE_SIZE = 9


def horizontal_unit(bearing_degrees: float) -> NDArray[np.float64]:
    """`(cos, sin)` of a bearing, as a 2-vector in the x-y plane.

    Not a compass bearing: 0 deg is +x and 90 deg is +y. Established from test19, whose
    90 deg current drives the plume to +y and whose 175 deg jet drives it to -x.
    """
    radians = math.radians(bearing_degrees)
    return np.array([math.cos(radians), math.sin(radians)], dtype=np.float64)


def velocity_vector(
    speed: float, vertical_degrees: float, horizontal_degrees: float
) -> NDArray[np.float64]:
    """A 3-vector from a speed and the two port angles.

    `vertical_degrees` is positive upward, so a 45 deg port fired upward has a positive `z`
    component; `horizontal_degrees` follows `horizontal_unit`.
    """
    vertical = math.radians(vertical_degrees)
    horizontal_part = speed * math.cos(vertical) * horizontal_unit(horizontal_degrees)
    return np.array(
        [horizontal_part[0], horizontal_part[1], speed * math.sin(vertical)], dtype=np.float64
    )


@dataclass(frozen=True, slots=True)
class LcvGeometry:
    """The invariants that fix the element's radius from its mass.

    `radius_constant` is `b^2 rho_j |U_j| / m`, held fixed by the `h` proportional to
    `|U_j|` law. It is evaluated once from the port conditions and then reused, which is
    what makes `b` an algebraic function of the state rather than another ODE.
    """

    #: `b_0^2 rho_e |U_0| / m_e`, m^2 kg/m^3 m/s per kg -- see the module docstring.
    radius_constant: float
    #: The effluent mass carried by the element, constant by assumption (manual p. 19:
    #: "the effluent mass in the Lagrangian element at each time step remains constant").
    effluent_mass: float
    #: Element thickness at the port, m. Arbitrary; only `h_0` with `m_e` matters.
    initial_thickness: float

    def radius(
        self,
        mass: NDArray[np.float64] | float,
        plume_density: NDArray[np.float64] | float,
        speed: NDArray[np.float64] | float,
    ) -> NDArray[np.float64]:
        """`b` from the state, by inverting `b^2 rho_j |U_j| / m = radius_constant`."""
        mass_arr = np.asarray(mass, dtype=np.float64)
        speed_arr = np.asarray(speed, dtype=np.float64)
        density_arr = np.asarray(plume_density, dtype=np.float64)
        if np.any(speed_arr <= 0.0):
            raise ValueError(
                "the element radius is undefined at zero speed: the h proportional to "
                "|U_j| law divides by the plume speed"
            )
        return np.asarray(np.sqrt(self.radius_constant * mass_arr / (density_arr * speed_arr)))

    def thickness(self, mass: float, plume_density: float, speed: float) -> float:
        """`h` from `m = rho_j pi b^2 h`."""
        b = float(self.radius(mass, plume_density, speed))
        return float(mass / (plume_density * math.pi * b * b))

    def dilution(self, mass: NDArray[np.float64] | float) -> NDArray[np.float64]:
        """`D = m / m_e` -- the flux-averaged dilution the exe reports as `Dilutn`."""
        return np.asarray(np.asarray(mass, dtype=np.float64) / self.effluent_mass)


@dataclass(frozen=True, slots=True)
class LcvState:
    """An unpacked LCV state at one instant."""

    mass: float
    velocity: NDArray[np.float64]
    temperature: float
    salinity: float
    position: NDArray[np.float64]

    @property
    def speed(self) -> float:
        return float(np.linalg.norm(self.velocity))

    @property
    def depth(self) -> float:
        """Depth below the surface, positive downward (the opposite sign to `z`)."""
        return -float(self.position[2])

    def density(
        self,
        pressure_decibars: float = 0.0,
        *,
        equation_of_state: EquationOfState = EquationOfState.EOS80,
    ) -> float:
        """Plume density, kg/m3.

        ⚠️ `pressure_decibars` is ignored under `KNUDSEN`, which has no pressure term -- see
        `plumes2.seawater.density_of`. Callers in the solver pass zero anyway, because the exe's
        EOS is a one-atmosphere formula and the 3rd edition says so outright.
        """
        return float(
            density_of(
                self.salinity,
                self.temperature,
                pressure_decibars,
                equation_of_state=equation_of_state,
            )
        )

    def pack(self) -> NDArray[np.float64]:
        return np.concatenate(
            (
                [self.mass],
                self.mass * self.velocity,
                [self.mass * self.temperature, self.mass * self.salinity],
                self.position,
            )
        )


def unpack(vector: NDArray[np.float64]) -> LcvState:
    """Recover the physical state from the packed conserved quantities."""
    if vector.shape[-1] != STATE_SIZE:
        raise ValueError(f"expected a state vector of length {STATE_SIZE}, got {vector.shape}")
    mass = float(vector[0])
    if mass <= 0.0:
        raise ValueError("element mass must stay positive")
    return LcvState(
        mass=mass,
        velocity=np.asarray(vector[1:4], dtype=np.float64) / mass,
        temperature=float(vector[4]) / mass,
        salinity=float(vector[5]) / mass,
        position=np.asarray(vector[6:9], dtype=np.float64),
    )


def initial_radius(case: Case) -> float:
    """`b_0 = (d_port / 2) sqrt(c)`, m -- the vena contracta.

    The contraction coefficient `c` shrinks the jet's *area* to `c` times the port area, so
    the radius carries `sqrt(c)`. Measured directly from the test23/test25 pair, which
    differ only in `c` (single port, zero ambient current, output interval 1):

        c = 1.00   step-1 plume diameter 0.013      0.0127        -> prints 0.013
        c = 0.61   step-1 plume diameter 0.010      0.0127*0.781  -> prints 0.010

    Note this also corrects the port diameter: the `.dat` diffuser echo prints `P-dia` to
    **two** decimals, so its "0.01" is 0.0127 rounded -- the Macoma baseline all along. The
    same two-decimal trap applies to `Ttl-flo` in (cms), whose "0.01" is 0.005.
    """
    return (case.diffuser.port_diameter / 2.0) * math.sqrt(
        case.near_field.contraction_coefficient
    )


def exit_speed(case: Case) -> float:
    """Port exit speed, m/s: `Q / (n c A_port)`.

    The flow passes through the *contracted* area, so `c` raises the speed by `1/c`. Both
    halves of the contraction are confirmed by test23 against test25: the initial radius
    scales as `sqrt(c)` and the speed as `1/c`, which together leave
    `b_0^2 rho_e |U_0| = rho_e Q / (n pi)` **independent of `c`**. That invariant is what the
    data shows -- the two runs' measured thickness constants agree to 0.25 % despite a 64 %
    change in `c` -- and it recovers each archived run's flow to within about 1 %.
    """
    diffuser = case.diffuser
    contracted_area = (
        math.pi * initial_radius(case) ** 2
    )  # == c * pi * (d/2)**2, by construction
    return case.effluent.flow / (diffuser.n_ports * contracted_area)


def initial_state(
    case: Case, *, element_thickness: float | None = None
) -> tuple[LcvState, LcvGeometry]:
    """The ZFE / port initial conditions, and the geometry invariants they fix.

    `element_thickness` sets the arbitrary initial element length; it cancels out of every
    reported quantity, and defaults to the initial radius so the element starts roughly
    isotropic. The initial radius carries the contraction coefficient -- see
    `initial_radius`.
    """
    diffuser = case.diffuser
    effluent = case.effluent
    radius = initial_radius(case)
    thickness = float(element_thickness) if element_thickness is not None else radius
    speed = exit_speed(case)
    # The port's initial mass must use the same equation of state as the trajectory, or
    # `Dilutn = m / m_e` is a ratio of two different densities from its first step.
    effluent_density = float(
        density_of(
            effluent.salinity,
            effluent.temperature,
            0.0,
            equation_of_state=case.near_field.equation_of_state,
        )
    )
    effluent_mass = effluent_density * math.pi * radius * radius * thickness

    state = LcvState(
        mass=effluent_mass,
        velocity=velocity_vector(speed, diffuser.vertical_angle, diffuser.horizontal_angle),
        temperature=effluent.temperature,
        salinity=effluent.salinity,
        position=np.array(
            [diffuser.x_position, diffuser.y_position, -diffuser.port_depth], dtype=np.float64
        ),
    )
    geometry = LcvGeometry(
        radius_constant=radius * radius * effluent_density * speed / effluent_mass,
        effluent_mass=effluent_mass,
        initial_thickness=thickness,
    )
    return state, geometry
