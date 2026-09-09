# case42 — merging at matched dilution: the suppression is set by the trajectory, not the spacing (test69–test70)

Run 2026-08-21 to settle what [case41](../case41_suppression_curve/) could not. Row 260d measured a
**0.198** spread in the exe's merged entrainment suppression across case41's three spacings; row
260e showed the spread is confounded, because spacing determines *when* a given `d/L` is reached, so
at matched overlap those runs sit **8.1×** apart in elapsed time and **4.0×** in accumulated
dilution. Spacing, time and dilution each fit the 0.198 equally well.

This pair holds the **dilution** fixed while the spacing moves 1.5×.

| run | spacing | port | flow | effluent | rows | merges | onset dilution |
|---|---|---|---|---|---|---|---|
| **test69** | 0.75 m | 0.0191 m | 0.0112598 m³/s | 35 psu | 474 | step 204 | **56.10** |
| **test70** | 5.00 m | 0.0191 m | 0.0112598 m³/s | 35 psu | 427 | ⚠️ step 367 — see below | — |

Base otherwise as case41: 25 ports, 2.0 m port depth, 45° vertical, 65° horizontal into a 90°
current at 0.02 m/s, ~31 psu case03 ambient, contraction 0.61, aspiration 0.1, output interval 1.

⚠️ The `.dat` diffuser echo rounds to two decimals (row 141), so both runs print `P-dia 0.02` and
`Ttl-flo 0.01`. The archived `.prj` files are the record, and they are the ones the exe wrote back
at run time.

## ✅ The design worked, and it is a construction rather than a fit

⛔ **Row 260e's own proposal could not work.** It asked for two spacings matched by trading spacing
against effluent *salinity*. Over 20–48 psu the dilution at a fixed diameter moves only **17 %**
where **41 %** was needed — and it is structurally impossible that way, since reaching `d/L` = 1 at
a wider spacing always needs a larger diameter and therefore more dilution, monotonically.

⭐ **The port is the lever.** Dilution at `d = L` goes as `(L/d₀)²`, so scaling the port diameter by
the same 1.5 as the spacing holds the onset dilution fixed, with the flow scaled by the port *area*
(2.25×) to hold the exit velocity.

**Predicted 55.1, measured 56.10, against test63's 57.0 — a 1.6 % match**, inside the 5 % validity
gate registered before the run. The port scaling is exact enough to use as a design tool.

## ⭐⭐ The discriminator: the suppression follows the dilution, not the spacing

test69 shares its **spacing** with case41's test65 (0.75 m) and its **onset dilution** with test63
(56.1 against 57.0). Whichever it resembles is the driver.

| run | spacing | onset `D` | `d/L` 1.5–2 | 2–2.5 | 2.5–3 | level | trend per unit `d/L` |
|---|---|---|---|---|---|---|---|
| case41 test65 | 0.75 m | 90.2 | 0.688 | 0.802 | 0.806 | 0.766 | **−0.020** |
| case41 test63 | 0.50 m | 57.0 | 0.530 | 0.515 | 0.659 | 0.568 | **+0.125** |
| case41 test64 | 0.25 m | 27.4 | 0.598 | 0.578 | 0.563 | 0.580 | **−0.028** |
| **test69** | **0.75 m** | **56.1** | **0.536** | 0.674 | 0.767 | 0.659 | **+0.147** |

**test69 tracks test63, not test65.** Its first bin is **0.536** against test63's 0.530 — 1.1 %
apart — where test65, at the *same spacing*, sits 28 % higher at 0.688. Its trend is **+0.147**
against test63's +0.125, where test65 trends the opposite way. Standard errors on the first bin are
0.008 and 0.006, so neither agreement nor disagreement is noise.

⭐ **So row 260d's 0.198 is a trajectory-stage effect, and the spacing is not the driver.** Where a
run *is* along its trajectory when merging starts — measured as the dilution accumulated by then —
sets the suppression it then applies. That reattributes the one unexplained number left in
case41's write-up.

⭐ **It also explains row 260f's anomaly.** test63's +0.125 trend was "the largest anomaly left" and
had no companion. test69 reproduces it at a different spacing and a different port with matched
dilution, so the rising trend belongs to the low-dilution regime rather than to the 0.5 m spacing.
Two independent runs now show it.

### ⚠️⚠️ And the prediction registered for this was framed on the wrong statistic

The registered discriminator was the **window-averaged level**: "~0.568 means dilution, ~0.766 means
spacing, outside 0.55–0.78 means neither". It came out at **0.659** — 0.091 from one and 0.107 from
the other, near enough equidistant to settle nothing. The question was answered by the *bins and the
trend* instead.

**That is a smaller copy of the mistake rows 260/260b were retracted for**: pre-registering a pooled
average for a quantity that had just been shown not to be one number. The physics prediction was
sound and the statistic was not. Recorded as a miss on the framing.

## ⭐⭐⭐ The brake, validated out of sample — and its last defect identified

