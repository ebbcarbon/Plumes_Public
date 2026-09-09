# case06 — aragonite unlocked, `Ca` ruled out, and a surfacing plume

Pulled 2026-08-12 11:22 from `C:\Users\jerem\Documents\Plumes\Macoma\test5_TxtOutputs.dat`.
Two hypotheses tested, **both resolved**, plus a third regime for free.

| File | Role |
|---|---|
| `test5_TxtOutputs.dat` | **golden trace** — 71 near-field rows + 1 termination row, 52 far-field rows |
| `testeffluent.csv`, `testmixzone.csv`, `testco2.csv` | inputs carried from case05 |

## Settings

Changed from [case05](../case05_merging/): **ambient salinity 30.9–31.9 →
36.0 psu at all six depths**, **ambient `Ca` 10300 → 5000 µmol/kg**. Everything else
identical (25 ports × 0.60 m, 0.005 cms, interval 5, TA 4000 / DIC 1646,
K1K2 = 10, KSO4 = 1, far-field max distance 500 m).

⚠️ No `.prj` or CSVs were re-saved, so the S = 36 profile survives only in the
`.dat` echo (which does show it) and `Ca = 5000` only in your report. `testco2.csv`
here still carries the old `Ca = 100`; treat the README as authoritative.

## Result 1 — the aragonite salinity-band hypothesis is CONFIRMED

`R_arg` is **non-zero in all 71 rows** (3433.906 → down the trace), against
**0/83 in case05**. Plume salinity is now **35.094 – 35.996 psu** — every row above
35, where case05 spanned 31.09–34.63 and never crossed it.

And the law reproduces exactly, identifying which band is used:

| band | K, N | pred / reported |
|---|---|---|
| **`35 < S < 44`: logK = 1.11, N = 2.26** | exp(1.11) = 3.034 | **1.00003** (0.99921 – 1.00078) |
| other: logK = 1.53, N = 2.33 | exp(1.53) = 4.618 | 1.692 (1.544 – 1.892) |

So `R_arg = exp(1.11)·(Ω_arag − 1)^2.26` for `35 < S < 44`, exact to 5 significant
figures — the same `exp()` (not `10^`) convention as calcite, confirmed independently
on a second mineral.

**The bug is therefore established: the aragonite branch has no coverage below
S = 35 and silently returns zero.** The second GUI entry (logK = 1.53, N = 2.33) is
never applied in any of our six runs — presumably it is meant for S < 35 and the
band selection is broken or missing. This matters practically: aragonite
precipitation reads as exactly zero for every brackish and normal-seawater discharge,
which is most real outfalls, with no warning. Worth reporting to SSMC.

Calcite continues to check out at the new salinity: pred/reported mean **0.99998**.

## Result 2 — the `Ca` column is inert

With `Ca = 5000` µmol/kg against ~10 500 for seawater at S = 36, a used value would
halve Ω — ratio ≈ 0.476. Observed:

```
exe Omega_arag / PyCO2SYS Omega_arag (salinity-derived Ca) = 0.9652
```

i.e. unchanged, and consistent with the usual ~3 % exe/PyCO2SYS offset. **`Ca` is
ignored for Ω.** And since both rate laws reproduce exactly from Ω alone, it does not
feed the precipitation rates either — the column is entirely inert.

This test worked because the value was deliberately wrong; the `Ca = 10300` I asked
for in case05 was ~seawater and could not discriminate.

## Result 3 — a positively buoyant, surfacing plume (free third regime)

Effluent at 35 psu into 36 psu ambient makes the plume **positively buoyant** for the
first time at this geometry. It rises from 2.0 m to 0.687 m and **surfaces**:

| banner | next row | depth | diameter |
|---|---|---|---|
| `Plume traps` | 195 | −1.291 | 0.491 |
| `merging happened` | 210 | −1.154 | 0.627 |
| **`Plume surfaces`** | 260 | −0.712 | 1.474 |
| `Local maximum rise or fall` | 280 | −0.689 | 1.618 |
| `Plume traps` | 320 | −1.112 | 2.202 |
| `Local maximum rise or fall` | (356, end) | −1.352 | 2.997 |

Two firsts: **trapping fires *before* merging** (case05 had it after), and
**surfacing does not terminate the run** — it continues 96 more steps. The upstream
example terminated at surfacing, but it has max rise/fall = 2 where this has 3, so
the switch evidently governs whether surfacing is terminal.

### Surfacing criterion — partly pinned

Testing `depth ≤ radius` (plume edge reaching the surface):

| case | bracketing rows: depth − radius | depth / radius |
|---|---|---|
| **case06** | +0.024 (step 255) → −0.025 (step 260) | **1.035 → 0.966** |
| upstream example | −0.508 (step 270) → −0.728 (step 275) | 0.837 → 0.775 |

case06 brackets `depth = radius` almost exactly. But the example crosses that
threshold between steps 260 and 265 and does not emit the banner until after 270 —
two output intervals late. So either the criterion differs for that case (both plumes
are merged by then, so it is not simply merged-vs-round), or the banner is emitted
with a lag there. Unresolved; flagged for Phase 5.

## Result 4 — wastefield width, fourth exact confirmation

```
(25 − 1) × 0.60 + 2.997 = 17.397   →  printed 17.40
```

## Result 5 — far-field

52 rows, 7.021 → **504.719 m** against a 500 m max distance, dilution 222.949 →
5084.333. Note the final dilution **exceeds 5000**, so this run terminated on
distance rather than the default max dilution.

Far-field overshoot past the max-distance limit, now three data points and still not
a constant: **1.611 m** (case02, 100 m interval), **7.189 m** (case05, 10 m),
**4.719 m** (case06, 10 m). Same limit and interval in the last two, different
overshoot — so it depends on the plume state at handoff, not just the grid.

## Termination row

Consistent with case05: step **356** is off-interval and truncated to 6 fields
(`222.949, 2.997, 0.000, 7.021, −1.352`), with no chemistry columns.

## Names (2026-09-09)

This folder was `case06_macoma_arag_s36` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.
