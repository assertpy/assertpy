"""Equality and membership answer where Python's own ``==`` raises instead.

A signalling `Decimal` NaN signals `InvalidOperation` at ``==``, and a `numpy` float overflows converting a Python
int past its range, on its own or inside a list or a mapping.  Every equality and membership assertion let the
exception out.  Each now answers as the pair's plain stand-in does: a signalling NaN as a quiet one, which equals
nothing but itself by identity inside a container, and a `numpy.float32` as the Python `float` it holds.
"""

from __future__ import annotations

import _pydecimal
import collections
import collections.abc
import decimal
import math
import numbers
import operator
import subprocess
import sys
import types

import pytest

from assertpy import assert_that, match
from assertpy._engine import _ordering, _require
from assertpy._engine._membership import occurrences
from assertpy._engine._ordering import (
    _holds_nan,
    broadcasts,
    held_key,
    may_broadcast,
    member,
    mixes_broadcasting,
)
from assertpy._engine._require import pure_decimal_code, raised_inside

_DECIMAL_REFUSES_A_NUMPY_INTEGER = r"argument must be an integer|Cannot convert (np\.int64\(5\)|5) to Decimal"
"""The C `decimal` and the one CPython runs in Python where built without it word this refusal differently."""

_PURE_DECIMAL = bool(pure_decimal_code())
"""Whether `decimal` runs in Python, which reads a registered rational's numerator itself rather than refusing it."""

_ASKED = {
    "is_equal_to": lambda value, other: assert_that(value).check().is_equal_to(other).passed,
    "is_not_equal_to": lambda value, other: assert_that(value).check().is_not_equal_to(other).passed,
    "is_equal_to-list": lambda value, other: assert_that([value]).check().is_equal_to([other]).passed,
    "is_equal_to-dict": lambda value, other: assert_that({"a": value}).check().is_equal_to({"a": other}).passed,
    "is_equal_to-ignore": lambda value, other: (
        assert_that({"a": value, "b": 1}).check().is_equal_to({"a": other, "b": 2}, ignore="b").passed
    ),
    "is_in": lambda value, other: assert_that(value).check().is_in(other, 2).passed,
    "is_not_in": lambda value, other: assert_that(value).check().is_not_in(other, 2).passed,
    "contains": lambda value, other: assert_that([value]).check().contains(other).passed,
    "contains-two": lambda value, other: assert_that([value, 3]).check().contains(other, 3).passed,
    "does_not_contain": lambda value, other: assert_that([value]).check().does_not_contain(other).passed,
    "contains_only": lambda value, other: assert_that([value]).check().contains_only(other).passed,
    "contains_only_once": lambda value, other: assert_that([value]).check().contains_only_once(other).passed,
    "contains_exactly": lambda value, other: assert_that([value]).check().contains_exactly(other).passed,
    "contains_sequence": lambda value, other: assert_that([value, 2]).check().contains_sequence(other, 2).passed,
    "contains_in_order": lambda value, other: assert_that([value, 2]).check().contains_in_order(other, 2).passed,
    "contains_duplicates": lambda value, other: assert_that([value, other]).check().contains_duplicates().passed,
    "does_not_contain_duplicates": lambda value, other: (
        assert_that([value, other]).check().does_not_contain_duplicates().passed
    ),
    "is_subset_of": lambda value, other: assert_that([value]).check().is_subset_of([other]).passed,
    "contains_value": lambda value, other: assert_that({"a": value}).check().contains_value(other).passed,
    "does_not_contain_value": lambda value, other: (
        assert_that({"a": value}).check().does_not_contain_value(other).passed
    ),
    "contains_entry": lambda value, other: assert_that({"a": value}).check().contains_entry({"a": other}).passed,
    "does_not_contain_entry": lambda value, other: (
        assert_that({"a": value}).check().does_not_contain_entry({"a": other}).passed
    ),
    "starts_with": lambda value, other: assert_that([value]).check().starts_with(other).passed,
    "ends_with": lambda value, other: assert_that([value]).check().ends_with(other).passed,
    "match.equal_to": lambda value, other: match.equal_to(other).matches(value),
    "match.is_in": lambda value, other: match.is_in(other, 2).matches(value),
    "match.contains": lambda value, other: match.contains(other).matches([value]),
}


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("counterpart", [1, "same"], ids=["another-value", "the-same-object"])
def test_a_signalling_nan_answers_as_a_quiet_one(asked, counterpart):
    signalling, quiet = decimal.Decimal("sNaN"), decimal.Decimal("NaN")
    other = signalling if counterpart == "same" else counterpart
    stand_in = quiet if counterpart == "same" else counterpart
    assert_that(_ASKED[asked](signalling, other)).is_equal_to(_ASKED[asked](quiet, stand_in))


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("bignum", [10**400, 1], ids=["past-the-float-range", "within-it"])
def test_a_numpy_float_answers_as_the_float_it_holds(asked, bignum):
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"):
        assert_that(_ASKED[asked](numpy.float32(1), bignum)).is_equal_to(_ASKED[asked](1.0, bignum))


def test_a_scalar_numpy_broadcasts_against_a_list_holding_a_signalling_nan_is_unequal():
    numpy = pytest.importorskip("numpy")
    assert_that(assert_that([decimal.Decimal("sNaN"), 1]).check().is_equal_to(numpy.float32(1)).passed).is_false()


def test_a_walk_reads_a_numpy_scalar_against_a_sequence_as_the_verdict_does():
    """A walk asks ``==`` of a pair itself, and `numpy` answers a scalar against a list with an array that is true."""
    numpy = pytest.importorskip("numpy")
    under_a_key_option = assert_that({"a": numpy.int64(5), "b": 1}).check().is_equal_to({"a": [5], "b": 2}, ignore="b")
    assert_that(under_a_key_option.passed).is_false()
    in_a_diff = assert_that([numpy.int64(5), 1]).check().is_equal_to([[5], 2])
    assert_that([entry.path for entry in in_a_diff.diff.entries]).is_equal_to(["[0]", "[1]"])


@pytest.mark.parametrize(
    "ask",
    [
        lambda held, other: assert_that([held]).is_equal_to([other]),
        lambda held, other: assert_that([held]).is_not_equal_to([other]),
        lambda held, other: assert_that({"a": [held], "b": 1}).is_equal_to({"a": [other], "b": 2}, ignore="b"),
    ],
    ids=["equal", "not-equal", "under-a-key-option"],
)
def test_a_frame_that_refuses_its_truth_with_a_type_error_is_named_inside_a_list(ask):
    """`polars` refuses the truth of a frame with a `TypeError`, where `numpy` refuses an array's with `ValueError`."""
    polars = pytest.importorskip("polars")
    with pytest.raises(TypeError, match=r"equal_to\(\) cannot directly compare <DataFrame>"):
        ask(polars.DataFrame({"a": [1, 2]}), polars.DataFrame({"a": [1, 2]}))


@pytest.mark.parametrize(
    "ask",
    [
        lambda value: assert_that(value).is_equal_to(0),
        lambda value: assert_that({"a": value, "b": 1}).is_equal_to({"a": 0, "b": 2}, ignore="b"),
    ],
    ids=["verdict", "walk"],
)
def test_a_refusal_whose_class_cannot_be_asked_comes_out_as_it_was_raised(ask):
    """What handles a refusal is read off its type, as ``except`` reads it: its ``__class__`` is never asked."""

    class InspectedError(OverflowError):
        @property
        def __class__(self):
            raise RuntimeError("class inspected")

    class RefusesEveryone:
        def __eq__(self, other: object) -> bool:
            raise InspectedError("mine")

    try:
        ask(RefusesEveryone())
    except OverflowError as refusal:
        assert_that(type(refusal)).is_same_as(InspectedError)
    else:
        pytest.fail("the refusal of == was answered instead of handed on")


