"""The semantic case model: validated physical inputs, all in SI.

This is the layer the physics reads. It sits above the lossless file views in
:mod:`plumes2.io`, which keep padding rows, unit selectors and undecoded flags so
files round-trip; here everything is resolved, converted and range-checked.

Design points worth stating, because they follow from things the reference cases
taught us rather than from taste:

* **Everything is SI.** The exe accepts feet and MGD on input but always reports SI,
  and its selectors rescale values silently (:mod:`plumes2.units`). Converting once,
  at the boundary, is the only way to keep that from leaking.
* **The seabed is derived, not stored.** `bottom_depth = port_depth + port_elevation`,
  confirmed by case10 where a 2.0 m port on a 1.0 m riser terminated against a 3.0 m
  bottom. Several projects in the repo are geometrically odd under this rule (a 2.0 m
  port on a 15.0 m riser implies 17 m of water against a 15 m ambient profile), so it
  is surfaced as a warning rather than an error -- the exe runs them.
* **Chemistry is modelled here even though the exe does not store it.** No `.prj`
  contains chemistry state, so a project written from our YAML cannot round-trip
  chemistry back into the exe. Keeping it in the model anyway is what lets us drive
  the chemistry module at all.
* **Optional means optional.** The ambient chemistry pH column is blank in case03 and
  the exe derives it, so `ph` is `None`-able and must not become 0.0.
"""

from __future__ import annotations

import math
import warnings
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Safe at module level: neither `seawater` nor `crossplume` imports anything from this package,
# so there is no cycle.
from plumes2.crossplume import SimilarityProfile
from plumes2.seawater import EquationOfState

__all__ = [
    "AmbientChemistryLevel",
    "AmbientDOLevel",
    "AmbientLevel",
    "AmbientProfile",
    "CarbonateSettings",
    "Case",
    "ConstantRangeWarning",
    "DesignWarning",
    "Diffuser",
    "EddyDiffusivityLaw",
    "Effluent",
    "EffluentChemistry",
    "EffluentDO",
    "ExeBuild",
    "FarFieldSettings",
    "GeometryWarning",
    "MixingZone",
    "NearFieldSettings",
    "PHRangeWarning",
    "PHScale",
    "SimilarityProfile",
]

Positive = Annotated[float, Field(gt=0)]
NonNegative = Annotated[float, Field(ge=0)]
#: A direction in the horizontal plane, degrees counter-clockwise from +x -- the PLUMES manual's
#: convention ("+ve CCW from x-axis"), fixed by test19 (`nearfield.state.horizontal_unit`).
#: Not a compass bearing: nothing in the model says which way +x points on the site.
Direction = Annotated[float, Field(ge=0, le=360)]


class GeometryWarning(UserWarning):
    """The geometry is self-inconsistent but still runnable, as the exe treats it."""


def _interpolate(at: float, depths: list[float], values: list[float]) -> float:
    """Linear interpolation over an ambient profile, clamped at both ends.

    ⚠️ Deliberately not `AmbientProfileView`, which is the module that owns interpolation policy:
    `ambient` imports `config`, so reaching the other way would be a cycle. This is used for one
    design check on two scalars, and clamping matches the view's own no-extrapolation default --
    but if it ever needs to do more than that, the dependency should be inverted rather than
    this grown.
    """
    if at <= depths[0]:
        return values[0]
    if at >= depths[-1]:
        return values[-1]
    for (low, high), (first, second) in zip(pairwise(depths), pairwise(values), strict=True):
        if low <= at <= high:
            span = high - low
            return first if span == 0 else first + (second - first) * (at - low) / span
    return values[-1]


class DesignWarning(UserWarning):
    """The discharge is outside the regime the near-field model is built for.

    Distinct from `GeometryWarning`, which says the inputs contradict each other. This one says the
    inputs are perfectly consistent and the *model* may not apply to them -- a different problem,
    and one only the user can judge.
    """


class ConstantRangeWarning(UserWarning):
    """A carbonate constant is being evaluated outside the window it was fitted in.

    The third of three, and the narrowest: `GeometryWarning` says the inputs contradict each
    other, `DesignWarning` says the *near-field* model may not apply, and this one says a
    **chemistry** number is an extrapolation. The plume still integrates and the pH is still
    printed; what changes is how much the last decimal is worth.

    ⚠️⚠️ **This is not hypothetical for the work this port exists to do.** Lueker et al. (2000) --
    the exe's default K1K2 and case03's selection -- was fitted over S 19-43 and T 2-35 C. An
    alkalinity-elevated discharge is a *high-salinity, high-pH* plume by construction: case07's
    effluent is already 45 psu, outside it, and the dose study (PLAN.md §8e) pushes further. Until
    this warning existed the extrapolation was silent, so nothing distinguished an interpolated
    pH from an extrapolated one -- which is the same defect shape as row 197, where a 48x enthalpy
    error produced a 10x error in `Ksp*` with no failing comparison anywhere.

    ⚠️ It says nothing about *how wrong* the number is. The fitted window is where the fit was
    checked, not a cliff edge; a plume half a unit outside it is probably fine and a plume twenty
    units outside it probably is not. The warning exists so the reader can ask, not so the model
    can answer.
    """


