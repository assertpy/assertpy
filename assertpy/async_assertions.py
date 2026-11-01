from __future__ import annotations

import dataclasses
import hashlib
import inspect
import math
import numbers
import time
import warnings
from collections import OrderedDict, deque
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final

from . import _passes
from ._engine._compare import _is_infinite, _is_nan
from ._engine._operations import DESCRIBES, WITHOUT_A_VERDICT
from ._engine._require import argument, refuse
from .errors import AssertionFailure, PollSample, PollTrace, _json_safe, _safe_repr, _safe_str
from .exception import _InertBuilder, named_classes

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from ._engine._compat import Self
    from ._matcher_impls import RetriedInfo

__tracebackhide__ = True

_PROBE_UNSET = object()


_CONTAINERS: Final = (dict, set, frozenset, tuple, list)
"""The kinds `_canonical` looks inside, which are also the only ones that can reach back to themselves."""


def _canonical(value: object, _seen: frozenset[int] = frozenset()) -> str:
    """A type-faithful rendering of *value*, with containers ordered where their type has no order.

    Not for reading: this exists so one poll's value can be told from the next's.  JSON was tried first
    and erases exactly what matters here, since `(1,)` and `[1]` both render as `[1]` and a mapping's
    keys all become strings.  A tag carries the container's type instead, and every part is written with
    its own length in front, so nothing a value prints can be read as this rendering's punctuation: a
    leaf whose repr is `[1,2]` used to render exactly as the list `[1, 2]` did.

    Dicts and sets are sorted by their rendered parts: they have no order to preserve, and two equal ones
    can still iterate differently, since a set built from `[0, 8]` and one built from `[8, 0]` collide
    into the same bucket in opposite orders.

    The boundary, since a rendering cannot reproduce `==`: two values that are equal and print
    differently, `1` against `1.0`, count as a change, and two that are unequal and print alike, a
    dataclass hiding a field from its own repr, count as one value.  A leaf carries no type tag of its
    own for the same reason, or a `str` subclass would differ from the string it equals.

    One case cannot be got right by any key of this shape, rather than being a choice made here:
    `OrderedDict([a, b]) == {a: ..., b: ...} == OrderedDict([b, a])` while the two `OrderedDict`s are
    unequal, so Python's own relation is not transitive there and nothing that digests one value at a
    time can follow it.  The ordered pair is the one honoured, because that is where the order carries
    the meaning.
    """
    if not isinstance(value, _CONTAINERS):
        # a leaf cannot reach back to anything, and the two set operations cost more than rendering it
        rendered = repr(value)
        return f"v{len(rendered)}:{rendered}"
    if id(value) in _seen:
        return "c"  # a container that reaches back to its own root, as `repr` marks with `...`
    inner = _seen | {id(value)}
    if isinstance(value, dict):
        pairs = (_framed(_canonical(key, inner)) + _framed(_canonical(held, inner)) for key, held in value.items())
        # sorted for every mapping but `OrderedDict`, the one whose own `==` reads order
        return "o" + "".join(pairs) if isinstance(value, OrderedDict) else "d" + "".join(sorted(pairs))
    if isinstance(value, (set, frozenset)):
        return "s" + "".join(sorted(_framed(_canonical(member, inner)) for member in value))
    if isinstance(value, tuple):
        return "t" + "".join(_framed(_canonical(member, inner)) for member in value)
    return "l" + "".join(_framed(_canonical(member, inner)) for member in value)


def _framed(text: str) -> str:
    """*text* with its own length in front, so no rendering can be mistaken for a longer one."""
    return f"{len(text)}:{text}"


def _change_key(value: object) -> str | None:
    """A bounded stand-in for what a probe returned, for deciding whether the value moved.

    ``None`` where no faithful one can be made, which is what stops the summary claiming a value moved,
    or held still, on evidence it does not have.

    Four things have to hold at once.  It must be **complete**, because the sample kept per poll is a
    diagnostic snapshot cut after a hundred items, and comparing those called a queue that grew past its
    hundredth entry unchanged for the rest of the run.  It must be **type-faithful**, since a probe that
    started returning a list where it returned a tuple did change.  It must not depend on **order** a
    value does not have, since two dicts that differ only in insertion order are equal.  And it must
    survive a **live** object, because probes commonly mutate and return the same one, so anything that
    compares the object rather than a rendering of it answers "unchanged" whatever it did.
    """
    try:
        text = _canonical(value)
    except Exception:  # their `__repr__` raised, or their container did when walked
        return None
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


