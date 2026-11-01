"""Two keywords of OpenAPI 3.0 held to the text of 3.0.3: ``nullable`` beside ``enum``, ``writeOnly`` in ``required``.

``nullable``: "A true value adds "null" to the allowed type specified by the type keyword, only if type is
explicitly defined within the same Schema Object. Other Schema Object constraints retain their defined behavior,
and therefore may disallow the use of null as a value."

``writeOnly``: "If the property is marked as writeOnly being true and is in the required list, the required will
take effect on the request only."  What is validated here is a response.

Both are read schema by schema, over what the response's own schema reaches, and never over a value.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, json_mixin

pytest.importorskip("jsonschema", reason="jsonschema not installed")

SECRET = {"type": "string", "writeOnly": True}
COMPONENTS: dict[str, Any] = {
    "Secret": SECRET,
    "SecretByName": {"$ref": "#/components/schemas/Secret"},
    "A Secret": SECRET,
    "Plain": {"type": "string"},
    "Loop": {"$ref": "#/components/schemas/Loop"},
    "Pet": {"type": "object", "properties": {"name": {"type": "string"}}},
    "Priority": {"type": "string", "nullable": True, "enum": ["low", "high"]},
    "A Note": {"type": "string", "nullable": True},
    "Wrapped": {"allOf": [{"type": "string", "nullable": True}, SECRET]},
    "Loose": {"nullable": True, "writeOnly": True, "anyOf": [{"type": "object"}, {"type": "string"}]},
    **{f"Hop{n}": {"$ref": f"#/components/schemas/Hop{n + 1}"} for n in range(40)},
    "Hop40": SECRET,
}


def _spec(schema: dict[str, Any], version: str) -> dict[str, Any]:
    if version == "2.0":
        return {
            "swagger": "2.0",
            "definitions": COMPONENTS,
            "paths": {"/x": {"get": {"responses": {"200": {"schema": schema}}}}},
        }
    return {
        "openapi": version,
        "components": {"schemas": COMPONENTS},
        "paths": {"/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
    }


def _violations(value: object, schema: dict[str, Any], version: str = "3.0.3") -> dict[str, object]:
    try:
        assert_that(value).conforms_to_openapi(_spec(schema, version), "/x", "get")
    except AssertionFailure as failure:
        assert failure.diff is not None
        return {entry.path: entry.expected for entry in failure.diff.entries}
    return {}


def _account(required: list[Any], password: dict[str, Any], **beside: Any) -> dict[str, Any]:
    properties = {"id": {"type": "integer"}, "password": password}
    return {"type": "object", "required": required, "properties": properties, **beside}


def _ref(name: str) -> dict[str, Any]:
    return {"$ref": f"#/components/schemas/{name}"}


class TestNullableAddsToTheTypeAndLeavesTheEnumAsWritten:
    def test_null_is_refused_where_the_enum_leaves_it_out(self):
        schema = {"type": "string", "nullable": True, "enum": ["low", "high"]}
        assert_that(_violations(None, schema)).is_equal_to({"$": "one of ['low', 'high']"})
        assert_that(_violations("low", schema)).is_empty()
        assert_that(_violations("urgent", schema)).is_equal_to({"$": "one of ['low', 'high']"})

    def test_null_passes_where_the_enum_lists_it(self):
        schema = {"type": "string", "nullable": True, "enum": ["low", None]}
        assert_that(_violations(None, schema)).is_empty()
        assert_that(_violations("low", schema)).is_empty()

    def test_null_passes_a_nullable_type_with_no_enum(self):
        assert_that(_violations(None, {"type": "string", "nullable": True})).is_empty()
        assert_that(_violations(None, {"type": "string", "nullable": False})).is_equal_to({"$": "type string"})
        assert_that(_violations(5, {"type": "string", "nullable": True})).is_not_empty()

    def test_null_passes_a_nullable_type_written_as_a_list(self):
        """No form of 3.0, and one the validator reads: the keyword adds to the list as it adds to a name."""
        assert_that(_violations(None, {"type": ["string", "integer"], "nullable": True})).is_empty()
        assert_that(_violations(1.5, {"type": ["string", "integer"], "nullable": True})).is_not_empty()

    @pytest.mark.parametrize(
        ("wrap", "body", "path"),
        [
            (lambda enum: {"type": "object", "properties": {"p": enum}}, {"p": None}, "$.p"),
            (lambda enum: {"type": "array", "items": enum}, [None], "$[0]"),
            (lambda enum: {"type": "array", "items": [enum], "additionalItems": enum}, [None, None], "$[1]"),
            (lambda enum: {"type": "object", "additionalProperties": enum}, {"k": None}, "$.k"),
            (lambda enum: {"type": "object", "patternProperties": {"^k": enum}}, {"k": None}, "$.k"),
            (
                lambda enum: {"type": "object", "dependencies": {"k": {"properties": {"p": enum}}}},
                {"k": 1, "p": None},
                "$.p",
            ),
            (lambda enum: {"allOf": [enum]}, None, "$"),
            (lambda enum: {"anyOf": [enum]}, None, "$"),
            (lambda enum: {"oneOf": [enum]}, None, "$"),
        ],
        ids=[
            "a property",
            "an item",
            "an item past the listed ones",
            "an additional property",
            "a pattern property",
            "a dependency",
            "allOf",
            "anyOf",
            "oneOf",
        ],
    )
    def test_the_keyword_is_read_wherever_the_validator_reads_a_schema(self, wrap, body, path):
        enum = {"type": "string", "nullable": True, "enum": ["a"]}
        assert_that(_violations(body, wrap(enum))).contains_key(path)
        assert_that(_violations(body, wrap({"type": "string", "nullable": True}))).is_empty()

    def test_the_keyword_is_read_under_a_negation(self):
        assert_that(_violations(None, {"not": {"type": "string", "nullable": True}})).is_not_empty()
        assert_that(_violations(None, {"not": {"type": "string"}})).is_empty()

    @pytest.mark.parametrize(
        "reference",
        ["#/components/schemas/Wrapped/allOf/0", "#/components%2Fschemas%2FA%20Note", "#/components/schemas/A%20Note"],
        ids=["into a list", "its separators percent-encoded", "its name percent-encoded"],
    )
    def test_a_reference_is_read_as_the_validator_reads_it(self, reference):
        """Decoded whole, then split, and into a list by its index: read otherwise, the keyword was missed."""
        assert_that(_violations(None, {"$ref": reference})).is_empty()
        assert_that(_violations(5, {"$ref": reference})).is_not_empty()

    @pytest.mark.parametrize("index", ["0", "+0", "-2", "00", " 0", "0_0", chr(0x660)])
    def test_an_index_into_a_list_is_whatever_the_validator_takes_for_one(self, index):
        """It reads the segment through `int`: read more narrowly here, the schema it reached kept its keyword."""
        assert_that(_violations(None, _ref(f"Wrapped/allOf/{index}"))).is_empty()
        assert_that(_violations(5, _ref(f"Wrapped/allOf/{index}"))).is_not_empty()

    @pytest.mark.parametrize("name", ["Priority", "A%20Note"])
    def test_the_keyword_is_read_on_a_schema_a_reference_names(self, name):
        """A name with a space is percent-encoded in its reference, and read as the validator reads it."""
        assert_that(_violations(5, _ref(name))).is_not_empty()
        assert_that(_violations(None, _ref(name))).is_equal_to(
            {"$": "one of ['low', 'high']"} if name == "Priority" else {}
        )

    @pytest.mark.parametrize("version", ["3.0.0", "3.0.1", "3.0.2", "3.0.3", "3.0"])
    def test_every_patch_of_three_zero_reads_it_as_three_zero_three_clarified(self, version):
        schema = {"type": "string", "nullable": True, "enum": ["low", "high"]}
        assert_that(_violations(None, schema, version)).is_not_empty()

    def test_with_no_type_and_no_reference_the_keyword_does_nothing(self):
        """3.0.3: it acts "only if type is explicitly defined within the same Schema Object"."""
        assert_that(_violations(None, {"nullable": True, "enum": ["a"]})).is_equal_to({"$": "one of ['a']"})
        assert_that(_violations("a", {"nullable": True, "enum": ["a"]})).is_empty()
        assert_that(_violations(None, {"nullable": True})).is_empty()

    @pytest.mark.parametrize(
        "schema",
        [
            {"nullable": True, "allOf": [{"type": "string"}]},
            {"nullable": True, "anyOf": [{"type": "string"}]},
            {"nullable": True, "oneOf": [_ref("Pet")]},
            {"nullable": True, **_ref("Pet")},
        ],
        ids=["allOf", "anyOf", "oneOf", "$ref"],
    )
    def test_a_nullable_reference_or_composition_still_allows_null(self, schema):
        """Wider than 3.0.3 on purpose: it is how a nullable reference is written in practice."""
        assert_that(_violations(None, schema)).is_empty()
        assert_that(_violations(5, schema)).is_not_empty()

    @pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
    def test_an_enum_beside_a_nullable_composition_is_kept(self, keyword):
        """The wider reading lets ``null`` past the composition and no further: the enum is asked of it as
        it is beside a ``type``."""
        composed = {"nullable": True, keyword: [{"type": "string"}]}
        assert_that(_violations(None, {**composed, "enum": ["a"]})).is_equal_to({"$": "one of ['a']"})
        assert_that(_violations(None, {**composed, "enum": ["a", None]})).is_empty()
        assert_that(_violations("a", {**composed, "enum": ["a"]})).is_empty()
        assert_that(_violations("b", {**composed, "enum": ["a"]})).is_equal_to({"$": "one of ['a']"})
        assert_that(_violations(5, {**composed, "enum": ["a", 5]})).is_not_empty()

    def test_whatever_stands_beside_a_nullable_composition_is_still_asked_of_null(self):
        """The union takes the place of the composition and of nothing else."""
        refused = {"nullable": True, "allOf": [{"type": "string"}], "enum": ["a", None], "not": {"type": "null"}}
        assert_that(_violations(None, refused)).is_not_empty()
        assert_that(_violations("a", refused)).is_empty()
        both = {"nullable": True, "allOf": [{"type": "string"}], "anyOf": [{"minLength": 2}], "minLength": 3}
        assert_that(_violations(None, both)).is_empty()
        assert_that(_violations("abc", both)).is_empty()
        assert_that(_violations("ab", both)).is_not_empty()
        assert_that(_violations("a", both)).is_not_empty()
        assert_that(_violations(5, both)).is_not_empty()

    def test_an_enum_beside_a_nullable_reference_is_ignored_with_the_rest(self):
        """OpenAPI 3.0 ignores what stands beside a ``$ref``, so the enum there asks nothing of any value."""
        named = {"nullable": True, **_ref("Plain"), "enum": ["a"]}
        assert_that(_violations(None, named)).is_empty()
        assert_that(_violations("b", named)).is_empty()
        assert_that(_violations(5, named)).is_not_empty()

    def test_the_extension_of_swagger_two_keeps_the_reading_it_had(self):
        """``x-nullable`` has no text of its own: ``null`` passes its enum, with a type beside it or without."""
        assert_that(_violations(None, {"type": "string", "x-nullable": True, "enum": ["low"]}, "2.0")).is_empty()
        assert_that(
            _violations("urgent", {"type": "string", "x-nullable": True, "enum": ["low"]}, "2.0")
        ).is_not_empty()
        assert_that(_violations(None, {"x-nullable": True, "enum": ["low"]}, "2.0")).is_empty()
        composed = {"x-nullable": True, "allOf": [{"type": "string"}], "enum": ["low"]}
        assert_that(_violations(None, composed, "2.0")).is_empty()
        assert_that(_violations(None, {"type": "string", "nullable": True}, "2.0")).is_not_empty()

    def test_a_value_shaped_like_a_schema_is_left_a_value(self):
        """Rewritten as a schema, the member no longer matched the very value it lists."""
        shaped = {"nullable": True, "type": "string"}
        schema = {"type": "object", "enum": [shaped], "example": shaped, "default": shaped}
        assert_that(_violations(shaped, schema)).is_empty()
        assert_that(_violations({"type": ["string", "null"]}, schema)).is_not_empty()
        untyped = {"nullable": True, "allOf": []}
        assert_that(_violations(untyped, {"enum": [untyped]})).is_empty()
        assert_that(_violations({"anyOf": [{"allOf": []}, {"type": "null"}]}, {"enum": [untyped]})).is_not_empty()


class TestStrictNullableHoldsTheKeywordToItsText:
    """``strict_nullable=True`` leaves the one wider reading out: with no ``type`` beside it, the keyword does
    nothing, "only if type is explicitly defined within the same Schema Object"."""

    @staticmethod
    def _took(value: object, spec: dict[str, Any], **options: Any) -> bool:
        return assert_that(value).check().conforms_to_openapi(spec, "/x", "get", **options).passed

    @pytest.mark.parametrize(
        "schema",
        [
            {"nullable": True, "$ref": "#/components/schemas/Plain"},
            {"nullable": True, "allOf": [{"type": "string"}]},
            {"nullable": True, "anyOf": [{"type": "string"}]},
            {"nullable": True, "oneOf": [{"type": "string"}]},
            {"type": "object", "properties": {"p": {"nullable": True, "$ref": "#/components/schemas/Plain"}}},
        ],
        ids=["$ref", "allOf", "anyOf", "oneOf", "a property"],
    )
    def test_null_is_refused_where_the_wider_reading_alone_took_it(self, schema):
        nested = "properties" in schema
        null, text = ({"p": None}, {"p": "a"}) if nested else (None, "a")
        spec = _spec(schema, "3.0.3")
        assert_that(self._took(null, spec)).is_true()
        assert_that(self._took(null, spec, strict_nullable=True)).is_false()
        assert_that(self._took(null, spec, strict_nullable=False)).is_true()
        assert_that(self._took(text, spec, strict_nullable=True)).is_true()

    @pytest.mark.parametrize(
        "schema",
        [
            {"type": "string", "nullable": True},
            {"type": ["string", "integer"], "nullable": True},
            {"nullable": True, "$ref": "#/components/schemas/A Note"},
            {"nullable": True, "anyOf": [{"type": "string", "nullable": True}]},
            {"nullable": True},
        ],
        ids=["a type", "a list of types", "a reference to a nullable type", "a nullable branch", "no schema at all"],
    )
    def test_null_passes_where_the_text_has_it_pass(self, schema):
        assert_that(self._took(None, _spec(schema, "3.0.3"), strict_nullable=True)).is_true()

    @pytest.mark.parametrize(
        ("schema", "takes_null"),
        [
            ({"nullable": True, "enum": ["a", None]}, True),
            ({"nullable": True, "enum": ["a"]}, False),
            ({"nullable": True, "not": {"type": "string"}}, True),
            ({"nullable": True, "allOf": [{"type": "string", "nullable": True}]}, True),
            ({"nullable": True, "allOf": [{"type": "string", "nullable": True}, {"type": "string"}]}, False),
            ({"nullable": True, "anyOf": [{"type": "string"}, {"type": "integer", "nullable": True}]}, True),
            ({"nullable": True, "oneOf": [{"type": "string"}, {"type": "integer", "nullable": True}]}, True),
            (
                {
                    "nullable": True,
                    "oneOf": [{"type": "string", "nullable": True}, {"type": "integer", "nullable": True}],
                },
                False,
            ),
        ],
        ids=[
            "an enum that lists it",
            "an enum that does not",
            "a negation it meets",
            "every branch of allOf takes it",
            "one branch of allOf does not",
            "a branch of anyOf takes it",
            "one branch of oneOf takes it",
            "two branches of oneOf take it",
        ],
    )
    def test_null_is_asked_of_what_else_the_schema_holds(self, schema, takes_null):
        """The mark with no ``type`` beside it does nothing, so each keyword answers as it would with no mark."""
        unmarked = {keyword: held for keyword, held in schema.items() if keyword != "nullable"}
        assert_that(self._took(None, _spec(schema, "3.0.3"), strict_nullable=True)).is_equal_to(takes_null)
        assert_that(self._took(None, _spec(unmarked, "3.0.3"))).is_equal_to(takes_null)

    def test_it_is_held_so_where_the_whole_spec_is_copied(self):
        """A key that is no text beside the schema referred to sends the check to the copy of the whole."""
        spec = _spec({"nullable": True, "$ref": "#/components/schemas/Plain"}, "3.0.3")
        spec["components"]["schemas"] = {**COMPONENTS, 404: {"type": "string"}}
        assert_that(json_mixin._part_read(spec, "/x", "get")).is_none()
        assert_that(self._took(None, spec)).is_true()
        assert_that(self._took(None, spec, strict_nullable=True)).is_false()

    def test_the_extension_of_swagger_two_has_no_text_to_be_held_to(self):
        spec = _spec({"x-nullable": True, "$ref": "#/definitions/Plain"}, "2.0")
        assert_that(self._took(None, spec)).is_true()
        assert_that(self._took(None, spec, strict_nullable=True)).is_true()

    @pytest.mark.parametrize("strict", [False, True])
    def test_three_one_has_no_such_keyword_either_way(self, strict):
        spec = _spec({"nullable": True, "$ref": "#/components/schemas/Plain"}, "3.1.0")
        assert_that(self._took(None, spec, strict_nullable=strict)).is_false()
        assert_that(self._took("a", spec, strict_nullable=strict)).is_true()


class TestARequiredWriteOnlyPropertyIsNotAskedOfAResponse:
    def test_the_property_may_be_absent(self):
        assert_that(_violations({"id": 1}, _account(["id", "password"], SECRET))).is_empty()

    def test_every_other_required_property_is_still_asked_for(self):
        violations = _violations({}, _account(["id", "password"], SECRET))
        assert_that(violations).is_equal_to({"$": "all required properties present"})
        with pytest.raises(AssertionFailure) as raised:
            assert_that({}).conforms_to_openapi(_spec(_account(["id", "password"], SECRET), "3.0.3"), "/x", "get")
        assert_that(str(raised.value)).contains("1 violation").does_not_contain("password")

    @pytest.mark.parametrize(
        "password",
        [
            {"type": "string"},
            {"type": "string", "writeOnly": False},
            {"type": "string", "writeOnly": "true"},
            {"type": "string", "readOnly": True},
            _ref("Plain"),
            {**_ref("Plain"), "writeOnly": True},
            {**_ref("Plain"), "writeOnly": True, "nullable": True},
            _ref("Missing"),
            _ref("Wrapped/allOf/9"),
            _ref("Wrapped/allOf/last"),
            _ref("Wrapped/allOf/0"),
            _ref("Loop"),
        ],
        ids=[
            "no mark",
            "false",
            "a text",
            "readOnly",
            "a plain $ref",
            "beside a $ref",
            "beside a nullable $ref",
            "a dangling $ref",
            "an index past the list",
            "a name where an index is due",
            "an unmarked member of a list",
            "a ring",
        ],
    )
    def test_a_property_that_is_not_marked_stays_required(self, password):
        assert_that(_violations({"id": 1}, _account(["id", "password"], password))).is_not_empty()

    @pytest.mark.parametrize(
        "password",
        [
            _ref("Secret"),
            _ref("SecretByName"),
            _ref("Hop0"),
            _ref("A%20Secret"),
            {"$ref": "#/components%2Fschemas%2FA%20Secret"},
            _ref("Wrapped/allOf/1"),
            _ref("Wrapped/allOf/-1"),
            {**_ref("Secret"), "nullable": True},
        ],
        ids=["one", "two", "forty", "an encoded name", "encoded separators", "into a list", "from its end", "nullable"],
    )
    def test_the_mark_is_read_through_references(self, password):
        assert_that(_violations({"id": 1}, _account(["id", "password"], password))).is_empty()

    @pytest.mark.parametrize("order", [0, 1], ids=["named first", "named last"])
    def test_the_mark_is_read_before_the_schema_it_stands_on_is_rewritten_for_another_reader(self, order):
        """One schema, reached twice: as the password of the account and on its own beside it."""
        both = [_account(["id", "password"], _ref("Loose")), _ref("Loose")]
        assert_that(_violations({"id": 1}, {"allOf": both[::-1] if order else both})).is_empty()

    def test_the_mark_is_read_on_a_nullable_schema_with_no_type_of_its_own(self):
        password = {"nullable": True, "writeOnly": True, "oneOf": [{"type": "string"}, {"type": "integer"}]}
        assert_that(_violations({"id": 1}, _account(["id", "password"], password))).is_empty()

    @pytest.mark.parametrize(
        ("wrap", "body"),
        [
            (lambda account: {"type": "object", "properties": {"user": account}}, {"user": {"id": 1}}),
            (lambda account: {"type": "array", "items": account}, [{"id": 1}]),
            (lambda account: {"type": "array", "items": [account], "additionalItems": account}, [{"id": 1}, {"id": 2}]),
            (lambda account: {"type": "object", "additionalProperties": account}, {"any": {"id": 1}}),
            (lambda account: {"type": "object", "patternProperties": {"^u": account}}, {"user": {"id": 1}}),
            (lambda account: {"dependencies": {"id": account}}, {"id": 1}),
            (lambda account: {"allOf": [account]}, {"id": 1}),
            (lambda account: {"anyOf": [account]}, {"id": 1}),
            (lambda account: {"oneOf": [account]}, {"id": 1}),
            (lambda account: {"not": {"not": account}}, {"id": 1}),
        ],
        ids=[
            "a property",
            "an item",
            "an item past the listed ones",
            "an additional property",
            "a pattern property",
            "a dependency",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
        ],
    )
    def test_the_rule_reaches_every_schema_the_response_holds(self, wrap, body):
        assert_that(_violations(body, wrap(_account(["id", "password"], SECRET)))).is_empty()
        assert_that(_violations(body, wrap(_account(["id", "password"], {"type": "string"})))).is_not_empty()

    def test_the_rule_reaches_a_schema_named_by_a_reference_that_holds_itself(self):
        node = _account(["id", "password"], SECRET)
        node["properties"]["next"] = _ref("Node")
        spec = _spec(_ref("Node"), "3.0.3")
        spec["components"]["schemas"] = {**COMPONENTS, "Node": node}
        assert_that({"id": 1, "next": {"id": 2}}).conforms_to_openapi(spec, "/x", "get")

    def test_a_write_only_property_that_did_arrive_is_not_refused(self):
        """It "SHOULD NOT be sent as part of the response", which is no MUST: its value is still validated."""
        assert_that(_violations({"id": 1, "password": "x"}, _account(["id", "password"], SECRET))).is_empty()
        assert_that(_violations({"id": 1, "password": 5}, _account(["id", "password"], SECRET))).contains_key(
            "$.password"
        )

    def test_a_required_read_only_property_is_asked_of_a_response(self):
        read_only = {"type": "integer", "readOnly": True}
        schema = {"type": "object", "required": ["id"], "properties": {"id": read_only}}
        assert_that(_violations({}, schema)).is_not_empty()

    def test_required_and_the_mark_in_two_schema_objects_are_not_brought_together(self):
        """A limit of this reading, not a conclusion of the text, which does not say where the mark is looked for."""
        schema = {"allOf": [{"type": "object", "properties": {"password": SECRET}}, {"required": ["password"]}]}
        assert_that(_violations({}, schema)).is_not_empty()

    def test_a_value_shaped_like_a_schema_is_left_a_value(self):
        shaped = {"required": ["password"], "properties": {"password": {"writeOnly": True}}}
        assert_that(_violations(shaped, {"type": "object", "enum": [shaped]})).is_empty()

    def test_a_name_in_required_that_is_no_text_is_no_property(self):
        schema = {"type": "object", "required": [["password"]], "properties": {"password": SECRET}}
        try:
            answer: object = _violations(5, schema)
        except TypeError as refusal:
            answer = type(refusal).__name__
        assert_that(answer).is_equal_to({"$": "type object"})

    @pytest.mark.parametrize("version", ["3.0.3", "3.1.0", "2.0"])
    def test_the_spec_handed_in_is_left_as_it_was(self, version):
        """Both readings rewrite schemas, and they rewrite the copy the assertion makes."""
        nullable = "x-nullable" if version == "2.0" else "nullable"
        schema = _account(["id", "password"], SECRET, **{nullable: True})
        plain = {"$ref": "#/definitions/Plain"} if version == "2.0" else _ref("Plain")
        schema["properties"]["tag"] = {nullable: True, "allOf": [plain], "enum": ["a"]}
        spec = _spec(schema, version)
        handed = copy.deepcopy(spec)
        assert_that({"id": 1, "password": "x", "tag": None}).check().conforms_to_openapi(spec, "/x", "get")
        assert_that(spec).is_equal_to(handed)

    @pytest.mark.parametrize("version", ["3.1.0", "3.2.0", "2.0"])
    def test_the_other_dialects_read_required_as_json_schema_does(self, version):
        """3.1 and 3.2 make the mark an annotation, and Swagger 2.0 has no such keyword."""
        assert_that(_violations({"id": 1}, _account(["id", "password"], SECRET), version)).is_not_empty()


_LEAVES = st.sampled_from(
    [
        {"type": "integer"},
        {"type": "string", "nullable": True},
        {"$ref": "#/components/schemas/Plain"},
        {"$ref": "#/components/schemas/Wrapped/allOf/0"},
        {"$ref": "#/components/schemas/SecretByName"},
        {"$ref": "urn:walk#/components/schemas/Priority"},
        {"$ref": "#/components%2Fschemas%2FA%20Note"},
        {"$ref": "#/components/schemas/Wrapped/allOf/-1"},
        {},
    ]
)
_DRAFT_FOUR = st.recursive(
    _LEAVES,
    lambda inner: st.one_of(
        st.dictionaries(st.sampled_from(["p", "q"]), inner, max_size=2).map(lambda held: {"properties": held}),
        st.dictionaries(st.sampled_from(["^p", "q$"]), inner, max_size=2).map(lambda held: {"patternProperties": held}),
        st.dictionaries(st.sampled_from(["p", "q"]), inner, max_size=2).map(lambda held: {"dependencies": held}),
        inner.map(lambda held: {"items": held}),
        st.tuples(st.lists(inner, max_size=2), inner).map(lambda held: {"items": held[0], "additionalItems": held[1]}),
        inner.map(lambda held: {"additionalProperties": held}),
        inner.map(lambda held: {"not": held}),
        st.lists(inner, min_size=1, max_size=2).map(lambda held: {"allOf": held}),
        st.lists(inner, min_size=1, max_size=2).map(lambda held: {"anyOf": held}),
        st.lists(inner, min_size=1, max_size=2).map(lambda held: {"oneOf": held}),
    ),
    max_leaves=6,
)
_BODIES = st.recursive(
    st.sampled_from([None, 1, "a"]),
    lambda inner: st.one_of(
        st.lists(inner, max_size=3), st.dictionaries(st.sampled_from(["p", "q", "pq"]), inner, max_size=3)
    ),
    max_leaves=6,
)


@settings(deadline=None, max_examples=1500, suppress_health_check=[HealthCheck.too_slow])
@given(schema=_DRAFT_FOUR, value=_BODIES)
def test_the_walk_reaches_every_schema_the_validator_asks(schema, value):
    """Both readings and the refusal act on what the walk reaches: a schema the validator asks and the walk
    misses is read as it was written, with its ``nullable`` unheard and its ``required`` whole.

    Every reference the validator follows is one the walk followed, to the same node of the same document.
    """
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    document = json_mixin._stringify_keys(_spec(schema, "3.0.3"))
    _, pointer = json_mixin._openapi_resolve(document, "/x", "get", None, "application/json")
    resource = referencing.Resource(contents=document, specification=referencing.jsonschema.DRAFT4)
    registry = referencing.Registry().with_resource(uri="urn:walk", resource=resource)
    followed: set[tuple[str, int, int]] = set()

    class Recording(json_mixin._References):
        def named(self, reference: str, resolver: Any) -> tuple[Any, Any]:
            contents, within = super().named(reference, resolver)
            if contents is not None:
                followed.add((reference, id(contents), id(within.lookup("#").contents)))
            return contents, within

    references = Recording(referencing.exceptions.Unresolvable, referencing.jsonschema.DRAFT4)
    walked = json_mixin._schemas_reached("urn:walk" + pointer, registry.resolver(base_uri="urn:walk"), references)
    reached = {id(one) for one, _ in walked}
    asked: list[Any] = []
    resolved: set[tuple[str, int, int]] = set()

    def recording(name: str, keyword: Any) -> Any:
        def recorded(validator: Any, held: Any, instance: Any, asked_of: Any) -> Any:
            asked.append(asked_of)
            if name == "$ref":
                found = validator._resolver.lookup(held)
                resolved.add((held, id(found.contents), id(found.resolver.lookup("#").contents)))
            return keyword(validator, held, instance, asked_of)

        return recorded

    keywords = {name: recording(name, keyword) for name, keyword in jsonschema.Draft4Validator.VALIDATORS.items()}
    entry = {"$ref": "urn:walk" + pointer}
    list(
        jsonschema.validators.extend(jsonschema.Draft4Validator, keywords)(entry, registry=registry).iter_errors(value)
    )
    missed = [one for one in asked if one is not entry and id(one) not in reached]
    assert_that(missed).described_as(f"asked and not reached, for {value!r} against {schema!r}").is_empty()
    assert_that(resolved - followed).described_as("a reference the validator read another way than the walk").is_empty()
    assert_that(len(asked)).is_greater_than(0)
