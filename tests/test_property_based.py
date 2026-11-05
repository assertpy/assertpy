"""Property-based tests (Hypothesis) for the riskiest pure-logic surfaces.

These complement the example-based suite: 100% line coverage does not exercise the *space* of
values, which is where recursive equality, ignore/include filtering, and matcher algebra hide bugs.
Each test states an invariant and lets Hypothesis attack it with generated data; on failure the
shrunk counterexample plus assertpy's structured ``AssertionFailure`` pinpoint the mismatch.
"""

import ast
import contextlib
import copy
import datetime
import decimal
import fractions
import functools
import itertools
import json
import operator
import pathlib
import re
import sys
import typing
from collections import Counter, namedtuple
from collections.abc import Callable, Hashable, Iterable, Mapping, Sized
from dataclasses import dataclass, replace
from itertools import pairwise
from types import MappingProxyType, SimpleNamespace, UnionType

import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

import assertpy._engine._typing
import assertpy.assertpy
from assertpy import assert_conforms, assert_that, match, soft_assertions
from assertpy._clustering import _VALUE_LIMIT, Observation, Signature, _shown, clusters, render, stable_repr
from assertpy._dangling import findings as dangling_findings
from assertpy._engine._compare import _EQ_ATOMIC, _within_tolerance, plainly_within
from assertpy._engine._contract import UncheckableDriftError, contract_drift, shape, shape_diff
from assertpy._engine._diff import _build_equality_diff, _ordered_keys, _sub_diff_entries
from assertpy._engine._equality import values_differ
from assertpy._engine._introspection import is_mapping_like
from assertpy._engine._membership import missing_items
from assertpy._engine._ordering import compare, holds
from assertpy._engine._path import _ROOT
from assertpy._engine._require import refuse
from assertpy._engine._size import length_of
from assertpy._engine._text import contains as text_contains
from assertpy._engine._text import ends_with as text_ends_with
from assertpy._engine._text import starts_with as text_starts_with
from assertpy._hints import diagnose
from assertpy._inline import _format_literal, is_literalable
from assertpy._snapshot_codec import _decode, _encode
from assertpy.assertpy import _format_soft_errors
from assertpy.errors import AssertionFailure, DiffEntry, DiffResult, _diff_sides, _disambiguated, _json_safe
from assertpy.exception import _matches_shape
from assertpy.outcome import AssertionOutcome
from assertpy.pytest_plugin import _format_diff
from tests.group_compat import BaseExceptionGroup, ExceptionGroup, needs_groups

try:
    import jsonschema  # noqa: F401  # presence gate only

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover - exercised only in an env without the extra
    _HAS_JSONSCHEMA = False

# JSON-like values: atoms plus nested lists/dicts. NaN is out of `_values` because reflexivity is not
# true of it, which is a property of `==` rather than of this library
_atoms = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
_values = st.recursive(
    _atoms,
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)
_NAN = float("nan")
"""The shared object the pinned examples below use, because the container case turns on identity:
`[x] == [x]` is true for the same `x` even when `x == x` is false, which is the shortcut
`PyObject_RichCompareBool` applies per element.  The strategy builds fresh ones instead, so that
`[nan] == [nan]` over two allocations, which is false, stays reachable."""

_values_with_nan = st.recursive(
    _atoms | st.builds(float, st.just("nan")),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=20,
)
_keys = st.text(min_size=1, max_size=5)


class _Unreprable:
    def __repr__(self):
        raise RuntimeError("no repr")


class _Refusing:
    """A `repr` of its own, so Hypothesis's printer never calls the refusing method while it reports an example."""

    def __repr__(self):
        return f"{type(self).__name__}()"


class _RefusingDict(_Refusing, dict):
    def items(self):
        raise RuntimeError("no items")


class _RefusingList(_Refusing, list):
    def __getitem__(self, index):
        raise RuntimeError("no items")


class _RefusingSet(_Refusing, set):
    def __iter__(self):
        raise RuntimeError("no items")


class _RefusingStr(_Refusing, str):
    def __len__(self):
        raise RuntimeError("no length")


_carried = st.recursive(
    _atoms
    | st.floats()
    | st.binary()
    | st.datetimes()
    | st.integers(min_value=10**4300, max_value=10**4400)
    | st.builds(_Unreprable)
    | st.builds(_RefusingDict, st.dictionaries(st.text(), st.integers()))
    | st.builds(_RefusingList, st.lists(st.integers()))
    | st.builds(_RefusingSet, st.sets(st.integers()))
    | st.builds(_RefusingStr, st.text()),
    lambda children: (
        st.lists(children)
        | st.tuples(children, children)
        | st.dictionaries(st.text() | st.integers(), children)
        | st.frozensets(st.integers() | st.text())
    ),
    max_leaves=20,
)
"""What a failure can carry into an attachment: JSON atoms, values JSON cannot spell, and subclasses whose own
methods raise."""


@settings(deadline=None)
@example(value=10**5000)
@example(value={"nested": [10**5000]})
@example(value=_RefusingDict(a=1))
@example(value=_RefusingList([1]))
@example(value=_RefusingSet({1}))
@example(value=_RefusingStr("text"))
@given(value=_carried)
def test_an_attachment_value_always_serialises_and_costs_only_itself(value):
    """A value `json.dumps` refuses costs the whole attachment, because the plugin's barrier swallows the error.

    Held between two siblings, so a conversion that gave up on the whole structure would show.
    """
    converted = _json_safe(["before", value, "after"])
    assert_that(json.dumps(converted, allow_nan=False)).is_instance_of(str)
    assert_that(converted).is_length(3)
    assert_that([converted[0], converted[2]]).is_equal_to(["before", "after"])


@settings(deadline=None)
@given(value=_values)
def test_is_equal_to_is_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(left=_values, right=_values)
def test_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
# both pinned: a generated pair is not guaranteed to be the two cases that carry the story, and each
# answers differently. `nan != nan` outright, while `[nan] == [nan]` holds through the identity
# shortcut CPython applies inside a container
@example(left=_NAN, right=_NAN)
@example(left=[_NAN], right=[_NAN])
@given(left=_values_with_nan, right=_values_with_nan)
def test_is_equal_to_consistent_with_eq_over_nan(left, right):
    """The half of the NaN story that is testable: reflexivity is not, agreement with `==` is.

    `nan != nan`, so a bare one fails, while `[nan] == [nan]` holds through the identity shortcut
    CPython applies inside a container. Both are what `==` answers, and this asserts the library
    answers the same rather than deciding for itself.
    """
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(left=_values, right=_values)
def test_is_not_equal_to_is_the_inverse(left, right):
    if left != right:
        assert_that(left).is_not_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_not_equal_to(right)


class _CaseInsensitive(str):
    """Replaces `__eq__` alone and so keeps `str.__ne__`, which then disagrees with it on "A" against "a"."""

    def __eq__(self, other):
        return isinstance(other, str) and self.casefold() == other.casefold()

    def __hash__(self):
        return hash(self.casefold())


_cased_atoms = st.one_of(
    st.sampled_from(["a", "A", "b"]), st.builds(_CaseInsensitive, st.sampled_from(["a", "A", "b"]))
)
_cased_values = st.one_of(
    _cased_atoms,
    st.lists(_cased_atoms, max_size=3),
    st.dictionaries(st.sampled_from(["id", "name"]), _cased_atoms, max_size=2),
)


@settings(deadline=None)
@example(left=_CaseInsensitive("A"), right="a")
@example(left="a", right=_CaseInsensitive("A"))
@given(left=_cased_values, right=_cased_values)
def test_every_spelling_of_equality_answers_what_eq_answers(left, right):
    """`==` decides, whichever spelling asks, however the value is nested, and whatever `!=` would say."""
    equal = bool(left == right)
    assert_that(assert_that(left).check().is_equal_to(right).passed).is_equal_to(equal)
    assert_that(assert_that(left).check().is_not_equal_to(right).passed).is_equal_to(not equal)
    assert_that(assert_that(left).check().is_equal_to(right, tolerance=0.1).passed).is_equal_to(equal)
    assert_that(match.equal_to(right).matches(left)).is_equal_to(equal)
    assert_that(match.equal_to(right, tolerance=0.1).matches(left)).is_equal_to(equal)


@given(left=st.sets(st.integers()), right=st.sets(st.integers()))
def test_is_equal_to_consistent_with_eq_for_sets(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(base=st.dictionaries(_keys, _atoms, max_size=6), perturbations=st.dictionaries(_keys, _atoms, max_size=4))
def test_ignore_removes_differences(base, perturbations):
    left = dict(base)
    right = {**base, **perturbations}
    assert_that(left).is_equal_to(right, ignore=list(perturbations))


@settings(deadline=None)
@given(
    common=st.dictionaries(_keys, _atoms, min_size=1, max_size=4),
    left_extra=st.dictionaries(_keys, _atoms, max_size=3),
    right_extra=st.dictionaries(_keys, _atoms, max_size=3),
)
def test_include_compares_only_listed_keys(common, left_extra, right_extra):
    included = list(common)
    left = {**{k: v for k, v in left_extra.items() if k not in common}, **common}
    right = {**{k: v for k, v in right_extra.items() if k not in common}, **common}
    assert_that(left).is_equal_to(right, include=included)


@given(value=st.integers(), low=st.integers(), high=st.integers())
def test_between_matcher_matches_python_semantics(value, low, high):
    """Over a range the matcher accepts: swapped bounds are refused at construction, as the builder refuses them."""
    low, high = sorted((low, high))
    assert match.between(low, high).matches(value) == (low <= value <= high)


@given(value=st.integers(), boundary=st.integers())
def test_greater_than_matcher_matches_python_semantics(value, boundary):
    assert match.greater_than(boundary).matches(value) == (value > boundary)


@given(value=st.integers(), low=st.integers(), high=st.integers())
def test_satisfies_between_consistent_with_semantics(value, low, high):
    low, high = sorted((low, high))
    if low <= value <= high:
        assert_that(value).satisfies(match.between(low, high))
    else:
        with pytest.raises(AssertionError):
            assert_that(value).satisfies(match.between(low, high))


@given(value=st.integers(), boundary_low=st.integers(), boundary_high=st.integers())
def test_matcher_combinators_follow_boolean_logic(value, boundary_low, boundary_high):
    matcher_a = match.greater_than(boundary_low)
    matcher_b = match.less_than(boundary_high)
    result_a = matcher_a.matches(value)
    result_b = matcher_b.matches(value)

    assert (matcher_a & matcher_b).matches(value) == (result_a and result_b)
    assert (matcher_a | matcher_b).matches(value) == (result_a or result_b)
    assert (~matcher_a).matches(value) == (not result_a)
    assert (~(matcher_a & matcher_b)).matches(value) == ((~matcher_a) | (~matcher_b)).matches(value)


@given(items=st.lists(st.integers()))
def test_is_length_matches_len(items):
    assert_that(items).is_length(len(items))


@given(items=st.lists(st.integers(), min_size=1))
def test_contains_every_element(items):
    assert_that(items).contains(*items)


class _SharedIterator:
    """Answers `iter(self) is self` with False and still has one position, which is the recorded gap."""

    def __init__(self, items):
        self.walker = iter(items)

    def __iter__(self):
        return self.walker


def _reported(subject, wanted) -> str | None:
    """The first line of the failure `contains()` raises over *subject*, or `None` when it held."""
    try:
        assert_that(subject).contains(wanted)
    except AssertionError as error:
        return str(error).splitlines()[0]
    return None


_ONE_SHOT = [
    lambda items: iter(items),
    lambda items: (item for item in items),
    lambda items: map(int, items),
    lambda items: filter(lambda item: True, items),
]


@given(items=st.lists(st.integers(), max_size=8), wanted=st.integers(), which=st.sampled_from(range(len(_ONE_SHOT))))
def test_a_one_shot_subject_reports_what_a_list_of_the_same_items_does(items, wanted, which):
    """A value consumed by the first pass must not report less than a re-iterable one holding the same.

    `materialized()` drains anything that is its own iterator, so the walk that decides and the walk
    that describes see the same items.  Without it the second pass finds nothing and the message names
    an empty value, which is the wrong contents rather than a wrong verdict.
    """
    assert_that(_reported(_ONE_SHOT[which](items), wanted)).is_equal_to(_reported(list(items), wanted))


def test_a_wrapper_over_one_shared_iterator_is_the_recorded_exception():
    """The other side of the same boundary, pinned because it is deliberate rather than missed.

    Being its own iterator is not the only way to have one position.  A wrapper handing out a shared
    one answers `iter(x) is x` with False, so `materialized()` leaves it alone and the message falls
    back to its `repr`.  Copying anything that merely lacks a length instead would turn a Pydantic
    model into a list of its field pairs, which is why this is left as it is.

    The address inside that `repr` is not asserted: it moves between runs.
    """
    reported = _reported(_SharedIterator([1, 2, 3]), 9)
    assert_that(reported).contains("_SharedIterator object at")
    assert_that(reported).does_not_contain("[1, 2, 3]")


@given(items=st.lists(st.integers()), candidate=st.integers())
def test_contains_present_iff_member(items, candidate):
    if candidate in items:
        assert_that(items).contains(candidate)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).contains(candidate)


@dataclass
class _Inner:
    a: int
    b: str


@dataclass
class _Outer:
    inner: _Inner
    items: list[int]
    name: str


@dataclass
class _InnerTwin:
    a: int
    b: str


@dataclass
class _Holding:
    held: object
    other: int = 0


_Pair = namedtuple("_Pair", ["first", "second"])

_inners = st.builds(_Inner, a=st.integers(), b=st.text(max_size=5))
_outers = st.builds(_Outer, inner=_inners, items=st.lists(st.integers(), max_size=4), name=st.text(max_size=5))
_pairs = st.builds(_Pair, first=st.integers(), second=st.text(max_size=5))


@settings(deadline=None)
@given(left=_outers, right=_outers)
def test_dataclass_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@settings(deadline=None)
@given(value=_outers)
def test_dataclass_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(value=_outers, new_name=st.text(max_size=5))
def test_dataclass_ignore_removes_field_difference(value, new_name):
    other = replace(value, name=new_name)
    assert_that(value).is_equal_to(other, ignore="name")


@given(left=_pairs, right=_pairs)
def test_namedtuple_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to(right)


@given(value=_pairs)
def test_namedtuple_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(left=_values, right=_values)
def test_diff_is_well_formed_for_unequal_values(left, right):
    if left == right:
        return
    with pytest.raises(AssertionFailure) as exc_info:
        assert_that(left).is_equal_to(right)
    failure = exc_info.value
    assert isinstance(str(failure), str)
    diff = failure.diff
    if diff is not None:
        assert isinstance(diff.kind, str)
        assert all(isinstance(entry.path, str) for entry in diff.entries)
        assert isinstance(_format_diff(diff, color=True), str)


@settings(deadline=None)
@given(left=_outers, right=_outers)
def test_diff_is_well_formed_for_unequal_dataclasses(left, right):
    if left == right:
        return
    with pytest.raises(AssertionFailure) as exc_info:
        assert_that(left).is_equal_to(right)
    diff = exc_info.value.diff
    if diff is not None:
        assert all(isinstance(entry.path, str) for entry in diff.entries)
        assert isinstance(_format_diff(diff, color=True), str)


