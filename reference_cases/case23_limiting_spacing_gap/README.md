# case23 — the limiting-spacing trigger, pinned (limspc_gap)

> Pre-run experiment note, with the predictions registered before the exe ran: [`EXPERIMENT_NOTE_limspc_gap.md`](EXPERIMENT_NOTE_limspc_gap.md) (moved here from `generated/experiments/` on 2026-08-26).

**Old build**, output interval 1, **single port**, 2.0 m port depth. Generated 2026-08-13 from
a project the port wrote, to settle the one ambiguity case22 left. Identical to case22's runs
except the port depth.

## What it settles

case22 showed the rule exists — a `merging happened` banner on a single port — but could not
say what triggers it, because its banner coincided with the first trapping. Two readings fit:
a continuous threshold, or a check reached only at trapping.

This run separates them, and **both of the original guesses were wrong**.

| run | port depth | first trap | banner | diameter at trap | diameter / port depth |
|---|---|---|---|---|---|
| `limspc_shallow` | 1.0 m | step 180 | **step 180** | 2.277 | **2.277** |
| `limspc_gap` | 2.0 m | step 176 | **step 176** | 2.028 | **1.014** |
| `limspc_deep_control` | 5.0 m | step 146 | none | 1.419 | 0.284 |

**The check is gated on trapping.** The banner lands on the first trapping step in both runs
that fire. It cannot be continuous: `limspc_shallow`'s diameter passed its port depth at step
**126**, fifty-four steps before the banner.

**The threshold is `diameter > port depth`, not twice it.** Every trapping event in all three
runs, including the ones that did not fire:

| diameter / port depth at a trap | banner |
|---|---|
| 0.284, 0.539 | no |
| **1.014** | **yes** |
| 2.277 | yes |

which brackets the threshold to **(0.539, 1.014]** — consistent with exactly 1.0. The gap run
is a knife-edge: it fired at 1.4 % above its port depth, having been 0.3 % below one step
earlier.

⚠️ **This differs from the Visual Plumes source on both counts.** That code checks
`diameter > 2 * depth` continuously. Our exe checks `diameter > depth` at trapping. So
PLUMES2.0 is not simply the UM3 in that repository — a useful thing to know before trusting
it anywhere else.

## ⚠️ A correction to case22's write-up

case22 claimed the rule "caps a runaway", citing the exe's 5.141 m against a predicted 8.1 m.
**That comparison was invalid** — it compared our model integrated past the point the exe
stopped. Sampled at the exe's own printed times, our maxima are 4.28 / 5.40 / 5.73 m against
3.62 / 4.42 / 5.14 m: **15–20 % high, not a factor of two**, and there is no merging in our
model on a single port at all, so nothing here is being capped.

The genuine runaway evidence remains test34/test35, where our merged diameter reaches 4.148 m
against the exe's 2.020 m **at matched times**.

## Accuracy on these runs

Early jet, first 100 steps: dilution **0.04 %**, diameter **0.65 %**. Whole run: dilution
13–18 %, diameter 8–12 % — the same late-trajectory drift seen everywhere, not something
specific to this geometry.

## Not implemented

The trigger is pinned but nothing acts on it, for a stated reason: it needs **run history** —
"has this plume trapped yet?" — which the solver's right-hand side, a pure function of the
state vector, cannot express. It needs a latch. And the payoff sits inside the late-trajectory
drift that is not understood yet, so adding it now would be tuning against noise.
