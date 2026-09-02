# case27 — the far field, with the near-field dilution varied

Generated as the experiment `farfield_bod_conversion` (note: [`EXPERIMENT_NOTE_farfield_bod_conversion.md`](EXPERIMENT_NOTE_farfield_bod_conversion.md)) and run 2026-08-18. The experiment was
designed to identify a rate-dependent amplitude that case26 had left unexplained. **It found
something else, and retired the question instead of answering it**: the exe never divides the
far-field BOD by the near-field dilution, and once that is known the amplitude was never there.

## ⚠️ The DO tab, recorded by hand

The Dissolved Oxygen tab is not saved in the `.prj` (manual §5.2.6), so these traces are
uninterpretable without this table. **Runs 1–6 did not use the values the experiment note asked
for** — the tab retained case24's defaults, and the note's H1/H2/H3 arms were never entered. This is
the third time a retained DO tab has changed what a run means (see case26's `nBOD5`), and it is why
the values below are user-supplied rather than inferred.

| field | runs 1–6 | run 7 | run 8 | run 9 | run 10 |
|---|---|---|---|---|---|
| effluent DO | 2.0 mg/L | 2.0 | 2.0 | 2.0 | 2.0 |
| IDOD | 0 | 0 | 0 | **3 mg/L** | 0 |
| cBOD5 | **20 mg/L** | **1000 mg/L** | 20 | 20 | 20 |
| cBOD decay | **0.23 /day** | **5.0 /day** | 0.23 | 0.23 | **20 /day** |
| nBOD5 | 30 mg/L | 30 | 30 | 30 | 30 |
| nBOD decay | **0.1 /day** | 0.1 | 0.1 | 0.1 | 0.1 |
| ambient | `AmbientDO_zero.csv` | zero | **`AmbientDO_one.csv`** | zero | zero |

⚠️ The nitrogenous rate is **0.1 /day here and 0.23 /day in case25 and case26**, which matters: at
0.1 the ultimate demand is 76.2 mg/L against 43.9 at 0.23, and the two are separated by the fit at
13x printed precision. Both agree with what each case recorded.

Ambient throughout: `AmbientDO_zero.csv` — DO 8.0 mg/L at every depth, both ambient BODs zero.

## The runs

Same project and same ambient in all seven. Runs 1–6 are three geometries × DO off/on, which is what
makes the finding possible: the **only** thing that differs between the three pairs is how far the
near field got.

| run | DO | stop at bottom/surface | max rise or fall | near steps | `D_near` | DO at 500 m |
|---|---|---|---|---|---|---|
| 1 | off | ticked | 2 | 275 | 169.754 | — |
| **2** | on | ticked | 2 | 275 | **169.754** | **7.266** |
| 3 | off | unticked | 2 | 476 | 217.021 | — |
| **4** | on | unticked | 2 | 476 | **217.021** | **7.267** |
| 5 | off | unticked | 3 | 572 | 246.607 | — |
| **6** | on | unticked | 3 | 572 | **246.607** | **7.258** |
| **7** | on | ticked | 2 | 275 | 169.754 | **−184.985** |

Runs 1/2 reproduce case26's near field step for step. DO is again a pure overlay: 1≡2, 3≡4 and 5≡6
in every shared column, which is row 215 confirmed on two more geometries.

## ⭐⭐ Settled: eq 28's `/D` is not in the exe

`D_near` spans **169.75 → 246.61, a 45 % increase**, with every DO input held fixed. Fitting the
demand present at the transition gives:

| run | `D_near` | fitted demand | what eq 28 requires |
|---|---|---|---|
| 2 | 169.754 | 71.39 mg/L | 71.39 |
| 4 | 217.021 | 70.49 mg/L | 55.85 |
| 6 | 246.607 | 70.18 mg/L | 49.15 |

**1.7 % spread where eq 28 demands 31 %.** The far-field demand is the effluent's *undiluted*
ultimate BOD. So the whole of eqs 24–30 reads, with nothing divided by `D`:

    DO(t) = DO_a + (DO_f − DO_a)/FF − [ L_ce(1−e^{−kc t}) + L_ne(1−e^{−kn t})
                                        − L_a(1−e^{−kc t}) ] / FF

and that form reproduces all four ordinary runs to **0.009–0.022 mg/L**, against a printed
resolution of 0.001.

## ⭐⭐ Run 7: the defect, at its full size

cBOD5 1000 mg/L into a near field that dilutes 170:1 leaves 5.9 mg/L of 5-day demand in the plume.
The exe applies all 1000 of it and prints a far-field DO of **−184.985 mg/L** — negative oxygen,
falling monotonically over 500 m, with no warning of any kind. The form above predicts −185.802,
i.e. **0.4 % of a 193 mg/L excursion**.

Run 7 is also the linearity check the experiment note asked for, at 50x rather than the 2x it
proposed: the same law holds from cBOD5 20 to cBOD5 1000, so the demand is linear in the typed value
and the "amplitude" is exactly 1.

## What this retires

Ledger row 225 consolidates the five rows this once occupied. All five were readings of a single
artefact: a cBOD5 of 20 recorded as 2000, compounded by assuming a division the exe does not
perform.

- the "unexplained factor of 4–6" (row 225) is the missing `/D` at a mis-scaled input;
- the "1.889x / 2.576x rate-dependent amplitude" is not real, and neither candidate form
  survives — the demand is eqs 24–25 exactly;
- **`nBOD5` was not negligible.** Undivided it carries 76.2 mg/L of ultimate demand and
  supplies most of the sag in runs 1–6, where the earlier arithmetic had it capped at 0.0067 mg/L.
- the ambient BOD is not specially undiluted — **nothing** is diluted, which is a simpler
  statement and a worse defect.

Rows 231 (the `1/FF`) and 235 (rates as typed, no θ) survive unchanged and are now measured over ten
traces rather than three.

## Runs 8, 9 and 10 — the three open questions, closed

Three more runs the same morning, each varying one input from run 6's baseline (the no-stop, max
rise/fall 3 geometry, `D_near` = 246.607). Between them they close everything this case left open.