# a pair the pairing calls equal is never examined, so a wrong match hides a real difference.
# Two defects of that shape shipped, both because difflib matched on something other than the verdict


class _Twin:
    """Unhashable and printed the same whatever it holds, so an alignment can only key on the repr."""

    __hash__ = None

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, _Twin) and self.value == other.value

    def __repr__(self):
        return "<twin>"


class _Split:
    """Hashable, with ``==`` and ``!=`` that disagree: difflib and the walk read the first, nothing the second."""

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return 7

    def __eq__(self, other):
        return isinstance(other, _Split)

    def __ne__(self, other):
        return not isinstance(other, _Split) or self.value != other.value

    def __repr__(self):
        return f"_Split({self.value})"


_drift_atoms = st.one_of(
    st.integers(min_value=-2, max_value=2),
    st.sampled_from([0.0, 1.0, 2.0, True, False, None, "", "a", "b"]),
    st.builds(float, st.just("nan")),
    st.builds(_Twin, st.integers(min_value=0, max_value=2)),
    st.builds(_Split, st.integers(min_value=0, max_value=2)),
    st.lists(st.integers(min_value=0, max_value=2), max_size=2),
    st.dictionaries(st.sampled_from(["id", "name"]), st.integers(min_value=0, max_value=2), max_size=2),
)


@st.composite
def _drifted_pair(draw):
    """Two sequences sharing a run, which is the only shape that reaches the alignment at all.

    Pairing by index is used whenever the two are the same length, so a strategy drawing both sides
    independently spends most of its examples never touching the code under test.  Here one side is
    the other with a run inserted and a few positions rewritten, which is what a shifted payload looks
    like and what makes a matched run long enough for a wrong match inside it to hide something.

    Drawing every element from one small pool is load-bearing rather than a way to get repeats.  A dict
    lookup settles identity before it asks ``==``, so difflib matches a pair like ``nan`` against ``nan``
    only when both sides hold the same object - and that pair, matched and then never compared, is the
    whole failure this is looking for.  Redraw the elements per side and the case stops being generated.
    """
    element = st.sampled_from(draw(st.lists(_drift_atoms, min_size=1, max_size=3)))
    base = draw(st.lists(element, min_size=1, max_size=6))
    cut = draw(st.integers(min_value=0, max_value=len(base)))
    expected = [*base[:cut], *draw(st.lists(element, max_size=3)), *base[cut:]]
    for index in draw(st.lists(st.integers(min_value=0, max_value=len(expected) - 1), max_size=2)):
        expected[index] = draw(element)
    return (expected, base) if draw(st.booleans()) else (base, expected)


_pairs_of_sequences = st.one_of(
    st.tuples(st.lists(_drift_atoms, max_size=6), st.lists(_drift_atoms, max_size=6)),
    _drifted_pair(),
)


def _sequence_diff_of(actual, expected):
    """The sequence diff of a failing pair, or ``None`` when there is nothing of that shape to read."""
    try:
        assert_that(actual).is_equal_to(expected)
    except AssertionFailure as failure:
        diff = failure.diff
    else:
        return None
    return diff if diff is not None and diff.kind == "sequence" else None


def _edits(entries):
    """Which actual indices the diff dropped, which expected indices it added, and which it named.

    Only a one-step entry can be one-sided about the sequence itself: deeper down, ``absent`` belongs
    to the nested key or index it names, and the position above it was compared like any other.
    """
    dropped, added, named = set(), set(), set()
    for entry in entries:
        assert entry.steps, "a sequence entry has to say where it sits"
        step = entry.steps[0]
        assert step.kind == "index"
        if len(entry.steps) == 1 and entry.absent == "expected":
            dropped.add(step.value)
        elif len(entry.steps) == 1 and entry.absent == "actual":
            added.add(step.value)
        else:
            named.add(step.value)
    return dropped, added, named


@settings(deadline=None)
@given(pair=_pairs_of_sequences)
def test_a_sequence_diff_pairs_off_every_position_it_leaves_unnamed(pair):
    actual, expected = pair
    diff = _sequence_diff_of(actual, expected)
    if diff is None:
        return
    dropped, added, named = _edits(diff.entries)
    kept_actual = [index for index in range(len(actual)) if index not in dropped]
    kept_expected = [index for index in range(len(expected)) if index not in added]
    assert len(kept_actual) == len(kept_expected)
    unaccounted = [
        (left, right)
        for left, right in zip(kept_actual, kept_expected, strict=True)
        # identity is equality here, which is the rule a container's own `==` applies to its members
        if left not in named and actual[left] is not expected[right] and not bool(actual[left] == expected[right])
    ]
    assert unaccounted == []


@settings(deadline=None)
@given(pair=_pairs_of_sequences)
def test_a_one_sided_sequence_entry_carries_the_element_it_names(pair):
    actual, expected = pair
    diff = _sequence_diff_of(actual, expected)
    if diff is None:
        return
    for entry in diff.entries:
        if len(entry.steps) != 1 or entry.absent is None:
            continue
        index = entry.steps[0].value
        if entry.absent == "expected":
            assert entry.actual is actual[index]
            assert entry.expected is None
        else:
            assert entry.expected is expected[index]
            assert entry.actual is None


def _is_subsequence(sub, seq):
    iterator = iter(seq)
    return all(any(candidate == element for candidate in iterator) for element in sub)


@given(val=st.lists(st.integers(), max_size=6), expected=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_exactly_matches_list_equality(val, expected):
    if val == expected:
        assert_that(val).contains_exactly(*expected)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_exactly(*expected)


@given(val=st.lists(st.integers(), max_size=6), items=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_only_matches_set_equality(val, items):
    if set(val) == set(items):
        assert_that(val).contains_only(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_only(*items)


@given(val=st.lists(st.integers(), max_size=8), items=st.lists(st.integers(), min_size=1, max_size=4))
def test_contains_sequence_matches_contiguous_slice(val, items):
    window = len(items)
    is_contiguous = any(val[index : index + window] == items for index in range(len(val) - window + 1))
    if is_contiguous:
        assert_that(val).contains_sequence(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_sequence(*items)


@given(val=st.lists(st.integers(), max_size=8), items=st.lists(st.integers(), min_size=1, max_size=4))
def test_contains_in_order_matches_subsequence(val, items):
    if _is_subsequence(items, val):
        assert_that(val).contains_in_order(*items)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_in_order(*items)


@given(items=st.lists(st.integers(), max_size=10))
def test_does_not_contain_duplicates_iff_unique(items):
    if len(items) == len(set(items)):
        assert_that(items).does_not_contain_duplicates()
    else:
        with pytest.raises(AssertionError):
            assert_that(items).does_not_contain_duplicates()


@given(items=st.lists(st.integers(), max_size=10))
def test_is_sorted_matches_python_sorted(items):
    if items == sorted(items):
        assert_that(items).is_sorted()
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_sorted()


@given(items=st.lists(st.integers(), max_size=10))
def test_is_sorted_reverse_matches_python_sorted(items):
    if items == sorted(items, reverse=True):
        assert_that(items).is_sorted(reverse=True)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_sorted(reverse=True)


@given(items=st.lists(st.integers(), max_size=8), superset=st.lists(st.integers(), max_size=10))
def test_is_subset_of_matches_set_subset(items, superset):
    if set(items) <= set(superset):
        assert_that(items).is_subset_of(superset)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_subset_of(superset)


@settings(deadline=None)
@given(
    items=st.dictionaries(st.sampled_from("abcd"), st.integers(0, 3), max_size=3),
    supersets=st.lists(st.dictionaries(st.sampled_from("abcd"), st.integers(0, 3), max_size=3), min_size=2, max_size=3),
    data=st.data(),
)
def test_is_subset_of_reads_the_same_whatever_order_the_supersets_arrive_in(items, supersets, data):
    """Several supersets are one question, so the answer cannot follow the order they were written in.

    They were merged into one mapping once, where a later key overwrote an earlier one and the verdict
    moved with the argument order.
    """
    shuffled = data.draw(st.permutations(supersets))
    first = _holds(lambda: assert_that(items).is_subset_of(*supersets))
    again = _holds(lambda: assert_that(items).is_subset_of(*shuffled))
    assert_that(first).described_as(f"is_subset_of{tuple(supersets)} against {tuple(shuffled)}").is_equal_to(again)


_BROKEN = [object(), type("NoOrder", (), {})(), float("nan")]


@settings(deadline=None)
@given(
    value=st.sampled_from(_BROKEN),
    call=st.sampled_from(
        [
            ("is_less_than", (1,)),
            ("is_greater_than", (1,)),
            ("is_between", (0, 1)),
            ("contains", ("a",)),
            ("is_length", (1,)),
            ("starts_with", ("a",)),
            ("has_size_greater_than", (1,)),
            ("is_close_to", (1, 1)),
        ]
    ),
)
def test_not_does_not_turn_a_foreign_error_into_a_passing_negation(value, call):
    """`not_` inverts a verdict, never an error: what the value cannot answer it cannot answer negated.

    An assertion catching `Exception` too widely would report the negation as held, which reads as a
    checked fact about a value the library never managed to examine.
    """
    name, arguments = call
    positive = _ordering_answer(lambda: getattr(assert_that(value), name)(*arguments))
    if positive != "refused":
        return
    negated = _ordering_answer(lambda: getattr(assert_that(value).not_, name)(*arguments))
    assert_that(negated).described_as(f"not_.{name}{arguments} on {value!r}").is_equal_to("refused")


@given(val=st.lists(st.integers(), max_size=6), expected=st.lists(st.integers(), min_size=1, max_size=6))
def test_contains_exactly_in_any_order_matches_multiset_equality(val, expected):
    if Counter(val) == Counter(expected):
        assert_that(val).contains_exactly_in_any_order(*expected)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).contains_exactly_in_any_order(*expected)


@given(items=st.lists(st.integers(), min_size=1, max_size=6), data=st.data())
def test_contains_exactly_in_any_order_is_permutation_invariant(items, data):
    shuffled = data.draw(st.permutations(items))
    assert_that(items).contains_exactly_in_any_order(*shuffled)


@given(items=st.lists(st.lists(st.integers(), max_size=3), min_size=1, max_size=5), data=st.data())
def test_contains_exactly_in_any_order_unhashable_permutation_invariant(items, data):
    # lists as items force the quadratic non-Counter fallback
    shuffled = data.draw(st.permutations(items))
    assert_that(items).contains_exactly_in_any_order(*shuffled)


# with pure equality matchers a perfect pairing exists iff the multisets are equal, so Counter is an oracle


@given(val=st.lists(st.integers(0, 5), max_size=5), expected=st.lists(st.integers(0, 5), min_size=1, max_size=5))
def test_satisfies_exactly_in_any_order_equality_matchers_match_multisets(val, expected):
    matchers = [match.equal_to(item) for item in expected]
    if Counter(val) == Counter(expected):
        assert_that(val).satisfies_exactly_in_any_order(*matchers)
    else:
        with pytest.raises(AssertionError):
            assert_that(val).satisfies_exactly_in_any_order(*matchers)


@given(items=st.lists(st.integers(), min_size=1, max_size=5), data=st.data())
def test_satisfies_exactly_in_any_order_is_permutation_invariant(items, data):
    shuffled = data.draw(st.permutations(items))
    assert_that(items).satisfies_exactly_in_any_order(*[match.equal_to(item) for item in shuffled])


_bounds = st.tuples(st.integers(0, 10), st.integers(0, 10)).map(sorted)


@given(items=st.lists(st.integers(), max_size=10), size=st.integers(0, 10))
def test_has_size_greater_than_matches_len_semantics(items, size):
    if len(items) > size:
        assert_that(items).has_size_greater_than(size)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_greater_than(size)


@given(items=st.lists(st.integers(), max_size=10), size=st.integers(0, 10))
def test_has_size_less_than_matches_len_semantics(items, size):
    if len(items) < size:
        assert_that(items).has_size_less_than(size)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_less_than(size)


@given(items=st.lists(st.integers(), max_size=10), bounds=_bounds)
def test_has_size_between_matches_len_semantics(items, bounds):
    low, high = bounds
    if low <= len(items) <= high:
        assert_that(items).has_size_between(low, high)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).has_size_between(low, high)


@given(items=st.lists(st.integers(), max_size=10), bounds=_bounds)
def test_is_length_between_matches_len_semantics(items, bounds):
    low, high = bounds
    if low <= len(items) <= high:
        assert_that(items).is_length_between(low, high)
    else:
        with pytest.raises(AssertionError):
            assert_that(items).is_length_between(low, high)


_ascii_text = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126))


@given(text=st.text(), data=st.data())
def test_inserting_whitespace_keeps_ignoring_whitespace_equality(text, data):
    position = data.draw(st.integers(0, len(text)))
    whitespace = data.draw(st.sampled_from([" ", "\t", "\n", "  ", "\r\n"]))
    padded = text[:position] + whitespace + text[position:]
    assert_that(padded).is_equal_to_ignoring_whitespace(text)


@given(left=st.text(), right=st.text())
def test_is_equal_to_ignoring_whitespace_matches_normalization(left, right):
    if "".join(left.split()) == "".join(right.split()):
        assert_that(left).is_equal_to_ignoring_whitespace(right)
    else:
        with pytest.raises(AssertionError):
            assert_that(left).is_equal_to_ignoring_whitespace(right)


# ascii-only: for unicode `lower(swapcase(s))` may differ from `lower(s)`, which is a property of Python casing
@given(text=_ascii_text.filter(lambda s: len(s) >= 1), data=st.data())
def test_starts_with_ignoring_case_accepts_case_mangled_prefix(text, data):
    prefix_length = data.draw(st.integers(1, len(text)))
    assert_that(text).starts_with_ignoring_case(text[:prefix_length].swapcase())


@given(text=_ascii_text.filter(lambda s: len(s) >= 1), data=st.data())
def test_ends_with_ignoring_case_accepts_case_mangled_suffix(text, data):
    suffix_length = data.draw(st.integers(1, len(text)))
    assert_that(text).ends_with_ignoring_case(text[-suffix_length:].swapcase())


_snapshot_zones = st.sampled_from(
    [
        None,
        datetime.timezone.utc,
        datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
        datetime.timezone(datetime.timedelta(hours=-8)),
        datetime.timezone(datetime.timedelta(minutes=5, seconds=30)),
    ]
)
_snapshot_codec_values = (
    st.dates()
    | st.times(timezones=_snapshot_zones)
    | st.decimals(allow_nan=False)
    | st.binary(max_size=64)
    | st.datetimes(
        min_value=datetime.datetime(1900, 1, 1),
        max_value=datetime.datetime(9999, 12, 30),
        timezones=_snapshot_zones,
    )
)


@settings(deadline=None)
@given(value=_snapshot_codec_values)
def test_snapshot_codec_roundtrip(value):
    encoded = json.dumps(_encode({"v": value}))
    decoded = _decode(json.loads(encoded))
    assert_that(decoded["v"]).is_equal_to(value)


_two_level = st.dictionaries(
    st.text(min_size=1, max_size=3),
    st.dictionaries(st.text(min_size=1, max_size=3), st.integers(), max_size=3),
    max_size=3,
)


