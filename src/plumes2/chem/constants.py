"""Carbonate constants, and the mapping from the exe's option numbers to PyCO2SYS.

Two jobs.

**Tracking the constant selections.** The exe's Carbonate Chemistry tab exposes the classic
CO2SYS selectors, and its dialog help text (supplied by the user, 2026-08-12) enumerates
them in full. That text is the authority here, and it corrects the manual on two points:

- There are **14** K1K2 options, not the "ten different options" §5.2.5 claims. They are
  the classic CO2SYS list 1-14, which PyCO2SYS numbers identically, so `opt_k_carbonic`
  is the exe's own number. The correspondence is therefore **confirmed**, not assumed.
- **KSO4 is a combined selector**, not a bare KSO4 choice: each of its four options pairs a
  bisulfate dissociation constant with a total-borate-to-salinity ratio. This is CO2SYS
  MATLAB's `KSO4CONSTANTS` parameter. PyCO2SYS splits the two apart into
  `opt_k_bisulfate` and `opt_total_borate`, so one exe option maps to a *pair*. Note the
  exe cannot reach Waters & Millero (2013) bisulfate at all.

The help text also states the rule **"pH scale will be the same as K1,K2"**, and records
each option's native scale and validity window. That resolves what the reference data could
not: with the default option 10 (Lueker et al. 2000) the exe reports on the **total** scale.
`native_ph_scale` carries it, and `validity` supports warning when a plume leaves the range
its own constants were fitted in -- which real cases do, e.g. a 45 psu effluent against
Lueker's S 19-43.

**The solubility products.** These the manual does specify: `K_sp` "computed based on
temperature (T) and salinity (S) per Millero (1995)", and calcium from a salinity relation
`[Ca2+] = 0.01028 x S/35` (Murata et al. 2015). Millero (1995) reproduces Mucci (1983) for
both minerals, which is what is implemented here.

Both solubility functions agree with PyCO2SYS to machine precision -- a test asserts it.
Against the exe they differ by 0.09 % in the ratio `Ksp_aragonite / Ksp_calcite`, which is
the one combination the reference data measures without the pH solver or calcium getting in
the way, since those cancel in `Omega_calcite / Omega_aragonite`:

    exe                   1.57253 .. 1.58255
    Mucci 1983 / PyCO2SYS 1.57370 .. 1.58366

Small, systematic, and left alone: PLAN.md §4 records differences from the exe rather than
tuning to them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from plumes2.config import PHScale

__all__ = [
    "CALCIUM_AT_S35",
    "EXE_K1K2_OPTIONS",
    "EXE_KSO4_OPTIONS",
    "MAGNESIUM_AT_S35",
    "PH_PARITY_WINDOW",
    "ConstantSet",
    "K1K2Option",
    "KSO4Option",
    "PHWindow",
    "UnknownConstantOptionError",
    "ValidityRange",
    "calcium_from_salinity",
    "magnesium_from_salinity",
    "resolve_constants",
    "solubility_aragonite",
    "solubility_calcite",
    "warn_outside_ph_window",
    "warn_outside_validity",
]

#: Total calcium at S = 35, mol/kg (Murata et al. 2015, as the manual quotes it).
#: PyCO2SYS carries Riley & Tongudai (1967) unrounded, 0.0102845, so our Omega runs a
#: fixed 0.04 % below its -- the only difference between the two implementations.
CALCIUM_AT_S35 = 0.01028

#: Total magnesium at S = 35, mol/kg, from the Reference Composition of Millero et al.
#: (2008). Conservative with salinity in the same way calcium is, and needed for brucite
#: (PLAN.md §8b) -- nothing in the exe uses it, because the exe has no brucite.
MAGNESIUM_AT_S35 = 0.0528171


@dataclass(frozen=True, slots=True)
class ValidityRange:
    """The temperature and salinity window an option was fitted in."""

    temperature_min: float
    temperature_max: float
    salinity_min: float
    salinity_max: float

    def covers(self, salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.bool_]:
        s = np.asarray(salinity, dtype=np.float64)
        t = np.asarray(temperature, dtype=np.float64)
        return np.asarray(
            (s >= self.salinity_min)
            & (s <= self.salinity_max)
            & (t >= self.temperature_min)
            & (t <= self.temperature_max)
        )

    def describe(self) -> str:
        return (
            f"T {self.temperature_min:g}-{self.temperature_max:g} C, "
            f"S {self.salinity_min:g}-{self.salinity_max:g}"
        )


@dataclass(frozen=True, slots=True)
class K1K2Option:
    """One entry of the exe's K1K2 dropdown."""

    reference: str
    #: The scale the constants are on, which per the dialog is also the scale the exe
    #: reports pH on. None for the pure-water option, whose scale the text omits.
    native_ph_scale: PHScale | None
    validity: ValidityRange
    #: "Artificial seawater", "Real seawater", "Field measurements", "Pure water".
    medium: str


