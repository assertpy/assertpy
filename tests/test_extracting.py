import sys
import traceback
import typing
from collections import namedtuple

import pytest

from assertpy import assert_that
from tests.optional import needs


class Person:
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def say_hello(self, name):
        return f"Hello, {name}!"


fred = Person("Fred", "Smith", 12)
john = Person("John", "Jones", 9.5)
people = [fred, john]


def test_extracting_property():
    assert_that(people).extracting("first_name").contains("Fred", "John")


def test_extracting_multiple_properties():
    assert_that(people).extracting("first_name", "last_name", "shoe_size").contains(
        ("Fred", "Smith", 12), ("John", "Jones", 9.5)
    )


def test_extracting_zero_arg_method():
    assert_that(people).extracting("full_name").contains("Fred Smith", "John Jones")


def test_extracting_property_and_method():
    assert_that(people).extracting("first_name", "full_name").contains(("Fred", "Fred Smith"), ("John", "John Jones"))


def test_extracting_dict():
    people_as_dicts = [{"first_name": person.first_name, "last_name": person.last_name} for person in people]
    assert_that(people_as_dicts).extracting("first_name").contains("Fred", "John")
    assert_that(people_as_dicts).extracting("last_name").contains("Smith", "Jones")


def test_extracting_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).extracting("bar")
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_extracting_bad_val_str_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").extracting("bar")
    assert_that(str(exc_info.value)).is_equal_to("val must be a collection rather than a string, but was <'foo'> (str)")


def test_extracting_empty_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting()
    assert_that(str(exc_info.value)).is_equal_to("one or more name args must be given")


def test_extracting_bad_property_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting("foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "item does not have property or zero-arg method <foo> (at index 0, item is <Person>)"
    )


def test_extracting_too_many_args_method_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting("say_hello")
    assert_that(str(exc_info.value)).is_equal_to(
        "item method <say_hello()> exists, but is not zero-arg method (at index 0, item is <Person>)"
    )


def test_extracting_reports_the_index_of_the_failing_item():
    # the whole point of the localization: one bad item in a long list must not send the reader hunting
    with pytest.raises(ValueError) as exc_info:
        assert_that([{"name": "a"}, {"name": "b"}, 42]).extracting("name")
    assert_that(str(exc_info.value)).ends_with("(at index 2, item is <int>)")


def test_extracting_suggests_a_close_attribute_name():
    with pytest.raises(ValueError) as exc_info:
        assert_that(people).extracting("frist_name")
    assert_that(str(exc_info.value)).contains("did you mean 'first_name'?")


def test_extracting_tells_a_broken_property_from_a_missing_one():
    # hasattr() reports a raising accessor as missing, which produced "does not have <total>; did you mean 'total'?"
    class Order:
        @property
        def total(self):
            raise AttributeError("price table not loaded")

    with pytest.raises(ValueError) as exc_info:
        assert_that([Order()]).extracting("total")
    message = str(exc_info.value)
    assert_that(message).contains("has property or zero-arg method <total>, but reading it raised")
    assert_that(message).contains("price table not loaded")
    assert_that(message).does_not_contain("did you mean")
    assert_that(exc_info.value.__cause__).is_instance_of(AttributeError)


def test_extracting_reports_an_unset_slot_as_a_broken_read():
    class Slotted:
        __slots__ = ("name",)

    with pytest.raises(ValueError) as exc_info:
        assert_that([Slotted()]).extracting("name")
    assert_that(str(exc_info.value)).contains("but reading it raised")


def test_extracting_lets_a_user_value_error_through_untouched():
    # the wrapper re-raises only this module's errors, or a failing property loses the traceback into user code
    class Flaky:
        @property
        def name(self):
            raise ValueError("bad state from user code")

    with pytest.raises(ValueError) as exc_info:
        assert_that([Flaky()]).extracting("name")
    assert_that(str(exc_info.value)).is_equal_to("bad state from user code")
    assert_that([frame.name for frame in traceback.extract_tb(exc_info.tb)]).contains("name")


def test_extracting_survives_an_item_with_a_broken_dir():
    class Hostile:
        def __dir__(self):
            raise RuntimeError("boom")

    with pytest.raises(ValueError) as exc_info:
        assert_that([Hostile()]).extracting("foo")
    assert_that(str(exc_info.value)).does_not_contain("did you mean")


