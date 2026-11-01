import functools
import numbers
from unittest import mock

import pytest

import assertpy.assertpy
from assertpy import add_extension, assert_that, remove_extension


def is_even_integer(self):
    if not isinstance(self.val, numbers.Integral):
        raise TypeError("val must be an integer")
    if self.val % 2 != 0:
        return self.error(f"Expected <{self.val}> to be an even integer, but was not.")
    return self


def is_multiple_of(self, other):
    if not isinstance(self.val, numbers.Integral) or self.val <= 0:
        raise TypeError("val must be a positive integer")

    if not isinstance(other, numbers.Integral) or other <= 0:
        raise TypeError("given arg must be a positive integer")

    _, rem = divmod(self.val, other)
    if rem > 0:
        return self.error(f"Expected <{self.val}> to be multiple of <{other}>, but was not.")

    return self


def is_factor_of(self, other):
    if not isinstance(self.val, numbers.Integral) or self.val <= 0:
        raise TypeError("val must be a positive integer")

    if not isinstance(other, numbers.Integral) or other <= 0:
        raise TypeError("given arg must be a positive integer")

    _, rem = divmod(other, self.val)
    if rem > 0:
        return self.error(f"Expected <{self.val}> to be factor of <{other}>, but was not.")

    return self


_SHARED = (is_even_integer, is_multiple_of, is_factor_of)


@pytest.fixture(autouse=True)
def _shared_extensions():
    """Register the three shared extensions per test, and take them back afterwards.

    The registry is global, so registering at import time made the file order-dependent: the test that
    proves a removed extension is gone removes all three, and every test after it in a different order
    would lose its assertion. Registering here scopes that to one test.

    What is restored is the registry as it was, not merely "these three names gone". Removing them
    unconditionally would destroy an extension of the same name that existed before, which trades one
    order dependency for another. A snapshot is taken instead, and `finally` puts it back whether the
    test removed things, added things, or raised half-way through.

    Both halves of the registry, and the second half is the one this was missing. `add_extension()`
    writes a plain function onto the builder subclass rather than into `_extensions`, so restoring the
    mapping alone left four names on the class after this file: another test reading the builder's own
    surface then saw them as members it was missing, and passed or failed on what ran before it.
    """
    before = dict(assertpy.assertpy._extensions)
    on_the_builder = dict(vars(assertpy.assertpy._ExtendedBuilder))
    try:
        for extension in _SHARED:
            add_extension(extension, override=True)
        yield
    finally:
        assertpy.assertpy._extensions.clear()
        assertpy.assertpy._extensions.update(before)
        for name in set(vars(assertpy.assertpy._ExtendedBuilder)) - set(on_the_builder):
            delattr(assertpy.assertpy._ExtendedBuilder, name)
        for name, member in on_the_builder.items():
            if getattr(assertpy.assertpy._ExtendedBuilder, name, None) is not member:
                setattr(assertpy.assertpy._ExtendedBuilder, name, member)


def test_is_even_extension():
    assert_that(124).is_even_integer()
    assert_that(124).is_type_of(int).is_even_integer().is_greater_than(123).is_less_than(125).is_equal_to(124)


def test_is_even_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_even_integer()
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be an even integer, but was not.")


def test_is_even_extension_failure_not_callable():
    with pytest.raises(TypeError) as exc_info:
        add_extension("foo")
    assert_that(str(exc_info.value)).is_equal_to("given func arg must be callable, but was <'foo'> (str)")


def test_is_even_extension_failure_not_integer():
    with pytest.raises(TypeError) as exc_info:
        assert_that(124.0).is_even_integer()
    assert_that(str(exc_info.value)).is_equal_to("val must be an integer")


def test_is_multiple_of_extension():
    assert_that(24).is_multiple_of(1)
    assert_that(24).is_multiple_of(2)
    assert_that(24).is_multiple_of(3)
    assert_that(24).is_multiple_of(4)
    assert_that(24).is_multiple_of(6)
    assert_that(24).is_multiple_of(8)
    assert_that(24).is_multiple_of(12)
    assert_that(24).is_multiple_of(24)
    assert_that(124).is_type_of(int).is_even_integer().is_multiple_of(31).is_equal_to(124)


def test_is_multiple_of_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(24).is_multiple_of(5)
    assert_that(str(exc_info.value)).is_equal_to("Expected <24> to be multiple of <5>, but was not.")


def test_is_multiple_of_extension_failure_bad_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24.0).is_multiple_of(5)
    assert_that(str(exc_info.value)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_negative_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(-24).is_multiple_of(6)
    assert_that(str(exc_info.value)).is_equal_to("val must be a positive integer")


def test_is_multiple_of_extension_failure_bad_arg():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24).is_multiple_of("foo")
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive integer")