class PHRangeWarning(ConstantRangeWarning):
    """The carbonate system was solved at a pH the port has never been checked at.

    A `ConstantRangeWarning` by inheritance -- filters and `pytest.warns` on the parent still
    catch it -- but a distinct category, so a sweep row can say *which* window the cell left. The
    S/T window is where the selected option was **fitted**; this one is where the port's chemistry
    has been **compared to anything** -- `chem.constants.PH_PARITY_WINDOW`, currently
    **pH 7.5-12.05 (total)**.

    ⭐⭐ **The ceiling is measured, and it moved the day it was earned.** It was 10.5 on the
    morning of 2026-08-25 -- the top of the archive, case03/case04's port -- because the dose dry
    run had reached pH 12 in silence and nothing distinguished that from an interpolated number.
    The four `pending/dose_parity` runs came back the same afternoon and put the exe's own CO2SYS
    at pH 9.148 to 11.988; it reads 0.011-0.025 below PyCO2SYS across the whole span, and the gap
    *narrows* above pH 11.5 rather than diverging. So the window is **12.05**, and the study's
    whole dose axis is now inside it.

    ⚠️ Above that nothing has been checked, and the way to move the ceiling again is to run the
    exe there -- not to widen the window.
    """


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class EddyDiffusivityLaw(StrEnum):
    """Brooks (1960) eddy-diffusivity growth laws."""

    CONSTANT = "constant"
    LINEAR = "linear"
    FOUR_THIRDS = "four_thirds"


class ExeBuild(StrEnum):
    """Which exe generation to reproduce, where the two disagree.

    ⚠️ **The builds are not interchangeable, and which one you want depends on the question.**
    The 2026 builds carry the carbonate and DO modules; the pre-2026 build offers more output
    columns and is what the far-field work uses for that reason. So a project can legitimately be
    run on either, and the archive holds traces from both -- case31 has one of each in a single
    folder.

    Exactly **one** modelled quantity differs so far: the wastefield width's angular correction.
    Measured on every archived trace that prints a width (row 96, and its legacy companion):

    | | current-build traces | legacy-build traces |
    |---|---|---|
    | with the cosine factor | **0.005 m** worst | 13.61 m worst |
    | without it | 13.61 m worst | **0.59 m** worst |

    The same project gives 96.29 m on a current build and 109.59 m on a legacy one -- a 13.30 m
    gap that is exactly the correction on an 18-port, 6.10 m, 30-degree diffuser. ⚠️ The legacy
    residual is 0.59 m rather than 0.005: the uncorrected span is right but the *diameter* the exe
    adds to it is not the last printed row (section 7 item 22), so this reproduces the legacy law
    to about 0.5 % rather than exactly.

    ⚠️ Nothing else in the port branches on this. The near-field trajectories are build-invariant
    -- the shipped example and case13 are bit-identical -- and the output-column difference is a
    GUI selection, not physics.
    """

    #: 2026 builds. The wastefield width carries `|cos(H-angle - current)|`.
    CURRENT = "current"
    #: Pre-2026. No angular correction at all: the width is the bare span plus a diameter.
    LEGACY = "legacy"


class PHScale(StrEnum):
    """pH scales the exe accepts. case03 entered free and the output reports total."""

    TOTAL = "total"
    SEAWATER = "seawater"
    FREE = "free"
    NBS = "nbs"


