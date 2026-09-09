"""Dissolved oxygen, against every archived DO trace -- twenty-seven of them.

Both halves are measured. The near field is case24's five runs plus case28's twelve; the far field
is case25, case26, case27 and case28's, which between them settle every unknown in eqs 24-30. Three
of the exe's placements turn out to be wrong, all in the same direction -- a demand that dilution
should remove is instead delivered by it -- so the tests that reproduce the exe pass
`reproduce_undiluted_bod` and `reproduce_idod_on_ambient`; the defaults are the manual's.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from plumes2.biochem.do_bod import (
    BOD5_DAYS,
    far_field_oxygen,
    near_field_oxygen,
    near_field_oxygen_for,
    rate_at_temperature,
    ultimate_bod,
)
from plumes2.config import (
    AmbientChemistryLevel,
    AmbientDOLevel,
    EffluentChemistry,
    EffluentDO,
)
from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.results import CHEMISTRY_COLUMNS, OXYGEN_COLUMNS, run
from tests.conftest import REFERENCE_CASES

CASE24 = REFERENCE_CASES / "case24_dissolved_oxygen"

#: The effluent DO tab for test37-test40, user-supplied -- the `.prj` cannot carry it (§7b), so
#: without this the traces are uninterpretable. See the case README.
CASE24_EFFLUENT = EffluentDO(
    dissolved_oxygen=2.0,
    idod=0.0,
    cbod5=20.0,
    nbod5=30.0,
    cbod_decay=0.23,
    nbod_decay=0.23,
)

#: `testDO.csv`: depth, DO, cBOD5, nBOD5.
CASE24_AMBIENT = ((1.0, 8.0), (3.0, 9.0), (6.0, 10.0), (10.0, 9.0), (12.0, 8.0))

#: What three printed decimals on the exe's `DO` column can resolve.
PRINTED = 5e-4


def _ambient_at(depth: np.ndarray) -> np.ndarray:
    depths = np.array([d for d, _v in CASE24_AMBIENT])
    values = np.array([v for _d, v in CASE24_AMBIENT])
    return np.interp(depth, depths, values)


def _trace(name: str):  # type: ignore[no-untyped-def]
    frame = read_dat(CASE24 / f"{name}.dat").nearfield
    return (
        frame["Dilutn"].to_numpy(dtype=float),
        -frame["Depth"].to_numpy(dtype=float),
        frame["DO"].to_numpy(dtype=float),
    )


# ------------------------------------------------------------------ the measured near field


@pytest.mark.golden
@pytest.mark.parametrize("name", ["test37", "test38", "test39", "test40"])
def test_the_path_integral_reproduces_every_archived_do_column(name: str) -> None:
    """Two geometries, one merging and one not, plus a run with chemistry alongside."""
    dilution, depth, theirs = _trace(name)
    ours = near_field_oxygen(CASE24_EFFLUENT, _ambient_at(depth), dilution)

    worst = float(np.max(np.abs(ours - theirs)))
    # 13x printed precision, and it is the *reconstruction* that limits this rather than the model:
    # the integral is rebuilt from three-decimal dilutions at the exe's own output steps.
    assert worst < 0.007, f"{name}: worst {worst:.5f} mg/L"
    # Past the first few rows, where the reconstruction is coarsest, it halves.
    developed = dilution > 5.0
    assert float(np.max(np.abs((ours - theirs)[developed]))) < 0.005


@pytest.mark.golden
@pytest.mark.parametrize("name", ["test37", "test39"])
def test_the_algebraic_reading_of_eq_23_is_decisively_worse(name: str) -> None:
    """The measurement that overturned the literal equation, kept so it cannot be re-adopted.

    Eq 23 with `DO_a` at the row's own depth is what the manual appears to say. It is off by two
    orders of magnitude more than the path integral, which is why the path integral is what ships.
    """
    dilution, depth, theirs = _trace(name)
    ambient = _ambient_at(depth)
    algebraic = ambient * (1.0 - 1.0 / dilution) + 2.0 / dilution
    path = near_field_oxygen(CASE24_EFFLUENT, ambient, dilution)

    algebraic_error = float(np.max(np.abs(algebraic - theirs)))
    path_error = float(np.max(np.abs(path - theirs)))
    assert algebraic_error > 0.15, f"{name}: algebraic {algebraic_error:.4f}"
    assert path_error < 0.007
    assert algebraic_error > 20.0 * path_error


@pytest.mark.golden
def test_both_bod_channels_are_inert_in_the_near_field() -> None:
    """test39 (cBOD5 0, nBOD5 30) and test40 (cBOD5 20, nBOD5 0) are byte-identical."""
    assert (CASE24 / "test39.dat").read_bytes() == (CASE24 / "test40.dat").read_bytes()
    # And our own answer does not move when the BOD inputs do.
    dilution, depth, _ = _trace("test39")
    ambient = _ambient_at(depth)
    swapped = CASE24_EFFLUENT.model_copy(update={"cbod5": 0.0, "nbod5": 30.0})
    assert np.array_equal(
        near_field_oxygen(CASE24_EFFLUENT, ambient, dilution),
        near_field_oxygen(swapped, ambient, dilution),
    )


@pytest.mark.golden
def test_do_does_not_perturb_the_hydrodynamics() -> None:
    """test36 (no DO), test37 (+DO) and test38 (+DO +chemistry) share every other column."""
    baseline = read_dat(CASE24 / "test36.dat").nearfield
    for name in ("test37", "test38"):
        other = read_dat(CASE24 / f"{name}.dat").nearfield
        shared = [column for column in baseline.columns if column in other.columns]
        assert len(shared) == 13
        for column in shared:
            assert np.array_equal(
                baseline[column].to_numpy(), other[column].to_numpy(), equal_nan=True
            ), f"{name}: {column}"


@pytest.mark.golden
def test_the_manuals_do_ph_exclusion_is_not_enforced_by_the_exe() -> None:
    """§5.2.6 says the two cannot run together; test38 runs both and matches test37's DO exactly."""
    both = read_dat(CASE24 / "test38.dat").nearfield
    assert {"TA", "DIC", "pH", "OmegaA", "DO"} <= set(both.columns)
    assert np.array_equal(
        both["DO"].to_numpy(), read_dat(CASE24 / "test37.dat").nearfield["DO"].to_numpy()
    )


