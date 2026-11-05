import functools
import json
import types

import pytest

from assertpy import assert_that, match
from assertpy._engine._introspection import is_attrs_instance
from assertpy._snapshot_codec import _decode, _encode
from assertpy.errors import AssertionFailure

attrs = pytest.importorskip("attrs", reason="attrs not installed")
import attr  # noqa: E402  # low-level attrs API, imported only after importorskip confirms attrs is installed


@attrs.define
class Point:
    x: int
    y: int


@attrs.define
class Line:
    start: Point
    end: Point


@attrs.define
class Named:
    x: int
    y: int
    label: str


@attrs.define
class Tag:
    """Compared by a key, the way attrs spells a case-insensitive field."""

    name: str = attrs.field(eq=str.lower)
    weight: int = 0


@attrs.frozen
class FrozenWithCache:
    x: int
    cache: int = attrs.field(default=0, eq=False)


@attrs.define(slots=False)
class Unslotted:
    x: int


@attrs.define
class Holder:
    value: object


@attrs.define
class PointTwin:
    """The fields of `Point` under another class."""

    x: int
    y: int


@attrs.define
class Signed:
    """A number compared by its magnitude."""

    value: float = attrs.field(eq=abs)


@attrs.define
class Tagged:
    name: object = attrs.field(eq=str.lower)
    values: object = None


@attrs.define
class Coded:
    """A key that folds two types together, which `==` then holds equal."""

    code: object = attrs.field(eq=str)


class Strict:
    """A value whose `==` answers `False` rather than declining a value of another kind."""

    def __init__(self, n):
        self.n = n

    def __eq__(self, other):
        return isinstance(other, Strict) and self.n == other.n

    __hash__ = None

    def __repr__(self):
        return f"Strict({self.n})"


@attrs.define
class Boxed:
    value: object = attrs.field(eq=repr)


@attrs.define
class Measured:
    ignored: object = attrs.field(eq=False)
    values: object = None


@attrs.define
class KeyedArray:
    """An array compared the way attrs documents it, through `cmp_using`, beside a field compared by `==`."""

    values: object = attrs.field(eq=attrs.cmp_using(eq=lambda left, right: (left == right).all()))
    other: object = None


@attrs.define
class Warmed:
    x: int
    runs: list = attrs.field(factory=list, eq=False)

    @functools.cached_property
    def heavy(self):
        self.runs.append(1)
        return self.x * 10


@attrs.define
class Base:
    a: int


@attrs.define
class Derived(Base):
    b: int


