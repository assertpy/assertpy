"""Membership as one decision: which of the wanted items a value does not contain.

`contains` is the second relation that a builder could express and a matcher could not.  A structural
spec had `each_item` (every element matches) and `is_in` (the value is one of these), but no way to say
the plain thing: *this collection contains that*.  Writing it a second time inside the matcher would
have repeated the part that is easy to get subtly wrong, since membership is not one rule: a mapping is
searched by key, a matcher argument is satisfied by any element rather than compared to the whole, and a
one-shot iterator has to be drained before it is searched more than once.

So the decision moves here and both spellings ask it.  What stays outside is the wording: the builder
turns the answer into a message with a closest-element hint, and a matcher turns it into a verdict.
"""

from __future__ import annotations

import datetime
import decimal
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, NoReturn, cast

from ._introspection import definition_of, is_mapping_like, materialized
from ._ordering import (
    _PLAIN,
    MEMBERSHIP_REFUSALS,
    REFUSALS,
    equals,
    lookup,
    may_broadcast,
    member,
    member_past,
    mixes_broadcasting,
)
from ._require import raised_inside, verdict

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def searchable(value: object) -> Any:
    """*value* in a form that can be searched more than once.

    A generator is consumed by the first pass, and membership is tested once per wanted item.  A value
    that cannot be iterated at all is handed back untouched, which is why the parameter is `object`:
    deciding whether membership can be asked of it is `is_searchable`'s job, not this one's.

    Only a one-shot iterator is copied.  A list, set, tuple or mapping is handed back as it is, so a
    matcher built from one stays a live view of it, the way `match.equal_to(expected)` does:

        known = [1]
        constraint = match.is_subset_of(known)
        known.append(2)
        constraint.matches([2])          # True: the same list, not a snapshot of it

    The copy for an iterator is therefore not a snapshot policy but the only way to answer twice at all,
    and it is eager: an endless iterator handed in as the expected operand never finishes being drained.
    """
    return materialized(cast("Iterable[Any]", value))


def is_searchable(value: object) -> bool:
    """Whether membership can be asked of *value*: `in` needs a container or an iterable.

    Wider than `is_walkable` on purpose, and the two are not interchangeable.  A value that answers
    `__contains__` and nothing else can be asked whether it holds something, and cannot be listed: it
    fits `contains` and does not fit `contains_only`, which has to see everything that is there.
    """
    # the builtins skip the ABC's 88 ns walk; each has `__contains__`, so the probe below said yes to them anyway
    return isinstance(value, (list, tuple, str, bytes, dict, set, frozenset, Iterable)) or hasattr(
        type(value), "__contains__"
    )


def is_walkable(value: object) -> bool:
    """Whether *value* can be listed, which is what "only these" and "a subset of" both need."""
    return isinstance(value, Iterable)


# types whose `__hash__` and `__eq__` agree; `bytearray` looks like one and turned `contains_only` into TypeError
_HASH_SAFE = frozenset(
    {
        int,
        float,
        complex,
        bool,
        str,
        bytes,
        frozenset,
        type(None),
        # `Fraction` qualifies and is left out: `fractions` drags in thirteen modules at import
        decimal.Decimal,
        datetime.date,
        datetime.datetime,
        datetime.time,
        datetime.timedelta,
    }
)


# measured 2x slower at ten elements and several times faster at a hundred
_WALK_UNDER = 400

# the one safe-list type that refuses to hash for a single value: `Decimal("snan")` raises
_HASH_MAY_REFUSE = frozenset({decimal.Decimal})


def _worth_hashing(container: Any, probes: Any) -> bool:
    """Whether the pair is large enough that a set can win at all, asked before anything expensive.

    The comparison count is what decides, so the two questions differ: searching one collection for the
    elements of another costs `len * len`, while looking for a repeat inside one collection costs about
    `len` squared over two but pays for only one set.  Passing the same collection twice is how the
    second question spells itself.
    """
    try:
        return len(container) * max(len(probes), 1) >= _WALK_UNDER
    except TypeError:  # no length: an iterator or a view, where the walk cost is unknown but not small
        return True
    except Exception:  # a length refused: the walk never sizes the value, and this is a cost, not a verdict
        return False


