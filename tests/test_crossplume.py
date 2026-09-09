"""The cross-plume profile, against every centreline the archive prints.

`Dilutn / CL-Dil` *is* the peak-to-mean concentration ratio, printed on every row of every trace
that selected both columns, so this module is checked against measurement rather than against
the reference's algebra -- which gets it wrong (3.8889 for the 3/2-power profile it derives,
where the exe uses a parabola's 2.0).
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from plumes2.crossplume import (
    PEAK_TO_MEAN_ROUND,
    PEAK_TO_MEAN_SLAB,
    centreline_dilution,
    exact_peak_to_mean,
    parabolic_weight,
    peak_to_mean,
)
from plumes2.io.dat import read_dat
from plumes2.validation import NON_DEFAULT_PROFILE_TRACES
from tests.conftest import ALL_DAT_PATHS


def printed_tolerance(mean: float, centreline: float, spacing: float) -> float:
    """How much slack three printed decimals leave when comparing the law to the archive.

    Three rounded numbers enter, each to +/-0.0005, and they matter in different regimes:

    * `Dilutn` and `CL-Dil` set the *measured* ratio, whose sensitivity to each is `1/CL` and
      `Dilutn/CL^2` -- so `0.0005 (1 + ratio) / CL`, which is 3e-4 at a centreline of 5 and 3e-6
      at 500.
    * `P-dia` sets the *predicted* one, through `0.5 * d / L`, contributing `0.00025 / L`
      regardless of how large the dilution has grown.

    The second dominates late in a trajectory, which is why a flat tolerance cannot work: test15
    ends at a centreline of 243, where the ratio is pinned to 6e-6 but the diameter alone allows
    1.3e-4. Deriving both is the difference between asserting the law is exact and asserting it
    is close.
    """
    ratio = 5e-4 * (1.0 + mean / centreline) / centreline
    return ratio + (0.5 * 5e-4 / spacing if spacing > 0.0 else 0.0)


# ------------------------------------------------------------------ the two limiting shapes


def test_the_round_and_slab_ratios_are_the_parabola_s_own_integrals() -> None:
    """Both anchors are exact integrals of `1 - u^2`, not fitted constants."""
    radial = np.trapezoid(
        parabolic_weight(u := np.linspace(0.0, 1.0, 200_001)) * 2.0 * u, u
    )  # area-weighted mean over a disc, / (pi b^2) with the pi cancelling
    assert PEAK_TO_MEAN_ROUND == pytest.approx(1.0 / radial, rel=1e-8)
    across = np.trapezoid(parabolic_weight(u), u)
    assert PEAK_TO_MEAN_SLAB == pytest.approx(1.0 / across, rel=1e-8)


def test_the_reference_s_three_halves_power_would_be_nearly_twice_as_peaked() -> None:
    """The 1994 report's own profile gives 3.8889 round, which the exe plainly does not use."""
    u = np.linspace(0.0, 1.0, 200_001)
    shape = (1.0 - u**1.5) ** 2
    assert 1.0 / np.trapezoid(shape * 2.0 * u, u) == pytest.approx(3.8889, abs=5e-4)
    assert 1.0 / np.trapezoid(shape, u) == pytest.approx(2.2222, abs=5e-4)


def test_the_profile_weight_is_one_on_the_centreline_and_zero_past_the_edge() -> None:
    assert parabolic_weight(0.0) == pytest.approx(1.0)
    assert parabolic_weight(1.0) == pytest.approx(0.0)
    # Outside the plume there is no excess to weight, so it floors rather than going negative.
    assert parabolic_weight(np.array([1.5, 3.0])).tolist() == [0.0, 0.0]


# ------------------------------------------------------------------ the blend, and its limits


