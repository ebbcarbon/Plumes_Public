"""The second brucite engine: PHREEQC / `pitzer.dat` through `plumes2.chem.pitzer`.

Skipped as a module when `phreeqpython` is not installed (`pip install 'plumes2[pitzer]'`); CI
installs it. Every number asserted here was first measured in the 2026-09-09 spike
(`studies/pitzer_spike.py`, PHREEQC_PLAN.md §8) and is pinned as a regression guard, or is a
model-independent literature value (pKw), or is an identity between the two engines.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

pytest.importorskip("phreeqpython", reason="the Pitzer engine needs the plumes2[pitzer] extra")

from plumes2.chem import (
    davies_activity_coefficient,
    magnesium_from_salinity,
    solubility_brucite,
    solve_from_alkalinity_dic,
)
from plumes2.chem.constants import BRUCITE_DISSOLUTION_ENTHALPY, BRUCITE_LOG_KSP_25C
from plumes2.chem.pitzer import (
    MILLERO_2008_S35,
    PitzerConvergenceWarning,
    available,
    brucite_phases_block,
    record,
    reference_seawater,
    solve_pitzer,
    water_fraction,
)

SITE = {"salinity": 30.9, "temperature": 11.2}
DIC = 2092.0
DOSE_AXIS = np.array([2146.0, 4000.0, 6000.0, 20000.0])


# ------------------------------------------------------------------ composition


def test_the_composition_shares_magnesium_and_calcium_with_the_davies_engine() -> None:
    """The two engines must differ only in the activity treatment, so the totals are one number."""
    for s in (0.0, 17.5, 30.9, 35.0, 45.0):
        comp = reference_seawater(s)
        kgw = water_fraction(s)
        magnesium = float(magnesium_from_salinity(s))
        assert float(comp["Mg"] * kgw) == pytest.approx(magnesium, rel=1e-12)
        assert float(comp["Ca"] * kgw) == pytest.approx(0.01028 * s / 35.0, rel=1e-12)


def test_the_composition_is_conservative_with_salinity_and_empty_at_zero() -> None:
    half = reference_seawater(17.5)
    full = reference_seawater(35.0)
    # Per kg of *water* the ratio is not exactly one half: the water fraction differs too.
    ratio = float(water_fraction(35.0) / water_fraction(17.5))
    for element in MILLERO_2008_S35:
        assert float(half[element] / full[element]) == pytest.approx(0.5 * ratio, rel=1e-12)
    assert all(float(v) == 0.0 for v in reference_seawater(0.0).values())
    with pytest.raises(ValueError, match="non-negative"):
        reference_seawater(-1.0)


def test_total_boron_matches_the_borate_option_pyco2sys_uses() -> None:
    """Leaving boron out was worth +0.13 to +0.31 pH in the spike; it has to be the same boron."""
    import PyCO2SYS as pyco2

    for option in (1, 2):
        ours = float(reference_seawater(SITE["salinity"], borate_option=option)["B"])
        ours *= float(water_fraction(SITE["salinity"]))  # back to per kg of solution
        ref = pyco2.sys(
            par1=2146.0,
            par2=DIC,
            par1_type=1,
            par2_type=2,
            salinity=SITE["salinity"],
            temperature=SITE["temperature"],
            opt_total_borate=option,
        )
        assert ours * 1e6 == pytest.approx(float(ref["total_borate"]), rel=1e-3)
    with pytest.raises(ValueError, match="borate option"):
        reference_seawater(35.0, borate_option=3)


def test_the_reference_composition_is_nearly_charge_balanced_before_alkalinity() -> None:
    """Sodium closes the charge; it must not be asked to close much."""
    comp = reference_seawater(35.0)
    kgw = float(water_fraction(35.0))
    charge = {"Na": 1, "K": 1, "Mg": 2, "Ca": 2, "Sr": 2, "Cl": -1, "S(6)": -2, "Br": -1}
    net = sum(charge[e] * float(comp[e]) * kgw for e in charge)
    # Millero's reference water has TA 2300 umol/kg: the cation excess IS the alkalinity, and the
    # unlisted anions (F-, OH-) are 76 umol/kg of it.
    assert 0.0019 < net < 0.0024


# ------------------------------------------------------------------ engine


def test_the_brucite_override_carries_this_repos_constants_in_kcal() -> None:
    block = brucite_phases_block()
    assert f"log_k\t{BRUCITE_LOG_KSP_25C}" in block
    assert f"{BRUCITE_DISSOLUTION_ENTHALPY / 4184:.5f} kcal/mol" in block
    assert "-0.54732 kcal/mol" in block, "the -2.29 kJ/mol enthalpy, not pitzer.dat's +4.85"
    assert available()
    described = record().describe()
    assert "pitzer.dat" in described and "Xiong 2008" in described and "MgOH+" in described


# ------------------------------------------------------------------ speciation


@pytest.fixture(scope="module")
def dose_axis():  # type: ignore[no-untyped-def]
    return solve_pitzer(DOSE_AXIS, DIC, SITE["salinity"], SITE["temperature"])


def test_the_entered_dic_and_alkalinity_come_back_and_the_shape_is_kept(dose_axis) -> None:  # type: ignore[no-untyped-def]
    assert dose_axis.omega_brucite.shape == DOSE_AXIS.shape
    assert np.all(np.isfinite(dose_axis.omega_brucite))
    scalar = solve_pitzer(4000.0, DIC, SITE["salinity"], SITE["temperature"])
    assert scalar.omega_brucite.shape == ()
    assert float(scalar.omega_brucite) == pytest.approx(float(dose_axis.omega_brucite[1]), rel=1e-9)
    grid = solve_pitzer(DOSE_AXIS.reshape(2, 2), DIC, SITE["salinity"], SITE["temperature"])
    assert grid.ph_total.shape == (2, 2)
    np.testing.assert_allclose(grid.ph_total.reshape(-1), dose_axis.ph_total, rtol=1e-9)


def test_pitzer_ph_on_the_total_scale_agrees_with_pyco2sys_to_three_hundredths(dose_axis) -> None:  # type: ignore[no-untyped-def]
    """The spike's row C: the two engines agree on the carbonate side, given the same boron."""
    ours = solve_from_alkalinity_dic(DOSE_AXIS, DIC, SITE["salinity"], SITE["temperature"])
    gap = dose_axis.ph_total - ours.ph_total
    assert np.all(np.abs(gap) <= 0.03), gap
    # The scales sit in the textbook order in seawater: NBS above free above total.
    assert np.all(dose_axis.ph_nbs > dose_axis.ph_free)
    assert np.all(dose_axis.ph_free > dose_axis.ph_total)