def test_the_seed_is_the_effluent_less_the_immediate_demand() -> None:
    """The manual's form, which is our default: IDOD is an effluent property, so it enters the seed.

    ⚠️ Do not read this as "only the difference is observable" -- that was true of the archive until
    case28's runs 11 and 12 separated them, and the exe's own placement (which this test does not
    use) makes them behave in opposite ways. See `test_the_effluent_seed_and_the_immediate_demand_
    are_separable`.
    """
    ambient = np.array([8.0, 8.0])
    dilution = np.array([1.0, 1.0])
    plain = EffluentDO(dissolved_oxygen=2.0, idod=0.0)
    split = EffluentDO(dissolved_oxygen=5.0, idod=3.0)
    assert near_field_oxygen(plain, ambient, dilution)[0] == pytest.approx(2.0)
    assert np.allclose(
        near_field_oxygen(plain, ambient, dilution),
        near_field_oxygen(split, ambient, dilution),
    )


def test_a_uniform_ambient_recovers_the_manuals_algebraic_equation() -> None:
    """The reconciliation, as an assertion: where the ambient is flat, eq 23 is exactly right.

    This is why the carbonate module's algebraic mixing (ledger row 39) and this module's path
    integral are one rule rather than two -- case24's ambient TA is flat over the traversed depths.
    """
    effluent = EffluentDO(dissolved_oxygen=2.0, idod=0.0)
    dilution = np.linspace(1.0, 200.0, 400)
    ambient = np.full_like(dilution, 8.0)
    eq23 = 8.0 + (2.0 - 0.0 - 8.0) / dilution
    assert near_field_oxygen(effluent, ambient, dilution) == pytest.approx(eq23, abs=1e-12)


def test_a_mismatched_or_impossible_input_is_refused() -> None:
    effluent = EffluentDO(dissolved_oxygen=2.0)
    with pytest.raises(ValueError, match="sampled together"):
        near_field_oxygen(effluent, np.array([8.0]), np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="at least 1"):
        near_field_oxygen(effluent, np.array([8.0, 8.0]), np.array([1.0, 0.5]))


# ------------------------------------------------------------------ through a run


