"""The harness the typing gates read their checkers through, where it reads a JSON report.

A checker's output and its error stream were read as one text.  A line pyright wrote to its error stream came
after the report, and every test reading pyright ended with ``Extra data``.
"""

from __future__ import annotations

import subprocess

import pytest

from assertpy import assert_that
from tests import typing_harness
from tests.optional import needs

REPORT = '{"generalDiagnostics": [{"rule": "reportCallIssue", "range": {"start": {"line": 4}}}], "n": 1}'
READ = {"generalDiagnostics": [{"rule": "reportCallIssue", "range": {"start": {"line": 4}}}], "n": 1}


def _finished(output: str, errors: str = "", code: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["pyright"], code, output, errors)


@pytest.mark.parametrize(
    "errors",
    ["", "node: a warning on the error stream\n", '{"generalDiagnostics": []}', "{not a report"],
    ids=["nothing", "a line", "a document of its own", "a brace"],
)
def test_the_report_is_the_output_stream_whatever_the_error_stream_holds(errors):
    assert_that(typing_harness.report_of(_finished(REPORT, errors))).is_equal_to(READ)
    assert_that(typing_harness.report_of(_finished(REPORT + "\n", errors, code=0))).is_equal_to(READ)


@pytest.mark.parametrize(
    "output",
    [
        "",
        "node: not found",
        REPORT + REPORT,
        '{"generalDiagnostics": []}\n' + REPORT,
        "a notice {cache}\n" + REPORT,
        "{}\n" + REPORT,
        REPORT + "\na line after it",
        REPORT[:-1],
        "null",
        "[]",
        "{}",
        '{"generalDiagnostics": {}}',
        '{"summary": {"errorCount": 0}}',
    ],
    ids=[
        "nothing",
        "no report",
        "two reports",
        "an empty report first",
        "a notice with a brace",
        "an object first",
        "a line after",
        "cut short",
        "a null",
        "a list",
        "an empty object",
        "diagnostics that are no list",
        "a summary alone",
    ],
)
def test_an_output_that_is_not_one_report_is_refused_and_not_searched(output):
    said = (
        assert_that(typing_harness.report_of)
        .raises(ValueError)
        .when_called_with(_finished(output, "on the error stream", 3))
    )
    said.contains("a checker printed no JSON report", "exit code 3", repr(output), "'on the error stream'")


def test_a_real_pyright_run_is_read():
    needs("pyright", delegated_to="the lint job")
    found = typing_harness.pyright(typing_harness.ROOT / "tests" / "typing_harness.py")
    assert_that(found).is_instance_of(dict)
