import datetime
import pathlib

from assertpy import assert_that
from assertpy.assertpy import AssertionBuilder


class TestOverloadsRuntimeBehavior:
    def test_str_returns_builder(self):
        assert_that(assert_that("hello")).is_instance_of(AssertionBuilder)

    def test_int_returns_builder(self):
        assert_that(assert_that(42)).is_instance_of(AssertionBuilder)

    def test_float_returns_builder(self):
        assert_that(assert_that(3.14)).is_instance_of(AssertionBuilder)

    def test_dict_returns_builder(self):
        assert_that(assert_that({"a": 1})).is_instance_of(AssertionBuilder)

    def test_list_returns_builder(self):
        assert_that(assert_that([1, 2, 3])).is_instance_of(AssertionBuilder)

    def test_tuple_returns_builder(self):
        assert_that(assert_that((1, 2))).is_instance_of(AssertionBuilder)

    def test_set_returns_builder(self):
        assert_that(assert_that({1, 2})).is_instance_of(AssertionBuilder)

    def test_date_returns_builder(self):
        assert_that(assert_that(datetime.date.today())).is_instance_of(AssertionBuilder)

    def test_datetime_returns_builder(self):
        assert_that(assert_that(datetime.datetime.now())).is_instance_of(AssertionBuilder)

    def test_path_returns_builder(self):
        assert_that(assert_that(pathlib.Path("."))).is_instance_of(AssertionBuilder)

    def test_callable_returns_builder(self):
        assert_that(assert_that(lambda: 42)).is_instance_of(AssertionBuilder)

    def test_none_returns_builder(self):
        assert_that(assert_that(None)).is_instance_of(AssertionBuilder)

    def test_bool_returns_builder(self):
        assert_that(assert_that(True)).is_instance_of(AssertionBuilder)

    def test_with_description(self):
        result = assert_that(42, "my description")
        assert_that(result).is_instance_of(AssertionBuilder)
        assert_that(result.description).is_equal_to("my description")


class TestTypingModuleImport:
    def test_typing_module_importable(self):
        import assertpy._engine._typing  # inline: tests that module is importable

        assert_that(assertpy._engine._typing).is_not_none()