@pytest.fixture(scope="module")
def oxygen_case():  # type: ignore[no-untyped-def]
    """The archived-diffuser baseline with both DO endmembers, built once for the module.

    A cheap single-port variant, because these tests are about the oxygen column rather than the
    hydrodynamics -- and an integration costs the same whatever `samples` asks for.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base = load_project(
            REFERENCE_CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
        ).to_case()
    cheap = base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": base.effluent.model_copy(update={"flow": 5.0e-5}),
        }
    )
    levels = [
        AmbientDOLevel(depth=depth, dissolved_oxygen=value, cbod5=5.0, nbod5=6.0)
        for depth, value in CASE24_AMBIENT
    ]
    return cheap, cheap.model_copy(
        update={
            "ambient": cheap.ambient.model_copy(update={"dissolved_oxygen": levels}),
            "effluent_do": CASE24_EFFLUENT,
        }
    )


@pytest.fixture(scope="module")
def oxygen_runs(oxygen_case):  # type: ignore[no-untyped-def]
    """Three integrations shared by every test below: bare, coarse and fine."""
    bare, dosed = oxygen_case
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(bare, samples=12), run(dosed, samples=25), run(dosed, samples=400)


@pytest.mark.slow
def test_a_run_grows_a_do_column_only_when_both_endmembers_are_present(oxygen_runs) -> None:  # type: ignore[no-untyped-def]
    bare, result, _fine = oxygen_runs
    assert not bare.has_oxygen, "no DO endmember, no column"

    assert result.has_oxygen
    assert next(iter(OXYGEN_COLUMNS)) in result.nearfield.columns
    oxygen = result.nearfield["dissolved_oxygen_mg_l"].to_numpy(dtype=float)
    # Starts at the discharge value less the demand, and relaxes toward the receiving water.
    assert oxygen[0] == pytest.approx(2.0, abs=1e-6)
    assert 7.5 < oxygen[-1] < 10.0
    assert np.all(oxygen >= 2.0 - 1e-9) and np.all(oxygen <= 10.0 + 1e-9)


@pytest.mark.slow
def test_the_do_column_does_not_depend_on_how_many_rows_were_asked_for(oxygen_runs) -> None:  # type: ignore[no-untyped-def]
    """A path integral evaluated on the output grid would make a 25-row run disagree with a 400."""
    _bare, coarse, fine = oxygen_runs

    # Compare at the coarse run's own times, which the fine grid also covers.
    sampled = np.interp(
        coarse.nearfield["time_s"].to_numpy(dtype=float),
        fine.nearfield["time_s"].to_numpy(dtype=float),
        fine.nearfield["dissolved_oxygen_mg_l"].to_numpy(dtype=float),
    )
    worst = float(np.max(np.abs(coarse.nearfield["dissolved_oxygen_mg_l"].to_numpy() - sampled)))
    assert worst < 0.01, f"a 16x change in output resolution moved DO by {worst:.4f} mg/L"


def test_the_case_refuses_to_compute_oxygen_without_an_endmember() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base = load_project(
            REFERENCE_CASES / "case01_cms" / "project.prj", warn_on_drift=False
        ).to_case()
    assert not base.oxygen_enabled
    with pytest.raises(ValueError, match="no effluent DO endmember"):
        near_field_oxygen_for(base, np.array([1.0]), np.array([2.0]))


# ------------------------------------------------------------------ the unvalidated far field


def test_the_ultimate_bod_conversion_matches_its_own_definition() -> None:
    """`BOD5 = BOD_L (1 - exp(-k*5))` is the definition; this inverts it, so invert it back."""
    for bod5, rate in ((20.0, 0.23), (30.0, 0.1), (5.0, 0.46)):
        ultimate = ultimate_bod(bod5, rate)
        assert ultimate * (1.0 - math.exp(-rate * BOD5_DAYS)) == pytest.approx(bod5)
    # A slower rate means a *larger* ultimate demand for the same 5-day measurement.
    assert ultimate_bod(10.0, 0.1) > ultimate_bod(10.0, 0.23)
    assert ultimate_bod(10.0, 0.23) == pytest.approx(14.6335, abs=5e-4)
    assert ultimate_bod(10.0, 0.1) == pytest.approx(25.4149, abs=5e-4)


def test_a_zero_decay_rate_is_refused_rather_than_dividing_by_zero() -> None:
    with pytest.raises(ValueError, match="positive"):
        ultimate_bod(10.0, 0.0)


def test_the_temperature_correction_is_the_identity_at_twenty_degrees() -> None:
    assert rate_at_temperature(0.23, 1.047, 20.0) == pytest.approx(0.23)
    assert rate_at_temperature(0.23, 1.047, 30.0) == pytest.approx(0.36408, abs=5e-6)
    assert rate_at_temperature(0.1, 1.08, 30.0) == pytest.approx(0.21589, abs=5e-6)


def test_the_far_field_sag_starts_at_the_near_field_value_and_falls() -> None:
    """The two halves join at the value the near field produced, and a demand can only subtract."""
    effluent = EffluentDO(dissolved_oxygen=2.0, cbod5=20.0, nbod5=30.0)
    factor = np.array([1.0, 2.0, 5.0, 10.0])
    days = np.array([0.0, 0.5, 2.0, 5.0])
    oxygen = far_field_oxygen(effluent, 8.0, 5.0, 6.0, 7.5, 100.0, factor, days)

    # At the transition FF = 1 and t = 0, so the sag terms vanish and it must equal DO_f exactly.
    assert oxygen[0] == pytest.approx(7.5)
    # A demand can only depress oxygen relative to the no-demand mixing line.
    mixing = 8.0 + (7.5 - 8.0) / factor
    assert np.all(oxygen <= mixing + 1e-12)


def test_a_far_field_with_no_demand_is_the_plain_mixing_line() -> None:
    """With both BOD channels zero, eq 30 collapses to `DO_a + (DO_f - DO_a)/FF`."""
    effluent = EffluentDO(dissolved_oxygen=2.0, cbod5=0.0, nbod5=0.0)
    factor = np.array([1.0, 3.0, 12.0])
    oxygen = far_field_oxygen(
        effluent, 8.0, 0.0, 0.0, 6.0, 100.0, factor, np.array([0.0, 1.0, 4.0])
    )
    assert oxygen == pytest.approx(8.0 + (6.0 - 8.0) / factor)


def test_a_factor_below_one_is_refused() -> None:
    """Brooks' factor is 1 at the transition; below it would mean the far field un-mixed."""
    with pytest.raises(ValueError, match="1 at the transition"):
        far_field_oxygen(
            EffluentDO(dissolved_oxygen=2.0),
            8.0,
            0.0,
            0.0,
            6.0,
            100.0,
            np.array([0.5]),
            np.array([0.0]),
        )


# --------------------------------------------------------------- the far field, against the traces

CASE25 = REFERENCE_CASES / "case25_farfield_bod"
CASE26 = REFERENCE_CASES / "case26_farfield_bod_rates"
CASE27 = REFERENCE_CASES / "case27_farfield_bod_conversion"

