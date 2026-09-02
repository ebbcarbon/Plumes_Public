# Reference cases

Exe-generated runs used as validation targets, one numbered folder per case (case00–case50), each
with a README of what was changed and what the output revealed. Since 2026-08-13 most new cases
start as a **generated experiment** in [`pending/`](pending/README.md): `plumes2.experiments` writes
the `.prj` beside a note carrying the GUI-only settings and the predictions registered *before* the
run; the operator runs it, copies the returning `.dat` and the rewritten (as-run) `.prj` aside, and
the folder graduates here. The exe overwrites the same filenames on every run, so the copy-aside
step is the one that matters.

## The one thing that does need care

**Save the project (`.prj`) before or after each run.** case02's saved as 0 bytes;
its hydrodynamic settings were eventually recovered from case03, but only by luck —
the two runs happened to have identical traces. The `.dat` echoes the ambient and
diffuser tables, so most inputs survive a lost `.prj`, but these live only in the
project file: aspiration coefficient, contraction coefficient, the max rise/fall switch
(`nearfield_flags[3]`), the stop-at-surface box (`nearfield_flags[1]`, case46) and the far-field
eddy-diffusivity law (far-field flags 2/3/4, case50). ⚠️ The `.prj` has **no far-field settings
block**: the far-field stop distance and dilution, the other stop boxes and the output-column
selection are session state it never carries (ledger row 277).

**And note the `.prj` does *not* save chemistry at all** — not the effluent TA/DIC,
not the constants options, not the chem CSV name. For any chemistry run, the
endmembers and K1K2/KSO4 options have to be written down separately — record them
in the case README alongside the trace.

⚠️⚠️ **The Dissolved Oxygen tab is the same, and worse, because it *retains* values.**
It is not saved in the `.prj` either, and the tab keeps whatever was last typed —
so a run can silently inherit a previous case's cBOD5 while the experiment note says
something else. This has now happened twice, and the second time cost two rounds of
analysis: case25 and case26 were both worked up against a cBOD5 of 2000 that was
never entered (it was 20), which manufactured a rate-dependent "amplitude" that did
not exist. **Read the six DO fields off the tab at run time and send them with the
trace** — DO, IDOD, cBOD5, nBOD5 and both decay rates. A far-field trace without
them is not evidence of anything.

## Manifest

| Case | Regime | Flow | Ports | Steps | Far-field | Chem | Notes |
|---|---|---|---|---|---|---|---|
| [`Example_project/`](../upstream/Example_project/) | positively buoyant, freshwater | 8.00 MGD | 18 × 6.10 m | 275 | ✅ runs, merged | — | upstream golden case; surfaces |
| [case01_macoma_cms](case01_macoma_cms/) | **negatively buoyant** | 0.005 **cms** | 25 × 2.00 m | 420 | ❌ **skipped** | — | oscillates; unmerged |
| [case02_macoma_mgd](case02_macoma_mgd/) | negatively buoyant, weak momentum | 0.005 **MGD** | 25 × 2.00 m | 410 | ✅ runs while unmerged, to 501.6 m | — | `.prj` saved empty; settings recovered from case03 |
| [case03_macoma_carbonate](case03_macoma_carbonate/) | same as case02, **bit-identical** | 0.005 MGD | 25 × 2.00 m | 410 | ✅ runs, to 212.4 m | ✅ **TA/DIC/pH/Ω/rates** | **the key case** — effluent TA ≈ 4115, near-port pH 10.00 |
| [case04_macoma_ta_dic](case04_macoma_ta_dic/) | same as case03, **bit-identical** | 0.005 MGD | 25 × 2.00 m | 410 | ✅ | ✅ TA+DIC entered | diagnostic: pH ignored; unit bug + precip formula decoded |
| [case05_macoma_merging](case05_macoma_merging/) | negatively buoyant, **plumes MERGE** | 0.005 cms | 25 × **0.60 m** | 417 | ✅ merged, to 507.2 m | ✅ | **`merging happened`** — merges at dia = spacing at 90°; interval 5 |
| [case06_macoma_arag_s36](case06_macoma_arag_s36/) | **positively buoyant, surfaces** | 0.005 cms | 25 × 0.60 m | 356 | ✅ merged, to 504.7 m | ✅ **R_arg nonzero** | ambient S=36; aragonite band + inert `Ca` both confirmed |
| [case07_macoma_s45_dense](case07_macoma_s45_dense/) | **strongly dense**, 45 psu effluent | 0.005 cms | 25 × 0.60 m | 529 | ✅ merged, to 210.3 m | ✅ | **S=35 aragonite cutoff crossed mid-trace**; no bottom hit (traps at 3.2 m) |
| [case08_macoma_shoreline](case08_macoma_shoreline/) | = case05 | 0.005 cms | 25 × 0.60 m | 417 | ✅ to 209.5 m | ✅ | shoreline vector 45° — **no effect at all**; two runs byte-identical |
| [case09_macoma_single_port](case09_macoma_single_port/) | **exe fails** | 0.005 cms | **1 port** | 5001 | all NaN | all NaN | 955 NaN rows; `(Ω−1)^N` NaN for Ω<1; plume rises above the surface |
| [case10_macoma_bottom_hit](case10_macoma_bottom_hit/) | dense, **hits the seabed** | 0.005 cms | 25 × 0.60 m | 345 | ✅ to 208.5 m | ✅ | **`Plume hits the bottom`** — elevation 1 m; boundary criterion decoded |
| [case11_macoma_single_port_slow](case11_macoma_single_port_slow/) | **single port, clean** | 5e-5 cms | **1 port** | 500 | ✅ to 72.1 m | ✅ | corrects case09: the failure was exit velocity, not port count |
| [case12_macoma_shoreline_enabled](case12_macoma_shoreline_enabled/) | = baseline, 2.00 m spacing | 0.005 cms | 25 × 2.00 m | 400 | ✅ unmerged, to 207.9 m | ✅ | shoreline **checkbox on**, 60°+5 m — still no effect |
| [case00_macoma_legacy_fps](case00_macoma_legacy_fps/) | — | — | — | **0** | — | — | Dec 2025, older exe build; header-only, **no data rows**. Format artifact: proves per-column **ft** unit flags |

