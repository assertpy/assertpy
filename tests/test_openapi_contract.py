import copy
import http
import typing

import pytest

pytest.importorskip("jsonschema", reason="jsonschema not installed")

from assertpy import assert_that

SPEC_30 = {
    "openapi": "3.0.3",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}},
                    "default": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                }
            }
        },
        "/orders": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"$ref": "#/components/schemas/Order"}}
                            }
                        }
                    }
                }
            }
        },
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "required": ["id", "status", "payment"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string", "minLength": 3},
                    "status": {"type": "string", "enum": ["placed", "approved", "delivered"]},
                    "customerEmail": {"type": "string", "format": "email", "nullable": True},
                    "priority": {"type": "string", "enum": ["low", "high"], "nullable": True},
                    "refund": {
                        "nullable": True,
                        "oneOf": [{"$ref": "#/components/schemas/Card"}, {"$ref": "#/components/schemas/Bank"}],
                    },
                    "payment": {
                        "oneOf": [{"$ref": "#/components/schemas/Card"}, {"$ref": "#/components/schemas/Bank"}]
                    },
                },
            },
            "Card": {
                "type": "object",
                "required": ["kind", "last4"],
                "properties": {"kind": {"type": "string", "enum": ["card"]}, "last4": {"type": "string"}},
            },
            "Bank": {
                "type": "object",
                "required": ["kind", "iban"],
                "properties": {"kind": {"type": "string", "enum": ["bank"]}, "iban": {"type": "string"}},
            },
            "Error": {"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}},
        }
    },
}

SPEC_31 = {
    "openapi": "3.1.0",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Order"}}}}
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "customerEmail": {"type": ["string", "null"], "format": "email"},
                },
            }
        }
    },
}

CARD = {"kind": "card", "last4": "4242"}
CONFORMANT = {"id": 1, "name": "widget", "status": "approved", "customerEmail": "a@b.com", "payment": CARD}


