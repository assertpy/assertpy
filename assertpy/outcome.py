"""The record of one failed assertion, between composing it and doing something about it.

`AssertionBuilder.error()` used to do both jobs in one body: it built the message, and then it decided
whether to raise, collect or log.  Only the string survived that function, which is why the soft
collector can hold nothing else, why there is nowhere to hand a caller a result instead of an
exception, and why `eventually()` has to bypass `error()` entirely to attach its poll trace.

Splitting the two leaves a record in the middle.  This is that record.  It carries what was composed,
not what should happen to it: the decision belongs to the delivery half, which reads the builder's
mode.

`check()` is the first caller outside this package to read one, so the type is exported and documented
from here on.  What it does **not** promise yet is that no field will be added: the soft collector is
next to hold these, and holding them is what will tell whether a failure's location belongs on the
record too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .errors import DiffResult, PollTrace


class _Missing:
    """The type of `MISSING`, so it reprs as itself in a dataclass and in a debugger."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = _Missing()
"""Stands in for an argument the caller did not pass.

``None`` cannot do that job: an assertion comparing a value against ``None`` passes ``None`` as a real
expected value, and the two readings are then indistinguishable.  The same ambiguity in `DiffEntry`
used to render a key whose value is ``None`` as a key that is not there at all.
"""


@dataclass(frozen=True, slots=True)
class Requirement:
    """What was asked of the value, as data rather than as a sentence.

    A consumer reading `AssertionOutcome` could tell what failed only by parsing the message: the
    fields beside it answer what the values were, not what was asked of them.  `expected` carries five
    different things depending on the family, the operand for `is_equal_to(2)`, a tuple for
    `contains(2)`, a rendered description for `satisfies(...)`, a type for `is_instance_of(str)`, and
    nothing at all for `is_empty()`, so grouping failures across a suite meant reading English.
    """

    operation: str
    """The name the caller wrote, as it appears in the API.

    A delegating assertion answers its own name rather than the one it delegates to: `is_positive()`
    asks `is_greater_than(0)` underneath, and the reader wants the assertion in the test.
    """

    parameters: Mapping[str, object] = field(default_factory=dict)
    """Every declared parameter with the value the assertion ran with, by name.

    Bound values rather than the call as written, which means a parameter left out appears with its
    default.  Two spellings of one requirement then group as one: `is_close_to(9, 0.1)` and
    `is_close_to(other=9, tolerance=0.1)` both read ``{"other": 9, "tolerance": 0.1}``, where a
    positional tuple would also be indistinguishable from a two-operand `contains`.

    The values are the objects themselves, as `actual` and `expected` already are, so a consumer that
    serialises has the same work to do here as there.
    """

    negated: bool = False
    """Whether the assertion ran through `not_`, where holding is the failure."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssertionOutcome:
    """What one assertion decided, as a value rather than as a raised exception.

    Returned by [`check()`][assertpy.assertpy.AssertionBuilder.check], which runs an assertion for its
    verdict instead of for its failure.  Truthy when the assertion passed, so it reads as the answer to
    the question it was asked.
    """

    passed: bool = False
    """Whether the assertion held.

    ``False`` on every record the failure path builds, which is all of them until something asks for a
    verdict: a failure is composed only when there is one.
    """

    message: str = ""
    """The full failure text, description prefix and all, exactly as it reaches the reader.

    Empty on a passing outcome.  There is no message for an assertion that held, and inventing one
    would put words in the report of anything that logs whatever it is handed.
    """

    actual: object = None
    """The value under test.  Filled from the builder when the assertion did not name one itself, so
    every failure carries it, and `actual_provided` says which of the two happened."""

    actual_provided: bool = False
    """Whether the assertion passed ``actual`` itself rather than having it filled in.

    Read by anything that renders: a value the assertion chose to name is worth showing, one filled in
    from the builder is usually already in the message.
    """

    expected: object = MISSING
    diff: DiffResult | None = None

    requirement: Requirement | None = None
    """Which operation was asked, with which parameters, and whether it was negated.

    ``None`` where no operation was asked, and that is a limit of the contract rather than a gap to be
    closed later.  Three shapes have no operation to name: `fail()`, a bare `error()` carrying a
    message of the caller's own, and a precondition of one of the few members `_operations.py` records
    as asserting nothing, where the failure is about the value's shape and not about a requirement.
    """

    trace: PollTrace | None = None
    """The convergence telemetry of a poll that timed out.

    Here rather than only on the exception because a polling assertion under a soft block or in warn
    mode never builds one: it goes through the same delivery as everything else, and the trace used to
    stop at that boundary.
    """

    group: str | None = None
    """The label a soft block was grouping under when this was collected.

    Only a soft block groups, so this is ``None`` everywhere else, including on a failure that was
    raised.  Kept on the record rather than beside it so a collected failure stays one thing.
    """

    location: tuple[str, int] | None = None
    """The ``(file, line)`` of the caller, on a failure that was collected rather than raised.

    ``None`` on a raised failure, whose traceback is the better answer, and where finding this costs a
    walk of the whole stack that nothing would read.
    """

    hint: str | None = None
    """The diagnostic line, kept apart from ``message`` as well as glued into it.

    It is glued in because that is where a reader needs it, and kept apart because once it is part of
    the string nothing downstream can tell it from the assertion's own words.
    """

    @property
    def has_expected(self) -> bool:
        """Whether an expected value was named at all, which ``expected is not None`` cannot answer."""
        return self.expected is not MISSING

    def __bool__(self) -> bool:
        """The verdict, so ``if assert_that(x).check().is_positive():`` reads as the question it asks."""
        return self.passed