def test_the_pitzer_omega_sits_seven_to_eight_times_below_the_davies_bound(dose_axis) -> None:  # type: ignore[no-untyped-def]
    """The spike's row D, pinned: 6.8-8.4x, rising gently with pH, never above the bound."""
    davies = solve_from_alkalinity_dic(DOSE_AXIS, DIC, SITE["salinity"], SITE["temperature"])
    bound = davies.omega_brucite(solubility_brucite(SITE["salinity"], SITE["temperature"]))
    ratio = bound / dose_axis.omega_brucite
    assert np.all(ratio > 1.0), "the Davies value is an upper bound; Pitzer must sit below it"
    # 7.6-7.9 across the axis on one concentration basis (the spike's 6.8-8.4 mixed bases): nearly
    # flat, rising a little from the ambient to the top of the axis as MgOH+ pairing grows.
    assert 7.0 < float(ratio.min()) and float(ratio.max()) < 9.0, ratio
    assert ratio[-1] > ratio[0], "the gap widens with pH as MgOH+ pairing grows"
    # The TA 4000 cell is the study's flip: supersaturated by the bound, not by Pitzer.
    assert bound[1] > 3.0 and dose_axis.omega_brucite[1] < 0.5


def test_the_ratio_decomposes_into_its_terms(dose_axis) -> None:  # type: ignore[no-untyped-def]
    """Why the columns differ, term by term -- the primer's table (PORTING_THE_PHYSICS §4)."""
    davies = solve_from_alkalinity_dic(DOSE_AXIS, DIC, SITE["salinity"], SITE["temperature"])
    g_mg = float(davies_activity_coefficient(2, SITE["salinity"], SITE["temperature"]))
    g_oh = float(davies_activity_coefficient(1, SITE["salinity"], SITE["temperature"]))
    i = 3  # TA 20 000
    # PyCO2SYS's hydroxide is the total; PHREEQC splits it into free OH- and the MgOH+ pair.
    # Within 5 %: the two engines' Kw and pairing constants differ, and PyCO2SYS's total also
    # carries what PHREEQC books under other pairs (CaOH+ is not in pitzer.dat; NaOH is not a pair).
    total_from_parts = dose_axis.hydroxide_free[i] + dose_axis.magnesium_hydroxide[i]
    assert total_from_parts == pytest.approx(float(davies.hydroxide[i]), rel=0.05)
    pair_share = dose_axis.magnesium_hydroxide[i] / total_from_parts
    assert 0.40 < pair_share < 0.48
    assert 0.25 < dose_axis.gamma_magnesium[i] < 0.27
    assert 0.53 < dose_axis.gamma_hydroxide[i] < 0.56
    magnesium_total = float(magnesium_from_salinity(SITE["salinity"])) * 1e6
    product = (
        (magnesium_total / dose_axis.magnesium_free[i])
        * (g_mg / dose_axis.gamma_magnesium[i])
        * (g_oh / dose_axis.gamma_hydroxide[i]) ** 2
        * (float(davies.hydroxide[i]) / dose_axis.hydroxide_free[i]) ** 2
    )
    ksp = solubility_brucite(SITE["salinity"], SITE["temperature"])
    bound = float(davies.omega_brucite(ksp)[i])
    # Until 2026-09-10 a last factor sat here: the Davies column's own basis slip,
    # `water_fraction**3` = 0.91 at S 30.9, from per-kg-of-solution concentrations against a molal
    # Ksp. `omega_brucite` now forms its product on the molal scale, so the four terms above are
    # the whole ratio (8.7x at TA 20 000, row 289) and the slip is gone from the decomposition.
    assert product == pytest.approx(bound / dose_axis.omega_brucite[i], rel=0.02)


