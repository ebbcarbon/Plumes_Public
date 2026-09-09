"""Generate the two exe experiments PLAN section 6's optional list still actually needs.

⚠️ **The list was audited first (2026-09-02), and three of its five entries were already run.**
The audit matters more than the generation: an experiment written for an answered question burns
an exe session and, worse, invites re-answering something the ledger already carries.

* **"case03 with KSO4 = 3"** — ran 2026-08-20 as `case03/kso4_option3.dat`: the selector is not
  cosmetic (pH moves 0.003-0.006, TA by exactly 0), rows 128/36 use it. What remains is analysis
  (which borate parameterisation, matched on the residual's *spread*), not a run.
* **"0.3 / 0.4 m ports at case30's geometry"** — ran 2026-08-20 (`d0.30_*`/`d0.40_*`, plus the
  0.22/0.25/0.28 bracket): the lag *switches* (regime B), the A→B boundary is (0.22, 0.25] m, and
  the regime map is complete on both axes. Row 191b. Only regime B's ~17-step offset stays open,
  and that is derivation, not data.
* **"an ambient DO profile whose depth-mean is far from its trapping-depth value"** — case28's
  close-out factorial did exactly this with mirror-image profiles sharing a depth-mean: the
  falling-rising difference is +1.765 across an 87x rate range, against 1.769 predicted for the
  trapping depth and 0.750 for the depth-mean. Settled.

What this module generates is the remaining two:

1. **`shoreline_stop_on` / `shoreline_stop_off`** — the controlled pair case12 could not be
   (its `.prj` is lost). Two byte-identical generated projects; the operator types the same
   shoreline vector (60°, 5 m) into both and ticks the stop-at-shoreline box in exactly one.
   Bit-identical traces make the shoreline feature inert beyond argument (the exe is
   deterministic, row 191c); any difference is the feature doing something three archived
   configurations never showed. ⭐ The box-on arm also saves the archive's **first non-zero
   shoreline vector**, decoding the `.prj` convention PORTING_NOTES records as unknown.
2. **`subcritical_sinks`** — case29's missing fourth arm (queued in prose 2026-08-19, never
   generated): identical to test41/42/43 except effluent salinity **45 psu**, so the discharge
   is dense and sinks. case29's three runs all breached the surface before going NaN, so they
   cannot separate "sub-critical is unusable" from "leaving the water column is unusable".
   This run stays submerged (the port traps it near 5 m), so a finite trace clears
   sub-criticality itself and NaN convicts it.

⚠️⚠️ **Postscript, same day: the audit itself missed one.** The sinking run came back
**byte-identical to case34's `L2.0_d0.50.dat`** (2026-08-19) — the repurposed `subcritical_sinks`
project's 2.0 m arm *was* this experiment, archived and read only for its merge trigger. So four
of the five listed entries had their data in the archive all along; the shoreline pair was the
one genuinely new run. The audit checked whether the other entries' *runs* existed but checked
this one for a *pending experiment* — wrong question, same list. The finding is claimed anyway
(row 285, case54 + case34), the collision is the fifth same-input determinism check, and this
note is here so the next audit asks about data, not directories.

Run from the repository root::

    .venv/Scripts/python studies/open_items_experiments.py

The port's own forecasts are computed here, at generation time, and written into the notes —
predictions registered before the run, per PLAN section 8.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from plumes2.config import AmbientProfile, Case
from plumes2.experiments import Experiment, write_experiment
from plumes2.io.project import load_project
from plumes2.results import Results, run
from plumes2.sweep import with_updated

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "reference_cases" / "pending"

#: Asked in every note since 2026-08-25: nothing in the `.prj` or `.dat` records which binary
#: ran (row 275 — same project, same near field, wastefield width 109.59 m vs 96.29 m).
BUILD_NOTE = (
    "WHICH EXE BUILD did this run: write down which executable was launched, and from where. "
    "Nothing in the .prj or the .dat records it, and the far-field wastefield width is the "
    "after-the-fact fingerprint (row 275). Legacy build is fine here — the operator prefers it "
    "for physics without chemistry — but the answer has to be written down."
)


def _case_from(path: Path) -> Case:
    """The case a project describes, with the load-time warnings quieted."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_project(path, warn_on_drift=False).to_case()


def _forecast(case: Case) -> Results:
    """The port's own integration, quieted (DesignWarning is expected on the sinking case)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run(case, samples=2000)


def _with(case: Case, attribute: str, value: object) -> Case:
    """`sweep.with_updated` with the warnings quieted.

    Both warnings this silences are known and deliberate: the archived diffuser's 17 m seabed /
    15 m profile GeometryWarning (intentional, operator 2026-09-01) and the sinking arm's
    sub-critical DesignWarning, which is the regime that experiment exists to probe.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return with_updated(case, attribute, value)


