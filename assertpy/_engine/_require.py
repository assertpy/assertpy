"""One shape for every refusal of a wrong type, and one place that decides how it reads.

An assertion refuses a value or an argument in two situations, and until now each site worded its own:
ninety-three different phrasings across a hundred and fifty-nine sites, for about ten actual
situations.  Ten of them said "not a number" and eleven said "not a string", differing in whether the
offending value appeared at all, whether its type did, and in what order.  The reader could not learn
the format once, because there was no format.

The shape here is::

    <subject> must be <expectation>, but was <value> (<type>)

`subject` is `val` for the value under assertion and `given <name> arg` for an argument, which is the
wording the package already used where it named the operand at all.  The value is shown because that is
the question a reader actually has: not *that* the type was wrong, but *what arrived* instead.  A
payload field that came back as the string ``"12"`` rather than the number ``12`` is invisible in
"val is not numeric" and obvious in ``but was <'12'> (str)``.

The type is printed next to the value even when `repr` already implies it.  `'12'` and `12` are told
apart by their quotes, but `Decimal("1")`, a numpy scalar and any class with a hand-written `__repr__`
are not, and a rule with an exception is a rule nobody can rely on.
"""

from __future__ import annotations

import decimal
import difflib
import functools
import inspect
import re
import types
from typing import Any, Final, NoReturn, TypeVar

from ..errors import _safe_repr, _truncated
from ._size import length_of

_T = TypeVar("_T")


def raised_on_purpose(excinfo: Any = None) -> bool:
    """Whether pytest hides a frame of the module that names this as its ``__tracebackhide__``.

    Only where the frame the exception was born in is a refusal of this library: one sets a name of its own,
    ``_assertpy_refusal``, where it raises, and then no frame of the library says anything of the mistake.
    Anything else keeps its frames, what the caller's code or another library raised, hidden by pytest's own
    flag or not, and a defect of this one, since they are what locate it.
    """
    try:
        last = excinfo.tb
        while last.tb_next is not None:
            last = last.tb_next
        return last.tb_frame.f_locals.get("_assertpy_refusal") is True
    except Exception:
        return True


__tracebackhide__ = raised_on_purpose

# a refusal is read on one terminal line, so the cap is well below the one a diff row uses
_SHOWN = 60


# a type name can be as long as its author liked, and the refusal is still one line
_NAMED = 40
# `repr` output is arbitrary text: escape sequences repaint the terminal, and newlines turn one refusal into several
_CONTROL = {code: "\\x{:02x}".format(code) for code in [*range(0x20), 0x7F, 0x85]} | {  # noqa: UP032  # an f-string cannot hold this escape
    # the bidi overrides reorder the printed line without changing the string
    code: "\\u{:04x}".format(code)  # noqa: UP032  # same
    for code in [0x2028, 0x2029, *range(0x202A, 0x2030), *range(0x2066, 0x206A)]
}


def _one_line(text: str) -> str:
    """*text* with control characters spelled out, so a refusal stays one readable line."""
    return text.translate(_CONTROL)


def _shown(value: object) -> str:
    """The value and its type, both capped, both safe to print next to a traceback.

    `_safe_repr` already answers `<unreprable X>` for a `__repr__` that raises, returns a non-string or
    recurses.  What it does not do is make the result printable: an object is free to return escape
    sequences or newlines from `__repr__`, and a diagnostic that repaints the terminal or spreads over
    four lines is worse than the mistake it reports.
    """
    # escaped before it is capped: capping first let sixty control characters render as two hundred and forty
    shown = _truncated(_one_line(_safe_repr(value)), _SHOWN)
    return f"<{shown}> ({_truncated(type(value).__name__, _NAMED)})"


def raised_inside(exc: BaseException) -> bool:
    """Whether *exc* came out of somebody else's code rather than from the operation itself.

    `len(42)` and `1 < "a"` are refusals by the operation: the traceback stops at the frame that tried
    it.  A `__len__` or a `__lt__` that raises `TypeError` of its own adds a frame, and that error is a
    bug in the value being tested, not a wrong operand.  Answering it with "val must be a sized object"
    is a lie that sends the reader looking in the wrong file, so those are re-raised untouched.

    A frame of `decimal` itself is the operation's own, where CPython was built without the C accelerator and
    runs it in Python (`pure_decimal_code`): the same refusal raised in C adds no frame at all.  Only when the
    method first called runs on a real `Decimal` or `Context`, since a class of anybody's can borrow one.
    """
    traceback = exc.__traceback__
    deeper = traceback.tb_next if traceback is not None else None
    if deeper is None:
        return False
    operation = pure_decimal_code()
    entry = deeper.tb_frame
    if entry.f_code not in operation or not isinstance(entry.f_locals.get("self"), (decimal.Decimal, decimal.Context)):
        return True
    while deeper is not None:
        if deeper.tb_frame.f_code not in operation:
            return True
        deeper = deeper.tb_next
    return False


