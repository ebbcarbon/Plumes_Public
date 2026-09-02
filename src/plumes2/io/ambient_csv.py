"""Ambient profiles from plain, tidy CSV files.

For callers using plumes2 as a physics package rather than as an exe companion: site data
usually lives in ordinary tables — one row per depth, one column per quantity — not in the
exe's six-table CSV dialect (`plumes2.io.csv_tables`) and not embedded in a YAML case. This
module reads those plain tables straight into the `plumes2.config.ambient` sections, so a
case can be assembled as

    from plumes2 import ambient_from_files, load_case, run

    case = load_case("base_case.yaml").model_copy(update={
        "ambient": ambient_from_files(
            "ambient_levels.csv",
            chemistry="ambient_chemistry.csv",
        )
    })
    results = run(case)

Column headers are exactly the field names of `AmbientLevel`, `AmbientChemistryLevel` and
`AmbientDOLevel` (`depth`, `salinity`, `temperature`, `total_alkalinity`, ...), in any order;
`plumes2 info` and USER_GUIDE.md §3.5 list them with their units. An empty cell means "use
the field's default" (or `None` where the field is optional, e.g. chemistry `ph`); an unknown
header is an error naming the valid ones, because a silently dropped column is how a held
assumption sneaks into a run. All validation — physical ranges, strictly increasing depths —
is the same pydantic validation every other construction path gets.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from plumes2.config import (
    AmbientChemistryLevel,
    AmbientDOLevel,
    AmbientLevel,
    AmbientProfile,
)

__all__ = ["ambient_from_files", "read_levels_csv"]


def read_levels_csv[M: BaseModel](path: str | Path, model: type[M]) -> list[M]:
    """One validated model instance per CSV row, blank cells falling back to defaults.

    The header check is deliberately strict where the cell check is lenient: a blank cell is
    an explicit "default, please", but a *misspelled column* would silently discard measured
    data (`temprature` would leave every level at 20 °C), so unknown headers are fatal and
    the message lists what the model accepts.
    """
    path = Path(path)
    frame = pd.read_csv(path, skipinitialspace=True)
    frame.columns = [str(column).strip() for column in frame.columns]
    known = set(model.model_fields)
    unknown = [column for column in frame.columns if column not in known]
    if unknown:
        raise ValueError(
            f"{path.name}: unknown column(s) {unknown}; {model.__name__} accepts "
            f"{sorted(known)} (units and meanings: USER_GUIDE.md section 3.5)"
        )
    rows: list[M] = []
    for record in frame.to_dict(orient="records"):
        cleaned = {key: value for key, value in record.items() if pd.notna(value)}
        rows.append(model.model_validate(cleaned))
    return rows


def ambient_from_files(
    levels: str | Path,
    chemistry: str | Path | None = None,
    dissolved_oxygen: str | Path | None = None,
) -> AmbientProfile:
    """An `AmbientProfile` from up to three plain CSV files.

    `levels` is required (depth, current, salinity, temperature, ...); `chemistry`
    (µmol/kg, as the GUI takes them) and `dissolved_oxygen` (mg/L) are optional, exactly
    as the sections are optional in a YAML case. Depths must strictly increase in each
    file — enforced by `AmbientProfile` itself, not re-implemented here.
    """
    return AmbientProfile(
        levels=read_levels_csv(levels, AmbientLevel),
        chemistry=(
            read_levels_csv(chemistry, AmbientChemistryLevel) if chemistry is not None else []
        ),
        dissolved_oxygen=(
            read_levels_csv(dissolved_oxygen, AmbientDOLevel)
            if dissolved_oxygen is not None
            else []
        ),
    )
