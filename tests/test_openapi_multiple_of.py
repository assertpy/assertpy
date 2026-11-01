"""`multipleOf` in `conforms_to_openapi`, asked of the numbers as a document writes them.

jsonschema divides two floats and asks whether the quotient is whole, so ``19.99`` failed a
``multipleOf: 0.01``: the quotient is ``1998.9999999999998``.  Every draft has the keyword hold where the
division "results in an integer", which is said of the numbers and not of the floats nearest them.  The cases
the official suite has for the keyword are held in `tests/test_openapi_format_suite.py`.
"""

from __future__ import annotations

import decimal
import fractions
import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, json_mixin

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema not installed")

_VERSIONS = ["2.0", "3.0.3", "3.1.0"]


def _spec(schema: dict[str, Any], version: str) -> dict[str, Any]:
    if version == "2.0":
        return {"swagger": "2.0", "paths": {"/x": {"get": {"responses": {"200": {"schema": schema}}}}}}
    response = {"content": {"application/json": {"schema": schema}}}
    return {"openapi": version, "paths": {"/x": {"get": {"responses": {"200": response}}}}}


def _took(schema: dict[str, Any], value: object, version: str = "3.0.3") -> bool:
    try:
        assert_that(value).conforms_to_openapi(_spec(schema, version), "/x", "get")
    except AssertionFailure:
        return False
    return True


def _conforms(value: object, step: object, version: str = "3.0.3") -> bool:
    return _took({"multipleOf": step}, value, version)


class TestAMultipleIsAskedOfTheNumbersAsWritten:
    @pytest.mark.parametrize("version", _VERSIONS)
    @pytest.mark.parametrize(
        ("value", "step"),
        [
            (19.99, 0.01),
            (0.3, 0.1),
            (4.35, 0.01),
            (0.07, 0.01),
            (1.1, 0.1),
            (-19.99, 0.01),
            (10, 0.01),
            (3, 0.5),
            (7.5, 2.5),
            (8, 2),
            (0, 0.01),
            (0.0, 7),
            (1e-07, 1e-08),
            (12391239123, 1e-08),
            (1e300, 1e-10),
            (10**400, 5),
            (decimal.Decimal("19.99"), 0.01),
            (19.99, decimal.Decimal("0.01")),
            (fractions.Fraction(1999, 100), 0.01),
        ],
    )
    def test_a_number_that_is_a_multiple_passes(self, value, step, version):
        assert_that(_conforms(value, step, version)).is_true()

    @pytest.mark.parametrize("version", _VERSIONS)
    @pytest.mark.parametrize(
        ("value", "step"),
        [
            (19.995, 0.01),
            (0.30000000000000004, 0.1),
            (7, 2),
            (3, 0.7),
            (35, 1.5),
            (1e308, 0.123456789),
            (10**400 + 1, 5),
            (decimal.Decimal("19.995"), 0.01),
            (float("inf"), 0.01),
            (float("-inf"), 2),
            (float("nan"), 0.01),
            (decimal.Decimal("Infinity"), 2),
            (decimal.Decimal("NaN"), 2),
        ],
    )
    def test_a_number_that_is_none_fails(self, value, step, version):
        assert_that(_conforms(value, step, version)).is_false()

    @pytest.mark.parametrize("value", ["19.99", True, False, None, [3], {"a": 3}])
    def test_what_is_no_number_is_not_held_to_it(self, value):
        assert_that(_conforms(value, 2)).is_true()

    def test_a_float_of_a_class_of_its_own_is_read_by_the_print_of_float(self):
        price = type("Price", (float,), {"__repr__": lambda self: "a price", "__str__": lambda self: "a price"})
        assert_that(_conforms(price(19.99), 0.01)).is_true()
        assert_that(_conforms(price(19.995), 0.01)).is_false()
        assert_that(_conforms(19.99, price(0.01))).is_true()

    def test_a_numpy_float_is_read_as_the_float_it_is(self):
        numpy = pytest.importorskip("numpy", reason="numpy not installed")
        assert_that(_conforms(numpy.float64(19.99), 0.01)).is_true()
        assert_that(_conforms(numpy.float64(19.995), 0.01)).is_false()
        assert_that(_conforms(numpy.int64(8), 2)).is_true()
        assert_that(_conforms(numpy.int64(7), 2)).is_false()

    @given(digits=st.integers(0, 6), unit=st.integers(1, 9999), count=st.integers(-(10**6), 10**6))
    def test_a_count_of_steps_passes_and_half_a_step_past_it_fails(self, digits, unit, count):
        """Twelve digits at most, so each float prints as the decimal it was made from."""
        step = decimal.Decimal(unit).scaleb(-digits)
        assert_that(_conforms(float(step * count), float(step))).is_true()
        assert_that(_conforms(float(step * count + step / 2), float(step))).is_false()

    def test_the_failure_names_the_place_the_number_and_the_step(self):
        schema = {"type": "object", "properties": {"price": {"type": "number", "multipleOf": 0.01}}}
        with pytest.raises(AssertionFailure) as failed:
            assert_that({"price": 19.995}).conforms_to_openapi(_spec(schema, "3.0.3"), "/x", "get")
        entries = failed.value.diff.entries
        assert_that([(entry.path, entry.actual, entry.expected) for entry in entries]).is_equal_to(
            [("$.price", 19.995, "19.995 is not a multiple of 0.01")]
        )


