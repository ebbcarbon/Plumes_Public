# case21 — the merging-spacing prediction test (test34, test35)

**Old build**, output interval 1, all output columns, 25 ports. Generated 2026-08-13 to test a
**prediction made before the runs existed**, not to fit anything.

Base is test19 (`case16`): 25 ports, 0.0127 m diameter, 0.005 m³/s, 45° vertical /
**175° horizontal** into a **90°** current at 0.02 m/s — an **85° offset** — 2 m port depth,
15 m elevation, effluent 35 psu / 10 °C, contraction 0.61, aspiration 0.1, rise/fall 3.
**Only the port spacing changes.**

| run | spacing | merge banner precedes | rows |
|---|---|---|---|
| test19 | 2.0 m | step 297 | 494 |
| **test35** | **1.5 m** | step 268 | 507 |
| **test34** | **1.0 m** | step 235 | 526 |

⚠️ **No matching `.prj` was captured.** The project file in the run directory had been reset to
the 2 m / 90° base by the time it was copied, so it describes neither run. The `.dat` diffuser
echo does record every field that changed, and the rest is test19's geometry — but mind the
**two-decimal echo trap**: `P-dia` of `0.01` is 0.0127 and `Ttl-flo` of `0.01` in (cms) is
0.005. Reconstruct from test19's project, changing spacing only.

## What it was testing

Ledger row 118 carried a fitted ellipse, `√(cos²θ + 0.596² sin²θ)`, invented because a static
`cos(azimuth − current)` sits *below* every measured merge trigger. Its constant was tuned to
the 85° bracket.

The replacement is not fitted: the effective spacing resolves against the plume's
**instantaneous horizontal heading**, and merging fires *mid-turn*, while the plume still
presents most of its aspect to its neighbours. That makes the trigger depend on the **spacing**
— a wider spacing means merging fires later, by which time the plume has turned further and
the effective spacing has shrunk. A static law cannot express that at all.

So at one fixed offset the ellipse must predict **one** number, and the derived law predicts a
**curve**. Hence these two runs.

## Result: the curve is reproduced, the constant is dead

| run | spacing | exe bracket | derived law | ellipse |
|---|---|---|---|---|
| test19 | 2.0 m | 0.5985–0.6015 | **0.5991** ✅ | 0.600 ✅ |
| test35 | 1.5 m | 0.6760–0.6800 | **0.6751** ⚠️ | 0.600 ❌ |
| test34 | 1.0 m | 0.7700–0.7780 | **0.7750** ✅ | 0.600 ❌ |

The ellipse is flat at 0.600 by construction and is excluded by **13 %** at 1.5 m and **23 %**
at 1.0 m — far outside brackets that output interval 1 pins to ~0.5 %.

The derived law reproduces the trend across a 2× spacing range with **no free parameter**.
⚠️ Be precise about test35: 0.6751 lands **0.0009 below** the bracket's lower edge, a 0.13 %
miss rather than a hit. That is inside our own trajectory error on these runs (dilution MARE
1.0–1.2 %), so it is a near-miss rather than a contradiction — but it is a near-miss, and the
row should not be written up as three clean hits.

## Whole-run accuracy

Dilution MARE against the full traces: 0.98 % (test19), 1.22 % (test35), 1.13 % (test34).
test34 splits 0.38 % pre-merge and 2.32 % post-merge. All three terminate on a surface hit in
our model before the exe's trace ends, so the later rows are not compared.
