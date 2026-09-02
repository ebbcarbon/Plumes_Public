# case20 — the port-spacing sweep (test31–test33)

⛔ **Superseded as the accuracy bar on 2026-08-21 — see [case44](../case44_spacing_sweep/).** What this case established about the merge *trigger* and about spacing being inert until the plume merges is unaffected and still executable (rows 51, 118, 181, 259). What is retired is its role as the merging-accuracy bar: test32's 1.01 % post-merge sat **below** its own unmerged control's 1.39 % (row 177), and an error smaller than the same case run with no merging at all is the signature of cancelling errors rather than of correctness. Its control was also a 2 m spacing rather than a single port — which case43 showed still trips the limiting-spacing rule — and it reaches only `d/L` 2.35. case44 replaces it with six spacings against a single-port control. Under what ships now test32 reads **5.24 %** (row 157).

**Old build**, output interval 1, all output columns, **25 ports** at 0.005 m³/s. Generated
2026-08-12 to pin the merging correction. Only the **port spacing** changes.

| run | spacing | rows | merges? | max plume diameter |
|---|---|---|---|---|
| test31 | 2.0 m | 420 | no | 1.967 m |
| test32 | **1.0 m** | 425 | **yes, at step 310** | 2.351 m |
| test33 | 5.0 m | 420 | no | 1.967 m |

## Spacing is inert until the plume merges

test31 and test33 have **byte-identical near-field tables** despite a 2.5× change in spacing.
The reason is visible in the last column: the plume reaches 1.967 m against a 2.0 m spacing,
so it just misses the merging trigger, and an unmerged multiport diffuser behaves as a set of
independent single plumes. Every run in `case18`–`case20` at 2 m or wider is in that
situation, which is why the whole set could be used to pin single-plume physics.

## The merging trigger is `diameter = effective spacing`, to 0.7 %

test32's 1 m spacing brings the trigger inside the trajectory, and at output interval 1 the
banner is bracketed by consecutive steps:

| step | diameter | diameter / spacing |
|---|---|---|
| 309 | 0.999 m | **0.9990** |
| 310 ← `merging happened` | 1.006 m | **1.0060** |

So the criterion is `diameter ≥ effective spacing` within 0.7 %. The previous best bracket
was 0.982–1.038 from case05, so this is about 5× tighter. The horizontal angle equals the
current direction here, so the angle offset is zero and effective spacing is the nominal
spacing — this run does not constrain the oblique-angle factor.

## The suppression curve, measured

Because spacing is inert before merging, test32 against test31 isolates the correction
exactly: the two are bit-identical through step 310 and diverge from step 311. Taking the
ratio of per-step fractional mass gain, merged over unmerged, across 87 steps where **neither
run is at the step controller's 2 % cap** (at the cap both read 2.0000 % and the ratio is 1 by
construction, carrying no information — a trap worth knowing about):

| diameter / spacing | measured suppression |
|---|---|
| 1.006 | 0.959 |
| 1.529 | 0.626 |
| 1.761 | 0.663 |
| 2.001 | 0.621 |
| 2.126 | 0.346 |

Candidate closed forms, against all 87 points:

| form | mean abs error |
|---|---|
| `sqrt(1 − 2·acos(1/x)/π)` | **0.064** |
| `1 − 2·acos(1/x)/π` (blocked perimeter) | 0.205 |
| `2/(πx)` (fully-merged line limit) | 0.237 |

The square-root form is much the best and tracks from 0.96 down to about 0.58, but it
flattens where the measurement keeps falling past `x ≈ 2`. Not yet implemented — recorded
here as the measured target for `nearfield/merging.py`.
