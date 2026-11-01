"""Generate the polling twins of the assertion protocols.

A polling chain records the assertion and replays it until it holds, so every assertion is available
through it with the return type replaced by the chain itself.  Both builders resolve the name at run
time through `__getattr__`, which no checker can read: until this existed, a polling chain was `Any`
from the first assertion onwards, and `eventually_sync().method_that_does_not_exist()` passed all
three checkers.

The twins are one flat protocol per flavour rather than one per view, and each assertion carries the
value types it applies to in its own ``self`` annotation.  A view per value type would have to be
chosen by `eventually_sync()`, whose overloads see the probe's return type: measured, a probe with no
annotation returns `Any`, an `Any` self matches the first rung, and every checker then reported a
string assertion on a chain that polls anything.  Per-assertion ``self`` inverts that: an `Any` chain
matches every rung and keeps the freedom it has today, and an annotated one is held to its type.

Two more shapes were measured against the same pair of questions, and both fail on the second one.  The
questions: does a string chain refuse `is_positive()`, and does an unannotated probe keep
`has_status("PAID")`.

* **a view per value type.**  The assertion is not declared on the view at all, so `__getattr__` answers
  it and nothing is refused.  Taking the hook off does refuse it on all three, and then mypy refuses
  `has_status("PAID")` on an unannotated probe, which is the idiom the hook exists for.
* **a view per value type, hook kept, with the assertions a view does not carry declared as
  non-callable sentinels** so a declaration shadows the hook.  This one does refuse the string chain on
  all three.  It also collapses on an unannotated probe, where the sentinel turns into a false
  rejection: pyright refuses `has_status("PAID")`, and mypy and pyright refuse a numeric assertion that
  is correct.

So the flat protocol is the only shape measured that refuses anything at all while the hook keeps
working, and what it cannot refuse is a value whose own view is narrower than the umbrella: overload
resolution has no way to say "only if no earlier rung matched".  `str` binds `_CapableT` by being
iterable, and there is no negation to exclude a type that has a view of its own.

Half of that is reachable anyway, and the half that is turns on where the *operands* come from.  A rung
is emitted per protocol *and per binding*, since `_TextAssertion` reaches `_RepeatableAssertion[str]`
while `_ListAssertion[_E]` reaches `_RepeatableAssertion[_E]`, and one rung covering both left `_E`
free for a text chain to bind off the argument.  The umbrella rung then has to read the element off the
receiver rather than leave it open, which is what `contains_in_order` asks `Iterable[_E]` for.  Both are
needed: measured, the split alone changes nothing, and the restriction alone changes nothing.

What that closes is an operand of the wrong type on a polled string, on mypy and pyright.  What stays
open is an assertion the value answers structurally, `is_positive()` on a polled string being the one
recorded: `str` orders, so the umbrella rung matches however the operands are typed.

Where that leaves the residue is worth naming, because it is not here.  `assert_that()` hands a value
the umbrella claims the whole builder, so `assert_that(mapping_shaped).is_positive()` type-checks off
the chain too and raises when it runs.  Narrowing the chain alone would leave a polled value stricter
than the same value off it, so the repair belongs to the umbrella.  Both are recorded as cases in
`tests/typing_negative_baseline.py`.

Rungs follow the order `assert_that()` dispatches in, since they answer the same question.

Run: `python scripts/generate_poll_protocols.py`
"""

from __future__ import annotations

import ast
import copy
import pathlib
import re
import subprocess
import sys
from typing import Final, NamedTuple, cast

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEWS = ROOT / "assertpy" / "_engine" / "_typing.py"
ENTRY = ROOT / "assertpy" / "assertpy.py"
TARGET = ROOT / "assertpy" / "_engine" / "_poll_typing.py"
TARGET_VERDICT = ROOT / "assertpy" / "_engine" / "_builder_check_typing.py"
TARGET_CAPABLE = ROOT / "assertpy" / "_engine" / "_capable_typing.py"
TARGET_NEGATED = ROOT / "assertpy" / "_engine" / "_negated_typing.py"

sys.path.insert(0, str(ROOT))
from assertpy._engine._operations import (  # noqa: E402 - needs the path
    ALSO_ASSERTS,
    NOT_AN_OPERATION,
    TRANSFORMS,
    WITHOUT_A_VERDICT,
)

# `not_` stays a property: the rewrite into a chain over the same value would have made it a call.  The
# two polls are rungs like any other, restricted to a chain over a callable, which is what a second poll
# asks of the value the first hands back
_SKIP = NOT_AN_OPERATION

# the verdict twin carries only what reaches a verdict, the same rule the per-view twins follow
_SKIP_FOR_A_VERDICT = NOT_AN_OPERATION | set(WITHOUT_A_VERDICT)

_VERDICT = "_CheckAnyValue"

# what a chain hands back once an expectation is set on it, which is the only state `when_called_with()`
# can be told from the absence of
_EXPECTING: Final = {"_SyncPoll": "_SyncPollExpecting", "_AsyncPoll": "_AsyncPollExpecting"}

_NOT_CARRIED: Final = frozenset({"_Exc"})
"""Parameters of a view that a chain over its value does not carry: the exception an expectation names."""

_LANDINGS: Final = {"_InvokedAssertion": "Invoked", "_WarnedAssertion": "Warned", "_CompletedAssertion": "Completed"}
"""The view a call lands on, to the name of its chain after the flavour: `_SyncPollInvoked` and the rest."""

