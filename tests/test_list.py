import collections
import decimal
import itertools

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, BaseMatcher, assert_that, match


def test_is_length():
    assert_that(["a", "b", "c"]).is_length(3)
    assert_that((1, 2, 3, 4)).is_length(4)
    assert_that({"a": 1, "b": 2}).is_length(2)
    assert_that({"a", "b"}).is_length(2)


def test_is_length_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length(4)
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to be of length <4>, but was <3>.")


class TestALengthMatcher:
    """A matcher for the length, as `has_length(greater_than(2))` reads in PyHamcrest.

    The size helpers cover one bound each, and a range or a composed condition needed two assertions.
    """

    def test_the_length_is_what_the_matcher_is_asked_about(self):
        assert_that(["a", "b", "c"]).is_length(match.greater_than(2)).is_length(match.between(1, 3))
        assert_that("foo").satisfies(match.has_length(match.less_than(4)) & match.is_length(match.is_odd()))

    def test_a_failure_names_the_condition_and_the_length(self):
        with pytest.raises(AssertionError) as failure:
            assert_that(["a"]).is_length(match.greater_than(2))
        assert_that(str(failure.value)).is_equal_to(
            "Expected <['a']> to have a length that is a value greater than <2>, but was <1>."
        )

    def test_a_composed_condition_says_which_part_failed(self):
        with pytest.raises(AssertionError) as failure:
            assert_that(["a"]).is_length(match.greater_than(2) & match.less_than(9))
        assert_that(str(failure.value)).is_equal_to(
            "Expected <['a']> to have a length that is (a value greater than <2> and a value less than <9>),"
            " but was <1>: <1> did not satisfy: a value greater than <2> (was <1>)."
        )

    def test_the_matcher_describes_the_condition(self):
        assert_that(match.has_length(match.greater_than(2)).describe()).is_equal_to(
            "a value with a length that is a value greater than <2>"
        )
        assert_that(match.is_length(match.greater_than(2)).matches([1])).is_false()

    def test_a_value_with_no_length_is_refused_or_not_matched_as_before(self):
        with pytest.raises(TypeError):
            assert_that(5).is_length(match.greater_than(0))
        assert_that(match.has_length(match.greater_than(0)).matches(iter([1]))).is_false()


def test_is_length_between():
    assert_that(["a", "b", "c"]).is_length_between(1, 5)
    assert_that("foo").is_length_between(3, 3)
    assert_that((1, 2)).is_length_between(2, 4)
    assert_that({"a": 1}).is_length_between(0, 1)


def test_is_length_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length_between(4, 6)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to be of length between <4> and <6>, but was <3>."
    )


def test_is_length_between_above_high_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_length_between(0, 2)
    assert_that(str(exc_info.value)).contains("to be of length between <0> and <2>, but was <3>.")


def test_is_length_between_bad_args():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a"]).is_length_between("1", 2)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be an integer, but was <'1'> (str)")
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a"]).is_length_between(1, "2")
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be an integer, but was <'2'> (str)")
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a"]).is_length_between(0, -1)
    assert_that(str(exc_info.value)).is_equal_to("given args must be positive ints")
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a"]).is_length_between(2, 1)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be less than given high arg")


def test_is_length_bad_arg_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).is_length("bar")
    assert_that(str(exc_info.value)).is_equal_to("given length arg must be an integer, but was <'bar'> (str)")


def test_is_length_negative_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a", "b", "c"]).is_length(-1)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive int")


def test_contains():
    assert_that(["a", "b", "c"]).contains("a")
    assert_that(["a", "b", "c"]).contains("c", "b", "a")
    assert_that((1, 2, 3, 4)).contains(1, 2, 3)
    assert_that((1, 2, 3, 4)).contains(4)
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a")
    assert_that({"a": 1, "b": 2, "c": 3}).contains("a", "b")
    assert_that({"a", "b", "c"}).contains("a")
    assert_that({"a", "b", "c"}).contains("c", "b")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe, bob]).contains(joe)


def test_contains_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("x")
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to contain item <x>, but did not.")


def test_contains_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("a", "x", "z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to contain items <'a', 'x', 'z'>, but did not contain <'x', 'z'>."
    )


def test_contains_multi_item_single_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).contains("a", "b", "z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to contain items <'a', 'b', 'z'>, but did not contain <z>."
    )


