"""Carbonate chemistry, against the reference cases and against PyCO2SYS itself."""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pytest

from plumes2.chem import (
    ARAGONITE_HIGH_SALINITY,
    ARAGONITE_LOW_SALINITY,
    ARAGONITE_LOW_SALINITY_AS_DIALOGUED,
    CALCITE,
    CALCIUM_AT_S35,
    EXE_K1K2_OPTIONS,
    EXE_KSO4_OPTIONS,
    RateLaw,
    UnknownConstantOptionError,
    aragonite_laws,
    calcium_from_salinity,
    carbonate_ion,
    effluent_endmember,
    mix,
    plume_carbonate,
    precipitation_rate,
    resolve_constants,
    saturation_states,
    solubility_aragonite,
    solubility_calcite,
    solve_from_alkalinity_dic,
    solve_from_alkalinity_ph,
    warn_outside_ph_window,
    warn_outside_validity,
)
from plumes2.config import (
    CarbonateSettings,
    ConstantRangeWarning,
    EffluentChemistry,
    PHRangeWarning,
    PHScale,
)
from plumes2.io.csv_tables import read_csv_table
from plumes2.io.dat import read_dat

CASES = Path(__file__).resolve().parent.parent / "reference_cases"
CASE03 = CASES / "case03_macoma_carbonate"
CASE04 = CASES / "case04_macoma_ta_dic"

#: The exe's own dialog selections for both carbonate cases.
EXE_K1K2 = 10
EXE_KSO4 = 1


# --------------------------------------------------------------------------- constants


def test_calcium_matches_the_manual_relation() -> None:
    assert calcium_from_salinity(35.0) == pytest.approx(CALCIUM_AT_S35)
    assert calcium_from_salinity(0.0) == pytest.approx(0.0)
    # Linear in salinity, so halving S halves calcium.
    assert calcium_from_salinity(17.5) == pytest.approx(CALCIUM_AT_S35 / 2.0)


def test_calcium_rejects_negative_salinity() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        calcium_from_salinity(-1.0)


def test_solubility_matches_pyco2sys_exactly() -> None:
    """Our Mucci (1983) implementation is PyCO2SYS's, not merely close to it."""
    pyco2 = pytest.importorskip("PyCO2SYS")
    salinity = np.array([30.0, 33.0, 35.0, 38.0, 45.0])
    temperature = np.array([5.0, 10.0, 15.0, 20.0, 25.0])
    result = pyco2.sys(
        par1=2300.0,
        par2=2000.0,
        par1_type=1,
        par2_type=2,
        salinity=salinity,
        temperature=temperature,
        pressure=0.0,
        opt_k_carbonic=EXE_K1K2,
        opt_k_bisulfate=EXE_KSO4,
    )
    np.testing.assert_allclose(
        solubility_calcite(salinity, temperature),
        np.asarray(result["k_calcite"], dtype=float),
        rtol=1e-12,
    )
    np.testing.assert_allclose(
        solubility_aragonite(salinity, temperature),
        np.asarray(result["k_aragonite"], dtype=float),
        rtol=1e-12,
    )


def test_constant_options_map_and_record_provenance() -> None:
    constants = resolve_constants(EXE_K1K2, EXE_KSO4)
    assert constants.pyco2sys_k_carbonic == 10
    assert constants.pyco2sys_k_bisulfate == 1
    assert constants.pyco2sys_total_borate == 1
    assert "Lueker" in constants.k1k2_reference
    assert "Dickson" in constants.bisulfate_reference
    assert "Uppstrom" in constants.borate_reference
    # Confirmed by the dialog help text, so `describe` must not hedge.
    assert constants.correspondence_confirmed
    assert "confirmed" in constants.describe()
    assert "ASSUMED" not in constants.describe()


def test_the_exe_k1k2_options_are_the_classic_list_of_fourteen() -> None:
    """The dialog enumerates 14, not the "ten" the manual claims, and PyCO2SYS agrees."""
    assert sorted(EXE_K1K2_OPTIONS) == list(range(1, 15))
    # The exe's number *is* PyCO2SYS's opt_k_carbonic, for every option.
    for option in EXE_K1K2_OPTIONS:
        assert resolve_constants(option, 1).pyco2sys_k_carbonic == option


def test_the_kso4_selector_is_a_bisulfate_borate_pair() -> None:
    """Four options = {Dickson, Khoo} x {Uppstrom, Lee}, i.e. CO2SYS's KSO4CONSTANTS."""
    assert sorted(EXE_KSO4_OPTIONS) == [1, 2, 3, 4]
    pairs = {
        option: (
            resolve_constants(10, option).pyco2sys_k_bisulfate,
            resolve_constants(10, option).pyco2sys_total_borate,
        )
        for option in EXE_KSO4_OPTIONS
    }
    assert pairs == {1: (1, 1), 2: (2, 1), 3: (1, 2), 4: (2, 2)}
    # All four are reachable -- nothing is refused any more.
    assert len({pairs[o] for o in pairs}) == 4


