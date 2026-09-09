"""Merging geometry -- eqs 51-56."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from plumes2.io.dat import read_dat
from plumes2.nearfield.merging import (
    MERGING_FLOOR_DEGREES,
    ConfinedDecrements,
    effective_half_spacing,
    merged_radius,
    merging_factors,
    overlap_angle,
)

EAST = np.array([1.0, 0.0, 0.0])


def test_the_overlap_angle_opens_from_first_contact() -> None:
    """Zero when the circles touch, and rising thereafter, in both variants."""
    for faithful in (True, False):
        assert overlap_angle(0.5, 0.5, faithful=faithful) == 0.0
        assert overlap_angle(0.4, 0.5, faithful=faithful) == 0.0, "clear of each other"
        opening = [overlap_angle(r, 0.5, faithful=faithful) for r in (0.6, 0.8, 1.2, 2.0)]
        assert opening == sorted(opening)
        assert all(0.0 < a < math.pi / 2 for a in opening)

    # The true geometry saturates at pi/2 for total overlap; the exe's arctan form does not,
    # which is one more way to see that it is not a reparameterisation but a mistake.
    assert overlap_angle(1.0, 0.5, faithful=False) == pytest.approx(math.acos(0.5))
    assert overlap_angle(1e6, 0.5, faithful=False) == pytest.approx(math.pi / 2, abs=1e-6)


def test_every_factor_is_one_at_first_contact_and_falls_after() -> None:
    """The sanity check the whole module hangs on."""
    touching = merging_factors(0.5, 0.5, 25)
    assert not touching.merged
    for value in (touching.taylor, touching.cylinder, touching.curvature):
        assert value == pytest.approx(1.0)

    previous = (1.0, 1.0, 1.0)
    for radius in (0.55, 0.7, 1.0, 2.0):
        f = merging_factors(radius, 0.5, 25)  # shipped default
        assert f.merged
        current = (f.taylor, f.cylinder, f.curvature)
        assert all(0.0 <= c < p for c, p in zip(current, previous, strict=True)), radius
        previous = current


def test_the_factors_follow_the_published_equations() -> None:
    """eqs 51, 53, 54 against a hand-evaluated overlap.

    `faithful=False` because this checks the *published* equations; the shipped default
    reproduces the exe's arctan bug instead. See `overlap_angle`.
    """
    radius, half_spacing = 1.0, 0.5
    phi = math.acos(0.5)
    f = merging_factors(radius, half_spacing, 25, faithful=False)
    assert f.taylor == pytest.approx(1.0 - 2.0 * phi / math.pi)
    assert f.cylinder == pytest.approx(half_spacing / radius)
    assert f.curvature == pytest.approx(f.taylor + math.sin(2.0 * phi) / math.pi)
    assert f.out_of_plane == pytest.approx(1.0 / 25)


def test_a_single_port_never_merges() -> None:
    for radius in (0.5, 5.0, 50.0):
        f = merging_factors(radius, 0.5, 1)
        assert not f.merged
        assert (f.taylor, f.cylinder, f.curvature, f.out_of_plane) == (1.0, 1.0, 1.0, 1.0)


def test_the_out_of_plane_share_waits_for_merging() -> None:
    """An unmerged multiport diffuser behaves as independent single plumes.

    That is what licenses using the 25-port runs to pin single-plume physics, and getting it
    wrong silently divided case14's out-of-plane term by 18 across its whole rise.
    """
    assert merging_factors(0.4, 0.5, 18).out_of_plane == 1.0
    assert merging_factors(0.6, 0.5, 18).out_of_plane == pytest.approx(1.0 / 18)


def test_the_merged_element_grows_taller_than_the_round_one() -> None:
    """eq 56. Confinement between reflecting planes has to go somewhere."""
    assert merged_radius(0.5, 0.5) == pytest.approx(0.5), "untouched before contact"
    for radius in (0.6, 1.0, 2.0):
        assert merged_radius(radius, 0.5) > radius
    # Monotone in the overlap.
    inflations = [merged_radius(r, 0.5) / r for r in (0.6, 0.8, 1.2, 2.0)]
    assert inflations == sorted(inflations)


def test_the_merged_radius_conserves_the_cross_sectional_area() -> None:
    """eq 55 is the statement being inverted, so it must round-trip.

    `phi` is taken at the **merged** radius, which is the whole point -- evaluating it at the
    unmerged one does not satisfy eq 55 and under-inflates by 12 % at deep overlap.
    """
    for unmerged in (0.6, 0.9, 1.5):
        merged = merged_radius(unmerged, 0.5)
        phi = overlap_angle(merged, 0.5, faithful=False)
        rounded_rectangle = merged * merged * (math.pi - 2.0 * phi + math.sin(2.0 * phi))
        assert rounded_rectangle == pytest.approx(math.pi * unmerged * unmerged, rel=1e-9)

        stale = overlap_angle(unmerged, 0.5, faithful=False)
        assert merged * merged * (math.pi - 2.0 * stale + math.sin(2.0 * stale)) != pytest.approx(
            math.pi * unmerged * unmerged, rel=1e-3
        )


def test_the_effective_spacing_foreshortens_with_the_plume_direction() -> None:
    """`s = (L/2)|sin psi|` against the *plume's* heading, not the current's."""
    # Axis east, plume heading north: fully across the diffuser, nothing foreshortened.
    assert effective_half_spacing(2.0, 0.0, np.array([0.0, 1.0, 0.0])) == pytest.approx(1.0)
    # Plume at 30 degrees to the axis.
    oblique = math.radians(30.0)
    heading = np.array([math.cos(oblique), math.sin(oblique), 0.0])
    assert effective_half_spacing(2.0, 0.0, heading) == pytest.approx(math.sin(oblique))


def test_the_effective_spacing_has_a_floor() -> None:
    """A plume running along the diffuser would otherwise see the spacing vanish."""
    floor = math.sin(math.radians(MERGING_FLOOR_DEGREES))
    for bearing in (0.0, 5.0, 179.0, 180.0):
        radians = math.radians(bearing)
        along = np.array([math.cos(radians), math.sin(radians), 0.0])
        assert effective_half_spacing(2.0, 0.0, along) == pytest.approx(floor)


def test_a_vertical_plume_is_not_foreshortened() -> None:
    """No horizontal aspect means no projection, and no division by zero."""
    assert effective_half_spacing(2.0, 0.0, np.array([0.0, 0.0, 1.0])) == pytest.approx(1.0)


def test_the_faithful_overlap_angle_reproduces_the_um3_bug() -> None:
    """UM3 divides inside the radical, which equals the real thing only at `s = 1 m`.

    The default is the faithful (buggy) form, because the exe has it -- see `overlap_angle`
    for the test32 evidence.
    """
    assert overlap_angle(1.4, 1.0, faithful=True) == pytest.approx(
        overlap_angle(1.4, 1.0, faithful=False)
    ), "the two agree exactly at s = 1 m, which is why it hid"
    assert overlap_angle(1.4, 1.0) == pytest.approx(overlap_angle(1.4, 1.0, faithful=True))
    for radius, half_spacing in ((0.52, 0.5), (0.9, 0.5), (2.0, 0.5)):
        assert overlap_angle(radius, half_spacing, faithful=True) < overlap_angle(
            radius, half_spacing, faithful=False
        ), "the bug weakens the suppression"


# ------------------------------------------- the limiting-spacing rule, case22 (unimplemented)

LIMITING = Path(__file__).resolve().parents[2] / "reference_cases" / "case22_limiting_spacing"


@pytest.mark.golden
def test_a_single_plume_is_declared_merged_once_it_is_wide_enough() -> None:
    """case22, predicted in advance and confirmed: the rule exists and has no port-count guard.

    One port cannot merge with anything, so a `merging happened` banner can only come from
    UM3's limiting-spacing rule -- a limiting spacing equal to the port depth, imposed once the
    element diameter exceeds twice that depth. The shallow run prints one; the control, with
    the threshold moved out of reach, does not.

    ⚠️ **Not implemented.** The constant is not pinned: the banner lands at 2.28x the port
    depth, not the 2.00x the source implies, and it coincides with the first trapping, so
    "the constant is 2.28" and "the check is gated on trapping" both fit. See PLAN.md §7c.
    """
    shallow = read_dat(LIMITING / "limspc_shallow.dat")
    control = read_dat(LIMITING / "limspc_deep_control.dat")

    def banner(parsed):  # type: ignore[no-untyped-def]
        return [e for e in parsed.events if e.text.strip().lower().startswith("merging")]

    assert len(banner(shallow)) == 1, "a single port merged"
    assert not banner(control), "and the control did not"

    step = banner(shallow)[0].next_step
    diameter = float(shallow.nearfield["P-dia"].loc[step])
    assert diameter / 1.0 == pytest.approx(2.277, abs=0.01), "2.28x the 1 m port depth"
    # The ambiguity, pinned so it cannot be quietly forgotten: the threshold was crossed well
    # before the banner, and the first trapping lands on the very same step.
    crossed = shallow.nearfield.index[shallow.nearfield["P-dia"] >= 2.0][0]
    assert crossed < step, "diameter passed 2 x port depth before the banner"
    traps = [e for e in shallow.events if e.text.strip().lower().startswith("plume traps")]
    assert traps[0].next_step == step, "the first trap coincides -- this is the ambiguity"


@pytest.mark.golden
def test_the_rule_caps_a_runaway_we_do_not_yet_cap() -> None:
    """Why it matters: the exe's merged element stops growing and ours does not (row 186)."""
    for run, ours in (("limspc_shallow", 8.1), ("limspc_deep_control", 7.2)):
        theirs = float(read_dat(LIMITING / f"{run}.dat").nearfield["P-dia"].max())
        assert theirs < ours * 0.75, f"{run}: exe {theirs:.2f} m against our {ours} m"


