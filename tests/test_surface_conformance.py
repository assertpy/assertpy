"""One failure driven through every delivery surface, compared surface against surface.

The surfaces differ on purpose: a soft block numbers its entries and prints one line per differing
path, warn mode logs instead of raising, and a polling failure prefixes its own timeout line.  That
deliberate difference in shape is exactly why they need a shared gate, because twice now it carried an
undeliberate difference in *content* along with it: a hint that reached one mode and not another, and a
long string whose position of change the block form pointed at while the compact form said nothing.

What is asserted here is agreement, not format.  Each surface is reduced to the three things a reader
acts on: the headline, the one-cause hint, and the set of paths named underneath.  A test that pins the
exact text of one mode belongs next to that mode (`test_soft.py`, `test_warn.py`); a test that says two
modes must say the same thing belongs here.
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import logging
import re
from typing import TYPE_CHECKING, NamedTuple

import pytest

from assertpy import AssertionFailure, assert_that, assert_warn, match, soft_assertions
from assertpy.async_assertions import AsyncAssertionBuilder

if TYPE_CHECKING:
    from collections.abc import Callable

# `[file.py:12]`, appended by the compact surfaces only, and stripped since it says where and not what
_LOCATION = re.compile(r"\s+\[[^\[\]]+:\d+\]$")
_POLL_PREFIX = re.compile(r"^Expected condition not met after .*?\. Last failure: ")
_COMPACT_ROW = re.compile(r"^   (?P<path>.+?): ")

_HINTS = (
    "every difference here is",
    "the values are equal",
)


@dataclasses.dataclass(frozen=True)
class Delivered:
    """What one surface said, reduced to what a reader acts on."""

    headline: str
    hint: str | None
    paths: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Case:
    """A failure worth driving through every surface, plus the value it is about."""

    name: str
    subject: object
    check: object


def _hint_of(lines: list[str]) -> str | None:
    return next((line.strip() for line in lines if line.strip().startswith(_HINTS)), None)


def _raised(failure: AssertionFailure, text: str) -> Delivered:
    """Reduce a raised failure, taking its paths from the structure rather than from the text.

    Under pytest the block rendering is not in `str(exc)` at all: the plugin builds its own section
    from `exc.diff`, so that the message is not printed twice. The structure is what both readings come
    from, which makes it the right thing to hold a compact rendering against.
    """
    headline, *rest = text.splitlines()
    entries = failure.diff.entries if failure.diff is not None else ()
    return Delivered(headline=headline, hint=_hint_of(rest), paths=tuple(entry.path for entry in entries))


def _split_compact(text: str) -> Delivered:
    """Reduce a compact failure: the same three things, read off the one-line-per-path rendering."""
    headline, *rest = text.splitlines()
    paths = [found.group("path") for line in rest if (found := _COMPACT_ROW.match(line))]
    return Delivered(headline=_LOCATION.sub("", headline), hint=_hint_of(rest), paths=tuple(paths))


def _hard(case: Case) -> Delivered:
    with pytest.raises(AssertionFailure) as failure:
        case.check(assert_that(case.subject))
    return _raised(failure.value, str(failure.value))


def _soft(case: Case) -> Delivered:
    with pytest.raises(AssertionFailure) as failure, soft_assertions():
        case.check(assert_that(case.subject))
    _header, *entry = str(failure.value).splitlines()
    entry[0] = entry[0].removeprefix("1. ")
    return _split_compact("\n".join(entry))


def _warn(case: Case) -> Delivered:
    stream = io.StringIO()
    logger = logging.getLogger(f"conformance.{case.name}")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    case.check(assert_warn(case.subject, logger=logger))
    return _split_compact(stream.getvalue().rstrip("\n"))


def _polled(case: Case) -> Delivered:
    with pytest.raises(AssertionFailure) as failure:
        case.check(assert_that(lambda: case.subject).eventually_sync(timeout=0.02, interval=0.01))
    return _raised(failure.value, _POLL_PREFIX.sub("", str(failure.value), count=1))


SURFACES = {"soft": _soft, "warn": _warn, "polling": _polled}


class Verdict(NamedTuple):
    """An assertion over a value, asked in every mode, which must answer the same in each."""

    name: str
    subject: object
    check: Callable[..., object]


def _answer(call: Callable[[], object]) -> str:
    """What a mode said: it held, it did not, or the operands were refused before either."""
    try:
        call()
    except TypeError:
        return "refused"
    except AssertionFailure:
        return "failed"
    return "passed"


def _hard_verdict(case: Verdict) -> str:
    return _answer(lambda: case.check(assert_that(case.subject)))


def _soft_verdict(case: Verdict) -> str:
    def run() -> None:
        with soft_assertions():
            case.check(assert_that(case.subject))

    return _answer(run)


def _warn_verdict(case: Verdict) -> str:
    stream = io.StringIO()
    logger = logging.getLogger(f"verdict.{case.name}")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    answer = _answer(lambda: case.check(assert_warn(case.subject, logger=logger)))
    # warn never raises for a failure, so the verdict is whether it logged one
    return "failed" if answer == "passed" and stream.getvalue().strip() else answer


def _check_verdict(case: Verdict) -> str:
    outcome = None

    def run() -> None:
        nonlocal outcome
        outcome = case.check(assert_that(case.subject).check())

    answer = _answer(run)
    if answer != "passed":
        return answer
    return "passed" if getattr(outcome, "passed", False) else "failed"


def _polled_verdict(case: Verdict) -> str:
    return _answer(lambda: case.check(assert_that(lambda: case.subject).eventually_sync(timeout=0.02, interval=0.01)))


MODES = {
    "hard": _hard_verdict,
    "soft": _soft_verdict,
    "warn": _warn_verdict,
    "check": _check_verdict,
    "polling": _polled_verdict,
}

VERDICTS = [
    Verdict("equality holds", 1, lambda builder: builder.is_equal_to(1)),
    Verdict("equality fails", 1, lambda builder: builder.is_equal_to(2)),
    Verdict("membership holds", [1, 2], lambda builder: builder.contains(1)),
    Verdict("membership fails", [1, 2], lambda builder: builder.contains(9)),
    Verdict("length holds", "abc", lambda builder: builder.is_length(3)),
    Verdict("length fails", "abc", lambda builder: builder.is_length(4)),
    Verdict("ordering holds", 3, lambda builder: builder.is_greater_than(1)),
    Verdict("ordering fails", 3, lambda builder: builder.is_greater_than(10)),
    Verdict("negation holds", 1, lambda builder: builder.not_.is_equal_to(2)),
    Verdict("negation fails", 1, lambda builder: builder.not_.is_equal_to(1)),
    Verdict("text holds", "hello", lambda builder: builder.starts_with("he")),
    Verdict("text fails", "hello", lambda builder: builder.starts_with("xx")),
    Verdict("mapping holds", {"a": 1}, lambda builder: builder.contains_key("a")),
    Verdict("mapping fails", {"a": 1}, lambda builder: builder.contains_key("b")),
    Verdict("predicate holds", 4, lambda builder: builder.satisfies(lambda value: value % 2 == 0)),
    Verdict("predicate fails", 5, lambda builder: builder.satisfies(lambda value: value % 2 == 0)),
    # the operands cannot be compared at all, which is a refusal and not a verdict in any mode
    Verdict("operands refused", "a", lambda builder: builder.is_greater_than(1)),
    Verdict("subject refused", 1, lambda builder: builder.starts_with("a")),
]

CASES = [
    Case("dict", {"id": 1, "name": "a"}, lambda builder: builder.is_equal_to({"id": 2, "name": "b"})),
    Case("nested dict", {"a": {"b": 1}}, lambda builder: builder.is_equal_to({"a": {"b": 2}})),
    Case("list", [1, 2, 3], lambda builder: builder.is_equal_to([1, 9, 3])),
    Case("set", {1, 2}, lambda builder: builder.is_equal_to({1, 9})),
    Case("tuple", (1, 2), lambda builder: builder.is_equal_to((1, 9))),
    Case("scalar", 1, lambda builder: builder.is_equal_to(2)),
    Case("none against a value", None, lambda builder: builder.is_equal_to(1)),
    Case("short line", "hello", lambda builder: builder.is_equal_to("hallo")),
    Case("long line", "x" * 90 + "A" + "y" * 90, lambda builder: builder.is_equal_to("x" * 90 + "B" + "y" * 90)),
    Case("many lines", "a\nb", lambda builder: builder.is_equal_to("a\nc")),
    Case("bytes", b"abd", lambda builder: builder.is_equal_to(b"abc")),
    Case("membership", [1, 2, 3], lambda builder: builder.contains(9)),
    Case("length", "foo", lambda builder: builder.is_length(4)),
    Case("negated", 1, lambda builder: builder.not_.is_equal_to(1)),
    Case("described", 1, lambda builder: builder.described_as("label").is_equal_to(2)),
    Case("one cause", {"a": b"x", "b": b"y"}, lambda builder: builder.is_equal_to({"a": "x", "b": "y"})),
    Case("mixed causes", {"a": b"x", "b": 1}, lambda builder: builder.is_equal_to({"a": "x", "b": 2})),
]

IDS = [case.name for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize("surface", SURFACES, ids=list(SURFACES))
def test_every_surface_says_the_same_thing_happened(case: Case, surface: str):
    """The headline is the assertion's own sentence, so no surface may reword or drop it."""
    assert_that(SURFACES[surface](case).headline).is_equal_to(_hard(case).headline)


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize("surface", SURFACES, ids=list(SURFACES))
def test_every_surface_carries_the_one_cause_hint(case: Case, surface: str):
    """A hint names why *all* the differences happened, which is the reader's shortest route to the
    cause.  It reached the block form first, and adding a surface used to mean forgetting to pass it on.
    """
    assert_that(SURFACES[surface](case).hint).is_equal_to(_hard(case).hint)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_compact_surfaces_name_the_same_paths(case: Case):
    """soft and warn share one renderer, so they may never drift apart from each other at all."""
    assert_that(_warn(case).paths).is_equal_to(_soft(case).paths)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_polling_delivers_the_failure_it_wrapped_untouched(case: Case):
    """A timeout adds a line in front of the failure. Everything below that line is the failure."""
    assert_that(_polled(case)).is_equal_to(_hard(case))


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_a_named_path_is_never_invented(case: Case):
    """The compact form is allowed to say less than the block form, never something else.

    Less is a deliberate trade: a scalar and a short line repeat the headline, so they are dropped. A
    path that appears in one form and not the other is the shape both regressions took.
    """
    assert_that(set(_soft(case).paths)).is_subset_of(set(_hard(case).paths))