def test_the_reported_ph_scale_follows_k1k2() -> None:
    """The dialog's rule: "pH scale will be the same as K1,K2"."""
    assert resolve_constants(10, 1).native_ph_scale is PHScale.TOTAL
    assert resolve_constants(1, 1).native_ph_scale is PHScale.TOTAL
    assert resolve_constants(4, 1).native_ph_scale is PHScale.SEAWATER
    assert resolve_constants(6, 1).native_ph_scale is PHScale.NBS
    # The pure-water option's scale is not stated in the dialog text.
    assert resolve_constants(8, 1).native_ph_scale is None


def test_validity_ranges_flag_out_of_range_plumes() -> None:
    """Lueker was fitted over S 19-43, and case07's 45 psu effluent leaves that window."""
    constants = resolve_constants(10, 1)
    assert constants.validity.describe() == "T 2-35 C, S 19-43"
    inside = constants.covers(salinity=[31.0, 35.0, 43.0], temperature=10.0)
    assert bool(np.all(inside))
    assert not bool(constants.covers(salinity=45.0, temperature=10.0))
    assert not bool(constants.covers(salinity=31.0, temperature=40.0))


@pytest.mark.parametrize(("k1k2", "kso4"), [(0, 1), (15, 1), (10, 5), (10, 0)])
def test_unknown_constant_options_are_refused_not_guessed(k1k2: int, kso4: int) -> None:
    with pytest.raises(UnknownConstantOptionError):
        resolve_constants(k1k2, kso4)


# -------------------------------------------------------------------------- saturation


def test_carbonate_ion_reduces_to_dic_at_high_ph() -> None:
    """As H goes to zero all DIC is carbonate, so eq 21 tends to DIC itself."""
    dic = 2.0e-3
    assert carbonate_ion(dic, 14.0, 1.4e-6, 1.2e-9) == pytest.approx(dic, rel=1e-4)


def test_saturation_states_keep_the_solubility_ratio() -> None:
    """Omega_calcite / Omega_aragonite is Ksp_aragonite / Ksp_calcite: calcium cancels."""
    salinity, temperature = 32.0, 11.0
    omega_c, omega_a = saturation_states(2.0e-4, salinity, temperature)
    assert omega_c / omega_a == pytest.approx(
        float(solubility_aragonite(salinity, temperature))
        / float(solubility_calcite(salinity, temperature))
    )


def test_saturation_states_agree_with_pyco2sys() -> None:
    """Our Omega, via the manual's own equations, reproduces PyCO2SYS's."""
    pyco2 = pytest.importorskip("PyCO2SYS")
    salinity = np.array([30.0, 33.0, 35.0])
    temperature = np.array([8.0, 12.0, 18.0])
    result = pyco2.sys(
        par1=np.array([2300.0, 2400.0, 2500.0]),
        par2=np.array([2000.0, 2100.0, 2200.0]),
        par1_type=1,
        par2_type=2,
        salinity=salinity,
        temperature=temperature,
        pressure=0.0,
        opt_pH_scale=1,
        opt_k_carbonic=EXE_K1K2,
        opt_k_bisulfate=EXE_KSO4,
    )
    carbonate = carbonate_ion(
        np.asarray(result["dic"], dtype=float) * 1e-6,
        np.asarray(result["pH_total"], dtype=float),
        np.asarray(result["k_carbonic_1"], dtype=float),
        np.asarray(result["k_carbonic_2"], dtype=float),
    )
    omega_c, omega_a = saturation_states(carbonate, salinity, temperature)
    # The only difference is calcium: the manual rounds to 0.01028 at S = 35 where
    # PyCO2SYS carries Riley & Tongudai (1967) in full, 0.0102845. That is a fixed
    # 0.04 % low, so our Omega is uniformly 0.04 % low and nothing else differs.
    riley_tongudai = 0.02128 / 40.087 / 1.80655 * 35.0
    expected_ratio = CALCIUM_AT_S35 / riley_tongudai
    assert expected_ratio == pytest.approx(0.99956, abs=1e-5)
    for ours, key in (
        (omega_c, "saturation_calcite"),
        (omega_a, "saturation_aragonite"),
    ):
        theirs = np.asarray(result[key], dtype=float)
        np.testing.assert_allclose(ours / theirs, expected_ratio, rtol=1e-9)


# ----------------------------------------------------------------------- precipitation


def test_rate_constant_is_exp_of_log_k_not_ten_to_it() -> None:
    """Confirmed against case03's R_cal column; see precipitation.py."""
    assert CALCITE.rate_constant == pytest.approx(math.exp(-0.106))
    assert CALCITE.rate_constant != pytest.approx(10.0**-0.106)


def test_precipitation_follows_the_dialog_formula() -> None:
    omega = 3.0
    expected = math.exp(-0.106) * (omega - 1.0) ** 2.87
    assert float(precipitation_rate(omega, 32.0, CALCITE)) == pytest.approx(expected)


def test_undersaturated_water_precipitates_nothing_by_default() -> None:
    rate = precipitation_rate(np.array([0.5, 1.0, 2.0]), 32.0, CALCITE)
    assert not np.any(np.isnan(rate))
    np.testing.assert_array_equal(rate[:2], [0.0, 0.0])
    assert rate[2] > 0.0


def test_undersaturated_nan_is_reproducible_on_request() -> None:
    """The exe's unguarded fractional power, which poisons the rest of a run (case09)."""
    rate = precipitation_rate(
        np.array([0.5, 1.0, 2.0]), 32.0, CALCITE, reproduce_undersaturated_nan=True
    )
    assert math.isnan(rate[0])
    assert rate[1] == 0.0
    assert rate[2] > 0.0


