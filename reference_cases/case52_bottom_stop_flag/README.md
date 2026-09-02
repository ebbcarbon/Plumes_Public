# case52 — near-field flag 1 **is** the stop-at-bottom box (1 = stop)

Flag-decode round 2's output arm (`studies/flag_decode_round2.py`), run by the operator within
minutes of generation (2026-09-01, same session as case51). One geometry — a dense discharge
aimed −45° at a seabed 0.3 m below the port, designed so contact is unavoidable — and one flag
moved: near-field position 1 (`nearfield_flags[0]`), 1 in the base arm, 0 in the other.

## The verdict, by output rather than recall

Both arms print `Plume hits the bottom` at **step 231** with every prior row bit-identical.
Then:

| arm | `nearfield_flags` (as-run) | after contact |
|---|---|---|
| `base_legacy.dat` | `[1, 1, 0, 3, 1, 1]` — **preserved** | **stops** on the truncated terminating row at step 231 (24 printed rows; far field hands off there, 52 rows to 503 m) |
| `nf1_legacy.dat` | `[0, 1, 0, 3, 1, 1]` — **preserved** | **continues 14 more printed rows** past contact, through `Plume traps` near step 320 to step ~370 (38 rows; far field 22 rows to 207 m) |

The exact analogue of case46's surface pair: position 2 is the stop-at-surface box, position 1
the stop-at-bottom box, and a hit is a *termination switch*, not physics — the plume model
integrates on happily when the box is clear, exactly as case06 does past the surface. Ledger
row 283.

⭐ **The pre-registered forecast hit.** The note predicted (from the port's own integration,
before the run) seabed contact "at t ≈ 21 s, flux-averaged dilution 93"; the exe printed the
banner at **21.409 s, dilution 97.200** — 2 % on time, 4.5 % on dilution, in the near field of
a case invented that afternoon.

## Build

Recorded as **legacy by inference, not by fingerprint**: this geometry discharges parallel to
the current (offset 0°), so the wastefield width is the same under both builds and cannot say.
The operator ran round 1 on the legacy exe deliberately (case51) and ran this pair in the same
sitting; the filenames carry `legacy` on that basis. Nothing in this case's *finding* is
build-sensitive — the pair is compared against itself.

## What stays open

Which *dialog* control position 1 is (presumably the "stop plume at bottom hit" checkbox, now
functionally proven; the label is confirmed by `flagdecode2_recon`, the no-run checklist still
in `pending/`), and the identities of near-field 5/6 and far-field 1/5/6 — same checklist.
