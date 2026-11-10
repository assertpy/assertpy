"""The HTTP response surface: what a failure says about the response, and the step into its body.

Every response here is a stand-in built to one client's shape, because the point of the module under
test is that it imports none of them. The shapes are taken from httpx and requests (``json()``,
``text``, ``request``), Flask (``get_json()``, ``data``, the request werkzeug attaches), Django
(``content``, and the request as a WSGI environ) and one that has not read its body at all.
"""

from __future__ import annotations

import json
from decimal import Decimal
from wsgiref.headers import Headers

import pytest

from assertpy import assert_that, match, soft_assertions
from assertpy.errors import AssertionFailure
from tests.optional import needs


class _Request:
    def __init__(self, method="GET", url="https://api.example.com/orders/7"):
        self.method, self.url = method, url


class Fetched:
    """The httpx and requests shape: its own parser, the body as text, and the request it answered."""

    def __init__(self, status_code=200, body='{"id": 7}', content_type="application/json", request=None):
        self.status_code = status_code
        self.text = body
        self.headers = {"Content-Type": content_type}
        self.request = request if request is not None else _Request()

    def json(self):
        return json.loads(self.text)


class Flasked:
    """The Flask shape: ``get_json()`` and ``data``, with the request werkzeug keeps on the response."""

    def __init__(self, status_code=200, body=b'{"id": 7}'):
        self.status_code = status_code
        self.data = body
        self.headers = {"Content-Type": "application/json"}
        self.request = _Request("POST", "http://localhost/orders")

    def get_json(self):
        return json.loads(self.data)


class Django:
    """The Django shape: ``content`` as bytes, no parser, and the request as a WSGI environ.

    It also reads its headers by key and iterates its body, as the real one does, which is what makes it
    look like a mapping to anything asking only for ``__getitem__`` and ``__iter__``.
    """

    def __init__(self, status_code=200, body=b'{"id": 7}', environ=None):
        self.status_code = status_code
        self.content = body
        self.headers = {"Content-Type": "application/json"}
        if environ is not None:
            self.request = environ

    def __getitem__(self, header):
        return self.headers[header]

    def __iter__(self):
        return iter([self.content])


class Redirected(Django):
    """A Django redirect, whose ``url`` is where it points rather than where it was asked."""

    def __init__(self):
        super().__init__(status_code=302, body=b"")
        self.url = "/login"


class Streaming:
    """A response whose body has not been read: touching it raises, as httpx does."""

    def __init__(self):
        self.status_code = 500
        self.headers = {"Content-Type": "application/json"}
        self.request = _Request("POST", "https://api.example.com/orders")

    @property
    def text(self):
        raise RuntimeError("attempted to read the body of a streaming response")

    def json(self):
        raise RuntimeError("attempted to read the body of a streaming response")


class Served:
    """The Starlette shape: the body under ``body``, and no parser of its own."""

    def __init__(self, status_code=200, body=b'{"id": 7}'):
        self.status_code = status_code
        self.body = body
        self.headers = {"Content-Type": "application/json"}


class Reading:
    """A client whose ``text`` is a reader to call rather than the body it would hand back."""

    def __init__(self, body=b'{"id": 7}'):
        self.status_code = 200
        self.content = body
        self.headers = {"Content-Type": "application/json"}

    def text(self):
        return self.content.decode()


class Decoding(Fetched):
    """A client parsing with a decoder of its own: money as ``Decimal`` rather than as a float."""

    def json(self):
        return json.loads(self.text, parse_float=Decimal)


class DecodingFlask(Flasked):
    """The same client, under Flask's name for the parser."""

    def get_json(self):
        return json.loads(self.data, parse_float=Decimal)


class RawHeaders:
    """The ASGI shape: names arrive lowercased off the wire, and are matched as they came."""

    def __init__(self, raw):
        self._raw = raw

    def keys(self):
        return [name.decode() for name, _ in self._raw]

    def __getitem__(self, key):
        return next(value.decode() for name, value in self._raw if name == key.encode())

    def __iter__(self):
        return iter(self._raw)

    def get(self, name, default=None):
        return next((value.decode() for found, value in self._raw if found == name.encode()), default)