def test_aragonite_uses_the_dialogued_low_band_by_default() -> None:
    """In the exe's dead band the default still precipitates, using the coefficients it offers."""
    rate = precipitation_rate(3.0, 32.0, aragonite_laws())
    assert float(rate) == pytest.approx(math.exp(1.53) * 2.0**2.33)


def test_the_exes_dead_band_is_reproducible_on_request() -> None:
    """`25 <= S <= 35` reports zero -- and only there. Below 25 the exe evaluates the band."""
    laws = aragonite_laws(reproduce_band_gap=True)
    assert float(precipitation_rate(3.0, 32.0, laws)) == 0.0
    # ⚠️ Not a floor at 35: below 25 the low band applies, which case13 shows over 15 rows.
    assert float(precipitation_rate(3.0, 3.0, laws)) == pytest.approx(math.exp(1.53) * 2.0**2.33)
    assert float(precipitation_rate(3.0, 24.0, laws)) == pytest.approx(math.exp(1.53) * 2.0**2.33)
    # The high-salinity band is unaffected either way.
    assert float(precipitation_rate(3.0, 36.0, laws)) == pytest.approx(math.exp(1.11) * 2.0**2.26)


def test_the_high_salinity_band_wins_where_the_bands_could_overlap() -> None:
    assert float(precipitation_rate(3.0, 36.0, aragonite_laws())) == pytest.approx(
        math.exp(1.11) * 2.0**2.26
    )


def test_the_dialog_bands_are_as_transcribed() -> None:
    """calcite 0<S<44; aragonite 0<S<35 and 35<S<44, two discrete bands -- as *written*."""
    assert (CALCITE.salinity_min, CALCITE.salinity_max) == (0.0, 44.0)
    assert (
        ARAGONITE_LOW_SALINITY_AS_DIALOGUED.salinity_min,
        ARAGONITE_LOW_SALINITY_AS_DIALOGUED.salinity_max,
    ) == (0.0, 35.0)
    assert (ARAGONITE_HIGH_SALINITY.salinity_min, ARAGONITE_HIGH_SALINITY.salinity_max) == (
        35.0,
        44.0,
    )


def test_the_low_band_the_exe_evaluates_stops_at_25() -> None:
    """⚠️ Measured, not transcribed: case13 brackets the edge to (24.613, 25.305].

    Same coefficients as the dialogued band -- only the edge moves, which is the whole finding.
    """
    assert (ARAGONITE_LOW_SALINITY.salinity_min, ARAGONITE_LOW_SALINITY.salinity_max) == (
        0.0,
        25.0,
    )
    assert ARAGONITE_LOW_SALINITY.log_k == ARAGONITE_LOW_SALINITY_AS_DIALOGUED.log_k
    assert ARAGONITE_LOW_SALINITY.exponent == ARAGONITE_LOW_SALINITY_AS_DIALOGUED.exponent


def test_the_calcite_log_k_is_negative() -> None:
    """Transcribed once as -1.06e-1 and once as 1.06e-01; the exe's R_cal picks negative.

    An unconstrained fit of log R against log(omega-1) over 153 rows of case03, case04 and
    case06 gives logK = -0.10600 under exp(). Under 10** the dialog would have to read
    -0.04604. A positive 0.106 would make the rate 24 % higher.
    """
    assert CALCITE.log_k == pytest.approx(-0.106)
    assert CALCITE.rate_constant == pytest.approx(math.exp(-0.106), rel=1e-9)
    assert CALCITE.rate_constant < 1.0


def test_rate_is_zero_outside_every_band() -> None:
    assert float(precipitation_rate(3.0, 50.0, aragonite_laws())) == 0.0
    assert float(precipitation_rate(3.0, 50.0, CALCITE)) == 0.0


def test_precipitation_requires_a_law() -> None:
    with pytest.raises(ValueError, match="at least one rate law"):
        precipitation_rate(3.0, 32.0, ())


def test_precipitation_broadcasts_omega_against_salinity() -> None:
    law = RateLaw("calcite", log_k=0.0, exponent=1.0, salinity_min=0.0, salinity_max=44.0)
    rate = precipitation_rate(np.array([2.0, 3.0, 4.0]), np.array([10.0, 20.0, 50.0]), law)
    np.testing.assert_allclose(rate, [1.0, 2.0, 0.0])


# --------------------------------------------------------------------------- transport


def test_mixing_is_a_dilution_weighted_average() -> None:
    assert float(mix(4000.0, 2900.0, 1.0)) == pytest.approx(4000.0)
    assert float(mix(4000.0, 2900.0, 2.0)) == pytest.approx(3450.0)
    # High dilution tends to the ambient value.
    assert float(mix(4000.0, 2900.0, 1e6)) == pytest.approx(2900.0, abs=1e-2)


def test_mixing_rejects_dilution_below_one() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        mix(4000.0, 2900.0, 0.5)


def test_effluent_pairing_prefers_dic_over_ph() -> None:
    """case04: TA 4000 with DIC 1646 and pH 11 both entered keeps 1646 and drops the pH."""
    chemistry = EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)
    endmember = effluent_endmember(chemistry, 35.0, 10.0)
    assert endmember.dic == pytest.approx(1646.0)
    assert not endmember.dic_derived_from_ph


