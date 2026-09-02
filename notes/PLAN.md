# plumes2 — project plan

**Current state and what is next.** Rewritten 2026-08-26 as a short document that is read at the
start of every session; the 5 600-line build log it replaced is [`PLAN_HISTORY.md`](PLAN_HISTORY.md),
frozen, and is for searching, not reading. Companions: [`PORTING_NOTES.md`](PORTING_NOTES.md) (the
decoded specification), [`LEDGER.md`](LEDGER.md) (every finding, one row each, executable),
[`PORTING_THE_PHYSICS.md`](../PORTING_THE_PHYSICS.md) (what to trust, for users),
[`USER_GUIDE.md`](../USER_GUIDE.md) (every flag, field and column), [`SSMC_REPORT.md`](SSMC_REPORT.md)
(the defects for the maintainers), [`ENVIRONMENT.md`](ENVIRONMENT.md) (toolchain).

**How this file is kept short.** Sections 1–8 describe the *present*; §9 is a changelog of one to
three lines per entry, newest first, capped at about fifteen entries; §10 maps the old section
numbers other documents cite to their headings in the history. When a finding needs more than a
few lines, it goes in the case README, the ledger row, or the study write-up — and one line here
points at it. Dated narrative, tables of intermediate results, retractions-in-place and predictions
belong in those places or in the history, never here.

---

## 0. Read this first

- **Purpose**: a Python re-implementation of PLUMES2.0 (library + CLI + plots) so that pH and
  brucite saturation in the plume of an **alkalinity-elevated discharge** can be iterated in a
  notebook. Parity with the exe is the floor; `Ω_brucite`, which the exe cannot report, is the point.
- **Where it stands**: phases 0–8 done, Phase 9 (the dose study) has run at Ebb's default profile.
  Ledger **191 of 191** countable rows executable (`plumes2 validate`; 198 targets).
- **Headline result** (Phase 9): below **TA ≈ 4340 µmol/kg at DIC 2500** the discharge never
  supersaturates brucite, even undiluted; above it the centreline window is ≤ 25 cm and ≤ 10 s, and
  the mixing-zone boundaries see ≤ +0.04 pH. `studies/ebb_dose_study/README.md`.
- **Largest known residual**: merging, a spacing-dependent tilt of about ±0.10 in the entrainment
  suppression (1–7 % post-merge past `d/L` 3). Second-order; deliberately not being chased (§6).
- **Next** (§7): Ebb's *measured* ambient chemistry below 4 m (the held rows are placeholders by
  design). The flag decode is **finished** — both rounds ran and graduated 2026-09-01 (case51,
  case52). The SSMC report is drafted and **on hold at the operator's request (2026-09-01) — do
  not prompt about sending it**.
- **Rules that bite** (§8): run the suite with `-n auto --dist loadfile`, never bare `-n auto`; the
  full suite is ~4 min — run targeted modules and ask before the whole thing; never edit
  `upstream/` or exe-produced data files; every generated exe experiment carries its predictions
  *before* the run; no `PR_BODY.md` in the repo.

## 1. Goal and non-goals

Importable, driveable from a CLI, plottable — outfall dilution and receiving-water chemistry
iterated in code instead of clicked through a Windows GUI. **Non-goals**: wrapping or decompiling
`plumes2.0v1.exe` (no source is published; this is a re-implementation from the manuals, the UM3
literature and archived traces; BSD-2 permits it); reproducing the Winteracter GUI; speed.

## 2. Standing decisions

