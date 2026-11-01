from __future__ import annotations

import functools

import pytest

from assertpy import assert_that, clear_custom_matchers, match, register_matcher, unregister_matcher


class TestRegisterMatcher:
    def teardown_method(self):
        clear_custom_matchers()

    def test_simple_matcher(self):
        @register_matcher("is_short")
        def is_short():
            return match.has_length(3)

        assert_that("foo").satisfies(match.is_short())

    def test_parametrised_matcher(self):
        @register_matcher("has_status")
        def has_status(expected: str):
            return match.equal_to(expected)

        assert_that("active").satisfies(match.has_status("active"))

    def test_parametrised_matcher_failure(self):
        @register_matcher("has_status")
        def has_status(expected: str):
            return match.equal_to(expected)

        with pytest.raises(AssertionError):
            assert_that("active").satisfies(match.has_status("inactive"))

    def test_composition_with_builtin(self):
        @register_matcher("is_valid_email")
        def is_valid_email():
            return match.matches_regex(r"^[\w.-]+@[\w.-]+\.\w+$")

        combined = match.is_valid_email() & match.contains_string("@company.com")
        assert_that("alice@company.com").satisfies(combined)

    def test_composition_failure(self):
        @register_matcher("is_valid_email")
        def is_valid_email():
            return match.matches_regex(r"^[\w.-]+@[\w.-]+\.\w+$")

        combined = match.is_valid_email() & match.contains_string("@company.com")
        with pytest.raises(AssertionError):
            assert_that("alice@other.com").satisfies(combined)

    def test_with_each(self):
        @register_matcher("is_short")
        def is_short():
            return match.has_length(3)

        assert_that(["foo", "bar", "baz"]).each(match.is_short())

    def test_with_matches_structure(self):
        @register_matcher("is_valid_name")
        def is_valid_name():
            return match.is_non_empty_string()

        data = {"name": "Alice", "age": 30}
        assert_that(data).matches_structure(
            {
                "name": match.is_valid_name(),
                "age": match.between(0, 200),
            }
        )

    def test_invert_custom_matcher(self):
        @register_matcher("is_short")
        def is_short():
            return match.has_length(3)

        inverted = ~match.is_short()
        assert_that("hello").satisfies(inverted)

    def test_or_custom_matchers(self):
        @register_matcher("is_three")
        def is_three():
            return match.has_length(3)

        @register_matcher("is_five")
        def is_five():
            return match.has_length(5)

        combined = match.is_three() | match.is_five()
        assert_that("hello").satisfies(combined)
        assert_that("foo").satisfies(combined)

    def test_a_name_already_taken_is_refused(self):
        # two libraries registering `has_status` used to end with whichever imported last, silently
        @register_matcher("custom")
        def custom_v1():
            return match.equal_to(1)

        with pytest.raises(ValueError, match="already registered"):

            @register_matcher("custom")
            def custom_v2():
                return match.equal_to(2)

        assert_that(1).satisfies(match.custom())

    def test_a_factory_rebuilt_by_a_fixture_is_not_a_clash(self):
        def build():
            def steady():
                return match.equal_to(1)

            return steady

        first, second = build(), build()
        assert first is not second
        register_matcher("custom")(first)
        register_matcher("custom")(second)
        assert_that(1).satisfies(match.custom())

    def test_one_decorator_over_two_factories_is_a_clash(self):
        def cached(factory):
            @functools.wraps(factory)
            def wrapper():
                return factory()

            return wrapper

        def one():
            return match.equal_to(1)

        def two():
            return match.equal_to(2)

        register_matcher("custom")(cached(one))
        with pytest.raises(ValueError, match="already registered"):
            register_matcher("custom")(cached(two))
        assert_that(1).satisfies(match.custom())

    def test_one_decorator_over_a_factory_and_over_a_value_is_a_clash(self):
        def cached(held):
            def wrapper():
                return held() if callable(held) else match.equal_to(held)

            return wrapper

        def one():
            return match.equal_to(1)

        register_matcher("custom")(cached(one))
        with pytest.raises(ValueError, match="already registered"):
            register_matcher("custom")(cached(2))
        assert_that(1).satisfies(match.custom())

    def test_replacing_deliberately_is_allowed(self):
        @register_matcher("custom")
        def custom_v1():
            return match.equal_to(1)

        @register_matcher("custom", override=True)
        def custom_v2():
            return match.equal_to(2)

        assert_that(2).satisfies(match.custom())

    def test_a_built_in_name_is_refused_outright(self):
        # `match.equal_to` is found by attribute lookup, which never consults this registry, so override never runs
        with pytest.raises(ValueError, match="built-in matcher"):
            register_matcher("equal_to")(lambda: match.equal_to(1))
        with pytest.raises(ValueError, match="built-in matcher"):
            register_matcher("equal_to", override=True)(lambda: match.equal_to(1))

    def test_returns_decorated_function(self):
        @register_matcher("my_matcher")
        def my_matcher():
            return match.is_positive()

        assert_that(callable(my_matcher)).is_true()
        result = my_matcher()
        assert_that(result.matches(5)).is_true()