#: The DO tab for every far-field trace, user-supplied -- see each case README. ⚠️ The nitrogenous
#: rate is 0.23 in case25/26 and 0.1 in case27, and the fit separates the two at 13x printed
#: precision, so these are not interchangeable.
_OLD = {"cbod5": 20.0, "nbod5": 30.0, "nbod_decay": 0.23}
_NEW = {"cbod5": 20.0, "nbod5": 30.0, "nbod_decay": 0.1}

#: `AmbientDO_one.csv` -- the only stratified ambient any far-field run has used.
CASE27_DEPTHS = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0])
CASE27_OXYGEN = np.array([7.0, 8.0, 9.0, 9.5, 10.0, 10.0, 10.5])

#: (path, effluent, ambient cBOD5, tolerance mg/L). Tolerances are what three printed decimals can
#: resolve once the sag is rebuilt from them -- never what the code happens to produce.
FAR_FIELD_TRACES = [
    (CASE25 / "ModelResults_2.dat", EffluentDO(**_OLD, cbod_decay=0.23), 0.0, 0.02),
    (CASE25 / "ModelResults_3.dat", EffluentDO(**_OLD, cbod_decay=0.23), 500.0, 0.11),
    (CASE26 / "ModelResults_1.dat", EffluentDO(**_OLD, cbod_decay=5.0), 0.0, 0.08),
    (CASE26 / "ModelResults_2.dat", EffluentDO(**_OLD, cbod_decay=1.0), 0.0, 0.03),
    (CASE27 / "ModelResults_2.dat", EffluentDO(**_NEW, cbod_decay=0.23), 0.0, 0.01),
    (CASE27 / "ModelResults_4.dat", EffluentDO(**_NEW, cbod_decay=0.23), 0.0, 0.02),
    (CASE27 / "ModelResults_6.dat", EffluentDO(**_NEW, cbod_decay=0.23), 0.0, 0.03),
    (
        CASE27 / "ModelResults_7.dat",
        EffluentDO(nbod5=30.0, nbod_decay=0.1, cbod5=1000.0, cbod_decay=5.0),
        0.0,
        3.4,
    ),
]


def _far_field_inputs(path):
    """`(effluent-side scalars, FF, days)` from a trace, on the exe's own dilution and time."""
    dat = read_dat(path)
    near, far = dat.nearfield, dat.farfield
    assert far is not None, f"{path.name} printed no far field"
    dilution = float(near["Dilutn"].iloc[-1])
    return (
        dilution,
        float(near["DO"].iloc[-1]),
        far["Dilution"].to_numpy(dtype=float) / dilution,
        far["Time"].to_numpy(dtype=float) / 24.0,
        far["DO"].to_numpy(dtype=float),
    )


@pytest.mark.parametrize(
    ("path", "effluent", "ambient_cbod5", "tolerance"),
    [
        pytest.param(*case, id=f"{case[0].parent.name[:6]}-{case[0].stem[-1]}")
        for case in FAR_FIELD_TRACES
    ],
)
def test_the_exe_far_field_is_reproduced_with_no_dilution_of_the_demand(
    path, effluent: EffluentDO, ambient_cbod5: float, tolerance: float
) -> None:
    """⭐⭐ Every archived far-field DO column, against eqs 24-30 with eq 28's `/D` removed.

    The ambient DO is uniform at 8.0 in all three cases, so `DO_a` is a scalar here.
    """
    dilution, transition, factor, days, printed = _far_field_inputs(path)
    ours = far_field_oxygen(
        effluent,
        8.0,
        ambient_cbod5,
        0.0,
        transition,
        dilution,
        factor,
        days,
        reproduce_undiluted_bod=True,
    )
    assert np.max(np.abs(ours - printed)) < tolerance


def test_the_missing_dilution_is_what_reproduces_the_traces() -> None:
    """⭐⭐ The measurement itself: three geometries, one set of inputs, one far-field curve.

    `D_near` spans 45 % across case27's runs 2, 4 and 6 while every DO input is held fixed. The
    exe's DO agrees across them to 0.02 mg/L, which is only possible if the demand never met the
    near-field dilution. Eq 28 as written separates the same three by 31 %, so this is not a
    tolerance question -- the two forms are qualitatively different and the traces pick one.
    """
    effluent = EffluentDO(**_NEW, cbod_decay=0.23)
    spread_exe, spread_manual, dilutions = [], [], []
    for name in ("ModelResults_2.dat", "ModelResults_4.dat", "ModelResults_6.dat"):
        dilution, transition, factor, days, printed = _far_field_inputs(CASE27 / name)
        dilutions.append(dilution)
        for reproduce, into in ((True, spread_exe), (False, spread_manual)):
            ours = far_field_oxygen(
                effluent,
                8.0,
                0.0,
                0.0,
                transition,
                dilution,
                factor,
                days,
                reproduce_undiluted_bod=reproduce,
            )
            into.append(float(np.max(np.abs(ours - printed))))

    assert max(dilutions) / min(dilutions) > 1.45, "the geometries must actually differ"
    assert max(spread_exe) < 0.03, "the undiluted form tracks all three"
    assert min(spread_manual) > 0.5, "eq 28 as written cannot fit any of them"