def test_does_not_contain():
    assert_that(["a", "b", "c"]).does_not_contain("x")
    assert_that(["a", "b", "c"]).does_not_contain("x", "y")
    assert_that((1, 2, 3, 4)).does_not_contain(5)
    assert_that((1, 2, 3, 4)).does_not_contain(5, 6)
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x")
    assert_that({"a": 1, "b": 2, "c": 3}).does_not_contain("x", "y")
    assert_that({"a", "b", "c"}).does_not_contain("x")
    assert_that({"a", "b", "c"}).does_not_contain("x", "y")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe]).does_not_contain(bob)


def test_does_not_contain_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("a")
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b', 'c']> to not contain item <a>, but did.")


def test_does_not_contain_list_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("x", "y", "a")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to not contain items <'x', 'y', 'a'>, but did contain <a>."
    )


def test_does_not_contain_list_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).does_not_contain("x", "a", "b")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['a', 'b', 'c']> to not contain items <'x', 'a', 'b'>, but did contain <'a', 'b'>."
    )


def test_contains_only():
    assert_that(["a", "b", "c"]).contains_only("a", "b", "c")
    assert_that(["a", "b", "c"]).contains_only("c", "b", "a")
    assert_that(["a", "a", "b"]).contains_only("a", "b")
    assert_that(["a", "a", "a"]).contains_only("a")
    assert_that((1, 2, 3, 4)).contains_only(1, 2, 3, 4)
    assert_that((1, 2, 3, 1)).contains_only(1, 2, 3)
    assert_that((1, 2, 2, 1)).contains_only(1, 2)
    assert_that((1, 1, 1, 1)).contains_only(1)
    assert_that("foobar").contains_only("f", "o", "b", "a", "r")


def test_contains_only_no_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([1, 2, 3]).contains_only()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_only_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 2)
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain only <1, 2>, but did contain <3>.")


def test_contains_only_multi_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 4)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain only <1, 4>, but did contain <2, 3> and did not contain <4>."
    )


def test_contains_only_superlist_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_only(1, 2, 3, 4)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain only <1, 2, 3, 4>, but did not contain <4>."
    )


def test_contains_only_tuple_items_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([("a",)]).contains_only("a")
    assert_that(str(exc_info.value)).contains("but did contain <('a',)>")


def test_contains_only_multi_tuple_items_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([("a",), ("b",)]).contains_only("x")
    assert_that(str(exc_info.value)).contains("but did contain <('a',), ('b',)>")


def test_contains_sequence():
    assert_that(["a", "b", "c"]).contains_sequence("a")
    assert_that(["a", "b", "c"]).contains_sequence("b")
    assert_that(["a", "b", "c"]).contains_sequence("c")
    assert_that(["a", "b", "c"]).contains_sequence("a", "b")
    assert_that(["a", "b", "c"]).contains_sequence("b", "c")
    assert_that(["a", "b", "c"]).contains_sequence("a", "b", "c")
    assert_that((1, 2, 3, 4)).contains_sequence(1)
    assert_that((1, 2, 3, 4)).contains_sequence(2)
    assert_that((1, 2, 3, 4)).contains_sequence(3)
    assert_that((1, 2, 3, 4)).contains_sequence(4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2)
    assert_that((1, 2, 3, 4)).contains_sequence(2, 3)
    assert_that((1, 2, 3, 4)).contains_sequence(3, 4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2, 3)
    assert_that((1, 2, 3, 4)).contains_sequence(2, 3, 4)
    assert_that((1, 2, 3, 4)).contains_sequence(1, 2, 3, 4)
    assert_that("foobar").contains_sequence("o", "o", "b")

    fred = Person("fred")
    joe = Person("joe")
    bob = Person("bob")
    assert_that([fred, joe, bob]).contains_sequence(fred, joe)


def test_contains_sequence_string_advances_past_match():
    # the search must advance past the first match, or arithmetic that re-finds the same "X" passes falsely
    with pytest.raises(AssertionError):
        assert_that("aX").contains_sequence("X", "X")


def test_contains_sequence_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence(4, 5)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain sequence <4, 5>, but did not. No run started with <4>."
    )


def test_contains_sequence_tail_prefix_absent_fails_cleanly():
    # the full sequence runs past the end: the scan must fail cleanly, never walk off into IndexError
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence(3, 9)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to contain sequence <3, 9>, but did not. The longest run that matched was <3>."
    )


