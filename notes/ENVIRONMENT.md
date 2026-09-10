# Environment and software packages

Verified working on Windows 11 Pro (10.0.26200), 2026-08-12.

## Interpreter

| Item | Version | Notes |
|---|---|---|
| CPython | **3.14.4** | any 3.14 install works; `uv python install 3.14` fetches one |
| uv | 0.11.6 | environment + dependency manager — install per <https://docs.astral.sh/uv/getting-started/installation/> (`winget install astral-sh.uv` on Windows) |
| Declared floor | `>=3.13` | `pyproject.toml`; 3.13 kept viable in case a later dependency lags 3.14 |

Pinned for the repo in [.python-version](../.python-version).

## Setup from scratch

```powershell
uv venv --python 3.14 .venv
uv pip install --python .venv -e ".[compare,dev,notebook,pitzer]"
```

Then activate with `.venv\Scripts\Activate.ps1`, or just call `.venv\Scripts\python.exe`
directly. To reproduce this exact environment instead of re-resolving:

```powershell
uv pip install --python .venv -r requirements.lock.txt
uv pip install --python .venv -e . --no-deps
```

## Runtime dependencies

Declared in [pyproject.toml](../pyproject.toml) under `[project].dependencies`.

| Package | Installed | Floor | Used for |
|---|---|---|---|
| numpy | 2.5.2 | >=2.1 | all array math; the LCV state vector and step integration |
| scipy | 1.18.0 | >=1.14 | ambient profile interpolation; Brent root-find in the pH solver |
| pandas | 3.0.5 | >=2.2 | the 6 CSV input tables and tabular step results |
| matplotlib | 3.11.1 | >=3.9 | the ~20 Visual Plumes plot types |
| pyyaml | 6.0.3 | >=6.0 | native YAML case files |
| pydantic | 2.13.4 | >=2.9 | input validation (physical ranges, monotonic depth profiles) |
| PyCO2SYS | 1.8.3.4 | >=1.8.3 | carbonate speciation (`plumes2.chem`); constant selections tracked explicitly |
| autograd | 1.9.1 | — | (PyCO2SYS transitive) |
| phreeqpython | 1.6.2 | >=1.6.2 (`pitzer` extra) | PHREEQC / `pitzer.dat`, the second brucite engine (`plumes2.chem.pitzer`, 2026-09-09); Apache-2.0; the sdist bundles the IPhreeqc library for Windows, Linux and macOS and installs on 3.13/3.14 without a compiler (PyPI wheels are 3.12-only) |

**PyCO2SYS moved from the `compare` extra to a runtime dependency on 2026-08-12**
(PLAN.md §2). The original plan was to port the exe's own embedded CO2SYS and keep
PyCO2SYS purely as a cross-check; the manual states that the exe's routines were
themselves "validated using the latest CO2SYS software version available in python
as PYCO2SYS", so PyCO2SYS is the same lineage one generation newer, and
re-deriving a pH solver to match an unreadable binary was the wrong place to spend
the effort. What remains is bookkeeping: `plumes2.chem.constants` states the
exe→PyCO2SYS option correspondence explicitly and every result carries the
`ConstantSet` it used.

Otherwise deliberately small — the physics is pure NumPy.

Smoke-tested working on numpy 2.5.2:

```
TA=1800, DIC=1600 umol/kg, S=32, T=8 C, opt_k_carbonic=10
  ->  pH 8.22813, Omega_arag 1.98651, Omega_calc 3.15220
```

## Optional extras

### `dev` — tooling

| Package | Installed | Used for |
|---|---|---|
| pytest | 9.1.1 | test runner (markers: `golden`, `manual`, `slow`) |
| pytest-cov | 7.1.0 | coverage |
| ruff | 0.16.2 | lint + format, line length 100 |
| mypy | 2.3.0 | type checking, `disallow_untyped_defs` |
| pandas-stubs | 3.0.5.260730 | type stubs |
| types-PyYAML | 6.0.12.20260724 | type stubs |
| pdoc | 16.0.0 | the API reference, rendered from the in-place docstrings |

### Building the API reference

```powershell
.venv\Scripts\python docs/build.py            # writes docs/api/ (git-ignored)
.venv\Scripts\python docs/build.py --serve    # live preview
```

The script walks the package rather than listing modules, because `plumes2/__init__.py` defines
`__all__` and pdoc honours it — a bare `pdoc plumes2` documents the top-level package and stops
there without saying so. It also **fails on pdoc's warnings** rather than printing them: an
unresolvable `__all__` entry puts a name in the reference that nobody can import, which had already
happened twice in `plumes2.chem` before the first build caught it.

### `notebook` — interactive iteration

| Package | Installed | Used for |
|---|---|---|
| jupyterlab | 4.6.3 | notebook-driven parameter sweeps |
| ipykernel | 7.3.0 | kernel |
| ipywidgets | 8.1.8 | interactive sliders over case inputs |

## Full lock

[requirements.lock.txt](../requirements.lock.txt) — 127 packages, the complete
transitive closure of all extras as installed. Regenerate with:

```powershell
uv pip freeze --python .venv --exclude-editable > requirements.lock.txt
```

## Not installed, considered

| Package | Why not (yet) |
|---|---|
| ~~PyCO2SYS as a *runtime* dep~~ | ✅ now a runtime dependency — see above |
| numba / cython | unnecessary — the golden case is ~275 steps; revisit only if sweeps get large |
| xarray | may earn its place if we add multi-case sweep outputs |
| streamlit / dash | only if a GUI is wanted later (deferred) |
| gfortran / Intel Fortran | no upstream source exists to compile; this is a re-implementation, not a wrapper |
