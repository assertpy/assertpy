from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, Final, cast

from ._engine._compare import _guarded_equal
from ._engine._diff import _sub_diff_entries
from ._engine._equality import fields_held, mapping_shaped
from ._engine._membership import (
    _hash_safe,
    _index,
    has_duplicates,
    is_searchable,
    is_walkable,
    missing_items,
    occurrences,
    only_faults,
    repeated_counts,
    searchable,
)
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import REFUSALS, equals, lookup, may_broadcast, member
from ._engine._pairing import completed_pairing
from ._engine._path import _ROOT
from ._engine._require import argument, refuse, require_type, sized_len, verdict
from ._hints import Roles, not_found, not_in_text, reads_as, under
from .errors import DiffEntry, DiffResult, _capped, _capped_format, _capped_repr, _safe_repr, _told_apart
from .matchers import _is_matcher

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


def _surplus(counted: Sequence[tuple[object, int]]) -> list[DiffEntry]:
    """One `DiffEntry` per copy too many, in the shape every other containment failure uses.

    A count paired against a value was the first shape, and the renderer showed nothing for it: only an
    entry saying which side is missing something reaches the extra/missing groups.  A repeat is a copy
    the expectation has no room for, so it is spelled the same way an unwanted element is, and the
    number of entries is how many copies over.
    """
    return [
        DiffEntry(path="duplicated", actual=item, expected=None, absent="expected")
        for item, total in counted
        for _ in range(total - 1)
    ]


def _counted_difference(val_items, given_items):
    """``(extra, missing)`` by `Counter`, or ``None`` where hashing cannot stand in for ``==``.

    A matcher hashes by identity and compares by its predicate, so counting them called a matching item
    missing where the ordered spelling accepted it.  The rule is membership's own.
    """
    if not (_hash_safe(val_items) and _hash_safe(given_items)):
        return None
    try:
        val_counts, given_counts = Counter(val_items), Counter(given_items)
    except TypeError:  # a value refused to hash after all
        return None
    return list((val_counts - given_counts).elements()), list((given_counts - val_counts).elements())


def _sequence_break(values, items, *, answered=False) -> int | None:
    """``None`` where *items* run contiguously in *values*, else how many lined up in the longest run.

    Of the runs that start with room for all of *items*: one that starts too late to fit is `_late_run`'s.
    Asked by ``==``, and *answered* by `equals` once a signalling NaN or an overflowing `numpy` float raised.
    The very object is itself before either is asked, as it is to `in`: a NaN the value holds is found.
    """
    if not items:
        return None
    best_prefix = 0
    first, rest = items[0], range(1, len(items))
    for i in range(len(values) - len(items) + 1):
        held = values[i]
        # the start of a run asked on its own: through the loop below, a search of 200 for 3 cost 16% more
        if not (held is first or (equals(held, first) if answered else held == first)):
            continue
        for j in rest:
            held, wanted = values[i + j], items[j]
            if held is wanted or (equals(held, wanted) if answered else held == wanted):
                continue
            best_prefix = max(best_prefix, j)
            break
        else:
            return None
    return best_prefix


def _late_run(values, items) -> int:
    """How many items lined up in the longest run that starts too late in *values* to fit, for the message alone.

    Left out, a value shorter than the sequence had started no run at all.  Asked once the verdict is settled,
    of elements the verdict never compared: one whose comparison raises costs the count and not the failure.
    """
    best = 0
    try:
        for i in range(max(len(values) - len(items) + 1, 0), len(values)):
            j = 0
            while i + j < len(values) and (values[i + j] is items[j] or equals(values[i + j], items[j])):
                j += 1
            best = max(best, j)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return best
    return best


def _walked_difference(val_items, given_items):
    """``(extra, missing)`` through ``==``, as a maximum pairing of the items held with the items given.

    A first-fit walk alone answered by the order the items were written in: against ``[1, 5]`` it gave
    the 1 to ``match.greater_than(0)`` and found no 1 left for ``1``, though the 5 takes the matcher.  It
    still runs first, in the same order, and settles a pass alone.  What it leaves unpaired is then
    offered every held item a chain of displacements reaches, compared only as that chain asks, and
    never about a pair the walk already asked: an ``==`` that answers once is not asked twice.
    """
    wanted = list(given_items)
    free = list(range(len(wanted)))
    paired: dict[int, int] = {}
    refused: dict[int, set[int]] = {}
    for index, item in enumerate(val_items):
        for at, entry in enumerate(free):
            if wanted[entry] is item or equals(wanted[entry], item):
                paired[index] = free.pop(at)
                break
            refused.setdefault(entry, set()).add(index)
    if free:
        walked = dict(paired)
        accepted: dict[int, list[int]] = {}

        def holders(entry: int) -> list[int]:
            if entry not in accepted:
                one, asked = wanted[entry], refused.get(entry, set())
                accepted[entry] = [
                    index
                    for index, item in enumerate(val_items)
                    if index not in asked and (walked.get(index) == entry or one is item or equals(one, item))
                ]
            return accepted[entry]

        completed_pairing(paired, free, holders)
    taken = set(paired.values())
    return (
        [item for index, item in enumerate(val_items) if index not in paired],
        [one for entry, one in enumerate(wanted) if entry not in taken],
    )


