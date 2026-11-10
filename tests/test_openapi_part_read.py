"""A check of one operation copies the part of the spec it reads, and gets from it what the whole gives.

`conforms_to_openapi` rewrites the schemas it reads, so it works on a copy.  Copied whole on every call, a
spec of megabytes cost a check milliseconds for an operation that reads a few schemas of it.  The part is
the operation and whatever it refers to, each at the place it has in the spec.  Where the part cannot be cut
out by places alone the whole is copied as before, so the law is one: the verdict of the part is the
verdict of the whole.
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from assertpy import assert_that, json_mixin
from tests.optional import needs
from tests.test_openapi_30_keywords import _BODIES, _DRAFT_FOUR, _spec

needs("jsonschema")


def _said(spec: Any, value: object, path: Any = "/x", method: Any = "get", **options: Any) -> tuple[Any, ...]:
    """How a check ended: its verdict and what it named, or the refusal it raised."""
    try:
        outcome = assert_that(value).check().conforms_to_openapi(spec, path, method, **options)
    except Exception as refusal:
        return type(refusal).__name__, str(refusal)
    named = [] if outcome.diff is None else outcome.diff.entries
    return outcome.passed, [(entry.path, repr(entry.actual), entry.expected) for entry in named]


def _of_the_whole(spec: Any, value: object, *where: object, **options: Any) -> tuple[Any, ...]:
    with patch.object(json_mixin, "_part_read", return_value=None):
        return _said(spec, value, *where, **options)


def _document(schema: Any, version: str = "3.0.3", **components: Any) -> dict[str, Any]:
    if version == "2.0":
        return {
            "swagger": "2.0",
            "definitions": components,
            "paths": {"/x": {"get": {"responses": {"200": {"schema": schema}}}}},
        }
    return {
        "openapi": version,
        "components": {"schemas": components},
        "paths": {"/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
    }


class _Untouched(dict):
    """A schema the check has no business reading: copying it, as the whole is copied, fails."""

    def items(self) -> Any:
        raise AssertionError("a part of the spec the operation does not refer to was read")


class TestThePartIsWhatTheOperationRefersTo:
    def test_what_it_does_not_refer_to_is_never_read(self):
        spec = _document({"$ref": "#/components/schemas/Order"}, Order={"type": "integer"}, Other=_Untouched(a=1))
        spec["paths"]["/y"] = _Untouched(get={})
        assert_that(_said(spec, 7)).is_equal_to((True, []))
        assert_that(_said(spec, "seven")[0]).is_false()
        assert_that(_of_the_whole(spec, 7)[0]).is_equal_to("AssertionError")

    def test_the_part_holds_the_operation_and_what_it_refers_to_at_their_places(self):
        line = {"type": "object", "properties": {"sku": {"type": "string"}}}
        order = {"type": "array", "items": {"$ref": "#/components/schemas/Line"}}
        spec = _document({"$ref": "#/components/schemas/Order"}, Order=order, Line=line, Unused={"const": 1})
        spec["paths"]["/y"] = {"get": {"responses": {}}}
        spec["info"] = {"title": "orders"}
        asked = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Unused"}}}}
        spec["paths"]["/x"]["get"]["requestBody"] = asked
        spec["paths"]["/x"]["post"] = {"responses": {}}
        part = json_mixin._part_read(spec, "/x", "get")
        assert_that(part).is_equal_to(
            {
                "openapi": "3.0.3",
                "components": {"schemas": {"Order": order, "Line": line}},
                "paths": {"/x": {"get": {"responses": spec["paths"]["/x"]["get"]["responses"]}}},
            }
        )
        assert_that(part["components"]["schemas"]["Order"]).is_not_same_as(order)

    def test_a_schema_it_does_not_refer_to_is_not_refused_for_what_it_holds(self):
        spec = _document({"type": "integer"}, Unused={"const": 1})
        assert_that(_said(spec, 7)).is_equal_to((True, []))


_REFERS = {"type": "object", "properties": {"p": {"$ref": "#/components/schemas/Held"}}}

_CUT_OUT: dict[str, tuple[Any, Any]] = {
    "a reference": (_document({"$ref": "#/components/schemas/Held"}, Held={"type": "integer"}), 7),
    "a reference of a reference": (
        _document(_REFERS, Held={"$ref": "#/components/schemas/Deeper"}, Deeper={"type": "integer"}),
        {"p": "seven"},
    ),
    "a schema that refers to itself": (
        _document(_REFERS, Held={"type": "object", "properties": {"p": {"$ref": "#/components/schemas/Held"}}}),
        {"p": {"p": {"p": 5}}},
    ),
    "into a list": (
        _document(
            {"$ref": "#/components/schemas/Both/allOf/1"}, Both={"allOf": [{"type": "string"}, {"type": "integer"}]}
        ),
        "seven",
    ),
    "into a list from its end": (
        _document(
            {"$ref": "#/components/schemas/Both/allOf/-1"}, Both={"allOf": [{"type": "string"}, {"type": "integer"}]}
        ),
        "seven",
    ),
    "into a list, then out of it by another reference": (
        _document(
            {"$ref": "#/components/schemas/Both/allOf/0"},
            Both={"allOf": [{"$ref": "#/components/schemas/Held"}, {"type": "string"}]},
            Held={"type": "integer"},
        ),
        "seven",
    ),
    "percent-encoded": (
        _document({"$ref": "#/components/schemas/A%20Held"}, **{"A Held": {"type": "integer"}}),
        "seven",
    ),
    "with an escaped slash": (
        _document({"$ref": "#/components/schemas/a~1b"}, **{"a/b": {"type": "integer"}}),
        "seven",
    ),
    "a part of a schema, then the schema": (
        _document(
            {"allOf": [{"$ref": "#/components/schemas/Held/properties/p"}, {"$ref": "#/components/schemas/Held"}]},
            Held={"type": "object", "properties": {"p": {"type": "object"}}, "nullable": True},
        ),
        {"p": 5},
    ),
    "a schema, then a part of it": (
        _document(
            {"allOf": [{"$ref": "#/components/schemas/Held"}, {"$ref": "#/components/schemas/Held/properties/p"}]},
            Held={"type": "object", "properties": {"p": {"type": "object"}}, "nullable": True},
        ),
        {"p": 5},
    ),
    "a nullable schema behind a reference": (
        _document(_REFERS, Held={"type": "string", "nullable": True, "enum": ["a"]}),
        {"p": None},
    ),
    "a keyword the dialect lacks behind a reference": (_document(_REFERS, Held={"const": "a"}), {"p": "b"}),
    "a status that YAML read as a number": (
        {
            "openapi": "3.0.3",
            "paths": {
                "/x": {"get": {"responses": {200: {"content": {"application/json": {"schema": {"type": "integer"}}}}}}}
            },
        },
        "seven",
    ),
    "a property that YAML read as a number": (
        _document({"type": "object", "properties": {7: {"type": "integer"}}}),
        {"7": "seven"},
    ),
    "a response that is a reference": (
        {
            "openapi": "3.0.3",
            "components": {"responses": {"Count": {"content": {"application/json": {"schema": {"type": "integer"}}}}}},
            "paths": {"/x": {"get": {"responses": {"200": {"$ref": "#/components/responses/Count"}}}}},
        },
        "seven",
    ),
    "swagger": (_document({"$ref": "#/definitions/Held"}, "2.0", Held={"type": "string", "x-nullable": True}), None),
    "three one, under $defs": (
        _document(
            {"$ref": "#/components/schemas/Held/$defs/Inner"}, "3.1.0", Held={"$defs": {"Inner": {"const": "a"}}}
        ),
        "b",
    ),
    "three one, an $anchor nothing refers to": (_document({"$anchor": "here", "type": "integer"}, "3.1.0"), "seven"),
    "a $recursiveRef, refused under three zero": (_document({"$recursiveRef": "#"}), 5),
    "a reference inside an example, which is data": (
        _document({"type": "integer", "example": {"$ref": "#/components/schemas/Held"}}, Held={"type": "string"}),
        "seven",
    ),
}

_NOT_CUT_OUT: dict[str, tuple[Any, Any]] = {
    "a reference to the whole document": (_document({"properties": {"p": {"$ref": "#"}}}), {"p": 5}),
    "a reference by the address of the document": (
        _document({"$ref": "urn:assertpy-openapi#/components/schemas/Held"}, Held={"type": "integer"}),
        "seven",
    ),
    "a reference out of the document": (
        _document({"$ref": "https://json-schema.org/draft/2020-12/schema"}),
        {"type": 5},
    ),
    "a reference that names nothing": (_document({"$ref": "#/components/schemas/Absent"}), 5),
    "a reference through a key YAML read as a number": (
        {
            "openapi": "3.0.3",
            "components": {"schemas": {7: {"type": "integer"}}},
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/7"}}}}
                        }
                    }
                }
            },
        },
        "seven",
    ),
    "a reference into a schema with an id of its own": (
        _document(
            {"$ref": "#/definitions/Held/definitions/P"},
            "2.0",
            T={"type": "integer"},
            Held={
                "id": "http://example.test/held",
                "definitions": {"T": {"type": "string"}, "P": {"$ref": "#/definitions/T"}},
            },
        ),
        "five",
    ),
    "three one, a reference into a schema with an $id of its own": (
        _document(
            {"$ref": "#/components/schemas/Held/$defs/P"},
            "3.1.0",
            Held={"$id": "https://example.test/held", "$defs": {"P": {"type": "integer"}}},
        ),
        "five",
    ),
    "three one, a schema that declares another dialect": (
        {
            "openapi": "3.1.0",
            "type": "integer",
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$schema": "https://json-schema.org/draft/2019-09/schema",
                                            "$recursiveRef": "#",
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
        },
        "five",
    ),
    "two keys that read alike, the text one first": (
        {
            "swagger": "2.0",
            "definitions": {"7": {"type": "integer"}, 7: {"type": "string"}},
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"$ref": "#/definitions/7"}}}}}},
        },
        "five",
    ),
    "two keys that read alike, the text one last": (
        {
            "swagger": "2.0",
            "definitions": {7: {"type": "string"}, "7": {"type": "integer"}},
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"$ref": "#/definitions/7"}}}}}},
        },
        "five",
    ),
    "a key that is no text beside the schema referred to": (
        {
            "openapi": "3.0.3",
            "components": {"schemas": {"Held": {"type": "integer"}, 404: {"type": "string"}}},
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Held"}}}}
                        }
                    }
                }
            },
        },
        "five",
    ),
    "a path that YAML read as a number beside the one asked": (
        {
            "openapi": "3.0.3",
            "paths": {
                "/x": {
                    "get": {"responses": {"200": {"content": {"application/json": {"schema": {"type": "integer"}}}}}}
                },
                7: {},
            },
        },
        "five",
    ),
    "a reference to a null": (_document({"$ref": "#/components/schemas/Held"}, Held=None), 5),
    "three one, a schema with an $id": (
        _document(_REFERS, "3.1.0", Held={"$id": "https://example.test/held", "type": "integer"}),
        {"p": "seven"},
    ),
    "three one, a reference to an anchor": (
        _document(_REFERS | {"$ref": "#here"}, "3.1.0", Held={"$anchor": "here", "type": "integer"}),
        "seven",
    ),
    "three one, a $dynamicRef": (
        _document({"$dynamicRef": "#/components/schemas/Held"}, "3.1.0", Held={"type": "integer"}),
        "seven",
    ),
    "a reference in an example that is no pointer": (
        _document({"type": "integer", "example": {"$ref": "elsewhere.json"}}),
        "seven",
    ),
    "an operation that is not there": (_document({"type": "integer"}), 5),
}


class TestThePartAndTheWholeGiveOneVerdict:
    @pytest.mark.parametrize("case", sorted(_CUT_OUT))
    def test_where_the_part_is_cut_out(self, case):
        spec, value = _CUT_OUT[case]
        before = copy.deepcopy(spec)
        assert_that(json_mixin._part_read(spec, "/x", "get")).is_not_none()
        assert_that(_said(spec, value)).is_equal_to(_of_the_whole(spec, value))
        assert_that(spec).is_equal_to(before)

    @pytest.mark.parametrize("case", sorted(_NOT_CUT_OUT))
    def test_where_it_is_not_and_the_whole_is_copied(self, case):
        spec, value = _NOT_CUT_OUT[case]
        where = ("/absent", "get") if case == "an operation that is not there" else ("/x", "get")
        assert_that(json_mixin._part_read(spec, *where)).is_none()
        assert_that(_said(spec, value, *where)).is_equal_to(_of_the_whole(spec, value, *where))

    @pytest.mark.parametrize("where", [(7, "get"), ("/x", 7), ("/x", None), (None, "get"), (["/x"], "get")])
    def test_a_path_or_a_method_that_is_no_text_is_left_to_the_whole_to_refuse(self, where):
        spec = _document({"type": "integer"})
        assert_that(json_mixin._part_read(spec, *where)).is_none()
        assert_that(_said(spec, 5, *where)).is_equal_to(_of_the_whole(spec, 5, *where))

    def test_both_values_of_a_case_are_told_apart_by_the_whole(self):
        """The cases above hand in one value each.  These are the ones whose part, read alone, took the other."""
        for case in (
            "a reference into a schema with an id of its own",
            "three one, a schema that declares another dialect",
            "two keys that read alike, the text one first",
        ):
            spec, _ = _NOT_CUT_OUT[case]
            assert_that([_said(spec, 5)[0], _said(spec, "five")[0]]).described_as(case).is_equal_to(
                [_of_the_whole(spec, 5)[0], _of_the_whole(spec, "five")[0]]
            )
            assert_that(_said(spec, 5)[0]).described_as(case).is_not_equal_to(_said(spec, "five")[0])

    def test_a_property_named_id_on_the_way_is_no_base(self):
        """A pointer through ``properties`` passes a mapping that may hold a key ``id``: a schema, not a text."""
        held = {"type": "object", "properties": {"id": {"type": "string"}, "p": {"type": "integer"}}}
        spec = _document({"$ref": "#/components/schemas/Held/properties/p"}, Held=held)
        assert_that(json_mixin._part_read(spec, "/x", "get")).is_not_none()
        assert_that(_said(spec, "five")).is_equal_to(_of_the_whole(spec, "five"))

    def test_a_spec_that_is_no_dict_is_left_to_the_whole(self):
        assert_that(json_mixin._part_read([], "/x", "get")).is_none()
        assert_that(json_mixin._part_read({"paths": []}, "/x", "get")).is_none()
        assert_that(json_mixin._part_read({"paths": {"/x": {"get": 7}}}, "/x", "get")).is_none()

    def test_what_swagger_says_it_produces_goes_with_the_part(self):
        schema = {"type": "integer"}
        of_the_spec = {
            "swagger": "2.0",
            "produces": ["text/plain"],
            "paths": {"/x": {"get": {"responses": {"200": {"schema": schema}}}}},
        }
        assert_that(_said(of_the_spec, 5)).is_equal_to(_of_the_whole(of_the_spec, 5))
        assert_that(_said(of_the_spec, 5)[0]).is_equal_to("ValueError")
        of_the_operation = copy.deepcopy(of_the_spec)
        of_the_operation["paths"]["/x"]["get"]["produces"] = ["application/json"]
        assert_that(_said(of_the_operation, 5)).is_equal_to((True, []))
        assert_that(_said(of_the_operation, "five")).is_equal_to(_of_the_whole(of_the_operation, "five"))

    def test_a_schema_with_an_id_of_its_own_sends_the_check_back_to_the_whole(self):
        """Cut out by places, the part does not hold what a reference under another base names.  Swagger 2.0
        is where the registry finds such a base, and there the part is given up for the whole."""
        held = {
            "id": "http://example.test/p",
            "definitions": {"T": {"const": "a"}},
            "allOf": [{"$ref": "#/definitions/T"}],
        }
        spec = _document(
            {"$ref": "#/definitions/Order"},
            "2.0",
            T={"type": "integer"},
            Order={"type": "object", "properties": {"p": held}},
        )
        assert_that(json_mixin._part_read(spec, "/x", "get")).is_not_none()
        said = _said(spec, {"p": "b"})
        assert_that(said).is_equal_to(_of_the_whole(spec, {"p": "b"}))
        assert_that(said[1]).contains("Schema <#/definitions/Order/properties/p/definitions/T> holds <const>")

    def test_two_schemas_under_one_id_are_why_the_part_is_given_up(self):
        """The registry keeps one schema for an ``id``, the one it met last, and the part holds only the one
        referred to: read alone, it would name the other twin's schema."""

        def twin(inner: dict[str, Any]) -> dict[str, Any]:
            return {"id": "http://example.test/s", "definitions": {"T": inner}, "allOf": [{"$ref": "#/definitions/T"}]}

        spec = _document(
            {"$ref": "#/definitions/Held"}, "2.0", T={}, Other=twin({"type": "string"}), Held=twin({"type": "integer"})
        )
        spec["definitions"] = {name: spec["definitions"][name] for name in ("T", "Other", "Held")}
        assert_that(json_mixin._part_read(spec, "/x", "get")).is_not_none()
        for value in (5, "five"):
            assert_that(_said(spec, value)).is_equal_to(_of_the_whole(spec, value))
        with patch.object(json_mixin, "_part_read", return_value=None):
            assert_that([_said(spec, 5)[0], _said(spec, "five")[0]]).is_equal_to([False, True])

    def test_an_id_that_is_data_does_not(self):
        """An ``id`` in an example, or a property of that name, is no base: the walk reaches neither as a schema."""
        schema = {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "example": {"id": "ord_7"},
            "enum": [{"id": "ord_7"}],
        }
        spec = _document(schema, Unused=_Untouched(a=1))
        assert_that(_said(spec, {"id": "ord_7"})).is_equal_to((True, []))


@settings(deadline=None, max_examples=1500, suppress_health_check=[HealthCheck.too_slow])
@given(schema=_DRAFT_FOUR, value=_BODIES, version=st.sampled_from(["3.0.3", "2.0", "3.1.0"]))
def test_the_part_gives_the_verdict_the_whole_gives(schema, value, version):
    spec = _spec(schema, version)
    before = copy.deepcopy(spec)
    assert_that(_said(spec, value)).is_equal_to(_of_the_whole(spec, value))
    assert_that(spec).is_equal_to(before)
