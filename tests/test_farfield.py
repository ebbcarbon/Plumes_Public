"""Brooks far-field, against the manual's equations and against eight exe traces.

Two findings are pinned here, one good and one open.

**The width law is exact.** With `beta = 12 alpha w0**(1/3) / u`, `w0` taken as the
far-field *starting* width and `x` measured from the far-field origin, the 4/3-power width
reproduces every current-build trace to ~1e-5 relative -- exact to the three decimals the exe
prints. Inverting the law gives a slope of exactly 1.0000 against the printed distance
column, which is what establishes the convention.

**The dilution is not.** The same parameters give dilutions systematically *low* by up
to **11.2 %** (case06), and the shortfall tracks the near-field-to-far-field width
adjustment. Recorded with a measured bound rather than fitted away; the bound now lives in
the validation registry as row 116, so the report and the suite share one number.
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import pytest
from scipy.special import erf

from plumes2.config import EddyDiffusivityLaw
from plumes2.farfield.brooks import (
    BrooksParameters,
    beta,
    dilution_factor,
    initial_eddy_diffusivity,
    width,
)
from plumes2.farfield.standalone import (
    STEPS_BEYOND_MIXING_ZONE,
    STEPS_TO_MIXING_ZONE,
    StandaloneRequest,
    independent_farfield,
    output_distances,
)
from plumes2.io.dat import read_dat
from tests.conftest import REFERENCE_CASES

#: (label, trace, far-field current speed). Every current-build trace with a far field.
FARFIELD_TRACES = [
    ("case02", REFERENCE_CASES / "case02_mgd/test1.dat", 0.02),
    ("case05", REFERENCE_CASES / "case05_merging/test4_TxtOutputs.dat", 0.02),
    ("case06", REFERENCE_CASES / "case06_arag_s36/test5_TxtOutputs.dat", 0.02),
    ("case07", REFERENCE_CASES / "case07_s45_dense/test6_TxtOutputs.dat", 0.02),
    ("case10", REFERENCE_CASES / "case10_bottom_hit/test11_TxtOutputs.dat", 0.02),
    ("case12", REFERENCE_CASES / "case12_shoreline_enabled/test13_TxtOutputs.dat", 0.02),
    ("case13", REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat", 0.05),
    ("case14", REFERENCE_CASES / "case14_generated_nochem/PythonGenerated3.dat", 0.05),
]
IDS = [trace[0] for trace in FARFIELD_TRACES]


_Columns = tuple[BrooksParameters, np.ndarray, np.ndarray, np.ndarray]


def _trace(path: object, current: float) -> _Columns:
    """Set a run up the way the exe evidently does, and return the printed columns."""
    dat = read_dat(path)  # type: ignore[arg-type]
    farfield = dat.farfield
    assert farfield is not None
    distance = farfield["Distance"].to_numpy(float)
    reported_width = farfield["Width"].to_numpy(float)
    reported_dilution = farfield["Dilution"].to_numpy(float)
    parameters = BrooksParameters(
        initial_width=reported_width[0],
        initial_dilution=reported_dilution[0],
        current_speed=current,
        law=EddyDiffusivityLaw.FOUR_THIRDS,
    )
    return parameters, distance - distance[0], reported_width, reported_dilution


class TestEquations:
    """Against the manual's own algebra (§2.3.2, eqs 10-16)."""

    def test_eddy_diffusivity(self) -> None:
        """eps_0 = alpha w0**(4/3), with alpha defaulting to 3e-4."""
        assert float(initial_eddy_diffusivity(50.0)) == pytest.approx(3e-4 * 50.0 ** (4 / 3))
        assert float(initial_eddy_diffusivity(50.0, 1e-4)) == pytest.approx(1e-4 * 50.0 ** (4 / 3))

    def test_beta_is_dimensionless_group_13(self) -> None:
        w0, u, alpha = 50.0, 0.05, 3e-4
        expected = 12.0 * alpha * w0 ** (4 / 3) / (u * w0)
        assert float(beta(w0, u, alpha)) == pytest.approx(expected)
        # Equivalently 12 alpha w0**(1/3) / u.
        assert float(beta(w0, u, alpha)) == pytest.approx(12 * alpha * w0 ** (1 / 3) / u)

    @pytest.mark.parametrize(
        ("law", "growth"),
        [
            (EddyDiffusivityLaw.CONSTANT, lambda bx: math.sqrt(1 + 2 * bx)),
            # Not the manual's `1 + 2 bx`: the exe prints `1 + bx` (case50, row 280b).
            (EddyDiffusivityLaw.LINEAR, lambda bx: 1 + bx),
            (EddyDiffusivityLaw.FOUR_THIRDS, lambda bx: (1 + (2 / 3) * bx) ** 1.5),
        ],
    )
    def test_width_laws(self, law: EddyDiffusivityLaw, growth: object) -> None:
        w0, beta_value, x = 50.0, 0.4, 120.0
        bx = beta_value * x / w0
        assert float(width(x, w0, beta_value, law)) == pytest.approx(w0 * growth(bx))  # type: ignore[operator]

    @pytest.mark.parametrize("law", list(EddyDiffusivityLaw))
    def test_width_starts_at_w0_and_grows(self, law: EddyDiffusivityLaw) -> None:
        assert float(width(0.0, 40.0, 0.5, law)) == pytest.approx(40.0)
        assert np.all(np.diff(width(np.linspace(0, 500, 50), 40.0, 0.5, law)) > 0)

    def test_dilution_factor_matches_the_erf_forms(self) -> None:
        w0, beta_value, x = 50.0, 0.4, 120.0
        bx = beta_value * x / w0
        expected = {
            EddyDiffusivityLaw.CONSTANT: 1 / erf(math.sqrt(3 / (4 * bx))),
            EddyDiffusivityLaw.LINEAR: 1 / erf(math.sqrt(1.5 / ((1 + bx) ** 2 - 1))),
            EddyDiffusivityLaw.FOUR_THIRDS: 1 / erf(math.sqrt(1.5 / ((1 + (2 / 3) * bx) ** 3 - 1))),
        }
        for law, value in expected.items():
            assert float(dilution_factor(x, w0, beta_value, law)) == pytest.approx(value)

    @pytest.mark.parametrize("law", list(EddyDiffusivityLaw))
    def test_no_dilution_at_zero_distance(self, law: EddyDiffusivityLaw) -> None:
        """erf(inf) = 1, so FF = 1: the far field has not diluted anything yet."""
        assert float(dilution_factor(0.0, 50.0, 0.4, law)) == pytest.approx(1.0)

    @pytest.mark.parametrize("law", list(EddyDiffusivityLaw))
    def test_dilution_factor_increases(self, law: EddyDiffusivityLaw) -> None:
        factors = dilution_factor(np.linspace(0, 500, 50), 50.0, 0.4, law)
        assert np.all(np.diff(factors) >= 0)

    def test_decay_increases_apparent_dilution(self) -> None:
        without = float(dilution_factor(200.0, 50.0, 0.4))
        with_decay = float(dilution_factor(200.0, 50.0, 0.4, decay_per_day=1.0, current_speed=0.05))
        assert with_decay > without

    def test_decay_needs_a_current(self) -> None:
        with pytest.raises(ValueError, match="current_speed is required"):
            dilution_factor(200.0, 50.0, 0.4, decay_per_day=1.0)

    def test_rejects_bad_inputs(self) -> None:
        with pytest.raises(ValueError, match="width must be positive"):
            beta(0.0, 0.05)
        with pytest.raises(ValueError, match="current speed must be positive"):
            beta(50.0, 0.0)
        with pytest.raises(ValueError, match="must be non-negative"):
            width(-1.0, 50.0, 0.4)