GAP = Path(__file__).resolve().parents[2] / "reference_cases" / "case23_limiting_spacing_gap"


@pytest.mark.golden
def test_the_limiting_spacing_trigger_is_the_port_depth() -> None:
    """The threshold is `diameter > port depth`, on three runs differing only in port depth.

    What this pins is the **threshold**: every trap that fired sits above every trap that did
    not, and the gap straddles 1.0, knife-edged at 1.014.

    ⚠️ **The "at trapping" half of the original reading is retracted** -- this test was
    called `..._is_the_port_depth_at_trapping` and asserted the banner lands on the first trap.
    In these three runs it does, but only because the trap and the crossing coincide; case30's
    `gap_1` separated them for the first time and traps at a ratio of 0.7804 **without firing**,
    with the banner landing one step after the diameter crosses the port depth. The check is
    **continuous** (row 191).

    ⚠️ The threshold still differs from the Visual Plumes source, which checks
    `diameter > 2 * depth`. PLUMES2.0 is not simply that UM3.
    """
    runs = (
        ("limspc_shallow", 1.0, LIMITING),
        ("limspc_gap", 2.0, GAP),
        ("limspc_deep_control", 5.0, LIMITING),
    )
    fired, quiet = [], []
    for run, port_depth, directory in runs:
        parsed = read_dat(directory / f"{run}.dat")
        frame = parsed.nearfield

        def steps(prefix: str, parsed=parsed) -> list[int]:
            return [e.next_step for e in parsed.events if e.text.strip().lower().startswith(prefix)]

        traps, banners = steps("plume traps"), steps("merging")
        assert len(banners) <= 1

        if banners:
            # In *these* runs the trap and the crossing coincide, which is exactly why
            # they could not settle continuity -- case30 is what separated them.
            assert banners[0] == traps[0], f"{run}: trap and crossing coincide here"
            # Not continuous: the diameter passed the port depth well before the banner.
            crossed = frame.index[frame["P-dia"] >= port_depth]
            assert crossed[0] <= banners[0], run
        for step in traps:
            ratio = float(frame["P-dia"].loc[step]) / port_depth
            (fired if step in banners else quiet).append(ratio)

    # Every trap that fired sits above every trap that did not, and the gap straddles 1.0.
    assert min(fired) > max(r for r in quiet if r < min(fired)), "the threshold is separable"
    assert max(r for r in quiet if r < min(fired)) < 1.0 <= min(fired) * 1.02
    assert min(fired) == pytest.approx(1.014, abs=0.005), "the knife-edge that pins it"


