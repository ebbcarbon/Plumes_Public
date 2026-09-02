# case26 — the far-field decay, with the rates raised so it curves

Generated as the experiment `farfield_bod_rates` (note: [`EXPERIMENT_NOTE_farfield_bod_rates.md`](EXPERIMENT_NOTE_farfield_bod_rates.md)) and run 2026-08-17. case25 established the
*shape* of the far-field sag but could not separate the demand `L` from the rate `k`, because a
2.74-hour far field makes `1 − e^{−kt}` linear to within 1.3 %. Raising the typed decay rate fixes
that **without touching the geometry** — it is a Dissolved Oxygen tab field — so every result here is
directly comparable with case25's three runs.

It worked: the departure from a straight line is **0.47 mg/L**, against 0.0019 in case25.

## The runs

Same project, same ambient DO (uniform 8.0 mg/L — confirmed loaded, since all three near-field DO
columns are identical and top out at 7.965). Effluent DO 2.0, IDOD 0, cBOD5 2000 throughout.

| trace | cBOD decay | ambient cBOD5 | far-field DO |
|---|---|---|---|
| `ModelResults_1.dat` | **5.0 /day** | 0 | 7.841 → 3.629 |
| `ModelResults_2.dat` | **1.0 /day** | 0 | 7.931 → 6.520 |
| `ModelResults_3.dat` | 5.0 /day | **500** | 10.646 → **99.922** |

`nBOD5` was **30 mg/L decaying at 0.23 /day** in all three runs (reported after the fact; the
experiment note had asked for 0, and the DO tab had retained the value from case24). This turns out
not to matter: over a 2.74-hour far field that channel can take **0.0067 mg/L**, and holding it at
these known values shifts every fit below by 0.12 %. It is ruled out as an explanation for anything
here.

## ⭐⭐ Settled: the ambient BOD is subtracted **undiluted**, and the result is unphysical

G3's far-field DO climbs to **100.06 mg/L**. Oxygen saturation at this temperature is about
11.6 mg/L, so the plume is reported at roughly **nine times saturation**, having started at 10.6 and
risen monotonically over 500 m.

This was predicted, in writing, before the run:

| reading of eqs 28–29 | predicted DO at the last row | observed |
|---|---|---|
| `(BOD_Le − BOD_La)/D`, as the manual writes it | 6.275 | — |
| `BOD_Le/D − BOD_La`, ambient subtracted undiluted | **102.407** | **99.922** |

A 2.4 % match to a prediction of an absurd number, against an alternative that is wrong by a factor
of sixteen. Combined with case25's run 3 — the same effect at a twentieth of the rate, reaching
15.5 mg/L — this is confirmed twice, at two rates, and it is not a modelling choice: **a plume
cannot gain oxygen by travelling through oxygen-demanding water.** It is an exe defect and belongs on
the report-to-SSMC list.

## ✅ Settled: eq 30's `1/FF` structure

Not by comparing fit residuals — by the pointwise demand, which is far stronger. Dividing the
observed sag by `(1 − e^{−kt})` at the typed rate and multiplying back by the Brooks factor gives a
demand that is **flat along the whole far field** (3658 → 3823, a 4.5 % drift). Omit the `1/FF` and
the same quantity **halves**, 3647 → 1699. The form is a single exponential over the Brooks factor.

## ✅ Settled: the rate is used exactly as typed, with no θ correction

Successive DO decrements decay by 0.9919 per block in G1 and 0.9984 in G2 — a ratio of **4.99**
against the typed 5:1. And with the rate fixed at the typed value, each run fits its own single
exponential to a worst residual of 0.079 (G1) and 0.020 (G2) mg/L. The earlier "fitted 4.50 / 1.35"
reading was two-parameter ill-conditioning, not a real offset.

## ⭐ Settled: exactly where the ambient defect sits in the equation

G1 and G3 differ *only* in ambient cBOD5 (0 vs 500), so `DO_3 − DO_1` isolates the ambient term
outright. Divided by the k=5 decay it runs **504 → 221** down the trace, against `500/FF` running
500 → 222 — a mean ratio of **0.9917**, against 0.709 for a flat 500. So the exe computes:

    DO = DO_a + (DO_f - DO_a)/FF  -  [ BOD_Le/D_near  -  BOD_La ] (1 - e^{-kt}) / FF

The ambient BOD is subtracted from the **already-diluted** effluent BOD, and only the resulting
bracket is divided by the Brooks factor. Correct would be `(BOD_Le − BOD_La)/D_total` — the ambient
divided by the *total* dilution. Because `BOD_La` is undivided by `D_near`, any ambient BOD above
`BOD_Le/D_near` flips the sign and the plume gains oxygen without bound. **That is the defect, now
stated precisely enough to report and to re-implement.** Note the ambient term carries **no**
multiplier, which is what makes the next item a separate question.

## ⚠️ Open: the *effluent* demand is 1.9–2.6x eqs 24–29, and the factor tracks the rate

With the ambient structure pinned and nBOD ruled out, one quantity is unexplained — the effluent
amplitude — and it is **not a constant multiplier**:

| typed cBOD rate | fitted `L x D_near` | against cBOD5 = 2000 |
|---|---|---|
| 5.0 /day | 3778.9 | **x1.889** |
| 1.0 /day | 5151.6 | **x2.576** |

Both are flat along the trace, so this is a real amplitude and not a fit artefact. What it is *not*:

- not nBOD — 0.0067 mg/L is all that channel can take here;
- not a θ correction, which would scale both runs equally;
- not reaeration — that is second-order at early time and would leave the early slope ratio at
  exactly 5.0, where the data give **3.646**;
- not a constant offset and not a time offset (both fit far worse);
- not a BOD5→ultimate conversion at any single rate — matching the two points needs c = 0.151 and
  c = 0.492, inconsistent by 3.3x;
- not a dilution error alone, which would scale the ambient term too, and it does not.

**Two points cannot identify a function of the rate.** `g = a + b/k` and `g = a·k^{−n}` both fit
these two exactly and then disagree by 70 % at a third rate. So the next experiment is a third and
fourth rate, plus the linearity-in-cBOD5 check that has never been done — specified in
the `farfield_bod_conversion` experiment (case27, whose note is [`../case27_farfield_bod_conversion/EXPERIMENT_NOTE_farfield_bod_conversion.md`](../case27_farfield_bod_conversion/EXPERIMENT_NOTE_farfield_bod_conversion.md)).