def test_omega_is_the_saturation_index_exponentiated(dose_axis) -> None:  # type: ignore[no-untyped-def]
    np.testing.assert_allclose(dose_axis.omega_brucite, 10.0**dose_axis.si_brucite)
    assert np.all(np.isfinite(dose_axis.si_aragonite)) and np.all(np.isfinite(dose_axis.si_calcite))
    assert 0.6 < float(dose_axis.ionic_strength[0]) < 0.65


def test_pkw_matches_harned_and_owen() -> None:
    """Model-independent: pure water's ion product, 13.995 at 25 C and 14.535 at 10 C (+-0.01)."""
    for temperature, pkw in ((25.0, 13.995), (10.0, 14.535)):
        state = solve_pitzer(0.0, 0.0, 0.0, temperature)
        # Pure water: pH_free = pOH; pKw = 2 pH. PHREEQC's NBS pH equals the free pH at I -> 0.
        assert float(2.0 * state.ph_free) == pytest.approx(pkw, abs=0.01)
        assert float(state.ph_nbs) == pytest.approx(float(state.ph_free), abs=1e-3)


def test_pure_water_dosed_with_hydroxide_reads_the_textbook_ph() -> None:
    """1 mmol/kg NaOH in pure water at 25 C is pH 10.98 (activity; 11.0 before gamma).

    ⚠️ This is the DIC 0 path -- the dose study's pure-water effluents. PHREEQC's `Alkalinity`
    keyword leaves the pH at its guess (8.0) here; stating TA through the charge balance does not.
    """
    state = solve_pitzer(1000.0, 0.0, 0.0, 25.0)
    assert float(state.ph_nbs) == pytest.approx(10.98, abs=0.02)
    assert float(state.ph_free) == pytest.approx(10.97, abs=0.02)
    assert float(state.omega_brucite) == 0.0, "no magnesium, no brucite"
    # A little seawater mixed in: still solved, and now there is magnesium to pair with.
    mixed = solve_pitzer(3000.0, 0.0, 0.05, 11.2)
    assert 11.5 < float(mixed.ph_total) < 12.5 and float(mixed.omega_brucite) > 0.0


