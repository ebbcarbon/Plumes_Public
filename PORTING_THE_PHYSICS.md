# Porting the physics

**For the people at Ebb who will use this model.** It assumes you know what the discharge is and
why we care about the plume; it does not assume you have read the plan documents
([`notes/PLAN.md`](notes/PLAN.md) and the build log behind it) or the manuals.

One question runs through all of it. This is a port of a Windows executable whose source we do not
have, written against manuals that the executable itself does not always obey. So for every
equation there were three candidate answers — what the manual says, what the exe does, and what is
physically right — and they are **not always the same**. This document is about the places where
they diverge, what the port does at each one, and how far you can push the numbers before the
answer stops being trustworthy.

---

## 1. What to trust

Everything below is measured against runs of the real executable, archived in `reference_cases/`
with their inputs recorded. Every figure is re-checked on demand — `plumes2 validate` runs the
whole ledger and prints ours, the reference, and the error.

⚠️ **Coverage is published, not implied.** 195 of the 195 countable findings in
[`LEDGER.md`](notes/LEDGER.md) are executable; the rest are marked with a named reason for why no
measurement of ours can add to them. A validation report that shows only what passes is worse
than none.

| what | how close to the exe | where it degrades |
|---|---|---|
| **Near-field dilution, jet phase** | **0.31 %** still water; **0.34–0.88 %** at 0.01–0.10 m/s | worst at the strongest cross-flow |
| Near-field dilution, whole trace | 0.74 % | **1.7 % after the plume traps and starts oscillating** |
| Plume diameter, jet phase | ~0.9 % | as above |
| **Merged plumes, shallow overlap** (`d/L` < ~2.4) | **1.0 %** — no worse than the same case unmerged | — |
| **Merged plumes, deep overlap** (`d/L` > ~4) | **29 %**, and the element over-inflates **11.9x** | ⚠️ **do not use** — see §2, and the experimental brake below |
| **Brooks far field** | 4.8×10⁻⁴ in dilution, against the exe's own calculator | nothing found |
| Carbonate pH | 0.024 pH on the exe's own TA and DIC | see §4: the exe and PyCO2SYS genuinely disagree |
| Ω aragonite | 3.4 % near field, **2.2 % far field** — a bounded, recorded offset, not a match | same cause |
| Precipitation rates | 5 significant figures | — |
| **Near-field dissolved oxygen** | **0.0063 mg/L** over four traces | — |
| Far-field dissolved oxygen | 0.009–0.10 mg/L | **0.59 mg/L at a 20 /day decay rate** — the archive's most extreme, and where this model is weakest |
| File I/O | byte-exact, **every archived trace** and every `.prj` | — |

**The floor is 0.31 %, and it is not ours.** The exe computes seawater density with a sigma-t
relation that differs from EOS-80 by about 0.036 kg/m³. That offset propagates into buoyancy and
therefore into dilution, and it sets a floor no amount of closure work can go below. A result
*better* than 0.31 % would be evidence that something had been fitted rather than derived, which is
why the test suite asserts a lower bound as well as an upper one.

**Where to be careful.** The late-trajectory drift is real: once the plume has trapped and begun to
oscillate, dilution runs about 1.7 % off. If you care about a number at the end of a long
oscillating trace rather than in the jet, treat it as ±2 %, not ±0.5 %.

⚠️⚠️ **And do not trust a tightly-spaced diffuser.** Merging is reproduced well while neighbouring
plumes are just touching, and badly once they are deeply overlapped. The control is the ratio of
plume diameter to port spacing, `d/L`: below about 2.4 the model is as good as the same case with
no merging at all, and by `d/L` ≈ 4 it is **29 % wrong on dilution** while the element inflates to
**11.9×** the diameter the exe reports. Worse, the *sign* is wrong — the executable's element stops
growing under deep confinement and ours runs away — so this is not a tolerance to widen but a
regime to stay out of. **Check `d/L` at the end of your run before quoting a number from it.**
This is ledger rows 157b and 186, and it is the largest open problem in the near field.

