"""What a `log_passes()` block reports, and the state that tells a pass from a failure delivered quietly.

A built-in assertion does no bookkeeping when it holds, and outside every block that stays true: `_builder()`
makes `_ExtendedBuilder` itself until a block opens somewhere.  A builder made inside a block is of a class whose
assertions are observed, and an observed call reports itself once it has run without a failure being delivered.

Returning is not the verdict.  A soft block collects a failure and the chain goes on, a warn chain logs one and
goes on, and `check()` hands a failure back as a value, so an observed call holds an `Observed` that
`mark_failed()` flips where a failure is delivered without raising.  Only the outermost observed call reports:
`is_positive()` asks `is_greater_than(0)` of the same builder, and the reader wrote the first.

Every marker here has a lifetime of its own, `alive`, and not only a place in a context.  A task started inside an
observed call, a poll attempt or a block keeps a copy of the context it started in, and without the flag it went
on reading a call that had returned as one still running.
"""

from __future__ import annotations

import contextvars
import itertools
import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from .outcome import AssertionOutcome


class PassLogger(Protocol):
    """What a block asks of a logger: whether a level is on, and one line at it, as `Logger` and `LoggerAdapter` do."""

    def isEnabledFor(self, level: int) -> bool: ...  # noqa: N802 - the name `logging` gives it

    def log(self, level: int, msg: str) -> object: ...


open_blocks = 0
"""How many `log_passes()` blocks are open in any thread."""

_counting = threading.Lock()

logged_class: type[Any] | None = None
"""The builder class a block hands out, made when the first block opens: its wrappers cost the import nothing."""

_births = itertools.count()
"""The order entries and poll attempts began in, so a pass can tell an entry made during its attempt."""


@dataclass(slots=True)
class PassScope:
    """Where the passes of one entry into a block go: to *on_pass* when given, else to *logger* at *level*.

    Made afresh at each entry, and ``active`` goes off at its exit for good: a task that outlived the entry holds
    this in its own context copy, and a later entry of the same block is not its.  *previous* is the scope the
    entry's context had before it, put back at the exit by the context that exits, which needs no token: two tasks
    entering one block each restore their own.
    """

    logger: PassLogger
    level: int
    on_pass: Callable[[AssertionOutcome], object] | None
    previous: PassScope | None = None
    active: bool = True
    born: int = field(default_factory=lambda: next(_births))

    def wanted(self) -> bool:
        """Whether anything would read a pass, so one nobody reads is never rendered.  Asked of an active scope."""
        return self.on_pass is not None or self.logger.isEnabledFor(self.level)


class Observed:
    """An assertion call being observed, whether a failure was delivered while it ran, and whether it still runs."""

    __slots__ = ("alive", "failed")

    def __init__(self) -> None:
        self.failed = False
        self.alive = True


class Held:
    """The passes of one poll attempt, kept until the attempt is known to have passed as a whole.

    *wanted* is the entry's logger asked once before the attempt, outside the retry, so a pass into it renders
    nothing a refusing logger would drop.  *scope* is ``None`` for a poll in a context outside every block, which
    still holds what its probe asserts through builders of blocks open elsewhere.  A poll inside another's attempt
    takes the outer one's entry and answer, and hands what it held to that attempt.
    """

    __slots__ = ("alive", "born", "records", "scope", "wanted")

    def __init__(self, scope: PassScope | None, wanted: bool) -> None:
        self.records: list[tuple[PassScope, AssertionOutcome, Callable[[], str], bool]] = []
        self.scope, self.wanted = scope, wanted
        self.alive = True
        self.born = next(_births)


scope: contextvars.ContextVar[PassScope | None] = contextvars.ContextVar("assertpy_pass_scope", default=None)
observed: contextvars.ContextVar[Observed | None] = contextvars.ContextVar("assertpy_observed", default=None)
held: contextvars.ContextVar[Held | None] = contextvars.ContextVar("assertpy_held_passes", default=None)


def open_block(make_class: Callable[[], type[Any]], counted: Callable[[int], object]) -> None:
    """Count a block in, making the class it hands out on the first, and tell *counted* the count under the lock."""
    global open_blocks, logged_class
    with _counting:
        if logged_class is None:
            logged_class = make_class()
        open_blocks += 1
        counted(open_blocks)


def close_block(counted: Callable[[int], object]) -> None:
    """Count a block out, telling *counted* the count under the lock."""
    global open_blocks
    with _counting:
        open_blocks -= 1
        counted(open_blocks)


