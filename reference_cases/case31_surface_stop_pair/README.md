# case31 — the surface stop, isolated, and the 40 % endpoint gap turns out not to be physics

Run 2026-08-19 from `reference_cases/pending/surface_stop_and_salinity/`, which asked three
questions. It answers two outright and reframes the largest open problem in the port.

Both runs are case13's project — the upstream example, written by `plumes2.io.project` — at
**output interval 1** instead of 5. The only thing that differs between them is the GUI's
**stop plume at surface hit** checkbox.

| run | build | stop at surface | rows | last step | final dilution |
|---|---|---|---|---|---|
| `surface_on.dat` | **current** | ✅ ticked | 275 | 275 | **169.754** |
| `surface_off.dat` | **old** | ❌ unticked | 572 | 572 | 246.607 |

⚠️ `surface_on` selected only the five default columns; `surface_off` carries thirteen,
including **`P-Sal`**. The chemistry columns were not selected in either, so the aragonite
band edges (row 60) still rest on a reconstructed salinity — that part of the request is
still open.

## ⭐⭐ The two builds agree bit for bit

`surface_on` (current build) against the archived `case13/PythonGenerated2.dat` (interval 5):
**55 shared steps × 5 columns, worst difference 0.0**. And `surface_on` against `surface_off`
(old build) over their 275 shared steps: **also 0.0**.

So the near field is unchanged between builds, and case30's determinism finding extends across
them. The build difference lives in the far field, where the ledger already placed it.

## ⭐⭐ The exe runs 14 steps past surface contact

At interval 1 the contact step is visible for the first time. `|Depth| − P-dia/2` crosses zero
between steps 260 and 261:

| step | Dilutn | P-dia | Depth | `|Depth| − P-dia/2` |
|---|---|---|---|---|
| 259 | 153.668 | 5.672 | −2.899 | +0.0630 |
| 260 | 155.017 | 5.722 | −2.869 | **+0.0080** |
| 261 | 156.331 | 5.774 | −2.839 | **−0.0480** |
| … | | | | |
| 275 ← `Plume surfaces`, last row | 169.754 | 6.481 | −2.512 | −0.7285 |

**Both predictions registered before the run hold**: contact at step 260 ± 1 (261), and the
banner at 271–275 (275). The exe therefore carries on for **14 steps and +8.6 % dilution**
after the plume's top reaches the surface, then stops. Nothing obvious marks step 275 — the
overshoot is not a threshold on `|Depth| − P-dia/2`, which reads −0.73 there.

⚠️ This is the same shape as case30's merging banner, which lagged its own trigger by 0–54
steps. Two different events, both detected late, both in a model whose step controller targets
2 % mass gain per step. Worth treating as one question rather than two.

## ⭐⭐⭐ Row 258 was reading a termination difference as a physics error

Row 258 recorded case13 as "ours 38.9 % vs the exe, and our near field ends at dilution
**237.7** against its 169.8 — a 40 % gap that swamps everything downstream", and concluded the
far-field error was a phase 5 problem wearing a phase 3 coat. The phase attribution was right.
The size was not.

`PythonGenerated.prj` parses as **`stop_at_surface = False`**, and the flag is session state
that no `.prj` carries. So our run sails through the surface exactly as `surface_off` does,
while the archived trace it was being compared against had the box **ticked**:

| | final dilution |
|---|---|
| ours, `stop_at_surface = False` (what the `.prj` parses) | 237.668 |
| ours, `stop_at_surface = True` | **159.223** |
| exe at its own contact step 261 | **156.331** |
| exe where it actually stops, step 275 | 169.754 |

**1.9 % at contact**, against a recorded 40 %. The trajectory was never the problem.

And with the flag matched to `surface_off`, sampled at the exe's own printed times:

| window | dilution MARE | worst |
|---|---|---|
| jet, before the first trap (steps < 251) | **2.30 %** | 4.08 % |
| to surface contact (≤ 261) | **2.37 %** | 4.22 % |
| past the surface (> 275) | 11.52 % | 15.21 % |
| all 572 steps | 7.13 % | 15.21 % |

So our near field on case13 is a ~2.4 % model up to the point the plume touches the surface,
and degrades to 11.5 % beyond it — where neither model has a free-surface treatment and neither
result means much. What remains genuinely unexplained is the exe's 14-step overshoot, worth
+8.6 %, which is an order of magnitude smaller than the number row 258 carried.

## ⭐⭐ The salinity column implies ~2–4 % more dilution than the dilution column

`surface_off` prints `P-Sal` against a **uniform 32 psu** ambient and a 0 psu effluent, so
conservative mixing is exact arithmetic — `S = 32(1 − 1/D)` — with no path-integral question to
confound it (row 222's collapse). The printed salinity does not match it:

| steps | D | `P-Sal` − prediction |
|---|---|---|
| 1–5 | 1.02–1.08 | +0.030 to +0.067 |
| 20–100 | 1.5–7.0 | +0.097 to **+0.206** |
| 100–275 | 7–169 | +0.004 to +0.095 |
| 275–572 | 170–247 | +0.003 to +0.005 |

Always positive, peaking early, decaying as `1/D`. That shape is the signature of a **fixed
fractional offset in the dilution**, since `dS = contrast × ε / D`. Solving for `ε` gives
**0.028** here, and across all eight archived traces that print `P-Sal` it stays in
**0.016–0.044** while the effluent–ambient contrast spans 3.5 to 32 psu — a 9× range in the
driving term against a 2.7× spread in `ε`.

⚠️ **This corrects yesterday's reading of row 109.** That note said the residual "scales with
the contrast"; it does, but only because `ε` is what is actually fixed. Quoting psu made a
0.006 trace and a 0.125 trace look like different physics when they differ by contrast and
dilution alone.

⭐ And `ε ≈ 2 %` is the step controller's own per-step mass target, which makes a one-step
alignment between the scalar columns and the dilution column the obvious candidate — the same
family as row 220's one-step DO accumulator lag. ⚠️ **Not confirmed**: shifting the comparison
by one whole step fixes this run (0.125 → 0.008 psu) and makes every limiting-spacing trace
**worse** (0.003 → 0.015). So the offset is real and measured; the one-step story is a
hypothesis that one test already argues against.

## Still open from the original request

- **The aragonite band edges from a printed salinity.** Neither run selected the chemistry
  columns, so rows 60 and 60b still rest on reconstruction. A rerun of `surface_off`'s column
  set **plus** TA/DIC/pH/OmegaC/OmegaA/R_cal/R_arg would settle both edges outright.