def _finish(chain):
    """Run a polling chain to its verdict, whichever surface built it."""
    return asyncio.run(chain) if isinstance(chain, AsyncAssertionBuilder) else chain


class _Polling(NamedTuple):
    """One polling surface: how a chain starts on it, and how it is brought to a verdict."""

    start: Callable[..., object]
    finish: Callable[[object], object]


@pytest.fixture(params=["eventually_sync", "eventually"])
def polling(request) -> _Polling:
    """Both polling surfaces under one name, so every question about a chain is asked of each.

    The four tests below describe what waiting *is*, and all four used to be asked of the sync surface
    only, which is how the async one came to do none of them.
    """

    def start(probe, **kwargs):
        return getattr(assert_that(probe), request.param)(**kwargs)

    return _Polling(start, _finish)


class TestPollingSurvivesTheChain:
    """Waiting is the whole point of the polling surface, and a chained call used to end it silently.

    Every fluent method hands back a builder, so the poller had no way to tell a navigation step from a
    final assertion: it ran one poll, returned the plain builder of that single snapshot, and everything
    written after the first call ran against it.  A chain that should have waited two seconds failed
    immediately instead, which reads as a flaky test rather than as a defect in the wait.
    """

    @staticmethod
    def _counting_probe(counter: dict[str, int]):
        def probe() -> int:
            counter["polls"] += 1
            return counter["polls"]

        return probe

    def test_a_second_assertion_keeps_waiting(self, polling):
        counter = {"polls": 0}
        polling.finish(
            polling.start(self._counting_probe(counter), timeout=2, interval=0.01).is_instance_of(int).is_equal_to(4)
        )
        assert_that(counter["polls"]).described_as("polls spent").is_greater_than(1)

    def test_a_navigation_step_keeps_waiting(self, polling):
        counter = {"polls": 0}
        polling.finish(
            polling.start(self._counting_probe(counter), timeout=2, interval=0.01).described_as("label").is_equal_to(4)
        )
        assert_that(counter["polls"]).described_as("polls spent").is_greater_than(1)

    def test_negation_polls_instead_of_raising_an_attribute_error(self, polling):
        states = iter(["pending", "pending", "ready"])
        chain = polling.start(lambda: next(states, "ready"), timeout=2, interval=0.01)
        polling.finish(chain.not_.is_equal_to("pending"))

    def test_a_negated_expectation_that_never_holds_times_out(self, polling):
        with pytest.raises(AssertionFailure, match="Expected condition not met"):
            polling.finish(polling.start(lambda: 1, timeout=0.05, interval=0.01).not_.is_equal_to(1))