@settings(deadline=None)
@given(base=_two_level, data=st.data())
def test_nested_ignore_removes_leaf_differences(base, data):
    paths = [(outer, leaf) for outer, inner in base.items() for leaf in inner]
    perturbed = data.draw(st.lists(st.sampled_from(paths), unique=True)) if paths else []
    right = {outer: dict(inner) for outer, inner in base.items()}
    for outer, leaf in perturbed:
        right[outer][leaf] += 1000
    assert_that(base).is_equal_to(right, ignore=list(perturbed))


@settings(deadline=None)
@given(base=_two_level, data=st.data())
def test_nested_include_compares_only_listed_leaves(base, data):
    paths = [(outer, leaf) for outer, inner in base.items() for leaf in inner]
    if not paths:
        return
    included = data.draw(st.lists(st.sampled_from(paths), unique=True, min_size=1))
    included_set = set(included)
    right = {outer: dict(inner) for outer, inner in base.items()}
    for outer, leaf in paths:
        if (outer, leaf) not in included_set:
            right[outer][leaf] += 1000
    assert_that(base).is_equal_to(right, include=list(included))


_json_atoms = st.none() | st.booleans() | st.integers() | st.floats() | st.text()
_json = st.recursive(_json_atoms, lambda children: st.lists(children) | st.dictionaries(_keys, children), max_leaves=20)


def _canon(value):
    """Replace every scalar leaf with a fixed representative of its category, preserving structure."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, str):
        return ""
    if isinstance(value, dict):
        return {key: _canon(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canon(item) for item in value]
    return value


@settings(deadline=None)
@given(value=_json)
def test_shape_never_drifts_from_itself(value):
    assert_that(shape_diff(shape(value), shape(value))).is_empty()


@settings(deadline=None)
@given(value=_json)
def test_shape_ignores_leaf_values(value):
    assert_that(shape(value)).is_equal_to(shape(_canon(value)))
    assert_that(shape_diff(shape(value), shape(_canon(value)))).is_empty()


@settings(deadline=None)
@given(left=_json, right=_json)
def test_shape_diff_is_total(left, right):
    shape_diff(shape(left), shape(right))


@settings(deadline=None)
@given(number=st.integers() | st.floats())
def test_numbers_share_one_category(number):
    assert_that(shape(number)).is_equal_to("number")


@settings(deadline=None)
@given(value=_json)
def test_duplicate_elements_merge_to_one(value):
    assert_that(shape([value, value])).is_equal_to(shape([value]))


@settings(deadline=None)
@given(ident=st.integers(), name=st.text(), tags=st.lists(st.text()))
def test_conforming_dump_has_no_drift(ident, name, tags):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int
        name: str
        tags: list[str]

    dump = Item(id=ident, name=name, tags=tags).model_dump()
    assert_that(contract_drift(dump, Item.model_validate(dump))).is_empty()


@settings(deadline=None)
@given(payload=st.dictionaries(_keys, _json_atoms), extra_key=st.text(min_size=1))
def test_undeclared_key_is_always_detected(payload, extra_key):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int

    assume(extra_key != "id")
    grown = {**payload, "id": 1, extra_key: 1}
    found = contract_drift(grown, Item.model_validate(grown))
    assert_that([(named, sent) for (_, named, _), sent in found]).contains((extra_key, 1))


@settings(deadline=None)
@given(payload=st.dictionaries(_keys, _json))
def test_contract_drift_is_total(payload):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Sub(BaseModel):
        x: int

    class Item(BaseModel):
        id: int
        sub: Sub
        items: list[Sub]

    # a payload the instance was not built from, as a before-validator can leave it: answered or refused, nothing else
    with contextlib.suppress(UncheckableDriftError):
        contract_drift(payload, Item(id=1, sub=Sub(x=1), items=[Sub(x=2)]))


def _grown(draw, value):
    """*value* with undeclared keys put into some of the model payloads under it, and how many were put."""
    if isinstance(value, dict):
        grown, count = {}, 0
        for key, part in value.items():
            grown[key], added = _grown(draw, part)
            count += added
        # a mapping of rows by name takes any key for a row
        names = ["extra", "more", "0"] if value.keys() & {"x", "sub", "rows"} else []
        for name in draw(st.lists(st.sampled_from(names), unique=True, max_size=2)) if names else []:
            grown[name] = draw(_json_atoms | st.just([1]) | st.just({"k": 1}))
            count += 1
        return grown, count
    if isinstance(value, list):
        parts = [_grown(draw, part) for part in value]
        return [part for part, _ in parts], sum(added for _, added in parts)
    return value, 0


@settings(deadline=None)
@given(data=st.data(), widths=st.lists(st.integers(0, 3), min_size=3, max_size=3))
def test_every_undeclared_key_is_an_entry_whose_steps_lead_back_to_it(data, widths):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Sub(BaseModel):
        x: int

    class Row(BaseModel):
        sub: Sub
        subs: list[Sub]

    class Item(BaseModel):
        rows: list[Row]
        named: dict[str, Row]
        pair: tuple[Sub, list[Sub]]

    def row(width):
        return {"sub": {"x": 1}, "subs": [{"x": index} for index in range(width)]}

    clean = {
        "rows": [row(widths[0]) for _ in range(widths[1])],
        "named": {str(index): row(1) for index in range(widths[2])},
        "pair": [{"x": 1}, [{"x": 2}]],
    }
    payload, count = _grown(data.draw, clean)
    if not count:
        assert_conforms(payload, Item, exact=True)
        return
    with pytest.raises(AssertionFailure) as caught:
        assert_conforms(payload, Item, exact=True)
    entries = caught.value.diff.entries
    assert_that(entries).is_length(count)
    for entry in entries:
        reached = payload
        for step in entry.steps:
            reached = reached[step.value]
        assert_that(reached).described_as(entry.path).is_same_as(entry.actual)
        assert_that(entry.absent).is_equal_to("expected")
        rendered = "".join(f"[{step.value}]" if step.kind == "index" else f".{step.value}" for step in entry.steps)
        assert_that(entry.path).is_equal_to(rendered.removeprefix("."))


_collidable = st.sampled_from([0, 1, 2, "0", "1", "2", 1.0, 2.0, "1.0", "2.0", True, False, None, "None", "True"])


@settings(deadline=None)
@given(left=_collidable, right=_collidable)
def test_disambiguated_distinguishes_colliding_reprs(left, right):
    shown_left, shown_right = _disambiguated(left, right)
    if str(left) == str(right) and type(left) is not type(right):
        assert_that(shown_left).is_not_equal_to(shown_right)


_soft_groups = st.none() | st.sampled_from(["Headers", "Body"])
_soft_specs = st.lists(st.tuples(_soft_groups, st.booleans(), st.booleans()), min_size=1, max_size=8)


@settings(deadline=None)
@given(specs=_soft_specs)
def test_soft_report_numbers_every_failure_sequentially(specs):
    entries = [
        AssertionOutcome(
            group=group,
            location=(f"file{index}.py", index) if located else None,
            message=f"failure message {index}",
            diff=DiffResult(kind="dict", entries=[DiffEntry(path=f"field{index}", actual=index, expected=-index)])
            if diffed
            else None,
        )
        for index, (group, located, diffed) in enumerate(specs)
    ]
    report = _format_soft_errors(entries)
    for outcome in entries:
        assert_that(report).contains(outcome.message)
    for number in range(1, len(entries) + 1):
        assert_that(report).contains(f"{number}. ")


@settings(deadline=None)
@given(specs=_soft_specs)
def test_soft_report_shows_each_diff_path_under_its_own_entry(specs):
    entries = [
        AssertionOutcome(
            group=group,
            message=f"failure message {index}",
            diff=DiffResult(kind="dict", entries=[DiffEntry(path=f"field{index}", actual=index, expected=-index)])
            if diffed
            else None,
        )
        for index, (group, located, diffed) in enumerate(specs)
    ]
    report = _format_soft_errors(entries)
    for index, outcome in enumerate(entries):
        if outcome.diff is not None:
            assert_that(report).contains(f"field{index}: {index} != {-index}")


_field = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6)


@settings(deadline=None)
@given(ids=st.lists(st.integers(), max_size=6), suffix=st.text(max_size=4))
def test_assert_conforms_each_preserves_length_and_order(ids, suffix):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int
        name: str

    payloads = [{"id": ident, "name": f"{suffix}{ident}"} for ident in ids]
    validated = assert_conforms(payloads, Item, each=True).val
    assert_that(validated).is_length(len(ids))
    assert_that([item.id for item in validated]).is_equal_to(ids)


@settings(deadline=None)
@given(ids=st.lists(st.integers(), min_size=1, max_size=5), position=st.integers(), extra=_field)
def test_assert_conforms_each_exact_reports_indexed_drift(ids, position, extra):
    pytest.importorskip("pydantic", reason="pydantic not installed")
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int

    assume(extra != "id")
    index = position % len(ids)
    payloads = [{"id": ident} for ident in ids]
    payloads[index] = {**payloads[index], extra: 1}
    with pytest.raises(AssertionError) as exc_info:
        assert_conforms(payloads, Item, each=True, exact=True)
    assert_that(str(exc_info.value)).contains(f"[{index}].{extra}")


_chain_types = st.sampled_from([ValueError, KeyError, TypeError, RuntimeError, IndexError, AttributeError])


@settings(deadline=None)
@given(chain=st.lists(_chain_types, min_size=1, max_size=6))
def test_has_root_cause_walks_to_the_deepest_link(chain):
    errors = [exc_type(f"e{index}") for index, exc_type in enumerate(chain)]
    for outer, inner in pairwise(errors):
        outer.__cause__ = inner

    def raise_head():
        raise errors[0]

    assert_that(raise_head).raises(chain[0]).when_called_with().has_root_cause(chain[-1])


@settings(deadline=None)
@given(
    common=st.dictionaries(_keys, st.integers(), max_size=5),
    nulls=st.dictionaries(_keys, st.integers(), max_size=3),
)
def test_ignore_null_skips_every_expected_none_key(common, nulls):
    expected = {**common, **dict.fromkeys(nulls, None)}
    actual = {**common, **nulls}
    assert_that(actual).is_equal_to(expected, ignore_null=True)


_OPENAPI_TYPES = {"string": st.text(max_size=5), "integer": st.integers(), "boolean": st.booleans()}


@st.composite
def _openapi_operation(draw, min_required=0):
    """A generated object schema, a body built to satisfy it, and one required key to drop.

    ``min_required`` pins the schema to at least that many required keys, for the tests whose whole
    point is a missing one: filtering those cases out afterwards would throw away half the examples.
    """
    names = draw(st.lists(st.text(alphabet="abcdef", min_size=1, max_size=3), min_size=1, max_size=4, unique=True))
    types = {name: draw(st.sampled_from(sorted(_OPENAPI_TYPES))) for name in names}
    required = sorted(draw(st.lists(st.sampled_from(names), unique=True, min_size=min_required)))
    body = {name: draw(_OPENAPI_TYPES[kind]) for name, kind in types.items()}
    schema = {
        "type": "object",
        "required": required,
        "properties": {name: {"type": kind} for name, kind in types.items()},
    }
    dropped = draw(st.sampled_from(required)) if required else None
    return schema, body, dropped


def _spec_30(schema):
    content = {"application/json": {"schema": schema}}
    return {"openapi": "3.0.3", "paths": {"/r": {"get": {"responses": {"200": {"content": content}}}}}}


def _spec_20(schema):
    operation = {"produces": ["application/json"], "responses": {"200": {"schema": schema}}}
    return {"swagger": "2.0", "paths": {"/r": {"get": operation}}}


def _conforms(spec, body):
    try:
        assert_that(body).conforms_to_openapi(spec, "/r", "get")
    except AssertionFailure:
        return False
    return True


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation())
def test_a_body_built_from_the_schema_always_conforms(operation):
    schema, body, _dropped = operation
    assert_that(_conforms(_spec_30(schema), body)).is_true()


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation(min_required=1))
def test_dropping_a_required_key_is_always_detected(operation):
    schema, body, dropped = operation
    broken = {name: value for name, value in body.items() if name != dropped}
    assert_that(_conforms(_spec_30(schema), broken)).is_false()


@pytest.mark.skipif(not _HAS_JSONSCHEMA, reason="needs the [json] extra")
@settings(deadline=None)
@given(operation=_openapi_operation())
def test_swagger_2_and_openapi_3_agree_on_every_verdict(operation):
    schema, body, dropped = operation
    assert_that(_conforms(_spec_20(schema), body)).is_equal_to(_conforms(_spec_30(schema), body))
    if dropped is not None:
        broken = {name: value for name, value in body.items() if name != dropped}
        assert_that(_conforms(_spec_20(schema), broken)).is_equal_to(_conforms(_spec_30(schema), broken))


_literal_atoms = (
    st.none() | st.booleans() | st.integers() | st.text(max_size=5) | st.floats(allow_nan=False, allow_infinity=False)
)
_literals = st.recursive(
    _literal_atoms,
    lambda children: (
        st.lists(children, max_size=4)
        | st.tuples(children)
        | st.dictionaries(st.text(max_size=3), children, max_size=4)
        | st.frozensets(st.integers(), max_size=4)
    ),
    max_leaves=8,
)


@settings(deadline=None)
@given(value=_literals, column=st.integers(min_value=0, max_value=40))
def test_a_recorded_inline_literal_round_trips(value, column):
    # the input to `eval` is the literal this very call just rendered, never outside data
    assume(is_literalable(value))
    restored = eval(_format_literal(value, column))
    assert_that(restored).is_equal_to(value)


@st.composite
def _line_and_edit(draw):
    """A line plus a one-character edit of it, so the renderer has an intra-line change to point at.

    Two unrelated random strings would mostly be empty or share nothing, which never produces a caret
    row and leaves the property vacuous.
    """
    # every category str.splitlines() treats as a break is out, or the row extraction below over-splits
    printable = st.characters(exclude_categories=("Cc", "Cs", "Zl", "Zp"))
    base = draw(st.text(alphabet=printable, min_size=1, max_size=30))
    index = draw(st.integers(min_value=0, max_value=len(base) - 1))
    replacement = draw(printable)
    assume(base[index] != replacement)
    return base, base[:index] + replacement + base[index + 1 :]


@settings(deadline=None)
@given(pair=_line_and_edit())
def test_string_diff_shows_both_sides_with_anchored_carets(pair):
    left, right = pair
    rendered = _format_diff(DiffResult(kind="string", entries=[DiffEntry(path="line 1", actual=left, expected=right)]))
    rows = rendered.splitlines()[2:]
    assert_that([row[6:] for row in rows if row.startswith("    - ")]).is_equal_to([left])
    assert_that([row[6:] for row in rows if row.startswith("    + ")]).is_equal_to([right])
    assert_that(rows[0].startswith("    ?")).is_false()
    for previous, row in pairwise(rows):
        if row.startswith("    ?"):
            assert_that(previous.startswith(("    - ", "    + "))).is_true()


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12))
def test_mapped_mirrors_the_comprehension(items):
    assert_that(assert_that(items).mapped(lambda item: item * 2).val).is_equal_to([item * 2 for item in items])


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12), threshold=st.integers())
def test_filtered_on_mirrors_the_comprehension(items, threshold):
    def keeps(item):
        return item > threshold

    assert_that(assert_that(items).filtered_on(keeps).val).is_equal_to([item for item in items if keeps(item)])


@settings(deadline=None)
@given(items=st.lists(st.integers(), max_size=12))
def test_flat_mapped_equals_flatten_of_map(items):
    def expand(item):
        return [item, -item]

    assert_that(assert_that(items).flat_mapped(expand).val).is_equal_to(
        [part for item in items for part in expand(item)]
    )


@settings(deadline=None)
@given(items=st.lists(st.integers(), min_size=1, max_size=12), offset=st.integers(min_value=0, max_value=100))
def test_element_first_and_last_agree_with_indexing(items, offset):
    index = offset % len(items)
    assert_that(assert_that(items).element(index).val).is_equal_to(items[index])
    assert_that(assert_that(items).first().val).is_equal_to(items[0])
    assert_that(assert_that(items).last().val).is_equal_to(items[-1])


def _holds(check):
    try:
        check()
    except AssertionError:
        return False
    return True


@settings(deadline=None)
@given(left=st.datetimes(), right=st.datetimes())
def test_is_before_is_the_exact_complement_of_is_after_or_equal_to(left, right):
    before = _holds(lambda: assert_that(left).is_before(right))
    after_or_equal = _holds(lambda: assert_that(left).is_after_or_equal_to(right))
    assert_that(before).is_not_equal_to(after_or_equal)


@settings(deadline=None)
@given(left=st.datetimes(), right=st.datetimes())
def test_is_after_is_the_exact_complement_of_is_before_or_equal_to(left, right):
    after = _holds(lambda: assert_that(left).is_after(right))
    before_or_equal = _holds(lambda: assert_that(left).is_before_or_equal_to(right))
    assert_that(after).is_not_equal_to(before_or_equal)


def _ordering_answer(call):
    """A verdict, or the refusal that says the operands cannot be ordered at all."""
    try:
        call()
    except TypeError:
        return "refused"
    except AssertionError:
        return "failed"
    return "passed"


_MIXED = st.sampled_from(
    [
        0,
        1,
        -1,
        True,
        1.5,
        float("nan"),
        float("inf"),
        decimal.Decimal(1),
        decimal.Decimal("NaN"),
        fractions.Fraction(1, 2),
        complex(1, 2),
        "a",
        b"a",
        [1],
        (1,),
        {"a": 1},
        datetime.datetime(2026, 1, 1),
        datetime.date(2026, 1, 1),
        datetime.timedelta(seconds=1),
        datetime.time(12, 0),
    ]
)


_MIRRORED = [
    ("is_less_than", "is_greater_than"),
    ("is_less_than_or_equal_to", "is_greater_than_or_equal_to"),
]


@settings(deadline=None)
@given(left=_MIXED, right=_MIXED, pair=st.sampled_from(_MIRRORED))
def test_an_ordering_relation_reads_the_same_from_either_side(left, right, pair):
    """`a < b` and `b > a` are one question, and a pair that cannot be ordered is refused in both.

    Written after a NaN on the right answered for a pair before it had been tried: `is_less_than(nan)`
    on a string reported a failed comparison where `is_less_than(1)` on the same string refuses the
    operands, so an unorderable pair read as a verdict from one side only.
    """
    forward, backward = pair
    one = _ordering_answer(lambda: getattr(assert_that(left), forward)(right))
    other = _ordering_answer(lambda: getattr(assert_that(right), backward)(left))
    assert_that(one).described_as(f"{forward}({right!r}) on {left!r} against its mirror").is_equal_to(other)


@settings(deadline=None)
@given(value=_MIXED, low=_MIXED, high=_MIXED)
def test_a_range_refuses_the_operands_its_halves_refuse(value, low, high):
    """`is_between` is two relations, so it cannot accept operands either half would refuse."""
    halves = {
        _ordering_answer(lambda: assert_that(value).is_greater_than_or_equal_to(low)),
        _ordering_answer(lambda: assert_that(value).is_less_than_or_equal_to(high)),
    }
    if "refused" not in halves:
        return
    between = _ordering_answer(lambda: assert_that(value).is_between(low, high))
    assert_that(between).described_as(f"is_between({low!r}, {high!r}) on {value!r}").is_equal_to("refused")


# not "no message shows an address": a value's own repr is inherited, and this covers the text written around it

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{6,}")


class _Opaque:
    """No ``__repr__`` of its own, so ``repr()`` falls back to the address form."""


class _SelfIdentifying:
    def __repr__(self):
        return f"<Session {id(self):#x}>"


@dataclass
class _Wrapper:
    payload: object


_leaky_items = st.recursive(
    st.sampled_from([_Opaque, _SelfIdentifying]).map(lambda factory: factory()),
    lambda children: st.builds(_Wrapper, payload=children),
    max_leaves=3,
)


@settings(deadline=None)
@given(item=_leaky_items, name=st.text(alphabet="abc", min_size=1, max_size=4))
def test_the_extracting_item_label_never_leaks_a_memory_address(item, name):
    """Whatever the item's repr does, the label assertpy writes for it stays reproducible.

    A message that differs between runs cannot be asserted on, cannot be diffed in CI, and sends the
    reader chasing a number that means nothing.
    """
    assume(not hasattr(item, name))
    with pytest.raises(ValueError) as exc_info:
        assert_that([item]).extracting(name)
    assert_that(_ADDRESS.search(str(exc_info.value))).is_none()


@settings(deadline=None)
@given(
    error_type=st.sampled_from([ValueError, RuntimeError, KeyError, ZeroDivisionError, LookupError]),
    message=st.text(alphabet="abc 123", min_size=1, max_size=20),
)
def test_an_error_raised_by_user_code_reaches_the_caller_unchanged(error_type, message):
    """``extracting()`` annotates its own failures with an index, so it must not repackage anyone else's.

    ``AttributeError`` is deliberately absent from the sample: that one assertpy does intercept, to
    tell a broken accessor from a missing name.
    """

    class Failing:
        @property
        def name(self):
            raise error_type(message)

    with pytest.raises(error_type) as exc_info:
        assert_that([Failing()]).extracting("name")
    assert_that(type(exc_info.value)).is_equal_to(error_type)
    assert_that(str(exc_info.value)).is_equal_to(str(error_type(message)))


def _unavailable(_self):
    raise AttributeError("unavailable")


@settings(deadline=None)
@given(
    attributes=st.lists(st.text(alphabet="abcdef", min_size=3, max_size=8), min_size=1, max_size=5, unique=True),
    requested=st.text(alphabet="abcdef", min_size=3, max_size=8),
    declared_but_raising=st.booleans(),
)
def test_a_suggestion_is_a_real_attribute_and_never_the_one_that_was_asked_for(
    attributes, requested, declared_but_raising
):
    """Suggesting the name the reader just typed is worse than saying nothing: it reads as a bug.

    ``declared_but_raising`` is the case that produced exactly that. A property that raises is invisible
    to ``hasattr()``, so the name lands in ``dir()`` as its own closest match.
    """
    assume(requested not in attributes)
    namespace = dict.fromkeys(attributes, 0)
    if declared_but_raising:
        namespace[requested] = property(_unavailable)
    item = type("Generated", (), namespace)()
    with pytest.raises(ValueError) as exc_info:
        assert_that([item]).extracting(requested)
    suggested = re.search(r"did you mean '([^']*)'\?", str(exc_info.value))
    if suggested:
        assert_that(suggested.group(1)).is_not_equal_to(requested)
        assert_that(attributes).contains(suggested.group(1))


class _Money:
    """A value object the walker does not take apart: deliberately **not** a dataclass.

    The gap between the eight atomic types and the five decomposable shapes is where a whole class of
    bugs lives, and a domain object with its own ``__eq__`` is its most common inhabitant - far more so
    than the set that led us here. A dataclass would not reach it: the dispatcher keys on
    ``is_dataclass``, not on who wrote ``__eq__``, so ``_Inner`` above already covers that branch.
    """

    def __init__(self, amount):
        self.amount = amount

    def __eq__(self, other):
        return isinstance(other, _Money) and self.amount == other.amount

    def __hash__(self):
        return hash(self.amount)

    def __repr__(self):
        return f"_Money({self.amount})"


_UNDECOMPOSABLE = (_Money,)
"""The shapes in the lattice the walkers cannot take apart, named rather than only built.

