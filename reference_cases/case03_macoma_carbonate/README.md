# case03 — Macoma with carbonate chemistry (the important one)

Pulled 2026-08-12 10:22. **This is the case the project exists to reproduce**: an
alkalinity-elevated effluent, with the exe reporting TA, DIC, pH, Ω and
precipitation rates through the plume.

⚠️ **The 2 m port spacing in this project is a unit slip relative to the site** (operator,
2026-09-01): Macoma's ports sit at 2 *feet* (0.6096 m) — the Dec-2025 original stored "2.0"
under the `.prj` feet flag (row 49), and the 2026 re-entry took it as metres. The archive stays
as entered: every parity number measured here is a valid exe comparison at 2 m. Site-facing work
(`studies/ebb_dose_study/`, `examples/run_macoma.py`) carries the corrected 0.6096 m.

| File | Role |
|---|---|
| `test2_TxtOutputs.dat` | **golden trace** — 41 near-field rows × 13 cols, plus a 24-row far-field table |
| `test.prj` | project file, 143 lines — saved correctly this time |
| `testco2.csv` | ambient carbonate profile: depth, TA, DIC, pH *(blank)*, Ca |
| `testdiffuser.csv`, `macoma2effluent.csv`, `macoma2ambient.csv`, `macoma2mixzone.csv` | unchanged inputs |

## It is a controlled overlay on case02

The near-field columns `step, Dilutn, P-dia, x-posn, y-posn, Depth` are
**bit-identical** to [case02](../case02_macoma_mgd/) in all 41 rows. So chemistry
does not feed back on the hydrodynamics — it rides on top as a scalar-transport
plus speciation calculation. That is a clean, valuable structural fact, and it
means we can develop and test the chemistry against a plume we already match.

It also **recovers case02's lost settings**. `test.prj` is the same project saved
12 minutes later, and identical hydrodynamics require identical hydrodynamic
inputs, so case02 had aspiration 0.100, contraction **1.000**, max rise/fall **3**.

⚠️ Correction to the case02 write-up: contraction changed from 0.610 (case01) to
1.000, so case01→case02 was **not** a single-variable change. The differences were
flow unit, contraction coefficient, ambient current at 15 m, output interval, and
the variable lists.

## Chemistry output format

Near-field: the 5 selected variables plus **7 automatically appended** chemistry
columns.

```
    Dilutn  P-dia  x-posn  y-posn  Depth        TA       DIC        pH   OmegaC  OmegaA     R_cal     R_arg
                                          (mmol/m3) (mmol/m3)   (total)      ()      () (umol/hr) (umol/hr)
```

Far-field: 3 selected variables plus **5 appended** (`TA, DIC, pH, OmegaC,
OmegaA` — no rates).

`test.prj`'s near-field name list holds only 5 names and the far-field list 3, so
**chemistry columns are not selectable — they are appended when the module is on.**
The `.dat` writer needs to model that.

Units: the output header says **`mmol/m3`** and pH **`(total)`**. But the GUI takes
TA, DIC and Ca in **µmol/kg**, and no conversion happens between the two (see
"Effluent chemistry" below) — so one of those two labels is wrong by ~2.7 %.

## Answers to open questions

- **The `AmbientChem` pH column is optional.** `testco2.csv` leaves it *blank* on
  every row and the model runs, computing pH from TA + DIC. The example project's
  internally-inconsistent `pH = 7.80` was a stale/ignored value. More generally the
  exe appears to accept **any two of TA / DIC / pH** and derive the third — for the
  *effluent* it used TA + pH and ignored `DIC = 0`.
- **Input units are µmol/kg** (TA, DIC, Ca), per the GUI. Output pH is total scale
  even though the effluent pH was entered on the free scale, so the exe does convert
  pH scales.

## Effluent chemistry — resolved (2026-08-12, from user)

