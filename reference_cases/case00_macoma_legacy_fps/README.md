# case00 — the Dec-2025 build, and the unit-flag decode

Two files from **2025-12-02**, found in `C:\Users\jerem\Documents\Plumes\Macoma\`:

| File | What |
|---|---|
| `Macoma.prj` | project file, **147 lines** — a different layout from the 2026 builds |
| `ModelResults_Macoma1.dat` | its output, but **header-only**: 1898 bytes, no step rows |

They are a matched pair — the `.prj` names its output `ModelResults_Macoma1`. The run
produced no steps, so this is not a validation trace. It is kept because the pair
decoded two things nothing else could.

## 1. The `.prj` unit flags — flag 2 means the alternate unit

The `.prj` stores raw values plus a per-column unit selector; the `.dat` echoes the
converted values. Having both for the same project reads the mapping straight off:

| column | flag | stored in `.prj` | echoed in `.dat` | ratio |
|---|---|---|---|---|
| diffuser spacing | **2** | 2.00 | **0.61 m** | 0.3050 |
| acute mixing zone | **2** | 20.70 | **6.31 m** | **0.3048** |
| chronic mixing zone | **2** | 207.0 | **63.09 m** | **0.3048** |
| effluent flow | **2** | 0.005 | header reads `(m3/s)` | — |
| everything else | 1 | — | unchanged | 1.0000 |

`0.3048` is exactly feet → metres. So:

* **flag 1 = the primary unit** (metres, MGD)
* **flag 2 = the alternate unit** — feet for lengths, m³/s for flow

Both are per column, and they **silently rescale physical inputs**: the same stored
`2.0` is 2 m or 0.61 m depending on one integer elsewhere in the file. That is why
`units.py` refuses an unrecognised flag rather than defaulting to SI.

### Flag-to-column alignment

The counts are not uniform, and the pair resolves that too:

| table | flags | columns | mapping |
|---|---|---|---|
| diffuser | 9 | 9 | **direct** — spacing is column 5 and flag index 5 is the `2` |
| effluent | 5 | 4 | **offset by one** — flow is column 0 and flag index 1 is the `2` |
| mixing zone | 3 | 2 | offset by one — flags `[1, 2, 2]`, both columns converted |
| ambient | 11 | 10 | offset by one (presumed, no converted example yet) |

So three of the four tables carry a leading flag of unknown purpose — plausibly a
table-level unit-system selector — and only the diffuser maps one-to-one.

## 2. A different `.prj` layout, and a different `.dat` header style

`Macoma.prj` has **one** near-field plot flag where every 2026 file has **four**
(147 lines vs 149 for the otherwise-similar `case01/Macoma2.prj`). Our reader
therefore reads both plot blocks greedily up to the next text record, taking the last
integer as the name count; hard-coding four would reject this file. It round-trips
byte-exactly like the others.

It also contributes a variable name absent from every 2026 project —
**`Plume-Temp`** — which is exactly the `P-Temp` column its `.dat` emits:

```
FluxAvg-Dilution, Plume-Diameter, Position-Xdir, Position-Ydir, Plume-Depth,
Centerline-Dilution, Plume-Temp, Pollutant-Conc., Plume-Density, Time
```

The `.dat` header style differs too, so the reader must not key on literal text:

| | Dec 2025 | 2026 builds |
|---|---|---|
| unit row | bare: `m`, `m/s`, `deg` | parenthesised: `(m)`, `(m/s)` |
| pollutant | `kg/kg` | `(mg/L)` |
| decay | `s-1` | `(1/day)` |
| flow | `(m3/s)` | `(cms)` |
| dilution column | `Avg-Dil ()` | `Dilutn (FluxAvg)` |
| extra column | **`P-Temp (C)`** | — |
