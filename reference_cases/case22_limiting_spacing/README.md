# case22 — the limiting-spacing rule (limspc_shallow, limspc_deep_control)

> Pre-run experiment notes, with the predictions registered before the exe ran: [`EXPERIMENT_NOTE_limspc_shallow.md`](EXPERIMENT_NOTE_limspc_shallow.md), [`EXPERIMENT_NOTE_limspc_deep_control.md`](EXPERIMENT_NOTE_limspc_deep_control.md) (moved here from `generated/experiments/` on 2026-08-26).

**Old build**, output interval 1, **single port**, generated 2026-08-13 from projects the port
wrote itself (`plumes2.experiments`) — the first runs in the archive whose `.prj` was not
hand-edited, and the first with predictions registered **before** the run.

Both runs are one port at 0.20 m, 0.005 m³/s, discharged **downward at −45°** so the plume
sinks away from the surface and can grow wide while staying submerged. Effluent 35 psu /
10 °C into the case03 ambient profile, 0.02 m/s current. **Only the port depth differs.**

| run | port depth | `2 × port depth` | merging banner | max diameter |
|---|---|---|---|---|
| `limspc_shallow` | 1.0 m | 2.0 m | **yes, step 180** | 5.141 m |
| `limspc_deep_control` | 5.0 m | 10.0 m | **none** | 3.618 m |

## The rule is real, and it fires on a single port

UM3 sets a limiting spacing equal to the port depth once the element diameter exceeds twice
that depth, and — with **no port-count guard** — declares the plume merged at the same moment.
A single port cannot merge with anything, so a `merging happened` banner here can only come
from that rule. **It appears.** The control, with the threshold moved out of reach, produces
none. Both predictions were registered in advance and both hold.

⚠️ **An earlier version of this file claimed the rule "caps a runaway", citing 5.141 m against
a predicted 8.1 m. That comparison was invalid** — it compared our model integrated past the
point the exe stopped. Sampled at the exe's own times our maxima are 15–20 % high, not double,
and a single port merges nowhere in our model, so nothing here is capped. See case23.

## ⚠️ What the pair did not settle — ✅ now settled by case23

The banner fires at step 180, diameter **2.277 m** — a ratio of **2.28 × port depth**, not the
2.00 the source implies. The diameter crossed 2.0 m seven steps earlier, at step 173, and
there is **no discontinuity in growth** at the banner (1.73 % per step before, 1.65 % after),
so nothing visibly changes in the geometry when it fires.

`Plume traps` fires at **the same step 180**. So two readings survive:

1. the threshold is continuous but the constant is ~2.28 rather than 2.00; or
2. the check is only reached at trapping, and the condition (`diameter > 2 × port depth`) was
   already satisfied by then.

Both fit both runs — the control traps at a diameter/threshold ratio of 0.14 and never crosses,
so it cannot separate them.

✅ **case23 (`limspc_gap`, a 2.0 m port) settled it, and both readings above were wrong.** The
check *is* gated on trapping — this run's diameter passed its port depth at step 126, fifty-four
steps before the banner — but the threshold is **`diameter > port depth`**, not twice it,
bracketed to (0.539, 1.014] by every trapping event across the three runs.

## Also confirmed here

- **Termination**: both runs end on the 4th turning point with the switch at 3 — shallow
  trap/maxrise/trap/maxrise at 180/315/428/527, control at 146/292/412/521. Consistent with
  ledger row 183.
- ⚠️ **The `.prj` does not carry output-variable selection.** These runs came back with a
  different column set and order from the archive's, chosen in the GUI. Another entry for
  PLAN.md §7b.
