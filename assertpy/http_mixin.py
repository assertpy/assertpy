"""What a failure says about the HTTP response it came from, and the one step into that response's body.

Duck-typed, like the pydantic and attrs support: nothing here imports httpx, requests, Starlette, Flask
or Django, and installing any of them next to this library costs nothing.  A response is recognised by
what it *is* rather than by what it is called, and by the values of those attributes rather than by
their names alone.  Names alone are not enough: a ``DataFrame`` with columns called ``status_code`` and
``headers`` answers to both, a ``MagicMock`` answers to anything at all, and attaching an authoritative
HTTP reading to somebody else's failure is worse than saying nothing.

The provenance line reads no body and starts no I/O.  That is not caution, it is the only correct rule:
a streaming httpx response raises ``ResponseNotRead`` when its ``.text`` is touched, a chunked requests
body is consumed by reading it, and a body has no size limit.  A failure being reported is not the place
to discover any of that.  Reading the body is what `decoded_as_json()` does, and calling it is the
caller saying they want it read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Protocol, cast

from ._engine._mixin_base import _MixinBase
from ._engine._require import refuse
from .errors import _truncated

if TYPE_CHECKING:
    from .assertpy import AssertionBuilder


class _Response(Protocol):
    """The shape every client family shares, and all this module ever reads from a response."""

    status_code: int
    headers: object


__tracebackhide__ = True

# the range HTTP defines; outside it the number is somebody else's and the line would be a guess
_STATUS_RANGE: Final = range(100, 600)
_BODY_PREVIEW: Final = 120


def _mapping_shaped(value: object) -> bool:
    """Whether this answers to the two operations a headers mapping is used through."""
    return hasattr(value, "keys") and hasattr(value, "__getitem__")


def response_of(value: object) -> _Response | None:
    """*value* when it is an HTTP response, else ``None``.

    Both attributes are read and both are checked: an integer status inside the range HTTP defines, and
    headers that behave like a mapping.  ``bool`` is excluded because it is an ``int`` and no status is
    a boolean.  Every read is guarded, since a property runs the caller's code and this is asked on the
    way to a failure that must survive whatever it does.
    """
    try:
        status = getattr(value, "status_code", None)
        if not isinstance(status, int) or isinstance(status, bool) or status not in _STATUS_RANGE:
            return None
        return cast("_Response", value) if _mapping_shaped(getattr(value, "headers", None)) else None
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None


def _request_line(response: _Response) -> str:
    """``METHOD URL`` for the request this answered, or as much of it as the client kept.

    Only the request is read, never ``response.url``: on a Django redirect that attribute is where the
    response points, so a call to ``/private`` answered with ``302`` to ``/login`` would be reported as
    having been a call to ``/login``.  Django keeps the request as its WSGI environ rather than as an
    object, which is the second shape read here.
    """
    request = getattr(response, "request", None)
    method = getattr(request, "method", None)
    url = getattr(request, "url", None)
    if method is None and url is None and isinstance(request, Mapping):
        method, url = request.get("REQUEST_METHOD"), request.get("PATH_INFO")
        # without the query two different calls to one endpoint read as the same call
        query = request.get("QUERY_STRING")
        if url is not None and query:
            url = f"{url}?{query}"
    parts = [str(part) for part in (method, url) if part is not None]
    return " ".join(parts)


def response_note(response: _Response) -> str | None:
    """The provenance line for a failure whose value came from *response*, or ``None``.

    Never the body: see the module docstring for why that rule is not negotiable.
    """
    try:
        status = response.status_code
        asked = _request_line(response)
        return f"from {asked} -> {status}" if asked else f"from a response with status {status}"
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return None


def _content_type(response: _Response) -> str:
    """The declared content type, or ``""``.

    Three shapes, because header containers disagree about what they are.  ``get()`` where there is one,
    since every client's container is case-insensitive through it.  Then iteration, which yields names
    in a plain mapping and ``(name, value)`` pairs in werkzeug's ``Headers``: reading a pair as a name
    is how this silently reported that no type had been declared when one had.
    """
    try:
        headers = cast("dict[str, str]", response.headers)
        getter = getattr(headers, "get", None)
        found = getter("content-type") if callable(getter) else None
        if found:
            return str(found)
        for item in headers:
            name, value = item if isinstance(item, tuple) and len(item) == 2 else (item, None)
            if str(name).lower() == "content-type":
                return str(headers[name] if value is None else value)
    except Exception:  # a header mapping of somebody else's may raise from anything
        return ""
    return ""


class _NoBodyError(Exception):
    """The response keeps its body under none of the names read here, so there is nothing to parse."""


def _raw_body(response: _Response) -> object:
    """The body as the client kept it, under whichever of the four names this client uses."""
    for name in ("text", "content", "data", "body"):
        found = getattr(response, name, None)
        if found is not None and not callable(found):
            return found
    return None


def _preview(response: _Response) -> str | None:
    """How the body starts, or ``None`` when it cannot be read at all.

    A body that was never read raises from every name it might be under, and this runs while a refusal
    is being built: losing the refusal to the preview would be the worst of both.  ``None`` and the
    empty string are different answers here, since a body that is empty was read and one that raised
    was not, and only one of those two says anything about what the body holds.
    """
    try:
        body = _raw_body(response)
    except Exception:  # the same rule as everywhere here: the report survives whatever the value does
        return None
    return _truncated(str(body)[:_BODY_PREVIEW], _BODY_PREVIEW) if body is not None else None


def _parsed(response: _Response) -> object:
    """The body as a document, through the client's own parser where it has one.

    ``json()`` in httpx, requests and both test clients; ``get_json()`` in Flask; and the raw body
    parsed here for the clients that keep no parser of their own.  A parser of somebody else's is
    allowed to raise anything at all, so anything it raises is read as "this is not JSON" rather than
    propagated as itself.
    """
    for name in ("json", "get_json"):
        parser = getattr(response, name, None)
        if callable(parser):
            document = parser()
            # Flask answers `None` rather than raising, and a body of literal `null` parses to `None` too
            if document is not None:
                return document
            break
    body = _raw_body(response)
    if not isinstance(body, (str, bytes, bytearray)):
        raise _NoBodyError
    return json.loads(body)


class HttpMixin(_MixinBase):
    """Assertions and steps for an HTTP response."""

    def decoded_as_json(self) -> AssertionBuilder[object]:
        """Parse the response body and return a new builder holding the parsed document.

        The step every API test takes, made part of the chain so that what it finds is asserted on with
        the response still in hand: a failure below this line says which request it came from and what
        that request answered.

        Examples:
            Usage:

                assert_that(response).decoded_as_json().matches_structure({"id": match.is_positive()})
                assert_that(response).decoded_as_json().at_json_path("$.items[0].sku").is_equal_to("A-1")

        Returns:
            AssertionBuilder: a new instance holding the parsed body.  Typed over ``object`` rather than
                over the response, for the reason `at_json_path()` is typed the way it is: a document is
                whatever the body held, so a step that cannot know its result must not go on promising
                the shape of its subject.

        Raises:
            TypeError: if val is not an HTTP response
            ValueError: if the body is not JSON, naming the content type and how the body starts
        """
        response = response_of(self.val)
        if response is None:
            refuse(self.val, "an HTTP response, with a status code and headers")
        try:
            document = _parsed(response)
        except _NoBodyError:
            raise TypeError("the response carries no body this can read, under text, content, data or body") from None
        except Exception as exc:
            # the two together name the usual cause: an expired session answered with a login page
            declared = _content_type(response)
            named = f"content-type is {declared!r}" if declared else "no content type was declared"
            preview = _preview(response)
            if preview is None:
                # nothing is claimed about a body nobody could read: it may well have been JSON
                raise ValueError(f"the response body could not be read: {named}") from exc
            shown = f"it starts with {preview!r}" if preview else "it is empty"
            raise ValueError(f"the response body is not JSON: {named} and {shown}") from exc
        # `builder()` is declared to hand back the same kind, wrong for a step whose result holds the document
        return cast("AssertionBuilder[object]", self.builder(document, self.description, self.kind, logger=self.logger))