@functools.cache
def pure_decimal_code() -> frozenset[types.CodeType]:
    """The code `decimal` runs in Python where CPython was built without its C accelerator, else nothing.

    Read once from the namespace `Decimal.__add__` was defined in, nested code included: the functions and the
    classes defined there, `Decimal` and `Context` among them, and not what it imported from elsewhere, such as
    `collections.namedtuple`.  That namespace is `_pydecimal`'s, whether `decimal` is that module itself, as on
    3.15, or re-exports its names, as below it, and it must hold the very `Decimal` in use.
    """
    added = inspect.getattr_static(decimal.Decimal, "__add__")
    if not isinstance(added, types.FunctionType) or added.__globals__.get("Decimal") is not decimal.Decimal:
        return frozenset()
    namespace = added.__globals__
    held = list(namespace.values())
    for kind in [one for one in held if isinstance(one, type) and one.__module__ == namespace.get("__name__")]:
        for member in vars(kind).values():
            held += [getattr(member, "__func__", member)]
            if isinstance(member, property):
                held += [member.fget, member.fset, member.fdel]
    pending = [
        function.__code__
        for function in held
        if isinstance(function, types.FunctionType) and function.__globals__ is namespace
    ]
    found: set[types.CodeType] = set()
    while pending:
        code = pending.pop()
        if code not in found:
            found.add(code)
            pending += [constant for constant in code.co_consts if isinstance(constant, types.CodeType)]
    return frozenset(found)


def refuse(value: object, expectation: str, *, subject: str = "val", note: str = "") -> NoReturn:
    """Raise the refusal for *value*, for a check the caller has already made, with *note* after it."""
    message = f"{subject} must be {expectation}, but was {_shown(value)}{note}"
    _assertpy_refusal = True
    raise TypeError(message)


def require_type(
    value: object, types: type[_T] | tuple[type[_T], ...], expectation: str, *, subject: str = "val"
) -> _T:
    """Refuse *value* unless it is an instance of *types*, which is what most of these checks are.

    The value is handed back so a caller can bind it and keep the narrowing: a type checker cannot see
    through a function that only raises, and the alternative at each site was a second `isinstance` or a
    cast written purely for the checker.
    """
    if not isinstance(value, types):
        refuse(value, expectation, subject=subject)
    return value


def argument(name: str) -> str:
    """The subject for an argument of the assertion, as opposed to the value under assertion."""
    return f"given {name} arg"


def require_pattern(pattern: object) -> re.Pattern[str]:
    """*pattern* compiled, refused unless it is a string or a pattern compiled from one, and not empty.

    A pattern compiled from bytes is never found in a string, and an empty one is found in every string.  A
    string goes through ``re.compile`` and its cache, as ``re.search`` would take it.  A compiled one comes back
    as it is, flags and all.
    """
    text = pattern.pattern if isinstance(pattern, re.Pattern) else pattern
    if not isinstance(text, str):
        refuse(pattern, "a string or a pattern compiled from one", subject=argument("pattern"))
    if len(text) == 0:
        _assertpy_refusal = True
        raise ValueError("given pattern arg must not be empty")
    return pattern if isinstance(pattern, re.Pattern) else re.compile(text)


def sized_len(value: object, *, subject: str = "val") -> int:
    """The length of *value*, refusing it in the shared shape when it has none.

    Left to `len()` alone, the refusal reads "object of type 'int' has no len()": true, and about the
    builtin rather than about the assertion, with no mention of which operand was wrong.
    """
    length = length_of(value)
    if length is None:
        refuse(value, "a sized object", subject=subject)
    # a `__len__` that exists and still raises is a bug in the value, and it travels out as its author wrote it
    return length