def test_the_blend_runs_from_round_at_one_spacing_to_slab_at_two() -> None:
    spacing = 2.0
    assert peak_to_mean(spacing, spacing, True) == pytest.approx(PEAK_TO_MEAN_ROUND)
    assert peak_to_mean(2.0 * spacing, spacing, True) == pytest.approx(PEAK_TO_MEAN_SLAB)
    assert peak_to_mean(1.5 * spacing, spacing, True) == pytest.approx(1.75)
    # and holds the slab value however wide the plume gets
    assert peak_to_mean(10.0 * spacing, spacing, True) == pytest.approx(PEAK_TO_MEAN_SLAB)


def test_an_unmerged_plume_is_round_however_close_the_neighbours() -> None:
    assert peak_to_mean(3.0, 1.0, False) == pytest.approx(PEAK_TO_MEAN_ROUND)


def test_a_single_port_never_blends() -> None:
    """No spacing, no neighbour, no confinement -- `limspc_shallow` holds 2.0 at 5.1 m wide."""
    assert peak_to_mean(5.139, 0.0, True) == pytest.approx(PEAK_TO_MEAN_ROUND)


def test_the_ratio_exceeds_two_when_an_oblique_diffuser_merges_early() -> None:
    """Nominal spacing in the law, effective spacing in the flag: the exe argues with itself.

    Not a bug we introduced and not one we can fix without departing from `CL-Dil`; the test is
    here so the behaviour cannot change unnoticed.
    """
    assert peak_to_mean(0.6015, 1.0, True) == pytest.approx(2.1993, abs=5e-4)


def test_the_exact_integral_reproduces_both_anchors_from_geometry_alone() -> None:
    """`exact_peak_to_mean` is derived, not fitted: it hits 2.0 and 1.5 with nothing tuned."""
    assert exact_peak_to_mean(1.0, 1.0) == pytest.approx(PEAK_TO_MEAN_ROUND)
    # u = s/b -> 0 is the slab limit; 1e4 spacings wide is close enough to see it.
    assert exact_peak_to_mean(1e4, 1.0) == pytest.approx(PEAK_TO_MEAN_SLAB, abs=1e-3)
    assert exact_peak_to_mean(0.5, 1.0) == PEAK_TO_MEAN_ROUND, "clear plumes are round"


def test_the_exe_s_linear_blend_is_a_shortcut_and_the_gap_is_bounded() -> None:
    """Pinning the disagreement, because a figure may draw either and must say which."""
    diameters = np.linspace(1.0, 4.0, 601)
    linear = peak_to_mean(diameters, 1.0, True)
    truth = np.array([exact_peak_to_mean(float(d), 1.0) for d in diameters])
    difference = linear - truth
    assert difference.max() == pytest.approx(0.028, abs=2e-3), "blend runs high near d = 1.3 L"
    assert difference.min() == pytest.approx(-0.131, abs=2e-3), "and low at the slab corner"
    assert abs(difference[0]) < 1e-12, "they agree exactly at first contact"


def test_the_exact_integral_is_monotone_between_its_two_limits() -> None:
    values = [exact_peak_to_mean(d, 1.0) for d in np.linspace(1.0, 20.0, 400)]
    assert all(later <= earlier + 1e-12 for earlier, later in itertools.pairwise(values))
    assert PEAK_TO_MEAN_SLAB <= min(values) and max(values) <= PEAK_TO_MEAN_ROUND


# ------------------------------------------------------------------ the ZFE floor


def test_the_centreline_is_floored_at_one_through_the_zone_of_flow_establishment() -> None:
    """The exe prints a flat 1.000 until the flux average passes the peak-to-mean."""
    dilution = np.array([1.0, 1.5, 2.0, 4.0, 100.0])
    assert centreline_dilution(dilution, PEAK_TO_MEAN_ROUND).tolist() == [1.0, 1.0, 1.0, 2.0, 50.0]


def test_a_merged_centreline_is_less_dilute_than_a_round_one() -> None:
    """Confinement flattens the profile, so the centreline moves *up* towards the mean."""
    round_ = centreline_dilution(100.0, PEAK_TO_MEAN_ROUND)
    slab = centreline_dilution(100.0, PEAK_TO_MEAN_SLAB)
    assert float(round_) == pytest.approx(50.0)
    assert float(slab) == pytest.approx(66.667, abs=1e-3)


