# Examples — plumes2 as a called physics package

For the reader who wants dilution and receiving-water chemistry out of a function call — not
to reproduce the Windows executable. (If you *do* need exe parity, byte-exact files, or the
defect flags, that all exists too: [USER_GUIDE.md](../USER_GUIDE.md) §4.8–4.9 and §7.)

The shape of the API, in full:

```python
from plumes2 import ambient_from_files, load_case, run

case = load_case("case.yaml")        # a whole case from one YAML file, or build it in code
results = run(case)                  # near-field UM3 + Brooks far field + chemistry
results.nearfield                    # pandas DataFrame, one row per sample
results.farfield                     # pandas DataFrame (or None)
```

Everything is an ordinary import; nothing shells out; results are dataframes.

## `run_from_files.py` — ambient tables in plain CSVs, parameters in code

The intended split for iterating on a discharge: measured site data lives in **plain CSV
files** (one row per depth, headers = field names, blank cell = default), and the things you
sweep — geometry, flow, the alkalinity dose — are typed in code. [`run_from_files.py`](run_from_files.py)
reads [`ambient_levels.csv`](ambient_levels.csv) and [`ambient_chemistry.csv`](ambient_chemistry.csv)
via `ambient_from_files(...)`, assembles the `Case` (every input validated: physical ranges,
strictly increasing depths), runs it, and prints:

```text
$ .venv/Scripts/python examples/run_from_files.py
at the port: pH 10.66 (total), omega_brucite 365.46 (an upper bound; see PORTING_THE_PHYSICS.md)
termination: oscillation limit
near-field end: dilution 331.5 at 243.0 s

near field (last rows):
     time_s  dilution  ph_total  omega_brucite
197 240.531   328.525     8.065          0.001
198 241.752   330.032     8.065          0.001
199 242.973   331.523     8.065          0.001

mixing-zone boundaries:
            region dilution ph_total omega_brucite
acute    nearfield  268.868    8.071         0.001
chronic   farfield  703.308    8.052         0.001
```

That is the package's reason to exist in one screen: an alkalinity-elevated discharge is
strongly brucite-supersaturated *at the port* (pH 10.7, Ω ≈ 365 — a quantity the exe cannot
report at all) and back to Ω ≈ 0.001 by the first regulatory boundary.

`tests/test_examples.py` executes this script on every suite run, so the output above cannot
silently drift from the code.

## `run_macoma.py` — the real site: Ebb's default (Macoma) profile

The same pattern at the configuration the project was built for: case03's diffuser and
effluent ([`reference_cases/case03_macoma_carbonate/`](../reference_cases/case03_macoma_carbonate/README.md)),
the measured ambient in [`macoma_ambient_levels.csv`](macoma_ambient_levels.csv) and
[`macoma_ambient_chemistry.csv`](macoma_ambient_chemistry.csv), and the alkalinity dose
(`DOSE_TA`, default 6000 µmol/kg at the intake DIC) as the knob. This is the geometry the
Phase 9 dose study ran at, and the script's numbers reproduce the study's TA 6000 row
([`studies/ebb_dose_study/`](../studies/ebb_dose_study/README.md)): port pH 10.671, Ω 385,
crossing at dilution 2.16 / 0.47 s / 1.8 cm, boundary dilutions 633 / 4319.

```text
$ .venv/Scripts/python examples/run_macoma.py
warning: the seabed is at 17 m (port depth 2 + elevation 15) but the ambient profile stops at 15 m, [...]

port: pH 10.671 (total), omega_brucite 385.4 (an upper bound)
termination: oscillation limit; near-field end dilution 534 at 139 s
flux-averaged omega_brucite falls back through 1 at dilution 2.16, 0.47 s, 1.8 cm from the port (nearfield); the parabolic centreline crossing sits at twice that dilution

mixing-zone boundaries:
           region     dilution  ph_total omega_brucite omega_aragonite
acute    farfield   633.341845  8.389211      0.008777        4.702409
chronic  farfield  4319.472201  8.384259      0.008564        4.653772
```

⚠️ The port spacing here is **0.6096 m — 2 ft**, the 2026-09-01 correction: the archived case03
project carries 2 m ("2.0" entered with the wrong unit; the Dec-2025 original stored 2.0 under
the `.prj` feet flag). At Ebb's flow the plume never grows to 0.61 m, so merging never fires and
the **near field is identical either way** — spacing is inert until merging. What the correction
moves is the far field (a 14.6 m wastefield instead of 48 m) and therefore the boundary rows
above.

Two inherited caveats, both deliberate and both flagged by the script itself: the ambient
chemistry below the deepest measured row (4 m) is **held constant** to the 17 m seabed — a
placeholder by design; replace those CSV rows when a measured profile exists — and the
`GeometryWarning` above is intentional, not a data error: nothing is measured at the 17 m
seabed itself, and the profiles are notional because the depth changes with the tides
(operator, 2026-09-01). The warning states an extrapolation.

## Where to go next

| you want | look at |
|---|---|
| every case field, unit and default | [USER_GUIDE.md](../USER_GUIDE.md) §3 (the YAML schema is the `Case` schema) |
| the API by task — variants, sweeps, chemistry alone | [USER_GUIDE.md](../USER_GUIDE.md) §4 |
| a dose–response sweep like the real study | `plumes2.sweep.sweep` (§4.4) and [`studies/ebb_dose_study/`](../studies/ebb_dose_study/README.md) |
| what to trust, and where the model degrades | [PORTING_THE_PHYSICS.md](../PORTING_THE_PHYSICS.md) |
| output column definitions | [USER_GUIDE.md](../USER_GUIDE.md) §6 |
