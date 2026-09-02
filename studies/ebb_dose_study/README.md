# Phase 9 — the fixed-DIC dose study at Ebb's default profile (2026-08-26; rerun 2026-09-01)

**The study the port was built for, run at the geometry it was built for.** Ebb's default profile is
the Macoma configuration (operator, 2026-08-26): case03's diffuser, effluent, ambient and constants —
with **one correction (2026-09-01): the port spacing is 2 ft, 0.6096 m**. The archived case03
project carries 2 m ("2.0" entered with the wrong unit; the Dec-2025 original stored 2.0 under the
`.prj` feet flag, echoing 0.61 m — ledger row 49). The archive stays as entered; the study
overrides the one field. ⚠️ At 0.61 m the higher-flow sweep cells can **merge** (case05 merged at
0.60 m at 23× this flow), which is a regime the 2 m geometry never entered. Two inputs are added,
and both are the study's rather than the archive's:

1. **Ambient chemistry to the seabed.** case03's table stops at 4 m; here the deepest measured row
   (TA 2850, DIC 2450 µmol/kg) is **held constant** to the 17 m seabed. An assumption, stated in the
   case's own `description`; replace the held rows in [`ebb_macoma_default.yaml`](ebb_macoma_default.yaml)
   when Ebb has a measured profile.
2. **The effluent is TA at the intake's DIC** (2500 µmol/kg) — Ebb's specification, and the axis a
   feedstock actually moves along (PLAN_HISTORY §8f finding 1).

Produced by [`../ebb_dose_study.py`](../ebb_dose_study.py) (32 cells, ~3.5 min). Every Ω_brucite is
the **upper bound** PLAN_HISTORY §8b describes; Ω = 1 is thermodynamic, not a rate. The centreline is read
through the **parabola** — the profile decision in PLAN §2, the exe's default — with the literature Gaussian as the
stated sensitivity (+16 % on any centreline extent).

## Headline: the dose ceiling below which brucite never supersaturates, and the window above it

| effluent TA (µmol/kg, DIC 2500) | port pH (total) | Ω_brucite at the port | Ω = 1 extent, flux-averaged: dilution / time / distance | **centreline (parabola)**: dilution / time / distance | centreline, Gaussian: distance |
|---|---|---|---|---|---|
| 3000 (no dose) | 8.454 | 0.014 | never | never | — |
| 4000 | 9.168 | 0.38 | **never** | **never** | — |
| 5000 | 9.837 | 8.3 | 1.46 / 0.17 s / 0.7 cm | 2.9 / 0.9 s / **3.2 cm** | 4.3 cm |
| 6000 | 10.671 | 385 | 2.16 / 0.47 s / 1.8 cm | 4.3 / 2.5 s / **7.7 cm** | 9.0 cm |
| 8000 | 11.259 | 5 800 | 3.56 / 1.6 s / 5.1 cm | 7.1 / 4.0 s / **11.6 cm** | 12.6 cm |
| 10 000 | 11.505 | 17 900 | 4.95 / 3.0 s / 8.9 cm | 9.9 / 5.1 s / **14.0 cm** | 15.2 cm |
| 15 000 | 11.824 | 78 000 | 8.45 / 4.6 s / 12.8 cm | 16.9 / 7.2 s / **18.6 cm** | 20.1 cm |
| 20 000 | 12.006 | 181 000 | 11.9 / 5.7 s / 15.5 cm | 23.9 / 8.9 s / **22.4 cm** | 24.2 cm |

⭐ **Below TA ≈ 4340 µmol/kg the discharge is never brucite-supersaturated, even undiluted.** With
DIC held at the intake's 2500, the port pH is a function of TA alone and crosses pH* = 9.43 (total,
S 32 / 10 °C — PLAN_HISTORY §8f) at TA* ≈ 4340; TA 4000 gives pH 9.17 and Ω 0.38. That is the analytic
result of PLAN_HISTORY §8f seen at Ebb's own profile, and it is a **dose ceiling** rather than a distance.

⭐ **Above it the window is centimetres and seconds.** Even at TA 20 000 — port pH 12.0, Ω 1.8 × 10⁵
— the centreline falls back through Ω = 1 at 22 cm from the port, within 9 s, at a flux-averaged
dilution of 24. On the fixed-DIC axis the dilution extent is linear in dose,
`D* = (TA_eff − TA_amb) / (TA* − TA_amb)` (PLAN_HISTORY §8f), and the parabola doubles it for the axis. The
Gaussian sensitivity adds 1–2 cm.

**Nothing reaches the regulatory boundaries.** Both are far-field numbers here (acute 20.7 m at a
dilution of 633, chronic 207 m at 4319; the near field ends 2.84 m from the port at 534 — the
2 ft wastefield is 14.6 m wide where the mis-entered 2 m gave 48 m, so the boundary dilutions
grew). Across the whole dose axis the acute-boundary pH rises **8.383 → 8.416** and the chronic
**8.383 → 8.388** (the ambient at the trapping depth is 8.38); Ω_aragonite at the acute boundary
4.65 → 4.96; Ω_brucite at both ≈ 0.009 at every dose.

## Port depth: the window does not care

Seabed held at 17 m (the riser shortens as the port sinks):