class TestAKeyComparedFieldIsReadThroughItsKey:
    """`attrs.asdict` read the raw value, so a configured comparison refused what `==` holds equal."""

    def test_a_configured_comparison_agrees_with_equality(self):
        assert_that(Tag("X")).is_equal_to(Tag("x"), ignore="weight")

    def test_the_diff_leaves_out_a_field_its_key_holds_equal(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Tag("X", 1)).is_equal_to(Tag("x", 2))
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to([".weight"])

    def test_a_nested_instance_of_another_class_is_compared_by_contents_as_before(self):
        """What `attrs.asdict` did for a nested instance, kept: a configured comparison reads contents."""
        assert_that(Holder(Point(1, 2))).is_equal_to(Holder(PointTwin(1, 2)), ignore="unrelated")

    def test_strict_types_still_tells_a_nested_class_apart(self):
        """Taken apart into a plain mapping, the nested instance lost its class and passed `strict_types`."""
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Holder(Point(1, 2))).is_equal_to(Holder(PointTwin(1, 2)), ignore="unrelated", strict_types=True)
        assert_that(str(caught.value)).contains("only their types differ")
        assert_that(Holder(Point(1, 2))).is_equal_to(Holder(Point(1, 2)), ignore="unrelated", strict_types=True)

    @pytest.mark.parametrize("configured", [{}, {"ignore": "unrelated"}], ids=["plain", "configured"])
    def test_a_difference_is_shown_as_the_values_held(self, configured):
        """The key decides, and printed in their place `str.lower` showed a value neither side has."""
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Tag("X", 1)).is_equal_to(Tag("Y", 1), **configured)
        assert_that([(entry.actual, entry.expected) for entry in caught.value.diff.entries]).is_equal_to([("X", "Y")])
        assert_that(str(caught.value)).contains("'X'").does_not_contain("'x'")

    def test_an_array_compared_through_cmp_using_is_shown_as_the_array(self):
        numpy = pytest.importorskip("numpy")
        with pytest.raises(AssertionFailure) as caught:
            assert_that(KeyedArray(numpy.array([1, 2]))).is_equal_to(KeyedArray(numpy.array([1, 3]), 1), ignore="other")
        assert_that(str(caught.value)).contains("array([1, 2])").does_not_contain("object at 0x")
        assert_that(KeyedArray(numpy.array([1, 2]))).is_equal_to(KeyedArray(numpy.array([1, 2]), 1), ignore="other")

    def test_a_nested_instance_is_read_through_its_key(self):
        assert_that(Holder(Tag("X"))).is_equal_to(Holder(Tag("x")), ignore="unrelated")

    def test_a_payload_value_is_compared_as_held(self):
        """The key belongs to attrs' `==`, which a payload has no part in: read through it on the instance's
        side only, a payload holding the very same `"X"` failed."""
        assert_that(Holder(Tag("X"))).is_equal_to(Holder({"name": "X", "weight": 0}), ignore="unrelated")
        with pytest.raises(AssertionFailure):
            assert_that(Holder(Tag("X"))).is_equal_to(Holder({"name": "x", "weight": 0}), ignore="unrelated")

    def test_either_side_can_be_the_payload(self):
        """Put in the field's place, the key met a payload's value whose `==` answers first on one side only."""
        assert_that(Boxed(Strict(1))).is_equal_to({"value": Strict(1)}, ignore="unrelated")
        assert_that({"value": Strict(1)}).is_equal_to(Boxed(Strict(1)), ignore="unrelated")
        assert_that(Holder({"value": Strict(1)})).is_equal_to(Holder(Boxed(Strict(1))), ignore="unrelated")

    @pytest.mark.parametrize("configured", [{}, {"ignore": "unrelated"}], ids=["plain", "configured"])
    def test_strict_types_reads_the_type_a_keyed_field_holds(self, configured):
        """The key folds `1` and `"1"` together, and `strict_types` still reads the two types held."""
        assert_that(Coded(1)).is_equal_to(Coded("1"), **configured)
        with pytest.raises(AssertionFailure):
            assert_that(Coded(1)).is_equal_to(Coded("1"), strict_types=True, **configured)

    def test_a_configured_failure_leaves_out_a_field_its_key_holds_equal(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Tag("X", 1)).is_equal_to(Tag("x", 2), ignore="unrelated")
        assert_that([entry.path for entry in caught.value.diff.entries]).is_equal_to(["weight"])
        assert_that(str(caught.value)).starts_with("Expected <Tag(.., weight=1)>")

    def test_a_payload_that_is_not_a_dict_is_compared_as_held(self):
        assert_that(Holder(Tag("X"))).is_equal_to(
            Holder(types.MappingProxyType({"name": "X", "weight": 0})), ignore="unrelated"
        )

    def test_ignore_null_leaves_a_keyed_field_before_its_key_reads_it(self):
        """Read through the key first, `str.lower(None)` raised where `ignore_null` leaves the field out."""
        assert_that(Tag("X", 1)).is_equal_to(Tag(None, 1), ignore_null=True, ignore="unrelated")

    def test_a_key_that_raises_inside_equality_is_the_error_raised(self):
        """The search that names an array read the key again, and raised a second error handling the first."""
        with pytest.raises(TypeError, match="lower") as caught:
            assert_that(Tag("X", 1)).is_equal_to(Tag(None, 1))
        assert_that(caught.value.__context__).is_none()

    @pytest.mark.parametrize("configured", [{}, {"ignore": "unrelated"}], ids=["plain", "configured"])
    def test_a_tolerance_reaches_a_keyed_number(self, configured):
        """Read as the wrapper of one comparison, a keyed number was never a number to the tolerance."""
        assert_that(Signed(1.0)).is_equal_to(Signed(1.05), tolerance=0.1, **configured)
        assert_that(Signed(1.0)).is_equal_to(Signed(-1.0), tolerance=0.1, **configured)
        with pytest.raises(AssertionFailure):
            assert_that(Signed(1.0)).is_equal_to(Signed(1.5), tolerance=0.1, **configured)

    def test_a_key_that_raises_leaves_no_array_to_blame(self):
        """attrs reads every key before comparing a field, so the array after the key never took part."""
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError, match="lower") as caught:
            assert_that(Tagged(None, numpy.array([1, 2]))).is_equal_to(Tagged("a", numpy.array([1, 3])))
        assert_that(str(caught.value)).does_not_contain("cannot directly compare")

    def test_a_failure_hands_out_the_values_held(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(Tag("X", 1)).is_equal_to(Tag("Y", 1), ignore="weight")
        assert_that(caught.value.actual).is_equal_to({"name": "X", "weight": 1})
        assert_that(caught.value.actual["name"]).is_instance_of(str)

    def test_a_matcher_or_none_in_the_payload_is_compared_as_held(self):
        assert_that(Holder(Tag("Xy"))).is_equal_to(
            Holder({"name": match.starts_with("X"), "weight": 0}), ignore="unrelated"
        )
        with pytest.raises(AssertionFailure):
            assert_that(Holder(Tag("X"))).is_equal_to(Holder({"name": None, "weight": 0}), ignore="unrelated")

    def test_a_comparator_named_for_the_field_gets_the_values_held(self):
        seen = []
        assert_that(Tag("X", 1)).is_equal_to(
            Tag("Y", 2),
            ignore="weight",
            comparators={"name": lambda actual, expected: seen.append((actual, expected)) is None},
        )
        assert_that(seen).is_equal_to([("X", "Y")])

    def test_a_comparator_named_for_a_type_reaches_the_field(self):
        assert_that(Tag("X", 1)).is_equal_to(
            Tag("Y", 2), ignore="weight", comparators={str: lambda actual, expected: actual[0] == "X"}
        )


class TestAnArrayInAnAttrsFieldIsNamed:
    def test_the_refusal_names_the_array_as_it_does_in_a_dataclass(self):
        """The search that names it went through dataclasses and models, and a bare `ValueError` came out."""
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError) as caught:
            assert_that(Holder(numpy.array([1, 2]))).is_equal_to(Holder(numpy.array([1, 3])))
        assert_that(str(caught.value)).starts_with("is_equal_to() cannot directly compare <ndarray>")

    def test_a_field_equality_leaves_out_is_not_named(self):
        """Only the fields `==` compares can have broken it, so an ignored one is never the culprit."""
        numpy = pytest.importorskip("numpy")
        pandas = pytest.importorskip("pandas")
        with pytest.raises(TypeError) as caught:
            assert_that(Measured(pandas.Series([1]), numpy.array([1, 2]))).is_equal_to(
                Measured(pandas.Series([2]), numpy.array([1, 3]))
            )
        assert_that(str(caught.value)).starts_with("is_equal_to() cannot directly compare <ndarray>")

    @pytest.mark.parametrize("side", ["actual", "expected"])
    def test_an_array_on_one_side_only_is_named(self, side):
        """The search read one side's fields as missing, and only an array on both sides was found."""
        numpy = pytest.importorskip("numpy")
        pair = [Holder(numpy.array([1, 2])), Holder(1)]
        actual, expected = pair if side == "actual" else pair[::-1]
        with pytest.raises(TypeError) as caught:
            assert_that(actual).is_equal_to(expected)
        assert_that(str(caught.value)).starts_with("is_equal_to() cannot directly compare <ndarray>")

    def test_a_field_compared_through_its_key_is_read_through_it(self):
        """The key compares the array, so the culprit is the field `==` compares as it is."""
        numpy = pytest.importorskip("numpy")
        pandas = pytest.importorskip("pandas")
        with pytest.raises(TypeError) as caught:
            assert_that(KeyedArray(numpy.array([1, 2]), pandas.Series([1, 2]))).is_equal_to(
                KeyedArray(numpy.array([1, 2]), pandas.Series([1, 3]))
            )
        assert_that(str(caught.value)).starts_with("is_equal_to() cannot directly compare <Series>")


