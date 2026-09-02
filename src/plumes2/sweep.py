"""Multi-case sweeps: the dose study's harness (PLAN Phase 8.3).

The study the port exists for is a sweep — alkalinity dose x port geometry x ambient
stratification, reporting pH and Ω at the mixing-zone boundaries — and until this module
there was no way to run one except a hand-written loop. `validation.py` has two private
sweep helpers built for its own ledger rows; this is the public, general one.

Three design points, each carrying a lesson from elsewhere in the project:

* **The integration count is the only cost that matters** (§8d's profiling: no hot spot in
  the right-hand side is worth more than a few per cent). A sweep runs `len(cells)`
  integrations, full stop — so the cell count is computed and logged before the first run,
  and nothing here caches across cells, because every cell is a distinct case by
  construction.
* **Warnings become data, not console noise.** `ConstantRangeWarning` exists so the dose
  study can tell an extrapolated pH from an interpolated one (§8.2) — and a sweep that let
  two hundred cells print two hundred warnings would bury exactly that fact, while a sweep
  that swallowed them would erase it. Each cell records the warning categories it raised in
  its own row.
* **A cell that fails is a row, not a crash** — the same rule as `validation.measure`. A
  dose high enough to break the speciation solver is a *finding* about the dose axis, and
  the 199 other cells are still wanted.

Usage::

    from plumes2.sweep import sweep

    frame = sweep(
        base_case,
        axes={
            "effluent_chemistry.total_alkalinity": [2300, 3000, 4000, 6000],
            "diffuser.port_depth": [2.0, 5.0, 10.0],
        },
    )
    # one row per (dose, depth) combination, keyed by both, carrying the mixing-zone
    # chemistry, the termination reason, and any warnings the cell raised

⚠️ **For a brucite question pass `extract=brucite_extract`.** The first dry run (PLAN §8f) found
that both of case03's regulatory boundaries sit in the far field, where Ω_brucite is ~0.009 at
every dose while the port sits at 10²-10⁵ -- so the default extract, which reads only the
boundaries, reports *no* brucite risk. `brucite_extract` adds the port and near-field peak values
and the extent of supersaturation: the dilution, time and distance at which Ω_brucite falls
through 1. Sample densely (`samples=3000`) for that crossing; it sits a fraction of a second from
the port and 200 samples overstate its dilution by ~30 %.
"""

from __future__ import annotations

import logging
import math
import warnings as warnings_module
from collections.abc import Callable, Mapping, Sequence
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel

from plumes2.config import Case
from plumes2.results import Results, mixing_zone_values, run

__all__ = ["brucite_extract", "mixing_zone_extract", "sweep", "with_updated"]

_logger = logging.getLogger(__name__)


def with_updated(case: Case, path: str, value: Any) -> Case:
    """`case` with the field at dotted `path` replaced, re-validated whole.

    `"effluent_chemistry.total_alkalinity"` names `case.effluent_chemistry.total_alkalinity`.
    Setting a path through a `None` (a dose axis on a case with no chemistry) is an error
    with the fix in the message, not an AttributeError from inside pydantic.

    ⚠️ **Re-validated deliberately.** `model_copy(update=...)` skips validation, which is
    fine for test fixtures and wrong for a harness: a sweep axis is exactly where an
    out-of-range value arrives mechanically rather than by a person typing it. Rebuilding
    through `model_validate` re-runs every validator, so a negative flow fails the cell
    loudly and a self-inconsistent geometry raises its `GeometryWarning` inside the cell
    that owns it.
    """
    parts = path.split(".")
    updated = _updated(case, parts, value, path)
    return Case.model_validate(updated.model_dump())


def _updated(model: BaseModel, parts: list[str], value: Any, full_path: str) -> Any:
    head = parts[0]
    if not hasattr(model, head):
        raise ValueError(f"{type(model).__name__} has no field {head!r} (axis {full_path!r})")
    if len(parts) == 1:
        return model.model_copy(update={head: value})
    child = getattr(model, head)
    if child is None:
        raise ValueError(
            f"axis {full_path!r} passes through {head!r}, which is None on this case -- "
            f"give the base case a {head} before sweeping inside it"
        )
    if not isinstance(child, BaseModel):
        raise ValueError(f"axis {full_path!r}: {head!r} is not a model, cannot descend into it")
    return model.model_copy(update={head: _updated(child, parts[1:], value, full_path)})