| decision | choice | note |
|---|---|---|
| interface | library + CLI + plots; results are dataframes, `.dat` is a formatter over them | sweeps are list comprehensions |
| formats | byte-exact round trip of `.prj` / CSV / `.dat`, plus native YAML | `Case` is the whole input; the `.prj` is a lossy export |
| chemistry engine | **PyCO2SYS**; the exe's option numbers map 1:1 (K1K2 1–14, KSO4 1–4 combined) | gaps vs the exe measured and pinned, never tuned |
| exe defects | **correct by default, reproduce on request** — `reproduce_*` flags on `CarbonateSettings` and `DoBodSettings` | see PORTING_THE_PHYSICS |
| equation of state | `EOS80` default; the exe's is **Knudsen (1901)**, selectable (`EquationOfState.KNUDSEN`) | row 262: 0.00098 kg/m³ worst over 51 670 rows, zero parameters |
| near-field entrainment | UM3's structure re-derived from trace measurements (cite-and-re-derive; SFEI's GPL source is corroboration, not copied) | licence decision 2026-08-13 |
| merging decrements | `ConfinedDecrements.ALL` default (since 2026-08-21) | UM3's own documented mechanism; 0.98 % post-merge out of sample |
| similarity profile | `parabolic` default (the exe's default); `three_halves`, `exe_gaussian`, `gaussian` selectable per case | operator decision 2026-08-26; centreline Ω extent +16 % under `gaussian` |
| brucite `log Ksp` | **Xiong (2008) −10.95 ± 0.2** | operator decision 2026-08-24; `−11.16` (wateq4f lineage) stays callable |
| far field | Brooks is the family's only working far field; **4/3 law** for open water (constant-eddy for channelised sites is a *site* decision) | all three laws now confirmed against the exe (rows 116, 280, 280b) |
| far-field stops | `max_distance` 500 m, `max_dilution` 10 000× — the operator's usual exe entries | the exe stores neither; row 277 censuses the archive |
| stop-at-surface | `stop_at_surface=False` default; the `.prj`'s `nearfield_flags[1]` **is** the box (1 = stop) | row 187 / case46 |
| DO and carbonate | coexist; the manual's XOR is not enforced by the exe and not inherited | 8.6 |
| Python | 3.14.4, floor 3.13 | ENVIRONMENT.md |

## 3. Repository and document map

```
upstream/            verbatim ssmc-uw/PLUMES2.0 snapshot -- READ ONLY (exe, manuals, example)
references/          third-party sources the manuals cite; README.md is the digest.
                     ⚠️ Millero (2010) and Cenedese & Linden (2014) are NOT public domain --
                     they are git-TRACKED, so publishing needs a history rewrite, not a rm
reference_cases/     one folder per exe run + README; pending/ holds generated experiments
                     awaiting the exe (empty as of 2026-09-01, night)
studies/             the dose study, the dry run, the experiment generators, example_case.yaml
examples/            the library-consumer quickstart (plain-CSV ambient tables), suite-executed
notes/               this file and the other planning/dev docs (PLAN_HISTORY, LEDGER,
                     PORTING_NOTES, MANUAL_DIGEST, SSMC_REPORT, ENVIRONMENT)
src/plumes2/         the port          tests/   the suite (2 500+ tests)
```

| question | document |
|---|---|
| how do I call it as a physics package | `examples/README.md` |
| how do I run it / what does field X mean | `USER_GUIDE.md` |
| what is verified, to what precision | `LEDGER.md`, `plumes2 validate` |
| what to trust, where it degrades, which defects are flagged | `PORTING_THE_PHYSICS.md` |
| how a file format or equation was decoded | `PORTING_NOTES.md`, `MANUAL_DIGEST.md` |
| what a specific exe run showed | `reference_cases/caseNN_*/README.md` |
| why a decision was taken, how a finding was reached, what was retracted | `PLAN_HISTORY.md` (search it) |
| what to tell the maintainers | `SSMC_REPORT.md` |

## 4. Architecture

`src/plumes2/`: `config.py` (pydantic `Case`, frozen), `units.py`, `seawater.py` (EOS-80 and
Knudsen), `ambient.py`; `nearfield/` (`state`, `entrainment` — UM3 closure, `geometry`, `merging` —
eqs 51–56 + `ConfinedDecrements`, `terminate`, `solver`); `farfield/` (`brooks`, `standalone`);
`chem/` (`constants` — the option map and every `Ksp`, `speciation` — the PyCO2SYS adapter,
`saturation`, `precipitation`, `transport`); `biochem/do_bod.py`; `crossplume.py` (the four
similarity profiles); `io/` (`prj`, `csv_tables`, `dat` + `dat_format`, `yaml_case`, `project`);
`results.py`, `sweep.py`, `experiments.py`, `validation.py` (the executable ledger),
`provenance.py`, `display.py`, `comparison.py`, `plotframe.py`, `report/`, `cli.py`.

Rules: results are dataframes; every physics module is callable alone; no global state; SI inside,
units only at the boundary; provenance never enters a byte-exact artefact.

## 5. Status by phase

| phase | what | ledger | accuracy / what to know |
|---|---|---|---|
| 1 legacy I/O | `.prj` + 6 CSVs + `.dat`, readers and writers | 20/20 | byte-exact round trip on every archived trace; the `.dat` reader splits on the 10-column grid (fields can collide) |
| 2 seawater | EOS-80 default, Knudsen identified as the exe's | 11/11 | switching to Knudsen buys parity, **not** accuracy (row 148 refuted) |
| 3 Brooks far field | three laws, standalone calculator | 21/21 | equations exact (5e-6 vs the exe's own calculator); width 1e-5; **all three laws** confirmed (case50). Dilution at the handoff is the near-field endpoint's error, not Brooks' |
| 4 chemistry + DO/BOD | PyCO2SYS, Ω (arag/calc/**brucite**), precipitation, path-integrated DO | 43/43 | exe pH within 0.011–0.025 of PyCO2SYS from pH 8.4 to **12.0** (case47); scalar columns print one step ahead of `Dilutn` (row 258c) |
| 5 near field UM3 | LCV solver, UM3 entrainment, merging, termination | 72/72 | jet 0.31 %; cross-flow 0.34–0.88 %; post-merge 1–7 % past `d/L` 3 (the residual); zero-current post-trapping drift ~5 % on one run (test23) |
| 6 output | byte-exact `.dat`, tidy CSV + provenance, HTML report, comparisons | 21/21 | the exe has **three** similarity profiles; the parabola is its default |
| 7 validation | the executable ledger, docs, PORTING_THE_PHYSICS | 1/1 | coverage figures in four documents are test-checked against the registry |
| 8 beyond parity | `Ω_brucite` (upper bound; 5.37× worst-case band), out-of-range warnings, sweep harness, profile decision, far-field decision | 2/2 | `Ω_brucite = 1` is a pH threshold: **9.43 total at S 32, T 10 °C** (moves ~0.05 pH/°C) |
| 9 dose study | fixed-DIC TA axis at Ebb's default (Macoma) profile | — | headline in §0; chemistry below 4 m is *held*, the stated assumption to replace |

Recorded divergences inside the green counts (rows 17, 116, 157b, 171c/d, 186, 264c): the
ledger labels them `diverges`; "executable" means measured, not agreeing.

## 6. Open items

**Residuals, known and bounded (not being chased now — see "not now")**
- Merging: suppression tilt ±0.10 across spacings, zero-crossing near 0.64 m (row 276); the exe's
  suppression depends on trajectory stage at merge onset (row 266) and port count (`1/n_ports`,
  row 271). Candidates are derivation, not data.
- Zero-current post-trapping entrainment suppression the exe applies and the port lacks (test23,
  5 % late window); one valid comparison run exists. Mechanism named by a 4th-edition sentence
  ("UM3 addresses the overlap problem"), not measured.
- Exe stop-lag family: surface stop 14 steps / +8.6 % past contact (row 258b); single-port
  limiting-spacing banner lag in "regime B" (~17 steps, row 191b); far-field dilution stop 1–4 rows
  late.
- `Ω_brucite` absolute value: ion pairing + Davies past its range are co-dominant with the `Ksp`
  band (2.14× and 2.51×). Today's Ω is an **upper bound**; trends and the pH threshold are sound.

**Inputs and diligence still owed**
- Ebb's measured ambient chemistry below 4 m — the held rows are **placeholders by design**
  (operator, 2026-09-01); replace them in `studies/ebb_dose_study/ebb_macoma_default.yaml` *and*
  `examples/macoma_ambient_chemistry.csv` when data exists, and rerun the study.
- ✅ *Resolved 2026-09-01*: the Macoma 17 m seabed / 15 m profile is **intentional** — there is no
  measurement at 17 m, and the profiles are notional because the depth changes with the tides
  (operator). The `GeometryWarning` stays as a statement of extrapolation, not a suspicion.
- ✅ *Resolved 2026-09-01*: Xiong (2008) is now cited directly (Aquatic Geochemistry 14:223–238,
  doi:10.1007/s10498-008-9034-3); the operator waived the verification read.
- ✅ *Resolved 2026-09-01* — both flag-decode rounds ran the day they were generated (**case51,
  case52**, rows 281–283). The complete map: near-field 1/2/3 are the **bottom / surface /
  shoreline stop boxes**, 4 the rise/fall count, 5–6 non-dialog constants; far-field 1 and 5
  **each gate the far field** (no dialog control), 2/3/4 the eddy law, 6 a non-dialog constant,
  7 exe-owned. ⚠️⚠️ **Never write near-field flag 3 = 1 against a zero shoreline vector** — the
  exe fails silently and truncates the project (row 282). The base arm's width fingerprinted the
  build (legacy, deliberate), retiring the case42–45 attribution question.
- Licence: Millero (2010) and Cenedese & Linden (2014) in `references/` may not be redistributed;
  publishing the repo needs a history rewrite (they are git-tracked).
- TODO: a CI workflow (`pytest -n auto --dist loadfile -m "not slow"`) — the suite discipline is
  currently enforced only by CONTRIBUTING.md.

**Optional exe runs, none blocking**: case12 with the shoreline box unchecked; case03 with
KSO4 = 3 (borate half of the selector); 0.3 / 0.4 m ports at case30's geometry (row 191b's lag
onset); a sinking sub-critical discharge (`subcritical_sinks`, never generated); an ambient DO
profile whose depth-mean is far from its trapping-depth value.

**Not now, and why**: the merging tilt (second-order, derivation not data); solver speed (audited,
no hot spot); the other far-field methods (DKHW/NRFIELD/PDS are *near-field* models — a category
error); a GUI; time-varying ambient (no driver); the `Ω_brucite` ion-pairing / Pitzer treatment
(**future work**, operator 2026-09-01 — today's upper bound and pH threshold serve every current
claim).

## 7. Next actions, in order

1. **Replace the held chemistry rows** (placeholders by design) in
   `studies/ebb_dose_study/ebb_macoma_default.yaml` and `examples/macoma_ambient_chemistry.csv`
   with measured values below 4 m when Ebb has them, and rerun `studies/ebb_dose_study.py`;
   rewrite the headline if TA* moves (it is set by pH*(S, T) and the intake DIC, so it should
   not move much).
2. Optional exe runs above, as convenient.

(The SSMC report is **on hold at the operator's request** — held until they say send, not a step
here. The Pitzer treatment is future work, §6.)

## 8. Working rules

- **Traceability.** Every input to a run must be recoverable from what the run produces. The exe
  fails this (chemistry, DO, the stop boxes, the far-field stops and the output-column selection are
  session state the `.prj` does not carry; the `.dat` has no provenance and rounds inputs to two
  decimals). The port answers with `Case` round-tripping through YAML, a provenance sidecar (code
  version, commit, dirty flag, case SHA-256, time, platform) and `plumes2.experiments`, which writes
  each exe experiment with its GUI-only settings and pre-registered predictions beside the `.prj`.
  The exe writes the `.prj` on every run — copy a returning run aside before the next.
- **Ledger.** One row per finding, numbers never reused, retractions struck through in place. A
  row is ✅ only if a `Target` in `validation.py` re-derives it; tolerances come from what the
  reference can resolve, never from what the code produces. Coverage figures in `PLAN.md`,
  `LEDGER.md`, `PORTING_THE_PHYSICS.md` are test-checked against the derived counts — update all
  of them together. Adding a ledger row means: the row, its bucket heading count, the identity set
  and the mechanical row-count pin in the tests, and a `Target`.
- **Experiments.** Predictions before the run, in the note. A miss is recorded as a miss. Score
  far fields on the trace's own first row (`w₀`, `D₀`, origin), not end to end from our near field.
- **Tests.** `pytest -n auto --dist loadfile` (per-file distribution preserves the shared
  fixtures); `-m "not slow"` is a real fast lane; the ledger's measured outcomes are cached on disk
  keyed by a digest of `src/` and the archive (`PLUMES2_NO_CACHE=1` disables). Full suite ~4 min —
  ask before running it.
- **Archive.** `validation._archive_traces` globs `reference_cases/*/*.dat` one level deep, so
  `pending/` is invisible and graduating a case can move archive-wide counts (de-duplicated by
  content hash; the EOS census band is 50 000–62 000 rows). A trace with `legacy` in its filename
  classifies as the pre-2026 build.
- **Documents.** This file stays under ~300 lines. `PLAN_HISTORY.md` is frozen — do not append to
  it. New narrative goes to the case README, the study README, or the ledger row.

## 9. Changelog (newest first; ≤ 15 entries)

- **2026-09-01 (night)** — ⚠️ **Macoma's port spacing corrected: 2 ft (0.6096 m), not 2 m**
  (operator; the archived case03 stays as entered — its "2.0" was the Dec-2025 feet entry, row 49,
  re-typed as metres). Dose study rerun: the headline and every Ω = 1 crossing are unchanged
  (the default flow never merges, end `d/L` 0.89); the far-field boundaries moved (acute dilution
  548 → 633, chronic 1852 → 4319) and the 5 L/s flow cells now merge to `d/L` 3.85 — their end
  dilutions carry the post-merge ±7 % caveat. Study README, example, YAML and tests updated.
- **2026-09-01 (evening)** — the flag-decode suite **ran and graduated as case51** (legacy build,
  deliberate). Far-field flags 1 and 5 each gate the far field; flag 7 is exe-owned; nf 1/5/6 +
  ff 6 file-owned, inert on a surfacing run; ⚠️ **nf 3 = 1 fails silently and truncates the
  project** (rows 281, 281b, 281c, 282). Round 2 ran the same night: **near-field 1 is the
  stop-at-bottom box** (case52, row 283; the pre-registered forecast landed 21.409 s / 97.2
  against a predicted ~21 s / 93), the recon checklist named nf 3 as the **shoreline-stop box**
  and showed nf 5/6, ff 1/5/6/7 have no dialog control. Every flag now has an owner; ledger
  191/191, 198 targets.
- **2026-09-01 (pm)** — open items dispositioned by the operator. The Macoma 17 m/15 m geometry is
  **intentional** (no data at 17 m; tidal depth, notional profiles); the held chemistry rows are
  placeholders awaiting data; SSMC report **held, do not prompt**; Pitzer → future work. Xiong
  (2008) and the Frick quote both cited directly. The **flag-decode suite generated** —
  `pending/flagdecode_*`, nine projects, one unknown flag flipped each; its base arm fingerprints
  the exe build (retires the case42–45 attribution question). §6's "near-field flags 2, 6" was
  stale — the unknowns are positions 1, 3, 5, 6. `reference_cases/README.md` manifest extended to
  all fifty-one cases.
- **2026-09-01** — collaborator prep. Root decluttered: the planning/dev docs moved to `notes/`
  (all links rewritten; `tests/test_validation.py` follows). Library-consumer surface:
  `ambient_from_files` (plain-CSV ambient tables), `run`/`sweep`/`mixing_zone_values` re-exported
  from `plumes2`, `examples/` with a suite-executed worked script, README quickstart + glossary,
  `CONTRIBUTING.md`. Stale prose fixed (PORTING_NOTES status line, the 135/49/"four" counts, old
  `PLAN §Nx` citations now point at PLAN_HISTORY). pyproject no longer claims upstream's licence;
  the port's own code is **MIT** (root `LICENSE`, operator's decision 2026-09-01) and the
  package URLs point at this repo.
- **2026-08-26 (pm)** — `generated/` retired: its data were byte-duplicates of case13/14 and case22–28, the
  seven pre-run experiment notes now sit beside their traces as `EXPERIMENT_NOTE_*.md`, and
  `example_case.yaml` moved to `studies/`. `PLAN.md` cut to a current-state document; the build log is
  `PLAN_HISTORY.md`. **case50**: the far-field law selector is far-field flags 2/3/4 one-hot;
  `Constant` and `Linearly varying` reproduce the port's Brooks to 2e-4 on dilution; the exe's
  linear **width** is `1 + βx/w₀` where the manual's eq 11 prints `1 + 2βx/w₀` — a manual typo the
  port had copied, fixed (rows 280, 280b; SSMC item 19). Two reader defects fixed (`based` required
  in the preamble; the preamble read as a table heading). Ledger 186/186.
- **2026-08-26 (am)** — `USER_GUIDE.md` written and test-pinned. 8.4 reworked and decided:
  `similarity_profile` per case, `parabolic` default (operator). **Phase 9 ran** at Ebb's default
  (Macoma) profile: no brucite supersaturation below TA ≈ 4340 at DIC 2500. case47's far field
  examined (0.010 pH gap, seam exact, dose runs stopped at 5 000× not the declared 10 000×). case49:
  the non-default profiles blend round→slab by the parabola's linear law (row 279). `flags[3]` is
  the rise/fall count. SSMC report drafted (18 items). `t = 0` dilution floored at 1 (one-ULP bug).
- **2026-08-25** — Phase 9 dry run: the dose axis is **TA at the intake DIC**, not TA at a held pH;
  `Ω_brucite = 1` is a pH threshold (9.43 total at S 32, T 10 °C); the risk window is centimetres
  (§8b's "30 s / 100×" retracted). case47 `dose_parity`: exe CO2SYS within 0.011–0.025 pH to pH 12
  — `PH_PARITY_WINDOW` 7.5–12.05. Fixed-width `.dat` field collision found and fixed. case46:
  `nearfield_flags[1]` is the surface-stop box. case48: three similarity profiles enumerated (row
  278; row 198 rescoped). Ebb's discharge spec confirmed: (TA, DIC), or (TA, pH) when DIC is 0.
  Row 258c closed: scalar columns print one step ahead of `Dilutn`. Ledger 184/184.
- **2026-08-24** — brucite `log Ksp` → Xiong (2008) −10.95 (every Ω fell 1.62×). 8.3 sweep
  machinery + far-field chemistry + `mixing_zone_values`. 8.5 assessed: Brooks is the only far
  field; 4/3 law chosen. Far-field stop census (row 277); `max_dilution` → 10 000×. The `.prj` has
  no far-field settings block. The exe has no Save-As — the `.prj` is the as-run state.
- **2026-08-21** — `ConfinedDecrements.ALL` located (decrement radius asymmetry), validated out of
  sample (case42, 0.98 %), made default; case43 port-count sweep confirms `1/n_ports` and matches
  Cenedese & Linden's pair asymptote within 3.7 %; row 260's "plateau at 0.60" retracted as a
  pooling artefact. `Ω_brucite` error budget measured (5.37× worst case). `ConstantRangeWarning`.
  Suite 420 s → 187 s (shared ledger outcomes + on-disk cache). Phase 7 complete.
- **2026-08-20** — EOS identified as **Knudsen (1901)** (row 262); row 148 refuted — the late
  drift is a post-trapping entrainment suppression, not the EOS. Merging block executable; the
  runaway is a finite-time singularity (`db/dt ∝ b²`), so no coefficient can fix it. Legacy far
  field predictable from the case (`ExeBuild`). Muellenhoff (1985) read: entrainment was a *maximum*
  in OUTPLM.
- **2026-08-19** — row 258's "40 % endpoint gap" was a checkbox (`stop_at_surface`); aragonite
  zero band is `25 ≤ S ≤ 35`, a gap not a floor; merging-banner lag resolved into three regimes.
- **2026-08-18** — far-field DO: eq 28's `/D` is absent from the exe (DO = −185 mg/L at cBOD5
  1000; −1.86 from 20 mg/L at a fast rate); IDOD is subtracted from the ambient. Phase 4 done.
  Ledger moved to `LEDGER.md`; denominator derived, not hand-counted.
- **2026-08-17** — DO is path-integrated along the trajectory (eq 23 is the uniform-ambient
  special case); the peak-to-mean law `max(1.5, 2.5 − 0.5 d/L)` (row 203); report and comparison
  layers landed; code audit (1.4× solver, suite halved).
- **2026-08-13** — UM3's entrainment algorithm found in SFEI's open-source Visual Plumes; Taylor
  shear is `α(|V| − u₁)` and the cylinder term cancels; cross-flow sweep 21 % → 0.34–0.88 %. Merging
  (eqs 51–56) and termination (an ordinal count of turning points) landed. Licence: cite and
  re-derive.
- **2026-08-12** — 3rd edition obtained; `A_p` fully specified; chemistry decision: PyCO2SYS is the
  engine. Repository split into `upstream/` and ours.

## 10. Where the history is

Other documents and docstrings cite the old plan by section. The headings are unchanged in
`PLAN_HISTORY.md`; search for the heading text.

| cited as | heading in `PLAN_HISTORY.md` |
|---|---|
| §1, §2, §2b | `## 1. Goal`, `## 2. Decisions made`, `## 2b. Audit against the UM theory reference` |
| §3, §4 | `## 3. Repository layout and provenance`, `## 4. Architecture` |
| Phase *N* | `### Phase N — …` under `## 5. Phases` (Phase 4: DO/BOD; Phase 5: the near-field narrative, merging, termination; Phase 6 and §6b: the report and the profile law) |
| 8.1 – 8.6, §8b (brucite) | `### Phase 8 — Beyond parity` → `#### ⏳ Phase 8's remaining work`, `### 8b. ⭐ Brucite saturation state` |
| §6 (ledger), §7 (open questions), §7b (traceability), §7c (limiting spacing) | `## 6. Validation ledger`, `## 7. Open questions for you`, `## 7b. Traceability`, `## 7c. ✅ The limiting-spacing rule is real` |
| §8 (risks), §8b (where things stand; merging), §8c (audit; TODO 1 stop boxes, TODO 2 far-field extent), §8d, §8e (scope), §8f (dose dry run) | `## 8. Risks`, `## 8b. Where things stand (2026-08-20)`, `## 8c. The code audit`, `## 8d. The 2026-08-21 audit`, `## 8e. Scope for the next phase`, `## 8f. ⭐⭐ 2026-08-25: Phase 9's first dry run` |
| §9 | `## 9. Immediate next steps` |