def test_a_row_phreeqc_cannot_solve_is_nan_and_named_not_fatal() -> None:
    """One bad sample must not blank a frame."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        state = solve_pitzer(
            np.array([4000.0, np.nan, 6000.0]), DIC, SITE["salinity"], SITE["temperature"]
        )
    assert np.isfinite(state.omega_brucite[0]) and np.isfinite(state.omega_brucite[2])
    assert math.isnan(float(state.omega_brucite[1]))
    messages = [str(w.message) for w in caught if w.category is PitzerConvergenceWarning]
    assert len(messages) == 1 and "1 of 3 rows" in messages[0] and "index 1" in messages[0]


# ------------------------------------------------------------------ wired into a run


def _dosed_run(samples: int = 32, **carbonate):  # type: ignore[no-untyped-def]
    """case03's ambient, a TA 4000 / pH 10.5 effluent, with the given carbonate settings."""
    from plumes2 import load_project
    from plumes2.config import EffluentChemistry
    from plumes2.results import run
    from tests.conftest import REFERENCE_CASES

    case = load_project(
        REFERENCE_CASES / "case03_carbonate" / "test.prj", warn_on_drift=False
    ).to_case()
    case = case.model_copy(
        update={
            "effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5),
            "carbonate": case.carbonate.model_copy(update=carbonate),
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(case, samples=samples)


@pytest.fixture(scope="module")
def pitzer_run():  # type: ignore[no-untyped-def]
    """`carbonate.pitzer` on under the default solver -- 32 samples."""
    return _dosed_run(pitzer=True)


# ------------------------------------------------------------------ the solver selector


def test_solver_none_runs_the_plume_with_no_chemistry_columns() -> None:
    from plumes2.config import ChemistrySolver
    from plumes2.results import CHEMISTRY_COLUMNS, NEARFIELD_COLUMNS

    result = _dosed_run(samples=16, solver=ChemistrySolver.NONE)
    assert not result.has_chemistry and not result.has_pitzer
    assert list(result.nearfield.columns) == list(NEARFIELD_COLUMNS)
    assert result.farfield is not None
    assert not set(CHEMISTRY_COLUMNS) & set(result.farfield.columns)
    assert result.provenance.chemistry_engines is None


def test_solver_phreeqc_fills_every_chemistry_column_from_the_pitzer_engine() -> None:
    from plumes2.config import ChemistrySolver
    from plumes2.results import CHEMISTRY_COLUMNS, NEARFIELD_COLUMNS

    ours = _dosed_run(samples=24)
    theirs = _dosed_run(samples=24, solver=ChemistrySolver.PHREEQC)
    assert theirs.has_chemistry and not theirs.has_pitzer
    assert list(theirs.nearfield.columns) == [*NEARFIELD_COLUMNS, *CHEMISTRY_COLUMNS]
    a, b = ours.nearfield, theirs.nearfield
    # The mixing is the same under every solver; only the re-solve differs.
    np.testing.assert_allclose(b["total_alkalinity_umol_kg"], a["total_alkalinity_umol_kg"])
    np.testing.assert_allclose(b["dic_umol_kg"], a["dic_umol_kg"])
    assert float((b["ph_total"] - a["ph_total"]).abs().max()) <= 0.03
    # Brucite: the PHREEQC column IS the Pitzer value, 5-12x below the Davies bound.
    ratio = a["omega_brucite"] / b["omega_brucite"]
    assert 5.0 < float(ratio.min()) and float(ratio.max()) < 12.0
    # The carbonate minerals are PHREEQC's own -- and on this water they sit 2 % above Mucci's at
    # ambient pH and ~10 % at the pH 10.5 port, one-signed. (The blending tool's 1.64x was its own
    # low-calcium 8 C water plus a pH-scale slip; the plan's row G predicted 1.5-1.8x -- a miss.)
    arag = b["omega_aragonite"] / a["omega_aragonite"]
    assert 1.0 < float(arag.min()) < 1.05 and float(arag.max()) < 1.3, arag.describe()
    assert np.all(np.isfinite(b["pco2_uatm"])) and np.all(b["pco2_uatm"] > 0)
    # Total carbonate ion: PHREEQC speciates ~6 % less CO3-2 (free + MgCO3) than PyCO2SYS's
    # stoichiometric total, while its aragonite SI sits 2 % higher -- the activity coefficient
    # doing the rest. Within 15 % either way is the claim; the sign is not.
    assert 0.85 < float((b["carbonate_umol_kg"] / a["carbonate_umol_kg"]).mean()) < 1.15
    engines = theirs.provenance.chemistry_engines
    assert engines and engines.startswith("solver: phreeqc") and "pitzer.dat" in engines
    # And the far field continues from the near-field end, as under the default solver.
    assert theirs.farfield is not None
    assert float(theirs.farfield["omega_brucite"].iloc[0]) == pytest.approx(
        float(b["omega_brucite"].iloc[-1]), rel=0.05
    )


def test_solver_all_carries_both_engines_side_by_side(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Cross-comparison: PyCO2SYS under the usual names, PHREEQC as `*_phreeqc`, row for row."""
    from plumes2.config import ChemistrySolver
    from plumes2.report import build_report
    from plumes2.results import CHEMISTRY_COLUMNS, NEARFIELD_COLUMNS, PHREEQC_COLUMNS, write_results
    from plumes2.sweep import brucite_extract

    both = _dosed_run(samples=24, solver=ChemistrySolver.ALL)
    theirs = _dosed_run(samples=24, solver=ChemistrySolver.PHREEQC)
    ours = _dosed_run(samples=24)
    assert both.has_chemistry and both.has_comparison and not both.has_pitzer
    assert list(both.nearfield.columns) == [
        *NEARFIELD_COLUMNS,
        *CHEMISTRY_COLUMNS,
        *PHREEQC_COLUMNS,
    ]
    # The usual names are PyCO2SYS's, the suffixed ones are exactly the phreeqc solver's.
    for column in CHEMISTRY_COLUMNS:
        np.testing.assert_allclose(both.nearfield[column], ours.nearfield[column])
    for column in PHREEQC_COLUMNS:
        base = column.removesuffix("_phreeqc")
        np.testing.assert_allclose(both.nearfield[column], theirs.nearfield[base])
    assert both.farfield is not None and set(PHREEQC_COLUMNS) <= set(both.farfield.columns)
    engines = both.provenance.chemistry_engines
    assert engines and engines.startswith("solver: all")
    # Sweeps read the PHREEQC brucite under the same keys as the pitzer flag would give.
    out = brucite_extract(both)
    assert out["nearfield_peak_omega_brucite_phreeqc"] < out["nearfield_peak_omega_brucite"]
    # The report gets the comparison panel, and the pH / saturation panels carry both engines.
    provenance = (write_results(both, tmp_path / "run") / "provenance.yaml").read_text("utf-8")
    assert "has_comparison: True" in provenance and "omega_aragonite_phreeqc:" in provenance
    target = build_report(both, tmp_path / "both.html")
    html = target.read_text(encoding="utf-8")
    assert (
        "solver-comparison" in html
        and "brucite (PHREEQC)" in html
        and "aragonite (PHREEQC)" in html
    )


def test_the_pitzer_column_is_only_valid_beside_the_default_solver() -> None:
    from plumes2.config import CarbonateSettings, ChemistrySolver

    with pytest.raises(ValueError, match="nothing to sit beside"):
        CarbonateSettings(solver=ChemistrySolver.PHREEQC, pitzer=True)
    with pytest.raises(ValueError, match="nothing to sit beside"):
        CarbonateSettings(solver=ChemistrySolver.NONE, pitzer=True)
    with pytest.raises(ValueError, match="already there"):
        CarbonateSettings(solver=ChemistrySolver.ALL, pitzer=True)
    assert CarbonateSettings(solver="phreeqc").solver is ChemistrySolver.PHREEQC
    assert CarbonateSettings().solver is ChemistrySolver.PYCO2SYS


def test_the_pitzer_columns_follow_the_chemistry_columns_when_asked(pitzer_run) -> None:  # type: ignore[no-untyped-def]
    from plumes2.results import CHEMISTRY_COLUMNS, NEARFIELD_COLUMNS, PITZER_COLUMNS

    assert pitzer_run.has_chemistry and pitzer_run.has_pitzer
    assert list(pitzer_run.nearfield.columns) == [
        *NEARFIELD_COLUMNS,
        *CHEMISTRY_COLUMNS,
        *PITZER_COLUMNS,
    ]
    near = pitzer_run.nearfield
    assert np.all(np.isfinite(near["omega_brucite_phreeqc"]))
    # The bound stays the bound: every row's Pitzer value sits below the Davies value.
    ratio = near["omega_brucite"] / near["omega_brucite_phreeqc"]
    assert (ratio > 1.0).all() and 5.0 < float(ratio.min()) and float(ratio.max()) < 12.0
    # The pH diagnostic tracks PyCO2SYS within the spike's 0.03 along the whole plume.
    assert float((near["ph_total_phreeqc"] - near["ph_total"]).abs().max()) <= 0.03
    # The far field carries the same two columns, continuing from the near-field end.
    assert pitzer_run.farfield is not None
    assert {"omega_brucite_phreeqc", "ph_total_phreeqc"} <= set(pitzer_run.farfield.columns)
    assert float(pitzer_run.farfield["omega_brucite_phreeqc"].iloc[0]) == pytest.approx(
        float(near["omega_brucite_phreeqc"].iloc[-1]), rel=0.05
    )


def test_the_run_records_the_engine_and_writes_the_columns(pitzer_run, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from plumes2.results import write_results

    engines = pitzer_run.provenance.chemistry_engines
    assert engines and "pitzer.dat" in engines and "phreeqpython" in engines
    assert any("engines" in line for line in pitzer_run.provenance.as_comment_lines())
    target = write_results(pitzer_run, tmp_path)
    provenance = (target / "provenance.yaml").read_text(encoding="utf-8")
    assert "has_pitzer: True" in provenance and "omega_brucite_phreeqc:" in provenance


def test_the_sweep_extract_carries_both_engines(pitzer_run) -> None:  # type: ignore[no-untyped-def]
    from plumes2.sweep import brucite_extract

    out = brucite_extract(pitzer_run)
    for key in (
        "port_omega_brucite_phreeqc",
        "nearfield_peak_omega_brucite_phreeqc",
        "nearfield_end_omega_brucite_phreeqc",
    ):
        assert key in out and np.isfinite(out[key])
    assert out["nearfield_peak_omega_brucite_phreeqc"] < out["nearfield_peak_omega_brucite"]


def test_a_run_without_the_flag_has_no_pitzer_columns_and_no_engine_record(cheap_run) -> None:  # type: ignore[no-untyped-def]
    assert not cheap_run.has_pitzer
    assert not any("pitzer" in c for c in cheap_run.nearfield.columns)
    assert cheap_run.provenance.chemistry_engines is None


def test_asking_without_the_package_is_one_clear_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import importlib

    from plumes2.chem.pitzer import PitzerUnavailableError

    # The package re-exports the *function* `engine`, shadowing the submodule's name.
    engine_module = importlib.import_module("plumes2.chem.pitzer.engine")
    engine_module.engine.cache_clear()
    monkeypatch.setattr(engine_module, "available", lambda: False)
    try:
        with pytest.raises(PitzerUnavailableError, match=r"plumes2\[pitzer\]"):
            solve_pitzer(4000.0, DIC, SITE["salinity"], SITE["temperature"])
    finally:
        engine_module.engine.cache_clear()


def test_the_batched_call_leaves_no_solutions_behind() -> None:
    """The engine is a process singleton; a leak here would grow with every frame."""
    from plumes2.chem.pitzer import engine

    pp = engine()
    solve_pitzer(DOSE_AXIS, DIC, SITE["salinity"], SITE["temperature"])
    # The batch defined solutions 1-4 and deleted them on its way out: `USE solution 1` finds
    # nothing to calculate and the selected output is empty -- not even a header.
    pp.ip.run_string("SELECTED_OUTPUT\n\t-reset false\n\t-pH\nEND\nUSE solution 1\nEND\n")
    assert len(pp.ip.get_selected_output_array()) == 0