def test_the_defect_drives_the_exe_to_negative_oxygen() -> None:
    """⚠️⚠️ case27 run 7: cBOD5 1000 diluted 170:1 still reads -185 mg/L, and we reproduce it.

    Kept as its own test because it is the finding to report, not a tolerance: no warning, no clamp,
    a monotone fall through zero, and a value no water body can hold.
    """
    effluent = EffluentDO(cbod5=1000.0, cbod_decay=5.0, nbod5=30.0, nbod_decay=0.1)
    dilution, transition, factor, days, printed = _far_field_inputs(CASE27 / "ModelResults_7.dat")
    ours = far_field_oxygen(
        effluent,
        8.0,
        0.0,
        0.0,
        transition,
        dilution,
        factor,
        days,
        reproduce_undiluted_bod=True,
    )
    assert printed.min() < -180.0, "the archived trace really does print negative oxygen"
    assert np.max(np.abs(ours - printed)) / (printed.max() - printed.min()) < 0.02

    # And the corrected form stays physical on the very same inputs, which is the point of the flag.
    corrected = far_field_oxygen(
        effluent,
        8.0,
        0.0,
        0.0,
        transition,
        dilution,
        factor,
        days,
    )
    assert corrected.min() > 0.0


def test_the_ambient_demand_is_converted_to_ultimate_before_it_is_subtracted() -> None:
    """case25's ambient run picks eqs 24-25 on the ambient over its raw 5-day figure, by 26x.

    The ambient CSV carries a 5-day value and no rate of its own, so the effluent's carbonaceous
    rate is what converts it -- which only a run with a slow rate can see, since the conversion
    factor is 1.000 at 5 /day.
    """
    dilution, transition, factor, days, printed = _far_field_inputs(CASE25 / "ModelResults_3.dat")
    effluent = EffluentDO(**_OLD, cbod_decay=0.23)
    converted = far_field_oxygen(
        effluent,
        8.0,
        500.0,
        0.0,
        transition,
        dilution,
        factor,
        days,
        reproduce_undiluted_bod=True,
    )
    assert np.max(np.abs(converted - printed)) < 0.11

    # The alternative: subtract the 5-day figure as typed. `ultimate_bod` at this rate is 1.4634x,
    # so passing the pre-divided value reproduces "no conversion" exactly.
    raw = far_field_oxygen(
        effluent,
        8.0,
        500.0 * (1.0 - math.exp(-0.23 * BOD5_DAYS)),
        0.0,
        transition,
        dilution,
        factor,
        days,
        reproduce_undiluted_bod=True,
    )
    assert np.max(np.abs(raw - printed)) > 2.5


def test_the_exe_subtracts_idod_from_the_ambient_not_the_effluent() -> None:
    """⭐⭐ case27 run 9: an IDOD of 3 mg/L *grows* along the trajectory instead of diluting away.

    Eq 23 makes IDOD an effluent property, so at `D` = 246.6 three mg/L of it should be worth
    0.012. Against run 6, which differs in nothing else, it is worth 2.989 -- and the exe's
    placement reproduces the column to the printed resolution once the first rows are past.
    """
    nearfield = read_dat(CASE27 / "ModelResults_9.dat").nearfield
    dilution = nearfield["Dilutn"].to_numpy(dtype=float)
    printed = nearfield["DO"].to_numpy(dtype=float)
    ambient = np.full_like(dilution, 8.0)
    effluent = EffluentDO(dissolved_oxygen=2.0, idod=3.0, **_NEW, cbod_decay=0.23)

    exe = near_field_oxygen(effluent, ambient, dilution, reproduce_idod_on_ambient=True)
    developed = dilution > 5.0
    assert np.max(np.abs((exe - printed)[developed])) < 0.0015
    # The first rows carry the one-step accumulator lag row 220 documents, and no more than that.
    assert np.max(np.abs(exe - printed)) < 0.07

    manual = near_field_oxygen(effluent, ambient, dilution)
    assert np.max(np.abs(manual - printed)) > 2.9

    # The control: at IDOD = 0 -- every other archived trace -- the two forms are the same, which
    # is why this went unseen through three phases of DO validation.
    without = EffluentDO(dissolved_oxygen=2.0, idod=0.0, **_NEW, cbod_decay=0.23)
    assert np.array_equal(
        near_field_oxygen(without, ambient, dilution),
        near_field_oxygen(without, ambient, dilution, reproduce_idod_on_ambient=True),
    )


def test_the_path_integral_holds_on_a_monotonic_ambient_profile() -> None:
    """case27 run 8: the first far-field geometry run against a stratified ambient, 7.0 to 10.5."""
    nearfield = read_dat(CASE27 / "ModelResults_8.dat").nearfield
    dilution = nearfield["Dilutn"].to_numpy(dtype=float)
    depth = -nearfield["Depth"].to_numpy(dtype=float)
    printed = nearfield["DO"].to_numpy(dtype=float)
    effluent = EffluentDO(dissolved_oxygen=2.0, **_NEW, cbod_decay=0.23)

    ours = near_field_oxygen(effluent, np.interp(depth, CASE27_DEPTHS, CASE27_OXYGEN), dilution)
    assert np.max(np.abs(ours - printed)) < 0.06