def test_is_multiple_of_extension_failure_negative_arg():
    with pytest.raises(TypeError) as exc_info:
        assert_that(24).is_multiple_of(-6)
    assert_that(str(exc_info.value)).is_equal_to("given arg must be a positive integer")


def test_is_factor_of_extension():
    assert_that(1).is_factor_of(24)
    assert_that(2).is_factor_of(24)
    assert_that(3).is_factor_of(24)
    assert_that(4).is_factor_of(24)
    assert_that(6).is_factor_of(24)
    assert_that(8).is_factor_of(24)
    assert_that(12).is_factor_of(24)
    assert_that(24).is_factor_of(24)
    assert_that(31).is_type_of(int).is_factor_of(124).is_equal_to(31)


def test_is_factor_of_extension_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(5).is_factor_of(24)
    assert_that(str(exc_info.value)).is_equal_to("Expected <5> to be factor of <24>, but was not.")


def test_call_missing_extension():
    def is_missing():
        pass

    with pytest.raises(AttributeError) as exc_info:
        remove_extension(is_even_integer)
        remove_extension(is_multiple_of)
        remove_extension(is_factor_of)
        remove_extension(is_missing)
        assert_that(24).is_multiple_of(6)
    assert_that(str(exc_info.value)).is_equal_to("assertpy has no assertion <is_multiple_of()>")


def test_remove_bad_extension():
    with pytest.raises(TypeError) as exc_info:
        remove_extension("foo")
    assert_that(str(exc_info.value)).is_equal_to("given func arg must be callable, but was <'foo'> (str)")


def is_foo(self):
    if self.val != "foo":
        return self.error(f"Expected <{self.val}> to be foo, but was not.")
    return self


def dupe1():
    add_extension(is_foo, override=True)
    assert_that("foo").is_foo()
    with pytest.raises(AssertionError) as exc_info:
        assert_that("FOO").is_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected <FOO> to be foo, but was not.")


def dupe2():
    def is_foo(self):
        if self.val != "FOO":
            return self.error(f"Expected <{self.val}> to be FOO, but was not.")
        return self

    add_extension(is_foo, override=True)
    assert_that("FOO").is_foo()
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be FOO, but was not.")


def test_dupe_extensions():
    dupe1()
    dupe2()
    dupe1()


def test_a_second_implementation_under_one_name_is_refused():
    # two functions claiming one name used to end with whichever was imported last, silently
    def already_there(self):
        return self

    def already_there_again(self):
        return self.error("the other one")

    already_there_again.__name__ = "already_there"

    add_extension(already_there)
    try:
        with pytest.raises(ValueError, match="already been added"):
            add_extension(already_there_again)
        add_extension(already_there_again, override=True)
    finally:
        remove_extension(already_there)


def test_a_function_rebuilt_by_a_fixture_is_not_a_clash():
    # a conftest fixture defining its assertion inline hands over a new function object every run,
    # so identity would call the second module a clash; the code object stays the same across rebuilds
    def build():
        def steady(self):
            return self

        return steady

    first, second = build(), build()
    assert first is not second
    add_extension(first)
    try:
        add_extension(second)
    finally:
        remove_extension(first)


