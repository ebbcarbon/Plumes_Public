# PLUMES2.0 → Python: assessment and porting spec

Status: **the decoded specification, kept current as the port was built.**
First written 2026-08-12 as the pre-port assessment of the upstream snapshot (commit 1);
the port is now complete through Phase 9 — see [PLAN.md](PLAN.md) for where it stands.

---

## 1. What the executable actually is

`plumes2.0v1.exe` (3.5 MB, AMD64) is a **compiled Intel Fortran 90 Windows GUI
application**. No source is published — the upstream repo ships the binary only.

- GUI framework: **Winteracter** (commercial Fortran GUI toolkit — confirmed by
  `WDialog*` / `WGrid*` / `IGr*` symbols and `winter.ini` in the string table).
- Resources: Win32 dialogs, `upstream/icons/*.ico`, `upstream/images/*.bmp`.
- Provenance: EPA + PNNL + UW Salish Sea Modeling Center. BSD-2 (Battelle, 2024)
  — **re-implementation and redistribution are permitted**; keep the copyright
  notice and the PNNL disclaimer.

It is a revival of EPA's **Visual Plumes / UM3** (Frick et al. 2004), which was
Delphi Pascal and no longer runs on modern Windows.

**Implication for the port:** there is no code to translate. The port is a
re-implementation from (a) the two manuals in `upstream/Docs/`, (b) the published UM3
literature, and (c) the shipped golden output trace. Section 5 lists the one
genuinely under-specified piece.

## 2. Feature inventory (what "all the same features" means)

Derived from the manuals + the exe's string table.

**Physics**
1. Near-field **UM3** Lagrangian Control Volume solver — jet/plume dynamics,
   Taylor (shear) + forced (projected-area) entrainment, multiport **plume
   merging**, 3/2-power radial profile, flux-averaged *and* centerline dilution.
2. Termination criteria: trapping (neutral buoyancy), velocity reversal,
   surface hit, bottom hit, shoreline hit, and the **"No. of maximum plume rise
   or fall" = 0/1/2/3** switch.
3. Far-field **Brooks (1960)** — three eddy-diffusivity laws: constant,
   linear, 4/3 power. Plus first-order pollutant decay.
4. **Carbonate chemistry** — TA/DIC advected as scalars, pH via embedded
   CO2SYS (10 × K1K2 options, 4 × KSO4 options), Ω_arag / Ω_calc, and
   Zhong & Mucci (1989) potential precipitation rates.
5. **DO / BOD** — IDOD, cBOD5/nBOD5 → ultimate BOD, θ temperature correction,
   far-field DO sag. (Mutually exclusive with carbonate chemistry in the exe —
   the Python port need not keep that restriction.)
6. **Independent far-field calculator** — standalone Brooks run, 25 steps to
   the mixing zone + 3 beyond.

**I/O and UI**
7. `.prj` project file (format decoded — §4), 6 CSV tables, ASCII output file
   byte-formatted like Visual Plumes, ~20 plot types, unit switching
   (SI/FPS on input; output always SI), acute/chronic mixing-zone flags.

## 3. Physics spec (all equations located)

`upstream/Docs/PLUMES2.0v1_SSMC_User Manual.pdf` is the superset (64 pp; the EPA one is
54 pp and predates the DO/carbonate work). Section map:

| Topic | Section | Equations |
|---|---|---|
| LCV continuity / momentum / heat / salt | 2.3.1 | 2–5 |
| 3/2 power profile, flux-averaged conc. | 2.3.1 | 6–7 |
| Brooks width growth (3 cases) | 2.3.2 | 10–13 |
| Brooks centerline concentration (3 cases) | 2.3.2 | 14–16 |
| TA/DIC transport, Ω, precipitation | 3.2 | 17–22 |
| DO after initial dilution, BOD, DO(t) | 4.2 | 23–30 |
| ε₀ = α·w₀^(4/3), α ∈ [1e-4, 5e-4], default 3e-4 | 5.2.4 | 15 (dup. numbering) |

Density: Fofonoff (1985) sigma-t equation of state. Peak/mean concentration
ratio 3.89 (round) / 2.22 (fully merged line plume).

Defaults (Visual Plumes parity): aspiration coefficient **0.1**, contraction
coefficient **1.0**, light absorption 0.16 (unused), max rise/fall switch **2**,
near-field output interval 5 steps, far-field interval 10 m, max dilution 5000.

