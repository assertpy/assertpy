"""Equality as one decision, reachable from every spelling of it.

The comparison itself was already shared: one walker, one compare config.  What was not shared was the
way in: the recursive mapping comparison and the ignore/include filtering were methods on the builder's
mixin, so a matcher could not use them.  The visible consequence was not a wrong answer but a missing
one: `assert_that(v).is_equal_to(x, tolerance=0.1)` worked and `match.equal_to(x, tolerance=0.1)` raised
`TypeError`, which meant a structural spec could not express "close enough" or "ignore this field" at all.

These tests hold the two spellings together, and hold the core to the behaviour it had before the move.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import fractions
import itertools
import math
import operator
import traceback
import unicodedata
import unittest.mock
from dataclasses import dataclass

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, BaseMatcher, assert_that, assert_warn, match, soft_assertions
from assertpy._engine._compare import (
    WindowRefusedError,
    _both_decline,
    _CompareConfig,
    _declines,
    tolerance_window,
)
from assertpy._engine._diff import _stored_members
from assertpy._engine._equality import (
    IncludeKeysMissingError,
    ignore_specs,
    include_specs,
    mapping_differs,
    mapping_shaped,
    values_differ,
)
from assertpy._engine._introspection import materialized
from assertpy._engine._membership import (
    MembershipRefusedError,
    _classified,
    _hash_safe,
    has_duplicates,
    missing_items,
    not_contained_in,
    occurrences,
    only_faults,
    repeated_items,
    searchable,
)
from assertpy._engine._ordering import (
    UnorderableError,
    compare,
    first_out_of_order,
    first_plainly_out_of_order,
    holds,
    plainly_sortable,
)
from assertpy._engine._size import length_of
from assertpy._engine._text import contains as text_contains
from assertpy._engine._text import starts_with as text_starts_with
from assertpy.errors import _json_safe
from assertpy.matchers import _is_matcher
from tests.group_compat import ExceptionGroup, needs_groups


@dataclass
class Reading:
    sensor: str
    value: float


class _ByField:
    """Equality by field, hash by identity: the pair a set cannot answer for.

    Written by hand rather than taken from a library because that is how it appears in real suites, and
    it is the value that decides whether a set may stand in for a walk.
    """

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _ByField) and other.value == self.value

    def __hash__(self) -> int:
        return id(self)


class _NoHash:
    """Inherited equality, but explicitly unhashable, which the type rule alone would not notice."""

    __hash__ = None


class _EqualToAnything:
    def __eq__(self, other):
        return True

    __hash__ = None


class _Counted(int):
    """A subclass that changes neither operation, so it answers exactly as `int` does."""


class _HashesLikeText(int):
    """One operation inherited and the other replaced, which is the disagreement the rule looks for."""

    __hash__ = str.__hash__


class _Status(str, enum.Enum):
    """Spelled with the mixin rather than as `enum.StrEnum`, which arrived in 3.11 and this suite runs 3.10.

    Identical where it matters: both take `__eq__` and `__hash__` from `str`, which is what the rule reads.
    """

    PAID = "paid"
    DUE = "due"


class _Split:
    """`==` and `!=` both say yes, which is what a `str` or `dict` subclass replacing `__eq__` alone does."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return True

    __hash__ = None

    def __repr__(self) -> str:
        return f"_Split({self.value})"


class _NeverEqual:
    """`==` and `!=` both say no, so asking `!=` passed an equality `==` refuses."""

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = None


class _Clause:
    """What an expression DSL hands back from a comparison: an object, truthy, and not a bool."""


class _Column:
    """`==` and `!=` both build a truthy `_Clause`."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):
        return _Clause()

    def __ne__(self, other):
        return _Clause()

    __hash__ = None


class _NeRaises:
    """Equality by value and an `__ne__` that raises: `!=` was an error where `==` has an answer."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _NeRaises) and other.value == self.value

    def __ne__(self, other: object) -> bool:
        raise RuntimeError("__ne__ was asked")

    __hash__ = None


class _CaseInsensitive(str):
    """Replaces `__eq__` alone, so `!=` is still `str.__ne__` and calls "Ada" and "ada" unequal."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, str) and self.casefold() == other.casefold()

    def __hash__(self) -> int:
        return hash(self.casefold())


class _WithinOne(int):
    """Replaces `__eq__` alone, so `!=` is still `int.__ne__`."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, int) and abs(int(self) - int(other)) <= 1

    __hash__ = int.__hash__


class _CaseFoldedBytes(bytes):
    """Replaces `__eq__` alone, so `!=` is still `bytes.__ne__`."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, bytes) and self.lower() == other.lower()

    __hash__ = bytes.__hash__


class _OrderSensitive(dict):
    """Replaces `__eq__` with one that reads the order too, so `dict.__ne__` calls a reordered copy equal."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, dict) and list(self.items()) == list(other.items())

    __hash__ = None


@dataclass(eq=False)
class _AnsweringInequality:
    """Leaves `__eq__` to `object` and answers `!=` itself, so `!=` calls it equal to what `==` does not."""

    value: int

    def __ne__(self, other: object) -> bool:
        return False


@dataclass(eq=False)
class _Unrelated:
    value: int


class _Accentless(str):
    """Replaces `__eq__` alone and keeps its kind through `lower()`, so `!=` is still `str.__ne__`."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, str) and _unaccented(self) == _unaccented(other)

    __hash__ = str.__hash__

    def lower(self) -> _Accentless:
        return _Accentless(str.lower(self))


def _unaccented(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))


class _SameMonth(datetime.date):
    """Replaces `__eq__` alone, so `!=` is still `date.__ne__`."""

    def __eq__(self, other: object) -> bool:
        return isinstance(other, datetime.date) and (self.year, self.month) == (other.year, other.month)

    __hash__ = datetime.date.__hash__


class _MonthlyStamp(datetime.datetime):
    def date(self) -> _SameMonth:
        return _SameMonth(self.year, self.month, self.day)


@dataclass
class _Holder:
    item: object
    noise: int = 0


class _Carrier:
    def __init__(self, item: object) -> None:
        self.item = item


# both halves in one generator, so the properties below test the classifier and not the fast path.
# the last three are the subclass half: two a set may answer for, one that hashes by another rule
_MIXED_ELEMENTS = st.one_of(
    st.integers(-5, 5),
    st.text(max_size=2),
    st.none(),
    st.booleans(),
    st.builds(bytearray, st.binary(max_size=2)),
    st.builds(_ByField, st.integers(-2, 2)),
    st.builds(_NoHash),
    st.lists(st.integers(-2, 2), max_size=2),
    st.builds(_Counted, st.integers(-2, 2)),
    st.builds(_HashesLikeText, st.integers(-2, 2)),
    st.sampled_from(_Status),
)


OPTIONS = [
    ("tolerance", {"tolerance": 0.1}, 1.0, 1.05),
    ("tolerance too tight", {"tolerance": 0.001}, 1.0, 1.05),
    ("ignore", {"ignore": "b"}, {"a": 1, "b": 2}, {"a": 1, "b": 99}),
    (
        "ignore nested",
        {"ignore": ("user", "session")},
        {"user": {"id": 1, "session": "x"}},
        {"user": {"id": 1, "session": "y"}},
    ),
    ("include", {"include": "a"}, {"a": 1, "b": 2}, {"a": 1, "b": 99}),
    (
        "include nested",
        {"include": ("user", "id")},
        {"user": {"id": 1, "session": "x"}},
        {"user": {"id": 1, "session": "y"}},
    ),
    ("ignore_null", {"ignore_null": True}, {"a": 1, "b": 2}, {"a": 1, "b": None}),
    ("strict_types", {"strict_types": True}, {"id": 1}, {"id": True}),
    (
        "comparators",
        {"comparators": {str: lambda left, right: left.lower() == right.lower()}},
        {"n": "AB"},
        {"n": "ab"},
    ),
]


class TestBothSpellingsOfEqualityAnswerAlike:
    @pytest.mark.parametrize(("label", "options", "actual", "expected"), OPTIONS, ids=[case[0] for case in OPTIONS])
    def test_the_matcher_offers_what_the_assertion_offers(self, label, options, actual, expected):
        def by_builder() -> bool:
            try:
                assert_that(actual).is_equal_to(expected, **options)
            except AssertionFailure:
                return False
            return True

        assert_that(match.equal_to(expected, **options).matches(actual)).described_as(label).is_equal_to(by_builder())

    def test_an_option_the_relation_does_not_have_is_refused_by_name(self):
        # the matcher used to accept no options at all, so "not supported" read the same as "spelled wrong"
        with pytest.raises(TypeError, match=r"equal_to.*strict_type"):
            match.equal_to(1, strict_type=True)

    def test_a_spec_can_now_say_close_enough(self):
        readings = {"sensor": "t1", "value": 20.03}
        assert_that(readings).matches_structure({"sensor": "t1", "value": match.equal_to(20.0, tolerance=0.1)})

    def test_a_spec_can_now_ignore_a_field(self):
        assert_that({"user": {"id": 1, "seen_at": "now"}}).matches_structure(
            {"user": match.equal_to({"id": 1, "seen_at": "whenever"}, ignore="seen_at")}
        )

    @pytest.mark.parametrize(
        ("options", "expected_note"),
        [
            ({"tolerance": 0.1}, "tolerance=0.1"),
            ({"ignore": "b"}, "ignoring 'b'"),
            ({"include": "a"}, "including 'a'"),
            ({"ignore_null": True}, "ignore_null=True"),
            ({"strict_types": True}, "strict_types=True"),
            ({"comparators": {str: lambda left, right: True}}, "comparators for str"),
        ],
        ids=["tolerance", "ignore", "include", "ignore_null", "strict_types", "comparators"],
    )
    def test_the_configuration_shows_up_in_the_failure(self, options, expected_note):
        """A verdict computed under a configuration has to be reported under it too.

        Otherwise the matcher compares with a tolerance and then says plainly "not equal", and a reader
        asking why a field they thought was tolerated still failed has nothing to read.  The assertion
        already echoes the settings on its own failures; this is the same line for a spec.
        """
        assert_that(match.equal_to({"a": 1, "b": 2}, **options).describe()).contains(expected_note)

    def test_no_configuration_means_no_note(self):
        assert_that(match.equal_to(1).describe()).is_equal_to("a value equal to <1>")

    def test_the_note_reaches_the_message_of_a_real_failure(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"v": 25.0}).matches_structure({"v": match.equal_to(20.0, tolerance=0.1)})
        assert_that(str(failure.value)).contains("tolerance=0.1")

    def test_a_comparator_that_raises_is_not_swallowed_by_either_spelling(self):
        # a comparator is user code like any operator: its own failure is a bug in the test, not a verdict
        def broken(left: object, right: object) -> bool:
            raise TypeError("bug inside comparator")

        with pytest.raises(TypeError, match="bug inside comparator"):
            assert_that({"n": 1}).is_equal_to({"n": 2}, comparators={int: broken})
        with pytest.raises(TypeError, match="bug inside comparator"):
            match.equal_to({"n": 2}, comparators={int: broken}).matches({"n": 1})

    def test_both_spellings_carry_the_same_structured_result(self):
        options = {"tolerance": 0.1}
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"v": 25.0}).is_equal_to({"v": 20.0}, **options)
        assert_that([entry.path for entry in failure.value.diff.entries]).is_equal_to(["v"])
        assert_that(match.equal_to({"v": 20.0}, **options).matches({"v": 25.0})).is_false()

    def test_an_include_naming_an_absent_key_is_a_non_match_rather_than_an_error(self):
        assert_that(match.equal_to({"a": 1}, include="missing").matches({"a": 1})).is_false()


class TestTheCoreItself:
    """The extracted functions, exercised where the public paths cannot reach them cleanly."""

    def test_a_mapping_shape_is_structural_rather_than_nominal(self):
        class Rowlike:
            def keys(self):
                return ["a"]

            def values(self):
                return [1]

            def __getitem__(self, key):
                return 1

            def __iter__(self):
                return iter(["a"])

        assert_that(mapping_shaped(Rowlike())).is_true()
        assert_that(mapping_shaped(Rowlike(), check_values=False)).is_true()
        assert_that(mapping_shaped([1, 2])).is_false()
        assert_that(mapping_shaped(42)).is_false()

    def test_a_cycle_is_answered_rather_than_recursed_into(self):
        """The guard covers the paths the core walks itself: with filtering, and under a compare config, where a
        `==` that runs out of stack hands the pair to the walk.

        Two *different* self-referential mappings still reach Python's own `==` when nothing is filtered and no
        config is given, and that raises `RecursionError` from the interpreter, as it did before this core existed.
        A value met under a key option is past that: there the walk reads what `==` cannot finish.
        """
        left: dict = {"name": "a"}
        right: dict = {"name": "a"}
        left["self"] = left
        right["self"] = right
        assert_that(mapping_differs(left, right, ignore="nothing")).is_false()
        assert_that(mapping_differs(left, right, config=_CompareConfig())).is_false()
        with pytest.raises(RecursionError):
            mapping_differs(left, right)
        assert_that(values_differ(left, right, None)).is_false()
        assert_that(values_differ([left], [right], None)).is_false()
        right["name"] = "b"
        assert_that(values_differ([left], [right], None)).is_true()

    def test_identity_short_circuits_before_equality(self):
        # NaN is the one value where the two disagree, and the walker must not be asked about it twice
        nan = float("nan")
        assert_that(values_differ(nan, nan, None)).is_false()
        assert_that(values_differ(nan, float("nan"), None)).is_true()
        assert_that(math.isnan(nan)).is_true()

    def test_the_mixin_still_answers_for_an_extension_that_calls_it(self):
        # thin wrappers on purpose: an extension calling `self._normalize_key_specs(...)` keeps working
        builder = assert_that({"a": 1})
        assert_that(builder._normalize_key_specs(["a", "b"], "ignore")).is_equal_to(["a", "b"])
        assert_that(builder._dict_ignore(("a",))).is_equal_to(["a"])
        assert_that(builder._dict_include(("a", "b"))).is_equal_to(["a"])
        assert_that(builder._is_dict_like({"a": 1})).is_true()

    def test_the_two_spec_normalizers_differ_on_purpose(self):
        # for include a path selects its first segment, and getting this backwards broke nested include
        assert_that(ignore_specs(("a",))).is_equal_to(["a"])
        assert_that(ignore_specs(("a", "b"))).is_equal_to([("a", "b")])
        assert_that(include_specs(("a", "b"))).is_equal_to(["a"])

    def test_a_missing_include_key_is_signalled_from_the_depth_it_was_found(self):
        with pytest.raises(IncludeKeysMissingError) as signal:
            mapping_differs({"a": {"b": 1}}, {"a": {"c": 1}}, include=("a", "c"))
        assert_that(signal.value.missing).is_equal_to(["c"])

    def test_a_leaf_takes_the_config_that_applies_to_it(self):
        loose = _CompareConfig(tolerance=0.1)
        assert_that(values_differ(1.0, 1.05, loose)).is_false()
        assert_that(values_differ(1.0, 2.0, loose)).is_true()
        # a set is a leaf, and asking strict types about one called two equal sets unequal
        assert_that(values_differ({1, 2}, {1, 2}, _CompareConfig(strict_types=True))).is_false()


class TestMembershipIsOneDecisionToo:
    """The second relation a spec could not express, and the same treatment.

    A spec had `each_item` (every element matches) and `is_in` (the value is one of these), but not the
    plain one: this collection contains that.  Written a second time inside the matcher it would have
    repeated the parts that are easy to get subtly wrong, so it asks the same core `contains()` asks.
    """

    @pytest.mark.parametrize(
        ("label", "value", "items"),
        [
            ("present", [1, 2, 3], (2,)),
            ("absent", [1, 2, 3], (9,)),
            ("several, one missing", [1, 2, 3], (1, 9)),
            ("mapping is searched by key", {"a": 1, "b": 2}, ("a",)),
            ("mapping key absent", {"a": 1}, ("b",)),
            ("string holds a substring", "hello", ("ell",)),
            ("set", {1, 2}, (2,)),
            ("tuple", (1, 2), (3,)),
        ],
    )
    def test_the_matcher_answers_what_the_assertion_answers(self, label, value, items):
        def by_builder() -> bool:
            try:
                assert_that(value).contains(*items)
            except AssertionFailure:
                return False
            return True

        assert_that(match.contains(*items).matches(value)).described_as(label).is_equal_to(by_builder())

    def test_a_matcher_among_the_items_is_satisfied_by_any_element(self):
        # what makes membership more than `item in value`: the argument is asked of each element
        assert_that(match.contains(match.greater_than(100)).matches([1, 200])).is_true()
        assert_that(match.contains(match.greater_than(100)).matches([1, 2])).is_false()

    def test_a_matcher_without_the_equality_protocol_is_asked_too(self):
        """The built-in matchers also answer `==`, which hides the branch that asks them.

        `match.greater_than(100) in [1, 200]` is true through `__eq__` alone, so dropping the explicit
        matcher check changed nothing for them.  A duck-typed matcher has no such fallback, and it is
        the case that proves the branch is load-bearing.
        """

        class OverAHundred:
            def matches(self, value: object) -> bool:
                return isinstance(value, int) and value > 100

            def describe(self) -> str:
                return "more than 100"

            def describe_mismatch(self, value: object) -> str:
                return f"was {value}"

        duck = OverAHundred()
        assert_that(duck in [1, 200]).described_as("plain membership does not find it").is_false()
        assert_that(match.contains(duck).matches([1, 200])).is_true()
        assert_that(match.contains(duck).matches([1, 2])).is_false()
        assert_that([1, 200]).contains(duck)

    def test_a_value_that_cannot_be_searched_is_a_non_match_rather_than_an_error(self):
        assert_that(match.contains("x").matches(42)).is_false()
        with pytest.raises(TypeError, match=r"^val must be a container or iterable"):
            assert_that(42).contains("x")

    class _OldSequence:
        """Iterated by the interpreter through `__getitem__`, which `collections.abc.Iterable` does not see."""

        def __getitem__(self, index):
            if index < 3:
                return index
            raise IndexError(index)

    class _IterationRefused(_OldSequence):
        __iter__ = None

    @pytest.mark.parametrize(
        "value", [42, _OldSequence(), _IterationRefused()], ids=["a-number", "an-old-sequence", "iter-set-to-none"]
    )
    @pytest.mark.parametrize("asked", ["contains", "does_not_contain"])
    def test_both_sides_refuse_a_value_that_cannot_be_searched(self, value, asked):
        """`does_not_contain` asked `in` unguarded: it answered an old sequence `contains` refused, and let
        Python's own `argument of type 'int' is not iterable` out for the rest."""
        with pytest.raises(TypeError, match=r"^val must be a container or iterable, but was <"):
            getattr(assert_that(value), asked)(0)

    @pytest.mark.parametrize(
        "asked",
        [
            lambda: assert_that("a").contains(1),
            lambda: assert_that("a").contains("a", 1),
            lambda: assert_that("a").does_not_contain("a", 1),
            lambda: assert_that("a").contains_only(1),
            lambda: assert_that("a").check().contains("a", 1),
            lambda: assert_warn("a").contains("a", 1),
        ],
        ids=["contains-one", "contains-two", "does-not-contain-two", "contains-only", "check", "warn"],
    )
    def test_an_operand_refusal_reaches_a_builder_caller_as_the_operators_own(self, asked):
        """Two or more items went through the matchers' private class, which named a private module to the caller."""
        with pytest.raises(TypeError) as operator_refusal:
            operator.contains("a", 1)
        said = str(operator_refusal.value)
        with pytest.raises(TypeError) as refused:
            asked()
        linked, pending = [], [refused.value]
        while pending:
            link = pending.pop()
            if link is not None and all(link is not seen for seen in linked):
                linked.append(link)
                pending += [link.__cause__, link.__context__]
        assert_that([type(link) for link in linked]).does_not_contain(MembershipRefusedError)
        assert_that(type(refused.value)).is_same_as(TypeError)
        assert_that(str(refused.value)).is_equal_to(said)
        assert_that("".join(traceback.format_exception(refused.value))).does_not_contain("MembershipRefusedError")

    class _MatchesRaising(BaseMatcher):
        def matches(self, value: object) -> bool:
            raise TypeError("my own matches")

        def describe(self) -> str:
            return "a matcher whose own matches raises"

    @pytest.mark.parametrize(
        "asked",
        [
            lambda matcher: assert_that("text").contains(matcher, None),
            lambda matcher: match.contains(matcher, None).matches("text"),
        ],
        ids=["builder", "matcher"],
    )
    def test_a_matchers_own_error_is_not_taken_for_a_later_items_refusal(self, asked):
        """The `None` refuses under `in` too, and named, it hid the bug in the matcher, or read it as no match."""
        with pytest.raises(TypeError, match="my own matches"):
            asked(self._MatchesRaising())

    def test_an_operand_refusal_is_not_collected_by_a_soft_block(self):
        with pytest.raises(TypeError) as refused, soft_assertions():
            assert_that("a").contains("a", 1)
        assert_that(type(refused.value)).is_same_as(TypeError)

    @pytest.mark.parametrize(
        "pair", [("contains", "does_not_contain"), ("contains_key", "does_not_contain_key")], ids=["items", "keys"]
    )
    def test_both_sides_refuse_in_the_same_words(self, pair):
        value = self._OldSequence()
        refusals = set()
        for asked in pair:
            with pytest.raises(TypeError) as refused:
                getattr(assert_that(value), asked)(0)
            refusals.add(str(refused.value))
        assert_that(refusals).is_length(1)

    def test_a_value_answering_membership_alone_is_searched_by_both_sides(self):
        class Evens:
            def __contains__(self, item):
                return item % 2 == 0

        assert_that(Evens()).contains(2).does_not_contain(3)

    def test_a_one_shot_iterator_is_searched_rather_than_consumed(self):
        assert_that(match.contains(1, 3).matches(iter([1, 2, 3]))).is_true()

    def test_it_says_what_was_missing(self):
        assert_that(match.contains("beta").describe()).is_equal_to("a collection containing 'beta'")
        assert_that(match.contains("beta").describe_mismatch(["a"])).contains("missing 'beta'")
        assert_that(match.contains("beta").describe_mismatch(42)).contains("cannot be searched")

    def test_it_refuses_to_be_built_with_nothing_to_look_for(self):
        with pytest.raises(ValueError, match="one or more items"):
            match.contains()


