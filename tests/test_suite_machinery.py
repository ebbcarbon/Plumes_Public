"""The suite's own machinery: the warm outcome cache, the memos, and the `slow` marker.

⚠️⚠️ **A cache over measured physics is the one optimisation in this repo that can turn a red
suite green.** Every other speed-up here was accepted or rejected on a measurement of accuracy --
the analytic density partials in `_density_partials`, the vectorised right-hand side in PLAN §8d --
and this one changes no number, but it *reuses* numbers, and a reuse keyed on too little would
report yesterday's physics against today's code. So the **key** is the subject of these tests. The
speed is measured in PLAN §8d and needs no assertion; a test that pinned a duration would fail on a
loaded machine and teach everyone to ignore it.

Measured 2026-08-21: `tests/test_validation.py` went 233 s -> 127 s cold (one `run_all` instead of
three) -> 2.5 s warm.
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import pytest

from plumes2.validation import TARGETS, cached_functions, clear_caches, coverage_by_phase
from tests.conftest import (
    OUTCOME_CACHE,
    OUTCOME_CACHE_MAX_AGE_SECONDS,
    REFERENCE_CASES,
    REPO_ROOT,
    SLOW_SECONDS,
    UPSTREAM,
    _read_outcome_cache,
    _source_fingerprint,
    _write_outcome_cache,
)


class TestTheFingerprint:
    """What the cache is keyed on, which is the whole safety argument.

    ⚠️⚠️ These build a throwaway tree rather than editing a real source file. An earlier draft
    proved the digest covered `src/plumes2` by appending a line to `units.py` and reverting it.
    That passes in serial and **races under `-n auto`**: with `--dist loadfile` the test mutating
    the tree runs concurrently with the worker hashing it, so the worker fingerprints a file that
    is about to be reverted and writes the cache under a digest nothing will ever match again.
    Every later run is then silently cold -- one 543 s serial run that should have been ~190 s.
    A test that can corrupt the thing it is testing is not a test.
    """

    @pytest.fixture
    def tree(self, tmp_path: Path) -> tuple[Path, Path]:
        """A miniature of the real layout: some code, some reference data."""
        code, data = tmp_path / "code", tmp_path / "data"
        code.mkdir()
        data.mkdir()
        (code / "solver.py").write_text("ALPHA = 0.1\n", encoding="utf-8")
        (data / "case01.dat").write_text("depth dilution\n1.0 2.0\n", encoding="utf-8")
        return code, data

    def test_it_is_stable_across_calls(self, tree: tuple[Path, Path]) -> None:
        code, data = tree
        assert _source_fingerprint(code, (data,)) == _source_fingerprint(code, (data,))

    def test_a_code_edit_changes_it(self, tree: tuple[Path, Path]) -> None:
        """⭐ The property the cache's correctness rests on."""
        code, data = tree
        before = _source_fingerprint(code, (data,))
        (code / "solver.py").write_text("ALPHA = 0.2\n", encoding="utf-8")
        assert _source_fingerprint(code, (data,)) != before, (
            "a changed constant left the digest alone, so a warm cache would serve "
            "measurements taken against different code"
        )

    def test_reverting_an_edit_restores_the_digest(self, tree: tuple[Path, Path]) -> None:
        """A warm cache must survive being briefly invalidated -- checkouts do this constantly."""
        code, data = tree
        before = _source_fingerprint(code, (data,))
        (code / "solver.py").write_text("ALPHA = 0.2\n", encoding="utf-8")
        (code / "solver.py").write_text("ALPHA = 0.1\n", encoding="utf-8")
        assert _source_fingerprint(code, (data,)) == before

    def test_a_new_reference_case_changes_it(self, tree: tuple[Path, Path]) -> None:
        """A new exe run must invalidate, not merge into, the warm set.

        Half the targets sweep the whole archive and their values move when it grows -- row 262's
        row count moved twice on 2026-08-21 alone. A digest over code only would keep serving the
        old sweep.
        """
        code, data = tree
        before = _source_fingerprint(code, (data,))
        (data / "case02.dat").write_text("depth dilution\n1.0 3.0\n", encoding="utf-8")
        assert _source_fingerprint(code, (data,)) != before

    def test_an_edited_reference_case_changes_it(self, tree: tuple[Path, Path]) -> None:
        """Content, not just the file list -- a re-run case keeps its name."""
        code, data = tree
        before = _source_fingerprint(code, (data,))
        (data / "case01.dat").write_text("depth dilution\n1.0 9.9\n", encoding="utf-8")
        assert _source_fingerprint(code, (data,)) != before

    def test_irrelevant_files_are_ignored(self, tree: tuple[Path, Path]) -> None:
        """⚠️ Notes and plots in a case folder must not evict a valid cache.

        Case folders carry a README each, and several carry plots. If those counted, writing up a
        finding would throw away the measurements the finding was based on.
        """
        code, data = tree
        before = _source_fingerprint(code, (data,))
        (data / "README.md").write_text("what this case is for\n", encoding="utf-8")
        (data / "plot.png").write_bytes(b"\x89PNG\r\n")
        assert _source_fingerprint(code, (data,)) == before

    def test_the_defaults_point_at_the_real_tree(self) -> None:
        """The parameters exist for these tests; the defaults are what production uses."""
        defaults = inspect.signature(_source_fingerprint).parameters
        assert defaults["code"].default == REPO_ROOT / "src" / "plumes2"
        assert defaults["data"].default == (REFERENCE_CASES, UPSTREAM)

    def test_the_real_tree_hashes_something(self) -> None:
        """⚠️ A digest over an empty file set is constant, so the cache would always read warm."""
        empty = _source_fingerprint(REPO_ROOT / "docs" / "does-not-exist", ())
        assert _source_fingerprint() != empty


