# references/

Third-party source documents that the manuals cite but do not reproduce. **Not our work, and
not upstream's** — these are external publications, kept here because the PLUMES2.0 manuals
defer to them for the physics they leave unspecified.

| file | citation | why it is here |
|---|---|---|
| `Baumgartner_Frick_Roberts_1994_..._COMPLETE.pdf` | Baumgartner, D.J., Frick, W.E., Roberts, P.J.W. (1994). *Dilution Models for Effluent Discharges*, 3rd edition. EPA/600/R-94/086, June 1994. 199 pp. | **Closes the `A_p` gap.** Contains the full UM model theory (pp. 111–142) including the Projected Area Entrainment hypothesis the PLUMES2.0 manual defers to Frick (1984) for. |
| `Frick_et_al_2003_..._Visual_Plumes_EPA-600-R-03-025.pdf` | Frick, W.E., Roberts, P.J.W., Davis, L.R., Keyes, J., Baumgartner, D.J., George, K.P. (2003). *Dilution Models for Effluent Discharges*, 4th edition (Visual Plumes). EPA/600/R-03/025, March 2003. | The **4th edition**, and the one that documents **UM3** — the model our exe actually runs — rather than UM. §7.2.2 gives the three-dimensional generalisation of PAE, and §7.2.1 confirms UM3 descends directly from the UM of the 3rd edition. |
| `Muellenhoff_et_al_1985_..._Vol1_EPA-600-3-85-073a.pdf` | Muellenhoff, W.P., Soldate, A.M., Baumgartner, D.J., Schuldt, M.D., Davis, L.R., Frick, W.E. (1985). *Initial Mixing Characteristics of Municipal Ocean Discharges, Volume 1: Procedures and Applications*. EPA/600/3-85/073a. 101 pp. | The original documentation of this model family, added while hunting the equation of state. ✅ **Read 2026-08-20 — and it earned its keep, though not for the reason it was archived.** See below. |
| `Millero_2010_History_of_the_Equation_of_State_of_Seawater_Oceanography_23-3.pdf` ⚠️ **not public domain — see below** | Millero, F.J. (2010). *History of the Equation of State of Seawater*. Oceanography 23(3):18–33. 16 pp. | Added 2026-08-20, and the only non-EPA item here. It supplies the **lineage and the sign** for the EOS identification below: that the Knudsen (1901) / Ekman (1908) one-atmosphere equations "were used for about 70 years, from approximately 1908 to 1980", reformulated by Fofonoff et al. (1958) and Sweers (1971) — the era H.O. 615 and Teeter & Baumgartner (1979) sit in — and, quantitatively, that Knudsen's densities run **high**: "Cox et al. (1970) measurements of S_P = 35 seawater found that the Knudsen (1901) results were too high by 0.013 kg m⁻³", with Millero & Lepple (1973) "0.007 ± 0.004 kg m⁻³ lower than Knudsen (1901)". |
| `Cenedese_Linden_2014_Entrainment_in_two_coalescing_axisymmetric_turbulent_plumes_JFM_accepted_manuscript.pdf` ⚠️ **not public domain — see below** | Cenedese, C. and Linden, P.F. (2014). *Entrainment in two coalescing axisymmetric turbulent plumes*. J. Fluid Mech. 11 pp. (accepted manuscript). | Added 2026-08-21, and the **only source that solves the merging problem from first principles**. Gives a closed form for the effective entrainment constant `α_eff` — our suppression ratio under another name — with a merged asymptote of `2^(-1/2)` = **0.707**, parameterised by `z* = α z / x₀` rather than by `d/L`. That is independent theoretical support for ledger row 266. See below. |
| `Kirkes_Xiong_2017_Brucite_Solubilities_NaCl_Elevated_Temperatures_SAND2017-3039C.pdf` | Kirkes, L.D. and Xiong, Y. (2017). *Experimental Determination of Brucite Solubilities in NaCl Solutions at Elevated Temperatures*. Sandia National Laboratories, SAND2017-3039C, ABC Salt(V) Conference. 17 pp. OSTI 1431597. | Added 2026-08-24 while chasing brucite `Ksp` (§8.1). A conference deck, not a paper — archived because it is the public part of the citation trail: it states outright that brucite thermodynamic data **at elevated temperatures was still lacking as of 2017**, which is why the temperature term in `Ω_brucite` stays a recorded uncertainty. US DOE work (Sandia, contract AC04-94AL85000), public via OSTI. |

The three EPA reports are US EPA Office of Research and Development reports, so US Government works
and in the public domain; the Sandia deck is US DOE work, public via OSTI. Retrieved from EPA NEPIS (`nepis.epa.gov`, dockets `3000354K` and
`20012V0C`) and from EPA's January-2021 site snapshot
(`19january2021snapshot.epa.gov/.../VP-Manual.pdf`).

