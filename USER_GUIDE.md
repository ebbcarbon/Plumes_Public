# plumes2 — user guide

**Everything you need to drive the model, spelled out, with no internet required.** This is the
reference for *how to say it*: the command-line syntax, every field of the case file with its unit
and default, the Python calls, the output columns, the warnings and what each asks you to do, and
the workflow around the Windows executable. For *what to trust* read
[PORTING_THE_PHYSICS.md](PORTING_THE_PHYSICS.md); for *why* read [PLAN.md](notes/PLAN.md).

⭐ **This guide is checked, not just written.** Each reference table below sits under an HTML
comment such as `<!-- schema: plumes2.config.Diffuser -->`, and `tests/test_user_guide.py` reads
those tables back against the real models, enums, column dictionaries and command-line parser. A
field, default, flag or column that changes in the code fails the suite until this file is fixed.
If a table here and the code ever disagree, the test run will say so — trust the failing test.

Conventions: **SI everywhere** (metres, m³/s, °C, psu, µmol/kg, seconds) unless a column name says
otherwise. Depths are positive down. Angles are degrees. Horizontal directions (`horizontal_angle`,
`current_direction`, `farfield_direction`) are **counter-clockwise from the model's +x axis**, as the
PLUMES manual defines them; the model has no compass, so `x` / `y` in the outputs and the report
are that frame, not east and north — orient it to the site yourself. Defaults in the tables are
written the way YAML reads them: `true` / `false`, `null` for "not given", `required` for "you
must supply it".

---

## 1. Setting up and running anything

Windows PowerShell, from the repository root. Nothing below fetches from the network once the
environment exists.

```powershell
uv venv --python 3.14 .venv
uv pip install --python .venv -e ".[compare,dev,notebook,pitzer]"  # first time only; pitzer = the optional PHREEQC engine (§8.4)
uv pip install --python .venv -r requirements.lock.txt           # or: the exact pinned set
uv pip install --python .venv -e . --no-deps
```

Two equivalent ways to invoke the command line:

```powershell
.venv\Scripts\plumes2.exe --version
.venv\Scripts\python.exe -m plumes2.cli --version
```

Activate with `.venv\Scripts\Activate.ps1` if you would rather type `plumes2` and `python`
bare. Everything below writes `plumes2 …`; substitute either spelling.

⚠️ **Console output is plain ASCII on purpose** — Windows consoles default to cp1252 — and Python
warnings are reprinted as `note: …` lines on stderr instead of tracebacks.

**Exit codes**: `0` success; `1` a bad input or unreadable file (`ValueError`/`OSError`), or a
`validate` run with any target out of tolerance; `2` a usage error (no such file, unknown
extension).

---

## 2. The command line

Six subcommands. `CASE` is either a `.prj` written by the exe or one of our `.yaml` files; the
extension decides, and the two are **not** equivalent (§4.8).

### `plumes2 run` — integrate a case and write a result directory

```powershell
plumes2 run CASE
plumes2 run CASE -o DIR --samples 500 --units US
```

| flag | meaning | default |
|---|---|---|
| `CASE` | a `.prj` from the exe, or a `.yaml` of ours | required |
| `-o DIR`, `--out DIR` | output directory | `<CASE's folder>/<CASE stem>_results` |
| `--samples N` | rows in the near-field output — **output resolution only**, the integration is adaptive and independent of it | `200` |
| `--units SI|US` | units for the **printed summary only**; the files are always SI | `SI` |

Writes into `DIR`:

| file | contents |
|---|---|
| `nearfield.csv` | one row per sample, full precision, units in every column name (§6.1) |
| `farfield.csv` | the Brooks far field, when the case enables it and the current is non-zero (§6.2) |
| `case.yaml` | the complete resolved input, chemistry included |
| `provenance.yaml` | version, commit, UTC stamp, case digest, termination, and the meaning of every column |

Prints: the near-field end time and termination reason, the final flux-averaged dilution and
depth, the centreline dilution with the peak-to-mean, the plume diameter, and — with chemistry —
the pH and Ω_brucite at the port and the end, plus a `note:` if brucite went supersaturated.

### `plumes2 report` — one report, a PDF by default

```powershell
plumes2 report CASE
plumes2 report CASE -o out\report.pdf --samples 300 --units US
plumes2 report CASE -o out\report.html
plumes2 report TRACE.dat --case-file CASE.yaml
plumes2 report CASE --gradient-dir out\figures
```

| flag | meaning | default |
|---|---|---|
| `CASE` | a `.prj` or `.yaml` to run, **or a `.dat` the exe already wrote** | required |
| `-o FILE`, `--out FILE` | output file; **the suffix picks the format**, `.pdf` or `.html` | `<CASE with extension replaced by .report.pdf>` |
| `--samples N` | rows, as for `run` (ignored for a `.dat`) | `200` |
| `--units SI|US` | display units | `SI` |
| `--case-file PATH` | **for a `.dat` only**: the `.prj` or `.yaml` behind it, which unlocks the carbonate secondaries (pCO₂, CO₃²⁻, HCO₃⁻, Ω_brucite) the exe never printed | none |
| `--gradient-dir DIR` | also write standalone pH / aragonite / calcite / brucite **gradient figures** (PNG + SVG) into `DIR`; needs chemistry, so a bare `.dat` needs `--case-file` too | none |

