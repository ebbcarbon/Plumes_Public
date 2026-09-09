# shoreline_stop_on

**Question.** Is the exe's shoreline stop inert even when the box is ticked against a non-zero shoreline vector? This arm is the ticked half of the controlled pair case12 could not be (its .prj is lost): identical projects, identical typed vector (60°, 5 m), the box the only difference. Bit-identical traces close ledger row 90's caveat and make the SSMC item a clean bug report; a difference is a live feature nobody has ever seen fire.

## Run it

1. Open `shoreline_stop_on.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns (already named in the generated .prj)
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: leave as loaded (the plume traps ~1.3 m down; inert here)
   - ⭐⭐ type the shoreline vector: **60 degrees, 5 m** — case12's entry, re-typed because the generated file carries 0, 0 (the .prj convention is unknown, so this generator refuses to guess an order)
   - ⭐⭐ THEN tick **stop plume at shoreline hit** — vector first, box second. ⚠️⚠️ Never run the box ticked while the vector still reads zero: that is ledger row 282's silent failure, and it truncates the project on rewrite
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
| this arm against shoreline_stop_off | bit-identical .dat, every row and column, near field and far field — the exe is deterministic across sessions (row 191c), so byte-equality is decidable |
| as-run near-field flag 3 | 1 — the box writes the flag (recon checklist, case51). If it comes back 0 the box was not ticked and this arm duplicated the off arm; say so and re-run |
| as-run shoreline records | ⭐ the archive's FIRST non-zero shoreline vector: two reals, one holding 60 and one holding 5, in an order no saved project has ever shown (PORTING_NOTES). Whichever position holds 60 decodes the convention |

## Notes

- ONE run. Copy the .dat and the as-run .prj aside before anything else runs.
- The generated projects in shoreline_stop_on/ and shoreline_stop_off/ are byte-identical on purpose: the typed vector is the same in both arms, so the box is the only intended difference between the two runs.
- case12 is the archived box-on sibling of this configuration (chemistry on, interval 5): no shoreline event, plume to y = 5.389 m against a 5 m shoreline. This pair exists because case12 has nothing to diff against.
- No chemistry and no DO — do not enter any; the carbonate tab stays off.
- WHICH EXE BUILD did this run: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it, and the far-field wastefield width is the after-the-fact fingerprint (row 275). Legacy build is fine here — the operator prefers it for physics without chemistry — but the answer has to be written down.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     6c8f21596da5b7a78653372128f82a20fec20deb (dirty)
generated  2026-09-02T16:37:34Z
case       5823bb324209710cce625c1424f9b0b8f8db70726531461e1d2e7ef2f295ab29
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
