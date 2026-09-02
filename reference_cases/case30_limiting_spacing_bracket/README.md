# case30 — the limiting-spacing rule is continuous, and it is not only about depth

Run 2026-08-18 to split ledger row 191's open bracket. It splits it, **and it overturns the
other half of row 191**: the check is *not* gated on trapping. case22/23 only looked that way
because in both of those runs the two coincided.

**Old build**, output interval 1, single port at 0.005 m³/s discharged **downward at −45°**,
effluent into the Macoma profile at 0.02 m/s. Everything is case23's `limspc_gap` except the
fields marked below.

| run | port diameter | port depth | effluent | rows | first trap | `merging happened` |
|---|---|---|---|---|---|---|
| `gap_1` | 0.2 m | **2.4 m** | 35 psu | 576 | 171 | **192** |
| `gap_2` | 0.2 m | 2.0 m | 35 psu | 575 | 176 | 176 |
| `gap_3` | **0.5 m** | 2.0 m | **45 psu** | 739 | 222 | **248** |
| `gap_4` | **0.5 m** | 2.0 m | 35 psu | 648 | 208 | **227** |

## ⚠️ The `.prj` describes `gap_1` only

`gap_1.prj` is the project as it stood after the last save, which carries gap_1's 2.4 m port
depth. It is **wrong for the other three**. They are still unambiguous because every field
that varies — `P-dia`, `P-depth`, `Eff-sal` — survives the diffuser echo's two decimals
losslessly, so the `.dat` is authoritative here. ⚠️ `Ttl-flo` does not: it echoes `0.01`
against a true 0.005 m³/s, the same trap case29 records.

## ⭐⭐ gap_2 reproduces `limspc_gap` **byte for byte**

Five days apart, a fresh GUI session, and the two files are identical at all 115 366 bytes.
That is the first same-input repeat run in the archive, and it establishes something every
other measurement here has quietly assumed: **the exe is deterministic across sessions**, so a
difference between two runs is a difference between their inputs. Without it, every one-run
finding rested on an untested premise.

## ⭐⭐ The check is continuous, not gated on trapping — gap_1 settles it

Row 191 concluded "the check is gated on trapping", because in `limspc_shallow` and
`limspc_gap` the banner landed exactly on the first trapping step. `gap_1` separates them for
the first time:

| | step | diameter | diameter / port depth |
|---|---|---|---|
| first trapping | 171 | 1.873 | **0.7804** |
| diameter crosses the port depth | 191 | 2.410 | 1.0042 |
| `merging happened` | **192** | 2.431 | 1.0129 |

The banner is **21 steps after** the trapping and **one step after** the crossing. So the rule
fires on the crossing, and case22/23's coincidence was exactly that — a coincidence. The
one-step delay is the same "the merge takes effect a step late" that row 206 records.

## The bracket closes from below

`gap_1` traps at a ratio of **0.7804** without firing, so the threshold is above 0.78, not the
0.539 the archive could previously only say. With `gap_2` firing as the ratio passes 1.0140,
the bracket is now **(0.78, 1.014]** — and given the crossing evidence above, the rule is
`diameter > port depth` with nothing else to fit.

## ⚠️⚠️ But that rule is incomplete, and gap_3/gap_4 are why

Widen the port from 0.2 m to 0.5 m at unchanged flow — a 6.25× drop in exit velocity — and the
banner stops arriving on the crossing:

| run | port diameter | port depth | crosses port depth | banner | lag |
|---|---|---|---|---|---|
| gap_2 | 0.2 m | 2.0 m | step 176 | 176 | **0** |
| gap_1 | 0.2 m | 2.4 m | step 191 | 192 | **1 step** |
| gap_4 | **0.5 m** | 2.0 m | step 211 | 227 | **16 steps** (9.17 s) |
| gap_3 | **0.5 m** | 2.0 m | step 225 | 248 | **23 steps** (15.26 s) |
| `limspc_shallow` | 0.2 m | **1.0 m** | step 126 | 180 | **54 steps** (45.61 s) |