class TestRegisterMatcherErrors:
    def teardown_method(self):
        clear_custom_matchers()

    def test_name_not_string(self):
        with pytest.raises(TypeError, match="given name arg must be a string"):
            register_matcher(123)

    def test_name_not_identifier(self):
        with pytest.raises(ValueError, match="must be a valid Python identifier"):
            register_matcher("not-valid")

    def test_name_not_identifier_spaces(self):
        with pytest.raises(ValueError, match="must be a valid Python identifier"):
            register_matcher("has spaces")

    def test_func_not_callable(self):
        with pytest.raises(TypeError, match="given func arg must be callable"):
            register_matcher("test")(42)

    def test_unregistered_name_attribute_error(self):
        with pytest.raises(AttributeError, match="match has no matcher"):
            match.nonexistent_matcher()


class TestUnregisterMatcher:
    def teardown_method(self):
        clear_custom_matchers()

    def test_unregister(self):
        @register_matcher("temp")
        def temp():
            return match.is_positive()

        assert_that(5).satisfies(match.temp())
        unregister_matcher("temp")
        with pytest.raises(AttributeError):
            match.temp()

    def test_unregister_unknown_name(self):
        with pytest.raises(KeyError, match="no custom matcher registered"):
            unregister_matcher("nonexistent")

    def test_clear_custom_matchers(self):
        @register_matcher("a")
        def a():
            return match.is_positive()

        @register_matcher("b")
        def b():
            return match.is_negative()

        assert_that(1).satisfies(match.a())
        clear_custom_matchers()
        with pytest.raises(AttributeError):
            match.a()
        with pytest.raises(AttributeError):
            match.b()


class TestBaseMatcherIsReachableFromThePackage:
    """It is the documented way to write a matcher whose rule cannot be composed from the built-ins,
    and until it was exported the only way to reach it was an import from a private module."""

    def test_it_is_importable_from_the_top_level(self):
        from assertpy import BaseMatcher

        assert_that(BaseMatcher).is_not_none()

    def test_a_subclass_works_everywhere_a_matcher_is_accepted(self):
        from assertpy import BaseMatcher

        class IsEven(BaseMatcher):
            def matches(self, value):
                return isinstance(value, int) and value % 2 == 0

            def describe(self):
                return "an even number"

        assert_that(4).satisfies(IsEven())
        assert_that([2, 4]).each(IsEven())
        assert_that({"n": 2}).matches_structure({"n": IsEven()})
        assert_that([1, 2]).contains(IsEven())

    def test_a_subclass_composes_with_the_operators(self):
        from assertpy import BaseMatcher, match

        class IsEven(BaseMatcher):
            def matches(self, value):
                return isinstance(value, int) and value % 2 == 0

            def describe(self):
                return "an even number"

        assert_that(4).satisfies(IsEven() & match.greater_than(2))
        assert_that(3).satisfies(IsEven() | match.greater_than(2))
        assert_that(3).satisfies(~IsEven())

    def test_the_default_mismatch_description_is_enough_to_get_started(self):
        from assertpy import BaseMatcher

        class IsEven(BaseMatcher):
            def matches(self, value):
                return isinstance(value, int) and value % 2 == 0

            def describe(self):
                return "an even number"

        with pytest.raises(AssertionError, match="was <3>"):
            assert_that(3).satisfies(IsEven())
