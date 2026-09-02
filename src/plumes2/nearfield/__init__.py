"""Near-field UM3 Lagrangian Control Volume solver.

`state.py` holds the LCV state vector, its geometry and the port initial conditions,
`entrainment.py` the two source terms of eq 2, and `solver.py` the time integration.
Merging, the full termination rule set and the step controller follow -- see PLAN.md Phase 5.
"""

from __future__ import annotations

from plumes2.nearfield.entrainment import (
    ProjectedArea,
    ProjectedAreaEntrainment,
    local_frame,
    shear_speed,
    taylor_area,
    taylor_entrainment,
)
from plumes2.nearfield.solver import (
    NO_FORCED_ENTRAINMENT,
    NearFieldSolution,
    Trajectory,
    integrate,
)
from plumes2.nearfield.state import (
    GRAVITY,
    STATE_SIZE,
    LcvGeometry,
    LcvState,
    exit_speed,
    horizontal_unit,
    initial_radius,
    initial_state,
    unpack,
    velocity_vector,
)

__all__ = [
    "GRAVITY",
    "NO_FORCED_ENTRAINMENT",
    "STATE_SIZE",
    "LcvGeometry",
    "LcvState",
    "NearFieldSolution",
    "ProjectedArea",
    "ProjectedAreaEntrainment",
    "Trajectory",
    "exit_speed",
    "horizontal_unit",
    "initial_radius",
    "initial_state",
    "integrate",
    "local_frame",
    "shear_speed",
    "taylor_area",
    "taylor_entrainment",
    "unpack",
    "velocity_vector",
]