Entered in the GUI: **TA 4000 µmol/kg, DIC 0 µmol/kg, pH 10.5 free scale,
K1K2 option 10, KSO4 option 1.** Ambient `Ca` is also µmol/kg.

None of this is stored in `test.prj` — 143 lines with no chemistry block and no
value resembling any of it. So the chemistry state (endmembers, enable flag, chem
CSV name, constant options) is **session-only**, and a `.prj` we write can never
round-trip chemistry into the exe.

### What the model actually transported

A two-parameter least-squares fit of conservative mixing over all 41 rows
(`C_p = C_eff/S + C_amb·(S−1)/S`) recovers both endmembers cleanly:

| | fitted (output units) | entered | max residual |
|---|---|---|---|
| TA effluent | **4110.16** | 4000 | 1.49 |
| TA ambient | **2900.49** | 2900 | " |
| DIC effluent | **1645.18** | **0** | 0.58 |
| DIC ambient | **2499.90** | 2500 | " |

Three conclusions, in order of confidence:

**1. `DIC = 0` was treated as "not specified"; the exe used TA + pH.**
TA 4000 µmol/kg with pH 10.5 on the **free** scale at S=35, T=10, K1K2=10, KSO4=1
gives DIC = **1646.29** µmol/kg via PyCO2SYS, against the fitted **1645.18** —
0.07 %. The other three pH scales give 1602–1670 and fit worse. Note that
(TA 4000, DIC 0) would imply pH ≈ 11.0, not 10.5, so the three entered values were
mutually inconsistent and the exe silently picked a pair.

**2. There is no µmol/kg → mmol/m³ density conversion anywhere.** Ambient TA and
DIC are transported at their raw entered values (2900.49 vs 2900; 2499.90 vs 2500),
not ×ρ/1000 (which would give 2969 and 2560). The DIC match in (1) also required no
conversion. **So the output header's `(mmol/m3)` is inconsistent with the GUI's
µmol/kg input by ~2.7 % at seawater density** — one of the two labels is wrong.

**3. The +110 µmol/kg on effluent TA is the exe's own high-pH bias, not a unit
conversion.** Since (2) rules out a density factor, the transported 4110.16 must
come out of the exe's own TA/pH/DIC solve. And the magnitude checks out: near
pH 10.44 the alkalinity sensitivity is dominated by hydroxide,
d[OH⁻]/dpH ≈ 2.3·[OH⁻] ≈ 2250 µmol/kg per pH unit, so +110 µmol/kg ≈ 0.049 pH — the
same size as the **+0.068 pH** offset we independently measure against PyCO2SYS near
pH 10 (below). One systematic bias, showing up in two places.

Conclusion (3) is an inference, not a measurement. **The diagnostic that would
settle it:** re-run with `DIC = 1646` entered and **pH left blank**. If the
transported TA then comes out 4000 rather than 4110, the excess is an artifact of
the TA+pH path.


## PyCO2SYS comparison — the headline result

Feeding the exe's own reported TA and DIC, with the depth-interpolated S/T, back
into PyCO2SYS using **the exe's own declared options (K1K2 = 10, KSO4 = 1)**,
total pH scale, no unit conversion:

| exe pH range | n | mean Δ pH | max abs Δ pH |
|---|---|---|---|
| 8.3 – 9.0 | 33 | +0.015 | 0.027 |
| 9.0 – 9.6 | 6 | +0.036 | 0.048 |
| 9.6 – 10.1 | 2 | **+0.068** | **0.077** |

Overall RMS Δ pH **0.025**, max **0.077**. The exe reads systematically *low*, and
the gap grows with pH.

**Critically, using the exe's declared constants makes the agreement worse, not
better.** Scanning all of PyCO2SYS's `opt_k_carbonic` options gives RMS Δ pH of
0.013–0.020, best at options 2/11/17 — while option 10, which the exe actually
used, sits at 0.021–0.025. So **this is an implementation difference in the
alkalinity model, not a constants-selection mismatch.** Worth confirming: before we
knew the options, a settings artifact was still on the table.

