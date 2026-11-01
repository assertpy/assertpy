from unittest.mock import MagicMock, patch

import pytest

from assertpy import assert_that
from assertpy.behave_matchers import (
    ASSERTPY_TYPES,
    _bool_like,
    _non_empty_string,
    _non_negative_int,
    _positive_float,
    _positive_int,
    register_assertpy_types,
)


class TestPositiveInt:
    def test_valid(self):
        assert_that(_positive_int("5")).is_equal_to(5)
        assert_that(_positive_int("1")).is_equal_to(1)
        assert_that(_positive_int("999")).is_equal_to(999)

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            _positive_int("0")

    def test_has_pattern(self):
        assert_that(_positive_int.pattern).is_equal_to(r"\d+")


class TestNonNegativeInt:
    def test_valid(self):
        assert_that(_non_negative_int("0")).is_equal_to(0)
        assert_that(_non_negative_int("42")).is_equal_to(42)

    def test_has_pattern(self):
        assert_that(_non_negative_int.pattern).is_equal_to(r"\d+")


class TestPositiveFloat:
    def test_valid(self):
        assert_that(_positive_float("3.14")).is_close_to(3.14, 0.001)
        assert_that(_positive_float("1")).is_equal_to(1.0)
        assert_that(_positive_float("0.001")).is_close_to(0.001, 0.0001)

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="positive float"):
            _positive_float("0")

    def test_has_pattern(self):
        assert_that(_positive_float.pattern).is_equal_to(r"\d+\.?\d*")


class TestNonEmptyString:
    def test_valid(self):
        assert_that(_non_empty_string("hello")).is_equal_to("hello")
        assert_that(_non_empty_string("  padded  ")).is_equal_to("padded")

    def test_blank_rejected(self):
        with pytest.raises(ValueError, match="non-empty string"):
            _non_empty_string("   ")

    def test_has_pattern(self):
        assert_that(_non_empty_string.pattern).is_equal_to(r".+?")


class TestBoolLike:
    @pytest.mark.parametrize("text", ["true", "True", "TRUE", "yes", "Yes", "1", "on", "ON"])
    def test_truthy(self, text):
        assert_that(_bool_like(text)).is_true()

    @pytest.mark.parametrize("text", ["false", "False", "FALSE", "no", "No", "0", "off", "OFF"])
    def test_falsy(self, text):
        assert_that(_bool_like(text)).is_false()

    def test_invalid_rejected(self):
        with pytest.raises(ValueError, match="boolean-like"):
            _bool_like("maybe")

    def test_has_pattern(self):
        assert_that(_bool_like.pattern).is_equal_to(r"\w+")


class TestAssertpyTypesDict:
    def test_contains_all_types(self):
        assert_that(set(ASSERTPY_TYPES)).is_equal_to(
            {"PositiveInt", "NonNegativeInt", "PositiveFloat", "NonEmptyString", "BoolLike"}
        )

    def test_values_are_callables(self):
        for name, func in ASSERTPY_TYPES.items():
            assert_that(callable(func)).described_as(f"{name} is not callable").is_true()

    def test_all_have_pattern(self):
        for name, func in ASSERTPY_TYPES.items():
            assert_that(hasattr(func, "pattern")).described_as(f"{name} missing .pattern").is_true()


class TestRegisterAssertpyTypes:
    def test_calls_register_type(self):
        mock_register = MagicMock()
        with patch.dict("sys.modules", {"behave": MagicMock(register_type=mock_register)}):
            register_assertpy_types()
        mock_register.assert_called_once_with(**ASSERTPY_TYPES)

    def test_raises_without_behave(self):
        with (
            patch.dict("sys.modules", {"behave": None}),
            pytest.raises(ImportError, match="behave is required"),
        ):
            register_assertpy_types()