class TestOrderingIsOneDecisionAsWell:
    """The comparison is an operator; the rule around it was written twice.

    A builder listed types and then tried the operator, a matcher tried the operator and answered False.
    Two spellings of one rule is how the text matchers drifted apart on bytes, so both now ask the same
    core and keep only what is genuinely theirs: what to do when the answer is "cannot be ordered".
    """

    @pytest.mark.parametrize(
        ("label", "actual", "expected", "relation"),
        [
            ("less", 1, 2, "lt"),
            ("greater", 2, 1, "gt"),
            ("equal under le", 1, 1, "le"),
            ("equal under ge", 1, 1, "ge"),
            ("int against float", 1, 1.0, "le"),
            ("strings", "a", "b", "lt"),
            ("dates", datetime.date(2026, 1, 1), datetime.date(2026, 6, 1), "lt"),
        ],
    )
    def test_the_relation_answers_what_python_answers(self, label, actual, expected, relation):
        operator = {"lt": "<", "le": "<=", "gt": ">", "ge": ">="}[relation]
        assert_that(holds(actual, expected, relation)).described_as(label).is_equal_to(
            eval(f"actual {operator} expected")
        )

    @pytest.mark.parametrize(
        ("label", "actual", "expected", "kind"),
        [
            ("complex has no ordering", 1j, 0, "value"),
            ("a date wants a date", datetime.date(2026, 1, 1), 5, "kind"),
            ("a number wants a number", 1, "a", "kind"),
            ("the operator refuses the pair", object(), object(), "pair"),
        ],
    )
    def test_an_unorderable_pair_says_why(self, label, actual, expected, kind):
        with pytest.raises(UnorderableError) as unordered:
            compare(actual, expected)
        assert_that(unordered.value.kind).described_as(label).is_equal_to(kind)

    def test_a_nan_outside_the_builtin_types_is_answered_the_same(self):
        """The fast path covers `float`; the rule behind it has to hold for the rest too.

        A `numpy.float64` NaN goes the long way round, where "neither smaller nor larger" would read as
        "equal" and make `le`/`ge` true. It is the only case that reaches that guard now that plain
        floats short-circuit, so it is what keeps the guard honest.
        """
        numpy = pytest.importorskip("numpy")
        nan = numpy.float64("nan")
        assert_that(holds(nan, nan, "le")).is_false()
        assert_that(holds(nan, nan, "ge")).is_false()
        assert_that(holds(nan, nan, "lt")).is_false()

    def test_nan_is_neither_less_nor_greater_nor_equal(self):
        # `compare` answers 0, and this is where "not less, not greater" must not become equal: `le`/`ge` stay false
        nan = float("nan")
        assert_that(holds(nan, nan, "le")).is_false()
        assert_that(holds(nan, nan, "ge")).is_false()
        assert_that(holds(nan, 1, "lt")).is_false()

    def test_both_spellings_treat_an_unorderable_pair_their_own_way(self):
        # deliberate: a wrong subject is a mistake in the test, while a matcher feeds `==` and the combinators
        assert_that(match.greater_than(1).matches("a")).is_false()
        with pytest.raises(TypeError, match=r"^given other arg must be a number"):
            assert_that(1).is_greater_than("a")

    def test_a_broken_operator_still_travels_out_of_the_core(self):
        class BrokenOrder:
            def __lt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

            def __gt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

        with pytest.raises(TypeError, match="bug inside __lt__"):
            compare(BrokenOrder(), BrokenOrder())


class TestTheRelationsASpecCouldNotExpress:
    """Three relations the builder has always had and a structural spec could not say at all.

    Each is the same decision the assertion reaches, asked of the same core: the point of the move is
    that there is no second implementation to drift, not that a matcher was added.
    """

    @pytest.mark.parametrize(
        ("label", "value", "items"),
        [
            ("exactly these", [1, 2], (1, 2)),
            ("one extra", [1, 2, 3], (1, 2)),
            ("one missing", [1], (1, 2)),
            ("order does not matter", [2, 1], (1, 2)),
            ("duplicates are still only these", [1, 1, 2], (1, 2)),
        ],
    )
    def test_contains_only_answers_what_the_assertion_answers(self, label, value, items):
        def by_builder() -> bool:
            try:
                assert_that(value).contains_only(*items)
            except AssertionFailure:
                return False
            return True

        assert_that(match.contains_only(*items).matches(value)).described_as(label).is_equal_to(by_builder())

    def test_contains_only_asks_which_items_not_how_many(self):
        """The boundary the matcher guide warns about, pinned so the warning cannot go stale.

        `contains_only` asks that nothing outside the given items is there.  Multiset equality is a
        different question, and the assertion that answers it is `contains_exactly_in_any_order`.
        """
        assert_that(match.contains_only("reader", "reader").matches(["reader"])).is_true()
        assert_that(match.contains_only(1, 2).matches([1, 1, 2])).is_true()
        with pytest.raises(AssertionFailure):
            assert_that([1, 1, 2]).contains_exactly_in_any_order(1, 2)

    @pytest.mark.parametrize(
        ("label", "value", "superset"),
        [
            ("proper subset", [1, 2], [1, 2, 3]),
            ("equal sets", [1, 2], [1, 2]),
            ("one outside", [1, 9], [1, 2]),
            ("empty is a subset of anything", [], [1]),
        ],
    )
    def test_is_subset_of_answers_what_the_assertion_answers(self, label, value, superset):
        def by_builder() -> bool:
            try:
                assert_that(value).is_subset_of(*superset)
            except AssertionFailure:
                return False
            return True

        assert_that(match.is_subset_of(superset).matches(value)).described_as(label).is_equal_to(by_builder())

    @pytest.mark.parametrize(
        ("label", "value", "reverse"),
        [
            ("ascending", [1, 2, 3], False),
            ("out of order", [1, 3, 2], False),
            ("descending under reverse", [3, 2, 1], True),
            ("ascending under reverse", [1, 2, 3], True),
            ("equal neighbours are sorted", [1, 1, 2], False),
            ("single element", [1], False),
        ],
    )
    def test_is_sorted_answers_what_the_assertion_answers(self, label, value, reverse):
        def by_builder() -> bool:
            try:
                assert_that(value).is_sorted(reverse=reverse)
            except AssertionFailure:
                return False
            return True

        assert_that(match.is_sorted(reverse=reverse).matches(value)).described_as(label).is_equal_to(by_builder())

    def test_is_sorted_takes_a_key_the_same_way(self):
        rows = [{"n": 1}, {"n": 2}]
        assert_that(rows).is_sorted(key=lambda row: row["n"])
        assert_that(match.is_sorted(key=lambda row: row["n"]).matches(rows)).is_true()

    def test_they_say_what_was_wrong(self):
        assert_that(match.contains_only("a", "b").describe()).is_equal_to("a collection containing only 'a', 'b'")
        assert_that(match.contains_only("a").describe_mismatch(["a", "b"])).contains("also had 'b'")
        assert_that(match.contains_only("a", "b").describe_mismatch(["a"])).contains("lacked 'b'")
        assert_that(match.is_subset_of([1]).describe_mismatch([1, 9])).contains("9 outside it")
        assert_that(match.is_sorted().describe_mismatch([3, 1])).contains("out of order at index 0")
        assert_that(match.is_sorted().describe()).is_equal_to("a collection sorted in order")
        assert_that(match.is_sorted(reverse=True).describe()).is_equal_to("a collection sorted in reverse")
        assert_that(match.is_subset_of([1]).describe()).contains("all appear in")

    def test_a_value_they_cannot_walk_is_a_non_match(self):
        assert_that(match.contains_only("a").matches(42)).is_false()
        assert_that(match.is_subset_of([1]).matches(42)).is_false()
        assert_that(match.is_sorted().matches(42)).is_false()
        assert_that(match.contains_only("a").describe_mismatch(42)).contains("cannot be listed")
        assert_that(match.is_subset_of([1]).describe_mismatch(42)).contains("cannot be listed")
        assert_that(match.is_sorted().describe_mismatch(42)).contains("cannot be walked")

    def test_answering_membership_is_not_the_same_as_being_listable(self):
        """`contains` needs only `in`; "only these" and "a subset of" need every element.

        Told apart because they were not: a value with `__contains__` and nothing else satisfied the
        capability check and then met Python's own "object is not iterable" inside the comprehension.
        """

        class MembershipOnly:
            def __contains__(self, item: object) -> bool:
                return item == 1

        value = MembershipOnly()
        assert_that(match.contains(1).matches(value)).described_as("membership is enough").is_true()
        assert_that(match.contains_only(1).matches(value)).described_as("listing is not").is_false()
        assert_that(match.is_subset_of([1]).matches(value)).described_as("listing is not").is_false()
        assert_that(value).contains(1)
        for relation in ("contains_only", "is_subset_of"):
            with pytest.raises(TypeError, match=r"^val must be iterable"):
                getattr(assert_that(value), relation)(1)

    def test_elements_that_cannot_be_ordered_are_not_sorted(self):
        assert_that(match.is_sorted().matches([1, "a"])).is_false()

    def test_the_assertion_refuses_the_same_collection_in_its_own_words(self):
        # a matcher answers, an assertion refuses; what must not reach the reader is `'<' not supported between`
        with pytest.raises(TypeError, match=r"^val must be a collection whose items can be ordered"):
            assert_that([1, "a"]).is_sorted()

    def test_a_broken_operator_still_travels_out_of_is_sorted(self):
        class BrokenOrder:
            def __lt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

            def __gt__(self, other: object) -> bool:
                raise TypeError("bug inside __lt__")

        with pytest.raises(TypeError, match="bug inside __lt__"):
            match.is_sorted().matches([BrokenOrder(), BrokenOrder()])

    @pytest.mark.parametrize("factory", [match.contains, match.contains_only, match.is_subset_of])
    def test_they_refuse_to_be_built_with_nothing(self, factory):
        with pytest.raises(ValueError, match="one or more items"):
            factory()


