# limspc_deep_control

**Question.** Control: with the threshold moved out of reach, does the banner disappear?

## Run it

1. Open `limspc_deep_control.prj` in the exe. **Do not open a hand-maintained
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
| port depth / elevation | 5 m / 15 m |
| total flow | 0.005 m3/s |
| effluent | 35 psu, 10 C |
| ambient current | 0.02, 0.05 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.20` for 0.2 and `Ttl-flo 0.01` for 0.005. Read inputs from the `.prj`, never the echo.

## Predicted, before the run

| observable | port predicts |
|---|---|
| `merging happened` banner | **NO** -- our max diameter is 7.2 m against a 10 m threshold, a 28 % margin |
| max plume diameter | ~7.2 m |
| termination | 4th turning point (no boundary hit; 20 m column) |

## Notes

- UM3 sets a limiting spacing equal to the port depth once the element diameter exceeds **twice the port depth**, and -- with no port-count guard -- declares the plume MERGED at the same moment. These two runs are a **single port**, where merging is otherwise impossible, so a `merging happened` banner can only come from that rule.
- Everything is identical between the two runs except the port depth, which moves the threshold from 2 m to 10 m of diameter.
- The discharge points **downward** (-45 deg) so the plume sinks away from the surface and can grow wide while staying well submerged -- the threshold is otherwise reached only as the plume surfaces, where the two effects cannot be told apart.
- This is the control. If it *also* merges, the trigger is not 2 x port depth and the pair says so.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     b79f9a8a16cc1055d3b17156c2dc1557403ed5fb (dirty)
generated  2026-08-13T20:17:14Z
case       8cc1dbcfe136f15999b4fd6e65655048ce6f36c46fc7121897998968628f1605
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 5 m port** or the exe refuses to run.
