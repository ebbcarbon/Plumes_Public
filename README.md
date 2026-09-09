# plumes2-python

A Python re-implementation of **PLUMES2.0** — the EPA/PNNL/UW-SSMC outfall plume
model (UM3 near-field + Brooks far-field, with carbonate chemistry and DO/BOD) —
built so that dilution and receiving-water chemistry can be iterated on in a
notebook instead of clicked through a Windows GUI.

The immediate driver is **predicting pH in the plume of an alkalinity-elevated
discharge**.

Status: **Phases 0–8 complete; Phase 9, the dose study, has run.** The file I/O round-trips
byte-exactly, the near-field solver clears upstream's own 0.5 % acceptance bar, Brooks is
confirmed against the exe's own independent calculator, the chemistry and dissolved-oxygen
modules reproduce every archived trace, and the validation ledger is *executable* and
**complete — 195 of 195 countable rows**: `plumes2 validate` re-derives every published
number rather than restating a typed one.

⚠️ **Parity is not the goal, it is the floor.** What the port exists to do — predict the
pH and mineral saturation of an alkalinity-elevated plume — is a question the executable
cannot answer at all.

**The study has run** (2026-08-26; rerun 2026-09-09 at the site's **5900 L/h** with intake water as the
effluent, on both ambients — the 2 cm/s acute and the 5 cm/s chronic current — and with the site's
ambient chemistry, **TA 2146 / DIC 2092 µmol/kg, uniform in depth**) at Ebb's default profile, the
Macoma configuration. Headline: **below TA ≈ 3660 µmol/kg at the intake DIC (2092) the discharge
never supersaturates brucite, even undiluted** — ≈ 3040 if it leaves at 30 °C; above it the
centreline window is centimetres and seconds (≤ 42 cm, ≤ 7.5 s at TA 20 000), and the mixing-zone
boundaries, in receiving water at pH 7.73, see at most +0.32 pH. Four named effluents at the same geometry show that the hydroxide per
kilogram of effluent sets the window, not its pH. Every pH on the dose axis is parity-checked: the exe's
own carbonate solver stays within **0.011–0.025 pH** of PyCO2SYS from pH 8.4 to 12.0
([`case47`](reference_cases/case47_dose_parity/README.md)). The centreline is read through the exe's
default **parabolic** profile — the exe offers three
([`case48`](reference_cases/case48_similarity_profiles/README.md)) and the port implements all of
them plus the literature's Gaussian, selectable per case. `Ω_brucite` is an **upper bound** (no ion
pairing); `Ω_brucite = 1` is a pH threshold, ≈ 9.43 total at S 32 / 10 °C.

See [`studies/ebb_dose_study/`](studies/ebb_dose_study/README.md) for the write-up, [PLAN.md](notes/PLAN.md)
for where the project stands and what is next, and [SSMC_REPORT.md](notes/SSMC_REPORT.md) for the findings
to be sent to the PLUMES2.0 maintainers (nineteen items, awaiting review).

**New here?** In order:

