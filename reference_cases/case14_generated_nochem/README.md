# case14 — the same generated project with chemistry off

`PythonGenerated3.dat` is [case13](../case13_generated_example/)'s project — the same
`PythonGenerated.prj`, written by the port from the upstream example — run again with
**chemistry off** and the **"stop plume at surface" checkbox cleared**.

> ⛔⛔ **The `.prj` in this directory is STALE, established 2026-08-24.** It is byte-identical
> to case13's (md5 `5c60f5d3…`) and carries `nearfield_flags[1] = 1`, but the sentence above
> says this run had the surface checkbox **cleared**. The exe writes the project *every time the
> model runs* — there is no Save-As (operator, 2026-08-24) — so a genuine as-run file for this
> run could not still hold case13's flag state. What is filed here is the **generated** project,
> copied into both case directories, not the two as-run files.
>
> ⭐ **This matters well beyond bookkeeping**, because "case13 and case14 have byte-identical
> `.prj` files and stop differently" is the primary evidence behind ledger row 187 — the claim
> that the `.prj` carries no stop-at checkbox — and behind the session-state reading in §7b. The
> evidence is an artefact of a stale file. Every other data point is consistent with
> `nearfield_flags[1]` **being** the surface-stop box:
>
> | run | box at run time | `flags[1]` in its `.prj` | stopped |
> |---|---|---|---|
> | case13 | on | 1 | `Plume surfaces`, step 275 |
> | **case14 (this one)** | **cleared** | **1 — stale, see above** | ran on to step 476 |
> | 2026-08-24 `ffdefault_flag1` | left as loaded | 1, saved back unchanged | `Plume surfaces`, step 275 — **bit-identical to case13** over all 55 steps |
> | 2026-08-24 `style_default` | unticked, as instructed | 0 | trapped; never reached the surface |
>
> ⚠️ The trajectory comparisons in this file are **unaffected** — they use the printed columns of
> `PythonGenerated3.dat`, which is a real trace. What is void is any inference from the *project
> file*. [case46](../case46_surface_stop_flag/README.md) (`surface_stop_pair_v2`, graduated) is the
> controlled pair that confirms the reading directly.

Two settings changed, and between them they answer the question case13 raised and close a
loose end.

## Result 1 — the cosine correction is independent of chemistry

| run | chemistry | final diameter | cosine prediction | printed |
|---|---|---|---|---|
| case13 | **on** | 6.481 | 17 × 6.10 × cos(30°) + 6.481 = 96.288 | **96.29** |
| case14 | **off** | 7.796 | 17 × 6.10 × cos(30°) + 7.796 = 97.603 | **97.60** |

Both exact, from different diameters — so these are two independent confirmations rather
than the same arithmetic twice. The oblique-angle effective-spacing correction is a
property of the near-field model, not of the chemistry module.

### Which settles where the shipped 109.59 m comes from

The remaining candidate is a build difference, and the background supports it: **the
carbonate module exists only in the newest version of the exe**, so the shipped
`upstream/Example_project/ModelResults_TxtOutputs.dat` was necessarily produced by an
earlier build. Its 109.59 m implies an effective spacing of 0.9943 × nominal — essentially
no correction — where the current build applies cos(30°) = 0.866 to the same inputs.

**Consequence for the validation ledger:** the shipped example's far-field numbers (rows 6,
7 and 8 — wastefield 109.59 m, the 21-row far-field table, and 178.408 at 104.435 m) are
old-build values and should not be treated as targets for the current exe. The
**near-field** rows are unaffected: steps 5–275 are bit-identical across the shipped trace,
case13 and case14.

## Result 2 — "stop plume at surface" is a control in its own right

This run also had that checkbox cleared, and it explains a difference I had briefly
attributed to chemistry:

| | case13 (box ticked) | case14 (box cleared) |
|---|---|---|
| steps 5–275 | identical | identical |
| final step | **275** | **476** |
| terminating event | `Plume surfaces` | `Plume traps` |
| events | traps 255, merge 260, surfaces 275 | traps 255, merge 260, surfaces 275, local max 375, traps 476 |

The trajectories are **bit-identical through step 275** — the plume does exactly the same
thing either way. The checkbox only decides whether reaching the surface ends the run.
With it cleared the plume surfaces, sinks back, reaches a local maximum at 375 and traps
again at 476.

So it is distinct from the `max_rise_or_fall` switch (which is 2 in this project), and it is
**not stored in the `.prj`** — both runs used the same file. Like the chemistry settings, it
is session state in the GUI. `NearFieldSettings.stop_at_surface` now models it, and it is a
candidate for one of the `.prj` near-field flag positions we have not identified (2 or 6),
though we cannot yet tell.

## A note on the exe's newest build

Two UI limitations reported alongside these runs, both worth recording because they bound
what evidence we can gather:

* **Extra output variables cannot be selected** — which is why no run has more than 5
  chosen near-field columns, and why ledger row 48's wish for a wide column set is
  permanently unmet on this build.
* The chemistry module is **new-build only**, so any older trace cannot have chemistry, and
  chemistry-bearing traces cannot be compared against old-build behaviour.
