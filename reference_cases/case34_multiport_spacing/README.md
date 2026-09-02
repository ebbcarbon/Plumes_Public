# case34 — the multiport merge trigger fires on the crossing, with no lag at all

Run 2026-08-19 from the `subcritical_sinks` project. **25 ports** at 0.005 m³/s total, **45 psu**
effluent into the ~31 psu Macoma ambient at a 2.0 m port depth, so the plume is dense and sinks.
Port spacing and port diameter are swept independently.

⚠️ These are not the sub-critical *sinking* run the project was written for — that asked for one
run at the case29 geometry. They are a spacing sweep on the same base, and they answer a bigger
question than the one they were pointed at.

| run | spacing `L` | port dia | `merging happened` | first step with `d ≥ L` | **lag** | `d/L` at the banner |
|---|---|---|---|---|---|---|
| `L2.0_d0.50` | 2.00 m | 0.50 m | 309 | 309 | **0** | 1.0070 |
| `L1.0_d0.50` | 1.00 m | 0.50 m | 250 | 250 | **0** | 1.0110 |
| `L0.5_d0.50` | 0.50 m | 0.50 m | 195 | 195 | **0** | 1.0020 |
| `L0.5_d0.25` | 0.50 m | 0.25 m | 215 | 215 | **0** | 1.0040 |
| `L0.3_d0.50` | 0.30 m | **0.50 m** | 2 | — | — | ⚠️ ports overlap **on the pipe** |
| `L0.5_d0.75` | 0.50 m | **0.75 m** | 2 | — | — | ⚠️ ports overlap **on the pipe** |

⚠️ **Those last two are geometrically impossible and the exe runs them anyway.** 0.5 m ports at
0.3 m spacing, and 0.75 m at 0.5 m, put more port than pipe — so the plumes overlap before they
leave the nozzle, the trigger fires at step 1, and the banner lands at step 2. The printed
diameter then *contracts* sharply, 0.418 → 0.069 m, as the dense jet accelerates downward. They
are kept because the profile law holds on them and because an input the exe should refuse and
does not is worth having on record.

## ⭐⭐⭐ Four spacings, zero lag, `d/L` inside 1.002–1.011

`merging happened` lands on **exactly** the step where the printed diameter first reaches the
spacing, in every run where the crossing happens inside the trajectory. A 4× range in spacing and
a 2× range in port diameter move it not at all.

That is worth stating plainly because of what it means for row 191b. The two runs that fire at
step 2 do so because the plumes already overlap at step 1 — the trigger has nothing to wait for.

## ⭐⭐⭐ So the lag belongs to the *limiting-spacing* rule, not to merging

Row 191b recorded a merging banner lagging its own trigger by 0, 1, 16, 23 and 54 steps and could
not say what set the lag. Those five runs were all **single-port**, where a `merging happened`
banner can only come from UM3's limiting-spacing rule — the one that declares a lone plume merged
once its diameter passes the port depth. This case is the multiport comparison that was missing.

| | trigger | lag |
|---|---|---|
| **multiport merging**, `d ≥ effective spacing` | 4 runs here, plus case20's test32 | **0, always** |
| **single-port limiting spacing**, `d > port depth` | case22/23/30/33 | 0 to 23 |

⚠️ **They are different code paths, and the archive had been reading them as one rule.** Nothing
before this case varied the multiport spacing with the crossing inside the trajectory, so the
zero-lag half was never measured.

⭐ And the Froude number rules out "one rule, lagging when the plume is slow". Within the
single-port runs the lag *is* monotone in it:

| run | ports | `F` | lag past `max(trap, crossing)` |
|---|---|---|---|
| case30 `gap_2` | 1 | 2.170 | 0 |
| case22 `limspc_shallow` | 1 | 2.170 | 0 |
| case30 `gap_1` | 1 | 2.170 | 1 |
| case33 `sal45` | 1 | 1.115 | **15** |
| case30 `gap_4` | 1 | 0.220 | **16** |
| case30 `gap_3` | 1 | 0.113 | **23** |
| **this case**, all four | **25** | **0.0045** | **0** |

A single-port run at `F` = 0.113 lags 23 steps; a multiport run at `F` = 0.0045 — twenty-five
times more sub-critical — does not lag at all. One `F`-dependent rule cannot produce both.

## What is still open

The single-port lag itself. It is now bounded to one rule and correlates with `F` over six runs,
which is a far narrower target than "the merging banner lags", but six points and a monotone
trend are not a mechanism. The obvious next probe is a single-port run at `F` ≈ 0.5, between
`sal45`'s 1.115 and `gap_4`'s 0.220, where the lag would have to be 15–16 for the trend to be
smooth.
