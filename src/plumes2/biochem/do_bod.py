"""Dissolved oxygen: the near field measured, the far-field sag taken on trust.

The manual gives eight equations (§4.2, after US EPA 1994) and the 3rd edition gives the first of
them as its own eq 10. Read literally, eq 23 is algebraic:

    DO = DO_a + (DO_e - IDOD - DO_a) / D                                            eq 23

⚠️ **That literal reading is wrong whenever the ambient is stratified, and case24 shows it.**
With `DO_a` taken at the plume's own depth it misses the exe's printed column by **0.218 mg/L**
on test37 and 0.171 on test39 -- 435x and 341x what three printed decimals can resolve -- and no
choice of a single `DO_a`, constant or linear in depth, closes the gap. What does close it is
integrating the entrained ambient along the trajectory:

    d(DO * D) / dD = DO_a(z)                                                   the measured form

which fits **both** traces to 0.0064 mg/L, the floor for reconstructing an integral from
printed rows. Two different geometries -- one merging and surfacing, one neither -- with one
model and one seed.

**This is the reference's stated intent, not a departure from it.** The 3rd edition (pp. 12-13) says
"to solve this equation it is necessary to have field data on the `cDOa` **profile**", and then the
sentence that settles it: if an outfall sits in an oxygen-poor basin and the plume rises to the
surface, "the resulting DO in the plume will be very nearly the same as **the deep water**". An
algebraic `DO_a` evaluated where the plume ends up would give the *surface* value -- the opposite
answer. The reference names the phenomenon: **"forced upwelling" or "effluent pumping"**. Eq 23 is
the uniform-ambient special case, where `integral(DO_a dD) = DO_a (D - 1)` recovers it exactly.

✅ **And it reconciles with the carbonate module rather than contradicting it.** Ledger row 39 found
that one scalar endmember explains every TA row of case03, i.e. that mixing is algebraic. Both hold,
because case24's `testC.csv` puts ambient TA at 3000 across *every depth those plumes traverse*:
where the ambient is uniform the path integral **is** the algebraic form. test38 confirms it
directly. So there is one rule for every entrained scalar, and the manual's algebraic equations are
its special case.

⚠️ **BOD does nothing in the near field, and that is measured too.** case24's test39 (cBOD5 0,
nBOD5 30 mg/L) and test40 (cBOD5 20, nBOD5 0) are **byte-identical**. The manual says as much --
"BOD's effect during initial dilution is neglected; IDOD is not" -- and the 3rd edition explains
why: a mixing zone is minutes, a BOD decay constant is per day.

⚠️⚠️ **The far field is measured now, and eq 28's dilution is simply absent from the exe.** Ten
traces across case25, case26 and the conversion experiment settle every unknown in eqs 24-30. The
5-day to ultimate conversion is exactly eqs 24-25, the typed decay rates are used **as typed** with
no theta correction, `FF` enters exactly as eq 30 writes it -- and the near-field dilution `D` never
enters at all. The exe applies the **undiluted** effluent ultimate demand to the far field:

    DO(t) = DO_a + (DO_f - DO_a)/FF - [ L_ce(1-e^{-kc t}) + L_ne(1-e^{-kn t})
                                        - L_a(1-e^{-kc t}) ] / FF        the measured form

Three runs differing *only* in the trajectory prove it: at near-field dilutions of 169.75, 217.02
and 246.61 -- a 45 % span -- the far-field DO curve moves by 0.02 mg/L, where eq 28's `/D` would
move it by 31 %. `far_field_oxygen` computes the manual's dilution-corrected form by default and the
exe's behind `reproduce_undiluted_bod`.

⚠️ **The consequence is unbounded, and the exe prints it without complaint.** An effluent BOD that a
170:1 near field has all but removed still exerts its full demand: run 7 of the conversion
experiment (cBOD5 1000 mg/L) reports a far-field DO of **-184.985 mg/L**. Negative oxygen,
reproduced by the form above to 0.4 %. This is the same defect the ambient-BOD reading chased -- an
ambient BOD is subtracted undiluted because *nothing* is diluted -- and it belongs at the top of the
SSMC list.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from plumes2.ambient import AmbientProfileView
from plumes2.config import Case, EffluentDO

__all__ = [
    "BOD5_DAYS",
    "far_field_oxygen",
    "near_field_oxygen",
    "rate_at_temperature",
    "ultimate_bod",
]

#: The incubation period a BOD5 measurement is defined over. Five days, by definition.
BOD5_DAYS = 5.0


def ultimate_bod(bod5: float, decay_per_day: float) -> float:
    """Ultimate BOD from the 5-day value, eqs 24-25: `BOD_L = BOD5 / (1 - exp(-k*5))`.

    The 5-day figure is what a laboratory reports; the ultimate is what the decay law needs. With
    the default `k_c` = 0.23/d the factor is 1.4634, and with `k_n` = 0.1/d it is 2.5415 -- so the
    nitrogenous channel's slower rate makes its ultimate demand *larger* for the same measurement,
    which is the opposite of what a quick reading suggests.

    ✅ Measured. The conversion is exactly this, at each channel's own typed rate: ten far-field
    traces spanning carbonaceous rates of 0.23, 1.0 and 5.0 /day fit it to 0.009-0.10 mg/L once the
    exe's missing dilution is accounted for. An earlier reading had it multiplied by an unexplained
    1.9-2.6x that tracked the rate; that factor was an artefact of a mis-recorded cBOD5 combined
    with a division the exe does not perform, and it is retired.
    """
    if decay_per_day <= 0.0:
        raise ValueError("a BOD decay rate must be positive; a zero rate has no ultimate demand")
    return bod5 / (1.0 - np.exp(-decay_per_day * BOD5_DAYS))


def rate_at_temperature(rate_at_20: float, theta: float, temperature: float) -> float:
    """Eqs 26-27: `k(T) = k(20) * theta^(T - 20)`.

    ⚠️ **Which temperature is not established.** The plume's, the ambient's at the trapping depth,
    or the effluent's -- the manual says only "T", and no archived run varies a temperature with
    BOD active, so nothing distinguishes them. Callers pass what they mean; `far_field_oxygen`
    passes the plume temperature at the transition and flags it.
    """
    return rate_at_20 * theta ** (temperature - 20.0)


def near_field_oxygen(
    effluent: EffluentDO,
    ambient_oxygen: NDArray[np.float64],
    dilution: NDArray[np.float64],
    *,
    reproduce_idod_on_ambient: bool = False,
) -> NDArray[np.float64]:
    """Plume DO along the trajectory, mg/L, by integrating the entrained ambient.

    `ambient_oxygen` is the receiving water's DO **at each sample's own depth**, and `dilution` is
    the flux-averaged dilution at the same samples. Both must be ordered along the path, because
    the integral is a path integral -- that is the whole point.

    The seed is `DO_e - IDOD` at `D = 1`, which is eq 23 as the manual writes it: the immediate
    demand is a property of the effluent, exerted once, and then diluted with it.

    ⚠️⚠️ **`reproduce_idod_on_ambient` -- the exe subtracts IDOD from the *ambient* instead.** One
    symbol out of place in eq 23, and the consequence is not small: the demand is then exerted by
    every unit of water entrained, so it grows with dilution rather than being diluted away.

        manual   DO = [ (DO_e - IDOD) + integral(DO_a dD)         ] / D
        exe      DO = [  DO_e         + integral((DO_a - IDOD) dD) ] / D

    so the manual's IDOD falls off as `1/D` while the exe's tends to its full value.

    case27 run 9 measures it: an IDOD of 3 mg/L against an otherwise identical run moves the DO
    column by **0.059 mg/L at `D` = 1.02 and by 2.989 at `D` = 246.6** -- it *grows*, where eq 23
    requires it to shrink to 0.012. `IDOD (D-1)/D` fits that to 0.0195 mg/L worst and 0.0037 mean,
    against 2.98 for the manual's form. ⚠️ The two are identical at `IDOD` = 0, which is every other
    archived trace, so three phases of DO validation could not have seen this.

    ✅ **Confirmed at 33x that IDOD.** case28 runs the same thing at 100 mg/L: the implied IDOD,
    backed out row by row, converges to **100.010 against a typed 100**. The exe prints a near-field
    DO of **-93.2 mg/L** doing it -- no clamp, no warning, no NaN, which no archived trace had ever
    tested. ⚠️ The *first-step* convention is what degrades at scale, not the form: the one-step
    accumulator lag of row 220 is worth 0.06 mg/L at IDOD 3 and 1.9 at IDOD 100, so reproduction
    past `D` > 5 goes from 0.0010 to 0.74 mg/L. ⚠️ And both IDOD-100 runs print exactly **0.000** in
    their first row, where this form gives +0.25 and where their differing ambients say the two runs
    should differ at all. One row, already the known-special one; recorded, not modelled.

    ⚠️ **Pass a fine grid.** The integral is evaluated by trapezoid over the samples given, so its
    accuracy is the caller's resolution. `results.run` integrates on a grid eight times the output
    resolution and interpolates down, which costs nothing and keeps the reported column independent
    of how many rows were asked for.

    ⚠️ **BOD is deliberately absent here**, and that is measured rather than assumed -- see the
    module docstring. A BOD term in the near field would be wrong, not merely negligible.
    """
    ambient = np.asarray(ambient_oxygen, dtype=np.float64)
    flux = np.asarray(dilution, dtype=np.float64)
    if ambient.shape != flux.shape:
        raise ValueError(
            f"ambient_oxygen and dilution must be sampled together: got {ambient.shape} and "
            f"{flux.shape}"
        )
    if flux.size == 0:
        return np.empty(0, dtype=np.float64)
    if np.any(flux < 1.0):
        raise ValueError("dilution must be at least 1 (1 means undiluted effluent)")

    if reproduce_idod_on_ambient:
        # The exe's placement: every unit of entrained water arrives already `IDOD` short. Applied
        # to the profile rather than as a separate term, so it goes through the same integral and
        # the same first-sample convention below without a second thing to keep consistent.
        seed = effluent.dissolved_oxygen
        ambient = ambient - effluent.idod
    else:
        seed = effluent.dissolved_oxygen - effluent.idod
    # d(DO*D)/dD = DO_a(z), integrated from the first sample. Trapezoid rather than a midpoint rule
    # because the samples are the only evaluation points available, and the ambient varies slowly
    # while the dilution does not.
    increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(flux)
    integral = np.concatenate([[0.0], np.cumsum(increments)])
    # ⚠️ **The integral starts at the first sample, crediting no ambient before it**, and that is
    # measured rather than chosen. The exe's step 1 sits at D = 1.020 yet prints DO = 1.961, which
    # is 2.000/1.020 to five figures -- i.e. `DO*D` still equals `DO_e - IDOD` there, with none of
    # the 2 % already-entrained ambient counted. An earlier revision "corrected" for that by adding
    # `(D_1 - 1) * DO_a` and got 334x printed precision instead of 12.8x, which is how the
    # convention was found. It reads as a one-step lag in the exe's accumulator; for our own runs
    # the first sample is at D = 1 exactly, so the two conventions coincide and nothing is lost.
    return np.asarray((seed + integral) / flux, dtype=np.float64)


def near_field_oxygen_for(
    case: Case, dilution: NDArray[np.float64], depth: NDArray[np.float64]
) -> NDArray[np.float64]:
    """`near_field_oxygen` with the ambient profile resolved from the case.

    Raises if the case carries no DO endmember or no ambient DO profile, because a DO column
    computed from a missing half would be a plausible wrong answer rather than an error.
    """
    if case.effluent_do is None:
        raise ValueError("this case carries no effluent DO endmember")
    view = AmbientProfileView(case.ambient)
    return near_field_oxygen(case.effluent_do, view.dissolved_oxygen(depth), dilution)


def far_field_oxygen(
    effluent: EffluentDO,
    ambient_oxygen: float,
    ambient_cbod5: float,
    ambient_nbod5: float,
    oxygen_at_transition: float,
    near_field_dilution: float,
    dilution_factor: NDArray[np.float64],
    travel_time_days: NDArray[np.float64],
    *,
    temperature: float | None = None,
    reproduce_undiluted_bod: bool = False,
) -> NDArray[np.float64]:
    """The far-field DO sag, eqs 24-30, measured against ten traces.

        L_f  = (BOD_Le - BOD_La) / D                                            eqs 28-29
        DO(t) = DO_a + (DO_f - DO_a)/FF
                     - (L_fc/FF)(1 - exp(-k_c t)) - (L_fn/FF)(1 - exp(-k_n t))       eq 30

    `near_field_dilution` is eq 28's `D` -- the flux-averaged dilution the near field ended at.
    `dilution_factor` is Brooks' `FF`, which is 1 at the transition and grows downstream, and
    `travel_time_days` is the time since it. `oxygen_at_transition` is `DO_f`, the near-field
    endpoint, so the two halves join at the value the near field actually produced rather than at a
    recomputed one.

    ⚠️ **`ambient_oxygen` is the profile's value at the trapping depth**, not its depth-mean and not
    the value where the plume started -- measured, not assumed. case28 runs two mirror-image ambient
    profiles built to share a depth-mean (7.167) while differing at the trapping depth (8.264
    against 6.354), so their difference isolates this term: it comes out **1.765 mg/L at 500 m in
    three independent pairs**, across an 87x change in decay rate and a 100 mg/L change in IDOD,
    against 1.769 for the trapping depth and 0.750 for the depth-mean. Inverting eq 30 for the
    ambient and reading it back as a depth gives 4.419 m and 4.501 m from profiles with **opposite
    gradients**, against a trapping depth of 4.472 m.

    What the traces settled, in the order it matters:

    ⚠️⚠️ **`reproduce_undiluted_bod` -- the exe never divides by `D`, and the result is unbounded.**
    Set it to reproduce the exe: the effluent's *undiluted* ultimate demand is applied to the far
    field, so a discharge the near field has diluted 170:1 exerts the demand it had at the port. The
    measurement is three runs differing only in trajectory -- `D` = 169.75, 217.02, 246.61, a 45 %
    span -- whose far-field DO agrees to 0.02 mg/L, where the `/D` would separate them by 31 %. It
    is the single worst defect found in this exe: run 7 of the conversion experiment prints a DO of
    **-185 mg/L**. Default `False` computes eq 28 as the manual writes it, which is also the only
    form that conserves oxygen.

    ✅ **The `1/FF` on the demand is confirmed** (row 231) and so is the `1/FF` on the initial
    dilution: the pointwise demand implied by the observed sag is flat along the whole far field
    with it and halves without it.

    ✅ **The rates are used exactly as typed**, at 20 °C, with **no theta correction** (row 235):
    successive DO decrements decay at the typed ratio to 4.99 against 5.00. So `temperature`
    defaults to `None`, meaning "as typed" -- pass a temperature only to *depart* from the exe, and
    eqs 26-27 will then be applied. ⚠️ Which temperature eqs 26-27 intend is still unestablished;
    nothing in the archive varies one with BOD active.

    ✅ **Both BOD channels are converted to ultimate by eqs 24-25 at their own rate**, and so is the
    ambient, at the *effluent's* carbonaceous rate. Fitting case25's ambient run with the ambient
    left as a 5-day figure instead misses by 2.64 mg/L against 0.10 for the conversion.

    Worst residuals over every far-field trace in the archive: 0.009-0.022 mg/L on the four runs
    with an ordinary demand, 0.07-0.10 where the typed rate is 5 /day, and 1.7 % of the excursion on
    the two runs the defect sends to absurd values.
    """
    factor = np.asarray(dilution_factor, dtype=np.float64)
    time = np.asarray(travel_time_days, dtype=np.float64)
    if factor.shape != time.shape:
        raise ValueError("dilution_factor and travel_time_days must be sampled together")
    if np.any(factor < 1.0):
        raise ValueError("the Brooks dilution factor is 1 at the transition and grows from there")

    if near_field_dilution < 1.0:
        raise ValueError("the near-field dilution is at least 1 (1 means undiluted effluent)")

    if temperature is None:
        k_c, k_n = effluent.cbod_decay, effluent.nbod_decay
    else:
        k_c = rate_at_temperature(effluent.cbod_decay, effluent.theta_c, temperature)
        k_n = rate_at_temperature(effluent.nbod_decay, effluent.theta_n, temperature)

    # eqs 24-25 on every channel. ⚠️ The *ambient* carbonaceous demand converts at the effluent's
    # carbonaceous rate, which is measured: the ambient CSV carries a 5-day figure and no rate of
    # its own, and case25's ambient run picks the conversion over the raw value by 26x.
    effluent_c = ultimate_bod(effluent.cbod5, k_c)
    effluent_n = ultimate_bod(effluent.nbod5, k_n)
    ambient_c = ultimate_bod(ambient_cbod5, k_c)
    ambient_n = ultimate_bod(ambient_nbod5, k_n)

    # eqs 28-29: the excess ultimate demand over the receiving water. The exe applies it undiluted;
    # the manual divides it by the dilution the near field achieved.
    divisor = 1.0 if reproduce_undiluted_bod else near_field_dilution
    excess_c = (effluent_c - ambient_c) / divisor
    excess_n = (effluent_n - ambient_n) / divisor

    return np.asarray(
        ambient_oxygen
        + (oxygen_at_transition - ambient_oxygen) / factor
        - (excess_c / factor) * (1.0 - np.exp(-k_c * time))
        - (excess_n / factor) * (1.0 - np.exp(-k_n * time)),
        dtype=np.float64,
    )