def _multiset_diff_entries(val_items, given_items):
    """Build extra/missing `DiffEntry` rows between two item lists compared as multisets (order ignored)."""
    extra, missing = _counted_difference(val_items, given_items) or _walked_difference(val_items, given_items)
    entries = [
        DiffEntry(path="extra", actual=item, expected=None, absent="expected") for item in sorted(extra, key=_safe_repr)
    ]
    entries.extend(
        DiffEntry(path="missing", actual=None, absent="actual", expected=item)
        for item in sorted(missing, key=_safe_repr)
    )
    return entries


def _as_row(value: object) -> Any:
    """*value* as the keys or fields a closest element is looked for by, or ``None`` where it has neither."""
    return value if mapping_shaped(value, check_values=False) else fields_held(value)


_OF_AN_ITEM: Final = Roles()
_OF_A_KEY: Final = Roles("the key not found", "a key", named=True)


def _why(item: object, values: Iterable[object], roles: Roles = _OF_AN_ITEM) -> str:
    """The line that says why *item* was not found, on a line of its own under the sentence, or nothing."""
    line = not_found(item, values, roles)
    return "" if line is None else f"\n{line}"


def _is_held(item: object, values: object) -> bool:
    """Whether *values* holds *item* after all, asked for a line of a failure: a search that raises says it may."""
    try:
        return member(item, values)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return True


def _why_absent(item: object, values: Iterable[object]) -> str:
    """`_why` for an item a failure names that the collection may still hold out of place: said where it does not."""
    return "" if _is_held(item, values) else _why(item, values)


def _related(mine: object, other: object) -> bool:
    """Whether two values under one key agree: equal, or two plain values of two types that read the same."""
    if _guarded_equal(mine, other):
        return True
    return reads_as(mine, other)


def _closest(item, values, *, item_is_actual=False):
    """The element of *values* most similar to *item*, with its diff entries, or ``None`` when nothing shares
    enough structure to be an actionable 'did you mean' hint.

    Asked of dict-like values and of records, a dataclass, an attrs instance, a named tuple or a model: a list
    of rows is as often one as the other.  Similarity is the fewest differing paths among elements that share
    a key whose values are equal or read the same, so an element that shares no value is not offered and
    ``{"id": 7}`` is offered for ``{"id": "7"}``.  Runs only on a failed assertion, never on the hot path.

    *item_is_actual* is which side of the entries the item is on: ``contains`` looks for what was expected among
    what is held, ``is_in`` and a subset for what is held among what was given.

    Reading a row runs its code, a field of a record or an item of a mapping, and what that raises costs
    the hint and not the failure it was for.
    """
    try:
        return _closest_row(item, values, item_is_actual)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None


def _closest_row(item, values, item_is_actual):
    sought = _as_row(item)
    if sought is None:
        return None
    best = None
    for element in values:
        held = _as_row(element)
        if held is None:
            continue
        shared = ((held[key], *lookup(sought, key)) for key in held)
        if not any(found and _related(mine, other) for mine, found, other in shared):
            continue  # no shared key that agrees -> not related enough to suggest
        actual, expected = (item, element) if item_is_actual else (element, item)
        entries = _sub_diff_entries(actual, expected, _ROOT, config=None)
        # an element the walk finds nothing under, two records of a class with no equality, names no difference
        if entries and (best is None or len(entries) < len(best[1])):
            best = (element, entries)
    return best


def _differences(entries, limit=3):
    """A compact 'path (actual != expected)' summary of the closest element's differences."""
    parts = ["{} ({} != {})".format(entry.path, *_two_sides(entry)) for entry in entries[:limit]]
    if len(entries) > limit:
        parts.append(f"and {len(entries) - limit} more")
    return ", ".join(parts)