def test_contains_sequence_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_sequence(1, 2)
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_contains_sequence_no_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([1, 2, 3]).contains_sequence()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_sequence_string_substrings():
    assert_that("foobar").contains_sequence("foo", "bar")
    assert_that("foobar").contains_sequence("f", "bar")
    assert_that("foobar").contains_sequence("fo", "ob", "ar")
    assert_that("foobar").contains_sequence("foo")
    assert_that("foobar").contains_sequence("bar")
    assert_that("abcdef").contains_sequence("ab", "cd", "ef")
    assert_that("abcdef").contains_sequence("a", "f")
    assert_that("hello world").contains_sequence("hello", "world")


def test_contains_sequence_string_substrings_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_sequence("bar", "foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foobar> to contain sequence <'bar', 'foo'>, but <foo> was not found after <bar>."
    )


def test_contains_sequence_string_substrings_not_found():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_sequence("foo", "xyz")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foobar> to contain sequence <'foo', 'xyz'>, but <xyz> was not found after <foo>."
    )


def test_contains_sequence_string_bad_arg_type():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foobar").contains_sequence("foo", 123)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, to match val, but was <123> (int)")


def test_contains_duplicates():
    assert_that(["a", "b", "c", "a"]).contains_duplicates()
    assert_that(("a", "b", "c", "a")).contains_duplicates()
    assert_that([1, 2, 3, 3]).contains_duplicates()
    assert_that((1, 2, 3, 3)).contains_duplicates()
    assert_that("foobar").contains_duplicates()

    fred = Person("fred")
    joe = Person("joe")
    assert_that([fred, joe, fred]).contains_duplicates()


def test_contains_duplicates_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).contains_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("Expected <[1, 2, 3]> to contain duplicates, but did not.")


def test_contains_duplicates_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_does_not_contain_duplicates():
    assert_that(["a", "b", "c"]).does_not_contain_duplicates()
    assert_that(("a", "b", "c")).does_not_contain_duplicates()
    assert_that({"a", "b", "c"}).does_not_contain_duplicates()
    assert_that([1, 2, 3]).does_not_contain_duplicates()
    assert_that((1, 2, 3)).does_not_contain_duplicates()
    assert_that({1, 2, 3}).does_not_contain_duplicates()
    assert_that("fobar").does_not_contain_duplicates()

    fred = Person("fred")
    joe = Person("joe")
    assert_that([fred, joe]).does_not_contain_duplicates()


def test_does_not_contain_duplicates_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3, 3]).does_not_contain_duplicates()
    assert_that(str(exc_info.value)).starts_with(
        "Expected <[1, 2, 3, 3]> to not contain duplicates, but <3> was repeated."
    )


def test_does_not_contain_duplicates_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_contain_duplicates()
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_contains_duplicates_unhashable_items():
    assert_that([{"a": 1}, {"b": 2}, {"a": 1}]).contains_duplicates()
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"b": 2}]).contains_duplicates()


def test_does_not_contain_duplicates_unhashable_items():
    assert_that([{"a": 1}, {"b": 2}]).does_not_contain_duplicates()
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"a": 1}]).does_not_contain_duplicates()


def test_contains_only_once_unhashable_items():
    assert_that([{"a": 1}, {"b": 2}]).contains_only_once({"a": 1})
    with pytest.raises(AssertionError):
        assert_that([{"a": 1}, {"a": 1}]).contains_only_once({"a": 1})


def test_is_empty():
    assert_that([]).is_empty()
    assert_that(()).is_empty()
    assert_that({}).is_empty()


def test_is_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b"]).is_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected <['a', 'b']> to be empty, but was not.")


def test_is_not_empty():
    assert_that(["a", "b"]).is_not_empty()
    assert_that((1, 2)).is_not_empty()
    assert_that({"a": 1, "b": 2}).is_not_empty()
    assert_that({"a", "b"}).is_not_empty()


def test_is_not_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([]).is_not_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected not empty, but was empty.")


def test_starts_with():
    assert_that(["a", "b", "c"]).starts_with("a")
    assert_that((1, 2, 3)).starts_with(1)

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered.keys()).starts_with("z")
    assert_that(ordered.values()).starts_with(9)
    assert_that(ordered.items()).starts_with(("z", 9))


def test_starts_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).starts_with("d")
    assert_that(str(exc_info.value)).is_equal_to("Expected ['a', 'b', 'c'] to start with <d>, but did not.")


def test_starts_with_bad_val_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([]).starts_with("a")
    assert_that(str(exc_info.value)).is_equal_to("val must not be empty")


