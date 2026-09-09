# case18 — the Phase 5 isolation set (test21–test26)

Six **old-build** runs generated 2026-08-12 to close the near-field unknowns, all at
**output interval 1** (consecutive steps) with **all output columns enabled**, which is what
makes them usable: `Time`, `P-Den`, `P-Sal`, `P-Temp` and position together.

None of them merge — the plume diameter never reaches the 2.0 m port spacing — so the
merging correction is absent from all six and cannot contaminate the entrainment fit.

| run | ports | ambient current | contraction | flow (m³/s) | rows | purpose |
|---|---|---|---|---|---|---|
| test21 | 25 | 0.02 m/s | 0.61 | 0.005 | 420 | baseline for the set |
| test22 | 25 | **0** | 0.61 | 0.005 | 666 | forced entrainment off |
| test23 | **1** | **0** | 0.61 | 5e-5 | 732 | Taylor entrainment alone |
| test24 | **1** | 0.02 m/s | 0.61 | 5e-5 | 365 | single-port `A_p` partner to test23 |
| test25 | **1** | **0** | **1.0** | 5e-5 | 768 | contraction partner to test23 |
| test26 | 25 | 0.02 m/s | **1.0** | 5e-5 | 512 | contraction at 25 ports |

`Amb-cur` is the near-field current; the far-field speed stays at 0.02 m/s because the exe
will not accept zero there. All six use the case03 ambient profile, a 0.0127 m port at
45° vertical / 90° horizontal, 2.0 m spacing, 2 m port depth, 15 m port elevation, and
effluent at 35 psu / 10 °C.

## Why the zero-current runs matter

Setting the ambient current to zero makes the forced-entrainment term of the manual's eq 2,
`−ρ_a A_p·U_a`, vanish **identically**. What is left is Taylor entrainment, which the manual
fully specifies. So test22 and test23 validate the whole solver *except* the one term the
manual defers to Frick (1984) for — and test23 does it with a single port, so merging is
impossible rather than merely absent.

Differencing test23 against test24 (identical but for the current) isolates `A_p` itself.

## What they established

- **The Taylor coefficient is the value entered.** Reducing eq 2 to a specific rate,
  `d(ln D)/dt = 2α(ρ_a/ρ_j)|U_j|/b`, and solving for α gives **0.0967 ± 0.0006** (test22)
  and **0.0991 ± 0.0013** (test23) against the project file's 0.1.
- **The contraction coefficient is the vena contracta.** test23 against test25 differ only
  in it, and their step-1 plume diameters are 0.010 and 0.013. So the initial jet *area* is
  `c` times the port area, giving `b_0 = (d/2)√c` and `|U_0| = Q/(n c A)`. Those cancel in
  `b_0²ρ_e|U_0| = ρ_e Q/(nπ)`, and the pair's measured constants indeed agree to 0.25 %
  across a 64 % change in `c`.
- **The element-thickness law `h ∝ |U_j|`** holds here as it does on test19, to within 1 %.

## ⚠️ Two rounding traps in the `.dat` echo

The **diffuser echo prints two decimals**, so its `P-dia` of `0.01` is really 0.0127 and its
`Ttl-flo` of `0.01` in (cms) is really 0.005 — both the archived-diffuser baseline. Only the
*simulation results* table prints three decimals. Both traps bit during this analysis: the
flow one produced an apparent factor-of-2 discrepancy in the Taylor coefficient, and the
diameter one initially hid the contraction relation. **Read inputs from the `.prj`.**

## `test21.prj` — the baseline project, and a confirmation

`test21.prj` is archived here and round-trips byte-exactly (7016 bytes). It is identified as
**test21's configuration by its values, not by its timestamp** — the exe's save timing is
not something to rely on. It matches test21's echo on every field, including the distinctive
0.05 m/s bottom-level current, and it cannot describe test22–test26, which differ in port
count, ambient current or contraction. So it pins the *baseline*, and the variants' own
settings remain measurements anchored to it.

It also arrived *after* the analysis above, which makes it a clean check on trace-only
reasoning. Four values had been inferred from the traces alone:

| quantity | inferred from | `.prj` |
|---|---|---|
| port diameter 0.0127 m | the test23/test25 contraction pair | ✅ 0.0127 |
| effluent flow 0.005 m³/s | the measured thickness constant | ✅ 0.005 |
| Taylor α = 0.1 | zero-current entrainment | ✅ 0.1 |
| contraction 0.61 | the step-1 diameters | ✅ 0.61 |

All four matched exactly. It also confirms `output_interval = 1` and the max-rise-or-fall
switch at 3, and gives the aspiration coefficient directly rather than by assumption —
closing PLAN.md §7 Trial D for this set.
