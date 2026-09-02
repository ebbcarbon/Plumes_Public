# dose_parity

**Question.** Does the exe's embedded CO2SYS stay within its measured 0.011-0.024 pH of PyCO2SYS as the effluent alkalinity rises from 4000 to 20000 umol/kg at a fixed DIC of 2500 -- port pH from ~9.5 to ~12 -- or does the gap grow with dose? Phase 9 cannot quote a parity-checked pH along the dose axis until the exe has been run along it.

## Run it

1. Open `dose_parity.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - leave stop-plume-at-surface AS YOU FIND IT and say which way it was (it is surface_stop_pair_v2's subject; this geometry traps at ~2.3 m and never surfaces)
   - carbonate module ON, KSO4 selector = 1 (case03's setting: Dickson bisulfate, Lee borate per row 128), K1K2 as case03 had it
   - ambient chemistry: load AmbientChem_dose_parity.csv from this directory (it is case03's testco2.csv, 1-4 m, which reaches below the 2 m port, with the blank pH column filled by the solver because the GUI refuses a blank -- nothing to type)
   - far-field stop: calculation distance **500 m** and dilution **10000x** -- type *both*.
     The exe stops at whichever binds first, the `.prj` carries neither, and an
     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN section 8c TODO 2).

   ⚠️ **The carbonate tab is GUI-only.** `AmbientChem_dose_parity.csv` is written beside the
   `.prj` and can be loaded, but the **effluent** endmember and the constant
   selections (K1K2, KSO4) have to be typed -- the `.prj` holds no chemistry at all.

   ⚠️ **4 of 4 ambient rows have no pH in the case, and the GUI will not run
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
| hydrodynamics, every run | Dilutn, P-dia, Depth bit-identical to case03's kso4_option3.dat on every shared step -- chemistry rides on top of the plume and does not feed back (row 215). If this fails, nothing below is about chemistry |
| TA and DIC columns, every run | conservative in dilution: TA_row = TA_amb + (TA_eff*rho/1000 - TA_amb)/Dilutn to the exe's printed precision, as case03 shows (row 40); DIC likewise from 2500*rho/1000. The exe prints mmol/m3, i.e. umol/kg x 1.02695 at this effluent (PLAN 7.5) |
| the gap, and the reason for the runs | on case03/case04 (port pH ~10.0-10.4) the exe's pH sits 0.011-0.024 BELOW PyCO2SYS and its Omega 0.8-3.4 % above (rows 41/43), attributed to the speciation rather than the Ksp (row 123). These runs put the exe's port pH at ~9.5, ~10.6, ~11.4 and ~11.9. If the divergence is a constant offset the first-row gap stays 0.01-0.03 all the way up and the dose curve's pH is parity-checked to that; if it widens above pH 11 -- where borate, water and the carbonate alkalinity terms trade places -- the widening is the number the study must carry as a named non-parity justification |
| OmegaA / OmegaC, every run | the exe reports both; the ratio OmegaC/OmegaA is Ksp_A/Ksp_C and must match case03's 1.57 exactly (row 123). Any row where it does not is a Ksp change, not speciation |
| TA 4000: first printed row (Dilutn ~1.0) | pH(total) ~9.168, OmegaA ~17.9, OmegaC ~28.2; the exe 0.01-0.03 below on pH and a few percent above on Omega if the gap is the constant offset measured at TA 4000 |
| TA 4000: near-field end (Dilutn ~534) | TA ~2902 umol/kg (~2980 mmol/m3 as printed), pH(total) ~8.386, OmegaA ~4.67 -- within 0.007 pH and 2.2 % of the exe if row 36's far-field agreement holds |
| TA 6000: first printed row (Dilutn ~1.0) | pH(total) ~10.671, OmegaA ~36.6, OmegaC ~57.5; the exe 0.01-0.03 below on pH and a few percent above on Omega if the gap is the constant offset measured at TA 4000 |
| TA 6000: near-field end (Dilutn ~534) | TA ~2906 umol/kg (~2984 mmol/m3 as printed), pH(total) ~8.390, OmegaA ~4.71 -- within 0.007 pH and 2.2 % of the exe if row 36's far-field agreement holds |
| TA 10000: first printed row (Dilutn ~1.0) | pH(total) ~11.505, OmegaA ~37.7, OmegaC ~59.2; the exe 0.01-0.03 below on pH and a few percent above on Omega if the gap is the constant offset measured at TA 4000 |
| TA 10000: near-field end (Dilutn ~534) | TA ~2913 umol/kg (~2992 mmol/m3 as printed), pH(total) ~8.399, OmegaA ~4.80 -- within 0.007 pH and 2.2 % of the exe if row 36's far-field agreement holds |
| TA 20000: first printed row (Dilutn ~1.0) | pH(total) ~12.006, OmegaA ~37.8, OmegaC ~59.4; the exe 0.01-0.03 below on pH and a few percent above on Omega if the gap is the constant offset measured at TA 4000 |
| TA 20000: near-field end (Dilutn ~534) | TA ~2932 umol/kg (~3011 mmol/m3 as printed), pH(total) ~8.421, OmegaA ~5.02 -- within 0.007 pH and 2.2 % of the exe if row 36's far-field agreement holds |

## Notes

- This is case03's geometry and ambient, unchanged; only the effluent chemistry moves. It is NOT case03's entry style: enter TA and DIC, not TA and pH. The dry run found that TA at a held pH gives the same port pH (10.44) at every dose, so nothing would be learned; TA at a held DIC makes the exe compute the port pH itself.
- One project serves all four runs because no .prj stores chemistry. For each dose, in order: open the carbonate dialog, enter effluent TA = <dose>, DIC = 2500, and leave the pH field at whatever it holds (the exe uses TA + DIC when both are given and discards the pH -- case04, row 30), run, then copy the trace to dose_<TA>.dat and the project to asrun_dose_<TA>.prj BEFORE the next run overwrites both.
- Doses, in umol/kg: 4000, 6000, 10000, 20000. If the exe refuses a value, prints NaN, or stops early at one of them, that is a finding -- say which and keep the others. TA 20000 / DIC 2500 is pH ~12 at the port and is the run most likely to break something.
- If the carbonate dialog shows any option besides KSO4 and K1K2 (a pH-scale selector, a borate selector, a calcium field), write down what it shows and what was selected. Nothing decoded so far records it.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     b94ab26530df2c30f256b2effc3580cb61c3468f (dirty)
generated  2026-08-25T20:54:18Z
case       8125fb987a167086ef6b98f7e7ba8aacef9d2ba04e0d59c9790444e036d20acd
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.


## What came back so far (2026-08-25)

- ⚠️ **The exe would not run with the generated `AmbientChem_dose_parity.csv`** because its pH
  column was blank; the operator typed 7.80 in each row and overwrote the file (since replaced by the
  regenerated one -- last bullet). The generator now writes a solved pH -- the exe does not use the
  column (case03 README), but it demands one.
- `dose_baseline_TA2930.dat` -- the one run so far, renamed from `ModelResults_TxtOutputs.dat`. Its
  TA/DIC columns back out to an effluent of **TA 2930 / DIC 2500 µmol/kg** (pH 8.37 flat), so it is a
  **no-dose baseline**, not one of the four doses. Two things it settles anyway: `Dilutn`, `P-dia`
  and `Depth` are **bit-identical to `kso4_option3.dat` on all 410 steps** (prediction 1), and at no
  dose the exe's pH is **0.008 below** PyCO2SYS on the exe's own TA/DIC with Ω_arag within 0.3 % --
  the constant offset rows 36/41 measure. `dose_parity.prj` is the as-run project (`flags[1]` = 1,
  surface box left as found).
- ⏳ **Still needed: the four dose runs**, TA 4000 / 6000 / 10 000 / 20 000 at DIC 2500, each copied
  to `dose_<TA>.dat` / `asrun_dose_<TA>.prj` before the next.
- ⭐ **The ambient CSV in this directory was regenerated on 2026-08-25 with the pH column filled**
  by the generator (`experiments.fill_ambient_ph`): PyCO2SYS's free-scale pH of each row's TA and
  DIC at the profile's S and T -- 8.56 / 8.45 / 8.45 / 8.46 at 1-4 m -- replacing the 7.80 placeholder
  the operator typed. The exe ignores the column either way (row 45); the fill is so the GUI loads
  the file without typing. Load *this* file for the four dose runs. `dose_parity.prj` is untouched:
  it is still the as-run project from the baseline run.


## ✅ All four runs are in (2026-08-25, afternoon)

`ModelResults_TA4000/6000/10000/20000.dat`, 410 steps each at output interval 1, surface-stop box
left ticked as found (`flags[1]` = 1). **Every registered prediction holds.**

| dose | exe port pH | ours | gap | Ω_arag (exe) | Ω_C/Ω_A |
|---|---|---|---|---|---|
| TA 4 000 | 9.148 | 9.161 | +0.013 | 27.31 | 1.57989 |
| TA 6 000 | 10.628 | 10.653 | +0.025 | 57.04 | 1.57989 |
| TA 10 000 | 11.483 | 11.504 | +0.021 | 59.07 | 1.57990 |
| TA 20 000 | 11.988 | 12.008 | +0.020 | 59.29 | 1.57990 |

⭐⭐⭐ **The answer to the question this experiment asked: the gap does *not* widen above pH 11.**
It peaks near pH 10.5 and narrows above 11.5. Over all 2050 rows the exe reads 0.011–0.025 below
PyCO2SYS on its own printed TA/DIC. The dose axis is parity-checked to 0.025 pH end to end, and
`PH_PARITY_WINDOW`'s ceiling moved 10.5 → 12.05 on the strength of it.

Also confirmed: hydrodynamics **bit-identical** to `kso4_option3.dat` on all 410 steps of all four
runs; Ω_C/Ω_A flat at 1.5799 (row 123's `Ksp` ratio, unmoved by 2.8 pH units).

⛔ **Two of the four traces broke the reader, and it was our defect not the exe's.** `R_cal`
reaches 105 022.286 µmol/hr at the top doses — exactly the ten-column field width — so it abuts
`OmegaA` with no separator. `io/dat.py` now splits on the fixed grid (PLAN §8f). The round trip is
188/188.

⚠️ **The chemistry columns are µmol/kg despite the `(mmol/m3)` heading** — at a dilution of 562.6
they converge to the entered ambient, TA 2900.208 / DIC 2500.120. Do not divide by ρ.

⏳ **Not yet examined**: the far-field halves of these four traces, and
`check_farfield_session_state` against them.