def test_a_signal_ahead_of_an_array_is_answered_as_the_signal():
    """``==`` stopped at the signalling NaN and never asked the array after it, so the array is not what refused."""
    numpy = pytest.importorskip("numpy")
    held = [decimal.Decimal("sNaN"), numpy.array([1, 2])]
    assert_that(held).is_not_equal_to([decimal.Decimal("sNaN"), numpy.array([1, 2])])


class _ListOfItsOwn(list):
    def __eq__(self, other: object) -> bool:
        return list.__eq__(self, other)


class _DictOfItsOwn(dict):
    def __eq__(self, other: object) -> bool:
        return dict.__eq__(self, other)


class _ContainingOfItsOwn:
    """A container whose own `__contains__` raises what it was built with."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __contains__(self, item: object) -> bool:
        raise self.error

    def __iter__(self):
        return iter([1])


class _ArrayShapedSignal:
    """Shaped like an array for the guard in front of `==`, with an `__eq__` of its own that signals."""

    __array__ = None

    def __eq__(self, other: object) -> bool:
        raise decimal.InvalidOperation("my own signal")


class _OverflowingButOrdered:
    """An `__eq__` that overflows in its own code, and an order that calls it equal to anything."""

    def __eq__(self, other: object) -> bool:
        raise OverflowError("my own overflow")

    def __lt__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False


class _InvertedList(list):
    __eq__ = list.__ne__


class _InvertedDict(dict):
    __eq__ = dict.__ne__


@pytest.mark.parametrize(
    ("value", "other"),
    [(_InvertedList([decimal.Decimal("sNaN")]), [1]), (_InvertedDict(a=decimal.Decimal("sNaN")), {"a": 1})],
    ids=["list", "dict"],
)
def test_a_container_whose_equality_is_not_the_built_in_one_is_not_walked(value, other):
    """Written in C but not the built-in `==`, so its elements decide nothing, and the NaN it holds answers."""
    assert_that(assert_that(value).check().is_equal_to(other).passed).is_false()


def test_dicts_whose_keys_differ_after_the_signal_are_unequal():
    """`dict.__eq__` compared a value, which signalled, before it met the key the other lacks."""
    value, other = {"a": decimal.Decimal("sNaN"), "b": 1}, {"a": 1, "c": 1}
    assert_that(assert_that(value).check().is_equal_to(other).passed).is_false()
    assert_that(assert_that(value).check().is_not_equal_to(other).passed).is_true()


@pytest.mark.parametrize(
    ("call", "raised"),
    [
        (lambda: assert_that(_ListOfItsOwn([decimal.Decimal("sNaN")])).is_equal_to([1]), decimal.InvalidOperation),
        (lambda: assert_that(_DictOfItsOwn(a=decimal.Decimal("sNaN"))).is_equal_to({"a": 1}), decimal.InvalidOperation),
        (
            lambda: assert_that(_ContainingOfItsOwn(decimal.InvalidOperation("own"))).contains(1),
            decimal.InvalidOperation,
        ),
        (lambda: assert_that(_ContainingOfItsOwn(OverflowError("own"))).contains(1), OverflowError),
        (lambda: assert_that(_ArrayShapedSignal()).is_equal_to(1, tolerance=0.5), decimal.InvalidOperation),
        (lambda: assert_that(_OverflowingButOrdered()).is_equal_to(1), OverflowError),
        (lambda: assert_that(_SignallingOfItsOwn()).is_equal_to(decimal.Decimal("NaN")), decimal.InvalidOperation),
        (lambda: assert_that([_SignallingOfItsOwn()]).is_equal_to([decimal.Decimal("sNaN")]), decimal.InvalidOperation),
    ],
    ids=[
        "list-with-its-own-eq",
        "dict-with-its-own-eq",
        "contains-signal",
        "contains-overflow",
        "array-guard",
        "ordered",
        "beside-a-quiet-nan",
        "beside-a-signalling-nan",
    ],
)
def test_an_error_raised_in_code_of_the_values_own_is_handed_on(call, raised):
    """Its own `__eq__` or `__contains__`, even one delegating to the built-in, is the value's to answer for."""
    with pytest.raises(raised):
        call()


def test_an_operand_refusal_is_told_apart_beside_a_signal():
    """The bytes' own ints signal against the NaN, and the NaN in the bytes is the operator refusing it."""
    with pytest.raises(TypeError, match="bytes-like"):
        assert_that(b"\x01").contains_only(decimal.Decimal("sNaN"))


@pytest.mark.parametrize(("item", "held"), [(3, True), (4, False), (2, True)])
def test_an_iterator_is_searched_on_from_where_the_signal_stopped_it(item, held):
    """What `in` consumed before the signal compared unequal, and the NaN that signalled equals nothing."""
    assert_that(member(item, iter([2, decimal.Decimal("sNaN"), 3]))).is_equal_to(held)


class _RefusingSet(collections.abc.Set):
    """A set whose own `__contains__` raises `TypeError`, in the very words a hash refusal uses."""

    def __contains__(self, item: object) -> bool:
        raise TypeError("my own refusal: Cannot hash a signaling NaN value")

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


@pytest.mark.parametrize(
    "item",
    [1, (1,), (decimal.Decimal("NaN"),), decimal.Decimal("sNaN"), (decimal.Decimal("sNaN"),)],
    ids=["plain", "tuple", "hashable-nan", "signalling-nan", "tuple-holding-one"],
)
def test_a_sets_own_refusal_of_a_hashable_item_is_handed_on(item):
    """Answered as absent only where the set's refusal is the item's own refusal to hash, as a NaN's is."""
    with pytest.raises(TypeError, match="my own refusal"):
        member(item, _RefusingSet())


class _RefusingMapping(collections.abc.Mapping):
    """A mapping whose own lookup raises `TypeError` in the very words a hash refusal uses."""

    def __getitem__(self, key: object) -> object:
        raise TypeError("Cannot hash a signaling NaN value")

    def __contains__(self, key: object) -> bool:
        raise TypeError("Cannot hash a signaling NaN value")

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


def _user_dict_over(mapping: object) -> collections.UserDict:
    held = collections.UserDict()
    held.data = mapping  # ty: ignore[invalid-assignment]  # the path a trusted lookup must not assume is a dict
    return held


@pytest.mark.parametrize(
    "container",
    [
        lambda: _user_dict_over(_RefusingMapping()),
        lambda: collections.abc.KeysView(_RefusingMapping()),
        lambda: collections.abc.KeysView(_user_dict_over(_RefusingMapping())),
    ],
    ids=["user-dict-over-a-mapping", "keys-view-over-a-mapping", "keys-view-over-that-user-dict"],
)
def test_a_lookup_that_does_not_end_in_a_built_in_one_hands_its_refusal_on(container):
    """The path is followed down to a built-in dict, and a mapping of anybody's saying the same words is not one."""
    with pytest.raises(TypeError, match="Cannot hash"):
        member(decimal.Decimal("sNaN"), container())


