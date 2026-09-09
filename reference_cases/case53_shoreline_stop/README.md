# case53 — the shoreline stop is inert: the controlled pair, byte-identical

Run 2026-09-02, both arms from the byte-identical projects `studies/open_items_experiments.py`
generated the same morning (predictions registered before the runs — the two
`EXPERIMENT_NOTE_*.md` files beside the traces). The operator typed the same shoreline vector
(**60°, 5 m** — case12's entry) into both sessions and ticked **stop plume at shoreline hit** in
exactly one. This is the pair case12 could not be: its `.prj` is lost, so no rerun of *it* could
ever be guaranteed identical.

| file | role |
|---|---|
| `shoreline_ON_legacy.dat` / `asrun_shoreline_ON_legacy.prj` | box **ticked**, 400 near-field + 498 far-field rows |
| `shoreline_OFF_legacy.dat` / `asrun_shoreline_OFF_legacy.prj` | box **unticked**, same |
| `EXPERIMENT_NOTE_shoreline_stop_on.md` / `_off.md` | the generated notes, predictions included |

## ⭐⭐⭐ The result: ON ≡ OFF at every byte

Both traces are **90 387 bytes with the same SHA-256** (`5799eb6c…`). With the exe deterministic
across sessions (row 191c, four checks), byte-equality between runs is a decidable statement about
their inputs — and the as-run projects show the inputs differed exactly where intended:

| | `asrun_shoreline_ON_legacy.prj` | `asrun_shoreline_OFF_legacy.prj` |
|---|---|---|
| near-field flags | `1, 1, **1**, 3, 1, 1` | `1, 1, **0**, 3, 1, 1` |
| shoreline records | `5.0, 60.0` | `5.0, 60.0` |

So the box was really ticked in one arm and not the other (near-field flag 3 moved, and only
flag 3 — the run-level confirmation of the recon checklist's identification), the vector was
really typed in both, the plume really crossed the stated 5 m shoreline (y reaches 5.389 m, first
passing 5 m at step 395, t = 154.85 s) — **and the feature did nothing at all**. Ledger row 284;
row 90's "still an inference from one run" caveat is closed, and the SSMC inert-shoreline item is
now a clean bug report rather than an inference.

## ⭐⭐ The `.prj` shoreline convention, decoded for free — row 284b

These are the archive's **first saved projects with a non-zero shoreline vector** (PORTING_NOTES
had "the coordinate convention remains unknown"). The exe wrote both back at run time as
`5.0` then `60.0` for a typed "60°, 5 m": **the first record is the distance in metres, the
second the bearing in degrees.**

## ⭐⭐ And the ON arm is bit-identical to case12 on every shared step

case12 (2026-08-12: chemistry **on**, output interval 5, box ticked) against this arm
(chemistry **off**, interval 1, 21 days later): all **80 shared steps agree to every printed
digit** in `Dilutn`, `P-dia`, `x-posn`, `y-posn`, `Depth`. Three findings hold again, out of
sample: the chemistry overlay is a pure overlay (row 215), the exe is deterministic (row 191c),
and the full-precision input reconstruction (case03's `test.prj` + the 0.005 cms flow) recovered
case12's session exactly.

## The prediction scorecard

| registered | measured | |
|---|---|---|
| ON ≡ OFF bit-identical | SHA-256 equal, 90 387 bytes | ✅ |
| no shoreline banner | events: max rise/fall 241, traps 312, max 361, traps 400 — nothing else | ✅ |
| ends step 400, `Plume traps`, Dilutn 296.962, y 5.389, Depth −1.722 | exactly that | ✅ |
| as-run nf 3 = 1 (ON) / 0 (OFF) | as above | ✅ |
| shoreline records non-zero, order decoded | `5.0, 60.0` = [m, deg] | ✅ |
| port: min depth ≈ 1.29 m, never near the surface | −1.296 min | ✅ |
| port: y = 5 crossed at t ≈ 152 s, dilution ≈ 259 | 154.85 s, 268.97 | ✅ (2 %, 4 %) |
| port: end t ≈ 163 s, dilution ≈ 280 | 169.13 s, 296.96 | ✅ 3.5 % / **−5.7 %**, the slow-current post-trapping family (test23) |

Far field: 498 rows to **501.519 m** — the typed 500 m distance stop bound first (dilution 2 697,
well under the 10 000× cap); `check_farfield_session_state` returns clean on both arms.
Wastefield width **49.76 = 24 × 2.00 + 1.760** exact — the ninth exact confirmation, the second
at 2.00 m spacing. case12's banner steps (245/315/365) were its interval-5 quantisation of the
true 241/312/361 printed here at interval 1.

## Which build

**Legacy** (operator, 2026-09-02) — the filenames carry it, per the archive's classification rule.
The trace itself could not have said: the discharge-to-current offset is 0°, where the legacy and
current wastefield-width laws coincide (row 275's fingerprint is inert), and nothing in a `.dat`
or `.prj` records the binary. Nothing measured above depends on the build at this geometry — and
the case12 bit-identity gains a footnote: case12 ran 2026-08-12 on a near field that is identical
across builds anyway (case13/case31).
