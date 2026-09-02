# case12 — shoreline enabled via its checkbox, and still nothing happens

Pulled 2026-08-12 12:19 (`test13_TxtOutputs.dat`). This is the third attempt at a
shoreline hit, and the first with the feature explicitly switched on:

* **"stop plume at shoreline" checkbox — checked**
* **shoreline vector 60°, 5 m**
* baseline diffuser and effluent: 25 ports × **2.00 m** spacing, 0.005 cms, 35 psu,
  port elevation 15.0 m, port depth 2.0 m

80 rows, terminating at step **400** on `Plume traps`. No NaN.

## Result — no shoreline event, and the plume travels past 5 m

```
events:  Local maximum rise or fall (245, 365),  Plume traps (315, 400)
```

No shoreline banner, and none of the seven known banners is shoreline-flavoured. The
run ends on trapping, exactly as an equivalent run without a shoreline would.

**The plume demonstrably passes the stated shoreline distance.** Near-field travel is
`y` from 0.002 m to **5.389 m** — the current runs at 90°, so all displacement is in
`y` — against a shoreline 5 m away. And the far-field then spreads to **236 m wide**
over 208 m of travel. If a 5 m shoreline were being enforced, neither could happen.

That is now three configurations with no effect:

| case | shoreline setting | checkbox | result |
|---|---|---|---|
| [case08](../case08_macoma_shoreline/) | 45° | (not set) | byte-identical to the no-shoreline run |
| case08 second run | 45° + 5 m | (not set) | byte-identical to the 45°-only run |
| **case12** | **60° + 5 m** | **checked** | no shoreline event; plume travels to 5.389 m |

So enabling the checkbox does not change the outcome, and the earlier null results
were not simply "the feature was switched off".

## The one thing that would make this airtight

case12 uses a geometry no other case matches exactly (2.00 m spacing with contraction
1.0 and the cms flow), so there is no existing run to diff it against — unlike case08,
where the two shoreline runs could be compared to each other and to case05.

**One control run would close it: re-run this exact project with the checkbox
unchecked and nothing else changed.** If the output is byte-identical, the feature is
inert beyond argument, and it becomes a clean bug report. That is a single click.

## Other confirmations

- **Wastefield width**, eighth exact confirmation, and the first at 2.00 m spacing
  since case02: `24 × 2.00 + 1.760 = 49.760` → printed **49.76**.
- **Terminating row**: step 400 is on the output interval of 5, and the row is
  complete (12 of 12 columns) — consistent with the rule refined in
  [case10](../case10_macoma_bottom_hit/).
- **Unmerged**: final diameter 1.760 m against 2.00 m spacing, so the plumes never
  merge and the far-field runs with the advisory — the case02 control-flow path.
- Far-field: 22 rows, 5.389 → 207.891 m, dilution to 1021.276, width 52.016 →
  236.421 m. The first far-field row's distance again equals the near-field endpoint
  (`hypot(0, 5.389) = 5.389`).