def _two_sides(entry: DiffEntry) -> tuple[str, str]:
    """Both sides of one difference as text, a side that is not there named as such: its ``None`` read as a value."""
    if entry.absent == "actual":
        return "<missing>", _safe_repr(entry.expected)
    if entry.absent == "expected":
        return _safe_repr(entry.actual), "<missing>"
    return _told_apart(_safe_repr(entry.actual), _safe_repr(entry.expected), entry.actual, entry.expected)


def _one_not_found(
    missing: Sequence[object],
    candidates: Iterable[object],
    *,
    noun: str | None = "element",
    item_is_actual: bool = False,
    roles: Roles = _OF_AN_ITEM,
    searched: Iterable[object] | None = None,
) -> str:
    """What a membership failure says of the one item it did not find: the nearest row there is, and why not it.

    Nothing for several items, each of which would need its own, and nothing for a matcher, which is no item.
    *noun* is what the assertion calls a candidate, or ``None`` where a nearest one is not looked for.  The line
    is asked for last, past everything the sentence prints: printing runs code of the values.  It looks among
    *searched* where that is more than the candidates for the nearest row.
    """
    if len(missing) != 1 or _is_matcher(missing[0]):
        return ""
    item = missing[0]
    nearest = ""
    closest = None if noun is None else _closest(item, candidates, item_is_actual=item_is_actual)
    if closest is not None:
        element, entries = closest
        nearest = f" Closest {noun} <{_capped_format(element)}> differs at {_differences(entries)}."
    return nearest + _why(item, candidates if searched is None else searched, roles)


def _lone_pair(extra: Sequence[object], missing: Sequence[object]) -> tuple[str, str] | None:
    """One element nobody asked for and one item not found, each as it is printed, told apart by class where the
    two print the same.  ``None`` for any other count: a list of several is printed as a list."""
    if len(extra) != 1 or len(missing) != 1:
        return None
    shown = _told_apart(_capped_format(extra[0]), _capped_format(missing[0]), extra[0], missing[0])
    return f"<{shown[0]}>", f"<{shown[1]}>"


def _unmatched(entries: Sequence[DiffEntry]) -> tuple[list[object], list[object]]:
    """The ``(extra, missing)`` a multiset diff holds, as the values themselves."""
    extra = [entry.actual for entry in entries if entry.absent == "expected"]
    return extra, [entry.expected for entry in entries if entry.absent == "actual"]


def _both_ways(extra: Sequence[object], missing: Sequence[object], values: object, items: Sequence[object]) -> str:
    """What is said where a collection was to hold the items given and nothing else.

    Of the one item it lacks: its nearest row among the elements nobody asked for where there are any, which is
    named as that, and the line among every element.  Or, where it lacks none, of the one element nobody asked
    for, against the items given.

    Counted, a collection can be short of an item it has, or hold one it was asked for once too often: "not
    found" and "not expected" would be false of it, so there the two counts are said instead (`_counted`).
    """
    held = cast("Iterable[object]", values)
    if missing:
        short = _the_one(missing)
        if short is not _SEVERAL and _is_held(short, held):
            return _counted(short, held, items, short=True)
        if extra:
            return _one_not_found(missing, extra, noun="unexpected element", searched=held)
        return _one_not_found(missing, held)
    over = _the_one(extra)
    if over is not _SEVERAL and _is_held(over, items):
        return _counted(over, held, items, short=False)
    return _one_not_found(extra, items, noun=None, roles=Roles("the element not expected", "a given item"))


_SEVERAL: Final = object()


def _the_one(entries: Sequence[object]) -> object:
    """The item every one of *entries* is, or `_SEVERAL` where they are of more than one, or there are none."""
    try:
        if entries and all(entry is entries[0] or equals(entry, entries[0]) for entry in entries[1:]):
            return entries[0]
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return _SEVERAL
    return _SEVERAL


def _counted(item: object, values: Iterable[object], items: Sequence[object], *, short: bool) -> str:
    """How often a collection holds *item* against how often it was asked for, where it is *short* of it or over.

    Counted again for the sentence, past the verdict and past every printing, that of the item included, all
    of which run code of the values: said only where the two counts still show what the verdict found, held
    fewer times than asked for or more.
    """
    shown = _capped_repr(item)
    try:
        held, asked = occurrences(list(values), [item])[0], occurrences(list(items), [item])[0]
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return ""
    if not (0 < held < asked if short else held > asked > 0):
        return ""
    times = [f"{count} time{'' if count == 1 else 's'}" for count in (held, asked)]
    return f" <{shown}> is held {times[0]} and was asked for {times[1]}."