def test_a_user_dicts_items_view_hands_the_hash_refusal_on_as_python_does():
    """The recorded boundary: the view looks a key up through `__getitem__`, whose path is not followed."""
    with pytest.raises(TypeError):
        member((decimal.Decimal("sNaN"), 1), collections.UserDict(a=1).items())


def test_a_container_that_holds_itself_is_searched_for_a_nan_once():
    looped: list = [1]
    looped.append(looped)
    mapping: dict = {"a": 1}
    mapping["self"] = mapping
    assert_that(_holds_nan(looped)).is_false()
    assert_that(_holds_nan(mapping)).is_false()
    looped.append(decimal.Decimal("sNaN"))
    assert_that(_holds_nan(looped)).is_true()


_HASHED_ASKED = {
    "set-contains": lambda nan: assert_that({1, 2}).check().contains(nan).passed,
    "set-does_not_contain": lambda nan: assert_that({1, 2}).check().does_not_contain(nan).passed,
    "dict-contains": lambda nan: assert_that({"a": 1}).check().contains(nan).passed,
    "contains_key": lambda nan: assert_that({"a": 1}).check().contains_key(nan).passed,
    "does_not_contain_key": lambda nan: assert_that({"a": 1}).check().does_not_contain_key(nan).passed,
    "set-contains_only": lambda nan: assert_that({1}).check().contains_only(nan).passed,
    "set-is_subset_of": lambda nan: assert_that([nan]).check().is_subset_of({1, 2}).passed,
    "match.contains-set": lambda nan: match.contains(nan).matches({1, 2}),
    "match.is_in-frozenset": lambda nan: match.is_in(frozenset({1})).matches(nan),
}


@pytest.mark.parametrize(
    "asked",
    [
        lambda nan: member((nan,), {(1,)}),
        lambda nan: member((nan, 1), {"a": 1}.keys()),
        lambda nan: member((nan, 1), {"a": 1}.items()),
        lambda nan: member(("a", nan), {"a": 1}.items()),
        lambda nan: member(((nan,),), {(1,)}),
        lambda nan: member((nan, []), {"a": 1}.items()),
        lambda nan: member(nan, collections.UserDict(a=1)),
        lambda nan: member(nan, collections.UserDict(a=1).keys()),
    ],
    ids=[
        "tuple-in-set",
        "tuple-in-keys",
        "key-in-items",
        "value-in-items",
        "nested-tuple",
        "key-beside-an-unhashable-value-in-items",
        "user-dict",
        "user-dict-keys",
    ],
)
def test_a_hashed_container_holds_no_tuple_holding_a_signalling_nan(asked):
    assert_that(asked(decimal.Decimal("sNaN"))).is_equal_to(asked(decimal.Decimal("NaN")))


@pytest.mark.parametrize(
    "probe",
    [
        lambda nan: ({"a": nan},),
        lambda nan: ([nan],),
        lambda nan: (collections.UserDict(a=nan),),
        lambda nan: (nan, [1]),
        lambda nan: ([1], nan),
    ],
    ids=["dict", "list", "user-dict", "nan-then-list", "list-then-nan"],
)
def test_a_probe_unhashable_without_the_nan_is_refused_as_a_quiet_one_is(probe):
    """A list or a mapping in a tuple refuses to hash whatever it holds, so the NaN changes nothing."""
    for nan in (decimal.Decimal("sNaN"), decimal.Decimal("NaN")):
        with pytest.raises(TypeError):
            member(probe(nan), {(1,)})


@pytest.mark.parametrize("asked", list(_HASHED_ASKED))
def test_a_hashed_container_holds_no_signalling_nan(asked):
    """A signalling NaN refuses to hash, so a set or a mapping's keys cannot hold one, and the answer says so."""
    signalling, quiet = decimal.Decimal("sNaN"), decimal.Decimal("NaN")
    assert_that(_HASHED_ASKED[asked](signalling)).is_equal_to(_HASHED_ASKED[asked](quiet))


@pytest.mark.parametrize("asked", list(_ASKED))
def test_a_signalling_nan_on_the_other_side_answers_as_a_quiet_one(asked):
    """Rich comparison dispatches from the left, so the NaN is asked from the argument's side as well."""
    assert_that(_ASKED[asked](1, decimal.Decimal("sNaN"))).is_equal_to(_ASKED[asked](1, decimal.Decimal("NaN")))


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("bignum", [10**400, 1], ids=["past-the-float-range", "within-it"])
def test_a_bignum_against_a_numpy_float_answers_as_against_the_float_it_holds(asked, bignum):
    numpy = pytest.importorskip("numpy")
    with numpy.errstate(all="ignore"):
        assert_that(_ASKED[asked](bignum, numpy.float32(1))).is_equal_to(_ASKED[asked](bignum, 1.0))


def _decimal_and_int64(text: str, *, decimal_first: bool) -> tuple[list[object], list[object]]:
    """The pair of a `Decimal` and a `numpy.int64(5)`, and the same pair with a Python ``5`` standing in."""
    numpy = pytest.importorskip("numpy")
    pair, stand_in = [decimal.Decimal(text), numpy.int64(5)], [decimal.Decimal(text), 5]
    if not decimal_first:
        pair.reverse()
        stand_in.reverse()
    return pair, stand_in


@pytest.mark.parametrize("asked", list(_ASKED))
@pytest.mark.parametrize("text", ["5", "1.5"], ids=["equal", "apart"])
@pytest.mark.parametrize("decimal_first", [True, False], ids=["decimal-first", "int64-first"])
def test_a_decimal_against_a_numpy_integer_answers_as_against_the_int_it_holds(asked, text, decimal_first):
    """The `Decimal` reads the integer's numerator, a `numpy` one, and raises `TypeError` rather than answering."""
    pair, stand_in = _decimal_and_int64(text, decimal_first=decimal_first)
    assert_that(_ASKED[asked](*pair)).is_equal_to(_ASKED[asked](*stand_in))


_HOLDERS_ASKED = {
    "set-contains": lambda held, item: assert_that({held}).check().contains(item).passed,
    "set-does_not_contain": lambda held, item: assert_that({held}).check().does_not_contain(item).passed,
    "set-contains_only": lambda held, item: assert_that({held}).check().contains_only(item).passed,
    "set-is_subset_of": lambda held, item: assert_that([item]).check().is_subset_of({held}).passed,
    "contains_key": lambda held, item: assert_that({held: 1}).check().contains_key(item).passed,
    "keys-contains": lambda held, item: assert_that({held: 1}.keys()).check().contains(item).passed,
    "items-contains": lambda held, item: assert_that({held: 1}.items()).check().contains((item, 1)).passed,
    "deque-contains": lambda held, item: assert_that(collections.deque([held])).check().contains(item).passed,
    "match.contains-set": lambda held, item: match.contains(item).matches({held}),
}


@pytest.mark.parametrize("asked", list(_HOLDERS_ASKED))
@pytest.mark.parametrize("text", ["5", "1.5"], ids=["equal", "apart"])
@pytest.mark.parametrize("decimal_held", [True, False], ids=["decimal-held", "int64-held"])
def test_a_set_or_a_deque_searched_for_a_decimal_against_a_numpy_integer_answers(asked, text, decimal_held):
    """Equal hashes lead a set to compare the pair, and a deque compares every element, where the `Decimal` raises."""
    (held, item), (held_stand_in, item_stand_in) = _decimal_and_int64(text, decimal_first=decimal_held)
    expected = _HOLDERS_ASKED[asked](held_stand_in, item_stand_in)
    assert_that(_HOLDERS_ASKED[asked](held, item)).is_equal_to(expected)