class TestWidthAgainstTheExe:
    @pytest.mark.parametrize(("label", "path", "current"), FARFIELD_TRACES, ids=IDS)
    def test_reproduces_the_width_column(self, label: str, path: object, current: float) -> None:
        """Exact to the printed precision on six of eight; 8e-4 on the two example runs."""
        parameters, x, reported, _dilution = _trace(path, current)
        predicted = parameters.width(x)
        relative = np.abs(predicted - reported) / reported
        assert relative.max() < 1e-3, f"{label}: max relative error {relative.max():.2e}"

    @pytest.mark.parametrize(
        ("label", "path", "current"),
        [t for t in FARFIELD_TRACES if t[0] not in ("case13", "case14")],
        ids=[t[0] for t in FARFIELD_TRACES if t[0] not in ("case13", "case14")],
    )
    def test_archive_traces_are_exact_to_printed_precision(
        self, label: str, path: object, current: float
    ) -> None:
        parameters, x, reported, _dilution = _trace(path, current)
        assert np.abs(parameters.width(x) - reported).max() < 0.005

    @pytest.mark.parametrize(("label", "path", "current"), FARFIELD_TRACES, ids=IDS)
    def test_inverting_the_law_recovers_the_distance_axis(
        self, label: str, path: object, current: float
    ) -> None:
        """The evidence for the convention: slope exactly 1 against the printed column."""
        parameters, x, reported, _dilution = _trace(path, current)
        w0, b = parameters.initial_width, parameters.beta
        implied = (w0 / ((2 / 3) * b)) * ((reported / w0) ** (2 / 3) - 1.0)
        slope, _intercept = np.polyfit(x, implied, 1)
        assert slope == pytest.approx(1.0, abs=1e-3)


