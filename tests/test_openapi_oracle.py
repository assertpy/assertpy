"""`conforms_to_openapi` under OpenAPI 3.0, held to a validator written by other hands.

A test written beside the code agrees with the code: the suite once held that ``null`` passes a nullable
``enum`` that leaves it out, because the rewrite was built to add it.  Here the same response and the same
schema are handed to `openapi-schema-validator`, read in the direction of a response, and the two verdicts
have to be one over generated schemas and values.

Where the two are meant to part, the place is named below with both verdicts, so a change on either side shows.
"""

from __future__ import annotations

import copy
import re
from typing import Any, ClassVar

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, json_mixin
from tests.format_corpus import durations, hostnames, uris

pytest.importorskip("jsonschema", reason="jsonschema not installed")
oracle = pytest.importorskip("openapi_schema_validator", reason="openapi-schema-validator not installed")
extend = pytest.importorskip("jsonschema.validators").extend

COMPONENTS: dict[str, Any] = {
    "Text": {"type": "string"},
    "Count": {"type": "integer", "nullable": True},
    "Level": {"type": "string", "nullable": True, "enum": ["low", "high"]},
    "Secret": {"type": "string", "writeOnly": True},
}

_AS_SENT = oracle.OAS30ReadValidator
"""The oracle as it ships for a response."""

_AS_REQUIRED = extend(_AS_SENT, validators={"writeOnly": None})
"""The oracle without its refusal of a ``writeOnly`` property that did arrive, which 3.0.3 words as SHOULD NOT."""


def _here(value: object, schema: dict[str, Any], **options: Any) -> bool:
    """The verdict of this library, which must leave the spec and the value it was handed as they were."""
    wrapped = {"type": "object", "properties": {"v": schema}}
    spec = {
        "openapi": "3.0.3",
        "components": {"schemas": COMPONENTS},
        "paths": {"/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": wrapped}}}}}}},
    }
    body = {"v": value}
    handed, sent = copy.deepcopy(spec), copy.deepcopy(body)
    try:
        assert_that(body).conforms_to_openapi(spec, "/x", "get", **options)
    except AssertionFailure:
        passed = False
    else:
        passed = True
    assert_that((spec, body)).described_as("the spec and the value after the call").is_equal_to((handed, sent))
    return passed


def _there(value: object, schema: dict[str, Any], validator: Any = _AS_REQUIRED) -> bool:
    wrapped = {"type": "object", "properties": {"v": schema}, "components": {"schemas": COMPONENTS}}
    return not list(validator(wrapped).iter_errors({"v": value}))


_VALUES = st.recursive(
    st.sampled_from([None, True, False, 0, 1, 7, 1.5, "", "a", "low", "high"]),
    lambda inner: st.one_of(
        st.lists(inner, max_size=2),
        st.dictionaries(st.sampled_from(["p", "q", "s"]), inner, max_size=3),
    ),
    max_leaves=6,
)


@st.composite
def _typed(draw: st.DrawFn) -> dict[str, Any]:
    """A schema with a ``type`` of its own, where ``nullable`` and an ``enum`` meet as 3.0.3 words them."""
    schema: dict[str, Any] = {"type": draw(st.sampled_from(["string", "integer", "number", "boolean"]))}
    if draw(st.booleans()):
        schema["nullable"] = draw(st.booleans())
    if draw(st.booleans()):
        schema["enum"] = draw(st.lists(st.sampled_from([None, "a", "low", 0, 1, True]), min_size=1, max_size=3))
    return schema


@st.composite
def _marked(draw: st.DrawFn, inner: st.SearchStrategy[dict[str, Any]]) -> dict[str, Any]:
    """An object whose ``required`` names properties marked ``readOnly`` or ``writeOnly``, and one it does not hold."""
    properties: dict[str, Any] = {}
    for name in draw(st.lists(st.sampled_from(["p", "q", "s"]), unique=True, max_size=3)):
        declared = dict(draw(inner))
        mark = draw(st.sampled_from([None, "readOnly", "writeOnly"]))
        if mark is not None and "$ref" not in declared:
            declared[mark] = draw(st.booleans())
        properties[name] = declared
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if draw(st.booleans()):
        schema["nullable"] = draw(st.booleans())
    required = draw(st.lists(st.sampled_from(["p", "q", "s"]), unique=True, max_size=3))
    if required:
        schema["required"] = required
    if draw(st.booleans()):
        schema["additionalProperties"] = draw(st.one_of(st.booleans(), inner))
    return schema


