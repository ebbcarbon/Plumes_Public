# case08 — the shoreline vector appears to do nothing

Pulled 2026-08-12 11:56. Two runs were made, both on [case05](../case05_macoma_merging/)'s
configuration with only the shoreline vector changed:

| run | shoreline vector |
|---|---|
| `test7_TxtOutputs.dat` (kept here) | **45 degrees** |
| `test8_TxtOutputs.dat` (not kept) | **45 degrees and 5 m** |

## Result — no effect whatsoever

**`test7` and `test8` are byte-identical to each other.** Adding a 5 m shoreline
distance changed nothing, on a run whose far-field wastefield spreads to **176 m
wide**. A shoreline 5 m away should have been reached almost immediately.

And **`test7`'s near-field is bit-identical to case05** — all 84 rows across all 12
columns, same events (`merging happened` 225, `Local maximum rise or fall` 245 and
370, `Plume traps` 310 and 417), same wastefield width of 16.83 m. No
`shoreline`-flavoured banner appears in any of the ten traces we now hold.

So on the available evidence the **shoreline vector is inert in this build** — at
least for this geometry — and the shoreline-hit termination criterion listed in the
manual is not reachable. Only `test7` is archived; `test8` being a byte-for-byte
duplicate *is* the finding.

Consequences:

* No shoreline-hit coverage, and none obtainable by this route. The gap stays open.
* The `.prj` shoreline vector's **coordinate convention remains unknown** — we know
  it is two reals and that neither position visibly does anything. Our reader keeps
  both values so a `.prj` still round-trips, but the semantic model cannot interpret
  them.
* The shoreline-hit branch in `nearfield/termination.py` will have **no validation
  target**. It should be implemented from the manual and clearly marked unvalidated.

## The far-field difference is not the shoreline

test7's far-field stops at **209.465 m** where case05's ran to 507.189 m. That is
*not* attributable to the shoreline: test7 and test8 differ in shoreline distance and
are identical, so the shoreline cannot be shortening anything. It is the far-field
**max distance** setting, which was 500 m for case05 and evidently ~207–210 m here.

Everything else about the far-field matches case05 exactly at equal distance — width
18.462 m at the 5.759 m handoff, TA asymptote 2925.3, 4/3-power law.

## Worth asking

Does the GUI's shoreline entry have an enable checkbox, or another field (an origin, a
side-of-diffuser selector) that has to be set before the vector takes effect? If it is
genuinely non-functional, that is a third item for the SSMC report.
