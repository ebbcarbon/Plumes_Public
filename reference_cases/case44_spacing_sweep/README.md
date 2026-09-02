# case44 — the spacing sweep that replaces case20 (test77–test82)

Run 2026-08-21. Six spacings at **25 ports, 0.0127 m port, 0.005 m³/s total, 35 psu, 65° horizontal,
interval 1** — only the spacing changes. The unmerged denominator is
[case43's test71](../case43_port_count/): one port at the same port diameter and per-port flow.
Spacing is inert on a single port (row 191o), so one control serves all six arms.

## ⛔ Why case20 had to be replaced

case20's test32 was the **only** run that ever favoured the unbraked closure — 1.01 % post-merge
against the confined-decrement reading's 5.24 % — and three things disqualify it as a bar:

- **its 1.01 % sits *below* its own unmerged control's 1.39 %** (row 177). An error smaller than the
  same case run with no merging at all is cancelling errors, not correctness. That is why the
  default moved to `ConfinedDecrements.ALL` despite it;
- **its control was a 2 m spacing, not a single port** — and case43 showed wide-spacing controls
  trip the limiting-spacing rule anyway (rows 261, 268), so that denominator carried merging;
- **it reached only `d/L` 2.35**, one shallow sample carrying the whole argument.

## The exe's suppression rises with spacing — 0.540 to 0.744

| spacing | onset `D` | max `d/L` | exe level | ours (`ALL`, ships) | offset | ours (`NONE`, retired) | offset |
|---|---|---|---|---|---|---|---|
| 0.30 m | 32.7 | 12.08 | **0.572** | 0.695 | **+0.123** | 0.894 | +0.322 |
| 0.45 m | 50.6 | 7.16 | **0.540** | 0.619 | **+0.079** | 0.832 | +0.292 |
| 0.60 m | 70.3 | 4.95 | **0.644** | 0.665 | **+0.021** | 0.859 | +0.215 |
| 0.80 m | 97.5 | 3.45 | **0.744** | 0.664 | **−0.080** | 0.967 | +0.223 |
| 1.10 m | 150.4 | 2.32 | **0.698** | 0.622 | **−0.076** | 0.851 | +0.153 |
| 1.60 m | 278.7 | 1.46 | (below the bins) | 0.578 | — | 0.775 | — |

⭐⭐ **Row 272's question is answered: the sign change is a smooth function of spacing, not noise.**
Row 264b saw −0.071 / +0.049 / +0.145 on three case41 spacings and could not tell a law from three
samples straddling zero. Six samples give a monotone walk from **+0.123** at 0.30 m to **−0.080** at
0.80 m, crossing zero near **0.62 m**. So there is a law to find.

⭐ **And it agrees with case41 where they overlap** — case41's 0.75 m read 0.766 against this
sweep's 0.80 m at 0.744; its 0.25 m read 0.580 against this 0.30 m at 0.572; its 0.50 m read 0.568,
between this 0.45 m (0.540) and 0.60 m (0.644). The "non-monotone" look of case41's three points was
coarse sampling.

⚠️ **The mean offset is only +0.014.** What ships is nearly *unbiased* across the sweep and carries
a spacing-dependent tilt of about ±0.10; the retired default was biased **+0.241** and tilted as
well. That is the residual split of row 272 seen on the other axis.

## Accuracy — the direct case20 replacement

Post-merge dilution MARE at the exe's own printed times, and our max diameter over the exe's:

| spacing | max `d/L` | `ALL` (ships) | `NONE` (retired) | dia `ALL` | dia `NONE` |
|---|---|---|---|---|---|
| 0.30 m | 12.08 | **20.74 %** | 43.40 % | 1.600 | **16.721** |
| 0.45 m | 7.16 | **6.85 %** | 21.81 % | 1.255 | 5.221 |
| 0.60 m | 4.95 | **1.13 %** | 80.27 % | 1.099 | 10.869 |
| 0.80 m | 3.45 | **2.90 %** | 10.18 % | 1.003 | 1.700 |
| 1.10 m | 2.32 | 5.14 % | **1.13 %** | 0.954 | 1.124 |
| 1.60 m | 1.46 | 5.61 % | **4.67 %** | 0.951 | 0.981 |

**What ships wins on four of six, and by an order of magnitude where it wins** — 1.13 % against
80.27 % at 0.60 m, and it holds the element to 1.0–1.6× the exe's diameter where the retired default
reaches **16.7×**. The retired default wins on the two shallowest arms, by 4.0 pp and 0.9 pp.

⭐ **So the trade is exactly as characterised and now sampled six times instead of once**: the
confined reading is right wherever the overlap gets past `d/L` ≈ 3, and the round reading is
slightly better below it. The 1.10 m arm (`d/L` 2.32) is the closest thing to test32 in this sweep
and reproduces its verdict — 1.13 % against 5.14 % — which is the honest version of what case20 was
claiming, measured against a *single-port* control this time.

⚠️ **The 1.60 m arm never reaches `d/L` 1.5**, so it has no bin in the standard window. Read on the
shallower bins it gives 0.722 over `d/L` 1.0–1.2 and 0.594 over 1.2–1.4 — the only arm where the
level *falls* with overlap. Predicted max `d/L` 1.93 against a measured 1.46, so the prediction for
this arm was 32 % out on reach; it is recorded as the sweep's one design miss.

## ⚠️⚠️ And it exposed something unrelated: the width cosine has a threshold

These runs use a **65° bearing into a 90° current** — 25° off — and the archive had only 0° and 30°.
At 25° the exe applies **no** cosine reduction to the wastefield-width span (implied factor 0.990
against `cos 25°` = 0.906), so row 96's law broke by up to 10.73 m here and on case42/case43. That
is **row 275**, it is a far-field finding rather than a merging one, and the run that settles it is a
bearing sweep at 26–29°.
