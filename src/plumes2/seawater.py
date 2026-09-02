"""Seawater density — EOS-80 by default, and **Knudsen (1901), which is the exe's**.

Two equations of state live here, and which one a caller wants depends on the question:

* **EOS-80 / UNESCO (1983)** — Millero & Poisson (1981) for the one-atmosphere density and
  Millero et al. (1980) for the secant bulk modulus, checked against the canonical UNESCO
  check values to 1e-5. The modern standard, and the default per PLAN §2's "correct by
  default, reproduce on request".
* **Knudsen (1901) sigma-t** — `knudsen_sigma_t`, which reproduces the exe's `P-Den` column
  to **one rounding digit over 51 670 archived rows with no fitted parameter**. Select it
  through `EquationOfState.KNUDSEN` when comparing a trajectory against a trace.

⭐⭐⭐ **The long-standing EOS discrepancy is closed (2026-08-20).** This module used to open by
recording, on PORTING_NOTES §3's authority, that the exe used "the Fofonoff (1985) sigma-t
equation of state", and then spend four paragraphs on an unexplained 0.02-0.07 kg/m3 residual.
Both are now superseded. The exe's density is Knudsen (1901) — the formulation tabulated by
*U.S. Navy Hydrographic Office (1952), Tables for seawater density, H.O. Pub. No. 615*, which
`references/README.md` traces to it by citation through OUTPLM and Teeter & Baumgartner (1979).
Neither manual in the family prints a polynomial because the source of the numbers is a table.

⚠️ **The offset is a line in salinity, not a constant**, and row 255 said so first: +0.061 at
S = 10, +0.028 at S = 31, +0.021 at S = 36, with essentially no temperature dependence across
2.7-11 C. Row 108's "-0.0275" is scoped in its own text to the seawater range and stays true
there; what the identification adds is *why* — two polynomials agreeing near seawater and
separating away from it, which is what row 255 described from the data alone.

⚠️⚠️ **And the identification refutes what the EOS was blamed for.** Ledger 148 reads the
late-trajectory drift *as* this discrepancy: buoyancy is `rho_ambient - rho_plume`, that
difference collapses near the trapping level, the offset is therefore amplified ~15x there, and
"that ~15x amplification matches the 0.31 % -> 5.16 % error growth". The amplification argument
is sound and the correlation is real, but it was never testable until the exe's own EOS was in
hand. It is now, and switching to it **does not fix the drift**:

| run | window | EOS-80 | Knudsen |
|---|---|---|---|
| test23 | jet (first quarter) | 0.30 % | 0.30 % |
| test23 | **late (last quarter)** | **5.07 %** | **5.01 %** |
| test27 | late | 1.64 % | 1.69 % |
| test29 | late | 1.50 % | 1.63 % |
| test30 | late | 1.37 % | 1.50 % |

Removing the density difference entirely -- matching the exe to one rounding digit -- moves the
late window by 0.06 pp on the run the claim was measured on, and makes three of the four
cross-flow runs slightly *worse*. So the late drift has another cause and row 148's attribution
is retired: a mechanism that matched a ratio, refuted the moment it could be switched off.
Selecting `KNUDSEN` is still the right thing for a parity comparison -- it removes a known
difference rather than accommodating it -- but it buys no accuracy, and nobody should expect it
to.

Vectorised over NumPy arrays throughout, so a whole depth profile or a whole plume
trajectory converts in one call.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "EquationOfState",
    "densimetric_froude_number",
    "density",
    "density_anomaly",
    "density_of",
    "depth_from_pressure",
    "knudsen_density",
    "knudsen_sigma_t",
    "pressure_from_depth",
    "reduced_gravity",
    "secant_bulk_modulus",
    "sigma_t",
]

#: Standard gravity, m/s^2.
GRAVITY = 9.80665

# --- One-atmosphere density: Millero & Poisson (1981) -----------------------------------
_RHO_W = (999.842594, 6.793952e-2, -9.095290e-3, 1.001685e-4, -1.120083e-6, 6.536332e-9)
_A = (8.24493e-1, -4.0899e-3, 7.6438e-5, -8.2467e-7, 5.3875e-9)
_B = (-5.72466e-3, 1.0227e-4, -1.6546e-6)
_C = 4.8314e-4

# --- Secant bulk modulus: Millero et al. (1980) -----------------------------------------
_KW = (19652.21, 148.4206, -2.327105, 1.360477e-2, -5.155288e-5)
_AW = (3.239908, 1.43713e-3, 1.16092e-4, -5.77905e-7)
_BW = (8.50935e-5, -6.12293e-6, 5.2787e-8)
_K0_S = (54.6746, -0.603459, 1.09987e-2, -6.1670e-5)
_K0_S32 = (7.944e-2, 1.6483e-2, -5.3009e-4)
_A_S = (2.2838e-3, -1.0981e-5, -1.6078e-6)
_A_S32 = 1.91075e-4
_B_S = (-9.9348e-7, 2.0816e-8, 9.1697e-10)


def _poly(coefficients: tuple[float, ...], x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Horner evaluation, ascending powers."""
    result = np.zeros_like(x)
    for coefficient in reversed(coefficients):
        result = result * x + coefficient
    return result