class TestStrictNeverTurnsUnequalIntoEqual:
    """`strict_types=True` may reject more pairs than plain equality. It may not accept more.

    It did: `assert_that(nan).is_equal_to(nan)` failed and the same call with the flag passed, because
    the strict path short-circuited on identity before asking `__eq__` at all.  The shortcut is right
    *inside* a container, where Python gives it for free (`[nan] == [nan]` is true when both elements are
    the same object), and wrong at the root, where there is no container to inherit it from.
    """

    class NotReflexive:
        """A value that is not equal to itself, the way `nan` is, without being a number."""

        def __eq__(self, other: object) -> bool:
            return False

        __hash__ = None  # ty: ignore[invalid-assignment]  # deliberately unhashable

    @staticmethod
    def _passes(value: object, expected: object, **options: object) -> bool:
        try:
            assert_that(value).is_equal_to(expected, **options)
        except AssertionFailure:
            return False
        return True

    def test_the_same_nan_is_unequal_to_itself_in_both_modes(self):
        nan = float("nan")
        assert_that(self._passes(nan, nan)).described_as("plain").is_false()
        assert_that(self._passes(nan, nan, strict_types=True)).described_as("strict").is_false()

    def test_two_different_nans_are_unequal_in_both_modes(self):
        assert_that(self._passes(float("nan"), float("nan"))).is_false()
        assert_that(self._passes(float("nan"), float("nan"), strict_types=True)).is_false()

    def test_a_decimal_nan_behaves_the_same(self):
        quiet = decimal.Decimal("NaN")
        assert_that(self._passes(quiet, quiet)).is_false()
        assert_that(self._passes(quiet, quiet, strict_types=True)).is_false()

    def test_a_shared_nan_inside_containers_stays_equal(self):
        nan = float("nan")
        assert_that([nan] == [nan]).described_as("python itself").is_true()
        assert_that(self._passes([nan], [nan])).described_as("plain").is_true()
        assert_that(self._passes([nan], [nan], strict_types=True)).described_as("strict").is_true()
        assert_that(self._passes({"v": nan}, {"v": nan}, strict_types=True)).described_as("mapping").is_true()

    def test_two_different_nans_inside_containers_stay_unequal(self):
        assert_that(self._passes([float("nan")], [float("nan")])).is_false()
        assert_that(self._passes([float("nan")], [float("nan")], strict_types=True)).is_false()

    def test_a_value_that_is_not_equal_to_itself_is_treated_the_same(self):
        odd = self.NotReflexive()
        assert_that(self._passes(odd, odd)).described_as("plain").is_false()
        assert_that(self._passes(odd, odd, strict_types=True)).described_as("strict").is_false()
        assert_that(self._passes([odd], [odd], strict_types=True)).described_as("inside a list").is_true()

    def test_the_matcher_keeps_the_same_invariant(self):
        nan = float("nan")
        assert_that(match.equal_to(nan, strict_types=True).matches(nan)).is_false()
        assert_that(match.equal_to([nan], strict_types=True).matches([nan])).is_true()

    @given(
        left=st.one_of(st.integers(), st.floats(allow_nan=True), st.text(max_size=5), st.booleans()),
        right=st.one_of(st.integers(), st.floats(allow_nan=True), st.text(max_size=5), st.booleans()),
    )
    @settings(deadline=None)
    def test_strict_implies_plain_for_any_pair(self, left, right):
        """The property behind all of the above, over generated pairs rather than chosen ones."""
        if self._passes(left, right, strict_types=True):
            assert_that(self._passes(left, right)).described_as(f"{left!r} vs {right!r}").is_true()


class TestTheCoresUnderTheAwkwardCases:
    """The cases a chosen-example test does not think of, listed by review and measured here."""

    def test_a_key_is_computed_once_per_element(self):
        calls = []

        def counting(item: int) -> int:
            calls.append(item)
            return item

        first_out_of_order([1, 2, 3, 4], key=counting)
        assert_that(calls).is_length(4)

    def test_a_length_is_read_once(self):
        calls = []

        class CountingLength:
            def __len__(self) -> int:
                calls.append(1)
                return 3

        length_of(CountingLength())
        assert_that(calls).is_length(1)

    def test_membership_drains_a_one_shot_iterator_before_searching_it(self):
        assert_that(missing_items(searchable(iter([1, 2, 3])), [1, 3], _is_matcher)).is_empty()

    def test_membership_works_on_unhashable_elements(self):
        assert_that(missing_items([[1], [2]], [[2]], _is_matcher)).is_empty()
        assert_that([{"a": 1}]).contains({"a": 1})

    def test_duplicates_do_not_confuse_membership(self):
        assert_that(missing_items([1, 1, 2], [1, 2], _is_matcher)).is_empty()
        assert_that(only_faults([1, 1, 2], (1, 2))).is_equal_to(([], []))

    def test_membership_keeps_its_answer_when_hashing_and_equality_disagree(self):
        """The case the set shortcut must refuse: equality by field, hash by identity.

        `a in [b]` is True because `==` says so, and `a in {b}` is False because the hashes differ and
        the comparison never happens. Membership here follows `==`, so such a value has to keep the walk.
        """

        wanted, held = _ByField(1), _ByField(1)
        assert_that(held in {wanted, _ByField(2)}).described_as("premise: a set cannot find it").is_false()
        assert_that(missing_items([held], [wanted], _is_matcher)).described_as("membership finds it").is_empty()
        assert_that(only_faults([held], (wanted,))).is_equal_to(([], []))
        assert_that(not_contained_in([held], [wanted])).is_empty()
        assert_that([held]).contains_only(wanted)
        assert_that([held]).is_subset_of([wanted])

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(bytearray(b"a"), id="bytearray: mutable, so unhashable despite looking built-in"),
            pytest.param(_NoHash(), id="identity equality but __hash__ set to None"),
        ],
    )
    def test_a_value_that_cannot_be_hashed_is_answered_rather_than_raised_at(self, value):
        """Both of these once raised `TypeError: cannot use 'bytearray' as a set element`.

        Hashability has to be asked, not assumed from the type looking simple or from equality being the
        inherited one: a class may keep identity equality and still say `__hash__ = None`.
        """
        twin = bytearray(b"a") if isinstance(value, bytearray) else value
        assert_that(only_faults([value], (twin,))).is_equal_to(([], []))
        assert_that(not_contained_in([value], [twin])).is_empty()
        assert_that(missing_items([value], [twin], _is_matcher)).is_empty()
        assert_that(repeated_items([value, twin])).described_as("two equal elements are one repeat").is_length(1)
        assert_that([value]).contains_only(twin)
        assert_that([value]).is_subset_of([twin])
        assert_that([value]).contains(twin)
        assert_that([value]).does_not_contain_duplicates()

    def test_the_shortcut_is_taken_once_the_collections_are_large_enough(self):
        """The other side of the threshold, and the reason it exists at all.

        Small collections keep the walk because deciding to avoid it costs more than the walk. These
        sizes are past that point, so the set path runs, and it has to answer exactly the same thing.
        """
        values, wanted = list(range(60)), tuple(range(60))
        assert_that(only_faults(values, wanted)).is_equal_to(([], []))
        assert_that(only_faults([*values, 999], wanted)).is_equal_to(([999], []))
        assert_that(not_contained_in(values, [*wanted, 999])).is_empty()
        assert_that(missing_items(values, wanted, _is_matcher)).is_empty()

    def test_a_value_without_a_length_is_judged_worth_hashing(self):
        """A collection that can be walked but not sized: the cost of walking it is unknown.

        The core assumes it is not small rather than skipping the shortcut on something that may well be
        huge. Reachable from the public API, since being walkable is all `contains_only` requires.
        """

        class Unsized:
            def __iter__(self):
                return iter(range(60))

        assert_that(only_faults(Unsized(), tuple(range(60)))).is_equal_to(([], []))
        assert_that(Unsized()).contains_only(*range(60))

    def test_the_fast_path_asks_for_one_hash_per_element_and_no_comparisons(self):
        """What the shortcut is actually for, counted rather than assumed.

        A property test proves the answer is the same; it says nothing about the work done to reach it.
        These counters do: the walk would compare every element against every wanted one, and the set
        hashes each element once instead.
        """
        hashes: list[int] = []

        class Counted:
            """No `__eq__` of its own, so equality is identity and the shortcut may hash it."""

            def __init__(self, value: int) -> None:
                self.value = value

            def __hash__(self) -> int:
                hashes.append(self.value)
                return self.value

        def hash_calls_for(size: int) -> int:
            hashes.clear()
            values = [Counted(index) for index in range(size)]
            only_faults(values, tuple(values))
            return len(hashes)

        small, large = hash_calls_for(30), hash_calls_for(60)
        assert_that(large / small).described_as("hash calls when the input doubles").is_close_to(2.0, 0.1)
        assert_that(small / 30).described_as("hash calls per element").is_close_to(4.0, 0.1)

    def test_the_walk_is_kept_where_it_must_be_and_costs_what_it_costs(self):
        comparisons: list[tuple[int, int]] = []

        class ByValue:
            def __init__(self, value: int) -> None:
                self.value = value

            def __eq__(self, other: object) -> bool:
                comparisons.append((self.value, getattr(other, "value", -1)))
                return isinstance(other, ByValue) and other.value == self.value

            __hash__ = None

        values = [ByValue(index) for index in range(6)]
        only_faults(values, tuple(values))
        assert_that(comparisons).described_as("a walk does compare, and that is the price of it").is_not_empty()

    def test_a_one_shot_value_is_walked_once(self):
        seen: list[int] = []

        def counting():
            for index in range(50):
                seen.append(index)
                yield index

        assert_that(only_faults(searchable(counting()), tuple(range(50)))).is_equal_to(([], []))
        assert_that(seen).described_as("elements produced by the generator").is_length(50)

    def test_decimals_take_the_shortcut_and_answer_the_same(self):
        """`Decimal` is on the safe list, so this has to prove the fast path, not just the answer.

        Sizes are past the threshold on purpose: at one element the walk would run whatever the list
        says, and the test would prove nothing about the path it claims to exercise.
        """
        values = [decimal.Decimal(index) for index in range(30)]
        assert_that(_hash_safe(values)).described_as("classified as safe to index").is_true()
        assert_that(_classified(values, tuple(values))).described_as("and worth indexing at this size").is_true()
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)
        assert_that([*values, values[0]]).contains_duplicates()

    def test_a_subclass_that_changes_neither_operation_takes_the_shortcut(self):
        """The safe list holds exact types, so a subclass used to walk although it answers as its base.

        `IntEnum` and `StrEnum` are the shapes a suite actually carries, a status field most of all.  Four
        thousand of them cost 30 ms on the walk against 0.09 ms indexed, and the answer is the same either
        way because the subclass inherits both operations unchanged.
        """

        class Money(int):
            def __init__(self, *_: object) -> None:
                self.currency = "USD"

        class Status(str, enum.Enum):
            PAID = "paid"
            DUE = "due"

        class Level(enum.IntEnum):
            LOW = 1
            HIGH = 2

        for values in ([Money(index) for index in range(30)], list(Status) * 15, list(Level) * 15):
            assert_that(_hash_safe(values)).described_as(f"{type(values[0]).__name__} is safe to index").is_true()
            assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
            assert_that(values).contains_only(*values)
            assert_that(values).is_subset_of(values)

        assert_that([*list(Status), Status.PAID]).contains_duplicates()
        assert_that(_hash_safe([Level.LOW, 1, True])).described_as("mixed with the base type").is_true()

    def test_a_subclass_that_replaces_one_operation_stays_on_the_walk(self):
        """Inheriting one of the pair and redefining the other is exactly the disagreement to avoid.

        Asked of the owner of each definition, so all four of these are refused: the first hashes by one
        rule and compares by another, the second compares by its own, the third is not hashable at all
        although its base is, and the fourth had equality assigned onto it after the class body ran.

        That last one is the case the `__eq__` half of the rule exists for, and it takes a patched class
        to build: writing `__eq__` in the body sets `__hash__` to `None` with it, so the hash half already
        refuses those.  Patched, it keeps `int.__hash__` and answers `True` to every comparison, and a set
        keeps two values the walk calls equal.
        """

        class HashesLikeText(int):
            __hash__ = str.__hash__

        class ComparesItsOwnWay(int):
            def __eq__(self, other: object) -> bool:
                return isinstance(other, ComparesItsOwnWay) and int(self) == int(other)

            __hash__ = int.__hash__

        class RefusesToHash(int):
            __hash__ = None  # ty: ignore[invalid-assignment]  # the shape under test

        class Patched(int):
            pass

        def _everything_is_equal(self: object, other: object) -> bool:
            return True

        Patched.__eq__ = _everything_is_equal  # ty: ignore[invalid-assignment]  # the shape under test

        assert_that(Patched(1) == Patched(2)).described_as("the patched comparison").is_true()
        assert_that({Patched(1), Patched(2)}).described_as("a set does not agree with it").is_length(2)

        for kind in (HashesLikeText, ComparesItsOwnWay, RefusesToHash, Patched):
            values = [kind(index) for index in range(30)]
            assert_that(_hash_safe(values)).described_as(f"{kind.__name__} is not safe to index").is_false()

        walked = [ComparesItsOwnWay(index) for index in range(30)]
        assert_that(only_faults(walked, tuple(walked))).is_equal_to(([], []))
        assert_that([*walked, walked[0]]).contains_duplicates()

    def test_fractions_stay_on_the_walk_and_answer_the_same(self):
        """Kept out of the shortcut for import cost, not for correctness, so both have to be shown."""
        values = [fractions.Fraction(index, 3) for index in range(30)]
        assert_that(_hash_safe(values)).described_as("not classified as safe: the list omits Fraction").is_false()
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)
        assert_that([*values, values[0]]).contains_duplicates()

    def test_a_value_that_refuses_to_hash_despite_its_type_falls_back(self):
        """`Decimal` is on the safe list, and one `Decimal` still refuses to be hashed.

        A signalling NaN is meant to be noticed rather than compared quietly, so it raises on hashing.
        That is a property of the value, invisible to a rule about types, so the set is attempted and the
        walk takes over when it fails.  The sizes are past the threshold, so the fast path really is tried.
        """
        values = [decimal.Decimal("snan")] * 30
        assert_that(only_faults(values, tuple(values))).is_equal_to(([], []))
        assert_that(not_contained_in(values, values)).is_empty()
        assert_that(values).contains_only(*values)
        assert_that(values).is_subset_of(values)

    def test_naming_repeats_of_one_object_never_compares_it_with_itself(self):
        """Thirty references to one signalling NaN: identity answers, where `==` on it signals.

        The walk used to reach `==` twice for every element, once to count and once to see whether the
        value had already been named, and the second reading raised where the first had answered.
        """
        same_object = [decimal.Decimal("snan")] * 30
        assert_that(has_duplicates(same_object)).described_as("one object, thirty times").is_true()
        assert_that(repeated_items(same_object)).is_length(1)

    def test_a_value_whose_class_cannot_be_hashed_keeps_the_walk(self):
        """The classifier hashes the types, and a metaclass may refuse that.

        The instances compare perfectly well, so refusing to classify has to mean walking rather than
        raising. Found by review: the shortcut turned a plain assertion failure into a `TypeError`.
        """

        class Unhashable(type):
            __hash__ = None

        class Odd(metaclass=Unhashable):
            pass

        values = [Odd() for _ in range(30)]
        others = tuple(Odd() for _ in range(30))
        assert_that(_hash_safe(values)).described_as("cannot be classified, so not safe").is_false()
        assert_that(only_faults(values, others)[0]).is_length(len(values))
        with pytest.raises(AssertionFailure):
            assert_that(values).contains_only(*others)

    def test_a_hash_that_raises_is_not_a_reason_to_stop_answering(self):
        """A shortcut may not introduce an exception the library did not have.

        This class compares by identity, which the rule accepts, and hashes by raising. Before the
        shortcut nothing hashed it and the assertion simply failed; that is what it does again.
        """

        class Angry:
            def __hash__(self) -> int:
                raise ValueError("hashing is a bug in this value")

        values = [Angry() for _ in range(30)]
        assert_that(only_faults(values, tuple(Angry() for _ in range(30)))[0]).is_length(len(values))
        with pytest.raises(AssertionFailure):
            assert_that(values).contains_only(*[Angry() for _ in range(30)])

    def test_indexing_is_all_or_nothing_across_both_sides(self):
        """One side indexed and the other not is how the lookup started raising again.

        Plain decimals index cleanly, a signalling NaN among the wanted items does not, and asking a set
        about it would hash it after all.  Walked instead, each signalling NaN is answered as absent.
        """
        plain = [decimal.Decimal(index) for index in range(30)]
        signalling = [decimal.Decimal("snan")] * 30
        assert_that(only_faults(plain, tuple(signalling))).is_equal_to((plain, signalling))
        assert_that(not_contained_in(signalling, plain)).is_equal_to(signalling)
        assert_that(missing_items(plain, tuple(signalling), _is_matcher)).is_equal_to(signalling)

    def test_a_raw_one_shot_value_is_materialised_before_it_is_classified(self):
        assert_that(only_faults(iter([1, 2, 3]), (1, 2, 3))).is_equal_to(([], []))
        assert_that(not_contained_in(iter([1, 2]), [1, 2, 3])).is_empty()
        assert_that(missing_items(iter([1, 2, 3]), (1, 3), _is_matcher)).is_empty()

    def test_a_value_that_can_be_walked_twice_is_handed_back_untouched(self):
        values = [1, 2, 3]
        assert_that(materialized(values)).is_same_as(values)

    @pytest.mark.parametrize("shape", ["one shared iterator", "a fresh generator over shared state"])
    def test_a_value_sharing_one_position_is_not_copied(self, shape):
        """The recorded boundary: being its own iterator is not the only way to have one position.

        Both shapes lose what a first walk read, so a matcher asked twice reports the remainder.  What
        is refused is copying anything that merely lacks a length, which turns a Pydantic model into a
        list of its field pairs, and walking one to find out costs the position that is shared.
        """

        class Shared:
            def __init__(self, items):
                self.items = iter(items)

            def __iter__(self):
                return self.items if shape == "one shared iterator" else (item for item in self.items)

        subject = Shared([1, 2, 3])
        assert_that(materialized(subject)).is_same_as(subject)

    def test_a_value_that_is_not_an_iterator_keeps_its_own_shape(self):
        @dataclasses.dataclass
        class FieldPairs:
            id: int

            def __iter__(self):
                return iter(dataclasses.asdict(self).items())

        model = FieldPairs(id=1)
        assert_that(materialized(model)).is_same_as(model)

    def test_user_code_that_raises_during_the_search_is_not_swallowed_by_the_fallback(self):
        """The boundary of the `try`, which is the whole point of where it is drawn.

        Only hashing may be caught, because only hashing is what the shortcut added. A comparison or a
        matcher raising is user code failing, and this library reports that as a bug in the test rather
        than retrying quietly on the walk. A wider `try` would have hidden it and answered anyway.
        """

        class Exploding:
            def matches(self, value: object) -> bool:
                raise RuntimeError("the matcher itself is broken")

            def describe(self) -> str:
                return "an exploding matcher"

            def describe_mismatch(self, value: object) -> str:
                return "boom"

        values = list(range(60))
        with pytest.raises(RuntimeError, match="matcher itself is broken"):
            missing_items(values, (Exploding(),), _is_matcher)
        with pytest.raises(RuntimeError, match="matcher itself is broken"):
            assert_that(values).contains(Exploding())

    def test_an_operator_that_raises_travels_out_of_both_paths(self):
        class Angry:
            def __eq__(self, other: object) -> bool:
                raise ValueError("comparison is a bug in the value, not a verdict")

            __hash__ = None

        with pytest.raises(ValueError, match="bug in the value"):
            only_faults([Angry()], (Angry(),))
        with pytest.raises(ValueError, match="bug in the value"):
            assert_that([Angry()]).contains_only(Angry())

    def test_duplicates_are_found_when_hashing_and_equality_disagree(self):
        """The other half of the disagreement case: the count has to follow `==`, not the hash."""
        first, second = _ByField(1), _ByField(1)
        assert_that(repeated_items([first, second])).is_length(1)
        with pytest.raises(AssertionFailure):
            assert_that([first, second]).does_not_contain_duplicates()
        assert_that([first, second]).contains_duplicates()

    def test_membership_keeps_its_answer_on_values_that_cannot_be_hashed(self):
        assert_that(only_faults([[1], [2]], ([1], [2]))).is_equal_to(([], []))
        assert_that(not_contained_in([{"a": 1}], [{"a": 1}, {"b": 2}])).is_empty()
        assert_that([[1], [2]]).contains_only([1], [2])

    def test_a_matcher_among_the_wanted_items_keeps_the_walk(self):
        """Matchers are hashable, so a set would look them up by hash and answer the wrong thing.

        What the walk answers, and what this pins, is the behaviour the shipped revision had: a matcher
        is "found" because its own `__eq__` accepts the element, so nothing is reported missing.
        """
        assert_that(only_faults([1, 2], (match.greater_than(0), match.greater_than(1)))).is_equal_to(([], []))
        assert_that([5]).contains(match.greater_than(3))

    def test_nan_is_found_by_identity_on_both_paths(self):
        nan = float("nan")
        assert_that(missing_items([nan], [nan], _is_matcher)).described_as("the same object").is_empty()
        assert_that(only_faults([nan], (nan,))).is_equal_to(([], []))
        assert_that(missing_items([float("nan")], [float("nan")], _is_matcher)).described_as(
            "two distinct NaNs stay unequal"
        ).is_length(1)

    def test_membership_still_drains_a_one_shot_value_once(self):
        assert_that(only_faults(searchable(iter([1, 2])), (1, 2))).is_equal_to(([], []))
        assert_that(not_contained_in(searchable(iter([1])), [1, 2])).is_empty()

    def test_duplicates_are_named_once_in_order_of_first_appearance(self):
        assert_that(repeated_items([3, 1, 3, 2, 1, 3])).is_equal_to([3, 1])
        assert_that(repeated_items([1, 2, 3])).is_empty()
        assert_that(repeated_items([1, 1.0, 2])).is_equal_to([1])
        assert_that(repeated_items([[1], [1], [2]])).described_as("unhashable keeps the walk").is_equal_to([[1]])

    @given(
        values=st.lists(_MIXED_ELEMENTS, max_size=12),
        items=st.lists(_MIXED_ELEMENTS, max_size=6),
    )
    @settings(max_examples=300)
    def test_the_shortcut_answers_what_the_walk_answers(self, values, items):
        """The property the whole optimisation rests on, checked against the walk it replaced.

        The elements are deliberately mixed rather than all safe: a generator of integers and strings
        exercises only the fast half and would have missed both ways the classifier was wrong.
        """
        walked_extra = [item for item in values if item not in items]
        walked_missing = [item for item in items if item not in values]
        assert_that(only_faults(values, items)).is_equal_to((walked_extra, walked_missing))
        assert_that(not_contained_in(values, items)).is_equal_to([item for item in values if item not in items])
        assert_that(missing_items(values, items, _is_matcher)).is_equal_to(walked_missing)

    @given(values=st.lists(_MIXED_ELEMENTS, max_size=12))
    @settings(max_examples=300)
    def test_naming_duplicates_answers_what_counting_answered(self, values):
        counted: list[object] = []
        for value in values:
            if values.count(value) > 1 and not any(value == earlier for earlier in counted):
                counted.append(value)
        assert_that(repeated_items(values)).is_equal_to(counted)

    def test_text_relations_accept_subclasses_of_their_types(self):
        class Name(str):
            pass

        class Raw(bytes):
            pass

        assert_that(text_contains(Name("hello"), "ell")).is_true()
        assert_that(text_starts_with(Name("hello"), "he")).is_true()
        assert_that(text_contains(Raw(b"hello"), b"ell")).is_true()
        assert_that(text_contains(bytearray(b"hello"), b"ell")).is_true()

    def test_a_tuple_of_prefixes_is_not_accepted_by_either_spelling(self):
        """`str.startswith` takes a tuple; this relation does not, and did not before the move.

        Recorded rather than fixed: accepting it would make the matcher answer a question the assertion
        refuses, which is the drift this core exists to prevent. Widening both is a separate decision.
        """
        assert_that(text_starts_with("hello", ("he", "xx"))).is_false()
        with pytest.raises(TypeError, match=r"^given prefix arg must be a string"):
            assert_that("hello").starts_with(("he", "xx"))

    def test_a_length_that_is_negative_is_pythons_own_error(self):
        class Negative:
            def __len__(self) -> int:
                return -1  # noqa: PLE0303  # the invalid length is exactly what is measured

        with pytest.raises(ValueError, match="__len__"):
            length_of(Negative())