def _value_not_found(mapping: Any, missing: Sequence[object]) -> str:
    """What a failed ``contains_value`` says of the one value not found, among the values read again for it."""
    try:
        held = list(mapping.values())
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return ""
    return _one_not_found(missing, held, noun="value", roles=Roles(held="a value"))


def _entry_not_found(mapping: object, missing: Sequence[dict[Any, Any]]) -> str:
    """What a failed ``contains_entry`` says of the one entry not found: what its key holds, and why not it."""
    if len(missing) != 1:
        return ""
    ((key, wanted),) = missing[0].items()
    try:
        found, held = lookup(mapping, key)
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return ""
    if not found:
        return f" There is no key <{_capped_format(key)}>." + _why(key, cast("Iterable[object]", mapping), _OF_A_KEY)
    reason = _why(wanted, (held,), Roles("the value expected", "the value held"))
    return f" Key <{_capped_format(key)}> holds <{_capped_repr(held)}>.{reason}"


def _pair_why(missing: Sequence[dict[Any, Any]], supersets: Sequence[dict[Any, Any]]) -> str:
    """The line on why the one pair of a mapping no superset holds is not the pair a superset has under its key.

    Nothing where no superset has the key: the pair is missing for that, whatever its value is.
    """
    if len(missing) != 1:
        return ""
    ((key, wanted),) = missing[0].items()
    try:
        held = [superset[key] for superset in supersets if key in superset]
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return ""
    if not held:
        return ""
    return _why(wanted, held, Roles("the value missing", "the value the superset holds under the key"))