# `None` args mark a step that was read rather than called, which is `not_`
_Step = tuple[str, "tuple[Any, ...] | None", "dict[str, Any] | None"]


_COLLECT_RETRIES: bool = False
"""Whether retried polls are collected at all.

Turned on by the pytest plugin, which is the only consumer: it drains the list per test and reports at
session end.  Off everywhere else (unittest, a plain script, ``-p no:assertpy``) so nothing accumulates
in a process that would never read it.
"""

_RETRIES: list[tuple[int, float, float]] = []
"""Polls that only passed after retrying, as ``(attempts, elapsed, budget)``.

The recorder already samples every failed poll, so a probe that converges on its third attempt has
already paid for the first two: collecting them costs a list append on a path that has just spent
several sleeps.  Drained by the pytest plugin, which knows which test they belong to.
"""


class _PollRecorder:
    """Collects per-poll samples, collapsing identical runs and keeping the first and last polls."""

    def __init__(self, head: int = 5, tail: int = 20):
        self._head: list[PollSample] = []
        self._head_limit = head
        self._tail: deque[PollSample] = deque(maxlen=tail)
        # reading recurrence off the cut snapshots instead called five distinct hundred-item lists a cycle
        self._head_keys: list[str | None] = []
        self._tail_keys: deque[str | None] = deque(maxlen=tail)
        self.dropped = 0
        self.total_polls = 0
        # counted as it happens: the window keeps 25 samples, so a value new on each of 1337 polls read as 24
        self.fail_polls = 0
        self.error_polls = 0
        self.value_changes = 0
        # since the last raising poll, because "value then changed" is a claim about what followed the recovery
        self.changes_after_last_error = 0
        self.uncomparable = False
        self.last_change_elapsed: float | None = None
        self.error_type: type | None = None
        self.mixed_error_types = False
        self.last_outcome: str | None = None
        self._last_fail_key: str | None = None

    def record(self, elapsed, outcome, value, detail, raw=_PROBE_UNSET, error_type=None):
        self.total_polls += 1
        self.last_outcome = outcome
        key = None
        if outcome == "fail":
            self.fail_polls += 1
            # against the last value a poll returned: a probe that raises in between still moved from A to B
            key = _change_key(value if raw is _PROBE_UNSET else raw)
            if key is None:
                self.uncomparable = True
            elif self._last_fail_key is not None and key != self._last_fail_key:
                self.value_changes += 1
                self.changes_after_last_error += 1
                self.last_change_elapsed = elapsed
            if key is not None:
                self._last_fail_key = key
        else:  # the only other outcome is "error"
            self.error_polls += 1
            self.changes_after_last_error = 0
            # the class itself, by identity: two classes can share a `__name__`
            if error_type is not None:
                if self.error_type is None:
                    self.error_type = error_type
                elif error_type is not self.error_type:
                    self.mixed_error_types = True
        last = self._tail[-1] if self._tail else (self._head[-1] if self._head else None)
        last_key = self._tail_keys[-1] if self._tail_keys else (self._head_keys[-1] if self._head_keys else None)
        # decided by the key: two polls whose values differ past the cut are two polls
        same_value = (
            key == last_key and key is not None if outcome == "fail" else last is not None and last.value == value
        )
        if last is not None and last.outcome == outcome and last.detail == detail and same_value:
            collapsed = dataclasses.replace(last, repeats=last.repeats + 1)
            if self._tail:
                self._tail[-1] = collapsed
            else:
                self._head[-1] = collapsed
            return
        sample = PollSample(elapsed=elapsed, outcome=outcome, value=value, detail=detail)
        if len(self._head) < self._head_limit:
            self._head.append(sample)
            self._head_keys.append(key)
            return
        if len(self._tail) == self._tail.maxlen:
            self.dropped += 1
        self._tail.append(sample)
        self._tail_keys.append(key)

    def build(self, elapsed) -> PollTrace:
        samples = self._head + list(self._tail)
        self.kept_keys = self._head_keys + list(self._tail_keys)
        return PollTrace(
            samples=samples,
            total_polls=self.total_polls,
            dropped=self.dropped,
            elapsed=elapsed,
            summary=_summarize(samples, self, elapsed),
        )


