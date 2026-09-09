"""The oblique-angle effective-spacing correction, across every exe run we hold.

PORTING_NOTES section 5 named this as the main unpublished piece of the near field. It
was decoded by generating a project, having the exe run it, and finding that the width it
reported was not the one the shipped upstream trace reports for the same inputs.

The rule that fits eight of nine runs::

    effective spacing = port spacing * |cos(horizontal angle - current direction)|
    wastefield width  = (n_ports - 1) * effective spacing + final plume diameter

Every archived-diffuser case discharges at 90 degrees into a 90 degree current, so the angle between
them is zero and the correction is invisible -- which is why the uncorrected form fitted
them all and hid this for so long. case13 is the only run at a non-zero offset produced by
the current exe build, and it follows the cosine exactly.

The ninth run is the **shipped** upstream trace, which reports 109.59 m where the current
build reports 96.29 m for a byte-identical project. See case13's README.
"""

from __future__ import annotations

import math

import pytest

from plumes2.config import Diffuser
from plumes2.io.dat import read_dat
from tests.conftest import REFERENCE_CASES, UPSTREAM

#: (label, trace, n_ports, spacing, horizontal angle, current direction)
_C = REFERENCE_CASES
RUNS = [
    ("case02", _C / "case02_mgd/test1.dat", 25, 2.00, 90.0, 90.0),
    ("case05", _C / "case05_merging/test4_TxtOutputs.dat", 25, 0.60, 90.0, 90.0),
    ("case06", _C / "case06_arag_s36/test5_TxtOutputs.dat", 25, 0.60, 90.0, 90.0),
    ("case07", _C / "case07_s45_dense/test6_TxtOutputs.dat", 25, 0.60, 90.0, 90.0),
    ("case10", _C / "case10_bottom_hit/test11_TxtOutputs.dat", 25, 0.60, 90.0, 90.0),
    ("case11", _C / "case11_single_port_slow/test12_TxtOutputs.dat", 1, 0.60, 90.0, 90.0),
    ("case12", _C / "case12_shoreline_enabled/test13_TxtOutputs.dat", 25, 2.00, 90.0, 90.0),
    ("case13", _C / "case13_generated_example/PythonGenerated2.dat", 18, 6.10, 30.0, 0.0),
    ("case14", _C / "case14_generated_nochem/PythonGenerated3.dat", 18, 6.10, 30.0, 0.0),
]

SHIPPED_EXAMPLE = UPSTREAM / "Example_project/ModelResults_TxtOutputs.dat"


def _diffuser(n_ports: int, spacing: float, horizontal_angle: float) -> Diffuser:
    return Diffuser(
        port_diameter=0.076,
        port_elevation=0.31,
        vertical_angle=45.0,
        horizontal_angle=horizontal_angle,
        n_ports=n_ports,
        port_spacing=spacing,
        port_depth=11.0,
    )