⚠️⚠️ **Millero (2010) is the exception, and anyone publishing this repository needs to know.**
It is freely downloadable from <https://www.teos-10.org/pubs/Millero_History_EOS.pdf>, and its own
first page grants the use it is here for — "Permission is granted to copy this article for use in
teaching and research" — but it continues: "Republication, systematic reproduction, or collective
redistribution of any portion of this article by photocopy machine, **reposting**, or other means
is permitted only with the approval of The Oceanography Society." © 2010 The Oceanography Society.
So it is fine in a research repository and is **not** cleared for a public one; if this repo is
ever published, either get TOS approval or drop the file and keep the citation. Nothing in
`src/` depends on it — `seawater.knudsen_sigma_t` carries the two quoted figures inline.

⚠️⚠️ **Cenedese & Linden (2014) is the second exception, and a stricter one.** It is the author's accepted manuscript, deposited in Cambridge's institutional repository under a green open-access policy: free to download and read for research, **not** cleared for redistribution. © Cambridge University Press. Same rule as Millero — fine here, drop it and keep the citation if this repo is ever published. Nothing in `src/` depends on it; its numbers appear only as targets to test against, and the DOI is enough to recover them.

⚠️ A partial copy circulates as `DOS-PLUMES-guide-pages1-94.pdf` (clu-in.org). **It stops at
page 94 and therefore omits the entire theory section.** Use the complete file archived here.

## ✅ Muellenhoff (1985) has been read, and the equation of state turns out to be a *table*

Added 2026-08-18 on spec while looking for the **equation of state**; read 2026-08-20. Ledger row
159 rests on one sentence in the 3rd edition (p. 124): UM's density comes from the `Sigmat`
function of *Teeter, A.M. and Baumgartner, D.J. (1979), Predictions of initial dilution for
municipal ocean discharges, CERL Publ. 043* — and **neither manual prints the polynomial**.

That 1979 paper still cannot be found. It is a *lab-internal* Corvallis series rather than an
EPA-600 report, so it is absent from NEPIS and from EPA's Science Inventory, and appears online
only as a citation in other people's bibliographies. ⚠️ The manuals also cite it under the wrong
title — "Prediction of initial **mixing**" where the catalogued title is "Predictions of initial
**dilution**" — which is part of why it is hard to trace. The 4th edition's bibliography repeats the
wrong title, so both manuals are wrong the same way.

### How to read it, because the obvious route fails

The NEPIS copy is a scanned image with **no text layer at all** — 0 characters across all 101
pages, confirmed rather than assumed. `pdftotext` returns an empty file and nothing greps. The
Read tool's PDF path also fails here: it shells out to `pdftoppm`, and this environment's poppler
install ships `pdftotext.exe` only.

⭐ **The way through is that each page is a single full-page TIFF**, so no rasteriser is needed —
`pypdf` hands the image over directly:

```python
from pypdf import PdfReader
r = PdfReader('Muellenhoff_et_al_1985_..._Vol1_EPA-600-3-85-073a.pdf')
list(r.pages[47].images)[0].image.convert('L').save('p048.png')   # = report page 37
```

**PDF page = report page + 11** (the front matter is roman i–ix). Pages are 2500 × 3510 and
legible.

### ⭐⭐ What it settles: the density source is one generation further back, and it has no polynomial

Report p. 37, under **UOUTPLM → Theoretical Development** — OUTPLM being the cooling-tower model
that *Teeter and Baumgartner (1979)* adapted for marine discharges:

> An equation relating temperature, salinity, and density (**U.S. Navy Hydrographic Office 1952**)
> is used to calculate the density of the ambient and the plume element at each time step.

and in the reference list, report p. 84:

> **U.S. Navy Hydrographic Office. 1952. Tables for seawater density. H.O. Pub. No. 615.
> Washington, DC. 265 pp.**

⚠️ **It is not a polynomial and it never was one.** H.O. 615 is 265 pages of *tables*, computed at
one atmosphere — the Knudsen/Ekman sigma-t tradition, a quarter-century before EOS-80. That is the
likeliest reason no manual in this family prints coefficients: **the source has none.** Whatever
Teeter and Baumgartner (1979) contributed was a fit to, or an interpolation of, that table — which
is also what the 3rd edition is distinguishing when it speaks of "the *nonlinear* equation of state"
and a run-time "linear/nonlinear window" (p. 116).

⚠️ **This is a chain of attribution, not a printed statement about UM.** Muellenhoff attributes
H.O. 615 to **OUTPLM**; the 3rd edition attributes **UM**'s `Sigmat` to Teeter and Baumgartner
(1979); UM3 descends from UM. So the chain is

    USNHO (1952)  →  OUTPLM  →  Teeter & Baumgartner (1979)  →  UM  →  UM3  →  PLUMES2.0

