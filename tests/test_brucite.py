"""Brucite saturation -- the quantity the exe cannot report (PLAN.md section 8b).

Every test here is independent of the `Ksp*` value, which is deliberately not chosen yet:
they check the arithmetic, the scaling and the unit handling, all of which are settled, and
leave the constant to be supplied. See `saturation.omega_brucite`.
"""

from __future__ import annotations

import numpy as np
import pytest

from plumes2.chem.constants import (
    _GAS_CONSTANT,
    BRUCITE_DISSOLUTION_ENTHALPY,
    BRUCITE_LOG_KSP_25C,
    MAGNESIUM_AT_S35,
    davies_activity_coefficient,
    ionic_strength_from_salinity,
    magnesium_from_salinity,
    solubility_brucite,
)
from plumes2.chem.saturation import omega_brucite
from plumes2.chem.speciation import solve_from_alkalinity_dic

KSP = 5.6e-12  # placeholder only -- never assert on its absolute consequences


def test_magnesium_is_conservative_with_salinity() -> None:
    assert magnesium_from_salinity(35.0) == pytest.approx(MAGNESIUM_AT_S35)
    assert magnesium_from_salinity(17.5) == pytest.approx(MAGNESIUM_AT_S35 / 2)
    assert magnesium_from_salinity(0.0) == 0.0
    with pytest.raises(ValueError, match="non-negative"):
        magnesium_from_salinity(-1.0)


def test_omega_scales_as_the_square_of_hydroxide() -> None:
    """The reason a pH-scale slip is dangerous: `[OH-]` enters squared."""
    base = omega_brucite(1e-5, 35.0, KSP)
    assert omega_brucite(2e-5, 35.0, KSP) == pytest.approx(4 * base)
    assert omega_brucite(3e-5, 35.0, KSP) == pytest.approx(9 * base)
    # A 0.02 pH-unit error is ~10 % in Omega, which is the point of the warning.
    slipped = omega_brucite(1e-5 * 10**0.02, 35.0, KSP)
    assert slipped / base == pytest.approx(10**0.04, rel=1e-9)
    assert 1.09 < slipped / base < 1.10


def test_omega_scales_linearly_in_magnesium_and_inversely_in_ksp() -> None:
    base = omega_brucite(1e-5, 35.0, KSP)
    assert omega_brucite(1e-5, 17.5, KSP) == pytest.approx(base / 2), "Mg tracks salinity"
    assert omega_brucite(1e-5, 35.0, 2 * KSP) == pytest.approx(base / 2)


def test_the_solubility_product_is_required_and_must_be_physical() -> None:
    """Nothing is defaulted: an unsourced constant must not creep into the headline result."""
    with pytest.raises(TypeError):
        omega_brucite(1e-5, 35.0)  # type: ignore[call-arg]
    for bad in (0.0, -1e-12):
        with pytest.raises(ValueError, match="positive"):
            omega_brucite(1e-5, 35.0, bad)
    with pytest.raises(ValueError, match="non-negative"):
        omega_brucite(-1e-5, 35.0, KSP)


def test_hydroxide_comes_from_the_same_solve_as_the_ph() -> None:
    """`[OH-]` must be consistent with the `Kw` and pH scale PyCO2SYS used.

    Deriving it by hand from a pH on the wrong scale is the silent error this guards.
    """
    state = solve_from_alkalinity_dic(
        np.array([2300.0]), np.array([2000.0]), np.array([35.0]), np.array([10.0])
    )
    kw = state.constants  # noqa: F841  -- the scale lives with the constant set
    hydrogen = 10.0 ** (-state.ph_total)
    # PyCO2SYS's own Kw, recovered from its OH and H, must reproduce the reported OH.
    implied_kw = hydrogen * state.hydroxide * 1e-6
    assert implied_kw == pytest.approx(1.438e-14, rel=5e-3), "total-scale Kw at S=35, T=10"
    assert state.hydroxide[0] == pytest.approx(2.727, rel=1e-3)


def test_the_state_helper_handles_the_unit_change() -> None:
    """The class carries umol/kg and the arithmetic wants mol/kg -- one place to get it wrong."""
    state = solve_from_alkalinity_dic(
        np.array([2300.0]), np.array([2000.0]), np.array([35.0]), np.array([10.0])
    )
    direct = omega_brucite(state.hydroxide * 1e-6, state.salinity, KSP)
    assert state.omega_brucite(KSP) == pytest.approx(direct)