def test_extracting_dict_missing_key_failure():
    people_as_dicts = [{"first_name": person.first_name, "last_name": person.last_name} for person in people]
    with pytest.raises(ValueError) as exc_info:
        assert_that(people_as_dicts).extracting("foo")
    assert_that(str(exc_info.value)).matches(r"item keys \[.*\] did not contain key <foo>")


def test_described_as_with_extracting():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(people).described_as("extra msg").extracting("first_name").contains("Fred", "Bob")
    assert_that(str(exc_info.value)).is_equal_to(
        "[extra msg] Expected <['Fred', 'John']> to contain items <'Fred', 'Bob'>, but did not contain <Bob>."
    )


def test_described_as_with_double_extracting():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(people).described_as("extra msg").extracting("first_name").described_as("other msg").contains(
            "Fred", "Bob"
        )
    assert_that(str(exc_info.value)).is_equal_to(
        "[other msg] Expected <['Fred', 'John']> to contain items <'Fred', 'Bob'>, but did not contain <Bob>."
    )


users = [
    {"user": "Fred", "age": 36, "active": True},
    {"user": "Bob", "age": 40, "active": False},
    {"user": "Johnny", "age": 13, "active": True},
]


def test_extracting_filter():
    assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
    assert_that(users).extracting("user", filter={"active": False}).is_equal_to(["Bob"])
    assert_that(users).extracting("user", filter={"age": 36, "active": True}).is_equal_to(["Fred"])
    assert_that(users).extracting("user", filter=lambda x: x["age"] > 20).is_equal_to(["Fred", "Bob"])
    assert_that(users).extracting("user", filter=lambda x: x["age"] < 10).is_empty()


def test_extracting_filter_none():
    assert_that(users).extracting("user", filter=None).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_filter_bad_type():
    with pytest.raises(TypeError, match="given filter arg must be a str, a dict, or a callable"):
        assert_that(users).extracting("user", filter=123)


def test_extracting_filter_ignore_bad_key_types():
    assert_that(users).extracting("user", filter={"active": True, 123: "foo"}).is_equal_to(["Fred", "Johnny"])


def test_extracting_filter_custom_func():
    def _f(x):
        return x["user"] == "Bob" or x["age"] == 13

    assert_that(users).extracting("user", filter=_f).is_equal_to(["Bob", "Johnny"])


def test_extracting_filter_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter="foo")
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter={"foo": "bar"})
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_multi_item_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", filter={"age": 36, "active": True, "foo": "bar"})
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_filter_lambda_failure():
    with pytest.raises(KeyError) as exc_info:
        assert_that(users).extracting("user", filter=lambda x: x["foo"] > 0)
    assert_that(str(exc_info.value)).is_equal_to("'foo'")


def test_extracting_filter_custom_func_failure():
    def _f(x):
        raise RuntimeError("foobar!")

    with pytest.raises(RuntimeError) as exc_info:
        assert_that(users).extracting("user", filter=_f)
    assert_that(str(exc_info.value)).is_equal_to("foobar!")


def test_extracting_filter_bad_values():
    bad = [{"user": "Fred", "age": 36}, {"user": "Bob", "age": "bad"}, {"user": "Johnny", "age": 13}]
    with pytest.raises(TypeError) as exc_info:
        assert_that(bad).extracting("user", filter=lambda x: x["age"] > 20)
    if sys.version_info[1] <= 5:
        assert_that(str(exc_info.value)).contains("unorderable types")
    else:
        assert_that(str(exc_info.value)).contains("not supported between instances of 'str' and 'int'")


def test_extracting_sort():
    assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
    assert_that(users).extracting("user", sort=["active", "age"]).is_equal_to(["Bob", "Johnny", "Fred"])
    assert_that(users).extracting("user", sort=("active", "age")).is_equal_to(["Bob", "Johnny", "Fred"])
    assert_that(users).extracting("user", sort=lambda x: -x["age"]).is_equal_to(["Bob", "Fred", "Johnny"])


def test_extracting_sort_none():
    assert_that(users).extracting("user", sort=None).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_sort_bad_type():
    # mirrors filter: a wrong arg is a mistake, and unsorted items surface later as a baffling order mismatch
    with pytest.raises(TypeError, match="given sort arg must be a str, an iterable, or a callable"):
        assert_that(users).extracting("user", sort=123)