@dataclass(frozen=True, slots=True)
class KSO4Option:
    """One entry of the exe's combined KSO4 selector.

    Each option pairs a bisulfate constant with a total-borate-to-salinity ratio, which
    PyCO2SYS exposes as two independent settings.
    """

    bisulfate_reference: str
    borate_reference: str
    pyco2sys_k_bisulfate: int
    pyco2sys_total_borate: int


#: Exe K1K2 option -> its identity. PyCO2SYS `opt_k_carbonic` uses the same numbers.
EXE_K1K2_OPTIONS: dict[int, K1K2Option] = {
    1: K1K2Option(
        "Roy et al. 1993", PHScale.TOTAL, ValidityRange(0, 45, 5, 45), "artificial seawater"
    ),
    2: K1K2Option(
        "Goyet & Poisson 1989",
        PHScale.SEAWATER,
        ValidityRange(1, 40, 10, 50),
        "artificial seawater",
    ),
    3: K1K2Option(
        "Hansson 1973, refit by Dickson & Millero 1987",
        PHScale.SEAWATER,
        ValidityRange(2, 35, 20, 40),
        "artificial seawater",
    ),
    4: K1K2Option(
        "Mehrbach et al. 1973, refit by Dickson & Millero 1987",
        PHScale.SEAWATER,
        ValidityRange(2, 35, 20, 40),
        "artificial seawater",
    ),
    5: K1K2Option(
        "Hansson and Mehrbach, refit by Dickson & Millero 1987",
        PHScale.SEAWATER,
        ValidityRange(2, 35, 20, 40),
        "artificial seawater",
    ),
    6: K1K2Option(
        "GEOSECS (original Mehrbach 1973)",
        PHScale.NBS,
        ValidityRange(2, 35, 19, 43),
        "real seawater",
    ),
    7: K1K2Option(
        "Peng et al. 1987 (original Mehrbach)",
        PHScale.NBS,
        ValidityRange(2, 35, 19, 43),
        "real seawater",
    ),
    8: K1K2Option("Millero 1979, pure water only", None, ValidityRange(0, 50, 0, 0), "pure water"),
    9: K1K2Option(
        "Cai & Wang 1998",
        PHScale.NBS,
        ValidityRange(2, 35, 0, 49),
        "real and artificial seawater",
    ),
    10: K1K2Option(
        "Lueker et al. 2000 (exe default)",
        PHScale.TOTAL,
        ValidityRange(2, 35, 19, 43),
        "real seawater",
    ),
    11: K1K2Option(
        "Mojica Prieto & Millero 2002",
        PHScale.SEAWATER,
        ValidityRange(0, 45, 5, 42),
        "real seawater",
    ),
    12: K1K2Option(
        "Millero et al. 2002",
        PHScale.SEAWATER,
        ValidityRange(1.6, 35, 34, 37),
        "field measurements",
    ),
    13: K1K2Option(
        "Millero et al. 2006", PHScale.SEAWATER, ValidityRange(0, 50, 1, 50), "real seawater"
    ),
    14: K1K2Option(
        "Millero et al. 2010", PHScale.SEAWATER, ValidityRange(0, 50, 1, 50), "real seawater"
    ),
}

#: Exe KSO4 option -> the (bisulfate, total borate) pair it selects. The exe's own
#: numbering; note it offers no route to Waters & Millero (2013) bisulfate.
EXE_KSO4_OPTIONS: dict[int, KSO4Option] = {
    1: KSO4Option("Dickson 1990", "Uppstrom 1974", 1, 1),
    2: KSO4Option("Khoo et al. 1977", "Uppstrom 1974", 2, 1),
    3: KSO4Option("Dickson 1990", "Lee et al. 2010", 1, 2),
    4: KSO4Option("Khoo et al. 1977", "Lee et al. 2010", 2, 2),
}


@dataclass(frozen=True, slots=True)
class ConstantSet:
    """A resolved set of constant choices, with provenance."""

    exe_k1k2: int
    exe_kso4: int
    pyco2sys_k_carbonic: int
    pyco2sys_k_bisulfate: int
    pyco2sys_total_borate: int
    k1k2_reference: str
    bisulfate_reference: str
    borate_reference: str
    #: The scale the exe reports pH on for this K1K2 choice, per the dialog's
    #: "pH scale will be the same as K1,K2".
    native_ph_scale: PHScale | None
    validity: ValidityRange
    #: True now that the dialog help text has been read: the exe's K1K2 numbering is
    #: the classic CO2SYS list, which PyCO2SYS reproduces option-for-option.
    correspondence_confirmed: bool = True

    def describe(self) -> str:
        scale = self.native_ph_scale.value if self.native_ph_scale else "unstated"
        confirmed = "confirmed" if self.correspondence_confirmed else "ASSUMED"
        return (
            f"K1K2 option {self.exe_k1k2} = {self.k1k2_reference} "
            f"[{scale} scale, {self.validity.describe()}]; "
            f"KSO4 option {self.exe_kso4} = {self.bisulfate_reference} bisulfate + "
            f"{self.borate_reference} borate; correspondence {confirmed}"
        )

    def covers(self, salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.bool_]:
        """Whether each sample lies inside the chosen option's fitted window."""
        return self.validity.covers(salinity, temperature)


