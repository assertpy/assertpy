"""Negation inverts the answer to a question, never whether the question could be asked.

Each site below asks something the subject has to be fit for first: a permission of the file at a
path, the name of that file, the value of a field, the keys an ``include=`` compares, the group a
pattern captures.  Each used to report the unfit subject as its answer, so ``not_`` read "the path
does not exist" as "the file is not readable" and passed.  The exception-group family went first and
is covered in `test_expected_exception.py`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import pathlib
from dataclasses import replace
from io import StringIO
from typing import TYPE_CHECKING, Any, NamedTuple
from unittest.mock import patch

import pytest

from assertpy import (
    WarningLoggingAdapter,
    add_extension,
    assert_that,
    assert_warn,
    remove_extension,
    soft_assertions,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_HERE = pathlib.Path(__file__).resolve()
_FILE = str(_HERE)
_DIRECTORY = str(_HERE.parent)
_OUTSIDE = str(_HERE.parent.parent / "pyproject.toml")
_SIBLING = str(_HERE.parent / "conftest.py")
_MISSING = "no-such-directory-for-prerequisites/no-such-file.txt"
_ABSENT = f"Expected <{_MISSING}> to exist, but was not found."
_NOT_A_FILE = f"Expected <{_DIRECTORY}> to be a file, but was not."


class _Person:
    def __init__(self, first_name: str) -> None:
        self.first_name = first_name


class _Nameless:
    """An object with no `first_name`, which is what a typo in a dynamic assertion's name asks of."""


@dataclasses.dataclass
class _Point:
    x: int
    y: int


@dataclasses.dataclass
class _Flat:
    y: int


class Met(NamedTuple):
    """The same question asked where it can be, and whether the answer is yes."""

    subject: object
    ask: Callable[[Any], Any]
    holds: bool
    access: bool | None = None


class Site(NamedTuple):
    """A subject unfit for the question, the failure saying so, and where the question can be asked."""

    subject: object
    ask: Callable[[Any], Any]
    message: str
    met: tuple[Met, ...]


def _permission(ask: Callable[[Any], Any]) -> Site:
    return Site(_MISSING, ask, _ABSENT, (Met(_FILE, ask, True, access=True), Met(_FILE, ask, False, access=False)))


def _named(chain: Any) -> Any:
    return chain.is_named(_HERE.name)


def _child(chain: Any) -> Any:
    return chain.is_child_of(_DIRECTORY)


def _first_name(chain: Any) -> Any:
    return chain.has_first_name("Fred")


def _key(chain: Any) -> Any:
    return chain.has_a(1)


def _including_a(chain: Any) -> Any:
    return chain.is_equal_to({"a": 1, "b": 2}, include="a")


def _including_nested(chain: Any) -> Any:
    return chain.is_equal_to({"a": {"x": 1}}, include=[("a", "x")])


def _including_field(chain: Any) -> Any:
    return chain.is_equal_to(_Point(1, 2), include="x")


def _including_per_item(chain: Any) -> Any:
    return chain.is_equal_to([{"a": 1}], include="a")


def _second_group(chain: Any) -> Any:
    return chain.extracting_group(r"a=(\d)", 2)


def _first_group(chain: Any) -> Any:
    return chain.extracting_group(r"a=(\d)", 1)


def _optional_group(chain: Any) -> Any:
    return chain.extracting_group(r"a=(\d)(x)?", 2)


_SITES = {
    "is_readable": _permission(lambda chain: chain.is_readable()),
    "is_writable": _permission(lambda chain: chain.is_writable()),
    "is_executable": _permission(lambda chain: chain.is_executable()),
    "is_named-missing": Site(_MISSING, _named, _ABSENT, (Met(_FILE, _named, True), Met(_SIBLING, _named, False))),
    "is_named-directory": Site(_DIRECTORY, _named, _NOT_A_FILE, (Met(_FILE, _named, True),)),
    "is_child_of-missing": Site(_MISSING, _child, _ABSENT, (Met(_FILE, _child, True), Met(_OUTSIDE, _child, False))),
    "is_child_of-directory": Site(_DIRECTORY, _child, _NOT_A_FILE, (Met(_FILE, _child, True),)),
    "has_-attribute": Site(
        _Nameless(),
        _first_name,
        "Expected attribute <first_name>, but val has no attribute <first_name>.",
        (Met(_Person("Fred"), _first_name, True), Met(_Person("Joe"), _first_name, False)),
    ),
    "has_-key": Site(
        {"b": 1},
        _key,
        "Expected key <a>, but val has no key <a>.",
        (Met({"a": 1}, _key, True), Met({"a": 2}, _key, False)),
    ),
    "include-mapping": Site(
        {"b": 2},
        _including_a,
        "Expected <{'b': 2}> to include key <a>, but did not include key <a>.",
        (Met({"a": 1, "b": 3}, _including_a, True), Met({"a": 2}, _including_a, False)),
    ),
    "include-nested": Site(
        {"a": {"y": 1}},
        _including_nested,
        "Expected <{'y': 1}> to include key <x>, but did not include key <x>.",
        (Met({"a": {"x": 1, "y": 2}}, _including_nested, True), Met({"a": {"x": 2}}, _including_nested, False)),
    ),
    "include-fields": Site(
        _Flat(2),
        _including_field,
        "Expected <_Flat(y=2)> to include key <x>, but did not include key <x>.",
        (Met(_Point(1, 5), _including_field, True), Met(_Point(3, 2), _including_field, False)),
    ),
    "include-per-item": Site(
        [{"b": 1}],
        _including_per_item,
        "Expected <{'b': 1}> to include key <a>, but did not include key <a>.",
        (Met([{"a": 1, "b": 2}], _including_per_item, True), Met([{"a": 2}], _including_per_item, False)),
    ),
    "extracting_group": Site(
        "a=1",
        _second_group,
        r"Expected pattern <a=(\d)> to have group <2>, but it does not.",
        (Met("a=1", _first_group, True), Met("a=1", _optional_group, False)),
    ),
}


