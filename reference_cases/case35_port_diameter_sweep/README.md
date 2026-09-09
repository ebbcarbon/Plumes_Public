# case35 — the port-diameter sweep, and the Froude explanation dies

Run 2026-08-19 to test whether the single-port limiting-spacing lag is smooth in the densimetric
Froude number, as case33 and case30 together suggested. **It is not, and `F` is not the variable.**

`limspc_mid`'s geometry throughout: **one port**, discharged downward at −45° from a **2.4 m**
port depth, 35 psu effluent into the case03 ambient, output interval 1. Only the port diameter
and the total flow change.

| run | port dia | flow | first trap | `d >` port depth | first local max | `merging happened` | **lag** |
|---|---|---|---|---|---|---|---|
| `d0.20_q5.0` | 0.20 m | 5e-3 | 171 | 191 | 322 | **192** | **1** |
| `d0.30_q5.0` | 0.30 m | 5e-3 | 179 | 202 | 340 | **340** | 138 |
| `d0.40_q5.0` | 0.40 m | 5e-3 | 197 | 221 | 362 | **362** | 141 |
| `d0.50_q5.0` | 0.50 m | 5e-3 | 203 | 227 | 369 | **369** | 142 |
| `d0.60_q5.0` | 0.60 m | 5e-3 | 200 | 224 | 367 | **367** | 143 |
| `d0.40_q4.0` | 0.40 m | 4e-3 | 207 | 233 | 368 | **368** | 135 |
| `d0.40_q3.0` | 0.40 m | 3e-3 | 220 | 247 | 372 | **372** | 125 |

⚠️ The flow is **not** readable from the echo: `Ttl-flo` prints 0.010 for 5e-3 and **0.000** for
both 4e-3 and 3e-3. Row 141's two-decimal rounding, at its most destructive. The values above come
from the run log, not the file.

## ⭐⭐⭐ The controlled pair that kills the Froude story

case30's `gap_4` and this case's `d0.50_q5.0` differ in **exactly one echoed field**:

| field | `gap_4` | `d0.50_q5.0` |
|---|---|---|
| port diameter | 0.500 | 0.500 |
| vertical / horizontal angle | −45 / 90 | −45 / 90 |
| ports / spacing | 1 / 0 | 1 / 0 |
| total flow, effluent salinity, temperature | 0.010 / 35 / 10 | 0.010 / 35 / 10 |
| **port depth** | **2.000** | **2.400** |

Same exit velocity, same buoyancy, so the same densimetric Froude number: **F = 0.2196**. The
lags are **16** and **142**.

⚠️ **So yesterday's "the lag is monotone in `F`" was a coincidence of a six-point sample**, and it
is recorded here as such rather than quietly dropped. The four points that suggested it — F 2.17,
1.115, 0.220, 0.113 giving lags 0–1, 15, 16, 23 — all happened to vary port depth and salinity
together with the diameter. Holding everything but the depth fixed separates them, and `F` loses.

## ⭐⭐ What the new runs do instead: fire on the local maximum

Six of the seven land the banner on **exactly** the `Local maximum rise or fall` step — 340, 362,
369, 367, 368, 372 — not on the crossing. The lag is then not a property of the merge check at
all: it is the distance from the crossing to wherever the trajectory happens to turn.

That also explains the sweep's flatness. Across a **9× range in port area** (0.2→0.6 m) the lag
sits at 138, 141, 142, 143; across a flow drop of 5→4→3 e-3 it moves 141→135→125. Those are
trajectory shifts, not rule shifts.

⚠️ **But `d0.20_q5.0` does not do this**, and neither do case30's `gap_1`, `gap_3` or `gap_4`.
They fire mid-trajectory — 192, 192, 248, 227 — with no printed event anywhere near, and no
unflagged depth turning point either (checked: the nearest is 95 steps away).

## Where this leaves row 191b

Two behaviours, and no rule that covers both:

| | fires | runs |
|---|---|---|
| **on the crossing**, +0 to +1 | at `d >` port depth | `gap_2`, `limspc_shallow`, `gap_1`, `d0.20_q5.0` |
| **mid-trajectory**, +15 to +23 | nothing marks it | `gap_3`, `gap_4`, `sal45` |
| **on the first local maximum** | +125 to +143 | the six wide-port runs here |

Checked and rejected across the set: the densimetric Froude number (this case), depth below the
surface, height above the seabed, distance fallen, path length, elapsed time, dilution, the
diameter excess `d − d₀`, `d >` port depth + port diameter, `d > 2 ×` port depth, and the
diameter-to-port-depth ratio at the banner (1.013, 1.333–1.473 — not constant).

⭐ The one thing that has separated cleanly is **port depth**: every short-lag run sits at 1.0 or
2.0 m and every long-lag run at 2.4 m. With only two depths carrying most of the contrast that is
a lead rather than a result, and the run that would test it is this same sweep at **port depth
2.0 m** — where the Froude story predicts nothing and the depth story predicts the lag collapses
back to ~16.
