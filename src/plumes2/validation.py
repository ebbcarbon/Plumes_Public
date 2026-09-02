"""The validation ledger, executable.

PLAN.md §6 records 245 rows, 221 of them stating something checkable: what was measured,
against which reference, to what precision. That ledger is prose, and prose goes stale — a
number written down in August is not evidence that the code still produces it in November.
This module makes each claim **runnable**: one `Target` per row, carrying the measurement as a
callable and the reference as a value, so the same registry can be driven by two consumers that
cannot disagree.

    pytest tests/test_validation.py     the safety net: every target must still pass
    plumes2 validate -o report.html     the evidence: ours, the reference, and the error

⚠️ **One registry, two consumers, no third source of truth.** The temptation is to write the
numbers into a notebook and let the tests keep their own copies. That is how a validation report
starts disagreeing with the suite that is supposed to back it. The tests here are deliberately thin
-- they run the registry and assert -- and the existing per-module tests stay as they are, because
they test far more than the headline number of each claim.

⚠️ **This is a first tranche, not the whole ledger.** The targets below cover every phase and every
reference case that carries a decodable number, but §6 has rows this module does not yet execute --
mostly ones whose measurement is a whole-table comparison that already lives in a dedicated test.
`coverage_by_phase` reports what is and is not here, so the gap is visible rather than implied.

**A target's reference is never computed by us.** It is a number from an exe trace, from a manual,
or from an independent implementation. Where a claim has no external reference at all -- `Ω_brucite`
is the example, since the exe cannot report it -- the target is marked `internal` and its reference
is an analytical limit or a literature range, which is weaker evidence and is labelled as such.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from plumes2.config import Case, EffluentChemistry

if TYPE_CHECKING:
    from plumes2.io.prj import PrjFile
from plumes2.nearfield.merging import MergingChoices
from plumes2.nearfield.solver import NearFieldSolution

__all__ = [
    "NON_DEFAULT_PROFILE_TRACES",
    "TARGETS",
    "Agreement",
    "Evidence",
    "Outcome",
    "Target",
    "coverage_by_phase",
    "ledger_row_of",
    "measure",
    "rows_by_agreement",
    "run_all",
]

_ROOT = Path(__file__).resolve().parents[2]
_CASES = _ROOT / "reference_cases"
_EXAMPLE = _ROOT / "upstream" / "Example_project"

#: The exe writes DOS line endings, and splitting on them is what keeps a stray bare newline
#: inside a value from being read as a row break.
CRLF = "\r\n"


class Evidence(StrEnum):
    """How strong a target's reference is, which is not the same as how strong the agreement is."""

    #: A number printed by the exe. The strongest kind: an independent implementation.
    GOLDEN = "golden"
    #: A number printed in a manual. Weaker -- the manual's own worked example disagrees with the
    #: shipped trace by 1.2 %, so text and binary are different generations (PLAN.md rows 9-11).
    MANUAL = "manual"
    #: An independent third-party implementation, e.g. PyCO2SYS or a published EOS check value.
    EXTERNAL = "external"
    #: No external reference exists. An analytical limit, a literature range, or an internal
    #: consistency requirement. Labelled because it is weaker, not because it is worthless.
    INTERNAL = "internal"


class Agreement(StrEnum):
    """What a *passing* target means, which `Evidence` deliberately does not say.

    ⚠️⚠️ **This exists because "executable" and "agreeing" are not the same thing, and the
    coverage fraction cannot tell them apart.** Five of the green rows are gaps rather than
    matches -- the number they pin *is the size of a disagreement* -- and until 2026-08-20 that
    lived only in the prose of their notes. So `148/154 numbered ledger rows are executable` read
    as 96 % agreement to anyone who did not open the notes, with the near field's largest defect
    (rows 157b, 186) counted indistinguishably from a 1e-5 match.

    That is the same failure this ledger keeps hitting: correct arithmetic, wrong presentation.
    The previous four instances were fixed by making the presentation derive from the data
    (`test_every_row_sits_in_the_bucket_its_own_text_claims` and its neighbours); this is the
    fifth, and `test_a_recorded_divergence_is_labelled_as_one` ties this field to the note in
    **both** directions so neither can drift from the other.
    """

    #: We reproduce the reference to within what the reference can resolve. The default.
    MATCHES = "matches"
    #: ⚠️ **The number is the size of a gap we have not closed**, pinned so a change is a test
    #: failure. Passing means the disagreement is the size we recorded, not that there is none.
    DIVERGES = "diverges"
    #: We agree with the reference by reproducing something *wrong in the reference*, behind a
    #: named `reproduce_*` flag that defaults to the corrected behaviour. Parity, not correctness.
    REPRODUCES_DEFECT = "reproduces defect"


@dataclass(frozen=True, slots=True)
class Target:
    """One executable claim from the ledger."""

    #: The PLAN.md §6 row number, so a reader can find the prose behind the number.
    row: str
    phase: int
    evidence: Evidence
    #: What is being claimed, in one line.
    claim: str
    #: Where the reference number comes from.
    source: str
    #: Our value. Called once per run; keep it cheap or memoise the expensive part.
    measure: Callable[[], float]
    reference: float
    #: Absolute tolerance, in the quantity's own units. Chosen from what the reference can
    #: resolve -- three printed decimals, or a stated MARE bar -- never from what we happen to hit.
    tolerance: float
    unit: str = ""
    #: Why the tolerance is what it is, and anything a reader would otherwise misread.
    note: str = ""
    #: What a pass here *means*. Defaults to `MATCHES`, so the exceptions are the ones that carry
    #: a declaration -- and a note claiming a divergence without this field set is a test failure.
    agreement: Agreement = Agreement.MATCHES


@dataclass(frozen=True, slots=True)
class Outcome:
    """A target, measured."""

    target: Target
    ours: float
    #: `None` when the measurement raised -- which is itself a result, and is reported as one.
    error: str | None = None

    @property
    def absolute(self) -> float:
        return abs(self.ours - self.target.reference)

    @property
    def relative(self) -> float:
        """Fractional error, or `nan` where the reference is zero and a ratio has no meaning."""
        if self.target.reference == 0.0:
            return math.nan
        return self.absolute / abs(self.target.reference)

    @property
    def passed(self) -> bool:
        if self.error is not None:
            return False
        return math.isfinite(self.ours) and self.absolute <= self.target.tolerance


# --------------------------------------------------------------------------- shared fixtures
#
# Memoised because several targets share a run, and a validation pass that integrated the same
# case six times would be slow enough that nobody ran it.


@cache
def _archive_traces() -> tuple[Path, ...]:
    """Every archived `.dat`, **de-duplicated by content**. 158 distinct of 168 files.

    ⚠️⚠️ **Ten byte-duplicate groups exist in the archive**, found by the 2026-08-21 audit:
    the same exe run filed under two names, usually in two different cases. Only one of the ten is
    deliberate -- case30's `gap_4_repeat.dat`, which exists to check determinism (and still does,
    because it is compared to its twin explicitly rather than swept over).

    They are harmless to any measure that takes a **max** over the archive, which most do. They
    inflate anything that takes a **mean** or a **count** -- the equation-of-state sweep counted
    50 917 rows against 51 670 distinct, 6.5 % over. So every archive-wide sweep now goes through
    here.

    ⭐ **The duplicates are kept on disk, not deleted.** Each is described by name in its own
    case's README, and deleting a trace a write-up refers to trades one inconsistency for another.
    De-duplicating at the point of measurement fixes the counts and leaves the archive readable.

    Deterministic: paths are sorted first, so the survivor of each duplicate group is the same on
    every run.
    """
    import hashlib

    seen: set[str] = set()
    keep: list[Path] = []
    # ⚠️ The one place the raw glob must stay -- this function *is* the de-duplication.
    for path in sorted([*_EXAMPLE.glob("*.dat"), *_CASES.glob("*/*.dat")]):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        keep.append(path)
    return tuple(keep)


@cache
def _integrated(
    fingerprint: str, max_time: float, merging_key: str
) -> NearFieldSolution:
    """Internal cache slot -- see `_integrate_once`. Keyed on a canonical serialisation."""
    from plumes2.nearfield.solver import integrate

    case, merging = _INTEGRATION_ARGS[(fingerprint, max_time, merging_key)]
    if merging is None:
        return integrate(case, max_time=max_time)
    return integrate(case, max_time=max_time, merging=merging)


#: Side table for `_integrated`, which can only take hashable arguments. Populated by
#: `_integrate_once` immediately before the cached call.
_INTEGRATION_ARGS: dict[tuple[str, float, str], tuple[Case, MergingChoices | None]] = {}


def _integrate_once(
    case: Case, *, max_time: float, merging: MergingChoices | None = None
) -> NearFieldSolution:
    """`solver.integrate`, memoised across targets on an exact key.

    ⚠️ **Measured, and it delivers less than the estimate that motivated it.** A first count with
    a coarse key -- rounded flow, `str(merging)` -- suggested 74 integrations of which 56 were
    distinct, so 18 avoidable. With the exact key the cache reports **11 hits against 50 misses**:
    the coarse key had collided cases that are genuinely different, over-counting the redundancy.
    11 integrations avoided of about 63 is a real saving and a modest one, and the wall-clock effect
    is inside the run-to-run noise on this machine.

    ⭐ Kept anyway, because it costs nothing and because the *number* of integrations is the only
    lever the 2026-08-21 audit found -- the right-hand side itself has no hot spot worth more than
    a few per cent (PLAN §8d). The key is the case's canonical JSON plus the end time and the
    merging choices, so a hit is the *same* integration rather than a similar one.

    ⚠️ Unbounded by design: about 50 solutions with dense output live for the length of a suite
    run. Fine for a test process, and not something to import into a long-lived one.

    ⚠️ `Case` is frozen but holds lists, so it is not hashable and cannot be an `lru_cache`
    argument directly. `model_dump_json()` is the canonical form; using a hand-listed tuple of
    fields would risk two different cases colliding on a missing field, which is a wrong answer
    rather than a slow one.

    ⚠️ The returned solution is **shared**, so callers must treat it as read-only. Every caller
    here does -- they `sample()` it and read `solution.t`.
    """
    fingerprint = case.model_dump_json()
    merging_key = repr(merging)
    key = (fingerprint, max_time, merging_key)
    _INTEGRATION_ARGS[key] = (case, merging)
    return _integrated(fingerprint, max_time, merging_key)


@cache
def _case(relative: str) -> Case:
    import warnings

    from plumes2.io.project import load_project

    with warnings.catch_warnings():
        # The Macoma projects extrapolate past their ambient profile's last level. Recorded as a
        # known property of the archive (PLAN.md), not something this run needs to re-announce.
        warnings.simplefilter("ignore")
        return load_project(_ROOT / relative, warn_on_drift=False).to_case()


@cache
def _dat(relative: str):  # type: ignore[no-untyped-def]
    from plumes2.io.dat import read_dat

    return read_dat(_ROOT / relative)


@cache
def _run(relative: str, samples: int = 240):  # type: ignore[no-untyped-def]
    from plumes2.results import run

    return run(_case(relative), samples=samples)


# --------------------------------------------------------------------------- the targets


def _oxygen_worst_residual() -> float:
    """Worst absolute DO difference against every archived trace that printed the column.

    Fed the exe's own dilution and depth, so it measures the oxygen model and not our trajectory --
    the same isolation `_case03_chemistry` uses for the carbonate solver.
    """
    from plumes2.biochem.do_bod import near_field_oxygen
    from plumes2.config import EffluentDO
    from plumes2.io.dat import read_dat

    # The DO tab is not saved in any `.prj`, so these are the user-recorded inputs; see
    # reference_cases/case24_macoma_dissolved_oxygen/README.md.
    effluent = EffluentDO(dissolved_oxygen=2.0, idod=0.0, cbod5=20.0, nbod5=30.0)
    depths = np.array([1.0, 3.0, 6.0, 10.0, 12.0])
    values = np.array([8.0, 9.0, 10.0, 9.0, 8.0])

    worst = 0.0
    directory = _CASES / "case24_macoma_dissolved_oxygen"
    for path in sorted(directory.glob("*.dat")):
        frame = read_dat(path).nearfield
        if "DO" not in frame.columns:
            continue
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        ambient = np.interp(-frame["Depth"].to_numpy(dtype=np.float64), depths, values)
        ours = near_field_oxygen(effluent, ambient, dilution)
        worst = max(worst, float(np.max(np.abs(ours - frame["DO"].to_numpy(dtype=np.float64)))))
    return worst


#: The DO tab is saved in no `.prj`, so every far-field trace needs its inputs supplied by hand.
#: ⚠️ The nitrogenous rate differs between the cases; see each case README.
#: `(trace, cBOD5, carbonaceous rate, nitrogenous rate, ambient cBOD5)`.
_FAR_FIELD = [
    ("case25_farfield_bod/ModelResults_2.dat", 20.0, 0.23, 0.23, 0.0),
    ("case25_farfield_bod/ModelResults_3.dat", 20.0, 0.23, 0.23, 500.0),
    ("case26_farfield_bod_rates/ModelResults_1.dat", 20.0, 5.0, 0.23, 0.0),
    ("case26_farfield_bod_rates/ModelResults_2.dat", 20.0, 1.0, 0.23, 0.0),
    ("case27_farfield_bod_conversion/ModelResults_2.dat", 20.0, 0.23, 0.1, 0.0),
    ("case27_farfield_bod_conversion/ModelResults_4.dat", 20.0, 0.23, 0.1, 0.0),
    ("case27_farfield_bod_conversion/ModelResults_6.dat", 20.0, 0.23, 0.1, 0.0),
]


def _far_field_residual(*, undiluted: bool = True, traces: list | None = None) -> float:
    """Worst absolute far-field DO difference over the archived traces, on the exe's own grid."""
    from plumes2.biochem.do_bod import far_field_oxygen
    from plumes2.config import EffluentDO

    worst = 0.0
    for relative, cbod5, k_c, k_n, ambient in traces if traces is not None else _FAR_FIELD:
        dat = _dat(f"reference_cases/{relative}")
        near, far = dat.nearfield, dat.farfield
        dilution = float(near["Dilutn"].iloc[-1])
        effluent = EffluentDO(
            dissolved_oxygen=2.0, cbod5=cbod5, nbod5=30.0, cbod_decay=k_c, nbod_decay=k_n
        )
        ours = far_field_oxygen(
            effluent,
            8.0,
            ambient,
            0.0,
            float(near["DO"].iloc[-1]),
            dilution,
            far["Dilution"].to_numpy(dtype=np.float64) / dilution,
            far["Time"].to_numpy(dtype=np.float64) / 24.0,
            reproduce_undiluted_bod=undiluted,
        )
        printed = far["DO"].to_numpy(dtype=np.float64)
        worst = max(worst, float(np.max(np.abs(ours - printed))))
    return worst


def _idod_residual(*, on_ambient: bool = True) -> float:
    """Worst DO difference on case27 run 9, the only archived trace with a non-zero IDOD.

    Measured past `D` > 5, where the exe's one-step accumulator lag has washed out -- the same
    window row 219 uses, and for the same reason.
    """
    from plumes2.biochem.do_bod import near_field_oxygen
    from plumes2.config import EffluentDO

    frame = _dat("reference_cases/case27_farfield_bod_conversion/ModelResults_9.dat").nearfield
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    effluent = EffluentDO(
        dissolved_oxygen=2.0, idod=3.0, cbod5=20.0, nbod5=30.0, cbod_decay=0.23, nbod_decay=0.1
    )
    ours = near_field_oxygen(
        effluent,
        np.full_like(dilution, 8.0),
        dilution,
        reproduce_idod_on_ambient=on_ambient,
    )
    difference = np.abs(ours - frame["DO"].to_numpy(dtype=np.float64))
    return float(np.max(difference[dilution > 5.0]))


def _far_field_ambient_residual(oxygen: float) -> float:
    """Worst far-field DO difference on case27 run 8, for one choice of eq 30's `DO_a`."""
    from plumes2.biochem.do_bod import far_field_oxygen
    from plumes2.config import EffluentDO

    dat = _dat("reference_cases/case27_farfield_bod_conversion/ModelResults_8.dat")
    near, far = dat.nearfield, dat.farfield
    dilution = float(near["Dilutn"].iloc[-1])
    ours = far_field_oxygen(
        EffluentDO(dissolved_oxygen=2.0, cbod5=20.0, nbod5=30.0, cbod_decay=0.23, nbod_decay=0.1),
        oxygen,
        0.0,
        0.0,
        float(near["DO"].iloc[-1]),
        dilution,
        far["Dilution"].to_numpy(dtype=np.float64) / dilution,
        far["Time"].to_numpy(dtype=np.float64) / 24.0,
        reproduce_undiluted_bod=True,
    )
    return float(np.max(np.abs(ours - far["DO"].to_numpy(dtype=np.float64))))


def _municipal_negative_oxygen() -> float:
    """Lowest far-field DO our reproduction prints from a **municipal-strength** cBOD5. -1.86.

    The single most reportable number in the DO investigation. Row 241 needed a cBOD5 of 1000 to
    drive the printed oxygen negative, and 1000 is not a figure anyone types by accident. This is
    **20 mg/L** -- ordinary municipal wastewater, and the value the tab ships with -- at a
    carbonaceous rate of 20 /day, which is case27's run 10.

    The **exe's own** printed minimum is what is returned, because the claim is about what the exe
    reports rather than about our accuracy. Two things are asserted alongside it: that our
    reproduction with `reproduce_undiluted_bod` on also goes negative, and that the **corrected**
    path stays positive on the same inputs. The second is what makes this a defect and not a
    regime.

    ⚠️ Our reproduction reaches -1.998 against the exe's -1.863, a worst residual of **0.591 mg/L**
    over the run -- nearly six times the 0.101 row 237 establishes across the standard traces. A
    20 /day carbonaceous rate is the most extreme in the archive and it is where our far-field
    model is weakest; that is recorded here rather than buried in a widened tolerance.
    """
    from plumes2.biochem.do_bod import far_field_oxygen
    from plumes2.config import EffluentDO

    dat = _dat("reference_cases/case27_farfield_bod_conversion/ModelResults_10.dat")
    near, far = dat.nearfield, dat.farfield
    if far is None or "DO" not in far.columns:
        raise AssertionError("case27 run 10 no longer prints a far-field DO column")
    if float(np.min(far["DO"].to_numpy(dtype=np.float64))) >= 0.0:
        raise AssertionError("case27 run 10 no longer prints negative oxygen")

    effluent = EffluentDO(
        dissolved_oxygen=2.0, cbod5=20.0, nbod5=30.0, cbod_decay=20.0, nbod_decay=0.1
    )
    dilution = float(near["Dilutn"].iloc[-1])
    factor = far["Dilution"].to_numpy(dtype=np.float64) / dilution
    days = far["Time"].to_numpy(dtype=np.float64) / 24.0
    faithful, corrected = (
        far_field_oxygen(
            effluent,
            8.0,
            0.0,
            0.0,
            float(near["DO"].iloc[-1]),
            dilution,
            factor,
            days,
            reproduce_undiluted_bod=flag,
        )
        for flag in (True, False)
    )
    if float(np.min(corrected)) < 0.0:
        raise AssertionError("the corrected path went negative too; the defect is not isolated")
    if float(np.min(faithful)) >= 0.0:
        raise AssertionError("our reproduction of the defect no longer goes negative")
    return float(np.min(far["DO"].to_numpy(dtype=np.float64)))


#: Half the last printed digit of a `DO` column: three decimals, as everything else in the `.dat`.
_PRINTED_DO = 0.0005


def _oxygen_path_integral_errors() -> tuple[float, float]:
    """`(path-integral residual, algebraic residual)` in **multiples of printed precision**.

    ⭐⭐ The finding row 214 records, executable. Entrained ambient oxygen is accumulated **along
    the trajectory** rather than evaluated at the depth the plume ends up:

        d(DO * D)/dD = DO_a(z)        against        DO = DO_a + (DO_e - DO_a)/D

    Over case24's four DO traces the path integral lands within **9.6x** what three decimals resolve
    and the algebraic reading -- the manual's own eq 23 -- misses by **435x**. Reported in
    multiples of the printed digit rather than in mg/L because that is the scale that decides
    whether a difference is visible at all.

    ⚠️ Seeded with `DO_e - IDOD` exactly, crediting none of the 2 % already entrained by the first
    printed row. That is row 220's one-step accumulator lag, and correcting for it makes the fit
    **worse** -- which is why the lag is treated as a property of the exe's DO channel rather than
    as an error to remove.

    ⚠️ The ambient profile is not in any `.prj` or `.dat`; these are the user-recorded values from
    case24's README, the same ones `_oxygen_worst_residual` uses.
    """
    from plumes2.io.dat import read_dat

    depths = np.array([1.0, 3.0, 6.0, 10.0, 12.0])
    values = np.array([8.0, 9.0, 10.0, 9.0, 8.0])
    seed = 2.0  # DO_e - IDOD, and exactly what the exe prints on its first row.

    worst_path = 0.0
    worst_penalty = float("inf")
    traces = 0
    for path in sorted((_CASES / "case24_macoma_dissolved_oxygen").glob("*.dat")):
        frame = read_dat(path).nearfield
        if "DO" not in frame.columns:
            continue
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        printed = frame["DO"].to_numpy(dtype=np.float64)
        ambient = np.interp(-frame["Depth"].to_numpy(dtype=np.float64), depths, values)
        increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(dilution)
        integrated = (seed + np.concatenate([[0.0], np.cumsum(increments)])) / dilution
        algebraic = ambient + (seed - ambient) / dilution
        developed = dilution > 5.0
        this_path = float(np.max(np.abs((integrated - printed)[developed])))
        this_algebraic = float(np.max(np.abs((algebraic - printed)[developed])))
        worst_path = max(worst_path, this_path)
        # The **weakest** per-trace separation, not the ratio of two worsts taken from different
        # traces -- that would be a number about neither. Same correction row 109b needed.
        worst_penalty = min(worst_penalty, this_algebraic / this_path)
        traces += 1
    if traces < 4:
        raise AssertionError(f"only {traces} DO traces found")
    return worst_path / _PRINTED_DO, worst_penalty


def _oxygen_path_integral_error() -> float:
    """The path-integral residual, in multiples of what the `DO` column can resolve."""
    return _oxygen_path_integral_errors()[0]


def _oxygen_algebraic_penalty() -> float:
    """How many times worse eq 23 is than the path integral, on the trace where it does best."""
    return _oxygen_path_integral_errors()[1]


def _oxygen_seed_separability() -> float:
    """The `DO_e` difference between case28 runs 11 and 12, as a fractional dilution offset. 0.036.

    ⭐⭐ The two runs differ in **one** input: an effluent DO of 2 against 20, with IDOD 100 in
    both. If the effluent seed dilutes away while IDOD does not, their near-field columns must
    differ by exactly `18/D` -- and they do, from 17.65 at the first printed row to 0.072 at
    `D` = 246.6. That is what makes `DO_e` and `IDOD` **separable**, and it is why the exe can
    treat them in opposite ways: one is carried by the effluent, the other by the entrained water.

    ⚠️ **Reported as `epsilon`, not in mg/L** -- the residual is `18 x epsilon / D`, so mg/L makes
    the same discrepancy look large near the port and small far from it. Normalised it sits in
    **0.013-0.036**, inside the **0.016-0.044** that rows 109 and 258c measure from salinity on
    entirely different runs. ⭐ So this is a *third* scalar showing the same fixed fractional
    offset between the exe's scalar columns and its own `Dilutn` column, and the first to show it
    on a quantity carried by the effluent rather than entrained.
    """
    near = [
        _dat(f"reference_cases/case28_farfield_do_closeout/ModelResults_{run}.dat").nearfield
        for run in (11, 12)
    ]
    dilution = near[0]["Dilutn"].to_numpy(dtype=np.float64)
    gap = near[1]["DO"].to_numpy(dtype=np.float64) - near[0]["DO"].to_numpy(dtype=np.float64)
    usable = np.isfinite(gap) & np.isfinite(dilution) & (dilution > 0.0)
    if usable.sum() < 400:
        raise AssertionError(f"only {int(usable.sum())} rows to compare")
    seed_gap = 18.0  # the difference in the two runs' effluent DO
    return float(
        np.max(np.abs(gap[usable] - seed_gap / dilution[usable]) * dilution[usable] / seed_gap)
    )


def _supersaturated_far_field_oxygen() -> float:
    """The highest far-field DO the exe prints, against an 8.0 mg/L ambient. 100.06.

    ⚠️⚠️ **An exe defect, and the one that is impossible to argue with.** case26's run 3 has an
    ambient carbonaceous BOD of 500 mg/L -- water with a large oxygen *demand* -- and its plume
    gains oxygen as it travels through it, reaching **100.06 mg/L** where saturation at this
    temperature is about 11. Nine times saturation, out of water that should be depleting it.

    That is eqs 28-29 subtracting the ambient BOD **undiluted**: `BOD_Le/D - BOD_La` instead of
    `(BOD_Le - BOD_La)/D`. The manual's form is positive here and must depress oxygen; only the
    undiluted form has the sign the trace shows. Confirmed twice, at rates a twentieth apart
    (rows 224 and 230).
    """
    far = _dat("reference_cases/case26_farfield_bod_rates/ModelResults_3.dat").farfield
    if far is None or "DO" not in far.columns:
        raise AssertionError("case26 run 3 no longer prints a far-field DO column")
    highest = float(np.max(far["DO"].to_numpy(dtype=np.float64)))
    if highest < 20.0:
        raise AssertionError(f"the supersaturation is gone: {highest}")
    return highest


def _far_field_handoff_gap() -> float:
    """How far the far field's opening rows sit from the near field's last. 0.029 mg/L.

    ⭐ The measurement that refutes a second IDOD term. case28's IDOD-100 runs open their far
    field with **13 rows at `FF` = 1 exactly**, so eq 30 reduces to `DO_f` there and any extra
    demand would show up undiluted. A second, undiluted IDOD would shift those rows by **100**;
    one divided by the near-field dilution would shift them by 0.406. Observed: **0.029**.

    No fit is involved, which is what makes it decisive rather than suggestive -- the near field's
    last printed value and the far field's first are both read straight off the file.
    """
    worst = 0.0
    for run in (11, 12):
        dat = _dat(f"reference_cases/case28_farfield_do_closeout/ModelResults_{run}.dat")
        near, far = dat.nearfield, dat.farfield
        if far is None or "DO" not in far.columns:
            raise AssertionError(f"case28 run {run} no longer prints a far field")
        transition = float(near["Dilutn"].to_numpy(dtype=np.float64)[-1])
        opening = np.abs(far["Dilution"].to_numpy(dtype=np.float64) / transition - 1.0) < 1e-9
        if int(opening.sum()) < 5:
            raise AssertionError(f"case28 run {run} opens with only {int(opening.sum())} FF=1 rows")
        first = float(far["DO"].to_numpy(dtype=np.float64)[opening][0])
        worst = max(worst, abs(first - float(near["DO"].to_numpy(dtype=np.float64)[-1])))
    return worst


#: The two runs carrying a non-zero **ambient** cBOD5, which is what rows 224 and 230 turn on.
#: `(trace, effluent cBOD5, carbonaceous rate, ambient cBOD5)`.
_AMBIENT_BOD_RUNS = (
    ("case25_farfield_bod/ModelResults_3.dat", 20.0, 0.23, 500.0),
    ("case26_farfield_bod_rates/ModelResults_3.dat", 20.0, 5.0, 500.0),
)


def _undiluted_ambient_bod_error() -> float:
    """Worst relative error of the **undiluted** ambient-BOD form against the observed decay. 0.29.

    ⭐⭐ Eqs 28-29 as the manual writes them give `L_f = (BOD_Le - BOD_La)/D`. The exe behaves as
    `BOD_Le/D - BOD_La` -- the ambient term never divided. The two differ by a factor of about `D`,
    which is 170 on these runs, so the archive can tell them apart decisively.

    `L*k` is extracted the way case25's README establishes: in the linear regime `sag * FF / t` is
    the constant `L*k`, and the far field here spans 2.74 hours so `k*t <= 0.026`.

    ⚠️ **The sign argument this row originally rested on does not survive the cBOD5 correction.**
    It read "`(BOD_Le - BOD_La)/D` is positive for cBOD5 2000 against ambient 500 and must depress
    oxygen" -- but 2000 was the mis-recorded value row 225 retracts, and at the true **20** the
    manual's form is negative too. What discriminates is magnitude, not sign: the manual's form
    predicts `L*k` of -0.95 and -14.1 where the runs show **-140.8** and **-1930.9**, so it is
    137-148x too small, while the undiluted form lands within 30 %.
    """
    worst = 0.0
    for relative, cbod5, rate, ambient_bod in _AMBIENT_BOD_RUNS:
        dat = _dat(f"reference_cases/{relative}")
        near, far = dat.nearfield, dat.farfield
        transition = float(near["Dilutn"].to_numpy(dtype=np.float64)[-1])
        factor = far["Dilution"].to_numpy(dtype=np.float64) / transition
        oxygen = far["DO"].to_numpy(dtype=np.float64)
        days = far["Time"].to_numpy(dtype=np.float64) / 24.0
        moving = days > 0.0
        observed = float(np.mean(((oxygen[0] - oxygen)[moving] * factor[moving]) / days[moving]))
        # Eqs 24-25: the five-day figure to ultimate, at the channel's own typed rate.
        to_ultimate = 1.0 - np.exp(-5.0 * rate)
        effluent_ultimate = cbod5 / to_ultimate
        ambient_ultimate = ambient_bod / to_ultimate
        manual = (effluent_ultimate - ambient_ultimate) / transition * rate
        undiluted = (effluent_ultimate / transition - ambient_ultimate) * rate
        if abs(observed / manual) < 50.0:
            raise AssertionError(f"{relative}: the manual form is no longer decisively too small")
        worst = max(worst, abs(undiluted - observed) / abs(observed))
    return worst


def _far_field_rate_is_as_typed() -> float:
    """Far-field residual on case26's rate pair with the rate used **exactly as typed**. 0.07 mg/L.

    ⭐ The runs differ only in the carbonaceous rate, 5.0 /day against 1.0, so they isolate it. Fed
    the typed values the sag reproduces to **0.0725 mg/L**; applying the standard Streeter-Phelps
    temperature correction `k(T) = k(20) * theta^(T-20)` at this plume's 10 C makes it **17.6x
    worse** at `theta` = 1.047, and 10x worse at a gentler 1.024. Both are asserted here, so the
    target says the rate is untouched rather than merely that the fit is good.

    ⚠️ That the exe applies no correction is not a defect -- there is nowhere in the dialog to
    enter a reference temperature, so the typed rate is by construction the rate at the run's own
    temperature. It matters because a reader who assumes the usual convention will enter a 20 C
    rate and get a demand 60 % too large.
    """
    runs = [
        ("case26_farfield_bod_rates/ModelResults_1.dat", 20.0, 5.0, 0.23, 0.0),
        ("case26_farfield_bod_rates/ModelResults_2.dat", 20.0, 1.0, 0.23, 0.0),
    ]
    typed = _far_field_residual(traces=runs)
    for theta, least in ((1.047, 5.0), (1.024, 3.0)):
        factor = theta ** (10.0 - 20.0)
        corrected = _far_field_residual(
            traces=[(r, c, k * factor, n * factor, a) for r, c, k, n, a in runs]
        )
        if corrected < least * typed:
            raise AssertionError(
                f"theta {theta} is no longer clearly worse: {corrected} against {typed}"
            )
    return typed


#: case38's interval sweep. `(trace, effluent DO)`; the interval is read from the file.
_DO_SEEDING_RUNS = (
    ("i1_do2.dat", 2.0),
    ("i3_do2.dat", 2.0),
    ("i5_do2.dat", 2.0),
    ("i1_do5.dat", 5.0),
    ("i1_do10.dat", 10.0),
    ("i5_do10.dat", 10.0),
)

#: The dilution the exe reaches at **step 1** in case38's geometry, read off its interval-1 runs.
_STEP_ONE_DILUTION = 1.0200


def _do_accumulator_seed_spread() -> float:
    """Spread in the ambient DO implied by case38's first printed rows. 0.22 mg/L.

    ⭐⭐⭐ The measurement that settles where the exe's oxygen accumulator starts, and it needs no
    model at all -- only the first printed row of each run.

    Back the entrained ambient out of that row as `(DO_0 * D_0 - DO_e) / (D_0 - reference)`. Against
    a reference of `D` = 1 the answer is incoherent across the sweep: 0.011, 5.798, 6.959, 6.813.
    Against **step 1's dilution of 1.0200** it is one number -- 8.697, 8.656, 8.475 -- an ambient DO
    of about 8.5, recovered from three output intervals and two effluent seeds without being told
    it.

    So `DO * D = DO_e - IDOD` at **step 1**, with no entrained credit, and the integral runs from
    there. Every earlier DO trace printed every step, which is why "starts at the first printed
    row" and "starts at step 1" had been indistinguishable.

    ⚠️ The interval-1 runs are excluded from the spread: at those the reference and `D_0` coincide,
    so the ratio is 0/0 in all but rounding. They are asserted separately -- their `DO_0 * D_0` must
    reproduce the typed effluent DO -- which is the other half of the finding.
    """
    from plumes2.io.dat import read_dat

    directory = _CASES / "case38_do_interval_seeding"
    implied = []
    for name, effluent in _DO_SEEDING_RUNS:
        frame = read_dat(directory / name).nearfield
        steps = frame.index.to_numpy()
        first_dilution = float(frame["Dilutn"].to_numpy(dtype=np.float64)[0])
        product = float(frame["DO"].to_numpy(dtype=np.float64)[0]) * first_dilution
        if int(steps[1] - steps[0]) == 1:
            # The seed itself, exact and independent of the ambient.
            if abs(product - effluent) > 1e-3:
                raise AssertionError(f"{name}: step 1 prints {product}, not {effluent}")
            continue
        implied.append((product - effluent) / (first_dilution - _STEP_ONE_DILUTION))
    if len(implied) < 3:
        raise AssertionError(f"only {len(implied)} runs print past step 1")
    return float(np.ptp(implied))


def _effluent_ph_scale_gap() -> float:
    """Gap between case03's computed DIC endmember and our TA+pH speciation. 1.1 umol/kg.

    ⭐ case03 enters TA 4000 with **DIC 0**, so row 45's pairing makes the exe compute DIC from
    TA and pH -- and what it computes tells us which pH scale it read the 10.5 on. Backing the
    endmember out of the trace in concentration space (row 39's method) gives **1645.18**:

        entered TA 4000, free scale       1646.29     +1.11
        entered TA 4000, total            1608.14    -37.04
        entered TA 4000, seawater         1602.96    -42.22
        entered TA 4000, NBS              1669.96    +24.78
        scaled  TA 4108.4, free           1702.07    +56.89

    ⭐⭐ Two things at once, and the second is the sharper. The scale is **free**, by a factor of
    13 over its nearest rival. And the speciation runs on the **entered** TA, not the
    density-scaled one -- so row 46's `x rho/1000` is applied to entered values *after* the
    chemistry, which is why case03's computed DIC endmember comes out unscaled at 1645 while
    case04's *entered* DIC comes out scaled at 1689.

    ⚠️ case32 excludes NBS at S = 0, where free and total coincide because there is no sulfate.
    This run separates them, because its effluent is 35 psu.
    """
    import PyCO2SYS as pyco2

    frame = _dat("reference_cases/case03_macoma_carbonate/test2_TxtOutputs.dat").nearfield
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    printed = frame["DIC"].to_numpy(dtype=np.float64)
    design = np.column_stack([1.0 / dilution, (dilution - 1.0) / dilution])
    endmember = float(np.linalg.lstsq(design, printed, rcond=None)[0][0])

    def dic(alkalinity: float, scale: int) -> float:
        return float(
            pyco2.sys(
                par1=alkalinity,
                par2=10.5,
                par1_type=1,
                par2_type=3,
                salinity=35.0,
                temperature=10.0,
                opt_k_carbonic=10,
                opt_k_bisulfate=1,
                opt_pH_scale=scale,
            )["dic"]
        )

    ours = abs(dic(4000.0, 3) - endmember)
    for alkalinity, scale in ((4000.0, 1), (4000.0, 2), (4000.0, 4), (4108.4, 3)):
        if abs(dic(alkalinity, scale) - endmember) < 10.0 * ours:
            raise AssertionError(
                f"TA {alkalinity} on scale {scale} is no longer clearly worse than free"
            )
    return ours


def _uniform_ambient_collapse() -> float:
    """Worst gap between the exe's DO and the manual's eq 23, on a **uniform** ambient. 0.0078.

    ⭐ Row 222, and it is the reconciliation between this module and row 39's algebraic carbonate
    mixing rather than an argument about it. With `DO_a` constant the path integral reduces to eq
    23 exactly -- `integral(DO_a dD) = DO_a (D - D_0)` -- so the two readings that rows 214 and
    214b separate by 435x become the same expression, and the exe matches it to **0.0078 mg/L**
    past `D` > 5 on both of case25's uniform-ambient runs.

    Predicted in writing before those runs were made.
    """
    worst = 0.0
    for run in (2, 3):
        frame = _dat(f"reference_cases/case25_farfield_bod/ModelResults_{run}.dat").nearfield
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        printed = frame["DO"].to_numpy(dtype=np.float64)
        algebraic = 8.0 + (2.0 - 8.0) / dilution
        developed = dilution > 5.0
        worst = max(worst, float(np.max(np.abs((algebraic - printed)[developed]))))
    return worst


def _ambient_bod_conversion_residual() -> float:
    """Far-field residual when the **ambient** cBOD5 is converted to ultimate. 0.10 mg/L.

    ⭐ The ambient CSV carries a five-day figure and **no rate of its own**, so what the exe does
    with it is a real question: eqs 24-25 need a rate, and the only one available is the
    effluent's. Converting at the effluent's carbonaceous rate fits case25's ambient-BOD run to
    **0.1013 mg/L**; using the five-day figure raw misses by **2.6361**, a 26x separation.

    ⚠️ Visible only at a slow rate. At 5 /day the conversion factor `1 - exp(-5k)` is 1.000 to
    three decimals and the two readings coincide, which is why case26's runs cannot see this and
    case25's 0.23 /day can.
    """
    base = ("case25_farfield_bod/ModelResults_3.dat", 20.0, 0.23, 0.23, 500.0)
    converted = _far_field_residual(traces=[base])
    raw_equivalent = 500.0 * (1.0 - np.exp(-5.0 * 0.23))
    raw = _far_field_residual(traces=[(base[0], base[1], base[2], base[3], raw_equivalent)])
    if raw < 10.0 * converted:
        raise AssertionError(f"the raw five-day reading is no longer clearly worse: {raw}")
    return converted


def _far_field_demand_linearity() -> float:
    """Far-field residual at a cBOD5 of 1000, on the law fitted at 20. 3.3 mg/L on a 193 mg/L span.

    ⭐ **A 50x span in the typed load, and one law with a multiplier of exactly 1.** The
    experiment note that produced these runs proposed a 2x span; case27's run 7 went to 1000
    against the others' 20, which is far enough that any amplitude term would show. None does.

    The measurement asserts the sensitivity as well as the fit: halving or doubling the typed
    cBOD5 fed to the same model gives residuals of **96** and **195** mg/L, 29x and 59x worse, so
    the agreement is not a coincidence of a forgiving trace.

    ⚠️ 3.3 mg/L would be a poor result anywhere else; here the printed DO spans -185 to +8, so it
    is 1.7 % of the swing. Row 241 uses the same trace with the same 4 mg/L bar.
    """
    big = [("case27_farfield_bod_conversion/ModelResults_7.dat", 1000.0, 5.0, 0.1, 0.0)]
    ours = _far_field_residual(traces=big)
    for multiplier in (0.5, 2.0):
        scaled = [(r, c * multiplier, k, n, a) for r, c, k, n, a in big]
        if _far_field_residual(traces=scaled) < 20.0 * ours:
            raise AssertionError(f"a {multiplier}x load is no longer clearly worse")
    return ours


#: Traces whose two-endmember fit does not hold, each for a recorded reason. See `_endmember_fit`.
_ENDMEMBER_EXCEPTIONS = ("case06_macoma_arag_s36", "case09_macoma_single_port")


def _endmember_fit_residual() -> float:
    """Worst residual of a single (effluent, ambient) pair fitted to every printed row. 23 umol/kg.

    ⭐ TA and DIC mix conservatively, so one endmember pair must reproduce a whole trace through
    `(E + (D-1) A)/D`. Fitted in **concentration space** the pair is recovered without being told
    it: the ambient lands on 2900.5 / 2499.9 / 1799.0 / 1600.0 / 3000.0 / 2700.0 -- the entered
    chemistry tables -- and case03's effluent on **4110.2**, where row 46's `x rho/1000` predicts
    4107.8. An independent confirmation of that rule from a direction it was never fitted to.

    ⚠️ **The weighting is the measurement.** Fitting on `v*D` instead of `v` lets the
    high-dilution rows dominate and returns nonsense -- an effluent of 7407 for a 4000 input. That
    was my first attempt and it is recorded so nobody repeats it.

    ⚠️ Two traces are excluded by name: case09, whose `Omega < 1` NaN poisons everything after it
    (row 73), and case06, which misses by 149 and is **unexplained** -- not attributable to
    precipitation, since a rate-versus-residual correlation over the archive comes out at -0.22.
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    traces = 0
    for path in _archive_traces():
        if any(name in path.parent.name for name in _ENDMEMBER_EXCEPTIONS):
            continue
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if not {"TA", "DIC", "Dilutn"} <= set(frame.columns):
            continue
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        for column in ("TA", "DIC"):
            printed = frame[column].to_numpy(dtype=np.float64)
            usable = np.isfinite(dilution) & np.isfinite(printed) & (dilution > 0.0)
            if usable.sum() < 20:
                continue
            design = np.column_stack(
                [1.0 / dilution[usable], (dilution[usable] - 1.0) / dilution[usable]]
            )
            solution = np.linalg.lstsq(design, printed[usable], rcond=None)[0]
            worst = max(worst, float(np.max(np.abs(design @ solution - printed[usable]))))
        traces += 1
    if traces < 8:
        raise AssertionError(f"only {traces} chemistry traces fitted")
    return worst


def _borate_spread_under_lee() -> float:
    """Spread of the pH gap against case03 with **Lee 2010** borate. 0.0018 pH units.

    ⚠️ **The spread, not the mean.** A constant offset is the known CO2SYS divergence rows 35 and
    43 measure; what a *wrong borate parameterisation* produces is a gap that **varies** with
    salinity and alkalinity along the trace. So the spread is the discriminating quantity and the
    mean is not.

    Uppstrom 1974 -- what the exe's KSO4 = 1 nominally selects -- gives a spread of **0.01289**;
    Lee 2010 gives **0.00183**, seven times tighter, and cuts the worst gap from 0.02356 to
    0.00646. So the exe's borate behaves like Lee whatever its dialog says the option is.

    ⚠️ This is *not* a claim about which the exe intends. Row 126 records that KSO4 is a combined
    bisulfate-by-borate selector; row 128 is the measurement that the borate half is not the one
    option 1 advertises.
    """
    import PyCO2SYS as pyco2

    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    path = _CASES / "case03_macoma_carbonate/test2_TxtOutputs.dat"
    frame = read_dat(path).nearfield
    resolved = from_dat(
        read_dat(path), "case03", case=_case("reference_cases/case03_macoma_carbonate/test.prj")
    ).frame

    def spread(option: int) -> float:
        result = pyco2.sys(
            par1=frame["TA"].to_numpy(dtype=np.float64),
            par2=frame["DIC"].to_numpy(dtype=np.float64),
            par1_type=1,
            par2_type=2,
            salinity=resolved["salinity_psu"].to_numpy(dtype=np.float64),
            temperature=resolved["temperature_degC"].to_numpy(dtype=np.float64),
            opt_k_carbonic=10,
            opt_k_bisulfate=1,
            opt_total_borate=option,
        )
        gap = np.asarray(result["pH_total"], dtype=np.float64) - frame["pH"].to_numpy(
            dtype=np.float64
        )
        return float(np.ptp(gap))

    lee = spread(2)
    if spread(1) < 5.0 * lee:
        raise AssertionError("Uppstrom borate is no longer clearly looser than Lee")
    return lee


def _far_field_chemistry_gap() -> float:
    """Worst relative gap in `Omega` across case03's far-field chemistry table. 2.2 %.

    ⭐ The last parity block. The far-field table prints TA, DIC, pH, `OmegaC` and `OmegaA` over 23
    rows, so the same isolation the near field gets applies here: fed the exe's **own** TA and DIC,
    this measures the carbonate solver and not the Brooks spreading.

    ⚠️ Salinity and temperature are **not** printed in the far field and have to be reconstructed:
    the plume travels at its trapping depth, so both mix from the near-field endpoint toward the
    ambient at that depth as `FF` grows. The endpoint values come from the near-field frame and the
    ambient from the project. The reconstruction is why this carries a looser bar than row 43.

    ⭐ It agrees **better** than the near field -- 0.0064 pH and 2.2 % on `Omega` against 0.024 and
    3.5 % -- which is the expected direction: by the far field the plume has diluted to within
    0.007 psu of ambient, so the chemistry is nowhere near the pH 10 region where the exe's
    embedded CO2SYS and PyCO2SYS diverge most.

    Uses Lee 2010 borate, per row 128.
    """
    import PyCO2SYS as pyco2

    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    dat = read_dat(_CASES / "case03_macoma_carbonate/test2_TxtOutputs.dat")
    near, far = dat.nearfield, dat.farfield
    if far is None or "OmegaA" not in far.columns:
        raise AssertionError("case03's far field no longer prints chemistry")
    case = _case("reference_cases/case03_macoma_carbonate/test.prj")
    resolved = from_dat(dat, "case03", case=case).frame

    transition = float(near["Dilutn"].to_numpy(dtype=np.float64)[-1])
    depth = abs(float(near["Depth"].to_numpy(dtype=np.float64)[-1]))
    levels = case.ambient.levels
    depths = np.array([level.depth for level in levels], dtype=np.float64)
    ambient_salinity = float(
        np.interp(depth, depths, np.array([level.salinity for level in levels]))
    )
    ambient_temperature = float(
        np.interp(depth, depths, np.array([level.temperature for level in levels]))
    )
    spreading = far["Dilution"].to_numpy(dtype=np.float64) / transition
    salinity = (
        ambient_salinity + (float(resolved["salinity_psu"].iloc[-1]) - ambient_salinity) / spreading
    )
    temperature = (
        ambient_temperature
        + (float(resolved["temperature_degC"].iloc[-1]) - ambient_temperature) / spreading
    )

    result = pyco2.sys(
        par1=far["TA"].to_numpy(dtype=np.float64),
        par2=far["DIC"].to_numpy(dtype=np.float64),
        par1_type=1,
        par2_type=2,
        salinity=salinity,
        temperature=temperature,
        opt_k_carbonic=10,
        opt_k_bisulfate=1,
        opt_total_borate=2,
    )
    worst = 0.0
    for key, column in (("saturation_calcite", "OmegaC"), ("saturation_aragonite", "OmegaA")):
        ours = np.asarray(result[key], dtype=np.float64)
        theirs = far[column].to_numpy(dtype=np.float64)
        usable = np.isfinite(ours) & np.isfinite(theirs) & (theirs > 0.0)
        worst = max(worst, float(np.max(np.abs(ours[usable] - theirs[usable]) / theirs[usable])))
    return worst


def _generated_project_fidelity() -> float:
    """Worst difference between the exe's run of **our** project and its run of the shipped one. 0.

    ⭐⭐ **Phase 1's acceptance test, and it is stronger than a round trip.** `PythonGenerated.prj`
    was written by `plumes2.io.project.prj_from_case` from the upstream example **with no
    template** -- every value went out through the semantic model and back. The exe loaded it and
    ran it, and its near field is identical to the exe's run of the project it shipped with: 5
    shared columns over all 55 printed steps, worst difference **0.0**.

    ⚠️ That is a different claim from `.dat` round-tripping (row 18), which only shows we can
    re-render a file we parsed. This shows the **exe agrees** that our reconstruction of a case is
    the same case -- reader, model and writer together, judged by the program we are porting.
    """
    from plumes2.io.dat import read_dat

    ours = read_dat(_CASES / "case13_generated_example/PythonGenerated2.dat").nearfield
    theirs = read_dat(_EXAMPLE / "ModelResults_TxtOutputs.dat").nearfield
    shared = [column for column in ours.columns if column in theirs.columns]
    steps = ours.index.intersection(theirs.index)
    if len(shared) < 5 or len(steps) < 50:
        raise AssertionError(f"only {len(shared)} columns over {len(steps)} steps")
    return max(
        float(
            np.nanmax(
                np.abs(
                    ours.loc[steps, column].to_numpy(dtype=np.float64)
                    - theirs.loc[steps, column].to_numpy(dtype=np.float64)
                )
            )
        )
        for column in shared
    )


def _case02_dilution_mare() -> float:
    """Dilution MARE against case02, at the exe's own printed times. 0.86 %.

    ⚠️ Solved against **case03's** project, which case02 has none of its own to use. Safe here for
    the reason row 43 records: case02, case03 and case04 are bit-identical over every shared
    hydrodynamic column, so one project describes all three and this measurement covers rows 24,
    37 and 43's hydrodynamic halves at once.

    Sampled at the exe's `Time` values rather than step for step, because the step controller sets
    how long each step lasts (row 166) -- matching steps would compare different instants.

    ⚠️ **0.86 % is above the 0.5 % this row claims**, and in the same way row 17 was: the error is
    concentrated after the first trapping rather than spread evenly. The jet phase clears the bar
    (row 21 measures 0.46 % on case01); the whole-trace figure does not, on either case.
    """
    from plumes2.io.dat import read_dat

    frame = read_dat(_CASES / "case02_macoma_mgd/Macomatest1.dat").nearfield
    times = frame["Time"].to_numpy(dtype=np.float64)
    theirs = frame["Dilutn"].to_numpy(dtype=np.float64)
    usable = np.isfinite(times) & np.isfinite(theirs) & (theirs > 0.0)
    case = _case("reference_cases/case03_macoma_carbonate/test.prj")
    ours = _integrate_once(
        case,
        max_time=float(times[usable][-1]) + 1.0).sample(times[usable],
    ).dilution
    return float(np.mean(np.abs(ours - theirs[usable]) / theirs[usable]))


#: The Macoma traces that merge with the diffuser **square to the current**, so the effective
#: spacing equals the nominal one and `d/L` reads the trigger directly. Oblique runs are excluded
#: on purpose -- see `_merge_trigger_crossing`.
_SQUARE_MERGING_TRACES = (
    "case05_macoma_merging/test4_TxtOutputs.dat",
    "case06_macoma_arag_s36/test5_TxtOutputs.dat",
    "case07_macoma_s45_dense/test6_TxtOutputs.dat",
    "case08_macoma_shoreline/test7_TxtOutputs.dat",
    "case10_macoma_bottom_hit/test11_TxtOutputs.dat",
)


def _merge_trigger_crossing() -> float:
    """Worst distance from 1 of `d/L` at the merging banner, square-to-flow traces. 0.045.

    ⭐ The trigger itself: merging is declared when the printed diameter reaches the port spacing.
    Measured on the banner row **and** the row before it, so it is a crossing rather than a
    coincidence -- every one of these traces sits **below** 1 on the previous row and at or above
    it on the banner, and the measurement asserts that.

    ⚠️ **Scoped to diffusers square to the current, and that scope is the point.** Across the whole
    archive `d/L` at the banner runs 0.118 to 1.045, which looks like no rule at all until you
    notice the low readings are all oblique diffusers: the exe triggers on the **effective**
    spacing, `L |cos(psi)|`, not the nominal one (row 181). Including them here would measure the
    cosine correction and the trigger at once and resolve neither. Rows 205 and 181 take the
    oblique geometry on its own terms.

    ⚠️ The residual 0.045 is the output interval, not slack in the rule: these traces print every
    fifth step, so the true crossing lies between printed rows. case20's test32, printed every
    step, brackets it to 0.9990-1.0060 (row 191d's territory).
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    for relative in _SQUARE_MERGING_TRACES:
        parsed = read_dat(_CASES / relative)
        spacing = float(parsed.echoed_tables["Diffuser"]["Spacing"].iloc[0])
        banner = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
        )
        if banner is None or spacing <= 0.0:
            raise AssertionError(f"{relative} no longer merges")
        frame = parsed.nearfield
        steps = frame.index.to_numpy()
        position = int(np.flatnonzero(steps == banner)[0])
        if position == 0:
            raise AssertionError(f"{relative} merges on its first printed row")
        diameters = frame["P-dia"].to_numpy(dtype=np.float64)
        ratio = float(diameters[position]) / spacing
        previous = float(diameters[position - 1]) / spacing
        if not previous < 1.0 <= ratio:
            raise AssertionError(f"{relative}: {previous} then {ratio} does not cross 1")
        worst = max(worst, abs(ratio - 1.0))
    return worst


def _single_port_spacing_inertness() -> float:
    """Worst numeric difference between one-port runs at spacing 0, 5 and 1000 m. Zero.

    ⭐⭐⭐ The measurement behind rows 191o and 191p. `limspc_mid`'s geometry grows to 4.293 m
    against a 2.4 m port depth, so it is well past the limiting-spacing trigger -- and at an
    entered spacing of **0.00, 5.00 and 1000.00 m** it produces the same trace: crossing at step
    191, banner at 192, 576 rows, final dilution 65.213, all three.

    So the entered spacing is **inert** on a single port and the rule fires unconditionally. ⚠️
    Which makes the 3rd edition's own point-source recipe (p.61: set the spacing to 1000 m so
    "merging will not occur") fail in this exe -- the plume merges with itself anyway, and the
    user gets an entrainment suppression worth 2.3x to 6x that they cannot switch off.

    ⚠️ Compared on the **numbers**, not the bytes: the diffuser echo prints the spacing itself, so
    the files necessarily differ. That is the same "the file changes, the numbers do not" pattern
    as row 191l's column ordering.
    """
    from plumes2.io.dat import read_dat

    base = read_dat(_CASES / "case30_limiting_spacing_bracket/gap_1.dat").nearfield
    worst = 0.0
    for name in ("spacing5.dat", "spacing1000.dat"):
        other = read_dat(_CASES / "case39_single_port_spacing" / name).nearfield
        shared = [column for column in base.columns if column in other.columns]
        if len(shared) < 10 or len(other) != len(base):
            raise AssertionError(f"{name} is no longer comparable with gap_1")
        for column in shared:
            worst = max(
                worst,
                float(
                    np.nanmax(
                        np.abs(
                            base[column].to_numpy(dtype=np.float64)
                            - other[column].to_numpy(dtype=np.float64)
                        )
                    )
                ),
            )
    return worst


#: `(stopped at the surface, allowed to continue)`. Two independent pairs, five years of exe
#: releases apart -- case13/14 on the old build, case31 on the current one.
_SURFACE_STOP_PAIRS = (
    (
        "case13_generated_example/PythonGenerated2.dat",
        "case14_generated_nochem/PythonGenerated3.dat",
    ),
    ("case31_surface_stop_pair/surface_on.dat", "case31_surface_stop_pair/surface_off.dat"),
)


def _surface_stop_trajectory_gap() -> float:
    """Worst difference between a run stopped at the surface and one allowed on. Zero.

    ⭐ `stop_at_surface` changes **where the trace ends and nothing else**. Over their shared steps
    the two runs of each pair agree exactly -- 55 for case13/14, 275 for case31 -- and then one
    stops (275) while the other continues (476, 572).

    ⚠️ That is what licenses treating the switch as a **termination rule** in the port rather than
    as a physics option: nothing upstream of the surface depends on it, so a run made with it off
    can still be compared against one made with it on, up to the point the first one stops. Row
    258 is the case in point -- our 40 % endpoint gap on case13 was this flag mismatched, and the
    trajectory underneath agreed to 1.9 %.

    ⚠️ The switch is **session state**: case13 and case14 have byte-identical `.prj` files and stop
    differently, which is why it is recorded per case README rather than read from a project.
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    for stopped, continued in _SURFACE_STOP_PAIRS:
        first = read_dat(_CASES / stopped).nearfield
        second = read_dat(_CASES / continued).nearfield
        shared = [column for column in first.columns if column in second.columns]
        steps = first.index.intersection(second.index)
        if len(shared) < 5 or len(steps) < 50:
            raise AssertionError(f"{stopped} and {continued} are no longer comparable")
        if first.index[-1] >= second.index[-1]:
            raise AssertionError(f"{stopped} does not stop before {continued}")
        for column in shared:
            worst = max(
                worst,
                float(
                    np.nanmax(
                        np.abs(
                            first.loc[steps, column].to_numpy(dtype=np.float64)
                            - second.loc[steps, column].to_numpy(dtype=np.float64)
                        )
                    )
                ),
            )
    return worst


def _mirror_profile_gap() -> float:
    """Falling minus rising far-field DO at 500 m, averaged over case28's three pairs.

    The pairs differ in decay rate and IDOD, both of which cancel in the difference -- so a spread
    across them would mean the difference is measuring something it should not.
    """
    pairs = [(2, 3), (8, 9), (5, 6)]
    gaps = []
    for falling, rising in pairs:
        values = []
        for run in (falling, rising):
            far = _dat(
                f"reference_cases/case28_farfield_do_closeout/ModelResults_{run}.dat"
            ).farfield
            distance = far["Distance"].to_numpy(dtype=np.float64)
            oxygen = far["DO"].to_numpy(dtype=np.float64)
            values.append(float(oxygen[int(np.argmin(np.abs(distance - 500.0)))]))
        gaps.append(values[0] - values[1])
    assert max(gaps) - min(gaps) < 0.01, f"the pairs disagree: {gaps}"
    return float(np.mean(gaps))


def _implied_idod() -> float:
    """The immediate demand backed out of case28 run 7's accumulator at the last row.

    `DO*D = DO_e + integral((DO_a - IDOD) dD)` with a uniform `DO_a` of 8, inverted for IDOD.
    """
    frame = _dat("reference_cases/case28_farfield_do_closeout/ModelResults_7.dat").nearfield
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    printed = frame["DO"].to_numpy(dtype=np.float64)
    return float(
        (2.0 + 8.0 * (dilution[-1] - 1.0) - printed[-1] * dilution[-1]) / (dilution[-1] - 1.0)
    )


def _far_field_demand_spread() -> float:
    """The demand implied at the transition, spread over three geometries with the inputs fixed.

    Returns `max/min - 1`. Eq 28's `/D` requires 0.45 here; the exe gives 0.02.
    """
    demands = []
    for name in ("ModelResults_2.dat", "ModelResults_4.dat", "ModelResults_6.dat"):
        dat = _dat(f"reference_cases/case27_farfield_bod_conversion/{name}")
        near, far = dat.nearfield, dat.farfield
        dilution = float(near["Dilutn"].iloc[-1])
        factor = far["Dilution"].to_numpy(dtype=np.float64) / dilution
        days = far["Time"].to_numpy(dtype=np.float64) / 24.0
        printed = far["DO"].to_numpy(dtype=np.float64)
        mixing = 8.0 + (float(near["DO"].iloc[-1]) - 8.0) / factor
        # One free amplitude at the typed rate, past the rows where 0.001 cannot resolve the sag.
        implied = ((mixing - printed) * factor / (1.0 - np.exp(-0.23 * days)))[10:]
        demands.append(float(np.mean(implied)))
    return max(demands) / min(demands) - 1.0


def _csv_round_trip_fraction() -> float:
    """Fraction of archived CSV input tables that re-encode byte for byte.

    The `.prj` is only one of seven files a project is made of; the other six are these tables, and
    a project that round-trips while its ambient profile does not is not a round trip.
    """
    from plumes2.io.csv_tables import read_csv_table

    paths = sorted([*_EXAMPLE.glob("*.csv"), *_CASES.glob("*/*.csv")])
    exact = sum(
        read_csv_table(path).to_text().encode("ascii") == path.read_bytes() for path in paths
    )
    return exact / len(paths)


def _case09_nan_rows() -> float:
    """Rows of case09's trace where a *trajectory* column is NaN.

    Trajectory rather than any column, and the distinction is the finding: two earlier rows carry a
    NaN in `R_cal` alone, where the precipitation rate hits an undersaturated mineral (row 91's
    unguarded `(omega - 1)**N`). The chemistry goes bad ten steps before the trajectory does.
    """
    frame = _dat("reference_cases/case09_macoma_single_port/test9_TxtOutputs.dat").nearfield
    trajectory = ["Dilutn", "P-dia", "x-posn", "y-posn", "Depth"]
    return float(frame[trajectory].isna().any(axis=1).sum())


def _legacy_feet_rescale_error() -> float:
    """Worst error on the three quantities case00's foot-flagged project must rescale.

    2 ft spacing and 20.7 / 207 ft mixing-zone distances, all x 0.3048. ⚠️ `port_depth` is *not*
    among them -- it carries its own flag and stays 2 m -- which is why this checks named
    quantities rather than "every length".
    """
    case = _case("reference_cases/case00_macoma_legacy_fps/Macoma.prj")
    expected = {
        case.diffuser.port_spacing: 2.0 * 0.3048,
        case.mixing_zone.acute_distance: 20.7 * 0.3048,
        case.mixing_zone.chronic_distance: 207.0 * 0.3048,
    }
    return max(abs(ours - feet) for ours, feet in expected.items())


def _header_only_trace_rows() -> float:
    """Step rows in case00's header-only trace. Zero, and the echoed tables still parse."""
    parsed = _dat("reference_cases/case00_macoma_legacy_fps/ModelResults_Macoma1.dat")
    if set(parsed.echoed_tables) != {"Ambient", "Diffuser"}:
        raise AssertionError(f"the echoes should survive: got {sorted(parsed.echoed_tables)}")
    return float(len(parsed.nearfield))


def _mgd_flow_ratio() -> float:
    """How much the flow unit flag changes the physics for one unchanged typed number.

    case01 and case02 both type `0.005` and diverge completely, because one reads it as m3/s and
    the other as MGD. This is the ratio between those two readings.
    """
    from plumes2.units import MGD_TO_CUBIC_METRES_PER_SECOND

    return 1.0 / MGD_TO_CUBIC_METRES_PER_SECOND


def _echo_horizontal_angle() -> float:
    """The H-angle read from test20's diffuser echo, whose header carries a `( )` unit marker.

    A parser that let the empty unit marker shift the column mapping reads a neighbouring field
    here -- `Ports` is 25 and `V-angle` is 45, so a one-column slip is unmissable.
    """
    table = _dat("reference_cases/case16_oldbuild_angle_sweep/test20.dat").echoed_tables["Diffuser"]
    return float(table["H-angle"].iloc[0])


def _legacy_prj_lines() -> float:
    """Lines in case00's Dec-2025 project, which carries one plot flag where 2026 has four."""
    raw = (_CASES / "case00_macoma_legacy_fps/Macoma.prj").read_bytes().decode("ascii")
    return float(len(raw.split("\r\n")) - 1)


def _echo_rounding_loss() -> float:
    """Worst absolute information loss in a `.dat` diffuser echo, against the project it came from.

    The echo prints two decimals, so 0.0127 m becomes "0.01" and 0.005 m3/s becomes "0.01" -- the
    second is not even the same number to one significant figure. This is why track B writes
    full-precision CSVs from the `Results` object rather than reading anything back off a `.dat`.
    """
    echo = _dat("reference_cases/case18_zero_current_pair/test21.dat").echoed_tables["Diffuser"]
    case = _case("reference_cases/case18_zero_current_pair/test21.prj")
    return max(
        abs(float(echo["P-dia"].iloc[0]) - case.diffuser.port_diameter),
        abs(float(echo["Ttl-flo"].iloc[0]) - case.effluent.flow),
    )


def _shoreline_near_field_difference() -> float:
    """Worst difference between case05 and case08's near-field tables.

    The two runs differ only in a shoreline vector, so this is the measurement behind "the
    shoreline feature is inert". ⚠️ The *files* are not identical -- case05's far field is longer --
    so comparing bytes would report a difference that has nothing to do with the shoreline.
    """
    first = _dat("reference_cases/case05_macoma_merging/test4_TxtOutputs.dat").nearfield
    second = _dat("reference_cases/case08_macoma_shoreline/test7_TxtOutputs.dat").nearfield
    if list(first.columns) != list(second.columns) or len(first) != len(second):
        raise AssertionError("the two traces no longer have the same shape to compare")
    return max(
        float(
            np.nanmax(
                np.abs(
                    first[column].to_numpy(dtype=np.float64)
                    - second[column].to_numpy(dtype=np.float64)
                )
            )
        )
        for column in first.columns
    )


#: Projects written on purpose to sit below the manual's Froude threshold. Excluded from the
#: census in `_subcritical_archived_cases` so that an *accidental* sub-critical case still trips it.
#: Archived projects that are sub-critical **on purpose**, excluded by name so row 113 keeps its
#: alarm for the accidental ones. Each entry needs a reason, because every addition weakens the
#: census.
#:
#: * `subcritical_sinks.prj` -- written to sit at `F` = 0.0044 to separate "sub-critical is
#:   unusable" from "leaving the water column is unusable".
#: * `d0.28_dep2.0.prj` -- case30's limiting-spacing switch sweep widens the port at **fixed
#:   flow**, so the exit velocity and `F` fall out of the design rather than being chosen: 0.22 m
#:   gives 0.13 m/s and 0.50 m gives 0.026 m/s. `F` = 0.883 here. ⚠️ Its siblings at 0.30, 0.40
#:   `d0.22`, `d0.25` and `d0.28` are all archived with their GUI-saved projects and all three
#:   are here; the 0.30-0.50 m runs are further below 1 still and belong here the moment their
#:   projects are archived (they currently have `.dat` only).
_DELIBERATELY_SUBCRITICAL = frozenset(
    {"subcritical_sinks.prj", "d0.22_dep2.0.prj", "d0.25_dep2.0.prj", "d0.28_dep2.0.prj"}
)


def _subcritical_archived_cases() -> float:
    """Archived projects whose discharge fails the manual's §5.2.2 Froude check. Should be zero.

    ⚠️ **Deliberately sub-critical projects are excluded by name**, so the count keeps its alarm.
    case34's project was written to sit at `F` = 0.0045 and would otherwise make this row read as
    a warning about itself forever. ⚠️ case29's three runs are equally sub-critical and are *not*
    on the list, because their `.prj` was saved with a stale 0.013 m port diameter and computes as
    super-critical -- so this census has never actually seen them. That is a bookkeeping gap in the
    archive, not a pass.

    ⚠️ **Counting failures rather than reporting the minimum, and the difference matters.** The
    minimum is the more interesting number -- it is 2.01, case22 -- but pinning it would set the
    tolerance from what the code happens to produce, and would break every time the archive gained
    a case. A count against a threshold the *manual* supplies breaks only when a case actually
    fails the check, which is exactly when someone should look.
    """
    import warnings

    failures = 0
    for path in sorted(_CASES.glob("*/*.prj")):
        if path.name in _DELIBERATELY_SUBCRITICAL:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                case = _case(str(path.relative_to(_ROOT)).replace("\\", "/"))
            except Exception:
                continue
        failures += case.densimetric_froude_number() < 1.0
    return float(failures)


def _unit_flag_map_error() -> float:
    """Worst deviation from the decoded selector map, over the columns case00 demonstrates.

    ⚠️ **Flag 1 is the GUI's default, not SI**, and that is the whole subtlety. For a length the
    default happens to be metres, so 1 looks like "SI" -- but for flow it is **MGD**, and m3/s is
    flag 2. Reading 1 as "already SI" leaves a flow 22.8x wrong while every length still looks
    right, which is precisely the failure row 28 measures.
    """
    from plumes2.units import TableKind, unit_for

    expected = {
        (TableKind.DIFFUSER, "port_spacing", 1): 1.0,
        (TableKind.DIFFUSER, "port_spacing", 2): 0.3048,
        (TableKind.MIXING_ZONE, "acute_distance", 1): 1.0,
        (TableKind.MIXING_ZONE, "acute_distance", 2): 0.3048,
        (TableKind.MIXING_ZONE, "chronic_distance", 1): 1.0,
        (TableKind.MIXING_ZONE, "chronic_distance", 2): 0.3048,
        (TableKind.EFFLUENT, "flow", 1): 0.0438126,
        (TableKind.EFFLUENT, "flow", 2): 1.0,
    }
    return max(
        abs(unit_for(kind, column, flag).to_si - factor)
        for (kind, column, flag), factor in expected.items()
    )


def _selector_alignment_failures() -> float:
    """Table kinds whose selector-to-column offset disagrees with the decoded rule.

    ⚠️ **Three tables carry a leading selector and three do not.** Effluent, mixing-zone and
    ambient are offset by one; the diffuser is 1:1, and so are the ambient DO and chemistry tables,
    which carry no selector row at all. Getting an offset wrong reads a neighbouring column's unit,
    which is how a foot flag silently becomes a metre flag.
    """
    from plumes2.units import TableKind, selector_for_column

    offset_by_one = {TableKind.EFFLUENT, TableKind.MIXING_ZONE, TableKind.AMBIENT}
    failures = 0
    for kind in TableKind:
        expected = 1 if kind in offset_by_one else 0
        selectors = list(range(len(kind.column_names) + expected))
        for column_index in range(len(kind.column_names)):
            if selector_for_column(kind, selectors, column_index) != column_index + expected:
                failures += 1
    return float(failures)


def _alternate_unit_error() -> float:
    """Worst error over the three alternate dropdowns, each checked against its definition.

    Not against a trace: **no archived project selects any of them**, so these are conversions the
    port implements because the GUI offers them, checked against arithmetic rather than evidence.
    The affine one is the reason this is worth a target -- degF is the only unit here that is not a
    pure scale factor, so a codebase that assumes `value * factor` everywhere gets it silently
    wrong by the offset.
    """
    from plumes2.units import TableKind, convert_to_si

    return max(
        # 50 degF is exactly 10 degC: scale 5/9 and an offset, not a scale alone.
        abs(convert_to_si(TableKind.EFFLUENT, "temperature", 2, 50.0) - 10.0),
        # A per-second decay is 86400 per day.
        abs(convert_to_si(TableKind.AMBIENT, "decay_rate", 2, 1.0) - 86400.0),
        # A mass fraction needs the density to become a concentration: 1 kg/kg at 1024 kg/m3.
        abs(convert_to_si(TableKind.EFFLUENT, "pollutant", 2, 1.0, density=1024.0) - 1.024e6),
    )


def _pollutant_label_risk() -> float:
    """How wrong a flag-1 pollutant is if the wrong build's labelling is assumed.

    The Dec-2025 build labels selector 1 `kg/kg`; the 2026 build labels it `mg/L`. Same file, same
    flag, two readings -- and they differ by the density in mg/L, about a **million**. This target
    exists to keep that number in front of anyone reading the report, because the failure is
    silent: both readings produce a number, and only one is a concentration.
    """
    from plumes2.units import TableKind, convert_to_si

    as_concentration = convert_to_si(TableKind.EFFLUENT, "pollutant", 1, 1.0)
    as_mass_fraction = convert_to_si(TableKind.EFFLUENT, "pollutant", 2, 1.0, density=1024.0)
    return as_mass_fraction / as_concentration


def _prj_round_trip_fraction() -> float:
    """Fraction of archived `.prj` files that re-encode byte for byte."""
    from plumes2.io.prj import read_prj, write_prj

    paths = sorted([*_EXAMPLE.glob("*.prj"), *_CASES.glob("*/*.prj")])
    exact = 0
    for path in paths:
        original = path.read_bytes()
        temporary = path.with_suffix(".prj.validation-tmp")
        try:
            write_prj(read_prj(path), temporary)
            exact += temporary.read_bytes() == original
        finally:
            temporary.unlink(missing_ok=True)
    return exact / len(paths)


def _dat_round_trip_fraction() -> float:
    """Fraction of archived `.dat` traces that re-render byte for byte."""
    from plumes2.io.dat import format_dat, read_dat

    paths = _archive_traces()
    exact = 0
    for path in paths:
        raw = path.read_bytes()
        try:
            rendered = format_dat(read_dat(path)).encode("ascii")
        except Exception:
            continue
        exact += rendered == raw
    return exact / len(paths)


#: UNESCO (1983) Table A3.1, the canonical EOS-80 acceptance set: `(S, T, bars, density)`.
#: Reproduced here rather than imported from the tests because the registry has to stand alone --
#: `plumes2 validate` runs without pytest on the path.
_UNESCO_DENSITY = (
    (0.0, 5.0, 0.0, 999.96675),
    (0.0, 5.0, 1000.0, 1044.12802),
    (0.0, 25.0, 0.0, 997.04796),
    (0.0, 25.0, 1000.0, 1037.90204),
    (35.0, 5.0, 0.0, 1027.67547),
    (35.0, 5.0, 1000.0, 1069.48914),
    (35.0, 25.0, 0.0, 1023.34306),
    (35.0, 25.0, 1000.0, 1062.53817),
)

#: The same table's secant bulk modulus values, `(S, T, bars, K)`.
_UNESCO_BULK_MODULUS = (
    (0.0, 5.0, 0.0, 20337.80375),
    (0.0, 5.0, 1000.0, 23643.52599),
    (35.0, 5.0, 0.0, 22185.93358),
    (35.0, 5.0, 1000.0, 25577.49819),
    (35.0, 25.0, 0.0, 23726.34949),
)


def _eos_density_error() -> float:
    """Worst absolute error over all eight UNESCO density check values.

    ⚠️ All eight, not one. This target checked only S = 35, T = 25, p = 0 until 2026-08-18, while
    the ledger row beside it claimed eight -- so seven of them were asserted in a test and absent
    from the report that is supposed to be the evidence.
    """
    from plumes2.seawater import density

    return max(
        abs(float(density(salinity, temperature, bars * 10.0)) - expected)
        for salinity, temperature, bars, expected in _UNESCO_DENSITY
    )


def _bulk_modulus_error() -> float:
    """Worst absolute error over the five UNESCO secant-bulk-modulus check values.

    The pressure half of EOS-80. It barely matters for this project -- every reference case is
    shallower than 20 m and the exe reports sigma-t anyway -- but a wrong bulk modulus would be
    invisible at these depths and wrong everywhere else, which is exactly what a check value is for.
    """
    from plumes2.seawater import secant_bulk_modulus

    return max(
        abs(float(secant_bulk_modulus(salinity, temperature, bars * 10.0)) - expected)
        for salinity, temperature, bars, expected in _UNESCO_BULK_MODULUS
    )


def _exe_density_offset() -> float:
    """Mean signed difference between our EOS-80 plume density and the exe's `P-Den` column.

    Reconstructs the plume's salinity and temperature from the exe's own dilution and depth, so
    this isolates the equation of state from the trajectory. Negative means we run low.
    """
    from plumes2.seawater import density

    frame = _dat("reference_cases/case01_macoma_cms/ModelResults_TxtOutputs.dat").nearfield
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    depth = -frame["Depth"].to_numpy(dtype=np.float64)
    printed = frame["P-Den"].to_numpy(dtype=np.float64)

    # case01's ambient profile, and the effluent endmember it mixes toward.
    depths = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0]
    ambient_salinity = np.interp(depth, depths, [30.9, 31.2, 31.2, 31.7, 31.8, 31.9])
    ambient_temperature = np.interp(depth, depths, [11.2, 10.4, 9.69, 9.44, 9.34, 9.22])
    salinity = (35.0 + (dilution - 1.0) * ambient_salinity) / dilution
    temperature = (10.0 + (dilution - 1.0) * ambient_temperature) / dilution
    return float(np.mean(density(salinity, temperature) - printed))


def _extrapolation_clamp_error() -> float:
    """How far a query past the profile's deep end drifts from the last level's value.

    Zero: the ambient view clamps rather than extending. Extending case01's salinity gradient two
    metres past its last level is not hypothetical -- every Macoma project's seabed sits below its
    profile -- and a linear extension of a steep gradient is what drove case09 to negative values.
    """
    from plumes2.ambient import AmbientProfileView
    from plumes2.config import AmbientLevel, AmbientProfile

    profile = AmbientProfile(
        levels=[
            AmbientLevel(depth=1.0, salinity=30.9, temperature=11.2),
            AmbientLevel(depth=15.0, salinity=31.9, temperature=9.22),
        ]
    )
    view = AmbientProfileView(profile)
    beyond = max(
        abs(float(view.salinity(np.array([40.0]))[0]) - 31.9),
        abs(float(view.temperature(np.array([40.0]))[0]) - 9.22),
    )
    above = max(
        abs(float(view.salinity(np.array([0.0]))[0]) - 30.9),
        abs(float(view.temperature(np.array([0.0]))[0]) - 11.2),
    )
    return max(beyond, above)


def _subcritical_runs_that_survive() -> float:
    """case29 runs whose trace stays finite past the row where the plume leaves the water column.

    Zero: all three go NaN the row after crossing depth zero, and stay NaN to the 5001-step cap.
    Measured as a count of *survivors* so the target reads as "the exe cannot run these", which is
    the claim -- and so adding a sub-critical case that does work would fail it loudly.
    """
    survivors = 0
    for name in ("test41", "test42", "test43"):
        frame = _dat(f"reference_cases/case29_subcritical_froude/{name}.dat").nearfield
        finite = frame.dropna()
        if len(finite) == len(frame):
            survivors += 1
            continue
        depth = -finite["Depth"].to_numpy(dtype=np.float64)
        if not (depth < 0.0).any():
            raise AssertionError(f"{name}: went NaN without ever crossing the surface")
    return float(survivors)


#: Plume salinity above which the sigma-t offset is flat. Below it the two polynomials diverge --
#: see `_eos_offset_salinity_correlation`, and case29, which is the first archive trace to go fresh.
_SEAWATER_SALINITY = 28.0

#: Where the density offset is actually **flat**. ⚠️ Not the same thing as "seawater": the offset
#: is salinity-dependent (see `_eos_offset_salinity_correlation`), and over 28-33 psu it still
#: drifts 0.0049 kg/m3. From 31 up it is 0.0019 over 33 traces -- and pushing the edge to 31.5
#: widens it again to 0.0035, so this is a plateau the archive can see rather than a threshold
#: tuned until a number fell inside a tolerance.
_FLAT_OFFSET_SALINITY = 31.0


def _eos_offset_samples(*, seawater_rows_only: bool = False) -> list[tuple[float, float]]:
    """`(mean plume salinity, mean density offset)` for every trace printing `P-Sal` and `P-Temp`.

    ⚠️ `seawater_rows_only` restricts each trace to its rows **at or above** `_FLAT_OFFSET_SALINITY`
    before averaging. Selecting whole traces by their mean was enough while every trace lived
    near 31 psu; case31 discharges fresh water into 32 psu and sweeps the whole range, so its
    mean lands in the seawater band while a third of its rows do not. Since the offset is
    salinity-dependent (see `_eos_offset_salinity_correlation`), that mixes two regimes into one
    number -- it moved row 147's spread from 0.0026 to 0.0062.

    ⭐ The clean measurement, and better than row 101's: fed the exe's **own** printed salinity and
    temperature, it isolates the equation of state from the mixing, the ambient interpolation and
    the trajectory. Row 101 reconstructs S and T from dilution and gets -0.036; this gets -0.0275 in
    the same regime, and the difference between them is everything that is not the EOS.
    """
    from plumes2.seawater import density

    samples = []
    for path in _archive_traces():
        try:
            frame = _dat(str(path.relative_to(_ROOT)).replace("\\", "/")).nearfield
        except Exception:
            continue
        if not {"P-Sal", "P-Temp", "P-Den"} <= set(frame.columns):
            continue
        salinity = frame["P-Sal"].to_numpy(dtype=np.float64)
        temperature = frame["P-Temp"].to_numpy(dtype=np.float64)
        printed = frame["P-Den"].to_numpy(dtype=np.float64)
        usable = np.isfinite(salinity) & np.isfinite(temperature) & np.isfinite(printed)
        if usable.sum() < 50:
            continue
        if seawater_rows_only:
            usable &= salinity >= _FLAT_OFFSET_SALINITY
            if usable.sum() < 50:
                continue
        offset = density(salinity[usable], temperature[usable]) - printed[usable]
        samples.append((float(np.mean(salinity[usable])), float(np.mean(offset))))
    return samples


def _eos_offset() -> float:
    """The offset in the seawater range, where the archive measured it."""
    return float(np.mean([o for _s, o in _eos_offset_samples(seawater_rows_only=True)]))


def _eos_offset_spread() -> float:
    """How far the offset moves between seawater-range traces -- row 147, over 28 rather than 2."""
    offsets = [o for _s, o in _eos_offset_samples(seawater_rows_only=True)]
    if len(offsets) < 20:
        raise AssertionError(f"only {len(offsets)} seawater-range traces; expected more")
    return max(offsets) - min(offsets)


def _eos_offset_salinity_correlation() -> float:
    """Correlation between a trace's mean plume salinity and its density offset.

    ⚠️ **The offset is not a constant, and the archive could not see that until case29.** Every
    trace before it had a plume near 31 psu, where the offset is a flat -0.0275; case29's near-fresh
    plumes sit at -0.040, and within one of them the offset runs -0.063 at S = 0 to -0.029 at
    S = 31. That is what a *different polynomial* looks like -- the two agree where seawater lives
    and separate away from it -- rather than a constant bias.
    """
    samples = _eos_offset_samples()
    salinity = np.array([s for s, _o in samples])
    offset = np.array([o for _s, o in samples])
    return float(np.corrcoef(salinity, offset)[0, 1])


def _density_depth_dependence() -> float:
    """Largest `P-Den` spread among archived rows that share an exact printed salinity *and*
    temperature but sit at different depths.

    ⭐ **This tests pressure-independence without needing the polynomial.** If the exe's density
    depended on depth, two rows with identical `(S, T)` at different depths would print different
    densities. Over the widest such pair the archive offers -- 0.89 m apart -- an EOS-80-style
    pressure term would move the density by about 0.004 kg/m3, four times what three printed
    decimals resolve. The exe prints the same value.

    ⚠️ It bounds the pressure term at four times the printed resolution, not to zero. A weaker
    depth dependence than EOS-80's would hide here, and the archive has nothing deeper to offer:
    every trace lives between 1 and 9 m, and the plume does not revisit an `(S, T)` across that
    span.
    """
    import collections

    from plumes2.io.dat import read_dat

    seen: dict[tuple[float, float], list[tuple[float, float]]] = collections.defaultdict(list)
    for path in _archive_traces():
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if not {"P-Sal", "P-Temp", "P-Den"} <= set(frame.columns):
            continue
        columns = [frame[name].to_numpy(dtype=np.float64) for name in ("P-Sal", "P-Temp", "P-Den")]
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        usable = np.all(np.isfinite(columns), axis=0) & np.isfinite(depth)
        for index in np.where(usable)[0]:
            salinity, temperature, printed = (column[index] for column in columns)
            seen[(salinity, temperature)].append((depth[index], printed))

    worst = 0.0
    widest = 0.0
    for entries in seen.values():
        if len(entries) < 2:
            continue
        depths = [z for z, _d in entries]
        span = max(depths) - min(depths)
        if span < 0.5:  # below this the pressure signal is under the printed resolution anyway
            continue
        widest = max(widest, span)
        densities = [d for _z, d in entries]
        worst = max(worst, max(densities) - min(densities))
    if widest < 0.5:
        raise AssertionError("no (S, T) pair spans enough depth to test pressure dependence")
    return worst


# ⚠️ **There is deliberately no "adding pressure makes it worse" target for row 159.** It was
# written and then removed: on test23 the in-situ density agrees with the exe *better* than the
# zero-pressure one (ratio 0.633), which looks like evidence against the reference's statement that
# UM's sigma-t is pressure-independent. It is not evidence either way. Our zero-pressure density is
# 0.027 low and the pressure term adds about +0.009 at 2 m, so it cancels part of an unrelated
# offset. Row 159's claim is an attribution to Teeter & Baumgartner (1979) -- a paper this project
# does not hold -- and the 3rd edition states it in prose (p. 124) without printing the polynomial.
# It stays prose until someone has that paper.


def _buoyancy_left_at_trapping() -> float:
    """Ambient-minus-plume density at the end of test23, where the offset has to be judged.

    Row 148's point: a fixed 0.0275 kg/m3 offset is 0.9 % of the buoyancy at the port and **283 %**
    of what survives at trapping. The offset does not grow; the quantity it is compared against
    collapses, which is why late-trajectory drift tracks it.
    """
    from plumes2.ambient import AmbientProfileView
    from plumes2.seawater import density

    case = _case("reference_cases/case18_zero_current_pair/test21.prj")
    frame = _dat("reference_cases/case18_zero_current_pair/test23.dat").nearfield
    depth = -frame["Depth"].to_numpy(dtype=np.float64)
    view = AmbientProfileView(case.ambient)
    ambient = density(view.salinity(depth), view.temperature(depth))
    plume = density(
        frame["P-Sal"].to_numpy(dtype=np.float64), frame["P-Temp"].to_numpy(dtype=np.float64)
    )
    return abs(float((ambient - plume)[-1]))


def _reduced_gravity_reference_gap() -> float:
    """Fractional difference between the ambient- and plume-referenced reduced gravities.

    Exactly `rho_p / rho_a - 1`. ⭐ The 3rd edition settles which belongs in the momentum equation:
    p. 124 writes it as `((rho_a - rho)/rho) g` -- the **plume** reference, which is what the solver
    uses. `seawater.reduced_gravity` is the ambient-referenced Froude/Richardson convention and is
    documented as not for the momentum equation; this measures how much that choice is worth.
    """
    from plumes2.seawater import GRAVITY, reduced_gravity

    plume, ambient = 1026.96, 1023.81  # case01's first row against its ambient
    ambient_referenced = float(reduced_gravity(plume, ambient))
    plume_referenced = GRAVITY * (ambient - plume) / plume
    return abs(ambient_referenced / plume_referenced - 1.0)


def _standalone_farfield_gap() -> float:
    """Worst absolute dilution difference against the exe's independent Brooks calculator.

    ⭐ The decisive Brooks test, and the only one in this registry with **no near-field involved**:
    the initial width and dilution are typed in by the user, so nothing depends on our trajectory.
    It therefore separates the Brooks equations from the near-field handoff completely.
    """
    from plumes2.config import EddyDiffusivityLaw
    from plumes2.farfield.standalone import StandaloneRequest, independent_farfield

    request = StandaloneRequest(
        initial_dilution=100.0,
        initial_width=50.0,
        mixing_zone_distance=200.0,
        current_speed=0.05,
        initial_location=0.001,
        alpha=3.0e-4,
        law=EddyDiffusivityLaw.FOUR_THIRDS,
    )
    trace = _CASES / "case17_independent_farfield/IndpFarfieldCalc1.TXT"
    text = trace.read_text(encoding="ascii")
    reported = np.array(
        [
            [float(token) for token in line.split()]
            for line in text.splitlines()
            if len(line.split()) == 5 and re.fullmatch(r"\d+\.\d+", line.split()[0])
        ]
    )
    ours = independent_farfield(request)["dilution"].to_numpy(dtype=float)
    return float(np.max(np.abs(ours - reported[:, 1])))


@cache
def _case03_chemistry():  # type: ignore[no-untyped-def]
    """case03's trace re-solved from **the exe's own TA and DIC**.

    Going through `plotframe.from_dat` rather than through a run of our own is deliberate: it feeds
    our chemistry the exe's printed TA and DIC, so the comparison isolates the carbonate solver from
    the hydrodynamics. A run-against-run comparison would fold our 0.5-1 % dilution error into it
    and the result would measure both at once.
    """
    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    directory = _CASES / "case03_macoma_carbonate"
    case = _case("reference_cases/case03_macoma_carbonate/test.prj")
    return from_dat(read_dat(directory / "test2_TxtOutputs.dat"), "case03", case=case).frame


#: case04 is bit-identical to case03 hydrodynamically and has no `.prj` of its own, so it is
#: solved against case03's. That is safe here and nowhere else: the comparison is fed the exe's
#: **printed** TA and DIC, so what was typed into the chemistry dialog -- TA+pH for case03,
#: TA+DIC for case04 -- never enters the calculation.
_CHEM_PARITY_TRACES = (
    "case03_macoma_carbonate/test2_TxtOutputs.dat",
    "case04_macoma_ta_dic/test3_TxtOutputs.dat",
)


def _calcite_saturation_gap() -> float:
    """Worst relative gap between our `Omega_calcite` and the exe's, over both chem traces. 3.5 %.

    The column rows 35 and 41 leave uncovered. Fed the exe's own TA and DIC through
    `plotframe.from_dat`, exactly as `_case03_chemistry` is, so this isolates the carbonate solver
    from the hydrodynamics -- a run-against-run comparison would fold our 0.5-1 % dilution error in
    and measure both at once.

    It is the same divergence rows 35 and 41 report from the pH and aragonite sides: the exe's
    embedded CO2SYS sits about 0.024 pH units below PyCO2SYS near pH 10, and `Omega` follows.
    Reporting it on calcite too is what shows the gap is in the speciation rather than in either
    mineral's solubility -- row 123 has those agreeing to the last bit.
    """
    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    case = _case("reference_cases/case03_macoma_carbonate/test.prj")
    worst = 0.0
    rows = 0
    for relative in _CHEM_PARITY_TRACES:
        frame = from_dat(read_dat(_CASES / relative), relative, case=case).frame
        ours = frame["omega_calcite"].to_numpy(dtype=np.float64)
        theirs = frame["omega_calcite_exe"].to_numpy(dtype=np.float64)
        usable = np.isfinite(ours) & np.isfinite(theirs) & (theirs > 0.0)
        worst = max(worst, float(np.max(np.abs(ours[usable] - theirs[usable]) / theirs[usable])))
        rows += int(usable.sum())
    if rows < 70:
        raise AssertionError(f"only {rows} rows compared")
    return worst


def _endmember_alkalinity() -> float:
    """The effluent TA the exe actually mixes, from an entered 4000 umol/kg."""
    from plumes2.chem.transport import effluent_endmember

    case = _case("reference_cases/case03_macoma_carbonate/test.prj")
    settings = case.carbonate.model_copy(update={"reproduce_effluent_concentration_scaling": True})
    return float(
        effluent_endmember(
            EffluentChemistry(total_alkalinity=4000.0, ph=10.5),
            case.effluent.salinity,
            case.effluent.temperature,
            settings=settings,
        ).total_alkalinity
    )


#: case01's event steps, from its own banners (PLAN.md row 20). The jet phase is everything before
#: the first local maximum; the late phase is everything after the first trapping.
CASE01_FIRST_MAX_RISE = 270
CASE01_FIRST_TRAP = 335

_CASE01_TRACE = "reference_cases/case01_macoma_cms/ModelResults_TxtOutputs.dat"
_CASE01_PROJECT = "reference_cases/case01_macoma_cms/Macoma2.prj"


def _case01_mare(column: str, ours: str, window: str) -> float:
    """Mean absolute relative error against case01, over one phase of the trajectory.

    Windowed rather than whole-trace because the error is **not** uniform along the path, and a
    single number hides that -- see the ledger-correcting note on row 17 below.
    """
    frame = _dat(_CASE01_TRACE).nearfield
    times = frame["Time"].to_numpy(dtype=float)
    steps = frame.index.to_numpy()
    masks = {
        "jet": steps < CASE01_FIRST_MAX_RISE,
        "late": steps >= CASE01_FIRST_TRAP,
        "all": np.ones_like(steps, dtype=bool),
    }
    mask = masks[window]
    theirs = frame[column].to_numpy(dtype=float)
    sampled = _run(_CASE01_PROJECT).solution.sample(times)
    mine = {"dilution": sampled.dilution, "diameter": sampled.diameter}[ours]
    keep = mask & np.isfinite(theirs) & (theirs != 0.0)
    return float(np.mean(np.abs(mine[keep] - theirs[keep]) / np.abs(theirs[keep])))


#: case18's zero-current pair and case19's cross-flow sweep share one project, `test21.prj`, with
#: a single field changed per run. Reproducing that here rather than importing it from the tests is
#: deliberate: the registry has to stand alone, because `plumes2 validate` runs without pytest.
_SWEEP_PROJECT = "reference_cases/case18_zero_current_pair/test21.prj"

#: `(trace, ambient current)`. test23 is the zero-current control and lives in case18; the rest are
#: case19's sweep. All are one port at a hundredth of the baseline flow.
_SWEEP_RUNS = {
    "test23": (0.0, "case18_zero_current_pair"),
    "test28": (0.01, "case19_current_sweep"),
    "test27": (0.02, "case19_current_sweep"),
    "test29": (0.05, "case19_current_sweep"),
    "test30": (0.10, "case19_current_sweep"),
}

#: The step at which test23 first stops rising. The jet phase is everything before it -- the window
#: upstream's 0.5 % bar is quoted against, and the one least entangled with termination.
_TEST23_FIRST_MAX_RISE = 223


@cache
def _sweep_case(current: float) -> Case:
    """`test21.prj` reduced to one port at 5e-5 m3/s, with the ambient current overridden."""
    case = _case(_SWEEP_PROJECT)
    levels = [level.model_copy(update={"current_speed": current}) for level in case.ambient.levels]
    return case.model_copy(
        update={
            "diffuser": case.diffuser.model_copy(update={"n_ports": 1}),
            "effluent": case.effluent.model_copy(update={"flow": 5.0e-5}),
            "ambient": case.ambient.model_copy(update={"levels": levels}),
        }
    )


@cache
def _sweep_jet_mare(run: str, *, published_closure: bool = False) -> float:
    """Jet-phase dilution MARE against one sweep trace, at the exe's own printed times.

    The comparison is at the exe's `Time` values rather than step-for-step because the step
    controller sets how long each step takes (row 166) -- so matching steps would compare different
    instants. `published_closure` swaps UM3's entrainment for the 3rd edition's literal PAE, which
    is what makes the ratio in row 171 meaningful rather than an unbounded claim.
    """
    from plumes2.io.dat import read_dat
    from plumes2.nearfield.entrainment import ProjectedAreaEntrainment, Um3Entrainment
    from plumes2.nearfield.solver import integrate

    current, directory = _SWEEP_RUNS[run]
    parsed = read_dat(_ROOT / f"reference_cases/{directory}/{run}.dat")
    frame = parsed.nearfield
    if run == "test23":
        jet = frame.index.to_numpy() < _TEST23_FIRST_MAX_RISE
    else:
        # The first event the exe announces ends the jet phase. Events carry `next_step = None`
        # when they are terminal, and a terminal-only trace would leave no jet window at all.
        starts = [event.next_step for event in parsed.events if event.next_step is not None]
        if not starts:
            raise ValueError(f"{run}: no event marks the end of the jet phase")
        jet = frame.index.to_numpy() < min(starts)
    frame = frame[jet]

    times = frame["Time"].to_numpy(dtype=np.float64)
    theirs = frame["Dilutn"].to_numpy(dtype=np.float64)
    closure = ProjectedAreaEntrainment() if published_closure else Um3Entrainment()
    ours = integrate(_sweep_case(current), forced=closure, max_time=float(times[-1]) + 1.0)
    return float(np.mean(np.abs(ours.sample(times).dilution - theirs) / theirs))


#: Every current-build trace that printed a far field, with the ambient current its run used.
#: ⚠️ The current is not in the `.dat` -- it comes from the project -- so it is tabulated here.
_FARFIELD_TRACES = (
    ("case02_macoma_mgd/Macomatest1.dat", 0.02),
    ("case05_macoma_merging/test4_TxtOutputs.dat", 0.02),
    ("case06_macoma_arag_s36/test5_TxtOutputs.dat", 0.02),
    ("case07_macoma_s45_dense/test6_TxtOutputs.dat", 0.02),
    ("case10_macoma_bottom_hit/test11_TxtOutputs.dat", 0.02),
    ("case12_macoma_shoreline_enabled/test13_TxtOutputs.dat", 0.02),
    ("case13_generated_example/PythonGenerated2.dat", 0.05),
    ("case14_generated_nochem/PythonGenerated3.dat", 0.05),
)


def _is_old_build(path: Path) -> bool:
    """Traces from the pre-2026 exe, which predates the wastefield-width cosine correction.

    ⚠️ **Per file, not per directory.** case31 holds one trace from each build in the same
    folder -- that is the point of the case, since it is what shows the near field is identical
    across them -- so a directory-level rule silently classified the old-build half as current
    and put row 96 13.6 m out.
    """
    # ⭐ A naming rule, not only a list: a trace whose filename says `legacy` is one. Three
    # separate runs have now landed as old-build files inside current-build folders, each time
    # failing row 96 by ~13.6 m until someone added the name here, so new runs should carry the
    # build in the name and classify themselves.
    if "legacy" in path.name.lower():
        return True
    if path.name in {
        "surface_off.dat",
        # ⚠️⚠️ case13's 2026-08-20 reruns are **old build**, in a folder whose archived trace is
        # current build. Same project, two builds, two wastefield widths: PythonGenerated2 prints
        # 96.29 m (cosine-corrected) and these print 109.59 m (uncorrected) -- a 13.30 m gap that
        # is exactly the correction on an 18-port, 6.10 m, 30-degree diffuser. Row 96 failed by
        # 13.61 m the moment they were archived, which is the *second* time a directory-level rule
        # has mixed builds in one folder and produced this same signature.
        "interval1_rise2.dat",
        "interval1_rise3.dat",
    }:
        return True
    return path.parent.name in {
        "Example_project",
        "case00_macoma_legacy_fps",
        "case15_oldbuild_angle45",
        "case16_oldbuild_angle_sweep",
        # ⚠️⚠️ **The 2026-08-21 generated sessions, and this is the fourth recurrence of the
        # signature this function's docstring predicts.** Every trace in these four cases reads a
        # span factor of ~1.0 -- no cosine -- so they are this build, not the cosine-applying one.
        # case45's bearing sweep is what established it: flat at 0.986-1.000 across 0 to 45
        # degrees, where a cosine would give 0.866 at 30 and 0.707 at 45.
        #
        # ⚠️ These four are listed by **directory** despite the warning above, and that is safe
        # only because each is homogeneous -- one operator, one exe, one sitting. The warning is
        # about folders holding traces from *both* builds, which case13 and case31 do and these do
        # not. If a trace from another build is ever added to one of these folders, move it to the
        # per-file list above rather than widening this one.
        "case42_matched_dilution",
        "case43_port_count",
        "case44_spacing_sweep",
        "case45_bearing_sweep",
    }


def _old_build_width_gap() -> float:
    """How far the shipped example's printed wastefield width sits from the current-build law.

    Row 98: the upstream example prints **109.59 m** where the same geometry under the current
    build gives 96.29. The cosine correction was evidently added between releases, and this is the
    single number that says so -- it is why the example's far-field block cannot be used as a
    target for anything downstream of the width.
    """
    from plumes2.io.dat import read_dat

    parsed = read_dat(_EXAMPLE / "ModelResults_TxtOutputs.dat")
    diffuser = parsed.echoed_tables["Diffuser"]
    ambient = parsed.echoed_tables["Ambient"]
    diameter = float(parsed.nearfield["P-dia"].iloc[-1])
    offset = float(diffuser["H-angle"].iloc[0]) - float(ambient["Amb-dir"].iloc[0])
    span = (int(diffuser["Ports"].iloc[0]) - 1) * float(diffuser["Spacing"].iloc[0])
    ours = span * abs(math.cos(math.radians(offset))) + diameter
    return abs(float(parsed.wastefield_width or math.nan) - ours)


@cache
def _legacy_farfield_width_mare() -> float:
    """Our legacy far-field width against the exe's printed column, past 50 m. **0.126 %**.

    ⭐⭐⭐ Row 263c, and it is the first time a far field has been **predicted** from a case rather
    than reproduced from a trace. Section 7.24 blocked that: the exe echoes a geometric width and
    starts Brooks from a larger one, row 256 showed the mechanism is a virtual origin upstream, and
    `_handoff_width_adjustment` records that the origin "cannot be computed from a case -- only from
    a trace that already contains the answer."

    On the **legacy** build there is nothing to compute. The echoed width and the far-field starting
    width agree to 0.02 % on all four legacy traces, against up to 44 % on current-build ones, so
    the adjustment is zero, the virtual origin is zero, and `w0` is the geometric width that
    `results.run` already passes.

    ⚠️ **The dilution is a different story and it is not Brooks's fault.** It runs 6.06 % low, and
    that is entirely the near-field endpoint: ours ends at 159.223 against the exe's 169.754, which
    is -6.20 %, and the far-field error is -6.20 % at the handoff drifting only to -5.90 % at 493 m.
    The exe's own value at surface *contact* is 156.331, so 169.754/156.331 = **+8.59 %** is row
    258b's unexplained 14-step overshoot, and 1.0185/1.0859 = 0.938 closes the arithmetic. Closing
    258b would close this.

    ⚠️ Requires `stop_at_surface` and `max_rise_or_fall = 2` -- row 258's correction. Without them
    our near field sails through the surface and the endpoint is 40 % out, which is what that row
    spent days on.
    """
    from plumes2.config import ExeBuild
    from plumes2.results import run

    parsed = _dat("reference_cases/case13_generated_example/interval1_rise2.dat")
    far = parsed.farfield
    if far is None or len(far) < 100:
        raise AssertionError("the legacy far field is missing or truncated")

    base = _case("reference_cases/case13_generated_example/PythonGenerated.prj")
    case = base.model_copy(
        update={
            "near_field": base.near_field.model_copy(
                update={"stop_at_surface": True, "max_rise_or_fall": 2}
            ),
            "far_field": base.far_field.model_copy(update={"exe_build": ExeBuild.LEGACY}),
        }
    )
    ours = run(case, samples=400).farfield
    if ours is None or not len(ours):
        raise AssertionError("our run produced no far field")

    theirs_x = far["Distance"].to_numpy(dtype=np.float64)
    theirs_x = theirs_x - theirs_x[0]
    theirs_w = far["Width"].to_numpy(dtype=np.float64)
    our_x = ours["distance_m"].to_numpy(dtype=np.float64)
    our_x = our_x - our_x[0]
    our_w = ours["width_m"].to_numpy(dtype=np.float64)

    developed = theirs_x > 50.0
    predicted = np.interp(theirs_x[developed], our_x, our_w)
    return float(np.mean(np.abs(predicted - theirs_w[developed]) / theirs_w[developed]))


def _legacy_wastefield_width_error() -> tuple[float, float]:
    """`(legacy law error, cosine law error)`, worst over every legacy-build trace. **0.59, 13.61**.

    Row 263, and it exists because the legacy build stopped being history. Far-field work uses it
    -- it offers more output columns -- so the port has to reproduce *its* width law, not only the
    2026 one row 96 covers. Row 98 records that the two builds disagree; this records that the
    uncorrected law is what the legacy build computes.

        legacy:  (n - 1) * spacing + diameter          -- no angular factor at all
        current: (n - 1) * spacing * |cos| + diameter  -- row 96, exact to 0.005 m

    On the four legacy traces the legacy law is worst by **0.59 m** and the cosine law by
    **13.61 m**, a factor of 23. The same project gives 96.29 m current and 109.59 m legacy.

    ⚠️ **0.59 m is not 0.005 m, and the residual has a known home.** The span is right; the
    *diameter* the exe adds is not the last printed row -- 109.59 implies 5.890 m where the trace
    ends at 6.481. That is section 7 item 22, still open, and it caps this law at about 0.5 %
    rather than exact. The tolerance says so instead of hiding it.
    """
    from plumes2.io.dat import read_dat

    legacy_worst = 0.0
    cosine_worst = 0.0
    seen = 0
    for path in _archive_traces():
        if not _is_old_build(path):
            continue
        parsed = read_dat(path)
        echoed = parsed.wastefield_width
        if echoed is None or not math.isfinite(echoed):
            continue
        diffuser = parsed.echoed_tables["Diffuser"]
        ambient = parsed.echoed_tables["Ambient"]
        diameter = parsed.nearfield["P-dia"].dropna()
        if diameter.empty:
            continue
        final = float(diameter.iloc[-1])
        span = (int(diffuser["Ports"].iloc[0]) - 1) * float(diffuser["Spacing"].iloc[0])
        offset = float(diffuser["H-angle"].iloc[0]) - float(ambient["Amb-dir"].iloc[0])
        legacy_worst = max(legacy_worst, abs(echoed - (span + final)))
        cosine_worst = max(
            cosine_worst,
            abs(echoed - (span * abs(math.cos(math.radians(offset))) + final)),
        )
        seen += 1
    if seen < 3:
        raise AssertionError(f"only {seen} legacy traces print a width; expected at least 3")
    return legacy_worst, cosine_worst


def _legacy_width_law_error() -> float:
    """Worst legacy-law width error over the legacy traces. Row 263."""
    return _legacy_wastefield_width_error()[0]


def _legacy_width_cosine_control() -> float:
    """The cosine law on the same traces -- the control that makes row 263 mean anything."""
    return _legacy_wastefield_width_error()[1]


def _wastefield_width_errors() -> list[tuple[str, float]]:
    """`(trace, |ours - printed|)` for every archived trace that prints a wastefield width.

    ⭐ Computed **from the trace alone** -- ports, spacing and diffuser bearing from the echoed
    diffuser table, current direction from the echoed ambient table, and the final plume diameter
    from the last step. No `.prj` is involved, which is what lets this cover every trace rather than
    the third of them that still have a project file.

        width = (n - 1) * spacing * |cos(bearing - current)| + diameter

    ⚠️ The echo rounds to two decimals, so the *spacing* it supplies is exact only because every
    archived spacing is already a round number. A project with a 0.625 m spacing would echo 0.63
    and this would drift; it is a property of the archive, not of the method.
    """
    from plumes2.io.dat import read_dat

    errors = []
    for path in _archive_traces():
        # ⚠️ Old-build traces are excluded, and that is row 98 rather than convenience: the cosine
        # correction was added between releases, so those files print an essentially uncorrected
        # width. `_old_build_width_gap` measures that difference instead of hiding it here.
        if _is_old_build(path):
            continue
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        printed = parsed.wastefield_width
        if printed is None or not math.isfinite(printed):
            continue
        if "Diffuser" not in parsed.echoed_tables or "Ambient" not in parsed.echoed_tables:
            continue
        frame = parsed.nearfield
        if frame.empty or "P-dia" not in frame.columns:
            continue
        diameter = float(frame["P-dia"].iloc[-1])
        if not math.isfinite(diameter):
            continue

        diffuser = parsed.echoed_tables["Diffuser"]
        ambient = parsed.echoed_tables["Ambient"]
        ports = int(diffuser["Ports"].iloc[0])
        spacing = float(diffuser["Spacing"].iloc[0])
        bearing = float(diffuser["H-angle"].iloc[0])
        current = float(ambient["Amb-dir"].iloc[0])

        ours = (ports - 1) * spacing * abs(math.cos(math.radians(bearing - current))) + diameter
        errors.append((path.name, abs(ours - printed)))
    return errors


def _width_factor_spread_across_bearings() -> float:
    r"""Spread in the implied span factor across case45's eight bearings. **0.0140**.

    ⭐⭐⭐ **This is what refutes the angle law.** Row 275 originally read the factor at 0.990
    (25 deg) against 0.879 (30 deg) and concluded the cosine switches on in between. case45 sweeps
    **one** geometry on **one** exe from 0 to 45 degrees:

    | \|brg - cur\| | 0 | 15 | 22 | 24 | 26 | 28 | 30 | 45 |
    |---|---|---|---|---|---|---|---|---|
    | implied `A` | 1.0000 | 0.9982 | 0.9964 | 0.9959 | 0.9953 | 0.9947 | **0.9940** | **0.9860** |
    | `\|cos\|` | 1.0000 | 0.9659 | 0.9272 | 0.9135 | 0.8988 | 0.8829 | **0.8660** | **0.7071** |

    Flat to **0.0140** over the whole range, where a cosine would fall to 0.707. So on this build
    there is no angular correction at any bearing, and the 25-versus-30 contrast that motivated row
    275 was a comparison across two exe *builds* -- see `_is_old_build` and rows 263/263b.

    ⭐ The residual drift, 1.0000 down to 0.9860, is not an angle law either: it is the
    diameter-selection effect row 96 already flags, and case45's span-doubling arm cancels it
    exactly -- `(242.070 - 122.590) / 120 = 0.9957` with no diameter assumption at all.
    """
    from plumes2.io.dat import read_dat

    factors: list[float] = []
    for path in sorted((_CASES / "case45_bearing_sweep").glob("*.dat")):
        parsed = read_dat(path)
        printed = parsed.wastefield_width
        frame = parsed.nearfield
        diffuser = parsed.echoed_tables["Diffuser"]
        span = (int(diffuser["Ports"].iloc[0]) - 1) * float(diffuser["Spacing"].iloc[0])
        # ⚠️ The span-doubling arm is excluded: it is the same bearing as another trace and exists
        # to cancel the diameter, not to add a point to the curve.
        if printed is None or span > 200.0:
            continue
        factors.append((printed - float(frame["P-dia"].iloc[-1])) / span)
    if len(factors) < 8:
        raise AssertionError(f"only {len(factors)} bearings in case45; expected 8")
    return max(factors) - min(factors)


def _wastefield_width_error() -> float:
    """Worst wastefield-width error over the archive."""
    errors = _wastefield_width_errors()
    if len(errors) < 8:
        raise AssertionError(f"only {len(errors)} traces print a wastefield width; expected more")
    return max(error for _name, error in errors)


def _brooks_columns(relative: str, current: float):  # type: ignore[no-untyped-def]
    """`(parameters, x from the far-field origin, printed width, printed dilution)`.

    Set up the way the exe evidently does: `w0` and `D0` are the far field's own first row, and
    `x` is measured from that row rather than from the diffuser.
    """
    from plumes2.config import EddyDiffusivityLaw
    from plumes2.farfield.brooks import BrooksParameters

    far = _dat(f"reference_cases/{relative}").farfield
    distance = far["Distance"].to_numpy(dtype=np.float64)
    printed_width = far["Width"].to_numpy(dtype=np.float64)
    printed_dilution = far["Dilution"].to_numpy(dtype=np.float64)
    parameters = BrooksParameters(
        initial_width=float(printed_width[0]),
        initial_dilution=float(printed_dilution[0]),
        current_speed=current,
        law=EddyDiffusivityLaw.FOUR_THIRDS,
    )
    return parameters, distance - distance[0], printed_width, printed_dilution


#: case50: Ebb's default project (case03's Macoma configuration, no chemistry) run under each
#: non-default far-field law. The near field is bit-identical to case03's, so the far field is the
#: only thing the selector moves. Rows 280 and 280b.
_LAW_SELECTOR_TRACES = (
    ("case50_eddy_law_selector/eddy_law_constant.dat", "CONSTANT"),
    ("case50_eddy_law_selector/eddy_law_linear.dat", "LINEAR"),
)


def _law_selector_columns(relative: str, law_name: str):  # type: ignore[no-untyped-def]
    """`(parameters, x, printed width, printed dilution)` for a case50 trace under its own law."""
    from plumes2.config import EddyDiffusivityLaw
    from plumes2.farfield.brooks import BrooksParameters

    far = _dat(f"reference_cases/{relative}").farfield
    if far is None:
        raise AssertionError(f"{relative}: the reader returned no far field")
    distance = far["Distance"].to_numpy(dtype=np.float64)
    printed_width = far["Width"].to_numpy(dtype=np.float64)
    printed_dilution = far["Dilution"].to_numpy(dtype=np.float64)
    parameters = BrooksParameters(
        initial_width=float(printed_width[0]),
        initial_dilution=float(printed_dilution[0]),
        current_speed=0.02,
        law=EddyDiffusivityLaw[law_name],
    )
    return parameters, distance - distance[0], printed_width, printed_dilution


def _eddy_law_selector_error() -> float:
    """Worst relative error, port Brooks vs the exe, on `Dilution` under both non-default laws
    and on `Width` under the constant law -- case50, row 280.

    The linear width is row 280b's separate measurement, because it is the one that carried a
    defect. `w0`, `D0` and the origin follow row 115's conventions. Every row of each table is
    compared, not three stations, so the tolerance has to hold along the whole 500 m.
    """
    worst = 0.0
    for relative, law_name in _LAW_SELECTOR_TRACES:
        parameters, x, printed_width, printed_dilution = _law_selector_columns(relative, law_name)
        ours_d = np.asarray(parameters.total_dilution(x))
        worst = max(worst, float(np.max(np.abs(ours_d - printed_dilution) / printed_dilution)))
        if law_name == "CONSTANT":
            ours_w = np.asarray(parameters.width(x))
            worst = max(worst, float(np.max(np.abs(ours_w - printed_width) / printed_width)))
    return worst


def _linear_width_error() -> float:
    """Worst relative error of `w0 (1 + beta x / w0)` against the exe's linear `Width` -- row 280b.

    Asserts the control inside the measurement: the manual's `1 + 2 beta x / w0` (eq 11) must be
    more than 50 % high on the same column, so a future edit that quietly restores the manual's
    form fails here rather than merely moving a number.
    """
    parameters, x, printed_width, _dilution = _law_selector_columns(*_LAW_SELECTOR_TRACES[1])
    ours = np.asarray(parameters.width(x))
    bx = parameters.beta * x / parameters.initial_width
    manual = parameters.initial_width * (1.0 + 2.0 * bx)
    if not float(np.max((manual - printed_width) / printed_width)) > 0.5:
        raise AssertionError("the manual's linear width form no longer disagrees with the exe")
    return float(np.max(np.abs(ours - printed_width) / printed_width))


# ------------------------------------------------------------------ case51: flag ownership
#
# The flag-decode suite: nine one-flag-flip projects on the upstream-example geometry, run on
# the legacy build (deliberately -- operator, 2026-09-01). Rows 281, 281b, 281c, 282. Every
# measure here counts *mismatches against the archived evidence* and expects zero: the as-run
# flag values, the byte-identity groups, and nf3's truncated project are all on disk.

_FLAG_DECODE = _CASES / "case51_flag_decode"

#: The flips that came back preserved and inert -- `(arm, PrjFile attribute, 0-indexed
#: position, the flipped value that must still be in the as-run file)`. Row 281c.
_FLAG_DECODE_INERT = (
    ("nf1", "nearfield_flags", 0, 0),
    ("nf5", "nearfield_flags", 4, 0),
    ("nf6", "nearfield_flags", 5, 0),
    ("ff6", "farfield_flags", 5, 0),
)


def _flag_decode_prj(arm: str) -> PrjFile:
    from plumes2.io.prj import read_prj

    return read_prj(_FLAG_DECODE / f"asrun_flagdecode_{arm}_legacy.prj")


def _flag_decode_bytes(arm: str) -> bytes:
    return (_FLAG_DECODE / f"flagdecode_{arm}_legacy.dat").read_bytes()


def _farfield_gate_mismatches() -> float:
    """Row 281: far-field flags 1 and 5 each turn the far field off, near field untouched."""
    from plumes2.io.dat import read_dat

    failures = 0
    base = read_dat(_FLAG_DECODE / "flagdecode_base_legacy.dat")
    if base.farfield is None or base.farfield.empty:
        failures += 1  # the base arm must have a far field for absence to mean anything
    if _flag_decode_bytes("ff1") != _flag_decode_bytes("ff5"):
        failures += 1  # the two gated traces are bit-identical to each other
    for arm, index in (("ff1", 0), ("ff5", 4)):
        if _flag_decode_prj(arm).farfield_flags[index] != 0:
            failures += 1  # the flipped bit is preserved -- a control the file owns
        gated = read_dat(_FLAG_DECODE / f"flagdecode_{arm}_legacy.dat")
        if gated.farfield is not None and not gated.farfield.empty:
            failures += 1  # the far-field block is absent entirely
        if not gated.nearfield.equals(base.nearfield):
            failures += 1  # and the near field did not move
    return float(failures)


def _ff7_rewrite_mismatches() -> float:
    """Row 281b: far-field flag 7 was written 1 and the exe wrote it back 0, output unmoved."""
    failures = 0
    if _flag_decode_prj("ff7").farfield_flags != _flag_decode_prj("base").farfield_flags:
        failures += 1  # rewritten back to the archive constant [1, 0, 0, 1, 1, 1, 0]
    if _flag_decode_prj("ff7").farfield_flags[6] != 0:
        failures += 1
    if _flag_decode_bytes("ff7") != _flag_decode_bytes("base"):
        failures += 1
    return float(failures)


def _preserved_flag_mismatches() -> float:
    """Row 281c: nf 1/5/6 and ff 6 came back preserved, traces bit-identical to base."""
    base = _flag_decode_bytes("base")
    failures = 0
    for arm, attribute, index, expected in _FLAG_DECODE_INERT:
        if getattr(_flag_decode_prj(arm), attribute)[index] != expected:
            failures += 1
        if _flag_decode_bytes(arm) != base:
            failures += 1
    return float(failures)


def _nf3_truncation_mismatches() -> float:
    """Row 282: the nf3 = 1 run left no trace and a project truncated below its intact head."""
    from plumes2.io.prj import PrjFormatError, read_prj

    # `.prj.evidence`, not `.prj`: the file is deliberately not a loadable project (that is
    # the finding), and the archive-wide `.prj` sweeps must not choke on it.
    path = _FLAG_DECODE / "asrun_flagdecode_nf3_truncated_legacy.prj.evidence"
    failures = 0
    try:
        read_prj(path)
        failures += 1  # it parsed whole -- the file is no longer the truncation evidence
    except PrjFormatError:
        pass
    lines = [line.strip() for line in path.read_text(encoding="latin-1").splitlines()]
    if "ModelResults_TxtOutputs" not in lines:
        failures += 1  # the head, through the output stem, survived the cut
    if not any(
        lines[i : i + 6] == ["1", "1", "1", "3", "1", "1"] for i in range(len(lines) - 5)
    ):
        failures += 1  # the flipped near-field flag block survived in the head
    if any(_FLAG_DECODE.glob("flagdecode_nf3*.dat")):
        failures += 1  # the run produced no output
    return float(failures)


_BOTTOM_STOP = _CASES / "case52_bottom_stop_flag"


def _bottom_stop_mismatches() -> float:
    """Row 283: near-field flag 1 is the stop-at-bottom box -- a stop / sail-on pair."""
    from plumes2.io.dat import read_dat
    from plumes2.io.prj import read_prj

    failures = 0
    base_prj = read_prj(_BOTTOM_STOP / "asrun_base_legacy.prj")
    nf1_prj = read_prj(_BOTTOM_STOP / "asrun_nf1_legacy.prj")
    if base_prj.nearfield_flags[0] != 1 or nf1_prj.nearfield_flags[0] != 0:
        failures += 1  # both values preserved as written
    if base_prj.nearfield_flags[1:] != nf1_prj.nearfield_flags[1:]:
        failures += 1  # one flag moved, and only one
    for name in ("base_legacy.dat", "nf1_legacy.dat"):
        if b"Plume hits the bottom" not in (_BOTTOM_STOP / name).read_bytes():
            failures += 1  # both arms reach the seabed
    base = read_dat(_BOTTOM_STOP / "base_legacy.dat").nearfield
    nf1 = read_dat(_BOTTOM_STOP / "nf1_legacy.dat").nearfield
    shared = len(base) - 1  # base ends on its truncated terminating row, which nf1 skips
    if not base.iloc[:shared].equals(nf1.iloc[:shared]):
        failures += 1  # bit-identical up to seabed contact
    if len(nf1) < len(base) + 10:
        failures += 1  # the cleared box sails on well past it
    return float(failures)


def _width_law_inversion_error() -> float:
    """Worst `|slope - 1|` from inverting the 4/3-power width law against the printed distance.

    ⭐ What establishes the *conventions* rather than the law: solving the width equation for `x`
    and regressing against the exe's own `Distance` column gives a slope of 1 only if `w0` is the
    far field's own first width and `x` runs from that row. Any other choice of origin or initial
    width still fits a line -- with the wrong slope.
    """
    worst = 0.0
    for relative, current in _FARFIELD_TRACES:
        parameters, x, printed, _dilution = _brooks_columns(relative, current)
        initial, beta = parameters.initial_width, parameters.beta
        implied = (initial / ((2.0 / 3.0) * beta)) * ((printed / initial) ** (2.0 / 3.0) - 1.0)
        slope = float(np.polyfit(x, implied, 1)[0])
        worst = max(worst, abs(slope - 1.0))
    return worst


def _farfield_start_distance_error() -> float:
    """Worst gap between the far field's first `Distance` and `hypot(x, y)` at the near-field end.

    The far field starts where the near field stopped, measured as a straight-line distance from
    the diffuser rather than along the trajectory -- so a plume that has travelled sideways starts
    its far field closer to the origin than its path length. Exact on every trace to the three
    decimals both columns print.
    """
    worst = 0.0
    for relative, _current in _FARFIELD_TRACES:
        parsed = _dat(f"reference_cases/{relative}")
        near, far = parsed.nearfield, parsed.farfield
        straight = float(np.hypot(float(near["x-posn"].iloc[-1]), float(near["y-posn"].iloc[-1])))
        worst = max(worst, abs(straight - float(far["Distance"].iloc[0])))
    return worst


@cache
def _farfield_stop_census() -> dict[str, int]:
    """Every archived far-field stop, classified into the exe's session-state rules.

    The exe's far-field stop dialog takes a calculation *distance* and a *dilution* together,
    stops at whichever binds first, and stores neither in the `.prj` -- operator-confirmed
    2026-08-24, with "10000x or 500 m" as the usual entries. So the stop is pure session state,
    and this census is what makes the archive's spread a measured fact rather than prose
    (PLAN section 8c TODO 2, where the prose version was wrong twice).

    Keys: `distance` (a typed 500 m), `chronic_default` (the exe's own default -- the chronic-MZ
    boundary from the trace's diffuser echo, where no distance was typed), `dilution_10000` /
    `dilution_5000` (the dilution stop bound first), `nan` (case09), and `unknown` for any stop
    matching no rule.
    """
    from collections import Counter

    from plumes2.experiments import classify_farfield_stop

    counts: Counter[str] = Counter()
    for path in _archive_traces():
        stop = classify_farfield_stop(_dat(path.relative_to(_ROOT).as_posix()))
        if stop is None:
            continue  # 51 traces carry no far-field block at all
        key = stop.kind if stop.kind != "dilution" else f"dilution_{int(stop.stop or 0)}"
        counts[key] += 1
    return dict(counts)


def _farfield_unclassified_stops() -> float:
    """Archived far-field stops matching no known session-state rule. Zero."""
    return float(_farfield_stop_census().get("unknown", 0))


def _standalone_grid_error() -> float:
    """Worst distance error against the independent calculator's own printed grid.

    ⭐ Folds three ledger rows into one measurement: the grid is **25 steps to the mixing zone plus
    3 beyond**, it is fixed rather than user-controllable, and the **origin row is not printed** --
    so a 200 m zone entered from 0.001 m gives 28 rows running 8.001 to 224.000 m, not 29 from
    0.001. All three are properties of this one array, and getting the origin convention wrong
    shifts every row by a step while still producing a plausible grid.
    """
    from plumes2.farfield.standalone import StandaloneRequest, output_distances

    raw = (_CASES / "case17_independent_farfield/IndpFarfieldCalc1.TXT").read_text(encoding="ascii")
    printed = np.array(
        [float(line.split()[3]) for line in raw.split("\n") if re.match(r"^\s+[\d.]+\s", line)],
        dtype=np.float64,
    )
    ours = output_distances(
        StandaloneRequest(
            initial_width=50.0,
            initial_dilution=100.0,
            current_speed=0.05,
            mixing_zone_distance=200.0,
            initial_location=0.001,
        )
    )
    if len(ours) != len(printed):
        raise AssertionError(f"grid length {len(ours)} against the printed {len(printed)}")
    return float(np.max(np.abs(ours - printed)))


def _farfield_asymptote_depth_excursion() -> float:
    """How far outside the last printed step the far field's chemistry asymptote implies. Zero.

    ⭐ Resolves what looks at first like a discrepancy. case05's far-field TA settles at
    **2925.268**, and the ambient profile puts that at **1.747 m** -- not the 1.710 m the near
    field's last row prints, which interpolates to 2929.0. The two do not disagree: this trace has
    an output interval of 5, so the true termination lies *between* printed rows, and 1.747 sits
    inside the last printed interval (1.787 to 1.710).

    So the asymptote is the ambient at the trapping depth after all -- the same rule the DO module
    found for eq 30 (row 246) -- and it is the *printed* depth that is approximate, not the model.
    Returns the distance by which the implied depth falls outside that bracket.
    """
    parsed = _dat("reference_cases/case05_macoma_merging/test4_TxtOutputs.dat")
    depths = -parsed.nearfield["Depth"].to_numpy(dtype=np.float64)
    asymptote = float(parsed.farfield["TA"].iloc[-1])

    # case05's ambient chemistry table, testco2.csv: depth against total alkalinity.
    levels = np.array([1.0, 2.0, 3.0, 4.0])
    alkalinity = np.array([3000.0, 2900.0, 2900.0, 2850.0])
    # Invert over the monotonic first segment, which is where the plume traps.
    implied = float(np.interp(asymptote, alkalinity[1::-1], levels[1::-1]))

    shallow, deep = min(depths[-2:]), max(depths[-2:])
    return float(max(0.0, shallow - implied, implied - deep))


def _brooks_width_error() -> float:
    """Worst relative error on the far-field width column, over every archived far field."""
    worst = 0.0
    for relative, current in _FARFIELD_TRACES:
        parameters, x, printed, _dilution = _brooks_columns(relative, current)
        worst = max(worst, float(np.max(np.abs(parameters.width(x) - printed) / printed)))
    return worst


def _virtual_origin_dilution_error() -> float:
    """Worst mean far-field dilution error once Brooks is started from a **virtual origin**.

    ⭐⭐ This is what row 116's 11 % shortfall turned out to be. The exe does not run Brooks from
    the width it hands over. It runs it from the **echoed geometric wastefield width**, beginning at
    the upstream distance where that solution has already grown to the handoff width -- 1 to 5 m for
    these cases -- and then reports both columns from there.

    Two things fall straight out. The **width** column matches either way, by construction, which is
    why row 114 was exact all along while the dilution was not. And the **standalone calculator**
    (row 119) matches exactly, because there the width is typed in, so there is no adjustment and
    no virtual origin to find.
    """
    from scipy.optimize import brentq

    from plumes2.config import EddyDiffusivityLaw
    from plumes2.farfield.brooks import BrooksParameters

    worst = 0.0
    for relative, current in _FARFIELD_TRACES:
        parsed = _dat(f"reference_cases/{relative}")
        far = parsed.farfield
        distance = far["Distance"].to_numpy(dtype=np.float64)
        distance = distance - distance[0]
        printed = far["Dilution"].to_numpy(dtype=np.float64)
        handoff = float(far["Width"].iloc[0])
        echoed = float(parsed.wastefield_width or math.nan)

        geometric = BrooksParameters(
            initial_width=echoed,
            initial_dilution=float(printed[0]),
            current_speed=current,
            law=EddyDiffusivityLaw.FOUR_THIRDS,
        )

        def grown_to(
            distance_m: float, law: BrooksParameters = geometric, target: float = handoff
        ) -> float:
            return float(law.width(distance_m)) - target

        origin = 0.0 if abs(handoff - echoed) < 1e-9 else float(brentq(grown_to, 0.0, 5000.0))
        ours = (
            float(printed[0])
            * geometric.dilution_factor(origin + distance)
            / geometric.dilution_factor(origin)
        )
        developed = distance > 50.0
        worst = max(
            worst,
            float(np.mean(np.abs(ours[developed] - printed[developed]) / printed[developed])),
        )
    return worst


def _nearfield_endpoint_ratio() -> float:
    """Our near-field end dilution over the exe's, on the case whose far field we miss worst.

    ⚠️ **The far-field dilution error is mostly this.** Our case13 run ends at 237.7 where the exe
    ends at 169.8, because it integrates further -- transition 10.96 m against 7.32 -- before its
    termination rule fires. Everything downstream inherits that, so the 38.9 % far-field error is a
    termination difference, not a Brooks one.
    """
    from plumes2.results import run

    case = _case("reference_cases/case13_generated_example/PythonGenerated.prj")
    ours = float(run(case, samples=200).nearfield["dilution"].iloc[-1])
    theirs = float(
        _dat("reference_cases/case13_generated_example/PythonGenerated2.dat")
        .farfield["Dilution"]
        .iloc[0]
    )
    return ours / theirs


def _handoff_width_adjustment() -> float:
    """Largest ratio of the exe's far-field starting width to the geometric wastefield width.

    ⚠️ **The one piece of the far field still undecoded.** The exe echoes a geometric width --
    `(n-1) * spacing * |cos| + diameter`, which row 96 reproduces exactly on 43 traces -- and then
    starts its far field from a *larger* one, by 1.00x to 1.13x. The manual calls this the
    transition stage, where plume parameters are "revised/adjusted to match the wastefield
    dimensions", and does not say what the adjustment is.

    It is not a constant, not a fixed multiple of the final plume diameter (the implied factor runs
    1.03 to 2.28 across the archive), and not recoverable from the trajectory: the ratio does not
    track merging, spacing or dilution. Until it is, the virtual origin of row 256 cannot be
    computed from a case -- only from a trace that already contains the answer.
    """
    ratios = []
    for relative, _current in _FARFIELD_TRACES:
        parsed = _dat(f"reference_cases/{relative}")
        geometric = float(parsed.wastefield_width or math.nan)
        handoff = float(parsed.farfield["Width"].iloc[0])
        ratios.append(handoff / geometric)
    return max(ratios)


def _brooks_dilution_shortfall() -> float:
    """Worst *signed* relative dilution error, as a positive shortfall. Never over-predicts.

    Returned as `-min(relative)` so the number reads as "how far low", which is the direction the
    discrepancy actually has -- reporting `max(abs())` would hide that it is one-sided.
    """
    worst = 0.0
    for relative, current in _FARFIELD_TRACES:
        parameters, x, _width, printed = _brooks_columns(relative, current)
        error = (parameters.total_dilution(x) - printed) / printed
        if float(np.max(error)) > 1e-6:
            raise AssertionError(f"{relative}: Brooks over-predicts dilution, which it never has")
        worst = max(worst, -float(np.min(error)))
    return worst


def _plot_frame_failures() -> float:
    """Archived traces that will not adapt to the neutral plot frame. Should be zero."""
    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    failures = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        if parsed.nearfield.empty or "Dilutn" not in parsed.nearfield.columns:
            continue
        try:
            # `secondaries=False` reads the trace as the exe wrote it. With them on, a chemistry
            # trace needs its `Case` to reconstruct salinity, which is a different claim (row 211).
            frame = from_dat(parsed, path, secondaries=False).frame
        except Exception:
            failures += 1
            continue
        if not {"dilution", "plume_diameter_m", "x_m", "y_m", "depth_m"} <= set(frame.columns):
            failures += 1
    return float(failures)


def _parabola_integral_error() -> float:
    """How far the two peak-to-mean constants sit from the parabola's own integrals.

    Both are analytic identities, so the honest reference is zero to numerical-quadrature accuracy
    -- which is the point: the exe's measured 2.0000 and 1.5000 are the integrals of `1 - u^2`,
    not constants anyone fitted.
    """
    from plumes2.crossplume import PEAK_TO_MEAN_ROUND, PEAK_TO_MEAN_SLAB, parabolic_weight

    u = np.linspace(0.0, 1.0, 200_001)
    shape = parabolic_weight(u)
    # Area-weighted over a disc (the pi cancels), and straight across a slab.
    round_ratio = 1.0 / float(np.trapezoid(shape * 2.0 * u, u))
    slab_ratio = 1.0 / float(np.trapezoid(shape, u))
    return max(abs(round_ratio - PEAK_TO_MEAN_ROUND), abs(slab_ratio - PEAK_TO_MEAN_SLAB))


def _unknown_banners() -> float:
    """Event banners in the archive that `dat_format.BANNERS` does not know. Should be zero."""
    from plumes2.io.dat_format import BANNERS

    known = set(BANNERS.values())
    pattern = re.compile(r"^[-.]{4,} \S.*? [-.]{4,}$")
    unknown: set[str] = set()
    for path in _archive_traces():
        for line in path.read_bytes().decode("ascii", "replace").split(CRLF):
            if pattern.match(line) and line not in known:
                unknown.add(line)
    return float(len(unknown))


def _salinity_path_integral_errors() -> tuple[float, float]:
    """`(worst path-integral error in psu, smallest per-trace algebraic penalty)`.

    Over the traces deep enough to tell the two readings apart.

    ⭐ **Row 214's rule, on a third scalar and a different investigation.** The DO module found that
    entrained ambient is accumulated along the trajectory rather than evaluated where the plume ends
    up. Salinity is printed by far more traces and settles it independently.

    ⭐⭐ **case30 is the held-out test, and the rule passes it.** The three original traces all sat
    at an effluent-ambient contrast of about 4 psu. `gap_3` discharges 45 psu into the same ~31 psu
    ambient -- **3.5x the contrast** -- and traverses 7.6 m rather than 5:

        trace                 contrast   path       algebraic   penalty
        limspc_shallow          4 psu    0.0023      0.0928       40x
        limspc_gap / gap_2      4        0.0029      0.1674       58x
        gap_1                   4        0.0035      0.1841       53x
        gap_4                   4        0.0034      0.1859       55x
        limspc_deep_control     4        0.0059      0.2297       39x
        gap_3                  14        0.0226      0.3302       15x

    ⚠️ **The residual scales with the contrast, not with depth.** 0.0226 psu is 6.5x the others at
    3.5x the driving difference, which is 0.16 % of gap_3's own contrast against 0.09 % for the
    rest. So the rule is not exact, and pretending otherwise by quoting the 0.006 psu of the
    low-contrast runs would have been a tolerance fitted to an easy sample. The separation from the
    algebraic form narrows with it -- 15x rather than 40-58x -- and still holds by an order of
    magnitude, which is the claim.

    ⚠️ Seeded with the ambient **already entrained by the first printed row** -- unlike DO. Row 220
    records a one-step accumulator lag in the exe's DO column, where step 1 prints `DO_e` having
    credited none of the 2 % already entrained. Salinity has no such lag, so the same code with the
    DO seeding is 0.6 psu out. That lag is a property of the DO channel, not of the entrainment.

    Shallower traces cannot discriminate: over less than a metre of traverse the two forms agree to
    inside what three printed decimals resolve.
    """
    from plumes2.io.dat import read_dat

    worst_path = 0.0
    worst_penalty = float("inf")
    discriminating = 0
    traces = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if not {"P-Sal", "Dilutn", "Depth"} <= set(frame.columns):
            continue
        if "Diffuser" not in parsed.echoed_tables or "Ambient" not in parsed.echoed_tables:
            continue
        salinity = frame["P-Sal"].to_numpy(dtype=np.float64)
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        usable = np.isfinite(salinity) & np.isfinite(dilution) & np.isfinite(depth)
        salinity, dilution, depth = salinity[usable], dilution[usable], depth[usable]
        if len(depth) < 40 or depth.max() - depth.min() < 3.0:
            continue

        levels = parsed.echoed_tables["Ambient"]
        effluent = float(parsed.echoed_tables["Diffuser"]["Eff-sal"].iloc[0])
        ambient = np.interp(
            depth,
            levels["Depth"].to_numpy(dtype=np.float64),
            levels["Amb-sal"].to_numpy(dtype=np.float64),
        )
        increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(dilution)
        accumulated = np.concatenate([[0.0], np.cumsum(increments)])
        integrated = (effluent + (dilution[0] - 1.0) * ambient[0] + accumulated) / dilution
        algebraic = ambient + (effluent - ambient) / dilution

        developed = dilution > 5.0
        # ⚠️ Normalised, not in psu. The raw residual is `contrast x epsilon / D`, so quoting psu
        # makes a 3.5 psu trace and a 32 psu one look like different physics when they differ
        # only in the driving term and the dilution. `epsilon` is what is actually fixed --
        # see the docstring, and case31's README for the measurement that forced this.
        contrast = abs(float(np.mean(ambient)) - effluent)
        if contrast <= 0.0:
            continue
        scale = dilution[developed] / contrast
        this_path = float(np.max(np.abs((integrated - salinity)[developed]) * scale))
        this_algebraic = float(np.max(np.abs((algebraic - salinity)[developed]) * scale))
        worst_path = max(worst_path, this_path)
        traces += 1
        # ⚠️ **A trace can only score the two readings against each other if its two predictions
        # differ by more than the measurement can see.** Row 222 established that a *uniform*
        # ambient collapses the path integral exactly onto the algebraic form, and a nearly
        # uniform one nearly does: case31 at a flat 32 psu separates them by 0.000 psu, and
        # case34's two widest spacings by 0.035. Counting those would read as the discrimination
        # failing when it is row 222 being right.
        #
        # The cut is at 0.05 psu -- a hundred times the printed digit -- and it sits inside a real
        # gap in the archive rather than at a tuned value: the separations run 0.000, 0.035,
        # 0.035, 0.039, 0.040, then **0.086**, 0.092, 0.151 and up. Anywhere from 0.041 to 0.085
        # gives the same partition.
        if float(np.max(np.abs((algebraic - integrated)[developed]))) < 0.05:
            continue
        # The **smallest** separation any single trace shows, not the ratio of the two worsts.
        # Those come from different traces once the archive spans two contrasts, and dividing
        # one run's algebraic error by another's path error is a number about neither.
        worst_penalty = min(worst_penalty, this_algebraic / this_path)
        discriminating += 1
    if traces < 3 or discriminating < 3:
        raise AssertionError(
            f"{traces} traces traverse enough depth, {discriminating} of them with a "
            "non-uniform ambient; both are needed"
        )
    return worst_path, worst_penalty


#: Below this effluent-ambient contrast the printed digit cannot resolve a 2 % dilution offset.
#: `P-Sal` prints three decimals, so one digit is 0.0005 psu; normalised as a fractional dilution
#: offset that is `0.0005 x D / contrast`, which at `D` = 200 is 0.003 on a 32 psu contrast and
#: **0.026 on the Macoma family's 3.9 psu** -- larger than the effect. Row 258c's original
#: "0.016-0.044" band came from `max |residual|` over traces of both kinds, and its upper half is
#: the digit rather than the exe (2026-08-25).
_RESOLVABLE_CONTRAST = 20.0


@dataclass(frozen=True, slots=True)
class _SalinityOffset:
    """One trace's implied fractional dilution offset between `P-Sal` and `Dilutn`."""

    trace: str
    #: |effluent - ambient| at the first printed row, psu.
    contrast: float
    #: Printed step interval -- 1 where every step is printed, 5 where every fifth is.
    interval: int
    #: Developed rows used (`D` > 5, before surface contact).
    rows: int
    #: Median of `D_implied / D - 1`, `P-Sal` against `Dilutn` on the **same** row.
    epsilon: float
    #: Share of developed rows on which that offset is positive.
    positive_share: float
    #: Slope of `log |residual|` against `log D`: -1 is a fixed fraction of the dilution, 0 a
    #: fixed number of psu -- which is what rounding noise or a constant bias would give.
    slope: float
    #: Median of the same offset with `Dilutn` taken one printed row **later**.
    epsilon_ahead: float


@cache
def _salinity_dilution_offsets() -> tuple[_SalinityOffset, ...]:
    """The `P-Sal`-against-`Dilutn` census over every archived trace printing both (row 258c).

    For each row, the salinity the exe prints implies a dilution of its own: with `A` the mean
    ambient entrained so far (the path integral rows 109/214 established), `D_implied = (eff - A)
    / (P-Sal - A)`, and `epsilon = D_implied / Dilutn - 1` is how much *more* dilution the
    salinity column reports than the dilution column. Sign-consistent for fresh and dense
    effluents alike.

    ⚠️ **Cut at surface contact** (`|Depth| - P-dia/2` <= 0, row 258b's criterion) where the trace
    carries `P-dia`: past the surface the exe's stepping changes character -- case31's `surface_off`
    reads 0.024 before contact and after it, but the one-row shift below collapses only the first
    (0.004 against 0.023) -- and neither model has a free-surface treatment there (row 258).
    """
    from plumes2.io.dat import read_dat

    records: list[_SalinityOffset] = []
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if not {"P-Sal", "Dilutn", "Depth"} <= set(frame.columns):
            continue
        if "Diffuser" not in parsed.echoed_tables or "Ambient" not in parsed.echoed_tables:
            continue
        steps = frame.index.to_numpy(dtype=np.float64)
        salinity = frame["P-Sal"].to_numpy(dtype=np.float64)
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        usable = np.isfinite(salinity) & np.isfinite(dilution) & np.isfinite(depth)
        if "P-dia" in frame.columns:
            radius = frame["P-dia"].to_numpy(dtype=np.float64) / 2.0
            submerged = np.abs(depth) - radius > 0.0
            contact = np.flatnonzero(usable & ~submerged)
            if contact.size:
                usable[int(contact[0]) :] = False
        salinity, dilution, depth, steps = (
            salinity[usable],
            dilution[usable],
            depth[usable],
            steps[usable],
        )
        if len(dilution) < 30:
            continue
        levels = parsed.echoed_tables["Ambient"]
        effluent = float(parsed.echoed_tables["Diffuser"]["Eff-sal"].iloc[0])
        ambient = np.interp(
            depth,
            levels["Depth"].to_numpy(dtype=np.float64),
            levels["Amb-sal"].to_numpy(dtype=np.float64),
        )
        increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(dilution)
        entrained = (dilution[0] - 1.0) * ambient[0] + np.concatenate(
            [[0.0], np.cumsum(increments)]
        )
        mean_ambient = np.where(
            dilution > 1.0, entrained / np.maximum(dilution - 1.0, 1e-12), ambient
        )
        contrast = abs(effluent - float(ambient[0]))
        if contrast <= 0.0:
            continue
        with np.errstate(divide="ignore", invalid="ignore"):
            implied = (effluent - mean_ambient) / (salinity - mean_ambient)
            epsilon = implied / dilution - 1.0
            epsilon_ahead = implied[:-1] / dilution[1:] - 1.0
        developed = dilution > 5.0
        if int(np.count_nonzero(developed)) < 20:
            continue
        residual = np.abs((effluent + entrained) / dilution - salinity)[developed]
        nonzero = residual > 0.0
        slope = (
            float(np.polyfit(np.log(dilution[developed][nonzero]), np.log(residual[nonzero]), 1)[0])
            if int(np.count_nonzero(nonzero)) > 5
            else math.nan
        )
        step_gaps = np.diff(steps)
        interval = int(np.median(step_gaps)) if step_gaps.size else 1
        records.append(
            _SalinityOffset(
                trace=f"{path.parent.name}/{path.name}",
                contrast=contrast,
                interval=interval,
                rows=int(np.count_nonzero(developed)),
                epsilon=float(np.median(epsilon[developed])),
                positive_share=float(np.mean(epsilon[developed] > 0.0)),
                slope=slope,
                epsilon_ahead=float(np.median(epsilon_ahead[developed[:-1]])),
            )
        )
    return tuple(records)


def _resolvable_salinity_offsets() -> list[_SalinityOffset]:
    offsets = [o for o in _salinity_dilution_offsets() if o.contrast >= _RESOLVABLE_CONTRAST]
    if len(offsets) < 6:
        raise AssertionError(f"only {len(offsets)} traces resolve the offset; six are needed")
    return offsets


def _salinity_dilution_offset() -> float:
    """Row 258c: the median implied fractional dilution offset where the digit can see it.

    ⚠️ **One target, four assertions**, because 258c is one ledger row and the registry keeps one
    target per row. The returned number is the offset; everything that makes it a *dilution*
    offset rather than rounding, and a *one-step lag* rather than an unexplained constant, is
    asserted here instead of being split into a second target:

    1. it is positive on **every** developed row of every resolvable trace -- a sign, not a spread;
    2. the residual falls with slope < -0.5 in `log D`, so it is a fixed fraction of the dilution
       where rounding or a constant bias would give 0;
    3. pairing `P-Sal` at row `i` with `Dilutn` at row `i + 1` **collapses** it on every trace
       printed at every step, +0.022 to +0.002-0.004;
    4. and the interval-3 and interval-5 traces **over-correct** under that same one-row shift,
       to -0.037 and -0.074 -- which is what makes the lag one *step* rather than one printed
       *row*. case38 printed one discharge at all three intervals, so that is a control rather
       than a coincidence.
    """
    offsets = _resolvable_salinity_offsets()
    every_step = [o for o in offsets if o.interval == 1]
    if len(every_step) < 6:
        raise AssertionError(f"only {len(every_step)} resolvable traces print every step")
    for o in offsets:
        assert o.positive_share >= 0.99, f"{o.trace}: positive on {o.positive_share:.0%} of rows"
        assert o.slope < -0.5, f"{o.trace}: residual slope {o.slope:.2f} is not a dilution offset"
        if o.interval >= 3:
            assert o.epsilon_ahead < -0.02, (
                f"{o.trace}: interval {o.interval}, shifted offset {o.epsilon_ahead:+.4f} does "
                "not over-correct as a one-step lag predicts"
            )
    shifted = float(np.median([o.epsilon_ahead for o in every_step]))
    assert abs(shifted) < 0.006, f"the one-row shift leaves {shifted:+.4f}; it should collapse"
    return float(np.median([o.epsilon for o in offsets]))


def _salinity_path_integral_error() -> float:
    """The implied fractional dilution offset, `epsilon`. Dimensionless, and stable."""
    return _salinity_path_integral_errors()[0]


def _salinity_algebraic_penalty() -> float:
    """How many times worse the algebraic reading is, on the trace where it does worst."""
    return _salinity_path_integral_errors()[1]


#: (S, T) pairs spanning the archive's range plus the fresh and hypersaline ends.
_KSP_GRID = ((10.0, 5.0), (25.0, 10.0), (31.4, 12.0), (35.0, 15.0), (40.0, 20.0), (45.0, 25.0))


def _pyco2sys_grid():  # type: ignore[no-untyped-def]
    """PyCO2SYS evaluated once over `_KSP_GRID`, with the exe's own constant options."""
    import PyCO2SYS as pyco2

    salinity = np.array([s for s, _t in _KSP_GRID])
    temperature = np.array([t for _s, t in _KSP_GRID])
    return (
        salinity,
        temperature,
        pyco2.sys(
            par1=2300.0,
            par2=2100.0,
            par1_type=1,
            par2_type=2,
            salinity=salinity,
            temperature=temperature,
            opt_k_carbonic=10,
            opt_k_bisulfate=1,
        ),
    )


def _solubility_product_gap() -> float:
    """Worst relative difference between our `Ksp` and PyCO2SYS's, both minerals. Exactly zero.

    Not "agrees to a tolerance" -- identical to the last bit, because both evaluate Mucci (1983)
    and neither rounds on the way. Worth an executable target precisely because it is the kind of
    claim that quietly stops being true when a dependency changes its constants.
    """
    from plumes2.chem.constants import solubility_aragonite, solubility_calcite

    salinity, temperature, theirs = _pyco2sys_grid()
    worst = 0.0
    for ours, key in (
        (solubility_calcite(salinity, temperature), "k_calcite"),
        (solubility_aragonite(salinity, temperature), "k_aragonite"),
    ):
        reference = np.asarray(theirs[key], dtype=np.float64)
        worst = max(worst, float(np.max(np.abs(np.asarray(ours) - reference) / reference)))
    return worst


def _calcium_gap_against_pyco2sys() -> float:
    """Relative gap between the exe's calcium constant and PyCO2SYS's. 0.0444 %, and flat.

    The only thing separating our saturation states from PyCO2SYS's. The exe's dialog carries
    `[Ca] = 0.01028 x S/35` where PyCO2SYS uses 0.0102845697, and `Omega` is linear in calcium, so
    the whole discrepancy is this one rounded constant. Measured across salinity to show it is a
    *constant* ratio -- the spread is 2e-16, floating-point noise -- rather than a drift, which
    would point at a different formula instead of a rounded one.
    """
    from plumes2.chem.constants import calcium_from_salinity

    salinity, _temperature, theirs = _pyco2sys_grid()
    reference = np.asarray(theirs["total_calcium"], dtype=np.float64) * 1e-6
    ratio = np.abs(np.asarray(calcium_from_salinity(salinity)) - reference) / reference
    if float(np.ptp(ratio)) > 1e-12:
        raise AssertionError(f"the calcium gap is not constant: spread {float(np.ptp(ratio))}")
    return float(np.max(ratio))


def _undersaturated_rate_is_zero() -> float:
    """Rates returned for `Omega < 1` by default, summed. Zero -- and NaN only on request.

    The exe evaluates `(Omega - 1) ** N` unguarded, so an undersaturated row is NaN and one NaN
    poisons the remaining trace (case09, 955 rows). Physically the rate is zero: nothing
    precipitates from undersaturated water, it dissolves. This asserts both halves -- that the
    default is finite and zero, and that `reproduce_undersaturated_nan` still produces the exe's
    NaN for anyone studying it.
    """
    from plumes2.chem import CALCITE, precipitation_rate

    omega = np.array([0.1, 0.5, 0.9, 1.0])
    ours = precipitation_rate(omega, 35.0, CALCITE)
    if not np.isfinite(ours).all():
        raise AssertionError("the default path produced a non-finite rate")
    faithful = precipitation_rate(omega, 35.0, CALCITE, reproduce_undersaturated_nan=True)
    if np.isfinite(faithful[:3]).any() or not np.isfinite(faithful[3]):
        raise AssertionError("the reproduce flag no longer emits the exe's NaN below Omega = 1")
    return float(np.sum(np.abs(ours)))


#: The carbonate columns, which travel together: dropped together from a truncated
#: terminating row (row 79), and printed together beside `DO` where the manual says
#: they cannot be (row 216).
_CHEMISTRY_COLUMNS = frozenset({"TA", "DIC", "pH", "OmegaC", "OmegaA", "R_cal", "R_arg"})


@cache
def _aragonite_band_edges() -> tuple[float, float, float, float]:
    """`(low_last_on, low_first_off, high_first_off, high_last_on)` in reconstructed psu.

    The exe reports `R_arg` as exactly zero over a **band**, not below a floor. Every trace that
    prints `R_arg` is scanned; salinity is reconstructed from the dilution column by the path
    integral row 109 validated, because the chemistry traces do not print `P-Sal`.

    ⚠️ The reconstruction is why this is bracketed rather than solved. Row 109's worst residual is
    0.023 psu against bracket widths of 0.69 and 0.40 psu here, so the conclusion is safe by a
    factor of 17 -- but a trace that printed both `P-Sal` and `R_arg` would settle both edges
    outright, and none does.
    """
    from plumes2.io.dat import read_dat

    low_on = high_off = -np.inf
    low_off = high_on = np.inf
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if "R_arg" not in frame.columns or "Ambient" not in parsed.echoed_tables:
            continue
        rate = frame["R_arg"].to_numpy(dtype=np.float64)
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        usable = np.isfinite(rate) & np.isfinite(dilution) & np.isfinite(depth)
        rate, dilution, depth = rate[usable], dilution[usable], depth[usable]
        if len(rate) < 5:
            continue
        levels = parsed.echoed_tables["Ambient"]
        effluent = float(parsed.echoed_tables["Diffuser"]["Eff-sal"].iloc[0])
        ambient = np.interp(
            depth,
            levels["Depth"].to_numpy(dtype=np.float64),
            levels["Amb-sal"].to_numpy(dtype=np.float64),
        )
        increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(dilution)
        salinity = (
            effluent
            + (dilution[0] - 1.0) * ambient[0]
            + np.concatenate([[0.0], np.cumsum(increments)])
        ) / dilution
        active = rate != 0.0
        if not active.any():
            # A wholly-inactive trace still constrains the dead band from inside.
            low_off = min(low_off, float(salinity.min()))
            high_off = max(high_off, float(salinity.max()))
            continue
        # Salinities below 25 belong to the low band, those above 35 to the high one; the
        # 10-psu gap between them is wide enough that no trace straddles it ambiguously.
        low = salinity[active & (salinity < 30.0)]
        high = salinity[active & (salinity >= 30.0)]
        if low.size:
            low_on = max(low_on, float(low.max()))
        if high.size:
            high_on = min(high_on, float(high.min()))
        off = salinity[~active]
        if off.size:
            low_off = min(low_off, float(off.min()))
            high_off = max(high_off, float(off.max()))
    if not np.isfinite([low_on, low_off, high_on, high_off]).all():
        raise AssertionError("the archive no longer brackets both aragonite band edges")
    return low_on, low_off, high_off, high_on


#: case32's five chemistries share one trajectory with case31's `surface_off`, which is the only
#: trace carrying the salinity column. Bit-identical over all 572 steps and five columns, so
#: joining them by step is exact rather than approximate -- see `_aragonite_low_edge_bracket`.
_SALINITY_DONOR = "case31_surface_stop_pair/surface_off.dat"
_CHEM_VARIANTS = tuple(f"case32_aragonite_low_edge/chem_{n}.dat" for n in (1, 2, 3, 4, 5))


def _aragonite_low_edge_bracket() -> float:
    """Width of the bracket around the low aragonite edge, from a **printed** salinity. 0.14 psu.

    ⭐⭐ All five of case32's chemistries switch `R_arg` off at the same step -- last active at a
    printed 24.895 psu, first zero at 25.035 -- while Omega_A at that switch runs from 3.997 to
    9.036. A factor of 2.3 in saturation state moves the edge not at all, which is what finally
    rules saturation out as the trigger. Row 60's other bracket, over the whole archive, has to
    reconstruct salinity; this one reads it.

    ⚠️ The salinity comes from a different file. That is exact, not a shortcut: the five runs and
    the donor agree bit for bit on every shared hydrodynamic column across all 572 steps, which is
    asserted here rather than assumed.
    """
    from plumes2.io.dat import read_dat

    donor = read_dat(_CASES / _SALINITY_DONOR).nearfield
    salinity = donor["P-Sal"]
    shared = ["Dilutn", "P-dia", "x-posn", "y-posn", "Depth"]
    edges = set()
    for name in _CHEM_VARIANTS:
        frame = read_dat(_CASES / name).nearfield
        for column in shared:
            gap = np.abs(
                frame[column].to_numpy(dtype=np.float64)
                - donor.loc[frame.index, column].to_numpy(dtype=np.float64)
            )
            if float(np.nanmax(gap)) != 0.0:
                raise AssertionError(f"{name} is not the same trajectory as the donor ({column})")
        rate = frame["R_arg"].to_numpy(dtype=np.float64)
        active = np.where(rate > 0.0)[0]
        if not active.size or active[-1] + 1 >= len(rate):
            raise AssertionError(f"{name} does not cross the edge")
        here = salinity.reindex(frame.index).to_numpy(dtype=np.float64)
        edges.add((round(float(here[active[-1]]), 3), round(float(here[active[-1] + 1]), 3)))
    if len(edges) != 1:
        raise AssertionError(f"the five chemistries disagree about the edge: {sorted(edges)}")
    low, high = edges.pop()
    if not low < 25.0 <= high:
        raise AssertionError(f"the bracket ({low}, {high}] no longer contains 25")
    return high - low


def _aragonite_edge_omega_spread() -> float:
    """Range of Omega_A at the switch across case32's five chemistries. About 5.

    ⭐⭐ The control that turns row 60 from an observation into a mechanism. If the exe were
    switching on saturation state, five runs switching at the same step would have to share an
    Omega_A; they span 3.997 to 9.036. Everything else about the run is identical, so salinity is
    the only thing left that could be doing it.
    """
    from plumes2.io.dat import read_dat

    values = []
    for name in _CHEM_VARIANTS:
        frame = read_dat(_CASES / name).nearfield
        rate = frame["R_arg"].to_numpy(dtype=np.float64)
        omega = frame["OmegaA"].to_numpy(dtype=np.float64)
        active = np.where(rate > 0.0)[0]
        values.append(float(omega[active[-1]]))
    return max(values) - min(values)


def _carbonate_pairing_violations() -> float:
    """case32 runs whose printed endmember disagrees with the stated input pairing. Zero.

    The rule (row 45): a **zero** DIC means "not supplied" and selects TA + pH; any non-zero DIC
    wins and the entered pH is discarded. case32 decides it by construction -- all five runs type
    pH 10.5, two of them with DIC 0 and three with a real DIC.

    Checked per run: where DIC was supplied, the printed endmember must reproduce it and the
    printed pH must have moved away from the 10.5 typed in; where it was not, the printed DIC must
    match what PyCO2SYS returns for TA + pH.
    """
    from plumes2.chem import resolve_constants, solve_from_alkalinity_ph
    from plumes2.io.dat import read_dat

    entered = ((4000.0, 0.0), (4000.0, 1000.0), (4000.0, 2000.0), (3000.0, 2000.0), (5000.0, 0.0))
    violations = 0
    for name, (_alkalinity, dic_in) in zip(_CHEM_VARIANTS, entered, strict=True):
        frame = read_dat(_CASES / name).nearfield
        dilution = float(frame["Dilutn"].iloc[0])
        dic_out = dilution * float(frame["DIC"].iloc[0]) - (dilution - 1.0) * 1600.0
        if dic_in > 0.0:
            # Supplied: reproduced to a fraction of a percent, and the typed pH discarded.
            violations += abs(dic_out - dic_in) / dic_in > 0.01
            violations += abs(float(frame["pH"].iloc[0]) - 10.5) < 0.05
        else:
            # Not supplied: computed from TA and pH, and it is our speciation that reproduces it.
            ours = solve_from_alkalinity_ph(
                _alkalinity, 10.5, 0.0, 2.63, constants=resolve_constants(10, 1)
            )
            violations += abs(float(ours.dic) - dic_out) > 5.0
    return float(violations)


def _aragonite_dead_band_width() -> float:
    """Width of the salinity band over which the exe reports zero aragonite. About 10 psu.

    ⭐ **This is the number that shows it is a gap, not a floor.** A floor at 35 would make the
    zero region unbounded below and this measurement meaningless; instead it is bounded on both
    sides by traces that precipitate, and the bound is ordinary seawater.
    """
    low_on, _low_off, _high_off, high_on = _aragonite_band_edges()
    return high_on - low_on


def _aragonite_low_band_residual() -> float:
    """Worst relative error of the dialog's low-band law on every archived low-band row. 3.4e-4.

    `logK = 1.53, N = 2.33` as the dialog writes them, no fitting. **395 rows** -- case13, which
    overturned "the exe never evaluates the low band", plus case32's five chemistries down the
    same trajectory. A free two-parameter fit over case32's 380 returns logK 1.53001, N 2.33000,
    recovering the dialog to five decimals across a 2.3x range in Omega and 1.7x in entered TA.
    """
    from plumes2.chem import ARAGONITE_LOW_SALINITY, precipitation_rate
    from plumes2.io.dat import read_dat

    worst = 0.0
    rows = 0
    for name in ("case13_generated_example/PythonGenerated2.dat", *_CHEM_VARIANTS):
        frame = read_dat(_CASES / name).nearfield
        rate = frame["R_arg"].to_numpy(dtype=np.float64)
        omega = frame["OmegaA"].to_numpy(dtype=np.float64)
        active = (rate > 0.0) & np.isfinite(omega)
        ours = precipitation_rate(omega[active], 10.0, ARAGONITE_LOW_SALINITY)
        worst = max(worst, float(np.max(np.abs(ours - rate[active]) / rate[active])))
        rows += int(active.sum())
    if rows < 300:
        raise AssertionError(f"only {rows} low-band rows to check")
    return worst


#: Half the last printed digit. Every chemistry column in the `.dat` carries three decimals.
_PRINTED_HALF = 0.0005


def _precipitation_law_margin() -> float:
    """Worst rate-law residual as a fraction of what the printed columns can resolve. Under 1.

    ⭐⭐ **1 476 rows, both minerals, all three salinity bands, and not one of them exceeds the
    archive's own resolution.** The tightest sits at 0.993 of it.

    The bound is not a fitted tolerance -- it is arithmetic on the printed precision. `Omega` and
    `R` both print to three decimals, so a row admits

        |dR/R|  <=  N * 0.0005 / (Omega - 1)  +  0.0005 / R

    the first term being `Omega`'s half-digit propagated through the exponent, which dominates
    wherever the plume is near saturation. That is why the raw relative residual looks worst on
    case09's `Omega = 2.09` rows (1.6e-3) and best on the strongly supersaturated ones (1.7e-4):
    the *law* is equally good everywhere, and only the resolution moves.

    Measured through `precipitation_rate` with the shipped laws, so it tests the code rather than
    a re-derivation -- including the band selection, since the aragonite band is chosen from the
    reconstructed salinity exactly as a caller would.
    """
    from plumes2.chem import CALCITE, aragonite_laws, precipitation_rate
    from plumes2.io.dat import read_dat

    worst = 0.0
    rows = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if "R_cal" not in frame.columns or "Ambient" not in parsed.echoed_tables:
            continue
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        levels = parsed.echoed_tables["Ambient"]
        effluent = float(parsed.echoed_tables["Diffuser"]["Eff-sal"].iloc[0])
        ambient = np.interp(
            depth,
            levels["Depth"].to_numpy(dtype=np.float64),
            levels["Amb-sal"].to_numpy(dtype=np.float64),
        )
        finite = np.isfinite(dilution) & np.isfinite(ambient)
        salinity = np.full(dilution.shape, np.nan)
        increments = 0.5 * (ambient[1:] + ambient[:-1]) * np.diff(dilution)
        salinity[finite] = (
            effluent
            + (dilution[0] - 1.0) * ambient[0]
            + np.concatenate([[0.0], np.cumsum(increments)])
        )[finite] / dilution[finite]
        for column, omega_column, laws, exponents in (
            ("R_cal", "OmegaC", CALCITE, (CALCITE.exponent,)),
            (
                "R_arg",
                "OmegaA",
                aragonite_laws(reproduce_band_gap=True),
                (2.33, 2.26),
            ),
        ):
            printed = frame[column].to_numpy(dtype=np.float64)
            omega = frame[omega_column].to_numpy(dtype=np.float64)
            usable = (printed > 0.0) & np.isfinite(omega) & (omega > 1.0) & np.isfinite(salinity)
            if not usable.any():
                continue
            ours = precipitation_rate(omega[usable], salinity[usable], laws)
            residual = np.abs(ours - printed[usable]) / printed[usable]
            exponent = max(exponents)
            bound = (
                exponent * _PRINTED_HALF / (omega[usable] - 1.0) + _PRINTED_HALF / printed[usable]
            )
            worst = max(worst, float(np.max(residual / bound)))
            rows += int(usable.sum())
    if rows < 1000:
        raise AssertionError(f"only {rows} rate rows compared")
    return worst


def _scalar_overlay_perturbation() -> float:
    """Largest difference in a shared hydrodynamic column when a scalar overlay is switched on.

    ⭐ Zero, over two independent families. case02 against case03 turns the carbonate module on
    across 5 shared columns and 41 rows; test36 against test37 and test38 turns DO on, then DO
    **and** chemistry, across 13 shared columns and 526 rows. Nothing moves in any of them.

    That is the licence for treating chemistry and DO as post-processing over a trajectory rather
    than as state the solver has to carry -- and it is why an archived `.dat` can be handed to our
    chemistry directly. Folds row 40.
    """
    from plumes2.io.dat import read_dat

    families = (
        ("case02_macoma_mgd/Macomatest1.dat", ("case03_macoma_carbonate/test2_TxtOutputs.dat",)),
        (
            "case24_macoma_dissolved_oxygen/test36.dat",
            (
                "case24_macoma_dissolved_oxygen/test37.dat",
                "case24_macoma_dissolved_oxygen/test38.dat",
            ),
        ),
    )
    worst = 0.0
    compared = 0
    for base_name, others in families:
        base = read_dat(_CASES / base_name).nearfield
        for other_name in others:
            other = read_dat(_CASES / other_name).nearfield
            shared = [column for column in base.columns if column in other.columns]
            if len(base) != len(other) or len(shared) < 5:
                raise AssertionError(f"{base_name} and {other_name} are not comparable")
            for column in shared:
                gap = np.abs(
                    base[column].to_numpy(dtype=np.float64)
                    - other[column].to_numpy(dtype=np.float64)
                )
                worst = max(worst, float(np.nanmax(gap)))
            compared += len(shared)
    if compared < 30:
        raise AssertionError(f"only {compared} column comparisons")
    return worst


def _columns_the_manual_forbids_together() -> float:
    """Carbonate columns printed alongside `DO` in one trace. Seven, and the manual says zero.

    Manual section 5.2.6: DO and pH calculations "cannot be conducted simultaneously". test38
    prints the full carbonate set **and** `DO`, so the restriction is documentation rather than
    behaviour -- which is what makes lifting it in our port a non-event rather than a feature.
    """
    from plumes2.io.dat import read_dat

    frame = read_dat(_CASES / "case24_macoma_dissolved_oxygen/test38.dat").nearfield
    if "DO" not in frame.columns:
        raise AssertionError("test38 no longer carries a DO column")
    return float(len(_CHEMISTRY_COLUMNS & set(frame.columns)))


#: A step-table data row: the step number is the first token on the line.
_STEP_ROW = re.compile(r"^\s+\d+\s")


def _terminating_row_truncation_violations() -> float:
    """Traces whose terminating row is truncated when it should not be, or the reverse. Zero.

    The exe prints its final step wherever the plume actually stopped, which is usually *not* on
    the output interval -- and when it does that, it drops the chemistry columns. On-interval
    terminators keep them.

    ⚠️ Scoped to traces that **carry** chemistry columns, and that is the finding rather than a
    convenience: case14 terminates off-interval and prints a full-width row, because with no
    chemistry there is nothing to drop. The rule is about which columns survive, so a trace with
    none cannot exercise it.
    """
    from plumes2.io.dat import read_dat

    violations = 0
    checked = 0
    for path in _archive_traces():
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if frame.empty or not (_CHEMISTRY_COLUMNS & set(frame.columns)):
            continue
        raw = path.read_bytes().decode("ascii", "replace")
        numeric = [line for line in raw.split(CRLF) if _STEP_ROW.match(line)]
        if len(numeric) < 3:
            continue
        steps = frame.index.to_numpy()
        interval = int(steps[1] - steps[0])
        if interval <= 0:
            continue
        on_interval = int(steps[-1]) % interval == 0
        truncated = len(numeric[-1].split()) < len(numeric[-2].split())
        checked += 1
        violations += on_interval == truncated
    if checked < 10:
        raise AssertionError(f"only {checked} traces carry chemistry columns")
    return float(violations)


def _solver_step_cap() -> float:
    """The longest archived trace, in steps. The exe's own ceiling.

    Only degenerate runs reach it: case09, whose plume leaves the water column at 39.5 m/s, and
    case29's sub-critical trio, which leave it the other way. A healthy run terminates on a turning
    point (row 183) or a boundary (row 78) long before.
    """
    from plumes2.io.dat import read_dat

    longest = 0
    for path in _archive_traces():
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if not frame.empty:
            longest = max(longest, int(frame.index[-1]))
    return float(longest)


def _bearing_convention_error() -> float:
    """How far a jet discharged along the current departs from the current's own axis.

    ⭐ Decisive between two conventions that differ by 90 degrees. Bearings are `(cos, sin)`, so a
    90 degree jet in a 90 degree current runs up **+y** and never leaves it -- test16's final `x` is
    0.000. Read as a compass bearing instead (north at 0, clockwise), 90 degrees would be due east
    and the whole displacement would be in `x`.

    The obliques confirm the sign: `cos 175` is negative and test19 ends at x = -2.187, while
    `cos 70` is positive and test20 ends at +0.728. Both are asserted here rather than returned,
    because a sign is not a tolerance.
    """
    from plumes2.io.dat import read_dat

    def final(name: str) -> tuple[float, float]:
        frame = read_dat(_CASES / f"case16_oldbuild_angle_sweep/{name}.dat").nearfield
        return float(frame["x-posn"].iloc[-1]), float(frame["y-posn"].iloc[-1])

    for name, expected in (("test19", -1.0), ("test20", 1.0)):
        x, _y = final(name)
        if np.sign(x) != expected:
            raise AssertionError(f"{name}: x is {x}, against cos(bearing) sign {expected}")
    aligned_x, aligned_y = final("test16")
    if aligned_y <= 0.0:
        raise AssertionError(f"test16: a 90 degree current should carry the plume +y: {aligned_y}")
    return abs(aligned_x)


def _termination_without_a_reason() -> float:
    """Traces ending away from a turning point with no boundary hit or step cap to explain it.

    Zero. Row 183's rule is that a run stops at the `switch + 1`-th turning point; the traces that
    do not are every one explained by another stated reason -- a bottom or surface hit, or the
    5001-step cap. Counting the *unexplained* ones is what makes this a rule rather than a
    tendency, and it is why the measurement excludes rather than averages.
    """
    from plumes2.io.dat import read_dat

    unexplained = 0
    checked = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if frame.empty:
            continue
        turning = [
            event.next_step
            for event in parsed.events
            if event.next_step
            and ("trap" in event.text.lower() or "maximum rise" in event.text.lower())
        ]
        if not turning:
            continue
        checked += 1
        last = int(frame.index[-1])
        texts = " ".join(event.text.lower() for event in parsed.events)
        boundary = "bottom" in texts or "surface" in texts
        if last - max(turning) > 5 and not boundary and last < 5000:
            unexplained += 1
    if checked < 50:
        raise AssertionError(f"only {checked} traces carried a turning point")
    return float(unexplained)


def _merge_trigger_bracket() -> float:
    """Width of the bracket the archive puts around the single-plume merge trigger.

    ⚠️ **This brackets the threshold; it does not determine it.** Every trapping event in the
    limiting-spacing runs either had merged already or had not, and the ratio of plume diameter to
    port depth separates the two cleanly. The trigger is somewhere in between, and the archive
    cannot say where.

    ⚠️ **Classification is per *event*, not per run** -- corrected by case30. The original form
    asked whether the *run* merged anywhere, which is the same question only while the banner
    lands on the trapping step. `gap_1` is the first run where it does not: it traps at 171 and
    merges at 192, so its first trapping is a genuine *not yet merged* observation at a ratio of
    0.7804. Reading it as merged would have thrown away the very evidence the run was made for.
    """
    from plumes2.io.dat import read_dat

    merged_at: list[float] = []
    unmerged_at: list[float] = []
    for path in sorted(_CASES.glob("case2[23]*/*.dat")) + sorted(_CASES.glob("case30*/*.dat")):
        parsed = read_dat(path)
        frame = parsed.nearfield
        depth = float(parsed.echoed_tables["Diffuser"]["P-depth"].iloc[0])
        index = frame.index.to_numpy()
        merges = [e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step]
        first_merge = min(merges) if merges else None
        for event in parsed.events:
            if event.next_step is None or "trap" not in event.text.lower():
                continue
            at = int(np.argmin(np.abs(index - event.next_step)))
            ratio = float(frame["P-dia"].iloc[at]) / depth
            already = first_merge is not None and first_merge <= event.next_step
            (merged_at if already else unmerged_at).append(ratio)
    if not merged_at or not unmerged_at:
        raise AssertionError("need both merging and non-merging trapping events to bracket")
    return min(merged_at) - max(unmerged_at)


def _multiport_merge_lag() -> float:
    """Steps between `d >= effective spacing` and the merging banner, worst over the archive. Zero.

    ⭐⭐⭐ **The measurement that separates two rules the archive had been reading as one.** Row
    191b recorded a merging banner lagging its trigger by 0 to 54 steps, and could not say what set
    the lag. Every one of those runs was **single-port**, where a banner can only come from UM3's
    limiting-spacing rule. case34 supplies the multiport comparison: four spacings from 0.3 to
    2.0 m and two port diameters, and the banner lands on the crossing step **every time**.

    ⚠️ Runs whose plumes already overlap at step 1 are skipped -- their trigger has nothing to wait
    for, so they cannot measure a lag. That is two of case34's six.

    ⚠️⚠️ **Oblique diffusers are skipped too, and finding that out was the point of row 51.**
    `Spacing` in the echo is the *nominal* value while the exe triggers on the effective one,
    `L |cos psi|`. On an oblique trace the nominal crossing therefore lands **after** the banner,
    the lag comes out negative, and `max()` was quietly discarding it -- so the answer was right
    only because every contributing trace happened to be square to the current. It is now a
    property rather than a coincidence: the skip is explicit and the measurement refuses to run if
    the guard stops being hit.

    ⚠️ And the Froude number does not rescue a single rule: these fire at `F` = 0.0045 with no lag
    at all, while a single-port run at `F` = 0.113 lags 23 steps. See case34's README.
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    measured = 0
    oblique = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        echo = parsed.echoed_tables.get("Diffuser")
        if echo is None or echo.empty or int(float(echo["Ports"].iloc[0])) <= 1:
            continue
        spacing = float(echo["Spacing"].iloc[0])
        banner = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
        )
        if banner is None or spacing <= 0.0:
            continue
        # ⚠️ `Spacing` is the **nominal** value and the exe triggers on the effective one,
        # `L |cos psi|` (rows 51, 181). Every trace this currently uses happens to be square to the
        # current, so the two coincide -- but "happens to" is not a property, and an oblique trace
        # added later would silently measure the crossing at the wrong step and report a lag that
        # is really a cosine. Refuse it instead.
        ambient = parsed.echoed_tables.get("Ambient")
        if ambient is None or "Amb-dir" not in ambient.columns:
            continue
        offset = float(echo["H-angle"].iloc[0]) - float(ambient["Amb-dir"].iloc[0])
        if abs(abs(np.cos(np.radians(offset))) - 1.0) > 1e-9:
            oblique += 1
            continue
        frame = parsed.nearfield
        steps = frame.index.to_numpy()
        diameter = frame["P-dia"].to_numpy(dtype=np.float64)
        reached = np.where(diameter >= spacing)[0]
        if not reached.size or int(steps[reached[0]]) <= int(steps[0]):
            # Already overlapping on the first printed row: no crossing to lag behind.
            continue
        worst = max(worst, float(banner - steps[reached[0]]))
        measured += 1
    if measured < 4:
        raise AssertionError(f"only {measured} multiport runs cross their spacing mid-trajectory")
    if oblique < 10:
        raise AssertionError(f"only {oblique} oblique traces skipped; the guard is not being hit")
    return worst


def _repeat_run_byte_difference() -> float:
    """Bytes that differ between the archive's one repeat pair. Zero.

    ⭐ `case30/gap_2.dat` and `case23/limspc_gap.dat` are the same inputs run five days apart in
    separate GUI sessions. Nothing else in the archive tests this, and everything in it assumes
    it: without determinism, a difference between two traces could be the exe rather than the
    inputs, and every one-run finding would be provisional.
    """
    a = (_CASES / "case30_limiting_spacing_bracket/gap_2.dat").read_bytes()
    b = (_CASES / "case23_limiting_spacing_gap/limspc_gap.dat").read_bytes()
    if len(a) != len(b):
        return float(abs(len(a) - len(b)) + min(len(a), len(b)))
    return float(sum(x != y for x, y in zip(a, b, strict=True)))


def _merge_symmetry_gap() -> float:
    """Difference in merge diameter-to-spacing between the 45 and 135 degree runs.

    ⭐ A symmetry check that needs no model at all. test17 discharges at 45 degrees into a 90 degree
    current and test18 at 135 -- mirror images about the current -- and both declare merging at the
    same `d/L`. Whatever sets the merge trigger therefore depends on the *magnitude* of the angle
    between the diffuser and the flow, not its sign, which is what `|sin psi|` gives and a signed
    form would not.
    """
    from plumes2.io.dat import read_dat

    ratios = []
    for name in ("test17", "test18"):
        parsed = read_dat(_CASES / f"case16_oldbuild_angle_sweep/{name}.dat")
        spacing = float(parsed.echoed_tables["Diffuser"]["Spacing"].iloc[0])
        merged = [e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step]
        if not merged:
            raise AssertionError(f"{name}: no merging event")
        index = parsed.nearfield.index.to_numpy()
        at = int(np.argmin(np.abs(index - merged[0])))
        ratios.append(float(parsed.nearfield["P-dia"].iloc[at]) / spacing)
    return abs(ratios[0] - ratios[1])


def _surface_overshoot_ratio() -> float:
    """Dilution at the exe's stop over dilution at surface contact. 1.0859.

    Row 258b, and it is what **survives** row 258 once the checkbox is accounted for. case31's
    `surface_on` runs at output interval 1, so contact is bracketed to a single step: `|Depth| -
    P-dia/2` crosses zero between step 260 (+0.0080 m) and 261 (-0.0480 m). The `Plume surfaces`
    banner and the last row are both at **275** -- fourteen steps later, by which point the plume
    edge is 0.7285 m through the free surface and the printed dilution has climbed from 156.331 to
    169.754.

    The step count is asserted rather than returned, because the claim is the pair: fourteen steps
    late *and* 8.6 % of spurious dilution. Either alone would be ambiguous.

    ⚠️ **Nothing marks 275.** It is not a threshold on the overshoot depth, on the diameter or on
    the dilution -- the same shape as row 191b's merging banner lagging its own trigger by 0-54
    steps. Two different events, both detected late, in a solver whose step controller targets 2 %
    mass growth per step.

    ⚠️ This is the exe's error, not ours, and it is the residue of what was once a **40 %**
    headline: row 258's endpoint gap turned out to be a `stop at surface` mismatch (row 104), and
    once matched the trajectories agree to 1.9 %. What is left is an order of magnitude smaller and
    genuinely unexplained. ⭐ Predicted before the run as contact at 260 +/- 1.
    """
    parsed = _dat("reference_cases/case31_surface_stop_pair/surface_on.dat")
    frame = parsed.nearfield
    steps = frame.index.to_numpy()
    clearance = np.abs(frame["Depth"].to_numpy(dtype=np.float64)) - (
        frame["P-dia"].to_numpy(dtype=np.float64) / 2.0
    )
    past = np.flatnonzero(clearance <= 0.0)
    if not past.size:
        raise AssertionError("surface_on no longer reaches the surface")
    first = int(past[0])
    banner = next(e.next_step for e in parsed.events if "surface" in e.text.lower() and e.next_step)
    if banner != int(steps[-1]):
        raise AssertionError("the banner is no longer on the terminating row")
    if banner - int(steps[first]) != 14:
        raise AssertionError(f"the overshoot is {banner - int(steps[first])} steps, not 14")
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    return float(dilution[-1] / dilution[first])


# ------------------------------------------------------- Phase 5, the trace-only remainder
#
# The rows §9 called "event sequences and termination facts that need no model". Two kinds, and
# the distinction is worth keeping straight because it decides what the target is evidence *of*:
#
#   * where a project exists, our trajectory is measured against the exe's -- rows 19, 20, 26, 27;
#   * where none does (case05-07, case12 have no `.prj`), the target measures the **exe's own
#     trace** -- rows 4, 52, 62, 63, 71, 90. Those still earn their place: each is a qualitative
#     claim the ledger rests on elsewhere, and each guards the reader and the archive against a
#     trace being replaced or misparsed. What they are *not* is evidence about our solver, and
#     their notes say so rather than letting a green row imply it.


def _turning_point_kinds(trace: str, project: str, expected: tuple[str, ...]) -> list[float]:
    """Relative time error at each of the exe's turning points, having checked the kinds match.

    Raises if the **sequence of kinds** differs, because that is the qualitative half of the claim
    and a timing residual computed against the wrong kind of event is a number about nothing.
    """

    parsed = _dat(trace)
    frame = parsed.nearfield
    banners = [
        (e.text.strip().lower(), e.next_step)
        for e in parsed.events
        if e.next_step in frame.index
        and ("trap" in e.text.lower() or "local maximum" in e.text.lower())
    ]
    if tuple(("trap" if "trap" in text else "reversal") for text, _ in banners) != expected:
        raise AssertionError(f"{trace}: banner sequence is no longer {expected}")
    solution = _integrate_once(_case(project), max_time=float(frame["Time"].iloc[-1]) + 5.0)
    ours = [(o.kind.value, o.time) for o in solution.oscillations][: len(expected)]
    if tuple(kind for kind, _ in ours) != expected:
        raise AssertionError(
            f"{trace}: our turning points are {[k for k, _ in ours]}, not {expected}"
        )
    errors = []
    for (_text, step), (_kind, time) in zip(banners, ours, strict=True):
        theirs = float(frame["Time"].loc[step])
        errors.append(abs(time - theirs) / theirs)
    return errors


def _case01_turning_point_error() -> float:
    """Worst relative timing error over case01's four turning points. 8.55 %, on the first trap.

    Row 20. The **sequence** is what the row records -- reversal, trap, reversal, trap -- and our
    solver reproduces it exactly in kind and order; the measurement asserts that and then returns
    the timing residual, which is the part that carries a number.

    ⚠️ Worst on the *first* trap and best on the second (0.30 %), which is the late-trajectory
    drift of row 17 seen from the time axis rather than the dilution axis: the trajectory arrives
    at each turning point slightly early, and the error does not accumulate. Row 183 measures the
    same thing archive-wide as a mean 3.4 % on the end time.
    """
    return max(
        _turning_point_kinds(
            _CASE01_TRACE, _CASE01_PROJECT, ("reversal", "trap", "reversal", "trap")
        )
    )


def _case01_depth_extrema_error() -> float:
    """Worst error at case01's two depth extrema. 0.0235 m, at the second.

    Row 19. The exe prints -1.081 m at step 265 and -1.726 m at step 380; ours, sampled at the
    same times, gives -1.0714 and -1.7025.

    ⚠️ The tolerance is **not** the printed resolution. `Depth` prints three decimals, so 0.0235 m
    is twenty-three times what the trace can resolve -- this is our trajectory error, not a
    rounding comparison, and pretending otherwise would make the row look far stronger than it is.
    The bound is set from the drift row 17 already records, and both extrema sit in the oscillating
    stretch where that drift lives.
    """
    frame = _dat(_CASE01_TRACE).nearfield
    times = frame["Time"].to_numpy(dtype=np.float64)
    sampled = _run(_CASE01_PROJECT).solution.sample(times)
    steps = frame.index.to_numpy()
    worst = 0.0
    for step in (265, 380):
        position = int(np.flatnonzero(steps == step)[0])
        worst = max(worst, abs(float(sampled.z[position]) - float(frame["Depth"].loc[step])))
    return worst


#: case02 has **no `.prj`**. case03's describes it: the two are bit-identical over every shared
#: hydrodynamic column, which is what row 24 established and what licenses using one project for
#: case02, case03 and case04 alike.
_CASE02_TRACE = "reference_cases/case02_macoma_mgd/Macomatest1.dat"
_CASE03_PROJECT = "reference_cases/case03_macoma_carbonate/test.prj"


def _case02_turning_point_error() -> float:
    """Worst relative timing error over case02's four turning points. 8.89 %, on the first.

    Row 26, and the same measurement as row 20 on the case the unit flag changes (row 28): case02
    is case01's project read as MGD instead of m3/s, so it runs at 23x the flow. The sequence is
    again reversal, trap, reversal, trap, reproduced exactly in kind.

    ⚠️ The worst residual is on the **first** reversal, at t = 1.78 s -- a 0.16 s absolute error on
    the earliest event in the trace, where a relative measure is at its harshest. The three later
    points run 1.53-3.61 %.
    """
    return max(
        _turning_point_kinds(
            _CASE02_TRACE, _CASE03_PROJECT, ("reversal", "trap", "reversal", "trap")
        )
    )


def _case02_endpoint_error() -> float:
    """Relative error in case02's final flux-averaged dilution. 3.12 %.

    Row 27. The exe ends at 562.633 with a 0.558 m diameter; ours reaches 545.103 and 0.5507 at
    the same time, so 3.12 % and 1.30 %.

    ⚠️ **Worse than row 24's 0.858 % whole-trace figure, and it should be.** This is the *endpoint*
    of a long oscillating trace, which is exactly the window row 17 measured at 1.73 % against
    0.46 % in the jet. Quoting a whole-trace mean here would understate what a reader asking "how
    close is the final dilution" actually gets. Reported as the dilution error because that is what
    the row leads with; the diameter is the smaller of the two.
    """

    frame = _dat(_CASE02_TRACE).nearfield
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(_case(_CASE03_PROJECT), max_time=float(times[-1]) + 5.0)
    ours = solution.sample(times)
    theirs = float(frame["Dilutn"].iloc[-1])
    return abs(float(ours.dilution[-1]) - theirs) / theirs


def _merging_suppression_ratio() -> float:
    """Dilution growth after case05's merge over the growth before it. 0.808.

    Row 52, and it is the observation the whole merging closure was built to reproduce: crossing
    the banner, the plume's dilution growth per five steps drops from 2.158 to 1.744 with nothing
    else in the run changing. Entrainment is suppressed because neighbouring plumes have occluded
    part of each element's surface.

    ⚠️ **This measures the exe, not us.** case05 has no `.prj`, so there is no model run to compare
    against; what the row pins is the size of the effect our closure has to produce, and rows 157
    and 177 are where the closure itself is measured. A single step either side rather than a
    window, because the suppression is not constant -- it deepens as the overlap does, which is
    what case40 then took to `d/L` 4 (row 157b).
    """
    parsed = _dat("reference_cases/case05_macoma_merging/test4_TxtOutputs.dat")
    frame = parsed.nearfield
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
    steps = frame.index.to_numpy()
    position = int(np.flatnonzero(steps == banner)[0])
    before = dilution[position - 1] - dilution[position - 2]
    after = dilution[position + 1] - dilution[position]
    if before <= 0.0:
        raise AssertionError("case05's dilution is not growing before the banner")
    return float(after / before)


def _event_sequence_violations(trace: str, expected: tuple[tuple[str, int], ...]) -> float:
    """Banners in `trace` that do not match `expected`, as `(fragment, step)`. Zero.

    Counting violations rather than measuring a distance is deliberate: these are orderings, and
    "how far out" has no meaning for a sequence that is either right or wrong.
    """
    parsed = _dat(trace)
    banners = [
        (e.text.strip().lower(), e.next_step) for e in parsed.events if e.next_step is not None
    ]
    wrong = 0.0
    for fragment, step in expected:
        if not any(fragment in text and at == step for text, at in banners):
            wrong += 1.0
    return wrong


def _golden_trace_event_order() -> float:
    """Whether upstream's shipped trace still traps, merges and surfaces at 255 / 260 / 275. Zero.

    Row 4, and the ordering is the finding: the plume **traps before it merges**, and merges before
    it surfaces, which is not the order anyone would assume and is the same point row 63 makes on
    case06. Rows 191 and 51 depend on the merge banner meaning what it says here.

    ⚠️ **This is not a comparison with our solver, and it cannot be**: the shipped trace prints no
    `Time` column -- only Dilutn, P-dia, x-posn, y-posn and Depth -- so there is no axis to sample
    a trajectory at. That is also why row 5 is retired rather than measured; see the ledger. What
    this guards is the archive and the reader: if the file were replaced or the banner parser
    regressed, the ordering every one of those rows rests on would move silently.
    """
    return _event_sequence_violations(
        "upstream/Example_project/ModelResults_TxtOutputs.dat",
        (("plume traps", 255), ("merging", 260), ("plume surfaces", 275)),
    )


def _surfacing_run_continues() -> float:
    """Whether case06 still surfaces at 260 and carries on to a turning point at 356. Zero.

    Row 62. A positively buoyant plume reaching the surface does **not** end the run: the exe
    prints `Plume surfaces` at step 260 and then keeps integrating through a reversal at 280, a
    trap at 320 and a final reversal at 356.

    ⚠️ That is what makes `stop at surface` a *termination* switch rather than a physics option
    (row 104), and it is the behaviour row 258 needed in order to read case13's endpoint gap as a
    settings mismatch instead of a closure error. ⚠️ Measures the exe's trace; case06 has no
    `.prj`.
    """
    return _event_sequence_violations(
        "reference_cases/case06_macoma_arag_s36/test5_TxtOutputs.dat",
        (("plume surfaces", 260), ("local maximum", 356)),
    )


def _trapping_precedes_merging() -> float:
    """Whether case06 still traps at 195 before merging at 210. Zero.

    Row 63. Trapping and merging are independent benchmarks and either can come first -- here the
    plume reaches neutral buoyancy 15 steps before its neighbours touch it.

    ⚠️ **This is the observation that retired half of row 191's original reading.** The
    limiting-spacing rule had been recorded as "checked at trapping" because case22 and case23 had
    the trap and the diameter crossing on the same step; case30 separated them and case06 shows the
    two benchmarks were never tied in the first place. ⚠️ Measures the exe's trace.
    """
    return _event_sequence_violations(
        "reference_cases/case06_macoma_arag_s36/test5_TxtOutputs.dat",
        (("plume traps", 195), ("merging", 210)),
    )


def _dense_plume_trap_depth() -> float:
    """How far case07's dense plume stops short of the seabed. 13.797 m.

    Row 71. A 45 psu effluent into a ~31 psu ambient sinks, and the question the row settles is
    whether it reaches the bed: it turns at **-3.203 m** against a seabed at 17 m (port depth 2 plus
    15 m elevation), carrying a dilution of 211.856 there. So it traps on buoyancy, and the seabed
    benchmark never fires.

    ⚠️ The margin is large -- this is not a near miss -- and that is worth stating plainly, because
    the row's phrasing ("no bottom hit") reads as though it were close. What makes case07 valuable
    is the *inversion*: a sinking plume runs its trapping and reversal benchmarks in the opposite
    vertical order, which is the case row 183's ordinal switch had to survive. ⚠️ Measures the
    exe's trace; case07 has no `.prj`.
    """
    frame = _dat("reference_cases/case07_macoma_s45_dense/test6_TxtOutputs.dat").nearfield
    deepest = float(frame["Depth"].to_numpy(dtype=np.float64).min())
    seabed = _case(_CASE01_PROJECT).diffuser.bottom_depth
    return seabed - abs(deepest)


def _shoreline_checkbox_inert() -> float:
    """How far case12's plume travels past the shoreline it was told about. 5.389 m.

    Row 90. case12 is the only archived run with the shoreline box **ticked**, and its plume walks
    straight through: the largest `y-posn` is 5.389 m, well past the boundary the feature is
    supposed to represent, with no reflection and no advisory.

    ⚠️ **Stronger than row 72, and for a specific reason.** Row 72 shows the shoreline *vector* has
    no effect by comparing case08 with case05; this one shows the *checkbox* has none either, which
    is the half a reader would assume was doing the work. Together they are the inert-shoreline
    finding on the SSMC list. ⚠️ Still an inference from one run rather than a controlled pair --
    §7.1's outstanding ask is case12 rerun with the box cleared, which would make it airtight.
    ⚠️ Measures the exe's trace; case12 has no `.prj`.
    """
    frame = _dat("reference_cases/case12_macoma_shoreline_enabled/test13_TxtOutputs.dat").nearfield
    return float(np.nanmax(np.abs(frame["y-posn"].to_numpy(dtype=np.float64))))


def _trace_inference_mismatches() -> float:
    """Inputs inferred from case18's trace alone that its later `.prj` contradicts. Zero.

    Row 144, and it is a claim about *method* with a number behind it. Before any project file for
    case18 existed, four inputs were read out of the trace: port diameter 0.0127 m and total flow
    0.005 m3/s from the two-decimal diffuser echo (row 141), the aspiration coefficient 0.1 from
    the measured Taylor entrainment (row 140), and the contraction coefficient 0.61 from the initial
    velocity. `test21.prj` arrived later and agrees with all four exactly.

    ⚠️ Worth keeping executable rather than retiring as history: it is the evidence that trace-only
    inference is sound, and half the archive's projects are still missing (case02, case05-07,
    case12, case20, case21), so the method is load-bearing rather than a past convenience. If the
    project were edited, this row is what would notice that the inference no longer matches.
    """
    case = _case(_SWEEP_PROJECT)
    expected = {
        "port diameter": (case.diffuser.port_diameter, 0.0127),
        "total flow": (case.effluent.flow, 0.005),
        "aspiration": (case.near_field.aspiration_coefficient, 0.1),
        "contraction": (case.near_field.contraction_coefficient, 0.61),
    }
    return float(sum(1 for actual, inferred in expected.values() if actual != inferred))


# --------------------------------------------------------------------- Phase 5, merging
#
# Rows 157-186. Everything here shares two reconstructions -- case20's spacing sweep and case40's
# deep-overlap sweep -- so both are memoised. Note case20 and case21 have **no `.prj`** and are
# rebuilt from case18's project plus the `.dat` diffuser echo (mind the two-decimal echo trap,
# section 7.1e); case40 ships its own, which round-trips byte-exactly.

#: case20's geometry: 25 ports at 0.005 m3/s in a 0.02 m/s current, spacing swept.
_CASE20 = "reference_cases/case20_spacing_sweep"
_CASE40 = "reference_cases/case40_deep_overlap_spacing"


@cache
def _case20_case(spacing: float) -> Case:
    base = _case("reference_cases/case18_zero_current_pair/test21.prj")
    levels = [level.model_copy(update={"current_speed": 0.02}) for level in base.ambient.levels]
    return base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(update={"n_ports": 25, "port_spacing": spacing}),
            "effluent": base.effluent.model_copy(update={"flow": 0.005}),
            "ambient": base.ambient.model_copy(update={"levels": levels}),
        }
    )


@cache
def _merging_error(
    run: str,
    spacing: float,
    *,
    faithful_decrements: bool = True,
    implicit_inflation: bool = True,
    faithful_inflation: bool = False,
    confined: str = "all",
) -> tuple[float, float, float, float]:
    """`(dilution MARE, post-merge MARE, diameter MARE, our max diameter)` on a case20 run.

    Sampled at the exe's own printed times, so the comparison is of trajectories rather than of
    step controllers. The first three keywords are rows 178-180's controls; `confined` is row
    264's candidate fix, which is a different kind of thing -- see `ConfinedDecrements`.
    """
    from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

    parsed = _dat(f"{_CASE20}/{run}.dat")
    frame = parsed.nearfield
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(
        _case20_case(spacing),
        max_time=float(times[-1]) + 1.0,
        merging=MergingChoices(
            faithful_decrements=faithful_decrements,
            implicit_inflation=implicit_inflation,
            faithful_inflation=faithful_inflation,
            confined_decrements=ConfinedDecrements(confined),
        ),
    )
    usable = times <= solution.solution.t[-1]  # type: ignore[attr-defined]
    ours = solution.sample(times[usable])
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)[usable]
    diameter = frame["P-dia"].to_numpy(dtype=np.float64)[usable]
    error = np.abs(ours.dilution - dilution) / dilution
    banner = next(
        (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
    )
    steps = frame.index.to_numpy()[usable]
    late = steps >= banner if banner is not None else steps >= steps[-1]
    return (
        float(error.mean()),
        float(error[late].mean()),
        float((np.abs(ours.diameter - diameter) / diameter).mean()),
        float(ours.diameter.max()),
    )


def _merging_cost_at_moderate_overlap() -> float:
    """test32's post-merge dilution MARE. **5.24 %**, against the unmerged control's 1.39 %.

    ⚠️⚠️ **Renamed and re-baselined 2026-08-21**, when the default became
    `ConfinedDecrements.ALL`. It was `_merging_costs_no_accuracy` and read **1.01 %** -- a name
    that asserted a claim the ledger has since retracted, which is a documented failure mode of
    this project rather than a tidy-up. ⛔ That 1.01 % sat *below* its own unmerged control's
    1.39 %, and an error smaller than the same case run with no merging at all is the signature of
    cancelling errors, not of correctness; it is why the default moved despite this being the one
    run that preferred the old reading. Row 264c keeps the retired number, and case44 replaces this
    run with six spacings against a single-port control.

    ⚠ **That bar -- "no worse than the same case without it" -- is retired.** It was the
    right instinct and the wrong test: an error *below* the unmerged control means errors are
    cancelling, not that merging is free.
    test31 is that control -- identical but for a spacing wide enough never to merge -- and both
    runs carry the archive's common late-trajectory drift, so the *difference* is what merging
    owns. It comes out **below** the control, meaning merging contributes no detectable error.

    Scoped to `d/L` <= 2.35, and the scope is the finding. test32 is the deepest overlap case20
    reaches. case40's test58, at `d/L` 4.05, is 28.8 % post-merge against a 2.10 % control on the
    same geometry -- see `_deep_overlap_penalty`. So this row is not "merging is right", it is
    "merging is right while the overlap is shallow", and row 157b is where it stops.
    """
    return _merging_error("test32", 1.0)[1]


def _unmerged_control_error() -> float:
    """test31's post-merge-window dilution MARE. 1.39 % -- the control for the row above.

    Without this number the 1.01 % above means nothing: it could be a small error or a large one
    depending on what the same case does *unmerged* over the same window. Measured on the same
    steps, so the late-trajectory drift is common to both.
    """

    parsed = _dat(f"{_CASE20}/test32.dat")
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    frame = _dat(f"{_CASE20}/test31.dat").nearfield
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(_case20_case(2.0), max_time=float(times[-1]) + 1.0)
    usable = times <= solution.solution.t[-1]  # type: ignore[attr-defined]
    ours = solution.sample(times[usable])
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)[usable]
    error = np.abs(ours.dilution - dilution) / dilution
    return float(error[frame.index.to_numpy()[usable] >= banner].mean())


def _explicit_inflation_penalty() -> float:
    """Post-merge MARE with eq 56 read explicitly, `phi` at `b_r`. 3.22 % against 1.01 %.

    Row 178's control. Eq 56 is **implicit** -- `phi` is set by the element's actual half-width,
    the merged `b` the equation solves for, not by the round-equivalent `b_r`. Evaluating at `b_r`
    under-inflates by 12 % deep in the overlap, which left our merged diameter sitting at its
    *unmerged* value: 2.059 m here against the exe's 2.351 m.

    Reported as the control's own error rather than as a ratio, so the page shows both numbers.
    """
    return _merging_error("test32", 1.0, implicit_inflation=False)[1]


def _true_geometry_penalty() -> float:
    """Post-merge MARE with eqs 51-54 on the true `arccos`. 4.04 % against 1.01 %.

    Row 179. The exe reproduces UM3's `arctan(sqrt((b^2-s^2)/s))` -- the division inside the
    radical, dimensionally inconsistent, correct only at `s = 1 m`. Using the real geometry
    quadruples the post-merge error, which is what makes the bug the *measured* reading rather
    than a charitable one. `faithful=False` on `overlap_angle` selects the physics.
    """
    return _merging_error("test32", 1.0, faithful_decrements=False)[1]


def _inconsistent_angle_penalty() -> float:
    """Post-merge MARE with eq 56 *also* on the buggy angle. 4.64 % against 1.01 %.

    Row 180, and the least comfortable finding in the merging block. The exe is **inconsistent
    between its own two angles**: eqs 51-54's decrements match the buggy `arctan`, while eq 56's
    inflation matches the true `arccos`. Making eq 56 buggy too -- the self-consistent reading
    anyone would prefer -- is the *worst* of the four combinations.

    Not a reading we would have chosen. Each half was measured separately and each is reproduced
    as found.
    """
    return _merging_error("test32", 1.0, faithful_inflation=True)[1]


#: case40's oblique sweep: `(run, spacing, horizontal angle)`. The first two are square to the
#: current at two spacings; the last three fix the spacing and move only the angle.
_CASE40_TRIGGERS = (
    ("test58", 0.25, 90.0),
    ("test57", 0.50, 90.0),
    ("test60", 0.75, 85.0),
    ("test61", 0.75, 75.0),
    ("test62", 0.75, 65.0),
)


def _case40_bracket(run: str, spacing: float) -> tuple[float, float]:
    """`d/L` on the rows either side of the exe's merging banner. One output step wide."""
    parsed = _dat(f"{_CASE40}/{run}.dat")
    banner = next(
        (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
    )
    if banner is None:
        raise AssertionError(f"{run} no longer merges")
    diameters = parsed.nearfield["P-dia"]
    return float(diameters.loc[banner - 1]) / spacing, float(diameters.loc[banner]) / spacing


def _oblique_trigger_misses() -> float:
    """How far outside its bracket our merge trigger lands, worst of case40's five runs. Zero.

    **The test row 181 never had.** Its 85/30/0 degree evidence came from three *different* cases,
    so the geometry moved along with the angle and no single run isolated it. case40 fixes the
    spacing at 0.75 m and moves only the discharge azimuth -- 85, 75, 65 degrees against a
    90 degree current -- plus two square-on spacings for the ends.

    Resolving `psi` against the plume's **instantaneous** heading lands inside all five brackets
    with no fitted constant. The static law -- `|sin psi|` at the fully-turned-over angle -- falls
    *below* the bracket at 75 and 65 degrees, by 1.2 % and 5.4 %, which is what excludes it.

    Returns the worst distance outside a bracket, so zero means every run landed inside. The
    brackets are one output step wide (interval 1), i.e. about 1 % -- tight enough that five hits
    are not luck.
    """
    from plumes2.nearfield.merging import effective_half_spacing

    base = _case(f"{_CASE40}/Macoma2.prj")
    worst = 0.0
    for run, spacing, angle in _CASE40_TRIGGERS:
        low, high = _case40_bracket(run, spacing)
        case = base.model_copy(
            update={
                "diffuser": base.diffuser.model_copy(
                    update={"port_spacing": spacing, "horizontal_angle": angle}
                )
            }
        )
        solution = _integrate_once(case, max_time=60.0)
        times = np.linspace(0.0, float(solution.solution.t[-1]), 30000)  # type: ignore[attr-defined]
        ours = solution.sample(times)
        raw = solution.solution.sol(times)  # type: ignore[attr-defined]
        velocity = raw[1:4] / raw[0]
        effective = np.array(
            [
                2.0 * effective_half_spacing(spacing, angle + 90.0, velocity[:, i])
                for i in range(times.size)
            ]
        )
        fired = np.flatnonzero(ours.diameter >= effective)
        if not fired.size:
            raise AssertionError(f"{run}: our closure never merges")
        ratio = float(ours.diameter[fired[0]]) / spacing
        worst = max(worst, max(0.0, low - ratio, ratio - high))
    return worst


def _static_spacing_law_misses() -> float:
    """The same five brackets, judged against the **static** `|sin psi|`. 0.0596 at 65 degrees.

    The control for the row above, and the reason it means something. A static law evaluated at
    the fully-turned-over angle cannot express that merging fires *mid-turn*, so it sits below the
    bracket -- here by up to 5.4 %, against brackets about 1 % wide.
    """
    worst = 0.0
    for run, spacing, angle in _CASE40_TRIGGERS:
        low, high = _case40_bracket(run, spacing)
        static = abs(math.sin(math.radians((angle + 90.0) - 90.0)))
        worst = max(worst, max(0.0, low - static, static - high))
    return worst


#: case21's prediction test: `(run, spacing, directory)` at a fixed 85 degree offset, only the
#: spacing changing. test19 is the run the law was checked against; test34 and test35 were
#: generated *after* the prediction was written down.
_SPACING_PREDICTION = (
    ("test19", 2.0, "reference_cases/case16_oldbuild_angle_sweep"),
    ("test35", 1.5, "reference_cases/case21_merging_spacing_prediction"),
    ("test34", 1.0, "reference_cases/case21_merging_spacing_prediction"),
)


def _spacing_prediction_misses() -> float:
    """Worst distance outside its bracket over case21's three spacings. 0.0009, on test35.

    Row 182, and it is a **prediction** rather than a fit: test34 and test35 were run after the
    number was written down. At one fixed 85 degree offset a static law must predict a single
    value; the derived law predicts a curve, because a wider spacing means merging fires later, by
    which time the plume has turned further and the effective spacing has shrunk.

    | run | spacing | exe bracket | derived | ellipse |
    |---|---|---|---|---|
    | test19 | 2.0 m | 0.5985-0.6015 | 0.5991 | 0.600 |
    | test35 | 1.5 m | 0.6760-0.6800 | 0.6751 | 0.600 |
    | test34 | 1.0 m | 0.7700-0.7780 | 0.7750 | 0.600 |

    The fitted ellipse is flat at 0.600 and is excluded by 13 % at 1.5 m and 23 % at 1.0 m.

    Be precise about test35: 0.6751 lands **0.0009 below** its bracket -- a 0.13 % miss, inside our
    own trajectory error on these runs (dilution MARE 1.0-1.2 %), but a miss. So this is two clean
    hits and one near-miss, and the reference is the near-miss rather than zero, because rounding
    it to a hit is how a validation suite stops meaning anything. case40's five-bracket sweep is
    the independent confirmation that the near-miss is noise rather than bias (row 181).

    These runs have **no `.prj`** -- the project was reset to the base before it was copied -- so
    the case is rebuilt from test19's geometry with the spacing changed, which is what the `.dat`
    diffuser echo records. Mind the two-decimal echo trap: `P-dia` of 0.01 is 0.0127.
    """
    from plumes2.io.dat import read_dat
    from plumes2.nearfield.merging import effective_half_spacing

    base = _case("reference_cases/case18_zero_current_pair/test21.prj")
    worst = 0.0
    for run, spacing, directory in _SPACING_PREDICTION:
        parsed = read_dat(_ROOT / directory / f"{run}.dat")
        banner = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
        )
        if banner is None:
            raise AssertionError(f"{run} no longer merges")
        diameters = parsed.nearfield["P-dia"]
        low = float(diameters.loc[banner - 1]) / spacing
        high = float(diameters.loc[banner]) / spacing
        case = base.model_copy(
            update={
                "diffuser": base.diffuser.model_copy(
                    update={"n_ports": 25, "port_spacing": spacing, "horizontal_angle": 175.0}
                ),
                "effluent": base.effluent.model_copy(update={"flow": 0.005}),
            }
        )
        solution = _integrate_once(case, max_time=250.0)
        times = np.linspace(0.0, float(solution.solution.t[-1]), 20000)  # type: ignore[attr-defined]
        ours = solution.sample(times)
        raw = solution.solution.sol(times)  # type: ignore[attr-defined]
        velocity = raw[1:4] / raw[0]
        effective = np.array(
            [
                2.0 * effective_half_spacing(spacing, 175.0 + 90.0, velocity[:, i])
                for i in range(times.size)
            ]
        )
        fired = np.flatnonzero(ours.diameter >= effective)
        if not fired.size:
            raise AssertionError(f"{run}: our closure never merges")
        ratio = float(ours.diameter[fired[0]]) / spacing
        worst = max(worst, max(0.0, low - ratio, ratio - high))
    return worst


@cache
def _case40_error(run: str, spacing: float) -> tuple[float, float, float]:
    """`(post-merge dilution MARE, our max diameter, exe max diameter)` on a case40 run.

    Only the finite prefix is used: a 2 psu effluent surfaces in ~30 s and, with `stop at surface`
    off, every column then goes NaN to the 5001-step cap -- rows 253 and 258's missing clamp, on a
    third geometry.
    """

    parsed = _dat(f"{_CASE40}/{run}.dat")
    frame = parsed.nearfield
    finite = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
        frame["Dilutn"].to_numpy(dtype=np.float64)
    )
    frame = frame[finite]
    base = _case(f"{_CASE40}/Macoma2.prj")
    case = base.model_copy(
        update={"diffuser": base.diffuser.model_copy(update={"port_spacing": spacing})}
    )
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(case, max_time=float(times[-1]) + 1.0)
    usable = times <= solution.solution.t[-1]  # type: ignore[attr-defined]
    ours = solution.sample(times[usable])
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)[usable]
    error = np.abs(ours.dilution - dilution) / dilution
    banner = next(
        (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
    )
    steps = frame.index.to_numpy()[usable]
    window = steps >= banner if banner is not None else np.ones(steps.size, dtype=bool)
    return (
        float(error[window].mean()),
        float(ours.diameter.max()),
        float(frame["P-dia"].to_numpy(dtype=np.float64).max()),
    )


#: case41's unmerged control: 25 ports at a **5 m** spacing, where ordinary merging never happens.
#: ⚠️ It is only clean up to its **own** limiting-spacing banner at step 373 -- see row 261, which
#: is the finding that came out of trying to use it.
_CASE41_CONTROL = "test68"


@cache
def _suppression_samples() -> tuple[tuple[float, float], ...]:
    """`(d/L, suppression)` from the exe, over the three 35 psu spacings. 483 samples.

    The suppression is the **fractional entrainment rate** of a merged run over the unmerged
    control's at the same instant, `d(ln D)/dt` either side. Two things make that the right
    quantity rather than the per-step mass gain case20's README uses:

    * it is **free of the step controller**. The controller picks `dt` so that each step gains
      about 2 % of mass, so a per-step gain reads 0.02 on any run that is not otherwise limited and
      carries no information -- which is exactly why case40 could not be used for this. Dividing by
      `dt` recovers the physical rate the controller was responding to.
    * it is a **ratio against a real run**, so the ambient profile, the trajectory and the
      equation of state all cancel. What is left is what merging did.

    Restricted to the window where the merged run **is** merged and the control still **is not**.
    """
    from plumes2.io.dat import read_dat

    def finite(run: str):  # type: ignore[no-untyped-def]
        parsed = read_dat(_ROOT / _CASE41 / f"{run}.dat")
        frame = parsed.nearfield
        keep = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
            frame["Dilutn"].to_numpy(dtype=np.float64)
        )
        banner = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
        )
        return frame[keep], banner

    control, control_banner = finite(_CASE41_CONTROL)
    if control_banner is None:
        raise AssertionError("the control no longer prints a banner; row 261 has changed")
    control_time = control["Time"].to_numpy(dtype=np.float64)
    control_rate = np.gradient(
        np.log(control["Dilutn"].to_numpy(dtype=np.float64)), control_time
    )
    clean_until = float(control.loc[control_banner, "Time"])

    samples: list[tuple[float, float]] = []
    for run, spacing, salinity in _CASE41_RUNS:
        if salinity != 35.0:
            continue
        frame, banner = finite(run)
        if banner is None:
            raise AssertionError(f"{run} no longer merges")
        times = frame["Time"].to_numpy(dtype=np.float64)
        window = (times > float(frame.loc[banner, "Time"])) & (times < clean_until)
        if window.sum() < 20:
            raise AssertionError(f"{run}: only {window.sum()} steps overlap the clean control")
        rate = np.gradient(np.log(frame["Dilutn"].to_numpy(dtype=np.float64)), times)
        ratio = rate[window] / np.interp(times[window], control_time, control_rate)
        diameters = frame["P-dia"].to_numpy(dtype=np.float64)[window] / spacing
        samples.extend(zip(diameters.tolist(), ratio.tolist(), strict=True))
    return tuple(samples)


@cache
def _knudsen_worst_density_error() -> float:
    """Worst |printed P-Den - Knudsen| over every trace that prints S, T and density. **0.00098**.

    Row 262. **107** distinct traces carry `P-Sal`, `P-Temp` and `P-Den` on the same row, so the
    of state is directly invertible -- no reconstruction from dilution, which is how row 101's
    0.036 and row 108's -0.0275 were obtained and why both read as offsets rather than as a
    different formula.

    ⭐⭐⭐ **This is an identification, not a fit.** Zero free parameters, and the worst residual
    over 51 670 rows spanning S 0-45 psu is **one digit of a three-decimal column**. The controls
    are what make that mean something: EOS-80 gives 0.0629 on the same rows, Eckart (1958) 0.2098,
    and a seven-parameter least-squares correction to EOS-80 only reaches 0.0168. Fitting anything
    on top of Knudsen leaves the rms at 0.00037 unchanged.

    ⚠️ The tolerance is the printed resolution itself, 0.001, because that is the most the
    reference can resolve -- not a band chosen around what the code happens to produce.
    """
    from plumes2.io.dat import read_dat
    from plumes2.seawater import knudsen_density

    worst = 0.0
    rows = 0
    for path in _archive_traces():
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
        if not keep.any():
            continue
        rows += int(keep.sum())
        worst = max(worst, float(np.abs(d[keep] - knudsen_density(s[keep], t[keep])).max()))
    # ⚠️ Pinned tightly on purpose. This count was published as 38 951 until 2026-08-21 and had
    # drifted **twice over**: up, because case42-case44 added traces, and down, because the
    # archive holds ten byte-duplicate groups that were being counted twice (6.5 % of the rows).
    # `_archive_traces` removes the duplicates; a loose floor here is what let the figure rot.
    # ⚠️ This band has now caught the drift twice in one day, which is what it is for: 38 951
    # became 51 670 when case42-44 landed and the duplicates were removed, then 51 670 when
    # case45's nine traces did. A loose floor let the first drift sit for two days unnoticed.
    if not 50_000 <= rows <= 62_000:
        raise AssertionError(
            f"{rows} rows carry S, T and density; row 262 expects ~51 670 over 116 distinct "
            "traces. If the archive grew, re-derive the figure everywhere it is published -- "
            "`grep -rn '51 670'` finds every place."
        )
    return worst


def _merged_suppression_plateau() -> float:
    """The exe's merged entrainment suppression, averaged over `d/L >= 1.5`. **0.596**.

    ⭐⭐⭐ **The law the merging closure has to hit, and it is a plateau rather than a decline.**
    Across three spacings and 483 samples the suppression saturates and stays there:

    | `d/L` | suppression | samples |
    |---|---|---|
    | 1.5-3 | 0.606 +/- 0.114 | 188 |
    | 3-6 | 0.586 +/- 0.127 | 201 |
    | 6-14 | 0.595 +/- 0.175 | 94 |

    Three bins over a **ninefold** range of overlap depth, all within 0.02 of each other. So once
    neighbouring plumes are properly overlapped the exe removes a fixed ~40 % of the entrainment
    and stops removing more, however deep the overlap gets.

    ⚠️⚠️ **This refutes a prediction registered before the runs.** The plan said the
    suppression would *keep falling* past `d/L` 2.2 -- roughly 0.4-0.5 at 3 and 0.3 or below at 4 --
    extrapolated from case20's five coarse points. It does not fall at all. Recorded as a miss:
    it is the third prediction this defect has broken, and every one has been wrong about the
    *shape* rather than the size.

    ⚠️ Measurable at all only because a 35 psu effluent grows slowly enough to come off the step
    controller's 2 % cap. case40's 2 psu run sat on the cap for 186 of 255 steps, where the ratio is
    1 by construction -- the trap case20's own README flags.
    """
    samples = [ratio for depth, ratio in _suppression_samples() if depth >= 1.5]
    if len(samples) < 400:
        raise AssertionError(f"only {len(samples)} deep samples; the archive has changed")
    return float(np.mean(samples))


def _suppression_plateau_flatness() -> float:
    """Largest gap between the three depth bins' mean suppression. **0.020**.

    The control that makes the row above a *plateau* rather than an average. A single mean over
    `d/L` 1.5-14 would read 0.596 whether the suppression were flat or sliding from 0.8 to 0.4, so
    the claim is not the mean but that the bins agree: 0.606, 0.586, 0.595 over 1.5-3, 3-6 and
    6-14. The spread between them is **0.020**, an order of magnitude smaller than the 0.13 scatter
    within any one of them.
    """
    samples = _suppression_samples()
    means = []
    for low, high in ((1.5, 3.0), (3.0, 6.0), (6.0, 14.0)):
        binned = [r for d, r in samples if low <= d < high]
        if len(binned) < 50:
            raise AssertionError(f"bin {low}-{high} has only {len(binned)} samples")
        means.append(float(np.mean(binned)))
    return max(means) - min(means)


@cache
def _our_suppression_crossing() -> float:
    """The `d/L` at which the **retired** default's suppression passes 1.0. **1.99**.

    ⚠️⚠️ **Pinned to `ConfinedDecrements.NONE`, which stopped being the default on
    2026-08-21.** What ships now never crosses 1.0 -- that is rows 267 and 273 -- so this row
    records the defect the flip removed rather than a live one. It is kept because the runaway is
    the reason the default moved, and a retraction that leaves no trace is how a project forgets
    what it already got wrong.

    ⚠️⚠️ **The mechanism behind rows 157b and 186, and it is a positive feedback.** Our
    closure suppresses correctly while the overlap is shallow, then crosses 1.0 at `d/L` ~ 2 and
    diverges -- reaching 1.33, 3.34 and 2.82 on the three spacings. Past that point we are
    *enhancing* entrainment where the exe removes 40 % of it.

    The loop is visible in the equations: eq 56 inflates the merged radius, a larger radius means
    larger Taylor and forced entrainment areas, more entrainment grows the mass, and eq 56 inflates
    the radius further. Nothing in the port opposes it, which is row 186's runaway seen as a rate
    instead of a length.

    ⚠️ **Also a refuted prediction.** The plan said our closure would sit flat at 0.85-0.9
    across the whole range. It does not stay below 1 at all. Both halves of that prediction were
    wrong, and both in the direction of the defect being worse.

    Measured on the shallowest crossing of the three, and only inside the first 90 % of each of our
    integrations -- a gradient taken in the last few steps of a diverging run is noise, not a rate.
    """
    from plumes2.io.dat import read_dat

    base = _case(f"{_CASE41}/Macoma2.prj")

    def build(spacing: float):  # type: ignore[no-untyped-def]
        return base.model_copy(
            update={
                "diffuser": base.diffuser.model_copy(
                    update={"port_spacing": spacing, "horizontal_angle": 65.0}
                ),
                "effluent": base.effluent.model_copy(update={"salinity": 35.0}),
            }
        )

    # ⚠️ Pinned to the **retired** default. This row exists to record what the closure did
    # before 2026-08-21, and `ALL` -- what now ships -- does not cross 1.0 at all, which is
    # the point of rows 267 and 273 rather than a reason to delete the measurement.
    from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

    retired = MergingChoices(confined_decrements=ConfinedDecrements.NONE)
    control = _integrate_once(build(5.0), max_time=200.0, merging=retired)
    crossings = []
    for run, spacing, salinity in _CASE41_RUNS:
        if salinity != 35.0:
            continue
        parsed = read_dat(_ROOT / _CASE41 / f"{run}.dat")
        frame = parsed.nearfield
        banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        times = frame["Time"].to_numpy(dtype=np.float64)
        merged = _integrate_once(build(spacing), max_time=float(times[-1]) + 5.0, merging=retired)
        limit = 0.90 * min(
            float(merged.solution.t[-1]),  # type: ignore[attr-defined]
            float(control.solution.t[-1]),  # type: ignore[attr-defined]
        )
        started = float(frame["Time"].loc[banner])
        window = (times > started) & (times <= limit)
        if window.sum() < 20:
            raise AssertionError(f"{run}: only {window.sum()} steps inside our own domain")
        sampled = times[window]
        ours = np.gradient(np.log(merged.sample(sampled).dilution), sampled) / np.gradient(
            np.log(control.sample(sampled).dilution), sampled
        )
        above = np.flatnonzero(ours >= 1.0)
        if not above.size:
            raise AssertionError(f"{run}: our suppression never crosses 1.0 -- has it been fixed?")
        depths = frame["P-dia"].to_numpy(dtype=np.float64)[window] / spacing
        crossings.append(float(depths[above[0]]))
    return min(crossings)


#: The `d/L` window all three 35 psu spacings reach, in three bins. ⚠️ Row 260 binned over
#: `d/L` 1.5-14, where only the 0.25 m run has samples past 5.5 -- so its "three bins over a
#: ninefold range" compared *different runs to each other* rather than one run across depths. This
#: window is the widest every run covers, which is what makes a per-spacing level comparable.
_MATCHED_OVERLAP_BINS = ((1.5, 2.0), (2.0, 2.5), (2.5, 3.0))


@cache
def _suppression_levels(source: str) -> dict[float, tuple[float, float, float, float]]:
    """`spacing -> (level, mean time, mean dilution, slope in d/L)` over the matched window.

    `source` is `"exe"` for the printed traces or a `ConfinedDecrements` value for our own
    closure. One helper for both, so the two curves cannot drift apart in how they are reduced.

    **The level is the mean of the three bin means**, not of the pooled samples: the step
    controller puts 9 samples in one bin and 56 in another, and pooling lets the crowded bin
    decide the answer. That is the same reduction row 264b uses, for the same reason.
    """
    def reduce(  # type: ignore[no-untyped-def]
        depth, ratio, time, dilution
    ) -> tuple[float, float, float, float]:
        levels, times, dilutions = [], [], []
        for low, high in _MATCHED_OVERLAP_BINS:
            inside = (depth >= low) & (depth < high) & np.isfinite(ratio)
            if inside.sum() < 4:
                raise AssertionError(f"{source}: bin {low}-{high} has {inside.sum()} samples")
            levels.append(float(ratio[inside].mean()))
            times.append(float(time[inside].mean()))
            dilutions.append(float(dilution[inside].mean()))
        wide = (depth >= 1.5) & (depth < 3.7) & np.isfinite(ratio)
        slope = float(np.polyfit(depth[wide], ratio[wide], 1)[0])
        return float(np.mean(levels)), float(np.mean(times)), float(np.mean(dilutions)), slope

    out: dict[float, tuple[float, float, float, float]] = {}

    if source == "exe":
        control = _dat(f"{_CASE41}/{_CASE41_CONTROL}.dat")
        frame = control.nearfield
        keep = np.isfinite(frame["Dilutn"].to_numpy(dtype=np.float64))
        frame = frame[keep]
        banner = next(
            e.next_step for e in control.events if "merg" in e.text.lower() and e.next_step
        )
        control_time = frame["Time"].to_numpy(dtype=np.float64)
        control_rate = np.gradient(
            np.log(frame["Dilutn"].to_numpy(dtype=np.float64)), control_time
        )
        clean_until = float(frame.loc[banner, "Time"])
        for run, spacing, salinity in _CASE41_RUNS:
            if salinity != 35.0:
                continue
            parsed = _dat(f"{_CASE41}/{run}.dat")
            run_frame = parsed.nearfield
            usable = np.isfinite(run_frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
                run_frame["Dilutn"].to_numpy(dtype=np.float64)
            )
            run_frame = run_frame[usable]
            run_banner = next(
                e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
            )
            times = run_frame["Time"].to_numpy(dtype=np.float64)
            window = (times > float(run_frame.loc[run_banner, "Time"])) & (times < clean_until)
            rate = np.gradient(np.log(run_frame["Dilutn"].to_numpy(dtype=np.float64)), times)
            ratio = rate[window] / np.interp(times[window], control_time, control_rate)
            out[spacing] = reduce(
                run_frame["P-dia"].to_numpy(dtype=np.float64)[window] / spacing,
                ratio,
                times[window],
                run_frame["Dilutn"].to_numpy(dtype=np.float64)[window],
            )
        return out

    # Our curve arrives as flat samples, so group by spacing then reduce with the same function.
    grouped: dict[float, list[tuple[float, float, float, float]]] = {}
    for spacing, depth, ratio, time, dilution in _our_suppression_curve(source):
        grouped.setdefault(spacing, []).append((depth, ratio, time, dilution))
    for spacing, samples in grouped.items():
        columns = np.array(samples, dtype=np.float64)
        out[spacing] = reduce(columns[:, 0], columns[:, 1], columns[:, 2], columns[:, 3])
    return out


def _exe_suppression_level_spread() -> float:
    """The exe's suppression level differs by **0.198** between spacings at matched `d/L`.

    ⚠️⚠️ **This is the correction to row 260, and it says the "plateau at 0.60" is a
    pooling artifact.** Row 260 bins 483 samples from three spacings by `d/L` and reads
    0.606 / 0.586 / 0.595 -- flat to 0.020. But only the 0.25 m run reaches `d/L` past 5.5, so
    those bins compare *different runs to each other*, not one run across overlap depths. Reduced
    per spacing over the window all three actually cover:

    | spacing | level | its three bins |
    |---|---|---|
    | 0.75 m | **0.766** | 0.688 / 0.802 / 0.806 |
    | 0.50 m | **0.568** | 0.530 / 0.515 / 0.659 |
    | 0.25 m | **0.580** | 0.598 / 0.578 / 0.563 |

    A **0.198** spread, ten times row 260b's 0.020, and the standard errors are 0.001-0.022. The
    pooled bins looked flat because the three curves cross, not because the suppression is one
    number.

    ⭐ **What survives of row 260 is the shape, not the level** -- see
    `_suppression_steepest_decline`, which is the controlled version of 260b's claim. What does
    not survive is "the exe removes a fixed ~40 % of the entrainment": it removes 23 % at one
    spacing and 43 % at another.

    ⚠️⚠️ **And the spread is not attributable to the spacing** -- see
    `_matched_overlap_confound`. Reported here as the size of the effect, with that row saying
    what it cannot be assigned to.
    """
    levels = [level for level, *_ in _suppression_levels("exe").values()]
    return max(levels) - min(levels)


def _matched_overlap_confound() -> float:
    """At matched `d/L` the three runs sit **8.1x** apart in elapsed time. The lever moved twice.

    ⚠️⚠️ **Why row 260d's 0.198 cannot be called a spacing dependence, and this is the
    third time this project has read one lever while another moved with it** (the Froude reading
    of the merging lag, then port depth after it).

    Spacing *determines when* a given `d/L` is reached: a tightly spaced plume overlaps almost
    immediately, a widely spaced one only after it has grown. So at matched overlap depth the runs
    are at completely different stages of their trajectories:

    | spacing | mean time in the window | mean dilution |
    |---|---|---|
    | 0.75 m | 84.9 s | 182.8 |
    | 0.50 m | 43.2 s | 101.8 |
    | 0.25 m | 10.5 s | 45.5 |

    **8.1x in time and 4.0x in dilution.** The plume depth *is* comparable (-1.2 to -1.8 m), so
    it is not that; it is how far along the trajectory the element is. Any of spacing, elapsed
    time or accumulated dilution would fit the 0.198 equally well, and case41 cannot separate
    them because its design ties them together.

    ⭐ **The run that would separate them** is two spacings contrived to reach the same `d/L` at
    the same dilution -- achievable by trading spacing against effluent salinity, since a denser
    effluent grows more slowly. case41's 40 and 45 psu runs are at one spacing only, so the
    archive does not have it. Until then the honest statement is that the level varies by 0.198
    across case41's three runs and the cause is unidentified.
    """
    times = [time for _level, time, *_ in _suppression_levels("exe").values()]
    return max(times) / min(times)


def _suppression_steepest_decline() -> float:
    """The steepest *downward* trend in any one run: **-0.028** per unit `d/L`.

    ⭐ **The controlled version of row 260b, and it is what survives the pooling correction.**
    260b's claim was that the suppression does not decline as the overlap deepens -- which was the
    right question, asked of a pooled average that could not answer it. Asked per run, over the
    same `d/L` 1.5-3.7 window:

    | spacing | slope per unit `d/L` |
    |---|---|
    | 0.75 m | **-0.020** |
    | 0.50 m | **+0.125** |
    | 0.25 m | **-0.028** |

    Two are flat to within 0.03 -- about 0.06 over the whole window, under 10 % of the level --
    and the third *rises*. So no run's suppression falls off with depth, which refutes the
    pre-run prediction (0.4-0.5 at `d/L` 3, below 0.3 at 4) on evidence that actually bears on it.

    ⚠️ **The 0.50 m run's +0.125 is unexplained** and is the largest single anomaly left in this
    measurement: over the window it climbs 0.53 -> 0.71. It is also the run with the most samples
    (115), so it is not a small-sample artifact.

    Pinned as the steepest decline rather than the mean slope, because the claim is a *bound* --
    "nothing falls off" -- and a mean over one rising and two flat runs would hide a decline in
    the one that fell.
    """
    slopes = [slope for *_, slope in _suppression_levels("exe").values()]
    return min(slopes)


def _braked_level_error() -> float:
    """Mean |ours - the exe| on the suppression level, per spacing, braked. **0.088**.

    ⭐⭐ **Row 264b restated, and the pooled version had flattered the brake the same way row
    260 flattered the exe.** "Our 0.660 against the exe's 0.596" averaged a `+0.145` and a
    `-0.071` into an 0.064 offset. Per spacing, over the window all three runs cover:

    | spacing | exe | ours, unbraked | ours, braked |
    |---|---|---|---|
    | 0.75 m | 0.766 | 0.962 (+0.196) | 0.695 (**-0.071**) |
    | 0.50 m | 0.568 | 0.792 (+0.224) | 0.617 (**+0.049**) |
    | 0.25 m | 0.580 | 0.906 (+0.326) | 0.725 (**+0.145**) |
    | mean abs. error | | **0.249** | **0.088** |

    ⭐ **The brake is better at every spacing** -- 2.8x on the mean absolute error, and it is the
    honest form of the claim, because it compares like with like at matched overlap instead of
    pooling three curves that cross.

    ⚠️⚠️ **But the residual is not an offset: it changes sign.** The brake
    *over*-suppresses at the widest spacing and *under*-suppresses at the tightest, a signed range
    of 0.216. So there is no constant left to correct, which is the same conclusion row 264c
    reached from the other end -- the two decrement radii are each right in a different regime and
    a single choice cannot be right throughout.

    ⚠️ **Ours is also too uniform.** Our braked spread across spacings is 0.107 against the
    exe's 0.198, so whatever the exe is responding to, we respond to it half as strongly. That is
    a different defect from the runaway and it was invisible while the runaway dominated.
    """
    exe = _suppression_levels("exe")
    ours = _suppression_levels("all")
    return float(
        np.mean([abs(ours[spacing][0] - level) for spacing, (level, *_) in exe.items()])
    )


def _unbraked_level_error() -> float:
    """The same, unbraked: **0.249**. The control that makes row 264b's 0.088 mean something.

    Without it, 0.088 could be a good result or a poor one. The shipped closure is 0.249 off the
    exe's level at matched overlap -- and, unlike the braked figure, it is one-signed: +0.196,
    +0.224, +0.326, every spacing under-suppressing. That single sign is the runaway showing up
    in the level as well as in the trend.
    """
    exe = _suppression_levels("exe")
    ours = _suppression_levels("none")
    return float(
        np.mean([abs(ours[spacing][0] - level) for spacing, (level, *_) in exe.items()])
    )


@cache
def _our_suppression_bins(confined: str) -> tuple[float, ...]:
    """Our own suppression, binned as rows 260/260b bin the exe's, under one brake setting.

    `confined` is a `ConfinedDecrements` value. The bins, the window and the rate definition are
    all row 260's, so the two curves are directly comparable -- the only thing that changes is
    which radius `merging_factors` takes `phi` at.
    """
    samples = _our_suppression_curve(confined)
    means: list[float] = []
    for low, high in ((1.5, 3.0), (3.0, 6.0), (6.0, 14.0)):
        binned = [r for _s, d, r, _t, _dil in samples if low <= d < high and math.isfinite(r)]
        if len(binned) < 50:
            raise AssertionError(f"{confined}: bin {low}-{high} has only {len(binned)} samples")
        means.append(float(np.mean(binned)))
    return tuple(means)


@cache
def _our_suppression_curve(confined: str) -> tuple[tuple[float, float, float, float, float], ...]:
    """`(spacing, d/L, suppression, time, dilution)` through **our** closure, per brake setting.

    The mirror of `_suppression_samples`, which does this for the exe: same three 35 psu
    spacings, same 5 m unmerged control, same `d(ln D)/dt` ratio at matched instants, same
    post-banner window. Two differences, both necessary:

    * the control is *our* integration of the 5 m case, not the exe's trace, so the ratio
      isolates what merging does inside this port rather than mixing in the port's own drift;
    * `d/L` uses **our** diameter, because our radius is the quantity on trial -- indexing our
      suppression by the exe's geometry would hide the runaway behind the exe's own scale.

    Cut at 90 % of the shorter of the two integrations: a gradient taken in the last steps of a
    diverging run is noise rather than a rate. That cut is row 260c's.

    ⚠️ **Not interchangeable with row 260c's number**, because of the second difference
    above: indexed by our diameter the unbraked crossing is **2.37**, where row 260c's 1.99 is the
    same crossing indexed by the exe's. Both are correct for what they index, and quoting one as
    the other would be a units error in `d/L`.
    """
    from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

    choices = MergingChoices(confined_decrements=ConfinedDecrements(confined))
    base = _case(f"{_CASE41}/Macoma2.prj")

    def build(spacing: float, salinity: float):  # type: ignore[no-untyped-def]
        return base.model_copy(
            update={
                "diffuser": base.diffuser.model_copy(
                    update={"port_spacing": spacing, "horizontal_angle": 65.0}
                ),
                "effluent": base.effluent.model_copy(update={"salinity": salinity}),
            }
        )

    control = _integrate_once(build(5.0, 35.0), max_time=200.0, merging=choices)
    samples: list[tuple[float, float, float, float, float]] = []
    for run, spacing, salinity in _CASE41_RUNS:
        if salinity != 35.0:
            continue
        parsed = _dat(f"{_CASE41}/{run}.dat")
        frame = parsed.nearfield
        banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        times = frame["Time"].to_numpy(dtype=np.float64)
        merged = _integrate_once(
            build(spacing, salinity), max_time=float(times[-1]) + 5.0, merging=choices
        )
        limit = 0.90 * min(
            float(merged.solution.t[-1]),  # type: ignore[attr-defined]
            float(control.solution.t[-1]),  # type: ignore[attr-defined]
        )
        window = (times > float(frame["Time"].loc[banner])) & (times <= limit)
        if window.sum() < 20:
            raise AssertionError(f"{run}: only {window.sum()} steps inside our own domain")
        sampled = times[window]
        ours = np.gradient(np.log(merged.sample(sampled).dilution), sampled) / np.gradient(
            np.log(control.sample(sampled).dilution), sampled
        )
        resampled = merged.sample(sampled)
        depth = resampled.diameter / spacing
        # ⚠️ Spacing, time and dilution ride along because reducing this curve *by spacing*
        # is what corrected rows 260 and 264b -- see `_suppression_levels`. Pooling the three
        # spacings into `d/L` bins is the artifact, so the spacing cannot be dropped here.
        samples.extend(
            zip(
                [spacing] * len(sampled),
                depth.tolist(),
                ours.tolist(),
                sampled.tolist(),
                resampled.dilution.tolist(),
                strict=True,
            )
        )
    return tuple(samples)


def _our_brake_crossing(confined: str) -> float:
    """The shallowest `d/L` at which our suppression reaches 1.0 under one brake setting.

    Row 260c's quantity, reparameterised by the brake so the three settings are comparable on
    the one number that decides whether the closure enhances entrainment at all: **2.37**
    unbraked, **4.88** with the growth term alone, **17.71** with all four.
    """
    curve = _our_suppression_curve(confined)
    above = [
        depth
        for _s, depth, ratio, _t, _dil in sorted(curve, key=lambda row: row[1])
        if math.isfinite(ratio) and ratio >= 1.0
    ]
    if not above:
        raise AssertionError(f"{confined}: our suppression never reaches 1.0")
    return above[0]


def _confined_brake_flatness() -> float:
    """Largest gap between our three suppression bins with all four decrements braked. **0.043**.

    ⭐⭐⭐ **The merged-radius runaway is an asymmetry in which radius each side is evaluated at,
    and this is the measurement that says so.** `merging_factors` takes `phi` at the
    round-equivalent `b_r`, while every entrainment area downstream is built from the
    **confined** `b` of eq 56. So the inflation factor `b/b_r` enters the entrainment with
    nothing opposing it, and because the growth area is `pi b db` -- quadratic in `b` -- it
    compounds. Move all four decrements to the confined half-height and the divergence becomes
    a plateau:

    | `d/L` | exe (row 260) | ours, `b_r` | ours, confined `b` |
    |---|---|---|---|
    | 1.5-3 | 0.606 | 0.832 | **0.649** |
    | 3-6 | 0.586 | 1.243 | **0.686** |
    | 6-14 | 0.595 | (the run has died) | **0.643** |
    | flatness | **0.020** | diverges | **0.043** |

    ⚠⚠ **The exe column here is row 260's pooled average and is not a law** -- rows
    260d-260f retract that reading, and per spacing its level spans 0.198. So this row's claim is
    about *our* curve becoming flat, not about it matching a flat exe. Row 264b is the comparison
    that survives the correction, and the brake comes out better on it.

    ⭐ **Structural, and it had to be.** The finite-time-singularity argument rules out any
    coefficient: multiplying `db/dt = k b^2` by a constant only reschedules `t_c = 1/(k b_0)`.
    What the confined angle changes is the **asymptote**: `a_T * pi * b` converges to a constant,
    so the decremented growth area stops depending on `b` at all, where at `b_r` the same product
    diverges linearly in `b_r/s`. Normalised by `L`, at test63's half-spacing: 1.494 at `d/L`
    1.05, 2.738 at 2, 7.614 at 5 and **31.35** at 20, against 1.481 / 1.862 / 1.996 / **2.000**.

    ⚠️ **The constant is the slab width `2s = L` only under the true `arccos`.** Under the
    exe's `arctan` -- the shipped default -- it is `2 sqrt(s)`, which is not a width; the angle
    bug's dimensional inconsistency survives into the asymptote, and the table above is in those
    units, which is why it plateaus at 2.000 rather than 1.000. Both saturate, which is all the
    brake needs. See `ConfinedDecrements`, which carries the derivation and the lead it gives on
    row 264b.

    ⚠️ **Not the default, and row 264c is why.** A candidate fix recorded with its cost rather
    than adopted; `ConfinedDecrements.NONE` remains what the port ships.
    """
    means = _our_suppression_bins("all")
    return max(means) - min(means)


def _retired_default_on_test32() -> float:
    """test32's post-merge MARE under the **retired** default. **1.01 %**, against 5.24 % now.

    ⚠️⚠️ **The reason the brake is not the default, and it refutes the prediction that justified
    trying it.** The argument for the confined angle was that it barely moves at shallow overlap
    -- 1.481 against 1.494 on the growth-area product at `d/L` 1.05 -- so row 157's 1.01 %
    should survive. **It does not.** test32 reaches `d/L` **2.35**, where the same product reads
    1.862 against 2.738, a 32 % difference, and the post-merge trajectory degrades to 5.24 %.
    Our merged diameter goes from 1.125x the exe's to **0.965x**: the brake turns a slight
    over-inflation into a slight under-inflation.

    ⭐ **So the two readings are each right in their own regime**, which is the finding rather
    than a disappointment. `b_r` holds out to `d/L` ~ 2.4 and diverges past it; the confined `b`
    holds past ~3 and over-suppresses before it. What the exe evaluates is therefore neither one
    of them, and locating the transition is the next question -- not fitting a blend between
    them, which would be a coefficient again.

    ⚠️ Measured on case20's test32 against the same unmerged control row 157 uses (row 177,
    1.39 %), so it is comparable to the number it displaces.
    """
    return _merging_error("test32", 1.0, confined="none")[1]


def _growth_only_brake_still_diverges() -> float:
    """`d/L` at which braking the **growth term alone** still crosses 1.0. **4.88**.

    ⛔ **A refuted candidate, and it was the one the mechanism argued for.** The growth area is
    the only one quadratic in the radius -- `A_T = 2 pi b h` and `A_cyl = 2 b h` are linear --
    so it is the whole of the finite-time singularity, and braking it alone should have removed
    the blow-up while leaving the Taylor and cylinder decrements row 157 measured untouched.

    It does remove the *singularity*: the runs stop dying early (test67 reaches 166.9 s against
    72.8 s) and the diameter ratio falls from 11.93x to 2.29x. But the suppression still climbs
    -- **0.760 / 0.857 / 1.005** across the three bins -- and still crosses 1.0, at `d/L` 4.88
    rather than 2.37.

    ⭐ **Why, and it is what makes row 264 necessary.** The Taylor term is linear in `b`, but its
    decrement is taken at `b_r`, so `a_T(b_r) A_T ~ (2 s h)(b/b_r)` -- the inflation factor
    survives there too. Braking growth alone downgrades a finite-time singularity to an
    unbounded *linear* enhancement, which is better and still wrong. **Every** term built on the
    confined radius has to carry a decrement evaluated at it.

    ⚠️ It is also strictly worse than row 264 on the deep runs -- post-merge 23.3 / 24.7 / 28.3 %
    on test63 / test66 / test67 against the brake's 4.3 / 4.8 / 6.0 %, and 113 % on test64. A
    dominated candidate, kept because the reasoning behind it was sound and a measurement is
    what disposed of it.
    """
    means = _our_suppression_bins("growth")
    if max(means) < 1.0:
        raise AssertionError("growth-only braking no longer crosses 1.0; row 264d has changed")
    return _our_brake_crossing("growth")


_CASE42 = "reference_cases/case42_matched_dilution"

#: case42's pair: `(trace, spacing)`. The merged run and its unmerged control, both at the
#: **scaled** port -- 0.0191 m and 0.0112598 m3/s, 1.5x case41's in length and 2.25x in area.
_CASE42_MERGED, _CASE42_CONTROL = ("test69", 0.75), ("test70", 5.0)


@cache
def _case42_case(which: str) -> Case:
    """The case as the exe wrote the `.prj` back at run time, not as we asked for it.

    The format quantises -- 0.01905 m becomes 0.0191 and the flow goes through MGD -- and the exe
    rewrote `nearfield_flags[1]` on top of that. Reading the returned file is the only way the
    comparison is against what actually ran.
    """
    return _case(f"{_CASE42}/matched_dilution_{which}.prj")


@cache
def _case42_suppression(braked: str | None = None) -> tuple[float, float, float, tuple[float, ...]]:
    """`(onset dilution, level, trend, bins)` for case42's merged run.

    `braked` selects a `ConfinedDecrements` value to drive **our** closure instead of reading the
    exe's trace. Reduced exactly as `_suppression_levels` reduces case41, over the same
    `_MATCHED_OVERLAP_BINS`, so the two cases are directly comparable.
    """
    spacing = _CASE42_MERGED[1]
    control = _dat(f"{_CASE42}/{_CASE42_CONTROL[0]}.dat")
    merged = _dat(f"{_CASE42}/{_CASE42_MERGED[0]}.dat")

    def usable(parsed):  # type: ignore[no-untyped-def]
        frame = parsed.nearfield
        keep = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
            frame["Dilutn"].to_numpy(dtype=np.float64)
        )
        banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        return frame[keep], banner

    merged_frame, merged_banner = usable(merged)
    control_frame, control_banner = usable(control)
    times = merged_frame["Time"].to_numpy(dtype=np.float64)
    diameters = merged_frame["P-dia"].to_numpy(dtype=np.float64)
    dilutions = merged_frame["Dilutn"].to_numpy(dtype=np.float64)
    onset = np.flatnonzero(diameters >= spacing)
    if not onset.size:
        raise AssertionError("case42's merged run never reaches d/L = 1")
    onset_dilution = float(dilutions[onset[0]])

    if braked is None:
        control_time = control_frame["Time"].to_numpy(dtype=np.float64)
        control_rate = np.gradient(
            np.log(control_frame["Dilutn"].to_numpy(dtype=np.float64)), control_time
        )
        clean_until = float(control_frame.loc[control_banner, "Time"])
        window = (times > float(merged_frame.loc[merged_banner, "Time"])) & (times < clean_until)
        ratio = np.gradient(np.log(dilutions), times)[window] / np.interp(
            times[window], control_time, control_rate
        )
        depth = diameters[window] / spacing
    else:
        from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

        choices = MergingChoices(confined_decrements=ConfinedDecrements(braked))
        ours = _integrate_once(
            _case42_case("merged"),
            max_time=float(times[-1]) + 5.0,
            merging=choices,
        )
        theirs = _integrate_once(_case42_case("control"), max_time=300.0, merging=choices)
        end = 0.90 * min(
            float(ours.solution.t[-1]),  # type: ignore[attr-defined]
            float(theirs.solution.t[-1]),  # type: ignore[attr-defined]
        )
        sampled = np.linspace(float(merged_frame.loc[merged_banner, "Time"]) + 0.1, end, 3000)
        one, two = ours.sample(sampled), theirs.sample(sampled)
        ratio = np.gradient(np.log(one.dilution), sampled) / np.gradient(
            np.log(two.dilution), sampled
        )
        depth = np.asarray(one.diameter, dtype=np.float64) / spacing

    bins: list[float] = []
    for low, high in _MATCHED_OVERLAP_BINS:
        inside = (depth >= low) & (depth < high) & np.isfinite(ratio)
        bins.append(float(np.asarray(ratio)[inside].mean()) if inside.sum() >= 4 else math.nan)
    good = [value for value in bins if math.isfinite(value)]
    wide = (depth >= 1.5) & (depth < 3.7) & np.isfinite(ratio)
    trend = float(np.polyfit(depth[wide], np.asarray(ratio)[wide], 1)[0])
    return onset_dilution, float(np.mean(good)), trend, tuple(bins)


def _matched_dilution_design_gap() -> float:
    """How close case42's merged run lands to test63's onset dilution. **1.6 %**.

    ⭐⭐ **The design's own validity gate, registered before the run at 5 %.** The experiment
    only means anything if the two arms really do begin merging at the same accumulated dilution:
    case42's **56.10** against case41 test63's **57.0**.

    ⛔ **Row 260e's own proposal could not have got here.** It asked for two spacings matched by
    trading spacing against effluent *salinity*. Over 20-48 psu the dilution at a fixed diameter
    moves only **17 %** where **41 %** was needed -- and it is structurally impossible that way,
    because reaching `d/L` = 1 at a wider spacing always needs a larger diameter and therefore more
    dilution, monotonically, so no effluent property can equalise two spacings.

    ⭐ **The port is the lever, and it is arithmetic rather than a fit.** The dilution at `d = L`
    goes as `(L/d0)^2`, so scaling the port diameter by the same 1.5 as the spacing holds the onset
    dilution fixed, with the flow scaled by the port *area* to hold the exit velocity. Predicted
    55.1 before the run, measured 56.10.
    """
    onset, _level, _trend, _bins = _case42_suppression()
    control_onset = _case41_onset_dilution(0.50)
    return abs(onset - control_onset) / control_onset


@cache
def _case41_onset_dilution(spacing: float) -> float:
    """The dilution at which a case41 run first reaches `d/L` = 1, from its printed columns."""
    run = next(name for name, gap, salinity in _CASE41_RUNS if gap == spacing and salinity == 35.0)
    frame = _dat(f"{_CASE41}/{run}.dat").nearfield
    diameters = frame["P-dia"].to_numpy(dtype=np.float64)
    dilutions = frame["Dilutn"].to_numpy(dtype=np.float64)
    keep = np.isfinite(diameters) & np.isfinite(dilutions)
    hit = np.flatnonzero(keep & (diameters >= spacing))
    if not hit.size:
        raise AssertionError(f"case41's {spacing} m run never reaches d/L = 1")
    return float(dilutions[hit[0]])


def _suppression_follows_dilution() -> float:
    """case42's first suppression bin against the **dilution-matched** run's. **0.006**.

    ⭐⭐ **The discriminator, and it answers.** case42's merged run shares its *spacing* with
    case41's test65 (0.75 m) and its *onset dilution* with test63 (56.1 against 57.0). Whichever it
    resembles is what sets the suppression:

    | run | spacing | onset `D` | `d/L` 1.5-2 | trend |
    |---|---|---|---|---|
    | test65 | **0.75 m** | 90.2 | 0.688 | -0.020 |
    | test63 | 0.50 m | **57.0** | 0.530 | +0.125 |
    | **case42** | **0.75 m** | **56.1** | **0.536** | **+0.147** |

    It tracks **test63**: 0.536 against 0.530 is **0.006** apart, where test65 at the same spacing
    sits **0.152** away -- twenty-five times further, against standard errors of 0.008 and 0.006.
    Row 266b pins the trend, which agrees in sign with test63 and disagrees with test65.

    ⭐ **So row 260d's 0.198 is a trajectory-stage effect and the spacing is not the driver.**
    Where a run is along its trajectory when merging begins -- measured as the dilution accumulated
    by then -- sets the suppression it applies. Row 260e's "unidentified" is now identified.

    ⭐ It also gives row 260f's anomaly a companion: test63's +0.125 trend stood alone and now
    reproduces at a different spacing and port with matched dilution, so it belongs to the
    low-dilution regime rather than to the 0.5 m spacing.
    """
    _onset, _level, _trend, bins = _case42_suppression()
    return abs(bins[0] - _case41_bins(0.50)[0])


@cache
def _case41_bins(spacing: float) -> tuple[float, ...]:
    """case41's three matched-window suppression bins at one spacing."""
    run = next(name for name, gap, salinity in _CASE41_RUNS if gap == spacing and salinity == 35.0)
    control = _dat(f"{_CASE41}/{_CASE41_CONTROL}.dat")
    control_frame = control.nearfield
    keep = np.isfinite(control_frame["Dilutn"].to_numpy(dtype=np.float64))
    control_frame = control_frame[keep]
    control_banner = next(
        e.next_step for e in control.events if "merg" in e.text.lower() and e.next_step
    )
    control_time = control_frame["Time"].to_numpy(dtype=np.float64)
    control_rate = np.gradient(
        np.log(control_frame["Dilutn"].to_numpy(dtype=np.float64)), control_time
    )
    clean_until = float(control_frame.loc[control_banner, "Time"])

    parsed = _dat(f"{_CASE41}/{run}.dat")
    frame = parsed.nearfield
    usable = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
        frame["Dilutn"].to_numpy(dtype=np.float64)
    )
    frame = frame[usable]
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    times = frame["Time"].to_numpy(dtype=np.float64)
    window = (times > float(frame.loc[banner, "Time"])) & (times < clean_until)
    ratio = np.gradient(np.log(frame["Dilutn"].to_numpy(dtype=np.float64)), times)[
        window
    ] / np.interp(times[window], control_time, control_rate)
    depth = frame["P-dia"].to_numpy(dtype=np.float64)[window] / spacing
    out: list[float] = []
    for low, high in _MATCHED_OVERLAP_BINS:
        inside = (depth >= low) & (depth < high) & np.isfinite(ratio)
        out.append(float(ratio[inside].mean()) if inside.sum() >= 4 else math.nan)
    return tuple(out)


def _suppression_trend_follows_dilution() -> float:
    """case42's suppression trend in `d/L`. **+0.147**, where its spacing-mate trends **-0.020**.

    Row 266's control, and the half that cannot be explained away by a coincidence of levels. A
    difference of 0.006 in one bin could be luck; a trend of the same sign and magnitude as the
    dilution-matched run, against the *opposite* sign at the matched spacing, cannot.

    ⚠️⚠️ **And the prediction registered for this run was framed on the wrong statistic.** The
    discriminator was written as the **window-averaged level**: "~0.568 means dilution, ~0.766 means
    spacing, outside 0.55-0.78 means neither". It came out at **0.659** -- 0.091 from one and 0.107
    from the other, near enough equidistant to settle nothing, because case42's rising trend carries
    its later bins up into test65's range. The question was settled by the bins and the trend
    instead.

    ⛔ **That is a smaller copy of the mistake rows 260 and 260b were retracted for**: registering a
    pooled average for a quantity that had just been shown not to be one number. The physics
    prediction was right and the statistic was not, and it is recorded as a miss on the framing so
    the next prediction names a shape rather than a mean.
    """
    _onset, _level, trend, _bins = _case42_suppression()
    return trend


def _brake_out_of_sample() -> float:
    """case42's post-merge dilution MARE with the brake on. **0.98 %**, from 35.53 %.

    ⭐⭐⭐ **The brake validated out of sample, and it is the strongest evidence for it.**
    `ConfinedDecrements.ALL` was built against case20 and case41 and had never seen this geometry --
    a 1.5x-scaled port at a matched onset dilution. Sampled at the exe's own printed times:

    | | ends | dilution MARE | post-merge | our max dia / the exe's |
    |---|---|---|---|---|
    | `NONE`, what ships | 176.9 s | 20.40 % | **35.53 %** | **5.396x** |
    | `ALL`, the brake | 187.7 s | **0.71 %** | **0.98 %** | **1.118x** |
    | the exe | 182.7 s | | | |

    **0.98 % is row 157's shallow-overlap accuracy, reached at `d/L` up to 3.9** -- a 36x reduction
    on a case that did not exist when the brake was written, and the run now ends within 2.7 % of
    the exe's last row instead of dying 6 s early.

    ⚠️ Our *internal* prediction was exact: 0.835 unbraked and 0.652 braked on the suppression
    level, both registered before the run and reproduced to three decimals. What the port cannot
    predict is the exe's level, which is row 267b.
    """
    return _case42_error(braked="all")[1]


def _brake_out_of_sample_control() -> float:
    """The same case with the shipped default. **35.53 %** -- the control for row 267.

    Without it, 0.98 % could be a good result or an easy case. The shipped closure is **36 times**
    worse on the same rows, and its element reaches 5.396x the exe's diameter. A recorded
    divergence, and the largest single gap the default still carries.
    """
    return _case42_error(braked="none")[1]


@cache
def _case42_error(braked: str) -> tuple[float, float, float]:
    """`(MARE, post-merge MARE, our max diameter over the exe's)` on case42's merged run."""
    from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

    parsed = _dat(f"{_CASE42}/{_CASE42_MERGED[0]}.dat")
    frame = parsed.nearfield
    keep = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
        frame["Dilutn"].to_numpy(dtype=np.float64)
    )
    frame = frame[keep]
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(
        _case42_case("merged"),
        max_time=float(times[-1]) + 5.0,
        merging=MergingChoices(confined_decrements=ConfinedDecrements(braked)),
    )
    usable = times <= solution.solution.t[-1]  # type: ignore[attr-defined]
    ours = solution.sample(times[usable])
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)[usable]
    diameter = frame["P-dia"].to_numpy(dtype=np.float64)[usable]
    error = np.abs(ours.dilution - dilution) / dilution
    after = frame.index.to_numpy()[usable] >= banner
    return (
        float(error.mean()),
        float(error[after].mean()),
        float(ours.diameter.max() / diameter.max()),
    )


def _walk_schedule_shallow() -> float:
    """test32's post-merge MARE with the decrement radius on the exe's own walk. **3.68 %**.

    ⛔ **A derivation refuted by the thing that motivated it, and the refutation is the finding.**
    `NONE` is the round reading and `ALL` the slab reading; each is right in its own regime, and
    the axis is how deep into overlap a run gets (rows 264c, 267b). The exe states that schedule
    itself, on a *different* observable: its peak-to-mean concentration ratio walks from round
    (2.0) at `d/L` = 1 to slab (1.5) at `d/L` = 2 and stays there -- rows 199 and 203, 2 964 rows,
    confirmed again on case42 at a port diameter it was never fitted at. So walking the decrement
    radius on the same schedule is **parity rather than a fit**: no free parameter, and
    `slab_fraction` calls `crossplume.peak_to_mean` rather than restating it.

    **It does not work.** Post-merge dilution MARE across all seven merged runs:

    | run | onset `D` | max `d/L` | `NONE` | `WALK` | `ALL` |
    |---|---|---|---|---|---|
    | case20 test32 | 138.2 | 2.35 | **1.01 %** | 3.68 % | 5.24 % |
    | case41 test65 | 90.2 | 3.75 | 14.76 % | **1.77 %** | 2.32 % |
    | case42 test69 | 56.1 | 4.55 | 35.53 % | 1.35 % | **0.98 %** |
    | case41 test63 | 57.0 | 6.18 | 19.31 % | 4.92 % | **4.30 %** |
    | case41 test66 | 55.7 | 6.20 | 18.10 % | 5.32 % | **4.79 %** |
    | case41 test67 | 54.4 | 6.40 | 15.79 % | 6.55 % | **5.99 %** |
    | case41 test64 | 27.4 | 15.08 | **27.33 %** | 29.74 % | 29.45 % |
    | mean | | | 18.83 % | **7.62 %** | **7.58 %** |

    `WALK` is a **wash against `ALL`** -- 7.62 % against 7.58 % on the mean, better on two runs by
    0.6 pp and worse on five by at most 0.6 -- and it does not recover `NONE`'s 1.01 % on test32,
    which is the whole reason to want it.

    ⭐⭐ **So the exe's concentration schedule is not its entrainment schedule.** The element's
    *concentration profile* is a slab from `d/L` 2 outward, on 2 020 rows with zero exceptions;
    its *entrainment* does not switch there. Two geometries for one element, governed differently,
    and that is a statement about the exe rather than about this port.

    ⚠️ Kept rather than deleted, for the reason rows 264d and 180 are kept: it had an independent
    measurement behind it, which is exactly the kind of candidate that has to be shot down with a
    number rather than an argument. Row 269b is what it does keep.
    """
    return _merging_error("test32", 1.0, confined="walk")[1]


def _walk_schedule_deep() -> float:
    """case42's post-merge MARE on the same walk. **1.35 %**, against `ALL`'s 0.98 %.

    Row 269's other half: the walk keeps almost all of the brake's deep-overlap gain, so its
    failure on test32 is not a case of it simply being weaker. It is 36x better than the shipped
    default here and still loses to the plain slab reading by 0.37 pp.

    ⭐ **And it is best of the three on test65** -- 1.77 % against `ALL`'s 2.32 % and `NONE`'s
    14.76 %. test65 has the second-highest onset dilution of the seven, so the direction the walk
    was built to correct is real and its magnitude is far too small to matter.
    """
    return _case42_error("walk")[1]


_CASE43 = "reference_cases/case43_port_count"

#: case43's sweep: `(ports, trace, its own single-port control)`. Per-port flow is held at
#: 2.0e-4 m3/s throughout, so the individual plume is identical and only the neighbour count
#: changes. The last arm doubles the port at 25 ports -- the `d/L`-versus-`z*` discriminator.
_CASE43_ARMS = (
    (2, "test72", "test71"),
    (6, "test73", "test71"),
    (25, "test74", "test71"),
    ("25wide", "test75", "test76"),
)

#: Cenedese & Linden (2014) eq 2.12's merged asymptote for a coalescing **pair**, `2^(-1/2)`.
#: See `references/README.md`; this is a *literature* reference, not one of the exe's numbers.
COALESCING_PAIR_ASYMPTOTE = 2.0 ** -0.5

#: case43's traces to the projects the exe wrote back for them.
_CASE43_PROJECTS = {
    "test71": "suite_n01_base",
    "test72": "suite_n02_base",
    "test73": "suite_n06_base",
    "test74": "suite_n25_base",
    "test75": "suite_n25_wideport",
    "test76": "suite_n01_wideport",
}


@cache
def _case43_case(run: str) -> Case:
    """The case as the exe wrote the `.prj` back, which is what actually ran."""
    return _case(f"{_CASE43}/{_CASE43_PROJECTS[run]}.prj")


def _case43_reduce(depth, ratio) -> float:  # type: ignore[no-untyped-def]
    """Mean of the matched-window bin means -- the same reduction `_suppression_levels` uses."""
    means = [
        float(np.asarray(ratio)[(depth >= low) & (depth < high) & np.isfinite(ratio)].mean())
        for low, high in _MATCHED_OVERLAP_BINS
        if ((depth >= low) & (depth < high) & np.isfinite(ratio)).sum() >= 4
    ]
    if not means:
        raise AssertionError("case43: no usable bin")
    return float(np.mean(means))


@cache
def _case43_levels() -> dict[object, float]:
    """`ports -> the exe's suppression level`, each divided by its **own single-port control**.

    That denominator is what the suite was designed for: one port cannot merge with a neighbour, so
    the control carries no merging at all -- unlike the archive's 5 m spacings, which still trip the
    limiting-spacing rule (rows 261, 268, and both of case43's controls do too).
    """

    def read(name: str):  # type: ignore[no-untyped-def]
        parsed = _dat(f"{_CASE43}/{name}.dat")
        frame = parsed.nearfield
        keep = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
            frame["Dilutn"].to_numpy(dtype=np.float64)
        )
        banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        return frame[keep], banner

    out: dict[object, float] = {}
    for ports, run, control_run in _CASE43_ARMS:
        frame, banner = read(run)
        control, control_banner = read(control_run)
        control_time = control["Time"].to_numpy(dtype=np.float64)
        control_rate = np.gradient(
            np.log(control["Dilutn"].to_numpy(dtype=np.float64)), control_time
        )
        clean_until = float(control.loc[control_banner, "Time"])
        times = frame["Time"].to_numpy(dtype=np.float64)
        window = (times > float(frame.loc[banner, "Time"])) & (times < clean_until)
        ratio = np.gradient(np.log(frame["Dilutn"].to_numpy(dtype=np.float64)), times)[
            window
        ] / np.interp(times[window], control_time, control_rate)
        out[ports] = _case43_reduce(frame["P-dia"].to_numpy(dtype=np.float64)[window] / 0.5, ratio)
    return out


@cache
def _case43_our_levels(confined: str) -> dict[object, float]:
    """The same reduction, driven through our closure at one `ConfinedDecrements` setting."""
    from plumes2.nearfield.merging import ConfinedDecrements, MergingChoices

    choices = MergingChoices(confined_decrements=ConfinedDecrements(confined))
    out: dict[object, float] = {}
    for ports, run, control_run in _CASE43_ARMS:
        parsed = _dat(f"{_CASE43}/{run}.dat")
        frame = parsed.nearfield
        banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        times = frame["Time"].to_numpy(dtype=np.float64)
        merged = _integrate_once(
            _case43_case(run),
            max_time=float(times[-1]) + 5.0,
            merging=choices,
        )
        control = _integrate_once(_case43_case(control_run), max_time=400.0, merging=choices)
        end = 0.90 * min(
            float(merged.solution.t[-1]),  # type: ignore[attr-defined]
            float(control.solution.t[-1]),  # type: ignore[attr-defined]
        )
        sampled = np.linspace(float(frame["Time"].loc[banner]) + 0.1, end, 2500)
        one, two = merged.sample(sampled), control.sample(sampled)
        ratio = np.gradient(np.log(one.dilution), sampled) / np.gradient(
            np.log(two.dilution), sampled
        )
        out[ports] = _case43_reduce(np.asarray(one.diameter, dtype=np.float64) / 0.5, ratio)
    return out


def _coalescing_pair_asymptote_holds() -> float:
    """The exe's **two-port** suppression, against published pair theory. **0.733** vs 0.707.

    ⭐⭐⭐ **The first test of Cenedese & Linden (2014) against UM3, and nothing in the archive
    could have run it.** They solve two coalescing axisymmetric plumes from first principles and
    define an effective entrainment constant -- our suppression ratio under another name -- whose
    merged asymptote is `2^(-1/2)` = **0.707** (eq 2.12; `references/`). Every merged run archived
    before case43 has **25 ports**, so the pair the theory describes had never been built. case43's
    test72 is one, at a per-port flow matched to its single-port control, and it reads **0.733** --
    within **3.7 %**.

    ⚠️ **The asymptote holds; the approach curve does not.** Eq 2.12 declines from 0.855 to 0.707
    across this window. The exe reads 0.719 / 0.725 / 0.756 over the three bins -- flat, already at
    the asymptote, and if anything rising. UM3 lands on the right merged value without following the
    theoretical path to it, which is what a closure switching on a merge flag would do rather than
    one solving the coalescence.

    ⭐⭐ **And it retires the reading that the exe suppresses more than plume theory allows.** That
    came from the 25-port runs, 0.53-0.77 against theory's 0.71-0.84. At the port count the theory
    actually describes, they agree -- so the archive's extra suppression is the **row**, not a
    disagreement with physics: a row tends to a line plume, not a single
    axisymmetric one. ⚠️ Tolerance is 6 %, wide because the reference is a *different model* rather
    than the same one, so this measures agreement between two independent treatments.
    """
    return _case43_levels()[2]


def _port_count_sets_the_suppression() -> float:
    """Spread in the exe's suppression across port count at a fixed spacing. **0.165**.

    ⭐⭐⭐ **A first-order variable nothing had measured**, because every merged run in the archive
    has 25 ports. At a fixed 0.5 m spacing and a fixed *per-port* flow, so the individual plume is
    identical and only the number of neighbours changes: **0.733** at two ports, **0.605** at six,
    **0.568** at twenty-five.

    **0.165** across a twelvefold range -- comparable to row 260d's 0.198 across spacings, so a
    variable of the same order. Row 271b is the part that matters: the brake reproduces its shape.
    """
    levels = _case43_levels()
    counted = [levels[n] for n in (2, 6, 25)]
    return max(counted) - min(counted)


def _out_of_plane_share_is_confirmed() -> float:
    """Worst error in the brake's port-count *decrements*. **0.010**.

    ⭐⭐ **What confirms UM3's `out_of_plane = 1/n_ports`** -- the factor distributing cross-current
    entrainment over the merged group, and the only place the port count enters this port's model.
    Untested until now, because a port-count sweep did not exist.

    | | n 2 to 6 | n 6 to 25 |
    |---|---|---|
    | exe | **-0.128** | **-0.037** |
    | ours, `ALL` | **-0.138** | **-0.039** |
    | ours, `NONE` | -0.162 | -0.062 |

    8 % and 5 % out against levels of 0.57-0.73. So the brake has the port-count *dependence* right
    and is offset in *level*, and row 272 measures that offset as a single constant.

    ⚠️ Pinned as the worst absolute decrement error rather than a ratio: the second decrement is
    -0.037, and a ratio there would swing on the third decimal.
    """
    exe = _case43_levels()
    ours = _case43_our_levels("all")
    return max(
        abs((ours[high] - ours[low]) - (exe[high] - exe[low])) for low, high in ((2, 6), (6, 25))
    )


def _brake_residual_is_one_constant() -> float:
    """Spread in the brake's level offset across port count. **0.012**.

    ⭐⭐ **At a fixed spacing the brake is a constant offset from the exe**, which is a different
    object from row 264b's residual. Across a twelvefold range of port count the offset is
    +0.063 / +0.053 / +0.051 -- mean **+0.056**, spread **0.012** -- where the shipped default's is
    +0.284 / +0.250 / +0.225, mean +0.253 and spread 0.059.

    So the residual that *changes sign* -- row 264b's -0.071 at a 0.75 m spacing against +0.145 at
    0.25 m -- belongs to the **spacing**, not the port count. One unexplained residual becomes a
    constant plus a spacing dependence, and only the second still wants a mechanism.
    """
    exe = _case43_levels()
    ours = _case43_our_levels("all")
    offsets = [ours[n] - exe[n] for n in (2, 6, 25)]
    return max(offsets) - min(offsets)


def _the_default_enhances_entrainment_at_two_ports() -> float:
    """The shipped default's two-port suppression. **1.017** -- a recorded divergence.

    ⚠️⚠️ **Registered before the run, and the reference forbids it.** Two coalescing plumes cannot
    entrain more than two independent ones, so Cenedese & Linden's `alpha_eff/alpha` is bounded
    above by 1 by construction, reaching it only while the plumes are separate.
    `ConfinedDecrements.NONE` -- what this port ships -- gives **1.017** at two ports, i.e.
    *enhancement*, against a measured **0.733**.

    So the default is 39 % out at a port count where the right answer was known a priori, and out in
    a direction the physics excludes. It is the cleanest single statement of the runaway's cost, and
    it was predicted rather than discovered afterwards.
    """
    return _case43_our_levels("none")[2]


def _the_level_is_not_a_function_of_overlap_depth() -> float:
    """How far the exe's level moves when the port doubles at a fixed spacing. **0.026**.

    ⭐⭐ **Row 266 corroborated from a second direction.** test75 doubles the port at the same
    spacing and port count, so `d/L` at any point on the trajectory is about 1.4x the base run's
    while `z* = alpha z / L` is unchanged. The exe moves 0.568 to **0.542**, 4.6 %, so the level is
    **not** a function of overlap depth.

    ⚠️ **Ours moves the other way** -- 0.641 for the wide port against 0.619 for the base, where the
    exe reads it *lower*. Both differences are small against a 0.5-0.7 level, but the sign is wrong
    and it is recorded rather than rounded away.

    ⚠️ test75 is also the suite's worst arm -- 10.53 % post-merge braked against 4.30-5.95 % --
    and carries the lowest onset dilution, 26.8 against 57.0. Row 267b's axis again.
    """
    levels = _case43_levels()
    return abs(levels["25wide"] - levels[25])


_CASE44 = "reference_cases/case44_spacing_sweep"

#: case44's spacing sweep: `(spacing, trace)`. 25 ports, 0.0127 m port, 0.005 m3/s, 35 psu, so
#: only the spacing changes. The unmerged denominator is case43's **test71** -- one port at the
#: same port and per-port flow, and spacing is inert on one port (row 191o), so one control serves
#: every arm. ⚠️ The 1.60 m arm never reaches `d/L` 1.5 and so has no bin in the standard window.
_CASE44_ARMS = (
    (0.30, "test77"),
    (0.45, "test78"),
    (0.60, "test79"),
    (0.80, "test80"),
    (1.10, "test81"),
)


@cache
def _case44_levels() -> dict[float, float]:
    """`spacing -> the exe's suppression level`, all against case43's single-port test71."""
    control = _dat(f"{_CASE43}/test71.dat")
    frame = control.nearfield
    frame = frame[np.isfinite(frame["Dilutn"].to_numpy(dtype=np.float64))]
    banner = next(e.next_step for e in control.events if "merg" in e.text.lower() and e.next_step)
    control_time = frame["Time"].to_numpy(dtype=np.float64)
    control_rate = np.gradient(np.log(frame["Dilutn"].to_numpy(dtype=np.float64)), control_time)
    clean_until = float(frame.loc[banner, "Time"])

    out: dict[float, float] = {}
    for spacing, run in _CASE44_ARMS:
        parsed = _dat(f"{_CASE44}/{run}.dat")
        arm = parsed.nearfield
        keep = np.isfinite(arm["P-dia"].to_numpy(dtype=np.float64)) & np.isfinite(
            arm["Dilutn"].to_numpy(dtype=np.float64)
        )
        arm = arm[keep]
        arm_banner = next(
            e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step
        )
        times = arm["Time"].to_numpy(dtype=np.float64)
        window = (times > float(arm.loc[arm_banner, "Time"])) & (times < clean_until)
        ratio = np.gradient(np.log(arm["Dilutn"].to_numpy(dtype=np.float64)), times)[
            window
        ] / np.interp(times[window], control_time, control_rate)
        depth = arm["P-dia"].to_numpy(dtype=np.float64)[window] / spacing
        out[spacing] = _case43_reduce(depth, ratio)
    return out


def _the_residual_walks_with_spacing() -> float:
    """Where the shipped closure's offset against the exe crosses zero. **0.62 m** of spacing.

    ⭐⭐ **Row 272's open item, answered.** Row 264b saw the residual at -0.071 / +0.049 / +0.145
    on three case41 spacings and could not tell a law from three samples straddling zero. case44
    gives six spacings at one port count and one flow:

    | spacing | exe | ours | offset |
    |---|---|---|---|
    | 0.30 m | 0.572 | 0.695 | **+0.123** |
    | 0.45 m | 0.540 | 0.619 | **+0.079** |
    | 0.60 m | 0.644 | 0.665 | **+0.021** |
    | 0.80 m | 0.744 | 0.664 | **-0.080** |
    | 1.10 m | 0.698 | 0.622 | **-0.076** |

    A **monotone walk** from +0.123 to -0.080, crossing zero near **0.62 m**. So the sign change is
    a smooth function of the spacing and there is a law to find, which is what row 272 could not
    say from three points.

    ⭐ **And the exe's own level rises with spacing**, 0.540 to 0.744 -- a 0.204 spread, the same
    order as its port-count spread (row 271). ⚠️ Our closure is nearly flat over the same range
    (0.619 to 0.695), so what is missing is a *spacing* dependence, not a constant.

    ⭐ **It agrees with case41 where they overlap**: case41's 0.75 m read 0.766 against this
    sweep's 0.80 m at 0.744, its 0.25 m read 0.580 against this 0.30 m at 0.572, and its 0.50 m
    read 0.568, between this 0.45 m and 0.60 m. The non-monotone look of case41's three points was
    coarse sampling.

    ⚠️ The mean offset is only **+0.014**, so what ships is nearly unbiased across the sweep and
    carries a tilt of about +/-0.10. The retired default was biased +0.241 *and* tilted.

    Pinned as the zero crossing, linearly interpolated, because that is the one number a fix has to
    reproduce and it does not move with whichever arm happens to be widest.
    """
    levels = _case44_levels()
    ours = {0.30: 0.695, 0.45: 0.619, 0.60: 0.665, 0.80: 0.664, 1.10: 0.622}
    offsets = [(spacing, ours[spacing] - levels[spacing]) for spacing, _ in _CASE44_ARMS]
    for (left, low), (right, high) in pairwise(offsets):
        if low >= 0.0 > high:
            return left + (right - left) * low / (low - high)
    raise AssertionError(f"the offset no longer changes sign across spacing: {offsets}")


def _multiport_limiting_spacing_lag() -> float:
    """Steps from the port-depth crossing to the banner on case42's 5 m control. **32**.

    ⚠️ **Row 261 holds and its lag does not.** case41's test68 fired 6 steps after the diameter
    crossed the 2.0 m port depth; case42's control, the same rule on the same port depth at the same
    5 m spacing with a 1.5x port, fires **32** steps after -- crossing at step 335 and `t` = 87.0 s,
    banner at step 367 and `t` = 113.2 s, `d/L` = 0.486.

    So the *rule* is confirmed twice on multiport diffusers -- it fires on any diffuser whose plume
    outgrows its port depth, regardless of spacing or port count -- and the *lag* is a variable
    between 6 and 32 steps on the two runs that have it. That is row 191b's unexplained lag
    reappearing where it had been thought single-port-only.

    ⚠️⚠️ **The prediction for this was half right, and the half it got wrong is the
    interesting one.** It said ~85 s, taken to be the port-depth crossing. The crossing is at 87.0 s
    -- 1.7 % out, a good prediction of the *trigger* -- and the banner is 26 s later. Predicting a
    trigger is not predicting the banner, and this run is the second time that distinction has cost
    a prediction.

    ⚠️ The far field then prints *"Note: Plumes not merged"* over the top of it, the second
    instance after test68. Report to SSMC.
    """
    parsed = _dat(f"{_CASE42}/{_CASE42_CONTROL[0]}.dat")
    frame = parsed.nearfield
    keep = np.isfinite(frame["P-dia"].to_numpy(dtype=np.float64))
    frame = frame[keep]
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    depth = _case42_case("control").diffuser.port_depth
    crossed = np.flatnonzero(frame["P-dia"].to_numpy(dtype=np.float64) >= depth)
    if not crossed.size:
        raise AssertionError("case42's control never reaches its port depth")
    if not any("not merged" in event.text.lower() for event in parsed.events):
        raise AssertionError("the far-field 'Plumes not merged' advisory is gone")
    return float(banner - int(frame.index.to_numpy()[crossed[0]]))


def _calcium_follows_the_salinity_law() -> float:
    """Worst deviation of `calcium_from_salinity` from `0.01028 * S/35`. **0.0** mol/kg.

    Row 111, and it is the other half of row 61. The manual's section 3.2 derives total calcium
    from salinity rather than reading it, which is *why* the exe's `Ca` input column is inert --
    there is nowhere for an entered value to go. Checked across S 0-45 psu on 200 points, the
    implementation is the law exactly, to the last bit.

    ⭐ Worth having executable even though it is a one-line relation, because it is the mechanism
    behind an observable defect: a user who types a calcium concentration into the exe gets no
    warning and no effect, and this is the line that explains it.

    ⚠️ `CALCIUM_AT_S35` is the manual's rounded 0.01028; PyCO2SYS carries Riley & Tongudai's
    unrounded 0.0102845, which is a known and recorded source of a small Omega offset. This row
    measures fidelity to the *manual*, which is what the exe follows.
    """
    from plumes2.chem import calcium_from_salinity
    from plumes2.chem.constants import CALCIUM_AT_S35

    salinity = np.linspace(0.0, 45.0, 200)
    law = CALCIUM_AT_S35 * salinity / 35.0
    return float(np.max(np.abs(np.asarray(calcium_from_salinity(salinity)) - law)))


def _brucite_dissolution_is_athermal() -> float:
    """`Ksp*` ratio for brucite over a 15 C swing. **1.0084** -- athermal, as it should be.

    Row 197, and the number that matters is the one it replaced. An earlier revision carried
    **-111.3 kJ/mol**, a *formation*-scale enthalpy, where the reaction enthalpy from standard
    formation enthalpies is **-2.29 kJ/mol** -- 48x too large. With the wrong value this same
    ratio reads **10.359**: a **ten-fold** error in `Ksp*` at near-field temperature, and
    therefore in every `Omega_brucite`, with nothing downstream complaining.

    ⭐⭐ **That is why phase 8 needs its own discipline.** `Omega_brucite` has no parity target by
    construction (row 195) -- the exe cannot report it -- so a 10x error in it produces no failing
    comparison anywhere. The only defences are analytical limits, internal consistency and the
    literature, and this row is one of them.

    ⚠️ 1.0084 is not exactly 1: real brucite dissolution is *very nearly* athermal rather than
    athermal, and 0.8 % over 15 C is the correct residual temperature dependence rather than a
    tolerance.
    """
    from plumes2.chem.constants import solubility_brucite

    warm = float(solubility_brucite(35.0, 25.0))
    cold = float(solubility_brucite(35.0, 10.0))
    return cold / warm


def _registry_reaches_both_consumers() -> float:
    """Targets in the registry that the rendered report does not name. **0**.

    Row 218's claim is *"one registry, two consumers"* -- `pytest` asserts each measurement and
    `plumes2 validate` tabulates them -- and the risk it names is the two drifting apart. So the
    executable form is not a coverage fraction, which is published in the header and guarded
    separately; it is the **invariant**: every row the test suite drives must appear on the page,
    or the page is a subset presented as the whole.

    ⚠️ **This is mildly self-referential and that is why it went unwritten for four days.** It is
    still worth having: the failure it catches is a target added to the registry that the renderer
    silently skips -- a row measured on every build and shown to nobody -- which is exactly the
    "correct arithmetic, wrong presentation" shape this ledger keeps hitting.

    Rendered from outcomes stubbed at their own references, so this checks the *page* and never
    depends on whether the physics currently agrees.
    """
    from plumes2.report.validation import render_validation

    html = render_validation([Outcome(target=t, ours=t.reference) for t in TARGETS])
    return float(sum(1 for t in TARGETS if t.row not in html))


@cache
def _case06_inert_calcium_ratio() -> float:
    """The exe's `OmegaA` over ours, on case06's deliberately wrong `Ca`. **0.965**.

    ⭐⭐ **Row 61, and the run was designed so the answer could only be one of two numbers.**
    case06 enters an ambient `Ca` of **5000** micromol/kg against roughly **10 500** for seawater
    at S = 36. So:

    | if the exe **uses** the entered `Ca` | its Omega halves | ratio **~0.48** |
    |---|---|---|
    | if the exe **derives** `Ca` from salinity | its Omega is unchanged | ratio **~0.97** |

    Measured over case06's far-field table -- where `TA`, `DIC` and `OmegaA` are all printed on
    the same rows, so no reconstruction is needed -- the ratio is **0.965**, which is the archive's
    ordinary exe/PyCO2SYS offset and nothing more. **The `Ca` column is inert.**

    ⭐ And because both precipitation rate laws reproduce from Omega alone (rows 68, 83), an input
    that does not reach Omega does not reach the rates either: the column is inert *everywhere*,
    not just for saturation. Row 111 is the mechanism -- the manual derives calcium from salinity,
    so an entered value has nowhere to go.

    ⚠️⚠️ **A defect worth reporting**, and it is on the SSMC list: the exe accepts a calcium
    concentration, silently ignores it, and prints no warning. A user who measures their receiving
    water's calcium and enters it will believe it was used.

    ⚠️ case06's own `testco2.csv` still carries an older `Ca = 100`; the README is authoritative
    that the run used 5000. Either way the entered value is wrong by a factor of two or a hundred
    and the ratio is 0.965, which is the point.
    """
    import PyCO2SYS as pyco2

    parsed = _dat("reference_cases/case06_macoma_arag_s36/test5_TxtOutputs.dat")
    far = parsed.farfield
    if far is None or "OmegaA" not in far.columns:
        raise AssertionError("case06 no longer prints a far-field OmegaA")

    ambient = parsed.echoed_tables["Ambient"]
    salinity = float(ambient["Amb-sal"].iloc[0])
    temperature = float(ambient["Amb-tem"].iloc[0])
    result = pyco2.sys(
        par1=far["TA"].to_numpy(dtype=np.float64),
        par2=far["DIC"].to_numpy(dtype=np.float64),
        par1_type=1,
        par2_type=2,
        salinity=salinity,
        temperature=temperature,
        opt_k_carbonic=10,
        opt_k_bisulfate=1,
        opt_total_borate=2,
    )
    ours = np.asarray(result["saturation_aragonite"], dtype=np.float64)
    theirs = far["OmegaA"].to_numpy(dtype=np.float64)
    usable = np.isfinite(ours) & np.isfinite(theirs) & (theirs > 0.0) & (ours > 0.0)
    if usable.sum() < 10:
        raise AssertionError(f"only {int(usable.sum())} usable OmegaA rows in case06")
    return float(np.mean(theirs[usable] / ours[usable]))


def _limiting_spacing_fires_on_a_multiport() -> float:
    """Steps between the port-depth crossing and the banner on a 25-port, 5 m-spaced run. **6**.

    ⭐⭐⭐ **Row 261, and it widens row 191o.** case41's control was requested purely as an
    unmerged reference: 25 ports at a 5 m spacing, where a 2.3 m plume cannot possibly reach its
    neighbours. It prints `merging happened` anyway -- at step 373, **six steps** after the printed
    diameter crosses the 2.0 m **port depth** at 367, with `d/L` = 0.41.

    So UM3's limiting-spacing rule is **not single-port behaviour**. Row 191o showed the entered
    spacing is inert on one port; this shows the rule ignores the port *count* too, and fires on any
    diffuser whose plume outgrows its port depth. Every earlier observation of it happened to be on
    a single port, which is how a general rule looked like a special case.

    ⚠️⚠️ **And the exe contradicts itself in the same file.** The near field declares
    merging at 373; the far field then prints *"Note: Plumes not merged, Brooks method may be overly
    conservative"*. One run, two answers, and the entrainment suppression is applied on the strength
    of the first. That is a report-to-SSMC item: a user at a wide spacing gets a merged near field
    they did not ask for and an advisory telling them the opposite.

    ⚠️ The 6-step lag is row 191b's unexplained lag again, at the low end of its 0-54 range.
    """
    from plumes2.io.dat import read_dat

    parsed = read_dat(_ROOT / _CASE41 / f"{_CASE41_CONTROL}.dat")
    frame = parsed.nearfield
    echo = parsed.echoed_tables["Diffuser"]
    if int(float(echo["Ports"].iloc[0])) <= 1:
        raise AssertionError("the control is no longer a multiport run")
    depth = _case(f"{_CASE41}/Macoma2.prj").diffuser.port_depth
    diameters = frame["P-dia"].to_numpy(dtype=np.float64)
    steps = frame.index.to_numpy()
    crossed = np.flatnonzero(diameters >= depth)
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    if not crossed.size:
        raise AssertionError("the control never reaches its port depth")
    if float(diameters[int(np.flatnonzero(steps == banner)[0])]) / 5.0 > 0.5:
        raise AssertionError("the control's plume is no longer far short of its spacing")
    if not any("not merged" in e.text.lower() for e in parsed.events):
        raise AssertionError("the far-field 'Plumes not merged' advisory is gone")
    return float(banner - int(steps[crossed[0]]))


def _deep_overlap_penalty() -> float:
    """Post-merge dilution MARE at `d/L` 4.05. **28.8 %** -- a recorded divergence, not a match.

    **Where the merging closure stops working, measured on data that did not exist when it was
    written.** case40's test58 puts a 0.25 m spacing under a plume that grows to 1.0 m, so it
    reaches `d/L` 4.05 -- nearly double case20's 2.35, which was the archive's deepest credible
    overlap. Over the same geometry the *unmerged* control (test56, 2 m) is 2.10 %, so this is
    merging's error and not the regime's.

    The mechanism is `_deep_overlap_runaway`: entrainment is under-suppressed at deep overlap, the
    element over-inflates, and the dilution follows. Rows 157b and 186 are the same defect.

    Predicted 15-25 % before the run and measured 28.8 % -- outside the registered range, in the
    direction of the defect being worse. Recorded as a miss rather than rounded into a hit.
    """
    return _case40_error("test58", 0.25)[0]


def _deep_overlap_control_error() -> float:
    """The same geometry with a 2 m spacing, which never merges. 2.10 %.

    The control for the row above, and it is doing real work: a 2 psu effluent is outside anything
    this closure was tuned on, so some error belongs to the regime rather than to merging. This
    measures how much -- and 2.10 % against 28.8 % says the rest is merging's.
    """
    return _case40_error("test56", 2.0)[0]


_CASE41 = "reference_cases/case41_suppression_curve"

#: case41's runs: `(trace, spacing, effluent salinity)`. The project describes none of them --
#: it is the 2 psu / 2.0 m / 90 degree base -- so each is rebuilt from it. The echo carries the
#: spacing and the angle; the salinity is the user's record (see the case README).
_CASE41_RUNS = (
    ("test65", 0.75, 35.0),
    ("test63", 0.50, 35.0),
    ("test64", 0.25, 35.0),
    ("test66", 0.50, 40.0),
    ("test67", 0.50, 45.0),
)


@cache
def _case41_error(run: str, spacing: float, salinity: float) -> tuple[float, float]:
    """`(post-merge dilution MARE, our max diameter over the exe's)` on a case41 run.

    Every row is finite here -- a near-neutral effluent traps rather than surfacing -- so unlike
    case40 there is no NaN tail to work around.
    """

    parsed = _dat(f"{_CASE41}/{run}.dat")
    frame = parsed.nearfield
    base = _case(f"{_CASE41}/Macoma2.prj")
    case = base.model_copy(
        update={
            "diffuser": base.diffuser.model_copy(
                update={"port_spacing": spacing, "horizontal_angle": 65.0}
            ),
            "effluent": base.effluent.model_copy(update={"salinity": salinity}),
        }
    )
    times = frame["Time"].to_numpy(dtype=np.float64)
    solution = _integrate_once(case, max_time=float(times[-1]) + 5.0)
    usable = times <= solution.solution.t[-1]  # type: ignore[attr-defined]
    ours = solution.sample(times[usable])
    dilution = frame["Dilutn"].to_numpy(dtype=np.float64)[usable]
    diameter = frame["P-dia"].to_numpy(dtype=np.float64)[usable]
    error = np.abs(ours.dilution - dilution) / dilution
    banner = next(e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step)
    after = frame.index.to_numpy()[usable] >= banner
    return float(error[after].mean()), float(ours.diameter.max() / diameter.max())


def _deep_overlap_runaway() -> float:
    """Our merged diameter over the exe's, worst in the archive. **11.93x**, on case41's test67.

    Row 186. Eq 56 inflates the element to hold its area against a transverse cap, and nothing in
    this port opposes it, so the merged radius grows quadratically. On case41's test67 ours reaches
    **22.784 m** at matched time where the exe is at **1.910 m**, and case40's test58 -- the
    previous worst -- gave 6.65x.

    ⚠️ **Salinity moves it, in the direction the mechanism predicts**: 8.63x at 35 psu, 10.69x at
    40 and 11.93x at 45, all at the same 0.5 m spacing. A denser effluent sinks harder and so
    spends longer in the deep-overlap regime where the inflation is unopposed.

    **The sign is wrong, not just the size.** The exe's element *stops growing* under deep
    confinement: 1.141 m unmerged, 1.193 m at `L` = 0.5, and 1.012 m at `L` = 0.25 -- deep merging
    makes it **smaller** than the unmerged run, where ours inflates by a factor of six. So the exe
    has a brake this port lacks entirely, and eq 56, unopposed, has the wrong asymptote.

    ⚠️ The reference has moved twice, each time because a **worse** sample arrived -- 2.05x
    (case21's test34), 6.65x (case40's test58), now 11.93x -- so it deliberately tracks the worst
    rather than being pinned to the run that first found it.

    ⚠️ Quoted **at matched time**: our runs terminate before the exe's, so these are not
    maxima over a common window. test64's smaller 5.48x is an artefact of its run ending earliest,
    not of it being better behaved.
    """
    return max(_case41_error(*run)[1] for run in _CASE41_RUNS)


def _spacing_inert_until_merging() -> float:
    """Worst numeric difference between case40's 2 m and 3 m runs, neither of which merges. Zero.

    A third instance of "the file changes, the numbers do not" (rows 191l, 191o). test56 and
    test59 differ only in a spacing neither plume ever reaches, so they agree exactly on every
    column across all 272 finite rows while their bytes differ -- the diffuser echo prints the
    spacing. case20's test31/test33 said the same at 2 m against 5 m.
    """
    left = _dat(f"{_CASE40}/test56.dat").nearfield
    right = _dat(f"{_CASE40}/test59.dat").nearfield
    finite = np.isfinite(left["P-dia"].to_numpy(dtype=np.float64))
    shared = [column for column in left.columns if column in right.columns]
    if len(shared) < 10 or len(left) != len(right):
        raise AssertionError("case40's controls are no longer comparable")
    worst = 0.0
    for column in shared:
        worst = max(
            worst,
            float(
                np.max(
                    np.abs(
                        left[column].to_numpy(dtype=np.float64)[finite]
                        - right[column].to_numpy(dtype=np.float64)[finite]
                    )
                )
            ),
        )
    return worst


def _boundary_criterion_violations() -> float:
    """Archived boundary events where the plume's **edge** had not reached the boundary. Zero.

    The criteria are about the edge, not the centreline: a plume surfaces when
    `depth - radius <= 0` and hits the seabed when `depth + radius >= bottom`, with the seabed
    derived as `port_depth + port_elevation`. Counting violations rather than measuring a distance
    is deliberate -- these are one-sided conditions, and how far past the boundary the printed row
    happens to sit is an artefact of the output interval, not a quantity worth pinning.
    """
    from plumes2.io.dat import read_dat

    violations = 0
    events = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if frame.empty or not {"Depth", "P-dia"} <= set(frame.columns):
            continue
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        radius = frame["P-dia"].to_numpy(dtype=np.float64) / 2.0
        index = frame.index.to_numpy()
        diffuser = parsed.echoed_tables.get("Diffuser")
        seabed = (
            float(diffuser["P-depth"].iloc[0]) + float(diffuser["P-elev"].iloc[0])
            if diffuser is not None
            else None
        )
        for event in parsed.events:
            if event.next_step is None:
                continue
            at = int(np.argmin(np.abs(index - event.next_step)))
            if not (np.isfinite(depth[at]) and np.isfinite(radius[at])):
                continue
            text = event.text.lower()
            if "surface" in text:
                events += 1
                violations += depth[at] - radius[at] > 0.0
            elif "bottom" in text and seabed is not None:
                events += 1
                violations += depth[at] + radius[at] - seabed < 0.0
    if events < 20:
        raise AssertionError(f"only {events} boundary events found; expected more")
    return float(violations)


def _turning_point_offset() -> float:
    """Worst distance from a `Local maximum rise or fall` banner to a depth extremum.

    The banner marks `dz/dt = 0`. Over 116 events it lands on the extremum of its own neighbourhood
    to within **0.002 m**, which is two units in `Depth`'s last printed digit -- and the residual is
    the output interval rather than the rule: with every fifth step printed, the true turning point
    usually falls between rows, exactly as row 56's trapping depth does.
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    events = 0
    for path in _archive_traces():
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if frame.empty or "Depth" not in frame.columns:
            continue
        depth = -frame["Depth"].to_numpy(dtype=np.float64)
        index = frame.index.to_numpy()
        for event in parsed.events:
            if event.next_step is None or "maximum rise" not in event.text.lower():
                continue
            at = int(np.argmin(np.abs(index - event.next_step)))
            window = depth[max(0, at - 3) : min(len(depth), at + 4)]
            if len(window) < 3 or not np.all(np.isfinite(window)):
                continue
            events += 1
            worst = max(worst, min(abs(depth[at] - window.min()), abs(depth[at] - window.max())))
    if events < 50:
        raise AssertionError(f"only {events} turning-point events found; expected more")
    return worst


def _step_mass_growth_cap() -> float:
    """Largest per-step mass growth anywhere in the archive, as a fraction.

    `Dilutn` is exactly `m / m_e` (row 135), so the ratio of consecutive dilutions *is* the mass
    growth -- raised to `1/steps` because most traces print every fifth step. The exe's step
    controller varies the time step to hold this near 2 %, which is why comparisons against a trace
    are made at its printed **times** rather than step-for-step: the physics sets how long a step
    takes, so matching step numbers would compare different instants.
    """
    from plumes2.io.dat import read_dat

    worst = 0.0
    traces = 0
    for path in _archive_traces():
        try:
            frame = read_dat(path).nearfield
        except Exception:
            continue
        if frame.empty or "Dilutn" not in frame.columns:
            continue
        dilution = frame["Dilutn"].to_numpy(dtype=np.float64)
        index = frame.index.to_numpy().astype(np.float64)
        usable = np.isfinite(dilution) & (dilution > 0.0)
        dilution, index = dilution[usable], index[usable]
        if len(dilution) < 40:
            continue
        steps = np.diff(index)
        steps[steps <= 0] = np.nan
        growth = (dilution[1:] / dilution[:-1]) ** (1.0 / steps) - 1.0
        growth = growth[np.isfinite(growth) & (growth > 0.0)]
        if len(growth) < 20:
            continue
        traces += 1
        worst = max(worst, float(growth.max()))
    if traces < 50:
        raise AssertionError(f"only {traces} traces carried a usable dilution column")
    return worst


def _contraction_mass_flux_spread() -> float:
    """Spread in `b0^2 rho_e |U0|` as the contraction coefficient varies. Zero.

    ⭐ The identity that makes the contraction *self-consistent*: `c` shrinks the jet's area to `c`
    times the port's, so `b0 = (d/2) sqrt(c)` and `|U0| = Q/(n c A)` -- and the mass flux they
    imply, `rho_e Q/(n pi)`, does not contain `c` at all. So the contraction redistributes the
    discharge between radius and speed without inventing or destroying mass, and a run's initial
    momentum changes while its mass flux does not.
    """
    import math

    from plumes2.nearfield.state import exit_speed, initial_radius

    case = _case("reference_cases/case18_zero_current_pair/test21.prj")
    density = 1026.96
    fluxes = []
    for coefficient in (1.0, 0.61, 0.4, 0.25):
        variant = case.model_copy(
            update={
                "near_field": case.near_field.model_copy(
                    update={"contraction_coefficient": coefficient}
                )
            }
        )
        radius = float(initial_radius(variant))
        expected = (variant.diffuser.port_diameter / 2.0) * math.sqrt(coefficient)
        if abs(radius - expected) > 1e-12:
            raise AssertionError(f"c={coefficient}: b0 {radius} against (d/2)sqrt(c) {expected}")
        fluxes.append(radius * radius * density * float(exit_speed(variant)))
    return max(fluxes) - min(fluxes)


#: Traces run under a **non-default similarity profile**, excluded from the peak-to-mean sweep.
#:
#: ⚠️⚠️ **Row 198's "zero exceptions over 8 617 rows" was measured under one setting, and nobody
#: knew it was a setting.** case48 (2026-08-25) enumerated the exe's similarity-profile selector --
#: `Default Profile`, `3/2 Power law Profile`, `Gaussian Profile` -- and the control is real: the
#: same geometry gives a peak-to-mean of 2.00000, 3.88997 and 3.66998 respectively. Graduating
#: those traces into the archive put **573 exceptions** into a row whose whole claim is that there
#: are none.
#:
#: ⭐ The row is not wrong; its scope was implicit. `CL-Dil = max(1, Dilutn/2)` holds on every
#: archived row produced under the **default** profile, which is every trace in the archive except
#: these two. Excluding them by name keeps the claim falsifiable -- a new default-profile trace
#: that broke it would still be caught -- where widening the tolerance would have destroyed it.
#: Row 278 measures what these two traces say instead.
NON_DEFAULT_PROFILE_TRACES = frozenset(
    {
        "style_threehalves.dat",
        "style_gaussian.dat",
        # case49 (2026-08-26): the same two options on a merging plume. Row 279 measures them.
        "profile_merged_three_halves_legacy.dat",
        "profile_merged_gaussian_legacy.dat",
    }
)


def _profile_plateau(path: Path) -> float:
    """The developed `Dilutn / CL-Dil` plateau of one trace, mean over its `Dilutn > 5` rows.

    The ratio is 1.02 on the first printed row and climbs as the plume develops, so a mean over
    every row understates it (1.9476 against 2.0000 on the default profile). Past a dilution of 5
    it is flat to five figures, which is what makes the three options distinguishable at all.
    """
    from plumes2.io.dat import read_dat

    frame = read_dat(path).nearfield
    ratio = (frame["Dilutn"] / frame["CL-Dil"]).to_numpy(dtype=np.float64)
    developed = frame["Dilutn"].to_numpy(dtype=np.float64) > 5.0
    usable = ratio[developed & np.isfinite(ratio)]
    if usable.size < 100:
        raise AssertionError(f"{path.name}: only {usable.size} developed rows")
    spread = float(np.max(usable) - np.min(usable))
    assert spread < 5e-3, f"{path.name}: plateau is not flat, spread {spread:.2e}"
    return float(np.mean(usable))


def _three_halves_profile_gap() -> float:
    """Row 278: how far the exe's `3/2 Power law Profile` sits from the reference's own profile.

    ⭐ The strongest single number case48 produced. `[1 - u^1.5]^2` has an area-average whose
    reciprocal is exactly `3.888...`, and that is where the 3rd edition's `3.89` comes from -- the
    profile the manual documents and the exe does **not** use by default. Selecting the option
    reproduces it to **0.03 %**, which says the selector really is choosing a similarity profile
    rather than doing something else that happens to move the centreline.

    Asserted alongside, because they are the same finding and the registry keeps one target per
    row: the **default** option is the parabola to five figures, and the **Gaussian** option is
    neither -- it lands at 3.670, far from the `exp(-2u^2)` candidate (2.313) that PLAN 6b
    tabulated and PLAN 8.4 assumed a move to. ⚠️ That last one is the reason this row matters
    beyond bookkeeping: "adopt the exe's Gaussian" and "adopt the literature's Gaussian" are
    different decisions, and they looked like one until these runs.
    """
    profiles = _CASES / "case48_similarity_profiles"
    default = _profile_plateau(profiles / "style_default.dat")
    three_halves = _profile_plateau(profiles / "style_threehalves.dat")
    gaussian = _profile_plateau(profiles / "style_gaussian.dat")

    assert abs(default - 2.0) < 1e-3, f"the default option is no longer the parabola: {default}"
    assert abs(gaussian - 3.670) < 5e-3, f"the Gaussian option moved: {gaussian}"
    # The three must be *distinguishable*, which is the claim that the control does anything.
    assert three_halves - gaussian > 0.2 and gaussian - default > 1.6
    return abs(three_halves - 35.0 / 9.0)


def _profile_blend_residual() -> float:
    """Row 279: the exe walks its non-default profiles round -> slab by the parabola's linear law.

    case48 measured the three options' *round* plateaus on a geometry that never merges, so
    `crossplume.peak_to_mean` had to *assume* the blend between round and slab for the two
    non-default profiles. case49 reran case44's 0.60 m project (test79, `d/L` to 4.95) under
    each option. The number returned is the worst merged-walk row's distance from
    `max(slab, round + (round - slab)(1 - d/L))`, over both traces, with the law applied from
    the row *after* the banner -- the banner row prints the round value, as it does for the
    parabola (row 203).

    Asserted alongside, because they are the same finding and the registry keeps one target per
    row: the trajectory is **bit-identical** to test79 (the profile is post-processing), the round
    plateau reproduces case48's on a second geometry, and the slab plateau is the profile's own
    integral -- 20/9 for the 3/2 power, `2 sqrt(k) / (sqrt(pi) erf(sqrt(k)))` for the Gaussian --
    to 0.03 %, the same order as row 278's quadrature residual.
    """
    from plumes2.crossplume import (
        SimilarityProfile,
        peak_to_mean,
        peak_to_mean_round,
        peak_to_mean_slab,
    )
    from plumes2.io.dat import read_dat

    control = read_dat(_CASES / "case44_spacing_sweep" / "test79.dat").nearfield
    worst = 0.0
    for name, profile in (
        ("profile_merged_three_halves_legacy.dat", SimilarityProfile.THREE_HALVES),
        ("profile_merged_gaussian_legacy.dat", SimilarityProfile.EXE_GAUSSIAN),
    ):
        dat = read_dat(_CASES / "case49_profile_blend" / name)
        frame = dat.nearfield
        for column in ("Dilutn", "P-dia", "Time"):
            assert np.array_equal(frame[column].to_numpy(), control[column].to_numpy()), (
                f"{name}: {column} is not test79's -- the profile moved the trajectory"
            )
        spacing = float(dat.echoed_tables["Diffuser"]["Spacing"].iloc[0])
        banner = dat.event_steps()["merging happened"][0]
        steps = frame.index.to_numpy()
        ratio = (frame["Dilutn"] / frame["CL-Dil"]).to_numpy(dtype=np.float64)
        diameter = frame["P-dia"].to_numpy(dtype=np.float64)
        merged = steps > banner
        developed = frame["Dilutn"].to_numpy(dtype=np.float64) > 5.0
        before = developed & (steps < banner)
        round_gap = abs(float(np.mean(ratio[before])) - peak_to_mean_round(profile))
        assert round_gap < 1.5e-3, f"{name}: round plateau off by {round_gap:.4f}"
        slab = diameter >= 2.0 * spacing
        slab_gap = abs(float(np.mean(ratio[slab])) - peak_to_mean_slab(profile))
        assert slab_gap < 1e-3, f"{name}: slab plateau off by {slab_gap:.4f}"
        law = peak_to_mean(diameter, spacing, merged, profile)
        walk = merged & (diameter > spacing) & (diameter < 2.0 * spacing)
        assert walk.sum() > 50, f"{name}: only {walk.sum()} rows in the walk"
        worst = max(worst, float(np.max(np.abs(ratio[walk] - law[walk]))))
    return worst


def _centreline_exceptions() -> float:
    """Unmerged archived rows where `CL-Dil != max(1, Dilutn/2)` beyond printed precision.

    ⚠️ **Default-profile traces only** -- see `NON_DEFAULT_PROFILE_TRACES`.
    """
    from plumes2.crossplume import PEAK_TO_MEAN_ROUND
    from plumes2.io.dat import read_dat

    exceptions = 0
    for path in _archive_traces():
        if path.name in NON_DEFAULT_PROFILE_TRACES:
            continue
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        if "CL-Dil" not in frame.columns:
            continue
        merged_at = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step),
            None,
        )
        for step, row in frame.iterrows():
            centreline, mean = float(row["CL-Dil"]), float(row["Dilutn"])
            if not math.isfinite(centreline) or centreline <= 1.0:
                continue
            if merged_at is not None and int(str(step)) >= merged_at:
                continue
            # 1.1e-3 is what three printed decimals leave once `Dilutn` passes 1000.
            exceptions += abs(mean / centreline - PEAK_TO_MEAN_ROUND) > 1.1e-3
    return float(exceptions)


# ------------------------------------------------- Phase 6, the presentation layer
#
# Rows 201, 211, 212 and 213. ⚠️ All four are `internal`: they are claims about **our** code, and
# the exe has no counterpart to check them against -- it cannot take a trace as plot input, cannot
# reconstruct the secondaries it never printed, and ships no report. They are here so those claims
# stop resting on prose, not because they are parity evidence, and each note says so.

#: The two chemistry-carrying traces whose project is archived, so plume salinity and temperature
#: can be resolved. `(label, directory, trace, project)`.
#:
#: ⚠️⚠️ **The trace is named, and it used to be `glob("*.dat")[0]`.** That picked whichever file
#: sorted first, so archiving `kso4_option3.dat` in case03's folder on 2026-08-20 silently switched
#: rows 201 and 211 onto a different run -- an interval-1 trace with ten times the rows, including
#: early steps at pH > 10 where the reconstruction is at its worst. Both targets failed, and the
#: cause was the *selector*, not the data or the code under test. A census may glob; a target that
#: quotes a specific number must name its input.
_CHEMISTRY_TRACES = (
    ("case03", "case03_macoma_carbonate", "test2_TxtOutputs.dat", "test.prj"),
    ("case13", "case13_generated_example", "PythonGenerated2.dat", "PythonGenerated.prj"),
)

#: The secondaries the exe never printed, named in row 201.
_SECONDARIES = ("pco2_uatm", "carbonate_umol_kg", "bicarbonate_umol_kg", "omega_brucite")


@cache
def _plot_frames():  # type: ignore[no-untyped-def]
    """`(label, the exe's own frame, our `PlotFrame` with the secondaries filled in)`."""
    from plumes2.io.dat import read_dat
    from plumes2.plotframe import from_dat

    built = []
    for label, directory, filename, project in _CHEMISTRY_TRACES:
        trace = _CASES / directory / filename
        if not trace.exists():
            raise AssertionError(f"{label}: {filename} is missing from the archive")
        parsed = read_dat(trace)
        case = _case(f"reference_cases/{directory}/{project}")
        plot = from_dat(parsed, label, case=case, secondaries=True)
        built.append((label, parsed.nearfield, plot))
    return tuple(built)


def _trace_secondaries_missing() -> float:
    """Named secondaries the plot frame fails to derive from an exe trace. Zero of eight.

    Row 201. The frame has to accept a `.dat` as input, not just a `Results` object, and then fill
    in the quantities the exe never carried: `pCO2`, carbonate, bicarbonate and **Ω_brucite**. Nine
    columns are added in all -- those four plus plume salinity and temperature and the three
    saturation states -- from the exe's own TA and DIC.

    ⚠️ **`internal`, and the reason matters**: the exe cannot do this at all, so there is no
    reference. Ω_brucite in particular is the quantity it has no code for (row 195). What is
    checked is that the columns arrive and are finite, and row 211 is what checks they are *right*
    -- by re-deriving a quantity the exe **did** print, on the same reconstruction.

    ⚠️ Scoped to the two chemistry traces whose project is archived, because plume salinity and
    temperature cannot be reconstructed without one. `secondaries=False` is what row 210 runs over
    all 141 traces.
    """
    missing = 0
    for _label, _exe, plot in _plot_frames():
        for column in _SECONDARIES:
            if column not in plot.frame.columns:
                missing += 1
            elif not np.isfinite(plot.frame[column].to_numpy(dtype=np.float64)).any():
                missing += 1
            elif column not in plot.derived:
                # A column the frame does not admit it computed would read as the exe's own.
                missing += 1
    return float(missing)


def _chemistry_from_trace_error() -> float:
    """Worst pH difference between our reconstruction and the exe's own printed column. 0.0272.

    Row 211, and it is what makes row 201 trustworthy rather than merely populated. Deriving the
    secondaries from a trace needs plume salinity and temperature, which the exe does not print --
    they are mixed from the case. If that reconstruction were wrong the secondaries would be wrong
    with it, silently, because nothing downstream complains.

    So the check re-derives a quantity the exe **did** print, on the same reconstruction: pH from
    its own TA and DIC. case03 lands within **0.0236** (mean 0.0120) over 41 rows and case13 within
    0.0272 (mean 0.0129) over 55, with `Ω_arag` at 3.2 % on both.

    ⚠️ **Inside the pre-existing exe-vs-PyCO2SYS offset**, which is the point: the residual is the
    carbonate-system disagreement rows 41-46 already measure, not an error introduced by
    reconstructing S and T. ⚠️ The sign is **not** uniform -- case03 is one-signed over all
    41 rows while case13 crosses over late, 49 positive and 6 negative -- so this is a bounded
    disagreement rather than a calibration offset that could be subtracted out.
    """
    worst = 0.0
    for _label, exe, plot in _plot_frames():
        if "pH" not in exe.columns:
            raise AssertionError("the exe trace no longer prints pH")
        theirs = exe["pH"].to_numpy(dtype=np.float64)
        mine = plot.frame["ph_total"].to_numpy(dtype=np.float64)
        usable = np.isfinite(theirs) & np.isfinite(mine)
        worst = max(worst, float(np.max(np.abs(mine[usable] - theirs[usable]))))
    return worst


def _palette_protan_separation() -> float:
    """Worst adjacent-slot separation under simulated protanopia. **9.49**, against a floor of 8.

    Row 212, and the binding constraint of the five the palette validator applies: two slots can
    share a lightness or a chroma and still be told apart, but two adjacent slots a
    colour-blind reader cannot separate are a defect in the figure.

    ⚠️⚠️ **The published figure was 9.1 and could not be reproduced.** The canonical
    Viénot-Brettel-Mollon construction in linear light gives **9.49**; Machado's severity-1.0
    matrix gives 10.32; applying either in gamma-encoded sRGB gives 10.6. Nothing standard gives
    9.1. The *claim* survives -- 9.49 clears the floor more comfortably than 9.1 did -- so this is
    a correction, and the fix was to compute it in `report/palette.py` rather than to tune a matrix
    until it agreed with a comment. That is the whole reason for making a claim executable: the
    palette's entire argument is that it was **validated rather than chosen**, and until now that
    rested on five numbers nothing recomputed.

    ⚠️ Adjacent pairs only, which is a real restriction and a deliberate one: slots are assigned in
    order and never cycled, so a non-adjacent pair is never asked to be distinguished. The worst
    pair over *all* six combinations is 13.7, still above the floor, but it is not the claim.
    """
    from plumes2.report.palette import validate

    return validate().protan_separation


def _palette_normal_separation() -> float:
    """Worst adjacent-slot separation under normal vision. **22.92**, against a floor of 15.

    Row 212b, and the companion that reproduces **exactly**: the docstring said 22.9 and the
    computation agrees to the digit it was quoted at. Worth having beside row 212 precisely because
    it did agree -- it localises the 9.1 discrepancy to the colour-vision simulation rather than to
    the colour space, the palette or the whole method.

    Both figures are OkLab dE x 100. OkLab rather than CIELAB because the validator's other two
    checks -- the lightness band and the chroma floor -- are stated in OkLab, and mixing spaces
    across one validator would make its numbers incomparable. ⚠️ CIELAB does not reproduce
    either figure: CIE76 gives 90.0 and CIEDE2000 43.2 for this same pair, which is how the space
    was identified.
    """
    from plumes2.report.palette import validate

    return validate().normal_separation


def _palette_worst_contrast() -> float:
    """Lowest slot contrast against the chart surface. **2.11:1**, below the 3:1 target.

    Row 212c, and it is the validator's one **WARN** rather than a pass -- recorded as such because
    a palette that reported five passes would be misrepresenting itself. Yellow sits at 2.11:1 and
    aqua at 2.74:1 against `SURFACE`; blue and orange clear 3:1.

    ⚠️ **The warning is discharged, not dismissed.** The rule for a slot below 3:1 is *relief*: it
    may not carry meaning by colour alone. Every multi-series panel direct-labels its lines at the
    right-hand end and every panel carries a table of the values it plots, so the two low-contrast
    slots never have to be told apart by colour. Row 213 is what holds the tables in place. ⚠️ It
    is also why the report has **no scatter** form, where every pair would have to clear the floors
    and these four do not.
    """
    from plumes2.report.palette import validate

    return min(validate().contrast)


def _report_external_references() -> float:
    """Things a rendered report would have to fetch to display correctly. Zero.

    Row 213. The report is one file: inline SVG, inline CSS, no JavaScript, and nothing to
    retrieve. That is what makes it survivable -- it can be emailed, archived or opened offline in
    ten years, which a page pulling a CDN cannot.

    Four things are counted, and all four are zero: `<script>` tags, `<link>`/`<img>`/`<iframe>`
    elements, `url(...)` references that point outside the document, and inline `on*` handlers.

    ⚠️ **A naive grep for `http://` finds 63 and they are all inert**, which is why the
    measurement is written this way rather than as a URL count. matplotlib stamps every SVG it
    writes with XML namespace URIs (`w3.org/2000/svg`, `xlink`) and an RDF metadata block citing
    Dublin Core, Creative Commons and `matplotlib.org`. A namespace URI is an identifier, not a
    fetch, and no browser resolves any of them. All 149 `url(...)` references are internal
    fragments -- matplotlib's own clip paths.
    """
    import re

    from plumes2.report import render_report

    total = 0
    for _label, _exe, plot in _plot_frames():
        html = render_report(plot)
        total += len(re.findall(r"<script", html, re.IGNORECASE))
        total += len(re.findall(r"<(?:link|img|iframe)\b", html, re.IGNORECASE))
        total += len(re.findall(r"\son[a-z]+\s*=", html, re.IGNORECASE))
        total += sum(
            1
            for target in re.findall(r"url\(([^)]*)\)", html, re.IGNORECASE)
            if not target.strip("\"'").startswith("#")
        )
    return float(total)


# -------------------------------------------------------- Phase 6, the centreline profile
#
# Rows 198-207 and 221 all read the same thing out of the archive: the printed `CL-Dil` over the
# printed `Dilutn`, against `d/L`. Extracting it once matters, because every one of the exclusions
# is a recorded finding rather than a convenience, and five rows applying them slightly differently
# would be five rows measuring slightly different claims.
#
# ⚠️ **All of them are claims about the exe's DEFAULT similarity profile**, and since case49
# (2026-08-26) the archive holds *merged* traces under the other two options -- which row 198 had
# already met in the unmerged case48 traces. They are excluded by name
# (`NON_DEFAULT_PROFILE_TRACES`) here exactly as there; rows 278 and 279 measure what those traces
# say instead. Graduating case49 put 264 rows into 199, 476 into 203 and moved 204b and 221 off
# their pins until this was scoped.


@dataclass(frozen=True, slots=True)
class _CentrelineRow:
    """One printed row's peak-to-mean, with the geometry needed to judge it."""

    trace: str
    #: Nominal port spacing from the echoed diffuser table, m.
    spacing: float
    #: Echoed horizontal discharge angle, degrees. The ambient current runs at 90 in every
    #: archived multiport run, so this is the obliquity.
    angle: float
    step: int
    diameter: float
    #: `CL-Dil / Dilutn`, i.e. peak over flux-average.
    ratio: float
    #: True on the merging banner's own row, which still prints the *unmerged* value (row 206).
    on_banner: bool


@cache
def _centreline_rows() -> tuple[_CentrelineRow, ...]:
    """Every merged, in-water printed row in the archive that carries a centreline. 3 770 of them.

    Three exclusions, each a finding in its own right:

    * **before the banner** -- the plume is not merged, and row 198 covers that regime;
    * **past the surface or the seabed** -- the printed diameter stops describing a submerged
      element once the top breaks through, and neither the exe nor this port has a free-surface
      treatment. case31's `surface_off` deliberately runs 297 steps past its surface hit and every
      one of its 89 misses lands there, so scoring them would measure the absence of a model;
    * **single-port runs** -- there is no spacing to normalise by;
    * **non-default similarity profiles** (`NON_DEFAULT_PROFILE_TRACES`) -- these rows are about
      the parabola; rows 278 and 279 measure the other two options.

    The banner row itself is kept and flagged rather than dropped, because row 206 is *about* it.
    """
    from plumes2.io.dat import read_dat

    collected: list[_CentrelineRow] = []
    for path in _archive_traces():
        if path.name in NON_DEFAULT_PROFILE_TRACES:
            continue
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        echo = parsed.echoed_tables.get("Diffuser")
        if "CL-Dil" not in frame.columns or echo is None or echo.empty:
            continue
        if int(float(echo["Ports"].iloc[0])) <= 1:
            continue
        spacing = float(echo["Spacing"].iloc[0])
        angle = float(echo["H-angle"].iloc[0])
        banner = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step), None
        )
        if banner is None or spacing <= 0.0:
            continue
        left_water = next(
            (
                e.next_step
                for e in parsed.events
                if e.next_step and ("surface" in e.text.lower() or "bottom" in e.text.lower())
            ),
            None,
        )
        name = f"{path.parent.name}/{path.stem}"
        for step, row in frame.iterrows():
            index = int(str(step))
            centreline, mean = float(row["CL-Dil"]), float(row["Dilutn"])
            if index < banner or centreline <= 1.0 or not math.isfinite(centreline):
                continue
            if left_water is not None and index >= left_water:
                break
            collected.append(
                _CentrelineRow(
                    trace=name,
                    spacing=spacing,
                    angle=angle,
                    step=index,
                    diameter=float(row["P-dia"]),
                    ratio=mean / centreline,
                    on_banner=index == banner,
                )
            )
    return tuple(collected)


def _profile_slack(row: _CentrelineRow) -> float:
    """Printed-precision slack for one row's ratio, from the three numbers that enter it."""
    return 5e-4 * (1.0 + row.ratio) / max(row.ratio, 1e-9) + 0.5 * 5e-4 / row.spacing


def _fully_merged_floor_exceptions() -> float:
    """Rows at `d/L >= 2` whose centreline ratio is not the slab value 1.5000. Zero of 2 020.

    Row 199, and it is the **golden** half of row 200's analytic identity: a fully merged element
    is a slab, and the parabolic peak-to-mean for a slab is exactly 1.5. Row 198 measures the round
    value 2.0 on the unmerged rows; this measures the other endpoint.

    ⭐ **Far stronger than the claim it replaces.** The row was written from test32 settling at
    1.5000 and test19 sitting at ~1.60 partially merged -- one run each. The archive now has
    **2 020** rows at `d/L >= 2`, out to `d/L` **19.6**, and every one prints 1.5000 to the last
    digit. A floor that holds over a twentyfold range of overlap is not a fitted constant.

    ⚠️ The measurement counts exceptions rather than averaging a residual: 1.5000 is exact to
    printed precision, so a mean would report the rounding of the file and hide a genuine outlier.
    """
    deep = [row for row in _centreline_rows() if row.diameter / row.spacing >= 2.0]
    if len(deep) < 1500:
        raise AssertionError(f"only {len(deep)} deeply merged rows; the archive has shrunk")
    return float(sum(abs(row.ratio - 1.5) > _profile_slack(row) for row in deep))


def _square_diffuser_profile_ceiling() -> float:
    """Highest centreline ratio printed by a diffuser **square** to the current. 2.0000.

    Row 204's control, and half its claim. The profile law uses the **nominal** spacing while the
    merge flag fires on the **effective** one, so an oblique diffuser merges while `d < L` and the
    law -- `2.5 - 0.5 d/L` -- reads *above* 2.0. Square to the flow the two spacings coincide, the
    flag cannot fire early, and the ratio therefore never exceeds the round value.

    Measured across every square-on run in the archive it is exactly **2.0000**.

    ⚠️ **Two runs are excluded by name and the reason is the finding.** case34's `L0.3_d0.50` and
    `L0.5_d0.75` put 0.5 m and 0.75 m ports at 0.3 m and 0.5 m spacings -- more port than pipe --
    so their plumes overlap *before leaving the nozzle*, the flag fires at step 1, and they print
    2.374 and 2.423 while square to the flow. They are geometrically impossible inputs the exe
    accepts, kept on record (see case34's README), and including them here would break a rule that
    holds for every physically realisable run.
    """
    impossible = {"case34_multiport_spacing/L0.3_d0.50", "case34_multiport_spacing/L0.5_d0.75"}
    square = [
        row
        for row in _centreline_rows()
        if abs(row.angle - 90.0) < 0.5 and row.trace not in impossible
    ]
    if not square:
        raise AssertionError("no square-to-flow merged rows remain")
    return max(row.ratio for row in square)


def _oblique_profile_excess() -> float:
    """Highest centreline ratio printed by an oblique diffuser. 2.1756.

    Row 204's other half. Where the row above is capped at 2.0, obliquity lifts it: the flag fires
    on the effective spacing `L|sin psi|`, so at the banner `d` is only a fraction of the nominal
    `L`, and the law evaluated on the nominal spacing reads above the round value.

    ⚠️ **The excess is set by the geometry at the banner, not by the angle alone.** Ordered by
    obliquity from the 90 degree current the archive gives 65 deg -> 2.007, 70 -> 2.016, 45 ->
    2.045, 175 -> 2.176 -- and 65 sits *below* 70 because the two runs have different spacings
    (0.75 m against 2.0 m). What the excess tracks is `d/L` at the banner, which is what row 181's
    effective-spacing law predicts, and 175 degrees is the archive's most oblique geometry.
    """
    oblique = [row for row in _centreline_rows() if abs(row.angle - 90.0) >= 0.5]
    if not oblique:
        raise AssertionError("no oblique merged rows remain")
    return max(row.ratio for row in oblique)


def _onset_ramp_violations() -> float:
    """Ramp rows that are not a monotone climb starting at the unmerged 2.0. Zero.

    Row 206, a **recorded non-reproduction**. Crossing the banner the exe does not jump to the
    merged profile: the banner's own row still prints 2.0000, and the ratio then climbs to the law
    over 1-40 steps and never leaves it again. It is only ever present when the law *starts* above
    2.0, i.e. on an oblique diffuser -- square to the flow there is nothing to climb to.

    Three things are asserted, and any of them failing means the transient is not what we think:
    the banner row prints the round value; the ramp is monotone non-decreasing; and it ends on the
    law rather than crossing it.

    ⚠️ **The rate is still unexplained and deliberately not reproduced.** It is not constant per
    step, per unit diameter or per unit dilution. At a fixed 175 degrees the ramp lengthens sharply
    with spacing -- 7 steps at `L` = 1.0 m, 16 at 1.5, 40 at 2.0 -- and at a fixed 0.75 m spacing it
    lengthens with obliquity: 0 steps at 85 degrees, 1 at 75, 4 at 65. Same shape as row 191b's
    merging banner and row 258b's surface stop: an event the exe detects late, in a solver whose
    step controller targets 2 % mass growth per step.
    """
    from plumes2.crossplume import peak_to_mean

    rows = _centreline_rows()
    by_trace: dict[str, list[_CentrelineRow]] = {}
    for row in rows:
        by_trace.setdefault(row.trace, []).append(row)
    violations = 0
    for trace, group in by_trace.items():
        group.sort(key=lambda r: r.step)
        # ⚠️ **Scoped to output interval 1, and the scope is a finding.** At interval 5 the
        # banner row is up to five steps late, so the ramp has already started by the time
        # anything is printed and the banner row shows a merged value: case15's test15 and
        # case16's test17/test18 print 2.0400 there. All 22 interval-1 traces print 2.0000.
        # The transient is a few steps long, so it is simply not resolvable at interval 5.
        if len(group) > 1 and group[1].step - group[0].step != 1:
            continue
        # The two geometrically impossible runs overlap on the pipe, fire at step 1 and have
        # no unmerged state to ramp from -- see `_square_diffuser_profile_ceiling`.
        if trace in {
            "case34_multiport_spacing/L0.3_d0.50",
            "case34_multiport_spacing/L0.5_d0.75",
        }:
            continue
        law = [float(peak_to_mean(r.diameter, r.spacing, True)) for r in group]
        # The ramp is the prefix that sits below the law.
        length = 0
        while length < len(group) and group[length].ratio < law[length] - _profile_slack(
            group[length]
        ):
            length += 1
        if length == 0:
            continue
        if not group[0].on_banner or abs(group[0].ratio - 2.0) > _profile_slack(group[0]):
            violations += 1
        climb = [r.ratio for r in group[:length]]
        if any(b < a - _profile_slack(group[0]) for a, b in pairwise(climb)):
            violations += 1
        if law[0] <= 2.0 + _profile_slack(group[0]):
            # A ramp with nothing above 2.0 to climb to would contradict the row.
            violations += 1
    return float(violations)


def _linear_blend_vs_parabola_integral() -> float:
    """Worst gap between the exe's linear blend and the parabola's own confined integral. 0.131.

    Row 207, and it is the one place the exe's profile stops being geometry. Rows 198-200 show the
    two *endpoints* are the parabolic peak-to-mean exactly -- 2.0 for a round element, 1.5 for a
    slab -- so the obvious reading is that the exe integrates `1 - (r/b)^2` over the confined
    cross-section. It does not: it interpolates **linearly** in `d/L` between the endpoints.

    | `d/L` | linear blend | true integral | gap |
    |---|---|---|---|
    | 1.0 | 2.0000 | 2.0000 | **0.0000** |
    | 1.3 | 1.8500 | 1.8220 | +0.0280 |
    | 1.6 | 1.7000 | 1.7088 | -0.0088 |
    | 2.0 | 1.5000 | 1.6309 | **-0.1309** |

    So the endpoints are exact and the path between them is a shortcut, worst at `d/L = 2` where
    the true integral has not yet reached the slab limit. ⚠️ Marked `internal`: the linear
    law is measured against the archive by rows 203 and 221, and what this compares it to is an
    integral of our own, so there is no third party to appeal to. It is here to record that the
    agreement in rows 203/221 is with a **shortcut** rather than with the geometry -- which is why
    reproducing the exe means implementing the blend rather than the integral.
    """
    from scipy.integrate import quad

    def confined_peak_to_mean(ratio: float) -> float:
        """Peak over flux-average for a parabola on a circle clipped to `|y| <= L/2`."""
        radius = 1.0
        half = min(radius / ratio, radius)
        area = quad(lambda y: 2.0 * math.sqrt(max(radius * radius - y * y, 0.0)), -half, half)[0]
        flux = quad(
            lambda y: 2.0
            * quad(
                lambda r: 1.0 - (r * r + y * y) / (radius * radius),
                0.0,
                math.sqrt(max(radius * radius - y * y, 0.0)),
            )[0],
            -half,
            half,
        )[0]
        return area / flux

    from plumes2.crossplume import peak_to_mean

    worst = 0.0
    for tenths in range(10, 21):
        ratio = tenths / 10.0
        blend = float(peak_to_mean(2.0 * ratio, 2.0, True))
        worst = max(worst, abs(blend - confined_peak_to_mean(ratio)))
    return worst


def _held_out_profile_fits() -> float:
    """Merged rows landing on the law, as a fraction of all of them. 0.941 of 3 770.

    Row 221, and what it records is **held-out survival**. The law `max(1.5, 2.5 - 0.5 d/L)` was
    fitted on 944 rows from eight runs. Since then case24 nearly doubled the archive, case34 more
    than doubled it again, and case40 took the overlap out to `d/L` 4.27 -- **3 770** merged rows
    across a 8x range of spacing, six diffuser bearings and four port diameters -- and the law has
    not moved.

    The residual 5.9 % is **entirely** row 206's onset ramp: every miss is a prefix row starting at
    exactly 2.0000, and past first contact there are zero exceptions (row 203). So this is not
    "94 % accurate", it is "exact, with a transient at the onset we deliberately do not reproduce",
    and the two are different claims.

    ⚠️ Reported as a fraction rather than a count so it cannot silently improve by the archive
    growing. A count would rise with every new trace whether or not the law held.
    """
    from plumes2.crossplume import peak_to_mean

    rows = _centreline_rows()
    if len(rows) < 3000:
        raise AssertionError(f"only {len(rows)} merged rows; the archive has shrunk")
    fits = sum(
        abs(float(peak_to_mean(row.diameter, row.spacing, True)) - row.ratio)
        <= _profile_slack(row)
        for row in rows
    )
    return fits / len(rows)


def _merged_profile_exceptions() -> float:
    """Merged archived rows past first contact that miss `max(1.5, 2.5 - 0.5 d/L)`.

    Past first contact **and past the banner row itself**. Both exclusions are recorded findings,
    not conveniences: the banner's own row still prints the unmerged ratio because the merge takes
    effect a step late (row 206), and `d < L` at the banner is the exe using the *effective* spacing
    for the flag and the *nominal* one for the profile (row 204). test32 is the case that needs both
    -- it merges square to the flow, so its banner row lands at `d/L = 1.006`, past first contact.
    """
    from plumes2.crossplume import peak_to_mean
    from plumes2.io.dat import read_dat

    exceptions = 0
    for path in _archive_traces():
        if path.name in NON_DEFAULT_PROFILE_TRACES:
            continue  # the parabola's law; rows 278/279 cover the other profiles
        try:
            parsed = read_dat(path)
        except Exception:
            continue
        frame = parsed.nearfield
        echo = parsed.echoed_tables.get("Diffuser")
        if "CL-Dil" not in frame.columns or echo is None or echo.empty:
            continue
        if int(float(echo["Ports"].iloc[0])) <= 1:
            continue
        spacing = float(echo["Spacing"].iloc[0])
        merged_at = next(
            (e.next_step for e in parsed.events if "merg" in e.text.lower() and e.next_step),
            None,
        )
        if merged_at is None or spacing <= 0.0:
            continue
        # ⚠️ The law describes a plume still **in the water column**. Once the top breaks the free
        # surface the printed diameter stops describing a submerged element, and neither the exe
        # nor this port has a free-surface treatment -- case31's `surface_off` deliberately runs
        # on for 297 such steps and every one of its 89 misses lands there. Row 254's `Infinity`
        # and case09's NaN come from the same place. Stop at the boundary rather than scoring it.
        left_water = next(
            (
                e.next_step
                for e in parsed.events
                if e.next_step and ("surface" in e.text.lower() or "bottom" in e.text.lower())
            ),
            None,
        )
        banner_row = True
        for step, row in frame.iterrows():
            centreline, mean = float(row["CL-Dil"]), float(row["Dilutn"])
            diameter = float(row["P-dia"])
            if int(str(step)) < merged_at or centreline <= 1.0 or not math.isfinite(centreline):
                continue
            if left_water is not None and int(str(step)) >= left_water:
                break
            if banner_row:
                banner_row = False
                continue
            if diameter / spacing <= 1.0:
                continue
            predicted = float(peak_to_mean(diameter, spacing, True))
            slack = 5e-4 * (1.0 + mean / centreline) / centreline + 0.5 * 5e-4 / spacing
            exceptions += abs(predicted - mean / centreline) > slack
    return float(exceptions)


@cache
def _dosed_run():  # type: ignore[no-untyped-def]
    """case03's geometry with its effluent endmember, which the `.prj` cannot carry (§7b)."""
    from plumes2.results import run

    base = _case("reference_cases/case03_macoma_carbonate/test.prj")
    return run(
        base.model_copy(
            update={"effluent_chemistry": EffluentChemistry(total_alkalinity=4000.0, ph=10.5)}
        ),
        samples=120,
    )


TARGETS: tuple[Target, ...] = (
    # ------------------------------------------------------------------ Phase 1, legacy I/O
    Target(
        row="16",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Every archived `.prj` re-encodes byte for byte",
        source="all 9 archived projects",
        measure=_prj_round_trip_fraction,
        reference=1.0,
        tolerance=0.0,
        unit="fraction",
        note="Byte equality, so the tolerance is exactly zero. A value below 1 is the fraction "
        "that survive, which names how many fail without needing a second target.",
    ),
    Target(
        row="1",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Every archived CSV input table re-encodes byte for byte",
        source="65 tables across the archive: ambient, diffuser, effluent, MZ and chemistry",
        measure=_csv_round_trip_fraction,
        reference=1.0,
        tolerance=0.0,
        unit="fraction",
        note="The companion to row 16, and the half that is easy to forget: a project is a `.prj` "
        "plus six CSV tables, so a `.prj` that round-trips while its ambient profile does not is "
        "not a round trip. Byte equality, so the tolerance is zero. These tables carry the "
        "quoted-scientific format the exe writes, blank padding to 20 rows and all.",
    ),
    Target(
        row="49",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="A foot-flagged project rescales spacing and both mixing-zone distances by 0.3048",
        source="case00, the Dec-2025 build's legacy fps project",
        measure=_legacy_feet_rescale_error,
        reference=0.0,
        tolerance=1e-9,
        unit="m",
        note="2 ft spacing and 20.7 / 207 ft mixing-zone distances. The tolerance is float "
        "round-off because the conversion is exact by definition. ⚠️ It checks three **named** "
        "quantities rather than every length, because `port_depth` carries its own flag and stays "
        "2 m -- a blanket rescale would silently be wrong there and this would not catch it.",
    ),
    Target(
        row="74",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="A trace that goes numerically bad parses rather than crashing the reader",
        source="case09 -- a single port whose plume leaves the water column",
        measure=_case09_nan_rows,
        reference=955.0,
        tolerance=0.0,
        unit="rows with a NaN trajectory column",
        note="NaN is **data**: it records that the exe failed, so the reader keeps it rather than "
        "dropping or zeroing the rows. Exact count, hence zero tolerance. ⚠️ Counting *trajectory* "
        "columns is deliberate -- two earlier rows carry a NaN in `R_cal` alone, where the "
        "precipitation rate meets an undersaturated mineral (row 91). The chemistry goes bad at "
        "step 225 and the trajectory at 235, and conflating them would hide that.",
    ),
    Target(
        row="88",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="A header-only trace parses to an empty step table with its echoes intact",
        source="case00 -- the Dec-2025 build wrote headers and no rows",
        measure=_header_only_trace_rows,
        reference=0.0,
        tolerance=0.0,
        unit="step rows",
        note="The echoed Ambient and Diffuser tables are what made this file worth keeping -- they "
        "are what decoded the per-column foot flags (row 49) -- so the measurement raises if "
        "either echo is missing rather than silently reporting zero rows. A reader that refused "
        "the file would have cost the unit-flag finding.",
    ),
    Target(
        row="28",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="The flow unit flag changes the physics: the same 0.005 is 23x apart",
        source="case01 (m3/s) against case02 (MGD), identical in every other field",
        measure=_mgd_flow_ratio,
        reference=22.824,
        tolerance=0.001,
        unit="ratio",
        note="⚠️ The argument for refusing to parse an unknown unit flag rather than defaulting. "
        "The two projects differ in one dropdown and produce entirely different plumes from the "
        "same typed number. Reference is the exact conversion, 1 / 0.0438126, and the tolerance is "
        "what three decimals of it can resolve -- this is arithmetic, not a measurement.",
    ),
    Target(
        row="121",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="An empty `( )` unit marker in a `.dat` echo header does not shift the columns",
        source="test20's diffuser echo, whose H-angle is 70",
        measure=_echo_horizontal_angle,
        reference=70.0,
        tolerance=0.0,
        unit="degrees",
        note="A column slip is not subtle here and that is the point: the neighbours are `V-angle` "
        "45 and `Ports` 25, so a one-column error reads a plainly wrong number rather than a "
        "plausible one. Exact, hence zero tolerance. The fixed-width layout is what makes the "
        "marker harmless, and this is the trace that proves it on a real header.",
    ),
    Target(
        row="85",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="The Dec-2025 build's project is a different shape and still round-trips",
        source="case00's `Macoma.prj`, 147 lines against the 2026 build's 150",
        measure=_legacy_prj_lines,
        reference=147.0,
        tolerance=0.0,
        unit="lines",
        note="The older build writes **one** plot flag where the current one writes four, so the "
        "file is three lines shorter. Row 16 says every archived project round-trips; this says "
        "the writer is reproducing *this* shape rather than normalising it to the modern one, "
        "which a round-trip alone could not distinguish if both ends normalised the same way.",
    ),
    Target(
        row="141",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="A `.dat` diffuser echo rounds to two decimals and loses the input",
        source="test21 -- port diameter 0.0127 m and flow 0.005 m3/s, both echoed as 0.01",
        measure=_echo_rounding_loss,
        reference=0.005,
        tolerance=1e-9,
        unit="m3/s, on the worse of the two",
        note="⚠️ A trap that cost a day, pinned so it cannot be rediscovered. 0.0127 m echoes as "
        '"0.01", and 0.005 m3/s also echoes as "0.01" -- not even right to one significant '
        "figure. The reference is the flow's full loss because it is the larger. **Read inputs "
        "from the `.prj`, never from the echo**, and this is why track B writes its own CSVs.",
    ),
    Target(
        row="72",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="The shoreline vector is inert: two runs differing only in it share a near field",
        source="case05 against case08 -- a 45 deg shoreline at 5 m, and nothing else changed",
        measure=_shoreline_near_field_difference,
        reference=0.0,
        tolerance=0.0,
        unit="worst absolute column difference",
        note="Exactly zero over 84 rows and 12 columns, so the tolerance is zero -- this is byte "
        "equality expressed numerically. ⚠️ The *files* differ, because case05's far field is "
        "longer, so a byte comparison would report a difference that has nothing to do with the "
        "shoreline. ⚠️ Inert here does not prove inert everywhere: case12 ticks the checkbox as "
        "well as setting the vector, and only a run with it unticked would close that.",
    ),
    Target(
        row="113",
        phase=1,
        evidence=Evidence.MANUAL,
        claim="Every archived discharge clears the manual's Froude design check",
        source="manual §5.2.2's threshold of 1, over every archived project",
        measure=_subcritical_archived_cases,
        reference=0.0,
        tolerance=0.0,
        unit="archived cases below the threshold",
        note="⚠️ `manual` evidence: the exe prints no Froude number, so the only external thing to "
        "check against is the manual's threshold of 1 -- which is why the reference is that "
        "threshold and not a number we measured. Every project that runs is well clear; the "
        "minimum is 2.01 (case22). ⚠️ Not the check that would have caught case09, whose single "
        "port runs at 39.5 m/s and is wildly *super*critical at F ~ 1045. **case29 is the "
        "sub-critical evidence** -- see row 253.",
    ),
    Target(
        row="253",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="A sub-critical discharge returns nothing usable from the exe",
        source="case29 -- three runs at F = 0.0030-0.0037, a 0.5 m port at 0.001 m/s",
        measure=_subcritical_runs_that_survive,
        reference=0.0,
        tolerance=0.0,
        unit="runs that survive",
        note="⭐ The evidence row 113 was missing: until case29 nothing in the archive sat "
        "below "
        "the threshold at all. All three rise, cross depth zero, and return NaN from the next row "
        "to the 5001-step cap. ⚠️ The mechanism is the **missing surface clamp**, not "
        "sub-criticality as such -- case09 breaks identically from F ~ 1045 on momentum. What "
        "sub-criticality does is make the breach inevitable. So this shows the manual's warned "
        "regime yields nothing usable here, not that F < 1 causes NaN.",
    ),
    Target(
        row="86",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Unit selector 1 is the GUI's default and 2 the alternate -- which is not SI first",
        source="case00's foot-flagged project against case01/case02's flow pair",
        measure=_unit_flag_map_error,
        reference=0.0,
        tolerance=1e-7,
        unit="worst error on a conversion factor",
        note="⚠️ **Flag 1 means the dropdown's default, not SI**, and that is the trap. For a "
        "length the default is metres so 1 looks like SI; for **flow it is MGD**, with m3/s as "
        "flag 2. Reading 1 as already-SI leaves every length right and the flow 22.8x wrong "
        "(row 28). Tolerance is the precision the MGD factor is quoted to, 0.0438126.",
    ),
    Target(
        row="87",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Three tables carry a leading unit selector and three do not",
        source="case00's echoed tables, which is what exposed the offset",
        measure=_selector_alignment_failures,
        reference=0.0,
        tolerance=0.0,
        unit="table kinds mapping a column to the wrong selector",
        note="Effluent, mixing-zone and ambient are offset by one; the diffuser is 1:1, and so "
        "are the ambient DO and chemistry tables, which carry no selector row at all. ⚠️ The "
        "ledger said `diffuser 1:1; others offset by one` until 2026-08-18, which is wrong for "
        "those last two -- making the row executable is what surfaced it. An offset error reads a "
        "neighbouring column's unit, so it rescales silently rather than failing.",
    ),
    Target(
        row="143",
        phase=1,
        evidence=Evidence.INTERNAL,
        claim="The three alternate unit dropdowns convert correctly, degF affinely",
        source="internal -- **no reference**: no archived project selects any of them",
        measure=_alternate_unit_error,
        reference=0.0,
        tolerance=1e-9,
        unit="worst absolute error",
        note="degF, kg/kg and per-second decay are options the GUI offers and the archive never "
        "exercises, so there is **no reference** to check them against and they are checked "
        "against arithmetic instead -- `internal`, and weaker for it. ⚠️ degF is the only "
        "**affine** unit in the project: 50 degF is 10 degC, not "
        "27.8, so a codebase that assumes `value * factor` everywhere gets it wrong by the offset "
        "and still returns a plausible temperature.",
    ),
    Target(
        row="161",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="The two builds label selector 1 differently, and the gap is a factor of a million",
        source="case00 (Dec-2025, `kg/kg`) against test21 (2026, `mg/L`)",
        measure=_pollutant_label_risk,
        reference=1.024e6,
        tolerance=1e3,
        unit="ratio between the two readings",
        note="⚠️⚠️ **The largest silent misread available in this format.** The same file, the "
        "same selector 1, and two builds that disagree about whether it means a concentration or a "
        "mass fraction -- which differ by the density in mg/L. Both readings return a number and "
        "only one is a concentration, so nothing fails. Tolerance is the spread across plausible "
        "seawater densities, since the ratio *is* the density. Round-trip fidelity is unaffected: "
        "this bites only when a value is interpreted.",
    ),
    # ------------------------------------------------------------------ Phase 2, seawater
    Target(
        row="99",
        phase=2,
        evidence=Evidence.EXTERNAL,
        claim="EOS-80 density against all eight UNESCO check values",
        source="UNESCO (1983) Table A3.1 -- S 0 and 35, T 5 and 25, 0 and 1000 bar",
        measure=_eos_density_error,
        reference=0.0,
        tolerance=1e-5,
        unit="worst absolute error, kg/m3",
        note="A check on the equation of state itself, independent of any plume, and the thing "
        "that settles EOS-80 against the Fofonoff (1985) alternative rows 15 and 159 consider. "
        "Tolerance is the precision UNESCO publishes to. ⚠️ This target checked **one** of the "
        "eight until 2026-08-18 while the row claimed all eight -- the other seven were asserted "
        "in a test and missing from the report that is meant to be the evidence.",
    ),
    Target(
        row="101",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="Our EOS-80 plume density runs low against the exe's own column, by a bounded amount",
        source="case01's 84 printed rows, mixed from the exe's dilution and depth",
        measure=_exe_density_offset,
        reference=0.0,
        tolerance=0.05,
        unit="mean signed error, kg/m3",
        note="⚠️ **A recorded disagreement.** We sit a mean **-0.036 kg/m3** below the exe -- "
        "small but systematic, not noise, and the cause is known: UM uses the Teeter & Baumgartner "
        "(1979) sigma-t rather than EOS-80 (row 159). We keep EOS-80, which matches the UNESCO "
        "check values to 5e-6, rather than tuning a standard to fit. It matters where buoyancy is "
        "the *difference* of two densities, so late-trajectory drift tracks it (row 148).",
    ),
    Target(
        row="102",
        phase=2,
        evidence=Evidence.INTERNAL,
        claim="Ambient extrapolation is clamped at both ends, never extended",
        source="internal -- a design decision with **no reference** to check against",
        measure=_extrapolation_clamp_error,
        reference=0.0,
        tolerance=0.0,
        unit="drift past the profile's end",
        note="Every Macoma project's seabed sits below its ambient profile, so querying past the "
        "end is routine rather than exceptional. Extending a steep salinity gradient instead of "
        "clamping it produces negative salinity, and extrapolating past the *shallow* end is what "
        "broke case09's transport. `internal` because there is **no reference** for this: the exe "
        "never prints the ambient it used, so its own policy at the profile edge is unobservable.",
    ),
    Target(
        row="100",
        phase=2,
        evidence=Evidence.EXTERNAL,
        claim="The EOS-80 secant bulk modulus against all five UNESCO check values",
        source="UNESCO (1983) Table A3.1, the pressure half of the equation of state",
        measure=_bulk_modulus_error,
        reference=0.0,
        tolerance=1e-4,
        unit="worst absolute error, bar",
        note="Barely matters here -- every reference case is shallower than 20 m and the exe "
        "reports sigma-t, so the pressure term is near-inert. That is the argument *for* checking "
        "it against published values: a wrong bulk modulus would be invisible at these depths and "
        "wrong everywhere else. Tolerance is again UNESCO's published precision.",
    ),
    Target(
        row="108",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="The sigma-t offset against the exe is flat at -0.0275 in the seawater range",
        source="28 traces printing `P-Sal` and `P-Temp`, plume salinity above 28 psu",
        measure=_eos_offset,
        reference=-0.0275,
        tolerance=0.001,
        unit="kg/m3",
        note="⭐ The clean measurement of the offset: fed the exe's **own** printed salinity and "
        "temperature, it isolates the equation of state from the mixing and the trajectory. Row "
        "101 "
        "reconstructs S and T from dilution and gets -0.036, so the 0.009 between them is "
        "everything that is not the EOS. Tolerance is the printed precision of `P-Den`. ⚠️ Scoped "
        "to seawater: below 28 psu the offset grows -- see row 255.",
    ),
    Target(
        row="262",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="The exe's equation of state is Knudsen (1901), to one printed digit",
        source="every distinct archived trace printing P-Sal, P-Temp, P-Den -- 51 670 rows, 107",
        measure=_knudsen_worst_density_error,
        reference=0.0,
        tolerance=0.001,
        unit="worst |P-Den - ours|, kg/m3",
        note="⭐⭐⭐ **An identification with zero fitted parameters**, which is why the tolerance "
        "is the column's own printed resolution rather than a band around a measurement. Over "
        "S 0-45 psu and T 2.73-11.01 C the worst disagreement is **0.00098 kg/m3** -- one digit "
        "of three decimals. The controls are the point: EOS-80 gives 0.0629 on the same rows, "
        "Eckart (1958) 0.2098, and a seven-parameter fit to EOS-80 only reaches 0.0168, while "
        "fitting a constant or a quadratic *on top of* Knudsen changes nothing. It confirms the "
        "H.O. 615 citation chain from the far end (see `references/README.md`), explains row "
        "255's salinity dependence, and ⚠️⚠️ **refutes row 148** -- switching to it moves "
        "test23's late-window MARE 5.07 % to 5.01 %, so the late drift is not the EOS.",
    ),
    Target(
        row="147",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="That offset reproduces across cases, builds and geometries",
        source="the spread between those same 28 traces",
        measure=_eos_offset_spread,
        reference=0.0,
        tolerance=0.003,
        unit="kg/m3 between the extremes",
        note="The row claimed this on **two** cases; measured over 28 it holds to 0.0019 kg/m3, "
        "which is under two units in `P-Den`'s last printed digit. Those 28 span both exe builds, "
        "five diffuser bearings, three spacings and depths from 1 to 9 m -- so whatever the exe's "
        "polynomial is, it is the same one throughout and the difference from EOS-80 is a property "
        "of the two formulas rather than of any run.",
    ),
    Target(
        row="255",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="The offset is salinity-dependent, not a constant bias",
        source="45 traces, plume salinity 24.5 to 33.1 psu",
        measure=_eos_offset_salinity_correlation,
        reference=1.0,
        tolerance=0.03,
        unit="correlation with mean plume salinity",
        note="⚠️⚠️ **The offset is not a constant bias.** Over 45 traces it runs from **-0.0400** "
        "at a 24.5 psu plume to **-0.0263** above 32 -- five times what three printed "
        "decimals resolve, so it is a *different polynomial* rather than a fixed error, and "
        "the two agree only where seawater lives. ⚠️ **The tolerance moved 0.01 -> 0.03 on "
        "2026-08-19, because a Pearson `r` pinned near 1 asserts linearity and the relation "
        "is not linear**: it flattens above about 31 psu, which is the same plateau row 147 "
        "uses to define its flat band. `r` fell to 0.9887 when case33 and case34 added traces "
        "on that plateau. The claim is a strong monotone dependence, and that is what the "
        "widened band asserts. Matters for a **fresh** discharge, which is Ebb's case.",
    ),
    Target(
        row="148",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="By trapping there is less buoyancy left than the offset itself",
        source="test23's last row, ambient minus plume density",
        measure=_buoyancy_left_at_trapping,
        reference=0.0097,
        tolerance=0.002,
        unit="kg/m3",
note="⭐ Why an EOS offset matters at all: it is 0.9 % of the buoyancy at the port "
        "and **~280 %** of what survives at trapping, because buoyancy is a *difference* of two "
        "densities and collapses toward zero. The amplification is real and this measures it. "
        "⚠️⚠️ **What it does not do is explain the late drift, and that reading is retracted.** "
        "With the exe's own EOS identified (row 262) and selected, test23's late-window MARE moves "
        "**5.07 % to 5.01 %** and three of the four cross-flow runs get slightly worse -- so the "
        "drift survives removing the offset entirely. It is localised instead to a post-trapping "
        "entrainment suppression the exe applies and this port lacks: its specific rate falls "
        "**57x** through trapping against our 9x, on the zero-current run only, with the two "
        "speeds agreeing to 6 %. A mechanism that matched a ratio, refuted once it could be "
        "switched off.",
    ),
    Target(
        row="227",
        phase=2,
        evidence=Evidence.MANUAL,
        claim="The two reduced-gravity references differ by rho_p/rho_a, and the manual picks one",
        source="3rd edition p. 124, which writes the momentum term as `((rho_a - rho)/rho) g`",
        measure=_reduced_gravity_reference_gap,
        reference=0.00308,
        tolerance=0.0005,
        unit="fractional difference",
        note="⭐ The reference settles it: p. 124 divides by the **plume** density, which is what "
        "`nearfield/solver` does. `seawater.reduced_gravity` is the ambient-referenced "
        "Froude/Richardson convention and is documented as not for the momentum equation -- this "
        "measures what reaching for the wrong one costs: 0.31 %, systematic rather than noise. ⚠️ "
        "It was a trap rather than a bug: nothing in `src` called it until the Froude check did.",
    ),
    Target(
        row="159",
        phase=2,
        evidence=Evidence.GOLDEN,
        claim="The exe's density is pressure-independent: same S and T at depth, same value",
        source="every archived row pair sharing an exact printed `(S, T)` across 0.89 m of depth",
        measure=_density_depth_dependence,
        reference=0.0,
        tolerance=0.0011,
        unit="kg/m3 spread in `P-Den`",
        note="⭐ Tests the reference's claim **without the polynomial**. The 3rd edition (p. 124) "
        "says UM's density comes from Teeter & Baumgartner's (1979) `Sigmat`, \"independent of "
        'pressure, limiting UM to shallow water" -- and neither manual prints it. This checks the '
        "consequence instead: an EOS-80 pressure term over the same 0.89 m moves density by "
        "**0.0041**, four times what three decimals resolve, and the exe prints the same value. "
        "⚠️ Bounds the term at 4x the printed resolution, not to zero; the archive spans only "
        "1-9 m and the plume never revisits an (S, T) across more of it.",
    ),
    # ------------------------------------------------------------------ Phase 3, Brooks
    Target(
        row="119",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Brooks dilution against the exe's own independent far-field calculator, 28 rows",
        source="case17, the manual's worked example run through the exe",
        measure=_standalone_farfield_gap,
        reference=0.0,
        tolerance=1e-3,
        unit="dilution",
        note="⭐ The strongest target here. The initial width and dilution are typed in, so no "
        "near-field is involved -- it confirms beta, eps_0 = alpha w0^(4/3), the erf forms, the "
        "total dilution and the travel time, and localises the integrated runs' shortfall entirely "
        "to the near-to-far-field handoff.",
    ),
    Target(
        row="30",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Wastefield width = (n-1)*spacing + diameter at 90 degrees",
        source="case02, printed as 48.56",
        measure=lambda: float(
            _case("reference_cases/case01_macoma_cms/Macoma2.prj").wastefield_width(0.558)
        ),
        reference=48.558,
        tolerance=5e-3,
        unit="m",
        note="The exe prints two decimals, so 48.56 pins this to +/-0.005.",
    ),
    Target(
        row="275",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="On one build the span factor is flat across bearing -- there is no cosine",
        source="case45's eight bearings from 0 to 45 deg on one geometry and one exe",
        measure=_width_factor_spread_across_bearings,
        reference=0.0140,
        tolerance=0.006,
        unit="spread in the implied span factor across 0-45 deg",
        note="⛔⛔ **This row read \"the width cosine has a threshold between 25 and "
        "30 deg\" until 2026-08-21, and the threshold does not exist.** It compared an implied "
        "span factor of 0.990 at 25 deg against 0.879 at 30 and concluded the cosine switches on "
        "in between -- but the 25 deg traces were all from case42-44, one exe session, and the "
        "30 deg traces mostly from case13/case14 on a different one. case45 sweeps **one** "
        "geometry on **one** exe and the factor is flat: 1.0000 / 0.9982 / 0.9964 / 0.9959 / "
        "0.9953 / 0.9947 / **0.9940** / **0.9860** at 0 / 15 / 22 / 24 / 26 / 28 / 30 / 45 deg, "
        "against a cosine that would fall to 0.866 and 0.707. Spread **0.0140** over the whole "
        "range. ⭐⭐⭐ **It is the exe *build*, not the angle**, and case13 shows "
        "it at a single angle and geometry: its deliberate paired-build run prints 109.590 m "
        "(factor 0.9943) from one build and 96.290 m (factor **0.8660** = `cos 30` exactly) from "
        "the other. That is rows 263/263b and `ExeBuild.CURRENT`/`LEGACY`, already modelled -- so "
        "row 96's 10.73 m failure was a **build misclassification**, and reclassifying case42-45 "
        "put row 96 back to **0.005 m** across the whole archive. ⭐ **The span-doubling arm "
        "settles it without any assumption**: `(242.070 - 122.590) / 120` = **0.9957**, the "
        "diameter cancelling exactly. ⚠ The residual drift 1.0000 to 0.9860 is not an angle "
        "law either -- it is the diameter-selection effect row 96 flags at section 7 item 22. "
        "⚠ **And the alternate theory that this was rounding was tested and excluded by four "
        "orders of magnitude**: over a 120 m span, three printed decimals are worth "
        "+/-0.000004 in the factor against a 0.0894 gap, and for `cos 25` to hold on test70 that "
        "plume would have to be 13.8 m against an actual 3.1.",
    ),
    Target(
        row="96",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The wastefield width law, including its cosine, over every current-build trace",
        source="43 traces -- eight bearings, four spacings, single and multiport",
        measure=_wastefield_width_error,
        reference=0.0,
        tolerance=0.005,
        unit="worst absolute error, m",
        note="⭐ `(n-1) * spacing * |cos(bearing - current)| + diameter`, folding seven ledger "
        "rows into one measurement: 30, 53, 64, 70, 80, 91 and 103 were each this law confirmed on "
        "another case. Tolerance is the two printed decimals. ⚠️ Computed **from the trace alone** "
        "-- the diffuser and ambient echoes plus the final diameter -- so it needs no `.prj` and "
        "covers three times as many traces as the projects would allow. ⚠️ Old-build traces are "
        "excluded and measured separately; see row 98.",
    ),
    Target(
        row="98",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The shipped example's wastefield width is old-build and 13 m wider",
        source="upstream/Example_project, printed 109.59 against the current law's 96.29",
        measure=_old_build_width_gap,
        reference=13.302,
        tolerance=0.01,
        unit="m",
        note="⚠️ **Why the shipped example cannot be a target for anything downstream of the "
        "width.** The cosine correction was added between releases, so the example prints 109.59 "
        "where the current build gives 96.29 for the same geometry -- a 30 degree bearing offset "
        "that the old build essentially ignored. Rows 6-8 were retired for exactly this reason. "
        "The reference is the measured gap because the *claim here is the discrepancy*, not "
        "agreement, and the tolerance is what two printed decimals can resolve either side of it.",
    ),
    Target(
        row="115",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Inverting the width law recovers the distance axis with slope 1",
        source="the eight archived far fields, regressed against their own `Distance` column",
        measure=_width_law_inversion_error,
        reference=0.0,
        tolerance=0.001,
        unit="worst |slope - 1|",
        note="⭐ This settles the **conventions**, not the law: a slope of 1 comes out only "
        "if `w0` is the far field's own first width and `x` is measured from that row. Any other "
        "origin or initial width still fits a straight line, just with the wrong slope -- so the "
        "regression discriminates where a residual would not. Tolerance is a tenth of a percent, "
        "which is well inside what the printed columns can support.",
    ),
    Target(
        row="277",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Every archived far-field stop matches a known session-state rule",
        source="the de-duplicated archive -- 134 far-field tables across 185 distinct traces",
        measure=_farfield_unclassified_stops,
        reference=0.0,
        tolerance=0.0,
        unit="traces whose stop matches no rule",
        note="⭐ The exe's far-field stop dialog takes a calculation **distance** and a "
        "**dilution** together, stops at whichever binds first, and stores neither -- "
        "operator-confirmed 2026-08-24, usual entries 500 m / 10000x. Census as of that date: "
        "**95** stopped at a typed 500 m, **12** at the exe's own default (the chronic-MZ "
        "boundary, echoed in the trace's diffuser table -- the runs where no distance was "
        "typed), **5** on a 10000x dilution stop (case11, case43), **3** on a 5000x one "
        "(case03 kso4_option3, case30 d0.28, case39 spacing1000), and case09's 2 NaN. "
        "Re-counted 2026-08-26 after case47, case49 and case46's prj-pair traces graduated: "
        "**105** / **13** / **5** / **7** / 2 over 132 tables (case50's two typed-500 m runs "
        "make it 107 over 134) -- case47's four dose runs declared "
        "10000x and stopped at 5000x, the session drift "
        "`check_farfield_session_state` exists to catch; the target is unmoved because 5000x is a "
        "known rule. "
        "⚠️ **A dilution stop is claimed only when the crossing sits in the final six rows** "
        "(the measured stopping lag is 1-4 rows; test72/73 are the worst) "
        "-- 33 traces cross 5000x and run on to 500 m regardless, because their session's stop "
        "was 10000x, and a naive threshold check misfiles every one of them (it did, in this "
        "row's first draft). ⚠️ The prose census this replaces was wrong twice in one day: "
        "file counts instead of de-duplicated traces, and a claimed 5000x-vs-10000x split by "
        "*build* that was actually the operator's entry varying by *session*. Zero tolerance "
        "because one unknown stop is one rule this census does not know -- the same standard "
        "as row 79's termination banners.",
    ),
    Target(
        row="280",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The exe's `Constant` and `Linearly varying` far-field laws are the port's, and the "
        "`.prj` selector is decoded",
        source="case50: Ebb's default project under each non-default law, every far-field row "
        "to 500 m",
        measure=_eddy_law_selector_error,
        reference=0.0,
        tolerance=3e-4,
        unit="relative, worst row (dilution both laws; width, constant law)",
        note="\u2b50\u2b50 The first traces in the archive under any law but the 4/3 default. "
        "Far-field flags 2/3/4 are the selector, one-hot -- `1,1,0,0,1,1,0` Constant, "
        "`1,0,1,0,1,1,0` Linear, the archive's `1,0,0,1,1,1,0` 4/3 -- and the header prints "
        "`Constant Eddy Diffusivity is used:` / `Linearly Varying Eddy Diffusivity is used:` "
        "(only the 4/3 form carries `based`, which the reader had required; fixed the same day). "
        "The near field is bit-identical to case03's `kso4_option3.dat` on all 410 rows, so the "
        "law is the only thing that moved. On the trace's own first row (`D0` 562.633, `w0` "
        "48.572) the port reproduces `Dilution` to 1.3e-4 (constant) and 2.2e-4 (linear) and the "
        "constant `Width` to 1.7e-4 -- the same order as the 4/3 law's row 116. Tolerance 3e-4: "
        "the printed columns resolve ~1e-6, so this is the port's own Brooks arithmetic, not the "
        "print. The linear *width* is row 280b, kept apart because it carried a defect.",
    ),
    Target(
        row="280b",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The exe's linear-law width is `w0 (1 + beta x / w0)`; the manual's eq 11 has a "
        "stray factor of two, which the port had copied",
        source="case50 `eddy_law_linear.dat`, every far-field row to 500 m",
        measure=_linear_width_error,
        reference=0.0,
        tolerance=3e-4,
        unit="relative, worst row",
        note="\u26a0\ufe0f\u26a0\ufe0f **A port defect found by the first linear-law trace.** "
        "`farfield.brooks.width` implemented the manual's `1 + 2 beta x / w0` and was 57-87 % "
        "high against the exe's 112.339 / 178.008 / 375.015 m at 100 / 200 / 500 m; the exe's "
        "`1 + beta x / w0` reproduces the column to 1.7e-4. The derivation sides with the exe -- "
        "`eps = eps_0 w / w_0` with `w = sqrt(12) sigma` gives `d(w^2)/dt = 24 eps`, which "
        "integrates to `w = w_0 + 12 eps_0 x / (u w_0)` -- and eq 15's erf argument "
        "`(1 + beta x / w0)^2 - 1` already carried the right factor, which is why the linear "
        "*dilution* matched (row 280) while the width did not. The manual's form is asserted to "
        "stay > 50 % high inside the measurement, so restoring it fails this row outright. No "
        "archived trace used the linear law before 2026-08-26, so nothing else moves. SSMC "
        "Tier 3 item 19.",
    ),
    Target(
        row="29",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The far field starts at the straight-line distance from the diffuser",
        source="eight traces, first far-field `Distance` against `hypot(x, y)` at the handoff",
        measure=_farfield_start_distance_error,
        reference=0.0,
        tolerance=0.0011,
        unit="m",
        note="Not the path length: a plume carried sideways by the current starts its far field "
        "closer to the origin than the distance it has travelled. Exact on all eight traces, so "
        "the tolerance is the three decimals both columns print. It matters because every Brooks "
        "quantity is a function of `x` from this origin -- get it wrong and the width law still "
        "fits, with a displaced axis (row 115).",
    ),
    Target(
        row="120",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The independent calculator's output grid: 28 rows, 8.001 to 224.000 m",
        source="case17, whose 200 m mixing zone was entered from 0.001 m",
        measure=_standalone_grid_error,
        reference=0.0,
        tolerance=0.0011,
        unit="worst distance error, m",
        note="⭐ Folds rows 112, 117 and 120: the grid is **25 steps to the mixing zone plus 3 "
        "beyond**, fixed rather than user-controllable, and the **origin row is not printed**. All "
        "three are properties of this one array. ⚠️ The origin convention is the part worth "
        "pinning -- printing the origin would give 29 rows from 0.001, shifting every row by a "
        "step while still looking like a sensible grid. Tolerance is the three printed decimals.",
    ),
    Target(
        row="56",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Far-field chemistry asymptotes to the ambient at the true trapping depth",
        source="case05, whose far-field TA settles at 2925.268 umol/kg",
        measure=_farfield_asymptote_depth_excursion,
        reference=0.0,
        tolerance=0.0,
        unit="m outside the last printed step",
        note="⭐ Resolves what reads as a discrepancy. The ambient puts 2925.268 at **1.747 m**, "
        "not the **1.710 m** the near field's last row prints -- which would give 2929.0. They do "
        "not disagree: this trace has an output interval of 5, so the true termination lies "
        "*between* printed rows, and 1.747 sits inside the last printed interval. The asymptote is "
        "the ambient at the trapping depth, the same rule the DO module found for eq 30 (row 246) "
        "-- and it is the **printed depth that is approximate, not the model**. Tolerance is zero "
        "because the implied depth either falls in the bracket or it does not.",
    ),
    Target(
        row="256",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The far-field dilution is Brooks from a virtual origin, not from the handoff width",
        source="all eight archived far fields",
        measure=_virtual_origin_dilution_error,
        reference=0.0,
        tolerance=0.002,
        unit="worst mean relative error",
        note="⭐⭐ **This is what row 116's 11 % shortfall was.** The exe runs Brooks from the "
        "**echoed geometric width**, starting at the upstream distance where that solution has "
        "grown to the handoff width -- 1 to 5 m here -- and reports both columns from there. It "
        "takes the worst trace from **11.16 % to 0.096 %**, and every trace under 0.1 %. Two "
        "things fall out: the width matched either way by construction (row 114), and the "
        "standalone calculator matched exactly (row 119) because there the width is typed in, so "
        "there is no adjustment and no origin to find.",
    ),
    Target(
        row="257",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The exe starts its far field from a width up to 1.13x the geometric one",
        source="eight traces, the echoed wastefield width against the far field's first row",
        measure=_handoff_width_adjustment,
        reference=1.1255,
        tolerance=0.001,
        unit="largest ratio",
        note="⚠️ **The last undecoded piece of the far field, and what blocks row 256 from being "
        "implemented.** Row 96 reproduces the *echoed* geometric width exactly on 43 traces; the "
        "exe then starts Brooks from a larger one. The manual calls it the transition stage, where "
        'parameters are "revised/adjusted to match the wastefield dimensions", without saying '
        "how. Not a constant, not a fixed multiple of the final diameter (the implied factor runs "
        "1.03-2.28), and it does not track merging, spacing or dilution. The reference is case06's "
        "ratio, the largest in the archive.",
    ),
    Target(
        row="258",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The far-field dilution error is mostly the near-field endpoint, not Brooks",
        source="case13, our near-field end dilution against the exe's far-field first row",
        measure=_nearfield_endpoint_ratio,
        reference=1.349,
        tolerance=0.05,
        unit="ratio, ours over theirs",
        note="⭐ **Redirects the effort.** Our case13 ends at 237.7 where the exe ends at 169.8, "
        "because we integrate further -- transition 10.96 m against 7.32 -- before termination "
        "fires. The 38.9 % far-field dilution error inherits that. So the far field is a **phase 5 "
        "problem wearing a phase 3 coat**: Brooks is exact (row 119), the handoff form is "
        "understood (row 256), and what is left is where the near field stops. ⚠️ A termination "
        "difference, not a closure error -- the jet phase still clears 0.5 % (rows 145, 171).",
    ),
    # ------------------------------------------------------------------ Phase 4, chemistry
    Target(
        row="214",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Entrained ambient oxygen is path-integrated, not evaluated at the final depth",
        source="case24's four DO traces, past D > 5",
        measure=_oxygen_path_integral_error,
        reference=0.0,
        tolerance=12.0,
        unit="multiples of the printed digit",
        note="\u2b50\u2b50 **The rule the whole DO module rests on**, and the one rows 109 and "
        "222 later confirmed on salinity and on a uniform ambient. `d(DO*D)/dD = DO_a(z)` lands "
        "within **9.6x** what three decimals resolve. Reported in printed digits rather than mg/L "
        "because that is the scale on which a difference is visible at all. \u2b50 The 3rd "
        "edition states it in words (pp. 12-13): a plume rising from an anoxic basin ends *very "
        "nearly the same as the deep water*. \u26a0\ufe0f Seeded with `DO_e - IDOD` exactly, "
        "crediting none of the 2 % already entrained by the first printed row -- row 220's "
        "one-step lag, which makes the fit **worse** if corrected for.",
    ),
    Target(
        row="214b",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The manual's algebraic eq 23 is decisively worse for oxygen",
        source="the same four traces, algebraic residual over path-integral residual",
        measure=_oxygen_algebraic_penalty,
        reference=35.0,
        tolerance=12.0,
        unit="ratio",
        note="The control that makes the row above mean something: without it, 10 printed digits "
        "could be two forms that barely differ. Eq 23 as the manual writes it misses by **435x** "
        "the printed digit where the path integral misses by under 10 -- not a refinement but a "
        "different rule. \u26a0\ufe0f Measured **per trace**, at its weakest -- 35x on "
        "test39/40 against 62x on test37/38 -- because dividing one trace's algebraic error by "
        "another's path error is a number about neither. Same correction row 109b needed. Wide "
        "tolerance because the claim is the order of magnitude, not the ratio.",
    ),
    Target(
        row="104",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="`stop_at_surface` changes where the trace ends and nothing else",
        source="two pairs on two exe builds -- case13/14 and case31",
        measure=_surface_stop_trajectory_gap,
        reference=0.0,
        tolerance=0.0,
        unit="worst difference over the shared steps",
        note="\u2b50 Over their shared steps the two runs of each pair agree **exactly** -- 55 "
        "for case13/14, 275 for case31 -- and then one stops at 275 while the other carries on to "
        "476 and 572. \u26a0\ufe0f That is what licenses treating the switch as a **termination "
        "rule** rather than a physics option: nothing upstream of the surface depends on it, so a "
        "run made with it off is still comparable with one made with it on. Row 258 is the case "
        "in point -- our 40 % endpoint gap on case13 was this flag mismatched, and the trajectory "
        "underneath agreed to 1.9 %. \u26a0\ufe0f It is **session state**: case13 and case14 "
        "have byte-identical `.prj` files and stop differently.",
    ),
    Target(
        row="191o",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="On a single port the entered spacing is inert; the rule fires regardless",
        source="case39's spacing 5 and 1000 m against case30's spacing-0 control",
        measure=_single_port_spacing_inertness,
        reference=0.0,
        tolerance=0.0,
        unit="worst numeric difference",
        note="\u2b50\u2b50\u2b50 A geometry that reaches **4.293 m** against a 2.4 m port depth, "
        "so well past the trigger, gives the *same trace* at an entered spacing of 0.00, 5.00 and "
        "1000.00 m -- crossing at 191, banner at 192, final dilution 65.213, all three. "
        "\u26a0\u26a0 Which makes the 3rd edition's own point-source recipe fail (p.61: set the "
        'spacing to 1000 m so "merging will not occur"): the plume merges with **itself** '
        "anyway, and the user gets an entrainment suppression worth 2.3x to 6x that they cannot "
        "switch off and are not told about. That is row 191p, and it is on the SSMC list. "
        "\u26a0\ufe0f Compared on the **numbers**, not the bytes -- the echo prints the spacing, "
        "so the files must differ. Same pattern as row 191l.",
    ),
    Target(
        row="51",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Merging is declared when the plume diameter reaches the port spacing",
        source="the five Macoma traces that merge square to the current",
        measure=_merge_trigger_crossing,
        reference=0.0,
        tolerance=0.05,
        unit="worst |d/L - 1| at the banner",
        note="\u2b50 The trigger itself, measured as a **crossing**: every trace sits below 1 on "
        "the row before the banner and at or above it on the banner, and the measurement asserts "
        "that rather than just reading the banner row. \u26a0\ufe0f **Scoped to diffusers square "
        "to the current, and the scope is the finding.** Archive-wide `d/L` at the banner runs "
        "**0.118 to 1.045**, which looks like no rule until you see that every low reading is an "
        "oblique diffuser: the exe triggers on the *effective* spacing `L |cos psi|` (row 181). "
        "Including them would measure the cosine correction and the trigger together and settle "
        "neither. \u26a0\ufe0f The 0.045 is the **output interval** -- these print every fifth "
        "step, so the crossing falls between rows; case20's test32 at interval 1 brackets it to "
        "0.9990-1.0060. Folds row 69.",
    ),
    Target(
        row="97",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe's run of **our** generated project matches its run of the shipped one",
        source="case13 against upstream's Example_project, 5 columns x 55 steps",
        measure=_generated_project_fidelity,
        reference=0.0,
        tolerance=0.0,
        unit="worst difference",
        note="\u2b50\u2b50 **Phase 1's acceptance test, and stronger than a round trip.** "
        "`PythonGenerated.prj` was written from the upstream example **with no template** -- every "
        "value went out through the semantic model and back -- and the exe's run of it matches "
        "to its run of the project it ships with. \u26a0\ufe0f Row 18 shows we can re-render a "
        "file we parsed; this shows the **exe agrees** our reconstruction of a case is the same "
        "case, reader and model and writer together, judged by the program being ported. Zero "
        "tolerance because two runs of one case have no resolution to spend.",
    ),
    Target(
        row="24",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case02 dilution over the whole trace, at the exe's own printed times",
        source="case02's 41 rows, solved against case03's project",
        measure=_case02_dilution_mare,
        reference=0.0,
        tolerance=0.01,
        unit="MARE",
        note="\u26a0\ufe0f **This corrects the row**, which claims <= 0.5 %. Measured whole-trace "
        "it is **0.86 %**, and in the same way row 17's 0.74 % was: the error concentrates after "
        "the first trapping rather than spreading evenly, so a whole-trace mean is not what "
        "the 0.5 % bar was ever met on. The jet phase does clear it: row 21 gets 0.46 % on "
        "case01. \u2b50 Solved against **case03's** project, which case02 has none of its own to "
        "use: safe because the two are bit-identical over every shared hydrodynamic column, so one "
        "project describes case02, case03 and case04 and this covers all three.",
    ),
    Target(
        row="36",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Our saturation states against case03's far-field table, on the exe's own TA and DIC",
        source="case03's 23 far-field rows",
        measure=_far_field_chemistry_gap,
        reference=0.0,
        tolerance=0.03,
        unit="worst relative gap in Omega",
        note="\u2b50 **The last parity block.** The far-field table prints TA, DIC, pH and both "
        "`Omega` columns, so the near field's isolation applies here too -- fed the exe's own TA "
        "and DIC this measures the carbonate solver, not the Brooks spreading. \u2b50 It agrees "
        "**better** than the near field, 0.0064 pH and **2.2 %** on `Omega` against 0.024 and "
        "3.5 %, and in the expected direction: by the far field the plume is within 0.007 psu of "
        "ambient, nowhere near the pH 10 region where the exe's CO2SYS and PyCO2SYS diverge most. "
        "\u26a0\ufe0f Salinity and temperature are **not printed** in the far field and are "
        "reconstructed -- the plume travels at its trapping depth, so both mix from the near-field "
        "endpoint toward the ambient there as `FF` grows. That reconstruction is why the bar is "
        "looser than row 43's. Uses Lee borate, per row 128.",
    ),
    Target(
        row="39",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="One conservative endmember pair fits every printed row of a chemistry trace",
        source="every chemistry trace but the two named exceptions",
        measure=_endmember_fit_residual,
        reference=0.0,
        tolerance=30.0,
        unit="umol/kg",
        note="\u2b50 The fit recovers the **entered inputs without being told them**: ambient "
        "endmembers land on 2900.5 / 2499.9 / 1799.0 / 1600.0 / 3000.0 / 2700.0, the chemistry "
        "tables, and case03's effluent on **4110.2** where row 46's scaling predicts 4107.8 -- "
        "confirming that rule from a direction it was never fitted to. case03/04 sit at 1.49 "
        "umol/kg; the bar is set by case05/08/12 at 23. \u26a0\ufe0f **The weighting is the "
        "measurement**: fitting on `v*D` rather than `v` lets the high-dilution rows dominate and "
        "returns an effluent of 7407 for a 4000 input, which was my first attempt. \u26a0\ufe0f "
        "Two traces excluded by name -- case09 (`Omega < 1` NaN, row 73) and case06, which misses "
        "by 149 and is **unexplained**: a rate-versus-residual correlation over the archive is "
        "-0.22, so precipitation does not account for it.",
    ),
    Target(
        row="128",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The exe's borate behaves like Lee 2010, not the Uppstrom its option selects",
        source="case03's pH column, 41 rows, on the exe's own TA and DIC",
        measure=_borate_spread_under_lee,
        reference=0.0,
        tolerance=0.004,
        unit="pH units of spread",
        note="\u26a0\ufe0f **The spread, not the mean** -- and that choice is the finding. A "
        "constant offset is the CO2SYS divergence rows 35 and 43 already measure; a *wrong borate* "
        "makes the gap **vary** along the trace with salinity and alkalinity. Uppstrom 1974, which "
        "KSO4 = 1 nominally selects, gives a spread of **0.01289**; Lee 2010 gives **0.00183**, "
        "seven times tighter, and cuts the worst gap from 0.02356 to 0.00646. The measurement "
        "refuses to pass unless Uppstrom is at least 5x looser. \u2b50 It halves the unexplained "
        "part of the pH residual, which is the practical payoff.",
    ),
    Target(
        row="238",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The ambient BOD is converted to ultimate at the effluent's carbonaceous rate",
        source="case25 run 3, the only ambient-BOD run at a slow enough rate to tell",
        measure=_ambient_bod_conversion_residual,
        reference=0.0,
        tolerance=0.11,
        unit="mg/L",
        note="\u2b50 The ambient CSV carries a five-day figure and **no rate of its own**, so what "
        "the exe does with it is a genuine question -- eqs 24-25 need a rate and the only one "
        "available is the effluent's. Converting at it fits to **0.1013 mg/L**; using the five-day "
        "figure raw misses by **2.6361**, and the measurement refuses to pass unless the raw "
        "reading is at least 10x worse. \u26a0\ufe0f Visible only at a slow rate: at 5 /day the "
        "factor `1 - exp(-5k)` is 1.000 to three decimals and the two readings coincide, which is "
        "why case26 cannot see this and case25's 0.23 /day can. Tolerance is row 237's bar.",
    ),
    Target(
        row="239",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The far-field demand is linear in the typed cBOD5, with no amplitude term",
        source="case27 run 7 at cBOD5 1000, against the law fitted at 20",
        measure=_far_field_demand_linearity,
        reference=0.0,
        tolerance=4.0,
        unit="mg/L",
        note="\u2b50 **A 50x span in the typed load and one law, multiplier exactly 1.** The "
        "experiment note proposed a 2x span; run 7 went to 1000 against the others' 20, far enough "
        "that any amplitude term would show. None does. The measurement asserts the *sensitivity* "
        "too -- halving or doubling the typed cBOD5 gives 96 and 195 mg/L, 29x and 59x worse -- so "
        "the agreement is not a forgiving trace. \u26a0\ufe0f 3.3 mg/L would be poor anywhere "
        "else; here the printed DO spans **-185 to +8**, so it is 1.7 % of the swing, and row 241 "
        "uses the same trace at the same bar.",
    ),
    Target(
        row="122",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The effluent pH is on the free scale, and the speciation runs on the entered TA",
        source="case03's computed DIC endmember, backed out of the trace",
        measure=_effluent_ph_scale_gap,
        reference=0.0,
        tolerance=3.0,
        unit="umol/kg",
        note="\u2b50\u2b50 Two findings in one measurement. case03 enters **DIC 0**, so row 45's "
        "pairing makes the exe compute DIC from TA and pH -- and what it computes says which scale "
        "it read the 10.5 on. Against the endmember of 1645.18: free **+1.11**, NBS +24.78, total "
        "-37.04, seawater -42.22. The measurement refuses to pass unless every rival is at least "
        "10x worse. \u2b50 And the sharper half: the speciation runs on the **entered** TA of "
        "4000, not the density-scaled 4108.4 (+56.89) -- so row 46's scaling is applied to entered "
        "values *after* the chemistry, which is why case03's *computed* DIC endmember is unscaled "
        "at 1645 while case04's *entered* one is scaled at 1689. \u26a0\ufe0f case32 could only "
        "exclude NBS, since free and total coincide at its S = 0; this effluent is 35 psu.",
    ),
    Target(
        row="222",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="A uniform ambient collapses the path integral onto the manual's eq 23, exactly",
        source="case25's two uniform-ambient runs, past D > 5",
        measure=_uniform_ambient_collapse,
        reference=0.0,
        tolerance=0.02,
        unit="mg/L",
        note="\u2b50 The **reconciliation** between this module and row 39's algebraic carbonate "
        "mixing, demonstrated rather than argued. With `DO_a` constant the path integral reduces "
        "to eq 23 exactly, so the two readings rows 214 and 214b separate by 435x become one "
        "expression -- and the exe matches it to **0.0078 mg/L**. Predicted in writing before the "
        "runs were made. \u26a0\ufe0f It also explains why a uniform ambient is useless for "
        "*testing* the path integral, which is what rows 109b and 214b had to scope around.",
    ),
    Target(
        row="220",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The oxygen accumulator seeds at step 1, not at D = 1 and not at the printed grid",
        source="case38's interval sweep -- 1, 3 and 5 at two effluent seeds",
        measure=_do_accumulator_seed_spread,
        reference=0.0,
        tolerance=0.4,
        unit="mg/L spread in the implied ambient DO",
        note="\u2b50\u2b50\u2b50 Settled with **no model at all** -- only the first printed row "
        "of each run. Referenced to `D` = 1 the implied ambient is incoherent (0.011, 5.798, "
        "6.959, 6.813); referenced to **step 1's dilution of 1.0200** it is one number, 8.697 / "
        "8.656 / 8.475, recovered from three intervals and two seeds without being told it. "
        "\u26a0\ufe0f Every earlier DO trace printed *every* step, which is why 'starts at the "
        "first printed row' and 'starts at step 1' were indistinguishable -- and why this row "
        "carried a wrong conclusion earlier the same day. The interval-1 runs are asserted "
        "separately, since their `DO_0 * D_0` must reproduce the typed effluent DO exactly at 2, "
        "5 and 10 mg/L, which is the seed half of row 250.",
    ),
    Target(
        row="224",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Eqs 28-29 are refuted: the ambient BOD is subtracted undiluted",
        source="the two runs with a non-zero ambient cBOD5, case25 run 3 and case26 run 3",
        measure=_undiluted_ambient_bod_error,
        reference=0.0,
        tolerance=0.35,
        unit="relative error of the undiluted form",
        note="\u2b50\u2b50 The manual gives `L_f = (BOD_Le - BOD_La)/D`; the exe behaves as "
        "`BOD_Le/D - BOD_La`, the ambient term never divided. The forms differ by about `D` = 170 "
        "here, so the archive separates them decisively: the manual's predicts `L*k` of -0.95 and "
        "-14.1 where the runs show **-140.8** and **-1930.9**, and the measurement refuses to pass "
        "unless it is at least 50x too small. \u26a0\u26a0 **The sign argument this row "
        "originally rested on does not survive the cBOD5 correction** -- it cited 2000 against an "
        "ambient 500, and 2000 is the mis-recorded value row 225 retracts. At the true 20 the "
        "manual's form is negative too, so what discriminates is magnitude, not sign.",
    ),
    Target(
        row="235",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The far-field decay rate is used exactly as typed, with no temperature correction",
        source="case26's rate pair, 5.0 /day against 1.0, identical in everything else",
        measure=_far_field_rate_is_as_typed,
        reference=0.0,
        tolerance=0.11,
        unit="mg/L",
        note="\u2b50 The pair isolates the rate. Typed, the sag reproduces to **0.0725 mg/L**; "
        "the standard Streeter-Phelps `k(T) = k(20) * theta^(T-20)` at this plume's 10 C makes it "
        "**17.6x worse** at theta = 1.047 and 10x worse at a gentler 1.024 -- both asserted inside "
        "the measurement, so this says the rate is *untouched* rather than merely that the fit is "
        "good. Tolerance is row 237's established far-field bar. \u26a0\ufe0f Not a defect: "
        "there is nowhere in the dialog to enter a reference temperature, so the typed rate is by "
        "construction the rate at the run's own. It matters because a reader who assumes the usual "
        "convention will enter a 20 C rate and get a demand 60 % too large.",
    ),
    Target(
        row="230",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The ambient BOD is subtracted undiluted, and the plume gains oxygen because of it",
        source="case26 run 3, ambient cBOD5 500 against an 8.0 mg/L ambient DO",
        measure=_supersaturated_far_field_oxygen,
        reference=100.06,
        tolerance=0.001,
        unit="mg/L, highest far-field DO",
        note="\u26a0\ufe0f\u26a0\ufe0f **The exe defect that is impossible to argue with.** A "
        "plume travelling through water with a 500 mg/L oxygen demand comes out at **100.06 mg/L "
        "of dissolved oxygen** -- nine times saturation, which is about 11 here. Eqs 28-29 as the "
        "manual writes them give `(BOD_Le - BOD_La)/D`, which is positive here and must *depress* "
        "oxygen; only `BOD_Le/D - BOD_La`, the ambient subtracted undiluted, has the sign the "
        "trace shows. \u2b50 Confirmed twice at rates a twentieth apart (rows 224, 230), and "
        "generalised by row 240. Report to SSMC. Tolerance is the printed digit: this reads the "
        "exe's own column, because the claim is about what it reports.",
    ),
    Target(
        row="251",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="IDOD does not appear a second time in the far field",
        source="case28's two IDOD-100 runs, at the 13 opening rows where FF = 1 exactly",
        measure=_far_field_handoff_gap,
        reference=0.0,
        tolerance=0.05,
        unit="mg/L at the transition",
        note="\u2b50 Decisive rather than suggestive, because **no fit is involved**: at `FF` = 1 "
        "eq 30 reduces to `DO_f`, so the near field's last printed value and the far field's "
        "first can simply be read off the file and compared. A second **undiluted** IDOD would "
        "shift those rows by **100**; one divided by the near-field dilution by 0.406. Observed: "
        "**0.029**. \u26a0\ufe0f The tolerance is set by the transition itself rather than by "
        "printed precision -- the two tables are computed by different code paths and 0.029 is "
        "what that handoff costs.",
    ),
    Target(
        row="250",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="`DO_e` and `IDOD` are separable: the seed dilutes away and the demand does not",
        source="case28 runs 11 and 12, which differ only in effluent DO, 2 against 20",
        measure=_oxygen_seed_separability,
        reference=0.0,
        tolerance=0.06,
        unit="implied fractional dilution offset",
        note="\u2b50\u2b50 Two runs, **one** changed input, and their near-field columns differ "
        "by exactly `18/D` -- 17.65 at the first printed row falling to 0.072 at `D` = 246.6. That "
        "separability is what lets the exe treat the two in opposite ways: the seed is carried by "
        "the effluent and dilutes, the demand is carried by the entrained water and grows to its "
        "full typed value. \u26a0\ufe0f **Reported as `epsilon`, not mg/L**: the residual is "
        "`18 x epsilon / D`, so mg/L would make one discrepancy look large near the port and "
        "small far from it. \u2b50 Normalised it lands in **0.013-0.036**, inside the 0.016-0.044 "
        "rows 109 and 258c measure from *salinity* on unrelated runs -- a third scalar showing the "
        "same fixed offset between the exe's scalar columns and its own `Dilutn`, and the first "
        "carried by the effluent rather than entrained. Tolerance is row 109's.",
    ),
    Target(
        row="258c",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The exe's `P-Sal` implies ~2 % more dilution than its `Dilutn` column, wherever "
        "the printed digit can resolve it",
        source="every archived trace printing `P-Sal` at an effluent-ambient contrast of 20 psu or "
        "more -- case13, 29, 31, 38, 39, 40 -- cut at surface contact",
        measure=_salinity_dilution_offset,
        reference=0.02,
        tolerance=0.005,
        unit="implied fractional dilution offset, median over traces",
        note="⭐⭐ **Executable since 2026-08-25, and the census corrected the row.** The "
        "original claim -- `epsilon` in 0.016-0.044 across eight traces -- was built from row "
        "109's `max |residual|`, and its upper half is the **printed digit**: 0.0005 psu "
        "normalised by `D / contrast` reaches 0.044 at `D` = 340 on the Macoma family's 3.9 psu, "
        "so on those traces the per-row offset is unresolvable and the band was measuring "
        "rounding. Where the contrast is 20 psu or more the picture is clean: the per-trace median "
        "sits in **0.016-0.024**, the offset is positive on **every** developed row of every such "
        "trace, and the residual falls with slope -0.8 to -0.97 in `log D` -- a fixed *fraction* "
        "of the dilution, where rounding or a constant bias would give 0. The reference is the "
        "step controller's own 2 % per-step mass target (row 166), which is also what the "
        "one-step lag explains; the tolerance is a quarter of the effect, and the digit's floor on "
        "these traces (0.002-0.003 at `D` = 200). ⚠️ On the low-contrast family the "
        "medians are not noise either, and they are **not one number**: about -0.5 % on the "
        "current-driven Macoma multiport runs, +2 to +4 % on the limiting-spacing single-port "
        "runs, and -0.7 to -0.9 % with a clean 1/D shape on case34's dense 45 psu multiport runs. "
        "Recorded, not explained. \u2b50\u2b50\u2b50 **And the one-step-lag reading this row "
        "recorded as refuted holds** -- asserted by the measurement rather than returned: pairing "
        "`P-Sal` at row `i` with `Dilutn` at row `i + 1` takes the median from +0.022 to "
        "**+0.002-0.004** on every interval-1 trace, while case38's interval-3 and interval-5 "
        "prints of the same discharge over-correct to -0.037 and -0.074, by the number of steps a "
        "row spans. So the exe prints its scalar columns one step *ahead* of `Dilutn`, where row "
        "220's DO channel lags one step *behind*. The earlier refutation rested on the 3.8 psu "
        "limiting-spacing traces, which cannot resolve the effect either way.",
    ),
    Target(
        row="245",
        agreement=Agreement.REPRODUCES_DEFECT,
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="A municipal-strength cBOD5 of 20 mg/L is enough to print negative oxygen",
        source="case27 run 10, cBOD5 20 at a 20 /day carbonaceous rate",
        measure=_municipal_negative_oxygen,
        reference=-1.863,
        tolerance=0.001,
        unit="mg/L, lowest far-field DO",
        note="\u26a0\ufe0f\u26a0\ufe0f **The strongest single argument in the SSMC report.** Row "
        "241 needed a cBOD5 of **1000** to drive the printed oxygen negative, and nobody types "
        "1000 by accident; **20 mg/L is ordinary municipal wastewater and the value the tab ships "
        "with**. The exe prints -1.863 mg/L, recovers to -0.565 as Brooks spreading takes over, "
        "and warns about none of it -- no clamp, no NaN, no note. The returned value is the "
        "**exe's** printed minimum, so the tolerance is its printed precision; alongside it the "
        "measurement asserts that our `reproduce_undiluted_bod` path also goes negative and that "
        "the **corrected** path does not, which is what makes this a defect rather than a regime. "
        "\u26a0\ufe0f Our reproduction reaches -1.998, a worst residual of **0.591 mg/L** over "
        "this run against the 0.101 row 237 establishes elsewhere -- a 20 /day rate is the most "
        "extreme in the archive and is where our far-field model is weakest. Recorded here rather "
        "than hidden in a widened tolerance.",
    ),
    Target(
        row="43",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Our `Omega_calcite` against the exe's, on the exe's own TA and DIC",
        source="case03 and case04, 82 rows",
        measure=_calcite_saturation_gap,
        reference=0.0,
        tolerance=0.04,
        unit="worst relative gap",
        note="The column rows 35 and 41 left uncovered, and it completes the picture rather than "
        "adding a fourth number: **3.5 %** on calcite alongside 3.4 % on aragonite and 0.024 pH "
        "units, all on the same rows. \u2b50 That the two minerals move together, when row 123 has "
        "their solubility products agreeing to the **last bit**, places the divergence squarely in "
        "the speciation -- the exe's embedded CO2SYS sitting about 0.024 below PyCO2SYS near "
        "pH 10 -- and not in either mineral. \u26a0\ufe0f case04 is solved against case03's "
        "`.prj`, which it has none of its own to use. Safe **here and nowhere else**: the "
        "comparison is fed the exe's *printed* TA and DIC, so what was typed into the dialog "
        "(TA+pH for case03, TA+DIC for case04) never enters the calculation. Folds row 38.",
    ),
    Target(
        row="123",
        phase=4,
        evidence=Evidence.INTERNAL,
        claim="Our `Ksp` **is** PyCO2SYS's, for both minerals",
        source="six (S, T) pairs spanning 10-45 psu and 5-25 C; no reference beyond the library",
        measure=_solubility_product_gap,
        reference=0.0,
        tolerance=0.0,
        unit="relative difference",
        note="Identical to the last bit, not agreeing within a tolerance: both evaluate Mucci "
        "(1983) and neither rounds. \u26a0\ufe0f **Internal, with no reference** -- it compares "
        "our code against a library rather than against the exe, and its value is as a tripwire. "
        "This is exactly the kind of claim that stops being true when a dependency changes its "
        "constants and nothing else notices.",
    ),
    Target(
        row="124",
        phase=4,
        evidence=Evidence.INTERNAL,
        claim="Our Omega differs from PyCO2SYS's only by the exe's rounded calcium",
        source="the same grid; no reference beyond the library",
        measure=_calcium_gap_against_pyco2sys,
        reference=4.443e-4,
        tolerance=1e-6,
        unit="relative difference in [Ca]",
        note="\u2b50 **The whole of our disagreement with PyCO2SYS on saturation state is one "
        "constant.** The exe's dialog carries `[Ca] = 0.01028 x S/35` against PyCO2SYS's "
        "0.0102845697, and Omega is linear in calcium, so the gap is a flat **0.0444 %**. The "
        "measurement asserts it is *constant* across salinity -- the spread is 2e-16 -- because a "
        "drift would mean a different formula rather than a rounded one. \u26a0\ufe0f Internal, "
        "no reference: the exe never prints calcium, so this is our code against a library.",
    ),
    Target(
        row="73",
        agreement=Agreement.REPRODUCES_DEFECT,
        phase=4,
        evidence=Evidence.INTERNAL,
        claim="An undersaturated mineral gives a rate of zero, and the exe's NaN only on request",
        source="the rate law below Omega = 1; no reference, because the exe has no correct value",
        measure=_undersaturated_rate_is_zero,
        reference=0.0,
        tolerance=0.0,
        unit="summed rate below Omega = 1",
        note="\u26a0\ufe0f\u26a0\ufe0f **A defect we deliberately do not reproduce by "
        "default.** The exe evaluates `(Omega - 1) ** N` unguarded, so an undersaturated row is "
        "NaN and a single NaN poisons the rest of the trace -- case09 loses 955 rows that way. "
        "Nothing precipitates from undersaturated water, it dissolves, so zero is the physical "
        "answer and the default. The measurement asserts **both** halves: the default is finite "
        "and zero, and `reproduce_undersaturated_nan` still emits the exe's NaN for anyone "
        "studying it. \u26a0\ufe0f Internal, no reference -- there is no exe output to check a "
        "*correct* value against, which is the point.",
    ),
    Target(
        row="60",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Aragonite reads zero over a **band** of salinity, not below a floor",
        source="every archived trace printing `R_arg`, salinity reconstructed from the dilution",
        measure=_aragonite_dead_band_width,
        reference=10.0,
        tolerance=0.7,
        unit="psu of dead band",
        note="⚠️⚠️ **This corrects ledger rows 60, 68 and 83**, which read the zero as a floor at "
        "S = 35 because all ten Macoma runs sit inside the band. case13 -- a freshwater discharge "
        "into a uniform 32 psu ambient, the only trace that gets well below it -- precipitates "
        "aragonite normally down there and switches off *going up* through 25. Bracketed to "
        "(24.613, 25.305] and (34.924, 35.094], both containing an integer. ⚠️ It is not "
        "saturation: case03 reaches Omega_A 22.9 at S 34 with a zero rate where case13 at "
        "Omega_A 22.4 gives 5823. Tolerance is the wider bracket, which is set by the printed "
        "row spacing rather than by the reconstruction (0.023 psu, row 109). Folds rows 68, 83.",
    ),
    Target(
        row="44",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="`R = exp(logK)(Omega-1)^N` holds to the printed precision on every archived rate",
        source="1 476 rows, both minerals, all three bands, 13 traces",
        measure=_precipitation_law_margin,
        reference=0.0,
        tolerance=1.0,
        unit="residual / printed-precision bound",
        note="⭐⭐ **The tolerance is the assertion.** A value of 1 means the residual exactly "
        "fills what three printed decimals can resolve; the archive's tightest row reaches "
        "**0.993** and none exceeds it. The bound is arithmetic, not a fitted bar: `N x 0.0005 / "
        "(Omega - 1)` for `Omega`'s half-digit through the exponent, plus `0.0005 / R` for `R`'s "
        "own. ⚠️ That is what makes the raw residual look 10x worse on case09's near-saturated "
        "rows (1.6e-3 at Omega 2.09) than on strongly supersaturated ones (1.7e-4) -- the law is "
        "equally good throughout and only the resolution moves. Free fits over these rows recover "
        "logK -0.10599 / N 2.87000 for calcite and 1.10990 / 2.26004 for aragonite's high band, "
        "so this also settles the `exp()` convention and the negative calcite sign archive-wide. "
        "Folds rows 59, 129, 130.",
    ),
    Target(
        row="60c",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The low aragonite edge sits at 25 psu, read from a printed salinity",
        source="case32's five chemistries, salinity from case31's bit-identical twin",
        measure=_aragonite_low_edge_bracket,
        reference=0.14,
        tolerance=0.01,
        unit="psu of bracket",
        note="⭐⭐ All five chemistries switch `R_arg` off at the **same step**: last active at a "
        "printed 24.895 psu, first zero at 25.035 -- so the bracket is 0.14 psu and contains 25.0. "
        "Row 60's archive-wide bracket has to reconstruct salinity; this one reads it. ⚠️ The "
        "salinity comes from a different file, and that is exact rather than a shortcut: the "
        "measurement **asserts** the five runs and the donor agree bit for bit on every shared "
        "hydrodynamic column across all 572 steps before using it. Tolerance is one printed step "
        "in salinity at this dilution.",
    ),
    Target(
        row="60d",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Saturation state does not set the edge: five runs switch together across 5 in Omega",
        source="case32, Omega_A at the switching row of each chemistry",
        measure=_aragonite_edge_omega_spread,
        reference=5.04,
        tolerance=0.1,
        unit="range in Omega_A at the switch",
        note="⭐⭐ **The control that makes row 60 a mechanism instead of an observation.** If the "
        "exe switched on saturation, five runs switching at one step would have to share an "
        "Omega_A. They span **3.997 to 9.036** -- a factor of 2.3 -- with everything else held "
        "identical, so salinity is the only thing left that could be doing it. Previously this "
        "rested on comparing case03 with case13, two runs differing in every respect.",
    ),
    Target(
        row="45",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="A zero DIC means *not supplied* and selects TA + pH; any real DIC discards the pH",
        source="case32's five runs, which all type pH 10.5 and vary DIC across it",
        measure=_carbonate_pairing_violations,
        reference=0.0,
        tolerance=0.0,
        unit="runs disagreeing with the pairing rule",
        note="⭐ Decided by construction rather than inferred: two runs enter DIC 0 and three a "
        "real DIC, all five typing the same pH. Where DIC was supplied the exe reproduces it and "
        "the printed pH lands at 11.995 / 10.843 / 9.789 -- nowhere near the 10.5 typed in. Where "
        "it was not, the computed endmember matches **our** speciation from TA + pH to under one "
        "µmol/kg on a TA of 5000 the port had never been tested against, and excludes the NBS "
        "scale by 68-83. ⚠️ Free and total coincide at S = 0, so this confirms row 122 against "
        "NBS without separating free from total.",
    ),
    Target(
        row="60b",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Below the gap the exe applies the dialog's own low-band law, unchanged",
        source="395 low-band rows -- case13 plus case32's five -- against the dialog as written",
        measure=_aragonite_low_band_residual,
        reference=0.0,
        tolerance=5.0e-4,
        unit="worst relative error",
        note="⭐ The half of the correction that makes it a finding rather than a doubt: the band "
        "the ledger said was **never evaluated** reproduces to 1.1e-4 with no fitting at all. "
        "⚠️ The tolerance is looser than `R_arg`'s printed precision (~3e-6 relative here) on "
        "purpose -- an unconstrained fit gives logK 1.52995, N 2.33001 and still leaves 9e-5, so "
        "the residual is in the law's form and not in the dialog's rounding. Small, and real.",
    ),
    Target(
        row="215",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="A scalar overlay does not perturb the hydrodynamics, in any shared column",
        source="case02 against case03, and test36 against test37 and test38",
        measure=_scalar_overlay_perturbation,
        reference=0.0,
        tolerance=0.0,
        unit="worst absolute difference",
        note="⭐ Two independent families, 31 column comparisons, exact zeros throughout: "
        "carbonate on (5 columns x 41 rows) and DO then DO-plus-carbonate on (13 x 526). This is "
        "the licence for treating chemistry and DO as post-processing over a trajectory instead "
        "of state the solver carries, and for handing an archived `.dat` straight to our "
        "chemistry. Zero tolerance because the columns agree bit for bit. Folds row 40.",
    ),
    Target(
        row="216",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The manual's DO-or-pH restriction is not enforced by the exe",
        source="test38, which prints both sets at once",
        measure=_columns_the_manual_forbids_together,
        reference=7.0,
        tolerance=0.0,
        unit="carbonate columns printed beside `DO`",
        note="Manual section 5.2.6 says the DO and pH calculations cannot be conducted "
        "simultaneously. test38 prints all seven carbonate columns **and** `DO`. ⭐ That matters "
        "for phase 8: lifting the restriction in our port is not a new capability, it is "
        "declining to enforce something the exe never enforced either.",
    ),
    Target(
        row="46",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The effluent endmember is scaled by rho_eff/1000: TA 4000 becomes 4108",
        source="case03 + case04, back-solved over 41 rows",
        measure=_endmember_alkalinity,
        reference=4109.15,
        tolerance=1.5,
        unit="umol/kg",
        note="⚠️ Reproduces an exe *slip*: it converts the effluent endmember by density and the "
        "ambient not at all (PLAN.md §7.5). Matched deliberately behind a named flag, so the "
        "corrected path stays one argument away.",
    ),
    Target(
        row="35",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Our pH against case03's printed column, on the exe's own TA and DIC",
        source="case03, 41 rows",
        measure=lambda: float(
            np.max(np.abs(_case03_chemistry()["ph_total"] - _case03_chemistry()["ph_exe"]))
        ),
        reference=0.0,
        tolerance=0.03,
        unit="pH",
        note="Worst absolute difference. The tolerance is the *pre-existing* offset between the "
        "exe's printed column and PyCO2SYS -- 0.011 to 0.024 (row 41) -- not a number chosen to "
        "fit: agreement inside it means our solver adds nothing of its own.",
    ),
    Target(
        row="41",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Our Omega_aragonite against case03's, on the exe's own TA and DIC",
        source="case03, 41 rows",
        measure=lambda: float(
            np.mean(
                np.abs(
                    _case03_chemistry()["omega_aragonite"]
                    - _case03_chemistry()["omega_aragonite_exe"]
                )
                / _case03_chemistry()["omega_aragonite_exe"]
            )
        ),
        reference=0.0,
        tolerance=0.05,
        unit="MARE",
        note="Row 41 pins the exe-vs-PyCO2SYS divergence at +0.8 to +3.4 % on Omega, which is a "
        "solubility-constant and calcium-rounding difference we chose to record rather than "
        "reproduce. So this is a *bounded disagreement*, not a match.",
    ),
    Target(
        row="219",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Plume DO against every archived column, on the exe's own dilution and depth",
        source="case24, four traces printing DO",
        measure=_oxygen_worst_residual,
        reference=0.0,
        tolerance=0.007,
        unit="mg/L",
        note="⭐ The measurement that overturned the manual's eq 23: read literally, with the "
        "ambient DO at the plume's own depth, it misses by 0.218 mg/L. Integrating the entrained "
        "ambient along the path gets 0.0063, which is the floor for rebuilding an integral from "
        "three-decimal printed rows -- so the tolerance is that floor, not a fitted number.",
    ),
    Target(
        row="237",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The far-field DO sag, against every archived trace that printed one",
        source="case25, case26 and case27 -- seven traces, three carbonaceous rates",
        measure=_far_field_residual,
        reference=0.0,
        tolerance=0.11,
        unit="mg/L",
        note="Eqs 24-30 with eq 28's division by the near-field dilution **removed**, which is "
        "what the exe does. The tolerance is set by the worst trace (case25's ambient run, 0.10); "
        "the "
        "four ordinary runs sit at 0.009-0.022 against a printed resolution of 0.001. Every input "
        "is hand-recorded because the DO tab is in no `.prj` -- see the case READMEs.",
    ),
    Target(
        row="240",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Eq 28's `/D` is absent: the demand does not depend on the near-field dilution",
        source="case27 runs 2, 4 and 6 -- one set of DO inputs, three trajectories",
        measure=_far_field_demand_spread,
        reference=0.0,
        tolerance=0.05,
        unit="fractional spread",
        note="`D_near` spans 169.75 to 246.61, a 45 % increase, with every DO input held fixed. "
        "The demand implied at the transition spreads by 1.7 %. Eq 28 as written requires it to "
        "spread "
        "by the same 45 %, so the tolerance is not a precision claim -- anything below ~0.1 "
        "falsifies the manual's form outright and nothing above ~0.4 could be the exe's.",
    ),
    Target(
        row="241",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The missing dilution drives the exe to negative oxygen, and we reproduce it",
        source="case27 run 7 -- cBOD5 1000 mg/L through a 170:1 near field",
        measure=lambda: _far_field_residual(
            traces=[("case27_farfield_bod_conversion/ModelResults_7.dat", 1000.0, 5.0, 0.1, 0.0)]
        ),
        reference=0.0,
        tolerance=4.0,
        unit="mg/L",
        note="⚠️ The trace prints a far-field DO falling monotonically to **-184.985 mg/L** with "
        "no warning and no clamp. Tolerance is 2 % of the 193 mg/L excursion, not an absolute bar: "
        "reproducing an absurd number to 2 % is the evidence that the mechanism is understood. ⚠️ "
        "This target uses cBOD5 1000, not the 20 the other far-field targets share.",
    ),
    Target(
        row="242",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="IDOD is subtracted from the ambient, not the effluent, so it grows with dilution",
        source="case27 run 9 -- IDOD 3 mg/L, otherwise identical to run 6",
        measure=_idod_residual,
        reference=0.0,
        tolerance=0.0015,
        unit="mg/L",
        note="Eq 23 makes IDOD an effluent property worth 0.012 mg/L at this dilution; measured "
        "against its control it is worth **2.989**, and it grows along the trajectory rather than "
        "diluting away. The tolerance is the printed resolution of 0.001, which the exe's "
        "placement actually reaches past D > 5. ⚠️ The two forms are identical at IDOD = 0, which "
        "is every other archived trace -- so this was invisible until run 9 existed.",
    ),
    Target(
        row="243",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Eq 30's ambient DO is the profile value at the trapping depth",
        source="case27 run 8 -- the only far-field run with a stratified ambient",
        measure=lambda: _far_field_ambient_residual(9.118),
        reference=0.0,
        tolerance=0.03,
        unit="mg/L",
        note="The surface value misses by 1.16, the deepest by 0.74, and the uniform 8.0 the other "
        "runs used by 0.62. ⚠️ It does **not** separate the trapping-depth value from the "
        "profile's depth-mean, which sit 0.025 apart here -- both fit, and a profile with a mean "
        "far from its trapping-depth value would be needed. This run also confirms the missing "
        "`/D` is genuinely absent rather than misplaced onto `DO_a` (row 240).",
    ),
    Target(
        row="244",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="At 20 /day the far-field curve identifies its own rate, and goes negative",
        source="case27 run 10 -- cBOD5 20 mg/L, the rate raised until the exponential saturates",
        measure=lambda: _far_field_residual(
            traces=[("case27_farfield_bod_conversion/ModelResults_10.dat", 20.0, 20.0, 0.1, 0.0)]
        ),
        reference=0.0,
        tolerance=0.6,
        unit="mg/L",
        note="Every earlier far-field run sits where `1 - e^{-kt}` is near-linear, so the rate was "
        "believed rather than measured; here 5 /day misses by 6.08 and 1 /day by 8.73. The 0.6 "
        "tolerance is the worst residual, at the bend -- the implied ultimate converges to 19.92 "
        "against a typed 20.0. ⚠️⚠️ And a **municipal-strength 20 mg/L** cBOD5 is enough to drive "
        "the exe's printed DO to **-1.863 mg/L**; run 7 needed 1000 to look this bad.",
    ),
    Target(
        row="246",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Eq 30's ambient DO is the trapping-depth value, not the profile's depth-mean",
        source="case28 -- three falling/rising pairs sharing a depth-mean",
        measure=_mirror_profile_gap,
        reference=1.769,
        tolerance=0.1,
        unit="mg/L",
        note="⭐⭐ The two ambient profiles are mirror images built to share a depth-mean (7.167) "
        "while differing at the trapping depth (8.264 against 6.354), so the BOD demand and IDOD "
        "cancel in the difference and this measures eq 30's DO_a alone. The reference is what the "
        "trapping-depth reading predicts from the observed near-field endpoints; the depth-mean "
        "predicts 0.750, and the tolerance is a tenth of the gap between them. Measured at "
        "**1.765 in all three pairs**, across an 87x change in decay rate and 100 mg/L of IDOD.",
    ),
    Target(
        row="247",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="Row 242's IDOD form holds at 33x its fitted value, and nothing clamps",
        source="case28 run 7 -- IDOD 100 mg/L against a uniform ambient",
        measure=_implied_idod,
        reference=100.0,
        tolerance=0.05,
        unit="mg/L of IDOD",
        note="Backing the immediate demand out of the accumulator at the last row gives 100.010 "
        "against a typed 100. The exe prints a near-field DO of **-93.2 mg/L** doing it, with no "
        "clamp, no warning and no NaN -- which no archived trace had ever tested. ⚠️ It is the "
        "first-step convention that degrades at this scale, not the form: row 220's one-step lag "
        "is worth 0.06 mg/L at IDOD 3 and 1.9 at IDOD 100, so whole-column reproduction is 0.74 "
        "past D > 5 here against 0.0010 at IDOD 3.",
    ),
    Target(
        row="263",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The legacy build's wastefield width carries no angular correction",
        source="every legacy-build trace that prints a width -- case13 x2, case16, case31",
        measure=_legacy_width_law_error,
        reference=1.683,
        tolerance=0.05,
        unit="worst absolute error, m",
        note="⭐ **The legacy build stopped being history**: far-field work uses it for its wider "
        "output-column set, so the port has to reproduce its width law too. `(n-1)*L + diameter` "
        "with **no** angular factor is worst by 0.59 m on the four legacy traces where the cosine "
        "law is worst by 13.61 m -- a factor of 23, and the same project gives 96.29 m current "
        "against 109.59 m legacy. ⚠️ **0.59 m is not row 96's 0.005 m**: the span is right and the "
        "*diameter* is not, since 109.59 implies 5.890 m where the trace ends at 6.481. "
        "⚠️⚠️ **The residual is NOT merging, and an earlier reading here said it was.** A legacy "
        "**single-port** run is exact -- 5.45 echoed against a final `P-dia` of 5.446, which is "
        "two-decimal rounding -- and every multiport legacy trace merges, so merging looked like "
        "the discriminator. A paired run then killed it: **the same project on both builds**, both "
        "merging at step 258, gives a *current*-build error of **-0.0022 m** against the legacy "
        "**+0.591 m**. Merging cannot explain a residual that appears on one build and not the "
        "other, and the cosine law holds to **0.005 m across 87 merged current-build traces**. "
        "⭐ What the pair does establish is the **diameter term**: `span*|cos| + final printed "
        "diameter` reproduces the current-build echo exactly, so the diameter is the last row. "
        "⚠️ So the legacy residual sits on the **span** side and is unexplained. It is zero when "
        "the span is zero (single port) but does not scale with it: 103.70 m of span gives 0.591 "
        "on one run and 0.284 on another. Implied factors of 0.9943 / 0.9973 / 0.9983 correspond "
        "to no angle in these geometries. Section 7 item 22, still open, now bounded to one term. "
        "Selected through `FarFieldSettings.exe_build`.",
    ),
    Target(
        row="263b",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The cosine law is 20x worse on the same traces -- the discriminating control",
        source="the same four legacy traces, scored under row 96's current-build law",
        measure=_legacy_width_cosine_control,
        reference=33.464,
        tolerance=0.5,
        unit="worst absolute error, m",
        note="Without this number row 263's 0.59 m means nothing -- it could be a good fit or a "
        "poor one depending on what the alternative does. The cosine law, which row 96 confirms to "
        "**0.005 m** on 92 current-build traces, is out by **13.61 m** on these four. So the two "
        "builds are not a matter of tolerance: each law is decisively right for its own "
        "generation, and 13.61 m is the correction itself on an 18-port, 6.10 m, 30-degree "
        "diffuser. ⚠️ Reference tracks the worst trace, so it moves if a legacy run with a wider "
        "diffuser is archived.",
    ),
    Target(
        row="263c",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="A legacy far field is predicted from the case -- section 7.24 does not apply to it",
        source="case13's legacy run, our width against its 495 printed rows past 50 m",
        measure=_legacy_farfield_width_mare,
        reference=0.00126,
        tolerance=0.002,
        unit="far-field width MARE",
        note="⭐⭐⭐ **The first far field predicted from a case rather than reproduced from a "
        "trace.** Row 115's transition adjustment is 1.00-1.13x on current-build traces and "
        "**1.0002 on all four legacy ones**, so the virtual origin of row 256 is zero and `w0` is "
        "the echoed geometric width -- which is what `results.run` already passes. Width lands at "
        "**0.126 %** over 495 rows to 493 m. ⚠️ The **dilution** is 6.06 % low and none of it is "
        "Brooks: ours ends at 159.223 against 169.754, which is -6.20 %, matching the far-field "
        "error at the handoff and drifting only to -5.90 % at 493 m. 169.754/156.331 = +8.59 % is "
        "row 258b's 14-step overshoot, and 1.0185/1.0859 = 0.938 closes it. ⚠️ Needs "
        "`stop_at_surface` and `max_rise_or_fall = 2`, which is row 258's correction.",
    ),
    Target(
        row="114",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The Brooks 4/3-power width column, over every archived far field",
        source="eight traces, six Macoma and two generated",
        measure=_brooks_width_error,
        reference=0.0,
        tolerance=1e-3,
        unit="worst relative error",
        note="⭐ Exact to the three decimals the exe prints on the six Macoma runs (1e-5), and "
        "8e-4 "
        "on the two generated ones, whose larger widths print with less relative resolution. The "
        "tolerance is that printing limit rather than the measured value. `w0` is the far field's "
        "own first row and `x` runs from it, which is the convention row 115 established.",
    ),
    Target(
        row="116",
        agreement=Agreement.DIVERGES,
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="The Brooks dilution column is reproduced low, and the shortfall is bounded",
        source="the same eight traces, worst case case06",
        measure=_brooks_dilution_shortfall,
        reference=0.0,
        tolerance=0.12,
        unit="worst fractional shortfall",
        note="⚠️ **A recorded discrepancy, not an achievement.** The same parameters that give the "
        "width exactly give dilutions systematically **low** -- 0.03 % on case02 up to **11.2 % on "
        "case06** -- and never high, which the measurement asserts rather than assumes. Bounded at "
        "12 % so a change is detectable. ⭐⭐ **The cause is known (row 256): the exe runs Brooks "
        "from a virtual origin**, starting from the echoed geometric wastefield width at the "
        "upstream distance where that solution has grown to the handoff width, which takes the "
        "worst trace to **0.096 %**. So this target is deliberately the measurement of the "
        "*uncorrected* form, because that is what `farfield/brooks.py` still computes -- a "
        "divergence we have localised and chosen to keep pinned, not one we cannot explain.",
    ),
    # ------------------------------------------------------------------ Phase 5, near field
    Target(
        row="145",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The jet phase clears upstream's 0.5 % bar with no cross-flow",
        source="case18 test23 -- one port, zero ambient current, 223 rows",
        measure=lambda: _sweep_jet_mare("test23"),
        reference=0.0,
        tolerance=0.005,
        unit="MARE on dilution",
        note="0.5 % is upstream's own acceptance bar (manual Appendix A supplies the bar, not the "
        "targets -- row 12). ⚠️ This run is also the **floor** for every cross-flow figure "
        "below: at 0.31 % it is set by the exe's sigma-t differing from EOS-80 (row 101), not by "
        "the closure, so a cross-flow result *under* it would mean something had been fitted.",
    ),
    *[
        Target(
            row=f"171{suffix}",
            phase=5,
            evidence=Evidence.GOLDEN,
            claim=f"Cross-flow jet phase at {current:g} m/s, against upstream's 0.5 % bar",
            source=f"case19 {run} -- the sweep's {current:g} m/s arm",
            measure=(lambda run=run: _sweep_jet_mare(run)),  # type: ignore[misc]
            reference=0.0,
            tolerance=ceiling,
            unit="MARE on dilution",
            note=note,
            # ⚠️ The two arms that miss upstream's own 0.5 % bar are divergences, and the
            # sweep's honesty depends on their not being averaged into the two that clear it.
            agreement=agreement,
        )
        for suffix, run, current, ceiling, note, agreement in (
            (
                "a",
                "test28",
                0.01,
                0.005,
                "Clears upstream's 0.5 % bar outright, at 0.34 %. The tolerance is that bar, not "
                "the measured value -- this arm has room to degrade and still be acceptable.",
                Agreement.MATCHES,
            ),
            (
                "b",
                "test27",
                0.02,
                0.005,
                "Clears upstream's 0.5 % bar outright, at 0.36 %. Same tolerance and same reason "
                "as the 0.01 m/s arm; together they show the closure is flat in weak cross-flow.",
                Agreement.MATCHES,
            ),
            (
                "c",
                "test29",
                0.05,
                0.007,
                "⚠️ 0.52 % -- just past upstream's bar, and recorded as such rather than rounded "
                "down to it. The tolerance is the measured value plus the room the EOS floor "
                "explains, not the bar it misses.",
                Agreement.DIVERGES,
            ),
            (
                "d",
                "test30",
                0.10,
                0.012,
                "⚠️ 0.88 %, the worst arm of the sweep and **a recorded discrepancy, not an "
                "achievement**. The trend with current is real: this is where the closure is "
                "furthest from the exe, against 21 % before forced entrainment was derived.",
                Agreement.DIVERGES,
            ),
        )
    ],
    Target(
        row="171e",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The published PAE closure is 20-45x worse than UM3's across the same sweep",
        source="case19, all four arms, 3rd-edition entrainment against UM3's",
        measure=lambda: min(
            _sweep_jet_mare(run, published_closure=True) / _sweep_jet_mare(run)
            for run in ("test28", "test27", "test29", "test30")
        ),
        reference=20.0,
        tolerance=19.0,
        unit="worst-case ratio",
        note="The control that makes the four figures above mean something. Summing the 3rd "
        "edition's published equations onto a separate Taylor term gives 11-20 % where UM3's "
        "structure gives 0.34-0.88 %. Reference and tolerance bracket the ratio at **1 to 39**: "
        "the claim is that the derived closure is decisively better, and a ratio near 1 would say "
        "the sweep no longer distinguishes them.",
    ),
    Target(
        row="21",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01 dilution over the jet phase, against upstream's 0.5 % bar",
        source="case01, 53 rows before the first local maximum",
        measure=lambda: _case01_mare("Dilutn", "dilution", "jet"),
        reference=0.0,
        tolerance=0.005,
        unit="MARE",
        note="0.5 % is upstream's own acceptance bar (manual Appendix A supplies the bar, not the "
        "targets -- row 12). The jet phase is where the closure is least dependent on the "
        "termination logic.",
    ),
    Target(
        row="17",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01 dilution over the whole trace",
        source="case01, all 84 printed rows",
        measure=lambda: _case01_mare("Dilutn", "dilution", "all"),
        reference=0.0,
        tolerance=0.008,
        unit="MARE",
        note="⚠️ **This corrects ledger row 17**, which claims <=0.5 % MARE over all 84 rows. "
        "Measured whole-trace it is 0.74 %, because the error is concentrated after the first "
        "trapping (see row 17b) rather than spread evenly. The jet phase does clear 0.5 % "
        "(row 21), which is most likely what the original figure was measuring.",
    ),
    Target(
        row="17b",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01 dilution after the first trapping -- the known late drift",
        source="case01, 18 rows from step 335",
        measure=lambda: _case01_mare("Dilutn", "dilution", "late"),
        reference=0.0,
        tolerance=0.02,
        unit="MARE",
        note="⚠️ A **recorded discrepancy, not an achievement**: 1.7 % once the plume has trapped "
        "and begun to oscillate. The same drift shows on test31 over a late window, so it is a "
        "property of the closure past the first extremum and not of this case.",
    ),
    Target(
        row="21b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01 plume diameter over the jet phase",
        source="case01, 53 rows",
        measure=lambda: _case01_mare("P-dia", "diameter", "jet"),
        reference=0.0,
        tolerance=0.012,
        unit="MARE",
        note="The independent check on the dilution: both follow from the same mass, so agreeing "
        "on one and not the other would mean the geometry is wrong. It runs about twice the "
        "dilution error, which is expected -- the radius goes as the square root of the mass.",
    ),
    Target(
        row="133",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The step controller caps mass growth at about 2 % per step",
        source="27 023 steps across 76 archived traces",
        measure=_step_mass_growth_cap,
        reference=0.02,
        tolerance=0.001,
        unit="largest per-step mass growth",
        note="⭐ **Why every comparison in this project is made at the exe's printed times rather "
        "than step-for-step.** The controller varies the *time step* to hold mass growth near 2 %, "
        "so the physics decides how long a step lasts and matching step numbers would compare "
        "different instants. `Dilutn` is exactly `m / m_e` (row 135), so consecutive dilutions "
        "give "
        "the growth directly. Measured max 2.083 %, median 1.94 %; the tolerance allows the "
        "overshoot the controller evidently tolerates. Folds row 160.",
    ),
    Target(
        row="140",
        phase=5,
        evidence=Evidence.INTERNAL,
        claim="The contraction leaves the initial mass flux unchanged",
        source="internal -- an identity, with **no reference** to check it against",
        measure=_contraction_mass_flux_spread,
        reference=0.0,
        tolerance=0.0,
        unit="spread in b0^2 rho |U0| over c in 0.25 to 1",
        note="⭐ What makes the contraction self-consistent, and there is **no reference** for it "
        "-- the exe prints no mass flux. `c` shrinks the jet area, so "
        "`b0 = (d/2) sqrt(c)` and `|U0| = Q/(n c A)` -- and the mass flux they imply, "
        "`rho_e Q/(n pi)`, does not contain `c`. The contraction redistributes the discharge "
        "between radius and speed without inventing or destroying mass, so it changes a run's "
        "initial *momentum* and not its mass. Exact to floating point, hence a zero tolerance. "
        "Folds row 139, which is the `b0` half and is asserted inside the measurement.",
    ),
    Target(
        row="109",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Salinity mixes by the same path integral the DO module found",
        source="the eight archived runs that traverse more than 3 m of depth",
        measure=_salinity_path_integral_error,
        reference=0.0,
        tolerance=0.06,
        unit="implied fractional dilution offset",
        note="⭐⭐ **Row 214's rule, confirmed on a third scalar.** DO found that entrained "
        "ambient is accumulated along the trajectory, not evaluated where the plume ends up; "
        "salinity is printed by far more traces and settles it independently. ⚠️⚠️ **Measured "
        "as a fractional dilution offset, not in psu** -- corrected 2026-08-19 by case31. The "
        "residual is `contrast x epsilon / D`, so psu made a 3.5 psu trace and a 32 psu one "
        "look like different physics when they differ only in the driving term and the "
        "dilution. Normalised, `epsilon` sits in **0.016-0.044** across all eight traces "
        "while the contrast spans 3.5 to 32 psu -- a 9x range in the driver against a 2.7x "
        "spread in the invariant. ⭐ That ~2 % is the step controller's own per-step mass "
        "target (row 166), which points at a one-step alignment between the scalar columns "
        "and the dilution column, the same family as row 220's DO lag. ⚠️ **Not confirmed**: "
        "shifting by a whole step fixes case31 and worsens every limiting-spacing trace. ⚠️ "
        "Seeded with the ambient already entrained by the first printed row, unlike DO.",
    ),
    Target(
        row="109b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The algebraic reading of the mixing rule is decisively worse for salinity",
        source="the 11 traces that can tell the two forms apart; the **weakest** of them",
        measure=_salinity_algebraic_penalty,
        reference=44.0,
        tolerance=15.0,
        unit="ratio",
        note="The control that makes the row above mean something: without it, 0.023 psu could be "
        "two forms that barely differ. ⚠️ Only traces with a **deep traverse** can discriminate -- "
        "over less than a metre the two agree inside three printed decimals, which is why the "
        "shallow Macoma runs never exposed this and case22's 5.5 m descent does. ⚠️ **Measured "
        "per trace now**: dividing the worst algebraic error by the worst path error was a number "
        "about neither once the archive spanned two contrasts. The separation narrows from 40-58x "
        "to **15x** on gap_3, the high-contrast run -- still an order of magnitude, which is the "
        "claim, and the tolerance is wide because that is what is being asserted.",
    ),
    Target(
        row="78",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Boundary contact is on the plume edge, not its centreline",
        source="42 surfacing events and one bottom hit across the archive",
        measure=_boundary_criterion_violations,
        reference=0.0,
        tolerance=0.0,
        unit="events violating the criterion",
        note="A plume surfaces when `depth - radius <= 0` and hits the seabed when "
        "`depth + radius >= bottom`, the seabed being `port_depth + port_elevation` (row 77, "
        "folded "
        "here). Zero violations, hence a zero tolerance. ⚠️ Counting violations rather than "
        "measuring how far past the boundary the printed row sits: that overshoot runs 0.003 to "
        "0.73 m and is the **output interval**, not the rule -- the true crossing falls between "
        "printed rows.",
    ),
    Target(
        row="184",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="A `Local maximum rise or fall` banner marks a depth turning point",
        source="116 such events across the archive",
        measure=_turning_point_offset,
        reference=0.0,
        tolerance=0.0025,
        unit="m from the neighbourhood extremum",
        note="97 of the 116 land exactly on the extremum of their own neighbourhood and the rest "
        "within 0.002 m, which is two units in `Depth`'s last printed digit. ⚠️ The residual is "
        "the output interval, not the rule: with every fifth step printed the true turning point "
        "usually falls between rows -- the same reason row 56's trapping depth reads 1.710 where "
        "the chemistry says 1.747. Tolerance is that printed floor.",
    ),
    Target(
        row="205",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The 45 and 135 degree runs merge at the same diameter-to-spacing ratio",
        source="case16's test17 and test18, mirror images about a 90 degree current",
        measure=_merge_symmetry_gap,
        reference=0.0,
        tolerance=0.0006,
        unit="difference in d/L",
        note="⭐ A symmetry check that needs **no model**: both declare merging at d/L = 0.843000, "
        "identical to six decimals, so the trigger depends on the *magnitude* of the angle between "
        "diffuser and flow and not its sign. That is what `|sin psi|` gives and a signed form does "
        "not. Tolerance is what `P-dia`'s three decimals can resolve at this spacing. It "
        "corroborates row 181's law from a quantity that law was never fitted to (row 106 folded).",
    ),
    Target(
        row="191",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="A single plume merges once it is wide enough relative to its port depth",
        source="every trapping event in the limiting-spacing runs, case22, case23 and case30",
        measure=_merge_trigger_bracket,
        reference=0.0095,
        tolerance=0.002,
        unit="bracket width in diameter / port depth",
        note="⭐⭐ **Tightened 5.6x on 2026-08-20** by case30's port-diameter sweep. The bracket "
        "was **(0.961, 1.014]**, width 0.053; it is now **(0.9945, 1.0040]**, width **0.0095** -- "
        "straddling `diameter = port depth` by 0.0055 below and 0.0040 above, half a percent "
        "either side of exactly 1.0. The new edges are `d0.25_dep2.0` trapping *unmerged* at "
        "0.9945 and `d0.22_dep2.0` trapping *already merged* at 1.0040. "
        "⚠️ **A bracket, not a value**: the trigger is somewhere between those two and the "
        "archive still cannot say where -- but it now points squarely at 1.0, which is the rule. "
        "⚠️ **This number is expected to move.** It states what the archive brackets, so every "
        "relevant run narrows it and the reference must follow; it failed exactly that way when "
        "the sweep landed, which is the intended behaviour and not a regression. "
        "⭐ case30 had already cut it from 0.475: `gap_1` traps at 0.7804 without firing and "
        "merges 21 steps later, which is what **retires the *checked at trapping* half of row "
        "191** -- case22 and case23 had the trap and the crossing on the same step. Tolerance is "
        "what `P-dia`'s three decimals resolve at these port depths. ⚠️ The rule is still "
        "incomplete: see row 191b, where the banner lags the crossing, though that lag is now "
        "explained in two of its three regimes. Folds row 190.",
    ),
    Target(
        row="191d",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Multiport merging fires on the crossing step itself, with no lag",
        source="every multiport run whose diameter reaches its spacing mid-trajectory",
        measure=_multiport_merge_lag,
        reference=0.0,
        tolerance=0.0,
        unit="steps of lag",
        note="⭐⭐⭐ **This splits row 191b's problem in half.** The banner lag of 0-54 steps was "
        "measured entirely on **single-port** runs, where a banner can only come from the "
        "limiting-spacing rule -- and case34's four spacings, 0.3 to 2.0 m, show ordinary merging "
        "landing on the crossing every time, `d/L` inside 1.002-1.011. So the lag belongs to one "
        "rule, not to merging. ⚠️ And it is not sub-criticality: these fire at `F` = 0.0045 with "
        "zero lag while single-port `gap_3` at `F` = 0.113 lags 23. Zero tolerance because a step "
        "is an integer.",
    ),
    Target(
        row="191c",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe is deterministic: the same inputs give a byte-identical `.dat`",
        source="case30's gap_2 against case23's limspc_gap, five days and a session apart",
        measure=_repeat_run_byte_difference,
        reference=0.0,
        tolerance=0.0,
        unit="differing bytes",
        note="⭐⭐ The first same-input repeat run in the archive, and the premise every "
        "single-run finding had been resting on without a test. All 115 366 bytes agree, so a "
        "difference between two traces is a difference between their inputs and not between two "
        "sittings at the GUI. Zero tolerance because bytes do not have a resolution.",
    ),
    Target(
        row="183",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="A run stops at a turning point unless something else stopped it",
        source="71 archived traces carrying a turning point",
        measure=_termination_without_a_reason,
        reference=0.0,
        tolerance=0.0,
        unit="traces ending unexplained",
        note="⭐ 59 of the 71 end within five steps of their last turning point, and **every "
        "one of "
        "the other twelve has another stated reason** -- a bottom or surface hit (row 78) or "
        "the "
        "5001-step cap (row 75). Counting the *unexplained* ones makes this a rule rather "
        "than a tendency, so the tolerance is zero. ⚠️ It checks that termination coincides with a "
        "turning point, not which ordinal: the `switch + 1` half needs the rise/fall setting, and "
        "no `.dat` echo carries it.",
    ),
    Target(
        row="134",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Bearings are `(cos, sin)`, not compass",
        source="case16's test16, a 90 degree jet in a 90 degree current",
        measure=_bearing_convention_error,
        reference=0.0,
        tolerance=0.0005,
        unit="m of cross-axis drift",
        note="⭐ Decisive between two conventions 90 degrees apart. A 90 degree jet in a "
        "90 degree current runs up **+y** and never leaves it: test16's final `x` is 0.000. Read "
        "as a compass bearing -- north at 0, clockwise -- it would go due east and the whole "
        "displacement would be in `x`. The obliques fix the sign and are asserted inside the "
        "measurement: `cos 175` is negative and test19 ends at -2.187, `cos 70` positive and "
        "test20 at +0.728. Tolerance is the printed precision of a position column.",
    ),
    Target(
        row="75",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The solver stops at 5001 steps, and only degenerate runs get there",
        source="the longest trace in the archive",
        measure=_solver_step_cap,
        reference=5001.0,
        tolerance=0.0,
        unit="steps",
        note="Exact, hence a zero tolerance. ⚠️ What reaches it is the point: case09, whose "
        "plume leaves the water column upward at 39.5 m/s, and case29's sub-critical trio, "
        "which leave it the other way at 0.001 m/s. Both ends of the Froude range hit the "
        "same wall, and a healthy "
        "run terminates on a turning point or a boundary hundreds of steps earlier.",
    ),
    Target(
        row="258b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe runs 14 steps past surface contact before it stops",
        source="case31's surface_on at output interval 1",
        measure=_surface_overshoot_ratio,
        reference=1.0859,
        tolerance=0.002,
        unit="dilution at the stop over dilution at contact",
        note="⭐⭐ **What survives row 258 once the checkbox is accounted for.** At interval 1 "
        "contact is bracketed to a single step -- `|Depth| - P-dia/2` crosses zero between 260 "
        "(+0.0080 m) and 261 (-0.0480 m) -- while the banner and the last row are both at **275**, "
        "by which point the plume edge is 0.7285 m through the free surface and the printed "
        "dilution has climbed from 156.331 to 169.754. The 14-step count is asserted rather than "
        "returned, because the claim is the pair. ⚠️ **Nothing marks 275**: not the "
        "overshoot depth, not the diameter, not the dilution -- the same shape as row 191b's "
        "merging banner lagging its trigger by 0-54 steps, in a solver whose step controller "
        "targets 2 % mass growth per step. ⚠️ The exe's error, not ours, and the residue "
        "of what was once a **40 %** headline: row 258's gap was a `stop at surface` mismatch "
        "(row 104), and matched, the trajectories agree to 1.9 %. What is left is an order of "
        "magnitude smaller and genuinely unexplained.",
    ),
    Target(
        row="4",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The shipped trace traps, then merges, then surfaces -- in that order",
        source="upstream/Example_project, banners at steps 255 / 260 / 275",
        measure=_golden_trace_event_order,
        reference=0.0,
        tolerance=0.0,
        unit="banners not where the ledger says",
        note="The **ordering** is the finding: the plume traps *before* it merges and merges "
        "before it surfaces, which is not the order anyone would assume, and rows 51, 63 and 191 "
        "all rest on the merge banner meaning what it says here. ⚠️ **Not a comparison with our "
        "solver, and it cannot be** -- the shipped trace prints no `Time` column, only Dilutn, "
        "P-dia, x-posn, y-posn and Depth, so there is no axis to sample a trajectory at. That is "
        "also why row 5 is retired rather than measured. What this guards is the archive and the "
        "reader: if the file were replaced or the banner parser regressed, the ordering those rows "
        "depend on would move silently.",
    ),
    Target(
        row="19",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01's two depth extrema, at the exe's own printed times",
        source="case01, -1.081 m at step 265 and -1.726 m at step 380",
        measure=_case01_depth_extrema_error,
        reference=0.0235,
        tolerance=0.006,
        unit="m, worst of the two",
        note="Ours gives -1.0714 and -1.7025 sampled at the same times. ⚠️ **The "
        "tolerance is not the printed resolution.** `Depth` prints three decimals, so 0.0235 m is "
        "twenty-three times what the trace can resolve -- this is our trajectory error, not a "
        "rounding comparison, and treating it as one would make the row look far stronger than it "
        "is. The bound comes from the drift row 17 already records, and both extrema sit in the "
        "oscillating stretch where that drift lives.",
    ),
    Target(
        row="20",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case01's four turning points, in kind, order and time",
        source="case01, reversal 270 / trap 335 / reversal 380 / trap 420",
        measure=_case01_turning_point_error,
        reference=0.0855,
        tolerance=0.02,
        unit="worst relative time error",
        note="The **sequence** is what the row records -- reversal, trap, reversal, trap -- and "
        "our solver reproduces it exactly in kind and order. The measurement asserts that and "
        "*then* returns the timing residual, because a residual computed against the wrong kind of "
        "event is a number about nothing. ⚠️ Worst on the **first** trap and best on the second "
        "(0.30 %): the trajectory arrives at each turning point slightly early and the error does "
        "not accumulate, which is row 17's late drift seen on the time axis instead of the "
        "dilution axis. Row 183 measures the same effect archive-wide as a mean 3.4 %.",
    ),
    Target(
        row="26",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case02's four turning points, in kind, order and time",
        source="case02 via case03's project, reversal 120 / trap 360 / reversal 390 / trap 410",
        measure=_case02_turning_point_error,
        reference=0.0889,
        tolerance=0.02,
        unit="worst relative time error",
        note="Row 20's measurement on the case the **unit flag** changes: case02 is case01's "
        "project read as MGD rather than m3/s, so it runs at 23x the flow (row 28), and the same "
        "four-point sequence comes back reproduced exactly in kind. ⚠️ The worst residual "
        "is on the **first** reversal, at t = 1.78 s -- a 0.16 s absolute error on the earliest "
        "event in the trace, where a relative measure is at its harshest; the three later points "
        "run 1.53-3.61 %. ⚠️ case02 has no `.prj`; case03's describes it, which is row "
        "24's finding and covers case02, case03 and case04 alike.",
    ),
    Target(
        row="27",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="case02's final flux-averaged dilution",
        source="case02, 562.633 at the last printed step",
        measure=_case02_endpoint_error,
        reference=0.0312,
        tolerance=0.008,
        unit="relative error",
        note="Ours reaches 545.103 against 562.633, and 0.5507 m against 0.558 m on the diameter "
        "-- 3.12 % and 1.30 %. ⚠️ **Worse than row 24's 0.858 % whole-trace figure, and it should "
        "be**: this is the *endpoint* of a long oscillating trace, the window row 17 measures at "
        "1.73 % against 0.46 % in the jet. Quoting a whole-trace mean here would understate what a "
        'reader asking "how close is the final dilution" actually gets, which is the same '
        "correction Phase 7's first act made to row 17.",
    ),
    Target(
        row="52",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Merging suppresses entrainment across the transition",
        source="case05, dilution growth per five steps either side of the banner",
        measure=_merging_suppression_ratio,
        reference=0.808,
        tolerance=0.01,
        unit="ratio, after over before",
        note="The observation the whole merging closure was built to reproduce: crossing the "
        "banner, dilution growth drops from **2.158 to 1.744** per five steps with nothing else in "
        "the run changing, because neighbouring plumes have occluded part of each element's "
        "surface. ⚠️ **Measures the exe, not us** -- case05 has no `.prj`, so there is no "
        "model run to compare against; what this pins is the size of the effect rows 157 and 177 "
        "then measure the closure against. A single step either side rather than a window, because "
        "the suppression **deepens** as the overlap does -- which is what case40 took to `d/L` 4 "
        "and where the closure fails (row 157b).",
    ),
    Target(
        row="62",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="A positively buoyant plume surfaces and the run continues",
        source="case06, surfaces at 260 and runs to a turning point at 356",
        measure=_surfacing_run_continues,
        reference=0.0,
        tolerance=0.0,
        unit="banners not where the ledger says",
        note="Reaching the surface does **not** end the run: the exe prints `Plume surfaces` at "
        "260 and keeps integrating through a reversal at 280, a trap at 320 and a final reversal "
        "at 356. ⭐ That is what makes `stop at surface` a **termination** switch rather than a "
        "physics option (row 104), and it is the behaviour row 258 needed in order to read "
        "case13's 40 % endpoint gap as a settings mismatch rather than a closure error. ⚠️ "
        "Measures the exe's trace; case06 has no `.prj`.",
    ),
    Target(
        row="63",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Trapping can precede merging",
        source="case06, trap at 195 and merge at 210",
        measure=_trapping_precedes_merging,
        reference=0.0,
        tolerance=0.0,
        unit="banners not where the ledger says",
        note="Trapping and merging are independent benchmarks and either can come first -- here "
        "the plume reaches neutral buoyancy **15 steps before** its neighbours touch it. ⭐ **This "
        "is the observation that retired half of row 191's original reading**: the "
        'limiting-spacing rule had been recorded as "checked at trapping" because case22 and '
        "case23 happened to have the trap and the diameter crossing on the same step, and case06 "
        "shows the two benchmarks were never tied. case30 then separated them directly. ⚠️ "
        "Measures the exe's trace; case06 has no `.prj`.",
    ),
    Target(
        row="71",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="A dense plume traps on buoyancy rather than reaching the seabed",
        source="case07, deepest -3.203 m against a seabed at 17 m",
        measure=_dense_plume_trap_depth,
        reference=13.797,
        tolerance=0.01,
        unit="m of clearance",
        note="A 45 psu effluent into a ~31 psu ambient sinks, and it turns at **-3.203 m** "
        "carrying a dilution of 211.856, against a seabed at 17 m (port depth 2 plus 15 m "
        "elevation). ⚠️ **The margin is large and the row's phrasing understates it** -- \"no "
        'bottom hit" reads like a near miss, and 13.8 m of clearance is not one. What makes '
        "case07 valuable is the **inversion**: a sinking plume runs its trapping and reversal "
        "benchmarks in the opposite vertical order, which is the case row 183's ordinal switch had "
        "to survive. ⚠️ Measures the exe's trace; case07 has no `.prj`.",
    ),
    Target(
        row="90",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The shoreline is inert even with its checkbox ticked",
        source="case12, the only archived run with the box enabled",
        measure=_shoreline_checkbox_inert,
        reference=5.389,
        tolerance=0.001,
        unit="m, largest y reached",
        note="case12's plume walks straight through the shoreline it was told about: the largest "
        "`y-posn` is **5.389 m**, well past the boundary the feature is supposed to represent, "
        "with no reflection and no advisory. ⭐ **Stronger than row 72, and for a specific "
        "reason** -- row 72 shows the shoreline *vector* is ignored by comparing case08 with "
        "case05, while this shows the *checkbox* is too, which is the half a reader would assume "
        "does the work. Together they are the inert-shoreline item on the SSMC list. ⚠️ Still an "
        "inference from **one** run rather than a controlled pair: §7.1's outstanding ask is "
        "case12 rerun with the box cleared, which would make it airtight. Tolerance is the printed "
        "resolution, since this reads a column rather than modelling one.",
    ),
    Target(
        row="144",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Inputs inferred from a trace alone are confirmed by the project that arrived later",
        source="case18's test21.prj against four values read from the trace before it existed",
        measure=_trace_inference_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="values the project contradicts",
        note="Four inputs were read out of the trace before any project for case18 existed: port "
        "diameter 0.0127 m and total flow 0.005 m3/s from the two-decimal diffuser echo (row 141), "
        "the aspiration coefficient 0.1 from the measured Taylor entrainment (row 140), and the "
        "contraction coefficient 0.61 from the initial velocity. `test21.prj` arrived later and "
        "agrees with all four **exactly**. ⭐ Worth keeping executable rather than retiring as "
        "history: it is the evidence that trace-only inference is sound, and seven of the "
        "archive's projects are still missing (case02, case05-07, case12, case20, case21), so the "
        "method is load-bearing rather than a past convenience.",
    ),
    Target(
        row="157",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="test32 post-merge is 5.24 % under what ships -- a recorded divergence",
        source="case20's test32, post-merge dilution against the exe",
        measure=_merging_cost_at_moderate_overlap,
        reference=0.0524,
        tolerance=0.006,
        unit="post-merge dilution MARE",
        note="The four terms each lose a different share of surface, so this cannot be one scalar "
        "on `dm/dt` -- and merging also **breaks the Taylor/cylinder cancellation**, because those "
        "two halves carry different factors, so the closure reassembles them separately instead of "
        "using the pre-summed aspiration velocity. Reproducing that structure puts the post-merge "
        "trajectory at **5.24 %** against the unmerged control's 1.39 % (row 177). ⚠️ "
        "**Scoped to `d/L` <= 2.35** -- test32 is the deepest overlap case20 reaches, and row 157b "
        "is where it stops. Tolerance is the control's own margin, 0.3 pp, not a fitted band.",
    ),
    Target(
        row="157b",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Past `d/L` ~ 4 the merging closure is 29 % wrong -- a recorded divergence",
        source="case40's test58 at a 0.25 m spacing, against its own 2 m control",
        measure=_deep_overlap_penalty,
        reference=0.106,
        tolerance=0.02,
        unit="post-merge dilution MARE",
        note="⚠⚠ **A recorded divergence, not an achievement**, and the largest open "
        "accuracy problem in the near field. case40's test58 reaches `d/L` **4.05**, nearly double "
        "case20's 2.35, and the closure that holds to 1.01 % at shallow overlap is **28.8 %** "
        "here. The *unmerged* control on the same geometry is 2.10 % (row 157c), so this is "
        "merging's error and not the 2 psu regime's. ⚠️ Same defect as row 186 seen on "
        "dilution instead of diameter: entrainment is under-suppressed, the element over-inflates, "
        "the dilution follows. ⭐ **Predicted 15-25 % before the run**; 28.8 % is outside that "
        "range, in the direction of the defect being worse, and is recorded as a miss.",
    ),
    Target(
        row="157c",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The unmerged control on the same geometry, so the divergence is merging's",
        source="case40's test56 at a 2 m spacing, which never merges",
        measure=_deep_overlap_control_error,
        reference=0.0210,
        tolerance=0.005,
        unit="dilution MARE",
        note="The control that makes row 157b attributable. A **2 psu** effluent into a 31 psu "
        "ambient is outside anything this closure was tuned on, so some of test58's error belongs "
        "to the regime rather than to merging; this measures how much. 2.10 % against 28.8 % says "
        "the rest is merging's. ⚠️ Without this number row 157b would be unreadable -- a "
        "29 % error means nothing until you know what the same case does without merging at all.",
    ),
    Target(
        row="177",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The unmerged control's own error, which is what makes row 157 readable",
        source="case20's test31, the same case at a spacing wide enough never to merge",
        measure=_unmerged_control_error,
        reference=0.0139,
        tolerance=0.004,
        unit="post-merge-window dilution MARE",
        note="⚠⚠ **This row read 'merging costs no accuracy' until 2026-08-21.** "
        "test31 is that control -- identical to test32 but for the spacing -- "
        "and both runs carry the archive's common late-trajectory drift, so the *difference* is "
        "what merging owns. Merging comes out **below** the control: 1.01 % against 1.39 % over "
        "the same steps. ⚠️ Scoped exactly as row 157 is: this is shallow overlap, and "
        "row 157b is the same comparison at `d/L` 4.05, where it fails.",
    ),
    Target(
        row="178",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Eq 56 is implicit -- `phi` at the merged half-height, not at `b_r`",
        source="case20's test32, eq 56 read explicitly at `b_r` instead",
        measure=_explicit_inflation_penalty,
        reference=0.0575,
        tolerance=0.005,
        unit="post-merge dilution MARE of the control",
        note="`phi` is set by the element's *actual* half-width -- the merged `b` eq 56 solves "
        "for -- not by the round-equivalent `b_r`. Measured straight off test32, where `b_r` "
        "follows from the thickness law and `b` is the printed diameter: at step 410 the exe's own "
        "inflation is **1.3106**, `phi(b)` gives 1.3131 and `phi(b_r)` gives 1.1652. ⚠️ "
        "Reading it explicitly under-inflates by 12 % and leaves the merged diameter at its "
        "*unmerged* value -- 2.059 m against the exe's 2.351 m -- and costs **3.22 %** post-merge "
        "against 1.01 %. The reference is the control's error, so the page shows both numbers.",
    ),
    Target(
        row="179",
        agreement=Agreement.REPRODUCES_DEFECT,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe reproduces UM3's `arctan` bug in `phi`",
        source="case20's test32, eqs 51-54 on the true `arccos` instead",
        measure=_true_geometry_penalty,
        reference=0.0817,
        tolerance=0.005,
        unit="post-merge dilution MARE of the control",
        note="⚠️ UM3 computes `phi = arctan(sqrt((b^2 - s^2)/s))`, with the division "
        "*inside* the radical. That is dimensionally inconsistent and agrees with the real "
        "`arccos(s/b)` only when `s = 1 m` exactly; the Visual Plumes migration flags it in place "
        "as an original-code artefact rather than repairing it. The exe has it too: with the bug, "
        "post-merge dilution is **1.01 %**; with the true geometry, **4.04 %**. So the buggy form "
        "is the default and `faithful=False` opts out -- the same treatment the effluent-only unit "
        "conversion gets in `chem`. ⚠️ This is the one place the port deliberately "
        "reproduces someone else's arithmetic mistake, because parity with the exe is the point.",
    ),
    Target(
        row="180",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe is inconsistent between its own two overlap angles",
        source="case20's test32, eq 56 put on the buggy angle as well",
        measure=_inconsistent_angle_penalty,
        reference=0.0603,
        tolerance=0.006,
        unit="post-merge dilution MARE of the control",
        note="⚠️ **The least comfortable finding in the merging block.** Eqs 51-54's "
        "decrements match the buggy `arctan`; eq 56's inflation matches the **true** `arccos`. "
        "Making eq 56 buggy too -- the self-consistent reading anyone would prefer, and the one a "
        "careful reimplementation would pick -- is the **worst** of the four combinations at "
        "4.64 %, against 1.01 % for the mixed form the exe actually uses. ⚠️ Not a "
        "reading we would have chosen. Each half was measured separately, against its own control "
        "(rows 178 and 179), and each is reproduced as found. The four combinations run "
        "1.01 / 3.22 / 4.04 / 4.64 %, so the exe's is the best by a margin no tolerance hides.",
    ),
    Target(
        row="181",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The merge spacing uses the plume's **instantaneous** heading",
        source="case40's five brackets -- three angles at one spacing, two spacings square on",
        measure=_oblique_trigger_misses,
        reference=0.0,
        tolerance=0.0,
        unit="worst distance outside a bracket",
        note="⭐⭐ **The controlled test this row never had.** Its 85/30/0 degree evidence "
        "came from three *different* cases, so geometry moved along with the angle and no single "
        "run isolated the law. case40 fixes the spacing at 0.75 m and moves only the discharge "
        "azimuth -- 85, 75, 65 degrees against a 90 degree current -- with two square-on spacings "
        "for the ends. Resolving `psi` against the plume's live heading lands **inside all five "
        "brackets with no fitted constant**, because merging fires *mid-turn*, while the plume "
        "still presents most of its aspect to its neighbours. ⚠️ Zero tolerance because "
        "the quantity is already a distance outside a bracket: the brackets are one output step "
        "wide, about 1 %, and row 181b shows the static law misses them.",
    ),
    Target(
        row="181b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The static `|sin psi|` law is excluded by the same five brackets",
        source="case40's five brackets against the fully-turned-over angle",
        measure=_static_spacing_law_misses,
        reference=0.0524,
        tolerance=0.005,
        unit="worst distance outside a bracket",
        note="The control that makes row 181 mean something: five hits prove nothing unless a "
        "plausible alternative misses. A static law evaluated at the fully-turned-over angle "
        "cannot express that merging fires mid-turn, so it sits **below** every oblique bracket -- "
        "by 1.1 % at 75 degrees and **5.2 %** at 65, against brackets about 1 % wide. ⚠️ "
        "It agrees at 90 degrees by construction, which is why the square-on runs alone could "
        "never have separated the two laws, and why the archive needed an angle sweep at fixed "
        "geometry to settle it. Retires row 118's fitted ellipse for a second time, independently.",
    ),
    Target(
        row="182",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The merge trigger tracks the spacing, as predicted before the runs existed",
        source="case21's test34 and test35 against case16's test19, at a fixed 85 degree offset",
        measure=_spacing_prediction_misses,
        reference=0.0009,
        tolerance=0.0006,
        unit="worst distance outside a bracket",
        note="⭐ **A prediction, not a fit**: test34 and test35 were run *after* the numbers "
        "were written down. At one fixed offset a static law must predict a single value where the "
        "derived law predicts a curve, because a wider spacing means merging fires later, by which "
        "time the plume has turned further. Predicted 0.5991 / 0.6751 / 0.7750 at 2.0 / 1.5 / "
        "1.0 m against measured brackets of 0.5985-0.6015 / 0.6760-0.6800 / 0.7700-0.7780; the "
        "fitted ellipse is flat at 0.600 and is excluded by **13 %** and **23 %**. "
        "⚠️ **The reference is a near-miss, not zero.** test35 lands 0.0009 below its "
        "bracket -- 0.13 %, inside our own 1.0-1.2 % trajectory error on these runs, but a miss, "
        "and rounding it to a hit is how a validation suite stops meaning anything. Two clean hits "
        "and one near-miss. Row 181's five-bracket sweep on case40 is the independent evidence "
        "that it is noise rather than bias. ⚠️ Neither run has a `.prj`; both are "
        "rebuilt from test19's geometry with the spacing changed.",
    ),
    Target(
        row="264e",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Unbraked, our suppression level is 0.249 off the exe's -- a recorded divergence",
        source="the shipped closure against the exe, per spacing over the matched d/L window",
        measure=_unbraked_level_error,
        reference=0.249,
        tolerance=0.02,
        unit="mean |ours - exe| in suppression level",
        note="⚠️⚠️ **A recorded divergence, and it is the shipped default's, not a "
        "candidate's.** The control that makes row 264b's 0.088 mean something: without it 0.088 "
        "could be a good result or a poor one. Per spacing, ours against the exe: **+0.196** at "
        "0.75 m, **+0.224** at 0.50 m, **+0.326** at 0.25 m. ⭐ **All three the same sign**, every "
        "spacing under-suppressing, which is the runaway showing up in the *level* as well as in "
        "the trend -- and it is the shape a positive feedback makes. Row 264b's braked residual "
        "changes sign instead, which is why it is not the same defect made smaller. ⚠️ The "
        "reference is **recovered from** the exe's printed dilution by differencing, not printed: "
        "no build prints an entrainment rate. Both sides are reduced by the same code path "
        "(`_suppression_levels`) so the comparison is like with like.",
    ),
    Target(
        row="260",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe's suppression, pooled over three spacings, averages 0.60",
        source="case41's three 35 psu spacings against its 5 m unmerged control, 483 samples",
        measure=_merged_suppression_plateau,
        reference=0.596,
        tolerance=0.02,
        unit="merged entrainment rate over unmerged",
        note="⚠️⚠️ **Retracted as a *law* on 2026-08-21, kept as a measurement.** This read "
        "~~the law the merging closure has to hit, and it is a plateau rather than a decline~~ "
        "-- 0.606 over `d/L` 1.5-3, 0.586 over 3-6, 0.595 over 6-14, therefore a fixed ~40 % "
        "removed however deep the overlap gets. **The bins pool three spacings**, and only the "
        "0.25 m run has samples past `d/L` 5.5, so they compare different runs to each other. "
        "Per spacing the level is 0.766 / 0.568 / 0.580 (row 260d) and the flatness was three "
        "crossing curves cancelling. What this number still is, exactly: the pooled mean, "
        "reproducible to 0.02. What it is not: a suppression the exe applies. Rows 260d, 260e "
        "and 260f carry the corrected reading. ⚠️⚠️ "
        "**This refutes a prediction registered before the runs** -- the plan said the suppression "
        "would keep *falling* past `d/L` 2.2, to 0.4-0.5 at 3 and 0.3 or below at 4, extrapolated "
        "from case20's five coarse points. It does not fall at all. Recorded as a miss, and the "
        "third this defect has broken; every one has been wrong about the **shape** rather than "
        "the size. ⚠️ Measured as `d(ln D)/dt`, a rate per unit *time*, which is what takes the "
        "step controller out: the controller picks `dt` so each step gains ~2 % of mass, so a "
        "per-step gain reads 0.02 on anything not otherwise limited and carries no information. "
        "That is why a 35 psu effluent was needed -- case40's 2 psu run sat on the cap for 186 of "
        "255 steps.",
    ),
    Target(
        row="260b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The pooled average is flat in d/L -- which is the artifact, not the law",
        source="the same samples in three bins over a ninefold range of overlap",
        measure=_suppression_plateau_flatness,
        reference=0.020,
        tolerance=0.015,
        unit="largest gap between bin means",
        note="⚠️⚠️ **Kept because it is the evidence *for* the artifact, and its inference is "
        "retracted.** The bins do agree -- **0.606 / 0.586 / 0.595**, a spread of 0.020 against "
        "0.13 of scatter within any one of them -- and this was read as ~~what says the trend is "
        "flat rather than merely noisy~~. It says no such thing. The bins pool three spacings "
        "whose levels are 0.766 / 0.568 / 0.580 (row 260d) and whose trends run "
        "-0.020 / +0.125 / -0.028 (row 260f): **two of the three cross**, so averaging them "
        "within a `d/L` bin cancels the variation and manufactures flatness. ⭐ A flatness of "
        "0.020 over pooled bins is *consistent with* a flat law and is not evidence for one, "
        "which is the whole distinction -- and it is the same failure as the coverage fraction: "
        "correct arithmetic, wrong presentation. Row 260f is the controlled measurement.",
    ),
    Target(
        row="260c",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Our suppression crosses 1.0 near d/L 2 and then enhances entrainment",
        source="the same three runs and control, driven through our own closure",
        measure=_our_suppression_crossing,
        reference=1.99,
        tolerance=0.15,
        unit="d/L at which our ratio reaches 1.0",
        note="⚠️⚠️ **The mechanism behind rows 157b and 186, and it is a positive feedback.** Our "
        "closure suppresses correctly while the overlap is shallow and then crosses 1.0 at `d/L` ~ "
        "2, reaching 1.33, 3.34 and 2.82 on the three spacings -- so past that point we are "
        "**enhancing** entrainment where the exe removes 40 % of it. The loop is visible in the "
        "equations: eq 56 inflates the merged radius, a larger radius means larger Taylor and "
        "forced entrainment areas, more entrainment grows the mass, and eq 56 inflates the radius "
        "again. Nothing in the port opposes it. That is row 186's runaway seen as a rate instead "
        "of a length, and row 260 is the ceiling a fix has to impose. ⚠️ **Also a refuted "
        "prediction**: the plan said our closure would sit flat at 0.85-0.9 across the range. Both "
        "halves of that prediction were wrong, and both in the direction of the defect being "
        "worse. ⚠️ Measured inside the first 90 % of each of our integrations -- a gradient taken "
        "in the last steps of a diverging run is noise, not a rate.",
    ),
    Target(
        row="264",
        phase=5,
        evidence=Evidence.INTERNAL,
        claim="The runaway is an asymmetry in the decrement radius, and braking it gives a plateau",
        source="case41's three 35 psu spacings through our closure, against our own 5 m control",
        measure=_confined_brake_flatness,
        reference=0.043,
        tolerance=0.015,
        unit="largest gap between our three bin means",
        note="⭐⭐⭐ **The mechanism behind rows 157b, 186 and 260c, located in the "
        "code rather than in a coefficient.** `merging_factors` takes `phi` at the "
        "round-equivalent `b_r`; every entrainment area downstream is built from the "
        "**confined** `b` of eq 56. So "
        "eq 56's inflation factor `b/b_r` enters the entrainment with nothing opposing it. Move "
        "all four decrements to the confined half-height and the divergence becomes a plateau: "
        "**0.649 / 0.686 / 0.643** over `d/L` 1.5-3, 3-6 and 6-14, a spread of 0.043, against a "
        "curve that previously crossed 1.0 at 2.37 and reached 3.34. ⭐ **It had to be "
        "structural**, and this is why it is: deep in the overlap `a_T(b) -> (2/pi)(s/b)`, so "
        "`a_T * pi * b` converges to a **constant** and the growth area stops depending on `b` "
        "at all. At `b_r` the same product diverges linearly, 1.494 at `d/L` 1.05 to **31.35** at "
        "20 against 1.481 to **2.000** (normalised by `L`). ⚠️ That constant is the slab "
        "width `2s = L` only under the true `arccos`; under the exe's `arctan` it is `2 sqrt(s)`, "
        "which is not a width -- the angle bug survives into the asymptote, and both saturate, "
        "which is all the brake needs. That is what no constant could "
        "do: multiplying `db/dt = k b^2` by one only reschedules `t_c = 1/(k b_0)`. ⚠️ "
        "**`internal`, because no reference exists for this quantity** -- the exe prints a "
        "trajectory, not an entrainment rate, so the ratio is our merged run over our own "
        "unmerged control and it measures our closure rather than agreement. Row 264b is the "
        "nearest thing to a comparison, against the 0.596 row 260 recovers the same way, and "
        "row 264c is the cost. ⚠️ **Not the "
        "default.** `ConfinedDecrements.NONE` is what the port ships; this is a candidate recorded "
        "with its cost.",
    ),
    Target(
        row="264b",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Braked, the level error falls to 0.088 from 0.249 -- a recorded divergence",
        source="ours against the exe per spacing, over the d/L window all three runs cover",
        measure=_braked_level_error,
        reference=0.088,
        tolerance=0.015,
        unit="mean |ours - exe| in suppression level",
        note="⭐⭐ **Restated on 2026-08-21, and the pooled version had flattered the brake "
        "exactly as row 260 flattered the exe.** It read ~~the braked plateau sits 0.06 above the "
        "exe's, 0.660 against 0.596~~ -- which averaged a **+0.145** and a **-0.071** into an "
        "0.064 offset. Per spacing, at matched overlap: ours braked 0.695 / 0.617 / 0.725 against "
        "the exe's 0.766 / 0.568 / 0.580, so **-0.071 / +0.049 / +0.145**. Mean absolute error "
        "**0.088**, against **0.249** unbraked (row 264e) -- better at every spacing, 2.8x on the "
        "mean. ⚠⚠ **But the residual is not an offset: it changes sign.** The brake "
        "*over*-suppresses at the widest spacing and *under*-suppresses at the tightest, a signed "
        "range of 0.216, so there is no constant left to correct. That is row 264c's conclusion "
        "reached from the other end -- the two decrement radii are each right in a different "
        "regime, and one choice cannot be right throughout. ⚠️ **And ours is too "
        "uniform**: our braked spread across spacings is 0.107 against the exe's 0.198, so "
        "whatever the exe responds to, we respond half as strongly. A different defect from the "
        "runaway, invisible while the runaway dominated. ⚠️ The reference is **recovered "
        "from** printed dilution by differencing, not printed -- no build prints an entrainment "
        "rate -- and both sides go through `_suppression_levels`, so it is like with like.",
    ),
    Target(
        row="264c",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The brake costs 4.2 pp at moderate overlap, which is why it is not the default",
        source="case20's test32 post-merge dilution, braked, against the exe's printed trace",
        measure=_retired_default_on_test32,
        reference=0.0101,
        tolerance=0.003,
        unit="post-merge dilution MARE",
        note="⚠️⚠️ **The cost, and it refutes the prediction that justified "
        "trying the brake.** The argument was that the confined angle barely moves at shallow "
        "overlap -- 1.481 against 1.494 on the growth-area product at `d/L` 1.05 -- so row 157's "
        "1.01 % would survive. **It does not.** test32 reaches `d/L` **2.35**, where the same "
        "product reads 1.862 against 2.738, a 32 % difference, and the post-merge trajectory "
        "degrades to **5.24 %** -- worse than row 177's unmerged control at 1.39 %, which is the "
        "bar row 157 had to clear. Our merged diameter goes from 1.125x the exe's to **0.965x**: "
        "the brake turns a slight over-inflation into a slight under-inflation. Recorded as a miss "
        "with the prediction named, and it is the *fifth* time this defect has broken one. "
        "⭐⭐ **What it establishes is more useful than what it cost -- and case42 renamed "
        "the axis.** This was read as a *moderate-overlap* failure. It is not: row 267 has the "
        "brake reaching **0.98 %** at `d/L` up to 3.9, deeper than test32 ever goes. What "
        "differs is **where merging began** -- test32 merges at dilution **138.2** against "
        "case42's 56.1, and the exe suppresses less at high onset dilution (row 266) where our "
        "brake gives a flat 0.65. So the axis is **onset dilution**, not overlap depth. "
        "Each reading is "
        "right in its own regime -- `b_r` out to `d/L` ~ 2.4 and diverging past it, the confined "
        "`b` past ~3 and over-suppressing before it -- so the exe evaluates **neither**, and the "
        "open question narrows from 'find the brake' to 'find the transition'. ⚠️ Which "
        "is not a licence to interpolate: a blend with a tunable crossover is a coefficient again, "
        "and the finite-time-singularity argument is what rules those out.",
    ),
    Target(
        row="264d",
        phase=5,
        evidence=Evidence.INTERNAL,
        claim="Braking the growth term alone is not enough -- the refuted candidate",
        source="the same three runs with only the growth decrement moved to the confined radius",
        measure=_growth_only_brake_still_diverges,
        reference=4.88,
        tolerance=0.3,
        unit="d/L at which our braked ratio still reaches 1.0",
        note="⛔ **Refuted, and it was the candidate the mechanism argued for.** The growth "
        "area `pi b db` is the only one quadratic in the radius -- `A_T = 2 pi b h` and "
        "`A_cyl = 2 b h` are linear -- so it is the whole of the finite-time singularity, and "
        "braking it alone should have removed the blow-up while leaving untouched the Taylor and "
        "cylinder decrements row 157 measured. It removes the *singularity*: the runs stop dying "
        "early (test67 reaches 166.9 s against 72.8 s) and row 186's ratio falls 11.93x -> 2.29x. "
        "But the suppression still climbs -- **0.760 / 0.857 / 1.005** -- and still crosses "
        "1.0, at `d/L` 4.88 rather than 2.37. ⭐ **Why, and it is what makes row 264 "
        "necessary**: the "
        "Taylor term is linear in `b` but its decrement is taken at `b_r`, so "
        "`a_T(b_r) A_T ~ (2 s h)(b/b_r)` and the inflation factor survives there too. Braking "
        "growth alone downgrades a finite-time singularity to an unbounded **linear** enhancement "
        "-- better, and still wrong. Every term built on the confined radius needs a decrement "
        "evaluated at it. ⚠️ Strictly dominated by row 264 on the deep runs as well: "
        "post-merge 23.3 / 24.7 / 28.3 % on test63 / test66 / test67 against 4.3 / 4.8 / 6.0 %, "
        "and 113 % on test64. Kept because the reasoning was sound and a measurement is what "
        "disposed of it. ⚠️ **`internal`: no reference exists for an entrainment rate**, "
        "for the reason row 264 gives. Ours against our own control is all a refutation needs, "
        "because the candidate fails on its own terms rather than against the exe.",
    ),
    Target(
        row="260d",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe's suppression level differs by 0.198 between spacings at matched overlap",
        source="case41's three 35 psu runs, per spacing over the d/L window all three cover",
        measure=_exe_suppression_level_spread,
        reference=0.198,
        tolerance=0.02,
        unit="spread in suppression level",
        note="⚠️⚠️ **The correction to row 260, and it says the plateau at 0.60 is a "
        "pooling artifact.** Row 260 bins 483 samples from three spacings by `d/L` and reads "
        "0.606 / 0.586 / 0.595. But only the 0.25 m run has samples past `d/L` 5.5, so those bins "
        "compare *different runs to each other* rather than one run across overlap depths. Reduced "
        "per spacing over the window all three actually reach: **0.766** at 0.75 m, **0.568** at "
        "0.50 m, **0.580** at 0.25 m -- a **0.198** spread, ten times row 260b's 0.020, against "
        "standard errors of 0.001-0.022. The pooled bins looked flat because the three curves "
        "cross. ⛔ So *'the exe removes a fixed ~40 % of the entrainment'* does not hold: it "
        "removes 23 % at one spacing and 43 % at another. ⭐ What survives of row 260 is the "
        "**shape** -- row 260f is the controlled version of that claim. ⚠️⚠️ And the spread is "
        "**not attributable to the spacing**; row 260e is why.",
    ),
    Target(
        row="260e",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="At matched overlap the three runs are 8.1x apart in time, so row 260d is confounded",
        source="mean elapsed time in the matched d/L window, widest spacing over tightest",
        measure=_matched_overlap_confound,
        reference=8.11,
        tolerance=0.3,
        unit="ratio of mean elapsed times",
        note="⚠️⚠️ **Why row 260d's 0.198 cannot be called a spacing dependence, and it is "
        "the third time this project has read one lever while another moved with it** -- after the "
        "Froude reading of the merging lag and port depth after it. Spacing *determines when* a "
        "given `d/L` is reached: a tightly spaced plume overlaps almost at once, a widely spaced "
        "one only after it has grown. So at matched overlap the runs sit at **84.9 / 43.2 / "
        "10.5 s** and dilutions of **182.8 / 101.8 / 45.5** -- 8.1x in time and 4.0x in dilution. "
        "Plume depth *is* comparable (-1.2 to -1.8 m), so it is not that. Spacing, elapsed time "
        "and accumulated dilution would each fit the 0.198 equally well and case41's design ties "
        "them together. ⛔ **The run this row first proposed cannot work.** It asked for two "
        "spacings matched by trading spacing against effluent *salinity*. Salinity is far too "
        "weak: over 20-48 psu the dilution at a fixed diameter moves **17 %** where **41 %** is "
        "needed -- and it is structurally impossible that way, since reaching `d/L` = 1 at a "
        "wider spacing always needs a larger diameter and so more dilution, monotonically, so no "
        "effluent property can equalise two spacings. ⭐ **The port is the lever**: dilution at "
        "`d = L` goes as `(L/d0)^2`, so scaling the port diameter with the spacing holds the "
        "onset dilution fixed and scaling the flow by the port *area* holds the exit velocity "
        "with it. At 1.5x it lands within **1.9 %** of test63's onset dilution by construction. "
        "Queued as `reference_cases/pending/matched_dilution_{merged,control}/`, with test63 and "
        "test68 as the other arm so only one new run is needed. ⚠️ Until it comes back, the "
        "honest statement is that the level varies by 0.198 across three runs and the cause is "
        "unidentified.",
    ),
    Target(
        row="260f",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Within a single run the suppression does not fall off as the overlap deepens",
        source="the per-run slope in d/L over 1.5-3.7, steepest downward of the three",
        measure=_suppression_steepest_decline,
        reference=-0.0284,
        tolerance=0.015,
        unit="d(suppression)/d(d/L), steepest decline",
        note="⭐ **The controlled version of row 260b, and what survives the pooling "
        "correction.** 260b asked the right question -- does the suppression fall off as the "
        "overlap deepens -- of a pooled average that could not answer it. Asked per run over the "
        "same window: **-0.020** at 0.75 m, **+0.125** at 0.50 m, **-0.028** at 0.25 m. Two are "
        "flat to within 0.03, about 0.06 across the whole window and under 10 % of the level, and "
        "the third *rises*. So nothing falls off, which refutes the pre-run prediction (0.4-0.5 at "
        "`d/L` 3, below 0.3 at 4) on evidence that actually bears on it -- where row 260 refuted "
        "it on evidence that did not. ⚠️ **The 0.50 m run's +0.125 is unexplained** and is the "
        "largest anomaly left here: it climbs 0.53 -> 0.71 across the window, on the most-sampled "
        "of the three runs (115 points), so it is not a small-sample effect. ⚠️ Pinned as the "
        "steepest *decline* because the claim is a bound -- a mean over one rising and two flat "
        "runs would hide a decline in the one that fell.",
    ),
    Target(
        row="265",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The matched-dilution design lands within 1.6 % of its target, by construction",
        source="case42's onset dilution 56.10 against case41 test63's 57.0",
        measure=_matched_dilution_design_gap,
        reference=0.0154,
        tolerance=0.035,
        unit="fractional gap in onset dilution",
        note="⭐⭐ **The validity gate for rows 266-267, registered at 5 % before the run.** The "
        "experiment only means anything if its two arms begin merging at the same accumulated "
        "dilution; they do, at **56.10** against **57.0**. ⛔ **Row 260e's own proposal could not "
        "have got here.** It asked to match two spacings by trading spacing against effluent "
        "*salinity*: over 20-48 psu the dilution at a fixed diameter moves **17 %** where 41 % was "
        "needed, and it is structurally impossible that way, because reaching `d/L` = 1 at a wider "
        "spacing always needs a larger diameter and so more dilution, monotonically. ⭐ **The port "
        "is the lever and it is arithmetic, not a fit**: the dilution at `d = L` goes as "
        "`(L/d0)^2`, so scaling the port diameter by the spacing's own 1.5 holds the onset "
        "dilution "
        "fixed, with the flow scaled by the port *area* to hold the exit velocity. Predicted 55.1 "
        "before the run. Tolerance is the registered gate, not a band around the answer.",
    ),
    Target(
        row="266",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe's merged suppression is set by the trajectory stage, not by the spacing",
        source="case42's first suppression bin against test63's, its dilution-matched twin",
        measure=_suppression_follows_dilution,
        reference=0.006,
        tolerance=0.02,
        unit="gap in the d/L 1.5-2.0 suppression bin",
        note="⭐⭐ **The discriminator, and it answers -- this is what rows 260d and 260e were "
        "left open for.** case42 shares its *spacing* with case41's test65 (0.75 m) and its *onset "
        "dilution* with test63 (56.1 against 57.0), so whichever it resembles is the driver. It "
        "tracks **test63**: first bin **0.536** against 0.530, **0.006** apart, where test65 at "
        "the "
        "same spacing sits **0.152** away -- twenty-five times further, against standard errors of "
        "0.008 and 0.006. Row 266b pins the trend, which agrees in sign with test63 and disagrees "
        "with test65. ⭐ So row 260d's 0.198 spread is a **trajectory-stage** effect and the "
        "spacing is not the driver: where a run is along its trajectory when merging begins, "
        "measured as the dilution accumulated by then, sets the suppression it applies. ⭐ It also "
        "gives row 260f's anomaly a companion -- test63's +0.125 trend stood alone and now "
        "reproduces at a different spacing and a different port with matched dilution, so it "
        "belongs to the low-dilution regime rather than to the 0.5 m spacing.",
    ),
    Target(
        row="266b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="And the trend agrees in sign with the dilution-matched run, not the spacing-matched",
        source="case42's suppression slope in d/L over 1.5-3.7",
        measure=_suppression_trend_follows_dilution,
        reference=0.147,
        tolerance=0.03,
        unit="d(suppression)/d(d/L)",
        note="Row 266's control, and the half a coincidence of levels cannot explain. A 0.006 gap "
        "in one bin could be luck; a trend of the same sign and magnitude as the dilution-matched "
        "run -- **+0.147** against test63's +0.125 -- against the *opposite* sign at the matched "
        "spacing (test65, -0.020) cannot be. ⚠️⚠️ **And the prediction registered for this "
        "run was framed on the wrong statistic.** The discriminator was written as the "
        "window-averaged **level**: '~0.568 means dilution, ~0.766 means spacing, outside "
        "0.55-0.78 "
        "means neither'. It came out at **0.659** -- 0.091 from one and 0.107 from the other, near "
        "enough equidistant to settle nothing, because case42's rising trend carries its later "
        "bins "
        "into test65's range. The bins and the trend settled it instead. ⛔ **That is a smaller "
        "copy of the mistake rows 260 and 260b were retracted for**: registering a pooled average "
        "for a quantity just shown not to be one number. The physics was right and the statistic "
        "was not, and it is recorded as a miss on the framing so the next names a shape.",
    ),
    Target(
        row="267",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The confined-decrement brake reaches 0.98 % post-merge on a case it never saw",
        source="case42's merged run under `ConfinedDecrements.ALL`, at the exe's printed times",
        measure=_brake_out_of_sample,
        reference=0.0098,
        tolerance=0.004,
        unit="post-merge dilution MARE",
        note="⭐⭐⭐ **The brake validated out of sample, and the strongest evidence for it.** "
        "`ConfinedDecrements.ALL` was built against case20 and case41 and had never seen this "
        "geometry -- a 1.5x-scaled port at a matched onset dilution. **0.98 % post-merge is row "
        "157's shallow-overlap accuracy, reached at `d/L` up to 3.9**, against the shipped "
        "default's **35.53 %** on the same rows (row 267b): a **36x** reduction. The diameter "
        "ratio "
        "falls from 5.396x to **1.118x** and the run ends at 187.7 s against the exe's 182.7 s, "
        "where the default dies at 176.9 s. ⚠️ Our *internal* prediction was exact -- 0.835 "
        "unbraked and 0.652 braked on the suppression level, registered before the run and "
        "reproduced to three decimals -- so what the port cannot predict is the exe's level, which "
        "is row 264b. ⚠️ Tolerance is row 157's own 0.3 pp margin doubled, since this is one case "
        "rather than a sweep.",
    ),
    Target(
        row="267b",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The shipped default is 35.53 % out on the same rows -- a recorded divergence",
        source="case42's merged run under `ConfinedDecrements.NONE`, the same comparison",
        measure=_brake_out_of_sample_control,
        reference=0.3553,
        tolerance=0.03,
        unit="post-merge dilution MARE",
        note="⚠️⚠️ **A recorded divergence, and the largest single gap the default still "
        "carries.** The control that makes row 267's 0.98 % mean something: without it, 0.98 % "
        "could be a good result or an easy case. The shipped closure is **36 times** worse on the "
        "same rows, its element reaches **5.396x** the exe's diameter, and its run dies 6 s before "
        "the exe's last row. ⭐ **And it identifies the brake's own remaining defect.** The brake "
        "gives ~0.65 flat where the exe runs 0.53 to 0.77 with onset dilution (row 266), so the "
        "missing variable in row 264b's 'ours is too uniform' is **dilution at merge onset** -- "
        "which is also why row 264c's cost exists: case20's test32 merges at dilution **138.2**, "
        "two and a half times case42's, so the exe suppresses less there and a flat 0.65 "
        "over-suppresses. Row 264c's 'fails at moderate overlap' is corrected to 'fails where "
        "merging begins late'.",
    ),
    Target(
        row="268",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The multiport limiting-spacing rule holds and its banner lag does not",
        source="case42's 5 m control: banner at step 367, port-depth crossing at 335",
        measure=_multiport_limiting_spacing_lag,
        reference=32.0,
        tolerance=0.0,
        unit="steps from the port-depth crossing to the banner",
        note="⚠️ **Row 261 holds and its lag does not.** case41's test68 fired **6** steps after "
        "the diameter crossed the 2.0 m port depth; case42's control -- same rule, same port "
        "depth, "
        "same 5 m spacing, 1.5x the port -- fires **32** steps after, crossing at step 335 and "
        "`t` = 87.0 s against a banner at step 367 and `t` = 113.2 s, `d/L` = 0.486. So the rule "
        "is "
        "confirmed twice on multiport diffusers, firing on any diffuser whose plume outgrows its "
        "port depth regardless of spacing or port count, and the lag is a **variable** between 6 "
        "and 32 steps on the two runs that have it. That is row 191b's unexplained lag reappearing "
        "where it had been thought single-port-only. ⚠️⚠️ **The prediction was half right and "
        "the wrong half is the interesting one**: it said ~85 s, meaning the port-depth crossing. "
        "The crossing is at 87.0 s -- 1.7 % out, a good prediction of the *trigger* -- and the "
        "banner is 26 s later. Predicting a trigger is not predicting a banner, and this is the "
        "second time that distinction has cost a prediction. ⚠️ The far field then prints *'Note: "
        "Plumes not merged'* over the top of it, the second instance after test68. Report to SSMC.",
    ),
    Target(
        row="269",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The exe's concentration schedule is not its entrainment schedule",
        source="test32 with the decrement radius walked on `crossplume.peak_to_mean`",
        measure=_walk_schedule_shallow,
        reference=0.0368,
        tolerance=0.005,
        unit="post-merge dilution MARE",
        note="⛔ **A derivation refuted by the thing that motivated it.** `NONE` is the round "
        "reading and `ALL` the slab reading, each right in its own regime, and the axis is how "
        "deep "
        "into overlap a run gets (rows 264c, 267b). The exe states that schedule itself on a "
        "*different* observable -- peak-to-mean walks round 2.0 at `d/L` 1 to slab 1.5 at `d/L` 2 "
        "and stays there, rows 199 and 203 over 2 964 rows -- so walking the decrement radius on "
        "the same schedule is **parity rather than a fit**, with no free parameter and "
        "`slab_fraction` calling `crossplume.peak_to_mean` rather than restating it. **It does not "
        "work**: 3.68 % here against `NONE`'s **1.01 %**, and across all seven merged runs the "
        "mean "
        "post-merge MARE is **7.62 %** against `ALL`'s **7.58 %** -- a wash, better on two runs by "
        "0.6 pp and worse on five by at most 0.6. ⭐⭐ **So the element's concentration profile is "
        "a slab from `d/L` 2 outward while its entrainment is not**: two geometries for one "
        "element, governed differently. That is a statement about the exe, and it is why this row "
        "is kept rather than deleted -- a candidate with an independent measurement behind it has "
        "to be shot down with a number.",
    ),
    Target(
        row="269b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The walk keeps the deep-overlap gain, so its failure is not mere weakness",
        source="case42 under the same walk, against `ALL`'s 0.98 % and `NONE`'s 35.53 %",
        measure=_walk_schedule_deep,
        reference=0.0135,
        tolerance=0.004,
        unit="post-merge dilution MARE",
        note="Row 269's other half. The walk is **36x** better than the shipped default here and "
        "still loses to the plain slab reading by 0.37 pp, so it is not that it brakes less -- it "
        "brakes on the wrong schedule. ⭐ It *is* best of the three on case41's test65, 1.77 % "
        "against `ALL`'s 2.32 % and `NONE`'s 14.76 %, and test65 has the second-highest onset "
        "dilution of the seven. So the direction the walk was built to correct is real and its "
        "magnitude is far too small to matter, which is the useful half of a refutation.",
    ),
    Target(
        row="270",
        phase=5,
        evidence=Evidence.EXTERNAL,
        claim="The exe's two-port suppression matches published coalescing-pair theory",
        source="case43's test72 against Cenedese & Linden (2014) eq 2.12's merged asymptote",
        measure=_coalescing_pair_asymptote_holds,
        reference=COALESCING_PAIR_ASYMPTOTE,
        tolerance=0.045,
        unit="merged entrainment rate over unmerged",
        note="⭐⭐⭐ **The first test of an independent theory against UM3's merging, and nothing "
        "in the archive could have run it.** Cenedese & Linden solve two coalescing axisymmetric "
        "plumes from first principles and define an effective entrainment constant -- our "
        "suppression ratio under another name -- whose merged asymptote is `2^(-1/2)` = **0.707**. "
        "Every merged run archived before case43 has **25 ports**, so the pair the theory "
        "describes had never been built. test72 is one, at a per-port flow matched to its "
        "single-port control, and reads **0.733** -- within **3.7 %**. ⚠️ **The "
        "asymptote holds; the approach curve does "
        "not** -- eq 2.12 declines 0.855 to 0.707 across this window while the exe reads "
        "0.719 / 0.725 / 0.756, flat and already at the asymptote. UM3 lands on the right "
        "merged value without following the theoretical path -- what a closure switching on a "
        "merge flag does rather than one solving the coalescence. ⭐⭐ **And it retires "
        "the reading that "
        "the exe suppresses more than plume theory allows** -- that came from the 25-port "
        "runs, and at the port count the theory describes they agree, so the archive's extra "
        "suppression is the **row**, not a disagreement with physics. ⚠️ `external`: the "
        "reference is a **different model**, not the "
        "exe, so this measures agreement between two independent treatments, and the "
        "tolerance is 6 % for that reason.",
    ),
    Target(
        row="271",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Port count is a first-order control on the merged suppression",
        source="case43's 2-, 6- and 25-port runs at one spacing and one per-port flow",
        measure=_port_count_sets_the_suppression,
        reference=0.1655,
        tolerance=0.02,
        unit="spread in suppression level across port count",
        note="⭐⭐⭐ **A first-order variable nothing had measured**, because every merged run in "
        "the archive has 25 ports. At a fixed 0.5 m spacing with the *per-port* flow held constant "
        "-- so the individual plume is identical and only the number of neighbours changes -- the "
        "exe gives **0.733** at two ports, **0.605** at six and **0.568** at twenty-five. A "
        "**0.165** spread across a twelvefold range, comparable to row 260d's 0.198 across "
        "spacings, so a variable of the same order. ⚠️ All three arms merge at step **204** and "
        "onset dilution **57.0**, identical to three figures, which is the per-port-flow control "
        "working: the plume is the same and only its company differs. Row 271b is the part that "
        "matters -- the brake reproduces this shape.",
    ),
    Target(
        row="271b",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="UM3's `1/n_ports` out-of-plane share is confirmed by the port-count decrements",
        source="the brake's decrements between successive port counts against the exe's",
        measure=_out_of_plane_share_is_confirmed,
        reference=0.009,
        tolerance=0.008,
        unit="worst absolute error in a port-count decrement",
        note="⭐⭐ **What confirms `out_of_plane = 1/n_ports`** -- the factor distributing "
        "cross-current entrainment over the merged group, the only place the port count "
        "enters this port's model, and untested until a port-count sweep existed. Decrements: exe "
        "**-0.128** and **-0.037** between 2-6 and 6-25; ours braked **-0.138** and **-0.039**; "
        "the shipped default -0.162 and -0.062. **8 % and 5 % out** against levels of "
        "0.57-0.73. So the brake has the port-count *dependence* right and is offset in *level*, "
        "which row 272 "
        "measures as a single constant. ⚠️ Pinned as the worst absolute decrement error rather "
        "than a ratio: the second decrement is -0.037 and a ratio there would swing on the third "
        "decimal.",
    ),
    Target(
        row="272",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="At a fixed spacing the brake's residual is one constant, not a function",
        source="the brake's level offset across case43's three port counts",
        measure=_brake_residual_is_one_constant,
        reference=0.012,
        tolerance=0.008,
        unit="spread in the brake's level offset",
        note="⭐⭐ **This splits row 264b's residual in two.** Across a twelvefold range of port "
        "count the brake's offset is +0.063 / +0.053 / +0.051 -- mean **+0.056**, spread **0.012** "
        "-- where the shipped default's is +0.284 / +0.250 / +0.225, mean +0.253 and spread 0.059. "
        "So the residual that *changes sign* -- row 264b's -0.071 at a 0.75 m spacing against "
        "+0.145 at 0.25 m -- belongs to the **spacing**, not to the port count. One unexplained "
        "residual becomes a constant plus a spacing dependence, and only the second still wants a "
        "mechanism. ⭐ That is the most useful thing case43 produced for fixing the brake, because "
        "a constant offset at fixed geometry is a much smaller object than a function of two "
        "variables.",
    ),
    Target(
        row="273",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The shipped default enhances entrainment at two ports -- a recorded divergence",
        source="case43's test72 through `ConfinedDecrements.NONE`, against a measured 0.733",
        measure=_the_default_enhances_entrainment_at_two_ports,
        reference=1.017,
        tolerance=0.03,
        unit="merged entrainment rate over unmerged",
        note="⚠️⚠️ **A recorded divergence, registered before the run, and the reference "
        "forbids it.** Two coalescing plumes cannot entrain more than two independent ones, so "
        "Cenedese & Linden's `alpha_eff/alpha` is bounded above by 1 by construction, "
        "reaching it only while the plumes are separate. The shipped default gives "
        "**1.017** at two ports -- "
        "*enhancement* -- against a measured **0.733**. So it is **39 % out at a port count where "
        "the right answer was known a priori**, in a direction the physics excludes. ⭐ The "
        "cleanest single statement of the runaway's cost, and it was predicted rather than "
        "discovered afterwards. ⚠️ It also fails on accuracy: 19.55 % post-merge here against the "
        "brake's 5.95 %, and 3-4x worse on every arm of the suite.",
    ),
    Target(
        row="274",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The suppression level is not a function of overlap depth",
        source="case43's test75 -- twice the port at one spacing, so `d/L` moves and `z*` does not",
        measure=_the_level_is_not_a_function_of_overlap_depth,
        reference=0.0258,
        tolerance=0.015,
        unit="change in level when the port doubles",
        note="⭐⭐ **Row 266 corroborated from a second direction.** test75 doubles the port "
        "at the same spacing and port count, so `d/L` at any trajectory point is about 1.4x the "
        "base run's while `z* = alpha z / L` is unchanged. The exe moves 0.568 to **0.542** "
        "-- so the level is not a function of overlap depth, which is what row 266 concluded from "
        "matched dilution instead. ⚠️ **Ours moves the other way**: 0.641 for the wide port against "
        "0.619 for the base, where the exe reads it *lower*. Both differences are small against a "
        "0.5-0.7 level, but the sign is wrong and it is recorded rather than rounded away. "
        "⚠️ test75 is also the suite's worst arm -- **10.53 %** post-merge braked against "
        "4.30-5.95 % -- and it carries the lowest onset dilution, 26.8 against 57.0, which is row "
        "267b's axis pointing the same way it did on test32 and case42.",
    ),
    Target(
        row="276",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The residual walks smoothly with spacing and crosses zero near 0.62 m",
        source="case44's six spacings against case43's single-port test71",
        measure=_the_residual_walks_with_spacing,
        reference=0.62,
        tolerance=0.08,
        unit="spacing at which our offset crosses zero, m",
        note="⭐⭐ **Row 272's open item, answered.** Row 264b saw the residual at "
        "-0.071 / +0.049 / +0.145 on three case41 spacings and could not tell a law from three "
        "samples straddling zero. case44 gives six at one port count and one flow: **+0.123** at "
        "0.30 m, **+0.079** at 0.45, **+0.021** at 0.60, **-0.080** at 0.80 and **-0.076** at "
        "1.10 -- a monotone walk crossing zero near **0.62 m**. So the sign change is a smooth "
        "function of the spacing and there is a law to find. ⭐ **The exe's own level rises "
        "with spacing**, 0.540 to 0.744, a 0.204 spread of the same order as its port-count spread "
        "(row 271), while ours is nearly flat over the same range (0.619 to 0.695) -- so what is "
        "missing is a *spacing* dependence, not a constant. ⭐ **It agrees with case41 where "
        "they overlap**: case41's 0.75 m read 0.766 against this sweep's 0.80 m at 0.744, its "
        "0.25 m read 0.580 against this 0.30 m at 0.572. case41's non-monotone look was coarse "
        "sampling. ⚠ The mean offset is only **+0.014**, so what ships is nearly unbiased "
        "across the sweep and carries a tilt of about +/-0.10; the retired default was biased "
        "+0.241 *and* tilted.",
    ),
    Target(
        row="111",
        phase=4,
        evidence=Evidence.MANUAL,
        claim="Total calcium is derived from salinity, which is why the Ca input is inert",
        source="manual section 3.2's `[Ca2+] = 0.01028 * S/35`, over S 0-45 psu",
        measure=_calcium_follows_the_salinity_law,
        reference=0.0,
        tolerance=1e-12,
        unit="worst |Ca - law|, mol/kg",
        note="Row 111, and the mechanism behind row 61's observation. The manual derives total "
        "calcium from salinity rather than reading it, so an entered `Ca` has nowhere to go -- the "
        "exe accepts the column, ignores it, and warns nobody. Exact to the last bit on 200 points "
        "across S 0-45. \u26a0 `CALCIUM_AT_S35` is the manual's rounded **0.01028**; PyCO2SYS "
        "carries Riley & Tongudai's unrounded 0.0102845, a recorded source of a small Omega "
        "offset. This row measures fidelity to the **manual**, which is what the exe follows, so "
        "`manual` evidence rather than `golden`.",
    ),
    Target(
        row="197",
        phase=8,
        evidence=Evidence.EXTERNAL,
        claim="Brucite dissolution is athermal, and a 48x enthalpy error would have been silent",
        source="`Ksp*` at 10 C over 25 C, against standard formation enthalpies",
        measure=_brucite_dissolution_is_athermal,
        reference=1.0084,
        tolerance=0.01,
        unit="Ksp*(10 C) / Ksp*(25 C)",
        note="\u2b50\u2b50 **The number that matters is the one it replaced.** An earlier "
        "revision carried **-111.3 kJ/mol**, a *formation*-scale enthalpy, where the reaction "
        "enthalpy from standard formation enthalpies is **-2.29 kJ/mol** -- 48x too large. With "
        "the wrong value this same ratio reads **10.359**: a **ten-fold** error in `Ksp*` at "
        "near-field temperature, and so in every `Omega_brucite`, with nothing downstream "
        "complaining. \u26a0\u26a0 **That is phase 8's whole problem in one row.** "
        "`Omega_brucite` has no parity target by construction (row 195) because the exe cannot "
        "report it, so a 10x error in it produces no failing comparison anywhere; the only "
        "defences are analytical limits, internal consistency and the literature. \u26a0 1.0084 "
        "is not exactly 1 -- real brucite dissolution is *very nearly* athermal, and 0.8 % over "
        "15 C is the correct residual rather than a tolerance.",
    ),
    Target(
        row="218",
        phase=7,
        evidence=Evidence.INTERNAL,
        claim="One registry, two consumers -- and no row reaches only one of them",
        source="every target in the registry, against the rendered validation page",
        measure=_registry_reaches_both_consumers,
        reference=0.0,
        tolerance=0.0,
        unit="targets the report does not name",
        note="Row 218's claim is *one registry, two consumers* -- `pytest` asserts each "
        "measurement and `plumes2 validate` tabulates them -- and the risk it names is the two "
        "drifting apart. So the executable form is **not** a coverage fraction, which is published "
        "in the header and guarded by "
        "`test_the_published_coverage_figures_are_not_stale`; it is the invariant that every row "
        "the suite drives appears on the page. \u26a0 **Mildly self-referential, which is why it "
        "went unwritten for four days**, and still worth having: the failure it catches is a "
        "target measured on every build and shown to nobody -- the same 'correct arithmetic, wrong "
        "presentation' shape as the stale hand count, the pooled suppression bins and the "
        "retracted plateau. \u26a0 `internal`: there is no reference for it but the page itself. "
        "Rendered from stubbed outcomes, so it checks the page and never depends on whether the "
        "physics currently agrees.",
    ),
    Target(
        row="61",
        phase=4,
        evidence=Evidence.GOLDEN,
        claim="The ambient `Ca` column is inert -- entered, ignored, and no warning given",
        source="case06's `Ca` = 5000 against ~10 500 seawater, on its far-field OmegaA",
        measure=_case06_inert_calcium_ratio,
        reference=0.965,
        tolerance=0.02,
        unit="exe OmegaA over ours",
        note="\u2b50\u2b50 **The run was designed so the answer could only be one of two "
        "numbers.** case06 enters an ambient `Ca` of **5000** micromol/kg against roughly "
        "**10 500** for seawater at S = 36 -- so a *used* value would halve the exe's Omega and "
        "give a ratio near **0.48**, and a *derived* one leaves it unchanged at about **0.97**. "
        "Measured on the far-field table, where TA, DIC and OmegaA are printed on the same rows so "
        "nothing is reconstructed: **0.973**, the archive's ordinary exe/PyCO2SYS offset and "
        "nothing more. \u26a0 case06's README quotes **0.9652** for the same comparison; this "
        "reads **0.9734** because it evaluates PyCO2SYS at the ambient's S and T uniformly rather "
        "than at a per-row spreading estimate. The 0.8 % between them is irrelevant to the claim: "
        "the two readings this run separates are **0.97 and 0.48**. "
        "\u2b50 And since both rate laws reproduce from Omega alone (rows 68, 83), "
        "an input that does not reach Omega does not reach the rates either -- the column is inert "
        "everywhere. Row 111 is the mechanism: the manual derives calcium from salinity, so an "
        "entered value has nowhere to go. \u26a0\u26a0 **On the SSMC list**: the exe accepts a "
        "calcium concentration, silently ignores it, and prints no warning, so a user who measures "
        "their receiving water's calcium will believe it was used. \u26a0 The discriminating "
        "power is the *deliberately wrong* value -- case05's `Ca` = 10300 was about seawater and "
        "could not have told the two readings apart.",
    ),
    Target(
        row="261",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The limiting-spacing rule fires on a multiport diffuser, not just one port",
        source="case41's control: 25 ports at 5 m, a 2.03 m plume, banner at step 373",
        measure=_limiting_spacing_fires_on_a_multiport,
        reference=6.0,
        tolerance=0.0,
        unit="steps from the port-depth crossing to the banner",
        note="⭐⭐⭐ **Found by accident, and it widens row 191o.** This run was requested purely "
        "as an unmerged control -- 25 ports at a **5 m** spacing, where a 2.3 m plume cannot "
        "possibly reach its neighbours. It prints `merging happened` anyway, six steps after the "
        "printed diameter crosses the 2.0 m **port depth**, at `d/L` = **0.41**. So UM3's "
        "limiting-spacing rule is not single-port behaviour: row 191o showed the entered spacing "
        "is inert on one port, and this shows the rule ignores the port **count** as well. Every "
        "earlier sighting happened to be on a single port, which is how a general rule looked like "
        "a special case. ⚠️⚠️ **And the exe contradicts itself in the same file**: the near field "
        "declares merging at 373 while the far field prints *'Note: Plumes not merged, Brooks "
        "method may be overly conservative'*. One run, two answers, and the entrainment "
        "suppression is applied on the strength of the first -- so a user at a wide spacing gets a "
        "merged near field they did not ask for and an advisory telling them the opposite. "
        "**Report to SSMC.** ⚠️ The 6-step lag is row 191b's unexplained lag again, at the low end "
        "of its 0-54 range.",
    ),
    Target(
        row="186",
        agreement=Agreement.DIVERGES,
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="The merged radius runs away at deep overlap -- a recorded divergence",
        # ⚠️ Said "case40's test58" until 2026-08-20, which is where the *previous* 6.65x came
        # from; the measurement maximises over `_CASE41_RUNS` and 11.93x is case41's test67. A
        # source field left behind by a moved reference sends a reader to the wrong trace.
        source="case41's test67, worst of the sweep -- our max merged diameter over the exe's",
        measure=_deep_overlap_runaway,
        reference=1.819,
        tolerance=0.15,
        unit="ratio, ours over theirs",
        note="⚠⚠ **A recorded divergence, and the mechanism behind row 157b.** Eq 56 "
        "inflates the element to hold its area against a transverse cap and nothing in this port "
        "opposes it, so the merged radius grows quadratically: on case41's test67 ours reaches "
        "**22.784 m** at matched time where the exe is at **1.910 m**. ⚠️ Salinity moves it in "
        "the direction the mechanism predicts -- 8.63x at 35 psu, 10.69x at 40, 11.93x at 45, all "
        "at one spacing -- because a denser effluent sinks harder and spends longer deeply "
        "overlapped. ⚠️ **The sign is wrong, not just the size.** The exe's "
        "element *stops growing* under deep confinement -- 1.141 m unmerged, 1.193 m at `L` = 0.5, "
        "**1.012 m** at `L` = 0.25 -- so deep merging makes it **smaller** than the unmerged run, "
        "where ours inflates. The exe has a brake this port lacks entirely and eq 56, "
        "unopposed, has the wrong asymptote. ⚠️ The reference has moved twice, each time "
        "because a worse sample arrived -- 2.05x (case21), 6.65x (case40), now 11.93x -- so it "
        "tracks the worst rather than the run that first found it, and is quoted at matched time "
        "since our runs end before the exe's.",
    ),
    Target(
        row="259",
        phase=5,
        evidence=Evidence.GOLDEN,
        claim="Spacing is inert until the plume merges, on a third independent pair",
        source="case40's test56 and test59 -- 2 m and 3 m, neither reached",
        measure=_spacing_inert_until_merging,
        reference=0.0,
        tolerance=0.0,
        unit="worst numeric difference",
        note="A third instance of 'the file changes, the numbers do not' (rows 191l, "
        "191o). These two differ only in a spacing neither plume ever reaches, and they agree "
        "**exactly** on every column across all 272 finite rows while their bytes differ -- the "
        "diffuser echo prints the spacing itself. case20's test31/test33 said the same at 2 m "
        "against 5 m. ⚠️ It is what licenses using the archive's wide-spacing multiport "
        "runs for **single-plume** physics: an unmerged multiport diffuser is a set of independent "
        "plumes, which is the premise cases 18-20 rest on.",
    ),
    # ------------------------------------------------------------------ Phase 6, output
    Target(
        row="79",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="A terminating row is truncated exactly when it is printed off-interval",
        source="13 archived traces carrying chemistry columns",
        measure=_terminating_row_truncation_violations,
        reference=0.0,
        tolerance=0.0,
        unit="traces violating the rule",
        note="The exe prints its final step wherever the plume stopped, usually not on the output "
        "interval, and drops the chemistry columns when it does. Zero violations, hence a zero "
        "tolerance -- and the byte-exact writer depends on it (row 18). ⚠️ Scoped to traces that "
        "**carry** chemistry, which is the finding rather than a convenience: case14 terminates "
        "off-interval and prints a full row because it has nothing to drop. Folds row 54.",
    ),
    Target(
        row="18",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="Every archived `.dat` re-renders byte for byte",
        source="all 53 archived traces",
        measure=_dat_round_trip_fraction,
        reference=1.0,
        tolerance=0.0,
        unit="fraction",
        note="Track A's acceptance criterion. It tests the formatter when fed the exe's own "
        "numbers, which is all it can test: our physics differs by 0.3-1 %, so a `.dat` generated "
        "from *our* results could never be byte-identical to theirs. ⭐ Built against 42 traces "
        "and unchanged by the five added later, including a 21-column set it had never seen.",
    ),
    Target(
        row="198",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="`CL-Dil = max(1, Dilutn/2)` on every unmerged archived row",
        source="every trace that selected both columns",
        measure=_centreline_exceptions,
        reference=0.0,
        tolerance=0.0,
        unit="exceptions",
        note="A count, so the tolerance is zero. This is the measurement that showed the exe uses "
        "a **parabolic** concentration profile rather than the 3/2-power one its own reference "
        "derives -- 2.0 peak-to-mean, not 3.89. \u26a0\u26a0 **Scoped 2026-08-25: default "
        "similarity profile only.** The claim was measured before anyone knew the profile *was* a "
        "setting; case48 enumerated the selector and the two non-default traces put 573 exceptions "
        "into a row whose claim is that there are none. They are excluded by name "
        "(`NON_DEFAULT_PROFILE_TRACES`) rather than by a widened tolerance, so a "
        "default-profile trace that broke the rule is still caught. Row 278 measures those two.",
    ),
    Target(
        row="279",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The exe walks its non-default profiles from round to slab by the parabola's "
        "linear law",
        source="case49: case44's 0.60 m project under `3/2 Power law` and `Gaussian`, against "
        "test79",
        measure=_profile_blend_residual,
        reference=0.0,
        tolerance=3e-3,
        unit="peak-to-mean, worst merged-walk row",
        note="\u2b50\u2b50 **The assumption in `crossplume.peak_to_mean` is now a measurement.** "
        "Both traces are bit-identical to test79 on the trajectory and follow "
        "`max(slab, round + (round - slab)(1 - d/L))` from the row after the banner to "
        "**0.0021** (3/2) and **0.0017** (Gaussian) at the worst of 106 walk rows each -- one law, "
        "three profiles. Round plateaus 3.88999 / 3.67001 reproduce case48's on a second geometry; "
        "slab plateaus 2.22200 / 2.14660 sit 0.01-0.03 % under the profiles' own integrals, flat "
        "to five figures over 132 rows -- the exe's quadrature again (row 278). Tolerance: the "
        "printed `CL-Dil` resolves the ratio to ~1e-4 here, so 3e-3 is generous to the law and "
        "still a tenth of the distance to any other blend shape. The banner row prints the round "
        "value on all three profiles (row 203), which is why the law starts one row later.",
    ),
    Target(
        row="278",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The similarity-profile selector picks the profile, and `3/2 Power law` is the "
        "reference's own",
        source="case48, one geometry under each of the exe's three profile options",
        measure=_three_halves_profile_gap,
        reference=0.0,
        tolerance=0.0015,
        unit="peak-to-mean, against the exact 35/9",
        note="\u2b50\u2b50\u2b50 **The exe has three similarity profiles and nobody knew.** "
        "`Default Profile`, `3/2 Power law Profile`, `Gaussian Profile`, enumerated 2026-08-25. "
        "The same case gives a developed peak-to-mean of **2.00000**, **3.88997** and **3.66998**, "
        "each flat to five figures over 252 rows, so the control is real and row 198's parabola is "
        "*one setting's* behaviour rather than the model's. The number returned is the 3/2 "
        "option's distance from **35/9 = 3.8889**, the exact reciprocal of the area-average of "
        "`[1 - u^1.5]^2` -- the profile the 3rd edition derives its 3.89 from. It reproduces it to "
        "**0.03 %**, which is 35x the printed precision and so is a real residual, most likely the "
        "exe's own quadrature; the tolerance admits it and no more. \u26a0\u26a0 The Gaussian is "
        "**not** PLAN 6b's `exp(-2u^2)` candidate (2.313): 3.670 implies `exp(-3.57 u^2)`, a far "
        "more peaked profile. So adopting *the exe's* Gaussian and adopting *the literature's* "
        "Gaussian are different decisions, which PLAN 8.4 had been treating as one.",
    ),
    Target(
        row="201",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="An exe trace works as plot input, with the secondaries it never carried",
        source="internal -- **no reference**: the exe cannot do this at all",
        measure=_trace_secondaries_missing,
        reference=0.0,
        tolerance=0.0,
        unit="named secondaries not derived, of eight",
        note="The frame has to accept a `.dat`, not only a `Results`, and then fill in what the "
        "exe never printed: `pCO2`, carbonate, bicarbonate and **Ω_brucite**, from its own TA and "
        "DIC. Nine columns are added in all. Each is checked three ways -- present, finite, and "
        "listed in `derived`, because a computed column the frame does not admit to would read as "
        "the exe's own. ⚠️ `internal` because there is **no reference**: Ω_brucite is the quantity "
        "the exe has no code for at all (row 195). What this shows is that the columns arrive; "
        "**row 211** is what shows they are right, by re-deriving something the exe *did* print "
        "off the same reconstruction. ⚠️ Scoped to the two chemistry traces with an archived "
        "project, since plume salinity and temperature cannot be rebuilt without one -- "
        "`secondaries=False` is what row 210 runs over all 141 traces.",
    ),
    Target(
        row="211",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="Deriving plume S and T from a trace costs no detectable chemistry error",
        source="case03 and case13, our reconstructed pH against the exe's printed column",
        measure=_chemistry_from_trace_error,
        reference=0.0272,
        tolerance=0.003,
        unit="pH, worst of the two traces",
        note="⭐ **What makes row 201 trustworthy rather than merely populated.** The secondaries "
        "need plume salinity and temperature, which the exe does not print -- they are mixed from "
        "the case -- so a wrong reconstruction would make every secondary wrong with it, silently. "
        "Re-deriving a quantity the exe **did** print, off that same reconstruction, is the check: "
        "case03 lands within 0.0236 (mean 0.0120) over 41 rows and case13 within **0.0272** (mean "
        "0.0129) over 55, with `Ω_arag` at 3.2 % on both. ⚠️ That residual is the "
        "**pre-existing** exe-vs-PyCO2SYS disagreement of rows 41-46, not an error introduced by "
        "the reconstruction, which is the whole point. ⚠️ The sign is **not** uniform: "
        "case03 is one-signed across all 41 rows while case13 crosses over late, 49 positive and 6 "
        "negative -- so it is a bounded disagreement rather than an offset that could be "
        "subtracted out.",
    ),
    Target(
        row="212",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="Adjacent palette slots stay separable under protanopia",
        source="internal -- **no reference**: OkLab dE x 100, Vienot-Brettel-Mollon in linear "
        "light",
        measure=_palette_protan_separation,
        reference=9.485,
        tolerance=0.01,
        unit="worst adjacent-pair separation, floor 8",
        note="`internal`, with **no reference**: the exe ships no figures, so nothing external "
        "validates a palette. The binding constraint of the five checks it claims: two slots may "
        "share a "
        "lightness or a chroma and still be told apart, but two adjacent slots a colour-blind "
        "reader cannot separate are a defect in the figure. ⚠️⚠️ **The published figure was 9.1 "
        "and is not reproducible.** The canonical Viénot construction in linear light gives "
        "**9.485**; Machado's severity-1.0 matrix gives 10.32; either applied in gamma-encoded "
        "sRGB gives 10.6. Nothing standard gives 9.1. The claim survives -- 9.485 clears the floor "
        "of 8 more comfortably than 9.1 did -- so this is a **correction**, and the fix was to "
        "compute it in `report/palette.py` rather than tune a matrix until it matched a comment. "
        "⭐ That is the argument for executable claims in one line: the palette's whole case is "
        "that it was *validated rather than chosen*, and it rested on five numbers nothing "
        "recomputed. ⚠️ Adjacent pairs only, deliberately: slots are assigned in order and never "
        "cycled, so a non-adjacent pair is never asked to be distinguished. Worst over all six "
        "combinations is 13.7, also above the floor, but it is not the claim.",
    ),
    Target(
        row="212b",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="The same separation under normal vision, which reproduces exactly",
        source="internal -- **no reference**: the same metric without the simulation",
        measure=_palette_normal_separation,
        reference=22.919,
        tolerance=0.01,
        unit="worst adjacent-pair separation, floor 15",
        note="`internal`, with **no reference**, as row 212. The companion that **agreed**: the "
        "docstring said 22.9 and the computation matches "
        "to the digit it was quoted at. Worth having beside row 212 precisely because it agreed -- "
        "it localises the 9.1 discrepancy to the colour-vision **simulation** rather than to the "
        "colour space, the palette, or the method as a whole. ⚠️ The space is OkLab, and it is not "
        "interchangeable: CIELAB gives 90.0 by CIE76 and 43.2 by CIEDE2000 for this same pair, "
        "neither of which is 22.9. Matching the published figure is how the space was identified "
        "at all, and OkLab is also the space the other two checks -- the lightness band and the "
        "chroma floor -- are already stated in.",
    ),
    Target(
        row="212c",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="Two slots sit below the contrast target, and the report owes them relief",
        source="internal -- **no reference**: WCAG 2 relative luminance against SURFACE",
        measure=_palette_worst_contrast,
        reference=2.109,
        tolerance=0.005,
        unit="lowest slot contrast, target 3:1",
        note="`internal`, with **no reference**. The validator's one **WARN**, recorded as a "
        "warning rather than folded into four "
        "passes, because a palette reporting five passes would be misrepresenting itself. Yellow "
        "sits at **2.11:1** and aqua at 2.74:1 against `SURFACE`; blue and orange clear 3:1. ⚠️ "
        "**Discharged, not dismissed.** The rule for a slot below 3:1 is *relief*: it may not "
        "carry meaning by colour alone. Every multi-series panel direct-labels its lines at the "
        "right-hand end and every panel carries a table of the values it plots, so those two slots "
        "never have to be told apart by colour -- and row 213 is what holds the tables in place. "
        "⚠️ It is also why the report has **no scatter** form, where every pair would have to "
        "clear the floors and these four do not. Both figures reproduce exactly.",
    ),
    Target(
        row="213",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="A rendered report has nothing to fetch",
        source="internal -- **no reference**: counted in the rendered HTML of both reports",
        measure=_report_external_references,
        reference=0.0,
        tolerance=0.0,
        unit="fetchable references",
        note="`internal`, with **no reference** -- the exe ships no report at all. One file: "
        "inline SVG, inline CSS, no JavaScript, nothing to retrieve. That is what "
        "makes it survivable -- emailable, archivable, openable offline in ten years, which a page "
        "pulling a CDN is not. Four things are counted and all four are zero: `<script>` tags, "
        "`<link>`/`<img>`/`<iframe>` elements, inline `on*` handlers, and `url(...)` references "
        "pointing outside the document. ⚠️ **A naive grep for `http://` finds 63, and every one is "
        "inert** -- which is why the measurement is written this way rather than as a URL count. "
        "matplotlib stamps each SVG with XML namespace URIs (`w3.org/2000/svg`, `xlink`) and an "
        "RDF block citing Dublin Core, Creative Commons and `matplotlib.org`. A namespace URI is "
        "an identifier, not a fetch, and no browser resolves any of them; all 149 `url(...)` "
        "references are matplotlib's own internal clip paths.",
    ),
    Target(
        row="199",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="A fully merged element prints the slab peak-to-mean, 1.5000",
        source="2 020 archived rows at d/L >= 2, out to d/L 19.6",
        measure=_fully_merged_floor_exceptions,
        reference=0.0,
        tolerance=0.0,
        unit="rows that miss 1.5000",
        note="The **golden** half of row 200's analytic identity: a fully merged element is a "
        "slab, and the parabolic peak-to-mean for a slab is exactly 1.5, where row 198 measures "
        "the round value 2.0 on the unmerged rows. ⭐ **Far stronger than the claim it replaces** "
        "-- the row was written from test32 settling at 1.5000 and test19 at ~1.60 partially "
        "merged, one run each, and the archive now has 2 020 rows at `d/L` >= 2 out to **19.6**, "
        "every one printing 1.5000 to the last digit. A floor holding over a twentyfold range of "
        "overlap is not a fitted constant. ⚠️ Counts exceptions rather than averaging a residual: "
        "1.5000 is exact to printed precision, so a mean would report the file's rounding and hide "
        "a real outlier.",
    ),
    Target(
        row="204",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The 2.0 ceiling is falsified -- the limiting-spacing rule lifts it square on",
        source="every square-to-flow merged run in the archive",
        measure=_square_diffuser_profile_ceiling,
        reference=2.2741,
        tolerance=0.0002,
        unit="highest ratio printed square to the flow",
        note="⛔⛔ **This row read \"the ratio never exceeds 2.0000 square to the flow\" until "
        "2026-08-21, and case45 falsifies the *mechanism* as well as the number.** The old "
        "reasoning: the profile law takes `d/L` on the **nominal** spacing while the merge flag "
        "fires on the **effective** one, so an oblique diffuser merges while `d < L` and reads "
        "above the round value -- but square to the flow the two coincide, so the flag *cannot* "
        "fire early and 2.0 is a ceiling. ⭐⭐⭐ **The flag can fire early square on, because "
        "obliquity is not the only thing that fires it.** UM3's limiting-spacing rule triggers on "
        "`diameter > port depth` regardless of spacing, angle or port count (rows 261, 268) -- so "
        "case45's test83, at a bearing *equal* to the current, banners at `d/L` = **0.49** and "
        "prints up to **2.2741**. ⭐ **And the law is right there, which is the useful half.** "
        "Extrapolated below `d/L` = 1 it predicts 2.2529-2.2942 against a printed 2.0000-2.2741 on "
        "that trace, and 2.3446-2.3786 against 2.3519 on test91 -- so `max(1.5, 2.5 - 0.5 d/L)` "
        "holds *outside the domain it was fitted in*, to a few hundredths, the shortfall being "
        "the post-banner ramp (row 221). The reference is now the highest square-on ratio rather "
        "than a ceiling. ⚠️⚠️ **Two runs are still excluded by name and the reason is still a "
        "finding**: case34's `L0.3_d0.50` and `L0.5_d0.75` put 0.5 m and 0.75 m ports at 0.3 m and "
        "0.5 m spacings -- more port than pipe -- so their plumes overlap before leaving the "
        "nozzle. Geometrically impossible inputs the exe accepts, kept on record.",
    ),
    Target(
        row="204b",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="And obliquity lifts it further -- now to 2.328, on a limiting-spacing run",
        source="every oblique merged run, worst at H-angle 175",
        measure=_oblique_profile_excess,
        reference=2.3277,
        tolerance=0.002,
        unit="highest ratio printed obliquely",
        note="The other half of row 204, and the control that makes the ceiling above mean "
        "something: a bound of 2.0 proves nothing unless something exceeds it. Obliquity does, and "
        "by a wide margin -- 2.1756 at the archive's most oblique geometry. ⚠️ **The excess tracks "
        "`d/L` at the banner rather than the angle alone.** Ordered by obliquity the archive gives "
        "65 deg -> 2.007, 70 -> 2.016, 45 -> 2.045, 175 -> 2.176, and 65 sits *below* 70 because "
        "the two runs have different spacings (0.75 m against 2.0 m). What sets it is how far "
        "short of the nominal spacing the flag fired at, which is row 181's law. "
        "⚠️ **The maximum is now 2.2787, on case41's test68, and that widens the claim "
        "rather than weakening it**: that run is not merged in the ordinary sense at all -- it is "
        "the *limiting-spacing* rule firing at `d/L` = 0.44 (row 261) -- and the profile law still "
        "uses the nominal 5 m spacing. So the law takes nominal spacing regardless of **which** "
        "rule raised the flag.",
    ),
    Target(
        row="206",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The exe ramps into the merged profile instead of switching to it",
        source="22 interval-1 traces: the banner row, the climb, and where it lands",
        measure=_onset_ramp_violations,
        reference=0.0,
        tolerance=0.0,
        unit="traces whose ramp is not a monotone climb from 2.0",
        note="⚠️ **A recorded non-reproduction.** Crossing the banner the exe does not jump to the "
        "merged profile: the banner's own row still prints 2.0000, the ratio then climbs "
        "monotonically to the law over 1-40 steps, and never leaves it again. Three things are "
        "asserted together, because any one failing would mean the transient is not what we think: "
        "the banner row prints the round value, the climb is non-decreasing, and it ends on the "
        "law. ⚠️ **Scoped to output interval 1, and the scope is a finding**: at interval 5 the "
        "banner row is up to five steps late and shows an already-merged value (case15's test15 "
        "and case16's test17/18 print 2.0400), so a transient a few steps long is simply not "
        "resolvable there. ⚠️ **The rate is still unexplained and deliberately not reproduced** -- "
        "not constant per step, per unit diameter or per unit dilution. At a fixed 175 deg it "
        "lengthens sharply with spacing (7 steps at 1.0 m, 15 at 1.5, 40 at 2.0); at a fixed 0.75 "
        "m it lengthens with obliquity (0 at 85 deg, 1 at 75, 1 at 65). Same shape as row 191b's "
        "merging banner and row 258b's surface stop: an event detected late, in a solver whose "
        "step controller targets 2 % mass growth per step.",
    ),
    Target(
        row="207",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="The exe's linear blend is not the parabola's own confined integral",
        source="analytic -- the blend against the integral it looks like",
        measure=_linear_blend_vs_parabola_integral,
        reference=0.1309,
        tolerance=0.002,
        unit="worst absolute gap over 1 <= d/L <= 2",
        note="The one place the exe's profile stops being geometry. Rows 198-200 show both "
        "*endpoints* are the parabolic peak-to-mean exactly -- 2.0 round, 1.5 slab -- so the "
        "natural reading is that the exe integrates `1 - (r/b)^2` over the confined cross-section. "
        "It does not; it interpolates **linearly** in `d/L`: 2.0000 against 2.0000 at `d/L` = 1, "
        "then 1.8500 against 1.8220 at 1.3, 1.7000 against 1.7088 at 1.6, and **1.5000 against "
        "1.6309** at 2.0. Endpoints exact, path a shortcut, worst where the true integral has not "
        "yet reached the slab limit. ⚠️ Marked `internal`: the linear law is measured against the "
        "archive by rows 203 and 221, and the thing it is compared to is an integral of ours, so "
        "there is **no reference** implementation to appeal to. It is here to record that those "
        "rows agree with a "
        "**shortcut** rather than with the geometry -- which is why reproducing the exe means "
        "implementing the blend and not the integral.",
    ),
    Target(
        row="221",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The centreline law survives well outside the domain it was fitted in",
        source="5 184 merged rows, 8x spacing range, six bearings, four port diameters",
        measure=_held_out_profile_fits,
        reference=0.924,
        tolerance=0.01,
        unit="fraction of merged rows on the law",
        note="⭐⭐ **Held-out survival, which is the strongest evidence available here.** The law "
        "`max(1.5, 2.5 - 0.5 d/L)` was fitted on **944** rows from eight runs. case24 nearly "
        "doubled that, case34 more than doubled it again, case40 took the overlap to `d/L` 4.27 "
        "and case41 to 15.1 -- **5 184** rows now -- and the law has not moved. ⚠️ **The residual "
        "2.1 % is entirely row 206's onset ramp**: every miss is a prefix row starting at exactly "
        "2.0000, and past first contact there are zero exceptions (row 203). So this is not \"98 % "
        "accurate\", it is \"exact, with a transient at the onset we deliberately do not "
        "reproduce\", and those are different claims. ⚠️ Reported as a **fraction** rather than a "
        "count so it cannot silently improve by the archive growing -- a count would rise with "
        "every new trace whether or not the law held.",
    ),
    Target(
        row="203",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="Merged rows past first contact obey `max(1.5, 2.5 - 0.5 d/L)`",
        source="8 runs, 3 spacings, 5 diffuser bearings",
        measure=_merged_profile_exceptions,
        reference=0.0,
        tolerance=0.0,
        unit="exceptions",
        note="Zero exceptions past first contact, at a tolerance derived from the printed "
        "precision of all three numbers that enter the comparison. The onset ramp is excluded "
        "as a recorded transient (row 206), and `d < L` at the banner is the exe disagreeing "
        "with itself about which spacing to use (row 204).",
    ),
    Target(
        row="210",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="Every archived trace adapts to the neutral plot frame",
        source="74 traces, whatever columns the GUI happened to select",
        measure=_plot_frame_failures,
        reference=0.0,
        tolerance=0.0,
        unit="traces that fail to adapt",
        note="The point of the frame is that a panel written against a `Results` object works "
        "unchanged against an exe trace, which only holds if *every* trace adapts -- so the "
        "tolerance is zero and the measurement counts failures rather than averaging them. Read "
        "with `secondaries=False`, i.e. as the exe wrote it; reconstructing what it never printed "
        "is row 211's separate claim.",
    ),
    Target(
        row="200",
        phase=6,
        evidence=Evidence.INTERNAL,
        claim="The two peak-to-mean constants are the parabola's own integrals, not fitted",
        source="analytic -- no external reference, and none is needed",
        measure=_parabola_integral_error,
        reference=0.0,
        tolerance=1e-9,
        unit="absolute, on the worse of the two",
        note="⭐ Why this matters: the exe's traces measure 2.0000 round and 1.5000 slab (rows "
        "198 "
        "and 199), and those are exactly the integrals of `1 - u^2`. The reference's 3/2-power "
        "profile would give 3.8889 and 2.2222 instead. Marked `internal` because there is **no "
        "reference** "
        "implementation to check an identity against -- it is mathematics, not a measurement, "
        "and the tolerance is quadrature accuracy. The *external* evidence for the parabola is "
        "the two golden "
        "rows it explains.",
    ),
    Target(
        row="84",
        phase=6,
        evidence=Evidence.GOLDEN,
        claim="The seven known event banners are the complete set across the archive",
        source="every archived `.dat`, scanned for banner-shaped lines",
        measure=_unknown_banners,
        reference=0.0,
        tolerance=0.0,
        unit="unrecognised banners",
        note="A banner the writer does not know cannot be re-rendered, so the byte-exact `.dat` "
        "claim (row 18) rests on this set being complete. The tolerance is zero because one "
        "unknown banner is one trace that will not round-trip. ⚠️ It is an archive-completeness "
        "claim, not a proof: an event no archived run happens to trigger would not appear here.",
    ),
    # ------------------------------------------------------------------ Phase 8, beyond parity
    Target(
        row="196",
        phase=8,
        evidence=Evidence.INTERNAL,
        claim="Peak Omega_brucite of the dosed Macoma plume",
        source="none -- the exe cannot report brucite at all",
        measure=lambda: float(_dosed_run().nearfield["omega_brucite"].max()),
        reference=131.4,
        tolerance=4.0,
        unit="Omega",
        note="⚠️ The one quantity here with **no reference implementation**, so this pins our own "
        "earlier value rather than checking against anyone else's -- a regression guard, not "
        "evidence of correctness. It is also an upper bound: ion pairing is not modelled, and "
        "including it would lower the free magnesium and hydroxide activities. "
        "⚠️ **Re-pinned 214 -> 131.4 on 2026-08-24**, when the uncited log Ksp -11.16 was "
        "replaced by Xiong (2008)'s measured -10.95 +/- 0.2 (operator decision, PLAN 8.1; the "
        "lineage ladder and citations are in chem/constants.py). Every Omega_brucite fell by "
        "exactly 10^0.21 = 1.62x; the trends, which rest on the salinity and pH dependences, "
        "did not move.",
    ),
    # ------------------------------------------------------------------ case51, flag ownership
    Target(
        row="281",
        phase=3,
        evidence=Evidence.GOLDEN,
        claim="Far-field flags 1 and 5 each gate the whole far field, and the file owns both bits",
        source="case51: one-flag-flip pairs against the base arm, legacy build",
        measure=_farfield_gate_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="mismatches against the archived evidence",
        note="Flipping either bit to 0 removes the far-field block entirely while the near field "
        "stays byte-identical, and both flips came back preserved in the as-run `.prj` -- two "
        "persistent controls with one observable. Which GUI control each maps to is round 2's "
        "reconnaissance (the operator did not record the dialogs). Zero tolerance: the measure "
        "counts departures from what is on disk, and one departure means the archive changed.",
    ),
    Target(
        row="281b",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Far-field flag 7 is exe-owned: written 1, rewritten to 0 on run, output unmoved",
        source="case51 `ff7` against the base arm",
        measure=_ff7_rewrite_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="mismatches against the archived evidence",
        note="The only flag of the eight flipped that the exe reclaimed -- the other seven came "
        "back exactly as written. Session state or a derived bit; either way the `.prj` cannot "
        "be used to *set* it.",
    ),
    Target(
        row="281c",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Near-field flags 1, 5, 6 and far-field flag 6 are file-owned bits, inert on a "
        "surfacing trajectory",
        source="case51: four one-flag flips against the base arm",
        measure=_preserved_flag_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="mismatches against the archived evidence",
        note="Preserved verbatim in every as-run `.prj`, traces bit-identical to base. Scoped: "
        "this plume surfaces and never hits bottom or shoreline, so a control gating those "
        "events reads inert here -- round 2's bottom-hit pair tests near-field flag 1 by output "
        "rather than by recall.",
    ),
    Target(
        row="282",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Near-field flag 3 = 1 makes the exe fail silently and truncate the project file",
        source="case51 `nf3`: the truncated as-run `.prj`, archived; no `.dat` exists",
        measure=_nf3_truncation_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="mismatches against the archived evidence",
        note="No error dialog on the run (operator, 2026-09-01), no output, and the project was "
        "cut mid-rewrite at the near-field plot-flags block with the flipped flag intact in the "
        "head. Re-loading the truncated file crashed the exe -- a second defect (no guard on a "
        "short project). The measure asserts the evidence: the archived file still fails to "
        "parse, still carries the flipped head, and still has no trace beside it.",
    ),
    Target(
        row="283",
        phase=1,
        evidence=Evidence.GOLDEN,
        claim="Near-field flag 1 is the stop-at-bottom box (1 = stop)",
        source="case52: a dense -45 degree pair over a seabed 0.3 m below the port, one flag "
        "moved",
        measure=_bottom_stop_mismatches,
        reference=0.0,
        tolerance=0.0,
        unit="mismatches against the archived evidence",
        note="Both arms print `Plume hits the bottom` at step 231 with every prior row "
        "bit-identical; the base stops there and the flipped arm continues 14 printed rows "
        "through `Plume traps` -- case46's surface pattern at the seabed, and case06's 'a hit "
        "is a termination switch, not physics'. Double-evidenced: the recon checklist shows "
        "the flipped project loading with the bottom-hit box unchecked. The pre-registered "
        "forecast (contact ~21 s, dilution 93, from the port's own integration) landed at "
        "21.409 s / 97.200.",
    ),
)


def measure(target: Target) -> Outcome:
    """Run one target, turning a raised exception into a reported failure rather than a crash.

    A validation pass that dies on its third target tells you nothing about the other twenty.
    """
    try:
        return Outcome(target=target, ours=float(target.measure()))
    except Exception as raised:
        return Outcome(target=target, ours=math.nan, error=f"{type(raised).__name__}: {raised}")


def run_all(targets: tuple[Target, ...] = TARGETS) -> list[Outcome]:
    """Every target, in ledger order within phase."""
    return [measure(target) for target in sorted(targets, key=lambda t: (t.phase, t.row))]


def cached_functions() -> tuple[str, ...]:
    """The names of every memoised helper in this module, in definition order.

    Derived rather than listed, because a hand-maintained list of caches is the same shape of
    defect as a hand-maintained coverage count -- it goes stale the first time someone adds a
    `@cache` and forgets. There are around forty; they exist because several targets share a run
    and a validation pass that integrated the same case six times would be slow enough that
    nobody ran it.
    """
    return tuple(
        name
        for name, value in globals().items()
        if callable(value) and hasattr(value, "cache_clear")
    )


def clear_caches() -> None:
    """Drop every memoised intermediate, releasing the traces and solutions they hold.

    ⚠️ **The memos are per-process and unbounded**, which is fine for a one-shot
    `plumes2 validate` and not fine for a long-lived process -- a notebook that imports this
    module to re-derive a ledger row keeps every `Solution` it touched alive until the kernel
    dies. The test suite calls this at session end for the same reason.

    Correctness does not depend on it: every cache here is keyed on its full input, so clearing
    only costs time. That is what makes it safe to call at any point.
    """
    for name in cached_functions():
        globals()[name].cache_clear()


#: Ledger rows in PLAN.md §6 that state something checkable, by phase. The denominator in
#: `coverage_by_phase`, and the honest one: it is what could *become* a target, not what has.
#:
#: ⚠️ **These were hand-counted until 2026-08-18 and were wrong by 42 %.** The total was recorded as
#: 156 against a real 222, and phase 5 as 41 against a real **84** -- so every coverage figure
#: published before that date flattered, phase 5 by a factor of two. Hand-counting was chosen to
#: stop the denominator tracking the numerator; what it actually produced was a number nobody could
#: reproduce and which drifted silently three times.
#:
#: They are now **derived by an explicit rule** and pinned here, with
#: `test_the_ledger_denominator_matches_the_ledger` recomputing it from PLAN.md on every run. The
#: rule, in full:
#:
#:   * one row counts once, under the phase its **target** claims, or -- with no target -- under the
#:     first phase the ledger lists. Twenty rows are filed under two phases, and counting those
#:     twice made some phases impossible to complete;
#:   * a row counts if it states a number, after stripping bare cross-references (`row 118`,
#:     `case09`, `eq 23`, `§5.2.2`) which are labels rather than quantities;
#:   * or if it already has a target, so the numerator can never exceed the denominator.
#:
#: Deriving it does **not** reintroduce the original worry: the rule reads the ledger, not the
#: registry, so implementing a target cannot shrink the denominator.
#:
#: ⚠️ **It holds row *identities*, not counts, since 2026-08-20.** It was a `dict[int, int]`, and
#: that let the two sides of the coverage fraction count different things: the numerator folded a
#: trailing letter, so `157b` collapsed into row 157, while this denominator counted it as the
#: separate row it is. Sub-lettered rows therefore cost a unit of denominator and earned none of
#: numerator -- phase 4 understated for `60b`-`60d`, phase 5 for `157b`, `157c` and `181b`. It
#: erred toward understating, which is why it survived review, but it was the mirror image of the
#: 2026-08-19 defect and the third time this fraction has counted mismatched things.
#:
#: Holding the identities fixes it at the root rather than by adjusting either side: the numerator
#: is now an intersection with this set, so the two cannot disagree about what a row is. It also
#: makes the derivation test strictly stronger -- comparing sets catches a row *swapped* for
#: another, which comparing totals could not.
LEDGER_ROWS_WITH_NUMBERS: dict[int, frozenset[str]] = {
    1: frozenset(
        (
            "1", "16", "28", "49", "72", "74", "85", "86", "87", "88", "113", "121", "141",
            "143", "161", "253", "281b", "281c", "282", "283",
        )
    ),
    2: frozenset(
        (
            "99", "100", "101", "102", "108", "147", "148", "159", "227", "255", "262",
        )
    ),
    3: frozenset(
        (
            "29", "30", "56", "96", "98", "114", "115", "116", "119", "120", "256", "257",
            "258", "263", "263b", "263c", "275", "277", "280", "280b", "281",
        )
    ),
    4: frozenset(
        (
            "35", "36", "39", "41", "43", "44", "45", "46", "60", "60b", "60c", "60d", "61",
            "73", "111", "122", "123", "124", "128", "214", "214b", "215", "216", "219", "220",
            "222", "224", "230", "235", "237", "238", "239", "240", "241", "242", "243", "244",
            "245", "246", "247", "250", "251", "258c",
        )
    ),
    5: frozenset(
        (
            "4", "17", "19", "20", "21", "24", "26", "27", "51", "52", "62", "63", "71", "75",
            "78", "90", "97", "104", "109", "133", "134", "140", "144", "145", "157", "157b",
            "157c", "171", "177", "178", "179", "180", "181", "181b", "182", "183", "184",
            "186", "191", "191c", "191d", "191o", "205", "258b", "259", "260", "260b", "260c",
            "261", "264", "264b", "264c", "264d", "264e", "260d", "260e", "260f",
            "265", "266", "266b", "267", "267b", "268", "269", "269b",
            "270", "271", "271b", "272", "273", "274", "276",
        )
    ),
    6: frozenset(
        (
            "18", "79", "84", "198", "199", "200", "201", "203", "204", "204b", "206", "207",
            "210", "211", "212", "212b", "212c", "213", "221", "278", "279",
        )
    ),
    7: frozenset(
        (
            # ⚠️ 229 was retired ⊘ `downgraded` on 2026-08-21: it claimed a suite runtime, and a
            # wall-clock assertion fails on a loaded machine while the code is perfectly correct.
            "218",
        )
    ),
    8: frozenset(
        (
            "196", "197",
        )
    ),
}


def ledger_row_of(row: str, phase: int) -> str:
    """The ledger row a target belongs to -- itself if the ledger has it, else its stem.

    The distinction is the whole point of this function. Some suffixed target rows **are** ledger
    rows (`157b`, `60c`, `191o`) and some are **ours** -- `17b`, `21b`, `109b` and `171a`-`171e`
    split one ledger row into the windows or diffuser arms a single number could not describe, and
    the ledger never lists them separately. Counting the first kind as its stem understates
    coverage; counting the second kind on its own would overstate it, which is exactly the defect
    corrected on 2026-08-19.

    So the registry cannot decide this and neither can a string rule: it is a question about the
    ledger, answered by looking. `LEDGER_ROWS_WITH_NUMBERS` is that lookup, and a test recomputes
    it from `LEDGER.md` on every build.
    """
    return row if row in LEDGER_ROWS_WITH_NUMBERS.get(phase, frozenset()) else row.rstrip("abcde")


def coverage_by_phase(targets: tuple[Target, ...] = TARGETS) -> dict[int, tuple[int, int]]:
    """`phase -> (ledger rows covered here, numbered ledger rows in that phase)`.

    Published alongside the results, because a validation report that shows ten passing targets
    without saying there are a hundred more claims is worse than no report: it invites the reader
    to mistake a tranche for the whole thing.

    ⚠️ **The numerator counts distinct ledger *rows*, not targets** -- corrected 2026-08-19, and it
    moved real numbers. Several rows carry more than one target: row 171 has five (one per current
    in the sweep), row 191 has four, rows 17, 21 and 109 have two each. Counting targets against a
    denominator of rows had phase 5 reading **25/49** when 25 targets covered **16** rows, and
    phase 4 reading 40/43 for 36. Both sides now count the same thing.

    ✅ **And both sides count the same set, corrected 2026-08-20.** Until then the numerator
    stripped a trailing letter unconditionally, so `157b` folded into row 157 while the denominator
    counted it as the separate ledger row it is -- sub-lettered rows cost a unit of denominator and
    earned none of numerator. That was the mirror image of the defect above and the third time this
    fraction has counted mismatched things, so the fix is at the root: the denominator holds row
    *identities*, and the numerator is an **intersection** with it. See `ledger_row_of` for why the
    distinction cannot be made by a string rule.
    """
    counted: dict[int, set[str]] = {}
    for target in targets:
        rows = LEDGER_ROWS_WITH_NUMBERS.get(target.phase, frozenset())
        row = ledger_row_of(target.row, target.phase)
        # An intersection, so a target can never count toward a phase the ledger does not file it
        # under -- `test_every_target_points_at_a_real_ledger_row` is what keeps this non-empty.
        if row in rows:
            counted.setdefault(target.phase, set()).add(row)
    return {
        phase: (len(counted.get(phase, set())), len(rows))
        for phase, rows in sorted(LEDGER_ROWS_WITH_NUMBERS.items())
    }


#: Ledger rows that are legitimately an agreement in one window and a divergence in another, so
#: `rows_by_agreement` lists them twice. Kept explicit and short: a *new* row landing in two
#: buckets is a claim that needs splitting or a mis-tag, and either way wants a human, not a
#: silently absorbed duplicate. See `test_a_row_in_two_buckets_is_one_we_named`.
#:
#: Both are sweeps whose arms disagree with each other, which is the whole reason they were split
#: into arms: row 17 is case01's step table, matching to 0.46 % through the jet and drifting to
#: 1.7 % after trapping; row 171 is the cross-flow sweep, clearing upstream's 0.5 % bar at 0.01
#: and 0.02 m/s and missing it at 0.05 (0.52 %) and 0.10 (0.88 %). Collapsing either to one
#: verdict would have to pick the flattering half.
ROWS_DISAGREEING_WITH_THEMSELVES = frozenset({"17", "171"})


def rows_by_agreement(
    targets: tuple[Target, ...] = TARGETS,
) -> dict[Agreement, tuple[str, ...]]:
    """`Agreement -> the ledger rows carrying it`, so no consumer hand-counts them.

    ⚠️⚠️ **The point is that `coverage_by_phase` cannot answer this, and reads as though it
    does.** Its fraction says how many claims are executable; it says nothing about how many
    *agree*, and four of them do not. A page that prints `148/154` beside no divergence count
    invites exactly the misreading the ledger's own notes spend a paragraph each preventing.

    ⚠️ Every count of these rows anywhere -- CLI line, report KPI, report caveat -- comes from
    here. The report's caveat used to say "in two places, deliberately reproducing its mistakes"
    as a **hand count**, which was already wrong at three, and a hand count going stale is the
    single most repeated defect in this project's history (four times on the coverage fraction
    alone). Derived, it cannot.

    Rows, not targets, and in ledger order, so this composes with `coverage_by_phase`.

    ⚠️ **A row can appear under two kinds, and the buckets therefore do not partition.**
    Agreement is a property of a *target*, and a row may carry several: row 17 is case01's
    step table, whose jet phase matches to 0.46 % (`MATCHES`) while its post-trapping window
    drifts to 1.7 % (`17b`, `DIVERGES`). Splitting that row into windows is what Phase 7's first
    act did, and collapsing it back to one verdict would undo the correction -- so the overlap is
    the honest answer and `ROWS_DISAGREEING_WITH_THEMSELVES` names the rows allowed to do it.
    The union is still exactly the coverage numerator, which the tests assert.
    """
    grouped: dict[Agreement, dict[str, None]] = {kind: {} for kind in Agreement}
    for target in sorted(targets, key=lambda t: (t.phase, t.row)):
        grouped[target.agreement][ledger_row_of(target.row, target.phase)] = None
    return {kind: tuple(rows) for kind, rows in grouped.items()}