def _logged(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        return func(self, *args, **kwargs)

    return wrapper


def test_one_decorator_over_two_functions_is_a_clash():
    """Everything one decorator wraps shares the wrapper's code, so only what it wraps tells them apart."""

    def decorated(self):
        return self

    def another(self):
        return self.error("the other one")

    another.__name__ = "decorated"
    add_extension(_logged(decorated))
    try:
        with pytest.raises(ValueError, match="already been added"):
            add_extension(_logged(another))
    finally:
        remove_extension(decorated)


def _defaulted(func):
    def wrapper(self, _impl=func):
        return _impl(self)

    wrapper.__name__ = func.__name__
    return wrapper


def _keyword_defaulted(func):
    def wrapper(self, *, _impl=func):
        return _impl(self)

    wrapper.__name__ = func.__name__
    return wrapper


def _via_wrapped(func):
    def wrapper(self):
        return wrapper.__wrapped__(self)

    wrapper.__wrapped__ = func
    wrapper.__name__ = func.__name__
    return wrapper


@pytest.mark.parametrize("decorate", [_defaulted, _keyword_defaulted, _via_wrapped])
def test_a_decorator_keeping_what_it_wraps_elsewhere_still_tells_two_apart(decorate):
    """A wrapper may hold the wrapped function in a default or in `__wrapped__` rather than its closure."""

    def kept(self):
        return self

    def other(self):
        return self.error("the other one")

    other.__name__ = "kept"
    add_extension(decorate(kept))
    try:
        add_extension(decorate(kept))
        with pytest.raises(ValueError, match="already been added"):
            add_extension(decorate(other))
    finally:
        remove_extension(kept)


def test_one_decorator_over_one_function_rebuilt_is_not_a_clash():
    def decorated_again(self):
        return self

    add_extension(_logged(decorated_again))
    try:
        add_extension(_logged(decorated_again))
    finally:
        remove_extension(decorated_again)


def test_a_function_rebuilt_with_fresh_data_is_not_a_clash():
    """A fixture's closure holds new objects on every run, and the latest registration is meant to win."""

    def build(limit):
        def is_within(self):
            return self if self.val in limit else self.error(f"{self.val} is outside {limit}")

        return is_within

    add_extension(build([1]))
    try:
        add_extension(build([2]))
        assert_that(2).is_within()
    finally:
        remove_extension(build([]))


class _NoCode:
    __code__ = None

    def __call__(self):
        return None


@pytest.mark.parametrize("fresh", [mock.Mock, _NoCode], ids=["mock", "no-code"])
def test_a_function_rebuilt_around_a_fresh_callable_is_not_a_clash(fresh):
    """A callable that is not a function is data: a fresh mock, or an object whose `__code__` is not a code object."""

    def build():
        spy = fresh()

        def is_spied(self):
            spy()
            return self

        return is_spied

    add_extension(build())
    try:
        add_extension(build())
    finally:
        remove_extension(build())


def test_a_rebuilt_function_that_holds_itself_is_not_a_clash():
    def build():
        def recursive(self):
            return recursive

        return recursive

    add_extension(build())
    try:
        add_extension(build())
    finally:
        remove_extension(build())


def test_a_rebuilt_function_with_an_unfilled_closure_is_not_a_clash():
    """A name the function closes over but its builder never assigned leaves an empty cell behind."""

    def build(ready=False):
        def pending(self):
            return later(self)

        if ready:
            later = _logged
        return pending

    add_extension(build())
    try:
        add_extension(build())
    finally:
        remove_extension(build())


def test_a_callable_object_falls_back_to_identity():
    # an instance with `__call__` has no code object, so identity is the strictest answer available
    class Callable:
        __name__ = "instance_extension"

        def __call__(self, builder):
            return builder

    first, second = Callable(), Callable()
    add_extension(first)
    try:
        add_extension(first)
        with pytest.raises(ValueError, match="already been added"):
            add_extension(second)
    finally:
        remove_extension(first)


def test_a_callable_without_a_usable_name_is_refused():
    # the registry keys on `__name__`, and a lambda gives "<lambda>", which nobody can call on the builder
    with pytest.raises(ValueError, match="valid Python identifier"):
        add_extension(lambda self: self)


def test_replacing_a_built_in_assertion_has_to_be_deliberate():
    # this went through in silence, and every later call to the core assertion got the extension's message
    def is_type_of(self, other):
        return self.error("shadowed")

    with pytest.raises(ValueError, match="already defined on the assertion builder"):
        add_extension(is_type_of)


class TestNamesAPollingChainAnswersItself:
    """Refused at registration, since after `eventually()` such an extension is unreachable."""

    @pytest.mark.parametrize("name", ["close", "send", "throw", "within", "every", "ignoring", "val", "not_"])
    def test_a_name_the_chain_owns_is_refused(self, name):
        def extension(self):
            return self.error("shadowed")

        extension.__name__ = name
        with pytest.raises(ValueError, match="polling chain spells one of its own"):
            add_extension(extension)

    @pytest.mark.parametrize("name", ["cr_code", "gi_frame", "_custom"])
    def test_a_coroutine_attribute_name_is_refused(self, name):
        def extension(self):
            return self.error("shadowed")

        extension.__name__ = name
        with pytest.raises(ValueError, match="polling chain spells one of its own"):
            add_extension(extension)

    def test_override_does_not_get_past_it(self):
        def close(self):
            return self.error("shadowed")

        with pytest.raises(ValueError, match="polling chain spells one of its own"):
            add_extension(close, override=True)

    def test_a_name_of_its_own_still_registers(self):
        def is_closed(self):
            return self.error("mine")

        add_extension(is_closed)
        try:
            assert_that(assert_that(1)).is_not_none()
        finally:
            remove_extension(is_closed)


class TestExtensionBindingMechanics:
    """Plain functions bind to the extension host class once; exotic callables fall back to
    per-instance grafting; removal never damages the original API."""

    def test_extension_shadowing_a_builtin_method_is_restored_on_removal(self):
        def is_true(self):
            return self.error("shadowed is_true")

        add_extension(is_true, override=True)
        try:
            with pytest.raises(AssertionError, match="shadowed is_true"):
                assert_that(True).is_true()
        finally:
            remove_extension(is_true)
        assert_that(True).is_true()

    def test_callable_object_extension_uses_per_instance_fallback(self):
        class IsBar:
            __name__ = "is_bar"

            def __call__(self, builder):
                if builder.val != "bar":
                    return builder.error(f"Expected <{builder.val}> to be bar, but was not.")
                return builder

        extension = IsBar()
        add_extension(extension)
        try:
            assert_that("bar").is_bar()
            with pytest.raises(AssertionError, match="to be bar"):
                assert_that("baz").is_bar()
        finally:
            remove_extension(extension)
        with pytest.raises(AttributeError):
            assert_that("bar").is_bar()

    def test_extension_becomes_visible_to_builders_created_before_registration(self):
        builder = assert_that("foo")

        def is_visible_late(self):
            return self

        add_extension(is_visible_late)
        try:
            builder.is_visible_late()
        finally:
            remove_extension(is_visible_late)

    def test_removed_extension_disappears_from_live_builders(self):
        def is_transient(self):
            return self

        add_extension(is_transient)
        builder = assert_that("foo")
        builder.is_transient()
        remove_extension(is_transient)
        with pytest.raises(AttributeError):
            builder.is_transient()

    def test_builder_stays_an_assertion_builder_instance(self):
        from assertpy.assertpy import AssertionBuilder

        assert_that(assert_that(1)).is_instance_of(AssertionBuilder)


class TestAnOverrideLeavesOneImplementation:
    """A name is registered in one of two places by shape, and an override can change the shape.

    A plain function is set on the builder subclass, anything else is grafted onto each instance in
    `_builder()`. An instance attribute shadows a class one, so leaving the old entry behind meant the
    replaced implementation kept running while `add_extension()` reported success.
    """

    def test_a_callable_object_is_replaced_by_a_function(self):
        class Refusing:
            __name__ = "is_shape_changed"

            def __call__(self, builder):
                return builder.error("the callable object ran")

        def is_shape_changed(self):
            return self.error("the function ran")

        add_extension(Refusing())
        add_extension(is_shape_changed, override=True)
        try:
            with pytest.raises(AssertionError) as failure:
                assert_that(1).is_shape_changed()
            assert_that(str(failure.value)).is_equal_to("the function ran")
            assert_that(assertpy.assertpy._extensions).does_not_contain_key("is_shape_changed")
        finally:
            remove_extension(is_shape_changed)

    def test_a_function_is_replaced_by_a_callable_object(self):
        def is_shape_changed(self):
            return self.error("the function ran")

        class Refusing:
            __name__ = "is_shape_changed"

            def __call__(self, builder):
                return builder.error("the callable object ran")

        replacement = Refusing()
        add_extension(is_shape_changed)
        add_extension(replacement, override=True)
        try:
            with pytest.raises(AssertionError) as failure:
                assert_that(1).is_shape_changed()
            assert_that(str(failure.value)).is_equal_to("the callable object ran")
            assert_that(vars(assertpy.assertpy._ExtendedBuilder)).does_not_contain_key("is_shape_changed")
        finally:
            remove_extension(replacement)

    def test_the_replaced_implementation_does_not_come_back_after_a_removal(self):
        """Removal takes the name away rather than uncovering what the override replaced."""

        class Refusing:
            __name__ = "is_shape_changed"

            def __call__(self, builder):
                return builder.error("the callable object ran")

        def is_shape_changed(self):
            return self.error("the function ran")

        add_extension(Refusing())
        add_extension(is_shape_changed, override=True)
        remove_extension(is_shape_changed)
        with pytest.raises(AttributeError) as refused:
            assert_that(1).is_shape_changed()
        assert_that(str(refused.value)).contains("is_shape_changed")

    def test_a_name_lives_in_exactly_one_half_whichever_way_it_was_overridden(self):
        """The invariant the two directions share, stated once rather than implied by the pair above."""

        class Refusing:
            __name__ = "is_shape_changed"

            def __call__(self, builder):
                return builder

        def is_shape_changed(self):
            return self

        first, second = Refusing(), Refusing()
        for installed in (first, is_shape_changed, second):
            add_extension(installed, override=True)
            halves = [
                "is_shape_changed" in vars(assertpy.assertpy._ExtendedBuilder),
                "is_shape_changed" in assertpy.assertpy._extensions,
            ]
            assert_that(halves).described_as(f"where {installed!r} was registered").contains_only(True, False)
        remove_extension(second)
