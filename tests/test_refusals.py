"""Every refusal of a wrong type says the same kind of sentence, whichever assertion produced it.

A refusal is not an assertion failure: it means the test itself is wrong, and the reader is a developer
looking at their own call.  What that reader needs is which operand was rejected, what was expected of
it, and what arrived instead.  Ninety-three different phrasings across the package used to answer at
most two of the three, and which two depended on the assertion.

The gate drives every public assertion with operands of the wrong type and holds each `TypeError` to
one shape.  It is written as a sweep rather than as a list of cases on purpose: a list would be a
second place to remember, and a new assertion added next year would simply not be in it.
"""

from __future__ import annotations

import datetime
import inspect
import pathlib
import re
import warnings

import pytest

import assertpy
from assertpy import assert_that, match
from assertpy._engine._require import argument, refuse, require_type, sized_len

# `<subject> must be <expectation>, but was <value> (<type>)`
SHAPE = re.compile(r"^.+ must be .+, but was <.*> \(\w+\)$", re.DOTALL)

# refusals about the state of the chain rather than an operand, and worse for being squeezed into the shape
NOT_ABOUT_A_TYPE = (
    "no exception captured",
    "no expectation set",
    "no return value captured",
    "got an unexpected keyword argument",
    "missing 3 required positional arguments",
    "assertpy has no assertion",
)

_PACKAGE = pathlib.Path(assertpy.__file__).parent

WRONG_VALUES = [42, object(), None]
WRONG_OPERANDS = ["wrong", 42, object()]


def _public_assertions() -> list[str]:
    """Assertions the package itself ships, found by where each one is defined.

    `add_extension` registers globally and the registry outlives the test that filled it, so a sweep
    over the live builder also picks up assertions written in other test files, in whatever order the
    suite happened to run.  Those belong to their authors: the shape is a convention this package
    keeps and the guide recommends, not a rule imposed on extensions.
    """
    builder = assert_that(1)
    names = []
    for name in dir(builder):
        if name.startswith("_") or name == "error":
            continue
        method = getattr(builder, name, None)
        if callable(method) and getattr(method, "__module__", "").startswith("assertpy"):
            names.append(name)
    return names


def _arity(method: object) -> int:
    try:
        signature = inspect.signature(method)  # ty: ignore[no-matching-overload]  # any callable here
    except (TypeError, ValueError):  # pragma: no cover - builtins without a signature
        return 0
    return sum(
        1
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    )


def _bindable(method: object, args: tuple) -> bool:
    """Whether the call is even well-formed, so a signature error is never graded as a refusal."""
    try:
        inspect.signature(method).bind(*args)  # ty: ignore[no-matching-overload]  # any callable here
    except TypeError:
        return False
    return True


def _ours(exc: BaseException) -> bool:
    """Whether this package raised it, rather than a library the value belongs to.

    numpy answers an unusable operand with its own `TypeError`, and letting that through is deliberate:
    it says more about the array than a generic refusal could.  What it must not do is decide the gate
    by its wording.  That list used to carry two numpy phrasings, and on numpy 1.26 a third one appeared
    (`ufunc 'isfinite' not supported`), so the gate passed on one release of somebody else's library and
    failed on another while this package had not changed at all.

    The deepest frame is the one that raised, so the question is simply whose file it sits in.
    """
    frame = exc.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    if frame is None:
        return True
    return _PACKAGE in pathlib.Path(frame.tb_frame.f_code.co_filename).parents


def _refusals() -> list[tuple[str, str, int]]:
    """Every `TypeError` the sweep provokes, as (assertion, message, which operand was spoiled).

    One wrong operand at a time, each position in turn: an assertion with two constrained arguments
    (`is_between`, `is_close_to`) refuses on the first bad one, so spoiling them together would leave
    the later positions unexercised and their wording unchecked.
    """
    found = []
    for name in _public_assertions():
        method = getattr(assert_that(1), name)
        arity = _arity(method)
        for value in WRONG_VALUES:
            for role in range(max(arity, 1)):
                for operand in WRONG_OPERANDS:
                    # a plain int in the other positions: it is valid for the numeric and length
                    # assertions, which are the ones taking more than one constrained operand
                    args = tuple(operand if index == role else 1 for index in range(arity))
                    if not _bindable(method, args):
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        try:
                            getattr(assert_that(value), name)(*args)
                        except TypeError as exc:
                            if _ours(exc):
                                found.append((name, str(exc), role))
                        except Exception:
                            pass
    return found


