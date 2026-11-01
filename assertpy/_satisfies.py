from __future__ import annotations

import collections.abc
import warnings
from typing import TYPE_CHECKING, Any, cast

from . import _renamed
from ._engine._diff import _walk_leaves
from ._engine._introspection import (
    caller_stacklevel,
    class_name,
    is_attrs_instance,
    is_mapping_like,
    is_model_dump_object,
    plainly_hashed,
)
from ._engine._mixin_base import _MixinBase
from ._engine._pairing import maximum_pairing
from ._engine._path import _ROOT
from ._engine._require import VerdictError, argument, refuse, verdict
from ._hints import class_in_spec, under
from ._matcher_impls import _A_STRUCTURE, _describe_spec_value, _has_own_evaluate, _outcome_of, _ReadOnce
from .errors import (
    DiffEntry,
    DiffResult,
    VacuousAssertionWarning,
    _capped,
    _capped_format,
    _safe_repr,
    _truncated,
)
from .helpers import _ELIDED, _entry_part, _field_part, _joined_parts, _Part
from .matchers import (
    BaseMatcher,
    IsNotNoneMatcher,
    Matcher,
    StructureMatcher,
    _apply_matcher,
    _describe_matcher,
    _evaluate_matcher,
    _is_matcher,
    _refused,
    _resolved,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ._engine._compat import Self

__tracebackhide__ = True


_Kept = dict[int, tuple[object, Any]]
"""The keys of one level of a spec that lead to a mismatch, by the identity of the key, each with the level under it."""


def _kept_keys(entries: list[DiffEntry]) -> _Kept:
    """The keys on the way to every mismatch of a spec, level by level, read off the steps its walk recorded."""
    kept: _Kept = {}
    for entry in entries:
        level = kept
        for step in entry.steps:
            level = level.setdefault(id(step.value), (step.value, {}))[1]
    return kept


def _elided_spec(expected: object, kept: _Kept) -> str:
    """What a spec value is described as, with the keys that matched left out as ``..``.

    Whole where nothing under it failed, and where the spec there is no exact dict: its keys are found by
    identity, and a dict of a class of its own may hand out other objects each time it is read.
    """
    spec = expected._spec if type(expected) is StructureMatcher else expected
    if not kept or type(spec) is not dict:
        return _describe_spec_value(expected)
    parts: list[_Part] = []
    pending = False
    for key, value in spec.items():
        found = kept.get(id(key))
        if found is None:
            pending = True
            continue
        if pending:
            parts.append(_ELIDED)
            pending = False
        parts.append(f"{key}: {_elided_spec(value, found[1])}")
    if pending:
        parts.append(_ELIDED)
    described = _joined_parts(parts, opener="{", closer="}")
    return described if spec is expected else f"{_A_STRUCTURE} {described}"


def _elided_mapping(
    mapping: object, kept: _Kept, opener: str, closer: str, part_of: Callable[[object, str], str]
) -> str | None:
    """*mapping* as a failed spec leaves it in a message: the keys on the way to a mismatch, ``..`` for the rest.

    ``None`` where it is not read that way: nothing under it failed, it is no exact dict, or a key of it or of
    the spec's on the way is of a class whose lookup runs that class's ``__hash__`` or ``__eq__``.  And where it
    is written as a record and a key to show is no name: ``x=1, y`` as a field would read as two.
    """
    if not kept or type(mapping) is not dict:
        return None
    if not all(plainly_hashed(key) for key, _ in kept.values()) or not all(map(plainly_hashed, mapping)):
        return None
    below_of = dict(kept.values())
    parts: list[_Part] = []
    pending = False
    # read before anything is printed: the repr of a value may take a key out of the dict that holds it
    for key, value in list(mapping.items()):
        below = below_of.get(key)
        if below is None:
            pending = True
            continue
        if part_of is _field_part and not (type(key) is str and key.isidentifier()):
            return None
        if pending:
            parts.append(_ELIDED)
            pending = False
        nested = _elided_mapping(value, below, "{", "}", _entry_part)
        parts.append(part_of(key, _safe_repr(value) if nested is None else nested))
    if pending:
        parts.append(_ELIDED)
    return _joined_parts(parts, opener=opener, closer=closer)


def _describe_unpaired(matcher, raised_count):
    """Describe an unpaired matcher, noting raised probes so a buggy predicate is not mistaken for a mismatch."""
    description = _describe_matcher(matcher)
    if raised_count:
        item_word = "item" if raised_count == 1 else "items"
        return f"{description} (probe raised TypeError on {raised_count} {item_word})"
    return description


def _max_bipartite_assignment(satisfied: list[list[bool]]) -> list[int | None]:
    """Pair each row with a distinct satisfying column (None where no pairing reaches it)."""
    column_owner = maximum_pairing([{column for column, ok in enumerate(row) if ok} for row in satisfied])
    assignment: list[int | None] = [None] * len(satisfied)
    for column, row in column_owner.items():
        assignment[row] = column
    return assignment


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_enabled() -> bool:
    """Read the environment switch, at import and from the pytest plugin rather than per assertion.

    The switch cannot change within a process, and the lookup with its two string operations costs
    around 300ns: more than the emptiness check it decides to skip, on every quantifier call.
    """
    return _renamed.environ("ASSERTPY_VACUOUS").strip().lower() in _TRUTHY


_VACUOUS_GUARD: bool = _env_enabled()
"""Whether a universal assertion over an empty value warns.

Off by default: a suite running ``filterwarnings = ["error"]`` would otherwise fail on upgrade, and a
property-based test generates empty collections as a matter of course.  Turn it on with the pytest
``--assertpy-vacuous`` flag or the ``ASSERTPY_VACUOUS`` environment variable for other runners.
"""


def _guarding(builder: _MixinBase) -> bool:
    """Whether an assertion on *builder* that checked nothing should say so now.

    Not when another assertion runs it for its own answer.  Under `not_` its pass is the failure the
    caller gets, and the warning beside it pointed into the library.  Under a snapshot the keys it
    ignores include the placeholders the snapshot checks with matchers of their own.  Kept on the
    builder, so an assertion a callback of the caller's runs on a builder of its own still speaks.
    """
    return _VACUOUS_GUARD and not builder._answering_another


def _warn_nothing_compared() -> None:
    """Say that `is_equal_to()` passed with ``ignore`` and ``include`` leaving no key to compare."""
    warnings.warn(
        "is_equal_to() passed with ignore and include leaving no key to compare, so nothing was checked.",
        VacuousAssertionWarning,
        stacklevel=caller_stacklevel(),
    )


def _warn_vacuous(builder: _MixinBase, name: str, allow_empty: bool) -> None:
    """Say that *name* passed over nothing, pointing at the line that called the assertion.

    Called by the assertion itself once its walk is over, never before it.  Asking the subject first
    was the earlier design and it went wrong in every direction available: it spoke in front of a
    refusal, it took an item from a value whose walks share one position, and it answered about a
    length where the assertion was about to walk fields.  What was walked is the only thing that
    answers "nothing was checked", and only the walk knows it.
    """
    if allow_empty or not _guarding(builder):
        return
    warnings.warn(
        f"{name}() passed over an empty value, so nothing was checked. Pass allow_empty=True if that is intended.",
        VacuousAssertionWarning,
        stacklevel=caller_stacklevel(),
    )


class SatisfiesMixin(_MixinBase):
    """Predicate and matcher-application assertions: satisfies / each / *_satisfy / matches_structure."""

    def all_fields_satisfy(self, matcher: Matcher[Any] | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that every scalar leaf in val's object graph satisfies the given matcher.

        Walks val recursively (mappings, dataclasses, namedtuples, Pydantic models, lists, tuples) and
        applies the matcher to each leaf value, reporting the path of every leaf that does not satisfy it.
        Scalars, strings, sets and opaque objects are treated as single leaves.  A Pydantic model is
        walked through the values its fields hold, not its ``model_dump()``: a field excluded from the
        dump is walked, a computed field is not, and a field serializer does not apply.

        Args:
            matcher: a `Matcher` or callable predicate applied to every leaf

        Examples:
            Usage:

                from assertpy import match

                assert_that({"a": 1, "nested": {"b": 2}}).all_fields_satisfy(match.is_positive())
                assert_that([1, [2, 3]]).all_fields_satisfy(lambda x: x > 0)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any leaf does **not** satisfy the matcher
            TypeError: if matcher is neither a Matcher nor callable
        """
        return self._every_field(matcher, allow_empty, "all_fields_satisfy")

    def _every_field(self, matcher, allow_empty: bool, name: str) -> Self:
        """The walk both field quantifiers make, named by whichever of them asked for it."""
        description = None
        walked = 0
        failures = []
        reading = _resolved(matcher)
        apply = reading.apply  # read once: the attribute lookup is per leaf otherwise
        for path, leaf in _walk_leaves(self.val):
            walked += 1
            if not apply(leaf):
                # asked on the first refusal: a self-describing matcher would otherwise read the subject first
                description = reading.describe() if description is None else description
                failures.append(path.leaf_entry(actual=leaf, expected=description))
        if failures:
            count = len(failures)
            field_word = "field" if count == 1 else "fields"
            return self.error(
                f"Expected all fields to satisfy {description}, but {count} {field_word} did not.",
                actual=self.val,
                expected=description,
                diff=DiffResult(kind="match", entries=failures),
            )
        if not walked:
            _warn_vacuous(self, name, allow_empty)
        return self

    def has_no_none_fields(self, *, allow_empty: bool = False) -> Self:
        """Asserts that no scalar leaf in val's object graph is ``None``.

        Convenience wrapper over `all_fields_satisfy()` with a not-``None`` matcher; reports the path
        of every ``None`` leaf found anywhere in the graph, reading a Pydantic model as that does.

        Examples:
            Usage:

                assert_that({"id": 1, "profile": {"name": "Alice"}}).has_no_none_fields()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any leaf **is** ``None``
        """
        return self._every_field(IsNotNoneMatcher(), allow_empty, "has_no_none_fields")

    def satisfies(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self:
        """Asserts that val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy import match

                assert_that(7).satisfies(match.greater_than(5) & match.less_than(10))
                assert_that('hello').satisfies(match.starts_with('he'))

            Usage with callables:

                assert_that(42).satisfies(lambda x: x % 2 == 0)

            When the callable is typed with ``TypeIs`` it also *narrows* the chain to the guarded type
            (refinement narrowing), so ``.value`` hands the value back typed - see
            [Type Safety](../concepts/type-safety.md#refinement-narrowing-with-a-typeis-predicate-advanced) for
            checker support (advanced; not yet in PyCharm).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** satisfy the matcher
        """
        if _is_matcher(matcher):
            read = _ReadOnce(self.val, self._drained, self._handed_out)
            result = _outcome_of(matcher, read)
            if result is not None:
                value = read.shown()
                return self.error(
                    f"Expected {result.description}, but {result.mismatch}.",
                    actual=value,
                    expected=result.description,
                    diff=DiffResult(
                        kind="match", entries=[_ROOT.leaf_entry(actual=value, expected=result.description)]
                    ),
                )
        elif callable(matcher):
            if not verdict(cast("Callable[..., object]", matcher)(self._handed_out())):
                return self.error(
                    f"Expected <{_capped(self.val)}> to satisfy {_describe_matcher(matcher)}, but did not.",
                    expected=_describe_matcher(matcher),
                )
        else:
            refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))
        return self

    def each(self, matcher: Matcher[Any] | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that every item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy import match

                assert_that([1, 2, 3]).each(match.is_positive())
                assert_that([10, 20, 30]).each(match.between(1, 100))

            Usage with extracting:

                assert_that(users).extracting('age').each(match.between(18, 120))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item does **not** satisfy the matcher
        """
        if not _is_matcher(matcher) and not callable(matcher):
            refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        return self._every_item(matcher, allow_empty, "each")

    def _every_item(self, matcher, allow_empty: bool, name: str) -> Self:
        """The walk both item quantifiers make, named by whichever of them asked for it."""
        walked = 0
        if _is_matcher(matcher):
            # a structure is asked for its failure alone, so the spec is described only for the item that failed
            structural = getattr(type(matcher), "evaluate", None) is StructureMatcher.evaluate
            for i, item in enumerate(self._walked()):
                walked += 1
                # the verdict and the reason come from the same look, so a user's `key` runs once
                if structural or _has_own_evaluate(matcher):
                    outcome = (
                        cast("StructureMatcher", matcher)._failure(item)
                        if structural
                        else _evaluate_matcher(matcher, item)
                    )
                elif verdict(matcher.matches(item), subject="the matcher"):
                    continue
                else:
                    outcome = _refused(matcher, item)
                if outcome is not None and not outcome.matched:
                    # read off the refusal: the matcher said what it wanted, and asking twice ran its own method twice
                    description = outcome.description
                    return self.error(
                        f"Expected all items to satisfy {description},"
                        f" but item at index {i} <{_capped_format(item)}> did not:"
                        f" {outcome.mismatch}.",
                        actual=item,
                        expected=description,
                        diff=DiffResult(
                            kind="match", entries=[_ROOT.index(i).entry(actual=item, expected=description)]
                        ),
                    )
        else:
            for i, item in enumerate(self._walked()):
                walked += 1
                if not verdict(cast("Callable[..., object]", matcher)(item)):
                    return self.error(
                        f"Expected all items to satisfy {_describe_matcher(matcher)},"
                        f" but item at index {i} <{_capped_format(item)}> did not.",
                        expected=_describe_matcher(matcher),
                    )
        if not walked:
            _warn_vacuous(self, name, allow_empty)
        return self

    def matches_structure(self, spec: dict[Any, Any]) -> Self:
        """Asserts that val matches the given structure specification.

        ``val`` may be any mapping (a ``dict``, a ``MappingProxyType``, 3.15's ``frozendict``, or your
        own ``collections.abc.Mapping``), a pydantic-style model (anything exposing ``model_dump()``),
        or an ``attrs`` instance, which is normalized to its dict before matching.  Each key in
        ``spec`` maps to either a `Matcher`, a raw value (checked via ``==``), or a nested ``dict``
        for recursive matching.  Extra keys in val that are absent from the spec are allowed.

        A failure prints the spec with what matched left out as ``..``, and val the same way where it is read
        as plain dicts with plain keys, a model and an attrs instance among them.  It holds both whole.

        Args:
            spec: a dict where values can be Matcher instances, raw values, or nested dicts

        Examples:
            Usage:

                from assertpy import assert_that, match

                user = {"name": "Alice", "age": 30, "id": "550e8400-e29b-41d4-a716-446655440000"}
                assert_that(user).matches_structure({
                    "name": match.is_non_empty_string(),
                    "age": match.between(18, 120),
                    "id": match.is_uuid(),
                })

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** match the structure spec
        """
        if not is_mapping_like(self.val) and not is_model_dump_object(self.val) and not is_attrs_instance(self.val):
            refuse(self.val, "a mapping, a pydantic-style model, or an attrs instance")
        if not isinstance(spec, dict):
            refuse(spec, "a dict", subject=argument("spec"))
        matcher = StructureMatcher(spec)
        mapped = matcher._as_mapping(self.val)
        # one walk, read twice: the entries want every mismatch, the message wants the first one in words
        mismatches = matcher._walk(mapped, spec, _ROOT, set())
        if mismatches:
            entries = [
                mismatch.path.entry(actual=mismatch.actual, expected=mismatch.expected_desc) for mismatch in mismatches
            ]
            kept = _kept_keys(entries)
            spelling = (
                ("{", "}", _entry_part) if mapped is self.val else (f"{class_name(type(self.val))}(", ")", _field_part)
            )
            shown = _elided_mapping(mapped, kept, *spelling)
            return self.error(
                f"Expected <{_capped(self.val) if shown is None else _truncated(shown)}> to match structure"
                f" {_elided_spec(spec, kept)}, but"
                f" {matcher.render_mismatch(mismatches)}."
                f"{under(class_in_spec((one.path.text, one.actual, one.literal) for one in mismatches))}",
                actual=self.val,
                expected=spec,
                diff=DiffResult(kind="match", entries=entries),
            )
        return self

    def is_callable(self) -> Self:
        """Asserts that val is callable.

        Examples:
            Usage:

                assert_that(lambda: None).is_callable()
                assert_that(print).is_callable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** callable
        """
        if not callable(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to be callable, but was not.")
        return self

    def is_not_callable(self) -> Self:
        """Asserts that val is not callable.

        Examples:
            Usage:

                assert_that(42).is_not_callable()
                assert_that('foo').is_not_callable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** callable
        """
        if callable(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to not be callable, but was.")
        return self

    def any_satisfy(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self:
        """Asserts that at least one item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy import match

                assert_that([1, -2, 3]).any_satisfy(match.is_negative())

            Usage with callables:

                assert_that([1, 2, 3]).any_satisfy(lambda x: x > 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if no item satisfies the matcher
        """
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        # resolving is what refuses, so the matcher is inspected once rather than here and again there
        reading = _resolved(matcher)
        apply = reading.apply  # read once: the attribute lookup is per item otherwise
        values = self._drained()
        # kept as the verdict walks them: the message names them, and a second walk is a read the verdict never made
        items = []
        for item in values:
            if apply(item):
                return self
            items.append(item)
        # asked once the verdict is in, since it is wanted only for the message
        description = reading.describe()
        return self.error(
            f"Expected any item to satisfy {description}, but none of the {len(items)} did.",
            actual=values,
            expected=description,
            diff=DiffResult(
                kind="match",
                entries=[
                    _ROOT.index(index).entry(actual=item, expected=description) for index, item in enumerate(items[:5])
                ],
            ),
        )

    def all_satisfy(self, matcher: Matcher[Any] | Callable[..., bool], *, allow_empty: bool = False) -> Self:
        """Asserts that all items in val satisfy the given matcher.

        Semantic alias for [`each()`][assertpy.base.BaseMixin.each].

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy import match

                assert_that([1, 2, 3]).all_satisfy(match.is_positive())

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item does **not** satisfy the matcher
        """
        if not _is_matcher(matcher) and not callable(matcher):
            refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        return self._every_item(matcher, allow_empty, "all_satisfy")

    def none_satisfy(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self:
        """Asserts that no item in val satisfies the given matcher.

        Args:
            matcher: a `Matcher` instance, or a callable that takes
                a value and returns a bool

        Examples:
            Usage with matchers:

                from assertpy import match

                assert_that([1, 2, 3]).none_satisfy(match.is_negative())

            Usage with callables:

                assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if any item satisfies the matcher
        """
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        if _is_matcher(matcher):
            for i, item in enumerate(self._walked()):
                if verdict(matcher.matches(item), subject="the matcher"):
                    return self.error(
                        f"Expected no item to satisfy {matcher.describe()},"
                        f" but item at index {i} <{_capped_format(item)}> did."
                    )
        elif callable(matcher):
            for i, item in enumerate(self._walked()):
                if verdict(cast("Callable[..., object]", matcher)(item)):
                    return self.error(
                        f"Expected no item to satisfy {_describe_matcher(matcher)},"
                        f" but item at index {i} <{_capped_format(item)}> did."
                    )
        else:
            refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))
        return self

    def satisfies_exactly(self, *matchers: Matcher[Any] | Callable[..., bool]) -> Self:
        """Asserts that val has exactly one item per matcher, each satisfying the matcher at its position.

        Unlike [`each()`][assertpy.base.BaseMixin.each] (one matcher applied to every item), this
        pairs the i-th item with the
        i-th matcher and additionally requires the lengths to match.  Every positional mismatch is
        reported, not just the first.

        Args:
            *matchers: one `Matcher` or callable predicate per expected item,
                applied in order

        Examples:
            Usage:

                from assertpy import match

                assert_that([1, "foo", 3.0]).satisfies_exactly(
                    match.is_odd(), match.is_instance_of(str), match.is_positive()
                )
                assert_that([2, 4]).satisfies_exactly(lambda x: x == 2, lambda x: x == 4)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the length differs, or any item does **not** satisfy its matcher
            TypeError: if val is not iterable, or a given arg is neither a Matcher nor callable
            ValueError: if no matchers are given
        """
        if len(matchers) == 0:
            raise ValueError("one or more args must be given")
        # before the value is read, as the any-order twin: the length decided, and `not_` passed an argument like `123`
        for matcher in matchers:
            if not isinstance(matcher, BaseMatcher) and not callable(matcher) and not _is_matcher(matcher):
                refuse(matcher, "a Matcher or a callable", subject=argument("matcher"))
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        items = list(self._walked())
        if len(items) != len(matchers):
            return self.error(
                f"Expected collection length <{len(matchers)}>, but was <{len(items)}>.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
            )
        entries = [
            _ROOT.index(index).entry(actual=item, expected=_describe_matcher(matcher))
            for index, (item, matcher) in enumerate(zip(items, matchers, strict=True))
            if not _apply_matcher(matcher, item)
        ]
        if entries:
            failed = "item" if len(entries) == 1 else "items"
            return self.error(
                f"Expected items to satisfy the given matchers in order, but {len(entries)} {failed} did not.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
                diff=DiffResult(kind="match", entries=entries),
            )
        return self

    def satisfies_exactly_in_any_order(self, *matchers: Matcher[Any] | Callable[..., bool]) -> Self:
        """Asserts that the items and the given matchers can be paired one-to-one, in any order.

        Like [`satisfies_exactly()`][assertpy.base.BaseMixin.satisfies_exactly] but ignoring
        positions: passes when some one-to-one assignment pairs every item with a distinct matcher
        it satisfies.  The lengths must still match, and no matcher may be reused for two items.

        Since every matcher is probed against every item, a probe that raises ``TypeError`` (a
        type-incompatible comparison on a mixed collection, like ``is_positive()`` meeting a string)
        counts as a non-match instead of crashing the pairing.  On failure, an unpaired matcher whose
        probes raised is annotated with the raise count in the diff, so a buggy predicate is not
        mistaken for an ordinary mismatch.

        Args:
            *matchers: one `Matcher` or callable predicate per expected item, in any order

        Examples:
            Usage:

                from assertpy import match

                assert_that(["foo", 3]).satisfies_exactly_in_any_order(
                    match.is_odd(), match.is_instance_of(str)
                )
                assert_that([2, 1]).satisfies_exactly_in_any_order(lambda x: x == 1, lambda x: x == 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the length differs, or no one-to-one pairing satisfies all matchers
            TypeError: if val is not iterable, or a given arg is neither a Matcher nor callable
            ValueError: if no matchers are given
        """
        if len(matchers) == 0:
            raise ValueError("one or more args must be given")
        # resolved here rather than asked again per item, and the resolution is what refuses a bad one
        appliers = [reading.apply for reading in (_resolved(matcher) for matcher in matchers)]
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        items = list(self._walked())
        if len(items) != len(matchers):
            return self.error(
                f"Expected collection length <{len(matchers)}>, but was <{len(items)}>.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
            )
        raised_counts = [0] * len(matchers)
        satisfied = []
        for item in items:
            row = []
            for column, apply in enumerate(appliers):
                try:
                    row.append(apply(item))
                except VerdictError:  # noqa: PERF203  # never a non-match, always a mistake
                    raise
                except TypeError:  # every probe may raise independently on a mixed collection
                    raised_counts[column] += 1
                    row.append(False)
            satisfied.append(row)
        assignment = _max_bipartite_assignment(satisfied)
        unpaired_items = [index for index, column in enumerate(assignment) if column is None]
        if unpaired_items:
            paired_columns = {column for column in assignment if column is not None}
            entries = [
                _ROOT.member(items[index], "extra").entry(actual=items[index], expected=None, absent="expected")
                for index in unpaired_items
            ]
            entries.extend(
                DiffEntry(
                    path="missing",
                    actual=None,
                    absent="actual",
                    expected=_describe_unpaired(matcher, raised_counts[column]),
                )
                for column, matcher in enumerate(matchers)
                if column not in paired_columns
            )
            failed = "item" if len(unpaired_items) == 1 else "items"
            return self.error(
                f"Expected items to satisfy the given matchers in any order,"
                f" but no pairing covers {len(unpaired_items)} {failed}.",
                actual=self.val,
                expected=[_describe_matcher(matcher) for matcher in matchers],
                diff=DiffResult(kind="contains", entries=entries),
            )
        return self

    def zip_satisfies(
        self, other: Iterable[object], predicate: Callable[..., bool], *, allow_empty: bool = False
    ) -> Self:
        """Asserts that each pair from zipping val with other satisfies the two-arg predicate.

        Pairs the i-th item of val with the i-th item of ``other`` and checks ``predicate(a, b)``.
        The two iterables must have equal length.  Every failing pair is reported.

        Args:
            other: the iterable to zip with val
            predicate: a two-arg callable returning a bool, applied to each ``(val_item, other_item)`` pair

        Examples:
            Usage:

                assert_that([1, 2, 3]).zip_satisfies([2, 4, 6], lambda a, b: b == a * 2)
                assert_that(["a", "bb"]).zip_satisfies([1, 2], lambda s, n: len(s) == n)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the lengths differ, or any pair does **not** satisfy the predicate
            TypeError: if val or other is not iterable, or predicate is not callable
        """
        if not callable(predicate):
            refuse(predicate, "callable", subject=argument("predicate"))
        if not isinstance(self.val, collections.abc.Iterable):
            refuse(self.val, "iterable")
        if not isinstance(other, collections.abc.Iterable):
            refuse(other, "iterable", subject=argument("other"))
        val_items = list(self._walked())
        other_items = list(other)
        if len(val_items) != len(other_items):
            return self.error(
                f"Expected collection length <{len(other_items)}>, but was <{len(val_items)}>.",
                actual=self.val,
                expected=other,
            )
        # warned here: a length mismatch is the verdict, and warning first said the call passed over nothing
        if not val_items:
            _warn_vacuous(self, "zip_satisfies", allow_empty)
        entries = [
            _ROOT.index(index).entry(actual=val_item, expected=other_item)
            for index, (val_item, other_item) in enumerate(zip(val_items, other_items, strict=True))
            if not verdict(predicate(val_item, other_item))
        ]
        if entries:
            failed = "pair" if len(entries) == 1 else "pairs"
            return self.error(
                f"Expected paired items to satisfy <{predicate}>, but {len(entries)} {failed} did not.",
                actual=self.val,
                expected=other,
                diff=DiffResult(kind="match", entries=entries),
            )
        return self
