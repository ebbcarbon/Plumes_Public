"""The PHREEQC / Pitzer spike of 2026-09-09 -- Phase 0 of ``notes/PHREEQC_PLAN.md``.

Not part of the package and not run by the suite: it needs ``phreeqpython`` (``pip install
phreeqpython``; the source distribution bundles the PHREEQC library for Windows, Linux and macOS and
installs on Python 3.13 and 3.14 without a compiler). Run it from a venv that also has this repo
installed::

    python studies/pitzer_spike.py

What it establishes, and what the plan's §8 records:

* ``pitzer.dat`` accepts Brucite re-parameterised to Xiong (2008)'s ``log_k`` -10.95 with this
  repo's ``dH`` -2.29 kJ/mol (-0.547 kcal/mol). The database carries boron itself (pKa 9.239 and
  the Mg/Ca borate pairs); the spike's first pass *left boron out of the input* and PHREEQC's pH
  sat 0.13-0.31 above PyCO2SYS's at pH 7.7-10, the borate alkalinity being read as carbonate.
  (An earlier revision of this script redefined the boron species at run time, believing the
  database lacked them; the numbers moved by <= 0.04 in SI and <= 0.03 in pH.)
* TA and DIC enter as ``Alkalinity`` and ``C(4)`` (per kg of water -- every input on one basis, or
  PHREEQC rejects the block); pH is the solved unknown and the entered DIC comes back exactly.
  ⚠️ Phase 1 found this fails at DIC 0 (pH stays at the guess), so the package states TA through
  the charge balance instead (``plumes2.chem.pitzer.speciation``). This script keeps the keyword
  form: its rows all have DIC 2092. It also enters TA and DIC per kg of water *unconverted*, a
  uniform 3 % that the package corrects; the pH agreement here is the consistent-basis one.
* With boron entered, PHREEQC's total-scale pH (``-log10(m(H+) + m(HSO4-))``) matches PyCO2SYS's to
  0.003-0.03 from pH 7.7 to 12.
* ``Omega_brucite`` from PHREEQC sits 6.8-8.4x below this repo's Davies / total-concentration value
  on the same water and the same Ksp. Decomposed, the factor is ``[OH-]^2`` (3.1x: PyCO2SYS's
  hydroxide is a total of which ~45 % is the MgOH+ ion pair at pH 11-12), ``gamma(OH-)^2`` (1.9x:
  Pitzer 0.54 vs Davies 0.75), ``gamma(Mg2+)`` (1.2x) and Mg pairing (1.0-1.2x).
* 1.0-1.1 ms per solve, single or batched.
"""

from __future__ import annotations

import math
import time

import numpy as np
import PyCO2SYS as pyco2
from phreeqpython import PhreeqPython

from plumes2.chem import (
    davies_activity_coefficient,
    magnesium_from_salinity,
    solubility_brucite,
    solve_from_alkalinity_dic,
)
from plumes2.chem.constants import BRUCITE_DISSOLUTION_ENTHALPY, BRUCITE_LOG_KSP_25C

#: Reference seawater at S 35, mg per kg of water (Millero's composition, as the blending tool
#: carried it in mg/L; the 2-3 % basis difference is uniform and is not what the spike measures).
REFERENCE_S35 = {
    "Na": 10781.0,
    "Mg": 1284.0,
    "Ca": 412.0,
    "K": 399.0,
    "Cl": 19353.0,
    "S(6)": 2712.0,
    "Br": 67.0,
}
#: Uppstrom (1974) total boron, mol/kg at S 35 -- the same source PyCO2SYS's option 1 uses.
#: (The spike ran with 0.0004106, the blending tool's figure, 1.2 % low; the package uses
#: 0.0004157.)
TOTAL_BORON_S35 = 0.0004157

BRUCITE_OVERRIDE = (
    "PHASES\nBrucite\n\tMg(OH)2 = Mg+2 + 2 OH-\n"
    f"\tlog_k\t{BRUCITE_LOG_KSP_25C}\n"
    f"\t-delta_H\t{BRUCITE_DISSOLUTION_ENTHALPY / 4184:.4f} kcal/mol\n"
)