The PDF is US Letter, one section per panel — heading, explanation, figure, notes, and the table of
values — with selectable text and vector figures, typeset with matplotlib; it needs nothing but a
PDF reader. Its contents rows are links to their sections and the same entries form the document's
bookmarks (the outline in a viewer's sidebar), added by `pypdf` after the pages are written. The HTML variant is inline SVG plus an inline stylesheet — no JavaScript, no external
reference — so it opens from the file alone. In either, panels are skipped rather than drawn empty.

**The receiving water first.** A report on a case (a run, or a `.dat` with `--case-file`) opens with
two panels of the ambient profiles the plume was integrated into, depth down the page: temperature,
salinity, the model's density, the near- and far-field currents and their directions; and, when the
case carries chemistry, the entered TA and DIC with the pH, aragonite and brucite saturation solved
from them at each row. The port, the seabed and the trapping depth are drawn across every column, and
the stretch below the profile's last row is shaded. A bare `.dat` has no case, so it gets neither.

**Surfacing plumes.** With `stop_at_surface` off the model integrates on past the contact, and
rows whose centreline is above the surface are its continuation into the air. Every table and CSV
keeps them; no figure draws them. The side view, the 3-D body, the chemistry sections and the
far-field slab are cut at the surface plane, the centreline stops where it crosses (marked), the
top-down footprints end there, and the comparison overlays stop each depth line on the plane. Each
affected panel says where the plume reached the surface and how many rows lie above it.

**The far field in plan.** Straight after the top-down view, a run with a far field adds the same
picture carried on: the wastefield as a band from the near-field end along the far-field current, its
width the Brooks width at each distance and its shade the slab-average dilution, with the acute and
chronic mixing-zone boundaries crossing it at their distances and the dilution read there. It is drawn
to a margin past the last boundary the far field reaches (the far-field panels carry the rest), the
across-current axis is stretched by a printed factor when the band would otherwise be a hairline, and
a bare `.dat` lays the band along the plume's final heading because the file names no current.

**The chemistry section panels.** When the case carries chemistry, the report adds one panel per
mineral and for pH showing the quantity **on the plume itself**: a side view with distance from the
diffuser along the bottom and depth down the side, the outline the plume's own diameter, and the
quantity filled in as a colour field across the whole body. Each point is the carbonate system
*re-solved* at its local dilution, not interpolated between the centreline and the edge, because pH
and Ω are non-linear in dilution. The dark end of the colour scale is the discharge, the light end
the receiving water, and the ambient is marked on the colour bar. The vertical scale is stretched by
a round factor printed on the figure so the plume has visible thickness, and the surface and seabed
are drawn when they are near or named with their distance when they are not. These panels are the
near field; `--gradient-dir` additionally writes a `_full` figure per quantity with the far field
beside it on its own distance axis, continued to the acute and chronic mixing-zone boundaries as a
slab average. Files are named `chem_<quantity>_nearfield.{svg,png}` and
`chem_<quantity>_full.{svg,png}`. From Python:
`plumes2.report.write_chemistry_gradient_figures(results, out_dir)`.

### `plumes2 validate` — run the executable ledger

```powershell
plumes2 validate
plumes2 validate -o validation.pdf
```

| flag | meaning |
|---|---|
| `-o FILE`, `--out FILE` | also write the validation report here (`.pdf` or `.html`, by suffix) |

Re-derives every executable claim in [LEDGER.md](notes/LEDGER.md), prints ours / the reference / the
error per row, then the coverage line (`executable / numbered ledger rows`) and, unconditionally,
how many passing rows are recorded *divergences* or *reproduced defects* rather than agreements.
**Exits 1 if any target is outside tolerance**, so it works as a gate.

### `plumes2 info` — summarise a case without running it

```powershell
plumes2 info CASE
```

Prints ports and spacing; port diameter and angles; port depth and seabed; flow, salinity,
temperature; ambient level count and current range; whether an effluent chemistry endmember and an
ambient chemistry table are present; the termination settings (max rise/fall, stop at surface,
stop at bottom); and **the unit each `.prj` table is stored in** — for a `.prj` input, what the
file carries; for a YAML case, what a written `.prj` would carry — listing every column not in its
primary unit (see §4.8 on why a metric case can come out in feet).

### `plumes2 convert` — `.prj` ↔ `.yaml`

```powershell
plumes2 convert case.prj case.yaml
plumes2 convert case.yaml case.prj
```

The target's extension picks the direction. **`.yaml → .prj` is lossy and says so on stderr**: a
`.prj` cannot carry chemistry, the stop-at checkboxes, the far-field stops or the output-variable
selection (§4.8). Those stay in the YAML and are re-entered in the GUI.

### `plumes2 farfield` — the standalone Brooks calculator

```powershell
plumes2 farfield --dilution 170 --width 96.3 --distance 500 --current 0.05
plumes2 farfield --dilution 170 --width 96.3 --distance 500 --current 0.05 --decay 0.23
```

| flag | meaning | default |
|---|---|---|
| `--dilution D` | initial (near-field end) dilution | required |
| `--width W` | initial wastefield width, m | required |
| `--distance X` | mixing-zone distance, m | required |
| `--current U` | far-field current speed, m/s | required |
| `--decay k` | first-order decay, per day | `0.0` |

Prints a table indexed by distance with `dilution_factor`, `dilution`, `width`, `travel_time_s`.
This reproduces the exe's own standalone far-field dialog (ledger row 119).

---

## 3. The case file (`.yaml`)

The native input. SI throughout, defaults omitted when written, and able to hold what a `.prj`
cannot: the effluent carbonate endmember, the constant options, dissolved oxygen, the stop
settings and the far-field stops. **Unknown keys are rejected** (`extra="forbid"`), so a typo in
a field name is an error, not a silently ignored line.

Load and save from Python with `plumes2.load_case(path)` / `plumes2.io.dump_case(case, path)`;
`loads_case(text)` / `dumps_case(case)` for strings. `load(dump(case)) == case`.

### 3.1 Top level

<!-- schema: plumes2.config.Case -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `description` | text | — | `"Project Description"` | free text; goes into the `.prj` header |
| `diffuser` | section §3.2 | — | required | geometry |
| `effluent` | section §3.3 | — | required | discharge properties |
| `mixing_zone` | section §3.4 | — | required | the two regulatory distances |
| `ambient` | section §3.5 | — | required | depth profiles (hydrographic, chemistry, DO) |
| `near_field` | section §3.6 | — | (defaults) | solver and termination settings |
| `far_field` | section §3.7 | — | (defaults) | Brooks settings and stops |
| `effluent_chemistry` | section §3.8 | — | `null` | carbonate endmember; **chemistry runs only when this and `ambient.chemistry` are both given** |
| `carbonate` | section §3.9 | — | (defaults) | constant options, rate laws, defect flags |
| `effluent_do` | section §3.10 | — | `null` | oxygen endmember; **DO runs only when this and `ambient.dissolved_oxygen` are both given** |

Chemistry and DO may be given together; the port does not inherit the manual's XOR (the exe runs
both, case24).

### 3.2 `diffuser`

<!-- schema: plumes2.config.Diffuser -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `port_diameter` | float > 0 | m | required | one port's diameter |
| `port_elevation` | float ≥ 0 | m | required | port height above the seabed; **the seabed is `port_depth + port_elevation`**, never stored separately |
| `vertical_angle` | float, −90…90 | deg | required | discharge angle above horizontal (negative = downward) |
| `horizontal_angle` | float, 0…360 | deg | required | discharge direction in the horizontal plane, counter-clockwise from +x (not a compass bearing) |
| `n_ports` | int ≥ 1 | — | required | number of ports |
| `port_spacing` | float ≥ 0 | m | required | nominal spacing along the diffuser; `0` with `n_ports > 1` warns (`GeometryWarning`) |
| `port_depth` | float > 0 | m | required | depth of the port below the surface |
| `x_position` | float | m | `0.0` | diffuser origin, x |
| `y_position` | float | m | `0.0` | diffuser origin, y |

Derived, read-only: `bottom_depth`, `port_area`, `diffuser_length = (n_ports − 1) · port_spacing`.

### 3.3 `effluent`

<!-- schema: plumes2.config.Effluent -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `flow` | float > 0 | m³/s | required | **total** across all ports |
| `salinity` | float ≥ 0 | psu | `0.0` | effluent salinity |
| `temperature` | float | °C | `20.0` | effluent temperature |
| `pollutant` | float ≥ 0 | — | `0.0` | tracer concentration (any unit; reported diluted) |
| `excess_density` | float ≥ 0 | kg/m³ | `0.0` | density the dissolved load adds beyond what `salinity` accounts for (pure water + NaOH, say); dilutes with the effluent, **invisible to the chemistry**; not in a `.prj` |

Exit velocity per port is `flow / n_ports / port_area` (`case.exit_velocity`).

### 3.4 `mixing_zone`

<!-- schema: plumes2.config.MixingZone -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `acute_distance` | float ≥ 0 | m | required | acute (near) regulatory boundary; must not exceed the chronic one |
| `chronic_distance` | float ≥ 0 | m | required | chronic (far) regulatory boundary; also the exe's default far-field extent |

### 3.5 `ambient`

<!-- schema: plumes2.config.AmbientProfile -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `levels` | list of §3.5.1, ≥ 1 row | — | required | the hydrographic profile |
| `chemistry` | list of §3.5.2 | — | `[]` | ambient carbonate profile; **must reach deeper than the port** when chemistry is on, or the case is refused (the exe refuses too) |
| `dissolved_oxygen` | list of §3.5.3 | — | `[]` | ambient DO/BOD profile |

In every list **depths must strictly increase**. Between levels the port interpolates linearly; past
the ends it clamps to the end value (`ambient.ExtrapolationPolicy.CLAMP` by default). A seabed
below the deepest level warns (`GeometryWarning`) rather than refusing, because the exe runs such
projects.

#### 3.5.1 one `levels` row

<!-- schema: plumes2.config.AmbientLevel -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `depth` | float ≥ 0 | m | required | |
| `current_speed` | float ≥ 0 | m/s | `0.0` | near-field current |
| `current_direction` | float, 0…360 | deg | `0.0` | near-field current direction, counter-clockwise from +x (same convention as `horizontal_angle`) |
| `salinity` | float ≥ 0 | psu | `0.0` | |
| `temperature` | float | °C | `20.0` | |
| `background_pollutant` | float ≥ 0 | — | `0.0` | ambient tracer concentration |
| `decay_rate` | float ≥ 0 | 1/day | `0.0` | first-order tracer decay used by the far field |
| `farfield_speed` | float ≥ 0 | m/s | `0.0` | **the far field's own current** — `0` disables Brooks (no downstream axis) |
| `farfield_direction` | float, 0…360 | deg | `0.0` | |
| `dispersion_alpha` | float ≥ 0 | m^(2/3)/s | `0.0003` | Brooks eddy-diffusivity coefficient |

#### 3.5.2 one `chemistry` row (µmol/kg, as the GUI takes them)