class ContainsMixin(_MixinBase):
    """Containment assertions mixin."""

    def contains(self, *items: object) -> Self:
        """Asserts that val contains the given item or items.

        Checks if the collection contains the given item or items using ``in`` operator.

        Args:
            *items: the item or items expected to be contained

        Examples:
            Usage:

                assert_that('foo').contains('f')
                assert_that('foo').contains('f', 'oo')
                assert_that(['a', 'b']).contains('b', 'a')
                assert_that((1, 2, 3)).contains(3, 2, 1)
                assert_that({'a': 1, 'b': 2}).contains('b', 'a')  # checks keys
                assert_that({'a', 'b'}).contains('b', 'a')
                assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the item or items
            TypeError: if val is not a container or iterable

        Note:
            Where one item is not found, the failure says what is nearest to it: the closest row among the elements,
            and on a line under the message why it is not there, where one fact about it says so.

        Tip:
            Use the [`contains_key()`][assertpy.dict.DictMixin.contains_key] alias when working with
            *dict-like* objects to be self-documenting.

        See Also:
            [`contains_ignoring_case()`][assertpy.string.StringMixin.contains_ignoring_case] -
                for case-insensitive string contains
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        # membership is tested once per argument, so a one-shot iterator has to be drained first
        values = searchable(self._drained())
        if not is_searchable(values):
            # left to `in`, Python answers about the operator rather than about the value the assertion was handed
            refuse(self.val, "a container or iterable")
        if len(items) == 1:
            item = items[0]
            if _is_matcher(item):
                if not any(verdict(item.matches(value), subject="the matcher") for value in values):
                    diff = DiffResult(
                        kind="contains",
                        entries=[DiffEntry(path="missing", actual=None, absent="actual", expected=item.describe())],
                    )
                    return self.error(
                        f"Expected <{_capped_format(values)}> to contain item matching {item.describe()}, but did not.",
                        diff=diff,
                        expected=items,
                    )
            elif not member(item, values):
                if mapping_shaped(values):
                    diff = DiffResult(
                        kind="contains",
                        entries=[DiffEntry(path="missing", actual=None, absent="actual", expected=item)],
                    )
                    return self.error(
                        f"Expected <{_capped_format(values)}> to contain key <{_capped_format(item)}>, but did not."
                        f"{_why(item, values, _OF_A_KEY)}",
                        diff=diff,
                        expected=items,
                    )
                closest = _closest(item, values)
                if closest is not None:
                    element, entries = closest
                    return self.error(
                        f"Expected <{_capped_format(values)}> to contain item <{_capped_format(item)}>, but did not."
                        f" Closest element <{_capped_format(element)}> differs at {_differences(entries)}."
                        f"{_why(item, values)}",
                        diff=DiffResult(kind="contains", entries=entries),
                        expected=items,
                    )
                diff = DiffResult(
                    kind="contains", entries=[DiffEntry(path="missing", actual=None, absent="actual", expected=item)]
                )
                in_text = type(values) is str and type(item) is str
                return self.error(
                    f"Expected <{_capped_format(values)}> to contain item <{_capped_format(item)}>, but did not."
                    f"{under(not_in_text(values, item)) if in_text else _why(item, values)}",
                    diff=diff,
                    expected=items,
                )
        else:
            missing = missing_items(values, items, _is_matcher)
            if missing:
                missing_desc = [
                    missing_item.describe() if _is_matcher(missing_item) else missing_item for missing_item in missing
                ]
                diff = DiffResult(
                    kind="contains",
                    entries=[
                        DiffEntry(path="missing", actual=None, absent="actual", expected=missing_item)
                        for missing_item in missing_desc
                    ],
                )
                if mapping_shaped(values):
                    sentence = (
                        f"Expected <{_capped_format(values)}> to contain keys {self._fmt_items(items)},"
                        f" but did not contain key{'' if len(missing) == 1 else 's'} {self._fmt_items(missing_desc)}."
                    )
                    said = _one_not_found(missing, values, noun=None, roles=_OF_A_KEY)
                else:
                    sentence = (
                        f"Expected <{_capped_format(values)}> to contain items {self._fmt_items(items)},"
                        f" but did not contain {self._fmt_items(missing_desc)}."
                    )
                    said = _one_not_found(missing, values)
                return self.error(sentence + said, diff=diff, expected=items)
        return self

    def does_not_contain(self, *items: object) -> Self:
        """Asserts that val does not contain the given item or items.

        Checks if the collection excludes the given item or items using ``in`` operator.

        Args:
            *items: the item or items expected to be excluded

        Examples:
            Usage:

                assert_that('foo').does_not_contain('x')
                assert_that(['a', 'b']).does_not_contain('x', 'y')
                assert_that((1, 2, 3)).does_not_contain(4, 5)
                assert_that({'a': 1, 'b': 2}).does_not_contain('x', 'y')  # checks keys
                assert_that({'a', 'b'}).does_not_contain('x', 'y')
                assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain the item or items
            TypeError: if val is not a container or iterable

        Note:
            Accepts a `Matcher` for any item, the same as
            [`contains()`][assertpy.contains.ContainsMixin.contains]: the assertion then fails when any
            item of val matches it.

        Tip:
            Use the [`does_not_contain_key()`][assertpy.dict.DictMixin.does_not_contain_key] alias when working with
            *dict-like* objects to be self-documenting.
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        values = self._drained()
        if not is_searchable(values):
            refuse(self.val, "a container or iterable")
        probes = [item for item in items if not _is_matcher(item)]
        # the index `contains` already builds for the same question: asked one item at a time, each of
        # them walks the whole collection
        searched = _index(values, probes) if len(probes) > 1 else None
        lookup = values if searched is None else searched

        def described(item: object) -> object:
            return item.describe() if _is_matcher(item) else item

        def present(item: object) -> bool:
            # a matcher handed here was compared with `in`, which asks the wrong question
            if _is_matcher(item):
                return any(verdict(item.matches(value), subject="the matcher") for value in values)
            return member(item, lookup)

        if len(items) == 1:
            if present(items[0]):
                return self.error(
                    f"Expected <{_capped_format(values)}> to not contain item"
                    f" <{_capped_format(described(items[0]))}>, but did."
                )
        else:
            found = [item for item in items if present(item)]
            if found:
                shown = [described(item) for item in items]
                found_shown = [described(item) for item in found]
                return self.error(
                    f"Expected <{_capped_format(values)}> to not contain items {self._fmt_items(shown)},"
                    f" but did contain {self._fmt_items(found_shown)}."
                )
        return self

    def contains_only(self, *items: object) -> Self:
        """Asserts that val contains *only* the given item or items.

        Checks if the collection contains only the given item or items using ``in`` operator.

        Args:
            *items: the *only* item or items expected to be contained

        Examples:
            Usage:

                assert_that('foo').contains_only('f', 'o')
                assert_that(['a', 'a', 'b']).contains_only('a', 'b')
                assert_that((1, 1, 2)).contains_only(1, 2)
                assert_that({'a': 1, 'a': 2, 'b': 3}).contains_only('a', 'b')
                assert_that({'a', 'a', 'b'}).contains_only('a', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val contains anything **not** item or items

        Note:
            Where one item is not found, the failure says what is nearest to it: the closest row among the
            elements nobody asked for, and on a line under the message why it is not there, where one fact about
            it says so.
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        # walked twice below and rendered a third time, so a one-shot iterator has to be drained
        values = searchable(self._drained())
        if not is_walkable(values):
            # "only these" has to see every element, and the comprehension answered "object is not iterable"
            refuse(self.val, "iterable")
        extra, missing = only_faults(values, items)
        if extra or missing:
            # both halves at once: reporting only the extras sends the reader to rerun into the other
            faults = []
            entries = []
            had, lacked = _lone_pair(extra, missing) or (self._fmt_items(extra), self._fmt_items(missing))
            if extra:
                faults.append(f"did contain {had}")
                entries += [DiffEntry(path="extra", actual=item, expected=None, absent="expected") for item in extra]
            if missing:
                faults.append(f"did not contain {lacked}")
                entries += [DiffEntry(path="missing", actual=None, absent="actual", expected=item) for item in missing]
            return self.error(
                f"Expected <{_capped_format(values)}> to contain only {self._fmt_items(items)},"
                f" but {' and '.join(faults)}." + _both_ways(extra, missing, values, items),
                diff=DiffResult(kind="contains", entries=entries),
                expected=items,
            )
        return self

    def contains_sequence(self, *items: object) -> Self:
        """Asserts that val contains the given ordered sequence of items.

        Checks if the collection contains the given sequence of items using ``in`` operator.

        Args:
            *items: the sequence of items expected to be contained

        Examples:
            Usage:

                assert_that('foo').contains_sequence('f', 'o')
                assert_that('foo').contains_sequence('o', 'o')
                assert_that(['a', 'b', 'c']).contains_sequence('b', 'c')
                assert_that((1, 2, 3)).contains_sequence(1, 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contains the given sequence of items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        if isinstance(self.val, str):
            search_start = 0
            for item in items:
                text = require_type(item, str, "a string, to match val", subject=argument("item"))
                found_index = self.val.find(text, search_start)
                if found_index == -1:
                    # name where the chain broke: "but did not" makes the reader re-derive it by eye
                    matched = items[: items.index(item)]
                    trail = f" after {self._fmt_items(matched)}" if matched else ""
                    return self.error(
                        f"Expected <{_capped(self.val)}> to contain sequence {self._fmt_items(items)},"
                        f" but <{_capped_format(item)}> was not found{trail}.",
                        expected=items,
                    )
                search_start = found_index + len(text)
            return self
        # this walk is by index, which a one-shot iterator does not support at all
        values = self._drained()
        if not isinstance(values, Sequence):
            # the old guard said "not iterable" for both: true for an int, false for a set, which has no order
            require_type(values, Iterable, "iterable")
            refuse(self.val, "a sequence, to contain a sequence")
        try:
            best_prefix = _sequence_break(values, items, answered=any(may_broadcast(item) for item in items))
        except REFUSALS:
            best_prefix = _sequence_break(values, items, answered=True)
        if best_prefix is None:
            return self
        best_prefix = max(best_prefix, _late_run(values, items))
        # the longest run that lined up says where the sequence broke down
        detail = (
            f" The longest run that matched was {self._fmt_items(items[:best_prefix])}."
            if best_prefix
            # X may well be present, just never at a position where the whole sequence still fits
            else f" No run started with <{_capped_format(items[0])}>."
        )
        return self.error(
            f"Expected <{_capped_format(values)}> to contain sequence {self._fmt_items(items)}, but did not.{detail}"
            + _why_absent(items[best_prefix], values),
            expected=items,
        )

    def contains_duplicates(self) -> Self:
        """Asserts that val is iterable and *does* contain duplicates.

        Examples:
            Usage:

                assert_that('foo').contains_duplicates()
                assert_that(['a', 'a', 'b']).contains_duplicates()
                assert_that((1, 1, 2)).contains_duplicates()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain any duplicates
        """
        try:
            values = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        if has_duplicates(values):
            return self
        return self.error(f"Expected <{_capped(self.val)}> to contain duplicates, but did not.")

    def does_not_contain_duplicates(self) -> Self:
        """Asserts that val is iterable and *does not* contain any duplicates.

        Examples:
            Usage:

                assert_that('fox').does_not_contain_duplicates()
                assert_that(['a', 'b', 'c']).does_not_contain_duplicates()
                assert_that((1, 2, 3)).does_not_contain_duplicates()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain duplicates
        """
        try:
            values = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        if not has_duplicates(values):
            return self
        # "but did" leaves the reader to scan the value for the repeat
        repeated = repeated_counts(values)
        named = [value for value, _total in repeated]
        return self.error(
            f"Expected <{_capped(self.val)}> to not contain duplicates, but {self._fmt_items(named)}"
            f" {'was' if len(named) == 1 else 'were'} repeated.",
            diff=DiffResult(kind="contains", entries=_surplus(repeated)),
        )

    def is_empty(self) -> Self:
        """Asserts that val is empty.

        Examples:
            Usage:

                assert_that('').is_empty()
                assert_that([]).is_empty()
                assert_that(()).is_empty()
                assert_that({}).is_empty()
                assert_that(set()).is_empty()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** empty
        """
        if sized_len(self.val) != 0:
            if isinstance(self.val, str):
                return self.error(f"Expected <{_capped(self.val)}> to be empty string, but was not.")
            else:
                return self.error(f"Expected <{_capped(self.val)}> to be empty, but was not.")
        return self

    def is_not_empty(self) -> Self:
        """Asserts that val is *not* empty.

        Examples:
            Usage:

                assert_that('foo').is_not_empty()
                assert_that(['a', 'b']).is_not_empty()
                assert_that((1, 2, 3)).is_not_empty()
                assert_that({'a': 1, 'b': 2}).is_not_empty()
                assert_that({'a', 'b'}).is_not_empty()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** empty
        """
        if sized_len(self.val) == 0:
            if isinstance(self.val, str):
                return self.error("Expected not empty string, but was empty.")
            else:
                return self.error("Expected not empty, but was empty.")
        return self

    def contains_exactly(self, *items: object) -> Self:
        """Asserts that val contains exactly the given items in the given order.

        Unlike [`contains_only()`][assertpy.contains.ContainsMixin.contains_only] (which ignores
        order) and [`contains_sequence()`][assertpy.contains.ContainsMixin.contains_sequence]
        (which allows extra items), this method requires exact count, items, and order.

        Args:
            *items: the items expected, in exact order

        Examples:
            Usage:

                assert_that([1, 2, 3]).contains_exactly(1, 2, 3)
                assert_that(['a', 'b']).contains_exactly('a', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain exactly the given items in order
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        expected_list = list(items)
        if equals(val_list, expected_list):
            return self
        message = f"Expected <{_capped(self.val)}> to contain exactly {self._fmt_items(items)}, but did not."
        entries = _multiset_diff_entries(val_list, expected_list)
        # equal multisets, so only the order differs: name the first position that disagrees
        disagreeing = (
            i
            for i, (found, wanted) in enumerate(zip(val_list, expected_list, strict=True))
            if not _guarded_equal(found, wanted, method="contains_exactly")
        )
        # none, from an `__eq__` that answered the list's question and the rescan's differently
        index = None if entries else next(disagreeing, None)
        if index is None:
            diff = DiffResult(kind="contains", entries=entries)
            message += _both_ways(*_unmatched(entries), val_list, expected_list)
        else:
            message += f" Same items, but the order differs at index {index}."
            diff = DiffResult(
                kind="sequence",
                entries=[_ROOT.index(index).entry(actual=val_list[index], expected=expected_list[index])],
            )
        return self.error(message, diff=diff, expected=items)

    def contains_exactly_in_any_order(self, *items: object) -> Self:
        """Asserts that val contains exactly the given items, in any order.

        Like [`contains_exactly()`][assertpy.contains.ContainsMixin.contains_exactly] but ignoring
        order: val and the given items must be equal as multisets, so duplicates count (each item
        must occur exactly as many times as given).  Unlike
        [`contains_only()`][assertpy.contains.ContainsMixin.contains_only] (which checks membership
        both ways and ignores counts), an extra duplicate or a missing one fails.

        Args:
            *items: the items expected, in any order

        Examples:
            Usage:

                assert_that([3, 1, 2]).contains_exactly_in_any_order(1, 2, 3)
                assert_that(['b', 'a', 'b']).contains_exactly_in_any_order('a', 'b', 'b')

                assert_that([1, 2, 2]).contains_exactly_in_any_order(1, 2)  # fails (extra 2)
                assert_that([1, 2]).contains_exactly_in_any_order(1, 2, 2)  # fails (missing 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain exactly the given items in any order
            TypeError: if val is not iterable
            ValueError: if no items are given
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        entries = _multiset_diff_entries(val_list, list(items))
        if entries:
            return self.error(
                f"Expected <{_capped(self.val)}> to contain exactly {self._fmt_items(items)} in any order, "
                f"but did not." + _both_ways(*_unmatched(entries), val_list, items),
                diff=DiffResult(kind="contains", entries=entries),
                expected=items,
            )
        return self

    def contains_in_order(self, *items: object) -> Self:
        """Asserts that val contains the given items in the given order (as a subsequence).

        Items must appear in the given order but do not need to be contiguous.
        Unlike [`contains_sequence()`][assertpy.contains.ContainsMixin.contains_sequence] which
        requires contiguous items.

        Args:
            *items: the items expected, in order (but not necessarily contiguous)

        Examples:
            Usage:

                assert_that([1, 5, 2, 8, 3]).contains_in_order(1, 2, 3)
                assert_that(['a', 'x', 'b', 'y', 'c']).contains_in_order('a', 'b', 'c')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain items in the given order
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        item_index, wanted = 0, items[0]
        for element in val_list:
            # the very object is itself before `==` is asked, as it is to `in`: a NaN the value holds follows
            if element is wanted or equals(element, wanted):
                item_index += 1
                if item_index == len(items):
                    break
                wanted = items[item_index]
        if item_index != len(items):
            # item_index counts how many lined up before the run stopped, so the next one is the culprit
            matched = items[:item_index]
            trail = f" after {self._fmt_items(matched)}" if matched else ""
            return self.error(
                f"Expected <{_capped(self.val)}> to contain {self._fmt_items(items)} in order, "
                f"but <{_capped_format(items[item_index])}> did not follow{trail}."
                + _why_absent(items[item_index], val_list),
                expected=items,
            )
        return self

    def contains_only_once(self, *items: object) -> Self:
        """Asserts that val contains each given item exactly once.

        Each given item must appear in val with a count of exactly one: an item absent from val is
        reported as missing, an item occurring more than once is reported as duplicated.

        Args:
            *items: the items each expected to occur exactly once

        Examples:
            Usage:

                assert_that([1, 2, 3]).contains_only_once(1, 3)
                assert_that('foo').contains_only_once('f')

                assert_that([1, 2, 2, 3]).contains_only_once(2)  # fails (occurs twice)
                assert_that([1, 2, 3]).contains_only_once(4)  # fails (missing)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any given item is missing from val or occurs more than once
            TypeError: if val is not iterable
            ValueError: if no items are given
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        try:
            val_list = list(self._walked())
        except TypeError:
            refuse(self.val, "iterable")
        counts = occurrences(val_list, items)
        missing = [item for item, total in zip(items, counts, strict=True) if total == 0]
        repeats = [(item, total) for item, total in zip(items, counts, strict=True) if total > 1]
        duplicated = [item for item, _ in repeats]
        if missing or duplicated:
            entries = [DiffEntry(path="missing", actual=None, absent="actual", expected=item) for item in missing]
            entries.extend(_surplus(repeats))
            problems = []
            if missing:
                problems.append(f"did not contain {self._fmt_items(missing)}")
            if duplicated:
                problems.append(f"contained {self._fmt_items(duplicated)} more than once")
            return self.error(
                f"Expected <{_capped_format(val_list)}> to contain {self._fmt_items(items)} only once,"
                f" but {' and '.join(problems)}." + _one_not_found(missing, val_list),
                diff=DiffResult(kind="contains", entries=entries),
                expected=items,
            )
        return self

    def is_in(self, *items: object) -> Self:
        """Asserts that val is equal to one of the given items.

        Args:
            *items: the items expected to contain val

        Examples:
            Usage:

                assert_that('foo').is_in('foo', 'bar', 'baz')
                assert_that(1).is_in(0, 1, 2, 3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** in the given items

        Note:
            The failure says what is nearest to val: the closest row among the given items, and on a line under
            the message why val is in none of them, where one fact about it says so.
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        # identity first, as `in` asks: the very NaN a tuple holds is in it, and `==` alone said no
        if member(self.val, items):
            return self
        roles = Roles("the value", "a given item")
        return self.error(
            f"Expected <{_capped(self.val)}> to be in {self._fmt_items(items)}, but was not."
            + _one_not_found((self.val,), items, noun="item", item_is_actual=True, roles=roles),
            expected=items,
        )

    def is_not_in(self, *items: object) -> Self:
        """Asserts that val is not equal to one of the given items.

        Args:
            *items: the items expected to exclude val

        Examples:
            Usage:

                assert_that('foo').is_not_in('bar', 'baz', 'box')
                assert_that(1).is_not_in(-1, -2, -3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** in the given items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        if member(self.val, items):
            return self.error(f"Expected <{_capped(self.val)}> to not be in {self._fmt_items(items)}, but was.")
        return self