@pytest.mark.parametrize(
    "asked",
    [
        lambda held, item: assert_that({held}).contains(item, [1]),
        lambda held, item: assert_that({held}).contains_only(item, [1]),
    ],
    ids=["contains", "contains_only"],
)
def test_the_refusal_named_after_a_pair_a_decimal_refuses_is_the_item_refused(asked):
    """Asked again one item at a time, the `Decimal` refused ahead of the list, which is what the set refuses."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError, match="unhashable type: 'list'"):
        asked(decimal.Decimal(5), numpy.int64(5))


@pytest.mark.parametrize("asked", [match.contains, match.contains_only], ids=["contains", "contains_only"])
def test_a_matcher_reads_the_refusal_after_a_pair_a_decimal_refuses_as_no_match(asked):
    numpy = pytest.importorskip("numpy")
    assert_that(asked(numpy.int64(5), [1]).matches({decimal.Decimal(5)})).is_false()


class _EqualityBrokenInside:
    """An `__eq__` of its own that raises `TypeError`, met through a hash equal to the probe's."""

    def __eq__(self, other: object) -> bool:
        raise TypeError("my own __eq__")

    def __hash__(self) -> int:
        return 7


class _CountedHash:
    """Hashes as `_EqualityBrokenInside` does, counting how often it is asked."""

    def __init__(self) -> None:
        self.asked = 0

    def __hash__(self) -> int:
        self.asked += 1
        return 7


class _CountOfItsOwn(collections.UserList):
    """A sequence whose own `count` raises `TypeError`."""

    def count(self, item: object) -> int:
        raise TypeError("my own count")


def test_an_error_raised_inside_a_sequences_own_count_is_handed_on():
    """Counted element by element only where `count` itself refused a pair, as `member` searches."""
    with pytest.raises(TypeError, match="my own count"):
        occurrences(_CountOfItsOwn([[1]]), [[1]])


def test_an_error_raised_inside_a_hashed_lookup_is_handed_on_before_the_key_is_hashed_again():
    probe = _CountedHash()
    with pytest.raises(TypeError, match="my own __eq__"):
        member(probe, {_EqualityBrokenInside()})
    assert_that(probe.asked).is_equal_to(1)


class _RationalOfItsOwn:
    """Registered as a rational, with a numerator a `Decimal` refuses and no exact value to answer by."""

    numerator = 1.5
    denominator = 1


class _IntegralOfItsOwn:
    """Registered as an integral, with a numerator a `Decimal` refuses and a conversion of its own to 5."""

    numerator = 1.5
    denominator = 1

    def __index__(self) -> int:
        return 5

    __int__ = __index__


numbers.Rational.register(_RationalOfItsOwn)
numbers.Integral.register(_IntegralOfItsOwn)


@pytest.mark.parametrize("refused", [_RationalOfItsOwn, _IntegralOfItsOwn])
@pytest.mark.parametrize(
    "asked", ["is_equal_to", "is_equal_to-list", "contains", "is_in", "match.equal_to", "starts_with"]
)
def test_a_refusal_with_no_exact_value_to_answer_by_is_handed_on(asked, refused):
    """Only `int`'s own or a `numpy` integer's conversion is read: the value's own could answer anything.

    Where `decimal` runs in Python its `==` reads the numerator itself and answers, and so does the library.
    """
    if _PURE_DECIMAL:
        assert_that(_ASKED[asked](decimal.Decimal(5), refused())).is_false()
        return
    with pytest.raises(TypeError, match="argument must be an integer"):
        _ASKED[asked](decimal.Decimal(5), refused())


@pytest.mark.parametrize("refused", [_RationalOfItsOwn, _IntegralOfItsOwn])
def test_a_pair_with_no_exact_value_to_order_by_is_left_unordered(refused):
    if _PURE_DECIMAL:
        assert_that(assert_that(decimal.Decimal(5)).check().is_less_than(refused()).passed).is_false()
        return
    with pytest.raises(TypeError, match="must be comparable"):
        assert_that(decimal.Decimal(5)).is_less_than(refused())


class _SignallingOfItsOwn:
    """An `__eq__` that raises `InvalidOperation` of its own, with no NaN anywhere in the pair."""

    def __eq__(self, other: object) -> bool:
        raise decimal.InvalidOperation("my own signal")

    __hash__ = object.__hash__


class _OverflowingOfItsOwn:
    """An `__eq__` that overflows in its own code."""

    def __eq__(self, other: object) -> bool:
        raise OverflowError("my own overflow")

    __hash__ = object.__hash__


@pytest.mark.parametrize(
    ("value", "raised"),
    [(_SignallingOfItsOwn(), decimal.InvalidOperation), (_OverflowingOfItsOwn(), OverflowError)],
    ids=["signal", "overflow"],
)
@pytest.mark.parametrize("asked", ["is_equal_to", "is_equal_to-list", "contains", "is_in", "match.equal_to"])
def test_an_error_of_the_values_own_equality_is_handed_on(value, raised, asked):
    """Only a NaN, or a number overflowing its own conversion, makes the raise an answer."""
    with pytest.raises(raised, match="my own"):
        _ASKED[asked](value, 1)


_KEYED_ASKED = {
    "is_equal_to-set": lambda held, item: assert_that({held}).check().is_equal_to({item}).passed,
    "is_equal_to-frozenset": lambda held, item: assert_that(frozenset({held})).check().is_equal_to({item}).passed,
    "is_equal_to-frozensets": lambda held, item: (
        assert_that(frozenset({held})).check().is_equal_to(frozenset({item})).passed
    ),
    "is_equal_to-set-frozenset": lambda held, item: assert_that({held}).check().is_equal_to(frozenset({item})).passed,
    "is_equal_to-frozensets-and-more": lambda held, item: (
        assert_that(frozenset({held, 1})).check().is_equal_to(frozenset({item, 2})).passed
    ),
    "is_not_equal_to-set": lambda held, item: assert_that({held}).check().is_not_equal_to({item}).passed,
    "is_equal_to-keys": lambda held, item: assert_that({held: 1}).check().is_equal_to({item: 1}).passed,
    "is_equal_to-values-differ": lambda held, item: assert_that({held: 1}).check().is_equal_to({item: 2}).passed,
    "is_not_equal_to-keys": lambda held, item: assert_that({held: 1}).check().is_not_equal_to({item: 1}).passed,
    "is_equal_to-set-and-more": lambda held, item: assert_that({held, 1}).check().is_equal_to({item, 2}).passed,
    "is_equal_to-keys-and-more": lambda held, item: (
        assert_that({held: 1, "x": 3}).check().is_equal_to({item: 2, "y": 3}).passed
    ),
    "is_equal_to-strict-keys": lambda held, item: (
        assert_that({held: 1}).check().is_equal_to({item: 1}, strict_types=True).passed
    ),
    "ignore-and-fail": lambda held, item: (
        assert_that({held: 1, "b": 2}).check().is_equal_to({item: 9, "b": 3}, ignore="b").passed
    ),
    "is_equal_to-nested": lambda held, item: assert_that([{"a": {held}}]).check().is_equal_to([{"a": {item}}]).passed,
    "is_less_than_or_equal_to-set": lambda held, item: (
        assert_that({held}).check().is_less_than_or_equal_to({item}).passed
    ),
    "is_greater_than_or_equal_to-set": lambda held, item: (
        assert_that({held}).check().is_greater_than_or_equal_to({item}).passed
    ),
    "is_in-set": lambda held, item: assert_that({held}).check().is_in({item}, 2).passed,
    "is_in-keys": lambda held, item: assert_that({held: 1}).check().is_in({item: 1}, 2).passed,
    "contains_entry": lambda held, item: assert_that({held: 1}).check().contains_entry({item: 1}).passed,
    "does_not_contain_entry": lambda held, item: (
        assert_that({held: 1}).check().does_not_contain_entry({item: 1}).passed
    ),
    "is_subset_of-keys": lambda held, item: assert_that({item: 1}).check().is_subset_of({held: 1}).passed,
    "matches_structure": lambda held, item: assert_that({held: 1}).check().matches_structure({item: 1}).passed,
    "match.equal_to-keys": lambda held, item: match.equal_to({item: 1}).matches({held: 1}),
    "contains-mapping-in-list": lambda held, item: (
        assert_that([{held: 1, "a": 2}]).check().contains({item: 2, "a": 2}).passed
    ),
    "ignore": lambda held, item: (
        assert_that({held: 1, "b": 2}).check().is_equal_to({item: 9, "b": 2}, ignore=item).passed
    ),
    "include": lambda held, item: (
        assert_that({held: 1, "b": 2}).check().is_equal_to({item: 1, "b": 3}, include=item).passed
    ),
    "ordered": lambda held, item: (
        assert_that(collections.OrderedDict([(held, 1), ("b", 2)]))
        .check()
        .is_equal_to(collections.OrderedDict([(item, 1), ("b", 2)]))
        .passed
    ),
}