def density(
    salinity: ArrayLike, temperature: ArrayLike, pressure_dbar: ArrayLike = 0.0
) -> NDArray[np.float64]:
    """Seawater density in kg/m3.

    Args:
        salinity: practical salinity, psu.
        temperature: temperature, degrees Celsius (IPTS-68, as EOS-80 expects).
        pressure_dbar: gauge pressure in decibars; 0 gives the one-atmosphere density,
            whose anomaly is sigma-t.
    """
    s = np.asarray(salinity, dtype=np.float64)
    t = np.asarray(temperature, dtype=np.float64)
    p = np.asarray(pressure_dbar, dtype=np.float64)

    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")

    root_s = np.sqrt(s)
    rho_zero = _poly(_RHO_W, t) + _poly(_A, t) * s + _poly(_B, t) * s * root_s + _C * s * s

    # Zero pressure is the common case and short-circuits the bulk modulus entirely.
    if np.all(p == 0):
        return np.asarray(rho_zero, dtype=np.float64)

    bars = p / 10.0
    k = secant_bulk_modulus(s, t, p)
    return np.asarray(rho_zero / (1.0 - bars / k), dtype=np.float64)


def secant_bulk_modulus(
    salinity: ArrayLike, temperature: ArrayLike, pressure_dbar: ArrayLike
) -> NDArray[np.float64]:
    """Secant bulk modulus K(S, T, P) in bars, per Millero et al. (1980)."""
    s = np.asarray(salinity, dtype=np.float64)
    t = np.asarray(temperature, dtype=np.float64)
    bars = np.asarray(pressure_dbar, dtype=np.float64) / 10.0
    root_s = np.sqrt(s)

    k_zero = _poly(_KW, t) + _poly(_K0_S, t) * s + _poly(_K0_S32, t) * s * root_s
    a = _poly(_AW, t) + _poly(_A_S, t) * s + _A_S32 * s * root_s
    b = _poly(_BW, t) + _poly(_B_S, t) * s
    return np.asarray(k_zero + a * bars + b * bars * bars, dtype=np.float64)


def sigma_t(salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.float64]:
    """Sigma-t: one-atmosphere density anomaly, kg/m3.

    This is what the exe's `P-Den` column reports — confirmed against case01, where
    including the pressure term would shift the values by more than the printed precision.
    """
    return density(salinity, temperature, 0.0) - 1000.0


def density_anomaly(
    salinity: ArrayLike, temperature: ArrayLike, pressure_dbar: ArrayLike = 0.0
) -> NDArray[np.float64]:
    """Density minus 1000 kg/m3, at the given pressure."""
    return density(salinity, temperature, pressure_dbar) - 1000.0


