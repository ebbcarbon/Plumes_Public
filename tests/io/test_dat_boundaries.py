"""Boundary termination and the terminating-row rule.

case10 closed the last reachable coverage gap (a bottom hit) and case11 corrected
case09's diagnosis of the single-port failure. Both also pinned down two rules that
earlier cases had only half-shown, so those are asserted here across every trace.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from plumes2.io.dat import read_dat
from tests.conftest import ALL_DAT_PATHS, REFERENCE_CASES

CASE06 = REFERENCE_CASES / "case06_arag_s36" / "test5_TxtOutputs.dat"
CASE09_A = REFERENCE_CASES / "case09_single_port" / "test9_TxtOutputs.dat"
CASE09_B = REFERENCE_CASES / "case09_single_port" / "test10_TxtOutputs.dat"
CASE10 = REFERENCE_CASES / "case10_bottom_hit" / "test11_TxtOutputs.dat"
CASE11 = REFERENCE_CASES / "case11_single_port_slow" / "test12_TxtOutputs.dat"

PORT_AREA = math.pi * (0.0127 / 2) ** 2


class TestBottomHit:
    def test_new_banner_and_termination(self) -> None:
        """Ledger row 76: the only trace with a bottom hit."""
        dat = read_dat(CASE10)
        assert dat.event_steps() == {
            "Local maximum rise or fall": [220],
            "merging happened": [310],
            "Plume hits the bottom": [345],
        }
        assert dat.final_step == 345

    def test_criterion_is_lower_edge_reaching_the_seabed(self) -> None:
        """depth + radius >= bottom, where bottom = port depth + port elevation."""
        nearfield = read_dat(CASE10).nearfield
        bottom = 2.0 + 1.0
        lower_edge = -nearfield["Depth"] + nearfield["P-dia"] / 2
        assert lower_edge.loc[340] < bottom
        assert lower_edge.loc[345] > bottom
        # And it is genuinely tight: within half a step of the boundary.
        assert lower_edge.loc[340] == pytest.approx(2.984, abs=1e-3)
        assert lower_edge.loc[345] == pytest.approx(3.189, abs=1e-3)

    def test_surface_criterion_is_the_mirror_image(self) -> None:
        """case06 brackets depth - radius = 0, the same rule at the other boundary."""
        nearfield = read_dat(CASE06).nearfield
        upper_edge = -nearfield["Depth"] - nearfield["P-dia"] / 2
        assert upper_edge.loc[255] > 0
        assert upper_edge.loc[260] < 0

    def test_no_nan_and_omega_stays_supersaturated(self) -> None:
        nearfield = read_dat(CASE10).nearfield
        assert nearfield["R_cal"].notna().all()
        assert nearfield["OmegaC"].min() > 1.0


class TestSinglePortCorrection:
    def test_a_single_port_can_run_cleanly(self) -> None:
        """Ledger row 78: case09's 'single ports are unvalidatable' was wrong."""
        dat = read_dat(CASE11)
        assert len(dat.nearfield) == 100
        assert dat.final_step == 500
        assert dat.nearfield.notna().all().all()
        assert dat.has_farfield
        assert dat.farfield is not None
        assert not dat.farfield.isna().any().any()

    def test_the_failure_correlates_with_exit_velocity_not_port_count(self) -> None:
        fast = 0.005 / PORT_AREA
        slow = 5e-5 / PORT_AREA
        assert fast == pytest.approx(39.5, abs=0.5)
        assert slow == pytest.approx(0.39, abs=0.01)
        # The fast pair overshoot the surface; the slow one never does.
        for path in (CASE09_A, CASE09_B):
            depth = -read_dat(path).nearfield["Depth"]
            assert depth.min() < 0, f"{path.name} should breach the surface"
        assert (-read_dat(CASE11).nearfield["Depth"]).min() > 0

    def test_both_fast_single_port_runs_fail_identically(self) -> None:
        for path in (CASE09_A, CASE09_B):
            dat = read_dat(path)
            nan_steps = dat.nearfield.index[dat.nearfield["Dilutn"].isna()]
            assert nan_steps[0] == 235
            assert len(nan_steps) == 955
            assert dat.final_step == 5001

    def test_width_formula_degenerates_for_one_port(self) -> None:
        """(n-1)*spacing vanishes, leaving just the diameter."""
        dat = read_dat(CASE11)
        final_diameter = dat.nearfield.loc[dat.final_step, "P-dia"]
        assert final_diameter == pytest.approx(1.451)
        assert dat.wastefield_width == pytest.approx(1.45, abs=0.005)


