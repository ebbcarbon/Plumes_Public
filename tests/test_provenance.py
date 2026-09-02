"""Provenance recorded with results -- PLAN.md section 7b."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plumes2.io.project import load_project
from plumes2.io.yaml_case import dumps_case, loads_case
from plumes2.provenance import Provenance, case_digest, git_state, provenance

CASES = Path(__file__).resolve().parents[1] / "reference_cases"
STAMP = datetime(2026, 8, 13, 14, 30, 5, 123456, tzinfo=UTC)


def _case():  # type: ignore[no-untyped-def]
    return load_project(
        CASES / "case18_zero_current_pair" / "test21.prj", warn_on_drift=False
    ).to_case()


def test_the_digest_is_stable_and_canonical() -> None:
    case = _case()
    assert case_digest(case) == case_digest(case)
    assert re.fullmatch(r"[0-9a-f]{64}", case_digest(case))
    # Equal cases hash equal, however they were built.
    assert case_digest(case) == case_digest(case.model_copy())


def test_the_digest_survives_a_yaml_round_trip() -> None:
    """A case written out and read back is the same case, so it must hash the same."""
    case = _case()
    assert case_digest(loads_case(dumps_case(case))) == case_digest(case)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("diffuser", "port_spacing", 1.25),
        ("diffuser", "n_ports", 7),
        ("effluent", "flow", 0.007),
        ("near_field", "aspiration_coefficient", 0.12),
    ],
)
def test_any_input_change_changes_the_digest(section: str, field: str, value: float) -> None:
    case = _case()
    changed = case.model_copy(
        update={section: getattr(case, section).model_copy(update={field: value})}
    )
    assert case_digest(changed) != case_digest(case), f"{section}.{field}"


def test_the_digest_covers_fields_left_at_their_defaults() -> None:
    """The trap this module exists to close, and it is not hypothetical.

    `yaml_case` writes with `exclude_defaults=True`, so a defaulted field is *absent* from the
    file. Hashing that terse form would mean a later release changing a default silently
    changes what an old file means while its digest stays put. `stop_at_surface` flipped from
    True to False on 2026-08-13 for exactly that kind of reason.
    """
    case = _case()
    assert case.near_field.stop_at_surface is False, "the default this test is guarding"
    flipped = case.model_copy(
        update={"near_field": case.near_field.model_copy(update={"stop_at_surface": True})}
    )
    assert case_digest(flipped) != case_digest(case)
    # And the terse serialisation genuinely cannot see it, which is the point.
    assert "stop_at_surface" not in dumps_case(case)


def test_provenance_records_the_four_questions() -> None:
    case = _case()
    record = provenance(case, source="somewhere/test21.prj", now=STAMP)
    assert record.case_digest == case_digest(case)
    assert record.generated_at == "2026-08-13T14:30:05Z", "UTC, seconds, no microseconds"
    assert record.port_version and record.python_version and record.platform
    assert record.source == "somewhere/test21.prj"


def test_provenance_survives_having_no_repository(tmp_path: Path) -> None:
    """An installed copy has no git history, and a result from one is still a result."""
    commit, dirty = git_state(tmp_path)
    assert (commit, dirty) == (None, None)
    record = provenance(_case(), now=STAMP, repository=tmp_path)
    assert record.git_commit is None
    assert record.git_dirty is None
    assert "unknown" in "\n".join(record.as_comment_lines())


def test_a_dirty_tree_is_called_out() -> None:
    """`dirty` means the result cannot be reproduced from the commit alone -- say so."""
    record = Provenance(
        port_version="0.0.1",
        case_digest="0" * 64,
        generated_at="2026-08-13T14:30:05Z",
        git_commit="a" * 40,
        git_dirty=True,
        python_version="3.14.0",
        platform="test",
    )
    assert "(dirty)" in "\n".join(record.as_comment_lines())
    clean = Provenance(**{**record.to_dict(), "git_dirty": False})  # type: ignore[arg-type]
    assert "(dirty)" not in "\n".join(clean.as_comment_lines())


def test_comment_lines_are_comments() -> None:
    record = provenance(_case(), now=STAMP)
    lines = record.as_comment_lines()
    assert all(line.startswith("# ") for line in lines)
    assert any("plumes2" in line for line in lines)
    assert all(line.startswith("!") for line in record.as_comment_lines(prefix="!"))
