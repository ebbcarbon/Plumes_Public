"""Carbonate ion and the calcite/aragonite saturation states (manual eqs 19-21).

Kept free of PyCO2SYS so that the saturation arithmetic is testable on its own, given
`K1`/`K2` from any source. `speciation.py` supplies those from PyCO2SYS.

The manual's chain is

    [CO3--] = DIC * K1 K2 / (H^2 + K1 H + K1 K2)          (eq 21)
    Omega_calcite   = [Ca++][CO3--] / Ksp_calcite         (eq 19)
    Omega_aragonite = [Ca++][CO3--] / Ksp_aragonite       (eq 20)

with `[Ca++] = 0.01028 * S/35` and `Ksp` from Mucci (1983) -- see `constants.py`.

**How close is this to the exe?** Measured against `case03`, reconstructing the plume's
mixed salinity and temperature from the printed dilution:

    Ksp_aragonite / Ksp_calcite   ours == PyCO2SYS exactly; exe differs by 0.09 %
    Omega (given the exe's own pH) ours is 0.8 - 2.6 % high, growing with pH
    Omega (from TA and DIC)        ours is a near-constant 3.3 % high
    pH (from TA and DIC)           exe is 0.011 - 0.024 below PyCO2SYS (total scale)

So the exe's carbonate system agrees with PyCO2SYS to about 0.02 pH units and a few
percent in Omega. The residual is a genuine constant/solver difference in the exe's
embedded CO2SYS, not a unit or scale error -- the offsets persist at high dilution where
the plume is essentially ambient water, so they cannot come from the salinity and
temperature reconstruction. Per PLAN.md the port follows PyCO2SYS and records the gap
rather than tuning to it.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.chem.constants import (
    calcium_from_salinity,
    magnesium_from_salinity,
    solubility_aragonite,
    solubility_calcite,
    water_fraction,
)

__all__ = [
    "carbonate_ion",
    "omega_aragonite",
    "omega_calcite",
    "saturation_states",
]


def carbonate_ion(
    dic: ArrayLike,
    ph: ArrayLike,
    k1: ArrayLike,
    k2: ArrayLike,
) -> NDArray[np.float64]:
    """`[CO3--]` in mol/kg from DIC in **mol/kg** and pH (eq 21).

    `ph` must be on the same scale as `k1` and `k2`. Note the units: the exe's tables and
    the CSV files carry umol/kg, so divide by 1e6 before calling.
    """
    dic_arr = np.asarray(dic, dtype=np.float64)
    k1_arr = np.asarray(k1, dtype=np.float64)
    k2_arr = np.asarray(k2, dtype=np.float64)
    hydrogen = 10.0 ** -np.asarray(ph, dtype=np.float64)
    denominator = hydrogen * hydrogen + k1_arr * hydrogen + k1_arr * k2_arr
    return np.asarray(dic_arr * k1_arr * k2_arr / denominator)


def omega_calcite(
    carbonate: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
) -> NDArray[np.float64]:
    """Calcite saturation state (eq 19); `carbonate` in mol/kg."""
    calcium = calcium_from_salinity(salinity)
    return np.asarray(
        calcium
        * np.asarray(carbonate, dtype=np.float64)
        / solubility_calcite(salinity, temperature)
    )


def omega_aragonite(
    carbonate: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
) -> NDArray[np.float64]:
    """Aragonite saturation state (eq 20); `carbonate` in mol/kg."""
    calcium = calcium_from_salinity(salinity)
    return np.asarray(
        calcium
        * np.asarray(carbonate, dtype=np.float64)
        / solubility_aragonite(salinity, temperature)
    )


def saturation_states(
    carbonate: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Both saturation states at once, `(calcite, aragonite)`."""
    return (
        omega_calcite(carbonate, salinity, temperature),
        omega_aragonite(carbonate, salinity, temperature),
    )


def omega_brucite(
    hydroxide: ArrayLike,
    salinity: ArrayLike,
    solubility: ArrayLike,
) -> NDArray[np.float64]:
    """Brucite saturation state, `m(Mg2+) m(OH-)^2 / Ksp*`; `hydroxide` in mol per kg of solution.

    ✅ **Formed on the molal scale (2026-09-10).** `hydroxide` arrives per kilogram of
    *solution*, as PyCO2SYS reports it, and so does `magnesium_from_salinity`; `Ksp*` is defined
    per kilogram of *water*. Both concentrations are divided by `water_fraction(S)` before the
    product is taken, so the three concentration factors and the constant share one basis. Until
    this date the product was formed per kg of solution, which read `water_fraction**3` -- 0.91 at
    S 30.9, 0.90 at S 35 -- *below* the same physics on one basis; that was the one bias in this
    column that pointed down (PHREEQC_PLAN.md section 8, ledger row 289). In pure water the two
    bases coincide and nothing changes.

    ⭐ **The exe cannot report this**, and for an alkalinity-elevated discharge it is the
    saturation state that matters most: when the feedstock is Mg(OH)2, or whenever the
    near-field pH spike is large enough, the plume can go supersaturated in **brucite** and
    precipitate away the alkalinity the discharge was meant to deliver. `omega_aragonite`
    cannot see that happening. See PLAN.md §8b.

    ⚠️ **`solubility` is required, not defaulted.** `Ksp*` for brucite in seawater is a
    genuine choice -- a stoichiometric constant folding in activity coefficients and ion
    pairing, as Mucci's is for aragonite, is *not* the same as a thermodynamic `Ksp` used with
    free concentrations, and picking one silently would put an unsourced number at the centre
    of the result this project exists to produce. Supply it explicitly, in `mol^3 / kg^3`, and
    cite it where it is defined.

    ⚠️ **`hydroxide` must come from the same speciation solve as everything else.** `[OH-]`
    enters *squared*, so a pH-scale mismatch is a silent multiplicative error rather than a
    visible one -- a 0.02 pH-unit slip is about 10 % in Omega. `CarbonateState.hydroxide`
    takes it straight from PyCO2SYS, consistent with the `Kw` and pH scale it solved on.

    ⚠️ **Omega is a thermodynamic statement, not a rate.** Supersaturation is necessary but
    not sufficient for precipitation: there is a nucleation barrier, and seawater sits
    supersaturated in aragonite as a matter of course. Do not infer alkalinity loss from this
    number without a kinetic model.
    """
    oh = np.asarray(hydroxide, dtype=np.float64)
    ksp = np.asarray(solubility, dtype=np.float64)
    if np.any(oh < 0):
        raise ValueError("hydroxide must be non-negative")
    if np.any(ksp <= 0):
        raise ValueError("the brucite solubility product must be positive")
    # Per kg of solution -> per kg of water, so the product sits on the constant's own scale.
    per_kg_water = 1.0 / water_fraction(salinity)
    magnesium = magnesium_from_salinity(salinity) * per_kg_water
    oh_molal = oh * per_kg_water
    return np.asarray(magnesium * oh_molal * oh_molal / ksp)