def _kinds(items: Any) -> set[type] | None:
    """The distinct types in *items*, or ``None`` when even that cannot be asked.

    Collected in the interpreter's own loop rather than a Python one: over ten thousand elements the loop
    would cost more than the set it is deciding about, and what is left to judge is one entry per type,
    which is almost always one.

    Asking can itself fail, which is not hypothetical: a class whose metaclass declares `__hash__ = None`
    cannot go into a set although its instances compare perfectly well.  Unanswerable means "no".
    """
    try:
        return set(map(type, items))
    except TypeError:  # the class objects themselves refuse to be hashed
        return None


def _safe(kinds: set[type] | None) -> bool:
    """Whether every one of *kinds* hashes and compares by the same rule."""
    return kinds is not None and all(_agrees(kind) for kind in kinds)


def _agrees(kind: type) -> bool:
    """Whether this type's ``==`` and ``hash()`` answer consistently, so a set may stand in for a walk.

    Hashability is asked of the type, not tried on the value: an unhashable type carries
    `__hash__ = None`.  It is not implied by the rest of the rule, since a class can inherit identity
    equality and still declare itself unhashable, and without this the shortcut raised where it answered.

    The third clause is what admits a subclass.  A name on the safe list is not enough on its own,
    because that list holds exact types, and `IntEnum`, `StrEnum` and a plain `class Money(int)` all
    took the quadratic walk although they answer exactly as their base does: four thousand of them cost
    30 ms against 0.09 ms.  Asked of the owner of each definition rather than of the definition itself,
    so a class that assigns `__hash__ = str.__hash__` beside an inherited `int.__eq__` is refused: its
    owner is the class, not a safe type.  A base cannot supply the two from different safe types either,
    since inheriting from two of them is a layout conflict the interpreter refuses.
    """
    return kind.__hash__ is not None and (
        kind in _HASH_SAFE
        or kind.__eq__ is object.__eq__
        or (_owned_by_a_safe_type(kind, "__eq__") and _owned_by_a_safe_type(kind, "__hash__"))
    )


def _owned_by_a_safe_type(kind: type, name: str) -> bool:
    """Whether *kind* inherits *name* unchanged from one of the types on the safe list."""
    found = definition_of(kind, name)
    return found is not None and found[0] in _HASH_SAFE


def _hash_safe(items: Any) -> bool:
    """Whether *items* may be indexed. Kept as a name of its own because the tests read better with it."""
    return _safe(_kinds(items))


class MembershipRefusedError(TypeError):
    """The operands refuse the question: this item cannot be searched for in this value at all.

    Its own type so a matcher can answer "no match" to it, while a `TypeError` raised inside the value's
    own `__contains__` or `__eq__` still reaches the reader as the bug in that value it is.  Raised only for
    a caller that asks with ``marked=True``: a builder's caller gets the operator's own `TypeError`, as a
    single item does, where the class used to name a private module whenever two or more were asked.
    """


def _told_apart(pairs: Sequence[tuple[Any, Any]], original: TypeError, *, marked: bool) -> NoReturn:
    """Ask again one expression at a time, so an operand refusal can be told from a bug in their code.

    Reached only where a walk has already raised, so the second ask costs a passing run nothing.  Asked
    whole, the walk is several frames deep and `raised_inside` cannot see which frame tried the operator;
    asked one `in` at a time, it reads exactly that.
    """
    for items, container in pairs:
        for item in items:
            try:
                if item in container:
                    continue
            except (decimal.InvalidOperation, OverflowError):
                continue  # a signalling NaN or a `numpy` overflow, which `member` answers: not the refusal sought
            except TypeError as refusal:
                if raised_inside(refusal):
                    raise
                if _answered(item, container):
                    continue
                if not marked:
                    raise
                raise MembershipRefusedError(str(refusal)) from refusal
    raise original


def _answered(item: Any, container: Any) -> bool:
    """Whether `member` answers what ``in`` refused, as it does a `Decimal` against a `numpy` integer."""
    try:
        member(item, container)
    except TypeError:
        return False
    return True


