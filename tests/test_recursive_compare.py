import dataclasses
import threading
import types
from collections import namedtuple

import pytest

from assertpy import assert_that
from assertpy.helpers import HelpersMixin


@dataclasses.dataclass
class User:
    id: int
    name: str
    email: str


@dataclasses.dataclass
class Address:
    city: str
    zip_code: str


@dataclasses.dataclass
class UserWithAddress:
    id: int
    name: str
    address: Address


Point = namedtuple("Point", ["x", "y", "label"])


class PlainUser:
    def __init__(self, id, name, role):
        self.id = id
        self.name = name
        self.role = role


class TestDataclassIgnore:
    def test_ignore_single_field(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=99, name="Alice", email="a@x.com")
        assert_that(actual).is_equal_to(expected, ignore="id")

    def test_ignore_multiple_fields(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=99, name="Alice", email="different@x.com")
        assert_that(actual).is_equal_to(expected, ignore=["id", "email"])

    def test_ignore_set_of_fields(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=99, name="Alice", email="different@x.com")
        assert_that(actual).is_equal_to(expected, ignore={"id", "email"})

    def test_ignore_nested_field(self):
        actual = UserWithAddress(id=1, name="Alice", address=Address(city="NYC", zip_code="10001"))
        expected = UserWithAddress(id=1, name="Alice", address=Address(city="NYC", zip_code="99999"))
        assert_that(actual).is_equal_to(expected, ignore=[("address", "zip_code")])

    def test_ignore_failure(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=1, name="Bob", email="a@x.com")
        with pytest.raises(AssertionError, match="Alice"):
            assert_that(actual).is_equal_to(expected, ignore="id")

    def test_equal_objects_with_ignore_passes(self):
        user = User(id=1, name="Alice", email="a@x.com")
        assert_that(user).is_equal_to(user, ignore="id")

    def test_ignore_un_deepcopyable_field(self):
        # asdict deep-copied every leaf, so ignoring an un-copyable field (a lock) still crashed
        @dataclasses.dataclass
        class Resource:
            name: str
            lock: object

        actual = Resource("db", threading.Lock())
        expected = Resource("db", threading.Lock())
        assert_that(actual).is_equal_to(expected, ignore="lock")

    def test_shared_identity_field_not_deepcopied(self):
        # a shared reference must stay identity-equal; asdict deep-copied it and reported a false difference
        class Handle:
            def __init__(self, token):
                self.token = token

        @dataclasses.dataclass
        class Config:
            version: int
            handle: object

        shared = Handle("s")
        assert_that(Config(1, shared)).is_equal_to(Config(1, shared))

    def test_ignore_with_nested_namedtuple_dict_and_list_fields(self):
        # exercises the shallow-asdict recursion over namedtuple / dict / list field values
        point = namedtuple("Point", ["x", "y"])

        @dataclasses.dataclass
        class Shape:
            id: int
            corner: object
            meta: dict
            tags: list

        actual = Shape(1, point(1, 2), {"k": "v"}, ["a", "b"])
        expected = Shape(99, point(1, 2), {"k": "v"}, ["a", "b"])
        assert_that(actual).is_equal_to(expected, ignore="id")


class TestDataclassInclude:
    def test_include_single_field(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=99, name="Alice", email="different@x.com")
        assert_that(actual).is_equal_to(expected, include="name")

    def test_include_multiple_fields(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=99, name="Alice", email="a@x.com")
        assert_that(actual).is_equal_to(expected, include=["name", "email"])


class TestNamedtuple:
    def test_ignore_field(self):
        actual = Point(x=1, y=2, label="origin")
        expected = Point(x=1, y=2, label="different")
        assert_that(actual).is_equal_to(expected, ignore="label")

    def test_include_field(self):
        actual = Point(x=1, y=99, label="a")
        expected = Point(x=1, y=0, label="b")
        assert_that(actual).is_equal_to(expected, include="x")


class TestPlainObject:
    def test_ignore_field(self):
        actual = PlainUser(id=1, name="Alice", role="admin")
        expected = PlainUser(id=99, name="Alice", role="admin")
        assert_that(actual).is_equal_to(expected, ignore="id")

    def test_include_field(self):
        actual = PlainUser(id=1, name="Alice", role="admin")
        expected = PlainUser(id=99, name="Alice", role="viewer")
        assert_that(actual).is_equal_to(expected, include="name")


