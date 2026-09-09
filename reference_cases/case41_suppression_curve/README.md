# case41 — deep overlap at 35–45 psu, where the step controller lets go (test63–test68)

Run 2026-08-20 to answer the question [case40](../case40_deep_overlap_spacing/) could not: what the
merging closure does at deep overlap **in a regime the port is accurate in**. case40's 2 psu
effluent grows so fast that its step controller sits on its 2 % cap, and its unmerged control
carries 2.10 % of error all by itself.

`project.prj` is archived with them. ⚠️ **It describes neither the salinity nor the spacing of any
run here** — it is the 2 psu / 2.0 m / 90° base, and every run below changes the effluent salinity,
the port spacing and the horizontal angle from it. The `.dat` diffuser echo records the spacing and
the angle; the salinity is the user's record, listed below.

Base: **25 ports**, 0.0127 m port diameter, 0.005 m³/s total, 2.0 m port depth, 45° vertical,
**65° horizontal** into a 90° current at 0.02 m/s, ~31 psu case03 ambient, contraction 0.61,
aspiration 0.1, output interval 1.

| run | spacing | effluent | rows | merges | max `d/L` |
|---|---|---|---|---|---|
| test65 | 0.75 m | 35 psu | 443 | step 232 | 3.75 |
| test63 | 0.50 m | 35 psu | 461 | step 204 | 6.18 |
| test64 | 0.25 m | 35 psu | 485 | step 166 | **15.08** |
| test66 | 0.50 m | 40 psu | 498 | step 205 | 6.20 |
| test67 | 0.50 m | 45 psu | 372 | step 205 | 6.20 |
| **test68** | **5.00 m** | 35 psu | 408 | ⚠️ step 373 — see below | 0.46 |

⭐ **Every row is finite.** A near-neutral effluent traps instead of surfacing, so unlike case40
there is no NaN tail and no missing-surface-clamp artefact to work around. test64 is the only one
that reaches the surface, and only at the very end.

⭐ **The step controller lets go**, which is the whole point of choosing 35 psu. Per-step
fractional dilution gain runs 0.0003–0.0208 with a **median of 0.007–0.018**, and only ~40 % of
steps sit at the 2 % cap against 73 % on case40 — which is what makes the suppression law below
measurable at all.

## ⚠️⚠️ The merging defect, at 35–45 psu

⚠️⚠️ **Every "ours" number in this section is the *retired* default's**, measured before
`ConfinedDecrements.ALL` became the default on 2026-08-21. Under what ships now the same runs give
**2.3–6.0 %** post-merge and **1.02–1.30×** on diameter, against the 15–27 % and 2.1–11.9× below.
The *exe* columns are unchanged and still correct. See rows 264–267 and
[case44](../case44_spacing_sweep/).

Our closure against the exe, sampled at the exe's own printed times:

| run | spacing | effluent | dilution MARE | **post-merge** | our max dia | exe max dia |
|---|---|---|---|---|---|---|
| test65 | 0.75 m | 35 psu | 7.28 % | **14.76 %** | 5.905 m | 2.813 m — 2.10× |
| test63 | 0.50 m | 35 psu | 8.22 % | **19.31 %** | 15.603 m | 1.809 m — 8.63× |
| test64 | 0.25 m | 35 psu | 7.05 % | **27.33 %** | 4.675 m | 0.853 m — 5.48× |
| test66 | 0.50 m | 40 psu | 8.18 % | **18.10 %** | 20.052 m | 1.876 m — 10.69× |
| test67 | 0.50 m | 45 psu | 7.42 % | **15.79 %** | 22.784 m | 1.910 m — **11.93×** |

**This is a much cleaner attribution than case40's.** At 35 psu with this geometry the port's
unmerged accuracy is the 0.31–0.88 % of rows 145 and 171, not case40's 2.10 % — so essentially all
of the 15–27 % is merging, and none of it is the regime. The runaway also gets worse: **11.93×** at
45 psu against case40's 6.65×, and our element reaches 20–23 m where the exe's stays under 2 m.

⚠️ The diameter ratios are quoted **at matched time**, and our runs terminate before the exe's, so
they are not maxima over the same window. test64's smaller 5.48× is an artefact of its run ending
earliest (218 steps compared, against 345–372 for the others), not of it being better behaved.

⚠️ **Salinity moves the runaway and the direction is worth noting**: 8.63× at 35 psu, 10.69× at 40,
11.93× at 45, all at the same 0.5 m spacing. A denser effluent sinks harder, so the element spends
longer in the deep-overlap regime where eq 56's inflation is unopposed.

## ⛔ RETRACTED — "the suppression law: a plateau at 0.60"

⚠️⚠️ **This section's headline claim was retracted on 2026-08-21, and the section is kept
because a retraction that leaves no trace is how a project forgets what it already got wrong.**