def test_effluent_pairing_falls_back_to_free_scale_ph() -> None:
    """case03: TA 4000 with pH 10.5 free gives the DIC 1646 the exe went on to use."""
    chemistry = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE)
    endmember = effluent_endmember(chemistry, 35.0, 10.0)
    assert endmember.dic_derived_from_ph
    assert endmember.dic == pytest.approx(1646.0, abs=1.0)


def test_the_free_scale_is_what_the_data_selects() -> None:
    """Total and NBS are far enough off to be excluded outright."""
    for scale, expected in ((PHScale.TOTAL, 1608.0), (PHScale.NBS, 1670.0)):
        chemistry = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=scale)
        dic = effluent_endmember(chemistry, 35.0, 10.0).dic
        assert dic == pytest.approx(expected, abs=1.0)
        assert abs(dic - 1646.0) > 20.0


def test_effluent_concentration_scaling_is_off_by_default() -> None:
    chemistry = EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)
    endmember = effluent_endmember(chemistry, 35.0, 10.0)
    assert endmember.concentration_scaling == 1.0
    assert endmember.total_alkalinity == pytest.approx(4000.0)


def test_effluent_concentration_scaling_reproduces_the_exe_endmember() -> None:
    """case04's back-out: TA 4000 -> 4108.4 and DIC 1646 -> 1690.0, both +-0.6 umol/kg."""
    settings = CarbonateSettings(reproduce_effluent_concentration_scaling=True)
    chemistry = EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)
    endmember = effluent_endmember(chemistry, 35.0, 10.0, settings=settings)
    # The back-out itself is only good to ~1.5 umol/kg: a least-squares fit over all 41
    # rows gives TA 4109.15 and DIC 1689.27, a row-by-row inversion 4108.4 and 1690.0.
    assert endmember.total_alkalinity == pytest.approx(4108.8, abs=1.5)
    assert endmember.dic == pytest.approx(1689.6, abs=1.5)
    assert endmember.concentration_scaling == pytest.approx(1.02695, abs=1e-4)


def test_a_derived_dic_escapes_the_scaling() -> None:
    """case03 scaled its entered TA but not the DIC it worked out from TA and pH."""
    settings = CarbonateSettings(reproduce_effluent_concentration_scaling=True)
    chemistry = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE)
    endmember = effluent_endmember(chemistry, 35.0, 10.0, settings=settings)
    assert endmember.total_alkalinity == pytest.approx(4108.4, abs=0.7)
    assert endmember.dic == pytest.approx(1646.0, abs=1.0)


# ------------------------------------------------------------------ against the exe


def _plume_state(case: Path, dat_name: str) -> dict[str, np.ndarray]:
    """Reconstruct a case's mixed salinity and temperature from its printed dilution.

    Read from the CSVs rather than the `.prj`, because case04 has no `.prj` -- the exe
    keeps chemistry in session state, so the user re-ran the same project with new
    chemistry and only the tables and the `.dat` came out.
    """
    nearfield = read_dat(case / dat_name).nearfield
    effluent = read_csv_table(case / "macoma2effluent.csv")
    ambient = read_csv_table(case / "macoma2ambient.csv")
    effluent_row = next(iter(effluent.active_rows())).values
    effluent_salinity = effluent_row[effluent.column_names.index("salinity")]
    effluent_temperature = effluent_row[effluent.column_names.index("temperature")]
    rows = [row.values for row in ambient.active_rows()]
    grid = [row[ambient.column_names.index("depth")] for row in rows]

    depth = -nearfield["Depth"].to_numpy(dtype=float)
    dilution = nearfield["Dilutn"].to_numpy(dtype=float)
    ambient_salinity = np.interp(
        depth, grid, [row[ambient.column_names.index("salinity")] for row in rows]
    )
    ambient_temperature = np.interp(
        depth, grid, [row[ambient.column_names.index("temperature")] for row in rows]
    )
    return {
        "depth": depth,
        "dilution": dilution,
        "salinity": mix(effluent_salinity, ambient_salinity, dilution),
        "temperature": mix(effluent_temperature, ambient_temperature, dilution),
        "alkalinity": nearfield["TA"].to_numpy(dtype=float),
        "dic": nearfield["DIC"].to_numpy(dtype=float),
        "ph": nearfield["pH"].to_numpy(dtype=float),
        "omega_calcite": nearfield["OmegaC"].to_numpy(dtype=float),
        "omega_aragonite": nearfield["OmegaA"].to_numpy(dtype=float),
    }