class TestAnAttrsInstanceRoundTripsThroughASnapshot:
    """A slotted class has no `__dict__`, so writing one raised `Object of type ... is not JSON serializable`."""

    @pytest.mark.parametrize(
        "value", [Point(1, 2), FrozenWithCache(1, cache=5), Unslotted(3), Line(Point(1, 2), Point(3, 4))], ids=repr
    )
    def test_what_is_written_is_what_is_read(self, value):
        assert_that(_round_trip(value)).is_equal_to(value)

    def test_the_slots_of_a_base_class_come_back(self):
        assert_that(_round_trip(Derived(1, 2))).is_equal_to(Derived(1, 2))

    def test_what_the_instance_holds_beside_its_fields_comes_back(self):
        loose = Unslotted(3)
        loose.note = "kept"
        assert_that(_round_trip(loose).note).is_equal_to("kept")
        warmed = Warmed(2)
        assert_that(warmed.heavy).is_equal_to(20)
        back = _round_trip(warmed)
        assert_that(back.heavy).is_equal_to(20)
        assert_that(back.runs).is_equal_to([1])

    def test_a_cached_property_is_not_run_to_write_one(self):
        """Read through `getattr`, the slot attrs keeps a `cached_property` in ran the property to fill it."""
        cold = Warmed(2)
        _round_trip(cold)
        assert_that(cold.runs).is_empty()


def _round_trip(value):
    return _decode(json.loads(json.dumps(_encode({"v": value}))))["v"]