@pytest.mark.parametrize("asked", list(_KEYED_ASKED))
@pytest.mark.parametrize("text", ["5", "1.5"], ids=["equal", "apart"])
@pytest.mark.parametrize("decimal_held", [True, False], ids=["decimal-held", "int64-held"])
def test_a_decimal_and_a_numpy_integer_as_keys_or_elements_answer_as_the_int_does(asked, text, decimal_held):
    """Equal hashes lead a set or a dict to compare the pair, where the `Decimal` raises rather than answering."""
    (held, item), (held_stand_in, item_stand_in) = _decimal_and_int64(text, decimal_first=decimal_held)
    expected = _KEYED_ASKED[asked](held_stand_in, item_stand_in)
    assert_that(_KEYED_ASKED[asked](held, item)).is_equal_to(expected)


class _InvertedSet(set):
    __eq__ = set.__ne__


def test_a_set_whose_equality_is_not_the_built_in_one_hands_its_refusal_on():
    """Its elements decide nothing, so the `Decimal`'s refusal of the `numpy` integer is the answer's to give."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError, match=_DECIMAL_REFUSES_A_NUMPY_INTEGER):
        assert_that(_InvertedSet({numpy.int64(5)})).is_equal_to({decimal.Decimal(5)})


_ABSENT_KEY_ASKED = {
    "is_subset_of": lambda held, key: assert_that({key: 1}).check().is_subset_of({held: 1}).passed,
    "matches_structure": lambda held, key: assert_that({held: 1}).check().matches_structure({key: 1}).passed,
    "contains_entry": lambda held, key: assert_that({held: 1}).check().contains_entry({key: 1}).passed,
    "does_not_contain_entry": lambda held, key: assert_that({held: 1}).check().does_not_contain_entry({key: 1}).passed,
    "is_equal_to-keys": lambda held, key: assert_that({held: 1}).check().is_equal_to({key: 1}).passed,
    "is_equal_to-set": lambda held, key: assert_that({held}).check().is_equal_to({key}).passed,
    "contains-set": lambda held, key: assert_that({held}).check().contains(key).passed,
}
_BEYOND = 314159 + (2**61 - 1) * 10**400
"""A Python int past the float range whose hash is an infinity's, which `numpy` overflows converting to compare."""


@pytest.mark.parametrize("asked", list(_ABSENT_KEY_ASKED))
@pytest.mark.parametrize("collision", ["decimal-int64", "float32-bignum"])
@pytest.mark.parametrize("numpy_held", [True, False], ids=["numpy-held", "numpy-asked"])
def test_a_key_whose_hash_collides_with_one_it_does_not_equal_is_absent(asked, collision, numpy_held):
    """An equal hash leads the lookup to compare the two, and the comparison may raise instead of answering no.

    `numpy.int64(2**61 - 1)` hashes to 0 as `Decimal(0)` does, where the `Decimal` refuses the integer (a held
    `numpy.int64` answers for itself), and a `numpy.float32` infinity hashes as `_BEYOND` does, which `numpy`
    overflows converting either way round.
    """
    numpy = pytest.importorskip("numpy")
    kinds = {
        "decimal-int64": (numpy.int64(2**61 - 1), decimal.Decimal(0), 2**61 - 1),
        "float32-bignum": (numpy.float32("inf"), _BEYOND, math.inf),
    }
    numpy_side, other, stand_in = kinds[collision]
    pair, plain = (numpy_side, other), (stand_in, other)
    if not numpy_held:
        pair, plain = pair[::-1], plain[::-1]
    assert_that(_ABSENT_KEY_ASKED[asked](*pair)).is_equal_to(_ABSENT_KEY_ASKED[asked](*plain))


class _EqualityCountedRaising:
    """A value whose own `__eq__` raises `TypeError`, counting how often it is asked."""

    def __init__(self) -> None:
        self.asked = 0

    def __eq__(self, other: object) -> bool:
        self.asked += 1
        raise TypeError("my own __eq__")

    __hash__ = object.__hash__


@pytest.mark.parametrize(
    "asked",
    [
        lambda value: assert_that({"a": value}).contains_entry({"a": 1}),
        lambda value: assert_that({"a": value}).does_not_contain_entry({"a": 1}),
        lambda value: assert_that({"a": value}).is_subset_of({"a": 1}),
        lambda value: assert_that({"a": 1}).matches_structure({"a": value}),
    ],
    ids=["contains_entry", "does_not_contain_entry", "is_subset_of", "matches_structure"],
)
def test_an_error_of_a_values_own_equality_is_handed_on_once_and_not_taken_for_a_key_refusal(asked):
    value = _EqualityCountedRaising()
    with pytest.raises(TypeError, match="my own __eq__"):
        asked(value)
    assert_that(value.asked).is_equal_to(1)


def test_a_key_is_searched_past_a_refusal_only_in_a_container_searched_by_hash():
    """Elsewhere the key held cannot be read back through identity, so the refusal is the answer's to give."""
    numpy = pytest.importorskip("numpy")
    assert_that(held_key({decimal.Decimal(5)}, numpy.int64(5))).is_equal_to((True, decimal.Decimal(5)))
    with pytest.raises(TypeError, match=_DECIMAL_REFUSES_A_NUMPY_INTEGER):
        held_key([decimal.Decimal(5)], numpy.int64(5))


class _SpecCounted:
    """An ignore-spec whose own `__eq__` counts how often it is asked, and names no key."""

    def __init__(self) -> None:
        self.asked = 0

    def __eq__(self, other: object) -> bool:
        self.asked += 1
        return False

    __hash__ = object.__hash__


