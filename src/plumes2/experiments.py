"""Generate self-contained exe experiments, so no hand-maintained project is ever edited.

Every decoded number in this port came from a trace, and every trace came from someone
clicking through the GUI. That has a cost the physics does not: the archive's two most
awkward gaps are both bookkeeping, not science --

* **test19 has no `.prj`.** It was only reconstructible because it happened to be test21's
  geometry with one field moved. A different base and the 85 degree bracket would have been
  unusable, and it is the bracket that killed four candidate laws.
* **test34/test35's `.prj` was stale.** The project file had been reset to the base before it
  was copied, so it described neither run.

Both are avoided by writing the project *from* the case that defines the experiment, next to
a note saying what it is for and what the port predicts. Then the file on disk cannot drift
from the intent, and a run that comes back is self-describing.

Usage is deliberately blunt::

    from plumes2.experiments import Experiment, write_experiment

    write_experiment(
        Experiment(
            name="merge_spacing_1m",
            case=my_case,
            question="Does the merge trigger track spacing, or is it fixed by the offset?",
            predictions={"diameter/spacing at the merging banner": "0.775 (0.600 if fixed)"},
            settings=("output interval 1", "all output columns", "3 rise/falls, bottom-hit"),
        ),
        directory,
    )

⚠️ Two things a generated project **cannot** carry, both established the hard way:

* **Chemistry**, which no `.prj` stores -- case03 ran the carbonate module and its project
  file contains none of it. It has to be re-entered in the GUI.
* **The rise/fall count**, and *possibly* the three stop-at checkboxes -- though the second
  half of that is now in doubt. The evidence for "session state" was that case13 and case14
  have byte-identical projects and stop differently; the evidence against is that a run given
  no box instruction came back with `nearfield_flags[1]` = 1 and stopped at the surface, while
  one told to untick came back 0 (2026-08-24). If the flag is the box, one of those two
  archived projects is stale and the boxes belong in the file after all.
  `reference_cases/pending/surface_stop_pair_v2` is the controlled pair that decides it.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from pathlib import Path

from plumes2.ambient import AmbientProfileView
from plumes2.chem.constants import resolve_constants
from plumes2.chem.speciation import solve_from_alkalinity_dic
from plumes2.config import AmbientChemistryLevel, Case, EddyDiffusivityLaw
from plumes2.io.csv_tables import TableKind, table_from_values, write_csv_table
from plumes2.io.dat import DatFile
from plumes2.io.prj import write_prj
from plumes2.io.project import prj_from_case
from plumes2.provenance import provenance

__all__ = [
    "Experiment",
    "FarfieldStop",
    "check_farfield_session_state",
    "classify_farfield_stop",
    "fill_ambient_ph",
    "write_experiment",
]


#: The far-field eddy-diffusivity selector's labels, as the exe's GUI shows them (operator,
#: 2026-08-26). 4/3 is the default and what every archived trace used; the `.prj` position that
#: encodes the selection is undecoded because no other option has ever been run (case49 README).
EDDY_LAW_GUI_LABEL: dict[EddyDiffusivityLaw, str] = {
    EddyDiffusivityLaw.CONSTANT: "Constant Eddy Diffusivity",
    EddyDiffusivityLaw.LINEAR: "Linearly varying eddy diffusivity",
    EddyDiffusivityLaw.FOUR_THIRDS: "4/3 power law based eddy diffusivity",
}


@dataclass(frozen=True, slots=True)
class Experiment:
    """One exe run, with the reason it exists attached to it."""

    #: Short slug; becomes the `.prj` stem and the directory name.
    name: str
    case: Case
    #: What the run is meant to settle, in one sentence.
    question: str
    #: What the port predicts, keyed by the observable. **Write these before running** --
    #: a prediction recorded afterwards is a fit.
    predictions: dict[str, str] = field(default_factory=dict)
    #: GUI settings the `.prj` cannot carry. Reproduced verbatim in the note.
    #:
    #: ⚠️⚠️ **"stop plume at surface hit: unticked" was removed from this default on
    #: 2026-08-24, and the reason is a probable retraction of ledger row 275b.** That row
    #: records that "every generated run comes back with `nearfield_flags[1]` flipped from 1
    #: to 0 by the exe". It now looks as though **the exe never flipped it**: this tuple told
    #: the operator to untick that box on every generated experiment, and unticking it is what
    #: writes 0. Evidence, same day: `style_enumeration` was given the instruction and came
    #: back 0; `surface_stop_prj_pair` was given no box instruction, came back 1, and stopped
    #: dead on `Plume surfaces`. Leaving the box out of the default means the next generated
    #: run cannot re-create the confound -- an experiment that *wants* a box state should say
    #: so explicitly, the way `surface_stop_pair_v2` does.
    #:
    #: ⚠️ `output interval` is **not** here either: it is a real `Case` field
    #: (`near_field.output_interval`) that the `.prj` carries and the exe saves back, so it
    #: belongs in the file rather than in a list of things a person has to remember.
    settings: tuple[str, ...] = (
        "all output columns",
        "No. of maximum plume rise or fall = 3",
        "stop plume at bottom hit: ticked",
        "stop plume at surface hit: **leave as loaded** -- do not untick by habit (case49 came "
        "back 0 on both runs with no instruction: operator-confirmed habit, 2026-08-26); a run "
        "that wants it moved says so here",
    )
    #: Anything else the person at the keyboard needs to know.
    notes: tuple[str, ...] = ()


def _rounds_away(value: float) -> bool:
    """Does the `.dat` echo's two-decimal rounding lose this value?

    `P-dia` and `Ttl-flo` are both printed to two decimals, which is how 0.0127 m became
    "0.01" and 0.005 m3/s became "0.01" -- two separate traps that each cost a day.
    """
    return round(value, 2) != value


def _note(experiment: Experiment) -> str:
    diffuser = experiment.case.diffuser
    effluent = experiment.case.effluent
    levels = experiment.case.ambient.levels
    currents = sorted({level.current_speed for level in levels})
    bearings = sorted({level.current_direction for level in levels})
    offset = diffuser.horizontal_angle - (bearings[0] if bearings else 0.0)

    lines = [
        f"# {experiment.name}",
        "",
        f"**Question.** {experiment.question}",
        "",
        "## Run it",
        "",
        f"1. Open `{experiment.name}.prj` in the exe. **Do not open a hand-maintained",
        "   project** -- this file exists so none has to be touched.",
        "2. Set these in the GUI, which the `.prj` cannot carry"
        f" (the output interval is **already {experiment.case.near_field.output_interval}** in"
        " the file, and needs no typing):",
        "",
    ]
    lines += [f"   - {setting}" for setting in experiment.settings]
    far = experiment.case.far_field
    if far.enabled:
        # Derived from the case rather than typed into the default tuple, so the instruction
        # cannot drift from the declared stops -- the same reason the legend is derived (row 209).
        lines += [
            f"   - far-field stop: calculation distance **{far.max_distance:g} m** and dilution "
            f"**{far.max_dilution:g}x** -- type *both*.",
            "     The exe stops at whichever binds first, the `.prj` carries neither, and an",
            "     untyped distance silently defaults to the **chronic-MZ boundary** (PLAN "
            "section 8c TODO 2).",
            f"   - far-field eddy diffusivity: **{EDDY_LAW_GUI_LABEL[far.law]}**. The selector "
            "offers three laws; `4/3 power law` is the GUI default. Check it rather than assume "
            "it:",
            "     the as-run `.prj` records the choice in far-field flags 2/3/4 (one-hot, case50), "
            "so a wrong selection is visible after the fact but only after the run.",
        ]
    chemistry = experiment.case.ambient.chemistry
    if chemistry:
        blank_ph = [level for level in chemistry if level.ph is None]
        lines += [
            "",
            f"   ⚠️ **The carbonate tab is GUI-only.** `AmbientChem_{experiment.name}.csv` is "
            "written beside the",
            "   `.prj` and can be loaded, but the **effluent** endmember and the constant",
            "   selections (K1K2, KSO4) have to be typed -- the `.prj` holds no chemistry at all.",
        ]
        if blank_ph:
            lines += [
                "",
                f"   ⚠️ **{len(blank_ph)} of {len(chemistry)} ambient rows have no pH in the case, "
                "and the GUI will not run",
                "   with a blank in that column** (found on `dose_parity`, 2026-08-25). The CSV "
                "written here",
                "   therefore carries the **PyCO2SYS solution of that row's TA and DIC** at the "
                "profile's S and T,",
                "   on the **free** scale the exe's dialog takes typed pH on. The value is "
                "**ignored** by the exe,",
                "   which derives the ambient carbonate system from TA and DIC in preference to "
                "an entered pH",
                "   (row 45, and confirmed on the ambient table by case03's KSO4 rerun: 7.5 "
                "entered in every",
                "   row left the ambient-limit pH at 8.372, where a used 7.5 would have shown as "
                "~0.9 units) --",
                "   so it is there to satisfy the GUI, and it is at least *consistent* with the "
                "columns the exe",
                "   does read. Nothing needs typing.",
            ]
    lines += [
        "",
        "3. Run. ⭐ **The exe writes the `.prj` when the model runs** -- there is no Save-As for",
        "   projects (operator, 2026-08-24) -- so the project on disk is now the *as-run* state,",
        "   GUI settings included. Nothing needs saving by hand.",
        "4. ⚠️⚠️ **Before any further run, copy both files aside** under names that say which run",
        "   they are: the next run overwrites the `.dat` **and** rewrites the `.prj`. This is the",
        "   whole reason test34/test35 came back describing a different run than they were filed",
        "   under -- a stale project file is worse than none.",
        "",
        "   ⭐ Supporting tables (ambient, DO, carbonate) *can* be saved individually, so those",
        "   survive independently of the run.",
        "",
        "## What is in the case",
        "",
        f"| ports | {diffuser.n_ports} |",
        "|---|---|",
        f"| port spacing | {diffuser.port_spacing:g} m |",
        f"| port diameter | {diffuser.port_diameter:g} m |",
        f"| vertical angle | {diffuser.vertical_angle:g} deg |",
        f"| horizontal angle | {diffuser.horizontal_angle:g} deg |",
        f"| port depth / elevation | {diffuser.port_depth:g} m / {diffuser.port_elevation:g} m |",
        f"| total flow | {effluent.flow:g} m3/s |",
        f"| effluent | {effluent.salinity:g} psu, {effluent.temperature:g} C |",
        f"| ambient current | {', '.join(f'{c:g}' for c in currents)} m/s "
        f"at {', '.join(f'{b:g}' for b in bearings)} deg |",
        f"| discharge-to-current offset | {offset:g} deg |",
        "",
        "⚠️ The `.dat` diffuser echo rounds to **two decimals**, so it will print",
        f"`P-dia {diffuser.port_diameter:.2f}` for {diffuser.port_diameter:g} and "
        f"`Ttl-flo {effluent.flow:.2f}` for {effluent.flow:g}."
        + (
            " Both lose information here."
            if _rounds_away(diffuser.port_diameter) and _rounds_away(effluent.flow)
            else " Read inputs from the `.prj`, never the echo."
        ),
        "",
    ]
    if experiment.predictions:
        lines += ["## Predicted, before the run", "", "| observable | port predicts |", "|---|---|"]
        lines += [f"| {key} | {value} |" for key, value in experiment.predictions.items()]
        lines += [""]
    if experiment.notes:
        lines += ["## Notes", ""] + [f"- {note}" for note in experiment.notes] + [""]
    record = provenance(experiment.case)
    lines += [
        "## Provenance",
        "",
        "What generated this experiment. The `.prj` cannot carry any of it -- it has no field",
        "for a version, a commit or a date -- so it lives here (PLAN.md section 7b).",
        "",
        "```",
        *record.as_comment_lines(prefix=""),
        "```",
        "",
        "`case` is a SHA-256 over the fully-resolved case. If the `.prj` beside this note is",
        "ever regenerated from a different case, that digest changes and the two stop agreeing.",
        "",
        "## Chemistry",
        "",
        "Not in the file -- no `.prj` stores it. If this run needs the carbonate module it has",
        "to be re-entered in the GUI, and the ambient chemistry table must reach **deeper than",
        f"the {diffuser.port_depth:g} m port** or the exe refuses to run.",
        "",
    ]
    return "\n".join(lines)


#: The widest output-column selection the exe has been observed to accept, as the `.prj` spells
#: the names. Generated experiments request all of it.
#:
#: ⭐⭐ **This is worth doing because the column list IS in the `.prj`.** PLAN section 5 asks for
#: old-build runs on the grounds that "the new build's UI bug blocks the extra output columns, and
#: `Time`, `P-Den`, `P-Sal`, `P-Temp` are what make a trace usable here". Confirmed 2026-08-20:
#: the bug is in the **GUI's column picker**, not in the model -- a 2026 build handed a project
#: that already names the columns prints all of them. So the constraint was never the build, and
#: `prj_from_case`'s five-column default was quietly making every generated experiment thin.
#:
#: ⚠️ These are the names as **observed**, not invented: 13 near-field and 6 far-field, read back
#: from a project the GUI saved at run time. The chemistry and DO columns are **not** here -- a
#: 21-column run exists but its project was not available to read the eight extra names from, and
#: guessing an output name that the exe then silently ignores is worse than asking for fewer.
_FULL_NEARFIELD_VARIABLES = (
    "FluxAvg-Dilution",
    "Plume-Diameter",
    "Position-Xdir",
    "Position-Ydir",
    "Plume-Depth",
    "Time",
    "Net-Dilution",
    "Plume-Density",
    "Pollutant-Conc.",
    "Plume-Salinity",
    "Plume-Temp",
    "Ambient-Current",
    "Centerline-Dilution",
)
_FULL_FARFIELD_VARIABLES = (
    "Dilution",
    "P-Width",
    "Distance",
    "Time",
    "Bckgrd",
    "Pollutant-Conc.",
)

#: Ambient side-tables the `.prj` cannot hold, as `(profile attribute, table kind, filename
#: prefix, the level fields in file order)`. The exe reads these as separate CSVs.
_SIDE_TABLES = (
    (
        "chemistry",
        TableKind.AMBIENT_CHEM,
        "AmbientChem",
        ("depth", "total_alkalinity", "dic", "ph", "calcium"),
    ),
    (
        "dissolved_oxygen",
        TableKind.AMBIENT_DO,
        "AmbientDO",
        ("depth", "dissolved_oxygen", "cbod5", "nbod5"),
    ),
)


def fill_ambient_ph(case: Case) -> list[AmbientChemistryLevel]:
    """The case's ambient chemistry levels with every blank pH replaced by a solved one.

    ⚠️ **The exe's GUI refuses to run with a blank in the ambient pH column, and it also
    ignores the column.** Both halves are measured: `dose_parity` (2026-08-25) would not start
    until a number was typed into each row, and case03's KSO4 rerun typed 7.5 into every row
    and left the ambient-limit pH at 8.372 (row 45) -- a used 7.5 would have moved it by ~0.9.
    case03's own `testco2.csv` is blank and *did* run on 2026-08-12, so the check is a
    session-state one -- but a generated file that only loads on some sessions is the failure
    `write_experiment` exists to prevent, and it arrives after the GUI is set up.

    So the value written is a placeholder in effect, and this makes it the *right* placeholder:
    PyCO2SYS's pH from the row's own TA and DIC, at the profile's salinity and temperature at
    that depth, under the case's constant selection. On the **free** scale, because that is
    the scale the exe's dialog labels typed pH with (case03 and case04 READMEs); the trace
    reports total. A row that already carries a pH is left alone.

    `warn_outside_validity` fires through the solver as usual, so an ambient outside Lueker's
    window warns here the way it would in a run.
    """
    levels = list(case.ambient.chemistry)
    blank = [index for index, level in enumerate(levels) if level.ph is None]
    if not blank:
        return levels
    view = AmbientProfileView(case.ambient)
    depths = [levels[index].depth for index in blank]
    state = solve_from_alkalinity_dic(
        [levels[index].total_alkalinity for index in blank],
        [levels[index].dic for index in blank],
        view.salinity(depths),
        view.temperature(depths),
        constants=resolve_constants(case.carbonate.k1k2_option, case.carbonate.kso4_option),
        context="ambient chemistry table",
    )
    for position, index in enumerate(blank):
        levels[index] = levels[index].model_copy(update={"ph": float(state.ph_free[position])})
    return levels


def write_experiment(experiment: Experiment, directory: str | Path) -> Path:
    """Write `<directory>/<name>/` containing the `.prj`, any ambient CSVs, and a `README.md`.

    Returns the directory written. The `.prj` is byte-formatted exactly as the exe writes
    them, which is what makes it loadable -- confirmed against the exe in Phase 1.

    ⚠️ **A chemistry or DO experiment needs its ambient side-table written too, and this used
    to omit it.** The `.prj` carries no chemistry at all (PLAN section 7b), but the *ambient*
    half lives in a CSV that we can write and the exe can load -- so writing only the `.prj`
    left the person at the keyboard to retype an ambient table by hand, which is both work and
    a fresh opportunity for the run to differ from the case that was predicted. Found the hard
    way on `case03_kso4_option3`, 2026-08-20: the exe will not run a carbonate case without an
    ambient chemistry table.

    ⚠️ The *effluent* endmember and the constant selections are still GUI-only and still have to
    be entered by hand; `_note` lists them. This closes the half that can be automated, not the
    whole gap.
    """
    target = Path(directory) / experiment.name
    target.mkdir(parents=True, exist_ok=True)
    # Ask for every column the exe is known to print. `prj_from_case` defaults to five, which is
    # the shipped example's selection and leaves out `Time` -- and a trace with no `Time` column
    # cannot be compared at the exe's own instants, which is what row 105 was retired for.
    project = dataclasses.replace(
        prj_from_case(experiment.case),
        nearfield_plot_variables=list(_FULL_NEARFIELD_VARIABLES),
        farfield_plot_variables=list(_FULL_FARFIELD_VARIABLES),
    )
    write_prj(project, target / f"{experiment.name}.prj")
    for attribute, kind, prefix, fields in _SIDE_TABLES:
        levels = getattr(experiment.case.ambient, attribute, None)
        if not levels:
            continue
        if attribute == "chemistry":
            levels = fill_ambient_ph(experiment.case)
        rows = [[getattr(level, name) for name in fields] for level in levels]
        write_csv_table(
            table_from_values(kind, rows),
            target / f"{prefix}_{experiment.name}.csv",
        )
    (target / "README.md").write_text(_note(experiment), encoding="utf-8")
    return target


# --------------------------------------------------------------- far-field session state
#
# The exe's far-field stop dialog takes a calculation *distance* and a *dilution* together and
# stops at whichever binds first. Neither reaches the `.prj` (the decoded layout has no far-field
# block at all), so both are session state -- and the archive shows the operator's entries varied:
# 500 m / 10000x usually (operator-confirmed), 5000x on seven runs, and the chronic-MZ boundary
# wherever the distance was never typed. PLAN section 8c TODO 2 carries the census; row 277 pins
# it. These two functions are how a returning run is checked against the stops its experiment
# declared, the way `nearfield_flags[1]` drift is already watched.

#: The dilution stops observed in the archive. 10000x is the operator's usual entry; 5000x
#: appears on seven traces: case03 kso4_option3, case30 d0.28, case39 spacing1000, and case47's
#: four dose runs -- which declared 10000x and came back at 5000x, the drift
#: `check_farfield_session_state` exists to catch (2026-08-26 census).
OBSERVED_DILUTION_STOPS: tuple[float, ...] = (10_000.0, 5_000.0)

#: How far past a distance stop the exe's partial final step may land. The worst archived
#: overshoot is 8.357 m (case16 test20, interval 10); interval-1 runs overshoot by under 1 m.
DISTANCE_STOP_SLACK = 15.0

#: A dilution stop is only claimed when the crossing sits within this many final rows. The exe
#: stops 1-4 rows past the crossing (measured on all eight archived dilution stops; test72 and
#: test73 are the worst at 4) -- the same lag family as the near field's rows 258b and 191b.
#: Six gives headroom while staying far below the tens-to-hundreds of rows separating a
#: crossing from the end of a distance-stopped table.
DILUTION_STOP_LAG_ROWS = 6


@dataclass(frozen=True, slots=True)
class FarfieldStop:
    """How a far-field table stopped, classified from the trace alone.

    `kind` is one of:

    * ``"distance"`` -- the run reached a typed calculation distance (`stop` names which);
    * ``"chronic_default"`` -- the run stopped at the chronic-MZ boundary echoed in the trace's
      own diffuser table, which is what the exe defaults to when no distance is typed;
    * ``"dilution"`` -- the printed dilution crossed a dilution stop within the final rows
      (`stop` names the cap), short of any distance stop;
    * ``"nan"`` -- the table ends in NaN (case09's shape);
    * ``"unknown"`` -- none of the above. A new stop shape, which is exactly what the census
      target (row 277) exists to catch.
    """

    kind: str
    #: The last printed far-field distance, m.
    distance: float
    #: The last printed far-field dilution.
    dilution: float
    #: The stop value matched -- a distance for `"distance"`/`"chronic_default"`, a dilution
    #: for `"dilution"`, `None` otherwise.
    stop: float | None = None


def classify_farfield_stop(
    dat: DatFile,
    *,
    distances: tuple[float, ...] = (500.0,),
    dilutions: tuple[float, ...] = OBSERVED_DILUTION_STOPS,
) -> FarfieldStop | None:
    """Classify how `dat`'s far-field table stopped, or `None` if it has no far field.

    `distances` and `dilutions` are the candidate typed stops -- the archive's observed values
    by default, or the single declared pair when checking a returning experiment.

    ⚠️ **Order matters, and it encodes "whichever binds first".** A distance stop is tested
    before a dilution stop because a run that reached its typed distance may *also* have crossed
    a dilution level in its final rows (case02's test1 crosses 5000x at 500.0 m exactly) --
    the distance bound it, and the dilution number is a coincidence. A dilution stop is only
    claimed when the crossing happened within the final `DILUTION_STOP_LAG_ROWS`, which bounds
    the exe's measured stopping lag of 1-4 rows (rows 258b, 191b have the same shape in the
    near field).
    """
    far = dat.farfield
    if far is None or far.empty:
        return None
    import numpy as np

    dilution = far["Dilution"].to_numpy(dtype=float)
    distance = far["Distance"].to_numpy(dtype=float)
    last_distance, last_dilution = float(distance[-1]), float(dilution[-1])

    if not math.isfinite(last_dilution):
        return FarfieldStop("nan", last_distance, last_dilution)
    for typed in distances:
        if typed <= last_distance < typed + DISTANCE_STOP_SLACK:
            return FarfieldStop("distance", last_distance, last_dilution, typed)
    chronic = _echoed_chronic_mz(dat)
    if (
        chronic is not None
        and chronic <= last_distance <= chronic + DISTANCE_STOP_SLACK
        and last_dilution < min(dilutions, default=math.inf)
    ):
        return FarfieldStop("chronic_default", last_distance, last_dilution, chronic)
    for cap in sorted(dilutions, reverse=True):
        window = DILUTION_STOP_LAG_ROWS + 1
        crossed_late = len(dilution) < window or float(dilution[-window]) < cap
        if last_dilution >= cap and float(np.nanmin(dilution)) < cap and crossed_late:
            return FarfieldStop("dilution", last_distance, last_dilution, cap)
    return FarfieldStop("unknown", last_distance, last_dilution)


def _echoed_chronic_mz(dat: DatFile) -> float | None:
    """The chronic-MZ distance from the trace's own diffuser echo, or `None` without one.

    Trace-only on purpose: nine cases have no `.prj` at all (PLAN section 9), and the echo's
    two-decimal rounding (row 141) is harmless on a mixing-zone distance.
    """
    diffuser = dat.echoed_tables.get("Diffuser")
    if diffuser is None or "ChrncMZ" not in diffuser.columns or diffuser.empty:
        return None
    return float(diffuser["ChrncMZ"].iloc[0])


def check_farfield_session_state(dat: DatFile, case: Case) -> list[str]:
    """Discrepancies between a returned trace's far-field stop and the case's declared stops.

    Empty means consistent. Run this when an experiment's trace comes back, before the
    directory graduates out of `pending/` -- the far-field analogue of watching
    `nearfield_flags[1]` for the surface-stop drift.
    """
    settings = case.far_field
    if dat.farfield is None or dat.farfield.empty:
        return ["the trace has no far-field block"] if settings.enabled else []
    stop = classify_farfield_stop(
        dat, distances=(settings.max_distance,), dilutions=(settings.max_dilution,)
    )
    assert stop is not None  # the empty case returned above
    if stop.kind == "chronic_default":
        return [
            f"the far field stopped at the chronic-MZ default ({stop.distance:.3f} m) -- the "
            f"declared calculation distance ({settings.max_distance:g} m) was never typed"
        ]
    if stop.kind == "nan":
        return [f"the far field ends in NaN at {stop.distance:.3f} m"]
    if stop.kind == "unknown":
        return [
            f"the far-field stop matches neither declared rule: last row {stop.distance:.3f} m "
            f"at dilution {stop.dilution:.1f}, against a calculation distance of "
            f"{settings.max_distance:g} m and a dilution stop of {settings.max_dilution:g}x"
        ]
    return []
