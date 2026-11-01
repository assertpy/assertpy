"""What the checkers make of a real HTTP response from each client this library supports.

`tests/test_typing.py` pins the same dispatch against a stand-in, which is what runs everywhere.  This
file needs the clients installed, because a stand-in proves the overload is written correctly and says
nothing about whether a real `Response` still matches it.  Two of these did not: an ASGI and a WSGI
response are callables, so the callable overload claimed them before the capability that describes
them, and `has_status_code()` on a Starlette or a Flask response was a type error in all three
checkers while the runtime answered it.

Every line here has to type-check.  A diagnostic on any of them is the defect, not a finding to record.
The calls are also run against real responses, since a ``has_*`` call type-checks through the dynamic
hook whatever the runtime then does with it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_type

from assertpy import assert_that

if TYPE_CHECKING:
    import django.http
    import flask
    import httpx
    import requests
    import starlette.responses

    from assertpy._engine._capable_typing import _CapableAssertion


def responses_keep_their_own_assertions(
    from_requests: requests.Response,
    from_httpx: httpx.Response,
    from_starlette: starlette.responses.Response,
    from_flask: flask.Response,
    from_django: django.http.HttpResponse,
) -> None:
    assert_that(from_requests).has_status_code(200)
    assert_that(from_httpx).has_status_code(200)
    assert_that(from_starlette).has_status_code(200)
    assert_that(from_flask).has_status_code(200)
    assert_that(from_django).has_status_code(200)
    assert_that(from_requests).has_reason("OK")
    assert_that(from_flask).decoded_as_json().is_equal_to({"ok": True})
    assert_that(from_starlette).is_not_none()


if TYPE_CHECKING:
    # the protocol is declared for the checkers only, so this half is read and never run
    def each_client_keeps_its_own_type(
        from_requests: requests.Response,
        from_httpx: httpx.Response,
        from_starlette: starlette.responses.Response,
        from_flask: flask.Response,
        from_django: django.http.HttpResponse,
    ) -> None:
        """The witness that a client is still being read, rather than resolved to `Any` and waved through.

        A checker that cannot read a package answers `Any` for everything in it, and every call on such a
        value type-checks.  Without this, a client that stopped shipping `py.typed` would leave this gate
        silently: its lines would keep passing while proving nothing at all.

        The head of each expected type belongs to this package rather than to the client, which is what makes
        the witness a witness: `assert_type(x.value, x.Response)` degrades on both sides at once and passes,
        since `Any` is asserted against `Any`.  Against `_CapableAssertion[...]` a degraded client reads as
        `Any` on one side and a real class on the other.
        """
        assert_type(assert_that(from_requests), _CapableAssertion[requests.Response])
        assert_type(assert_that(from_httpx), _CapableAssertion[httpx.Response])
        assert_type(assert_that(from_starlette), _CapableAssertion[starlette.responses.Response])
        assert_type(assert_that(from_flask), _CapableAssertion[flask.Response])
        assert_type(assert_that(from_django), _CapableAssertion[django.http.HttpResponse])


def a_response_assertion_is_refused_where_the_value_is_not_one(text: str) -> None:
    """The witness that the checkers ran at all: every one of them has to refuse this line.

    A crashed checker reports nothing, which in a file whose whole claim is "nothing was reported"
    reads exactly like a clean run.  So one line here is wrong on purpose.
    """
    assert_that(text).has_header("content-type")  # case: refused-on-a-string
