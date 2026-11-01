"""A call that hands back an awaitable has its outcome still to come, so no call assertion may judge it.

Judged as it stood, `does_not_raise()` passed on an `async def` that raises when awaited, `raises()` failed
on it, `returned()` handed back the coroutine, and the coroutine warned that it was never awaited.
"""

import asyncio
import collections.abc
import gc
import inspect
import warnings
from functools import partial

import pytest

from assertpy import assert_that, assert_warn, soft_assertions

_REFUSED = r"whose outcome when_called_with\(\) cannot see"


async def _succeeds() -> int:
    return 1


async def _fails() -> int:
    raise ValueError("boom")


async def _warns() -> int:
    warnings.warn("late", UserWarning, stacklevel=2)
    return 1


async def _yields():
    yield 1


class _AsyncCall:
    async def __call__(self) -> int:
        return 1


class _CustomAwaitable:
    def __await__(self):
        yield
        return 1


def _raises_before_it_returns():
    raise ValueError("before")


def _generates():
    raise ValueError("on the first item")
    yield


class _RegisteredOnly:
    """Registered with the ABC, which makes `inspect.isawaitable` say yes, with no `__await__` to await."""


collections.abc.Awaitable.register(_RegisteredOnly)


ROUTES = {
    "raises": lambda builder: builder.raises(ValueError),
    "raises-the-refusal-type": lambda builder: builder.raises(TypeError),
    "does_not_raise": lambda builder: builder.does_not_raise(ValueError),
    "warns": lambda builder: builder.warns(UserWarning),
    "does_not_warn": lambda builder: builder.does_not_warn(UserWarning),
}
PROBES = {
    "async-def": _succeeds,
    "async-def-raising": _fails,
    "async-def-warning": _warns,
    "async-call-object": _AsyncCall(),
    "partial": partial(_fails),
    "async-generator": _yields,
    "custom-awaitable": _CustomAwaitable,
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("probe", PROBES)
def test_every_route_refuses_a_call_whose_outcome_is_still_to_come(route, probe):
    with pytest.raises(TypeError, match=_REFUSED):
        ROUTES[route](assert_that(PROBES[probe])).when_called_with()


def test_the_refusal_says_where_to_look_instead():
    with pytest.raises(TypeError) as refused:
        assert_that(_fails).does_not_raise(ValueError).when_called_with()
    assert_that(str(refused.value)).starts_with("<_fails> returned coroutine").contains(
        "await the call yourself", "eventually()"
    )


def test_an_async_generator_is_told_to_be_iterated_rather_than_awaited():
    with pytest.raises(TypeError) as refused:
        assert_that(_yields).does_not_raise(ValueError).when_called_with()
    assert_that(str(refused.value)).contains("iterate it with `async for`").does_not_contain("await the call")


@pytest.mark.parametrize("probe", [_fails, _AsyncCall(), partial(_fails)], ids=["async-def", "object", "partial"])
def test_a_coroutine_the_call_created_is_closed_rather_than_left_unawaited(probe):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(TypeError, match=_REFUSED):
            assert_that(probe).does_not_raise(ValueError).when_called_with()
        gc.collect()
    assert_that([str(warning.message) for warning in caught]).is_empty()


def test_a_coroutine_handed_back_from_elsewhere_is_left_as_it_was():
    borrowed = _succeeds()
    try:
        with pytest.raises(TypeError, match=_REFUSED):
            assert_that(lambda: borrowed).does_not_raise(ValueError).when_called_with()
        assert_that(inspect.getcoroutinestate(borrowed)).is_equal_to(inspect.CORO_CREATED)
    finally:
        borrowed.close()


def test_a_plain_generator_is_judged_as_returned_and_runs_only_when_consumed():
    returned = assert_that(_generates).does_not_raise(ValueError).when_called_with().returned()
    with pytest.raises(ValueError, match="on the first item"):
        next(returned.val)


def test_a_class_only_registered_as_awaitable_is_not_refused():
    assert_that(_RegisteredOnly).does_not_raise(ValueError).when_called_with()


def test_a_future_it_returned_is_left_alone():
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        with pytest.raises(TypeError, match=_REFUSED):
            assert_that(lambda: future).does_not_raise(ValueError).when_called_with()
        assert_that(future.cancelled()).is_false()
    finally:
        loop.close()


def test_a_call_that_raises_before_it_returns_is_still_judged():
    assert_that(_raises_before_it_returns).raises(ValueError).when_called_with().is_equal_to("before")


def test_a_verdict_asked_for_is_refused_rather_than_answered():
    with pytest.raises(TypeError, match=_REFUSED):
        assert_that(_fails).does_not_raise(ValueError).check().when_called_with()


def test_soft_and_warn_modes_hand_the_refusal_on():
    with pytest.raises(TypeError, match=_REFUSED), soft_assertions():
        assert_that(_fails).raises(ValueError).when_called_with()
    with pytest.raises(TypeError, match=_REFUSED):
        assert_warn(_fails).does_not_raise(ValueError).when_called_with()


def test_a_polled_call_is_refused_too():
    with pytest.raises(TypeError, match=_REFUSED):
        assert_that(lambda: _fails).eventually_sync(timeout=0, interval=0).raises(ValueError).when_called_with()