class TestAStepThatIsNoNumberAboveZeroIsRefused:
    """Every draft has the keyword take a number "strictly greater than 0".  jsonschema raised
    `ZeroDivisionError` for a zero, took a negative step by its size, and passed every number for an infinity."""

    @pytest.mark.parametrize("version", _VERSIONS)
    @pytest.mark.parametrize(
        "step",
        [0, 0.0, -2, -0.01, float("inf"), float("nan"), decimal.Decimal("Infinity"), "0.01", True, None, [2]],
        ids=repr,
    )
    def test_it_is_refused_by_name(self, step, version):
        refused = None
        try:
            assert_that(4).conforms_to_openapi(_spec({"multipleOf": step}, version), "/x", "get")
        except ValueError as refusal:
            refused = str(refusal)
        assert_that(refused).is_not_none().contains("multipleOf", f"<{step!r}>")

    def test_it_is_refused_where_a_number_is_held_to_it(self):
        assert_that(_conforms("no number", 0)).is_true()


class TestASchemaThatDeclaresItsDialect:
    """jsonschema hands a schema with a ``$schema`` of its own to the class it keeps for that dialect, whose
    division is jsonschema's.  Here it goes to the class made from that one, which divides as written.  OpenAPI
    3.0 has no ``$schema`` in a Schema Object, and it is taken out there."""

    _DIALECT = "https://json-schema.org/draft/2020-12/schema"

    @pytest.mark.parametrize(
        "wrap",
        [
            lambda schema: schema,
            lambda schema: {"allOf": [schema]},
            lambda schema: {"type": "object", "properties": {"price": schema}},
            lambda schema: {"$ref": "#/components/schemas/Price"},
        ],
        ids=["the schema itself", "a branch", "a property", "a schema referred to"],
    )
    @pytest.mark.parametrize("declared", [_DIALECT, _DIALECT + "#"], ids=["as written", "with an empty fragment"])
    @pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
    def test_the_dialect_of_the_document_declared_again_changes_no_verdict(self, wrap, declared, version):
        for dialect in ({}, {"$schema": declared}):
            price = {**dialect, "type": "number", "multipleOf": 0.01}
            spec = _spec(wrap(price), version) | {"components": {"schemas": {"Price": price}}}
            holding = "properties" in wrap(price)
            for value, valid in ((19.99, True), (19.995, False)):
                took = (
                    assert_that({"price": value} if holding else value).check().conforms_to_openapi(spec, "/x", "get")
                )
                assert_that(took.passed).described_as(f"{value} under {dialect}").is_equal_to(valid)

    def test_only_a_document_that_may_hold_one_is_asked_at_every_schema(self, monkeypatch):
        """The asking cost 0.1 to 0.2 us for each schema entered.  A document cut to its part holds no ``$schema``, and
        under 3.0 each one is taken out, so neither is asked."""
        asked = []
        made = json_mixin._dividing_as_written
        monkeypatch.setattr(
            json_mixin, "_dividing_as_written", lambda cls, **named: asked.append(named) or made(cls, **named)
        )
        plain = {"type": "number", "multipleOf": 0.01}
        declared = {"$schema": self._DIALECT, **plain}
        for schema, version, redeclared in (
            (plain, "3.1.0", {False}),
            (plain, "3.0.3", {False}),
            (declared, "3.0.3", {False}),
            (declared, "3.1.0", {True}),
        ):
            asked.clear()
            assert_that(_took(schema, 19.99, version)).is_true()
            assert_that({named.get("redeclared", False) for named in asked}).is_equal_to(redeclared)

    @pytest.mark.parametrize(
        "dialect",
        [
            "http://json-schema.org/draft-04/schema#",
            "http://json-schema.org/draft-06/schema#",
            "http://json-schema.org/draft-07/schema#",
            "https://json-schema.org/draft/2019-09/schema",
            "https://json-schema.org/draft/2020-12/schema",
        ],
    )
    def test_whatever_dialect_a_schema_of_three_one_declares_it_is_divided_as_written(self, dialect):
        declared = {"$schema": dialect, "multipleOf": 0.01}
        nested = {"$schema": dialect, "properties": {"price": {"multipleOf": 0.01}}}
        again = {"$schema": dialect, "allOf": [{"$schema": self._DIALECT, "multipleOf": 0.01}]}
        for schema, good, bad in (
            (declared, 19.99, 19.995),
            (nested, {"price": 19.99}, {"price": 19.995}),
            (again, 0.3, 0.305),
        ):
            assert_that(_took(schema, good, "3.1.0")).described_as(f"{good} under {schema}").is_true()
            assert_that(_took(schema, bad, "3.1.0")).described_as(f"{bad} under {schema}").is_false()

    @pytest.mark.parametrize(
        ("name", "beside_a_reference"),
        [
            ("Draft4Validator", False),
            ("Draft6Validator", False),
            ("Draft7Validator", False),
            ("Draft201909Validator", True),
            ("Draft202012Validator", True),
        ],
    )
    def test_the_class_made_for_a_dialect_reads_a_reference_as_the_class_of_jsonschema_does(
        self, name, beside_a_reference
    ):
        """The drafts up to 7 read a ``$ref`` alone, and what stands beside it is ignored.  Reached from a schema
        of another dialect, jsonschema reads it as the schema that reached it does, and so does the class here."""
        theirs = getattr(jsonschema, name)
        ours = json_mixin._dividing_as_written(theirs, redeclared=True)
        at_the_root = {"definitions": {"T": {}}, "$ref": "#/definitions/T", "minLength": 5}
        assert_that(theirs(at_the_root).is_valid("a")).is_equal_to(not beside_a_reference)
        assert_that(ours(at_the_root).is_valid("a")).is_equal_to(not beside_a_reference)
        declared = {"$schema": theirs.META_SCHEMA["$schema"], "$ref": "#/$defs/T", "minLength": 5, "multipleOf": 0.01}
        reaching = {"$defs": {"T": {}}, "allOf": [declared]}
        latest = jsonschema.Draft202012Validator
        for value in ("a", "a text", 19.995):
            assert_that(
                json_mixin._dividing_as_written(latest, redeclared=True)(reaching).is_valid(value)
            ).described_as(repr(value)).is_equal_to(latest(reaching).is_valid(value))
        assert_that(latest(reaching).is_valid(19.99)).is_false()
        assert_that(json_mixin._dividing_as_written(latest, redeclared=True)(reaching).is_valid(19.99)).is_true()

    def test_a_dialect_with_no_such_keyword_is_left_to_jsonschema(self):
        """Draft 3 has ``divisibleBy`` and no ``multipleOf``, and a class made for it here would add one."""
        declared = {"$schema": "http://json-schema.org/draft-03/schema#", "multipleOf": 2, "divisibleBy": 2}
        assert_that(_took(declared, 4, "3.1.0")).is_true()
        assert_that(_took(declared, 3, "3.1.0")).is_false()
        assert_that(
            _took({"$schema": "http://json-schema.org/draft-03/schema#", "multipleOf": 2}, 3, "3.1.0")
        ).is_true()


