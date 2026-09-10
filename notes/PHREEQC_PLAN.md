# PHREEQC for the chemical equilibrium — the plan

**Status: planned 2026-09-09; the spike (Phase 0) ran the same evening (§8); Phases 1–4 built the
same night on the `equilibrium` branch (the engine, the wiring, ledger rows 287–289, the study rerun);
**done** — and the Davies column's basis slip, the one loose end, was closed on 2026-09-10 (§8, Phase 5).** Queued as [`PLAN.md`](PLAN.md) §7 item 7. Operator's
brief (2026-09-08, PLAN §6): integrate PHREEQC as the speciation engine for the high-pH /
ion-pairing regime PyCO2SYS is extrapolated in, reusing the methods already developed in
Ebb's earlier in-house PHREEQC blending tool ("the blending tool" below), **cloning the code into
this repo so it stays standalone**, and leaving that tool's comparison against a commercial
speciation package behind.

This document is the survey of both sides, the design, the work in order, and the predictions the
work will be scored against. It is the "anything longer goes elsewhere" companion PLAN §0 allows
itself.

---

## 1. Why, in one paragraph

`Ω_brucite` is the number this project exists to produce and the one with nothing to check it
against (ledger row 195). Today it is `[Mg²⁺]_total [OH⁻]²_total / Ksp*`, with `Ksp*` built from
Xiong (2008)'s thermodynamic `Ksp` divided by Davies activity coefficients
(`chem/constants.py::solubility_brucite`). Its error budget, measured 2026-08-21: the `Ksp` band
2.51×, **the activity coefficients 2.14×**, ion pairing unmodelled and one-signed, worst case
5.37×. The two structural terms — activities past the Davies range, and a tenth of seawater Mg
complexed as MgSO₄ with MgOH⁺ growing as pH rises — are **the same problem**: getting from total
concentrations to free-ion activities. A Pitzer ion-interaction model does both at once. PHREEQC
with `pitzer.dat` is that model, open, auditable, and already exercised on exactly this water and
this reagent in the blending tool. It turns today's *upper bound* into a *value with a measured
comparison*, and it moves the study headline: `Ω_brucite = 1` is a pH threshold (9.43 total at
S 32 / T 10 °C), so a lower Ω raises the threshold and raises TA\* above 3660.

## 2. What the blending tool has (surveyed 2026-09-09)

One author, 29 commits, no licence file, no CI, no `pyproject`; validated on Python 3.13, Windows.

**Engine.** `phreeqpython==1.6.2` (IPhreeqc bindings; the PHREEQC library **and** the `.dat`
databases ship inside the wheel, nothing on `PATH`). Constructed everywhere as
`PhreeqPython(database="pitzer.dat")` then `apply_mineral_overrides(...)`. Raw PHREEQC input is
used in exactly one place — a `PHASES` block via `pp.ip.run_string(...)` — and it is load-bearing.

**Database.** `pitzer.dat` by default: the only bundled database valid from dilute to concentrated
caustic *and* carrying Brucite (`phreeqc.dat` has no Brucite at all). Not stored in the repo; not
edited. **One re-parameterisation, applied on every run**: Brucite `log_k` −10.88 → **−10.95**
(Xiong 2008, the same value this repo pinned as `BRUCITE_LOG_KSP_25C` on 2026-08-24) and
`-delta_H` +4.85 → **−0.40 kcal/mol** (the shipped sign is wrong for a retrograde mineral). A
retired `−10.50` fitted to the commercial package is kept there only as a warning constant — do not clone it.

**Core (`mix_calc.py`, 1138 lines, four concerns in one file).** (a) water and base construction
with unit conversion — `make_brine` (SOLUTION from temp, pH, alkalinity as mg/L CaCO₃, major ions
in mg/L, Na charge balance), `make_base` (NaOH/KOH/LiOH/Ca(OH)₂/Mg(OH)₂ by wt %, mol/L, g/L, meq/L
or pH, with iterated per-litre conversions); (b) the engine and mineral overrides;
(c) mixing — PHREEQC `MIX` weighted by **kg of water**, temperature by an external mass-and-cp
balance pushed back in, `equalize` with `in_phase=[0]` so minerals can only precipitate, **one
joint `equalize` for every phase** (sequential brucite-then-calcite put a plateau at pH 8.58 where
the joint solve puts it above 10); (d) CLI, tables, seven runtime caveats. The `blend()` function is
a closure inside `main()` and is re-implemented twice more.