def mixing_zone_extract(results: Results) -> dict[str, Any]:
    """The default per-cell observables: everything at both mixing-zone boundaries, flattened.

    `mixing_zone_values`'s two rows become `acute_*` / `chronic_*` columns, plus the
    termination reason and the near-field end dilution — the quantities a dose-response
    curve is drawn from. Pass your own `extract` to `sweep` for anything else.
    """
    out: dict[str, Any] = {
        "termination": results.termination,
        "nearfield_end_dilution": float(results.nearfield["dilution"].iloc[-1]),
    }
    table = mixing_zone_values(results)
    for boundary, row in table.iterrows():
        for column, value in row.items():
            out[f"{boundary}_{column}"] = value
    return out


def brucite_extract(results: Results) -> dict[str, Any]:
    """`mixing_zone_extract` plus the near-field quantities the boundaries cannot see.

    Promoted from the first dry run (`studies/dose_dry_run.py`, 2026-08-25), which found that a
    boundary-only extract is not a brucite observable (PLAN §8f, finding 4). Adds, per cell:

    * `port_*` -- pH, DIC, Ω_brucite and Ω_aragonite on the first printed row;
    * `nearfield_peak_*` -- the largest Ω_brucite and pH anywhere in the near field;
    * `nearfield_end_*` -- distance, time, pH and Ω_brucite where the near field stops;
    * `omega1_*` -- the **extent of brucite supersaturation**: the dilution, time and distance at
      which Ω_brucite last exceeds 1, interpolated on log Ω between the bracketing samples, and
      `omega1_region` saying where that was found: `"never"` (the port itself is undersaturated),
      `"nearfield"`, `"farfield"` (still supersaturated at the near-field end, crossing found in
      the Brooks table), or `"beyond_farfield"` (still above 1 where the tables end -- the
      values are then the last row's, and are a floor on the extent, not the extent).

    ⚠️ Thermodynamic, not kinetic. Ω = 1 is a necessary condition for precipitation and says
    nothing about how much, if any, forms: `chem/precipitation.py` has no brucite rate law and
    PLAN §8b forbids inferring alkalinity loss from Ω without one. And Ω_brucite is itself an
    upper bound (no ion pairing), so the extent is an upper bound too.

    Refuses a run without chemistry rather than raising a KeyError from inside pandas.
    """
    if not results.has_chemistry:
        raise ValueError(
            "brucite_extract needs a chemistry run: give the case an effluent_chemistry and an "
            "ambient chemistry table, or use mixing_zone_extract"
        )
    out = mixing_zone_extract(results)
    near = results.nearfield
    omega = near["omega_brucite"].to_numpy(np.float64)
    dilution = near["dilution"].to_numpy(np.float64)
    # Horizontal distance from the port, made monotone so a plume that curls back does not read as
    # closer than it was -- the far field's `distance_m` continues from the same origin.
    distance = np.maximum.accumulate(
        np.hypot(near["x_m"].to_numpy(np.float64), near["y_m"].to_numpy(np.float64))
    )
    time_s = near["time_s"].to_numpy(np.float64)

    out["port_ph_total"] = float(near["ph_total"].iloc[0])
    out["port_dic_umol_kg"] = float(near["dic_umol_kg"].iloc[0])
    out["port_omega_brucite"] = float(omega[0])
    out["port_omega_aragonite"] = float(near["omega_aragonite"].iloc[0])
    out["nearfield_peak_omega_brucite"] = float(np.nanmax(omega))
    out["nearfield_peak_ph_total"] = float(np.nanmax(near["ph_total"].to_numpy(np.float64)))
    out["nearfield_end_distance_m"] = float(distance[-1])
    out["nearfield_end_time_s"] = float(time_s[-1])
    out["nearfield_end_ph_total"] = float(near["ph_total"].iloc[-1])
    out["nearfield_end_omega_brucite"] = float(omega[-1])

    crossing = _log_crossing(omega, dilution, time_s, distance)
    region = "nearfield"
    if crossing is None and omega[0] <= 1.0:
        region = "never"
    elif crossing is None:
        # Still supersaturated at the near-field end: continue into the Brooks table, whose
        # chemistry starts from the near-field endpoint by construction (`_farfield_chemistry`).
        far = results.farfield
        region = "beyond_farfield"
        if far is not None and len(far) and "omega_brucite" in far.columns:
            far_time = time_s[-1] + far["travel_time_hr"].to_numpy(np.float64) * 3600.0
            crossing = _log_crossing(
                far["omega_brucite"].to_numpy(np.float64),
                far["dilution"].to_numpy(np.float64),
                far_time,
                far["distance_m"].to_numpy(np.float64),
            )
            if crossing is not None:
                region = "farfield"
            else:
                crossing = (
                    float(far["dilution"].iloc[-1]),
                    float(far_time[-1]),
                    float(far["distance_m"].iloc[-1]),
                )
        else:
            crossing = (float(dilution[-1]), float(time_s[-1]), float(distance[-1]))
    if crossing is None:
        crossing = (math.nan, math.nan, math.nan)
    out["omega1_dilution"], out["omega1_time_s"], out["omega1_distance_m"] = crossing
    out["omega1_region"] = region
    return out