def missing_items(
    value: Any, items: Sequence[Any], is_matcher: Callable[[object], bool], *, marked: bool = False
) -> list[Any]:
    """Which of *items* are not in *value*, in the order they were asked for.

    A matcher among the items is satisfied by any single element, which is what makes this more than
    `item in value`: `contains(match.greater_than(3))` asks whether *some* element is greater than 3,
    not whether the collection holds that matcher object.

    The matcher test is passed in rather than imported: matchers are a layer above this one, and having
    the core reach up for them would make the dependency circular.
    """
    walked = materialized(value)
    wanted = materialized(items)
    present = _index(walked, wanted) if isinstance(walked, (list, tuple)) else None
    return _absent_from(walked if present is None else present, wanted, is_matcher, walked, marked)


def _absent_from(
    present: Any, items: Any, is_matcher: Callable[[object], bool], walked: Any, marked: bool
) -> list[Any]:
    """The loop itself, so the fast and the walking form stay one piece of logic rather than two.

    A refusal is named by the item it came from.  A matcher is asked of the elements and never by ``in``, so an
    error of its own is its own and leaves as it was raised; an item `member` refused is asked again alone.
    """
    absent = []
    # the index `_index` built holds only types that hash and compare alike, which no `numpy` scalar or list is
    verify = present is walked
    for item in items:
        if is_matcher(item):
            if not any(verdict(item.matches(element), subject="the matcher") for element in walked):
                absent.append(item)
            continue
        try:
            if not _held(item, present, verify):
                absent.append(item)
        except TypeError as refusal:
            _told_apart((((item,), present),), refusal, marked=marked)
    return absent


def _held(item: Any, present: Any, verify: bool) -> bool:
    """`member`, asking ``in`` itself where no item that may broadcast can come: through it cost 100 items 11%."""
    if not verify or type(item) in _PLAIN:
        try:
            return item in present
        except MEMBERSHIP_REFUSALS as refusal:
            found = member_past(item, present, refusal)
            if found is None:
                raise
            return found
    return member(item, present, verify)


def only_faults(value: Any, items: Sequence[Any], *, marked: bool = False) -> tuple[list[Any], list[Any]]:
    """``(extra, missing)`` for "contains only these": what is there but unwanted, and what is absent.

    Both halves at once, because reporting only the extras sends the reader to fix one problem and rerun
    into the other.  A matcher looks at whether either list is non-empty; the assertion words them.
    """
    # walked three times below, and idempotent for the callers that already did it
    walked, wanted_items = materialized(value), materialized(items)
    # each side is searched for the other, and building both together is what makes either refusal fall back
    # only over sequences, as the other two searches are: a set of a string's characters answers by character
    # where the walk answers by substring, and the verdict then moved with the length of the string
    indexable = isinstance(walked, (list, tuple)) and isinstance(wanted_items, (list, tuple))
    both = _index_both(wanted_items, walked) if indexable else None
    try:
        if both is None:
            return _without(walked, wanted_items), _without(wanted_items, walked)
        wanted, present = both
        extra = _without(walked, wanted)
        missing = _without(wanted_items, present)
    except TypeError as refusal:
        _told_apart(((walked, wanted_items), (wanted_items, walked)), refusal, marked=marked)
    return extra, missing


def _without(items: Iterable[Any], container: Any) -> list[Any]:
    """The *items* not in *container*, asked by ``in`` and, once that raised, as `member` asks it.

    A `TypeError` is asked again too, since a signalling NaN refuses to hash for a set: `member` answers that
    one and hands every other refusal on.
    """
    # a walk of a sequence is quadratic, so the pass that finds a `numpy` scalar meeting a list costs it nothing
    if isinstance(container, (list, tuple)) and mixes_broadcasting(items, container):
        return [item for item in items if not member(item, container)]
    try:
        return [item for item in items if item not in container]
    except REFUSALS:
        return [item for item in items if not member(item, container)]