def test_extracting_sort_none_means_no_ordering():
    assert_that(users).extracting("user", sort=None).is_equal_to(["Fred", "Bob", "Johnny"])


def test_extracting_sort_ignore_bad_key_types():
    assert_that(users).extracting("user", sort=["active", "age", 123]).is_equal_to(["Bob", "Johnny", "Fred"])


def test_extracting_sort_custom_func():
    def _f(x):
        if x["user"] == "Johnny":
            return 0
        elif x["age"] == 40:
            return 1
        return 10

    assert_that(users).extracting("user", sort=_f).is_equal_to(["Johnny", "Bob", "Fred"])


def test_extracting_sort_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort="foo")
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_list_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort=["foo"])
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_multi_item_dict_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(users).extracting("user", sort=["active", "age", "foo"])
    assert_that(str(exc_info.value)).ends_with("'] did not contain key <foo>")


def test_extracting_sort_lambda_failure():
    with pytest.raises(KeyError) as exc_info:
        assert_that(users).extracting("user", sort=lambda x: x["foo"] > 0)
    assert_that(str(exc_info.value)).is_equal_to("'foo'")


def test_extracting_sort_custom_func_failure():
    def _f(x):
        raise RuntimeError("foobar!")

    with pytest.raises(RuntimeError) as exc_info:
        assert_that(users).extracting("user", sort=_f)
    assert_that(str(exc_info.value)).is_equal_to("foobar!")


def test_extracting_sort_bad_values():
    bad = [{"user": "Fred", "age": 36}, {"user": "Bob", "age": "bad"}, {"user": "Johnny", "age": 13}]
    with pytest.raises(TypeError) as exc_info:
        assert_that(bad).extracting("user", sort="age")
    if sys.version_info[1] <= 5:
        assert_that(str(exc_info.value)).contains("unorderable types")
    else:
        assert_that(str(exc_info.value)).contains("not supported between instances of 'str' and 'int'")


def test_extracting_iterable_of_lists():
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert_that(matrix).extracting(0).is_equal_to([1, 4, 7])
    assert_that(matrix).extracting(0, 1).is_equal_to([(1, 2), (4, 5), (7, 8)])
    assert_that(matrix).extracting(-1).is_equal_to([3, 6, 9])
    assert_that(matrix).extracting(-1, -2).extracting(0).is_equal_to([3, 6, 9])


