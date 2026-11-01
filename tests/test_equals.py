import collections
import dataclasses

import pytest

from assertpy import assert_that
from assertpy._engine._compare import _find_ambiguous_operand


def test_is_equal():
    assert_that("foo").is_equal_to("foo")
    assert_that(123).is_equal_to(123)
    assert_that(0.11).is_equal_to(0.11)
    assert_that(["a", "b"]).is_equal_to(["a", "b"])
    assert_that((1, 2, 3)).is_equal_to((1, 2, 3))
    assert_that(1 == 1).is_equal_to(True)
    assert_that(1 == 2).is_equal_to(False)
    assert_that({"a", "b"}).is_equal_to({"b", "a"})
    assert_that({"a": 1, "b": 2}).is_equal_to({"b": 2, "a": 1})


def test_is_equal_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_equal_to("bar")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be equal to <bar>, but was not.")


def test_is_equal_int_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_equal_to(234)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be equal to <234>, but was not.")


def test_is_equal_list_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_equal_to(["a", "b", "c"])
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be equal to <['a', 'b', 'c']>, but was not.")


def test_is_equal_long_list_failure_elides_the_matching_elements():
    actual, expected = list(range(40)), list(range(40))
    expected[27] = 999
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    assert_that(str(exc_info.value)).is_equal_to("Expected <[.., 27, ..]> to be equal to <[.., 999, ..]>, but was not.")


def test_is_equal_few_but_long_elements_still_elides():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["x" * 30, "y" * 30]).is_equal_to(["x" * 30, "z" * 30])
    assert_that(str(exc_info.value)).starts_with("Expected <[.., 'yyy")


def test_is_equal_long_tuple_failure_keeps_tuple_brackets():
    actual, expected = tuple(range(40)), list(range(40))
    expected[27] = 999
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(tuple(expected))
    assert_that(str(exc_info.value)).is_equal_to("Expected <(.., 27, ..)> to be equal to <(.., 999, ..)>, but was not.")


def test_is_equal_multiline_failure_elides_the_matching_lines():
    actual = "\n".join(f"line {index}" for index in range(8))
    expected = actual.replace("line 5", "line five")
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <.., line 6: line 5, ..> to be equal to <.., line 6: line five, ..>, but was not."
    )


def test_is_equal_multiline_failure_lists_every_changed_line():
    actual = "\n".join(f"line {index}" for index in range(8))
    expected = actual.replace("line 1", "L1").replace("line 6", "L6")
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    assert_that(str(exc_info.value)).contains("line 2: line 1, .., line 7: line 6")


def test_is_equal_short_multiline_failure_is_printed_whole():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("a\nb\nc").is_equal_to("a\nX\nc")
    assert_that(str(exc_info.value)).is_equal_to("Expected <a\nb\nc> to be equal to <a\nX\nc>, but was not.")


def test_is_equal_multiline_failure_with_a_shorter_counterpart():
    actual = "\n".join(f"line {index}" for index in range(8))
    expected = "\n".join(f"line {index}" for index in range(5))
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    assert_that(str(exc_info.value)).ends_with("to be equal to <..>, but was not.")


def test_is_equal_long_list_without_any_match_shows_everything():
    actual = [f"itemAAAAAAAAAA{i}" for i in range(4)]
    expected = [f"otherBBBBBBBBB{i}" for i in range(4)]
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    assert_that(str(exc_info.value)).does_not_contain("..")


def test_is_equal_caps_how_many_differing_parts_are_named():
    actual = {f"k{index}": index for index in range(60)}
    expected = {f"k{index}": -index for index in range(60)}
    with pytest.raises(AssertionError) as exc_info:
        assert_that(actual).is_equal_to(expected)
    message = str(exc_info.value)
    assert_that(message).contains("... and 54 more")
    assert_that(len(message.splitlines()[0])).is_less_than(250)


def test_is_equal_type_collision_annotates_types():
    # when the two reprs collide, the message tags each with its type so it does not read as "1 != 1"
    with pytest.raises(AssertionError) as exc_info:
        assert_that("1").is_equal_to(1)
    assert_that(str(exc_info.value)).is_equal_to("Expected <1:str> to be equal to <1:int>, but was not.")


def test_is_not_equal():
    assert_that("foo").is_not_equal_to("bar")
    assert_that(123).is_not_equal_to(234)
    assert_that(0.11).is_not_equal_to(0.12)
    assert_that(["a", "b"]).is_not_equal_to(["a", "x"])
    assert_that(["a", "b"]).is_not_equal_to(["a"])
    assert_that(["a", "b"]).is_not_equal_to(["a", "b", "c"])
    assert_that((1, 2, 3)).is_not_equal_to((1, 2))
    assert_that(1 == 1).is_not_equal_to(False)
    assert_that(1 == 2).is_not_equal_to(True)
    assert_that({"a", "b"}).is_not_equal_to({"a"})
    assert_that({"a": 1, "b": 2}).is_not_equal_to({"a": 1, "b": 3})
    assert_that({"a": 1, "b": 2}).is_not_equal_to({"a": 1, "c": 2})


