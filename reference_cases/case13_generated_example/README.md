# case13 — our own generated project, and the angle correction it decoded

`PythonGenerated.prj` was written by `plumes2.io.project.prj_from_case` from the upstream
example, **with no template** — every value went through the semantic model and back out.
The exe loaded it without complaint and ran it, producing `PythonGenerated2.dat`.

This started as the Phase 1 acceptance check. It ended up resolving the biggest open
question in PORTING_NOTES section 5.

| File | What |
|---|---|
| `PythonGenerated.prj` | written by the port; identical to the upstream example except the output filename |
| `PythonGenerated2.dat` | the exe's run of it |
| `*_PythonGenerated.csv` | the input tables, rewritten by our CSV writer |

## Phase 1 acceptance: passed

* The exe **loads** a project we generated.
* The near-field is **bit-identical** to the shipped upstream trace — all 55 rows across
  all 5 shared columns, `Plume traps` at 255, `merging happened` at 260,
  `Plume surfaces` at 275, final flux-averaged dilution **169.754**.

So the reader → semantic model → writer chain is faithful for everything the near field
depends on. (One extra step was needed to run it: the exe requires the ambient chemistry
profile to reach deeper than the port, and the GUI was still holding case03's 1–4 m table
against this project's 11 m port. Chemistry is session state, not project state.)

## The disagreement: 96.29 m vs 109.59 m

The wastefield width does **not** match the shipped trace:

| | wastefield width | far-field endpoint |
|---|---|---|
| shipped `upstream/Example_project` | **109.59 m** | 178.408 @ 104.435 m |
| this run, same project | **96.29 m** | 180.792 @ 104.484 m |

The far-field difference follows from the width — a narrower wastefield dilutes faster
under Brooks, so a higher dilution is exactly what you would expect.

And 96.29 has an exact form:

```
17 × 6.10 × cos(30°) + 6.481  =  96.288      printed 96.29
```

30° is the angle between the discharge azimuth (horizontal angle 30°) and the ambient
current direction (0°).

## The rule this reveals

```
effective spacing = port spacing × |cos(horizontal angle − current direction)|
wastefield width  = (n_ports − 1) × effective spacing + final plume diameter
```

Checked against every exe run we hold:

| run | H-angle | current | offset | cos | predicted | printed | |
|---|---|---|---|---|---|---|---|
| case02 | 90° | 90° | 0° | 1.0000 | 48.558 | 48.56 | ✅ |
| case05 | 90° | 90° | 0° | 1.0000 | 16.828 | 16.83 | ✅ |
| case06 | 90° | 90° | 0° | 1.0000 | 17.397 | 17.40 | ✅ |
| case07 | 90° | 90° | 0° | 1.0000 | 17.307 | 17.31 | ✅ |
| case10 | 90° | 90° | 0° | 1.0000 | 15.625 | 15.62 | ✅ |
| case11 | 90° | 90° | 0° | 1.0000 | 1.451 | 1.45 | ✅ |
| case12 | 90° | 90° | 0° | 1.0000 | 49.760 | 49.76 | ✅ |
| **case13** | **30°** | **0°** | **30°** | **0.8660** | **96.288** | **96.29** | ✅ |
| shipped example | 30° | 0° | 30° | 0.8660 | 96.288 | **109.59** | ❌ |

**Eight of nine.** Every archived-diffuser case discharges parallel to the current, so the offset is
zero, the cosine is 1, and the correction is invisible — which is precisely why the
uncorrected `(n−1)·spacing + diameter` fitted all of them and hid this for so long.
case13 is the only run at a non-zero offset produced by the current exe build.

This is the oblique-angle effective-spacing correction that PORTING_NOTES section 5 lists
as the main unpublished piece of the near field, and it turns out to be a plain cosine.

## Which leaves the shipped trace as the outlier

Its 109.59 m implies an effective spacing of **0.9943 × nominal** — neither the
uncorrected 1.0000 nor cos(30°) = 0.8660. Two candidate explanations, and we cannot yet
separate them:

1. **The shipped `.dat` came from an earlier exe build** whose angle correction differed.
   Its header style is the 2026 form, so it is not the Dec-2025 build in case00, but there
   could be intermediate builds.
2. **Chemistry being enabled changes the correction.** Chemistry was on for this run and
   off for the shipped one. That would be strange, but no archived-diffuser case can rule it out —
   they all have a zero offset, where any cosine factor is 1.

### The experiment that separates them

Run `upstream/Example_project/Example_project.prj` **as shipped, with chemistry off**, in
the current exe.

* width 96.29 → the shipped trace is from a different build, and validation-ledger rows 6,
  7 and 8 need re-baselining against the current one.
* width 109.59 → the correction is somehow tied to the chemistry module, which would be a
  much odder finding and worth reporting to SSMC.

Either answer is worth having, and it matters before Phase 3: the example's far-field
table is currently our primary Brooks validation target, and if it is unreproducible we
should be validating against case13 instead.

## ⭐⭐ 2026-08-20: interval 1 settles row 258's question — the exe stops on a rule, 14 steps late

Two interval-1 reruns arrived. `interval1_rise2.dat` is the one PLAN queued: everything as the
archived `PythonGenerated2` except the output interval. `interval1_rise3.dat` came first and has
`max rise or fall` at 3 with stop-at-surface off, so it sails through and cannot answer the
termination question — but it is kept, because its 572 rows and 491-row far field resolve the same
event sequence.

| trace | interval | rise/fall | rows | trap | merge | `Plume surfaces` | surface contact | overshoot |
|---|---|---|---|---|---|---|---|---|
| `PythonGenerated2.dat` | 5 | 2 | 55 | 255 | 260 | 275 | step 265 | 10 steps |
| `interval1_rise3.dat` | 1 | 3 | 572 | 251 | 258 | 275 | **261** | **14 steps** |
| `interval1_rise2.dat` | **1** | **2** | **275** | 251 | 258 | **275** | **261** | **14 steps** |

**The exe stops on a rule, and the rule is late.** `interval1_rise2` ends at step 275, exactly on
the banner — so with stop-at-surface ticked the surfacing *is* terminal, and it is not drifting to
some other benchmark. But the plume edge reaches the surface at step **261**, where
`|Depth| − P-dia/2` crosses from +0.0080 m to −0.0480 m. So the exe ran **14 steps past contact**
before announcing it. The overshoot is in the *detection*, not the termination.

⭐ **Interval 1 makes it exact rather than bracketed.** At interval 5 contact could only be placed
between steps 260 and 265, which is why row 258b could say no better than "up to 15 steps". It is
14, and the two interval-1 runs agree on it exactly despite different rise/fall settings — so the
overshoot is a property of the surface check and not of the termination logic.

⚠️ **Two of the three registered predictions were wrong, from one bad inference.** The note
predicted surface contact "between 251 and 253" and therefore an overshoot of "22–24 steps",
reasoning from the trap moving 255 → 251 when the grid refined. That was wrong: the trap and the
contact are different events, and contact moved 265 → 261, not 255 → 251. The overshoot is
**14 steps, exactly what row 258b already said** — so the prediction that this would *enlarge* the
unexplained overshoot failed, and the existing figure is confirmed rather than revised. Only the
third prediction — that the banner would stay at 275 — held.

✅ `interval1_rise2.prj` is the project as the GUI saved it at run time, so unlike case30's
`gap_1.prj` this one describes its own run.


## ⭐⭐⭐ 2026-08-20: the paired-build run — the near field is bit-identical, the far field is not

`paired_legacy.dat` and `paired_current.dat` are the **same project run on both exe generations**,
output interval 1, everything else held fixed. It was written as a pending experiment with its
predictions registered first, and all three landed.

| | legacy | current |
|---|---|---|
| rows, columns | 275, 13 | 275, 13 |
| events | trap 251, merge 258, surface 275 | **identical** |
| final `P-dia` | 6.481 m | 6.481 m |
| echoed wastefield width | **109.59 m** | **96.29 m** |
| far-field start width | 109.610 | 97.242 |
| **ratio** | **1.0002** | **1.0099** |
| far-field rows, opening dilution | 495, 169.754 | 495, 169.754 |

⭐⭐ **The near field is bit-identical**: worst absolute difference across all 13 shared columns
over all 275 shared steps is **exactly 0.0**. The port has long assumed the trajectory is
build-invariant — PLAN said so from the shipped example against case13 — and this is the controlled
proof, at interval 1 with the full column set.

⭐⭐⭐ **The far-field transition adjustment is build-linked.** 1.0002 against 1.0099 with nothing
else changed. The single-port pair (`legacy_singleport.dat` and its new-build counterpart) says the
same at 1.0004 against 1.0253, and there the span is zero so the adjustment cannot hide in a large
denominator. Row 263c's reading holds, and case02 — current build, ratio 1.0002 — becomes the
anomaly to explain rather than a counterexample.

⚠️⚠️ **And it retracts a merging attribution.** Both builds *merge* on this run, at step 258. The
current-build width law is out by **−0.0022 m** and the legacy one by **+0.591 m**, so the legacy
residual cannot be a merged-element effect, which is what it had been recorded as an hour earlier
on the strength of the single-port run being exact. The cosine law also holds to 0.005 m across 87
merged current-build traces. What survives is the **diameter term**: `span·|cos| + final printed
diameter` reproduces the current echo exactly, so the diameter is the last printed row. The legacy
residual is on the span side, is zero when the span is zero, and is not proportional to it.