The strictness property earns its keep only while the lattice still grows one, so narrowing it for
speed would leave that property green and disarmed.  The guard below reads this tuple, which is the
same one the strategy is built from, so removing a shape here fails there.
"""

# a value against a copy of itself: two different generated values would trip over the documented hash-matching gap
_wide_atoms = (
    _atoms
    | st.binary()
    | st.decimals(allow_nan=False, allow_infinity=False)
    | st.dates()
    | st.uuids()
    | st.one_of(*(st.builds(shape, amount=st.integers()) for shape in _UNDECOMPOSABLE))
)
_wide_values = st.recursive(
    _wide_atoms,
    lambda children: (
        st.lists(children)
        | st.dictionaries(st.text(), children)
        | st.tuples(children, children)
        | st.sets(_wide_atoms)
        | st.frozensets(_wide_atoms)
        | st.builds(_Pair, first=children, second=children)
        | st.builds(_Inner, a=st.integers(), b=st.text())
    ),
    max_leaves=20,
)


def test_the_lattice_still_names_a_shape_the_walkers_cannot_take_apart() -> None:
    """An empty tuple would skip every parametrised guard below rather than fail one, so the tuple
    itself is asserted first.  The strictness property carries the shape as a pinned `@example`, which
    is what actually keeps a narrowing from disarming it."""
    assert_that(_UNDECOMPOSABLE).is_not_empty()


@pytest.mark.parametrize("shape", _UNDECOMPOSABLE)
def test_the_wide_lattice_reaches_a_value_the_nested_walker_cannot_decompose(shape) -> None:
    """`test_a_value_is_strictly_equal_to_itself` earns its keep only while the lattice grows values
    the walkers cannot take apart, so the reach is asserted rather than assumed - once per ladder,
    because the two answer different questions and disagree (see the module docstring of
    ``assertpy._engine._diff``).

    Asserted on the shape the lattice is built from rather than on one a search found: `find()` is a
    randomised search and answered `NoSuchExample` once on a full run, which is a guard that lies in
    both directions.
    """
    value = shape(amount=1)
    assert_that(type(value) in _EQ_ATOMIC).is_false()
    assert_that(_sub_diff_entries(value, value, _ROOT)).is_none()


@pytest.mark.parametrize("shape", _UNDECOMPOSABLE)
def test_the_wide_lattice_reaches_a_value_the_top_level_ladder_runs_out_on(shape) -> None:
    """The nested guard above is satisfied by a set, which the *top-level* builder does handle - and
    the top-level fall-through is the branch the `UUID` regression actually lived in.  Mappings are
    excluded because their ``"scalar"`` kind means "routed to _dict_err before reaching the ladder",
    not "the ladder ran out"."""
    value = shape(amount=1)
    assert_that(type(value) in _EQ_ATOMIC).is_false()
    assert_that(is_mapping_like(value)).is_false()
    assert_that(_build_equality_diff(value, value).kind).is_equal_to("scalar")


def _passes(callable_):
    try:
        callable_()
    except AssertionError:
        return False
    return True


@settings(deadline=None)
@given(left=_values, right=_values)
def test_the_flag_and_the_matcher_agree(left, right):
    # on a composite expected value the matcher used to stop at the top-level type and hand the rest to `==`
    by_flag = _passes(lambda: assert_that(left).is_equal_to(right, strict_types=True))
    by_matcher = match.equal_to(right, strict_types=True).matches(left)
    assert_that(by_matcher).is_equal_to(by_flag)


@settings(deadline=None)
@given(left=_values, right=_values)
def test_strictness_only_ever_refines_equality(left, right):
    if _passes(lambda: assert_that(left).is_equal_to(right, strict_types=True)):
        assert_that(left).is_equal_to(right)


_held_values = st.integers(0, 1).flatmap(
    lambda a: st.sampled_from([_Inner(a, ""), _InnerTwin(a, ""), {"a": a, "b": ""}, _Pair(a, "")])
)


@settings(deadline=None)
@example(left=_Inner(1, ""), right=_InnerTwin(1, ""))
@given(left=_held_values, right=_held_values)
def test_ignoring_a_field_both_sides_hold_equal_changes_no_strict_verdict(left, right):
    """Taken apart for `ignore`, a nested value lost its class, and `strict_types` passed another class."""
    plain = _passes(lambda: assert_that(_Holding(left)).is_equal_to(_Holding(right), strict_types=True))
    ignoring = _passes(
        lambda: assert_that(_Holding(left)).is_equal_to(_Holding(right), strict_types=True, ignore="other")
    )
    assert_that(ignoring).is_equal_to(plain)


def _pinning_every_undecomposable(test):
    """Pin one example per shape in `_UNDECOMPOSABLE`, read from the tuple rather than written out.

    Hardcoding `_Money` here would leave the example testing it after a replacement, so the property
    would go on passing over a shape the lattice no longer grows.
    """
    for undecomposable in _UNDECOMPOSABLE:
        test = example(value=undecomposable(amount=1))(test)
    return test


@settings(deadline=None)
# pinned so narrowing the lattice cannot disarm this: the shape the walkers cannot take apart is what
# the property is here for, and a generated one is not guaranteed to arrive
@_pinning_every_undecomposable
@given(value=_wide_values)
def test_a_value_is_strictly_equal_to_itself(value):
    # the first line pins the identity shortcut, the second that strictness does not depend on it
    assert_that(value).is_equal_to(value, strict_types=True)
    assert_that(value).is_equal_to(copy.deepcopy(value), strict_types=True)


# a wide oracle over comparison semantics measured net-negative at 12800 pairs. ESC is excluded
# from every generated string, paths included, since a string diff prints its values raw
_NO_ESC = st.text(alphabet=st.characters(exclude_characters="\x1b"), max_size=200)
_TEXT_LEAVES = _NO_ESC | st.binary(max_size=200)
_ANY_LEAF = _TEXT_LEAVES | st.integers() | st.floats(allow_nan=True) | st.none() | st.booleans()
_DIFF_KINDS = st.sampled_from(["dict", "sequence", "string", "scalar", "model", "attrs", "set", "contains", "match"])


@st.composite
def _diffs(draw):
    """A `DiffResult` of any kind, whose entries may be one-sided, text-on-text, or mixed."""
    kind = draw(_DIFF_KINDS)
    entries = draw(
        st.lists(
            st.builds(
                DiffEntry,
                path=_NO_ESC,
                actual=_ANY_LEAF,
                expected=_ANY_LEAF,
            ),
            max_size=8,
        )
    )
    return DiffResult(kind=kind, entries=entries)


@settings(deadline=None)
@given(diff=_diffs(), color=st.booleans())
def test_rendering_a_diff_never_raises(diff, color):
    assert_that(_format_diff(diff, color=color)).is_instance_of(str)


@settings(deadline=None)
@given(diff=_diffs())
def test_a_caret_row_always_annotates_the_row_above_it(diff):
    # matched unindented: a generated path of "?" renders as `  ?: - ''` and would read as a guide row
    rows = _format_diff(diff).splitlines()
    for previous, row in pairwise(rows):
        if row.startswith("    ?"):
            assert_that(previous.startswith(("    - ", "    + "))).is_true()
    if rows:
        assert_that(rows[0].startswith("    ?")).is_false()


@settings(deadline=None)
@given(count=st.integers(min_value=1, max_value=200), kind=_DIFF_KINDS, one_sided=st.booleans())
def test_the_block_never_outgrows_its_budget(count, kind, one_sided):
    filler = "x" * 3_000
    entries = [DiffEntry(path="k", actual=filler, expected=None if one_sided else filler[:-1]) for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0)
    assert_that(len(rendered)).is_less_than(21_000)


@settings(deadline=None)
@given(count=st.integers(min_value=30, max_value=200), kind=st.sampled_from(["set", "contains"]))
def test_a_clipped_block_still_shows_something(count, kind):
    # `set` and `contains` join every item into one row, so dropping the row over the limit erased the diff
    filler = "x" * 3_000
    # `absent` is what puts an item in the extra group; without it the entry claims its expected value is None
    entries = [DiffEntry(path="extra", actual=filler, expected=None, absent="expected") for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0)
    assert_that(len(rendered)).is_greater_than(1_000)
    assert_that(rendered).contains("xxx")


@settings(deadline=None)
@given(diff=_diffs())
def test_an_uncoloured_render_adds_no_escape_sequences(diff):
    assert_that(_format_diff(diff, color=False)).does_not_contain("\033")


def _colour_is_balanced(rendered):
    opens = sum(rendered.count(code) for code in ("\033[31m", "\033[32m", "\033[36m"))
    return rendered.count("\033[0m") == opens


@settings(deadline=None)
@given(diff=_diffs())
def test_every_colour_opened_is_closed(diff):
    assert_that(_colour_is_balanced(_format_diff(diff, color=True))).is_true()


@settings(deadline=None)
@given(count=st.integers(min_value=1, max_value=200), kind=_DIFF_KINDS)
def test_colour_stays_balanced_when_the_block_is_clipped(count, kind):
    # a row cut blind loses the reset that closed its colour and stains every line after it
    filler = "x" * 3_000
    entries = [DiffEntry(path="k", actual=filler, expected=None) for _ in range(count)]
    rendered = _format_diff(DiffResult(kind=kind, entries=entries), max_entries=0, color=True)
    assert_that(_colour_is_balanced(rendered)).is_true()


@settings(deadline=None)
@given(
    entries=st.lists(
        st.builds(DiffEntry, path=st.text(min_size=1, max_size=8), actual=st.integers(), expected=st.integers()),
        min_size=1,
        max_size=12,
    ),
    limit=st.integers(min_value=1, max_value=12),
)
def test_the_entry_cap_is_honoured_and_the_remainder_counted(entries, limit):
    rendered = _format_diff(DiffResult(kind="dict", entries=entries), max_entries=limit)
    # counting the rendered value rows: the summary is emitted from the entry count alone
    shown = sum(1 for row in rendered.splitlines() if row.startswith("    - "))
    assert_that(shown).is_equal_to(min(len(entries), limit))
    if len(entries) > limit:
        assert_that(rendered).contains(f"... and {len(entries) - limit} more entries")
    else:
        assert_that(rendered).does_not_contain("more entries")


@given(
    actual=st.dictionaries(st.text(min_size=1, max_size=4), st.integers(), max_size=8),
    expected=st.dictionaries(st.text(min_size=1, max_size=4), st.integers(), max_size=8),
)
def test_the_key_walk_covers_both_sides_once_and_keeps_the_written_order(actual, expected):
    walked = _ordered_keys(actual, expected)
    assert_that(walked).is_length(len(set(actual) | set(expected)))
    assert_that(set(walked)).is_equal_to(set(actual) | set(expected))
    assert_that([key for key in walked if key in actual]).is_equal_to(list(actual))
    assert_that(_ordered_keys(actual, expected)).is_equal_to(walked)


@given(
    lead=st.integers(min_value=0, max_value=3000),
    trail=st.integers(min_value=0, max_value=3000),
    marker=st.sampled_from("ABC"),
)
def test_a_windowed_pair_shows_where_the_two_sides_part_however_deep_it_is(lead, trail, marker):
    # the defect this replaced: each side was cut from its start, so a difference past the cap printed
    # two identical-looking values. The shared run is generated well past the 400-character cap
    left, right = f"{'x' * lead}{marker}{'y' * trail}", f"{'x' * lead}z{'y' * trail}"
    rendered_left, rendered_right = _diff_sides(left, right)
    assert_that(rendered_left).is_not_equal_to(rendered_right)
    assert_that(rendered_left).contains(marker)
    assert_that(rendered_right).contains("z")


class TestOneDifferenceReadsTheSameInTextAndBytes:
    """The hint is about the difference, not about the type carrying it.

    It was type-dependent: the string branch demanded two `str` and returned nothing for anything else,
    so an upload compared as bytes got no hint while the identical comparison on text got one. Example
    tests pinned seven shapes. This states the rule over the space instead.
    """

    _TEXT = st.text(alphabet=st.sampled_from(" \t\r\n abcXYZ019"), max_size=24)

    @staticmethod
    def _hint(actual, expected):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(actual).is_equal_to(expected)
        return diagnose(failure.value.diff, actual, expected)

    @given(_TEXT, _TEXT)
    @settings(deadline=None)
    def test_the_same_pair_reads_the_same_in_both_types(self, actual, expected):
        assume(actual != expected)
        assert_that(self._hint(actual.encode(), expected.encode())).is_equal_to(self._hint(actual, expected))

    @given(_TEXT)
    @settings(deadline=None)
    def test_trailing_whitespace_is_named_in_both_types(self, value):
        assume(value.strip() and value.strip() != value)
        stripped = value.strip()
        assert_that(self._hint(value, stripped)).contains("surrounding whitespace")
        assert_that(self._hint(value.encode(), stripped.encode())).contains("surrounding whitespace")


class TestTheDanglingScanCountsWhatWasWritten:
    """The check's whole value is that it does not miss the shape it exists for, and its whole cost is
    reporting a working chain. Generated modules attack both at once.
    """

    _STATEMENTS = st.lists(
        st.sampled_from(
            [
                ("    assert_that(1)\n", 1),
                ("    assert_that(2).is_equal_to(2)\n", 0),
                ("    assert_that(3)  # assertpy: allow-dangling\n", 0),
                ('    assert_that("# assertpy: allow-dangling")\n', 1),
                ("    builder = assert_that(4)\n", 0),
                ("    assert_that(5).is_none\n", 1),
            ]
        ),
        min_size=1,
        max_size=8,
    )

    @given(_STATEMENTS)
    @settings(deadline=None)
    def test_every_dangling_line_is_reported_and_no_other(self, statements):
        body = "".join(line for line, _ in statements)
        source = "from assertpy import assert_that\n\n\ndef test_generated():\n" + body
        assert_that(dangling_findings(source, "generated.py")).is_length(sum(count for _, count in statements))


class TestTheCompactRenderingKeepsThePositionOfChange:
    """A soft entry drops the detail row when the headline already carries both values readably.

    "Readably" is a threshold, and a threshold is where an example-based test stops being convincing:
    every string long enough must keep a window around its first difference, wherever that difference
    falls, and every short one must stay a single line.  Generated pairs attack both sides of it.
    """

    @staticmethod
    def _detail(actual: str, expected: str) -> list[str]:
        """The diff rows of the single collected entry, without the one-cause hint above them.

        The hint is indented into the entry the same way, and it is about the whole failure rather than
        about a path: a pair like `''` against `' '` is explained by one and has no rows at all.
        """
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(actual).is_equal_to(expected)
        _header, _entry, *detail = str(failure.value).splitlines()
        return [row for row in detail if not row.strip().startswith(("every difference here is", "the values are"))]

    @given(
        head=st.text(alphabet="abcdefghij", min_size=61, max_size=200),
        tail=st.text(alphabet="abcdefghij", max_size=200),
    )
    @settings(deadline=None)
    def test_a_long_pair_always_shows_where_it_diverges(self, head, tail):
        actual, expected = head + "X" + tail, head + "Y" + tail
        detail = self._detail(actual, expected)
        assert_that(detail).is_length(1)
        assert_that(detail[0]).starts_with("   line 1: ").contains("X").contains("Y")

    # `\r` and friends are line breaks to `splitlines()`, which is how the message is read back:
    # a value carrying one is a multi-line failure, and those keep their per-line rows by design
    _ONE_LINE = st.text(st.characters(exclude_categories=("Cc", "Cs", "Zl", "Zp")), max_size=60)

    @given(actual=_ONE_LINE, expected=_ONE_LINE)
    @settings(deadline=None)
    def test_a_short_pair_never_repeats_the_headline(self, actual, expected):
        assume(actual != expected)
        assert_that(self._detail(actual, expected)).is_empty()


class TestEveryRefusalIsReadableWhateverArrived:
    """The refusal shape has to survive the value it is describing.

    It embeds `repr(value)`, and a repr can be empty, enormous, multi-line, or contain the very
    brackets the shape uses. Generated values attack all four at once, which no fixed set of examples
    covers: what a reader must always get back is the subject, the expectation and a named type.
    """

    @given(value=_values, expectation=st.text(min_size=1, max_size=20).filter(str.strip))
    @settings(deadline=None)
    def test_the_sentence_survives_any_value(self, value, expectation):
        with pytest.raises(TypeError) as failure:
            refuse(value, expectation)
        message = str(failure.value)
        assert_that(message).starts_with(f"val must be {expectation}, but was <")
        assert_that(message).ends_with(f"({type(value).__name__})")

    @given(value=st.text(min_size=200, max_size=4000))
    @settings(deadline=None)
    def test_a_long_value_never_floods_the_line(self, value):
        with pytest.raises(TypeError) as failure:
            refuse(value, "a number")
        assert_that(len(str(failure.value))).is_less_than(140)


class TestTheEvaluationCoresAgreeWithPython:
    """The cores answer the same questions Python does, over generated values rather than chosen ones.

    Each core replaced a rule that was written twice, and the risk of that kind of move is a shift at the
    edges rather than in the middle: the examples that were in mind when it was written keep passing.
    """

    @given(left=_values, right=_values)
    @settings(deadline=None)
    def test_equality_without_options_is_python_equality(self, left, right):
        assert_that(values_differ(left, right, None)).is_equal_to(not bool(left == right))

    @given(left=st.integers(), right=st.integers())
    def test_ordering_is_a_total_order_on_integers(self, left, right):
        assert_that(compare(left, right)).is_equal_to((left > right) - (left < right))
        assert_that(holds(left, right, "lt")).is_equal_to(left < right)
        assert_that(holds(left, right, "ge")).is_equal_to(left >= right)

    @given(left=st.integers(), middle=st.integers(), right=st.integers())
    def test_ordering_is_transitive(self, left, middle, right):
        if holds(left, middle, "lt") and holds(middle, right, "lt"):
            assert_that(holds(left, right, "lt")).is_true()

    @given(items=st.lists(st.integers(), max_size=8), wanted=st.integers())
    def test_membership_matches_the_in_operator(self, items, wanted):
        absent = missing_items(items, [wanted], lambda candidate: False)
        assert_that(not absent).is_equal_to(wanted in items)

    @given(items=st.lists(st.integers(), min_size=1, max_size=8))
    def test_a_collection_contains_all_of_its_own_elements(self, items):
        assert_that(missing_items(items, items, lambda candidate: False)).is_empty()

    @given(
        value=st.one_of(st.text(), st.lists(st.integers()), st.dictionaries(st.text(), st.integers()), st.integers())
    )
    def test_size_answers_none_exactly_when_len_refuses(self, value):
        try:
            expected = len(value)  # ty: ignore[invalid-argument-type]  # the refusal is the point
        except TypeError:
            expected = None
        assert_that(length_of(value)).is_equal_to(expected)

    @given(left=st.text(max_size=20), right=st.text(max_size=20))
    def test_text_relations_match_their_str_methods(self, left, right):
        assert_that(text_contains(left, right)).is_equal_to(right in left)
        assert_that(text_starts_with(left, right)).is_equal_to(left.startswith(right))
        assert_that(text_ends_with(left, right)).is_equal_to(left.endswith(right))

    @given(left=st.binary(max_size=20), right=st.binary(max_size=20))
    def test_text_relations_do_the_same_for_bytes(self, left, right):
        assert_that(text_contains(left, right)).is_equal_to(right in left)
        assert_that(text_starts_with(left, right)).is_equal_to(left.startswith(right))

    @given(text=st.text(max_size=20), raw=st.binary(max_size=20))
    def test_the_two_text_families_never_match_each_other(self, text, raw):
        assert_that(text_contains(text, raw)).is_false()
        assert_that(text_contains(raw, text)).is_false()
        assert_that(text_starts_with(text, raw)).is_false()
        assert_that(text_ends_with(raw, text)).is_false()


# Which narrowed view each subject reaches, so the table below is checked against the typed
# surface. A hand-written list of "types with a pipeline" stops matching the first time one is added.
_PIPELINE_VIEWS = {
    "list": "_IterableAssertion",
    "tuple": "_IterableAssertion",
    "set": "_IterableAssertion",
    "frozenset": "_IterableAssertion",
    "str": "_StringAssertion",
    "bytes": "_BytesAssertion",
    "bytearray": "_BytesAssertion",
    "dict": "_DictAssertion",
}

_PIPELINE_SUBJECTS = {
    "list": list,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "str": lambda items: "".join(chr(ord("a") + item % 26) for item in items),
    "bytes": lambda items: bytes(item % 256 for item in items),
    "bytearray": lambda items: bytearray(item % 256 for item in items),
    "dict": lambda items: dict.fromkeys(items, 0),
}
_PIPELINE_STEPS = {
    "filtered_on": lambda view: view.filtered_on(lambda item: True),
    "mapped": lambda view: view.mapped(str),
    "flat_mapped": lambda view: view.flat_mapped(lambda item: [item, item]),
}


# what a value no overload recognises resolves to
_FALLBACK_VIEW = "_ObjectAssertion"
# the one overload with no subject, so naming it as the fallback would collect the wrong overload
_UMBRELLA_VIEW = "_CapableAssertion"


def _plain_name(annotation) -> str:
    """The bare name an annotation is written with, or `""` for anything qualified, quoted or absent.

    Reading `.value.id` straight off a subscript raised `AttributeError` on `module.View[T]`, which is
    the opposite of the deliberate refusal the caller promises: an accident, not a diagnostic.
    """
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    return annotation.id if isinstance(annotation, ast.Name) else ""


def _pinned_pairs() -> dict[str, str]:
    """``{subject type name: view}`` read from the `assert_type(assert_that(<literal>), View)` calls.

    Written as a syntactic walk rather than a text search on purpose: `", _DateAssertion"` matches an
    import, a comment or an unrelated tuple just as happily as the call that proves anything.
    """
    source = pathlib.Path(__file__).with_name("test_typing.py").read_text(encoding="utf-8")
    pinned: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _plain_name(node.func) != "assert_type" or len(node.args) != 2:
            continue
        checked, view = node.args
        if not isinstance(checked, ast.Call) or _plain_name(checked.func) != "assert_that" or not checked.args:
            continue
        subject = _literal_type(checked.args[0])
        if not subject:
            continue
        # pinned twice to different views is a contradiction; twice to the same view is ordinary, since
        # `test_typing.py` checks a list subject in many chains and each line is a real assertion
        if subject in pinned and pinned[subject] != _plain_name(view):
            raise AssertionError(f"{subject} is pinned to both {pinned[subject]} and {_plain_name(view)}")
        pinned[subject] = _plain_name(view)
    return pinned


def _literal_type(expression) -> str:
    """The type name a literal subject has, or `""` when the expression is not a literal.

    Only literals are read, because only they say what type `assert_that` was handed without resolving
    a name.  A subject pinned solely through a variable simply does not count towards the pairs.
    """
    match expression:
        case ast.Constant(value=value):
            return type(value).__name__
        case ast.List():
            return "list"
        case ast.Tuple():
            return "tuple"
        case ast.Dict():
            return "dict"
        case ast.Set():
            return "set"
        case ast.Lambda():
            return "Callable"
        case ast.Call(func=ast.Name(id="cast"), args=[ast.Constant(value=str(name)), *_]):
            # the only way to write a value of a protocol type: a shape-keyed overload has no literal
            return name
        case ast.Call(func=ast.Attribute(value=ast.Name(id=module), attr=name)):
            return f"{module}.{name}"
        case ast.Call(func=ast.Name(id=name)):
            return name
    return ""


def _shape_bounds() -> dict[str, str]:
    """``{type variable: the shape it is bound to}``, for the overloads that key on a bound variable.

    A shape-keyed overload names a type variable rather than the protocol, so the view can carry the
    subject through to `.value`.  Resolving the bound is what keeps the subject readable here, and
    `tests/test_overload_order.py` reads the same declarations for the order it holds.
    """
    source = pathlib.Path(assertpy._engine._typing.__file__).read_text(encoding="utf-8")
    bounds = {}
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Assign(
                targets=[ast.Name(id=name)],
                value=ast.Call(func=ast.Name(id="TypeVar"), keywords=keywords),
            ):
                for keyword in keywords:
                    # only a bound written as one name resolves to a subject; the umbrella's is a union in a string
                    if keyword.arg == "bound" and isinstance(keyword.value, ast.Name):
                        bounds[name] = keyword.value.id
    return bounds


def _view_classes() -> dict[str, ast.ClassDef]:
    """Every protocol a value can be handed, by name.

    Both modules, not just the views: the umbrella is declared in the generated façade, so reading only
    `_typing.py` dropped it from the reachable set while the code still named it, and the gate stopped
    asking anything about it at all.
    """
    engine = pathlib.Path(__file__).resolve().parent.parent / "assertpy" / "_engine"
    return {
        node.name: node
        for source in (engine / "_typing.py", engine / "_capable_typing.py")
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion")
    }


def _named_view(node: ast.expr | None, classes: dict[str, ast.ClassDef]) -> str:
    """The protocol an annotation or a base names, reading through a subscript."""
    if node is None:
        return ""
    named = _plain_name(node.value if isinstance(node, ast.Subscript) else node)
    return named if named in classes else ""


def _members(name: str, classes: dict[str, ast.ClassDef], seen: set[str] | None = None) -> list[ast.FunctionDef]:
    """A protocol's methods and the ones it inherits.

    Inherited ones are not optional here: `_InvokedAssertion` reaches `_TextAssertion` only through a
    `first()` it does not declare itself.
    """
    seen = set() if seen is None else seen
    if name in seen or name not in classes:
        return []
    seen.add(name)
    found = [node for node in classes[name].body if isinstance(node, ast.FunctionDef)]
    for base in classes[name].bases:
        found += _members(_named_view(base, classes), classes, seen)
    return found


def _reachable_views() -> set[str]:
    """Every protocol a caller can end an expression on, from the entry views outwards.

    Reachability rather than position in the hierarchy.  A first attempt asked which protocols nothing
    inherits, and that answer is wrong in both directions: `_CoreAssertion` is a base and is returned by
    `returned()`, `raised()` and `at_json_path()`, while `_TextAssertion` is a base whose own `first()`
    hands it back, which is the only way to reach it and had no pin on it at all.
    """
    classes = _view_classes()
    reachable = {name for name in set(_dispatch_relation().values()) | {_UMBRELLA_VIEW} if name in classes}
    frontier = set(reachable)
    while frontier:
        found = {
            returned
            for name in frontier
            for method in _members(name, classes)
            if (returned := _named_view(method.returns, classes)) and returned not in reachable
        }
        reachable |= found
        frontier = found
    return reachable


def _pinned_views() -> set[str]:
    """Every protocol named as the expected type of an `assert_type` over a real chain.

    The subject has to be rooted in `assert_that`, so a pin written over a `cast` satisfies neither this
    nor a reader: it would prove the name exists rather than that anything resolves to it.
    """
    source = pathlib.Path(__file__).with_name("test_typing.py").read_text(encoding="utf-8")
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _plain_name(node.func) != "assert_type" or len(node.args) != 2:
            continue
        if _rooted_in_assert_that(node.args[0]) and (named := _plain_name(node.args[1])):
            found.add(named)
    return found


def _rooted_in_assert_that(node: ast.expr) -> bool:
    """Whether an expression is a chain that starts at `assert_that(...)`."""
    while True:
        if isinstance(node, ast.Call):
            if _plain_name(node.func) == "assert_that":
                return True
            node = node.func
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return False


def _dispatch_relation() -> dict[str, str]:
    """``{subject type name: protocol}`` for every `assert_that` overload that names a concrete type.

    Only top-level definitions carrying `@overload` are read.  Walking every `assert_that` in the file
    would take the implementation as well, whose annotation is the generic fallback and describes no
    subject, and any nested definition a test happens to declare.

    A subject appearing twice with different views is an error rather than a last-one-wins: the point of
    reading this relation is to notice a change, and a silent overwrite is how a change goes unnoticed.
    """
    source = pathlib.Path(assertpy.assertpy.__file__).read_text(encoding="utf-8")
    relation: dict[str, str] = {}
    fallbacks: list[list[str]] = []
    umbrellas: list[list[str]] = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if not any(_is_overload(decorator) for decorator in node.decorator_list):
            continue
        returns, arguments = node.returns, node.args.args
        view = _plain_name(returns)
        subjects = _annotated_types(arguments[0].annotation) if arguments and arguments[0].annotation else []
        if view == _FALLBACK_VIEW:
            # a bare TypeVar subject, which is what stops a concrete overload from hiding behind the same return
            fallbacks.append(subjects)
            continue
        if view == _UMBRELLA_VIEW:
            # the umbrella keeps the whole surface without naming a type, dispatching on a union of shapes,
            # so it has no row in the relation and the order guard is what holds its placement
            umbrellas.append(subjects)
            continue
        if not view.endswith("Assertion"):
            written = ast.unparse(returns) if returns else "nothing"
            raise AssertionError(f"an assert_that overload returns {written}, which this walk cannot read")
        # an unreadable overload would drop out of the relation silently, so refuse as the protocol walk does
        if not subjects:
            raise AssertionError(f"an assert_that overload returning {view} has a subject this walk cannot read")
        bounds = _shape_bounds()
        for subject in (bounds.get(name, name) for name in subjects):
            # a repeat is an error even when it agrees: letting the agreeing case through would hide a duplicate
            if subject in relation:
                raise AssertionError(f"{subject} is dispatched by more than one overload")
            relation[subject] = view
    if fallbacks != [["_T"]]:
        raise AssertionError(f"expected exactly one generic fallback overload, found subjects {fallbacks}")
    if umbrellas != [["_CapableT"]]:
        raise AssertionError(f"expected exactly one capability umbrella overload, found subjects {umbrellas}")
    return relation


def _is_overload(decorator) -> bool:
    """`@overload` or `@typing.overload`, the two ways the same decorator gets written."""
    if isinstance(decorator, ast.Name):
        return decorator.id == "overload"
    return isinstance(decorator, ast.Attribute) and decorator.attr == "overload"


def _annotated_types(annotation) -> list[str]:
    """The concrete type names an annotation mentions, with `list[_E] | tuple[_E, ...]` giving two."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _annotated_types(annotation.left) + _annotated_types(annotation.right)
    if isinstance(annotation, ast.Subscript):
        return _annotated_types(annotation.value)
    if isinstance(annotation, ast.Attribute):
        return [
            f"{annotation.value.id}.{annotation.attr}" if isinstance(annotation.value, ast.Name) else annotation.attr
        ]
    return [annotation.id] if isinstance(annotation, ast.Name) else []


