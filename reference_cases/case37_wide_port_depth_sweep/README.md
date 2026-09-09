# case37 — the depth axis at a wide port, and the regime boundary is located

Run 2026-08-19, the discriminator case36 asked for: **port depth swept at a fixed 0.5 m port**,
so the axis moves alone. One port, 0.005 m³/s, downward at −45°, 35 psu into the case03 ambient,
output interval 1.

| run | port depth | first trap | `d >` depth | first local max | banner | lag past `max(trap, cross)` | regime |
|---|---|---|---|---|---|---|---|
| `d0.50_dep1.5` | 1.5 m | 214 | **192** | 372 | **214** | **0** | **A** — on the trap |
| `d0.50_dep2.0` | 2.0 m | 208 | 211 | 372 | **227** | **16** | **B** — mid-trajectory |
| case35 `d0.50_q5.0` | 2.4 m | 203 | 227 | 369 | **369** | 142 | **C** — on the local max |
| `d0.50_dep2.5` | 2.5 m | 202 | 233 | 368 | **368** | 135 | **C** |
| `d0.50_dep3.0` | 3.0 m | 196 | 278 | 364 | **364** | 86 | **C** |

## ⭐⭐⭐ Along one axis the regimes are ordered, and the boundary is 2.0–2.4 m

With port diameter and salinity held fixed, increasing the port depth walks the run **A → B → C**
in order, and the B/C boundary is bracketed to **(2.0, 2.4] m**. That is the first time any single
parameter has moved the regime cleanly, and it is only visible because case36 showed depth alone
does *not* set the regime — at a 0.2 m port, 2.4 m is still regime A.

So the regime is set by at least depth **and** port diameter together, and this sweep fixes the
boundary along one of them.

⚠️ **The lag is not monotone even inside C** — 142, 135, 86 as the depth goes 2.4, 2.5, 3.0 —
which is the same point case36 made from the other side: in regime C the banner is at the local
maximum, so the lag measures where the *trajectory* turns, not what the check is doing.

## What moves underneath

The two events the banner might attach to move in opposite directions as the port deepens:

| depth | first trap | crossing | crossing − trap |
|---|---|---|---|
| 1.5 m | 214 | 192 | **−22** |
| 2.0 m | 208 | 211 | +3 |
| 2.5 m | 202 | 233 | +31 |
| 3.0 m | 196 | 278 | +82 |

A deeper port traps sooner and crosses later, so the crossing slides from before the trap to long
after it. ⚠️ **That ordering does not decide the regime either**, and case36 is the counterexample:
its 2.4 m / 0.2 m run has a crossing 20 steps *after* its trap and is still regime A with a lag of
1, while its 45 psu run at a gap of +2 is regime B with a lag of 24.

## ⭐⭐ A fifth repeat, and a second one that differs only in column order

`d0.50_dep2.0` reproduces case30's `gap_4`. Like case33's `sal35`/`gap_1` pair it is **not**
byte-identical — the same thirteen columns came back in a different order — but exact on every
number: **13 columns × 648 rows, worst difference 0.0**.

That is now two independent instances, and the cause is known: **the exe writes the columns in the
order they were picked from the output dropdowns** (confirmed by the user). So it is a GUI-ordering
effect, not a numerical one — byte-identity between two runs needs the same *selection sequence* as
well as the same inputs, which is what bounds row 191c's claim.

## Still open

Nothing here explains *why* a run lands in A, B or C — only that depth orders them at a fixed
port. The remaining cheap probe is the same sweep at a **third** diameter, say 0.3 m, to see
whether the B/C boundary moves smoothly with port diameter or jumps.
