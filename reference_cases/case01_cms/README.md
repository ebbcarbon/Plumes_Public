# case01 — the archived diffuser at 0.005 cms (second validation case)

Copied 2026-08-12 from `C:\Users\jerem\Documents\Plumes\Macoma\Macoma2`
(user-supplied, run with `plumes2.0v1.exe`). Files kept under their original
names so the exe still opens the project unchanged.

| File | Modified | Contents |
|---|---|---|
| `project.prj` | 2026-02-19 10:36 | project file, 149 lines |
| `ModelResults_TxtOutputs.dat` | 2026-02-19 10:37 | **golden trace**, 84 step rows to step 420 |
| `ambient.csv` | 2025-12-02 | 6 depth levels, 0–15 m |
| `diffuser.csv` | 2025-12-02 | 1 active case |
| `effluent.csv` | 2025-12-04 | 8 flow cases, row 1 active |
| `mixzone.csv` | 2025-12-02 | acute 20.7 m, chronic 207 m |
| `varios flows.csv` | 2025-12-02 | alternate 7-row effluent table (not referenced by the `.prj`) |

The `.dat` is timestamped one minute after the `.prj`, so it is the output of
exactly the saved project state — a directly usable golden trace.

## Why this case is valuable

It differs from `upstream/Example_project/` in almost every way that matters, so it
exercises code paths the shipped example never touches:

| | Example | archived diffuser |
|---|---|---|
| Port diameter | 0.076 m | **0.0127 m** (6× smaller) |
| Ports × spacing | 18 × 6.10 m | **25 × 2.00 m** |
| Horizontal angle | 30° | **90°** (normal to current) |
| Port depth | 11.0 m | **2.0 m** (near-surface) |
| Port elevation | 0.31 m | **15.0 m** |
| Ambient current | 0.090 → 0.050 m/s | **0.020 m/s, uniform** |
| Current direction | 0° | **90°** |
| Effluent salinity | 0.0 psu (fresh) | **35.0 psu** (hypersaline) |
| Effluent temp | 2.63 °C | 10.0 °C |
| Contraction coeff. | 1.00 | **0.61** (sharp-edged orifice) |
| Max rise/fall switch | 2 | **3** |
| Flow unit flag | 1 | **2** |

A 35 psu, 10 °C effluent into 31 psu, ~10 °C ambient is **near-neutral or
negative** buoyancy, versus the strongly positively buoyant freshwater example.
That is a completely different dynamical regime and a much stronger test of the
LCV solver than the golden case alone.

## What this case already told us about the `.prj` format

Diffing the two files structurally resolved several things PORTING_NOTES §4 left
open:

1. **The per-table integer blocks are unit selectors, not case flags.** Counts
   match the column counts (diffuser 9, effluent 5, mixing zone 3, ambient 11).
   The archived diffuser's effluent block is `[1, 2, 1, 1, 1]` where the example is all `1` —
   and the only differing column is flow. So flow is stored in *whatever unit the
   flag names*, and the example's flag-1 flow of 8.00 is the MGD the output header
   reports. **We must not hard-code MGD.** Decoding the flag→unit map is Phase 1
   work; question 5 below asks you directly.
2. **The trailing variable-name lists are count-prefixed and variable-length** —
   near-field 5 names here vs 9 there, far-field 4 vs 5. Any fixed-line-offset
   parser would break; the reader has to be sequential.
3. **The near-field settings block is 3 reals + 6 flags + interval + filename.**
   Example `[1,1,0,2,1,1]`, archived diffuser `[1,0,0,3,1,0]`. Position 4 is the max
   rise/fall switch (2 → 3). Positions 2 and 6 also differ and are unidentified.
4. **The far-field flag block is 7 flags + count.** Example `[1,0,0,1,1,1,0]`,
   archived diffuser `[1,0,0,1,0,0,0]`. Position 4 is presumably the eddy-diffusivity law
   (both are 4/3-power); 5 and 6 are unidentified.

## What the `.dat` resolved

The output settled two open questions outright:

1. **Flow units.** The Diffuser Table header reads `Ttl-flo (cms)` where the
   example's reads `(MGD)`. So the unit flag maps `1 → MGD`, `2 → m³/s`, and the
   stored `0.005` is 5 L/s. Confirmed, not inferred.
