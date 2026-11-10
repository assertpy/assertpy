"""Hold what the checkers make of real pandas, polars and numpy values to the recorded matrix.

The overloads narrow on structure, and the structures belong to pandas, polars and numpy.  So the
question this file answers is not whether the overloads are written correctly, which
`tests/test_typing.py` answers against stand-ins on every platform, but whether the libraries still
match them.  Stub drift is silent by construction: a member that stops being declared moves a value to
the generic builder, which type-checks fine and simply stops offering the narrowed methods.

Skipped where the checkers or the libraries are absent, so this runs in the type-check job.
"""

from __future__ import annotations

import sys

import pytest

from tests.optional import needs

needs("pyright", delegated_to="the lint job")
needs("mypy", delegated_to="the lint job")
needs("pandas")
needs("polars")
needs("numpy")

from assertpy import assert_that
from tests import typing_harness
from tests.typing_integrations_baseline import DIVERGING, REFUSED, SILENT, STUB_WITNESS

_CASES = typing_harness.ROOT / "tests" / "typing_integrations.py"
# the interpreter running this test, which the skips above proved has the libraries; `.venv` is a guess
_INTERPRETER = sys.executable
_TARGET = "3.14"


@pytest.fixture(scope="module")
def reported() -> dict[str, dict[int, set[str]]]:
    """Line number to diagnostic codes, per checker, each given its environment rather than left to find one."""
    return {
        "ty": typing_harness.ty(_CASES, "--python", _INTERPRETER, "--python-version", _TARGET),
        "mypy": typing_harness.mypy(_CASES, "--python-executable", _INTERPRETER, "--python-version", _TARGET),
        "pyright": typing_harness.pyright(_CASES, "--pythonpath", _INTERPRETER, "--pythonversion", _TARGET),
    }


@pytest.fixture(scope="module")
def by_case(reported) -> dict[str, dict[str, set[str]]]:
    return typing_harness.by_case(reported, _CASES)


class TestTheMeasurementItselfRan:
    """Comparing against a run that never happened passes everything, so the run has to be shown."""

    def test_every_recorded_case_is_present_in_the_file(self, by_case):
        assert_that(set(by_case)).is_equal_to(SILENT | set(DIVERGING) | set(REFUSED))

    def test_all_three_checkers_reported_something(self, reported):
        silent = [checker for checker, found in reported.items() if not found]
        assert_that(silent).described_as("a checker reported nothing at all: it did not run").is_empty()

    def test_the_checkers_resolved_the_stubs(self, by_case):
        """Without `pandas-stubs` every member reads as `Any` and the matrix goes quiet for the wrong reason."""
        blind = {checker: sorted(codes) for checker, codes in by_case[STUB_WITNESS].items() if codes}
        assert_that(blind).described_as("the stub witness failed: the run did not see pandas-stubs").is_empty()

    def test_no_diagnostic_lands_outside_a_tagged_line(self, reported):
        lines = typing_harness.tagged_lines(_CASES)
        stray = {
            checker: sorted(number for number in found if number not in lines)
            for checker, found in reported.items()
            if set(found) - set(lines)
        }
        assert_that(stray).described_as("diagnostics away from a tagged case: the file is broken").is_empty()


class TestTheRealLibrariesStillMatchTheShapes:
    def test_every_agreed_case_is_accepted_by_all_three(self, by_case):
        refused = {
            name: {checker: sorted(codes) for checker, codes in by_case[name].items() if codes}
            for name in SILENT
            if any(by_case[name].values())
        }
        assert_that(refused).described_as(
            "a real value stopped matching, or a narrowed view stopped carrying a call that works"
        ).is_empty()

    def test_the_only_disagreement_is_the_recorded_one(self, by_case):
        observed = {
            name: {checker: sorted(codes) for checker, codes in codes_by_checker.items() if codes}
            for name, codes_by_checker in by_case.items()
            if name not in REFUSED and any(codes_by_checker.values())
        }
        recorded = {
            name: {checker: sorted(codes) for checker, codes in expected.items()}
            for name, expected in DIVERGING.items()
        }
        assert_that(observed).described_as(
            "the checkers disagree somewhere new. Closed one? Update typing_integrations_baseline.py"
        ).is_equal_to(recorded)


class TestTheNarrowingRefusesWhatTheRuntimeRefuses:
    """The half that says the narrowing is worth its cost: on the generic builder these all type-check."""

    def test_each_refusal_is_made_by_all_three_with_the_recorded_codes(self, by_case):
        differing = {}
        for name, expected in REFUSED.items():
            observed = {checker: sorted(codes) for checker, codes in by_case[name].items() if codes}
            recorded = {checker: sorted(codes) for checker, codes in expected.items()}
            if observed != recorded:
                differing[name] = {"recorded": recorded, "observed": observed}
        assert_that(differing).described_as("a refusal changed. Update typing_integrations_baseline.py").is_empty()
