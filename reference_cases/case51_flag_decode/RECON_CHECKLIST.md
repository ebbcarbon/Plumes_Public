# flagdecode2_recon -- a checklist, not a run

**DO NOT RUN ANY PROJECT IN THIS FOLDER.** Opening a project writes nothing; running rewrites
the `.prj` and, for `recon_nf3.prj`, reproduces the silent failure of ledger row 282. Loading
is safe -- round 1's flipped `nf3` loaded without error; only the *run* failed, and only the
*truncated* file it left behind crashes the loader.

Every file here is case51's as-run base project with exactly one flag flipped -- the same
flips as round 1, freshly cut. The question each answers: **which GUI control shows the flip?**

1. Open `recon_base.prj`. Write down the state of every control on the model-settings and
   far-field dialogs: the three stop boxes (bottom checked, surface checked, shoreline un-checked), the rise/fall count (3), the eddy-diffusivity 
   selector(4/3), and any checkbox or dropdown not in that list.
2. Open each `recon_*.prj` in turn and fill the table: the ONE control that differs from base,
   and its state. "Nothing visible" is also an answer (then the flag is not a dialog control).
3. Close without running. Send this file back filled in.

| project | flipped flag (1-indexed) | control that differs from base | its state |
|---|---|---|---|
| `recon_nf1.prj` | near-field 1 (1 → 0) | | | (bottom hit unchecked)
| `recon_nf3.prj` | near-field 3 (0 → 1) ⚠️ do not run | | | (shoreline hit checked)
| `recon_nf5.prj` | near-field 5 (1 → 0) | | |  (same)
| `recon_nf6.prj` | near-field 6 (1 → 0) | | | (same)
| `recon_ff1.prj` | far-field 1 (1 → 0) | | | (same)
| `recon_ff5.prj` | far-field 5 (1 → 0) | | | (same)
| `recon_ff6.prj` | far-field 6 (1 → 0) | | | (same)
| `recon_ff7.prj` | far-field 7 (0 → 1) | | | (same)

Context: rows 281 (ff 1 and 5 gate the far field), 281b (ff 7 is exe-owned), 281c (nf 1/5/6
and ff 6 file-owned, inert on a surfacing run), 282 (nf 3 = 1 is fatal) -- all in
`reference_cases/case51_flag_decode/`.
