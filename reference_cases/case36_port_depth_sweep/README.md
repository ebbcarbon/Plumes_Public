# case36 — the port-depth sweep, and the lag resolves into three regimes

Run 2026-08-19 to test the one lever case35 left standing: port depth. It does not stand either
— but with these six runs the archive finally has enough single-port banners to see that the
"lag" is not one number with a hidden argument. It is **three distinct behaviours**.

`limspc_mid`'s geometry throughout: **one port at 0.20 m**, 0.005 m³/s, downward at −45°, output
interval 1, into the case03 ambient.

| run | port depth | effluent | first trap | `d >` depth | first local max | banner | lag past `max(trap, cross)` | fires |
|---|---|---|---|---|---|---|---|---|
| `dep1.5_s35` | 1.5 m | 35 psu | 183 | 155 | 322 | **183** | **0** | on the trap |
| `dep2.0_s35` | 2.0 m | 35 psu | 176 | 176 | 324 | **176** | **0** | on both at once |
| `dep2.4_s35` | 2.4 m | 35 psu | 171 | 191 | 322 | **192** | **1** | on the crossing |
| `dep2.0_s30` | 2.0 m | **30 psu** | 238 | 268 | 137 | **274** | **6** | mid-trajectory |
| `dep2.0_s45` | 2.0 m | **45 psu** | 199 | 201 | 381 | **225** | **24** | mid-trajectory |
| `dep3.0_s35` | **3.0 m** | 35 psu | 164 | 250 | 316 | **316** | **66** | **on the local max** |

⭐ `dep2.4_s35` is byte-identical to case33's `sal35`, which is the fourth independent repeat of
that configuration in the archive and the third to come back bit for bit.

## ⚠️ Port depth alone does not do it either

case35's `d0.50_q5.0` at a **2.4 m** depth lags 142. `dep2.4_s35` sits at the same depth and lags
**1**. The difference is port diameter, 0.5 m against 0.2 m — so the depth story fails exactly the
way the Froude story did the day before, and for the same reason: one lever was being read while
another moved with it.

## ⭐⭐ Three regimes, and every archived single-port banner falls into one

| regime | lag | runs |
|---|---|---|
| **A — on `max(trap, crossing)`** | 0 to 1 | `limspc_shallow`, `limspc_gap`/`gap_2`/`dep2.0_s35`, `dep1.5_s35`, `gap_1`/`dep2.4_s35`/`sal35`/`d0.20_q5.0` |
| **B — mid-trajectory, nothing marks it** | 6 to 24 | `dep2.0_s30`, `sal45`, `gap_4`, `gap_3`, `dep2.0_s45` |
| **C — exactly on the first local maximum** | 66 to 143 | `dep3.0_s35`, and all six of case35's wide-port runs |

The parameter map, as far as the archive constrains it:

- at **0.20 m** and 35 psu, depths 1.0 / 1.5 / 2.0 / 2.4 are all **A**; depth **3.0** is **C**
- at **0.20 m** and depth 2.0, 35 psu is **A** while **30** and **45** psu are both **B**
- at depth **2.0**, 0.2 m is **A** and 0.5 m is **B**
- at depth **2.4**, 0.2 m is **A** and 0.3–0.6 m are all **C**

So increasing the depth, widening the port, or moving the effluent salinity away from the ambient
all push a run out of A — and no single one of them decides the regime.

⭐ Regime C is internally very tight, which is what identifies it as a trajectory property rather
than a rule: across the seven C runs the diameter at the banner sits at **0.450–0.462 × the depth
below the surface**, and at **0.673–0.680 × the distance fallen**, while the lag ranges 66 to 143.
The banner is simply wherever the plume stops, and the merge check is not choosing that step.

## ⚠️ `dep2.0_s30` is worth its own line

At 30 psu the effluent is *lighter* than the ~31.4 psu ambient, so this plume **rises**: its local
maximum comes at step 137, long **before** the trap at 238 and the crossing at 268, and the banner
lands at 274. It is the only run in the archive where the first local maximum precedes the
crossing, and it fires 6 steps after — regime B, not C. So "fires on the local max" is not "fires
on the first turning point available"; C runs wait for a turning point that is still ahead of them.

## What would settle it

Nothing in the parameter map isolates the regime boundary, and three levers each move it. The
cheapest discriminator left is a **depth sweep at a wide port** — 0.5 m at depths 1.5, 2.0, 2.4,
3.0 — which crosses the B/C boundary along one axis with the other two fixed. `gap_4` (2.0 m,
regime B) and `d0.50_q5.0` (2.4 m, regime C) are already its endpoints, so it is two runs.
