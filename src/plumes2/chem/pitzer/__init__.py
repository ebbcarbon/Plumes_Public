"""The second brucite engine: PHREEQC with `pitzer.dat`, an ion-interaction activity model.

Optional (`pip install 'plumes2[pitzer]'`) and **opt-in per case** (`CarbonateSettings.pitzer`).
It does not replace PyCO2SYS: pH and the carbonate saturation states stay with the engine whose
parity to the exe is measured. It adds `omega_brucite_phreeqc` beside `omega_brucite`, and the two
are kept side by side permanently -- their ratio is the measured size of the activity and
ion-pairing terms that the Davies column can only bound (PHREEQC_PLAN.md; PORTING_THE_PHYSICS §4).

`composition.py` builds reference seawater at a salinity, `engine.py` holds the one
re-parameterised PHREEQC instance, `speciation.py` solves a frame's rows in one call.
"""

from __future__ import annotations

from plumes2.chem.pitzer.composition import (
    ABSOLUTE_PER_PRACTICAL_SALINITY,
    CONSERVATIVE_CHARGE,
    MILLERO_2008_S35,
    TOTAL_BORON_S35,
    conservative_charge_excess,
    reference_seawater,
    water_fraction,
)
from plumes2.chem.pitzer.engine import (
    DATABASE,
    PITZER_EXTRA,
    PitzerRecord,
    PitzerUnavailableError,
    available,
    brucite_phases_block,
    engine,
    record,
)
from plumes2.chem.pitzer.speciation import PitzerConvergenceWarning, PitzerState, solve_pitzer

__all__ = [
    "ABSOLUTE_PER_PRACTICAL_SALINITY",
    "CONSERVATIVE_CHARGE",
    "DATABASE",
    "MILLERO_2008_S35",
    "PITZER_EXTRA",
    "TOTAL_BORON_S35",
    "PitzerConvergenceWarning",
    "PitzerRecord",
    "PitzerState",
    "PitzerUnavailableError",
    "available",
    "brucite_phases_block",
    "conservative_charge_excess",
    "engine",
    "record",
    "reference_seawater",
    "solve_pitzer",
    "water_fraction",
]
