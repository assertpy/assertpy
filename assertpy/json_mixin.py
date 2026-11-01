from __future__ import annotations

import decimal
import fractions
import functools
import json
import operator
import re
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Final, cast

from ._engine._mixin_base import _MixinBase
from ._engine._ordering import _exact_real
from ._engine._require import argument, require_type
from .errors import DiffEntry, DiffResult

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ._engine._compat import Self

__tracebackhide__ = True


_OPENAPI_VERSION: Final = re.compile(r"3\.([012])(?:\.\d+)?")
"""The versions whose dialect this reads, matched whole: a patch number is allowed and nothing else is."""

_SWAGGER_2: Final = re.compile(r"2\.0(?:\.\d+)?")
"""Swagger's one version, read the same way, so "20" is not it."""

_RFC_3339_TIME: Final = r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:[Zz]|([+-])([0-9]{2}):([0-9]{2}))"
"""A `time` as RFC 3339 writes its ``full-time``: a time to the second, then `Z` or an offset."""

_RFC_3339_MOMENT: Final = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]" + _RFC_3339_TIME)
"""A `date-time` as RFC 3339 writes it: a full date, a `T`, then `_RFC_3339_TIME`."""

# The four below are texts that `re` compiles at first use: compiled at import they cost 0.5 ms.
_DURATION: Final = (
    r"(?ai:P(?:"
    r"(?:[0-9]+D|[0-9]+M(?:[0-9]+D)?|[0-9]+Y(?:[0-9]+M(?:[0-9]+D)?)?)"
    r"(?:T(?:[0-9]+H(?:[0-9]+M(?:[0-9]+S)?)?|[0-9]+M(?:[0-9]+S)?|[0-9]+S))?"
    r"|T(?:[0-9]+H(?:[0-9]+M(?:[0-9]+S)?)?|[0-9]+M(?:[0-9]+S)?|[0-9]+S)"
    r"|[0-9]+W))"
)
"""A `duration` by the ABNF of RFC 3339, appendix A, which the format is defined by.

Narrower than ISO 8601 where the ABNF is: a unit may be followed only by the next smaller one, so ``P1Y2D`` and
``PT1H2S`` are no durations, weeks stand alone, and there is no fraction and no sign.  A letter is taken in
either case: a quoted letter of an ABNF stands for both (RFC 5234), which is the ground the ``t`` and ``z`` of a
`date-time` are taken on.  In either case of ASCII alone: the long ``s`` of Unicode folds to ``S`` and is none.
"""