class TestConformant:
    def test_conformant_body_passes_and_chains(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get").is_type_of(dict)

    def test_nullable_field_null_is_conformant(self):
        assert_that({**CONFORMANT, "customerEmail": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_nullable_enum_takes_a_value_and_refuses_the_null_it_does_not_list(self):
        assert_that({**CONFORMANT, "priority": "low"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        with pytest.raises(AssertionError) as exc_info:
            assert_that({**CONFORMANT, "priority": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        assert_that(_entries(exc_info.value)).contains_key("$.priority")

    def test_nullable_oneof_null_and_value_conformant(self):
        assert_that({**CONFORMANT, "refund": None}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        assert_that({**CONFORMANT, "refund": CARD}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_nullable_optional_field_absent(self):
        body = {"id": 1, "status": "placed", "payment": CARD}
        assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_property_literally_named_nullable_is_validated(self):
        # a property whose NAME is "nullable" must not be mistaken for the OpenAPI nullable keyword
        schema = {
            "type": "object",
            "properties": {"nullable": {"type": "string"}, "name": {"type": "string"}},
            "required": ["nullable", "name"],
        }
        spec = {
            "openapi": "3.0.3",
            "paths": {"/c": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"nullable": "x", "name": "y"}).conforms_to_openapi(spec, "/c", "get")
        with pytest.raises(AssertionError):
            assert_that({"nullable": 123, "name": 456}).conforms_to_openapi(spec, "/c", "get")

    def test_nullable_false_does_not_allow_null(self):
        schema = {"type": "object", "properties": {"name": {"type": "string", "nullable": False}}, "required": ["name"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/c": {"get": {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"name": "x"}).conforms_to_openapi(spec, "/c", "get")
        with pytest.raises(AssertionError):
            assert_that({"name": None}).conforms_to_openapi(spec, "/c", "get")

    def test_yaml_integer_status_key_is_matched(self):
        # PyYAML parses an unquoted status code (200:) as an int; it must still resolve and match
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {200: {"content": {"application/json": {"schema": schema}}}}}}},
        }
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get")
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get", status=200)
        with pytest.raises(AssertionError):
            assert_that({"id": "bad"}).conforms_to_openapi(spec, "/x", "get")

    def test_dangling_response_ref_raises(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/y": {"get": {"responses": {"200": {"$ref": "#/components/responses/Nope"}}}}},
        }
        with pytest.raises(ValueError, match="unresolvable"):
            assert_that({"id": 5}).conforms_to_openapi(spec, "/y", "get")

    def test_external_response_ref_raises(self):
        spec = {"openapi": "3.0.3", "paths": {"/y": {"get": {"responses": {"200": {"$ref": "other.yaml#/x"}}}}}}
        with pytest.raises(ValueError, match="unresolvable"):
            assert_that({"id": 5}).conforms_to_openapi(spec, "/y", "get")

    def test_response_level_ref_is_resolved(self):
        # a Response Object given as a local $ref into components must resolve, not report "no schema"
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"$ref": "#/components/responses/Ok"}}}}},
            "components": {
                "responses": {"Ok": {"description": "ok", "content": {"application/json": {"schema": schema}}}}
            },
        }
        assert_that({"id": 5}).conforms_to_openapi(spec, "/x", "get")
        with pytest.raises(AssertionError):
            assert_that({"id": "bad"}).conforms_to_openapi(spec, "/x", "get")

    def test_array_response_conformant(self):
        assert_that([CONFORMANT, {**CONFORMANT, "id": 2}]).conforms_to_openapi(SPEC_30, "/orders", "get")

    def test_method_is_case_insensitive(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "GET")

    def test_explicit_status_str_and_int(self):
        assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status=200)
        assert_that({"message": "boom"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get", status="default")

    def test_openapi_31_native_null(self):
        assert_that({"id": 1, "customerEmail": None}).conforms_to_openapi(SPEC_31, "/orders/{id}", "get")


def _entries(exc: AssertionError) -> dict[str, str]:
    """Map the structured diff carried by an OpenAPI failure to ``{path: expected}``."""
    return {entry.path: entry.expected for entry in exc.diff.entries}


class TestViolations:
    def _violation(self, body: dict) -> dict[str, str]:
        with pytest.raises(AssertionError) as exc_info:
            assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")
        return _entries(exc_info.value)

    def test_wrong_type_reports_path(self):
        assert_that(self._violation({**CONFORMANT, "id": "one"})).contains_key("$.id")

    def test_wrong_type_expected_text(self):
        assert_that(self._violation({**CONFORMANT, "id": "one"})["$.id"]).contains("type integer")

    def test_missing_required_field(self):
        assert_that(self._violation({"status": "placed", "payment": CARD})["$"]).contains("required properties")

    def test_bad_enum_value(self):
        assert_that(self._violation({**CONFORMANT, "status": "SHIPPED"})["$.status"]).contains("one of")

    def test_bad_format_on_nullable_field_stays_precise(self):
        assert_that(self._violation({**CONFORMANT, "customerEmail": "not-an-email"})["$.customerEmail"]).is_equal_to(
            "email format"
        )

    def test_bad_enum_on_nullable_field_stays_precise(self):
        assert_that(self._violation({**CONFORMANT, "priority": "urgent"})["$.priority"]).contains("one of")

    def test_oneof_matching_neither(self):
        assert_that(self._violation({**CONFORMANT, "payment": {"kind": "paypal"}})["$.payment"]).contains(
            "exactly one of"
        )

    def test_nullable_oneof_wrong_value_reports_anyof(self):
        assert_that(self._violation({**CONFORMANT, "refund": {"kind": "paypal"}})["$.refund"]).is_equal_to(
            "one of the declared schemas"
        )

    def test_plain_constraint_falls_back_to_message(self):
        assert_that(self._violation({**CONFORMANT, "name": "ab"})["$.name"]).contains("too short")

    def test_multiple_violations_counted(self):
        body = {"id": "x", "status": "SHIPPED", "payment": {"kind": "paypal"}}
        with pytest.raises(AssertionError, match="3 violations"):
            assert_that(body).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")

    def test_single_violation_is_singular(self):
        with pytest.raises(AssertionError, match="found 1 violation"):
            assert_that({**CONFORMANT, "id": "x"}).conforms_to_openapi(SPEC_30, "/orders/{id}", "get")


class TestStructuralErrors:
    def test_unknown_operation(self):
        with pytest.raises(ValueError, match="no operation <POST /orders/"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "post")

    def test_a_method_that_is_not_a_string_is_named_rather_than_crashing(self):
        """It used to answer with `AttributeError: 'int' object has no attribute 'lower'`."""
        with pytest.raises(TypeError, match="given method arg must be a string"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", 42)  # ty: ignore[invalid-argument-type]  # the shape under test

    def test_unknown_path(self):
        with pytest.raises(ValueError, match="no operation"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/nope", "get")

    def test_unknown_status(self):
        asked = assert_that([CONFORMANT]).conforms_to_openapi
        said = assert_that(asked).raises(ValueError).when_called_with(SPEC_30, "/orders", "get", status=404)
        said.is_equal_to("Operation <GET /orders> declares no response <404>.")

    def test_no_autopickable_status(self):
        spec = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {"418": {"content": {}}}}}}}
        with pytest.raises(ValueError, match="Specify status"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_missing_content_type(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"text/plain": {"schema": {}}}}}}}},
        }
        with pytest.raises(ValueError, match="no <application/json> schema"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_custom_content_type(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {
                "/x": {
                    "get": {
                        "responses": {"200": {"content": {"application/vnd.api+json": {"schema": {"type": "object"}}}}}
                    }
                }
            },
        }
        assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/vnd.api+json")


SPEC_20 = {
    "swagger": "2.0",
    "info": {"title": "Orders", "version": "1.0"},
    "paths": {
        "/orders/{id}": {
            "get": {
                "produces": ["application/json"],
                "responses": {
                    "200": {"schema": {"$ref": "#/definitions/Order"}},
                    "204": {"description": "no content, no schema"},
                },
            }
        }
    },
    "definitions": {
        "Order": {
            "type": "object",
            "required": ["id", "status"],
            "properties": {
                "id": {"type": "integer"},
                "status": {"type": "string", "enum": ["placed", "approved"]},
                "note": {"type": "string", "x-nullable": True},
            },
        }
    },
}


class TestSwagger20:
    PATH, METHOD = "/orders/{id}", "get"

    def test_conformant_body_with_definitions_ref_passes_and_chains(self):
        result = assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(result).is_not_none()

    def test_x_nullable_null_is_conformant(self):
        assert_that({"id": 1, "status": "placed", "note": None}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)

    def test_x_nullable_wrong_type_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": 1, "status": "placed", "note": 5}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.note")

    def test_wrong_type_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": "x", "status": "placed"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.id")

    def test_bad_enum_reports_path(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": 1, "status": "unknown"}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD)
        assert_that(_entries(exc_info.value)).contains_key("$.status")

    def test_response_without_schema_raises(self):
        # the method is echoed upper case, as the spec spells it, not as the argument was written
        with pytest.raises(ValueError, match=r"of <GET /orders/\{id\}> declares no schema"):
            assert_that({"x": 1}).conforms_to_openapi(SPEC_20, self.PATH, self.METHOD, status=204)

    def test_content_type_outside_produces_raises(self):
        # 2.0 has no content-type layer, so the check falls to the operation's `produces` list
        with pytest.raises(ValueError, match="no <application/xml> schema"):
            assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(
                SPEC_20, self.PATH, self.METHOD, content_type="application/xml"
            )

    def test_content_type_inside_produces_passes(self):
        assert_that({"id": 1, "status": "placed"}).conforms_to_openapi(
            SPEC_20, self.PATH, self.METHOD, content_type="application/json"
        )

    def test_global_produces_is_honoured(self):
        spec = {
            "swagger": "2.0",
            "produces": ["application/json"],
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "object"}}}}}},
        }
        with pytest.raises(ValueError, match="no <application/xml> schema"):
            assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/xml")

    def test_absent_produces_skips_the_content_type_check(self):
        spec = {"swagger": "2.0", "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "object"}}}}}}}
        assert_that({}).conforms_to_openapi(spec, "/x", "get", content_type="application/xml")


class TestStatusAutoSelection:
    """With no ``status=`` the first declared response among 200, 201, the range ``2XX`` and ``default`` is
    used, in that order.  Every test above either names a status or declares exactly one, so neither the
    order nor the membership of that list was pinned."""

    @staticmethod
    def _spec(*status_codes):
        responses = {
            code: {"content": {"application/json": {"schema": {"type": "object", "required": [code]}}}}
            for code in status_codes
        }
        return {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": responses}}}}

    def test_two_hundred_wins_over_two_hundred_and_one(self):
        # each schema demands a property named after its status code, so the failure names the one chosen
        with pytest.raises(AssertionError, match="200"):
            assert_that({}).conforms_to_openapi(self._spec("201", "200"), "/x", "get")

    def test_two_hundred_and_one_wins_over_default(self):
        with pytest.raises(AssertionError, match="201"):
            assert_that({}).conforms_to_openapi(self._spec("default", "201"), "/x", "get")

    def test_default_is_used_when_nothing_else_is_declared(self):
        with pytest.raises(AssertionError, match="default"):
            assert_that({}).conforms_to_openapi(self._spec("default"), "/x", "get")

    def test_an_unpickable_set_names_what_was_declared(self):
        with pytest.raises(ValueError, match=r"Specify status: <GET /x> declares responses \['418'\]"):
            assert_that({}).conforms_to_openapi(self._spec("418"), "/x", "get")


class _Code(int):
    """A number of a class of its own, which prints as it pleases."""

    def __str__(self) -> str:
        return "a code"


class TestAResponseIsSelectedByItsCodeThenItsRangeThenTheDefault:
    """OpenAPI 3: "2XX represents all response codes between [200-299]", "the explicit code definition takes
    precedence over the range definition for that code", and ``default`` documents "responses other than the
    ones declared for specific HTTP response codes".  Swagger 2.0 has codes and ``default``, and no ranges.

    Each schema asks for a property named after its own key, so a failure names the response chosen."""

    @staticmethod
    def _spec(declared, dialect="3.0.3"):
        if dialect == "2.0":
            responses = {code: {"schema": {"type": "object", "required": [code]}} for code in declared}
            return {"swagger": "2.0", "paths": {"/x": {"get": {"responses": responses}}}}
        responses = {
            code: {"content": {"application/json": {"schema": {"type": "object", "required": [code]}}}}
            for code in declared
        }
        return {"openapi": dialect, "paths": {"/x": {"get": {"responses": responses}}}}

    def _chosen(self, declared, status, dialect="3.0.3"):
        options = {} if status is None else {"status": status}
        try:
            assert_that({}).conforms_to_openapi(self._spec(declared, dialect), "/x", "get", **options)
        except AssertionError as failure:
            return str(failure).partition("response <")[2].partition(">")[0]
        except ValueError as refusal:
            return f"refused: {refusal}"
        return "passed"

    @pytest.mark.parametrize(
        ("declared", "status", "chosen"),
        [
            (("2XX",), 200, "2XX"),
            (("2XX",), "299", "2XX"),
            (("2XX",), "2XX", "2XX"),
            (("200", "2XX"), 200, "200"),
            (("200", "2XX"), 204, "2XX"),
            (("2XX", "default"), 200, "2XX"),
            (("2XX", "default"), 404, "default"),
            (("4XX", "default"), 404, "4XX"),
            (("default",), 500, "default"),
            (("1XX", "3XX", "5XX"), 101, "1XX"),
            (("1XX", "3XX", "5XX"), 302, "3XX"),
            (("1XX", "3XX", "5XX"), 503, "5XX"),
        ],
    )
    def test_the_code_comes_first_then_its_range_then_the_default(self, declared, status, chosen):
        assert_that(self._chosen(declared, status)).is_equal_to(chosen)
        assert_that(self._chosen(declared, status, "3.1.0")).is_equal_to(chosen)

    @pytest.mark.parametrize(
        ("declared", "status"),
        [
            (("5XX",), 404),
            (("2xx",), 200),
            (("2XX",), 20),
            (("2XX",), "2000"),
            (("2XX",), "20X"),
            (("6XX",), 600),
            (("0XX",), "099"),
            (("2XX",), "2\u0660\u0660"),
        ],
        ids=[
            "another range",
            "a small x",
            "two digits",
            "four digits",
            "no code",
            "past 5XX",
            "below 1XX",
            "other digits",
        ],
    )
    def test_a_status_no_declaration_covers_is_refused_by_its_name(self, declared, status):
        assert_that(self._chosen(declared, status)).is_equal_to(
            f"refused: Operation <GET /x> declares no response <{status}>."
        )

    @pytest.mark.parametrize("status", [404, "404", http.HTTPStatus.NOT_FOUND, _Code(404)])
    def test_a_status_is_read_by_the_number_it_holds(self, status):
        """Below 3.11 the `str` of `HTTPStatus.NOT_FOUND` was its name, and the response it named was not found."""
        assert_that(self._chosen(("404", "4XX"), status)).is_equal_to("404")
        assert_that(self._chosen(("4XX",), status)).is_equal_to("4XX")
        assert_that(self._chosen(("200",), status)).is_equal_to(
            "refused: Operation <GET /x> declares no response <404>."
        )

    def test_a_truth_value_is_no_status(self):
        assert_that(self._chosen(("1", "default"), True)).is_equal_to("default")
        assert_that(self._chosen(("1",), True)).is_equal_to("refused: Operation <GET /x> declares no response <True>.")

    def test_a_response_declared_under_an_empty_key_is_found_by_it(self):
        assert_that(self._chosen(("",), "")).is_equal_to("")

    def test_swagger_two_has_the_default_and_no_ranges(self):
        assert_that(self._chosen(("2XX",), 200, "2.0")).starts_with("refused: Operation <GET /x> declares no response")
        assert_that(self._chosen(("default",), 404, "2.0")).is_equal_to("default")
        assert_that(self._chosen(("200", "default"), 200, "2.0")).is_equal_to("200")

    @pytest.mark.parametrize(
        ("declared", "dialect", "chosen"),
        [
            (("2XX",), "3.0.3", "2XX"),
            (("2XX", "default"), "3.0.3", "2XX"),
            (("201", "2XX"), "3.0.3", "201"),
            (("2XX", "default"), "3.1.0", "2XX"),
            (("2XX", "default"), "2.0", "default"),
        ],
    )
    def test_with_no_status_named_a_success_range_comes_ahead_of_the_default(self, declared, dialect, chosen):
        assert_that(self._chosen(declared, None, dialect)).is_equal_to(chosen)

    def test_with_no_status_named_swagger_two_does_not_pick_a_range(self):
        assert_that(self._chosen(("2XX",), None, "2.0")).starts_with("refused: Specify status")

    @pytest.mark.parametrize(
        ("reference", "found"),
        [
            ("#/x-shared/0", True),
            ("#/x-shared/-1", True),
            ("#/x%2Dshared/0", True),
            ("#/x-shared/1", False),
            ("#/x-shared/first", False),
            ("#/x-shared/0/content/application~1json/schema/type/0", False),
        ],
        ids=["by its index", "from the end", "percent-encoded", "past the list", "by a name", "into a text"],
    )
    def test_a_response_that_is_a_reference_into_a_list_is_read_as_a_pointer_is(self, reference, found):
        shared = [{"content": {"application/json": {"schema": {"type": "integer"}}}}]
        spec = {
            "openapi": "3.0.3",
            "x-shared": shared,
            "paths": {"/x": {"get": {"responses": {"200": {"$ref": reference}}}}},
        }
        try:
            said = "took" if assert_that("seven").check().conforms_to_openapi(spec, "/x", "get").passed else "failed"
        except ValueError as refused:
            said = str(refused)
        assert_that(said).is_equal_to("failed" if found else "Response <200> of <GET /x> has an unresolvable $ref.")
        if found:
            assert_that(7).conforms_to_openapi(spec, "/x", "get")

    def test_a_response_under_a_range_may_be_a_reference(self):
        named = {"content": {"application/json": {"schema": {"type": "integer"}}}}
        spec = {
            "openapi": "3.0.3",
            "components": {"responses": {"Count": named}},
            "paths": {"/x": {"get": {"responses": {"2XX": {"$ref": "#/components/responses/Count"}}}}},
        }
        assert_that(7).conforms_to_openapi(spec, "/x", "get", status=204)
        with pytest.raises(AssertionError, match="response <2XX>"):
            assert_that("seven").conforms_to_openapi(spec, "/x", "get", status=204)


class TestStructuralErrorsNameTheMethodInUpperCase:
    """The operation is echoed as the caller would find it in the spec, which is upper case: the
    argument itself is lower case, so a message built from it unchanged reads as a different key."""

    def test_an_unknown_operation_upper_cases_the_method(self):
        with pytest.raises(ValueError, match=r"<POST /orders/\{id\}>"):
            assert_that(CONFORMANT).conforms_to_openapi(SPEC_30, "/orders/{id}", "post")

    def test_an_unknown_status_upper_cases_the_method(self):
        with pytest.raises(ValueError, match=r"<GET /orders>"):
            assert_that([CONFORMANT]).conforms_to_openapi(SPEC_30, "/orders", "get", status=404)

    def test_a_missing_content_type_upper_cases_the_method(self):
        spec = {
            "openapi": "3.0.3",
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"text/plain": {"schema": {}}}}}}}},
        }
        with pytest.raises(ValueError, match=r"<GET /x>"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")

    def test_a_response_without_a_schema_upper_cases_the_method(self):
        spec = {"openapi": "3.0.3", "paths": {"/x": {"get": {"responses": {"200": {}}}}}}
        with pytest.raises(ValueError, match=r"<GET /x>"):
            assert_that(CONFORMANT).conforms_to_openapi(spec, "/x", "get")


class TestNullableInsideArrays:
    """``nullable: true`` is rewritten to a null-union before jsonschema sees it, and the rewrite has
    to reach schemas nested inside a list.  Nothing put a nullable schema inside one."""

    _SPEC: typing.ClassVar = {
        "openapi": "3.0.3",
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "who": {
                                                "oneOf": [
                                                    {"type": "string", "nullable": True},
                                                    {"type": "integer"},
                                                ]
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    def test_a_null_inside_a_oneof_branch_is_conformant(self):
        assert_that({"who": None}).conforms_to_openapi(self._SPEC, "/x", "get")

    def test_a_non_null_value_still_has_to_match_a_branch(self):
        with pytest.raises(AssertionError):
            assert_that({"who": 1.5}).conforms_to_openapi(self._SPEC, "/x", "get")


class TestSwagger20NullableInsideArrays:
    """Swagger 2.0 spells nullability ``x-nullable``, and the rewrite carries that keyword down.
    Losing it inside a list recursion falls back to the 3.0 spelling, which a 2.0 spec never uses."""

    _SPEC: typing.ClassVar = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "produces": ["application/json"],
                    "responses": {
                        "200": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "who": {"allOf": [{"type": "string", "x-nullable": True}]},
                                },
                            }
                        }
                    },
                }
            }
        },
    }

    def test_a_null_inside_an_allof_branch_is_conformant(self):
        assert_that({"who": None}).conforms_to_openapi(self._SPEC, "/x", "get")

    def test_a_wrong_type_inside_the_branch_still_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"who": 1}).conforms_to_openapi(self._SPEC, "/x", "get")