1. The [glossary below](#names-you-will-meet) — five names this repo uses constantly.
2. [`examples/`](examples/README.md) — plumes2 as a **called physics package**: build a case
   from plain CSV ambient tables and code, run it, get dataframes. Ten minutes, runnable.
3. [USER_GUIDE.md](USER_GUIDE.md) — the reference for driving it: every command, field,
   default and column spelled out, and checked against the code by the test suite.
4. [PORTING_THE_PHYSICS.md](PORTING_THE_PHYSICS.md) — what to trust, where this port
   deliberately differs from the executable, and the defects it reproduces only on request.
   (Written for readers at Ebb; it assumes you know what the discharge is.)

Then `python docs/build.py` for the rendered API reference.

## Names you will meet

| name | meaning |
|---|---|
| **the exe** | `plumes2.0v1.exe`, the compiled Windows executable this is a port of. No source is published; everything known about it was decoded from manuals and output traces. |
| **a trace** | a `.dat` output file the exe wrote. The archive of traces in `reference_cases/` is what every accuracy figure is measured against. |
| **the operator** | the person who runs the exe by hand and makes the modelling decisions (profile choice, constants, what to send the maintainers) — the exe is GUI-only, so exe runs cannot be scripted. |
| **Ebb** | [Ebb Carbon](https://ebbcarbon.com), whose alkalinity-elevated discharge is the reason this port exists. |
| **Macoma** | Ebb's site, and the configuration the dose study runs at: 25 ports at 2 ft, 5900 L/h of intake water, 20.7 / 207 ft mixing zones, ambient TA 2146 / DIC 2092. The archived exe runs in `reference_cases/case00`–`case12` and `case24` were an *earlier entry* of that diffuser with known slips (2 m, 35 psu, 0.219 L/s, zones in metres) and are called "the archived diffuser", never Macoma; the site's own case, run in the exe on 2026-09-09, is `reference_cases/case55_macoma_site/`. |
| **a ledger row** | one numbered finding in [`notes/LEDGER.md`](notes/LEDGER.md), re-derived by `plumes2 validate`; docs cite them as "row 262". |

## What is upstream and what is new here

This distinction matters, so it is enforced by directory:

| Path | Provenance | Editable? |
|---|---|---|
| **[`upstream/`](upstream/)** | Verbatim snapshot of [ssmc-uw/PLUMES2.0](https://github.com/ssmc-uw/PLUMES2.0) — the Windows executable, both user manuals, the shipped example project, icons, and the upstream README/licence/disclaimer. | **No.** Treat as read-only reference. |
| `src/plumes2/` | New. The Python port. | yes |
| `tests/` | New. Validation suite. | yes |
| `reference_cases/` | New. Exe-generated runs used as validation targets (case00–case54), each with a write-up of what it revealed. The `.dat`/`.csv`/`.prj` files inside are exe output — do not hand-edit them; the READMEs are ours. `pending/` holds generated experiments awaiting the exe. | READMEs yes, data no |
| `references/` | Third-party sources the manuals cite but do not reproduce (the 1985, 1994 and 2003 EPA reports, and three non-EPA papers). ⚠️ Millero (2010) and Cenedese & Linden (2014) are **not** redistributable — see its README before publishing this repo. | README yes, PDFs no |
| `studies/` | New. The dose study and its dry run, with write-ups; the scripts that generate exe experiments; `example_case.yaml`, the shipped example in the port's native format. | yes |
| [`examples/`](examples/README.md) | New. plumes2 as a called physics package: plain-CSV ambient tables, a runnable script, its expected output. Executed by the test suite. | yes |
| `USER_GUIDE.md` | New. Every command, field, default and column spelled out, pinned to the code by `tests/test_user_guide.py`. | yes |
| `PORTING_THE_PHYSICS.md` | New. The write-up for people *using* the model: accuracy, where the exe contradicts its own manual, and the defect flags. | yes |
| `reports/` | Local only: where `plumes2 report` writes its PDFs. The whole folder is ignored by git, so a clone has no `reports/` directory; a report goes into the repository only by a deliberate `git add -f`. | no |
| [`notes/`](notes/) | New. The development record: `PLAN.md` (current state and next actions), `PLAN_HISTORY.md` (the frozen build log — search it, do not read it), `LEDGER.md` (the validation ledger, every finding one row), `PORTING_NOTES.md` (the decoded specification), `MANUAL_DIGEST.md` (the upstream manuals condensed), `SSMC_REPORT.md` (findings for the maintainers, awaiting the operator's review), `ENVIRONMENT.md` (toolchain). | yes (`PLAN_HISTORY.md` frozen) |
| `docs/` | New. `build.py` renders the API reference from the in-place docstrings; the output is git-ignored. | yes |

Nothing in `upstream/` is modified — it is there so the port can be checked
against the real thing, and so the provenance of every reference number is
unambiguous. There is no upstream source code to translate: the upstream repo
ships the compiled binary only, so this is a re-implementation from the manuals,
the published UM3 literature, and exe output traces.

## Licence and attribution

Upstream PLUMES2.0 is BSD-2-Clause (Battelle Memorial Institute, 2024), which
permits re-implementation and redistribution. The copyright notice and the PNNL
disclaimer are retained in [`upstream/license.md`](upstream/license.md) and
[`upstream/disclaimer_notice.md`](upstream/disclaimer_notice.md). This port is
not endorsed by EPA, PNNL, Battelle, or the UW Salish Sea Modeling Center.

**The port's own code — everything outside `upstream/` and `references/` — is
[MIT-licensed](LICENSE), © 2026 Ebb Carbon.** `upstream/license.md` covers only the upstream
snapshot; the two regimes coexist and neither restricts the other.

⚠️ **Do not redistribute this repository.** Two PDFs under [`references/`](references/README.md)
— Millero (2010) and Cenedese & Linden (2014) — are copyrighted works we may hold for
private research but **not** republish, and they are tracked in git history, not just the
working tree. Private collaborator access is fine; any public release must first remove them
(a history rewrite or a history-free snapshot export, not a `git rm`) — see
`references/README.md`.

## Getting started

With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
(`winget install astral-sh.uv` on Windows, `brew install uv` on macOS):

```powershell
uv venv --python 3.14 .venv
uv pip install --python .venv -e ".[compare,dev,notebook]"
.venv\Scripts\python.exe -m pytest -n auto --dist loadfile
```

Full setup notes, including how to reproduce the exact pinned environment, are in
[ENVIRONMENT.md](notes/ENVIRONMENT.md).

### Run something

The shipped example case, from the command line:

```text
$ .venv\Scripts\plumes2 run studies/example_case.yaml -o out/example
ran   studies\example_case.yaml
wrote out\example
  near field ended after 102.0 s (oscillation limit)
  dilution 228.9 at 3.09 m depth
  centreline dilution 126.5 (peak/mean 1.810, merged)
  plume diameter 8.422 m
```

Or as a library — the whole API in four lines:

```python
from plumes2 import load_case, run

results = run(load_case("studies/example_case.yaml"))
print(results.nearfield[["time_s", "dilution", "plume_diameter_m"]].tail())
```

[`examples/`](examples/README.md) has the full worked version — ambient tables from plain
CSVs, an alkalinity-elevated discharge, mixing-zone chemistry — with its expected output.

### Running the suite

Over 2 500 tests, and deliberately not pinned here — a hand-maintained count is the one thing
this project has watched go stale most often. Most are cheap — half of them round-trip every archived `.prj`, `.dat` and CSV one
file at a time, which is what catches a formatting change the day it lands.

| | command | time |
|---|---|---|
| **everything, parallel** | `pytest -n auto --dist loadfile` | ~150 s (2 794 tests, 2026-08-26) |
| **everything, serial** | `pytest` | slower, but the only run that checks the `slow` marker |
| **the fast lane** | `pytest -m "not slow"` | skips the tests over a second |
| **the ledger only** | `plumes2 validate` | every validated claim, re-derived |

⚠️ **`--dist loadfile`, not bare `-n auto`.** Per-file distribution keeps a module's tests on one
worker, which is what preserves the shared fixtures the suite is built on — one of them measures
every validation target once and is the difference between a 2.5 s module and a 233 s one.

Measured outcomes are cached in a single gitignored `.plumes2_outcome_cache.json`, keyed on a digest
of `src/plumes2` plus the archived reference data, so **any change to the model or the cases
discards it whole**. `pytest --wipe-outcome-cache` clears it by hand;
`PLUMES2_NO_CACHE=1` disables it. See [PLAN_HISTORY.md](notes/PLAN_HISTORY.md) §8e ("Suite speed") for what
this replaced and why the key is as coarse as it is.

## Where to start reading

- [examples/README.md](examples/README.md) — plumes2 as a called physics package, runnable.
- [USER_GUIDE.md](USER_GUIDE.md) — how to run it: the CLI, the YAML
  case file, the Python API, the outputs, the warnings, and the exe-side workflow.
- [PLAN.md](notes/PLAN.md) — where the project stands, what was decided, and what is next;
  [PLAN_HISTORY.md](notes/PLAN_HISTORY.md) is the frozen build log behind it.
- [PORTING_NOTES.md](notes/PORTING_NOTES.md) — the decoded specification.
- [reference_cases/README.md](reference_cases/README.md) — the validation cases
  and the cross-case findings that drove most of the decoding.
- [CONTRIBUTING.md](CONTRIBUTING.md) — the working rules if you change anything.