class TestAMatcherIsASpecificationAndAnswersTheSameWayTwice:
    """A matcher is built once and used many times, often against several values in a row.

    The four new ones take a collection as their expected operand, and a collection handed in as a
    generator is gone after the first question.  Drained at construction, so the second call reaches the
    same verdict as the first: anything else makes a spec silently depend on how often it was used.
    """

    @pytest.mark.parametrize(
        ("label", "build", "value"),
        [
            ("contains", lambda: match.contains(1, 2), [1, 2, 3]),
            ("contains_only", lambda: match.contains_only(1, 2), [1, 2]),
            ("is_subset_of from a list", lambda: match.is_subset_of([1, 2, 3]), [1, 2]),
            ("is_subset_of from items", lambda: match.is_subset_of(1, 2, 3), [1, 2]),
            ("is_sorted", lambda: match.is_sorted(), [1, 2, 3]),
            ("equal_to with options", lambda: match.equal_to({"a": 1}, ignore="b"), {"a": 1, "b": 9}),
        ],
    )
    def test_three_calls_give_the_same_answer(self, label, build, value):
        matcher = build()
        verdicts = [matcher.matches(value) for _ in range(3)]
        assert_that(set(verdicts)).described_as(label).is_length(1)

    def test_a_generator_as_the_expected_operand_is_drained_once(self):
        constraint = match.is_subset_of(iter([1, 2, 3]))
        assert_that(constraint.matches([1])).described_as("first").is_true()
        assert_that(constraint.matches([1])).described_as("second").is_true()
        assert_that(constraint.matches([2, 3])).described_as("third, other value").is_true()

    def test_an_ordinary_collection_stays_a_live_view(self):
        """Copy only what has to be copied.

        `equal_to` keeps its expected value rather than a snapshot of it, and a membership matcher does
        the same: a list handed in stays the same list.  Only a one-shot iterator is drained, because
        there is no other way for it to answer twice.  Saying "a matcher is a specification" does not
        settle this, so it is measured.
        """
        known = [1]
        constraint = match.is_subset_of(known)
        assert_that(constraint.matches([1])).described_as("before").is_true()
        known.append(2)
        assert_that(constraint.matches([2])).described_as("after the list grew").is_true()

    def test_a_one_shot_iterator_is_the_only_thing_copied(self):
        drained = match.is_subset_of(iter([1, 2]))
        assert_that(drained.matches([1])).is_true()
        assert_that(drained.matches([2])).described_as("still answers, from the copy").is_true()

    def test_the_description_survives_being_asked_twice(self):
        constraint = match.is_subset_of(iter([1, 2]))
        assert_that(constraint.describe()).is_equal_to(constraint.describe())

    def test_one_matcher_serves_several_values(self):
        constraint = match.contains("beta")
        assert_that(["alpha", "beta"]).satisfies(constraint)
        assert_that({"beta": 1}).satisfies(constraint)
        assert_that("a beta release").satisfies(constraint)


class TestTheNewMatchersAcceptTheCollectionsPeopleActuallyHave:
    """Binding the element to the collection must not make the annotation narrower than the runtime.

    `Iterable` is covariant and `Matcher` is contravariant, so the combination is easy to get wrong in
    the strict direction: a `list[object]` or a `list[Base]` holding a `Derived` is ordinary code, and a
    checker refusing it would be a regression dressed as a type improvement.  Runtime is asserted here;
    the static half of the same cases lives in `tests/typing_cases.py`, where three checkers read them.
    """

    class Base:
        pass

    class Derived(Base):
        pass

    def test_a_heterogeneous_collection_is_searched_by_one_of_its_types(self):
        mixed: list[int | str] = [1, "x"]
        assert_that(mixed).satisfies(match.contains("x"))
        assert_that(mixed).satisfies(match.contains_only(1, "x"))

    def test_a_collection_of_object_is_searched_by_a_concrete_value(self):
        wide: list[object] = [1, "x"]
        assert_that(wide).satisfies(match.contains("x"))
        assert_that(wide).satisfies(match.is_subset_of([1, "x", 2.0]))

    def test_a_collection_of_a_base_class_is_searched_by_a_subclass_instance(self):
        item = self.Derived()
        values: list[TestTheNewMatchersAcceptTheCollectionsPeopleActuallyHave.Base] = [item]
        assert_that(values).satisfies(match.contains(item))
        assert_that(values).satisfies(match.is_subset_of(values))


class TestAMatcherLooksAtItsValueOnce:
    """The verdict and the reason come from one walk, and every consumer asks for them together.

    Two walks are wrong in two different ways. Over a one-shot value the second sees the remains of the
    first, so the message named items that were there and missed the ones that were not. Over any value
    it runs the user's `key` or comparator again, which is a side effect nobody asked for.
    """

    @pytest.mark.parametrize(
        ("label", "matcher", "expected"),
        [
            ("contains", match.contains(9), "missing 9"),
            ("contains_only", match.contains_only(1, 2), "also had 3"),
            ("is_subset_of", match.is_subset_of([1, 2]), "3 outside it"),
            ("is_sorted", match.is_sorted(), "out of order at index 0"),
        ],
    )
    def test_the_reason_is_right_on_a_one_shot_value(self, label, matcher, expected):
        source = {"contains": [1, 2], "contains_only": [1, 3], "is_subset_of": [3], "is_sorted": [2, 1]}[label]
        result = matcher.evaluate(iter(source))
        assert_that(result.matched).described_as(label).is_false()
        assert_that(result.mismatch).described_as(label).contains(expected)

    def test_a_key_runs_once_per_element_through_the_public_surface(self):
        calls: list[int] = []

        def key(value: int) -> int:
            calls.append(value)
            return value

        with pytest.raises(AssertionFailure):
            assert_that([2, 1]).satisfies(match.is_sorted(key=key))
        assert_that(calls).is_equal_to([2, 1])

    def test_a_key_runs_once_per_element_inside_each(self):
        calls: list[int] = []

        def key(value: int) -> int:
            calls.append(value)
            return value

        with pytest.raises(AssertionFailure):
            assert_that([[2, 1]]).each(match.is_sorted(key=key))
        assert_that(calls).is_equal_to([2, 1])

    def test_an_iterator_as_a_leaf_of_a_structure_keeps_its_reason(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"rows": iter([2, 1])}).matches_structure({"rows": match.is_sorted()})
        assert_that(str(failure.value)).contains("out of order at index 0")

    def test_a_single_walk_matcher_that_passes_inside_a_structure(self):
        assert_that({"rows": [1, 2, 3]}).matches_structure({"rows": match.is_sorted()})
        assert_that({"tags": ["a", "b"]}).matches_structure({"tags": match.contains("a")})

    def test_the_matcher_still_answers_the_same_way_twice(self):
        matcher = match.is_sorted()
        assert_that(matcher.matches([1, 2])).is_true()
        assert_that(matcher.matches([2, 1])).is_false()
        assert_that(matcher.matches([1, 2])).is_true()


