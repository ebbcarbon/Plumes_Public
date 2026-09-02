# style_enumeration

**Question.** What does each of the exe's three similarity-profile options do to the centreline? The options are now known (operator, 2026-08-25): **Default Profile** (selected on open), **3/2 Power law Profile**, **Gaussian Profile**. The default is measured -- style_default.dat gives Dilutn / CL-Dil = 2.0000 flat over 410 rows, the parabola. TWO RUNS REMAIN, one per unselected option. This gates PLAN 8.4, and 8.4 gates the dose study's headline, because Omega_brucite's risk window is a centreline quantity and the centreline is what a profile choice moves.

## Run it

1. Open `style_enumeration.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - ⭐ the **similarity profile** selector -- enumerated 2026-08-25, and it offers exactly three: `Default Profile` (selected on open), `3/2 Power law Profile`, `Gaussian Profile`. Run the two that are not the default, one run each
   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - leave stop-plume-at-surface AS YOU FIND IT and say which way it was -- it writes into nearfield_flags[1] and belongs to surface_stop_pair_v2, not to this experiment
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
| **3/2 Power law Profile** -> Dilutn / CL-Dil | **3.8889** unmerged -- the exact reciprocal of the area-average of `[1 - u^1.5]^2`, which is the profile the 3rd edition derives its own 3.89 from (PLAN 6b). If this option reads 3.889 the control is real, and the exe defaults away from the profile its own manual documents |
| **Gaussian Profile** -> Dilutn / CL-Dil | the value identifies WHICH Gaussian, and that is the point of running it. A Gaussian truncated at the plume radius has no single peak-to-mean: `exp(-u^2)` gives **1.582**, `exp(-2u^2)` gives **2.313** (PLAN 6b's candidate), `exp(-3u^2)` gives **3.157**. Whatever it prints pins the decay constant |
| if both come back 2.0000 anyway | the control is inert -- present in the dialog and not reaching CL-Dil. That is a finding in its own right, a user-facing option that does nothing, and it leaves PLAN 8.4's parabola standing unconditionally |
| the direction, because the first issue of this note had it upside down | report **Dilutn / CL-Dil**, flux-average over centreline. The centreline is the LESS diluted of the pair, so the ratio is >= 1. CL-Dil / Dilutn reads 0.5000 and is the same measurement inverted |
| merging | this geometry never merges -- the trace prints `Plumes not merged` -- so only the unmerged column above is testable here. The merged values would be 2.2222 for 3/2-power, 1.5000 parabolic and 1.6718 for exp(-2u^2) |

## Notes

- TWO runs, independent, either order. For each: select the option, run, then copy the trace to `style_threehalves.dat` or `style_gaussian.dat` and the project to `asrun_style_<same>.prj` BEFORE the next run, which overwrites both.
- ⭐⭐ **Why this matters more than it looks.** PLAN 8.4 has been sitting on whether to move the port from the exe-matching parabola to the Gaussian the jet-and-plume literature favours for scalars, and the assumed cost of that move was LEAVING PARITY. If `Gaussian Profile` is a real setting there is no such cost: the port can be Gaussian and still reproduce a run the exe can produce. That is the single thing most likely to move the dose study's headline number.
- ✅ The default option is already done: `style_default.dat` and `asrun_style_default.prj` are in this directory from 2026-08-24 and give 2.0000. Do not re-run it.
- The output interval is already 1 in the file and needs no typing.
- WHICH EXE BUILD did this run: the far-field header's wastefield width says which arm of ledger row 275 you are on, but only after the fact -- write down which executable was launched, and from where. The 2026-08-25 rerun of surface_stop_pair_v2 came back with a near field bit-identical to August's over 275 steps and a wastefield width of 96.29 m against 109.59 m, which is the cos-30 legacy arm. Nothing in the .prj or the .dat records which binary ran.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     f9742e79b6b8b97469b148307ce94d456e9e1acd (dirty)
generated  2026-08-25T22:58:34Z
case       29b8d2e3226f8d5eba3b1f0500f2beb87c88693a7dfdabf15779b06e3696235f
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
