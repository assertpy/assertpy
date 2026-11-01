from __future__ import annotations

import decimal
from types import GenericAlias
from typing import TYPE_CHECKING, SupportsIndex

from ._engine._compare import (
    _EQ_ATOMIC,
    _ambiguous_array_operand,
    _array_equality_error,
    _build_compare_config,
    _config_note,
    _guarded_equal,
    _kinds_never_equal,
    _node_decision,
    _resolve_comparator,
    _types_differ,
)
from ._engine._diff import _build_equality_diff, _child_entries
from ._engine._equality import (
    fields_pair,
    filtered_to_nothing,
    key_specs_given,
    mapping_shaped,
)
from ._engine._introspection import is_namedtuple
from ._engine._ordering import require_integer
from ._engine._path import _ROOT
from ._engine._require import argument, refuse, reject_unknown_kwargs, require_type, sized_len, verdict
from ._hints import identity_candidate
from ._matcher_impls import _is_matcher, _outcome_of, _ReadOnce, _require_class_info
from ._satisfies import SatisfiesMixin, _guarding, _warn_nothing_compared
from .errors import _capped, _capped_format, _disambiguated, _safe_str, _told_apart, _truncated, _type_expression_name
from .helpers import _both_list_like, _elided_seq_repr, _elided_text_repr

if TYPE_CHECKING:
    from ._engine._compare import _CompareConfig
    from ._engine._compat import Self
    from ._matcher_impls import ClassInfo, Matcher

__tracebackhide__ = True

_IS_EQUAL_TO_OPTIONS = frozenset(
    {"ignore", "include", "tolerance", "rel", "comparators", "ignore_null", "strict_types"}
)