_HEADER = '''"""The polling twin of every assertion protocol, generated by `scripts/generate_poll_protocols.py`.

Do not edit.  A polling chain replays the assertions recorded on it until they hold together, so it
offers the same assertions the value's own view does and hands back the chain rather than a builder.

Which assertions a chain offers follows the probe's return type, carried in each ``self`` annotation
rather than in the chain's class: see the generator for why the alternative reported a string
assertion on every chain built from an unannotated probe.

A name nobody declares stays open, because `__getattr__` answers it.  That is what keeps
``has_status("PAID")`` working: a dynamic assertion is resolved from the polled value's own
attributes, and no declaration can list it.  It hands back the chain over the same value rather than
one over an unknown, so the assertions after it are still read.  A name that *is* declared still
refuses a chain it was not declared for, measured on mypy and pyright: the hook answers only what the
declarations do not.

What the chain is *not* held to is the surface of a value the capability umbrella claims.  Each
assertion carries a last rung for it, because that is the surface `assert_that()` hands such a value,
and Python's overload resolution has no way to say "only if no earlier rung matched".  So a `str`,
being iterable, reaches rungs the string view does not carry.

Its *operands* are held, though, where the value's own type says what they are: a rung is emitted per
binding as well as per protocol, so a chain over text takes the elements text has rather than any the
argument happens to be.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
{imports}
    from ._typing import _CompletedAssertion, _InvokedAssertion, _WarnedAssertion

    # what the call lands on, carried by the expectation and read by `when_called_with()`
    _L_co = TypeVar("_L_co", covariant=True)
    _R_co = TypeVar("_R_co", covariant=True)
    _Exc_co = TypeVar("_Exc_co", bound=BaseException, covariant=True)

    class _NoVerdictAfterAPoll:
        """The type of `check` on a polling chain, which is not callable and says why in the diagnostic.

        A poll delivers its own failure, so there is no verdict to hand back and `check()` is refused at
        run time.  Declared here so the three checkers that read a declaration over `__getattr__` refuse
        it where it is written rather than where it runs.
        """

    class _NoValueOnAChain:
        """The type of `value` on a polling chain, which is not callable and says why.

        A chain hands its value back under `val`, and `value` is a name only the builder has.  Left to
        `__getattr__` it was recorded as an assertion and failed inside the replay, where the message
        named a type and not the mistake.
        """

    class _NoExpectationOnAChain:
        """The type of `when_called_with` on a chain with no expectation set, which is not callable.

        The call raises `no expectation set` at run time.  Which expectation was set is a state, and a
        rung is chosen by its ``self`` annotation alone, so the state has to be the type `raises()`,
        `warns()` and the two `does_not_*` hand back.
        """

    class _NotAnAssertionToNegate:
        """The type of a name a negated polling chain refuses, which is not callable and says why.

        `not_` negates the assertion after it.  A transform, an expectation, a description and a second
        negation are not assertions, so each raises at run time.  Declared rather than left to
        `__getattr__`, which answers any name the class does not carry.
        """

    class _SyncPoll(Protocol[_P_co]):
        """A blocking polling chain over a probe returning `_P_co`."""

        def within(self, timeout: float) -> _SyncPoll[_P_co]: ...
        def every(self, interval: float) -> _SyncPoll[_P_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _SyncPoll[_P_co]: ...
        @property
        def not_(self) -> _NegatedSyncPoll[_P_co]: ...
        @property
        def val(self) -> _P_co: ...
        check: _NoVerdictAfterAPoll
        value: _NoValueOnAChain
        when_called_with: _NoExpectationOnAChain
        def __getattr__(self, name: str) -> Callable[..., _SyncPoll[_P_co]]: ...
{sync}

    class _SyncPollExpecting(Protocol[_P_co, _L_co]):
        """A chain with an expectation set, which is the one state `when_called_with()` needs.

        Its own protocol rather than a subclass, for the reason the negated chain is one: a protocol
        inheriting the one that hands it back overflowed ty's stack.

        The assertions come off the hook rather than being repeated here.  Nothing in the tree or the
        docs writes an assertion between an expectation and the call, and repeating them costs about
        1300 declarations for that shape alone.  `_L_co` is the chain the call lands on, which each
        expectation names: the caught message, the warning's message, or the callable that completed.
        """

        def within(self, timeout: float) -> _SyncPollExpecting[_P_co, _L_co]: ...
        def every(self, interval: float) -> _SyncPollExpecting[_P_co, _L_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _SyncPollExpecting[_P_co, _L_co]: ...
        @property
        def val(self) -> _P_co: ...
        check: _NoVerdictAfterAPoll
        def when_called_with(self, *some_args: object, **some_kwargs: object) -> _L_co: ...
        def __getattr__(self, name: str) -> Callable[..., _SyncPoll[_P_co]]: ...

    class _NegatedSyncPoll(Protocol[_P_co]):
        """What `not_` hands back: the same chain, with what cannot be negated declared as refused.

        Its own protocol rather than a subclass of the chain: inheriting the protocol whose `not_` hands
        this one back overflowed ty's stack (0.0.83) on
        `assert_type(assert_that(len), _CallableAssertion[int])`, bisected to that one line.

        The assertions hand back the plain chain, since a negation covers the one assertion after it,
        measured on both the chain and the builder.  Setting the budget keeps it, so those hand back
        this one.
        """

        def within(self, timeout: float) -> _NegatedSyncPoll[_P_co]: ...
        def every(self, interval: float) -> _NegatedSyncPoll[_P_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _NegatedSyncPoll[_P_co]: ...
        @property
        def val(self) -> _P_co: ...
        check: _NoVerdictAfterAPoll
{refusals}
        def __getattr__(self, name: str) -> Callable[..., _SyncPoll[_P_co]]: ...
{sync_negated}

    class _AsyncPoll(Protocol[_P_co]):
        """An awaitable polling chain over a probe returning `_P_co`.

        Awaiting it hands back the ordinary builder over the value that passed, so anything asked
        afterwards is a plain assertion on a settled value rather than a new wait.
        """

        def within(self, timeout: float) -> _AsyncPoll[_P_co]: ...
        def every(self, interval: float) -> _AsyncPoll[_P_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _AsyncPoll[_P_co]: ...
        def close(self) -> None: ...
        @property
        def not_(self) -> _NegatedAsyncPoll[_P_co]: ...
        def __await__(self) -> Generator[Any, None, AssertionBuilder[_P_co]]: ...
        check: _NoVerdictAfterAPoll
        value: _NoValueOnAChain
        when_called_with: _NoExpectationOnAChain
        def __getattr__(self, name: str) -> Callable[..., _AsyncPoll[_P_co]]: ...
{asynchronous}

    class _AsyncPollExpecting(Protocol[_P_co, _L_co]):
        """The awaitable chain with an expectation set, built the same way."""

        def within(self, timeout: float) -> _AsyncPollExpecting[_P_co, _L_co]: ...
        def every(self, interval: float) -> _AsyncPollExpecting[_P_co, _L_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _AsyncPollExpecting[_P_co, _L_co]: ...
        def close(self) -> None: ...
        @property
        def val(self) -> _P_co: ...
        check: _NoVerdictAfterAPoll
        def when_called_with(self, *some_args: object, **some_kwargs: object) -> _L_co: ...
        def __getattr__(self, name: str) -> Callable[..., _AsyncPoll[_P_co]]: ...

    class _NegatedAsyncPoll(Protocol[_P_co]):
        """The awaitable chain's negation, built the same way and refusing the same names."""

        def within(self, timeout: float) -> _NegatedAsyncPoll[_P_co]: ...
        def every(self, interval: float) -> _NegatedAsyncPoll[_P_co]: ...
        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> _NegatedAsyncPoll[_P_co]: ...
        def close(self) -> None: ...
        def __await__(self) -> Generator[Any, None, AssertionBuilder[_P_co]]: ...
        check: _NoVerdictAfterAPoll
{refusals}
        def __getattr__(self, name: str) -> Callable[..., _AsyncPoll[_P_co]]: ...
{asynchronous_negated}
{landings}
'''

_IMPORTS = """    import datetime
    import pathlib
    import re
{abc}
    from pathlib import Path
    from typing import Any, Protocol, SupportsFloat, SupportsIndex, TypeVar, overload

    from typing_extensions import TypeIs

    from .._matcher_impls import ClassInfo, ExceptionInfo, RetriedInfo, WarningInfo
    from ..assertpy import AssertionBuilder
    from ..matchers import Matcher
    from ._capable_typing import (
        _Callable,
        _Indexed,
        _Keyed,
        _KeyedWithItems,
        _KeyedWithValues,
        _Orderable,
        _PathLike,
    )
    from ._introspection import MappingLike

    from ._typing import (
        _ArrayT_co,
        _Capable,
        _CapableT,
        _Exc,
        _FrameT_co,
        _Landed,
        _Other,
        _P_co,
        _T_co,
        _U,
    )

    _KeySpecs = Hashable | list[Hashable] | set[Hashable] | frozenset[Hashable]

    _E = TypeVar("_E")
    _N = TypeVar("_N", int, float)
    _K = TypeVar("_K")
    _V = TypeVar("_V")
    _R = TypeVar("_R")
    _B_co = TypeVar("_B_co", bytes, bytearray, covariant=True)
    _U2 = TypeVar("_U2")
    _U3 = TypeVar("_U3")
    _Number = SupportsFloat

    # the rungs below restrict `self` with the annotations `assert_that()` overloads are written with
    _T = TypeVar("_T")
    _P = TypeVar("_P")"""


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def _bases(node: ast.ClassDef, known: dict[str, ast.ClassDef]) -> list[str]:
    found = []
    for base in node.bases:
        target = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(target, ast.Name) and target.id in known:
            found.append(target.id)
    return found


def _lineage(name: str, known: dict[str, ast.ClassDef], seen: list[str] | None = None) -> list[str]:
    """*name* and every protocol above it, in the order a reader meets them."""
    seen = [] if seen is None else seen
    if name in seen or name not in known:
        return seen
    seen.append(name)
    for base in _bases(known[name], known):
        _lineage(base, known, seen)
    return seen


def _dispatch() -> list[tuple[str, str]]:
    """``(value type, view)`` per `assert_that()` overload, in the order the overloads are written."""
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "assert_that":
            first = node.args.args[0]
            if first.annotation is not None and node.returns is not None:
                found.append((ast.unparse(first.annotation), ast.unparse(node.returns)))
    return found


def _polled(annotation: str, flavour: str) -> str:
    """The chain over *annotation*, which is what a rung restricts its ``self`` to."""
    return " | ".join(f"{flavour}[{one.strip()}]" for one in annotation.split("|"))


_PER_CALL: Final = frozenset(re.findall(r"^ *(_\w+) = TypeVar\(", _IMPORTS, re.MULTILINE))
"""The type variables a rung solves per call, as against `_P_co`, which the chain already carries."""


def _one_per_member(rung: ast.FunctionDef, restriction: str | None) -> list[ast.FunctionDef]:
    """*rung* once per chain its ``self`` is restricted to, where that binds a variable and the return is solved.

    Written as one union, ``list[_E] | tuple[_E, ...] | set[_E] | frozenset[_E]``, mypy solved `_E` to
    `Never`, so a polled `first()` over ints answered `Never`.  Split, mypy answers `int`.  The return
    need not name the bound variable itself: `flat_mapped()` returns `_R`, solved through a parameter
    typed with `_E`, and split only where `_E` was returned, `flat_mapped(identity)` read `Never` again.
    """
    own = (rung.args.posonlyargs or rung.args.args)[0]
    if restriction is None or " | " not in restriction or own.annotation is None:
        return [rung]
    returned = set(re.findall(r"\b_\w+\b", ast.unparse(rung.returns) if rung.returns else ""))
    solved = set(re.findall(r"\b_\w+\b", restriction)) & _PER_CALL
    if ast.unparse(own.annotation) != restriction or not solved or not returned & _PER_CALL:
        return [rung]
    pieces = []
    for member in restriction.split(" | "):
        piece = cast("ast.FunctionDef", ast.parse(ast.unparse(rung)).body[0])
        (piece.args.posonlyargs or piece.args.args)[0].annotation = ast.Name(id=member)
        pieces.append(piece)
    return pieces


