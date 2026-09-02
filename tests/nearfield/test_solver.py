"""The LCV integration, against the zero-ambient-current traces.

These are the traces where `A_p` is excluded *by construction*: with `U_a = 0` the forced
term of eq 2 vanishes identically, so a comparison tests only documented physics plus the
two relations measured in `state.py` -- `h` proportional to `|U_j|`, and the vena contracta.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np
import pytest

from plumes2.config import Case
from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.nearfield.entrainment import (
    ProjectedAreaEntrainment,
    Um3Entrainment,
    aspiration_velocity,
    local_frame,
    projected_area,
    shear_speed,
    taylor_area,
    taylor_entrainment,
    vertical_plane_frame,
)
from plumes2.nearfield.merging import effective_half_spacing
from plumes2.nearfield.solver import NO_FORCED_ENTRAINMENT, integrate
from plumes2.seawater import density

CASES = Path(__file__).resolve().parents[2] / "reference_cases"
ZERO_CURRENT = CASES / "case18_zero_current_pair"
SWEEP = CASES / "case19_current_sweep"
SPACING = CASES / "case20_spacing_sweep"

#: The event boundaries the exe prints in test23, which separate the trajectory's phases.
TEST23_FIRST_MAX_RISE = 223
TEST23_FIRST_TRAP = 395


def _baseline() -> Case:
    return load_project(ZERO_CURRENT / "test21.prj", warn_on_drift=False).to_case()


def _variant(*, ports: int, flow: float, current: float, contraction: float | None = None) -> Case:
    """test21's project with the single field each variant changed."""
    case = _baseline()
    levels = [level.model_copy(update={"current_speed": current}) for level in case.ambient.levels]
    updates: dict[str, object] = {
        "diffuser": case.diffuser.model_copy(update={"n_ports": ports}),
        "effluent": case.effluent.model_copy(update={"flow": flow}),
        "ambient": case.ambient.model_copy(update={"levels": levels}),
    }
    if contraction is not None:
        updates["near_field"] = case.near_field.model_copy(
            update={"contraction_coefficient": contraction}
        )
    return case.model_copy(update=updates)


def _test23() -> Case:
    """Single port, zero ambient current, 100x-reduced flow."""
    return _variant(ports=1, flow=5.0e-5, current=0.0)


# ------------------------------------------------------------------ entrainment terms


def test_taylor_area_is_the_cylindrical_wrap() -> None:
    assert taylor_area(2.0, 3.0) == pytest.approx(2.0 * math.pi * 6.0)


def test_taylor_entrainment_is_linear_in_each_factor() -> None:
    base = taylor_entrainment(1024.0, 0.5, 0.2, 1.5, 0.1)
    assert taylor_entrainment(2048.0, 0.5, 0.2, 1.5, 0.1) == pytest.approx(2 * base)
    assert taylor_entrainment(1024.0, 1.0, 0.2, 1.5, 0.1) == pytest.approx(2 * base)
    assert taylor_entrainment(1024.0, 0.5, 0.4, 1.5, 0.1) == pytest.approx(2 * base)
    assert taylor_entrainment(1024.0, 0.5, 0.2, 3.0, 0.1) == pytest.approx(2 * base)
    assert taylor_entrainment(1024.0, 0.5, 0.2, 1.5, 0.2) == pytest.approx(2 * base)


def test_taylor_entrainment_uses_the_speed_magnitude() -> None:
    """A plume moving backwards still entrains."""
    assert taylor_entrainment(1024.0, 0.5, 0.2, -1.5, 0.1) == pytest.approx(
        taylor_entrainment(1024.0, 0.5, 0.2, 1.5, 0.1)
    )


def test_taylor_entrainment_rejects_a_negative_coefficient() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        taylor_entrainment(1024.0, 0.5, 0.2, 1.5, -0.1)


def test_the_shear_speed_is_relative_to_the_ambient_by_default() -> None:
    plume = np.array([0.3, 0.4, 0.0])
    ambient = np.array([0.1, 0.0, 0.0])
    assert shear_speed(plume, ambient) == pytest.approx(math.hypot(0.2, 0.4))
    assert shear_speed(plume, ambient, relative=False) == pytest.approx(0.5)


def test_the_two_shear_conventions_coincide_in_still_water() -> None:
    """Why it went unnoticed: no zero-current run can tell the two apart.

    `alpha |V|` and `alpha |V - U_a|` are identically equal when `U_a = 0`, which is every
    run that validated `alpha`, the thickness law and the vena contracta.
    """
    for velocity in ([0.3, 0.4, 0.0], [0.0, 0.0, -0.5], [0.1, -0.2, 0.3]):
        plume = np.array(velocity)
        assert shear_speed(plume, np.zeros(3)) == shear_speed(plume, np.zeros(3), relative=False)


def test_the_local_frame_is_orthonormal_and_correctly_oriented() -> None:
    """`e2` lies in the vertical plane and `e3` is horizontal -- see entrainment.py."""
    for velocity in ([1.0, 0.0, 1.0], [0.0, 2.0, -1.0], [0.3, -0.4, 0.5]):
        frame = local_frame(np.array(velocity))
        assert frame.components(np.array(velocity))[1] == pytest.approx(0.0, abs=1e-12)
        vectors = (frame.along, frame.in_plane, frame.out_of_plane)
        for vector in vectors:
            assert float(np.linalg.norm(vector)) == pytest.approx(1.0)
        for first in range(3):
            for second in range(first + 1, 3):
                assert float(np.dot(vectors[first], vectors[second])) == pytest.approx(
                    0.0, abs=1e-12
                )
        # e3 horizontal; e2 in the vertical plane containing the trajectory.
        assert frame.out_of_plane[2] == pytest.approx(0.0, abs=1e-12)
        assert float(np.dot(np.cross(frame.along, frame.in_plane), frame.out_of_plane)) > 0.0


def test_the_current_defines_the_plane_for_a_vertical_trajectory() -> None:
    """The choice is *not* arbitrary: an unlucky azimuth would zero out `u2` entirely."""
    rising = np.array([0.0, 0.0, 0.5])
    current = np.array([0.02, 0.0, 0.0])
    frame = local_frame(rising, current)
    # u3 must vanish, and u2 must carry the whole current.
    along, in_plane, out_of_plane = frame.components(current)
    assert along == pytest.approx(0.0, abs=1e-12)
    assert out_of_plane == pytest.approx(0.0, abs=1e-12)
    assert abs(in_plane) == pytest.approx(0.02)
    # Without the current the plane is undetermined and u2 can land on zero.
    assert local_frame(rising).components(current)[1] == pytest.approx(0.0, abs=1e-12)


def test_the_working_plane_always_contains_the_current() -> None:
    """`u3 = 0` by construction, which is the 2-D restriction the reference assumes."""
    for velocity in ([0.3, 0.0, 0.4], [0.0, 0.2, -0.1], [0.5, -0.5, 0.2]):
        for current in ([0.02, 0.0, 0.0], [0.0, 0.05, 0.0], [-0.03, 0.04, 0.0]):
            frame = local_frame(np.array(velocity), np.array(current))
            assert frame.components(np.array(current))[2] == pytest.approx(0.0, abs=1e-12)