class TestDigitsAFloatDoesNotKeep:
    def test_they_are_gone_before_the_check_and_a_decimal_keeps_them(self):
        written = "1.0000000000000001"
        assert_that(float(written)).is_equal_to(1.0)
        assert_that(_conforms(float(written), 1)).is_true()
        assert_that(_conforms(json.loads(written, parse_float=decimal.Decimal), 1)).is_false()
        assert_that(_conforms(json.loads("19.990000000000000001", parse_float=decimal.Decimal), 0.01)).is_false()
        assert_that(_conforms(json.loads("19.990000000000000000", parse_float=decimal.Decimal), 0.01)).is_true()

    @given(
        value=st.decimals(min_value=-(10**9), max_value=10**9, places=22),
        step=st.decimals(min_value="0.0000000001", max_value=10**6, places=10),
        count=st.integers(-(10**9), 10**9),
    )
    def test_two_decimals_are_divided_exactly(self, value, step, count):
        """Held to `Fraction`'s own remainder, on numbers of more digits than a float keeps."""
        assert_that(_conforms(value, step)).is_equal_to(fractions.Fraction(value) % fractions.Fraction(step) == 0)
        assert_that(_conforms(step * count, step)).is_true()


class TestTheClassThatDividesSoIsMadeOnce:
    def test_a_second_check_makes_none(self, monkeypatch):
        """Made for each check, the class cost the check 213 us."""
        for version in _VERSIONS:
            assert_that(_conforms(19.99, 0.01, version)).is_true()
        made = []
        create = jsonschema.validators.create
        monkeypatch.setattr(jsonschema.validators, "create", lambda **named: made.append(named) or create(**named))
        for version in _VERSIONS:
            assert_that(_conforms(19.99, 0.01, version)).is_true()
        assert_that(made).is_empty()

    def test_the_step_of_a_schema_is_read_once_for_all_the_numbers_held_to_it(self, monkeypatch):
        """Read again for each number, it cost the number 0.7 us."""
        read = []
        as_written = json_mixin._as_written
        monkeypatch.setattr(json_mixin, "_as_written", lambda number: read.append(number) or as_written(number))
        step = 0.0078125
        assert_that(_took({"type": "array", "items": {"multipleOf": step}}, [step * 2, step * 3, step * 5])).is_true()
        assert_that(read.count(step)).is_less_than_or_equal_to(1)
        assert_that(read).contains(step * 2, step * 3, step * 5)

    def test_what_stands_beside_a_reference_is_read_as_the_dialect_reads_it(self):
        """Draft 4 reads a ``$ref`` alone and 2020-12 reads what stands beside it.  A class made by ``extend()``
        of jsonschema 4.18 had lost the first, and validated what a 3.0 schema holds beside its reference."""
        referring = {"$ref": "#/components/schemas/Text", "minLength": 5, "multipleOf": 2}
        spec = _spec(referring, "3.0.3") | {"components": {"schemas": {"Text": {}}}}
        assert_that(assert_that("a").check().conforms_to_openapi(spec, "/x", "get").passed).is_true()
        assert_that(assert_that(3).check().conforms_to_openapi(spec, "/x", "get").passed).is_true()
        spec = _spec(referring, "3.1.0") | {"components": {"schemas": {"Text": {}}}}
        assert_that(assert_that("a").check().conforms_to_openapi(spec, "/x", "get").passed).is_false()
        assert_that(assert_that(3).check().conforms_to_openapi(spec, "/x", "get").passed).is_false()

    def test_it_is_the_class_handed_in_with_one_keyword_of_its_own(self):
        ours = json_mixin._dividing_as_written(jsonschema.Draft4Validator)
        theirs = jsonschema.Draft4Validator.VALIDATORS
        assert_that({name for name in theirs if ours.VALIDATORS[name] is not theirs[name]}).is_equal_to({"multipleOf"})
        assert_that(set(ours.VALIDATORS)).is_equal_to(set(theirs))
