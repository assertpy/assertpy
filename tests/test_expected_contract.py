"""Every assertion either names what it measured against, or is written down as one that cannot.

`AssertionOutcome.expected` is what a report consumer reads: an Allure attachment, a dashboard, a
clustering key.  For most of the library that is the operand the assertion was handed, and for a while
only 22 of the 163 failure sites passed it, so the same question got a different answer depending on
which assertion had failed.

What cannot name one is a real category rather than an oversight, and this file is the boundary between
the two.  A negation was handed a value the subject must *not* be, and putting that under `expected`
would tell a reader the opposite of the truth.  A predicate with no operand was handed nothing at all.
Both are listed below with which of the two they are, so a new assertion has to be decided about.
"""

from __future__ import annotations

import ast
import collections
import datetime
import pathlib
import warnings

import pytest

from assertpy import assert_that, match
from assertpy.errors import AssertionFailure

_STAMP = datetime.datetime(2026, 2, 1)
_EARLIER = datetime.datetime(2026, 1, 1)


def _raise_key_error() -> None:
    raise KeyError("key")


def _warn_user() -> None:
    warnings.warn("user warning", UserWarning, stacklevel=2)


_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy"

# What the value must not be, which is not what it was expected to be
_NEGATIONS = {
    "contains_none_of",
    "does_not_contain",
    "does_not_contain_duplicates",
    "does_not_contain_entry",
    "does_not_contain_error",
    "does_not_contain_value",
    "does_not_exist",
    "does_not_have_json_path",
    "does_not_match",
    "is_not_between",
    "is_not_callable",
    "is_not_empty",
    "is_not_equal_to",
    "is_not_in",
    "is_not_inf",
    "is_not_close_to",
    "is_not_iterable",
    "is_not_nan",
    "is_not_none",
    "is_not_same_as",
    "none_satisfy",
    "_when_called_with_not_expected",
    "_when_called_with_not_warning",
}

# Nothing was handed in: the assertion asks about the value alone
_ASKS_ABOUT_THE_VALUE_ALONE = {
    "contains_duplicates",
    "exists",
    "is_callable",
    "is_directory",
    "is_empty",
    "is_even",
    "is_executable",
    "is_file",
    "is_inf",
    "is_iterable",
    "is_nan",
    "is_odd",
    "is_readable",
    "is_sorted",
    "is_unicode",
    "is_valid_utf8",
    "is_writable",
}

# Not assertions: a refused subject, an exhausted poll, a walk reporting its own find
_NOT_AN_ASSERTION = {
    "_check_placeholders",
    "_dict_not_equal",
    "_out_of_time",
    "_require_existing",
    "_require_file",
    "_require_group",
    "conforms_to_openapi",
    "matches_contract_snapshot",
}

# a prerequisite's failure is decided at its `_unmet()` call, as an answer's is at `error()`
_FAILURE_CALLS = frozenset({"error", "_unmet"})

_EXCUSED = _NEGATIONS | _ASKS_ABOUT_THE_VALUE_ALONE | _NOT_AN_ASSERTION


