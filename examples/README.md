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
at the port: pH 10.66 (total), omega_brucite 400.60 (an upper bound; see PORTING_THE_PHYSICS.md)
termination: oscillation limit
near-field end: dilution 331.5 at 243.0 s

near field (last rows):
     time_s  dilution  ph_total  omega_brucite
197 240.531   328.525     8.065          0.001
198 241.752   330.032     8.065          0.001
199 242.973   331.523     8.065          0.001

mixing-zone boundaries:
            region dilution ph_total omega_brucite
acute    nearfield  268.869    8.071         0.001
chronic   farfield  703.309    8.052         0.001
```

That is the package's reason to exist in one screen: an alkalinity-elevated discharge is
strongly brucite-supersaturated *at the port* (pH 10.7, Ω ≈ 400 — a quantity the exe cannot
report at all) and back to Ω ≈ 0.001 by the first regulatory boundary.

`tests/test_examples.py` executes this script on every suite run, so the output above cannot
silently drift from the code.

## `run_macoma.py` — the real site: Ebb's default (Macoma) profile

The same pattern at the configuration the project was built for: case03's diffuser and
flow ([`reference_cases/case03_carbonate/`](../reference_cases/case03_carbonate/README.md))
with the effluent as intake water (S 30.9 / T 11.2 — operator, 2026-09-08),
the measured hydrography in [`macoma_ambient_levels.csv`](macoma_ambient_levels.csv), the site's
carbonate chemistry — TA 2146 / DIC 2092 µmol/kg, uniform in depth (operator, 2026-09-09) — in
[`macoma_ambient_chemistry.csv`](macoma_ambient_chemistry.csv), and the alkalinity dose
(`DOSE_TA`, default 6000 µmol/kg at the intake DIC) as the knob. This is the geometry the
Phase 9 dose study ran at, and the script's numbers reproduce the study's TA 6000 row
([`studies/ebb_dose_study/`](../studies/ebb_dose_study/README.md)): port pH 10.990, Ω 1700,
crossing at dilution 2.59 / 0.17 s / 3.6 cm, boundary dilutions 159 / 360. (The example runs
the acute 2 cm/s ambient only; the study reads its chronic boundary on the 5 cm/s ambient, 306.)

```text
$ .venv/Scripts/python examples/run_macoma.py
warning: the seabed is at 17 m (port depth 2 + elevation 15) but the ambient profile stops at 15 m, [...]

port: pH 10.990 (total), omega_brucite 1699.8 (an upper bound)
termination: oscillation limit; near-field end dilution 158 at 142 s
flux-averaged omega_brucite falls back through 1 at dilution 2.59, 0.17 s, 3.6 cm from the port (nearfield); the parabolic centreline crossing sits at twice that dilution

mixing-zone boundaries:
           region    dilution  ph_total omega_brucite omega_aragonite
acute    farfield  159.255443  7.808659      0.000685        1.129753
chronic  farfield  359.789851  7.764697      0.000559        1.022499
```

⚠️ Two unit corrections are applied here, both the same feet-as-metres slip in the archived
case03 project, which stores all three values in metres. **The port spacing is 0.6096 m — 2 ft**
(2026-09-01): at the site's 5900 L/h (98.3 L/min — a third correction, 2026-09-08; the archive
ran 0.219 L/s) the jets grow to 0.84 m and **merge** in shallow overlap (end `d/L` 1.38, the ~1 %
regime), so the spacing now touches the near field as well as the far field (a 15.5 m wastefield
instead of 48 m). **The mixing zones are 6.31 m / 63.09 m — 20.7 ft / 207 ft** (2026-09-02), which
is where the boundary rows above are read; the acute boundary sits just past the near-field end,
so its dilution (159) is barely above the endpoint's 158.

Two things to know, both deliberate: the ambient carbonate chemistry is **uniform in depth** —
TA 2146 / DIC 2092 µmol/kg from the surface to the 17 m seabed (operator, 2026-09-09; Ebb has no
depth-resolved measurement at Macoma, and the archived case's table was the exe run's entry, not the
site's), which puts the receiving water at pH 7.72–7.74 (total) and Ω_aragonite ≈ 0.93–0.95 — and
the `GeometryWarning` above is intentional, not a data error: nothing is measured at the 17 m
seabed itself, and the profiles are notional because the depth changes with the tides
(operator, 2026-09-01). The warning states an extrapolation.

## Where to go next

| you want | look at |
|---|---|
| every case field, unit and default | [USER_GUIDE.md](../USER_GUIDE.md) §3 (the YAML schema is the `Case` schema) |
| the API by task — variants, sweeps, chemistry alone | [USER_GUIDE.md](../USER_GUIDE.md) §4 |
| a dose–response sweep like the real study | `plumes2.sweep.sweep` (§4.4) and [`studies/ebb_dose_study/`](../studies/ebb_dose_study/README.md) |
| what to trust, and where the model degrades | [PORTING_THE_PHYSICS.md](../PORTING_THE_PHYSICS.md) |
| the second brucite engine (PHREEQC / Pitzer), or both engines side by side | `carbonate.pitzer` / `carbonate.solver: all` — [USER_GUIDE.md](../USER_GUIDE.md) §8.4; needs `pip install "plumes2[pitzer]"` |
| output column definitions | [USER_GUIDE.md](../USER_GUIDE.md) §6 |