@pytest.fixture(scope="module")
def refusals() -> list[tuple[str, str, int]]:
    """Collected once per module, inside a test rather than at import: extensions registered by other
    files come and go with the run order, and a value frozen at import time would depend on it."""
    return _refusals()


def test_the_sweep_actually_provokes_refusals(refusals):
    """Guards the gate itself: a sweep that stopped refusing anything would pass in silence."""
    assert_that(refusals).described_as("refusals provoked").is_not_empty()
    assert_that({name for name, _, _ in refusals}).described_as("assertions reached").is_not_empty()


def test_every_type_refusal_has_the_same_shape(refusals):
    off_shape = [
        (name, message)
        for name, message, _role in refusals
        if not SHAPE.match(message) and not any(marker in message for marker in NOT_ABOUT_A_TYPE)
    ]
    assert_that(off_shape).described_as("refusals not in the shared shape").is_empty()


def test_every_type_refusal_shows_the_value_it_rejected(refusals):
    """The part no old wording carried consistently, and the only one that answers "why".

    "val is not numeric" leaves the reader to find out which value arrived; a payload field that came
    back as the string "12" instead of the number 12 is invisible in it.
    """
    without_value = [
        (name, message)
        for name, message, _role in refusals
        if SHAPE.match(message) and re.search(r"but was <>", message)
    ]
    assert_that(without_value).is_empty()


class TestTheHelpersBehindTheShape:
    def test_a_matching_type_is_handed_back_for_binding(self):
        assert_that(require_type("text", str, "a string")).is_equal_to("text")

    def test_a_wrong_type_is_refused_in_the_shape(self):
        with pytest.raises(TypeError, match=r"^val must be a string, but was <42> \(int\)$"):
            require_type(42, str, "a string")

    def test_the_subject_names_an_argument_when_it_is_one(self):
        with pytest.raises(TypeError, match=r"^given prefix arg must be a string"):
            require_type(42, str, "a string", subject=argument("prefix"))

    def test_a_long_value_is_cut_rather_than_dumped(self):
        # a refusal is read on one line, so a 500-character payload shows its opening and a count of the rest
        with pytest.raises(TypeError) as failure:
            refuse("x" * 500, "a number")
        message = str(failure.value)
        assert_that(message).contains("(442 more chars)")
        assert_that(len(message)).is_less_than(140)

    def test_a_hostile_repr_is_shown_on_one_line(self):
        """`repr` is arbitrary text written by whoever defined the type.

        A newline turns one refusal into what reads as several, an escape sequence repaints the
        terminal it is printed on, and a bidi override reorders the line without changing the string.
        None of that is worth carrying to report a wrong argument.
        """

        class Hostile:
            def __repr__(self) -> str:
                return "red\x1b[31m\x07 then\nnext line then\u202ereversed"

        with pytest.raises(TypeError) as failure:
            refuse(Hostile(), "a number")
        message = str(failure.value)
        assert_that(message.splitlines()).described_as("stays one line").is_length(1)
        assert_that(message).contains("\\x1b").contains("\\x0a").contains("\\u202e")

    def test_escaping_happens_before_the_cap_not_after(self):
        """Order matters: an escape is four characters where the original was one.

        Capped first and escaped second, a value of two hundred control characters came back as three
        hundred, and the cap that exists to keep the refusal on one line stopped doing it.
        """

        class AllControl:
            def __repr__(self) -> str:
                return chr(0x1B) * 200

        with pytest.raises(TypeError) as failure:
            refuse(AllControl(), "a number")
        assert_that(len(str(failure.value))).is_less_than(140)

    def test_a_control_character_is_shown_rather_than_dropped(self):
        # dropping them would print two different values identically, which is the point of showing the value
        class Carriage:
            def __repr__(self) -> str:
                return chr(0x0D) + "OVERWRITE"

        class Plain:
            def __repr__(self) -> str:
                return "OVERWRITE"

        with pytest.raises(TypeError) as carriage:
            refuse(Carriage(), "a number")
        with pytest.raises(TypeError) as plain:
            refuse(Plain(), "a number")
        assert_that(str(carriage.value)).contains("\\x0d")
        assert_that(str(carriage.value)).is_not_equal_to(str(plain.value).replace("Plain", "Carriage"))

    def test_an_unreprable_value_is_named_rather_than_raised_over(self):
        class Unreprable:
            def __repr__(self) -> str:
                raise RuntimeError("bug inside __repr__")

        with pytest.raises(TypeError, match="unreprable Unreprable"):
            refuse(Unreprable(), "a number")

    def test_a_type_with_an_enormous_name_does_not_take_the_line(self):
        enormous = type("N" * 300, (), {})
        with pytest.raises(TypeError) as failure:
            refuse(enormous(), "a number")
        assert_that(len(str(failure.value))).is_less_than(200)

    def test_size_is_read_where_there_is_one(self):
        assert_that(sized_len([1, 2, 3])).is_equal_to(3)

    def test_size_is_refused_where_there_is_none(self):
        with pytest.raises(TypeError, match=r"^val must be a sized object, but was <42> \(int\)$"):
            sized_len(42)