def test_a_long_line_keeps_its_position_of_change_everywhere():
    """The one case where the compact form is not allowed to stay silent.

    Dropping the detail row is right when the headline carries both values readably.  On a 181-character
    payload it is not: the block form points a caret at character 91 and the compact form used to print
    nothing, leaving a reader to compare two walls of text by eye.
    """
    case = next(one for one in CASES if one.name == "long line")
    for surface in ("soft", "warn"):
        assert_that(SURFACES[surface](case).paths).described_as(surface).is_equal_to(("line 1",))


# every name on both surfaces; `is_falsy`, `is_truthy`, `is_uuid`, `filtered_on` and `extracting` have no twin
@pytest.mark.parametrize("case", VERDICTS, ids=lambda case: case.name)
def test_every_mode_reaches_the_same_verdict(case: Verdict) -> None:
    """The surfaces differ in shape on purpose; what they must not differ in is the answer.

    `assertpy.py` returns from five separate places depending on the mode, and the modes have twice
    diverged in content already.  A misuse stays a misuse everywhere too: an operand the assertion
    cannot read is refused rather than reported as a failed comparison.
    """
    answers = {mode: read(case) for mode, read in MODES.items()}
    assert_that(set(answers.values())).described_as(f"{case.name}: {answers}").is_length(1)


