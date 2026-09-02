# flagdecode2_bottomhit_nf1

**Question.** Is near-field flag 1 the stop-at-bottom box? Same project, flag 1 flipped to 0: if it is the box, this arm runs past seabed contact the way case06 runs past the surface; if the traces are bit-identical, it is not.

## Run it

1. Open `flagdecode2_bottomhit_nf1.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 10** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - ⚠️ do NOT touch the bottom-hit box -- run exactly as loaded; the flipped flag may already have moved it, and that is the measurement
   - stop plume at surface hit: leave as loaded
   - far-field stop: calculation distance **500 m** and dilution **10000x** -- type *both*.
     The exe stops at whichever binds first, the `.prj` carries neither, and an
     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN section 8c TODO 2).
   - far-field eddy diffusivity: **4/3 power law based eddy diffusivity**. The selector offers three laws; `4/3 power law` is the GUI default. Check it rather than assume it:
     the as-run `.prj` records the choice in far-field flags 2/3/4 (one-hot, case50), so a wrong selection is visible after the fact but only after the run.

3. Run. ⭐ **The exe writes the `.prj` when the model runs** -- there is no Save-As for
   projects (operator, 2026-08-24) -- so the project on disk is now the *as-run* state,
   GUI settings included. Nothing needs saving by hand.
4. ⚠️⚠️ **Before any further run, copy both files aside** under names that say which run
   they are: the next run overwrites the `.dat` **and** rewrites the `.prj`. This is the
   whole reason test34/test35 came back describing a different run than they were filed
   under -- a stale project file is worse than none.

   ⭐ Supporting tables (ambient, DO, carbonate) *can* be saved individually, so those
   survive independently of the run.

## What is in the case

| ports | 25 |
|---|---|
| port spacing | 2 m |
| port diameter | 0.0127 m |
| vertical angle | -45 deg |
| horizontal angle | 90 deg |
| port depth / elevation | 10 m / 0.3 m |
| total flow | 0.000219063 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.01` for 0.0127 and `Ttl-flo 0.00` for 0.000219063. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| if nf1 is the bottom box | the run continues past contact to a later stop (rise/fall count, oscillation, or the step cap) -- trace differs from the base arm after the contact step |
| if nf1 is not the bottom box | bit-identical to `flagdecode2_bottomhit` |
| GUI on load | if nf1 is the box, it shows unticked; write down its state BEFORE running |

## Notes

- Part of the flag-decode round 2 (case51's open question). Legacy build is fine -- the operator prefers it for physics without chemistry.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     99911d63483561ad79cb5e79eac4a23424c6c753 (dirty)
generated  2026-09-01T23:22:25Z
case       310427ca813919f2d955cef1af8e0b640221c39a7edf66363a5125a2efa5db77
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 10 m port** or the exe refuses to run.
