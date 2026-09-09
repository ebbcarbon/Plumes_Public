"""The API reference, and the claims its landing page makes.

Phase 7's deliverable is "an entry point that is not PLAN.md", which means the package docstring is
now documentation rather than a note to ourselves -- so the things it asserts are tested like any
other claim. Both tests here were written after the thing they check had already gone wrong once:
`plumes2.chem` exported two names that could not be imported, and the landing page's own worked
example named a column that does not exist.
"""

from __future__ import annotations

import importlib
import pkgutil
import warnings

import pytest

import plumes2
from plumes2 import load_project
from plumes2.results import run
from tests.conftest import REFERENCE_CASES


def _modules() -> list[str]:
    return ["plumes2", *(info.name for info in pkgutil.walk_packages(plumes2.__path__, "plumes2."))]


@pytest.mark.parametrize("name", _modules())
def test_every_exported_name_resolves(name: str) -> None:
    """An `__all__` entry that does not resolve is a promise the package cannot keep.

    It puts a name in the rendered reference that no reader can import, and pdoc reports it as a
    warning it then carries on past. `plumes2.chem` shipped two such names --
    `davies_activity_coefficient` and `ionic_strength_from_salinity` -- until the first docs build.
    """
    module = importlib.import_module(name)
    missing = [export for export in getattr(module, "__all__", ()) if not hasattr(module, export)]
    assert not missing, f"{name}.__all__ promises {missing}, which do not resolve"


@pytest.mark.slow
def test_the_landing_pages_worked_example_runs() -> None:
    """The example in `plumes2.__doc__`, executed -- because it did not work when first written.

    Kept deliberately literal: the same two imports, the same call, the same three column names. If
    a column is renamed, this fails and the docstring gets fixed in the same commit.
    """
    documented = plumes2.__doc__ or ""
    columns = ["time_s", "dilution", "plume_diameter_m"]
    example = 'results.nearfield[["time_s", "dilution", "plume_diameter_m"]]'
    assert example in documented

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        case = load_project(
            REFERENCE_CASES / "case01_cms" / "project.prj", warn_on_drift=False
        ).to_case()
    results = run(case, samples=8)

    assert list(results.nearfield[columns].columns) == columns
    assert results.nearfield["dilution"].iloc[-1] > 1.0


def test_the_landing_page_lists_every_subpackage() -> None:
    """Its module table is the map a new reader navigates by, so it may not omit one."""
    documented = plumes2.__doc__ or ""
    subpackages = {
        info.name for info in pkgutil.walk_packages(plumes2.__path__, "plumes2.") if info.ispkg
    }
    for package in subpackages:
        assert f"`{package}`" in documented, f"{package} is missing from the landing page's table"