<!-- schema: plumes2.config.AmbientChemistryLevel -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `depth` | float ≥ 0 | m | required | |
| `total_alkalinity` | float ≥ 0 | µmol/kg | required | |
| `dic` | float ≥ 0 | µmol/kg | required | |
| `ph` | float 0…14 or `null` | — | `null` | optional; the exe derives ambient pH from TA and DIC and **ignores** this column. Leave it out rather than writing `0` |
| `calcium` | float ≥ 0 or `null` | µmol/kg | `null` | kept for round-tripping; the exe ignores it (case06) and the port uses `0.01028 · S / 35` mol/kg |

#### 3.5.3 one `dissolved_oxygen` row (mg/L)

<!-- schema: plumes2.config.AmbientDOLevel -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `depth` | float ≥ 0 | m | required | |
| `dissolved_oxygen` | float ≥ 0 | mg/L | required | |
| `cbod5` | float ≥ 0 | mg/L | `0.0` | ambient carbonaceous BOD₅ (far field only) |
| `nbod5` | float ≥ 0 | mg/L | `0.0` | ambient nitrogenous BOD₅ (far field only) |

### 3.6 `near_field`

<!-- schema: plumes2.config.NearFieldSettings -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `aspiration_coefficient` | float > 0 | — | `0.1` | Taylor entrainment α |
| `contraction_coefficient` | float, 0 < c ≤ 1 | — | `1.0` | port contraction |
| `light_absorption` | float ≥ 0 | — | `0.16` | carried for `.prj` fidelity; unused |
| `max_rise_or_fall` | int 0…3 | — | `2` | the GUI's "No. of maximum plume rise or fall"; the run is allowed `switch + 1` turning points. `.prj` field `nearfield_flags[3]` |
| `stop_at_surface` | bool | — | `false` | the "stop plume at surface hit" box (`nearfield_flags[1]`, 1 = stop); `false` matches how the archive was generated |
| `stop_at_bottom` | bool | — | `true` | the "stop plume at bottom hit" box |
| `stop_at_shoreline` | bool | — | `false` | carried; measured **inert** in the exe (case12) |
| `output_interval` | int ≥ 1 | steps | `5` | the exe's print interval; carried in the `.prj`, irrelevant to our sampling |
| `max_steps` | int ≥ 1 | — | `5000` | the exe's step cap |
| `max_dilution` | float > 0 | — | `5000.0` | near-field dilution stop |
| `equation_of_state` | enum §3.11 | — | `eos80` | `eos80` (standard, default) or `knudsen` (**what the exe computes**; pick it for a parity comparison) |
| `similarity_profile` | enum §3.11 | — | `parabolic` | cross-plume profile the centreline is read through; post-processing only, does not touch the trajectory. Decided (PLAN §2): `parabolic` is what the study quotes; pick another to match a trace run under that exe option, or for a sensitivity (history: PLAN_HISTORY §8.4) |

### 3.7 `far_field`

<!-- schema: plumes2.config.FarFieldSettings -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `enabled` | bool | — | `true` | run Brooks after the near field |
| `exe_build` | enum §3.11 | — | `current` | `current` (2026 builds: wastefield width carries `|cos(H-angle − current)|`) or `legacy` (pre-2026: no cosine) |
| `law` | enum §3.11 | — | `four_thirds` | eddy-diffusivity growth law; `four_thirds` is the open-water choice and the operator's decision (PLAN §2; history in PLAN_HISTORY §8.5) |
| `interval` | float > 0 | m | `10.0` | far-field output spacing |
| `max_distance` | float > 0 | m | `500.0` | calculation distance — the operator's usual GUI entry, not the exe's default (which is the chronic boundary) |
| `max_dilution` | float > 0 | — | `10000.0` | dilution stop entered beside the distance; whichever binds first stops the table. The first row at or past it is kept so the crossing is visible |

### 3.8 `effluent_chemistry` (µmol/kg)

<!-- schema: plumes2.config.EffluentChemistry -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `total_alkalinity` | float ≥ 0 | µmol/kg | required | |
| `dic` | float ≥ 0 or `null` | µmol/kg | `null` | give **exactly one** of `dic` and `ph` |
| `ph` | float 0…14 or `null` | — | `null` | give **exactly one** of `dic` and `ph` |
| `ph_scale` | enum §3.11 | — | `free` | the scale `ph` is on; the exe's dialog takes typed pH as free |