def has_duplicates(values: Sequence[Any]) -> bool:
    """Whether any element appears twice, by the same equality the rest of membership uses."""
    if _classified_alone(values):
        try:
            # what a set replaces is a growing list of seen elements, quadratic from the first few
            return len(set(values)) != len(values)
        except Exception:  # a value refused to hash after all; only hashing is inside this `try`
            pass
    if mixes_broadcasting(values):
        return any(member(value, values[:index]) for index, value in enumerate(values))
    # `in` rather than a generator of `==`: the interpreter asks it, and it short-circuits on identity
    seen: list[Any] = []
    try:
        for value in values:
            if value in seen:
                return True
            seen.append(value)
    except REFUSALS:
        return any(member(value, values[:index]) for index, value in enumerate(values))
    return False


def occurrences(values: Sequence[Any], items: Sequence[Any]) -> list[int]:
    """How often each of *items* appears in *values*, in the order they were asked for.

    `list.count()` per item walks the whole collection once per item: a thousand items over ten thousand
    elements is ten million comparisons, and the failure report asked for another pass.  Where both sides
    are safe to hash, by the same rule membership uses, one `Counter` answers all of them.

    The probes are hashed inside the guard and looked up outside it, as `_index` does: a lookup runs
    `__eq__` on a collision, and a comparison that raises is a bug in the value rather than a count.
    """
    counted = None
    if _classified(values, items):
        try:
            counted = Counter(values)
            for item in items:
                hash(item)
        except TypeError:  # a value that refuses to hash despite its type, such as a signalling NaN
            counted = None
    if counted is None:
        return [_count(values, item) for item in items]
    return [counted[item] for item in items]


def _count(values: Sequence[Any], item: Any) -> int:
    """``values.count(item)``, each element asked as `equals` asks it once ``count`` raised."""
    if may_broadcast(item) and mixes_broadcasting(values, (item,)):
        return sum(1 for value in values if value is item or equals(value, item))
    try:
        return values.count(item)
    except REFUSALS as refusal:
        if raised_inside(refusal):
            raise
        return sum(1 for value in values if value is item or equals(value, item))


def repeated_counts(values: Sequence[Any]) -> list[tuple[Any, int]]:
    """Each element appearing more than once with how often, in order of first appearance.

    Counting with `list.count()` per element re-walks the whole sequence every time, so naming the
    duplicates in a collection of a few thousand costs as much as the assertion it explains.  Where the
    elements are safe to hash (same rule as membership uses), one pass counts them all.
    """
    counts = None
    if _classified_alone(values):
        try:
            counts = Counter(values)
        except TypeError:  # a value that refuses to hash despite its type, such as a signalling NaN
            counts = None
    if counts is None:
        named: list[tuple[Any, int]] = []
        for value in values:
            total = _count(values, value)
            if total > 1 and not any(earlier is value or equals(earlier, value) for earlier, _ in named):
                named.append((value, total))
        return named
    seen: set[Any] = set()
    repeated = []
    for value in values:
        if counts[value] > 1 and value not in seen:
            seen.add(value)
            repeated.append((value, counts[value]))
    return repeated


def repeated_items(values: Sequence[Any]) -> list[Any]:
    """Which elements appear more than once, each named once, in order of first appearance."""
    return [value for value, _count in repeated_counts(values)]


def flattened_supersets(supersets: Sequence[Any]) -> list[Any]:
    """The supersets of `is_subset_of` as one collection of items, which is what the value is searched in.

    A superset that cannot be iterated is a single item, and a string is its characters, which is what
    ``in`` over a flattened list answers.  The matcher used to keep the superset whole, so a string
    superset answered substring membership and a `set` superset hashed items that refuse to hash.
    """
    collected: list[Any] = []
    for superset in supersets:
        try:
            collected.extend(materialized(superset))
        except TypeError:  # noqa: PERF203  # a non-iterable superset is one item, as the assertion has always read it
            collected.append(superset)
    return collected