At the banner the ratio reads 1.2175 (gap_4) and 1.4720 (gap_3) rather than 1.01. So a second
condition exists that the narrow-port runs never expose, and it is **not** pure geometry:
gap_3 and gap_4 differ only in effluent salinity, 45 psu against 35, and they lag differently.

⭐ **And this reframes case22's oddity.** Row 191 read `limspc_shallow`'s 54-step gap as proof
the check *cannot* be continuous. It is the same lag gap_3 and gap_4 show, just larger — and in
that run it happened to land on the trapping step, which is what made "gated on trapping" look
like the answer. One run's coincidence became a mechanism; gap_1 is the run that separates them.

Checked and rejected as the missing quantity, each constant across the set if it were the
trigger: the plume's depth below the surface, its height above the seabed, the distance
fallen, the path length, elapsed time, dilution, the diameter excess `d − d₀`, and
`d > port depth + port diameter`. None is.

⚠️ **Do not read the 1.2175 and 1.4720 as a revised threshold.** They are where the diameter
happened to be when *something else* fired, and fitting a constant to two points that disagree
by 21 % would bury the real mechanism.

## What would isolate it

The two variables moved together here — port diameter went 0.2 → 0.5 while exit velocity went
0.16 → 0.025 m/s. A sweep at fixed port depth 2.0 m and 35 psu, port diameter **0.3** and
**0.4**, brackets the onset with gap_2 and gap_4 as the endpoints already in hand. If the lag
grows smoothly with port diameter it is a resolution or step-size effect; if it switches on
somewhere it is a regime the exe tests for.

## ⭐⭐⭐ 2026-08-20: the sweep arrived, and the lag **switches** — row 191b is answered

The section above asked for exactly this and stated the test in advance: *"If the lag grows
smoothly with port diameter it is a resolution or step-size effect; if it switches on somewhere
it is a regime the exe tests for."* Five more runs came back, all one port at 0.005 m³/s
discharged downward at −45° into the same profile at output interval 1, with **port diameter the
only thing moving within an arm** — which is what the original gap_3/gap_4 pair could not offer,
since diameter and exit velocity moved together there.

⚠️ **The exe's own echo is the authority for what each file is**, because the default output
names do not describe the runs — see the naming warning below.

| trace | P-dia | depth | first trap | crosses depth | banner | lag | `d`/depth at banner |
|---|---|---|---|---|---|---|---|
| `gap_2.dat` | 0.20 m | 2.0 m | 176 | 176 | 176 | **0** | 1.0140 |
| `d0.30_dep2.0.dat` | 0.30 m | 2.0 m | 184 | 186 | 204 | **18** | 1.2400 |
| `d0.40_dep2.0.dat` | 0.40 m | 2.0 m | 202 | 205 | 222 | **17** | 1.2275 |
| `gap_4.dat` | 0.50 m | 2.0 m | 208 | 211 | 227 | **16** | 1.2175 |
| `gap_1.dat` | 0.20 m | 2.4 m | 171 | 191 | 192 | **1** | 1.0129 |
| `d0.30_dep2.4.dat` | 0.30 m | 2.4 m | 179 | 202 | **340** | **138** | 1.4425 |
| `d0.40_dep2.4.dat` | 0.40 m | 2.4 m | 197 | 221 | **362** | **141** | 1.4583 |

**It switches.** At 2.0 m the lag goes 0 → 18 between a 0.2 m and a 0.3 m port, and is then
**flat at 18 / 17 / 16** while the diameter goes 0.3 → 0.5 m and the exit velocity falls 2.8×
(0.071 → 0.026 m/s). A resolution or step-size effect would keep growing; this plateaus
immediately. So by the criterion set above it is **a regime the exe tests for**, and the port
diameter only decides *which* regime — it does not control the lag continuously.

### ⭐⭐ And the 2.4 m arm's 138 steps is not a lag at all

`d0.30_dep2.4.dat` prints `Local maximum rise or fall@340` and `merging happened@340`; 
`d0.40_dep2.4.dat` prints both at 362. **The banner lands exactly on the first local
maximum.** That is regime C of the three-regime structure the ledger already carried — "fires
exactly on the first local maximum (66–143)" — and 138 and 141 sit inside that range. So in
regime C the timing is *fully explained*: the rule waits for the first turning point.