**What was wrong with it.** The three bins below pool **three different spacings**, and only the
0.25 m run has samples past `d/L` 5.5 — so they compare *different runs to each other* rather than
one run across overlap depths. Reduced per spacing over the window all three actually cover, the
level is **0.766 / 0.568 / 0.580** — a **0.198** spread where the pooled bins read flat to 0.020.
The three curves cross, and averaging them inside a `d/L` bin manufactures a plateau. Rows 260d,
260e and 260f carry the corrected reading; row 260b is kept as the evidence *for* the artifact.

⭐ **What survives**: the exe's suppression does not *decline* with overlap depth — asked per run,
two of three slopes are flat to within 0.03 and the third rises. The pre-run prediction of 0.4–0.5
at `d/L` 3 is still refuted, now on evidence that bears on it.

⚠️ **And it is not a spacing law either.** case42 and case43 showed the level tracks trajectory
stage (row 266) and port count (row 271); case44's six spacings then found the real spacing
dependence, rising 0.540 → 0.744 (row 276). The "0.60" here is none of those — it is an average
over a mixture.

### The original section follows, unedited

test68 is the unmerged control, and with it the **isolated suppression** becomes measurable — the
merged run's fractional entrainment rate over the control's at the same instant, `d(ln D)/dt`
either side. Taking the rate per unit *time* rather than per step is what removes the step
controller: the controller picks `dt` so each step gains about 2 % of mass, so a per-step gain
reads 0.02 on anything not otherwise limited and carries no information at all. That is the trap
[case20](../case20_spacing_sweep/)'s README flags and the reason case40 could not be used.

| `d/L` | exe suppression | our closure | samples |
|---|---|---|---|
| 1.5–3 | **0.606** ± 0.114 | rising through 1.0 | 188 |
| 3–6 | **0.586** ± 0.127 | 1.3–3.3 | 201 |
| 6–14 | **0.595** ± 0.175 | (past our range) | 94 |

**The exe saturates.** Three bins over a ninefold range of overlap depth, all within **0.020** of
each other — an order of magnitude tighter than the 0.13 scatter inside any one bin. Once plumes
are properly overlapped the exe removes a fixed ~40 % of the entrainment and stops removing more.
~~That is a law a fix can be built against: rows 260 and 260b.~~ ⛔ **It is not a law** — see
the retraction above.

⚠️⚠️ **Our closure crosses 1.0 at `d/L` 1.99 and then enhances entrainment** — reaching 1.33, 3.34
and 2.82 on the three spacings. Past `d/L` 2 we *add* entrainment where the exe removes 40 % of it.
The loop is visible in the equations: eq 56 inflates the merged radius, a larger radius means
larger Taylor and forced entrainment areas, more entrainment grows the mass, and eq 56 inflates the
radius again. Nothing opposes it. That is row 186's runaway seen as a rate instead of a length, and
it is row 260c.

### ⚠️⚠️ Two predictions registered before these runs, both wrong

| predicted | measured |
|---|---|
| the exe's suppression keeps **falling** past `d/L` 2.2 — 0.4–0.5 at 3, ≤0.3 at 4 | it **plateaus** at 0.59 out to `d/L` 14 |
| ours sits flat at **0.85–0.9** across the range | ours **crosses 1.0** at `d/L` 2 and reaches 3.3 |

Both were wrong about the *shape* rather than the size, which is the third and fourth time this
defect has broken a prediction. Recorded as misses.

## ⭐⭐⭐ And test68 found something it was not looking for

It was requested purely as an unmerged reference. **It prints `merging happened` anyway** — at step
373, six steps after the printed diameter crosses the 2.0 m **port depth**, with `d/L` = **0.41**
against a 5 m spacing. Twenty-five ports, and a plume that cannot possibly reach its neighbours.

So UM3's **limiting-spacing rule is not single-port behaviour.** Row 191o showed the entered
spacing is inert on one port; this shows the rule ignores the port *count* too, and fires on any
diffuser whose plume outgrows its port depth. Every earlier sighting happened to be single-port,
which is how a general rule looked like a special case. That is row 261.

⚠️⚠️ **The exe then contradicts itself in the same file.** The near field declares merging at 373;
the far field prints *"Note: Plumes not merged, Brooks method may be overly conservative"*. One
run, two answers — and the entrainment suppression is applied on the strength of the first, so a
user at a wide spacing gets a merged near field they did not ask for and an advisory telling them
the opposite. **Report to SSMC.**

⚠️ It also caps how far the suppression measurement reaches: the control is only clean up to its
own banner at step 373 (t = 123.75 s), which is what bounds the samples above. The merged runs'
banners are at 166–232, so the usable window is wide, but it is not the whole trace.

## Names (2026-09-09)

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `Macoma2.prj` → `project.prj`, `macoma2ambient.csv` → `ambient.csv`, `macoma2diffuser.csv` → `diffuser.csv`, `macoma2effluent.csv` → `effluent.csv`, `macoma2mixzone.csv` → `mixzone.csv`.