def _summarize(samples, recorder, elapsed) -> str:
    """Classify the convergence trend of a timed-out poll into one diagnostic sentence.

    Every count and every type here comes from the recorder, which saw all of the run.  The retained
    samples are read for one thing only, the *shape* of what repeated, and that sentence names the polls
    it was read from rather than borrowing the run's total.
    """
    total_polls = recorder.total_polls
    if recorder.fail_polls == 0:
        raised = (
            "exceptions" if recorder.mixed_error_types or recorder.error_type is None else recorder.error_type.__name__
        )
        return f"probe raised {raised} on all {total_polls} polls"
    change_word = "time" if recorder.value_changes == 1 else "times"
    if recorder.error_polls:
        poll_word = "poll" if recorder.error_polls == 1 else "polls"
        since = recorder.changes_after_last_error
        # the run-wide total counts movement from before the last raising poll as well
        if recorder.uncomparable:
            trend = "value could not be compared"
        elif since:
            trend = f"value then changed {since} {'time' if since == 1 else 'times'}"
        else:
            trend = "value then never changed"
        # "recovered" is a claim about order, and a probe that raised, returned and raised again ended raising
        if recorder.last_outcome == "fail":
            return f"probe recovered after {recorder.error_polls} raising {poll_word}; {trend}"
        return f"probe raised on {recorder.error_polls} of {total_polls} polls; {trend}"
    if recorder.uncomparable:
        # no count of movement would be one this recorder took.  Reached only where every poll returned
        return f"value could not be compared across {total_polls} polls"
    if not recorder.value_changes:
        return f"value unchanged across {total_polls} polls"
    kept = [(sample, key) for sample, key in zip(samples, recorder.kept_keys, strict=True) if sample.outcome == "fail"]
    fails = [sample for sample, _ in kept]
    keys = [key for _, key in kept]
    kept_changes = [right for left, right in pairwise(keys) if left != right]
    distinct = {key for key in keys if key is not None}
    # a simple path through k values takes k-1 changes, so a surplus means the probe returned to a reported value
    if len(kept_changes) >= len(distinct):
        kept_polls = sum(sample.repeats for sample in fails)
        over = f"in the {kept_polls} polls kept" if recorder.dropped else f"across {total_polls} polls"
        return f"value cycles between {len(distinct)} states {over}"
    # recorded when it happened rather than read back off the retained samples
    last_change = elapsed - (recorder.last_change_elapsed or 0.0)
    return f"value changed {recorder.value_changes} {change_word}; last change {last_change:.1f}s before the deadline"


def _last_failure_text(exc: BaseException) -> str:
    """The inner failure's headline, without whatever its own rendering would append.

    Outside pytest a failure renders its diff into ``str()``, and the timeout message quotes that text
    while carrying the same diff itself: the reader saw the block twice, once inside the sentence and
    once under it.  Under pytest the plugin turns that rendering off, so the doubling only ever showed
    up where the message is all there is, which is the surface it was added for.
    """
    if isinstance(exc, AssertionFailure):
        # our own class, and the only undecorated form of its message
        return exc._message
    # reading an ignored exception's `__repr__` is running the caller's code, and one that raised escaped the poll
    return _safe_str(exc) if isinstance(exc, AssertionError) else _safe_repr(exc)


def _duration(value: object, name: str, *, endless: bool) -> float:
    """*value* as the seconds a poll waits, refused where it is given rather than inside the loop.

    A NaN timeout compared false against every clock reading and polled forever.  A string or a `Decimal`
    failed in the deadline arithmetic, and an interval `time.sleep` cannot take failed in its C code, while
    the async loop slept a negative one as zero.  An endless timeout is kept, since waiting until the
    condition holds is a thing to ask for, and one past the float range is endless.
    """
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        refuse(value, "a number of seconds", subject=argument(name))
    try:
        seconds = float(value)
    except OverflowError:
        seconds = -math.inf if value < 0 else math.inf
    if _is_nan(seconds) or seconds < 0 or (not endless and _is_infinite(seconds)):
        shape = "a non-negative number of seconds" if endless else "a finite, non-negative number of seconds"
        raise ValueError(f"given {name} arg must be {shape}, but was <{value}>")
    return seconds


def _seconds(timeout: float) -> str:
    """The budget as it was given: `:.1f` printed 0.04 as 0.0, and `:g` rounds past six digits."""
    return str(float(timeout))


