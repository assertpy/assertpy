import pytest

from assertpy import assert_that


class TestIsCallable:
    def test_callable_lambda(self):
        assert_that(lambda: None).is_callable()

    def test_callable_function(self):
        assert_that(print).is_callable()

    def test_callable_class(self):
        assert_that(int).is_callable()

    def test_callable_method(self):
        assert_that("foo".upper).is_callable()

    def test_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(42).is_callable()
        assert_that(str(exc_info.value)).is_equal_to("Expected <42> to be callable, but was not.")

    def test_callable_string_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that("foo").is_callable()
        assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be callable, but was not.")


class TestIsNotCallable:
    def test_not_callable_int(self):
        assert_that(42).is_not_callable()

    def test_not_callable_string(self):
        assert_that("foo").is_not_callable()

    def test_not_callable_none(self):
        assert_that(None).is_not_callable()

    def test_not_callable_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(print).is_not_callable()
        assert_that(str(exc_info.value)).contains("to not be callable, but was.")

    def test_not_callable_lambda_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(lambda: None).is_not_callable()
        assert_that(str(exc_info.value)).contains("to not be callable, but was.")