✅ **The confined-decrement correction is now the default**, as of 2026-08-21, and the numbers
above are what the *retired* default gave. `ConfinedDecrements.ALL` evaluates eqs 51–54's decrements
at the *confined* half-height rather than the round-equivalent one — which is where the runaway came
from, since every entrainment area is already built from the confined radius.

**Why it moved**, in order of weight:

1. ⭐ **UM3's own documented mechanism selects it.** Aspiration entrainment is taken "only over the
   surfaces still exposed to ambient fluid", and for eq 55's truncated circle that exposed fraction
   *is* the decrement evaluated at the confined radius. The retired default matched no statement in
   any reference — it was simply how this port was first written.
2. **Out-of-sample accuracy**: 0.98 % post-merge on case42, against the old default's 35.53 %, on a
   case the correction had no part in designing. And 3–4× better on every arm of case43.
3. **It is the only setting that respects a physical bound.** At two ports the old default predicted
   a suppression of 1.017 — *enhancement* — where coalescing-plume theory bounds the ratio below 1
   by construction and the exe measures 0.733.
4. **Its residual is a constant** across port count, where the old default's was a function.

### What this means for the numbers you use

| | old default | **now** |
|---|---|---|
| merged, deep overlap (`d/L` 4–10) | 15–35 % | **1–7 %** |
| element over-inflation | up to **11.9×** | **1.0–1.8×** |
| merged, moderate overlap (`d/L` ~2.3) | 1.0 % | **5.2 %** |

⚠️ **The one place it is worse is moderate overlap**, and that trade was made deliberately. The
1.0 % it gave there sits *below* the same case run with no merging at all (1.4 %) — an error smaller
than the unmerged control is the signature of cancelling errors, not of correctness.

⚠️ **A residual remains and it is spacing-dependent.** Our suppression is offset from the exe's by
about +0.12 at a 0.30 m spacing and −0.08 at 0.80 m — smooth, measured on six spacings, and not yet
explained. If you need a merged number to better than ~10 %, check the spacing against
`reference_cases/case44_spacing_sweep/`.

⚠️ Set `MergingChoices(confined_decrements=ConfinedDecrements.NONE)` to recover the old behaviour;
every ledger row it re-baselined records what it read before.

---

## 2. Seven places the exe contradicts its own manual

These are the substance of the port. In each case the manual says one thing, the traces say
another, and we followed the traces — because the traces are what the exe actually did, and parity
with the exe is the point of a port. Each is measured, not argued.

### The velocity profile is parabolic, not 3/2-power

The reference specifies a 3/2-power profile, which gives a peak-to-mean ratio of 3.89. Every
archived trace under the exe's **default** profile says **2.0000**, exactly, on 8 617 unmerged rows
with zero exceptions — which is the parabolic value. Merged, it becomes exactly 1.5, the parabolic
value for a slab instead of a round element. Both fall out of the geometry with nothing fitted.
⚠️ The exe *offers* the manual's 3/2 profile and a (very peaked) Gaussian as non-default options
(case48: 3.89 and 3.67); it defaults away from its own manual. The port implements all three plus
the literature's Gaussian (`near_field.similarity_profile`), parabola by default.

**What this means for you:** centreline concentrations are *half* the flux-averaged value, not a
quarter of it. If you are reading a peak concentration against a permit limit, this is a factor of
two.

### The entrained ambient is path-integrated, not evaluated where the plume ends up

The manual's eq 23 reads as simple algebra: mix effluent with ambient at the plume's depth. Taken
literally it misses the exe's own dissolved-oxygen column by 0.218 mg/L. What fits, to 0.0063, is
integrating the entrained ambient **along the trajectory** — every parcel of water the plume
swallowed on the way, at the depth where it swallowed it.

This is the reference's stated intent rather than a departure from it: the 3rd edition says in as
many words that a plume rising from an oxygen-poor basin ends up "very nearly the same as the deep
water", and names the phenomenon *forced upwelling*. Eq 23 is the special case where the ambient
happens to be uniform.

