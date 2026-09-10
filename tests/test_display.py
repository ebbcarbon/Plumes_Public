"""Display units: the output half of `units.py`, and its refusals."""

from __future__ import annotations

import pandas as pd
import pytest

from plumes2 import units
from plumes2.display import (
    _DIMENSIONS,
    _FIXED,
    SI,
    SYSTEMS,
    US,
    UndeclaredColumnError,
    UnitSystem,
    convert_frame,
)
from plumes2.io.csv_tables import TableKind
from plumes2.plotframe import EXE_CHEMISTRY_COLUMNS
from plumes2.results import (
    CHEMISTRY_COLUMNS,
    FARFIELD_COLUMNS,
    NEARFIELD_COLUMNS,
    OXYGEN_COLUMNS,
    PHREEQC_COLUMNS,
    PITZER_COLUMNS,
)


@pytest.fixture
def frame() -> pd.DataFrame:
    """One row of every column an output frame can carry."""
    return pd.DataFrame(
        {
            **{name: [0.0] for name in NEARFIELD_COLUMNS},
            **{name: [0.0] for name in CHEMISTRY_COLUMNS},
        }
    ).assign(merged=[False])


# ------------------------------------------------------------------ the registry is complete


def test_every_output_column_declares_a_dimension() -> None:
    """The registry is what makes the refusal below safe rather than obstructive."""
    for registry in (NEARFIELD_COLUMNS, CHEMISTRY_COLUMNS, OXYGEN_COLUMNS, FARFIELD_COLUMNS):
        missing = [name for name in registry if name not in _DIMENSIONS]
        assert not missing, missing


def test_every_declared_dimension_resolves_in_both_systems() -> None:
    for system in SYSTEMS.values():
        for name, dimension in _DIMENSIONS.items():
            assert system.unit_for(dimension) is not None, f"{name} in {system.name}"


def test_the_registry_carries_nothing_the_outputs_do_not() -> None:
    """A stale entry would be harmless but misleading about what the outputs contain."""
    known = {
        *NEARFIELD_COLUMNS,
        *CHEMISTRY_COLUMNS,
        *PITZER_COLUMNS,
        *PHREEQC_COLUMNS,
        *OXYGEN_COLUMNS,
        *FARFIELD_COLUMNS,
        # A frame adapted from an exe `.dat` carries the exe's own pH and saturation states too.
        *EXE_CHEMISTRY_COLUMNS,
    }
    assert set(_DIMENSIONS) == known


def test_a_frame_adapted_from_an_exe_trace_converts() -> None:
    """The two layers have to compose: a `.dat` frame is as convertible as a run's."""
    frame = pd.DataFrame(
        {"depth_m": [3.048], "dilution": [10.0], **{name: [1.0] for name in EXE_CHEMISTRY_COLUMNS}}
    )
    out = convert_frame(frame, US)
    assert out["depth_ft"].iloc[0] == pytest.approx(10.0)
    for name in EXE_CHEMISTRY_COLUMNS:
        assert name in out.columns, name


# ------------------------------------------------------------------ the conversions themselves


def test_si_is_a_no_op_that_still_copies(frame: pd.DataFrame) -> None:
    """One code path for both systems, and no aliasing back into the caller's frame."""
    out = convert_frame(frame, "SI")
    assert list(out.columns) == list(frame.columns)
    pd.testing.assert_frame_equal(out, frame)
    out.iloc[0, 0] = 999.0
    assert frame.iloc[0, 0] != 999.0


def test_lengths_speeds_and_temperatures_convert_and_are_renamed() -> None:
    frame = pd.DataFrame({"depth_m": [3.048], "speed_m_s": [0.3048], "temperature_degC": [100.0]})
    out = convert_frame(frame, US)
    assert list(out.columns) == ["depth_ft", "speed_ft_s", "temperature_degF"]
    assert out["depth_ft"].iloc[0] == pytest.approx(10.0)
    assert out["speed_ft_s"].iloc[0] == pytest.approx(1.0)
    assert out["temperature_degF"].iloc[0] == pytest.approx(212.0)


