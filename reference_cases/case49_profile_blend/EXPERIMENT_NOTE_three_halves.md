# profile_merged_three_halves

**Question.** How does the exe walk its `3/2 Power law Profile` from round to slab as neighbouring plumes merge -- and is it the same linear law in d/L the default parabola uses?

## Run it

1. Open `profile_merged_three_halves.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns (Centerline-Dilution and Plume-Diameter are the two that matter)
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - **Similarity profile: select `3/2 Power law Profile`** -- the selector opens on `Default Profile` every time (case48); check it before pressing run
   - far-field stop: calculation distance **500 m** and dilution **10000x** -- type *both*.
     The exe stops at whichever binds first, the `.prj` carries neither, and an
     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN section 8c TODO 2).

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
| port spacing | 0.6 m |
| port diameter | 0.0127 m |
| vertical angle | 45 deg |
| horizontal angle | 65 deg |
| port depth / elevation | 2 m / 15 m |
| total flow | 0.005 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02, 0.05 m/s at 90 deg |
| discharge-to-current offset | -25 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.01` for 0.0127 and `Ttl-flo 0.01` for 0.005. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| `Dilutn` and `P-dia`, every row | bit-identical to case44's test79 (the profile is post-processing; case48's three traces shared one `Dilutn` column) |
| `Dilutn / CL-Dil` before the merge banner, developed rows (`Dilutn` > 5) | 3.8889, flat to five figures (case48 measured 3.88997 on the unmerged case03 geometry) |
| `Dilutn / CL-Dil` once `P-dia` >= 2 x 0.6 m (deep slab) | 2.2222 -- the profile's own slab integral (20/9) |
| `Dilutn / CL-Dil` for 0.6 < `P-dia` < 1.2 m | **the assumption under test**: max(2.2222, 3.8889 + 1.6667 * (1 - d/L)), the parabola's linear walk applied between this profile's anchors. Alternatives to look for: no blend at all (flat at the round value), or a geometric blend that is not a straight line in d/L |
| the banner row and the rows after it | the parabola overshoots 2.0 at the banner on this oblique diffuser and ramps into the line over a few rows (PLAN 6b); whether this profile shows the same overshoot/ramp shape is unmeasured -- record it either way |

## Notes

- This is case44's `spacing_0p6m.prj` regenerated from the case, so the .prj here should load identically; test79 in case44 is the default-profile arm and is the control -- no default-profile rerun is needed unless the build differs.
- Copy the trace aside as `profile_merged_three_halves.dat` before any further run.
- One run per note, one option per run. The sibling directory asks for the other option on the same project.
- WHICH EXE BUILD did this run: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it, and the two builds print different wastefield widths for the same project (ledger row 275). test79 was a legacy-build run.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     05d84c01174d4895fb2bc1f9011905d2cc5ababa (dirty)
generated  2026-08-26T18:25:44Z
case       cc6f0284c808bc2357df5745d4644a107400762729e2808656cb52c84b8f49a9
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
