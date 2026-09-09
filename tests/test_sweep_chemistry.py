"""The sweep harness on a chemistry case: the dose axis exists and reaches Ω_brucite (PLAN 9).

⚠️ Until 2026-08-25 the harness had only ever been exercised on `cheap_case` over a flow axis
(`test_sweep.py`). Every piece of the dose path -- `with_updated` through `effluent_chemistry`,
far-field chemistry at a chronic boundary, `omega_brucite` in the extract -- had been tested
alone and never together, so the study's own quantity could have vanished from the frame with
no test noticing. This module is that pin. Three integrations of case03, the archive's one
chemistry case -- two sweep cells and one dense run shared by the crossing tests -- which is why
it is marked slow and kept to that.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from plumes2.config import Case, EffluentChemistry
from plumes2.io.project import load_project
from plumes2.sweep import brucite_extract, sweep
from tests.conftest import REFERENCE_CASES

DOSE = "effluent_chemistry.total_alkalinity"


def _case03_dosed() -> Case:
    """case03 with its effluent endmember attached -- the `.prj` cannot carry it (PLAN 7b)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base = load_project(
            REFERENCE_CASES / "case03_carbonate" / "test.prj", warn_on_drift=False
        ).to_case()
        dosed = base.model_copy(
            update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
        )
        return Case.model_validate(dosed.model_dump())


@pytest.fixture(scope="module")
def dose_sweep():  # type: ignore[no-untyped-def]
    """case03 at its own dose and twice it -- two integrations, the module's whole budget."""
    return sweep(_case03_dosed(), {DOSE: [4000.0, 8000.0]}, samples=48)


@pytest.mark.slow
def test_the_dose_axis_runs_and_reaches_brucite(dose_sweep) -> None:  # type: ignore[no-untyped-def]
    assert list(dose_sweep[DOSE]) == [4000.0, 8000.0]
    assert (dose_sweep["error"] == "").all(), dose_sweep["error"].tolist()
    for boundary in ("acute", "chronic"):
        for column in ("ph_total", "omega_aragonite", "omega_brucite"):
            name = f"{boundary}_{column}"
            assert name in dose_sweep.columns, name
            assert np.isfinite(dose_sweep[name]).all(), name


@pytest.mark.slow
def test_both_boundaries_are_answered_by_the_far_field_on_case03(dose_sweep) -> None:  # type: ignore[no-untyped-def]
    """⚠️ A structural fact about the driver case, and a finding of the first dry run.

    case03's acute boundary is 20.7 m against a near field a few metres long, so *both*
    regulatory distances are Brooks numbers -- and Ω_brucite there is ~0.009 at any dose the
    harness has seen. A study that read only the boundaries would report no brucite risk while
    the port sits above Ω = 100; the near-field peak has to be read separately.
    """
    assert set(dose_sweep["acute_region"]) == {"farfield"}
    assert set(dose_sweep["chronic_region"]) == {"farfield"}
    assert (dose_sweep["acute_omega_brucite"] < 1.0).all()


@pytest.mark.slow
def test_more_alkalinity_means_more_alkalinity_downstream(dose_sweep) -> None:  # type: ignore[no-untyped-def]
    """Conservative mixing: the dose must not be lost between the port and the chronic zone.

    ⚠️ Deliberately loose. At a 500-2000x dilution the two doses differ by a few µmol/kg at
    the boundary, so this asserts the *sign* only -- the sharp conservative-mixing checks live
    in `test_chem.py` against the exe's own rows.
    """
    ta = dose_sweep.sort_values(DOSE)["chronic_total_alkalinity_umol_kg"].to_numpy()
    assert ta[1] > ta[0]
    assert not math.isclose(ta[1], ta[0], rel_tol=0, abs_tol=1e-9)


@pytest.fixture(scope="module")
def dense_run():  # type: ignore[no-untyped-def]
    """One dense integration of case03 at its own dose -- the crossing is ~0.3 s from the port."""
    from plumes2.results import run

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(_case03_dosed(), samples=3000)


@pytest.mark.slow
def test_the_plume_crosses_brucite_saturation_at_the_analytical_ph(dense_run) -> None:  # type: ignore[no-untyped-def]
    """The study's crossing agrees with the constants it is computed from -- an internal check.

    Row 197's lesson: a quantity with no parity target needs an analytical limit. Here the limit
    is `pH*` from `test_brucite.brucite_saturation_ph_total`, and the run's own Ω = 1 crossing
    must land on it.
    """
    from tests.test_brucite import brucite_saturation_ph_total

    near = dense_run.nearfield
    omega = near["omega_brucite"].to_numpy()
    last_above = int(np.flatnonzero(omega > 1.0)[-1])
    # pH falls ~0.15 per sample this close to the port, so interpolate at log Ω = 0 rather than
    # averaging the two bracketing rows -- the mean is 0.03 high, the interpolation is not.
    lo, hi = np.log(omega[last_above]), np.log(omega[last_above + 1])
    frac = lo / (lo - hi)

    def at_crossing(column: str) -> float:
        a, b = near[column].iloc[last_above], near[column].iloc[last_above + 1]
        return float(a + frac * (b - a))

    crossing_ph = at_crossing("ph_total")
    expected = brucite_saturation_ph_total(
        at_crossing("salinity_psu"), at_crossing("temperature_degC")
    )
    assert crossing_ph == pytest.approx(expected, abs=0.01), (crossing_ph, expected)
    # And it happens within the first couple of dilutions, not the first hundred.
    assert float(near["dilution"].iloc[last_above + 1]) < 2.5


