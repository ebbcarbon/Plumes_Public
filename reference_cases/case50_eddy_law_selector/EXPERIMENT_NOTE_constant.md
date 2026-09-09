# eddy_law_constant

**Question.** Which `.prj` flag encodes the far-field eddy-diffusivity selector, what does the header print for `Constant Eddy Diffusivity`, and does the exe's constant eddy diffusivity law match the port's?

## Run it

1. Open `eddy_law_constant.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: **leave as loaded** -- do not untick by habit
   - **far-field eddy diffusivity: select `Constant Eddy Diffusivity`** -- the selector opens on the 4/3 law; this run exists to see what selecting another option does
   - carbonate module: **off** -- nothing to type in the chemistry dialog for this run
   - far-field stop: calculation distance **500 m** and dilution **10000x** -- type *both*.
     The exe stops at whichever binds first, the `.prj` carries neither, and an
     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN section 8c TODO 2).
   - far-field eddy diffusivity: **Constant Eddy Diffusivity**. The selector offers three laws; `4/3 power law` is the GUI default and the only one ever archived,
     so check it rather than assume it -- the `.prj` field that stores the choice is undecoded.

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
| total flow | 0.000219063 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.01` for 0.0127 and `Ttl-flo 0.00` for 0.000219063. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| near field, every column | bit-identical to case03's interval-1 trace (`case03_carbonate/kso4_option3.dat`, hydrodynamic columns) -- the law is a far-field input and nothing upstream of the transition reads it |
| the seven far-field flags in the as-run `.prj` | **one position changes** from the archive's `1,0,0,1,1,1,0`. Position 4 (1-indexed) is the standing guess for the law; whichever position moves, and to what, is the decoding this run exists for |
| the far-field header's law line | prints something other than `4/3 Power Law` -- record the exact string; the reader (`io/dat.py`) stores it as `eddy_diffusivity_law` and has only ever seen one value |
| far-field `Dilution` at 100 m | **747.6** under this law (the 4/3 default gives 997.8 on the same near field); the port's Brooks is confirmed to 5e-4 against the exe's own standalone calculator on the 4/3 law (row 119), so a match here also confirms the other law's implementation |
| far-field `Width` at 100 m | 92.46 m |
| far-field `Dilution` at 200 m | **977.3** under this law (the 4/3 default gives 1790.9 on the same near field); the port's Brooks is confirmed to 5e-4 against the exe's own standalone calculator on the 4/3 law (row 119), so a match here also confirms the other law's implementation |
| far-field `Width` at 200 m | 122.17 m |
| far-field `Dilution` at 500 m | **1470.9** under this law (the 4/3 default gives 4964.5 on the same near field); the port's Brooks is confirmed to 5e-4 against the exe's own standalone calculator on the 4/3 law (row 119), so a match here also confirms the other law's implementation |
| far-field `Width` at 500 m | 184.53 m |
| far-field first row | dilution 534.351 at 2.844 m -- the near-field end, identical under every law |

## Notes

- Ebb's default profile (case03's configuration) without chemistry, interval 1.
- Copy the trace aside as `eddy_law_constant.dat` and the rewritten project as `asrun_eddy_law_constant.prj` before any further run.
- One run per note, one law per run. The sibling directory asks for the other non-default law on the same project.
- WHICH EXE BUILD did this run: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it (ledger row 275).

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     d0038865208929724a1b5a795f5fdd5d5951a027 (dirty)
generated  2026-08-26T19:57:38Z
case       be051eb0ea88da25c678128529f1684f3729da395cf1b51dfd3d6f35200a9e0a
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
