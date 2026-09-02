"""Render the API reference with pdoc.

    .venv/Scripts/python docs/build.py            # writes docs/api/
    .venv/Scripts/python docs/build.py --serve    # live preview on localhost

The modules are documented in place and heavily -- most of what this project learned is written
beside the code that encodes it -- so the reference is a rendering job rather than a writing one.
pdoc was chosen for exactly that: no config file, no second source tree to keep in step, and
self-contained HTML, which is the constraint the run report and the validation report are already
held to.

⚠️ **The submodule list is discovered, not written down.** `plumes2/__init__.py` defines `__all__`,
and pdoc honours it -- which means a bare `pdoc plumes2` documents the top-level package and stops
there, silently. Walking the package here is what stops the reference quietly losing a subpackage
the day someone adds one.
"""

from __future__ import annotations

import pkgutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "api"


def modules() -> list[str]:
    """Every importable module in the package, parents first, so pdoc renders the whole tree."""
    sys.path.insert(0, str(ROOT / "src"))
    import plumes2

    found = [
        info.name
        for info in pkgutil.walk_packages(plumes2.__path__, prefix="plumes2.")
        if not info.name.rpartition(".")[2].startswith("_")
    ]
    return ["plumes2", *sorted(found)]


def main() -> int:
    names = modules()
    serve = "--serve" in sys.argv
    command = [sys.executable, "-m", "pdoc", *names]
    command += ["--no-browser"] if serve else ["-o", str(OUTPUT)]

    completed = subprocess.run(command, cwd=ROOT, capture_output=not serve, text=True)
    if serve:
        return completed.returncode

    # pdoc reports an unresolvable `__all__` entry as a warning and carries on, leaving a name in
    # the reference that no reader can import. That has happened once already -- two names in
    # `plumes2.chem` -- so it is treated as a failure here rather than as console noise.
    warnings = [line for line in (completed.stderr or "").splitlines() if line.startswith("Warn:")]
    if completed.stdout:
        print(completed.stdout, end="")
    for line in warnings:
        print(line, file=sys.stderr)
    if completed.returncode == 0 and not warnings:
        print(f"wrote {len(names)} modules to {OUTPUT.relative_to(ROOT)}")
    return completed.returncode or (1 if warnings else 0)


if __name__ == "__main__":
    raise SystemExit(main())