class TestTheFailureSaysWhichResponseItCameFrom:
    def test_a_failure_on_the_response_itself(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Fetched(status_code=500)).has_status_code(200)
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 500")

    def test_a_failure_under_the_parsed_body(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Fetched(body='{"id": 7}')).decoded_as_json().is_equal_to({"id": 9})
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 200")

    @pytest.mark.needs("jsonpath_ng")
    def test_a_failure_two_pivots_below_the_response(self):
        response = Fetched(body='{"items": [{"sku": "A-1"}]}')
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().at_json_path("$.items[0].sku").is_equal_to("B-2")
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 200")

    def test_a_response_that_kept_no_request(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Django(status_code=404)).has_status_code(200)
        assert_that(str(failure.value)).contains("from a response with status 404")

    def test_a_flask_response_names_its_request(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Flasked(status_code=418)).has_status_code(200)
        assert_that(str(failure.value)).contains("from POST http://localhost/orders -> 418")

    def test_a_request_kept_as_a_wsgi_environ(self):
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/orders"}
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Django(status_code=400, environ=environ)).has_status_code(200)
        assert_that(str(failure.value)).contains("from POST /orders -> 400")

    def test_a_wsgi_environ_keeps_its_query_string(self):
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/search", "QUERY_STRING": "q=alice"}
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Django(status_code=500, environ=environ)).has_status_code(200)
        assert_that(str(failure.value)).contains("from GET /search?q=alice -> 500")

    def test_a_wsgi_environ_with_an_empty_query_string(self):
        environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/search", "QUERY_STRING": ""}
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Django(status_code=500, environ=environ)).has_status_code(200)
        assert_that(str(failure.value)).contains("from GET /search -> 500")

    def test_a_redirect_is_not_reported_as_a_request_to_where_it_points(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Redirected()).has_status_code(200)
        assert_that(str(failure.value)).contains("from a response with status 302").does_not_contain("/login")

    def test_an_ordinary_value_says_nothing_about_http(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        assert_that(str(failure.value)).does_not_contain("from ")

    def test_a_soft_block_keeps_the_note(self):
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(Fetched(status_code=500)).has_status_code(200)
        assert_that(str(failure.value)).contains("-> 500")

    def test_the_note_never_reads_the_body(self):
        # the safety rule: a streaming response has not been read, and a failure is no place to find that out
        with pytest.raises(AssertionFailure) as failure:
            assert_that(Streaming()).has_status_code(200)
        assert_that(str(failure.value)).contains("from POST https://api.example.com/orders -> 500")

    @pytest.mark.needs("jsonpath_ng")
    def test_a_response_that_is_falsey_still_carries_its_note(self):
        # `requests.Response` is falsey for every 4xx and 5xx, exactly the one whose provenance a reader needs
        class Refused(Fetched):
            def __bool__(self):
                return False

        response = Refused(status_code=500, body='{"error": "locked"}')
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().at_json_path("$.error").is_equal_to("open")
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 500")


class TestWhatCountsAsAResponse:
    @pytest.mark.parametrize(
        ("status", "headers"),
        [
            ("200", {"Content-Type": "application/json"}),
            (True, {"Content-Type": "application/json"}),
            (42, {"Content-Type": "application/json"}),
            (999, {"Content-Type": "application/json"}),
            (200.0, {"Content-Type": "application/json"}),
            (200, ["Content-Type"]),
            (200, None),
        ],
        ids=[
            "text status",
            "bool status",
            "below any status",
            "above any status",
            "float status",
            "headers as a list",
            "no headers",
        ],
    )
    def test_an_impostor_is_not_read_as_a_response(self, status, headers):
        class Impostor:
            def __init__(self):
                self.status_code, self.headers = status, headers

        with pytest.raises(AssertionFailure) as failure:
            assert_that(Impostor()).is_equal_to(1)
        assert_that(str(failure.value)).does_not_contain("from ")

    def test_a_request_that_raises_when_read_is_survived(self):
        class HalfHostile:
            status_code = 500
            headers = {}  # noqa: RUF012 - a stand-in, and the annotation would be about nothing

            @property
            def request(self):
                raise RuntimeError("no")

        with pytest.raises(AssertionFailure) as failure:
            assert_that(HalfHostile()).has_status_code(200)
        assert_that(str(failure.value)).contains("to be equal to")

    def test_a_status_that_raises_when_read_is_survived(self):
        class Hostile:
            headers = {}  # noqa: RUF012 - a stand-in, and the annotation would be about nothing

            @property
            def status_code(self):
                raise RuntimeError("no")

        with pytest.raises(AssertionFailure) as failure:
            assert_that(Hostile()).is_equal_to(1)
        assert_that(str(failure.value)).contains("to be equal to")

    def test_a_response_that_reads_its_headers_by_key_answers_its_status_by_attribute(self):
        response = Django(status_code=404)
        assert_that(response).has_status_code(404)
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).has_status_code(200)
        assert_that(str(failure.value)).starts_with("Expected <404> to be equal to <200> on attribute <status_code>")