class TestTheOtherTwoLawsAgainstTheExe:
    """case50: the same project run under `Constant` and `Linearly varying` (ledger rows 280, 280b).

    Set up as every far-field comparison is (row 115): `w0` and `D0` are the far field's own first
    row and `x` runs from it. The near field is bit-identical to case03's, so the far field is the
    only thing the law selector moves -- and the exe's `Dilution` follows the port's Brooks under
    each law to 2e-4, its `Width` to 1.7e-4. ⚠️ The linear width did **not** match until the
    manual's stray factor of two in eq 11 was removed (row 280b); this is the test that would have
    caught it, had a linear-law trace existed before 2026-08-26.
    """

    CASE = "reference_cases/case50_eddy_law_selector"
    #: Exe rows at 100 / 200 / 500 m: (Distance, Dilution, Width), read off the traces.
    EXE: ClassVar[dict[EddyDiffusivityLaw, list[tuple[float, float, float]]]] = {
        EddyDiffusivityLaw.CONSTANT: [
            (100.000, 787.151, 92.477),
            (200.000, 1028.928, 122.187),
            (500.000, 1548.571, 184.560),
        ],
        EddyDiffusivityLaw.LINEAR: [
            (100.000, 947.831, 112.339),
            (200.000, 1493.781, 178.008),
            (500.000, 3144.325, 375.015),
        ],
    }

    @pytest.mark.parametrize(
        ("law", "trace"),
        [
            (EddyDiffusivityLaw.CONSTANT, "eddy_law_constant.dat"),
            (EddyDiffusivityLaw.LINEAR, "eddy_law_linear.dat"),
        ],
    )
    def test_dilution_and_width_follow_the_selected_law(
        self, law: EddyDiffusivityLaw, trace: str
    ) -> None:
        from plumes2.io.dat import read_dat

        dat = read_dat(f"{self.CASE}/{trace}")
        far = dat.farfield
        assert far is not None, "the reader must parse a far field headed by this law"
        w0 = float(far["Width"].iloc[0])
        d0 = float(far["Dilution"].iloc[0])
        x0 = float(far["Distance"].iloc[0])
        assert d0 == pytest.approx(562.633)  # case03's near-field end, identical under every law
        parameters = BrooksParameters(
            initial_width=w0, initial_dilution=d0, current_speed=0.02, alpha=3e-4, law=law
        )
        for distance, dilution, printed_width in self.EXE[law]:
            row = far[far["Distance"] == distance].iloc[0]
            assert float(row["Dilution"]) == dilution and float(row["Width"]) == printed_width
            ours_d = float(parameters.total_dilution(distance - x0))
            ours_w = float(parameters.width(distance - x0))
            assert ours_d == pytest.approx(dilution, rel=3e-4)
            assert ours_w == pytest.approx(printed_width, rel=3e-4)

    def test_the_manual_form_of_the_linear_width_is_refuted(self) -> None:
        """`1 + 2 bx` is 57-87 % high against the printed column; `1 + bx` is 1.7e-4."""
        from plumes2.io.dat import read_dat

        far = read_dat(f"{self.CASE}/eddy_law_linear.dat").farfield
        assert far is not None
        w0 = float(far["Width"].iloc[0])
        x = far["Distance"].to_numpy(dtype=np.float64) - float(far["Distance"].iloc[0])
        printed = far["Width"].to_numpy(dtype=np.float64)
        bx = float(beta(w0, 0.02, 3e-4)) * x / w0
        manual = w0 * (1 + 2 * bx)
        exe_form = w0 * (1 + bx)
        assert np.max(np.abs(exe_form - printed) / printed) < 3e-4
        assert np.max((manual - printed) / printed) > 0.5

    def test_the_selector_is_one_hot_in_the_far_field_flags(self) -> None:
        """Positions 2, 3, 4 of the seven far-field flags: Constant / Linear / 4/3."""
        from plumes2.io.prj import read_prj

        constant = read_prj(f"{self.CASE}/asrun_eddy_law_constant.prj").farfield_flags
        linear = read_prj(f"{self.CASE}/asrun_eddy_law_linear.prj").farfield_flags
        assert constant == [1, 1, 0, 0, 1, 1, 0]
        assert linear == [1, 0, 1, 0, 1, 1, 0]