@pytest.mark.golden
def test_case03_alkalinity_and_dic_mix_conservatively() -> None:
    """Invert every high-dilution row for the ambient endmember and recover the CSV.

    This is the sharpest available check that TA and DIC are transported as conservative
    tracers with a plain per-mass dilution weighting.
    """
    state = _plume_state(CASE03, "test2_TxtOutputs.dat")
    chemistry = read_csv_table(CASE03 / "testco2.csv")
    rows = [row.values for row in chemistry.active_rows()]
    grid = [row[0] for row in rows]
    expected_alkalinity = np.interp(state["depth"], grid, [row[1] for row in rows])
    expected_dic = np.interp(state["depth"], grid, [row[2] for row in rows])

    # The endmember the exe actually used, per the case03 back-out.
    dilution = state["dilution"]
    high = dilution > 25.0
    assert high.sum() >= 15, "expected plenty of high-dilution rows to invert"

    def ambient_from(column: np.ndarray, endmember: float) -> np.ndarray:
        return (dilution * column - endmember) / (dilution - 1.0)

    np.testing.assert_allclose(
        ambient_from(state["alkalinity"], 4108.4)[high], expected_alkalinity[high], atol=0.5
    )
    np.testing.assert_allclose(
        ambient_from(state["dic"], 1645.9)[high], expected_dic[high], atol=0.5
    )


@pytest.mark.golden
@pytest.mark.parametrize(
    ("case", "dat_name", "column"),
    [
        (CASE03, "test2_TxtOutputs.dat", "alkalinity"),
        (CASE03, "test2_TxtOutputs.dat", "dic"),
        (CASE04, "test3_TxtOutputs.dat", "alkalinity"),
        (CASE04, "test3_TxtOutputs.dat", "dic"),
    ],
)
def test_one_endmember_explains_every_row_algebraically(
    case: Path, dat_name: str, column: str
) -> None:
    """No per-step accumulation: a single scalar endmember fits the whole run.

    This is what licenses computing concentrations from the dilution rather than advecting
    them through the near-field integrator -- see transport.py, which supersedes an earlier
    reading of this same data.
    """
    state = _plume_state(case, dat_name)
    chemistry = read_csv_table(case / "testco2.csv")
    rows = [row.values for row in chemistry.active_rows()]
    grid = [row[0] for row in rows]
    csv_column = 1 if column == "alkalinity" else 2
    ambient = np.interp(state["depth"], grid, [row[csv_column] for row in rows])

    observed = state[column]
    dilution = state["dilution"]
    # Least squares for the single endmember E in observed = (E + (D-1)*ambient)/D.
    weight = 1.0 / dilution
    endmember = float(
        np.sum(weight * (observed - (dilution - 1.0) * ambient / dilution))
        / np.sum(weight * weight)
    )
    residual = observed - mix(endmember, ambient, dilution)

    assert np.abs(residual).max() < 1.5, "one endmember should explain every row"
    # And the residual must not be structured in dilution, which is what stepwise
    # accumulation would look like.
    early = residual[dilution < 5.0].mean()
    late = residual[dilution > 50.0].mean()
    assert abs(early - late) < 0.2


@pytest.mark.golden
@pytest.mark.parametrize(
    ("case", "dat_name"),
    [(CASE03, "test2_TxtOutputs.dat"), (CASE04, "test3_TxtOutputs.dat")],
)
def test_our_ph_tracks_the_exe_to_within_the_recorded_offset(case: Path, dat_name: str) -> None:
    """PyCO2SYS sits 0.011-0.024 pH above the exe on the total scale. Pin that gap.

    The test asserts the *size* of the difference, not agreement: PLAN.md §4 records
    differences from the exe rather than tuning to them, and a change in this offset means
    something in the port moved.
    """
    state = _plume_state(case, dat_name)
    solved = solve_from_alkalinity_dic(
        state["alkalinity"],
        state["dic"],
        state["salinity"],
        state["temperature"],
        constants=resolve_constants(EXE_K1K2, EXE_KSO4),
    )
    offset = state["ph"] - solved.ph_total
    assert offset.max() < 0.0, "the exe should read below PyCO2SYS on the total scale"
    assert offset.min() > -0.05
    # Free and NBS are excluded by a wide margin, which is what makes the scale identifiable.
    assert np.abs(state["ph"] - solved.ph_free).min() > 0.05


@pytest.mark.golden
def test_the_exe_borate_behaves_like_lee_not_uppstrom() -> None:
    """The exe's pH gap collapses when total borate is Lee (2010) rather than Uppstrom.

    case03 was run on KSO4 option 1, which the dialog documents as Dickson bisulfate with
    **Uppstrom** borate. But the residual against PyCO2SYS tells a different story:

        option 1 (Uppstrom)  gap -0.0107 .. -0.0236   spread 0.0129   rms 0.0122
        option 3 (Lee 2010)  gap -0.0046 .. -0.0065   spread 0.0018   rms 0.0057

    The spread -- the part that varies along the plume -- drops sevenfold, which is the
    signature of the right salinity dependence rather than a coincidence. Fitting the
    borate freely to zero the *mean* instead lands on 447.8 umol/kg with the spread back up
    at 0.0119, so Lee is the best description of the shape and a near-constant -0.0057
    offset is what remains.

    Either the exe mislabels option 1, or that run was actually on option 3. One control
    run settles it: rerun case03 with KSO4 = 3 and nothing else changed. Identical output
    means the borate half of the selector is ignored.
    """
    pytest.importorskip("PyCO2SYS")
    state = _plume_state(CASE03, "test2_TxtOutputs.dat")
    spreads = {}
    for option in (1, 3):
        solved = solve_from_alkalinity_dic(
            state["alkalinity"],
            state["dic"],
            state["salinity"],
            state["temperature"],
            constants=resolve_constants(EXE_K1K2, option),
        )
        gap = state["ph"] - solved.ph_total
        spreads[option] = float(gap.max() - gap.min())
        assert gap.max() < 0.0, "the exe reads below PyCO2SYS either way"
    assert spreads[1] == pytest.approx(0.0129, abs=0.002)
    assert spreads[3] == pytest.approx(0.0018, abs=0.001)
    # The whole point: Lee's salinity dependence tracks the exe far better.
    assert spreads[3] < spreads[1] / 4.0