# ------------------------------------------------------------------ against the whole archive


def _measured(path):  # type: ignore[no-untyped-def]
    """Every printed `(diameter, spacing, ports, merged, ratio)` a trace offers.

    ⚠️⚠️ **Non-default similarity profiles are skipped, and until 2026-08-25 nobody knew there
    were any.** Every claim in this module -- the exact 2.0 unmerged, the 1.5 merged slab, the
    onset ramp -- describes the *parabolic* profile, and case48 showed that is one setting of
    three: the same geometry gives a peak-to-mean of 2.00000, 3.88997 or 3.66998 depending on the
    exe's similarity-profile selector. Graduating those traces broke four tests here for the right
    reason. Skipping at this one chokepoint keeps every claim falsifiable on the traces it is
    actually about; `validation.NON_DEFAULT_PROFILE_TRACES` names them and ledger row 278 measures
    what they say instead.
    """
    if path.name in NON_DEFAULT_PROFILE_TRACES:
        return None
    dat = read_dat(path)
    frame = dat.nearfield
    if "CL-Dil" not in frame.columns or "Diffuser" not in dat.echoed_tables:
        return None
    diffuser = dat.echoed_tables["Diffuser"].iloc[0]
    # In metres whatever unit the echo flags (case55's 2 ft echoes as `2.0 (ft)`).
    spacing = float(dat.echoed_port_spacing or 0.0)
    ports = int(float(diffuser["Ports"]))
    merged_at = next(
        (e.next_step for e in dat.events if "merg" in e.text.lower() and e.next_step is not None),
        None,
    )
    # The profile law describes a plume still **in the water column**. Once the top breaks the
    # free surface the printed diameter no longer describes a submerged element, and neither the
    # exe nor this port has a free-surface treatment. case31's `surface_off` deliberately runs on
    # for 297 such steps, and every one of its misses lands there -- which is what broke the
    # "misses are a prefix" reading until this cut was added.
    left_water = next(
        (
            e.next_step
            for e in dat.events
            if e.next_step is not None
            and ("surface" in e.text.lower() or "bottom" in e.text.lower())
        ),
        None,
    )
    rows = []
    for step, row in frame.iterrows():
        centreline, mean = float(row["CL-Dil"]), float(row["Dilutn"])
        # Rows still in the ZFE are pinned at 1.000 and say nothing about the profile.
        if not math.isfinite(centreline) or centreline <= 1.0 or not math.isfinite(mean):
            continue
        if left_water is not None and int(step) >= left_water:
            break
        rows.append(
            {
                "step": int(step),
                "diameter": float(row["P-dia"]),
                "spacing": spacing if ports > 1 else 0.0,
                "merged": merged_at is not None and int(step) >= merged_at and ports > 1,
                "ratio": mean / centreline,
                "tolerance": printed_tolerance(mean, centreline, spacing if ports > 1 else 0.0),
            }
        )
    merged_rows = [row for row in rows if row["merged"]]
    for row in rows:
        # The banner's own row still prints the unmerged ratio -- see the test below.
        row["banner"] = bool(merged_rows) and row is merged_rows[0]
        # ⚠️ And whether that row **is** the banner's row, which is not the same thing. case34's
        # two overlapping-port geometries fire at step 2, before the plume has left the ZFE, so
        # their first *measured* merged row is far past the banner and already on the merged law.
        # A rule about what the banner row prints has nothing to say about them.
        row["on_banner_step"] = merged_at is not None and row["step"] == merged_at
    return rows


def _residuals(rows):  # type: ignore[no-untyped-def]
    """`(row, law - measured)` for each row, with the law evaluated on the printed diameter."""
    return [
        (row, float(peak_to_mean(row["diameter"], row["spacing"], row["merged"])) - row["ratio"])
        for row in rows
    ]