class UnknownConstantOptionError(ValueError):
    """Raised for a constant-set option the exe does not offer."""


def warn_outside_validity(
    constants: ConstantSet,
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    context: str,
    stacklevel: int = 4,
) -> int:
    """Emit `ConstantRangeWarning` if any sample sits outside the option's fitted window.

    Returns the number of samples outside, so a caller can report it without re-deriving it;
    zero means the run was fully inside and nothing was emitted.

    ⚠️ **Once per array, not once per sample.** The chemistry is solved vectorised over the whole
    trajectory, so this is called a handful of times per run rather than per row -- and the message
    names the *extremes* reached rather than listing offenders, because a 200-row plume that leaves
    the window leaves it on almost every row and a per-row warning would bury the one fact that
    matters.

    The message deliberately carries four things: which option, its window, how far outside the
    run actually went, and what share of the run was out. The last two are what separate "one
    sample grazed the edge" from "this entire plume is an extrapolation", and only the reader can
    judge which matters.
    """
    import warnings

    from plumes2.config import ConstantRangeWarning

    s = np.asarray(salinity, dtype=np.float64)
    t = np.asarray(temperature, dtype=np.float64)
    inside = constants.covers(s, t)
    outside = int(np.count_nonzero(~inside))
    if outside == 0:
        return 0

    def span(values: NDArray[np.float64], unit: str = "") -> str:
        """`45` for a scalar, `34-45` for a range. A plume is an array; an endmember is not."""
        low, high = float(np.min(values)), float(np.max(values))
        body = f"{low:.4g}" if low == high else f"{low:.4g}-{high:.4g}"
        return f"{body}{unit}"

    window = constants.validity
    excursions = []
    if np.any(s < window.salinity_min) or np.any(s > window.salinity_max):
        excursions.append(f"S reached {span(s)}")
    if np.any(t < window.temperature_min) or np.any(t > window.temperature_max):
        excursions.append(f"T reached {span(t, ' C')}")
    total = int(inside.size)
    share = "the sample lies" if total == 1 else f"{outside} of {total} samples lie"
    warnings.warn(
        f"{context}: K1K2 option {constants.exe_k1k2} ({constants.k1k2_reference}) was fitted "
        f"over {window.describe()}, and {share} outside it"
        + (f" -- {', '.join(excursions)}" if excursions else "")
        + ". The carbonate system is extrapolated there; pH and the saturation states are "
        "still computed but their accuracy is not established by the fit.",
        ConstantRangeWarning,
        stacklevel=stacklevel,
    )
    return outside


@dataclass(frozen=True, slots=True)
class PHWindow:
    """A total-scale pH interval, with what it is the interval *of*."""

    low: float
    high: float
    #: One clause naming the evidence the bounds rest on. Printed in the warning.
    basis: str

    def covers(self, ph_total: ArrayLike) -> NDArray[np.bool_]:
        ph = np.asarray(ph_total, dtype=np.float64)
        return np.asarray((ph >= self.low) & (ph <= self.high))

    def describe(self) -> str:
        return f"pH {self.low:g}-{self.high:g} (total)"


#: Where the port's carbonate chemistry has been checked against something. ⚠️ Not a fitted
#: window -- `ValidityRange` is that -- but a *parity* one: the range over which the exe's embedded
#: CO2SYS and PyCO2SYS have actually been run against each other on identical TA and DIC.
#:
#: ⭐⭐ **The ceiling moved 10.5 -> 12.05 on 2026-08-25, and it was measured rather than assumed.**
#: It was 10.5 that morning -- case03/case04's port, rows 41/43/128, the top of the archive -- with
#: `pending/dose_parity` queued to push it. Those four runs came back the same day: case03's
#: geometry at TA 4000 / 6000 / 10 000 / 20 000 with DIC 2500 entered, putting the exe's own port
#: pH at 9.148 / 10.628 / 11.483 / 11.988. Over 2050 rows spanning pH 8.37-11.99 the exe reads
#: **0.011-0.025 below** PyCO2SYS, and the gap does **not** run away at the top: it peaks near
#: pH 10.5 and *narrows* above 11.5, where hydroxide carries the alkalinity and both solvers are
#: doing less carbonate arithmetic rather than more.
#:
#: ⚠️ **12.05 rather than 12.0, and the 0.05 is deliberate headroom that has to be stated.** This
#: window is tested against *our* solved pH, and on the exe's own top-dose row -- TA 20 193.6,
#: DIC 2566.1, S 34.924, T 10.013 -- PyCO2SYS returns **12.008** where the exe printed 11.988. A
#: ceiling of 12.0 would therefore fire on the very run that is the evidence for it. The highest
#: *compared* point is 12.008; the ceiling sits a rounding above it rather than a rounding below.
#:
#: The floor stays nominal: nothing in the archive discharges below pH 7.5 and nothing has been
#: compared there.
PH_PARITY_WINDOW = PHWindow(
    7.5,
    12.05,
    "the exe and PyCO2SYS agree to 0.011-0.025 pH from ambient 8.37 up to 12.008 on case03/case04 "
    "(rows 41, 43, 128) and the four pending/dose_parity runs of 2026-08-25, and have never been "
    "compared above it",
)