TWINS = [
    ("is_greater_than", match.greater_than, (0,)),
    ("is_greater_than_or_equal_to", match.greater_than_or_equal_to, (0,)),
    ("is_less_than", match.less_than, (0,)),
    ("is_less_than_or_equal_to", match.less_than_or_equal_to, (0,)),
    ("is_equal_to", match.equal_to, (1,)),
    ("is_between", match.between, (0, 10)),
    ("is_close_to", match.close_to, (1, 0.5)),
    ("contains", match.contains_string, ("ell",)),
    ("starts_with", match.starts_with, ("he",)),
    ("ends_with", match.ends_with, ("lo",)),
    # the same three against bytes: with a `str` operand the method refuses a bytes value outright
    ("contains", match.contains_string, (b"ell",)),
    ("starts_with", match.starts_with, (b"he",)),
    ("ends_with", match.ends_with, (b"lo",)),
    ("is_length", match.has_length, (5,)),
    ("is_in", match.is_in, (1, 2)),
    ("is_instance_of", match.is_instance_of, (int,)),
    ("is_type_of", match.is_type_of, (int,)),
    ("is_divisible_by", match.is_divisible_by, (2,)),
    ("is_empty", match.is_empty, ()),
    ("is_not_empty", match.is_not_empty, ()),
    ("is_none", match.is_none, ()),
    ("is_not_none", match.is_not_none, ()),
    ("is_even", match.is_even, ()),
    ("is_odd", match.is_odd, ()),
    ("is_positive", match.is_positive, ()),
    ("is_negative", match.is_negative, ()),
    ("is_zero", match.is_zero, ()),
    ("is_callable", match.is_callable, ()),
]

VALUES = [1, 0, -1, 2.0, "hello", b"hello", bytearray(b"hello"), "", [], [1, 2], {"a": 1}, None, True, print]


