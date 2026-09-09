"""plumes2 -- a Python re-implementation of PLUMES2.0.

An outfall plume model: a near-field UM3 Lagrangian control-volume solver, the Brooks (1960) far
field, carbonate chemistry on PyCO2SYS, and dissolved oxygen. It exists because Ebb needs to predict
pH in the plume of an **alkalinity-elevated discharge**, and the reference implementation -- a
Windows executable from SSMC -- cannot report the quantity that matters most for one (see
`plumes2.chem.saturation.omega_brucite`).

## Thirty seconds

    from plumes2 import load_case, run

    case = load_case("case.yaml")                  # or load_project("project.prj").to_case()
    results = run(case)                            # .nearfield, .farfield, both DataFrames
    print(results.nearfield[["time_s", "dilution", "plume_diameter_m"]].tail())

`examples/` in the repository holds this as a runnable script, including assembling the case
from plain CSV ambient tables (`ambient_from_files`) instead of a YAML file.

Or from a shell, without writing any Python:

    plumes2 run CASE -o out/      tidy CSVs at full precision, with a provenance sidecar
    plumes2 report CASE           one PDF of explained panels (HTML with an .html path)
    plumes2 validate -o v.pdf     the validation ledger, executed
    plumes2 info CASE             what a case contains, without running it
    plumes2 convert CASE          .prj <-> .yaml
    plumes2 farfield ...          the standalone Brooks calculator

## Where things are

| module | what it holds |
|---|---|
| `plumes2.config` | the validated `Case` -- every input, with its units and its physical range |
| `plumes2.io` | `.prj`, `.dat` and the six CSV tables, all round-tripping byte-exactly |
| `plumes2.nearfield` | the LCV solver: entrainment, merging, termination |
| `plumes2.farfield` | Brooks, and the exe's standalone far-field calculator |
| `plumes2.chem` | speciation, saturation states (including brucite), precipitation rates |
| `plumes2.biochem` | dissolved oxygen and BOD |
| `plumes2.results` | `run()` -- the thing most callers want |
| `plumes2.report` | the reports, PDF or HTML |
| `plumes2.validation` | the executable ledger: every claim, its reference, its tolerance |

## Reading this reference

⚠️ **The docstrings carry the findings, not just the signatures.** This is a port of a program whose
source is unavailable, so most of what was learned was learned by measuring traces -- and it is
written beside the code that encodes it. Where the exe departs from its own manual, the docstring
says which reading the traces chose and by how much. Those notes are the actual work; the
signatures are the easy part.

⚠️ **`reproduce_*` flags mark defects, not preferences.** Several exe behaviours are wrong and are
reproduced only on request -- an undiluted far-field BOD, an IDOD applied to the ambient, a NaN for
an undersaturated mineral. The default is always the corrected form. Each flag's docstring says what
the exe does, what the manual says, and what the traces measured.

⚠️ **Not everything here has a reference to check against.** `Omega_brucite` is the clearest case:
the exe cannot compute it, so there is no trace to compare with, and `plumes2.validation` labels
that evidence `internal` rather than `golden`. Trust the labels.

See `PLAN.md` for the build order and the full ledger, `PORTING_NOTES.md` for the specification
this was derived from, and `reference_cases/` for the exe runs every number is measured against.
"""

from __future__ import annotations

#: Defined before the imports below: `plumes2.provenance` (reached through
#: `plumes2.results`) does `from plumes2 import __version__` while this module is still
#: executing, so the name has to exist first.
__version__ = "0.0.1.dev0"

from plumes2.config import Case
from plumes2.io import (
    ambient_from_files,
    dump_case,
    load_case,
    load_project,
    read_dat,
    read_prj,
)
from plumes2.results import (
    mixing_zone_values,
    run,
    sample_at_distance,
    write_results,
)
from plumes2.sweep import sweep, with_updated

__all__ = [
    "Case",
    "__version__",
    "ambient_from_files",
    "dump_case",
    "load_case",
    "load_project",
    "mixing_zone_values",
    "read_dat",
    "read_prj",
    "run",
    "sample_at_distance",
    "sweep",
    "with_updated",
    "write_results",
]
