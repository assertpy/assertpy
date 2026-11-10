"""Assertion library for python unit testing with a fluent API"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import inspect
import logging
import os
import sys
import threading
import types
from dataclasses import replace
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Generic,
    Literal,
    NoReturn,
    Protocol,
    SupportsIndex,
    TypeVar,
    cast,
    overload,
)

if TYPE_CHECKING:
    import datetime
    import pathlib
    from collections.abc import Callable, Collection, Mapping

    from typing_extensions import TypeIs

    from ._engine._builder_check_typing import _CheckAnyValue
    from ._engine._capable_typing import _CapableAssertion
    from ._engine._compat import Self
    from ._engine._typing import (
        _ArrayAssertion,
        _ArrayT_co,
        _BoolAssertion,
        _BytesAssertion,
        _CallableAssertion,
        _CapableT,
        _ComplexAssertion,
        _DateAssertion,
        _DateTimeAssertion,
        _DictAssertion,
        _FrameAssertion,
        _FrameT_co,
        _IterableAssertion,
        _NumericAssertion,
        _ObjectAssertion,
        _PathAssertion,
        _StringAssertion,
    )
    from ._matcher_impls import ClassInfo, ExceptionInfo, RetriedInfo
    from ._passes import PassLogger
    from .errors import PollTrace
    from .matchers import Matcher

from . import _hints, _passes
from . import errors as _errors
from ._engine._compat import _LoggerAdapter
from ._engine._contract import exactness_failure, kept_apart, put_as_sent, put_back, runs_own_code, sent_record
from ._engine._introspection import ASSERTPY_FILES, WarningLogger, is_same_implementation
from ._engine._operations import (
    ALSO_ASSERTS,
    CONFIGURES,
    DESCRIBES,
    HANDS_THE_SUBJECT_BACK,
    NOT_AN_OPERATION,
    POLLS,
    TRANSFORMS,
    WHAT_IT_DOES,
    WITHOUT_A_VERDICT,
)
from ._engine._path import _ROOT, _Path
from ._engine._require import argument, refuse, verdict
from .async_assertions import AsyncAssertionBuilder, SyncAssertionBuilder, _normalize_ignoring
from .base import BaseMixin
from .bytes_mixin import BytesMixin
from .collection import CollectionMixin
from .contains import ContainsMixin
from .dataframe import DataFrameMixin
from .date import DateMixin
from .dict import DictMixin
from .dynamic import DynamicMixin, _one_operand
from .errors import (
    AssertionFailure,
    DiffEntry,
    DiffResult,
    Step,
    _capped,
    _capped_repr,
    _diff_sides,
    _render_diff,
    _safe_str,
    _truncated,
    _windowed,
)
from .exception import _UNSET, ExceptionMixin
from .extracting import ExtractingMixin
from .file import FileMixin
from .helpers import HelpersMixin
from .http_mixin import HttpMixin, response_note, response_of
from .json_mixin import JsonMixin
from .numeric import NumericMixin
from .outcome import MISSING, AssertionOutcome, Requirement
from .snapshot import SnapshotMixin
from .string import StringMixin
from .warning import WarningMixin

__version__ = "2.36.0"

# the tracked value type of the generic AssertionBuilder fallback (_U appears only in narrowing stubs)
_T = TypeVar("_T")
# the assertion type `not_` was reached from, so an inverted step hands the same narrowed type back
_E_co = TypeVar("_E_co", covariant=True)  # the element a pivot hands back
_S = TypeVar("_S")
if TYPE_CHECKING:
    _U = TypeVar("_U")
    _U2 = TypeVar("_U2")
    _U3 = TypeVar("_U3")
    _E = TypeVar("_E")  # element type of a collection, so first()/element()/... narrow to it
    _R = TypeVar("_R")  # result element type after a mapping pivot
    _K = TypeVar("_K")  # dict key type, so .value keeps dict[K, V]
    _V = TypeVar("_V")  # dict value type
    _P = TypeVar("_P")  # what a probe hands back, so a polling chain asserts on that and not on `object`

    class _Extension(Protocol):
        """A function attached as an extension, which the registry keys on its own name.

        The name is part of the contract rather than incidental: `add_extension` refuses a value whose
        `__name__` is not an identifier, and `remove_extension` reads it to find what to take off.
        """

        __name__: str

        def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

    class _ElementSource(Protocol[_E_co]):
        """Anything whose value is a collection of `_E_co`, however it was annotated.

        Structural because `AssertionBuilder` is invariant in `_T`: a builder over a `Sequence[int]`
        is not a builder over a `Collection[int]`, so the nominal self type bound for a mapping and
        missed every other container.
        """

        @property
        def value(self) -> Collection[_E_co]: ...


__tracebackhide__ = True  # clean tracebacks via py.test integration


_run_as_written: contextvars.ContextVar[bool] = contextvars.ContextVar("assertpy_run_as_written", default=False)
"""Whether the assertion being located was written inside a callable we are running.

`assert_all()` calls what it was given, so the outermost handover is its own call site and every failure
it collected was tagged with that one line.  A callable passed to it holds the assertions as written, so
theirs is the line to report.
"""


def _caller_location() -> tuple[str, int] | None:
    """The ``(filename, lineno)`` of the user frame that called into assertpy, skipping internal frames.

    Used to locate a warn-mode warning and each collected soft-assertion failure.

    The answer is the frame just outside the *outermost* assertpy frame, which is why the walk cannot
    stop at the first user frame it meets going inwards: a predicate passed to `satisfies()` or `each()`
    runs inside our own call, and the line worth reporting is the assertion in the test rather than the
    lambda we invoked.  Walking outwards and keeping the last handover does the same in one pass,
    without building a list of the whole stack.

    ``None`` where no such handover exists, so a caller that cannot be located logs without the prefix
    instead of crashing on unpacking.
    """
    frame: types.FrameType | None = sys._getframe(1)  # CPython accessor; the inspect equivalent is 10x slower here
    innermost = _run_as_written.get()
    location: tuple[str, int] | None = None
    inner_is_internal = False
    while frame:
        filename = frame.f_code.co_filename
        is_internal = filename in ASSERTPY_FILES
        if inner_is_internal and not is_internal:
            location = (filename, frame.f_lineno)
            if innermost:
                return location
        inner_is_internal = is_internal
        frame = frame.f_back
    return location


def _what_was_asked(builder: object, given: Requirement | None = None) -> Requirement | None:
    """What the failure being composed was asked for.

    A live extension call on this builder first, because it owns what runs under it the way
    `is_positive()` owns the `is_greater_than(0)` it asks.  That has to beat *given*, which is what the
    negated proxy and a dynamic ``has_`` assertion say about themselves: an extension delegating to
    either of those was reporting the delegate.

    The extension answers only for the builder it was called on.  An assertion it makes about some
    other value is that assertion's own, exactly as one inside a `satisfies()` predicate is.
    """
    asked = _asked_of.get()
    if asked is not None and asked.answers_for(builder):
        return _extension_requirement(asked)
    return given if given is not None else _requirement_of()


def _requirement_of() -> Requirement | None:
    """Which operation the failure being composed was asked for, read off the stack.

    The name and the arguments live at the assertion's entry and not at its failure: of the 164 places
    that reach `error()`, 144 are the public method itself and 20 are private helpers it calls.  So the
    answer is read here instead of passed down from each of them, which costs a built-in assertion
    nothing at all on the passing path and one microsecond on a failure that is already building a diff
    and a hint.  An extension is the exception and pays a wrapper on every call, because a frame cannot
    be tied back to a registration: `_ExtensionCall` says why.

    The *outermost* assertion still inside the package, for the same reason `_caller_location()` walks
    outwards: `is_positive()` asks `is_greater_than(0)` and `contains_key()` asks `contains()`, so the
    innermost frame answers the delegate rather than the assertion in the test.  A predicate passed to
    `satisfies()` is not our code, so the walk leaves the package there and an assertion inside the
    predicate still answers itself.  An extension is not read off the stack at all: it says what it is
    before its body runs, because a frame cannot be tied back to a registration.  Two instances of one
    callable class, and two functions from one decorator factory, share a code object.

    ``None`` where no operation was asked: `fail()`, and a bare `error()` with the caller's own message.
    """
    frame: types.FrameType | None = sys._getframe(3)  # skips this, `_what_was_asked` and `_compose`
    found: types.FrameType | None = None
    while frame is not None and frame.f_code.co_filename in ASSERTPY_FILES:
        if frame.f_code.co_name in _ASSERTS:
            found = frame
        frame = frame.f_back
    return None if found is None else Requirement(found.f_code.co_name, _bound_parameters(found))


def _bound_parameters(frame: types.FrameType, receivers: int = 1) -> dict[str, object]:
    """Every declared parameter of *frame* with the value it was bound to, minus the receiver.

    A frame cannot say whether an argument was omitted, passed positionally or passed by keyword, so
    what is read here is what the assertion ran with.  `Requirement.parameters` says why that is the
    more useful of the two.
    """
    code = frame.f_code
    local = frame.f_locals
    names = code.co_varnames
    taken = code.co_argcount + code.co_kwonlyargcount
    found: dict[str, object] = {name: local[name] for name in names[receivers:taken] if name in local}
    if code.co_flags & inspect.CO_VARARGS:
        found[names[taken]] = tuple(local.get(names[taken], ()))
        taken += 1
    if code.co_flags & inspect.CO_VARKEYWORDS:
        found[names[taken]] = dict(local.get(names[taken], {}))
    return found


@functools.cache
def _method_signature(own: Callable[..., object]) -> inspect.Signature:
    """The signature of an assertion as its caller writes it, without the receiver.

    Cached on the function rather than on the bound method, which is a new object per attribute access.
    `inspect.signature` costs 4.8 microseconds, three times what composing a negated failure costs
    without it, and the set of assertion functions is fixed at import.
    """
    found = inspect.signature(own)
    return found.replace(parameters=list(found.parameters.values())[1:])


def _signature_of(attr: Callable[..., object]) -> inspect.Signature | None:
    """As a caller writes it, for anything callable, or ``None`` where it cannot be read.

    Only a bound method is cached: a dynamic ``has_`` assertion and a registered extension are closures
    built per access, and holding them in a cache would grow it for the life of the process.
    """
    own = getattr(attr, "__func__", None)
    try:
        # only a function is cached: a callable object need not be hashable, and the key would refuse it
        return _method_signature(own) if isinstance(own, types.FunctionType) else inspect.signature(attr)
    except (TypeError, ValueError):
        return None


class _SoftBlock:
    """The failures one `soft_assertions()` block is collecting, and whether it is still collecting.

    ``active`` exists because a context variable is copied *by value* into a new task: a child created
    inside the block inherits the depth and the list, and the parent's exit is invisible to it.  The
    list is shared, so the flag rides along with it and the child can see that nobody is listening any
    more.  Without it, an assertion in a task that outlived the block appended to an orphaned list and
    the test passed having checked nothing.
    """

    __slots__ = ("active", "compared", "failures")

    def __init__(self) -> None:
        self.failures: list[AssertionOutcome] = []
        # by the identity of the record, which `failures` keeps alive, the pair its equality compared
        self.compared: dict[int, tuple[object, object]] = {}
        self.active = True

    def taken(self) -> tuple[list[AssertionOutcome], tuple[tuple[object, object] | None, ...]]:
        """What was collected, with the pair beside each, the block left empty for whatever comes next."""
        errs, compared = self.failures, self.compared
        self.failures, self.compared = [], {}
        return errs, tuple(compared.get(id(outcome)) for outcome in errs)


def _collecting() -> _SoftBlock | None:
    """The block currently collecting in this context, or ``None`` when assertions should raise."""
    if not _soft_ctx.get():
        return None
    block = _soft_err.get(None)
    return block if block is not None and block.active else None


_soft_ctx: contextvars.ContextVar[int] = contextvars.ContextVar("assertpy_soft_ctx", default=0)
# nothing about a soft failure is flattened until the aggregate message is rendered
_soft_err: contextvars.ContextVar[_SoftBlock | None] = contextvars.ContextVar("assertpy_soft_err", default=None)
_soft_group: contextvars.ContextVar[str | None] = contextvars.ContextVar("assertpy_soft_group", default=None)


class _Group:
    """The context `group()` hands back.

    A class rather than a `@contextlib.contextmanager` generator, and the same goes for the soft block
    itself.  A generator-based manager puts `contextlib.__exit__` on the stack, so a failure raised on
    the way out is reported against `contextlib.py` instead of the `with` line in the test.  The old
    cure was setting `__tracebackhide__` on the `contextlib` module, which fixed our two managers by
    changing how every third-party context manager in the process is reported.
    """

    __slots__ = ("_label", "_token")

    def __init__(self, label: str) -> None:
        self._label = label

    def __enter__(self) -> None:
        self._token = _soft_group.set(self._label)

    def __exit__(self, *_exc: object) -> None:
        _soft_group.reset(self._token)


class SoftAssertionCollector:
    """Collector returned by [`soft_assertions()`][assertpy.assertpy.soft_assertions] for grouping
    errors hierarchically."""

    def group(self, label: str) -> _Group:
        """Group subsequent assertion failures under *label*.

        Examples:
            Usage:

                with soft_assertions() as sa:
                    with sa.group("Headers"):
                        assert_that(headers).contains_key("Content-Type")
                    with sa.group("Body"):
                        assert_that(body["status"]).is_equal_to("ok")
        """
        return _Group(label)


def _located(location: tuple[str, int] | None, msg: str) -> str:
    """Append ``[file:line]`` so each collected soft failure can be jumped to, matching warn-mode."""
    if location is None:  # pragma: no cover - only None when a user file shadows assertpy (see _caller_location)
        return msg
    return f"{msg}  [{os.path.basename(location[0])}:{location[1]}]"


# half the block form's window, because the compact form puts both sides on one line
_SCANNABLE_WIDTH = 60


def _indented_diff(diff: object, indent: str) -> list[str]:
    """Render a collected failure's diff under its entry, or nothing when it carries none."""
    # one line per differing path: a soft run exists to show many of them at once
    lines = []
    entries = getattr(diff, "entries", None) or []
    # a mapping whose only differing key is spelled "." has a step, and used to be dropped here
    only = entries[0] if len(entries) == 1 else None
    if only is not None and not only.steps and only.path == ".":
        return lines
    if only is not None and only.steps == (Step("line", 1),):
        # past this width the change cannot be found by eye, so a window around it is drawn instead
        actual_text, expected_text = _safe_str(only.actual), _safe_str(only.expected)
        if len(actual_text) <= _SCANNABLE_WIDTH and len(expected_text) <= _SCANNABLE_WIDTH:
            return lines
        near_actual, near_expected = _windowed(actual_text, expected_text, _SCANNABLE_WIDTH)
        return [f"{indent}{only.path}: {near_actual} != {near_expected}"]
    shown = entries[:5]  # bound once: a slice and a separate threshold would drift apart
    for entry in shown:
        if entry.absent == "expected":  # an extra item, which has no counterpart to contrast with
            lines.append(f"{indent}{entry.path}: {_capped_repr(entry.actual)}")
        elif entry.absent == "actual":  # a missing one
            lines.append(f"{indent}{entry.path}: {_capped_repr(entry.expected)}")
        else:
            actual_side, expected_side = _diff_sides(entry.actual, entry.expected, 4000)
            lines.append(f"{indent}{entry.path}: {actual_side} != {expected_side}")
    if len(entries) > len(shown):
        lines.append(f"{indent}... and {len(entries) - len(shown)} more")
    return lines


