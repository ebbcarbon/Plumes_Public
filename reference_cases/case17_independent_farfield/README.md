# case17 — the exe's own far-field calculator, run standalone (IndpFarfieldCalc1.TXT)

⚠️ **Written 2026-08-21, long after the run.** This directory held one file and no write-up; what
follows is reconstructed from the file and the two places `validation.py` reads it.

**Not a near-field run at all.** PLUMES2.0 ships a standalone Brooks far-field calculator that takes
a wastefield width, an initial dilution, a current and a dispersion `alpha`, and integrates the
4/3-power-law solution on its own. This is one run of it:

| input | value |
|---|---|
| wastefield width | **50.00 m** |
| eddy diffusivity | **4/3 power law** |
| dispersion `alpha` | **0.0003** |
| far-field current | **0.0500 m/s** |
| initial dilution | **100** |

and it prints dilution, width, distance and time on an 8 m distance grid.

## ⭐⭐ Why this is the most valuable single file in the archive for phase 3

**It is the only place the exe's far field is observable without the near field in front of it.**
Every other far-field number in the archive is downstream of a near-field trajectory, so a
disagreement could belong to either half. Here the inputs are typed and the output is pure Brooks —
so `farfield/brooks.py` can be checked against the exe's *own* implementation with nothing else in
the way.

**That test passes exactly.** It is the source of the 4.8×10⁻⁴ figure quoted in
`PORTING_THE_PHYSICS.md`: our Brooks integration reproduces this table to within a fraction of the
printed resolution, which is what licenses treating far-field residuals elsewhere as near-field
handoff problems rather than Brooks problems. `farfield/standalone.py` exists to parse this format
and its module docstring carries the result.

⭐ It also supplies the **`initial_dilution = 100`** convention: the calculator is fed a round 100,
so the dilution column is readable directly as a multiplier on the near-field value.

## ⚠️ What it does not do

- **No `.dat`, no near field, no `.prj`.** It is a `.TXT` in the calculator's own format, which is
  why it is invisible to every archive-wide sweep that globs `*.dat` — including the width and EOS
  measurements. That is correct, not an oversight, but it is worth knowing when a sample count looks
  short.
- **One parameter set.** The `alpha` and the current are single values, so nothing here tests the
  `alpha` dependence; row 30's law and the archive's own far-field tables do that.