def test_alkalinity_addition_supersaturates_brucite_long_before_aragonite() -> None:
    """Why the exe's output is not enough for this project's driver.

    At an alkalinity-elevated condition the exe reports `OmegaA` and nothing else. Brucite
    responds far more sharply, because it goes as `[OH-]^2` while aragonite goes as
    `[CO3--]`, which is already near its ceiling once carbonate dominates.
    """
    ambient = solve_from_alkalinity_dic(
        np.array([2300.0]), np.array([2000.0]), np.array([35.0]), np.array([10.0])
    )
    dosed = solve_from_alkalinity_dic(
        np.array([4000.0]), np.array([1646.0]), np.array([35.0]), np.array([10.0])
    )
    assert ambient.ph_total[0] < 8.5 < dosed.ph_total[0]

    brucite_gain = dosed.omega_brucite(KSP)[0] / ambient.omega_brucite(KSP)[0]
    aragonite_gain = dosed.omega_aragonite[0] / ambient.omega_aragonite[0]
    assert brucite_gain > 100 * aragonite_gain, (
        f"brucite rose {brucite_gain:.0f}x against aragonite's {aragonite_gain:.1f}x"
    )


# ------------------------------------------------------- the explicit activity model


def test_ionic_strength_matches_the_standard_seawater_relation() -> None:
    assert ionic_strength_from_salinity(35.0) == pytest.approx(0.7228, abs=1e-4)
    assert ionic_strength_from_salinity(0.0) == 0.0


def test_activity_coefficients_land_in_the_literature_range() -> None:
    """Davies is past its stated range at seawater strength, so check it stays plausible."""
    gamma_mg = float(davies_activity_coefficient(2, 35.0, 10.0))
    gamma_oh = float(davies_activity_coefficient(1, 35.0, 10.0))
    assert 0.23 <= gamma_mg <= 0.36, gamma_mg
    assert 0.65 <= gamma_oh <= 0.80, gamma_oh
    # A divalent ion is far more strongly screened than a monovalent one: z^2 in the exponent.
    assert gamma_mg < gamma_oh**2


def test_brucite_dissolution_is_very_nearly_athermal() -> None:
    """Regression on a bug that would have been silent.

    An earlier revision carried -111.3 kJ/mol -- a formation-scale enthalpy where the
    *reaction* enthalpy is -2.29 kJ/mol, derived from standard formation enthalpies. That is
    ~48x too large and put a **10x error** into `Ksp*` at near-field temperature, with nothing
    downstream complaining. Real brucite dissolution barely responds to temperature.
    """
    warm = float(solubility_brucite(35.0, 25.0))
    cold = float(solubility_brucite(35.0, 10.0))
    assert cold / warm == pytest.approx(1.0, abs=0.05), "a 15 C swing is a few percent, not 10x"


def test_the_activity_correction_is_large_and_in_the_right_direction() -> None:
    """`Ksp*` must exceed the thermodynamic `Ksp`, because the gammas are below one.

    This is the whole reason a thermodynamic constant cannot be used with total
    concentrations unmodified -- doing so would overstate Omega several-fold.
    """
    thermodynamic = 10.0**BRUCITE_LOG_KSP_25C
    conditional = float(solubility_brucite(35.0, 25.0))
    assert conditional > thermodynamic
    assert 3.0 < conditional / thermodynamic < 10.0, conditional / thermodynamic
    # Fresh water is much less screened, so the correction shrinks toward 1.
    assert float(solubility_brucite(0.5, 25.0)) < conditional


def test_brucite_is_undersaturated_in_ordinary_seawater_and_not_when_dosed() -> None:
    """The qualitative result the whole quantity exists to deliver.

    Ordinary seawater does not precipitate brucite; alkalinity-elevated water can. The exe
    reports only aragonite, which rises far less steeply.
    """
    state = solve_from_alkalinity_dic(
        np.array([2300.0, 4000.0]),
        np.array([2000.0, 1646.0]),
        np.array([35.0, 35.0]),
        np.array([10.0, 10.0]),
    )
    omega = state.omega_brucite(solubility_brucite(state.salinity, state.temperature))
    assert omega[0] < 0.1, "ambient seawater is far below brucite saturation"
    assert omega[1] > 10.0, "the dosed condition is strongly supersaturated"
    assert omega[1] > state.omega_aragonite[1], "and more so than aragonite"


# ------------------------------------------------------- the error budget, measured (Phase 8.1)
#
# ⚠️⚠️ The module docstring above says every test here is independent of the `Ksp*` *value*, and
# these still are: they measure how much `Omega` **moves** when each input is pushed across its
# own uncertainty, which is a property of the arithmetic rather than of the constant. That is the
# point -- the budget has to be checkable before the constant is chosen, because the budget is
# what decides how much choosing it buys.
#
# The budget was stated qualitatively until 2026-08-21 and two of its four terms were wrong: the
# activity coefficients by an order of magnitude low, the temperature term by a factor of seven
# high. A prose error budget is exactly the kind of number this project has watched go stale four
# times on the coverage fraction alone, so it is pinned.

#: The sample the published budget is quoted at. A representative near-field plume, not an extreme.
_BUDGET_S, _BUDGET_T = 32.0, 11.0

