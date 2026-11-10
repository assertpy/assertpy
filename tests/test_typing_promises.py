"""Both halves of one claim: a checker accepts the promise, and the object matches it.

The cases live in `typing_promises.py`.  A declaration a checker accepts and the runtime contradicts
fails here rather than reaching a user.
"""

from __future__ import annotations

import asyncio
import inspect
import types
import typing

import pytest

from assertpy import assert_that
from tests import typing_harness, typing_promises
from tests.optional import needs


async def _awaited(coroutine):
    return await coroutine


_CASES = {
    name: case
    for name, case in vars(typing_promises).items()
    if inspect.isfunction(case) and not name.startswith("_") and case.__module__ == typing_promises.__name__
}


def test_the_walk_found_the_cases() -> None:
    """A walk that found nothing would agree with every promise below it."""
    assert_that(_CASES).described_as("cases collected from typing_promises.py").is_not_empty()


@pytest.mark.parametrize("name", sorted(_CASES))
def test_the_object_is_what_the_annotation_promised(name: str) -> None:
    """The gate the other typing tests cannot be: it reads the value, not another declaration.

    `isinstance` rather than an equality on the type, so a subclass and a parametrised generic pass: the
    claim is that a consumer can use the result as the declared type.
    """
    case = _CASES[name]
    promised = typing.get_type_hints(case)["return"]
    origin = typing.get_origin(promised) or promised
    # both spellings: `str | None` gives `types.UnionType` and `Optional[str]` gives `typing.Union`
    arms = typing.get_args(promised) if origin in (typing.Union, types.UnionType) else (origin,)
    checked = tuple(typing.get_origin(arm) or arm for arm in arms)

    value = case()
    if inspect.iscoroutine(value):
        # an awaitable chain is the one shape whose promise is about what `await` hands back
        value = asyncio.run(_awaited(value))
    assert_that(isinstance(value, checked)).described_as(
        f"{name}() promised {promised} and returned {value!r} of type {type(value).__name__}"
    ).is_true()


def test_an_ordinary_negated_assertion_runs_the_way_it_says() -> None:
    """The runtime side of the promise above, since a chain typed `bytes` could still hand back another."""
    value = typing_promises.an_ordinary_negated_assertion_also_hands_the_view_back()
    assert_that(value).is_instance_of(bytes).is_equal_to(b"x")


@pytest.mark.parametrize("checker", ["ty", "mypy", "pyright"])
def test_no_checker_disagrees_with_a_promise(checker: str) -> None:
    """An `assert_type` a checker rejects is a promise the surface does not keep.

    All three, because both defects this file was written for were accepted by all of them.
    """
    needs("mypy", delegated_to="the lint job")
    needs("pyright", delegated_to="the lint job")
    path = typing_harness.ROOT / "tests" / "typing_promises.py"
    reported = getattr(typing_harness, checker)(path)
    named = {line: sorted(codes) for line, codes in sorted(reported.items())}
    assert_that(named).described_as(f"{checker} diagnostics over the promises").is_equal_to({})