@pytest.mark.golden
def test_case03_saturation_ratio_matches_the_exe_to_a_tenth_of_a_percent() -> None:
    """Omega_calcite / Omega_aragonite isolates Ksp: calcium and the pH solver cancel."""
    state = _plume_state(CASE03, "test2_TxtOutputs.dat")
    exe_ratio = state["omega_calcite"] / state["omega_aragonite"]
    ours = solubility_aragonite(state["salinity"], state["temperature"]) / solubility_calcite(
        state["salinity"], state["temperature"]
    )
    np.testing.assert_allclose(ours, exe_ratio, rtol=1.5e-3)
    # Recorded shape of the residual: we read slightly high, systematically.
    assert np.all(ours > exe_ratio)
    assert float(np.max(np.abs(ours - exe_ratio))) < 2.0e-3


@pytest.mark.golden
def test_case03_saturation_states_agree_with_the_exe_to_a_few_percent() -> None:
    """Given the exe's own pH, our Omega runs 0.8-3.4 % high. Pin the envelope."""
    state = _plume_state(CASE03, "test2_TxtOutputs.dat")
    solved = solve_from_alkalinity_dic(
        state["alkalinity"],
        state["dic"],
        state["salinity"],
        state["temperature"],
        constants=resolve_constants(EXE_K1K2, EXE_KSO4),
    )
    for ours, theirs in (
        (solved.omega_calcite, state["omega_calcite"]),
        (solved.omega_aragonite, state["omega_aragonite"]),
    ):
        relative = (ours - theirs) / theirs
        assert relative.min() > 0.0
        assert relative.max() < 0.05


@pytest.mark.golden
def test_case04_effluent_dic_is_the_entered_value_scaled() -> None:
    """The pairing measurement itself: TA + DIC wins, and both get the density factor."""
    state = _plume_state(CASE04, "test3_TxtOutputs.dat")
    chemistry = read_csv_table(CASE04 / "testco2.csv")
    rows = [row.values for row in chemistry.active_rows()]
    grid = [row[0] for row in rows]
    dilution = state["dilution"]
    ambient_dic = np.interp(state["depth"], grid, [row[2] for row in rows])
    endmember = dilution * state["dic"] - (dilution - 1.0) * ambient_dic

    settings = CarbonateSettings(reproduce_effluent_concentration_scaling=True)
    expected = effluent_endmember(
        EffluentChemistry(total_alkalinity=4000.0, dic=1646.0), 35.0, 10.0, settings=settings
    ).dic
    assert float(endmember[0]) == pytest.approx(expected, abs=1.0)
    # Had the exe used the entered pH of 11 instead, the endmember would be far lower.
    from_ph = effluent_endmember(
        EffluentChemistry(total_alkalinity=4000.0, ph=11.0, ph_scale=PHScale.FREE), 35.0, 10.0
    ).dic
    assert abs(from_ph - float(endmember[0])) > 400.0


# ------------------------------------------------------------------------- pH scales


def test_ph_is_available_on_every_scale_the_data_admits() -> None:
    solved = solve_from_alkalinity_dic(2300.0, 2000.0, 33.0, 12.0)
    # Free is above total, which is above seawater, by construction of the scales.
    assert float(solved.ph(PHScale.FREE)) > float(solved.ph(PHScale.TOTAL))
    assert float(solved.ph(PHScale.TOTAL)) > float(solved.ph(PHScale.SEAWATER))


def test_the_nbs_scale_is_refused_with_its_reason() -> None:
    solved = solve_from_alkalinity_dic(2300.0, 2000.0, 33.0, 12.0)
    with pytest.raises(ValueError, match="NBS"):
        solved.ph(PHScale.NBS)


def test_solving_from_ph_round_trips_through_dic() -> None:
    first = solve_from_alkalinity_ph(2300.0, 8.1, 33.0, 12.0, ph_scale=PHScale.TOTAL)
    second = solve_from_alkalinity_dic(2300.0, float(first.dic), 33.0, 12.0)
    assert float(second.ph_total) == pytest.approx(8.1, abs=1e-6)


def test_every_state_records_the_constants_it_used() -> None:
    constants = resolve_constants(4, 2)
    solved = solve_from_alkalinity_dic(2300.0, 2000.0, 33.0, 12.0, constants=constants)
    assert solved.constants is constants
    assert solved.constants.pyco2sys_k_carbonic == 4
    assert "Mehrbach" in solved.constants.k1k2_reference


# ------------------------------------------------------- the out-of-range warning (Phase 8.2)
#
# ⚠️⚠️ `ValidityRange.covers` and `ConstantSet.covers` were written, tested and re-exported the day
# the constants were decoded -- and **nothing called them**, so a plume that left Lueker's S 19-43
# extrapolated in silence for the whole of phases 4 through 7. The tests above this line check that
# the window is known. These check that leaving it is *said out loud*, which is the half that makes
# it a feature.


