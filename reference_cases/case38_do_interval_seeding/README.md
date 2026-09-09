# case38 — the DO accumulator seeds at step 1, and the output interval proves it

Run 2026-08-19 to settle ledger row 220, which had been claiming one thing, then two contradictory
things, and could not decide because **every DO trace in the archive printed every step**. With
the first printed row always at step 1, "seeds at the first printed row" and "seeds at step 1"
are the same statement. Varying the output interval separates them.

case29's project geometry throughout. Only the output interval and the effluent DO change.

| run | interval | effluent DO | first printed step | `D₀` | `DO₀` | `DO₀·D₀` |
|---|---|---|---|---|---|---|
| `i1_do2` | 1 | 2.0 | 1 | 1.0200 | 1.9610 | **2.0002** |
| `i3_do2` | **3** | 2.0 | 3 | 1.0600 | 2.2150 | 2.3479 |
| `i5_do2` | **5** | 2.0 | 5 | 1.1020 | 2.4590 | 2.7098 |
| `i1_do5` | 1 | **5.0** | 1 | 1.0200 | 4.9020 | **5.0000** |
| `i1_do10` | 1 | **10.0** | 1 | 1.0200 | 9.8040 | **10.0001** |
| `i5_do10` | **5** | 10.0 | 5 | 1.1020 | 9.7050 | 10.6949 |

## ⭐⭐⭐ The accumulator starts at step 1, not at `D` = 1 and not at the printed grid

Back the entrained ambient out of the first printed row two ways. Against `D` = 1 it is incoherent:

| run | `(DO₀·D₀ − DO_e)/(D₀ − 1)` |
|---|---|
| `i1_do2` | 0.011 |
| `i3_do2` | 5.798 |
| `i5_do2` | 6.959 |
| `i5_do10` | 6.813 |

Against **step 1's dilution of 1.0200** it is one number:

| run | `(DO₀·D₀ − DO_e)/(D₀ − 1.0200)` |
|---|---|
| `i3_do2` | **8.697** |
| `i5_do2` | **8.656** |
| `i5_do10` | **8.475** |

An ambient DO of about 8.5–8.7 mg/L, recovered from three different intervals and two different
effluent seeds without being told it. That is the answer: **`DO·D = DO_e − IDOD` at step 1, with
no entrained credit, and the integral runs from there.**

## What this settles, and what it corrects

✅ **Row 220's original claim was right**, and is now stated precisely. "The path integral starts
at the first printed step" is true only because every earlier trace ran at interval 1; the rule is
that it starts at **step 1**, whose dilution is 1.0200 in this geometry.

❌ **The reading recorded earlier on 2026-08-19 — that case24 and case25 disagree, so the exe
matches neither pure seeding — was the wrong conclusion drawn from a real observation.** The
observation stands (case25 does prefer a `D` = 1 seeding by 3×), but attributing it to the seeding
rule was wrong: these six runs pin the rule directly, with no fitting, and it is step 1.

⚠️ **So case25 is now the anomaly, and a smaller one.** Under the confirmed rule its residual is
0.0225 mg/L against case24's 0.0035 — six times worse but still 45 printed digits, and no longer
evidence about seeding. Its ambient DO is the one thing about it the archive has never confirmed:
its own README records that run 1's profile was *not* the one the experiment asked for, recovered
only by forward-modelling. Runs 2 and 3 are assumed uniform 8.0 on the strength of the near-field
DO topping out at 7.965.

⭐ **The seed itself is exact and independent of everything.** `DO₀·D₀` reproduces the typed
effluent DO to 2 parts in 10⁴ at 2.0, 5.0 and 10.0 mg/L, which also confirms that `DO_e` enters
undivided and undiminished — the effluent-carried half of row 250.

## ⚠️ These runs are sub-critical and go NaN

The project is case29's, at a 0.5 m port. All six terminate in NaN once the plume leaves
the water column and run on to the 5001-step cap, so only the finite prefix is usable — which is
ample, since everything above is read from the first printed row.

## Names (2026-09-09)

The exe wrote these files under the names on the left; renamed the same day, contents byte-identical (the `.dat` header still echoes the original project title): `Macoma2.prj` → `project.prj`.