def warn_outside_ph_window(
    ph_total: ArrayLike,
    *,
    context: str,
    window: PHWindow = PH_PARITY_WINDOW,
    stacklevel: int = 4,
) -> int:
    """Emit `PHRangeWarning` if any solved pH sits outside `window`; return how many did.

    The pH companion of `warn_outside_validity`, and the same shape: once per array, naming the
    extreme reached and the share of samples outside. ⚠️ The two answer different questions. That
    one says the *constants* were fitted elsewhere; this one says the *result* is a pH at which the
    port's chemistry has never been compared to the exe or to a measurement -- Lueker's window is S
    and T only, so the first dose dry run solved pH-12 seawater and nothing spoke (PLAN §8f).

    ⭐ **The window is evidence, not caution**, which is why it moved to pH 12 the day the
    `dose_parity` runs came back rather than being left conservative: a warning nobody can act on
    is noise, and the fix for this one is to run the exe where you intend to quote it. Above the
    ceiling the honest statement is that nothing has been checked -- ion pairing in `omega_brucite`
    is unmodelled and grows with `[OH-]`, and no constant set publishes a pH range at all. Like its
    companion, this says *ask*, not *how wrong*.
    """
    import warnings

    from plumes2.config import PHRangeWarning

    ph = np.asarray(ph_total, dtype=np.float64)
    finite = ph[np.isfinite(ph)]
    inside = window.covers(finite)
    outside = int(np.count_nonzero(~inside))
    if outside == 0:
        return 0
    total = int(finite.size)
    share = "the sample lies" if total == 1 else f"{outside} of {total} samples lie"
    excursions = []
    if np.any(finite > window.high):
        excursions.append(f"pH reached {float(np.max(finite)):.2f}")
    if np.any(finite < window.low):
        excursions.append(f"pH fell to {float(np.min(finite)):.2f}")
    warnings.warn(
        f"{context}: {share} outside {window.describe()}, the window in which this chemistry "
        f"has been checked -- {', '.join(excursions)}. Basis of the window: {window.basis}. "
        "pH and the saturation states are still computed, but above it hydroxide and borate carry "
        "the alkalinity and no comparison against the exe or a measurement exists.",
        PHRangeWarning,
        stacklevel=stacklevel,
    )
    return outside


def resolve_constants(exe_k1k2: int = 10, exe_kso4: int = 1) -> ConstantSet:
    """Map the exe's option numbers onto PyCO2SYS, or refuse.

    Defaults are the exe's own defaults, which are also case03's selections: K1K2 = 10
    (Lueker et al. 2000) and KSO4 = 1 (Dickson bisulfate with Uppstrom borate).
    """
    if exe_k1k2 not in EXE_K1K2_OPTIONS:
        raise UnknownConstantOptionError(
            f"K1K2 option {exe_k1k2} is outside the exe's range of 1-14; known: "
            f"{sorted(EXE_K1K2_OPTIONS)}. (The manual's section 5.2.5 says ten options, "
            "but the dialog help text enumerates fourteen.)"
        )
    if exe_kso4 not in EXE_KSO4_OPTIONS:
        raise UnknownConstantOptionError(
            f"KSO4 option {exe_kso4} is outside the exe's range of 1-4; known: "
            f"{sorted(EXE_KSO4_OPTIONS)}. Each option selects a bisulfate constant "
            "together with a total-borate ratio."
        )
    k1k2 = EXE_K1K2_OPTIONS[exe_k1k2]
    kso4 = EXE_KSO4_OPTIONS[exe_kso4]
    return ConstantSet(
        exe_k1k2=exe_k1k2,
        exe_kso4=exe_kso4,
        pyco2sys_k_carbonic=exe_k1k2,
        pyco2sys_k_bisulfate=kso4.pyco2sys_k_bisulfate,
        pyco2sys_total_borate=kso4.pyco2sys_total_borate,
        k1k2_reference=k1k2.reference,
        bisulfate_reference=kso4.bisulfate_reference,
        borate_reference=kso4.borate_reference,
        native_ph_scale=k1k2.native_ph_scale,
        validity=k1k2.validity,
    )


