# Upstream snapshot — do not edit

Everything in this directory is a **verbatim copy** of
[ssmc-uw/PLUMES2.0](https://github.com/ssmc-uw/PLUMES2.0) @ `main`, vendored in
commit `e53acfc` (2026-08-12).

| Item | What it is |
|---|---|
| `plumes2.0v1.exe`, `.exe.manifest` | The compiled Windows GUI application (Intel Fortran 90 + Winteracter). No source is published. |
| `Docs/PLUMES2.0v1_SSMC_User Manual.pdf` | Primary specification, 64 pp, includes the DO and carbonate chapters. |
| `Docs/EPA_SSMC-PLUMES2.0_User Manual_reformat_v4_B-24.pdf` | EPA edition, 54 pp, predates the DO/carbonate work. |
| `Example_project/` | The shipped example project and its output — validation ledger rows 1-8. |
| `icons/`, `images/` | GUI resources. |
| `README.md`, `license.md`, `disclaimer_notice.md` | Upstream text, retained for attribution. |

## Rules

1. **Never modify these files.** They are the reference against which the port is
   validated; editing one would silently invalidate every test that cites it.
2. `.prj`, `.dat` and `.csv` files here are marked `-text` in `.gitattributes`, so
   git preserves their exact bytes (CRLF included). The `.dat` writer has to
   reproduce them byte-for-byte, which only works if they are not normalised.
3. New exe runs go in `reference_cases/`, not here.

Upstream is BSD-2-Clause (Battelle Memorial Institute, 2024) — re-implementation
and redistribution are permitted provided the copyright notice and disclaimer are
kept. See `license.md` and `disclaimer_notice.md`.
