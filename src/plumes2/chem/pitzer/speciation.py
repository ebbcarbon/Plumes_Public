"""One batched PHREEQC call per array: the Pitzer brucite saturation state and its parts.

Every row of a plume becomes a `SOLUTION` block -- the reference composition at the row's
salinity, its TA as `Alkalinity`, its DIC as `C(4)`, sodium closing the charge -- and one
`run_string` solves them all with a `SELECTED_OUTPUT` naming what comes back. ~1 ms per row either
way (the spike measured single and batched alike); batching is for the call overhead and so the
engine is asked once per frame, not once per sample. The solutions are deleted at the end of the
same input, so the engine does not grow.

What is read back, and why each:

* `si_Brucite` -- the result. `Omega = 10**SI`, with SI in *activities* against the re-parameterised
  `Ksp`, so no unit conversion touches it.
* the pH on three scales. PHREEQC's own pH is the NBS/activity scale; the free and total scales
  are built from the molalities (`m(H+)`, `m(H+) + m(HSO4-)`), converted to per kg of *solution*,
  so `ph_total` is on PyCO2SYS's basis and the two can be laid side by side. Fluoride is not in the
  database, so the seawater scale's `HF` term cannot be formed and that scale is not offered.
* free hydroxide, free magnesium, the MgOH+ pair, and the two activity coefficients -- the terms of
  the Pitzer/Davies ratio (PHREEQC_PLAN.md §8), so a reader can see *why* the two columns differ,
  row by row.

**How TA enters.** Not through PHREEQC's `Alkalinity` keyword. That keyword and Dickson's definition
give the identical number for this water (checked to 0.1 ueq/kg), but when DIC is zero PHREEQC
treats alkalinity as a *carbon* constraint and leaves the pH at its starting guess -- and DIC 0 is
exactly the pure-water NaOH effluent the dose study states. So TA enters the way Dickson defines
it: sodium is set so that the conservative-ion charge excess equals the row's TA, DIC and boron
enter as totals, and `pH charge` makes pH the one unknown that closes the electroneutrality. At
S 0 the sodium *is* the dose. Every total is converted to per kg of water first; converting TA and
not DIC was worth +0.2 pH in the first draft.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.chem.pitzer.composition import (
    conservative_charge_excess,
    reference_seawater,
    water_fraction,
)
from plumes2.chem.pitzer.engine import PitzerRecord, engine, record

__all__ = [
    "PitzerConvergenceWarning",
    "PitzerState",
    "solve_pitzer",
]


class PitzerConvergenceWarning(UserWarning):
    """PHREEQC failed on one or more rows; those rows are NaN, the others are real."""


@dataclass(frozen=True, slots=True)
class PitzerState:
    """A solved Pitzer speciation. Concentrations umol per kg of solution; pH dimensionless."""

    total_alkalinity: NDArray[np.float64]
    dic: NDArray[np.float64]
    salinity: NDArray[np.float64]
    temperature: NDArray[np.float64]
    #: PHREEQC's own pH: the activity (NBS) scale.
    ph_nbs: NDArray[np.float64]
    ph_free: NDArray[np.float64]
    ph_total: NDArray[np.float64]
    ionic_strength: NDArray[np.float64]
    si_brucite: NDArray[np.float64]
    omega_brucite: NDArray[np.float64]
    #: PHREEQC's carbonate minerals: on the site water 2 % above Mucci's / PyCO2SYS at ambient pH
    #: and ~10 % at a pH 10.5 port (PHREEQC_PLAN.md §8, row G -- the blending tool's 1.64x was its
    #: own water). Under the default solver `results.py` keeps Mucci's; under `solver: phreeqc`
    #: these are what the `omega_*` columns carry, and the provenance says so.
    si_aragonite: NDArray[np.float64]
    si_calcite: NDArray[np.float64]
    omega_aragonite: NDArray[np.float64]
    omega_calcite: NDArray[np.float64]
    #: The carbonate system as PHREEQC speciates it, umol/kg: bicarbonate is the free HCO3-;
    #: carbonate is the *total* CO3-2 (free plus the MgCO3 pair, the only carbonate pair in
    #: pitzer.dat), which is the quantity PyCO2SYS's `carbonate` is; aqueous CO2 and its
    #: partial pressure (uatm, from the SI of CO2(g)).
    bicarbonate: NDArray[np.float64]
    carbonate: NDArray[np.float64]
    aqueous_co2: NDArray[np.float64]
    pco2: NDArray[np.float64]
    #: Free `OH-`, umol/kg -- the quantity the brucite product uses. PyCO2SYS's `hydroxide` is the
    #: *total*, of which the MgOH+ pair below is ~45 % at pH 11-12.
    hydroxide_free: NDArray[np.float64]
    magnesium_free: NDArray[np.float64]
    magnesium_hydroxide: NDArray[np.float64]
    gamma_magnesium: NDArray[np.float64]
    gamma_hydroxide: NDArray[np.float64]
    record: PitzerRecord


_SELECTED_OUTPUT = (
    "SELECTED_OUTPUT\n\t-reset false\n\t-pH\n\t-ionic_strength\n"
    "\t-si Brucite Aragonite Calcite CO2(g)\n"
    "\t-molalities H+ HSO4- OH- Mg+2 MgOH+ HCO3- CO3-2 MgCO3 CO2\n"
    "\t-activities Mg+2 OH-\n"
    "END\n"
)

#: The `SELECTED_OUTPUT` headings, as IPhreeqc names them.
_NAMES = (
    "pH",
    "mu",
    "si_Brucite",
    "si_Aragonite",
    "si_Calcite",
    "si_CO2(g)",
    "m_H+(mol/kgw)",
    "m_HSO4-(mol/kgw)",
    "m_OH-(mol/kgw)",
    "m_Mg+2(mol/kgw)",
    "m_MgOH+(mol/kgw)",
    "m_HCO3-(mol/kgw)",
    "m_CO3-2(mol/kgw)",
    "m_MgCO3(mol/kgw)",
    "m_CO2(mol/kgw)",
    "la_Mg+2",
    "la_OH-",
)


def _solution_block(
    number: int,
    composition: dict[str, float],
    total_alkalinity_kgw: float,
    dic_kgw: float,
    temperature: float,
) -> str:
    """One `SOLUTION`, everything in mol per kg of water, pH closing the charge.

    `composition["Na"]` arrives already adjusted so the conservative excess equals the TA; the
    `pH 8.0` is the starting guess for the unknown PHREEQC solves.
    """
    lines = [
        f"SOLUTION {number}",
        f"\ttemp\t{temperature:.6g}",
        "\tpH\t8.0\tcharge",
        "\tunits\tmol/kgw",
        f"\tC(4)\t{max(dic_kgw, 0.0):.10g}",
    ]
    del total_alkalinity_kgw  # stated through the sodium; kept in the signature for the reader
    for element, value in composition.items():
        lines.append(f"\t{element}\t{value:.10g}")
    lines.append("END")
    return "\n".join(lines)


def _run(blocks: list[str]) -> dict[str, NDArray[np.float64]]:
    """Solve the blocks in one IPhreeqc call and return the selected output by heading."""
    pp = engine()
    text = _SELECTED_OUTPUT + "\n".join(blocks) + f"\nDELETE\n\t-solution 1-{len(blocks)}\nEND\n"
    pp.ip.run_string(text)
    array: list[list[Any]] = [list(row) for row in pp.ip.get_selected_output_array()]
    header = [str(cell) for cell in array[0]]
    rows = array[1:]
    if len(rows) != len(blocks):
        raise RuntimeError(f"PHREEQC returned {len(rows)} rows for {len(blocks)} solutions")
    return {
        name: np.asarray([row[header.index(name)] for row in rows], dtype=np.float64)
        for name in _NAMES
    }


def solve_pitzer(
    total_alkalinity: ArrayLike,
    dic: ArrayLike,
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    borate_option: int = 1,
) -> PitzerState:
    """Solve every row through PHREEQC / `pitzer.dat`. Inputs umol/kg (TA, DIC), psu, degC.

    Broadcasts like PyCO2SYS. A row PHREEQC cannot converge is NaN and named in one
    `PitzerConvergenceWarning`; the batch is first tried whole and, on failure, row by row, so one
    bad sample does not blank a frame.
    """
    ta, c, s, t = np.broadcast_arrays(
        np.asarray(total_alkalinity, dtype=np.float64),
        np.asarray(dic, dtype=np.float64),
        np.asarray(salinity, dtype=np.float64),
        np.asarray(temperature, dtype=np.float64),
    )
    shape = ta.shape
    ta, c, s, t = (a.reshape(-1) for a in (ta, c, s, t))
    n = ta.size
    kgw_per_kg = water_fraction(s)
    composition = reference_seawater(s, borate_option=borate_option)
    # Per kg of solution -> per kg of water, both totals alike; then sodium carries the TA.
    ta_kgw = ta * 1e-6 / kgw_per_kg
    dic_kgw = c * 1e-6 / kgw_per_kg
    composition["Na"] = composition["Na"] + (ta_kgw - conservative_charge_excess(composition))
    blocks = [
        _solution_block(
            i + 1,
            {element: float(values[i]) for element, values in composition.items()},
            float(ta_kgw[i]),
            float(dic_kgw[i]),
            float(t[i]),
        )
        for i in range(n)
    ]

    columns: dict[str, NDArray[np.float64]] = {name: np.full(n, np.nan) for name in _NAMES}
    if n:
        # Obtain the engine *outside* the fallback: a missing package must be one clear error,
        # never a frame of NaN with a convergence warning attached (a test caught exactly that).
        engine()
        try:
            columns = _run(blocks)
        except Exception as batch_error:
            failed: list[int] = []
            for i, block in enumerate(blocks):
                try:
                    single = _run([block.replace(f"SOLUTION {i + 1}", "SOLUTION 1", 1)])
                except Exception:
                    failed.append(i)
                    continue
                for name in _NAMES:
                    columns[name][i] = single[name][0]
            if failed:
                first = failed[0]
                warnings.warn(
                    f"PHREEQC did not converge on {len(failed)} of {n} rows (first at index "
                    f"{first}: TA {ta[first]:.1f}, DIC {c[first]:.1f}, S {s[first]:.3f}, "
                    f"T {t[first]:.2f}); those rows are NaN. Batch error: "
                    f"{str(batch_error).splitlines()[0][:160]}",
                    PitzerConvergenceWarning,
                    stacklevel=2,
                )

    # Per kg of water -> per kg of solution, so concentrations and the concentration-based pH
    # scales sit on PyCO2SYS's basis. Activities, SI and gamma are basis-free.
    m_h = columns["m_H+(mol/kgw)"] * kgw_per_kg
    m_hso4 = columns["m_HSO4-(mol/kgw)"] * kgw_per_kg
    m_oh = columns["m_OH-(mol/kgw)"]
    m_mg = columns["m_Mg+2(mol/kgw)"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ph_free = -np.log10(m_h)
        ph_total = -np.log10(m_h + m_hso4)
        gamma_mg = 10.0 ** columns["la_Mg+2"] / m_mg
        gamma_oh = 10.0 ** columns["la_OH-"] / m_oh

    def out(values: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(values, dtype=np.float64).reshape(shape)

    return PitzerState(
        total_alkalinity=out(ta),
        dic=out(c),
        salinity=out(s),
        temperature=out(t),
        ph_nbs=out(columns["pH"]),
        ph_free=out(ph_free),
        ph_total=out(ph_total),
        ionic_strength=out(columns["mu"]),
        si_brucite=out(columns["si_Brucite"]),
        omega_brucite=out(10.0 ** columns["si_Brucite"]),
        si_aragonite=out(columns["si_Aragonite"]),
        si_calcite=out(columns["si_Calcite"]),
        omega_aragonite=out(10.0 ** columns["si_Aragonite"]),
        omega_calcite=out(10.0 ** columns["si_Calcite"]),
        bicarbonate=out(columns["m_HCO3-(mol/kgw)"] * kgw_per_kg * 1e6),
        carbonate=out(
            (columns["m_CO3-2(mol/kgw)"] + columns["m_MgCO3(mol/kgw)"]) * kgw_per_kg * 1e6
        ),
        aqueous_co2=out(columns["m_CO2(mol/kgw)"] * kgw_per_kg * 1e6),
        pco2=out(10.0 ** columns["si_CO2(g)"] * 1e6),
        hydroxide_free=out(m_oh * kgw_per_kg * 1e6),
        magnesium_free=out(m_mg * kgw_per_kg * 1e6),
        magnesium_hydroxide=out(columns["m_MgOH+(mol/kgw)"] * kgw_per_kg * 1e6),
        gamma_magnesium=out(gamma_mg),
        gamma_hydroxide=out(gamma_oh),
        record=record(),
    )