class TestADiagnosticNeverReplacesSomebodyElsesError:
    """The line between "your operand has no such capability" and "your capability is broken".

    Both surface as `TypeError`, and the package used to answer both with its own sentence.  For the
    second that is a lie with a cost: `val must be a sized object` about a value whose `__len__` raises
    sends the reader to check the type of the value, when the bug is a few lines inside their own class.

    Told apart by where the error came from: `len(42)` never leaves the frame that tried it, while a
    `__len__` of one's own adds one.  The same test that proves the pass-through must prove the refusal
    still happens, or "re-raise everything" would pass it.
    """

    class BrokenLength:
        def __len__(self) -> int:
            raise TypeError("bug inside __len__")

    class BrokenOrder:
        def __lt__(self, other: object) -> bool:
            raise TypeError("bug inside __lt__")

        def __gt__(self, other: object) -> bool:
            raise TypeError("bug inside __gt__")

    @pytest.mark.parametrize(
        ("label", "call"),
        [
            ("is_length", lambda broken: assert_that(broken).is_length(3)),
            ("is_empty", lambda broken: assert_that(broken).is_empty()),
            ("is_not_empty", lambda broken: assert_that(broken).is_not_empty()),
            ("has_same_size_as as val", lambda broken: assert_that(broken).has_same_size_as([1])),
            ("has_same_size_as as arg", lambda broken: assert_that([1]).has_same_size_as(broken)),
            ("matcher has_length", lambda broken: assert_that(broken).satisfies(match.has_length(3))),
            ("matcher is_empty", lambda broken: assert_that(broken).satisfies(match.is_empty())),
        ],
    )
    def test_a_length_that_raises_is_reported_as_written(self, label, call):
        with pytest.raises(TypeError, match="bug inside __len__"):
            call(self.BrokenLength())

    @pytest.mark.parametrize(
        ("label", "call"),
        [
            ("is_greater_than", lambda broken: assert_that(broken).is_greater_than(broken)),
            ("is_less_than", lambda broken: assert_that(broken).is_less_than(broken)),
            ("matcher greater_than", lambda broken: assert_that(broken).satisfies(match.greater_than(1))),
            ("matcher less_than", lambda broken: assert_that(broken).satisfies(match.less_than(1))),
        ],
    )
    def test_a_comparison_that_raises_is_reported_as_written(self, label, call):
        with pytest.raises(TypeError, match="bug inside __"):
            call(self.BrokenOrder())

    def test_the_operand_that_simply_cannot_is_still_refused(self):
        with pytest.raises(TypeError, match=r"^val must be a sized object"):
            assert_that(42).is_length(3)
        with pytest.raises(TypeError, match=r"^given other arg must be comparable"):
            assert_that("10").is_greater_than(5)

    def test_a_matcher_still_answers_no_for_an_operand_it_cannot_compare(self):
        # a matcher feeds `==` and the combinators: an operand it cannot compare is a non-match, not an error
        assert_that(match.less_than(1).matches("text")).is_false()
        assert_that(match.has_length(3).matches(42)).is_false()