@pytest.mark.golden
def test_the_shallow_run_lags_its_crossing_by_fifty_steps() -> None:
    """The banner lags the `diameter > port depth` crossing by 54 steps -- row 191b's lag.

    ⚠️ **This test used to be called `test_the_shallow_run_refutes_a_continuous_check`,
    and that reading is retracted.** case30 separated the trap from the crossing for the first
    time and showed the check *is* continuous (row 191); case34 then showed the multiport trigger
    fires on the crossing with **zero** lag, so the lag belongs to the single-port
    limiting-spacing path alone. What this run actually pins is the size of that lag, which is
    still unexplained -- not a refutation of continuity.
    """
    parsed = read_dat(LIMITING / "limspc_shallow.dat")
    frame = parsed.nearfield
    banner = next(
        e.next_step for e in parsed.events if e.text.strip().lower().startswith("merging")
    )
    crossed = int(frame.index[frame["P-dia"] >= 1.0][0])  # 1.0 m = its port depth
    assert crossed == 126
    assert banner == 180
    assert banner - crossed > 50, "the single-port lag row 191b cannot yet explain"


# ------------------------------------------------------- the brake, rows 264-264d


def test_the_default_takes_every_decrement_at_the_round_radius() -> None:
    """`ConfinedDecrements.NONE` is what the port ships, and it must not have moved.

    Every golden row in phases 5 and 6 was measured with the decrements at `b_r`. The brake is a
    candidate recorded with its cost (row 264c), not an adopted fix, so the shipped path has to be
    bit-identical to what it was before `ConfinedDecrements` existed -- including `growth_factor`
    falling back to `taylor`, which is what the reference states: "the same correction factor
    applies to the growth entrainment term".
    """
    for radius in (0.55, 0.7, 1.0, 2.0, 8.0):
        plain = merging_factors(radius, 0.5, 25)
        explicit = merging_factors(
            radius,
            0.5,
            25,
            confined_radius=merged_radius(radius, 0.5),
            confined=ConfinedDecrements.NONE,
        )
        assert plain == explicit, radius
        assert plain.growth is None
        assert plain.growth_factor == plain.taylor