def test_the_far_field_ambient_is_taken_at_the_trapping_depth() -> None:
    """⭐ case27 run 8 again: eq 30's `DO_a` against four readings of a stratified profile.

    ⚠️ This separates the plausible from the refuted, not the trapping depth from the depth-mean --
    on this profile those two are 0.025 apart and the data cannot tell them apart. The case README
    records what would.
    """
    dilution, transition, factor, days, printed = _far_field_inputs(CASE27 / "ModelResults_8.dat")
    effluent = EffluentDO(dissolved_oxygen=2.0, **_NEW, cbod_decay=0.23)
    trapping = float(np.interp(4.472, CASE27_DEPTHS, CASE27_OXYGEN))

    def residual(ambient_oxygen: float, **kwargs: bool) -> float:
        ours = far_field_oxygen(
            effluent,
            ambient_oxygen,
            0.0,
            0.0,
            transition,
            dilution,
            factor,
            days,
            reproduce_undiluted_bod=kwargs.get("undiluted", True),
        )
        return float(np.max(np.abs(ours - printed)))

    assert residual(trapping) < 0.03
    for refuted in (7.0, 10.5, 8.0):
        assert residual(refuted) > 0.5, refuted

    # And the demand still carries no near-field dilution, which is what a stratified ambient was
    # run to check: the missing `/D` is absent, not misplaced onto `DO_a`.
    assert residual(trapping, undiluted=False) > 0.7


def test_a_fast_rate_identifies_itself_from_the_curve() -> None:
    """⚠️⚠️ case27 run 10: cBOD5 20 mg/L at 20 /day, and the exe prints -1.863 mg/L.

    Every earlier far-field run sits where `1 - e^{-kt}` is near-linear, so the rate was believed
    rather than measured. At 20 /day it saturates inside the far field, and the shape picks the
    typed rate out of its neighbours by an order of magnitude.
    """
    dilution, transition, factor, days, printed = _far_field_inputs(CASE27 / "ModelResults_10.dat")
    assert printed.min() < -1.8, "an ordinary 20 mg/L cBOD5 really does go negative here"

    def residual(rate: float) -> float:
        effluent = EffluentDO(dissolved_oxygen=2.0, **_NEW, cbod_decay=rate)
        ours = far_field_oxygen(
            effluent,
            8.0,
            0.0,
            0.0,
            transition,
            dilution,
            factor,
            days,
            reproduce_undiluted_bod=True,
        )
        return float(np.max(np.abs(ours - printed)))

    assert residual(20.0) < 0.6
    assert residual(5.0) > 6.0
    assert residual(1.0) > 8.0


CASE28 = REFERENCE_CASES / "case28_farfield_do_closeout"

#: The two mirror profiles, built to share a depth-mean while differing at the trapping depth.
FALLING = np.array([12.0, 10.0, 8.5, 7.5, 6.0, 4.0, 2.0])
RISING = FALLING[::-1].copy()
TRAPPING_DEPTH = 4.472


def test_the_two_mirror_profiles_share_a_depth_mean() -> None:
    """The premise of the discriminator, asserted so it cannot silently stop being true."""
    mean_falling = float(np.trapezoid(FALLING, CASE27_DEPTHS) / 12.0)
    mean_rising = float(np.trapezoid(RISING, CASE27_DEPTHS) / 12.0)
    assert mean_falling == pytest.approx(mean_rising)
    # ...while the trapping-depth values are far apart, which is what makes the test discriminate.
    at_trapping = [float(np.interp(TRAPPING_DEPTH, CASE27_DEPTHS, p)) for p in (FALLING, RISING)]
    assert abs(at_trapping[0] - at_trapping[1]) > 1.9


@pytest.mark.golden
@pytest.mark.parametrize(
    ("falling_run", "rising_run", "condition"),
    [
        ("ModelResults_2.dat", "ModelResults_3.dat", "cBOD 20/day, IDOD 0"),
        ("ModelResults_8.dat", "ModelResults_9.dat", "cBOD 0.23/day, IDOD 0"),
        ("ModelResults_5.dat", "ModelResults_6.dat", "cBOD 20/day, IDOD 100"),
    ],
)
def test_the_far_field_ambient_is_the_trapping_depth_value_not_the_depth_mean(
    falling_run: str, rising_run: str, condition: str
) -> None:
    """⭐⭐ case28's discriminator: two ambients with one depth-mean, differenced.

    The BOD demand and IDOD are identical within each pair and cancel exactly in the difference, so
    this measures eq 30's `DO_a` and nothing else -- which is why the same number comes out under
    conditions that differ by 87x in decay rate and 100 mg/L in IDOD.
    """

    def at_500(name: str) -> float:
        far = read_dat(CASE28 / name).farfield
        distance = far["Distance"].to_numpy(dtype=float)
        return float(far["DO"].to_numpy(dtype=float)[int(np.argmin(np.abs(distance - 500.0)))])

    gap = at_500(falling_run) - at_500(rising_run)
    # 1.769 for the trapping-depth value against 0.750 for the depth-mean, both computed from the
    # observed near-field endpoints. The tolerance is a tenth of the gap between the two.
    assert gap == pytest.approx(1.769, abs=0.1), condition