def _timeout_failure(recorder: _PollRecorder | None, timeout: float, elapsed: float, failure: str):
    """Build the ``(message, trace)`` pair for a timed-out poll; without a recorder there is no trace."""
    if recorder is None:
        return f"Expected condition not met after {_seconds(timeout)} seconds. Last failure: {failure}", None
    trace = recorder.build(elapsed)
    message = f"Expected condition not met after {_seconds(timeout)} seconds ({trace.summary}). Last failure: {failure}"
    return message, trace


def _structured_of(last_error: Exception | None) -> dict[str, Any]:
    """The values and the diff of the assertion that kept failing, as `error()` keyword arguments.

    Only the ones it actually named: `error()` reads "was this named" from whether the argument is there
    at all, so passing everything would put an empty block under every collected timeout.  Which ones
    those were comes from the failure's own record rather than from a test against `None`, because
    `is_equal_to(None)` names an expected value and a probe returning `None` provides an actual one.
    """
    outcome = getattr(last_error, "_outcome", None)
    fields: dict[str, Any] = {}
    if outcome is not None:
        if outcome.actual_provided:
            fields["actual"] = getattr(last_error, "actual", None)
        if outcome.has_expected:
            fields["expected"] = getattr(last_error, "expected", None)
    else:  # built by hand, by a snapshot re-wrap or by `eventually()` itself: the values are all there is
        for name in ("actual", "expected"):
            value = getattr(last_error, name, None)
            if value is not None:
                fields[name] = value
    diff = getattr(last_error, "diff", None)
    if diff is not None:
        fields["diff"] = diff
    # the inner assertion's, not the poll's: a timeout is that assertion's failure with a wait in front
    if outcome is not None and outcome.requirement is not None:
        fields["requirement"] = outcome.requirement
    return fields


def _timed_out(message: str, trace: PollTrace | None, last_error: Exception | None) -> AssertionFailure:
    """The timeout failure, carrying the structured payload of the assertion that kept failing.

    A polling failure *is* that assertion's failure with a waiting line in front of it, so dropping the
    values and the diff on the way out left the two surfaces unequal where it mattered most: under
    pytest the diff section is built from `exc.diff`, and a timed-out equality printed no section at all
    while the same equality outside a poll printed the full one.

    The record travels with them.  Without it the report falls back to reading "was this named" off a
    test against `None`, which is wrong in both directions: `is_equal_to(None)` lost its expected value,
    a probe returning `None` lost its actual one, and `is_not_empty()`, which names neither, gained a
    block of values nobody asked about.
    """
    failure = AssertionFailure(
        message,
        actual=getattr(last_error, "actual", None),
        expected=getattr(last_error, "expected", None),
        diff=getattr(last_error, "diff", None),
        trace=trace,
        requirement=getattr(last_error, "requirement", None),
    )
    failure._outcome = getattr(last_error, "_outcome", None)
    failure._compared = _pair_kept(last_error)
    return failure


def _pair_kept(last_error: Exception | None) -> tuple[object, object] | None:
    """The pair the attempt that kept failing compared, read off a failure of this library's class alone.

    Anything may sit under the name on another exception, and one that raises when read must not cost the
    timeout it is being read for.
    """
    if not isinstance(last_error, AssertionFailure):
        return None
    try:
        return last_error._compared
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None


def _normalize_ignoring(ignoring) -> tuple[type[Exception], ...]:
    """Normalize an ``ignoring`` spec (one exception type, or a union or a tuple of them) to a flat validated tuple.

    Only ``Exception`` subclasses are accepted, so ``BaseException``-only classes such as
    ``KeyboardInterrupt`` can never be swallowed by the polling loop.  Flat because ``except`` takes a class
    or a tuple of classes and no union, and ``()`` stays the default it always was: nothing is retried.
    """
    expectation = "an Exception subclass, or a union or a tuple of them"
    return named_classes(ignoring, Exception, expectation, subject="ignoring", allow_empty=True)


def _replay(builder_func: Callable, val: object, description: str, steps: tuple[_Step, ...], quiet: int = 0) -> Any:
    """Run a chain's recorded calls against a fresh builder over *val*, returning the last result.

    The first *quiet* steps report nothing to a `log_passes()` block, having been reported by the call that added them.
    """
    builder = builder_func(val, description)
    # inside an observed call every step is already quiet, and a failure has to mark that call
    if quiet and _passes.open_blocks and _passes.current_call() is None:
        return _replay_quietly(builder, steps, quiet)
    for step, step_args, step_kwargs in steps:
        attribute = getattr(builder, step)
        # `not_` is read, not called, so it has no arguments
        builder = attribute if step_args is None or step_kwargs is None else attribute(*step_args, **step_kwargs)
    return builder