class Diffuser(_Model):
    """Diffuser geometry, SI."""

    port_diameter: Positive
    port_elevation: NonNegative
    vertical_angle: Annotated[float, Field(ge=-90, le=90)]
    horizontal_angle: Direction
    n_ports: Annotated[int, Field(ge=1)]
    port_spacing: NonNegative
    port_depth: Positive
    x_position: float = 0.0
    y_position: float = 0.0

    @property
    def bottom_depth(self) -> float:
        """Seabed depth below the surface. Confirmed by case10's bottom hit."""
        return self.port_depth + self.port_elevation

    @property
    def port_area(self) -> float:
        return math.pi * (self.port_diameter / 2.0) ** 2

    @property
    def diffuser_length(self) -> float:
        """Span of the port line. Zero for a single port."""
        return (self.n_ports - 1) * self.port_spacing

    def effective_spacing(
        self, current_direction: float, *, build: ExeBuild = ExeBuild.CURRENT
    ) -> float:
        """Port spacing projected across the current: `spacing * |cos(H-angle - current)|`.

        **Scope: this is the wastefield-width correction in the current exe build only.**
        It reproduces every current-build width exactly, including two independent
        measurements at a 30 degree offset with different final diameters (case13 with
        chemistry on, 96.29 m; case14 with it off, 97.60 m). Every archived-diffuser case discharges
        parallel to the current, so the offset is zero and the correction is invisible --
        which is why the uncorrected form fitted all of them.

        Two things it is *not*:

        * **Not the older build's behaviour.** The shipped upstream trace reports 109.59 m
          where the current build gives 96.29 m for a byte-equivalent project, implying
          essentially no correction. The cosine was evidently added between releases.
        * **Not the merging criterion**, which is a genuinely different reduction and lives in
          :mod:`plumes2.nearfield.merging`. Merging is build-invariant -- the shipped example and
          case13 have bit-identical trajectories and merge at the same step -- and it turns on
          `|sin psi|` against the plume's *instantaneous* bearing, not on a cosine of the static
          discharge angle. The interval-1 runs this docstring once asked for were supplied
          (test19, test20) and settled it: see `merging.effective_half_spacing`, which needs no
          fitted constant. Do not reach for the width correction to decide when plumes merge.

        Untested outside 0, 30 and 45 degrees. `abs` is a guess past 90 degrees, where a
        signed cosine would give a negative spacing; the 4th-edition reference states a 20 degree
        floor on the *merging* spacing, which `merging.MERGING_FLOOR_DEGREES` implements -- whether
        the width correction has one too is unknown.
        """
        if build is ExeBuild.LEGACY:
            # The pre-2026 build applies no angular correction at all. Returning the bare
            # spacing here -- rather than branching in `wastefield_width` -- keeps the two
            # laws expressed in one place, and makes `effective_spacing` mean the same thing
            # to both callers: the spacing this build presents across the current.
            return self.port_spacing
        return self.port_spacing * abs(
            math.cos(math.radians(self.horizontal_angle - current_direction))
        )

    # ⚠️ **There is deliberately no merge-trigger method here.** An earlier revision carried
    # `merging_spacing`, an ellipse `sqrt(cos^2 + 0.596^2 sin^2)` fitted to the measured brackets,
    # plus the fitted constant as a class variable. Ledger row 118 flagged the fit as suspect and
    # `nearfield/merging.effective_half_spacing` replaced it with a derived law -- `(L/2)|sin psi|`
    # against the plume's *instantaneous* bearing, with no fitted constant -- but the old method
    # survived, uncalled, with a docstring still presenting the fit as current. It was removed in
    # the 2026-08-17 audit. `effective_spacing` below is a **different** reduction and is live: it
    # governs the wastefield width, uses `|cos|`, and is exact on eight runs (row 96).

    def wastefield_width(
        self,
        final_plume_diameter: float,
        current_direction: float,
        *,
        build: ExeBuild = ExeBuild.CURRENT,
    ) -> float:
        """`(n - 1) * effective_spacing + diameter`.

        Exact on eight independent exe runs, spanning 1 and 25 ports, spacings of 0.60,
        2.00 and 6.10 m, and both angle cases. See :meth:`effective_spacing` for the one
        run it does not fit.

        ⚠️ **`build` is not cosmetic.** On a 30-degree diffuser the two laws differ by
        **13.30 m** out of 110, and the archive holds traces from both generations -- so the
        default reproduces the 2026 builds and `ExeBuild.LEGACY` reproduces the pre-2026 one.
        See :class:`ExeBuild` for the measurements either way.
        """
        return (self.n_ports - 1) * self.effective_spacing(
            current_direction, build=build
        ) + final_plume_diameter

    @model_validator(mode="after")
    def _warn_on_multiport_without_spacing(self) -> Self:
        if self.n_ports > 1 and self.port_spacing == 0:
            warnings.warn(
                f"{self.n_ports} ports with zero spacing: merging would trigger "
                "immediately, since plumes merge once the diameter reaches the spacing",
                GeometryWarning,
                stacklevel=3,
            )
        return self