# --- Knudsen (1901): the equation of state the exe actually uses -------------------------


def knudsen_sigma_t(salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.float64]:
    r"""Knudsen (1901) sigma-t, kg/m3 -- **the exe's own equation of state**.

    ⭐⭐⭐ **Identified 2026-08-20, and it closes the oldest open discrepancy in the port.**
    116 archived traces print `P-Sal`, `P-Temp` and `P-Den` on the same row, so the exe's EOS is
    directly invertible with no reconstruction from dilution. Scored against all **51 670** such
    rows, over S 0-45 psu and T 2.73-11.01 C, with **no fitted parameter**:

    | candidate | free parameters | mean residual | rms | worst |
    |---|---|---|---|---|
    | **Knudsen (1901)** | **0** | **-0.00001** | **0.00037** | **0.00098** |
    | EOS-80 at p = 0 | 0 | +0.02882 | 0.02942 | 0.06292 |
    | Eckart (1958) | 0 | +0.12205 | 0.12331 | 0.20979 |
    | EOS-80 + cubic in S, quadratic in T | 7 | 0 | 0.00055 | 0.01679 |

    `P-Den` is printed to three decimals, so a worst-case residual of **0.00098 kg/m3 is one
    rounding digit**: the agreement is exact to everything the trace can show. ⭐ And fitting a
    constant, a line in S, or a quadratic *on top of* Knudsen leaves the rms at 0.00037 unchanged
    -- there is nothing left to absorb, which is what distinguishes an identification from a fit.

    **It confirms the provenance chain end to end.** `references/README.md` traces the exe's
    density from UM3 back through Teeter & Baumgartner (1979) and OUTPLM to *U.S. Navy
    Hydrographic Office (1952), Tables for seawater density, H.O. Pub. No. 615* -- which
    tabulates exactly these Knudsen/Ekman results. Two of those links were never printed
    anywhere we hold; this measurement closes the gap from the other end.

    ⚠️⚠️ **It also retracts the "+0.0275 kg/m3 constant offset".** That figure was measured on
    case16 and test23, both of which live entirely inside 31-35 psu. Pooled over the whole
    archive the EOS-80 residual is a **function of salinity**, running +0.061 at S = 10 down to
    +0.021 at S = 36 -- so what looked like a constant was one salinity band's value of a line.
    The direction always held, and Millero's history of the EOS says why: Cox et al. (1970) found
    Knudsen's densities "too high by 0.013 kg m-3" at S = 35, and Millero & Lepple (1973)
    0.007 +/- 0.003 lower still.

    ⚠️ **Pressure-independent by construction**, which is not a limitation of this port but of
    the model: the 3rd edition says the EOS is "independent of pressure, limiting UM to shallow
    water". There is no pressure argument here, and evaluating the exe's density at depth is
    therefore not a thing anyone can do.

    The formula is the classical one, as printed in Sverdrup, Johnson & Fleming (1942) and
    Fofonoff (1962):

    .. math::
        \sigma_0 &= -0.093 + 0.8149 S - 0.000482 S^2 + 0.0000068 S^3 \\
        \Sigma_t &= -\frac{(T - 3.98)^2 (T + 283)}{503.570 (T + 67.26)} \\
        A_t &= T (4.7867 - 0.098185 T + 0.0010843 T^2) \times 10^{-3} \\
        B_t &= T (18.030 - 0.8164 T + 0.01667 T^2) \times 10^{-6} \\
        \sigma_t &= \Sigma_t + (\sigma_0 + 0.1324)
                    [1 - A_t + B_t (\sigma_0 - 0.1324)]

    Two internal checks the tests pin, because a transcribed coefficient is exactly the kind of
    error that produces plausible numbers: `sigma_0` at S = 35 is **28.1296** against the
    tabulated 28.13, and `sigma_t == sigma_0` at T = 0 identically, which the algebra requires
    since `A_t` and `B_t` both vanish there.

    Args:
        salinity: practical salinity, psu. Knudsen's own variable was chlorinity; the archive's
            agreement is against the salinity the exe prints, so that is what this takes.
        temperature: temperature, degrees Celsius.
    """
    s = np.asarray(salinity, dtype=np.float64)
    t = np.asarray(temperature, dtype=np.float64)
    if np.any(s < 0):
        raise ValueError("salinity must be non-negative")
    sigma_zero = -0.093 + 0.8149 * s - 0.000482 * s**2 + 0.0000068 * s**3
    pure = -((t - 3.98) ** 2) * (t + 283.0) / (503.570 * (t + 67.26))
    a_t = t * (4.7867 - 0.098185 * t + 0.0010843 * t**2) * 1e-3
    b_t = t * (18.030 - 0.8164 * t + 0.01667 * t**2) * 1e-6
    anomaly = pure + (sigma_zero + 0.1324) * (1.0 - a_t + b_t * (sigma_zero - 0.1324))
    return np.asarray(anomaly, dtype=np.float64)