`ConfinedDecrements.ALL` (rows 264–264e) was written against case20 and case41 and never saw this
geometry. Sampled at the exe's own printed times:

| | ends | dilution MARE | post-merge | our max dia / exe's |
|---|---|---|---|---|
| `NONE` (the default until 2026-08-21) | 176.9 s | 20.40 % | **35.53 %** | **5.396×** |
| `ALL` (the brake; the default since 2026-08-21) | 187.7 s | **0.71 %** | **0.98 %** | **1.118×** |
| the exe | 182.7 s | — | — | — |

**0.98 % post-merge is row 157's shallow-overlap accuracy, reached at `d/L` up to 3.9 on a case the
brake was not built against.** A 36× reduction in post-merge error, and the run now ends within
2.7 % of the exe's own last row instead of dying 6 s early.

⚠️ **Our own suppression prediction was exact**: 0.835 unbraked and 0.652 braked were registered
before the run and reproduce to three decimals. So the port's *internal* behaviour is predictable;
what it disagrees with the exe about is the level.

### ⚠️ Which is where the brake's remaining defect now has a name

The brake gives ~0.65 **flat**, where the exe runs 0.53 → 0.77 depending on onset dilution. Row
264b already measured that as "ours is too uniform — 0.107 spread across spacings against the exe's
0.198"; this run identifies the missing variable as **dilution at merge onset**, and the direction
resolves an outstanding puzzle:

| onset `D` | exe suppresses | brake gives | so the brake is |
|---|---|---|---|
| 56 (test69) | 0.53 → 0.77 rising | 0.65 | **right** — 0.98 % post-merge |
| 138 (case20 test32) | (higher; test65 at 90 gives 0.766) | 0.65 | **too strong** — 5.24 % against 1.01 % |

⭐ **That is why row 264c's cost exists.** test32 merges at dilution **138.2**, two and a half times
test69's, so the exe suppresses less there and a flat 0.65 over-suppresses. It was read as "the
brake fails at *moderate overlap*"; it is not overlap depth at all, it is **where in the trajectory
merging began**. Row 264c's framing is corrected accordingly.

## Other findings

⚠️ **The limiting-spacing banner fires on this multiport control too, and the lag is not fixed.**
test70 is 25 ports at 5 m, `d/L` = 0.486, and prints `merging happened` at step **367** —
**32 steps** after the diameter crosses the 2.0 m port depth at step 335. Row 261 found the same
thing on case41's test68 with a **6**-step lag. So the rule fires on any diffuser whose plume
outgrows its port depth (row 261 holds) but the lag is a variable, 6 to 32 steps on two multiport
runs, which is row 191b's unexplained lag reappearing where it was thought to be single-port-only.

⚠️ **The prediction for that banner was wrong, and only half wrong.** It said ~85 s, taken as the
2.0 m crossing. The crossing is at **87.0 s** — 1.7 % out, a good prediction — but the banner is at
**113.2 s**. Predicting the trigger and predicting the banner are different things, and this run
says so.

⚠️ **The far field contradicts the near field again**: test70 prints *"Note: Plumes not merged,
Brooks method may be overly conservative"* after its near field declared merging at step 367. One
run, two answers, and the entrainment suppression is applied on the strength of the first. Second
instance, after case41's test68. **Report to SSMC.**

✅ **Peak-to-mean confirmed at a port diameter the law was never fitted at.** Rows 199 and 203 give
2.0 unmerged, then `max(1.5, 2.5 − 0.5·d/L)`. On test69, at a 0.0191 m port: 2.0010 at most
pre-merge, walking 1.9946 → 1.7511 over `d/L` 1–1.5, 1.7476 → 1.5050 over 1.5–2, and **exactly
1.5000 on all 146 rows past `d/L` 2**. ⭐ That is the exe stating the merged element is a **slab**
from `d/L` = 2 outward — on the concentration column, independent of entrainment, and it is the
constraint the brake's asymptote was derived to meet.

⚠️ **A `.prj` flag moved, and its meaning is *not* established.** Both projects came back with
`nearfield_flags[1]` changed from 1 to **0** — a position `io/prj.py` records as "not yet
identified". The GUI instruction for both runs was *stop plume at surface hit: unticked*, which
makes the surface-stop switch the obvious candidate, and test69 does continue past its own
`Plume surfaces` at step 473 rather than stopping there.

⛔ **But the archive refuses to confirm it, and the attempt is worth recording.** Correlating
`nearfield_flags[1]` against whether a trace *stops* on `Plume surfaces` gives **42 consistent
against 45 inconsistent** — noise. ⚠️ And the test is not sound in the first place: several case
directories hold traces from more than one project while archiving only the last-saved `.prj`, so
the flag being read is often not the flag that produced the trace. That is PLAN §7b's traceability
problem biting a decoding attempt, and it means this flag needs a **deliberate pair** — one project
run twice with only that box changed — not archive mining. Recorded as an observation, not a
finding.