def test_starts_with_bad_prefix_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).starts_with("a", "b")
    assert_that(str(exc_info.value)).contains("starts_with() takes 2 positional arguments but 3 were given")


def test_ends_with():
    assert_that(["a", "b", "c"]).ends_with("c")
    assert_that((1, 2, 3)).ends_with(3)

    ordered = collections.OrderedDict([("z", 9), ("x", 7), ("y", 8)])
    assert_that(ordered.keys()).ends_with("y")
    assert_that(ordered.values()).ends_with(8)
    assert_that(ordered.items()).ends_with(("y", 8))


def test_ends_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).ends_with("d")
    assert_that(str(exc_info.value)).is_equal_to("Expected ['a', 'b', 'c'] to end with <d>, but did not.")


def test_ends_with_bad_val_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that([]).ends_with("a")
    assert_that(str(exc_info.value)).is_equal_to("val must not be empty")


def test_ends_with_bad_prefix_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b", "c"]).ends_with("b", "c")
    assert_that(str(exc_info.value)).contains("ends_with() takes 2 positional arguments but 3 were given")


def test_chaining():
    assert_that(["a", "b", "c"]).is_type_of(list).is_length(3).contains("a").does_not_contain("x")
    assert_that(["a", "b", "c"]).is_type_of(list).is_length(3).contains("a", "b").does_not_contain("x", "y")


def test_list_of_lists():
    nested = [[1, 2, 3], ["a", "b", "c"], (4, 5, 6)]
    assert_that(nested).is_length(3)
    assert_that(nested).is_equal_to([[1, 2, 3], ["a", "b", "c"], (4, 5, 6)])

    assert_that(nested).contains([1, 2, 3])
    assert_that(nested).contains(["a", "b", "c"])
    assert_that(nested).contains((4, 5, 6))

    assert_that(nested).starts_with([1, 2, 3])
    assert_that(nested).ends_with((4, 5, 6))

    assert_that(nested[0]).is_equal_to([1, 2, 3])
    assert_that(nested[2]).is_equal_to((4, 5, 6))

    assert_that(nested[0][0]).is_equal_to(1)
    assert_that(nested[2][2]).is_equal_to(6)


def test_list_of_dicts():
    dicts = [{"a": 1}, {"b": 2}, {"c": 3}]
    assert_that(dicts).is_length(3)
    assert_that(dicts).is_equal_to([{"a": 1}, {"b": 2}, {"c": 3}])

    assert_that(dicts).contains({"a": 1})
    assert_that(dicts).contains({"b": 2})
    assert_that(dicts).contains({"c": 3})

    assert_that(dicts).starts_with({"a": 1})
    assert_that(dicts).ends_with({"c": 3})

    assert_that(dicts[0]).is_equal_to({"a": 1})
    assert_that(dicts[2]).is_equal_to({"c": 3})

    assert_that(dicts[0]["a"]).is_equal_to(1)
    assert_that(dicts[2]["c"]).is_equal_to(3)


class Person:
    def __init__(self, name):
        self.name = name


class TestContainsClosestElement:
    def test_closest_element_pinpoints_difference(self):
        haystack = [{"id": 1, "name": "Alice", "role": "admin"}, {"id": 2, "name": "Bob", "role": "user"}]
        with pytest.raises(AssertionError) as exc:
            assert_that(haystack).contains({"id": 2, "name": "Bob", "role": "ADMIN"})
        assert_that(str(exc.value)).contains("Closest element").contains("role ('user' != 'ADMIN')")

    def test_closest_element_populates_structured_diff(self):
        haystack = [{"id": 2, "name": "Bob", "role": "user"}]
        with pytest.raises(AssertionError) as exc:
            assert_that(haystack).contains({"id": 2, "name": "Bob", "role": "ADMIN"})
        assert_that([entry.path for entry in exc.value.diff.entries]).contains("role")

    def test_unrelated_needle_has_no_closest(self):
        with pytest.raises(AssertionError) as exc:
            assert_that([{"id": 1, "name": "Alice"}]).contains({"zzz": 999})
        assert_that(str(exc.value)).does_not_contain("Closest element")

    def test_scalar_haystack_with_dict_needle_has_no_closest(self):
        with pytest.raises(AssertionError) as exc:
            assert_that([1, 2, 3]).contains({"a": 1})
        assert_that(str(exc.value)).does_not_contain("Closest element")

    def test_closest_is_the_most_similar_of_several(self):
        with pytest.raises(AssertionError) as exc:
            assert_that([{"id": 2, "x": 1, "y": 2}, {"id": 2, "x": 9, "y": 9}]).contains({"id": 2, "x": 1, "y": 1})
        assert_that(str(exc.value)).contains("{'id': 2, 'x': 1, 'y': 2}").contains("y (2 != 1)")

    def test_many_differences_are_truncated(self):
        # 4 differing paths, limit 3 -> reports exactly "and 1 more" (pins the count, not just its presence)
        with pytest.raises(AssertionError) as exc:
            assert_that([{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}]).contains(
                {"a": 1, "b": 99, "c": 99, "d": 99, "e": 99}
            )
        assert_that(str(exc.value)).contains("Closest element").contains("and 1 more")

    def test_differences_exactly_at_limit_have_no_more_suffix(self):
        # exactly `limit` (3) differing paths -> all shown, no "and 0 more" suffix (boundary at == limit)
        with pytest.raises(AssertionError) as exc:
            assert_that([{"a": 1, "b": 2, "c": 3, "d": 4}]).contains({"a": 1, "b": 99, "c": 99, "d": 99})
        assert_that(str(exc.value)).contains("Closest element").does_not_contain("more")