def _handed_back(
    node: ast.FunctionDef,
    known: dict[str, ast.ClassDef],
    flavour: str,
    *,
    holder: str,
    umbrella: bool,
    returns_as: str | None = None,
    restriction: str | None = None,
) -> str:
    """The chain an assertion hands back, which is a chain over whatever value the view would hold.

    A pivot names the view it lands on, and every view says what its value is, so the chain after a
    pivot keeps a type rather than falling to `Any`: `first()` on a chain over text is a chain over
    text.  The umbrella rung is the exception, since the value it pivots to is the one thing a
    capability does not say.  The verdict twin hands back a verdict instead of a chain, so none of
    that applies to it.

    A negated chain keeps the value whatever the declaration says it narrows to, because the negation
    is what it asserts: `not_.is_not_none()` says the value *is* `None`, and `not_.is_instance_of(str)`
    says it is not a `str`.  Read narrowed, both handed back a chain over the type they had just denied,
    and `.val` on it was that type to every checker while the run time had the original value.  The
    builder's own negation twins answer the same way, over their receiver's parameter.
    """
    if flavour == _VERDICT:
        return "AssertionOutcome"
    if returns_as is not None:
        return f"{returns_as}[_P_co]"
    if node.returns is None:
        return f"{flavour}[Any]"
    rendered = ast.unparse(node.returns)
    if rendered == "Self":
        return f"{flavour}[_P_co]"
    head, _, tail = rendered.partition("[")
    arguments = [one.strip() for one in tail[:-1].split(",")] if tail else []
    if _keeps_its_value(head, arguments, holder, known):
        landing = _landing(head, arguments, known, flavour, restriction)
        return f"{_EXPECTING[flavour]}[_P_co, {landing}]" if landing else f"{flavour}[_P_co]"
    if umbrella:
        return f"{flavour}[Any]"
    if head == "AssertionBuilder":
        return f"{flavour}[{arguments[0]}]" if arguments else f"{flavour}[Any]"
    value = _value_of(head, known)
    if value is None or _carries_more_than_its_value(head, known):
        return f"{flavour}[Any]"
    for parameter, argument in zip(_parameters(head, known), arguments, strict=False):
        value = re.sub(rf"\b{re.escape(parameter)}\b", argument, value)
    # a rung handing back its own view over its own parameter is `Self` written the long way, which a
    # restricted receiver cannot spell.  Copied verbatim it puts an unbound variable in the chain class
    if value in _parameters(head, known):
        return f"{flavour}[_P_co]"
    return f"{flavour}[{value}]"


def _landing(
    head: str, arguments: list[str], known: dict[str, ast.ClassDef], flavour: str, restriction: str | None
) -> str | None:
    """The chain `when_called_with()` lands on after the expectation *head*, or ``None`` if it names none.

    Read off the expectation view's own `when_called_with()`, with its parameters put in: the exception
    `raises()` was given, and the callable's return where the rung's ``self`` binds one.  The umbrella's
    callable names no return, so that one is `Any`.
    """
    if flavour not in _EXPECTING:
        return None
    call = next(
        (item for item in known[head].body if isinstance(item, ast.FunctionDef) and item.name == "when_called_with"),
        None,
    )
    if call is None or call.returns is None:
        return None
    lands, _, given = ast.unparse(call.returns).partition("[")
    if lands not in _LANDINGS:
        return None
    bound = re.fullmatch(rf"{flavour}\[Callable\[\.\.\., (.+)\]\]", restriction or "")
    written = dict(zip(_parameters(head, known), arguments, strict=False))
    written["_P_co"] = bound.group(1) if bound else "Any"
    parameter = given.rstrip("]").strip()
    if parameter not in written:
        raise ValueError(f"{head}.when_called_with() lands on {lands}[{parameter}], which no argument of it binds")
    return f"{flavour}{_LANDINGS[lands]}[{written[parameter]}]"


def _keeps_its_value(head: str, arguments: list[str], holder: str, known: dict[str, ast.ClassDef]) -> bool:
    """Whether the landing view is the declaring one with more declared on it, over the same value.

    `raises()` is declared on the callable view and lands on the expectation view, which inherits that
    view over the same parameter and adds `when_called_with()`: the value is the same callable, so the
    chain is unchanged and the rung hands itself back.  `when_called_with()` lands on the invoked view,
    which inherits text instead, and that is a pivot to the caught message.

    The values have to match as well as the parameters.  `filtered_on()` is declared above the list view
    and lands on it over the same `_E`, but a list is not the iterable it was declared for, and reading
    that as "unchanged" typed a filtered set as a set.

    A parameter in `_NOT_CARRIED` is state a chain does not hold, so it is not compared.  Any other
    parameter still has to match, since an unshared one can be state the landing view means.
    """
    if head == holder or head not in known:
        return False
    reached = dict(_bound(head, known))
    if holder not in reached or any(parameter != argument for parameter, argument in reached[holder].items()):
        return False
    if _value_of(head, known) != _value_of(holder, known):
        return False
    parameters = _parameters(head, known)
    return len(arguments) == len(parameters) and all(
        argument == parameter
        for parameter, argument in zip(parameters, arguments, strict=True)
        if parameter not in _NOT_CARRIED
    )


def _carries_more_than_its_value(name: str, known: dict[str, ast.ClassDef]) -> bool:
    """Whether a landing view offers assertions no chain over its value type could offer.

    `when_called_with()` lands on the invoked view, whose value is the caught message but whose
    surface adds `raised()`, `returned()` and the exception-group assertions.  Reading that view's
    value type would call the chain a chain over text and then answer those eight names off the hook,
    claiming text for whatever they hand back.  A chain over an unknown value is the honest answer.
    """
    dispatched: set[str] = set()
    for _value, view in _dispatch():
        for protocol in _lineage(view.split("[")[0], known):
            dispatched |= {item.name for item in known[protocol].body if isinstance(item, ast.FunctionDef)}
    landing = {
        item.name
        for protocol in _lineage(name, known)
        for item in known[protocol].body
        if isinstance(item, ast.FunctionDef)
    }
    return bool(landing - dispatched)


def _parameters(name: str, known: dict[str, ast.ClassDef]) -> list[str]:
    """The type variables a view is written over, in the order it declares them."""
    node = known.get(name)
    if node is None:
        return []
    for base in node.bases:
        if isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name) and base.value.id == "Protocol":
            given = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
            return [ast.unparse(one) for one in given]
    return []


def _value_of(name: str, known: dict[str, ast.ClassDef]) -> str | None:
    """What a view says its value is, taken from the first `value` declaration up its lineage."""
    for protocol in _lineage(name, known):
        for item in known[protocol].body:
            if isinstance(item, ast.FunctionDef) and item.name == "value" and item.returns is not None:
                return ast.unparse(item.returns)
    return None


def _rewritten(
    node: ast.FunctionDef,
    restriction: str | None,
    flavour: str,
    known: dict[str, ast.ClassDef],
    *,
    holder: str,
    umbrella: bool = False,
    returns_as: str | None = None,
) -> ast.FunctionDef:
    """The same signature with ``self`` restricted to the chains it applies to and the chain returned."""
    copied = ast.parse(ast.unparse(node)).body[0]
    assert isinstance(copied, ast.FunctionDef)
    own = (copied.args.posonlyargs or copied.args.args)[0]
    if own.annotation is not None:
        # a rung narrowing itself is about the value kept whole: `_ObjectAssertion[str | None]` is one value
        # that is either, and a chain over each member separately is a different question
        inner = ast.unparse(own.annotation)
        own.annotation = ast.Name(id=f"{flavour}[{inner[inner.index('[') + 1 : -1] if '[' in inner else '_P_co'}]")
    elif restriction is not None:
        own.annotation = ast.Name(id=restriction)
    copied.returns = ast.Name(
        id=_handed_back(
            node, known, flavour, holder=holder, umbrella=umbrella, returns_as=returns_as, restriction=restriction
        )
    )
    copied.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
    copied.decorator_list = [one for one in copied.decorator_list if ast.unparse(one) != "property"]
    return copied


def _falls_back_to_a_bare_type(node: ast.FunctionDef, siblings: list[ast.FunctionDef]) -> bool:
    """Whether *node* is the overload a bare `type` falls back to, beside one taking `type[...]`.

    Left off a chain.  With it every checker takes `raises(int)` on a poll, which all four refuse without it
    and the run time refuses too, measured.  Without it ty alone refuses an exception written as a bare
    `type`, which it reads as `type[object]`, and the other three accept through the rung carrying the class.
    """
    written = [ast.unparse(one.annotation) if one.annotation else "" for one in node.args.args[1:]]
    if "type" not in written:
        return False
    return any(
        other is not node
        and other.name == node.name
        and any(ast.unparse(one.annotation).startswith("type[") for one in other.args.args[1:] if one.annotation)
        for other in siblings
    )


def _past_a_bare_type(node: ast.FunctionDef, siblings: list[ast.FunctionDef]) -> ast.FunctionDef:
    """*node* with a bare `type` taken out of a union it is a member of, beside a sibling taking `type[...]`.

    The member is left off a chain for the reason `_falls_back_to_a_bare_type` gives, and the classes written
    beside it in the same union are kept: the chain takes a tuple or a union of exceptions and refuses `int`.
    """
    if not any(
        other is not node
        and other.name == node.name
        and any(ast.unparse(one.annotation).startswith("type[") for one in other.args.args[1:] if one.annotation)
        for other in siblings
    ):
        return node
    rewritten = copy.deepcopy(node)
    for argument in rewritten.args.args[1:]:
        members = _union_members(argument.annotation) if argument.annotation is not None else []
        kept = [one for one in members if ast.unparse(one) != "type"]
        if len(members) > 1 and kept and len(kept) < len(members):
            joined = kept[0]
            for one in kept[1:]:
                joined = ast.BinOp(left=joined, op=ast.BitOr(), right=one)
            argument.annotation = joined
    return rewritten