def reject_unknown_kwargs(kwargs: dict, known: frozenset, method: str) -> None:
    """Raise on a keyword the method does not read, naming the closest one it does.

    A misspelt option is the worst silent pass there is.  ``is_equal_to(other, strict_type=True)``
    returned green with the comparison never tightened, and nothing said so: no error, no warning, and
    no type error either, because a ``**kwargs`` signature makes every spelling legal to a checker.
    The reader is left certain they asserted something they did not.

    The matcher spelling of the same option already fails loudly, since a real parameter list gets
    this from the interpreter for free.  This gives the ``**kwargs`` entry points the same manners.
    """
    unknown = sorted(set(kwargs) - known)
    if not unknown:
        return
    named = []
    for name in unknown:
        # one suggestion, like the extraction hint: measured typos score ~0.9 and wrong neighbours ~0.65
        close = difflib.get_close_matches(str(name), sorted(known), n=1)
        named.append(f"{name!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
    plural = "" if len(named) == 1 else "s"
    message = f"{method}() got an unexpected keyword argument{plural} {', '.join(named)}"
    _assertpy_refusal = True
    raise TypeError(message)


class VerdictError(TypeError):
    """A predicate handed back something that is not an answer: a mistake in the test, not a non-match.

    Its own type because several assertions catch `TypeError` from a probe on purpose, reading it as
    "this one does not match", which is right for a predicate that cannot judge some item and wrong for
    one that was never asked: swallowed there, the refusal came back as an ordinary failed assertion.
    """


class CoroutineVerdictError(VerdictError):
    """A predicate handed back a coroutine, so nothing ever ran."""


class MatcherVerdictError(VerdictError):
    """A predicate handed back a matcher, so nothing was ever asked of the value."""


_MATCHER_MEMBERS: Final = ("matches", "describe", "describe_mismatch")

NON_MATCHER_TYPES: Final = frozenset(
    {int, float, bool, complex, str, bytes, bytearray, list, tuple, dict, set, frozenset, type(None)}
)
"""Types no matcher is, which is what an ordinary answer is: one frozenset lookup instead of three reads."""


def _answers_like_a_matcher(answer: object) -> bool:
    """Whether this object is a matcher by the only rule that matters: it has the three members.

    Read statically, wherever a matcher keeps its members: on the type, in the instance dictionary or in
    slots.  Never through `getattr`, which runs a `__getattr__`, a property or a metaclass hook: a `Mock`
    answers every name with something callable, and a hostile object could decide its own verdict.

    The frozenset first because the static read costs 1.08 us against 0.11 us for a plain `getattr`, and
    the answers that reach here are almost always an ordinary value of a builtin type.
    """
    if type(answer) in NON_MATCHER_TYPES:
        return False
    for member in _MATCHER_MEMBERS:
        held = inspect.getattr_static(answer, member, None)
        if isinstance(held, types.MemberDescriptorType):
            # a slot: its own `__get__` reads the value, which is a C-level read and not their code
            try:
                held = held.__get__(answer)
            except AttributeError:
                return False  # the slot was never filled
        if not callable(held):
            return False
    return True


def verdict(answer: object, *, subject: str = "predicate") -> object:
    """The answer a predicate gave, refusing what is not one rather than reading it as truth.

    A coroutine object is truthy, so an `async def` predicate passed every assertion that reads one
    without ever running: measured, ten of the thirteen places that take a callable went green on a
    predicate that always answers `False`.  A matcher is truthy the same way, so a factory that was
    named but never called, or a predicate written in matcher style, passed on any value at all.

    Asked of the answer rather than of the callable, so a lambda handing one back is caught too, and a
    coroutine is closed before raising so the refusal is not followed by "was never awaited".
    """
    if answer is True or answer is False:
        return answer
    # the exact type, since `inspect.iscoroutine` and even `isinstance` read attributes off the answer,
    # and a hostile `__getattribute__` then decides a failure that is not about it at all.  Nothing
    # subclasses a coroutine, so `is` asks the same question
    if type(answer) is types.CoroutineType:
        answer.close()
        message = (
            f"{subject} handed back a coroutine instead of an answer; assertions here are synchronous, "
            "so await the call yourself and assert on what it returned"
        )
        _assertpy_refusal = True
        raise CoroutineVerdictError(message)
    if _answers_like_a_matcher(answer):
        message = (
            f"{subject} handed back a matcher instead of an answer; pass the matcher where one is taken, "
            "or ask it about the value and answer with what it said"
        )
        _assertpy_refusal = True
        raise MatcherVerdictError(message)
    return answer
