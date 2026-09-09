# case25 — the far-field DO sag (ModelResults_1 to _3)

The first runs in the archive whose **far field executes with BOD active**, generated from
the generated experiment `farfield_bod` on 2026-08-17 (note: [`EXPERIMENT_NOTE_farfield_bod.md`](EXPERIMENT_NOTE_farfield_bod.md)). They settle two of the four open questions
about eqs 24–30 and leave two open for a reason worth recording.

⚠️ **New build, so the output columns are reduced** — the near field prints six
(`Dilutn`, `P-dia`, `x-posn`, `y-posn`, `Depth`, `DO`) rather than the thirteen the old build gives.
No `Time`, `P-Sal` or `P-Temp`, so these traces cannot be sampled at the exe's own times the way the
near-field validation targets do. The far field prints `Dilution`, `Width`, `Distance`, `Time`
(hrs.), `DO`.

## The runs

All three share the project (`farfield_bod.prj`: 18 ports, 8 MGD, 11 m port depth, the upstream
example geometry) and effluent DO 2.0 mg/L with IDOD 0. Only the DO tab differs, and it is not saved
in any file — **the near-field DO column is the only way to tell the three apart**.

| trace | ambient DO | ambient cBOD5 | identified by |
|---|---|---|---|
| `ModelResults_1.dat` | **8/9/10/9/8** at 1/3/6/10/12 m | 0 | near-field DO reaches 9.486, above 8.0 |
| `ModelResults_2.dat` | uniform **8.0** | 0 | near-field DO tops out at 7.965 |
| `ModelResults_3.dat` | uniform **8.0** | **500** | DO *rises* to 15.532 |

⚠️ **Run 1's ambient DO is not what the experiment asked for.** `AmbientDO_F1_F2.csv` was not loaded
for it, so the DO tab still held the previous `testDO.csv` profile. Recovered from the trace rather
than assumed: forward-modelling the path integral on 8/9/10/9/8 reproduces its DO column to
0.038 mg/L, where the uniform 8.0 it was supposed to have would be out by 1.545. The run is still
useful — see below — it just answers a different question than intended.

## What they establish

1. ⭐ **A third geometry confirms the path integral.** Run 1's near-field DO follows
   `d(DO·D)/dD = DO_a(z)` on the 18-port, 8 MGD, 11 m-deep geometry that surfaces — against
   case24's two archived-diffuser geometries. Its residual is 0.038 mg/L, larger than case24's 0.006 because
   this profile has kinks at 3, 6 and 10 m that the plume crosses and a trapezoid over printed rows
   smooths.
2. ✅ **With a uniform ambient the path integral collapses to the manual's eq 23 exactly**, as
   predicted. Runs 2 and 3 match `8.0 + (2.0 − 8.0)/D` to **0.0078 mg/L past `D` > 5**. This was
   stated in advance in the experiment note and is the cleanest confirmation of the reconciliation
   between this module and the algebraic carbonate mixing of ledger row 39.
3. ✅ **BOD does nothing in the near field even at cBOD5 = 2000 mg/L**, confirming case24's
   byte-identical pair at a hundredfold larger load.
4. ✅ **Eq 30's demand term carries `1/FF`.** In the linear regime `sag·FF/t` should be the constant
   `L·k`, and it is: **16.601 ± 0.135** for run 2 and **−149.354 ± 1.219** for run 3, both a spread
   of 0.8 % over 494 rows. A demand term without the `1/FF` would not give a constant.
5. ✅ **The far field starts exactly where the near field ended.** The first far-field row reports
   `Dilution` = 169.754 = the near field's last `Dilutn`, so `FF` = 1 at the transition.
6. ⭐⭐ **Eqs 28–29 as written are refuted.** `L_f = (BOD_Le − BOD_La)/D` is *positive* for run 3
   (2000 against 500), so it must depress oxygen. Run 3's DO instead **rises to 15.532 mg/L**, far
   above its 8.0 ambient, and `L·k` comes out at **−149**, not +3. Only a form that subtracts the
   ambient BOD **undiluted** — `BOD_Le/D − BOD_La` — has the right sign and the right order of
   magnitude (−112 to −164 depending on the rate). A plume that gains oxygen as it travels through
   water with a high oxygen demand is not physical; this looks like a genuine exe defect and should
   go on the report-to-SSMC list.

## What they do not establish, and why

⚠️ **`L` and `k` cannot be separated from these runs — a flaw in the experiment design, not in the
data.** The far field spans only 2.74 hours, so `k·t ≤ 0.026` and `1 − e^{−kt}` is linear in `t` to
within 1.3 %. Only the product `L·k` is identifiable, which leaves all three of these entangled:

- whether the 5-day BOD is converted to an ultimate demand (eqs 24–25),
- whether the typed rates are 20 °C values corrected by θ (eqs 26–27),
- and what exactly divides the demand.

⚠️ **And the magnitude is not yet explained.** Run 2's `L·k` = 16.60 against 2.7–4.0 for every
candidate reading — a factor of 4 to 6 unaccounted for. So something in eqs 28–30 is still not
understood, and it is not a small correction.

**What would settle it:** the same three runs with the far-field current reduced from 0.05 to about
0.002 m/s, or the maximum distance raised well past 500 m. Either lengthens the travel time enough
for the exponential to curve, which separates `L` from `k` and turns the unexplained factor into a
measurement. The near-field half of the module is unaffected either way — it is already validated to
0.006 mg/L on three geometries.
