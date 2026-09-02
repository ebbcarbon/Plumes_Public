"""Carbonate transport through the plume: what mixes conservatively, and what does not.

Total alkalinity and DIC are conservative with respect to mixing -- unlike pH and the
saturation states, which have to be re-solved at every step from the mixed pair. The manual
states this (eqs 17-18) and the reference data confirms it to the last printed digit.

The check, on `case03` and `case04`: fit the *single* effluent endmember that best explains
every printed row, given the CSV ambient profile and the printed dilution, and look at what
is left over. One scalar reproduces all 41 rows to

    TA    1.12 umol/kg worst case   (0.036 %)
    DIC   0.68 umol/kg worst case   (0.029 %)

which is the precision of the two-decimal printed columns once the ambient interpolation is
accounted for -- the plume sits at 1.98 - 2.34 m where the CSV's TA gradient is
100 umol/kg/m. Inverting the other way, the seventeen rows above dilution 25 return
TA = 2900.02 - 2900.38 and DIC = 2499.93 - 2500.00 against CSV values of exactly 2900 and
2500. So mixing is a plain dilution-weighted average on a per-mass basis, with no
volumetric or density weighting.

**This supersedes an earlier reading of the same data.** A previous pass concluded the exe
must advect TA and DIC stepwise through the LCV loop, accumulating about 7 ppm per step,
because the implied endmember appeared to drift 0.26 % monotonically along the run. It does
not: that drift is what a slightly-wrong endmember estimate looks like, because the
inversion's sensitivity to the endmember is `1/(D - 1)` and so decays with dilution exactly
as the apparent drift did. Fitting the endmember instead of assuming it removes the trend
entirely. Concentrations can therefore be computed algebraically from the dilution, which
means the chemistry stays a genuine post-hoc overlay on the trajectory and Phase 5 need not
carry scalars through its integrator.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.chem.constants import ConstantSet, resolve_constants
from plumes2.chem.speciation import (
    CarbonateState,
    solve_from_alkalinity_dic,
    solve_from_alkalinity_ph,
)
from plumes2.config import CarbonateSettings, EffluentChemistry
from plumes2.seawater import density

__all__ = [
    "Endmember",
    "effluent_endmember",
    "mix",
    "plume_carbonate",
]


@dataclass(frozen=True, slots=True)
class Endmember:
    """A conservative carbonate endmember, umol/kg."""

    total_alkalinity: float
    dic: float
    #: True when `dic` was derived from TA and pH rather than entered directly.
    dic_derived_from_ph: bool = False
    #: The factor applied to reproduce the exe's umol/kg to umol/L slip, else 1.0.
    concentration_scaling: float = 1.0


def effluent_endmember(
    chemistry: EffluentChemistry,
    salinity: float,
    temperature: float,
    *,
    settings: CarbonateSettings | None = None,
    constants: ConstantSet | None = None,
) -> Endmember:
    """Resolve the effluent to a conservative `(TA, DIC)` pair.

    Mirrors the exe's pairing: DIC is used when given, and pH is the fallback -- see
    `speciation.py` for the case03/case04 measurement that establishes this. When
    `settings.reproduce_effluent_concentration_scaling` is set, both values are multiplied
    by the effluent density in kg/L, reproducing the exe's unit slip.
    """
    settings = settings or CarbonateSettings()
    total_alkalinity = float(chemistry.total_alkalinity)
    derived = False

    if chemistry.dic is not None:
        dic = float(chemistry.dic)
    else:
        assert chemistry.ph is not None  # guaranteed by EffluentChemistry's validator
        state = solve_from_alkalinity_ph(
            total_alkalinity,
            chemistry.ph,
            salinity,
            temperature,
            ph_scale=chemistry.ph_scale,
            constants=constants or resolve_constants(
                settings.k1k2_option, settings.kso4_option
            ),
            # ⚠️ The effluent is the sample most likely to be outside the window, and the one
            # the user chose: case07's is 45 psu against Lueker's 43. Labelled separately from
            # the plume so the message says which end of the mixing line is the extrapolation.
            context="effluent endmember",
        )
        dic = float(state.dic)
        derived = True

    scaling = 1.0
    if settings.reproduce_effluent_concentration_scaling:
        scaling = float(density(salinity, temperature, 0.0)) / 1000.0
        total_alkalinity *= scaling
        # case03 shows a DIC that the model derived itself escapes the scaling; only
        # user-entered values are affected.
        if not derived:
            dic *= scaling

    return Endmember(
        total_alkalinity=total_alkalinity,
        dic=dic,
        dic_derived_from_ph=derived,
        concentration_scaling=scaling,
    )


def mix(effluent: ArrayLike, ambient: ArrayLike, dilution: ArrayLike) -> NDArray[np.float64]:
    """Dilution-weighted mixing: one part effluent to `D - 1` parts ambient.

    `dilution` is the exe's `Dilutn` column, so `D = 1` is undiluted effluent.
    """
    dilution_arr = np.asarray(dilution, dtype=np.float64)
    if np.any(dilution_arr < 1.0):
        raise ValueError("dilution must be at least 1 (1 means undiluted effluent)")
    effluent_arr = np.asarray(effluent, dtype=np.float64)
    ambient_arr = np.asarray(ambient, dtype=np.float64)
    return np.asarray(
        (effluent_arr + (dilution_arr - 1.0) * ambient_arr) / dilution_arr
    )


def plume_carbonate(
    endmember: Endmember,
    ambient_alkalinity: ArrayLike,
    ambient_dic: ArrayLike,
    dilution: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    pressure: ArrayLike = 0.0,
    constants: ConstantSet | None = None,
) -> CarbonateState:
    """Mix, then re-solve: the full carbonate state along a plume trajectory.

    `salinity` and `temperature` are the *mixed* plume values, which the caller already has
    from the near-field solution.
    """
    return solve_from_alkalinity_dic(
        mix(endmember.total_alkalinity, ambient_alkalinity, dilution),
        mix(endmember.dic, ambient_dic, dilution),
        salinity,
        temperature,
        pressure=pressure,
        constants=constants,
        context="plume trajectory",
    )