def test_leaving_the_fitted_window_is_warned_about() -> None:
    """⭐ The claim: an extrapolated carbonate system announces itself.

    45 psu against Lueker's 43. This is not a contrived number -- case07's effluent is 45, and
    an alkalinity dose raises salinity by construction (PLAN.md §8e).
    """
    with pytest.warns(ConstantRangeWarning) as caught:
        solve_from_alkalinity_dic(2300.0, 2000.0, 45.0, 15.0)
    message = str(caught[0].message)
    # Four things the reader needs, and the reason each is there.
    assert "option 10" in message, "which selector to change"
    assert "Lueker" in message, "whose fit it is"
    assert "S 19-43" in message, "what the window is"
    assert "S reached 45" in message, "how far outside this run went"
    assert "extrapolated" in message, "what it means for the number"


def test_staying_inside_the_window_is_silent() -> None:
    """⚠️ The half that stops the warning becoming noise everyone filters out.

    Every archived case except case07 sits inside Lueker, so if this fired on ordinary seawater
    the warning would be worthless the day it shipped.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConstantRangeWarning)
        solve_from_alkalinity_dic(2300.0, 2000.0, 35.0, 15.0)
        solve_from_alkalinity_dic(2300.0, 2000.0, [19.0, 31.0, 43.0], [2.0, 15.0, 35.0])


def test_temperature_leaves_the_window_too() -> None:
    """Salinity is the axis a dose moves, but the window has two."""
    with pytest.warns(ConstantRangeWarning, match=r"T reached 40"):
        solve_from_alkalinity_dic(2300.0, 2000.0, 35.0, 40.0)


def test_a_two_hundred_row_plume_warns_once_and_not_two_hundred_times() -> None:
    """⚠️ Once per array, not once per row.

    The chemistry is solved vectorised, and a plume that leaves the window leaves it on almost
    every row. A per-row warning would bury the one fact that matters under two hundred copies
    of itself -- and the point of the exercise is that the reader notices.
    """
    salinity = np.linspace(30.0, 48.0, 200)
    with pytest.warns(ConstantRangeWarning) as caught:
        solve_from_alkalinity_dic(
            np.full(200, 2300.0), np.full(200, 2000.0), salinity, np.full(200, 15.0)
        )
    assert len(caught) == 1, [str(w.message) for w in caught]
    # The share is what separates "one sample grazed the edge" from "this plume is extrapolated".
    assert "of 200 samples" in str(caught[0].message)


def test_the_message_says_which_end_of_the_mixing_line_it_is() -> None:
    """The effluent and the plume are labelled apart, because the fixes differ.

    An out-of-range *effluent* is the user's own input and they can change it or the selector;
    an out-of-range *plume* is a consequence of mixing and they cannot.
    """
    chemistry = EffluentChemistry(total_alkalinity=4000.0, ph=10.5, ph_scale=PHScale.FREE)
    with pytest.warns(ConstantRangeWarning, match="effluent endmember"):
        effluent_endmember(chemistry, 45.0, 10.0)

    # DIC given rather than derived from pH, so building the endmember costs no solve of its
    # own and this half of the test isolates the plume label.
    inside = EffluentChemistry(total_alkalinity=4000.0, dic=1646.0)
    endmember = effluent_endmember(inside, 35.0, 10.0)
    with pytest.warns(ConstantRangeWarning, match="plume trajectory"):
        plume_carbonate(endmember, 2300.0, 2000.0, [1.0, 2.0], [46.0, 40.0], [10.0, 10.0])


def test_a_wider_option_does_not_fire_where_lueker_does() -> None:
    """⭐ The warning tracks the *selected* option, not one fixed window.

    Option 13 (Millero et al. 2006) was fitted to S 1-50, so 45 psu is inside it. This is also
    the actionable half of the message: the fix for an out-of-range plume may be to pick a
    constant set that covers it.
    """
    wide = resolve_constants(13, 1)
    assert wide.validity.describe() == "T 0-50 C, S 1-50"
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConstantRangeWarning)
        solve_from_alkalinity_dic(2300.0, 2000.0, 45.0, 15.0, constants=wide)


def test_the_emitter_reports_how_many_samples_were_outside() -> None:
    """Returned rather than only warned, so a caller can act on it without re-deriving it."""
    constants = resolve_constants(10, 1)
    salinity = [31.0, 35.0, 44.0, 45.0]
    with pytest.warns(ConstantRangeWarning):
        outside = warn_outside_validity(constants, salinity, 10.0, context="probe")
    assert outside == 2

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConstantRangeWarning)
        assert warn_outside_validity(constants, [31.0, 35.0], 10.0, context="probe") == 0


# ⚠️ The S/T window above is where the constants were *fitted*. The first dose dry run
# (2026-08-25) solved pH-12 seawater inside it and nothing spoke, because Lueker's window is S and
# T only. These pin the second check at the chokepoint: the pH range in which the port's chemistry
# has been *compared* to anything (case03/case04, rows 41/43/128 -- ambient 8.37 to port 10.44).


def test_a_ph_above_the_parity_ceiling_is_warned_about() -> None:
    """⭐ TA 40 000 at DIC 2500 is pH 12.4 -- past anything the exe has ever been run at."""
    with pytest.warns(PHRangeWarning) as caught:
        state = solve_from_alkalinity_dic(40000.0, 2500.0, 35.0, 10.0)
    assert float(state.ph_total[()]) > 12.0
    message = str(caught[0].message)
    assert "pH 7.5-12" in message, "what the window is"
    assert "pH reached 12" in message, "how far outside this solve went"
    assert "dose_parity" in message, "what the window rests on"
    assert "never been compared" in message, "what it means for the number"


def test_the_ph_warning_is_a_constant_range_warning_but_its_own_category() -> None:
    """A filter on the parent still catches it; a sweep row can still tell the two windows apart."""
    assert issubclass(PHRangeWarning, ConstantRangeWarning)
    with pytest.warns(ConstantRangeWarning) as caught:
        solve_from_alkalinity_dic(40000.0, 2500.0, 35.0, 10.0)
    assert {w.category for w in caught} == {PHRangeWarning}, "S 35 / T 10 is inside Lueker"


#: The exe's own first printed row from each `dose_parity` run of 2026-08-25, converted from the
#: printed columns, exactly as printed: `(TA, DIC, salinity, temperature, the exe's own pH)`.
#:
#: ⚠️⚠️ **No density conversion, and the first draft of this tuple applied one.** The column is
#: headed `(mmol/m3)`, which would need dividing by 1.02695 to reach umol/kg -- but the traces
#: settle it directly: by a dilution of 562.6 they converge to TA **2900.208** and DIC
#: **2500.120**, the *entered* ambient values in umol/kg to four figures. The label is wrong and
#: the numbers are umol/kg (PLAN 7.5). Dividing by rho moved every gap below to 0.008 and would
#: have quietly re-pinned rows 41/43 at the wrong value.
_DOSE_PARITY_FIRST_ROWS = (
    (4084.213, 2566.114, 34.924, 10.013, 9.148),
    (6097.889, 2566.114, 34.924, 10.013, 10.628),
    (10125.239, 2566.114, 34.924, 10.013, 11.483),
    (20193.616, 2566.114, 34.924, 10.013, 11.988),
)


def test_the_dose_axis_the_exe_has_actually_run_is_inside_the_window() -> None:
    """⭐⭐ The ceiling is evidence, and this is the evidence: the four `dose_parity` runs.

    On 2026-08-25 the exe was run at case03's geometry with DIC 2500 entered and TA at 4000,
    6000, 10 000 and 20 000, and its own CO2SYS printed a port pH of 9.148, 10.628, 11.483 and
    11.988 -- staying 0.011-0.025 below PyCO2SYS over all 2050 rows. That is what moved the
    ceiling from 10.5 to 12.0, so no row the exe actually printed may warn. If this starts
    failing, the window was narrowed without the runs being retracted.

    ⚠️ The traces themselves are deliberately *not* read here: they live in
    `reference_cases/pending/`, and a test that depends on a file still being run is a test that
    breaks when the next run overwrites it. The inputs above are transcribed from them instead.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", PHRangeWarning)
        for ta, dic, salinity, temperature, exe_ph in _DOSE_PARITY_FIRST_ROWS:
            state = solve_from_alkalinity_dic(ta, dic, salinity, temperature)
            ours = float(state.ph_total[()])
            assert ours <= 12.05, (ta, ours)
            # And the gap the window is a statement about: the exe reads low, by 0.013-0.025.
            assert 0.012 <= ours - exe_ph <= 0.026, (ta, ours - exe_ph)