class TestTheRequirementNamesTheCallersSpec:
    """The spec is normalised to string keys before validation, and the failure reported that copy.

    `not_` binds the caller's own spec through the signature, so one requirement had two answers
    whenever the spec carried an integer status key, as YAML parses `200`.
    """

    _SPEC: typing.ClassVar = {
        "openapi": "3.0.3",
        "paths": {
            "/x": {"get": {"responses": {200: {"content": {"application/json": {"schema": {"type": "integer"}}}}}}}
        },
    }

    def test_a_failure_carries_the_spec_it_was_given(self):
        asked = assert_that("text").check().conforms_to_openapi(self._SPEC, "/x", "get").requirement
        assert_that(asked.parameters["spec"]).is_same_as(self._SPEC)

    def test_the_negated_failure_carries_the_same(self):
        asked = assert_that(1).check().not_.conforms_to_openapi(self._SPEC, "/x", "get").requirement
        assert_that(asked.parameters["spec"]).is_same_as(self._SPEC)


class TestTheDialectFollowsTheVersion:
    """Read as 3.0 a newer spec validates against Draft 4, which has no word for a keyword of a later draft."""

    @staticmethod
    def _spec(version):
        return {
            "openapi": version,
            "paths": {
                "/x": {
                    "get": {"responses": {"200": {"content": {"application/json": {"schema": {"const": "only-this"}}}}}}
                }
            },
        }

    @pytest.mark.parametrize("version", ["3.1.0", "3.2.0"])
    def test_a_2020_12_keyword_is_read(self, version):
        outcome = assert_that("other").check().conforms_to_openapi(self._spec(version), "/x", "get", status=200)
        assert_that(outcome.passed).is_false()

    def test_an_unknown_version_is_refused_rather_than_guessed(self):
        with pytest.raises(ValueError, match="is not one this can validate"):
            assert_that("other").conforms_to_openapi(self._spec("4.0.0"), "/x", "get", status=200)

    def test_three_zero_refuses_the_keyword_it_would_pass_over(self):
        asked = assert_that("other").conforms_to_openapi
        said = assert_that(asked).raises(ValueError).when_called_with(self._spec("3.0.3"), "/x", "get", status=200)
        said.is_equal_to(
            "Schema <#/paths/~1x/get/responses/200/content/application~1json/schema> holds <const>, which OpenAPI"
            " 3.0 does not have, so the response would not be held to it as written."
            " Leave it out, or move the spec to OpenAPI 3.1 as a whole: with the version line alone changed,"
            " `nullable` and a boolean exclusive bound are what is not read."
        )


