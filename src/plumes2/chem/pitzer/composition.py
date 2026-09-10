"""Reference seawater as a PHREEQC composition, scaled with salinity.

The blending tool this engine descends from carried seawater as one hard-coded analysis at S 35.
Here the composition is a *function of salinity*, because every row of a plume has its own: the
Reference Composition of Millero et al. (2008) scaled by `S/35`, the same conservative rule
`calcium_from_salinity` and `magnesium_from_salinity` already apply -- so the two brucite engines
see **the same total magnesium by construction**, and differ only in how they get from totals to
activities.

Units are the trap. PHREEQC states a `SOLUTION` per kilogram of *water*; oceanography states
concentrations per kilogram of *solution*; the two differ by the mass of dissolved salt, ~3.5 % at
S 35. Every input here is converted to mol per kg of water, and `speciation.py`'s outputs are
converted back, so a pH compared with PyCO2SYS's is compared on one basis. Mixing the two bases
inside one block is also a PHREEQC input error (`units for master species ... not compatible`),
which is how the spike found it.

Total boron follows the case's borate option -- Uppstrom (1974) or Lee et al. (2010), the same two
PyCO2SYS offers -- so the borate alkalinity, 367 umol/kg at S 30.9, is the same in both engines.
Leaving boron out of the input is worth **+0.13 to +0.31 pH** at pH 7.7-10 (the spike's first
pass did exactly that), because PHREEQC then reads the borate alkalinity as carbonate.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.chem.constants import (
    ABSOLUTE_PER_PRACTICAL_SALINITY,
    calcium_from_salinity,
    magnesium_from_salinity,
    water_fraction,
)

__all__ = [
    "ABSOLUTE_PER_PRACTICAL_SALINITY",
    "CONSERVATIVE_CHARGE",
    "MILLERO_2008_S35",
    "TOTAL_BORON_S35",
    "conservative_charge_excess",
    "reference_seawater",
    "water_fraction",
]

#: Charge per mole of each conservative ion the composition enters. Boron is not here: it is a
#: total whose speciation PHREEQC solves, like carbon.
CONSERVATIVE_CHARGE: dict[str, int] = {
    "Na": 1,
    "K": 1,
    "Mg": 2,
    "Ca": 2,
    "Sr": 2,
    "Cl": -1,
    "S(6)": -2,
    "Br": -1,
}

#: Millero et al. (2008), Table 4: the Reference Composition of seawater at practical salinity 35,
#: mol per kg of *solution*, for the conservative major ions this engine enters by name. Magnesium
#: and calcium are not listed here: they come from `constants.py` so the two engines share them
#: (`MAGNESIUM_AT_S35` is the same Millero value; `CALCIUM_AT_S35` is the manual's 0.01028).
#: Fluoride is omitted: `pitzer.dat` has no fluorine, and at 68 umol/kg it is 0.01 % of the charge.
#: Keys are PHREEQC master-species names.
MILLERO_2008_S35: dict[str, float] = {
    "Na": 0.4686071,
    "K": 0.0102077,
    "Sr": 0.0000907,
    "Cl": 0.5458696,
    "S(6)": 0.0282352,
    "Br": 0.0008421,
}

#: Total boron at S 35, mol per kg of solution, by borate option: 1 = Uppstrom (1974), 2 = Lee et
#: al. (2010) -- PyCO2SYS's `opt_total_borate` numbering, which `ConstantSet` already carries.
TOTAL_BORON_S35: dict[int, float] = {1: 0.0004157, 2: 0.0004326}

# `water_fraction` and `ABSOLUTE_PER_PRACTICAL_SALINITY` moved to `chem/constants.py` on
# 2026-09-10, when `omega_brucite` began using the same conversion; re-exported here unchanged.


def reference_seawater(
    salinity: ArrayLike, *, borate_option: int = 1
) -> dict[str, NDArray[np.float64]]:
    """The conservative major ions plus total boron, **mol per kg of water**, at each salinity.

    Every entry scales linearly with practical salinity from the S 35 reference and is then divided
    by the water fraction, so a PHREEQC `SOLUTION` built from it and given the plume's own TA and
    DIC is the same water PyCO2SYS is handed as (TA, DIC, S, T). At S 0 every entry is zero: a
    pure-water effluent is pure water, and the dosed hydroxide's counter-ion arrives through the
    sodium charge balance (`speciation.py`).
    """
    if borate_option not in TOTAL_BORON_S35:
        raise ValueError(
            f"borate option must be one of {sorted(TOTAL_BORON_S35)}, got {borate_option}"
        )
    s = np.asarray(salinity, dtype=np.float64)
    per_kg_water = 1.0 / water_fraction(s)
    scale = s / 35.0 * per_kg_water
    out = {element: np.asarray(value * scale) for element, value in MILLERO_2008_S35.items()}
    out["Mg"] = np.asarray(magnesium_from_salinity(s) * per_kg_water)
    out["Ca"] = np.asarray(calcium_from_salinity(s) * per_kg_water)
    out["B"] = np.asarray(TOTAL_BORON_S35[borate_option] * scale)
    return out


def conservative_charge_excess(composition: dict[str, NDArray[np.float64]]) -> NDArray[np.float64]:
    """Cation minus anion equivalents of the conservative ions, eq per kg of water.

    This *is* total alkalinity by Dickson's definition -- the excess of conservative cations over
    conservative anions, balanced by the proton acceptors -- so setting sodium such that the
    excess equals the row's TA, and letting PHREEQC find the pH that makes the water electrically
    neutral, states TA exactly. For Millero's reference water the excess is 2013 ueq/kg of
    solution; its TA of 2300 minus the fluoride and hydroxide the composition does not list.
    """
    total = np.zeros_like(np.asarray(composition["Na"], dtype=np.float64))
    for element, charge in CONSERVATIVE_CHARGE.items():
        total = total + charge * np.asarray(composition[element], dtype=np.float64)
    return np.asarray(total)