#: The literature bounds `davies_activity_coefficient`'s own docstring quotes for seawater.
_GAMMA_BOUNDS = {"low": (0.23, 0.65), "high": (0.36, 0.76)}


def _omega_multiplier(ksp_star: float) -> float:
    """How much `Omega` changes relative to the shipped constant. `Omega` scales as `1/Ksp*`."""
    return float(solubility_brucite(_BUDGET_S, _BUDGET_T)) / ksp_star


def test_the_ksp_spread_is_the_two_and_a_half_times_it_is_published_as() -> None:
    """The one term the prose budget had right, now pinned rather than asserted in a docstring."""
    optimistic = float(solubility_brucite(_BUDGET_S, _BUDGET_T, log_ksp_25c=-10.9))
    pessimistic = float(solubility_brucite(_BUDGET_S, _BUDGET_T, log_ksp_25c=-11.3))
    assert optimistic / pessimistic == pytest.approx(2.51, abs=0.02)


def test_the_activity_coefficients_are_co_dominant_not_a_minor_term() -> None:
    """⭐⭐ The correction that reorders Phase 8.1.

    The budget called Davies "perhaps 10-20 %". Against the bounds this module itself quotes it
    is **2.14x** -- the same order as the `Ksp` spread. Ion pairing and the activity model are
    the same problem, so a Pitzer treatment is one change against two dominant terms rather than
    the last item on a list.
    """
    thermodynamic = 10.0**BRUCITE_LOG_KSP_25C
    spread = {
        name: _omega_multiplier(thermodynamic / (gamma_mg * gamma_oh**2))
        for name, (gamma_mg, gamma_oh) in _GAMMA_BOUNDS.items()
    }
    assert spread["high"] / spread["low"] == pytest.approx(2.14, abs=0.03)
    assert spread["high"] / spread["low"] > 1.5, (
        "if this ever falls to the 10-20 % the budget used to claim, the budget was right and "
        "this test is what changed -- check davies_activity_coefficient's quoted bounds"
    )


def test_davies_sits_at_the_optimistic_end_of_those_bounds() -> None:
    """⚠️ So `Omega` is biased **high** on the activity count as well as on ion pairing.

    Both known biases point the same way, which is what makes the current number quotable as an
    upper bound rather than merely uncertain.
    """
    thermodynamic = 10.0**BRUCITE_LOG_KSP_25C
    ours = _omega_multiplier(float(solubility_brucite(_BUDGET_S, _BUDGET_T)))
    low, high = (
        _omega_multiplier(thermodynamic / (mg * oh**2)) for mg, oh in _GAMMA_BOUNDS.values()
    )
    assert low < ours <= high * 1.02, (ours, low, high)
    assert ours > (low + high) / 2, "Davies should be above the midpoint of the quoted bounds"


def test_the_temperature_term_cancels_down_to_under_a_percent() -> None:
    """⭐ The thermodynamic `Ksp` moves 5 %; the conditional `Ksp*` that `Omega` uses moves 0.7 %.

    The Davies coefficients fall with temperature in the same direction as `Ksp`, so the two
    partly cancel. The published "5 % effect" was right about `Ksp` and wrong about the quantity
    that matters -- and this is the test that stops that being restated.
    """
    shift = -(BRUCITE_DISSOLUTION_ENTHALPY / _GAS_CONSTANT) * (
        1.0 / (10.0 + 273.15) - 1.0 / (25.0 + 273.15)
    )
    thermodynamic_ratio = float(np.exp(shift))
    assert thermodynamic_ratio == pytest.approx(1.050, abs=0.002), "the 5 % is real, on Ksp"

    conditional_ratio = float(solubility_brucite(_BUDGET_S, 10.0)) / float(
        solubility_brucite(_BUDGET_S, 25.0)
    )
    assert conditional_ratio == pytest.approx(1.007, abs=0.002), "but 0.7 % on Ksp*"
    assert thermodynamic_ratio - 1.0 > 5.0 * (conditional_ratio - 1.0), (
        "the cancellation is the finding; if it stops holding the budget needs re-measuring"
    )


def _ksp_star(log_ksp: float, gammas: tuple[float, float]) -> float:
    """`Ksp*` rebuilt from first principles for an arbitrary constant and activity pair.

    Deliberately not a call into `solubility_brucite` with overrides: that function owns the
    Davies model, and the point here is to substitute *different* activity coefficients for it.
    """
    gamma_mg, gamma_oh = gammas
    shift = -(BRUCITE_DISSOLUTION_ENTHALPY / _GAS_CONSTANT) * (
        1.0 / (_BUDGET_T + 273.15) - 1.0 / (25.0 + 273.15)
    )
    return 10.0**log_ksp * float(np.exp(shift)) / (gamma_mg * gamma_oh**2)