def test_is_not_equal_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_not_equal_to("foo")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be not equal to <foo>, but was.")


def test_is_not_equal_int_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_not_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be not equal to <123>, but was.")


def test_is_not_equal_list_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_not_equal_to(["a", "b"])
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be not equal to <['a', 'b']>, but was.")


class _FakeArray:
    """Array-like: has ``__array__`` and an element-wise ``==`` whose truth value is ambiguous."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return self

    def __bool__(self):
        raise ValueError("the truth value of a _FakeArray is ambiguous")

    __hash__ = object.__hash__


class _FakeScalarArray:
    """Array-like but scalar: has ``__array__`` yet a truth-testable ``==`` (like a 0-d array/scalar)."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return isinstance(other, _FakeScalarArray)

    __hash__ = object.__hash__


class _FakeFrame(_FakeArray):
    """Frame-like: an array-like that also carries the ``equals()`` a DataFrame or Series would."""

    def equals(self, other):
        return False


class TestArrayLikeEqualityGuard:
    """is_equal_to/is_not_equal_to reject element-wise array/frame-likes with a clear, actionable error."""

    def test_is_equal_to_rejects_array_like(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeArray()).is_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("is_equal_to").contains("_FakeArray").contains("element-wise")

    def test_the_guard_points_an_array_at_is_array_equal(self):
        # the point of the message: send the reader to the assertion naming the index, not one wrapping a bare False
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeArray()).is_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("is_array_equal(expected)").does_not_contain("is_frame_equal")

    def test_the_guard_points_a_frame_at_is_frame_equal(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeFrame()).is_equal_to(_FakeFrame())
        assert_that(str(exc_info.value)).contains("is_frame_equal(expected)").does_not_contain("is_array_equal")

    def test_is_not_equal_to_rejects_array_like(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_FakeArray()).is_not_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("is_not_equal_to").contains("_FakeArray")

    def test_array_like_as_expected_operand_is_rejected(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(5).is_equal_to(_FakeArray())
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_an_array_inside_two_sequences_of_different_lengths_is_still_named(self):
        # the top-level `!=` short-circuits before the array, so the diff surfaces it through the alignment
        with pytest.raises(TypeError) as exc_info:
            assert_that([0, 1, _FakeArray(), 3, 4]).is_equal_to([9, 0, 1, _FakeArray(), 3, 4])
        assert_that(str(exc_info.value)).contains("_FakeArray").contains("element-wise")

    def test_scalar_array_like_is_not_rejected(self):
        assert_that(_FakeScalarArray()).is_equal_to(_FakeScalarArray())
        with pytest.raises(AssertionError):
            assert_that(_FakeScalarArray()).is_not_equal_to(_FakeScalarArray())

    def test_numpy_array_raises_clear_error(self):
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError) as exc_info:
            assert_that(numpy.array([1, 2, 3])).is_equal_to(numpy.array([1, 2, 3]))
        assert_that(str(exc_info.value)).contains("element-wise")

    def test_pandas_dataframe_raises_clear_error(self):
        pandas = pytest.importorskip("pandas")
        frame = pandas.DataFrame({"a": [1, 2]})
        with pytest.raises(TypeError) as exc_info:
            assert_that(frame).is_equal_to(frame)
        assert_that(str(exc_info.value)).contains("element-wise")

    def test_polars_dataframe_raises_clear_error(self):
        polars = pytest.importorskip("polars")
        frame = polars.DataFrame({"a": [1, 2]})
        with pytest.raises(TypeError) as exc_info:
            assert_that(frame).is_equal_to(frame)
        assert_that(str(exc_info.value)).contains("element-wise")


class _RaisingEq:
    """Non-array value whose ``==`` raises, to pin that only array-caused errors are converted."""

    def __eq__(self, other):
        raise ValueError("raising eq")

    __hash__ = object.__hash__


@dataclasses.dataclass
class _ArrayField:
    payload: object


@dataclasses.dataclass
class _EmptyDataclass:
    pass


@dataclasses.dataclass
class _CachedArray:
    cache: object = dataclasses.field(compare=False)
    payload: object = None


class _ArrayModel:
    """Duck pydantic model: ``__eq__`` compares dumps, so an array field breaks it like real pydantic."""

    def __init__(self, payload):
        self.payload = payload

    def model_dump(self):
        return {"payload": self.payload}

    def __eq__(self, other):
        return self.model_dump() == other.model_dump()

    __hash__ = object.__hash__