def _method_verdict(method: str, value: object, args: tuple) -> str:
    """`pass`, `fail`, or `error` when the method refused the operand types outright."""
    try:
        getattr(assert_that(value), method)(*args)
    except AssertionFailure:
        return "fail"
    except Exception:
        return "error"
    return "pass"


@pytest.mark.parametrize(
    ("method", "factory", "args"), TWINS, ids=[f"{method}{list(args) or ''}" for method, _factory, args in TWINS]
)
def test_a_matcher_answers_what_its_method_answers(method: str, factory, args: tuple):
    """Where the method gives a verdict, the matcher must give the same one.

    The two are allowed to differ in *strictness*: a method raises `TypeError` on operands it will not
    compare, and a matcher answers False instead, because it feeds `==` and combinators where raising
    would be wrong.  They are not allowed to differ in the verdict itself, which is what happened with
    bytes: `assert_that(b"hello").contains(b"ell")` passed while `match.contains_string(b"ell")` said no.
    """
    for value in VALUES:
        verdict = _method_verdict(method, value, args)
        if verdict == "error":
            continue
        try:
            matcher = factory(*args)
        except TypeError:
            continue
        assert_that(matcher.matches(value)).described_as(f"{method} on {value!r}").is_equal_to(verdict == "pass")


class TestCheckIsTheSameVerdictWithoutTheRaise:
    """`check()` answers instead of raising, which makes it the one surface with no exception to compare.

    That is exactly why it needs holding to the others: everything a raised failure carries has to be in
    the outcome it hands back, and everything that is *not* a failed assertion has to keep travelling.
    """

    class BrokenOrder:
        def __lt__(self, other: object) -> bool:
            raise TypeError("bug inside __lt__")

    def test_a_passing_assertion_answers_true(self):
        assert_that(assert_that([1, 2]).check().is_length(2).passed).is_true()

    def test_a_failing_assertion_answers_false(self):
        assert_that(assert_that([1, 2]).check().is_length(3).passed).is_false()

    def test_the_outcome_carries_what_the_raised_failure_carries(self):
        outcome = assert_that({"a": 1}).check().is_equal_to({"a": 2})
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        raised = failure.value
        assert_that(outcome.message).is_equal_to(str(raised).splitlines()[0])
        assert_that(outcome.actual).is_equal_to(raised.actual)
        assert_that(outcome.expected).is_equal_to(raised.expected)
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(
            [entry.path for entry in raised.diff.entries]
        )

    def test_a_wrong_argument_type_is_still_raised(self):
        # a usage error is not a verdict: `passed=False` reads as "not of that length" and hides the wrong call
        with pytest.raises(TypeError, match=r"^given length arg must be an integer"):
            assert_that([1, 2]).check().is_length("2")

    def test_a_broken_operator_of_their_own_is_still_raised(self):
        with pytest.raises(TypeError, match="bug inside __lt__"):
            assert_that(self.BrokenOrder()).check().is_less_than(1)

    def test_negation_answers_rather_than_inverting_a_usage_error(self):
        assert_that(assert_that([1, 2]).check().not_.is_length(2).passed).is_false()
        assert_that(assert_that([1, 2]).check().not_.is_length(3).passed).is_true()
        with pytest.raises(TypeError, match=r"^given length arg must be an integer"):
            assert_that([1, 2]).check().not_.is_length("2")

    @pytest.mark.parametrize(
        "spoil",
        [
            lambda builder: builder.check().is_length("2"),
            lambda builder: builder.check().is_less_than(object()),
        ],
        ids=["wrong argument type", "incomparable operand"],
    )
    def test_the_builder_survives_an_error_raised_inside_check(self, spoil):
        # `check()` swaps the builder into collecting mode for one call, and an error on that path used to
        # leave it swapped, so the next ordinary assertion collected instead of raising
        builder = assert_that([1, 2])
        with pytest.raises(TypeError):
            spoil(builder)
        assert_that(builder.is_length(2)).described_as("chains as before").is_same_as(builder)
        with pytest.raises(AssertionFailure):
            builder.is_length(3)
        assert_that(builder.check().is_length(2).passed).described_as("check still answers").is_true()
