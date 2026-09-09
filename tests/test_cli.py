"""The command line."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from plumes2.cli import main
from plumes2.io.project import load_project
from plumes2.provenance import case_digest

CASES = Path(__file__).resolve().parents[1] / "reference_cases"
PROJECT = CASES / "case18_zero_current_pair" / "test21.prj"


@pytest.mark.slow
def test_run_writes_a_result_directory(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "results"
    assert main(["run", str(PROJECT), "-o", str(out), "--samples", "20"]) == 0

    written = {p.name for p in out.iterdir()}
    assert {"nearfield.csv", "case.yaml", "provenance.yaml"} <= written
    # test21 carries a far-field current, so `farfield.csv` joins them.
    assert "farfield.csv" in written
    frame = pd.read_csv(out / "nearfield.csv")
    assert len(frame) == 20

    printed = capsys.readouterr().out
    assert "near field ended" in printed
    assert "dilution" in printed


def test_the_units_flag_changes_the_summary_and_nothing_else(  # type: ignore[no-untyped-def]
    cheap_case_file, tmp_path: Path, capsys
) -> None:
    """Display units are display-only: the files stay SI, and the run says so.

    On the cheap shared case rather than the archived project: this is about the flag, and the
    test needs two runs to show the files are identical, so it is worth halving each.
    """
    case = str(cheap_case_file)
    metric, imperial = tmp_path / "si", tmp_path / "us"
    assert main(["run", case, "-o", str(metric), "--samples", "20"]) == 0
    si_printed = capsys.readouterr().out
    assert main(["run", case, "-o", str(imperial), "--samples", "20", "--units", "US"]) == 0
    us_printed = capsys.readouterr().out

    assert " m depth" in si_printed and "files are SI" not in si_printed
    assert " ft depth" in us_printed and "files are SI" in us_printed
    # Same numbers on disk either way -- the solver never sees the flag.
    assert (metric / "nearfield.csv").read_text(encoding="utf-8") == (
        imperial / "nearfield.csv"
    ).read_text(encoding="utf-8")


@pytest.mark.slow
def test_run_defaults_the_output_directory_beside_the_case(cheap_case_file, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    copied = tmp_path / "mycase.yaml"
    copied.write_text(cheap_case_file.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["run", str(copied), "--samples", "8"]) == 0
    assert (tmp_path / "mycase_results" / "nearfield.csv").exists()


@pytest.mark.slow
def test_report_writes_a_pdf_by_default(cheap_case_file, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """No `-o`: a `.report.pdf` beside the case, and the console says it is a PDF."""
    copied = tmp_path / "mycase.yaml"
    copied.write_text(cheap_case_file.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["report", str(copied), "--samples", "20"]) == 0
    out = tmp_path / "mycase.report.pdf"
    assert out.read_bytes().startswith(b"%PDF-1.")
    assert {p.name for p in tmp_path.iterdir()} == {copied.name, out.name}, "no sidecars"
    printed = capsys.readouterr().out
    assert "wrote" in printed and "PDF" in printed


@pytest.mark.slow
def test_report_writes_one_html_file_when_asked(cheap_case_file, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An `.html` suffix still writes the self-contained page."""
    out = tmp_path / "report.html"
    assert main(["report", str(cheap_case_file), "-o", str(out), "--samples", "20"]) == 0
    assert [out.name] == [p.name for p in tmp_path.iterdir()], "self-contained: no sidecars"
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "<svg" in html
    assert "browser" in capsys.readouterr().out


@pytest.mark.golden
def test_report_accepts_an_exe_dat_directly(tmp_path: Path) -> None:
    """The GUI's own output is a first-class input, which is what makes the archive reportable."""
    trace = CASES / "case03_carbonate" / "test2_TxtOutputs.dat"
    out = tmp_path / "trace.html"
    assert (
        main(
            [
                "report",
                str(trace),
                "-o",
                str(out),
                "--case-file",
                str(CASES / "case03_carbonate" / "test.prj"),
            ]
        )
        == 0
    )
    html = out.read_text(encoding="utf-8")
    assert "carries no provenance" in html, "a .dat has none, and the report must say so"
    assert "brucite" in html, "and it still reaches the quantity the exe cannot report"


def test_info_does_not_run_the_model(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["info", str(PROJECT)]) == 0
    printed = capsys.readouterr().out
    assert "ports" in printed and "termination" in printed
    # Nothing was written anywhere.
    assert not list(tmp_path.iterdir())


def test_convert_round_trips_a_case_semantically(tmp_path: Path) -> None:
    """Byte fidelity is the `.prj` reader's job; `convert` must preserve the *case*.

    Going through our YAML re-encodes the project from the semantic model, so undecoded flag
    padding is not reproduced -- but every field the model carries has to survive, and the
    digest is what says so.
    """
    yaml_path, back = tmp_path / "case.yaml", tmp_path / "back.prj"
    assert main(["convert", str(PROJECT), str(yaml_path)]) == 0
    assert main(["convert", str(yaml_path), str(back)]) == 0

    original = load_project(PROJECT, warn_on_drift=False).to_case()
    returned = load_project(back, warn_on_drift=False).to_case()
    assert case_digest(original) == case_digest(returned)


def test_converting_to_a_prj_warns_about_what_it_drops(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The lossy direction has to say so: chemistry and the checkboxes do not fit in a .prj."""
    yaml_path = tmp_path / "case.yaml"
    assert main(["convert", str(PROJECT), str(yaml_path)]) == 0
    capsys.readouterr()

    assert main(["convert", str(yaml_path), str(tmp_path / "out.prj")]) == 0
    complaint = capsys.readouterr().err
    assert "cannot carry chemistry" in complaint
    assert "checkboxes" in complaint

    # The safe direction stays quiet.
    capsys.readouterr()
    assert main(["convert", str(PROJECT), str(tmp_path / "again.yaml")]) == 0
    assert "cannot carry" not in capsys.readouterr().err


def test_farfield_runs_standalone(capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "farfield",
            "--dilution",
            "170",
            "--width",
            "110",
            "--distance",
            "200",
            "--current",
            "0.02",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "dilution" in printed and "width" in printed


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["run", "no-such-file.prj"], "no such file"),
        (["run", "README.md"], "unrecognised case file"),
    ],
)
def test_user_errors_are_reported_without_a_traceback(argv, expected, capsys) -> None:  # type: ignore[no-untyped-def]
    """A missing file is the caller's problem; a traceback would bury the one useful line."""
    assert main(argv) == 2
    complaint = capsys.readouterr().err
    assert expected in complaint
    assert "Traceback" not in complaint


def test_output_is_plain_ascii(capsys) -> None:  # type: ignore[no-untyped-def]
    """Windows consoles are cp1252; a stray non-ASCII character raises mid-run."""
    assert main(["info", str(PROJECT)]) == 0
    captured = capsys.readouterr()
    for stream in (captured.out, captured.err):
        stream.encode("ascii")  # raises if anything slipped in