def knudsen_density(salinity: ArrayLike, temperature: ArrayLike) -> NDArray[np.float64]:
    """Knudsen (1901) density in kg/m3 -- `1000 + knudsen_sigma_t`. See that function."""
    return 1000.0 + knudsen_sigma_t(salinity, temperature)


class EquationOfState(StrEnum):
    """Which density formula to use. **`EOS80` is the default, deliberately.**

    ⚠️ The two answer different questions, and neither is "better" without one being named:

    * `EOS80` is the modern standard, validated here against the eight UNESCO check values to
      1e-5. It is what the port's own science should rest on, and it is what §2's "correct by
      default, reproduce on request" rule selects.
    * `KNUDSEN` is what **the exe** computes, to one rounding digit over 51 670 archived rows.
      Choose it to compare trajectories against a trace without the EOS difference contaminating
      the comparison -- which matters most exactly where it is largest, since buoyancy depends on
      `rho_ambient - rho_plume` and that difference collapses near the trapping level.
    """

    EOS80 = "eos80"
    KNUDSEN = "knudsen"


def density_of(
    salinity: ArrayLike,
    temperature: ArrayLike,
    pressure_dbar: ArrayLike = 0.0,
    *,
    equation_of_state: EquationOfState = EquationOfState.EOS80,
) -> NDArray[np.float64]:
    """Density in kg/m3 under the selected equation of state.

    ⚠️ `pressure_dbar` is **ignored** for `KNUDSEN`, which has no pressure term at all rather
    than one this port declines to evaluate. Silently ignoring an argument is normally wrong, so
    the alternative was considered and rejected: raising would make every caller special-case the
    selector, and the archive is a 2 m outfall where the term is worth ~0.01 kg/m3. The docstring
    is the contract, and `knudsen_sigma_t` states the limitation the 3rd edition states.
    """
    if equation_of_state is EquationOfState.KNUDSEN:
        return knudsen_density(salinity, temperature)
    return density(salinity, temperature, pressure_dbar)


def depth_from_pressure(
    pressure_dbar: ArrayLike, latitude_deg: float = 45.0
) -> NDArray[np.float64]:
    """Depth in metres for a gauge pressure in decibars (UNESCO 1983).

    Included for completeness; it matters little here, since the exe reports sigma-t and
    every reference case is shallower than 20 m.
    """
    p = np.asarray(pressure_dbar, dtype=np.float64)
    sin_phi = np.sin(np.radians(latitude_deg)) ** 2
    gravity = 9.780318 * (1.0 + (5.2788e-3 + 2.36e-5 * sin_phi) * sin_phi)
    numerator = (((-1.82e-15 * p + 2.279e-10) * p - 2.2512e-5) * p + 9.72659) * p
    return np.asarray(numerator / (gravity + 1.092e-6 * p), dtype=np.float64)