The discrepancy scales with hydroxide — a linear fit gives
Δ pH ≈ 5.4×10⁻⁴·[OH⁻] + 0.014 (R² 0.83, [OH⁻] spanning 3.4–146 µmol/kg) — so there
is an OH⁻-dependent term plus a ~0.014 pH baseline offset. Borate is the other
likely contributor.

Separately, **Ω_calcite/Ω_aragonite = 1.5725 in the exe vs 1.5836 in PyCO2SYS**, a
constant 0.23 % difference across every row. A clean, separable Ksp formulation
difference, unrelated to the pH bias.

**This is the "limits of the current software" question answered, and the limits
bite exactly where we care.** An alkalinity-elevated discharge has its highest pH
near the port, which is where the exe and PyCO2SYS part company. It makes the
planned PyCO2SYS backend a substantive improvement rather than a refactor.

## Two suspected bugs

1. **`R_arg` is 0.000 in every single row** while `R_cal` ranges from 24 268 down
   to 168 µmol/hr. Aragonite precipitation being identically zero while calcite is
   large is not physical — Ω_arag is 4.5–22.9 throughout, i.e. strongly
   supersaturated. Looks like an unimplemented or short-circuited branch.
2. **The `Ca` column appears to be ignored for Ω.** Confirmed µmol/kg, so
   `Ca = 100` is ~100× *below* seawater calcium (~10 300 µmol/kg), which would drive
   Ω down by ~100×. Instead the reported Ω_arag matches a salinity-derived calcium to
   0.18 % at the far end of the plume. So the exe is not using the entered Ca for
   saturation state. It may still feed the precipitation rates — untested, and a
   re-run with `Ca = 10300` would settle it (§ questions).

   Consistent with the upstream example, which has `Ca = 0` and still produces Ω.

## Far-field

Runs with the unmerged advisory, 10 m interval, 4/3-power law, 24 rows, ending at
**212.356 m** against a 207 m chronic MZ. The chemistry barely changes across it
(TA 2902.167 → 2900.188), as expected once dilution is already 562.

On where the far-field stops — now three data points, still unresolved:

| Case | chronic MZ | interval | last distance | overshoot |
|---|---|---|---|---|
| example | 102 m | 5 m | 104.435 | 2.435 |
| case02 | 207 m | 100 m | 501.611 | 294.611 |
| case03 | 207 m | 10 m | 212.356 | 5.356 |

The example and case03 overshoot by roughly half an interval; case02 blows past by
almost 300 m. case02's `.prj` was lost, so we can't compare its far-field flags.
Is there a max-distance or max-dilution field in the far-field dialog?

## `.prj` flag blocks across all three saved projects

| | example | case01 | case03 |
|---|---|---|---|
| effluent unit flags | `[1,1,1,1,1]` | `[1,2,1,1,1]` | `[1,1,1,1,1]` |
| aspiration / contraction / light abs. | 0.100 / 1.000 / 0.160 | 0.100 / **0.610** / 0.160 | 0.100 / 1.000 / 0.160 |
| near-field flags | `[1,1,0,2,1,1]` | `[1,0,0,3,1,0]` | `[1,0,0,3,1,1]` |
| output interval | 5 | 5 | 10 |
| chemistry in output | no | no | **yes** |

Position 4 is confirmed as the max rise/fall switch. Positions 2 and 6 remain
unidentified — and note **position 6 is `1` in both the example and case03 but the
example has no chemistry output**, so position 6 is *not* the chemistry enable.
Combined with the total absence of chemistry data in `test.prj`, the chemistry
state looks like it simply isn't saved.

That has a consequence for us: our YAML case format will have to represent
chemistry ourselves, and a `.prj` we write can never round-trip chemistry back
into the exe.

## ⭐⭐ 2026-08-20: the KSO4 selector's borate half **is** honoured — and the ambient pH column is not

