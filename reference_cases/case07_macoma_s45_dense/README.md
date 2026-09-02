# case07 — 45 psu effluent: strongly dense, and the S=35 cutoff proven in one run

Pulled 2026-08-12 11:55 (`test6_TxtOutputs.dat`). Changed from
[case05](../case05_macoma_merging/): **effluent salinity 35 → 45 psu**, ambient back
to its original 30.9–31.9 profile. Everything else identical (25 ports × 0.60 m,
0.005 cms, interval 5, TA 4000 / DIC 1646, K1K2 = 10, KSO4 = 1).

The intent was a **bottom hit**. It did not happen — see below — but the run turned
out to be the most decisive chemistry case in the set anyway.

## Result 1 — the aragonite S=35 cutoff, proven within a single run

Because the effluent is 45 psu and the ambient ~31, plume salinity starts at 43.7 psu
and falls through 35 as it dilutes. So one run brackets the cutoff from both sides:

| | |
|---|---|
| plume salinity range | **31.239 – 43.679 psu** |
| rows with S > 35 | **12** of 105 |
| rows with `R_arg` > 0 | **12** |
| rows where `(S > 35) == (R_arg > 0)` | **105 / 105** |

The switch is exact and hard:

| step | plume S | `R_arg` |
|---|---|---|
| 60 | 35.302 | **578.082** |
| 65 | 34.903 | **0.000** |

Previously this rested on comparing case05 (all rows below 35, all zero) with case06
(all rows above, all non-zero). Now it is a single-run, self-contained demonstration
with the transition captured mid-trace — much harder to argue with, and the cleanest
possible evidence for the bug report. On the 12 active rows the law
`exp(1.11)·(Ω_arag − 1)^2.26` reproduces to **1.00000**.

## Result 2 — no bottom hit, and why

The plume sinks but only reaches **3.203 m** depth (at step 445) against a seabed at
**17 m** (port depth 2.0 + port elevation 15.0). It falls 13.8 m short.

The reason is dilution: by its deepest point the plume has already diluted **212:1**,
so almost none of the 45 psu excess density survives. With a 0.0127 m port, 25 of them
at 0.60 m spacing, merging at step 310, the plume entrains far too fast to carry its
buoyancy deficit 15 m down.

**To actually get a bottom hit, shorten the water column rather than making the
effluent denser** — see the request at the end of this file.

## Result 3 — merging at `dia = spacing`, third confirmation at 90°

| step | diameter | / spacing (0.60) |
|---|---|---|
| 300 | 0.566 | 0.943 |
| 305 | 0.591 | **0.985** |
| 310 | 0.623 | **1.038** |

Bracketing 1.000 again, as in case05 (0.982–1.012). Two independent runs at 90° now
agree, which makes the upstream example's 0.895–0.938 at 30° a solid measurement of
the oblique-angle correction rather than noise.

## Result 4 — wastefield width, fifth exact confirmation

```
(25 − 1) × 0.60 + 2.907 = 17.307   →  printed 17.31
```

## Trace summary

105 full rows plus a truncated terminating row at step **529** (`252.652, 2.907,
0.000, 5.267, −2.603`), consistent with the case05/case06 truncation rule.

Events: `Local maximum rise or fall` before 220 and 450, `merging happened` before
310, `Plume traps` before 350 and 529. Far-field: 23 rows, 5.267 → 210.305 m,
dilution 252.652 → 1884.685, 4/3-power law.

## What would actually produce a bottom hit

The plume wants to reach ~3.2 m. So put the seabed just above that:

- **Port elevation 15.0 → 1.0 m**, keeping port depth at 2.0 m. That puts the bottom
  at **3.0 m**, which the plume already tries to pass through.
- Keep the 45 psu effluent and everything else from this run.

That also resolves a long-standing oddity in this project: port depth 2.0 m with
elevation 15.0 m implies a 17 m water column, but the ambient profile only goes to
15 m. A 1.0 m elevation makes the geometry self-consistent as well.