@pytest.mark.golden
def test_the_registered_predictions_landed() -> None:
    """case28 runs 8 and 9 are the exact conditions the predictions were written for.

    ⚠️ Runs 1-7 were not -- the DO tab retained a 20 /day rate where the note asked for 0.23 -- so
    the registered absolute numbers apply to these two runs only. Kept because a prediction that was
    written down before the run and then landed is the strongest evidence this project produces.
    """
    for name, registered, refuted in (
        ("ModelResults_8.dat", 7.409, 6.814),
        ("ModelResults_9.dat", 5.624, 6.064),
    ):
        far = read_dat(CASE28 / name).farfield
        distance = far["Distance"].to_numpy(dtype=float)
        observed = float(far["DO"].to_numpy(dtype=float)[int(np.argmin(np.abs(distance - 500.0)))])
        assert abs(observed - registered) < 0.03
        assert abs(observed - refuted) > 0.4


@pytest.mark.golden
@pytest.mark.parametrize("name", ["ModelResults_5.dat", "ModelResults_6.dat", "ModelResults_7.dat"])
def test_a_large_idod_confirms_the_form_and_finds_no_clamp(name: str) -> None:
    """✅ IDOD 100 mg/L -- 33x where the law was fitted -- and the exe prints -93 mg/L to do it."""
    nearfield = read_dat(CASE28 / name).nearfield
    dilution = nearfield["Dilutn"].to_numpy(dtype=float)
    printed = nearfield["DO"].to_numpy(dtype=float)

    assert printed.min() < -90.0, "the near field prints deeply negative oxygen, unclamped"
    # Rows past the first are strictly negative, so the lone 0.000 first row is not a clamp.
    assert np.all(printed[1:] < 0.0)

    # Back the immediate demand out of the accumulator: DO*D = DO_e + integral((DO_a - IDOD) dD).
    # Only the uniform-ambient run has a DO_a simple enough to invert in one line.
    if name == "ModelResults_7.dat":
        implied = (2.0 + 8.0 * (dilution - 1.0) - printed * dilution) / (dilution - 1.0)
        assert implied[-1] == pytest.approx(100.0, abs=0.05)


@pytest.mark.golden
def test_the_effluent_seed_and_the_immediate_demand_are_separable() -> None:
    """⭐ case28 runs 11 and 12 differ only in `DO_e`, 2 against 20, and split the pair apart.

    Until these two runs the archive could see only `DO_e - IDOD`, so the two inputs looked
    interchangeable. They are not: the seed dilutes as `1/D` while IDOD grows to its full value,
    because the exe carries one on the effluent and the other on the water entrained into it.
    """
    columns = {}
    for trace in (11, 12):
        frame = read_dat(CASE28 / f"ModelResults_{trace}.dat").nearfield
        columns[trace] = frame["DO"].to_numpy(dtype=float)
        dilution = frame["Dilutn"].to_numpy(dtype=float)

    difference = columns[12] - columns[11]
    seed = 18.0 / dilution
    assert np.max(np.abs(difference - seed)) < 0.12
    # It is the *tail* that carries the meaning: 18 mg/L of effluent DO is worth 0.072 by the end.
    assert difference[-1] == pytest.approx(seed[-1], abs=0.002)
    assert difference[-1] < 0.08


@pytest.mark.golden
def test_idod_does_not_appear_a_second_time_in_the_far_field() -> None:
    """✅ Refuted at the opening rows, where the far field is at FF = 1 and nothing is diluted yet.

    A second appearance would be at full size there -- 100 mg/L undiluted, or 0.406 divided by the
    near-field dilution. The agreement instead is 0.004 mg/L, so neither form survives, and no fit
    is involved.
    """
    dat = read_dat(CASE28 / "ModelResults_11.dat")
    near, far = dat.nearfield, dat.farfield
    dilution = float(near["Dilutn"].iloc[-1])
    factor = far["Dilution"].to_numpy(dtype=float) / dilution
    printed = far["DO"].to_numpy(dtype=float)
    effluent = EffluentDO(dissolved_oxygen=2.0, idod=100.0, **_NEW, cbod_decay=0.23)

    ours = far_field_oxygen(
        effluent,
        8.0,
        0.0,
        0.0,
        float(near["DO"].iloc[-1]),
        dilution,
        factor,
        far["Time"].to_numpy(dtype=float) / 24.0,
        reproduce_undiluted_bod=True,
    )
    opening = factor == 1.0
    assert opening.sum() == 13, "the far field opens with 13 rows before Brooks spreading begins"
    assert np.max(np.abs((ours - printed)[opening])) < 0.03

    # Both candidate second appearances would show at full size in exactly those rows.
    for shift in (100.0, 100.0 / dilution):
        assert np.max(np.abs((ours - shift / factor - printed)[opening])) > 0.3


