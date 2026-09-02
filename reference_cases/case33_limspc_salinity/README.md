# case33 — effluent salinity through the limiting-spacing rule, and a buoyant control

Run 2026-08-19 from the `limspc_mid` project: **one port** at 0.2 m and 0.005 m³/s, discharged
downward at −45° from a **2.4 m** port depth into the Macoma ambient. Only the effluent salinity
differs.

| run | effluent | first trap | `merging happened` | first step with `d >` port depth | lag |
|---|---|---|---|---|---|
| `sal35` | 35 psu | 171 | 192 | 191 | **1** |
| `sal45` | **45 psu** | 197 | 224 | 209 | **15** |
| `sal25` | **25 psu** | none | **none** | never | — |

## The 25 psu control does what it should

At 25 psu the effluent is *lighter* than the ~31 psu ambient, so the plume rises and surfaces at
step 323 without trapping. Its diameter tops out at **1.18 m** against a 2.4 m port depth, so it
never reaches the limiting-spacing threshold — and no banner appears. A negative control the rule
survives: no crossing, no banner.

## ⭐ Salinity moves the lag, and that is what led to case34 — and then to case35

`sal35` and `sal45` share a geometry exactly. Raising the effluent salinity by 10 psu takes the
banner from **1 step** behind the crossing to **15**. Combined with case30's `gap_3`/`gap_4`,
which moved the lag with *port diameter* at fixed salinity, the two levers pointed at the same
thing: the densimetric Froude number.

| run | `F` | lag past `max(trap, crossing)` |
|---|---|---|
| `sal35` (= case30 `gap_1`) | 2.170 | 1 |
| `sal45` | **1.115** | **15** |
| case30 `gap_4` | 0.220 | 16 |
| case30 `gap_3` | 0.113 | 23 |

⚠️ **That trend is real but it is not the mechanism**, and case34 is why: a *multiport* run at
`F` = 0.0045 — twenty-five times more sub-critical than `gap_3` — has a lag of exactly zero. The
lag belongs to the single-port limiting-spacing rule specifically, not to any merge banner. See
case34's README.

## ⭐⭐ `sal35` is a repeat of case30's `gap_1`, and it confirms determinism a second way

The two are **not** byte-identical, and the reason is worth recording: they carry the same
thirteen output columns in a **different order**, because the columns were re-selected in the GUI
between sessions. On the numbers they are exact — 13 columns × 576 rows, worst difference **0.0**.

So the exe's determinism (row 191c) is unaffected by which columns are selected or how they are
ordered, and the `.dat` reader and writer handle both orderings. Row 191c's evidence was one
byte-identical pair; this adds a pair that is identical in everything that is a number.