def test_the_frame_refuses_a_motionless_element() -> None:
    with pytest.raises(ValueError, match="motionless"):
        local_frame(np.zeros(3))


def test_the_three_areas_follow_the_published_equations() -> None:
    """eqs 38-41: growth `pi b db`, cylinder `2 b h`, curvature `-(pi/2) b^2 dth/ds h`."""
    area = projected_area(radius=0.5, thickness=0.2, radius_gradient=0.1, elevation_gradient=0.3)
    assert area.growth == pytest.approx(math.pi * 0.5 * 0.1 * 0.2)
    assert area.cylinder == pytest.approx(2.0 * 0.5 * 0.2)
    assert area.curvature == pytest.approx(-0.5 * math.pi * 0.25 * 0.3 * 0.2)


def test_the_curvature_area_is_signed() -> None:
    """"Positive curvature has the effect of reducing the total projected area." """
    rising = projected_area(0.5, 0.2, 0.1, +0.3)
    falling = projected_area(0.5, 0.2, 0.1, -0.3)
    assert rising.curvature < 0.0 < falling.curvature
    assert rising.in_plane_total < falling.in_plane_total


def test_the_in_plane_area_is_floored_at_zero() -> None:
    """Strong positive curvature would otherwise make entrainment a sink."""
    area = projected_area(radius=0.5, thickness=0.2, radius_gradient=0.0, elevation_gradient=50.0)
    assert area.cylinder + area.curvature < 0.0
    assert area.in_plane_total == 0.0


def test_forced_entrainment_vanishes_in_still_water() -> None:
    """With `U_a = 0` every component is zero, so the whole forced term is.

    This is the structural reason the zero-current runs isolate the Taylor term, and why
    they are unaffected by any choice of weights.
    """
    forced = ProjectedAreaEntrainment()
    velocity = np.array([0.3, 0.0, 0.4])
    assert forced.rate(1024.0, np.zeros(3), velocity, 0.5, 0.2, 0.1, 0.05) == 0.0


def test_forced_entrainment_is_nonzero_in_a_cross_flow() -> None:
    forced = ProjectedAreaEntrainment()
    velocity = np.array([0.0, 0.0, 0.5])
    current = np.array([0.02, 0.0, 0.0])
    assert forced.rate(1024.0, current, velocity, 0.5, 0.2, 0.1, 0.05) > 0.0


def test_forced_entrainment_is_never_negative() -> None:
    """Eq 28's sign convention makes the term a gain, whatever the geometry."""
    forced = ProjectedAreaEntrainment()
    for current in ([0.02, 0.0, 0.0], [-0.02, 0.0, 0.0], [0.0, -0.05, 0.0]):
        for velocity in ([0.0, 0.0, 0.5], [0.0, 0.0, -0.5], [0.4, 0.3, 0.0]):
            for elevation_gradient in (-2.0, 0.0, 2.0):
                assert (
                    forced.rate(
                        1024.0,
                        np.array(current),
                        np.array(velocity),
                        0.5,
                        0.2,
                        0.1,
                        elevation_gradient,
                    )
                    >= 0.0
                )


def test_each_weight_switches_its_own_term() -> None:
    """The weights exist for exactly this -- demonstrating a term contributes."""
    current = np.array([0.02, 0.0, 0.0])
    velocity = np.array([0.1, 0.0, 0.1])
    arguments = (1024.0, current, velocity, 0.5, 0.2, 0.1, 0.05)
    full = ProjectedAreaEntrainment().rate(*arguments)
    for field in ("growth", "cylinder", "curvature"):
        reduced = ProjectedAreaEntrainment(**{field: 0.0}).rate(*arguments)
        assert reduced != pytest.approx(full), field
    assert ProjectedAreaEntrainment(
        growth=0.0, cylinder=0.0, curvature=0.0
    ).rate(*arguments) == 0.0


# --------------------------------------------------------------------- initial state


def test_the_integration_starts_at_the_port() -> None:
    solution = integrate(_test23(), max_time=1.0)
    trajectory = solution.sample(np.array([0.0]))
    assert float(trajectory.dilution[0]) == pytest.approx(1.0)
    assert float(trajectory.z[0]) == pytest.approx(-2.0)
    assert float(trajectory.salinity[0]) == pytest.approx(35.0)
    # b_0 = (d/2) sqrt(c) = 0.00635 * sqrt(0.61); U_0 = Q / (n c A).
    assert float(trajectory.diameter[0]) == pytest.approx(0.0127 * math.sqrt(0.61), rel=1e-6)
    assert float(trajectory.speed[0]) == pytest.approx(
        5.0e-5 / (0.61 * math.pi * (0.0127 / 2) ** 2), rel=1e-6
    )


# ------------------------------------------------------------ against test23 (Ua = 0)


@pytest.fixture(scope="module")
def test23_comparison():  # type: ignore[no-untyped-def]
    nearfield = read_dat(ZERO_CURRENT / "test23.dat").nearfield
    times = nearfield["Time"].to_numpy(dtype=float)
    solution = integrate(_test23(), max_time=float(times[-1]) + 1.0)
    return nearfield, solution.sample(times)


@pytest.mark.golden
def test_the_jet_phase_meets_the_upstream_acceptance_bar(test23_comparison) -> None:  # type: ignore[no-untyped-def]
    """0.5 % mean absolute relative error is upstream's own bar (manual Appendix A).

    Measured 0.31 % on dilution over the jet phase, using only the manual's equations plus
    the two measured relations. `A_p` is excluded by construction here.
    """
    nearfield, ours = test23_comparison
    steps = nearfield.index.to_numpy()
    window = steps < TEST23_FIRST_MAX_RISE
    theirs = nearfield["Dilutn"].to_numpy(dtype=float)[window]
    error = np.abs(ours.dilution[window] - theirs) / theirs
    assert error.mean() < 0.005
    assert error.max() < 0.015


@pytest.mark.golden
def test_the_rise_to_first_trapping_also_meets_the_bar(test23_comparison) -> None:  # type: ignore[no-untyped-def]
    nearfield, ours = test23_comparison
    steps = nearfield.index.to_numpy()
    window = (steps >= TEST23_FIRST_MAX_RISE) & (steps < TEST23_FIRST_TRAP)
    theirs = nearfield["Dilutn"].to_numpy(dtype=float)[window]
    error = np.abs(ours.dilution[window] - theirs) / theirs
    assert error.mean() < 0.005


@pytest.mark.golden
def test_salinity_and_temperature_are_conserved_essentially_exactly(test23_comparison) -> None:  # type: ignore[no-untyped-def]
    """Heat and salt need no closure at all, so these should be the cleanest columns."""
    nearfield, ours = test23_comparison
    for column, predicted in (
        ("P-Sal", ours.salinity),
        ("P-Temp", ours.temperature),
    ):
        theirs = nearfield[column].to_numpy(dtype=float)
        error = np.abs(predicted - theirs) / theirs
        assert error.mean() < 5e-4, column
        assert error.max() < 3e-3, column