**What this means for you:** in a stratified water column, what the plume carries reflects where it
has *been*, not where it stops. For a discharge into a stratified receiving water this is not a
correction, it is the mechanism.

### Two different spacings, for two different things

The port carries two reductions of the port spacing and they are not interchangeable:

- the **wastefield width** uses `spacing × |cos(heading − current)|`
- the **merge trigger** uses `(L/2)·|sin ψ|` against the plume's *instantaneous* bearing

An earlier version of this project fitted a single ellipse to cover both. That fit was wrong, was
flagged as suspect in the ledger, and was eventually deleted — but not before it survived for weeks
in the code with a docstring arguing for it. The derived law reproduces the 85°, 30° and 0° cases
with **no fitted constant**, and predicted three merge points at different spacings before they
were run.

### Merging inherits a bug from UM3, and we reproduce it

The half-angle `phi` is computed with a division inside the radical — `arctan(sqrt((b²−s²)/s))` —
which is dimensionally wrong and happens to be correct only when the spacing is exactly 1 m.
Reproducing it gives 1.01 % post-merge; using the true geometry gives 4.04 %. So the buggy form is
the default, and `faithful=False` opts out.

⚠️ Worse, the exe is *inconsistent between its own two angles*: the merged-radius inflation matches
the true angle while the entrainment decrements match the buggy one. We measured them separately
and reproduce each as found. This is not a reading anyone would choose; it is what the binary does.

### The DO/pH exclusion is not enforced

The manual (§5.2.6) says dissolved oxygen and pH calculations cannot be run together. The exe runs
them together quite happily and prints both column sets, with DO identical to the DO-only run over
all 526 rows. Our `Case` therefore does **not** refuse the combination.

### The far field never dilutes its oxygen demand — see §3

The largest of them, and it belongs with the defects.

---

### The linearly-varying eddy-diffusivity width has a factor of two the manual's eq 11 does not

The manual prints the Brooks width under the linear law as `w/w₀ = 1 + 2βx/w₀`. The exe prints
`w/w₀ = 1 + βx/w₀` — reproduced to 1.7×10⁻⁴ on every row of the first linear-law trace (case50,
2026-08-26) — and the derivation agrees with the exe: `ε ∝ w` integrates to `w = w₀ + 12ε₀x/(u w₀)`.
The dilution formula beside it (eq 15) already carried the right factor, so only the width was
affected. ⚠️ **The port had transcribed the manual's form**, and no archived trace could have caught
it until a run under that law existed; it is corrected (ledger row 280b).

**What this means for you:** the constant and 4/3 laws were never affected. If you quoted a far-field
*width* under the linear law from a port build before 2026-08-26, it was 57–87 % too wide; the
dilutions were right.

## 3. Defects we reproduce only on request

Five behaviours are, as far as we can tell, simply wrong. The port computes the **corrected** form
by default and reproduces the exe's behind an explicitly named flag, so that anyone comparing
against an exe run can get parity without anyone getting a wrong answer by accident.

| flag | what the exe does | why it matters |
|---|---|---|
| `reproduce_undiluted_bod` | applies the effluent's **undiluted** ultimate BOD to the far field — eq 28's `/D` is absent | a discharge diluted 170:1 exerts the demand it had at the port |
| `reproduce_idod_on_ambient` | subtracts the immediate oxygen demand from the **entrained ambient** instead of the effluent | IDOD *grows* with dilution instead of vanishing |
| `reproduce_undersaturated_nan` | evaluates `(Ω−1)^N` unguarded, returning NaN for Ω < 1 | one undersaturated row poisons an entire run |
| `reproduce_aragonite_band_gap` | reports exactly zero aragonite for `25 ≤ S ≤ 35` | its dialog declares one continuous `0 < S < 35` band, and it evaluates that band normally *below* 25 — so the zero is a gap in the middle of ordinary seawater, not a floor |
| `reproduce_effluent_concentration_scaling` | multiplies **effluent** TA and DIC by density in kg/L, leaving ambient alone | a µmol/kg treated as µmol/L; biases the endmember 2.7 % high |

