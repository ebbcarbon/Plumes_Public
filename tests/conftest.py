"""Shared fixtures: locations of the upstream snapshot and the reference cases."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = REPO_ROOT / "upstream"
EXAMPLE_PROJECT = UPSTREAM / "Example_project"
REFERENCE_CASES = REPO_ROOT / "reference_cases"

#: Every `.prj` in the repo, upstream and ours. Any new case folder is picked up
#: automatically, so the round-trip suite widens as more exe runs arrive.
ALL_PRJ_PATHS: list[Path] = sorted(
    [*EXAMPLE_PROJECT.glob("*.prj"), *REFERENCE_CASES.glob("*/*.prj")]
)

#: Every exe-produced output file.
ALL_DAT_PATHS: list[Path] = sorted(
    [*EXAMPLE_PROJECT.glob("*.dat"), *REFERENCE_CASES.glob("*/*.dat")]
)

#: Every exe-produced input table.
ALL_CSV_PATHS: list[Path] = sorted(
    [*EXAMPLE_PROJECT.glob("*.csv"), *REFERENCE_CASES.glob("*/*.csv")]
)


def _ids(paths: list[Path]) -> list[str]:
    """Readable test ids: the parent folder plus the filename."""
    return [f"{path.parent.name}/{path.name}" for path in paths]


@pytest.fixture(params=ALL_PRJ_PATHS, ids=_ids(ALL_PRJ_PATHS))
def prj_path(request: pytest.FixtureRequest) -> Path:
    """Parametrised over every `.prj` file in the repo."""
    return request.param


@pytest.fixture(params=ALL_CSV_PATHS, ids=_ids(ALL_CSV_PATHS))
def csv_path(request: pytest.FixtureRequest) -> Path:
    """Parametrised over every exe-written CSV input table."""
    return request.param


@pytest.fixture
def example_prj() -> Path:
    """The upstream shipped example project."""
    return EXAMPLE_PROJECT / "Example_project.prj"


# --------------------------------------------------------------------- shared cheap fixtures
#
# ⚠️ **An integration costs the same whatever `samples` asks for.** The cost is the ODE; `samples`
# only picks rows off the dense output. So the way to make this suite fast is to run fewer
# *integrations*, not to ask for fewer rows -- which is why these are session-scoped and why the
# case is a single port at a hundredth of the flow. Measured 2026-08-17: the suite spent most of
# its time re-integrating the same handful of cases.


def cheap_case():  # type: ignore[no-untyped-def]
    """A single-port, low-flow variant of test21 -- the standard cheap trajectory.

    Single port removes merging and the reduced flow shortens the rise, so it integrates in about
    two-thirds the time of the archived project while still exercising every output column.
    """
    from plumes2.io.project import load_project

    base = load_project(
        REFERENCE_CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
    ).to_case()
    return base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": base.effluent.model_copy(update={"flow": 5.0e-5}),
        }
    )


@pytest.fixture(scope="session")
def cheap_run():  # type: ignore[no-untyped-def]
    """One completed run of `cheap_case`, shared across every module in the suite."""
    import warnings

    from plumes2.results import run

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(cheap_case(), samples=64)


@pytest.fixture(scope="session")
def cheap_case_file(tmp_path_factory):  # type: ignore[no-untyped-def]
    """`cheap_case` written as a `.yaml`, for tests that must go through a file path.

    The CLI takes a `.yaml` as a first-class input, so this exercises the real entry point while
    skipping the archived project's heavier trajectory. One test deliberately keeps using the
    `.prj` so that branch stays covered.
    """
    import warnings

    from plumes2.io.yaml_case import dump_case

    target = tmp_path_factory.mktemp("cheap") / "cheap_case.yaml"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dump_case(cheap_case(), target)
    return target


# ------------------------------------------------------------- the ledger outcome cache
#
# ⚠️⚠️ **`run_all()` used to run three times per suite.** Once spread across the 187
# parametrised `test_the_ledger_target_still_holds` cases, then whole in
# `test_the_report_is_built_from_the_same_registry`, then whole again in
# `test_the_cli_summary_is_plain_ascii` -- 45 s and 51 s respectively, measured 2026-08-21, or
# **18 % of the entire suite** spent re-deriving numbers the parametrised tests had derived
# seconds earlier. The `@cache` on `_integrate_once` absorbed the ODE solves, which is why they
# cost 45 s rather than 137 s; the per-target frame work sits outside it and was paid three times.
#
# The fix is one measurement per session, shared by all three consumers. It removes no evidence:
# every ledger value is still asserted, once, against the same tolerance.

#: Single JSON file, overwritten in place -- never one file per entry, and never committed.
OUTCOME_CACHE = REPO_ROOT / ".plumes2_outcome_cache.json"

#: How long a warm cache stays warm. A fingerprint mismatch wipes it immediately, so this only
#: catches the case where *nothing* changed for a week -- a stale-by-abandonment guard rather
#: than a correctness one.
OUTCOME_CACHE_MAX_AGE_SECONDS = 7 * 24 * 3600


def _source_fingerprint(
    code: Path = REPO_ROOT / "src" / "plumes2",
    data: tuple[Path, ...] = (REFERENCE_CASES, UPSTREAM),
) -> str:
    """A digest over everything whose content can change a measured number.

    ⚠️ **This is the whole safety argument for caching measurements to disk**, so it is
    deliberately coarse: every `.py` under `src/plumes2` and every archived `.dat`/`.prj`/`.csv`,
    hashed by content. Any edit anywhere in the model or the reference data changes the digest and
    the entire cache is discarded. That means the cache helps only when the tree is *identical* to
    the run that filled it -- which is the honest bound, and the one that makes a warm run
    trustworthy. A finer key (per-target dependency tracking) would cache more and would be a
    defect waiting to happen the first time a shared helper moved.

    Costs about 0.2 s over 39 MB, against the 233 s it protects.

    ⚠️⚠️ **The roots are parameters so the tests never have to edit a real source file.** An
    earlier draft proved the digest covered `src/plumes2` by appending a line to `units.py` and
    reverting it. That passes in serial and is a **race under `-n auto`**: with `--dist loadfile`
    the test mutating the tree runs at the same time as the worker hashing it, so the worker
    fingerprints a file that is about to be reverted, writes the cache under a digest nothing will
    ever match again, and every subsequent run is silently cold. Measured: one 543 s serial run
    that should have been ~190 s. Cost nothing but time -- a wrong fingerprint can only *miss* a
    cache, never serve a stale row -- which is why the failure hid.
    """
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(code.rglob("*.py")):
        digest.update(path.relative_to(code).as_posix().encode())
        digest.update(path.read_bytes())
    for root in data:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".dat", ".prj", ".csv"}:
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def _read_outcome_cache(
    fingerprint: str, path: Path = OUTCOME_CACHE
) -> dict[str, dict[str, object]]:
    """The warm rows, or `{}` if the cache is absent, stale, foreign or unreadable.

    Every failure path returns `{}` rather than raising: a corrupt cache must cost time, never
    correctness, or the optimisation becomes a way to fail a suite for reasons unrelated to the
    physics.
    """
    import json
    import os
    import time

    if os.environ.get("PLUMES2_NO_CACHE"):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if payload.get("fingerprint") != fingerprint:
        return {}  # a big change: wipe rather than trust a single row of it
    written = payload.get("written_at")
    if not isinstance(written, (int, float)):
        return {}
    if time.time() - written > OUTCOME_CACHE_MAX_AGE_SECONDS:
        return {}
    rows = payload.get("outcomes")
    return rows if isinstance(rows, dict) else {}


def _write_outcome_cache(
    fingerprint: str, rows: dict[str, dict[str, object]], path: Path = OUTCOME_CACHE
) -> None:
    """Overwrite the one file, atomically, carrying only rows for the current fingerprint.

    Atomic because `--dist loadfile` keeps all of `test_validation.py` on one xdist worker but
    does not *guarantee* no other worker ever touches this, and a half-written cache that still
    parses is the one failure mode that could put a wrong number in front of a reader.
    """
    import json
    import os
    import time

    payload = {
        "note": "Generated by the test suite; safe to delete. See tests/conftest.py.",
        "fingerprint": fingerprint,
        "written_at": time.time(),
        "outcomes": rows,
    }
    # ⚠️ The path is a parameter so `tests/test_suite_machinery.py` can exercise the expiry,
    # corruption and overwrite paths against a tmp file. It used to write to the real cache,
    # which meant running the suite destroyed its own warm state -- the tests passed and the
    # optimisation they were testing never survived them.
    scratch = path.with_suffix(f".json.{os.getpid()}.tmp")
    try:
        scratch.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(scratch, path)
    except OSError:
        scratch.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def ledger_outcomes():  # type: ignore[no-untyped-def]
    """Every validation target, measured once, keyed by ledger row.

    The single most expensive fixture in the suite and the one that pays for the rest. Consumed by
    the parametrised per-row assertion and by both registry consumers, so the page, the CLI and
    the suite cannot report different numbers for the same claim -- which is the reason the
    registry exists at all (PLAN.md Phase 7), now enforced by construction rather than by three
    independent passes agreeing.
    """
    import math

    from plumes2.validation import TARGETS, Outcome, measure

    fingerprint = _source_fingerprint()
    warm = _read_outcome_cache(fingerprint)
    outcomes: dict[str, object] = {}
    rows: dict[str, dict[str, object]] = {}
    for target in TARGETS:
        cached = warm.get(target.row)
        if isinstance(cached, dict) and "ours" in cached:
            value = cached["ours"]
            outcome = Outcome(
                target=target,
                # `null` round-trips a non-finite measurement, which is a real result: a target
                # whose measure returned nan must stay nan rather than becoming a pass.
                ours=math.nan if value is None else float(value),  # type: ignore[arg-type]
                error=cached.get("error"),  # type: ignore[arg-type]
            )
        else:
            outcome = measure(target)
        outcomes[target.row] = outcome
        rows[target.row] = {
            "ours": outcome.ours if math.isfinite(outcome.ours) else None,
            "error": outcome.error,
        }
    _write_outcome_cache(fingerprint, rows)
    return outcomes


@pytest.fixture(scope="session", autouse=True)
def _release_the_memos():  # type: ignore[no-untyped-def]
    """Drop the validation module's ~33 memos at session end.

    They hold whole `Solution` objects and archived frames, and under `-n auto` every worker
    carries its own set. Clearing is free of correctness risk because every cache is keyed on its
    full input.
    """
    yield
    try:
        from plumes2.validation import clear_caches
    except ImportError:  # pragma: no cover - the module is always importable in this repo
        return
    clear_caches()


# ------------------------------------------------------------- keeping `slow` honest
#
# ⚠️ **The `slow` marker claimed "takes more than a second" and sat on 18 tests, while a dozen
# unmarked ledger targets took 2-10 s each** (measured 2026-08-21). A marker that is wrong is worse
# than no marker: `-m "not slow"` read as a fast lane and deselected 18 of 2526 tests, saving a
# tenth of the clock while looking like a fast lane. This guard is what stops it drifting again --
# the same reason the coverage fraction and the ledger denominator are derived rather than typed.

#: Where `slow` starts, matching the marker's own wording in `pyproject.toml`.
SLOW_SECONDS = 1.0

#: `nodeid -> call-phase seconds`, for tests that carry no `slow` marker. Populated from the
#: reports rather than from collected items, which is what makes it work under `-n auto`:
#: `pytest_collection_modifyitems` runs in the *workers*, so a controller-side set of marked
#: node ids would be empty and the guard would flag the entire suite. `report.keywords` is
#: serialised across the worker boundary, so it is the same data on either path.
_unmarked_durations: dict[str, float] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--wipe-outcome-cache",
        action="store_true",
        help="Delete the warm ledger-outcome cache before running (see OUTCOME_CACHE).",
    )
    parser.addoption(
        "--strict-slow-marker",
        action="store_true",
        help="Fail the session if a test over SLOW_SECONDS is not marked `slow`.",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--wipe-outcome-cache"):
        OUTCOME_CACHE.unlink(missing_ok=True)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    # `call` only, deliberately: session-fixture setup is charged to whichever test happens to
    # request it first, so including setup would permanently brand one arbitrary ledger row as
    # slow. The marker is about the test's own work.
    if report.when != "call" or "slow" in report.keywords:
        return
    if report.duration > SLOW_SECONDS:
        _unmarked_durations[report.nodeid] = report.duration


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    """Report tests whose call phase outran the `slow` marker's own threshold.

    ⚠️ **Silent under `-n`, deliberately.** Twelve workers contending for four physical cores
    inflate every duration -- tests that take 0.4 s alone were measured at 2.1-2.5 s under
    `-n auto` on 2026-08-21 -- so a parallel run would nominate a dozen tests that are not slow,
    and a guard that cries wolf gets ignored, which is how the marker drifted in the first place.
    The serial run is the one that measures a test's own work.

    ⚠️ **And the whole-suite serial run, not a single module.** Run alone, a module pays the
    cold-start of whatever it imports first -- PyCO2SYS across `test_chem.py`'s first few solves,
    matplotlib across the plot modules -- and three tests appear over the threshold that the full
    run puts well under it. Marking on an isolated run would brand tests slow for a cost they do
    not carry in the suite. Take the full serial run as the reference and treat a single module's
    list as a hint.
    """
    if getattr(config.option, "numprocesses", None):
        return
    unmarked = sorted((duration, node) for node, duration in _unmarked_durations.items())
    if not unmarked:
        return
    terminalreporter.write_sep("=", f"{len(unmarked)} unmarked tests over {SLOW_SECONDS:g}s")
    for duration, node in reversed(unmarked[-15:]):
        terminalreporter.write_line(f"{duration:8.2f}s  {node}")
    terminalreporter.write_line(
        "Add @pytest.mark.slow, or speed them up. `-m 'not slow'` is only a fast lane "
        "if this list is empty."
    )
    if config.getoption("--strict-slow-marker"):
        raise pytest.UsageError(f"{len(unmarked)} tests over {SLOW_SECONDS:g}s lack `slow`")