## 4. File formats (decoded from `upstream/Example_project/`)

**`.prj`** — fixed-width Fortran text. Layout: description line, then per-table
blocks of `I11` flags followed by `E12.3` data rows (20 rows/table):

> **Correction (2026-08-12), from diffing the `.prj` files in
> [reference_cases/](../reference_cases/) against the example:** the per-table `I11`
> blocks are **unit selectors, one per column** (diffuser 9, effluent 5, mixing
> zone 3, ambient 11), *not* case flags — the per-row case enable lives in the
> CSVs' leading `No`/`Yes` column. case01's effluent block is `[1,2,1,1,1]`, so its
> flow is stored in a different unit than the example's MGD. The trailing
> variable-name lists are also count-prefixed and variable-length (5 vs 9
> near-field names), so a reader must be sequential rather than line-offset based.
>
> **Unit flag map, decoded** from the matched `.prj`/`.dat` pair in
> [case00](../reference_cases/case00_macoma_legacy_fps/): **flag 1 = the primary unit,
> flag 2 = the alternate one** — feet for lengths, m³/s for flow. In that project
> diffuser spacing (flag 2, stored 2.0) echoes as 0.61 m and both mixing-zone
> distances (flags 2, stored 20.7 / 207.0) echo as 6.31 / 63.09 m, all exactly
> ×0.3048; flow with flag 2 is labelled `(m3/s)` there and `(cms)` in 2026 builds,
> against `(MGD)` for flag 1. **The flag genuinely reinterprets the stored number** —
> case01 and case02 both store `0.005` and differ by 23× in flow.
>
> **Flag-to-column alignment differs by table.** The diffuser's 9 flags map 1:1 to its
> 9 columns (spacing is column 5 and flag index 5 carries the 2). Effluent (5 flags /
> 4 columns), mixing zone (3 / 2) and ambient (11 / 10) each carry **one leading flag
> of unknown purpose** and then map 1:1 — effluent flow is column 0 but its selector
> is flag index 1.
>
> **The number of plot flags is build-dependent**: the Dec-2025 build writes one
> near-field plot flag where 2026 builds write four (147 vs 149 lines). Both plot
> blocks must therefore be read greedily up to the next text record, taking the last
> integer as the name count.
>
> When a `.prj` and its CSVs disagree, **the `.prj` wins** — case01's output echoes
> the `.prj` value at 15 m, not the stale CSV one.
>
> Known variable names for the count-prefixed lists, near-field:
> `FluxAvg-Dilution, Plume-Diameter, Position-Xdir, Position-Ydir, Plume-Depth,
> Plume-Density, Pollutant-Conc., Centerline-Dilution, Time, Amb-Current,
> Net-Dilution`; far-field: `Dilution, P-Width, Distance, Pollutant-Conc.,
> Background, Time`. (The last few are inferred from output column headers
> `Amb-Curr`, `Net-Dil`, `Bckgrd`; exact `.prj` spelling unconfirmed for those.)

diffuser (9 cols) → effluent (4) → mixing zone (2) → ambient (10) → near-field
settings (aspiration, contraction, light abs., then integer flags, output
interval, output filename) → shoreline vector → far-field flags → variable
name lists.

**CSVs** — quoted scientific notation, 20 fixed rows, leading `No`/`Yes` case
column on diffuser/effluent/mixing-zone tables:
- `Ambient`: depth, current, direction, salinity, temp, background pollutant,
  decay, far-field speed, far-field direction, dispersion α
- `Diffuser`: case, port dia, port elev, vertical angle, horizontal angle,
  n ports, spacing, port depth, X, Y
- `Effluent`: case, flow (MGD), salinity, temp, pollutant
- `Mixing_zone`: case, acute, chronic
- `AmbientDO`: depth, DO, cBOD5, nBOD5
- `AmbientChem`: depth, TA, DIC, pH, Ca