class TestTheOutcomeCacheFile:
    """One file, overwritten, and every failure path costs time rather than correctness.

    ⚠️ Every test here writes to a **tmp** path. An earlier draft pointed them at the real
    `OUTCOME_CACHE`, so running the suite deleted its own warm cache -- the tests passed while
    quietly destroying the thing they were testing.
    """

    @pytest.fixture
    def cache(self, tmp_path: Path) -> Path:
        return tmp_path / "outcomes.json"

    def test_it_is_a_single_file_and_gitignored(self) -> None:
        assert OUTCOME_CACHE.parent == REPO_ROOT, "the cache must not scatter into a directory"
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert OUTCOME_CACHE.name in ignored, "a cache of measured physics must never be committed"

    def test_a_foreign_fingerprint_is_discarded_whole(self, cache: Path) -> None:
        """Not row by row: a partial match is the failure mode worth refusing outright."""
        _write_outcome_cache("aaaa", {"1": {"ours": 1.0, "error": None}}, cache)
        assert _read_outcome_cache("aaaa", cache) == {"1": {"ours": 1.0, "error": None}}
        assert _read_outcome_cache("bbbb", cache) == {}

    def test_an_absent_cache_is_simply_cold(self, cache: Path) -> None:
        assert _read_outcome_cache("aaaa", cache) == {}

    def test_a_corrupt_cache_is_ignored_rather_than_raised(self, cache: Path) -> None:
        """⚠️ A truncated write must not fail a suite for reasons unrelated to the physics."""
        cache.write_text('{"fingerprint": "aaaa", "outcom', encoding="utf-8")
        assert _read_outcome_cache("aaaa", cache) == {}

    def test_a_cache_without_a_timestamp_is_refused(self, cache: Path) -> None:
        """An unstamped file cannot be aged out, so it is treated as cold rather than fresh."""
        cache.write_text(
            json.dumps({"fingerprint": "aaaa", "outcomes": {"1": {"ours": 1.0}}}),
            encoding="utf-8",
        )
        assert _read_outcome_cache("aaaa", cache) == {}

    def test_a_stale_cache_expires(self, cache: Path) -> None:
        _write_outcome_cache("aaaa", {"1": {"ours": 1.0, "error": None}}, cache)
        payload = json.loads(cache.read_text(encoding="utf-8"))
        payload["written_at"] -= OUTCOME_CACHE_MAX_AGE_SECONDS + 1
        cache.write_text(json.dumps(payload), encoding="utf-8")
        assert _read_outcome_cache("aaaa", cache) == {}

    def test_a_rewrite_replaces_rather_than_accumulates(self, cache: Path) -> None:
        """⭐ Overwrite one file, never grow a pile of them."""
        _write_outcome_cache("aaaa", {"1": {"ours": 1.0, "error": None}}, cache)
        _write_outcome_cache("aaaa", {"2": {"ours": 2.0, "error": None}}, cache)
        assert set(_read_outcome_cache("aaaa", cache)) == {"2"}
        assert list(cache.parent.iterdir()) == [cache], "one file, not one per run"

    def test_no_temporary_files_are_left_behind(self, cache: Path) -> None:
        _write_outcome_cache("aaaa", {"1": {"ours": 1.0, "error": None}}, cache)
        assert not list(cache.parent.glob("*.tmp"))


class TestTheSharedMeasurement:
    """What the three registry consumers now share."""

    def test_every_target_is_present_and_keyed_by_row(self, ledger_outcomes) -> None:  # type: ignore[no-untyped-def]
        assert set(ledger_outcomes) == {target.row for target in TARGETS}

    def test_a_non_finite_measurement_survives_the_round_trip(self, tmp_path: Path) -> None:
        """⚠️ `nan` is a *result* -- row 195's `Omega < 1` case is one -- and `null` carries it.

        If it came back as a number the target would silently start passing.
        """
        cache = tmp_path / "outcomes.json"
        _write_outcome_cache("aaaa", {"1": {"ours": None, "error": "boom"}}, cache)
        row = _read_outcome_cache("aaaa", cache)["1"]
        assert row["ours"] is None
        assert row["error"] == "boom", "a raised measurement must stay a raised measurement"
        assert math.isnan(math.nan if row["ours"] is None else float(row["ours"]))  # type: ignore[arg-type]


class TestTheMemos:
    def test_every_cache_is_discovered_rather_than_listed(self) -> None:
        """A hand-listed set of caches goes stale the first time someone adds a `@cache`."""
        assert len(cached_functions()) > 25, cached_functions()

    def test_clearing_is_idempotent_and_leaves_the_module_usable(self) -> None:
        """Correctness cannot depend on it: every memo is keyed on its full input."""
        clear_caches()
        clear_caches()
        assert coverage_by_phase(), "the module must still work after its memos are dropped"


def test_the_slow_threshold_matches_the_marker_text() -> None:
    """The marker says "more than a second"; the guard must enforce that number and no other."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"slow: takes more than a second' in text
    assert SLOW_SECONDS == 1.0