@pytest.mark.golden
def test_the_late_oscillation_drifts_and_the_drift_is_pinned(test23_comparison) -> None:  # type: ignore[no-untyped-def]
    """Recorded, not fixed: 1.7 % then 5.2 % across the two post-trapping phases.

    The cause is quantified in `test_the_eos_offset_reproduces_on_a_second_case`: the
    buoyancy difference driving the late phases is ~0.04 kg/m3, so the EOS residual that
    does *not* cancel between plume and ambient is about 12 % of it, against 0.7 % in the
    jet. Bracketed on both sides so that a fix shows up as a failure rather than passing
    silently.
    """
    nearfield, ours = test23_comparison
    steps = nearfield.index.to_numpy()
    theirs = nearfield["Dilutn"].to_numpy(dtype=float)
    window = steps >= TEST23_FIRST_TRAP
    error = np.abs(ours.dilution[window] - theirs[window]) / theirs[window]
    assert 0.01 < error.mean() < 0.06
    jet = steps < TEST23_FIRST_MAX_RISE
    jet_error = np.abs(ours.dilution[jet] - theirs[jet]) / theirs[jet]
    assert error.mean() > 5.0 * jet_error.mean(), "the late phases should be decisively worse"


@pytest.mark.golden
def test_the_eos_offset_reproduces_on_a_second_case() -> None:
    """The exe's density sits +0.0278 kg/m3 above EOS-80 on test23, using its own S and T.

    Phase 2 measured +0.0275 +- 0.0014 on case16, an unrelated case, so this is independent
    confirmation that the discrepancy is a formula difference rather than anything we do.
    """
    nearfield = read_dat(ZERO_CURRENT / "test23.dat").nearfield
    salinity = nearfield["P-Sal"].to_numpy(dtype=float)
    temperature = nearfield["P-Temp"].to_numpy(dtype=float)
    reported = nearfield["P-Den"].to_numpy(dtype=float)
    ours = np.asarray(density(salinity, temperature, 0.0), dtype=float)
    offset = reported - ours
    assert offset.mean() == pytest.approx(0.0278, abs=0.002)
    assert offset.std() < 0.005, "the offset should be near-constant, not structured"


# --------------------------------------------------------------------- termination


@pytest.mark.golden
def test_a_dense_plume_does_not_reach_the_surface() -> None:
    """test23's effluent is 35 psu into ~31 psu ambient, so it traps rather than surfacing.

    It rings about its trapping level instead, and with the switch at 3 the fourth turning
    point is what ends the near field -- which is exactly what the trace does, at step 732.
    """
    solution = integrate(_test23(), max_time=160.0)
    assert "surface" not in solution.events
    assert "seabed" not in solution.events
    assert solution.reason == "oscillation limit"
    assert len(solution.oscillations) >= 4


def test_the_dilution_ceiling_terminates_the_run() -> None:
    solution = integrate(_test23(), max_time=400.0, max_dilution=40.0)
    assert solution.reason == "dilution limit"
    final = solution.sample(np.array([solution.events["dilution limit"]]))
    assert float(final.dilution[0]) == pytest.approx(40.0, rel=1e-4)


# ------------------------------------------------------- case19 / case20 findings


def test_the_zero_current_trajectory_is_unchanged_by_the_shear_convention() -> None:
    """The blind spot, at solver level: nothing already validated can move when this flips."""
    times = np.linspace(0.0, 100.0, 200)
    relative = integrate(_test23(), max_time=110.0).sample(times)
    absolute = integrate(_test23(), relative_shear=False, max_time=110.0).sample(times)
    np.testing.assert_array_equal(relative.dilution, absolute.dilution)
    np.testing.assert_array_equal(relative.z, absolute.z)


def test_the_default_closure_is_um3() -> None:
    """Not the published sum -- which is a different model, and a worse one in a cross-flow."""
    times = np.linspace(0.0, 20.0, 50)
    case = _variant(ports=1, flow=5.0e-5, current=0.05)
    default = integrate(case, max_time=25.0).sample(times).dilution
    explicit = integrate(case, forced=Um3Entrainment(), max_time=25.0).sample(times).dilution
    np.testing.assert_allclose(default, explicit, rtol=1e-12)
    for changed in (
        integrate(case, forced=ProjectedAreaEntrainment(), max_time=25.0),
        integrate(case, forced=NO_FORCED_ENTRAINMENT, max_time=25.0),
    ):
        assert not np.allclose(default, changed.sample(times).dilution, rtol=1e-6)


# --------------------------------------------------------------------------- the UM3 closure


def test_the_aspiration_velocity_reduces_to_the_published_form_in_still_water() -> None:
    """`alpha |V|` exactly, so no zero-current result can move."""
    for velocity in ([0.3, 0.4, 0.0], [0.0, 0.0, 0.5], [0.1, -0.2, 0.3]):
        plume = np.array(velocity)
        assert aspiration_velocity(plume, np.zeros(3), 0.1) == pytest.approx(
            0.1 * float(np.linalg.norm(plume))
        )


def test_the_cylinder_term_is_exactly_cancelled() -> None:
    """The identity the whole closure turns on, asserted directly.

    The `-u2/pi` folded into the aspiration velocity, carried on `A_T = 2 pi b h`, is
    *identically* the published cylinder term `A_cyl = 2 b h` driven by `u2`. So the pair
    reduces to `alpha(|V| - u1)` alone whenever the cross-flow is too weak to open the angle.
    """
    alpha, radius, thickness = 0.1, 0.5, 0.2
    plume = np.array([0.0, 0.6, 0.6])  # 45 deg, fast enough that u2 < ven
    ambient = np.array([0.0, 0.02, 0.0])

    frame = vertical_plane_frame(plume)
    along = float(np.dot(ambient, frame.along))
    across = float(np.linalg.norm(ambient)) * abs(plume[2]) / float(np.linalg.norm(plume))
    assert across < alpha * (float(np.linalg.norm(plume)) - along), "the angle must stay shut"

    area = taylor_area(radius, thickness)
    shear = alpha * (float(np.linalg.norm(plume)) - along)
    cylinder = projected_area(radius, thickness, 0.0, 0.0).cylinder * across

    # The Taylor term as UM3 actually reduces it, plus the published cylinder term...
    reduced = area * (shear - across / math.pi)
    assert reduced + cylinder == pytest.approx(area * shear)
    # ...which is exactly what the paired velocity returns: the cylinder has vanished.
    assert area * aspiration_velocity(plume, ambient, alpha) == pytest.approx(area * shear)


