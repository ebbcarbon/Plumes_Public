# case29 — the first sub-critical discharges, and the exe cannot run them

Run 2026-08-18 to give the Froude design check (row 113) something real to stand on. Until these
three runs, **nothing in the archive exercised it**: the lowest discharge Froude number anywhere was
case22 at 2.01, against a threshold of 1.

These sit at **F ≈ 0.003**, three orders of magnitude below it. All three fail.

## ⚠️ The `.prj` does not describe these runs

`Macoma2.prj` was saved with a port diameter of **0.013 m**; the runs used **0.5 m**. The project
file was not re-saved after the diameter was changed, so it is the `.dat` **echo** that is
authoritative here, and the diameter is the one input the echo happens to carry losslessly.

⚠️ And the echo is lossless only by luck: it prints `Ttl-flo` as **0.01** where the true flow is
**0.005 m³/s**, which is row 141's two-decimal rounding caught live. A reader who took the flow from
the echo would be 2× out.

| field | test41 | test42 | test43 |
|---|---|---|---|
| port diameter | 0.5 m | 0.5 m | 0.5 m |
| ports / spacing | 25 | 25 | 25 |
| total flow | 0.005 m³/s | 0.005 | 0.005 |
| **effluent salinity** | **2 psu** | **0 psu** | **10 psu** |
| effluent temperature | 10 °C | 10 | 10 |
| port depth | 2.0 m | 2.0 | 2.0 |

Everything else is the Macoma baseline: ambient ~31 psu, 9–11 °C over 15 m.

## The regime

Widening the port to 0.5 m at an unchanged 0.005 m³/s across 25 ports drops the exit velocity to
**0.001019 m/s**, while a fresh effluent against a 31 psu ambient makes the buoyancy large. The
ratio is the point:

| run | effluent | `g'` | exit velocity | **Froude** |
|---|---|---|---|---|
| test41 | 2 psu | 0.213 m/s² | 0.001019 m/s | **0.00310** |
| test42 | 0 psu | 0.228 | 0.001019 | **0.00300** |
| test43 | 10 psu | 0.154 | 0.001019 | **0.00365** |

Our `DesignWarning` fires on all three.

## ⭐⭐ What the exe does: rises, breaches the surface, and returns NaN

Every run follows the same three-line story:

| run | finite rows | depth, first → last finite | surface crossed at | max dilution |
|---|---|---|---|---|
| test41 | 244 of 5001 | 1.968 → **−0.017 m** | row 243 | 118.2 |
| test42 | 243 of 5001 | 1.966 → **−0.007 m** | row 242 | 115.7 |
| test43 | 247 of 5001 | 1.977 → **−0.007 m** | row 246 | 126.1 |

The plume rises under buoyancy it has no momentum to resist, **crosses depth zero**, and from the
very next row every column is NaN — for the remaining ~4 750 rows, out to the 5001-step cap.

⚠️ **The mechanism is the missing surface clamp, not sub-criticality as such.** case09 breaks the
same way from the opposite extreme: a single port at 39.5 m/s, F ≈ 1045, drives the plume through
the surface on momentum instead. Both leave the water column and the exe has no clamp at the free
surface, so both produce a trace of NaN. What sub-criticality does is make the breach *inevitable* —
with buoyancy dominating and nothing to carry the plume sideways, there is nowhere else to go.

So these runs do not prove "F < 1 causes NaN". They establish something narrower and still worth
having: **in the regime the manual's §5.2.2 warns about, this exe returns nothing usable**, which is
the strongest justification the design check has.

## What this settles

- **Row 113 has evidence.** The check was implemented against the manual's threshold with no case
  to test it on. Now three archived cases sit below it and all three fail, so the warning is
  pointing at a real cliff rather than a stated one.
- **The warning must not become a refusal.** These traces are still readable for their first ~245
  rows, and the dilution reached (~118×) is not obviously wrong. Refusing to build the case would
  throw that away; the exe itself computes it, and a port of the exe has to be able to as well.

## Still open

- **A sub-critical run that does *not* surface**, e.g. a dense effluent so buoyancy drives it down
  onto the seabed rather than up. That would separate "sub-critical is unusable" from "leaving the
  water column is unusable", which these three cannot.
- ⚠️ **Re-save the `.prj` at run time.** These three are interpretable only because the port
  diameter survives the echo; a second changed field would have made them ambiguous.