def _reachable_methods(protocol: str) -> set[str]:
    """Every method a protocol offers, inherited ones included."""
    source = pathlib.Path(assertpy._engine._typing.__file__).read_text(encoding="utf-8")
    declared: dict[str, tuple[set[str], list[str]]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            bases = [_plain_name(base) for base in node.bases]
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            declared[node.name] = (methods, [base for base in bases if base.endswith("Assertion")])

    def walk(name: str) -> set[str]:
        methods, parents = declared[name]
        return methods.union(*(walk(parent) for parent in parents)) if parents else methods

    return walk(protocol)


def _form_names(test_name: str) -> list[str]:
    """The keys of the `forms` dictionary inside one test, read from this file's own syntax."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == test_name:
            assigned = [
                statement
                for statement in node.body
                if isinstance(statement, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "forms" for target in statement.targets)
            ]
            if len(assigned) != 1:
                raise AssertionError(f"{test_name} has {len(assigned)} `forms` dictionaries, expected one")
            for statement in assigned:
                if True:
                    # a computed key would be dropped here and the form would vanish from the comparison
                    if not isinstance(statement.value, ast.Dict):
                        raise AssertionError(f"`forms` in {test_name} is not a dictionary literal")
                    if not all(
                        isinstance(key, ast.Constant) and isinstance(key.value, str) for key in statement.value.keys
                    ):
                        raise AssertionError(f"`forms` in {test_name} has a key this gate cannot read")
                    return [key.value for key in statement.value.keys]
    raise AssertionError(f"no `forms` dictionary found in {test_name}")


class _TakesAnyKey(Mapping):
    """A row that reads a key without hashing it, which is why the selector type stays `object`.

    Written out rather than assumed: a mapping is free to define `__getitem__` however it likes, and
    this one answers for a list.  Every narrowing of the selector type tried during review refused this
    call, and the runtime takes it.
    """

    def __getitem__(self, key):
        return f"got {key!r}"

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


class TestEveryViewAValueCanReachIsPinned:
    """The other half of the pin gate: the views a *chain step* reaches, not the entry.

    `test_every_subject_and_view_pair_is_pinned_by_an_assert_type` covers what `assert_that` resolves to.
    Everything past that first step is this one's: a pivot, a narrowing, an element.  It found one view
    with no pin on it at all, `_TextAssertion`, reachable only as the text of a caught message.
    """

    def test_every_reachable_view_has_an_assert_type_on_it(self):
        reachable = _reachable_views()
        # the views module is the subject, so a walk that found few of them read the wrong thing
        assert_that(reachable).described_as("protocols a caller can reach").is_length_between(10, 40)

        missing = sorted(reachable - _pinned_views())
        assert_that(missing).described_as("reachable views with no assert_type over a real chain").is_empty()

    def test_a_view_nothing_reaches_is_not_asked_for_a_pin(self):
        """Guards the exclusion rather than trusting it: unreachable protocols exist and are out."""
        unreachable = set(_view_classes()) - _reachable_views()
        assert_that(unreachable).described_as("protocols no expression can end on").is_not_empty()


class TestEveryPipelineStepHandsBackAList:
    """The runtime half of what the typed surface promises after a pivot.

    `_ListAssertion` says `value` is a `list`, and the point of saying so is that it holds for every
    subject a pipeline accepts, not only for the `list` a suite usually starts from.  The check is the
    whole product of subject and operation rather than a sample of it: the union that used to be
    declared here came precisely from reasoning about one container and assuming the other three.
    """

    def test_the_subject_table_matches_what_assert_that_dispatches(self):
        """The whole subject-to-view relation, read out of the overloads rather than remembered.

        Comparing only the set of view names was not enough, and the hole is worth naming: a new subject
        dispatched to a view already in the table, or one of several subjects sharing a view going away,
        both left the comparison equal.  So the relation is compared as a relation.

        Inheritance is resolved on the way, because a carrier can hold the pipeline without declaring it:
        `_ListAssertion` gets `filtered_on` from `_IterableAssertion` and an inherited method is as real
        to a caller as a declared one.
        """
        dispatched = _dispatch_relation()
        with_a_pipeline = {
            subject: view for subject, view in dispatched.items() if "filtered_on" in _reachable_methods(view)
        }
        assert_that(with_a_pipeline).described_as(
            "what assert_that narrows to a view with a pipeline, against the subjects this file walks"
        ).is_equal_to(_PIPELINE_VIEWS)

    def test_every_subject_and_view_pair_is_pinned_by_an_assert_type(self):
        """The structural relation says what is written; `test_typing.py` says what a checker picks.

        This gate reads annotations, so it cannot see overload resolution: a wider overload written
        above a narrower one would change which view a checker actually chooses while leaving the text
        here untouched.  What closes that gap is the other file, where the pair is pinned with
        `assert_type` and run through ty, mypy, pyright and pyrefly.

        Pairs, not views.  Several subjects reach the same view, so pinning the view once would let the
        resolution of every other subject in that group drift to the fallback unnoticed.
        """
        pinned = _pinned_pairs()
        missing = {
            f"{subject} -> {view}" for subject, view in _dispatch_relation().items() if pinned.get(subject) != view
        }
        assert_that(missing).described_as("subject-to-view pairs with no assert_type on them").is_empty()

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("View", "View"),
            ("View[int]", "View"),
            ("module.View", ""),
            ("module.View[int]", ""),
            ("'View'", ""),
            ("View[int, str]", "View"),
        ],
    )
    def test_the_name_reader_says_what_it_can_and_cannot_read(self, written, expected):
        """The syntax these gates understand, written down instead of implied.

        Every walk here reads source rather than resolved types, so which spellings it understands is a
        real limit and belongs in a test: a form it cannot read has to come back empty and reach the
        caller's explicit refusal, never an `AttributeError` and never a wrong answer.
        """
        assert_that(_plain_name(ast.parse(written, mode="eval").body)).is_equal_to(expected)

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("[1, 2]", "list"),
            ("(1, 2)", "tuple"),
            ("{1, 2}", "set"),
            ("{'a': 1}", "dict"),
            ("'text'", "str"),
            ("b'raw'", "bytes"),
            ("1", "int"),
            ("True", "bool"),
            ("lambda: None", "Callable"),
            ("frozenset([1])", "frozenset"),
            ("datetime.date(2026, 1, 1)", "datetime.date"),
            ("some_variable", ""),
            ("a + b", ""),
        ],
    )
    def test_the_literal_reader_names_the_types_it_supports(self, written, expected):
        """Which subjects count towards the pinned pairs, and which are simply not literals."""
        assert_that(_literal_type(ast.parse(written, mode="eval").body)).is_equal_to(expected)

    def test_a_second_step_runs_on_what_the_first_one_returned(self):
        """The result of a pivot carries the pivots itself, which is what makes a chain a chain."""
        chained = assert_that([1, 2, 3]).mapped(str).filtered_on(lambda item: item != "2")
        assert_that(type(chained.value)).is_equal_to(list)
        assert_that(chained.value).is_equal_to(["1", "3"])
        assert_that(type(chained.mapped(int).value)).is_equal_to(list)

    @pytest.mark.parametrize("subject", sorted(_PIPELINE_SUBJECTS), ids=sorted(_PIPELINE_SUBJECTS))
    @pytest.mark.parametrize("step", sorted(_PIPELINE_STEPS), ids=sorted(_PIPELINE_STEPS))
    @given(items=st.lists(st.integers(min_value=0, max_value=255), max_size=8))
    def test_a_step_builds_a_list_whatever_the_subject_was(self, subject, step, items):
        built = _PIPELINE_STEPS[step](assert_that(_PIPELINE_SUBJECTS[subject](items)))
        assert_that(type(built.value)).described_as(f"{step} on a {subject}").is_equal_to(list)

    @pytest.mark.parametrize("subject", ["list", "tuple", "set", "frozenset"], ids=lambda name: name)
    @given(identifiers=st.lists(st.integers(), max_size=6, unique=True))
    def test_extraction_ends_on_a_list_from_every_collection(self, subject, identifiers):
        """The subject reaches `extracting` as the container under test, not as a list of its items.

        The first version of this built the container and then rebuilt a list out of it before calling
        `extracting`, so all four cases were the same case.  Rows are tuples here because a `set` and a
        `frozenset` need hashable members, and a tuple is extracted by index the same way a mapping row
        is extracted by key.
        """
        rows = _PIPELINE_SUBJECTS[subject]((identifier, "name") for identifier in identifiers)
        extracted = assert_that(rows).extracting(0)
        assert_that(type(extracted.value)).described_as(f"extracting from a {subject}").is_equal_to(list)

    @given(rows=st.lists(st.tuples(st.integers(), st.text(alphabet="ab", max_size=3)), max_size=6))
    def test_every_call_form_of_extraction_ends_on_a_list(self, rows):
        """One name, several names, and each keyword option the signature accepts.

        The declared return covers `*names` and `**kwargs` alike, so checking a single positional name
        would leave the multi-name form, `filter` and `sort` resting on nothing.  Several names build
        tuples rather than scalars, which is a different code path to the same promise.
        """
        subject = [{"id": identifier, "name": name} for identifier, name in rows]
        # held in a variable, as the typed suite pins: an invariant `dict[str, str]` fits no `dict[str, object]`
        criteria: dict[str, str] = {"name": "a"}
        forms = {
            # keyed by the case name in `typing_cases.py`, so the two suites compare as sets, not as two numbers
            "one-name": lambda: assert_that(subject).extracting("id"),
            "several-names": lambda: assert_that(subject).extracting("id", "name"),
            "filter-callable": lambda: assert_that(subject).extracting("id", filter=lambda row: True),
            "filter-by-key": lambda: assert_that(subject).extracting("id", filter="name"),
            "sort-callable": lambda: assert_that(subject).extracting("id", sort=lambda row: row["id"]),
            "filter-by-mapping": lambda: assert_that(subject).extracting("id", filter={"name": "a"}),
            "sort-by-key": lambda: assert_that(subject).extracting("id", sort="id"),
            "sort-by-keys": lambda: assert_that(subject).extracting("id", sort=["name", "id"]),
            "filter-and-sort": lambda: assert_that(subject).extracting("id", filter="name", sort="id"),
            "filter-from-a-variable": lambda: assert_that(subject).extracting("id", filter=criteria),
            "filter-from-a-mapping": lambda: assert_that(subject).extracting(
                "id", filter=MappingProxyType({"name": "a"})
            ),
            "a-slice": lambda: assert_that([(1, 2, 3)]).extracting(slice(0, 2)),
            "an-unhashable-selector": lambda: assert_that([_TakesAnyKey()]).extracting([]),
        }
        for description, build in forms.items():
            assert_that(type(build().value)).described_as(f"extracting {description}").is_equal_to(list)

    def test_the_call_forms_here_match_the_ones_the_typed_suite_records(self):
        """The two halves of the same claim, compared as sets of named forms.

        `typing_cases.py` records each accepted call form as a case a checker must accept, and the test
        above runs each one.  They drifted once already: the runtime side was missing the mapping filter
        and the multi-key sort while the report said both were covered.

        The keys are read out of the syntax of that test's own dictionary, not by searching the file for
        text: a second variable named `forms` anywhere above would have won the search, and the answer
        would have been about the wrong dictionary.
        """
        here = _form_names("test_every_call_form_of_extraction_ends_on_a_list")
        assert_that(here).described_as("call forms named twice").does_not_contain_duplicates()

        recorded = pathlib.Path(__file__).with_name("typing_cases.py").read_text(encoding="utf-8")
        # a label left behind after its call was deleted would keep the two sets equal with the form gone
        marked = [
            found.group(1)
            for line in recorded.splitlines()
            if (found := re.search(r"# case: (valid-extracting-[\w-]+)", line)) and ".extracting(" in line
        ]
        every_marker = re.findall(r"# case: (valid-extracting-[\w-]+)", recorded)
        assert_that(marked).described_as("markers that no longer sit on a call").is_equal_to(every_marker)
        assert_that(marked).described_as("cases marked twice").does_not_contain_duplicates()

        typed = {name.removeprefix("valid-extracting-") for name in marked}
        assert_that(set(here)).described_as(
            "call forms exercised here, against the ones typing_cases.py records"
        ).is_equal_to(typed)

    @given(keys=st.lists(st.text(alphabet="abc", min_size=1, max_size=3), max_size=6))
    def test_extraction_from_a_mapping_walks_its_keys(self, keys):
        """What extraction does to a mapping, recorded as measured rather than as intended.

        A mapping is walked over its keys, so `extracting(0)` indexes into the key itself and a mapping
        with integer keys raises.  Whether that is the API anyone wants is an open question, and this
        test deliberately asserts only the part the typed surface depends on, that the result is a list.
        Pinning the extracted values here would turn an unreviewed behaviour into a contract and make
        fixing it look like a regression.
        """
        extracted = assert_that(dict.fromkeys(keys, 0)).extracting(0)
        assert_that(type(extracted.value)).is_equal_to(list)


@needs_groups
class TestEveryLeafOfAGroupIsReachable:
    """What the group pivots promise on a tree of arbitrary shape.

    The example-based tests use one flat group and one with a single nested level, which is the shape
    anyone writes by hand.  Real groups come out of `asyncio.TaskGroup` and retry loops, where nesting
    is whatever the failures happened to produce.  Two invariants: the leaves pivot loses nothing and
    invents nothing, and the three type questions answer with one voice.
    """

    @staticmethod
    def _tree(draw):
        """A group whose members are leaves or further groups, drawn to an arbitrary depth.

        The leaf types vary so that a drawn question has no fixed answer: with every leaf a `ValueError`
        the agreement below would hold on a constant, which is close to asserting nothing.
        """
        leaf = st.builds(
            lambda kind, text: kind(text),
            st.sampled_from([ValueError, KeyError, TypeError]),
            st.integers(min_value=0, max_value=99).map(str),
        )
        return draw(
            st.recursive(
                leaf,
                lambda inner: st.builds(
                    lambda members: ExceptionGroup("generated", members),
                    st.lists(inner, min_size=1, max_size=4),
                ),
                max_leaves=12,
            )
        )

    @staticmethod
    def _flatten(exc):
        """The leaves, computed the obvious way, to compare the implementation against."""
        if not isinstance(exc, BaseExceptionGroup):
            return [exc]
        return [leaf for member in exc.exceptions for leaf in TestEveryLeafOfAGroupIsReachable._flatten(member)]

    @given(data=st.data())
    @settings(max_examples=50)
    def test_the_pivot_reaches_every_leaf_and_no_more(self, data):
        group = self._tree(data.draw)
        assume(isinstance(group, BaseExceptionGroup))

        def raise_it():
            raise group

        caught = assert_that(raise_it).raises(type(group)).when_called_with()
        expected = self._flatten(group)
        assert_that(caught.errors().value).is_length(len(expected))
        assert_that([id(leaf) for leaf in caught.errors().value]).is_equal_to([id(leaf) for leaf in expected])

    @given(data=st.data(), asked=st.sampled_from([ValueError, KeyError, TypeError, LookupError, Exception]))
    @settings(max_examples=100)
    def test_the_three_group_forms_agree_on_whatever_is_asked(self, data, asked):
        """One verdict, three spellings.

        All three walk the same nodes, groups included, so a type one of them finds the others have to
        agree about. A type the group holds has to be found
        by both and refused by `does_not_contain_error`, and a type it does not hold the other way round.
        The drawn types include a base class and a group type on purpose: those are the two shapes that
        told the leaves-only version of `error_of` apart from this one.
        """
        group = self._tree(data.draw)
        assume(isinstance(group, BaseExceptionGroup))

        def raise_it():
            raise group

        for wanted in (asked, type(group)):
            caught = assert_that(raise_it).raises(type(group)).when_called_with()
            present = caught.check().contains_error(wanted).passed
            assert_that(caught.check().error_of(wanted).passed).described_as(
                f"error_of({wanted.__name__}) against contains_error"
            ).is_equal_to(present)
            assert_that(caught.check().does_not_contain_error(wanted).passed).described_as(
                f"does_not_contain_error({wanted.__name__}) against contains_error"
            ).is_equal_to(not present)


class TestTheGroupShapeMatcherAgreesWithAnExhaustiveSearch:
    """What `matches_error_tree()` claims, checked against trying every pairing.

    The matcher pairs entries with members by augmenting paths, which is the part of this library where
    a plausible-looking shortcut gives a wrong verdict rather than a wrong message.  At these widths the
    permutations can all be tried, so the reference needs no cleverness to be trusted.
    """

    _KINDS = st.sampled_from([ValueError, KeyError, TypeError])

    @staticmethod
    def _pairs_somehow(spec, exceptions):
        """Whether any assignment of members to entries satisfies all of them, tried exhaustively."""
        if len(spec) != len(exceptions):
            return False
        return any(
            all(isinstance(exceptions[order[entry]], spec[entry]) for entry in range(len(spec)))
            for order in itertools.permutations(range(len(exceptions)))
        )

    @given(
        spec=st.lists(st.sampled_from([ValueError, KeyError, TypeError, Exception]), min_size=1, max_size=6),
        kinds=st.lists(_KINDS, min_size=1, max_size=6),
    )
    @settings(max_examples=300)
    def test_the_verdict_is_the_one_an_exhaustive_search_gives(self, spec, kinds):
        exceptions = tuple(kind("x") for kind in kinds)
        assert_that(_matches_shape(spec, exceptions)).is_equal_to(self._pairs_somehow(spec, exceptions))

    @given(
        spec=st.lists(st.sampled_from([ValueError, KeyError, TypeError, Exception]), min_size=1, max_size=6),
        kinds=st.lists(_KINDS, min_size=1, max_size=6),
        data=st.data(),
    )
    @settings(max_examples=300)
    def test_the_verdict_does_not_depend_on_the_order_either_side_is_written(self, spec, kinds, data):
        """The claim is about the shape, so rewriting it in another order has to answer the same.

        This is the property a greedy pairing fails: `pytest.RaisesGroup` accepts one spelling of a spec
        and refuses the other on the same group.
        """
        exceptions = tuple(kind("x") for kind in kinds)
        verdict = _matches_shape(spec, exceptions)
        assert_that(_matches_shape(data.draw(st.permutations(spec)), exceptions)).is_equal_to(verdict)
        assert_that(_matches_shape(spec, tuple(data.draw(st.permutations(exceptions))))).is_equal_to(verdict)


_LEAVES = st.one_of(
    st.integers(), st.floats(allow_nan=False), st.text(max_size=8), st.booleans(), st.none(), st.binary(max_size=8)
)
_STRUCTURES = st.recursive(
    _LEAVES,
    lambda inner: st.one_of(
        st.lists(inner, max_size=4),
        st.tuples(inner, inner),
        st.dictionaries(st.text(max_size=4), inner, max_size=4),
        st.frozensets(_LEAVES, max_size=4),
    ),
    max_leaves=12,
)


class TestStableReprHoldsOverArbitraryStructures:
    """It runs inside a pytest report hook, where an exception costs the reader the whole run.

    Both shapes that used to escape were found by a reviewer rather than by the example suite, so the
    invariant is stated here as a property instead of as more examples.
    """

    @given(_STRUCTURES)
    @settings(deadline=None)
    def test_it_never_raises_and_repeats_itself(self, value):
        first = stable_repr(value)
        assert_that(first).is_instance_of(str)
        assert_that(stable_repr(value)).described_as("same value, same text").is_equal_to(first)

    @given(st.frozensets(_LEAVES, max_size=6))
    @settings(deadline=None)
    def test_a_set_reads_the_same_however_it_was_built(self, members):
        # the xdist hazard in miniature: two processes iterate one set in two orders
        rebuilt = frozenset(reversed(list(members)))
        assert_that(stable_repr(rebuilt)).is_equal_to(stable_repr(members))

    @given(st.dictionaries(st.text(max_size=4), _LEAVES, max_size=4))
    @settings(deadline=None)
    def test_a_value_that_contains_itself_terminates(self, value):
        value["self"] = value
        assert_that(stable_repr(value)).contains("...")


class TestClusteringDoesNotDependOnArrivalOrder:
    """Under xdist the controller receives failures in whatever order workers finish in.

    A summary that changes with that order is a summary a reader cannot compare between two runs of the
    same red suite, and one such dependency shipped into the rewrite before a reviewer caught it.
    """

    _OBSERVATIONS = st.lists(
        st.builds(
            Observation,
            st.builds(Signature, st.just(True), st.sampled_from(["a", "b.c", "d[*]"]), st.just((("key", "'a'"),))),
            st.sampled_from(["1", "2", "3"]),
            st.sampled_from(["9", "8"]),
        ),
        min_size=1,
        max_size=3,
    )

    @given(st.lists(st.tuples(st.text(min_size=1, max_size=6), _OBSERVATIONS), min_size=3, max_size=12), st.randoms())
    @settings(deadline=None)
    def test_the_rendered_summary_is_a_function_of_the_set_not_the_sequence(self, recorded, random):
        shuffled = list(recorded)
        random.shuffle(shuffled)
        total = len(recorded)
        assert_that(render(clusters(shuffled, total), total)).is_equal_to(render(clusters(recorded, total), total))

    @given(st.lists(st.tuples(st.text(min_size=1, max_size=6), _OBSERVATIONS), max_size=12))
    @settings(deadline=None)
    def test_no_cluster_ever_claims_more_failures_than_the_run_had(self, recorded):
        total = len(recorded)
        for cluster in clusters(recorded, total):
            assert_that(cluster.size).is_less_than_or_equal_to(total)


class TestSummaryValuesStayWithinTheirBudget:
    """Two failures over a large payload used to put the payload on the terminal twice and through the
    xdist transport once per failure. The cap is what keeps a summary a summary.
    """

    @given(_STRUCTURES)
    @settings(deadline=None)
    def test_no_value_exceeds_the_cap_by_more_than_its_own_notice(self, value):
        shown = _shown(value)
        assert_that(len(shown)).is_less_than_or_equal_to(_VALUE_LIMIT + len("... (999999 more chars)"))

    @given(st.text(min_size=400, max_size=900))
    @settings(deadline=None)
    def test_a_long_value_says_how_much_was_cut(self, value):
        shown = _shown(value)
        assert_that(shown).starts_with(stable_repr(value)[:_VALUE_LIMIT]).ends_with("more chars)")


_TENTHS = st.integers(-20, 20).map(lambda tenths: tenths / 10)
_TOLERANCES = st.sampled_from([0.1, 0.2, 0.3, 0.5, 1.0])


@settings(deadline=None)
@example(value=-1.1, other=-0.9, tolerance=0.2)
@example(value=float("inf"), other=float("inf"), tolerance=1.0)
@example(value=float("nan"), other=float("nan"), tolerance=1.0)
@given(value=_TENTHS, other=_TENTHS, tolerance=_TOLERANCES)
def test_closeness_is_one_answer_however_it_is_asked(value, other, tolerance):
    """The builder windowed around `other`, the matcher around the value and `tolerance=` took the difference,
    and a float rounds each differently at the boundary: `-1.1` was close to `-0.9` and not the reverse."""
    answers = {
        "is_close_to": _passes(lambda: assert_that(value).is_close_to(other, tolerance)),
        "swapped": _passes(lambda: assert_that(other).is_close_to(value, tolerance)),
        "matcher": match.close_to(other, tolerance).matches(value),
        "tolerance": _passes(lambda: assert_that(value).is_equal_to(other, tolerance=tolerance)),
        "negated": not _passes(lambda: assert_that(value).is_not_close_to(other, tolerance)),
    }
    assert_that(set(answers.values())).described_as(str(answers)).is_length(1)


_PLAIN_OPERANDS = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True, allow_subnormal=True),
    st.integers(),
    st.integers(-(10**400), 10**400),
)
_PLAIN_TOLERANCES = st.one_of(
    st.floats(min_value=0, allow_infinity=True, allow_subnormal=True), st.integers(0, 10**400)
)


@settings(deadline=None)
@example(value=-1.1, other=-0.9, tolerance=0.2)
@example(value=0.1 + 0.2, other=0.3, tolerance=5.551115123125783e-17)
@example(value=-0.0, other=0.0, tolerance=0)
@example(value=5e-324, other=0.0, tolerance=5e-324)
@example(value=10**400, other=1e308, tolerance=float("inf"))
@example(value=float("inf"), other=float("inf"), tolerance=0)
@example(value=float("-inf"), other=float("inf"), tolerance=float("inf"))
@example(value=float("nan"), other=float("nan"), tolerance=float("inf"))
@given(value=_PLAIN_OPERANDS, other=_PLAIN_OPERANDS, tolerance=_PLAIN_TOLERANCES)
def test_the_plain_closeness_answers_as_the_general_one(value, other, tolerance):
    """`match.close_to` answers exact ints and floats inline, and only an int past the float range leaves it."""
    plain = plainly_within(value, other, tolerance)
    general = _within_tolerance(value, other, tolerance)
    assert_that(plain).described_as(f"{value!r}, {other!r}, {tolerance!r}").is_in(None, general)
    if plain is None:
        assert_that(any(type(operand) is int for operand in (value, other, tolerance))).is_true()


_MOMENT = datetime.datetime(2026, 9, 24, 12, 0, 0)
_CLOSE_PAIRS = st.one_of(
    st.tuples(
        st.integers(-20, 20).map(lambda tenths: decimal.Decimal(tenths) / 10),
        _TENTHS,
        _TOLERANCES,
    ),
    st.tuples(
        st.integers(-20, 20).map(lambda tenths: fractions.Fraction(tenths, 10)),
        _TENTHS,
        _TOLERANCES,
    ),
    st.tuples(
        st.integers(-20, 20).map(lambda seconds: _MOMENT + datetime.timedelta(seconds=seconds)),
        st.integers(-20, 20).map(lambda seconds: _MOMENT + datetime.timedelta(seconds=seconds)),
        st.integers(0, 10).map(lambda seconds: datetime.timedelta(seconds=seconds)),
    ),
)


@settings(deadline=None)
@given(pair=_CLOSE_PAIRS)
def test_closeness_is_symmetric_in_every_domain_it_accepts(pair):
    """`Decimal` against a float, a `Fraction`, and a datetime within a `timedelta`: the same answer both ways."""
    value, other, tolerance = pair
    forward = _passes(lambda: assert_that(value).is_close_to(other, tolerance))
    assert_that(_passes(lambda: assert_that(other).is_close_to(value, tolerance))).is_equal_to(forward)
    assert_that(match.close_to(other, tolerance).matches(value)).is_equal_to(forward)


_FINITE = st.one_of(
    _TENTHS,
    st.integers(-(10**400), 10**400),
    st.integers(-20, 20).map(lambda tenths: decimal.Decimal(tenths) / 10),
    st.fractions(max_denominator=10),
)


@settings(deadline=None)
@example(value=1, sign=1, tolerance=float("inf"))
@given(
    value=_FINITE,
    sign=st.sampled_from([1, -1]),
    tolerance=st.one_of(_TOLERANCES, st.just(float("inf")), st.just(decimal.Decimal("Infinity"))),
)
def test_an_infinity_is_close_to_no_finite_value(value, sign, tolerance):
    """Whichever side it is on and however large the tolerance: an infinite one was a wildcard."""
    infinity = sign * float("inf")
    for first, second in ((value, infinity), (infinity, value)):
        answers = {
            "is_close_to": assert_that(first).check().is_close_to(second, tolerance).passed,
            "negated": not assert_that(first).check().is_not_close_to(second, tolerance).passed,
            "matcher": match.close_to(second, tolerance).matches(first),
            "tolerance": assert_that(first).check().is_equal_to(second, tolerance=tolerance).passed,
        }
        assert_that(answers).described_as(f"{first!r} against {second!r}").is_equal_to(dict.fromkeys(answers, False))


_CLASS_LEAVES = st.sampled_from([int, bool, str, bytes, float, list, dict, KeyError, OSError, LookupError, object])
_CLASS_LEAVES |= st.sampled_from([Exception, Hashable, Iterable, Sized, typing.SupportsInt])


@typing.runtime_checkable
class _NamedAtRunTime(typing.Protocol):
    name: str


# its own class, since on 3.10 and 3.11 an `isinstance` against a data protocol fills the ABC negative
# cache, after which `issubclass` answers False from it instead of refusing
@typing.runtime_checkable
class _NamedForIssubclass(typing.Protocol):
    name: str


class _Shadowed(tuple):
    """A tuple whose own iteration shows nothing, where `isinstance` reads the storage."""

    def __iter__(self):
        return iter(())


def _union(members, legacy):
    # the legacy spelling is part of the space
    union = typing.Union[tuple(members)] if legacy else functools.reduce(operator.or_, members)  # noqa: UP007
    # below 3.14 a legacy union, even one `|` made, asks `issubclass(type(x), member)`, which a data protocol refuses
    if sys.version_info < (3, 14) and not isinstance(union, UnionType) and _NamedAtRunTime in typing.get_args(union):
        return functools.reduce(operator.or_, typing.get_args(union))
    return union


def _tuple(members, shadowed):
    return _Shadowed(members) if shadowed else tuple(members)


def _placed_among(one, others):
    return st.builds(
        lambda before, it, after: [*before, it, *after], st.lists(others, max_size=2), one, st.lists(others, max_size=2)
    )


def _unions_of(leaves):
    """Classes and unions of them in both spellings.  A union holds no tuple and flattens what it holds."""
    return st.recursive(
        leaves, lambda inner: st.builds(_union, st.lists(inner, min_size=2, max_size=3), st.booleans()), max_leaves=6
    )


def _class_info(leaves):
    """What `isinstance` takes: unions, and tuples of anything nested to any depth, empty ones included."""
    return st.recursive(
        _unions_of(leaves), lambda inner: st.builds(_tuple, st.lists(inner, max_size=4), st.booleans()), max_leaves=10
    )


def _with_one_bad_member(leaves, bad_in_a_union, bad_in_a_tuple):
    """Class info with exactly one member the check cannot take, at any tuple depth and position.

    Inside a union it is always one level down, since a union flattens whatever it holds.
    """
    in_a_union = st.one_of(
        bad_in_a_union, st.builds(_union, _placed_among(bad_in_a_union, _unions_of(leaves)), st.booleans())
    )
    return st.recursive(
        st.one_of(in_a_union, bad_in_a_tuple),
        lambda inner: st.builds(_tuple, _placed_among(inner, _class_info(leaves)), st.booleans()),
        max_leaves=4,
    )


_GENERICS = st.sampled_from([list[str], dict[str, int], Callable[[int], str]])
_NOT_CLASSES = st.sampled_from(["int", 3])
# a runtime protocol with data members answers `isinstance` and refuses `issubclass`, reliably from 3.12
_ISINSTANCE_LEAVES = _CLASS_LEAVES | st.just(_NamedAtRunTime)
_FOR_ISINSTANCE = _class_info(_ISINSTANCE_LEAVES)
_FOR_ISSUBCLASS = _class_info(_CLASS_LEAVES)
_BAD_FOR_ISINSTANCE = _with_one_bad_member(_ISINSTANCE_LEAVES, _GENERICS, _NOT_CLASSES)
_BAD_FOR_ISSUBCLASS = _with_one_bad_member(
    _CLASS_LEAVES, _GENERICS | st.just(_NamedForIssubclass) if sys.version_info >= (3, 12) else _GENERICS, _NOT_CLASSES
)
_INSTANCES = st.sampled_from(
    [1, True, "s", b"b", 1.5, [1], {"a": 1}, KeyError("k"), OSError("o"), object(), None, SimpleNamespace(name="n")]
)
_CLASSES = st.sampled_from([int, bool, str, bytes, list, dict, KeyError, OSError, ValueError, object, type(None)])
_EXCEPTIONS = st.sampled_from([KeyError, OSError, ValueError, TypeError, LookupError])


def _caught_with(cause_class, root_class):
    def raising():
        cause = cause_class("cause")
        cause.__cause__ = root_class("root")
        raise ValueError("wrapped") from cause

    return assert_that(raising).raises(ValueError).when_called_with()


def _refused(call, message):
    try:
        call()
    except TypeError as error:
        return re.search(message, str(error)) is not None
    except AssertionError:
        return False
    return False


@settings(deadline=None)
@given(
    value=_INSTANCES,
    expected=_FOR_ISINSTANCE,
    before=st.lists(_FOR_ISINSTANCE, max_size=2),
    after=st.lists(_FOR_ISINSTANCE, max_size=2),
)
def test_class_info_is_answered_as_isinstance_answers_it(value, expected, before, after):
    """Reading every member up front leaves the answer to `isinstance`, on every surface that takes class info."""
    answers = {
        "is_instance_of": assert_that(value).check().is_instance_of(expected).passed,
        "negated": not _passes(lambda: assert_that(value).not_.is_instance_of(expected)),
        "matcher": match.is_instance_of(expected).matches(value),
        "is_instance_of_any": assert_that(value).check().is_instance_of_any(*before, expected, *after).passed,
    }
    holds = isinstance(value, expected)
    wanted = {**dict.fromkeys(answers, holds), "is_instance_of_any": isinstance(value, (*before, expected, *after))}
    assert_that(answers).described_as(repr(expected)).is_equal_to(wanted)


@settings(deadline=None)
@given(value=_CLASSES, expected=_FOR_ISSUBCLASS)
def test_class_info_is_answered_as_issubclass_answers_it(value, expected):
    answers = {
        "is_subclass_of": assert_that(value).check().is_subclass_of(expected).passed,
        "negated": not _passes(lambda: assert_that(value).not_.is_subclass_of(expected)),
    }
    holds = issubclass(value, expected)
    assert_that(answers).described_as(repr(expected)).is_equal_to(dict.fromkeys(answers, holds))


@settings(deadline=None)
@given(cause_class=_EXCEPTIONS, root_class=_EXCEPTIONS, expected=_FOR_ISINSTANCE)
def test_a_cause_is_answered_as_isinstance_answers_it(cause_class, root_class, expected):
    answers = {
        "caused_by": _caught_with(cause_class, root_class).check().caused_by(expected).passed,
        "has_root_cause": _caught_with(cause_class, root_class).check().has_root_cause(expected).passed,
    }
    wanted = {
        "caused_by": isinstance(cause_class("cause"), expected),
        "has_root_cause": isinstance(root_class("root"), expected),
    }
    assert_that(answers).described_as(repr(expected)).is_equal_to(wanted)


@settings(deadline=None)
@example(value=1, expected=(list[str], int, str), before=[], after=[])
@example(value=1, expected=(int, list[str], str), before=[], after=[])
@example(value=1, expected=(int, str, list[str]), before=[], after=[])
@example(value=1, expected=int | list[str], before=[object], after=[])
@example(value=1, expected=typing.Union[int, list[str]], before=[], after=[str])  # noqa: UP007  # the legacy spelling is the subject
@given(
    value=_INSTANCES,
    expected=_BAD_FOR_ISINSTANCE,
    before=st.lists(_FOR_ISINSTANCE, max_size=2),
    after=st.lists(_FOR_ISINSTANCE, max_size=2),
)
def test_a_member_isinstance_cannot_take_is_refused_wherever_it_stands(value, expected, before, after):
    """`isinstance` stops at the first member that matches, so a bad one behind it used to decide nothing."""
    refused = {
        "is_instance_of": _refused(lambda: assert_that(value).is_instance_of(expected), "must be a class"),
        "checked": _refused(lambda: assert_that(value).check().is_instance_of(expected), "must be a class"),
        "negated": _refused(lambda: assert_that(value).not_.is_instance_of(expected), "must be a class"),
        "matcher": _refused(lambda: match.is_instance_of(expected), "must be a class"),
        "is_instance_of_any": _refused(
            lambda: assert_that(value).is_instance_of_any(*before, expected, *after), "must be classes"
        ),
    }
    assert_that(refused).described_as(repr(expected)).is_equal_to(dict.fromkeys(refused, True))


@settings(deadline=None)
@example(value=bool, expected=int | list[str])
@example(value=bool, expected=(int, (str, list[str])))
@given(value=_CLASSES, expected=_BAD_FOR_ISSUBCLASS)
def test_a_member_issubclass_cannot_take_is_refused_wherever_it_stands(value, expected):
    refusal = "must be a class|non-method members"
    refused = {
        "is_subclass_of": _refused(lambda: assert_that(value).is_subclass_of(expected), refusal),
        "checked": _refused(lambda: assert_that(value).check().is_subclass_of(expected), refusal),
        "negated": _refused(lambda: assert_that(value).not_.is_subclass_of(expected), refusal),
    }
    assert_that(refused).described_as(repr(expected)).is_equal_to(dict.fromkeys(refused, True))


@settings(deadline=None)
@given(cause_class=_EXCEPTIONS, root_class=_EXCEPTIONS, expected=_BAD_FOR_ISINSTANCE)
def test_a_cause_member_isinstance_cannot_take_is_refused_wherever_it_stands(cause_class, root_class, expected):
    refused = {
        f"{pivot}{mode}": _refused(
            lambda pivot=pivot, mode=mode: getattr(
                _caught_with(cause_class, root_class).check() if mode else _caught_with(cause_class, root_class), pivot
            )(expected),
            "must be a class",
        )
        for pivot in ("caused_by", "has_root_cause")
        for mode in ("", " checked")
    }
    assert_that(refused).described_as(repr(expected)).is_equal_to(dict.fromkeys(refused, True))