class TestNumbersBeyondFloat:
    """`Decimal`, `Fraction` and arbitrary-precision integers answer where a float would, or say why not.

    A `Decimal` NaN signals `InvalidOperation` instead of answering `<`, and a `Decimal` refuses arithmetic
    with a float outright, so every relation that reached the operator directly raised the value's own
    exception where a verdict was promised.
    """

    _NAN = decimal.Decimal("NaN")

    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda value: assert_that(value).is_greater_than(0), id="is_greater_than"),
            pytest.param(lambda value: assert_that(value).is_less_than(0), id="is_less_than"),
            pytest.param(lambda value: assert_that(value).is_greater_than_or_equal_to(0), id="is_greater_or_equal"),
            pytest.param(lambda value: assert_that(value).is_less_than_or_equal_to(0), id="is_less_or_equal"),
            pytest.param(lambda value: assert_that(value).is_positive(), id="is_positive"),
            pytest.param(lambda value: assert_that(value).is_negative(), id="is_negative"),
            pytest.param(lambda value: assert_that(value).is_between(0, 1), id="is_between"),
            pytest.param(lambda value: assert_that([decimal.Decimal(1), value]).is_sorted(), id="is_sorted"),
        ],
    )
    @pytest.mark.parametrize("nan", [decimal.Decimal("NaN"), decimal.Decimal("sNaN"), float("nan")], ids=str)
    def test_a_nan_fails_every_relation_rather_than_signalling(self, call, nan):
        with pytest.raises(AssertionFailure):
            call(nan)

    @pytest.mark.parametrize("nan", [decimal.Decimal("NaN"), decimal.Decimal("sNaN"), float("nan")], ids=str)
    def test_a_nan_is_never_close_to_anything(self, nan):
        """`is_close_to` reads the NaN itself, where a signalling `Decimal` refuses to become a float."""
        with pytest.raises(AssertionFailure):
            assert_that(nan).is_close_to(decimal.Decimal(1), 1)

    @pytest.mark.parametrize(
        "matcher",
        [
            pytest.param(match.greater_than(decimal.Decimal(5)), id="greater_than"),
            pytest.param(match.between(decimal.Decimal(0), decimal.Decimal(9)), id="between"),
            pytest.param(match.is_positive(), id="is_positive"),
            pytest.param(match.is_negative(), id="is_negative"),
            pytest.param(match.is_sorted(), id="is_sorted"),
        ],
    )
    def test_a_matcher_answers_no_match_for_a_decimal_nan(self, matcher):
        value = [decimal.Decimal(1), self._NAN] if matcher.describe().startswith("a sorted") else self._NAN
        assert_that(matcher.matches(value)).is_false()
        assert_that(matcher == value).is_false()

    @pytest.mark.parametrize(
        ("actual", "expected", "tolerance", "within"),
        [
            pytest.param({"price": decimal.Decimal("1.00")}, {"price": 1.0001}, 0.01, True, id="decimal-vs-float"),
            pytest.param({"price": decimal.Decimal("1.00")}, {"price": 9.0}, 0.01, False, id="decimal-far-from-float"),
            pytest.param({"n": 10**400}, {"n": 1.0}, 0.1, False, id="bignum-vs-float"),
            pytest.param({"n": 10**400}, {"n": 10**400 + 1}, 2, True, id="bignum-vs-bignum"),
            pytest.param({"x": decimal.Decimal("NaN")}, {"x": decimal.Decimal(1)}, 1, False, id="decimal-nan"),
            pytest.param({"x": float("inf")}, {"x": 1.0}, 1, False, id="infinity"),
            pytest.param({"x": float("inf")}, {"x": float("inf")}, 1, True, id="two-infinities"),
            pytest.param({"x": decimal.Decimal("Infinity")}, {"x": 1.0}, 1, False, id="decimal-infinity"),
        ],
    )
    def test_a_tolerance_measures_the_pair_rather_than_raising(self, actual, expected, tolerance, within):
        assert_that(assert_that(actual).check().is_equal_to(expected, tolerance=tolerance).passed).is_equal_to(within)

    @pytest.mark.parametrize(
        ("value", "other", "tolerance"),
        [
            pytest.param(decimal.Decimal("1.0"), decimal.Decimal("1.05"), 0.1, id="decimal-pair-float-tolerance"),
            pytest.param(1.0, decimal.Decimal("1.05"), 0.1, id="float-value-decimal-other"),
            pytest.param(decimal.Decimal("1.0"), 1.05, 0.1, id="decimal-value-float-other"),
        ],
    )
    def test_is_close_to_mixes_decimals_and_floats(self, value, other, tolerance):
        assert_that(value).is_close_to(other, tolerance)
        assert_that(value).is_not_close_to(other, tolerance / 100)

    def test_a_datetime_subclass_is_a_datetime_to_the_ordering(self):
        class Stamp(datetime.datetime):
            pass

        boundary = datetime.datetime(2026, 1, 1)
        later = Stamp(2026, 6, 1)
        assert_that(later).is_greater_than(boundary)
        assert_that(boundary).is_less_than(later)
        assert_that(match.greater_than(boundary).matches(later)).is_true()
        assert_that(match.between(boundary, Stamp(2026, 12, 1)).matches(later)).is_true()
        with pytest.raises(TypeError, match="must be a datetime"):
            assert_that(later).is_greater_than(5)

    @pytest.mark.parametrize(
        ("build", "message"),
        [
            pytest.param(lambda: match.between(9, 1), "low arg must be less than", id="between"),
            pytest.param(lambda: match.close_to(5, -1), "tolerance arg must not be negative", id="close_to"),
        ],
    )
    def test_a_matcher_refuses_what_the_builder_refuses(self, build, message):
        with pytest.raises(ValueError, match=message):
            build()

    def test_a_tolerance_with_no_ordering_against_zero_is_left_to_the_call(self):
        assert_that(match.close_to(datetime.datetime(2026, 1, 1), datetime.timedelta(hours=1)).describe()).contains(
            "within"
        )
        with pytest.raises(ValueError, match="tolerance arg must not be negative"):
            match.close_to(datetime.datetime(2026, 1, 1), datetime.timedelta(hours=-1))

    @pytest.mark.parametrize(
        ("value", "other", "tolerance"),
        [
            pytest.param(
                decimal.Decimal("1.0"), decimal.Decimal("1.05"), fractions.Fraction(1, 10), id="decimal-fraction"
            ),
            pytest.param(fractions.Fraction(1), fractions.Fraction(21, 20), 0.1, id="fraction-float"),
        ],
    )
    def test_a_window_no_type_can_hold_is_measured_exactly(self, value, other, tolerance):
        assert_that(value).is_close_to(other, tolerance)
        assert_that(value).is_not_close_to(other, tolerance / 100)

    def test_bounds_with_no_ordering_are_left_to_the_call(self):
        matcher = match.between("a", 1)
        assert_that(matcher.matches(0)).is_false()
        assert_that(match.close_to(1, decimal.Decimal("0.5")).matches(1.2)).is_true()

    def test_a_tolerance_with_no_ordering_at_all_is_left_to_the_call(self):
        matcher = match.close_to(1, "a wide one")
        assert_that(matcher.matches(1)).is_false()

    def test_a_matcher_refusing_the_operand_is_not_equal_to_it(self):
        class Refusing(BaseMatcher):
            def matches(self, value):
                raise TypeError("this matcher takes no such operand")

            def describe(self):
                return "a refusing matcher"

        assert_that(Refusing() == 5).is_false()


class TestSubsetIsOneDecision:
    """`is_subset_of` had two implementations: the assertion's, and the matcher's own walk over a superset.

    The matcher kept the superset whole, so a string superset answered substring membership and a set
    superset hashed items that refuse to hash, and a mapping value was judged by its keys alone.
    """

    @pytest.mark.parametrize(
        ("value", "supersets", "holds"),
        [
            pytest.param({"a": 999, "b": 2}, ({"a": 1, "b": 2, "c": 3},), False, id="mapping-wrong-value"),
            pytest.param({"a": 1}, ({"a": 1, "b": 2},), True, id="mapping-pair-held"),
            pytest.param(["ab"], ("abc",), False, id="string-superset-by-item"),
            pytest.param([""], ("abc",), False, id="empty-string-is-no-item"),
            pytest.param(["a", "b"], ("abc",), True, id="characters-are-items"),
            pytest.param([[1]], ({1, 2},), False, id="unhashable-against-a-set"),
            pytest.param([[1]], ([[1], [2]],), True, id="unhashable-held"),
            pytest.param({"a": 1}, ({"a": 2}, {"a": 1}), True, id="second-superset-holds-it"),
            pytest.param({"a": 1}, ({"a": 1}, {"a": 2}), True, id="first-superset-holds-it"),
        ],
    )
    def test_the_assertion_and_the_matcher_answer_alike(self, value, supersets, holds):
        outcome = assert_that(value).check().is_subset_of(*supersets)
        assert_that(outcome.passed).described_as("the assertion").is_equal_to(holds)
        assert_that(match.is_subset_of(*supersets).matches(value)).described_as("the matcher").is_equal_to(holds)

    def test_one_nan_under_a_key_is_held_by_itself(self):
        same = float("nan")
        assert_that({"a": same}).is_subset_of({"a": same})

    def test_a_missing_pair_names_the_supersets_as_given(self):
        outcome = assert_that({"a": 1}).check().is_subset_of({"a": 2}, {"b": 3})
        assert_that(outcome.message).contains("[{'a': 2}, {'b': 3}]")

    def test_a_mapping_superset_is_shown_as_its_pairs(self):
        """The failure has always printed pairs, so a mapping that reprs as something else is read first."""

        class Terse:
            def __init__(self, pairs):
                self._pairs = pairs

            def keys(self):
                return self._pairs.keys()

            def __iter__(self):
                return iter(self._pairs)

            def __getitem__(self, key):
                return self._pairs[key]

            def __repr__(self):
                return "<terse>"

        outcome = assert_that({"a": 1}).check().is_subset_of(Terse({"a": 2}))
        assert_that(outcome.message).contains("{'a': 2}").does_not_contain("<terse>")
        assert_that(outcome.expected).is_equal_to({"a": 2})

    def test_a_one_shot_mapping_is_a_subset_of_itself(self):
        """Its pairs were read for the comparison already, so reading it again as a superset finds nothing."""

        class OneShot:
            def __init__(self, pairs):
                self._pairs = pairs
                self._left = list(pairs)

            def keys(self):
                return list(self._pairs)

            def __iter__(self):
                left, self._left = self._left, []
                return iter(left)

            def __getitem__(self, key):
                return self._pairs[key]

        same = OneShot({"a": 1})
        assert_that(same).is_subset_of(same)

    def test_a_one_shot_superset_is_read_once(self):
        """Read twice, a generator is empty the second time and every item reads as missing."""
        assert_that([1, 2]).is_subset_of(item for item in [1, 2, 3])
        assert_that(assert_that([1, 9]).check().is_subset_of(item for item in [1, 2, 3]).passed).is_false()


class TestMembershipShortcutsKeepTheWalksAnswer:
    """A set or a `Counter` may stand in for the walk only where hashing and ``==`` agree."""

    @pytest.mark.parametrize("length", [66, 67], ids=["under-the-threshold", "over-the-threshold"])
    def test_contains_only_on_a_string_answers_the_same_at_any_length(self, length):
        """A set of a string's characters answers by character where the walk answers by substring."""
        text = "ab" * length
        assert_that(text).contains_only("a", "b", "ab")
        assert_that(match.contains_only("a", "b", "ab").matches(text)).is_true()
        assert_that(assert_that(text).check().contains_only("a", "ab").passed).is_false()

    def test_a_matcher_item_is_counted_by_what_it_matches(self):
        assert_that([1, 2]).contains_exactly_in_any_order(match.greater_than(0), 2)
        assert_that([1, 2]).contains_exactly_in_any_order(2, match.greater_than(0))
        assert_that([1, 2]).contains_exactly(match.greater_than(0), 2)

    @pytest.mark.parametrize("size", [2, 20], ids=["walk", "set"])
    def test_a_probe_whose_hash_raises_still_gets_a_verdict(self, size):
        class Angry:
            def __hash__(self):
                raise RuntimeError("no hash from me")

        probes = [Angry() for _ in range(size)]
        haystack = list(range(size))
        assert_that(assert_that(probes).check().is_subset_of(haystack).passed).is_false()
        assert_that(assert_that(haystack).check().contains(*probes).passed).is_false()

    def test_one_object_repeated_is_named_once_whatever_else_is_there(self):
        same = float("nan")
        for values in ([same, same], [same, same, []]):
            outcome = assert_that(values).check().does_not_contain_duplicates()
            assert_that(outcome.passed).is_false()
            assert_that(outcome.message).contains("<nan> was repeated")

    def test_a_collection_with_no_length_is_searched_all_the_same(self):
        """The shortcut asks how big the pair is; a re-iterable without `__len__` cannot say, so it is tried."""

        class Countless:
            def __iter__(self):
                return iter(range(30))

        assert_that(not_contained_in([1, 2], Countless())).is_empty()
        assert_that(not_contained_in([99], Countless())).is_equal_to([99])
        assert_that(not_contained_in(Countless(), list(range(30)))).is_empty()

    def test_counting_falls_back_where_a_value_refuses_to_hash(self):
        """`Decimal` hashes as a rule and a signalling NaN still refuses, so the count gives way to the walk."""
        signalling = decimal.Decimal("snan")
        assert_that([signalling]).contains_exactly_in_any_order(signalling)
        outcome = assert_that([signalling]).check().contains_exactly_in_any_order(signalling, 1)
        assert_that(outcome.passed).is_false()


class TestAnAnswerIsAnAnswer:
    """A truthy object handed back by a predicate is not a verdict, and reading it as one passed anything."""

    def test_a_predicate_handing_back_a_matcher_is_refused(self):
        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that(5).satisfies(lambda value: match.greater_than(100))

    def test_a_factory_that_was_never_called_is_refused(self):
        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that([1, 2]).each(lambda value: match.is_none())

    def test_the_refusal_survives_the_probes_that_swallow_type_errors(self):
        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that([1, 2]).satisfies_exactly_in_any_order(lambda value: match.is_none(), lambda value: True)

    def test_a_duck_typed_matcher_counts_as_one(self):
        class Duck:
            def matches(self, value):
                return True

            def describe(self):
                return "anything"

            def describe_mismatch(self, value):
                return "nothing"

        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that(5).satisfies(lambda value: Duck())

    def test_an_ordinary_truthy_answer_is_still_an_answer(self):
        assert_that(5).satisfies(lambda value: "yes")
        assert_that(5).satisfies(lambda value: [0])

    def test_a_matcher_that_holds_its_members_on_the_instance_is_refused(self):
        """A matcher may install the three members in `__init__`, where reading the type alone misses them."""

        class Installed:
            def __init__(self):
                self.matches = lambda value: True
                self.describe = lambda: "installed"
                self.describe_mismatch = lambda value: "no"

        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that(5).satisfies(lambda value: Installed())

    def test_an_object_that_answers_every_name_is_not_a_matcher(self):
        """Read through `getattr`, a `Mock` has all three members and every answer became a refusal."""
        assert_that(5).satisfies(lambda value: unittest.mock.Mock())


class TestAMatcherAnswersWhereTheBuilderRefuses:
    """A matcher that raises cannot be negated or combined, so a question it cannot ask is a non-match."""

    @pytest.mark.parametrize(
        ("matcher", "value"),
        [
            pytest.param(match.contains("a"), b"abc", id="str-item-in-bytes"),
            pytest.param(match.contains(b"a"), "abc", id="bytes-item-in-str"),
            pytest.param(match.contains(1), "abc", id="int-item-in-str"),
            pytest.param(match.contains_only("a"), b"abc", id="only-str-item-in-bytes"),
            pytest.param(match.contains_only(b"a"), "abc", id="only-bytes-item-in-str"),
        ],
    )
    def test_an_item_the_value_cannot_be_searched_for_is_not_in_it(self, matcher, value):
        assert_that(matcher.matches(value)).described_as("plain").is_false()
        assert_that((~matcher).matches(value)).described_as("negated").is_true()
        assert_that((matcher | match.has_length(3)).matches(value)).described_as("either").is_true()
        assert_that(matcher.describe_mismatch(value)).contains("cannot be asked about")

    def test_the_builder_still_refuses_the_same_question(self):
        """The assertion names the mistake, since nothing downstream has to keep working."""
        with pytest.raises(TypeError):
            assert_that("abc").contains(b"a")

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda item: match.contains(item).matches([1]), id="contains"),
            pytest.param(lambda item: match.contains(item).describe_mismatch([1]), id="contains-mismatch"),
            pytest.param(lambda item: match.contains_only(item).matches([1]), id="contains-only"),
        ],
    )
    def test_a_nested_matcher_that_answers_with_a_matcher_is_still_refused(self, ask):
        """The refusal has to pass through the same `except TypeError` that turns a refusal into a no."""

        class Sneaky(BaseMatcher):
            def matches(self, value):
                return match.is_none()

            def describe(self):
                return "sneaky"

        with pytest.raises(TypeError, match="handed back a matcher"):
            ask(Sneaky())


class TestAOneShotValueIsReadOnce:
    """A generator handed to a composite was consumed by the first child, so the rest judged nothing."""

    @pytest.mark.parametrize(
        ("build", "held"),
        [
            pytest.param(lambda: match.contains(1) & match.contains(9), True, id="and-holding"),
            pytest.param(lambda: match.contains(1) & match.contains(7), False, id="and-failing"),
            pytest.param(lambda: match.contains(7) | match.contains(9), True, id="or-holding"),
            pytest.param(lambda: match.contains(5) | match.contains(7), False, id="or-failing"),
            pytest.param(lambda: match.all_of(match.contains(1), match.contains(9)), True, id="all-of"),
            pytest.param(lambda: match.any_of(match.contains(7), match.contains(9)), True, id="any-of"),
        ],
    )
    def test_every_child_sees_the_whole_value(self, build, held):
        assert_that(build().matches(item for item in [1, 9])).is_equal_to(held)

    def test_the_reason_reads_the_same_value_the_verdict_did(self):
        composite = match.contains(1) & match.contains(7)
        assert_that(composite.describe_mismatch(item for item in [1, 9])).contains("missing")

    def test_each_item_names_the_item_that_failed(self):
        """Deciding drained the generator, and describing afterwards saw only what was left of it."""
        outcome = (
            assert_that({"items": (item for item in [1, 2, -3])})
            .check()
            .matches_structure({"items": match.each_item(match.greater_than(0))})
        )
        assert_that(outcome.message).contains("item at index 2 <-3>")

    def test_a_re_iterable_value_is_walked_rather_than_copied(self):
        class Counting(list):
            def __init__(self, items):
                super().__init__(items)
                self.walks = 0

            def __iter__(self):
                self.walks += 1
                return super().__iter__()

        value = Counting([1, 9])
        assert_that((match.contains(1) & match.contains(9)).matches(value)).is_true()
        assert_that(value.walks).described_as("walks").is_greater_than(0)


