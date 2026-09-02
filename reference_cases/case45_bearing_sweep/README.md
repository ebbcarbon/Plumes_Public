# case45 — the wastefield-width bearing sweep, and it refutes the question it was built to answer (test83–test91)

Run 2026-08-21 to bracket where the width's span factor switches from 1.0 to `|cos|` — row 275 had
it off at 20° and 25° and on at 30°. **There is no switch.** The factor is ≈1 at every bearing, and
row 275's apparent threshold was an artefact of comparing traces from two different exe builds.

Eight bearings at **25 ports, 5 m spacing (span 120 m), 0.0191 m port, 0.0112598 m³/s, 35 psu**, plus
one span-doubling arm. `|cos|` is the value the law under test would predict.

| run | bearing | \|brg−cur\| | span | printed width | last `P-dia` | **implied `A`** | `\|cos\|` |
|---|---|---|---|---|---|---|---|
| test83 | 90° | **0°** | 120 m | 122.470 | 2.471 | **1.0000** | 1.0000 |
| test84 | 75° | **15°** | 120 m | 122.630 | 2.846 | **0.9982** | 0.9659 |
| test85 | 68° | **22°** | 120 m | 122.590 | 3.017 | **0.9964** | 0.9272 |
| test86 | 66° | **24°** | 120 m | 122.590 | 3.079 | **0.9959** | 0.9135 |
| test87 | 64° | **26°** | 120 m | 122.560 | 3.123 | **0.9953** | 0.8988 |
| test88 | 62° | **28°** | 120 m | 122.530 | 3.167 | **0.9947** | 0.8829 |
| test89 | 60° | **30°** | 120 m | 122.490 | 3.205 | **0.9940** | 0.8660 |
| test90 | 45° | **45°** | 120 m | 121.380 | 3.063 | **0.9860** | 0.7071 |
| **test91** | 65° | 25° | **240 m** | **242.070** | 3.108 | **0.9957** | 0.9063 |

## ⛔ Row 275 is retracted: there is no angle threshold

The factor is flat at **0.986–1.000 across 0° to 45°**. If a cosine were applied anywhere in that
range, test89 (30°) would read 0.866 and test90 (45°) would read 0.707. They read 0.994 and 0.986.

⭐⭐ **And test91 settles it with no assumption at all.** It is test83–90's geometry with the spacing
doubled, so the span goes 120 → 240 m while the plume is identical. Against case42's test70 at the
same bearing and the same 120 m span:

    A = (242.070 − 122.590) / 120 = 119.480 / 120 = **0.9957**

The diameter cancels exactly. No rounding assumption, no diameter assumption, no cosine.

## ⭐⭐⭐ What was really going on: it is the **build**, not the angle

Row 275 compared 25° traces (all from case42–case44, one exe session) against 30° traces (mostly
case13/case14, a different exe). The tell is in case13 itself, which holds a **deliberate paired-build
run** at one geometry and one angle:

| trace | printed width | implied `A` |
|---|---|---|
| `paired_legacy.dat` | 109.590 | **0.9943** |
| `paired_current.dat` | 96.290 | **0.8660** = `cos 30°` exactly |

Same project, same 30°, same 18 ports at 6.10 m — **two builds, two widths**. That is rows 263/263b
and `ExeBuild.CURRENT`/`LEGACY`, already modelled. So:

- one build applies the cosine to the span, the other does not;
- **the exe currently in use does not** — every trace in case42, case43, case44 and this case reads
  `A ≈ 1`;
- row 96's 10.73 m failure was therefore a **build misclassification**, not a physics gap.

⚠️⚠️ **This is the fourth recurrence of one specific failure**, and `_is_old_build`'s own
docstring predicted it: *"Three separate runs have now landed as old-build files inside current-build
folders, each time failing row 96 by ~13.6 m until someone added the name here, so new runs should
carry the build in the name and classify themselves."* case42–case45 are the fourth, fifth, sixth and
seventh such runs.

## ⛔ And there is no trace-level signal to fix it with

`paired_current.dat` and `paired_legacy.dat` are **801 lines each and differ on 496 of them — all in
the far-field block**. The near field is byte-identical (row 263), the column set and order are
identical, the events are identical. The *only* difference is the printed width and everything
downstream of it.

So a build detector cannot read the build from the trace without reading the width, which is
circular for the row that uses it. The name/manifest rule in `_is_old_build` is forced, not lazy —
and the durable fix is for `plumes2.experiments` to put the build in the filename it generates.

## ⚠️ One thing this case does *not* settle

Solved with `A = 1`, the diameter the exe adds sits slightly **below** the last printed row, and the
deficit grows with the run: 1.0000 at 0° down to 0.9860 at 45°. That is not an angle law — it is the
diameter-selection effect row 96 already flags (§7 item 22, "the diameter the exe adds is not the
last printed row"). test91 makes it *irrelevant to the factor* by cancelling it, which was the
design, but it remains unexplained in its own right.

## ⚠️ Open question for whoever ran these

Which executable produced case42–case45? The behaviour is `ExeBuild.LEGACY`'s (no cosine), but if
this is a **2026** build that dropped the correction rather than the pre-2026 one, then "legacy" is
the wrong label for it and the build model needs a third value rather than a reclassification. The
traces cannot tell us — see above.