and only two of those links are printed anywhere we hold. **Row 159 does not depend on it** and
still does not — the claim's substance is tested directly against the archive, where rows sharing
an exact printed `(S, T)` across 0.89 m of depth print the same `P-Den`, where an EOS-80 pressure
term would move it four times the printed resolution.

✅ **What this does do is explain both halves of what row 159 measured.** One atmosphere is why the
density is pressure-independent, which the 3rd edition states as a *limitation* ("limiting UM to
shallow water") without ever saying where it comes from. And a pre-1980 table read against EOS-80 is
exactly the shape of a small offset in a known direction.

⭐ **A checkable lead, in the 3rd edition and not previously noted here.** p. 116 says the computed
effluent density's "computed values vary slightly from published values (see Table III in the next
chapter)", and **Table III** (p. 94, *PLUMES and CORMIX1 densities compared with published values*,
Weast 1977) prints the comparison outright — 1024.66 against a published 1024.5 at S = 34.84,
T = 20 °C, i.e. UM reads **high**, the same direction the identification below confirms. ⚠️ Read it
from the page image before using it: the columns interleave under text extraction and the (T, S)
pairings come out scrambled.

## ⭐⭐⭐ The equation of state is **Knudsen (1901)**, and it is now measured rather than inferred

The section above traces the exe's density *to* H.O. 615 by citation and stops there, because the
polynomial is not printed anywhere in the chain. It did not need to be. **The exe prints `P-Sal`,
`P-Temp` and `P-Den` on the same row in 116 archived traces**, so its equation of state is directly
invertible — no reconstruction from dilution, which is how the old figure was obtained. Scored on
all **51 670** such rows, S 0–45 psu and T 2.73–11.01 °C, with **no fitted parameter**:

| candidate | free parameters | mean residual | rms | worst |
|---|---|---|---|---|
| **Knudsen (1901) σ_t** | **0** | **−0.00001** | **0.00037** | **0.00098** |
| EOS-80 / UNESCO (1983) at p = 0 | 0 | +0.02882 | 0.02942 | 0.06292 |
| Eckart (1958), Tumlirz form | 0 | +0.12205 | 0.12331 | 0.20979 |
| EOS-80 + cubic in S, quadratic in T | 7 | 0 | 0.00055 | 0.01679 |

`P-Den` carries three decimals, so a worst case of **0.00098 kg/m³ is one rounding digit**: Knudsen
reproduces the column to everything the trace can show. ⭐ And fitting a constant, a line in S, or
a quadratic *on top of* Knudsen leaves the rms at 0.00037 unchanged — there is nothing left to
absorb, which is what separates an identification from a fit. A seven-parameter fit to EOS-80 does
not reach it.

So the chain closes from the far end. H.O. 615 tabulates the Knudsen/Ekman results; the exe
computes Knudsen; the two links nobody printed are bridged by the archive itself. Implemented as
`seawater.knudsen_sigma_t`, selectable through `seawater.EquationOfState`, with EOS-80 left as the
default per PLAN §2's "correct by default, reproduce on request".

⚠️ **This retracts a sentence that stood in *this file* earlier today** — that a pre-1980 table
against EOS-80 gives "a small, nearly constant offset, which is what the +0.0275 kg/m³ is". It is
not nearly constant. Pooled across the archive the EOS-80 residual runs +0.061 at S = 10, +0.028 at
S = 31 and +0.021 at S = 36, and a plane fit gives `+0.0751 − 0.001512·S + 0.000048·T` — a line in
salinity with essentially no temperature dependence across the archive's 2.7–11 °C.

⭐ **The ledger got there first, and deserves the credit**: row 255 recorded on 2026-08-19 that
"the sigma-t offset is salinity-dependent, not a constant bias", with a +0.9985 correlation over 31
traces and case29's fresh discharge running −0.063 at S = 0 to −0.029 at S = 31. What the
identification adds is the *reason* — two specific polynomials, agreeing near seawater and
separating away from it, exactly as row 255 predicted in those words. The retracted "constant" was
row 108's, which is scoped in its own text to "the seawater range" and is therefore still true as
written.

⚠️ **Where the formula came from, stated plainly, because it matters here.** The coefficients were
**not** transcribed from any document in this folder — none of the six prints them. They are the
classical form as it appears in Sverdrup, Johnson & Fleming (1942) and Fofonoff (1962), written
from knowledge and then checked three ways: `σ₀(35) = 28.1296` against the tabulated 28.13,
`σ_t ≡ σ₀` at T = 0 (which the algebra requires, since `A_t` and `B_t` both vanish), and the 51 670
rows above. **The third check is the load-bearing one** — a wrong coefficient could survive the
first two and could not survive the third at 0.00037 kg/m³. Millero (2010) supplies the
corroboration that the sign and rough size are right (Knudsen high by 0.007–0.013 kg/m³ at S = 35,
against our +0.022 there). ⚠️ Anyone wanting a primary citation for the coefficients themselves
should check Knudsen, M. (1901), *Hydrographische Tabellen* — which is **not** in this folder.