# --------------------------------------------------------------- brucite_extract (2026-08-25)


@pytest.mark.slow
def test_brucite_extract_reads_what_the_boundaries_cannot(dense_run) -> None:  # type: ignore[no-untyped-def]
    """⭐ Finding 4 of the dry run, as a pin: the port is at Ω > 100, both boundaries at 0.009.

    `mixing_zone_extract` alone is not a brucite observable on case03; the promoted extract must
    carry the port and peak values and the crossing, and its crossing must be the same number the
    analytical test above interpolates by hand.
    """
    out = brucite_extract(dense_run)
    for key in ("acute_omega_brucite", "chronic_omega_brucite", "termination"):
        assert key in out, "the default extract's columns are kept"
    assert out["port_omega_brucite"] > 100.0
    assert out["nearfield_peak_omega_brucite"] == out["port_omega_brucite"], (
        "the port is the peak: dilution only ever lowers pH on a dosed plume"
    )
    assert out["acute_omega_brucite"] < 0.02 and out["chronic_omega_brucite"] < 0.02
    assert out["omega1_region"] == "nearfield"
    assert 1.0 < out["omega1_dilution"] < 2.5, "the risk window is a couple of dilutions"
    assert 0.0 < out["omega1_time_s"] < 1.0, "under a second"
    assert 0.0 < out["omega1_distance_m"] < 0.05, "centimetres, not the 30 s / 100x once quoted"

    near = dense_run.nearfield
    omega = near["omega_brucite"].to_numpy()
    last = int(np.flatnonzero(omega > 1.0)[-1])
    lo, hi = np.log(omega[last]), np.log(omega[last + 1])
    frac = lo / (lo - hi)
    a, b = near["dilution"].iloc[last], near["dilution"].iloc[last + 1]
    assert out["omega1_dilution"] == pytest.approx(float(a + frac * (b - a)), rel=1e-12)


@pytest.mark.slow
def test_an_undosed_plume_never_crosses(dense_run) -> None:  # type: ignore[no-untyped-def]
    """A frame with Ω below 1 throughout reads `never`, with NaN for the extent."""
    import dataclasses

    near = dense_run.nearfield.copy()
    near["omega_brucite"] = near["omega_brucite"] * 1e-6
    out = brucite_extract(dataclasses.replace(dense_run, nearfield=near))
    assert out["omega1_region"] == "never"
    for key in ("omega1_dilution", "omega1_time_s", "omega1_distance_m"):
        assert math.isnan(out[key]), key


@pytest.mark.slow
def test_a_plume_still_supersaturated_at_the_near_field_end_continues_downstream(dense_run) -> None:  # type: ignore[no-untyped-def]
    """Scaling Ω so the near field never falls through 1 must find the crossing in the Brooks table.

    ⚠️ The scale is a narrow choice, and the first draft of this test got it wrong twice. On
    case03 the far field lowers Ω_brucite by only **2 %** over 500 m (0.00873 at the seam to
    0.00855 at a 5000x dilution -- pH moves by hundredths out there), and the seam value *is*
    the near-field end by construction. So Ω = 2 at the transition is still 2 at 500 m and the
    honest answer is `beyond_farfield`; only a scale that puts the seam within 2 % above 1 puts
    the crossing in the Brooks table. Both premises are asserted rather than assumed. Scaled up
    again so nothing crosses, the region is `beyond_farfield` and the values are the last
    row's -- a floor, and labelled as one.
    """
    import dataclasses

    near = dense_run.nearfield.copy()
    far = dense_run.farfield.copy()
    assert far is not None and "omega_brucite" in far.columns
    scale = 1.01 / float(near["omega_brucite"].iloc[-1])
    assert float(far["omega_brucite"].iloc[0]) * scale > 1.0, "the premise: above 1 at the seam"
    assert float(far["omega_brucite"].iloc[-1]) * scale < 1.0, "and below 1 where the table ends"
    near["omega_brucite"] = near["omega_brucite"] * scale
    far["omega_brucite"] = far["omega_brucite"] * scale
    out = brucite_extract(dataclasses.replace(dense_run, nearfield=near, farfield=far))
    assert out["omega1_region"] == "farfield"
    assert out["omega1_distance_m"] > out["nearfield_end_distance_m"]
    assert out["omega1_time_s"] > out["nearfield_end_time_s"]

    far["omega_brucite"] = far["omega_brucite"] * 1e9
    out = brucite_extract(dataclasses.replace(dense_run, nearfield=near, farfield=far))
    assert out["omega1_region"] == "beyond_farfield"
    assert out["omega1_distance_m"] == pytest.approx(float(far["distance_m"].iloc[-1]))