| run | what changed | DO tab | far-field DO |
|---|---|---|---|
| **8** | ambient DO **varies with depth** (`AmbientDO_one.csv`: 7.0 at the surface to 10.5 at 12 m) | as runs 1–6 | 8.995 → 8.344 |
| **9** | **IDOD = 3 mg/L** | otherwise as runs 1–6 | 4.959 → 5.895 |
| **10** | **cBOD decay = 20 /day** | otherwise as runs 1–6 | 7.172 → **−0.565**, minimum **−1.863** |

### ⭐⭐ Run 9: the exe subtracts IDOD from the **ambient**, not the effluent

Eq 23 makes IDOD a property of the effluent, so it dilutes away — 3 mg/L at `D` = 246.6 should move
the DO column by 0.012. Against run 6, which differs in nothing else, it moves by **2.989**. And the
difference *grows* along the trajectory, 0.059 at `D` = 1.02 to 2.989 at the end, which is the
signature of a demand carried by the entrained water rather than by the effluent:

| form | worst | mean |
|---|---|---|
| `IDOD (D−1)/D` — subtracted from the ambient | **0.0195** | **0.0037** |
| `IDOD / D` — eq 23 as written | 2.977 | 2.618 |

Past `D` > 5 the exe's form reproduces the column to **0.0010 mg/L**, which is the printed
resolution. One symbol out of place in eq 23, and it inverts the behaviour: the demand tends to its
full value as dilution grows instead of vanishing. ⚠️ **Every other archived DO trace has IDOD = 0**,
where the two forms are identical — which is why three phases of validation could not have seen it.
It also settles matrix item D1: `DO_e` and `IDOD` are now separated, and they are not interchangeable.

### ⭐ Run 8: the far field's `DO_a` is the ambient at the trapping depth

The first stratified ambient in any far-field run, and it answers whether the missing `/D` is absent
or merely misplaced onto something else. It is **absent**: the demand still needs no `/D` (0.023
mg/L with, 0.728 without), and the mixing term works with the ambient DO at the depth the plume
trapped:

| `DO_a` used in eq 30 | worst |
|---|---|
| **ambient at the trapping depth (9.118)** | **0.023** |
| depth-mean of the profile (9.143) | 0.022 |
| surface (7.0) | 1.162 |
| deepest (10.5) | 0.742 |
| the uniform 8.0 of the other runs | 0.618 |

⚠️ **The trapping-depth value and the depth-mean cannot be separated here** — this profile puts them
0.025 apart. Both readings that differ materially are refuted; distinguishing the two would need a
profile whose mean is far from its value at the trapping depth.

The near-field path integral also gets its first real test on a varying profile — case24's ambient
spans 8→10→8 over the traversed depths, this one 7.0→10.5 monotonically — and reproduces the column
to **0.050 mg/L** worst, 0.021 mean.

### ⚠️⚠️ Run 10: an ordinary cBOD5 of 20 mg/L drives the exe negative

Run 7 needed cBOD5 1000 to reach absurdity. Run 10 gets there with **20 mg/L** — a municipal-strength
BOD — simply by typing a fast decay rate: the DO falls to **−1.863 mg/L** before the Brooks spreading
pulls it back to −0.565. That makes the defect far more reportable than run 7 did, because nobody
would type 1000 by accident and everybody types 20.

It is also the first run whose **rate is identifiable from the curve's own shape** rather than from
what was typed, because at 20 /day the exponential saturates inside the 2.74-hour far field:

| assumed rate | worst | mean |
|---|---|---|
| **20 /day, as typed** | **0.59** | **0.14** |
| 5 /day | 6.08 | 4.88 |
| 1 /day | 8.73 | 7.24 |

The implied carbonaceous ultimate converges to **19.92 against the typed 20.0**, 0.4 %. The 0.59
worst sits where the curve bends hardest and is the largest residual in the case; everywhere the
demand has saturated it is far smaller.

## Still open

- **A profile whose depth-mean is far from its trapping-depth value**, to separate the two readings
  of eq 30's `DO_a` (run 8 above).
- **Whether IDOD is also misplaced in the far field.** Run 9's far field fits to 0.046 mg/L taking
  `DO_f` from the near field, so nothing there contradicts it — but no run varies IDOD with a far
  field that would isolate a second appearance of it.