⭐ It also confirms what the 3rd edition asserts without support: Knudsen σ_t has **no pressure
term at all**, so "independent of pressure, limiting UM to shallow water" is a property of the
formula rather than a simplification anyone chose, and this port's habit of evaluating density at
p = 0 was right by construction.

### ⭐⭐⭐ And it settles something nobody was looking for: the two entrainment mechanisms are a *maximum*, not a sum

Report p. 38, continuing the same section:

> The second mechanism is aspiration entrainment (i.e., the Taylor entrainment hypothesis
> discussed in Taylor et al. 1956) which captures 0.1 times the product of the external area of
> the plume element and its shear velocity. **Total entrainment is taken to be the larger of these
> two mechanisms.**

That is the missing *account* of the branch `nearfield/entrainment.py` transcribed from traces
without one. UM3's aspiration velocity tests `u2 > ven` before opening its `angl` and blending the
forced and Taylor contributions — which is a comparison of the two mechanisms' magnitudes, i.e. a
smoothed version of "take the larger". The port measures that blend to the noise floor; what it
could not say was *why* a comparison appears at all in a closure documented as a sum. It is
inherited, and it is older than UM.

⚠️ Provenance, not licence to change the code. The arctan blend is what the traces agree with; a
hard maximum is what the 1985 ancestor describes. They are not the same function, and nothing here
has measured which one PLUMES2.0 evaluates.

### ⭐ Three trace-derived relations are stated outright, in 1985, in one paragraph

Same page, and each of these cost the port a measurement:

| our measurement | report p. 38 |
|---|---|
| `h ∝ \|U_j\|` (element stretching) | "The segment length is changed in proportion to the total velocity to conserve mass and pollutant." |
| `b` is algebraic, not integrated | "The radius is changed to correspond to the new mass and density." |
| drag = 0 | "Since the element is considered to be one of a train, each following the preceding element, drag is assumed to be negligible." — the *reason*, which the 3rd edition asserts without |
| Taylor `α = 0.1` | "captures **0.1 times** the product of the external area … and its shear velocity" — a model constant, not a user field |
| `A_p` = growth + cylinder + curvature | "the projected area formulation contains a cylindrical term, a growth term, and a curvature term as described in Frick (1984)" — a third independent statement of the decomposition, and the earliest |

`Dilutn` as a volume ratio is there too: "Dilution is calculated by comparing the initial volume to
that of the element."

### ⚠️ What it does not contain

The `Sigmat` coefficients, PLUMES2.0's own additions, and the step-controller target. Note the
abstract (p. iv): **"Complete program listings in FORTRAN IV-PLUS are provided in Volume II."** So
the code — the one place a `SigmaT` function would be readable outright — is in a volume we do not
hold, distributed in 1985 on 9-track tape or diskette through NTIS. That is where to look if the
polynomial is ever actually needed. The port does not need it.

## What the 3rd edition settles

The PLUMES2.0 manual gives the LCV conservation laws but describes `A_p` only qualitatively
before deferring to Frick (1984) and Frick et al. (1995). This report gives the equations
outright, in a section titled *Experimental Justification of the Projected Area Entrainment
Hypothesis*. Equation numbers below are this report's.

**Confirms, independently, four things we had measured from traces:**

| our measurement | this report |
|---|---|
| `h ∝ \|U_j\|` (element stretching) | eq 32: `h/h₀ = u_s/u_s0` |
| `A_T = 2πbh` | eq 35, identical |
| Taylor `α = 0.1` | eq 34 plus a derivation: 0.082 Gaussian → 0.116 top-hat, 0.081 for jets, "an average value for α of 0.1 is thought to be slightly conservative" |
| `b` is algebraic, not integrated | eq 50: "the radius, b, is not an independent variable, rather it is a dependent variable" |

**Gives the projected area as three terms**, in a local frame with `ê₁` along the trajectory,
`ê₂` the horizontal normal, `ê₃` in the vertical plane, and `U = u₁ê₁ + u₂ê₂ + u₃ê₃` (eq 36).
Each *component* of the current acts on its **own** area:

- **growth**, paired with `u₁`: `A₁ = π b Δb` with `Δb = (∂b/∂s) h` (eqs 38–39). Half the
  circumference only — "the assumption is made that only the upstream portion of the area,
  half the circumference, has flow going through it".
- **cylinder**, paired with `u₂`: `A_cyl = 2 b h` (eq 40).
- **curvature**, paired with `u₂`: `A_cur = −(π/2) b² (∂θ/∂s) h` (eq 41), `θ` the elevation
  angle of the trajectory. **Signed** — "positive curvature has the effect of reducing the
  total projected area".
- `u₃` is dropped: "since only the two-dimensional problem is considered the u₃ component is
  ignored".

