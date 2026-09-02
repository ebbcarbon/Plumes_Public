# case43 — the port-count sweep: what actually sets the merged suppression (test71–test76)

Run 2026-08-21, from a suite **designed rather than re-cut from the archive** (see
`reference_cases/pending/README.md` as it stood at the time). It answers two things the archive
could not, and one of them was never testable at all.

Six runs at **0.5 m spacing, 35 psu, 65° horizontal, output interval 1**, with the **per-port flow
held fixed at 2.0×10⁻⁴ m³/s** so every individual plume is identical and only the number of
neighbours changes. The exe's flow field is the *total*, so each run entered a different number
there.

| run | ports | port | total flow | rows | merges | onset `D` | max `d/L` |
|---|---|---|---|---|---|---|---|
| **test71** | 1 | 0.0127 m | 0.0002 m³/s | 407 | ⚠️ step 373 | — | control |
| **test72** | **2** | 0.0127 m | 0.0004 m³/s | 438 | step 204 | 57.0 | 9.75 |
| **test73** | **6** | 0.0127 m | 0.0012 m³/s | 454 | step 204 | 57.0 | 7.04 |
| **test74** | **25** | 0.0127 m | 0.0050 m³/s | 461 | step 204 | 57.0 | 6.18 |
| **test75** | 25 | **0.0254 m** | 0.0200 m³/s | 508 | step 166 | 26.8 | 8.32 |
| **test76** | 1 | **0.0254 m** | 0.0008 m³/s | 439 | ⚠️ step 331 | — | control |

✅ **The design held.** All three base-port arms merge at **step 204** and onset dilution **57.0**,
identical to three figures — which is the per-port-flow control working exactly as intended: same
plume, different number of neighbours. None of the six hit the 5 001-step cap.

⚠️ Both controls trip the limiting-spacing rule anyway — test71 at step 373, test76 at step 331 —
so each is clean only before its own banner, which bounds every ratio below. Rows 261 and 268 again,
now on **single-port** runs at a 0.5 m spacing.

## ⭐⭐⭐ The port count is a first-order variable, and the brake already had it right

Suppression is the merged run's `d(ln D)/dt` over its **own single-port control's** at the same
instant, over `d/L` 1.5–3.0.

| ports | exe | ours, `ALL` | offset | ours, `NONE` | offset |
|---|---|---|---|---|---|
| 2 | **0.733** | 0.796 | +0.063 | 1.017 | +0.284 |
| 6 | **0.605** | 0.658 | +0.053 | 0.855 | +0.250 |
| 25 | **0.568** | 0.619 | +0.051 | 0.793 | +0.225 |

**A 0.165 spread across port count at a fixed spacing** — comparable to row 260d's 0.198 across
spacings, so this is a variable of the same order and nothing had measured it.

⭐⭐ **And the brake reproduces its *shape* almost exactly.** The decrements between successive
port counts:

| | n 2→6 | n 6→25 |
|---|---|---|
| exe | **−0.128** | **−0.037** |
| ours, `ALL` | **−0.138** | **−0.039** |
| ours, `NONE` | −0.162 | −0.062 |

8 % and 5 % out. **That confirms UM3's `out_of_plane = 1/n_ports`** — the factor that distributes
cross-current entrainment over the merged group, and the only place the port count enters our model.
It had never been tested against a port-count sweep because the archive has none.

⭐⭐ **The brake's residual at fixed spacing is one constant.** `+0.056` mean, spread **0.012**
across a twelvefold range of port count, against the default's `+0.253` and spread 0.059. That is a
very different object from row 264b's sign-changing residual across *spacings* (−0.071 to +0.145),
and it localises what is left: at fixed spacing the brake is a constant offset from the exe; the
part that changes sign belongs to the spacing.

## ⭐⭐⭐ First test of published pair theory against UM3, and it holds

Cenedese & Linden (2014) — `references/` — solve two coalescing axisymmetric plumes from first
principles and give an effective entrainment constant that is our suppression ratio under another
name, with a merged asymptote of **`2^(-1/2)` = 0.707**. Nothing in the archive was a pair, so the
number had never been testable.

**test72 measures 0.733** — within **3.7 %** of the theoretical asymptote.

⚠️ **The approach curve does not match, only the asymptote.** Their eq 2.12 declines from 0.855 to
0.707 over our window; the exe reads 0.719 / 0.725 / 0.756 across the three bins — essentially flat
and already at the asymptote, with a slight *rise*. So UM3 lands on the right merged value without
following the theoretical approach to it, which is what one would expect of a closure that switches
on a merge flag rather than solving the coalescence.

⭐ **And it retires the reading that the exe suppresses "more than theory".** That was inferred from
the 25-port runs (0.53–0.77 against theory's 0.71–0.84). At the port count the theory actually
describes, the exe agrees. The extra suppression in the archive is the **row**, not a disagreement
with plume physics — which is what a row *should* do, since a row of plumes tends to a line plume
and not to a single axisymmetric one.

## ⚠️ The `d/L`-versus-`z*` arm: the level is not set by `d/L`, and our small difference has the wrong sign

test75 doubles the port at the same spacing, so `d/L` at any point on the trajectory is ~1.4× the
base run's while `z* = α z / L` is unchanged.

| | exe | ours, `ALL` |
|---|---|---|
| test74, base port | 0.568 | 0.619 |
| test75, wide port | **0.542** | **0.641** |

The exe moves **0.026** — 4.6 % — across a 1.4× change in `d/L`. So the level is **not** a function
of `d/L`, which corroborates row 266 from a second direction: at fixed spacing and port count, how
fat the plume is barely matters.

⚠️ **Ours moves the other way.** We predicted the wide port slightly *higher* (0.641 against 0.619)
and the exe reads it slightly *lower*. Both differences are small — ±0.03 against a 0.5–0.7 level —
but the sign is wrong, and it is recorded rather than rounded away.

⚠️ test75 is also the suite's worst arm for accuracy — 10.53 % post-merge braked against 4.30–5.95 %
for the other three — and it has the lowest onset dilution (26.8 against 57.0), which is row 267b's
axis pointing the same way it did on test32 and case42.

## Accuracy, and the case for the default moving

Post-merge dilution MARE at the exe's own printed times:

| run | `NONE` (the default until 2026-08-21) | `WALK` | `ALL` (the default since) |
|---|---|---|---|
| test72, n=2 | 19.55 % | 6.57 % | **5.95 %** |
| test73, n=6 | 17.19 % | 5.24 % | **4.63 %** |
| test74, n=25 | 19.31 % | 4.92 % | **4.30 %** |
| test75, n=25 wide | 32.35 % | 10.93 % | **10.53 %** |

`ALL` is **3–4× better than the shipped default on every arm**, with no case in this suite where the
default wins. Combined with case42's 36× (row 267) and with UM3's own documented mechanism now
pointing at `ALL` (see `references/README.md`), the evidence against `NONE` as a default is
substantial — and the one case that still favours it, case20's test32, is a single run whose 1.01 %
sits *below* its own unmerged control's 1.39 % (row 177), which is the signature of cancelling
errors rather than of correctness.

✅ **Our pre-registered suppression predictions were exact** — 0.796 / 0.658 / 0.619 / 0.641 braked
and 1.017 / 0.855 / 0.793 / 0.822 default, all reproduced to three decimals. And the registered
prediction that the default would *enhance* entrainment at two ports (1.017 > 1, which the theory
forbids) is confirmed against a measured 0.733.
