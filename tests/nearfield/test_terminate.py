"""Where the near field ends -- the oscillation counter of manual §5.2.7."""

from __future__ import annotations

import pytest

from plumes2.nearfield.terminate import (
    OscillationEvent,
    OscillationKind,
    TerminationReason,
    near_field_end,
    oscillation_limit,
)


def _events(*times: float) -> list[OscillationEvent]:
    """Alternating turning points, which is the pattern every trace shows."""
    kinds = (OscillationKind.REVERSAL, OscillationKind.TRAP)
    return [OscillationEvent(t, kinds[i % 2]) for i, t in enumerate(times)]


def test_the_switch_is_an_ordinal_not_a_kind() -> None:
    """0-3 selects the 1st-4th turning point, whatever kind each happens to be."""
    assert [oscillation_limit(s) for s in range(4)] == [1, 2, 3, 4]
    for bad in (-1, 4):
        with pytest.raises(ValueError, match="0-3"):
            oscillation_limit(bad)


@pytest.mark.parametrize(("switch", "expected"), [(0, 10.0), (1, 20.0), (2, 30.0), (3, 40.0)])
def test_the_run_ends_on_the_nth_turning_point(switch: int, expected: float) -> None:
    end, reason = near_field_end(_events(10.0, 20.0, 30.0, 40.0, 50.0), switch)
    assert end == expected
    assert reason == TerminationReason.OSCILLATION


def test_too_few_turning_points_falls_through() -> None:
    """A plume that never rings enough times just runs out."""
    end, reason = near_field_end(_events(10.0), 3, fallback=99.0)
    assert (end, reason) == (99.0, TerminationReason.TIME_LIMIT)


def test_a_boundary_hit_wins_when_it_comes_first() -> None:
    end, reason = near_field_end(
        _events(10.0, 20.0, 30.0, 40.0),
        3,
        boundary_time=25.0,
        boundary_reason=TerminationReason.SEABED,
    )
    assert (end, reason) == (25.0, TerminationReason.SEABED)


def test_a_boundary_hit_on_the_fallback_is_not_reported_as_a_time_limit() -> None:
    """The regression the `<=` guards: the integrator stopped *because* of the boundary.

    A terminal event lands exactly on the last integration time, so comparing strictly would
    call it a time limit and bury the real reason.
    """
    end, reason = near_field_end(
        _events(10.0),
        3,
        boundary_time=36.5,
        boundary_reason=TerminationReason.DILUTION,
        fallback=36.5,
    )
    assert (end, reason) == (36.5, TerminationReason.DILUTION)


def test_a_late_boundary_does_not_extend_the_run() -> None:
    end, reason = near_field_end(
        _events(10.0, 20.0, 30.0, 40.0),
        3,
        boundary_time=99.0,
        boundary_reason=TerminationReason.SURFACE,
    )
    assert (end, reason) == (40.0, TerminationReason.OSCILLATION)


def test_the_order_of_the_kinds_does_not_matter() -> None:
    """test23 discharges dense and runs reversal-first; the count is what survives.

    "For discharges with negative vertical angle the rise and fall sequence is reversed."
    """
    forward = [
        OscillationEvent(10.0, OscillationKind.TRAP),
        OscillationEvent(20.0, OscillationKind.REVERSAL),
    ]
    reversed_order = [
        OscillationEvent(10.0, OscillationKind.REVERSAL),
        OscillationEvent(20.0, OscillationKind.TRAP),
    ]
    assert near_field_end(forward, 1)[0] == near_field_end(reversed_order, 1)[0] == 20.0


def test_events_are_counted_in_time_order_however_supplied() -> None:
    assert near_field_end(_events(30.0, 10.0, 20.0), 1)[0] == 20.0
