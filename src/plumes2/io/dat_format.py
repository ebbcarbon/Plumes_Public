"""Numeric formatting for the `.dat` output file -- Phase 6 track A.

The `.dat` is a Fortran fixed-format listing, and its layout turns out to be far simpler than
the `.prj`'s: **every numeric field is right-justified in ten columns**, with no exceptions.
That is measured, not assumed -- reformatting all **15 408** numeric lines across the 42
archived traces from their own tokens reproduces every one byte for byte.

What is *not* uniform is how many decimals a value carries, and that is what turns a float
back into a token. It depends on the **table**, not just the column name:

    Ambient Table        3, except `Disprsn` at 5
    Diffuser Table       2
    Simulation Results   3, with `Step` an integer
    far field            3

`P-dia` is the trap: it appears in the diffuser echo at two decimals *and* in the step table
at three. Keying a format map on the column name alone silently rounds one of them.

⚠️ **This is the lossy echo, deliberately.** Two decimals is why the diffuser's `P-dia` of
`0.01` is really 0.0127 and `Ttl-flo` of `0.01` is really 0.005 -- the trap that produced an
apparent factor-of-two error in `alpha` and hid the contraction relation. Reproducing it is
the whole point of track A, and it is exactly why track B writes full precision to CSV
instead. See PLAN.md §7b.

⚠️ **`NaN` is data.** `case09` drives itself numerically bad and prints literal `NaN` for
every value, including its wastefield width and whole far-field table. Those rows record the
failure and must survive a round trip.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "DEFAULT_DECIMALS",
    "FIELD_WIDTH",
    "decimals_for",
    "format_row",
    "format_value",
]

#: Every numeric field, in every table, in every archived file.
FIELD_WIDTH = 10

#: Decimals per table, before the per-column exceptions below.
DEFAULT_DECIMALS: dict[str, int] = {
    "Ambient": 3,
    "Diffuser": 2,
    "Simulation Results": 3,
    "farfield": 3,
}

#: `(table, column)` exceptions. Only one exists, and it is easy to miss.
_EXCEPTIONS: dict[tuple[str, str], int] = {
    ("Ambient", "Disprsn"): 5,
}

#: Columns written as integers rather than fixed-point.
_INTEGER_COLUMNS = frozenset({"Step"})


def decimals_for(table: str, column: str) -> int:
    """Decimals for one column of one table; `-1` means write it as an integer.

    `table` is the heading as the file spells it -- `'Ambient'`, `'Diffuser'`,
    `'Simulation Results'` -- or `'farfield'` for the unheaded far-field block.
    """
    if column in _INTEGER_COLUMNS:
        return -1
    if (table, column) in _EXCEPTIONS:
        return _EXCEPTIONS[table, column]
    try:
        return DEFAULT_DECIMALS[table]
    except KeyError:
        raise ValueError(f"unknown .dat table {table!r}") from None


def format_value(value: float, decimals: int) -> str:
    """One field, right-justified in `FIELD_WIDTH` columns.

    `decimals = -1` writes an integer.

    ⚠️ **The exe distinguishes `NaN` from `Infinity`, and so must this.** Both are printed in the
    same ten-column field rather than blanking the row, and both are *data*: they record how a run
    failed. `Infinity` went unseen until case29 -- a sub-critical discharge whose plume leaves the
    water column -- where one column overflows to it while its neighbours go NaN on the same row.
    Collapsing the two lost that distinction and broke the byte-exact round trip on those traces.
    """
    if math.isnan(value):
        text = "NaN"
    elif math.isinf(value):
        text = "Infinity" if value > 0 else "-Infinity"
    elif decimals < 0:
        text = f"{round(value)}"
    else:
        text = f"{value:.{decimals}f}"
    if len(text) > FIELD_WIDTH:
        raise ValueError(
            f"{text!r} does not fit the {FIELD_WIDTH}-column field; the exe has no wider "
            "form, so a value this large cannot be written in its format"
        )
    return text.rjust(FIELD_WIDTH)


def format_row(values: Sequence[float], table: str, columns: Sequence[str]) -> str:
    """One numeric row, right-trimmed exactly as the exe writes it.

    Short rows are allowed and are *not* padded: the terminating step is printed with only
    its non-chemistry columns, six fields where every other row in the same table has
    thirteen (case05 step 417). Passing the values you have reproduces that.
    """
    if len(values) > len(columns):
        raise ValueError(f"{len(values)} values against {len(columns)} columns")
    fields = [
        format_value(value, decimals_for(table, column))
        for value, column in zip(values, columns, strict=False)
    ]
    return "".join(fields).rstrip()


# --------------------------------------------------------------------------- document parts

#: Rules are always exactly 100 characters, and only the fill differs: one row of asterisks
#: opens the file, dashes separate the sections.
RULE_WIDTH = 100
ASTERISK_RULE = "*" * RULE_WIDTH
DASH_RULE = "-" * RULE_WIDTH

#: Event banners, verbatim. Each message has its **own** fixed shape -- the totals run 70, 72
#: and 84 characters and the fill is not centred -- so they cannot be generated from a rule
#: and are stored as measured. Every occurrence of a given message across the archived
#: traces is byte-identical, which is what licenses treating them as constants.
BANNERS: dict[str, str] = {
    "Plume traps": f"{'-' * 28} Plume traps {'-' * 29}",
    "Local maximum rise or fall": f"{'-' * 22} Local maximum rise or fall {'-' * 20}",
    "Starting Farfield Calculations": f"{'-' * 20} Starting Farfield Calculations {'-' * 20}",
    "merging happened": f"{'-' * 25} merging happened {'-' * 27}",
    "Reached Chronic Mixing Zone": f"{'.' * 29} Reached Chronic Mixing Zone {'.' * 26}",
    "Plume surfaces": f"{'-' * 28} Plume surfaces {'-' * 26}",
    "Plume hits the bottom": f"{'-' * 25} Plume hits the bottom {'-' * 22}",
}

#: The advisory the exe appends when the plumes never merged.
NOT_MERGED_NOTE = "Note: Plumes not merged, Brooks method may be overly conservative"

_WASTEFIELD_PREFIX = "Farfield dispersion based on wastefield width of :"
_WASTEFIELD_FIELD = 11


def format_banner(text: str) -> str:
    """One event banner, exactly as the exe writes it.

    Refuses an unknown message rather than inventing a plausible one: the widths are
    per-message and measured, so a guess would be wrong in a way nothing would catch.
    """
    try:
        return BANNERS[text]
    except KeyError:
        raise ValueError(
            f"no measured banner for {text!r}; the exe's widths are per-message and cannot "
            "be derived, so this has to be read off a trace and added to BANNERS"
        ) from None


def format_header(names: Sequence[str], units: Sequence[str]) -> list[str]:
    """The two header lines of a table: names, then units.

    Both are the same ten-column fields as the data. The step table **staggers** them -- the
    name row omits `Step` and the unit row carries it as its first field -- so a leading
    `Step` in `names` is written on the units line instead, and the names line opens with a
    blank field::

                      Dilutn     P-dia    x-posn
              Step (FluxAvg)       (m)       (m)
    """
    if len(units) != len(names):
        raise ValueError(f"{len(names)} names against {len(units)} units")
    if names and names[0] == "Step":
        blank = " " * FIELD_WIDTH
        name_line = blank + "".join(n.rjust(FIELD_WIDTH) for n in names[1:])
        unit_line = "".join(u.rjust(FIELD_WIDTH) for u in units)
    else:
        name_line = "".join(n.rjust(FIELD_WIDTH) for n in names)
        unit_line = "".join(u.rjust(FIELD_WIDTH) for u in units)
    return [name_line.rstrip(), unit_line.rstrip()]


def format_wastefield_width(width: float) -> str:
    """The far-field preamble line, two decimals in an eleven-column field."""
    text = "NaN" if not math.isfinite(width) else f"{width:.2f}"
    return f"{_WASTEFIELD_PREFIX}{text.rjust(_WASTEFIELD_FIELD)} (m)"


#: The far-field preamble, per law, exactly as the exe prints it. Only the 4/3 form carries the
#: word `based` (case50 measured the other two), and like `format_banner` this refuses a law it
#: has not seen rather than inventing a plausible line that nothing would catch.
_EDDY_LAW_LINES: dict[str, str] = {
    "4/3 Power Law": "4/3 Power Law based Eddy Diffusivity is used:",
    "Constant": "Constant Eddy Diffusivity is used:",
    "Linearly Varying": "Linearly Varying Eddy Diffusivity is used:",
}


def format_eddy_law(law: str) -> str:
    """`'4/3 Power Law based Eddy Diffusivity is used:'`, or the constant / linear forms.

    The reader keeps the law as the text before `(based) Eddy Diffusivity is used`, so the three
    values here are the three the archive has printed. An unknown law raises, because a guessed
    preamble would break the byte-exact round trip in a way no test would name.
    """
    try:
        return _EDDY_LAW_LINES[law]
    except KeyError:
        known = ", ".join(repr(k) for k in _EDDY_LAW_LINES)
        raise ValueError(f"unknown eddy-diffusivity law {law!r}; known: {known}") from None
