"""EOS-80 density, checked against UNESCO's published values and against the exe.

The exe-facing test is the interesting one: case01 reports a `P-Den` column, so its 84
rows are 84 independent checks of both the equation of state and the assumption that
temperature and salinity mix conservatively with dilution. It also settles empirically
whether the exe reports sigma-t or in-situ density.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from plumes2.config import NearFieldSettings
from plumes2.io.dat import read_dat
from plumes2.seawater import (
    EquationOfState,
    density,
    density_of,
    depth_from_pressure,
    knudsen_density,
    knudsen_sigma_t,
    pressure_from_depth,
    reduced_gravity,
    secant_bulk_modulus,
    sigma_t,
)
from tests.conftest import REFERENCE_CASES

CASE01 = REFERENCE_CASES / "case01_macoma_cms" / "ModelResults_TxtOutputs.dat"


class TestUnescoCheckValues:
    """UNESCO (1983) Table A3.1 -- the canonical EOS-80 acceptance values."""

    @pytest.mark.parametrize(
        ("salinity", "temperature", "pressure_bar", "expected"),
        [
            (0.0, 5.0, 0.0, 999.96675),
            (0.0, 5.0, 1000.0, 1044.12802),
            (0.0, 25.0, 0.0, 997.04796),
            (0.0, 25.0, 1000.0, 1037.90204),
            (35.0, 5.0, 0.0, 1027.67547),
            (35.0, 5.0, 1000.0, 1069.48914),
            (35.0, 25.0, 0.0, 1023.34306),
            (35.0, 25.0, 1000.0, 1062.53817),
        ],
    )
    def test_density(
        self, salinity: float, temperature: float, pressure_bar: float, expected: float
    ) -> None:
        # UNESCO tabulates pressure in bars; our API takes decibars.
        got = density(salinity, temperature, pressure_bar * 10.0)
        assert float(got) == pytest.approx(expected, abs=1e-5)

    @pytest.mark.parametrize(
        ("salinity", "temperature", "pressure_bar", "expected"),
        [
            (0.0, 5.0, 0.0, 20337.80375),
            (0.0, 5.0, 1000.0, 23643.52599),
            (35.0, 5.0, 0.0, 22185.93358),
            (35.0, 5.0, 1000.0, 25577.49819),
            (35.0, 25.0, 0.0, 23726.34949),
        ],
    )
    def test_secant_bulk_modulus(
        self, salinity: float, temperature: float, pressure_bar: float, expected: float
    ) -> None:
        got = secant_bulk_modulus(salinity, temperature, pressure_bar * 10.0)
        assert float(got) == pytest.approx(expected, abs=1e-4)


class TestBasics:
    def test_sigma_t_is_the_zero_pressure_anomaly(self) -> None:
        assert float(sigma_t(35.0, 5.0)) == pytest.approx(1027.67547 - 1000.0, abs=1e-5)

    def test_freshwater_maximum_density_near_4c(self) -> None:
        temperatures = np.linspace(0.0, 10.0, 1001)
        densities = density(0.0, temperatures)
        assert temperatures[int(np.argmax(densities))] == pytest.approx(3.98, abs=0.02)

    def test_vectorises(self) -> None:
        got = density([0.0, 35.0], [5.0, 5.0])
        assert got.shape == (2,)
        assert got[1] > got[0]

    def test_negative_salinity_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            density(-1.0, 10.0)

    def test_pressure_and_depth_are_mutual_inverses(self) -> None:
        depths = np.array([1.0, 17.0, 100.0, 1000.0])
        assert depth_from_pressure(pressure_from_depth(depths)) == pytest.approx(depths, abs=1e-6)

    def test_pressure_is_a_little_over_one_dbar_per_metre(self) -> None:
        assert float(pressure_from_depth(100.0)) == pytest.approx(100.7, abs=1.0)

    def test_reduced_gravity_sign(self) -> None:
        # Freshwater in seawater rises.
        assert float(reduced_gravity(1000.0, 1025.0)) > 0
        # case07's 45 psu effluent is denser than ambient, so g' is negative.
        dense = float(density(45.0, 10.0))
        ambient = float(density(31.2, 10.4))
        assert dense > ambient
        assert float(reduced_gravity(dense, ambient)) < 0


class TestAgainstTheExe:
    """case01 prints plume density, so it validates the EOS and the mixing together."""

    @staticmethod
    def _mixed(dilution: np.ndarray, depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Conservative T/S mixing of case01's 35 psu, 10 C effluent with its ambient."""
        depths = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0]
        ambient_salinity = np.interp(depth, depths, [30.9, 31.2, 31.2, 31.7, 31.8, 31.9])
        ambient_temperature = np.interp(depth, depths, [11.2, 10.4, 9.69, 9.44, 9.34, 9.22])
        salinity = (35.0 + (dilution - 1.0) * ambient_salinity) / dilution
        temperature = (10.0 + (dilution - 1.0) * ambient_temperature) / dilution
        return salinity, temperature

    def test_reproduces_the_plume_density_column(self) -> None:
        """84 rows, and the agreement decides sigma-t versus in-situ."""
        nearfield = read_dat(CASE01).nearfield
        dilution = nearfield["Dilutn"].to_numpy(float)
        depth = -nearfield["Depth"].to_numpy(float)
        reported = nearfield["P-Den"].to_numpy(float)

        salinity, temperature = self._mixed(dilution, depth)
        at_zero_pressure = density(salinity, temperature)
        in_situ = density(salinity, temperature, pressure_from_depth(depth))

        zero_error = at_zero_pressure - reported
        situ_error = in_situ - reported

        # EOS-80 tracks the exe to 7e-5 relative, but runs systematically low by a mean
        # 0.036 kg/m3. Recorded rather than tuned away; see the module docstring.
        assert np.abs(zero_error).max() < 0.08
        assert zero_error.mean() == pytest.approx(-0.036, abs=0.005)
        # Adding pressure does not close the gap -- it is not the cause.
        assert np.abs(situ_error).mean() > 0.02

    def test_the_first_row_is_the_near_undiluted_effluent(self) -> None:
        nearfield = read_dat(CASE01).nearfield
        first = nearfield.iloc[0]
        salinity, temperature = self._mixed(
            np.array([first["Dilutn"]]), np.array([-first["Depth"]])
        )
        assert float(density(salinity, temperature)[0]) == pytest.approx(first["P-Den"], abs=0.05)
        # 1026.677 kg/m3 against an ambient near 1023.8: negatively buoyant from the start.
        assert first["P-Den"] == pytest.approx(1026.677, abs=1e-3)

    def test_the_plume_approaches_ambient_density(self) -> None:
        """By the end, dilution is 388:1 and the plume is essentially ambient water."""
        nearfield = read_dat(CASE01).nearfield
        last = nearfield.iloc[-1]
        ambient = float(density(31.2, 10.4))
        assert last["P-Den"] == pytest.approx(ambient, abs=0.5)


