# case54 — the sub-critical discharge the exe *can* run: submerged, finite, trapped

Run 2026-09-02 from `studies/open_items_experiments.py` (predictions registered before the run —
`EXPERIMENT_NOTE_subcritical_sinks.md`): case29's discharge (25 × 0.5 m ports, 0.005 m³/s, case03
profile, port at 2.0 m) with a **45 psu** effluent — denser than every ambient level, so it
**sinks** instead of surfacing. F ≈ **0.0044** (exit velocity 0.001019 m/s, g′ ≈ 0.108 m/s²),
the same three-orders-below-threshold regime as case29's arms.

| file | role |
|---|---|
| `subcritical_sinks_legacy.dat` | 448 near-field + 500 far-field rows, interval 1 — ⚠️ **byte-identical to case34's `L2.0_d0.50.dat`**, see below |
| `asrun_subcritical_sinks_legacy.prj` | the as-run project, written from the case and re-saved by the run |

## ⭐⭐⭐ The separation: case29's NaN cliff is the surface, not the regime

**Zero NaN cells anywhere** — 448 finite near-field rows through `Plume traps`, 500 finite
far-field rows to the 500 m stop. case29's three sub-critical arms all rose, crossed depth zero,
and went NaN for ~4 750 remaining rows; this one, at the same Froude number, never gets shallower
than **2.015 m** and runs clean end to end. So the exe's failure mode is **leaving the water
column** (the missing free-surface clamp, as case09 shows from the momentum extreme), not
sub-criticality itself — the two things case29 could not separate. Ledger row 285; row 253 is
rescoped accordingly. The manual's §5.2.2 warning (and our `DesignWarning`) still stands as a
*regime* warning; what it is not is a crash predictor for a submerged plume.

The trajectory: sinks from the 2.0 m port to a deepest **5.332 m** at t ≈ 160 s — the port's
pre-registered forecast said **5.33** — rebounds ~0.5 m, and traps. Events: `Local maximum rise
or fall` at **step 1** (a momentumless dense discharge aimed 45° up turns immediately), traps
296, merges 309 (on the d ≥ spacing crossing with zero lag — row 191d's case34 rule, on this very
trace), max 391, traps 448. Nowhere near the 17 m seabed: the stratified ambient (30.9 → 31.9
psu) traps the diluted mixture long before pure-effluent density could matter.

## ⚠️⭐⭐ The twist: the data had been in the archive for two weeks

This trace is **byte-identical to `case34/L2.0_d0.50.dat`** (SHA-256 `1fc1caaa…`, 97 332 bytes),
run 2026-08-19. The `subcritical_sinks` project was written back then for exactly this run, got
repurposed into case34's spacing sweep, and its 2.0 m-spacing arm — read only for the merge
trigger — *was* the sub-critical separation run all along. Nobody claimed the finding: case29's
"Still open" stayed open, PLAN §6 carried "`subcritical_sinks`, never generated", and the
2026-09-02 audit that regenerated this experiment missed it too. Two lessons, both kept:

- **A finding can be absent from the ledger while its data is already archived.** The audit
  checked whether the *runs* existed for the other four list entries and found three; for this
  one it checked whether the *pending experiment* existed. Wrong question, same list.
- ⭐ The collision is the archive's **fifth same-input determinism check**, and the strongest
  form yet: a fresh GUI session, two weeks apart, from a project independently *regenerated from
  the case* rather than copied — and every one of 97 332 bytes agrees (row 191c's premise, again).

What this run adds beyond case34's arm: the finding is now recognized, claimed (row 285) and
executable; the pre-registered port forecast beside it; and a correct as-run `.prj` (case34's
parked project describes whichever sweep arm ran last).

## The prediction scorecard — one miss, recorded as a miss

Registered the morning of the run, before it came back (and, it turned out, scored against data
two weeks old — which changes nothing about their standing as predictions of the port's model):

| registered | measured | |
|---|---|---|
| no NaN anywhere | 0 cells in 948 rows | ✅ |
| deepest ≈ 5.3 m (port 5.33), rebound, trapped | 5.332 m, ends −4.824 m | ✅ |
| ends on the rise/fall count, not bottom, not surface | traps at step 448, t = 254.19 s | ✅ |
| merge near the d = 2 m crossing (port t ≈ 91 s, depth ≈ 4.9 m) | step 309, t = 92.31 s, depth 4.92 m | ✅ |
| **final dilution 600–700** (port 640) | **714.469** | ❌ **miss, 2 % past the band's top** |
| far field present, 500 m distance stop binds, dilution < 10 000× | 500 rows to 503.677 m, 6 350 | ✅ |
| F ≈ 0.0044, the exe computes it anyway | ran clean | ✅ |

On the miss: at the port's **own** end time (t ≈ 243 s) the exe reads 686.7 — inside the band —
and the exe then integrates ~11 s further before its trapping benchmark fires, adding the rest.
So the 11.6 % endpoint gap decomposes into ~7 % of rate (merged from step 309, inside the
post-merge 1–7 % band, plus the slow-current suppression family) and ~4 % of stop timing (the
exe's late-stop family, rows 258b/191b). Decomposition is diagnosis, not absolution: the
registered band was 600–700 and the trace says 714.469.

Other confirmations: wastefield width **51.49 = 24 × 2.00 + 3.493** exact; the far field's first
`Distance` (5.014) equals the near-field end's straight-line offset; `check_farfield_session_state`
returns clean — both stops were typed and the distance bound first.

## Which build

**Legacy** (operator, 2026-09-02) — the filenames carry it, per the archive's classification rule.
The trace itself could not have said: zero discharge-to-current offset makes row 275's width
fingerprint inert. The byte-identity then says one more thing: **whatever binary ran case34 on
2026-08-19 produced bytes identical to the legacy exe's** at this geometry — either case34's
sweep was also the legacy build, or the two builds are bit-indistinguishable here; the trace
cannot separate those, so case34's own files stay classified as they are. No measurement above
depends on the build at this geometry.
