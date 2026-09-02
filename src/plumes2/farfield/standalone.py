"""The independent far-field calculator (manual §5.2.9).

A standalone Brooks run for wastefields that never had a near field -- diffuse or
multi-source discharges. Because the user supplies the initial width and dilution
*directly*, this path involves **no near-field transition adjustment**, which made it the
cleanest possible test of the Brooks implementation.

**That test passed exactly.** Against `reference_cases/case17_independent_farfield` -- the
manual's own worked example -- width, dilution and travel time all agree to ~5e-6 relative,
which is exact to the three decimals the exe prints. Brooks is therefore *confirmed*, and the
up-to-9 % dilution shortfall seen in the *integrated* runs lies entirely in the near-field to
far-field handoff, not in these equations.

The manual fully specifies the output stepping, and it is not user-controllable:

> The calculator divides the user-defined distance to the mixing zone boundary into 25
> steps, and 3 additional steps beyond the mixing zone boundary are included in the output.

So a 200 m mixing zone prints every 8 m and ends at 224 m.

The initial location may be as small as 0.001 m but **not zero**.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from plumes2.config import EddyDiffusivityLaw
from plumes2.farfield.brooks import BrooksParameters

__all__ = ["STEPS_BEYOND_MIXING_ZONE", "STEPS_TO_MIXING_ZONE", "independent_farfield"]

#: Fixed by the exe, per manual §5.2.9.
STEPS_TO_MIXING_ZONE = 25
STEPS_BEYOND_MIXING_ZONE = 3


@dataclass(frozen=True, slots=True)
class StandaloneRequest:
    """Inputs to the independent far-field calculator, SI."""

    initial_dilution: float
    initial_width: float
    mixing_zone_distance: float
    current_speed: float
    #: The manual allows values down to 0.001 m but not zero.
    initial_location: float = 0.001
    alpha: float = 3.0e-4
    law: EddyDiffusivityLaw = EddyDiffusivityLaw.FOUR_THIRDS
    initial_concentration: float | None = None
    decay_per_day: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_location <= 0.0:
            raise ValueError(
                "initial wastefield location must be greater than zero "
                "(the exe allows values down to 0.001 m)"
            )
        if self.mixing_zone_distance <= self.initial_location:
            raise ValueError("the mixing zone must lie beyond the initial wastefield location")
        if self.initial_dilution < 1.0:
            raise ValueError(
                "initial dilution must be at least 1; enter exactly 1 when it is unknown, "
                "which the manual describes as the conservative choice"
            )


def output_distances(request: StandaloneRequest) -> NDArray[np.float64]:
    """The fixed grid: 25 steps to the mixing zone, then 3 beyond.

    Distances are measured from the outfall. The **origin row is not printed** -- the exe
    starts at step 1, so a 200 m mixing zone from 0.001 m gives 28 rows running
    8.001 .. 224.000 m. Confirmed exactly against
    `reference_cases/case17_independent_farfield`.
    """
    span = request.mixing_zone_distance - request.initial_location
    step = span / STEPS_TO_MIXING_ZONE
    count = STEPS_TO_MIXING_ZONE + STEPS_BEYOND_MIXING_ZONE
    steps = np.arange(1, count + 1, dtype=np.float64)
    return np.asarray(request.initial_location + step * steps)


def independent_farfield(request: StandaloneRequest) -> pd.DataFrame:
    """Run the standalone Brooks calculation.

    Returns a frame indexed by distance from the outfall, with the far-field dilution
    factor, the total dilution, the wastefield width, travel time, and -- when an initial
    concentration was supplied -- the resulting concentration.
    """
    distances = output_distances(request)
    # Brooks x is measured from the start of the far field, not the outfall.
    x = distances - request.initial_location

    parameters = BrooksParameters(
        initial_width=request.initial_width,
        initial_dilution=request.initial_dilution,
        current_speed=request.current_speed,
        alpha=request.alpha,
        law=request.law,
        decay_per_day=request.decay_per_day,
    )

    frame = pd.DataFrame(
        {
            "distance": distances,
            "dilution_factor": parameters.dilution_factor(x),
            "dilution": parameters.total_dilution(x),
            "width": parameters.width(x),
            "travel_time_s": parameters.travel_time(x),
        }
    ).set_index("distance")
    frame["travel_time_hr"] = frame["travel_time_s"] / 3600.0

    if request.initial_concentration is not None:
        frame["concentration"] = request.initial_concentration / frame["dilution"]
    return frame