class BaseMixin(SatisfiesMixin):
    """Base mixin."""

    def described_as(self, description: str) -> Self:
        """Describes the assertion.  On failure, the description is included in the error message.

        This is not an assertion itself.  But if the any of the following chained assertions fail,
        the description will be included in addition to the regular error message.

        Args:
            description: the error message description

        Examples:
            Usage:

                assert_that(1).described_as('error msg desc').is_equal_to(2)  # fails
                # [error msg desc] Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion
        """
        self.description: str = str(description)
        return self

    def is_equal_to(self, other: object, **kwargs: object) -> Self:
        """Asserts that val is equal to other.

        Checks actual is equal to expected using the ``==`` operator. When val is *dict-like*
        or has introspectable fields (dataclass, namedtuple, attrs, Pydantic model),
        optionally ignore or include keys/fields when checking equality.

        Args:
            other: the expected value
            **kwargs: see below

        Keyword Args:
            ignore (Hashable | list | set | frozenset | None): the key/field (or list/set/frozenset of
                keys/fields) to ignore.  Besides exact keys and nested-path tuples, a ``re.Pattern`` matches
                field names by regex and a ``type`` matches fields by value type.
            include (Hashable | list | set | frozenset | None): the key/field (or list/set/frozenset of
                keys/fields) to include.  Accepts the same ``re.Pattern`` / ``type`` specs as ``ignore``.  A
                key the value does not have fails the assertion with or without ``not_``.
            tolerance (float | None): an absolute tolerance that widens ``==`` for every pair of real-number
                leaves anywhere in the structure: a pair ``==`` holds equal stays equal, and any other is
                measured as [`is_close_to()`][assertpy.numeric.NumericMixin.is_close_to] measures it.
            comparators (dict | None): a dict mapping a ``type`` or a field name to an
                ``(actual, expected) -> bool`` predicate that alone decides every node it matches, the root
                included, even inside a container whose ``==`` holds; a field-name key wins over a type
                key.  Mapping keys, set members and whatever a container shared by both sides holds are
                left to ``==``.
            ignore_null (bool): when ``True``, skip any named field the *expected* side leaves ``None``
                (a partial expected/template), at any depth.  Only the expected side is skipped, so an
                unexpectedly ``None`` actual field is still reported.  Defaults to ``False``.
            strict_types (bool): when ``True``, both sides of every node must be the same type, at any
                depth.  Plain ``==`` does not require this: ``True == 1``, ``Decimal("1") == 1`` and
                ``[True] == [1]`` are all true, so a boolean read from JSON compares equal to an
                integer without a word.  Opting in also rejects pairs some callers consider equal
                (``IntEnum`` against ``int``, a ``dict`` subclass against ``dict``, ``float`` against
                ``int``), and it wins over ``tolerance``, which says how far apart two numbers may be
                and not that they may be different types.  A ``comparators`` entry still decides the
                nodes it matches ahead of it, the root included, and a `Matcher` on the expected side is
                exempt, so composed matchers keep working.  Dictionary keys and set elements are covered
                too, although a container matches them by hash before any type is looked at: ``{True: "a"}`` against
                ``{1: "a"}`` and ``{1}`` against ``{1.0}`` both fail, as ``[True]`` against ``[1]``
                does.  Defaults to ``False``.

        Examples:
            Usage:

                assert_that(1 + 2).is_equal_to(3)
                assert_that('foo').is_equal_to('foo')
                assert_that(123).is_equal_to(123)
                assert_that(123.4).is_equal_to(123.4)
                assert_that(['a', 'b']).is_equal_to(['a', 'b'])
                assert_that((1, 2, 3)).is_equal_to((1, 2, 3))
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1, 'b': 2})
                assert_that({'a', 'b'}).is_equal_to({'a', 'b'})

            When the val is *dict-like*, keys can optionally be *ignored* when checking equality:

                # ignore a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, ignore='b')

                # ignore multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1}, ignore=['b', 'c'])

                # ignore nested keys
                assert_that({'a': {'b': 2, 'c': 3, 'd': 4}}).is_equal_to(
                    {'a': {'d': 4}}, ignore=[('a', 'b'), ('a', 'c')]
                )

            When the val is *dict-like*, only certain keys can be *included* when checking equality:

                # include a single key
                assert_that({'a': 1, 'b': 2}).is_equal_to({'a': 1}, include='a')

                # include multiple keys
                assert_that({'a': 1, 'b': 2, 'c': 3}).is_equal_to({'a': 1, 'b': 2}, include=['a', 'b'])

            Works with dataclasses, namedtuples, attrs, and Pydantic models:

                @dataclass
                class User:
                    id: int
                    name: str

                assert_that(User(id=1, name="Alice")).is_equal_to(User(id=99, name="Alice"), ignore="id")

            Compares lists of objects pairwise:

                actual = [User(id=1, name="Alice"), User(id=2, name="Bob")]
                expected = [User(id=99, name="Alice"), User(id=99, name="Bob")]
                assert_that(actual).is_equal_to(expected, ignore="id")

            Compare nested floats with an absolute tolerance, or supply custom comparators:

                assert_that({"price": 1.0001}).is_equal_to({"price": 1.0}, tolerance=0.001)

                # by type, or by field name (field name wins over type)
                assert_that(actual).is_equal_to(expected, comparators={float: lambda a, e: round(a, 2) == round(e, 2)})
                assert_that(actual).is_equal_to(expected, comparators={"name": lambda a, e: a.lower() == e.lower()})

            Ignore fields by regex or by type:

                import re

                assert_that(payload).is_equal_to(expected, ignore=re.compile(r"^_"))  # ignore private-ish keys
                assert_that(payload).is_equal_to(expected, ignore=float)               # ignore all float fields

            Require the same type at every level, which plain ``==`` does not:

                assert_that({"active": True}).is_equal_to({"active": 1})                     # passes
                assert_that({"active": True}).is_equal_to({"active": 1}, strict_types=True)  # fails

            Failure produces a nice error message:

                assert_that(1).is_equal_to(2)  # fails
                # Expected <1> to be equal to <2>, but was not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** equal to expected
            TypeError: if ``ignore``/``include`` is a one-shot or otherwise unsupported iterable, or is
                used on a value that is neither dict-like nor has introspectable fields; if ``tolerance`` is
                not a real number or ``comparators`` is not a dict of callables; or if val or other is (or
                contains, at any nesting depth) an element-wise array/frame-like (numpy/pandas/polars) whose
                ``==`` has no single truth value (compare the value's own equality, e.g.
                ``actual.equals(expected)``, instead)
            ValueError: if ``tolerance`` is ``NaN`` or negative

        Tip:
            Using [`is_equal_to()`][assertpy.base.BaseMixin.is_equal_to] with a ``float`` val is just
            asking for trouble. Instead, you'll
            always want to use *fuzzy* numeric assertions
            like [`is_close_to()`][assertpy.numeric.NumericMixin.is_close_to]
            or [`is_between()`][assertpy.numeric.NumericMixin.is_between].

        See Also:
            [`is_equal_to_ignoring_case()`][assertpy.string.StringMixin.is_equal_to_ignoring_case] -
                for case-insensitive string equality
        """
        if not kwargs:
            if type(self.val) in _EQ_ATOMIC and type(other) in _EQ_ATOMIC:
                # atomic scalars: no array or dict likeness, and `==` yields a real bool
                try:
                    if self.val == other:
                        return self
                except decimal.InvalidOperation:
                    pass  # only a signalling `Decimal` NaN signals between two atomic scalars, and it equals nothing
                if isinstance(self.val, str) and isinstance(other, str):
                    actual_repr = _truncated(_elided_text_repr(self.val, other))
                    expected_repr = _truncated(_elided_text_repr(other, self.val))
                else:
                    actual_repr, expected_repr = _disambiguated(self.val, other)
                diff = _build_equality_diff(self.val, other)
                self._compared = (self.val, other)
                return self.error(
                    f"Expected <{actual_repr}> to be equal to <{expected_repr}>, but was not.",
                    actual=self.val,
                    expected=other,
                    diff=diff,
                )
            ignore = include = config = None
        else:
            reject_unknown_kwargs(kwargs, _IS_EQUAL_TO_OPTIONS, "is_equal_to")
            ignore = kwargs.get("ignore")
            include = kwargs.get("include")
            config = _build_compare_config(
                kwargs.get("tolerance"),
                kwargs.get("comparators"),
                kwargs.get("ignore_null", False),
                kwargs.get("strict_types", False),
                kwargs.get("rel"),
            )

        operand = _ambiguous_array_operand(self.val, other)
        if operand is not None:
            raise _array_equality_error("is_equal_to", operand)

        # cleared however this leaves, since a soft block goes on using the builder after a failure it collected
        # stored only for a call given comparators: a second attribute stored on every one cost a passing dict 200 ns
        compared_through = config is not None and bool(config.comparators)
        enclosing = False
        try:
            if compared_through:
                enclosing, self._comparators_took_part = self._comparators_took_part, True
            compared = self._compare_to(other, ignore=ignore, include=include, config=config)
        finally:
            self._equality_comparison = False
            if compared_through:
                # as it was: a comparator may assert on this same builder while the comparison it serves runs
                self._comparators_took_part = enclosing
        if self._compared_nothing:
            self._compared_nothing = False
            _warn_nothing_compared()
        return compared

    def _compare_to(self, other: object, *, ignore: object, include: object, config: _CompareConfig | None) -> Self:
        """The dispatch of `is_equal_to` once its options are parsed, so the caller can scope them."""
        # read once: code of the value can put another on the builder while it is compared and printed
        val = self.val
        if config is not None and config.comparators and _resolve_comparator(val, config, field=None) is not None:
            # a comparator owns the root as it owns any node, ahead of strict types and of the key walk
            return self._config_verdict(other, config)
        if config is not None and config.strict_types and _types_differ(val, other):
            # the key walk never sees the pair, so an OrderedDict against a dict would pass a strict comparison
            actual_repr, expected_repr = _disambiguated(val, other)
            return self.error(
                f"Expected <{actual_repr}> to be equal to <{expected_repr}>, but was not.{_config_note(config)}",
                actual=val,
                expected=other,
                diff=_build_equality_diff(val, other, config=config),
            )

        if mapping_shaped(val, check_values=False) and mapping_shaped(other, check_values=False):
            if self._dict_not_equal(val, other, ignore=ignore, include=include, config=config):
                self._dict_err(val, other, ignore=ignore, include=include, config=config)
            else:
                self._note_if_nothing_compared(val, other, ignore=ignore, include=include)
        elif key_specs_given(ignore) or key_specs_given(include):
            val_is_namedtuple = is_namedtuple(val)
            other_is_namedtuple = is_namedtuple(other)
            if (
                isinstance(val, (list, tuple))
                and isinstance(other, (list, tuple))
                and not val_is_namedtuple
                and not other_is_namedtuple
            ):
                self._seq_equal_with_filter(val, other, ignore=ignore, include=include, config=config)
            else:
                self._obj_equal_with_filter(val, other, ignore=ignore, include=include, config=config)
        elif config is not None:
            return self._config_verdict(other, config)
        else:
            # the one branch deciding with `==`, asked first since a type may rewrite its own `__eq__` while answering
            self._equality_comparison = identity_candidate(val, other)
            if not _guarded_equal(val, other):
                if _both_list_like(val, other):
                    actual_repr = _truncated(_elided_seq_repr(val, other))
                    expected_repr = _truncated(_elided_seq_repr(other, val))
                else:
                    actual_repr, expected_repr = _disambiguated(val, other)
                diff = _build_equality_diff(val, other)
                self._compared = (val, other)
                return self.error(
                    f"Expected <{actual_repr}> to be equal to <{expected_repr}>, but was not.",
                    actual=val,
                    expected=other,
                    diff=diff,
                )
        return self

    def _config_verdict(self, other: object, config: _CompareConfig) -> Self:
        """`is_equal_to` under a compare config, decided by the structural walk from the root down."""
        diff = _build_equality_diff(self.val, other, config=config)
        if diff.entries:
            actual_text, expected_text = _told_apart(
                _truncated(_safe_str(self.val)), _truncated(_safe_str(other)), self.val, other
            )
            return self.error(
                f"Expected <{actual_text}> to be equal to <{expected_text}>, but was not.{_config_note(config)}",
                actual=self.val,
                expected=other,
                diff=diff,
            )
        return self

    def _obj_equal_with_filter(self, actual, expected, *, ignore=None, include=None, config=None):
        """Compare two objects by converting to dicts and applying ignore/include filters."""
        # a plain dict against an object is what the sequence path already compares element by element
        actual_dict, expected_dict = fields_pair(actual, expected)
        if actual_dict is None or expected_dict is None:
            raise TypeError(
                "ignore/include requires dict-like objects or objects with introspectable fields"
                " (dataclass, namedtuple, attrs, Pydantic model, or object with __dict__)"
            )
        if self._dict_not_equal(actual_dict, expected_dict, ignore=ignore, include=include, config=config):
            # a dict read beside a record is a copy, and the failure hands back the caller's own
            held = (
                actual if isinstance(actual, dict) else actual_dict,
                expected if isinstance(expected, dict) else expected_dict,
            )
            self._dict_err(actual_dict, expected_dict, ignore=ignore, include=include, config=config, held=held)
        else:
            self._note_if_nothing_compared(actual_dict, expected_dict, ignore=ignore, include=include)

    def _note_if_nothing_compared(self, actual: object, expected: object, *, ignore: object, include: object) -> None:
        """Keep, for `is_equal_to` to warn about, a pass whose key filter left nothing to compare."""
        if (
            (ignore is not None or include is not None)
            and _guarding(self)
            and filtered_to_nothing(actual, expected, ignore=ignore, include=include)
        ):
            self._compared_nothing = True

    def _seq_equal_with_filter(self, actual, expected, *, ignore=None, include=None, config=None):
        """Compare two sequences pairwise, an element with fields through them under ``ignore``/``include``.

        The first element that differs, or a length that does, ends the comparison, and the failure is one for the
        two sequences, as a dict's is.  It used to be the element's own, which said neither where it stood nor what
        else differed, and a length or a plain element failed with no diff at all.  A list is no tuple under a
        key option either, where the ``==`` of both declines the other (`_kinds_never_equal`).
        """
        if len(actual) == len(expected) and not _kinds_never_equal(actual, expected):
            for actual_item, expected_item in zip(actual, expected, strict=True):
                differs = self._item_differs(actual_item, expected_item, ignore, include, config)
                if differs is None:
                    return
                if differs:
                    break
            else:
                return
        self._dict_err(actual, expected, ignore=ignore, include=include, config=config)

    def _item_differs(self, actual_item, expected_item, ignore, include, config) -> bool | None:
        """Whether one element of a sequence differs from its counterpart, or ``None`` once a prerequisite failed."""
        actual_fields, expected_fields = fields_pair(actual_item, expected_item)
        if actual_fields is not None and expected_fields is not None:
            return self._dict_not_equal(actual_fields, expected_fields, ignore=ignore, include=include, config=config)
        decision = _node_decision(actual_item, expected_item, config)
        if decision in ("strict", "unanswered") or (decision == "recurse" and config is not None):
            # the walk decides where `==` alone cannot: under strict types, on a graph, or under a config
            return bool(_child_entries(actual_item, expected_item, _ROOT, descended_for=decision, config=config))
        return decision != "equal"

    def is_not_equal_to(self, other: object) -> Self:
        """Asserts that val is not equal to other.

        Checks actual is not equal to expected using the ``==`` operator, the question `is_equal_to`
        asks.  ``!=`` is never asked: a type's ``__ne__`` need not be the negation of its ``__eq__``.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that(1 + 2).is_not_equal_to(4)
                assert_that('foo').is_not_equal_to('bar')
                assert_that(123).is_not_equal_to(456)
                assert_that(123.4).is_not_equal_to(567.8)
                assert_that(['a', 'b']).is_not_equal_to(['c', 'd'])
                assert_that((1, 2, 3)).is_not_equal_to((1, 2, 4))
                assert_that({'a': 1, 'b': 2}).is_not_equal_to({'a': 1, 'b': 3})
                assert_that({'a', 'b'}).is_not_equal_to({'a', 'x'})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual **is** equal to expected
            TypeError: if val or other is (or contains, at any nesting depth) an element-wise
                array/frame-like (numpy/pandas/polars) whose ``==`` has no single truth value; compare
                the value's own equality instead
        """
        operand = _ambiguous_array_operand(self.val, other)
        if operand is not None:
            raise _array_equality_error("is_not_equal_to", operand)

        if _guarded_equal(self.val, other, method="is_not_equal_to"):
            return self.error(
                f"Expected <{_truncated(_safe_str(self.val))}> to be not equal to"
                f" <{_truncated(_safe_str(other))}>, but was."
            )
        return self

    def is_same_as(self, other: object) -> Self:
        """Asserts that val is identical to other.

        Checks actual is identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Basic types are identical:

                assert_that(1).is_same_as(1)
                assert_that('foo').is_same_as('foo')
                assert_that(123.4).is_same_as(123.4)

            As are immutables like ``tuple``:

                assert_that((1, 2, 3)).is_same_as((1, 2, 3))

            But mutable collections like ``list``, ``dict``, and ``set`` are not:

                # these all fail...
                assert_that(['a', 'b']).is_same_as(['a', 'b'])  # fails
                assert_that({'a': 1, 'b': 2}).is_same_as({'a': 1, 'b': 2})  # fails
                assert_that({'a', 'b'}).is_same_as({'a', 'b'})  # fails

            Unless they are the same object:

                x = {'a': 1, 'b': 2}
                y = x
                assert_that(x).is_same_as(y)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** identical to expected
        """
        if self.val is not other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be identical to <{_capped_format(other)}>, but was not.",
                expected=other,
            )
        return self

    def is_not_same_as(self, other: object) -> Self:
        """Asserts that val is not identical to other.

        Checks actual is not identical to expected using the ``is`` operator.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that(1).is_not_same_as(2)
                assert_that('foo').is_not_same_as('bar')
                assert_that(123.4).is_not_same_as(567.8)
                assert_that((1, 2, 3)).is_not_same_as((1, 2, 4))

                # mutable collections, even if equal, are not identical...
                assert_that(['a', 'b']).is_not_same_as(['a', 'b'])
                assert_that({'a': 1, 'b': 2}).is_not_same_as({'a': 1, 'b': 2})
                assert_that({'a', 'b'}).is_not_same_as({'a', 'b'})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual **is** identical to expected
        """
        if self.val is other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be not identical to <{_capped_format(other)}>, but was."
            )
        return self

    def is_true(self) -> Self:
        """Asserts that val is true.

        Examples:
            Usage:

                assert_that(True).is_true()
                assert_that(1).is_true()
                assert_that('foo').is_true()
                assert_that(1.0).is_true()
                assert_that(['a', 'b']).is_true()
                assert_that((1, 2, 3)).is_true()
                assert_that({'a': 1, 'b': 2}).is_true()
                assert_that({'a', 'b'}).is_true()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** false
            TypeError: if val is a coroutine, since every coroutine is truthy and this would hold
                whatever awaiting it would have answered
        """
        if not verdict(self.val, subject="the call under test"):
            return self.error(f"Expected <{_capped(self.val)}> to be <True>, but was not.", expected=True)
        return self

    def is_false(self) -> Self:
        """Asserts that val is false.

        Examples:
            Usage:

                assert_that(False).is_false()
                assert_that(0).is_false()
                assert_that('').is_false()
                assert_that(0.0).is_false()
                assert_that([]).is_false()
                assert_that(()).is_false()
                assert_that({}).is_false()
                assert_that(set()).is_false()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** true
            TypeError: if val is a coroutine, since every coroutine is truthy and this would refuse
                whatever awaiting it would have answered
        """
        if verdict(self.val, subject="the call under test"):
            return self.error(f"Expected <{_capped(self.val)}> to be <False>, but was not.", expected=False)
        return self

    def is_none(self) -> Self:
        """Asserts that val is none.

        Examples:
            Usage:

                assert_that(None).is_none()
                assert_that(print('hello world')).is_none()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** none
        """
        if self.val is not None:
            return self.error(f"Expected <{_capped(self.val)}> to be <None>, but was not.", expected=None)
        return self

    def is_not_none(self) -> Self:
        """Asserts that val is not none.

        Examples:
            Usage:

                assert_that(0).is_not_none()
                assert_that('foo').is_not_none()
                assert_that(False).is_not_none()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** none
        """
        if self.val is None:
            return self.error("Expected not <None>, but was.")
        return self

    @staticmethod
    def _type(val):
        if hasattr(val, "__name__"):
            return val.__name__
        return val.__class__.__name__

    def is_type_of(self, some_type: type) -> Self:
        """Asserts that val is of the given type.

        Args:
            some_type (type): the expected type

        Examples:
            Usage:

                assert_that(1).is_type_of(int)
                assert_that('foo').is_type_of(str)
                assert_that(123.4).is_type_of(float)
                assert_that(['a', 'b']).is_type_of(list)
                assert_that((1, 2, 3)).is_type_of(tuple)
                assert_that({'a': 1, 'b': 2}).is_type_of(dict)
                assert_that({'a', 'b'}).is_type_of(set)
                assert_that(True).is_type_of(bool)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** of the given type
        """
        if type(some_type) is not type and not issubclass(type(some_type), type):
            refuse(some_type, "a type", subject=argument("type"))
        if type(self.val) is not some_type:
            type_name = self._type(self.val)
            return self.error(
                f"Expected <{_capped(self.val)}:{type_name}> to be of type <{some_type.__name__}>, but was not.",
                expected=some_type,
            )
        return self

    def is_instance_of(self, some_class: ClassInfo) -> Self:
        """Asserts that val is an instance of the given class.

        Args:
            some_class: the expected class, a union of them, or a tuple nested to any depth

        Examples:
            Usage:

                assert_that(1).is_instance_of(int)
                assert_that('foo').is_instance_of(str)
                assert_that(123.4).is_instance_of(float)
                assert_that(['a', 'b']).is_instance_of(list)
                assert_that((1, 2, 3)).is_instance_of(tuple)
                assert_that({'a': 1, 'b': 2}).is_instance_of(dict)
                assert_that({'a', 'b'}).is_instance_of(set)
                assert_that(True).is_instance_of(bool)

            With a user-defined class:

                class Foo: pass
                f = Foo()
                assert_that(f).is_instance_of(Foo)
                assert_that(f).is_instance_of(object)

            With alternatives, anything `isinstance` takes, nested to any depth:

                assert_that(1).is_instance_of(int | str)
                assert_that(1).is_instance_of((int, str))
                assert_that(1).is_instance_of((int, (str, bytes)))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** an instance of the given class
            TypeError: if the given arg, or any member of a union or tuple, is not a class
        """
        # a class answers `isinstance` itself, raising what it raises, though a generic alias passes for one on 3.10
        if not isinstance(some_class, type) or isinstance(some_class, GenericAlias):
            _require_class_info(some_class, name="class", probe=self.val)
        if not isinstance(self.val, some_class):
            type_name = self._type(self.val)
            some_class_name = _type_expression_name(some_class)
            return self.error(
                f"Expected <{_capped(self.val)}:{type_name}> to be instance of class <{some_class_name}>, but was not.",
                expected=some_class,
            )
        return self

    def is_instance_of_any(self, *some_classes: ClassInfo) -> Self:
        """Asserts that val is an instance of at least one of the given classes.

        Args:
            *some_classes: the candidate classes, each a class, a union of them, or a nested tuple

        Examples:
            Usage:

                assert_that(1).is_instance_of_any(int, float)
                assert_that('foo').is_instance_of_any(str, bytes)
                assert_that(TimeoutError()).is_instance_of_any(OSError, ValueError)
                assert_that(1).is_instance_of_any(int | str, (bytes, bytearray))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** an instance of any of the given classes
            TypeError: if a given arg is not a class
            ValueError: if no classes are given
        """
        if len(some_classes) == 0:
            raise ValueError("one or more args must be given")
        _require_class_info(some_classes, name="class", expectation="classes", probe=self.val)
        if not isinstance(self.val, some_classes):
            type_name = self._type(self.val)
            class_names = ", ".join(_type_expression_name(some_class) for some_class in some_classes)
            return self.error(
                f"Expected <{_capped(self.val)}:{type_name}> to be instance of any of <{class_names}>, but was not.",
                expected=some_classes,
            )
        return self

    def is_subclass_of(self, some_class: ClassInfo) -> Self:
        """Asserts that val is a class and is a subclass of the given class.

        Checks the class hierarchy using the ``issubclass()`` built-in, so a class counts as a
        subclass of itself.

        Args:
            some_class: the expected ancestor class, a union of them, or a tuple nested to any depth

        Examples:
            Usage:

                assert_that(bool).is_subclass_of(int)
                assert_that(TimeoutError).is_subclass_of(OSError)

                class Base: pass
                class Derived(Base): pass

                assert_that(Derived).is_subclass_of(Base)
                assert_that(Derived).is_subclass_of(Derived)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** a subclass of the given class
            TypeError: if val or the given arg, or any member of a union or tuple, is not a class
        """
        require_type(self.val, type, "a class")
        # as in `is_instance_of`, with `issubclass` asking each member
        if not isinstance(some_class, type) or isinstance(some_class, GenericAlias):
            _require_class_info(some_class, name="class", probe=self.val, check=issubclass)
        if not issubclass(self.val, some_class):
            expected_name = _type_expression_name(some_class)
            return self.error(
                f"Expected <{self.val.__name__}> to be subclass of <{expected_name}>, but was not.",
                expected=some_class,
            )
        return self

    def is_length(self, length: SupportsIndex | Matcher[int]) -> Self:
        """Asserts that val is the given length.

        Checks val is the given length using the ``len()`` built-in.  A matcher in place of the number is
        asked about the length, so a bound or a range reads as one assertion: ``is_length(match.between(2,
        5))``.

        Args:
            length (int | Matcher): the expected length, or a matcher the length has to satisfy

        Examples:
            Usage:

                assert_that('foo').is_length(3)
                assert_that(['a', 'b']).is_length(2)
                assert_that((1, 2, 3)).is_length(3)
                assert_that({'a': 1, 'b': 2}).is_length(2)
                assert_that({'a', 'b'}).is_length(2)
                assert_that(['a', 'b']).is_length(match.greater_than(1))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** the given length
        """
        if _is_matcher(length):
            return self._length_satisfies(length)
        wanted = length if type(length) is int else require_integer(length, "length")
        if wanted < 0:
            raise ValueError("given arg must be a positive int")
        if sized_len(self.val) != wanted:
            return self.error(
                f"Expected <{_capped(self.val)}> to be of length <{length}>, but was <{sized_len(self.val)}>.",
                expected=length,
            )
        return self

    def _length_satisfies(self, matcher: Matcher[int]) -> Self:
        """`is_length()` with a matcher for the length, which is asked about the number `len()` gives."""
        size = sized_len(self.val)
        outcome = _outcome_of(matcher, _ReadOnce(size))
        if outcome is not None:
            # the reason a leaf gives about a bare number is that number again
            reason = "" if outcome.mismatch == f"was <{size}>" else f": {outcome.mismatch}"
            return self.error(
                f"Expected <{_capped(self.val)}> to have a length that is {outcome.description},"
                f" but was <{size}>{reason}.",
                expected=matcher,
            )
        return self

    def is_length_between(self, low: SupportsIndex, high: SupportsIndex) -> Self:
        """Asserts that val's length is between low and high (both inclusive).

        Checks val's length using the ``len()`` built-in, like
        [`is_length()`][assertpy.base.BaseMixin.is_length].  Identical to
        [`has_size_between()`][assertpy.collection.CollectionMixin.has_size_between] apart from
        the error message wording.

        Args:
            low: the inclusive lower length bound
            high: the inclusive upper length bound

        Examples:
            Usage:

                assert_that('foo').is_length_between(1, 5)
                assert_that(['a', 'b']).is_length_between(2, 2)
                assert_that((1, 2, 3)).is_length_between(0, 3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** between low and high
            TypeError: if a given arg is not an int
            ValueError: if a given arg is negative, or low is greater than high
        """
        least = low if type(low) is int else require_integer(low, "low")
        most = high if type(high) is int else require_integer(high, "high")
        if least < 0 or most < 0:
            raise ValueError("given args must be positive ints")
        if least > most:
            raise ValueError("given low arg must be less than given high arg")
        if not least <= sized_len(self.val) <= most:
            return self.error(
                f"Expected <{_capped(self.val)}> to be of length between <{low}> and <{high}>, "
                f"but was <{sized_len(self.val)}>.",
                expected=(low, high),
            )
        return self
