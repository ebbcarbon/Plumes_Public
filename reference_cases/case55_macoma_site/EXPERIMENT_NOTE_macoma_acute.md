# macoma_acute

**Question.** The site's actual values on the acute ambient (0.02 m/s): does the exe reproduce the port's near field, boundaries and pH at 2 ft spacing, 5900 L/h of intake water and the site's uniform chemistry -- the configuration the dose study is built on, which no archived run carries?

## Run it

1. Open `macoma_acute.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 5** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: **leave as loaded** -- do not untick by habit (case49 came back 0 on both runs with no instruction: operator-confirmed habit, 2026-08-26); a run that wants it moved says so here
   - Carbonate chemistry ON. Effluent entered as the (TA, DIC) pair: TA 6000 / DIC 2092 umol/kg -- never TA at a pH. K1K2 option 10 (Lueker), KSO4 option 1. Ambient chemistry: load the CSV written beside this note (TA 2146 / DIC 2092 on both rows; the pH column is PyCO2SYS's value, which the GUI demands and ignores).
   - far-field stop: calculation distance **500 m** and dilution **10000x** -- type *both*.
     The exe stops at whichever binds first, the `.prj` carries neither, and an
     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN section 8c TODO 2).
   - far-field eddy diffusivity: **4/3 power law based eddy diffusivity**. The selector offers three laws; `4/3 power law` is the GUI default. Check it rather than assume it:
     the as-run `.prj` records the choice in far-field flags 2/3/4 (one-hot, case50), so a wrong selection is visible after the fact but only after the run.

   ⚠️ **The carbonate tab is GUI-only.** `AmbientChem_macoma_acute.csv` is written beside the
   `.prj` and can be loaded, but the **effluent** endmember and the constant
   selections (K1K2, KSO4) have to be typed -- the `.prj` holds no chemistry at all.

   ⚠️ **2 of 2 ambient rows have no pH in the case, and the GUI will not run
   with a blank in that column** (found on `dose_parity`, 2026-08-25). The CSV written here
   therefore carries the **PyCO2SYS solution of that row's TA and DIC** at the profile's S and T,
   on the **free** scale the exe's dialog takes typed pH on. The value is **ignored** by the exe,
   which derives the ambient carbonate system from TA and DIC in preference to an entered pH
   (row 45, and confirmed on the ambient table by case03's KSO4 rerun: 7.5 entered in every
   row left the ambient-limit pH at 8.372, where a used 7.5 would have shown as ~0.9 units) --
   so it is there to satisfy the GUI, and it is at least *consistent* with the columns the exe
   does read. Nothing needs typing.

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
| port spacing | 0.6096 m |
| port diameter | 0.0127 m |
| vertical angle | 45 deg |
| horizontal angle | 90 deg |
| port depth / elevation | 2 m / 15 m |
| total flow | 0.00163889 m3/s |
| effluent | 30.9 psu, 11.2 C |
| ambient current | 0.02 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.01` for 0.0127 and `Ttl-flo 0.00` for 0.00163889. Both lose information here.

## Predicted, before the run

| observable | port predicts |
|---|---|
| termination | `oscillation limit` at t = 142 s |
| near-field end: flux-averaged dilution | 158 |
| near-field end: distance from the diffuser | 3.66 m |
| trapping depth (centreline at the end) | 1.68 m |
| plume diameter at the end | 0.84 m |
| wastefield width handed to the far field | 15.5 m |
| merging | the jets merge in shallow overlap before the end (`merging happened` banner expected) |
| port pH (total) | 10.990 |
| pH at the end of the near field (total) | 7.809 |
| Omega_brucite falls back through 1 (flux-averaged; the exe cannot print it) | dilution 2.54, 0.16 s, 3.5 cm from the port |
| acute mixing-zone boundary (6.31 m): dilution / pH | 159 / 7.809 (farfield) |
| chronic mixing-zone boundary (63.09 m): dilution / pH | 360 / 7.765 (farfield) |
| far field at its last row | 504 m, dilution 3970, width 538.7 m |

## Notes

- WHICH EXE BUILD ran this: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it, and the far-field wastefield width is the after-the-fact fingerprint (row 275). This case has chemistry, so it needs the 2026 build.
- The ambient chemistry CSV is in the exe's own table format, which carries three significant figures: it loads as TA 2150 / DIC 2090, not 2146 / 2092. The forecasts above were made at 2146 / 2092 (the difference is ~0.002 in pH). If the dialog allows it, retype 2146 and 2092 into both rows after loading; either way, record what the table held when it ran.
- The port spacing in the .prj is 0.6096 m -- 2 ft in metres. Do not retype it as 2.0: that is the slip the archived runs carry.
- The seabed (17 m) sits below the profile's last row (15 m). Intentional (operator, 2026-09-01); the exe runs this shape on every archived project.
- Surface-stop box: leave as loaded. The Macoma rule is that a surface hit does not stop the plume (operator, 2026-09-08); this case traps at ~1.5 m anyway.
- Copy the returning .dat and the as-run .prj aside before the next run; the other arm overwrites them.
- `case.yaml` beside this note is the port's own statement of the case; `plumes2 run case.yaml` reproduces every prediction above.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     8ad888605d04cf222e1837c8442453503928fb63 (dirty)
generated  2026-09-09T17:26:10Z
case       adc690bc0de789da270ae4aad551608e379d65148045d15a7b477942df19c0a4
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
