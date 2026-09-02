"""The project's own YAML case format.

This is the primary input format for the Python port: readable, diffable, unit-explicit
and able to express things the exe cannot store -- chiefly the effluent carbonate
endmember and the equilibrium-constant options, none of which appear in any `.prj`
(see PORTING_NOTES section 4).

Round-tripping is exact in the sense that matters: `load(dump(case)) == case`. It is not
byte-stable against hand-edited files, and is not meant to be -- byte fidelity is the
`.prj` writer's job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from plumes2.config import Case

__all__ = ["dump_case", "dumps_case", "load_case", "loads_case"]


def _to_plain(case: Case) -> dict[str, Any]:
    """Model to plain data, dropping defaults so files stay readable.

    Enums become their string values, and `None` chemistry is omitted entirely rather
    than written as a null.
    """
    return case.model_dump(mode="json", exclude_defaults=True, exclude_none=True)


def dumps_case(case: Case) -> str:
    """Serialise a case to YAML text."""
    payload = _to_plain(case)
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, allow_unicode=True)


def dump_case(case: Case, path: str | Path) -> None:
    """Write a case to a YAML file (UTF-8, LF)."""
    Path(path).write_text(dumps_case(case), encoding="utf-8", newline="\n")


def loads_case(text: str) -> Case:
    """Parse YAML text into a validated :class:`Case`."""
    payload = yaml.safe_load(text)
    if payload is None:
        raise ValueError("empty YAML document")
    if not isinstance(payload, dict):
        raise TypeError(f"expected a YAML mapping at the top level, got {type(payload).__name__}")
    return Case.model_validate(payload)


def load_case(path: str | Path) -> Case:
    """Read a case from a YAML file."""
    return loads_case(Path(path).read_text(encoding="utf-8"))