def test_the_temperature_conversion_is_the_exact_inverse_of_the_input_side() -> None:
    """Both directions come off the same two constants, so they cannot drift apart."""
    for celsius in (-2.0, 0.0, 10.5, 37.0):
        fahrenheit = US.temperature(celsius)
        back = units.convert_to_si(TableKind.AMBIENT, "temperature", 2, fahrenheit)
        assert back == pytest.approx(celsius, abs=1e-12)


def test_flow_reaches_both_units_a_permit_is_written_in() -> None:
    from plumes2.display import CUBIC_FEET_PER_SECOND, MGD

    one_mgd = units.MGD_TO_CUBIC_METRES_PER_SECOND
    assert MGD(one_mgd) == pytest.approx(1.0)
    assert CUBIC_FEET_PER_SECOND(units.CUBIC_FEET_TO_CUBIC_METRES) == pytest.approx(1.0)
    assert US.flow is MGD, "MGD is the default because it is what the exe's own dropdown leads on"


def test_density_and_the_chemistry_stay_in_si_in_every_system(frame: pd.DataFrame) -> None:
    """Declined deliberately -- mg/L would mean picking a side in the exe's conversion slip."""
    out = convert_frame(frame, US)
    for name in ("density_kg_m3", "total_alkalinity_umol_kg", "pco2_uatm", "ph_total"):
        assert name in out.columns, name
    pd.testing.assert_series_equal(out["density_kg_m3"], frame["density_kg_m3"])


def test_flags_and_ratios_keep_their_type(frame: pd.DataFrame) -> None:
    """A bool multiplied by 1.0 would silently become a float, and `merged` is a flag."""
    out = convert_frame(frame, US)
    assert out["merged"].dtype == bool
    assert out["dilution"].dtype == frame["dilution"].dtype
    assert "dilution" in out.columns, "a dimensionless name gains no suffix"


def test_the_far_field_converts_too() -> None:
    frame = pd.DataFrame({name: [1.0] for name in FARFIELD_COLUMNS})
    out = convert_frame(frame, US)
    assert list(out.columns) == [
        "distance_ft",
        "width_ft",
        "dilution",
        "dilution_factor",
        "travel_time_hr",
    ]
    assert out["distance_ft"].iloc[0] == pytest.approx(1.0 / units.FEET_TO_METRES)


# ------------------------------------------------------------------ the refusals


def test_an_undeclared_column_is_refused_rather_than_passed_through() -> None:
    frame = pd.DataFrame({"depth_m": [1.0], "mystery_furlongs": [2.0]})
    with pytest.raises(UndeclaredColumnError, match="mystery_furlongs"):
        convert_frame(frame, US)


def test_an_already_converted_frame_is_refused(frame: pd.DataFrame) -> None:
    """SI is the only source of truth: a converted frame is for reading, not for converting."""
    once = convert_frame(frame, US)
    with pytest.raises(UndeclaredColumnError):
        convert_frame(once, SI)


def test_an_unknown_system_name_raises() -> None:
    with pytest.raises(KeyError):
        convert_frame(pd.DataFrame({"depth_m": [1.0]}), "imperial-ish")


def test_a_system_is_frozen(frame: pd.DataFrame) -> None:
    """Nothing may rebind a unit mid-report and leave two panels disagreeing."""
    with pytest.raises((AttributeError, TypeError)):
        US.length = _FIXED["density"]  # type: ignore[misc]


def test_a_custom_system_needs_no_change_here() -> None:
    """Mixed systems are a legitimate request -- feet with celsius happens on US permits."""
    mixed = UnitSystem(
        name="mixed", length=US.length, speed=SI.speed, temperature=SI.temperature, flow=US.flow
    )
    out = convert_frame(pd.DataFrame({"depth_m": [1.0], "temperature_degC": [10.0]}), mixed)
    assert list(out.columns) == ["depth_ft", "temperature_degC"]
    assert out["temperature_degC"].iloc[0] == pytest.approx(10.0)