def test_the_published_bound_on_omega_is_the_one_the_budget_states() -> None:
    """⚠️ 5.37x is a *bound* over independent worst cases, not a confidence interval.

    The terms are not independent and the true spread is narrower. It is pinned because it is
    what the dose study may honestly quote before the literature pick is settled -- and an
    unpinned headline uncertainty is the same defect shape as an unpinned coverage fraction,
    which this project has watched go stale four times.
    """
    multipliers = [
        _omega_multiplier(_ksp_star(log_ksp, gammas))
        for log_ksp in (-10.9, -11.3)
        for gammas in _GAMMA_BOUNDS.values()
    ]
    assert max(multipliers) / min(multipliers) == pytest.approx(5.37, abs=0.10)
    # And the shipped value sits inside its own bound, which is the least it can do.
    assert min(multipliers) < 1.0 < max(multipliers)


# --------------------------------------------------------------- the saturation pH (2026-08-25)


def brucite_saturation_ph_total(salinity: float, temperature: float) -> float:
    """The total-scale pH at which `Ω_brucite` = 1, with magnesium conservative in salinity.

    `Ω = [Mg2+][OH-]^2 / Ksp*` and `[OH-] = Kw / [H+]`, so `Ω = 1` is one pH:

        [OH-]* = sqrt(Ksp* / [Mg2+]),   pH* = -log10(Kw / [OH-]*)

    `Kw` is recovered from a PyCO2SYS solve at the same S and T -- the same constant and scale
    `omega_brucite` is fed from -- so this is the analytical limit PLAN 8b asked for, not a
    second model. The TA/DIC used to get `Kw` are immaterial: `Kw` depends on S and T only.
    """
    state = solve_from_alkalinity_dic(
        np.array([2300.0]), np.array([2000.0]), np.array([salinity]), np.array([temperature])
    )
    kw = float(10.0 ** (-state.ph_total[0]) * state.hydroxide[0] * 1e-6)
    ksp = float(solubility_brucite(salinity, temperature))
    hydroxide_star = np.sqrt(ksp / float(magnesium_from_salinity(salinity)))
    return float(-np.log10(kw / hydroxide_star))


def test_the_saturation_ph_is_about_nine_point_four_in_cold_coastal_water() -> None:
    """⭐ `Ω_brucite = 1` is a **pH threshold**, and this is its value on the adopted `Ksp`.

    The dose dry run (`studies/dose_dry_run/`, 2026-08-25) found Ω falling through 1 at pH 9.41-9.42
    (total) on every dose from TA 4000 to 20 000 -- dose only moves how much dilution it takes to
    get there. That is what conservative magnesium implies, and this pins the number the study
    quotes. It moves with `Ksp` (0.1 pH per 0.2 in `log Ksp`, next test) and only weakly with S.

    ⚠️ **It moves strongly with temperature, and the reason is row 197's.** Brucite dissolution
    is athermal, so `Ksp*` barely moves, but `Kw` is not: `pKw` falls ~0.04 per °C, so a warmer
    water needs a *lower* pH to reach the same `[OH-]` and the threshold falls ~0.05 pH per °C --
    8.95 at 20 °C, 9.43 at 10 °C, 9.80 at 2 °C. A study quoting one threshold pH must say the
    temperature it is for; a cold ambient is the *more* protective case against brucite.
    """
    assert brucite_saturation_ph_total(32.0, 10.0) == pytest.approx(9.43, abs=0.02)
    assert brucite_saturation_ph_total(35.0, 10.0) == pytest.approx(9.38, abs=0.02)
    assert brucite_saturation_ph_total(35.0, 20.0) == pytest.approx(8.95, abs=0.03)
    assert brucite_saturation_ph_total(32.0, 2.0) == pytest.approx(9.80, abs=0.03)


def test_the_saturation_ph_tracks_ksp_as_half_its_log() -> None:
    """`[OH-]*` goes as `sqrt(Ksp)`, so 0.2 in `log Ksp` -- Xiong's stated band -- is 0.1 in pH*."""
    state = solve_from_alkalinity_dic(
        np.array([2300.0]), np.array([2000.0]), np.array([32.0]), np.array([10.0])
    )
    kw = float(10.0 ** (-state.ph_total[0]) * state.hydroxide[0] * 1e-6)
    mg = float(magnesium_from_salinity(32.0))
    phs = []
    for log_ksp in (BRUCITE_LOG_KSP_25C - 0.2, BRUCITE_LOG_KSP_25C + 0.2):
        ksp = float(solubility_brucite(32.0, 10.0, log_ksp_25c=log_ksp))
        phs.append(float(-np.log10(kw / np.sqrt(ksp / mg))))
    assert phs[1] - phs[0] == pytest.approx(0.2, abs=1e-9)