class TestPairingIsIterative:
    """Kuhn's augmenting path recursed as deep as the input is wide, and 1100 pairs is past the limit."""

    def test_a_thousand_items_pair_without_running_out_of_stack(self):
        items = list(range(1200))
        assert_that(items).satisfies_exactly_in_any_order(*[match.greater_than(-1) for _ in items])

    @needs_groups
    def test_an_exception_group_of_a_thousand_still_matches(self):
        def raise_group():
            raise ExceptionGroup("many", [ValueError(str(index)) for index in range(1200)])

        assert_that(raise_group).raises(ExceptionGroup).when_called_with().matches_error_tree(*([ValueError] * 1200))

    def test_an_unpairable_item_is_still_named(self):
        outcome = assert_that([1, 2]).check().satisfies_exactly_in_any_order(match.greater_than(5), match.less_than(5))
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).contains("no pairing covers 1 item")
        assert_that([str(entry.expected) for entry in outcome.diff.entries]).contains(
            match.contains_string("greater than")
        )


class TestAHostileValueCannotBreakTheReport:
    """A value whose `__repr__` or `__str__` raises turned every failure into the user's own exception."""

    def test_a_raising_repr_is_rendered_as_a_placeholder(self):
        class BadRepr:
            def __repr__(self):
                raise RuntimeError("no repr from me")

        class Holder:
            colour = BadRepr()

        assert_that(match.has_property("colour", match.is_none()).describe_mismatch(Holder())).contains("unreprable")
        assert_that(match.has_property("missing", match.is_none()).describe_mismatch(BadRepr())).contains("unreprable")
        for call in (
            lambda: assert_that(BadRepr()).is_none(),
            lambda: assert_that(BadRepr()).is_instance_of(int),
            lambda: assert_that(BadRepr()).satisfies(match.is_none()),
            lambda: assert_that([BadRepr()]).satisfies(match.each_item(match.is_none())),
        ):
            with pytest.raises(AssertionFailure, match="unreprable"):
                call()

    def test_a_raising_str_still_names_the_subject_of_a_negated_call(self):
        class BadStr:
            def __str__(self):
                raise RuntimeError("no str from me")

            def __repr__(self):
                return "BadStr()"

        with pytest.raises(AssertionFailure, match="BadStr"):
            assert_that(BadStr()).not_.is_instance_of(BadStr)

    def test_an_exception_whose_str_raises_still_pivots(self):
        class BadStrError(Exception):
            def __str__(self):
                raise RuntimeError("no str from me")

        def raise_it():
            raise BadStrError

        def raise_from_it():
            try:
                raise BadStrError
            except BadStrError as cause:
                raise ValueError("outer") from cause

        assert_that(assert_that(raise_it).raises(BadStrError).when_called_with().val).contains("BadStrError")
        pivoted = assert_that(raise_from_it).raises(ValueError).when_called_with().caused_by(BadStrError)
        assert_that(pivoted.val).contains("BadStrError")


class TestReadingOnceDoesNotReplaceTheValue:
    """Reading a one-shot value for the children that walk it must not hand a list to the ones that do not."""

    def test_a_type_check_beside_a_walk_still_sees_what_was_passed(self):
        composite = match.is_instance_of(list) & match.contains(1)
        assert_that(composite.matches(item for item in [1, 9])).described_as("a generator is not a list").is_false()
        assert_that(composite.matches([1, 9])).described_as("a list is").is_true()

    def test_an_alternative_that_holds_without_walking_reads_nothing(self):
        walks = []

        class Counting:
            def __iter__(self):
                walks.append(1)
                return iter([1, 9])

        assert_that(match.any_of(match.is_not_none(), match.contains(1)).matches(Counting())).is_true()
        assert_that(walks).described_as("walks").is_empty()

    def test_an_endless_value_is_answered_rather_than_read(self):
        """`evaluate` decides and describes in one walk, so it must stop where the walk stops."""
        endless = itertools.count()
        result = match.each_item(match.less_than(3)).evaluate(endless)
        assert_that(result.matched).is_false()
        assert_that(result.mismatch).contains("item at index 3")


class TestARefusalFromInsideTheValueIsNotAMismatch:
    """Answering "no match" to somebody's own `TypeError` sends the reader looking in the wrong file."""

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(lambda: match.contains(1).matches, id="contains"),
            pytest.param(lambda: match.contains(1).describe_mismatch, id="contains-mismatch"),
            pytest.param(lambda: match.contains_only(1).matches, id="contains-only"),
        ],
    )
    def test_a_container_whose_membership_raises_is_not_answered(self, build):
        class Angry:
            def __contains__(self, item):
                raise TypeError("my own refusal")

            def __iter__(self):
                return iter([1])

            def __eq__(self, other):
                raise TypeError("my own refusal")

            __hash__ = None

        with pytest.raises(TypeError, match="my own refusal"):
            build()(Angry())


class TestBoundsAreCheckedOnlyWhereTheyCanBe:
    """Two values that each order plainly need not order against each other."""

    @pytest.mark.parametrize(
        ("low", "high"),
        [
            pytest.param(datetime.datetime(2020, 1, 1), datetime.date(2020, 1, 2), id="datetime-against-date"),
            pytest.param(datetime.time(1, tzinfo=datetime.timezone.utc), datetime.time(2), id="aware-against-naive"),
        ],
    )
    def test_an_unorderable_pair_is_judged_where_it_is_used(self, low, high):
        """Construction says nothing about a pair it cannot order, and matching answers "no"."""
        assert_that(match.between(low, high).matches(low)).is_false()

    def test_swapped_bounds_are_still_refused_at_construction(self):
        with pytest.raises(ValueError, match="less than"):
            match.between(10, 1)

    def test_a_negative_tolerance_is_still_refused_at_construction(self):
        with pytest.raises(ValueError, match="must not be negative"):
            match.close_to(1, -1)

    def test_a_zero_tolerance_is_allowed(self):
        assert_that(match.close_to(1, 0).matches(1)).is_true()


class TestARefusalThatCannotBeReproducedIsNotRewritten:
    """The second ask learns who refused, and a refusal it cannot find again is handed on as it was."""

    def test_a_container_that_refuses_only_once_keeps_its_own_error(self):
        class Moody:
            def __init__(self):
                self.asked = 0

            def __contains__(self, item):
                self.asked += 1
                if self.asked == 1:
                    raise TypeError("only the first time")
                return False

            def __iter__(self):
                return iter([])

        with pytest.raises(TypeError, match="only the first time"):
            missing_items(Moody(), [1], _is_matcher)

    def test_an_element_whose_equality_changes_its_answer_is_asked_once(self):
        """The refusal ``in`` raised is answered as caught: asked again, the second answer passed the item."""
        numpy = pytest.importorskip("numpy")

        class Fickle:
            def __init__(self):
                self.asked = 0

            def __eq__(self, other):
                self.asked += 1
                return numpy.array([True, False]) if self.asked == 1 else True

            __hash__ = None

        fickle = Fickle()
        with pytest.raises(ValueError, match="ambiguous"):
            assert_that([fickle]).contains(5)
        assert_that(fickle.asked).is_equal_to(1)

    def test_a_mapping_of_many_non_string_keys_says_how_many_it_dropped(self):
        wide = {index: index for index in range(101)}
        written = _json_safe(wide)
        assert_that(written["__type__"]).is_equal_to("dict")
        assert_that(written["__truncated__"]).contains("1 more keys")


class TestWhatCountsAsAMatcherIsReadWithoutRunningAnything:
    """The three members may live on the type, in the instance dictionary or in slots."""

    def test_a_matcher_holding_its_members_in_slots_is_refused(self):
        class Slotted:
            __slots__ = ("describe", "describe_mismatch", "matches")

            def __init__(self):
                self.matches = lambda value: True
                self.describe = lambda: "slotted"
                self.describe_mismatch = lambda value: "no"

        with pytest.raises(TypeError, match="handed back a matcher"):
            assert_that(5).satisfies(lambda value: Slotted())

    def test_an_object_whose_slots_were_never_filled_is_an_answer(self):
        class Empty:
            __slots__ = ("describe", "describe_mismatch", "matches")

        assert_that(5).satisfies(lambda value: Empty())

    @pytest.mark.parametrize("shape", ["a-slot-holding-something-else", "a-class-attribute-that-is-not-callable"])
    def test_a_slotted_object_that_is_not_a_matcher_is_an_answer(self, shape):
        """Slots of its own say nothing: the three names have to be there and have to be callable."""

        class Counter:
            __slots__ = ("matches",)

            def __init__(self):
                self.matches = 5

        class Mixed:
            __slots__ = ("matches",)
            describe = "not callable at all"

            def __init__(self):
                self.matches = lambda value: True

        answer = Counter() if shape.startswith("a-slot") else Mixed()
        assert_that(5).satisfies(lambda value: answer)


class TestAToleranceRefusalIsNotABug:
    """The `Fraction` retry repairs a mixed pair, and a value whose own arithmetic raises is not that."""

    def test_a_number_whose_subtraction_raises_is_handed_on(self):
        class Angry(float):
            def __sub__(self, other):
                raise TypeError("my own refusal")

            def __rsub__(self, other):
                raise TypeError("my own refusal")

        with pytest.raises(TypeError, match="my own refusal"):
            assert_that({"a": Angry(1.0)}).is_equal_to({"a": 2.0}, tolerance=0.5)

    def test_a_window_whose_own_subtraction_raises_is_handed_on(self):
        """The difference is taken first, so only a value that refuses the tolerance alone reaches the window."""

        class AngryAtTolerances(float):
            def __sub__(self, other):
                if other == 0.5:
                    raise TypeError("my own refusal")
                return float(self) - other

        with pytest.raises(TypeError, match="my own refusal"):
            match.close_to(AngryAtTolerances(1.0), 0.5).matches(3.0)

    def test_a_mixed_pair_is_still_repaired(self):
        """A `Decimal` against a `float` refuses to subtract, which is the pair the retry is there for."""
        assert_that({"a": decimal.Decimal("1.0")}).is_equal_to({"a": 1.05}, tolerance=0.1)


class TestAPropertyIsReadOnce:
    """Asked through `hasattr` and then again, a property that counts its reads answered the two apart."""

    def test_describing_a_mismatch_reads_it_once(self):
        class Counting:
            def __init__(self):
                self.reads = 0

            @property
            def size(self):
                self.reads += 1
                return self.reads

        holder = Counting()
        match.has_property("size", match.greater_than(100)).describe_mismatch(holder)
        assert_that(holder.reads).described_as("reads").is_equal_to(1)

    def test_a_property_that_is_not_there_still_says_so(self):
        assert_that(match.has_property("nowhere").describe_mismatch(object())).contains("has no property")


class TestNobodysCodeDecidesAVerdict:
    """A value handed back as an answer is read, never asked: what it says is not its own verdict."""

    def test_an_object_that_answers_every_read_by_raising_is_still_an_answer(self):
        class Hostile:
            def __getattribute__(self, name):
                raise RuntimeError("my own code ran")

        assert_that(5).satisfies(lambda value: Hostile())

    def test_a_metaclass_that_fabricates_members_does_not_make_a_matcher(self):
        class Fabricating(type):
            def __getattr__(cls, name):
                return lambda *args, **kwargs: True

        class Fabricated(metaclass=Fabricating):
            pass

        assert_that(5).satisfies(lambda value: Fabricated())

    def test_a_coroutine_is_still_refused(self):
        async def probe():
            return True

        with pytest.raises(TypeError, match="handed back a coroutine"):
            assert_that(5).satisfies(lambda value: probe())


class TestAWindowThatCannotBeBuiltIsNotACrash:
    """A pair with no interval answers no match rather than raising out of the matcher."""

    @pytest.mark.parametrize(
        "middle",
        [
            pytest.param(decimal.Decimal("Infinity"), id="infinite-decimal"),
            pytest.param(decimal.Decimal("NaN"), id="decimal-nan"),
            pytest.param(float("inf"), id="infinite-float"),
        ],
    )
    def test_a_middle_without_a_window_answers_no_match(self, middle):
        assert_that(match.close_to(middle, 0.5).matches(1)).is_false()

    @pytest.mark.parametrize(
        "middle",
        [
            pytest.param(decimal.Decimal("NaN"), id="decimal-nan"),
            pytest.param(decimal.Decimal("sNaN"), id="signalling-nan"),
            pytest.param("text", id="not-a-number-at-all"),
        ],
    )
    def test_a_pair_with_no_window_says_so_in_its_own_terms(self, middle):
        """The exact conversion refuses too, and a stray `ValueError` is not what a matcher can answer."""
        with pytest.raises(WindowRefusedError):
            tolerance_window(middle, 0.5)

    def test_a_pair_that_has_one_still_gets_it(self):
        assert_that(tolerance_window(decimal.Decimal("1.5"), 0.5)).is_equal_to(
            (fractions.Fraction(1), fractions.Fraction(2))
        )

    @pytest.mark.parametrize(
        "middle",
        [pytest.param(decimal.Decimal("Infinity"), id="decimal"), pytest.param(float("inf"), id="float")],
    )
    def test_an_infinite_expectation_fails_the_assertion_rather_than_breaking_it(self, middle):
        """A float infinity has always failed here, and a `Decimal` one raised out of the conversion."""
        assert_that(assert_that(1).check().is_close_to(middle, 0.5).passed).is_false()


class TestTheEqualityProbeAsksWhatTheOperatorWouldAsk:
    """`_both_decline` replays `==`, and replaying it through ordinary lookup asks a different question."""

    def test_a_metaclass_cannot_fabricate_the_answer(self):
        """`type(x).__eq__` is an ordinary read on the class, and `==` never makes one."""

        class Hooked(type):
            def __getattribute__(cls, name):
                return (lambda *args: False) if name == "__eq__" else type.__getattribute__(cls, name)

        class Plain(metaclass=Hooked):
            pass

        assert_that(_both_decline(Plain(), Plain())).described_as("what object's own __eq__ answers").is_true()

    def test_two_sides_that_really_decline_still_decline(self):
        class Declining:
            def __eq__(self, other):
                return NotImplemented

            __hash__ = None

        assert_that(_both_decline(Declining(), Declining())).is_true()
        assert_that(_both_decline(1, "text")).described_as("an int against a string").is_true()
        assert_that(_both_decline(1, 2)).described_as("two ints").is_false()


class TestAnInfiniteWindowStillReadsItsTolerance:
    """(inf, inf) is the right window only where the tolerance is one, or an infinity matches anything."""

    @pytest.mark.parametrize("tolerance", [object(), "wide"], ids=["object", "string"])
    def test_a_tolerance_that_is_not_a_number_has_no_window(self, tolerance):
        assert_that(match.close_to(float("inf"), tolerance).matches(float("inf"))).is_false()

    def test_no_tolerance_and_no_rel_is_refused_where_it_is_written(self):
        refused = assert_that(match.close_to).raises(TypeError).when_called_with(float("inf"), None).value
        assert_that(refused).is_equal_to(
            "given tolerance arg must be a number, or a rel given instead, but was <None> (NoneType)"
        )

    def test_an_infinity_against_itself_within_a_real_tolerance_holds(self):
        assert_that(match.close_to(float("inf"), 0.5).matches(float("inf"))).is_true()
        assert_that(match.close_to(decimal.Decimal("Infinity"), 0.5).matches(decimal.Decimal("Infinity"))).is_true()

    def test_a_decimal_subclass_is_not_asked_whether_it_is_infinite(self):
        """Its own `is_infinite` would decide this, and run before the arithmetic it is asked about."""

        class Loud(decimal.Decimal):
            def is_infinite(self):
                raise RuntimeError("my own code ran")

        assert_that(tolerance_window(Loud("1.5"), decimal.Decimal("0.5"))).is_equal_to(
            (decimal.Decimal("1.0"), decimal.Decimal("2.0"))
        )


class TestTheProbeCallsWhatTheOperatorCalls:
    """A class may hold its `__eq__` as anything the descriptor protocol binds, and `==` binds it."""

    def test_a_staticmethod_eq_is_bound_the_way_it_is_written(self):
        class Static:
            @staticmethod
            def __eq__(other):
                return NotImplemented

            __hash__ = None

        assert_that(_both_decline(Static(), Static())).is_true()

    def test_an_eq_that_binds_to_nothing_is_called_the_way_the_operator_calls_it(self):
        """Read off the class and bound to nothing, it is called with the other side alone, as `==` does."""
        calls = []

        class Recording:
            def __call__(self, *args):
                calls.append(args)
                return NotImplemented

        class Odd:
            __eq__ = Recording()
            __hash__ = None

        one, other = Odd(), Odd()
        one == other  # noqa: B015  # asked for what the operator passes, not for the answer
        by_the_operator = calls[0]  # the first of the two directions the operator tries
        calls.clear()
        assert_that(_declines(one, other)).described_as("declined").is_true()
        assert_that(calls).described_as("calls the probe made").is_length(1)
        assert_that(calls[0]).described_as("what the probe passed").is_equal_to(by_the_operator)

    def test_a_plain_eq_still_answers(self):
        assert_that(_both_decline(1, "text")).described_as("an int against a string").is_true()
        assert_that(_both_decline(1, 2)).described_as("two ints").is_false()


