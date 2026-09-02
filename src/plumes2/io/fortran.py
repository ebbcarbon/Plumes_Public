"""Fortran fixed-format primitives for the `.prj` project file.

The layout was reverse-engineered from the three `.prj` files in the repo (see
PORTING_NOTES.md section 4). Two record types occur:

**Integer records** occupy 12 columns, right-justified::

    '           1'

**Real records** are written in fields of 12 columns, each holding a 9-character
Fortran E-format number at offset 1 within the field, and trailing whitespace is
stripped from the line::

    ' 0.760E-01   0.310E+00   0.450E+02'
     ^          ^^^          ^
     |          | |          number starts at column 13 (= 1 + 12)
     |          | two pad columns closing field 0
     number starts at column 1

So a line of *n* reals is ``12 * (n - 1) + 10`` characters long. That prediction
matches every real record in all three files: 1, 2, 4, 9 and 10 columns give 10,
22, 46, 106 and 118 characters respectively.

Lines are separated by CRLF and the file ends with one, matching the exe.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

__all__ = [
    "INT_WIDTH",
    "REAL_FIELD_WIDTH",
    "format_e",
    "format_int_record",
    "format_real_record",
    "parse_e",
    "parse_int_record",
    "parse_real_record",
    "real_record_width",
]

INT_WIDTH = 12
REAL_FIELD_WIDTH = 12

#: Blank columns the exe leaves after each real, inside the field width.
_TRAILING_SPACES = 2
_MANTISSA_DIGITS = 3
#: Width of the number itself, e.g. len('0.760E-01').
_NUMBER_WIDTH = _MANTISSA_DIGITS + 6

_REAL_RECORD_RE = re.compile(r"^[-+\s\d.EDed]+$")


def real_record_width(n_values: int) -> int:
    """Character length of a right-trimmed real record holding `n_values` numbers."""
    if n_values < 1:
        return 0
    return REAL_FIELD_WIDTH * (n_values - 1) + 1 + _NUMBER_WIDTH


def format_e(value: float) -> str:
    """Format `value` the way the exe does: a normalised Fortran E field.

    The mantissa is scaled into [0.1, 1) so the text always begins ``0.``, and the
    exponent carries an explicit sign and two digits::

        0.076  -> '0.760E-01'
        45.0   -> '0.450E+02'
        1.0    -> '0.100E+01'
        0.0    -> '0.000E+00'
    """
    if value == 0.0 or not math.isfinite(value):
        # The exe has no representation for inf/nan; emitting zero keeps the file
        # loadable rather than producing something it would choke on.
        return "0.000E+00"

    magnitude = abs(value)
    exponent = math.floor(math.log10(magnitude)) + 1
    mantissa = magnitude / 10.0**exponent
    text = f"{mantissa:.{_MANTISSA_DIGITS}f}"
    if not text.startswith("0."):
        # Rounding carried into the integer part (0.9999 -> '1.000'); renormalise.
        exponent += 1
        mantissa = magnitude / 10.0**exponent
        text = f"{mantissa:.{_MANTISSA_DIGITS}f}"

    sign = "-" if value < 0 else ""
    return f"{sign}{text}E{exponent:+03d}"


def parse_e(text: str) -> float:
    """Parse one Fortran real, tolerating the ``D`` exponent marker."""
    cleaned = text.strip().replace("D", "E").replace("d", "e")
    if not cleaned:
        return 0.0
    return float(cleaned)


def format_real_record(values: Sequence[float]) -> str:
    """Render a real record, right-trimmed, exactly as the exe writes it."""
    fields = []
    for value in values:
        # The **signed** number is right-justified to end two characters before the field
        # boundary, so a minus sign eats a leading space instead of widening the field:
        #
        #     |   0.150E+02|  positive: one leading space, then the 9-character number
        #     |  -0.450E+02|  negative: the sign takes that space, field width unchanged
        #
        # Measured off case22, whose -45 degree vertical angle is the **first negative value
        # in any archived `.prj`** -- every other project is non-negative throughout, which is
        # why an earlier version of this function padded the magnitude and prepended the sign,
        # producing a field one character too wide, and no round-trip test could see it.
        fields.append(format_e(value).rjust(REAL_FIELD_WIDTH - _TRAILING_SPACES) + "  ")
    return "".join(fields).rstrip()


def parse_real_record(line: str, n_values: int | None = None) -> list[float]:
    """Parse a whitespace-separated real record.

    Splitting on whitespace rather than slicing fixed columns means a value wide
    enough to fill its field still parses. `n_values`, when given, is checked.
    """
    if not _REAL_RECORD_RE.match(line):
        raise ValueError(f"not a Fortran real record: {line!r}")
    values = [parse_e(token) for token in line.split()]
    if n_values is not None and len(values) != n_values:
        raise ValueError(f"expected {n_values} reals, found {len(values)}: {line!r}")
    return values


def format_int_record(value: int) -> str:
    """Render an integer record in 12 right-justified columns."""
    return f"{value:{INT_WIDTH}d}"


def parse_int_record(line: str) -> int:
    """Parse an integer record."""
    text = line.strip()
    if not re.fullmatch(r"[-+]?\d+", text):
        raise ValueError(f"not an integer record: {line!r}")
    return int(text)