**The first two are the ones to know about**, because together they are not a small error. The
demand that dilution should remove is instead delivered by it, and the consequence is unbounded:

- an ordinary **municipal-strength cBOD5 of 20 mg/L**, with a fast decay rate typed in, drives the
  exe's predicted far-field dissolved oxygen to **−1.86 mg/L**;
- a 1000 mg/L discharge reaches **−185 mg/L**;
- an ambient BOD above a threshold flips the sign, and the plume *gains* oxygen without limit — one
  archived run reports 100 mg/L, nine times saturation.

No warning, no clamp, no NaN. If you are ever handed a far-field DO number from the executable,
this is the first thing to check. All three are reproduced by this port to within 0.4–2 % of the
excursion, which is how we know the mechanism is understood rather than guessed.

---

## 4. Where there is no reference at all

**Ω brucite is the reason this project exists, and it is the one number with nothing to check it
against.** The exe reports saturation states for calcite and aragonite only. When alkalinity is
added — especially when the feedstock is Mg(OH)₂ — the near-field pH spike can drive the water
supersaturated with respect to brucite, and runaway brucite precipitation removes the very
alkalinity the discharge was meant to deliver. `Ω_aragonite` cannot see that happening.

On the dosed archived-diffuser case: **Ω_brucite = 131.4 at the port, 0.010 by 100× dilution** (on Xiong
(2008)'s `log Ksp` = −10.95, adopted 2026-08-24; the superseded −11.16 read 213). Aragonite moves by
a factor of 5 across the same trajectory; brucite moves by four orders of magnitude.

⚠️ **The risk window is centimetres, not tens of seconds — corrected 2026-08-25.** This document
used to say "the first ~30 seconds and first ~100× of dilution", read off a three-row table whose
second row *was* 30 s. Sampled densely, Ω_brucite falls through 1 at a dilution of **1.7**, **0.27 s**
and **1.1 cm** from the port on case03's own dose (TA 4000 at pH 10.5), and at dilution **12**,
**5.7 s**, **16 cm** at the most extreme dose tried (TA 20 000 at DIC 2500, port pH 12.0). ⭐ The
reason is worth more than the numbers: with Mg²⁺ conserved, `Ω_brucite = 1` is a **pH threshold** —
**pH ≈ 9.41 (total) at S 32, T 10 °C** on that `Ksp` — and the dose only sets how much dilution it
takes to fall to it. So the thermodynamic window is the jet's first few diameters, which the exe's
output interval cannot resolve and which sits *inside* any regulatory boundary: on case03 both mixing
zones are Brooks far-field numbers and read Ω_brucite ≈ 0.009 at every dose. A study that reports Ω
only at the boundaries reports no brucite risk at all. See `studies/dose_dry_run/`.

⚠️ **Three caveats, and they are not decorative.**

1. **No parity target exists.** Validation comes from analytical limits, internal consistency
   against Ω_aragonite from the same speciation, and the literature. The ledger labels this
   `internal` rather than `golden`; every other number in the project is `golden`.
2. **It is an upper bound, and as of 2026-08-21 the bound is measured rather than asserted.**
   Every known bias pushes the same way, which is what makes "upper bound" a usable statement
   instead of a hedge: ion pairing is not modelled (a tenth of seawater magnesium is complexed,
   more as pH rises), total rather than free concentrations are used, and the Davies equation sits
   at the **optimistic** end of its own quoted range while being applied past that range. At
   S = 32, T = 11 °C:

   | term | how much it can move `Ω` |
   |---|---|
   | `log Ksp` — Xiong (2008)'s −10.95 **± 0.2** (was the uncited −10.9 to −11.3 spread; same width) | **2.51×** |
   | activity coefficients across their quoted seawater bounds | **2.14×** |
   | temperature, 25 → 10 °C | 1.007× — negligible |
   | **both dominant terms, worst case** | **5.37×** |

   ⚠️ **Quote the 5.37× as a bound, not an error bar.** It combines independent worst cases; the
   terms are not independent and the true spread is narrower. ⛔ **And two of these figures were
   wrong until they were measured** — the activity term was published as "10–20 %" and temperature
   as "5 %". If you have quoted a brucite uncertainty from this document before that date, it was
   too small. **The absolute value is indicative; the salinity and pH trends are sound**, and they
   rest on much firmer ground than the constant does.
3. **Ω is a thermodynamic statement, not a rate.** Supersaturation is necessary but not sufficient
   for precipitation — there is a nucleation barrier, and seawater sits supersaturated in aragonite
   routinely without precipitating. Do not infer alkalinity loss from Ω without a kinetic model.

### The model now tells you when a constant is out of range

⭐ **New on 2026-08-21, and it matters most for exactly this work.** The carbonate constants were
each fitted over a temperature and salinity window, and the exe's default — Lueker et al. (2000) —
was fitted over **S 19–43, T 2–35 °C**. An alkalinity-elevated discharge is a high-salinity,
high-pH plume *by construction*, so leaving that window is normal rather than exotic: case07's
effluent is already 45 psu.

A run that leaves the window now emits a `ConstantRangeWarning` naming the option, its window, how
far outside the run actually went, and **what share of the run was outside** — the last being what
separates one sample grazing the edge from an entire plume being extrapolated. It says which end of
the mixing line is at fault, because the fixes differ: an out-of-range *effluent* is your input and
you can change it, an out-of-range *plume* is a consequence of mixing and you cannot.

⭐ **It is often actionable rather than merely a caveat**, because it tracks the option you selected
rather than one fixed window: 45 psu is outside Lueker and *inside* Millero et al. 2006 (option 13,
S 1–50), so choosing a constant set that covers your plume is a real remedy.

⚠️ **It does not tell you how wrong the number is.** A fitted window is where the fit was checked,
not a cliff edge. Half a unit outside is probably fine; twenty units outside probably is not. The
warning exists so you can ask the question, not so the model can answer it. ⚠️ Numbers produced
before this existed carry no such signal — nothing distinguished an extrapolated pH from an
interpolated one.

⭐ **And since 2026-08-25 there is a second window, on the pH itself.** The fitted window is in S
and T only, so the first dose dry run solved pH-12 seawater inside it and nothing spoke. A
`PHRangeWarning` (a `ConstantRangeWarning` by inheritance, so existing filters catch it) now fires
when a solved pH leaves **7.5–12.05 (total)** — not a fit range but the range in which this port's
chemistry has been *compared to anything*.

⭐⭐ **The ceiling was 10.5 for about six hours.** It started at case03/case04's port pH, the top of
the archive; the four `pending/dose_parity` runs came back the same afternoon and put the exe's own
CO2SYS at pH 9.148 → 11.988 on case03's geometry at TA 4000–20 000 with DIC 2500. Across 2050 rows
the exe reads **0.011–0.025 below** PyCO2SYS and the gap **narrows** above pH 11.5 rather than
diverging — so an alkalinity dose curve's pH is parity-checked to 0.025 over its whole range, which
is the single most useful thing the exe comparison has produced. ⚠️ The 0.05 above 12.0 is stated
headroom: the highest point actually compared is 12.008.

### The exe's chemistry and PyCO2SYS genuinely disagree

Not a porting artefact — a real difference, and it is largest **exactly in our target regime**. On
identical TA and DIC the exe's embedded CO2SYS reads **0.011–0.024 pH *below* PyCO2SYS** between
the ambient (~8.4) and case03/case04's port (pH 10.0–10.44), with Ω 0.8–3.4 % above (ledger rows
35, 41, 43); above 10.44 the two have never been compared, which is what `PHRangeWarning` marks.
The port runs PyCO2SYS and records the divergence rather than tuning it away.

