"""One line naming *why* two values differ, when the whole difference has a single explanation.

The diff says what differs, which is where every assertion library stops.  It leaves the reader to
work out why, and there are failures where that is genuinely hard: two strings that render
identically and differ in a trailing space, a comparison that can never pass because a NaN is in it.

A hint is stated only when it accounts for **every** entry in the diff.  A partial explanation is
worse than none, because the reader acts on it and lands back at the same failure.  That rule is what
keeps this from becoming the kind of advice people learn to scroll past, and it is measurable: over a
corpus of 20000 ordinary failures (a wrong leaf somewhere in a generated structure) the checks below
stay silent on all of them, and over a set of near misses built to resemble each form without being
it, likewise.

Everything here reads the diff rather than the values.  That is not only cheaper, though it is: the
diff of a failure over 500 records holds one entry, so the cost does not grow with the data.  It also
means a difference nested six levels down is examined exactly like a top-level one, with no separate
code path.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import difflib
import enum
import fractions
import json
import re
import sys
from collections import Counter
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from ._engine._compare import _non_finite
from ._engine._equality import comparable_fields
from ._engine._introspection import (
    class_name,
    class_namespace,
    class_tree,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    kind_of,
)
from ._engine._ordering import equals, nan_operand
from .errors import _capped, _class_names, _safe_repr, _safe_str

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from .errors import DiffEntry, DiffResult, Step

    # a step's wording: fixed, or decided from the shape of the pairs it is describing
    _Label = str | Callable[[Sequence[tuple[object, object]]], str]

_OBJECT_EQUALITY: Final = object.__dict__["__eq__"]
_NAN_FACT = "a NaN takes part in this comparison, and a NaN is equal to nothing, not even itself"
_IDENTITY_FACT = (
    "these values compare with object's __eq__, so equality is identity and no two separate instances are equal"
)

_UNSEEN_FACT = "a difference here prints the same on both sides, so what holds the two apart is not in their repr"
_UNSEEN_IDENTITY_FACT = (
    "a difference here prints the same on both sides, and the class of the two leaves __eq__ to object,"
    " so two separate instances are never equal"
)
_ORDER_FACT = "both sides hold the same elements, in a different order"
_UNSEEN_ORDER_FACT = f"{_ORDER_FACT}, and their repr does not show which is which"
# exact types whose repr differs wherever their values do, so ``==`` answers for the repr at a fraction of its cost
_PRINTED_AS_HELD: Final = frozenset({int, str, bytes, bool})
# the plain values a payload spells one way and a test another: an id as text, a flag as a word
_READ_AS_TEXT: Final = frozenset({int, float, str, bool})

_VALUE_KINDS: Final = frozenset(
    {"dict", "sequence", "dataclass", "namedtuple", "model", "attrs", "set", "string", "scalar"}
)
"""Diff kinds whose entries hold two values compared for equality.

