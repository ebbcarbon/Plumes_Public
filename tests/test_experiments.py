"""Generated exe experiments."""

from __future__ import annotations

from pathlib import Path

import pytest

from plumes2.ambient import AmbientProfileView
from plumes2.chem.constants import resolve_constants
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.experiments import Experiment, fill_ambient_ph, write_experiment
from plumes2.io.project import load_project

CASES = Path(__file__).resolve().parents[1] / "reference_cases"


def _case():  # type: ignore[no-untyped-def]
    return load_project(
        CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
    ).to_case()


def test_a_generated_experiment_round_trips_through_the_exe_format(tmp_path: Path) -> None:
    """The point of generating rather than hand-editing: the file matches the case exactly."""
    case = _case()
    diffuser = case.diffuser.model_copy(update={"port_spacing": 1.25, "horizontal_angle": 175.0})
    case = case.model_copy(update={"diffuser": diffuser})

    written = write_experiment(
        Experiment(name="probe", case=case, question="Does it round-trip?"), tmp_path
    )
    reloaded = load_project(written / "probe.prj", warn_on_drift=False).to_case()
    assert reloaded.diffuser.port_spacing == 1.25
    assert reloaded.diffuser.horizontal_angle == 175.0
    assert reloaded.diffuser.n_ports == case.diffuser.n_ports
    assert reloaded.effluent.flow == case.effluent.flow


def test_the_note_carries_what_the_project_file_cannot(tmp_path: Path) -> None:
    """The GUI-only settings and the prediction have to travel *with* the file.

    Both archive failures were bookkeeping: test19 had no project, test34's was stale. A note
    written from the case cannot drift from it.
    """
    written = write_experiment(
        Experiment(
            name="probe",
            case=_case(),
            question="Why does this run exist?",
            predictions={"merge trigger": "0.775"},
            notes=("watch for an early surface hit",),
        ),
        tmp_path,
    )
    note = (written / "README.md").read_text(encoding="utf-8")
    assert "Why does this run exist?" in note
    assert "0.775" in note
    assert "watch for an early surface hit" in note
    # The three things the .prj silently drops.
    assert "stop plume at bottom hit" in note
    assert "maximum plume rise or fall" in note
    assert "Chemistry" in note
    # And the trap that has bitten twice.
    assert "two decimals" in note
    # ⚠️ The stale-project protection, reworded 2026-08-24: the old note said "save the .prj
    # before closing it", and there is no Save-As -- the exe writes the project when the model
    # runs. So what protects a run is copying both files aside before the *next* run, which is
    # what test34/test35 actually needed.
    assert "copy both files aside" in note.lower()
    assert "test34/test35" in note


def test_the_note_records_what_generated_it(tmp_path: Path) -> None:
    """A generated experiment has to say which code made it -- PLAN.md section 7b.

    The `.prj` has no field for a version, a commit or a date, so the note is the only place
    it can go.
    """
    from plumes2.provenance import case_digest

    case = _case()
    written = write_experiment(Experiment(name="probe", case=case, question="?"), tmp_path)
    note = (written / "README.md").read_text(encoding="utf-8")
    assert "## Provenance" in note
    assert case_digest(case) in note, "the digest must pin the case the .prj came from"
    assert "plumes2" in note


def _chemistry_case():  # type: ignore[no-untyped-def]
    """case03's project, which carries a four-level ambient chemistry table."""
    return load_project(CASES / "case03_carbonate" / "test.prj", warn_on_drift=False).to_case()


def test_a_chemistry_experiment_gets_its_ambient_table(tmp_path: Path) -> None:
    """⚠️ **The exe will not run a carbonate case without an ambient chemistry table.**

    Found on `case03_kso4_option3`, 2026-08-20: the generated experiment carried only the `.prj`,
    and the `.prj` holds no chemistry at all (PLAN section 7b). The *ambient* half does live in a
    CSV the exe loads, so leaving it out made the person at the keyboard retype a four-level table
    by hand -- work, and a fresh chance for the run to diverge from the case that was predicted.

    Byte-identity against the exe's own `testco2.csv` is the assertion that matters: a CSV the exe
    rejects is worse than no CSV, because the failure arrives after the GUI session is set up.

    ⚠️ **Since 2026-08-25 the identity holds with one column excepted.** `testco2.csv` leaves its
    pH blank, and the exe's GUI refused to run `dose_parity` until a number sat in every row -- so
    the generator now fills a blank pH with the solved value (`fill_ambient_ph`). Blank that field
    back out and the bytes must still match the exe's file exactly, quoting, `%.2E`, CRLF and the
    sixteen padding rows included.
    """
    case = _chemistry_case()
    assert case.ambient.chemistry, "case03 should carry an ambient chemistry table"
    assert all(level.ph is None for level in case.ambient.chemistry), (
        "this test relies on case03's pH column being blank in the archived file"
    )

    written = write_experiment(
        Experiment(name="probe", case=case, question="does the ambient table come along?"),
        tmp_path,
    )
    generated = written / "AmbientChem_probe.csv"
    assert generated.exists(), "a case with ambient chemistry must get its CSV written"

    reference = (CASES / "case03_carbonate" / "testco2.csv").read_bytes()
    generated_lines = generated.read_bytes().split(b"\r\n")
    reference_lines = reference.split(b"\r\n")
    assert len(generated_lines) == len(reference_lines)
    filled = 0
    for ours, theirs in zip(generated_lines, reference_lines, strict=True):
        if ours == theirs:
            continue
        # The only permitted difference: the fourth (pH) field is filled where theirs is blank.
        ours_fields, theirs_fields = ours.split(b","), theirs.split(b",")
        assert theirs_fields[3] == b'""', f"unexpected difference outside the pH column: {ours!r}"
        assert ours_fields[3] != b'""', "the pH field must be filled, not blank"
        ours_fields[3] = b'""'
        assert ours_fields == theirs_fields, f"row differs beyond the pH field: {ours!r}"
        filled += 1
    assert filled == len(case.ambient.chemistry), "every data row's pH must be filled"


