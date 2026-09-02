# case28 — the close-out: eq 30's ambient, and IDOD at scale

Generated as the experiment `farfield_do_closeout` (note: [`EXPERIMENT_NOTE_farfield_do_closeout.md`](EXPERIMENT_NOTE_farfield_do_closeout.md); the one-off scoring script is [`analyse_do_closeout.py`](analyse_do_closeout.py)) and run 2026-08-18. The experiment asked
for three runs; twelve came back, as a **3 × 2 factorial of ambient profile against IDOD, repeated at
two carbonaceous rates**. That redundancy is what makes the result as strong as it is — the headline
measurement repeats three times over inputs that were *not* held fixed.

## ⚠️ The DO tab, recorded by hand

| field | runs 1–7 | runs 8–10 | run 11 | run 12 |
|---|---|---|---|---|
| effluent DO | 2.0 mg/L | 2.0 | 2.0 | **20 mg/L** |
| IDOD | **0** (runs 1–4), **100 mg/L** (runs 5–7) | 0 | **100** | **100** |
| cBOD5 | 20 mg/L | 20 | 20 | 20 |
| cBOD decay | **20 /day** | **0.23 /day** | 0.23 | 0.23 |
| nBOD5 | 30 mg/L | 30 | 30 | 30 |
| nBOD decay | 0.1 /day | 0.1 | 0.1 | 0.1 |

⚠️ **The rate of 20 /day was not what the experiment note asked for** — it asked for 0.23, and the
tab had retained 20 from case27 run 10. This is the third time the retained tab has changed what a
run means. It cost nothing here, for a reason worth keeping: **the headline measurement is a
difference between two runs, and the demand cancels in it exactly.** An experiment designed as a
difference survived an input error that would have wrecked an absolute one.

| run | ambient | IDOD | cBOD decay | geometry | far-field DO at 500 m |
|---|---|---|---|---|---|
| 1 | uniform | 0 | 20 | ⚠️ **275 steps, `D_near` 169.754** — the project as loaded | −0.369 |
| 2 | falling | 0 | 20 | 572 steps, 246.607 | −0.414 |
| 3 | rising | 0 | 20 | 572 steps | −2.179 |
| 4 | uniform | 0 | 20 | 572 steps | −0.565 |
| 5 | falling | **100** | 20 | 572 steps | −45.853 |
| 6 | rising | **100** | 20 | 572 steps | −47.618 |
| 7 | uniform | **100** | 20 | 572 steps | −46.004 |
| 8 | falling | 0 | **0.23** | 572 steps | 7.409 |
| 9 | rising | 0 | **0.23** | 572 steps | 5.644 |
| 10 | uniform | 0 | **0.23** | 572 steps | 7.258 |
| 11 | uniform | **100** | **0.23** | 572 steps | −38.181 |
| 12 | uniform | **100** | **0.23** | 572 steps, **`DO_e` = 20** | −38.148 |

⚠️ **Run 1 is on a different trajectory** — the project's saved settings, not the note's — so its DO
is not comparable with runs 2–10. Kept as the archive's record of what "as loaded" produces.

## ⭐⭐ Settled: eq 30's `DO_a` is the ambient at the **trapping depth**

`AmbientDO_falling.csv` and `AmbientDO_rising.csv` are mirror images, built so their **depth-means
are identical (7.167)** while their values at the trapping depth differ (8.264 against 6.354). So
the difference between a falling run and a rising run isolates `DO_a` and nothing else: the BOD
demand is the same in both and cancels exactly, as does IDOD.

| pair | conditions | falling − rising at 500 m |
|---|---|---|
| 2 − 3 | cBOD 20 /day, IDOD 0 | **+1.765** |
| 8 − 9 | cBOD 0.23 /day, IDOD 0 | **+1.765** |
| 5 − 6 | cBOD 20 /day, IDOD 100 | **+1.765** |

**The same number to three decimals across an 87× change in decay rate and a 100 mg/L change in
IDOD** — which is what a quantity that depends on neither should do. Predicted in writing before the
runs: **1.785 for the trapping-depth value, 0.750 for the depth-mean.** Recomputed with the observed
`DO_f` rather than the predicted one it is 1.769, against 1.765 measured.

⭐ **And runs 8–10 happen to be the exact conditions the predictions were registered for** — cBOD
decay 0.23 /day, IDOD 0 — so the absolute numbers can be read straight off, not just the difference:

| observable | trapping depth (registered) | depth-mean (registered) | **observed** |
|---|---|---|---|
| run 8, falling, DO at 500 m | **7.409** | 6.814 | **7.409** |
| run 9, rising, DO at 500 m | **5.624** | 6.064 | **5.644** |
| run 8 near-field `DO_f` | 8.013 | — | 7.991 |
| run 9 near-field `DO_f` | 6.375 | — | 6.399 |

Run 8 lands on its registered prediction **to three decimals**, and run 9 within 0.020, against
alternatives 0.60 and 0.42 away. The near-field endpoints are 0.022 and 0.024 out, which is the
path integral on gradients three times steeper than anything it had been tested on and is the source
of run 9's 0.020.

Inverting eq 30 for the ambient the exe used gives the same answer as a *depth*, on the two runs
where our far-field model is accurate to 0.022 mg/L:

| run | implied `DO_a` | which is the profile's value at | trapping depth is |
|---|---|---|---|
| 8 (falling) | 8.291 | **4.419 m** | 4.472 m |
| 9 (rising) | 6.376 | **4.501 m** | 4.472 m |
| 10 (uniform) | 8.023 | — (8.000 everywhere) | — |

Two profiles with **opposite gradients** bracket the trapping depth within 0.05 m, so the agreement
is not an artefact of either one. The depth-mean is refuted by 1.12 mg/L on run 8 and 0.79 on run 9,
**in opposite directions**.

## ✅ Settled: the near field does not clamp, and `IDOD (D−1)/D` holds at 33× the tested value

Runs 5–7 carry IDOD = 100 mg/L, and the exe prints a near-field DO column that falls to
**−93.2 mg/L** without a warning, a clamp, or a NaN. Row 242's form is confirmed far outside where
it was fitted — the implied IDOD, backed out row by row, converges to **100.010 against a typed
100**, an agreement of 0.01 %:

| `D` | 1.019 | 1.123 | 1.826 | 7.233 | 179.760 | 246.607 |
|---|---|---|---|---|---|---|
| implied IDOD | 113.26 | 103.45 | 101.52 | 100.34 | 100.014 | **100.010** |

⚠️ **The early rows are not noise, they are the one-step accumulator lag of row 220 amplified.** At
IDOD 3 that lag was worth 0.06 mg/L and reached the printed resolution by `D` > 5; at IDOD 100 the
same lag is worth 1.9 mg/L and has not fully washed out by `D` = 5. Our reproduction is therefore
0.74 mg/L worst past `D` > 5 here against 0.0010 at IDOD 3 — the *form* is right, the first-step
convention is what is approximate, and it scales with IDOD.

⚠️ **One row is unexplained.** Both IDOD-100 runs print **exactly 0.000** in the first row where the
accumulator form gives +0.25, and both do so despite having different ambients at the port (3.0 and
8.0), which the form says should matter. Rows 2 onward are negative and plainly unclamped. One row,
in the row already known to be special — recorded rather than modelled.

## ✅ Settled by runs 11 and 12: IDOD does **not** appear a second time in the far field

Run 11 is the run this case asked for — IDOD 100 at cBOD decay 0.23, removing the 20 /day
systematic. Run 12 repeats it with the **effluent DO raised from 2 to 20**, which turns out to
settle a separate question entirely.

The far field **opens at `FF` = 1**, and that is where the test lives: any second appearance of IDOD
would be at full size in the first row, before Brooks spreading has diluted anything.

| second appearance in eq 30 | shift it requires at `x` = 14 m | observed (model − exe) |
|---|---|---|
| none | 0 | **+0.004 mg/L** |
| undiluted, `−IDOD/FF` | −100.0 | — |
| divided, `−IDOD/(D·FF)` | −0.406 | — |

**Both are refuted by the opening rows alone**, without any appeal to a fit. Inverting eq 30 for the
ambient gives **8.019** on run 11 against **8.018** on its IDOD-0 twin — the far field's ambient does
not notice IDOD at all.

## ⭐ Settled by run 12: `DO_e` and `IDOD` are separately identifiable, and treated oppositely

Every previous trace could see only the difference `DO_e − IDOD`, so the two were assumed
interchangeable. Runs 11 and 12 differ **only** in `DO_e`, 2 against 20, and their near-field columns
differ by exactly the seed term:

| `D` | 1.019 | 1.123 | 7.233 | 179.760 | 246.607 |
|---|---|---|---|---|---|
| run 12 − run 11 | 17.647 | 15.984 | 2.436 | 0.098 | **0.072** |
| `18/D` | 17.664 | 16.029 | 2.489 | 0.100 | **0.073** |

So the two numbers typed into the same dialog behave in opposite ways: **`DO_e` is diluted away as
`1/D`** — 18 mg/L of it becomes 0.07 by the end — **while `IDOD` grows to its full typed value**,
because one is carried by the effluent and the other, wrongly, by the water entrained into it. That
is the clearest single statement of the defect in row 242, and it needs no model to see.

## ⚠️ One residual left, and it is not a missing term

Run 11's far field reproduces to 1.45 mg/L worst on a 53 mg/L span, where its IDOD-0 twin at the same
rate and geometry reproduces to 0.022. The discrepancy scales with `DO_f − DO_a`, and it **arcs**:
0.004 at the first row, −1.449 mid-field, −0.010 at the last. No term in eq 30 can do that — every
candidate is monotone in `FF`, which is exactly why the section above can refute them.

Backing the mixing factor out of the exe's own numbers, it disagrees with the printed `Dilution`
column by up to **1.7 % mid-field** while agreeing to 0.00 % at both ends, non-monotonically. So it
is a discrepancy in the far-field mixing itself, invisible in every earlier run because
`DO_f − DO_a` was a couple of mg/L rather than a hundred. Recorded, not modelled.

## What this closes

- Row 243's caveat is gone: `DO_a` is the trapping-depth value, and the depth-mean is refuted.
- Row 242 is confirmed at 33× its fitted IDOD, with the first-step convention identified as the
  approximation rather than the form.
- The near field is confirmed not to clamp, which no archived trace had ever tested.
- Runs 11 and 12 close the last question -- no second IDOD term in the far field -- and
  separate `DO_e` from `IDOD` for the first time.
- Runs 8–10 also re-confirm the far field at 0.022 mg/L on two stratified profiles, and the
  near-field path integral at 0.067 on gradients three times steeper than case27 run 8's.