class TestAToleranceIsAnOrderedDistance:
    """A window needs a real tolerance: a complex one has no order, and an infinity matched everything."""

    @pytest.mark.parametrize(
        "tolerance",
        [1j, complex(1, 0), math.nan, decimal.Decimal("NaN")],
        ids=["imaginary", "complex-with-no-imaginary-part", "nan", "decimal-nan"],
    )
    def test_a_tolerance_with_no_order_has_no_window(self, tolerance):
        assert_that(match.close_to(float("inf"), tolerance).matches(float("inf"))).is_false()

    def test_a_tolerance_of_its_own_type_is_not_compared_when_the_matcher_is_built(self):
        class Loud(float):
            def __lt__(self, other):
                raise RuntimeError("compared at construction")

            __gt__ = __lt__

        assert_that(match.close_to(1.0, Loud(0.5)).describe()).contains("within")

    @pytest.mark.parametrize(
        ("expected", "tolerance"),
        [("x", 1), ([1], 1), (5, datetime.timedelta(days=1)), (1j, 1)],
        ids=["text", "a-list", "a-duration-between-numbers", "a-complex-value"],
    )
    def test_a_value_with_no_distance_is_not_close_even_to_itself(self, expected, tolerance):
        assert_that(match.close_to(expected, tolerance).matches(expected)).is_false()

    def test_an_expected_value_with_no_distance_is_not_close_to_a_number(self):
        assert_that(match.close_to("x", 1).matches(5)).is_false()

    def test_a_bool_is_no_distance_and_is_measured_by_none(self):
        """`True` and `False` are one apart as ints, and a tolerance of one still tells them apart."""
        with pytest.raises(AssertionError):
            assert_that({"flag": True}).is_equal_to({"flag": False}, tolerance=1)
        assert_that(match.close_to(1, True).matches(1.5)).is_false()

    def test_a_decimal_tolerance_is_a_real_one(self):
        assert_that(tolerance_window(decimal.Decimal(1), decimal.Decimal("0.5"))).is_equal_to(
            (decimal.Decimal("0.5"), decimal.Decimal("1.5"))
        )
        assert_that(
            match.close_to(decimal.Decimal("Infinity"), decimal.Decimal("0.5")).matches(decimal.Decimal("Infinity"))
        ).is_true()


class TestTheMatcherMeasuresWhatTheAssertionMeasures:
    """The matcher refused a pair it could build no window around, where the assertion measured the same pair."""

    @pytest.mark.parametrize(
        ("value", "expected", "tolerance"),
        [
            pytest.param(
                datetime.datetime(2026, 1, 1),
                datetime.datetime(2026, 1, 1, 1),
                datetime.timedelta.max,
                id="a-window-past-the-calendar",
            ),
            pytest.param(decimal.Decimal("0.1"), 1, math.inf, id="an-infinite-float-tolerance-around-a-decimal"),
            pytest.param(0.7, 1, decimal.Decimal("Infinity"), id="an-infinite-decimal-tolerance-around-a-float"),
        ],
    )
    def test_both_spellings_hold_the_pair(self, value, expected, tolerance):
        assert_that(value).is_close_to(expected, tolerance)
        assert_that(match.close_to(expected, tolerance).matches(value)).is_true()

    @pytest.mark.parametrize(
        ("expected", "tolerance", "value"),
        [
            pytest.param(_EqualToAnything(), 1, 5, id="equal-to-anything"),
            pytest.param(5, datetime.timedelta(hours=1), datetime.datetime(2026, 1, 1), id="a-number-under-a-duration"),
            pytest.param(datetime.datetime(2026, 1, 1), 1, 5, id="a-moment-under-a-number"),
        ],
    )
    def test_an_expected_value_the_assertion_refuses_is_close_to_nothing(self, expected, tolerance, value):
        """Equality answers before any distance, so an expected value equal to everything matched everything."""
        with pytest.raises(TypeError):
            assert_that(value).is_close_to(expected, tolerance)
        assert_that(match.close_to(expected, tolerance).matches(value)).is_false()

    @pytest.mark.parametrize(
        ("value", "expected"), [(True, 2), (2, True), (True, True)], ids=["subject", "expected", "both"]
    )
    def test_a_bool_is_refused_by_the_assertion_and_close_to_nothing(self, value, expected):
        """Both read a bool as its int once, where `tolerance=` leaves a bool out of any distance."""
        with pytest.raises(TypeError):
            assert_that(value).is_close_to(expected, 1)
        assert_that(match.close_to(expected, 1).matches(value)).is_false()

    def test_a_naive_moment_is_no_match_for_an_aware_one_rather_than_an_error(self):
        aware = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        matcher = match.close_to(aware, datetime.timedelta(hours=1))
        assert_that(matcher.matches(datetime.datetime(2026, 1, 1))).is_false()


class TestTheShortcutAndTheWalkAgree:
    """Each of these reads a collection in one pass where it read it once per item; the answer is the same."""

    @pytest.mark.parametrize(
        ("values", "items"),
        [
            pytest.param([1, 2, 3], [1, 9], id="hashable"),
            pytest.param([[1], [2]], [[1], [9]], id="unhashable"),
            pytest.param([1, 1, 2], [1, 2, 3], id="repeats"),
            pytest.param(list(range(80)), list(range(70, 90)), id="past-the-threshold"),
            pytest.param([True, 1, 2], [1, True], id="bool-against-int"),
            pytest.param([decimal.Decimal("1.0"), 1], [1], id="decimal-against-int"),
            pytest.param([], [1], id="empty"),
        ],
    )
    def test_occurrences_counts_what_the_walk_counts(self, values, items):
        assert_that(occurrences(values, items)).is_equal_to([values.count(item) for item in items])

    def test_a_type_that_passes_the_rule_and_still_refuses_falls_back(self):
        """A signalling NaN is a `Decimal`, which the rule allows, and it refuses to hash all the same."""
        signalling = decimal.Decimal("snan")
        values = [signalling] * 30
        assert_that(occurrences(values, [signalling] * 30)).is_equal_to([30] * 30)

    def test_a_value_that_refuses_to_hash_falls_back_to_the_walk(self):
        class Angry:
            def __hash__(self):
                raise RuntimeError("no hash from me")

            def __eq__(self, other):
                return self is other

        one = Angry()
        assert_that(occurrences([one, one], [one])).is_equal_to([2])

    @pytest.mark.parametrize(
        ("values", "items"),
        [
            pytest.param(list(range(50)), [60, 70], id="absent"),
            pytest.param(list(range(50)), [1, 60], id="one-present"),
            pytest.param([[1], [2]], [[3]], id="unhashable"),
            pytest.param("abcdef", ["cd", "xy"], id="substring"),
            pytest.param([1, 2], [True, 5], id="bool-against-int"),
        ],
    )
    def test_does_not_contain_answers_as_the_walk_did(self, values, items):
        walked = [item for item in items if item in values]
        outcome = assert_that(values).check().does_not_contain(*items)
        assert_that(outcome.passed).is_equal_to(not walked)


_LEAF_OPTIONS = {
    "tolerance": {"tolerance": 0.1},
    "ignore_null": {"ignore_null": True},
    "comparators": {"comparators": {"unrelated": lambda actual, expected: True}},
    "strict_types": {"strict_types": True},
}


def _spellings_of_equality():
    """Every way the library asks whether two values are equal, each answering as a bool."""
    spellings = {
        "is_equal_to": lambda actual, expected: assert_that(actual).check().is_equal_to(expected).passed,
        "is_not_equal_to": lambda actual, expected: not assert_that(actual).check().is_not_equal_to(expected).passed,
        "not_.is_equal_to": lambda actual, expected: not assert_that(actual).check().not_.is_equal_to(expected).passed,
        "equal_to": lambda actual, expected: match.equal_to(expected).matches(actual),
        "not_(equal_to)": lambda actual, expected: not match.not_(match.equal_to(expected)).matches(actual),
        "matches_inline": lambda actual, expected: assert_that(actual).check().matches_inline(expected).passed,
        "in a list": lambda actual, expected: assert_that([actual]).check().is_equal_to([expected]).passed,
        "in a mapping": lambda actual, expected: (
            assert_that({"item": actual}).check().is_equal_to({"item": expected}).passed
        ),
        "in a dataclass, ignore": lambda actual, expected: (
            assert_that(_Holder(actual, 1)).check().is_equal_to(_Holder(expected, 2), ignore="noise").passed
        ),
        "equal_to in a mapping, ignore": lambda actual, expected: match.equal_to(
            {"item": expected, "noise": 2}, ignore="noise"
        ).matches({"item": actual, "noise": 1}),
        "matches_structure": lambda actual, expected: (
            assert_that({"item": actual}).check().matches_structure({"item": expected}).passed
        ),
        "structure": lambda actual, expected: match.structure({"item": expected}).matches({"item": actual}),
        "has_<key>": lambda actual, expected: assert_that({"item": actual}).check().has_item(expected).passed,
        "has_<attribute>": lambda actual, expected: assert_that(_Carrier(actual)).check().has_item(expected).passed,
        "contains_entry": lambda actual, expected: (
            assert_that({"item": actual}).check().contains_entry({"item": expected}).passed
        ),
        "does_not_contain_entry": lambda actual, expected: (
            not assert_that({"item": actual}).check().does_not_contain_entry({"item": expected}).passed
        ),
        "contains_sequence": lambda actual, expected: (
            assert_that([actual, 0]).check().contains_sequence(expected, 0).passed
        ),
        "contains": lambda actual, expected: assert_that([actual]).check().contains(expected).passed,
    }
    for name, selector in (("ignore", {"ignore": "noise"}), ("include", {"include": "item"})):
        spellings[f"in a mapping, {name}"] = lambda actual, expected, selector=selector: (
            (
                assert_that({"item": actual, "noise": 1})
                .check()
                .is_equal_to({"item": expected, "noise": 2}, **selector)
            ).passed
        )
    for name, options in _LEAF_OPTIONS.items():
        spellings[f"is_equal_to, {name}"] = lambda actual, expected, options=options: (
            assert_that(actual).check().is_equal_to(expected, **options).passed
        )
        spellings[f"equal_to, {name}"] = lambda actual, expected, options=options: match.equal_to(
            expected, **options
        ).matches(actual)
        spellings[f"in a mapping, {name}"] = lambda actual, expected, options=options: (
            assert_that({"item": actual}).check().is_equal_to({"item": expected}, **options).passed
        )
        spellings[f"in a list, {name}"] = lambda actual, expected, options=options: (
            assert_that([actual]).check().is_equal_to([expected], **options).passed
        )
    return spellings


def _asked(spelling, actual, expected):
    try:
        return spelling(actual, expected)
    except Exception as error:  # a spelling that raises where `==` answered disagrees with it
        return f"raised {type(error).__name__}: {error}"