def _union_members(annotation: ast.expr) -> list[ast.expr]:
    """The members of a union written with `|`, in order, or the annotation alone."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return [*_union_members(annotation.left), *_union_members(annotation.right)]
    return [annotation]


def _lands_elsewhere(rung: ast.FunctionDef, chain: str) -> bool:
    """Whether the umbrella rung hands back anything but a verdict or the chain it was asked on.

    Such a rung keeps the type variable.  Written with the bound itself it overlapped the named rung above it,
    and ty read a polled `first()` over a list as `Unknown`.  A rung that lands where it stood has nothing for the
    overlap to change, and the bound is what holds mypy to it, measured: through the variable it took a value
    that is a number or a text, or an `object`, for one the umbrella claims.
    """
    return ast.unparse(rung.returns or ast.Name(id="")) not in ("AssertionOutcome", f"{chain}[_P_co]")


def _narrows_itself(node: ast.FunctionDef) -> bool:
    """Whether the declaration restricts its own ``self``, which is a restriction the view already made."""
    own = (node.args.posonlyargs or node.args.args)[0]
    return own.annotation is not None


def _refines(node: ast.FunctionDef) -> bool:
    """Whether the rung exists only to narrow the value to another view.

    A `TypeIs` predicate tells `assert_that()` which view to hand back next.  A chain has no next view
    to hand back: every rung of such a ladder erases to a chain over an unknown value, so the ladder
    would be one declaration repeated seventeen times.  The plain rung beneath it accepts the same
    predicates, since a `TypeIs` callable is a callable.
    """
    return "TypeIs[" in ast.unparse(node.args)


class _Reached(NamedTuple):
    """A protocol a dispatched view reaches, with everything the rungs for it are built from."""

    protocol: str
    restriction: str | None
    methods: list[ast.FunctionDef]
    """As the binding leaves them, which is what the named rungs carry."""
    holders: int
    declared: list[ast.FunctionDef]
    """As the protocol wrote them, which is what the umbrella rung carries."""


def _protocols(known: dict[str, ast.ClassDef], flavour: str) -> list[_Reached]:
    """One entry per protocol a dispatched view reaches, per set of arguments the view gave it."""
    ordered_views: list[str] = []
    value_of: dict[str, list[str]] = {}
    for value, view in _dispatch():
        name = view.split("[")[0]
        if name not in known:  # the umbrella hands back the builder itself, which has no protocol
            name = "_Umbrella"
        if name not in ordered_views:
            ordered_views.append(name)
        value_of.setdefault(name, []).append(value)

    named = [view for view in ordered_views if view != "_Umbrella"]
    # keyed by the arguments the view gave the protocol, not by the protocol alone: `_TextAssertion`
    # reaches `_RepeatableAssertion[str]` and `_ListAssertion[_E]` reaches `_RepeatableAssertion[_E]`,
    # and one rung covering both left `_E` free, so a polled string took an element of any type
    reach: dict[tuple[str, tuple[tuple[str, str], ...]], list[str]] = {}
    for view in named:
        for protocol, mapping in _bound(view, known):
            reach.setdefault((protocol, tuple(sorted(mapping.items()))), []).append(view)

    found = []
    for (protocol, binding), holders in sorted(
        reach.items(), key=lambda pair: min(named.index(one) for one in pair[1])
    ):
        # a negated chain drops the same names the verdict twin does, and for the same reason: neither a
        # transform nor an expectation is an assertion.  Declared in the body they would shadow the
        # refusals the class opens with, which is how two checkers stopped seeing them
        skip = _SKIP_FOR_A_VERDICT if flavour == _VERDICT or flavour.startswith("_Negated") else _SKIP
        declared = [
            item
            for item in known[protocol].body
            if isinstance(item, ast.FunctionDef)
            and item.name not in skip
            and not item.name.startswith("_")
            and not _refines(item)
        ]
        if not declared:
            continue
        methods = [_Substituted(dict(binding)).visit(ast.parse(ast.unparse(item)).body[0]) for item in declared]
        values = [value for view in holders for value in value_of.get(view, [])]
        universal = len(holders) == len(named)
        restriction = None if universal else _polled(" | ".join(values), flavour)
        found.append(_Reached(protocol, restriction, methods, len(holders), declared))
    return found


def _rungs(
    known: dict[str, ast.ClassDef], flavour: str, returns_as: str | None = None
) -> dict[str, list[ast.FunctionDef]]:
    """``{name: its rungs}``, in the order `assert_that()` would reach them, one per surviving signature.

    A view that redeclares an inherited assertion to keep its own value type renders the same rung
    twice, since both land on the same chain, so the second is dropped here rather than emitted and
    then reported as an overload nothing can select.
    """
    found: dict[str, list[ast.FunctionDef]] = {}
    open_to_any: dict[str, list[ast.FunctionDef]] = {}
    widest: dict[str, tuple[int, list[ast.FunctionDef], str]] = {}
    seen: set[str] = set()
    for protocol, restriction, methods, holders, declared in _protocols(known, flavour):
        for method, written_as in zip(methods, declared, strict=True):
            if _falls_back_to_a_bare_type(method, methods):
                continue
            method = _past_a_bare_type(method, methods)
            rendered = _rewritten(method, restriction, flavour, known, holder=protocol, returns_as=returns_as)
            # narrowed only to bind what the chain then hands back as `Any`: the rung under it says the same
            if _narrows_itself(method) and rendered.returns and ast.unparse(rendered.returns) == f"{flavour}[Any]":
                continue
            pieces = [one for one in _one_per_member(rendered, restriction) if ast.unparse(one) not in seen]
            if not pieces:
                continue
            seen.update(ast.unparse(one) for one in pieces)
            # a rung open to any chain would make every later one unreachable, so it goes to the end
            narrowed = restriction is not None or _narrows_itself(method)
            (found if narrowed else open_to_any).setdefault(method.name, []).extend(pieces)
            # the umbrella rung reads the declaration as written, since it is not the one a binding narrowed
            current = widest.get(method.name)
            if narrowed and (current is None or holders > current[0]):
                widest[method.name] = (holders, [written_as], protocol)
            elif (
                narrowed
                and current is not None
                and (holders, protocol) == (current[0], current[2])
                and all(written_as is not one for one in current[1])
            ):
                # an overload of the same declaration, which the umbrella needs whole; a second binding repeats it
                current[1].append(written_as)

    # the umbrella rung comes after the named ones, and is skipped where an open rung already covers the chain
    for name, (_holders, methods, protocol) in widest.items():
        if name in open_to_any:
            continue
        # the ordering six ask for an ordering, the restriction `_capable_typing` puts on the surface off the chain
        claimed = _RESTRICTED.get(name, "_Capable")
        if claimed == "_Callable" and any(
            ast.unparse(_own(one).annotation or ast.Name(id="")) == f"{flavour}[Callable[..., _P]]"
            and ast.unparse(one.returns or ast.Name(id="")).startswith(f"{_EXPECTING.get(flavour, flavour)}[")
            for one in found.get(name, [])
        ):
            # `_Callable` is `Callable[..., Any]` as a protocol, which the rung above takes already; beside it ty read
            # the two differing landings as ambiguous and answered `Unknown` for every polled `does_not_raise()`
            continue
        for method in methods:
            if _falls_back_to_a_bare_type(method, methods):
                continue
            method = _past_a_bare_type(method, methods)
            for asked in (claimed, "_CapableT"):
                rung = _rewritten(
                    method, f"{flavour}[{asked}]", flavour, known, holder=protocol, umbrella=True, returns_as=returns_as
                )
                if asked != "_Capable" or not _lands_elsewhere(rung, returns_as or flavour):
                    break
            # a restriction naming a type a rung above claims writes that rung twice, and pyright reports the overlap
            if ast.unparse(rung) not in seen:
                found[name].append(rung)
    for name, rungs in open_to_any.items():
        found.setdefault(name, []).extend(rungs)
    return found


def _none_stripped(flavour: str) -> ast.FunctionDef:
    """`is_not_none()` on a poll chain, as one rung taking `None` off whatever the probe returns.

    Rendered from the view's ladder, a list came back as `list | tuple | set | frozenset` of its items,
    the union the iterable view covers, and a pivot after it typed as `Any` under mypy and pyright, where
    the next ladder's first rung answered `list[str]` for a probe returning ints.
    """
    rung = ast.parse(f"def is_not_none(self: {flavour}[_T | None]) -> {flavour}[_T]: ...").body[0]
    return cast("ast.FunctionDef", rung)


def _body(known: dict[str, ast.ClassDef], flavour: str, returns_as: str | None = None) -> str:
    lines: list[str] = []
    by_name = _rungs(known, flavour, returns_as)
    if flavour in ("_SyncPoll", "_AsyncPoll"):
        by_name["is_not_none"] = [_none_stripped(flavour)]
    for rungs in by_name.values():
        lines.append("")
        for rendered in rungs:
            if len(rungs) > 1 and not any(ast.unparse(one) == "overload" for one in rendered.decorator_list):
                rendered.decorator_list.insert(0, ast.Name(id="overload"))
            elif len(rungs) == 1:
                # the one rung left of an overloaded declaration, whose fallback a chain does not carry
                rendered.decorator_list = [one for one in rendered.decorator_list if ast.unparse(one) != "overload"]
            lines.append("\n".join(f"        {line}" for line in ast.unparse(rendered).splitlines()))
    return "\n".join(lines)


_ABC_INDENT: Final = "    "
"""The mirrored modules declare their imports inside `if TYPE_CHECKING:`, so the line is written indented."""


def _abc_names(source: pathlib.Path) -> set[str]:
    """The `collections.abc` names one module imports."""
    line = next(
        one
        for one in source.read_text(encoding="utf-8").splitlines()
        if one.strip().startswith("from collections.abc import")
    )
    return {name.strip() for name in line.split("import ", 1)[1].split(",")}


def _abc_import() -> str:
    """The `collections.abc` import for a mirrored module, taken from both modules it is built from.

    The views alone were not enough.  A rung's ``self`` is the annotation an `assert_that()` overload is
    written with, and those live in the entry module, so a name reaching the body from there was emitted
    and never imported.  `Sequence` did exactly that, and every rung carrying it read as an undefined
    name in all 86 places at once.
    """
    names = sorted(_abc_names(VIEWS) | _abc_names(ENTRY) | {"Generator"})
    return f"{_ABC_INDENT}from collections.abc import " + ", ".join(names)


def _refusals() -> str:
    """The names a negated chain refuses, declared as a value that cannot be called.

    Read from `_operations.py` rather than listed here: a name is refused after `not_` when it is not an
    assertion, which is the same register the verdict twin drops.  `check` keeps its own refusal, whose
    reason is the poll and not the negation, and `builder`, `error` and `value` are not on a chain.
    """
    names = (NOT_AN_OPERATION | set(WITHOUT_A_VERDICT)) - {"builder", "check", "error", "value"}
    return "\n".join(f"        {name}: _NotAnAssertionToNegate" for name in sorted(names))


def generate() -> str:
    known = _classes(ast.parse(VIEWS.read_text(encoding="utf-8")))
    return _HEADER.format(
        imports=_IMPORTS.format(abc=_abc_import()),
        sync=_body(known, "_SyncPoll"),
        asynchronous=_body(known, "_AsyncPoll"),
        sync_negated=_body(known, "_NegatedSyncPoll", returns_as="_SyncPoll"),
        asynchronous_negated=_body(known, "_NegatedAsyncPoll", returns_as="_AsyncPoll"),
        refusals=_refusals(),
        landings=_landings(),
    )


_PIVOTS_OF_A_LANDING: Final = {
    "Invoked": (
        "        def raised(self) -> {flavour}[{held}]: ...",
        *(
            f"        @overload\n        def {name}(self, ex: type[_Landed]) -> {{landing}}[_Landed]: ...\n"
            f"        @overload\n        def {name}(self, ex: {taken}) -> {{landing}}[BaseException]: ..."
            for name, taken in (("caused_by", "ClassInfo"), ("has_root_cause", "ClassInfo"), ("error_of", "type"))
        ),
        "        def errors(self) -> {flavour}[list[BaseException]]: ...",
    ),
    "Warned": ("        def returned(self) -> {flavour}[{held}]: ...",),
    "Completed": ("        def returned(self) -> {flavour}[{held}]: ...",),
}
"""What each landing adds to the value it holds, declared: the hook would answer it over that value."""


def _landings() -> str:
    """The chains a call lands on, one per landing view and flavour, each with its negation.

    The assertions come off the hook and hand the landing back, so `raised()` after `contains()` still
    reaches the exception; only what the landing view adds is declared.  Awaited, a landing hands back
    the view itself.  The awaitable invoked landing is invariant in the exception, as that view is.
    """
    shapes = {
        "Invoked": ("str", "_InvokedAssertion"),
        "Warned": ("str", "_WarnedAssertion"),
        "Completed": ("Callable[..., {held}]", "_CompletedAssertion"),
    }
    blocks = []
    for flavour in ("_SyncPoll", "_AsyncPoll"):
        for kind, (value, view) in shapes.items():
            held = (
                "_Exc"
                if (kind == "Invoked" and flavour == "_AsyncPoll")
                else ("_Exc_co" if kind == "Invoked" else "_R_co")
            )
            landing, negated = f"{flavour}{kind}", f"_Negated{flavour[1:]}{kind}"
            shown = value.format(held=held)
            knobs = [
                f"        def within(self, timeout: float) -> {{same}}[{held}]: ...",
                f"        def every(self, interval: float) -> {{same}}[{held}]: ...",
                f"        def ignoring(self, *exceptions: type[Exception] | RetriedInfo) -> {{same}}[{held}]: ...",
            ]
            if flavour == "_AsyncPoll":
                knobs.append("        def close(self) -> None: ...")
                reading = [f"        def __await__(self) -> Generator[Any, None, {view}[{held}]]: ..."]
            else:
                reading = ["        @property", f"        def val(self) -> {shown}: ..."]
            pivots = [one.format(flavour=flavour, held=held, landing=landing) for one in _PIVOTS_OF_A_LANDING[kind]]
            blocks.append(
                "\n".join(
                    [
                        f"    class {landing}(Protocol[{held}]):",
                        f'        """Where the call lands, `{view}` over a probe polled again."""',
                        "",
                        *(one.format(same=landing) for one in knobs),
                        "        @property",
                        f"        def not_(self) -> {negated}[{held}]: ...",
                        *reading,
                        "        check: _NoVerdictAfterAPoll",
                        "        value: _NoValueOnAChain",
                        "        when_called_with: _NoExpectationOnAChain",
                        *pivots,
                        f"        def __getattr__(self, name: str) -> Callable[..., {landing}[{held}]]: ...",
                        "",
                        f"    class {negated}(Protocol[{held}]):",
                        f'        """`not_` after the call: the assertion after it hands back `{landing}`."""',
                        "",
                        *(one.format(same=negated) for one in knobs),
                        *reading,
                        "        check: _NoVerdictAfterAPoll",
                        _refusals(),
                        f"        def __getattr__(self, name: str) -> Callable[..., {landing}[{held}]]: ...",
                    ]
                )
            )
    return "\n\n" + "\n\n".join(blocks)


def generate_verdict() -> str:
    known = _classes(ast.parse(VIEWS.read_text(encoding="utf-8")))
    matchers = "    from ..matchers import Matcher"
    imports = _IMPORTS.format(abc=_abc_import()).replace(
        matchers, matchers + "\n    from ..outcome import AssertionOutcome"
    )
    # every rung of this twin hands back a verdict, so none keeps the type variable
    imports = imports.replace("        _CapableT,\n", "")
    return _VERDICT_HEADER.format(imports=imports, body=_body(known, _VERDICT))


_VERDICT_HEADER = '''"""The verdict twin of a value the builder holds.

