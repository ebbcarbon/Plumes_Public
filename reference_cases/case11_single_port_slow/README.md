# case11 — a single port that works, correcting case09

Pulled 2026-08-12 12:06 (`test12_TxtOutputs.dat`). **`Ports = 1`** with the flow
reduced **100×** (0.005 → 5×10⁻⁵ cms), port elevation back to 15.0 m, 45 psu effluent.

100 clean rows to step **500**, a 9-row far-field, **no NaN anywhere**.

## This corrects case09

[case09](../case09_single_port/README.md) concluded that a single-port run was
"apparently impossible to validate" because `Ports = 1` produced 955 rows of NaN. That
was the wrong diagnosis. **The port count was never the problem — the exit velocity
was.**

| run | ports | flow | exit velocity | outcome |
|---|---|---|---|---|
| case09 `test9` | 1 | 0.005 cms | **39.5 m/s** | surfaced, rose above the free surface, NaN |
| case09 `test10` | 1 | 0.005 cms | 39.5 m/s | identical failure at elevation 1.0 m, 45 psu |
| **case11** | **1** | **5e-5 cms** | **0.39 m/s** | **clean, submerged throughout** |

Putting the whole flow through one 0.0127 m port gives a 39.5 m/s jet — 25× the
per-port velocity of the 25-port cases. That momentum drove the plume clean through
the free surface (centreline depth reached −0.041 m), and everything after that was
downstream of an unphysical state.

So the exe's real defects here are the **missing surface clamp** and the
**`(Ω − 1)^N` NaN for Ω < 1**, both of which case09 documents. Single ports themselves
are fine, and this case is a usable validation target for single-plume entrainment
with no merging term at all.

Depth stays between 1.901 m and 3.024 m; Ω_calc never drops below 7.171, so the rate
law is never evaluated on undersaturated water.

## Result — the wastefield width formula degenerates correctly

With one port the `(n − 1) × spacing` term vanishes, leaving just the diameter:

```
(1 − 1) × 0.60 + 1.451 = 1.451   →  printed 1.45
```

Seventh exact confirmation, and the first that exercises the degenerate case. Worth
having: an implementation that wrote `n × spacing` instead of `(n − 1) × spacing` would
have matched none of the multiport cases, but one that special-cased single ports
wrongly would only fail here.

## Result — the terminating row is complete

Step **500** is a multiple of the output interval 5 and its row carries all 12
columns, matching [case10](../case10_bottom_hit/) and confirming that
truncation happens only when the terminating step falls off the interval.

## Carried-over confirmations

- Aragonite S = 35 cutoff: `(S > 35) == (R_arg > 0)` on **100/100** rows, plume
  salinity spanning 31.203 – 43.679 psu.
- Events: `Local maximum rise or fall` before 155 and 460, `Plume traps` before 390
  and 500. A damped oscillation about the trapping level, then termination.
- Far-field: 9 rows, 3.374 → 72.078 m.

## One reader caveat

`DatFile.merged` reports `True` here, because it is defined as "no *plumes not merged*
advisory was printed" and the exe prints none for a single port. Semantically there is
nothing to merge. The property is about the advisory, not about physics; anything
depending on merging should check the port count.

## Names (2026-09-09)

This folder was `case11_macoma_single_port_slow` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.