class Effluent(_Model):
    """Discharge properties. `flow` is total across all ports, in m3/s.

    `excess_density` exists for effluents whose dissolved load is not seawater's -- pure water
    carrying NaOH, say. The equation of state reads salinity alone, so the hydroxide's mass would
    otherwise be invisible to the buoyancy; giving it as an equivalent salinity instead would
    hand the *chemistry* a false seawater fraction (Mg, borate, and a strongly salinity-
    dependent Kw -- tried and abandoned 2026-09-08, when the coupling ran away). So it is a
    separate, density-only quantity: added to the plume density at the port, diluted with the
    effluent mass along the trajectory (`excess / D`), and never seen by the carbonate system.
    """

    flow: Positive
    salinity: NonNegative = 0.0
    temperature: float = 20.0
    pollutant: NonNegative = 0.0
    #: Density the dissolved load adds beyond what `salinity` accounts for, kg/m3 at the port.
    #: Conservative in the effluent mass, invisible to the chemistry; not stored in a `.prj`.
    excess_density: NonNegative = 0.0

    def exit_velocity(self, diffuser: Diffuser) -> float:
        """Per-port exit velocity.

        Worth having as a first-class quantity: case09 showed the exe drives the plume
        clean through the free surface at 39.5 m/s, where the same total flow through
        25 ports (1.58 m/s) is fine.
        """
        return self.flow / diffuser.n_ports / diffuser.port_area


class MixingZone(_Model):
    acute_distance: NonNegative
    chronic_distance: NonNegative

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        if self.chronic_distance and self.acute_distance > self.chronic_distance:
            raise ValueError(
                f"acute mixing zone ({self.acute_distance} m) is farther than the "
                f"chronic one ({self.chronic_distance} m)"
            )
        return self


class AmbientLevel(_Model):
    depth: NonNegative
    current_speed: NonNegative = 0.0
    current_direction: Direction = 0.0
    salinity: NonNegative = 0.0
    temperature: float = 20.0
    background_pollutant: NonNegative = 0.0
    decay_rate: NonNegative = 0.0
    farfield_speed: NonNegative = 0.0
    farfield_direction: Direction = 0.0
    dispersion_alpha: NonNegative = 3.0e-4


class AmbientChemistryLevel(_Model):
    """Ambient carbonate chemistry. Units are umol/kg, as the GUI takes them.

    `ph` is optional: case03 leaves the column blank and the exe derives pH from TA and
    DIC. It must stay None rather than becoming 0.0.
    """

    depth: NonNegative
    total_alkalinity: NonNegative
    dic: NonNegative
    ph: Annotated[float, Field(ge=0, le=14)] | None = None
    #: The exe ignores this entirely (case06: Ca = 5000 left omega unchanged), but it
    #: is kept so projects round-trip and so our own solver can use it.
    calcium: NonNegative | None = None


class AmbientDOLevel(_Model):
    depth: NonNegative
    dissolved_oxygen: NonNegative
    cbod5: NonNegative = 0.0
    nbod5: NonNegative = 0.0