class TestStructuralDiff:
    def test_nested_attrs_reports_field_path(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Line(Point(1, 2), Point(3, 4))).is_equal_to(Line(Point(1, 2), Point(9, 4)))
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("attrs")
        assert_that([entry.path for entry in diff.entries]).contains(".end.x")

    def test_equal_attrs_pass(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).is_equal_to(Line(Point(1, 2), Point(3, 4)))

    def test_top_level_field_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Point(1, 2)).is_equal_to(Point(1, 99))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains(".y")

    def test_extra_and_missing_fields(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Named(1, 2, "a")).is_equal_to(Point(1, 2))
        paths = [entry.path for entry in exc_info.value.diff.entries]
        assert_that(paths).contains(".label")  # present in actual, absent in expected

    def test_ignore_and_tolerance_still_work(self):
        assert_that(Named(1, 2, "a")).is_equal_to(Named(1, 2, "b"), ignore="label")


@attrs.define(frozen=True)
class Frozen:
    x: int
    y: int


@attrs.define
class Converted:
    n: int = attrs.field(converter=int)


@attrs.define
class Private:
    _secret: int
    name: str


@attr.s
class OldStyle:
    x = attr.ib()
    y = attr.ib()


@attrs.define
class Nested:
    inner: Frozen
    tag: str


class TestVariants:
    def test_attrs_class_is_not_an_instance(self):
        assert_that(is_attrs_instance(Frozen)).is_false()
        assert_that(is_attrs_instance(Frozen(1, 2))).is_true()

    def test_comparing_classes_does_not_crash(self):
        assert_that(Frozen).is_equal_to(Frozen)  # class, not instance: equal by identity, no field read

    def test_frozen_field_diff(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Frozen(1, 2)).is_equal_to(Frozen(1, 9))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains(".y")

    def test_converter_value_compared(self):
        assert_that(Converted("5")).is_equal_to(Converted(5))
        assert_that(Converted("5")).matches_structure({"n": 5})

    def test_private_field_name_kept(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(Private(1, "a")).is_equal_to(Private(9, "a"))
        assert_that([entry.path for entry in exc_info.value.diff.entries]).contains("._secret")
        assert_that(Private(1, "a")).matches_structure({"_secret": 1})

    def test_old_style_attr_s(self):
        assert_that(OldStyle(1, 2)).is_equal_to(OldStyle(1, 2))
        assert_that(OldStyle(1, 2)).matches_structure({"x": 1})

    def test_nested_ignore_reaches_into_attrs(self):
        assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "a"), ignore=("inner", "y"))

    def test_nested_include_reaches_into_attrs(self):
        assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "b"), include=("inner", "x"))

    def test_nested_ignore_does_not_over_ignore(self):
        with pytest.raises(AssertionError):
            assert_that(Nested(Frozen(1, 2), "a")).is_equal_to(Nested(Frozen(1, 9), "a"), ignore="tag")


@attrs.define
class Knot:
    tag: str
    child: object = None


class TestFieldWalk:
    def test_all_fields_satisfy_walks_into_attrs(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).all_fields_satisfy(lambda leaf: isinstance(leaf, int))

    def test_all_fields_satisfy_flags_bad_leaf(self):
        with pytest.raises(AssertionError):
            assert_that(Named(1, 2, "a")).all_fields_satisfy(lambda leaf: isinstance(leaf, int))

    def test_has_no_none_fields_on_attrs(self):
        @attrs.define
        class Maybe:
            a: int
            b: object

        assert_that(Maybe(1, 2)).has_no_none_fields()
        with pytest.raises(AssertionError):
            assert_that(Maybe(1, None)).has_no_none_fields()

    def test_the_leaf_walk_names_attrs_fields_bare_and_stops_at_a_cycle(self):
        """A field of the value under test is named bare, and a self-reference is no field of its own."""
        knot = Knot("a")
        knot.child = knot
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that(knot).all_fields_satisfy(lambda leaf: leaf == 42)
        rows = [(entry.path, entry.actual) for entry in exc_info.value.diff.entries]
        assert_that(rows).is_equal_to([("tag", "a")])
        # a predicate was asked about the marker, which the value does not hold, and failed on it
        assert_that(knot).all_fields_satisfy(lambda leaf: leaf == "a")


class TestMatchesStructure:
    def test_attrs_with_matchers(self):
        assert_that(Point(1, 2)).matches_structure({"x": match.between(0, 10), "y": 2})

    def test_nested_attrs_structure(self):
        assert_that(Line(Point(1, 2), Point(3, 4))).matches_structure({"end": {"x": 3}})

    def test_attrs_mismatch_reports_field(self):
        with pytest.raises(AssertionError, match="x"):
            assert_that(Point(1, 2)).matches_structure({"x": 99})

    def test_non_mapping_value_rejected(self):
        with pytest.raises(TypeError, match="mapping, a pydantic-style model, or an attrs instance"):
            assert_that([1, 2]).matches_structure({"x": 1})
