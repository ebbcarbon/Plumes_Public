# Digest of the two upstream user manuals

Review of both PDFs in [upstream/Docs/](../upstream/Docs/), written 2026-08-12. Covers the
complete input inventory, the model structure, the GUI, and — importantly — what the
manuals **do not** specify.

| | |
|---|---|
| `PLUMES2.0v1_SSMC_User Manual.pdf` | 64 pp, Dec 2025, PNNL-38865. Khangaonkar & Premathilake. **The superset**: adds carbonate chemistry (§3) and DO/BOD (§4). |
| `EPA_SSMC-PLUMES2.0_User Manual_reformat_v4_B-24.pdf` | 54 pp, EPA edition. Same text minus chemistry and DO. |

Both defer to the same external references for the two pieces they don't derive. The EPA
edition contains nothing the newer one lacks, so the newer one is the working spec.

---

## 1. Model structure

Three phases (§2.1): **jet mixing** → **buoyancy-driven transition** → **far-field passive
transport**. Near field is 10–1000 m over 1–10 minutes; far field 100–10 000 m over 1–20
hours.

### Near field — Lagrangian Control Volume (§2.3.1)

Top-hat properties over each LCV, dropping sharply to ambient outside the boundary.
Governing equations, integrated numerically:

| Eq | Content |
|---|---|
| 2 | continuity: `dm/dt = −ρ_a **A_p**·**U_a** + ρ_a A_T β_T` |
| 3 | momentum: `d(m**U_j**)/dt = **U_a** dm/dt − m (ρ_a − ρ_j)/ρ_j **g**` |
| 4 | heat: `d(m T_j)/dt = T_a dm/dt` |
| 5 | salt: `d(m S_j)/dt = S_a dm/dt` |

* `β_T = α|**U_j**|` — Taylor (shear) entrainment, α the aspiration coefficient.
* `A_T` is the cylindrical wrap area; `A_p` is the **projected area vector** for forced
  entrainment, lying in the vertical plane containing the velocity vector and pointing
  upstream. `A_p` and `U_j` are anti-parallel so their dot product is negative.
* **Drag is taken as zero** (outer surface matches ambient), per Baumgartner et al. (1994).
* Densities from the **sigma-t equation of state, Fofonoff (1985)**.

Concentration profile (eq 6): 3/2-power, `Φ = (1 − (r/b)^1.5)²`. Flux-averaged
concentration is eq 7. Peak/mean ratios: **3.89 round, 2.22 fully merged line plume** — but
the manual explicitly warns these are *limiting* values, that in much of the plume the ratio
is "considerably smaller … approaching 1.0 at the source", and that **"the centerline
concentration prediction is approximate and occasionally deviates from the expected
trend"**. That is consistent with what we measured: the exe simply reports
`CL-Dil = max(1, FluxAvg/2)`.

**Merging** (§2.3.1, Figure 4): overlapping plumes reduce the effective entrainment area,
reducing entrainment and dilution efficiency, via "a geometry-based correction" from
Baumgartner et al. (1994). **The correction itself is not given.**

