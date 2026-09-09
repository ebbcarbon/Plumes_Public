# case40 — deep overlap, and the oblique law on one geometry (test56–test62)

⚠️⚠️ **The "ours" numbers here are the *retired* default's** — measured before `ConfinedDecrements.ALL` became the default on 2026-08-21. The **6.65×** runaway and **28.8 %** post-merge below are what the old closure gave; what ships now reads 10.6 % on the same comparison (row 157b) and holds the element to a small multiple rather than a runaway (row 186, 11.93× → 1.82×). The **exe** columns are unchanged. See rows 264–267.

Run 2026-08-20 to answer two questions the archive could not: what merging does **past `d/L` ≈ 2**,
and whether the effective-spacing law survives an angle sweep where *only* the angle moves.

`project.prj` is archived with them and **round-trips byte-exactly**, as do all seven `.dat` files.
It describes `test56` — the 2 m base — and every other run changes one field from it.

Base: **25 ports**, 0.0127 m port diameter, 0.005 m³/s total, **2.0 m port depth**, 45° vertical,
90° horizontal into a **90° current at 0.02 m/s**, effluent **2 psu / 10 °C** into the ~31 psu
case03 ambient, contraction 0.61, aspiration 0.1, output interval 1, `stop at surface` **off**.

| run | spacing | H-angle | merges | finite rows | max `d/L` |
|---|---|---|---|---|---|
| test56 | 2.00 m | 90° | no | 272 | 0.57 |
| test59 | 3.00 m | 90° | no | 272 | 0.38 |
| test57 | 0.50 m | 90° | step 217 | 256 | **2.39** |
| test58 | **0.25 m** | 90° | step 172 | 233 | **4.27** |
| test60 | 0.75 m | 85° | step 245 | 268 | 1.59 |
| test61 | 0.75 m | 75° | step 243 | 271 | 1.58 |
| test62 | 0.75 m | 65° | step 241 | 272 | 1.57 |

⚠️ **A nearly-fresh discharge, which is a new regime for this port.** At 2 psu into 31 psu the
plume is strongly buoyant and surfaces in 27–36 s. With `stop at surface` off it then sails
through the free surface and every column goes NaN to the 5001-step cap — the missing surface
clamp of rows 253 and 258, here on a *third* geometry. Only the finite prefix is used.

## ⭐⭐ The effective-spacing law holds on five runs with nothing fitted

Three angles at one fixed spacing, plus two spacings square to the flow. This is the test the
archive never had: row 181's 85°/30°/0° evidence came from three *different* cases, so geometry
moved with angle. Here only the angle moves.

| run | `L` | H-angle | exe bracket (`d/L`) | derived law | static `\|sin ψ\|` |
|---|---|---|---|---|---|
| test58 | 0.25 m | 90° | 0.9960–1.0120 | **1.0001** ✅ | 1.0000 ✅ |
| test57 | 0.50 m | 90° | 0.9940–1.0080 | **1.0000** ✅ | 1.0000 ✅ |
| test60 | 0.75 m | 85° | 0.9973–1.0120 | **0.9988** ✅ | 0.9962 ✅ |
| test61 | 0.75 m | 75° | 0.9773–0.9920 | **0.9890** ✅ | 0.9659 ❌ |
| test62 | 0.75 m | 65° | 0.9587–0.9720 | **0.9703** ✅ | 0.9063 ❌ |

**Five brackets, five hits, no fitted constant.** Resolving `ψ` against the plume's *instantaneous*
heading lands inside every bracket, while the static law — `|sin ψ|` at the fully-turned-over
angle — falls below the bracket at 75° and 65°, by 1.2 % and 5.4 %. The brackets are one output
step wide, so they are ~1 % tight.

⭐ It also settles the shape of row 182's near-miss on case21's test35 from the other side: the
derived law now has five clean hits on a sweep where the only moving part is the one it depends on.

## ⚠️⚠️ Merging is 29 % wrong past `d/L` ≈ 4, and the element runs away

`test56`/`test59` are the unmerged controls, so the *difference* is merging's. Our closure against
the exe, at the exe's own printed times:

| run | max `d/L` | dilution MARE | **post-merge** | diameter MARE | our max dia | exe max dia |
|---|---|---|---|---|---|---|
| test56 | 0.57 (never merges) | 2.10 % | — | 1.08 % | 1.156 m | 1.141 m |
| test57 | 2.39 | 2.87 % | **7.86 %** | 2.77 % | 1.629 m | 1.193 m — **1.37×** |
| test58 | **4.05** | 8.82 % | **28.79 %** | 16.68 % | 6.731 m | 1.012 m — **6.65×** |

The 2.10 % on the control is this geometry's own baseline — a 2 psu discharge is outside anything
the closure was tuned on. Against that, merging adds nothing at `d/L` 0.57, little at 2.39, and
**29 %** at 4.05.

⚠️ **The sign is wrong, not just the magnitude.** The exe's element *stops growing*: its maximum
diameter is 1.141 m unmerged, 1.193 m at `L` = 0.5, and **1.012 m** at `L` = 0.25 — deep merging
makes it **smaller** than the unmerged run. Ours inflates to 6.7 m. So the exe has something that
strongly limits growth under deep confinement that this port lacks entirely; eq 56's inflation,
unopposed, is the wrong asymptote. That is ledger row 186, and it is worse than the row recorded:
2.05× on case21's test34, 6.65× here.

### The predictions were registered before the runs, and one was too optimistic

Written into the plan before these existed: our max diameter 2–4× the exe's, and post-merge
dilution MARE 15–25 %. Measured: **6.65×** and **28.8 %** at the deepest overlap — both *outside*
the predicted range, in the direction of the defect being worse. Recorded as a miss rather than
rounded into a hit.

⚠️ **The third prediction could not be tested, and the reason is worth keeping.** The plan was to
extend case20's *suppression-ratio* measurement (merged over unmerged per-step mass gain) out to
`d/L` 4. It cannot be done on these runs: a 2 psu effluent grows so fast that the step controller
sits on its 2 % cap for 186 of 255 steps, where the ratio is 1 by construction and carries no
information. That is the trap case20's own README flags, and case20 escapes it only because a
35 psu effluent grows slowly enough to fall off the cap. **Extending the ratio measurement needs a
weakly buoyant effluent at a tight spacing** — 35 psu at `L` = 0.5 m and 0.25 m — not this one.

## ⭐ Spacing is inert until the plume merges, on a third pair

`test56` (2 m) and `test59` (3 m) are **numerically identical on every column across all 272 finite
rows**, worst difference 0.0, while their bytes differ — the diffuser echo prints the spacing. Same
result as case20's test31/test33 at 2 m vs 5 m, and the same "the file changes, the numbers do not"
pattern as rows 191l and 191o.

## Names (2026-09-09)

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `Macoma2.prj` → `project.prj`, `macoma2ambient.csv` → `ambient.csv`, `macoma2diffuser.csv` → `diffuser.csv`, `macoma2effluent.csv` → `effluent.csv`, `macoma2mixzone.csv` → `mixzone.csv`.