@pytest.mark.parametrize("ignore_first", [True, False], ids=["counted-first", "counted-last"])
def test_a_spec_that_refuses_the_key_asks_no_other_spec_again(ignore_first):
    """The `Decimal` refuses the `numpy` key, and every other spec is asked as often as beside a spec that does not."""
    numpy = pytest.importorskip("numpy")
    value, other = {numpy.int64(5): 1, "b": 2}, {numpy.int64(5): 9, "b": 2}
    asked = []
    for last in (decimal.Decimal(5), 5):
        counted = _SpecCounted()
        specs = [counted, last] if ignore_first else [last, counted]
        assert_that(value).is_equal_to(other, ignore=specs)
        asked.append(counted.asked)
    assert_that(asked[0]).is_equal_to(asked[1])


class _RefusingInC:
    """A key whose `__eq__` is C code of another type's, so it refuses with no frame of its own below the lookup."""

    __eq__ = int.__add__

    def __hash__(self) -> int:
        return 0


_REFUSED_KEY_ASKED = {
    "contains_key": lambda key: assert_that({0: 1}).contains_key(key),
    "contains_entry": lambda key: assert_that({0: 1}).contains_entry({key: 1}),
    "does_not_contain_entry": lambda key: assert_that({0: 1}).does_not_contain_entry({key: 1}),
    "is_subset_of": lambda key: assert_that({key: 1}).is_subset_of({0: 1}),
    "matches_structure": lambda key: assert_that({0: 1}).matches_structure({key: 1}),
    "is_equal_to-keys": lambda key: assert_that({0: 1}).is_equal_to({key: 1}),
    "is_equal_to-set": lambda key: assert_that({0}).is_equal_to({key}),
    "contains-set": lambda key: assert_that({0}).contains(key),
    "is_in": lambda key: assert_that(key).is_in({0}, 2),
    "ignore": lambda key: assert_that({0: 1, "b": 2}).is_equal_to({0: 1, "b": 3}, ignore=key),
}


@pytest.mark.parametrize("asked", list(_REFUSED_KEY_ASKED))
def test_a_key_refusing_in_c_code_of_its_own_is_handed_on_not_answered(asked):
    """The search past a refusal asks `equals`, which answers only numbers it reads exactly; this one it hands on."""
    with pytest.raises(TypeError, match="descriptor '__add__'"):
        _REFUSED_KEY_ASKED[asked](_RefusingInC())


_BROADCAST_ASKED = {
    "is_equal_to": lambda scalar, sequence: assert_that(scalar).check().is_equal_to(sequence).passed,
    "is_equal_to-swapped": lambda scalar, sequence: assert_that(sequence).check().is_equal_to(scalar).passed,
    "is_not_equal_to": lambda scalar, sequence: assert_that(scalar).check().is_not_equal_to(sequence).passed,
    "match.equal_to": lambda scalar, sequence: match.equal_to(sequence).matches(scalar),
    "match.equal_to-swapped": lambda scalar, sequence: match.equal_to(scalar).matches(sequence),
    "is_in": lambda scalar, sequence: assert_that(scalar).check().is_in(sequence, 7).passed,
    "is_in-swapped": lambda scalar, sequence: assert_that(sequence).check().is_in(scalar, 7).passed,
    "is_not_in": lambda scalar, sequence: assert_that(scalar).check().is_not_in(sequence, 7).passed,
    "match.is_in": lambda scalar, sequence: match.is_in(sequence, 7).matches(scalar),
    "match.is_in-swapped": lambda scalar, sequence: match.is_in(scalar, 7).matches(sequence),
    "contains": lambda scalar, sequence: assert_that([scalar, 7]).check().contains(sequence).passed,
    "contains-swapped": lambda scalar, sequence: assert_that([sequence, 7]).check().contains(scalar).passed,
    "contains-two": lambda scalar, sequence: assert_that([scalar, 7]).check().contains(sequence, 7).passed,
    "does_not_contain": lambda scalar, sequence: assert_that([scalar]).check().does_not_contain(sequence).passed,
    "match.contains": lambda scalar, sequence: match.contains(sequence).matches([scalar]),
    "contains_only": lambda scalar, sequence: assert_that([scalar, 7]).check().contains_only(sequence, 7).passed,
    "contains_only-swapped": lambda scalar, sequence: (
        assert_that([sequence, 7]).check().contains_only(scalar, 7).passed
    ),
    "contains_only_once": lambda scalar, sequence: assert_that([scalar]).check().contains_only_once(sequence).passed,
    "contains_sequence": lambda scalar, sequence: (
        assert_that([scalar, 7]).check().contains_sequence(sequence, 7).passed
    ),
    "contains_value": lambda scalar, sequence: assert_that({"a": scalar}).check().contains_value(sequence).passed,
    "is_subset_of": lambda scalar, sequence: assert_that([sequence]).check().is_subset_of([scalar, 7]).passed,
    "contains_duplicates": lambda scalar, sequence: (
        assert_that([scalar, sequence]).check().contains_duplicates().passed
    ),
    "starts_with": lambda scalar, sequence: assert_that([scalar, 7]).check().starts_with(sequence).passed,
    "ends_with": lambda scalar, sequence: assert_that([7, scalar]).check().ends_with(sequence).passed,
}


_SCALAR_KINDS = {"int64": 5, "float32": 5.0, "float64": 5.0, "bool_": True, "str_": "5"}
_SEQUENCE_SHAPES = {
    "empty": lambda plain: [],
    "one-element": lambda plain: [plain],
    "tuple": lambda plain: (plain,),
    "two-elements": lambda plain: [plain, plain],
}


@pytest.mark.parametrize("asked", list(_BROADCAST_ASKED))
@pytest.mark.parametrize("kind", list(_SCALAR_KINDS))
@pytest.mark.parametrize("shape", list(_SEQUENCE_SHAPES))
def test_a_numpy_scalar_against_a_list_is_unequal_as_the_value_it_holds_is(asked, kind, shape):
    """`numpy` compares a scalar with a sequence element by element: true for one equal element, raising on the
    truth of several, and on none, where numpy 1 only warns; the library asked that pair itself, and a Python
    value is simply unequal to a list.
    """
    numpy = pytest.importorskip("numpy")
    plain = _SCALAR_KINDS[kind]
    sequence = _SEQUENCE_SHAPES[shape](plain)
    scalar = getattr(numpy, kind)(plain)
    assert_that(_BROADCAST_ASKED[asked](scalar, sequence)).is_equal_to(_BROADCAST_ASKED[asked](plain, sequence))


@pytest.mark.parametrize("sequence", [[5], (5,)], ids=["list", "tuple"])
def test_the_failure_of_a_numpy_scalar_against_a_sequence_does_not_call_them_equal(sequence):
    """The hint used to read numpy's array for the pair as equal values and name only their types."""
    numpy = pytest.importorskip("numpy")
    message = assert_that(numpy.int64(5)).check().is_equal_to(sequence).message
    assert_that(message).does_not_contain("only their types differ")


class _Values(list):
    """A list that keeps the built-in search and iteration."""


def test_a_list_subclass_keeping_the_built_in_search_is_searched_past_a_broadcast():
    numpy = pytest.importorskip("numpy")
    assert_that(assert_that(_Values([numpy.int64(5)])).check().contains([5]).passed).is_false()
    assert_that(assert_that(_Values([[5]])).check().contains(numpy.int64(5)).passed).is_false()


_HELD = (0, 1)
"""A tuple whose hash an `int64` holds and hashes to as well, so a lookup of one meets the other and compares them."""