def _shoreline_case() -> Case:
    """case12's configuration at full precision, chemistry off, output interval 1.

    case12's own `.prj` is lost; case03's `test.prj` is the same archived-diffuser project saved the
    same day and its hydrodynamics are bit-identical to case02's (row 215), so it carries every
    shared field losslessly. The two fields case12 moved are re-applied: the flow was entered
    as **0.005 cms** (case03's file holds the mgd entry; case12's echo prints `Ttl-flo 0.01`,
    which only 0.005 m³/s rounds to) and the interval here is 1 rather than case12's 5, for
    banner-step resolution. Chemistry is deliberately absent: the shoreline question is
    hydrodynamic, a scalar overlay cannot move a trajectory (row 215), and a chemistry-free
    case spares the GUI re-entry the `.prj` cannot carry.
    """
    base = _case_from(ROOT / "reference_cases" / "case03_carbonate" / "test.prj")
    case = base.model_copy(
        update={
            "description": "shoreline stop pair: identical runs, box on vs off",
            # load_project picks up case03's testco2.csv sibling; this pair is
            # hydrodynamics-only, so the ambient profile is rebuilt without it.
            "ambient": AmbientProfile(levels=base.ambient.levels),
            "effluent_chemistry": None,
            "effluent_do": None,
        }
    )
    case = _with(case, "effluent.flow", 0.005)
    return _with(case, "near_field.output_interval", 1)