def test_the_working_plane_is_vertical_and_contains_the_trajectory() -> None:
    """UM3's frame, which is *not* `local_frame`'s -- see entrainment.py."""
    for velocity in ([0.3, 0.0, 0.4], [0.0, 0.2, -0.1], [0.5, -0.5, 0.2]):
        frame = vertical_plane_frame(np.array(velocity))
        assert frame.out_of_plane[2] == pytest.approx(0.0, abs=1e-12), "e3 must be horizontal"
        # The vertical is spanned by e1 and e2, so it has no out-of-plane part.
        assert float(np.dot(np.array([0.0, 0.0, 1.0]), frame.out_of_plane)) == pytest.approx(
            0.0, abs=1e-12
        )
        vectors = (frame.along, frame.in_plane, frame.out_of_plane)
        for first in range(3):
            assert float(np.linalg.norm(vectors[first])) == pytest.approx(1.0)
            for second in range(first + 1, 3):
                assert float(np.dot(vectors[first], vectors[second])) == pytest.approx(
                    0.0, abs=1e-12
                )


def test_the_um3_closure_vanishes_to_taylor_with_no_current() -> None:
    plume = np.array([0.0, 0.3, 0.4])
    total = Um3Entrainment().rate(1024.0, np.zeros(3), plume, 0.5, 0.2, 0.1, 0.05, 0.1)
    assert total == pytest.approx(1024.0 * taylor_area(0.5, 0.2) * 0.1 * 0.5)


# ------------------------------------------------- forced entrainment, measured from traces


def _measured_terms(path: Path, current: float, window: int = 12):
    """Every term of eq 2 as a *specific* rate, from a trace's printed columns alone.

    The element thickness cancels out of each one, so no assumption about `h` enters:

        total/m = d(ln D)/dt      taylor/m = 2 rho_a alpha |shear| / (rho b)
        growth/m = rho_a (db/ds) |u1| / (rho b)      cyl/m = 2 rho_a |u2| / (pi rho b)
        cur/m = -rho_a (dtheta/ds) |u2| / (2 rho)

    Velocity comes from differencing the printed positions over `+-window` samples.
    """
    from plumes2.ambient import AmbientProfileView

    case = _baseline()
    alpha = case.near_field.aspiration_coefficient
    bearing = math.radians(case.ambient.levels[0].current_direction)
    ambient_velocity = current * np.array([math.cos(bearing), math.sin(bearing), 0.0])

    parsed = read_dat(path)
    frame = parsed.nearfield[
        parsed.nearfield.index.to_numpy() < min(event.next_step for event in parsed.events)
    ]
    time = frame["Time"].to_numpy(dtype=float)
    radius = frame["P-dia"].to_numpy(dtype=float) / 2.0
    plume_density = frame["P-Den"].to_numpy(dtype=float)  # full density, not sigma-t
    position = np.column_stack(
        [
            frame["x-posn"].to_numpy(dtype=float),
            frame["y-posn"].to_numpy(dtype=float),
            frame["Depth"].to_numpy(dtype=float),  # already signed elevation
        ]
    )
    view = AmbientProfileView(case.ambient)
    ambient_density = np.array([float(view.sample(-z).density) for z in position[:, 2]])

    index = np.arange(window, len(time) - window)
    span = time[index + window] - time[index - window]
    velocity = (position[index + window] - position[index - window]) / span[:, None]
    speed = np.linalg.norm(velocity, axis=1)
    along = velocity / speed[:, None]
    arc = np.linalg.norm(position[index + window] - position[index - window], axis=1)

    total = (np.log(frame["Dilutn"].to_numpy(dtype=float))[index + window] - np.log(
        frame["Dilutn"].to_numpy(dtype=float)
    )[index - window]) / span
    b, rho, rho_a = radius[index], plume_density[index], ambient_density[index]

    taylor_absolute = 2.0 * rho_a * alpha * speed / (rho * b)
    taylor_relative = (
        2.0 * rho_a * alpha * np.linalg.norm(velocity - ambient_velocity, axis=1) / (rho * b)
    )
    u1 = along @ ambient_velocity
    u2 = np.linalg.norm(ambient_velocity - u1[:, None] * along, axis=1)
    elevation = np.arcsin(np.clip(velocity[:, 2] / speed, -1.0, 1.0))
    pae = (
        rho_a * ((radius[index + window] - radius[index - window]) / arc) * np.abs(u1) / (rho * b)
        + 2.0 * rho_a * u2 / (math.pi * rho * b)
        - rho_a * np.gradient(elevation, np.cumsum(arc)) * u2 / (2.0 * rho)
    )
    return {
        "total": total,
        "taylor_absolute": taylor_absolute,
        "taylor_relative": taylor_relative,
        "pae": pae,
        "velocity_ratio": current / speed,
    }


@pytest.mark.golden
def test_the_trace_measurement_recovers_taylor_exactly_with_no_current() -> None:
    """The control that licenses everything below: on test23 the residual must vanish.

    `A_p` is identically zero there, so `total - taylor` measures nothing but the method's
    own error. It comes out at a few percent of the Taylor term -- the floor set by
    differencing positions printed to three decimals.
    """
    measured = _measured_terms(ZERO_CURRENT / "test23.dat", 0.0)
    residual = measured["total"] - measured["taylor_absolute"]
    assert np.abs(residual / measured["taylor_absolute"]).mean() < 0.03
    np.testing.assert_allclose(measured["pae"], 0.0, atol=1e-12)


