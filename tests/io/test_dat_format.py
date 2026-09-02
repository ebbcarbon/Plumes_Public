"""Byte-exact numeric formatting for the `.dat` -- Phase 6 track A.

The acceptance test is a round trip over the whole archive: take every numeric line in every
reference trace, parse it to floats, format it back, and require the bytes to match. That is
what "byte-exact" can mean for a formatter -- our *physics* differs from the exe by 0.3-1 %,
so a `.dat` generated from our own numbers could never match theirs.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from plumes2.io.dat import _split_fixed_width
from plumes2.io.dat_format import (
    FIELD_WIDTH,
    decimals_for,
    format_row,
    format_value,
)

ROOT = Path(__file__).resolve().parents[2]
_NUMERIC = re.compile(r"^\s*(?:-?\d+\.?\d*|NaN)(\s|$)", re.IGNORECASE)


def _traces() -> list[Path]:
    found = sorted(ROOT.glob("reference_cases/**/*.dat")) + sorted(
        ROOT.glob("upstream/**/*.dat")
    )
    assert found, "no reference traces found"
    return found


def _numeric_lines(path: Path) -> list[str]:
    raw = path.read_bytes().decode("ascii", "replace")
    return [line for line in raw.split("\r\n") if line.strip() and _NUMERIC.match(line)]


def test_the_field_width_is_uniform_across_the_whole_archive() -> None:
    """15 408 lines, one rule: every field right-justified in ten columns.

    Reformatted from each line's own fields, so this isolates the *layout* from the decimal
    question -- the fields already carry their decimals.

    ⚠️ **Split by the grid, not by whitespace, since 2026-08-25.** This test rebuilt each line
    from `line.split()`, which silently assumes every field is separated -- and the assumption is
    the very thing the test claims to be checking. `pending/dose_parity`'s TA 20 000 run prints
    `R_cal` = `105022.286`, exactly `FIELD_WIDTH` characters, so it abuts its neighbour and the
    whitespace split returns one token where there are two. Rebuilding that gives a *shorter*
    line and the test failed on a file that is perfectly well formed. `_split_fixed_width` is the
    reader's own splitter, so the test and the parser now agree about what a field is.
    """
    checked = 0
    for path in _traces():
        for line in _numeric_lines(path):
            assert len(line) % FIELD_WIDTH == 0, f"{path.name}: not a whole number of fields"
            rebuilt = "".join(
                line[start : start + FIELD_WIDTH].strip().rjust(FIELD_WIDTH)
                for start in range(0, len(line), FIELD_WIDTH)
            )
            assert rebuilt == line, f"{path.name}: {line!r}"
            checked += 1
    assert checked > 15000, checked


@pytest.mark.parametrize(
    ("table", "column", "expected"),
    [
        ("Ambient", "Amb-cur", 3),
        ("Ambient", "Disprsn", 5),
        ("Diffuser", "P-dia", 2),
        ("Simulation Results", "P-dia", 3),
        ("Simulation Results", "Step", -1),
        ("farfield", "Dilution", 3),
    ],
)
def test_decimals_depend_on_the_table_not_just_the_column(
    table: str, column: str, expected: int
) -> None:
    """`P-dia` is the trap: two decimals in the diffuser echo, three in the step table."""
    assert decimals_for(table, column) == expected


def test_an_unknown_table_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match=r"unknown \.dat table"):
        decimals_for("Nonsense", "P-dia")


def test_nan_and_infinity_both_survive_because_both_are_data() -> None:
    """case09 goes numerically bad and prints NaN; case29 prints `Infinity` beside it.

    ⚠️ They are **different data** -- they record different failures -- and collapsing `Infinity`
    to `NaN` is what broke the byte-exact round trip on case29's three traces, the first `.dat`
    files in the archive the writer had ever failed.
    """
    assert format_value(math.nan, 3) == "       NaN"
    assert format_value(math.inf, 3) == "  Infinity"
    assert format_value(-math.inf, 3) == " -Infinity"
    for value in (math.nan, math.inf, -math.inf):
        assert len(format_value(value, 3)) == FIELD_WIDTH


def test_a_value_too_wide_is_refused_rather_than_silently_mangled() -> None:
    """The exe has no wider field, so there is no right answer -- say so instead."""
    with pytest.raises(ValueError, match="does not fit"):
        format_value(1.2345678e9, 3)


def test_the_two_decimal_echo_is_reproduced_deliberately() -> None:
    """The trap that cost a day: 0.0127 prints as 0.01, and 0.005 as 0.01.

    Track A has to reproduce that, which is precisely why track B writes full precision to
    CSV instead of trusting this. See PLAN.md §7b.
    """
    assert format_value(0.0127, decimals_for("Diffuser", "P-dia")).strip() == "0.01"
    assert format_value(0.005, decimals_for("Diffuser", "Ttl-flo")).strip() == "0.01"
    # The same quantity in the step table keeps a decimal the echo throws away.
    assert format_value(0.0127, decimals_for("Simulation Results", "P-dia")).strip() == "0.013"


def test_a_short_row_is_not_padded() -> None:
    """The terminating step prints only its non-chemistry columns (case05 step 417)."""
    columns = ["Step", "Dilutn", "P-dia", "TA", "DIC"]
    full = format_row([417, 1.5, 0.2, 2300.0, 2000.0], "Simulation Results", columns)
    short = format_row([417, 1.5, 0.2], "Simulation Results", columns)
    assert full.startswith(short)
    assert len(short) < len(full)
    with pytest.raises(ValueError, match="against"):
        format_row([1.0] * 6, "Simulation Results", columns)


@pytest.mark.slow
def test_rows_round_trip_from_parsed_floats() -> None:
    """The real test: floats in, identical bytes out, for every table in the archive.

    Walks each file tracking which table it is inside, because the decimals depend on it.
    """
    tables = {"Ambient Table:": "Ambient", "Diffuser Table:": "Diffuser"}
    checked, seen = 0, set()
    for path in _traces():
        raw = path.read_bytes().decode("ascii", "replace")
        lines = raw.split("\r\n")
        table, columns = None, []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped in tables:
                table = tables[stripped]
                continue
            if stripped == "Simulation Results:":
                table = "Simulation Results"
                continue
            if not stripped or set(stripped) <= set("-*."):
                continue

            if _NUMERIC.match(line):
                if table is None or not columns:
                    continue
                # ⚠️ `_split_fixed_width`, not `line.split()`: a value filling all ten columns
                # leaves no separator, and this test's whole point is that the writer reproduces
                # such a line byte for byte. See the layout test above.
                values = _split_fixed_width(line)
                assert format_row(values, table, columns) == line, f"{path.name}: {line!r}"
                seen.add(table)
                checked += 1
                continue

            # A header: names, then a units line. The step table staggers `Step` onto it,
            # and the far-field block has no heading of its own -- it is recognised by its
            # first column being `Dilution`, against the step table's `Dilutn`.
            following = lines[index + 1] if index + 1 < len(lines) else ""
            names = line.split()
            if following.strip().startswith("Step"):
                table, columns = "Simulation Results", ["Step", *names]
            elif following.strip().startswith("("):
                columns = names
                if names and names[0] == "Dilution":
                    table = "farfield"
    assert checked > 15000, checked
    assert seen == {"Ambient", "Diffuser", "Simulation Results", "farfield"}, seen


# ------------------------------------------------------------------- document parts

_BANNER = re.compile(r"^[-.]{4,} (?P<text>\S.*?) [-.]{4,}$")


def _fields(line: str) -> list[str]:
    """Split a header line into its ten-column fields, dropping the blanks."""
    return [
        field
        for field in (line[j : j + 10].strip() for j in range(0, len(line), 10))
        if field
    ]


def _special_lines():  # type: ignore[no-untyped-def]
    """Every banner, note, wastefield and eddy-law line in the archive."""
    for path in _traces():
        raw = path.read_bytes().decode("ascii", "replace")
        for line in raw.split("\r\n"):
            yield path, line


def test_every_banner_and_special_line_in_the_archive_is_reproduced() -> None:
    """Every banner and note across the archive, with no message missing from `BANNERS`."""
    from plumes2.io.dat_format import (
        NOT_MERGED_NOTE,
        format_banner,
        format_eddy_law,
        format_wastefield_width,
    )

    checked, seen = 0, set()
    for path, line in _special_lines():
        match = _BANNER.match(line)
        if match:
            text = match.group("text")
            seen.add(text)
            assert format_banner(text) == line, f"{path.name}: {line!r}"
        elif line.startswith("Farfield dispersion"):
            token = line.split(":")[1].replace("(m)", "").strip()
            width = math.nan if token == "NaN" else float(token)
            assert format_wastefield_width(width) == line, f"{path.name}: {line!r}"
        elif "Eddy Diffusivity is used" in line:
            # The reader's rule: the law is the text before `(based) Eddy Diffusivity is used`;
            # only the 4/3 form carries `based` (case50).
            law = line.split(" Eddy Diffusivity is used")[0].removesuffix(" based").strip()
            assert format_eddy_law(law) == line, f"{path.name}: {line!r}"
        elif line.startswith("Note:"):
            assert line == NOT_MERGED_NOTE
        else:
            continue
        checked += 1
    assert checked > 250, checked
    assert len(seen) == 7, seen


def test_an_unknown_banner_is_refused_rather_than_invented() -> None:
    """The widths are per-message and measured; a plausible guess would be wrong silently."""
    from plumes2.io.dat_format import format_banner

    with pytest.raises(ValueError, match="no measured banner"):
        format_banner("Plume does a barrel roll")


def test_banner_widths_really_do_differ_between_messages() -> None:
    """The reason they are stored rather than centred in a fixed field."""
    from plumes2.io.dat_format import BANNERS

    widths = {len(line) for line in BANNERS.values()}
    assert widths == {70, 72, 84}, widths
    # And the fill is not symmetric, so centring would not reproduce them either.
    traps = BANNERS["Plume traps"]
    assert traps.index(" ") != len(traps) - traps.rindex(" ") - 1


def test_headers_round_trip_including_the_staggered_step_row() -> None:
    """144 header pairs across the archive, names and units both."""
    from plumes2.io.dat_format import format_header

    checked = 0
    for path in _traces():
        lines = path.read_bytes().decode("ascii", "replace").split("\r\n")
        for index in range(len(lines) - 1):
            names_line, units_line = lines[index], lines[index + 1]
            if not names_line.strip() or not units_line.strip():
                continue
            if _NUMERIC.match(names_line) or set(names_line.strip()) <= set("-*."):
                continue
            staggered = units_line.strip().startswith("Step")
            if not (units_line.strip().startswith("(") or staggered):
                continue

            names = _fields(names_line)
            units = _fields(units_line)
            if staggered:
                names = ["Step", *names]
            if len(units) != len(names):
                continue

            assert format_header(names, units) == [names_line.rstrip(), units_line.rstrip()]
            checked += 1
    assert checked > 140, checked


def test_a_header_with_mismatched_units_is_refused() -> None:
    from plumes2.io.dat_format import format_header

    with pytest.raises(ValueError, match="against"):
        format_header(["Depth", "Amb-cur"], ["(m)"])


def test_the_rules_are_a_hundred_characters() -> None:
    from plumes2.io.dat_format import ASTERISK_RULE, DASH_RULE, RULE_WIDTH

    assert len(ASTERISK_RULE) == len(DASH_RULE) == RULE_WIDTH == 100
    for path in _traces():
        raw = path.read_bytes().decode("ascii", "replace")
        assert raw.startswith(ASTERISK_RULE), path.name
        assert DASH_RULE in raw, path.name


# ------------------------------------------------------- whole-document round trip


@pytest.mark.slow
def test_every_archived_trace_round_trips_byte_for_byte() -> None:
    """⭐ Track A's acceptance test: parse a `.dat`, rebuild it, compare bytes.

    Nothing is replayed as text. Every line is regenerated from the measured primitives --
    rules from a fill character, headers from retained names and units, rows from parsed
    floats, banners from the per-message table. The layout supplies only the *order*, which
    is the one thing that cannot be derived.

    ⚠️ This tests the **formatter**, not the physics. Fed the exe's own numbers it reproduces
    the exe's file; fed ours it would not, because our dilution differs by 0.3-1 %. That is
    the only sense in which a re-implementation can be byte-exact.
    """
    from plumes2.io.dat import format_dat, read_dat

    checked = 0
    pending = 0
    for path in _traces():
        original = path.read_bytes().decode("ascii", "replace")
        assert format_dat(read_dat(path)) == original, path.name
        # ⚠️⚠️ **The count pin excludes `pending/`, the round trip does not.** Every trace found
        # is round-tripped, including raw exe output sitting in `reference_cases/pending/` --
        # that breadth is the point, and checking a returning run *before* it is archived is
        # when a format surprise is cheapest to find. But `pending/` holds working files whose
        # names and number change with every run at the keyboard, so counting them made the pin
        # fail on activity rather than on growth: it went 178 -> 186 in one afternoon, five of
        # those being raw `ModelResults_*.dat` from runs still in progress, four of which were
        # byte duplicates of traces already archived beside them. A pin that fires on that is
        # noise, and noise is what gets a real failure waved through.
        if "pending" in path.parts:
            pending += 1
            continue
        checked += 1
    # ⭐ 75, not the 42 the writer was built against. case24's five DO traces were added later
    # and needed **no change at all** -- including test38's 21-column set, the widest in the
    # archive and one the formatter had never seen. A format map that had been fitted rather than
    # measured would not have survived that. case25's far-field traces then made it 50, again
    # unchanged, and case27 and case28's twenty-two made it 75 -- among them DO columns carrying
    # **negative** values, and case29's `Infinity`, which the writer had been collapsing to
    # `NaN` until it met a trace that printed both on one row. case30's four brought it to 82 and
    # case31's two to 84, case32's five to 89, case33/34's nine to 98, case35/36/37's seventeen
    # to 115, case38's six to 121 and case39's seven to 128 -- and case31 is the first to carry a
    # trace from the **current** exe build, which the writer had never been fed and which needed
    # nothing either. case40/41's thirteen took it to 141, and case42-case45's twenty-three to
    # **178** -- the merging investigation's whole output, and again the writer needed nothing.
    # ⭐ Those twenty-three are worth naming because they are the *first* generated by
    # `plumes2.experiments` asking for every output column, so their column **order** differs from
    # every hand-made project in the archive: `Depth, Time, Net-Dil, ...` where the older traces
    # print `Depth, CL-Dil, Amb-Curr, ...`. The formatter takes the order from the layout it
    # measured rather than assuming one, which is exactly why that cost nothing.
    # The pin is expected to grow with the archive -- update it, having first checked that the new
    # traces round-trip, which is the whole point of it failing.
    #
    # ⭐ It counts **archived** traces only; `pending/` is round-tripped and not counted, for the
    # reason given in the loop. So this number moves when a case graduates, which is a deliberate
    # act someone should have to acknowledge, and not when a run lands in `pending/`, which is a
    # Tuesday.
    # 178 -> 190 on 2026-08-25, when case46/47/48 graduated out of `pending/` (12 traces).
    # 190 -> 194 on 2026-08-26: case49's two profile runs, and the 2026-08-24 prj-pair traces that
    # joined case46 -- all four legacy-build, all four unchanged through the writer.
    # 196 -> 204 on 2026-09-01: case51's eight flag-decode traces (legacy build, interval 5,
    # generated column order) -- all eight unchanged through the writer.
    # 204 -> 206 the same evening: case52's bottom-stop pair, again unchanged.
    assert checked == 206, checked
    assert pending >= 0  # kept explicit so the split above cannot be silently dropped


def test_the_truncated_terminating_row_is_not_padded_back_out() -> None:
    """case05's last step prints six fields where its neighbours print thirteen.

    The reader pads it with NaN to make a rectangular frame, and case09 prints *genuine*
    NaNs, so the two are indistinguishable afterwards -- `row_widths` is what keeps them
    apart. Without it the terminating row would come back seven fields too long.
    """
    from plumes2.io.dat import read_dat

    dat = read_dat(ROOT / "reference_cases" / "case05_macoma_merging" / "test4_TxtOutputs.dat")
    widths = {
        width
        for (table, _), width in dat.row_widths.items()
        if table == "Simulation Results"
    }
    assert len(widths) > 1, "this case must contain a short row for the test to mean anything"
    assert min(widths) < max(widths)


def test_a_rule_closes_a_table_rather_than_reading_as_an_empty_banner() -> None:
    """A latent reader quirk the layout work exposed.

    `_BANNER_RE` matches a line of dashes with empty text, so a rule following the last data
    row was captured as a banner. It was invisible while echo-table banners were discarded,
    and put phantom entries in the document the moment anything looked at them.
    """
    from plumes2.io.dat import read_dat

    for path in _traces():
        dat = read_dat(path)
        assert all(event.text.strip() for event in dat.events), path.name
        for kind, payload in dat.layout:
            if kind == "banner":
                assert str(payload).strip(), path.name


def test_write_dat_puts_the_formatted_text_on_disk_as_ascii() -> None:
    """The public writer had no test at all until the 2026-08-17 audit.

    It is one line over `format_dat`, which is exhaustively tested -- but it is also the only place
    the encoding is chosen, and a `.dat` that came back as UTF-8 with a BOM would round-trip in
    Python and be rejected by the exe. That is precisely the kind of failure a thin wrapper hides.
    """
    import tempfile

    from plumes2.io.dat import read_dat, write_dat

    source = next(path for path in _traces() if path.name == "ModelResults_TxtOutputs.dat")
    parsed = read_dat(source)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "out.dat"
        write_dat(parsed, target)
        raw = target.read_bytes()
    assert raw == source.read_bytes()
    raw.decode("ascii")  # raises if anything non-ASCII slipped in