And it states the failure mode we hit, in as many words:

> Historically the growth and curvature terms have either not been recognized or have been
> thought to be small compared to the cylinder term (Schatzmann, 1979). However, in general,
> it can be shown that all three contributions to the total projected area are important. Any
> earlier perceived inadequacies in the projected area entrainment hypothesis can be
> attributed to the omission of the growth and curvature terms.

That is exactly our symptom: a cylinder-only closure whose fitted coefficient drifts with
ambient current and whose residual arcs along the trajectory. The element "is not a cylinder
but is in general a section of a bent cone. The consequences of this fact cannot be
overstated."

**The step controller** (p. 125) is also described: the time step is varied "to control the
relative amount of mass that is entrained during any one single step" — guess a step, compute
the entrained mass, compare "with the target mass increase", adjust, solve, repeat, "to meet
the appropriate doubling criterion". Our measured 2 % per step is that target.

**Merging** is per-term, not one scalar: "each of the four entrainment terms is decremented to
a different degree as merging proceeds". Oblique diffusers are handled by "mathematically
reducing the spacing distance between adjacent ports by the appropriate trigonometric factor",
valid for "currents between 90 and 45 degrees" — which is the effective-spacing cosine we
measured.

## ⚠️⚠️ "Overlap" in these manuals is **not** plume-to-plume merging

An earlier version of this README closed the merging paragraph above with eq 50 "gives anomalous
results" once plumes overlap, "the source of the overestimation of radius and entrainment" — which
reads as a warning about *merged* plumes, and PLAN's Phase 5 carried it the same way until
2026-08-20 (now in `PLAN_HISTORY.md`). **The quote
is accurate and the placement is wrong.** The 3rd edition defines the condition, p. 113:

> In special cases of plume trajectory of smaller radius-of-curvature than the plume radius
> itself, **the element faces would intersect, or overlap**, a physically impossible situation.

So "overlap" is a **single-element, single-plume** phenomenon: a strongly bent trajectory folding
one element's own end faces through each other. It has nothing to do with neighbouring ports. That
is why the eq-50 citation is a paper called *Improved prediction of bending plumes*, why DOS PLUMES
prints "plume element overlap" on single-port runs, and why the far field can be started at
"element overlap" as an alternative to maximum rise — overlap arrives near the trapping level,
where the trajectory flattens.

The same page gives UM's response, which is a **termination rule the port does not have**:

> UM does issue a warning when overlap begins and, in its the default mode, terminates the initial
> dilution computation. In other models of the same class, both Lagrangian and Eulerian integral
> flux, the condition is not identified, or even recognized, and results in the over-prediction of
> plume radius and entrainment unless the increase has been effectively tuned out, a practice that
> would introduce spurious behavior elsewhere.

⚠️ **This mattered for what was then PLAN's largest open problem** (the runaway itself was closed by
`ConfinedDecrements.ALL` on 2026-08-21; the point about attribution stands). The merged-radius runaway (rows 157b, 186) has
been partly framed as something the reference already warned about. It did not: the reference's
eq-50 warning is about *bending*, and the runaway is about *confinement*. They are two separate
defects that both fall out of inverting eq 50, and only one of them is documented upstream.

## ⭐ Two leads for the merged-radius runaway, both new

Neither is a mechanism, but both are cheaper to chase than another exe run.

1. **The correction has a name and a citation.** The 4th edition describes a file shipped on the
   Visual Plumes CD, `DOS-PLUMES/Original Files/FBF93G8.eps`, as "Figure 8 from Frick,
   Baumgartner, and Fox, 1994, showing the difference between UM model predictions **with and
   without correction for the negative volume anomaly**". So the search term is *negative volume
   anomaly*, not "overlap", and the paper is the eq-50 citation in full (3rd ed. bibliography):

   > Frick, W.E., D.J. Baumgartner, and C.G. Fox, 1994. Improved prediction of bending plumes.
   > Accepted for publication in **Journal of Hydraulic Research**, IAHR, Delft.

   ⚠️ We do not hold it, and it is a journal paper rather than an EPA report, so it will not be on
   NEPIS.

2. **UM3 fixed it, and the 4th edition says where the fix shows up.** Walking a user through a run
   (Appendix A): "not much entrainment occurs beyond the trapping level where the plume element
   enters the spreading layer. This is quite different from the DOS Plumes UM prediction because
   **UM3 addresses the 'overlap' problem** described in the DOS Plumes manual." An entrainment
   brake that engages at the trapping level, described from the outside. ⚠️ Bending again rather
   than merging — but it is the closest thing on record to the brake rows 260/260b bound without
   locating.

## The 4th edition (Visual Plumes) — what it adds

Our exe runs **UM3**, not UM. The 3rd edition documents UM; this one documents UM3, and the
difference is not cosmetic.

