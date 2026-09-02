# farfield_do_closeout

**Question.** The last two questions in Phase 4. (1) Eq 30's ambient DO is the profile value at the trapping depth -- but case27 run 8 could not separate that from the profile's depth-mean, which sat 0.025 mg/L away. K1 and K2 are mirror images with the **same depth-mean and different trapping-depth values**, so the difference between them answers it outright. (2) Whether IDOD appears a second time in the far field, and whether the near field clamps DO at zero -- no archived near-field trace has ever gone negative.

## Run it

1. Open `farfield_do_closeout.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry:

   - output interval 1
   - all output columns, including DO
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: UNTICKED
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
| K1 near-field DO_f | 8.013 mg/L |
| K1 far-field DO at 102 / 300 / 500 m | **7.725 / 7.476 / 7.409** if DO_a is the trapping-depth value (8.264); 7.672 / 7.090 / 6.814 if it is the depth-mean (7.167) |
| K2 near-field DO_f | 6.375 mg/L |
| K2 far-field DO at 102 / 300 / 500 m | **6.074 / 5.742 / 5.624** if DO_a is the trapping-depth value (6.354); 6.113 / 6.028 / 6.064 if it is the depth-mean (7.167, identical to K1's) |
| K1 - K2 at 500 m | **1.785** for the trapping depth against **0.750** for the depth-mean -- the discriminator, and it needs no absolute accuracy from us |
| K3 near-field DO_f | **-91.612 mg/L** if IDOD acts on the ambient and nothing clamps; +7.570 if eq 23's placement were right; 0.000 if the exe clamps |
| K3 near-field DO crosses zero | at D = 1.123, i.e. within the first few printed steps |
| K3 far-field DO at 102 / 300 / 500 m | **-87.032 / -57.210 / -38.350** with no second IDOD term; -182.134 / -122.046 / -84.137 if it reappears undiluted; -87.418 / -57.473 / -38.535 if it reappears divided by the near-field dilution |

## Notes

- **When the traces come back**, drop them in this folder and run `.venv/Scripts/python reference_cases/case28_farfield_do_closeout/analyse_do_closeout.py` (moved beside this note when `generated/` was retired, 2026-08-26). It adjudicates every observable above against the predictions in this note, so the verdict is fixed by arithmetic written before the runs. Edit its `RUNS` mapping first if the exe's output counter continued past 1.
- ⚠️⚠️ **THREE RUNS FROM THIS ONE PROJECT**, and the hydrodynamics must be identical in all three: 572 steps, `D_near` = 246.607, trapping depth 4.472 m. Check that first -- if a run has a different step count, something in the geometry moved and its DO is not comparable. DO is a pure overlay (row 215), so the trajectory cannot legitimately change.
- **K1** -- load `AmbientDO_falling.csv`. DO 12.0 at the surface falling to 2.0 at 12 m.
- **K2** -- load `AmbientDO_rising.csv`. The exact mirror: 2.0 at the surface rising to 12.0 at 12 m. **Its depth-mean is identical to K1's, 7.167**, which is the whole point.
- **K3** -- load `AmbientDO_uniform.csv` (DO 8.0 throughout, both ambient BODs zero) and set **IDOD = 100 mg/L**. Everything else as K1/K2.
- DO tab for all three: effluent DO 2.0, cBOD5 20 mg/L at 0.23 /day, nBOD5 30 mg/L at 0.1 /day. IDOD 0 for K1 and K2, **100 for K3**.
- ⚠️⚠️ **Read the six DO fields off the tab at run time and send them with the traces.** The tab is not saved in the `.prj` and it retains values between runs; that is what cost two rounds of analysis on case25 and case26, where a cBOD5 of 20 was worked up as 2000.
- ⚠️ If the exe refuses an IDOD of 100, use the largest it accepts and say what it was -- the run works at any large value, it is only the resolution of the second-appearance test that scales with it.
- ⚠️ K3's near-field DO is expected to be about -91 mg/L. That is not a mistake in the setup; it is the prediction being tested. If it comes back at 0.000 instead, the exe clamps, and that is the finding.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     274b319bd60d53d109f1078f374821badd6e1593 (dirty)
generated  2026-08-18T17:42:52Z
case       59a654ce60fd32649029699091bb4659c63c349484885914824eb53d49cb1083
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 11 m port** or the exe refuses to run.