@pytest.mark.golden
def test_absolute_shear_demands_impossible_negative_forced_entrainment() -> None:
    """This is what rules out the reference's literal `beta_T = alpha |V|`.

    With that convention the Taylor term alone exceeds the total entrainment the exe
    applied, so the forced term would have to be a *sink*; eq 28's sign convention makes it
    a gain. Under `alpha |V - U_a|` the same residual is positive across the whole late jet
    at every current.

    The deficit deepens monotonically with the current -- 6 %, 21 %, 49 %, 76 % of the
    Taylor term -- which is the signature of a shear velocity that should have had `U_a`
    subtracted from it. At 0.01 m/s it is only just outside the control's noise floor; the
    0.05 and 0.10 m/s runs carry the decisive signal.
    """
    deepest = []
    for run, current in (("test28", 0.01), ("test27", 0.02), ("test29", 0.05), ("test30", 0.10)):
        measured = _measured_terms(SWEEP / f"{run}.dat", current)
        absolute = (measured["total"] - measured["taylor_absolute"]) / measured["taylor_absolute"]
        relative = measured["total"] - measured["taylor_relative"]
        late = slice(-len(absolute) // 10, None)
        assert relative[late].min() > 0.0, f"{run}: relative shear must leave a forced gain"
        assert absolute[late].max() < 0.05, f"{run}: absolute shear must run a deficit"
        deepest.append(float(absolute.min()))
    assert deepest == sorted(deepest, reverse=True), "the deficit must deepen with the current"
    assert deepest[0] < -0.05 and deepest[-1] < -0.4


@pytest.mark.golden
def test_the_forced_residual_is_the_published_pae_attenuated_by_the_velocity_ratio() -> None:
    """`f = measured forced / unit-weight PAE` collapses onto `|U_a| / |V|` alone.

    Across a tenfold range of current the four runs agree within a bin while `f` itself
    sweeps 0.22 to 0.87.

    ⚠️ **This is a true measurement of a quantity that turned out not to mean what it looked
    like.** `f` is the gap between the exe and *this* decomposition, and UM3 does not use this
    decomposition -- it cancels the cylinder term against a reduction in the Taylor velocity,
    after which there is no gap to explain (see `ProjectedAreaEntrainment`). The test is kept
    because the numbers are real and pin the traces, and because a clean one-variable collapse
    across a tenfold range is worth remembering as something that can still be an artifact of
    the null model it was differenced against.
    """
    edges = np.arange(0.05, 0.96, 0.1)
    binned: dict[float, list[float]] = {}
    for run, current in (("test28", 0.01), ("test27", 0.02), ("test29", 0.05), ("test30", 0.10)):
        measured = _measured_terms(SWEEP / f"{run}.dat", current)
        usable = measured["pae"] > 0.0
        f = (measured["total"] - measured["taylor_relative"])[usable] / measured["pae"][usable]
        ratio = measured["velocity_ratio"][usable]
        for low, high in itertools.pairwise(edges):
            window = (ratio >= low) & (ratio < high)
            if window.sum() >= 2:
                binned.setdefault(round(float(low), 2), []).append(float(f[window].mean()))

    # Every current that reaches a bin must agree there, and f must rise with the ratio.
    for low, values in binned.items():
        assert max(values) - min(values) < 0.08, f"bin {low} does not collapse: {values}"
    centres = sorted(binned)
    means = [float(np.mean(binned[low])) for low in centres]
    assert means == sorted(means), "f must increase with |Ua|/|V|"
    assert means[0] < 0.3 and means[-1] > 0.8
    # The gap is real: the published closure is never the measured magnitude.
    assert max(means) < 0.95


def _jet_error(run: str, current: float, closure) -> float:  # type: ignore[no-untyped-def]
    """Jet-phase dilution MARE against a sweep trace, at the exe's own printed times."""
    parsed = read_dat(SWEEP / f"{run}.dat")
    frame = parsed.nearfield[
        parsed.nearfield.index.to_numpy() < min(e.next_step for e in parsed.events)
    ]
    times = frame["Time"].to_numpy(dtype=float)
    theirs = frame["Dilutn"].to_numpy(dtype=float)
    case = _variant(ports=1, flow=5.0e-5, current=current)
    ours = integrate(case, forced=closure, max_time=float(times[-1]) + 1.0)
    return float((np.abs(ours.sample(times).dilution - theirs) / theirs).mean())


SWEEP_CURRENTS = (("test28", 0.01), ("test27", 0.02), ("test29", 0.05), ("test30", 0.10))


@pytest.mark.golden
def test_the_cross_flow_runs_now_meet_the_upstream_acceptance_bar() -> None:
    """0.5 % MARE is upstream's own bar, and the cross-flow sweep now clears it to 0.05 m/s.

    Where this started: 11-20 % summing the published equations onto a separate Taylor term,
    and 0.7-21 % omitting forced entrainment altogether.

    Bracketed on both sides. The lower bound matters: the zero-current runs sit at 0.31 %,
    which is the floor set by the exe's own sigma-t differing from EOS-80, so a cross-flow
    result *below* that would mean something had been fitted rather than derived.

    ⚠️ **The ceilings live in the validation registry, not here.** This test asserts them by running
    the registry's own targets, so `plumes2 validate` and this test cannot report different numbers
    for the same claim -- which is the whole reason the registry exists (PLAN.md Phase 7).
    """
    from plumes2.validation import TARGETS, measure

    checked = 0
    for target in TARGETS:
        if not target.row.startswith("171") or target.row == "171e":
            continue
        outcome = measure(target)
        assert outcome.passed, f"{target.row}: {outcome.ours:.4f} over {target.tolerance}"
        # The lower bound is this test's own, and it is the half the registry cannot express:
        # a MARE *below* the zero-current floor would mean the closure had been fitted.
        assert outcome.ours > 0.002, f"{target.row}: {outcome.ours:.4f} is below the EOS floor"
        checked += 1
    assert checked == 4, checked


@pytest.mark.slow
@pytest.mark.golden
def test_the_curvature_term_is_inert_in_the_exe() -> None:
    """Switching eq 41 on makes every cross-flow run worse, and worse in proportion to it.

    Corroborates the source, where the curvature area is driven by `V . unit(Rc)` with `Rc`
    built as `V x (V x V_last)` -- perpendicular to `V`, so the term is identically zero. See
    `Um3Entrainment`. A term that is merely mis-scaled would not show a deficit that grows
    monotonically with the current.
    """
    penalties = []
    for run, current in SWEEP_CURRENTS:
        off = _jet_error(run, current, Um3Entrainment())
        on = _jet_error(run, current, Um3Entrainment(curvature=1.0))
        assert on > off, f"{run}: curvature should not help"
        penalties.append(on - off)
    assert penalties == sorted(penalties), "the penalty must grow with the current"


@pytest.mark.golden
def test_the_exe_is_deterministic_run_to_run() -> None:
    """test27 is a rerun of test24 with nothing changed, and the bytes match exactly.

    No randomness, no timing dependence, a fully deterministic step controller -- which is
    what makes byte-exact `.dat` comparison a reasonable Phase 6 target.
    """
    assert (ZERO_CURRENT / "test24.dat").read_bytes() == (SWEEP / "test27.dat").read_bytes()


@pytest.mark.golden
def test_port_spacing_is_inert_until_the_plume_merges() -> None:
    """2 m and 5 m spacing give byte-identical near-field tables: the plume never merges.

    Max diameter is 1.967 m against a 2.0 m spacing, so the trigger is just missed, and an
    unmerged multiport diffuser behaves as independent single plumes. That is what licenses
    using the 25-port runs to pin single-plume physics.
    """
    wide = read_dat(SPACING / "test33.dat").nearfield
    narrow = read_dat(SPACING / "test31.dat").nearfield
    assert list(wide.columns) == list(narrow.columns)
    assert len(wide) == len(narrow)
    for column in wide.columns:
        np.testing.assert_array_equal(
            wide[column].to_numpy(dtype=float), narrow[column].to_numpy(dtype=float)
        )
    assert wide["P-dia"].max() < 2.0


@pytest.mark.golden
def test_merging_triggers_when_the_diameter_reaches_the_spacing() -> None:
    """Bracketed to 0.7 % by consecutive steps at output interval 1 (test32, 1 m spacing).

    step 309 -> 0.9990 of the spacing; step 310, which the banner precedes -> 1.0060. The
    previous best bracket was 0.982-1.038 from case05, so this is about 5x tighter. The
    horizontal angle equals the current direction here, so the offset is zero and effective
    spacing is nominal -- this run says nothing about the oblique-angle factor.
    """
    dat = read_dat(SPACING / "test32.dat")
    spacing = 1.0
    merges = [event for event in dat.events if event.text.strip().lower().startswith("merging")]
    assert len(merges) == 1
    step = merges[0].next_step
    diameters = dat.nearfield["P-dia"]
    before = float(diameters.loc[step - 1]) / spacing
    at = float(diameters.loc[step]) / spacing
    assert before < 1.0 <= at
    assert 0.995 < before < 1.0
    assert 1.0 <= at < 1.01


@pytest.mark.golden
def test_merging_suppresses_entrainment_by_the_measured_amount() -> None:
    """test32 against test31 isolates the correction: identical until merging, then not.

    Steps at the controller's 2 % cap are excluded -- both runs read 2.0000 % there and the
    ratio is 1 by construction, which would wash out the effect. Recorded as a measured
    envelope; `nearfield/merging.py` does not exist yet.
    """
    merged = read_dat(SPACING / "test32.dat").nearfield
    unmerged = read_dat(SPACING / "test31.dat").nearfield
    count = min(len(merged), len(unmerged))
    gain_merged = np.diff(merged["Dilutn"].to_numpy(dtype=float)[:count]) / merged[
        "Dilutn"
    ].to_numpy(dtype=float)[: count - 1]
    gain_unmerged = np.diff(unmerged["Dilutn"].to_numpy(dtype=float)[:count]) / unmerged[
        "Dilutn"
    ].to_numpy(dtype=float)[: count - 1]
    overlap = merged["P-dia"].to_numpy(dtype=float)[: count - 1] / 1.0

    uncapped = (
        (overlap > 1.0)
        & (gain_unmerged < 0.02 * 0.995)
        & (gain_merged < 0.02 * 0.995)
        & (gain_unmerged > 1e-6)
    )
    assert uncapped.sum() > 50
    ratio = gain_merged[uncapped] / gain_unmerged[uncapped]
    assert np.all(ratio < 1.0), "merging must reduce entrainment, never increase it"
    # Just past the trigger it is a few percent; deep into the overlap it approaches a third.
    assert ratio[np.argmin(overlap[uncapped])] > 0.9
    assert ratio.min() < 0.5


# ------------------------------------------------- coverage gaps found by audit, 2026-08-13

GENERATED = CASES / "case14_generated_nochem"


def test_a_freshwater_discharge_runs() -> None:
    """Regression: `S = 0` effluent crashed the solver outright.

    `_density_partials` central-differenced the equation of state, so at the freshwater end it
    evaluated EOS-80 at `S = -1e-4`, which is out of domain and raises. Municipal outfalls are
    routinely fresh -- case14's effluent is 0.0 psu -- so this is an ordinary input, and it
    made an entire archived case unrunnable.
    """
    case = load_project(GENERATED / "PythonGenerated.prj", warn_on_drift=False).to_case()
    assert case.effluent.salinity == 0.0
    solution = integrate(case, max_time=3000.0)
    trajectory = solution.sample(np.linspace(0.0, solution.solution.t[-1], 50))
    assert np.all(trajectory.salinity >= 0.0)
    assert np.all(np.isfinite(trajectory.dilution))
    assert trajectory.dilution[-1] > trajectory.dilution[0]


def test_a_vertical_discharge_puts_the_current_in_the_working_plane() -> None:
    """Every vertical plane contains a vertical trajectory, and the choice is not harmless.

    An arbitrary azimuth sends the whole current out-of-plane, which both zeroes `u2` -- so
    the aspiration velocity loses its cross-flow reduction -- and feeds the *uncancelled*
    out-of-plane term instead, inventing entrainment. Spanning the plane with the current
    instead leaves a vertical plume in a cross-current entraining exactly as it would in still
    water, which is what the cancelled Taylor/cylinder pair requires.

    No archived case discharges vertically, so only this test covers it.
    """
    rising = np.array([0.0, 0.0, 2.0])
    for azimuth in (0.0, 37.0, 90.0, 180.0, 270.0):
        radians = math.radians(azimuth)
        current = 0.05 * np.array([math.cos(radians), math.sin(radians), 0.0])
        frame = vertical_plane_frame(rising, current)
        assert float(np.dot(current, frame.out_of_plane)) == pytest.approx(0.0, abs=1e-12)

        moving = Um3Entrainment().rate(1024.0, current, rising, 0.5, 0.2, 0.05, 0.0, 0.1)
        still = Um3Entrainment().rate(1024.0, np.zeros(3), rising, 0.5, 0.2, 0.05, 0.0, 0.1)
        assert moving == pytest.approx(still), f"azimuth {azimuth}"


@pytest.mark.slow
@pytest.mark.golden
def test_the_out_of_plane_term_is_needed_by_the_oblique_case() -> None:
    """case14 is the only case whose current is not in the trajectory's vertical plane.

    It fires at 30 deg azimuth into a 0 deg current, so the plume swings horizontally toward
    the current as it rises -- 32.5 deg down to 17.7 deg over the pre-merge trajectory. That
    swing is the out-of-plane term's only witness, and it is a completely independent case:
    18 ports, freshwater effluent, oblique current, and it never informed the closure.

    Compared in depth-space rather than at printed times, because this trace has no `Time`
    column -- which is why it had never been used to check the solver at all.
    """
    case = load_project(GENERATED / "PythonGenerated.prj", warn_on_drift=False).to_case()
    frame = read_dat(GENERATED / "PythonGenerated3.dat").nearfield
    pre = frame[frame.index.to_numpy() < 255]  # before the trap and the merge
    depth = pre["Depth"].to_numpy(dtype=float)
    assert np.all(np.diff(depth) > 0), "the comparison needs a monotonic rise"

    def sample(closure):  # type: ignore[no-untyped-def]
        solution = integrate(case, forced=closure, max_time=3000.0)
        dense = solution.sample(np.linspace(0.0, solution.solution.t[-1], 20000))
        top = int(np.argmax(dense.z))
        rise = dense.z[: top + 1]
        order = np.argsort(rise)
        return [
            np.interp(depth, rise[order], value[: top + 1][order])
            for value in (dense.x, dense.y, dense.dilution)
        ]

    theirs = [pre[column].to_numpy(dtype=float) for column in ("x-posn", "y-posn", "Dilutn")]
    bearing = math.degrees(math.atan2(theirs[1][-1], theirs[0][-1]))
    assert 17.0 < bearing < 18.5, "the exe swings from 30 deg toward the current"

    with_term = sample(Um3Entrainment())
    without = sample(Um3Entrainment(out_of_plane=0.0))
    for ours, label in ((with_term, "with"), (without, "without")):
        error = float((np.abs(ours[2] - theirs[2]) / theirs[2]).mean())
        ours_bearing = math.degrees(math.atan2(ours[1][-1], ours[0][-1]))
        if label == "with":
            assert error < 0.03, f"dilution {error:.4f}"
            assert abs(ours_bearing - bearing) < 0.3, f"bearing {ours_bearing:.2f}"
        else:
            assert error > 0.05, "dropping the term should hurt dilution"
            assert abs(ours_bearing - bearing) > 1.0, "and should bend the plume wrongly"


# --------------------------------------------------------------------------------- merging

SPACING_SWEEP = {"test32": 1.0, "test31": 2.0, "test33": 5.0}


def _spacing_case(spacing: float) -> Case:
    """case20's geometry: 25 ports at 0.005 m3/s in a 0.02 m/s current."""
    case = _variant(ports=25, flow=0.005, current=0.02)
    return case.model_copy(
        update={"diffuser": case.diffuser.model_copy(update={"port_spacing": spacing})}
    )


def _spacing_run(run: str):  # type: ignore[no-untyped-def]
    spacing = SPACING_SWEEP[run]
    frame = read_dat(SPACING / f"{run}.dat").nearfield
    times = frame["Time"].to_numpy(dtype=float)
    solution = integrate(_spacing_case(spacing), max_time=float(times[-1]) + 1.0)
    usable = times <= solution.solution.t[-1]
    ours = solution.sample(times[usable])
    return frame, frame.index.to_numpy()[usable], ours, usable, spacing


@pytest.mark.golden
def test_merging_fires_when_the_diameter_reaches_the_spacing() -> None:
    """The trigger, against the tightest bracket we have.

    test32 at output interval 1 puts the exe's banner between step 309 (diameter 0.999 m) and
    step 310 (1.006 m), against a 1 m spacing -- so the criterion is `diameter >= spacing` to
    0.7 %. Ours must fire in the same place, and the 2 m and 5 m runs must not fire at all.
    """
    _, steps, ours, _, _ = _spacing_run("test32")
    fired = np.flatnonzero(ours.diameter >= 1.0)
    assert fired.size, "test32 must merge"
    assert steps[fired[0]] == 310
    assert 1.0 <= ours.diameter[fired[0]] < 1.02

    for run in ("test31", "test33"):
        _, _, wide, _, spacing = _spacing_run(run)
        assert np.all(wide.diameter < spacing), f"{run} must stay clear"


@pytest.mark.golden
def test_merging_costs_accuracy_at_moderate_overlap_and_that_is_the_trade() -> None:
    """⚠️ **Renamed and re-baselined 2026-08-21**, when the default became `ALL`.

    It was `test_merging_costs_no_accuracy_against_the_unmerged_control`, and it asserted test32's
    overall dilution error below 1 % and its late window no worse than test31's -- the unmerged
    control at a spacing wide enough never to merge. Under the confined-decrement default that is
    **false**: test32 goes to 1.83 % overall, and row 157 is now a recorded divergence.

    ⛔ **The old assertion is not something to restore.** test32's 1.01 % sat *below* its own
    unmerged control's 1.39 %, and an error smaller than the same case run with no merging at all
    is the signature of cancelling errors rather than of correctness. A test whose name asserts a
    reading the ledger has retracted is a documented failure mode of this project -- it has
    happened twice before -- so the name goes with the number.

    ⭐ What replaces the bar is `case44`, six spacings against a **single-port** control instead of
    one shallow run against a 2 m spacing that still trips the limiting-spacing rule. The trade
    this test now pins: the confined reading costs accuracy at moderate overlap and wins by an
    order of magnitude past `d/L` ~ 3.
    """
    errors = {}
    for run in ("test32", "test31"):
        frame, steps, ours, usable, _ = _spacing_run(run)
        theirs = frame["Dilutn"].to_numpy(dtype=float)[usable]
        error = np.abs(ours.dilution - theirs) / theirs
        errors[run] = (error.mean(), error[steps >= 310].mean())

    # The cost is real and bounded. Pinned both ways so a silent improvement is also a failure:
    # if this drops back under 1 % something has changed the default back.
    assert 0.012 < errors["test32"][0] < 0.025, f"test32 overall: {errors['test32'][0]}"
    # ⚠️ And the control is *unmerged*, so it must not move at all -- merging cannot reach it.
    assert errors["test31"][0] < 0.01, f"the unmerged control moved: {errors['test31'][0]}"


@pytest.mark.golden
def test_the_merged_element_inflates_as_the_exe_reports() -> None:
    """eq 56 is observable: the merged run reaches a *larger* diameter while entraining less.

    test32 peaks at 2.351 m against test31's 1.967 m, despite merging suppressing its
    entrainment -- the element is confined transversely and grows vertically instead. Getting
    the implicit angle wrong left our peak at 1.971 m, i.e. no inflation at all.

    ⚠️ **The tolerance moved from 2 % to 3 % on 2026-08-21**, when the default became `ALL`: the
    diameter error on this run goes 1.9 % to **2.05 %**. The *claim* is unchanged and is what this
    test is for -- the element inflates, and by roughly the amount the exe reports -- and the
    inflation floor below is untouched, which is the half that actually discriminates. Row 157's
    dilution number is where the trade shows up, not here.
    """
    frame, _, ours, usable, _ = _spacing_run("test32")
    theirs = frame["P-dia"].to_numpy(dtype=float)[usable]
    assert (np.abs(ours.diameter - theirs) / theirs).mean() < 0.03
    assert ours.diameter.max() > 2.2, "the element must actually inflate"

    _, _, control, _, _ = _spacing_run("test31")
    assert ours.diameter.max() > control.diameter.max() * 1.15


ANGLE_SWEEP = CASES / "case16_oldbuild_angle_sweep"


@pytest.mark.golden
def test_the_merge_trigger_needs_no_fitted_constant_at_85_degrees() -> None:
    """The bracket that killed every static law, reproduced by the derived one.

    test19 discharges at 175 deg into a 90 deg current -- an **85 degree** offset -- and its
    merge banner is bracketed at output interval 1 to `diameter/spacing` of 0.5985-0.6015.
    That single measurement excludes `cos`, `cos**0.5`, `cos**(2/3)` and `(1+cos)/2`, and is
    what the fitted ellipse `sqrt(cos^2 + 0.596^2 sin^2)` was tuned to hit.

    Resolving the spacing against the plume's **instantaneous heading** reproduces it with no
    fitted constant at all: merging fires while the plume has swung only from 175 deg to about
    122 deg, so it still presents most of its aspect to its neighbours. Bracketed tightly here
    because landing inside 0.5985-0.6015 by accident is not plausible.
    """
    case = _baseline().model_copy(
        update={
            "diffuser": _baseline().diffuser.model_copy(
                update={"n_ports": 25, "port_spacing": 2.0, "horizontal_angle": 175.0}
            ),
            "effluent": _baseline().effluent.model_copy(update={"flow": 0.005}),
        }
    )
    parsed = read_dat(ANGLE_SWEEP / "test19.dat")
    merges = [e for e in parsed.events if e.text.strip().lower().startswith("merging")]
    assert len(merges) == 1
    step = merges[0].next_step
    diameters = parsed.nearfield["P-dia"]
    low = float(diameters.loc[step - 1]) / 2.0
    high = float(diameters.loc[step]) / 2.0
    assert (low, high) == pytest.approx((0.5985, 0.6015), abs=5e-4), "the archived bracket"

    solution = integrate(case, max_time=250.0)
    times = np.linspace(0.0, solution.solution.t[-1], 20000)
    ours = solution.sample(times)
    raw = solution.solution.sol(times)
    velocity = raw[1:4] / raw[0]
    spacing = np.array(
        [
            2.0 * effective_half_spacing(2.0, 175.0 + 90.0, velocity[:, i])
            for i in range(times.size)
        ]
    )
    fired = np.flatnonzero(ours.diameter >= spacing)
    assert fired.size, "test19 must merge"
    assert low <= ours.diameter[fired[0]] / 2.0 <= high, ours.diameter[fired[0]] / 2.0


PREDICTION = CASES / "case21_merging_spacing_prediction"

#: (run, spacing, source case) at a fixed 85 degree offset -- only the spacing changes.
SPACING_PREDICTION = (
    ("test19", 2.0, ANGLE_SWEEP),
    ("test35", 1.5, PREDICTION),
    ("test34", 1.0, PREDICTION),
)


def _merge_bracket(directory: Path, run: str, spacing: float) -> tuple[float, float]:
    """`diameter/spacing` on the rows either side of the exe's merging banner."""
    parsed = read_dat(directory / f"{run}.dat")
    merges = [e for e in parsed.events if e.text.strip().lower().startswith("merging")]
    assert len(merges) == 1, run
    step = merges[0].next_step
    diameters = parsed.nearfield["P-dia"]
    return float(diameters.loc[step - 1]) / spacing, float(diameters.loc[step]) / spacing


def _predicted_trigger(spacing: float) -> float:
    """Where our closure fires, as `diameter/spacing`, on test19's geometry."""
    base = _baseline()
    case = base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(
                update={"n_ports": 25, "port_spacing": spacing, "horizontal_angle": 175.0}
            ),
            "effluent": base.effluent.model_copy(update={"flow": 0.005}),
        }
    )
    solution = integrate(case, max_time=250.0)
    times = np.linspace(0.0, solution.solution.t[-1], 20000)
    ours = solution.sample(times)
    velocity = solution.solution.sol(times)[1:4] / solution.solution.sol(times)[0]
    effective = np.array(
        [
            2.0 * effective_half_spacing(spacing, 175.0 + 90.0, velocity[:, i])
            for i in range(times.size)
        ]
    )
    fired = np.flatnonzero(ours.diameter >= effective)
    assert fired.size, spacing
    return float(ours.diameter[fired[0]] / spacing)


