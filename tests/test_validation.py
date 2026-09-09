"""The executable ledger, asserted.

Deliberately thin: the claims, the references and the tolerances all live in `plumes2.validation`,
and this module only drives them. The per-module tests elsewhere stay as they are -- they check far
more than the headline number of each claim, and this is not a replacement for them.

⚠️ **The tolerances are not adjustable from here.** If a target starts failing, the fix is in the
code or -- if the reference turns out to be wrong -- in the registry with a note saying so. Widening
a tolerance in a test file to make a red row green is how a validation suite stops meaning anything.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

import pytest

from plumes2.report.validation import (
    build_validation_report,
    render_validation,
    summary_lines,
)
from plumes2.validation import (
    LEDGER_ROWS_WITH_NUMBERS,
    ROWS_DISAGREEING_WITH_THEMSELVES,
    TARGETS,
    Agreement,
    Evidence,
    Outcome,
    Target,
    coverage_by_phase,
    ledger_row_of,
    measure,
    rows_by_agreement,
)


@pytest.mark.golden
@pytest.mark.parametrize("target", TARGETS, ids=lambda t: f"p{t.phase}-row{t.row}")
def test_the_ledger_target_still_holds(target: Target, ledger_outcomes) -> None:  # type: ignore[no-untyped-def]
    """Every ledger row, against its own tolerance.

    ⚠️ The measurement comes from the session fixture rather than a `measure()` call here, because
    this test and the two registry consumers below used to run the whole registry independently --
    three passes, 18 % of the suite's clock, all deriving the same numbers. Nothing about the
    assertion changed: one row, one tolerance, one verdict.
    """
    outcome = ledger_outcomes[target.row]
    assert outcome.error is None, outcome.error
    assert outcome.passed, (
        f"row {target.row}: ours {outcome.ours!r} vs reference {target.reference!r}, "
        f"error {outcome.absolute:.6g} exceeds tolerance {target.tolerance:.6g}"
    )


# ------------------------------------------------------------------ the registry's own shape


def test_every_target_is_well_formed() -> None:
    for target in TARGETS:
        assert target.row, target.claim
        assert target.phase in LEDGER_ROWS_WITH_NUMBERS, f"row {target.row} has an unknown phase"
        assert target.tolerance >= 0.0, target.row
        assert len(target.claim.split()) >= 4, f"row {target.row}: the claim is not a sentence"


def test_no_two_targets_share_a_row_number() -> None:
    """A duplicated row would make the report ambiguous about which claim was measured."""
    rows = [target.row for target in TARGETS]
    assert len(rows) == len(set(rows)), sorted(rows)


def test_every_target_says_why_its_tolerance_is_what_it_is() -> None:
    """A tolerance without a stated basis is a number chosen to pass."""
    for target in TARGETS:
        assert target.note, f"row {target.row} has no note"
        assert len(target.note.split()) >= 10, f"row {target.row}: the note is too thin"


def test_a_weak_reference_is_labelled_as_one() -> None:
    """`internal` means no external reference exists, which the report has to be able to say."""
    internal = [t for t in TARGETS if t.evidence is Evidence.INTERNAL]
    assert internal, "brucite has no reference implementation, so at least one target is internal"
    for target in internal:
        assert "no reference" in target.note.lower() or "regression" in target.note.lower()


#: This project's own vocabulary for "the number below is a gap, not a match". Matched against the
#: claim and the note together, because either is where a reader would find out.
#:
#: ⚠️ A tripwire, not the definition -- `Target.agreement` is the authority, and this only asserts
#: that a target cannot *say* it diverges while the totals count it as agreement. Widen it when a
#: new phrasing appears; `past upstream` was added after row 171c said the same thing as 171d in
#: different words, 0.52 % against the same 0.5 % bar.
_DIVERGENCE_PHRASES = (
    "recorded divergence",
    "recorded discrepancy",
    "not an achievement",
    "past upstream",
)


def test_a_recorded_divergence_is_labelled_as_one() -> None:
    """⚠️⚠️ The fifth instance of this ledger's recurring failure, now guarded.

    `Evidence` says how strong a target's *reference* is; it deliberately says nothing about how
    strong the *agreement* is. Nothing else did either, so five rows whose measured number **is
    the size of a gap** were counted, coloured and totalled exactly like a 1e-5 match, and
    `148/154 numbered ledger rows are executable` read as 96 % agreement to anyone who did not
    open the notes. Rows 157b and 186 -- merging 15-29 % wrong past `d/L` 4, the merged radius
    running away 11.9x -- are the near field's largest open defect and they sat inside the
    numerator with nothing on the page to say so.

    ⚠️ **Nothing caught it because nothing was wrong with the numbers.** Every one of those five
    notes spells the divergence out in its first sentence. The defect was that the prose and the
    arithmetic were in different places, so a reader could take the total without the caveats --
    which is the same shape as the stale hand count, the target-against-row numerator, the
    numerator that folded sub-lettered rows, and the buckets that disagreed with their headings.

    The guard runs **both** ways, which is the part that matters. Prose without the field is a
    divergence the totals miss; the field without prose is a scarlet letter with no explanation.
    """
    for target in TARGETS:
        says = any(
            phrase in f"{target.claim} {target.note}".lower() for phrase in _DIVERGENCE_PHRASES
        )
        declares = target.agreement is Agreement.DIVERGES
        assert says == declares, (
            f"row {target.row}: note says divergence={says} but agreement={target.agreement}. "
            "Set agreement=Agreement.DIVERGES and say so in the note, or neither."
        )


def test_reproducing_a_defect_is_not_filed_as_a_match() -> None:
    """A pass earned by copying the reference's mistake is parity, not correctness.

    These three are the ones PLAN's Phase 7 notes describe as passing "by reproducing something we
    chose to document rather than fix" -- the `Omega < 1` NaN, UM3's `arctan` bug, and the
    undiluted far-field BOD. Each is behind a named `reproduce_*` flag defaulting to the corrected
    behaviour, and each must say which, so the report cannot present it as agreement on the physics.
    """
    defects = rows_by_agreement()[Agreement.REPRODUCES_DEFECT]
    assert defects, "at least the arctan bug and the undiluted BOD are reproduced deliberately"
    for target in TARGETS:
        if target.agreement is not Agreement.REPRODUCES_DEFECT:
            continue
        text = f"{target.claim} {target.note}".lower()
        assert "reproduce" in text or "faithful" in text, (
            f"row {target.row} claims to reproduce a defect but its note never names the switch"
        )


def test_a_row_in_two_buckets_is_one_we_named() -> None:
    """Agreement belongs to a target, so a row carrying several can hold more than one verdict.

    Row 17 does, legitimately: case01's jet phase matches to 0.46 % while its post-trapping window
    drifts to 1.7 %, and splitting the row into windows is exactly the correction Phase 7's first
    act made. What must not happen is a *new* row quietly acquiring two verdicts, because then the
    headline count of divergences is smaller than the number of diverging claims.
    """
    kinds = rows_by_agreement()
    seen: dict[str, list[str]] = {}
    for kind, rows in kinds.items():
        for row in rows:
            seen.setdefault(row, []).append(str(kind))
    doubled = {row: k for row, k in seen.items() if len(k) > 1}
    assert set(doubled) == set(ROWS_DISAGREEING_WITH_THEMSELVES), (
        f"rows in more than one agreement bucket: {doubled}. Either split the ledger row or add "
        "it to ROWS_DISAGREEING_WITH_THEMSELVES with a reason."
    )
    # The union has to be the coverage numerator, or one of the two is counting something else.
    covered = {ledger_row_of(t.row, t.phase) for t in TARGETS}
    assert set(seen) == covered
    assert len(covered) == sum(count for count, _total in coverage_by_phase().values())


def test_the_divergences_reach_the_page() -> None:
    """A number that only the registry knows is the defect this whole guard exists to prevent.

    Rendered from outcomes stubbed at their own references rather than from `run_all`, so this
    checks the *page* and costs nothing: whether the physics currently agrees is what the
    parametrised target test is for, and it must not be a precondition for the page saying that
    four of these rows are not agreements at all.
    """
    diverging = rows_by_agreement()[Agreement.DIVERGES]
    assert {"157b", "186"} <= set(diverging)

    from plumes2.validation import Outcome

    html = render_validation([Outcome(target=t, ours=t.reference) for t in TARGETS])
    assert "recorded divergences, not" in html
    assert "not an agreement fraction" in html
    assert "Recorded divergences" in html, "the KPI row must carry it beside the coverage fraction"
    for row in diverging:
        assert row in html, f"row {row} is a recorded divergence and must be named on the page"


def test_coverage_is_reported_rather_than_implied() -> None:
    """A tranche presented as the whole ledger would be worse than no report at all."""
    coverage = coverage_by_phase()
    assert set(coverage) == set(LEDGER_ROWS_WITH_NUMBERS)
    for phase, (executable, total) in coverage.items():
        assert executable <= total, f"phase {phase} claims more targets than it has ledger rows"
    # ⚠️ Rows, not targets. Several ledger rows carry more than one target -- row 171 has five,
    # one per current in the sweep -- so the numerator is the number of distinct rows covered and
    # is legitimately smaller than len(TARGETS). Counting targets against a denominator of rows is
    # what made phase 5 read 25/49 when 25 targets covered 16 rows.
    #
    # ⚠️ And the row a target counts as comes from `ledger_row_of`, not from stripping a
    # letter: `157b` is a ledger row in its own right while `171a` is ours. Stripping
    # unconditionally is what made the numerator understate against this same denominator until
    # 2026-08-20, so this assertion has to use the same resolution the numerator does or it just
    # re-pins the bug.
    covered = {ledger_row_of(t.row, t.phase) for t in TARGETS}
    assert sum(e for e, _t in coverage.values()) == len(covered)
    # ⚠️ Until 2026-08-25 this read `<`: "this is explicitly a first tranche, and the report must
    # not pretend otherwise". Row 258c was the last open countable row, and closing it made the
    # numerator equal the denominator -- so the guard is now that the numerator can never *exceed*
    # it (a target citing a row the ledger does not count), and that the figure is derived from the
    # ledger rather than typed, which `test_the_published_coverage_figures_are_not_stale` holds.
    assert sum(e for e, _t in coverage.values()) <= sum(
        len(rows) for rows in LEDGER_ROWS_WITH_NUMBERS.values()
    )


def test_a_failing_measurement_is_reported_not_raised() -> None:
    """A pass that dies on target three tells you nothing about the other twelve."""

    def explode() -> float:
        raise RuntimeError("deliberate")

    broken = Target(
        row="test",
        phase=1,
        evidence=Evidence.INTERNAL,
        claim="a target whose measurement raises",
        source="none",
        measure=explode,
        reference=0.0,
        tolerance=0.0,
        note="only used here, to prove a raising measurement is caught and reported",
    )
    outcome = measure(broken)
    assert not outcome.passed
    assert outcome.error is not None and "deliberate" in outcome.error


# ------------------------------------------------------------------ the report over it


def _in_ledger_order(outcomes: dict[str, object]) -> list:  # type: ignore[type-arg]
    """The fixture's rows in the order `run_all` would have produced them.

    Both consumers render in this order, so it is part of what they assert. Sorting here rather
    than storing a list keeps the fixture keyed by row, which is what the per-row test needs.
    """
    return [
        outcomes[row]
        for row in sorted(outcomes, key=lambda r: (outcomes[r].target.phase, r))  # type: ignore[attr-defined]
    ]


def test_the_report_is_built_from_the_same_registry(ledger_outcomes) -> None:  # type: ignore[no-untyped-def]
    """One registry, two consumers: the page must not be able to disagree with the suite.

    ⭐ It now cannot even in principle. This used to re-run `run_all()` -- a second independent
    pass that *could* have disagreed with the suite's own, and cost 45 s to prove it did not. Both
    consumers and the per-row assertions read one measurement, so agreement is structural.
    """
    outcomes = _in_ledger_order(ledger_outcomes)
    html = render_validation(outcomes)

    assert html.startswith("<!doctype html>")
    assert "<script" not in html
    # Escaped, because the claims contain apostrophes and the page escapes everything it
    # interpolates -- which this assertion incidentally confirms.
    for outcome in outcomes:
        assert escape(outcome.target.claim) in html, outcome.target.row
    # The coverage gap and the "a pass is not proof" caveat are both required on the page.
    assert "This is a tranche." in html
    assert "not proof that the physics is right" in html


def test_the_cli_summary_is_plain_ascii(ledger_outcomes) -> None:  # type: ignore[no-untyped-def]
    """Windows consoles are cp1252, the same constraint the rest of the CLI is held to."""
    for line in summary_lines(_in_ledger_order(ledger_outcomes)):
        line.encode("ascii")


# ------------------------------------------------------------------ the denominator itself


#: Rows in `LEDGER.md` carrying a numeric phase cell, as of 2026-09-09 (row 286 added -- case55,
#: the site case; before it rows 284, 284b and 285 for case53 and case54). Three rows
#: are filed under "—" and are not counted here. Not the same as
#: `LEDGER_ROWS_WITH_NUMBERS`, which counts only the rows carrying a *number* and is the honest
#: denominator for coverage -- this one is mechanical, and exists purely to notice growth.
LEDGER_TABLE_ROWS = 320


def _ledger_rows() -> dict[str, list[int]]:
    """`row number -> phases it is filed under`, parsed straight from `LEDGER.md`."""
    import re

    from tests.conftest import REPO_ROOT

    pattern = re.compile(r"^\| (\d+[a-z]?) \|.*\|\s*([0-9, ]+)\s*\|\s*$")
    rows: dict[str, list[int]] = {}
    text = (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8")
    for line in text.split("\n"):
        matched = pattern.match(line)
        if matched:
            rows[matched.group(1)] = [int(n) for n in re.findall(r"\d+", matched.group(2))]
    return rows


def test_every_target_points_at_a_real_ledger_row() -> None:
    """A target citing a row that does not exist sends the reader of the report nowhere.

    Suffixed rows come in two kinds, and until 2026-08-25 this test could not tell them apart:
    `171a` is ours (one ledger row split into the arms it covers) and is checked against its stem,
    but `157b` and `258c` are ledger rows in their own right and must be checked as themselves.
    Stemming unconditionally passed `258b` against row 258's phases by luck and failed `258c`
    (phase 4, where row 258 is 3 and 5) the day it became executable -- the same folding
    `ledger_row_of` was written to stop in the numerator.
    """
    rows = _ledger_rows()
    assert len(rows) > 200, f"the ledger parse found only {len(rows)} rows; has the format changed?"
    for target in TARGETS:
        row = target.row if target.row in rows else target.row.rstrip("abcde")
        assert row in rows, f"target row {target.row} is not in LEDGER.md"
        assert target.phase in rows[row], (
            f"target row {target.row} is filed under phase {target.phase}, "
            f"but the ledger files it under {rows[row]}"
        )


def _countable_rows_by_phase() -> dict[int, frozenset[str]]:
    """Recompute `LEDGER_ROWS_WITH_NUMBERS` from `LEDGER.md` by the rule its docstring states.

    One row counts once, under the phase its target claims or else the first phase the ledger
    lists; it counts if it states a number once bare cross-references are stripped, or if it
    already has a target.
    """
    import re

    from tests.conftest import REPO_ROOT

    # ⚠️ The whole file, not a slice of a bigger one. That is the point of the 2026-08-19 move:
    # `| 3 |` and `| 6 |` also open ordinary prose tables in PLAN.md, and bounding the parse by
    # section headings was the same fragility that let bulk edits overwrite real rows twice.
    section = (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8")
    pattern = re.compile(r"^\| (\d+[a-z]?) \| (.*?) \| (.*?) \| ([^|]*) \| ([^|]*) \|\s*$")
    # A bare reference is a label, not a quantity: "row 118", "case09", "eq 23", a section.
    references = re.compile(
        # The ledger writes ranges with an en dash and sections with a section sign. Both are
        # escaped rather than written literally, because as literals they read as a hyphen and
        # an S to anyone scanning the pattern -- which is what ruff's look-alike rule objects to.
        "rows? \\d+(\\s*[-\\u2013,]\\s*\\d+)*"
        "|case\\d+|test\\d+"
        "|\\u00a7\\s*[\\d.]+|eqs? [\\d\\-\\u2013, ]+"
    )
    # ⚠️ **Resolved the same way the numerator resolves it, and for the same reason.** A bare
    # `rstrip("abcde")` collides `258b` with `258` -- two ledger rows, in different phases, whose
    # targets then overwrite each other in this dict and move a row between phases at random. That
    # is the 2026-08-20 numerator defect wearing a different hat, so an exact match wins and the
    # stem is only a fallback for our own splits (`171a`, `17b`), which are not ledger rows.
    exact = {target.row: target.phase for target in TARGETS}
    stems: dict[str, int] = {}
    for target in TARGETS:
        stems.setdefault(target.row.rstrip("abcde"), target.phase)
    claimed = stems | exact

    counts: dict[int, set[str]] = {}
    for line in section.split(chr(10)):
        matched = pattern.match(line)
        if not matched:
            continue
        row, target_text, value, _source, phase_text = matched.groups()
        phases = [int(n) for n in re.findall(r"\d+", phase_text)]
        primary = claimed.get(row, phases[0] if phases else None)
        if primary is None:
            continue
        # ⊘-marked rows cannot become targets and are excluded from the denominator, so a phase
        # can reach 100 % honestly. See the ledger header for the four reasons allowed.
        if "Not executable" in value and row not in claimed:
            continue
        countable = bool(re.search(r"\d", references.sub(" ", f"{target_text} {value}")))
        if countable or row in claimed:
            counts.setdefault(primary, set()).add(row)
    return {phase: frozenset(rows) for phase, rows in counts.items()}


def test_the_ledger_denominator_matches_the_ledger() -> None:
    """⚠️ The thing this project got wrong three times, now checked rather than trusted.

    `LEDGER_ROWS_WITH_NUMBERS` was hand-counted until 2026-08-18 and was wrong by 42 % -- 156
    against a real 222, with phase 5 recorded as 41 against **84**. Every coverage figure published
    before then flattered, phase 5 by a factor of two.

    Hand-counting was chosen so the denominator could not track the numerator. What it produced was
    a number nobody could reproduce, which drifted silently three times. Deriving it from an
    explicit rule keeps the original protection -- the rule reads the ledger, never the registry,
    so implementing a target cannot shrink it -- while making the number checkable.
    """
    derived = _countable_rows_by_phase()
    assert derived == LEDGER_ROWS_WITH_NUMBERS, (
        f"the ledger now implies {dict(sorted(derived.items()))}, against a pinned "
        f"{dict(sorted(LEDGER_ROWS_WITH_NUMBERS.items()))}. Update the constant in the same commit "
        f"that changed the ledger."
    )


NOT_EXECUTABLE_TAGS = ("subsumed", "documentary", "downgraded", "no input")


def _ledger_buckets() -> dict[str, tuple[str, str, bool]]:
    """`row -> (section, bucket, carries the not-executable tag)`, parsed from `LEDGER.md`.

    The bucket comes from the nearest `###` heading above the row, which is how a reader sees it.
    """
    from tests.conftest import REPO_ROOT

    marks = {"✅": "measured", "⏳": "open", "⊘": "notexec"}
    section = bucket = None
    found: dict[str, tuple[str, str, bool]] = {}
    for line in (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8").split(chr(10)):
        if line.startswith("## "):
            section, bucket = line[3:].strip(), None
        elif line.startswith("### "):
            # ⚠️ The **leading** mark, not any mark in the line. A completion note like
            # "⏳ Open (2) -- ✅ complete" carries two, and matching whichever came first in the
            # dict read the bucket as Measured and mislabelled everything under it. Found by this
            # test firing on phase 6, which is what it is for -- but it was this test's own bug.
            bucket = marks.get(line[4:].lstrip()[:1])
        elif line.startswith("| ") and bucket and section:
            row = line.split("|")[1].strip()
            if row and row != "#" and set(row) - set("-"):
                found.setdefault(row, (section, bucket, "Not executable" in line))
    return found


def test_every_row_sits_in_the_bucket_its_own_text_claims() -> None:
    """⚠️ The fourth instance of this ledger's recurring failure, now guarded.

    A row's bucket is presentation and its tag is identity, and until 2026-08-20 nothing checked
    that they agreed. Ten phase-5 rows disagreed: five carried the ⊘ tag while sitting under
    ⏳ Open (69, 168, 176, 191l, 191p, classified in text but never moved), and five had live
    targets and were still filed Open (51, 104, 171, 182, 191o -- each one moved there by the commit
    that measured it, which updated the row and not its section).

    ⚠️ **Nothing caught it because nothing was wrong with the numbers.** The derived
    denominator reads each row's tag, never its heading, so coverage was right throughout while the
    page said Measured (28) / Open (25) where the truth was 33 and 15. That is the whole failure
    mode this ledger keeps hitting -- a figure that is correct and a presentation of it that is
    not -- and it is the same shape as the stale hand count, the target-against-row numerator, and
    the numerator that folded sub-lettered rows.

    The rule is exactly three lines, which is the point: a row carrying the tag belongs under
    ⊘; a row a target measures belongs under ✅; everything else is ⏳.
    """
    from plumes2.validation import TARGETS, ledger_row_of

    measured = {ledger_row_of(target.row, target.phase) for target in TARGETS}
    wrong = []
    for row, (section, bucket, tagged) in sorted(_ledger_buckets().items()):
        expected = "notexec" if tagged else ("measured" if row in measured else "open")
        if expected != bucket:
            wrong.append(f"row {row} ({section}) is filed {bucket} but should be {expected}")
    assert not wrong, "the ledger's buckets disagree with its rows:" + chr(10) + chr(10).join(wrong)


def test_every_row_sits_under_a_phase_it_claims() -> None:
    """A row filed under a phase its own Phase cell does not list sends the reader astray.

    ⚠️ Two rows did, until 2026-08-20: `258b` and `258c` sat in the **Phase 3** section beside
    their parent row 258, while declaring phases 5 and 4 -- which is where the derived denominator
    had been counting them all along. So the page and the arithmetic disagreed about where two
    findings belonged, silently, for as long as they had existed.

    Keeping a sub-row beside its parent is good for reading, and it is exactly why this needs a
    test rather than a convention: row 258 is genuinely a far-field finding, its two children are
    not, and nothing but a check will notice when those come apart.

    A row may declare **several** phases -- 26 do -- and then it belongs under any one of them.
    What it may not do is sit under a phase it never claimed.
    """
    import re

    from tests.conftest import REPO_ROOT

    marks = ("✅", "⏳", "⊘")
    section: str | None = None
    bucketed = False
    wrong = []
    for line in (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8").split(chr(10)):
        if line.startswith("## "):
            section, bucketed = line[3:].strip(), False
        elif line.startswith("### "):
            bucketed = line[4:].lstrip()[:1] in marks
        elif line.startswith("| ") and bucketed and section:
            cells = line.split("|")
            row = cells[1].strip()
            if not row or row == "#" or not set(row) - set("-"):
                continue
            heading = re.match(r"Phase (\d+)", section)
            declared = [int(n) for n in re.findall(r"\d+", cells[-2])]
            if heading and declared and int(heading.group(1)) not in declared:
                wrong.append(f"row {row} is under {section} but declares {declared}")
    assert not wrong, "rows filed under a phase they do not claim:" + chr(10) + chr(10).join(wrong)


def test_every_bucket_heading_counts_its_own_rows() -> None:
    """A heading saying Measured (28) over 33 rows is a claim about coverage, and it was wrong.

    Pinned separately from the rule above because the two fail for different reasons: that one
    catches a row in the wrong place, this one catches a *count* left behind when a row moved. Both
    happened on 2026-08-20, in the same ten rows.
    """
    import re

    from tests.conftest import REPO_ROOT

    marks = ("✅", "⏳", "⊘")
    heading = None
    seen = 0
    wrong = []
    body = (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8").split(chr(10))
    # A sentinel so the final bucket is checked like every other one.
    for line in [*body, "## end"]:
        if line.startswith("### ") or line.startswith("## "):
            if heading is not None:
                stated = int(re.search(r"\((\d+)\)", heading).group(1))  # type: ignore[union-attr]
                if stated != seen:
                    wrong.append(f"{heading.strip()} covers {seen} rows")
            heading = line if line.startswith("### ") and any(m in line for m in marks) else None
            seen = 0
        elif line.startswith("| ") and heading:
            row = line.split("|")[1].strip()
            if row and row != "#" and set(row) - set("-"):
                seen += 1
    assert not wrong, (
        "bucket headings disagree with their contents:" + chr(10) + chr(10).join(wrong)
    )


def test_every_excluded_row_says_why_it_cannot_be_measured() -> None:
    """⚠️ The guard on the escape hatch.

    A row marked ⊘ drops out of the coverage denominator, which makes every phase easier to
    complete. That is legitimate for a claim no measurement of ours can add to, and a way to
    flatter the figures otherwise -- so each one must name one of four reasons, and `subsumed` must
    name the row that covers it.
    """
    import re

    from tests.conftest import REPO_ROOT

    section = (REPO_ROOT / "notes/LEDGER.md").read_text(encoding="utf-8")
    marked = 0
    for line in section.split(chr(10)):
        row = re.match(r"^\| (\d+[a-z]?) \|", line)
        if not row or "Not executable" not in line:
            continue
        marked += 1
        tag = re.search(r"Not executable\*\* \(`([^`]+)`\)", line)
        assert tag, f"row {row.group(1)}: ⊘ without a tag"
        assert tag.group(1) in NOT_EXECUTABLE_TAGS, (
            f"row {row.group(1)}: unknown tag {tag.group(1)}"
        )
        if tag.group(1) == "subsumed":
            assert re.search(r"by rows? \d+", line), (
                f"row {row.group(1)}: `subsumed` must name the row that covers it"
            )
    assert marked > 0, "the ⊘ convention is documented but unused; has the format changed?"


#: The four files that publish the coverage fraction in prose, and are therefore the four that
#: have gone stale. `LEDGER.md` is the denominator; the other three quote it.
_FILES_PUBLISHING_COVERAGE = (
    "notes/LEDGER.md",
    "notes/PLAN.md",
    "PORTING_THE_PHYSICS.md",
    "README.md",
)

#: Of those, the ones `.publicignore` keeps out of the public snapshot (`ebbcarbon/Plumes_Public`,
#: PLAN.md withheld 2026-09-08). Absent there, the file is skipped; absent *here*, any other file
#: in the list is still a failure. The first public CI run after the export (2026-09-09) fell over
#: on exactly this: an unconditional `read_text` of a file the export had dropped.
_WITHHELD_FROM_PUBLIC = frozenset({"notes/PLAN.md"})

#: `n of m` as these files write it, with the thousands of other number pairs in them excluded by
#: requiring the literal "of" and a following word that commits it to being a coverage claim.
_PUBLISHED_FRACTION = re.compile(
    r"\*{0,2}(\d{2,3}) of (?:the )?(\d{2,3})\*{0,2} "
    r"(?:countable|numbered|of the countable)"
)

#: A retracted figure, kept on the page by the ledger's own convention. Non-greedy, so two
#: retractions on one line do not swallow the live figure between them.
_STRUCK_THROUGH = re.compile(r"~~.*?~~")


def test_the_published_coverage_figures_are_not_stale() -> None:
    """⚠️⚠️ The seventh instance, and the first one a test can see.

    `test_the_ledger_denominator_matches_the_ledger` guards the *derived* per-phase counts, and
    `test_the_ledger_denominator_has_not_gone_stale` guards the mechanical row count. Neither reads
    the **prose**, so on 2026-08-21 four documents published three different totals and three of
    them were wrong:

    | | published | derived |
    |---|---|---|
    | `PLAN.md` §8b | 152 of 158 | 152 of 158 |
    | `PLAN.md` §8b (later) | 148 of 154 | 152 of 158 |
    | `PLAN.md` §9 | 142 of 152 | 152 of 158 |
    | `LEDGER.md` header | 148 of 154 | 152 of 158 |
    | `PORTING_THE_PHYSICS.md` | 148 of 154 | 152 of 158 |

    ⚠️ **`PORTING_THE_PHYSICS.md` is the reader-facing one**, which is what makes this worth a
    test rather than a tidy-up: it is the document the README sends a newcomer to, and it was
    understating the port's own coverage by four rows while claiming coverage is "published, not
    implied".

    ⭐ **And it found an eighth on its first run**, which is the argument for writing it rather
    than fixing the five by hand: row 218's note carried "15 of 114 numbered rows **so far**" --
    a live-sounding figure from 2026-08-17 that had been false since the following day, sitting
    inside the row that *describes* the executable ledger. Now struck through and dated, which is
    the ledger's own convention for a retraction, and struck spans are exempt below.

    The failure is the same one §8b enumerates four times over -- correct arithmetic, wrong
    presentation -- and the same fix applies: a number nobody has to *produce* goes stale, so this
    produces every one of them and compares.

    ⚠️ **What it checks is "is this a figure the ledger derives", not "is this the total".** A
    published fraction may be the total or any one phase's pair, because the prose legitimately
    quotes both -- `LEDGER.md`'s phase-5 section says 53 of 53 three hundred lines below a header
    saying 156 of 162, and both are right. Telling them apart would mean guessing which one a
    sentence meant. The looser rule still catches every instance that has occurred, because a
    stale figure matches **neither**: 148 of 154, 142 of 152 and phase 5's own 45 of 45 were not
    any phase's numbers either.
    """
    from tests.conftest import REPO_ROOT

    coverage = coverage_by_phase()
    covered = sum(count for count, _total in coverage.values())
    countable = sum(total for _count, total in coverage.values())

    # A published figure has to be one the ledger actually derives -- the total, or one phase's
    # own pair. Accepting either is what lets the phase-5 section quote its own 53 of 53 while
    # PLAN's headline quotes the total. A *stale* figure matches neither, which is the only case
    # that has ever occurred.
    allowed = {(covered, countable), *coverage.values()}

    found = 0
    for name in _FILES_PUBLISHING_COVERAGE:
        path = REPO_ROOT / name
        if not path.exists():
            assert name in _WITHHELD_FROM_PUBLIC, f"{name} is missing and is not a withheld file"
            continue  # the public snapshot: check the three documents it does carry
        text = path.read_text(encoding="utf-8")
        for line in text.split("\n"):
            # ⚠️ A struck-through figure is a retraction kept on purpose -- "a retraction that
            # leaves no trace is how a project forgets what it already got wrong", per the ledger
            # header. Strip the struck span rather than skipping the whole line, so a row that
            # quotes its own retracted figure *and* a live one still has the live one checked.
            live = _STRUCK_THROUGH.sub(" ", line)
            for numerator, denominator in _PUBLISHED_FRACTION.findall(live):
                found += 1
                assert (int(numerator), int(denominator)) in allowed, (
                    f"{name} publishes {numerator} of {denominator}, which the ledger derives "
                    f"neither as a total ({covered} of {countable}) nor for any one phase "
                    f"({sorted(coverage.items())}). Update the prose in the same commit that "
                    "changed the rows -- this is the failure mode PLAN section 8b enumerates."
                )
    assert found >= 4, (
        f"only {found} published coverage fractions found across "
        f"{len(_FILES_PUBLISHING_COVERAGE)} files; has the phrasing changed? The regex needs to "
        "keep matching, or this test silently guards nothing."
    )


def test_the_ledger_denominator_has_not_gone_stale() -> None:
    """⚠️ The one this project has actually got wrong, twice.

    `LEDGER_ROWS_WITH_NUMBERS` is hand-counted on purpose -- inferring it would let the denominator
    track the numerator, and every coverage figure would flatter. The cost of hand-counting is that
    it goes stale silently, which it did at rows 222-236 and again at 237-252, flattering every
    figure published in between.

    So: this asserts the *mechanical* row count, which is cheap and exact. When it fails, the fix is
    to re-count how many of the new rows carry a number, update `LEDGER_ROWS_WITH_NUMBERS`, and
    bump the pin here -- in the same commit that added the rows.

    ⚠️ **What this does not catch: a hand count that is simply wrong.** Changing phase 4 from 51 to
    36 passes this test, because the ledger has not grown. It catches the failure mode that actually
    occurred twice -- rows added, denominator left behind -- and nothing else. That limit is
    deliberate: the obvious mechanical proxy, "the detail column contains a digit", counts 96 rows
    in phase 5 against a hand count of 41, because step numbers and case references are digits too.
    A cross-check that loose would either pass everything or fire constantly.

    ⚠️ And it is not even an upper bound: that proxy gives **18** for phase 6 against a hand count
    of 22, and 1 for phase 7 against 2. Whoever next re-counts by hand should start there, because
    at least one of the two numbers in each of those pairs is wrong.
    """
    total = len(_ledger_rows())
    assert total == LEDGER_TABLE_ROWS, (
        f"the ledger has {total} rows against a pinned {LEDGER_TABLE_ROWS}. Re-count how many of "
        f"the new ones carry a number, update LEDGER_ROWS_WITH_NUMBERS, then bump this pin."
    )
    # And the hand count can never exceed the mechanical one, whatever else drifts.
    assert sum(len(rows) for rows in LEDGER_ROWS_WITH_NUMBERS.values()) <= total


def test_the_validation_report_is_a_pdf_when_the_path_says_so(tmp_path: Path) -> None:
    """The same table document, on letter pages: the ledger is what goes in the permit file."""
    outcomes = [Outcome(target=t, ours=t.reference) for t in TARGETS]
    target = build_validation_report(tmp_path / "validation.pdf", outcomes)
    data = target.read_bytes()
    assert data.startswith(b"%PDF-1.")
    assert len(re.findall(rb"/Type\s*/Page[^s]", data)) >= 2, "a table that long flows over pages"