class TestAKeywordTheDialectDoesNotHaveIsRefused:
    """Draft 4 reads OpenAPI 3.0 and Swagger 2.0, and passes over a keyword of a later JSON Schema.  Each schema
    here took a value its keyword forbids, in silence."""

    LATER: typing.ClassVar[dict[str, tuple[dict, object]]] = {
        "const": ({"const": "a"}, "b"),
        "contains": ({"type": "array", "contains": {"type": "integer"}}, ["a"]),
        "propertyNames": ({"type": "object", "propertyNames": {"maxLength": 1}}, {"long": 1}),
        "if": ({"if": {"type": "integer"}, "then": {"minimum": 5}}, 1),
        "dependentRequired": ({"type": "object", "dependentRequired": {"a": ["b"]}}, {"a": 1}),
        "dependentSchemas": ({"type": "object", "dependentSchemas": {"a": {"required": ["b"]}}}, {"a": 1}),
        "unevaluatedProperties": ({"type": "object", "unevaluatedProperties": False}, {"b": 2}),
        "unevaluatedItems": ({"type": "array", "unevaluatedItems": False}, [1]),
        "prefixItems": ({"type": "array", "prefixItems": [{"type": "integer"}]}, ["a"]),
        "$dynamicRef": ({"$dynamicRef": "#/components/schemas/Text"}, 5),
        "$recursiveRef": ({"type": "object", "properties": {"next": {"$recursiveRef": "#"}}}, {"next": 1}),
        "exclusiveMinimum as a number": ({"type": "integer", "exclusiveMinimum": 5}, 1),
        "exclusiveMaximum as a number": ({"type": "integer", "exclusiveMaximum": 5}, 9),
    }

    @staticmethod
    def _spec(schema, dialect="3.0.3", components=None):
        named = {"Text": {"type": "string"}, **(components or {})}
        if dialect == "2.0":
            return {
                "swagger": "2.0",
                "definitions": named,
                "paths": {"/x": {"get": {"responses": {"200": {"schema": schema}}}}},
            }
        response = {"content": {"application/json": {"schema": schema}}}
        return {
            "openapi": dialect,
            "components": {"schemas": named},
            "paths": {"/x": {"get": {"responses": {"200": response}}}},
        }

    def _said(self, schema, dialect="3.0.3", value=None, components=None):
        try:
            assert_that(value).conforms_to_openapi(self._spec(schema, dialect, components), "/x", "get")
        except AssertionError:
            return "failed"
        except ValueError as refusal:
            return str(refusal)
        return "passed"

    @pytest.mark.parametrize("keyword", sorted(LATER))
    def test_each_is_refused_by_name_whatever_the_value(self, keyword):
        schema, forbidden = self.LATER[keyword]
        for dialect, named in (("3.0.3", "OpenAPI 3.0"), ("3.0", "OpenAPI 3.0"), ("2.0", "Swagger 2.0")):
            said = self._said(schema, dialect, forbidden)
            assert_that(said).contains(f"holds <{keyword}>, which {named} does not have")
            assert_that(self._said(schema, dialect, "anything else")).is_equal_to(said)

    @pytest.mark.parametrize("keyword", sorted(set(LATER) - {"$recursiveRef"}))
    def test_each_is_read_where_the_spec_declares_three_one(self, keyword):
        schema, forbidden = self.LATER[keyword]
        assert_that(self._said(schema, "3.1.0", forbidden)).is_equal_to("failed")

    def test_the_one_that_three_one_gave_up_is_read_by_the_draft_that_had_it(self):
        """``$recursiveRef`` is of 2019-09 alone: Draft 4 passes it over, and so does 2020-12, which renamed it."""
        jsonschema = pytest.importorskip("jsonschema")
        ring = {"$recursiveAnchor": True, "type": "object", "properties": {"next": {"$recursiveRef": "#"}}}
        assert_that(jsonschema.Draft201909Validator(ring).is_valid({"next": 1})).is_false()
        assert_that(jsonschema.Draft4Validator(ring).is_valid({"next": 1})).is_true()
        assert_that(self._said(ring, value={"next": 1})).contains("holds <$recursiveRef>")

    def test_the_version_line_alone_is_no_way_out(self):
        """What the refusal says, held: read as 3.1 with nothing else changed, the bound of 3.0 forbids nothing."""
        mixed = {"type": "integer", "minimum": 5, "exclusiveMinimum": True, "const": 5}
        assert_that(self._said(mixed, value=5)).contains("holds <const>", "move the spec to OpenAPI 3.1 as a whole")
        assert_that(self._said(mixed, "3.1.0", value=5)).is_equal_to("passed")
        assert_that(self._said({"type": "integer", "minimum": 5, "exclusiveMinimum": True}, value=5)).is_equal_to(
            "failed"
        )

    def test_the_refusal_names_where_the_schema_stands(self):
        order = {"type": "object", "properties": {"status": {"allOf": [{"type": "string"}, {"const": "open"}]}}}
        said = self._said(
            {"type": "array", "items": {"$ref": "#/components/schemas/Order"}}, components={"Order": order}
        )
        assert_that(said).starts_with("Schema <#/components/schemas/Order/properties/status/allOf/1> holds <const>,")
        named = self._said({"type": "object", "properties": {"a/b~c": {"const": 1}}})
        assert_that(named).contains("/schema/properties/a~1b~0c> holds <const>")

    def test_the_schema_named_is_the_one_reached_and_not_one_equal_to_it(self):
        twin = {"const": 1}
        said = self._said({"allOf": [{"type": "integer"}, {"const": 1}], "example": twin}, components={"Unused": twin})
        assert_that(said).contains("/schema/allOf/1> holds <const>")

    def test_every_keyword_of_one_schema_is_named(self):
        said = self._said({"type": "integer", "exclusiveMinimum": 5, "const": 7, "if": {}})
        assert_that(said).contains("holds <const>, <if>, <exclusiveMinimum as a number>, which OpenAPI 3.0")

    @pytest.mark.parametrize(
        ("schema", "value"),
        [
            ({"type": "object", "properties": {"const": {"type": "string"}, "if": {"type": "string"}}}, {"const": "x"}),
            ({"then": {"minimum": 5}, "else": {"minimum": 5}, "minContains": 2, "maxContains": 3}, 1),
            ({"type": "integer", "minimum": 1, "exclusiveMinimum": True, "maximum": 9, "exclusiveMaximum": False}, 9),
            ({"type": "integer", "exclusiveMinimum": None, "exclusiveMaximum": "5"}, 9),
            ({"$ref": "#/components/schemas/Text", "const": "ignored beside a reference"}, "a"),
            ({"type": "string", "example": {"const": "a"}, "default": "a", "x-rule": {"if": {}}}, "a"),
            ({"enum": [{"const": "a"}, "a"]}, {"const": "a"}),
            (
                {"type": "string", "contentMediaType": "text/plain", "$comment": "an annotation", "deprecated": True},
                "a",
            ),
            (
                {"type": "object", "patternProperties": {"^a": {"type": "string"}}, "dependencies": {"a": ["b"]}},
                {"b": 1},
            ),
        ],
        ids=[
            "a property of that name",
            "a keyword that forbids nothing alone",
            "a bound as the flag it is",
            "a bound that is no number",
            "beside a reference",
            "inside a value",
            "inside an enum",
            "an annotation",
            "a keyword of draft four",
        ],
    )
    def test_what_loses_nothing_is_not_refused(self, schema, value):
        swagger = {**schema, "$ref": "#/definitions/Text"} if "$ref" in schema else schema
        assert_that(self._said(schema, value=value)).is_equal_to("passed")
        assert_that(self._said(swagger, "2.0", value=value)).is_equal_to("passed")

    def test_a_schema_the_validator_never_asks_is_not_read(self):
        """Beside an ``items`` that is one schema Draft 4 does not ask ``additionalItems``, so nothing is lost there."""
        beside = {"type": "array", "items": {"type": "integer"}, "additionalItems": {"const": 0}}
        assert_that(self._said(beside, value=[1, 2])).is_equal_to("passed")
        assert_that(self._said({"type": "array", "additionalItems": {"const": 0}}, value=[1])).is_equal_to("passed")
        listed = {"type": "array", "items": [{"type": "integer"}], "additionalItems": {"const": 0}}
        assert_that(self._said(listed, value=[1, 5])).contains("/schema/additionalItems> holds <const>")

    def test_a_schema_never_asked_for_what_stands_beside_it_is_read_all_the_same(self):
        """The limit of that rule: the walk goes by the shape of a schema, not by what its patterns take."""
        every_name = {"type": "object", "patternProperties": {"^": {}}, "additionalProperties": {"const": 0}}
        assert_that(self._said(every_name, value={"a": 1})).contains("/schema/additionalProperties> holds <const>")

    @pytest.mark.parametrize(
        "reference",
        [
            "#/components/schemas/Rule",
            "urn:assertpy-openapi#/components/schemas/Rule",
            "#/components/schemas/Both/allOf/0",
        ],
        ids=["by its pointer", "by the address of the document", "into a list"],
    )
    def test_a_keyword_behind_any_reference_the_validator_follows_is_refused(self, reference):
        components = {"Rule": {"const": "a"}, "Both": {"allOf": [{"const": "a"}]}}
        assert_that(self._said({"$ref": reference}, value="b", components=components)).contains("holds <const>")

    @pytest.mark.parametrize("dialect", ["3.0.3", "2.0"])
    def test_a_schema_out_of_the_document_is_read_in_the_dialect_it_names(self, dialect):
        """A metaschema is no part of the spec: jsonschema reads it by its own ``$schema``, and nothing is refused."""
        spec = self._spec({"$ref": "https://json-schema.org/draft/2020-12/schema"}, dialect)
        assert_that({"type": "string"}).conforms_to_openapi(spec, "/x", "get")
        outcome = assert_that({"additionalProperties": {"type": 5}}).check().conforms_to_openapi(spec, "/x", "get")
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["$.additionalProperties.type"])

    def test_a_schema_that_names_a_dialect_of_its_own_is_read_as_the_document_is(self):
        """jsonschema reads a schema by the ``$schema`` it declares.  OpenAPI 3.0 has none in a Schema Object,
        so the document stays one dialect: the keyword is refused, and what 3.0 ignores is ignored there too."""
        jsonschema = pytest.importorskip("jsonschema")
        later = "https://json-schema.org/draft/2020-12/schema"
        declared = {"$schema": later, "const": "a"}
        assert_that(jsonschema.Draft4Validator({"properties": {"p": declared}}).is_valid({"p": "b"})).is_false()
        assert_that(jsonschema.Draft4Validator({"properties": {"p": {"const": "a"}}}).is_valid({"p": "b"})).is_true()
        said = self._said({"type": "object", "properties": {"p": declared}}, value={"p": "b"})
        assert_that(said).contains("/schema/properties/p> holds <const>")

        ignored = {"$ref": "#/components/schemas/Any", "properties": {"p": {"type": "integer"}}}
        beside = {"$schema": later, "allOf": [ignored]}
        flag = {"$schema": later, "type": "integer", "minimum": 0, "exclusiveMinimum": True}
        assert_that(jsonschema.Draft202012Validator(flag).is_valid(1)).is_false()
        spec = self._spec({"type": "object", "properties": {"held": beside, "count": flag}}, components={"Any": {}})
        before = copy.deepcopy(spec)
        assert_that({"held": {"p": "b"}, "count": 1}).conforms_to_openapi(spec, "/x", "get")
        outcome = assert_that({"held": {"p": "b"}, "count": 0}).check().conforms_to_openapi(spec, "/x", "get")
        assert_that([entry.path for entry in outcome.diff.entries]).is_equal_to(["$.count"])
        assert_that(spec).is_equal_to(before)

    @pytest.mark.parametrize("declared", [{}, {"$schema": "https://json-schema.org/draft/2020-12/schema"}])
    def test_a_nullable_schema_that_names_a_dialect_is_read_as_one_that_names_none(self, declared):
        """On a composition ``nullable`` moves the schema a level down, and the ``$schema`` must not go with it."""
        flag = {"type": "integer", "minimum": 0, "exclusiveMinimum": True}
        for schema in ({**declared, **flag, "nullable": True}, {**declared, "nullable": True, "allOf": [flag]}):
            answers = [self._said(schema, value=value) for value in (1, None, 0)]
            assert_that(answers).is_equal_to(["passed", "passed", "failed"])

    def test_a_reference_under_a_schema_with_an_id_of_its_own_is_read_from_that_schema(self):
        """The validator enters a child by its ``id``, so ``#/definitions/T`` under it names the child's own."""
        held = {"id": "http://example.test/p", "allOf": [{"$ref": "#/definitions/T"}]}
        order = {"type": "object", "properties": {"p": held}}

        def spec(inner):
            named = {
                "T": {"type": "integer"},
                "Order": {**order, "properties": {"p": {**held, "definitions": {"T": inner}}}},
            }
            return self._spec({"$ref": "#/definitions/Order"}, "2.0", named)

        refused = assert_that(assert_that({"p": "b"}).conforms_to_openapi).raises(ValueError)
        refused.when_called_with(spec({"const": "a"}), "/x", "get").contains(
            "Schema <#/definitions/Order/properties/p/definitions/T> holds <const>"
        )
        maybe = spec({"type": "string", "x-nullable": True})
        assert_that({"p": None}).conforms_to_openapi(maybe, "/x", "get")
        assert_that({"p": "text"}).conforms_to_openapi(maybe, "/x", "get")
        assert_that(assert_that({"p": 5}).check().conforms_to_openapi(maybe, "/x", "get").passed).is_false()

    def test_a_reference_by_the_id_of_a_schema_is_followed_as_the_validator_follows_it(self):
        named = {
            "Rule": {"id": "http://example.test/rule", "const": "a"},
            "Maybe": {"id": "http://example.test/maybe", "type": "string", "x-nullable": True},
        }
        spec = self._spec({"$ref": "http://example.test/rule"}, "2.0", named)
        assert_that(assert_that("b").conforms_to_openapi).raises(ValueError).when_called_with(
            spec, "/x", "get"
        ).contains("Schema <#/definitions/Rule> holds <const>, which Swagger 2.0 does not have")
        assert_that(None).conforms_to_openapi(
            self._spec({"$ref": "http://example.test/maybe"}, "2.0", named), "/x", "get"
        )

    def test_a_bound_as_a_number_is_read_by_draft_four_as_a_flag_whatever_the_number(self):
        """Why the number is refused beside a ``minimum`` as well: there it is not passed over, it is misread."""
        jsonschema = pytest.importorskip("jsonschema")
        apart = {"type": "integer", "minimum": 0, "exclusiveMinimum": 5}
        assert_that(jsonschema.Draft4Validator(apart).is_valid(3)).is_true()
        assert_that(jsonschema.Draft202012Validator(apart).is_valid(3)).is_false()
        alike = {"type": "integer", "minimum": 5, "exclusiveMinimum": 5}
        for value in (4, 5, 6):
            assert_that(jsonschema.Draft4Validator(alike).is_valid(value)).is_equal_to(
                jsonschema.Draft202012Validator(alike).is_valid(value)
            )
        for schema in (apart, alike):
            assert_that(self._said(schema, value=6)).contains("holds <exclusiveMinimum as a number>")

    def test_a_keyword_that_forbids_nothing_where_it_stands_is_refused_as_well(self):
        for schema in ({"if": {}}, {"dependentRequired": {}}, {"unevaluatedProperties": True}):
            assert_that(self._said(schema, value=1)).contains("does not have")

    def test_a_schema_the_response_does_not_reach_is_not_read(self):
        assert_that(self._said({"type": "string"}, value="a", components={"Unused": {"const": 1}})).is_equal_to(
            "passed"
        )

    def test_the_spec_is_refused_before_the_value_is_read(self):
        class Unread:
            def __getattribute__(self, name):
                raise AssertionError(f"the value was asked for {name}")

        assert_that(self._said({"const": 1}, value=Unread())).contains("holds <const>")