def test_density_anomaly_is_the_density_less_a_thousand() -> None:
    """Exported and used internally, but untested until the 2026-08-17 audit.

    Trivial by construction -- which is the argument for a one-line test rather than against it,
    since `sigma_t` next door is *not* simply this at pressure and the two are easy to conflate.
    """
    from plumes2.seawater import density, density_anomaly

    points = ((35.0, 25.0, 0.0), (0.0, 4.0, 0.0), (31.2, 9.69, 100.0))
    for salinity, temperature, pressure in points:
        assert float(density_anomaly(salinity, temperature, pressure)) == pytest.approx(
            float(density(salinity, temperature, pressure)) - 1000.0
        )
    # sigma_t is the zero-pressure anomaly, so the two agree only at the surface.
    assert float(density_anomaly(35.0, 10.0, 0.0)) == pytest.approx(float(sigma_t(35.0, 10.0)))
    assert float(density_anomaly(35.0, 10.0, 500.0)) != pytest.approx(float(sigma_t(35.0, 10.0)))


@functools.cache
def _archived_density_rows() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(P-Sal, P-Temp, P-Den)` pooled over every trace that prints all three.

    Cached because it parses most of the archive, and three tests want the same rows.
    """
    salinity, temperature, printed = [], [], []
    for path in sorted(REFERENCE_CASES.glob("*/*.dat")):
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if not {"P-Sal", "P-Temp", "P-Den"} <= set(frame.columns):
            continue
        s = frame["P-Sal"].to_numpy(dtype=np.float64)
        t = frame["P-Temp"].to_numpy(dtype=np.float64)
        d = frame["P-Den"].to_numpy(dtype=np.float64)
        keep = np.isfinite(s) & np.isfinite(t) & np.isfinite(d) & (s >= 0.0)
        salinity.append(s[keep])
        temperature.append(t[keep])
        printed.append(d[keep])
    return (
        np.concatenate(salinity),
        np.concatenate(temperature),
        np.concatenate(printed),
    )


def _cheap_eos_case():  # type: ignore[no-untyped-def]
    """A single-port, low-flow case -- the same shape `conftest.cheap_run` uses."""
    from plumes2.io.project import load_project

    base = load_project(
        REFERENCE_CASES / "case18_zero_current_pair" / "test21.prj"
    ).to_case(row_index=0)
    return base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": base.effluent.model_copy(update={"flow": 5.0e-5}),
        }
    )


class TestKnudsenIsTheExesEquationOfState:
    """⭐⭐⭐ Knudsen (1901), identified 2026-08-20 against 39 000 printed rows.

    The oldest open discrepancy in the port: `P-Den` sat 0.02-0.06 kg/m3 above EOS-80 and the
    cause was recorded as "probably a different polynomial". It is Knudsen's, the formulation
    tabulated by U.S. Navy H.O. Pub. 615 (1952), which `references/README.md` traces the exe to
    by citation through OUTPLM and Teeter & Baumgartner (1979).

    The archive-wide test is the load-bearing one. The two algebraic checks come first because a
    transcribed coefficient is exactly the kind of error that produces plausible numbers -- the
    brucite enthalpy in `chem` was 48x wrong with correct units and no warning -- and neither of
    them would catch a wrong high-order term on its own.
    """

    def test_sigma_zero_matches_the_tabulated_value(self) -> None:
        """`sigma_0(35) = 28.13` is the number every textbook prints."""
        assert float(knudsen_sigma_t(35.0, 0.0)) == pytest.approx(28.1296, abs=5e-5)

    def test_sigma_t_reduces_to_sigma_zero_at_zero_celsius(self) -> None:
        """`A_t` and `B_t` both vanish at T = 0, so `sigma_t` collapses to `sigma_0` there.

        ⚠️ To **4e-5, not exactly**, and the residual is a real feature of the classical
        formula rather than a slip here: the additive `0.1324` is a rounded `-Sigma_t(0)`,
        whose exact value is 0.132360. Writing this test with a 1e-12 tolerance failed and
        that is how the constant's provenance became clear. Anything looser than 1e-4 would
        stop discriminating, and anything tighter asserts a precision Knudsen never had.
        """
        for salinity in (0.0, 10.0, 35.0, 45.0):
            sigma_zero = (
                -0.093
                + 0.8149 * salinity
                - 0.000482 * salinity**2
                + 0.0000068 * salinity**3
            )
            assert float(knudsen_sigma_t(salinity, 0.0)) == pytest.approx(sigma_zero, abs=5e-5)

    def test_it_reproduces_every_printed_density_in_the_archive(self) -> None:
        """The identification itself: 0 free parameters, one rounding digit.

        88 traces print `P-Sal`, `P-Temp` and `P-Den` on the same row, so this needs no
        reconstruction from dilution -- which is how the retracted "+0.0275 constant" was
        obtained, on two traces that both sat inside 31-35 psu.
        """
        salinity, temperature, printed = _archived_density_rows()
        assert printed.size > 30_000, "the archive should supply tens of thousands of rows"
        assert salinity.min() < 1.0 and salinity.max() > 44.0, "S 0-45 psu is the whole point"

        residual = printed - knudsen_density(salinity, temperature)
        # `P-Den` carries three decimals, so half a digit is the floor and one digit is the cap.
        assert np.abs(residual).max() <= 0.001
        assert abs(float(residual.mean())) <= 1e-4
        assert float(np.sqrt((residual**2).mean())) <= 5e-4

    def test_eos80_is_the_one_it_beats_and_the_gap_is_not_constant(self) -> None:
        """⚠️ The retraction, pinned: the EOS-80 residual is a *line in salinity*.

        The "+0.0275 kg/m3 constant offset" came from case16 and test23, both entirely inside
        31-35 psu. Pooled over the archive the residual runs from +0.06 at low salinity to +0.02
        at high, so treating it as a constant is what one band's worth of data looked like.
        """
        salinity, temperature, printed = _archived_density_rows()
        residual = printed - density(salinity, temperature, 0.0)
        assert residual.min() > 0.015, "the exe always reads high against EOS-80"
        assert residual.max() > 0.05, "and by far more than 0.0275 at low salinity"
        fresh = residual[salinity < 15.0].mean()
        salty = residual[salinity > 34.0].mean()
        assert fresh - salty > 0.02, "a constant offset cannot span the archive's salinity range"

    def test_knudsen_has_no_pressure_term(self) -> None:
        """The 3rd edition's "independent of pressure" is a property of the formula."""
        deep = density_of(35.0, 10.0, 500.0, equation_of_state=EquationOfState.KNUDSEN)
        shallow = density_of(35.0, 10.0, 0.0, equation_of_state=EquationOfState.KNUDSEN)
        assert float(deep) == float(shallow)
        # EOS-80, by contrast, must respond to it, or the comparison above is vacuous.
        assert float(density_of(35.0, 10.0, 500.0)) > float(density_of(35.0, 10.0, 0.0))

    def test_the_default_is_still_eos80(self) -> None:
        """§2's rule is "correct by default, reproduce on request", and this is the request."""
        assert float(density_of(35.0, 10.0)) == float(density(35.0, 10.0, 0.0))
        assert NearFieldSettings().equation_of_state is EquationOfState.EOS80

    def test_selecting_it_changes_a_trajectory_without_breaking_it(self) -> None:
        """A run under the exe's EOS still runs, and moves by a physically sensible amount.

        ⚠️ Deliberately not a claim that it *improves* the trajectory. It does not -- see
        `_KNUDSEN_DOES_NOT_FIX_THE_LATE_DRIFT` in the module docstring of `nearfield.solver`.
        """
        from plumes2.nearfield.solver import integrate

        base = _cheap_eos_case()
        eos80 = integrate(base, max_time=60.0)
        knudsen = integrate(
            base.model_copy(
                update={
                    "near_field": base.near_field.model_copy(
                        update={"equation_of_state": EquationOfState.KNUDSEN}
                    )
                }
            ),
            max_time=60.0,
        )
        shared = np.linspace(0.0, min(eos80.end_time, knudsen.end_time), 40)
        theirs = knudsen.sample(shared).dilution
        ours = eos80.sample(shared).dilution
        assert theirs[-1] > 1.0
        ratio = float(theirs[-1] / ours[-1])
        assert 0.5 < ratio < 2.0, "an EOS swap is a small perturbation, not a different model"
        assert not np.allclose(theirs, ours), "selecting KNUDSEN must actually change something"