class _Room:
    """What is left of the room for the blocks of collected failures: twenty failures drawn and 60 000 characters.

    One per message of a soft block where that message is the only place its diffs are read, and one per report
    under pytest, shared there by every block that failed in it.  A failure drawn and then too wide for what is left
    still takes one of the twenty: 200 wide failures each drawn and refused cost a report 0.49 s, against 0.05 s.
    """

    def __init__(self) -> None:
        self.failures = 20
        self.characters = 60_000


def _numbered(numbers: list[int]) -> str:
    """``[3, 21, 22, 23]`` as ``failures 3, 21 to 23``, and ``[3]`` as ``failure 3``: failures named by number."""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    spans = ", ".join(str(run[0]) if len(run) == 1 else f"{run[0]} to {run[-1]}" for run in runs)
    return f"failure {spans}" if len(numbers) == 1 else f"failures {spans}"


def _block_of(diff: object, indent: str, room: _Room) -> list[str] | None:
    """*diff* in block form under an entry, or ``None`` where it has none, the room is spent or it does not fit.

    A diff that cannot be drawn keeps the compact rows the summary has always printed, and a line saying why.
    """
    if diff is None or room.failures == 0:
        return None
    try:
        rendered = _render_diff(diff)
    except Exception as e:
        room.failures -= 1
        return [*_indented_diff(diff, indent), f"{indent}(no block: drawing it raised {type(e).__name__})"]
    if not rendered:
        return None
    room.failures -= 1
    block = [f"{indent}{line}" for line in rendered.splitlines()]
    size = sum(len(line) + 1 for line in block)
    if size > room.characters:
        return None
    room.characters -= size
    return block


def _format_soft_errors(errs: list[AssertionOutcome], *, blocks: bool = False, kept: bool = False) -> str:
    """The numbered summary a soft block raises, each entry located, with each failure's diff under it.

    The diff goes in compact rows, one per differing path, where the pytest plugin hangs each failure's block on
    the report anyway.  With *blocks*, for a message that is the only place a reader finds them, each diff goes in
    the block form a raised failure prints while a `_Room` lasts.  A block that does not fit keeps its compact rows
    and takes one of the twenty but none of the characters, so a smaller block after it still fits.  The last line
    names those failures, pointing at `failures` where *kept* says the summary is the message that carries them.
    """
    has_groups = any(outcome.group is not None for outcome in errs)
    lines = ["soft assertion failures:"]
    room = _Room() if blocks else None
    compact: list[int] = []
    current_group: str | None = None
    for counter, outcome in enumerate(errs, 1):
        indent = ""
        # one failure that cannot be drawn, its group's label included, costs its own entry and not the summary
        try:
            group = outcome.group
            indent = ("    " if group is not None else "  ") if has_groups else ""
            if has_groups and not _same_label(group, current_group):
                header = None if group is None else f"  [{group}]"
                current_group = group
                if header is not None:
                    lines.append(header)
            entry, squeezed = _entry_of(counter, outcome, indent, room)
        except Exception as e:
            entry, squeezed = [f"{indent}{counter}. (this failure could not be drawn: {type(e).__name__})"], False
        lines.extend(entry)
        if squeezed:
            compact.append(counter)
    if compact:
        pointer = " The diff of each is on `failures`." if kept else ""
        lines.append(f"Not drawn as a block for lack of room: {_numbered(compact)}.{pointer}")
    return "\n".join(lines)


def _same_label(label: object, other: object) -> bool:
    """Whether two group labels are one, a label whose ``==`` raises reading as another."""
    if label is other:
        return True
    try:
        return bool(label == other)
    except Exception:  # a label is anyone's object, and the entries after it still have to be drawn
        return False


def _entry_of(counter: int, outcome: AssertionOutcome, indent: str, room: _Room | None) -> tuple[list[str], bool]:
    """One entry of the summary, and whether its diff went in compact rows for lack of room."""
    # written flat, the location landed on the last line and the next entry read as a new section
    headline, *continuation = outcome.message.splitlines() or [""]
    lines = [f"{indent}{counter}. {_located(outcome.location, headline)}"]
    lines.extend(f"{indent}   {line}" for line in continuation)
    block = None if room is None else _block_of(outcome.diff, indent + "   ", room)
    if block is not None:
        return [*lines, *block], False
    lines.extend(_indented_diff(outcome.diff, indent + "   "))
    return lines, room is not None and bool(getattr(outcome.diff, "entries", None))


def _drawn(errs: list[AssertionOutcome], *, blocks: bool, kept: bool = False) -> str:
    """`_format_soft_errors`, or a line saying how many were collected where drawing them raised.

    The summary is a diagnostic: it must not take the place of the failure it describes, nor of an exception of the
    caller's that it is a note on.
    """
    try:
        return _format_soft_errors(errs, blocks=blocks, kept=kept)
    except Exception as e:
        return f"soft assertion failures: {len(errs)} collected, and drawing them raised {type(e).__name__}"


def _carry(
    exc: BaseException, collected: tuple[AssertionOutcome, ...], pairs: tuple[tuple[object, object] | None, ...]
) -> None:
    """Leave what a soft block collected on the exception that escaped it, where the pytest plugin reads it.

    Through the instance's own dictionary and past any ``__setattr__`` of its own, best-effort as the note is: the
    exception the caller raised is the one that has to come out of the block, whatever this manages.  Added to what
    an earlier block left, as its note is added to the notes, since one exception can escape two blocks in turn.
    """
    # an instance without a dictionary keeps the note, which carries the text
    with contextlib.suppress(Exception):
        vars(exc).setdefault("_assertpy_collected", []).append((collected, pairs))


def _attach_soft_note(exc: BaseException, rendered: str) -> None:
    """Put the collected failures on *exc* without ever becoming the reason the test failed.

    This is a diagnostic hung on somebody else's exception, so every step of it is best-effort.  Three
    things can go wrong and each of them used to matter more than the note:

    * `__notes__` may already be something other than a list.  CPython's own `add_note` refuses with
      `TypeError: Cannot add note: __notes__ is not a list`, and that error replaced the exception the
      user raised, leaving theirs in `__context__`.  Exactly backwards for a mechanism whose whole job
      is not losing information;
    * a user exception type can override `add_note` with something that raises, or with something that
      is not callable at all.  `BaseException.add_note` is called unbound to step around the override;
    * the attribute may not be writable, on a type with `__slots__` or a frozen instance.

    `add_note` also arrived in 3.11 and this package supports 3.10, which the first branch covers on the
    way past: there the unbound lookup raises `AttributeError` and the assignment takes over.
    """
    try:
        BaseException.add_note(exc, rendered)  # ty: ignore[missing-attribute]  # absent on 3.10
        return
    except Exception:  # every failure here falls through to the assignment below
        pass
    try:
        existing = getattr(exc, "__notes__", ())
        notes = [*existing, rendered] if isinstance(existing, (list, tuple)) else [rendered]
        exc.__notes__ = notes  # ty: ignore[missing-attribute]  # 3.10 lacks it until set
    except Exception:  # a note is worth nothing next to the exception it annotates
        pass


class _SoftAssertions:
    """The context `soft_assertions()` hands back.  See `_Group` for why this is a class."""

    __slots__ = ()

    def __enter__(self) -> SoftAssertionCollector:
        ctx = _soft_ctx.get()
        block = _soft_err.get(None)
        if ctx == 0 or block is None or not block.active:
            # a task outliving the block it inherited holds a closed one: collecting into it reaches nobody
            _soft_err.set(_SoftBlock())
            ctx = 0
        _soft_ctx.set(ctx + 1)
        return SoftAssertionCollector()

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, *_rest: object) -> None:
        _soft_ctx.set(_soft_ctx.get() - 1)
        if exc_type is not None:
            # the escaping error still wins, and what was collected before it travels as a note
            if exc is not None and (block := _soft_err.get(None)) is not None and _soft_ctx.get() == 0:
                block.active = False
                errs, pairs = block.taken()
                if errs:
                    _carry(exc, tuple(errs), pairs)
                    _attach_soft_note(exc, _drawn(errs, blocks=_errors._RENDER_DIFF_IN_MESSAGE))
            return
        block = _soft_err.get(None)
        errs: list[AssertionOutcome] = block.failures if block is not None else []
        pairs: tuple[tuple[object, object] | None, ...] = ()
        if _soft_ctx.get() == 0 and block is not None:
            # a task still running with this block in its own context copy stops collecting
            block.active = False
            errs, pairs = block.taken()
        if errs and _soft_ctx.get() == 0:
            # the same class as a single failure, so one `except AssertionFailure` covers both
            failure = AssertionFailure(_drawn(errs, blocks=False), failures=tuple(errs))
            failure._compared_pairs = pairs
            failure._soft_summary = functools.partial(_drawn, list(errs), blocks=True, kept=True)
            raise failure


def soft_assertions() -> _SoftAssertions:
    """Create a soft assertion context.

    Normally, any assertion failure will halt test execution immediately by raising an error.
    Soft assertions are way to collect assertion failures (and failure messages) together, to be
    raised all at once at the end, without halting your test.

    Uses `contextvars` internally, so each thread and each ``asyncio`` task gets its own
    soft-assertion state.  A task started inside an open block collects into that block while it is open.

    Examples:
        Create a soft assertion context, and some failing tests:

            from assertpy import assert_that, soft_assertions

            with soft_assertions():
                assert_that('foo').is_length(4)
                assert_that('foo').is_empty()
                assert_that('foo').is_false()
                assert_that('foo').is_digit()
                assert_that('123').is_alpha()

        When the context ends, any assertion failures are collected together and a single
        ``AssertionError`` is raised, each tagged with the ``file:line`` it came from:

            AssertionError: soft assertion failures:
            1. Expected <foo> to be of length <4>, but was <3>.  [test_str.py:10]
            2. Expected <foo> to be empty string, but was not.  [test_str.py:11]
            3. Expected <False>, but was not.  [test_str.py:12]
            4. Expected <foo> to contain only digits, but did not.  [test_str.py:13]
            5. Expected <123> to contain only alphabetic chars, but did not.  [test_str.py:14]

        Group errors by section:

            with soft_assertions() as sa:
                with sa.group("Headers"):
                    assert_that(headers["Content-Type"]).is_equal_to("application/json")
                with sa.group("Body"):
                    assert_that(body["status"]).is_equal_to("ok")

    Note:
        The soft assertion context only collects *assertion* failures, other errors such as
        ``TypeError`` or ``ValueError`` are always raised immediately.  Triggering an explicit test
        failure with [`fail()`][assertpy.assertpy.fail] will similarly halt execution immediately.
        If you need more forgiving behavior, use [`soft_fail()`][assertpy.assertpy.soft_fail] to add
        a failure message without halting test execution.
    """
    return _SoftAssertions()