class TestTheVersionIsReadRatherThanPrefixed:
    """`"3.10.0"` starts with `"3.1"` and is not it, and a spec read in the wrong dialect passes anything."""

    @staticmethod
    def _spec(version):
        return {
            "openapi": version,
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {}}}}}}}},
        }

    @pytest.mark.parametrize("version", ["3.10.0", "3.20.0", "3.2garbage", "4.0.0", "2.0"])
    def test_a_version_that_is_not_one_of_the_three_is_refused(self, version):
        with pytest.raises(ValueError, match="is not one this can validate"):
            assert_that({}).conforms_to_openapi(self._spec(version), "/x", "get", status=200)

    @pytest.mark.parametrize("version", ["3.0.3", "3.1.0", "3.2.0"])
    def test_the_three_it_reads_are_read(self, version):
        assert_that({}).conforms_to_openapi(self._spec(version), "/x", "get", status=200)


class TestAVersionIsMatchedWhole:
    """A prefix is not a version: "3.10.0" starts with "3.1" and "20" is not Swagger's "2.0"."""

    @staticmethod
    def _openapi(version):
        return {
            "openapi": version,
            "paths": {"/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {}}}}}}}},
        }

    @staticmethod
    def _swagger(version):
        return {
            "swagger": version,
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "object", "nullable": True}}}}}},
        }

    @pytest.mark.parametrize("version", ["3.1.garbage", "3.1.", "3.1x", " 3.1.0"])
    def test_a_version_that_only_looks_like_one_is_refused(self, version):
        with pytest.raises(ValueError, match="is not one this can validate"):
            assert_that({}).conforms_to_openapi(self._openapi(version), "/x", "get", status=200)

    def test_a_patch_number_is_still_a_version(self):
        assert_that({}).conforms_to_openapi(self._openapi("3.1.99"), "/x", "get", status=200)

    @staticmethod
    def _nullable(version):
        """A spec whose schema says `nullable`, which only the OpenAPI 3.0 rewrite turns into a null type."""
        return {
            "swagger": version,
            "paths": {"/x": {"get": {"responses": {"200": {"schema": {"type": "string", "nullable": True}}}}}},
        }

    def test_swagger_is_its_own_version_and_not_a_prefix(self):
        """Read by prefix, "20" took the Swagger path, which rewrites `x-nullable` and not `nullable`."""
        with pytest.raises(AssertionError, match="to conform to the OpenAPI schema"):
            assert_that(None).conforms_to_openapi(self._nullable("2.0"), "/x", "get", status=200)
        assert_that(None).conforms_to_openapi(self._nullable("20"), "/x", "get", status=200)
