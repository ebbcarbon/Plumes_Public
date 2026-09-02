"""Carbonate chemistry: PyCO2SYS speciation, saturation states and precipitation rates.

Unaffected by the UM theory reference (`references/`): carbonate chemistry is a PLUMES2.0
addition with no counterpart in Baumgartner et al. (1994), which predates it by 30 years.


`constants.py` pins and records which parameterisations a run used, `speciation.py` wraps
PyCO2SYS, `saturation.py` carries the manual's Omega arithmetic, `precipitation.py` the
Zhong & Mucci rate laws, and `transport.py` the conservative mixing of TA and DIC.
"""

from __future__ import annotations

from plumes2.chem.constants import (
    CALCIUM_AT_S35,
    EXE_K1K2_OPTIONS,
    EXE_KSO4_OPTIONS,
    ConstantSet,
    K1K2Option,
    KSO4Option,
    UnknownConstantOptionError,
    ValidityRange,
    calcium_from_salinity,
    davies_activity_coefficient,
    ionic_strength_from_salinity,
    magnesium_from_salinity,
    resolve_constants,
    solubility_aragonite,
    solubility_brucite,
    solubility_calcite,
    warn_outside_ph_window,
    warn_outside_validity,
)
from plumes2.chem.precipitation import (
    ARAGONITE_HIGH_SALINITY,
    ARAGONITE_LOW_SALINITY,
    ARAGONITE_LOW_SALINITY_AS_DIALOGUED,
    CALCITE,
    Mineral,
    RateLaw,
    aragonite_laws,
    precipitation_rate,
)
from plumes2.chem.saturation import (
    carbonate_ion,
    omega_aragonite,
    omega_brucite,
    omega_calcite,
    saturation_states,
)
from plumes2.chem.speciation import (
    CarbonateState,
    solve_from_alkalinity_dic,
    solve_from_alkalinity_ph,
)
from plumes2.chem.transport import Endmember, effluent_endmember, mix, plume_carbonate

__all__ = [
    "ARAGONITE_HIGH_SALINITY",
    "ARAGONITE_LOW_SALINITY",
    "ARAGONITE_LOW_SALINITY_AS_DIALOGUED",
    "CALCITE",
    "CALCIUM_AT_S35",
    "EXE_K1K2_OPTIONS",
    "EXE_KSO4_OPTIONS",
    "CarbonateState",
    "ConstantSet",
    "Endmember",
    "K1K2Option",
    "KSO4Option",
    "Mineral",
    "RateLaw",
    "UnknownConstantOptionError",
    "ValidityRange",
    "aragonite_laws",
    "calcium_from_salinity",
    "carbonate_ion",
    "davies_activity_coefficient",
    "effluent_endmember",
    "ionic_strength_from_salinity",
    "magnesium_from_salinity",
    "mix",
    "omega_aragonite",
    "omega_brucite",
    "omega_calcite",
    "plume_carbonate",
    "precipitation_rate",
    "resolve_constants",
    "saturation_states",
    "solubility_aragonite",
    "solubility_brucite",
    "solubility_calcite",
    "solve_from_alkalinity_dic",
    "solve_from_alkalinity_ph",
    "warn_outside_ph_window",
    "warn_outside_validity",
]