_REFERENCES = st.sampled_from([{"$ref": f"#/components/schemas/{name}"} for name in ("Text", "Count", "Level")])
_SCHEMAS = st.recursive(
    st.one_of(
        _typed(),
        _REFERENCES,
        st.just({}),
        st.just({"enum": ["a", None]}),
        st.just({"nullable": True, "enum": ["a"]}),
        st.just({"nullable": True}),
    ),
    lambda inner: st.one_of(
        _marked(inner),
        inner.map(lambda items: {"type": "array", "items": items}),
        st.lists(inner, min_size=1, max_size=2).map(lambda branches: {"allOf": branches}),
        st.lists(inner, min_size=1, max_size=2).map(lambda branches: {"anyOf": branches}),
        st.lists(inner, min_size=1, max_size=2).map(lambda branches: {"oneOf": branches}),
        inner.map(lambda negated: {"not": negated}),
    ),
    max_leaves=5,
)


_ACCOUNT = {"type": "object", "required": ["p", "q"], "properties": {"p": {"type": "string", "writeOnly": True}}}


@settings(deadline=None, max_examples=2500, suppress_health_check=[HealthCheck.too_slow])
@given(schema=_SCHEMAS, value=_VALUES)
@example(schema={"type": "string", "nullable": True, "enum": ["low", "high"]}, value=None)
@example(schema={"type": "string", "nullable": True, "enum": ["low", None]}, value=None)
@example(schema={"nullable": True, "enum": ["a"]}, value=None)
@example(schema={"$ref": "#/components/schemas/Level"}, value=None)
@example(schema=_ACCOUNT, value={"q": 1})
@example(schema=_ACCOUNT, value={})
@example(schema={"oneOf": [_ACCOUNT, {"type": "object", "required": ["q"]}]}, value={"q": 1})
@example(schema={"not": _ACCOUNT}, value={"q": 1})
@example(schema={"type": "array", "items": {"anyOf": [_ACCOUNT, {"type": "integer", "nullable": True}]}}, value=[None])
def test_a_response_gets_the_verdict_the_other_validator_gives_it(schema, value):
    assert_that(_here(value, schema)).described_as(f"{value!r} against {schema!r}").is_equal_to(_there(value, schema))


@settings(deadline=None, max_examples=500, suppress_health_check=[HealthCheck.too_slow])
@given(schema=_SCHEMAS.map(lambda schema: schema if "type" in schema else {**schema, "nullable": True}), value=_VALUES)
def test_under_strict_nullable_a_mark_with_no_type_beside_it_gets_that_verdict_too(schema, value):
    """With ``strict_nullable`` the mark is read as the other validator reads it, on whatever schema it stands."""
    assert_that(_here(value, schema, strict_nullable=True)).described_as(f"{value!r} against {schema!r}").is_equal_to(
        _there(value, schema)
    )


_NULLABLE_WITH_NO_TYPE = pytest.mark.parametrize(
    "schema",
    [
        {"nullable": True, "$ref": "#/components/schemas/Text"},
        {"nullable": True, "allOf": [{"type": "string"}]},
        {"nullable": True, "anyOf": [{"type": "string"}]},
        {"nullable": True, "oneOf": [{"type": "string"}]},
    ],
    ids=["$ref", "allOf", "anyOf", "oneOf"],
)