def _by_owner() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """``(what names an expected, what does not)``, each as ``{function: [file:line]}``."""
    named: dict[str, list[str]] = collections.defaultdict(list)
    silent: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(_PACKAGE.glob("**/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    owner[id(child)] = node.name
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") in _FAILURE_CALLS):
                continue
            where = f"{path.name}:{node.lineno}"
            side = named if any(keyword.arg == "expected" for keyword in node.keywords) else silent
            side[owner.get(id(node), "?")].append(where)
    return dict(named), dict(silent)


def test_the_walk_found_the_failure_sites() -> None:
    # a walk that found nothing would agree with any register below it
    named, silent = _by_owner()
    sites = sum(len(where) for where in named.values())
    assert_that(sites).described_as("failure sites naming an expected").is_greater_than(100)
    assert_that(set(named) & set(silent)).described_as(
        "an assertion that names one in some places and not in others, which is the drift this catches"
    ).is_empty()


def test_every_assertion_that_names_no_expected_is_written_down() -> None:
    """The one direction that matters: a new assertion cannot quietly skip the field."""
    _named, silent = _by_owner()
    assert_that(sorted(set(silent) - _EXCUSED)).described_as(
        "failure sites that name no expected value and no reason for it"
    ).is_empty()


def test_no_excused_name_stands_for_two_different_assertions() -> None:
    """The register is keyed by name, so a name that two modules define would be excused twice over."""
    owners = collections.defaultdict(set)
    for path in sorted(_PACKAGE.glob("**/*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.FunctionDef) and node.name in _EXCUSED):
                continue
            # only where a failure is raised: a protocol declares the names and raises nothing
            if any(
                isinstance(call, ast.Call) and getattr(call.func, "attr", "") in _FAILURE_CALLS
                for call in ast.walk(node)
            ):
                owners[node.name].add(path.name)
    shared = {name: sorted(where) for name, where in owners.items() if len(where) > 1}
    assert_that(shared).described_as("one entry excusing more than one assertion").is_equal_to({})


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (lambda: assert_that(0).is_true(), True),
        (lambda: assert_that(1).is_false(), False),
        (lambda: assert_that(1).is_none(), None),
        (lambda: assert_that("ab").is_length(3), 3),
        (lambda: assert_that(1).is_same_as(2), 2),
        (lambda: assert_that(1).is_instance_of(str), str),
        (lambda: assert_that("foo").is_instance_of_any(int, float), (int, float)),
        (lambda: assert_that(bool).is_subclass_of(str), str),
        (lambda: assert_that([1]).contains(9), (9,)),
        (lambda: assert_that(5).is_between(1, 2), (1, 2)),
        (lambda: assert_that(5).is_in(1, 2), (1, 2)),
        (lambda: assert_that(5).is_close_to(1, 0.5), (1, 0.5)),
        (
            lambda: assert_that(_STAMP).is_close_to(_EARLIER, datetime.timedelta(hours=1)),
            (_EARLIER, datetime.timedelta(hours=1)),
        ),
        (lambda: assert_that(_raise_key_error).raises(ValueError).when_called_with(), ValueError),
        (lambda: assert_that(lambda: None).raises(ValueError).when_called_with(), ValueError),
        (lambda: assert_that(_raise_key_error).raises(KeyError).when_called_with().caused_by(OSError), OSError),
        (lambda: assert_that(_raise_key_error).raises(KeyError).when_called_with().has_root_cause(OSError), OSError),
        (lambda: assert_that(_warn_user).warns(DeprecationWarning).when_called_with(), DeprecationWarning),
        (lambda: assert_that(lambda: None).warns(DeprecationWarning).when_called_with(), DeprecationWarning),
        (lambda: assert_that("abc").matches("z"), "z"),
        (lambda: assert_that(_STAMP).is_before(_EARLIER), _EARLIER),
        # a payload the assertion normalised before measuring against it, and a value it derived
        (lambda: assert_that({"a": 1}).contains_entry(a=2), [{"a": 2}]),
        (lambda: assert_that([1, 2]).has_same_size_as([1]), 1),
        # the dynamic hook: the operand, on the comparison and on the name the value does not have
        (lambda: assert_that({"a": 1}).has_a(2), 2),
        (lambda: assert_that({"a": 1}).has_b(2), 2),
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_the_value_it_names_is_the_one_it_was_measured_against(call, expected) -> None:
    """The keyword being there is not the claim: what it carries is.

    A walk over the source can see `expected=` and nothing about what was put in it, so these pin the
    value for one assertion of each shape: a demanded constant, an operand, a variadic, a pair.
    """
    with pytest.raises(AssertionFailure) as failure:
        call()
    assert_that(failure.value.expected).is_equal_to(expected)


_MATCHER = match.greater_than(10)


def _leaves(expected: object) -> list[object]:
    """The expected side flattened one level, since a family may carry one operand or a collection."""
    if isinstance(expected, dict):
        return list(expected.values())
    if isinstance(expected, (list, tuple)):
        return list(expected)
    return [expected]


_CARRIES_THE_OPERAND = {
    "is_equal_to": lambda: assert_that(5).is_equal_to(_MATCHER),
    "contains": lambda: assert_that([5]).contains(_MATCHER),
    "matches_structure": lambda: assert_that({"n": 5}).matches_structure({"n": _MATCHER}),
}

_CARRIES_A_DESCRIPTION = {
    "satisfies": lambda: assert_that(5).satisfies(_MATCHER),
    "each": lambda: assert_that([5]).each(_MATCHER),
    "all_satisfy": lambda: assert_that([5]).all_satisfy(_MATCHER),
    "any_satisfy": lambda: assert_that([5]).any_satisfy(_MATCHER),
    "all_fields_satisfy": lambda: assert_that({"n": 5}).all_fields_satisfy(_MATCHER),
    "has_no_none_fields": lambda: assert_that({"n": None}).has_no_none_fields(),
    "satisfies_exactly": lambda: assert_that([5]).satisfies_exactly(_MATCHER),
    "satisfies_exactly_in_any_order": lambda: assert_that([5]).satisfies_exactly_in_any_order(_MATCHER),
}

_NAMES_NOTHING = {"none_satisfy": lambda: assert_that([50]).none_satisfy(_MATCHER)}


@pytest.mark.parametrize(
    ("call", "carries_the_object"),
    [
        *((call, True) for call in _CARRIES_THE_OPERAND.values()),
        *((call, False) for call in _CARRIES_A_DESCRIPTION.values()),
    ],
    ids=[*_CARRIES_THE_OPERAND, *_CARRIES_A_DESCRIPTION],
)
def test_what_each_matcher_family_puts_in_expected(call, carries_the_object) -> None:
    """The split the stability page documents, held by a test rather than by intention.

    Three families carry the matcher you passed and four carry its rendered description, and nothing in
    the failure says which. Making them uniform was measured and refused: a matcher in `expected` changes
    the Allure attachment shape, which is a versioned wire format, and compares as a predicate.

    Identity rather than equality on purpose. `assert_that(expected).is_equal_to(_MATCHER)` would ask the
    matcher about the matcher, which is the trap the page warns about.
    """
    with pytest.raises(AssertionFailure) as failure:
        call()
    leaves = _leaves(failure.value.expected)
    if carries_the_object:
        assert_that(any(leaf is _MATCHER for leaf in leaves)).described_as("carries the matcher").is_true()
    else:
        assert_that([type(leaf) for leaf in leaves]).described_as("carries descriptions").is_equal_to(
            [str] * len(leaves)
        )


@pytest.mark.parametrize("call", _NAMES_NOTHING.values(), ids=_NAMES_NOTHING.keys())
def test_an_assertion_naming_no_expectation_says_so(call) -> None:
    """The third row of the table.  Which assertions belong in it is settled above by the source walk.

    `filtered_on` looked like one and is not: it never fails, so the failure a chain after it produces
    belongs to whatever came next and carries that assertion's expected value.
    """
    with pytest.raises(AssertionFailure) as failure:
        call()
    assert_that(failure.value.has_expected).described_as("has_expected").is_false()
    assert_that(failure.value.expected).is_none()


def test_an_assertion_taking_both_an_operand_and_a_predicate_names_the_operand() -> None:
    """`zip_satisfies` is the one that takes both, and the operand is what the values were measured against."""
    other = [5]
    with pytest.raises(AssertionFailure) as failure:
        assert_that([5]).zip_satisfies(other, lambda left, right: left > 10)
    assert_that(failure.value.expected is other).described_as("carries the operand itself").is_true()


def test_a_matcher_in_expected_compares_as_a_predicate() -> None:
    """The trap that made uniformity unattractive, pinned so it is a decision and not a surprise."""
    with pytest.raises(AssertionFailure) as failure:
        assert_that(5).is_equal_to(_MATCHER)
    assert_that(failure.value.expected == 50).described_as("greater_than(10) asked about 50").is_true()


def test_no_entry_is_excusing_something_that_no_longer_happens() -> None:
    """The other direction, and the one that rots: an entry with nothing to excuse says so to nobody."""
    _named, silent = _by_owner()
    assert_that(sorted(_EXCUSED - set(silent))).described_as(
        "excused here and naming an expected anyway, so the entry is stale"
    ).is_empty()
