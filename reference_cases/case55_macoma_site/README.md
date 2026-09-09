# case55 — the Macoma site itself: the actual values, both ambients, run in the exe

Generated and run **2026-09-09** from [`studies/macoma_site_experiment.py`](../../studies/macoma_site_experiment.py)
(forecasts registered before the run — `EXPERIMENT_NOTE_macoma_acute.md`,
`EXPERIMENT_NOTE_macoma_chronic.md`). This is the one archived exe run of Ebb's diffuser **as it is**:
every earlier "Macoma" folder (now case00–case12 and case24, "the archived diffuser") was an earlier
entry with known slips. Here:

| | value | note |
|---|---|---|
| ports | 25 × 0.0127 m at **2 ft (0.6096 m)**, 45° up, square to the current, 2 m deep on a 15 m riser | the `.prj` carries the spacing and the mixing zones **in feet** with the unit flag set; the trace echoes `Spacing 2.0 (ft)` and the exe converted it (it merges when d reaches 0.61 m) |
| effluent | **5900 L/h** (98.3 L/min) of intake water, S 30.9 / T 11.2, **TA 6000 / DIC 2092** µmol/kg entered as the (TA, DIC) pair | the example's illustrative dose; the study sweeps the axis |
| ambient chemistry | **TA 2146 / DIC 2092, uniform** to the 17 m seabed | ⚠️ the exe's CSV table format carries three figures, so it ran at **2150 / 2090** (the far-field tail prints TA 2150.0, DIC 2090.0) |
| mixing zones | 20.7 ft / 207 ft (6.31 m / 63.09 m) | read from the far-field table |
| ambients | **acute** 0.02 m/s and **chronic** 0.05 m/s, near and far field alike | one arm each; the operator's baselines folder |
| constants | K1K2 option 10, KSO4 option 1; 4/3-law far field to 500 m / 10 000× | `check_farfield_session_state`: no drift on either arm |

| file | role |
|---|---|
| `macoma_acute.dat`, `macoma_chronic.dat` | the traces: 57 / 56 near-field rows (interval 5) + 102 far-field rows each, with the carbonate columns |
| `asrun_macoma_acute.prj`, `asrun_macoma_chronic.prj` | the as-run projects — **byte-identical to what the port wrote**: the exe changed nothing |
| `AmbientChem_macoma_*.csv` | the chemistry tables the runs loaded (the pH column is PyCO2SYS's, which the GUI demands and ignores) |
| `macoma_acute.yaml`, `macoma_chronic.yaml` | the port's own statement of each case; `plumes2 run` reproduces every forecast |

## ⭐ What the site run shows: parity to trapping, then the post-trapping shortfall at full size

At the exe's own instants (`Time`), both arms:

| | D ≈ 2 to the trap (exe steps 35–185, D 2–39) | before the merge banner | at the exe's end |
|---|---|---|---|
| flux-averaged dilution | **±0.34 %** acute, **±0.81 %** chronic | acute −2.0 % (step 245, t 66 s), chronic **−4.9 %** (step 245, t 51 s) | **acute −6.6 %** (157.6 vs 168.7 at 143.9 s), **chronic −5.4 %** (240.3 vs 254.1 at 144.6 s) |
| plume diameter | ±1 % | −1.0 % / −2.6 % | −5.8 % / −3.1 % |
| trajectory (`y`, depth) | ≤ 1 cm | ≤ 1 cm | **≤ 1.5 cm** (3.661 vs 3.675 m; −1.680 vs −1.692 m) |
| pH (total) | ≤ 0.011 | 0.008 | **0.007** (7.809 vs 7.816) |

(The first two printed rows, D 1.1–1.2, sit 1–2 % apart: the initial element, as on every trace.)

The near field is the archive's usual parity **until the plume traps** (`Plume traps` at acute step
150, t = 5.9 s; chronic step 175, t = 5.8 s). From there the port entrains less, and it is already
2.0 % (acute) and **4.9 %** (chronic) short **before** either `merging happened` banner lands (acute
step 255, t = 83 s, d = 0.635 m; chronic step 275, t = 120 s, d = 0.612 m — the `d ≥ spacing`
crossing with zero lag, row 191d again). Merging adds little on top: the arms end 6.6 % and 5.4 %
below the exe. So this is **not** the post-merge tilt (rows 266, 271, 276), whose 1–7 % band the
numbers happen to share at end `d/L` 1.47 / 1.06; it is the **post-trapping shortfall** PLAN §6
carries as the zero- and slow-current residual — test23's late 5 %, case53/54's −5.7 % (unmerged)
and −7.3 % (merged) at 0.02 m/s — now measured at the site's own 0.02 and 0.05 m/s. **Ledger row
286** measures it; the study's boundary dilutions carry it: the exe reads **170** at the acute boundary
(6.31 m) against the port's 159, and **399** (acute arm) / **340** (chronic arm) at the chronic
boundary against 360 / 306 — the far field inheriting the near-field endpoint plus the wider start
below. pH at the boundaries agrees to **0.004** either way (7.813 vs 7.809 acute; 7.775 vs 7.771
chronic arm), because the far field is 7.7–7.8 whatever the dilution: the receiving water sets it.

