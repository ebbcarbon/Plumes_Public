# farfield_bod_rates

**Question.** case25 established the shape of the far-field sag but could not separate the demand from the decay rate, because a 2.74-hour far field makes 1 - exp(-k t) linear to within 1.3 %. Raising the typed decay rate fixes that without touching the geometry: at 5 /day the decay curves visibly within the same far field. Then the curvature gives k, the amplitude gives L, and the two together settle whether the 5-day BOD is converted to an ultimate demand, whether the typed rate is theta-corrected, and what divides the demand.

## Run it

1. Open `farfield_bod_rates.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry:

   - output interval 1
   - all output columns, including DO
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: unticked
   - Dissolved Oxygen Calculations: TICKED

3. Run, and save the `.dat` **and** the `.prj` as it stood at run time.

⚠️ If the GUI resets the project on exit, save the `.prj` before closing it. A stale
project file is worse than none: test34/test35 came back describing a different run.

## What is in the case

| ports | 18 |
|---|---|
| port spacing | 6.1 m |
| port diameter | 0.076 m |
| vertical angle | 45 deg |
| horizontal angle | 30 deg |
| port depth / elevation | 11 m / 0.31 m |
| total flow | 0.350501 m3/s |
| effluent | 0 psu, 2.63 C |
| ambient current | 0.05, 0.055, 0.06, 0.065, 0.07, 0.085, 0.09 m/s at 0 deg |
| discharge-to-current offset | 30 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.08` for 0.076 and `Ttl-flo 0.35` for 0.350501. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| near-field DO at the transition (unchanged from case25) | 7.965 mg/L |
| near-field dilution there (the exe's own, not ours) | 169.754 |
| G1 DO at 102 m | **6.779** if k is used as typed; **7.130** if it is theta-corrected to 12 C |
| G1 DO at the last row (500 m) | **5.706** as typed / **6.274** corrected |
| G1 curvature -- the whole point of the run | 0.7127 mg/L departure from a straight line, against 0.0019 in case25. That is what separates L from k |
| G2 DO at the last row | **7.415** as typed / **7.573** corrected |
| G2 curvature | 0.0331 mg/L |
| G1 vs G2 at the last row | -1.709 mg/L -- a 5x change in the typed rate must move the curve this much if the rate is used at all |
| G3 DO at the last row | **6.275** if eq 28 is applied as written, `(BOD_Le - BOD_La)/D`; **102.407** if the ambient is subtracted undiluted, `BOD_Le/D - BOD_La`. The second is above the ambient, i.e. the plume *gains* oxygen -- which is what case25 saw |
| G3 note | at 5 /day the ultimate conversion is a no-op, so G3 asks only the diluted-vs-undiluted question. The conversion question needs a *low* rate and is answered by re-reading case25 once G1 has pinned the divisor -- see the notes |
| ⚠️ and the case25 anomaly restated | case25's run 3 showed DO *rising* to 15.5 mg/L against an 8.0 ambient when ambient cBOD5 was 500. If G3 does that again, the ambient BOD is being subtracted undiluted and that is an exe defect, not a modelling choice |

## Notes

- ⚠️ THREE RUNS FROM THIS ONE PROJECT, and **the geometry is deliberately identical to case25's** -- same project, same ambient, same everything. Only the DO tab changes, so every result is directly comparable with the three runs already in hand.
- **G1 -- the key run.** Effluent DO 2.0, IDOD 0, cBOD5 **2000**, nBOD5 **0**, cBOD decay **5.0 /day**, nBOD decay anything (it is unused). Load `AmbientDO_G1_G2.csv` (DO 8.0 everywhere, ambient BODs zero).
- **G2 -- the rate control.** Identical, but cBOD decay **1.0 /day**. Two typed rates five times apart; if the fitted rates do not track them, the typed field is not what drives the decay.
- **G3 -- the ambient subtraction, asked again where the curve is informative.** Identical to G1, but load `AmbientDO_G3.csv`, which sets ambient cBOD5 to **500**.
- ⚠️ **Please load the ambient CSVs.** case25's first run went out with the previous DO profile still in the tab, which was recoverable only because the near-field mechanism was already known. The near-field DO column identifies the profile: with a uniform 8.0 it tops out at 7.965 and never exceeds 8.0, and with the old 8/9/10/9/8 profile it reaches 9.49.
- ⚠️ **If the decay-rate field rejects 5.0 /day**, use the largest it accepts and say what it was. Every prediction above scales with it, and the curvature -- the thing being bought -- grows with the rate: 0.0019 mg/L at 0.23, 0.024 at 1.0, 0.51 at 5.0.
- ⚠️ **The conversion question and the rate question cannot share a run**, and that is structural rather than an oversight: the ultimate factor `1/(1 - exp(-5k))` is 1.463 at k = 0.23 but 1.007 at k = 1 and exactly 1 at k = 5, so it is only visible at a low rate -- where the decay does not curve. G1 settles the divisor at a high rate, where the conversion cannot interfere; that then makes case25's existing k = 0.23 runs readable, because their only remaining unknown becomes the conversion. The new run unlocks the old data rather than replacing it.
- The far-field current, distance and grid are untouched, so the far field will again run 494 rows to 500 m in 2.74 hours. Nothing about the *geometry* needs to change to answer this -- only how fast the demand decays.
- ⚠️ Predictions are built from **the exe's own** transition values (D = 169.754, DO_f = 7.965), taken from case25. Our own near field reports a 40 % higher dilution for this geometry because the exe stops at its surface hit and we do not -- the stop-at-surface checkbox is session state the .prj cannot carry (ledger row 187). That gap is about where the near field *ends*, not about the trajectory: at the depth the exe stopped, our dilution agrees to 2.7 %.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     af6144e2bac5d5ad461f78a2dd31ea2d1b9e16ac (dirty)
generated  2026-08-17T23:07:26Z
case       dd667f4f72e4b84456a115c0d1bbbf0952057ac444131b236a2bfc8ab57631ff
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 11 m port** or the exe refuses to run.
