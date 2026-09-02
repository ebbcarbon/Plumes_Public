# farfield_bod

**Question.** Does the far-field DO sag follow eqs 28-30 as written? Four things in them have no reference data at all, because no archived run produces a far-field table with BOD active: whether the 5-day BOD is converted to an ultimate demand, whether the ambient BOD is subtracted as a 5-day or an ultimate figure, whether the typed decay rates are 20 C values that get theta-corrected, and whether the demand is divided by the near-field dilution as well as by the Brooks factor.

## Run it

1. Open `farfield_bod.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry:

   - output interval 1
   - all output columns, including DO
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: unticked
   - Dissolved Oxygen Calculations: TICKED -- the point of the run

3. Run, and save the `.dat` **and** the `.prj` as it stood at run time.

⚠️ If the GUI resets the project on exit, save the `.prj` before closing it. A stale
project file is worse than none: test34/test35 came back describing a different run.

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
| near-field DO at the transition (every run) | 7.975 mg/L |
| near-field dilution there (eq 28's D) | 237.7 |
| plume temperature there | 9.21 C |
| F1 DO at 102 m, the chronic mixing zone | **7.929** mg/L if the rates are theta-corrected to the plume temperature; **7.919** if they are used as typed |
| F1 DO at the last row (501 m) | **7.869** corrected / **7.845** as typed |
| F1 total sag at the last row, against no demand at all | 0.1192 mg/L (so a run showing no sag at all refutes eqs 28-30 outright) |
| F2 DO at 102 m | 7.938 mg/L |
| F2 vs F1 at the last row | +0.0233 mg/L -- the two channels differ only through their default rates, so an identical pair means the rates are shared |
| F3 DO at the last row | **7.899** if the ambient BOD is converted to ultimate before subtraction; **7.884** if the 5-day figure is subtracted directly |
| ultimate cBOD (eq 24), corrected / as typed | 3970.8 / 2926.7 mg/L (k_c = 0.1401 / 0.23 per day) |

## Notes

- ⚠️ THREE RUNS FROM THIS ONE PROJECT. The Dissolved Oxygen tab is not saved in a `.prj` (manual 5.2.6), so the project cannot distinguish them -- only the DO tab changes, and it has to be recorded by hand or the traces are uninterpretable. `AmbientDO_F1_F2.csv` and `AmbientDO_F3.csv` are in this directory and can be **loaded** rather than typed.
- **Run F1 (carbonaceous alone).** Effluent DO 2.0, IDOD 0, cBOD5 **2000**, nBOD5 **0**, cBOD decay 0.23/day, nBOD decay 0.1/day (the documented defaults -- please confirm what the dialog actually shows). Ambient: load `AmbientDO_F1_F2.csv` (DO 8.0 everywhere, both ambient BODs zero).
- **Run F2 (nitrogenous alone).** Identical, except effluent cBOD5 **0** and nBOD5 **2000**.
- **Run F3 (the ambient subtraction).** Identical to F1, except load `AmbientDO_F3.csv`, which sets ambient cBOD5 to **500** at every depth.
- ⚠️ **The far field is the entire point.** Please confirm each trace actually has a far-field table rather than only the 'Brooks method may be overly conservative' note. This 18-port, 8 MGD, 11 m-deep geometry is the one that demonstrably produces one -- the Macoma 25-port geometry never does, which is why case24's five runs could not answer this.
- ⚠️ **cBOD5 of 2000 mg/L is diagnostic, not realistic.** Eq 28 divides the demand by the near-field dilution of 238, so at a realistic 20 mg/L the entire sag would be 0.0013 mg/L -- under three times the printed precision, i.e. unmeasurable. At 2000 the sag is 0.13 mg/L and the temperature question separates by 0.025, both comfortably readable at three decimals. If the exe rejects a value this large, halve it and say so: the predictions scale linearly with it.
- The ambient DO is deliberately **uniform at 8.0 mg/L**, which makes the near-field column a clean control: with a flat ambient the path integral we measured from case24 collapses to the manual's algebraic eq 23, so the near field should reproduce `8.0 + (2.0 - 8.0)/D` exactly, giving 7.975 at the transition.
- Each far-field prediction is given as a **pair** wherever the reading is ambiguous. The pairs are far apart compared with the printed precision, so the trace picks one.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     7b1c3ac7849cf37343e5ea156c2f5cc5f7148106 (dirty)
generated  2026-08-17T21:58:39Z
case       8d220d4ea0f6c326f5f6a714fa844635e80fa041829c1dc3933359cbb5d9ef39
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 11 m port** or the exe refuses to run.