def _log_crossing(omega: np.ndarray, *series: np.ndarray) -> tuple[float, ...] | None:
    """Each of `series` where Ω last falls through 1, interpolated on log Ω; None if it never does.

    "Never" here means no downward crossing inside the array: either Ω is below 1 throughout, or
    it is still above 1 at the end. The caller tells those apart from `omega[0]`.
    """
    above = omega > 1.0
    if not above.any() or above[-1]:
        return None
    last = int(np.flatnonzero(above)[-1])
    lo, hi = math.log(omega[last]), math.log(omega[last + 1])
    frac = lo / (lo - hi) if lo != hi else 0.0
    return tuple(float(s[last] + frac * (s[last + 1] - s[last])) for s in series)


def sweep(
    base: Case,
    axes: Mapping[str, Sequence[Any]],
    *,
    extract: Callable[[Results], dict[str, Any]] = mixing_zone_extract,
    samples: int = 200,
) -> pd.DataFrame:
    """Run `base` at every combination of the axes; one row per cell.

    `axes` maps dotted field paths to the values each should take; the sweep is their full
    cross product, in `itertools.product` order (last axis fastest). Each row carries the
    axis values, whatever `extract` returns for that cell, an `error` column (empty string,
    or the exception that stopped the cell), and a `warnings` column naming the warning
    categories the cell raised (semicolon-joined, deduplicated) — re-run the one cell to see
    a warning's full text.

    The cell count — which is the cost, one integration each — is logged at INFO before the
    first run.
    """
    if not axes:
        raise ValueError("an empty axes mapping would sweep nothing")
    paths = list(axes)
    cells = list(product(*(axes[path] for path in paths)))
    _logger.info("sweep: %d cells over %s -- one integration each", len(cells), paths)

    rows: list[dict[str, Any]] = []
    for values in cells:
        row: dict[str, Any] = dict(zip(paths, values, strict=True))
        with warnings_module.catch_warnings(record=True) as caught:
            warnings_module.simplefilter("always")
            try:
                case = base
                for path, value in zip(paths, values, strict=True):
                    case = with_updated(case, path, value)
                row.update(extract(run(case, samples=samples)))
                row["error"] = ""
            except Exception as raised:  # a failed cell is a row, not a crash
                row["error"] = f"{type(raised).__name__}: {raised}"
        row["warnings"] = ";".join(sorted({w.category.__name__ for w in caught}))
        rows.append(row)

    frame = pd.DataFrame(rows)
    # A failed cell contributes no extractor columns; make the frame rectangular with NaN
    # rather than letting pandas invent an object-dtype patchwork.
    return frame.replace({None: math.nan})