Generated by `scripts/generate_poll_protocols.py`; do not edit.  `check()` on a typed view hands back
that view's own twin.  This is the one a value reaches through the builder, which is where an element
pivot and the capability umbrella both land.

Flat and self-dispatched for the same measured reason the polling twins are: overloading `check()` on
the builder's own type variable put an `AssertionBuilder[Any]` on the first rung, and every chain built
from a payload typed `dict[str, Any]` then read as a string.  A rung per assertion inverts that.

A name nobody declares stays open, because `__getattr__` answers it: a dynamic assertion is resolved
from the value's own attributes and reaches this proxy too.

`val` and `value` are declared, and not only because the proxy hands the value back under them.  They
hand the protocol's parameter out directly, where `not_` names it only through the protocol itself.
Measured on a protocol of two members: with `not_` alone ty takes the twin over a number for the twin
over a text, so no restriction on ``self`` was read and a text verdict asked of a number was taken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
{imports}

    class _CheckAnyValue(Protocol[_P_co]):
        """The verdict surface of a value reached through the builder rather than through a view."""

        @property
        def not_(self) -> _CheckAnyValue[_P_co]: ...
        @property
        def val(self) -> _P_co: ...
        @property
        def value(self) -> _P_co: ...
        def __getattr__(self, name: str) -> Callable[..., AssertionOutcome]: ...
{body}
'''


_CAPABLE = "_CapableAssertion"

_ASKS_A_SHAPE: Final = {
    # ordering reaches `_engine._ordering.compare`, which orders with `<`. Measured one operator at a time,
    # `__lt__` was the only one any of the six ran with, so keying on `__gt__` would refuse a working type
    "is_positive": "_Orderable",
    "is_negative": "_Orderable",
    "is_greater_than": "_Orderable",
    "is_greater_than_or_equal_to": "_Orderable",
    "is_less_than": "_Orderable",
    "is_less_than_or_equal_to": "_Orderable",
    # the dict family, split three ways because the necessity is: measured one capability at a time, the
    # key pair reads `keys()` and the walk, entries add the lookup, and values add `values()`
    "contains_key": "_Keyed",
    "does_not_contain_key": "_Keyed",
    "contains_entry": "_KeyedWithItems",
    "does_not_contain_entry": "_KeyedWithItems",
    "contains_value": "_KeyedWithValues",
    "does_not_contain_value": "_KeyedWithValues",
    # a chain polls what its probe hands back, so a second poll asks that value to be callable
    "eventually": "_Callable",
    "eventually_sync": "_Callable",
    # the filesystem: a `str` never reaches here, the string overload being above, so `__fspath__` is what is left
    "exists": "_PathLike",
    "does_not_exist": "_PathLike",
    "is_file": "_PathLike",
    "is_directory": "_PathLike",
    "is_named": "_PathLike",
    "is_child_of": "_PathLike",
    "is_readable": "_PathLike",
    "is_writable": "_PathLike",
    "is_executable": "_PathLike",
    # converting is necessary for these and for no other numeric: measured across eight shapes, a registered
    # number that converts to neither raises here and runs the five that stay open.  `SupportsFloat` alone
    # was wrong, `math.isnan` falling back to `__index__`, and closeness reads no ordering off the subject:
    # a bound that compares back runs it with nothing but the conversion
    "is_nan": "SupportsFloat | SupportsIndex",
    "is_not_nan": "SupportsFloat | SupportsIndex",
    "is_inf": "SupportsFloat | SupportsIndex",
    "is_not_inf": "SupportsFloat | SupportsIndex",
    "is_close_to": "SupportsFloat | SupportsIndex",
    # the one member whose operands are the value's own elements: bound off the receiver, the umbrella rung
    # reads them from it instead of leaving them open, and a polled string stops taking a number.  Both
    # ways of being a sequence, since `list(value)` walks either and refusing the older one refused a
    # value that runs
    "contains_in_order": "Iterable[_E] | _Indexed[_E]",
    # the call is structural, and the callable view sits below the umbrella, so this is the only description
    "raises": "_Callable",
    "does_not_raise": "_Callable",
    "warns": "_Callable",
    "does_not_warn": "_Callable",
    "when_called_with": "_Callable",
}
"""What each of these asks the value for: a capability it can carry, keyed on what the runtime reads.

Measured one capability at a time, because four separate readings were wrong when the fixture was
missing the one thing the assertion reached for: `is_positive` looks like `__gt__` and is held by
`__lt__`, `is_between` refuses a number that cannot be ordered, and `when_called_with()` refuses
everything until `raises()` has been called before it.
"""

_ASKS_A_TYPE: Final = {
    # whole numbers: a plain `isinstance` rather than the numeric family's registration. The rung above
    # claims `int | float`, so pyright reports the overlap; a wider key would let a float through
    "is_even": "int",
    "is_odd": "int",
    "is_divisible_by": "int",
    # text: `isinstance(val, str)`
    "matches": "str",
    "does_not_match": "str",
    "is_upper": "str",
    "is_lower": "str",
    "is_alpha": "str",
    "is_digit": "str",
    "is_alphanumeric": "str",
    "is_whitespace": "str",
    "is_equal_to_ignoring_case": "str",
    "is_equal_to_ignoring_whitespace": "str",
    "starts_with_ignoring_case": "str",
    "ends_with_ignoring_case": "str",
    "matches_with_groups": "str",
    "extracting_group": "str",
    # dates: `isinstance(val, datetime.datetime)`, and exactly that rather than `date`
    "is_before": "datetime.datetime",
    "is_after": "datetime.datetime",
    "is_before_or_equal_to": "datetime.datetime",
    "is_after_or_equal_to": "datetime.datetime",
    "is_equal_to_ignoring_time": "datetime.datetime",
    "is_equal_to_ignoring_seconds": "datetime.datetime",
    "is_equal_to_ignoring_milliseconds": "datetime.datetime",
    # bytes: `isinstance(val, (bytes, bytearray))`
    "is_hex_equal_to": "bytes | bytearray",
    "is_valid_utf8": "bytes | bytearray",
    "is_valid_encoding": "bytes | bytearray",
    "contains_bytes": "bytes | bytearray",
    "starts_with_bytes": "bytes | bytearray",
    "has_byte_at": "bytes | bytearray",
    "decoded_as": "bytes | bytearray",
}
"""Asked of a type no value reaching the umbrella can be, because each of those has an overload above it.

Declared rather than left out, and that distinction is the whole of it: an assertion the façade does not
declare is answered by `__getattr__` and refuses nothing.  Measured that way first, and text, dates and
bytes all still type-checked on a capable value until the rung was written.
"""

_RESTRICTED: Final = _ASKS_A_SHAPE | _ASKS_A_TYPE
"""Every rung the façade narrows, and what it asks the value for.

Five of the ten numeric assertions are still open, and the split between them was measured rather than
assumed.  All ten sit behind `isinstance(val, numbers.Number)`, a gate a class earns by registration
that no checker can read, so the question for each is whether a capability is *necessary* on top of it.
For `is_nan`, `is_not_nan`, `is_inf`, `is_not_inf` and `is_close_to` converting is: they reach
`math.isnan`, which reads `__float__` and falls back to `__index__`, so both halves are in the key.
For the other five nothing is: `is_zero` and `is_not_zero` ask only for `__eq__` with zero, and
`is_between`, `is_not_between` and `is_not_close_to` order the pair, which needs an ordering on either
side.  Measured on a registered subject carrying neither an ordering nor a conversion: all three run once
the bounds compare back, so keying them on `__le__` would refuse a call that runs.

Necessary, not sufficient, and the rung claims no more: a value that converts but never registered
still type-checks here and raises, because registration is what no checker can see.  What the rung buys
is the other direction, a value that cannot convert refused before the run.
"""


_BY_HAND: Final = frozenset(
    {
        "is_not_none",
        "is_instance_of",
        "is_instance_of_any",
        "first",
        "last",
        "element",
        "mapped",
        "single",
        "satisfies",
        "eventually",
        "eventually_sync",
        "builder",
        "error",
        "check",
        "raises",
        "does_not_raise",
        "warns",
        "does_not_warn",
        "when_called_with",
    }
)
"""Declared in the header instead, because the builder declares each of them as a ladder for checkers.

Flattened to the mixin's own signature they would lose what the ladder buys: the narrowing out of
`None`, the narrowing to a checked class, and the key type a pivot lands on.

The call family is here for the other reason a signature misleads: each is written `-> Self`, and the call
it waits for hands back the message or the result.  Flattened, `raises().when_called_with().matches()` was
refused on an enum class that runs it.
"""

_PIVOTS: Final = {name for name, kind in WITHOUT_A_VERDICT.items() if kind == TRANSFORMS} | ALSO_ASSERTS
"""Every operation handing back a value other than the subject, as `tests/test_operation_contract.py` derives it.

Most are written `-> Self` in the runtime, which says the subject comes back.  A flattened one says what
it hands back as `AssertionBuilder[Any]` instead: honest where the runtime names nothing better, and a
runtime that does, like `decoded_as_json()`, is kept as written.
"""

_LANDS_ON_A_LIST: Final = frozenset({"extracting", "filtered_on", "flat_mapped"})
"""The pivots a value the umbrella claims can answer, each handing back a list, as the collection views say.

On the open builder, `extracting().decoded_as()` type-checked and the list refused it.  Every other pivot
refuses such a value before handing anything back, so where it would land decides nothing.
"""


def _builder_surface() -> list[ast.FunctionDef]:
    """Every public assertion the builder carries, read from the mixins it is composed of.

    Read from the runtime rather than from the views, because the façade replaces the *builder* in one
    overload and has to offer what the builder offers.  Taking the views instead would narrow by
    accident: a view carries what one value type answers, and the value this stands in for is the one
    the library recognised without being able to name.
    """
    found: dict[str, ast.FunctionDef] = {}
    for path in sorted((ROOT / "assertpy").glob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Mixin"):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                    if item.name in _BY_HAND:
                        continue
                    found.setdefault(item.name, item)
    return [found[name] for name in sorted(found)]


def _capable_declaration(node: ast.FunctionDef) -> str:
    """One method of the façade: the runtime's own signature, with the body and the docstring gone."""
    rendered = ast.parse(ast.unparse(node)).body[0]
    if not isinstance(rendered, ast.FunctionDef):  # pragma: no cover - every entry here is a function
        raise TypeError(node.name)
    rendered.decorator_list = []
    rendered.body = [ast.Expr(value=ast.Constant(value=...))]
    # every default becomes `...`: copied verbatim they name things living only in the mixin, like `_UNSET`
    elided = [ast.Constant(value=...) for _ in rendered.args.defaults]
    rendered.args.defaults = elided
    rendered.args.kw_defaults = [None if one is None else ast.Constant(value=...) for one in rendered.args.kw_defaults]
    claims_the_subject = rendered.returns is not None and ast.unparse(rendered.returns) == "Self"
    if node.name in _RESTRICTED:
        asked = _RESTRICTED[node.name]
        rendered.args.args[0].annotation = ast.parse(f"{_CAPABLE}[{asked}]", mode="eval").body
        # `Self` needs an unannotated receiver, so a restricted rung has to name what it hands back
        if claims_the_subject:
            rendered.returns = ast.parse(f"{_CAPABLE}[_CapableT_co]", mode="eval").body
    if node.name in _PIVOTS and claims_the_subject:
        landing = "_ListAssertion[Any]" if node.name in _LANDS_ON_A_LIST else "AssertionBuilder[Any]"
        rendered.returns = ast.parse(landing, mode="eval").body
    return ast.unparse(rendered)


def generate_capable() -> str:
    body = "\n".join(
        "\n".join(f"        {line}" for line in _capable_declaration(node).splitlines()) for node in _builder_surface()
    )
    # rendered twice: the twin is read off the finished facade, whose ladders live in the header itself
    return _CAPABLE_HEADER.format(body=body, negated=_negated_capable(_CAPABLE_HEADER.format(body=body, negated="")))


_CAPABLE_HEADER = '''"""The surface of a value the capability umbrella claims.

Generated by `scripts/generate_poll_protocols.py`.

Do not edit.  `assert_that()` hands this back for a value that answers to some capability and to no
overload by name: a model, a dataclass, an HTTP response, a container of one\'s own.  It offers what the
builder offers, because that is what such a value used to get and none of it can be taken away without
refusing a call that runs.

What it exists to add is one restriction.  The six ordering assertions read the value with an ordering,
so a builder over a value that has none is not one they can be asked of.  Before this,
`assert_that(a_mapping).is_positive()` type-checked on ty, mypy and Pyright, the three gated then, and raised
ran.

A protocol rather than a subclass of the builder: narrowing ``self`` in a subclass is an invalid
override, measured on ty, and the working precedents that narrow it all end in a rung open to anything,
which is what a refusal cannot have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    import logging
    import re
    from collections.abc import Callable, Collection, Hashable, Iterable, Mapping, Sized
    from pathlib import Path
    from typing import Any, Protocol, SupportsFloat, SupportsIndex, TypeVar, overload

    from typing_extensions import TypeIs

    from .._matcher_impls import ClassInfo, ExceptionInfo, RetriedInfo, WarningInfo
    from ..assertpy import AssertionBuilder
    from ..matchers import Matcher
    from ._builder_check_typing import _CheckAnyValue
    from ._compat import Self
    from ._poll_typing import _AsyncPoll, _NoExpectationOnAChain, _SyncPoll
    from ._typing import (
        _E,
        _K,
        _R,
        _U,
        _V,
        _ExpectedCompletionAssertion,
        _ExpectedRaiseAssertion,
        _Landed,
        _ExpectedWarningAssertion,
        _ListAssertion,
    )

    # covariant: the façade only ever hands the subject back, through `value`
    _CapableT_co = TypeVar("_CapableT_co", covariant=True)
    _U2 = TypeVar("_U2")
    _U3 = TypeVar("_U3")
    _E_co = TypeVar("_E_co", covariant=True)

    class _Orderable(Protocol):
        """A value with an ordering, which is all the relational assertions ask of one."""

        def __lt__(self, other: Any, /) -> Any: ...

    class _Indexed(Protocol[_E_co]):
        """The older way to be a sequence: integer lookup that stops with `IndexError`, and no `__iter__`.

        `list(value)` accepts it, so `contains_in_order()` runs on it, and asking only for `Iterable`
        refused a value that works.

        One shape gets through that the runtime refuses, and it cannot be spelled out of: a class with
        this lookup and ``__iter__ = None`` disables the fallback, so `list(value)` raises while this
        still matches.  Structural typing has no way to ask for the absence of a member, and the
        direction is the safe one: the call is accepted here and refused with "val must be iterable"
        when it runs, which is what every other umbrella rung already does.
        """

        def __getitem__(self, index: int, /) -> _E_co: ...

    class _Keyed(Protocol):
        """`keys()`, which the dict gate reads before anything else.

        Iterability is read too and is deliberately NOT here: the gate asks
        `isinstance(value, collections.abc.Iterable)`, which a class earns by registration, and
        requiring `__iter__` structurally refused a registered value that runs.  Same blind spot as
        `numbers.Number` in the numeric family, and the same answer.
        """

        def keys(self) -> Any: ...

    class _KeyedWithItems(_Keyed, Protocol):
        """And a lookup, which reading an entry needs and reading a key does not."""

        def __getitem__(self, key: Any, /) -> Any: ...

    class _KeyedWithValues(_Keyed, Protocol):
        """And the values, which only the value pair reads.  A lookup is not enough: measured on a
        subject carrying `keys` and `__getitem__`, `contains_value` still refuses."""

        def values(self) -> Any: ...

    class _PathLike(Protocol):
        """A value the filesystem assertions can read a path out of, spelled as `os.PathLike` spells it."""

        def __fspath__(self) -> Any: ...

    class _Callable(Protocol):
        """A value the exception and warning assertions can call, which is what `callable()` asks."""

        def __call__(self, *args: Any, **kwargs: Any) -> Any: ...

    class _ElementSource(Protocol[_E_co]):
        """Anything whose value can be walked for `_E_co`, spelled the way the builder spells it.

        `Iterable` and not `Collection`: a value with only `__iter__` fell through to the `Self` overload,
        so `first()` kept the container's type after the value had become an element.
        """

        @property
        def value(self) -> Iterable[_E_co]: ...

    class _CapableAssertion(Protocol[_CapableT_co]):
        """What a value the umbrella claims can be asked."""

        # the data the builder carries: absent from `dir()`, so `__getattr__` read `description` as a callable
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | ExceptionInfo | None
        logger: logging.LoggerAdapter[Any]

        @property
        def value(self) -> _CapableT_co: ...
        @property
        def not_(self) -> _NegatedCapableAssertion[_CapableT_co]: ...
        def __getattr__(self, name: str) -> Callable[..., Self]: ...

        # the builder's ladders, carried across: a narrowing lost here is lost for every value the umbrella claims
        @overload
        def is_not_none(self: _CapableAssertion[_U | None]) -> _CapableAssertion[_U]: ...
        @overload
        def is_not_none(self) -> Self: ...
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
        @overload
        def is_instance_of_any(self, first: type[_U], second: type[_U2], /) -> AssertionBuilder[_U | _U2]: ...
        @overload
        def is_instance_of_any(
            self, first: type[_U], second: type[_U2], third: type[_U3], /
        ) -> AssertionBuilder[_U | _U2 | _U3]: ...
        @overload
        def is_instance_of_any(self, *some_classes: ClassInfo) -> Self: ...
        @overload
        def first(self: _CapableAssertion[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def first(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def first(self) -> Self: ...
        @overload
        def last(self: _CapableAssertion[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def last(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def last(self) -> Self: ...
        @overload
        def element(self: _CapableAssertion[Mapping[_K, _V]], index: SupportsIndex) -> AssertionBuilder[_K]: ...
        @overload
        def element(self: _ElementSource[_E], index: SupportsIndex) -> AssertionBuilder[_E]: ...
        @overload
        def element(self, index: SupportsIndex) -> Self: ...
        @overload
        def mapped(self: _ElementSource[_E], func: Callable[[_E], _R]) -> AssertionBuilder[list[_R]]: ...
        @overload
        def mapped(self, func: Callable[..., Any]) -> Self: ...
        @overload
        def single(self: _CapableAssertion[Mapping[_K, _V]]) -> AssertionBuilder[_K]: ...
        @overload
        def single(self: _ElementSource[_E]) -> AssertionBuilder[_E]: ...
        @overload
        def single(self) -> Self: ...
        @overload
        def satisfies(self, matcher: Callable[[Any], TypeIs[_U]]) -> AssertionBuilder[_U]: ...
        @overload
        def satisfies(self, matcher: Matcher[Any] | Callable[..., bool]) -> Self: ...
        # the polling pivots, over `Any`: no capability says the value is callable, so the chain keeps every rung open
        def eventually(
            self,
            *,
            timeout: float = ...,
            interval: float = ...,
            ignoring: type[Exception] | RetriedInfo = ...,
            trace: bool = ...,
        ) -> _AsyncPoll[Any]: ...
        def eventually_sync(
            self,
            *,
            timeout: float = ...,
            interval: float = ...,
            ignoring: type[Exception] | RetriedInfo = ...,
            trace: bool = ...,
        ) -> _SyncPoll[Any]: ...
        # where the callable view lands: flattened, the runtime's `-> Self` kept a caught message typed as the callable
        @overload
        def raises(self: _CapableAssertion[_Callable], ex: type[_Landed]) -> _ExpectedRaiseAssertion[Any, _Landed]: ...
        @overload
        def raises(
            self: _CapableAssertion[_Callable], ex: type | ExceptionInfo
        ) -> _ExpectedRaiseAssertion[Any, BaseException]: ...
        def does_not_raise(
            self: _CapableAssertion[_Callable], ex: type | ExceptionInfo
        ) -> _ExpectedCompletionAssertion[Any]: ...
        def warns(
            self: _CapableAssertion[_Callable], warning: type[Warning] | WarningInfo = ...
        ) -> _ExpectedWarningAssertion[Any]: ...
        def does_not_warn(
            self: _CapableAssertion[_Callable], warning: type[Warning] | WarningInfo = ...
        ) -> _ExpectedCompletionAssertion[Any]: ...
        when_called_with: _NoExpectationOnAChain
        # the builder's own helpers: left to `__getattr__`, `builder()` read as this facade over the value already here
        def builder(
            self,
            val: Any,
            description: str = ...,
            kind: str | None = ...,
            expected: Any = ...,
            logger: Any = ...,
            origin: Any = ...,
        ) -> AssertionBuilder[Any]: ...
        def error(
            self,
            msg: str,
            *,
            actual: Any = ...,
            expected: Any = ...,
            diff: Any = ...,
            trace: Any = ...,
            suppress_context: bool = ...,
        ) -> Self: ...
        def check(self) -> _CheckAnyValue[_CapableT_co]: ...
{body}

{negated}
'''


_NEGATED_HEADER = '''"""The negation twin of every assertion protocol.