def active_scope() -> PassScope | None:
    """The entry this context reports into, or ``None`` outside every one and after it closed."""
    found = scope.get()
    return found if found is not None and found.active else None


def current_call() -> Observed | None:
    """The observed call still running in this context, if any."""
    call = observed.get()
    return call if call is not None and call.alive else None


def mark_failed() -> None:
    """Note on the observed call that a failure was delivered without raising, so it reports no pass."""
    if open_blocks and (call := current_call()) is not None:
        call.failed = True


def wants(found: PassScope) -> bool:
    """Whether a pass into *found* is to be made, asked of the attempt when one is held and of the entry otherwise.

    A pass into another entry than the attempt's is kept and decided at the flush.  An entry that closed while the
    assertion ran, which a predicate leaving the block's `ExitStack` does, wants nothing and its logger is not asked.
    """
    if not found.active:
        return False
    kept = _holding(found)
    if kept is not None:
        return kept.wanted if found is kept.scope else True
    return found.wanted()


def _holding(found: PassScope) -> Held | None:
    """The attempt a pass into *found* waits in, or ``None`` where it is handed on as it comes.

    A block entered after the attempt began, by its probe or beside it, belongs to the attempt: its passes go as they
    come, and what its callback or logger raises is the attempt's to retry.  Told by when it was entered and not by
    what it was entered inside, since a context copied in one block can run a poll after another block was entered.
    """
    kept = held.get()
    if kept is None or not kept.alive or found.born > kept.born:
        return None
    return kept


def emit(found: PassScope, outcome: AssertionOutcome, line: Callable[[], str]) -> None:
    """Hand one pass on, or keep it for the poll attempt it came from, rendered now while its values are as checked.

    A pass into another entry than the attempt's has not asked that entry's logger whether it wants the level: that
    is user code, and asked inside an attempt an `AssertionError` it raised was retried as the assertion's own.  The
    flush asks, past the retry.
    """
    kept = _holding(found)
    if kept is not None:
        rendered = "" if found.on_pass is not None else line()
        kept.records.append((found, outcome, lambda: rendered, found is kept.scope))
        return
    deliver(found, outcome, line, asked=True)


def deliver(found: PassScope, outcome: AssertionOutcome, line: Callable[[], str], *, asked: bool) -> None:
    """To the callback, or as one line to the logger, with any assertion they make themselves left unreported.

    *asked* says whether the logger has already said it wants the level.  An entry that closed in the meantime,
    which a predicate leaving the block's `ExitStack` does, takes nothing.
    """
    if not found.active:
        return
    quiet = Observed()
    token = observed.set(quiet)
    try:
        if found.on_pass is not None:
            found.on_pass(outcome)
        elif asked or found.logger.isEnabledFor(found.level):
            found.logger.log(found.level, line())
    finally:
        quiet.alive = False
        observed.reset(token)


def holding() -> Held | None:
    """A place for one poll attempt's passes, or ``None`` inside an observed call, where none is made.

    Made before the attempt and outside its retry, which is where the logger is asked whether it wants the level,
    with any assertion it makes left unreported.  Inside another attempt that is the outer retry, so nothing is asked.
    """
    if current_call() is not None:
        return None
    outer = held.get()
    if outer is not None and outer.alive:
        return Held(outer.scope, outer.wanted)
    found = active_scope()
    if found is None:
        return Held(None, False)
    quiet = Observed()
    token = observed.set(quiet)
    try:
        return Held(found, found.wanted())
    finally:
        quiet.alive = False
        observed.reset(token)


def release(kept: Held, token: contextvars.Token[Held | None]) -> None:
    """Take *kept* out of place once the attempt is over, however it ended, for anything that outlives it."""
    held.reset(token)
    kept.alive = False


def flush(kept: Held) -> None:
    """Hand on what a poll's passing attempt held, in the order it ran, to the attempt it ran inside if any.

    A pass into a block entered during that outer attempt goes now: the block is the outer probe's.
    """
    kept.alive = False
    outer = held.get()
    for record in kept.records:
        if outer is not None and outer.alive and record[0].born < outer.born:
            outer.records.append(record)
        else:
            found, outcome, line, asked = record
            deliver(found, outcome, line, asked=asked)


default_logger: logging.Logger = logging.getLogger("assertpy.passes")