def test_the_ceiling_sits_just_above_the_highest_point_actually_compared() -> None:
    """⚠️ The 0.05 of headroom in the ceiling, pinned so it cannot quietly become a habit.

    The window is tested against *our* pH, and on the exe's own top-dose row PyCO2SYS returns
    12.008 where the exe printed 11.988. A ceiling at 12.0 -- the round number, and what this was
    for an hour on 2026-08-25 -- would have fired on the run that is the evidence for it. So the
    ceiling is 12.05: above the highest compared point, and close enough that a genuine
    extrapolation still trips. Both halves are asserted, because only the pair says the number is
    a boundary rather than a preference.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", PHRangeWarning)
        highest_compared = solve_from_alkalinity_dic(20193.616, 2566.114, 34.924, 10.013)
    assert 12.0 < float(highest_compared.ph_total[()]) < 12.05, "the evidence must not warn"

    with pytest.warns(PHRangeWarning):
        beyond = solve_from_alkalinity_dic(24000.0, 2566.114, 34.924, 10.013)
    assert float(beyond.ph_total[()]) > 12.05


def test_the_ph_emitter_counts_and_warns_once_per_array() -> None:
    ph = np.linspace(8.0, 13.0, 51)
    with pytest.warns(PHRangeWarning) as caught:
        outside = warn_outside_ph_window(ph, context="probe")
    assert len(caught) == 1
    assert outside == int(np.count_nonzero(ph > 12.0))
    assert "of 51 samples" in str(caught[0].message)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PHRangeWarning)
        assert warn_outside_ph_window([8.0, 12.0], context="probe") == 0
        assert warn_outside_ph_window([np.nan], context="probe") == 0, "NaN is not an excursion"
