# case39 — the entered spacing is inert on a single port, and the manual's point-source recipe fails

Run 2026-08-19 to test whether the single-port `merging happened` banner is the exe reacting to a
degenerate input. Every single-port run in the archive echoes **`Spacing 0.00`**, and the 3rd
edition (p.61) says a point source is modelled by making the spacing *unreachable*:

> "The default port spacing [spacing] of **1000 m** is acceptable. It means that merging will not
> occur because the plumes will never grow that large and thus UM will run as a **point source
> model**."

**It does not work in this exe.** The hypothesis is refuted.

## ⭐⭐⭐ Spacing 0, 5 and 1000 m give the *same trace*, banner included

`spacing1000.dat` and `spacing5.dat` are `limspc_mid`'s geometry — one port at 0.2 m, downward at
−45° from a 2.4 m port depth — which grows to **4.293 m**, well past the trigger. Against case30's
`gap_1`, the identical run at **spacing 0.00**:

| | `gap_1` | `spacing5` | `spacing1000` |
|---|---|---|---|
| entered spacing | **0.00 m** | **5.00 m** | **1000.00 m** |
| crosses the port depth | step 191 | 191 | 191 |
| `merging happened` | **192** | **192** | **192** |
| rows / max diameter | 576 / 4.293 | 576 / 4.293 | 576 / 4.293 |
| final dilution | 65.213 | 65.213 | 65.213 |

**13 columns × 576 rows, worst difference 0.0** against `gap_1` in both cases.

So on a single port the entered spacing is **completely inert**, and the limiting-spacing rule
fires unconditionally once `diameter > port depth`. A 1000 m spacing does not buy a point-source
model; the plume merges with itself anyway.

⚠️ **This is a manual-versus-exe discrepancy worth reporting.** A user following the 3rd edition's
own instructions to model a single port will get an entrainment suppression they did not ask for
and cannot switch off — worth **2.3× to 6×** in dilution growth rate (row 191n).

## The archived-diffuser control set, and why it could not answer

`test51`–`55` sweep spacing 2 / 5 / 1000 m at 25 and 1 ports on the archived-diffuser geometry, and
they show the *other* half of the same fact: with 25 ports, spacing 5 and 1000 m are numerically
identical; with 1 port, spacing 2, 5 and 1000 m are identical. **13 columns × 5001 rows, worst
difference 0.0** in both groups.

⚠️ But they cannot test the rule. That geometry is buoyant and shallow — the plumes surface at
step 135–257 having reached only **0.613 m** against a 2.0 m port depth, a ratio of **0.31**, where
the trigger needs about 1.0. No banner appears because no plume was ever wide enough, not because
the spacing prevented it. They are kept as the null control they are.

⭐ Their bytes *do* differ, and only because the diffuser echo prints the spacing itself — the same
"the file changes, the numbers do not" pattern as row 191l's column ordering.

## What this leaves

Rows 191b/h/i's three regimes stand, and the degenerate-input explanation for them is gone. The
rule is unconditional; what remains unexplained is only **when** the banner lands, which is where
this investigation was before case39 and is now the whole of it.

## Names (2026-09-09)

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `macoma_test51.dat` → `test51.dat`, `macoma_test52.dat` → `test52.dat`, `macoma_test53.dat` → `test53.dat`, `macoma_test54.dat` → `test54.dat`, `macoma_test55.dat` → `test55.dat`.
