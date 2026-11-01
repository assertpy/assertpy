from dataclasses import dataclass

import pytest

from assertpy import assert_that, match


@dataclass
class Item:
    name: str
    tags: list[str]
    value: int


ITEMS = [
    Item(name="Alice", tags=["admin", "active"], value=10),
    Item(name="Bob", tags=["user"], value=-5),
    Item(name="Carol", tags=["admin"], value=3),
]


class TestFilteredOn:
    def test_with_callable(self):
        assert_that([1, -2, 3, -4]).filtered_on(lambda value: value > 0).is_length(2)

    def test_with_matcher(self):
        assert_that([1, -2, 3, -4]).filtered_on(match.is_positive()).is_length(2)

    def test_with_a_matcher_that_does_not_inherit_the_base_class(self):
        # this one tested for a `BaseMatcher` subclass, so a custom matcher was called as a plain function
        class IsPositive:
            def matches(self, item):
                return item > 0

            def describe(self):
                return "is positive"

            def describe_mismatch(self, item):
                return f"was {item}"

        assert_that([1, -2, 3, -4]).filtered_on(IsPositive()).is_length(2)

    def test_empty_result(self):
        assert_that([1, 2, 3]).filtered_on(lambda value: value > 10).is_empty()

    def test_all_match(self):
        assert_that([2, 4, 6]).filtered_on(lambda value: value % 2 == 0).is_length(3)

    def test_on_objects(self):
        result = assert_that(ITEMS).filtered_on(lambda item: item.value > 0)
        result.is_length(2)

    def test_on_objects_with_matcher(self):
        assert_that(ITEMS).filtered_on(match.has_property("name", match.contains_string("o"))).is_length(2)

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).filtered_on(lambda value: value > 0)

    def test_preserves_description(self):
        result = assert_that([1, 2]).described_as("nums").filtered_on(lambda value: value > 0)
        assert_that(result.description).is_equal_to("nums")


class TestMapped:
    def test_basic(self):
        assert_that(["a", "b", "c"]).mapped(str.upper).contains("A", "B")

    def test_with_lambda(self):
        assert_that([1, 2, 3]).mapped(lambda value: value * 2).is_equal_to([2, 4, 6])

    def test_on_objects(self):
        assert_that(ITEMS).mapped(lambda item: item.name).contains("Alice", "Bob")

    def test_empty(self):
        assert_that([]).mapped(str.upper).is_empty()

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).mapped(str.upper)


class TestFlatMapped:
    def test_basic(self):
        assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "b", "c", "d")

    def test_on_objects(self):
        assert_that(ITEMS).flat_mapped(lambda item: item.tags).contains("admin", "user")

    def test_empty_inner(self):
        assert_that([[], [], []]).flat_mapped(lambda value: value).is_empty()

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).flat_mapped(list)


class TestFirst:
    def test_basic(self):
        assert_that([10, 20, 30]).first().is_equal_to(10)

    def test_single_element(self):
        assert_that([42]).first().is_equal_to(42)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            assert_that([]).first()

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).first()


class TestLast:
    def test_basic(self):
        assert_that([10, 20, 30]).last().is_equal_to(30)

    def test_single_element(self):
        assert_that([42]).last().is_equal_to(42)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            assert_that([]).last()

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).last()


class TestElement:
    def test_basic(self):
        assert_that([10, 20, 30]).element(1).is_equal_to(20)

    def test_first_element(self):
        assert_that([10, 20, 30]).element(0).is_equal_to(10)

    def test_last_element(self):
        assert_that([10, 20, 30]).element(2).is_equal_to(30)

    def test_out_of_range_raises(self):
        with pytest.raises(IndexError, match="out of range"):
            assert_that([10, 20]).element(5)

    def test_negative_index_raises(self):
        with pytest.raises(IndexError, match="out of range"):
            assert_that([10, 20]).element(-1)

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).element(0)


class TestSingle:
    def test_basic(self):
        assert_that([42]).single().is_equal_to(42)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="was empty"):
            assert_that([]).single()

    def test_multiple_raises(self):
        with pytest.raises(ValueError, match="had 3 elements"):
            assert_that([1, 2, 3]).single()

    def test_non_iterable_raises(self):
        with pytest.raises(TypeError, match="val must be iterable"):
            assert_that(42).single()


class TestPipelineChaining:
    def test_filtered_mapped_first(self):
        assert_that(ITEMS).filtered_on(lambda i: i.value > 0).mapped(lambda i: i.name).first().is_equal_to("Alice")

    def test_filtered_is_length(self):
        assert_that(ITEMS).filtered_on(match.has_property("value", match.is_positive())).is_length(2)

    def test_mapped_contains(self):
        assert_that(ITEMS).mapped(lambda i: i.name).contains("Alice", "Carol")

    def test_flat_mapped_contains_all_tags(self):
        assert_that(ITEMS).flat_mapped(lambda i: i.tags).contains("admin", "active", "user")

    def test_element_then_assert(self):
        assert_that(ITEMS).element(0).has_name("Alice")

    def test_chaining_with_not(self):
        assert_that(ITEMS).filtered_on(lambda i: i.value > 0).not_.is_empty()
