# case05 — the merging case (the Phase 5 unlock)

Pulled 2026-08-12 11:14 from `C:\Users\jerem\Documents\Plumes\Macoma\`.
**`merging happened` fires**, and the far-field then runs on a genuinely merged
wastefield with no unmerged advisory — the first case outside the upstream example
to exercise that path.

| File | Role |
|---|---|
| `test4_TxtOutputs.dat` | **golden trace** — 83 near-field rows + 1 termination row, 52 far-field rows |
| `testambient.csv`, `testeffluent.csv`, `testmixzone.csv`, `testco2.csv` | inputs as found alongside the run |

## Settings

Changed from [case04](../case04_macoma_ta_dic/): **port spacing 2.00 → 0.60 m**,
**flow unit → cms** (value 0.005), **output interval 10 → 5**, **ambient `Ca`
100 → 10300 µmol/kg**, far-field **max distance 500 m**.

⚠️ **No `.prj` was saved** (`test.prj` is still case03's, timestamped 10:22).
Recoverable, though: spacing, flow unit, interval and the chronic MZ are all visible
in the `.dat` echo, and the rest is case03's state — aspiration 0.100, contraction
1.000, max rise/fall 3, near-field variable list of 5 names.

You reported being **unable to add extra output variables — a GUI bug in this
build**. That is consistent with the `.prj` still holding 5 names, and it means
ledger row 48's wish for a wide column set stays unmet.

Note the chronic MZ echo is still **207 m** — the 500 m you set is the far-field
**max distance**, a separate field.

## Result 1 — the merging criterion, bracketed at 90°

| | H-angle | spacing | diameter before / after | ratio |
|---|---|---|---|---|
| **case05** | **90°** | 0.60 m | 0.589 (step 220) / 0.607 (step 225) | **0.982 – 1.012** |
| upstream example | 30° | 6.10 m | 5.462 (step 255) / 5.722 (step 260) | 0.895 – 0.938 |

**At 90° the plumes merge when the plume diameter equals the port spacing** — the
bracket straddles 1.000 tightly. At 30° merging fires early, at ~0.92 of nominal
spacing.

So the criterion itself is simply `diameter ≥ effective spacing`, and the whole of
the discrepancy lives in **effective spacing**, which is reduced at oblique
horizontal angles. That is exactly the unpublished piece PORTING_NOTES §5 flags, and
we now have it pinned from both ends:

| source | H-angle | implied effective spacing | / nominal |
|---|---|---|---|
| case05 merging trigger | 90° | 0.60 (= nominal) | 1.000 |
| case05 wastefield width | 90° | 0.60 (= nominal) | 1.000 |
| example wastefield width | 30° | 6.065 | 0.9943 |
| example merging trigger | 30° | ≈5.46–5.72 | 0.895–0.938 |

The two example-derived numbers disagree (0.994 from width vs ~0.92 from merging),
so effective spacing may not be a single quantity used in both places. Worth one
more case at an intermediate angle to separate them.

## Result 2 — wastefield width formula, third exact confirmation

```
(25 − 1) × 0.60 + 2.428 = 16.828   →  printed 16.83
```

`width = (n_ports − 1) × spacing + final diameter`, exact again at 90°. Now
confirmed on case02 (48.56), case05 (16.83), and failing only on the 30° example —
which localises the angle correction to that formula rather than to our reading of it.

## Result 3 — a new output-format rule

The **termination row is printed with only the 5 base variables and no chemistry
columns at all**:

> Refined by [case10](../case10_macoma_bottom_hit/) and
> [case11](../case11_macoma_single_port_slow/): truncation happens **only when the
> terminating step falls off the output interval**. When it lands on the interval
> (case10 step 345, case11 step 500) the row is complete.

```
       415   191.259     2.329     0.000     5.521    -1.787  2938.511  2495.754  8.422  7.892  4.988  229.114  0.000
---------------------------- Plume traps -----------------------------
       417   198.986     2.428     0.000     5.759    -1.710
```

Two things there: the final step (417) is **not on the output interval** — the exe
always prints the terminating step — and it is **truncated to the non-chemistry
columns**. The `.dat` writer has to special-case it.

## Result 4 — merging visibly suppresses entrainment

Dilution growth per 5 steps collapses right at the merge:

| steps | Δ dilution |
|---|---|
| 195 → 200 | 2.62 |
| 215 → 220 | 2.16 |
| **merge** | |
| 225 → 230 | 1.74 |
| 235 → 240 | 1.48 |

Then it recovers later as the merged line plume grows. This is the merged-plume
entrainment reduction we have no other data on, sampled every 5 steps across the
transition — the single most useful thing in this file for Phase 5.

## Result 5 — far-field on a merged wastefield

52 rows, 10 m interval, 4/3-power law, from 5.759 m (= `hypot(x, y)`, confirmed
again) to **507.189 m** against a max distance of 500 m. Dilution 198.986 → 4708.988.

- The `Reached Chronic Mixing Zone` banner still fires between 200 and 210 m for the
  207 m MZ, and the run **continues past it** to the max distance.
- Termination overshoots the 500 m limit by 7.189 m. case02 overshot its (also 500 m)
  limit by 1.611 m at a 100 m interval. So "one more partial step past the limit" is
  the shape of the rule but the exact partial-step size is still unexplained.
- TA/DIC/pH/Ω **freeze from 290 m onward** (TA 2925.268, DIC 2500.000) while dilution
  keeps climbing — the plume has reached ambient chemistry to printed precision. The
  asymptote matches the ambient profile interpolated to the **trapping depth of
  1.710 m** (TA ≈ 2929, DIC 2500), confirming the far-field holds the plume at its
  trapping depth.

## Result 6 — the `Ca` diagnostic failed, and that's my fault

Ω is unchanged: exe Ω_arag 4.988 at the last full row vs 5.148 from PyCO2SYS with
salinity-derived calcium — the same 3.2 % offset seen in every other case.

**But this test cannot distinguish the two hypotheses.** 10300 µmol/kg is
approximately seawater calcium, so "Ca is ignored" and "Ca is used correctly" predict
the same Ω. I picked a value that carries no information. The discriminating test is
a clearly *wrong* value — **`Ca = 5000`** should halve Ω if the entry is used at all.

## Result 7 — aragonite still untested

`R_arg` = 0.000 in all 83 rows, and plume salinity spans **31.09 – 34.63 psu**, still
entirely below 35. So the `35 < S < 44` band hypothesis remains alive but unprobed.
The clean test is still to raise **ambient** salinity to 36 psu at all depths.

## Confirmations carried over

- `R_cal = exp(logK)·(Ω_calc − 1)^N` — mean pred/reported **0.99999** on this third
  independent run.
- PyCO2SYS divergence: RMS Δ pH **0.0226**, max **0.0786** (case03 0.0253/0.0766,
  case04 0.0251/0.0759). Stable across three chemistry runs and two flow regimes.
