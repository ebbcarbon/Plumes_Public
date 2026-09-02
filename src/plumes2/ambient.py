"""Ambient conditions as continuous functions of depth.

The exe stores the receiving water as a handful of tabulated levels — 6 or 7 in every
reference case — and the plume needs values at arbitrary depths in between. This module
interpolates them, and is explicit about what happens **outside** the tabulated range,
because that is where the exe demonstrably misbehaves.

Extrapolation matters more than it sounds:

* Every Macoma project puts the seabed at 17 m (2 m port on a 15 m riser) against an
  ambient profile that stops at 15 m, so the bottom 2 m are always extrapolated.
* case09's plume rose above the top of its 1-4 m ambient chemistry profile and the
  transport broke completely — TA fell below the ambient endmember, which conservative
  mixing cannot do, and every state variable went NaN shortly after.

So the default policy is to **hold the endpoint value** (clamp) rather than continue the
last gradient, which cannot invent unphysical values, and :class:`AmbientProfileView`
records whether any query was extrapolated so a caller can report it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.config import AmbientChemistryLevel, AmbientDOLevel, AmbientProfile
from plumes2.seawater import EquationOfState, density_of

__all__ = [
    "AmbientProfileView",
    "AmbientSample",
    "ExtrapolationPolicy",
]


class ExtrapolationPolicy(StrEnum):
    """What to do for depths outside the tabulated range."""

    #: Hold the nearest endpoint value. Safe: cannot produce unphysical numbers.
    CLAMP = "clamp"
    #: Continue the end gradient. Can produce negative salinity, and is what appears to
    #: have poisoned case09.
    LINEAR = "linear"
    #: Refuse. Useful in tests and for strict batch runs.
    RAISE = "raise"


@dataclass(frozen=True, slots=True)
class AmbientSample:
    """Ambient conditions at one depth, SI."""

    depth: float
    current_speed: float
    current_direction: float
    salinity: float
    temperature: float
    background_pollutant: float
    decay_rate: float
    farfield_speed: float
    farfield_direction: float
    dispersion_alpha: float
    density: float
    #: True when the depth fell outside the tabulated range.
    extrapolated: bool = False


_LEVEL_FIELDS = (
    "current_speed",
    "current_direction",
    "salinity",
    "temperature",
    "background_pollutant",
    "decay_rate",
    "farfield_speed",
    "farfield_direction",
    "dispersion_alpha",
)


def _interpolate(
    depths: NDArray[np.float64],
    values: NDArray[np.float64],
    query: NDArray[np.float64],
    policy: ExtrapolationPolicy,
    what: str,
) -> NDArray[np.float64]:
    """Piecewise-linear interpolation with an explicit out-of-range policy."""
    if depths.size == 1:
        return values[0] * np.ones_like(query)

    outside = (query < depths[0]) | (query > depths[-1])
    if policy is ExtrapolationPolicy.RAISE and bool(np.any(outside)):
        offenders = np.unique(np.atleast_1d(query)[np.atleast_1d(outside)])
        raise ValueError(
            f"{what}: depth(s) {offenders.tolist()} lie outside the tabulated range "
            f"{depths[0]:g}-{depths[-1]:g} m and the policy is 'raise'"
        )

    # np.interp clamps to the endpoint values, which is exactly the CLAMP policy.
    # LINEAR is handled by the caller, via _linear_extrapolate.
    return np.asarray(np.interp(query, depths, values), dtype=np.float64)


def _linear_extrapolate(
    depths: NDArray[np.float64],
    values: NDArray[np.float64],
    query: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Continue the end gradients beyond the tabulated range."""
    result = np.interp(query, depths, values)
    if depths.size < 2:
        return np.asarray(result, dtype=np.float64)
    low_slope = (values[1] - values[0]) / (depths[1] - depths[0])
    high_slope = (values[-1] - values[-2]) / (depths[-1] - depths[-2])
    result = np.where(query < depths[0], values[0] + low_slope * (query - depths[0]), result)
    result = np.where(query > depths[-1], values[-1] + high_slope * (query - depths[-1]), result)
    return result