def calcium_from_salinity(salinity: ArrayLike) -> NDArray[np.float64]:
    """Total calcium, mol/kg: `[Ca2+] = 0.01028 * S / 35` (manual §3.2).

    Note this is what the exe uses regardless of the ambient `Ca` column, which case06
    showed to be inert -- entering 5000 umol/kg against a seawater ~10 300 left the
    saturation states unchanged.
    """
    s = np.asarray(salinity, dtype=np.float64)
    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")
    return np.asarray(CALCIUM_AT_S35 * s / 35.0)


#: Millero et al. (2008): absolute salinity 35.16504 g/kg at practical salinity 35, so the mass of
#: dissolved salt per kg of solution is `S * 35.16504 / 35 / 1000`. Used for the per-kg-of-water
#: conversion; the 0.5 % between absolute and practical salinity is inside the 3.5 % it corrects.
ABSOLUTE_PER_PRACTICAL_SALINITY = 35.16504 / 35.0


def water_fraction(salinity: ArrayLike) -> NDArray[np.float64]:
    """Kilograms of water per kilogram of solution, `1 - S_A / 1000`.

    The bridge between the two concentration bases this package meets. PyCO2SYS and the exe report
    per kilogram of *solution*; a thermodynamic solubility product such as brucite's is defined on
    the *molal* scale, per kilogram of *water*. Dividing a per-kg-of-solution concentration by this
    fraction puts it on the molal scale; multiplying a molality by it brings it back. 0.969 at
    S 30.9, 0.965 at S 35, 1 in pure water.
    """
    s = np.asarray(salinity, dtype=np.float64)
    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")
    return np.asarray(1.0 - s * ABSOLUTE_PER_PRACTICAL_SALINITY / 1000.0)


def magnesium_from_salinity(salinity: ArrayLike) -> NDArray[np.float64]:
    """Total magnesium, mol per kg of *solution*: `[Mg2+] = 0.0528171 * S / 35`.

    The same conservative scaling as `calcium_from_salinity`, and for the same reason: the
    major ions track salinity, so a diluting plume carries them down proportionally. Used by
    `omega_brucite`; the exe has no equivalent.
    """
    s = np.asarray(salinity, dtype=np.float64)
    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")
    return np.asarray(MAGNESIUM_AT_S35 * s / 35.0)


def _log10_solubility(
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    a0: float,
    a1: float,
    b0: float,
    b1: float,
    b2: float,
    c1: float,
    c2: float,
) -> NDArray[np.float64]:
    """Mucci (1983) form, shared by both minerals.

    log10 Ksp = a0 - 0.077993 T + a1/T + 71.595 log10 T
                + (b0 + b1 T + b2/T) sqrt(S) + c1 S + c2 S^1.5
    """
    s = np.asarray(salinity, dtype=np.float64)
    t_kelvin = np.asarray(temperature, dtype=np.float64) + 273.15
    root_s = np.sqrt(s)
    return np.asarray(
        a0
        - 0.077993 * t_kelvin
        + a1 / t_kelvin
        + 71.595 * np.log10(t_kelvin)
        + (b0 + b1 * t_kelvin + b2 / t_kelvin) * root_s
        + c1 * s
        + c2 * s * root_s
    )


def solubility_calcite(salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.float64]:
    """`K_sp` for calcite, (mol/kg)^2 (Mucci 1983, via Millero 1995)."""
    return np.asarray(
        10.0
        ** _log10_solubility(
            salinity,
            temperature,
            a0=-171.9065,
            a1=2839.319,
            b0=-0.77712,
            b1=0.0028426,
            b2=178.34,
            c1=-0.07711,
            c2=0.0041249,
        )
    )


def solubility_aragonite(salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.float64]:
    """`K_sp` for aragonite, (mol/kg)^2 (Mucci 1983, via Millero 1995)."""
    return np.asarray(
        10.0
        ** _log10_solubility(
            salinity,
            temperature,
            a0=-171.945,
            a1=2903.293,
            b0=-0.068393,
            b1=0.0017276,
            b2=88.135,
            c1=-0.10018,
            c2=0.0059415,
        )
    )


# --------------------------------------------------------------------------- brucite