def subset_faults(value: Any, supersets: Sequence[Any]) -> list[Any]:
    """What no superset holds: the pairs of a mapping value, or the elements of anything else.

    A pair holds when any one superset holds it, rather than when the mapping left after merging them
    does: merging let a later superset overwrite an earlier one, so the verdict moved with the order the
    supersets were written in.
    """
    if is_mapping_like(value):
        pairs = [(key, value[key]) for key in value]
        return [{key: item} for key, item in pairs if not _pair_held(key, item, supersets)]
    return not_contained_in(list(materialized(value)), flattened_supersets(supersets))


def _pair_held(key: Any, item: Any, supersets: Sequence[Any]) -> bool:
    """Whether one key/value pair is in any of the supersets, by identity first, as a container asks."""
    for superset in supersets:
        try:
            if not is_mapping_like(superset) or key not in superset:
                continue
            held = superset[key]
        except REFUSALS as refusal:
            found, held = lookup(superset, key, refusal)
            if not found:
                continue
        if held is item or equals(held, item):
            return True
    return False


def not_contained_in(value: Any, container: Any) -> list[Any]:
    """Which elements of *value* the *container* does not hold, for "is a subset of"."""
    value, container = materialized(value), materialized(container)
    indexed = _index(container, value) if isinstance(container, (list, tuple)) else None
    allowed = container if indexed is None else indexed
    return _without(value, allowed)


def _classified(container: Any, probes: Any) -> bool:
    """Whether a set may stand in for the walk here: worth the preparation, and safe to build."""
    return _worth_hashing(container, probes) and _hash_safe(container) and _hash_safe(probes)


def _index(container: Any, probes: Any) -> set[Any] | None:
    """*container* as a set, or ``None`` when the walk has to answer instead.

    Everything that can raise is inside, and nothing else is: building the set hashes the container, and
    the probes are asked separately only where a classified type is still allowed to refuse, because
    `x in some_set` hashes `x` too.  The search itself always runs outside any `except`.

    Asking every probe unconditionally was the first shape of this, and it hashed the same values twice
    on the successful path, which is a pass over the whole collection for `is_subset_of`.

    That boundary is the point.  A wider `try` around the search would swallow a failing comparison or a
    matcher raising from user code, and this library treats those as bugs in the test that must travel
    out, not as verdicts.  What is caught here is narrower and real: a type may pass the rule and still
    hold a value that refuses to hash, and before this shortcut existed nothing hashed it at all.

    Two limits, both deliberate.  Only subclasses of `Exception` are caught, so a `KeyboardInterrupt`
    during hashing still stops the run, as it should.  And a `__hash__` that answers once and raises
    later is not covered by anything here: a hash is required to be deterministic, and a value that
    breaks that contract is left to break it.
    """
    container_kinds, probe_kinds = _kinds(container), _kinds(probes)
    if not (_worth_hashing(container, probes) and _safe(container_kinds) and _safe(probe_kinds)):
        return None
    try:
        indexed = set(container)
        if probe_kinds is not None and (probe_kinds & _HASH_MAY_REFUSE or not probe_kinds <= _HASH_SAFE):
            # anything but an exact builtin may still refuse: a `Decimal("snan")`, or a class of one's own
            # that inherits identity equality and writes a `__hash__` that raises
            for probe in probes:
                hash(probe)
    except Exception:  # any Exception raised while hashing means the walk answers instead
        return None
    return indexed


def _index_both(left: Any, right: Any) -> tuple[set[Any], set[Any]] | None:
    """Both collections as sets, or nothing.

    Where each side is searched for the other, building both is already the whole question: a value that
    refuses to hash stops one of the two constructions, and there is nothing left to check separately.
    Asking `_index` twice would hash every element twice over for no added safety.
    """
    if not _classified(left, right):
        return None
    try:
        return set(left), set(right)
    except Exception:  # either side refusing is enough, and neither index is used then
        return None


def _classified_alone(values: Any) -> bool:
    """The same decision for a question asked of one collection, where only one set gets built.

    Kept apart from `_classified` because the arithmetic differs, and differs in the other direction than
    it first looks: what a set replaces here is a growing list of seen elements, which is quadratic from
    the very first elements.  A size threshold made this *slower* at thirty elements, so there is none:
    the only question is whether the elements may be hashed at all.
    """
    return _hash_safe(values)