**Termination — four benchmarks:**
1. plume density equals ambient (trapping / neutral buoyancy);
2. vertical velocity reverses (plume overshot and falls back — "the plume structure
   collapses");
3. boundary contact: water surface, shoreline, or seabed;
4. the max-rise-or-fall switch (§5.2.7, below).

### Far field — Brooks (§2.3.2)

1-D steady form of advection–diffusion (eq 9) with a first-order rate `k`. Three
eddy-diffusivity laws, with **`β = 12 ε₀ / (u · w₀)`** (eq 13, dimensionless):

| case | ε/ε₀ | width (eqs 10–12) | centre concentration (eqs 14–16) |
|---|---|---|---|
| 1 constant | 1 | `w/w₀ = (1 + 2β x/w₀)^½` | `C = C₀ e^{−kt} erf √(3/(4β x/w₀))` |
| 2 linear | `w/w₀` | `w/w₀ = 1 + 2β x/w₀` | `C = C₀ e^{−kt} erf √((3/2)/((1+β x/w₀)² − 1))` |
| 3 **4/3-law** | `(w/w₀)^{4/3}` | `w/w₀ = (1 + (2/3)β x/w₀)^{3/2}` | `C = C₀ e^{−kt} erf √((3/2)/((1+(2/3)β x/w₀)³ − 1))` |

`x = 0` is the **start of the far field**, not the outfall. `ε₀ = α w₀^{4/3}` with
α ∈ [0.0001, 0.0005] m^{2/3}/s, default **0.0003**. Vertical spreading is neglected.
`D_farfield = D · FF`.

**Confirms two of our measurements.** The far-field ambient is taken at *one* depth: "the
model determines those conditions based on the depth of the plume when the initial dilution
ends (surface or plume trapping depth)". And the initial width is "the width of the
wastefield **in the direction of the current** … affected by **current direction** and
diffuser configuration" — which is precisely the cosine projection we decoded from case13.

### Carbonate chemistry (§3.2)

TA and DIC are **scalars advected by entrainment** (eqs 17–18), exactly parallel to heat and
salt; biological effects neglected over minutes. pH from TA + DIC via **CO2SYS routines
compiled into PLUMES2.0**, validated against PyCO2SYS.

* Ω from eqs 19–20; `K_sp` per **Millero (1995)**.
* **`[Ca²⁺] = 0.01028 × S/35`** (Murata et al. 2015) — a *salinity-based relation*. This is
  the manual confirming our case06 finding: the ambient `Ca` column is **not used** for Ω.
* `[CO₃²⁻]` from eq 21 given K1, K2 and [H⁺].
* Precipitation, eq 22: **`log R = N log(Ω − 1) + log K`**, R in μmol/hr, per Zhong & Mucci
  (1989); N and K user-editable, defaults per salinity range. The manual states
  PLUMES2.0 "only calculates the **potential** precipitation rate … and does not dynamically
  simulate the conservation of precipitated mass" — confirming why TA transports
  conservatively despite non-zero rates.
* Ω > 5 is flagged as the runaway-precipitation threshold (Moras et al.) — directly relevant
  to the alkalinity use case.

⚠️ Eq 22 is written with **`log`**, and Zhong & Mucci tabulate base-10. The exe evaluates
`exp()`. See §5 below.

### DO / BOD (§4.2), per US EPA (1994)

BOD's effect during initial dilution is neglected; IDOD is not.

* eq 23 `DO_f = (DO_e − IDOD − DO_a)/D + DO_a`
* eqs 24–25 ultimate BOD: `cBOD_L = cBOD5/(1 − e^{−k_c·5})`, same for n
* eqs 26–27 temperature correction `k(T) = k(20)·θ^{T−20}`; defaults **k_c = 0.23/d,
  k_n = 0.1/d, θ_c = 1.047, θ_n = 1.08**
* eqs 28–29 `L_f = (BOD_Le − BOD_La)/D`
* eq 30 `DO(t) = DO_a + (DO_f − DO_a)/FF − (L_fc/FF)(1 − e^{−k_c t}) − (L_fn/FF)(1 − e^{−k_n t})`

---

## 2. Complete input inventory

### Diffuser tab (§5.2.2)

| # | Input | Units | Notes |
|---|---|---|---|
| 1 | Port diameter | m | circular or equivalent |
| 2 | Port elevation | m | **seabed to port centre** |
| 3 | Vertical angle | ° | to horizontal plane, +ve CCW from x-axis |
| 4 | Horizontal angle | ° | to vertical plane, +ve CCW from x-axis |
| 5 | Number of ports | — | 1 = single port |
| 6 | Port spacing | m | average, for irregular diffusers |
| 7 | Port depth | m | **water surface to port centreline** |
| 8 | X, Y | m | diffuser location = **mid-point of the diffuser section** |

**`port depth + port elevation = water depth at the diffuser`** — stated explicitly, and
what we had already derived from case10's bottom hit. The manual adds that the *ambient*
profile may be taken at a different, **deeper** location, which partly excuses the Macoma
projects' 17 m seabed against a 15 m profile (though theirs is shallower, not deeper).

Stated constraints: port depth **cannot be zero** (no surface discharges); port elevation
**cannot equal** port depth; **all ports must face the same direction**; no limit on port
count. Port elevation *may* be zero but then the plume hits bottom immediately unless the
bottom-hit termination is switched off.

Design guidance worth implementing as a warning: densimetric Froude number
**`Fr = U/√(gD(s−1)) > 1`** to prevent salinity intrusion, with `s` the ambient/effluent
density ratio.

### Effluent tab (§5.2.3)

Flow, temperature, salinity, and **two** pollutant constituents. Mixing-zone acute and
chronic distances live on this tab too. Pollutants are conservative unless a decay rate is
given on the Ambient tab.

### Ambient tab (§5.2.4)

Depth profiles of: **near-field** current magnitude and direction, temperature, salinity,
background concentration, pollutant decay, then **far-field** current magnitude and
direction, and **α**. The near-field velocity is at the diffuser; the far-field profile may
legitimately differ (e.g. tidally averaged).

### Carbonate Chemistry tab (§5.2.5) — optional, checkbox "Calculate Carbonate Chemistry"

* Effluent: **only two of the three** pH / TA / DIC are needed — exactly what case03/case04
  showed. Manual example: pH 8.9, TA 2930, DIC 2500 μmol/kg.
* Ambient profiles of pH, TA, DIC and **Ca²⁺**.
* **K1K2: ten options. KSO4: four.** Plus editable K and reaction order N for aragonite and
  calcite.
  * ⚠️ **The manual is wrong on the count.** The dialog's own help text enumerates
    **fourteen** K1K2 options — the classic CO2SYS list 1–14 — and states that the
    reported pH scale follows the K1K2 choice. Its four KSO4 entries are a *combined*
    bisulfate × total-borate selector, not four bisulfate constants. See PLAN.md §2 (the chemistry-engine row);
    the help text is the authority, and `chem/constants.py` follows it.
* ⚠️ **"the project file does not save carbonate chemistry information"** — stated outright,
  confirming what we found the hard way.

### Dissolved Oxygen tab (§5.2.6) — optional, checkbox "Dissolved Oxygen Calculations"

Effluent DO, IDOD, cBOD5, nBOD5 and their decay rates; ambient profiles of DO, cBOD5,
nBOD5. Also **not saved in the project file**.

⚠️ **"DO and pH calculations cannot be conducted simultaneously"** — the XOR is explicit.

### Model Run tab (§5.2.7)

Near-field settings:

| Setting | Default | Note |
|---|---|---|
| Aspiration coefficient | **0.1** | entrainment rate; affects spreading and plume rise |
| Diffuser contraction coefficient | **1.0** | 0.61 sharp-edged, 1.0 bell-shaped |
| Light absorption coefficient | **0.16** | **explicitly unused** — reserved for a future Mancini bacteria model |
| Stop the plume at **bottom** hit | ✅ checked | |
| Stop the plume at **surface** hit | ✅ checked | |
| Stop at **shoreline** hit | unchecked | selecting it prompts for the shoreline vector |
| **No. of Maximum Plume Rise or Fall** | **2** | see below |
| Output interval | **5** steps | minimum 1 = every internal model step |
| Select Variables for Outputs | — | dropdown, adds to the default list |

**The rise/fall switch, fully specified** — this answers it outright:

| Value | Behaviour |
|---|---|
| 0 | terminate at the **first** trapping (initial neutral-buoyancy depth) |
| 1 | momentum carries the plume to its **maximum rise** |
| **2** | gravity returns it to a **second trapping depth** (default) |
| 3 | downward momentum carries it to its **maximum fall** |

"For discharges with negative vertical angle … the rise and fall sequence is reversed."
Under ideal conditions the plume oscillates about the trapping level at the **Brunt–Väisälä
frequency** (Frick et al. 2003).

**Shoreline vector**: distance *and* direction to the nearest shoreline, "+tive
counter-clockwise from the x-axis". So the `.prj`'s two reals are (distance, direction).

Far-field settings: **PLUMES Integrated farfield calculations** checkbox (default on);
eddy-diffusivity law (constant / linear / **4/3 default**); **Maximum Dilution** limit
(default 5000:1) *and* a maximum **distance** limit; output interval in **metres**
(default 10).

### Independent far-field calculator (§5.2.9)

Standalone Brooks run from the Project page. Inputs: initial wastefield dilution (enter 1 if
unknown), initial width, initial location (**≥ 0.001 m, not zero**), mixing-zone distance,
ambient current, α, optional initial pollutant concentration and decay.

**Output stepping is not user-controllable**: it divides the distance to the mixing zone into
**25 steps** and adds **3 beyond** — so a 200 m mixing zone prints every 8 m and ends at
224 m. Settings cannot be saved.

---

## 3. GUI structure

Tabs: **Welcome → Project → Diffuser → Effluent → Ambient → [Carbonate Chemistry] →
[Dissolved Oxygen] → Model Run → Model Results**, plus About. Diffuser/Effluent/Ambient only
unlock after a project is created.

* Each data tab has **Load** / **Save** for its own `*.csv`, and a **case** column: "The
  table may be populated with multiple diffuser designs but **only the checked
  configuration is used**." That is the `Yes`/`No` column's purpose. Since the `.prj` stores
  only the values and not the check state, loading a project evidently just uses its stored
  row — which reconciles the upstream example shipping `No` on the row that ran.
* **"the entered information is not saved until the model run is executed"** — inputs are
  written to the project file automatically *on run*. This explains the empty `test.prj` we
  saw earlier.
* Units: SI by default, switchable per column via a dropdown on the unit cell. **Output is
  always SI.**
* Results: graphical window plus a text window; text output is deliberately byte-formatted
  like Visual Plumes.

**Documented unit options** (extends what we decoded from case00):

| Quantity | Options |
|---|---|
| Flow | **MGD, cms, cfs** |
| Temperature | **°C, °F** |
| Pollutant | **mg/L, kg/kg of effluent** |
| Lengths | SI or FPS (m / ft) |

---

## 4. What the manuals resolve

| Question | Answer |
|---|---|
| Rise/fall switch semantics | Fully specified, 0–3, above |
| Termination criteria | Four, each with its own checkbox; bottom + surface on by default |
| Shoreline vector convention | (distance, direction), +ve CCW from x-axis |
| Surface-hit criterion | "when the plume **outer boundary** touches the water surface" — the edge, not the centreline, matching case06/case10 |
| Water depth at the diffuser | `port depth + port elevation` |
| `Ca` column | Ω uses a **salinity-based** `[Ca²⁺] = 0.01028 S/35`, so the column is inert |
| Chemistry / DO not in the `.prj` | Stated explicitly for both |
| DO XOR carbonate | Stated explicitly |
| Precipitation is *potential* only | Stated explicitly |
| `Yes`/`No` case column | Selects which stored row runs |
| Far-field ambient | Taken at the trapping/surfacing depth |
| Far-field width depends on current direction | Stated explicitly |
| Far-field limits | Max dilution (5000 default) **and** max distance |
| Unit dropdowns | MGD/cms/cfs, °C/°F, mg/L or kg/kg, SI/FPS |
| Independent far-field stepping | 25 steps to the MZ + 3 beyond, fixed |
| Centreline dilution is approximate | The manual says so, which fits `max(1, FluxAvg/2)` |

## 5. What the manuals do **not** specify

These remain the real gaps, and both editions defer identically:

1. **The `A_p` decomposition.** Described qualitatively only — "To estimate the projected
   area, it is necessary to express mathematically how the length of the element changes …
   Further details … can be found in Frick (1984) and Frick et al. (1995)." Neither paper is
   in the repo. **This is the single biggest remaining unknown for Phase 5.**
2. **The merging area correction.** Attributed to Baumgartner et al. (1994); the geometry is
   shown in a figure but no formula is given. Our measured merging trigger (a diameter/spacing
   ratio of ~1.00 at 0°, 0.895–0.938 at 30°, 0.793–0.843 at 45°) is not derivable from the text.
3. **The time-step controller.** Never mentioned. The output interval is in "internal model
   steps" but what sets a step is unstated.
4. **The ZFE / initial conditions.** How the contraction coefficient enters, and where the
   zone of flow establishment ends (we measured step ≈37 from case01's `CL-Dil`).
5. **The exact effective-spacing formula.** The manual says the width is "affected by current
   direction" but gives no expression. We measured cos(offset) for the width in the current
   build.
6. **The sigma-t polynomial.** Cited as Fofonoff (1985) with no coefficients. We measure a
   near-constant **+0.0275 kg/m³** offset of the exe against EOS-80 using the exe's own
   reported salinity and temperature.
7. **Ambient extrapolation** beyond the tabulated profile. Unspecified.

## 6. Corrections this review forces

**⚠️ Appendix A is not usable as validation data.** It tabulates 31 near-field dilution
values, 31 diameters, and 10 far-field dilution/width values as **PLUMES2.0 vs Visual Plumes
(UM3) pairs with no input conditions**. Without the diffuser/effluent/ambient behind each
number they cannot be reproduced. What Appendix A does give is the **acceptance bar**: mean
absolute relative error 0.37 % (diameter), 0.26 % (height), 0.41 % (dilution), R² ≥ 0.9996;
and far-field per-case errors of 0.03–0.62 %. **Ledger rows 12 and 13 are retired.**

**⚠️ The manual's own §5.2.8 worked numbers disagree with the shipped trace.** At 100 m the
manual reports dilution 179.5 and width 129.5 m; the shipped `.dat` says 177.326 and 144.163
for what is described as the same example. So the manual text, the shipped `.dat`, and the
current build represent **three** different generations of numbers. The §5.2.8 figures
(boil to 1.9 m → 185:1; second trapping at 3.4 m → 217:1; 102 m → 180.1:1 and 130.3 m) are
therefore informative but not authoritative — treat a disagreement as a provenance question
rather than a failure. **Ledger rows 9–11 are downgraded.**

**Useful nuance:** §5.2.8 says the boil-over case reaches a maximum centreline depth of 1.9 m
where the plume diameter is ≈7.8 m — matching case14's final diameter of 7.796 m almost
exactly, which is reassuring for the un-terminated surface path.