class TestCosineRule:
    @pytest.mark.parametrize(
        ("label", "path", "n_ports", "spacing", "horizontal_angle", "current"),
        RUNS,
        ids=[run[0] for run in RUNS],
    )
    def test_reproduces_the_reported_wastefield_width(
        self,
        label: str,
        path: object,
        n_ports: int,
        spacing: float,
        horizontal_angle: float,
        current: float,
    ) -> None:
        dat = read_dat(path)  # type: ignore[arg-type]
        final_diameter = dat.nearfield.loc[dat.final_step, "P-dia"]
        predicted = _diffuser(n_ports, spacing, horizontal_angle).wastefield_width(
            final_diameter, current
        )
        assert dat.wastefield_width is not None
        # The exe prints two decimals, so agreement to 0.005 m is exact agreement.
        assert predicted == pytest.approx(dat.wastefield_width, abs=0.005)

    def test_only_the_generated_runs_discriminate(self) -> None:
        """Every archived-diffuser run has a zero offset, where the correction is invisible."""
        offsets = {label: abs(h - c) for label, _p, _n, _s, h, c in RUNS}
        assert offsets["case13"] == offsets["case14"] == pytest.approx(30.0)
        assert all(v == 0.0 for k, v in offsets.items() if k not in ("case13", "case14"))

    def test_the_correction_is_independent_of_chemistry(self) -> None:
        """case13 ran with chemistry on, case14 with it off; both follow the cosine.

        Different final diameters, so this is two independent confirmations rather than
        the same arithmetic twice.
        """
        chem_on = read_dat(REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat")
        chem_off = read_dat(REFERENCE_CASES / "case14_generated_nochem/PythonGenerated3.dat")
        assert chem_on.wastefield_width == pytest.approx(96.29)
        assert chem_off.wastefield_width == pytest.approx(97.60)
        assert chem_on.nearfield.loc[chem_on.final_step, "P-dia"] == pytest.approx(6.481)
        assert chem_off.nearfield.loc[chem_off.final_step, "P-dia"] == pytest.approx(7.796)

    def test_stop_at_surface_changes_termination_not_trajectory(self) -> None:
        """case13 and case14 are the same project with the checkbox toggled.

        Bit-identical through step 275; with the box ticked the run ends there, with it
        cleared it carries on to a second trapping at 476. So the difference between them
        is that one control -- not chemistry, which was the other thing that changed.
        """
        import numpy as np

        chem_on = read_dat(REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat")
        chem_off = read_dat(REFERENCE_CASES / "case14_generated_nochem/PythonGenerated3.dat")
        shared_steps = chem_on.nearfield.index
        columns = ["Dilutn", "P-dia", "x-posn", "y-posn", "Depth"]
        assert np.array_equal(
            chem_on.nearfield.loc[shared_steps, columns].to_numpy(float),
            chem_off.nearfield.loc[shared_steps, columns].to_numpy(float),
        )
        assert chem_on.final_step == 275
        assert chem_off.final_step == 476
        assert "Plume surfaces" in chem_off.event_steps()

    def test_the_uncorrected_form_would_fail_on_case13(self) -> None:
        """Guard: without the cosine, case13 is 14 % wide."""
        dat = read_dat(REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat")
        final_diameter = dat.nearfield.loc[dat.final_step, "P-dia"]
        uncorrected = 17 * 6.10 + final_diameter
        assert uncorrected == pytest.approx(110.181, abs=0.01)
        assert dat.wastefield_width == pytest.approx(96.29, abs=0.005)


class TestShippedExampleDisagrees:
    """The shipped upstream trace is the one run the rule does not fit."""

    def test_the_projects_are_equivalent(self) -> None:
        """case13's .prj differs from the upstream example only in the output filename."""
        from plumes2.io.prj import read_prj

        ours = read_prj(REFERENCE_CASES / "case13_generated_example/PythonGenerated.prj")
        theirs = read_prj(UPSTREAM / "Example_project/Example_project.prj")
        assert ours.diffuser.rows == theirs.diffuser.rows
        assert ours.ambient.rows == theirs.ambient.rows
        assert ours.effluent.rows == theirs.effluent.rows
        assert ours.mixing_zone.rows == theirs.mixing_zone.rows
        assert ours.nearfield_flags == theirs.nearfield_flags
        assert ours.farfield_flags == theirs.farfield_flags
        assert ours.output_filename != theirs.output_filename

    def test_the_near_fields_are_bit_identical(self) -> None:
        """So the disagreement is confined to the far-field handoff."""
        import numpy as np

        ours = read_dat(REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat")
        theirs = read_dat(SHIPPED_EXAMPLE)
        shared = list(theirs.nearfield.columns)
        assert np.array_equal(
            ours.nearfield[shared].to_numpy(float), theirs.nearfield[shared].to_numpy(float)
        )
        assert ours.final_step == theirs.final_step == 275
        assert ours.event_steps() == theirs.event_steps()

    def test_but_the_widths_differ(self) -> None:
        ours = read_dat(REFERENCE_CASES / "case13_generated_example/PythonGenerated2.dat")
        theirs = read_dat(SHIPPED_EXAMPLE)
        assert ours.wastefield_width == pytest.approx(96.29)
        assert theirs.wastefield_width == pytest.approx(109.59)

    def test_the_shipped_width_implies_almost_no_correction(self) -> None:
        """109.59 implies 0.9943 x nominal spacing, which is not cos(30 deg) = 0.866."""
        theirs = read_dat(SHIPPED_EXAMPLE)
        final_diameter = theirs.nearfield.loc[theirs.final_step, "P-dia"]
        implied = (theirs.wastefield_width - final_diameter) / 17 / 6.10
        assert implied == pytest.approx(0.9943, abs=1e-3)
        assert implied != pytest.approx(math.cos(math.radians(30)), abs=0.01)