_COLLISION_ASKED = {
    "contains-set": lambda key: assert_that({_HELD}).check().contains(key).passed,
    "is_in-set": lambda key: assert_that(key).check().is_in({_HELD}).passed,
    "contains_only-set": lambda key: assert_that({_HELD}).check().contains_only(key).passed,
    "is_equal_to-set": lambda key: assert_that({_HELD}).check().is_equal_to({key}).passed,
    "contains_entry": lambda key: assert_that({_HELD: 1}).check().contains_entry({key: 1}).passed,
    "does_not_contain_entry": lambda key: assert_that({_HELD: 1}).check().does_not_contain_entry({key: 1}).passed,
    "is_equal_to": lambda key: assert_that({_HELD: 1}).check().is_equal_to({key: 1}).passed,
    "is_equal_to-swapped": lambda key: assert_that({key: 1}).check().is_equal_to({_HELD: 1}).passed,
    "is_equal_to-ignore": lambda key: (
        assert_that({_HELD: 1, "a": 2}).check().is_equal_to({key: 1, "a": 3}, ignore="a").passed
    ),
    "is_subset_of": lambda key: assert_that({key: 1}).check().is_subset_of({_HELD: 1}).passed,
    "is_subset_of-swapped": lambda key: assert_that({_HELD: 1}).check().is_subset_of({key: 1}).passed,
    "match.equal_to": lambda key: match.equal_to({key: 1}).matches({_HELD: 1}),
    "matches_structure": lambda key: assert_that({_HELD: 1}).check().matches_structure({key: 1}).passed,
}


@pytest.mark.parametrize("asked", list(_COLLISION_ASKED))
def test_a_hash_collision_between_a_numpy_scalar_and_a_tuple_answers_as_the_int_does(asked):
    numpy = pytest.importorskip("numpy")
    colliding = numpy.int64(hash(_HELD))
    assert_that(hash(colliding)).is_equal_to(hash(_HELD))
    expected = _COLLISION_ASKED[asked](hash(_HELD))
    assert_that(_COLLISION_ASKED[asked](colliding)).is_equal_to(expected)


def test_a_one_shot_value_is_read_once_where_a_scalar_meets_a_list():
    numpy = pytest.importorskip("numpy")
    passed = assert_that(value for value in [numpy.int64(5), 2]).check().contains_only([5], 2).passed
    assert_that(passed).is_equal_to(assert_that(value for value in [5, 2]).check().contains_only([5], 2).passed)


@pytest.mark.parametrize(
    "asked",
    [
        lambda scalar: assert_that([scalar]).check().contains_exactly([5]).passed,
        lambda scalar: assert_that([scalar]).check().is_equal_to([[5]]).passed,
        lambda scalar: assert_that({"a": scalar}).check().is_equal_to({"a": [5]}).passed,
    ],
    ids=["contains_exactly", "list-of-lists", "dict-values"],
)
def test_a_numpy_scalar_meeting_a_list_inside_a_containers_own_comparison_is_numpys_answer(asked):
    """The recorded boundary: two containers compared by their own C `==` take the truth of numpy's array."""
    numpy = pytest.importorskip("numpy")
    assert_that(asked(numpy.int64(5))).is_true()


_RAISED_INSIDE_ASKED = {
    "is_equal_to": lambda scalar: assert_that([scalar]).check().is_equal_to([[5, 6]]).passed,
    "is_equal_to-swapped": lambda scalar: assert_that([[5, 6]]).check().is_equal_to([scalar]).passed,
    "dict-values": lambda scalar: assert_that({"a": scalar}).check().is_equal_to({"a": [5, 6]}).passed,
    "match.equal_to": lambda scalar: match.equal_to({"a": [5, 6]}).matches({"a": scalar}),
    "contains_exactly": lambda scalar: assert_that([scalar]).check().contains_exactly([5, 6]).passed,
    "contains_duplicates": lambda scalar: assert_that([[scalar], [[5, 6]]]).check().contains_duplicates().passed,
    "does_not_contain_duplicates": lambda scalar: (
        assert_that([[scalar], [[5, 6]]]).check().does_not_contain_duplicates().passed
    ),
    "contains_only_once": lambda scalar: assert_that([[scalar], [[5, 6]]]).check().contains_only_once([[5, 6]]).passed,
    "contains_only_once-swapped": lambda scalar: (
        assert_that([[[5, 6]], [scalar]]).check().contains_only_once([scalar]).passed
    ),
    "contains_exactly_in_any_order": lambda scalar: (
        assert_that([[scalar]]).check().contains_exactly_in_any_order([[5, 6]]).passed
    ),
    "contains_sequence": lambda scalar: assert_that([[scalar], 7]).check().contains_sequence([[5, 6]], 7).passed,
    "match.is_in": lambda scalar: match.is_in([[5, 6]], 7).matches([scalar]),
}


@pytest.mark.parametrize("asked", list(_RAISED_INSIDE_ASKED))
def test_a_containers_own_comparison_that_raised_on_the_pair_is_answered_as_the_int_is(asked):
    """Where numpy's array had no truth, the container's `==` raised, and the pairs are asked one by one."""
    numpy = pytest.importorskip("numpy")
    assert_that(_RAISED_INSIDE_ASKED[asked](numpy.int64(5))).is_equal_to(_RAISED_INSIDE_ASKED[asked](5))


def test_nothing_broadcasts_while_numpy_is_not_loaded(monkeypatch):
    """No `numpy` scalar can exist before `numpy` is imported, so no list can meet one."""
    monkeypatch.delitem(sys.modules, "numpy", raising=False)
    assert_that(broadcasts(5, [5])).is_false()
    assert_that(may_broadcast([5])).is_false()
    assert_that(mixes_broadcasting([5, [5]])).is_false()


class _ShiftingInC(int):
    """An int whose `==` and `<` are C code of `int`'s shift, raising `ValueError` for a negative count."""

    __eq__ = int.__rshift__
    __lt__ = int.__rshift__
    __hash__ = int.__hash__


@pytest.mark.parametrize(
    "asked",
    [
        lambda left, right: assert_that(left).is_equal_to(right),
        lambda left, right: assert_that(left).is_less_than(right),
    ],
    ids=["is_equal_to", "is_less_than"],
)
def test_a_value_error_of_a_values_own_comparison_in_c_is_handed_on(asked):
    with pytest.raises(ValueError, match="negative shift count"):
        asked(_ShiftingInC(1), _ShiftingInC(-1))


_NO_BROADCAST_ASKED = {
    "member": lambda left, right: member(left, [right]),
    "starts_with": lambda left, right: assert_that([[left]]).starts_with([right]),
    "ends_with": lambda left, right: assert_that([[left]]).ends_with([right]),
    "is_less_than": lambda left, right: assert_that([left]).is_less_than([right]),
}


@pytest.mark.parametrize("asked", list(_NO_BROADCAST_ASKED))
def test_an_ambiguous_truth_that_is_no_broadcast_is_handed_on(asked):
    """Two arrays are compared element by element by their own right, which `is_array_equal` is for."""
    numpy = pytest.importorskip("numpy")
    with pytest.raises(ValueError, match="truth value"):
        _NO_BROADCAST_ASKED[asked](numpy.array([1, 2]), numpy.array([1, 3]))


_RAGGED = [[5], [5, 6]]
"""A list `numpy` cannot build an array from, which its scalar's `==` raises on before any truth is asked."""