_HOSTNAME: Final = (
    r"(?![\s\S]{254})"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
"""A `hostname` by RFC 1123, section 2.1: labels of ASCII letters, digits and hyphens, a hyphen at neither end,
63 characters at most, joined by dots with none after the last, and 253 characters in all.  What an ``xn--``
label may decode to is asked apart, where the dialect asks it (`_is_hostname`)."""


def _mailbox_pattern() -> str:
    """An `email` by the ``Mailbox`` of RFC 5321, section 4.1.2: a local part, an ``@``, then a domain or an
    address in brackets.

    The local part is atoms joined by dots or a quoted string, and the domain is `_HOSTNAME`.  ASCII alone: an
    address with other letters is for the format `idn-email`.  The grammar has no lengths, and the 64 that SMTP
    allows a local part is not held: the domain has the lengths of a host name, as under the format `hostname`.

    The atoms are one run of their characters and their dots, and a quoted string one run of what may stand in
    it, with what a backslash quotes there judged apart (`_is_email`).

    The address is an IPv4 one, or ``IPv6:`` and an IPv6 one as section 4.1.3 writes it, which is narrower than
    RFC 4291: ``::`` stands for two groups at least, so six stand beside it at most, and four before an IPv4
    address.  No other tag is registered, so none is taken.
    """
    atoms = r"[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~.]+"
    octet = "(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])"
    ipv4 = rf"{octet}(?:\.{octet}){{3}}"
    group = "[0-9A-Fa-f]{1,4}"

    def groups(count: int) -> str:
        return f"{group}(?::{group}){{{count - 1}}}" if count else ""

    ipv6 = "|".join(
        [
            groups(8),
            f"{groups(6)}:{ipv4}",
            *(f"{groups(left)}::(?:{group}(?::{group}){{0,{5 - left}}})?" for left in range(6)),
            f"{groups(6)}::",
            *(f"{groups(left)}::(?:{group}:){{0,{4 - left}}}{ipv4}" for left in range(5)),
        ]
    )
    return (
        # no group repeats: as one, a megabyte of atoms held 63 MB of the engine's stack, and one in quotes 122
        rf'(?:(?!\.)(?![^@]*\.[.@]){atoms}|"(?P<quoted>[ -~]*)")@'
        rf"(?:{_HOSTNAME}|\[(?:{ipv4}|(?ai:IPv6):(?:{ipv6}))\])"
    )


_MAILBOX: Final = _mailbox_pattern()


def _uri_pattern() -> str:
    """A `uri` by the ABNF of RFC 3986, appendix A: a scheme, then an authority and a path, a path alone or
    nothing, then a query and a fragment.  What stands in brackets as the host is judged apart (`_is_uri`).

    A path is written as one run of its characters and its slashes, which is what the segments of the ABNF
    come to, and the two hex digits after a ``%`` are asked for once, ahead of the rest.
    """
    # no group repeats: with a segment or a `%XX` as one, a megabyte of either held 60 to 280 MB of the engine's stack
    plain = r"A-Za-z0-9\-._~!$&'()*+,;=%"
    path = f"[{plain}:@/]*"
    return (
        r"(?![\s\S]*%(?![0-9A-Fa-f]{2}))"
        r"[A-Za-z][A-Za-z0-9+.\-]*:"
        rf"(?://(?:[{plain}:]*@)?(?:\[(?P<literal>[^\]]*)\]|[{plain}]*)(?::[0-9]*)?(?:/{path})?"
        f"|/(?:[{plain}:@]{path})?"
        f"|[{plain}:@]{path}"
        "|)"
        rf"(?:\?[{plain}:@/?]*)?(?:#[{plain}:@/?]*)?"
    )


_URI: Final = _uri_pattern()


_DAYS_IN: Final = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_UNHEARD: Final = frozenset(
    {
        "const",
        "contains",
        "propertyNames",
        "if",
        "dependentRequired",
        "dependentSchemas",
        "unevaluatedProperties",
        "unevaluatedItems",
        "prefixItems",
        "$dynamicRef",
        "$recursiveRef",
    }
)
"""Keywords of later JSON Schema, drafts 6 to 2020-12, that can forbid a value and that Draft 4 does not have.

Draft 4 is the reading of OpenAPI 3.0 and of Swagger 2.0, and a keyword it does not know it passes over: a
3.0 schema with ``const: a`` took ``b``.  Each one here was measured to pass a value its own draft refuses.
A schema holding one is refused wherever it stands and whatever it would forbid there: ``if: {}`` forbids
nothing and is refused as well.  ``then``, ``else``, ``minContains`` and ``maxContains`` are left out, since
they do nothing without ``if`` or ``contains``, which are here.
"""


def _time_read(read: re.Match[str], first: int) -> tuple[int, int] | None:
    """The minute of the day a time stands at counted in UTC, beside its second.

    Read off the groups of `_RFC_3339_TIME`, which open at *first* in the match.  ``None`` where a field is
    past its range.  A second of ``60`` is within it: whether a leap second may stand there is for the
    caller, who knows the day.  The minute runs from -1439 to 2878, since an offset moves a time out of the
    day it is written in.
    """
    hour, minute, second = int(read[first]), int(read[first + 1]), int(read[first + 2])
    offset_hour, offset_minute = int(read[first + 4] or 0), int(read[first + 5] or 0)
    if hour > 23 or minute > 59 or second > 60 or offset_hour > 23 or offset_minute > 59:
        return None
    offset = (offset_hour * 60 + offset_minute) * (-1 if read[first + 3] == "-" else 1)
    return hour * 60 + minute - offset, second


def _is_rfc_3339_time(value: object) -> bool:
    """Whether a text is an RFC 3339 ``full-time``, which is what the format `time` names.

    The offset is required, as it is in a `date-time`.  A second of ``60`` is taken in the last minute of a
    day counted in UTC: with no date beside it, that is all that can be asked of a leap second.
    """
    if not issubclass(type(value), str):
        return True
    read = re.fullmatch(_RFC_3339_TIME, cast("str", value))
    stands = None if read is None else _time_read(read, 1)
    return stands is not None and (stands[1] < 60 or stands[0] in (1439, -1))


def _is_rfc_3339_moment(value: object) -> bool:
    """Whether a text is an RFC 3339 `date-time`.  What is no text is not this format's to judge.

    The grammar is the RFC's, read off its ABNF: lower-case ``t`` and ``z`` are allowed, a space for the ``T``
    is not, the offset is required, a fraction of a second is of any length, and the year runs from ``0000``.
    A second of ``60`` is taken where the RFC allows a leap second: in the last minute of a month, counted in
    UTC.  Which months held one is not asked.
    """
    if not issubclass(type(value), str):
        return True
    read = _RFC_3339_MOMENT.fullmatch(cast("str", value))
    if read is None:
        return False
    year, month, day = int(read[1]), int(read[2]), int(read[3])
    stands = _time_read(read, 4)
    if stands is None or not 1 <= month <= 12:
        return False
    in_utc, second = stands
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last = _DAYS_IN[month - 1] + (month == 2 and leap)
    ends_a_month = (in_utc == 1439 and day == last) or (in_utc == -1 and day == 1)
    return 1 <= day <= last and (second < 60 or ends_a_month)


def _written_as(pattern: str) -> Any:
    """A check that a text is written whole as *pattern* writes it.  What is no text is not a format's to judge.

    The text is read by the pattern alone, so a class of its own has no say in its length or its letters.
    """

    def written(value: object) -> bool:
        return not issubclass(type(value), str) or re.fullmatch(pattern, cast("str", value)) is not None

    return written


_is_duration: Final = _written_as(_DURATION)


def _is_email(value: object) -> bool:
    """Whether a text is a mailbox of RFC 5321: `_MAILBOX`, and a quoted local part one in which each backslash
    quotes the character after it and no quote stands bare.

    jsonschema asks a text for an ``@`` and no more, so ``@`` and ``a b@c`` passed for an address.
    """
    if not issubclass(type(value), str):
        return True
    read = re.fullmatch(_MAILBOX, cast("str", value))
    if read is None:
        return False
    quoting = False
    for character in read.group("quoted") or "":
        if not quoting and character == '"':
            return False
        quoting = not quoting and character == "\\"
    return not quoting


def _is_hostname(value: object) -> bool:
    """Whether a text is a host name: `_HOSTNAME`, and each label that opens ``xn--`` an A-label of IDNA 2008.

    The reading of JSON Schema since 2019, which has the format take in "host names produced using the
    Punycode algorithm": such a label has to decode, and to what RFC 5891 allows in a label.  Before that
    the format is the syntax alone, and so it is under OpenAPI 3.0 and Swagger 2.0 (`_openapi_formats`).

    The rules need tables of Unicode, which the `idna` package carries, so the answer for a code point is the
    one of the release installed.  A newer release takes what Unicode has assigned since: from 3.7 to 3.20
    that is 21 407 code points more, and none fewer.
    """
    if not issubclass(type(value), str):
        return True
    text = cast("str", value)
    if re.fullmatch(_HOSTNAME, text) is None:
        return False
    encoded = [] if str.find(text, "--") < 0 else re.findall(r"(?<![^.])[Xx][Nn]--[^.]*", text)
    if not encoded:
        return True
    try:
        import idna  # 2 ms at the first such label of a process, and nothing for a host name without one
    except ImportError:
        raise ImportError(
            "idna is required to check an `xn--` label of a hostname. Install it with: pip install assertpy[json]"
        ) from None
    try:
        for label in encoded:
            idna.decode(label)
    except UnicodeError:
        # every refusal of `idna` is one, and its releases before 3.3 let the codec's own out as it was
        return False
    return True


def _is_uri(value: object) -> bool:
    """Whether a text is a URI of RFC 3986: `_URI`, and a host in brackets that is an IPv6 address or an IPvFuture.

    The address is asked of `ipaddress`, once its text is hex digits, colons and dots alone: a zone, which
    `ipaddress` takes, is no part of the address as RFC 3986 writes it.
    """
    if not issubclass(type(value), str):
        return True
    read = re.fullmatch(_URI, cast("str", value))
    if read is None:
        return False
    literal = read.group("literal")
    if literal is None or re.fullmatch(r"[vV][0-9A-Fa-f]+\.[A-Za-z0-9\-._~!$&'()*+,;=:]+", literal) is not None:
        return True
    if re.fullmatch(r"[0-9A-Fa-f:.]+", literal) is None:
        return False
    import ipaddress  # 0.8 ms, kept off `import assertpy`: an address in brackets alone asks it

    try:
        ipaddress.IPv6Address(literal)
    except ValueError:
        return False
    return True


def _fits_in(bits: int) -> Any:
    """The check of OpenAPI's ``int32`` or ``int64``: a whole number within the signed range of *bits*.

    The number is read through `int` or `float` itself: a class of the caller's may answer ``<=`` or
    ``is_integer`` with code of its own.  A bool is an `int` to Python and a truth value to JSON, where it is
    no number.
    """
    low, high = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1

    def fits(value: Any) -> bool:
        kind = type(value)
        if issubclass(kind, int) and not issubclass(kind, bool):
            return low <= int.__add__(value, 0) <= high
        if issubclass(kind, float) and float.is_integer(value):
            return low <= float.__add__(value, 0.0) <= high
        return True

    return fits


def _openapi_formats(jsonschema_mod: Any, *, a_labels: bool) -> Any:
    """jsonschema's format checker, with the formats it leaves unchecked that a contract most often declares.

    `int32` and `int64` are OpenAPI's own, and jsonschema knows neither: ``2**40`` passed for an `int32`.
    `date-time`, `uri`, `hostname` and `duration` it checks only beside a package each, none of which this
    library installs, so ``"yesterday"`` passed for a moment and ``"not a uri"`` for a URI.  The checks here
    stand whether such a package is there or not, so a text is not judged by what else is installed.  The
    rest of what jsonschema checks beside a package of its own stays unchecked where that package is missing.

    `time` it checks everywhere, and by the rule of Draft 3: ``HH:MM:SS`` and no more, so ``10:00:00Z``
    failed and ``10:00:00`` passed, where the format has been RFC 3339's ``full-time`` since Draft 7.  `email`
    it checks everywhere too, by asking for an ``@``.

    *a_labels* is whether a `hostname` holds its ``xn--`` labels to IDNA: the dialect of OpenAPI 3.1 does,
    the one of 3.0 and Swagger 2.0 has the format as the syntax of a host name and no more.
    """
    checker = jsonschema_mod.FormatChecker()
    checker.checks("int32")(_fits_in(32))
    checker.checks("int64")(_fits_in(64))
    checker.checks("date-time")(_is_rfc_3339_moment)
    checker.checks("time")(_is_rfc_3339_time)
    checker.checks("duration")(_is_duration)
    checker.checks("email")(_is_email)
    checker.checks("hostname")(_is_hostname if a_labels else _written_as(_HOSTNAME))
    checker.checks("uri")(_is_uri)
    return checker


def _as_written(number: Any) -> fractions.Fraction | None:
    """A number exactly, and a float as the decimal it prints as: ``None`` for one that is not finite.

    A float prints as the shortest decimal that reads back as it, which is the number a document wrote unless
    that had more digits than a float keeps: ``0.30000000000000004`` stays what it is, and no ``0.3``.  The
    print is `float`'s own, whatever the class of the value.
    """
    if issubclass(type(number), float):
        try:
            # through `Decimal`, which reads the text in C: `Fraction` reading it cost a number 0.4 us more
            return fractions.Fraction(decimal.Decimal(float.__repr__(number)))
        except (ValueError, OverflowError):
            return None
    exact = _exact_real(number)
    return exact[1] if isinstance(exact, tuple) and not exact[0] else None


@functools.lru_cache(maxsize=64)
def _step_written(divisor: float) -> fractions.Fraction | None:
    """`_as_written` of a ``multipleOf`` that is a plain `int` or `float`, kept: read again for each number a
    schema holds to it, it cost the number 0.7 us."""
    return _as_written(divisor)


def _a_reference_alone(schema: Any) -> Any:
    """What Draft 4 reads of a schema: its ``$ref`` alone where it has one, and every keyword where it has none."""
    ref = schema.get("$ref")
    return schema.items() if ref is None else [("$ref", ref)]


@functools.cache
def _dividing_as_written(validator_cls: Any, *, redeclared: bool = False) -> Any:
    """*validator_cls* with a ``multipleOf`` that divides the numbers as they are written (`_as_written`).

    jsonschema divides two floats and asks whether the quotient is whole, and ``19.99 / 0.01`` is
    ``1998.9999999999998``: a price failed the ``multipleOf: 0.01`` it meets.  The class is made once: made
    for each check it cost the check 213 us.

    A ``multipleOf`` that is no number above zero is refused, as every draft has the keyword.  jsonschema
    raised `ZeroDivisionError` for a zero, took a negative one by its size and passed every number for an
    infinity.

    jsonschema hands a schema that declares a ``$schema`` to the class it keeps for that dialect, whose
    division is its own.  With *redeclared*, the schema goes to the class made here from that one instead,
    whichever of the drafts that have the keyword it declares: the one the document is read by or another.
    That is asked of every schema entered, at 0.1 to 0.2 us each, so it is for a document that may hold a ``$schema``
    and no other.

    Made by ``create()`` with what Draft 4 reads beside a ``$ref`` handed in.  ``extend()`` of jsonschema 4.18,
    the oldest the ``json`` extra takes, makes a class that has lost it and validates what stands there.
    """
    jsonschema_mod = _ensure_jsonschema()
    import attrs
    from jsonschema.validators import create

    def multiple_of(validator: Any, divisor: Any, instance: Any, schema: Any) -> Iterator[Any]:
        if not validator.is_type(instance, "number"):
            return
        if type(divisor) in (int, float):
            step = _step_written(divisor)
        else:
            step = _as_written(divisor) if validator.is_type(divisor, "number") else None
        if step is None or step <= 0:
            raise ValueError(f"multipleOf <{divisor!r}> is no number above zero, which is what the keyword takes")
        read = _as_written(instance)
        if read is None or read.numerator * step.denominator % (read.denominator * step.numerator):
            yield jsonschema_mod.ValidationError(f"{instance!r} is not a multiple of {divisor}")

    keywords: dict[str, Any] = {**validator_cls.VALIDATORS, "multipleOf": multiple_of}
    # the drafts that read a `$ref` alone.  Draft 3 has no `multipleOf` and is left to jsonschema
    alone = (jsonschema_mod.Draft4Validator, jsonschema_mod.Draft6Validator, jsonschema_mod.Draft7Validator)
    divided = (*alone, jsonschema_mod.Draft201909Validator, jsonschema_mod.Draft202012Validator)
    made: Any = create(
        meta_schema=validator_cls.META_SCHEMA,
        validators=keywords,
        type_checker=validator_cls.TYPE_CHECKER,
        format_checker=validator_cls.FORMAT_CHECKER,
        id_of=validator_cls.ID_OF,
        # named in either case, the later drafts with what jsonschema itself defaults to: every keyword
        applicable_validators=_a_reference_alone if validator_cls in alone else operator.methodcaller("items"),
    )
    as_jsonschema_evolves = made.evolve

    def evolve(validator: Any, **changes: Any) -> Any:
        evolved = as_jsonschema_evolves(validator, **changes)
        named = type(evolved)
        if named not in divided:
            return evolved
        ours = _dividing_as_written(named, redeclared=True)
        return ours(**{field.alias: getattr(evolved, field.name) for field in attrs.fields(named) if field.init})

    if redeclared:
        made.evolve = evolve
    return made


def _parsed_json_path(path: str):
    """The compiled expression, refusing a path that is not a string before the cache hashes it.

    A list reached the cache first and came back as "unhashable type: 'list'", which names the cache
    rather than the argument.
    """
    require_type(path, str, "a string", subject=argument("path"))
    return _compiled_json_path(path)


@functools.lru_cache(maxsize=256)
def _compiled_json_path(path: str):
    """The compiled form of a JSON path expression, kept across calls.

    Parsing is most of the cost of a path assertion and the lookup is a rounding error: on a twenty-record
    document a parse measures 0.15 ms against 0.002 ms for the search, and 5.8 ms under a ``jsonpath_ng``
    old enough to build a fresh PLY lexer and parser every time it is asked.  Expressions are immutable
    and ``find()`` does not mutate them, so one compiled expression serves every call with that path.

    Bounded rather than unbounded: a path built from test data (``$.users[7].name``) is a fresh string
    each time, and an unbounded cache would grow with the suite.
    """
    return _ensure_jsonpath_ng().parse(path)


def _ensure_jsonpath_ng():
    try:
        import jsonpath_ng.ext.parser  # optional dependency
    except ImportError:
        raise ImportError(
            "jsonpath-ng is required for JSON path assertions. Install it with: pip install assertpy[json]"
        ) from None
    return jsonpath_ng.ext.parser


def _ensure_jsonschema():
    try:
        import jsonschema  # optional dependency
    except ImportError:
        raise ImportError(
            "jsonschema is required for JSON schema assertions. Install it with: pip install assertpy[json]"
        ) from None
    return jsonschema


def _nullable_as_null(schema: dict[str, Any], keyword: str, *, by_the_text: bool) -> None:
    """Rewrite ``nullable: true`` of one Schema Object into JSON Schema, in place (jsonschema ignores the keyword).

    ``"null"`` is added to the ``type`` beside it, which keeps per-keyword error paths precise: a bad ``format``
    on a nullable field still reports ``format``, not a vague union.  An ``enum`` is left as written.  OpenAPI
    3.0.3 has ``nullable`` add to the type alone, "other Schema Object constraints retain their defined
    behavior", so ``null`` is allowed where the enum lists it.

    With no ``type`` of its own the keyword does nothing by that text.  One reading is kept wider on purpose: a
    schema that is a ``$ref`` or an ``allOf``, ``anyOf`` or ``oneOf`` becomes a union with ``null``, which is how
    a nullable reference is written in practice.  Of a composition the union takes the place of ``allOf``,
    ``anyOf`` and ``oneOf`` alone: what else the schema holds stays beside it and is asked of ``null`` too, so
    an ``enum`` there allows ``null`` only where it lists it, and a ``not`` still refuses what it refuses.  A
    ``$ref`` goes into the union with everything beside it: OpenAPI 3.0 ignores what stands beside a reference.

    *by_the_text* leaves that wider reading out: ``nullable`` with no ``type`` beside it then does nothing.

    Swagger 2.0 spells the idea ``x-nullable``.  It is an extension with no text of its own and keeps the
    reading it had: ``null`` passes its enum, and any schema with no ``type`` becomes the union, whatever
    *by_the_text* says.
    """
    nullable = schema.get(keyword)
    if not isinstance(nullable, bool):
        return
    del schema[keyword]
    if not nullable:
        return
    extension = keyword == "x-nullable"
    held = schema.get("type")
    if isinstance(held, (str, list)):
        schema["type"] = [*([held] if isinstance(held, str) else held), "null"]
        enum = schema.get("enum")
        if extension and isinstance(enum, list) and None not in enum:
            schema["enum"] = [*enum, None]
    elif by_the_text and not extension:
        return
    elif extension or "$ref" in schema:
        inner = dict(schema)
        schema.clear()
        schema["anyOf"] = [inner, {"type": "null"}]
    else:
        composed = {key: schema.pop(key) for key in ("allOf", "anyOf", "oneOf") if key in schema}
        if composed:
            schema["anyOf"] = [composed, {"type": "null"}]


def _stringify_keys(node: Any) -> Any:
    """Recursively convert all mapping keys to strings.

    YAML parses a numeric-looking key such as a status code (``200:``) as an ``int``, but OpenAPI and
    JSON-Schema keys are semantically strings and the JSON-Pointer resolver matches string segments.
    """
    if isinstance(node, dict):
        return {str(key): _stringify_keys(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_stringify_keys(item) for item in node]
    return node


def _refers_to(part: Any) -> list[str] | None:
    """Every ``$ref`` held anywhere in *part*, as data, or ``None`` where places alone do not say what it reads.

    That is under JSON Schema 2020-12 a schema with an ``$id``, which is the base of the references under it,
    a ``$dynamicRef``, which is followed like a reference and names its schema another way, and a ``$schema``:
    jsonschema reads a schema by the dialect it declares, and another dialect has other ways to refer, the
    ``$recursiveRef`` of 2019-09 to the root of the document among them.  Read as data and not by the keywords
    that hold a schema, so a reference inside an ``example`` counts as well: more is copied than is read, and
    never less.
    """
    found: list[str] = []
    pending = [part]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if "$id" in node or "$dynamicRef" in node or "$schema" in node:
                return None
            ref = node.get("$ref")
            if isinstance(ref, str):
                found.append(ref)
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return found


def _named_by_its_keys(holder: Any, sound: set[int]) -> bool:
    """Whether a text key of *holder* names in a part cut out below it what it names in the copy of the whole.

    Not where a key of it is no text: the copy turns keys to text and keeps the later of two that read alike,
    so ``7`` beside ``"7"`` names another schema there.  And not where the mapping is a schema with an ``id``
    or ``$id`` of its own: a reference under it is read from that base, which a part cut out below it does
    not carry.  *sound* holds the mappings found so, and each is gone through once a check: a mapping of
    20 000 schemas costs 0.2 ms.
    """
    if id(holder) in sound:
        return True
    if not isinstance(holder, dict) or isinstance(holder.get("id"), str) or isinstance(holder.get("$id"), str):
        return False
    if not set(map(type, holder)) <= {str}:
        return False
    sound.add(id(holder))
    return True


def _responses_read(spec: Any, path: Any, method: Any, sound: set[int]) -> dict[str, Any] | None:
    """The responses of one operation and what the spec says of itself, copied to the places they have in it.

    ``None`` where the operation is not found as written, or a mapping on the way to it does not name by its
    keys what it would in the whole (`_named_by_its_keys`).
    """
    if not (isinstance(path, str) and isinstance(method, str)):
        return None
    operation: Any = spec
    for key in ("paths", path, method.lower()):
        if not _named_by_its_keys(operation, sound) or key not in operation:
            return None
        operation = operation[key]
    if not _named_by_its_keys(operation, sound):
        return None
    read = {key: _stringify_keys(operation[key]) for key in ("responses", "produces") if key in operation}
    part = {key: _stringify_keys(spec[key]) for key in ("openapi", "swagger", "produces") if key in spec}
    part["paths"] = {path: {method.lower(): read}}
    return part


def _taken_to(part: dict[str, Any], spec: Any, segments: list[str], sound: set[int]) -> tuple[tuple[str, ...], Any]:
    """Copy what *segments* name in *spec* to the same place in *part*: the place copied whole, and the copy.

    A list on the way is the place, and is copied whole: a place in a list is a number, and a part of a list
    has other numbers.  The copy is ``None`` where a mapping on the way does not name by its keys what it
    would in the whole (`_named_by_its_keys`), and nothing is copied.
    """
    holder, taken, depth = spec, part, 0
    while _named_by_its_keys(holder, sound):
        child = holder[segments[depth]]
        if depth == len(segments) - 1 or isinstance(child, list):
            taken[segments[depth]] = _stringify_keys(child)
            return tuple(segments[: depth + 1]), taken[segments[depth]]
        holder, taken, depth = child, taken.setdefault(segments[depth], {}), depth + 1
    return (), None


def _part_read(spec: Any, path: Any, method: Any) -> dict[str, Any] | None:
    """The part of a spec that a check of one operation reads, copied with its keys as text.

    The responses of the operation, and whatever they refer to, each at the place it has in the spec, so a
    pointer names in the part what it names in the whole.  The rest is never looked at: copied whole on every
    call, a spec of 4 MB cost 13 ms a check, and one of 16 MB cost 60.

    ``None`` where the part cannot be cut out by places alone (`_refers_to`, `_named_by_its_keys`), or the
    operation or something it refers to is not found as a pointer into this document names it: a reference
    elsewhere, to an anchor or by an address is none.  The whole is copied then, as it was, and says what is
    wrong.
    """
    sound: set[int] = set()
    part = _responses_read(spec, path, method, sound)
    if part is None:
        return None
    whole: set[tuple[str, ...]] = {("paths", path, method.lower(), "responses")}
    pending = _refers_to(part)
    while pending:
        target, segments = _resolve_local_ref(spec, pending.pop())
        if target is None:
            return None
        if any(tuple(segments[:depth]) in whole for depth in range(1, len(segments) + 1)):
            continue
        place, copied = _taken_to(part, spec, segments, sound)
        more = _refers_to(copied)
        if copied is None or more is None:
            return None
        whole.add(place)
        pending.extend(more)
    return None if pending is None else part


def _resolve_local_ref(spec: dict[str, Any], ref: str):
    """Follow a local JSON-Pointer ``$ref`` (``#/a/b/c``); return ``(target_node, [a, b, c])``, or
    ``(None, [])`` for a non-local or dangling ref.

    Read as the validator reads it, or the two part ways on what a reference names: the fragment is
    percent-decoded whole, then split, then unescaped, and a segment into a list is whatever `int` takes for
    an index, ``+0`` and ``-1`` included.
    """
    if not ref.startswith("#/"):
        return None, []
    fragment = ref[2:]
    if "%" in fragment:
        from urllib.parse import unquote  # 1.6 ms, kept off `import assertpy`: an encoded reference alone asks it

        fragment = unquote(fragment)
    segments = [part.replace("~1", "/").replace("~0", "~") for part in fragment.split("/")]
    node: Any = spec
    for segment in segments:
        if isinstance(node, dict) and segment in node:
            node = node[segment]
        elif isinstance(node, list):
            try:
                node = node[int(segment)]
            except (ValueError, IndexError):
                return None, []
        else:
            return None, []
    return node, segments


class _References:
    """How the walk goes through a document: as the validator does, asking its registry and entering a schema.

    Read by a reader of its own, the two parted on what a reference names: one into a list, one whose
    separators were percent-encoded, one that names the document by its address, one that stands under a
    schema with an ``id`` of its own.
    """

    def __init__(self, unresolvable: type[Exception], draft: Any) -> None:
        self._unresolvable = unresolvable
        self._draft = draft

    def named(self, reference: str, resolver: Any) -> tuple[Any, Any]:
        """What *reference* names from the base *resolver* stands at, and the resolver in effect there.

        ``(None, resolver)`` is a reference that names nothing, which the validator says itself where it comes
        to it: in the registry's own error, or in the `ValueError` it lets out for a segment into a list that
        is no number.
        """
        try:
            found = resolver.lookup(reference)
        except (self._unresolvable, ValueError):
            return None, resolver
        return found.contents, found.resolver

    def inside(self, schema: dict[str, Any], resolver: Any) -> Any:
        """The resolver in effect inside a schema its parent holds: an ``id`` of its own moves the base there."""
        return resolver.in_subresource(self._draft.create_resource(schema))


def _schemas_reached(reference: str, resolver: Any, references: _References) -> list[tuple[dict[str, Any], Any]]:
    """Every schema the one *reference* names reaches, each once, beside the resolver in effect where it stands.

    Walked by the keywords that hold a schema for the validator, through the references it follows, and not as
    data: an ``enum`` member or an ``example`` shaped like a schema is a value, and rewritten as a schema it no
    longer matched itself.

    A schema Draft 4 never asks by the shape of what holds it is not reached: ``additionalItems`` beside an
    ``items`` that is one schema.  One it never asks for what a keyword beside it takes, an
    ``additionalProperties`` beside a pattern that takes every name, is reached like any other.

    A schema is read once, under the resolver it was first reached with.
    """
    reached: list[tuple[dict[str, Any], Any]] = []
    pending, seen = [references.named(reference, resolver)], set()
    while pending:
        schema, within = pending.pop()
        if not isinstance(schema, dict) or id(schema) in seen:
            continue
        seen.add(id(schema))
        reached.append((schema, within))
        ref = schema.get("$ref")
        if isinstance(ref, str):
            pending.append(references.named(ref, within))
            continue
        held: list[Any] = []
        for keyword in ("properties", "patternProperties", "dependencies"):
            mapped = schema.get(keyword)
            if isinstance(mapped, dict):
                held.extend(mapped.values())
        for keyword in ("items", "additionalProperties", "not", "allOf", "anyOf", "oneOf"):
            one = schema.get(keyword)
            held.extend(one if isinstance(one, list) else [one])
        if isinstance(schema.get("items"), list):
            # beside an `items` that is one schema, Draft 4 never asks `additionalItems`
            held.append(schema.get("additionalItems"))
        pending.extend((each, references.inside(each, within)) for each in held if isinstance(each, dict))
    return reached


def _write_only(declared: object, resolver: Any, references: _References) -> bool:
    """Whether the schema a property declares is marked ``writeOnly``, read through the references it is.

    What stands beside a ``$ref`` is ignored, as OpenAPI 3.0 has it, so the mark is the one on the schema the
    references lead to.
    """
    followed: set[int] = set()
    while isinstance(declared, dict) and id(declared) not in followed:
        followed.add(id(declared))
        ref = declared.get("$ref")
        if not isinstance(ref, str):
            return declared.get("writeOnly") is True
        declared, resolver = references.named(ref, resolver)
    return False


def _unrequire_write_only(schema: dict[str, Any], resolver: Any, references: _References) -> None:
    """Take every ``writeOnly`` property of one Schema Object out of its ``required``, in place.

    OpenAPI 3.0: "If the property is marked as writeOnly being true and is in the required list, the required
    will take effect on the request only", and a response is what is validated here.  Asked before ``nullable``
    is rewritten, so a mark is read off the schema as its author wrote it.

    A limit of this reading, and not a conclusion of the text: the mark is looked for in the ``properties`` of
    the Schema Object that holds the ``required``.  A ``required`` in one branch of an ``allOf`` and the marked
    property in another are not brought together.

    Asked of the validator instead, as a ``required`` keyword of its own, the class built per call cost a check
    of twenty rows about 600 us, against 294 this way.
    """
    properties, required = schema.get("properties"), schema.get("required")
    if isinstance(properties, dict) and isinstance(required, list):
        schema["required"] = [
            name
            for name in required
            if not (isinstance(name, str) and _write_only(properties.get(name), resolver, references))
        ]


def _unheard(schema: dict[str, Any]) -> list[str]:
    """What one Schema Object holds that Draft 4 does not have: a keyword of `_UNHEARD`, which it passes over, or
    an exclusive bound written as a number.  That one Draft 4 has as a flag beside ``minimum`` and ``maximum``:
    it reads any number but zero as the flag set, whatever the number, and passes it over where neither stands.

    What stands beside a ``$ref`` is ignored by 3.0 itself, so nothing there is lost.
    """
    if isinstance(schema.get("$ref"), str):
        return []
    found = sorted(_UNHEARD.intersection(schema))
    for bound in ("exclusiveMaximum", "exclusiveMinimum"):
        held = schema.get(bound)
        if isinstance(held, (int, float)) and not isinstance(held, bool):
            found.append(f"{bound} as a number")
    return found


def _pointer_to(document: Any, wanted: object) -> str:
    """The JSON pointer of one node of *document*, found by identity.  Asked only on the way to a refusal."""
    pending: list[tuple[str, Any]] = []
    where, node = "#", document
    while node is not wanted:
        if isinstance(node, dict):
            pending.extend((f"{where}/{key.replace('~', '~0').replace('/', '~1')}", held) for key, held in node.items())
        elif isinstance(node, list):
            pending.extend((f"{where}/{index}", held) for index, held in enumerate(node))
        where, node = pending.pop()
    return where


def _read_as_json_schema(
    document: dict[str, Any],
    reference: str,
    resolver: Any,
    references: _References,
    *,
    swagger: bool,
    whole: bool,
    strict_nullable: bool,
) -> bool:
    """Read the schemas a response reaches into the JSON Schema the validator knows, in the copy handed here.

    ``False``, with nothing read or refused, where *document* is a part of the spec and a schema reached holds
    an ``id`` of its own: a reference under it is then read from another base than the place it is written at,
    which the part was not cut out for.

    Every mark is read before any ``nullable`` is rewritten: a schema one property names may be rewritten for
    another first, and the union it becomes holds the mark a level down.

    A ``$schema`` a schema declares is taken out.  jsonschema reads a schema by the dialect it names, and an
    OpenAPI 3.0 or Swagger 2.0 document is one dialect, with no ``$schema`` in a Schema Object.  It goes before
    ``nullable`` is rewritten, which may move what a schema holds a level down.
    """
    reached = _schemas_reached(reference, resolver, references)
    if not whole and any("id" in schema for schema, _ in reached):
        return False
    for schema, _ in reached:
        unheard = _unheard(schema)
        if unheard:
            dialect = "Swagger 2.0" if swagger else "OpenAPI 3.0"
            raise ValueError(
                f"Schema <{_pointer_to(document, schema)}> holds <{'>, <'.join(unheard)}>, which {dialect} does not"
                " have, so the response would not be held to it as written."
                " Leave it out, or move the spec to OpenAPI 3.1 as a whole: with the version line alone changed,"
                " `nullable` and a boolean exclusive bound are what is not read."
            )
    for schema, within in () if swagger else reached:
        _unrequire_write_only(schema, within, references)
    for schema, _ in reached:
        schema.pop("$schema", None)
        _nullable_as_null(schema, "x-nullable" if swagger else "nullable", by_the_text=strict_nullable)
    return True


def _status_text(status: Any) -> str:
    """A status as a Responses Object spells it.  Read off `int` where it is one: below 3.11 the `str` of
    `HTTPStatus.NOT_FOUND` was its name, and the response it named was not found."""
    kind = type(status)
    return str(int.__index__(status)) if issubclass(kind, int) and not issubclass(kind, bool) else str(status)


def _declared_for(status: str, responses: Any, *, ranged: bool) -> str | None:
    """The key under which an operation declares the response for *status*, or ``None`` where it declares none.

    Its own code first, then its range, then ``default``.  OpenAPI 3: "2XX represents all response codes between
    [200-299]", "only the following range definitions are allowed: 1XX, 2XX, 3XX, 4XX, and 5XX", and "the
    explicit code definition takes precedence over the range definition for that code".  ``default`` is "the
    documentation of responses other than the ones declared for specific HTTP response codes".  Swagger 2.0 has
    codes and ``default``, and no ranges.
    """
    known = [status, "default"]
    if ranged and len(status) == 3 and status.isascii() and status.isdigit() and status[0] in "12345":
        known.insert(1, f"{status[0]}XX")
    return next((key for key in known if key in responses), None)


def _openapi_resolve(spec: dict[str, Any], path: str, method: str, status: str | int | None, content_type: str):
    """Resolve an operation's response-body schema to a JSON Pointer into the spec document.

    Returns ``(status_key, pointer)``. Raises ``ValueError`` for any structural miss (unknown path,
    method, status, or content type) - those are test-authoring mistakes, not contract violations.
    """
    # named rather than left to `.lower()`, which answered from three frames down without naming the argument
    require_type(method, str, "a string", subject=argument("method"))
    method_key = method.lower()
    try:
        operation = spec["paths"][path][method_key]
        responses = operation["responses"]
    except (KeyError, TypeError):
        raise ValueError(f"OpenAPI spec has no operation <{method.upper()} {path}>.") from None
    ranged = not str(spec.get("swagger", "")).startswith("2")
    if status is not None:
        asked = _status_text(status)
        status_key = _declared_for(asked, responses, ranged=ranged)
        if status_key is None:
            raise ValueError(f"Operation <{method.upper()} {path}> declares no response <{asked}>.")
    else:
        success = ("200", "201", "2XX", "default") if ranged else ("200", "201", "default")
        status_key = next((code for code in success if code in responses), "")
        if not status_key:
            raise ValueError(f"Specify status: <{method.upper()} {path}> declares responses {sorted(responses)}.")
    response = responses[status_key]
    response_segments = ["paths", path, method_key, "responses", status_key]
    if isinstance(response, dict) and "$ref" in response:
        response, response_segments = _resolve_local_ref(spec, response["$ref"])
        if response is None:
            raise ValueError(f"Response <{status_key}> of <{method.upper()} {path}> has an unresolvable $ref.")
    if not ranged:
        # Swagger 2.0 lists media types in `produces`, checked the way the 3.x content lookup does
        produces = operation.get("produces") or spec.get("produces")
        if produces and content_type not in produces:
            raise ValueError(
                f"Response <{status_key}> of <{method.upper()} {path}> declares no <{content_type}> schema."
            )
        if not (isinstance(response, dict) and "schema" in response):
            raise ValueError(f"Response <{status_key}> of <{method.upper()} {path}> declares no schema.")
        segments = [*response_segments, "schema"]
    else:
        content = response.get("content", {}) if isinstance(response, dict) else {}
        if content_type not in content or "schema" not in content[content_type]:
            raise ValueError(
                f"Response <{status_key}> of <{method.upper()} {path}> declares no <{content_type}> schema."
            )
        segments = [*response_segments, "content", content_type, "schema"]
    pointer = "#/" + "/".join(segment.replace("~", "~0").replace("/", "~1") for segment in segments)
    return status_key, pointer


def _validator_over(
    document: Any,
    path: str,
    method: str,
    status: str | int | None,
    content_type: str,
    *,
    whole: bool,
    strict_nullable: bool,
) -> tuple[str, Any] | None:
    """The key of the response asked for and a validator of its schema, over *document*, which is its to rewrite.

    ``None`` where *document* is a part of the spec that turns out too small to be read alone.
    """
    jsonschema_mod = _ensure_jsonschema()
    import referencing
    from referencing.exceptions import Unresolvable
    from referencing.jsonschema import DRAFT4, DRAFT202012

    version = str(document.get("openapi", ""))
    is_swagger_2 = _SWAGGER_2.fullmatch(str(document.get("swagger", ""))) is not None
    # matched whole, not by prefix: "3.10.0" starts with "3.1", and "3.1.garbage" is no version at all
    read = _OPENAPI_VERSION.fullmatch(version)
    if version and read is None:
        # read as 3.0 an unknown version validates against Draft 4, which passes anything it cannot spell
        raise ValueError(f"openapi version <{version}> is not one this can validate (3.0, 3.1 and 3.2 are)")
    # 3.2 keeps 3.1's dialect: the schema object is JSON Schema 2020-12 in both
    is_openapi_31 = read is not None and read.group(1) in ("1", "2")
    status_key, pointer = _openapi_resolve(document, path, method, status, content_type)
    specification = DRAFT202012 if is_openapi_31 else DRAFT4
    # a part holds no `$schema` (`_refers_to`), and under 3.0 each one is taken out
    validator_cls = _dividing_as_written(
        jsonschema_mod.Draft202012Validator if is_openapi_31 else jsonschema_mod.Draft4Validator,
        redeclared=whole and is_openapi_31,
    )
    base = "urn:assertpy-openapi"
    registry = referencing.Registry().with_resource(
        uri=base, resource=referencing.Resource(contents=document, specification=specification)
    )
    # 3.1 is JSON Schema 2020-12 already
    if not is_openapi_31 and not _read_as_json_schema(
        document,
        base + pointer,
        registry.resolver(base_uri=base),
        _References(Unresolvable, DRAFT4),
        swagger=is_swagger_2,
        whole=whole,
        strict_nullable=strict_nullable,
    ):
        return None
    return status_key, validator_cls(
        {"$ref": base + pointer},
        registry=registry,
        format_checker=_openapi_formats(jsonschema_mod, a_labels=is_openapi_31),
    )


def _openapi_expected(error: Any) -> str:
    """Render a jsonschema validation error's constraint as a short 'expected' description."""
    validator, value = error.validator, error.validator_value
    if validator == "required":
        return "all required properties present"
    if validator == "type":
        return f"type {value}"
    if validator == "enum":
        return f"one of {value}"
    if validator == "oneOf":
        return "exactly one of the declared schemas"
    if validator == "anyOf":
        return "one of the declared schemas"
    if validator == "format":
        return f"{value} format"
    return error.message


class JsonMixin(_MixinBase):
    """JSON path navigation and schema validation mixin."""

    def at_json_path(self, path: str) -> Self:
        """Navigate to a JSON path and return a new builder with the matched value.

        Uses JSONPath syntax (e.g. ``$.users[0].name``). If multiple matches are found,
        the value is a list of all matches. If exactly one match is found, the value is
        unwrapped from the list.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
                assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
                assert_that(data).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])

        Returns:
            AssertionBuilder: a new instance with the extracted value

        Raises:
            ValueError: if no match is found at the given path
        """
        expr = _parsed_json_path(path)
        # handed a scalar, jsonpath answers about its own indexing rather than about the value under assertion
        require_type(self.val, (dict, list), "a decoded JSON document (a dict or a list)")
        matches = expr.find(self.val)
        if not matches:
            raise ValueError(f"Expected JSON path <{path}> to exist, but it did not.")
        if len(matches) == 1:
            return self.builder(matches[0].value, self.description, self.kind, logger=self.logger)
        return self.builder([match.value for match in matches], self.description, self.kind, logger=self.logger)

    def has_json_path(self, path: str) -> Self:
        """Assert that the given JSON path exists in val.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"meta": {"total": 5}}
                assert_that(data).has_json_path("$.meta.total")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the path does not exist
        """
        expr = _parsed_json_path(path)
        # handed a scalar, jsonpath answers about its own indexing rather than about the value under assertion
        require_type(self.val, (dict, list), "a decoded JSON document (a dict or a list)")
        matches = expr.find(self.val)
        if not matches:
            return self.error(f"Expected JSON path <{path}> to exist, but it did not.", expected=path)
        return self

    def does_not_have_json_path(self, path: str) -> Self:
        """Assert that the given JSON path does not exist in val.

        Args:
            path: JSONPath expression.

        Examples:
            Usage:

                data = {"status": "ok"}
                assert_that(data).does_not_have_json_path("$.error")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the path exists
        """
        expr = _parsed_json_path(path)
        # handed a scalar, jsonpath answers about its own indexing rather than about the value under assertion
        require_type(self.val, (dict, list), "a decoded JSON document (a dict or a list)")
        matches = expr.find(self.val)
        if matches:
            return self.error(f"Expected JSON path <{path}> to not exist, but it did.")
        return self

    def matches_json_schema(self, schema: dict[str, Any]) -> Self:
        """Assert that val conforms to the given JSON Schema.

        Args:
            schema: a JSON Schema as a dict.

        Examples:
            Usage:

                schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
                assert_that({"name": "Alice"}).matches_json_schema(schema)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the schema
        """
        jsonschema_mod = _ensure_jsonschema()
        try:
            require_type(
                schema,
                (dict, bool),
                "a JSON Schema (a dict, or a bool for the trivial schema)",
                subject=argument("schema"),
            )
            jsonschema_mod.validate(self.val, schema)
        except jsonschema_mod.ValidationError as exc:
            # the path is the only part of jsonschema's text the message does not already have
            return self.error(
                f"Expected val to match JSON schema, but validation failed at {exc.json_path}: {exc.message}",
                suppress_context=True,
                expected=schema,
            )
        return self

    def matches_json_schema_from_file(self, path: str | Path) -> Self:
        """Assert that val conforms to a JSON Schema loaded from a file.

        Args:
            path: path to a JSON file containing the schema.

        Examples:
            Usage:

                assert_that(data).matches_json_schema_from_file("schemas/order.json")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the schema
        """
        require_type(path, (str, PurePath), "a path", subject=argument("path"))
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.matches_json_schema(schema)

    def conforms_to_openapi(
        self,
        spec: dict[str, Any],
        path: str,
        method: str,
        *,
        status: str | int | None = None,
        content_type: str = "application/json",
        strict_nullable: bool = False,
    ) -> Self:
        """Assert that val conforms to an OpenAPI operation's response-body schema.

        val is validated against the schema declared for the ``application/json`` response of the
        ``method``/``path`` operation in ``spec``. This checks only the response body of that one
        operation - not request bodies, parameters, headers, or the spec as a whole.

        OpenAPI 3.0 (its ``nullable`` keyword is honoured), 3.1, and Swagger 2.0 (schema declared directly
        on the response, its ``x-nullable`` extension honoured) are all supported. ``$ref``,
        ``oneOf``/``allOf``/``anyOf`` and ``enum`` all validate with full JSON-Schema semantics, and every
        violation is reported with its JSON path.

        Under OpenAPI 3.0, ``nullable: true`` adds ``null`` to the ``type`` beside it and leaves an ``enum``
        as written, so ``null`` passes an enum only where the enum lists it.  A property marked
        ``writeOnly: true`` is not asked for by ``required``, since val is a response.

        A ``multipleOf`` divides the numbers as they are written, so ``19.99`` is a multiple of ``0.01``,
        which it is not as two floats divided.  A float is read as the decimal it prints as: digits a float
        does not keep are gone before val is handed in, and a `decimal.Decimal` keeps them.

        A ``format`` is checked where there is a check for it: ``date``, ``time``, ``date-time``, ``email``,
        ``ipv4``, ``ipv6``, ``uuid``, ``regex``, ``uri``, ``hostname``, ``duration``, and OpenAPI's ``int32``
        and ``int64``.  A ``time`` is RFC 3339's, with its offset: ``10:00:00Z``, and not ``10:00:00``.  A
        ``hostname`` under OpenAPI 3.1 has its ``xn--`` labels held to IDNA by the ``idna`` package.  An
        ``email`` is the mailbox of RFC 5321, and a ``duration`` has no fraction: ``PT0.5S`` is none.  The
        others jsonschema checks only beside a package of their own, ``uri-reference``,
        ``iri``, ``json-pointer`` and ``uri-template`` among them, are checked where that package is
        installed (``jsonschema[format-nongpl]`` brings them all), and pass unchecked where it is not.

        Args:
            spec: a parsed OpenAPI document (dict); loading YAML/JSON is the caller's job.
            path: the operation's path template, e.g. ``"/orders/{id}"``.
            method: the HTTP method, e.g. ``"get"`` (case-insensitive).
            status: response status to validate against; defaults to ``200``, then ``201``, then the range
                ``2XX``, then ``default``.  A status is looked up by its own code, then by its range
                (``404`` under ``4XX``), then under ``default``.  Swagger 2.0 has no ranges.
            content_type: response content type; defaults to ``"application/json"``. Swagger 2.0 has no
                content-type layer, so it is checked against the operation's ``produces`` list instead
                (and skipped when the spec declares none).
            strict_nullable: hold OpenAPI 3.0's ``nullable`` to its text, where it adds ``null`` to the
                ``type`` beside it and does nothing with no ``type`` there.  By default ``nullable: true``
                beside a ``$ref``, an ``allOf``, an ``anyOf`` or a ``oneOf`` allows ``null`` as well, which is
                how a nullable reference is usually written.  Swagger 2.0's ``x-nullable`` and OpenAPI 3.1 are
                read the same either way.

        Examples:
            Usage:

                spec = {...}  # your parsed OpenAPI document
                assert_that(response.json()).conforms_to_openapi(spec, "/orders/{id}", "get")

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not conform to the response schema
            ValueError: if the operation, status, or content type is not found in the spec, a schema of
                OpenAPI 3.0 or Swagger 2.0 holds a keyword of later JSON Schema, which would be passed over,
                or a ``multipleOf`` that val is held to is no number above zero
        """
        part = _part_read(spec, path, method)
        over = None
        if part is not None:
            over = _validator_over(
                part, path, method, status, content_type, whole=False, strict_nullable=strict_nullable
            )
        if over is None:
            # YAML may parse numeric-looking keys (e.g. status 200) as ints, so the copy has them as text
            over = _validator_over(
                _stringify_keys(spec), path, method, status, content_type, whole=True, strict_nullable=strict_nullable
            )
        status_key, validator = cast("tuple[str, Any]", over)
        errors = sorted(validator.iter_errors(self.val), key=lambda error: (error.json_path, str(error.validator)))
        if not errors:
            return self
        entries = [
            DiffEntry(path=error.json_path, actual=error.instance, expected=_openapi_expected(error))
            for error in errors
        ]
        plural = "" if len(entries) == 1 else "s"
        return self.error(
            f"Expected the value to conform to the OpenAPI schema for <{method.upper()} {path}> response"
            f" <{status_key}>, but found {len(entries)} violation{plural}.",
            diff=DiffResult(kind="openapi", entries=entries),
        )
