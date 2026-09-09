"""`Effluent.excess_density`: dissolved load the salinity cannot see, carried for buoyancy alone.

Pure water plus NaOH is the case that needs it (the dose study's pH 12 / 13.5 effluents,
2026-09-08). The equation of state reads salinity, so 0.1 mol/kg of hydroxide -- 4.5 kg/m3 -- was
invisible to the buoyancy; giving it as an equivalent salinity instead handed the *chemistry* a
false seawater fraction and, through the seawater Kw's salinity dependence near S 0, ran away.
So it is a separate tracer: conserved as `m * excess` exactly as salinity is conserved as `m * S`,
read back as `excess / D`, added to the plume density, and never seen by the carbonate system.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from plumes2.config import Case, EffluentChemistry
from plumes2.io import load_case
from plumes2.nearfield.state import STATE_SIZE, LcvState, initial_state, unpack
from plumes2.seawater import density
from tests.conftest import REPO_ROOT

# The public example case, not the dose study's: this test travels with the library.
DEFAULT_YAML = REPO_ROOT / "studies" / "example_case.yaml"


def _pure_water(excess: float, *, salinity: float = 0.0) -> Case:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        base = load_case(DEFAULT_YAML)
        case = base.model_copy(
            update={
                "effluent": base.effluent.model_copy(
                    update={"salinity": salinity, "temperature": 11.2, "excess_density": excess}
                ),
                "effluent_chemistry": EffluentChemistry(total_alkalinity=103_000.0, dic=0.0),
            }
        )
        return Case.model_validate(case.model_dump())


def test_the_tracer_packs_as_a_conserved_quantity_and_enters_the_density() -> None:
    """`m * excess` is the tenth slot; `density` is the EOS reading plus the tracer."""
    state = LcvState(
        mass=2.0,
        velocity=np.array([1.0, 0.0, 0.5]),
        temperature=11.2,
        salinity=0.0,
        position=np.zeros(3),
        excess_density=4.5,
    )
    vector = state.pack()
    assert vector.shape == (STATE_SIZE,) == (10,)
    assert vector[9] == pytest.approx(9.0)
    back = unpack(vector)
    assert back.excess_density == pytest.approx(4.5)
    assert back.density() == pytest.approx(float(density(0.0, 11.2)) + 4.5)
    # Entraining mass without entraining excess halves the tracer: read back as excess / D.
    vector[0] *= 2.0
    assert unpack(vector).excess_density == pytest.approx(2.25)
    # The default is zero, so every existing case packs to the same physics as before.
    plain = LcvState(
        mass=2.0, velocity=state.velocity, temperature=11.2, salinity=0.0, position=np.zeros(3)
    )
    assert plain.pack()[9] == 0.0 and plain.density() == pytest.approx(float(density(0.0, 11.2)))


def test_the_port_carries_the_declared_excess() -> None:
    """`initial_state` starts the tracer at the effluent's value and puts it in the port density."""
    heavy, geometry_heavy = initial_state(_pure_water(4.5))
    light, geometry_light = initial_state(_pure_water(0.0))
    assert heavy.excess_density == 4.5 and light.excess_density == 0.0
    assert heavy.density() - light.density() == pytest.approx(4.5)
    # A denser effluent through the same port at the same speed is more mass per element.
    assert geometry_heavy.effluent_mass / geometry_light.effluent_mass == pytest.approx(
        heavy.density() / light.density()
    )


def test_a_case_round_trips_through_yaml_with_its_excess(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from plumes2.io import dump_case

    case = _pure_water(4.5)
    path = tmp_path / "pure.yaml"
    dump_case(case, path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert load_case(path).effluent.excess_density == 4.5


@pytest.mark.slow
def test_the_tracer_dilutes_with_the_mass_and_never_reaches_the_chemistry() -> None:
    """Along the run: density - EOS(S, T) == excess / D; the chemistry columns are those of S 0.

    And the tracer does what the equivalent salinity was meant to do -- reproduce the NaOH
    solution's buoyancy -- without its side effect: a case given the density-equivalent salinity
    instead starts at the same density but reports magnesium it does not have.
    """
    from plumes2.chem import magnesium_from_salinity
    from plumes2.results import run

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tracer = run(_pure_water(4.5), samples=150)
        plain = run(_pure_water(0.0), samples=150)
    near = tracer.nearfield
    eos = np.asarray(
        density(near["salinity_psu"].to_numpy(float), near["temperature_degC"].to_numpy(float))
    )
    expected = 4.5 / near["dilution"].to_numpy(float)
    np.testing.assert_allclose(near["density_kg_m3"].to_numpy(float) - eos, expected, rtol=1e-6)
    # Same endmember, same speciation at the port: the chemistry has not seen the tracer.
    for column in ("ph_total", "omega_brucite", "total_alkalinity_umol_kg", "salinity_psu"):
        assert float(near[column].iloc[0]) == pytest.approx(float(plain.nearfield[column].iloc[0]))
    assert float(near["salinity_psu"].iloc[0]) == 0.0
    assert float(near["omega_brucite"].iloc[0]) == 0.0  # no magnesium at S 0
    # The heavier effluent is less buoyant, so it rises less and entrains less.
    assert float(near["depth_m"].min()) > float(plain.nearfield["depth_m"].min())
    assert float(near["dilution"].iloc[-1]) < float(plain.nearfield["dilution"].iloc[-1])

    # The salinity that would have matched the port density instead brings Mg the water lacks.
    target = float(density(0.0, 11.2)) + 4.5
    lo, hi = 0.0, 40.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if float(density(mid, 11.2)) < target else (lo, mid)
    equivalent = _pure_water(0.0, salinity=0.5 * (lo + hi))
    port_tracer, _ = initial_state(_pure_water(4.5))
    port_equivalent, _ = initial_state(equivalent)
    assert port_tracer.density() == pytest.approx(port_equivalent.density(), abs=1e-6)
    assert float(magnesium_from_salinity(equivalent.effluent.salinity)) > 0.0