class TestListOfObjects:
    def test_list_of_dataclasses_ignore(self):
        actual = [User(id=1, name="Alice", email="a@x.com"), User(id=2, name="Bob", email="b@x.com")]
        expected = [User(id=99, name="Alice", email="a@x.com"), User(id=99, name="Bob", email="b@x.com")]
        assert_that(actual).is_equal_to(expected, ignore="id")

    def test_list_length_mismatch(self):
        actual = [User(id=1, name="Alice", email="a@x.com")]
        expected = [User(id=1, name="Alice", email="a@x.com"), User(id=2, name="Bob", email="b@x.com")]
        with pytest.raises(AssertionError) as failure:
            assert_that(actual).is_equal_to(expected, ignore="id")
        rows = [(entry.path, entry.expected, entry.absent) for entry in failure.value.diff.entries]
        assert_that(rows).is_equal_to([("[1]", {"name": "Bob", "email": "b@x.com"}, "actual")])

    def test_list_failure_at_element(self):
        actual = [User(id=1, name="Alice", email="a@x.com"), User(id=2, name="WRONG", email="b@x.com")]
        expected = [User(id=99, name="Alice", email="a@x.com"), User(id=99, name="Bob", email="b@x.com")]
        with pytest.raises(AssertionError, match="WRONG"):
            assert_that(actual).is_equal_to(expected, ignore="id")

    def test_empty_lists_with_ignore(self):
        assert_that([]).is_equal_to([], ignore="id")

    def test_tuple_of_objects_ignore(self):
        actual = (User(id=1, name="Alice", email="a@x.com"),)
        expected = (User(id=99, name="Alice", email="a@x.com"),)
        assert_that(actual).is_equal_to(expected, ignore="id")


class TestErrors:
    def test_unconvertible_int_raises_type_error(self):
        with pytest.raises(TypeError, match="introspectable fields"):
            assert_that(42).is_equal_to(43, ignore="x")

    def test_unconvertible_str_raises_type_error(self):
        with pytest.raises(TypeError, match="introspectable fields"):
            assert_that("foo").is_equal_to("bar", ignore="x")

    def test_unconvertible_none_raises_type_error(self):
        with pytest.raises(TypeError, match="introspectable fields"):
            assert_that(None).is_equal_to(None, ignore="x")

    def test_error_message_contains_field_values(self):
        actual = User(id=1, name="Alice", email="a@x.com")
        expected = User(id=1, name="Bob", email="a@x.com")
        with pytest.raises(AssertionError, match=r"Alice.*Bob|Bob.*Alice"):
            assert_that(actual).is_equal_to(expected, ignore="id")


class TestToComparableDict:
    def test_dataclass(self):
        user = User(id=1, name="Alice", email="a@x.com")
        result = HelpersMixin._to_comparable_dict(user)
        assert_that(result).is_equal_to({"id": 1, "name": "Alice", "email": "a@x.com"})

    def test_namedtuple(self):
        point = Point(x=1, y=2, label="a")
        result = HelpersMixin._to_comparable_dict(point)
        assert_that(result).is_equal_to({"x": 1, "y": 2, "label": "a"})

    def test_plain_object(self):
        obj = PlainUser(id=1, name="Alice", role="admin")
        result = HelpersMixin._to_comparable_dict(obj)
        assert_that(result).is_equal_to({"id": 1, "name": "Alice", "role": "admin"})

    def test_returns_none_for_int(self):
        assert_that(HelpersMixin._to_comparable_dict(42)).is_none()

    def test_returns_none_for_str(self):
        assert_that(HelpersMixin._to_comparable_dict("foo")).is_none()

    def test_returns_none_for_none(self):
        assert_that(HelpersMixin._to_comparable_dict(None)).is_none()

    def test_returns_none_for_class_itself(self):
        assert_that(HelpersMixin._to_comparable_dict(User)).is_none()

    def test_nested_dataclass_deep_conversion(self):
        obj = UserWithAddress(id=1, name="A", address=Address(city="NYC", zip_code="10001"))
        result = HelpersMixin._to_comparable_dict(obj)
        assert_that(result).is_equal_to({"id": 1, "name": "A", "address": {"city": "NYC", "zip_code": "10001"}})

    def test_model_dump_duck_type(self):
        class FakeModel:
            def model_dump(self):
                return {"x": 1, "y": 2}

        result = HelpersMixin._to_comparable_dict(FakeModel())
        assert_that(result).is_equal_to({"x": 1, "y": 2})

    def test_a_sequence_subclass_is_built_from_what_its_constructor_always_got(self):
        received = []

        class Recorded(list):
            def __init__(self, items=()):
                received.append(type(items))
                super().__init__(items)

        @dataclasses.dataclass
        class Holder:
            items: object

        result = HelpersMixin._to_comparable_dict(Holder(Recorded([1, 2])))
        assert_that(result["items"]).is_instance_of(Recorded).is_equal_to([1, 2])
        assert_that(received[-1]).is_equal_to(types.GeneratorType)


class TestListUnconvertibleElements:
    def test_list_of_ints_with_ignore_falls_through_to_equality(self):
        with pytest.raises(AssertionError) as failure:
            assert_that([1, 2]).is_equal_to([1, 3], ignore="x")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.value.diff.entries]
        assert_that(rows).is_equal_to([("[1]", 2, 3)])

    def test_list_mixed_equal_unconvertible_passes(self):
        assert_that([1, User(id=1, name="A", email="a@x.com")]).is_equal_to(
            [1, User(id=99, name="A", email="a@x.com")], ignore="id"
        )

    def test_list_mixed_unequal_unconvertible_fails(self):
        with pytest.raises(AssertionError) as failure:
            assert_that([1, User(id=1, name="A", email="a@x.com")]).is_equal_to(
                [2, User(id=99, name="A", email="a@x.com")], ignore="id"
            )
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.value.diff.entries]
        assert_that(rows).is_equal_to([("[0]", 1, 2)])
