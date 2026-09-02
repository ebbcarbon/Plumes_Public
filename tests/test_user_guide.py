"""`USER_GUIDE.md`'s syntax claims, checked against the code they describe.

The guide exists so the model can be driven without internet access, which means every field
name, default, CLI flag, column name and enum value in it has to be *right* -- and prose in this
project has gone stale on four separate occasions (PLAN §9 item 1). So the guide carries
machine-readable markers before each of its reference tables:

    <!-- schema: plumes2.config.Diffuser -->      the table lists every field, with its default
    <!-- enum: plumes2.crossplume.SimilarityProfile -->   the table lists every value
    <!-- columns: plumes2.results.NEARFIELD_COLUMNS -->   the table lists every column

and every ``plumes2 <command> ...`` line inside a code fence is parsed against the real argparse
parser. A renamed field, a changed default, a new column or a dropped flag fails here and the
guide is fixed in the same commit.
"""

from __future__ import annotations

import argparse
import importlib
import re
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from plumes2.cli import _build_parser

GUIDE = Path(__file__).resolve().parents[1] / "USER_GUIDE.md"
TEXT = GUIDE.read_text(encoding="utf-8")
LINES = TEXT.splitlines()

_MARKER = re.compile(r"^<!-- (schema|enum|columns): ([\w.]+) -->$")
_CELL_NAME = re.compile(r"^`([^`]+)`")


def _resolve(dotted: str):  # type: ignore[no-untyped-def]
    module, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _tables() -> list[tuple[str, str, list[list[str]]]]:
    """Every marked table as `(kind, dotted name, rows)`, each row a list of stripped cells."""
    found = []
    for index, line in enumerate(LINES):
        marker = _MARKER.match(line.strip())
        if not marker:
            continue
        kind, dotted = marker.groups()
        rows: list[list[str]] = []
        cursor = index + 1
        while cursor < len(LINES) and not LINES[cursor].startswith("|"):
            cursor += 1  # the blank line (or a sentence) between the marker and the table
        while cursor < len(LINES) and LINES[cursor].startswith("|"):
            cells = [cell.strip() for cell in LINES[cursor].strip().strip("|").split("|")]
            rows.append(cells)
            cursor += 1
        # Drop the header row and the `|---|` rule.
        body = [row for row in rows[2:] if row]
        assert body, f"{dotted}: the marked table has no rows"
        found.append((kind, dotted, body))
    return found


TABLES = _tables()


def _names(rows: list[list[str]]) -> list[str]:
    names = []
    for row in rows:
        match = _CELL_NAME.match(row[0])
        assert match, f"first cell must be a backticked name, got {row[0]!r}"
        names.append(match.group(1))
    return names


def _spell(field: FieldInfo) -> str | None:
    """How the guide spells a default: YAML literals, enum values, `required`; None = unchecked."""
    if field.is_required():
        return "required"
    default = field.get_default(call_default_factory=True)
    if isinstance(default, BaseModel):
        return None  # a section, documented by its own table
    if isinstance(default, bool):
        return "true" if default else "false"
    if default is None:
        return "null"
    if isinstance(default, StrEnum):
        return default.value
    if isinstance(default, (int, float)):
        return repr(default)
    if isinstance(default, str):
        return f'"{default}"'
    if isinstance(default, list):
        return "[]" if not default else None
    return None


def test_the_guide_exists_and_carries_every_marker_kind() -> None:
    kinds = {kind for kind, _, _ in TABLES}
    assert kinds == {"schema", "enum", "columns"}, kinds


@pytest.mark.parametrize(
    ("dotted", "rows"),
    [(dotted, rows) for kind, dotted, rows in TABLES if kind == "schema"],
    ids=[dotted for kind, dotted, _ in TABLES if kind == "schema"],
)
def test_each_schema_table_lists_every_field_with_its_real_default(
    dotted: str, rows: list[list[str]]
) -> None:
    model = _resolve(dotted)
    documented = _names(rows)
    assert documented == list(model.model_fields), (
        f"{dotted}: the guide lists {documented}, the model has {list(model.model_fields)}"
    )
    for row, name in zip(rows, documented, strict=True):
        assert len(row) >= 4, f"{dotted}.{name}: schema rows need field/type/unit/default/meaning"
        expected = _spell(model.model_fields[name])
        if expected is not None:
            stated = row[3].strip("`*")
            assert stated == expected, f"{dotted}.{name}: guide says {stated!r}, code {expected!r}"


@pytest.mark.parametrize(
    ("dotted", "rows"),
    [(dotted, rows) for kind, dotted, rows in TABLES if kind == "enum"],
    ids=[dotted for kind, dotted, _ in TABLES if kind == "enum"],
)
def test_each_enum_table_lists_exactly_the_enum_s_values(
    dotted: str, rows: list[list[str]]
) -> None:
    enum = _resolve(dotted)
    assert set(_names(rows)) == {member.value for member in enum}


@pytest.mark.parametrize(
    ("dotted", "rows"),
    [(dotted, rows) for kind, dotted, rows in TABLES if kind == "columns"],
    ids=[dotted for kind, dotted, _ in TABLES if kind == "columns"],
)
def test_each_column_table_lists_exactly_the_columns_written(
    dotted: str, rows: list[list[str]]
) -> None:
    columns = _resolve(dotted)
    assert _names(rows) == list(columns), f"{dotted}: guide {_names(rows)} vs code {list(columns)}"


def _cli_lines() -> list[str]:
    """Every `plumes2 ...` invocation inside a code fence."""
    inside, lines = False, []
    for line in LINES:
        if line.startswith("```"):
            inside = not inside
            continue
        stripped = line.strip()
        if inside and re.match(r"^(\.venv\\Scripts\\)?plumes2(\.exe)? ", stripped):
            lines.append(stripped)
    return lines


def test_every_documented_cli_invocation_parses_against_the_real_parser() -> None:
    parser = _build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    invocations = _cli_lines()
    assert len(invocations) >= 8, "the guide should show every subcommand at least once"
    seen = set()
    for line in invocations:
        tokens = re.sub(r"^(\.venv\\Scripts\\)?plumes2(\.exe)? ", "", line).split()
        command = tokens[0]
        if command == "--version":
            continue
        assert command in subparsers.choices, f"{line!r}: {command!r} is not a subcommand"
        seen.add(command)
        options = {
            string
            for action in subparsers.choices[command]._actions
            for string in action.option_strings
        }
        for token in tokens[1:]:
            if token.startswith("-") and not re.match(r"^-\d", token):
                flag = token.split("=")[0]
                assert flag in options, f"{line!r}: {flag!r} is not an option of {command!r}"
    missing = set(subparsers.choices) - seen
    assert not missing, f"subcommands never shown in the guide: {missing}"


def test_the_guide_names_the_yaml_top_level_keys_exactly() -> None:
    """The `Case` table is the top-level YAML schema; every key it lists must be a `Case` field."""
    from plumes2.config import Case

    case_tables = [rows for kind, dotted, rows in TABLES if dotted == "plumes2.config.Case"]
    assert len(case_tables) == 1, "exactly one table describes the top level"
    assert _names(case_tables[0]) == list(Case.model_fields)