@pytest.mark.slow
@pytest.mark.golden
def test_the_merge_trigger_tracks_the_spacing_as_predicted() -> None:
    """case21 was run to test this *before* the runs existed, and it holds.

    At one fixed 85 degree offset the old fitted ellipse must predict a single number, 0.600.
    Resolving the spacing against the plume's instantaneous heading predicts a **curve**,
    because a wider spacing means merging fires later with the plume further turned. Changing
    only the spacing therefore separates the two, and the exe follows the curve:

    | spacing | exe bracket | derived | ellipse |
    |---|---|---|---|
    | 2.0 m | 0.5985-0.6015 | 0.5991 | 0.600 |
    | 1.5 m | 0.6760-0.6800 | 0.6751 | 0.600 |
    | 1.0 m | 0.7700-0.7780 | 0.7750 | 0.600 |
    """
    ellipse = math.hypot(math.cos(math.radians(85.0)), 0.596 * math.sin(math.radians(85.0)))
    triggers = []
    for run, spacing, directory in SPACING_PREDICTION:
        low, high = _merge_bracket(directory, run, spacing)
        ours = _predicted_trigger(spacing)
        triggers.append((spacing, low, high, ours))
        # Within the bracket, or just outside it by less than our own trajectory error.
        assert low - 0.002 <= ours <= high + 0.002, f"{run}: {ours:.4f} vs {low:.4f}-{high:.4f}"

    # The measured trigger rises as the spacing narrows -- the effect a static law denies.
    assert [t[3] for t in triggers] == sorted(t[3] for t in triggers)
    widest, narrowest = triggers[0], triggers[-1]
    assert narrowest[1] > widest[2] * 1.25, "the two ends must be decisively different"
    # The fitted ellipse survives only at the spacing it was tuned on.
    assert widest[1] <= ellipse <= widest[2]
    for _, low, high, _ in triggers[1:]:
        assert not low <= ellipse <= high, "the ellipse must be excluded by the new runs"