**What it does not have.** No `composition(salinity)` — seawater is a hard-coded S 35 preset in
mg/L (Millero: Na 10781, Mg 1284, Ca 412, K 399, Cl 19353, S(6) 2712, Br 67). No DIC input (the
carbonate system is set by pH + alkalinity). No pH-scale conversion (PHREEQC reports NBS/activity
pH; PyCO2SYS total is ~0.05–0.10 lower on this water). No alkalinity readback from phreeqpython
(two workarounds exist: excess conservative charge, or the species sum HCO₃⁻ + 2 CO₃²⁻ + OH⁻ − H⁺).
No batching, no caching, and the engine accumulates every solution unless `forget()` is called.

**Validation worth cloning.** `validate_thermodynamics.py` (model-independent: pKw vs Harned &
Owen at three temperatures ±0.01, Pitzer single-ion γ vs Millero, log₁₀2 on doubling NaOH in pure
water); `validate_brucite_ladder.py` (brucite `log_k` gate across I = 0.016–1.9 m, a committed
six-line fixture, residual ≤ 0.20 pH); `test_smoke.py` (22 checks, each named after the bug that
motivated it). Recorded agreement against a commercial speciation package: NaOH wt % → pH MAE 0.024 (136
points); the seawater blend scenarios 0.03–0.08 pH at compliance dilutions; **Ω_aragonite from PHREEQC runs 1.64× above
PyCO2SYS, one-signed — "do not report this one from here yet"**; Ω_brucite ±20 % near 25 °C and
low I, widening to 2–3× in cold or concentrated water (the tool's own 8 °C harbour water is "the wide end").

**Leave behind.** `crossvalidate.py`, `validate_vs_oli.py`, `validate_1c.py`, `compare_1c_to_oli.py`,
the four report builders, the three PDFs, the two engine-selection write-ups, `investigation/`
(provenance one-offs), `studies/`, the site-specific water preset (a client transcription), the
metals mixing, the base-construction machinery (this repo states effluents as `(TA, DIC)`), the CLI.

**Performance.** ~2.0 ms per solve with the engine held open. A 200-row run is 0.4 s; the dose
study's 52 cells × 2 ambients × 200 rows is ~40 s serial; the section panels' meshes are the
expensive case and need batching (§4).

## 3. Design

**Hybrid, not a swap.** PyCO2SYS stays the carbonate engine: it is the exe's lineage, its parity
is measured (0.011–0.025 pH to pH 12, row 258/case47) and its `Ω_aragonite` is the one to report.
PHREEQC is added for the quantity it is better at — **the brucite saturation state**, and, as a
diagnostic, its own pH above the parity window. Both engines see the identical conservative
`(TA, DIC, S, T)` row that `chem/transport.py` already produces, so the near field, the mixing and
the carbonate columns are untouched; this is another post-hoc overlay on the trajectory, like the
chemistry already is.

**Composition from salinity.** The one thing to write rather than clone: reference seawater
(the preset above, which is Millero et al.'s S 35 composition) scaled by `S/35` — the same
conservative-with-salinity rule `calcium_from_salinity` and `magnesium_from_salinity` already use,
so the two engines agree on `[Mg²⁺]_total` by construction. TA enters **through the charge
balance**: sodium is set so the conservative-ion excess equals the row's TA (Dickson's definition
verbatim), DIC and boron enter as totals, and `pH charge` makes pH the unknown. ⚠️ *Found in Phase 1*:
PHREEQC's `Alkalinity` keyword gives the identical number when DIC > 0 (to 0.1 µeq/kg) but treats
alkalinity as a *carbon* constraint when DIC is 0 and leaves pH at its guess — which is the
dose-study's pure-water NaOH effluent. The charge form solves both (1 mmol/kg NaOH in pure water:
pH 10.98), so the `(TA, DIC 0, S 0)` endmembers need no special path. Borate: ✅ `pitzer.dat` **carries boron** (B(OH)₃/B(OH)₄⁻ at pKa 9.239, plus the MgB(OH)₄⁺ and
CaB(OH)₄⁺ pairs) and strontium; it lacks fluoride. ⚠️ The spike's first pass *forgot to enter*
boron and PHREEQC's pH sat 0.13–0.31 above PyCO2SYS's at pH 7.7–10, the 367 µmol/kg of borate
alkalinity being read as carbonate — an earlier revision of this paragraph blamed the database; it
was the input. Total boron follows the case's borate option (Uppstrom 0.0004157 × S/35, or Lee),
the same constant PyCO2SYS uses, so the two engines see one boron.

