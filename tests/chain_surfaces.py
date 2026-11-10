"""One call run on one delivery surface, reduced to what the surfaces must agree on.

A surface is how a verdict reaches the caller: raised (hard), returned (`check()`), collected (soft),
logged (warn), or delivered after a poll, synchronous or awaited. Each runner below catches what its
surface produces and reduces it to an `Answer`, so answers from different surfaces compare directly.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from assertpy import AssertionFailure, soft_assertions
from assertpy.outcome import AssertionOutcome

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable

Step = tuple[str, tuple[Any, ...] | None, dict[str, Any] | None]


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


WARN_HANDLER = _Records()
WARN_LOGGER = logging.getLogger("tests.chain_machine.warn")
WARN_LOGGER.handlers = [WARN_HANDLER]
WARN_LOGGER.setLevel(logging.WARNING)
WARN_LOGGER.propagate = False


@dataclass
class Answer:
    """What one surface made of one call.

    Attributes:
        status: `held`, `failed` or `refused`, or a shape no surface may take: `bare-assertion`,
            `failed-raised`, `not-an-outcome`, `collected-under-check`, `logged-under-check`.
        outcome: The failure record the surface delivered, if it delivered one.
        error: The exception type's name, for a refusal.
        text: The failure or refusal message as the surface delivered it.
        result: What the call handed back: the next builder, or the outcome for `check()`.
        count: How many failures a soft block collected, or how many records a warn call logged.
        raised: The refusal itself, for a refusal: its class and its traceback say what `error` cannot.
    """

    status: str
    outcome: AssertionOutcome | None = None
    error: str = ""
    text: str = ""
    result: Any = None
    count: int = 0
    raised: BaseException | None = None

    def brief(self) -> str:
        detail = self.error or (self.text.splitlines()[0] if self.text else "")
        return f"{self.status}({detail})"


def shown(value: object) -> str:
    try:
        return repr(value)
    except Exception as exc:  # a hostile repr must not end the run
        return f"<unrepr {type(value).__name__}: {type(exc).__name__}>"


def parameters_key(parameters: Any) -> tuple[tuple[str, str], ...]:
    """A mapping compares without order, and so does this: the frame and the signature list kw-only apart."""
    return tuple(sorted((name, shown(value)) for name, value in dict(parameters).items()))


def key_of(outcome: AssertionOutcome | None) -> tuple[object, ...] | None:
    """Everything a failure record says about the check, minus where it was delivered (group, location)."""
    if outcome is None:
        return None
    asked = outcome.requirement
    return (
        outcome.message,
        shown(outcome.actual),
        outcome.actual_provided,
        shown(outcome.expected),
        shown(outcome.diff),
        None if asked is None else (asked.operation, parameters_key(asked.parameters), asked.negated),
        outcome.hint,
    )


def same_value(left: object, right: object) -> bool:
    """The same object, or one of the same type and repr. An exception compares by its args instead."""
    if left is right:
        return True
    if type(left) is not type(right):
        return False
    if isinstance(left, BaseException):
        return left.args == right.args  # ty: ignore[missing-attribute]  # same type, checked above
    return shown(left) == shown(right)


def invoke(target: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Any:
    if negated:
        target = target.not_
    return getattr(target, name)(*args, **kwargs)


def _refused(exc: BaseException) -> Answer:
    return Answer("refused", error=type(exc).__name__, text=str(exc), raised=exc)


def run_hard(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    try:
        result = invoke(builder, name, args, kwargs, negated)
    except AssertionFailure as exc:
        return Answer("failed", outcome=exc._outcome, text=exc._message)
    except AssertionError as exc:
        return Answer("bare-assertion", text=str(exc))
    except Exception as exc:
        return _refused(exc)
    return Answer("held", result=result)


def run_check(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    try:
        proxy = builder.check()
        if negated:
            proxy = proxy.not_
        answered = getattr(proxy, name)(*args, **kwargs)
    except AssertionError as exc:
        return Answer("bare-assertion", text=str(exc))
    except Exception as exc:
        return _refused(exc)
    if not isinstance(answered, AssertionOutcome):
        return Answer("not-an-outcome", result=answered, text=type(answered).__name__)
    if answered.passed:
        return Answer("held", result=answered)
    return Answer("failed", outcome=answered, text=answered.message, result=answered)


def run_soft_check(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    """check() on a soft builder, inside a block: the verdict comes back and nothing is collected."""
    answer = Answer("refused")
    try:
        with soft_assertions():
            answer = run_check(builder, name, args, kwargs, negated)
    except AssertionFailure as exc:
        return Answer("collected-under-check", text=exc._message, count=len(exc.failures))
    return answer


def run_warn_check(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    """check() on a warn builder: the verdict comes back and nothing is logged."""
    WARN_HANDLER.messages.clear()
    answer = run_check(builder, name, args, kwargs, negated)
    if WARN_HANDLER.messages:
        return Answer("logged-under-check", text=WARN_HANDLER.messages[0])
    return answer


def run_soft(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    result = None
    try:
        with soft_assertions():
            result = invoke(builder, name, args, kwargs, negated)
    except AssertionFailure as exc:
        if exc.failures:
            first = exc.failures[0]
            return Answer("failed", outcome=first, text=first.message, result=result, count=len(exc.failures))
        return Answer("failed-raised", outcome=exc._outcome, text=exc._message, result=result)
    except AssertionError as exc:
        return Answer("bare-assertion", text=str(exc))
    except Exception as exc:
        return _refused(exc)
    return Answer("held", result=result)


def run_warn(builder: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    WARN_HANDLER.messages.clear()
    try:
        result = invoke(builder, name, args, kwargs, negated)
    except AssertionFailure as exc:
        return Answer("failed-raised", outcome=exc._outcome, text=exc._message)
    except AssertionError as exc:
        return Answer("bare-assertion", text=str(exc))
    except Exception as exc:
        return _refused(exc)
    if WARN_HANDLER.messages:
        return Answer("failed", text=WARN_HANDLER.messages[0], result=result, count=len(WARN_HANDLER.messages))
    return Answer("held", result=result)


def run_poll(chain: Any, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool) -> Answer:
    """A hard polled chain: a failure is the timeout, carrying the inner failure's record."""
    return run_hard(chain, name, args, kwargs, negated)


def run_async(loop: asyncio.AbstractEventLoop, start: Callable[[], Any], steps: list[Step]) -> Answer:
    """Build an awaited poll chain from the start, replaying every step, and run it on the loop.

    A step with `None` arguments is an attribute read (`not_`), anything else is a call.
    """
    chain = start()
    for name, args, kwargs in steps:
        attribute = getattr(chain, name)
        chain = attribute if args is None else attribute(*args, **(kwargs or {}))
    try:
        result = loop.run_until_complete(chain)
    except AssertionFailure as exc:
        return Answer("failed", outcome=exc._outcome, text=exc._message)
    except AssertionError as exc:
        return Answer("bare-assertion", text=str(exc))
    except Exception as exc:
        return _refused(exc)
    return Answer("held", result=result)


def dup(builder: Any) -> Any:
    """A side probe runs on a copy, so a soft or warn failure it causes does not taint the live chain."""
    return copy.copy(builder)