Everything here reasons about a pair as two values, so it only applies where both sides are one.  A
``match`` entry holds the actual value against a *description* of a predicate ("a value equal to
<guest>"), and an ``openapi`` one against a schema violation.  Treating a description as a value is
not a false positive waiting to happen so much as a category error, and one that would surface as an
authoritative-sounding line about whitespace in a predicate.
"""


def _newlines(value: object) -> object:
    if isinstance(value, bytes):
        return bytes.replace(value, b"\r\n", b"\n")
    return str.replace(value, "\r\n", "\n") if isinstance(value, str) else value


def _stripped(value: object) -> object:
    if isinstance(value, bytes):
        return bytes.strip(value)
    return str.strip(value) if isinstance(value, str) else value


def _spaced(value: object) -> object:
    if isinstance(value, bytes):
        return b" ".join(bytes.split(value))
    return " ".join(str.split(value)) if isinstance(value, str) else value


def _parsed_json(value: object) -> object:
    """A string that is a JSON document, parsed.  Anything else passes through."""
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _decoded(value: object) -> object:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    return value


def _enum_value(value: object) -> object:
    return value.value if isinstance(value, enum.Enum) else value


def _json_label(pairs: Sequence[tuple[object, object]]) -> str:
    """What parsing actually resolved, which is not the same thing on both shapes.

    One side a string and the other a container is the familiar forgotten ``.json()``.  Two strings
    that parse to the same document differ in their formatting instead, and calling either of them
    unparsed would be plainly wrong about both.
    """
    if all(isinstance(left, str) and isinstance(right, str) for left, right in pairs):
        return "the same JSON written differently"
    return "unparsed JSON text"


_OF_SPACE: list[tuple[Callable[[object], object], _Label]] = [
    (_newlines, "line endings"),
    (_stripped, "surrounding whitespace"),
]
# ordered, narrower first: a step explains a pair only if the pair differed before it ran
_STEPS: list[tuple[Callable[[object], object], _Label]] = [
    (_parsed_json, _json_label),
    (_decoded, "bytes against decoded text"),
    (_enum_value, "enum members against their values"),
    *_OF_SPACE,
]


def _explains(pairs: Sequence[tuple[object, object]], steps: Sequence[Callable[[object], object]]) -> bool:
    """Whether applying ``steps`` to both sides of every pair leaves nothing differing.

    A pair that already matches counts against every step rather than for it.  Under
    ``strict_types=True`` the two sides of an entry can compare equal and still be a difference,
    because what differs is their type - and then any normalisation "explains" them by doing nothing,
    so the first step in the ladder took the credit and the reader was told that a comparison holding
    no JSON at all was one of unparsed JSON text.

    A pair the steps left as it was is not accounted for either, and is not asked again: an ``==`` that answered
    otherwise the second time credited a step that had done nothing.

    Comparison failures count as "not explained" rather than propagating.  This runs while a failure
    is already being raised, on values the caller wrote, and a numpy array or any object with an
    opinionated ``__eq__`` can raise from ``==``.  Letting that out would replace the assertion error
    the reader needs with a crash from the line that was only trying to be helpful.
    """
    try:
        for left, right in pairs:
            if equals(left, right):
                return False
            read_left, read_right = left, right
            for step in steps:
                read_left, read_right = step(read_left), step(read_right)
            if (read_left is left and read_right is right) or not equals(read_left, read_right):
                return False
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    return True


def _typed(pairs: Sequence[tuple[object, object]], kind: str) -> str | None:
    """Whether every pair differs in its type, and what kind of type difference it is.

    The leaf twin of the DTO-against-payload claim above, and the case a REST payload produces more
    than any other: the ids came back as ``"7"`` where the test expects ``7``.  Two facts live here
    rather than one, because they are not the same news.  Values that compare equal differ only in
    their type, which is a difference at all only under ``strict_types``.  Values that do not compare
    equal but read alike are the same text on one side and a parsed value on the other.

    Silent where the headline already said it.  A scalar failure whose two sides render alike is
    tagged by `_disambiguated` as ``<1:str>`` / ``<1:int>``, which names the two types outright, and
    a line under it restating that in general terms is worse than nothing.
    """
    try:
        if not all(kind_of(left) is not kind_of(right) for left, right in pairs):
            return None
        if kind == "scalar" and all(str(left) == str(right) for left, right in pairs):
            return None
        if all(equals(left, right) for left, right in pairs):
            return "the values on both sides are equal, and only their types differ"
        if all(str(left) == str(right) for left, right in pairs):
            return "every difference here is the same text against a value of another type"
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None
    return None


def diagnose(
    diff: DiffResult | None,
    actual: object = None,
    expected: object = None,
    *,
    identity: bool = False,
    comparators: bool = False,
) -> str | None:
    """The one line to add to a failure message, or ``None`` when nothing can be said.

    Args:
        diff: the structured diff already built for this failure.
        actual: the value asserted on, needed only for the string case below.
        expected: the value it was compared against.
        identity: whether the comparison was an unconfigured equality one that `identity_candidate`
            found identity-bound *before* it ran.  Only then does identity account for the failure.
        comparators: whether the comparison was given ``comparators=``.  Identity is then not said of a pair
            inside the diff, whose verdict may be the predicate's.

    Returns:
        A lowercase clause to put on its own line under the message, or ``None``.
    """
    if diff is None or diff.kind not in _VALUE_KINDS:
        return None
    # asked of the two values compared, never of a pair inside the diff: identity equality can never pass
    if identity:
        return _IDENTITY_FACT
    if not diff.entries:
        return None
    entries = diff.entries

    # one flat pass: this is the only part whose cost grows with the entry count
    pairs: list[tuple[object, object]] = []
    # by the container each pair sits in: values swapped between two lists are not one list rearranged
    per_container: dict[tuple[object, ...], list[tuple[object, object]]] = {}
    absent_seen = False
    absent_expected_only = True
    positional = True
    for entry in entries:
        left, right = entry.actual, entry.expected
        if nan_operand(left) or nan_operand(right):
            # with a NaN in the comparison no other value would make it pass, so it comes before anything else
            return _beside_a_nan(entries, comparators=comparators)
        absent = entry.absent
        if absent is None:
            pairs.append((left, right))
            per_container.setdefault(entry.steps[:-1], []).append((left, right))
            absent_expected_only = False
        else:
            absent_seen = True
            if absent != "expected":
                absent_expected_only = False
        # a step and not the rendered text: a mapping key ending in a bracket used to read as an index
        if positional and not (entry.steps and entry.steps[-1].kind == "index"):
            positional = False

    if diff.kind == "string":
        # the whole strings: `splitlines()` reads "\r\n" as "\n", so a text differing in both yields one entry
        if not isinstance(actual, (str, bytes)) or not isinstance(expected, (str, bytes)):
            return None
        return _named([(actual, expected)])

    # restricted to plain mappings, since telling someone their list carries extra keys helps nobody
    if diff.kind == "dict" and absent_seen and absent_expected_only:
        return "every shared key matches, and actual carries keys the expected side does not"

    # a mixture of absent sides and differing values has no single statement that covers it
    if absent_seen:
        return _unseen(pairs, comparators=comparators)

    # a DTO against the payload it was built from, said before the leaf steps because the shape is the narrower claim
    if all(type(left) is not type(right) and _fields_match(left, right) for left, right in pairs):
        return "the contents match field for field, and only the type of the two sides differs"

    named = _named(pairs)
    if named is not None:
        return named

    # after the ladder: a step that resolves the pairs has named the encoding they differ in, which is narrower
    typed = _typed(pairs, diff.kind)
    if typed is not None:
        return typed

    # last, as the broadest thing that can be said; one differing value can never be a rearrangement
    if (
        len(pairs) >= 2
        and positional
        and all(len(group) >= 2 and _same_values(group) for group in per_container.values())
    ):
        # the elements moved, and where two of them print the same no row shows which went where
        return _UNSEEN_ORDER_FACT if any(_prints_alike(left, right) for left, right in pairs) else _ORDER_FACT
    return _unseen(pairs, comparators=comparators)


def placed(diff: DiffResult | None) -> str | None:
    """Where the differences of a diff sit, when they repeat at one to three places down a sequence, or ``None``.

    Forty rows that differ in one field are forty rows of diff to read before that can be said, and past the
    fiftieth the rows are not printed at all: a single difference of another field among them went unseen.
    A place is the path with every position replaced by ``[*]``.  It is a fact about where, said beside
    whatever is said about why, and it recommends nothing.
    """
    if diff is None or diff.kind not in _VALUE_KINDS or len(diff.entries) < 3:
        return None
    counted: dict[tuple[tuple[str, str], ...], int] = {}
    for entry in diff.entries:
        place = _place(entry.steps)
        if place is None:
            return None
        counted[place] = counted.get(place, 0) + 1
        if len(counted) > 3:
            return None
    total = len(diff.entries)
    spelled = {place: _spelled(place) for place in counted}
    # nothing repeats, two places read the same (a key and a field of one name), or one is too long to be a line
    if (
        len(counted) == total
        or len(set(spelled.values())) != len(spelled)
        or any(len(text) > 200 for text in spelled.values())
    ):
        return None
    if len(counted) == 1:
        return f"all {total} differences here are at <{next(iter(spelled.values()))}>"
    # by how many, and among equals by which came first, which is the order a dict keeps and a stable sort leaves
    ranked = [f"<{spelled[place]}> ({count})" for place, count in sorted(counted.items(), key=lambda item: -item[1])]
    return f"the {total} differences here are at {', '.join(ranked[:-1])} and {ranked[-1]}"


def _place(steps: Sequence[Step]) -> tuple[tuple[str, str], ...] | None:
    """*steps* with every position made one, or ``None`` where they name no field.

    The kind of each hop is kept, so a key and a field of one name are two places.  Only a name that is
    exactly a `str` counts: ``1`` and ``"1"`` are two keys and read as one.  A place with no position in it
    is met once and so never repeats, which is why none is asked for.
    """
    place: list[tuple[str, str]] = []
    named = False
    for step in steps:
        kind = step.kind
        if kind == "index":
            place.append(("index", "*"))
        elif kind in ("key", "attr") and type(step.value) is str:
            place.append((kind, step.value))
            named = True
        elif kind != "json":
            return None
    return tuple(place) if named else None


def _spelled(place: tuple[tuple[str, str], ...]) -> str:
    """A place as a path.  A name that is no identifier is quoted: ``[*]['a.b']`` is one key, ``[*].a.b`` two."""
    parts: list[str] = []
    for kind, name in place:
        if kind == "index":
            parts.append("[*]")
        elif not name.isidentifier():
            parts.append(f"[{name!r}]")
        else:
            parts.append(f".{name}" if parts else name)
    return "".join(parts)


def reads_as(one: object, other: object) -> bool:
    """Whether two plain values of two types read the same: ``7`` and ``"7"``."""
    kind, other_kind = type(one), type(other)
    return kind is not other_kind and kind in _READ_AS_TEXT and other_kind in _READ_AS_TEXT and str(one) == str(other)


class Roles(NamedTuple):
    """What the assertion asking calls the item it looked for and a candidate it looked among.

    ``is_in`` looks for the value among the items given, a subset for its own element in the superset.
    """

    sought: str = "the item not found"
    held: str = "an element"
    named: bool = False
    """Whether what it looked among are names, keys or attributes: one spelled almost the same is then said."""


_OF_AN_ITEM: Final = Roles()


def not_found(item: object, searched: Iterable[object], roles: Roles = _OF_AN_ITEM) -> str | None:
    """One line on why *item* was not found in *searched*, where a fact about the item says it, or ``None``.

    Said of the item sought and never of the collection: a NaN somewhere in a list does not explain a ``2`` that
    is missing from it.  Three facts are looked for.  The item is a NaN.  An element reads the same and is of
    another plain type.  An element prints the same, is of the item's class, and that class leaves ``==`` to
    `object`.  Each states what is so and leaves the reader to draw the rest.  Among names a fourth: one that
    reads almost the same (`_near_name`).
    """
    sought, held = roles.sought, roles.held
    names: list[str] = []
    try:
        if nan_operand(item):
            return f"{sought} is a NaN, and one NaN is not equal to another"
        kind = type(item)
        identity: bool | None = None
        for element in searched:
            if type(element) is not kind:
                if reads_as(element, item):
                    types = f"{class_name(type(element))}, not {class_name(kind)}"
                    return f"{held} reads the same as {sought} and is of another type: {types}"
                continue
            if roles.named and kind is str and isinstance(element, str):
                names.append(element)
            if identity is None:
                # a fact about the class, so asked of the first element of it and not of each
                identity = identity_candidate(item, element)
            # asked again past the two reprs, which are code of the class and may change what it compares by
            if identity and _safe_repr(element) == _safe_repr(item) and identity_candidate(item, element):
                return (
                    f"{held} prints the same as {sought}, and their class leaves __eq__ to object,"
                    " which compares by identity"
                )
        if names and isinstance(item, str):
            return _near_name(item, names, held)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None
    return None


_RUNS: Final = re.compile(r"\s+")


def under(line: str | None) -> str:
    """*line* on a line of its own under a sentence, or nothing."""
    return "" if line is None else f"\n{line}"


_INSTANCE_MATCHER: Final = "the matcher for an instance of a class is match.is_instance_of"


def matcher_for_a_class(given: object) -> str:
    """What follows the refusal of *given* where a matcher was wanted, where it is a class `type` itself built.

    Such a class takes an instance check and cannot refuse one, which a typed dict or a plain protocol does.
    """
    return f": {_INSTANCE_MATCHER}" if type(given) is type else ""


def class_in_spec(leaves: Iterable[tuple[str, object, object]]) -> str | None:
    """One line for the first place where a spec holds a class and the value there is an instance of it.

    A class in a spec is a value like any other, compared with ``==``.  Said where `match.is_instance_of` takes the
    value on the class tree alone: the class is built by `type` itself, so its instance check is the base one, and
    it stands in the tree of the value's class, so neither is asked anything.
    """
    for where, value, literal in leaves:
        if _an_instance_by_the_tree(value, literal):
            return f"at <{where}> the spec holds a class itself and the value is an instance of it: {_INSTANCE_MATCHER}"
    return None


def _an_instance_by_the_tree(value: object, literal: object) -> bool:
    return type(literal) is type and any(base is literal for base in class_tree(type(value)))


def type_beside_a_class(value: object, literal: object) -> str:
    """What follows a value held against a class it was not found to be an instance of: its type, as the matcher for
    an instance words it.

    A sentence prints a value by its text, so the text ``'7'`` beside the class `int` read ``<7>``.  Nothing where
    `class_in_spec` speaks of the same pair.
    """
    if not issubclass(type(literal), type) or _an_instance_by_the_tree(value, literal):
        return ""
    return f" of type <{class_name(type(value))}>"


def not_at_an_end(value: object, piece: object, *, start: bool, cased: bool = True) -> str | None:
    """One line on why a text does not start with another, or end with it, where one fact says it.

    Four are looked for, the narrowest first, each the relation itself holding once one thing is set aside:
    whitespace at that end of the value, case, whitespace round the text given, and the text held somewhere
    else in the value.  *cased* is whether the assertion minded case: where it did not, the two are read
    lowercased, so case is never the fact found.  Read off exact `str` alone, which runs no code of the values.
    """
    if type(value) is not str or type(piece) is not str:
        return None
    named, edge, side = ("prefix", "starts", "past") if start else ("suffix", "ends", "before")
    holds = str.startswith if start else str.endswith
    text, wanted = (value, piece) if cased else (value.lower(), piece.lower())
    if holds(text, wanted):
        return None
    bare = text.lstrip() if start else text.rstrip()
    if bare != text and holds(bare, wanted):
        gap = text[: len(text) - len(bare)] if start else text[len(bare) :]
        what = "a line break" if gap in ("\n", "\r\n", "\r") else "whitespace"
        return f"the value {edge} with {what}, and {edge} with the {named} {side} it"
    if holds(text.lower(), wanted.lower()):
        return f"the value {edge} with the {named} once case is ignored"
    trimmed = wanted.strip()
    if trimmed and trimmed != wanted and holds(text, trimmed):
        return f"the {named} given starts or ends with whitespace, and the value {edge} with it without that"
    if wanted in text:
        return f"the value holds the {named}, and not at its {'start' if start else 'end'}"
    return None


def not_in_text(value: object, piece: object, *, cased: bool = True) -> str | None:
    """One line on why a text does not hold another, where one fact says it.

    It holds it once case is ignored, or once every run of whitespace is read as one space, which is what a
    line break, a tab, a no-break space and two spaces in a row all come to, or once both are.  *cased* as in
    `not_at_an_end`.  Read off exact `str` alone.
    """
    if type(value) is not str or type(piece) is not str:
        return None
    text, wanted = (value, piece) if cased else (value.lower(), piece.lower())
    if wanted in text:
        return None
    if wanted.lower() in text.lower():
        return "the value holds it once case is ignored"
    # a run is read as one space and not taken out: stripped, a text given with a space before it was held
    spaced_text, spaced = _RUNS.sub(" ", text), _RUNS.sub(" ", wanted)
    if spaced in spaced_text:
        return "the value holds it once every run of whitespace is read as one space"
    if spaced.lower() in spaced_text.lower():
        return "the value holds it once case is ignored and every run of whitespace is read as one space"
    return None


def but_for_whitespace(value: object, other: object) -> str | None:
    """One line on two texts that are not equal without regard to case, where whitespace alone holds them apart.

    It names the whitespace as `is_equal_to` does for two texts.  Read off exact `str` alone.
    """
    if type(value) is not str or type(other) is not str:
        return None
    apart = _accounted([(value.lower(), other.lower())], _OF_SPACE)
    return None if apart is None else f"the two are equal without regard to case but for {apart}"


def but_for_case(value: object, other: object) -> str | None:
    """One line on two texts that are not equal ignoring whitespace, where case alone holds them apart.

    Read off exact `str` alone.
    """
    if type(value) is not str or type(other) is not str:
        return None
    if "".join(value.split()).lower() == "".join(other.split()).lower():
        return "the two are equal ignoring whitespace once case is ignored too"
    return None


def _own_datetime(standing: type) -> type[datetime.datetime]:
    """The standard library's datetime under the class that stands at `datetime.datetime`.

    A library that freezes time puts a class of its own at that name, made of the real one.  The real one is
    the last to write `utcoffset` on the line of bases the class takes its layout from (`__base__`).  Not the
    last of the whole tree: a mixin that writes one comes after it there.  And not the class of an instance
    the class hands out: its `min` may be an instance of the class itself.
    """
    found, base = standing, standing
    while base is not None:
        if "utcoffset" in class_namespace(base):
            found = base
        base = type.__dict__["__base__"].__get__(base)
    return cast("type[datetime.datetime]", found)


# in a tuple: such a library also rewrites each attribute of a module that is the real class
_MOMENT: Final = (_own_datetime(datetime.datetime),)
_ORDERED_BY: Final = ("__lt__", "__le__", "__gt__", "__ge__")


def out_of_order(value: object, other: object, *, before: bool, strict: bool) -> str | None:
    """One line on a moment that is not before another, or not after it: how far on the other side it is.

    Said by the four assertions of dates and by the four single relations of numbers, which take two datetimes
    too.  *before* is the side the assertion asked for, and *strict* whether the same moment fails it as well.  The
    distance is `datetime.datetime`'s own subtraction, exact to the microsecond.  Where that is only the
    distance between two readings of one clock (`_time_between`), the line says so.
    """
    measured = _time_between(value, other, _ORDERED_BY)
    if measured is None:
        return None
    apart, moments = measured
    if not apart:
        return _same(moments) if strict else None
    late = apart > datetime.timedelta()
    if late is not before:
        return None
    side = "after" if late else "before"
    if moments:
        return f"the value is {abs(apart)} {side} the moment given"
    return f"the value reads {abs(apart)} {side} the moment given on the clock the two share"


def apart_in_time(value: object, other: object, tolerance: object, *, close: bool) -> str | None:
    """One line on two moments held against a tolerance: how far apart they are, and how far that is from it.

    *close* is what the assertion asked for.  Measured as `out_of_order` measures.  Nothing is said of a pair
    found close whose distance is past the tolerance: a window round either moment reached the other where the
    distance did not.  The tolerance is read where it is exactly a `datetime.timedelta`, and the assertion has
    refused one below nothing.
    """
    measured = _time_between(
        value, other, (*_ORDERED_BY, "__eq__", "__sub__", "__rsub__", "__add__", "__radd__", "__float__")
    )
    if measured is None or type(tolerance) is not datetime.timedelta:
        return None
    apart, moments = measured
    distance = abs(apart)
    if not distance:
        return None if close else _same(moments)
    told = f"the two are {distance} apart" if moments else f"the two read {distance} apart on the clock they share"
    if close:
        return f"{told}, {distance - tolerance} more than the tolerance" if distance > tolerance else None
    if distance > tolerance:
        return None
    if distance == tolerance:
        return f"{told}, which is the tolerance"
    return f"{told}, {tolerance - distance} less than the tolerance"


def _same(moments: bool) -> str:
    return "the two are the same moment" if moments else "the two read the same on the clock they share"


# every setting named: one left out is copied from `decimal.DefaultContext`, which a caller may have changed
_SHOWN_EXACTLY: Final = decimal.Context(
    prec=34,
    rounding=decimal.ROUND_HALF_EVEN,
    Emin=decimal.MIN_EMIN,
    Emax=decimal.MAX_EMAX,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[decimal.Inexact, decimal.Overflow, decimal.InvalidOperation],
)
_SHOWN_ROUGHLY: Final = decimal.Context(
    prec=12,
    rounding=decimal.ROUND_HALF_EVEN,
    Emin=decimal.MIN_EMIN,
    Emax=decimal.MAX_EMAX,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[],
)

_SIDE: Final = {
    "is_less_than": "before",
    "is_less_than_or_equal_to": "before",
    "is_greater_than": "after",
    "is_greater_than_or_equal_to": "after",
    "is_before": "before",
    "is_before_or_equal_to": "before",
    "is_after": "after",
    "is_after_or_equal_to": "after",
}
"""The single bounds, by the side of the bound given each asks for."""


def passed_by(operation: str, value: object, parameters: Mapping[str, object], *, negated: bool) -> str | None:
    """How far a value that passed was from the bound it was held against, or ``None`` where that is no distance.

    Said for the bounds a threshold is written with: the four single relations of numbers and of dates, a range,
    and closeness.  The distance is taken between the values the comparison compared, exactly: a float is the
    binary number it holds, so ``5 - 4.9`` is ``0.0999999999999996447...``, shown as ``about 0.1``.  A distance
    is printed exactly where 34 digits hold it and rounded to twelve, with ``about``, where they do not.

    Only operands whose class is exactly a number of the standard library, a ``datetime``, a ``date`` or a
    ``timedelta`` are measured, so no code of anybody's runs.  Python orders those exactly, so the side a distance
    falls on is the side the verdict found.  A number whose exact ratio has a numerator or a denominator longer than
    3322 bits is not measured, so neither is one larger than about ``10**1000`` or smaller than about ``10**-1000``,
    nor a `Decimal` written with more than a thousand digits: a pure-Python `decimal` refuses to read so many.
    """
    if operation in _SIDE:
        return _from_bound(value, parameters.get("other"), _SIDE[operation])
    if operation in ("is_between", "is_not_between"):
        return _in_range(value, parameters.get("low"), parameters.get("high"))
    if operation in ("is_close_to", "is_not_close_to"):
        close = (operation == "is_close_to") is not negated
        return _near(value, parameters.get("other"), parameters.get("tolerance"), parameters.get("rel"), close=close)
    return None


def _exact(number: object) -> fractions.Fraction | None:
    """*number* as the exact rational it is, or ``None`` for anything else, a non-finite or an outsized number."""
    kind = type(number)
    if kind is int:
        whole = cast("int", number)
        return fractions.Fraction(whole) if int.bit_length(whole) <= 3322 else None
    if kind is float:
        return None if _non_finite(number) else fractions.Fraction(cast("float", number))
    if kind is decimal.Decimal:
        held = cast("decimal.Decimal", number)
        if _non_finite(held) or not -1000 <= decimal.Decimal.adjusted(held) <= 1000:
            return None
        if len(decimal.Decimal.as_tuple(held).digits) > 1000:
            return None
        return _bounded(fractions.Fraction(held))
    if kind is fractions.Fraction:
        return _bounded(cast("fractions.Fraction", number))
    return None


def _bounded(ratio: fractions.Fraction) -> fractions.Fraction | None:
    """*ratio*, unless its numerator or denominator is longer than 3322 bits, past about ``10**1000``."""
    return ratio if max(int.bit_length(ratio.numerator), int.bit_length(ratio.denominator)) <= 3322 else None


def _minus(left: object, right: object) -> fractions.Fraction | None:
    """*left* minus *right*, exactly, where both are numbers `_exact` reads."""
    first, second = _exact(left), _exact(right)
    if first is None or second is None:
        return None
    return first - second


def _durations(left: object, right: object) -> tuple[int, datetime.timedelta] | None:
    """Which way *left* lies from *right*, and how far, for two durations or two dates of exactly the standard classes.

    The size is the larger less the smaller: `-timedelta.max` is past the range though `timedelta.max` is not.
    """
    kinds = (type(left), type(right))
    if kinds != (datetime.timedelta, datetime.timedelta) and kinds != (datetime.date, datetime.date):
        return None
    first, second = cast("datetime.timedelta", left), cast("datetime.timedelta", right)
    larger, smaller, sign = (first, second, 1) if first >= second else (second, first, -1)
    try:
        return (sign if larger != smaller else 0), larger - smaller
    except OverflowError:
        # two durations at the two ends of the range compare, and their distance is past it
        return None


def _from_bound(value: object, bound: object, side: str) -> str | None:
    """Where *value* stands against one bound: how far below or above it, or before or after it.

    *side* is the one the assertion asked for, which `out_of_order` takes as the side to say nothing on.  Numbers
    are asked first, being what a threshold usually is: the moments' reading looks at the classes, which cost a
    passing line half its time when asked first.
    """
    difference = _minus(value, bound)
    words = ("above", "below")
    if difference is None:
        moment = out_of_order(value, bound, before=side == "after", strict=True) or out_of_order(
            value, bound, before=side != "after", strict=True
        )
        if moment is not None:
            return moment
        apart = _durations(value, bound)
        if apart is None:
            return None
        sign, size = apart
        if type(bound) is datetime.date:
            given, shown, words = "date", f"{size.days} day{'s' if size.days != 1 else ''}", ("after", "before")
        else:
            given, shown = "duration", str(size)
    else:
        sign, given, shown = (difference > 0) - (difference < 0), "number", _shown(abs(difference))
    if not sign:
        return f"the value is the {given} given"
    return f"the value is {shown} {words[0] if sign > 0 else words[1]} the {given} given"


def _shown(number: fractions.Fraction) -> str:
    """*number* in decimal: exactly where 34 digits hold it, else rounded to twelve and said to be."""
    numerator, denominator = decimal.Decimal(number.numerator), decimal.Decimal(number.denominator)
    try:
        written, about = _SHOWN_EXACTLY.divide(numerator, denominator), ""
    except decimal.Inexact:
        written, about = _SHOWN_ROUGHLY.divide(numerator, denominator), "about "
    plain = written.normalize(_SHOWN_ROUGHLY if about else _SHOWN_EXACTLY)
    # asked before formatting: a positional `1E+999` is a thousand characters. `E`, as `str()` reads the ambient context
    return about + format(plain, "f" if -12 <= plain.adjusted() <= 20 else "E")


def _in_range(value: object, low: object, high: object) -> str | None:
    """Where *value* stands against a range of numbers: how far within each end, or how far past the nearer."""
    from_low, to_high = _minus(value, low), _minus(high, value)
    if from_low is None or to_high is None:
        return None
    if from_low < 0 or to_high < 0:
        if from_low < 0:
            return f"the value is {_shown(-from_low)} below the low end"
        return f"the value is {_shown(-to_high)} above the high end"
    if not from_low:
        return "the value is the low end"
    if not to_high:
        return "the value is the high end"
    return f"the value is {_shown(from_low)} above the low end and {_shown(to_high)} below the high end"


def _near(value: object, other: object, tolerance: object, rel: object, *, close: bool) -> str | None:
    """How far apart two values that passed a closeness are, against what they were allowed.

    Either allowance holding is enough, so the larger is the one measured against.  Nothing is said where the
    exact distance disagrees with the verdict: a window round either value reached the other where it did not.
    """
    if isinstance(tolerance, datetime.timedelta) and rel is None:
        return apart_in_time(value, other, tolerance, close=not close)
    difference, allowed = _minus(value, other), _allowance(other, tolerance, rel)
    if difference is None or allowed is None:
        return None
    distance = abs(difference)
    spare = allowed - distance
    if (spare >= 0) is not close:
        return None
    if not distance:
        return "the two are equal"
    told = "the tolerance" if rel is None else f"the allowance of {_shown(allowed)}"
    if not spare:
        return f"the two are {_shown(distance)} apart, which is {told}"
    if close:
        return f"the two are {_shown(distance)} apart, {_shown(spare)} less than {told}"
    return f"the two are {_shown(distance)} apart, {_shown(-spare)} more than {told}"


def _allowance(other: object, tolerance: object, rel: object) -> fractions.Fraction | None:
    """The larger of the two allowances asked, exactly, or ``None`` where either given is past measuring.

    One past measuring, an infinite one among them, would be the larger, so no smaller one stands in for it.
    """
    absolute = _exact(tolerance) if tolerance is not None else None
    if tolerance is not None and absolute is None:
        return None
    if rel is None:
        return absolute
    scale, size = _exact(rel), _exact(other)
    if scale is None or size is None:
        return None
    relative = scale * abs(size)
    return relative if absolute is None or relative > absolute else absolute


def _time_between(value: object, other: object, asked: tuple[str, ...]) -> tuple[datetime.timedelta, bool] | None:
    """*value* minus *other* by `datetime.datetime`'s own subtraction, and whether that is the time between them.

    Read only for two whose classes leave *asked* to the base type: a class that writes one of those operators
    made the verdict its own way, on what it holds past the microsecond or anywhere else.

    Two that share one zone object, or have none, the base type compares and subtracts on their wall clocks,
    asking the zone nothing.  That is the time between the two where there is no zone, or where the zone gives
    both one offset.  Across a change of its clocks it is not: four hours read off a clock that went back for
    five that passed, and the two readings of the repeated hour found equal.  Then, and for a zone that is not
    asked, the answer is ``False`` and the line speaks of the clock the two share.

    A zone is asked only where it is one of the standard library's own (`_own_zone`), since a line read past the
    verdict cannot know what another zone's code told the verdict.  Two in different zones are measured as
    moments, which asks both, so a pair with a zone from elsewhere among them gets nothing.
    """
    moment = _MOMENT[0]
    if not isinstance(value, moment) or not isinstance(other, moment):
        return None
    try:
        if not (_left_to_datetime(type(value), asked) and _left_to_datetime(type(other), asked)):
            return None
        zone, other_zone = moment.tzinfo.__get__(value), moment.tzinfo.__get__(other)
        if zone is not other_zone:
            if not (_own_zone(zone) and _own_zone(other_zone)):
                return None
            return moment.__sub__(value, other), True
        apart = moment.__sub__(value, other)
        if zone is None:
            return apart, True
        if not _own_zone(zone):
            return apart, False
        offset = moment.utcoffset(value)
        one = offset is not None and datetime.timedelta.__eq__(offset, moment.utcoffset(other)) is True
        return apart, one
    except Exception:  # a naive moment against an aware one refuses to subtract, and no line outranks the failure
        return None


def _own_zone(zone: object) -> bool:
    """Whether *zone* is none, or one of the standard library's own, whose offset its code alone answers.

    The class of `zoneinfo` is read where it is loaded and not imported: no zone of its class exists without
    it, and the import costs 4.9 ms, measured, which every importer of the library would pay.  It is read off
    the two modules that implement it and not off `zoneinfo.ZoneInfo`: that is a name a test may put a class
    of its own at, and what such a class says of itself, its name and its module, is the class's to say.
    """
    kind = type(zone)
    if zone is None or kind is datetime.timezone:
        return True
    implemented_in = ("_zoneinfo", "zoneinfo._zoneinfo")
    return any(kind is getattr(sys.modules.get(name), "ZoneInfo", None) for name in implemented_in)


def _left_to_datetime(klass: type, asked: tuple[str, ...]) -> bool:
    """Whether *klass* is `datetime.datetime`, or leaves every operator in *asked* to it, read off its tree.

    The keys are read before any name is looked up: a key of a class of its own answers a lookup with its code.
    """
    if klass is _MOMENT[0]:
        return True
    if not _plainly_keyed(klass):
        return False
    for base in class_tree(klass):
        if base is _MOMENT[0]:
            return True
        written = class_namespace(base)
        if any(name in written for name in asked):
            return False
    return False


_JOINTS: Final = re.compile(r"[\s_.\-]+")
"""What joins the words of a name: a space, an underscore, a dot, a hyphen."""


def _near_name(name: str, names: Sequence[str], held: str) -> str | None:
    """One line on a name among *names* that reads almost as *name*, which was asked for and is not there.

    Two facts and one likeness, the narrowest first.  A name is the same once both are lowercased.  A name is
    the same once both are lowercased and what joins their words is taken out, ``userId`` beside ``user_id``.
    One spelling alone is almost the same (`_almost`), and the names of that spelling are named, the first
    three of them and how many more: two that differ only in case or joints are one spelling.  The last is a
    likeness and is worded as one: which name was meant is the reader's to say, and where two spellings come
    that close nothing is said.

    Read off exact `str` alone, which runs no code of the values.  By ``lower()`` and not ``casefold()``, which
    calls ``ß`` and ``ss`` one text, a difference that is not of case.  The likeness is looked for only where
    the name asked for and the name held are of a hundred characters at most, as they were written: past that
    it is no name, and the search is quadratic.
    """
    others = [each for each in names if each != name]
    lowered = name.lower()
    alike = [each for each in others if each.lower() == lowered]
    if alike:
        return f"{held} reads the same but for its case: {_listed(alike)}"
    plain = _JOINTS.sub("", lowered)
    if not plain:
        return None
    joined: dict[str, list[str]] = {}
    for each in others:
        joined.setdefault(_JOINTS.sub("", each.lower()), []).append(each)
    if plain in joined:
        return f"{held} reads the same but for how its words are joined: {_listed(joined[plain])}"
    if len(name) > 100:
        return None
    # one matcher for the name: built for every key, the ratio cost a failure over 200 keys 0.8 ms
    texts = difflib.SequenceMatcher(None, b=plain, autojunk=False)
    short = (each for each, held_as in joined.items() if each and all(len(key) <= 100 for key in held_as))
    close = [each for each in short if _almost(plain, each, texts)]
    if len(close) == 1:
        return f"{held} is spelled almost the same: {_listed(joined[close[0]])}"
    return None


def _almost(one: str, other: str, texts: difflib.SequenceMatcher[str]) -> bool:
    """Whether two names are one slip apart, or nearly one text.

    A slip is two neighbouring letters swapped, one letter too many, or one too few.  A letter in place of
    another is not one: that is how two words differ, ``date`` and ``data``.  Nearly one text is a `difflib`
    ratio of 0.85, which a long name reaches with a few letters dropped or replaced, ``created`` beside
    ``created_at`` and seventeen of one letter beside twenty.  Measured on 54 labelled typos and 46 pairs of
    unrelated key names: 52 named and 6, four of the six a singular beside its plural.  The ratio alone named
    49 and 5 at this floor, and 52 and 9 at 0.8.  *texts* holds *one* and is asked the ratio last, past its
    two upper bounds.
    """
    if len(one) == len(other):
        apart = [index for index in range(len(one)) if one[index] != other[index]]
        if (
            len(apart) == 2
            and apart[1] == apart[0] + 1
            and one[apart[0]] == other[apart[1]]
            and one[apart[1]] == other[apart[0]]
        ):
            return True
    elif abs(len(one) - len(other)) == 1:
        shorter, longer = sorted((one, other), key=len)
        parted = next((index for index in range(len(shorter)) if shorter[index] != longer[index]), len(shorter))
        if longer[parted + 1 :] == shorter[parted:]:
            return True
    texts.set_seq1(other)
    return texts.real_quick_ratio() >= 0.85 and texts.quick_ratio() >= 0.85 and texts.ratio() >= 0.85


def _listed(names: Sequence[str]) -> str:
    shown = ", ".join(f"<{_capped(each)}>" for each in names[:3])
    return shown if len(names) <= 3 else f"{shown} and {len(names) - 3} more"


def _beside_a_nan(entries: Sequence[DiffEntry], *, comparators: bool) -> str:
    """The NaN fact, and under it what is said of a pair no NaN takes part in that prints the same on both sides."""
    others = [
        (entry.actual, entry.expected)
        for entry in entries
        if entry.absent is None and not (nan_operand(entry.actual) or nan_operand(entry.expected))
    ]
    unseen = _unseen(others, comparators=comparators)
    return _NAN_FACT if unseen is None else f"{_NAN_FACT}\n{unseen}"


def _prints_alike(left: object, right: object) -> bool:
    """Whether a row of these two reads the same on both sides: one class, or two nothing tells apart, one repr."""
    kind = type(left)
    if kind is type(right) and kind in _PRINTED_AS_HELD:
        return left == right
    return _class_names(left, right) is None and _safe_repr(left) == _safe_repr(right)


def _unseen(pairs: Sequence[tuple[object, object]], *, comparators: bool) -> str | None:
    """What to say of pairs that print the same on both sides and are one class, or ``None`` where none does.

    Such a row names no difference a reader can see, and nothing above accounted for it.  Where no comparator
    took part and every one of them is two instances of a class that leaves ``==`` to `object`, that is the
    reason.  Otherwise the reason is in the comparison itself, a comparator or an ``__eq__`` of the value's
    own, and the line says what is known: the repr does not show it, and which attributes of the two differ
    where they hold any.  Asked of every pair: how many rows a diff prints is the renderer's to decide.

    The identity line here is not the top pair's.  That one speaks of the two values compared, and is asked
    before they are.  A pair inside has no before short of walking both values on every passing comparison
    (23 times the cost of one over 200 rows), so its line speaks of the row and of the class as it stands now.
    """
    alike = [(left, right) for left, right in pairs if _prints_alike(left, right)]
    if not alike:
        return None
    if not comparators and all(identity_candidate(left, right) for left, right in alike):
        return _UNSEEN_IDENTITY_FACT
    names: dict[str, None] = {}
    for left, right in alike:
        _attributes_apart(left, right, names)
        if len(names) > 5:
            break
    if not names:
        return _UNSEEN_FACT
    shown = list(names)
    return f"{_UNSEEN_FACT} (attributes that differ: {', '.join(shown[:5])}{', ..' if len(shown) > 5 else ''})"


def _attributes_apart(left: object, right: object, known: dict[str, None]) -> None:
    """Add to *known* the attributes two values hold that differ between them, up to the six a line can use.

    An attribute whose comparison raises is left out: nothing is known of it.
    """
    try:
        held, other = vars(left), vars(right)
        for name in (*held, *(name for name in other if name not in held)):
            if name not in held or name not in other or _held_apart(held[name], other[name]):
                known[_safe_str(name)] = None
                if len(known) > 5:
                    return
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return


def _held_apart(one: object, other: object) -> bool:
    try:
        return not equals(one, other)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False


def _fields_of(value: object) -> dict | None:
    """A dataclass, attrs instance or pydantic-style model as its fields, read as its ``==`` reads them.

    Read field by field, a field ``==`` leaves out kept the hint away from a payload that matched, and so
    did a nested object against the nested mapping it was built from.
    """
    if (
        is_model_dump_object(value)
        or is_attrs_instance(value)
        or (dataclasses.is_dataclass(value) and not isinstance(value, type))
    ):
        return comparable_fields(value)
    return None


def identity_candidate(left: object, right: object) -> bool:
    """Whether ``==`` between these two comes down to identity, asked *before* the comparison runs.

    Two separate instances of a type that leaves ``__eq__`` to ``object`` are never equal, whatever they
    hold.  That is a fact about the type rather than about what the two hold, which is the only claim worth
    making: state can live in a slot, in a descriptor's own table or in a C field, and a line that promised
    to have read all of it would be promising more than any reading can deliver.  It is said of two of one
    type only: a value of another type may answer the reflected comparison its own way.

    Three details make the answer trustworthy, and each was put here by a case that defeated the one
    before it.  It is asked before the comparison, because a type may rewrite its own ``__eq__`` while
    answering one, and a question asked afterwards would be answered by the type it left behind.  It
    reads no attribute of the class, not even through `type.__getattribute__`: that runs a descriptor
    the class holds under the name, and one that installs an equality while being asked failed a pair
    its own ``==`` held equal.  And what it reads is the class tree's own namespaces, in the order the
    tree has them, the way `slot_tp_richcompare` reads them, off the slots of `type`, which a metaclass
    cannot spell.  The tree is the real one: a metaclass's own ``mro()`` can put another class first, and
    that class's equality is then the one ``==`` runs.

    ``None`` is an answer: a class that writes ``__eq__ = None`` has said what its equality is.  A tree in
    which no class writes one, which reassigning ``__bases__`` under such a metaclass can leave behind, is
    no claim of identity.  A list and a tuple are answered before any namespace is read.  Scalars reach
    none of it: their comparison returns before this is asked.

    One thing a namespace can still run: a key of a class of its own, a `str` subclass, that compares itself
    and may answer one lookup one way and the next another.  Identity is therefore claimed only of a tree whose
    namespaces hold exact `str` keys alone (`_plainly_keyed`), which is read where the claim is about to be
    made and nowhere else: a tree that writes an equality of its own never pays for it.

    The first class of the tree answers for a type that writes its equality itself, at 105 ns where the
    look through the class it replaces took 76.  One that inherits it pays about 50 ns more a level.

    ``__ne__`` is not asked about: the comparison a failing assertion runs is ``actual == expected``, so a
    type defining only ``__ne__`` still compares by identity.
    """
    try:
        klass = type(left)
        # one object against itself is equal under identity too, so a failure can never be about that
        if left is right or klass is not type(right) or klass is list or klass is tuple:
            return False
        for base in class_tree(klass):
            written = class_namespace(base)
            if "__eq__" in written:
                return written["__eq__"] is _OBJECT_EQUALITY and _plainly_keyed(klass)
    except Exception:  # a key of a class of its own raised from its ``__eq__``: no claim, and a failure is on the way
        return False
    return False


def _plainly_keyed(klass: type) -> bool:
    """Whether every namespace of *klass*'s tree holds exact `str` keys alone, so a lookup in it ran no code."""
    return all(type(key) is str for base in class_tree(klass) for key in class_namespace(base))


def _fields_match(left: object, right: object) -> bool:
    """Whether one side is an object whose fields are exactly the other side's mapping."""
    try:
        for obj, other in ((left, right), (right, left)):
            fields = _fields_of(obj)
            if fields is not None and is_mapping_like(other) and fields == dict(other):
                return True
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    return False


def _same_values(pairs: Sequence[tuple[object, object]]) -> bool:
    """Whether the differing values are the same on both sides, sitting in different places.

    Counted rather than sorted wherever the values are hashable, which is the common case and the one
    that used to be expensive: sorting by ``repr`` calls ``repr`` on every value on both sides, and a
    failure over a two-thousand element sequence paid four thousand of them for an answer that is
    almost always no.  The sort stays as the fallback, since it is what handles values that are
    unhashable or not orderable against each other.
    """
    try:
        return Counter(value for value, _ in pairs) == Counter(value for _, value in pairs)
    except TypeError:  # unhashable values, which only the slower route can compare
        pass
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False
    try:
        return sorted((value for value, _ in pairs), key=repr) == sorted((value for _, value in pairs), key=repr)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return False


def _named(pairs: Sequence[tuple[object, object]]) -> str | None:
    """The narrowest set of steps that accounts for every pair, worded, or ``None``."""
    accounted = _accounted(pairs, _STEPS)
    return None if accounted is None else f"every difference here is one of {accounted}"


def _accounted(
    pairs: Sequence[tuple[object, object]], steps: Sequence[tuple[Callable[[object], object], _Label]]
) -> str | None:
    """What accounts for every pair, of *steps* and of whitespace of any kind and amount, the narrowest first.

    One step, then two.  Then the kind or amount of whitespace, alone and beside one step: it takes in line
    endings and surrounding whitespace, so said first it would stand in for the two narrower facts.

    Nothing is asked where no step reads the first pair (`_unread_by_any_step`): every step has to account for
    it, and asking all nineteen was most of what a failure of two numbers spent here.
    """
    if _unread_by_any_step(pairs[0]):
        return None
    for step, label in steps:
        if _explains(pairs, (step,)):
            return _worded(label, pairs)
    # only now pairs of steps: `"a\r\nb "` against `"a\nb"` needs both, and neither alone equalises it
    for index, (first_step, first_label) in enumerate(steps):
        for second_step, second_label in steps[index + 1 :]:
            if _explains(pairs, (first_step, second_step)):
                return f"{_worded(first_label, pairs)} and {_worded(second_label, pairs)}"
    if _explains(pairs, (_spaced,)):
        return "the kind or amount of whitespace"
    for step, label in steps:
        if step not in (_newlines, _stripped) and _explains(pairs, (step, _spaced)):
            return f"{_worded(label, pairs)} and the kind or amount of whitespace"
    return None


def _unread_by_any_step(pair: tuple[object, object]) -> bool:
    """Whether neither side of *pair* is a text, a ``bytes`` or an enum member, which is all a step reads.

    Asked as each step asks it.  Where a value's ``__class__`` is code of its own that raises, the pair is unread
    too: every step would have ended in that same error, and `_explains` counts it as no.
    """
    try:
        return not any(isinstance(side, (str, bytes, enum.Enum)) for side in pair)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return True


def _worded(label: _Label, pairs: Sequence[tuple[object, object]]) -> str:
    """A step's label, letting one that depends on the shape of the pairs decide for itself."""
    return label if isinstance(label, str) else label(pairs)