⚠️ **Until 2026-08-25 this paragraph said "+0.068 pH high near pH 10", and both halves were
wrong.** The 0.068 was the first comparison of 2026-08-12 (case03 README), made on two rows at
pH 9.6–10.1 with **Uppström** borate; the exe's KSO4 = 1 selects **Lee (2010)** borate, and matching
it tightened the gap seven-fold (row 128). And the exe reads *low*, not high — the sign had been
inverted in transcription. The 2026-08-12 figures are kept in the case03 README as history.

---

## 4b. One check the exe does not have

`Case.densimetric_froude_number()` implements the manual's §5.2.2 design guidance — `U / √(|g'| d)`,
the port's momentum over its buoyancy. Below 1 the discharge is not jetting and the near-field
model is outside the regime it was built for, and the port emits a `DesignWarning` saying so.

Two things to know. It **warns and never refuses**, because the exe runs these cases and a port
that rejected them could not reproduce a trace. And it uses the **magnitude** of `g'`: the manual
writes `s − 1`, which is negative for a sinking discharge, and half this archive is negatively
buoyant.

⚠️ **Nothing in `reference_cases/` exercises it** — the lowest is 2.01 — so it is tested against
constructed cases. Treat it as guidance you now get automatically, not as something validated
against the exe, which prints no Froude number at all.