Three runs (case02, case03, case04) share bit-identical hydrodynamics and differ
only in chemistry — the most productive artifacts in the set. It also proves
chemistry does not feed back on the plume dynamics.

The archive continues past case12 with the designed experiments — same columns, one row per
case (the folder's own `README.md` carries the full story, and `LEDGER.md` cites them by row).
Where a README omits an input it inherits (a flow, a spacing), the Macoma or upstream-example
baseline is shown:

| Case | Regime | Flow | Ports | Steps | Far-field | Chem | Notes |
|---|---|---|---|---|---|---|---|
| [case13_generated_example](case13_generated_example/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 275 | ✅ to 104.5 m, width **96.29 m** | ✅ carbonate on | first project written by the port; exe loads it and the near field is **bit-identical** to upstream — and the 96.29 vs 109.59 m gap decoded the **effective-spacing cosine**, `17 × 6.10 × cos30° + 6.481` |
| [case14_generated_nochem](case14_generated_nochem/) | positively buoyant, runs past the surface | 8.00 MGD | 18 × 6.10 m | 476 | ✅ width **97.60 m** | — (chemistry off) | same `.prj` with chem off and the surface box cleared: **cosine law confirmed a second time off a different final diameter**; ⛔ its archived `.prj` is stale, so the "byte-identical `.prj`s stop differently" claim (row 187) is void — see case46 |
| [case15_oldbuild_angle45](case15_oldbuild_angle45/) | negatively buoyant, unmerged | 0.005 cms | 25 × 2.00 m | 2 arms, 84 rows | — | — | old build at 90° and 45°: **merging is build-invariant, the width formula is not** — and the merging angle factor is *not* `cos`, it sits at `cos^½`–`cos^⅔` |
| [case16_oldbuild_angle_sweep](case16_oldbuild_angle_sweep/) | negatively buoyant, Macoma base | 0.005 cms | 25 × 2.00 m | 5 arms, 83–494 rows | ✅ test20 only (width 50.12 m) | — | old-build H-angle sweep 45–175°; **the 45°/135° mirror pair merges at `d/L` = 0.8430 identically**, pinning `\|sin ψ\|` independently (row 205). No `.prj` survives for any of the five |
| [case17_independent_farfield](case17_independent_farfield/) | — (no near field) | — | — | — | ✅ **standalone Brooks**, 50 m width, α 0.0003, D₀ = 100 | — | the exe's far-field calculator run alone — **the only place Brooks is observable without a near field in front of it**; our integration matches to 4.8×10⁻⁴ |
| [case18_zero_current_pair](case18_zero_current_pair/) | negatively buoyant, **none merge** | 0.005 / 5e-5 cms | 25 or **1** × 2.00 m | 6 arms, 365–768 rows | ❌ | — | the entrainment isolation set: **Taylor α = 0.0967/0.0991 against the entered 0.1**, and the contraction coefficient is the vena contracta (`b₀ = (d/2)√c`) |
| [case19_current_sweep](case19_current_sweep/) | negatively buoyant, single plume | 5e-5 cms | **1 port** | 4 arms, 318–472 rows | ❌ | — | current sweep 0.01–0.10 m/s: **the cross-flow closure `k` does not transfer** (0.05→0.25→0.45) so `ForcedEntrainment.cross_flow` defaults to 0; test27 ≡ test24 byte for byte proves determinism |
| [case20_spacing_sweep](case20_spacing_sweep/) | negatively buoyant, test32 **merges** | 0.005 cms | 25 × 1.00–5.00 m | 3 arms, 420–425 | — | — | ⛔ retired as the accuracy bar by case44; still holds **the merge trigger `d ≥ effective spacing` to 0.7 %** (steps 309/310) and that spacing is inert until merging (test31 ≡ test33) |
| [case21_merging_spacing_prediction](case21_merging_spacing_prediction/) | negatively buoyant, all merge | 0.005 cms | 25 × 1.00–2.00 m | 3 arms, 494–526 | — | — | 85° offset, spacing 1.0/1.5/2.0 m against a **prediction registered before the runs**: the derived instantaneous-heading law tracks the curve with no free parameter, **the fitted ellipse is excluded by 13–23 %** |
| [case22_limiting_spacing](case22_limiting_spacing/) | dense, sinks (−45°), traps | 0.005 cms | **1 port**, 0.20 m | 2 arms, to step 527 | — | — | first port-generated `.prj`s with predictions pre-registered: **`merging happened` fires on a single port** — UM3's limiting-spacing rule, no port-count guard; its "caps a runaway" claim is retracted |
| [case23_limiting_spacing_gap](case23_limiting_spacing_gap/) | dense, sinks, traps | 0.005 cms | **1 port**, 2.0 m depth | 575 | — | — | the 2.0 m-depth run that separates the two readings case22 left: **threshold is `diameter > port depth`, not twice it**, bracketed (0.539, 1.014] — so PLUMES2.0 ≠ the Visual Plumes UM3 source |
| [case24_macoma_dissolved_oxygen](case24_macoma_dissolved_oxygen/) | merges & surfaces (36–38); unmerged pair (39–40) | 0.005 cms | 25 × 1.00 / 2.00 m | 5 arms, 420–526 | ❌ none reach it | ✅ **DO** (+ carbonate on test38) | the DO module's near field: **DO is a pure overlay and the entrained ambient is path-integrated**, `d(DO·D)/dD = DO_a(z)` to 0.0064 mg/L; both BOD channels inert; seed = `DO_e − IDOD` |
| [case25_farfield_bod](case25_farfield_bod/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 3 arms | ✅ **first far field with BOD active** | ✅ DO/BOD | uniform-ambient runs collapse to eq 23 to 0.0078 mg/L and eq 30 carries `1/FF` — but **eqs 28–29 are refuted: run 3's DO *rises* to 15.5 mg/L in oxygen-demanding water**, an exe defect |
| [case26_farfield_bod_rates](case26_farfield_bod_rates/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 3 arms | ✅ to 500 m | ✅ DO/BOD, rates 1–5 /day | rates raised so the sag curves (0.47 vs 0.0019 mg/L): **far-field DO reaches 99.9 mg/L, ~9× saturation**, matching a pre-registered prediction of 102.4 — the defect confirmed at two rates |
| [case27_farfield_bod_conversion](case27_farfield_bod_conversion/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 10 arms, 275–572 near steps | ✅ to 500 m | ✅ DO/BOD, IDOD arm | `D_near` swept 169.75 → 246.61 (45 %) at fixed inputs: **eq 28's `/D` is simply not in the exe** — demand spread 1.7 % where eq 28 needs 31 %; run 7 prints **−184.985 mg/L DO** with no warning; retires the phantom "amplitude" |
| [case28_farfield_do_closeout](case28_farfield_do_closeout/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 12 arms (275 / 572) | ✅ to 500 m | ✅ DO/BOD/IDOD 100 | 3 × 2 factorial × 2 rates: **eq 30's `DO_a` is the ambient at the *trapping depth*** — mirrored falling/rising profiles with equal depth-means differ by **+1.765 mg/L, identical in all three pairs** |
| [case29_subcritical_froude](case29_subcritical_froude/) | **sub-critical, F ≈ 0.003** | 0.005 cms | 25 × 2.00 m, 0.5 m ports | 3 arms, 243–247 finite of 5001 | ❌ NaN | — | the first discharges below the Froude threshold: **all three rise, cross depth zero, and go all-NaN for ~4 750 rows** — the missing surface clamp; the `.prj` doesn't describe them |
| [case30_limiting_spacing_bracket](case30_limiting_spacing_bracket/) | dense, sinks | 0.005 cms | **1 port**, 0.2/0.5 m | 4 arms, 575–739 | — | — | `gap_1` separates trap from crossing for the first time: **the limiting-spacing check is continuous, not gated on trapping** — banner one step after the crossing, bracket now (0.78, 1.014]; `gap_2` repeats case23 **byte for byte across sessions** |
| [case31_surface_stop_pair](case31_surface_stop_pair/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 2 arms, 275 / 572 | — | — (columns not selected) | one checkbox, two builds: **row 258's 40 % endpoint gap was the stop-at-surface box, not physics**; the two builds agree bit for bit, and **the exe runs 14 steps and +8.6 % dilution past surface contact** |
| [case32_aragonite_low_edge](case32_aragonite_low_edge/) | positively buoyant, surfaces | 8.00 MGD | 18 × 6.10 m | 5 arms × 572 | — | ✅ **TA/DIC/pH, `R_arg`** | five endmembers down one trajectory (bit-identical to a sixth chem-free run): **the aragonite cutoff is 25 psu**, bracketed to (24.895, 25.035] — and Ω_A at the switch ranges 4.0–9.0, so saturation state is not what sets it |
| [case33_limspc_salinity](case33_limspc_salinity/) | 2 dense arms + a buoyant control | 0.005 cms | **1 port**, 0.20 m | 3 arms, 576 rows | — | — | effluent salinity through the limiting-spacing rule: **the banner's lag moves 1 → 15 steps with +10 psu**, which pointed at Froude (later killed by case35); 25 psu never crosses and never fires |
| [case34_multiport_spacing](case34_multiport_spacing/) | dense, sinks, merges | 0.005 cms | 25 × 0.30–2.00 m | 6 arms | — | — | the multiport comparison the archive lacked: **merging fires on the crossing with lag exactly 0 in every arm** (`d/L` 1.002–1.011), so the 0–23 step lag belongs to the *single-port* limiting-spacing rule — different code paths; two geometrically impossible arms run anyway |
| [case35_port_diameter_sweep](case35_port_diameter_sweep/) | dense, sinks | 3e-3 – 5e-3 cms | **1 port**, 0.20–0.60 m | 7 arms | — | — | **the Froude story dies**: `gap_4` and `d0.50_q5.0` share F = 0.2196 exactly and lag 16 vs 142. Six of seven land the banner on the **first local maximum**, so the lag measures where the trajectory turns |
| [case36_port_depth_sweep](case36_port_depth_sweep/) | dense, sinks | 0.005 cms | **1 port**, 0.20 m | 6 arms | — | — | port depth fails the same way: **the lag is not one number but three regimes** — A on `max(trap, crossing)` (0–1), B mid-trajectory (6–24), C on the first local max (66–143); no single parameter decides |
| [case37_wide_port_depth_sweep](case37_wide_port_depth_sweep/) | dense, sinks | 0.005 cms | **1 port**, 0.50 m | 4 arms | — | — | depth swept alone at a fixed 0.5 m port: **the regimes are ordered A → B → C and the B/C boundary brackets to (2.0, 2.4] m** — the first parameter to move the regime cleanly; a fifth exact repeat lands here too |
| [case38_do_interval_seeding](case38_do_interval_seeding/) | sub-critical, NaN tail | 0.005 cms | 25 × 2.00 m, 0.5 m ports | 6 arms (intervals 1/3/5) | — | ✅ DO | output interval varied to separate "first printed row" from "step 1": **the DO accumulator seeds at step 1, `DO·D = DO_e − IDOD`, with no entrained credit** — ambient 8.5–8.7 mg/L recovered blind from three intervals |
| [case39_single_port_spacing](case39_single_port_spacing/) | dense sinks + buoyant null controls | 0.005 cms | **1** and 25, spacing 0 / 2 / 5 / **1000 m** | 7 arms, 576 and 5001 rows | — | — | **the entered spacing is completely inert on one port** — spacing 0, 5 and 1000 m give the same trace, banner included (13 cols × 576 rows, worst diff 0.0). The 3rd edition's 1000 m point-source recipe **does not work**, and costs 2.3–6× in dilution growth |
| [case40_deep_overlap_spacing](case40_deep_overlap_spacing/) | **strongly buoyant (2 psu)**, surfaces then NaN | 0.005 cms | 25 × 0.25–3.00 m | 7 arms, 233–272 finite | — | — | one geometry, angle moving alone: **the effective-spacing law hits all five brackets with nothing fitted** where the static `\|sin ψ\|` misses at 75° and 65°; reaches `d/L` 4.27. ⚠️ its "ours" numbers are the retired closure's |
| [case41_suppression_curve](case41_suppression_curve/) | near-neutral 35–45 psu, traps, merges | 0.005 cms | 25 × 0.25–5.00 m | 6 arms, 372–498 rows | — | — | deep overlap where the step controller lets go (only ~40 % of steps at the 2 % cap): **`d/L` to 15.08**, and the merged-diameter runaway measured — 2.3–6.0 % post-merge under what ships, 15–27 % under the retired default |
| [case42_matched_dilution](case42_matched_dilution/) | 35 psu, traps, merges | 0.0112598 cms | 25 × 0.75 / 5.00 m | 2 arms, 474 / 427 | — | — | onset dilution held fixed while spacing moves 1.5× by scaling the port as `(L/d₀)²` (predicted 55.1, got 56.10): **the merged suppression follows the dilution, not the spacing** — test69 tracks test63 to 1.1 %, not its same-spacing twin 28 % away |
| [case43_port_count](case43_port_count/) | 35 psu, merges | 2.0e-4 cms **per port** | **1 / 2 / 6 / 25** × 0.50 m | 6 arms, 407–508 | — | — | per-port flow held fixed so only the neighbour count moves (all three merge at step 204, onset D 57.0): **port count is a first-order variable, 0.165 of suppression spread**, and the confined-decrement brake reproduces its shape (−0.128/−0.037 vs −0.138/−0.039) |
| [case44_spacing_sweep](case44_spacing_sweep/) | 35 psu, merges | 0.005 cms | 25 × 0.30–1.60 m | 6 arms | — | — | **the replacement accuracy bar for case20**, against a true single-port control: the exe's suppression walks monotonically 0.540 → 0.744 and **our offset crosses zero near 0.62 m spacing**, mean bias only +0.014 against the retired default's +0.241 |
| [case45_bearing_sweep](case45_bearing_sweep/) | 35 psu | 0.0112598 cms | 25 × 5.00 m (+ a 10 m span-doubling arm) | 9 arms | ✅ printed widths 121.4–242.1 m | — | eight bearings 0–45° offset: **there is no angle threshold — the span factor is 0.986–1.000 throughout**, so row 275 is retracted; test91's span-doubling gives `A` = 0.9957 with the diameter cancelling. **It is the build, not the angle** |
| [case46_surface_stop_flag](case46_surface_stop_flag/) | positively buoyant; surfaces vs traps | 8.00 MGD (0.3505 cms) | 18 × 6.10 m | 2 arms, 275 / 476 | — | — | one geometry, one session, one checkbox: **`nearfield_flags[1]` *is* the stop-at-surface box, 1 = stop** — first 275 steps bit-identical, dilution 169.754 vs 217.021. Retracts row 187: the exe never flipped the flag, **our own experiment note told the operator to** |
| [case47_dose_parity](case47_dose_parity/) | negatively buoyant (case03 geometry) | 0.005 MGD | 25 × 2.00 m | 5 arms × 410 | — | ✅ **TA 2930–20 000 / DIC**, exe's own CO2SYS | the alkalinity dose axis Phase 9 was blocked on, port pH 8.37 → 11.988: **the CO2SYS gap does not run away at high pH** — it peaks at 0.025 near pH 10.5 and narrows above 11.5. The carbonate dialog's default TA 2930 discharges a fake "dose" run |
| [case48_similarity_profiles](case48_similarity_profiles/) | negatively buoyant, never merges | 0.005 MGD | 25 × 2.00 m | 4 traces × 410 | — | — | the similarity-profile selector enumerated: **parabolic 2.00000 (default), 3/2-power 3.88997, Gaussian 3.66998** — so the manual's 3/2 profile ships as a non-default option, and **the exe's "Gaussian" is `k ≈ 3.568`, not the literature's `exp(−2u²)`** (a 59 % centreline overstatement) |
| [case49_profile_blend](case49_profile_blend/) | 35 psu, merges at step 215 | 0.005 cms | 25 × 0.60 m | 2 arms × 453 | ✅ stops at 501.65 m | — | the non-default profiles on a merging plume: **the round → slab blend is one linear-in-`d/L` law for all three profiles**, worst row 0.0021 — `peak_to_mean`'s assumption is now a measurement (row 279); hydrodynamics bit-identical to case44's test79 |
| [case50_eddy_law_selector](case50_eddy_law_selector/) | negatively buoyant (case03 geometry) | 0.005 MGD | 25 × 2.00 m | 2 arms × 410 | ✅ **constant and linear eddy laws**, to 502.6 m | — (chemistry off) | the two non-default far-field laws, never before run: **far-field flags 2/3/4 are one-hot** (`1,1,0,0,…` constant; `1,0,1,0,…` linear), both reproduce our Brooks to 2×10⁻⁴ — and the linear width exposed **a manual typo the port had copied** (176.12 → 112.35). Rows 280, 280b |
| [case51_flag_decode](case51_flag_decode/) | positively buoyant, surfaces (upstream example, **legacy build**) | 8.00 MGD | 18 × 6.10 m | 9 arms (8 traces × 55 + one failed run) | ✅ base to 501.9 m, width 109.59 m | — (chemistry off) | one undecoded flag flipped per arm: **far-field flags 1 and 5 each gate the far field** (near field byte-identical, block absent), **flag 7 is exe-owned** (written 1, rewritten 0), nf 1/5/6 + ff 6 file-owned and inert on a surfacing run — and ⚠️⚠️ **near-field flag 3 = 1 makes the exe fail silently and truncate the project** (no `.dat`, loader crashes on the remains). Rows 281–282; round 2 named the controls (the filled `RECON_CHECKLIST.md` lives here) |
| [case52_bottom_stop_flag](case52_bottom_stop_flag/) | **dense, −45°, hits the seabed** 0.3 m below the port | 0.000219 cms | 25 × 2.00 m | 2 arms, 24 / 38 rows | ✅ 503 / 207 m | — | round 2's output arm: **near-field flag 1 is the stop-at-bottom box (1 = stop)** — bit-identical to contact at step 231, the cleared box sails 14 printed rows past it through `Plume traps` (row 283). ⭐ The pre-registered forecast hit: predicted ~21 s / dilution 93, exe printed 21.409 s / 97.200 |

✅ **Merging is covered** by case05, and the gaps this section used to list are closed
by the table above it: **bottom hit** by case10, **single port** by case11, and
**salinity over 35 psu** by case07 at 45 psu. **Shoreline hit** is still unmet, and
the shoreline feature is inert in any case (case08, case12). The output-column limitation this
section once listed was a GUI column-picker bug, not a build limit: a generated project that already
names the columns comes back with all of them (13 near-field columns, 21 with chemistry and DO).

## Folder convention

One folder per exe run, self-contained: every input file the run used, the `.dat`
it produced, and a `README.md` recording what was changed and what the output
revealed. Files keep their original exe-written names so the project still opens
in the exe unchanged.

Where an input file wasn't re-saved for a run, it's copied in from the previous
case only after checking it against the `.dat`'s echoed tables — noted per case
when that happened.

## What the set has taught us so far

Cross-case diffs have been more informative than any single run. Findings live in
each case's README; the load-bearing ones are promoted into
[PORTING_NOTES.md](../notes/PORTING_NOTES.md) and the validation ledger,
[LEDGER.md](../notes/LEDGER.md), where each is a numbered row re-derived on every build.

⚠️ **This table is the early record (cases 00–12, August 12–13) and several rows were later
corrected**; the corrections are marked in place. The ledger is the authority.

Decoded and confirmed on two or more cases:

| Relation | Status |
|---|---|
| `CL-Dil = max(1.0, FluxAvg-Dilution / 2)` | exact, 0 exceptions in 125 rows across case01+case02 — later 8 617 rows (row 198). ⚠️ **Scoped**: unmerged and under the exe's *default* profile; merged it walks to 1.5 (row 203) and the exe's other two profiles print 3.89 / 3.67 (case48) |
| TA and DIC are advected as **conservative scalars**; reported precipitation is *potential* only | case03, 41 rows, 0.12 % scatter |
| Chemistry does **not** feed back on hydrodynamics | case02 vs case03 near-field bit-identical |
| Chemistry columns are **appended automatically**, not selected from the `.prj` name list | case03 (5 names → 12 columns) |
| Input units are **µmol/kg** (TA, DIC, Ca); output header says `mmol/m3`; the *ambient* values are transported as entered, the *effluent* values are scaled by ρ_eff/1000 (next row) | case03 + user; case47 confirms the far field asymptotes to the entered ambient to four figures |
| pH scales are converted: entered free, reported total | case03 |
| The exe prefers **TA + DIC**; `DIC = 0` is a "derive me" sentinel that makes it fall back to TA + pH. A *blank* field is rejected outright. | case03 vs case04 — pH 11 ignored when DIC was valid |
| `R_cal = exp(logK)·(Ω_calc − 1)^N` — **exact to 5 sig figs**, and `exp()` not `10^()` | case03 + case04, 82 rows, pred/reported 0.9998-1.0002 |
| Effluent chem is converted µmol/kg → mmol/m³ by **effluent density**; ambient chem is **not converted** → endmembers mixed in inconsistent units, ambient ~2.4 % low | case04; factor brackets EOS-80 1.026952 within ±0.06 % |
| ~~TA/DIC are **integrated stepwise through the LCV loop**, not computed algebraically from dilution (~7 ppm/row drift)~~ ⛔ **Retracted**: mixing is algebraic in the dilution — one scalar endmember explains every row (row 39); the apparent drift was the `1/(D−1)` sensitivity of the inversion to a slightly-wrong endmember | case03, case04, case32 |
| **`.prj` unit flag map: 1 = primary unit, 2 = alternate** (feet for lengths, m³/s for flow) | case00's matched `.prj`+`.dat` pair: stored 2.0 / 20.7 / 207.0 echo as 0.61 / 6.31 / 63.09 m, all ×0.3048 |
| flag-to-column alignment: diffuser maps 1:1; effluent, mixing zone and ambient each carry **one leading flag** then map 1:1 | case00 (effluent flow is column 0, selector is flag index 1) |
| the **number of `.prj` plot flags is build-dependent** — 1 near-field flag in Dec 2025, 4 in 2026 | case00 `Macoma.prj` (147 lines) vs case01 (149) |
| Entered `Ca` is **not used for Ω** — Ω matches salinity-derived calcium | case03 (`Ca=100` µmol/kg vs seawater ~10 300) |
| The `.dat` header text differs between exe builds (`Avg-Dil` vs `Dilutn`, bare vs parenthesised units) — the reader must not key on exact strings | case00 vs all 2026 runs |
| ~~The `AmbientChem` pH column is optional — it can be left blank~~ ⚠️ It ran blank on 2026-08-12 (case03) and was **refused blank on 2026-08-25** (case47) — session-dependent; the generator now fills it (`experiments.fill_ambient_ph`) and the exe ignores the value (SSMC item 10) | case03, case47 |
| Chemistry state is **not persisted in the `.prj`** at all | case03: chemistry on, zero chemistry values in the file |
| `Net-Dil = FluxAvg-Dilution` (with zero background) | exact, case02 |
| `P-Con. = C_effluent / dilution` | exact, case01 |
| far-field start distance = `hypot(x_posn, y_posn)` at near-field end | case02 (2.896) and example (7.319 vs 7.320 printed) |
| wastefield width = `(n_ports − 1) × spacing × |cos(bearing − current)| + diameter` in the **current** build; the **legacy** build has no cosine | case02/case05 at 90° (exact either way); the example's 109.59 m is the legacy build, 96.29 m the current one (case13, rows 96, 263, 275) |
| plumes merge when `diameter ≥ effective spacing`; at 90° effective = nominal | case05 brackets 0.982-1.012 and case07 0.985-1.038; the 30° example brackets 0.895-0.938 |
| **aragonite is 0 over `25 ≤ S ≤ 35`** — a gap, not a floor (corrected 2026-08-19: case13 precipitates from S 3 to 24.6 and case32 brackets the low edge at 25.0) | case07 gives the upper edge: 12/105 rows above 35, exactly those non-zero, switch between S=35.302 and S=34.903 |
| **`R = exp(logK)(Ω−1)^N` returns NaN for Ω<1** — a fractional power of a negative | case09; poisons the whole run |
| the plume centre can rise **above the free surface** with no clamp | case09 (depth +0.041 m) |
| the solver step cap is **5000** | case09 ran to 5001 |
| the **shoreline vector is inert**, even with its enable checkbox ticked | case08 (45°, 45°+5 m byte-identical) and case12 (60°+5 m, checkbox on, plume travels past 5 m) |
| `R_cal = exp(-0.106)(Ω_c−1)^2.87` and `R_arg = exp(1.11)(Ω_a−1)^2.26` for `35<S<44` | exact to 5 sig figs; case03-06 |
| ~~**aragonite returns exactly 0 below S = 35** — the branch has no coverage there~~ ⛔ superseded by the band row above: every Macoma case sat inside 25–35, which is how a gap impersonated a floor | case06 (S 35.09-36.00, R_arg nonzero in 71/71) vs case05 (S 31.1-34.6, 0/83) |
| the entered **`Ca` is entirely inert** — no effect on Ω or the rates | case06 (`Ca=5000` vs seawater ~10500; Ω unchanged) |
| surfacing fires near `depth = radius` but the example lags it by 2 intervals | case06 brackets 1.035→0.966; example 0.837→0.775 |
| surfacing is **not always terminal** — governed by the max rise/fall switch | case06 (switch 3) continues 96 steps past it; example (switch 2) stops |
| merging measurably suppresses entrainment (Δdilution/5 steps drops 2.16 → 1.74 across the merge) | case05 |
| the **terminating step** is always printed; it is an extra **truncated** row only when it falls **off** the output interval, and a complete row when it lands on it | truncated: case05/06/07 (417, 356, 529); complete: case10/11 (345, 500) |
| boundary termination uses the **plume edge**, not the centreline: `depth − radius ≤ 0` at the surface, `depth + radius ≥ bottom` at the seabed, where bottom = port depth + port elevation | case06 (+0.024 → −0.025) and case10 (2.984 → 3.189 vs 3.0) |
| the single-port NaN failure was **exit velocity, not port count** — 39.5 m/s overshoots the surface; 0.39 m/s runs clean | case09 vs case11 |
| `width = (n−1)·spacing + diameter` **degenerates correctly at n = 1** | case11 (0 + 1.451 → 1.45) |
| far-field holds the plume at its **trapping depth** — chemistry asymptotes to the ambient profile there | case05 (TA → 2925.3 at 1.710 m) |
| `.prj` unit flag: `1 → MGD`, `2 → cms` | confirmed by header text on both |
| `.prj` overrides its CSVs when they disagree | case01 |

Corrected along the way: case01 suggested "unmerged ⇒ far-field skipped", and
case02 disproved it — the unmerged *warning* is independent of whether Brooks
runs. See [case02](case02_macoma_mgd/README.md).

## case18 — the Phase 5 isolation set (test21–test26)

Six old-build runs at output interval 1 with all output columns, none of which merge.
Zero ambient current makes eq 2's forced-entrainment term vanish identically, isolating
Taylor entrainment; a single port makes merging impossible. Established the Taylor
coefficient (α = 0.1, measured 0.0967–0.0991), the contraction coefficient as the vena
contracta (`b₀ = (d/2)√c`, `U₀ = Q/(ncA)`), and the two-decimal rounding trap in the
`.dat` diffuser echo. See [case18_zero_current_pair/README.md](case18_zero_current_pair/README.md).