@dataclass(slots=True)
class AmbientProfileView:
    """Interpolating view over an :class:`~plumes2.config.AmbientProfile`."""

    profile: AmbientProfile
    policy: ExtrapolationPolicy = ExtrapolationPolicy.CLAMP
    #: Which density formula the derived densities use. `KNUDSEN` is the exe's; see
    #: `plumes2.seawater.knudsen_sigma_t`. The default keeps the modern standard, and the
    #: solver passes `case.near_field.equation_of_state` in so the plume and the ambient can
    #: never be evaluated under *different* equations of state -- which would put a spurious
    #: offset straight into the buoyancy, the one place it is least affordable.
    equation_of_state: EquationOfState = EquationOfState.EOS80
    #: Set whenever a query has fallen outside the tabulated range.
    extrapolation_seen: bool = field(default=False, init=False)

    # --- hydrodynamics -----------------------------------------------------------------
    @property
    def depths(self) -> NDArray[np.float64]:
        return np.array([level.depth for level in self.profile.levels], dtype=np.float64)

    def _column(self, name: str) -> NDArray[np.float64]:
        return np.array([getattr(level, name) for level in self.profile.levels], dtype=np.float64)

    def _lookup(self, name: str, depth: ArrayLike) -> NDArray[np.float64]:
        query = np.asarray(depth, dtype=np.float64)
        depths = self.depths
        values = self._column(name)
        if depths.size > 1 and bool(np.any(query < depths[0]) or np.any(query > depths[-1])):
            self.extrapolation_seen = True
        if self.policy is ExtrapolationPolicy.LINEAR:
            return _linear_extrapolate(depths, values, query)
        return _interpolate(depths, values, query, self.policy, f"ambient {name}")

    def salinity(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._lookup("salinity", depth)

    def temperature(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._lookup("temperature", depth)

    def current_speed(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._lookup("current_speed", depth)

    def current_direction(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._lookup("current_direction", depth)

    def dispersion_alpha(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._lookup("dispersion_alpha", depth)

    def density(self, depth: ArrayLike) -> NDArray[np.float64]:
        """Ambient sigma-t density, from the interpolated salinity and temperature."""
        return density_of(
            self.salinity(depth),
            self.temperature(depth),
            equation_of_state=self.equation_of_state,
        )

    def sample(self, depth: float) -> AmbientSample:
        """Every ambient field at one depth, plus the derived density."""
        depths = self.depths
        outside = bool(depths.size > 1 and (depth < depths[0] or depth > depths[-1]))
        values = {name: float(self._lookup(name, depth)) for name in _LEVEL_FIELDS}
        return AmbientSample(
            depth=depth,
            density=float(
                density_of(
                    values["salinity"],
                    values["temperature"],
                    equation_of_state=self.equation_of_state,
                )
            ),
            extrapolated=outside,
            **values,
        )

    # --- chemistry ---------------------------------------------------------------------
    def _chem_lookup(self, name: str, depth: ArrayLike) -> NDArray[np.float64]:
        levels: list[AmbientChemistryLevel] = self.profile.chemistry
        if not levels:
            raise ValueError("this profile carries no ambient chemistry")
        query = np.asarray(depth, dtype=np.float64)
        depths = np.array([level.depth for level in levels], dtype=np.float64)
        raw = [getattr(level, name) for level in levels]
        if any(value is None for value in raw):
            raise ValueError(
                f"ambient chemistry column {name!r} is blank at one or more levels, so it "
                "cannot be interpolated. The exe derives pH from TA and DIC rather than "
                "reading it (reference_cases/case03), so blanks are expected there."
            )
        values = np.array(raw, dtype=np.float64)
        if depths.size > 1 and bool(np.any(query < depths[0]) or np.any(query > depths[-1])):
            self.extrapolation_seen = True
        if self.policy is ExtrapolationPolicy.LINEAR:
            return _linear_extrapolate(depths, values, query)
        return _interpolate(depths, values, query, self.policy, f"ambient chemistry {name}")

    def total_alkalinity(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._chem_lookup("total_alkalinity", depth)

    def dic(self, depth: ArrayLike) -> NDArray[np.float64]:
        return self._chem_lookup("dic", depth)

    # --- dissolved oxygen ---------------------------------------------------------------
    def dissolved_oxygen(self, depth: ArrayLike) -> NDArray[np.float64]:
        levels: list[AmbientDOLevel] = self.profile.dissolved_oxygen
        if not levels:
            raise ValueError("this profile carries no dissolved-oxygen data")
        query = np.asarray(depth, dtype=np.float64)
        depths = np.array([level.depth for level in levels], dtype=np.float64)
        values = np.array([level.dissolved_oxygen for level in levels], dtype=np.float64)
        if depths.size > 1 and bool(np.any(query < depths[0]) or np.any(query > depths[-1])):
            self.extrapolation_seen = True
        if self.policy is ExtrapolationPolicy.LINEAR:
            return _linear_extrapolate(depths, values, query)
        return _interpolate(depths, values, query, self.policy, "ambient dissolved oxygen")