def assert_all(*callables: Callable[[], object]) -> None:
    """Run all callables inside a soft assertion context.

    A convenience wrapper around [`soft_assertions()`][assertpy.assertpy.soft_assertions] for inline use.

    Examples:
        Usage:

            from assertpy import assert_all, assert_that

            assert_all(
                lambda: assert_that(x).is_positive(),
                lambda: assert_that(y).is_not_none(),
            )

    Raises:
        AssertionError: if any of the callables produce assertion failures
        TypeError: if a callable hands back a coroutine, which has asserted nothing
    """
    with soft_assertions():
        for call in callables:
            located = _run_as_written.set(True)
            try:
                verdict(call(), subject="the callable")
            finally:
                _run_as_written.reset(located)


def _build_with(open_blocks: int) -> None:
    """Point `_builder()` at `_scoped_builder` while a block is open anywhere, called under the count's lock.

    A global swapped here rather than a test in `_builder()`, which outside every block cost `assert_that()` 9%.
    """
    global _made_builder
    _made_builder = _scoped_builder if open_blocks else _ExtendedBuilder


def _scoped_builder(val, description="", kind=None, expected=None, logger=None):
    """A builder whose assertions are observed when it is made inside an entry of a block, a plain one otherwise.

    Asked of the context that makes it, so a builder made in a thread with no block of its own is plain whatever
    another thread has open, and one made before its block opened stays plain inside it.  An observed builder
    reports into the entry it was made in, and into no other once that one has closed.
    """
    entered = _passes.active_scope()
    if entered is None or _passes.logged_class is None:
        return _ExtendedBuilder(val, description, kind, expected, logger)
    made = _passes.logged_class(val, description, kind, expected, logger)
    made._reports_to = entered
    return made


class _LogPasses:
    """The context `log_passes()` hands back.  Each entry reports into a scope of its own, so it may be reentered."""

    __slots__ = ("_level", "_logger", "_on_pass")

    def __init__(self, logger: PassLogger, level: int, on_pass: Callable[[AssertionOutcome], object] | None) -> None:
        self._logger, self._level, self._on_pass = logger, level, on_pass

    def __enter__(self) -> None:
        _passes.open_block(_logged_builder_class, _build_with)
        _passes.scope.set(_passes.PassScope(self._logger, self._level, self._on_pass, _passes.scope.get()))

    def __exit__(self, *_exc: object) -> None:
        try:
            # the entry `__enter__` set in this context, which is the one a `with` statement exits in
            entered = cast("_passes.PassScope", _passes.scope.get())
            # a task outliving the entry reads it from its own context copy, and stops here
            entered.active = False
            _passes.scope.set(entered.previous)
        finally:
            _passes.close_block(_build_with)


def log_passes(
    logger: PassLogger | None = None,
    *,
    level: int = logging.INFO,
    on_pass: Callable[[AssertionOutcome], object] | None = None,
) -> contextlib.AbstractContextManager[None]:
    """Report every assertion that passes inside the block, with the value it held for.

    An assertion that holds says nothing by default.  Inside this block each one logs a line naming the call, the
    value and the file and line it was asked at, and, for a comparison against a bound, how far the value was from
    it.  Nothing else changes: a failure is raised, collected or logged exactly as it would be outside.

    One line per assertion the test asked.  What an assertion asks underneath (`is_positive()` asking
    `is_greater_than(0)`, an assertion inside a `satisfies()` predicate) is part of it and not reported again.  A
    soft or warn assertion that failed is not a pass, nor is one run under `check()`.  A poll reports the steps of
    the attempt that passed, once.

    Uses `contextvars`, so each thread and task has its own: a task started inside the block reports into it while
    the block is open.  A builder reports into the block it was made in, while that block is open: one made before
    it reports nothing, and one kept past its end reports nothing, in a later block too.  A pivot reports where the
    builder it came from reports.

    Args:
        logger: where the lines go, any object with ``isEnabledFor()`` and ``log()``.  Defaults to the
            ``assertpy.passes`` logger
        level: the level of each line.  Defaults to ``logging.INFO``
        on_pass: called with each pass's [`AssertionOutcome`][assertpy.outcome.AssertionOutcome] in place of
            logging it: ``passed`` set, the value, the requirement, the ``(file, line)`` and, as ``hint``, how far
            the value was from its bound.  Not together with ``logger``

    Examples:
        Log the passes of a block:

            from assertpy import assert_that, log_passes

            with log_passes():
                assert_that(latency).is_less_than(0.5)
                assert_that(status).is_equal_to(200)

        Each pass is one line at ``INFO`` on the ``assertpy.passes`` logger:

            [test_api.py:5]: is_less_than(0.5) passed for <0.42>, the value is about 0.08 below the number given
            [test_api.py:6]: is_equal_to(200) passed for <200>

        Under pytest a passing test shows its log only when asked, so turn on live logging, for one run with
        ``pytest -o log_cli=true --log-cli-level=INFO`` or for good in the configuration:

            [tool.pytest.ini_options]
            log_cli = true
            log_cli_level = "INFO"

    Raises:
        TypeError: if ``level`` is not an ``int``, ``logger`` has no ``isEnabledFor()`` or ``log()``, ``on_pass``
            is not callable, or both ``logger`` and ``on_pass`` are given
    """
    if on_pass is not None:
        if logger is not None:
            refuse(logger, "None when on_pass is given, which takes each pass in its place", subject=argument("logger"))
        if not callable(on_pass):
            refuse(on_pass, "callable", subject=argument("on_pass"))
    if logger is not None and not (
        callable(getattr(logger, "isEnabledFor", None)) and callable(getattr(logger, "log", None))
    ):
        refuse(logger, "a logger, with isEnabledFor() and log()", subject=argument("logger"))
    if type(level) is not int:
        refuse(level, "an int logging level", subject=argument("level"))
    return _LogPasses(logger if logger is not None else _passes.default_logger, level, on_pass)


@overload
def assert_that(val: str, description: str = "") -> _StringAssertion: ...


@overload
def assert_that(val: bool, description: str = "") -> _BoolAssertion: ...
@overload
def assert_that(val: int, description: str = "") -> _NumericAssertion[int]: ...


@overload
def assert_that(val: float, description: str = "") -> _NumericAssertion[float]: ...


@overload
def assert_that(val: complex, description: str = "") -> _ComplexAssertion: ...


@overload
def assert_that(val: dict[_K, _V], description: str = "") -> _DictAssertion[_K, _V]: ...


@overload
def assert_that(val: list[_E] | tuple[_E, ...], description: str = "") -> _IterableAssertion[_E]: ...


@overload
def assert_that(val: set[_E] | frozenset[_E], description: str = "") -> _IterableAssertion[_E]: ...


@overload
# a `datetime` is a `date` and is claimed first: one view for both offered chronology to a type that cannot answer
def assert_that(val: datetime.datetime, description: str = "") -> _DateTimeAssertion: ...


@overload
def assert_that(val: datetime.date, description: str = "") -> _DateAssertion: ...


@overload
def assert_that(val: pathlib.Path, description: str = "") -> _PathAssertion: ...


@overload
def assert_that(val: bytes, description: str = "") -> _BytesAssertion[bytes]: ...


@overload
def assert_that(val: bytearray, description: str = "") -> _BytesAssertion[bytearray]: ...


# a frame is assignable to every structural protocol, so it goes first; `tests/test_overload_order.py` holds that
@overload
def assert_that(val: _FrameT_co, description: str = "") -> _FrameAssertion[_FrameT_co]: ...


@overload
def assert_that(val: _ArrayT_co, description: str = "") -> _ArrayAssertion[_ArrayT_co]: ...


# the umbrella: below the frame pair so it cannot claim their values, above the fallback so a capability keeps all
@overload
def assert_that(val: _CapableT, description: str = "") -> _CapableAssertion[_CapableT]: ...


# below the umbrella: an ASGI or WSGI response is a callable, and this claimed one before its capability could
@overload
def assert_that(val: Callable[..., _P], description: str = "") -> _CallableAssertion[_P]: ...


# the fallback, at the price of an overload overlap mypy and pyright report and ty does not
@overload
def assert_that(val: _T, description: str = "") -> _ObjectAssertion[_T]: ...


# `Any` rather than the base protocol, which took pyright past its 4 GB heap; the overloads are what a caller sees
def assert_that(val: object, description="") -> Any:
    """Set the value to be tested, plus an optional description, and allow assertions to be called.

    This is a factory method for the `AssertionBuilder`, and the single most important
    method in all of assertpy.

    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description. Defaults to ``''``
            (aka empty string)

    Examples:
        Just import it once at the top of your test file, and away you go...

            from assertpy import assert_that

            def test_something():
                assert_that(1 + 2).is_equal_to(3)
                assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
                assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')
    """
    if _collecting() is not None:
        return _builder(val, description, "soft")
    return _builder(val, description)


def _contract_entries(exc: object, prefix: _Path = _ROOT) -> list[DiffEntry]:
    """Turn a pydantic ``ValidationError`` into diff rows, mirroring the OpenAPI path in `json_mixin`.

    ``errors()`` already carries the location, the message and the offending input, so the structured
    channel costs a reshape rather than a second walk of the payload.  Under ``each=True`` the caller
    passes the element's ``[i]`` prefix, the way ``contract_drift`` labels its own paths.

    ``loc`` is already a tuple of keys and indices, so the machine half of the path comes straight
    across rather than being parsed back out of the text.
    """
    errors = exc.errors() if hasattr(exc, "errors") else []  # ty: ignore[call-non-callable]  # duck-typed pydantic
    entries = []
    for error in errors:
        path = prefix
        for segment in error.get("loc", ()):
            path = path.index(segment) if isinstance(segment, int) else path.key(segment)
        entries.append(path.leaf_entry(actual=error.get("input"), expected=error.get("msg", "")))
    return entries


def _exact_failure(val: object, pairs: Any, carrier: str, sent: Any) -> tuple[str, str, DiffResult] | None:
    """What an exact check of *pairs* found, in the words a failure continues with, the payload as it then reads, and
    the same finds as a diff.  ``None`` when it found nothing.

    All are read while the payload is put back as it was *sent*, where validation changed it in place, and it is
    returned to what validation left before this returns, whatever the check does.
    """
    left = put_as_sent(val, sent) if sent is not None else None
    try:
        found = exactness_failure(pairs, carrier=carrier)
        if found is None:
            return None
        entries = kept_apart(found[1]) if left else found[1]
        return found[0], _truncated(_safe_str(val)), DiffResult(kind="match", entries=entries)
    finally:
        if left:
            put_back(left)