**§7.2.2, the three-dimensional generalisation**, resolves the frame ambiguity the 3rd
edition leaves. It adds a term

> which represents the entrainment entering the plume element from the side represented by a
> vector pointing at right angles to the plane formed by the instantaneous direction of motion
> of the plume element and the gravitational acceleration vector.

So the working plane is the **vertical plane containing the trajectory**, and the added `u₃`
term is the current normal to *that*. This settles the reading the 3rd edition muddles — see
`nearfield/entrainment.py`, which argued for spanning the plane with the current instead and is
wrong on this point.

**§7.2.2 also confirms the 20° cap** on the merging spacing correction, which PORTING_NOTES
had guessed and then retracted after reading the 3rd edition's 45°–135° statement. Both are
right, for their own model: 45°–135° is UM's, and UM3 adds

> The problem of parallel currents is solved by assuming that for angles of less that 20 degrees,
> measured between the plane of the individual plume element motion and to a horizontal line at
> right angles to the local current, there is no further reduction in the effective spacing between
> adjacent plumes, which would otherwise reduce to zero when currents are parallel to the
> orientation of diffuser pipe.

§1.3 states the same cap from the summary side — "Dilution from diffusers oriented parallel to the
current is estimated by limiting the effective spacing to correspond to a cross-diffuser flow angle
of 20 degrees" — and adds that merged plumes are handled by **distributing the cross-current
entrainment over all plumes**, a coarser treatment than the per-term decrements of the 3rd edition,
and described as such: "Merged plumes are simulated less rigorously."

### ⭐⭐ §1.3 also names the second step-control criterion

PLAN has carried "the second step-control criterion" as unspecified since the trace measurement
found the 2 % mass cap slackening to 1.0002 late in a run, with `dt`, `Δs/b` and `Δz/b` all ruled
out. The 4th edition says what it is, in the UM3 summary:

> The runtime and display performance of UM3 has been improved by better controlling the simulation
> time step. **In addition to being controlled by the amount of entrainment, the time step is now
> also sensitive to the amount of trajectory curvature.** In some cases, this sensitivity to
> curvature actually reduces the number of time steps needed to produce a simulation because the
> sensitivity to entrainment can be reduced.

⚠️ **A name, not a formula.** No tolerance, no functional form, and no statement of how the two
criteria combine. But it is a UM3 addition absent from UM, which is consistent with the criterion
biting where the trajectory turns, and it says which quantity to regress the step size against
instead of the three that failed.

### ⚠️ Correction: chapter 7 has no §7.4 or §7.5

An earlier version of this README warned that "§7.4 and §7.5 are empty placeholders". **They do not
exist.** This report numbers its pages *chapter.page*, so the `7.4` and `7.5` that produced that
reading are page numbers — §7.2 UM3 theory begins on page 7.4 and §7.2.2 on page 7.5. Chapter 7 is
§7.1 (Visual Plumes, with .1–.3) and §7.2 (UM3 theory, with .1–.2), and nothing else.

The substance of the warning survives, so it is worth restating correctly. **The theory chapter is
thin**: the placeholder sentence "The text in this section is presently limited. It is planned for
expansion." stands where the body of **§7.1** should be, and again under **§8**. And the entrainment
equations themselves are *not* restated anywhere in chapter 7. For those, see the note on the Visual
Plumes source code in PLAN.md Phase 5 — the algorithm is public, but under a licence that makes
copying it a decision rather than a detail.

---

⚠️ **Nothing in `LEDGER.md` has been changed by this pass.** Everything above is a reading of the
archived sources, not a measurement; the rows it bears on are 159 (the equation of state), 157b and
186 (the merged-radius runaway), and PLAN §7.2 (the step controller). Whether any of those moves is
a separate decision. The two corrections in this file — the misplaced overlap quote and the
non-existent §7.4 — are corrections to *this README*, which is the only place they appeared in that
form; PLAN's Phase 5 carried the overlap quote in the same misleading position until it was
corrected on 2026-08-20 (`PLAN_HISTORY.md`).

---

## ⭐⭐⭐ 2026-08-21: UM3's merged entrainment mechanism, stated outright — and it is `ALL`

The merging brake (`ConfinedDecrements`, ledger rows 264–269) was built by measurement, with no
statement of UM3's mechanism to check it against. There is one, in Frick's own Visual Plumes
teaching material: Walter E. Frick, *Introduction to Visual Plumes* (training slide deck, Visual
Plumes Consultants / US EPA mixing-zone course material). Verified by web search 2026-09-01 —
the passage below is verbatim on the slides, mirrored at
<https://slidetodoc.com/introduction-to-visual-plumes-walter-e-frick-visual/> and
<https://www.slideserve.com/olisa/introduction-to-visual-plumes>; the same material circulates in
the EPA Region 10 mixing-zone course packet
(<https://clu-in.org/conf/tio/r10mixingzone_012313/2005-MZcourse-draft.pdf>, unverified — the file
is too large to fetch here). The deck itself is not archived in this repo:

> Aspiration entrainment tends to be the dominant entrainment mechanism in low currents, including
> stagnant ambient; in UM3 it is **proportional to the area the plume shares with the ambient
> fluid**. Where plumes are merged and are demarcated by vertical reflection planes, it is assumed
> that the plume and its neighbor gain and lose equivalent amounts of mass so that **no net
> entrainment occurs across those vertical surfaces, only over the surfaces still exposed to
> ambient fluid**.

⭐⭐ **That sentence picks one of our variants, and it is not the default.** Take the confined
cross-section eq 55 actually describes — a circle of radius `b` truncated at `|x| = s` — and ask
what its exposed perimeter is. The two reflection planes contribute nothing. The two exposed arcs
each span `π − 2φ` with `φ = arccos(s/b)`, so

    exposed perimeter = 2 b (π − 2φ),      unconfined = 2π b
    exposed fraction  = (π − 2φ)/π        ← which is eq 51's `a_T`, evaluated at the **confined** b

So "only over the surfaces still exposed to ambient fluid" **is** `a_T(b) · 2πbh` — exactly
`ConfinedDecrements.ALL`'s Taylor term. The same argument carries the growth term: confined, the
element grows only into its exposed arcs, so the growth annulus is `exposed perimeter × Δb / 2 =
a_T(b) · πbΔb`, which is again `ALL`.

⚠️ **This is the account the shipped default lacks.** `NONE` evaluates `a_T` at the *round*
`b_r` while building the area from the confined `b`, which corresponds to no statement in any
reference — it is how the port was first written, not a reading of anything. The brake's
out-of-sample 0.98 % (row 267) now has a mechanism behind it rather than only a measurement.

⚠️ **What it does not settle** is row 264c: `ALL` still costs test32 1.01 % → 5.24 %. Note that
test32's 1.01 % is *below* its own unmerged control's 1.39 % (row 177), which is the signature of
cancelling errors rather than of correctness — worth testing before treating it as the bar.

## ⭐⭐ Cenedese & Linden (2014) — coalescing plumes solved from first principles, with a number

`Cenedese_Linden_2014_Entrainment_in_two_coalescing_axisymmetric_turbulent_plumes_JFM_accepted_manuscript.pdf`
— the accepted manuscript, from Cambridge's institutional repository.

⚠️ **Licence note.** Unlike the EPA reports here, this is a copyrighted journal article deposited
under a green open-access policy. It is here for internal research use; it is not public-domain
material and should not be redistributed with the port.

**Why it matters: it is the same problem, solved independently of UM3, and it produces a closed
form.** Two coalescing axisymmetric plumes, three regions:

| region | state | entrainment |
|---|---|---|
| 1 | separate | unaffected — `α_eff = α` |
| 2 | touching, not merged | set by the dynamics **and the reduced surface area through which entrainment occurs** |
| 3 | merged | "equivalent to that in a single plume" |

⭐ **Region 2's mechanism is the same reduced-exposed-area statement Frick makes**, arrived at
independently. Two sources, one mechanism, and it is `ALL`.

⭐⭐⭐ **And Region 3 gives a number the port can be held to.** They define an *effective*
entrainment constant `α_eff` — the `α` that would give two independent plumes the same total volume
flux as two coalescing ones, which is precisely our suppression ratio. Their eq 2.12:

    α_eff/α = 1                                    z* < 0.35        (separate)
            = z*^(-5/4) (0.73 z* − 0.082)^(3/4)    0.35 ≤ z* ≤ 0.44 (touching)
            = 2^(-1/2) (1 + 0.12/z*)^(5/4)         z* > 0.44        (merged)

with **`z* = α z / x₀`** — distance from the source over the source separation. So:

- ⭐ **the merged asymptote is `2^(-1/2)` = 0.707**, approached *from above*;
- ⭐⭐ **the variable is `z*`, distance from source over spacing — not `d/L`.** That is
  independent theoretical support for ledger row 266, which measured the exe's suppression tracking
  trajectory stage rather than spacing. Two different arguments, same variable.

Evaluated over our range, taking `b ≈ 1.2 α z` so `z* = (d/L)/2.4`:

| `d/L` | 2 | 3 | 6 | ∞ |
|---|---|---|---|---|
| `α_eff/α` | 0.837 | 0.795 | 0.750 | **0.707** |

**Measured**, per spacing at matched overlap (row 260d): **0.766 / 0.568 / 0.580**, and case42's
0.659. Our braked closure gives ~0.65 flat.