#: (trace, output interval). The interval is a project setting, absent from the .dat.
_INTERVAL_CASES = [
    (REFERENCE_CASES / "case05_merging" / "test4_TxtOutputs.dat", 5),
    (CASE06, 5),
    (REFERENCE_CASES / "case07_s45_dense" / "test6_TxtOutputs.dat", 5),
    (CASE10, 5),
    (CASE11, 5),
]

#: The complete set of event banners across all eleven traces.
KNOWN_BANNERS = frozenset(
    {
        "Plume traps",
        "merging happened",
        "Plume surfaces",
        "Local maximum rise or fall",
        "Plume hits the bottom",
        "Starting Farfield Calculations",
        "Reached Chronic Mixing Zone",
    }
)


class TestTerminatingRowRule:
    @pytest.mark.parametrize(
        ("path", "interval"), _INTERVAL_CASES, ids=lambda v: getattr(v, "parent", v)
    )
    def test_truncated_only_when_off_interval(self, path: object, interval: int) -> None:
        """Amends ledger row 54: truncation is conditional on interval alignment."""
        dat = read_dat(path)  # type: ignore[arg-type]
        final_row = dat.nearfield.loc[dat.final_step]
        on_interval = dat.final_step % interval == 0
        complete = bool(final_row.notna().all())
        assert complete == on_interval, (
            f"step {dat.final_step}: on_interval={on_interval} but complete={complete}"
        )


class TestAragoniteCutoffAcrossEveryChemistryTrace:
    @pytest.mark.parametrize(
        ("path", "effluent_salinity"),
        [
            (REFERENCE_CASES / "case07_s45_dense" / "test6_TxtOutputs.dat", 45.0),
            (CASE10, 45.0),
            (CASE11, 45.0),
        ],
        ids=["case07", "case10", "case11"],
    )
    def test_r_arg_is_nonzero_exactly_above_salinity_35(
        self, path: object, effluent_salinity: float
    ) -> None:
        """Ledger row 60, now on three independent traces that cross the threshold."""
        nearfield = read_dat(path).nearfield  # type: ignore[arg-type]
        ambient = np.interp(
            -nearfield["Depth"],
            [0, 3, 6, 9, 12, 15],
            [30.9, 31.2, 31.2, 31.7, 31.8, 31.9],
        )
        dilution = nearfield["Dilutn"]
        plume_salinity = (effluent_salinity + (dilution - 1) * ambient) / dilution
        assert ((plume_salinity > 35.0) == (nearfield["R_arg"] > 0)).all()


class TestNoNewBannersAreUnaccountedFor:
    def test_every_banner_is_one_we_know(self) -> None:
        """A guard: a new exe behaviour should fail loudly rather than pass unnoticed."""
        seen: set[str] = set()
        for path in ALL_DAT_PATHS:
            if path.name == "ModelResults_legacy1.dat":
                continue  # header-only legacy artifact
            for event in read_dat(path).events:
                if not event.is_note:
                    seen.add(event.text)
        assert seen <= KNOWN_BANNERS, f"unrecognised banner(s): {seen - KNOWN_BANNERS}"
        # Everything we claim to know is actually exercised somewhere.
        assert seen == KNOWN_BANNERS
