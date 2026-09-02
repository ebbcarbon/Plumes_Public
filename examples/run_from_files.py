"""plumes2 as a called physics package: plain CSV ambient tables, parameters in code.

The intended pattern for a collaborator who wants dilution and carbonate chemistry out of a
function call rather than out of the exe's GUI:

* **ambient tables** live in ordinary CSVs beside this script (one row per depth, headers =
  field names — see `plumes2.io.ambient_csv` and USER_GUIDE.md §3.5 for names and units);
* **everything scalar** (diffuser geometry, effluent, the dose) is typed in code, where it
  can be swept;
* the result is dataframes (`results.nearfield`, `results.farfield`), not a `.dat` file.

Run it from the repository root (or anywhere, paths are script-relative):

    .venv/Scripts/python examples/run_from_files.py

The case is deliberately small and physically unremarkable: a mildly buoyant,
alkalinity-elevated discharge (TA 6000 µmol/kg at DIC 2500 — the (TA, DIC) pair is how such
a discharge is specified) from four ports at 10 m depth. Expected output is quoted in
`examples/README.md`, and `tests/test_examples.py` executes this file, so if it drifts from
the code it fails the suite.
"""

from __future__ import annotations

from pathlib import Path

from plumes2 import ambient_from_files, mixing_zone_values, run
from plumes2.config import Case, Diffuser, Effluent, EffluentChemistry, MixingZone

HERE = Path(__file__).parent


def build_case() -> Case:
    return Case(
        description="examples/run_from_files.py -- an alkalinity-elevated discharge",
        diffuser=Diffuser(
            port_diameter=0.05,  # m
            port_elevation=1.0,  # m above the seabed
            vertical_angle=45.0,  # degrees above horizontal
            horizontal_angle=0.0,  # bearing of discharge
            n_ports=4,
            port_spacing=2.0,  # m
            port_depth=10.0,  # m below the surface
        ),
        effluent=Effluent(
            flow=0.002,  # m3/s, total across all ports
            salinity=30.0,  # psu
            temperature=12.0,  # degC
        ),
        effluent_chemistry=EffluentChemistry(
            total_alkalinity=6000.0,  # umol/kg
            dic=2500.0,  # umol/kg; give (TA, DIC) -- or (TA, pH), never both
        ),
        mixing_zone=MixingZone(acute_distance=10.0, chronic_distance=100.0),
        ambient=ambient_from_files(
            HERE / "ambient_levels.csv",
            chemistry=HERE / "ambient_chemistry.csv",
        ),
    )


def main() -> None:
    case = build_case()
    results = run(case)  # samples=200; raise it for a dense trace

    columns = ["time_s", "dilution", "ph_total", "omega_brucite"]
    port = results.nearfield.iloc[0]
    print(
        f"at the port: pH {port['ph_total']:.2f} (total), "
        f"omega_brucite {port['omega_brucite']:.2f} (an upper bound; see PORTING_THE_PHYSICS.md)"
    )
    print(f"termination: {results.termination}")
    print(f"near-field end: dilution {results.final_dilution:.1f} at {results.end_time:.1f} s")
    print()
    print("near field (last rows):")
    print(results.nearfield[columns].tail(3).to_string(float_format="{:.3f}".format))
    print()
    print("mixing-zone boundaries:")
    zone = mixing_zone_values(results)
    print(zone[["region", "dilution", "ph_total", "omega_brucite"]].to_string(
        float_format="{:.3f}".format
    ))

    # To keep the run: write_results(results, "out/example_run") -- tidy CSVs at full
    # precision plus a provenance sidecar (code version, case hash, timestamp).


if __name__ == "__main__":
    main()
