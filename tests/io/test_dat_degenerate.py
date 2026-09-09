"""Reader behaviour on the exe's degenerate output.

`reference_cases/case09_single_port` is a run that went numerically bad: 955
rows of NaN, a NaN wastefield width and an all-NaN far-field. Those rows are data --
they record the failure -- so the reader parses them rather than skipping or raising.

The numbers asserted here also pin the failure mode itself, because two of its causes
are behaviours our port must deliberately *not* copy (see the case README).
"""

from __future__ import annotations

import numpy as np
import pytest

from plumes2.io.dat import read_dat
from tests.conftest import REFERENCE_CASES

CASE07 = REFERENCE_CASES / "case07_s45_dense" / "test6_TxtOutputs.dat"
CASE08 = REFERENCE_CASES / "case08_shoreline" / "test7_TxtOutputs.dat"
CASE09 = REFERENCE_CASES / "case09_single_port" / "test9_TxtOutputs.dat"
CASE05 = REFERENCE_CASES / "case05_merging" / "test4_TxtOutputs.dat"


class TestSinglePortFailure:
    def test_nan_rows_are_parsed_not_skipped(self) -> None:
        dat = read_dat(CASE09)
        assert len(dat.nearfield) == 1001
        assert dat.final_step == 5001
        nan_steps = dat.nearfield.index[dat.nearfield["Dilutn"].isna()]
        assert len(nan_steps) == 955
        assert nan_steps[0] == 235

    def test_nan_wastefield_width_is_parsed(self) -> None:
        width = read_dat(CASE09).wastefield_width
        assert width is not None
        assert np.isnan(width)

    def test_farfield_is_present_but_all_nan(self) -> None:
        dat = read_dat(CASE09)
        assert dat.has_farfield
        assert dat.farfield is not None
        assert bool(dat.farfield.isna().all().all())

    def test_rate_goes_nan_exactly_when_omega_drops_below_one(self) -> None:
        """The root cause: (Omega - 1)**2.87 is a fractional power of a negative."""
        nearfield = read_dat(CASE09).nearfield
        finite = nearfield.loc[nearfield["OmegaC"].notna()]
        undersaturated = finite["OmegaC"] < 1.0
        assert undersaturated.any(), "case09 must contain undersaturated rows"
        assert finite.loc[undersaturated, "R_cal"].isna().all()
        assert finite.loc[~undersaturated, "R_cal"].notna().all()

    def test_plume_centre_rises_above_the_free_surface(self) -> None:
        """Depth becomes positive -- nothing clamps or reflects at the surface."""
        nearfield = read_dat(CASE09).nearfield
        assert nearfield.loc[230, "Depth"] == pytest.approx(0.041)
        assert read_dat(CASE09).event_steps() == {"Plume surfaces": [220]}

    def test_ta_falls_below_the_ambient_endmember(self) -> None:
        """Conservative mixing cannot do this; the transport broke too."""
        nearfield = read_dat(CASE09).nearfield
        assert nearfield.loc[230, "TA"] == pytest.approx(2253.103)
        assert nearfield.loc[230, "TA"] < 2900.0  # ambient TA


class TestDenseEffluent:
    def test_no_bottom_hit_despite_45_psu(self) -> None:
        dat = read_dat(CASE07)
        depth = -dat.nearfield["Depth"]
        assert depth.max() == pytest.approx(3.203)
        # Seabed is at port depth 2.0 + port elevation 15.0.
        assert depth.max() < 17.0
        assert "bottom" not in " ".join(dat.event_steps()).lower()

    def test_aragonite_cutoff_is_crossed_mid_trace(self) -> None:
        """Ledger row 60, now demonstrated inside one run rather than across two."""
        nearfield = read_dat(CASE07).nearfield
        dilution = nearfield["Dilutn"]
        ambient_salinity = np.interp(
            -nearfield["Depth"], [0, 3, 6, 9, 12, 15], [30.9, 31.2, 31.2, 31.7, 31.8, 31.9]
        )
        plume_salinity = (45.0 + (dilution - 1) * ambient_salinity) / dilution
        active = nearfield["R_arg"] > 0
        assert active.sum() == 12
        assert ((plume_salinity > 35.0) == active).all()

    def test_wastefield_width_formula_holds(self) -> None:
        dat = read_dat(CASE07)
        final_diameter = dat.nearfield.loc[dat.final_step, "P-dia"]
        assert 24 * 0.60 + final_diameter == pytest.approx(dat.wastefield_width, abs=0.005)


class TestShorelineHasNoEffect:
    def test_nearfield_matches_case05_exactly(self) -> None:
        """A 45 degree shoreline vector changed nothing in the near field."""
        shoreline = read_dat(CASE08).nearfield
        baseline = read_dat(CASE05).nearfield
        assert list(shoreline.columns) == list(baseline.columns)
        assert shoreline.index.equals(baseline.index)
        assert np.allclose(
            shoreline.to_numpy(dtype=float), baseline.to_numpy(dtype=float), equal_nan=True
        )

    def test_no_shoreline_event_in_any_trace(self) -> None:
        from tests.conftest import ALL_DAT_PATHS

        for path in ALL_DAT_PATHS:
            if path.name == "ModelResults_legacy1.dat":
                continue  # header-only legacy artifact
            events = " ".join(read_dat(path).event_steps()).lower()
            assert "shore" not in events
