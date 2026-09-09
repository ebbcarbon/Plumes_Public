# case19 — the ambient-current sweep (test27–test30)

**Old build**, output interval 1, all output columns, **single port** so merging is
impossible. Generated 2026-08-12 to determine the forced-entrainment closure, which is the
last genuinely undocumented piece of the near field.

Base is test24: 1 port, 0.0127 m diameter, 5e-5 m³/s (the archived 0.005 ÷ 100), 45° vertical
/ 90° horizontal, 2 m port depth, 15 m elevation, effluent 35 psu / 10 °C, contraction 0.61,
aspiration 0.1, rise/fall 3. Only the **near-field ambient current** changes; the far-field
speed stays at 0.02 m/s because the exe will not accept zero there.

| run | ambient current | rows | first max rise |
|---|---|---|---|
| test27 | 0.02 m/s (rerun of test24) | 365 | 204 |
| test28 | 0.01 m/s | 472 | 211 |
| test29 | 0.05 m/s | 318 | 204 |
| test30 | 0.10 m/s | — | — |

## test27 proves the exe is deterministic

test27 is **byte-identical** to test24 — same 54 076 bytes, same 365 rows, same four event
steps. So identical inputs give identical output: no randomness, no timing dependence, and a
fully deterministic step controller. That answers the reproducibility half of PLAN.md §7.2
and it is what makes byte-exact `.dat` comparison a reasonable Phase 6 target.

## What the sweep showed: the cross-flow closure is wrong

Fitting the cross-flow weight `k` independently at each current, on runs that are otherwise
identical:

| current | best `k` | MARE at best `k` | MARE at `k = 0` |
|---|---|---|---|
| 0.01 m/s | 0.05 | 0.36 % | 0.67 % |
| 0.02 m/s | 0.25 | 1.82 % | 3.27 % |
| 0.05 m/s | 0.45 | 5.22 % | 9.56 % |

Two things, both damning for a cross-flow-only `A_p`:

1. **`k` does not transfer.** It climbs monotonically with the current, so there is no single
   coefficient. Transplanting the 0.02 value onto the 0.01 run makes it *worse* than omitting
   the term entirely (1.67 % against 0.67 %).
2. **The achievable error degrades with current**, 0.36 % → 1.82 % → 5.22 %. A closure with
   the right functional form would hold roughly constant. The error grows with exactly the
   quantity the term is supposed to account for.

At 0.01 m/s the two observables also disagree *within* the run: dilution prefers `k ≈ 0.05`
while the final downstream position prefers `k ≈ 0.40`.

So `ForcedEntrainment.cross_flow` **defaults to 0** — a documented omission rather than a
number that is right for one case. The near field is validated to 0.28–0.46 % on zero-current
runs and degrades to ~10 % as the cross-flow grows, and closing that needs Frick's actual
projected-area decomposition, which neither manual reproduces.

⚠️ This supersedes an earlier reading in which `k = 0.25` looked confirmed because it also
improved test21 and test26. Those two sit at the *same* 0.02 m/s current as the run it was
fitted on, so their agreement carried no information about the velocity dependence.

## 2026-08-13: what the sweep finally settled

The fit above is superseded twice over. Re-run as a *prediction* against the three-term
projected area (no free coefficients), the sweep failed — and chasing that failure is what
produced the two results below. Both come from measuring each entrainment term directly from
these traces' printed columns, since the element thickness cancels out of every specific rate.

⚠️ **Use test23 as the control before trusting any such measurement.** With `U_a = 0` the
forced term is identically zero, so the residual measures only the method's own error. It
comes out at ≤5 % of the Taylor term. The first attempt at this measurement skipped the
control and was wrong by a factor of two — the `.dat` `P-Den` column is already full density
(1026.9), not sigma-t, and adding 1000 to it halved every term.

### 1. The Taylor shear velocity is relative to the ambient

Taking the shear as `|V|`, the way the UM report writes it, the Taylor term **alone exceeds**
the total entrainment the exe applied. Forced entrainment would have to be a sink. The
deficit deepens with the current — 6 %, 21 %, 49 %, 76 % of the Taylor term at 0.01, 0.02,
0.05 and 0.10 m/s — which is itself the signature of a missing `− U_a`. Under
`alpha |V − U_a|` the residual is positive across the whole late jet in all four runs.

Every zero-current run in `case18` is blind to this, because the two forms are identical
there. That is why it survived three phases of validation.

### 2. The projected area is right in shape, attenuated in magnitude

The measured forced term over the published unit-weight PAE is a factor `f` that is not
constant but collapses onto the single dimensionless group `r = |U_a| / |V|`:

| `r` | 0.10 | 0.20 | 0.30 | 0.40 | 0.50 | 0.60 | 0.70 | 0.80 | 0.90 |
|---|---|---|---|---|---|---|---|---|---|
| `f` | 0.22 | 0.37 | 0.54 | 0.66 | 0.72 | 0.77 | 0.81 | 0.85 | 0.87 |

The four currents agree to ±0.03 within a bin while `f` sweeps 0.22–0.87 — so this is a
property of the model, not of one run. The trajectory elevation angle was tested as the
alternative collapse variable and **fails**: at fixed angle the runs spread by a factor of
two. No fitted curve for `f` is implemented; it would be tuned on the only runs available to
check it.

### Why these four runs could do what no single run could

`test27`–`test30` are identical but for the current, and `test23` is the same case at zero
current. That makes `R(t) = ln D(U_a) / ln D(0)` at matched times a model-free measurement of
the current's entire contribution. The exe's `R` **saturates** — 1.40 at 0.10 m/s, then turns
over. Relative shear reproduces the turnover; absolute shear grows past 1.56 and keeps going.