def _access(granted: bool | None) -> contextlib.AbstractContextManager[object]:
    return contextlib.nullcontext() if granted is None else patch("os.access", return_value=granted)


class TestNegationKeepsThePrerequisite:
    @pytest.mark.parametrize("site", list(_SITES))
    def test_the_positive_and_not_both_fail_on_it_with_the_same_message(self, site):
        found = _SITES[site]
        for asked in (assert_that(found.subject), assert_that(found.subject).not_):
            with pytest.raises(AssertionError) as exc_info:
                found.ask(asked)
            assert_that(str(exc_info.value)).is_equal_to(found.message)

    @pytest.mark.parametrize("site", list(_SITES))
    def test_check_answers_the_positive_failure_asked_through_not(self, site):
        found = _SITES[site]
        positive = found.ask(assert_that(found.subject).check())
        negated = found.ask(assert_that(found.subject).check().not_)
        assert_that(negated.passed).is_false()
        assert_that(negated.message).is_equal_to(found.message)
        assert_that(negated.requirement).is_equal_to(replace(positive.requirement, negated=True))
        assert_that(replace(negated, requirement=None)).is_equal_to(replace(positive, requirement=None))

    @pytest.mark.parametrize("site", list(_SITES))
    def test_a_soft_block_collects_it_once_either_way(self, site):
        found = _SITES[site]
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as soft, soft.group("unfit"):
            found.ask(assert_that(found.subject))
            negated = found.ask(assert_that(found.subject).not_)
            with pytest.raises(TypeError) as refusal:
                _ = negated.value
        assert_that(exc_info.value.failures).is_length(2)
        positive, collected = exc_info.value.failures
        assert_that(collected.message).is_equal_to(positive.message).is_equal_to(found.message)
        assert_that(collected.group).is_equal_to(positive.group).is_equal_to("unfit")
        assert_that(collected.location[0]).is_equal_to(positive.location[0]).ends_with("test_prerequisites.py")
        assert_that(str(refusal.value)).contains(f"soft or warn mode - {found.message}")

    @pytest.mark.parametrize("site", list(_SITES))
    def test_warn_logs_it_under_not_and_the_value_refuses(self, site):
        found = _SITES[site]
        capture = StringIO()
        logger = logging.getLogger(f"negated_prerequisite_{site}")
        handler = logging.StreamHandler(capture)
        logger.addHandler(handler)
        try:
            negated = found.ask(assert_warn(found.subject, logger=WarningLoggingAdapter(logger, None)).not_)
        finally:
            logger.removeHandler(handler)
        assert_that(capture.getvalue()).contains(found.message)
        with pytest.raises(TypeError) as refusal:
            _ = negated.value
        assert_that(str(refusal.value)).contains(f"soft or warn mode - {found.message}")

    @pytest.mark.parametrize("site", list(_SITES))
    def test_a_poll_never_holds_it_under_not(self, site):
        found = _SITES[site]
        chain = assert_that(lambda: found.subject).eventually_sync(timeout=0.05, interval=0.01)
        with pytest.raises(AssertionError) as exc_info:
            found.ask(chain.not_)
        assert_that(str(exc_info.value)).contains(f"Last failure: {found.message}")

    @pytest.mark.parametrize("site", list(_SITES))
    def test_not_is_the_complement_only_where_the_question_can_be_asked(self, site):
        found = _SITES[site]
        for met in found.met:
            passing, failing = (assert_that(met.subject), assert_that(met.subject).not_)
            if not met.holds:
                passing, failing = failing, passing
            with _access(met.access):
                met.ask(passing)
                with pytest.raises(AssertionError) as exc_info:
                    met.ask(failing)
            assert_that(str(exc_info.value)).is_not_equal_to(found.message)
        for asked in (assert_that(found.subject), assert_that(found.subject).not_):
            with pytest.raises(AssertionError):
                found.ask(asked)


