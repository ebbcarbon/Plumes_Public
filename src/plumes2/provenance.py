"""Provenance: what produced a result, recorded with the result.

PLAN.md §7b is a list of things the exe does not record — its `.prj` carries no chemistry, no
stop-at checkbox and no build marker, and its `.dat` has no header at all and rounds inputs to
two decimals. The standing requirement for this port is that **every input to a run is
recoverable from the artefacts that run produces**. `Case` covers the inputs; this module
covers the run.

Four questions have to be answerable from a result file alone:

    what code ran      port version, and the git commit with a dirty flag
    what went in       a digest of the fully-resolved case
    when              a UTC timestamp
    where             python and platform, because EOS-80 and PyCO2SYS are float-sensitive

⚠️ **The digest is taken over the *resolved* case, not the terse one.** `yaml_case.dumps_case`
writes with `exclude_defaults=True` to keep files readable, which is right for a file and
wrong for a hash: a field left at its default is simply absent, so **changing a default in a
later version silently changes what a file means while its digest stays put**. That is not
hypothetical — `stop_at_surface` flipped from `True` to `False` on 2026-08-13 when the archive
showed six of seven surface hits were non-terminal. Hashing `model_dump()` in full closes it.

⚠️ **Provenance must never enter a byte-exact artefact.** Phase 6 reproduces the exe's `.dat`
byte for byte, and a timestamp would destroy that immediately. It belongs in a **sidecar**, or
in a comment block on formats that have one — never interleaved with the table being matched.
`as_comment_lines` exists for the second case; the byte-exact writer must not call it.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from plumes2 import __version__
from plumes2.config import Case

__all__ = ["Provenance", "case_digest", "git_state", "provenance"]


def case_digest(case: Case) -> str:
    """SHA-256 over the fully-resolved case, as 64 hex characters.

    Canonicalised through JSON with sorted keys, so the digest depends on the *values* and not
    on field declaration order or YAML formatting. Two cases that compare equal hash equal;
    any difference in any field, defaulted or not, changes the digest.
    """
    payload = case.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def git_state(repository: Path | None = None) -> tuple[str | None, bool | None]:
    """`(commit, dirty)` for the working tree, or `(None, None)` outside a repository.

    Never raises: an installed copy of this package has no git history, and a result produced
    from one is still a valid result — it just cannot name a commit.
    """
    root = repository or Path(__file__).resolve().parent
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    return (commit or None), bool(status.strip())


@dataclass(frozen=True, slots=True)
class Provenance:
    """Everything needed to reproduce a run, minus the case itself."""

    #: `plumes2.__version__` of the code that ran.
    port_version: str
    #: See `case_digest` — over the resolved case, so defaults are covered.
    case_digest: str
    #: ISO-8601, UTC, seconds resolution.
    generated_at: str
    #: Full commit SHA, or `None` when there is no repository to ask.
    git_commit: str | None
    #: Whether the working tree had uncommitted changes. `True` means **this result cannot be
    #: reproduced from the commit alone**, which is the whole reason to record it.
    git_dirty: bool | None
    python_version: str
    platform: str
    #: Where the case came from, when it came from a file.
    source: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_comment_lines(self, prefix: str = "# ") -> list[str]:
        """Provenance as comment lines, for formats that tolerate a header.

        ⚠️ Not for byte-exact output — see the module docstring.
        """
        rows = [
            ("plumes2", self.port_version),
            ("commit", f"{self.git_commit}{' (dirty)' if self.git_dirty else ''}"
             if self.git_commit else "unknown"),
            ("generated", self.generated_at),
            ("case", self.case_digest),
            ("python", self.python_version),
            ("platform", self.platform),
        ]
        if self.source:
            rows.append(("source", self.source))
        width = max(len(name) for name, _ in rows)
        return [f"{prefix}{name.ljust(width)}  {value}" for name, value in rows]


def provenance(
    case: Case,
    *,
    source: str | Path | None = None,
    now: datetime | None = None,
    repository: Path | None = None,
) -> Provenance:
    """Describe the current run of `case`.

    `now` and `repository` are injectable so tests are not at the mercy of the clock or of
    whether the checkout happens to be dirty.
    """
    commit, dirty = git_state(repository)
    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    return Provenance(
        port_version=__version__,
        case_digest=case_digest(case),
        generated_at=stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        git_commit=commit,
        git_dirty=dirty,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        source=str(source) if source is not None else None,
    )
