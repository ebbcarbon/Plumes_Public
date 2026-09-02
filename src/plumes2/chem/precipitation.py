"""Calcite and aragonite precipitation rates (Zhong & Mucci 1989).

The GUI presents the law as

    Rate = K * (Omega - 1) ** N

with per-mineral `logK` and `N` and an explicit salinity band per entry. The dialog, as
transcribed by the user (2026-08-12)::

    calcite     0 < S < 44    logK = -1.06e-1   N = 2.87
    aragonite   0 < S < 35    logK =  1.53      N = 2.33
    aragonite  35 < S < 44    logK =  1.11      N = 2.26

So aragonite is defined over two discrete bands, and both minerals stop at S = 44.

Two things are established from the reference cases rather than the dialog:

**`K` is `exp(logK)`, not `10 ** logK`.** The exe's own `R_cal` column implies
`logK = -0.10600` over 153 rows across case03, case04 and case06 (range -0.1065 to
-0.1055) under `exp`, recovering the dialog's -0.106 exactly. Under `10 **` the dialog
would have to read -0.04604, which it does not. An odd choice for a field labelled *log*K,
and Zhong & Mucci (1989) tabulate log10, but the data is unambiguous. The same test on
aragonite's high band recovers `logK = 1.110` and `N = 2.260` from an unconstrained
two-parameter fit (case06 and case07), confirming both the convention and the values.

Note this also settles a sign: the calcite `logK` is **negative**. It was transcribed once
as `-1.06e-1` and once as `1.06e-01`, a 24 % difference in rate, and the data picks the
negative one.

**The low band's upper edge is 25, not the dialog's 35** -- corrected 2026-08-19, and the
correction reverses a finding rather than refining one. Ten runs had shown `R_arg` identically
zero wherever plume salinity fell below 35, which read as "the exe never applies the low band".
`case13` is the archive's only trace that gets *well* below it -- a freshwater discharge into a
uniform 32 psu ambient -- and it applies the band plainly: 15 rows of non-zero `R_arg` that the
dialog's own `logK = 1.53, N = 2.33` reproduce to **1.1e-4** relative, then exactly zero from the
next row on. Reconstructed salinity brackets the switch to **(24.613, 25.305]**, and the high
edge to (34.905, 35.304] on case07.

⚠️ **So the exe zeroes aragonite in `25 <= S <= 35` and nowhere else.** Every earlier case sat
inside that dead zone, which is why it looked like a floor at 35. It is not saturation state
doing it: `case03` reaches Omega_A 22.9 at S 34 with a zero rate, while `case13` at Omega_A 22.4
and S 3 gives 5823.

⭐ Both edges land on integers, and Zhong & Mucci (1989) ran their experiments at S = 5, 25, 35
and 44 -- so the dead zone is most likely the salinity gap between two of their aragonite series,
transcribed into the dialog as one band that reads wider than the exe evaluates. That is a
hypothesis about *why*; the bracket above is the measurement.

**Undersaturated water gives NaN in the exe.** `(Omega - 1) ** 2.87` for `Omega < 1` is a
fractional power of a negative number; the exe does not guard it, and a single NaN row
poisons the rest of the run (`case09`). Physically the rate is zero -- nothing precipitates
from undersaturated water, it dissolves -- so zero is the default here. This matters most
for exactly the acidified-water cases the model is useful for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "ARAGONITE_HIGH_SALINITY",
    "ARAGONITE_LOW_SALINITY",
    "ARAGONITE_LOW_SALINITY_AS_DIALOGUED",
    "CALCITE",
    "Mineral",
    "RateLaw",
    "aragonite_laws",
    "precipitation_rate",
]


class Mineral:
    """Mineral name constants, avoiding a bare string in call sites."""

    CALCITE = "calcite"
    ARAGONITE = "aragonite"


@dataclass(frozen=True, slots=True)
class RateLaw:
    """One row of the precipitation dialog."""

    mineral: str
    log_k: float
    exponent: float
    salinity_min: float
    salinity_max: float

    @property
    def rate_constant(self) -> float:
        """`K = exp(logK)` -- see the module docstring; not `10 ** logK`."""
        return float(np.exp(self.log_k))

    def applies(self, salinity: ArrayLike) -> NDArray[np.bool_]:
        s = np.asarray(salinity, dtype=np.float64)
        return np.asarray((s > self.salinity_min) & (s < self.salinity_max))


#: Defaults as the GUI presents them.
CALCITE = RateLaw(Mineral.CALCITE, log_k=-0.106, exponent=2.87, salinity_min=0.0, salinity_max=44.0)
ARAGONITE_HIGH_SALINITY = RateLaw(
    Mineral.ARAGONITE, log_k=1.11, exponent=2.26, salinity_min=35.0, salinity_max=44.0
)
#: The low band. ⚠️ The dialog writes it `0 < S < 35`; the exe stops evaluating it at **25**,
#: measured on case13 and bracketed to (24.613, 25.305]. See the module docstring.
ARAGONITE_LOW_SALINITY = RateLaw(
    Mineral.ARAGONITE,
    log_k=1.53,
    exponent=2.33,
    salinity_min=0.0,
    salinity_max=25.0,
)

#: The dialog's own transcription of the low band, for anyone who wants what the GUI says
#: rather than what it does. Using it makes `25 < S < 35` precipitate where the exe reports zero.
ARAGONITE_LOW_SALINITY_AS_DIALOGUED = RateLaw(
    Mineral.ARAGONITE, log_k=1.53, exponent=2.33, salinity_min=0.0, salinity_max=35.0
)


def precipitation_rate(
    omega: ArrayLike,
    salinity: ArrayLike,
    laws: RateLaw | tuple[RateLaw, ...],
    *,
    reproduce_undersaturated_nan: bool = False,
) -> NDArray[np.float64]:
    """`Rate = K (Omega - 1) ** N`, piecewise in salinity.

    `laws` may be a single law or several covering disjoint salinity bands; the first
    matching band wins. Outside every band the rate is zero.

    Set `reproduce_undersaturated_nan` to emit the exe's NaN for `Omega < 1` instead of zero.

    ⚠️ There used to be a second flag here, `reproduce_zero_outside_bands`, which suppressed the
    low aragonite band entirely on the belief that the exe never evaluated it. case13 shows it
    does. The exe's behaviour is now carried by the band edges themselves -- see
    `ARAGONITE_LOW_SALINITY` -- so choosing it is a choice of law, not a flag on the arithmetic.
    """
    laws_tuple = (laws,) if isinstance(laws, RateLaw) else tuple(laws)
    if not laws_tuple:
        raise ValueError("at least one rate law is required")

    omega_arr = np.asarray(omega, dtype=np.float64)
    salinity_arr = np.asarray(salinity, dtype=np.float64)
    omega_arr, salinity_arr = np.broadcast_arrays(omega_arr, salinity_arr)
    rate = np.zeros(omega_arr.shape, dtype=np.float64)

    supersaturated = omega_arr > 1.0
    assigned = np.zeros(omega_arr.shape, dtype=bool)
    for law in laws_tuple:
        band = law.applies(salinity_arr) & ~assigned
        assigned |= band
        active = band & supersaturated
        if np.any(active):
            rate[active] = law.rate_constant * (omega_arr[active] - 1.0) ** law.exponent

    if reproduce_undersaturated_nan:
        # The exe evaluates the power unguarded, so anything not supersaturated within a
        # band it did evaluate comes out NaN. Omega exactly 1 gives 0 either way.
        rate[assigned & (omega_arr < 1.0)] = np.nan
    return rate


def aragonite_laws(
    *,
    reproduce_band_gap: bool = False,
    low: RateLaw | None = None,
    high: RateLaw = ARAGONITE_HIGH_SALINITY,
) -> tuple[RateLaw, ...]:
    """Both aragonite bands, high salinity first so `35 < S < 44` wins at the boundary.

    ⚠️ `reproduce_band_gap` selects the low band **the exe evaluates**, `0 < S < 25`, which
    leaves `25 <= S <= 35` reporting exactly zero -- ordinary seawater, and the reason ten
    archived runs showed no aragonite at all. The default is the band **the dialog declares**,
    `0 < S < 35`, which is what a reader of the GUI would expect and what precipitates in
    seawater. Both use the same coefficients; only the edge moves.

    Pass `low` to override either.
    """
    if low is None:
        low = ARAGONITE_LOW_SALINITY if reproduce_band_gap else ARAGONITE_LOW_SALINITY_AS_DIALOGUED
    return (high, low)
