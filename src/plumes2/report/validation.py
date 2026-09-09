"""The validation report: every executable claim, our value, the reference, and the error.

Phase 7's deliverable, and it reuses the standard report's page rather than inventing a second
look: same validated palette, same self-contained single file, same escaping. A validation report
is a table document rather than a figure document, so its panels carry no figure -- see
`page._panel_html`, which renders a table-only panel with its table open instead of folded away,
and `pdf._section`, which does the same on paper. Like the run report it is a PDF or an HTML file
by the suffix of the path it is written to.

⚠️ **A pass here is not a claim of correctness, and the report says so.** Three things are
deliberately visible on the page: which targets rest on the exe rather than on a manual or an
independent implementation (`Evidence`), which are *recorded disagreements* rather than matches,
and how much of the ledger is executable at all. A validation report that showed ten green rows
without saying there are two hundred more claims would be worse than no report.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from plumes2 import __version__
from plumes2.provenance import git_state
from plumes2.report import write_document
from plumes2.report.page import Header, render_page
from plumes2.report.panels import Panel
from plumes2.validation import (
    LEDGER_ROWS_WITH_NUMBERS,
    TARGETS,
    Agreement,
    Evidence,
    Outcome,
    coverage_by_phase,
    rows_by_agreement,
    run_all,
)

__all__ = ["build_validation_report", "render_validation"]

_PHASE_NAMES = {
    1: "Data model and legacy I/O",
    2: "Seawater and ambient",
    3: "Brooks far field",
    4: "Chemistry",
    5: "Near-field UM3",
    6: "Output and the cross-plume profile",
    7: "Validation and docs",
    8: "Beyond parity",
}

_EVIDENCE_BLURB = {
    Evidence.GOLDEN: "a number printed by the executable itself -- an independent implementation",
    Evidence.MANUAL: "a number printed in a manual, which for this project is weaker: the "
    "manual's own worked example disagrees with the shipped trace",
    Evidence.EXTERNAL: "an independent third-party implementation or a published check value",
    Evidence.INTERNAL: "no external reference exists; an analytical limit or a regression guard",
}


def _rows(outcomes: list[Outcome]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "row": outcome.target.row,
                "claim": outcome.target.claim,
                "ours": outcome.ours,
                "reference": outcome.target.reference,
                "error": outcome.absolute,
                "tolerance": outcome.target.tolerance,
                "unit": outcome.target.unit or "--",
                "evidence": str(outcome.target.evidence),
                "means": str(outcome.target.agreement),
                "result": "pass" if outcome.passed else (outcome.error or "FAIL"),
            }
            for outcome in outcomes
        ]
    )


def _phase_panel(phase: int, outcomes: list[Outcome]) -> Panel:
    executable, total = coverage_by_phase()[phase]
    failures = [outcome for outcome in outcomes if not outcome.passed]
    name = _PHASE_NAMES.get(phase, f"Phase {phase}")
    verdict = (
        "Every target in this phase is inside its tolerance."
        if not failures
        else f"{len(failures)} of {len(outcomes)} targets are outside tolerance: "
        + ", ".join(f"row {outcome.target.row}" for outcome in failures)
        + "."
    )
    return Panel(
        key=f"phase-{phase}",
        title=f"Phase {phase} \N{EN DASH} {name}",
        explanation=(
            f"{executable} of the {total} numbered ledger rows in this phase "
            f"{'is' if executable == 1 else 'are'} executable here, running on every invocation "
            f"rather than being copied from a note. {verdict} "
            "Each row's tolerance comes from what its reference can resolve -- printed decimals, "
            "or a stated acceptance bar -- rather than from what the code happens to produce."
        ),
        svg="",
        table=_rows(outcomes),
        notes=tuple(
            f"Row {outcome.target.row}: {outcome.target.note}"
            for outcome in outcomes
            if outcome.target.note
        ),
    )


def _validation_document(outcomes: list[Outcome] | None) -> tuple[Header, list[Panel]]:
    """The validation report's header and panels -- everything but the format."""
    results = outcomes if outcomes is not None else run_all()
    passed = sum(outcome.passed for outcome in results)
    executable = sum(count for count, _total in coverage_by_phase().values())
    ledger = sum(len(rows) for rows in LEDGER_ROWS_WITH_NUMBERS.values())
    # Derived, never hand-counted: the caveat below used to read "in two places" and was already
    # wrong at three. A stale hand count is this project's most-repeated defect.
    kinds = rows_by_agreement()
    diverging = kinds[Agreement.DIVERGES]
    defects = kinds[Agreement.REPRODUCES_DEFECT]

    by_phase: dict[int, list[Outcome]] = {}
    for outcome in results:
        by_phase.setdefault(outcome.target.phase, []).append(outcome)

    panels = [
        Panel(
            key="how-to-read-this",
            title="How to read this",
            explanation=(
                "Each row is one claim from the project ledger, measured now. `ours` is what this "
                "code produced on this run; `reference` is a number from outside it. A row passes "
                "when the absolute error is inside a tolerance set by what its reference can "
                "resolve. Read the `evidence` column before the `result` column: they answer "
                "different questions, and a pass against a weak reference is weaker than a pass "
                "against a strong one."
            ),
            svg="",
            table=pd.DataFrame(
                [
                    {"evidence": str(kind), "what it means": blurb}
                    for kind, blurb in _EVIDENCE_BLURB.items()
                ]
            ),
            notes=(
                f"\N{WARNING SIGN} **{len(diverging)} of these rows are recorded divergences, not "
                f"matches** \N{EM DASH} rows "
                + ", ".join(diverging)
                + ". The number each one pins *is the size of a gap*, held fixed so that a change "
                "is a test failure; passing means the disagreement is still the size we recorded, "
                "not that there is none. Read the `means` column: rows 157b and 186 are the near "
                "field's largest open defect and they are inside the coverage count below.",
                f"A further {len(defects)} rows (" + ", ".join(defects) + ") pass by reproducing "
                "something *wrong in the reference itself*, behind a named flag that defaults to "
                "the corrected behaviour. That is parity, not correctness.",
                f"{executable} of the {ledger} numbered ledger rows are executable here. The rest "
                "are claims whose measurement is a whole-table comparison living in a dedicated "
                "test, or which record a decision rather than a number. This is a tranche. "
                "\N{WARNING SIGN} **Executable is not the same as agreeing**, which is what the "
                "two notes above are for.",
            ),
        )
    ]
    panels += [_phase_panel(phase, by_phase[phase]) for phase in sorted(by_phase)]

    commit, dirty = git_state()
    stamp = f"plumes2 {__version__}"
    if commit:
        stamp += f" \N{BULLET} commit {commit[:12]}{' (dirty tree)' if dirty else ''}"
    header = Header(
        title="plumes2 \N{EN DASH} validation report",
        subtitle=(
            f"{passed} of {len(results)} executable targets inside tolerance, across "
            f"{len(by_phase)} phases. Every number below was measured on this run."
        ),
        stamp=stamp,
        kpis=(
            ("Targets run", str(len(results)), ""),
            ("Inside tolerance", str(passed), ""),
            ("Outside", str(len(results) - passed), ""),
            ("Ledger rows executable", f"{executable}/{ledger}", ""),
            # Beside the coverage fraction, because it is the fraction that gets misread.
            ("Recorded divergences", str(len(diverging)), "inside that count"),
        ),
        caveats=(
            "A pass is evidence that a number has not moved, not proof that the physics is right. "
            "Where the only available reference is the executable we are re-implementing, "
            f"agreement means we reproduce it -- including, in {len(defects)} places, deliberately "
            "reproducing its mistakes.",
            f"\N{WARNING SIGN} {executable}/{ledger} is a coverage fraction, not an agreement "
            f"fraction. {len(diverging)} of those rows are measured *disagreements*, rows 157b "
            "and 186 among them, and they count as executable because they are measured.",
        ),
    )
    return header, panels


