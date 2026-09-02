# reference_cases/pending/

Generated projects waiting on the executable. Each carries its `.prj`, any ambient side-tables,
and a README with **predictions registered before the run** — a prediction recorded afterwards is
a fit. Written by `plumes2.experiments`; once a run comes back the directory graduates to
`reference_cases/caseNN_*`.

⚠️⚠️ **Read this before writing another experiment: the exe has no Save-As for projects.** It
writes the `.prj` when the model **runs** (operator, 2026-08-24). Two consequences, both learned
the hard way that day:

- an experiment cannot ask for a saved project *without* a run — the first cut of the surface-stop
  pair did, and was unperformable;
- a returning run must be **copied aside before the next one**, because the next run overwrites the
  `.dat` and rewrites the `.prj`. Supporting tables (ambient, DO, carbonate) *can* be saved
  individually.

⭐ The upside: a generated project comes back as the **as-run** state, GUI settings included — so
the file records more of the session than PLAN_HISTORY §7b credited it with.

⚠️ **Graduating is not just a move.** `validation._archive_traces` globs `reference_cases/*/*.dat`,
one level deep, so a trace in `pending/` is invisible to every archive-wide target and a graduated
one is not. Two things have to be right before the move:

- **build classification.** A trace carrying `legacy` in its filename classifies itself
  (`validation._is_old_build`); otherwise it is assumed current. Three separate old-build runs have
  landed in current-build folders and each failed ledger row 96 by ~13.6 m until someone noticed.
  case46 holds both builds deliberately and its filenames say which is which.
- **what the new rows do to existing sweeps.** Graduating case48 put 573 exceptions into row 198,
  whose claim is that there are none — correctly, because the row had an invisible scope. That is
  the *point* of graduating rather than an argument against it.

## ⏳ In the queue (updated 2026-09-01, night)

**Nothing is waiting on the exe.** Both flag-decode rounds ran and graduated the day they were
generated — round 1 as [`case51_flag_decode`](../case51_flag_decode/README.md), round 2's
bottom-hit pair as [`case52_bottom_stop_flag`](../case52_bottom_stop_flag/README.md), and the
filled reconnaissance checklist into case51. Every `.prj` flag now has an owner and, where one
exists, a dialog control.

## Graduated

The 2026-08-24 `surface_stop_prj_pair/` by-product (the unperformable first cut of the surface-stop
pair, whose two legacy-build traces still confirmed row 277 out of sample) was folded into case46
on 2026-08-26 rather than graduated on its own.

| was | is now | what it settled |
|---|---|---|
| `surface_stop_pair_v2/` | [`case46_surface_stop_flag`](../case46_surface_stop_flag/README.md) | `nearfield_flags[1]` **is** the stop-at-surface box, 1 = stop. PLAN_HISTORY §8e debt 3 closed |
| `dose_parity/` | [`case47_dose_parity`](../case47_dose_parity/README.md) | The exe's CO2SYS holds to **0.011–0.025 pH** from 8.37 to 11.99 and does *not* diverge at the top. Phase 9's pH axis is parity-checked end to end |
| `style_enumeration/` | [`case48_similarity_profiles`](../case48_similarity_profiles/README.md) | The exe has **three** similarity profiles and the selector really picks one — 2.00000 / 3.88997 / 3.66998. Ledger row 278; row 198 rescoped |
| `profile_merged_three_halves/`, `profile_merged_gaussian/` | [`case49_profile_blend`](../case49_profile_blend/README.md) | The non-default profiles walk round → slab by the parabola's linear law (0.002). Row 279 |
| `eddy_law_constant/`, `eddy_law_linear/` | [`case50_eddy_law_selector`](../case50_eddy_law_selector/README.md) | Far-field flags 2/3/4 are the one-hot law selector; both laws match the port's Brooks to 2e-4; the manual's eq 11 has a stray factor of two. Rows 280, 280b |
| `flagdecode_*/` (nine, round 1) | [`case51_flag_decode`](../case51_flag_decode/README.md) | Far-field flags 1 and 5 each gate the far field; flag 7 is exe-owned; nf 1/5/6 + ff 6 file-owned and inert on a surfacing run; ⚠️ **nf 3 = 1 fails silently and truncates the project**. Rows 281, 281b, 281c, 282 |
| `flagdecode2_bottomhit/`, `flagdecode2_bottomhit_nf1/` | [`case52_bottom_stop_flag`](../case52_bottom_stop_flag/README.md) | **Near-field flag 1 is the stop-at-bottom box** (1 = stop): identical to contact at step 231, the cleared box sails 14 printed rows past it. Row 283 |
| `flagdecode2_recon/` (no runs) | [`case51_flag_decode/RECON_CHECKLIST.md`](../case51_flag_decode/RECON_CHECKLIST.md) | nf 3 is the **shoreline-stop box** (row 282's mechanism); nf 5/6, ff 1/5/6/7 show **no dialog control** |

⚠️ **When a run comes back**: `plumes2.experiments.check_farfield_session_state(dat, case)` holds
it to the far-field stops it declared — the ones the `.prj` cannot carry (ledger row 277).
