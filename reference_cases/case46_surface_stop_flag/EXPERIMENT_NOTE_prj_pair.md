# surface_stop_prj_pair — run 2026-08-24, and the procedure it was given was impossible

⛔ **This experiment's instructions were wrong, and the runs are kept because they answered two
other things.** It asked for "two Save-As operations, do not run the model". **There is no Save-As
for projects** (operator, 2026-08-24): the exe writes the `.prj` when the model *runs*. So the
experiment as written could not be performed, and the operator did the only thing available —
ran it. The corrected version is [`../surface_stop_pair_v2/`](../surface_stop_pair_v2/README.md).

## What is in this directory

| file | what it is |
|---|---|
| `asrun_flag1.prj` | the project as the exe saved it. ⭐ **Byte-identical to what the generator wrote**, `nearfield_flags[1]` still **1**, `output_interval` still 5 |
| `ffdefault_flag1.dat` | run with the far-field distance **left untyped** |
| `ff500_flag1.dat` | run with the far-field distance **typed as 500 m** |

A third file, `ModelResults_TxtOutputs.dat`, was byte-identical to `ffdefault_flag1.dat` and was
deleted rather than archived as a duplicate — the archive already carries ten such pairs (§8d).

## ⭐ Finding 1 — ledger row 277 confirmed out of sample, on its first new data

The two traces are **byte-identical over their whole near field** (lines 1–79) and differ *only*
in the far field. `experiments.classify_farfield_stop`, written the day before and never run on
these, classified both correctly:

| trace | terminal distance | classified | check against the declared stops |
|---|---|---|---|
| `ffdefault_flag1.dat` | 104.421 m | `chronic_default` (chronic MZ = 102.0 m) | ⚠️ *"the declared calculation distance (500 m) was never typed"* |
| `ff500_flag1.dat` | 501.908 m | `distance`, stop 500.0 m | consistent |

That is exactly what row 277's census says the exe does — stop at whichever bound is typed, and
default the distance to the chronic-MZ boundary when none is — reproduced on one case with
everything else held fixed. `check_farfield_session_state` caught the untyped run without being
told anything.

## ⭐⭐ Finding 2 — `nearfield_flags[1]` looks like the surface-stop box, and row 275b may be *ours*

This run's README gave **no stop-box instruction**, so the boxes were left as loaded. The project
came back with `flags[1]` **unchanged at 1**, and the trace **stopped dead on `Plume surfaces` at
step 275** — case13's exact behaviour.

The same day, `style_enumeration` *was* told "stop plume at surface hit: **unticked**", and its
saved project came back with `flags[1]` **1 → 0** (and `output_interval` 10 → 1, matching the
other instruction it was given).

⚠️⚠️ **So the flip attributed to the exe in row 275b may simply be the operator following our own
README.** `plumes2.experiments`' default settings tuple has said *"stop plume at surface hit:
unticked"* on every generated experiment for weeks — which would explain, with no exe misbehaviour
at all, why "every generated run comes back with `nearfield_flags[1]` flipped from 1 to 0".

⚠️ **Not settled, because the pair is one-sided.** The `flags[1] = 0` run
(`style_enumeration/style_default.dat`) never reaches the surface — it traps at 2.27 m — so it
cannot show that unticking changes where a run *stops*. And the archived counter-evidence is
still standing: `case13` and `case14` have **byte-identical** `.prj` files, both `flags[1] = 1`,
and case13 stops at `Plume surfaces` (step 275) where case14 prints the same banner and runs on to
step 476. Under this reading one of those two archived projects must be **stale** — never
re-saved by the run it is filed with — which is a failure mode §7b already records twice
(test19, test34/test35).

`surface_stop_pair_v2` is the controlled pair that settles it: one project, one geometry, the box
the only thing that moves, and the copy step made explicit so each run survives the next.