class TestContainsExactly:
    def test_list(self):
        assert_that([1, 2, 3]).contains_exactly(1, 2, 3)

    def test_tuple(self):
        assert_that((1, 2, 3)).contains_exactly(1, 2, 3)

    def test_string_chars(self):
        assert_that("abc").contains_exactly("a", "b", "c")

    def test_wrong_order_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 3, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_missing_items_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_exactly(1, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_extra_items_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains_exactly(1, 2, 3)
        assert_that(str(exc_info.value)).contains("to contain exactly")

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_exactly()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_exactly(1)
        assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <42> (int)")

    def test_unhashable_items_failure(self):
        # the failure path used Counter and crashed with TypeError on unhashable items
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([[1], [2]]).contains_exactly([2], [1], [3])
        assert_that(str(exc_info.value)).contains("to contain exactly")
        entries = exc_info.value.diff.entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [("missing", None, [3])]
        )


class TestContainsExactlyInAnyOrder:
    def test_list(self):
        assert_that([3, 1, 2]).contains_exactly_in_any_order(1, 2, 3)

    def test_same_order(self):
        assert_that([1, 2, 3]).contains_exactly_in_any_order(1, 2, 3)

    def test_tuple(self):
        assert_that((2, 3, 1)).contains_exactly_in_any_order(1, 2, 3)

    def test_string_chars(self):
        assert_that("cba").contains_exactly_in_any_order("a", "b", "c")

    def test_duplicates_counted(self):
        assert_that(["b", "a", "b"]).contains_exactly_in_any_order("a", "b", "b")

    def test_unhashable_items(self):
        assert_that([[3], [1, 2]]).contains_exactly_in_any_order([1, 2], [3])

    def test_mixed_non_comparable_types_diff_fails_cleanly(self):
        # non-comparable items sort by repr for the message; natural order raises TypeError on mixed types
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, "a"]).contains_exactly_in_any_order(2, "b")
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1, 'a']> to contain exactly <2, 'b'> in any order, but did not."
        )

    def test_extra_duplicate_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 2]).contains_exactly_in_any_order(1, 2)
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1, 2, 2]> to contain exactly <1, 2> in any order, but did not."
            " <2> is held 2 times and was asked for 1 time."
        )

    def test_missing_duplicate_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2]).contains_exactly_in_any_order(1, 2, 2)
        assert_that(str(exc_info.value)).contains("to contain exactly").contains("in any order")

    def test_failure_diff_entries(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([1, 4]).contains_exactly_in_any_order(1, 2)
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("contains")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in diff.entries]).is_equal_to(
            [("extra", 4, None), ("missing", None, 2)]
        )

    def test_unhashable_items_failure(self):
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([[1], [1]]).contains_exactly_in_any_order([1], [2])
        assert_that(str(exc_info.value)).contains("in any order")
        entries = exc_info.value.diff.entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [("extra", [1], None), ("missing", None, [2])]
        )

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_exactly_in_any_order()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_exactly_in_any_order(1)
        assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <42> (int)")


def _holds(wanted, held):
    return wanted is held or wanted == held