def test_the_confined_brake_saturates_the_growth_area() -> None:
    """Row 264's mechanism, as an identity rather than as a trace comparison.

    The runaway is an asymmetry: the decrements are evaluated at `b_r` while every entrainment
    area is built from the confined `b`, so eq 56's inflation factor enters un-opposed. The growth
    area carries `pi b db`, so what matters is the product `a_T * pi * b`, and the two readings
    have different **asymptotes**:

    * at `b_r` the product **diverges** linearly in `b_r/s`;
    * at `b` it converges to a **constant**, so the growth area stops depending on the radius.

    A constant is the whole point: no coefficient can remove a finite-time singularity, it can
    only reschedule `t_c = 1/(k b_0)`. Changing the asymptote is what removes it.

    Both angles are checked, because the constant is **not the same one** -- see
    `test_the_saturation_constant_is_a_width_only_in_the_true_geometry`.
    """
    half_spacing = 0.25
    for faithful in (True, False):
        braked: list[float] = []
        unbraked: list[float] = []
        for ratio in (2.0, 5.0, 8.0, 12.0, 20.0):
            round_radius = ratio * half_spacing
            confined = merged_radius(round_radius, half_spacing)
            at_round = merging_factors(round_radius, half_spacing, 25, faithful=faithful)
            at_confined = merging_factors(
                round_radius,
                half_spacing,
                25,
                faithful=faithful,
                confined_radius=confined,
                confined=ConfinedDecrements.ALL,
            )
            braked.append(at_confined.taylor * math.pi * confined)
            unbraked.append(at_round.taylor * math.pi * confined)

        # Braked: converged. The last two samples agree to four decimals across a near-doubling
        # of the overlap, and every sample past `d/L` 5 sits inside a 1 % band. ⚠️ Not asserted
        # as monotone -- the true geometry approaches its limit from **above** (0.509 -> 0.500)
        # and the exe's from below (0.931 -> 1.000), so a direction would encode the angle bug.
        # The `d/L` 2 sample is excluded from the band: that is the approach, not the plateau.
        assert braked[-1] == pytest.approx(braked[-2], abs=1e-4), (faithful, braked)
        assert max(braked[1:]) / min(braked[1:]) < 1.01, (faithful, braked)
        # Unbraked: still climbing at the last sample, and by a wide margin -- not a tolerance
        # question. At `d/L` 20 it is more than fifteen times the braked plateau.
        assert unbraked[-1] > unbraked[-2] * 1.4, (faithful, unbraked)
        assert unbraked[-1] / braked[-1] > 15.0, (faithful, unbraked, braked)