@pytest.mark.golden
@pytest.mark.parametrize("path", ALL_DAT_PATHS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_unmerged_row_in_the_archive_is_exactly_round(path) -> None:  # type: ignore[no-untyped-def]
    rows = _measured(path)
    if rows is None:
        pytest.skip("no centreline column in this trace")
    clear = [row for row in rows if not row["merged"]]
    if not clear:
        pytest.skip("every row of this trace is merged")
    over = [row for row in clear if abs(row["ratio"] - PEAK_TO_MEAN_ROUND) > row["tolerance"]]
    assert not over, f"{len(over)} of {len(clear)} rows miss 2.0 by more than printing can hide"


@pytest.mark.slow
@pytest.mark.golden
def test_the_blend_reproduces_the_merged_archive_and_only_the_onset_ramp_escapes() -> None:
    """8 126 merged rows across the archive; 7 522 land on the law to printed precision.

    The 96 that do not are the ramp from 2.0000 at the merge banner up to the line, and they are
    confined to `d < L` -- the region where the law reads above 2.0 because the flag fired on the
    effective spacing. Both counts are pinned: a change in either means the law or the merge
    trigger moved.

    ⭐ The law was derived on 944 rows from eight runs. case24's DO traces then **nearly doubled**
    the merged archive without moving it: 876 further rows, 21 further ramp misses, and every one of
    those a prefix starting at exactly 2.0000. Fresh data that was not available when the law was
    fitted is the strongest kind of confirmation available here.

    ⭐ case34's six-run spacing sweep then more than doubled it again -- 3638 rows across a 4x
    range in spacing and a 3x range in port diameter, still 96 ramp misses and nothing else.

    ⭐⭐ **And case40 takes it to `d/L` 4.27 without moving it, case41 to 15.1**: 1 414 further
    rows between them, only 10 further ramp misses, every one still a prefix at 2.0000. That
    matters more than the count, because those two cases are where the *entrainment* side of
    merging fails outright -- 15-29 % on dilution and a radius runaway reaching 11.9x (rows 157b,
    186). The centreline blend is unaffected, which localises that defect to the entrainment
    decrements and the merged radius rather than to the profile.

    ⭐⭐⭐ **And case45 takes it below `d/L` = 1, which is outside the domain it was fitted in.**
    2 906 further rows from case42-case45 brought the merged archive to **8 126**, and the misses
    rose from 139 to **604** -- almost all of them case45's, because those runs banner on the
    *limiting-spacing* rule at `d/L` 0.24-0.64 where ordinary merging is impossible, so their ramps
    are long. ⚠️ **Every one still sits on the climb**, the max `d/L` among misses is unchanged at
    **1.0120**, and the law's own prediction out there is right to a few hundredths -- 2.3446-2.3786
    against a printed 2.3519 on test91. That is a law holding at a third of the smallest `d/L` it
    was fitted on, and it falsified row 204's ceiling on the way (PLAN section 8d).

    ⚠️ **The count fell from 1820 to 1679 earlier on 2026-08-19, and that was a narrowing rather
    than a loss.**
    `_measured` now stops where the plume leaves the water column, which drops 158 rows from six
    older traces that ran a little past a surface or bottom hit. Those rows were passing, but the
    law was never justified there and their agreement was luck rather than evidence: case31 is the
    first trace to run **298** steps past a surface hit, and it misses on 89 of them. Keeping the
    boundary makes the claim narrower and true instead of wider and lucky.
    """
    rows = [row for path in ALL_DAT_PATHS for row in (_measured(path) or []) if row["merged"]]
    # 8126 -> 8177 on 2026-08-25: case46 graduated three case13-geometry traces, which merge.
    # The law itself held on every new row -- what grew is the evidence, not the verdict.
    # 8177 -> 8183 on 2026-08-26: the 2026-08-24 prj-pair traces joined case46 (interval 5, three
    # merged rows each before the surface, every one on the line). case49's two are non-default
    # profiles and are skipped by `_measured`.
    # 8183 -> 8207 on 2026-09-01: case51's flag-decode traces (six on the merging upstream-example
    # geometry, interval 5, four merged rows each before the surface). The law held on every one.
    # 8207 -> 8347 on 2026-09-02: case54's subcritical_sinks_legacy.dat adds 140 merged rows. ⚠️ It
    # is byte-identical to case34's L2.0_d0.50.dat (the determinism repeat, ledger 285 / 191c), so
    # the archive genuinely carries the same merged trace twice and these are those rows again.
    # 8347 -> 8356 on 2026-09-09: case55's two site arms (interval 5, the 2 ft site spacing) add
    # 7 + 2 merged rows before their ends.
    assert len(rows) == 8356, "the merged archive changed size"

    residuals = _residuals(rows)
    fits = [(row, error) for row, error in residuals if abs(error) <= row["tolerance"]]
    misses = [(row, error) for row, error in residuals if abs(error) > row["tolerance"]]

    # 7522/604 -> 7567/610 on 2026-08-25 with case46's three graduated traces. The 45 new
    # fits and 6 new misses all obey the claims below unchanged -- the misses still sit on
    # the onset climb and still land at d/L <= 1.012, so this is more evidence, not weaker.
    # +6 on 2026-08-26, the case46 prj-pair rows; +24 on 2026-09-01, case51's flag-decode rows.
    # Misses unchanged both times: every new row is a fit.
    # 7597/610 -> 7736/611 on 2026-09-02, case54's subcritical_sinks_legacy.dat -- 140 merged
    # rows. ⚠️ It is byte-identical to case34's L2.0_d0.50.dat (the determinism repeat, ledger
    # 285 / 191c), so these are the *same* rows counted again and conform identically: 139 fits
    # and the one onset-ramp miss that trace already carried.
    # 7736 -> 7744 on 2026-09-09: case55's two site arms -- the acute arm's seven merged rows all
    # on the line (its interval-5 banner row included, d/L already 1.04 there), and the chronic
    # arm's second row. The 2 ft spacing reads from the echo in metres (`echoed_port_spacing`).
    assert len(fits) == 7744
    # 611 -> 612 on 2026-09-09: case55's chronic banner row (the onset ramp, one row).
    assert len(misses) == 612

    # Every miss is the onset transient rather than a competing law, and the claim is that each
    # one sits **on the climb** -- at or above the round 2.0 the previous row was already at, and
    # at or below the law it is climbing toward.
    #
    # ⚠️ This used to assert `ratio == approx(2.0, abs=0.18)`, which held only while every ramp
    # was short. case41's test68 breaks that and is right to: its flag is the *limiting-spacing*
    # rule firing at d/L 0.41 (row 261), so its law starts at 2.295 and the climb reaches 2.269
    # before landing. Bounding the climb by the law is the claim; a window around 2.0 was a
    # coincidence of the runs available when it was written.
    for row, _ in misses:
        law = peak_to_mean(row["diameter"], row["spacing"], True)
        assert PEAK_TO_MEAN_ROUND - 0.18 <= row["ratio"] <= max(law, PEAK_TO_MEAN_ROUND) + 1e-3, row
    # 1.0125 rather than the 1.011 that held before case40, and the basis is the crossing's
    # granularity rather than slack in the claim: the bound is "the misses sit at first contact",
    # and where exactly a crossing lands between two printed rows is set by the output interval.
    # case40's test58 has the archive's tightest spacing (0.25 m) so its banner row sits furthest
    # past d = L, at 1.0120. The claim is unchanged; the widest sample of it is not.
    assert max(row["diameter"] / row["spacing"] for row, _ in misses) <= 1.0125
    # 0.4 rather than 0.3 since case45, and for the same reason 0.3 replaced 0.2 at case41:
    # the bound is "how far a ramp has to climb", and that is set by how high the law reads at the
    # banner. A *limiting-spacing* banner (row 261) can fire at any d/L, so the lower the d/L the
    # higher the law and the longer the climb. case45's test91 banners at d/L 0.24 -- the archive's
    # lowest -- where the law reads 2.379, so its ramp climbs 0.379 from the round 2.0. That is the
    # arithmetic, not slack: the bound is `max(law) - 2.0` over the archive, and it will move again
    # the first time a run banners lower still.
    assert max(abs(error) for _, error in misses) < 0.4

    # Past first contact, and past the banner row itself, the law is exact with no exceptions.
    past_contact = [
        (row, error)
        for row, error in residuals
        if row["diameter"] / row["spacing"] > 1.0 and not row["banner"]
    ]
    assert len(past_contact) > 3000
    assert all(abs(error) <= row["tolerance"] for row, error in past_contact)


@pytest.mark.slow
@pytest.mark.golden
def test_the_banner_row_still_prints_the_unmerged_ratio() -> None:
    """The row carrying `merging happened` is itself still round: the profile changes after it.

    Every trace that prints every step shows exactly 2.0000 on that row -- including test32,
    where the law is already *below* 2.0 (1.9970) because its diffuser is square to the flow, so
    this is not the ramp seen from the other side. It is the merge taking effect one step late.
    """
    checked = 0
    for path in ALL_DAT_PATHS:
        rows = [row for row in (_measured(path) or []) if row["merged"]]
        if len(rows) < 2 or rows[1]["step"] - rows[0]["step"] != 1:
            continue  # printed every 5th step: the banner row is already several steps in
        if not rows[0]["on_banner_step"]:
            continue  # merged before leaving the ZFE, so no unmerged row precedes the measured set
        checked += 1
        assert rows[0]["ratio"] == pytest.approx(PEAK_TO_MEAN_ROUND, abs=5e-4), path.name
    # 47 -> 50 on 2026-08-25 with case46's three graduated traces, all of which conform.
    # 50 -> 51 on 2026-09-02: case54's subcritical_sinks_legacy.dat, an interval-1 trace whose
    # banner row is measured -- byte-identical to case34's L2.0_d0.50.dat, so it prints the same
    # round 2.0000 on that row (the merge fires on the crossing with zero lag, ledger 285).
    assert checked == 51, "the interval-1 traces whose banner row is itself measured"


@pytest.mark.slow
@pytest.mark.golden
def test_the_ramp_is_a_prefix_that_climbs_to_meet_the_law() -> None:
    """The misses form a contiguous run from the banner, rising until they join the line.

    This is what identifies them as a transient rather than a different law: once a trace joins
    the line it never leaves it again, and while it is climbing it only ever climbs.
    """
    ramped = 0
    for path in ALL_DAT_PATHS:
        rows = [row for row in (_measured(path) or []) if row["merged"]]
        ramp = [(row, error) for row, error in _residuals(rows) if abs(error) > row["tolerance"]]
        if not ramp:
            continue
        ramped += 1
        # Contiguous, and anchored at the merge banner -- never a recurrence later on.
        assert [row["step"] for row, _ in ramp] == [row["step"] for row in rows[: len(ramp)]], (
            f"{path.name}: the misses are not a prefix"
        )
        assert all(row["ratio"] >= PEAK_TO_MEAN_ROUND - 5e-4 for row, _ in ramp), path.name
        ratios = [row["ratio"] for row, _ in ramp]
        assert ratios == sorted(ratios), f"{path.name}: the ramp is not monotone"
        # It is only ever long when the law reads high at the banner, i.e. `d < L` there.
        if len(ramp) > 1:
            assert ramp[0][1] > 0.0 and ramp[0][0]["diameter"] < ramp[0][0]["spacing"], path.name
    # 49 -> 52 on 2026-08-25 with case46's three graduated traces, all of which ramp.
    # 52 -> 53 on 2026-09-02: case54's subcritical_sinks_legacy.dat ramps by its one onset row --
    # the byte-identical repeat of case34's L2.0_d0.50.dat (ledger 285), so it ramps identically.
    # 53 -> 54 on 2026-09-09: case55's chronic arm ramps by its banner row alone (printed 2.0000
    # where the law reads 1.998 at d/L 1.004); its acute arm has no ramp at all, the banner row
    # already on the line.
    assert ramped == 54, "every merged multiport trace ramps, most by only a row or two"