def shoreline_pair() -> tuple[Experiment, Experiment]:
    """The box-on and box-off arms. The generated projects are byte-identical on purpose."""
    case = _shoreline_case()
    ours = _forecast(case)
    frame = ours.nearfield
    crossing = frame[frame["y_m"] >= 5.0].iloc[0]
    port_forecast = (
        f"the port integrates this case to `{ours.termination}` at t = {ours.end_time:.0f} s, "
        f"flux-averaged dilution {ours.final_dilution:.0f}, ending at y = "
        f"{float(frame['y_m'].iloc[-1]):.2f} m — past the 5 m shoreline, which it first crosses "
        f"at t = {float(crossing['time_s']):.0f} s (dilution {float(crossing['dilution']):.0f}, "
        f"depth {float(crossing['depth_m']):.2f} m). The plume never nears the surface: minimum "
        f"depth {float(frame['depth_m'].min()):.2f} m, matching case12's printed -1.296"
    )
    #: What both arms share. The archived twin is case12 (chemistry on, interval 5): trace ends
    #: step 400 on `Plume traps`, dilution 296.962, y 5.389, Depth -1.722; banners at 245/315/365.
    shared_predictions = {
        "shoreline banner": (
            "none. No archived trace has ever printed one and none of the seven known banners "
            "is shoreline-flavoured (case12 README)"
        ),
        "where the run ends": (
            "step 400 exactly, on `Plume traps`, at Dilutn 296.962, y-posn 5.389, Depth -1.722 "
            "— case12's archived endpoint, which this configuration reproduces with chemistry "
            "off (a scalar overlay is a pure overlay, row 215) if the operator's session state "
            "matches. A different step is input drift, not the shoreline"
        ),
        "the port's own integration": port_forecast,
        "if the arms differ at all": (
            "the shoreline feature DOES something, and three archived configurations (case08 "
            "twice, case12) never had the geometry to show it — localise the first differing "
            "step and check whether it sits at the y = 5 m crossing (~9 rows before the end)"
        ),
    }
    on = Experiment(
        name="shoreline_stop_on",
        case=_with(case, "near_field.stop_at_shoreline", True),
        question=(
            "Is the exe's shoreline stop inert even when the box is ticked against a non-zero "
            "shoreline vector? This arm is the ticked half of the controlled pair case12 could "
            "not be (its .prj is lost): identical projects, identical typed vector (60°, 5 m), "
            "the box the only difference. Bit-identical traces close ledger row 90's caveat and "
            "make the SSMC item a clean bug report; a difference is a live feature nobody has "
            "ever seen fire."
        ),
        predictions={
            **shared_predictions,
            "this arm against shoreline_stop_off": (
                "bit-identical .dat, every row and column, near field and far field — the exe "
                "is deterministic across sessions (row 191c), so byte-equality is decidable"
            ),
            "as-run near-field flag 3": (
                "1 — the box writes the flag (recon checklist, case51). If it comes back 0 the "
                "box was not ticked and this arm duplicated the off arm; say so and re-run"
            ),
            "as-run shoreline records": (
                "⭐ the archive's FIRST non-zero shoreline vector: two reals, one holding 60 and "
                "one holding 5, in an order no saved project has ever shown (PORTING_NOTES). "
                "Whichever position holds 60 decodes the convention"
            ),
        },
        settings=(
            "all output columns (already named in the generated .prj)",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked",
            "stop plume at surface hit: leave as loaded (the plume traps ~1.3 m down; inert here)",
            "⭐⭐ type the shoreline vector: **60 degrees, 5 m** — case12's entry, re-typed "
            "because the generated file carries 0, 0 (the .prj convention is unknown, so this "
            "generator refuses to guess an order)",
            "⭐⭐ THEN tick **stop plume at shoreline hit** — vector first, box second. ⚠️⚠️ Never "
            "run the box ticked while the vector still reads zero: that is ledger row 282's "
            "silent failure, and it truncates the project on rewrite",
        ),
        notes=(
            "ONE run. Copy the .dat and the as-run .prj aside before anything else runs.",
            "The generated projects in shoreline_stop_on/ and shoreline_stop_off/ are "
            "byte-identical on purpose: the typed vector is the same in both arms, so the box "
            "is the only intended difference between the two runs.",
            "case12 is the archived box-on sibling of this configuration (chemistry on, "
            "interval 5): no shoreline event, plume to y = 5.389 m against a 5 m shoreline. "
            "This pair exists because case12 has nothing to diff against.",
            "No chemistry and no DO — do not enter any; the carbonate tab stays off.",
            BUILD_NOTE,
        ),
    )
    off = Experiment(
        name="shoreline_stop_off",
        case=_with(case, "near_field.stop_at_shoreline", False),
        question=(
            "The control arm: the identical project and the identical typed shoreline vector "
            "(60°, 5 m) with the stop-at-shoreline box left UNTICKED. Everything that matters "
            "is the comparison against shoreline_stop_on."
        ),
        predictions={
            **shared_predictions,
            "this arm against shoreline_stop_on": (
                "bit-identical .dat, every row and column — see the on arm's note; the pair is "
                "one measurement split across two runs"
            ),
            "as-run near-field flag 3": (
                "0 — the untouched box. A 1 here means the box was ticked by habit and the pair "
                "collapsed into two on-runs; say so and re-run this arm"
            ),
            "as-run shoreline records": (
                "non-zero here too (the vector is typed in both arms), corroborating whatever "
                "order the on arm shows"
            ),
        },
        settings=(
            "all output columns (already named in the generated .prj)",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked",
            "stop plume at surface hit: leave as loaded (the plume traps ~1.3 m down; inert here)",
            "⭐⭐ type the shoreline vector: **60 degrees, 5 m** — the same entry as the on arm",
            "⭐⭐ leave **stop plume at shoreline hit** UNTICKED — the box is the experiment, and "
            "this is the arm where it stays off",
        ),
        notes=(
            "ONE run. Copy the .dat and the as-run .prj aside before anything else runs.",
            "Run this arm and shoreline_stop_on in either order; neither depends on the other's "
            "output, only on both existing.",
            "No chemistry and no DO — do not enter any; the carbonate tab stays off.",
            BUILD_NOTE,
        ),
    )
    return on, off


