# flagdecode_nf6

**Question.** Which GUI control does `.prj` nearfield_flags position 6 (1-indexed; python [5]) carry? Undecoded in PLAN section 6; constant in every archived project, flipped here and nowhere else.

## Run it

1. Open `flagdecode_nf6.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 5** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: **leave as loaded** -- do not untick by habit (case49 came back 0 on both runs with no instruction: operator-confirmed habit, 2026-08-26); a run that wants it moved says so here
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
| near-field flag 6 (1 -> 0) | unknown -- no candidate |
| GUI on load | exactly one control differs from flagdecode_base, or none (then the flag is not a dialog control) |
| as-run flag value | 0 if the flag is a control the exe respects and saves; 1 if the exe rewrites it from session state on run (either way the bit's ownership is decided) |
| trace vs flagdecode_base | bit-identical unless the control gates an event that binds on this trajectory -- the plume surfaces (~step 275) and never hits bottom or shoreline, so a surface-gating control shows as truncation and a bottom/shoreline one shows as nothing |

## Notes

- RECONNAISSANCE FIRST, before running: open the project and write down the state of every control on the model-settings and far-field dialogs (the three stop boxes, the rise/fall count, the eddy-diffusivity selector, and any checkbox not yet in that list). Compare against `flagdecode_base` opened the same way: the flipped flag should show as EXACTLY ONE changed control. Name it. If nothing visible changed, that is also an answer -- the flag is not a dialog control, and the as-run `.prj` will say whether the exe preserves the bit or rewrites it.
- WHICH EXE BUILD: record which executable was launched and from where. The far-field header's wastefield width is the fingerprint regardless -- ~96-98 m is the current build (the cosine, row 275), ~110-112 m the legacy one. This suite doubles as the build discriminator PLAN section 6 used to ask for on case42-45: any future far-field run at this 30-degree offset identifies its own build.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     659620fec4942729943c0b184b34f3e1e14534bf (dirty)
generated  2026-09-01T22:53:21Z
case       db0f073cb625596f4f82205511685083b724ac2a24d79e3a4f7a1068cde7b3b7
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 11 m port** or the exe refuses to run.