> **Chemistry findings (2026-08-12), from
> [case03](../reference_cases/case03_macoma_carbonate/):**
> - **Input units are µmol/kg** (TA, DIC, Ca — the GUI dropdown has only this one
>   option). The **effluent** endmembers are converted to the output's `mmol/m3` using
>   **effluent density** (factor brackets EOS-80 ρ(35,10)/1000 = 1.026952 to ±0.06 %),
>   but the **ambient** chemistry CSV is read as already-`mmol/m3` and is *not*
>   converted. The two endmembers are therefore mixed in inconsistent units, leaving
>   ambient TA/DIC ~2.4 % low — a genuine exe bug. Output pH is **total** scale even
>   when input pH is entered on the **free** scale, so pH scales *are* converted.
> - TA and DIC are **integrated stepwise through the LCV loop**, not derived
>   algebraically from dilution: the implied endmember drifts 0.26 % monotonically
>   across a run (~7 ppm per step).
> - **Input pairing:** the exe prefers **TA + DIC**. `DIC = 0` acts as a
>   "not specified" sentinel and makes it fall back to **TA + pH**; a *blank* field is
>   rejected with an error. Confirmed by case04, where TA 4000 + DIC 1646 + pH 11 was
>   solved from TA + DIC and the pH entry ignored. The example project's inconsistent
>   `pH = 7.80` is a stale value.
> - **Precipitation rates:** `R = exp(logK)·(Ω − 1)^N`, exact to 5 significant figures
>   over 82 rows. GUI parameters are calcite `0<S<44: logK = -0.106, N = 2.87`;
>   aragonite `logK = 1.53, N = 2.33` and `35<S<44: logK = 1.11, N = 2.26`. Note the
>   exe applies **`exp()` where the label and Zhong & Mucci (1989) imply `10^()`** —
>   a 14.8 % overestimate of the calcite rate if so.
> - **The `.prj` unit flags include feet.** A Dec-2025 run rescaled port spacing and
>   both mixing-zone distances by 0.3048 while leaving port dimensions metric, in one
>   file. See [case00](../reference_cases/case00_macoma_legacy_fps/).
> - **Output header text varies between exe builds** (`Avg-Dil` vs `Dilutn (FluxAvg)`,
>   bare vs parenthesised unit rows, `kg/kg` vs `mg/L`, `m3/s` vs `cms`), and an older
>   build emits a `P-Temp` column. The `.dat` reader must not key on exact strings.
> - The entered **`Ca` is not used for Ω** — reported Ω matches salinity-derived
>   calcium to 0.18 %, not the entered 100 µmol/kg.
> - **TA and DIC are advected as conservative scalars.** Implied effluent values
>   back out of 41 rows with 0.12 % scatter, so the reported precipitation rate is
>   *potential* and does not remove TA.
> - **Chemistry does not feed back on hydrodynamics** — case02 and case03 have
>   bit-identical near-field traces.
> - **Chemistry columns are appended automatically** when the module is on (7 in the
>   near field, 5 in the far field), not selected via the `.prj` name list.
> - **No chemistry state is stored in the `.prj` at all** — not the effluent TA/DIC,
>   not an enable flag, not the chem CSV filename. A `.prj` we write therefore
>   cannot round-trip chemistry back into the exe. Chemistry is **session state**:
>   loading a different project does *not* replace the chemistry table the GUI holds,
>   confirmed 2026-08-12 when a generated 11 m-port project met the 1-4 m table left
>   over from case03.
> - **The exe requires the ambient chemistry profile to extend deeper than the port**,
>   refusing to run otherwise with *"Please input the ambient chemistry conditions at a
>   depth greater than port depth"*. Strictly greater — equality does not satisfy it, as
>   far as we can tell. It appears to check only the deep end; nothing stops the profile
>   starting below the port, which is what let case09 extrapolate off the shallow end.
> - Exe vs **PyCO2SYS at the exe's own declared options (K1K2 = 10, KSO4 = 1)**:
>   RMS Δ pH 0.025, rising from +0.015 below pH 9 to **+0.068 near pH 10**, and
>   2.7 % in Ω_arag near the port. Using the declared options is *worse* than the
>   best-fitting option 2 (RMS 0.013), so the divergence is an **implementation
>   difference, not a constants choice**. It scales with hydroxide
>   (Δ pH ≈ 5.4e-4·[OH⁻] + 0.014, R² 0.83); borate is the other likely contributor.
>   Ω_calc/Ω_arag is 1.5725 in the exe vs 1.5836 in PyCO2SYS — a constant 0.23 %
>   Ksp formulation difference, separable from the pH bias.
> - **`R_arg` is identically 0 for plume salinity below 35** — the aragonite branch
>   only covers `35 < S < 44`. case07 crosses the threshold mid-trace and the switch is
>   exact: 12 of 105 rows have S > 35 and exactly those 12 have `R_arg` > 0, flipping
>   between S = 35.302 (R_arg 578.082) and S = 34.903 (R_arg 0.000).
> - **`R = exp(logK)·(Ω − 1)^N` yields NaN whenever Ω < 1**, since N is fractional and
>   the base is negative. The NaN then propagates through the solver state, defeats the
>   termination tests, and the run grinds to the step cap (5000) emitting NaN. This is
>   critical for alkalinity work, where undersaturated receiving water is the point:
>   our port returns 0 for Ω ≤ 1 instead, as a documented divergence.
> - The entered **`Ca` is ignored for Ω** and for both rate laws.
> - The plume centreline can rise **above the free surface** (case09 depth +0.041 m)
>   with no clamp or reflection, and the ambient chemistry profile is extrapolated far
>   outside its defined depth range when that happens.
> - The **shoreline vector appears inert**, across three configurations: 45° alone and
>   45° + 5 m produce byte-identical output (case08), and 60° + 5 m **with the "stop
>   plume at shoreline" checkbox enabled** still ends on trapping while the plume
>   travels to y = 5.389 m, past the stated 5 m shoreline (case12). No shoreline event
>   appears in any of our twelve traces, and no saved `.prj` has a non-zero shoreline
>   vector, so the coordinate convention remains unknown.
> - A **single-port** run (`Ports = 1`) produces no usable output at all (case09).
> - The effluent endmember the model transports is **TA ~4109 against an entered
>   4000** (µmol/kg). ✅ **Explained (Phase 4, 2026-08-12):** a density factor does
>   account for it — both entered effluent values are multiplied by ρ_eff/1000 =
>   1.02695, giving 4107.8 and (for case04's DIC) 1690.4 against least-squares
>   back-outs of 4109.2 and 1689.3. The ambient CSV is not converted. The earlier
>   guess that this was the same effect as a high-pH alkalinity bias was wrong:
>   case04 changed pH from 10.5 to 11 with the transported TA unmoved.

**Output** — `ModelResults_TxtOutputs.dat`: 100-char rule lines, an echo of the
ambient and diffuser tables, then the step table, with in-line event banners:
`Plume traps`, `merging happened`, `Plume surfaces`, `Plume hits the bottom`,
`Local maximum rise or fall`, `Starting Farfield Calculations`,
`Reached Chronic Mixing Zone`. Those seven are the complete set across our eleven
traces, and a test asserts no others appear.

> **Additions (2026-08-12), from the runs in [reference_cases/](../reference_cases/):**
> - Two more output elements: the banner `Local maximum rise or fall`, and the
>   trailing line `Note: Plumes not merged, Brooks method may be overly
>   conservative`. Banner rule-lengths are not uniform — copy them literally.
> - **Boundary termination tests the plume edge, not the centreline:**
>   `depth − radius ≤ 0` at the free surface and `depth + radius ≥ bottom` at the
>   seabed, where `bottom = port depth + port elevation`. Bracketed by case06
>   (+0.024 → −0.025) and case10 (2.984 → 3.189 against a 3.0 m seabed).
> - **The terminating step is always printed.** It is an extra *truncated* row (base
>   variables only, no chemistry) when it falls off the output interval, and an ordinary
>   complete row when it lands on it. Truncated in case05/06/07 (steps 417, 356, 529);
>   complete in case10/11 (345, 500).
> - **The far-field section may be absent entirely** — case01 ends after the
>   near-field with only that note. But it is *not* gated on merging: case02 has
>   unmerged plumes and runs Brooks anyway, printing `Starting Farfield
>   Calculations` and then the note. So the note is an advisory about merging and
>   the far-field is enabled separately (a `.prj` flag, not yet identified).
> - Step-table columns are selected by the `.prj` variable-name list, in order
>   (5 columns in the example, 9 in each Macoma case, with different sets).
> - Decoded output relations, all exact:
>   `CL-Dil = max(1.0, FluxAvg-Dilution / 2)` (0 exceptions in 125 rows across
>   case01+case02), `P-Con. = C_effluent / dilution`, and
>   `Net-Dil = FluxAvg-Dilution` at zero background. The centerline value therefore
>   carries no independent information, and the factor is 2 rather than the
>   3.89 / 2.22 peak-to-mean ratios quoted below — worth flagging upstream.
> - **Far-field start distance = `hypot(x_posn, y_posn)`** at the near-field
>   endpoint (case02: 2.896; example: 7.319 vs 7.320 printed).
> - **Wastefield width = (n_ports − 1) × spacing + diameter** — exact for case02
>   (24 × 2.0 + 0.558 = 48.558 → 48.56) but 0.5 % high for the example
>   (17 × 6.10 + 6.481 = 110.181 vs 109.59 printed). case02 has a 90° horizontal
>   angle and the example 30°, so this is probably where the effective-spacing /
>   cross-diffuser-angle correction of §5 enters. Implied effective spacing for the
>   example is 6.065 m against a nominal 6.10 m.
> - The `Reached Chronic Mixing Zone` banner fires when the *next* step would cross
>   the MZ, and the run does **not** necessarily stop there — case02 continues to
>   501.611 m past a 207 m chronic MZ. Where it stops is unexplained; max dilution
>   (5000) is already exceeded at the 500 m row.

## 5. The one real unknown — ✅ **closed 2026-08-12**

The manuals give the LCV *governing* equations but **not** the projected-area
`A_p` decomposition, the merging area correction, the time-step controller, or
the ZFE initial conditions. Those live in Frick (1984), Frick et al. (1995), and
Baumgartner et al. (1994).

> ### ✅ Baumgartner et al. (1994) obtained; the physics is fully specified.
>
> The third of those citations turns out to be a **US EPA report in the public domain** —
> *Dilution Models for Effluent Discharges*, 3rd ed., EPA/600/R-94/086 — and its
> **UM MODEL THEORY** section (pp. 111–142) gives every equation the PLUMES2.0 manuals omit.
> Archived at
> [references/](../references/) with an index of what it settles. This section's premise no
> longer holds: there is no under-specified physics left in the near field, only
> implementation.
>
> Beware the partial copy circulating as `DOS-PLUMES-guide-pages1-94.pdf`: it **stops before
> the theory section entirely**.
>
> The projected area is three terms, each paired with a different *component* of the ambient
> current in a local frame (`ê₁` along the trajectory, `ê₂` horizontal normal, `ê₃` vertical):
>
> ```
> growth      u1 . ( pi b db ),   db = (db/ds) h              eqs 38-39
> cylinder    u2 . ( 2 b h )                                  eq 40
> curvature   u2 . ( -(pi/2) b^2 (dtheta/ds) h )   [signed]   eq 41
> u3 dropped -- only the two-dimensional problem is considered
> ```
>
> Merging reduces each of the four entrainment terms **by a different factor** (eqs 51–54) and
> changes the mass-to-radius inversion, because a reflecting plane half-way between ports caps
> the element's transverse extent at the spacing `L` (eqs 55–56). Full detail in PLAN.md §2b
> and Phase 5.
>
> ⚠️ **Two corrections to the report, both measured from the traces (2026-08-13).**
>
> 1. **The Taylor shear velocity is relative to the ambient.** Eq 34 writes
>    `beta_T = alpha |V|`; the exe behaves as `alpha |V - U_a|`. This is a refutation, not a
>    preference — with the literal form the Taylor term alone *exceeds* the total entrainment
>    the exe applied over the late jet, which would require forced entrainment to be a sink.
>    The two forms are identical when `U_a = 0`, so no zero-current run can distinguish them.
> 2. **The projected area is attenuated.** The measured forced term is the unit-weight PAE
>    multiplied by a factor that collapses onto `|U_a| / |V|` alone — 0.22 at 0.1, rising to
>    0.87 at 0.9 — consistently across a tenfold range of current. No derivation for it yet;
>    the report cites Frick (1984) and Cheung (1991) for this part and we have neither.
>
> Also settled: the step controller pins the mass increase at ~2 % per step and adjusts the
> time step to suit, so the physics determines *how long each step takes*. Nothing rescales
> the entrainment components beyond that bookkeeping.
>
> The guess recorded below — "`A_p` = growth + cross-flow + cylinder/curvature" with the
> cross-current term distributed over merged plumes and a 20° cap — was **roughly right on the
> term names and wrong on the structure**: the three terms are not summed against one velocity,
> and the angular limit is 45°–135° on the current-to-diffuser angle, not a 20° cap.

> **Largely resolved (2026-08-12).** The `A_p` decomposition and the time-step controller
> are still open, but the **effective-spacing correction is decoded**:
>
> ```
> effective spacing = port spacing x |cos(horizontal angle - current direction)|
> wastefield width  = (n_ports - 1) x effective spacing + final plume diameter
> ```
>
> It fits **every current-build run** exactly — nine of ten, the exception being the
> *shipped* trace. Every Macoma case discharges
> parallel to the current, so the offset is zero and the cosine is 1 — which is why the
> uncorrected form fitted them all and hid this. The ninth run is the *shipped* upstream
> trace, whose 109.59 m implies 0.9943 x nominal rather than cos(30 deg) = 0.866; a
> current-build run of a byte-equivalent project gives **96.29 m**, matching the cosine.
> **Confirmed independent of chemistry** by case14: the same project run with chemistry off
> gives 97.60 m against a cosine prediction of 97.603, from a different final diameter. So
> the shipped trace's 109.59 m is an **older-build** value — and the carbonate module exists
> only in the newest build, so the shipped `.dat` necessarily predates it. Its far-field
> numbers are not targets for the current exe; its near field is (steps 5-275 are
> bit-identical across the shipped trace, case13 and case14).
>
> **The merging criterion is a *separate* correction, and not the same cosine.** Merging is
> build-invariant (the shipped example and case13 have bit-identical trajectories and merge
> at the same step), whereas the width formula changed between builds. Bracketing the merge
> from the rows either side of the banner gives a diameter/nominal-spacing ratio of
> 0.982-1.038 at a 0 deg offset, 0.895-0.938 at 30 deg, and 0.793-0.843 at 45 deg
> (case15) — every oblique bracket lying **above** cos. `cos^(1/2)` and `cos^(2/3)` both fit
> and cannot be separated by these brackets. **One run at an oblique angle with the output
> interval set to 1** would narrow them ~5x and settle it.

**Validation targets already in hand:**
- ⚠️ **The shipped example's far-field numbers are old-build values** and are not
  reproducible by the current exe — see the note above. Its near-field is reproduced
  exactly, bit for bit.
- **"Stop plume at surface" is a separate GUI control**, distinct from the max rise/fall
  switch, and not stored in the `.prj`. case13 and case14 are the same project with it
  toggled: identical trajectories, but the run ends at the surfacing step with it on and
  continues to a second trapping with it off.
- `upstream/Example_project/ModelResults_TxtOutputs.dat` — a full 55-step near-field
  trace for the shipped case (18 ports, 0.076 m, 45°/30°, 8 MGD, 11 m depth):
  traps at step 255, merges at 260, surfaces at 275, **flux-avg dilution
  169.754**, wastefield width **109.59 m**, far-field to 104.435 m → **178.408**.
- Manual §5.2.8 gives alternative-setting answers for the same case: boil to
  1.9 m depth → 185:1; second trapping at 3.4 m → 217:1; far-field at exactly
  102 m with a 1 m interval → 180.1:1 and 130.3 m wide.
- Appendix A tabulates **31 near-field dilution + diameter pairs** and **10
  far-field dilution + width pairs** (PLUMES2.0 vs Visual Plumes). Upstream's
  own acceptance bar was ≤0.5% mean absolute relative error — a reasonable bar
  for this port too.

Brooks far-field, carbonate chemistry, and DO/BOD are all closed-form and
should reproduce to round-off; validate carbonate against **PyCO2SYS**, which is
what upstream validated against.

## 6. Suggested build order

1. I/O layer (`.prj` + CSV readers/writers, output formatter) — fully specified,
   testable against the example project immediately.
2. Brooks far-field + independent far-field calculator — closed form.
3. DO/BOD and carbonate chemistry — closed form; PyCO2SYS for the constants.
4. Near-field UM3 LCV — the real work; iterate against the golden trace.
5. Plots (matplotlib) + CLI, then a GUI if wanted.

A pure-Python/NumPy near-field is fine performance-wise: the golden case is
~275 steps.

## 7. Reference material

- `upstream/Docs/PLUMES2.0v1_SSMC_User Manual.pdf` — primary spec (v1, incl. chemistry).
- `upstream/Docs/EPA_SSMC-PLUMES2.0_User Manual_reformat_v4_B-24.pdf` — EPA edition.
- EPA Visual Plumes manual (4th ed.), 148 pp, UM3 background and PAE notes:
  <https://19january2021snapshot.epa.gov/sites/static/files/documents/VP-Manual.pdf>
- Premathilake & Khangaonkar (2019), *Mar. Pollut. Bull.* 149:110554 —
  FVCOM-plume, the direct Fortran ancestor of this near-field module.
- Frick (1984), *Atmos. Environ.* 18:653 — non-empirical closure / PAE.
- Frick, Baumgartner & Fox (1995), *J. Hydraul. Res.* 32:935 — bending plumes.