class TestWhatIsAtAPathIsAnAnswer:
    """`is_file()` and `is_directory()` ask what is at the path, and nothing there is one of the answers.

    Both went on after the missing path was reported, so a soft block collected a second failure for the
    same call and `check()` answered with the second one where the strict run raised the first.
    """

    @pytest.mark.parametrize("ask", [lambda chain: chain.is_file(), lambda chain: chain.is_directory()])
    def test_a_missing_path_is_one_failure_everywhere_and_not_holds(self, ask):
        with pytest.raises(AssertionError) as strict:
            ask(assert_that(_MISSING))
        with pytest.raises(AssertionError) as soft_run, soft_assertions():
            ask(assert_that(_MISSING))
        outcome = ask(assert_that(_MISSING).check())
        ask(assert_that(_MISSING).not_)
        assert_that(str(strict.value)).is_equal_to(_ABSENT)
        assert_that([failure.message for failure in soft_run.value.failures]).is_equal_to([_ABSENT])
        assert_that(outcome.message).is_equal_to(_ABSENT)


class TestAnItemWalkStopsAtTheFirstUnfitItem:
    """An ``include=`` checked item by item has nothing to compare from the first item lacking the key.

    The walk went on, so `check()` answered with the last such item where the strict run raised the first,
    and a soft block collected one failure per item for a single call.
    """

    def test_every_mode_reports_the_first_one_once(self):
        subject, expected = [{"b": 1}, {"c": 1}], [{"a": 1}, {"a": 1}]
        first = "Expected <{'b': 1}> to include key <a>, but did not include key <a>."
        with pytest.raises(AssertionError) as strict:
            assert_that(subject).is_equal_to(expected, include="a")
        with pytest.raises(AssertionError) as soft_run, soft_assertions():
            assert_that(subject).is_equal_to(expected, include="a")
        positive = assert_that(subject).check().is_equal_to(expected, include="a")
        negated = assert_that(subject).check().not_.is_equal_to(expected, include="a")
        assert_that(str(strict.value)).is_equal_to(first)
        assert_that([failure.message for failure in soft_run.value.failures]).is_equal_to([first])
        assert_that(positive.message).is_equal_to(negated.message).is_equal_to(first)


class TestABadArgumentIsRefusedWhateverTheSubject:
    """A path argument that is not one is a mistake in the call, and it was reported only past the file.

    The strict run reported the missing file first, while `not_` and `check()` recorded it and then raised
    the `TypeError` anyway, so one call answered two different ways.
    """

    @pytest.mark.parametrize("ask", [lambda chain: chain.is_named(123), lambda chain: chain.is_child_of(123)])
    def test_every_mode_raises_the_type_error(self, ask):
        for chain in (
            assert_that(_MISSING),
            assert_that(_MISSING).not_,
            assert_that(_MISSING).check(),
            assert_that(_MISSING).check().not_,
        ):
            with pytest.raises(TypeError, match="must be a path"):
                ask(chain)
        with pytest.raises(TypeError, match="must be a path"), soft_assertions():
            ask(assert_that(_MISSING))


def unfit_first(chain: Any) -> Any:
    chain.has_first_name("Fred")
    return chain.is_equal_to("something else")


def answered_first(chain: Any) -> Any:
    chain.is_equal_to("something else")
    return chain.has_first_name("Fred")


def answered_before_a_negation(chain: Any) -> Any:
    chain.is_equal_to("something else")
    return chain.not_.has_first_name("Fred")


class TestTheFirstFailureDecides:
    """A strict run stops at its first failure, so that is the one every mode answers with.

    Check mode goes on past a failure, and each later one replaced it: `check()` answered with the last,
    and a prerequisite missed after an ordinary failure, which the strict run never reaches, was
    delivered under `not_` as if the question could not be asked.
    """

    _UNFIT = "Expected attribute <first_name>, but val has no attribute <first_name>."

    @pytest.fixture(autouse=True)
    def _registered(self):
        for extension in (unfit_first, answered_first, answered_before_a_negation):
            add_extension(extension)
        yield
        for extension in (unfit_first, answered_first, answered_before_a_negation):
            remove_extension(extension)

    def test_a_prerequisite_missed_first_is_what_every_mode_reports(self):
        subject = _Nameless()
        for asked in (assert_that(subject), assert_that(subject).not_):
            with pytest.raises(AssertionError) as exc_info:
                asked.unfit_first()
            assert_that(str(exc_info.value)).is_equal_to(self._UNFIT)
        assert_that(assert_that(subject).check().unfit_first().message).is_equal_to(self._UNFIT)
        assert_that(assert_that(subject).check().not_.unfit_first().message).is_equal_to(self._UNFIT)

    def test_an_answer_first_leaves_the_later_prerequisite_unreached(self):
        """Missed directly or inside a negation of its own, the prerequisite comes after the answer."""
        subject = _Nameless()
        for name in ("answered_first", "answered_before_a_negation"):
            with pytest.raises(AssertionError) as strict:
                getattr(assert_that(subject), name)()
            assert_that(str(strict.value)).starts_with("Expected <").contains("to be equal to <something else>")
            assert_that(getattr(assert_that(subject).check(), name)().message).is_equal_to(str(strict.value))
            getattr(assert_that(subject).not_, name)()
            assert_that(getattr(assert_that(subject).check().not_, name)().passed).is_true()
