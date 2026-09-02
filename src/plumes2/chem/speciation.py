"""The carbonate solver: a thin, explicitly-tracked adapter over PyCO2SYS.

PLAN.md §4 settles the engine question. The manual says the exe's own CO2SYS routines were
"incorporated directly into PLUMES2.0" and then "validated using the latest CO2SYS software
version available in python as PYCO2SYS", so PyCO2SYS is the same lineage one generation
newer. The port therefore calls PyCO2SYS directly rather than re-deriving a pH solver, and
spends its effort on **matching and recording the constant selections** instead -- every
result carries the `ConstantSet` it was computed with.

Saturation states are computed here by `saturation.py` rather than taken from PyCO2SYS's
own `saturation_calcite` / `saturation_aragonite`. The two agree (a test asserts it), but
going through our own code keeps the manual's `[Ca++] = 0.01028 S/35` relation and the Mucci
(1983) `Ksp` visible and independently testable, which is what the exe documents.

Input pairing, measured from the reference cases
------------------------------------------------
The manual never says which two of TA, DIC and pH the exe uses when the dialog offers all
three, and the GUI refuses to run with any of them blank. The reference cases settle it:

    case03   entered TA 4000, DIC 0,    pH 10.5   ->  used TA + pH,  giving DIC 1646
    case04   entered TA 4000, DIC 1646, pH 11     ->  used TA + DIC, ignoring the pH

So **DIC wins when it is non-zero**, and pH is the fallback. The pH is on the **free
scale**: solving TA = 4000 with pH = 10.5 free gives DIC = 1646.29 against case03's
back-out of 1645.9, while the total scale gives 1608 and NBS 1670. That confirms the free
scale independently of the GUI label, to 0.02 %.

The umol/kg to umol/L slip
--------------------------
Both effluent inputs are multiplied by the effluent density in kg/L before being carried
into the plume, while the *ambient* values are not:

    case03   TA 4000 -> 4108.4        case04   TA  4000 -> 4108.4
                                               DIC 1646 -> 1690.0

Against rho(35, 10)/1000 = 1.02695 the predictions are 4107.8 and 1690.4, both inside the
+-0.6 umol/kg noise of the back-out. It is a unit-conversion bug -- a per-kilogram
concentration treated as per-litre -- and it biases the effluent endmember high by 2.7 %
while leaving the ambient alone. Off by default; see `CarbonateSettings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.chem.constants import (
    ConstantSet,
    resolve_constants,
    warn_outside_ph_window,
    warn_outside_validity,
)
from plumes2.chem.saturation import carbonate_ion, saturation_states
from plumes2.config import PHScale

__all__ = [
    "PH_SCALE_TO_PYCO2SYS",
    "CarbonateState",
    "solve_from_alkalinity_dic",
    "solve_from_alkalinity_ph",
]

#: Our scale names to PyCO2SYS `opt_pH_scale`.
PH_SCALE_TO_PYCO2SYS: dict[PHScale, int] = {
    PHScale.TOTAL: 1,
    PHScale.SEAWATER: 2,
    PHScale.FREE: 3,
    PHScale.NBS: 4,
}


@dataclass(frozen=True, slots=True)
class CarbonateState:
    """A solved carbonate system. Concentrations in umol/kg, pH dimensionless."""

    total_alkalinity: NDArray[np.float64]
    dic: NDArray[np.float64]
    ph_total: NDArray[np.float64]
    ph_free: NDArray[np.float64]
    ph_seawater: NDArray[np.float64]
    carbonate: NDArray[np.float64]
    bicarbonate: NDArray[np.float64]
    #: Partial pressure of CO2, uatm. Not used by the near field -- carried because it is
    #: what a reader wants alongside pH, and PyCO2SYS solves it anyway.
    pco2: NDArray[np.float64]
    #: Hydroxide, umol/kg. Taken straight from PyCO2SYS so it is consistent with the `Kw`
    #: and pH scale it solved on -- see `omega_brucite`, where `[OH-]` enters squared and a
    #: scale mismatch would be a silent factor rather than an error.
    hydroxide: NDArray[np.float64]
    aqueous_co2: NDArray[np.float64]
    omega_calcite: NDArray[np.float64]
    omega_aragonite: NDArray[np.float64]
    salinity: NDArray[np.float64]
    temperature: NDArray[np.float64]
    constants: ConstantSet

    def omega_brucite(self, solubility: ArrayLike) -> NDArray[np.float64]:
        """Brucite saturation state for this solved system (PLAN.md §8b).

        Handles the unit change -- this class carries concentrations in umol/kg while the
        saturation arithmetic works in mol/kg -- so the common path cannot get it wrong.
        `solubility` is `Ksp*` in mol^3/kg^3 and is deliberately required; see
        `saturation.omega_brucite` for why nothing is defaulted.
        """
        from plumes2.chem.saturation import omega_brucite

        return omega_brucite(self.hydroxide * 1e-6, self.salinity, solubility)

    def ph(self, scale: PHScale = PHScale.TOTAL) -> NDArray[np.float64]:
        """pH on the requested scale.

        Which scale the exe *reports* is fixed by its own dialog rule, "pH scale will be
        the same as K1,K2": with the default option 10 (Lueker et al. 2000) that is the
        **total** scale, which is this method's default. `ConstantSet.native_ph_scale`
        carries it per option, so a run on option 6 reports NBS and one on option 4
        reports seawater.

        The reference data alone could not have settled this -- the printed column sits
        0.011-0.024 below PyCO2SYS on total and 0.003-0.016 below on seawater, with the
        same spread either way. It does firmly exclude free (-0.087) and NBS (-0.130).
        """
        match scale:
            case PHScale.TOTAL:
                return self.ph_total
            case PHScale.FREE:
                return self.ph_free
            case PHScale.SEAWATER:
                return self.ph_seawater
            case PHScale.NBS:
                raise ValueError(
                    "the NBS scale is excluded by the reference data (0.13 pH units off) "
                    "and is not carried; use total, seawater or free"
                )
        raise ValueError(f"unknown pH scale: {scale}")


def _run(
    par1: ArrayLike,
    par2: ArrayLike,
    par1_type: int,
    par2_type: int,
    salinity: ArrayLike,
    temperature: ArrayLike,
    pressure: ArrayLike,
    constants: ConstantSet,
    input_ph_scale: PHScale,
    context: str = "carbonate chemistry",
) -> CarbonateState:
    """One PyCO2SYS call, packaged with our own saturation states.

    ⭐ **The one chokepoint every speciation call passes through**, which is why the validity check
    lives here rather than in each of the four public entry points. `ValidityRange.covers` and
    `ConstantSet.covers` existed and were tested from the day the constants were decoded, but
    nothing called them, so a plume that left Lueker's S 19-43 extrapolated silently -- half a
    feature, and the missing half was the half that warns (PLAN.md Phase 8.2).
    """
    import PyCO2SYS as pyco2

    warn_outside_validity(constants, salinity, temperature, context=context)

    shared: dict[str, Any] = {
        "salinity": salinity,
        "temperature": temperature,
        "pressure": pressure,
        "opt_k_carbonic": constants.pyco2sys_k_carbonic,
        "opt_k_bisulfate": constants.pyco2sys_k_bisulfate,
        # The exe's KSO4 selector also picks the total-borate ratio; PyCO2SYS keeps the
        # two apart, so both halves have to be passed. Borate is not a detail at these
        # pH values -- switching Uppstrom to Lee moves pH by 0.015 at pH 10.4.
        "opt_total_borate": constants.pyco2sys_total_borate,
    }
    # `opt_pH_scale` sets the scale of the *input* pH and of the returned K1/K2. eq 21
    # needs pH and the constants on one scale, so when the input is on some other scale a
    # second, total-scale pass supplies matching constants. Skipped when already total.
    scale_option = PH_SCALE_TO_PYCO2SYS[input_ph_scale]
    result = pyco2.sys(
        par1=par1,
        par2=par2,
        par1_type=par1_type,
        par2_type=par2_type,
        opt_pH_scale=scale_option,
        **shared,
    )
    if scale_option == 1:
        total_scale = result
    else:
        total_scale = pyco2.sys(
            par1=par1,
            par2=par2,
            par1_type=par1_type,
            par2_type=par2_type,
            opt_pH_scale=1,
            **shared,
        )

    def column(key: str) -> NDArray[np.float64]:
        return np.asarray(result[key], dtype=np.float64)

    ph_total = column("pH_total")
    # The second check at the chokepoint, added 2026-08-25 after the dose dry run solved pH-12
    # seawater in silence: the S/T window above is where the constants were *fitted*, this is
    # where the result has been *compared* to anything (PLAN §8f).
    warn_outside_ph_window(ph_total, context=context)
    salinity_arr = np.asarray(salinity, dtype=np.float64)
    temperature_arr = np.asarray(temperature, dtype=np.float64)
    carbonate = carbonate_ion(
        np.asarray(total_scale["dic"], dtype=np.float64) * 1e-6,
        ph_total,
        np.asarray(total_scale["k_carbonic_1"], dtype=np.float64),
        np.asarray(total_scale["k_carbonic_2"], dtype=np.float64),
    )
    omega_calcite, omega_aragonite = saturation_states(carbonate, salinity_arr, temperature_arr)

    return CarbonateState(
        total_alkalinity=column("alkalinity"),
        dic=column("dic"),
        ph_total=ph_total,
        ph_free=column("pH_free"),
        ph_seawater=column("pH_sws"),
        carbonate=carbonate * 1e6,
        bicarbonate=column("HCO3"),
        hydroxide=column("OH"),
        pco2=column("pCO2"),
        aqueous_co2=column("CO2"),
        omega_calcite=omega_calcite,
        omega_aragonite=omega_aragonite,
        salinity=salinity_arr,
        temperature=temperature_arr,
        constants=constants,
    )


def solve_from_alkalinity_dic(
    total_alkalinity: ArrayLike,
    dic: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    pressure: ArrayLike = 0.0,
    constants: ConstantSet | None = None,
    context: str = "carbonate chemistry",
) -> CarbonateState:
    """Solve from TA and DIC, both umol/kg. The exe's preferred pairing.

    `pressure` is dbar of *water* above the sample; the exe evaluates at the surface
    regardless of port depth, which at PLUMES depths shifts Omega by well under a percent.
    """
    return _run(
        total_alkalinity,
        dic,
        1,
        2,
        salinity,
        temperature,
        pressure,
        constants or resolve_constants(),
        PHScale.TOTAL,
        context=context,
    )


def solve_from_alkalinity_ph(
    total_alkalinity: ArrayLike,
    ph: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    ph_scale: PHScale = PHScale.FREE,
    pressure: ArrayLike = 0.0,
    constants: ConstantSet | None = None,
    context: str = "carbonate chemistry",
) -> CarbonateState:
    """Solve from TA and pH. The default scale is free, as the exe's dialog labels it."""
    return _run(
        total_alkalinity,
        ph,
        1,
        3,
        salinity,
        temperature,
        pressure,
        constants or resolve_constants(),
        ph_scale,
        context=context,
    )