@overload
def assert_conforms(
    val: object, model: type[_U], description: str = ..., *, exact: bool = ..., each: Literal[False] = ...
) -> AssertionBuilder[_U]: ...
@overload
def assert_conforms(
    val: object, model: type[_U], description: str = ..., *, exact: bool = ..., each: Literal[True]
) -> AssertionBuilder[list[_U]]: ...
def assert_conforms(
    val: object, model: type[_U], description: str = "", *, exact: bool = False, each: bool = False
) -> AssertionBuilder[Any]:
    """Validate ``val`` against a pydantic v2 ``model`` and continue over the validated instance.

    The narrowing-complete companion to [`assert_that()`][assertpy.assertpy.assert_that] for
    contract testing.  Runs ``model.model_validate(val)``: on success the returned builder carries the
    validated, coerced instance (so ``.value`` and ``extracting`` see typed fields); on failure it
    fails with pydantic's validation errors.

    Because the return type is driven by ``model`` rather than by the type of ``val``, the chain
    narrows to ``model`` for **any** input - including the ``Any`` a decoded JSON payload carries.

    With ``exact=True`` it also asserts **contract drift**: the payload must not carry fields the model
    does not declare.  ``model_validate`` silently drops undeclared fields, so a stale model keeps
    passing after the live API grows new ones.

    ``exact`` catches that drift in the models, dataclasses and ``TypedDict`` values the payload became inside
    lists, tuples, sets, dicts, unions and root models, and reports the exact paths.  It is alias-aware, and
    respects a model that opts into extras (``extra="allow"``).  A key that spells a field and was not read,
    a name sent beside its alias, is dropped by pydantic like any other, and is named with where the field
    was read from.

    Raw items that no longer pair one by one with what they became are still checked where they can be:

    - A set, a filtered list, an object wrapped into a list: validated again by their model class when they
      all became one, which runs that class's validators once more for them.  JSON text is read as the
      original JSON input.
    - An emptied list, whose raw items a validator left no built item for: checked against the type their
      field declares.  They are validated again as it, which runs the item model's validators but not the
      field's own, so a field validator that would have built them otherwise is not seen.

    What still cannot be paired fails with ``<path> cannot be checked`` and the reason:

    - items of mixed classes in a set or a resized list
    - emptied items the declared type does not build, or declares through a union of two or more types
      besides ``None`` or a named type alias
    - merged dict keys
    - a generator consumed during validation, or a lazy ``Iterable``

    It reads the payload as it was sent: what a validator changed in place in a plain dict or list is put back
    for the check and returned afterwards.

    Three things it does not see:

    - a validator that renames keys, or reorders or rewrites the items of a container without changing its
      size: those items are read by position
    - a validator that puts back into a dict a key validation dropped: the dict holds it, so it reads as kept
    - a model inside a container of plain values (``list[Any]``)

    A ``TypedDict`` is read off the schema pydantic built, so text annotations and type variables declare it
    too.  Where several are declared for one value and their ``Literal`` fields do not tell them apart, or a
    type beside them may build a dict as well, a key the built dict lost fails with ``cannot be checked``.

    An ``exact`` failure carries its finds as a ``diff``: an entry per undeclared field, holding the value the
    payload sent there and the steps that lead to it, or one entry holding the part that cannot be checked
    against the reason.

    Args:
        val: the raw payload to validate (e.g. a decoded JSON response)
        model: a pydantic v2 model class (anything exposing ``model_validate``)
        description (str, optional): the extra error message description.  Defaults to ``''``
        exact (bool, optional): also fail if the payload carries fields ``model`` does not declare.
            Defaults to ``False``
        each (bool, optional): validate a *list* payload element-by-element against ``model`` (for list
            endpoints), narrowing the chain to ``list[model]``.  ``exact`` then applies per element.
            Defaults to ``False``

    Examples:
        Usage:

            from assertpy import assert_conforms, assert_that

            order = assert_conforms(response.json(), OrderModel).value  # .value: OrderModel
            assert_that(order.total).is_greater_than(0)

            # catch silent API growth: fail if the response grew fields the model does not declare
            assert_conforms(response.json(), OrderModel, exact=True)

            # a list endpoint: validate every item, narrowing to list[OrderModel]
            orders = assert_conforms(response.json(), OrderModel, each=True).value  # .value: list[OrderModel]

    Returns:
        AssertionBuilder: a builder over the validated model instance, statically typed as ``model``

    Raises:
        TypeError: if ``model`` is not a pydantic v2 model class
        AssertionError: if ``val`` does not validate against ``model``, or (with ``exact``) drifts from it or
            holds a part that cannot be paired with the model built from it
    """
    if not (isinstance(model, type) and hasattr(model, "model_validate")):
        raise TypeError("assert_conforms requires a pydantic v2 model class")
    kind = "soft" if _collecting() is not None else None
    builder = _builder(val, description, kind)
    if type(builder) is _passes.logged_class:
        asked: dict[str, object] = {"model": model, "description": description, "exact": exact, "each": each}
        written: dict[str, object] = {name: True for name in ("exact", "each") if asked[name]}
        return _observe(
            builder,
            lambda: _conforming(builder, val, model, description, exact=exact, each=each, kind=kind),
            lambda: ("assert_conforms", (model,), written, Requirement("assert_conforms", asked)),
        )
    return _conforming(builder, val, model, description, exact=exact, each=each, kind=kind)


def _conforming(
    builder: AssertionBuilder[Any],
    val: object,
    model: Any,
    description: str,
    *,
    exact: bool,
    each: bool,
    kind: str | None,
) -> AssertionBuilder[Any]:
    """The body of `assert_conforms()`, run beneath its frame, which is the one a failure reads its requirement off."""
    pydantic = sys.modules.get("pydantic")  # loaded already, since model exposes model_validate
    catchable: tuple[type[BaseException], ...] = (pydantic.ValidationError,) if pydantic is not None else ()
    # only a model with code of its own can change the payload it validates; what it is sent is kept for the check
    sent = sent_record(val) if exact and runs_own_code(model) else None
    if each:
        if not isinstance(val, (list, tuple)):
            raise TypeError("assert_conforms(each=True) requires a list or tuple payload")
        validated_items = []
        for index, item in enumerate(val):
            try:
                validated_items.append(model.model_validate(item))
            except catchable as exc:  # noqa: PERF203  # per-element catch reports which item failed; ~0 cost on 3.11+
                return builder.error(
                    f"Expected item [{index}] to conform to <{model.__name__}>, but it did not:\n{exc}",
                    actual=val,
                    expected=model,
                    diff=DiffResult(kind="match", entries=_contract_entries(exc, _ROOT.index(index))),
                    suppress_context=True,
                )
        if exact:
            items = enumerate(zip(val, validated_items, strict=True))
            found = _exact_failure(val, ((item, it, index) for index, (item, it) in items), "", sent)
            if found:
                return builder.error(
                    f"Expected every item to conform exactly to <{model.__name__}>, but {found[0]}",
                    actual=val,
                    expected=model,
                    diff=found[2],
                )
        return builder.builder(validated_items, description, kind)
    try:
        validated = model.model_validate(val)
    except catchable as exc:
        return builder.error(
            f"Expected <{_truncated(_safe_str(val))}> to conform to <{model.__name__}>, but it did not:\n{exc}",
            actual=val,
            expected=model,
            diff=DiffResult(kind="match", entries=_contract_entries(exc)),
            suppress_context=True,
        )
    if exact:
        found = _exact_failure(val, [(val, validated, None)], "it carries ", sent)
        if found:
            return builder.error(
                f"Expected <{found[1]}> to conform exactly to <{model.__name__}>, but {found[0]}",
                actual=val,
                expected=model,
                diff=found[2],
            )
    return builder.builder(validated, description, kind)


def assert_warn(
    val: object,
    description: str = "",
    logger: WarningLogger | None = None,
    *,
    on_failure: Callable[[AssertionOutcome], object] | None = None,
) -> Any:
    """Set the value to be tested, and optional description and logger, and allow assertions to be
    called, but never fail, only log warnings or hand each failure to ``on_failure``.

    This is a factory method for the `AssertionBuilder`, but unlike [`assert_that()`][assertpy.assertpy.assert_that] a
    failed assertion raises no `AssertionError` and does not halt execution.  Instead, any assertion failures
    results in a warning message being logged. Uses the given logger, or defaults to a simple logger that prints
    warnings to ``stdout``.  An exception the logger or an ``on_failure`` callable raises does come out of the
    assertion that failed, whatever its type.


    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description. Defaults to ``''``
            (aka empty string)
        logger (Logger, optional): the logger for warning message on assertion failure. Defaults to ``None``
            (aka use the default simple logger that prints warnings to ``stdout``)
        on_failure (Callable, optional): called with each failure's
            [`AssertionOutcome`][assertpy.outcome.AssertionOutcome] in place of logging it: the message, the
            values, the diff and the ``(file, line)`` it was asked at, for every link of the chain.  An exception
            it raises, an ``AssertionError`` included, comes out of the assertion that failed.  Not together with
            ``logger``.

    Examples:
        Usage:

            from assertpy import assert_warn

            assert_warn('foo').is_length(4)
            assert_warn('foo').is_empty()
            assert_warn('foo').is_false()
            assert_warn('foo').is_digit()
            assert_warn('123').is_alpha()

        Even though all of the above assertions fail, ``AssertionError`` is never raised and
        test execution is never halted.  Instead, the failed assertions merely log the following
        warning messages to ``stdout``, each after the time it was logged, which is left out here:

            WARNING [test.py:23]: Expected <foo> to be of length <4>, but was <3>.
            WARNING [test.py:24]: Expected <foo> to be empty string, but was not.
            WARNING [test.py:25]: Expected <False>, but was not.
            WARNING [test.py:26]: Expected <foo> to contain only digits, but did not.
            WARNING [test.py:27]: Expected <123> to contain only alphabetic chars, but did not.

    Tip:
        Use `assert_warn()` if and only if you have a *really* good reason to log assertion
        failures instead of failing.
    """
    if on_failure is not None:
        if logger is not None:
            refuse(
                logger,
                "None when on_failure is given, which takes each failure in its place",
                subject=argument("logger"),
            )
        if not callable(on_failure):
            refuse(on_failure, "callable", subject=argument("on_failure"))
        logger = _Subscribed(on_failure)
    return _builder(val, description, "warn", logger=logger)


def fail(msg: str = "") -> NoReturn:
    """Force immediate test failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Fail a test:

            from assertpy import assert_that, fail

            def test_fail():
                fail('forced fail!')

        If you wanted to test for a known failure, here is a useful pattern:

            import operator

            def test_adder_bad_arg():
                try:
                    operator.add(1, 'bad arg')
                    fail('should have raised error')
                except TypeError as e:
                    assert_that(str(e)).contains('unsupported operand')
    """
    # the same class as every other failure, so a handler does not have to name two of them
    raise AssertionFailure(f"Fail: {msg}!" if msg else "Fail!")


def soft_fail(msg: str = "") -> None:
    """Within a [`soft_assertions()`][assertpy.assertpy.soft_assertions] context, append the failure
    message to the soft error list, but do not halt test execution.

    Otherwise, outside the context, acts identical to [`fail()`][assertpy.assertpy.fail] and forces immediate test
    failure with the given message.

    Args:
        msg (str, optional): the failure message.  Defaults to ``''``

    Examples:
        Failing soft assertions:

            from assertpy import assert_that, soft_assertions, soft_fail

            with soft_assertions():
                assert_that(1).is_equal_to(2)
                soft_fail('my message')
                assert_that('foo').is_equal_to('bar')

        Fails, and outputs the following soft error list (each tagged with its ``file:line``):

            AssertionError: soft assertion failures:
            1. Expected <1> to be equal to <2>, but was not.  [test_add.py:10]
            2. Fail: my message!  [test_add.py:11]
            3. Expected <foo> to be equal to <bar>, but was not.  [test_add.py:12]

    """
    if (block := _collecting()) is not None:
        if _passes.open_blocks:
            _passes.mark_failed()
        block.failures.append(
            AssertionOutcome(
                message=f"Fail: {msg}!" if msg else "Fail!",
                group=_soft_group.get(),
                location=_caller_location(),
            )
        )
        return
    fail(msg)


_extensions = {}
# guards the check-then-set below against two threads adding the same name
_extensions_lock = threading.Lock()


# `not_` is answered inside `__getattr__` rather than declared, so it is named here
_POLLING_NAMES: Final = frozenset(
    name
    for builder in (AsyncAssertionBuilder, SyncAssertionBuilder)
    for name in vars(builder)
    if not name.startswith("_")
) | {"not_"}


def add_extension(func: _Extension, *, override: bool = False) -> None:
    """Add a new user-defined custom assertion to assertpy.

    Once the assertion is registered with assertpy, use it like any other assertion.  Pass val to
    [`assert_that()`][assertpy.assertpy.assert_that], and then call it.

    A name already in use is refused, so an extension that would quietly replace a built-in assertion
    or another extension says so instead.  Registering the same implementation again is not a clash:
    a module-scoped ``conftest`` fixture rebuilds its function on every module that requests it.

    Args:
        func (Callable): the assertion function (to be added)
        override: replace an assertion of the same name instead of refusing

    Raises:
        TypeError: if ``func`` is not callable
        ValueError: if its ``__name__`` is not an identifier, or the name is taken and ``override``
            is false

    Examples:
        Usage:

            from assertpy import add_extension

            def is_5(self):
                if self.val != 5:
                    return self.error(f'{self.val} is NOT 5!')
                return self

            add_extension(is_5)

            def test_5():
                assert_that(5).is_5()

            def test_6():
                assert_that(6).is_5()  # fails
                # 6 is NOT 5!
    """
    if not callable(func):
        refuse(func, "callable", subject=argument("func"))
    name = getattr(func, "__name__", None)
    if not isinstance(name, str) or not name.isidentifier():
        raise ValueError(f"the assertion's __name__ must be a valid Python identifier, got {name!r}")
    # nothing to override: after `eventually()` the name is out of reach, and `override=True` bought silence
    if name in _POLLING_NAMES or name.startswith(("_", "cr_", "gi_")):
        raise ValueError(
            f"{name!r} is how a polling chain spells one of its own, so an extension of that name "
            f"would be unreachable after eventually(); give it another name"
        )
    with _extensions_lock:
        # re-adding the same implementation is a no-op, not a clash.  Compared against what was
        # registered rather than against the wrapper naming it, whose code every extension shares
        same = is_same_implementation(_registered(vars(_ExtendedBuilder).get(name)), func) or is_same_implementation(
            _registered(_extensions.get(name)), func
        )
        if not override and not same:
            # an extension called `is_equal_to` used to replace the core assertion in silence
            if name in vars(_ExtendedBuilder) or name in _extensions:
                raise ValueError(
                    f"an assertion named {name!r} has already been added; pass override=True to "
                    f"replace it, or remove_extension() it first"
                )
            if hasattr(AssertionBuilder, name):
                raise ValueError(
                    f"{name!r} is already defined on the assertion builder; pass override=True to "
                    f"replace it deliberately, or give the extension another name"
                )
        named = _named_extension(name, func)
        # one implementation per name, so an override that changes shape clears the other half too: a
        # callable grafted onto the instance in `_builder()` shadows a function set on the class
        if isinstance(func, types.FunctionType):
            _extensions.pop(name, None)
            # the descriptor protocol binds once here, and the subclass keeps `AssertionBuilder` pristine on removal
            setattr(_ExtendedBuilder, name, named)
        else:
            if name in vars(_ExtendedBuilder):
                delattr(_ExtendedBuilder, name)
            _extensions[name] = named