def test_the_filled_ambient_ph_is_the_solver_s_own_free_scale_value() -> None:
    """The placeholder the GUI demands is the *right* placeholder: PyCO2SYS on the row's TA and DIC.

    The exe ignores the column (row 45), so nothing downstream depends on the value; what this
    pins is that the number written is consistent with the columns the exe *does* read, at the
    profile's own S and T, on the free scale the dialog labels typed pH with. A `7.80` or a
    total-scale value would each be a silent 0.1-0.6 unit inconsistency for anyone reading the
    file later.
    """
    case = _chemistry_case()
    levels = fill_ambient_ph(case)
    assert [level.depth for level in levels] == [level.depth for level in case.ambient.chemistry]
    view = AmbientProfileView(case.ambient)
    for original, level in zip(case.ambient.chemistry, levels, strict=True):
        assert level.ph is not None
        # Everything but the pH is untouched.
        assert level.model_dump(exclude={"ph"}) == original.model_dump(exclude={"ph"})
        state = solve_from_alkalinity_dic(
            level.total_alkalinity,
            level.dic,
            view.salinity(level.depth),
            view.temperature(level.depth),
            constants=resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option),
        )
        assert level.ph == pytest.approx(float(state.ph_free), abs=1e-9)
        # Free sits above total by the sulfate term, ~0.09 at S 32; the total-scale figure is
        # the 8.37 the trace prints at its ambient limit (row 45), so free lands near 8.46.
        assert 8.3 < level.ph < 8.6
        assert level.ph > float(state.ph_total)


def test_a_row_that_already_carries_a_ph_is_left_alone() -> None:
    """Filling is for blanks only: an entered pH is the operator's, and is written as entered."""
    case = _chemistry_case()
    entered = [level.model_copy(update={"ph": 7.8}) for level in case.ambient.chemistry]
    case = case.model_copy(
        update={"ambient": case.ambient.model_copy(update={"chemistry": entered})}
    )
    assert [level.ph for level in fill_ambient_ph(case)] == [7.8] * len(entered)


def test_a_case_without_chemistry_gets_no_stray_csv(tmp_path: Path) -> None:
    """The side-tables are written only when the case has them, or every run gains empty files."""
    written = write_experiment(Experiment(name="probe", case=_case(), question="?"), tmp_path)
    assert not list(written.glob("AmbientChem_*.csv"))
    assert not list(written.glob("AmbientDO_*.csv"))
    assert (written / "probe.prj").exists()


def test_a_generated_experiment_asks_for_every_column(tmp_path: Path) -> None:
    """⭐⭐ The output-column selection **is** in the `.prj`, so a generated run need not be thin.

    PLAN section 5 asks for old-build runs because "the new build's UI bug blocks the extra output
    columns, and `Time`, `P-Den`, `P-Sal`, `P-Temp` are what make a trace usable here". Confirmed
    2026-08-20: the bug is in the **GUI's column picker**, not the model -- a 2026 build handed a
    project that already names the columns printed all 21 of them. So the constraint was never the
    build, and `prj_from_case`'s five-column default was quietly making every generated experiment
    thin.

    `Time` is the one that matters most: without it a trace cannot be compared at the exe's own
    instants, which is exactly what retired row 105.
    """
    from plumes2.io.prj import read_prj

    written = write_experiment(Experiment(name="probe", case=_case(), question="?"), tmp_path)
    project = read_prj(written / "probe.prj")
    assert len(project.nearfield_plot_variables) == 13
    assert len(project.farfield_plot_variables) == 6
    for required in ("Time", "Plume-Salinity", "Plume-Temp", "Plume-Density"):
        assert required in project.nearfield_plot_variables, required