def engine() -> PhreeqPython:
    pp = PhreeqPython(database="pitzer.dat")
    pp.ip.run_string(BRUCITE_OVERRIDE)
    return pp


def composition(
    salinity: float, temperature: float, ta_umol: float, dic_umol: float, *, boron: bool
) -> dict:
    comp: dict = {k: v * salinity / 35.0 for k, v in REFERENCE_S35.items()}
    comp["Na"] = f"{comp['Na']} charge"
    comp.update(units="mg/kgw", temp=temperature, pH=8.0)
    comp["Alkalinity"] = f"{ta_umol / 1000:.6f} mmol/kgw"
    comp["C(4)"] = f"{dic_umol / 1000:.6f} mmol/kgw"
    if boron:
        comp["B"] = f"{TOTAL_BORON_S35 * salinity / 35 * 1e3:.6f} mmol/kgw"
    return comp


def main() -> None:
    salinity, temperature, dic = 30.9, 11.2, 2092.0
    tk = temperature + 273.15
    ksp_t = 10**BRUCITE_LOG_KSP_25C * math.exp(
        -(BRUCITE_DISSOLUTION_ENTHALPY / 8.314462618) * (1 / tk - 1 / 298.15)
    )
    g_mg_d = float(davies_activity_coefficient(2, salinity, temperature))
    g_oh_d = float(davies_activity_coefficient(1, salinity, temperature))
    print(
        f"Davies: gamma(Mg)={g_mg_d:.3f} gamma(OH)={g_oh_d:.3f} "
        f"Mg_total={float(magnesium_from_salinity(salinity)):.5f} mol/kg "
        f"log10 Ksp(T)={math.log10(ksp_t):.3f}"
    )
    for boron in (False, True):
        pp = engine()
        print(f"\n== boron {'entered' if boron else 'left out of the input'} ==")
        print(
            f"{'TA':>6} {'pH_tot PHQ':>10} {'pH_tot PyCO2':>12} {'Om_davies':>10} "
            f"{'Om_pitzer':>10} {'ratio':>6} "
            f"{'Mg free':>8} {'g(Mg)':>6} {'g(OH)':>6} {'OH_free':>9} {'OH_pyco2':>9} {'ms':>5}"
        )
        for ta in (2146.0, 4000.0, 6000.0, 20000.0):
            t0 = time.perf_counter()
            sol = pp.add_solution(composition(salinity, temperature, ta, dic, boron=boron))
            dt = (time.perf_counter() - t0) * 1e3
            kgw = sol.mass
            sp = sol.species
            m_h, m_hso4, m_oh = sp["H+"] / kgw, sp.get("HSO4-", 0.0) / kgw, sp["OH-"] / kgw
            mg_tot, mg_free = sol.total_element("Mg", "mol") / kgw, sp["Mg+2"] / kgw
            a_mg, a_oh = sol.activity("Mg+2") / 1000, sol.activity("OH-") / 1000
            si = sol.si("Brucite")
            state = solve_from_alkalinity_dic(ta, dic, salinity, temperature)
            om_d = float(
                np.asarray(state.omega_brucite(solubility_brucite(salinity, temperature))).reshape(
                    -1
                )[0]
            )
            oh_d = float(np.asarray(state.hydroxide).reshape(-1)[0]) * 1e-6
            ref = pyco2.sys(
                par1=ta,
                par2=dic,
                par1_type=1,
                par2_type=2,
                salinity=salinity,
                temperature=temperature,
                opt_k_carbonic=10,
                opt_k_bisulfate=1,
                opt_total_borate=1,
            )
            print(
                f"{ta:6.0f} {-math.log10(m_h + m_hso4):10.3f} "
                f"{float(ref['pH_total']):12.3f} {om_d:10.4g} "
                f"{10**si:10.4g} {om_d / 10**si:6.2f} {mg_free / mg_tot:8.1%} "
                f"{a_mg / mg_free:6.3f} "
                f"{a_oh / m_oh:6.3f} {m_oh:9.3e} {oh_d:9.3e} {dt:5.2f}"
            )
            sol.forget()


if __name__ == "__main__":
    main()
