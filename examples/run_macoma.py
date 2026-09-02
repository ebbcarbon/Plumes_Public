"""The Macoma configuration -- Ebb's default profile -- as a called physics package.

Same pattern as `run_from_files.py`, with the real site: case03's diffuser and effluent
(the archived exe run `reference_cases/case03_macoma_carbonate/`), the measured ambient
profile in `macoma_ambient_levels.csv`, and the ambient carbonate chemistry in
`macoma_ambient_chemistry.csv`. This is the geometry the Phase 9 dose study ran at
(`studies/ebb_dose_study/`), so the numbers printed here can be checked against its tables.

Two things are inherited from the archived case, deliberately:

* ⚠️ the ambient chemistry below the deepest measured row (4 m) is **held constant** to the
  17 m seabed -- the dose study's one stated assumption; replace those CSV rows when a
  measured profile exists;
* ⚠️ a `GeometryWarning` fires: the seabed (port depth 2 m + elevation 15 m = 17 m) sits
  below the hydrographic profile's last row (15 m). Intentional, not a typo (operator,
  2026-09-01): no measurement exists at 17 m, and the profiles are notional because the
  water depth changes with the tides -- the warning states an extrapolation, not an error.

Run it:

    .venv/Scripts/python examples/run_macoma.py

`DOSE_TA` is the knob. At the intake DIC (2500 umol/kg), TA below ~4340 never
supersaturates brucite at all; the default here, 6000, is dosed enough that the
supersaturated window -- centimetres and seconds -- is visible in the output.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from plumes2 import ambient_from_files, mixing_zone_values, run
from plumes2.config import (
    Case,
    Diffuser,
    Effluent,
    EffluentChemistry,
    MixingZone,
    NearFieldSettings,
)
from plumes2.sweep import brucite_extract

HERE = Path(__file__).parent

DOSE_TA = 6000.0  # umol/kg effluent total alkalinity; the study swept 3000 -> 20000
INTAKE_DIC = 2500.0  # umol/kg; held while TA moves -- the axis a feedstock moves along


def build_case() -> Case:
    return Case(
        description=f"Macoma (case03) at TA {DOSE_TA:.0f} / DIC {INTAKE_DIC:.0f}",
        diffuser=Diffuser(
            port_diameter=0.0127,
            port_elevation=15.0,
            vertical_angle=45.0,
            horizontal_angle=90.0,
            n_ports=25,
            port_spacing=0.6096,  # 2 ft (operator, 2026-09-01) -- the archived case03 project
            # says 2 m, a unit slip; the site's spacing is corrected here and in the study
            port_depth=2.0,
        ),
        effluent=Effluent(flow=0.000219063, salinity=35.0, temperature=10.0),
        near_field=NearFieldSettings(max_rise_or_fall=3),  # as the archived case runs
        effluent_chemistry=EffluentChemistry(total_alkalinity=DOSE_TA, dic=INTAKE_DIC),
        mixing_zone=MixingZone(acute_distance=20.7, chronic_distance=207.0),
        ambient=ambient_from_files(
            HERE / "macoma_ambient_levels.csv",
            chemistry=HERE / "macoma_ambient_chemistry.csv",
        ),
    )


def main() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        case = build_case()  # GeometryWarning fires here: 17 m seabed, 15 m profile
        results = run(case, samples=3000)  # dense, for the omega = 1 crossing
    for warning in {str(w.message) for w in caught}:
        print(f"warning: {warning}")
    print()

    extracted = brucite_extract(results)
    print(f"port: pH {extracted['port_ph_total']:.3f} (total), "
          f"omega_brucite {extracted['port_omega_brucite']:.1f} (an upper bound)")
    print(f"termination: {results.termination}; "
          f"near-field end dilution {results.final_dilution:.0f} at {results.end_time:.0f} s")
    if extracted["omega1_region"] == "never":
        print("brucite: never supersaturated, even undiluted")
    else:
        print(
            "flux-averaged omega_brucite falls back through 1 at "
            f"dilution {extracted['omega1_dilution']:.2f}, "
            f"{extracted['omega1_time_s']:.2f} s, "
            f"{100 * extracted['omega1_distance_m']:.1f} cm from the port "
            f"({extracted['omega1_region']}); the parabolic centreline crossing sits at "
            "twice that dilution"
        )
    print()
    print("mixing-zone boundaries:")
    zone = mixing_zone_values(results)
    print(zone[["region", "dilution", "ph_total", "omega_brucite", "omega_aragonite"]])


if __name__ == "__main__":
    main()
