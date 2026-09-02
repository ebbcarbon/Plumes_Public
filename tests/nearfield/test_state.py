"""The LCV state vector, its geometry, and the conventions the traces establish."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.nearfield import (
    STATE_SIZE,
    exit_speed,
    horizontal_unit,
    initial_radius,
    initial_state,
    unpack,
    velocity_vector,
)

CASES = Path(__file__).resolve().parents[2] / "reference_cases"
MACOMA_PRJ = CASES / "case01_macoma_cms" / "Macoma2.prj"
TEST19 = CASES / "case16_oldbuild_angle_sweep" / "test19.dat"
ZERO_CURRENT = CASES / "case18_zero_current_pair"


@pytest.fixture
def macoma_case():  # type: ignore[no-untyped-def]
    return load_project(MACOMA_PRJ, warn_on_drift=False).to_case()


# ------------------------------------------------------------------ conventions


def test_bearings_are_cos_sin_not_compass() -> None:
    """test19's 90 deg current drives +y and its 175 deg jet drives -x."""
    np.testing.assert_allclose(horizontal_unit(0.0), [1.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(horizontal_unit(90.0), [0.0, 1.0], atol=1e-12)
    east_of_north = horizontal_unit(175.0)
    assert east_of_north[0] < -0.99, "a 175 deg bearing must point almost entirely to -x"
    assert east_of_north[1] > 0.0


@pytest.mark.golden
def test_the_bearing_convention_matches_test19s_trajectory() -> None:
    """The sign of the measured displacement must match the convention, on both axes."""
    nearfield = read_dat(TEST19).nearfield
    x = nearfield["x-posn"].to_numpy(dtype=float)
    y = nearfield["y-posn"].to_numpy(dtype=float)
    # Jet at 175 deg -> -x; ambient current at 90 deg -> +y.
    assert x[-1] < -1.0
    assert y[-1] > 1.0
    jet = horizontal_unit(175.0)
    current = horizontal_unit(90.0)
    assert jet[0] < 0.0 and x[-1] < 0.0
    assert current[1] > 0.0 and y[-1] > 0.0


def test_vertical_angle_is_positive_upward() -> None:
    velocity = velocity_vector(1.0, 45.0, 0.0)
    assert velocity[2] == pytest.approx(math.sin(math.radians(45.0)))
    assert velocity[0] == pytest.approx(math.cos(math.radians(45.0)))
    assert velocity_vector(1.0, -45.0, 0.0)[2] < 0.0
    assert velocity_vector(1.0, 90.0, 123.0)[2] == pytest.approx(1.0)


def test_speed_is_preserved_by_the_angle_decomposition() -> None:
    for vertical in (-90.0, -45.0, 0.0, 30.0, 90.0):
        for horizontal in (0.0, 45.0, 175.0, 300.0):
            assert float(np.linalg.norm(velocity_vector(2.5, vertical, horizontal))) == (
                pytest.approx(2.5)
            )


# ------------------------------------------------------------------- initial state


def test_exit_speed_uses_the_contracted_area(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """Macoma: 0.005 m3/s through 25 ports of 0.0127 m, contracted by 0.61."""
    geometric = macoma_case.effluent.flow / (
        macoma_case.diffuser.n_ports * math.pi * (macoma_case.diffuser.port_diameter / 2) ** 2
    )
    assert geometric == pytest.approx(1.5788, abs=1e-4)
    assert exit_speed(macoma_case) == pytest.approx(geometric / 0.61, rel=1e-9)


def test_the_contraction_coefficient_scales_area_so_radius_carries_its_root(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """Measured from test23 vs test25, which differ only in `c`."""
    assert macoma_case.near_field.contraction_coefficient == pytest.approx(0.61)
    port_radius = macoma_case.diffuser.port_diameter / 2.0
    assert initial_radius(macoma_case) == pytest.approx(port_radius * math.sqrt(0.61))
    # The jet area is exactly c times the port area.
    assert math.pi * initial_radius(macoma_case) ** 2 == pytest.approx(
        0.61 * math.pi * port_radius**2
    )


def test_the_thickness_constant_is_independent_of_contraction(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """`b_0^2 rho_e |U_0| = rho_e Q / (n pi)`: the `sqrt(c)` and `1/c` cancel.

    This is why test23 and test25 measure thickness constants 0.25 % apart despite a 64 %
    change in the contraction coefficient, and it is the relation that recovers each
    archived run's flow rate to about 1 %.
    """
    expected = None
    for contraction in (0.2, 0.61, 1.0):
        case = macoma_case.model_copy(
            update={
                "near_field": macoma_case.near_field.model_copy(
                    update={"contraction_coefficient": contraction}
                )
            }
        )
        state, geometry = initial_state(case)
        radius = float(geometry.radius(state.mass, state.density(), state.speed))
        constant = radius**2 * state.density() * state.speed
        closed_form = (
            state.density() * case.effluent.flow / (case.diffuser.n_ports * math.pi)
        )
        assert constant == pytest.approx(closed_form, rel=1e-9)
        if expected is None:
            expected = constant
        else:
            assert constant == pytest.approx(expected, rel=1e-9)


def test_initial_state_sits_at_the_port(macoma_case) -> None:  # type: ignore[no-untyped-def]
    state, geometry = initial_state(macoma_case)
    assert state.position[2] == pytest.approx(-2.0), "z is elevation, negative below surface"
    assert state.depth == pytest.approx(2.0)
    assert state.salinity == pytest.approx(35.0)
    assert state.temperature == pytest.approx(10.0)
    assert state.speed == pytest.approx(exit_speed(macoma_case))
    assert geometry.dilution(state.mass) == pytest.approx(1.0)


def test_the_geometry_reproduces_the_initial_radius(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """The algebraic radius must return `b_0` when evaluated at the port state."""
    state, geometry = initial_state(macoma_case)
    radius = geometry.radius(state.mass, state.density(), state.speed)
    assert float(radius) == pytest.approx(initial_radius(macoma_case))


@pytest.mark.golden
@pytest.mark.parametrize(
    ("dat", "contraction", "expected_diameter"),
    [("test23", 0.61, 0.010), ("test25", 1.0, 0.013)],
)
def test_contraction_sets_the_printed_initial_diameter(
    dat: str, contraction: float, expected_diameter: float
) -> None:
    """test23 and test25 differ only in `c`, and their step-1 diameters differ accordingly.

    Both are single-port, zero-ambient-current runs at output interval 1. The port diameter
    is 0.0127 m -- the diffuser echo's "0.01" is a two-decimal rounding.
    """
    nearfield = read_dat(ZERO_CURRENT / f"{dat}.dat").nearfield
    assert float(nearfield["P-dia"].iloc[0]) == pytest.approx(expected_diameter, abs=5e-4)
    predicted = 2.0 * (0.0127 / 2.0) * math.sqrt(contraction)
    assert round(predicted, 3) == pytest.approx(expected_diameter, abs=5e-4)


@pytest.mark.golden
def test_the_baseline_project_confirms_what_the_traces_implied() -> None:
    """Four values were inferred from test21-test26 alone, then the `.prj` arrived.

    This is the check that the trace-only reasoning was sound, and it is worth keeping as a
    regression: if any of the four inference paths breaks, this fails alongside it.

        port diameter  0.0127  inferred from the test23/test25 contraction pair
        effluent flow  0.005   inferred from the measured thickness constant
        Taylor alpha   0.1     inferred from zero-current entrainment
        contraction    0.61    inferred from the step-1 diameters

    All four matched exactly.

    The file is identified as **test21's configuration by its values, not its timestamp** --
    the exe's save timing is not something we can rely on. It matches test21's echo on every
    field including the distinctive 0.05 m/s bottom-level current, and it cannot describe
    test22-test26, which differ in port count, ambient current or contraction. So it pins
    the *baseline*; the variants' own settings remain measurements anchored to it.

    Note the `.dat` diffuser echo reports the first two values as "0.01" and "0.01" -- it
    prints two decimals -- which is why the echo is not a source of truth.
    """
    case = load_project(ZERO_CURRENT / "test21.prj", warn_on_drift=False).to_case()
    assert case.diffuser.port_diameter == pytest.approx(0.0127)
    assert case.effluent.flow == pytest.approx(0.005)
    assert case.near_field.aspiration_coefficient == pytest.approx(0.1)
    assert case.near_field.contraction_coefficient == pytest.approx(0.61)
    # The settings that make this set usable for Phase 5.
    assert case.near_field.output_interval == 1
    assert case.near_field.max_rise_or_fall == 3

    # And the contraction relation predicts the printed step-1 diameter.
    predicted = 2.0 * initial_radius(case)
    printed = float(read_dat(ZERO_CURRENT / "test21.dat").nearfield["P-dia"].iloc[0])
    assert round(predicted, 3) == pytest.approx(printed, abs=5e-4)


@pytest.mark.golden
def test_the_diffuser_echo_rounds_to_two_decimals() -> None:
    """The trap that produced a spurious factor of 2 in alpha. Pin it so it cannot recur."""
    case = load_project(ZERO_CURRENT / "test21.prj", warn_on_drift=False).to_case()
    echo = read_dat(ZERO_CURRENT / "test21.dat").echoed_tables["Diffuser"]
    assert float(echo["P-dia"].iloc[0]) == pytest.approx(0.01)
    assert case.diffuser.port_diameter == pytest.approx(0.0127)
    assert float(echo["Ttl-flo"].iloc[0]) == pytest.approx(0.01)
    assert case.effluent.flow == pytest.approx(0.005)
    # The results table, by contrast, carries three decimals.
    assert float(read_dat(ZERO_CURRENT / "test21.dat").nearfield["P-dia"].iloc[0]) < 0.0125


def test_the_arbitrary_element_thickness_cancels(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """Only h_0 together with m_e matters, so the reported geometry must not depend on it."""
    reference = None
    for thickness in (0.001, 0.00635, 1.0, 25.0):
        state, geometry = initial_state(macoma_case, element_thickness=thickness)
        radius = float(geometry.radius(state.mass, state.density(), state.speed))
        dilution = float(geometry.dilution(state.mass))
        assert dilution == pytest.approx(1.0)
        if reference is None:
            reference = radius
        else:
            assert radius == pytest.approx(reference, rel=1e-12)
    # The thickness itself does scale, as it must.
    _, thin = initial_state(macoma_case, element_thickness=0.001)
    _, thick = initial_state(macoma_case, element_thickness=1.0)
    assert thick.effluent_mass / thin.effluent_mass == pytest.approx(1000.0)


# ----------------------------------------------------------------------- geometry


def test_pack_and_unpack_round_trip(macoma_case) -> None:  # type: ignore[no-untyped-def]
    state, _ = initial_state(macoma_case)
    packed = state.pack()
    assert packed.shape == (STATE_SIZE,)
    recovered = unpack(packed)
    assert recovered.mass == pytest.approx(state.mass)
    assert recovered.temperature == pytest.approx(state.temperature)
    assert recovered.salinity == pytest.approx(state.salinity)
    np.testing.assert_allclose(recovered.velocity, state.velocity, rtol=1e-12)
    np.testing.assert_allclose(recovered.position, state.position, rtol=1e-12)


def test_unpack_rejects_a_wrong_length_vector() -> None:
    with pytest.raises(ValueError, match="length 9"):
        unpack(np.zeros(7))


def test_unpack_rejects_non_positive_mass() -> None:
    with pytest.raises(ValueError, match="mass must stay positive"):
        unpack(np.zeros(STATE_SIZE))


def test_thickness_and_radius_are_mutually_consistent(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """m = rho_j pi b^2 h must hold for whatever pair the geometry returns."""
    state, geometry = initial_state(macoma_case)
    for mass_factor, speed in ((1.0, 1.5788), (7.0, 0.4), (350.0, 0.02)):
        mass = state.mass * mass_factor
        plume_density = 1024.0
        b = float(geometry.radius(mass, plume_density, speed))
        h = geometry.thickness(mass, plume_density, speed)
        assert plume_density * math.pi * b * b * h == pytest.approx(mass, rel=1e-10)


def test_radius_grows_with_mass_and_shrinks_with_speed(macoma_case) -> None:  # type: ignore[no-untyped-def]
    """b^2 proportional to m / (rho |U|): more mass widens, more speed stretches instead."""
    state, geometry = initial_state(macoma_case)
    base = float(geometry.radius(state.mass, 1024.0, 1.0))
    assert float(geometry.radius(4.0 * state.mass, 1024.0, 1.0)) == pytest.approx(2.0 * base)
    assert float(geometry.radius(state.mass, 1024.0, 4.0)) == pytest.approx(base / 2.0)


def test_radius_refuses_zero_speed(macoma_case) -> None:  # type: ignore[no-untyped-def]
    state, geometry = initial_state(macoma_case)
    with pytest.raises(ValueError, match="zero speed"):
        geometry.radius(state.mass, 1024.0, 0.0)


def test_geometry_is_vectorised(macoma_case) -> None:  # type: ignore[no-untyped-def]
    state, geometry = initial_state(macoma_case)
    radii = geometry.radius(
        np.array([1.0, 4.0, 9.0]) * state.mass, 1024.0, np.array([1.0, 1.0, 1.0])
    )
    assert radii.shape == (3,)
    np.testing.assert_allclose(radii / radii[0], [1.0, 2.0, 3.0], rtol=1e-12)


# ------------------------------------------------- the measured thickness law


@pytest.mark.golden
def test_the_element_thickness_law_holds_on_test19() -> None:
    """`b^2 rho_j |U_j| / D` is constant, which is what fixes `h` proportional to `|U_j|`.

    The competing hypothesis -- constant `h`, giving `b^2 rho_j / D` constant -- varies by a
    factor of 15 over the same span, so the two are not close to each other.
    """
    nearfield = read_dat(TEST19).nearfield
    dilution = nearfield["Dilutn"].to_numpy(dtype=float)
    radius = nearfield["P-dia"].to_numpy(dtype=float) / 2.0
    plume_density = nearfield["P-Den"].to_numpy(dtype=float)
    x = nearfield["x-posn"].to_numpy(dtype=float)
    y = nearfield["y-posn"].to_numpy(dtype=float)
    z = nearfield["Depth"].to_numpy(dtype=float)
    time = nearfield["Time"].to_numpy(dtype=float)

    # Central differences for speed, valid on the interior.
    travelled = np.hypot(np.hypot(x[2:] - x[:-2], y[2:] - y[:-2]), z[2:] - z[:-2])
    # Time is printed to three decimals, so the earliest steps share a timestamp.
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = travelled / (time[2:] - time[:-2])
    interior = slice(1, -1)

    ours = radius[interior] ** 2 * plume_density[interior] * speed / dilution[interior]
    theirs = radius[interior] ** 2 * plume_density[interior] / dilution[interior]

    # Pre-merge (merging happens at step 297) and past the coarse-printing start.
    steps = np.arange(len(dilution))[interior]
    window = (steps > 60) & (steps < 296) & np.isfinite(ours)
    assert window.sum() > 200

    ours_cv = float(ours[window].std() / ours[window].mean())
    theirs_spread = float(theirs[window].max() / theirs[window].min())
    assert ours_cv < 0.07, "h proportional to |U| should hold to within the printing noise"
    assert theirs_spread > 10.0, "constant h should be decisively worse"

    # And the mean must be stable across the trajectory, not merely low-variance locally.
    early = ours[window & (steps < 180)].mean()
    late = ours[window & (steps >= 180)].mean()
    assert abs(late / early - 1.0) < 0.05