2. **`.prj` beats the CSVs.** The echoed ambient table shows `0.050` m/s at 15 m —
   the `.prj` value, not the CSV's `0.020`. The exe loaded the project file.
   Our reader should do the same, and warn on drift rather than silently picking one.

It also confirmed that the count-prefixed variable-name list in the `.prj` drives
the output columns one-for-one: 9 names → the 9 columns `Dilutn, P-dia, x-posn,
y-posn, Depth, P-Den, P-Con., CL-Dil, Time`, in list order.

## What the `.dat` revealed — three new behaviours

**1. The far-field can be skipped entirely.** Final plume diameter is 1.967 m
against 2.00 m port spacing, so the plumes never merge. The run ends after the
near-field with a bare warning and **no far-field section whatsoever**:

```
Note: Plumes not merged, Brooks method may be overly conservative
```

The chronic mixing zone at 207 m is simply never evaluated. This is a control-flow
path the example case cannot show us.

> ⚠️ **Superseded by [case02](../case02_mgd/README.md).** I originally read
> this as "unmerged ⇒ far-field skipped". case02 has unmerged plumes *and* runs the
> far-field, printing the same note. So the note is an advisory about merging, and
> the far-field is gated by something else — most likely a `.prj` enable flag.
> What case01 establishes is only that **the far-field can be absent**, which the
> output writer and reader still both have to handle.

**2. A termination/event banner absent from the example**, printed twice:

```
---------------------- Local maximum rise or fall --------------------
```

This is the max-rise/fall switch (`3` here vs `2` in the example) in action. The
plume oscillates: a **negatively buoyant** jet (initial density 1026.677 kg/m³ vs
ambient ≈1023.7) fired 45° upward on momentum, rising from 2.0 m to a shallowest
1.081 m at step 265, sinking back to 1.726 m at step 380, then rising again to
1.498 m where the run stops at step 420. Event sequence:

| Step | Event |
|---|---|
| 270 | `Local maximum rise or fall` (extremum at 265, depth −1.081) |
| 335 | `Plume traps` |
| 380 | `Local maximum rise or fall` (extremum at 380, depth −1.726) |
| 420 | `Plume traps`, then the no-merge note and end of run |

A damped oscillation about the trapping level. Note the banner is printed at the
first *output* step after the extremum is detected, not at the extremum itself.

**3. Centerline dilution is not independent.** Across all 84 rows, to the printed
precision and with zero exceptions:

```
CL-Dil == max(1.0, FluxAvg-Dilution / 2)
```

So the exe's "centerline dilution" is just half the flux-averaged value, floored
at 1. That is worth knowing before we try to derive it from the 3/2-power profile
— and it sits awkwardly next to the peak/mean ratios of 3.89 (round) / 2.22
(merged line plume) quoted in the manual. We should reproduce it and flag it
rather than assume we have misread something. See PLAN.md §6.14.

Also: `P-Con. = C_effluent / dilution` exactly (using unrounded dilution), and
`CL-Dil` sits at exactly 1.000 through step 30 and breaks away at step 35–40 —
which pins the **end of the zone of flow establishment** to roughly step 37. That
is a sharp, quantitative target for the ZFE initial conditions in Phase 5.

## Still missing

**`AmbientChem` and `AmbientDO` CSVs** — absent, and the `.prj` has no chemistry
block, so v1 chemistry was off for this run. If the alkalinity work is what Macoma
is for, a re-run *with the carbonate module enabled* (plus its output) is now the
most valuable single artifact you could add to this repo. It is the only validation
target we would have for the pH prediction that motivates the whole project.

## One input to check

**Geometry may be inconsistent.** Port depth 2.0 m below surface with port
elevation 15.0 m above the bottom implies a 17 m water column, but the ambient
profile stops at 15 m. In the example these are consistent (11.0 + 0.31 = 11.31 m
bottom, profile to 12 m). Is the 15 m elevation intentional — a tall riser — or
should one of those be something else? It does not affect this run (the plume
never goes below 2.02 m), but it will matter for bottom-hit termination.

## Names (2026-09-09)

This folder was `case01_macoma_cms` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `Macoma2.prj` → `project.prj`, `macoma2ambient.csv` → `ambient.csv`, `macoma2diffuser.csv` → `diffuser.csv`, `macoma2effluent.csv` → `effluent.csv`, `macoma2mixzone.csv` → `mixzone.csv`.