class TestNestedArrayLikeEqualityGuard:
    """The array/frame-like guard applies at any nesting depth, not only to the top-level operands."""

    def test_array_like_as_dict_value(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray()}).is_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("is_equal_to").contains("_FakeArray").contains("element-wise")

    def test_array_like_in_list_inside_dict(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": [_FakeArray()]}).is_equal_to({"a": [_FakeArray()]})
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_in_top_level_list(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that([_FakeArray()]).is_equal_to([_FakeArray()])
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_in_namedtuple(self):
        point = collections.namedtuple("point", ["payload"])
        with pytest.raises(TypeError) as exc_info:
            assert_that(point(_FakeArray())).is_equal_to(point(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_as_dataclass_field(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_ArrayField(_FakeArray())).is_equal_to(_ArrayField(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_as_model_field(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_ArrayModel(_FakeArray())).is_equal_to(_ArrayModel(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_with_ignored_sibling_key(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "b": 2}).is_equal_to({"a": _FakeArray(), "b": 3}, ignore="b")
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_with_tolerance(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "x": 1.0}).is_equal_to({"a": _FakeArray(), "x": 1.0}, tolerance=0.1)
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_array_like_reached_only_in_diff_phase(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray(), "b": 1}).is_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("_FakeArray")

    def test_non_array_comparison_error_propagates_unchanged(self):
        with pytest.raises(ValueError, match="raising eq"):
            assert_that({"a": _RaisingEq()}).is_equal_to({"a": _RaisingEq()})

    def test_is_not_equal_to_array_like_as_dict_value(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": _FakeArray()}).is_not_equal_to({"a": _FakeArray()})
        assert_that(str(exc_info.value)).contains("is_not_equal_to").contains("_FakeArray")

    def test_is_not_equal_to_non_array_error_propagates_unchanged(self):
        with pytest.raises(ValueError, match="raising eq"):
            assert_that({"a": _RaisingEq()}).is_not_equal_to({"a": _RaisingEq()})

    def test_numpy_array_nested_in_dict_raises_clear_error(self):
        numpy = pytest.importorskip("numpy")
        with pytest.raises(TypeError) as exc_info:
            assert_that({"a": numpy.array([1, 2])}).is_equal_to({"a": numpy.array([1, 2])})
        assert_that(str(exc_info.value)).contains("element-wise")


class TestFindAmbiguousOperand:
    """Direct coverage of the error-path search over shapes a crashed comparison cannot produce itself."""

    def test_shared_cyclic_sibling_is_skipped(self):
        loop = {}
        loop["self"] = loop
        arr = _FakeArray()
        found = _find_ambiguous_operand({"loop": loop, "arr": arr}, {"loop": loop, "arr": _FakeArray()})
        assert_that(found).is_same_as(arr)

    def test_key_without_counterpart_is_skipped(self):
        arr = _FakeArray()
        found = _find_ambiguous_operand({"only": 1, "arr": arr}, {"arr": _FakeArray(), "other": 2})
        assert_that(found).is_same_as(arr)

    def test_dataclass_field_missing_on_expected(self):
        arr = _FakeArray()
        found = _find_ambiguous_operand(_ArrayField(arr), _EmptyDataclass())
        assert_that(found).is_same_as(arr)

    def test_an_array_only_on_the_expected_side_is_found(self):
        # with the array only on the expected side the search fell through and its raw ValueError escaped
        arr = _FakeArray()
        assert_that(_find_ambiguous_operand([1], [arr])).is_same_as(arr)
        assert_that(_find_ambiguous_operand(_ArrayField(1), _ArrayField(arr))).is_same_as(arr)
        assert_that(_find_ambiguous_operand({"k": 1}, {"k": arr})).is_same_as(arr)

    def test_an_array_inside_an_expected_list_reports_the_actionable_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that({"k": [1, 2]}).is_equal_to({"k": [_FakeArray(), 2]})
        assert_that(str(exc_info.value)).contains("_FakeArray").contains("element-wise")

    def test_an_array_inside_an_expected_dataclass_field_reports_the_actionable_error(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(_ArrayField(1)).is_equal_to(_ArrayField(_FakeArray()))
        assert_that(str(exc_info.value)).contains("_FakeArray").contains("element-wise")

    def test_a_field_equality_leaves_out_is_not_searched(self):
        """Only a compared field can have broken `==`, so the array in the cache ahead of it is not the culprit."""
        payload = _FakeArray()
        found = _find_ambiguous_operand(_CachedArray(_FakeArray(), payload), _CachedArray(_FakeArray(), _FakeArray()))
        assert_that(found).is_same_as(payload)

    def test_dataclass_without_array_returns_none(self):
        assert_that(_find_ambiguous_operand(_ArrayField(1), _ArrayField(2))).is_none()

    def test_list_without_array_returns_none(self):
        assert_that(_find_ambiguous_operand([_RaisingEq()], [_RaisingEq()])).is_none()

    def test_plain_scalars_return_none(self):
        assert_that(_find_ambiguous_operand(1, 2)).is_none()

    def test_the_cycle_key_pairs_the_two_operands(self):
        """Keyed on one operand alone, the guard fires at the first node that repeats that side and the
        array reachable through the other side is never looked at."""
        arr = _FakeArray()
        loop = {}
        loop["k"] = loop
        assert_that(_find_ambiguous_operand({"k": {"k": arr}}, loop)).is_same_as(arr)
        assert_that(_find_ambiguous_operand(loop, {"k": {"k": arr}})).is_same_as(arr)

    def test_the_nested_guard_names_the_assertion_that_was_called(self):
        """The top-level gate is handed the name; only the nested search takes it from the default."""
        with pytest.raises(TypeError) as exc_info:
            assert_that({"k": [1, 2]}).is_equal_to({"k": [_FakeArray(), 2]})
        assert_that(str(exc_info.value)).starts_with("is_equal_to() cannot directly compare")


def test_is_equal_shifted_list_failure_elides_the_aligned_run():
    # elides on the alignment the diff pairs on: by position, every later element shifts out and both dump whole
    with pytest.raises(AssertionError) as exc_info:
        assert_that([0, *range(1, 40)]).is_equal_to(list(range(1, 40)))
    assert_that(str(exc_info.value)).contains("Expected <[0, ..]> to be equal to <[..]>")


class TestFindAmbiguousOperandOnMismatchedShapes:
    """Every branch of the walk gates on *both* operands having the shape.  Relaxing any of those
    conjunctions to a disjunction sends a pair down a branch only one side can survive, which is a
    crash rather than a wrong answer, and nothing above paired a shape with a different one."""

    def test_a_dict_against_a_list_is_not_walked_as_a_mapping(self):
        assert_that(_find_ambiguous_operand({"a": _FakeArray()}, ["a"])).is_none()

    def test_a_list_against_a_scalar_is_not_zipped(self):
        assert_that(_find_ambiguous_operand([_FakeArray()], 2)).is_none()

    def test_a_model_against_a_dict_is_not_dumped(self):
        assert_that(_find_ambiguous_operand(_ArrayModel(_FakeArray()), {"payload": 1})).is_none()

    def test_a_dataclass_against_a_plain_object_is_not_walked_by_fields(self):
        assert_that(_find_ambiguous_operand(_ArrayField(_FakeArray()), object())).is_none()

    def test_a_plain_object_against_a_dataclass_is_not_walked_by_fields(self):
        assert_that(_find_ambiguous_operand(object(), _ArrayField(_FakeArray()))).is_none()

    def test_a_dataclass_type_is_not_mistaken_for_an_instance(self):
        # `is_dataclass` answers True for the class too, and `fields()` on it yields no values to read
        assert_that(_find_ambiguous_operand(_ArrayField, _ArrayField)).is_none()

    def test_a_longer_actual_stops_at_the_shorter_expected(self):
        # non-strict on purpose: a length difference is the diff engine's business, and raising would hide it
        assert_that(_find_ambiguous_operand([1, _FakeArray()], [1])).is_none()


class TestFindAmbiguousOperandCycleGuard:
    """The seen-set has to survive every recursive hop.  Dropping it on any branch turns a
    self-referential payload into unbounded recursion, and only the mapping hop was pinned."""

    def test_a_cycle_through_a_list(self):
        loop = [1]
        loop.append(loop)
        assert_that(_find_ambiguous_operand(loop, list(loop))).is_none()

    def test_a_cycle_through_a_dataclass_field(self):
        holder = _ArrayField(None)
        holder.payload = holder
        other = _ArrayField(None)
        other.payload = other
        assert_that(_find_ambiguous_operand(holder, other)).is_none()

    def test_a_cycle_through_a_model_dump(self):
        model = _ArrayModel(None)
        model.payload = model
        other = _ArrayModel(None)
        other.payload = other
        assert_that(_find_ambiguous_operand(model, other)).is_none()

    def test_the_pair_identity_uses_both_sides(self):
        # keyed on one side, two expected values collapse into one entry and the second hides the array it holds
        shared = {"v": 1}
        arr = _FakeArray()
        assert_that(_find_ambiguous_operand([shared, shared], [{"v": 1}, {"v": arr}])).is_same_as(arr)