**Engine construction.** `pitzer.dat`, Brucite re-parameterised to Xiong's −10.95 with the
corrected `ΔH`. ✅ *Enthalpy settled 2026-09-09*: the two codes carried different values —
`BRUCITE_DISSOLUTION_ENTHALPY` here is **−2.29 kJ/mol**, derived from standard formation
enthalpies in `constants.py` and checkable; the blending tool's −0.40 kcal/mol (−1.67 kJ/mol) is
the wateq4f/CODATA figure. Both say "nearly athermal, slightly negative"; the override uses **this
repo's −2.29 kJ/mol (−0.547 kcal/mol)** so the two engines share every constant, and the
difference (~1.5 % on `Ksp` over 25 → 10 °C) is noted where the tool's value is cited.

**No `equalize`.** The blending tool precipitates minerals to a plateau pH. This repo's column is the
saturation state of the *unreacted* mixture ("Ω is a thermodynamic statement, not a rate"), so
PHREEQC is asked for `SI` only; precipitation stays with `chem/precipitation.py`'s rate laws.

**pH scales.** PHREEQC's pH is NBS. Derive **free** as −log₁₀ m(H⁺) and **total** as
−log₁₀ (m(H⁺) + m(HSO₄⁻)) from the species molalities (F is absent from the database, so the
seawater-scale HF term cannot be added — say so). Comparisons to PyCO2SYS are made like-for-like on
the total scale; the NBS value is carried as PHREEQC's own.

**Where it lives.** `src/plumes2/chem/pitzer/` (the name says what it adds; the engine is a detail):
`engine.py` (construction, the `PHASES` override, `forget()` discipline), `composition.py`
(`reference_seawater(salinity)`), `solution.py` (one batched `run_string` of many `SOLUTION` blocks
with a `SELECTED_OUTPUT` of `si("Brucite")`, `si("Aragonite")`, `si("Calcite")`, pH, and the H⁺ /
HSO₄⁻ / OH⁻ / CO₃²⁻ molalities — one IPhreeqc call per array, not one Python call per row),
`saturation.py` (`SI → Ω = 10^SI`, scales). Under `chem/`, exported from `plumes2.chem`, with
the same `ConstantSet`-style record of database, `log_k`, `ΔH` and phreeqpython version on every
result, so provenance can carry it.