#: `log10 Ksp` for `Mg(OH)2 <-> Mg2+ + 2 OH-` at 25 C, **thermodynamic** -- in terms of
#: *activities*, not concentrations. Unlike the Mucci fits above, which are stoichiometric
#: constants measured in seawater and used with total concentrations, this one has to be
#: paired with an activity model. See `solubility_brucite`.
#:
#: ⭐⭐ **This value is now identified, and a measured alternative exists** (2026-08-24, from
#: ebb-general-modeling PR 158, which did the literature work this constant was waiting on).
#: -11.16 is exactly the wateq4f_PWN.dat conversion -- its H+ form `log_k` 16.84 plus twice
#: water's -13.998 -- which encodes the **Robie & Hemingway (1995)** Gibbs energy of formation
#: (dfG -833.5 kJ/mol -> log Ksp -11.15). So it was never arbitrary, but it is one lineage
#: among five, and the spread between them is *not* a disagreement about chemistry -- each
#: database encodes a different dfG(brucite), at 5.708 kJ/mol per log unit:
#:
#:     Harvie, Moller & Weare 1984   dfG -831.4 kJ/mol  ->  log Ksp -10.79
#:     Brown et al. 1996                  -831.9        ->           -10.87   (~pitzer.dat)
#:     Xiong 2008                         -832.3        ->           -10.94   <- measured
#:     Robie & Hemingway 1995             -833.5        ->           -11.15   (~this value)
#:     Koenigsberger et al. 1999          -836.5        ->           -11.68   (~llnl.dat)
#:
#: ⭐ **The measured value is Xiong (2008)**, Aquatic Geochemistry 14:223-238,
#: doi:10.1007/s10498-008-9034-3 -- solubility from both under- and supersaturation in
#: 0.010-4.4 m NaCl, recommending log Ks = 17.05 +/- 0.2 at 25 C for the H+ form, i.e.
#: **-10.95 +/- 0.2** in this OH- form. Altmaier et al. (2003), Geochim. Cosmochim. Acta
#: 67(19):3595-3601, independently give 17.1 +/- 0.2 -> -10.90. PR 158 validated -10.95
#: against five OLI titration surveys spanning I = 0.016-1.9 mol/kg (3/5 inside the onset
#: band; a -10.50 misread fails 0/5). The journal copies are paywalled, but Xiong (2008) is
#: publicly mirrored in the DOE WIPP records library
#: (https://wipp.energy.gov/library/CRA/CRA-2014/References/Others/Xiong_2008_Aquatic_Geochemistry.pdf);
#: the citations are recorded in references/README.md.
#:
#: ✅ **Adopted 2026-08-24, by operator decision (PLAN section 8.1).** The value below is
#: Xiong (2008)'s measured -10.95; it replaced the uncited -11.16 the same day the lineage
#: ladder identified what -11.16 was. The change lowered every Omega_brucite by 1.62x --
#: row 196 was re-pinned in the same commit -- and replaced an uncited spread with a cited
#: +/-0.2 band, which at 10^0.4 = 2.51x is coincidentally as wide as the old prose spread.
#: The once-open diligence item -- a verification read of the paper behind PR 158's relay --
#: was **waived by the operator (2026-09-01)**: the paper is cited directly above, an open
#: copy is linked, and the two independent confirmations were judged sufficient.
#: The superseded Robie & Hemingway value stays available the way every superseded choice
#: does: `solubility_brucite(..., log_ksp_25c=-11.16)`.
BRUCITE_LOG_KSP_25C = -10.95

#: Enthalpy of the brucite dissolution reaction, J/mol, for the van 't Hoff correction.
#: From standard formation enthalpies, so it is checkable rather than quoted:
#:
#:     Mg(OH)2(s) -> Mg2+ + 2 OH-
#:     dH = (-466.85) + 2(-229.99) - (-924.54) = -2.29 kJ/mol
#:
#: **Brucite dissolution is very nearly athermal**, and it is even more nearly athermal than
#: this note used to claim. Over the 25 C -> 10 C that matters here it moves `log Ksp` by
#: +0.021, which is a **5.02 %** change in the thermodynamic `Ksp` -- the figure this comment
#: carried until 2026-08-21.
#:
#: ⭐ **But `Omega` divides by `Ksp*`, not `Ksp`, and the temperature terms partially cancel.**
#: The Davies coefficients fall with temperature in the same direction, so the *conditional*
#: constant moves only **+0.71 %** over the same 15 degrees (measured at S = 32; see
#: `solubility_brucite` for the full budget). The old figure was right about the wrong quantity
#: and overstated the term that matters by a factor of seven. Temperature is not a minor term
#: here, it is a negligible one.
#:
#: ⚠️ An earlier revision of this file carried -111.3 kJ/mol here, a formation-scale number
#: rather than a reaction one. It is ~48x too large and put a **10x error** into `Ksp*` at
#: near-field temperatures. Kept as a note because the failure is silent: the value is
#: plausible-looking, the units are right, and nothing downstream complains.
#:
#: ✅ **Independently confirmed 2026-08-24** by ebb-general-modeling PR 158, which reached
#: "nearly athermal, slightly negative" down four separate lines: wateq4f/CODATA -0.40
#: kcal/mol (-1.67 kJ), Gurvich et al. (1994) calorimetry ~-0.6 kcal/mol (-2.5 kJ) -- this
#: value sits between them -- and it caught pitzer.dat shipping **+4.85 kcal/mol, the wrong
#: sign** for a textbook retrograde mineral: the same class of silent constant error as the
#: -111.3 above, in a curated public database. ⚠️ One honest caveat from the same source:
#: OLI's MSE model implies a much steeper fall (its own K drops 2.96x from 5 to 45 C,
#: van 't Hoff ~-4.8 kcal/mol) -- not portable to this framework (mole-fraction basis), but
#: if its *magnitude* were right, Omega at 10 C would sit ~1.5x lower than the athermal
#: treatment gives. Elevated-temperature brucite data was still "lacking" as of Kirkes &
#: Xiong (2017, SAND2017-3039C, archived in references/), so this stays a recorded
#: uncertainty rather than a resolvable one.
BRUCITE_DISSOLUTION_ENTHALPY = -2.29e3