def subcritical_sinks_experiment() -> Experiment:
    """case29's fourth arm: the same discharge made dense, so it sinks instead of surfacing."""
    base = _case_from(ROOT / "reference_cases" / "case29_subcritical_froude" / "project.prj")
    case = base.model_copy(
        update={"description": "subcritical sinking discharge: case29's missing fourth arm"}
    )
    case = _with(case, "diffuser.port_diameter", 0.5)
    case = _with(case, "effluent.salinity", 45.0)
    ours = _forecast(case)
    frame = ours.nearfield
    deepest = frame.loc[frame["depth_m"].idxmax()]
    merged = frame[frame["merged"]].iloc[0]
    port_forecast = (
        f"sinks from the 2.0 m port to a deepest {float(deepest['depth_m']):.2f} m at "
        f"t = {float(deepest['time_s']):.0f} s (dilution {float(deepest['dilution']):.0f}), "
        f"rebounds ~0.4 m and oscillates; `{ours.termination}` at t = {ours.end_time:.0f} s, "
        f"flux-averaged dilution {ours.final_dilution:.0f}. It merges (2 m spacing) at "
        f"t = {float(merged['time_s']):.0f} s, depth {float(merged['depth_m']):.2f} m, "
        f"dilution {float(merged['dilution']):.0f}"
    )
    return Experiment(
        name="subcritical_sinks",
        case=case,
        question=(
            "Does the exe fail on sub-criticality itself, or on leaving the water column? "
            "case29's three arms (2/0/10 psu, F ≈ 0.003) all rose, breached the surface, and "
            "went NaN — so they cannot tell the two apart. This arm is identical except the "
            "effluent is 45 psu: dense, so it sinks toward a seabed 15 m below and, the port "
            "says, traps near 5 m without ever nearing the surface. A finite full-length trace "
            "clears sub-criticality (the NaN cliff is the missing surface clamp, as case09 "
            "suggests from the momentum extreme); NaN on a submerged plume convicts it."
        ),
        predictions={
            "NaN": (
                "none, anywhere. The plume never approaches depth zero, so the missing surface "
                "clamp never engages. If NaN appears anyway, sub-criticality itself breaks the "
                "exe and case29's mechanism story is wrong"
            ),
            "trajectory": (
                "monotonic sinking to a deepest point near 5.3 m (the exe prints Depth ≈ -5.3) "
                "around t ≈ 160 s, then a small rebound and trapping — buoyancy-trapped in the "
                "stratification, nowhere near the 17 m seabed"
            ),
            "termination": (
                "the rise/fall count (3), on `Local maximum rise or fall` / `Plume traps` "
                "banners — NOT `Plume hits the bottom` (13+ m short) and NOT the surface"
            ),
            "final dilution": (
                "600-700 (the port says ~640). The run merges at d/L ~1 and ends at d/L ~1.6, "
                "inside the post-merge 1-7 % band's shallow end; the slow 0.02 m/s current also "
                "invites the ~5 % post-trapping suppression (test23)"
            ),
            "merging banner": (
                "`merging happened`, near the diameter = 2 m spacing crossing (port: t ≈ 91 s, "
                "depth ≈ 4.9 m). 25 ports, so record the step — the single-port banner-lag "
                "regimes (row 191b) should not apply here"
            ),
            "far field": (
                "present, from the ~5 m trapping depth; the 500 m distance stop binds (the port "
                "reaches dilution ~5 700 at 500 m, under the 10 000x cap). Check the return with "
                "check_farfield_session_state — case47 declared 10 000x and came back at 5 000x"
            ),
            "the port's own integration": port_forecast,
            "Froude": (
                "F ≈ 0.0044 (exit velocity 0.001019 m/s through the 0.5 m port, g' ≈ 0.108 m/s² "
                "against the surface ambient) — the same three-orders-below-threshold regime as "
                "case29, on the sinking side. The port's DesignWarning fires"
            ),
        },
        settings=(
            "all output columns (already named in the generated .prj)",
            "No. of maximum plume rise or fall = 3",
            "stop plume at bottom hit: ticked (it should never fire; that is part of the point)",
            "stop plume at surface hit: leave as loaded",
            "no chemistry, no DO — the carbonate tab stays off",
        ),
        notes=(
            "ONE run. Copy the .dat and the as-run .prj aside before anything else runs — "
            "case29 is only interpretable because the diameter happened to survive the echo; "
            "this time the project is written from the case and the run re-saves it, closing "
            "that gap by construction.",
            "Identical to case29's test41/42/43 except effluent salinity 45 psu (they ran 2, 0 "
            "and 10). The generated .prj already carries the 0.5 m port, the 0.005 m³/s flow "
            "and the 45 psu effluent — nothing about the discharge needs typing.",
            "The 17 m seabed / 15 m profile shape is the archived projects' convention and "
            "intentional (operator, 2026-09-01); the port's GeometryWarning is a statement of "
            "extrapolation, not a suspicion.",
            BUILD_NOTE,
        ),
    )


def main() -> None:
    on, off = shoreline_pair()
    written = [write_experiment(experiment, PENDING) for experiment in (on, off)]
    on_prj = (written[0] / "shoreline_stop_on.prj").read_bytes()
    off_prj = (written[1] / "shoreline_stop_off.prj").read_bytes()
    # The pair's whole design is that the box is the only difference between the runs, so the
    # generated projects must not differ at all.
    if on_prj != off_prj:
        raise AssertionError("the shoreline pair's generated projects are not byte-identical")
    written.append(write_experiment(subcritical_sinks_experiment(), PENDING))
    for target in written:
        print(target)
        for path in sorted(target.iterdir()):
            print("   ", path.name)


if __name__ == "__main__":
    main()
