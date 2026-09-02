# Phase 9's first dry run — the alkalinity-dose sweep on case03 (2026-08-25)

> ✅ **Superseded the next day.** Everything this run said was missing has since landed: the exe
> ran the feedstock axis ([case47](../../reference_cases/case47_dose_parity/README.md), parity to
> pH 12), Ebb's discharge is specified as (TA, DIC), the similarity profile was decided (parabola,
> others selectable), and the study proper ran at Ebb's default profile —
> [`../ebb_dose_study/`](../ebb_dose_study/README.md). This file is the record of the dry run as
> it stood; PLAN section references below point into `PLAN_HISTORY.md`.

**What this is.** The first end-to-end run of the machinery the port was built for: `sweep.py`
(PLAN 8.3) over an alkalinity dose, reading pH and Ω at the mixing-zone boundaries. It was run to
find what breaks, on the one chemistry case the archive has (case03, Macoma, 25 × 0.0127 m ports at
2 m, 35 psu effluent at 0.22 L/s). ⛔ **Nothing here is publishable**: it is not Ebb's geometry or
dose, PLAN 8.4 (the similarity profile) is unsettled, and every Ω_brucite is the upper bound §8b
describes. Produced by [`../dose_dry_run.py`](../dose_dry_run.py); `sweep.csv`, `mgoh2_axis.csv`
and `depth_probe.csv` are the frames, the two SVGs the figures.

| sweep | axis | cells | wall |
|---|---|---|---|
| `sweep.csv` | TA 3000–20 000 at **pH 10.5 (free) held**, DIC derived — case03's own entry style — × flow 0.22 / 1.0 / 5.0 L/s | 24 | 198 s |
| `mgoh2_axis.csv` | TA 3000–20 000 at **DIC 2500 held**, pH floating — an Mg(OH)₂ feedstock in intake seawater | 8 | 51 s |
| `depth_probe.csv` | TA 4000 / 8000 × port depth 2 / 5 / 11 m | 6 | 15 s |

## Findings, in the order they matter

### 1. ⭐⭐ The archive's dose axis is not a brucite axis

Under case03's entry style — TA plus a held pH — **Ω_brucite at the port is 131.4 at every dose
from 3000 to 20 000 µmol/kg**, and the port pH is 10.437 at every dose. This is arithmetic, not a
bug: `Ω_brucite = [Mg²⁺][OH⁻]² / Ksp*`, pH fixes `[OH⁻]`, salinity fixes `[Mg²⁺]`, and the alkalinity
only moves the *derived* DIC (1646 → 16 800 across the axis). Nothing about brucite risk at the port
can be learned by sweeping it.

The axis a feedstock actually moves along is **TA at the intake's DIC**, pH floating. On it the
port pH climbs 8.45 → 9.17 → 9.84 → 10.67 → 11.26 → 11.50 → 11.82 → 12.01 and Ω_brucite 0.014 →
0.38 → 8.3 → 385 → 5 800 → 18 000 → 78 000 → 181 000. Ω_aragonite saturates at ~37.8 above TA 6000
because the carbonate is DIC-limited. **`mgoh2_axis.csv` is the dry run of the study; `sweep.csv`
is the dry run of the archive's habit.** Which one Ebb's discharge resembles is an input nobody
has written down yet.

### 2. ⭐⭐ `Ω_brucite = 1` is a pH threshold, and the risk window is centimetres

With magnesium conservative, Ω = 1 is one pH: `[OH⁻]* = √(Ksp*/[Mg²⁺])`, `pH* = −log₁₀(Kw/[OH⁻]*)`.
On Xiong (2008)'s `log Ksp` = −10.95 that is **pH 9.43 (total) at S 32, T 10 °C**, and every dense
run crosses Ω = 1 at pH 9.41–9.42 whatever the dose — pinned analytically in
`tests/test_brucite.py::test_the_saturation_ph_is_about_nine_point_four_in_cold_coastal_water` and
against a run in `tests/test_sweep_chemistry.py` (agreement 0.01 pH).

⚠️ **The threshold is strongly temperature-dependent, and for row 197's reason.** Brucite
dissolution is athermal so `Ksp*` barely moves, but `pKw` falls ~0.04 per °C: **pH* = 8.95 at
20 °C, 9.43 at 10 °C, 9.80 at 2 °C.** A quoted threshold must name its temperature, and a cold
ambient is the more protective one. Salinity is a second-order effect (9.38 at S 35).

So the dose only sets how much dilution it takes to fall to pH*. Sampled at 3000 points:

