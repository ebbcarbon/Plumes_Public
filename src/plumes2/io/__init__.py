"""Legacy PLUMES2.0 file formats, plus the project's own YAML case format.

The exe's formats are undocumented and were decoded from the files in
`upstream/Example_project/` and `reference_cases/`; see PORTING_NOTES.md section 4.
Readers and writers are both provided so the Python port can consume existing projects
and produce ones the exe can still open.
"""

from __future__ import annotations

from plumes2.io.ambient_csv import ambient_from_files, read_levels_csv
from plumes2.io.csv_tables import CsvRow, CsvTable, TableKind, read_csv_table, write_csv_table
from plumes2.io.dat import DatFile, read_dat
from plumes2.io.prj import PrjFile, PrjTable, read_prj, write_prj
from plumes2.io.project import Project, load_project, prj_from_case
from plumes2.io.yaml_case import dump_case, dumps_case, load_case, loads_case

__all__ = [
    "CsvRow",
    "CsvTable",
    "DatFile",
    "PrjFile",
    "PrjTable",
    "Project",
    "TableKind",
    "ambient_from_files",
    "dump_case",
    "dumps_case",
    "load_case",
    "load_project",
    "loads_case",
    "prj_from_case",
    "read_csv_table",
    "read_dat",
    "read_levels_csv",
    "read_prj",
    "write_csv_table",
    "write_prj",
]
