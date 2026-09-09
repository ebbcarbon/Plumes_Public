# subcritical_sinks

**Question.** Does the exe fail on sub-criticality itself, or on leaving the water column? case29's three arms (2/0/10 psu, F ≈ 0.003) all rose, breached the surface, and went NaN — so they cannot tell the two apart. This arm is identical except the effluent is 45 psu: dense, so it sinks toward a seabed 15 m below and, the port says, traps near 5 m without ever nearing the surface. A finite full-length trace clears sub-criticality (the NaN cliff is the missing surface clamp, as case09 suggests from the momentum extreme); NaN on a submerged plume convicts it.

## Run it

1. Open `subcritical_sinks.prj` in the exe. **Do not open a hand-maintained
   project** -- this file exists so none has to be touched.
2. Set these in the GUI, which the `.prj` cannot carry (the output interval is **already 1** in the file, and needs no typing):

   - all output columns (already named in the generated .prj)
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked (it should never fire; that is part of the point)
   - stop plume at surface hit: leave as loaded
   - no chemistry, no DO — the carbonate tab stays off
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
| port diameter | 0.5 m |
| vertical angle | 45 deg |
| horizontal angle | 90 deg |
| port depth / elevation | 2 m / 15 m |
| total flow | 0.005 m3/s |
| effluent | 45 psu, 10 C |
| ambient current | 0.02, 0.05 m/s at 90 deg |
| discharge-to-current offset | 0 deg |

⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print
`P-dia 0.50` for 0.5 and `Ttl-flo 0.01` for 0.005. Read inputs from the `.prj`, never the echo.

## Predicted, before the run

| observable | port predicts |
|---|---|
| NaN | none, anywhere. The plume never approaches depth zero, so the missing surface clamp never engages. If NaN appears anyway, sub-criticality itself breaks the exe and case29's mechanism story is wrong |
| trajectory | monotonic sinking to a deepest point near 5.3 m (the exe prints Depth ≈ -5.3) around t ≈ 160 s, then a small rebound and trapping — buoyancy-trapped in the stratification, nowhere near the 17 m seabed |
| termination | the rise/fall count (3), on `Local maximum rise or fall` / `Plume traps` banners — NOT `Plume hits the bottom` (13+ m short) and NOT the surface |
| final dilution | 600-700 (the port says ~640). The run merges at d/L ~1 and ends at d/L ~1.6, inside the post-merge 1-7 % band's shallow end; the slow 0.02 m/s current also invites the ~5 % post-trapping suppression (test23) |
| merging banner | `merging happened`, near the diameter = 2 m spacing crossing (port: t ≈ 91 s, depth ≈ 4.9 m). 25 ports, so record the step — the single-port banner-lag regimes (row 191b) should not apply here |
| far field | present, from the ~5 m trapping depth; the 500 m distance stop binds (the port reaches dilution ~5 700 at 500 m, under the 10 000x cap). Check the return with check_farfield_session_state — case47 declared 10 000x and came back at 5 000x |
| the port's own integration | sinks from the 2.0 m port to a deepest 5.33 m at t = 163 s (dilution 534), rebounds ~0.4 m and oscillates; `oscillation limit` at t = 244 s, flux-averaged dilution 640. It merges (2 m spacing) at t = 91 s, depth 4.88 m, dilution 369 |
| Froude | F ≈ 0.0044 (exit velocity 0.001019 m/s through the 0.5 m port, g' ≈ 0.108 m/s² against the surface ambient) — the same three-orders-below-threshold regime as case29, on the sinking side. The port's DesignWarning fires |

## Notes

- ONE run. Copy the .dat and the as-run .prj aside before anything else runs — case29 is only interpretable because the diameter happened to survive the echo; this time the project is written from the case and the run re-saves it, closing that gap by construction.
- Identical to case29's test41/42/43 except effluent salinity 45 psu (they ran 2, 0 and 10). The generated .prj already carries the 0.5 m port, the 0.005 m³/s flow and the 45 psu effluent — nothing about the discharge needs typing.
- The 17 m seabed / 15 m profile shape is the archived projects' convention and intentional (operator, 2026-09-01); the port's GeometryWarning is a statement of extrapolation, not a suspicion.
- WHICH EXE BUILD did this run: write down which executable was launched, and from where. Nothing in the .prj or the .dat records it, and the far-field wastefield width is the after-the-fact fingerprint (row 275). Legacy build is fine here — the operator prefers it for physics without chemistry — but the answer has to be written down.

## Provenance

What generated this experiment. The `.prj` cannot carry any of it -- it has no field
for a version, a commit or a date -- so it lives here (PLAN.md section 7b).

```
plumes2    0.0.1.dev0
commit     6c8f21596da5b7a78653372128f82a20fec20deb (dirty)
generated  2026-09-02T16:37:40Z
case       270dc104b042baef23108cc7533ca6e44c141e30b649bee8455ba7da47cf63c2
python     3.14.4
platform   Windows-11-10.0.26200-SP0
```

`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is
ever regenerated from a different case, that digest changes and the two stop agreeing.

## Chemistry

Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has
to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than
the 2 m port** or the exe refuses to run.
