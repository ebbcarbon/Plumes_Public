# case09 — a surface overshoot that poisons the run

> ⚠️ **Retitled and partly corrected by
> [case11](../case11_single_port_slow/README.md).** This file originally
> concluded that `Ports = 1` was the cause and that single-port runs were
> "impossible to validate". Wrong diagnosis: case11 runs a single port cleanly at
> 100× lower flow. The real cause is the **exit velocity** — putting the whole flow
> through one 0.0127 m port gives a **39.5 m/s** jet, 25× the per-port velocity of
> the 25-port cases, which drove the plume clean through the free surface. What this
> case genuinely establishes is the missing surface clamp and the Ω < 1 NaN, both
> below.
>
> A second file, `test10_TxtOutputs.dat`, is the same failure at port elevation 1.0 m
> with a 45 psu effluent — first NaN at step 235, 955 NaN rows, identical shape. It
> was intended as the bottom-hit case but still had `Ports = 1`; the real bottom hit
> is [case10](../case10_bottom_hit/).

Pulled 2026-08-12 11:57 (`test9_TxtOutputs.dat`). Settings: **`Ports = 1`**, no
shoreline vector, otherwise [case05](../case05_merging/)'s configuration
(0.0127 m port, 45°/90°, 2 m depth, 0.005 cms, effluent 35 psu, TA 4000 / DIC 1646).

**This run does not produce a usable trace.** It produces 955 rows of `NaN`, a `NaN`
wastefield width, and an all-`NaN` far-field table, across 134 kB. Kept because the
failure mode is precisely diagnosable and one of its causes is a serious bug that
would bite the alkalinity use case directly.

## What happens

| Step | Depth (m) | Ω_calc | R_cal | What |
|---|---|---|---|---|
| 215 | −0.478 | 4.335 | 28.515 | rising freely; no merging with one port |
| 218 | — | — | — | **`Plume surfaces`** banner |
| 220 | −0.321 | 2.092 | 1.156 | still rising |
| 225 | −0.148 | **0.580** | **NaN** | Ω drops below 1 → rate goes NaN |
| 230 | **+0.041** | 0.202 | NaN | **plume centre is above the water surface** |
| 235 | NaN | NaN | 0.000 | entire state NaN |
| … | | | | 955 NaN rows, to step **5001** |

Three distinct failures, in the order they appear:

**1. Surfacing does not terminate the run, and the plume keeps going up.** With max
rise/fall = 3 the surface is not a stop condition (consistent with
[case06](../case06_arag_s36/)), but here nothing else catches it either: the
depth becomes **positive at step 230**, i.e. the plume centreline is above the free
surface. There is no reflection and no clamp.

The trigger is the 39.5 m/s exit velocity. Note that case10 shows the *seabed* is
handled properly -- `depth + radius >= bottom` fires a clean `Plume hits the bottom`
and terminates -- so the surface boundary is the one that lacks a guard.

**2. `R_cal = NaN` as soon as Ω_calc < 1.** ⚠️ **The important one.** The decoded rate
law is `R = exp(logK)·(Ω − 1)^N` with `N = 2.87`, so for Ω < 1 it evaluates a
**fractional power of a negative number**, which is NaN in real arithmetic:

```
Omega_calc = 0.580  ->  (0.580 - 1) ** 2.87  =  (-0.42) ** 2.87  =  NaN
```

This has **nothing to do with single ports.** Any water with Ω < 1 triggers it — and
undersaturated water is exactly the acidified/upwelled receiving water that
alkalinity addition is meant to treat. A study with Ω_ambient < 1 would silently
produce NaN precipitation rates and, as below, poison the rest of the run.

**Our port must return 0 for Ω ≤ 1 rather than NaN.** That is a deliberate,
documented divergence from the exe: reproducing this particular behaviour faithfully
would make the model unusable on the cases we care most about. See PLAN.md Phase 4.

**3. TA falls below ambient, which conservative mixing cannot do.** Plume TA runs
2751 → 2618 → 2452 → **2253** while the endmembers are 4110 (effluent) and 2900
(ambient), so the transport has broken too. The likely trigger: `testco2.csv` defines
the ambient chemistry profile only from **1 m to 4 m depth**, and the plume rose above
1 m and then above 0 m, so the profile is being extrapolated far outside its range.
That is consistent with failures 1 and 3 sharing a root cause.

Once any state variable is NaN it propagates, the termination tests can never fire
(NaN comparisons are false), and the run grinds to the step cap — evidently **5000**,
with a final truncated row at 5001.

## What we take from it

- ~~A single-port configuration is not currently validatable.~~ **Superseded**: case11
  validates one cleanly at a realistic exit velocity.
- Ω < 1 must be handled explicitly in `chem/precipitation.py`, with a test asserting
  0 rather than NaN.
- The solver needs a surface clamp regardless of the max rise/fall switch, and the
  ambient-profile interpolator needs defined extrapolation behaviour at both ends
  (PLAN.md Phase 2 already flags this for the depth profiles).
- The step cap appears to be 5000. Worth knowing for the time-step controller.

## Worth reporting to SSMC

Two items, in priority order:

1. `(Ω − 1)^N` is evaluated without guarding Ω < 1, giving NaN for any
   undersaturated water and corrupting the whole run.
2. Nothing clamps or reflects the plume at the free surface, so a high-momentum
   discharge can drive the centreline above it and into an unphysical state -- while
   the seabed boundary *is* handled correctly (case10).

## Names (2026-09-09)

This folder was `case09_macoma_single_port` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.