class AmbientProfile(_Model):
    """Depth profiles. Depths must increase, and all profiles share that requirement."""

    levels: Annotated[list[AmbientLevel], Field(min_length=1)]
    chemistry: list[AmbientChemistryLevel] = Field(default_factory=list)
    dissolved_oxygen: list[AmbientDOLevel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_monotonic(self) -> Self:
        for name, rows in (
            ("levels", self.levels),
            ("chemistry", self.chemistry),
            ("dissolved_oxygen", self.dissolved_oxygen),
        ):
            depths = [row.depth for row in rows]
            if any(b <= a for a, b in pairwise(depths)):
                raise ValueError(f"ambient {name}: depths must strictly increase, got {depths}")
        return self

    @property
    def max_depth(self) -> float:
        return self.levels[-1].depth

    @property
    def has_chemistry(self) -> bool:
        return bool(self.chemistry)


class EffluentDO(_Model):
    """Effluent dissolved oxygen and biochemical demand, mg/L, with the decay rates.

    Not stored in any `.prj` — the Dissolved Oxygen tab is "not saved in the project file"
    (manual §5.2.6), exactly like the carbonate tab. So this exists only in our own case format,
    and a `.dat` from the exe is uninterpretable without the values written down separately. See
    `reference_cases/case24_dissolved_oxygen/README.md`, which is what makes that archive
    usable at all.

    ⚠️⚠️ **These two are not interchangeable, and the exe treats them in opposite ways.** Every
    trace up to case28 could see only the difference `dissolved_oxygen - idod`, so they looked like
    one number; case28's runs 11 and 12 differ *only* in `dissolved_oxygen`, 2 against 20, and
    separate them outright. `dissolved_oxygen` is carried by the effluent and **dilutes away as
    `1/D`** -- 18 mg/L of it becomes 0.072 by `D` = 246.6, matching `18/D` to 0.0010. `idod` is
    applied to the **entrained ambient** instead and therefore **grows to its full typed value** as
    dilution proceeds. See `biochem.do_bod.near_field_oxygen` and its `reproduce_idod_on_ambient`
    flag: the manual makes IDOD an effluent property, and the exe does not.

    ⚠️ **The BOD fields do nothing in the near field, and that is measured.** case24's test39
    (cBOD5 0, nBOD5 30) and test40 (cBOD5 20, nBOD5 0) are **byte-identical**, so neither channel
    touches initial dilution. They act only on the far-field sag — which is exactly what the 3rd
    edition says: "on this time scale chemical and biological demands in the ambient are
    inconsequential although for farfield water quality considerations after initial dilution they
    are frequently decisive."
    """

    #: Effluent DO, mg/L.
    dissolved_oxygen: NonNegative = 0.0
    #: Immediate dissolved oxygen demand, mg/L. Subtracted from the effluent before mixing, and
    #: the 3rd edition is explicit that its contribution is negative.
    idod: NonNegative = 0.0
    #: Five-day carbonaceous and nitrogenous demand, mg/L.
    cbod5: NonNegative = 0.0
    nbod5: NonNegative = 0.0
    #: Decay rates at 20 °C, per day. The manual's defaults; case24 used 0.23 for **both**, which
    #: was an accident there and is recorded in that case's README.
    cbod_decay: Positive = 0.23
    nbod_decay: Positive = 0.1
    #: Arrhenius-style temperature coefficients for eqs 26-27, `k(T) = k(20) theta^(T-20)`.
    theta_c: Positive = 1.047
    theta_n: Positive = 1.08


class EffluentChemistry(_Model):
    """Effluent carbonate endmember, umol/kg.

    Not stored in any `.prj`, so this exists only in our own case format. The exe
    prefers TA + DIC and falls back to TA + pH when DIC is zero (case04); we require
    the pair to be stated rather than inferring it from a sentinel.

    The pairing is measured, not guessed: case03 entered TA 4000 / DIC 0 / pH 10.5 and the
    plume endmember came out at DIC 1646, while case04 entered TA 4000 / DIC 1646 / pH 11
    and the endmember stayed at 1646 (times the density factor) with the pH 11 discarded.

    `ph_scale` defaults to **free**, which is both what the GUI labels the field and what
    the data confirms: TA 4000 with pH 10.5 free gives DIC 1646.29 against case03's 1645.9,
    where total would give 1608 and NBS 1670.
    """

    total_alkalinity: NonNegative
    dic: NonNegative | None = None
    ph: Annotated[float, Field(ge=0, le=14)] | None = None
    ph_scale: PHScale = PHScale.FREE

    @model_validator(mode="after")
    def _need_exactly_one_partner(self) -> Self:
        if (self.dic is None) == (self.ph is None):
            raise ValueError(
                "effluent chemistry needs total_alkalinity plus exactly one of "
                "dic or ph (the exe uses DIC when both are given and silently "
                "ignores the pH -- see reference_cases/case04)"
            )
        return self


class CarbonateSettings(_Model):
    """Equilibrium-constant options, matching the exe's dialog."""

    #: 1-14, the classic CO2SYS numbering, which the exe's dialog reproduces exactly.
    #: 10 = Lueker et al. (2000) is both the exe's default and case03's selection.
    k1k2_option: Annotated[int, Field(ge=1, le=14)] = 10
    #: 1-4. A *combined* selector: each option pairs a bisulfate constant with a
    #: total-borate ratio. 1 = Dickson bisulfate + Uppstrom borate (the exe's default).
    kso4_option: Annotated[int, Field(ge=1, le=4)] = 1
    #: Zhong & Mucci (1989) rate constants as the GUI presents them. K is exp(log_k),
    #: not 10 ** log_k -- confirmed against case03's R_cal column.
    calcite_log_k: float = -0.106
    calcite_exponent: float = 2.87
    #: The 35 < S < 44 aragonite band.
    aragonite_log_k: float = 1.11
    aragonite_exponent: float = 2.26
    #: The dialog's other aragonite entry, shown without a salinity range beside it.
    aragonite_low_log_k: float = 1.53
    aragonite_low_exponent: float = 2.33
    #: The exe evaluates (omega - 1) ** exponent unguarded, which is NaN for
    #: omega < 1 and poisons the whole run (case09). We return zero instead. Set this
    #: True only to study the exe's behaviour; it is not a sane default.
    reproduce_undersaturated_nan: bool = False
    #: ⚠️ The exe reports zero aragonite in `25 <= S <= 35` -- a dead band in the middle of
    #: ordinary seawater -- while its dialog declares one continuous `0 < S < 35` band. Below
    #: 25 it evaluates that band normally (case13, 15 rows to 1.1e-4). We use the dialogued
    #: edge. ⚠️ Renamed from `reproduce_aragonite_zero_below_s35`, which named a floor at 35
    #: that case13 disproved; there is no floor, there is a gap.
    reproduce_aragonite_band_gap: bool = False
    #: The exe multiplies the *effluent* TA and DIC by the effluent density in kg/L --
    #: a umol/kg treated as umol/L -- while leaving the ambient values alone, biasing the
    #: endmember 2.7 % high. Measured at 4000 -> 4108.4 and 1646 -> 1690.0 in case03/04.
    reproduce_effluent_concentration_scaling: bool = False


class NearFieldSettings(_Model):
    aspiration_coefficient: Positive = 0.1
    contraction_coefficient: Annotated[float, Field(gt=0, le=1)] = 1.0
    #: Carried for fidelity; the exe never uses it.
    light_absorption: NonNegative = 0.16
    #: "No. of maximum plume rise or fall". 2 in the upstream example, 3 in every
    #: archived-diffuser case.
    max_rise_or_fall: Annotated[int, Field(ge=0, le=3)] = 2
    #: The GUI's "stop plume at surface hit" checkbox — a control in its own right, distinct
    #: from `max_rise_or_fall`. case13 and case14 are the same project run with it on and
    #: off: the trajectories are bit-identical, but with it on the run ends at the
    #: surfacing step (275) and with it off it continues to a second trapping (476). It is
    #: **not stored in the `.prj`** (both runs used the same file), so it is session state in
    #: the exe, like the chemistry settings — a parsed value is a default, not a fact.
    #:
    #: ⚠️ Defaults to **False**, against the manual's "checked by default", because that is
    #: what the archive was generated with: every recent run used *bottom*-hit only, and six
    #: of the seven surface hits on record are sailed straight through. Surfacing terminating
    #: a run is the exception here, not the rule.
    stop_at_surface: bool = False
    #: The GUI's "stop plume at bottom hit" checkbox. Confirmed terminal by case10, which
    #: ends on "Plume hits the bottom" after a single oscillation event.
    stop_at_bottom: bool = True
    #: The GUI's "stop plume at shoreline hit" checkbox. Measured **inert**: case12 enables
    #: it and its near-field table is unchanged (§7.15). Carried so a project round-trips
    #: and so the finding stays visible, but nothing acts on it.
    stop_at_shoreline: bool = False
    output_interval: Annotated[int, Field(ge=1)] = 5
    #: The exe's cap, from case09 running to step 5001.
    max_steps: Annotated[int, Field(ge=1)] = 5000
    max_dilution: Positive = 5000.0
    #: Which density formula the near field integrates with.
    #:
    #: ⭐⭐⭐ **`KNUDSEN` is what the exe computes** — identified 2026-08-20 to one rounding
    #: digit over 51 670 archived rows with no fitted parameter (`seawater.knudsen_sigma_t`).
    #: `EOS80` stays the default under §2's "correct by default, reproduce on request", and
    #: because it is the standard this port's own science should rest on.
    #:
    #: ⚠️ It is not a cosmetic choice. Buoyancy is `rho_ambient - rho_plume`, which collapses
    #: toward zero near the trapping level, so the EOS difference is relatively largest exactly
    #: where the trapping depth is decided — ledger 148 measures the dilution error growing
    #: 0.31 % -> 5.16 % across that span. Select `KNUDSEN` for a parity comparison against a
    #: trace; leave it alone for anything else.
    equation_of_state: EquationOfState = EquationOfState.EOS80
    #: Which cross-plume similarity profile the centreline is read through.
    #:
    #: ⭐ **The exe has three, and this is its `Default Profile`** (case48, ledger row 278). It
    #: does not touch the integration -- the profile is layered on the flux-averaged solution,
    #: exactly as the exe does -- so it moves `centreline_dilution` and `peak_to_mean` and nothing
    #: else. Like the stop-at boxes it is GUI session state the `.prj` does not carry, so a parsed
    #: project always reads `PARABOLIC`; a trace made under another option has to say so.
    #: ✅ PLAN 8.4, decided 2026-08-26 (operator): the study quotes the **parabola**, and this
    #: stays a per-case setting so any of the exe's options -- or the literature's Gaussian -- can
    #: be selected when a user needs it, as the exe's own selector allows. See
    #: `plumes2.crossplume.SimilarityProfile`.
    similarity_profile: SimilarityProfile = SimilarityProfile.PARABOLIC


class FarFieldSettings(_Model):
    enabled: bool = True
    #: Which exe generation the wastefield width should reproduce. See :class:`ExeBuild`.
    #:
    #: ⚠️ It lives here because the width's only consumer is the far-field handoff, and
    #: **not** in `NearFieldSettings` even though the width is echoed in the near-field
    #: section of the `.dat`: the echo is a report, the handoff is a calculation.
    #:
    #: ⚠️ Like the stop-at checkboxes, the build is **not recorded in the `.prj`** -- there is
    #: no version string anywhere in 6 862 characters (section 7b) -- so a parsed project
    #: cannot tell you which build ran it. This defaults to `CURRENT` and a legacy comparison
    #: has to say so explicitly.
    exe_build: ExeBuild = ExeBuild.CURRENT
    law: EddyDiffusivityLaw = EddyDiffusivityLaw.FOUR_THIRDS
    interval: Positive = 10.0
    #: The far-field calculation distance. The exe runs one partial step past it (worst archived
    #: overshoot 8.357 m at interval 10, under 1 m at interval 1).
    #:
    #: ⚠️ **500.0 mirrors the operator's habit, not the exe's default.** The exe's stop dialog
    #: takes this and `max_dilution` together, stops at whichever binds first, and stores
    #: neither -- both are session state, the same class as the stop-at boxes. Left untyped,
    #: the exe defaults the distance to the **chronic-MZ boundary**, which ~12 archived traces
    #: show. Whether this field should follow the exe's default instead is a flagged decision
    #: (PLAN section 8c TODO 2), not one to change in passing.
    max_distance: Positive = 500.0
    #: The dilution stop entered beside the distance. ⚠️ Moved 5000 -> **10000** on 2026-08-24,
    #: by operator decision, to match their usual exe entry (row 277's census: five 10000x
    #: stops, three 5000x) -- and because 5000x was cutting far fields short of the chronic
    #: boundary on high-dilution sweep cells, turning the study's own quantity into NaN.
    #: `results.py` keeps the first row at or past the stop so the crossing is visible;
    #: `experiments.check_farfield_session_state` checks a returning run against both stops.
    max_dilution: Positive = 10000.0


class Case(_Model):
    """A complete, validated model case."""

    description: str = "Project Description"
    diffuser: Diffuser
    effluent: Effluent
    mixing_zone: MixingZone
    ambient: AmbientProfile
    near_field: NearFieldSettings = Field(default_factory=NearFieldSettings)
    far_field: FarFieldSettings = Field(default_factory=FarFieldSettings)
    effluent_chemistry: EffluentChemistry | None = None
    carbonate: CarbonateSettings = Field(default_factory=CarbonateSettings)
    #: ⚠️ Set alongside `effluent_chemistry` freely. The manual claims DO and pH "cannot be
    #: conducted simultaneously" (§5.2.6) but the exe does both in one run -- case24's test38 --
    #: so refusing the combination here would be stricter than the thing we are re-implementing.
    effluent_do: EffluentDO | None = None

    @property
    def oxygen_enabled(self) -> bool:
        """DO runs only when both endmembers are supplied, as chemistry does."""
        return self.effluent_do is not None and bool(self.ambient.dissolved_oxygen)

    @property
    def chemistry_enabled(self) -> bool:
        """Chemistry runs only when both endmembers are supplied."""
        return self.effluent_chemistry is not None and self.ambient.has_chemistry

    @property
    def exit_velocity(self) -> float:
        return self.effluent.exit_velocity(self.diffuser)

    def wastefield_width(self, final_plume_diameter: float) -> float:
        """Wastefield width, using the ambient current direction at the port depth.

        Follows `far_field.exe_build`, so a legacy comparison needs that set rather than a
        different call.
        """
        return self.diffuser.wastefield_width(
            final_plume_diameter,
            self.current_direction_at_port,
            build=self.far_field.exe_build,
        )

    @property
    def current_direction_at_port(self) -> float:
        """Ambient current direction interpolated to the port depth."""
        depths = [level.depth for level in self.ambient.levels]
        directions = [level.current_direction for level in self.ambient.levels]
        if len(depths) == 1:
            return directions[0]
        target = self.diffuser.port_depth
        if target <= depths[0]:
            return directions[0]
        if target >= depths[-1]:
            return directions[-1]
        for lower, upper, a, b in zip(depths, depths[1:], directions, directions[1:], strict=False):
            if lower <= target <= upper:
                span = upper - lower
                return a if span == 0 else a + (b - a) * (target - lower) / span
        return directions[-1]

    def densimetric_froude_number(self) -> float:
        """The discharge Froude number at the port, `U / sqrt(|g'| d)`. Manual §5.2.2.

        Above 1 the port is jetting and the near-field model applies; below 1 buoyancy dominates at
        the port itself and §5.2.2 treats that as a design problem. Densities are evaluated at the
        **port depth**, with the ambient interpolated there, because that is where the discharge
        actually meets the receiving water.

        ⚠️ It is a property of the case, not of a run, so it is available before integrating -- the
        point of a design check is to raise the question before the answer is computed.
        """
        from plumes2.seawater import densimetric_froude_number, density

        depth = self.diffuser.port_depth
        depths = [level.depth for level in self.ambient.levels]
        ambient_density = float(
            density(
                _interpolate(depth, depths, [level.salinity for level in self.ambient.levels]),
                _interpolate(depth, depths, [level.temperature for level in self.ambient.levels]),
            )
        )
        effluent_density = (
            float(density(self.effluent.salinity, self.effluent.temperature))
            + self.effluent.excess_density
        )
        return float(
            densimetric_froude_number(
                self.effluent.exit_velocity(self.diffuser),
                self.diffuser.port_diameter,
                effluent_density,
                ambient_density,
            )
        )

    def warn_if_outside_the_modelled_regime(self) -> None:
        """Emit `DesignWarning` if the discharge fails the manual's §5.2.2 Froude check.

        ⚠️ **Called from the validator *and* from `results.run`, and it needs both.** Pydantic's
        `model_copy` does not re-run validators, and building a variant with
        `case.model_copy(update=...)` is the idiom this codebase uses everywhere -- so a check that
        lived only in the validator would go silent for exactly the cases someone constructed by
        hand to explore a regime. `run` is the moment a number gets produced, whatever route the
        case took to get there.

        Warnings are deduplicated by Python per location, so the two call sites do not double up on
        a case that was constructed and then run.
        """
        froude = self.densimetric_froude_number()
        if froude < 1.0:
            warnings.warn(
                f"the discharge Froude number is {froude:.3g}, below 1: buoyancy dominates the "
                f"port's own momentum, so the discharge is not a jet and the near-field model is "
                f"outside the regime it was built for (manual section 5.2.2). Exit velocity "
                f"{self.effluent.exit_velocity(self.diffuser):.4g} m/s through a "
                f"{self.diffuser.port_diameter:g} m port. The result is still computed, because "
                f"the exe computes it too.",
                DesignWarning,
                stacklevel=3,
            )

    @model_validator(mode="after")
    def _check_design(self) -> Self:
        self.warn_if_outside_the_modelled_regime()
        return self

    @model_validator(mode="after")
    def _check_geometry(self) -> Self:
        bottom = self.diffuser.bottom_depth
        if self.diffuser.port_depth > bottom:
            raise ValueError(
                f"port depth {self.diffuser.port_depth} m exceeds the seabed at "
                f"{bottom} m (port depth + port elevation)"
            )
        if bottom > self.ambient.max_depth:
            warnings.warn(
                f"the seabed is at {bottom:g} m (port depth {self.diffuser.port_depth:g} "
                f"+ elevation {self.diffuser.port_elevation:g}) but the ambient profile "
                f"stops at {self.ambient.max_depth:g} m, so it will be extrapolated. "
                "Several projects in reference_cases/ have this shape and the exe runs "
                "them, but case09 shows extrapolation past a profile edge can produce "
                "nonsense.",
                GeometryWarning,
                stacklevel=3,
            )
        if self.chemistry_enabled:
            chem_max = self.ambient.chemistry[-1].depth
            chem_min = self.ambient.chemistry[0].depth
            if chem_max <= self.diffuser.port_depth:
                # The exe enforces this and refuses to run otherwise, with:
                #   "Please input the ambient chemistry conditions at a depth greater
                #    than port depth"
                # Observed 2026-08-12 when a generated 11 m-port project met a chemistry
                # table that only reached 4 m.
                raise ValueError(
                    f"the ambient chemistry profile must extend deeper than the port: "
                    f"its deepest level is {chem_max:g} m and the port is at "
                    f"{self.diffuser.port_depth:g} m. The exe refuses to run this case "
                    f'with "Please input the ambient chemistry conditions at a depth '
                    f'greater than port depth".'
                )
            if chem_min > self.diffuser.port_depth:
                warnings.warn(
                    f"the port is at {self.diffuser.port_depth:g} m but the ambient "
                    f"chemistry profile starts at {chem_min:g} m, so values above it will "
                    "be extrapolated. The exe only checks the deep end, but extrapolating "
                    "past the shallow end is what broke case09's transport.",
                    GeometryWarning,
                    stacklevel=3,
                )
        return self
