"""The PHREEQC engine: constructed once, re-parameterised once, described on every result.

PHREEQC (Parkhurst & Appelo, USGS) is driven through `phreeqpython`, whose wheel bundles the
IPhreeqc library and the thermodynamic databases, so nothing is looked for on `PATH`. It is an
**optional dependency** (`pip install 'plumes2[pitzer]'`): the import is guarded, a case that does
not ask for the Pitzer column never touches it, and a case that does gets one clear error when it
is missing.

One thing is changed from the database as shipped, and it is stated in the record every result
carries: **Brucite** is re-parameterised to Xiong (2008)'s `log Ksp` -10.95 and this repo's
dissolution enthalpy (-2.29 kJ/mol, from formation enthalpies -- `constants.py`), replacing
`pitzer.dat`'s -10.88 and **+4.85 kcal/mol, the wrong sign for a retrograde mineral**. With that,
the two brucite engines share every constant and differ only in the activity treatment -- which is
the whole point of having two. Nothing else is touched: `pitzer.dat` already carries boron (pKa
9.239 and the Mg/Ca borate pairs) and strontium. (The spike's run-time boron block turned out to
be redefining species the database had, and is gone.)

⚠️ The database's MgOH+ formation constant (`Mg+2 + H2O = MgOH+ + H+`, `log_k` -11.809, i.e.
log beta ≈ 2.19 for `Mg+2 + OH- = MgOH+` at 25 C) is the largest single term in the Pitzer/Davies
brucite ratio (PHREEQC_PLAN.md §8) and is a *database* value: `phreeqc.dat` carries -11.44
(log beta 2.56), and the literature spans 2.2-2.6. Recorded here so it is not mistaken for a
measurement in this water.
"""

from __future__ import annotations

import functools
import importlib
import importlib.metadata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plumes2.chem.constants import BRUCITE_DISSOLUTION_ENTHALPY, BRUCITE_LOG_KSP_25C

if TYPE_CHECKING:
    from phreeqpython import PhreeqPython

__all__ = [
    "DATABASE",
    "PITZER_EXTRA",
    "PitzerRecord",
    "PitzerUnavailableError",
    "available",
    "brucite_phases_block",
    "engine",
    "record",
]

#: The database. The only bundled one valid from dilute water to concentrated caustic that also
#: carries Brucite -- `phreeqc.dat` has no Brucite phase at all.
DATABASE = "pitzer.dat"

#: How to install what is missing, for the error message.
PITZER_EXTRA = "pip install 'plumes2[pitzer]'   (the phreeqpython package)"

_KCAL_PER_JOULE = 1.0 / 4184.0


class PitzerUnavailableError(ImportError):
    """The Pitzer engine was asked for and `phreeqpython` is not installed."""


def available() -> bool:
    """Whether `phreeqpython` can be imported. Cheap; does not build an engine."""
    try:
        importlib.import_module("phreeqpython")
    except ImportError:
        return False
    return True


def brucite_phases_block(
    *,
    log_ksp_25c: float = BRUCITE_LOG_KSP_25C,
    enthalpy_j_mol: float = BRUCITE_DISSOLUTION_ENTHALPY,
) -> str:
    """The `PHASES` block that re-parameterises Brucite, in PHREEQC's own units (kcal/mol)."""
    return (
        "PHASES\nBrucite\n\tMg(OH)2 = Mg+2 + 2 OH-\n"
        f"\tlog_k\t{log_ksp_25c}\n"
        f"\t-delta_H\t{enthalpy_j_mol * _KCAL_PER_JOULE:.5f} kcal/mol\n"
    )


@dataclass(frozen=True, slots=True)
class PitzerRecord:
    """What the Pitzer engine was, for provenance. Carried on every `PitzerState`."""

    database: str
    phreeqpython_version: str
    brucite_log_ksp_25c: float
    brucite_enthalpy_j_mol: float
    composition_reference: str = "Millero et al. (2008) Reference Composition, scaled S/35"
    magnesium_hydroxide_log_k: float = -11.809

    def describe(self) -> str:
        return (
            f"PHREEQC via phreeqpython {self.phreeqpython_version}, {self.database}; Brucite "
            f"log Ksp {self.brucite_log_ksp_25c} (Xiong 2008), dH "
            f"{self.brucite_enthalpy_j_mol / 1000:.2f} kJ/mol; {self.composition_reference}; "
            f"MgOH+ log_k {self.magnesium_hydroxide_log_k} (database)"
        )


@functools.cache
def engine() -> PhreeqPython:
    """The one engine, built on first use with Brucite re-parameterised.

    Cached for the process: constructing IPhreeqc and reading the database costs ~100 ms, a
    solve costs ~1 ms, and the engine holds no per-case state -- `speciation.py` deletes every
    solution it defines before returning.
    """
    if not available():
        raise PitzerUnavailableError(
            f"the Pitzer brucite column needs phreeqpython, which is not installed: {PITZER_EXTRA}"
        )
    from phreeqpython import PhreeqPython

    pp: Any = PhreeqPython(database=DATABASE)
    pp.ip.run_string(brucite_phases_block())
    return pp


def record() -> PitzerRecord:
    """The record for the engine as configured, without building it."""
    try:
        version = importlib.metadata.version("phreeqpython")
    except importlib.metadata.PackageNotFoundError:
        version = "not installed"
    return PitzerRecord(
        database=DATABASE,
        phreeqpython_version=version,
        brucite_log_ksp_25c=BRUCITE_LOG_KSP_25C,
        brucite_enthalpy_j_mol=BRUCITE_DISSOLUTION_ENTHALPY,
    )
