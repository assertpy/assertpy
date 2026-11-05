"""Property-based tests for attrs structural support (Hypothesis).

Mirrors the dataclass/namedtuple invariants for attrs-decorated classes: the structural comparison,
selective ignore (top-level and nested), matches_structure normalization, and the attrs diff branch
must agree with attrs' own equality and survive arbitrary generated instances. The whole module skips
when attrs is not installed.
"""

import copy
import json

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import assert_that, match
from assertpy._snapshot_codec import _decode, _encode
from assertpy.errors import AssertionFailure
from assertpy.pytest_plugin import _format_diff

attrs = pytest.importorskip("attrs")


@attrs.define
class _AttrsInner:
    a: int
    b: str


@attrs.define
class _AttrsOuter:
    inner: _AttrsInner
    items: list[int]
    name: str


@attrs.define
class _KeyedName:
    name: str = attrs.field(eq=str.lower)
    other: int = 0


@attrs.frozen
class _FrozenPair:
    left: int
    right: str


_attrs_inners = st.builds(_AttrsInner, a=st.integers(), b=st.text(max_size=5))
_attrs_outers = st.builds(
    _AttrsOuter, inner=_attrs_inners, items=st.lists(st.integers(), max_size=4), name=st.text(max_size=5)
)


@settings(deadline=None)
@given(left=_attrs_outers, right=_attrs_outers)
def test_attrs_is_equal_to_consistent_with_eq(left, right):
    if left == right:
        assert_that(left).is_equal_to(right)
    else:
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(left).is_equal_to(right)
        diff = exc_info.value.diff
        if diff is not None:
            assert isinstance(_format_diff(diff, color=True), str)


@settings(deadline=None)
@given(value=_attrs_outers)
def test_attrs_is_equal_to_reflexive(value):
    assert_that(value).is_equal_to(copy.deepcopy(value))


@settings(deadline=None)
@given(value=_attrs_outers, new_name=st.text(max_size=5))
def test_attrs_ignore_removes_top_level_field(value, new_name):
    other = attrs.evolve(value, name=new_name)
    assert_that(value).is_equal_to(other, ignore="name")


@settings(deadline=None)
@given(value=_attrs_outers, new_a=st.integers())
def test_attrs_ignore_reaches_into_nested_attrs(value, new_a):
    # a tuple is one nested path, exercising the recursive `attrs.asdict` that shallow filtering got wrong
    other = attrs.evolve(value, inner=attrs.evolve(value.inner, a=new_a))
    assert_that(value).is_equal_to(other, ignore=("inner", "a"))


@settings(deadline=None)
@given(value=_attrs_outers)
def test_attrs_matches_structure_normalizes_instance(value):
    # `StructureMatcher._as_mapping` normalises an attrs instance to its field dict
    assert_that(value).matches_structure(
        {"name": match.is_instance_of(str), "items": match.is_instance_of(list), "inner": match.is_not_none()}
    )


# a few letters in both cases, so two names a key folds together are drawn often
_cased = st.text(alphabet="aAbB", min_size=1, max_size=3)


@settings(deadline=None)
@example(left="A", right="a")
@given(left=_cased, right=_cased)
def test_a_configured_comparison_reads_a_keyed_field_as_equality_does(left, right):
    """Ignoring a field both sides hold equal changes no verdict, whatever the key folds together, and a
    difference is shown as the values held."""
    actual, expected = _KeyedName(left), _KeyedName(right)
    if actual == expected:
        assert_that(actual).is_equal_to(expected, ignore="other")
        assert_that(actual).is_equal_to({"name": left, "other": 0}, ignore="other")
    else:
        with pytest.raises(AssertionFailure) as caught:
            assert_that(actual).is_equal_to(expected, ignore="other")
        assert_that([(entry.actual, entry.expected) for entry in caught.value.diff.entries]).is_equal_to(
            [(left, right)]
        )


@settings(deadline=None)
@given(value=st.one_of(_attrs_outers, st.builds(_FrozenPair, left=st.integers(), right=st.text(max_size=5))))
def test_an_attrs_instance_round_trips_through_the_snapshot_codec(value):
    assert_that(_decode(json.loads(json.dumps(_encode({"v": value}))))["v"]).is_equal_to(value)