class TestTheStepIntoTheBody:
    @pytest.mark.parametrize(
        "response",
        [Fetched(), Flasked(), Django(), Served()],
        ids=["a parser of its own", "get_json", "raw bytes", "the body under body"],
    )
    def test_every_client_shape_is_parsed(self, response):
        assert_that(response).decoded_as_json().is_equal_to({"id": 7})

    def test_the_parsed_document_keeps_the_whole_surface(self):
        response = Fetched(body='{"id": 7, "items": ["A-1"]}')
        assert_that(response).decoded_as_json().matches_structure({"id": match.is_positive()})

    def test_a_body_that_is_not_json_names_the_content_type_and_the_start(self):
        response = Fetched(body="<!doctype html><html>Login required</html>", content_type="text/html; charset=utf-8")
        with pytest.raises(ValueError, match="the response body is not JSON") as failure:
            assert_that(response).decoded_as_json()
        assert_that(str(failure.value)).contains("text/html; charset=utf-8").contains("<!doctype html>")

    def test_a_body_that_is_not_json_and_declares_no_type(self):
        response = Fetched(body="nope")
        response.headers = {}
        with pytest.raises(ValueError) as failure:
            assert_that(response).decoded_as_json()
        assert_that(str(failure.value)).is_equal_to(
            "the response body is not JSON: no content type was declared and it starts with 'nope'"
        )

    def test_headers_that_carry_no_content_type(self):
        response = Fetched(body="nope")
        response.headers = {"Server": "nginx"}
        with pytest.raises(ValueError, match="no content type was declared"):
            assert_that(response).decoded_as_json()

    def test_headers_that_yield_pairs_rather_than_names(self):
        # werkzeug's Headers iterate as pairs, and reading one as a name reported no content type when one was set
        class Paired:
            def __init__(self, items):
                self._items = items

            def keys(self):
                return [name for name, _ in self._items]

            def __getitem__(self, key):
                return next(value for name, value in self._items if name == key)

            def __iter__(self):
                return iter(self._items)

        response = Fetched(body="nope")
        response.headers = Paired([("Content-Type", "text/html; charset=utf-8")])
        with pytest.raises(ValueError, match="text/html; charset=utf-8"):
            assert_that(response).decoded_as_json()

    def test_headers_that_raise_when_read(self):
        class Hostile:
            def keys(self):
                return []

            def __getitem__(self, key):
                raise RuntimeError("no")

            def __iter__(self):
                raise RuntimeError("no")

        response = Fetched(body="nope")
        response.headers = Hostile()
        with pytest.raises(ValueError, match="no content type was declared"):
            assert_that(response).decoded_as_json()

    def test_a_response_with_no_body_to_read(self):
        class Empty:
            status_code = 204
            headers = {"Content-Type": "application/json"}  # noqa: RUF012 - a stand-in, see above

        with pytest.raises(TypeError) as failure:
            assert_that(Empty()).decoded_as_json()
        assert_that(str(failure.value)).is_equal_to(
            "the response carries no body this can read, under text, content, data or body"
        )

    def test_a_parser_that_answers_none_rather_than_raising(self):
        # Flask's `get_json()` returns None for a body it will not parse, so the raw body has to be asked
        class Careful(Flasked):
            def get_json(self):
                return None

        response = Careful(body=b"<!doctype html>")
        response.headers = {"Content-Type": "text/html"}
        with pytest.raises(ValueError, match="the response body is not JSON"):
            assert_that(response).decoded_as_json()

    def test_a_body_that_is_the_json_null(self):
        class Careful(Flasked):
            def get_json(self):
                return None

        assert_that(Careful(body=b"null")).decoded_as_json().is_none()

    def test_a_body_that_cannot_be_read_at_all_still_refuses_cleanly(self):
        # the refusal must come out and must not name the body: an unread one may well have been JSON
        with pytest.raises(ValueError, match="the response body could not be read") as failure:
            assert_that(Streaming()).decoded_as_json()
        assert_that(str(failure.value)).does_not_contain("is not JSON")

    def test_an_empty_body_is_called_empty_rather_than_unreadable(self):
        response = Fetched(body="")
        with pytest.raises(ValueError) as failure:
            assert_that(response).decoded_as_json()
        assert_that(str(failure.value)).is_equal_to(
            "the response body is not JSON: content-type is 'application/json' and it is empty"
        )

    def test_a_value_that_is_not_a_response_is_refused(self):
        with pytest.raises(TypeError) as failure:
            assert_that(7).decoded_as_json()
        assert_that(str(failure.value)).is_equal_to(
            "val must be an HTTP response, with a status code and headers, but was <7> (int)"
        )

    def test_the_preview_of_a_long_body_is_capped(self):
        response = Fetched(body="x" * 500, content_type="text/plain")
        with pytest.raises(ValueError) as failure:
            assert_that(response).decoded_as_json()
        assert_that(len(str(failure.value))).is_less_than(300)

    def test_negating_the_step_is_refused(self):
        with pytest.raises(TypeError):
            assert_that(Fetched()).not_.decoded_as_json()

    def test_a_body_name_that_is_a_reader_is_not_read_as_the_body(self):
        """``text`` that has to be called is a reader, and the body is under the next name along."""
        assert_that(Reading()).decoded_as_json().is_equal_to({"id": 7})

    def test_the_step_keeps_the_failure_mode_it_was_given(self):
        """A pivot inside a soft block stays soft, so the second failure is collected rather than raised."""
        with pytest.raises(AssertionFailure) as failure, soft_assertions():
            assert_that(Fetched()).decoded_as_json().is_equal_to({"id": 8})
            assert_that(Fetched()).decoded_as_json().is_equal_to({"id": 9})
        assert_that(str(failure.value)).contains("{'id': 8}").contains("{'id': 9}")

    @pytest.mark.parametrize(
        "response",
        [Decoding(body='{"amount": 1.10}'), DecodingFlask(body=b'{"amount": 1.10}')],
        ids=["json", "get_json"],
    )
    def test_the_clients_own_parser_is_what_parses(self, response):
        """A decoder the client configured is honoured, so the document is its answer and not a re-parse."""
        assert_that(response).decoded_as_json().is_equal_to({"amount": Decimal("1.10")})

    @pytest.mark.parametrize(
        "headers",
        [
            Headers([("Content-Type", "text/html; charset=utf-8")]),
            RawHeaders([(b"content-type", b"text/html; charset=utf-8")]),
        ],
        ids=["wsgiref, which does not iterate at all", "raw ASGI pairs, which iterate as bytes"],
    )
    def test_a_header_container_that_answers_only_through_get(self, headers):
        """Iteration finds nothing in either container, so the declared type comes from ``get()``."""
        response = Fetched(body="nope")
        response.headers = headers
        with pytest.raises(ValueError) as failure:
            assert_that(response).decoded_as_json()
        assert_that(str(failure.value)).contains("content-type is 'text/html; charset=utf-8'")