def _replay_quietly(builder: Any, steps: tuple[_Step, ...], quiet: int) -> Any:
    """`_replay`'s loop with the first *quiet* steps run as if inside another assertion, which reports for them."""
    for index, (step, step_args, step_kwargs) in enumerate(steps):
        marker = _passes.Observed() if index < quiet else None
        token = _passes.observed.set(marker) if marker is not None else None
        try:
            attribute = getattr(builder, step)
            builder = attribute if step_args is None or step_kwargs is None else attribute(*step_args, **step_kwargs)
        finally:
            if marker is not None and token is not None:
                marker.alive = False
                _passes.observed.reset(token)
    return builder


def _record_poll(recorder: _PollRecorder | None, exc: Exception, probed: object, elapsed: float) -> str:
    """Record one failed poll, when this chain is recording, and hand back the inner failure's text."""
    failure = _last_failure_text(exc)
    if recorder is not None:
        recorder.record(
            elapsed=elapsed,
            # a probe that raised returned no value, so nothing here failed a check
            outcome="fail" if probed is not _PROBE_UNSET else "error",
            # snapshot now: probes commonly mutate and return the same object
            value=_json_safe(probed) if probed is not _PROBE_UNSET else None,
            detail=failure,
            raw=probed,
            error_type=None if probed is not _PROBE_UNSET else type(exc),
        )
    return failure


_NO_VERDICT_AFTER_A_POLL: Final = (
    "check() cannot follow a poll; a poll delivers its own failure, so there is no verdict to hand back"
)

_NO_VALUE_ON_A_CHAIN: Final = "value cannot be read on a polling chain; read `.val` once an assertion on it has passed"


def _out_of_time(
    chain: AsyncAssertionBuilder | SyncAssertionBuilder,
    recorder: _PollRecorder | None,
    elapsed: float,
    failure: str,
    last_error: Exception | None,
) -> Any:
    """Deliver the timeout the way this chain's mode asks for: collected, logged, or raised."""
    message, trace = _timeout_failure(recorder, chain._timeout, elapsed, failure)
    if chain._kind in ("soft", "warn"):
        # empty description: the inner failure already carries it, and two would read as a double prefix
        # over the value the failing assertion saw, as the raised timeout records it: over `None` it recorded `None`
        chain._builder_func(getattr(last_error, "actual", None), "", chain._kind, None, chain._logger).error(
            message, **_structured_of(last_error), trace=trace
        )
        # the poll never reached a value, so anything after it asserted about `None` and failed again.
        # It carries the timeout, which is the failure a reader acts on: without it `check()` answered
        # `passed=False` with an empty message and the refusals named the rule and not the cause
        return _InertBuilder(message)
    raise _timed_out(message, trace, last_error) from last_error


