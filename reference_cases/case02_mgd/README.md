# case02 — the archived diffuser, flow reinterpreted as MGD, far-field enabled

Pulled 2026-08-12 10:10 from `C:\Users\jerem\Documents\Plumes\Macoma\Macoma2`.
Same geometry as [case01](../case01_cms/), three settings changed.

| File | Role |
|---|---|
| `test1.dat` | **the golden trace** — 41 step rows to step 410, plus a far-field table |
| `testdiffuser.csv` | diffuser, re-saved for this run (identical values to case01) |
| `effluent.csv` | effluent, unchanged |
| `ambient.csv` | ambient — copied from case01; verified against the `.dat` echo |
| `mixzone.csv` | mixing zone — copied from case01; verified (20.7 / 207 m) |

⚠️ **`test.prj` was written as 0 bytes** for this run. ✅ **Recovered anyway** via
[case03](../case03_carbonate/): that run saved the same project 12 minutes
later and its near-field trace is bit-identical to this one, so the hydrodynamic
settings must match — **aspiration 0.100, contraction 1.000, max rise/fall 3**.

## What changed from case01

| | case01 | case02 |
|---|---|---|
| Flow unit | cms (0.005 m³/s) | **MGD** (0.005 MGD ≈ 2.19×10⁻⁴ m³/s) |
| → effective flow | — | **23× smaller** |
| Contraction coeff. | 0.610 | **1.000** |
| Ambient current @ 15 m | 0.050 m/s (from `.prj`) | 0.020 m/s (matches CSV) |
| Output interval | 5 steps | 10 steps |
| Far-field | not run | **runs**, 100 m interval, 4/3-power law |
| Near-field columns | Dilutn, P-dia, x, y, Depth, P-Den, P-Con., CL-Dil, Time | Dilutn, P-dia, x, y, Depth, **CL-Dil, Amb-Curr**, Time, **Net-Dil** |
| Far-field columns | — | Dilution, Width, Distance, **Bckgrd**, Time |

The unit switch is a genuine physics change, not cosmetic: the same stored `0.005`
becomes a 23× weaker jet. Time to step 10 goes from 0.002 s to 0.081 s, and the
plume behaves quite differently — momentum is now too weak to lift the dense
effluent, so it barely rises (2.0 → 1.980 m) before sinking to 2.335 m.

Two new variable names for the `.prj` name list: **`Amb-Curr`** and **`Net-Dil`**
(near-field), and **`Bckgrd`** (far-field).

## The correction this case forced

case01 ended with a bare `Note: Plumes not merged, ...` and **no far-field
section**, from which I concluded "unmerged ⇒ far-field skipped". **That was
wrong.** case02's plumes are also unmerged (final diameter 0.558 m vs 2.00 m
spacing) and the far-field runs anyway:

```
-------------------- Starting Farfield Calculations --------------------
Note: Plumes not merged, Brooks method may be overly conservative
Farfield dispersion based on wastefield width of :      48.56 (m)
```

So the note is an **advisory printed whenever the plumes are unmerged**, and
whether Brooks runs is controlled independently — presumably a far-field enable
flag in the `.prj`. Because `test.prj` is empty we can't yet confirm which flag,
and case01's far-field block `[1,0,0,1,0,0,0]` can't be diffed against anything.

Order matters for the output writer: the `Starting Farfield` banner comes
**before** the note.

## Newly decoded, exactly

- **Far-field start distance = `hypot(x_posn, y_posn)`** at the near-field
  endpoint: x=0.000, y=2.896 → printed 2.896. Cross-checks on the example case
  (7.017, 2.082 → 7.319 vs printed 7.320).
- **Wastefield width = (n_ports − 1) × spacing + diameter**:
  24 × 2.0 + 0.558 = 48.558 → printed **48.56**. Exact.
  But the example gives 17 × 6.10 + 6.481 = 110.181 against a printed **109.59**
  — 0.5 % low. The example has a 30° horizontal angle where the archived diffuser has 90°, so
  this is very likely the effective-spacing / cross-diffuser-angle correction that
  PORTING_NOTES §5 flags (the 20° cap). Implied effective spacing for the example
  is 6.065 m vs a nominal 6.10 m. Worth nailing down in Phase 3.
- **`Net-Dil` = `FluxAvg-Dilution`** exactly in all 41 rows — with zero background
  pollutant, so it presumably diverges when background ≠ 0.
- **`CL-Dil = max(1.0, FluxAvg/2)`** again exact, 0 exceptions. That is now 125
  rows across two cases with different column sets, so it is a real property of
  the exe, not a coincidence.
- **`Amb-Curr`** is the ambient current at plume depth: constant 0.020 here, as
  the profile is uniform.

## Event sequence

| Step | Event | Depth |
|---|---|---|
| 120 | `Local maximum rise or fall` | −1.980 (shallowest) |
| 360 | `Plume traps` | −2.265 |
| 390 | `Local maximum rise or fall` | −2.335 (deepest) |
| 410 | `Plume traps` → far-field | −2.272 |

Same 2-extrema / 2-trap pattern as case01, so the max rise/fall switch was
probably still 3 — but we can't confirm without the `.prj`.

## Unexplained: where the far-field stops

The far-field prints at a 100 m interval and then stops at **501.611 m**:

```
   562.633    48.572     2.896     0.000     0.000
  1050.004   124.736   100.000     0.000     1.349
  1884.914   224.741   200.000     0.000     2.738
............................. Reached Chronic Mixing Zone ..........................
  2872.852   342.631   300.000     0.000     4.127
  3991.042   476.013   400.000     0.000     5.516
  5225.559   623.261   500.000     0.000     6.904
  5246.337   625.740   501.611     0.000     6.927
```

Two things to explain:

1. The **chronic MZ banner is printed after the 200 m row** although the chronic
   MZ is at 207 m — i.e. it fires when the *next* step would cross it, not at the
   crossing. (Compare the example, where the final row lands exactly on 104.435 m
   and is *preceded* by the banner.) Note also that here the run **continues past
   the mixing zone**, where the example terminated at it.
2. The last row at **501.611 m** — 1.611 m past a grid point. Max dilution
   (default 5000) is exceeded at 500 m already (5225.6), so a simple
   "stop when dilution > 5000" doesn't explain the extra fractional step. Could be
   3-intervals-beyond-the-MZ plus a terminating partial step, or a time/dilution
   limit interacting with the interval. Open question.

## Settings recovery ✅

Three of the four `.prj`-only settings are recovered from case03 (identical
near-field trace ⇒ identical hydrodynamic inputs): **aspiration 0.100,
contraction 1.000, max rise/fall 3**.

Still unknown: the **far-field settings** that made this run continue to 501.611 m
past a 207 m chronic MZ on a 100 m interval, where case03 (10 m interval) stopped
at 212.356 m. That is the one remaining puzzle attached to this case.

Note this means case01 → case02 changed **five** things at once, not one — the
contraction coefficient moved 0.610 → 1.000 as well. So the pair is not a clean
single-variable comparison for the flow unit. The genuinely clean pair in the set
is **case02 ↔ case03**, which differ only by chemistry being switched on.

## Names (2026-09-09)

This folder was `case02_macoma_mgd` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `macoma2ambient.csv` → `ambient.csv`, `macoma2effluent.csv` → `effluent.csv`, `macoma2mixzone.csv` → `mixzone.csv`, `Macomatest1.dat` → `test1.dat`.