`kso4_option3.dat` is this case rerun with the carbonate dialog's KSO4 selector moved from **1** to
**3** — Dickson bisulfate either way, Uppström borate against Lee (2010). §7.6d asked for it because
case03's pH residual against PyCO2SYS has a *sevenfold* smaller spread under Lee borate than under
Uppström, which is the signature of the right salinity dependence rather than a coincidence.

⚠️ **Compare on step number, not row index.** This run is at output interval 1 (410 rows) against
the archived trace's interval 10 (41 rows), so a row-for-row comparison lines up step 1 against step
10 and reports differences of a whole pH unit that are pure misalignment. Aligned on step, 41 steps
are common.

**The hydrodynamics are bit-identical** — `Dilutn`, `P-dia` and `Depth` all differ by exactly 0 on
all 41 shared steps, which is row 215's overlay finding holding again, and it is what licenses
reading any difference below as chemistry.

| column | max abs difference | mean |
|---|---|---|
| `pH` | **0.006** | −0.0047 |
| `DIC` | 7.18 | −1.53 |
| `OmegaC` | 0.181 | −0.108 |
| `OmegaA` | 0.114 | −0.068 |
| `R_cal` | 353.2 | −54.3 |
| `TA` | **0** | 0 |

So the selector is **not** cosmetic: the output is not byte-identical, and pH falls by 0.003–0.006.
The sign is right for Lee — Lee (2010) gives a few per cent more total borate than Uppström, so more
of the alkalinity is borate alkalinity, carbonate alkalinity is lower, and pH falls. `TA` moving by
exactly zero is the check that the endmember itself did not change.

⚠️ **Registered prediction: at the bottom edge.** The note predicted "the printed pH column moves by
0.005–0.013" if the borate half is honoured. Measured max is **0.006** and the mean **0.0047** — the
max is inside the band, the mean marginally below it. Recorded as the low end rather than rounded in.

### ⭐⭐ And a confound that turned into its own finding: the ambient pH column is inert

⚠️ Two inputs differed between the runs, not one. The exe **refuses to run a carbonate case without
an ambient chemistry table**, and **will not run with the pH column empty either** -- so the rerun
was made with **7.5 entered in every row**, where this case's own `testco2.csv` leaves that column
**blank**. On paper that voids the comparison.

⭐ **And the blank archived file is itself informative.** `testco2.csv` has the pH column empty and
the archived run exists, so the "must be a number" requirement is a **GUI-session constraint, not a
file-format one**: a CSV with blanks loads, but the table editor will not run until something is
typed. Worth knowing before generating a chemistry experiment, and it is why `plumes2.experiments`
now writes the CSV with the blanks intact and warns in the note instead of inventing a value.

**The data rules it out.** If an ambient pH of 7.5 were being used, the plume would be driven toward
it as it dilutes — at a dilution of 563 the element is essentially ambient water. It is not: run B
prints **pH 8.372** there against the archived 8.377, and `dpH` is **flat at −0.003 to −0.006 across
a 460× range of dilution** (correlation with log dilution is weak and the endpoints differ by 0.002).
A used ambient pH of 7.5 would show as a ~0.9 unit divergence at the ambient limit.

⭐ So **the ambient chemistry table's pH column is ignored when DIC is present**, which extends row
45's "DIC wins when non-zero" from the *effluent* endmember to the *ambient* table — a pairing that
had only ever been measured on the effluent side. And it means the KSO4 comparison above is clean
after all: the only input with any effect was the selector.

⚠️ **What this does not settle.** That the selector does *something* of about the right size is not
the same as confirming option 1 is Uppström and option 3 is Lee. §7.6d's question — which
parameterisation the exe actually applies — needs our own PyCO2SYS pH computed under both borate
options against *both* traces, and matched on the spread rather than the mean. That is now possible
with two runs instead of one, and it is the outstanding half.