**Chemistry parity holds end to end.** Port pH 10.869 at the exe's first printed row (D 1.104)
against the port's 10.870; ambient-limit pH 7.739 at the far-field tail on both arms (the port's
ambient at 2150 / 2090 is 7.739). `OmegaA` 31.4 at the port, 1.14 at the near-field end, **1.00** at
the acute arm's chronic boundary — the receiving water is aragonite-undersaturated (0.956 in the
tail) and the dose carries the boundary to saturation, as the study says. The exe prints `NaN` in
the chemistry columns of the acute arm's final near-field row (step 284) — the one-step lag of the
scalar columns, row 258c, not a failure.

**Two things the exe printed that the port's far field does not start from.** The wastefield banner
is the row-96 law to the printed decimals: **15.53** and **15.28** m against `(n − 1)·L + d` = 15.526
and 15.277. The far-field table's *first* `Width`, though, is **16.836 / 16.587** — 1.31 m above the
banner on both arms. That is the current build's **virtual-origin** start of Brooks (rows 116, 256):
across the archive every current-build chemistry-on trace opens 0.5–2.4 m above its banner
(case03 1.87, case05 1.63, case13 0.95, case27 2.41) while chemistry-off and legacy traces agree to
0.02. The port scores far fields from the printed first row (row 115's convention) for exactly this
reason; it means the port's own far field, started at the law's width, dilutes slightly slower than
the exe's from the transition on.

## The prediction scorecard — 12 of 14, the two misses being the same residual

| registered (port) | acute | chronic | |
|---|---|---|---|
| termination `oscillation limit` at 142 / 143 s | third `Local maximum rise or fall`, 143.9 s | 144.6 s | ✅ same criterion (the 3-count), same time |
| near-field end dilution 158 / 240 | **168.7** | **254.1** | ❌ −6.3 % / −5.4 %: the post-trapping shortfall, recorded as the miss it is |
| end distance 3.66 / 7.64 m | 3.675 | 7.729 | ✅ (1.2 %) |
| trapping depth 1.68 / 1.78 m | 1.692 | 1.783 | ✅ |
| end diameter 0.84 / 0.63 m | 0.896 | 0.647 | ⚠️ −6 % / −3 %: the same residual in the geometry |
| wastefield width 15.5 / 15.3 m | 15.53 | 15.28 | ✅ exact |
| jets merge before the end | banner at step 255 | step 275 | ✅ |
| port pH 10.990 | 10.869 at D 1.104 (port 10.870 there) | same | ✅ |
| end pH 7.809 / 7.783 | 7.816 | 7.790 | ✅ (0.007) |
| acute boundary 159 / 7.809; 220 / 7.787 | 170 / 7.813 | 231 (near field) / 7.795 | pH ✅; dilution carries the residual |
| chronic boundary 360 / 7.765; 306 / 7.771 | 399 / 7.759 | 340 / 7.775 | pH ✅; dilution −10 % (shortfall + virtual origin) |
| far field at 504 / 508 m: 3970 / 1887, width 539 / 166 m | 4258, 541.5 m | 2016, 167.5 m | width ✅ (0.5 %); dilution −7 % |

The Ω_brucite = 1 crossing (dilution 2.54, 3.5 cm) cannot be scored: the exe does not print it.

## What it changes

- **The study's near-field statements stand**: the Ω = 1 windows sit at dilutions 1.3–23, centimetres
  from the port, where the two agree to 0.4 %. The **boundary dilutions** in
  `studies/ebb_dose_study/README.md` (159 / 306) are the port's and read 6–10 % low against this run;
  the boundary **pH** values are good to 0.01.
- **The post-trapping shortfall is now measured at the site's own geometry and currents** rather
  than inferred from test23 and case53/54, and it is the residual that matters for the boundaries:
  it starts after the trap and before the merge, so `ConfinedDecrements` is not where the missing
  entrainment is. It stays one of the project's two known residuals (PLAN §6), now with a number
  attached to the case that matters.
- The exe ran a **feet-entered** spacing and mixing zones from a port-written `.prj` for the first
  time, converted them correctly, and wrote the project back unchanged.

## Names (2026-09-09)

This is the first folder allowed the word: every earlier `macoma` folder was renamed the same day
because its exe runs were not the site's values (see the top-level README). The exe wrote each trace
as `ModelResults_TxtOutputs.dat`; they are `macoma_acute.dat` / `macoma_chronic.dat` here, byte-identical.