| axis | dose | Ω at port | Ω = 1 at dilution | time | distance |
|---|---|---|---|---|---|
| pH held | TA 4000 (case03) | 131 | **1.71** | 0.27 s | **1.1 cm** |
| pH held | TA 20 000 | 131 | 3.71 | 1.9 s | 5.9 cm |
| DIC held | TA 5 000 (pH 9.84) | 8.3 | 1.46 | 0.17 s | 0.7 cm |
| DIC held | TA 6 000 (pH 10.67) | 385 | 2.16 | 0.47 s | 1.8 cm |
| DIC held | TA 10 000 (pH 11.50) | 18 000 | 4.95 | 3.0 s | 8.9 cm |
| DIC held | TA 20 000 (pH 12.01) | 181 000 | **11.9** | 5.7 s | **15.5 cm** |

⛔ **This retracts the "first ~30 seconds and first ~100× of dilution" risk window** that PLAN §8b
and PORTING_THE_PHYSICS §4 carried. It was read off a three-row table whose second row happened to
be at 27.8 s; the true thermodynamic window at case03's dose is under a second and an inch, and
even at pH 12 it is a dozen dilutions and the first few port diameters. PORTING_THE_PHYSICS is
corrected; the PLAN §8b text stands with a dated note.

⭐ **On the fixed-DIC axis the extent is linear in dose.** With DIC the same on both sides of the
port, pH is a function of TA alone, so pH* is a fixed **TA\* ≈ 4340 µmol/kg** at DIC 2500 and the
crossing dilution is `D* = (TA_eff − TA_amb) / (TA* − TA_amb)`: 2.16 at 6000, 4.95 at 10 000, 11.9
at 20 000 — a straight line through the table above. That is the dose–response of the *extent*,
and it is analytic once pH*(S, T) and the intake DIC are known. A second dilution model is not
needed to draw it; what the plume model adds is the *time and distance* that dilution takes.

### 3. Both regulatory boundaries are far-field numbers, blind to brucite

case03's acute boundary is 20.7 m and the near field is 2.8–5.3 m long, so `mixing_zone_values`
answers **both** boundaries from Brooks (`region == "farfield"` on all 32 cells), and there
Ω_brucite is 0.0085–0.0104 at every dose. A study that reports Ω only at the boundaries reports no
brucite risk at all while the port sits at Ω = 10⁵. The extract used here adds the near-field peak
and the Ω = 1 extent; `sweep.mixing_zone_extract` alone is not a brucite observable. What the
boundaries *do* see is pH and Ω_aragonite: chronic pH 8.384 → 8.395 and Ω_arag 4.65 → 4.75 across
the feedstock axis at 0.22 L/s — a few hundredths, because the chronic dilution is ~1850.

### 4. ⚠️ PLAN 8e item 2's "runaway-precipitation threshold" cannot be run as written

`chem/precipitation.py` has calcite and aragonite rate laws only, and §8b itself says not to infer
alkalinity loss from Ω without kinetics. What this run reports is the **thermodynamic** threshold
(finding 2). A self-limiting-dose claim needs a brucite rate law — new scope, not a sweep.

### 5. The harness held up; what it lacked

- **A failed cell is a row.** The depth probe's 5 m and 11 m cells fail with `ValidationError: the
  ambient chemistry profile must extend deeper than the port: its deepest level is 4 m` — the
  right error, in the row, with the four other cells intact. It also says why a **port-depth axis
  cannot be run on case03**: its ambient chemistry table stops at 4 m. A study needs an ambient
  chemistry profile that reaches the seabed.
- **Warnings are data.** Every cell carries `GeometryWarning` (case03's seabed at 17 m sits below
  its 15 m ambient profile — a property of the archived case, not of the dose). No cell raised
  `ConstantRangeWarning`: TA 20 000 at S 35 stays inside Lueker's S 19–43, and the constants carry
  no TA window to leave. ⚠️ That last point is worth knowing — nothing warns that PyCO2SYS is being
  asked for pH 12 seawater, which is far outside any constant set's calibration.
- **Sampling.** At the default 200 samples the log-interpolated Ω = 1 crossing overstated the
  dilution (2.2 for 1.7) because the crossing sits a fraction of a second from the port; the script
  now asks for 3000. Integration cost is unchanged — `samples` only picks rows off the dense
  output.
- **Every cell terminated on `oscillation limit`** — case03's plume traps at ~2.3 m and oscillates
  to the rise/fall cap. Fine here, but a study should assert the termination it expects per cell.

## What this makes the next step

1. **The exe along the feedstock axis** — `reference_cases/pending/dose_parity/`, generated from
   this run: case03 at TA 4000 / 6000 / 10 000 / 20 000 with DIC 2500 entered, so the exe's own
   CO2SYS computes a port pH of 9.2 → 12.0. Every chemistry parity row in the ledger sits at
   TA 4000; the study cannot quote a parity-checked pH above it until this has run.
2. **Ebb's inputs, written down**: geometry, ambient (with a chemistry profile to the seabed),
   intake DIC, and whether the effluent is specified by (TA, DIC) or (TA, pH). Finding 1 says the
   answer changes the study.
3. **8.4 before publishing** — unchanged.
