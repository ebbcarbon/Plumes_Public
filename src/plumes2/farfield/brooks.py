"""Brooks (1960) far-field dilution.

Fully specified by the manual (§2.3.2, equations 10-16), unlike the near field. The
wastefield spreads laterally by turbulent diffusion while being advected at the ambient
current; vertical spreading is neglected. With

    beta = 12 * eps_0 / (u * w_0)          (eq 13, dimensionless)
    eps_0 = alpha * w_0 ** (4/3)           (section 5.2.4; alpha default 3e-4)

the three eddy-diffusivity laws are

    ==========  =====================================  ===================================
    law         width                                  centre concentration
    ==========  =====================================  ===================================
    constant    w/w0 = (1 + 2 b X)**0.5                erf( sqrt( 3 / (4 b X) ) )
    linear      w/w0 = 1 + b X                         erf( sqrt( 1.5 / ((1+b X)**2 - 1) ) )
    4/3 power   w/w0 = (1 + (2/3) b X)**1.5            erf( sqrt( 1.5 / ((1+(2/3) b X)**3 - 1) ) )
    ==========  =====================================  ===================================

where ``X = x / w_0`` and ``x`` is measured **from the start of the far field**, not from
the outfall.

⚠️ **The manual's eq 11 prints the linear width as ``1 + 2 b X`` and that is a typo.** The
exe prints ``1 + b X`` (case50, ledger row 280b: 1.7e-4 on every printed width under
``Linearly Varying Eddy Diffusivity``, where the manual's form is 57-87 % high), and the
derivation agrees -- with ``eps = eps_0 w/w_0`` and ``w = sqrt(12) sigma``, ``d(w^2)/dt =
24 eps`` integrates to ``w = w_0 + 12 eps_0 x/(u w_0) = w_0 (1 + b X)``. The erf form beside
it, ``(1 + b X)^2 - 1``, already carried the right factor, which is why the linear
*dilution* matched the exe before the width did. The constant and 4/3 laws are the exe's
to 1.7e-4 and 1e-5 respectively (rows 280, 116).

The far-field dilution factor is ``FF = C_0 / C = 1 / erf(...)``, and the total
is ``D_total = D_nearfield * FF``. First-order decay multiplies the concentration by
``exp(-k t)`` with ``t = x / u``.

The ambient is taken at a single depth -- the manual is explicit that "the model determines
those conditions based on the depth of the plume when the initial dilution ends (surface or
plume trapping depth)".

Note ``FF -> inf`` as ``x -> 0`` because ``erf(inf) = 1`` gives ``FF = 1``: at zero distance
the far field has not diluted anything yet, so ``FF = 1`` exactly. The implementation
returns 1 there rather than dividing by an erf of infinity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import erf

from plumes2.config import EddyDiffusivityLaw

__all__ = [
    "BrooksParameters",
    "beta",
    "dilution_factor",
    "initial_eddy_diffusivity",
    "width",
]

#: Below this value of `beta * x / w0` the erf argument overflows; FF is 1 to within
#: double precision anyway.
_TINY = 1e-300


def initial_eddy_diffusivity(initial_width: ArrayLike, alpha: ArrayLike = 3.0e-4) -> NDArray:
    """`eps_0 = alpha * w_0 ** (4/3)`, m2/s.

    `alpha` ranges 1e-4 to 5e-4 m^(2/3)/s; 3e-4 is the documented default.
    """
    w0 = np.asarray(initial_width, dtype=np.float64)
    return np.asarray(np.asarray(alpha, dtype=np.float64) * w0 ** (4.0 / 3.0))


def beta(initial_width: ArrayLike, current_speed: ArrayLike, alpha: ArrayLike = 3.0e-4) -> NDArray:
    """`beta = 12 eps_0 / (u w_0)` (eq 13), dimensionless."""
    w0 = np.asarray(initial_width, dtype=np.float64)
    u = np.asarray(current_speed, dtype=np.float64)
    if np.any(w0 <= 0):
        raise ValueError("initial wastefield width must be positive")
    if np.any(u <= 0):
        raise ValueError("ambient current speed must be positive for Brooks far-field")
    return np.asarray(12.0 * initial_eddy_diffusivity(w0, alpha) / (u * w0))


@dataclass(frozen=True, slots=True)
class BrooksParameters:
    """Everything a Brooks run needs, resolved to SI."""

    initial_width: float
    initial_dilution: float
    current_speed: float
    alpha: float = 3.0e-4
    law: EddyDiffusivityLaw = EddyDiffusivityLaw.FOUR_THIRDS
    #: First-order decay, 1/day as the exe stores it; converted internally.
    decay_per_day: float = 0.0

    @property
    def beta(self) -> float:
        return float(beta(self.initial_width, self.current_speed, self.alpha))

    @property
    def initial_eddy_diffusivity(self) -> float:
        return float(initial_eddy_diffusivity(self.initial_width, self.alpha))

    def travel_time(self, distance: ArrayLike) -> NDArray:
        """Seconds to travel `distance` metres at the ambient current."""
        return np.asarray(np.asarray(distance, dtype=np.float64) / self.current_speed)

    def width(self, distance: ArrayLike) -> NDArray:
        return width(distance, self.initial_width, self.beta, self.law)

    def dilution_factor(self, distance: ArrayLike) -> NDArray:
        return dilution_factor(
            distance,
            self.initial_width,
            self.beta,
            self.law,
            decay_per_day=self.decay_per_day,
            current_speed=self.current_speed,
        )

    def total_dilution(self, distance: ArrayLike) -> NDArray:
        """`D_nearfield * FF`."""
        return np.asarray(self.initial_dilution * self.dilution_factor(distance))


def _scaled(distance: ArrayLike, initial_width: float, beta_value: float) -> NDArray:
    """`beta * x / w0`, the single dimensionless group the laws depend on."""
    x = np.asarray(distance, dtype=np.float64)
    if np.any(x < 0):
        raise ValueError("far-field distance must be non-negative")
    return np.asarray(beta_value * x / initial_width)


def width(
    distance: ArrayLike,
    initial_width: float,
    beta_value: float,
    law: EddyDiffusivityLaw = EddyDiffusivityLaw.FOUR_THIRDS,
) -> NDArray:
    """Wastefield width at `distance` from the start of the far field (eqs 10-12)."""
    bx = _scaled(distance, initial_width, beta_value)
    if law is EddyDiffusivityLaw.CONSTANT:
        growth = np.sqrt(1.0 + 2.0 * bx)
    elif law is EddyDiffusivityLaw.LINEAR:
        # Not the manual's `1 + 2 bx` -- see the module docstring and ledger row 280b.
        growth = 1.0 + bx
    elif law is EddyDiffusivityLaw.FOUR_THIRDS:
        growth = (1.0 + (2.0 / 3.0) * bx) ** 1.5
    else:  # pragma: no cover - exhaustive
        raise ValueError(f"unknown eddy-diffusivity law: {law}")
    return np.asarray(initial_width * growth)


def _erf_argument(bx: NDArray, law: EddyDiffusivityLaw) -> NDArray:
    """The argument of erf in eqs 14-16, guarded at x = 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        if law is EddyDiffusivityLaw.CONSTANT:
            denominator = 4.0 * bx
            argument = np.sqrt(np.divide(3.0, np.maximum(denominator, _TINY)))
        elif law is EddyDiffusivityLaw.LINEAR:
            denominator = (1.0 + bx) ** 2 - 1.0
            argument = np.sqrt(np.divide(1.5, np.maximum(denominator, _TINY)))
        elif law is EddyDiffusivityLaw.FOUR_THIRDS:
            denominator = (1.0 + (2.0 / 3.0) * bx) ** 3 - 1.0
            argument = np.sqrt(np.divide(1.5, np.maximum(denominator, _TINY)))
        else:  # pragma: no cover - exhaustive
            raise ValueError(f"unknown eddy-diffusivity law: {law}")
    return np.asarray(argument)


def dilution_factor(
    distance: ArrayLike,
    initial_width: float,
    beta_value: float,
    law: EddyDiffusivityLaw = EddyDiffusivityLaw.FOUR_THIRDS,
    *,
    decay_per_day: float = 0.0,
    current_speed: float | None = None,
) -> NDArray:
    """Far-field dilution factor `FF = C_0 / C` (eqs 14-16).

    `FF` is 1 at zero distance and grows with distance. Decay, if any, *reduces* the
    concentration further and therefore *increases* the apparent dilution factor.
    """
    bx = _scaled(distance, initial_width, beta_value)
    fraction = erf(_erf_argument(bx, law))
    # erf -> 1 as x -> 0, so FF -> 1; clip guards the exact-zero case.
    factor = 1.0 / np.clip(fraction, np.finfo(np.float64).tiny, 1.0)

    if decay_per_day:
        if current_speed is None:
            raise ValueError("current_speed is required when a decay rate is given")
        seconds = np.asarray(distance, dtype=np.float64) / current_speed
        factor = factor * np.exp(decay_per_day / 86400.0 * seconds)
    return np.asarray(factor)
