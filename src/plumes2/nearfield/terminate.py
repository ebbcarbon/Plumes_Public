"""Where the near field ends (manual §2.3.1, §5.2.7).

The manual lists four termination benchmarks: neutral buoyancy, vertical velocity reversal,
boundary contact, and the max-rise-or-fall switch. Read literally they look like four
independent tests, and the switch looks like a fifth thing layered on top. Measured against
the traces they collapse into something much simpler.

**The plume oscillates, and the switch counts the turning points.** A discharge that is not
neutrally buoyant overshoots its equilibrium level and rings about it, at the Brunt-Vaisala
frequency in the ideal case. Each half-cycle is punctuated by two printed banners:

    "Plume traps"                  the plume crosses neutral buoyancy, rho_j = rho_a
    "Local maximum rise or fall"   the vertical velocity reverses -- one banner for **both**
                                   the top and the bottom of the swing

So the run's structure is a strict alternation of crossings and reversals, and the switch is
simply **how many of them to allow**:

    near field ends at oscillation event number `max_rise_or_fall + 1`

Which is what the manual's table says once you stop reading its four rows as descriptions of
*kinds* of event and start reading them as an *ordinal*: "terminate at the first trapping"
(0), "maximum rise" (1), "a second trapping depth" (2), "maximum fall" (3). The manual's
labels assume a buoyant plume rising; for a dense discharge the sequence inverts -- "for
discharges with negative vertical angle the rise and fall sequence is reversed" -- and the
*counting* is what survives. test23 discharges dense and runs reversal, crossing, reversal,
crossing; it still stops on the fourth with the switch at 3.

**Measured on 31 archived traces: 28 end exactly on event `switch + 1`.** All three exceptions
are the other benchmarks firing first, and each is independently explained:

    case09   0 events, stops at step 5001    -- the hard step cap; a 39.5 m/s jet that never
                                                turns over (PLAN.md §7, the NaN run)
    case10   1 event,  "Plume hits the bottom" -- seabed contact
    case13   1 event,  "Plume surfaces"        -- surface contact

⚠️ **`stop_at_surface` is session state, not project state.** case13 and case14 have
**byte-identical** `.prj` files and both parse as `stop_at_surface=True`, yet case13 stops on
its surface hit at step 275 while case14 sails through the same hit and runs on to its third
oscillation event at 476. The flag the GUI actually honoured is not in the file, exactly like
the chemistry tables. So it is a `Case` field here, and a `.prj` we write cannot round-trip
it -- treat a parsed value as a default rather than as fact.

Boundary contact uses the plume **edge**, not the centreline -- `depth - radius <= 0` at the
surface and `depth + radius >= bottom` at the seabed, both measured, and both live in
`solver.py` where the geometry is. Shoreline contact is inert (case12).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "MAX_STEPS",
    "OscillationEvent",
    "OscillationKind",
    "TerminationReason",
    "near_field_end",
    "oscillation_limit",
]

#: Hard cap on internal model steps. case09 runs to 5001 printed rows emitting NaN, which is
#: the only place we have seen it bind.
MAX_STEPS = 5000


class OscillationKind(StrEnum):
    """The two banners that punctuate the plume's ringing about its equilibrium level."""

    #: `rho_j = rho_a` -- the exe prints "Plume traps".
    TRAP = "trap"
    #: The vertical velocity changes sign -- "Local maximum rise or fall", top **or** bottom.
    REVERSAL = "reversal"


class TerminationReason(StrEnum):
    """Why the near field stopped. Ordered roughly by how much they mean."""

    OSCILLATION = "oscillation limit"
    SURFACE = "surface"
    SEABED = "seabed"
    DILUTION = "dilution limit"
    STEP_CAP = "step cap"
    TIME_LIMIT = "time limit"
    NON_PHYSICAL = "non-physical state"


@dataclass(frozen=True, slots=True, order=True)
class OscillationEvent:
    """One turning point, with the time it happened."""

    time: float
    kind: OscillationKind


def oscillation_limit(max_rise_or_fall: int) -> int:
    """How many oscillation events the run is allowed, i.e. `switch + 1`.

    The switch is 0-3 (manual §5.2.7), so this is 1-4. Four is the common case: every project
    in `reference_cases/` built on test21 uses 3.
    """
    if not 0 <= max_rise_or_fall <= 3:
        raise ValueError("the max-rise-or-fall switch is 0-3")
    return max_rise_or_fall + 1


def near_field_end(
    events: list[OscillationEvent],
    max_rise_or_fall: int,
    *,
    boundary_time: float | None = None,
    boundary_reason: TerminationReason | None = None,
    fallback: float = float("inf"),
    fallback_reason: TerminationReason = TerminationReason.TIME_LIMIT,
) -> tuple[float, TerminationReason]:
    """`(time, reason)` -- whichever benchmark fires first.

    `boundary_time` is the earliest hard stop the integrator already found (a surface or
    seabed contact, a dilution ceiling), if any; it wins if it precedes the oscillation limit.
    `fallback` covers the case where neither fires -- the integration simply ran out.
    """
    limit = oscillation_limit(max_rise_or_fall)
    ordered = sorted(events)
    end, reason = fallback, fallback_reason
    if len(ordered) >= limit and ordered[limit - 1].time < end:
        end, reason = ordered[limit - 1].time, TerminationReason.OSCILLATION
    # `<=`, not `<`: a boundary hit that lands exactly on the fallback *is* the reason the
    # integration stopped there, and saying "time limit" would bury it. It also wins an exact
    # tie with an oscillation, because running into the seabed is the more definite fact.
    if boundary_time is not None and boundary_time <= end:
        end = boundary_time
        reason = boundary_reason if boundary_reason is not None else TerminationReason.SURFACE
    return end, reason