_GAS_CONSTANT = 8.314462618
_REFERENCE_TEMPERATURE_K = 298.15


def ionic_strength_from_salinity(salinity: ArrayLike) -> NDArray[np.float64]:
    """Ionic strength, mol/kg: `I = 19.924 S / (1000 - 1.005 S)`.

    The standard seawater relation; gives 0.7227 mol/kg at S = 35.
    """
    s = np.asarray(salinity, dtype=np.float64)
    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")
    return np.asarray(19.924 * s / (1000.0 - 1.005 * s))


def davies_activity_coefficient(
    charge: int, salinity: ArrayLike, temperature: ArrayLike
) -> NDArray[np.float64]:
    """Single-ion activity coefficient by the Davies equation.

        log10 gamma = -A z^2 ( sqrt(I)/(1 + sqrt(I)) - 0.3 I )

    with `A = 0.4883 + 8.074e-4 t` (t in Celsius), the usual approximation for water.

    ⚠️ **Davies is being used past its stated range.** It is normally quoted as reliable to
    `I ~ 0.5 mol/kg`; seawater is 0.72. It is used here because it is explicit and checkable,
    which was the point of choosing an activity model over an empirical fit -- but a Pitzer
    treatment is the rigorous version, and the difference at seawater strength is not
    negligible. At S = 35, T = 10 C this gives gamma(Mg2+) ~ 0.33 and gamma(OH-) ~ 0.76,
    against literature ranges of roughly 0.23-0.36 and 0.65-0.76 -- consistent, at the
    optimistic end.
    """
    ionic_strength = ionic_strength_from_salinity(salinity)
    t = np.asarray(temperature, dtype=np.float64)
    a = 0.4883 + 8.074e-4 * t
    root = np.sqrt(ionic_strength)
    exponent = -a * charge * charge * (root / (1.0 + root) - 0.3 * ionic_strength)
    return np.asarray(10.0**exponent)