class TestDilutionDiscrepancy:
    """The dilution column is *not* reproduced. Bounded here so a fix is detectable."""

    def test_dilution_discrepancy_is_bounded(self) -> None:
        """The bound lives in the registry (row 116), so the report and the suite share one number.

        Kept as a whole-archive assertion rather than per-trace because the claim is about the
        worst case across every far field, which is what the ledger row states.
        """
        from plumes2.validation import TARGETS, measure

        target = next(t for t in TARGETS if t.row == "116")
        outcome = measure(target)
        assert outcome.passed, f"shortfall {outcome.ours:.4f} exceeds {target.tolerance}"
        # The half the registry cannot express: it is one-sided, and the worst case is real rather
        # than a rounding artefact, so a sudden *improvement* is as suspicious as a regression.
        assert outcome.ours > 0.05, f"shortfall {outcome.ours:.4f} -- has the handoff changed?"

    @pytest.mark.parametrize(("label", "path", "current"), FARFIELD_TRACES, ids=IDS)
    def test_the_first_row_is_the_handoff_dilution(
        self, label: str, path: object, current: float
    ) -> None:
        """Whatever the discrepancy is, it is zero at x = 0."""
        parameters, x, _width, reported = _trace(path, current)
        assert float(parameters.total_dilution(x[0])) == pytest.approx(reported[0])

    def test_the_shortfall_tracks_the_transition_width_adjustment(self) -> None:
        """The clue: the dilution shortfall correlates with w0_used / w0_echoed.

        The exe echoes a geometric wastefield width and then starts the far field from a
        slightly larger one -- the manual's "transition stage" where plume parameters are
        "revised/adjusted to match the wastefield dimensions". Cases whose two widths agree
        (case02, ratio 1.0002) show almost no dilution error; the largest ratio (case06,
        1.1255) shows the largest error.
        """
        ratios, shortfalls = [], []
        for _label, path, current in FARFIELD_TRACES:
            dat = read_dat(path)  # type: ignore[arg-type]
            parameters, x, reported_width, reported = _trace(path, current)
            assert dat.wastefield_width is not None
            ratios.append(reported_width[0] / dat.wastefield_width)
            shortfalls.append(
                float(np.abs(parameters.total_dilution(x) - reported).max() / reported.max())
            )
        correlation = np.corrcoef(ratios, shortfalls)[0, 1]
        assert correlation > 0.9, f"correlation {correlation:.3f}"


#: The manual's own worked example (§5.2.9), which the exe was run on for case17.
MANUAL_EXAMPLE = StandaloneRequest(
    initial_dilution=100.0,
    initial_width=50.0,
    mixing_zone_distance=200.0,
    current_speed=0.05,
    initial_location=0.001,
    alpha=3.0e-4,
    law=EddyDiffusivityLaw.FOUR_THIRDS,
)
CASE17 = REFERENCE_CASES / "case17_independent_farfield/IndpFarfieldCalc1.TXT"


def _read_standalone_output() -> np.ndarray:
    """Parse the independent calculator's five-column text output."""
    import re

    rows = []
    for line in CASE17.read_text(encoding="ascii").splitlines():
        tokens = line.split()
        if len(tokens) == 5 and re.fullmatch(r"\d+\.\d+", tokens[0]):
            rows.append([float(token) for token in tokens])
    return np.array(rows)


class TestAgainstTheIndependentCalculator:
    """The decisive Brooks test: w0 and D0 are user-supplied, so no handoff is involved.

    Everything agrees to the printed precision, which confirms the Brooks equations, beta,
    eps_0 = alpha w0**(4/3), the erf forms, D_total = D0 * FF, and the travel time. It
    therefore localises the integrated runs' dilution shortfall entirely to the near-field
    to far-field transition.
    """

    def test_grid_matches_exactly(self) -> None:
        reported = _read_standalone_output()
        assert len(reported) == 28
        assert output_distances(MANUAL_EXAMPLE) == pytest.approx(reported[:, 3], abs=0.001)

    def test_width_dilution_and_time_match_to_printed_precision(self) -> None:
        reported = _read_standalone_output()
        _conc, dilution, reported_width, _distance, hours = reported.T
        frame = independent_farfield(MANUAL_EXAMPLE)
        assert frame["width"].to_numpy() == pytest.approx(reported_width, abs=0.001)
        assert frame["dilution"].to_numpy() == pytest.approx(dilution, abs=0.001)
        assert frame["travel_time_hr"].to_numpy() == pytest.approx(hours, abs=0.001)

    def test_beta_for_the_manual_example(self) -> None:
        assert MANUAL_EXAMPLE_BETA == pytest.approx(0.265250, abs=1e-6)


