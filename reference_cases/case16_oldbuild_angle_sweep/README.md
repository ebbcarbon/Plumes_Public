# case16 — the old-build horizontal-angle sweep (test16–test20)

⚠️ **Written 2026-08-21, long after the runs.** This directory held five traces and no write-up for
two days, which the repository README promises against; what follows is reconstructed from the
traces and from the ledger rows that cite them, and it says so wherever the reconstruction is
uncertain.

**Old build**, 25 ports at a 2.0 m spacing, 45° vertical, output interval 1. Only the **horizontal
discharge angle** changes.

| run | H-angle | rows | wastefield width |
|---|---|---|---|
| test16 | **90°** | 84 | — |
| test17 | **45°** | 83 | — |
| test18 | **135°** | 83 | — |
| test19 | **175°** | 494 | — |
| test20 | **70°** | 409 | **50.12 m** |

## What it is for

⭐ **The 45°/135° pair is the reason this case exists.** Row 205 uses it to confirm the merging
effective-spacing law's `|sin ψ|` *independently of the law it was derived from*: both angles merge
at `d/L` = 0.8430, identical to four decimals, where an `|cos ψ|` reading would put them far apart.
That is a mirror-symmetry test — 45° and 135° are reflections about the diffuser normal — and it
costs nothing to run but pins the functional form.

⚠️ **test19 at 175° is the near-parallel case** and is why the row count jumps to 494: a plume
discharged almost along the diffuser axis takes far longer to reach a stopping condition. It is the
archive's closest approach to the 20° floor of row `MERGING_FLOOR_DEGREES`, from the other side.

⚠️ **Only test20 prints a wastefield width**, which is why the width rows cite it and not its
siblings; it is also the trace row 121 uses for the `( )`-unit column-shift check, where an H-angle
of 70 must parse as 70 rather than being displaced by the unit marker.

## ⚠️ Old build, and that is load-bearing

These are **pre-2026** traces, so they are excluded from row 96's width law by name — the cosine
correction was added between releases and these files print an essentially uncorrected width. Row 98
measures that difference rather than hiding it. `ExeBuild.LEGACY` is the switch.

⚠️ **No `.prj` survives for any of the five.** Their geometry above is read from the `.dat` diffuser
echo, which rounds to two decimals (row 141) — so the spacing and angles are exact only because
they are round numbers. This is the traceability gap PLAN §7b is about.