def _configure_django(django):
    """Settings and a URLconf, once per session: django refuses to work without them."""
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=True,
            ALLOWED_HOSTS=["*"],
            DATABASES={},
            INSTALLED_APPS=[],
            ROOT_URLCONF=__name__,
            LOGGING_CONFIG=None,
        )
        django.setup()
        from django.urls import path

        # the URLconf django resolves against: importing `path` before `setup()` is not allowed
        globals()["urlpatterns"] = [path("orders/<int:order_id>/", order_view)]


def order_view(request, order_id):
    """The one view the django test client calls, reached through ``urlpatterns`` below."""
    from django.http import JsonResponse

    return JsonResponse({"id": order_id, "status": "refunded"}, status=500)


class TestTheClientsThemselves:
    """The stand-ins above are shapes; these are the libraries, so the claim is measured not asserted.

    Neither is a dependency of this project, so both are skipped where they are absent. No request is
    made: both libraries build a response object directly.
    """

    @pytest.mark.needs("jsonpath_ng")
    def test_an_httpx_response(self):
        httpx = needs("httpx")
        response = httpx.Response(
            500,
            json={"error": "locked"},
            request=httpx.Request("GET", "https://api.example.com/orders/7"),
        )
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().at_json_path("$.error").is_equal_to("open")
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 500")

    def test_an_httpx_response_that_was_never_read(self):
        # its `.text` raises `ResponseNotRead`, which is the case the note is forbidden to trigger
        httpx = needs("httpx")
        response = httpx.Response(
            503,
            content=iter([b'{"error": "locked"}']),
            request=httpx.Request("GET", "https://api.example.com/orders/7"),
        )
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).has_status_code(200)
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/7 -> 503")

    @pytest.mark.needs("jsonpath_ng")
    def test_an_httpx2_response(self):
        httpx2 = needs("httpx2")
        response = httpx2.Response(
            404,
            json={"error": "no such order"},
            request=httpx2.Request("GET", "https://api.example.com/orders/9"),
        )
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().at_json_path("$.error").is_equal_to("locked")
        assert_that(str(failure.value)).contains("from GET https://api.example.com/orders/9 -> 404")

    def test_a_requests_response(self):
        # a requests response is falsey for every 4xx and 5xx, which is the case a truthiness test loses
        requests = needs("requests")
        response = requests.Response()
        response.status_code = 502
        response._content = b'{"error": "upstream"}'
        response.headers["Content-Type"] = "application/json"
        response.request = requests.Request("POST", "https://api.example.com/orders").prepare()
        assert_that(bool(response)).is_false()
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().is_equal_to({"error": "none"})
        assert_that(str(failure.value)).contains("from POST https://api.example.com/orders -> 502")

    @pytest.mark.needs("jsonpath_ng")
    def test_a_flask_response(self):
        flask = needs("flask")
        app = flask.Flask(__name__)

        @app.route("/orders/<int:order_id>")
        def order(order_id):
            return flask.jsonify({"id": order_id, "status": "refunded"}), 500

        with app.test_client() as client, pytest.raises(AssertionFailure) as failure:
            assert_that(client.get("/orders/7")).decoded_as_json().at_json_path("$.status").is_equal_to("paid")
        assert_that(str(failure.value)).contains("from GET http://localhost/orders/7 -> 500")

    def test_a_flask_response_that_is_not_json(self):
        flask = needs("flask")
        app = flask.Flask(__name__)

        @app.route("/private")
        def private():
            return "<!doctype html><html>Session expired</html>", 200

        with app.test_client() as client, pytest.raises(ValueError) as failure:
            assert_that(client.get("/private")).decoded_as_json()
        assert_that(str(failure.value)).contains("text/html").contains("Session expired")

    def test_a_django_response(self):
        django = needs("django")
        _configure_django(django)
        from django.http import JsonResponse

        response = JsonResponse({"error": "locked"}, status=502)
        assert_that(response).has_status_code(502)
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().is_equal_to({"error": "open"})
        assert_that(str(failure.value)).contains("from a response with status 502")

    @pytest.mark.needs("jsonpath_ng")
    def test_a_django_response_through_its_test_client(self):
        django = needs("django")
        _configure_django(django)
        from django.test import Client

        response = Client().get("/orders/7/", {"q": "alice"})
        with pytest.raises(AssertionFailure) as failure:
            assert_that(response).decoded_as_json().at_json_path("$.status").is_equal_to("paid")
        assert_that(str(failure.value)).contains("from GET /orders/7/?q=alice -> 500")

    def test_a_starlette_test_client_response(self):
        starlette = needs("starlette")
        needs("httpx2")
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        app = Starlette(routes=[Route("/orders/{order_id:int}", lambda request: JSONResponse({"id": 7}, 500))])
        client = TestClient(app, raise_server_exceptions=False)
        with pytest.raises(AssertionFailure) as failure:
            assert_that(client.get("/orders/7")).decoded_as_json().is_equal_to({"id": 9})
        assert_that(str(failure.value)).contains("-> 500")
        assert_that(starlette.__name__).is_equal_to("starlette")
