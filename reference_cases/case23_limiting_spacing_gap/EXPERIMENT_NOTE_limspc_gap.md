# limspc_gap

**Question.** Is the limiting-spacing check continuous, or only reached at trapping?

## Run it

1. Open `limspc_gap.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry:

   - output interval 1
   - all output columns
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: unticked

3. Run, and save the `.dat` **and** the `.prj` as it stood at run time.

⚠️ If the GUI resets the project on exit, save the `.prj` before closing it. A stale
project file is worse than none: test34/test35 came back describing a different run.

## What is in the case

| ports | 1 |
|---|---|
| port spacing | 0 m |
| port diameter | 0.2 m |
| vertical angle | -45 deg |
| horizontal angle | 90 deg |
| port depth / elevation | 2 m / 15 m |
| total flow | 0.005 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02, 0.05 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.20` for 0.2 and `Ttl-flo 0.01` for 0.005. Read inputs from the `.prj`, never the echo.

## Predicted, before the run

| observable | port predicts |
|---|---|
| if the check is CONTINUOUS | a `merging happened` banner **late**, at diameter ~4.0-4.6 m, long after the first trap |
| if the check is GATED ON TRAPPING | **no banner at all** -- the plume traps at ~2.1 m, only about half the 4.0 m threshold, and the condition is never re-tested |
| first trap | diameter ~2.1 m (ratio ~0.5 of the 4.0 m threshold), around step 160-180 |
| max diameter | ~5.6 m expected (the port over-predicts this by roughly half, reading 8.7 m), so the threshold is crossed with margin |
| termination | 4th turning point |

## Notes

- case22 left exactly one ambiguity. Its shallow run fired the banner at diameter 2.277 m for a 1 m port -- a ratio of 2.28, not the 2.00 the source implies -- and `Plume traps` fired at the SAME step, so 'threshold is 2.28x' and 'the check is only reached at trapping' both fit.
- This run separates them by making the plume trap at about **half** the threshold and cross it much later. A continuous check must fire late; a trapping-gated one must never fire.
- If a banner does appear, the diameter at it calibrates the constant directly: 4.00 m means 2.00x port depth, 4.55 m means 2.28x.
- Single port again, so a banner can only come from this rule.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     4adeb837a3ce8d195ab87e962bd97bc651ed55d0 (dirty)
generated  2026-08-13T20:26:43Z
case       6db83479e40213dcd9f7304ccd68ff2c26be8d8ffa1208bcc449da38e5dedcdf
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