def test_the_sweep_covers_every_public_assertion(refusals):
    """Discovery is the gate's weak point: a method it never reaches is a method it never checks.

    Reported rather than asserted away, because an assertion that refuses nothing is legitimate: it may
    accept any value by design.  What must not happen is an assertion missing from the sweep itself.
    """
    swept = set(_public_assertions())
    reached = {name for name, _, _ in refusals}
    assert_that(swept).described_as("assertions discovered").is_not_empty()
    assert_that(reached - swept).described_as("reached but not discovered").is_empty()
    # a floor: it moves with every assertion added, and the point is that discovery keeps finding most of them
    assert_that(len(reached)).described_as("assertions that refused something").is_greater_than(len(swept) // 3)


HOSTILE_MATCHERS = [
    ("greater_than", match.greater_than(1)),
    ("greater_than_or_equal_to", match.greater_than_or_equal_to(1)),
    ("less_than", match.less_than(1)),
    ("less_than_or_equal_to", match.less_than_or_equal_to(1)),
    ("between", match.between(0, 10)),
    ("close_to", match.close_to(1, 0.5)),
    ("has_length", match.has_length(3)),
    ("is_length", match.is_length(3)),
    ("is_empty", match.is_empty()),
    ("is_not_empty", match.is_not_empty()),
    ("is_positive", match.is_positive()),
    ("is_negative", match.is_negative()),
    ("is_zero", match.is_zero()),
    ("is_even", match.is_even()),
    ("is_odd", match.is_odd()),
    ("is_divisible_by", match.is_divisible_by(2)),
    ("is_in", match.is_in(1, 2)),
    ("contains_string", match.contains_string("a")),
    ("starts_with", match.starts_with("a")),
    ("ends_with", match.ends_with("a")),
    ("each_item", match.each_item(match.is_positive())),
    ("is_now", match.is_now()),
]


class TestNoMatcherSwallowsABrokenOperator:
    """The same line, drawn across every matcher at once rather than one test per matcher.

    A matcher answers False for an operand it cannot handle, which is right: it feeds `==` and the
    combinators, where raising would be wrong.  The catch that implements it used to swallow a
    `TypeError` raised *inside* the operand's own operator too, and the test then failed as an ordinary
    non-match with no sign that the value's code was broken.

    The subject reports whether its operator was reached at all, so the gate can tell "did not look" from
    "looked and stayed quiet" without listing which matcher uses which operator.
    """

    class Hostile:
        """Every operator a matcher might reach raises, and records that it was reached."""

        def __init__(self) -> None:
            self.touched = 0

        def _boom(self, *_args: object) -> bool:
            self.touched += 1
            raise TypeError("bug inside operator")

        __lt__ = __le__ = __gt__ = __ge__ = _boom
        __len__ = __iter__ = __contains__ = _boom
        __sub__ = __add__ = __rsub__ = __radd__ = _boom

    @pytest.mark.parametrize(("label", "matcher"), HOSTILE_MATCHERS, ids=[label for label, _ in HOSTILE_MATCHERS])
    def test_an_operator_that_raises_is_never_reported_as_a_non_match(self, label, matcher):
        hostile = self.Hostile()
        try:
            verdict = matcher.matches(hostile)
        except TypeError as exc:
            assert_that(str(exc)).described_as(f"{label} re-raised something of its own").contains("bug inside")
            return
        assert_that(hostile.touched).described_as(f"{label} answered <{verdict}> after using the operator").is_zero()

    def test_a_description_never_swallows_it_either(self):
        """`describe()` runs while a failure is being rendered, and it reads the value a second time.

        Its own catch had the same hole: a `__len__` that raises turned into "which has no length",
        printed inside the message of an unrelated assertion failure.
        """
        hostile = self.Hostile()
        with pytest.raises(TypeError, match="bug inside operator"):
            match.has_length(3).describe_mismatch(hostile)
        with pytest.raises(TypeError, match="bug inside operator"):
            match.each_item(match.is_positive()).describe_mismatch(hostile)

    def test_a_datetime_comparison_that_raises_travels_out(self):
        class HostileMoment(datetime.datetime):
            def __lt__(self, other: object) -> bool:
                raise TypeError("bug inside operator")

            def __gt__(self, other: object) -> bool:
                raise TypeError("bug inside operator")

        moment = HostileMoment(2026, 1, 1)
        with pytest.raises(TypeError, match="bug inside operator"):
            match.is_before(datetime.datetime(2026, 6, 1)).matches(moment)
        with pytest.raises(TypeError, match="bug inside operator"):
            match.is_after(datetime.datetime(2025, 1, 1)).matches(moment)

    def test_an_instance_check_that_raises_travels_out(self):
        class HostileMeta(type):
            def __instancecheck__(cls, instance: object) -> bool:
                raise TypeError("bug inside operator")

        class HostileType(metaclass=HostileMeta):
            pass

        with pytest.raises(TypeError, match="bug inside operator"):
            match.is_instance_of(HostileType)