class AsyncAssertionBuilder:
    """Async assertion builder that polls a callable until an assertion passes or timeout expires.

    Do not instantiate directly; use [`eventually()`][assertpy.assertpy.AssertionBuilder.eventually] instead.

    A chain records the calls made on it and runs them together when awaited, so the wait covers every
    link rather than only the first.  The four coroutine methods below make it a coroutine to
    `asyncio.run()` and `Task`, which take nothing else below 3.15.

    Args:
        func: a sync or async callable that produces the value to test
        builder_func: factory function to create assertion builders (receives ``val``, ``description``)
        description: optional error description forwarded to the builder
        timeout: maximum seconds to keep retrying
        interval: seconds between retries
        ignoring: exception types the polling loop retries instead of propagating
        kind: the failure mode of the *final* timeout failure (``None``/``"soft"``/``"warn"``);
            polling itself always retries on hard failures
        logger: the logger for ``"warn"`` mode
        trace: record a [`PollTrace`][assertpy.errors.PollTrace] of the polling timeline
            (default ``True``); ``False`` skips the flight recorder entirely
    """

    def __init__(
        self,
        func: Callable,
        *,
        builder_func: Callable,
        description: str = "",
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: tuple[type[Exception], ...] = (),
        kind: str | None = None,
        logger: object = None,
        trace: bool = True,
        steps: tuple[_Step, ...] = (),
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = _duration(timeout, "timeout", endless=True)
        self._interval = _duration(interval, "interval", endless=False)
        self._ignoring = ignoring
        self._kind = kind
        self._logger = logger
        self._trace = trace
        self._steps = steps  # replayed as a whole on every poll, see `_replay`
        self._coro: Any = None
        self._awaited = False
        self._superseded = False

    def _chained(self, steps: tuple[_Step, ...]) -> AsyncAssertionBuilder:
        """A copy carrying one more step, so awaiting the chain waits for all of them together.

        Marks the link it grew out of as handed on, or `__del__` would call it an abandoned chain.
        """
        self._superseded = True
        return AsyncAssertionBuilder(
            self._func,
            builder_func=self._builder_func,
            description=self._description,
            timeout=self._timeout,
            interval=self._interval,
            ignoring=self._ignoring,
            kind=self._kind,
            logger=self._logger,
            trace=self._trace,
            steps=steps,
        )

    def within(self, timeout: float) -> Self:
        """Override the timeout (in seconds).

        Infinity, or a number past the float range, retries until the assertion passes.

        Raises:
            TypeError: if ``timeout`` is not a real number, or is a bool
            ValueError: if ``timeout`` is negative or NaN
        """
        self._timeout = _duration(timeout, "timeout", endless=True)
        return self

    def every(self, interval: float) -> Self:
        """Override the polling interval (in seconds).

        Raises:
            TypeError: if ``interval`` is not a real number, or is a bool
            ValueError: if ``interval`` is negative, NaN or infinite
        """
        self._interval = _duration(interval, "interval", endless=False)
        return self

    def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> Self:
        """Replace the exception types the polling loop retries instead of propagating.

        Examples:
            Usage:

                await assert_that(get_order).eventually().within(10).ignoring(ConnectionError).has_status("PAID")

        Raises:
            TypeError: if any argument is not an ``Exception`` subclass
        """
        self._ignoring = _normalize_ignoring(exceptions)
        return self

    def __getattr__(self, name: str) -> Any:
        # `Any` rather than the inferred union, which made a checker refuse `eventually().is_equal_to(1)`
        if name.startswith("_"):
            raise AttributeError(name)
        # forwarded whole: the state attribute is `cr_suspended` on 3.11 and `cr_state` on 3.14, and `gi_` is refused
        if name.startswith("gi_"):
            raise AttributeError(name)
        if name.startswith("cr_"):
            if not self._steps:
                raise AttributeError(name)  # nothing recorded yet, so there is no coroutine to describe
            return getattr(self._coroutine(), name)
        if name == "check":
            raise TypeError(_NO_VERDICT_AFTER_A_POLL)
        if name in ("val", "value"):
            raise AttributeError(f"{name} is available on the builder that awaiting this chain returns")
        if name == "not_":
            return self._chained((*self._steps, (name, None, None)))  # read, not called: no arguments

        def _add(*args: Any, **kwargs: Any) -> AsyncAssertionBuilder:
            return self._chained((*self._steps, (name, args, kwargs)))

        return _add

    def _coroutine(self) -> Any:
        """The coroutine this chain runs, made on first use and kept, since a coroutine runs only once."""
        if self._coro is None:
            self._coro = self._poll()
        return self._coro

    def _started(self) -> Any:
        """The coroutine, marked as somebody's responsibility, which is what running it makes it.

        A closed chain needs no guard here: `close()` closes the coroutine, and awaiting a closed one
        already raises the "cannot reuse already awaited coroutine" a plain coroutine raises.
        """
        if all(WITHOUT_A_VERDICT.get(name) == DESCRIBES for name, _, _ in self._steps):
            self._awaited = True  # refused here, so not also reported as never awaited once it is collected
            raise TypeError("no assertion was called on this eventually() chain, so awaiting it would wait for nothing")
        coro = self._coroutine()
        self._awaited = True
        return coro

    def __await__(self) -> Generator[Any, None, Any]:
        """Poll until every call recorded on this chain passes together, or the timeout expires.

        Returns the ordinary builder over the value that passed, so anything asked of it afterwards is
        a plain assertion on that settled value rather than a new wait.
        """
        return self._started().__await__()

    # these three with `__await__` are what `Coroutine` checks structurally, so `asyncio.run(chain)` works below 3.15
    def send(self, value: Any) -> Any:
        return self._started().send(value)

    def throw(self, *args: Any, **kwargs: Any) -> Any:
        return self._started().throw(*args, **kwargs)

    def close(self) -> None:
        self._awaited = True  # an asked-for discard, and Python says nothing about a closed coroutine
        if self._steps:  # made if it does not exist, so it refuses to run and reads as closed
            self._coroutine().close()

    def __del__(self) -> None:
        """Warn about a chain built and never awaited: only its end is awaited, so only its end warns."""
        coro = getattr(self, "_coro", None)  # a construction that raised leaves none of these fields
        # asked of the coroutine rather than tracked by a flag: `__await__()` can be called and its iterator dropped
        unstarted = False
        if coro is not None and inspect.getcoroutinestate(coro) == inspect.CORO_CREATED:
            coro.close()  # or Python warns about it too, naming this module rather than the chain
            unstarted = True
        steps = getattr(self, "_steps", ())
        if not steps or self._superseded or warnings is None:  # None once shutdown clears it
            return
        if self._awaited and not unstarted:
            return
        # unguarded: under `filterwarnings = error` this raises, and that raise is the point
        warnings.warn(
            f"an eventually() chain ending in {steps[-1][0]}() was never awaited, so nothing was asserted",
            RuntimeWarning,
            stacklevel=1,  # the stack at collection time is not the code that built the chain
        )

    async def _poll(self) -> Any:
        # not at module level: asyncio costs 21ms of a 59ms import and only this path needs it, already inside a loop
        import asyncio

        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + self._timeout
        recorder = _PollRecorder() if self._trace else None
        last_error: Exception | None = None
        while True:
            probed = _PROBE_UNSET
            # held across the probe as well, whose own assertions are part of the attempt; released before the backoff
            kept = _passes.holding() if _passes.open_blocks else None
            token = _passes.held.set(kept) if kept is not None else None
            try:
                try:
                    val = self._func()
                    if inspect.isawaitable(val):
                        val = await val
                    probed = val
                    builder = _replay(self._builder_func, val, self._description, self._steps)
                finally:
                    if kept is not None and token is not None:
                        _passes.release(kept, token)
                if _COLLECT_RETRIES and recorder is not None and recorder.total_polls:
                    # a probe that only converges after retrying is the one that goes flaky in CI
                    _RETRIES.append((recorder.total_polls + 1, loop.time() - start, self._timeout))
            except (
                AssertionError,
                *self._ignoring,
            ) as exc:  # retry-on-failure needs the try/except per poll iteration
                last_error = exc
                failure = _record_poll(recorder, exc, probed, loop.time() - start)
                now = loop.time()
                if now >= deadline:
                    return _out_of_time(self, recorder, now - start, failure, last_error)
                await asyncio.sleep(min(self._interval, deadline - now))
                continue
            if kept is not None:
                _passes.flush(kept)
            return builder


class SyncAssertionBuilder:
    """Blocking assertion builder that polls a sync callable until an assertion passes or timeout expires.

    Do not instantiate directly; use
    [`eventually_sync()`][assertpy.assertpy.AssertionBuilder.eventually_sync] instead.

    Args:
        func: a sync callable that produces the value to test (an async probe raises ``TypeError``)
        builder_func: factory function to create assertion builders (receives ``val``, ``description``)
        description: optional error description forwarded to the builder
        timeout: maximum seconds to keep retrying
        interval: seconds between retries
        ignoring: exception types the polling loop retries instead of propagating
        kind: the failure mode of the *final* timeout failure (``None``/``"soft"``/``"warn"``);
            polling itself always retries on hard failures
        logger: the logger for ``"warn"`` mode
        trace: record a [`PollTrace`][assertpy.errors.PollTrace] of the polling timeline
            (default ``True``); ``False`` skips the flight recorder entirely
    """

    def __init__(
        self,
        func: Callable,
        *,
        builder_func: Callable,
        description: str = "",
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: tuple[type[Exception], ...] = (),
        kind: str | None = None,
        logger: object = None,
        trace: bool = True,
        steps: tuple[_Step, ...] = (),
        last: Any = None,
    ):
        self._func = func
        self._builder_func = builder_func
        self._description = description
        self._timeout = _duration(timeout, "timeout", endless=True)
        self._interval = _duration(interval, "interval", endless=False)
        self._ignoring = ignoring
        self._kind = kind
        self._logger = logger
        self._trace = trace
        self._steps = steps  # replayed as a whole on every poll, see `_replay`
        self._last = last

    @property
    def val(self) -> object:
        """The value the last passing poll saw.

        Declared on the class rather than left to `__getattr__`, which answers every other name with a
        polling call: reading `.val` off a chain would otherwise poll once and hand back a function.

        Before anything has passed there is no such value, and `__getattr__` says so.  A raise here
        would not: Python falls back to `__getattr__` whenever an attribute lookup ends in
        `AttributeError`, property included, so the message would have been swallowed and answered with
        a polling call all the same.
        """
        return self._last.val

    def _chained(self, steps: tuple[_Step, ...], last: Any = None) -> SyncAssertionBuilder:
        """A copy carrying one more step, so the next call in the chain polls with all of them."""
        return SyncAssertionBuilder(
            self._func,
            builder_func=self._builder_func,
            description=self._description,
            timeout=self._timeout,
            interval=self._interval,
            ignoring=self._ignoring,
            kind=self._kind,
            logger=self._logger,
            trace=self._trace,
            steps=steps,
            last=self._last if last is None else last,
        )

    def within(self, timeout: float) -> Self:
        """Override the timeout (in seconds).

        Infinity, or a number past the float range, retries until the assertion passes.

        Raises:
            TypeError: if ``timeout`` is not a real number, or is a bool
            ValueError: if ``timeout`` is negative or NaN
        """
        self._timeout = _duration(timeout, "timeout", endless=True)
        return self

    def every(self, interval: float) -> Self:
        """Override the polling interval (in seconds).

        Raises:
            TypeError: if ``interval`` is not a real number, or is a bool
            ValueError: if ``interval`` is negative, NaN or infinite
        """
        self._interval = _duration(interval, "interval", endless=False)
        return self

    def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> Self:
        """Replace the exception types the polling loop retries instead of propagating.

        Examples:
            Usage:

                assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")

        Raises:
            TypeError: if any argument is not an ``Exception`` subclass
        """
        self._ignoring = _normalize_ignoring(exceptions)
        return self

    def __getattr__(self, name: str) -> Any:
        # `Any` rather than the inferred union, which made a checker refuse `eventually_sync().is_equal_to(1)`
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "check":
            raise TypeError(_NO_VERDICT_AFTER_A_POLL)
        if name == "value":
            raise TypeError(_NO_VALUE_ON_A_CHAIN)
        if name == "val":  # reached only when the property above found no poll to read it from
            raise AttributeError("val is available once an assertion on this chain has passed")
        if name == "not_":
            # a property, so it joins the chain and is re-taken per poll: read straight, `.not_.is_equal_to(1)` died
            return self._chained((*self._steps, (name, None, None)))

        def _run(*args, **kwargs):
            steps = (*self._steps, (name, args, kwargs))
            start = time.monotonic()
            deadline = start + self._timeout
            recorder = _PollRecorder() if self._trace else None
            last_error: Exception | None = None
            while True:
                probed = _PROBE_UNSET
                kept = _passes.holding() if _passes.open_blocks else None
                token = _passes.held.set(kept) if kept is not None else None
                try:
                    try:
                        val = self._func()
                        if inspect.isawaitable(val):
                            if inspect.iscoroutine(val):
                                val.close()  # an orphaned coroutine would warn "never awaited" at GC time
                            raise TypeError(
                                "given probe returned an awaitable; use eventually() and await it for async probes"
                            )
                        probed = val
                        # a blocking chain polls all of it at every call, and the call reports the step it added
                        builder = _replay(self._builder_func, val, self._description, steps, len(steps) - 1)
                    finally:
                        if kept is not None and token is not None:
                            _passes.release(kept, token)
                    if _COLLECT_RETRIES and recorder is not None and recorder.total_polls:
                        _RETRIES.append((recorder.total_polls + 1, time.monotonic() - start, self._timeout))
                except (
                    AssertionError,
                    *self._ignoring,
                ) as exc:  # retry-on-failure needs the try/except per poll iteration
                    last_error = exc
                    failure = _record_poll(recorder, exc, probed, time.monotonic() - start)
                    now = time.monotonic()
                    if now >= deadline:
                        return _out_of_time(self, recorder, now - start, failure, last_error)
                    time.sleep(min(self._interval, deadline - now))
                    continue
                if kept is not None:
                    _passes.flush(kept)
                return self._chained(steps, builder)

        return _run
