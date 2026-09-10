"""Command-line entry point.

    plumes2 run CASE [-o DIR] [--samples N] [--units SI|US]
                                               integrate and write a result directory
    plumes2 report CASE [-o FILE] [--units SI|US]
                                               one report, a PDF (or HTML by suffix)
    plumes2 validate [-o FILE]                 run the validation ledger and report it
    plumes2 info CASE                          summarise a case without running it
    plumes2 convert IN OUT                     .prj <-> .yaml
    plumes2 farfield ...                       the standalone Brooks calculator

`CASE` may be either a `.prj` written by the exe or one of our own `.yaml` files; the
extension decides. **They are not equivalent** -- see `convert`, which says so loudly.

⚠️ **Output here is deliberately plain ASCII.** Windows consoles default to cp1252, and a
stray degree sign or arrow raises `UnicodeEncodeError` in the middle of a run rather than
printing badly. Warnings are caught and reprinted as `note:` lines for the same reason:
Python's default warning format writes a source line and a file path that mean nothing to
someone running a model.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

from plumes2 import __version__
from plumes2.display import SYSTEMS

__all__ = ["main"]

_PRJ_SUFFIXES = {".prj"}
_YAML_SUFFIXES = {".yaml", ".yml"}


class _UsageError(Exception):
    """Something the caller can fix, reported without a traceback."""


def _load_case(path: Path):  # type: ignore[no-untyped-def]
    """Read a `.prj` or a `.yaml` into a `Case`, whichever it is."""
    from plumes2.io.project import load_project
    from plumes2.io.yaml_case import load_case

    if not path.exists():
        raise _UsageError(f"no such file: {path}")
    suffix = path.suffix.lower()
    if suffix in _PRJ_SUFFIXES:
        return load_project(path, warn_on_drift=True).to_case()
    if suffix in _YAML_SUFFIXES:
        return load_case(path)
    raise _UsageError(
        f"unrecognised case file {path.name!r}: expected .prj (from the exe) or .yaml (ours)"
    )


def _collect(function, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Run `function`, returning `(value, notes)` with warnings turned into plain text."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        value = function(*args, **kwargs)
    return value, [f"note: {w.message}" for w in caught]


def _command_run(args: argparse.Namespace) -> int:
    from plumes2.results import run, write_results

    source = Path(args.case)
    case, notes = _collect(_load_case, source)
    results, more = _collect(run, case, samples=args.samples, source=source)
    notes += more

    target = Path(args.out) if args.out else source.parent / f"{source.stem}_results"
    write_results(results, target)

    for note in notes:
        print(note, file=sys.stderr)
    frame = results.nearfield
    # Display only: the files written above are SI regardless. `length` is the one dimension the
    # summary reports, so a whole frame conversion would be more machinery than it needs.
    length = SYSTEMS[getattr(args, "units", "SI")].length
    print(f"ran   {source}")
    print(f"wrote {target}")
    print(f"  near field ended after {results.end_time:.1f} s ({results.termination})")
    print(
        f"  dilution {frame['dilution'].iloc[-1]:.1f} at"
        f" {length(frame['depth_m'].iloc[-1]):.2f} {length.suffix} depth"
    )
    # The centreline is the number a mixing-zone limit is quoted against, so it belongs beside
    # the flux average rather than only in the CSV.
    print(
        f"  centreline dilution {frame['centreline_dilution'].iloc[-1]:.1f}"
        f" (peak/mean {frame['peak_to_mean'].iloc[-1]:.3f}"
        f"{', merged' if bool(frame['merged'].iloc[-1]) else ''})"
    )
    print(
        f"  plume diameter {length(frame['plume_diameter_m'].iloc[-1]):.3f} {length.suffix}"
        f"{'' if length.suffix == 'm' else '  (files are SI)'}"
    )
    if results.has_chemistry:
        print(
            f"  pH {frame['ph_total'].iloc[0]:.2f} -> {frame['ph_total'].iloc[-1]:.2f}"
            f", omega_brucite {frame['omega_brucite'].iloc[0]:.3g}"
            f" -> {frame['omega_brucite'].iloc[-1]:.3g}"
        )
        if "omega_brucite_phreeqc" in frame.columns:
            print(
                f"  omega_brucite (PHREEQC) {frame['omega_brucite_phreeqc'].iloc[0]:.3g}"
                f" -> {frame['omega_brucite_phreeqc'].iloc[-1]:.3g}"
            )
        peak = float(frame["omega_brucite"].max())
        if peak > 1.0:
            print(
                f"  note: brucite supersaturated (peak omega {peak:.3g});"
                " upper bound, see PLAN.md 8b"
            )
    return 0


def _command_report(args: argparse.Namespace) -> int:
    """`run` plus a report, or a report straight off an exe `.dat`.

    The `.dat` path is what makes every archived trace and every GUI run reportable -- and it takes
    an optional `--case` because a chemistry trace prints TA and DIC but not the plume salinity and
    temperature the secondary quantities need. See `plumes2.plotframe.from_dat`.
    """
    from plumes2.report import build_report, report_from_dat, write_chemistry_gradient_figures
    from plumes2.results import run

    source = Path(args.case)
    if not source.exists():
        raise _UsageError(f"no such file: {source}")
    target = Path(args.out) if args.out else source.with_suffix(".report.pdf")

    # What the standalone gradient figures are drawn from, when `--gradient-dir` is given: the run
    # on the case path, or the adapted `.dat` (with its case, if one was supplied) otherwise.
    figure_source: object | None = None
    if source.suffix.lower() == ".dat":
        _, notes = _collect(
            report_from_dat, source, target, case_path=args.case_file, units=args.units
        )
        if args.gradient_dir:
            figure_source, more = _collect(_plot_from_dat, source, args.case_file)
            notes += more
    else:
        case, notes = _collect(_load_case, source)
        results, more = _collect(run, case, samples=args.samples, source=source)
        notes += more
        _collect(build_report, results, target, units=args.units)
        figure_source = results

    for note in notes:
        print(note, file=sys.stderr)
    print(f"ran   {source}")
    print(f"wrote {target}")
    if target.suffix.lower() == ".pdf":
        print("  a PDF; open it in any reader")
    else:
        print("  open it in a browser; it needs nothing else")

    if args.gradient_dir and figure_source is not None:
        written, gnotes = _collect(
            write_chemistry_gradient_figures,
            figure_source,
            args.gradient_dir,
            units=args.units,
        )
        for note in gnotes:
            print(note, file=sys.stderr)
        if written:
            for path in written:
                print(f"wrote {path}")
        else:
            print(
                "  no gradient figures: the source carries no case to re-solve the plume "
                "section (a bare .dat needs --case)",
                file=sys.stderr,
            )
    return 0


def _plot_from_dat(dat_path: Path, case_path: str | None):  # type: ignore[no-untyped-def]
    """A `PlotFrame` from an exe `.dat`, with its case when one was supplied.

    The same adaptation `report_from_dat` does internally, exposed so the gradient figures can be
    drawn from a trace as well as from a run.
    """
    from plumes2.io.dat import read_dat
    from plumes2.io.project import load_project
    from plumes2.io.yaml_case import load_case
    from plumes2.plotframe import from_dat

    case = None
    if case_path is not None:
        source = Path(case_path)
        case = (
            load_project(source, warn_on_drift=False).to_case()
            if source.suffix.lower() == ".prj"
            else load_case(source)
        )
    return from_dat(read_dat(dat_path), dat_path, case=case)


def _command_validate(args: argparse.Namespace) -> int:
    """Run every executable ledger target, print the table, and optionally write the report.

    Exits **1** when a target is outside tolerance, so this is usable as a gate. A validation pass
    that reported a failure and still exited 0 would be decoration.
    """
    from plumes2.report.validation import build_validation_report, summary_lines
    from plumes2.validation import Agreement, coverage_by_phase, rows_by_agreement, run_all

    outcomes, notes = _collect(run_all)
    for note in notes:
        print(note, file=sys.stderr)

    print(f"ran   {len(outcomes)} validation targets")
    for line in summary_lines(outcomes):
        print(line)
    passed = sum(outcome.passed for outcome in outcomes)
    executable = sum(count for count, _total in coverage_by_phase().values())
    ledger = sum(total for _count, total in coverage_by_phase().values())
    print(
        f"  {passed}/{len(outcomes)} inside tolerance"
        f"; {executable}/{ledger} numbered ledger rows are executable"
    )
    # Executable is not the same as agreeing, and the fraction above cannot say which. Printed
    # unconditionally and derived, never hand-counted -- a reader who stops at the coverage line
    # would otherwise read 148/154 as 96 % agreement while the near field's largest defect
    # (rows 157b, 186) sits inside the numerator. See `plumes2.validation.Agreement`.
    kinds = rows_by_agreement()
    diverging, defects = kinds[Agreement.DIVERGES], kinds[Agreement.REPRODUCES_DEFECT]
    if diverging:
        print(
            f"  note: {len(diverging)} of those rows are recorded DIVERGENCES, not agreements"
            f" -- rows {', '.join(diverging)}"
        )
    if defects:
        print(
            f"  note: {len(defects)} pass by reproducing a defect in the reference"
            f" -- rows {', '.join(defects)}"
        )
    if args.out:
        print(f"wrote {build_validation_report(args.out, outcomes)}")
    return 0 if passed == len(outcomes) else 1


def _command_info(args: argparse.Namespace) -> int:
    case, notes = _collect(_load_case, Path(args.case))
    for note in notes:
        print(note, file=sys.stderr)
    diffuser, effluent = case.diffuser, case.effluent
    currents = sorted({level.current_speed for level in case.ambient.levels})
    print(f"{args.case}")
    print(f"  ports         {diffuser.n_ports} at {diffuser.port_spacing:g} m spacing")
    print(
        f"  port          {diffuser.port_diameter:g} m, {diffuser.vertical_angle:g} deg "
        f"vertical, {diffuser.horizontal_angle:g} deg horizontal"
    )
    print(f"  depth         {diffuser.port_depth:g} m, seabed at {diffuser.bottom_depth:g} m")
    print(
        f"  flow          {effluent.flow:g} m3/s at {effluent.salinity:g} psu, "
        f"{effluent.temperature:g} C"
    )
    print(
        f"  ambient       {len(case.ambient.levels)} levels, current "
        f"{min(currents):g}-{max(currents):g} m/s"
    )
    print(
        f"  chemistry     {'yes' if case.effluent_chemistry else 'no effluent endmember'}"
        f", ambient {'yes' if case.ambient.has_chemistry else 'no'}"
    )
    print(
        f"  termination   max rise/fall {case.near_field.max_rise_or_fall}, "
        f"stop at surface {case.near_field.stop_at_surface}, "
        f"bottom {case.near_field.stop_at_bottom}"
    )
    # The one place a unit can surprise someone: a `.prj` stores each column in whatever unit
    # its selector says, and the GUI shows that number in that unit. Say which before the GUI does.
    from plumes2.io.prj import read_prj
    from plumes2.io.project import prj_from_case, written_units

    path = Path(args.case)
    if path.suffix.lower() in _PRJ_SUFFIXES:
        stored, label = written_units(read_prj(path)), "stored in the .prj"
    else:
        stored, label = written_units(prj_from_case(case)), "a written .prj would store"
    detail = "; ".join(stored) if stored else "every table in its primary unit (m, MGD, degC)"
    print(f"  units         {label}: {detail}")
    return 0


def _command_convert(args: argparse.Namespace) -> int:
    from plumes2.io.prj import write_prj
    from plumes2.io.project import prj_from_case
    from plumes2.io.yaml_case import dump_case

    source, target = Path(args.source), Path(args.target)
    case, notes = _collect(_load_case, source)
    for note in notes:
        print(note, file=sys.stderr)

    suffix = target.suffix.lower()
    if suffix in _YAML_SUFFIXES:
        dump_case(case, target)
    elif suffix in _PRJ_SUFFIXES:
        write_prj(prj_from_case(case), target)
        # The one lossy direction, and it is lossy in a way that bites silently.
        print(
            "warning: a .prj cannot carry chemistry, the stop-at checkboxes, or the output"
            "\n         variable selection. Those stay in the .yaml and must be re-entered"
            "\n         in the GUI. See PLAN.md section 7b.",
            file=sys.stderr,
        )
    else:
        raise _UsageError(f"cannot write {target.name!r}: expected a .prj or .yaml target")
    print(f"{source} -> {target}")
    return 0


def _command_farfield(args: argparse.Namespace) -> int:
    from plumes2.farfield.standalone import StandaloneRequest, independent_farfield

    request = StandaloneRequest(
        initial_dilution=args.dilution,
        initial_width=args.width,
        mixing_zone_distance=args.distance,
        current_speed=args.current,
        decay_per_day=args.decay,
    )
    frame = independent_farfield(request)
    print(frame.to_string(index=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plumes2",
        description="PLUMES2.0 outfall plume model, re-implemented in Python.",
    )
    parser.add_argument("--version", action="version", version=f"plumes2 {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="integrate a case and write a result directory")
    run_parser.add_argument("case", help="a .prj from the exe, or one of our .yaml files")
    run_parser.add_argument("-o", "--out", help="output directory (default: CASE_results)")
    run_parser.add_argument("--samples", type=int, default=200, help="output rows (default: 200)")
    # ⚠️ Display only. The CSVs stay SI whatever this says -- see `plumes2.display`.
    run_parser.add_argument(
        "--units",
        choices=sorted(SYSTEMS),
        default="SI",
        help="units for the printed summary; the written files are always SI (default: SI)",
    )
    run_parser.set_defaults(handler=_command_run)

    report_parser = sub.add_parser("report", help="write one report, a PDF or (by suffix) HTML")
    report_parser.add_argument(
        "case", help="a .prj or .yaml to run, or a .dat the exe already wrote"
    )
    report_parser.add_argument(
        "-o", "--out", help="output file, .pdf or .html (default: CASE.report.pdf)"
    )
    report_parser.add_argument("--samples", type=int, default=200, help="rows (default: 200)")
    report_parser.add_argument(
        "--units", choices=sorted(SYSTEMS), default="SI", help="display units (default: SI)"
    )
    # Only meaningful for a .dat: it unlocks the carbonate secondaries the exe never printed.
    report_parser.add_argument(
        "--case-file",
        dest="case_file",
        help="for a .dat: the .prj or .yaml behind it, which unlocks the chemistry secondaries",
    )
    report_parser.add_argument(
        "--gradient-dir",
        dest="gradient_dir",
        help="also write standalone pH/aragonite/calcite/brucite gradient figures (PNG+SVG) here",
    )
    report_parser.set_defaults(handler=_command_report)

    validate_parser = sub.add_parser(
        "validate", help="run the validation ledger; exits 1 if any target is out of tolerance"
    )
    validate_parser.add_argument(
        "-o", "--out", help="also write the validation report here (.pdf or .html)"
    )
    validate_parser.set_defaults(handler=_command_validate)

    info_parser = sub.add_parser("info", help="summarise a case without running it")
    info_parser.add_argument("case")
    info_parser.set_defaults(handler=_command_info)

    convert_parser = sub.add_parser("convert", help="convert between .prj and .yaml")
    convert_parser.add_argument("source")
    convert_parser.add_argument("target")
    convert_parser.set_defaults(handler=_command_convert)

    ff = sub.add_parser("farfield", help="the standalone Brooks far-field calculator")
    ff.add_argument("--dilution", type=float, required=True, help="initial dilution")
    ff.add_argument("--width", type=float, required=True, help="initial wastefield width, m")
    ff.add_argument("--distance", type=float, required=True, help="mixing zone distance, m")
    ff.add_argument("--current", type=float, required=True, help="current speed, m/s")
    ff.add_argument("--decay", type=float, default=0.0, help="first-order decay, 1/day")
    ff.set_defaults(handler=_command_farfield)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return int(args.handler(args))
    except _UsageError as error:
        print(f"plumes2: {error}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as error:
        # Bad inputs and unreadable files are the caller's problem, not a bug; a traceback
        # here would bury the one line that matters.
        print(f"plumes2: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