def test_the_saturation_constant_is_a_width_only_in_the_true_geometry() -> None:
    """⚠️⚠️ The slab reading holds for `arccos` and **not** for the exe's `arctan`.

    Row 264's argument was written as "the decremented growth area becomes a slab of the
    diffuser's own width", which is exact -- for the *true* geometry. There
    `a_T(b) -> (2/pi)(s/b)`, so `a_T * pi * b -> 2s = L`.

    The shipped default takes `phi` from UM3's buggy `arctan(sqrt((b^2 - s^2)/s))` (row 179), and
    that limit is **`2 sqrt(s)`** instead -- a length in the square root of metres, which is not a
    width at all. The bug's dimensional inconsistency survives into the asymptote. The two
    coincide only at `s = 1 m`, which is why a single half-spacing could not have told them apart.

    ⭐ **And it is a lead on row 264b's 0.06 offset**: if the exe brakes this way its saturation
    level scales as `sqrt(s)` rather than `s`, so the plateau should move with the spacing. case41
    has three spacings, so that is measurable without a new run.
    """
    for half_spacing in (0.25, 0.375, 1.0):
        deep = 100.0 * half_spacing
        confined = merged_radius(deep, half_spacing)
        true_angle = merging_factors(
            deep,
            half_spacing,
            25,
            faithful=False,
            confined_radius=confined,
            confined=ConfinedDecrements.ALL,
        )
        exe_angle = merging_factors(
            deep,
            half_spacing,
            25,
            faithful=True,
            confined_radius=confined,
            confined=ConfinedDecrements.ALL,
        )
        assert true_angle.taylor * math.pi * confined == pytest.approx(
            2.0 * half_spacing, abs=1e-3
        ), half_spacing
        assert exe_angle.taylor * math.pi * confined == pytest.approx(
            2.0 * math.sqrt(half_spacing), abs=1e-3
        ), half_spacing


def test_braking_the_growth_term_alone_leaves_the_other_three_untouched() -> None:
    """Row 264d's candidate is exactly one factor different from the default, and no more.

    It was refuted -- the suppression still crosses 1.0, because the Taylor term leaks the same
    inflation factor -- but the switch has to isolate what it claims to isolate, or the refutation
    measures something else.
    """
    radius, half_spacing = 1.0, 0.25
    confined = merged_radius(radius, half_spacing)
    default = merging_factors(radius, half_spacing, 25)
    braked = merging_factors(
        radius, half_spacing, 25, confined_radius=confined, confined=ConfinedDecrements.GROWTH
    )
    assert braked.taylor == default.taylor
    assert braked.cylinder == default.cylinder
    assert braked.curvature == default.curvature
    assert braked.out_of_plane == default.out_of_plane
    # Only the growth decrement moves, and it moves **down** -- the confined element is wider, so
    # more of its circumference is occluded.
    assert braked.growth is not None
    assert 0.0 <= braked.growth < default.taylor
    assert braked.growth_factor == braked.growth


def test_a_brake_without_the_confined_radius_is_refused() -> None:
    """The confined half-height is not optional once a brake is selected.

    Defaulting it to the round radius would make `ALL` silently equal to `NONE`, so row 264 would
    measure the default and report it as the brake. Louder to refuse.
    """
    for confined in (ConfinedDecrements.GROWTH, ConfinedDecrements.ALL):
        with pytest.raises(ValueError, match="confined half-height"):
            merging_factors(1.0, 0.25, 25, confined=confined)
    # And a single port short-circuits before the check, because nothing merges there at all.
    assert merging_factors(1.0, 0.25, 1, confined=ConfinedDecrements.ALL).taylor == 1.0