def remove_extension(func: _Extension) -> None:
    """Remove a user-defined custom assertion.

    Args:
        func (Callable): the assertion function (to be removed)

    Examples:
        Usage:

            from assertpy import remove_extension

            remove_extension(is_5)
    """
    if not callable(func):
        refuse(func, "callable", subject=argument("func"))
    if func.__name__ in vars(_ExtendedBuilder):
        delattr(_ExtendedBuilder, func.__name__)
    _extensions.pop(func.__name__, None)
    # a signature cached against a function nobody can call any more
    _method_signature.cache_clear()


class _ExtensionCall:
    """One running call of one extension: what it was asked, on which builder, and whether it is still on.

    ``alive`` exists for the same reason `_SoftBlock.active` does.  A task created inside the call
    inherits the context variable by value and never sees the reset, so without it a failure raised
    after the call had returned was still reported under the extension's name.
    """

    __slots__ = ("alive", "args", "builder", "func", "kwargs", "name")

    def __init__(
        self,
        builder: object,
        name: str,
        func: Callable[..., object],
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> None:
        self.builder = builder
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.alive = True

    def answers_for(self, builder: object) -> bool:
        """Whether a failure on *builder* is this call's to name."""
        return self.alive and self.builder is builder


_asked_of: contextvars.ContextVar[_ExtensionCall | None] = contextvars.ContextVar("assertpy_asked_of", default=None)
"""The extension call now running, set before its body and read only if it fails.

An extension cannot be recognised from its frame.  Two instances of one callable class share
``__call__``'s code, two functions built by one decorator factory share the wrapper's, and a
`functools.partial` runs no Python frame of its own at all.  Naming it at the call is exact for every
shape, and it costs an extension call rather than every assertion.

Scoped to one builder, because the name belongs to a call and not to everything that runs during it.
An extension asserting about some other value has that assertion answer for itself, exactly as one
inside a `satisfies()` predicate does.  On the same builder the outer call keeps the name, which is
what a built-in does: `is_positive()` reports itself rather than the `is_greater_than()` it asks.
"""


def _registered(installed: object) -> object:
    """What was handed to `add_extension()`, behind the wrapper that names it."""
    return getattr(installed, "__wrapped__", installed)


def _named_extension(name: str, func: Callable[..., object]) -> Callable[..., object]:
    """*func*, saying what it was asked for the length of the call."""

    @functools.wraps(func)
    def named(self: object, *args: object, **kwargs: object) -> object:
        outer = _asked_of.get()
        if outer is not None and outer.answers_for(self):
            return func(self, *args, **kwargs)
        call = _ExtensionCall(self, name, func, args, kwargs)
        token = _asked_of.set(call)
        try:
            if _passes.open_blocks and type(self) is _passes.logged_class:
                return _observe_extension(cast("AssertionBuilder[Any]", self), func, args, kwargs, call)
            return func(self, *args, **kwargs)
        finally:
            call.alive = False
            _asked_of.reset(token)

    return named


def _observe_extension(
    builder: AssertionBuilder[Any],
    func: Callable[..., object],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    call: _ExtensionCall,
) -> object:
    """An extension's call, observed.  Apart from `named`: a closure there made its locals cells on every call."""
    return _observe(
        builder,
        lambda: func(builder, *args, **kwargs),
        lambda: (call.name, args, kwargs, _extension_requirement(call)),
    )


def _extension_requirement(asked: _ExtensionCall) -> Requirement:
    """What the running extension was asked, bound to its own parameter names where they can be read."""
    name, func, args, kwargs = asked.name, asked.func, asked.args, asked.kwargs
    found = _signature_of(func)
    if found is not None:
        # the receiver is the builder, which the caller did not write
        caller_writes = found.replace(parameters=list(found.parameters.values())[1:])
        with contextlib.suppress(TypeError):
            bound = caller_writes.bind(*args, **kwargs)
            bound.apply_defaults()
            return Requirement(name, dict(bound.arguments))
    # a signature nothing can read, or a call it disagrees with: the operands as the caller passed them
    return Requirement(name, {"args": args, "kwargs": kwargs})


def _call_text(name: str, args: tuple[object, ...], kwargs: Mapping[str, object]) -> str:
    """*name* called with *args* and *kwargs* as a call is written: ``key=value``, keywords in the caller's order."""
    rendered = ", ".join(
        [_capped_repr(arg) for arg in args] + [f"{key}={_capped_repr(value)}" for key, value in kwargs.items()]
    )
    return f"{name}({rendered})"


def _bound_requirement(
    attr: Callable[..., object],
    name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    *,
    negated: bool = False,
) -> Requirement:
    """What a call asked, bound to the parameter names of *attr*, as the positive path reads them off the frame."""
    found = _signature_of(attr)
    if found is None:
        # a builtin with no introspectable signature, or a call the assertion itself will refuse
        return Requirement(name, {"args": args, "kwargs": kwargs}, negated=negated)
    try:
        bound = found.bind(*args, **kwargs)
    except TypeError:
        return Requirement(name, {"args": args, "kwargs": kwargs}, negated=negated)
    bound.apply_defaults()
    return Requirement(name, dict(bound.arguments), negated=negated)


_Ran = TypeVar("_Ran")


def _observe(
    builder: AssertionBuilder[Any],
    run: Callable[[], _Ran],
    describe: Callable[[], tuple[str, tuple[object, ...], dict[str, object], Requirement]],
) -> _Ran:
    """Run one assertion of a builder a `log_passes()` block made, and report it if it held.

    Not reported: one asked inside another being observed, which is the outer one's to report, one run for its
    verdict (`check()`, and the run `not_` inverts), and one that delivered a failure without raising.
    *describe* is asked only for a pass that is reported.
    """
    if _passes.current_call() is not None:
        return run()
    found: _passes.PassScope | None = getattr(builder, "_reports_to", None)
    if found is None or not found.active:
        return run()
    # a verdict asked for is not reported, and neither is anything asked inside it
    asked_for_a_verdict = builder.kind == "check"
    call = _passes.Observed()
    token = _passes.observed.set(call)
    try:
        result = run()
        # still inside the call, so an assertion the logger or the callback makes is its, and reports nothing
        if not (asked_for_a_verdict or call.failed) and _passes.wants(found):
            _report_pass(found, builder, *describe())
    finally:
        call.alive = False
        _passes.observed.reset(token)
    return result


def _report_pass(
    found: _passes.PassScope,
    builder: AssertionBuilder[Any],
    name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    requirement: Requirement,
) -> None:
    """Hand one pass to the block: the record now, its line only if a logger is to print it."""
    location = _caller_location()
    val, description = builder.val, builder.description
    hint = _hints.passed_by(requirement.operation, val, requirement.parameters, negated=requirement.negated)
    outcome = AssertionOutcome(passed=True, actual=val, requirement=requirement, location=location, hint=hint)
    step = f"not_.{name}" if requirement.negated else name

    def line() -> str:
        where = f"[{os.path.basename(location[0])}:{location[1]}]: " if location is not None else ""
        desc = f"[{description}] " if description else ""
        margin = f", {hint}" if hint else ""
        text = f"{where}{desc}{_call_text(step, args, kwargs)} passed for <{_capped(val)}>{margin}"
        # one record, one line; and a lone surrogate cannot be encoded, which pytest-xdist does to captured logs
        text = text.replace("\r", "\\r").replace("\n", "\\n").encode("utf-8", "backslashreplace").decode("utf-8")
        return _errors._ends_kept(text)

    _passes.emit(found, outcome, line)


def _observing(name: str) -> Callable[..., object]:
    """The built-in assertion *name*, observed on a builder a `log_passes()` block made."""
    own = getattr(AssertionBuilder, name)

    @functools.wraps(own)
    def observed(self: AssertionBuilder[Any], *args: object, **kwargs: object) -> object:
        taken = vars(_ExtendedBuilder).get(name)
        if taken is not None:
            # an extension took the name over, and reports itself as one
            return taken(self, *args, **kwargs)
        return _observe(
            self,
            lambda: own(self, *args, **kwargs),
            lambda: (name, args, kwargs, _bound_requirement(types.MethodType(own, self), name, args, kwargs)),
        )

    return observed


def _observed_dynamic(self: AssertionBuilder[Any], name: str) -> object:
    """A dynamic ``has_`` assertion, observed as the built-ins are; anything else is refused as it always was."""
    found = DynamicMixin.__getattr__(self, name)

    # wrapped, so `not_` binds the operand to the name the assertion gives it
    @functools.wraps(found)
    def observed(*args: object, **kwargs: object) -> object:
        return _observe(
            self,
            lambda: found(*args, **kwargs),
            lambda: (name, args, kwargs, Requirement(name, _one_operand(args, kwargs))),
        )

    return observed


def _logged_builder_class() -> type[Any]:
    """The class a `log_passes()` block builds with: every operation of `_ASSERTS` observed, nothing else changed."""
    namespace: dict[str, object] = {name: _observing(name) for name in _ASSERTS if name != "assert_conforms"}
    namespace["__getattr__"] = _observed_dynamic
    namespace["_reports_to"] = None
    namespace["__doc__"] = "A builder made inside a `log_passes()` block, whose assertions report themselves."
    return type("_LoggedBuilder", (_ExtendedBuilder,), namespace)


def _builder(val, description="", kind=None, expected=None, logger=None):
    """Internal helper to build a new `AssertionBuilder` instance and glue on any extension methods.

    Function extensions already live on `_ExtendedBuilder`; only non-function callables (which the
    descriptor protocol cannot bind) still need per-instance grafting here.  Grafted in place rather than through
    `_grafted()`, whose call cost `assert_that()` 3%.
    """
    builder = _made_builder(val, description, kind, expected, logger)
    if _extensions:
        for name, func in _extensions.items():
            meth = types.MethodType(func, builder)
            setattr(builder, name, meth)
    return builder


def _grafted(builder):
    """*builder* with every non-function extension bound to it."""
    if _extensions:
        for name, func in _extensions.items():
            meth = types.MethodType(func, builder)
            setattr(builder, name, meth)
    return builder


def _builder_like(parent, val, description, kind, expected, logger):
    """A pivot of *parent* while a block is open: observed exactly when *parent* is, into the entry it reports to.

    A pivot made through `_builder()` asked the context that made it, so a builder made before its block took an
    observed pivot inside it, and one made in a closed entry handed its pivot to the entry open now.
    """
    observed = _passes.logged_class
    if observed is None or type(parent) is not observed:
        return _grafted(_ExtendedBuilder(val, description, kind, expected, logger))
    made = observed(val, description, kind, expected, logger)
    made._reports_to = parent._reports_to
    return _grafted(made)


class WarningLoggingAdapter(_LoggerAdapter):
    """Logging adapter to unwind the stack to get the correct callee filename and line number."""

    def process(self, msg: Any, kwargs: Any) -> tuple[Any, Any]:
        caller = _caller_location()
        if caller is None:
            return msg, kwargs
        filename, lineno = caller
        return f"[{os.path.basename(filename)}:{lineno}]: {msg}", kwargs


class _Subscribed:
    """The callback `assert_warn(on_failure=...)` hands each failure to, carried where the logger is carried.

    In the logger's place because every builder a chain goes on to is built with the logger the chain was given:
    a pivot, `extracting()` and a poll's own builder carry this too, and six pivots once dropped the logger.
    """

    __slots__ = ("callback",)

    def __init__(self, callback: Callable[[AssertionOutcome], object]) -> None:
        self.callback = callback

    def warning(self, msg: str) -> None:
        """What a code of anyone's that logs through the chain's logger reaches: a record carrying its message."""
        self.callback(AssertionOutcome(message=msg, location=_caller_location()))


_logger = logging.getLogger("assertpy")
_handler = logging.StreamHandler(sys.stdout)
_handler.setLevel(logging.WARNING)
_format = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_handler.setFormatter(_format)
_logger.addHandler(_handler)
_default_logger = WarningLoggingAdapter(_logger, None)


# what the register in `_engine/_operations.py` means for the proxy; `{name}` so the reader finds their call
_INSTEAD_OF_NEGATING: Final = {
    CONFIGURES: "negate the assertion that tests the expectation {name}() set instead",
    TRANSFORMS: "negate the assertion after {name}() instead",
    DESCRIBES: "call {name}() before not_ instead",
    POLLS: "assert the inverted condition instead",
}
_INSTEAD_OF_CHECKING: Final = {
    CONFIGURES: "ask check() for the verdict of the assertion that tests the expectation {name}() set",
    TRANSFORMS: "ask check() for the verdict of the assertion after {name}()",
    DESCRIBES: "call {name}() before check() instead",
    POLLS: "a poll delivers its own failure, so there is no verdict to hand back",
}


# the proxies themselves, reached the same way and not operations at all
_PROXY_ENTRIES: Final = {
    "check": "check() cannot be negated; call check().not_ before the assertion instead",
    "not_": "two negations cancel; drop both instead of writing not_.not_",
}


def _is_still_ours(target: object, name: str) -> bool:
    """Whether *name* on *target* is this library's own operation rather than an extension's.

    Asked of the object rather than of a global register, because the two ways an extension is applied
    have different lifetimes.  A plain function is set on `_ExtendedBuilder` and every instance sees it
    at once, but a non-function callable is grafted per instance at construction, so a builder made
    before the extension was registered keeps the built-in and one made before it was removed keeps the
    override.  Reading the registry instead let the first of those skip the refusal and then fail with
    `CollectionMixin.mapped() missing 1 required positional argument`.
    """
    return name not in vars(target) and name not in vars(_ExtendedBuilder)


def _refuse_without_a_verdict(target: object, name: str, proxy: str, remedies: dict[str, str]) -> None:
    """Raise for an operation reached through a proxy that has nothing to do with it.

    Both proxies exist to work on a verdict, so an operation that reaches none is a mistake in the
    call rather than something to invert or report.  Silently accepting one is worse than it sounds:
    `check()` answered `passed=True` for a pivot, which reads as an assertion that ran and held.
    """
    category = WITHOUT_A_VERDICT.get(name)
    # an extension over the name is somebody else's method, so the register's reason to refuse no longer applies
    if category is None or not _is_still_ours(target, name):
        return
    remedy = remedies[category].format(name=name)
    raise TypeError(f"{name}() {WHAT_IT_DOES[category]}, so it cannot be {proxy}; {remedy}")


class NegatedBuilder(Generic[_S]):
    """Proxy that inverts the next assertion. Created by ``assert_that(val).not_``.

    Generic over the assertion type it was reached from, so inverting a step returns the view the chain
    had before ``.not_``: ``assert_that("x").not_.starts_with("y")`` stays a string assertion rather
    than collapsing to the untyped builder and letting a numeric assertion follow it, and a negated
    narrowing narrows nothing.
    """

    if TYPE_CHECKING:
        # declared because a checker prefers it over `__getattr__`, which would type this as the negated method
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | ExceptionInfo | None
        logger: WarningLogger

    def __init__(self, builder: AssertionBuilder[Any]) -> None:
        self._builder = builder

    def __getattr__(self, name: str) -> Callable[..., _S]:
        _refuse_without_a_verdict(self._builder, name, "negated with not_", _INSTEAD_OF_NEGATING)
        # an extension over `check` or `not_` is somebody else's method, so it is not ours to refuse
        if name in _PROXY_ENTRIES and _is_still_ours(self._builder, name):
            raise TypeError(_PROXY_ENTRIES[name])
        attr = getattr(self._builder, name)
        if name in HANDS_THE_SUBJECT_BACK or not callable(attr):
            return attr

        def _negated(*args: object, **kwargs: object) -> AssertionBuilder:
            if self._builder.kind == "soft":
                return self._negated_soft(name, attr, *args, **kwargs)
            if self._builder.kind == "warn":
                return self._negated_warn(name, attr, *args, **kwargs)
            if self._builder.kind == "check":
                return self._negated_check(name, attr, *args, **kwargs)
            return self._negated_strict(name, attr, *args, **kwargs)

        if _passes.open_blocks and type(self._builder) is _passes.logged_class:
            # chosen here, so a negation outside every block pays no frame of its own
            def _observed(*args: object, **kwargs: object) -> Any:
                return _observe(
                    self._builder,
                    lambda: _negated(*args, **kwargs),
                    lambda: (name, args, kwargs, self._asked(attr, name, *args, **kwargs)),
                )

            return _observed

        # every branch hands back the wrapped builder, unsayable without `_builder: _S`, and an unbound TypeVar has none
        return _negated  # ty: ignore[invalid-return-type]  # see above

    def _make_msg(self, name: str, *args: object, **kwargs: object) -> str:
        """The negated failure, naming the call that held when it should not have.

        The arguments are in it because without them the message says which relation was asked for and
        not what it was asked about, which is the one thing the reader needs.

        Rendered here rather than by `HelpersMixin._fmt_args_kwargs()`, which spells a keyword as
        ``'key': value``: that is the shape `when_called_with()` has printed since assertpy and its
        messages are pinned to it, but this line reads as a call and ``key=value`` is what a call looks
        like.  Keyword order is the caller's, which Python preserves, so it is stable without sorting.
        """
        desc = f"[{self._builder.description}] " if self._builder.description else ""
        return f"{desc}Expected <{_capped(self._builder.val)}> to NOT satisfy: {_call_text(name, args, kwargs)}"

    def _asked(self, attr: Callable[..., object], name: str, *args: object, **kwargs: object) -> Requirement:
        """What the negated call asked for, bound to the underlying assertion's parameter names.

        Named here rather than read off the stack: a negated failure is composed after the assertion
        it inverted has already returned, so its frame is gone by then.  Bound through the signature
        so the parameters read the same as on the positive path, where they come out of the frame.
        """
        return _bound_requirement(attr, name, args, kwargs, negated=True)

    def _verdict(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionOutcome | None:
        """What the underlying assertion decided, or ``None`` when it held.

        Run in check mode, the one mode that hands a verdict back instead of delivering it.  That is
        what separates a verdict from an accident: anything still raised by the call came out of the
        value or out of an assertion nested inside it, and inverting *that* turns a break into a pass.

        Catching an exception class cannot make the distinction, whatever class is chosen.  A comparator
        that asserts with this library raises this library's own failure, and it is still not the
        verdict of the assertion being negated.  `_negated_check()` has always read the sink instead;
        the other three modes now do the same.

        A failure on something the question presupposes is not a verdict either, and inverting it turns
        "the question has no answer" into a pass.  When it is the run's first failure it is delivered
        before this returns, whatever failed after it, and handed back like any failure so no caller
        inverts it.  One after an ordinary failure was never reached by the strict run, which stops at
        the first, so the answer stands.  It keeps the positive assertion's message and values, takes the
        requirement every negated failure carries, and is recorded in turn for a negation this one runs
        inside of when it is that run's first failure too.

        Both records are read where `_verdict_holder()` keeps them, so a negation asked of a pivot inside
        an extension's own verdict run reads and restores that run's records rather than a stray copy.
        Only a run inside another one records what it passes on: at the top nobody reads it afterwards.
        """
        builder = self._builder
        holder = builder if builder._answers_to is None else builder._answers_to
        kind, answering = builder.kind, builder._answering_another
        sink, enclosing = holder._check_sink, holder._unmet_prerequisite
        builder.kind = "check"
        builder._answering_another = True
        holder._check_sink = None
        holder._unmet_prerequisite = None
        try:
            attr(*args, **kwargs)
            decided, unmet = holder._check_sink, holder._unmet_prerequisite
        finally:
            builder.kind, builder._answering_another = kind, answering
            holder._check_sink, holder._unmet_prerequisite = sink, enclosing
            if kind != "check" and holder._run_pivots is not None:
                holder._release_pivots()
        if unmet is None:
            return decided
        passed_on = replace(unmet, requirement=_what_was_asked(builder, self._asked(attr, name, *args, **kwargs)))
        if kind == "check" and sink is None:
            holder._unmet_prerequisite = passed_on
        failure = builder._deliver(passed_on)
        if failure is not None:
            raise failure
        return passed_on

    def _negated_strict(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(name, attr, *args, **kwargs) is not None:
            return self._builder
        # composed here rather than by `error()`, which would prefix the description twice
        raise AssertionBuilder._failure(
            AssertionOutcome(
                message=self._make_msg(name, *args, **kwargs),
                actual=self._builder.val,
                requirement=_what_was_asked(self._builder, self._asked(attr, name, *args, **kwargs)),
            )
        )

    def _negated_soft(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(name, attr, *args, **kwargs) is not None:
            return self._builder
        msg = self._make_msg(name, *args, **kwargs)
        outcome = AssertionOutcome(
            message=msg,
            actual=self._builder.val,
            group=_soft_group.get(),
            location=_caller_location(),
            requirement=_what_was_asked(self._builder, self._asked(attr, name, *args, **kwargs)),
        )
        block = _collecting()
        if block is None:
            # the block has closed, which an outliving task does: appending puts the failure in a list nobody reads
            raise self._builder._failure(outcome)
        if self._builder._value_taint_reason is None:
            self._builder._value_taint_reason = msg
        if _passes.open_blocks:
            _passes.mark_failed()
        block.failures.append(outcome)
        return self._builder

    def _negated_check(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(name, attr, *args, **kwargs) is not None:
            return self._builder
        holder = self._builder._verdict_holder()
        if holder._check_sink is None:
            holder._check_sink = AssertionOutcome(
                message=self._make_msg(name, *args, **kwargs),
                actual=self._builder.val,
                requirement=_what_was_asked(self._builder, self._asked(attr, name, *args, **kwargs)),
            )
        return self._builder

    def _negated_warn(
        self, name: str, attr: Callable[..., object], *args: object, **kwargs: object
    ) -> AssertionBuilder:
        if self._verdict(name, attr, *args, **kwargs) is not None:
            return self._builder
        self._builder._warned(
            AssertionOutcome(
                message=self._make_msg(name, *args, **kwargs),
                actual=self._builder.val,
                requirement=_what_was_asked(self._builder, self._asked(attr, name, *args, **kwargs)),
            )
        )
        return self._builder


class CheckBuilder:
    """Proxy returned by [`check()`][assertpy.assertpy.AssertionBuilder.check].

    Runs one assertion with the builder in verdict mode and hands back what it decided.  The mode is
    put on and taken off around the call rather than held, so a builder that is also used normally
    afterwards is unaffected, and an assertion that raises for a bad argument still leaves it clean.

    ``not_`` is proxied rather than refused, so a negated assertion can be asked for a verdict too.
    The value is handed straight back under ``val`` and ``value``, callable or not, and so is anything
    else that is not callable, ``description`` among them.
    """

    if TYPE_CHECKING:
        # declared because a checker prefers it over `__getattr__`, which types every name as a verdict call
        val: Any
        description: str

        @property
        def not_(self) -> CheckBuilder: ...

    def __init__(self, target: object, builder: AssertionBuilder[Any]) -> None:
        # two references: `not_` moves the target to the negation proxy while the mode stays underneath
        self._target = target
        self._builder = builder

    def __getattr__(self, name: str) -> Callable[..., AssertionOutcome]:
        _refuse_without_a_verdict(self._builder, name, "asked for a verdict", _INSTEAD_OF_CHECKING)
        if name == "check" and _is_still_ours(self._builder, name):
            raise TypeError("check() is already the verdict proxy; one check() is enough")
        attr = getattr(self._target, name)
        if name in HANDS_THE_SUBJECT_BACK:
            return attr
        if isinstance(attr, NegatedBuilder):
            # ty: ignore[invalid-return-type]  # declared above as a proxy; this is the path that cannot be described
            return CheckBuilder(attr, self._builder)
        if not callable(attr):
            return attr

        def _checked(*args: object, **kwargs: object) -> AssertionOutcome:
            # the verdict is answered here, so one this runs inside keeps its own failure and prerequisite
            builder = self._builder
            holder = builder if builder._answers_to is None else builder._answers_to
            kind, sink, unmet = builder.kind, holder._check_sink, holder._unmet_prerequisite
            builder.kind = "check"
            holder._check_sink = None
            try:
                attr(*args, **kwargs)
                failure = holder._check_sink
            finally:
                builder.kind, holder._check_sink, holder._unmet_prerequisite = kind, sink, unmet
                if kind != "check" and holder._run_pivots is not None:
                    holder._release_pivots()
            if failure is not None:
                return failure
            return AssertionOutcome(passed=True, actual=builder.val)

        return _checked


class AssertionBuilder(
    StringMixin,
    SnapshotMixin,
    NumericMixin,
    JsonMixin,
    HttpMixin,
    HelpersMixin,
    FileMixin,
    ExtractingMixin,
    ExceptionMixin,
    WarningMixin,
    DynamicMixin,
    DictMixin,
    DateMixin,
    ContainsMixin,
    CollectionMixin,
    BytesMixin,
    DataFrameMixin,
    BaseMixin,
    Generic[_T],
):
    """The main assertion class.  Never call the constructor directly, always use the
    [`assert_that()`][assertpy.assertpy.assert_that] helper instead.  Or if you just want warning messages, use the
    `assert_warn()` helper.

    Args:
        val: the value to be tested (aka the actual value)
        description (str, optional): the extra error message description.  Defaults to ``''``
            (aka empty string)
        kind (str, optional): the kind of assertions, one of ``None``, ``soft``, or ``warn``.
            Defaults to ``None``
        expected (Error, optional): the expected exception.  Defaults to ``None``
        logger (Logger, optional): the logger for warning messages.  Defaults to ``None``
    """

    def __init__(
        self,
        val: Any,
        description: str = "",
        kind: str | None = None,
        expected: type[BaseException] | ExceptionInfo | None = None,
        logger: WarningLogger | None = None,
    ) -> None:
        """Never call this constructor directly."""
        self.val = val
        self.description = description
        self.kind = kind
        self.expected = expected
        self.logger: WarningLogger = logger or _default_logger
        self._not_expected = False
        self._expected_warning = None
        self._return_value = _UNSET
        self._raised_exception = _UNSET
        # `.value` refuses an unverified value and names the root cause rather than breaking its type in silence
        self._value_taint_reason: str | None = None
        self._value_origin: str | None = None
        # where a failure lands while `check()` has this builder in verdict mode
        self._check_sink: AssertionOutcome | None = None

    @property
    def not_(self) -> NegatedBuilder[Self]:
        """Invert the next assertion in the chain."""
        return NegatedBuilder(self)

    def check(self) -> _CheckAnyValue[_T]:
        """Run the next assertion for its verdict instead of for its failure.

        The assertion does not raise, collect or log.  It returns an
        [`AssertionOutcome`][assertpy.outcome.AssertionOutcome], truthy when it held and carrying the
        failure message, values and diff when it did not.

        For asking a question about a value.  An assertion states a requirement, and a test that stops
        at the first unmet one is the point; this is for the cases that are not that, like branching on
        a precondition, or reporting a check into a system that is not pytest.

        A bad argument still raises.  ``TypeError`` and ``ValueError`` mean the call itself is wrong,
        which is not a verdict about the value and would be silenced by returning one.

        An assertion or an extension that fails more than once answers with its first failure, the one
        it raises outside ``check()``.

        Examples:
            Usage:

                outcome = assert_that(response).check().is_equal_to(expected)
                if not outcome:
                    logger.warning(outcome.message)

                assert_that(5).check().is_positive().passed        # True
                assert_that(5).check().not_.is_positive().passed   # False
        """
        # the proxy resolves every name through `__getattr__`: the twin is the shape, `CheckBuilder` is the thing
        return cast("_CheckAnyValue[_T]", CheckBuilder(self, self))

    @property
    def value(self) -> _T:
        """The value under test, returned as-is for typed extract-and-continue.

        Ends a chain by handing the checked value back, so a test can keep using it after the
        assertions passed.  For object- and union-typed values the static type is refined by the
        narrowing assertions along the way:
        [`is_not_none()`][assertpy.base.BaseMixin.is_not_none] removes ``None`` and
        [`is_instance_of()`][assertpy.base.BaseMixin.is_instance_of] narrows to the checked class, so
        no ``cast()`` or bare ``assert`` is needed to satisfy a type checker.

        ``value`` is a strict-mode extraction: it hands the value back only when *every* assertion on
        it passed.  If one failed under
        [`soft_assertions()`][assertpy.assertpy.soft_assertions] or
        [`assert_warn()`][assertpy.assertpy.assert_warn] - where failures are collected, not raised -
        reading ``value`` raises ``TypeError`` instead of returning an unverified value.  Read it in
        strict mode, or after the soft block has closed.

        The taint is per-value, not per-chain.  A value-changing pivot
        ([`extracting()`][assertpy.extracting.ExtractingMixin.extracting],
        [`first()`][assertpy.collection.CollectionMixin.first],
        [`decoded_as()`][assertpy.bytes_mixin.BytesMixin.decoded_as], ...) starts a *new* value with a
        fresh guard and validates its own input, so a pivot never reaches ``.value`` with a value
        derived from a failed assertion - it raises in the pivot first.

        Examples:
            Usage:

                order: Order | None = repo.find_order(42)
                paid = assert_that(order).is_not_none().is_instance_of(PaidOrder).value
                paid.refund()  # statically typed as PaidOrder

        Returns:
            object: the original value under test (never a copy)

        Raises:
            TypeError: if an assertion on this chain failed under ``soft_assertions()`` or
                ``assert_warn()``, so the value cannot be trusted to match its narrowed type; the
                message carries the underlying (root) failure so its cause is not lost
        """
        if self._value_taint_reason is not None:
            raise TypeError(
                "cannot extract .value: the underlying assertion failed under soft or warn mode - "
                f"{self._value_taint_reason} (read .value in strict mode, or after the soft-assertions block)"
            )
        return self.val

    if TYPE_CHECKING:
        # narrowing declarations for checkers only; the runtime behaviour lives in `BaseMixin`

        @overload
        def is_not_none(self: AssertionBuilder[_U | None]) -> AssertionBuilder[_U]: ...
        @overload
        def is_not_none(self) -> Self: ...
        def is_not_none(self) -> Any: ...

        # the second rung takes a tuple, and a union under checkers reading it as `UnionType`; it also keeps conformance
        @overload
        def is_instance_of(self, some_class: tuple[type[_U], type[_U2]]) -> AssertionBuilder[_U | _U2]: ...
        @overload
        def is_instance_of(
            self, some_class: tuple[type[_U], type[_U2], type[_U3]]
        ) -> AssertionBuilder[_U | _U2 | _U3]: ...
        @overload
        def is_instance_of(self, some_class: type[_U]) -> AssertionBuilder[_U]: ...
        @overload
        def is_instance_of(self, some_class: ClassInfo) -> Self: ...
        def is_instance_of(self, some_class: Any) -> Any: ...

        @overload
        def is_instance_of_any(self, first: type[_U], second: type[_U2], /) -> AssertionBuilder[_U | _U2]: ...
        @overload
        def is_instance_of_any(
            self, first: type[_U], second: type[_U2], third: type[_U3], /
        ) -> AssertionBuilder[_U | _U2 | _U3]: ...
        @overload
        def is_instance_of_any(self, *some_classes: ClassInfo) -> Self: ...
        def is_instance_of_any(self, *some_classes: Any) -> Any: ...

        # the pivots return `self.builder(<element>)` where `CollectionMixin` says `-> Self`; `_T` is invariant
        @overload
        def first(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def first(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def first(self) -> Self: ...
        def first(self) -> Any: ...

        @overload
        def last(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def last(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def last(self) -> Self: ...
        def last(self) -> Any: ...

        @overload
        def element(self: AssertionBuilder[Mapping[_K, _V]], index: SupportsIndex) -> AssertionBuilder[_K]: ...
        @overload
        def element(self: _ElementSource[_E], index: SupportsIndex) -> AssertionBuilder[_E]: ...
        @overload
        def element(self, index: SupportsIndex) -> Self: ...
        def element(self, index: SupportsIndex) -> Any: ...

        # `mapped()` builds a `list` whatever it was given, so `-> Self` was wrong about the container too and
        # refused working code.  Its boundary: a named function binds `_R` under both checkers, a lambda binds it
        # under ty and comes back `Any` under mypy, losing precision rather than rejecting.  `filtered_on()` and
        # `flat_mapped()` stay undeclared, measured: against `Matcher[_E] | Callable[[_E], object]` a lambda binds
        # nothing, so `filtered_on()` was `Unknown` under ty and `flat_mapped()` resolved there, and both stayed
        # `Any` under mypy.  One answer out of three checkers is the bar and neither reaches it
        @overload
        def mapped(self: _ElementSource[_E], func: Callable[[_E], _R]) -> AssertionBuilder[list[_R]]: ...
        @overload
        def mapped(self, func: Callable[..., Any]) -> Self: ...
        def mapped(self, func: Any) -> Any:  # overload impl stub, never executed
            ...

        @overload
        def single(self: AssertionBuilder[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def single(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def single(self) -> Self: ...
        def single(self) -> Any:  # overload impl stub, never executed
            ...

        # a `TypeIs` predicate narrows the chain; PyCharm does not solve TypeVars through it yet (PY-89124)
        @overload
        def satisfies(self, matcher: Callable[[Any], TypeIs[_U]]) -> AssertionBuilder[_U]: ...
        @overload
        def satisfies(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self: ...
        def satisfies(self, matcher: Any) -> Any:  # overload impl stub, never executed
            ...

    def builder(
        self,
        val: Any,
        description: str = "",
        kind: str | None = None,
        expected: type[BaseException] | ExceptionInfo | None = None,
        logger: WarningLogger | None = None,
        origin: str | None = None,
    ) -> Any:
        """Helper to build a new `AssertionBuilder` instance. Use this only if not chaining to ``self``.

        Args:
            val: the value to be tested (aka the actual value)
            description (str, optional): the extra error message description.  Defaults to ``''``
                (aka empty string)
            kind (str, optional): the failure mode of the assertions, one of ``None`` (raise),
                ``soft`` (collect), or ``warn`` (log).  Defaults to ``None``.  Unrelated to
                [`DiffResult.kind`][assertpy.errors.DiffResult], which is a diff category
            expected (Error, optional): the expected exception.  Defaults to ``None``
            logger (Logger, optional): the logger for warning messages.  Defaults to ``None``
        """
        pivoted = _builder_like(self, val, description, kind, expected, logger) if _passes.open_blocks else None
        if pivoted is None:
            pivoted = _builder(val, description, kind, expected, logger)
        pivoted._value_origin = origin
        if kind == "check":
            holder = self._verdict_holder()
            pivoted._answers_to = holder
            pivoted._answering_another = self._answering_another
            if holder._run_pivots is None:
                holder._run_pivots = []
            holder._run_pivots.append(pivoted)
        # kept across the pivot, and `is not None` not `or`, since a `requests.Response` is falsey for every 4xx
        pivoted._response = self._response if self._response is not None else response_of(self.val)
        return pivoted

    def error(
        self,
        msg: str,
        *,
        actual: Any = MISSING,
        expected: Any = MISSING,
        diff: DiffResult | None = None,
        trace: PollTrace | None = None,
        requirement: Requirement | None = None,
        suppress_context: bool = False,
    ) -> Self:
        """Helper to raise an ``AssertionError`` with the given message.

        If an error description is set by [`described_as()`][assertpy.base.BaseMixin.described_as], then that
        description is prepended to the error message.

        Always raises [`AssertionFailure`][assertpy.errors.AssertionFailure], which is an
        ``AssertionError``.  Structured data (``actual``, ``expected``, ``diff``) is carried on it when
        given, and the class is the same either way, which is why nothing reads the class to learn who
        raised it: `NegatedBuilder._verdict()` asks in check mode instead.

        Args:
            msg: the error message
            actual: the actual value (for structured error reporting)
            expected: the expected value (for structured error reporting)
            diff: a [`DiffResult`][assertpy.errors.DiffResult] instance (for structured error reporting)
            trace: a [`PollTrace`][assertpy.errors.PollTrace] from a poll that timed out
            requirement: what was asked, for a caller the stack cannot be read from.  A negated
                assertion, a poll that timed out and a dynamic ``has_`` assertion each compose their
                failure after or beside the frame that named the operation, so they say it here.
            suppress_context: raise ``from None``, dropping the exception currently being handled from
                the traceback.  Pass it when the caught exception is your own plumbing and its text is
                already folded into ``msg``, so the reader is not shown the same failure twice.  Leave
                it alone when the caught exception is the caller's, which is context they want.

        Raises:
            AssertionFailure: unless ``kind`` is ``warn``, ``soft`` or ``check``, which log it, collect
                it and record it respectively.

        Returns:
            AssertionBuilder: this instance, to chain the next assertion, whenever the failure was
                delivered some other way than by raising.
        """
        # taken ahead of anything that can raise, so a pair never outlives the failure it was set for
        compared, self._compared = self._compared, None
        failure = self._deliver(
            self._compose(msg, actual=actual, expected=expected, diff=diff, trace=trace, requirement=requirement),
            compared,
        )
        if failure is None:
            return self
        failure._compared = compared
        # the raise stays here: a failure's traceback ends at `error`, three frames deep, pinned in test_traceback.py
        if suppress_context:
            raise failure from None
        raise failure

    def _unmet(
        self,
        msg: str,
        *,
        expected: Any = MISSING,
        requirement: Requirement | None = None,
        suppress_context: bool = False,
    ) -> None:
        """Deliver *msg* as a failure of something the question presupposes rather than as its answer.

        Delivered like any failure, with the keywords `error()` takes.  What differs is under `not_`, whose
        verdict run is in check mode: recorded when it is the run's first failure, it is what
        `NegatedBuilder._verdict()` delivers as it stands.
        """
        holder = self._verdict_holder()
        first = holder._check_sink is None
        self.error(msg, expected=expected, requirement=requirement, suppress_context=suppress_context)
        if first:
            holder._unmet_prerequisite = holder._check_sink

    def _verdict_holder(self) -> AssertionBuilder[Any]:
        """The builder whose check-mode sink this one's failures land in: itself, unless it was pivoted to
        during another builder's verdict run, whose failures they then are."""
        return self if self._answers_to is None else self._answers_to

    def _release_pivots(self) -> None:
        """Hand the pivots made during the verdict run that just ended the mode this builder is back in.

        Kept in check mode, a pivot an extension held on to after the run swallowed every later failure.
        Called by the outermost run only, since a run inside another still belongs to that one.
        """
        made, self._run_pivots = self._run_pivots, None
        for pivot in made or ():
            pivot.kind, pivot._answers_to, pivot._answering_another = self.kind, None, self._answering_another

    def _compose(
        self,
        msg: str,
        *,
        actual: object,
        expected: object,
        diff: DiffResult | None,
        trace: PollTrace | None,
        requirement: Requirement | None = None,
    ) -> AssertionOutcome:
        """Build the failure record.  Decides nothing about what happens to it."""
        # filled here rather than per call site, which is what puts it on all 163 failures instead of 34
        provided = actual is not MISSING
        out = f"{f'[{self.description}] ' if len(self.description) > 0 else ''}{msg}"
        if self._value_origin and not len(self.val):
            # an empty derived value carries no context of its own, so name the step that produced it
            out = f"{out} The value is empty because {self._value_origin}."
        hint = _hints.diagnose(
            diff, actual, expected, identity=self._equality_comparison, comparators=self._comparators_took_part
        )
        # a message quoting a failure that already carries the hint printed it twice, the poll timeout among them
        if hint is not None and hint not in out:
            # on its own line, so the original message stays a prefix and a `match=` written against it keeps working
            out = f"{out}\n{hint}"
        places = _hints.placed(diff)
        if places is not None and places not in out:
            out = f"{out}\n{places}"
        response = self._response if self._response is not None else response_of(self.val)
        note = response_note(response) if response is not None else None
        if note is not None:
            # last, under the explanation: it says where the value came from, not why it differs
            out = f"{out}\n{note}"
        return AssertionOutcome(
            message=out,
            actual=actual if provided else self.val,
            actual_provided=provided,
            expected=expected,
            diff=diff,
            trace=trace,
            hint=hint,
            requirement=_what_was_asked(self, requirement),
        )

    def _deliver(
        self, outcome: AssertionOutcome, compared: tuple[object, object] | None = None
    ) -> AssertionFailure | None:
        """Act on a composed failure according to the builder's mode.

        Returns the exception the caller should raise, or ``None`` when the failure was collected or
        logged instead.  Raising is left to `error()` so the traceback keeps its shape.  *compared* is the pair
        an equality held against each other, kept on a failure a soft block collects as a raised one keeps it.
        """
        if self.kind == "warn":
            self._warned(outcome)
            return None
        if self.kind == "soft":
            block = _collecting()
            if block is None:
                # the block has closed, which an outliving task does: appending puts the failure in a list nobody reads
                return self._failure(outcome)
            if self._value_taint_reason is None:
                self._value_taint_reason = outcome.message
            collected = replace(outcome, group=_soft_group.get(), location=_caller_location())
            if compared is not None:
                block.compared[id(collected)] = compared
            if _passes.open_blocks:
                _passes.mark_failed()
            block.failures.append(collected)
            return None
        if self.kind == "check":
            # no taint, as a verdict was asked for and not asserted, and the first failure is it: strict stops there
            holder = self._verdict_holder()
            if holder._check_sink is None:
                holder._check_sink = outcome
            return None
        return self._failure(outcome)

    def _warned(self, outcome: AssertionOutcome) -> None:
        """Hand a warn-mode failure on: as its record to an `on_failure` callback, or as text to the logger.

        The value is marked as unverified first, and the record is located first, so a callback that raises leaves
        both as a logger that raises does.  Every warn-mode failure comes through here, negations included.
        """
        if self._value_taint_reason is None:
            self._value_taint_reason = outcome.message
        if _passes.open_blocks:
            _passes.mark_failed()
        logger = self.logger
        if isinstance(logger, _Subscribed):
            logger.callback(replace(outcome, location=_caller_location()))
            return
        detail = _indented_diff(outcome.diff, "   ")
        logger.warning("\n".join([outcome.message, *detail]) if detail else outcome.message)

    @staticmethod
    def _failure(outcome: AssertionOutcome) -> AssertionFailure:
        """Build the exception for a composed failure.

        One class for every failure.  The older split raised a bare `AssertionError` whenever the
        assertion had named no expected value and built no diff, which is most of them, so whether a
        caught failure carried structure at all depended on which assertion had failed.

        Separate from `_deliver` for the one caller that composes its own message: `NegatedBuilder`
        inverts by catching, so its own failure is the case where nothing was caught.
        """
        failure = AssertionFailure(
            outcome.message,
            actual=outcome.actual,
            expected=None if outcome.expected is MISSING else outcome.expected,
            diff=outcome.diff,
            requirement=outcome.requirement,
        )
        failure._outcome = outcome
        return failure

    def eventually(
        self,
        *,
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: type[Exception] | RetriedInfo = (),
        trace: bool = True,
    ) -> AsyncAssertionBuilder:
        """Switch to async polling mode for eventual-consistency assertions.

        The current ``val`` must be a callable (sync or async).  Returns an
        `AsyncAssertionBuilder` whose assertion
        methods are coroutines that poll ``val()`` until the assertion passes or
        ``timeout`` expires.

        By default only a failing assertion is retried: any other exception raised by ``val()`` itself
        propagates immediately.  An ``AssertionError`` from ``val()`` reaches the same place a failing
        assertion does and is retried the same way, which the timeout message names.  A probe that
        signals "not ready yet" by raising something else (a connection refused while a service boots,
        a record not yet visible) can be retried too by listing those types in ``ignoring``.

        Polling itself is always strict - retrying *requires* hard failures - but the final timeout
        failure honors the builder's mode: inside
        [`soft_assertions()`][assertpy.assertpy.soft_assertions] it is collected instead of raised,
        and under [`assert_warn()`][assertpy.assertpy.assert_warn] it is logged.

        Args:
            timeout: maximum seconds to keep retrying (default ``5.0``). Infinity, or a number past the
                float range, retries until the assertion passes
            interval: seconds between retries (default ``0.5``), finite
            ignoring: an ``Exception`` subclass, or a union or a tuple of them, the polling loop retries instead of
                propagating (default: none)
            trace: record a [`PollTrace`][assertpy.errors.PollTrace] flight recorder attached to the
                timeout failure (default ``True``); pass ``False`` to skip recording, for tight
                polling loops where per-poll snapshots of a heavy probed value are too costly

        Examples:
            Usage:

                import asyncio
                from assertpy import assert_that

                counter = {"n": 0}

                def get_count():
                    counter["n"] += 1
                    return counter["n"]

                asyncio.run(
                    assert_that(get_count).eventually(timeout=2).is_equal_to(3)
                )

            Retry a probe that raises while the system under test is not ready yet:

                await assert_that(get_order).eventually(timeout=10, ignoring=ConnectionError).has_status("PAID")

                # or configure fluently on the returned builder
                await assert_that(get_order).eventually().within(10).ignoring(ConnectionError).has_status("PAID")

        Returns:
            AsyncAssertionBuilder: an async builder whose assertion methods are awaitable

        Raises:
            TypeError: if ``val`` is not callable, if ``timeout`` or ``interval`` is not a real number or is
                a bool, or if ``ignoring`` contains anything that is not an ``Exception`` subclass
            ValueError: if ``timeout`` or ``interval`` is negative or NaN, or ``interval`` is infinite
        """
        if not callable(self.val):
            refuse(self.val, "callable, since eventually() polls it")
        return AsyncAssertionBuilder(
            self.val,
            builder_func=_builder,
            description=self.description,
            timeout=timeout,
            interval=interval,
            ignoring=_normalize_ignoring(ignoring),
            kind=self.kind,
            logger=self.logger,
            trace=trace,
        )

    def eventually_sync(
        self,
        *,
        timeout: float = 5.0,
        interval: float = 0.5,
        ignoring: type[Exception] | RetriedInfo = (),
        trace: bool = True,
    ) -> SyncAssertionBuilder:
        """Switch to blocking polling mode for eventual-consistency assertions, without asyncio.

        The synchronous sibling of [`eventually()`][assertpy.assertpy.AssertionBuilder.eventually]:
        the current ``val`` must be a sync callable, and the returned
        `SyncAssertionBuilder` exposes assertion methods
        that block the calling thread (via ``time.sleep``) while polling ``val()`` until the
        assertion passes or ``timeout`` expires - no event loop and no ``await`` needed.  A probe
        that returns an awaitable raises ``TypeError``; poll async probes with ``eventually()``.

        Retry, failure-mode, and diagnostics semantics are identical to ``eventually()``: only a
        failing assertion (or an exception type listed in ``ignoring``) is retried, the final
        timeout failure honors the builder's soft/warn mode, and it carries the same
        [`PollTrace`][assertpy.errors.PollTrace] flight recorder.

        Args:
            timeout: maximum seconds to keep retrying (default ``5.0``). Infinity, or a number past the
                float range, retries until the assertion passes
            interval: seconds between retries (default ``0.5``), finite
            ignoring: an ``Exception`` subclass, or a union or a tuple of them, the polling loop retries instead of
                propagating (default: none)
            trace: record a [`PollTrace`][assertpy.errors.PollTrace] flight recorder attached to the
                timeout failure (default ``True``); pass ``False`` to skip recording, for tight
                polling loops where per-poll snapshots of a heavy probed value are too costly

        Examples:
            Usage:

                from assertpy import assert_that

                counter = {"n": 0}

                def get_count():
                    counter["n"] += 1
                    return counter["n"]

                assert_that(get_count).eventually_sync(timeout=2, interval=0.1).is_equal_to(3)

            Retry a probe that raises while the system under test is not ready yet:

                assert_that(get_order).eventually_sync(timeout=10, ignoring=ConnectionError).has_status("PAID")

                # or configure fluently on the returned builder
                assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status("PAID")

        Returns:
            SyncAssertionBuilder: a blocking builder whose assertion methods poll on call

        Raises:
            TypeError: if ``val`` is not callable, if ``timeout`` or ``interval`` is not a real number or is
                a bool, or if ``ignoring`` contains anything that is not an ``Exception`` subclass
            ValueError: if ``timeout`` or ``interval`` is negative or NaN, or ``interval`` is infinite
        """
        if not callable(self.val):
            refuse(self.val, "callable, since eventually_sync() polls it")
        return SyncAssertionBuilder(
            self.val,
            builder_func=_builder,
            description=self.description,
            timeout=timeout,
            interval=interval,
            ignoring=_normalize_ignoring(ignoring),
            kind=self.kind,
            logger=self.logger,
            trace=trace,
        )


class _ExtendedBuilder(AssertionBuilder[Any]):
    """Host for user extensions: `add_extension()` installs plain functions here, so binding happens
    once at registration and `AssertionBuilder` itself stays pristine when an extension is removed."""


_made_builder: Callable[..., Any] = _ExtendedBuilder
"""What `_builder()` makes: `_ExtendedBuilder`, or while any `log_passes()` block is open, the class it hands out."""


_ASSERTS: Final = frozenset(
    name
    for name in dir(AssertionBuilder)
    if not name.startswith("_")
    and name not in NOT_AN_OPERATION
    and (name not in WITHOUT_A_VERDICT or name in ALSO_ASSERTS)
) | {"assert_conforms"}
"""The names `_requirement_of()` will answer with, derived rather than listed.

The complement of the register, plus the one assertion that is a module function and so has no frame
with a builder in it.  A hybrid such as `when_called_with()` belongs here: the register calls it a
configurer because it hands a value back, and it reaches a verdict on the way.
"""