The 2.0 m arm's banners (204 / 222 / 227) sit nowhere near their first local maxima (342 / 364 /
372), so those are regime B, "fires mid-trajectory with nothing marking it (6–24)" — and 18 / 17 /
16 are inside that range too.

### The regime map, now complete on two axes

| port depth | 0.20 m | 0.30 m | 0.40 m | 0.50 m |
|---|---|---|---|---|
| **2.0 m** | A (0) | B (18) | B (17) | B (16) |
| **2.4 m** | A (1) | C (138) | C (141) | C (142, case36) |

Two independent switches, each bracketed to one interval:

* **A → not-A is set by port diameter**, between **0.2 and 0.3 m**, at *both* depths.
* **B versus C is set by port depth**, between **2.0 and 2.4 m**, now at 0.3 and 0.4 m ports as
  well as case37's 0.5 m — which is the boundary case37 had already bracketed to (2.0, 2.4] m.

⭐ **What is left open is much smaller than before.** Regime A fires on `max(trap, crossing)` and
regime C fires on the first local maximum, so both timings are accounted for. Only **regime B's
~17-step offset** is unexplained, on a single depth. Row 191b previously read as "the banner lags
by 0 to 54 steps for no reason anyone can find"; it now reads as one unexplained offset in one
regime.

⚠️ **`d`/depth at the banner is not a threshold.** It reads 1.22 at 2.0 m and 1.44 at 2.4 m, and
`gap_3.dat` — 45 psu at 2.0 m — gives 1.47, matching the *deeper* arm rather than its own. So two
different conditions land on the same ratio and the same geometry lands on two, which is what a
consequence looks like rather than a cause. Do not fit a constant to it; the same warning the
section above gives about 1.2175 and 1.4720 applies.

⭐ **A third determinism check came free.** `gap_4_repeat.dat` is **byte-identical** to
`gap_4.dat` (SHA-256 prefix `54e0c2f3`, 125 670 bytes), a same-input repeat in a fresh session.
That is the second such pair in this case and it reinforces row 191c.

### ✅ Renamed on arrival, because the default names were a trap