def test_the_typed_rate_is_used_as_typed() -> None:
    """Row 235: no theta correction. A passed temperature is a departure, and must change things."""
    effluent = EffluentDO(**_OLD, cbod_decay=5.0)
    dilution, transition, factor, days, printed = _far_field_inputs(CASE26 / "ModelResults_1.dat")
    common = (8.0, 0.0, 0.0, transition, dilution, factor, days)

    as_typed = far_field_oxygen(effluent, *common, reproduce_undiluted_bod=True)
    assert np.max(np.abs(as_typed - printed)) < 0.08

    at_twenty = far_field_oxygen(effluent, *common, temperature=20.0, reproduce_undiluted_bod=True)
    assert at_twenty == pytest.approx(as_typed), "eqs 26-27 are the identity at 20 degrees"

    corrected = far_field_oxygen(effluent, *common, temperature=12.0, reproduce_undiluted_bod=True)
    assert np.max(np.abs(corrected - printed)) > 0.2, "a theta correction would spoil the fit"


# ------------------------------------------- DO and carbonate side by side (Phase 8.6)


@pytest.fixture(scope="module")
def coexisting_runs(oxygen_case):  # type: ignore[no-untyped-def]
    """One case carrying both endmember sets, and each half on its own for comparison.

    Three integrations, shared, because the claim needs all three: that both column families
    appear together, and that each is **numerically unchanged** by the other's presence.
    """
    cheap, _dosed = oxygen_case
    chemistry_levels = [
        AmbientChemistryLevel(depth=depth, total_alkalinity=2300.0, dic=2050.0)
        for depth in (0.0, 20.0)
    ]
    oxygen_levels = [
        AmbientDOLevel(depth=depth, dissolved_oxygen=value, cbod5=5.0, nbod5=6.0)
        for depth, value in CASE24_AMBIENT
    ]
    chemistry_only = cheap.model_copy(
        update={
            "ambient": cheap.ambient.model_copy(update={"chemistry": chemistry_levels}),
            "effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5),
        }
    )
    oxygen_only = cheap.model_copy(
        update={
            "ambient": cheap.ambient.model_copy(update={"dissolved_oxygen": oxygen_levels}),
            "effluent_do": CASE24_EFFLUENT,
        }
    )
    both = chemistry_only.model_copy(
        update={
            "ambient": chemistry_only.ambient.model_copy(
                update={"dissolved_oxygen": oxygen_levels}
            ),
            "effluent_do": CASE24_EFFLUENT,
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(both, samples=20), run(chemistry_only, samples=20), run(oxygen_only, samples=20)


@pytest.mark.slow
def test_dissolved_oxygen_and_carbonate_chemistry_coexist(coexisting_runs) -> None:  # type: ignore[no-untyped-def]
    """⭐ The exe made these mutually exclusive. This port never did, and now says so.

    ⚠️⚠️ **This closes Phase 8.6, and the item was already true when it was written down.** The
    restriction was never inherited -- `Case` has carried `effluent_do` and the carbonate tables
    side by side with no exclusion since phase 4 -- so there was nothing to implement and nothing
    asserting it either. That is the whole risk: a future change could reintroduce the coupling,
    by validator or by an `elif` in the results assembly, and no test would notice a *capability*
    quietly disappearing.

    The strong half is the second assertion. Coexisting is cheap; coexisting **without
    interfering** is the claim worth pinning, because the plausible regression is not "one column
    vanishes" but "one column changes when the other is present".
    """
    both, chemistry_only, oxygen_only = coexisting_runs

    assert both.has_chemistry and both.has_oxygen, "one run must be able to carry both"
    for column in (*CHEMISTRY_COLUMNS, *OXYGEN_COLUMNS):
        assert column in both.nearfield.columns, column

    # ⭐ Neither family perturbs the other. The carbonate system does not consume oxygen and the
    # BOD decay does not touch alkalinity, so agreement should be exact rather than approximate.
    for column in CHEMISTRY_COLUMNS:
        np.testing.assert_allclose(
            both.nearfield[column],
            chemistry_only.nearfield[column],
            rtol=0.0,
            atol=0.0,
            err_msg=f"{column} moved when the oxygen endmember was added",
        )
    for column in OXYGEN_COLUMNS:
        np.testing.assert_allclose(
            both.nearfield[column],
            oxygen_only.nearfield[column],
            rtol=0.0,
            atol=0.0,
            err_msg=f"{column} moved when the carbonate endmember was added",
        )


@pytest.mark.slow
def test_each_half_alone_carries_only_its_own_columns(coexisting_runs) -> None:  # type: ignore[no-untyped-def]
    """The other direction: a case with one endmember set must not grow the other's columns.

    Otherwise the coexistence test above would pass on a run that emitted every column
    unconditionally, filled with whatever a missing endmember defaults to.
    """
    _both, chemistry_only, oxygen_only = coexisting_runs

    assert chemistry_only.has_chemistry and not chemistry_only.has_oxygen
    assert not any(c in chemistry_only.nearfield.columns for c in OXYGEN_COLUMNS)

    assert oxygen_only.has_oxygen and not oxygen_only.has_chemistry
    assert not any(c in oxygen_only.nearfield.columns for c in CHEMISTRY_COLUMNS)