def _best(held, wanted):
    """The size of a largest pairing, by trying every assignment: the oracle for small sides."""
    if len(held) < len(wanted):
        return max(
            sum(_holds(one, item) for one, item in zip(arranged, held, strict=True))
            for arranged in itertools.permutations(wanted, len(held))
        )
    return max(
        sum(_holds(one, item) for one, item in zip(wanted, arranged, strict=True))
        for arranged in itertools.permutations(held, len(wanted))
    )


class TestAnyOrderPairsRatherThanWalking:
    """Items that cannot be counted were matched first-fit, in the order they were written.

    Against ``[1, 5]``, ``match.greater_than(0)`` written first took the 1, and the ``1`` after it found none
    left: "<1> is held 1 time and was asked for 2 times", while the other order of the same items passed.
    """

    def test_a_matcher_written_before_the_item_it_could_take(self):
        assert_that([1, 5]).contains_exactly_in_any_order(match.greater_than(0), 1)
        assert_that([1.0, 3.0]).contains_exactly_in_any_order(pytest.approx(1.0, abs=5), 1.0)

    def test_every_order_of_both_sides_answers_as_trying_every_assignment_does(self):
        pool = [match.greater_than(0), match.equal_to(1), match.less_than(6), 5, 9, match.greater_than(6)]
        for held_size, wanted_size in itertools.product((1, 2, 3), repeat=2):
            for held in itertools.permutations([1, 5, 9], held_size):
                for wanted in itertools.permutations(pool, wanted_size):
                    best = _best(held, wanted)
                    try:
                        assert_that(list(held)).contains_exactly_in_any_order(*wanted)
                    except AssertionFailure as failure:
                        entries = failure.diff.entries
                        assert_that(best == held_size == wanted_size).described_as(f"{held} {wanted}").is_false()
                        assert_that([entry.path for entry in entries].count("extra")).is_equal_to(held_size - best)
                        assert_that([entry.path for entry in entries].count("missing")).is_equal_to(wanted_size - best)
                    else:
                        assert_that(best == held_size == wanted_size).described_as(f"{held} {wanted}").is_true()

    def test_a_pass_costs_the_first_fit_walk_alone(self):
        class Counted:
            calls = 0
            __hash__ = None

            def __init__(self, value):
                self.value = value

            def __eq__(self, other):
                Counted.calls += 1
                return isinstance(other, Counted) and other.value == self.value

        assert_that([Counted(i) for i in range(50)]).contains_exactly_in_any_order(*(Counted(i) for i in range(50)))
        assert_that(Counted.calls).is_equal_to(50)

    def test_no_pair_is_asked_twice_on_the_way_to_a_pairing(self):
        asked = []

        class Positive(BaseMatcher):
            def matches(self, value):
                asked.append(value)
                return value > 0

            def describe(self):
                return "a positive value"

        assert_that([1, 5]).contains_exactly_in_any_order(Positive(), 1)
        assert_that(asked).is_equal_to([1, 5])

    def test_the_order_message_names_the_place_once_the_items_pair(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 5]).contains_exactly(match.greater_than(0), 1)
        assert_that(str(failure.value)).contains("Same items, but the order differs at index 1.")


