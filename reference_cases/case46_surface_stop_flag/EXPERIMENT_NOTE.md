# surface_stop_pair_v2

**Question.** Is nearfield_flags[1] the stop-at-surface checkbox? Run A (box TICKED) is already in this directory as surface_ON.dat/.prj -- it stops on `Plume surfaces` at step 275 with flags[1] = 1. This experiment is RUN B ONLY: the identical case with the box UNTICKED. If the flag is the box, run B comes back flags[1] = 0 and runs past the surface; if it comes back 1 again, the flag is something else and PLAN 8e debt 3 stays open.

## Run it

1. Open `surface_stop_pair_v2.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - ⭐⭐ stop plume at surface hit: **UNTICK IT**. It is TICKED when the project opens and unticking it is the entire experiment -- if it is still ticked when you press run, the result is a duplicate of surface_ON.dat and settles nothing (this is what happened on 2026-08-25)
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
| nearfield_flags[1] in the as-run .prj | 0. This is the whole question -- run A came back 1 with the box ticked, so a 0 here identifies the field and a second 1 refutes it |
| where the near field stops | it does NOT stop at the surface: the `Plume surfaces` banner still prints around step 275, and the run continues to roughly step 476 on `Plume traps`, the way case31's surface_off did (572 rows there, on a longer interval). Registered 2026-08-24, before run A came back |
| the first 275 steps | bit-identical to surface_ON.dat on every shared step and column -- the box changes where the run STOPS, not what it computes. If these differ, the box is doing something to the physics, a bigger finding than the flag |
| final dilution | higher than run A's 169.754, because the plume goes on entraining past the surface. case31's unticked run reached 246.607 on the same geometry |

## Notes

- ONE run. Everything else in this directory is already answered.
- Afterwards, copy the trace to `surface_OFF.dat` and the project to `surface_OFF.prj` -- both, before anything else is run, because the exe overwrites the trace and rewrites the project on every run.
- ⛔ Do NOT run this from `surface_ON.prj`. That is August's as-run file; running from it is what produced the 2026-08-25 duplicate. Open `surface_stop_pair_v2.prj`, which this script has just rewritten -- the previous copy on disk was truncated by the exe from 154 lines to 109 and will not load.
- WHICH EXE BUILD did this run: the far-field header's wastefield width says which arm of ledger row 275 you are on, but only after the fact -- write down which executable was launched, and from where. The 2026-08-25 rerun of surface_stop_pair_v2 came back with a near field bit-identical to August's over 275 steps and a wastefield width of 96.29 m against 109.59 m, which is the cos-30 legacy arm. Nothing in the .prj or the .dat records which binary ran.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     f9742e79b6b8b97469b148307ce94d456e9e1acd (dirty)
generated  2026-08-25T22:57:49Z
case       82b58883b020ae0cd29e14198d0d4f14c0d93be6cf22c7ee991a17f3f3e23237
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 11 m port** or the exe refuses to run.


## ✅ Run B came back, and it closes the question (2026-08-25)

`surface_OFF.dat` / `surface_OFF.prj` -- the box **unticked**, everything else identical.
**All four registered predictions hold, and two of them exactly.**

| prediction | predicted | observed |
|---|---|---|
| `nearfield_flags[1]` | **0** | **0** (run A: 1; every other flag identical) |
| where the near field stops | banner still prints, run continues to **~476** on `Plume traps` | banner prints, last step **476**, ends on `Plume traps` |
| the first 275 steps | bit-identical to `surface_ON.dat` | **worst difference 0.0** over 275 steps x 13 columns |
| final dilution | above run A's 169.754 | **217.021** |

⭐⭐⭐ **So `nearfield_flags[1]` IS the stop-at-surface checkbox, 1 = stop.** The controlled pair
does what the archive could not: one geometry, one exe session, one box moved. Ledger row 187's
stop-at half -- retired ⊘ `no input` because the only evidence was two projects that disagreed --
now has its input, and PLAN 8e debt 3 is closed.

⭐ It also confirms the retraction in `plumes2.experiments`' settings docstring: the exe never
flipped that flag, **our own README instruction did**, by telling the operator to untick the box
on every generated run. The default tuple stopped saying that on 2026-08-24 and this pair is why.

⚠️ Two things to carry, neither affecting the result:

- **`flags[3]` reads 2 in both runs** where the note asks for a rise/fall count of 3. The pair is
  still controlled -- both runs have it -- but either the setting was left at 2 or `flags[3]` is
  not the rise/fall count. Worth one look next time the dialog is open.
- **The wastefield widths differ, 109.59 m against 111.12 m**, and that is *not* the build split:
  the two runs stop in different places, so their near-field endpoints differ and Brooks starts
  from a different width. Both are the no-cosine arm. The legacy-build run in this directory is
  `ModelResults_on.dat` at 96.29 m.