def pressure_from_depth(depth_m: ArrayLike, latitude_deg: float = 45.0) -> NDArray[np.float64]:
    """Gauge pressure in decibars for a depth in metres.

    Inverts :func:`depth_from_pressure` by Newton iteration, which converges in two or
    three steps because the relation is very nearly linear.
    """
    z = np.asarray(depth_m, dtype=np.float64)
    pressure = z * 1.01  # within ~0.3 % everywhere, so a few steps suffice
    for _ in range(4):
        residual = depth_from_pressure(pressure, latitude_deg) - z
        slope = (
            depth_from_pressure(pressure + 1.0, latitude_deg)
            - depth_from_pressure(pressure - 1.0, latitude_deg)
        ) / 2.0
        pressure = pressure - residual / slope
    return np.asarray(pressure, dtype=np.float64)


def reduced_gravity(plume_density: ArrayLike, ambient_density: ArrayLike) -> NDArray[np.float64]:
    """Buoyant acceleration g' = g (rho_ambient - rho_plume) / rho_ambient, m/s2.

    Positive when the plume is lighter than its surroundings and therefore rises. The
    sign convention matters for the near-field solver: case07's 45 psu effluent starts at
    1034 kg/m3 against ~1024 ambient, so g' is negative and the plume only rises because
    of its initial momentum.

    ⚠️ **This is the ambient-referenced form, and the solver deliberately does not use it.**
    `nearfield/solver.py` divides by the *plume* density instead, because its buoyancy term is a
    force on the plume's own mass: `m (rho_a - rho_p)/rho_p g`. The two differ by `rho_p/rho_a`,
    which is only 0.3 % for seawater but is a systematic 0.3 %, not noise. This function exists for
    reporting a Froude or Richardson number, where the ambient reference is conventional -- reach
    for it there, and never as a shortcut into the momentum equation.
    """
    plume = np.asarray(plume_density, dtype=np.float64)
    ambient = np.asarray(ambient_density, dtype=np.float64)
    return np.asarray(GRAVITY * (ambient - plume) / ambient, dtype=np.float64)


def densimetric_froude_number(
    exit_velocity: ArrayLike,
    port_diameter: ArrayLike,
    plume_density: ArrayLike,
    ambient_density: ArrayLike,
) -> NDArray[np.float64]:
    """The discharge Froude number `F = U / sqrt(|g'| D)`, dimensionless. Manual §5.2.2.

    The ratio of the port's momentum to its buoyancy. Above 1 the discharge is jetting and the
    near-field model applies; below 1 buoyancy dominates at the port itself, the plume is not a
    jet, and §5.2.2 treats that as a design problem rather than a modelling regime.

    ⚠️ **The magnitude of `g'`, not its signed value.** The manual writes `s - 1` with `s` the
    density ratio, which is real only for a *buoyant* discharge. Half of this archive is negatively
    buoyant -- case07's 45 psu effluent is 10 kg/m3 denser than its ambient -- and the literal form
    puts a negative number under the root. A dense discharge is no less a jet for sinking, so the
    magnitude is what the ratio needs.

    Uses `reduced_gravity`, i.e. the **ambient**-referenced `g'`, which is the conventional choice
    for a Froude number and the reason that function is exported at all -- see its docstring for
    why the solver deliberately uses a different reference internally.

    ⚠️ Returns infinity for a neutrally buoyant discharge, which is correct rather than a failure:
    with no buoyancy to overcome, the discharge is pure momentum at every velocity.
    """
    reduced = np.abs(reduced_gravity(plume_density, ambient_density))
    diameter = np.asarray(port_diameter, dtype=np.float64)
    if np.any(diameter <= 0.0):
        raise ValueError("port diameter must be positive to form a Froude number")
    scale = np.sqrt(reduced * diameter)
    with np.errstate(divide="ignore", invalid="ignore"):
        froude = np.asarray(exit_velocity, dtype=np.float64) / scale
    return np.asarray(np.where(scale > 0.0, froude, np.inf), dtype=np.float64)
