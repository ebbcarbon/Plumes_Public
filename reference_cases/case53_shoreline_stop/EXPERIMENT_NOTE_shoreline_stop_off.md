# shoreline_stop_off

**Question.** The control arm: the identical project and the identical typed shoreline vector (60°, 5 m) with the stop-at-shoreline box left UNTICKED. Everything that matters is the comparison against shoreline_stop_on.

## Run it

1. Open `shoreline_stop_off.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns (already named in the generated .prj)
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: leave as loaded (the plume traps ~1.3 m down; inert here)
   - ⭐⭐ type the shoreline vector: **60 degrees, 5 m** — the same entry as the on arm
   - ⭐⭐ leave **stop plume at shoreline hit** UNTICKED — the box is the experiment, and this is the arm where it stays off
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
| vertical angle | 45 deg |
| horizontal angle | 90 deg |
| port depth / elevation | 2 m / 15 m |
| total flow | 0.005 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.01` for 0.0127 and `Ttl-flo 0.01` for 0.005. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| shoreline banner | none. No archived trace has ever printed one and none of the seven known banners is shoreline-flavoured (case12 README) |
| where the run ends | step 400 exactly, on `Plume traps`, at Dilutn 296.962, y-posn 5.389, Depth -1.722 — case12's archived endpoint, which this configuration reproduces with chemistry off (a scalar overlay is a pure overlay, row 215) if the operator's session state matches. A different step is input drift, not the shoreline |
| the port's own integration | the port integrates this case to `oscillation limit` at t = 163 s, flux-averaged dilution 280, ending at y = 5.27 m — past the 5 m shoreline, which it first crosses at t = 152 s (dilution 259, depth 1.81 m). The plume never nears the surface: minimum depth 1.29 m, matching case12's printed -1.296 |
| if the arms differ at all | the shoreline feature DOES something, and three archived configurations (case08 twice, case12) never had the geometry to show it — localise the first differing step and check whether it sits at the y = 5 m crossing (~9 rows before the end) |
| this arm against shoreline_stop_on | bit-identical .dat, every row and column — see the on arm's note; the pair is one measurement split across two runs |
| as-run near-field flag 3 | 0 — the untouched box. A 1 here means the box was ticked by habit and the pair collapsed into two on-runs; say so and re-run this arm |
| as-run shoreline records | non-zero here too (the vector is typed in both arms), corroborating whatever order the on arm shows |

## Notes

- ONE run. Copy the .dat and the as-run .prj aside before anything else runs.
- Run this arm and shoreline_stop_on in either order; neither depends on the other's output, only on both existing.
- No chemistry and no DO — do not enter any; the carbonate tab stays off.
- WHICH EXE BUILD did this run: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it, and the far-field wastefield width is the after-the-fact fingerprint (row 275). Legacy build is fine here — the operator prefers it for physics without chemistry — but the answer has to be written down.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     6c8f21596da5b7a78653372128f82a20fec20deb (dirty)
generated  2026-09-02T16:37:34Z
case       fd064e54408776925d622f407e77d380c75abb4f1aa272c481eb3e1445dbf51f
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