## 5. What we deliberately do not reproduce

Reproducing a bug behind a flag is one thing; adopting it is another. These we simply do not do:

- **The unguarded `(Ω−1)^N`.** We return zero for an undersaturated mineral. Available as a flag,
  never a default: one NaN row poisons a whole trace.
- **The post-merge ramp.** The exe eases into the merged profile over 1–40 steps at a rate that is
  not constant per step, per diameter, or per unit dilution. We switch cleanly. This is a
  documented, deliberate difference of at most a few percent over a short window.
- **The step controller.** The exe varies its time step to hold mass growth near 2 % per step; we
  integrate adaptively and sample evenly in time. This is why comparisons are made at the exe's
  printed **times** rather than step-for-step — matching step numbers would compare different
  instants.

---

## 6. Traceability — the thing that will bite you

**Two input dialogs are not saved in the `.prj` file: chemistry and dissolved oxygen.** A `.dat`
trace from the executable is therefore *uninterpretable* without someone having written those
inputs down by hand at the time.

⚠️ **And the DO tab retains its previous values between runs.** During this project that changed
the meaning of a run **three separate times**. Once it cost two full rounds of analysis: case25 and
case26 were both worked up against a cBOD5 of 2000 that had never been typed — it was 20 — which
manufactured a rate-dependent "amplitude" that did not exist, and two published findings had to be
retracted.

The rules that came out of that, and they are cheap:

1. **Read the six DO fields off the tab at run time and record them with the trace.** Effluent DO,
   IDOD, cBOD5, nBOD5, and both decay rates. A far-field trace without them is not evidence.
2. **Save the `.prj` at run time**, not from memory afterwards.
3. **Design experiments as differences where you can.** The measurement that settled eq 30's
   ambient oxygen was a difference between two runs, in which the demand cancels exactly — so it
   survived the retained-tab error intact and gave the same answer across an 87× change in decay
   rate. An absolute measurement would have been wrecked for the third time.

Our own runs carry a provenance sidecar recording version, commit, and a SHA-256 of the fully
resolved case, so a result written by this port can always be traced back to the inputs that
produced it.

---

## 7. If you are changing something

- `plumes2 validate` runs the whole executable ledger. Run it before and after; a speedup or a
  refactor that changes a number is a bug, and that check is the point of it.
- The tolerances live in `plumes2/validation.py` and are set by **what the reference can resolve** —
  three printed decimals, or a stated acceptance bar — never by what the code happens to produce.
  Widening one to turn a red row green is how a validation suite stops meaning anything.
- Findings live in the docstring beside the code that encodes them. If you change what the code
  does, the paragraph explaining why is the part that has to change with it.
- [`LEDGER.md`](notes/LEDGER.md) is the full ledger, **270 rows**, grouped by phase and then by
  resolution — measured, open, or retired with a named reason. This document is the part you
  need to use the model;
  that one is the part you need to trust it.