| TA | port 2 m | port 5 m | port 11 m |
|---|---|---|---|
| 6000 — centreline Ω = 1 distance | 7.7 cm | 7.7 cm | 6.8 cm |
| 10 000 | 14.0 cm | 14.4 cm | 15.5 cm |
| 20 000 | 22.4 cm | 23.0 cm | 25.0 cm |
| near-field end: distance / dilution | 2.84 m / 534 | 5.03 m / 1027 | 5.56 m / 1030 |
| chronic pH at TA 20 000 | 8.388 | 8.405 | 8.404 |

The supersaturated window sits in the jet's first diameters, before the ambient stratification has
had any say, so it is set by the dose and the port diameter and not by where the port is. What the
depth does change is how much water column the plume has to entrain before it traps: a 5 m or 11 m
port ends its near field at twice the dilution of the 2 m one.

## Flow: a faster jet crosses sooner in the jet — and later if it has already turned

| TA | Q = 0.22 L/s (case03) | Q = 1.0 L/s | Q = 5.0 L/s |
|---|---|---|---|
| 6000 — centreline Ω = 1: time / distance | 2.5 s / 7.7 cm | 0.78 s / 7.6 cm | 0.22 s / 8.6 cm |
| 10 000 | 5.1 s / 14.0 cm | 3.2 s / 19.6 cm | 0.93 s / 20.7 cm |
| 20 000 | 8.9 s / 22.4 cm | **14.3 s** / 56 cm | 4.9 s / 54 cm |
| acute pH at TA 20 000 | 8.416 | 8.443 | 8.495 |
| chronic pH at TA 20 000 | 8.388 | 8.392 | 8.420 |
| Ω_aragonite, acute, TA 20 000 | 4.96 | 5.24 | 5.84 |
| near-field end dilution / end `d/L` | 534 / 0.89 (unmerged) | 287 / 1.59 (merged, shallow) | 190 / **3.85** ⚠️ |

⚠️ **The 14.3 s at 1 L/s is not a mistake.** At that flow the 45° jet reverses at 7.3 s (the first
turning point), before the centreline has diluted to 24; from there dilution grows slowly and the
crossing lands at 14 s and 56 cm. At 5 L/s the jet is still rising at 26 s and the crossing is
inside it (4.9 s). At 0.22 L/s the reversal is at 1.6 s but the jet is so slow (0.07 m/s) that the
distance stays 22 cm. Where the crossing lands relative to the first turning point is worth
reporting alongside the extent, and the script prints the turning points on request.

**More flow moves the boundaries more than more dose does**: 5 L/s at TA 20 000 lifts the acute
pH by 0.112 over ambient against 0.032 at case03's flow, because the near field ends at a lower
dilution (190 against 534) — the mass of alkalinity delivered per second is what the boundary sees.

⚠️ **At 2 ft spacing the fatter plumes merge, and the 5 L/s column carries the port's known
residual.** The default flow never merges (end `d/L` 0.89 — spacing is inert below the trigger,
so its near field is identical to the pre-correction run). 1 L/s merges in shallow overlap
(`d/L` 1.59, the ~1 % regime), but 5 L/s ends at **`d/L` 3.85**, inside the 1–7 % post-merge band
(PORTING_THE_PHYSICS §1) — treat that column's *end dilutions and boundary rows* as ±7 %, not
±0.5 %. Every Ω = 1 crossing sits centimetres from the port, long before any plumes touch, and is
unaffected in all 32 cells.

## What every cell reported

- Termination: `oscillation limit` on all 32 cells (the plume traps and oscillates to the 3-count).
- Warnings: `GeometryWarning` on every cell — case03's seabed (17 m) sits below its hydrographic
  profile (15 m). **Intentional, not a typo** (operator, 2026-09-01): no measurement exists at
  17 m, and the profiles are notional because the depth changes with the tides. **No `ConstantRangeWarning` and no
  `PHRangeWarning`**: S stays 31–35 inside Lueker's window and the top port pH, 12.006, sits inside
  the 12.05 parity ceiling case47 earned. Every pH on this axis is therefore parity-checked to
  0.025 (case47) — Phase 9's exit criterion for pH.
- ⚠️ **One defect found and fixed by this run.** Every 5 m cell failed on
  `dilution must be at least 1`: the dense output's mass ratio at t = 0 came back as
  0.9999999999999999, one ULP under the 1.0 that `chem.transport.mix` requires, and every other
  depth happened to land on exactly 1.0. `NearFieldSolution.sample` now floors the dilution at 1;
  pinned in `tests/test_ebb_default_case.py`. The ledger did not move.

## What this does and does not say

- It says: at Ebb's default profile, a dose up to ~TA 4300 at the intake DIC never supersaturates
  brucite; above that, the thermodynamic window is the first ~0.25 m and ~10 s of the jet, and
  nothing reaches a mixing-zone boundary. Both statements are on an **upper bound** for Ω.
- It does not say how much brucite would form — there is no rate law — nor what a real ambient
  chemistry profile below 4 m looks like. The held rows are the assumption to replace first.
- Files: `dose_axis.csv`, `dose_x_depth.csv`, `dose_x_flow.csv` (every `brucite_extract` column
  plus `centreline_{parabolic,gaussian}_{dilution,time_s,distance_m,region}`), `figure_dose_axis`
  and `figure_second_axes` (SVG and PNG), `ebb_macoma_default.yaml`, `run.log`.