def test_the_generated_project_still_round_trips(tmp_path: Path) -> None:
    """Widening the column list must not break the byte format the exe parses."""
    from plumes2.io.prj import read_prj, write_prj

    written = write_experiment(Experiment(name="probe", case=_case(), question="?"), tmp_path)
    original = (written / "probe.prj").read_bytes()
    again = tmp_path / "again.prj"
    write_prj(read_prj(written / "probe.prj"), again)
    assert again.read_bytes() == original


# --------------------------------------------------------------- far-field session state
#
# The exe's far-field stop dialog takes a distance and a dilution together, stops at whichever
# binds first, and stores neither -- operator-confirmed 2026-08-24. Ledger row 277 census-checks
# the whole archive; these tests pin the classifier's edges on the traces that taught them.


def _archived_dat(relative: str):  # type: ignore[no-untyped-def]
    from plumes2.io.dat import read_dat

    return read_dat(CASES / relative)


def test_a_distance_stop_is_claimed_even_when_a_dilution_level_was_crossed() -> None:
    """⚠️ The trap the census's first draft fell into, kept as a test.

    case02's test1 crosses 5000x dilution at 500.0 m exactly and stops at 501.611 m -- the
    *distance* bound it, and the dilution number is a coincidence. 33 archived traces cross 5000x
    and run on to 500 m regardless (their session's stop was 10000x), so a naive threshold check
    misfiles every one of them.
    """
    from plumes2.experiments import classify_farfield_stop

    stop = classify_farfield_stop(_archived_dat("case02_mgd/test1.dat"))
    assert stop is not None
    assert stop.kind == "distance"
    assert stop.stop == 500.0
    assert stop.dilution > 5000.0, "the trap requires the dilution to have crossed"


def test_a_dilution_stop_is_claimed_despite_the_exe_stopping_rows_late() -> None:
    """The exe stops 1-4 rows past the dilution crossing; test72 is the worst archived case."""
    from plumes2.experiments import classify_farfield_stop

    stop = classify_farfield_stop(_archived_dat("case43_port_count/test72.dat"))
    assert stop is not None
    assert stop.kind == "dilution"
    assert stop.stop == 10_000.0

    stop = classify_farfield_stop(_archived_dat("case03_carbonate/kso4_option3.dat"))
    assert stop is not None
    assert stop.kind == "dilution"
    assert stop.stop == 5_000.0


def test_the_chronic_default_is_read_from_the_trace_alone() -> None:
    """A run where no distance was typed stops at the chronic-MZ boundary the trace echoes.

    Trace-only matters: nine cases have no `.prj` at all, and they classify anyway.
    """
    from plumes2.experiments import classify_farfield_stop

    stop = classify_farfield_stop(_archived_dat("case13_generated_example/PythonGenerated2.dat"))
    assert stop is not None
    assert stop.kind == "chronic_default"
    assert stop.stop == 102.0


def test_the_graduation_check_names_an_untyped_distance() -> None:
    """A returning run that stopped at the chronic default gets told, in the message, that the
    declared distance was never typed -- the far-field analogue of watching `nearfield_flags[1]`.
    """
    from plumes2.experiments import check_farfield_session_state
    from plumes2.io.project import load_project

    case = load_project(
        CASES / "case13_generated_example" / "PythonGenerated.prj", warn_on_drift=False
    ).to_case()
    problems = check_farfield_session_state(
        _archived_dat("case13_generated_example/PythonGenerated2.dat"), case
    )
    assert len(problems) == 1
    assert "never typed" in problems[0]
    assert "500" in problems[0], "the message must name the declared distance"


def test_the_graduation_check_passes_a_consistent_run() -> None:
    """A run that reached its declared distance stop raises nothing."""
    from plumes2.experiments import check_farfield_session_state
    from plumes2.io.project import load_project

    case = load_project(
        CASES / "case31_surface_stop_pair" / "surface_stop_and_salinity.prj", warn_on_drift=False
    ).to_case()
    problems = check_farfield_session_state(
        _archived_dat("case31_surface_stop_pair/surface_on.dat"), case
    )
    assert problems == []


def test_the_note_instructs_both_farfield_stops(tmp_path: Path) -> None:
    """The generated README must carry the distance *and* the dilution stop, derived from the
    case -- before 2026-08-24 it mentioned neither, which is how the operator habit went
    unrecorded for six weeks.
    """
    written = write_experiment(Experiment(name="probe", case=_case(), question="?"), tmp_path)
    note = (written / "README.md").read_text(encoding="utf-8")
    assert "far-field stop" in note
    assert "far-field eddy diffusivity: **4/3 power law based eddy diffusivity**" in note
    assert "500 m" in note
    assert "10000x" in note, "the operator's usual dilution stop, the default since 2026-08-24"
    assert "whichever binds first" in note
    assert "chronic-MZ boundary" in note