def solubility_brucite(
    salinity: ArrayLike,
    temperature: ArrayLike,
    *,
    log_ksp_25c: float = BRUCITE_LOG_KSP_25C,
    enthalpy: float = BRUCITE_DISSOLUTION_ENTHALPY,
) -> NDArray[np.float64]:
    """Conditional `Ksp*` for brucite, `mol^3/kg^3`, for use with **total** concentrations.

    Built the explicit way rather than fitted: take the thermodynamic `Ksp` in activities,
    correct it to temperature by van 't Hoff, and divide out the activity coefficients so the
    result can be used with concentrations, exactly as `solubility_aragonite` is:

        Ksp* = Ksp(T) / ( gamma(Mg2+) gamma(OH-)^2 )

    so that `Omega = [Mg2+][OH-]^2 / Ksp*` is the activity product over `Ksp` as it should be.
    That keeps `omega_brucite` the same shape as `omega_calcite` and `omega_aragonite`, and
    puts every assumption in one place.

    ⚠️ **Ion pairing is not modelled, and this is the leading structural limitation.** A
    tenth of seawater magnesium is complexed, mostly as MgSO4, and hydroxide pairs too
    (MgOH+, CaOH+) increasingly as pH rises -- which is exactly the regime this is for. Using
    *total* concentrations therefore **overestimates** the free-ion activity product, so
    `Omega` here is an **upper bound**. Mucci's aragonite fit dodges the whole problem by
    being measured in seawater with the pairing already inside it; the price of the explicit
    route is that the pairing has to be added separately to close the gap.

    ⚠️⚠️ **The error budget, measured 2026-08-21 (PLAN.md Phase 8.1). It was stated
    qualitatively before, and two of its four terms were wrong** -- one by a factor of seven and
    one by an order of magnitude, in opposite directions. At S = 32, T = 11 C:

        term                                          multiplier on Omega   was stated as
        log Ksp band (Xiong 2008, +/-0.2; the old
        -10.9..-11.3 spread was the same width)              2.51x          "~2.5x"      ok
        activity coefficients, gamma at quoted bounds        2.14x          "10-20 %"    LOW
        temperature, 25 -> 10 C, on Ksp*                     1.007x         "5 %"        HIGH
        both dominant terms together, worst case             5.37x          not stated

    ⭐⭐ **The activity coefficients are co-dominant with `Ksp`, not a minor term.** Against the
    literature bounds this module's own `davies_activity_coefficient` docstring quotes --
    gamma(Mg2+) 0.23-0.36, gamma(OH-) 0.65-0.76 -- `Omega` spans 0.543 to 1.161, a 2.14x range
    against the `Ksp` spread's 2.51x. Davies sits near the **optimistic** end of that, so today's
    `Omega` is high on this count as well as on ion pairing.

    ⭐ **Temperature is negligible, and for a reason worth keeping.** The thermodynamic `Ksp`
    moves 5.02 % over 25 -> 10 C, but the Davies coefficients move the same way, so the
    *conditional* `Ksp*` that `Omega` actually divides by moves **0.71 %**. The old "5 %" was
    right about `Ksp` and wrong about the quantity that matters.

    ⚠️ **This reorders the work.** PLAN §8.1 had the `Ksp` selection first, ion pairing second and
    Davies last. Measured, ion pairing and the activity model are **the same problem** -- both are
    about getting from total concentrations to free-ion activities -- and together they rival the
    `Ksp` spread. A Pitzer treatment addresses both at once, which makes it one change against two
    of the three dominant terms rather than the last item on a list.

    ⭐⭐ **Measured against a Pitzer treatment, 2026-09-09** (`chem/pitzer`, PHREEQC with
    `pitzer.dat`, the same `Ksp`; ledger rows 287-289): this function's `Omega` sits **7-8x above**
    the Pitzer value at the site (S 30.9, T 11.2), nearly flat from pH 7.7 to 12. Term by term:
    `[OH-]^2` 3.1x -- PyCO2SYS's hydroxide is a *total* of which ~45 % is the MgOH+ pair at pH
    11-12, and the product wants the free ion; `gamma(OH-)^2` 1.9x (Pitzer 0.54 against Davies'
    0.75 here); `gamma(Mg2+)` 1.2x; Mg pairing 1.0-1.2x. So the pairing that matters is on the
    hydroxide, not the magnesium this docstring foregrounds, and the activity error is nearly all
    `gamma(OH-)`. ✅ **And one term pointed the other way, until 2026-09-10**: `omega_brucite`
    used concentrations per kg of *solution* against this `Ksp`, which is defined on the *molal*
    scale -- three concentration factors, so `Omega` read `(1 - S_A/1000)^3` = 0.91 at S 30.9
    *below* the same physics on one basis. Corrected (operator, 2026-09-10): `omega_brucite` now
    divides each concentration by `water_fraction(S)` before forming the product, every Davies
    `Omega` rose ~10 % at seawater salinity (row 196's peak 131.4 -> 146.3) and the threshold pH
    fell 0.02 (9.43 -> 9.41 at S 32 / 10 C); the Davies/Pitzer ratio is now the 8.2-8.7x the other
    terms alone give (row 289: 7.9 -> 8.7 at TA 20 000). The two columns are kept side by side
    permanently, this one as the bound.

    **Treat the absolute value as indicative and the trends as sound** -- the salinity and pH
    dependences rest on much firmer ground than the constant does. The 5.37x is a *bound* built
    from independent worst cases, not a confidence interval; the terms are not independent and the
    true spread is narrower. It is quoted because a bound is what the dose study can honestly
    state. ✅ The `Ksp` pick was settled 2026-08-24 -- Xiong (2008)'s measured -10.95, see
    `BRUCITE_LOG_KSP_25C` -- which turns the band's meaning from "databases disagree" into
    "the measurement's stated uncertainty" without changing its width.
    """
    t_kelvin = np.asarray(temperature, dtype=np.float64) + 273.15
    if np.any(t_kelvin <= 0):
        raise ValueError("temperature must be above absolute zero")
    # van 't Hoff: ln K(T) = ln K(T0) - (dH/R)(1/T - 1/T0)
    shift = -(enthalpy / _GAS_CONSTANT) * (1.0 / t_kelvin - 1.0 / _REFERENCE_TEMPERATURE_K)
    ksp = 10.0**log_ksp_25c * np.exp(shift)
    gamma_magnesium = davies_activity_coefficient(2, salinity, temperature)
    gamma_hydroxide = davies_activity_coefficient(1, salinity, temperature)
    return np.asarray(ksp / (gamma_magnesium * gamma_hydroxide**2))