Generated by `scripts/generate_poll_protocols.py`.

Do not edit.  `not_` on a view hands one of these back, and every assertion on it hands the view back:
`NegatedBuilder` inverts one assertion and returns the builder it wrapped, so the type has to say
`positive -> negated -> positive` rather than making the negation permanent.

The narrowing ladders are absent by construction.  A negated `is_instance_of(str)` asserts the value is
*not* a string, so answering the string view promises the opposite of what was checked: that shipped,
typed an `int` as `str`, and all four checkers accepted it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
{imports}

{body}'''


def _negated_method(node: ast.FunctionDef, holder: str, negated: str) -> ast.FunctionDef:
    """The same signature, with any restricted `self` rebound to the twin and the view handed back."""
    copied = ast.parse(ast.unparse(node)).body[0]
    assert isinstance(copied, ast.FunctionDef)
    own = (copied.args.posonlyargs or copied.args.args)[0]
    if own.annotation is not None:
        inner = ast.unparse(own.annotation)
        own.annotation = ast.Name(id=f"{negated}[{inner[inner.index('[') + 1 : -1]}]" if "[" in inner else negated)
    copied.returns = ast.Name(id=holder)
    copied.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
    copied.decorator_list = []
    return copied


def _view_parameters(node: ast.ClassDef) -> str | None:
    for base in node.bases:
        rendered = ast.unparse(base)
        if rendered.startswith("Protocol["):
            return rendered[len("Protocol[") : -1]
    return None


def _reachable(known: dict[str, ast.ClassDef]) -> list[str]:
    """Every view a chain can end on, not only the ones `assert_that` hands back directly.

    A pivot, a narrowing or a call reaches a view no overload names, and a twin set built from the
    entry views alone left `_InvokedAssertion` behind: a negated `satisfies` there typed a caught
    message as an `int` and returned the string.
    """
    found: list[str] = []
    pending = []
    for _value, view in _dispatch():
        name = view.split("[")[0]
        if name in known and name not in found:
            found.append(name)
            pending.append(name)
    while pending:
        for protocol in _lineage(pending.pop(), known):
            for node in ast.walk(known[protocol]):
                if not isinstance(node, ast.FunctionDef) or node.returns is None:
                    continue
                for word in re.findall(r"_\w*Assertion", ast.unparse(node.returns)):
                    if word in known and word not in found:
                        found.append(word)
                        pending.append(word)
    return found


def _own(node: ast.AST) -> ast.arg:
    """The receiver of a declaration, wherever it is written."""
    if not isinstance(node, ast.FunctionDef):  # pragma: no cover - every caller parses one declaration
        raise TypeError(type(node).__name__)
    return (node.args.posonlyargs or node.args.args)[0]


def _surviving(rendered: list[str]) -> list[str]:
    """Drop a rung a wider one already accepts.

    Positively, `is_not_none()` restricts ``self`` to say which view it narrows to.  Negated there is
    nothing to narrow, both rungs answer the same view, and pyright read the pair as overlapping.
    """
    wide = {one for one in rendered if _own(ast.parse(one).body[0]).annotation is None}
    keep = []
    for one in rendered:
        node = ast.parse(one).body[0]
        own = _own(node)
        if own.annotation is not None:
            own.annotation = None
            if ast.unparse(node) in wide:
                continue
        keep.append(one)
    return keep


class _Substituted(ast.NodeTransformer):
    """Rewrite the type parameters a base was reached by into the arguments it was given."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.expr:
        written = self.mapping.get(node.id)
        return ast.parse(written, mode="eval").body if written else node


def _bound(name: str, known: dict[str, ast.ClassDef]) -> list[tuple[str, dict[str, str]]]:
    """*name* and every protocol above it, each with the arguments the path down to it gave.

    `_TextAssertion` inherits `_RepeatableAssertion[str]`, so its `contains_in_order` takes `str`.
    Copied without the substitution the twin kept a free `_E`, and `not_.contains_in_order(1)`
    type-checked on all four checkers where the positive method is refused by three.
    """
    found: list[tuple[str, dict[str, str]]] = []
    pending = [(name, {})]
    while pending:
        protocol, mapping = pending.pop(0)
        if protocol not in known or any(protocol == one for one, _ in found):
            continue
        found.append((protocol, mapping))
        for base in known[protocol].bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if not isinstance(target, ast.Name) or target.id not in known:
                continue
            asked = _view_parameters(known[target.id])
            if not isinstance(base, ast.Subscript) or asked is None:
                pending.append((target.id, {}))
                continue
            given = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
            written = [ast.unparse(_Substituted(mapping).visit(_copied(one))) for one in given]
            pending.append((target.id, dict(zip([one.strip() for one in asked.split(",")], written, strict=True))))
    return found


def _copied(node: ast.AST) -> ast.AST:
    """A detached copy, since the transformer rewrites in place."""
    return ast.parse(ast.unparse(node), mode="eval").body


def generate_negated() -> str:
    """A twin per reachable view, carrying what `_operations.py` calls an assertion and nothing else."""
    known = _classes(ast.parse(VIEWS.read_text(encoding="utf-8")))
    ordered = _reachable(known)

    blocks, used = [], set()
    for view in ordered:
        parameters = _view_parameters(known[view])
        holder = f"{view}[{parameters}]" if parameters else view
        negated = f"_Negated{view[1:]}"
        # every rung, not the widest: the narrow ones differ in what they accept, and a twin that
        # kept one of them would refuse operands the positive method takes
        rungs: dict[str, list[ast.FunctionDef]] = {}
        owner: dict[str, str] = {}
        for protocol, mapping in _bound(view, known):
            for item in known[protocol].body:
                if not isinstance(item, ast.FunctionDef):
                    continue
                if item.name.startswith("_") or item.name in _SKIP_FOR_A_VERDICT or _refines(item):
                    continue
                if any(ast.unparse(one) == "property" for one in item.decorator_list):
                    continue
                if owner.setdefault(item.name, protocol) != protocol:
                    continue
                declared = ast.parse(ast.unparse(item)).body[0]
                if not isinstance(declared, ast.FunctionDef):  # pragma: no cover - one declaration in, one out
                    raise TypeError(item.name)
                rungs.setdefault(item.name, []).append(_Substituted(mapping).visit(declared))
        methods = []
        for found in rungs.values():
            rendered: list[str] = []
            for item in found:
                one = ast.unparse(_negated_method(item, holder, negated))
                if one not in rendered:
                    rendered.append(one)
            rendered = _surviving(rendered)
            for one in rendered:
                prefix = "        @overload\n" if len(rendered) > 1 else ""
                methods.append(prefix + "\n".join(f"        {line}" for line in one.splitlines()))
        if not methods:
            continue
        used.add(view)
        opener = f"    class {negated}(Protocol[{parameters}]):" if parameters else f"    class {negated}(Protocol):"
        head = [opener, f'        """The negation twin of `{view}`."""', ""]
        blocks.append("\n".join(head + methods))

    imports = _IMPORTS.format(abc=_abc_import())
    imports += "\n" + "\n".join(f"    from ._typing import {name}" for name in sorted(used))
    return _NEGATED_HEADER.format(imports=imports, body="\n\n".join(blocks))


def _negated_capable(rendered: str) -> str:
    """The facade's twin, built from what the facade itself declares rather than shaped by hand.

    Not a subclass: inheriting the facade brought `described_as`, `__getattr__` and every `Self` back,
    so `not_.described_as("x")` type-checked while `NegatedBuilder` refused it.

    Read off the finished module rather than the generated body, because the four narrowing ladders are
    written in the header and a twin built from the body alone refused `not_.is_instance_of(str)`.
    """
    facade = next(
        node for node in ast.walk(ast.parse(rendered)) if isinstance(node, ast.ClassDef) and node.name == _CAPABLE
    )
    holder = f"{_CAPABLE}[_CapableT_co]"
    rungs: dict[str, list[str]] = {}
    for item in facade.body:
        if not isinstance(item, ast.FunctionDef) or item.name.startswith("_"):
            continue
        if item.name in _SKIP_FOR_A_VERDICT or _refines(item):
            continue
        if any(ast.unparse(one) == "property" for one in item.decorator_list):
            continue
        copied = ast.parse(ast.unparse(item)).body[0]
        assert isinstance(copied, ast.FunctionDef)
        own = _own(copied)
        if own.annotation is not None:
            inner = ast.unparse(own.annotation)
            own.annotation = ast.Name(id=f"_NegatedCapableAssertion[{inner[inner.index('[') + 1 : -1]}]")
        copied.returns = ast.Name(id=holder)
        copied.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
        copied.decorator_list = []
        rendered = ast.unparse(copied)
        if rendered not in rungs.setdefault(item.name, []):
            rungs[item.name].append(rendered)

    methods = []
    for found in map(_surviving, rungs.values()):
        for one in found:
            prefix = "        @overload\n" if len(found) > 1 else ""
            methods.append(prefix + "\n".join(f"        {line}" for line in one.splitlines()))
    head = [
        "    class _NegatedCapableAssertion(Protocol[_CapableT_co]):",
        '        """The negation twin of the capability facade: one step, then it back."""',
        "",
    ]
    return chr(10).join(head + methods)


def _tidy(written: pathlib.Path) -> None:
    """Format and autofix a generated file, refusing to report success when either step failed.

    Swallowed, a missing `ruff` or a file that does not parse left the generator exiting zero, and the
    caller went on to re-record a snapshot from a file nothing had checked.
    """
    for command in (
        ["uv", "run", "ruff", "format", str(written)],
        ["uv", "run", "ruff", "check", "--fix", str(written)],
    ):
        finished = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
        if finished.returncode:
            print(finished.stdout, finished.stderr, sep="", file=sys.stderr)
            raise SystemExit(f"{' '.join(command[2:])} failed on {written.relative_to(ROOT)}")


if __name__ == "__main__":
    TARGET.write_text(generate(), encoding="utf-8", newline="")
    TARGET_VERDICT.write_text(generate_verdict(), encoding="utf-8", newline="")
    TARGET_CAPABLE.write_text(generate_capable(), encoding="utf-8", newline="")
    TARGET_NEGATED.write_text(generate_negated(), encoding="utf-8", newline="")
    for written in (TARGET, TARGET_VERDICT, TARGET_CAPABLE, TARGET_NEGATED):
        _tidy(written)
        print(f"wrote {written.relative_to(ROOT)}")
