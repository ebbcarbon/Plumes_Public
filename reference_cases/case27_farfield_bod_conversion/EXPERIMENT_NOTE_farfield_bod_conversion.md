# farfield_bod_conversion

**Question.** case26 settled the far-field structure — the `1/FF`, the typed rate, and exactly where
the ambient-BOD defect sits — and left one thing open. The **effluent** demand comes out 1.889x the
typed cBOD5 at 5.0 /day and 2.576x at 1.0 /day. It is a real amplitude (flat along the whole trace),
it is not nBOD, not θ, not reaeration, not an offset, and not a dilution error. It is some function
of the typed rate, and **two points cannot identify a function.** This experiment adds a third and a
fourth rate, and the linearity check in cBOD5 that has never been run.

Same project, same geometry, same ambient as case25 and case26, so everything stays comparable.

## Run it

1. Open `farfield_bod_conversion.prj` in the exe. **Do not open a hand-maintained project.**
2. Set these in the GUI, which the `.prj` cannot carry:

   - output interval 1
   - all output columns, including DO
   - No. of maximum plume rise or fall = 3
   - stop plume at bottom hit: ticked
   - stop plume at surface hit: unticked
   - Dissolved Oxygen Calculations: TICKED

3. Load `AmbientDO_zero.csv` (DO 8.0 everywhere, both ambient BODs zero) for **all three** runs.
4. Run, and save the `.dat` **and** the `.prj` as it stood at run time.

## The three runs

Effluent DO 2.0 and IDOD 0 throughout. ⚠️ **Please set nBOD5 = 30 mg/L at 0.23 /day** — not because
it matters (it can take 0.0067 mg/L over this far field) but because it is what case26 actually ran
with, and holding it fixed keeps the comparison exact. Record it either way.

| run | cBOD5 | cBOD decay | what it is for |
|---|---|---|---|
| **H1** | 2000 mg/L | **0.2 /day** | the low-rate arm — where the candidate forms separate most |
| **H2** | **500 mg/L** | **20 /day** | the high-rate arm. cBOD5 is cut to 500 so the DO stays well clear of zero at this rate |
| **H3** | **1000 mg/L** | 5.0 /day | linearity in cBOD5, at a rate already measured. Every run so far used 2000, so this has never been tested |

## Predicted, before the runs

The two forms that reproduce case26's two points *exactly*, and therefore cannot be told apart by it:

    form P:  g(k) = 2.576 k^-0.1927
    form H:  g(k) = 1.7172 + 0.8588/k

| run | DO at 102 m | DO at 500 m |
|---|---|---|
| **H1** | 7.917 as written / **7.791** form P / **7.666** form H | 7.866 / **7.569** / **7.273** |
| **H2** | 6.956 as written / **6.506** form P / **6.188** form H | 6.809 / **6.284** / **5.915** |
| **H3** | 7.373 as written / **6.845** if linear in cBOD5 | 6.845 / **5.832** if linear |

"as written" is eqs 24–29 with no multiplier at all (`g = 1`) — kept in the table because if a run
lands there, the multiplier is not a function of the rate but something about the case26 runs.

The two forms are **0.30–0.37 mg/L** apart at 500 m and the exe prints DO to 0.001, so this
separates them by a factor of several hundred in resolution. A result outside *both* is the most
interesting outcome available: it would mean `g` is not a function of the rate alone.

⚠️ **H3 is the one that can invalidate the framing.** If halving cBOD5 does not halve the sag, then
"multiplier" is the wrong word for what is happening and the whole two-point analysis is built on
an assumption nobody has checked.

## Notes

- ⚠️ THREE RUNS FROM THIS ONE PROJECT. Only the DO tab changes between them.
- The `.dat` diffuser echo rounds to two decimals, so it will print `P-dia 0.08` for 0.076 and
  `Ttl-flo 0.35` for 0.350501. Both lose information; the `.prj` is the record.
- If the GUI resets the project on exit, save the `.prj` before closing it. A stale project file is
  worse than none: test34/test35 came back describing a different run.
