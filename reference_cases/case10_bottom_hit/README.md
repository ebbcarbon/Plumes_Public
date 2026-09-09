# case10 — bottom hit, and the boundary criterion decoded

Pulled 2026-08-12 12:05 (`test11_TxtOutputs.dat`). Changed from
[case07](../case07_s45_dense/): **port elevation 15.0 → 1.0 m**, keeping the
45 psu effluent, 25 ports × 0.60 m, 0.005 cms, interval 5.

A new banner appears, the last reachable coverage gap closed:

```
------------------------- Plume hits the bottom ----------------------
```

69 rows, terminating at step **345**. No NaN anywhere.

## Result 1 — the bottom criterion is `depth + radius ≥ bottom`

The seabed is at port depth 2.0 + port elevation 1.0 = **3.0 m**. The plume's lower
edge crosses it between the last two output rows:

| step | depth | diameter | radius | depth + radius |
|---|---|---|---|---|
| 335 | 2.320 | 0.963 | 0.481 | 2.801 |
| 340 | 2.444 | 1.080 | 0.540 | **2.984** |
| 345 | 2.576 | 1.225 | 0.613 | **3.189** |

So the criterion is the **plume edge touching the boundary**, not the centreline
reaching it. That mirrors the surfacing criterion measured in
[case06](../case06_arag_s36/), which brackets `depth − radius = 0`:

| boundary | criterion | bracketed by |
|---|---|---|
| surface | `depth − radius ≤ 0` | case06: +0.024 → −0.025 |
| seabed | `depth + radius ≥ bottom` | case10: 2.984 → 3.189 (bottom 3.0) |

A symmetric, sensible pair, and both now measured rather than assumed. It also
confirms **the seabed depth is derived as port depth + port elevation** — which is
what makes the old case01-case09 geometry (2.0 + 15.0 = 17 m, against a 15 m ambient
profile) the oddity it always looked like.

## Result 2 — the terminating-row rule is conditional, not absolute

Earlier cases suggested the terminating row is always truncated to the base
variables. It is not. Here step 345 is **complete — all 12 columns populated** — and
345 is a multiple of the output interval 5.

Across all seven usable traces the correlation is exact:

| case | final step | on interval? | terminating row |
|---|---|---|---|
| case05 | 417 | no | truncated to 6 fields |
| case06 | 356 | no | truncated |
| case07 | 529 | no | truncated |
| **case10** | **345** | **yes** | **complete** |
| **case11** | **500** | **yes** | **complete** |

So the rule is: **the terminating step is always printed; it is an extra truncated
row only when it falls off the output interval.** When it happens to land on the
interval it is an ordinary complete row. The `.dat` writer needs that distinction
(PLAN.md Phase 6, ledger row 54 amended).

## Result 3 — wastefield width, sixth exact confirmation

```
(25 − 1) × 0.60 + 1.225 = 15.625   →  printed 15.62
```

Note it prints **15.62**, not 15.63 — so the exe rounds half-to-even or truncates at
this boundary. Worth pinning when the byte-exact writer is built; a naive
round-half-away formatter would emit 15.63 and fail parity.

## Carried-over confirmations

- **Merging at `dia = spacing`**, third 90° measurement, bracketing 0.985 → 1.038
  (identical to case07, as expected from identical geometry and flow).
- **Aragonite S = 35 cutoff**: 12 of 69 rows above 35, `(S > 35) == (R_arg > 0)` on
  **69/69** rows.
- Ω_calc stays ≥ 7.663, so no `(Ω − 1)^N` NaN here.
- Far-field: 22 rows, 2.432 → 208.458 m, dilution 135.931 → 1091.922, 4/3-power law.

## Event sequence

`Local maximum rise or fall` before 220, `merging happened` before 310,
`Plume hits the bottom` before 345, then the far-field. Note the plume rises first
(local maximum at 220) before sinking to the seabed — the 45 psu effluent is dense but
the 45° upward jet carries it up first.

## Names (2026-09-09)

This folder was `case10_macoma_bottom_hit` until 2026-09-09. The word came off because these exe runs are an earlier entry of Ebb's diffuser with known slips (2 m for 2 ft ports, a 35 psu / 10 °C effluent, 0.219 L/s, mixing zones typed in metres, a chemistry table that was not the site's) and the name read as the site; the site's actual values are the standalone Macoma case (`reference_cases/pending/macoma_*` until the exe has run it). Data unchanged.
