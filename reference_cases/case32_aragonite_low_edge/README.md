# case32 — five chemistries down one trajectory, and the aragonite edge lands on 25

Run 2026-08-19. case13's project at **output interval 1**, chemistry on, five different effluent
endmembers and **nothing else changed**. It pins the aragonite band edge, rules out the last
competing explanation for it, and — because five entries share one trajectory — turns out to
settle three other rows for free.

| run | entered TA | entered DIC | entered pH | `R_arg` rows |
|---|---|---|---|---|
| `chem_1` | 4000 | **0** | 10.5 | 76 |
| `chem_2` | 4000 | 1000 | 10.5 | 76 |
| `chem_3` | 4000 | 2000 | 10.5 | 76 |
| `chem_4` | 3000 | 2000 | 10.5 | 76 |
| `chem_5` | 5000 | **0** | 10.5 | 76 |

Ambient chemistry: TA 1800, DIC 1600, pH 7.8 at 0/5/10/15 m (`AmbientChem_*.csv`). K1K2 = 10,
KSO4 = 1. Effluent 0 psu at 2.63 °C into a uniform 32 psu ambient.

## ⚠️ `P-Sal` did not get selected, and it did not matter

The request asked for `P-Sal` beside the carbonate columns; the exe came back with the twelve
above and no salinity. It cost nothing, because of what the control found.

## ⭐⭐ The control: five chemistries, one trajectory, bit for bit

Every run agrees with `case31/surface_off.dat` — a **sixth** run, with no chemistry at all — on
all five shared hydrodynamic columns across all 572 steps, **worst difference 0.0**. And with
each other.

So the salinity column in `surface_off` describes these runs too, and joining it to `chem_N` by
step is not an approximation. Row 215's "a scalar overlay does not perturb the hydrodynamics"
was measured on two families; this is a third, and the only one that varies the *strength* of
the overlay rather than its presence.

## ⭐⭐⭐ The edge is 25 psu, and saturation state is not what sets it

Joining `surface_off`'s printed `P-Sal` to each run's `R_arg`:

| run | last row with `R_arg > 0` | first row with `R_arg = 0` | Ω_A at the switch |
|---|---|---|---|
| `chem_1` | S = **24.895** | S = **25.035** | 6.153 → 6.058 |
| `chem_2` | 24.895 | 25.035 | **9.036** → 8.876 |
| `chem_3` | 24.895 | 25.035 | 6.563 → 6.459 |
| `chem_4` | 24.895 | 25.035 | **3.997** → 3.951 |
| `chem_5` | 24.895 | 25.035 | 7.453 → 7.329 |

**The same step in all five.** The edge brackets to **(24.895, 25.035]** — 0.14 psu, down from
0.69, from a *printed* salinity rather than a reconstructed one, and it contains 25.0.

⭐ And Ω_A at that switch runs from **3.997 to 9.036**, a factor of 2.3, while the switch does not
move at all. Saturation state was the last surviving alternative explanation — case03-versus-
case13 argued against it across two runs, and this settles it inside one trajectory with
everything else held fixed. **The trigger is salinity.**

**The prediction registered before the run** — "switches at the first row whose printed `P-Sal`
reaches 25.0, resolved to about 0.1 psu" — holds.

## ⭐⭐ The low-band law, on 380 rows instead of 15

`R = exp(1.53)(Ω_A − 1)^2.33`, the dialog's constants with no fitting:

| run | worst relative error |
|---|---|
| `chem_1` | 2.09e-4 |
| `chem_2` | 1.34e-4 |
| `chem_3` | 1.63e-4 |
| `chem_4` | 3.44e-4 |
| `chem_5` | 1.25e-4 |

A free two-parameter fit over all 380 rows returns **logK 1.53001, N 2.33000** — the dialog to
five decimals, across a 2.3× range in Ω and a 1.7× range in entered TA.

## ⭐⭐ Row 45's input pairing, decided by construction

`chem_1`/`chem_5` enter **DIC = 0**; the rest enter a real DIC. All five enter pH 10.5. What the
exe printed on its first row says what it did with them:

| run | entered | printed DIC | printed pH |
|---|---|---|---|
| `chem_1` | TA 4000, DIC 0, pH 10.5 | **2155.6** ← computed | 10.438 |
| `chem_5` | TA 5000, DIC 0, pH 10.5 | **2692.9** ← computed | 10.446 |
| `chem_2` | TA 4000, DIC 1000, pH 10.5 | 1011.8 ← used | **11.995** ← computed |
| `chem_3` | TA 4000, DIC 2000, pH 10.5 | 1992.2 ← used | **10.843** ← computed |
| `chem_4` | TA 3000, DIC 2000, pH 10.5 | 1992.2 ← used | **9.789** ← computed |

**`DIC = 0` means "not supplied"** and selects TA + pH; any non-zero DIC wins and the entered pH
is discarded — the printed pH is nowhere near the 10.5 typed into all five.

And the computed DIC is *ours*. Backing the endmember out of the first row and asking PyCO2SYS
for TA + pH → DIC at 0 psu / 2.63 °C, K1K2 = 10:

| | exe endmember | PyCO2SYS, free scale | NBS |
|---|---|---|---|
| `chem_1` (TA 4000) | 2166.14 | **2166.49** (+0.35) | 2233.85 (+67.7) |
| `chem_5` (TA 5000) | 2713.68 | **2714.52** (+0.84) | 2797.15 (+83.5) |

Under one µmol/kg on an endmember the port has never been tested against, and NBS excluded by
two orders of magnitude. ⚠️ Free and total coincide at S = 0 — no sulfate — so this run confirms
row 122's scale choice against NBS but cannot separate free from total on its own.

## ⭐⭐ Row 46's density scaling, tested where it predicts *nothing*

Row 46 says the exe multiplies the entered effluent TA and DIC by ρ_eff/1000 — measured as
**1.026952** on case03 at 35 psu / 10 °C, the +110 µmol/kg excess. Here the effluent is fresh and
cold, so ρ_eff/1000 = **0.99996** and the rule predicts the excess simply vanishes:

| run | entered TA | endmember backed out | ratio |
|---|---|---|---|
| `chem_4` | 3000 | 2998.90 | 0.99963 |
| `chem_1`–`chem_3` | 4000 | 3997.94 | 0.99949 |
| `chem_5` | 5000 | 4996.98 | 0.99940 |

It does. ⭐ That is a **held-out test of the mechanism, not of the number**: a fixed additive
offset or a fixed percentage would have shown up here just as it did on case03, and neither does.
The residual 0.05 % is the wrong sign for a scaling and is consistent with precipitation removing
TA between the port and the first printed row, where `R_cal` is at its largest.

## Still open

- **The 35 edge from a printed salinity.** This plume tops out near 31.9 psu. That edge is
  bracketed to (34.924, 35.094] by reconstruction — 0.17 psu, tight enough that a run is hard to
  justify.
- **Free versus total pH scale**, which needs a saline effluent to separate.
