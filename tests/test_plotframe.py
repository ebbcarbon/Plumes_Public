"""The neutral plot frame, and the exe trace as a first-class input to it."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from plumes2.crossplume import PEAK_TO_MEAN_ROUND
from plumes2.io.dat import read_dat
from plumes2.io.project import load_project
from plumes2.plotframe import (
    EXE_CHEMISTRY_COLUMNS,
    MissingColumnError,
    from_dat,
    from_results,
)
from plumes2.results import CHEMISTRY_COLUMNS
from tests.conftest import ALL_DAT_PATHS, EXAMPLE_PROJECT, REFERENCE_CASES

CARBONATE = REFERENCE_CASES / "case03_macoma_carbonate"
#: The Dec-2025 build's `.dat` is the one the reader cannot parse; see tests/io/test_dat.py.
CASE00 = REFERENCE_CASES / "case00_macoma_legacy_fps" / "Macoma_TxtOutputs.dat"
PARSEABLE = [path for path in ALL_DAT_PATHS if path != CASE00]


@pytest.fixture(scope="module")
def carbonate_case():  # type: ignore[no-untyped-def]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_project(CARBONATE / "test.prj", warn_on_drift=False).to_case()


# ------------------------------------------------------------------ the run adapter


def test_a_run_becomes_a_frame_with_provenance_and_no_caveats(cheap_run) -> None:  # type: ignore[no-untyped-def]
    results = cheap_run
    plot = from_results(results)
    assert plot.origin == "run"
    assert not plot.rounded
    assert plot.caveats == (), "our own runs carry no caveats -- they carry provenance instead"
    assert not plot.derived, "nothing is reconstructed from a run; it all came out of the solver"
    assert "plumes2" in plot.source and "case" in plot.source
    assert plot.case is results.case

    # A copy: a panel adding a column must not reach back into the run.
    plot.frame["scratch"] = 1.0
    assert "scratch" not in results.nearfield.columns


# ------------------------------------------------------------------ the exe adapter


@pytest.mark.golden
@pytest.mark.parametrize("path", PARSEABLE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_archived_trace_becomes_a_frame(path: Path) -> None:
    """Whatever columns the GUI happened to select, the trace is plottable."""
    plot = from_dat(read_dat(path), path, secondaries=False)
    assert plot.origin == "dat"
    assert plot.rounded
    assert len(plot.caveats) >= 3, "the three .dat limits must travel with every frame"
    assert plot.case is None
    # The trajectory columns every trace carries, under our names.
    for name in ("dilution", "plume_diameter_m", "x_m", "y_m", "depth_m"):
        assert name in plot.frame.columns, name
    assert len(plot.frame) == len(read_dat(path).nearfield)


@pytest.mark.golden
@pytest.mark.parametrize("path", PARSEABLE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_depth_is_flipped_to_positive_down(path: Path) -> None:
    """The exe prints `Depth` negative-down under a positive-sounding name."""
    dat = read_dat(path)
    plot = from_dat(dat, path, secondaries=False)
    assert np.allclose(
        plot.frame["depth_m"].to_numpy(dtype=float),
        -dat.nearfield["Depth"].to_numpy(dtype=float),
        equal_nan=True,
    )


def test_both_spellings_of_the_dilution_column_are_read() -> None:
    """2026 builds print `Dilutn`; the Dec-2025 build prints `Avg-Dil` for the same quantity."""
    plain = from_dat(
        read_dat(EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat"),
        "example",
        secondaries=False,
    )
    assert "dilution" in plain.frame.columns
    from plumes2.plotframe import _EXE_COLUMNS

    assert _EXE_COLUMNS["Avg-Dil"] == "dilution", "the legacy spelling must map to the same name"


@pytest.mark.golden
def test_a_merged_trace_gets_its_flag_from_the_exe_s_own_banner() -> None:
    """Not re-derived: the trigger uses an effective spacing that depends on the plume's bearing."""
    path = REFERENCE_CASES / "case20_spacing_sweep" / "test32.dat"
    dat = read_dat(path)
    plot = from_dat(dat, path, secondaries=False)
    banner = next(e for e in dat.events if "merg" in e.text.lower())

    assert "merged" in plot.frame.columns
    merged = plot.frame["merged"]
    assert not merged.loc[: banner.next_step - 1].any()
    assert merged.loc[banner.next_step :].all()
    # And the profile flattens from there, using the spacing off the echoed diffuser table.
    assert plot.frame.loc[banner.next_step :, "peak_to_mean"].min() < PEAK_TO_MEAN_ROUND
    assert {"merged", "peak_to_mean"} <= plot.derived


@pytest.mark.golden
def test_an_unmerged_trace_still_gets_a_centreline() -> None:
    """No banner means *not* merged, which is a fact -- so the round profile applies throughout.

    The flag is still derived rather than read, but an unmerged plume's peak-to-mean is exactly 2.0
    and needs no spacing, so there is nothing to guess at and no reason to withhold the centreline.
    """
    path = REFERENCE_CASES / "case20_spacing_sweep" / "test31.dat"
    plot = from_dat(read_dat(path), path, secondaries=False)
    assert not plot.frame["merged"].any()
    assert (plot.frame["peak_to_mean"] == PEAK_TO_MEAN_ROUND).all()
    # test31 selected `CL-Dil`, so the exe's own column is kept rather than overwritten.
    assert "centreline_dilution" not in plot.derived
    printed = plot.frame["centreline_dilution"].to_numpy(dtype=float)
    developed = printed > 1.0
    ours = plot.frame["dilution"].to_numpy(dtype=float)[developed] / PEAK_TO_MEAN_ROUND
    assert np.allclose(ours, printed[developed], rtol=2e-3)


