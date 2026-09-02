# case51 — the flag-decode suite: ownership of every undecoded `.prj` flag

Nine generated projects (`studies/flag_decode_experiments.py`, 2026-09-01), each flipping
exactly **one** undecoded flag on the upstream-example geometry; run by the operator the same
day. Eight came back with traces; one (`nf3`) failed. The generated (pre-flip) state of every
project is the generator script; what is archived here is the **as-run** state.

**Build: legacy, deliberately** — the operator ran the old executable ("better for assessing
the physics without chemistry involved"), and the base arm's wastefield width printed
**109.59 m**, the no-cosine legacy value (rows 263/275), exactly as the note's fingerprint
predicted for that build. Every `.dat` filename here carries `legacy` so the archive
classifies them correctly.

## What each flip showed

Flag positions are 1-indexed as the docs use them; python indices in brackets.

| arm | flip | as-run `.prj` | trace vs base | verdict |
|---|---|---|---|---|
| `ff1` | far-field 1 `[0]`: 1→0 | **preserved** | near field **byte-identical**; the far-field block absent entirely | **a far-field on/off control the file owns** |
| `ff5` | far-field 5 `[4]`: 1→0 | **preserved** | `.dat` **bit-identical to ff1's** | **a second far-field gate** — a different control with the same observable |
| `ff6` | far-field 6 `[5]`: 1→0 | preserved | bit-identical to base, far field included | file-owned, inert on this run |
| `ff7` | far-field 7 `[6]`: 0→1 | ⚠️ **rewritten to 0 by the exe** | bit-identical to base | **exe-owned/derived** — not a control the file carries |
| `nf1` | near-field 1 `[0]`: 1→0 | preserved | bit-identical to base | file-owned, inert **on a surfacing trajectory** (a bottom-gating control could not show here — round 2 tests that) |
| `nf5` | near-field 5 `[4]`: 1→0 | preserved | bit-identical to base | same |
| `nf6` | near-field 6 `[5]`: 1→0 | preserved | bit-identical to base | same |
| `nf3` | near-field 3 `[2]`: 0→1 | ⚠️⚠️ **truncated** — everything from the near-field plot-flags block down is gone | **no `.dat` at all** | **the value 1 makes the exe fail silently**: no error dialog on the run (operator), no output, and the project was cut mid-rewrite. Re-loading the truncated file later **crashed the exe** (operator, same day) — a second defect: no guard on a short project file |

Identical-content groups: `base ≡ nf1 ≡ nf5 ≡ nf6 ≡ ff6 ≡ ff7` (one distinct trace) and
`ff1 ≡ ff5` (a second). The ff1/ff5 diff against base is exactly the 110 lines of the
far-field block — the near-field table is equal to the byte.

## The base trace

55 near-field rows (output interval 5; the plume surfaces near step 275 and the surface box,
`nearfield_flags[1]` = 1 as loaded, stops it), then 101 far-field rows to 501.9 m — the
declared 500 m calculation-distance stop, `check_farfield_session_state` clean. Width
109.59 m, `4/3 Power Law` header.

## Round 2 closed it, the same evening

`studies/flag_decode_round2.py` generated a bottom-hit pair (graduated as
[`case52_bottom_stop_flag`](../case52_bottom_stop_flag/README.md), row 283) and a no-run
reconnaissance checklist — archived here, filled in, as
[`RECON_CHECKLIST.md`](RECON_CHECKLIST.md) with its nine `recon_*.prj` copies beside it. The
complete map (1-indexed positions):

| block | position | is |
|---|---|---|
| near-field | 1 | **stop-at-bottom box** (1 = stop) — case52 by output, checklist by dialog |
| near-field | 2 | stop-at-surface box (case46) |
| near-field | 3 | **stop-at-shoreline box** — and writing 1 against a zero shoreline vector is what made the `nf3` run fail silently (row 282) |
| near-field | 4 | rise/fall count |
| near-field | 5, 6 | file-owned constants, **no dialog control**, always 1, 1 |
| far-field | 1, 5 | far-field gates (0 = no far field), **no dialog control** — gates without checkboxes |
| far-field | 2, 3, 4 | eddy-diffusivity law, one-hot (case50) |
| far-field | 6 | file-owned constant, no dialog control |
| far-field | 7 | exe-owned; the exe rewrites it to 0 |

Ledger rows 281, 281b, 281c, 282, 283 carry the findings; the flag docstrings in
`src/plumes2/io/prj.py` are the working reference.