class TestEverySpellingOfEqualityAsksEq:
    """`==` decides equality wherever a value is compared for it, and `!=` is never asked.

    `is_equal_to` asked `!=` while `is_not_equal_to` asked `==`, so a type whose `__ne__` is not the negation
    of its `__eq__` failed both, and a list holding the same pair, which compares its members with `==`,
    passed.  A `str`, `int` or `dict` subclass replacing `__eq__` alone is such a type: it keeps the base
    type's `__ne__`.
    """

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            pytest.param(_Split(0), _Split(1), id="both-say-yes"),
            pytest.param(_NeverEqual(), _NeverEqual(), id="both-say-no"),
            pytest.param(_Column("a"), _Column("b"), id="truthy-non-bool"),
            pytest.param(_NeRaises(0), _NeRaises(0), id="ne-raises-equal"),
            pytest.param(_NeRaises(0), _NeRaises(1), id="ne-raises-unequal"),
            pytest.param(_CaseInsensitive("Ada"), _CaseInsensitive("ada"), id="str-subclass"),
        ],
    )
    def test_every_spelling_answers_what_eq_answers(self, actual, expected):
        equal = bool(actual == expected)
        answers = {name: _asked(spelling, actual, expected) for name, spelling in _spellings_of_equality().items()}
        assert_that({name: answer for name, answer in answers.items() if answer is not equal}).is_empty()

    def test_both_entry_assertions_ask_with_the_actual_value_on_the_left(self):
        """As `is_equal_to` asks, where `does_not_contain_entry` alone put the expected value on the left."""
        held = {"item": _Split(0)}
        assert_that(held).contains_entry({"item": _NeverEqual()})
        assert_that(assert_that(held).check().does_not_contain_entry({"item": _NeverEqual()}).passed).is_false()

    def test_is_zero_asks_eq(self):
        within_one_of_zero = _WithinOne(1)
        assert_that(within_one_of_zero).is_zero()
        assert_that(assert_that(within_one_of_zero).check().is_not_zero().passed).is_false()
        assert_that(match.is_zero().matches(within_one_of_zero)).is_true()

    def test_a_byte_is_compared_with_eq(self):
        assert_that(b"\x01").has_byte_at(0, _WithinOne(2))

    def test_hex_is_compared_with_eq(self):
        assert_that(_CaseFoldedBytes(b"AB")).is_hex_equal_to("6162")

    def test_a_file_name_is_compared_with_eq(self, tmp_path):
        report = tmp_path / "Report.txt"
        report.write_text("")
        assert_that(str(report)).is_named(_CaseInsensitive("report.TXT"))

    def test_the_position_contains_exactly_reports_is_found_with_eq(self):
        """Equal multisets in another order, where `!=` found no differing position and `next()` ran dry."""
        first, second = _OrderSensitive(x=1, y=2), _OrderSensitive(y=2, x=1)
        with pytest.raises(AssertionFailure, match="the order differs at index 0"):
            assert_that([first, second]).contains_exactly(second, first)

    def test_a_closest_element_shares_a_key_eq_calls_equal(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([{"name": _CaseInsensitive("Ada"), "id": 1}]).contains({"name": "ada", "id": 2})
        assert_that(str(failure.value)).contains("Closest element")

    def test_a_pair_eq_calls_equal_is_elided_from_the_message(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([_CaseInsensitive("Ada"), "x" * 60]).is_equal_to(["ada", "y" * 60])
        assert_that(str(failure.value)).starts_with("Expected <[.., 'xxx")

    def test_two_classes_that_decline_equality_differ_whatever_ne_says(self):
        """Under an option the walk would compare their fields, so the kinds decide, and `!=` had the last word."""
        assert_that(match.equal_to(_Unrelated(1), tolerance=0.1).matches(_AnsweringInequality(1))).is_false()

    def test_a_mapping_of_its_own_is_asked_with_eq(self):
        """A `dict` subclass replacing `__eq__` alone keeps `dict.__ne__`, which ignores the order `==` reads."""
        first, reordered = _OrderSensitive(x=1, y=2), _OrderSensitive(y=2, x=1)
        assert_that(assert_that(first).check().is_equal_to(reordered).passed).is_false()
        assert_that(first).is_not_equal_to(reordered)

    def test_a_shifted_pair_eq_calls_equal_is_elided_from_the_message(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(["p" * 30, _CaseInsensitive("Ada"), "q" * 30]).is_equal_to(["new", "p" * 30, "ada", "q" * 30])
        assert_that(str(failure.value)).starts_with("Expected <[..]> to be equal to <['new', ..]>")

    def test_a_pair_eq_calls_equal_leaves_nothing_for_an_alignment_to_win(self):
        outcome = assert_that([_CaseInsensitive("Ada"), 1]).check().is_equal_to(["ada", 1, 2])
        assert_that([(entry.path, entry.absent) for entry in outcome.diff.entries]).is_equal_to([("[2]", "actual")])

    def test_case_is_ignored_by_asking_eq_of_the_lowered_values(self):
        assert_that(_Accentless("Café")).is_equal_to_ignoring_case("CAFE")

    @pytest.mark.parametrize(
        "ignoring", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds", "is_equal_to_ignoring_time"]
    )
    def test_a_date_is_compared_by_asking_eq(self, ignoring):
        getattr(assert_that(_MonthlyStamp(2026, 1, 2, 3, 4, 5)), ignoring)(datetime.datetime(2026, 1, 20, 3, 4, 5))

    def test_an_eq_that_changes_its_answer_still_gets_a_failure(self):
        """Unequal as a list, equal as a multiset and at every position: no position to name, and no crash."""
        calls = []

        class Fickle:
            def __eq__(self, other):
                calls.append(other)
                return len(calls) > 1

            __hash__ = None

        with pytest.raises(AssertionFailure) as failure:
            assert_that([Fickle()]).contains_exactly(Fickle())
        assert_that(str(failure.value)).ends_with("but did not.")

    def test_a_difference_eq_finds_is_not_explained_by_a_normalisation(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([_NeverEqual()]).is_equal_to([_NeverEqual()])
        assert_that(str(failure.value)).does_not_contain("every difference here")


class _WalkedInt(int):
    """An `int` the ordering shortcuts do not recognise, so a pair holding it goes the general way."""


class _WalkedFloat(float):
    """A `float` the ordering shortcuts do not recognise."""


_REAL = st.one_of(st.integers(), st.integers(-(2**70), 2**70), st.floats(allow_nan=True, allow_infinity=True))


class TestTheOrderingShortcutsAnswerAsTheWalk:
    """An int against a float, and a plain sequence, are ordered without the general walk; the answers are its own."""

    @settings(max_examples=300)
    @given(_REAL, _REAL)
    @example(1, 1.0)
    @example(1.0, 1)
    @example(2**53 + 1, float(2**53))
    @example(float(2**53), 2**53 + 1)
    @example(10**400, 1e308)
    @example(1e308, 10**400)
    @example(10**400, math.inf)
    @example(-(10**400), -math.inf)
    @example(math.nan, 1)
    @example(1, math.nan)
    @example(0, -0.0)
    def test_an_int_against_a_float_orders_as_the_general_path(self, left, right):
        walked = _WalkedInt(left) if type(left) is int else _WalkedFloat(left)
        assert_that(compare(left, right)).is_equal_to(compare(walked, right))
        for relation in ("lt", "le", "gt", "ge"):
            assert_that(holds(left, right, relation)).is_equal_to(holds(walked, right, relation))

    @settings(max_examples=300)
    @given(
        st.one_of(
            st.lists(st.integers(-3, 3), max_size=12),
            st.lists(st.text("ab", max_size=2), max_size=12),
            st.lists(st.binary(max_size=2), max_size=12),
        ),
        st.booleans(),
    )
    def test_a_plain_sequence_breaks_where_the_walk_does(self, items, reverse):
        walked = first_out_of_order(items, key=lambda item: item, reverse=reverse)
        assert_that(first_plainly_out_of_order(items, reverse=reverse)).is_equal_to(walked)
        assert_that(first_plainly_out_of_order(tuple(items), reverse=reverse)).is_equal_to(walked)

    @pytest.mark.parametrize(
        ("items", "plain"),
        [
            pytest.param([1, 2, 3, 4, 5], True, id="ints"),
            pytest.param(("a", "b", "c", "d", "e"), True, id="strings"),
            pytest.param([b"a"] * 5, True, id="bytes"),
            pytest.param([1, 2, 3, 4], False, id="under-five"),
            pytest.param([1.0] * 5, False, id="a-float-may-be-nan"),
            pytest.param([1, 2, 3, 4, "e"], False, id="mixed"),
            pytest.param([True] * 5, False, id="bool"),
            pytest.param([_WalkedInt(1)] * 5, False, id="int-subclass"),
            pytest.param(type("Listed", (list,), {})([1] * 5), False, id="list-subclass"),
            pytest.param(iter([1] * 5), False, id="one-shot"),
        ],
    )
    def test_only_a_plain_sequence_takes_the_pass(self, items, plain):
        assert_that(plainly_sortable(items)).is_equal_to(plain)

    def test_a_type_is_told_apart_without_asking_its_metaclass_to_hash_it(self):
        class Unhashed(type):
            __hash__ = None

        refusing = Unhashed("Refusing", (), {})()
        assert_that(plainly_sortable([1, 2, 3, 4, 5, refusing])).is_false()

    def test_a_key_set_on_the_matcher_afterwards_is_the_key_it_orders_by(self):
        matcher = match.is_sorted()
        matcher.key = operator.neg
        assert_that(matcher.matches([1, 2, 3, 4, 5])).is_false()

    def test_a_nan_among_floats_still_breaks_the_order(self):
        with pytest.raises(AssertionFailure):
            assert_that([1.0, 2.0, math.nan, 3.0, 4.0]).is_sorted()

    def test_a_key_of_ones_own_is_still_asked_only_up_to_the_break(self):
        asked = []

        def key(item):
            asked.append(item)
            return item

        with pytest.raises(AssertionFailure):
            assert_that([1, 3, 2, 4, 5, 6]).is_sorted(key=key)
        assert_that(asked).is_equal_to([1, 3, 2])

    def test_the_matcher_takes_the_same_pass(self):
        assert_that(match.is_sorted().evaluate([1, 2, 4, 3, 5, 6]).mismatch).is_equal_to(
            "was <[1, 2, 4, 3, 5, 6]>, out of order at index 2: <4> then <3>"
        )
        assert_that(list(range(6))).satisfies(match.is_sorted())


class _Scaled(list):
    """Items read through `__getitem__` scaled tenfold, while `list.__eq__` compares the stored ones."""

    def __getitem__(self, index):
        return list.__getitem__(self, index) * 10


class _Unread(list):
    """Refuses every read by index, which `list.__eq__` never makes."""

    def __getitem__(self, index):
        raise RuntimeError("no reads")


class _UnreadTuple(tuple):
    def __getitem__(self, index):
        raise RuntimeError("no reads")


class _StopsIndexing(list):
    """Ends every read by index with `StopIteration`, which a `map` over the reads would take for the end."""

    def __getitem__(self, index):
        raise StopIteration


class _StopsIndexingTuple(tuple):
    def __getitem__(self, index):
        raise StopIteration


class _UnreadDelegating(_Unread):
    """An `__eq__` of its own that hands the question to the base, which reads the storage."""

    def __eq__(self, other):
        return list.__eq__(self, other)

    __hash__ = None


class _PosingList:
    """Claims to be a list through `__class__` and refuses to be sized: it has no storage to stand in."""

    __class__ = property(lambda self: list)

    def __len__(self):
        raise RuntimeError("no length")


class _Traced(list):
    """Records every read the walk makes of it."""

    def __init__(self, items):
        super().__init__(items)
        self.reads = []

    def __len__(self):
        self.reads.append("len")
        return list.__len__(self)

    def __getitem__(self, index):
        self.reads.append(index)
        return list.__getitem__(self, index)

    def __iter__(self):
        self.reads.append("iter")
        return list.__iter__(self)


class _Unsized(list):
    def __len__(self):
        raise RuntimeError("no length")


class _IteratesOnce(list):
    """Hands out its first item by iteration and refuses the next."""

    def __iter__(self):
        yield list.__getitem__(self, 0)
        raise RuntimeError("iterated once")


class _PosingSequence:
    """A list by `__class__` only, with a length, reads by index, and an iteration it refuses."""

    __class__ = property(lambda self: list)

    def __len__(self):
        return 3

    def __getitem__(self, index):
        if index >= 3:
            raise IndexError(index)
        return index

    def __iter__(self):
        raise RuntimeError("no iteration")


class _PosingStopped(_PosingSequence):
    """Thirty items long, so the message walks it, and ends its iteration before it starts."""

    def __len__(self):
        return 30

    def __iter__(self):
        raise StopIteration


class _Uniterable(list):
    def __iter__(self):
        raise RuntimeError("no iteration")


class _ThirtyNext:
    """Thirty items by `next()`, and an `__iter__` of its own that stops, which nothing walking it asks."""

    def __init__(self, failing_at=None):
        self.position = 0
        self.failing_at = failing_at

    def __iter__(self):
        raise StopIteration

    def __next__(self):
        if self.position == self.failing_at:
            raise RuntimeError("broke off")
        if self.position == 30:
            raise StopIteration
        self.position += 1
        return self.position - 1


class _PosingThirty(_PosingSequence):
    failing_at = None

    def __len__(self):
        return 30

    def __getitem__(self, index):
        if index >= 30:
            raise IndexError(index)
        return index

    def __iter__(self):
        return _ThirtyNext(self.failing_at)


class _PosingBreakingOff(_PosingThirty):
    failing_at = 1


class _PosingUnindexed(_PosingSequence):
    def __getitem__(self, index):
        raise RuntimeError("no reads")


class _ScaledSet(set):
    """Iterates ten times what it stores, which `set.__eq__` never asks."""

    def __iter__(self):
        return (item * 10 for item in set.__iter__(self))


class _UnreadSet(set):
    """Refuses its own iteration, which `set.__eq__` never makes."""

    def __iter__(self):
        raise RuntimeError("no items")


class _UnreadFrozenset(frozenset):
    def __iter__(self):
        raise RuntimeError("no items")


class _StoppedSet(set):
    def __iter__(self):
        raise StopIteration


class _UnaskedSet(set):
    """Refuses its own lookup, which `set.__eq__` never makes."""

    def __contains__(self, item):
        raise RuntimeError("no lookups")


class _BreaksOffSet(set):
    """Gives the first item it stores, then refuses."""

    def __iter__(self):
        yield from itertools.islice(set.__iter__(self), 1)
        raise RuntimeError("no more items")


class _Rehashed:
    """Hashes once, when stored; asked again, it refuses."""

    def __init__(self):
        self.hashed = False

    def __hash__(self):
        if self.hashed:
            raise RuntimeError("hashed again")
        self.hashed = True
        return 2


class _TracedSet(set):
    def __init__(self, items):
        super().__init__(items)
        self.reads = []

    def __iter__(self):
        self.reads.append("iter")
        return set.__iter__(self)

    def __contains__(self, item):
        self.reads.append(item)
        return set.__contains__(self, item)


class _Walks:
    """Counts how often it is walked."""

    def __init__(self, items):
        self.items = items
        self.walks = 0

    def __iter__(self):
        self.walks += 1
        return iter(self.items)


def _diff_of(actual, expected):
    with pytest.raises(AssertionFailure) as caught:
        assert_that(actual).is_equal_to(expected)
    return [(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]


class TestADiffReadsASequenceTheVerdictCouldRead:
    """A read the verdict never made may not refuse the failure; a read that answers is kept as it was.

    Accepted with it: on a failure, a `list` or `tuple` subclass is read once more before the walk, to learn whether
    its reads answer.
    """

    def test_reads_that_answer_are_the_reads_the_diff_shows(self):
        assert_that(_diff_of(_Scaled([1, 2]), [10, 30])).is_equal_to([("[1]", 20, 30)])

    def test_reads_that_answer_are_the_reads_the_message_shows(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_Scaled(range(21))).is_equal_to([999] * 21)
        assert_that(str(caught.value)).starts_with("Expected <[0, 1, 2, 3, 4, ... and 16 more]>")

    @pytest.mark.parametrize(
        "unread",
        [
            _Unread([1, 2]),
            _UnreadTuple((1, 2)),
            _UnreadDelegating([1, 2]),
            _StopsIndexing([1, 2]),
            _StopsIndexingTuple((1, 2)),
        ],
        ids=["list", "tuple", "equality-handed-to-the-base", "stop-iteration", "stop-iteration-tuple"],
    )
    def test_reads_that_refuse_leave_the_stored_items(self, unread):
        expected = (1, 3) if isinstance(unread, tuple) else [1, 3]
        assert_that(_diff_of(unread, expected)).is_equal_to([("[1]", 2, 3)])

    def test_the_message_elides_what_the_stored_items_share(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(["x" * 70, 1]).is_equal_to(_Unread(["x" * 70, 2]))
        assert_that(str(caught.value)).starts_with("Expected <[.., 1]> to be equal to <[.., 2]>")

    def test_reads_that_answer_are_made_as_the_walk_always_made_them(self):
        traced = _Traced([1, 2, 3])
        _diff_of(traced, [1, 2, 4])
        assert_that(traced.reads).is_equal_to(["len", "len", "len", "len", 0, "len", 1, "len", 2, 2])

    def test_a_length_that_refuses_leaves_the_stored_items(self):
        assert_that(_diff_of(_Unsized([1, 2]), [1, 3])).is_equal_to([("[1]", 2, 3)])

    def test_an_iteration_that_refuses_part_way_is_finished_from_the_storage(self):
        items = [*range(29), 99]
        with pytest.raises(AssertionFailure) as plain:
            assert_that(list(range(30))).is_equal_to(items)
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_IteratesOnce(range(30))).is_equal_to(items)
        assert_that(str(caught.value)).is_equal_to(str(plain.value))

    @pytest.mark.parametrize(
        ("posing", "refusal"),
        [(_PosingUnindexed, "no reads"), (_PosingSequence, "no iteration")],
        ids=["index", "iteration"],
    )
    def test_a_value_posing_as_a_list_keeps_a_refusal_of_its_reads(self, posing, refusal):
        with pytest.raises(RuntimeError, match=refusal):
            assert_that([7]).is_equal_to(posing())

    def test_a_value_posing_as_a_list_keeps_the_stop_its_iteration_raised(self):
        with pytest.raises(StopIteration):
            assert_that(_PosingStopped()).is_equal_to([0] * 30)

    def test_an_iteration_refused_outright_is_answered_from_the_storage(self):
        items = [*range(29), 99]
        with pytest.raises(AssertionFailure) as plain:
            assert_that(list(range(30))).is_equal_to(items)
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_Uniterable(range(30))).is_equal_to(items)
        assert_that(str(caught.value)).is_equal_to(str(plain.value))

    def test_an_iterator_is_walked_by_next_alone(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_PosingThirty()).is_equal_to([*range(29), 99])
        assert_that(str(caught.value)).contains("to be equal to <[.., 99]>")


class TestADiffReadsASetTheVerdictCouldRead:
    """`==` of two sets compares what they store; the diff reads a set's own iteration and lookup while they answer,
    and its storage from the first that refuses."""

    def test_reads_that_answer_are_the_reads_the_diff_shows(self):
        diff = _diff_of(_ScaledSet({1, 2}), {10, 30})
        assert_that(diff).is_equal_to([("extra", 20, None), ("missing", None, 10), ("missing", None, 30)])

    @pytest.mark.parametrize(
        "unread",
        [_UnreadSet({1, 2}), _UnreadFrozenset({1, 2}), _StoppedSet({1, 2}), _UnaskedSet({1, 2})],
        ids=["iteration", "frozenset-iteration", "stop-iteration", "lookup"],
    )
    def test_reads_that_refuse_leave_the_stored_items(self, unread):
        assert_that(_diff_of(unread, {1, 3})).is_equal_to([("extra", 2, None), ("missing", None, 3)])
        assert_that(_diff_of({1, 3}, unread)).is_equal_to([("extra", 3, None), ("missing", None, 2)])

    def test_an_iteration_that_refuses_part_way_is_finished_from_the_storage(self):
        diff = _diff_of(_BreaksOffSet(range(30)), {*range(1, 30), 99})
        assert_that(diff).is_equal_to([("extra", 0, None), ("missing", None, 99)])

    @pytest.mark.parametrize("kind", [_UnaskedSet, _UnreadFrozenset], ids=["set", "frozenset"])
    def test_the_storage_is_read_with_the_hashes_it_holds(self, kind):
        stored = _stored_members(kind([_Rehashed()]))
        assert_that(type(stored)).is_same_as(kind.__mro__[1])
        assert_that(stored).is_length(1)

    def test_reads_that_answer_are_made_as_the_walk_always_made_them(self):
        rendered = _TracedSet({1, 2})
        repr(rendered)
        traced = _TracedSet({1, 2})
        _diff_of(traced, {1, 3})
        assert_that(traced.reads).is_equal_to([*rendered.reads, "iter", 1, 3])

    def test_a_value_posing_as_a_list_keeps_a_refusal_part_way_through_its_iteration(self):
        with pytest.raises(RuntimeError, match="broke off"):
            assert_that(_PosingBreakingOff()).is_equal_to([*range(29), 99])

    def test_a_value_only_posing_as_a_list_keeps_its_own_refusal(self):
        with pytest.raises(RuntimeError, match="no length"):
            assert_that([1]).is_equal_to(_PosingList())


class TestAnySatisfyWalksTheValueOnce:
    def test_the_message_walks_the_value_no_more_than_the_verdict_did(self):
        passing, failing = _Walks([1, 2, 9]), _Walks([1, 2, 3])
        assert_that(passing).any_satisfy(lambda item: item > 5)
        with pytest.raises(AssertionFailure) as caught:
            assert_that(failing).any_satisfy(lambda item: item > 5)
        assert_that(failing.walks).is_equal_to(passing.walks)
        assert_that(str(caught.value)).contains("but none of the 3 did")

    def test_an_iterator_is_counted_whole(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(iter([1, 2, 3])).any_satisfy(lambda item: item > 5)
        assert_that(str(caught.value)).contains("but none of the 3 did")