⚠️ **This is Ebb's own specification**: (TA, DIC), or (TA, pH) where DIC is 0 (operator,
2026-08-25). **Omit `dic` to use pH — do not write `dic: 0`.** `0.0` is a number here ("TA with no
carbon"), not a sentinel, and `dic: 0` with a `ph` is rejected as two partners. It is also the
exe's own rule (case03 entered DIC 0 and it used TA + pH; case04 gave a DIC and discarded the pH).

### 3.9 `carbonate`

<!-- schema: plumes2.config.CarbonateSettings -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `solver` | enum | — | `pyco2sys` | which engine re-solves the mixed row: `none` (no chemistry columns), `pyco2sys` (the exe's lineage), `phreeqc` (every column from PHREEQC / Pitzer), `all` (both, side by side, for cross-comparison) — §8.4 |
| `k1k2_option` | int 1…14 | — | `10` | CO2SYS K1/K2 option, the exe's numbering (§8.1). 10 = Lueker et al. 2000, the exe's default |
| `kso4_option` | int 1…4 | — | `1` | bisulfate **and** total-borate pair (§8.2). 1 = Dickson 1990 + Uppström 1974, the exe's default |
| `calcite_log_k` | float | — | `-0.106` | Zhong & Mucci rate constant; `K = exp(log_k)`, not `10^` |
| `calcite_exponent` | float | — | `2.87` | |
| `aragonite_log_k` | float | — | `1.11` | the 35 < S < 44 band |
| `aragonite_exponent` | float | — | `2.26` | |
| `aragonite_low_log_k` | float | — | `1.53` | the dialog's other aragonite entry |
| `aragonite_low_exponent` | float | — | `2.33` | |
| `reproduce_undersaturated_nan` | bool | — | `false` | ⚠️ defect flag: the exe's `(Ω−1)^N` is NaN for Ω < 1 and poisons the run; we return 0 |
| `reproduce_aragonite_band_gap` | bool | — | `false` | ⚠️ defect flag: the exe reports zero aragonite rate for 25 ≤ S ≤ 35 |
| `reproduce_effluent_concentration_scaling` | bool | — | `false` | ⚠️ defect flag: the exe multiplies effluent TA/DIC by density in kg/L (a µmol/kg treated as µmol/L, +2.7 %) |
| `pitzer` | bool | — | `false` | ⭐ the second brucite engine (§8.4): PHREEQC / Pitzer adds `omega_brucite_phreeqc` and `ph_total_phreeqc` beside the unchanged columns; needs `pip install 'plumes2[pitzer]'` |

### 3.10 `effluent_do` (mg/L)

<!-- schema: plumes2.config.EffluentDO -->

| field | type | unit | default | meaning |
|---|---|---|---|---|
| `dissolved_oxygen` | float ≥ 0 | mg/L | `0.0` | effluent DO; dilutes as `1/D` |
| `idod` | float ≥ 0 | mg/L | `0.0` | immediate oxygen demand, subtracted from the effluent |
| `cbod5` | float ≥ 0 | mg/L | `0.0` | inert in the near field (measured); drives the far-field sag |
| `nbod5` | float ≥ 0 | mg/L | `0.0` | as above |
| `cbod_decay` | float > 0 | 1/day | `0.23` | at 20 °C |
| `nbod_decay` | float > 0 | 1/day | `0.1` | at 20 °C |
| `theta_c` | float > 0 | — | `1.047` | `k(T) = k(20) · θ^(T−20)` |
| `theta_n` | float > 0 | — | `1.08` | |

### 3.11 The enumerations (write the lower-case value)

<!-- enum: plumes2.seawater.EquationOfState -->

| value | meaning |
|---|---|
| `eos80` | UNESCO 1983, at zero pressure. **Default** — the standard the port's own science rests on |
| `knudsen` | Knudsen (1901) σ_t. **What the exe computes**, to one rounding digit over 51 670 rows; pick it to compare against a trace |

<!-- enum: plumes2.config.ExeBuild -->

| value | meaning |
|---|---|
| `current` | 2026 builds: wastefield width `= (n−1) · spacing · |cos(H-angle − current)| + diameter`. **Default** |
| `legacy` | pre-2026 builds: no cosine. The same project gives 109.59 m here and 96.29 m on `current` |

<!-- enum: plumes2.config.EddyDiffusivityLaw -->

| value | meaning |
|---|---|
| `four_thirds` | the 4/3 power law — open water. **Default** and the operator's decision |
| `constant` | constant eddy diffusivity — channelised inland waters; dilutes more slowly |
| `linear` | linear growth |

<!-- enum: plumes2.config.PHScale -->

| value | meaning |
|---|---|
| `free` | **default** for a typed effluent pH — what the exe's dialog labels the field |
| `total` | what the exe *reports* on its default constants, and what our `ph_total` column is |
| `seawater` | |
| `nbs` | |

<!-- enum: plumes2.config.ChemistrySolver -->

| value | meaning |
|---|---|
| `none` | no chemistry columns, even when the case carries the tables — a plain dilution run |
| `pyco2sys` | **default**; the exe's lineage — `omega_brucite` is the Davies upper bound, and `carbonate.pitzer` may add the Pitzer column beside it |
| `phreeqc` | every chemistry column from PHREEQC / `pitzer.dat` on free-ion activities — `omega_brucite` *is* the Pitzer value; its carbonate minerals sit 2–10 % above Mucci's on the site water (§8.4); needs `plumes2[pitzer]` |
| `all` | both engines on every row for cross-comparison: PyCO2SYS's columns under their usual names and PHREEQC's beside them as `*_phreeqc` (the `PHREEQC_COLUMNS` table, §6.1); the report draws the PHREEQC lines dashed and adds a comparison table |

<!-- enum: plumes2.crossplume.SimilarityProfile -->

| value | shape | peak/mean round | slab | meaning |
|---|---|---|---|---|
| `parabolic` | `1 − u²` | 2.000 | 1.500 | the exe's `Default Profile`; every archived comparison. **Default** |
| `three_halves` | `[1 − u^1.5]²` | 3.889 | 2.222 | the exe's `3/2 Power law Profile`; the 3rd edition's own |
| `exe_gaussian` | `exp(−3.57 u²)` | 3.670 | 2.148 | the exe's `Gaussian Profile` — **not** the literature's |
| `gaussian` | `exp(−2 u²)` | 2.313 | 1.672 | the jet-and-plume literature's Gaussian, truncated at the edge |

<!-- enum: plumes2.ambient.ExtrapolationPolicy -->

| value | meaning |
|---|---|
| `clamp` | hold the end value past the profile. **Default** |
| `linear` | continue the end gradient (can go negative; what broke case09) |
| `raise` | refuse |

<!-- enum: plumes2.nearfield.merging.ConfinedDecrements -->

| value | meaning |
|---|---|
| `all` | every merging decrement at the confined half-height. **Default since 2026-08-21** — UM3's documented mechanism, 0.98 % post-merge out of sample |
| `none` | the port's former default; carries the merged-radius runaway (15–35 % past `d/L` 3) |
| `growth` | only the growth term — refuted (row 264d), kept as a refutation |
| `walk` | walks from round to confined over `d/L` 1–2 — refuted, kept |

### 3.12 A complete example

```yaml
description: Ebb dose scenario, illustrative geometry
diffuser:
  port_diameter: 0.0127
  port_elevation: 0.0
  vertical_angle: 0.0
  horizontal_angle: 0.0
  n_ports: 25
  port_spacing: 0.6096   # 2 ft -- metres inside, always; a mis-unit here once cost a study rerun
  port_depth: 2.0
effluent:
  flow: 0.000219
  salinity: 35.0
  temperature: 10.0
mixing_zone:
  acute_distance: 20.7
  chronic_distance: 207.0
ambient:
  levels:
  - {depth: 0.0, current_speed: 0.02, current_direction: 0.0, salinity: 31.0, temperature: 11.0, farfield_speed: 0.02}
  - {depth: 5.0, current_speed: 0.02, current_direction: 0.0, salinity: 31.5, temperature: 10.0, farfield_speed: 0.02}
  - {depth: 15.0, current_speed: 0.02, current_direction: 0.0, salinity: 32.0, temperature: 9.0, farfield_speed: 0.02}
  chemistry:                       # must reach below the 2 m port
  - {depth: 0.0, total_alkalinity: 2900.0, dic: 2500.0}
  - {depth: 15.0, total_alkalinity: 2900.0, dic: 2500.0}
effluent_chemistry:                # TA at the intake's DIC -- the feedstock axis
  total_alkalinity: 6000.0
  dic: 2500.0
carbonate:
  k1k2_option: 10
  kso4_option: 1
near_field:
  max_rise_or_fall: 3
  stop_at_surface: false
far_field:
  max_distance: 500.0
  max_dilution: 10000.0
```

Anything left out takes the default in the tables above; `dump_case` writes only what differs from
the defaults.

---

## 4. The Python API, by task

Import paths are stable; everything below is public (`__all__`) and documented in place — run
`python docs/build.py` and open `docs/api/index.html` for the rendered reference.

### 4.1 Load a case

```python
from plumes2 import Case, load_case, load_project, read_dat, read_prj

case = load_case("case.yaml")                                     # ours
case = load_project("project.prj").to_case()                      # the exe's, plus CSVs beside it
case = load_project("project.prj", warn_on_drift=False).to_case() # silence ProjectDriftWarning
case = Case.model_validate({...})                                 # from a plain dict
prj  = read_prj("project.prj")                                    # lossless PrjFile, no validation
```

`load_project` finds the six CSV tables next to the `.prj` and reads chemistry and DO from them;
the `.prj` is authoritative where they disagree (`ProjectDriftWarning`).

**Ambient tables from plain CSVs** — for site data kept in ordinary tidy files rather than in
the YAML or the exe's dialect (one row per depth, headers = the §3.5 field names, blank cell =
default, unknown header = error naming the valid ones):

```python
from plumes2 import ambient_from_files

profile = ambient_from_files(
    "ambient_levels.csv",                  # §3.5.1 columns; required
    chemistry="ambient_chemistry.csv",     # §3.5.2 columns; optional
    dissolved_oxygen="ambient_do.csv",     # §3.5.3 columns; optional
)
case = base.model_copy(update={"ambient": profile})
```

See [`examples/run_from_files.py`](examples/run_from_files.py) for the whole pattern, executed
by the suite.

### 4.2 Build a variant

Pydantic models are frozen; make copies:

```python
dosed = case.model_copy(update={
    "effluent_chemistry": EffluentChemistry(total_alkalinity=6000.0, dic=2500.0),
    "near_field": case.near_field.model_copy(update={"max_rise_or_fall": 3}),
})
dosed = Case.model_validate(dosed.model_dump())   # re-run the validators after model_copy
```

⚠️ `model_copy` **skips validation**. Re-validate as above, or use `plumes2.sweep.with_updated`,
which does it for you:

```python
from plumes2.sweep import with_updated
dosed = with_updated(case, "effluent_chemistry.total_alkalinity", 6000.0)
```

### 4.3 Run it

```python
from plumes2.results import run, write_results, mixing_zone_values, sample_at_distance

results = run(case)                       # samples=200
results = run(case, samples=3000, source="case.yaml")

results.nearfield          # DataFrame, one row per sample (§6.1)
results.farfield           # DataFrame or None (§6.2)
results.termination        # e.g. "oscillation limit" (§6.3)
results.end_time           # s
results.final_dilution     # flux-averaged, at the near-field end
results.has_chemistry, results.has_oxygen
results.case, results.provenance
results.solution           # the raw NearFieldSolution: .sample(times), .oscillations, .events

write_results(results, "out/")            # nearfield.csv, farfield.csv, case.yaml, provenance.yaml

mixing_zone_values(results)               # 2 rows (acute, chronic) x every column + region
sample_at_distance(results, 12.5)         # Series: region, distance_m, every column, interpolated
```

`region` is `"nearfield"`, `"farfield"`, or `"beyond"` — and `beyond` is **NaN, never an
extrapolation** (the tables ended before the asked distance: far field disabled, no current, or
the dilution stop reached).

### 4.4 Sweep (the dose study's harness)

```python
from plumes2.sweep import sweep, brucite_extract, mixing_zone_extract

frame = sweep(
    base_case,
    axes={
        "effluent_chemistry.total_alkalinity": [3000, 4000, 6000, 10000, 20000],
        "diffuser.port_depth": [2.0, 5.0, 10.0],
    },
    extract=brucite_extract,     # default: mixing_zone_extract
    samples=3000,                # dense, for the Omega = 1 crossing
)
```

- **Axes** are dotted paths into the case; the sweep is the full cross product, last axis
  fastest. A path through a `null` section (`effluent_chemistry.…` on a case without one) is an
  error with the fix in the message.
- **Cells are re-validated**, so a bad value fails its own cell.
- **A failed cell is a row, not a crash**: `error` holds `"ExceptionType: message"`, else `""`.
- **Warnings are data**: `warnings` holds the warning category names the cell raised,
  `;`-joined (e.g. `ConstantRangeWarning;GeometryWarning`).

Columns of the returned frame: one per axis path (its value), then whatever `extract` returned,
then `error`, `warnings`.

`mixing_zone_extract(results)` gives `termination`, `nearfield_end_dilution`, and every
`mixing_zone_values` column as `acute_<column>` and `chronic_<column>` (including
`acute_region`, `chronic_region`).

`brucite_extract(results)` gives all of the above plus:

| column | meaning |
|---|---|
| `port_ph_total`, `port_dic_umol_kg`, `port_omega_brucite`, `port_omega_aragonite` | first near-field row |
| `nearfield_peak_omega_brucite`, `nearfield_peak_ph_total` | maxima anywhere in the near field |
| `nearfield_end_distance_m`, `nearfield_end_time_s`, `nearfield_end_ph_total`, `nearfield_end_omega_brucite` | where the near field stops |
| `port_omega_brucite_phreeqc`, `nearfield_peak_omega_brucite_phreeqc`, `nearfield_end_omega_brucite_phreeqc` | the same three readings from the second engine — only when `carbonate.pitzer` is on |
| `omega1_dilution`, `omega1_time_s`, `omega1_distance_m` | where Ω_brucite last falls through 1 (log-interpolated) |
| `omega1_region` | `never` (port already under-saturated), `nearfield`, `farfield`, or `beyond_farfield` (still > 1 where the tables end; values are then the last row and a **floor**) |

⚠️ `omega1_*` is thermodynamic and **flux-averaged**; the centreline crossing is
`(peak/mean) × omega1_dilution` under the chosen profile (§3.11), and there is no brucite rate law,
so Ω = 1 is a necessary condition for precipitation, not a prediction of it.

### 4.5 Compare several runs on one set of axes

```python
from plumes2.comparison import Comparison, differences
from plumes2.report import build_comparison_report, render_comparison

comparison = Comparison((run_a, run_b, run_c))
comparison.labels()                     # ("port_spacing 1", "port_spacing 2", ...) -- derived, not typed
comparison.differences                  # [Difference(field="diffuser.port_spacing", values=(1.0, 2.0, 2.5))]
comparison.frame()                      # one long frame with a `run` column; farfield=True for Brooks
build_comparison_report(comparison, "overlay.html", units="US", title="Spacing")
build_combined_report(comparison, "study.pdf", names=("2 ft", "1 m"))   # overlays, then each run's full report, one file
```

The legend is a diff of the *resolved* cases (defaults included); identical cases label
`identical`, and the overlay refuses more runs than the palette has slots.

### 4.6 Reports and plot frames

```python
from plumes2.report import build_report, render_report, report_from_dat
from plumes2.plotframe import from_results, from_dat, PlotFrame

build_report(results, "report.pdf", units="SI", title=None)            # from a run; .pdf or .html by suffix
report_from_dat("trace.dat", "report.pdf", case_path="case.yaml")      # from an exe trace
html = render_report(results)                                          # the HTML page as a string

plot = from_results(results)                                          # PlotFrame, no caveats
plot = from_dat(read_dat("trace.dat"), "trace.dat", case=case, secondaries=True,
                profile=SimilarityProfile.PARABOLIC)                  # declare the exe option it ran under
plot.frame, plot.source, plot.origin ("run" | "dat"), plot.caveats, plot.derived, plot.case, plot.profile
```

A `.dat` frame **always carries caveats** (three printed decimals; no provenance; the column set was
a GUI choice) and names in `derived` every column that was computed rather than read. A chemistry
trace without `P-Sal`/`P-Temp` cannot have its secondaries re-solved unless you pass `case`
(`MissingColumnError` names the missing column otherwise).

### 4.7 Units on the way out

```python
from plumes2.display import convert_frame, SYSTEMS, SI, US
frame_us = convert_frame(results.nearfield, "US")   # depth_m -> depth_ft, temperature_degC -> temperature_degF, m3_s -> MGD
```

The solver is SI, always; conversion is a copy with **renamed columns**, and converting a frame
twice raises (`UndeclaredColumnError`), as does an unregistered column. `US` = feet, ft/s, °F,
MGD; density and the chemistry stay kg/m³ and µmol/kg (mg/L was deliberately declined).

### 4.8 The exe's files

```python
from plumes2.io import read_dat, read_prj, write_prj, load_project, prj_from_case, dump_case, DatFile

dat = read_dat("ModelResults_TxtOutputs.dat")
dat.nearfield                    # DataFrame indexed by step; the exe's own column names
dat.farfield                     # DataFrame or None
dat.events                       # banners: Event(text, next_step, line_number)
dat.event_steps()                # {"merging happened": [128], "Plume traps": [...], ...}
dat.echoed_tables["Diffuser"]    # the input echo (two decimals -- read inputs from the .prj)
dat.wastefield_width, dat.eddy_diffusivity_law, dat.merged, dat.has_farfield, dat.final_step

write_prj(prj_from_case(case), "generated.prj")   # byte-formatted as the exe writes them
written_units(prj_from_case(case))                 # ["diffuser.port_spacing: 2 ft (selector 2)", ...]
```

⚠️ **A written `.prj` may store a value in feet or MGD.** Each `.prj` column carries an integer
unit selector (`plumes2.units`), and the writer picks, per value, the *evidenced* unit that survives
the format's three significant figures best: 0.6096 m is written as `2.00` under the feet flag
because 0.610 m would be 0.07 % off. The exe reads either correctly — ledger row 290 pins it on
case55, where the site's spacing and both mixing-zone distances went out in feet and came back
labelled `(ft)` with the wastefield width right to 0.01 m — but a person opening the file in the
GUI sees the stored number in the stored unit. `written_units` lists every such column; `plumes2
info` prints it and every experiment note carries it. Read a `.prj` value together with its
dropdown, never alone (the Dec-2025 feet-as-metres slip, row 49, is what this guards against).

Exe column → our name (`plumes2.plotframe`): `Dilutn`/`Avg-Dil` → `dilution`, `CL-Dil` →
`centreline_dilution`, `P-dia` → `plume_diameter_m`, `Depth` → `depth_m` (sign flipped),
`x-posn`/`y-posn` → `x_m`/`y_m`, `P-Sal` → `salinity_psu`, `P-Temp` → `temperature_degC`,
`P-Den` → `density_kg_m3`, `Time` → `time_s`, `TA`/`DIC` → `total_alkalinity_umol_kg`/`dic_umol_kg`,
`pH`/`OmegaC`/`OmegaA` → `ph_exe`/`omega_calcite_exe`/`omega_aragonite_exe`, `DO` →
`dissolved_oxygen_mg_l`.

⚠️ **What a `.prj` does not carry** (PLAN_HISTORY §7b): any chemistry (effluent or constants), the DO tab,
the far-field stops (distance and dilution), the exe build, the similarity profile, and (as far as
anyone has decoded) the eddy-diffusivity selection. It *does* carry
the stop-at-surface box (`nearfield_flags[1]`) and the rise/fall count (`nearfield_flags[3]`),
and **the exe rewrites the `.prj` on every run** (there is no Save-As), so a project on disk is the
*as-run* state of its last run.

⚠️ **`.dat` traps, all measured**: the chemistry columns are **µmol/kg despite the `(mmol/m3)`
heading**; the step table is **fixed-width, 10-character fields** — a value that fills its field
abuts its neighbour with no space (`R_cal` at high dose), which `read_dat` handles and
`str.split()` does not; `P-Sal`, `P-Temp` and the other scalar columns are printed **one
integration step ahead** of `Dilutn` (row 258c); the diffuser echo rounds to two decimals.

### 4.9 Generate an exe experiment

```python
from plumes2.experiments import (Experiment, write_experiment, fill_ambient_ph,
                                 classify_farfield_stop, check_farfield_session_state)

path = write_experiment(
    Experiment(
        name="dose_TA6000",
        case=dosed,
        question="Does the exe's CO2SYS track PyCO2SYS above pH 10.5?",
        predictions={"port pH (total)": "10.653"},        # write these BEFORE running
        settings=("all output columns", "No. of maximum plume rise or fall = 3",
                  "stop plume at bottom hit: ticked"),      # the default tuple; add what you need
        notes=("Which exe build ran this -- write it down.",),
    ),
    "reference_cases/pending",
)
# -> reference_cases/pending/dose_TA6000/{dose_TA6000.prj, AmbientChem_dose_TA6000.csv, README.md}
```

The README it writes is the run sheet: what to set in the GUI (the `.prj` cannot carry it), the
far-field stops derived from the case, the predictions, and the provenance digest. A blank ambient
pH is filled with PyCO2SYS's free-scale solution of that row (`fill_ambient_ph`) because the GUI
refuses a blank and ignores the value.

When a trace comes back:

```python
dat = read_dat(path / "dose_TA6000.dat")
check_farfield_session_state(dat, dosed)   # [] if the far field stopped where the case declared
classify_farfield_stop(dat)                # FarfieldStop(kind="distance"|"chronic_default"|"dilution"|"nan"|"unknown", ...)
```

Graduate a finished experiment by moving its directory to `reference_cases/caseNN_name/` with a
README of what it settled. ⚠️ `_archive_traces` globs one level deep, so a graduated trace enters
**every archive-wide ledger sweep** the moment it lands; expect pinned counts to move, and the
outcome cache to invalidate itself.

### 4.10 Chemistry on its own

```python
from plumes2.chem import (resolve_constants, solve_from_alkalinity_dic, solve_from_alkalinity_ph,
                          solubility_brucite, omega_brucite, magnesium_from_salinity,
                          effluent_endmember, plume_carbonate, precipitation_rate, CALCITE)

K = resolve_constants(exe_k1k2=10, exe_kso4=1)              # the exe's defaults; raises UnknownConstantOptionError otherwise
state = solve_from_alkalinity_dic([2900.0], [2500.0], salinity=31.1, temperature=10.6, constants=K)
state = solve_from_alkalinity_ph([4000.0], [10.5], 35.0, 10.0, ph_scale=PHScale.FREE, constants=K)
state.ph_total, state.ph_free, state.pco2, state.carbonate, state.bicarbonate, state.hydroxide
state.omega_calcite, state.omega_aragonite
state.omega_brucite(solubility_brucite(state.salinity, state.temperature))   # upper bound, no ion pairing
solubility_brucite(S, T, log_ksp_25c=-11.16)                                 # the superseded constant, on request
```

Concentrations in and out are µmol/kg (`hydroxide` too); `pressure` (dbar) defaults to 0, as the
exe evaluates it. Every solve passes through one chokepoint that emits `ConstantRangeWarning` /
`PHRangeWarning` (§5).

### 4.11 Seawater, far field, oxygen — the pieces

```python
from plumes2.seawater import density, density_of, knudsen_density, EquationOfState, densimetric_froude_number
density(salinity, temperature, pressure_dbar=0.0)                      # EOS-80, kg/m3
density_of(S, T, equation_of_state=EquationOfState.KNUDSEN)           # the exe's
case.densimetric_froude_number()                                       # < 1 -> DesignWarning

from plumes2.farfield import BrooksParameters
p = BrooksParameters(initial_width=96.3, initial_dilution=170.0, current_speed=0.05,
                     alpha=3.0e-4, law=EddyDiffusivityLaw.FOUR_THIRDS, decay_per_day=0.0)
p.width(x), p.dilution_factor(x), p.total_dilution(x), p.travel_time(x)   # x from the transition, m

from plumes2.farfield.standalone import StandaloneRequest, independent_farfield
independent_farfield(StandaloneRequest(initial_dilution=170, initial_width=96.3,
                                       mixing_zone_distance=500, current_speed=0.05))

from plumes2.biochem import near_field_oxygen, far_field_oxygen, ultimate_bod, rate_at_temperature
```

### 4.12 Provenance and validation

```python
from plumes2.provenance import case_digest, provenance, git_state
case_digest(case)                 # SHA-256 over the fully resolved case (defaults included)
provenance(case, source="case.yaml").to_dict()

from plumes2.validation import run_all, coverage_by_phase, rows_by_agreement, TARGETS, Agreement
outcomes = run_all()              # every ledger target, measured; Outcome.passed per row
coverage_by_phase()               # {phase: (rows executable, numbered rows)}
```

---

## 5. Warnings and errors — what each one is asking you to do

Warnings never stop a run; they are reprinted as `note:` lines by the CLI and recorded per cell by
`sweep`. Filter them with `warnings.catch_warnings()` / `warnings.simplefilter("ignore", Category)`.

| category | when | what to do |
|---|---|---|
| `GeometryWarning` (`plumes2.config`) | the inputs contradict each other but the exe would run them: seabed below the ambient profile, chemistry table starting below the port, multiport with zero spacing | check the profile depth; the exe extrapolates and case09 shows where that ends |
| `DesignWarning` (`plumes2.config`) | discharge Froude number < 1 — buoyancy dominates the port's own momentum; the near-field model is outside its regime | a design question, not a model one; the result is still computed |
| `ConstantRangeWarning` (`plumes2.config`) | the plume or the effluent left the selected K1/K2 option's fitted S/T window (Lueker: S 19–43, T 2–35); says which end and what share of the run | for an *effluent*, change the input or pick a covering option (13 = Millero 2006, S 1–50); for a *plume*, read the pH as an extrapolation |
| `PHRangeWarning` (subclass of the above) | a solved pH left **7.5–12.05 total** — the range the exe and PyCO2SYS have actually been compared over | the number is unchecked; the fix is an exe run there, not a wider window |
| `ProjectDriftWarning` (`plumes2.io.project`) | a CSV beside the `.prj` disagrees with it | the `.prj` wins (the exe echoes its values); `Project.drift()` lists the cells |
| `ProjectAmbiguityWarning` | two CSVs share a layout and the project cannot say which is meant | rename or remove one |

Errors you will meet, and their meaning:

| error | meaning |
|---|---|
| `ValidationError: … depths must strictly increase` | an ambient list is out of order or has a duplicate depth |
| `ValidationError: acute mixing zone … is farther than the chronic one` | swap them |
| `ValidationError: effluent chemistry needs total_alkalinity plus exactly one of dic or ph` | see §3.8 — omit `dic`, do not zero it |
| `ValidationError: the ambient chemistry profile must extend deeper than the port` | add a chemistry row below `port_depth` (the exe refuses the same case) |
| `ValidationError: port depth … exceeds the seabed` | `port_elevation` is negative in effect |
| `ValueError: axis '…' passes through '…', which is None on this case` | give the base case that section before sweeping inside it |
| `UnknownConstantOptionError` | `k1k2_option` outside 1–14 or `kso4_option` outside 1–4 |
| `MissingColumnError` (`plumes2.plotframe`) | the `.dat` lacks a column a derived quantity needs; pass `case=` for S and T |
| `UndeclaredColumnError` (`plumes2.display`) | a column with no registered dimension, or a frame converted twice |
| `plumes2: unrecognised case file '…'` (exit 2) | the extension is not `.prj`, `.yaml` or `.yml` |

---

## 6. Output columns

Names carry their units. Order is fixed so two runs diff line for line.

### 6.1 `nearfield.csv` / `results.nearfield`

<!-- columns: plumes2.results.NEARFIELD_COLUMNS -->

| column | meaning |
|---|---|
| `time_s` | seconds since discharge; the sampling grid is even in time |
| `dilution` | flux-averaged — the exe's `Dilutn` |
| `centreline_dilution` | the exe's `CL-Dil`: `max(1, dilution / peak_to_mean)`; a mixing-zone limit is argued against this |
| `peak_to_mean` | centreline over mean concentration under `near_field.similarity_profile` (parabolic: 2.0 round, 1.5 merged slab) |
| `merged` | whether neighbouring plumes overlap here |
| `plume_diameter_m` | `2b`; the merged vertical extent where merging applies |
| `depth_m` | positive down |
| `x_m` | along the model's x axis from the port (the frame the angles are measured in) |
| `y_m` | along the model's y axis from the port |
| `speed_m_s` | plume element speed |
| `salinity_psu` | plume |
| `temperature_degC` | plume |
| `density_kg_m3` | plume, under `near_field.equation_of_state`, plus the `excess_density` tracer |

Appended when chemistry runs (both endmembers given):

<!-- columns: plumes2.results.CHEMISTRY_COLUMNS -->

| column | meaning |
|---|---|
| `total_alkalinity_umol_kg` | conservative with mixing |
| `dic_umol_kg` | conservative with mixing |
| `ph_total` | total scale — what the exe reports on its default constants |
| `pco2_uatm` | |
| `carbonate_umol_kg` | [CO₃²⁻] |
| `bicarbonate_umol_kg` | [HCO₃⁻] |
| `omega_calcite` | |
| `omega_aragonite` | ours runs 2.8–3.4 % above the exe's — a recorded, bounded disagreement |
| `omega_brucite` | `[Mg²⁺][OH⁻]² / Ksp*`, **an upper bound** (no ion pairing); the exe cannot report it — PLAN_HISTORY §8b |

Appended after those when `carbonate.pitzer` is on (§8.4):

<!-- columns: plumes2.results.PITZER_COLUMNS -->

| column | meaning |
|---|---|
| `omega_brucite_phreeqc` | `a(Mg²⁺) a(OH⁻)² / Ksp` by PHREEQC / `pitzer.dat` — free-ion activities, ion pairing included; 8–9× below `omega_brucite` at the site, and kept beside it, never in its place |
| `ph_total_phreeqc` | PHREEQC's pH on the total scale, per kg of solution — a diagnostic; agrees with `ph_total` to 0.03 from pH 7.7 to 12 |

Appended instead when `carbonate.solver` is `all` (§8.4) — every non-conservative chemistry column a
second time, by PHREEQC, so the two engines can be read row against row (TA and DIC are not
repeated; they are identical under every solver):

<!-- columns: plumes2.results.PHREEQC_COLUMNS -->

| column | meaning |
|---|---|
| `ph_total_phreeqc` | PHREEQC's pH on the total scale, per kg of solution |
| `pco2_uatm_phreeqc` | from the saturation index of CO₂(g) |
| `carbonate_umol_kg_phreeqc` | total [CO₃²⁻]: free plus the MgCO₃ pair |
| `bicarbonate_umol_kg_phreeqc` | free [HCO₃⁻] |
| `omega_calcite_phreeqc` | `10^SI`, PHREEQC's own `Ksp` and activities |
| `omega_aragonite_phreeqc` | `10^SI`, PHREEQC's own `Ksp` and activities — 2–10 % above Mucci's on the site water |
| `omega_brucite_phreeqc` | `a(Mg²⁺) a(OH⁻)² / Ksp`, free-ion activities, the same Xiong `Ksp` as `omega_brucite` |

Appended when DO runs:

<!-- columns: plumes2.results.OXYGEN_COLUMNS -->

| column | meaning |
|---|---|
| `dissolved_oxygen_mg_l` | plume DO from the path-integrated entrained ambient; BOD is inert in the near field |

### 6.2 `farfield.csv` / `results.farfield`

<!-- columns: plumes2.results.FARFIELD_COLUMNS -->

| column | meaning |
|---|---|
| `distance_m` | from the diffuser, along the far-field current (the table starts at the near-field end) |
| `width_m` | wastefield width |
| `dilution` | total: near-field end value × the Brooks factor |
| `dilution_factor` | Brooks alone, 1 at the transition |
| `travel_time_hr` | from the transition, at `farfield_speed` |

With chemistry, the nine chemistry columns of §6.1 are appended too: TA, DIC, S and T relax from the
near-field endpoint toward the ambient **at the trapping depth** with the Brooks factor, and pH and
the Ωs are re-solved. The first far-field chemistry row equals the last near-field row by
construction (checked against the exe on case47, 2026-08-26).

### 6.3 `results.termination`

One of `plumes2.nearfield.terminate.TerminationReason`: `oscillation limit` (the rise/fall
switch), `surface`, `seabed`, `dilution limit`, `step cap`, `time limit`, `non-physical state`.

---

## 7. Working with the executable

1. **Generate the project from a case** (§4.9). Never hand-edit a project; the archive's two worst
   gaps (test19's missing `.prj`, test34/35's stale one) were bookkeeping.
2. **Set what the `.prj` cannot carry** from the run sheet: chemistry endmember and constants,
   the DO tab, rise/fall count, the stop boxes, the similarity profile, **both far-field stops**
   (distance *and* dilution — an untyped distance defaults to the chronic boundary), and the
   far-field eddy-diffusivity law (`Constant` / `Linearly varying` / `4/3 power law` — 4/3 is the
   default and the only one ever archived).
3. **Read the six DO fields off the tab at run time** if DO is on; the tab retains the previous
   run's values, which has cost two rounds of analysis.
4. **Run.** The exe writes the `.prj` (as-run state) and the `.dat`.
5. **Copy both aside** under names that say which run they were, before the next run overwrites
   them. Record **which exe build** ran — the pre-2026 build has no width cosine and the file does
   not say.
6. Check the returning trace: `check_farfield_session_state`, the `nearfield_flags`, and the
   predictions in the run sheet.
7. Graduate to `reference_cases/caseNN_…/` with a README of what it settled.

The chemistry dialog's **unedited defaults discharge TA 2930 / DIC 2500** — a run that looks like a
dose and is not (case47's baseline).

---

## 8. Reference tables

### 8.1 `k1k2_option` — K1/K2 constant sets (CO2SYS numbering; PyCO2SYS `opt_k_carbonic`)

| # | reference | pH scale | T range °C | S range | medium |
|---|---|---|---|---|---|
| 1 | Roy et al. 1993 | total | 0–45 | 5–45 | artificial seawater |
| 2 | Goyet & Poisson 1989 | seawater | 1–40 | 10–50 | artificial seawater |
| 3 | Hansson 1973, refit Dickson & Millero 1987 | seawater | 2–35 | 20–40 | artificial seawater |
| 4 | Mehrbach et al. 1973, refit Dickson & Millero 1987 | seawater | 2–35 | 20–40 | artificial seawater |
| 5 | Hansson and Mehrbach, refit Dickson & Millero 1987 | seawater | 2–35 | 20–40 | artificial seawater |
| 6 | GEOSECS (original Mehrbach 1973) | NBS | 2–35 | 19–43 | real seawater |
| 7 | Peng et al. 1987 (original Mehrbach) | NBS | 2–35 | 19–43 | real seawater |
| 8 | Millero 1979, pure water only | — | 0–50 | 0 | pure water |
| 9 | Cai & Wang 1998 | NBS | 2–35 | 0–49 | real and artificial |
| **10** | **Lueker et al. 2000 — the exe's default** | total | 2–35 | 19–43 | real seawater |
| 11 | Mojica Prieto & Millero 2002 | seawater | 0–45 | 5–42 | real seawater |
| 12 | Millero et al. 2002 | seawater | 1.6–35 | 34–37 | field measurements |
| 13 | Millero et al. 2006 | seawater | 0–50 | 1–50 | real seawater |
| 14 | Millero et al. 2010 | seawater | 0–50 | 1–50 | real seawater |

`ConstantRangeWarning` fires against the selected row's T and S ranges. A 45 psu effluent is
outside 10 and inside 13.

### 8.2 `kso4_option` — bisulfate + total borate pairs

| # | bisulfate | total borate | PyCO2SYS (`opt_k_bisulfate`, `opt_total_borate`) |
|---|---|---|---|
| **1** | Dickson 1990 | Uppström 1974 | (1, 1) — the exe's default |
| 2 | Khoo et al. 1977 | Uppström 1974 | (2, 1) |
| 3 | Dickson 1990 | Lee et al. 2010 | (1, 2) |
| 4 | Khoo et al. 1977 | Lee et al. 2010 | (2, 2) |

### 8.3 Fixed constants worth knowing

| quantity | value | where |
|---|---|---|
| brucite `log Ksp` (25 °C) | **−10.95 ± 0.2** (Xiong 2008, adopted 2026-08-24); superseded −11.16 available as `log_ksp_25c=` | `chem.constants.solubility_brucite` |
| Ω_brucite = 1 as a pH threshold | `pH* = −log₁₀(Kw / √(Ksp* w³ / [Mg²⁺]))`, `w` the water fraction (kg water per kg solution; the product is molal since 2026-09-10): **9.41 total at S 32, 10 °C**; 8.93 at 20 °C; 9.78 at 2 °C (≈ 0.05 pH per °C, from `Kw`) | PLAN_HISTORY §8f; `tests/test_brucite.py` |
| extent on the fixed-DIC axis | `D* = (TA_eff − TA_amb) / (TA* − TA_amb)`, `TA* ≈ 4340 µmol/kg` at DIC 2500 — linear in dose | PLAN_HISTORY §8f |
| `[Mg²⁺]`, `[Ca²⁺]` | `0.0528171 · S/35`, `0.01028 · S/35` mol/kg | `chem.constants` |
| pH parity window | 7.5–12.05 total (exe vs PyCO2SYS: 0.011–0.025 pH, gap narrows above 11.5) | `chem.constants.PH_PARITY_WINDOW` |
| Ω_brucite error budget | Ksp 2.51×, activity coefficients 2.14×, temperature 1.007×; worst case 5.37× — **a bound, not an error bar** | `tests/test_brucite.py` |
| near-field accuracy vs the exe | 0.31 % jet phase; ~1.7 % after trapping; 1–7 % deeply merged (`d/L` > 3) | PORTING_THE_PHYSICS §1 |

---

### 8.4 `solver` and `pitzer` — which engine, and the second brucite column

`carbonate.solver` picks the engine that re-solves every mixed row. `none` runs the plume with no
chemistry columns at all, whatever tables the case carries. `pyco2sys`, the default, is the exe's
lineage and the engine every parity row was measured on. `phreeqc` hands the whole system to
PHREEQC with `pitzer.dat`: `ph_total` (built on the total scale, per kg of solution), the carbonate
species, `pco2_uatm`, and the three saturation states from free-ion activities — the column names
do not change, and `provenance.yaml`'s `chemistry_engines` names the solver. Under `phreeqc`
the carbonate minerals are PHREEQC's own: on the site water they sit **2 % above** Mucci's /
PyCO2SYS's at ambient pH and about 10 % above at a pH 10.5 port, one-signed, so the two engines
agree on the carbonates to the same order as the exe and PyCO2SYS do (3 %); the brucite column is
the one that differs, 8–9×, and is what `phreeqc` is for. The effluent's `(TA, pH) → DIC` resolution stays PyCO2SYS's under every
solver — it is the exe's decoded input pairing, not a model choice. `pitzer: true` is only valid
with the default solver (it adds the Pitzer brucite column *beside* PyCO2SYS's); with `phreeqc`
that column already is the Pitzer value and the setting is rejected.

**Cross-comparison: `solver: all`.** Every row is solved by both engines. PyCO2SYS's columns keep
their names; PHREEQC's follow as `*_phreeqc` (§6.1). The report's pH and saturation panels draw the
PHREEQC values as dashed lines in the mineral's own colour, and a *solver comparison* panel tabulates
port, near-field-end and worst-gap values for pH, pCO₂, the carbonate species and the three
saturation states. `brucite_extract` reads the `_phreeqc` brucite column in this mode too, under the
same `*_omega_brucite_phreeqc` keys. `pitzer: true` is rejected under `all` (every PHREEQC column is
already there).


`omega_brucite` is `[Mg²⁺][OH⁻]² / Ksp*` with total concentrations and Davies activity coefficients:
an **upper bound**, because ion pairing is not modelled and Davies is used past its range
(PORTING_THE_PHYSICS §4 explains the terms). Setting `carbonate.pitzer: true` solves the same
conservative `(TA, DIC, S, T)` row a second time through **PHREEQC** with its `pitzer.dat`
ion-interaction database (Brucite re-parameterised to the same Xiong 2008 `Ksp` the first column
uses) and appends `omega_brucite_phreeqc` and `ph_total_phreeqc`. Nothing else changes: pH, the
carbonate columns and `omega_brucite` are exactly what they were.

```powershell
.venv\Scripts\python.exe -m pip install "plumes2[pitzer]"     # phreeqpython; no compiler, nothing on PATH
```

Read the two brucite columns together. At the Macoma site the Pitzer value sits **8–9× below**
the bound, nearly flat from pH 7.7 to 12; the factor is mostly the hydroxide (PyCO2SYS's `[OH⁻]` is
a total of which ~45 % is the MgOH⁺ pair at pH 11–12, and it enters squared) and Pitzer's
γ(OH⁻) ≈ 0.54 against Davies' 0.75. Because `Ω_brucite = 1` is a pH threshold, a factor 7–8 in Ω
is +0.42 to +0.46 in that threshold. The two columns are kept side by side permanently; the report's
saturation panel draws both, and `brucite_extract` carries both. Without the extra installed a case
that asks raises `PitzerUnavailableError` naming the install line; a row PHREEQC cannot converge is
NaN and named in a `PitzerConvergenceWarning`. The `provenance.yaml` of a run records the engine
(`chemistry_engines`).

## 9. Tests, lint, types, docs

```powershell
.venv\Scripts\python.exe -m pytest -n auto --dist loadfile        # everything, ~2.5-3 min (~4.5 cold)
.venv\Scripts\python.exe -m pytest -m "not slow"                  # the fast lane
.venv\Scripts\python.exe -m pytest tests\test_sweep.py -q         # one module
.venv\Scripts\python.exe -m pytest --wipe-outcome-cache           # discard the warm ledger cache first
.venv\Scripts\python.exe -m pytest --strict-slow-marker           # fail if an unmarked test exceeds 1 s
$env:PLUMES2_NO_CACHE = "1"; .venv\Scripts\python.exe -m pytest   # never read or write the cache
.venv\Scripts\plumes2.exe validate                                 # the ledger alone
.venv\Scripts\ruff.exe check src tests ; .venv\Scripts\ruff.exe format src tests
.venv\Scripts\mypy.exe                                             # files configured in pyproject
.venv\Scripts\python.exe docs\build.py                             # API reference -> docs\api\ (git-ignored)
.venv\Scripts\python.exe docs\build.py --serve                     # live preview
```

⚠️ **`--dist loadfile`, never bare `-n auto`**: per-file distribution keeps a module's shared
fixtures on one worker; scattering them turns one measurement into N and a 2.5 s module into 233 s.

Markers: `golden` (validated against an exe `.dat`), `manual` (a number printed in a manual),
`slow` (over one second, enforced by the guard in `tests/conftest.py`).

The measured-outcome cache `.plumes2_outcome_cache.json` is keyed on a digest of `src/plumes2` plus
every archived `.dat`/`.prj`/`.csv`; any edit to either discards it whole. It expires after seven
days.

Studies live in `studies/` and are plain scripts:

```powershell
.venv\Scripts\python.exe studies\dose_dry_run.py            # ~4.5 min; --replot redraws from the saved CSVs
.venv\Scripts\python.exe studies\dose_parity_experiment.py  # regenerates reference_cases\pending\dose_parity
.venv\Scripts\python.exe studies\ebb_dose_study.py          # the study at Ebb's default profile, ~3.5 min; --replot
```