⚠️⚠️ **So the exe suppresses *more* than pair theory says, and that is expected: the archive is
all 25-port rows.** A row of plumes tends to a *line* plume, not to a single axisymmetric one, and
its merged asymptote is a different problem — the relevant paper is Cambridge JFM's *Merging of a
row of plumes or jets with an application to plume rise in a channel*, which we do not hold and
which is paywalled. Its abstract states the shape we need: generalised plume equations carrying the
plume area and net entrainment, closed with an entrainment assumption, approaching "the appropriate
limiting similarity solutions above and below the merging height".

⭐ **Which is what the pair suite settled.** Nothing in the archive was a *pair* until the
`suite_n02_base` experiment — generated in `pending/`, run, and graduated as
[`reference_cases/case43_port_count/`](../reference_cases/case43_port_count/README.md): fixed
per-port flow against a single-port control. The exe's pair lands within **3.7 %** of the 0.707
coalescing-plume asymptote (ledger row on case43), turning the literature number into a
confirmation.


## ⭐⭐ 2026-08-24: the brucite `log Ksp` literature arrived by another door — ebb-general-modeling PR 158

§8.1's `Ksp` pick was blocked on sources this repo does not hold. **PR 158 in
`ebbcarbon/ebb-general-modeling`** (merged; `alkalinity_mixing_zone/`, `mix_calc.py` and
`ACCURACY.md`) did that literature work for its own PHREEQC calculator, and its findings map onto
this port's constants directly:

- ⭐⭐ **Our uncited −11.16 is now identified.** It is the wateq4f_PWN.dat conversion (H⁺-form
  `log_k` 16.84 + 2 × −13.998), which encodes **Robie & Hemingway (1995)**'s ΔfG. The database
  spread is not a chemistry disagreement — each database encodes a different ΔfG(brucite), at
  5.708 kJ/mol per log unit: HMW84 → −10.79, Brown 96 → −10.87, **Xiong 2008 → −10.94**,
  R&H95 → −11.15 (≈ ours), Koenigsberger 99 → −11.68.
- ⭐⭐ **The measured, citeable value is Xiong (2008)**, *Aquatic Geochemistry* **14**:223–238,
  doi:10.1007/s10498-008-9034-3 — brucite solubility from both under- and supersaturation in
  0.010–4.4 m NaCl, recommending log Ks = 17.05 ± 0.2 (H⁺ form) = **−10.95 ± 0.2** (OH⁻ form).
  Independently corroborated by **Altmaier et al. (2003)**, *Geochim. Cosmochim. Acta*
  **67**(19):3595–3601, at 17.1 ± 0.2 → −10.90. PR 158 validated −10.95 against five OLI
  titration surveys spanning I = 0.016–1.9 mol/kg (3/5 inside the onset band; a −10.50 misread
  of Xiong's *conditional* log Q column fails 0/5 — the cautionary tale rhymes with row 197).
  ⚠️ **Neither paper is open access** (checked via Unpaywall 2026-08-24), so per this folder's
  policy they are cited, not archived. The Kirkes & Xiong (2017) Sandia deck above is the public
  end of the trail.
- ✅ **Row 197's athermal enthalpy is independently confirmed.** PR 158 reached "nearly athermal,
  slightly negative" down four lines — wateq4f/CODATA −0.40 kcal/mol, Gurvich (1994) calorimetry
  ~−0.6 kcal/mol; our −2.29 kJ/mol sits between them — and caught **pitzer.dat shipping +4.85
  kcal/mol with the wrong sign** for a textbook retrograde mineral. The same silent-constant
  failure mode as row 197, in a curated public database.
- ✅ **PyCO2SYS is endorsed from the other side**: PHREEQC's Ω_aragonite runs 1.64× high against
  it (half in carbonate speciation), and PR 158's own conclusion is "take Ω_aragonite from
  PyCO2SYS" — the engine this port has used since Phase 4.
- ⚠️ **A site caveat for the dose study**: PR 158 measured Port Angeles calcium ~26 % below the
  standard-seawater value that salinity-based conservative relations assume, and Ω is linear in
  the cation. Our `calcium_from_salinity` and `magnesium_from_salinity` carry the same
  assumption; a site-water analysis would bound it.

✅ **−10.95 was adopted the same day, by operator decision** (2026-08-24, PLAN_HISTORY 8.1): every
`Ω_brucite` fell 1.62×, row 196 was re-pinned 214 → 131.4, and the superseded −11.16 stays
callable as an explicit argument. The source is cited directly: **Xiong, Y. (2008), "Thermodynamic
Properties of Brucite Determined by Solubility Studies and Their Significance to Nuclear Waste
Isolation", *Aquatic Geochemistry* 14:223–238, doi:10.1007/s10498-008-9034-3** — publicly mirrored
in the DOE WIPP records library
(<https://wipp.energy.gov/library/CRA/CRA-2014/References/Others/Xiong_2008_Aquatic_Geochemistry.pdf>).
The verification read that used to be owed was waived by the operator (2026-09-01); the figures
were originally relayed through PR 158's reading and independently confirmed twice (above).