@pytest.mark.golden
def test_a_trace_without_a_centreline_column_gets_one_derived() -> None:
    """The upstream example prints five columns and no centreline; ours follows from the profile."""
    path = EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat"
    plot = from_dat(read_dat(path), path, secondaries=False)
    assert "centreline_dilution" in plot.derived
    frame = plot.frame
    expected = np.maximum(1.0, frame["dilution"].to_numpy(float) / frame["peak_to_mean"].to_numpy())
    assert np.allclose(frame["centreline_dilution"].to_numpy(dtype=float), expected)


@pytest.mark.golden
def test_a_single_port_merge_leaves_the_profile_round() -> None:
    """`limspc_shallow` prints the banner with one port and holds 2.0 for the rest of the run."""
    path = REFERENCE_CASES / "case22_limiting_spacing" / "limspc_shallow.dat"
    plot = from_dat(read_dat(path), path, secondaries=False)
    assert plot.frame["merged"].any()
    assert (plot.frame["peak_to_mean"] == PEAK_TO_MEAN_ROUND).all()


# ------------------------------------------------------------------ the secondaries


@pytest.mark.golden
def test_a_chemistry_trace_without_salinity_is_refused_by_name() -> None:
    """The archive's chemistry traces lack exactly the pair the secondaries need."""
    path = CARBONATE / "test2_TxtOutputs.dat"
    with pytest.raises(MissingColumnError) as raised:
        from_dat(read_dat(path), path)
    message = str(raised.value)
    assert "P-Sal" in message and "P-Temp" in message
    assert "case=" in message, "the message must name the way out, not just the problem"


@pytest.mark.golden
def test_secondaries_can_be_switched_off_to_see_the_trace_as_the_exe_wrote_it() -> None:
    path = CARBONATE / "test2_TxtOutputs.dat"
    plot = from_dat(read_dat(path), path, secondaries=False)
    # TA and DIC are the exe's own columns and stay; everything solved *from* them is absent.
    solved = set(CHEMISTRY_COLUMNS) - {"total_alkalinity_umol_kg", "dic_umol_kg"}
    assert not solved & set(plot.frame.columns)
    assert {"total_alkalinity_umol_kg", "dic_umol_kg"} <= set(plot.frame.columns)
    for name in EXE_CHEMISTRY_COLUMNS:
        assert name in plot.frame.columns, name


@pytest.mark.golden
def test_a_case_unlocks_the_secondaries_the_exe_never_printed(carbonate_case) -> None:  # type: ignore[no-untyped-def]
    """⭐ The point of the exe adapter: Omega_brucite from a trace that could not report it."""
    path = CARBONATE / "test2_TxtOutputs.dat"
    plot = from_dat(read_dat(path), path, case=carbonate_case)
    frame = plot.frame

    for name in CHEMISTRY_COLUMNS:
        assert name in frame.columns, name
    # Salinity and temperature were reconstructed, and the frame says so.
    assert {"salinity_psu", "temperature_degC", "omega_brucite"} <= plot.derived
    # The exe's own saturation states survive beside ours rather than being overwritten.
    for name in EXE_CHEMISTRY_COLUMNS:
        assert name in frame.columns, name
    assert any("brucite" in caveat for caveat in plot.caveats)

    assert (frame["omega_brucite"] > 0).all()
    assert frame["omega_brucite"].iloc[0] > frame["omega_brucite"].iloc[-1], "dosed, then mixed"


@pytest.mark.golden
@pytest.mark.parametrize(
    ("folder", "project", "trace"),
    [
        ("case03_macoma_carbonate", "test.prj", "test2_TxtOutputs.dat"),
        ("case13_generated_example", "PythonGenerated.prj", "PythonGenerated2.dat"),
    ],
)
def test_the_reconstructed_salinity_adds_no_detectable_chemistry_error(
    folder: str, project: str, trace: str
) -> None:
    """The free check the adapter buys: our pH against the exe's, on the exe's own TA and DIC.

    Salinity and temperature here are *derived* -- mixed from the effluent and the ambient profile
    by the printed dilution -- so any error in that reconstruction lands on pH. It does not: the
    gap stays inside the 0.011-0.024 offset `chem/speciation.py` already measured between the exe's
    printed column and PyCO2SYS, which is the residual that exists with or without this path.
    """
    directory = REFERENCE_CASES / folder
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case = load_project(directory / project, warn_on_drift=False).to_case()
    frame = from_dat(read_dat(directory / trace), trace, case=case).frame

    gap = (frame["ph_total"] - frame["ph_exe"]).abs()
    assert gap.max() < 0.03, f"worst {gap.max():.4f}"
    assert gap.mean() < 0.02, f"mean {gap.mean():.4f}"
    # ⚠️ The sign is *not* uniform -- case13 crosses over late in the trajectory, where our pH
    # falls below the printed column. So this is a bounded offset, not a constant bias, and a
    # figure overlaying the two should not describe it as one.

    relative = (
        (frame["omega_aragonite"] - frame["omega_aragonite_exe"]).abs()
        / frame["omega_aragonite_exe"]
    )
    assert relative.mean() < 0.05, f"OmegaA MARE {relative.mean():.3f}"


def test_a_trace_with_no_dilution_column_is_refused() -> None:
    """Every figure is against dilution somewhere; a trajectory without it plots nothing."""
    dat = read_dat(EXAMPLE_PROJECT / "ModelResults_TxtOutputs.dat")
    stripped = dat.nearfield.drop(columns=["Dilutn"])
    with pytest.raises(MissingColumnError, match="dilution"):
        from_dat(
            type(dat)(
                echoed_tables=dat.echoed_tables,
                nearfield=stripped,
                farfield=dat.farfield,
                events=dat.events,
            ),
            "stripped",
        )
