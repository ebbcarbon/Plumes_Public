# case24 — dissolved oxygen (test36–test40)

Five runs supplied 2026-08-17 to unblock `biochem/do_bod.py`. **New build**, output interval 1, all
output columns. They settle the near-field mechanism outright and leave the far field untouched.

⚠️ **The Dissolved Oxygen tab is not saved in the `.prj`** (manual §5.2.6, the same gap the
carbonate tab has — PLAN.md §7b). So the effluent inputs below are recorded here **because the user
wrote them down**, and without this file the traces are uninterpretable. The ambient side is
recoverable: it is `testDO.csv`.

## The runs

| run | what it is | rows | DO column | chemistry | notes |
|---|---|---|---|---|---|
| `test36.dat` | baseline, no DO | 526 | — | — | 25 ports at 1 m, H-angle 175°; merges, surfaces |
| `test37.dat` | + DO | 526 | ✅ | — | hydrodynamics identical to test36 |
| `test38.dat` | + DO **and** carbonate | 526 | ✅ | ✅ | hydrodynamics identical to test36 |
| `test39.dat` | DO, cBOD5 zeroed | 420 | ✅ | — | 25 ports at 2 m, H-angle 90°; **does not merge** |
| `test40.dat` | DO, nBOD5 zeroed | 420 | ✅ | — | **byte-identical to test39** |

test39/test40 are the **case01 geometry**: their final flux-averaged dilution and diameter are
387.996 and 1.967, which is ledger row 21 exactly. So they are the archived baseline with DO turned
on, and they give a DO column on a trajectory whose hydrodynamics are already validated.

## Effluent DO inputs (user-supplied, not in any file)

| input | test37, test38 | test39 | test40 |
|---|---|---|---|
| effluent DO | 2 mg/L | 2 mg/L | 2 mg/L |
| IDOD | 0 | 0 | 0 |
| effluent cBOD5 | (not recorded) | **0** | 20 mg/L |
| effluent nBOD5 | (not recorded) | 30 mg/L | **0** |
| cBOD decay rate | 0.23 /day | 0.23 /day | 0.23 /day |
| nBOD decay rate | 0.23 /day | 0.23 /day | 0.23 /day |

⚠️ **The nBOD decay rate is 0.23, not the documented default of 0.1** — changed by accident and
noticed afterwards. It makes no difference to these five traces, because the near field ignores BOD
entirely (below), but any future run that reaches a far field must have its rates recorded.

## Ambient profiles

`testDO.csv` — `depth, DO, cBOD5, nBOD5`:

| depth (m) | 1 | 3 | 6 | 10 | 12 |
|---|---|---|---|---|---|
| DO (mg/L) | 8 | 9 | 10 | 9 | 8 |
| cBOD5 | 5 | 5 | 5 | 4 | 4 |
| nBOD5 | 6 | 6 | 6 | 4 | 4 |

`testC.csv` — `depth, TA, DIC, pH, ?` — TA is **3000 at 1, 3 and 6 m**, i.e. constant across every
depth these plumes traverse. That fact is what reconciles the DO finding with ledger row 39; see
below.

## What they establish

1. ✅ **DO is a pure overlay.** All thirteen shared columns of test36, test37 and test38 are
   identical over all 526 rows. DO does not feed back on the hydrodynamics, and neither does DO plus
   chemistry together. (Ledger row 215.)
2. ⚠️ **The manual's DO/pH exclusion is not enforced.** §5.2.6 says the two "cannot be conducted
   simultaneously"; test38 does both, and its DO column matches test37's exactly. (Row 216.)
3. ⭐⭐ **The entrained ambient is path-integrated, not evaluated at the plume's depth.** Algebraic
   eq 23 misses the printed DO column by 0.218 mg/L on test37 and 0.171 on test39 — 435× and 341×
   the printed precision — however `DO_a` is chosen. Integrating along the trajectory,
   `d(DO·D)/dD = DO_a(z)`, fits **both** to 0.0064 mg/L (12.8×, and 7× past `D > 5`), which is the
   floor for reconstructing an integral from printed rows. Two different geometries, one merging and
   one not, same model and same seed. (Row 214.)
4. ✅ **The seed is `DO_e − IDOD` exactly.** Measured 2.00022 on both runs; the user's inputs are
   `DO_e` = 2 and `IDOD` = 0, and `2 / 1.020 = 1.96078` prints as the observed `1.961`.
5. ✅ **Both BOD channels are inert in the near field.** test39 (cBOD5 0, nBOD5 30) and test40
   (cBOD5 20, nBOD5 0) are **byte-identical**. This is exactly what the 3rd edition predicts: "on
   this time scale chemical and biological demands in the ambient are inconsequential although for
   farfield water quality considerations after initial dilution they are frequently decisive."

## What they do not establish

**Everything downstream of initial dilution.** None of the five runs produced a far-field table —
test36/37/38 end on `Plume traps` and test39/40 print only the unmerged Brooks advisory — so eq 30
and the whole sag calculation (eqs 24–29: the 5-day → ultimate conversion, the θ temperature
correction, and `FF`) have **no reference data at all**. One run whose far field executes, with a
non-zero effluent cBOD5, would settle all of them at once. Until then `do_bod.py`'s far-field half
is implemented from the manual and marked unevidenced.