**Optional dependency.** `plumes2[pitzer]` extra pulling `phreeqpython`. The import is guarded; a
run that asks for the engine without it raises a clear error, a run that does not ask never
imports it. CI adds the extra to the existing matrix (Linux wheels exist for 1.6.2; 3.14 is the
spike's first question). Licence: PHREEQC is USGS public-domain software; check the phreeqpython
wheel's licence at adoption and record it in `references/README.md`; the blending tool has no
licence file and is Ebb's own — the operator confirms the clone into an MIT repo.

**Two columns, permanently (operator, 2026-09-09).** `omega_brucite` keeps its name, its Davies
activity model and its "upper bound" reading; `omega_brucite_phreeqc` (and `ph_nbs_pitzer` as the
diagnostic) is added beside it when the engine is installed, and the two are **never merged and
never switched**: the report shows both, and the physics document explains the gap between them as
the measured size of the activity/ion-pairing term. `CarbonateSettings.pitzer: bool = False` turns the
extra engine on; `results.CHEMISTRY_COLUMNS`, `display.py` units, the USER_GUIDE column table, the
report tiles and the `Ω brucite` panels follow (the panels draw both curves, the bound dashed).

## 4. Work, in order

0. ✅ **Spike — done 2026-09-09 (§8), the operator's stopping point: Phases 1–4 wait for a go.** `uv venv --python 3.14` and `3.13` in the scratchpad, `pip install
   phreeqpython`: do wheels exist for both, on Windows and on `ubuntu-latest`? Build the S 35
   preset as a `SOLUTION` from `Alkalinity` + `C(4)`, confirm pH is the solved unknown, read
   `si("Brucite")`, time one solve and one batched `run_string` of 200. **Gate:** wheels on both
   interpreters (else the extra is 3.13-only and CI's 3.14 leg skips the tests); the batched call
   ≤ 5 ms/row.
1. ✅ *2026-09-09* — **Clone the core.** (`chem/pitzer`: composition, engine, batched speciation; 14 tests.) Brief: The four modules above, lifted from `mix_calc.py` (a)–(c) minus
   base construction and `MIX`; the `PHASES` override verbatim; `forget()` after every batch;
   `validate_thermodynamics.py` and `validate_brucite_ladder.py` re-homed as tests (the ladder
   fixture as data, `--regenerate` dropped — it reads `ebb_tea/data`). `test_smoke.py`'s named-bug
   checks that still apply (readback units, `in_phase` is moot without `equalize`, pKw(T)) become
   tests. Docstrings carry the blending tool's findings, per CONTRIBUTING.
2. ✅ *2026-09-09* — **Wire in.** (`CarbonateSettings.pitzer`, `PITZER_COLUMNS`, provenance, panels, sweep, CLI, USER_GUIDE §8.4.) Brief: The setting, the guarded import, the columns, provenance (engine,
   database, override, wheel version), `plumes2 validate` targets for the rows below, USER_GUIDE
   and `PORTING_THE_PHYSICS.md` text. The gradient panels' meshes go through the batched path; if a
   mesh is still slow, solve at the mesh's resolution in TA–DIC space and interpolate Ω, never
   sub-sample the trajectory.
3. ✅ *2026-09-09* — **Validate.** (Rows 287–289 and their targets; the primer and `solubility_brucite`'s docstring carry the measured ratio.) Brief: The ledger rows in §5, each with a `Target`, tolerances from
   what the reference resolves. Then extend the brucite section of `PORTING_THE_PHYSICS.md` and
   `solubility_brucite`'s docstring: the 5.37× *bound* becomes a *measured difference* between two
   activity treatments, with the `Ksp` band (2.51×) the residual. **The reader-facing primer**
   (activities, ion pairing, what Pitzer and PHREEQC add, how to read two brucite columns) is
   written **with this plan** (operator, 2026-09-09) so the terms are explained before the numbers
   exist, and gains the measured numbers here.
4. ✅ *2026-09-09* — **Rerun.** (Both columns on every cell; the study README's *Two brucite engines* section.) Brief: The dose study and the four effluents with both columns; the headline
   TA\*, the Ω = 1 windows and the pH threshold stated **twice, as a band** — the Davies bound and
   the Pitzer value — in `studies/ebb_dose_study/README.md` and PLAN §0. No default changes: the
   operator decided (2026-09-09) that both columns stay, permanently.

Total: four to five days of work, one new dependency behind the `plumes2[pitzer]` extra (operator,
2026-09-09), no change to any parity number.

## 5. Predictions, registered before the work (the rule in PLAN §8)

| row | claim | prediction | how scored |
|---|---|---|---|
| A | pKw from PHREEQC/pitzer vs Harned & Owen at 8.25 / 25 / 30 °C | within ±0.01 (the blending tool's result, model-independent) | `internal`; a `Target` per temperature |
| B | Brucite ladder: pH at Ω = 1 across I 0.016–1.9 m against the committed fixture | max residual ≤ 0.20 pH, mean ≤ 0.12 (the blending tool's gates) | `internal` |
| C | PHREEQC pH vs PyCO2SYS pH on identical (TA, DIC, S 30.9, T 11.2), **total scale**, pH 7.7–12 | PHREEQC **lower** by 0.03–0.10, growing with pH (it computes 21–35 % more CO₃²⁻ from the same pair) | `diverges` by design, recorded not tuned; the parity window stays PyCO2SYS's |
| D | `Ω_brucite` Pitzer vs today's Davies/total-concentration value along the dose axis | Pitzer **lower by 1.5×–3×**, one-signed, the ratio growing with pH as MgOH⁺ pairing grows; never above the Davies value | `internal`; the ratio at TA 4000, 6000, 20 000 |
| E | The pH threshold for Ω_brucite = 1 at S 32 / T 10 °C (today 9.43 total) | rises by **0.09–0.24** (a factor 1.5–3 in Ω is 0.09–0.24 in pH since Ω ∝ [OH⁻]²) | `internal` |
| F | The study headline TA\* at DIC 2092, intake water, from the Pitzer column | **3900–4400** against the Davies bound's 3660; the 30 °C figure above 3040 in proportion | the study README, rerun; both stated |
| G | `Ω_aragonite` from PHREEQC vs Mucci/PyCO2SYS | 1.5×–1.8× high (the blending tool's 1.64×) — **not reported**, kept as the reason the hybrid is a hybrid | `diverges`, one target |

A miss is recorded as a miss. Row F is the one that reaches a reader; rows C–E are what make it
defensible.

## 6. Risks and what settles them

- ✅ **Wheels.** Settled by the spike: PyPI has binary wheels for 3.12 only, but the source
  distribution bundles the Windows, Linux and macOS libraries and selects one at install, so
  `pip install phreeqpython` works on 3.13 and 3.14 without a compiler (verified on Windows; the
  Linux `.so` is in the sdist for CI). Apache-2.0.
- ✅ **`Alkalinity` + `C(4)` with pH as the unknown** works when DIC > 0: PHREEQC returns the
  entered DIC exactly and solves pH. ⚠️ At DIC 0 it does not (pH stays at the guess), so the port
  states TA through the charge balance instead (§3). ⚠️ Every input must share one basis — mixing
  `mg/L` defaults with `mmol/kgw` is rejected, and converting TA to per-kg-of-water without DIC
  was worth +0.2 pH in the first draft; the port converts every total alike.
- **Charge balance moves pH by up to a unit** in the blending tool's client water (16 % out of balance).
  Reference seawater scaled by `S/35` is balanced by construction; the Na balance absorbs the dosed
  hydroxide's counter-ion exactly. Test: the charge gap of the scaled composition is < 0.1 meq/kg
  before TA is applied.
- **Temperature coverage in `pitzer.dat` is uneven** — Brucite is van 't Hoff only, 24 phases are
  25 °C-only. The site is 11 °C; the blending tool's own caveat widens Ω_brucite to 2–3× in cold water.
  This is the residual the plan does not remove; it is stated as such in PORTING_THE_PHYSICS.
- **The near-field mesh panels become slow.** Settled by batching (one `run_string` per panel) and
  the ≤ 5 ms/row gate; the report already renders in seconds per panel.
- **Two enthalpies.** §3; reconcile before Phase 1 writes the override.

## 8. Spike results (2026-09-09, Windows, Python 3.13 and 3.14 — identical to the last digit)

Setup: `pitzer.dat`; Brucite `log_k` −10.95, `ΔH` −2.29 kJ/mol; reference seawater (mg/kgw) with
Uppstrom boron, scaled to S 30.9; T 11.2 °C; DIC 2092; TA the dose axis. (The table was first
produced with the database's boron species *redefined* at pKa 9.24; re-run against the database's
own pKa 9.239 the pH agreement is 0.000–0.029 and the SI values move by ≤ 0.04 — the numbers
below are the redefined run's, the conclusions are unchanged.) PyCO2SYS on Lueker /
Dickson / Uppstrom, as the port runs it. The script is `studies/pitzer_spike.py`.

| TA | PHREEQC pH total | PyCO2SYS pH total | Ω_brucite Davies (as of the spike; ×1.10 since Phase 5) | Ω_brucite Pitzer | ratio |
|---|---|---|---|---|---|
| 2146 (ambient) | 7.727 | 7.724 | 4.5e-4 | 6.7e-5 | 6.8 |
| 4000 | 9.652 | 9.656 | **3.32** | **0.46** | 7.2 |
| 6000 | 10.961 | 10.990 | 1546 | 188 | 8.2 |
| 20 000 | 12.007 | 12.007 | 1.67e5 | 1.99e4 | 8.4 |

Timing: 1.0–1.1 ms per solve, single or batched (200 `SOLUTION` blocks in one `run_string` with a
`SELECTED_OUTPUT`: 225 ms); well under the 5 ms gate. The engine is deterministic across
interpreters.

**Scored against §5.**

- **Row C — miss, and a good one.** Predicted PHREEQC *lower* by 0.03–0.10. Measured: **within
  0.003–0.03 once boron is entered**, the sign varying (with boron left out of the input it is
  *higher* by 0.13–0.31, which is the borate-alkalinity term). The two engines agree on the carbonate side far better
  than the blending tool's aragonite experience suggested; the aragonite gap there is the mineral
  side, not the pH.
- **Row D — miss, by a factor of ~3.** Predicted the Pitzer Ω 1.5–3× below Davies; measured
  **6.8–8.4×**, rising gently with pH. Decomposed at TA 20 000 (the terms multiply):

  | term | factor | what it is |
  |---|---|---|
  | `[OH⁻]²` | **3.1×** | PyCO2SYS's hydroxide is the *total* (its stoichiometric `Kw`), and in PHREEQC 43 % of that total is the ion pair **MgOH⁺** at pH 12 (45 % at pH 11); the free `OH⁻` is what the brucite product uses |
  | `γ(OH⁻)²` | **1.9×** | Pitzer 0.54 against Davies 0.75 |
  | `γ(Mg²⁺)` | 1.2× | Pitzer 0.26 against Davies 0.31 |
  | Mg pairing | 1.0–1.2× | 0.1 % of Mg paired at the ambient, 16 % (mostly MgOH⁺) at TA 20 000 |

  So the ion-pairing term §1 named *is* there, but it sits on the hydroxide side, squared, not
  on the magnesium side; and the activity term is nearly all `γ(OH⁻)`. Both push the same way, so
  "upper bound" stands — the bound is just looser than the 2.14× the Davies-range argument gave.
- **Row E** follows: a factor 7–8 in Ω is **+0.42 to +0.46** in the pH threshold, 9.43 → ≈ 9.87
  total at S 32 / T 10 °C. Predicted +0.09 to +0.24.
- **Row F** is not measured by the spike (it needs the study rerun), but the table's TA 4000 row
  already shows the consequence: the cell the 2026-09-09 rerun reported as newly supersaturated
  (Ω 3.3) reads **0.46 under Pitzer** — so TA\* moves above 4000 and the 3900–4400 band is at
  risk of being low. Recorded now; scored in Phase 4.
- **Rows A, B, G** not exercised by the spike.

**Two caveats the numbers carry.** The MgOH⁺ share is a database statement — its formation constant
in `pitzer.dat`, not a measurement in this water — and it is the single biggest term, so Phase 3
should quote it as such and compare against the literature value (the seawater MgOH⁺ constant is
measured; the spike did not check the database's against it). And the database's borate constant
carries no enthalpy (`delta_h 0`), so at 11 °C its pKa is the 25 °C value; the residual in row C
(≤ 0.03) is of that size.

**Phase 1 findings (2026-09-09, evening).** With every total on one basis (per kg of water inside
PHREEQC, per kg of solution on the way out) the Davies/Pitzer ratio along the dose axis is **7.6 →
7.9**, nearly flat, and the term-by-term decomposition closes to 2 % once one more factor is
included: **the Davies column's own basis slip**. `omega_brucite` multiplies per-kg-of-solution
concentrations (`[Mg²⁺][OH⁻]²`, three of them) against a solubility product defined on the molal
scale, so it reads `water_fraction³` ≈ **0.91 at S 30.9** below what the same physics gives on one
basis — the only bias in the column that points *down*, ~9 %. Left as it is for now; correcting it
moves row 196's pinned peak (131.4 → ~144) and the study headline by a few percent, which is the
operator's call. Also found: PHREEQC's `Alkalinity` keyword and Dickson's definition agree to
0.1 µeq/kg, but the keyword leaves pH at its guess when DIC is 0, so TA enters through the charge
balance (§3); pKw from `pitzer.dat` is 13.995 at 25 °C and 14.531 at 10 °C against Harned & Owen's
13.995 / 14.535.

**Phase 4 results (2026-09-09, night).** The dose study rerun with `carbonate.pitzer` on every
cell (`studies/ebb_dose_study/README.md`, *Two brucite engines*). Resolved on a 1 µmol/kg grid,
undiluted effluent:

| water | TA\* bound | TA\* Pitzer | pH\* bound | pH\* Pitzer |
|---|---|---|---|---|
| S 30.9 / 11.2 °C (default) | 3660 | **4200** | 9.40 | **9.83** |
| S 30.9 / 30 °C | 3038 | **3720** | 8.64 | 9.09 |
| S 34.5 / 11.2 °C | 3656 | 4250 | 9.33 | 9.81 |
| S 34.5 / 30 °C (baselines) | 3014 | 3770 | 8.57 | 9.07 |
| S 32 / 10 °C (threshold row) | 3702 | 4240 | 9.43 | **9.88** |

Scored: **row F held** — 4200 sits in the 3900–4400 band, by the arithmetic of a pH threshold
rather than by the ratio the band was built on; **row E missed** — +0.45 (9.43 → 9.88) against the
predicted +0.09 to +0.24, the same miss as row D carried through. The pH 9.8 seawater effluent
(TA 4166) is supersaturated by the bound (6.4) and not by Pitzer (0.86); the TA 20 000 port reads
2.0 × 10⁴ against 1.7 × 10⁵; the far-field boundaries sit a decade lower than before (≈ 6 × 10⁻⁵)
and as far from saturation. Rows A and B (pKw, the ladder) became row 287 and the tests; row G
(aragonite) is carried in `PitzerState.si_aragonite` and not reported, as planned. ✅ **Closed
2026-09-10 (operator):** the Davies column's basis slip — see Phase 5 below.

**Phase 5 (2026-09-10): the Davies column on the molal scale.** `omega_brucite` now divides its
per-kg-of-solution `[Mg²⁺]` and `[OH⁻]` by the water fraction before forming the product, so the
three concentration factors and the molal `Ksp` share one basis (`chem/saturation.py`;
`water_fraction` moved to `chem/constants.py` and is shared with the Pitzer composition). Every
seawater Ω in the Davies column rose `1/w³` — 1.10 at S 30.9, 1.11 at S 35 — pure water is
unchanged, and the pH threshold fell `1.5 log₁₀ w` = 0.02. Row 196's peak re-pinned 131.4 → **146.3**
(the plan's estimate was ~144); row 289's ratio 7.9 → **8.7** at TA 20 000 (8.3 at the ambient),
because the 0.91 the decomposition carried is gone and the four physical terms are the whole ratio.
The bound's ceilings, undiluted, on the same 1 µmol/kg grid:

| water | TA\* bound (was) | pH\* bound (was) | TA\* Pitzer | pH\* Pitzer |
|---|---|---|---|---|
| S 30.9 / 11.2 °C (default) | **3632** (3660) | 9.38 (9.40) | **4200** | **9.83** |
| S 30.9 / 30 °C | 3010 (3038) | 8.62 (8.64) | 3720 | 9.09 |
| S 34.5 / 11.2 °C | 3624 (3656) | 9.31 (9.33) | 4250 | 9.81 |
| S 34.5 / 30 °C (baselines) | 2983 (3014) | 8.55 (8.57) | 3770 | 9.07 |
| S 32 / 10 °C (threshold row) | 3673 (3702) | 9.41 (9.43) | 4240 | 9.88 |

The Pitzer column did not move: it was already on one basis. The band the study reports is now
3630–4200.

**The solver selector (2026-09-09, later that night; operator).** `carbonate.solver` — `none`,
`pyco2sys` (default) or `phreeqc` — chooses the engine for *every* chemistry column; `pitzer: true`
stays the "second column beside the default" and is rejected under any other solver. Under
`phreeqc`, `omega_brucite` is the Pitzer value and the carbonate minerals are PHREEQC's own. That
let **row G** be scored on the site water: predicted 1.5–1.8× above Mucci's, **measured 1.02 at
ambient pH and 1.11 at the pH 10.5 port** — a miss in the good direction. The blending tool's 1.64×
was its own low-calcium 8 °C harbour water plus a pH-scale slip, not a property of the engine; on
reference seawater scaled to S 30.9 the two engines agree on the carbonates to the order the exe and
PyCO2SYS do. `solver: none` gives a chemistry-free run whatever tables the case carries.

## 7. Out of scope, deliberately

PHREEQC's `MIX` and `equalize` (this repo's mixing is verified conservative and its Ω is
unreacted); base construction by wt % (effluents are `(TA, DIC)` here); trace metals (not in
`pitzer.dat`, not this project's question); replacing PyCO2SYS for pH or `Ω_aragonite`; any
fitting to a commercial package's output; a `-analytic` temperature expression for Brucite (the blending tool's own next item — worth
doing later if row E's temperature sensitivity matters to a claim).
