import json
import sys
from unittest.mock import patch

import pytest

pytest.importorskip("jsonpath_ng", reason="jsonpath-ng not installed")
pytest.importorskip("jsonschema", reason="jsonschema not installed")

from assertpy import assert_that, json_mixin, match, soft_assertions
from assertpy.json_mixin import _ensure_jsonpath_ng, _ensure_jsonschema

DATA = {
    "users": [
        {"name": "Alice", "age": 30, "roles": ["admin", "user"]},
        {"name": "Bob", "age": 25, "roles": ["user"]},
    ],
    "meta": {"total": 2, "page": 1},
}

SCHEMA = {
    "type": "object",
    "properties": {
        "users": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name", "age"],
            },
        },
        "meta": {"type": "object"},
    },
    "required": ["users", "meta"],
}


class TestAtJsonPath:
    def test_simple_path(self):
        assert_that(DATA).at_json_path("$.meta.total").is_equal_to(2)

    def test_nested_object(self):
        assert_that(DATA).at_json_path("$.users[0].name").is_equal_to("Alice")

    def test_wildcard_returns_list(self):
        assert_that(DATA).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])

    def test_array_element(self):
        assert_that(DATA).at_json_path("$.users[1].age").is_equal_to(25)

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="to exist"):
            assert_that(DATA).at_json_path("$.nonexistent")

    def test_chaining_after_extract(self):
        assert_that(DATA).at_json_path("$.users[0].roles").satisfies(match.contains("admin"))

    def test_on_list_root(self):
        items = [{"id": 1}, {"id": 2}]
        assert_that(items).at_json_path("$[0].id").is_equal_to(1)

    def test_preserves_description(self):
        result = assert_that(DATA).described_as("api response").at_json_path("$.meta.total")
        assert_that(result.description).is_equal_to("api response")

    def test_preserves_kind_in_soft(self):
        with soft_assertions():
            assert_that(DATA).at_json_path("$.meta.total").is_equal_to(2)


class TestHasJsonPath:
    def test_existing_path(self):
        assert_that(DATA).has_json_path("$.meta.total")

    def test_nested_path(self):
        assert_that(DATA).has_json_path("$.users[0].name")

    def test_nonexistent_path_fails(self):
        with pytest.raises(AssertionError, match="to exist"):
            assert_that(DATA).has_json_path("$.nonexistent")

    def test_chaining(self):
        assert_that(DATA).has_json_path("$.meta.total").has_json_path("$.users")


class TestDoesNotHaveJsonPath:
    def test_nonexistent_path(self):
        assert_that(DATA).does_not_have_json_path("$.error")

    def test_existing_path_fails(self):
        with pytest.raises(AssertionError, match="to not exist"):
            assert_that(DATA).does_not_have_json_path("$.meta.total")

    def test_chaining(self):
        assert_that(DATA).does_not_have_json_path("$.error").does_not_have_json_path("$.missing")


class TestMatchesJsonSchema:
    def test_valid_schema(self):
        assert_that(DATA).matches_json_schema(SCHEMA)

    def test_invalid_schema_fails(self):
        bad_data = {"users": "not_an_array", "meta": {}}
        with pytest.raises(AssertionError, match="validation failed"):
            assert_that(bad_data).matches_json_schema(SCHEMA)

    def test_missing_required_field(self):
        incomplete = {"users": []}
        with pytest.raises(AssertionError, match="validation failed"):
            assert_that(incomplete).matches_json_schema(SCHEMA)

    def test_simple_type_schema(self):
        assert_that(42).matches_json_schema({"type": "integer"})

    def test_string_type_schema_fails(self):
        with pytest.raises(AssertionError, match="validation failed"):
            assert_that(42).matches_json_schema({"type": "string"})

    def test_chaining(self):
        assert_that(DATA).matches_json_schema(SCHEMA).has_json_path("$.meta")


class TestMatchesJsonSchemaFromFile:
    def test_load_from_file(self, tmp_path):
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps(SCHEMA), encoding="utf-8")
        assert_that(DATA).matches_json_schema_from_file(schema_file)

    def test_load_from_string_path(self, tmp_path):
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps(SCHEMA), encoding="utf-8")
        assert_that(DATA).matches_json_schema_from_file(str(schema_file))

    def test_invalid_data_from_file(self, tmp_path):
        schema_file = tmp_path / "schema.json"
        schema_file.write_text(json.dumps({"type": "string"}), encoding="utf-8")
        with pytest.raises(AssertionError, match="validation failed"):
            assert_that(42).matches_json_schema_from_file(schema_file)


class TestJsonPathIsCompiledOnce:
    """Parsing a path is the whole cost of a path assertion; the lookup is a rounding error."""

    def test_the_same_path_is_parsed_once(self):
        json_mixin._compiled_json_path.cache_clear()
        parse = _ensure_jsonpath_ng().parse
        with patch.object(_ensure_jsonpath_ng(), "parse", side_effect=parse) as spy:
            for _ in range(5):
                assert_that(DATA).at_json_path("$.meta.total").is_equal_to(2)
                assert_that(DATA).has_json_path("$.meta.total")
        assert_that(spy.call_count).is_equal_to(1)

    def test_a_different_path_is_parsed_again(self):
        json_mixin._compiled_json_path.cache_clear()
        parse = _ensure_jsonpath_ng().parse
        with patch.object(_ensure_jsonpath_ng(), "parse", side_effect=parse) as spy:
            assert_that(DATA).has_json_path("$.meta.total")
            assert_that(DATA).has_json_path("$.meta.page")
        assert_that(spy.call_count).is_equal_to(2)

    def test_the_cache_is_bounded(self):
        # a path built from test data is a fresh string, so an unbounded cache would grow with the suite
        assert_that(json_mixin._compiled_json_path.cache_info().maxsize).is_not_none()


class TestJsonImportErrors:
    def test_missing_jsonpath_ng(self):
        with (
            patch.dict(sys.modules, {"jsonpath_ng": None, "jsonpath_ng.ext": None}),
            pytest.raises(ImportError, match="jsonpath-ng is required"),
        ):
            _ensure_jsonpath_ng()

    def test_missing_jsonschema(self):
        with patch.dict(sys.modules, {"jsonschema": None}), pytest.raises(ImportError, match="jsonschema is required"):
            _ensure_jsonschema()


class TestJsonSoftMode:
    def test_has_json_path_in_soft(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(DATA).has_json_path("$.nonexistent")
            assert_that(DATA).does_not_have_json_path("$.meta.total")
        msg = str(exc_info.value)
        assert_that(msg).contains("1.")
        assert_that(msg).contains("2.")

    def test_schema_in_soft(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(42).matches_json_schema({"type": "string"})
            assert_that("foo").matches_json_schema({"type": "integer"})
        msg = str(exc_info.value)
        assert_that(msg).contains("1.")
        assert_that(msg).contains("2.")


class TestAPathIsRefusedBeforeItIsHashed:
    """The cache hashes its argument, so a list came back as "unhashable type: 'list'"."""

    @pytest.mark.parametrize("path", [["a"], 5, None, {"a"}], ids=["list", "int", "none", "set"])
    def test_a_path_that_is_not_a_string_names_the_argument(self, path):
        with pytest.raises(TypeError, match="given path arg must be a string"):
            assert_that({"a": 1}).at_json_path(path)

    def test_a_string_path_still_answers(self):
        assert_that({"a": 1}).at_json_path("$.a").is_equal_to(1)
