"""Hold the HTTP dispatch to what the real clients are, with all three checkers.

The clients are somebody else's classes, and what makes one reach the assertions written for it is the
shape it happens to carry.  A response that stops matching, or an overload that moves above the
capability again, is silent from inside this repository: the call keeps running and only a checker
says anything.
"""

from __future__ import annotations

import sys

import pytest

from tests.optional import needs

needs("pyright", delegated_to="the lint job")
needs("mypy", delegated_to="the lint job")
needs("requests")
needs("httpx")
needs("starlette")
needs("flask")
needs("django")

import django.http
import flask
import httpx
import requests
import starlette.responses

from assertpy import assert_that
from tests import typing_harness, typing_http

_CASES = typing_harness.ROOT / "tests" / "typing_http.py"
_INTERPRETER = sys.executable
_TARGET = "3.14"


@pytest.fixture(scope="module")
def reported() -> dict[str, dict[int, set[str]]]:
    return {
        "ty": typing_harness.ty(_CASES, "--python", _INTERPRETER, "--python-version", _TARGET),
        "mypy": typing_harness.mypy(_CASES, "--python-executable", _INTERPRETER, "--python-version", _TARGET),
        "pyright": typing_harness.pyright(_CASES, "--pythonpath", _INTERPRETER, "--pythonversion", _TARGET),
    }


def test_the_file_holds_a_call_for_every_client(reported) -> None:
    # a file that stopped naming a client would let its dispatch drift with nothing to say so
    written = _CASES.read_text(encoding="utf-8")
    assert_that(written).contains("requests", "httpx", "starlette", "flask", "django")
    assert_that(written.count("has_status_code(200)")).described_as("one status call per client").is_equal_to(5)


def _witness_line() -> int:
    """The line every checker has to refuse, found by its tag rather than counted by hand."""
    tagged = typing_harness.tagged_lines(_CASES)
    return next(number for number, case in tagged.items() if case == "refused-on-a-string")


def test_every_checker_ran_at_all(reported) -> None:
    """A checker that crashed reports nothing, and nothing is what a clean run looks like here.

    Measured rather than assumed: mypy handed a broken `--python-executable` prints a message this
    harness does not parse and hands back an empty mapping, and so does ty pointed at a path that does
    not exist.  Only pyright fails loudly, and only because its output stops being JSON.
    """
    witness = _witness_line()
    silent = [checker for checker, found in reported.items() if witness not in found]
    assert_that(silent).described_as("a checker that did not refuse the line written to be refused").is_empty()


def test_no_checker_refuses_a_response_its_own_assertions(reported) -> None:
    """Zero diagnostics about the calls, since every line here is one the runtime answers.

    Nothing is excused any more.  Django ships no `py.typed`, so mypy used to decline to read it and
    say so on the import, and that excuse cost the whole pair: to a checker that cannot read a package
    every value in it is `Any`, and every call on one type-checks.  `django-stubs` is a type-check
    dependency now, so all fifteen client-and-checker pairs answer for themselves.
    """
    refused = {
        checker: sorted(line for line in found if line != _witness_line()) for checker, found in reported.items()
    }
    assert_that({checker: lines for checker, lines in refused.items() if lines}).described_as(
        "lines a checker refused, each a call the runtime answers"
    ).is_equal_to({})


def test_every_line_the_checkers_accept_is_one_the_runtime_answers() -> None:
    """Run as well as read: two lines here once type-checked through the dynamic hook and failed when called."""
    from_requests = requests.Response()
    from_requests.status_code, from_requests.reason = 200, "OK"
    responses = (
        from_requests,
        httpx.Response(200),
        starlette.responses.Response(status_code=200),
        flask.Response('{"ok": true}', mimetype="application/json"),
        django.http.HttpResponse(status=200, content_type="text/plain", charset="utf-8"),
    )
    typing_http.responses_keep_their_own_assertions(*responses)