class TestWhereTheTwoAreMeantToPart:
    """Each is a decision recorded in the guide, with the other validator's verdict beside this library's."""

    @_NULLABLE_WITH_NO_TYPE
    def test_a_nullable_reference_or_composition_allows_null_here_alone(self, schema):
        assert_that(_there(None, schema)).is_false()
        assert_that(_here(None, schema)).is_true()
        assert_that(_here("a", schema)).is_equal_to(_there("a", schema)).is_true()
        assert_that(_here(5, schema)).is_equal_to(_there(5, schema)).is_false()

    @_NULLABLE_WITH_NO_TYPE
    def test_under_strict_nullable_it_does_not(self, schema):
        assert_that(_here(None, schema, strict_nullable=True)).is_equal_to(_there(None, schema)).is_false()
        assert_that(_here("a", schema, strict_nullable=True)).is_true()

    @pytest.mark.parametrize(("value", "step"), [(19.99, 0.01), (0.3, 0.1), (4.35, 0.01), (0.07, 0.01)])
    def test_a_decimal_multiple_is_one_here_alone(self, value, step):
        """The other validator divides two floats, as jsonschema does, and ``19.99 / 0.01`` is no whole number."""
        schema = {"type": "number", "multipleOf": step}
        assert_that(_there(value, schema)).is_false()
        assert_that(_here(value, schema)).is_true()
        past = value + step / 2
        assert_that(_here(past, schema)).is_equal_to(_there(past, schema)).is_false()
        assert_that(_here(7.5, {"type": "number", "multipleOf": 2.5})).is_equal_to(
            _there(7.5, schema | {"multipleOf": 2.5})
        )

    def test_a_write_only_property_that_did_arrive_is_refused_there_alone(self):
        schema = {"type": "object", "properties": {"p": {"type": "string", "writeOnly": True}}}
        assert_that(_there({"p": "a"}, schema, _AS_SENT)).is_false()
        assert_that(_here({"p": "a"}, schema)).is_true()
        assert_that(_here({"p": 5}, schema)).is_equal_to(_there({"p": 5}, schema, _AS_SENT)).is_false()

    @pytest.mark.parametrize(
        ("wrap", "there", "here"),
        [
            (lambda marked: {"not": marked}, True, False),
            (lambda marked: {"oneOf": [marked, {"type": "object"}]}, True, False),
            (lambda marked: {"anyOf": [marked, {"type": "integer"}]}, False, True),
        ],
        ids=["not", "oneOf", "anyOf"],
    )
    def test_under_a_composition_that_refusal_turns_the_whole_verdict(self, wrap, there, here):
        """What follows from the decision above and reaches further: a branch the other validator fails for the
        property that arrived holds here, so a ``not`` over it fails and a ``oneOf`` beside it counts two."""
        marked = {"type": "object", "properties": {"p": {"type": "string", "writeOnly": True}}}
        assert_that(_there({"p": "a"}, wrap(marked), _AS_SENT)).is_equal_to(there)
        assert_that(_here({"p": "a"}, wrap(marked))).is_equal_to(here)
        assert_that(_there({"p": "a"}, wrap(marked))).is_equal_to(here)

    def test_a_mark_behind_a_reference_is_read_here_alone(self):
        """The other validator reads the mark off the property as written and does not follow its reference."""
        schema = {"type": "object", "required": ["p"], "properties": {"p": {"$ref": "#/components/schemas/Secret"}}}
        assert_that(_there({}, schema)).is_false()
        assert_that(_here({}, schema)).is_true()

    def test_a_mark_that_is_no_boolean_counts_there_alone(self):
        schema = {"type": "object", "required": ["p"], "properties": {"p": {"type": "string", "writeOnly": "yes"}}}
        assert_that(_there({}, schema)).is_true()
        assert_that(_here({}, schema)).is_false()


class TestWhereTheTwoWereApart:
    """The two readings this module would have caught, each with the verdict the specification gives."""

    def test_null_against_a_nullable_enum_that_leaves_it_out(self):
        schema = {"type": "string", "nullable": True, "enum": ["low", "high"]}
        assert_that(_here(None, schema)).is_equal_to(_there(None, schema)).is_false()

    def test_a_response_without_its_required_write_only_property(self):
        schema = {"type": "object", "required": ["p"], "properties": {"p": {"type": "string", "writeOnly": True}}}
        assert_that(_here({}, schema)).is_equal_to(_there({}, schema)).is_true()