def render_validation(outcomes: list[Outcome] | None = None) -> str:
    """The validation report as an HTML string."""
    header, panels = _validation_document(outcomes)
    return render_page(header, panels, footer=_FOOTER)


_FOOTER = (
    "Generated by plumes2. The registry behind this page is `plumes2.validation`, which is also "
    "what `tests/test_validation.py` asserts against -- so this report and the test suite cannot "
    "disagree about what was measured."
)


def build_validation_report(path: str | Path, outcomes: list[Outcome] | None = None) -> Path:
    """Write the validation report to `path` -- PDF or HTML by suffix -- and return it."""
    header, panels = _validation_document(outcomes)
    return write_document(header, panels, path, footer=_FOOTER)


def summary_lines(outcomes: list[Outcome]) -> list[str]:
    """One plain-ASCII line per target, for the CLI.

    ASCII because Windows consoles are cp1252 -- the same constraint `plumes2.cli` documents. The
    written report is where the arrows and Greek live.
    """
    lines = []
    for outcome in outcomes:
        mark = "ok  " if outcome.passed else "FAIL"
        lines.append(
            f"  {mark} p{outcome.target.phase} row {outcome.target.row:<4} "
            f"{outcome.ours:>12.5g} vs {outcome.target.reference:<12.5g} "
            f"err {outcome.absolute:.3g} / tol {outcome.target.tolerance:.3g}  "
            f"{outcome.target.claim[:52]}"
        )
    return lines


assert set(_PHASE_NAMES) >= {target.phase for target in TARGETS}, "a phase has no name"