The five traces arrived carrying the exe's default output name, `ModelResults_gap_N`, where `N` is
a GUI counter rather than the run. The collisions were real: `ModelResults_gap_3` was 0.30 m at
2.0 m/35 psu while the archived `gap_3` is 0.50 m at 2.0 m/**45 psu** — adjacent names, different
runs. Renamed to carry the two variables that move, matching the convention case35-37 use:

| now | was | what it is |
|---|---|---|
| `d0.30_dep2.0.dat` | `ModelResults_gap_3` | 0.30 m port, 2.0 m depth, 35 psu |
| `d0.40_dep2.0.dat` | `ModelResults_gap_4` | 0.40 m port, 2.0 m depth, 35 psu |
| `d0.30_dep2.4.dat` | `ModelResults_gap_1` | 0.30 m port, 2.4 m depth, 35 psu |
| `d0.40_dep2.4.dat` | `ModelResults_gap_2` | 0.40 m port, 2.4 m depth, 35 psu |
| `gap_4_repeat.dat` | `ModelResults_gap_5` | byte-identical repeat of `gap_4`, kept as evidence |

⚠️ Nothing was lost to the renaming: every field that distinguishes these runs — `P-dia`,
`P-depth`, `Eff-sal` — survives the diffuser echo's two decimals, so each trace remains
self-describing and the echo is the authority if a name is ever doubted.

✅ **`gap_1.prj` has been restored** to the 0.2 m port it describes. It had been edited in place to
set these runs up, which briefly made the warning at the top of this file false.

## ⭐⭐⭐ 2026-08-20 (later): the A → B switch is bracketed to **(0.22, 0.25] m**

Two more runs at 2.0 m depth and 35 psu, changing only the port diameter, close the interval the
sweep above left open. The registered predictions were written into
`reference_cases/pending/limspc_switch_d0.22` before either was run.

| P-dia | exit velocity | trap | crosses depth | banner | lag | `d`/depth | `dt` at banner | regime |
|---|---|---|---|---|---|---|---|---|
| 0.20 m | 0.1592 m/s | 176 | 176 | 176 | **0** | 1.0140 | **1.1240 s** | A |
| **0.22 m** | 0.1315 m/s | 175 | 175 | 175 | **0** | 1.0040 | **1.1060 s** | **A** |
| **0.25 m** | 0.1019 m/s | 174 | 175 | 193 | **18** | 1.2510 | **0.4230 s** | **B** |
| **0.28 m** | 0.0812 m/s | 179 | 181 | 198 | **17** | 1.2350 | **0.4310 s** | **B** |
| 0.30 m | 0.0707 m/s | 184 | 186 | 204 | 18 | 1.2400 | 0.4220 s | B |
| 0.40 m | 0.0398 m/s | 202 | 205 | 222 | 17 | 1.2275 | 0.4240 s | B |
| 0.50 m | 0.0255 m/s | 208 | 211 | 227 | 16 | 1.2175 | 0.4300 s | B |

### ⭐⭐ `dt` at the banner is **bimodal**, and that was predicted before the runs

The note registered "dt at the banner: 0.42 ± 0.03 s if regime B", on the grounds that it was the
tightest quantity across the four archived regime-B runs. Measured at 0.25 m: **0.4230 s**, and at 0.28 m: **0.4310 s** -- both inside the band. And the
regime-A runs sit at **1.1060 and 1.1240 s** — a factor of 2.6 away, with **nothing in between**
across six runs spanning a 2.5× range of port diameter.

Two tight clusters and no intermediate values is a switch in the **step controller**, not a
continuum — and the 4th edition (§1.3) says UM3's controller is "also sensitive to the amount of
trajectory curvature" as well as to entrained mass, which is the first mechanism proposed for this
that is not already refuted.

⚠️ **Correlation, not yet causation.** In regime A the banner coincides with the trapping step; in
regime B it lands 16–18 steps after it. So `dt` may differ because the banner sits at a different
point of the trajectory rather than because `dt` decides anything. What the clustering does
establish is that the two regimes are separated by something discrete.

⚠️ **The other two predictions**: the lag was predicted at 16–19 steps for regime B and measured
**18** ✅; `d`/depth was predicted at 1.22 ± 0.03, i.e. ≤ 1.25, and measured **1.2510** — outside
by 0.001, recorded as a near-miss at the boundary rather than rounded in, the same treatment row
182's 0.0009 gets.

⚠️ **Port diameter and exit velocity cannot be separated here**, since the flow is fixed: the switch
sits between 0.1315 and 0.1019 m/s just as much as between 0.22 and 0.25 m. Any Froude-like group
moves monotonically with both.

### ⭐ The 0.22 and 0.25 traces were lost, re-run, and reproduced **exactly**

Both were measured and then destroyed during filing on 2026-08-20 — an `rm -rf` that ran after a
failed `mv`, on untracked files, so git could not recover them. They were re-run the same day, and
every measured quantity came back identical:

| | trap | crosses | banner | lag | `d`/depth | `dt` at banner |
|---|---|---|---|---|---|---|
| 0.22 m, before / after | 175 / **175** | 175 / **175** | 175 / **175** | 0 / **0** | 1.0040 / **1.0040** | 1.1060 / **1.1060** |
| 0.25 m, before / after | 174 / **174** | 175 / **175** | 193 / **193** | 18 / **18** | 1.2510 / **1.2510** | 0.4230 / **0.4230** |

⭐ That is a **fourth determinism check** on this exe, and the strongest kind: a fresh GUI session,
a regenerated project file, and every derived quantity landing on the same value. Row 191c's premise
holds again.

✅ So the bracket **(0.22, 0.25]** rests on archived traces, as it should have from the start. Both
runs carry their GUI-saved `.prj`, unlike `gap_1.prj` which describes only its own run.