@pytest.mark.parametrize("asked", list(_BROADCAST_ASKED))
def test_a_numpy_scalar_against_a_ragged_list_is_unequal_as_the_int_it_holds_is(asked):
    numpy = pytest.importorskip("numpy")
    assert_that(_BROADCAST_ASKED[asked](numpy.int64(5), _RAGGED)).is_equal_to(_BROADCAST_ASKED[asked](5, _RAGGED))


class _AlwaysEqualList(list):
    """A list that wrote its own `==`, answering a truthy object of its own."""

    def __eq__(self, other: object) -> object:
        return _Truthy()

    __hash__ = None


class _Truthy:
    def __bool__(self) -> bool:
        return True


def test_a_list_that_wrote_its_own_equality_keeps_its_answer_against_a_numpy_scalar():
    """Only `numpy`'s array is the broadcast; an answer of the subclass's own stands."""
    numpy = pytest.importorskip("numpy")
    assert_that(assert_that(_AlwaysEqualList([1])).check().is_equal_to(numpy.int64(5)).passed).is_true()


class _Declining(list):
    """A list whose own `==` declines every operand, leaving the answer to the other side's."""

    def __eq__(self, other: object) -> object:
        return NotImplemented

    __hash__ = None


@pytest.mark.parametrize("asked", list(_BROADCAST_ASKED))
@pytest.mark.parametrize("held", [[5], [5, 6]], ids=["one-element", "two-elements"])
def test_a_list_whose_own_equality_declined_a_numpy_scalar_is_unequal_as_to_the_int(asked, held):
    """Declined, the scalar's reflected `==` answered with its array, which is `numpy`'s broadcast after all."""
    numpy = pytest.importorskip("numpy")
    sequence = _Declining(held)
    assert_that(_BROADCAST_ASKED[asked](numpy.int64(5), sequence)).is_equal_to(_BROADCAST_ASKED[asked](5, sequence))


def test_a_list_whose_own_equality_answers_an_array_is_read_as_numpys_broadcast():
    """The recorded boundary: only a second call could tell which method answered, so the array is read."""
    numpy = pytest.importorskip("numpy")

    class AnsweringArray(list):
        def __eq__(self, other: object) -> object:
            return numpy.array([True])

        __hash__ = None

    assert_that(assert_that(AnsweringArray([7])).check().is_equal_to(numpy.int64(5)).passed).is_false()


def test_a_numpy_scalar_subclass_that_wrote_its_own_equality_keeps_its_answer():
    numpy = pytest.importorskip("numpy")

    class AlwaysEqual(numpy.int64):
        def __eq__(self, other: object) -> object:
            return numpy.array([True])

        __hash__ = numpy.int64.__hash__

    assert_that(assert_that(AlwaysEqual(5)).check().is_equal_to([7]).passed).is_true()


def _python_written_decimal_code(monkeypatch: pytest.MonkeyPatch) -> frozenset[types.CodeType]:
    """What `pure_decimal_code` reads where CPython runs `decimal` in Python, read here off `_pydecimal` itself."""
    monkeypatch.setattr(_require, "decimal", _pydecimal)
    return _require.pure_decimal_code.__wrapped__()


class TestADecimalWrittenInPython:
    """CPython built without its C accelerator runs `decimal` in Python, as the 3.15 candidates do on Linux.

    Its signal came out of Python frames, which `raised_inside` read as the value's own code, and its methods
    are no C methods, which `_exact_real` refused to read: 103 tests failed there.
    """

    def test_a_fresh_interpreter_without_the_accelerator_is_told_and_answered(self):
        """The real fallback, in a process of its own: 3.15 makes `decimal` the `_pydecimal` module, below it
        `decimal` re-exports its names, and either way a signalling NaN is answered rather than let out."""
        probe = (
            "import sys\n"
            "sys.modules['_decimal'] = None\n"
            "import decimal\n"
            "from assertpy import assert_that\n"
            "from assertpy._engine._require import pure_decimal_code\n"
            "print(bool(pure_decimal_code()))\n"
            "print(assert_that([decimal.Decimal('sNaN'), 1]).check().contains(1).passed)\n"
            "print(assert_that(decimal.Decimal('sNaN')).check().is_equal_to(1).passed)\n"
        )
        ran = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
        assert_that(ran.stdout.split()).is_equal_to(["True", "True", "False"])

    def test_its_code_is_read_whole_and_nothing_it_imported(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        assert_that(codes).contains(
            _pydecimal.Decimal.__eq__.__code__,
            _pydecimal.Context._raise_error.__code__,
            _pydecimal.Decimal.real.fget.__code__,
            _pydecimal.Decimal.from_float.__func__.__code__,
            _pydecimal._dec_from_triple.__code__,
        ).does_not_contain(collections.namedtuple.__code__)

    def test_a_signal_raised_in_its_code_is_the_operations_own(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        monkeypatch.setattr(_require, "pure_decimal_code", lambda: codes)
        with pytest.raises(_pydecimal.InvalidOperation) as signal:
            operator.eq(_pydecimal.Decimal("sNaN"), 1)
        assert_that(raised_inside(signal.value)).is_false()

    def test_a_signal_from_a_value_of_its_own_calling_into_it_is_still_the_values(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        monkeypatch.setattr(_require, "pure_decimal_code", lambda: codes)

        class Wrapping:
            def __eq__(self, other: object) -> bool:
                return bool(_pydecimal.Decimal("sNaN") == other)

            __hash__ = None

        with pytest.raises(_pydecimal.InvalidOperation) as signal:
            operator.eq(Wrapping(), 1)
        assert_that(raised_inside(signal.value)).is_true()

    def test_an_error_from_a_value_it_calls_into_is_the_values(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        monkeypatch.setattr(_require, "pure_decimal_code", lambda: codes)

        class Refusing:
            denominator = 1

            @property
            def numerator(self) -> int:
                raise ValueError("my own numerator")

        numbers.Rational.register(Refusing)
        with pytest.raises(ValueError, match="my own numerator") as raised:
            operator.eq(_pydecimal.Decimal(5), Refusing())
        assert_that(raised_inside(raised.value)).is_true()

    def test_a_class_borrowing_its_method_owns_the_error(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        monkeypatch.setattr(_require, "pure_decimal_code", lambda: codes)

        class Borrowing:
            __eq__ = _pydecimal.Decimal.__eq__
            __hash__ = None

        with pytest.raises(AttributeError) as borrowed:
            operator.eq(Borrowing(), 1)
        assert_that(raised_inside(borrowed.value)).is_true()

    def test_its_own_methods_are_read_as_the_c_ones_are(self, monkeypatch):
        codes = _python_written_decimal_code(monkeypatch)
        monkeypatch.setattr(_ordering, "pure_decimal_code", lambda: codes)
        monkeypatch.setattr(_ordering, "decimal", _pydecimal)

        class Borrowing:
            as_integer_ratio = _pydecimal.Decimal.as_integer_ratio

        read = _ordering._known_number_method
        assert_that(read(_pydecimal.Decimal, "as_integer_ratio", types.MethodDescriptorType)).is_same_as(
            _pydecimal.Decimal.as_integer_ratio
        )
        assert_that(read(Borrowing, "as_integer_ratio", types.MethodDescriptorType)).is_none()

        class Renaming(_pydecimal.Decimal):
            as_integer_ratio = _pydecimal.Decimal.__eq__

        assert_that(read(Renaming, "as_integer_ratio", types.MethodDescriptorType)).is_none()