MANUAL_EXAMPLE_BETA = float(beta(50.0, 0.05, 3.0e-4))


class TestStandaloneCalculator:
    """Manual §5.2.9. Fixed stepping, and no near-field transition to confound it."""

    def test_the_manual_example_grid(self) -> None:
        """200 m mixing zone -> 8 m steps, 28 rows from 8.001 to 224.000.

        The origin row is not printed: the exe starts at step 1.
        """
        distances = output_distances(MANUAL_EXAMPLE)
        assert len(distances) == STEPS_TO_MIXING_ZONE + STEPS_BEYOND_MIXING_ZONE
        assert distances[0] == pytest.approx(8.001, abs=0.001)
        assert distances[1] - distances[0] == pytest.approx(8.0, abs=0.001)
        assert distances[STEPS_TO_MIXING_ZONE - 1] == pytest.approx(200.0, abs=0.001)
        assert distances[-1] == pytest.approx(224.0, abs=0.001)

    def test_runs_and_dilution_grows_from_the_initial_value(self) -> None:
        request = StandaloneRequest(
            initial_dilution=100.0,
            initial_width=50.0,
            mixing_zone_distance=200.0,
            current_speed=0.05,
        )
        frame = independent_farfield(request)
        # The origin row is not printed, so the first row has already travelled one step:
        # dilution is a hair above the supplied 100 and the width above the supplied 50.
        assert frame["dilution"].iloc[0] == pytest.approx(100.0, abs=1e-3)
        assert frame["dilution"].iloc[0] >= 100.0
        assert frame["dilution"].is_monotonic_increasing
        assert frame["width"].iloc[0] > 50.0
        assert frame["width"].is_monotonic_increasing
        # Travel time is measured from the far-field origin, so the last row has
        # travelled 224 - 0.001 m rather than the full 224 m from the outfall.
        travelled = 224.0 - request.initial_location
        assert frame["travel_time_hr"].iloc[-1] == pytest.approx(travelled / 0.05 / 3600, rel=1e-6)

    def test_unknown_initial_dilution_gives_a_pure_factor(self) -> None:
        """The manual's conservative choice: enter 1."""
        frame = independent_farfield(
            StandaloneRequest(
                initial_dilution=1.0,
                initial_width=50.0,
                mixing_zone_distance=200.0,
                current_speed=0.05,
            )
        )
        assert frame["dilution"].to_numpy() == pytest.approx(frame["dilution_factor"].to_numpy())

    def test_concentration_is_optional(self) -> None:
        base = StandaloneRequest(
            initial_dilution=100.0,
            initial_width=50.0,
            mixing_zone_distance=200.0,
            current_speed=0.05,
        )
        assert "concentration" not in independent_farfield(base)
        with_conc = independent_farfield(
            StandaloneRequest(
                initial_dilution=100.0,
                initial_width=50.0,
                mixing_zone_distance=200.0,
                current_speed=0.05,
                initial_concentration=1000.0,
            )
        )
        assert with_conc["concentration"].iloc[0] == pytest.approx(10.0)

    def test_zero_initial_location_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="greater than zero"):
            StandaloneRequest(
                initial_dilution=100.0,
                initial_width=50.0,
                mixing_zone_distance=200.0,
                current_speed=0.05,
                initial_location=0.0,
            )

    def test_mixing_zone_must_be_beyond_the_start(self) -> None:
        with pytest.raises(ValueError, match="beyond the initial"):
            StandaloneRequest(
                initial_dilution=100.0,
                initial_width=50.0,
                mixing_zone_distance=0.0005,
                current_speed=0.05,
            )

    def test_dilution_below_one_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            StandaloneRequest(
                initial_dilution=0.5,
                initial_width=50.0,
                mixing_zone_distance=200.0,
                current_speed=0.05,
            )