class _DuckModel:
    """Duck-types a pydantic v2 model for the dependency-free path: iterable over (field, value)
    pairs and NOT subscriptable, with fields exposed as attributes and a model_dump() method.

    This is the exact shape that regressed extracting(): the object is iterable, so without the
    model-dump guard it fell into the index branch and item[name] raised (no [] accessor).  It must
    stay iterable and non-subscriptable to keep exercising that guard.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self):
        return dict(self.__dict__)

    def __iter__(self):
        return iter(self.__dict__.items())


_duck_users = [_DuckModel(user="Fred", age=36), _DuckModel(user="Bob", age=40)]


def test_extracting_model_dump_object_single_field():
    assert_that(_duck_users).extracting("user").contains("Fred", "Bob")


def test_extracting_model_dump_object_multiple_fields():
    assert_that(_duck_users).extracting("user", "age").contains(("Fred", 36), ("Bob", 40))


def test_extracting_model_dump_object_missing_field_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(_duck_users).extracting("foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "item does not have property or zero-arg method <foo> (at index 0, item is <_DuckModel>)"
    )


def test_extracting_real_pydantic_model():
    needs("pydantic")
    from pydantic import BaseModel

    class User(BaseModel):
        user: str
        age: int

    models = [User(user="Fred", age=36), User(user="Bob", age=40)]
    assert_that(models).extracting("user").contains("Fred", "Bob")
    assert_that(models).extracting("user", "age").contains(("Fred", 36), ("Bob", 40))


def test_extracting_iterable_multi_extracting():
    matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    assert_that(matrix).extracting(-1, 2).is_equal_to([(3, 3), (6, 6), (9, 9)])
    assert_that(matrix).extracting(-1, 1).extracting(1, 0).is_equal_to([(2, 3), (5, 6), (8, 9)])


def test_extracting_iterable_of_tuples():
    tuples = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
    assert_that(tuples).extracting(0).is_equal_to([1, 4, 7])
    assert_that(tuples).extracting(0, 1).is_equal_to([(1, 2), (4, 5), (7, 8)])
    assert_that(tuples).extracting(-1).is_equal_to([3, 6, 9])


def test_extracting_iterable_of_strings():
    strings = ["foo", "bar", "baz"]
    assert_that(strings).extracting(0).is_equal_to(["f", "b", "b"])
    assert_that(strings).extracting(0, 2).is_equal_to([("f", "o"), ("b", "r"), ("b", "z")])


def test_extracting_iterable_failure_set():
    with pytest.raises(TypeError) as exc_info:
        assert_that([{1}]).extracting(0).contains(1, 4, 7)
    assert_that(str(exc_info.value)).is_equal_to("item must be a value with a [] accessor, but was <{1}> (set)")


def test_extracting_iterable_failure_out_of_range():
    with pytest.raises(IndexError) as exc_info:
        assert_that([[1], [2], [3]]).extracting(4).is_equal_to(0)
    assert_that(str(exc_info.value)).is_equal_to("list index out of range")


def test_extracting_iterable_failure_index_is_not_int():
    with pytest.raises(TypeError) as exc_info:
        assert_that([[1], [2], [3]]).extracting("1").is_equal_to(0)
    assert_that(str(exc_info.value)).contains("list indices must be integers")


def test_extracting_namedtuple_by_field_name():
    point = namedtuple("Point", ["x", "y"])
    assert_that([point(1, 2), point(3, 4)]).extracting("x").is_equal_to([1, 3])


def test_extracting_single_name_returns_bare_values():
    assert_that([{"a": 1}, {"a": 2}]).extracting("a").is_equal_to([1, 2])


def test_extracting_multiple_names_returns_tuples():
    assert_that([{"a": 1, "b": 2}]).extracting("a", "b").is_equal_to([(1, 2)])


def test_extracting_namedtuple_property_and_zero_arg_method():
    base = namedtuple("Base", ["x", "y"])

    class Point(base):
        @property
        def total(self):
            return self.x + self.y

        def label(self):
            return f"pt{self.x}"

    points = [Point(1, 2), Point(3, 4)]
    assert_that(points).extracting("total").is_equal_to([3, 7])
    assert_that(points).extracting("label").is_equal_to(["pt1", "pt3"])
    assert_that(points).extracting("x").is_equal_to([1, 3])
    with pytest.raises(ValueError, match="did not contain attribute"):
        assert_that(points).extracting("missing").is_equal_to("x")


def test_extracting_zero_arg_method_body_typeerror_not_masked():
    class Obj:
        prices = None

        def total(self):
            return sum(self.prices)

    with pytest.raises(TypeError, match="not iterable"):
        assert_that([Obj()]).extracting("total").is_equal_to([0])


def test_extracting_method_without_introspectable_signature():
    # a zero-arg builtin (int() -> 0) whose inspect.signature raises ValueError must still be called
    class Obj:
        action = staticmethod(int)

    assert_that([Obj()]).extracting("action").is_equal_to([0])


class TestExtractingRefusesAMisspeltOption:
    """`extracting` reads only `filter` and `sort`; anything else was accepted and dropped, so a
    misspelt `sort` produced an unsorted result the caller believed was sorted."""

    _ROWS: typing.ClassVar = [{"title": "b"}, {"title": "a"}]

    def test_the_correct_spelling_still_sorts(self):
        assert_that(assert_that(self._ROWS).extracting("title", sort="title").val).is_equal_to(["a", "b"])

    @pytest.mark.parametrize(("typo", "suggestion"), [("sortt", "sort"), ("filtr", "filter"), ("sorted", "sort")])
    def test_a_near_miss_names_the_option_it_meant(self, typo, suggestion):
        with pytest.raises(TypeError) as exc_info:
            assert_that(self._ROWS).extracting("title", **{typo: "title"})
        assert_that(str(exc_info.value)).contains(typo).contains(f"did you mean {suggestion!r}?")

    def test_both_documented_options_are_accepted(self):
        extracted = assert_that(self._ROWS).extracting("title", filter=lambda row: True, sort="title").val
        assert_that(extracted).is_equal_to(["a", "b"])