def _in_the_address(change: Any) -> Any:
    """*change* applied to what stands in brackets as the host of a URI, and to nothing else of it."""
    return lambda written: re.sub(
        r"(?<=//)([^/?#\[]*\[)([^\]]*)", lambda host: host[1] + change(host[2]), written, count=1
    )


def _without_leading_zeros(address: str) -> str:
    return re.sub(r"(?<![0-9A-Fa-f])0+(?=[0-9]+(?:\.|$))", "", address) if "." in address else address


_LEFT_OUT: dict[str, dict[str, Any]] = {
    "hostname": {
        "a newline after it": lambda written: written.removesuffix("\n"),
        "a dot after the last label": lambda written: written.removesuffix("."),
    },
    "uri": {
        "a newline after it": lambda written: written.removesuffix("\n"),
        "a leading zero in an IPv4 octet of an IPv6 address": _in_the_address(_without_leading_zeros),
    },
    "duration": {
        "a sign": lambda written: written.replace("-", "").replace("+", ""),
        "a fraction or an exponent": lambda written: re.sub(r"[.e][0-9]+", "", written),
        "weeks beside another unit": lambda written: (
            re.sub("[0-9]+W", "", written) if re.search("[YMDHS]", written) else written
        ),
        "a unit left out between two": lambda written: re.sub("(?<=H)(?=[0-9]+S)|(?<=Y)(?=[0-9]+D)", "0M", written),
    },
}
_TAKEN_HERE_ALONE: dict[str, dict[str, Any]] = {"duration": {"a letter in lower case": str.upper}}
"""Why this library takes a text a package refuses: an ABNF has a quoted letter stand for either case."""

"""Why a package takes a text this library refuses, each reason one the grammar of the format rules out.

Beside each stands the text with that reason taken out of it.  A text the two part on has to pass here once
every reason it shows is taken out, so a reason is what kept the text out and not a mark it happens to carry.
"""


class TestTheThreeFormatsBesideThePackagesJsonschemaAsks:
    """`uri`, `hostname` and `duration` are checked here by their grammars, where jsonschema asks a package each.

    Asked the texts of one fixed corpus, the two have to agree, with two things allowed.  Where the package
    takes a text refused here, the text passes here too once the reasons of `_LEFT_OUT` are taken out of it.
    Where a text passes here that the package refuses, the package takes it once the reasons of
    `_TAKEN_HERE_ALONE` are taken out, and there is one: a letter of a `duration` in lower case.
    """

    CHECKS: ClassVar[dict[str, Any]] = {
        "uri": (json_mixin._is_uri, "rfc3986_validator", uris),
        "hostname": (json_mixin._is_hostname, "fqdn", hostnames),
        "duration": (json_mixin._is_duration, "isoduration", durations),
    }

    @pytest.mark.parametrize("form", sorted(CHECKS))
    def test_the_two_agree_but_for_what_the_grammar_rules_out(self, form):
        here, package, texts = self.CHECKS[form]
        pytest.importorskip(package, reason=f"{package} not installed")
        theirs = pytest.importorskip("jsonschema").FormatChecker()
        assert_that(theirs.checkers).contains_key(form)
        wider = _TAKEN_HERE_ALONE.get(form, {})
        seen = {"taken by both": 0, "refused by both": 0, **dict.fromkeys([*_LEFT_OUT[form], *wider], 0)}
        for written in sorted(set(texts())):
            took, they_took = here(written), theirs.conforms(written, form)
            if took is they_took:
                seen["taken by both" if took else "refused by both"] += 1
                continue
            mended = written
            for reason, without in wider.items() if took else ():
                if without(mended) != mended:
                    mended = without(mended)
                    seen[reason] += 1
            if took:
                assert_that(mended != written and theirs.conforms(mended, form)).described_as(
                    f"{written!r} passes here and is refused by {package}, and no reason named explains it"
                ).is_true()
                continue
            for reason, without in _LEFT_OUT[form].items():
                if without(mended) != mended:
                    mended = without(mended)
                    seen[reason] += 1
            assert_that(here(mended)).described_as(
                f"{written!r} is refused here and taken by {package}, and no reason named explains it: {mended!r}"
            ).is_true()
        assert_that(seen).described_as("each kind of answer was met at least once").does_not_contain_value(0)