class TestContainsInOrder:
    def test_all_present(self):
        assert_that([1, 5, 2, 8, 3]).contains_in_order(1, 2, 3)

    def test_contiguous(self):
        assert_that([1, 2, 3]).contains_in_order(1, 2, 3)

    def test_strings(self):
        assert_that(["a", "x", "b", "y", "c"]).contains_in_order("a", "b", "c")

    def test_single_item(self):
        assert_that([1, 2, 3]).contains_in_order(2)

    def test_wrong_order_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_in_order(3, 1)
        assert_that(str(exc_info.value)).contains("in order, but")

    def test_missing_item_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_in_order(1, 4)
        assert_that(str(exc_info.value)).contains("in order, but")

    def test_empty_args_failure(self):
        with pytest.raises(ValueError) as exc_info:
            assert_that([1]).contains_in_order()
        assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")

    def test_not_iterable_failure(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(42).contains_in_order(1)
        assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <42> (int)")


class TestOrderingFailuresNameTheBreakPoint:
    """ "but did not" makes the reader re-derive where the run stopped; the loops already know."""

    def test_sequence_names_the_longest_matching_run(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_sequence(1, 2, 9)
        assert_that(str(exc_info.value)).contains("The longest run that matched was <1, 2>")

    def test_a_run_that_starts_too_late_to_fit_is_a_run_that_matched(self):
        # 3 is in the list, at a place the two-element run cannot fit: "no run started with <3>" was false of it
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_sequence(3, 4)
        assert_that(str(exc_info.value)).ends_with("but did not. The longest run that matched was <3>.")

    def test_a_value_shorter_than_the_sequence_names_how_far_it_lined_up(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1]).contains_sequence(1, 2)
        assert_that(str(exc_info.value)).is_equal_to(
            "Expected <[1]> to contain sequence <1, 2>, but did not. The longest run that matched was <1>."
        )
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1]).contains_sequence(2, 1)
        assert_that(str(exc_info.value)).ends_with("but did not. No run started with <2>.")
        assert_that([1, 2]).contains_sequence(1, 2)
        assert_that([0, 1, 2]).contains_sequence(1, 2)

    def test_a_late_run_is_counted_for_the_message_and_decides_nothing(self):
        class Raising:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError("no equality")

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                return "raising"

        class Flip:
            asked = 0

            def __eq__(self, other: object) -> bool:
                Flip.asked += 1
                return Flip.asked > 1

            __hash__ = None  # ty: ignore[invalid-assignment]  # as above

            def __repr__(self) -> str:
                return "flip"

        # the element past the last start that fits was never compared, and comparing it for the message raised
        with pytest.raises(AssertionFailure) as exc_info:
            assert_that([0, Raising()]).contains_sequence(1, 2)
        assert_that(exc_info.value._message).is_equal_to(
            "Expected <[0, raising]> to contain sequence <1, 2>, but did not. No run started with <1>."
        )
        # the walk that decided is not run again for it: this element answers otherwise the second time
        with pytest.raises(AssertionFailure):
            assert_that([Flip(), 2, decimal.Decimal("sNaN")]).contains_sequence(1, 2)

    def test_string_sequence_names_the_substring_that_broke_the_chain(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that("foobar").contains_sequence("foo", "xyz")
        assert_that(str(exc_info.value)).contains("<xyz> was not found after <foo>")

    def test_in_order_names_the_item_that_did_not_follow(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).contains_in_order(1, 2, 9)
        assert_that(str(exc_info.value)).contains("<9> did not follow after <1, 2>")

    def test_duplicates_name_the_repeated_values(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 1, 2, 2, 3]).does_not_contain_duplicates()
        exc = exc_info.value
        assert_that(str(exc)).contains("<1, 2> were repeated")
        assert_that([entry.actual for entry in exc.diff.entries]).is_equal_to([1, 2])

    def test_duplicates_work_on_unhashable_items(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that([{"a": 1}, {"a": 1}]).does_not_contain_duplicates()
        assert_that(str(exc_info.value)).contains("was repeated")


class TestContainsOnAOneShotIterator:
    """`contains` tests membership once per argument, and `in` consumes a generator up to the match.
    Before the value was drained first, the second argument resumed from where the first stopped, so
    `contains(3, 1)` reported 1 as missing while the same call on a list passed."""

    @pytest.mark.parametrize(
        "items",
        [(1, 2, 3), (3, 1), (2, 1), (3, 2, 1)],
        ids=["in order", "reversed pair", "out of order", "fully reversed"],
    )
    def test_the_order_of_the_arguments_does_not_decide_the_verdict(self, items):
        assert_that(x for x in [1, 2, 3]).contains(*items)
        assert_that([1, 2, 3]).contains(*items)

    def test_a_genuinely_missing_item_still_fails(self):
        with pytest.raises(AssertionError, match="to contain item <9>"):
            assert_that(x for x in [1, 2, 3]).contains(9)

    def test_the_message_names_the_contents_rather_than_a_spent_generator(self):
        # the repr of an exhausted generator tells the reader nothing about what was compared
        with pytest.raises(AssertionError) as exc_info:
            assert_that(x for x in [1, 2, 3]).contains(9)
        assert_that(str(exc_info.value)).contains("[1, 2, 3]").does_not_contain("generator object")

    def test_the_closest_element_hint_survives(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(x for x in [{"id": 1, "name": "a"}]).contains({"id": 1, "name": "b"})
        assert_that(str(exc_info.value)).contains("Closest element")

    def test_a_re_iterable_value_is_handed_back_untouched(self):
        values = [1, 2, 3]
        assert_that(values).contains(1)
        assert_that(values).is_equal_to([1, 2, 3])

    def test_a_matcher_argument_works_on_a_generator_too(self):
        from assertpy import match

        assert_that(x for x in [1, 2, 3]).contains(match.greater_than(2), match.less_than(2))


class TestOtherAssertionsOnAOneShotIterator:
    """The same defect class as `contains`: an assertion that walks its subject twice, once to decide
    and again to describe or to check a second condition, saw an empty value the second time."""

    def test_contains_only_agrees_with_the_list_it_was_built_from(self):
        assert_that(x for x in [1, 2, 3]).contains_only(1, 2, 3)
        assert_that([1, 2, 3]).contains_only(1, 2, 3)

    def test_contains_only_once_agrees_with_the_list(self):
        assert_that(x for x in [1, 2, 3]).contains_only_once(1, 2, 3)
        assert_that([1, 2, 3]).contains_only_once(1, 2, 3)

    def test_any_satisfy_counts_what_it_actually_examined(self):
        messages = []
        for value in ((x for x in [1, 2, 3]), [1, 2, 3]):
            with pytest.raises(AssertionError) as exc_info:
                assert_that(value).any_satisfy(lambda item: item > 99)
            messages.append(str(exc_info.value))
        assert_that(messages[0]).contains("none of the 3 did").is_equal_to(messages[1])

    def test_contains_sequence_walks_by_index_and_needs_a_real_sequence(self):
        assert_that(x for x in [1, 2, 3]).contains_sequence(1, 2)
        assert_that([1, 2, 3]).contains_sequence(1, 2)

    def test_a_failing_contains_sequence_names_the_contents(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(x for x in [1, 2, 3]).contains_sequence(3, 1)
        assert_that(str(exc_info.value)).contains("[1, 2, 3]").does_not_contain("not iterable")

    def test_a_set_is_refused_by_name_rather_than_called_not_iterable(self):
        with pytest.raises(TypeError, match="must be a sequence"):
            assert_that({1, 2, 3}).contains_sequence(1, 2)

    def test_a_failing_contains_only_names_the_contents(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(x for x in [1, 2, 3]).contains_only(1, 2)
        assert_that(str(exc_info.value)).contains("[1, 2, 3]").does_not_contain("generator object")


class TestDoesNotContainAcceptsMatchers:
    """`contains` has taken a matcher since it was written and its own negation did not, so a matcher
    handed here was compared with `in` and the assertion answered a different question."""

    def test_a_matcher_no_item_satisfies_passes(self):
        from assertpy import match

        assert_that([1, 2, 3]).does_not_contain(match.greater_than(99))

    def test_a_matcher_some_item_satisfies_fails(self):
        from assertpy import match

        with pytest.raises(AssertionError, match="a value greater than <2>"):
            assert_that([1, 2, 3]).does_not_contain(match.greater_than(2))

    def test_matchers_and_plain_values_mix(self):
        from assertpy import match

        assert_that([1, 2, 3]).does_not_contain(9, match.greater_than(99))
        with pytest.raises(AssertionError) as exc_info:
            assert_that([1, 2, 3]).does_not_contain(9, match.greater_than(2))
        assert_that(str(exc_info.value)).contains("a value greater than <2>").does_not_contain("<9>, but")

    def test_it_works_on_a_one_shot_iterator_too(self):
        from assertpy import match

        assert_that(x for x in [1, 2, 3]).does_not_contain(match.greater_than(99), 9)


_WANTED = st.one_of(
    st.integers(0, 4),
    st.builds(match.greater_than, st.integers(0, 4)),
    st.builds(match.less_than, st.integers(0, 4)),
    st.builds(match.equal_to, st.integers(0, 4)),
)


class TestAnyOrderOverAnyItems:
    @settings(deadline=None)
    @example(held=[1, 5], wanted=[match.greater_than(0), 1])
    @given(held=st.lists(st.integers(0, 5), max_size=4), wanted=st.lists(_WANTED, min_size=1, max_size=4))
    def test_the_verdict_and_the_counts_are_the_largest_pairing(self, held, wanted):
        best = _best(held, wanted) if held else 0
        try:
            assert_that(list(held)).contains_exactly_in_any_order(*wanted)
        except AssertionFailure as failure:
            paths = [entry.path for entry in failure.diff.entries]
            assert_that(best == len(held) == len(wanted)).is_false()
            assert_that(paths.count("extra")).is_equal_to(len(held) - best)
            assert_that(paths.count("missing")).is_equal_to(len(wanted) - best)
        else:
            assert_that(best == len(held) == len(wanted)).is_true()