@pytest.mark.slow
@pytest.mark.golden
def test_the_near_field_ends_where_the_exe_stops() -> None:
    """The switch counts turning points, and that reproduces the end of the run.

    Every project here uses `max_rise_or_fall = 3`, so the near field ends on the **fourth**
    turning point. Across the archive 28 of 31 traces do exactly that; the exceptions are the
    other benchmarks firing first (a seabed hit, a surface hit, the 5000-step cap).

    A few percent is the bar, not a few tenths: this is the *accumulated* trajectory error at
    the end of four oscillations, long past the jet where the model is tightest.
    """
    runs = (
        ("test23", ZERO_CURRENT, {"ports": 1, "flow": 5.0e-5, "current": 0.0}),
        ("test30", SWEEP, {"ports": 1, "flow": 5.0e-5, "current": 0.10}),
        ("test32", SPACING, {"ports": 25, "flow": 0.005, "current": 0.02, "spacing": 1.0}),
    )
    for run, directory, spec in runs:
        frame = read_dat(directory / f"{run}.dat").nearfield
        theirs = float(frame["Time"].to_numpy(dtype=float)[-1])
        case = _variant(ports=spec["ports"], flow=spec["flow"], current=spec["current"])
        if "spacing" in spec:
            diffuser = case.diffuser.model_copy(update={"port_spacing": spec["spacing"]})
            case = case.model_copy(update={"diffuser": diffuser})
        case = case.model_copy(
            update={"near_field": case.near_field.model_copy(update={"max_rise_or_fall": 3})}
        )
        solution = integrate(case, max_time=theirs * 3.0 + 50.0)
        assert solution.reason == "oscillation limit", run
        assert len(solution.oscillations) >= 4, run
        assert abs(solution.end_time - theirs) / theirs < 0.06, (
            f"{run}: {solution.end_time:.1f} vs {theirs:.1f}"
        )


@pytest.mark.golden
def test_the_turning_points_alternate_between_trapping_and_reversal() -> None:
    """The structure the whole rule rests on: the plume rings about its trapping level.

    A crossing of neutral buoyancy has to be followed by a velocity reversal before the next
    crossing, because the plume must turn round to come back. If that alternation broke, the
    switch would be counting something else.
    """
    solution = integrate(_test23(), max_time=160.0)
    kinds = [event.kind for event in solution.oscillations[:6]]
    assert len(kinds) >= 4
    for first, second in itertools.pairwise(kinds):
        assert first != second, kinds
