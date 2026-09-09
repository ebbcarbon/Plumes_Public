"""Several runs on one set of axes, labelled by what actually differs between them.

> Several configurations on one set of axes — comparing dose, geometry or ambient side by side
> is the actual working mode.

The naive way to satisfy that is a plotting argument: pass a list of frames and a list of legend
strings. It goes wrong immediately, because the strings are written by hand. Relabel a run, edit
one case and forget the other, or reorder the list, and the figure says something false with no
way to notice — which is precisely what §7b's traceability rule exists to prevent.

So a comparison is a **collection of runs**, and the legend is *derived* from the cases. Ask two
runs what differs and they answer `port_spacing: 1.0 -> 2.0`; nobody types "1 m spacing" and
nobody can mistype it. It also answers the question a reader of a multi-line figure actually has,
which is not "what are these runs called" but "what is different about them".

⚠️ **The diff is over the *resolved* case**, defaults included, for the same reason
`provenance.case_digest` is: a default that changed between two runs is a real difference, and one
that only shows up in a resolved dump. Two cases whose files differ only in whitespace compare
equal, and two that were written identically but validated under different defaults do not.

⚠️ **Tables are compared whole.** A 6-level ambient profile that differs in one temperature
reports as `ambient.levels` changing, not as 60 separate scalar differences. A legend needs the
name of the knob, and the knob is the table.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from plumes2.config import Case
from plumes2.results import Results

__all__ = [
    "Comparison",
    "Difference",
    "differences",
    "flatten_case",
]

#: Fields whose contents are compared as a unit rather than element by element -- the profile
#: tables. Their `repr` is useless in a legend, so `Difference.describe` summarises them instead.
_WHOLE_TABLE_FIELDS = frozenset(
    {
        "ambient.levels",
        "ambient.chemistry",
        "ambient.dissolved_oxygen",
    }
)


def flatten_case(case: Case) -> dict[str, Any]:
    """The resolved case as `dotted.path -> value`, with the profile tables kept whole.

    `None` for an absent optional section is a value like any other: a run with chemistry and one
    without differ at `effluent_chemistry`, which is exactly what a legend should say.
    """

    def walk(prefix: str, value: Any) -> Iterator[tuple[str, Any]]:
        if isinstance(value, dict) and prefix not in _WHOLE_TABLE_FIELDS:
            for key, item in value.items():
                yield from walk(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, list) and prefix in _WHOLE_TABLE_FIELDS:
            # Compared whole: a tuple of tuples is hashable and order-sensitive, and a profile's
            # order is meaningful (it is interpolated in depth).
            yield prefix, tuple(tuple(sorted(row.items())) for row in value)
            # And column by column where a column is uniform down the table: an ambient whose
            # current is 0.05 m/s at every depth differs from one at 0.02 m/s *in its current*,
            # and a legend can say so, where 'levels (6 levels)' twice says nothing.
            if value and all(isinstance(row, dict) for row in value):
                for key in value[0]:
                    column = [row.get(key) for row in value]
                    if all(entry == column[0] for entry in column[1:]):
                        yield f"{prefix}.{key}", column[0]
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from walk(f"{prefix}[{index}]", item)
        else:
            yield prefix, value

    return dict(walk("", case.model_dump(mode="json")))


@dataclass(frozen=True, slots=True)
class Difference:
    """One field on which the runs of a comparison disagree, and the value each one has."""

    #: Dotted path into the resolved case, e.g. `diffuser.port_spacing`.
    field: str
    #: One entry per run, in the collection's order.
    values: tuple[Any, ...]

    @property
    def name(self) -> str:
        """The leaf field name, which is what a legend has room for."""
        return self.field.rsplit(".", maxsplit=1)[-1]

    def describe(self, index: int) -> str:
        """This run's value, short enough for a legend entry.

        A whole table cannot be printed, so it is named by its size -- `ambient.levels (6 levels)`
        distinguishes two profiles without pretending to summarise their contents.
        """
        value = self.values[index]
        if self.field in _WHOLE_TABLE_FIELDS:
            return f"{self.name} ({len(value)} levels)"
        if isinstance(value, float):
            return f"{self.name} {value:g}"
        return f"{self.name} {value}"


def differences(cases: Sequence[Case]) -> list[Difference]:
    """Every resolved field on which `cases` do not all agree, in case-definition order.

    `description` is excluded -- it names a case, it does not configure one.

    An empty list means the cases are identical, which is worth knowing: a comparison figure of
    two identical cases is a figure of one line drawn twice, and a caller should say so rather
    than let a reader infer a difference from two colours.
    """
    if len(cases) < 2:
        return []
    # The description is a label, not a setting: two cases that differ only in what they are called
    # are the same run, and a legend built on it would say nothing about the physics.
    flattened = [
        {key: value for key, value in flatten_case(case).items() if key != "description"}
        for case in cases
    ]
    fields = list(flattened[0])
    # A field missing from one case is itself a difference; `model_dump` on a validated Case is
    # complete, so this only fires if the model gains conditional fields later.
    fields += [key for other in flattened[1:] for key in other if key not in flattened[0]]
    seen: set[str] = set()
    found = []
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        values = tuple(entry.get(field) for entry in flattened)
        if any(value != values[0] for value in values[1:]):
            found.append(Difference(field, values))
    # A whole table that differs only in columns already named column-by-column adds nothing
    # a legend can use, so it steps aside for them.
    named = {difference.field for difference in found}
    return [
        difference
        for difference in found
        if difference.field not in _WHOLE_TABLE_FIELDS
        or not any(name.startswith(difference.field + ".") for name in named)
    ]


@dataclass(frozen=True, slots=True)
class Comparison:
    """Several completed runs, with labels derived from their cases rather than supplied.

    This is the unit a multi-configuration figure takes. It holds `Results`, not frames, so a
    panel can reach the case, the provenance and the far field without any of them being passed
    alongside and getting out of step.
    """

    runs: tuple[Results, ...]

    def __post_init__(self) -> None:
        if not self.runs:
            raise ValueError("a comparison needs at least one run")

    def __len__(self) -> int:
        return len(self.runs)

    def __iter__(self) -> Iterator[Results]:
        return iter(self.runs)

    @property
    def cases(self) -> tuple[Case, ...]:
        return tuple(run.case for run in self.runs)

    @property
    def differences(self) -> list[Difference]:
        """What distinguishes the runs, resolved defaults included."""
        return differences(self.cases)

    def labels(self, *, max_fields: int = 2) -> tuple[str, ...]:
        """A legend entry per run, naming the fields that differ and this run's value of each.

        `max_fields` bounds the label: when many things vary at once no legend can carry them all,
        so the first few are named and the rest counted. The counted remainder is *stated*, never
        dropped silently -- a legend that reads `spacing 1, ports 25 (+3 more)` tells a reader
        there is more to the difference, where truncating to `spacing 1` would not.

        With nothing differing, every run is labelled `identical`, which is the honest answer and
        makes a duplicated line obvious rather than mysterious.

        The bound bends for one thing: two runs must never share a label. If the first
        `max_fields` fields agree between some pair of runs -- four effluents whose first two
        differences are salinity and excess density, say, two of which are the same seawater --
        further fields are added, in order, until every label is distinct (or every field is
        shown). A legend with two identical entries misidentifies a line; a longer one does not.
        """
        found = self.differences
        if not found:
            return tuple("identical" for _ in self.runs)
        shown_count = min(max_fields, len(found))

        def build(count: int) -> tuple[str, ...]:
            shown, hidden = found[:count], found[count:]
            labels = []
            for index in range(len(self.runs)):
                parts = [difference.describe(index) for difference in shown]
                if hidden:
                    parts.append(f"(+{len(hidden)} more)")
                labels.append(", ".join(parts))
            return tuple(labels)

        labels = build(shown_count)
        while len(set(labels)) < len(self.runs) and shown_count < len(found):
            shown_count += 1
            labels = build(shown_count)
        return labels

    def frame(self, *, farfield: bool = False) -> pd.DataFrame:
        """The runs' rows in one long frame, with a `run` column carrying the derived label.

        Long rather than wide, because the runs do not share a time grid -- they terminate at
        different times, and reindexing them onto a common one would interpolate output that was
        never computed. A long frame plots directly, groups directly, and invents nothing.

        ⚠️ **The frames are SI.** Convert once, after this, with `display.convert_frame`: doing it
        per run would let two runs reach the same axes in different units.
        """
        labels = self.labels()
        pieces = []
        for label, run in zip(labels, self.runs, strict=True):
            source = run.farfield if farfield else run.nearfield
            if source is None:
                continue
            pieces.append(source.assign(run=label))
        if not pieces:
            raise ValueError("no run in this comparison produced a far field")
        return pd.concat(pieces, ignore_index=True)
