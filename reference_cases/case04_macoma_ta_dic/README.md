# case04 — the TA + DIC diagnostic run

Pulled 2026-08-12 10:51 from `C:\Users\jerem\Documents\Plumes\Macoma\` (note: the
parent folder, not `Macoma2\`). Same project as
[case03](../case03_macoma_carbonate/) with only the chemistry entries changed.

| File | Role |
|---|---|
| `test3_TxtOutputs.dat` | **golden trace**, 41 near-field rows × 13 cols |
| `testco2.csv`, `testdiffuser.csv`, `macoma2*.csv` | inputs, carried over from case03 and verified against the `.dat` echo |

No `.prj` — the project was re-run with a changed output filename and not re-saved.
Settings are otherwise case03's, and chemistry is never saved in the `.prj` anyway.

Entered chemistry: **TA 4000, DIC 1646, pH 11** (µmol/kg; pH free scale),
K1K2 = 10, KSO4 = 1. You noted the GUI **cannot** accept a blank field, and errors
on one, so all three had to be filled.

> Housekeeping: `test2_TxtOutputs.dat` in the same parent folder is byte-identical
> to `test3_TxtOutputs.dat` and is a duplicate of this run — not of case03, whose
> `test2_TxtOutputs.dat` lives in `Macoma2\` and differs. Only `test3` is kept here.

## Result 1 — the exe prefers TA + DIC, and ignored pH

Hydrodynamics and the **entire TA column** are bit-identical to case03. Only DIC,
pH, Ω and the rates changed. Fitting the endmembers by conservative mixing:

| | entered | transported | ratio |
|---|---|---|---|
| TA effluent | 4000 | **4110.16** | 1.027540 |
| DIC effluent (case03, `DIC=0`) | — derived from pH 10.5 | 1645.18 | — |
| DIC effluent (case04, `DIC=1646`) | 1646 | **1689.39** | 1.026361 |
| TA / DIC ambient | 2900 / 2500 | 2900.49 / 2499.91 | **1.0002 / 1.0000** |

The transported DIC tracks the **entered** 1646, so **pH = 11 was ignored**. So the
exe prefers **TA + DIC** when both are valid, and only fell back to TA + pH in
case03 because `DIC = 0` acted as a "not specified" sentinel. Since a blank field is
rejected, **`0` is the way to signal "derive this one"** — worth documenting, because
a user entering a genuine zero-DIC effluent would silently get something else.

## Result 2 — the unit inconsistency is real and quantified

The effluent factor is bracketed by the true seawater density factor:

```
EOS-80 rho(S=35, T=10)/1000 = 1.026952
   required by TA           = 1.027540   (+0.057 %)
   required by DIC          = 1.026361   (-0.058 %)
```

Both within ±0.06 % of it, straddling — so **the effluent endmembers are converted
µmol/kg → mmol/m³ using effluent density**, and the residual scatter is our fit
precision plus the exe's own step-integration drift (see Result 4).

The ambient is **not** converted: it would need 1.023809 at S=31.1/T=10.6, and comes
through at 1.0002.

**So the two endmembers are mixed in inconsistent units.** The effluent is properly
converted; the ambient CSV is taken as already-mmol/m³ despite the GUI labelling
µmol/kg. Net effect: **ambient TA and DIC are ~2.4 % low relative to the effluent.**

Because TA and DIC are biased *together*, the pH error is small (pH keys off the
TA/DIC ratio), but Ω scales roughly with absolute concentration, and the
precipitation rate goes as (Ω−1)^2.87 — so a 2.4 % Ω bias becomes a **~7 % rate
bias** in the diluted plume, which is where the ambient dominates. This is a genuine
exe bug and one we should reproduce-and-flag rather than silently fix.

You confirmed the chemistry dialog's units dropdown has **only one option**, so
this isn't a mis-set control — it's a missing conversion on the ambient path.

## Result 3 — the precipitation rate formula, decoded exactly

Your GUI parameters: `Rate = K·(Ω − 1)^N`, calcite (0<S<44) `logK = −1.06e−1`,
`N = 2.87`. Testing both exponentiation bases against all 41 rows of *both* runs:

| form | K | pred / reported |
|---|---|---|
| `10^logK` | 0.78343 | 0.87104 (mean), 0.8709–0.8712 |
| **`exp(logK)`** | **0.89942** | **1.00000** (mean), 0.99983–1.00016 |

**`R_cal = exp(logK)·(Ω_calc − 1)^N` reproduces the exe exactly** — 5 significant
figures, on both runs independently.

But the field is labelled *log*K, and Zhong & Mucci (1989) tabulate **log₁₀** rate
constants. So the exe applies `exp()` where `10^()` is intended, making the calcite
rate **14.8 % too high** (1/0.871). Unless that GUI field is documented as a natural
log, this is a second bug. Either way we can now reproduce it bit-for-bit.

## Result 4 — TA/DIC are integrated stepwise, not computed from dilution

With ambient endmembers fixed at their entered values, the implied effluent TA drifts
monotonically from 4108.39 (first row) to 4119.23 (last), a 0.26 % spread. Rounding
of the printed values accounts for only ~0.3 of the 11-unit drift, so this is real
non-conservation of ~7 ppm per row in TA.

That means the exe **advects TA and DIC through the LCV step loop** rather than
computing them algebraically from the dilution ratio, and accumulates a little
numerical drift. Small, but it tells us where the code puts the scalar transport —
and it means our `chem/transport.py` should integrate alongside the plume if we want
byte parity, not post-process.

The two-parameter least-squares fit (max residual 1.5 on 4110, i.e. 0.04 %) is the
right way to report the endmembers; the single-row back-calculation is not.

## Result 5 — aragonite: a salinity-band hypothesis

`R_arg` is still **0.000 in every row**. Your GUI shows aragonite parameters as
`logK = 1.53, N = 2.33` and a second band `35 < S < 44: logK = 1.11, N = 2.26`,
while calcite's single band is `0 < S < 44` — which covers everything, and calcite
works.

Plume salinity in this case spans **31.134 – 34.305 psu**, and **0 of 41 rows exceed
35**. With the `exp()` form, the first aragonite band would give R_arg of 6124 → 88
µmol/hr, and the 35<S<44 band 3242 → 53. Both far from zero.

So the leading hypothesis: **the aragonite branch only has coverage for S > 35**, and
returns zero below it. That is directly testable — a run with effluent salinity
raised (say 40 psu) would push plume salinity above 35 and should make `R_arg` come
alive. If it does, it's a clean bug report for SSMC: aragonite precipitation is
silently zero for all brackish and normal-seawater cases.

## PyCO2SYS comparison holds

Same divergence as case03, independently: RMS Δ pH **0.0251**, max **0.0759**
(case03: 0.0253 / 0.0766), over an exe pH range of 8.377–9.929. The bias is a
property of the exe's speciation, not of one particular endmember choice.
