import collections.abc
import dataclasses
import datetime
import enum
import inspect
import io
import itertools
import sys
import types
import typing

import pytest

from assertpy import AssertionFailure, assert_conforms, assert_that, match, soft_assertions
from assertpy._engine import _contract
from assertpy._engine._contract import (
    UncheckableDriftError,
    _placed,
    contract_drift,
    shape,
    shape_diff,
)
from assertpy.matchers import (
    EachMatcher,
    IgnoreMatcher,
    IsNonEmptyStringMatcher,
    IsUuidMatcher,
    StructureMatcher,
)
from tests.optional import needs


class TestIgnoreMatcher:
    def test_matches_anything(self):
        matcher = match.ignore()
        assert_that(matcher.matches(None)).is_true()
        assert_that(matcher.matches(42)).is_true()
        assert_that(matcher.matches("hello")).is_true()
        assert_that(matcher.matches([1, 2, 3])).is_true()
        assert_that(matcher.matches({})).is_true()

    def test_describe(self):
        assert_that(match.ignore().describe()).is_equal_to("anything (ignored)")

    def test_is_instance(self):
        assert_that(match.ignore()).is_instance_of(IgnoreMatcher)


class TestIsUuidMatcher:
    def test_matches_valid_uuid4(self):
        assert_that(match.is_uuid().matches("550e8400-e29b-41d4-a716-446655440000")).is_true()

    def test_matches_valid_uuid1(self):
        assert_that(match.is_uuid().matches("6ba7b810-9dad-11d1-80b4-00c04fd430c8")).is_true()

    def test_does_not_match_invalid(self):
        assert_that(match.is_uuid().matches("not-a-uuid")).is_false()

    def test_does_not_match_empty(self):
        assert_that(match.is_uuid().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_uuid().matches(42)).is_false()
        assert_that(match.is_uuid().matches(None)).is_false()

    def test_describe(self):
        assert_that(match.is_uuid().describe()).is_equal_to("a valid UUID string")

    def test_is_instance(self):
        assert_that(match.is_uuid()).is_instance_of(IsUuidMatcher)


class TestIsNonEmptyStringMatcher:
    def test_matches_non_empty(self):
        assert_that(match.is_non_empty_string().matches("hello")).is_true()
        assert_that(match.is_non_empty_string().matches(" ")).is_true()

    def test_does_not_match_empty(self):
        assert_that(match.is_non_empty_string().matches("")).is_false()

    def test_does_not_match_non_string(self):
        assert_that(match.is_non_empty_string().matches(42)).is_false()
        assert_that(match.is_non_empty_string().matches(None)).is_false()
        assert_that(match.is_non_empty_string().matches(["a"])).is_false()

    def test_describe(self):
        assert_that(match.is_non_empty_string().describe()).is_equal_to("a non-empty string")

    def test_is_instance(self):
        assert_that(match.is_non_empty_string()).is_instance_of(IsNonEmptyStringMatcher)


class TestEachMatcher:
    def test_all_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([1, 2, 3])).is_true()

    def test_some_do_not_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([1, -2, 3])).is_false()

    def test_empty_iterable(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches([])).is_true()

    def test_non_iterable(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.matches(42)).is_false()

    def test_describe(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.describe()).is_equal_to("each item matching a positive value")

    def test_describe_mismatch_with_failing_item(self):
        matcher = match.each_item(match.is_positive())
        result = matcher.describe_mismatch([1, -2, 3])
        assert_that(result).contains("index 1")
        assert_that(result).contains("-2")

    def test_describe_mismatch_non_iterable(self):
        matcher = match.each_item(match.is_positive())
        result = matcher.describe_mismatch(42)
        assert_that(result).contains("not iterable")

    def test_is_instance(self):
        assert_that(match.each_item(match.is_positive())).is_instance_of(EachMatcher)

    def test_composition(self):
        matcher = match.each_item(match.between(1, 10) & match.is_instance_of(int))
        assert_that(matcher.matches([1, 5, 10])).is_true()
        assert_that(matcher.matches([1, 5, 11])).is_false()

    def test_describe_mismatch_all_match(self):
        matcher = match.each_item(match.is_positive())
        assert_that(matcher.describe_mismatch([1, 2, 3])).is_equal_to("was <[1, 2, 3]>")

    def test_describe_mismatch_carries_what_the_item_matcher_found(self):
        """Only the requirement was named, so the field a record failed on was left for the reader to find."""
        matcher = match.each_item(match.structure({"city": "Paris"}))
        assert_that(matcher.describe_mismatch([{"city": "Paris"}, {"city": "Oslo"}])).is_equal_to(
            "item at index 1 <{'city': 'Oslo'}> did not match a mapping matching structure {city: <Paris>} "
            "(at <city>: expected <Paris>, but was <Oslo>)"
        )

    def test_each_item_is_asked_once_for_its_verdict_and_its_reason(self):
        class RefusesOnce:
            def __init__(self):
                self.asked = 0

            def matches(self, value):
                self.asked += 1
                return self.asked > 1

            def describe(self):
                return "asked twice"

            def describe_mismatch(self, value):
                return f"was asked {self.asked} time"

        outcome = match.each_item(RefusesOnce()).evaluate([7])
        assert_that(outcome.matched).is_false()
        assert_that(outcome.mismatch).is_equal_to("item at index 0 <7> did not match asked twice (was asked 1 time)")

    def test_an_item_that_is_its_own_iterator_is_not_read_again_for_a_reason(self):
        """Read again, the remainder was described as the item: `<-3>` at index 0, where `-2` had failed."""
        outcome = match.each_item(match.each_item(match.greater_than(0))).evaluate([iter([1, -2, -3])])
        assert_that(outcome.mismatch).ends_with("did not match each item matching a value greater than <0>")

    def test_an_item_that_refuses_to_be_iterated_still_gets_its_failure_described(self):
        """A closed file answers `iter()` with `ValueError`, which replaced the failure it was asked about."""
        closed = io.StringIO()
        closed.close()
        outcome = match.each_item(match.is_none()).evaluate([closed])
        assert_that(outcome.matched).is_false()
        assert_that(outcome.mismatch).starts_with("item at index 0 <")

    def test_an_endless_item_is_answered_rather_than_read_for_a_reason(self):
        endless = itertools.chain([5], itertools.repeat(0))
        outcome = match.each_item(match.each_item(match.less_than(3))).evaluate([endless])
        assert_that(outcome.matched).is_false()


class TestStructureMatcher:
    def test_basic_match(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(matcher.matches({"name": "Alice", "age": 30})).is_true()

    def test_missing_key(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": match.is_positive()})
        assert_that(matcher.matches({"name": "Alice"})).is_false()

    def test_value_mismatch(self):
        matcher = match.structure({"age": match.is_positive()})
        assert_that(matcher.matches({"age": -1})).is_false()

    def test_extra_keys_allowed(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        assert_that(matcher.matches({"name": "Alice", "extra": "field"})).is_true()

    def test_raw_value_equality(self):
        matcher = match.structure({"status": "active", "count": 5})
        assert_that(matcher.matches({"status": "active", "count": 5})).is_true()
        assert_that(matcher.matches({"status": "inactive", "count": 5})).is_false()

    def test_nested_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string(), "role": "admin"}})
        assert_that(matcher.matches({"user": {"name": "Alice", "role": "admin"}})).is_true()
        assert_that(matcher.matches({"user": {"name": "Alice", "role": "user"}})).is_false()

    def test_nested_not_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        assert_that(matcher.matches({"user": "not a dict"})).is_false()

    def test_non_dict_value(self):
        matcher = match.structure({"a": 1})
        assert_that(matcher.matches("not a dict")).is_false()
        assert_that(matcher.matches(42)).is_false()
        assert_that(matcher.matches(None)).is_false()

    def test_describe(self):
        matcher = match.structure({"name": match.is_non_empty_string(), "age": 30})
        desc = matcher.describe()
        assert_that(desc).contains("name: a non-empty string")
        assert_that(desc).contains("age: <30>")

    def test_describe_nested(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        desc = matcher.describe()
        assert_that(desc).contains("user: {name: a non-empty string}")

    def test_describe_mismatch_missing_key(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        result = matcher.describe_mismatch({"age": 30})
        assert_that(result).contains("missing key <name>")

    def test_describe_mismatch_value_fail(self):
        matcher = match.structure({"age": match.is_positive()})
        result = matcher.describe_mismatch({"age": -1})
        assert_that(result).contains("at <age>")
        assert_that(result).contains("a positive value")

    def test_describe_mismatch_non_dict(self):
        matcher = match.structure({"a": 1})
        result = matcher.describe_mismatch("not a dict")
        assert_that(result).contains("was not a mapping")

    def test_describe_mismatch_nested_path(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        result = matcher.describe_mismatch({"user": {"name": ""}})
        assert_that(result).contains("user.name")

    def test_nested_structure_matcher_matches(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        assert_that(matcher.matches({"address": {"city": "NYC"}})).is_true()

    def test_nested_structure_matcher_joined_path(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.describe_mismatch({"address": {"city": "LA"}})
        assert_that(result).contains("address.city")

    def test_nested_structure_matcher_non_dict(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.describe_mismatch({"address": "not a dict"})
        assert_that(result).contains("at <address>")

    def test_is_instance(self):
        assert_that(match.structure({"a": 1})).is_instance_of(StructureMatcher)

    def test_with_ignore(self):
        matcher = match.structure({"id": match.ignore(), "name": match.is_non_empty_string()})
        assert_that(matcher.matches({"id": 12345, "name": "Alice"})).is_true()
        assert_that(matcher.matches({"id": None, "name": "Bob"})).is_true()

    def test_with_uuid(self):
        matcher = match.structure({"id": match.is_uuid()})
        assert_that(matcher.matches({"id": "550e8400-e29b-41d4-a716-446655440000"})).is_true()
        assert_that(matcher.matches({"id": "not-uuid"})).is_false()

    def test_with_each_item(self):
        matcher = match.structure({"scores": match.each_item(match.between(0, 100))})
        assert_that(matcher.matches({"scores": [85, 90, 78]})).is_true()
        assert_that(matcher.matches({"scores": [85, 101, 78]})).is_false()

    def test_deeply_nested(self):
        matcher = match.structure({"a": {"b": {"c": match.equal_to(42)}}})
        assert_that(matcher.matches({"a": {"b": {"c": 42}}})).is_true()
        assert_that(matcher.matches({"a": {"b": {"c": 99}}})).is_false()

    def test_describe_mismatch_raw_value(self):
        matcher = match.structure({"status": "active"})
        result = matcher.describe_mismatch({"status": "inactive"})
        assert_that(result).contains("at <status>")
        assert_that(result).contains("expected <active>")
        assert_that(result).contains("was <inactive>")

    def test_describe_mismatch_all_match(self):
        matcher = match.structure({"a": 1})
        assert_that(matcher.describe_mismatch({"a": 1})).is_equal_to("was <{'a': 1}>")

    def test_circular_reference_detected(self):
        circular = {}
        circular["self"] = circular
        spec = {}
        spec["self"] = spec
        matcher = match.structure(spec)
        assert_that(matcher.matches(circular)).is_false()
        assert_that(matcher.describe_mismatch(circular)).contains("circular reference")

    def test_deep_nesting(self):
        value = {"a": 1}
        spec = {"a": 1}
        current_v = value
        current_s = spec
        for _i in range(20):
            inner_v = {"a": 1}
            inner_s = {"a": 1}
            current_v["nested"] = inner_v
            current_s["nested"] = inner_s
            current_v = inner_v
            current_s = inner_s
        matcher = match.structure(spec)
        assert_that(matcher.matches(value)).is_true()

    def test_shared_subobject_across_keys_is_not_a_cycle(self):
        # reuse under sibling keys is a DAG, not a cycle: matches() must scope its visited-set per path
        frag_spec = {"n": match.is_positive()}
        spec = {"a": frag_spec, "b": frag_spec}
        frag_val = {"n": 5}
        value = {"a": frag_val, "b": frag_val}
        assert_that(match.structure(spec).matches(value)).is_true()
        assert_that(value).satisfies(match.structure(spec))


def _texts(mismatches):
    """A mismatch list with its paths rendered, which is the half these tests are about."""
    return [(path.text, actual, description) for path, actual, description in mismatches]


class TestCollectMismatches:
    def test_collects_all_failing_fields(self):
        matcher = match.structure({"a": match.is_positive(), "b": match.is_positive(), "c": match.is_positive()})
        result = matcher.collect_mismatches({"a": -1, "b": 5, "c": -3})
        assert_that([entry[0].text for entry in result]).is_equal_to(["a", "c"])

    def test_empty_when_all_match(self):
        matcher = match.structure({"a": match.is_positive(), "status": "active"})
        assert_that(matcher.collect_mismatches({"a": 5, "status": "active"})).is_empty()

    def test_nested_structure_matcher_joins_path(self):
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches({"address": {"city": "LA"}})
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_missing_key_recorded(self):
        matcher = match.structure({"name": match.is_non_empty_string()})
        path, actual, description = matcher.collect_mismatches({})[0]
        assert_that(path.text).is_equal_to("name")
        assert_that(repr(actual)).is_equal_to("<missing>")
        assert_that(description).is_equal_to("a non-empty string")

    def test_nested_structure_matcher_against_non_dict(self):
        matcher = match.structure({"user": match.structure({"name": match.is_non_empty_string()})})
        result = matcher.collect_mismatches({"user": "not a dict"})
        assert_that(result[0][0].text).is_equal_to("user")

    def test_plain_nested_dict_against_non_dict(self):
        matcher = match.structure({"user": {"name": match.is_non_empty_string()}})
        path, _actual, description = matcher.collect_mismatches({"user": "not a dict"})[0]
        assert_that(path.text).is_equal_to("user")
        assert_that(description).is_equal_to("a mapping")

    def test_plain_nested_dict_recurses(self):
        matcher = match.structure({"user": {"role": "admin"}})
        result = matcher.collect_mismatches({"user": {"role": "guest"}})
        assert_that(result[0][0].text).is_equal_to("user.role")

    def test_raw_value_mismatch(self):
        matcher = match.structure({"status": "active"})
        path, actual, description = matcher.collect_mismatches({"status": "inactive"})[0]
        assert_that(path.text).is_equal_to("status")
        assert_that(actual).is_equal_to("inactive")
        assert_that(description).is_equal_to("<active>")

    def test_circular_reference(self):
        circular = {}
        circular["self"] = circular
        spec = {}
        spec["self"] = spec
        result = match.structure(spec).collect_mismatches(circular)
        assert_that(result[0][1]).is_equal_to("<circular ref>")


class TestMatchesStructureMethod:
    def test_basic(self):
        user = {"name": "Alice", "age": 30}
        assert_that(user).matches_structure({"name": match.is_non_empty_string(), "age": match.between(18, 120)})

    def test_failure_missing_key(self):
        with pytest.raises(AssertionError, match="missing key"):
            assert_that({"name": "Alice"}).matches_structure(
                {"name": match.is_non_empty_string(), "email": match.is_non_empty_string()}
            )

    def test_failure_value_mismatch(self):
        with pytest.raises(AssertionError, match="at <age>"):
            assert_that({"age": -5}).matches_structure({"age": match.is_positive()})

    def test_the_mismatch_names_the_offending_value(self):
        # every assertion matched on the path, so the detail was free to describe None and name only the key
        with pytest.raises(AssertionError) as failure:
            assert_that({"age": 10}).matches_structure({"age": match.greater_than(18)})
        assert_that(str(failure.value)).contains("but was <10>").does_not_contain("but was <None>")

    def test_nested(self):
        data = {"user": {"name": "Alice", "settings": {"theme": "dark"}}}
        assert_that(data).matches_structure(
            {"user": {"name": match.is_non_empty_string(), "settings": {"theme": "dark"}}}
        )

    def test_non_dict_val(self):
        with pytest.raises(TypeError, match="val must be a mapping"):
            assert_that("not a dict").matches_structure({"a": 1})

    def test_non_dict_spec(self):
        with pytest.raises(TypeError, match="given spec arg must be a dict"):
            assert_that({"a": 1}).matches_structure("not a dict")

    def test_chaining(self):
        data = {"name": "Alice", "age": 30}
        assert_that(data).matches_structure({"name": match.is_non_empty_string()}).contains_key("age")

    def test_with_uuid_and_ignore(self):
        response = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "created_at": "2024-01-01T00:00:00Z",
            "name": "Test",
        }
        assert_that(response).matches_structure(
            {
                "id": match.is_uuid(),
                "created_at": match.ignore(),
                "name": match.equal_to("Test"),
            }
        )

    def test_error_message_contains_structure_description(self):
        with pytest.raises(AssertionError, match="to match structure"):
            assert_that({"x": 1}).matches_structure({"x": match.is_non_empty_string()})

    def test_failure_attaches_structured_diff(self):
        value = {"role": "guest", "address": {"city": "LA"}}
        try:
            assert_that(value).matches_structure(
                {"role": match.is_in("admin", "user"), "address": match.structure({"city": match.equal_to("NYC")})}
            )
        except AssertionFailure as exc:
            assert_that(exc.diff.kind).is_equal_to("match")
            assert_that([entry.path for entry in exc.diff.entries]).contains("role", "address.city")
            assert_that(exc.actual).is_equal_to(value)
            assert_that(exc.expected).is_not_none()
        else:
            raise AssertionError("expected AssertionFailure") from None


class _SpecModel:
    """Duck-types a pydantic v2 model (exposes a recursive model_dump()) for the dependency-free
    structural-matching tests.  __eq__ is left at the object default on purpose, so
    ``model == match.structure(...)`` falls back to the matcher's reflected __eq__, exactly as real
    pydantic, whose __eq__ returns NotImplemented for non-model operands.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def model_dump(self):
        return {
            key: value.model_dump() if isinstance(value, _SpecModel) else value for key, value in self.__dict__.items()
        }


class TestStructureMatcherOnModel:
    """Structural matching accepts pydantic-style models (model_dump()), via duck-type without the dep."""

    def test_matches_structure_on_model(self):
        user = _SpecModel(id=1, name="Alice")
        assert_that(user).matches_structure({"id": match.is_positive(), "name": match.is_non_empty_string()})

    def test_matches_structure_on_model_failure(self):
        user = _SpecModel(id=-1, name="Alice")
        with pytest.raises(AssertionError, match="at <id>"):
            assert_that(user).matches_structure({"id": match.is_positive()})

    def test_matches_structure_on_nested_model(self):
        user = _SpecModel(id=1, address=_SpecModel(city="NYC"))
        assert_that(user).matches_structure({"id": match.is_positive(), "address": {"city": match.equal_to("NYC")}})

    def test_satisfies_structure_on_model(self):
        user = _SpecModel(id=1, name="Alice")
        assert_that(user).satisfies(match.structure({"id": match.is_positive()}))

    def test_each_structure_over_models(self):
        users = [_SpecModel(id=1), _SpecModel(id=2)]
        assert_that(users).each(match.structure({"id": match.is_positive()}))

    def test_model_equals_structure_matcher(self):
        user = _SpecModel(id=1, name="Alice")
        spec = match.structure({"id": match.is_positive(), "name": match.is_non_empty_string()})
        assert_that(user == spec).is_true()

    def test_model_not_equals_structure_matcher_on_mismatch(self):
        user = _SpecModel(id=-1)
        assert_that(user == match.structure({"id": match.is_positive()})).is_false()

    def test_matcher_matches_model_directly(self):
        matcher = match.structure({"id": match.is_positive()})
        assert_that(matcher.matches(_SpecModel(id=5))).is_true()

    def test_describe_mismatch_on_model(self):
        matcher = match.structure({"id": match.is_positive()})
        assert_that(matcher.describe_mismatch(_SpecModel(id=-1))).contains("at <id>")

    def test_real_pydantic_model(self):
        needs("pydantic")
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str

        class User(BaseModel):
            id: int
            name: str
            address: Address

        user = User(id=1, name="Alice", address=Address(city="NYC"))
        assert_that(user).matches_structure(
            {"id": match.is_positive(), "name": match.is_non_empty_string(), "address": {"city": match.equal_to("NYC")}}
        )
        assert_that(user).satisfies(match.structure({"id": match.is_positive()}))
        assert_that(user == match.structure({"id": match.is_positive()})).is_true()
        with pytest.raises(AssertionError, match="at <id>"):
            assert_that(User(id=-1, name="Bob", address=Address(city="LA"))).matches_structure(
                {"id": match.is_positive()}
            )


class _AmbiguousArray:
    """Array-like: element-wise ``==`` whose truth value is ambiguous (an ndarray stand-in)."""

    def __array__(self):
        return None

    def __eq__(self, other):
        return self

    def __bool__(self):
        raise ValueError("ambiguous")

    __hash__ = object.__hash__


class TestArrayLeavesInStructure:
    def test_raw_array_leaf_raises_actionable_error(self):
        with pytest.raises(TypeError, match="matches_structure"):
            assert_that({"a": _AmbiguousArray()}).matches_structure({"a": _AmbiguousArray()})

    def test_matcher_wrapped_array_leaf_records_mismatch(self):
        with pytest.raises(AssertionError, match="a value equal to"):
            assert_that({"a": _AmbiguousArray()}).matches_structure({"a": match.equal_to(_AmbiguousArray())})

    def test_matcher_that_cannot_evaluate_records_mismatch(self):
        with pytest.raises(AssertionError, match="at <n>"):
            assert_that({"n": "not-a-number"}).matches_structure({"n": match.is_positive()})


class TestModelNestedInsideDict:
    """A model under a plain dict is normalized per level, so it matches specs and keeps leaf paths."""

    def test_model_under_nested_structure_matcher_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        matcher = match.structure({"address": match.structure({"city": match.equal_to("NYC")})})
        result = matcher.collect_mismatches(value)
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_model_under_plain_dict_spec_matches(self):
        value = {"address": _SpecModel(city="NYC")}
        assert_that(match.structure({"address": {"city": "NYC"}}).matches(value)).is_true()

    def test_model_under_plain_dict_spec_keeps_leaf_path(self):
        value = {"address": _SpecModel(city="LA")}
        result = match.structure({"address": {"city": "NYC"}}).collect_mismatches(value)
        assert_that(result[0][0].text).is_equal_to("address.city")

    def test_matches_structure_failure_shows_model_leaf_path(self):
        with pytest.raises(AssertionError, match=r"at <address\.city>"):
            assert_that({"address": _SpecModel(city="LA")}).matches_structure(
                {"address": match.structure({"city": "NYC"})}
            )


class TestAssertConforms:
    @staticmethod
    def _order_model():
        needs("pydantic")
        from pydantic import BaseModel

        class Order(BaseModel):
            id: int
            total: float
            currency: str = "USD"

        return Order

    def test_valid_continues_over_validated_model(self):
        order_cls = self._order_model()
        result = assert_conforms({"id": 1, "total": 4.2}, order_cls)
        assert_that(result.val).is_instance_of(order_cls)

    def test_coerces_and_defaults(self):
        order_cls = self._order_model()
        validated = assert_conforms({"id": "7", "total": 4.2}, order_cls).value
        assert_that(validated.id).is_equal_to(7)
        assert_that(validated.currency).is_equal_to("USD")

    def test_capstone_value_chain(self):
        order_cls = self._order_model()
        order = assert_conforms({"id": 1, "total": 4.2}, order_cls).value
        assert_that(order.total).is_greater_than(0)

    def test_invalid_fails_with_validation_errors(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms({"id": "notint", "total": "x"}, order_cls)
        assert_that(str(exc_info.value)).contains("conform to <Order>").contains("int_parsing")
        assert_that(exc_info.value.actual).is_equal_to({"id": "notint", "total": "x"})
        assert_that(exc_info.value.expected).is_equal_to(order_cls)
        # pydantic's ValidationError text is already in the message, so it must not also head the traceback
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_invalid_item_fails_without_chaining_pydantic(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms([{"id": "notint", "total": "x"}], order_cls, each=True)
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_description_is_prepended_on_failure(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError, match=r"^\[order payload\]"):
            assert_conforms({"id": "notint"}, order_cls, "order payload")

    def test_non_pydantic_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="pydantic v2 model"):
            assert_conforms({}, dict)

    def test_non_type_arg_raises_typeerror(self):
        with pytest.raises(TypeError, match="pydantic v2 model"):
            assert_conforms({}, "not a type")

    def test_soft_collects_failure(self):
        order_cls = self._order_model()
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_conforms({"id": "bad", "total": "x"}, order_cls)


class TestAssertConformsExact:
    @staticmethod
    def _models():
        needs("pydantic")
        from datetime import datetime

        from pydantic import BaseModel

        class Customer(BaseModel):
            name: str

        class Item(BaseModel):
            sku: str

        class Order(BaseModel):
            id: int
            total: float
            created: datetime
            customer: Customer
            items: list[Item]

        return Order

    @staticmethod
    def _clean():
        return {
            "id": 1,
            "total": 5,
            "created": "2020-01-01T00:00:00",
            "customer": {"name": "Ann"},
            "items": [{"sku": "A"}, {"sku": "B"}],
        }

    def test_exact_clean_passes_without_coercion_noise(self):
        order_cls = self._models()
        assert_that(conforms_val := assert_conforms(self._clean(), order_cls, exact=True).value).is_not_none()
        assert_that(conforms_val.id).is_equal_to(1)

    def test_default_lenient_ignores_extra_fields(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        assert_that(assert_conforms(grew, order_cls).value).is_instance_of(order_cls)

    def test_exact_top_level_drift_fails(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(grew, order_cls, exact=True)
        assert_that(str(exc_info.value)).contains("conform exactly").contains("promo_code")
        assert_that(exc_info.value.actual).is_equal_to(grew)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_exact_nested_and_list_drift_paths(self):
        order_cls = self._models()
        payload = self._clean()
        payload["customer"] = {"name": "Ann", "vip": True}
        payload["items"] = [{"sku": "A"}, {"sku": "B", "gift_wrap": True}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payload, order_cls, exact=True)
        message = str(exc_info.value)
        assert_that(message).contains("customer.vip").contains("items[1].gift_wrap")

    def test_exact_alias_not_flagged(self):
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Aliased(BaseModel):
            user_id: int = Field(alias="userId")

        assert_that(assert_conforms({"userId": 1}, Aliased, exact=True).value.user_id).is_equal_to(1)

    def test_exact_respects_extra_allow_config(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict

        class Loose(BaseModel):
            model_config = ConfigDict(extra="allow")
            id: int

        assert_that(assert_conforms({"id": 1, "anything": 2}, Loose, exact=True).value.id).is_equal_to(1)

    def test_exact_soft_collects_drift(self):
        order_cls = self._models()
        grew = {**self._clean(), "promo_code": "X"}
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_conforms(grew, order_cls, exact=True)

    def test_validation_error_precedes_drift(self):
        order_cls = self._models()
        broken = {**self._clean(), "id": "notint", "surprise": 1}
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(broken, order_cls, exact=True)
        assert_that(str(exc_info.value)).contains("did not").does_not_contain("conform exactly")

    def test_each_validates_every_item_of_a_list_endpoint(self):
        order_cls = self._models()
        result = assert_conforms([self._clean(), self._clean()], order_cls, each=True)
        assert_that(result.val).is_length(2)
        assert_that(result.val[0]).is_instance_of(order_cls)

    def test_each_reports_the_failing_item_index(self):
        order_cls = self._models()
        payloads = [self._clean(), {**self._clean(), "id": "notint"}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payloads, order_cls, each=True)
        assert_that(str(exc_info.value)).contains("item [1]").contains("to conform")
        assert_that(exc_info.value.actual).is_equal_to(payloads)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_each_exact_drift_carries_the_element_index(self):
        order_cls = self._models()
        payloads = [self._clean(), {**self._clean(), "promo": "X"}]
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms(payloads, order_cls, each=True, exact=True)
        assert_that(str(exc_info.value)).contains("[1].promo")
        assert_that(exc_info.value.actual).is_equal_to(payloads)
        assert_that(exc_info.value.expected).is_equal_to(order_cls)

    def test_each_exact_clean_list_passes(self):
        order_cls = self._models()
        result = assert_conforms([self._clean(), self._clean()], order_cls, each=True, exact=True)
        assert_that(result.val).is_length(2)

    def test_each_accepts_a_tuple_and_an_empty_payload(self):
        order_cls = self._models()
        assert_that(assert_conforms((), order_cls, each=True).val).is_equal_to([])

    def test_each_requires_a_list_or_tuple_payload(self):
        order_cls = self._models()
        with pytest.raises(TypeError) as exc_info:
            assert_conforms(self._clean(), order_cls, each=True)
        assert_that(str(exc_info.value)).contains("list or tuple")

    def test_each_soft_collects_the_item_failure(self):
        order_cls = self._models()
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_conforms([{**self._clean(), "id": "x"}], order_cls, each=True)
        assert_that(str(exc_info.value)).contains("item [0]")


def _drift(payload, model):
    """What `assert_conforms(..., exact=True)` reports: the payload walked beside the instance it validated into."""
    return _paths(contract_drift(payload, model.model_validate(payload)))


def _paths(found):
    return [_placed(place)[0] for place, *_ in found]


def _is_text(value):
    return isinstance(value, (str, bytes, bytearray))


def _leads_back(whole, entry):
    """Whether the steps of *entry* reach, in the payload *whole*, the very object the entry holds."""
    reached = whole
    for step in entry.steps:
        if step.kind == "item":
            if not any(part is step.value for part in reached):
                return False
            reached = step.value
        elif step.kind == "json":
            # the step holds what the text it stands at decodes to
            if not _is_text(reached) or _contract._decoded_container(reached) != step.value:
                return False
            reached = step.value
        else:
            reached = reached[step.value]
    return reached is entry.actual


@pytest.fixture(autouse=True)
def _every_entry_leads_back_to_what_it_holds(monkeypatch):
    """Whatever an exact check of this module finds, the steps of each of its entries reach the value it holds."""
    exactness = _contract.exactness_failure

    def gated(pairs, *, carrier):
        pairs = list(pairs)
        found = exactness(pairs, carrier=carrier)
        if found is not None:
            whole = pairs[0][0] if pairs[0][2] is None else [payload for payload, _, _ in pairs]
            astray = [entry.path for entry in found[1] if not _leads_back(whole, entry)]
            assert_that(astray).described_as("entries whose steps do not reach what they hold").is_empty()
        return found

    monkeypatch.setattr("assertpy.assertpy.exactness_failure", gated)


class TestContractDrift:
    """Unit coverage of the drift walker's branches."""

    @staticmethod
    def _submodels():
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner = Field(alias="innerAlias")
            pair: tuple[Inner, ...]
            either: int | str
            note: str

        return Inner, Outer

    def test_a_payload_of_another_shape_is_refused_only_where_a_key_could_hide(self, monkeypatch):
        inner, _ = self._submodels()
        with pytest.raises(UncheckableDriftError, match="holds a list where a model was built"):
            contract_drift([{"x": 1}], inner(x=1))
        itself: list[object] = []
        itself.append(itself)
        for keyless in (42, None, [1, 2], itself, "not json", b"[1]", inner(x=1)):
            assert_that(contract_drift(keyless, inner(x=1))).described_as(repr(keyless)).is_empty()

        # how deep the decoder goes before RecursionError depends on the platform's stack
        def too_deep(text):
            raise RecursionError

        monkeypatch.setattr(_contract, "json", types.SimpleNamespace(loads=too_deep))
        with pytest.raises(UncheckableDriftError, match="holds a str where a model was built"):
            contract_drift("[[[", inner(x=1))

    def test_alias_resolved_tuple_and_union_branches(self):
        _, outer = self._submodels()
        payload = {
            "innerAlias": {"x": 1, "deep": 2},
            "pair": [{"x": 1}, {"x": 2, "oops": 9}],
            "either": "ok",
            "note": "n",
        }
        assert_that(sorted(_drift(payload, outer))).is_equal_to(["inner.deep", "pair[1].oops"])

    def test_null_submodel_value_is_skipped(self):
        inner_model, _ = self._submodels()
        from pydantic import BaseModel

        class Holder(BaseModel):
            inner: inner_model | None

        assert_that(_drift({"inner": None}, Holder)).is_empty()

    def test_validation_alias_str_not_flagged(self):
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias="userId")

        assert_that(_drift({"userId": 1}, Model)).is_empty()

    def test_alias_choices_not_flagged_but_genuine_drift_caught(self):
        needs("pydantic")
        from pydantic import AliasChoices, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasChoices("uid", "userId"))

        assert_that(_drift({"uid": 1}, Model)).is_empty()
        assert_that(_drift({"userId": 1}, Model)).is_empty()
        assert_that(_drift({"uid": 1, "surprise": 9}, Model)).is_equal_to(["surprise"])

    def test_alias_path_top_level_key_not_flagged(self):
        needs("pydantic")
        from pydantic import AliasPath, BaseModel, Field

        class Model(BaseModel):
            city: str = Field(validation_alias=AliasPath("address", "city"))

        assert_that(_drift({"address": {"city": "NYC"}}, Model)).is_empty()

    def test_submodel_resolved_via_validation_alias(self):
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            inner: Inner = Field(validation_alias="innerAlias")

        assert_that(_drift({"innerAlias": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["inner.extra"])

    def test_submodel_value_resolution_alias_loop_branches(self):
        needs("pydantic")
        from pydantic import AliasChoices, BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            plain: Inner | None = None
            aliased: Inner = Field(validation_alias=AliasChoices("first", "second"))

        assert_that(_drift({"second": {"x": 1, "deep": 9}}, Outer)).is_equal_to(["aliased.deep"])


class TestShape:
    def test_scalar_categories(self):
        assert_that(shape(None)).is_equal_to("null")
        assert_that(shape(True)).is_equal_to("bool")
        assert_that(shape(7)).is_equal_to("number")
        assert_that(shape(7.5)).is_equal_to("number")
        assert_that(shape("x")).is_equal_to("str")
        assert_that(shape(b"raw")).is_equal_to("bytes")

    def test_dict_and_empty_list(self):
        assert_that(shape({"id": 1, "name": "a"})).is_equal_to({"id": "number", "name": "str"})
        assert_that(shape([])).is_equal_to([])

    def test_list_merges_element_shapes(self):
        assert_that(shape([{"a": 1}, {"a": 2}])).is_equal_to([{"a": "number"}])
        assert_that(shape([{"a": 1}, {"b": 2}])).is_equal_to([{"a": "number", "b": "number"}])
        assert_that(shape([None, 1])).is_equal_to(["number"])
        assert_that(shape([1, None])).is_equal_to(["number"])
        assert_that(shape([1, "x"])).is_equal_to(["mixed"])
        assert_that(shape([[], [1]])).is_equal_to([["number"]])
        assert_that(shape([[1], []])).is_equal_to([["number"]])
        assert_that(shape([[1], ["x"]])).is_equal_to([["mixed"]])

    def test_nested_dict_elements_are_merged_key_by_key(self):
        # `[[1], ["x"]]` answers "mixed" either way; dict elements merge into a union rather than collapsing
        assert_that(shape([[{"a": 1}], [{"b": 2}]])).is_equal_to([[{"a": "number", "b": "number"}]])

    def test_a_self_referential_list_is_marked_not_followed(self):
        # the seen-set has to reach list elements too, or this recurses until the interpreter gives up
        cyclic = [1]
        cyclic.append(cyclic)
        assert_that(shape(cyclic)).is_equal_to(["mixed"])

    def test_a_self_referential_dict_keeps_the_marker(self):
        # a list merges the marker into "mixed", so a dict is the only place it reaches the stored shape
        cyclic = {"a": 1}
        cyclic["self"] = cyclic
        assert_that(shape(cyclic)).is_equal_to({"a": "number", "self": "<circular ref>"})


class TestShapeDiff:
    def test_no_drift_and_null_wildcard(self):
        assert_that(shape_diff({"a": "number"}, {"a": "number"})).is_empty()
        assert_that(shape_diff("null", "str")).is_empty()
        assert_that(shape_diff("str", "null")).is_empty()

    def test_added_removed_nested(self):
        old = {"id": "number", "user": {"name": "str"}}
        new = {"id": "number", "user": {"name": "str", "vip": "bool"}, "extra": "str"}
        assert_that(sorted(shape_diff(old, new))).is_equal_to([("added", "extra", ""), ("added", "user.vip", "")])
        assert_that(shape_diff(new, old)).contains(("removed", "extra", ""), ("removed", "user.vip", ""))

    def test_list_elementwise_and_empty(self):
        assert_that(shape_diff([{"a": "number"}], [{"a": "number", "b": "str"}])).is_equal_to([("added", "[*].b", "")])
        assert_that(shape_diff([], ["str"])).is_empty()
        assert_that(shape_diff(["str"], [])).is_empty()

    def test_retyped_names_objects_and_lists(self):
        assert_that(shape_diff("number", "str")).is_equal_to([("retyped", "", "number -> str")])
        assert_that(shape_diff({"a": "number"}, "str")).is_equal_to([("retyped", "", "object -> str")])
        assert_that(shape_diff("str", ["number"])).is_equal_to([("retyped", "", "str -> list")])


class TestContractFailuresCarryPaths:
    """A validation failure exposes the same structured channel every other comparison does."""

    @staticmethod
    def _models():
        needs("pydantic")
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str
            zip: str

        class User(BaseModel):
            id: int
            address: Address

        return User

    def test_paths_and_inputs_reach_the_diff(self):
        user_cls = self._models()
        with pytest.raises(AssertionError) as exc_info:
            assert_conforms({"id": "seven", "address": {"city": "Paris"}}, user_cls)
        diff = exc_info.value.diff
        assert_that(diff.kind).is_equal_to("match")
        assert_that([entry.path for entry in diff.entries]).contains("id", "address.zip")
        assert_that(next(entry for entry in diff.entries if entry.path == "id").actual).is_equal_to("seven")

    def test_each_names_the_element_that_failed(self):
        needs("pydantic")
        from pydantic import BaseModel

        class Item(BaseModel):
            sku: str
            qty: int

        with pytest.raises(AssertionError) as exc_info:
            assert_conforms([{"sku": "A", "qty": 2}, {"sku": "B", "qty": "two"}], Item, each=True)
        assert_that([entry.path for entry in exc_info.value.diff.entries]).is_equal_to(["[1].qty"])


class TestAliasResolution:
    """Every top-level key a field can arrive under.  `Field(alias=...)` fills `validation_alias` too,
    so a model built that way exercises both collectors at once and cannot tell them apart: breaking
    either one still leaves the other supplying the key.  These separate them, and cover the two alias
    objects nothing reached before."""

    def test_a_serialization_only_alias_is_not_declared(self):
        # `serialization_alias` renames a field on the way out, and pydantic will not accept it as input
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(serialization_alias="userId")

        assert_that(_drift({"user_id": 1}, Model)).is_empty()
        assert_that(_drift({"user_id": 1, "userId": 2}, Model)).is_equal_to(["userId"])

    def test_a_validation_only_alias_is_declared(self):
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias="incoming_id")

        assert_that(_drift({"incoming_id": 1}, Model)).is_empty()

    def test_every_choice_of_an_alias_choices_is_declared(self):
        needs("pydantic")
        from pydantic import AliasChoices, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasChoices("userId", "user-id", "uid"))

        for choice in ("userId", "user-id", "uid"):
            assert_that(_drift({choice: 1}, Model)).described_as(choice).is_empty()

    def test_an_alias_path_declares_the_key_it_consumes(self):
        needs("pydantic")
        from pydantic import AliasPath, BaseModel, Field

        class Model(BaseModel):
            user_id: int = Field(validation_alias=AliasPath("meta", "id"))

        assert_that(_drift({"meta": {"id": 1}}, Model)).is_empty()


class TestSubmodelAnnotations:
    def test_an_optional_submodel_is_still_walked(self):
        needs("pydantic")
        from pydantic import BaseModel

        class Inner(BaseModel):
            a: int

        class Outer(BaseModel):
            inner: Inner | None = None

        assert_that(_drift({"inner": {"a": 1, "extra": 2}}, Outer)).is_equal_to(["inner.extra"])


class TestDriftFollowsWhatPydanticBuilt:
    """The payload is walked beside the instance it validated into, so each nested model is checked where pydantic put
    one: the member of a union it chose, the element types of a tuple, the values of a dict, and the full path of an
    `AliasPath`.  Read off the annotation, a union or a dict of models was never entered and extras inside it passed,
    and an `AliasPath` was followed one segment only."""

    @staticmethod
    def _cases():
        needs("pydantic")
        from pydantic import AliasPath, BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator
        from typing_extensions import TypedDict

        class A(BaseModel):
            model_config = ConfigDict(frozen=True)
            kind: typing.Literal["a"] = "a"
            x: int

        class B(BaseModel):
            kind: typing.Literal["b"] = "b"
            y: int

        class Rows(RootModel[list[A]]):
            pass

        def holding(annotation, **extra):
            return type("Holder", (BaseModel,), {"__annotations__": {"f": annotation}, **extra})

        class Wrapped(BaseModel):
            sub: A = Field(validation_alias=AliasPath("wrap", "inner"))

        class Indexed(BaseModel):
            first: A = Field(validation_alias=AliasPath("items", 0))
            last: A = Field(validation_alias=AliasPath("items", -1))

        class EmptyAlias(BaseModel):
            sub: A = Field(validation_alias="")

        class IntKeyed(BaseModel):
            sub: A = Field(validation_alias=AliasPath("wrap", 0))

        class ByName(BaseModel):
            model_config = ConfigDict(populate_by_name=True)
            sub: A = Field(alias="theSub")

        class Extras(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, A]

        class Stamped(BaseModel):
            model_config = ConfigDict(extra="allow")
            x: int

            @model_validator(mode="after")
            def stamped(self):
                self.stamp = 1
                return self

        class AliasOnly(BaseModel):
            model_config = ConfigDict(populate_by_name=True, validate_by_alias=True, validate_by_name=False)
            sub: A = Field(default_factory=lambda: A(x=0), alias="theSub")

        class Shape(TypedDict):
            a: A
            b: int

        class Unreached(BaseModel):
            past: A | None = Field(None, validation_alias=AliasPath("items", 5))
            keyed: A | None = Field(None, validation_alias=AliasPath("items", "k"))

        class Frozen(BaseModel):
            f: dict[str, A]

            @field_validator("f")
            @classmethod
            def frozen(cls, value):
                return types.MappingProxyType(value)

        extra = {"x": 1, "extra": 2}
        discriminated = typing.Annotated[A | B, Field(discriminator="kind")]
        cases = {
            "union": (holding(A | B), {"f": extra}, ["f.extra"]),
            "union, the other member": (holding(A | B), {"f": {"y": 1, "extra": 2}}, ["f.extra"]),
            "dict of models": (holding(dict[str, A]), {"f": {"k": extra}}, ["f.k.extra"]),
            "dict with a coerced key": (holding(dict[int, A]), {"f": {"1": extra}}, ["f.1.extra"]),
            "list of a union": (holding(list[A | B]), {"f": [extra]}, ["f[0].extra"]),
            "tuple, clean": (holding(tuple[A, B]), {"f": [{"x": 1}, {"y": 2}]}, []),
            "tuple, extra in its second type": (
                holding(tuple[A, B]),
                {"f": [{"x": 1}, {"y": 2, "extra": 3}]},
                ["f[1].extra"],
            ),
            "discriminated union": (holding(discriminated), {"f": {"kind": "b", "y": 1, "extra": 2}}, ["f.extra"]),
            "dict of lists": (holding(dict[str, list[A]]), {"f": {"k": [extra]}}, ["f.k[0].extra"]),
            "root model": (Rows, [extra], ["[0].extra"]),
            "root model as a field": (holding(Rows), {"f": [extra]}, ["f[0].extra"]),
            "alias path, clean": (Wrapped, {"wrap": {"inner": {"x": 1}}}, []),
            "alias path, extra": (Wrapped, {"wrap": {"inner": extra}}, ["sub.extra"]),
            "alias path by index": (Indexed, {"items": [{"x": 1}, extra]}, ["last.extra"]),
            "a name allowed beside the alias": (ByName, {"sub": extra}, ["sub.extra"]),
            "list of lists": (holding(list[list[A]]), {"f": [[extra]]}, ["f[0][0].extra"]),
            "an empty alias": (EmptyAlias, {"": extra}, ["sub.extra"]),
            "alias path by dict key": (IntKeyed, {"wrap": {0: extra}}, ["sub.extra"]),
            "a typed dict it reorders": (holding(Shape), {"f": {"b": 1, "a": extra}}, ["f.a.extra"]),
            "a deque for a list": (holding(list[A]), {"f": collections.deque([extra])}, ["f[0].extra"]),
            "a dict's values for a list": (holding(list[A]), {"f": {"k": extra}.values()}, ["f[0].extra"]),
            "a mapping proxy for a model": (holding(A), {"f": types.MappingProxyType(extra)}, ["f.extra"]),
            "a mapping proxy for a dict": (
                holding(dict[str, A]),
                {"f": types.MappingProxyType({"k": extra})},
                ["f.k.extra"],
            ),
            "a mapping proxy as the payload": (holding(A), types.MappingProxyType({"f": extra}), ["f.extra"]),
            "alias path by index into a deque": (
                Indexed,
                {"items": collections.deque([{"x": 1}, extra])},
                ["last.extra"],
            ),
            "alias path through a bare getitem": (Indexed, {"items": _Indexed([{"x": 1}, extra])}, ["last.extra"]),
            "alias path by key through a bare getitem": (Wrapped, {"wrap": _Indexed({"inner": extra})}, ["sub.extra"]),
            "a name the config refuses over populate_by_name": (AliasOnly, {"sub": extra}, ["sub"]),
            "a sequence kept as a deque": (
                holding(collections.abc.Sequence[A]),
                {"f": collections.deque([extra])},
                ["f[0].extra"],
            ),
            "a dict a validator froze": (Frozen, {"f": {"k": extra}}, ["f.k.extra"]),
            "a declaration naming two lists": (
                holding(list[dict[str, A]] | list[int]),
                {"f": [{"k": extra}]},
                ["f[0].k.extra"],
            ),
            "alias paths reaching nothing": (Unreached, {"items": [extra]}, ["items"]),
            "alias paths into text": (Unreached, {"items": "text"}, ["items"]),
            "alias path through a bytes subclass": (Wrapped, {"wrap": _ByteItems(b"x")}, ["sub.extra"]),
            "a typed extra": (Extras, {"added": extra}, ["added.extra"]),
            "an extra a validator set": (Stamped, {"x": 1}, []),
        }
        try:
            EmptyAlias.model_validate({"": {"x": 1}})
        except ValueError:
            del cases["an empty alias"]  # an older pydantic takes an empty alias for no alias
        return cases

    def test_each_nested_model_is_checked_where_pydantic_put_it(self):
        found = {label: sorted(_drift(payload, model)) for label, (model, payload, _) in self._cases().items()}
        assert_that(found).is_equal_to({label: expected for label, (_, _, expected) in self._cases().items()})

    def test_a_name_the_config_does_not_read_is_named_and_not_followed(self):
        needs("pydantic")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            sub: Inner = Field(alias="theSub")

        # pydantic read `theSub` and dropped `sub`, so the key is named and what it holds is not the model built
        assert_that(_drift({"theSub": {"x": 1}, "sub": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["sub"])

    def test_a_key_that_spells_a_field_says_where_the_field_was_read(self):
        """A key the model knows and validation did not read is dropped like any other, and named with the reason: the
        key its field was read from in its place, or the keys validation reads it from where the payload sent none."""
        needs("pydantic")
        from pydantic import AliasChoices, AliasPath, BaseModel, Field

        class Named(BaseModel):
            user_id: int = Field(default=0, alias="userId")

        class Chosen(BaseModel):
            user_id: int = Field(default=0, validation_alias=AliasChoices("uid", "userId"))

        class Reached(BaseModel):
            user_id: int = Field(default=0, validation_alias=AliasPath("meta", "id"))
            first: int = Field(default=0, validation_alias=AliasPath("items", 0))

        class Dumped(BaseModel):
            user_id: int = Field(default=0, serialization_alias="userId")

        def said(payload, model):
            try:
                assert_conforms(payload, model, exact=True)
            except AssertionFailure as failure:
                return str(failure).split(", but it carries ")[1]
            return "passes"

        carries = "1 undeclared field(s) the model does not declare: "
        assert_that(
            {
                "both spellings": said({"userId": 1, "user_id": 2}, Named),
                "the name alone": said({"user_id": 2}, Named),
                "the later of two choices": said({"uid": 1, "userId": 2}, Chosen),
                "neither choice": said({"user_id": 2}, Chosen),
                "a path that leads nowhere": said({"meta": {"other": 1}}, Reached),
                "a position that is not there": said({"items": []}, Reached),
                "the alias a field is dumped under": said({"user_id": 1, "userId": 2}, Dumped),
                "a key that spells no field": said({"userId": 1, "more": 2}, Named),
                "paths that are followed": said({"meta": {"id": 1}, "items": [2]}, Reached),
            }
        ).is_equal_to(
            {
                "both spellings": f"{carries}['user_id']\n<user_id> is not read: its field was read from <userId>",
                "the name alone": (
                    f"{carries}['user_id']\n<user_id> is not read: validation reads its field from <userId>"
                ),
                "the later of two choices": f"{carries}['userId']\n<userId> is not read: its field was read from <uid>",
                "neither choice": (
                    f"{carries}['user_id']\n<user_id> is not read: validation reads its field from <uid> or <userId>"
                ),
                "a path that leads nowhere": (
                    f"{carries}['meta']\n<meta> is not read: validation reads its field from <meta.id>"
                ),
                "a position that is not there": (
                    f"{carries}['items']\n<items> is not read: validation reads its field from <items[0]>"
                ),
                "the alias a field is dumped under": (
                    f"{carries}['userId']\n<userId> is not read: its field was read from <user_id>"
                ),
                "a key that spells no field": f"{carries}['more']",
                "paths that are followed": "passes",
            }
        )

    def test_a_config_reading_names_only_is_followed_by_name(self):
        needs("pydantic")
        from pydantic import ConfigDict as _Config

        if "validate_by_name" not in _Config.__annotations__:
            pytest.skip(reason="validate_by_name arrived in pydantic 2.11")
        from pydantic import BaseModel, ConfigDict, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            model_config = ConfigDict(validate_by_alias=False, validate_by_name=True)
            sub: Inner | None = Field(alias="theSub")

        # pydantic read the `None` under the name and dropped the alias, whose model is not the one that was built
        assert_that(_drift({"sub": None, "theSub": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["theSub"])
        with pytest.raises(AssertionFailure) as dropped:
            assert_conforms({"sub": None, "theSub": {"x": 1}}, Outer, exact=True)
        assert_that(str(dropped.value)).ends_with("<theSub> is not read: its field was read from <sub>")

        class Incoming(BaseModel):
            model_config = ConfigDict(validate_by_alias=False, validate_by_name=True)
            user_id: int = Field(validation_alias="incoming_id")

        # an alias no dump shows either: it is known for a spelling of the field by being its validation alias
        with pytest.raises(AssertionFailure) as dropped:
            assert_conforms({"user_id": 1, "incoming_id": 2}, Incoming, exact=True)
        assert_that(str(dropped.value)).ends_with("<incoming_id> is not read: its field was read from <user_id>")
        assert_that(_drift({"sub": {"x": 1, "extra": 2}}, Outer)).is_equal_to(["sub.extra"])

    def test_the_assertion_reports_what_the_walk_finds(self):
        model, payload, _ = self._cases()["union"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms(payload, model, exact=True)
        assert_that(str(caught.value)).contains("['f.extra']")
        model, payload, _ = self._cases()["alias path, clean"]
        assert_that(assert_conforms(payload, model, exact=True).value.sub.x).is_equal_to(1)

    def test_a_model_is_read_once_and_the_reading_kept(self, monkeypatch):
        model, payload, expected = self._cases()["alias path, extra"]
        read = []
        original = _contract._field_sources
        monkeypatch.setattr(_contract, "_READS", {})
        monkeypatch.setattr(_contract, "_field_sources", lambda *args: read.append(args[0]) or original(*args))
        assert_that(_drift(payload, model)).is_equal_to(expected)
        first = list(read)
        assert_that(_drift(payload, model)).is_equal_to(expected)
        assert_that(read).is_equal_to(first).contains("sub")
        assert_that(_contract._READS).contains_key(model)

    def test_a_rebuilt_model_is_read_again(self):
        needs("pydantic")
        from pydantic import ConfigDict as _Config

        if "validate_by_name" not in _Config.__annotations__:
            pytest.skip(reason="validate_by_name arrived in pydantic 2.11")
        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            sub: Inner | None = Field(default=None, alias="theSub")

        payload = {"sub": {"x": 1, "extra": 2}}
        assert_that(_drift(payload, Outer)).is_equal_to(["sub"])
        Outer.model_config["validate_by_alias"] = False
        Outer.model_config["validate_by_name"] = True
        Outer.model_rebuild(force=True)
        assert_that(_drift(payload, Outer)).is_equal_to(["sub.extra"])

    def test_a_payload_holding_itself_is_walked_once(self):
        needs("pydantic")
        from pydantic import BaseModel

        class Loose(BaseModel):
            f: typing.Any

        looped: dict = {}
        looped["f"] = looped
        assert_that(assert_conforms(looped, Loose, exact=True).value.f).is_same_as(looped)

    def test_a_model_a_validator_made_hold_itself_is_walked_once(self):
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Selfish(BaseModel):
            f: typing.Optional["Selfish"] | typing.Any

            @model_validator(mode="after")
            def holding_itself(self):
                self.f = self
                return self

        looped: dict = {}
        looped["f"] = looped
        conformed = assert_conforms(looped, Selfish, exact=True).value
        assert_that(conformed.f).is_same_as(conformed)

    def test_a_full_record_of_models_still_answers_a_new_one(self, monkeypatch):
        model, payload, expected = self._cases()["union"]
        full = dict.fromkeys(range(256))
        monkeypatch.setattr(_contract, "_READS", full)
        assert_that(_drift(payload, model)).is_equal_to(expected)
        assert_that(full).is_length(256)

    def test_each_item_of_a_root_model_is_named_by_its_own_index(self):
        model, _, _ = self._cases()["root model"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms([[{"x": 1}], [{"x": 1, "extra": 2}]], model, each=True, exact=True)
        assert_that(str(caught.value)).contains("['[1][0].extra']")

    def test_each_item_is_walked_beside_its_own_instance(self):
        model, _, _ = self._cases()["union"]
        with pytest.raises(AssertionError) as caught:
            assert_conforms([{"f": {"x": 1}}, {"f": {"y": 1, "extra": 2}}], model, each=True, exact=True)
        assert_that(str(caught.value)).contains("['[1].f.extra']")


class _Indexed:
    """Indexed through `__getitem__` alone, as an `AliasPath` step may read it."""

    def __init__(self, items):
        self.items = items

    def __getitem__(self, index):
        return self.items[index]


class _ByteItems(bytes):
    """Bytes whose own `__getitem__` answers any step, which pydantic's alias reading asks."""

    def __getitem__(self, key):
        return {"x": 1, "extra": 2}


_T = typing.TypeVar("_T")


class _Rows:
    """Iterable, and neither a collection nor an iterator."""

    def __iter__(self):
        yield {"x": 1, "extra": 2}


class TestExactnessRefusesWhatItCannotPair:
    """Where no reading pairs a part of the payload with the model built from it, `exact=True` fails and says where,
    rather than pass it unread or read it against the wrong model."""

    @staticmethod
    def _models():
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Json, RootModel, field_validator, model_validator

        class A(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class B(BaseModel):
            model_config = ConfigDict(frozen=True)
            y: int

        def holding(annotation):
            return type("Holder", (BaseModel,), {"__annotations__": {"f": annotation}})

        class Filtered(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def without_nulls(cls, value):
                return [item for item in value if item is not None]

        class Wrapped(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def listed(cls, value):
                return value if isinstance(value, list) else [value]

        class Money(BaseModel):
            amount: int
            currency: str

            @model_validator(mode="before")
            @classmethod
            def spelled(cls, value):
                if isinstance(value, str):
                    amount, currency = value.split()
                    return {"amount": amount, "currency": currency}
                if isinstance(value, list):
                    return dict(zip(("amount", "currency"), value, strict=True))
                return value

        class WrappedSet(BaseModel):
            f: set[A]

            @field_validator("f", mode="before")
            @classmethod
            def listed(cls, value):
                return value if isinstance(value, list) else [value]

        class Wide(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int
            z: int

        class FilteredUnion(BaseModel):
            f: list[Wide | A]

            @field_validator("f", mode="before")
            @classmethod
            def without_nulls(cls, value):
                return [item for item in value if item is not None]

        class Entry(BaseModel):
            model_config = ConfigDict(frozen=True)
            id: int

            def __eq__(self, other):
                return isinstance(other, Entry) and self.id == other.id

            def __hash__(self):
                return hash(self.id)

        class Narrow(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class Broad(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int
            extra: int = 0

        class First(Entry):
            tag: typing.Literal[1]
            child: Narrow

        class Last(Entry):
            tag: int
            child: Broad

        class Envelope(BaseModel, typing.Generic[_T]):
            model_config = ConfigDict(frozen=True)
            event: _T

        class Batch(BaseModel):
            f: set[Envelope[First] | Envelope[Last]]

        class Entries(BaseModel):
            f: set[First | Last]

        class Dated(BaseModel):
            model_config = ConfigDict(frozen=True, strict=True)
            d: datetime.date

        class Expanded(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def expanded(cls, value):
                return value if isinstance(value, list) else [value, *value.get("more", [])]

        class Renamed(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def renamed(cls, value):
                return [{"x": item["X"]} for item in value if item]

        class Priced(BaseModel):
            f: list[Money]

            @field_validator("f", mode="before")
            @classmethod
            def without_blanks(cls, value):
                return [item for item in value if item]

        class Paired(BaseModel):
            f: dict[str, A]

            @field_validator("f", mode="before")
            @classmethod
            def from_pairs(cls, value):
                return dict(value) if isinstance(value, list) else value

        return {
            "A": A,
            "B": B,
            "holding": holding,
            "Filtered": Filtered,
            "Wrapped": Wrapped,
            "Json": Json,
            "Money": Money,
            "Priced": Priced,
            "Paired": Paired,
            "RootModel": RootModel,
            "Renamed": Renamed,
            "WrappedSet": WrappedSet,
            "FilteredUnion": FilteredUnion,
            "Dated": Dated,
            "Entries": Entries,
            "Batch": Batch,
            "Expanded": Expanded,
        }

    def _refusal(self, payload, model, **options):
        with pytest.raises(AssertionError) as caught:
            assert_conforms(payload, model, exact=True, **options)
        return str(caught.value).split(", but ", 1)[1]

    def test_each_part_it_cannot_pair_is_named_with_the_reason(self):
        models = self._models()
        a, b, holding, json_of = models["A"], models["B"], models["holding"], models["Json"]
        found = {
            "a set mixing model classes": self._refusal({"f": [{"x": 1}, {"y": 1}]}, holding(set[a | b])),
            "an item its class refuses alone": self._refusal({"f": [None, {"X": 1}]}, models["Renamed"]),
            "an object expanded into several": self._refusal(
                {"f": {"x": 1, "more": [{"x": 2, "extra": 3}]}}, models["Expanded"]
            ),
            "a set merging generic specializations": self._refusal(
                {
                    "f": [
                        {"event": {"id": 1, "tag": 2, "child": {"x": 1}}},
                        {"event": {"id": 1, "tag": 1, "child": {"x": 1, "extra": 2}}},
                    ]
                },
                models["Batch"],
            ),
            "a set merging classes through its own equality": self._refusal(
                {"f": [{"id": 1, "tag": 2, "child": {"x": 1}}, {"id": 1, "tag": 1, "child": {"x": 1, "extra": 2}}]},
                models["Entries"],
            ),
            "a filtered list of mixed classes": self._refusal(
                {"f": [None, {"x": 1}, {"x": 2, "z": 3}]}, models["FilteredUnion"]
            ),
            "merged keys of models": self._refusal({"f": {"01": {"x": 1}, "1": {"x": 2}}}, holding(dict[int, a])),
            "merged model keys with model values": self._refusal(
                {"f": {'{"x": 1, "extra": 2}': {"x": 1}, '{"x": 1}': {"x": 2}}}, holding(dict[json_of[a], a])
            ),
            "merged keys of lists": self._refusal(
                {"f": {"01": [{"x": 1}], "1": [{"x": 2, "extra": 3}]}}, holding(dict[int, list[a]])
            ),
            "a mapping from a list": self._refusal({"f": [["k", {"x": 1}]]}, models["Paired"]),
            "model keys merged": self._refusal({"f": {'{"x": 1}': 1, '{"x":1}': 2}}, holding(dict[json_of[a], int])),
            "a generator read up": self._refusal({"f": (item for item in [{"x": 1}])}, holding(list[a])),
            "an iterable that is no collection": self._refusal({"f": _Rows()}, holding(list[a])),
            "a lazy iterable": self._refusal({"f": [{"x": 1, "extra": 2}]}, holding(collections.abc.Iterable[a])),
            "merged keys of lazy iterables": self._refusal(
                {"f": {"01": [{"x": 1}], "1": [{"x": 2, "extra": 3}]}},
                holding(dict[int, collections.abc.Iterable[a]]),
            ),
        }
        cannot = "<f> cannot be checked: "
        merged = f"{cannot}validation changed its size, 2 keys became 1"
        unordered = f"{cannot}a set keeps no order to pair its items with the models they became"
        assert_that(found).is_equal_to(
            {
                "a set mixing model classes": unordered,
                "an item its class refuses alone": f"{cannot}validation changed its length, 2 items became 1",
                "an object expanded into several": f"{cannot}the payload holds a dict where a sequence was built",
                "a set merging classes through its own equality": unordered,
                "a set merging generic specializations": unordered,
                "a filtered list of mixed classes": f"{cannot}validation changed its length, 3 items became 2",
                "merged keys of models": merged,
                "merged model keys with model values": merged,
                "merged keys of lists": merged,
                "a mapping from a list": f"{cannot}the payload holds a list where a mapping was built",
                "model keys merged": merged,
                "a generator read up": f"{cannot}the payload holds a generator where a sequence was built",
                "an iterable that is no collection": f"{cannot}the payload holds a _Rows where a sequence was built",
                "a lazy iterable": f"{cannot}validation is lazy here and builds the models only as the value is read",
                "merged keys of lazy iterables": merged,
            }
        )

    def test_an_item_validated_again_runs_its_validators_once_more(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, model_validator

        runs = []

        class Tag(BaseModel):
            model_config = ConfigDict(frozen=True)
            name: str

            @model_validator(mode="before")
            @classmethod
            def counted(cls, value):
                runs.append(value["name"])
                return value

        class Tagged(BaseModel):
            tags: set[Tag]

        assert_conforms({"tags": [{"name": "a"}, {"name": "b"}]}, Tagged, exact=True)
        assert_that(runs).is_equal_to(["a", "b", "a", "b"])

    def test_a_filtered_list_is_checked_as_the_payload_sent_it(self):
        """An item the validator dropped is checked too: the contract is the payload's, not what was kept."""
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class Plain(BaseModel):
            x: int

        class Live(BaseModel):
            items: list[Plain]

            @field_validator("items", mode="before")
            @classmethod
            def without_deleted(cls, value):
                return [item for item in value if not item.get("deleted")]

        found = self._refusal({"items": [{"x": 1, "deleted": True}, {"x": 2}]}, Live)
        assert_that(found).is_equal_to(
            "it carries 1 undeclared field(s) the model does not declare: ['items[0].deleted']"
        )

    def test_a_container_validation_emptied_is_checked_by_the_classes_its_field_declares(self):
        """With no item left to tell what the dropped ones became, the raw items are validated again as the field's
        declared type and what that builds is read; where that cannot tell what they became (items pydantic will not
        build that type from, a choice the validators not run again could have steered), the check refuses, clean
        payloads too."""
        needs("pydantic")
        from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, Json, RootModel, field_validator
        from pydantic_core import core_schema
        from typing_extensions import TypeAliasType

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Loose(BaseModel):
            x: int
            z: int = 0

        class Stringly(BaseModel):
            x: str
            y: int

        class FrozenA(BaseModel, frozen=True):
            x: int

        class FrozenB(BaseModel, frozen=True):
            y: int

        def emptying(annotation, mode="before"):
            class Emptied(BaseModel):
                f: annotation

                @field_validator("f", mode=mode)
                @classmethod
                def emptied(cls, value):
                    return [] if mode == "before" else type(value)()

            return Emptied

        def inner_emptied(annotation):
            class InnerEmptied(BaseModel):
                f: annotation

                @field_validator("f", mode="before")
                @classmethod
                def empty_inner(cls, value):
                    return [[] for _ in value]

            return InnerEmptied

        class EmptiedValues(BaseModel):
            f: dict[str, typing.Annotated[list[A], BeforeValidator(lambda value: [])]]

        class Wider(A):
            y: int

        class Widened(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def widened(cls, value):
                return [Wider.model_validate(item) for item in value]

            @field_validator("f", mode="after")
            @classmethod
            def empty(cls, value):
                return []

        class Valued(BaseModel):
            __value__: typing.ClassVar[int] = 0
            x: int

        lookalike = type("TypeAliasType", (type(BaseModel),), {})

        class Metaclassed(BaseModel, metaclass=lookalike):
            x: int

        class Holder(BaseModel):
            x: int
            g: A | B

        class Loaded(BaseModel):
            x: int
            h: list[A] | list[int]

        class Pick(RootModel[A | B]):
            pass

        class Normalized(BaseModel):
            f: list[A | Stringly]

            @field_validator("f", mode="before")
            @classmethod
            def normalize(cls, value):
                return [dict(item, x=f"{item['x']}!") for item in value]

            @field_validator("f", mode="after")
            @classmethod
            def empty(cls, value):
                return []

        def strictly_emptied(kind):
            class StrictlyEmptied(BaseModel):
                model_config = ConfigDict(strict=True)
                f: kind[A]

                @field_validator("f", mode="before")
                @classmethod
                def as_kind(cls, value):
                    return kind(value)

                @field_validator("f", mode="after")
                @classmethod
                def empty(cls, value):
                    return kind()

            return StrictlyEmptied

        class Texted(BaseModel):
            g: str | Json[A]

        class ValuesOrList(BaseModel):
            f: dict[str, typing.Annotated[list[A], BeforeValidator(lambda value: [])]] | list[B]

        class OptionalEmptied(BaseModel):
            f: typing.Annotated[list[A], BeforeValidator(lambda value: [])] | None

        class Tags(frozenset):
            @classmethod
            def __get_pydantic_core_schema__(cls, source, handler):
                return core_schema.no_info_after_validator_function(
                    cls, core_schema.frozenset_schema(handler.generate_schema(FrozenA))
                )

        class Nested(BaseModel):
            f: list[list[A]]

            @field_validator("f", mode="before")
            @classmethod
            def empty_inner(cls, value):
                return [[] for _ in value]

        class Rows(RootModel[list[A]]):
            @field_validator("root", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        extra = {"x": 1, "extra": 2}
        found = {
            "a list": self._refusal({"f": [extra]}, emptying(list[A])),
            "a set": self._refusal({"f": [extra]}, emptying(set[A])),
            "an optional annotated list": self._refusal(
                {"f": [extra]}, emptying(typing.Annotated[list[A], "meta"] | None)
            ),
            "a tuple of any length": self._refusal({"f": [extra]}, emptying(tuple[A, ...])),
            "an object sent alone": self._refusal({"f": extra}, emptying(list[A])),
            "a root model": self._refusal([extra], Rows),
            "a list emptied inside a list": self._refusal({"f": [[extra]]}, Nested),
            "an item beside a None the list does not take": self._refusal({"f": [None, extra]}, emptying(list[A])),
            "a list emptied as a dict value": self._refusal({"f": {"k": [extra]}}, EmptiedValues),
            "a list of JSON text": self._refusal({"f": ['{"x": 1, "extra": 2}']}, emptying(list[Json[A]])),
            "an optional annotated list of lists": self._refusal(
                {"f": [[extra]]}, inner_emptied(typing.Annotated[list[list[A]], "meta"] | None)
            ),
            "a fixed tuple of lists": self._refusal(
                {"f": [[{"x": 1}], [{"y": 1, "extra": 2}]]}, inner_emptied(tuple[list[A], list[B]])
            ),
            "a fixed tuple with a number first": self._refusal(
                {"f": [1, extra]}, emptying(tuple[int, A], mode="after")
            ),
            "a list optional, emptied by its own validator": self._refusal({"f": [extra]}, OptionalEmptied),
            "a set of its own kind": self._refusal({"f": [{"x": 1}, extra]}, emptying(Tags, mode="after")),
            "a fixed tuple emptied after validation": self._refusal(
                {"f": [{"x": 1}, {"x": 2, "z": 3, "extra": 4}]}, emptying(tuple[A, Loose], mode="after")
            ),
            "a None dropped beside it": self._refusal({"f": [None, extra]}, emptying(list[A | None])),
            "a subclass the skipped validator built, against the declared class": self._refusal(
                {"f": [{"x": 1, "y": 2}]}, Widened
            ),
            "a choice with no key to hide inside the model": self._refusal(
                {"f": [{"x": 1, "h": [1], "extra": 2}]}, emptying(list[Loaded])
            ),
            "a model with a class attribute an alias also has": self._refusal({"f": [extra]}, emptying(list[Valued])),
            "a model whose metaclass has an alias's name": self._refusal({"f": [extra]}, emptying(list[Metaclassed])),
            "a strict tuple": self._refusal({"f": [extra]}, strictly_emptied(tuple)),
            "a strict deque": self._refusal({"f": [extra]}, strictly_emptied(collections.deque)),
        }
        carries = "it carries 1 undeclared field(s) the model does not declare: "
        assert_that(found).is_equal_to(
            {
                "a list": f"{carries}['f[0].extra']",
                "a set": f"{carries}['f[0].extra']",
                "an optional annotated list": f"{carries}['f[0].extra']",
                "a tuple of any length": f"{carries}['f[0].extra']",
                "an object sent alone": f"{carries}['f.extra']",
                "a root model": f"{carries}['[0].extra']",
                "a list emptied inside a list": f"{carries}['f[0][0].extra']",
                "an item beside a None the list does not take": f"{carries}['f[1].extra']",
                "a list emptied as a dict value": f"{carries}['f.k[0].extra']",
                "a list of JSON text": f"{carries}['f[0].extra']",
                "an optional annotated list of lists": f"{carries}['f[0][0].extra']",
                "a fixed tuple of lists": f"{carries}['f[1][0].extra']",
                "a fixed tuple with a number first": f"{carries}['f[1].extra']",
                "a list optional, emptied by its own validator": f"{carries}['f[0].extra']",
                "a set of its own kind": f"{carries}['f[1].extra']",
                "a fixed tuple emptied after validation": f"{carries}['f[1].extra']",
                "a None dropped beside it": f"{carries}['f[1].extra']",
                "a subclass the skipped validator built, against the declared class": f"{carries}['f[0].y']",
                "a choice with no key to hide inside the model": f"{carries}['f[0].extra']",
                "a model with a class attribute an alias also has": f"{carries}['f[0].extra']",
                "a model whose metaclass has an alias's name": f"{carries}['f[0].extra']",
                "a strict tuple": f"{carries}['f[0].extra']",
                "a strict deque": f"{carries}['f[0].extra']",
            }
        )
        if "coerce_numbers_to_str" in ConfigDict.__annotations__:

            class Coerced(BaseModel):
                model_config = ConfigDict(coerce_numbers_to_str=True)
                f: tuple[str, A]

                @field_validator("f", mode="after")
                @classmethod
                def emptied(cls, value):
                    return ()

            assert_that(self._refusal({"f": [1, extra]}, Coerced)).is_equal_to(f"{carries}['f[1].extra']")
        emptied = "cannot be checked: validation changed its length, 1 items became 0"
        steered = "cannot be checked: which of its declared types it became depends on validators not run again"
        refused = [
            (emptying(list[A | B]), {"f": [{"y": 1, "extra": 2}]}, f"<f> {emptied}"),
            (emptying(list[A | dict[str, int]]), {"f": [{"k": 1}]}, f"<f> {emptied}"),
            (emptying(list[A | Loose]), {"f": [{"x": 1}]}, f"<f> {emptied}"),
            (emptying(list[A] | tuple[A, ...]), {"f": [extra]}, f"<f> {emptied}"),
            (emptying(list[A] | tuple[B, ...], mode="after"), {"f": [{"y": 1}]}, f"<f> {emptied}"),
            (
                emptying(tuple[int, A] | list[dict[str, int]], mode="after"),
                {"f": [0, {"x": 1}]},
                "<f> cannot be checked: validation changed its length, 2 items became 0",
            ),
            (emptying(set[FrozenA] | list[B], mode="after"), {"f": [{"y": 1, "extra": 2}]}, f"<f> {emptied}"),
            (
                emptying(set[FrozenA] | set[FrozenB], mode="after"),
                {"f": [extra]},
                "<f> cannot be checked: a set keeps no order to pair its items with the models they became",
            ),
            (emptying(list[A] | list[B], mode="after"), {"f": [extra]}, f"<f> {emptied}"),
            (inner_emptied(list[list[A]] | tuple[list[A], ...]), {"f": [[extra]]}, f"<f[0]> {emptied}"),
            (ValuesOrList, {"f": {"k": [extra]}}, f"<f.k> {emptied}"),
            (Normalized, {"f": [{"x": 1, "y": 2}]}, f"<f> {emptied}"),
            (emptying(list[A | int]), {"f": [{"x": "bad", "extra": 2}]}, f"<f> {emptied}"),
            (emptying(list[A]), {"f": [{"X": 1}]}, f"<f> {emptied}"),
            (emptying(tuple[A, ...]), {"f": [{"X": 1}]}, f"<f> {emptied}"),
            (emptying(list[A | None]), {"f": [{"X": 1}]}, f"<f> {emptied}"),
            (emptying(list[Texted]), {"f": [{"g": '{"x": 1, "extra": 2}'}]}, f"<f[0].g> {steered}"),
            (
                emptying(list[Holder]),
                {"f": [{"x": 1, "g": {"y": 1, "extra": 2}, "top": 3}]},
                f"<f[0].g> {steered}",
            ),
            (emptying(list[Pick]), {"f": [{"y": 1}]}, f"<f[0]> {steered}"),
        ]
        rows = TypeAliasType("Rows", typing.Annotated[list[A], BeforeValidator(lambda value: [])])
        choice = TypeAliasType("Choice", A | Stringly)
        item = typing.TypeVar("item")
        listing = TypeAliasType("Listing", list[item], type_params=(item,))
        try:
            aliased, chosen, listed = emptying(rows, mode="after"), emptying(list[choice]), emptying(listing[A])
        # pydantic before 2.5 builds no schema for a named alias
        except TypeError:
            aliased = chosen = listed = None
        if aliased is not None:
            refused += [
                (aliased, {"f": [{"x": 1}]}, f"<f> {emptied}"),
                (chosen, {"f": [extra]}, f"<f> {emptied}"),
                (listed, {"f": [{"x": 1}]}, f"<f> {emptied}"),
            ]
        if "union_mode" in inspect.signature(Field).parameters:
            first = typing.Annotated[dict[str, int] | A, Field(union_mode="left_to_right")]
            refused.append((emptying(list[first], mode="after"), {"f": [extra]}, f"<f> {emptied}"))
        assert_that([self._refusal(payload, model) for model, payload, _ in refused]).is_equal_to(
            [expected for _, _, expected in refused]
        )
        clean = [
            (emptying(list[A]), {"f": [{"x": 1}]}),
            (emptying(typing.Any), {"f": [extra]}),
            (emptying(tuple[A, Loose], mode="after"), {"f": [{"x": 1}, {"x": 2, "z": 3}]}),
            (OptionalEmptied, {"f": [{"x": 1}]}),
            (emptying(Tags, mode="after"), {"f": [{"x": 1}, {"x": 2}]}),
            (emptying(list[Loaded]), {"f": [{"x": 1, "h": [1]}]}),
            (emptying(list[A]), {"f": [None, {"x": 1}]}),
            (strictly_emptied(tuple), {"f": [{"x": 1}]}),
            (emptying(list[Texted]), {"f": [{"g": "plain"}]}),
        ]
        for model, payload in clean:
            assert_conforms(payload, model, exact=True)

    def test_a_recursive_model_emptied_at_every_level_is_checked_at_every_level(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class Node(BaseModel):
            children: list["Node"] = []

            @field_validator("children", mode="before")
            @classmethod
            def pruned(cls, value):
                return []

        found = self._refusal({"children": [{"children": [{"junk": 1}]}]}, Node)
        # pydantic 2.0 keeps the self-reference as text in the field's annotation, which no replay can resolve
        unresolved = isinstance(typing.get_args(Node.model_fields["children"].annotation)[0], str)
        assert_that(found).is_equal_to(
            "<children> cannot be checked: validation changed its length, 1 items became 0"
            if unresolved
            else "it carries 1 undeclared field(s) the model does not declare: ['children[0].children[0].junk']"
        )

    def test_items_dropped_beside_plain_survivors_are_refused(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, field_validator

        class A(BaseModel):
            x: int

        class Duck:
            model_fields: typing.ClassVar[dict] = {}

        class Kept(BaseModel):
            f: list[A | dict[str, int]]

            @field_validator("f", mode="before")
            @classmethod
            def without_x(cls, value):
                return [item for item in value if "x" not in item]

        class Ducks(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            f: list[Duck]

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        class DuckSurvivors(BaseModel):
            model_config = ConfigDict(arbitrary_types_allowed=True)
            f: list[Duck]

            @field_validator("f", mode="before")
            @classmethod
            def ducked(cls, value):
                return [Duck() for item in value if item]

        refused = [
            self._refusal({"f": [{"x": 1}, {"k": 1}]}, Kept),
            self._refusal({"f": [{"a": 1}]}, Ducks),
            self._refusal({"f": [{"a": 1}, None]}, DuckSurvivors),
        ]
        resized = "<f> cannot be checked: validation changed its length"
        assert_that(refused).is_equal_to(
            [f"{resized}, 2 items became 1", f"{resized}, 1 items became 0", f"{resized}, 2 items became 1"]
        )

    def test_an_emptied_container_is_answered_when_the_records_are_full_and_refused_without_pydantic(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Emptied(BaseModel):
            f: list[A]
            g: dict[str, A] = {}

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        declared, adapters = dict.fromkeys(range(1024)), dict.fromkeys(range(256))
        monkeypatch.setattr(_contract, "_DECLARED", declared)
        monkeypatch.setattr(_contract, "_ADAPTERS", adapters)
        found = self._refusal({"f": [{"x": 1, "extra": 2}], "g": {"k": {"x": 1}}}, Emptied)
        assert_that(found).is_equal_to("it carries 1 undeclared field(s) the model does not declare: ['f[0].extra']")
        assert_that((0 in declared, 0 in adapters, len(declared) in range(1, 1024), len(adapters))).is_equal_to(
            (False, False, True, 1)
        )

        def refusing(annotation, config=None):
            raise TypeError(annotation)

        emptied = "<f> cannot be checked: validation changed its length, 1 items became 0"
        adapters.clear()
        stub = types.SimpleNamespace(TypeAdapter=refusing, ValidationError=sys.modules["pydantic"].ValidationError)
        monkeypatch.setitem(sys.modules, "pydantic", stub)
        assert_that(self._refusal({"f": [{"x": 1}]}, Emptied)).is_equal_to(emptied)
        adapters.clear()
        monkeypatch.setitem(sys.modules, "pydantic", None)
        assert_that(self._refusal({"f": [{"x": 1}]}, Emptied)).is_equal_to(emptied)

    @staticmethod
    def _emptying(item):
        """A model whose list of *item* its validator empties before validating it."""
        from pydantic import BaseModel, field_validator

        class Emptied(BaseModel):
            f: list[item]

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        return Emptied

    def test_typed_extras_are_checked_as_their_annotation_declares(self):
        """A list emptied inside a typed `__pydantic_extra__` is replayed as its annotation declares, read as written
        whatever other annotations the model holds.  Under a replay, an extra built through a choice refuses."""
        needs("pydantic")
        from pydantic import AfterValidator, BaseModel, ConfigDict

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        emptied = typing.Annotated[list[A], AfterValidator(lambda items: [])]

        class Open(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, emptied]

        class Peered(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, emptied]
            peer: "A | None" = None

        class OpenToOne(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, A]

        class OpenToEither(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, A | B]

        class OpenToAnything(BaseModel):
            model_config = ConfigDict(extra="allow")

        if Open.model_validate({"f": [{"x": 1}]}).__pydantic_extra__ != {"f": []}:
            pytest.skip("this pydantic keeps extras as sent, whatever `__pydantic_extra__` declares")
        for model, payload in [
            (Open, {"f": [{"x": 1}]}),
            (Peered, {"f": [{"x": 1}]}),
            (self._emptying(OpenToAnything), {"f": [{"k": {"z": 1}}]}),
        ]:
            assert_conforms(payload, model, exact=True)
        found = [
            self._refusal({"f": [{"x": 1, "extra": 2}]}, Open),
            self._refusal({"f": [{"x": 1, "extra": 2}]}, Peered),
            self._refusal({"f": [{"k": {"x": 1, "extra": 2}}]}, self._emptying(OpenToOne)),
            self._refusal({"f": [{"k": {"y": 1}}]}, self._emptying(OpenToEither)),
        ]
        assert_that(found).is_equal_to(
            [
                "it carries 1 undeclared field(s) the model does not declare: ['f[0].extra']",
                "it carries 1 undeclared field(s) the model does not declare: ['f[0].extra']",
                "it carries 1 undeclared field(s) the model does not declare: ['f[0].k.extra']",
                "<f[0].k> cannot be checked: which of its declared types it became depends on validators not run again",
            ]
        )

    def test_typed_extras_that_cannot_be_read_refuse(self, monkeypatch):
        """Text is not read back: pydantic read it in the frame that defined the model, where a name can mean another
        type than in its module.  A list emptied there refuses, and under a replay an extra built through it refuses
        too; so does one whose annotations raise when read, as from 3.14 a name defined only later does."""
        needs("pydantic")
        from pydantic import AfterValidator, BaseModel, ConfigDict, PydanticSchemaGenerationError

        class A(BaseModel):
            x: int

        emptied = typing.Annotated[list[A], AfterValidator(lambda items: [])]
        try:

            class WrittenLocally(BaseModel):
                model_config = ConfigDict(extra="allow")
                __pydantic_extra__: "dict[str, emptied]"

        except PydanticSchemaGenerationError:
            pytest.skip("this pydantic takes `__pydantic_extra__` only as a type, not as text")

        class OpenUnread(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: "dict[str, A]"

        class Unreadable(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, emptied]

        found = [
            self._refusal({"f": [{"x": 1}]}, WrittenLocally),
            self._refusal({"f": [{"k": {"x": 1}}]}, self._emptying(OpenUnread)),
        ]

        def unreadable(owner):
            raise NameError("Later")

        monkeypatch.setattr(inspect, "get_annotations", unreadable)
        found.append(self._refusal({"f": [{"x": 1}]}, Unreadable))
        assert_that(found).is_equal_to(
            [
                "<f> cannot be checked: validation changed its length, 1 items became 0",
                "<f[0].k> cannot be checked: which of its declared types it became depends on validators not run again",
                "<f> cannot be checked: validation changed its length, 1 items became 0",
            ]
        )

    def test_a_declaration_is_worked_out_once_whatever_ran_before(self, monkeypatch):
        """The caches are bounded, and a long run fills them before this one: each is emptied here, so a second ask
        is answered by what the first one worked out."""
        needs("pydantic")
        from pydantic import BaseModel

        class A(BaseModel):
            x: int

        monkeypatch.setattr(_contract, "_DECLARED", {})
        monkeypatch.setattr(_contract, "_ADAPTERS", {})
        mapping, sequence = (dict[str, list[A]], A, None), (set[A], A, None)
        target = _contract._replay_target(sequence)
        asks = [
            lambda: _contract._declared_mapping(mapping),
            lambda: _contract._declared_container(sequence),
            lambda: _contract._replay_target(sequence),
            lambda: _contract._adapter(target),
            lambda: _contract._listed(mapping),
        ]
        first = [ask() for ask in asks]
        assert_that([ask() is answer for ask, answer in zip(asks, first, strict=True)]).is_equal_to([True] * 5)

    def test_a_replay_that_builds_no_matching_sequence_refuses(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Emptied(BaseModel):
            f: list[A]

            @field_validator("f", mode="before")
            @classmethod
            def emptied(cls, value):
                return []

        monkeypatch.setattr(
            _contract, "_adapter", lambda declared: types.SimpleNamespace(validate_python=lambda items: 42)
        )
        refused = self._refusal({"f": [{"x": 1}]}, Emptied)
        assert_that(refused).is_equal_to("<f> cannot be checked: validation changed its length, 1 items became 0")

    def test_items_of_one_model_class_are_validated_again_and_json_text_is_read(self):
        """Clean, each shape passes; with an undeclared field, the field is named where the raw item held it."""
        models = self._models()
        a, holding, json_of, dated = models["A"], models["holding"], models["Json"], models["Dated"]
        cases = {
            "a set of models": (holding(set[a]), [{"x": 1}], [{"x": 1}, {"x": 1, "extra": 2}], "f[1].extra"),
            "a strict model read from JSON in a set": (
                holding(set[json_of[dated]]),
                ['{"d": "2026-09-30"}'],
                ['{"d": "2026-09-30", "extra": 2}'],
                "f[0].extra",
            ),
            "a filtered list": (models["Filtered"], [None, {"x": 1}], [None, {"x": 1, "extra": 2}], "f[1].extra"),
            "an object wrapped into a list": (models["Wrapped"], {"x": 1}, {"x": 1, "extra": 2}, "f.extra"),
            "an object wrapped into a set": (models["WrappedSet"], {"x": 1}, {"x": 1, "extra": 2}, "f.extra"),
            "a model read from text": (holding(json_of[a]), '{"x": 1}', '{"x": 1, "extra": 2}', "f.extra"),
            "models read from bytes": (
                holding(json_of[list[a]]),
                b'[{"x": 1}]',
                b'[{"x": 1, "extra": 2}]',
                "f[0].extra",
            ),
            "JSON text in a set": (holding(set[json_of[a]]), ['{"x": 1}'], ['{"x": 1, "extra": 2}'], "f[0].extra"),
            "a model built from a key": (
                holding(dict[json_of[a], int]),
                {'{"x": 1}': 1},
                {'{"x": 1, "extra": 2}': 1},
                "f.extra",
            ),
            "a model read from JSON twice": (
                holding(json_of[models["RootModel"][json_of[a]]]),
                '"{\\"x\\": 1}"',
                '"{\\"x\\": 1, \\"extra\\": 2}"',
                "f.extra",
            ),
        }
        for model, good, _, _ in cases.values():
            assert_conforms({"f": good}, model, exact=True)
        found = {name: self._refusal({"f": bad}, model) for name, (model, _, bad, _) in cases.items()}
        assert_that(found).is_equal_to(
            {
                name: f"it carries 1 undeclared field(s) the model does not declare: ['{where}']"
                for name, (_, _, _, where) in cases.items()
            }
        )

    def test_each_item_names_its_own_refusal(self):
        models = self._models()
        refusal = self._refusal([{"f": []}, {"f": [None, {"X": 1}]}], models["Renamed"], each=True)
        assert_that(refusal).is_equal_to("<[1].f> cannot be checked: validation changed its length, 2 items became 1")

    def test_what_holds_no_model_is_not_refused(self):
        models = self._models()
        a, holding = models["A"], models["holding"]
        merged = assert_conforms({"f": {"01": 1, "1": 2}}, holding(dict[int, a | int]), exact=True)
        assert_that(merged.value.f).is_length(1)
        assert_that(assert_conforms({"f": [1, 1, 2]}, holding(set[a | int]), exact=True).value.f).is_length(2)
        assert_that(assert_conforms({"f": [1, 2]}, holding(list[a | float]), exact=True).value.f).is_equal_to(
            [1.0, 2.0]
        )
        assert_that(assert_conforms({"f": "a,b"}, holding(str), exact=True).value.f).is_equal_to("a,b")

    def test_a_model_built_from_what_holds_no_key_is_not_refused(self):
        models = self._models()
        holding = models["holding"]
        for spelled in ("10 USD", [10, "USD"]):
            conformed = assert_conforms({"f": spelled}, holding(models["Money"]), exact=True)
            assert_that(conformed.value.f.amount).is_equal_to(10)
        filtered = assert_conforms({"f": ["1 A", "", "2 B"]}, models["Priced"], exact=True)
        assert_that(filtered.value.f).is_length(2)

    def test_a_model_given_instead_of_its_data_has_nothing_to_refuse(self):
        models = self._models()
        a = models["A"]
        assert_that(assert_conforms({"f": a(x=1)}, models["holding"](a), exact=True).value.f.x).is_equal_to(1)
        assert_that(assert_conforms({"f": a(x=1)}, models["Wrapped"], exact=True).value.f).is_length(1)
        assert_that(assert_conforms({"f": a(x=1)}, models["WrappedSet"], exact=True).value.f).is_length(1)
        assert_that(assert_conforms({"f": [["k", a(x=1)]]}, models["Paired"], exact=True).value.f).contains_key("k")
        lazy = assert_conforms({"f": [a(x=1)]}, models["holding"](collections.abc.Iterable[a]), exact=True)
        assert_that(list(lazy.value.f)).is_length(1)

    def test_a_validator_reordering_at_equal_length_is_read_by_position(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Reversed(BaseModel):
            f: list[A | B]

            @field_validator("f", mode="before")
            @classmethod
            def backwards(cls, value):
                return list(reversed(value))

        found = self._refusal({"f": [{"x": 1}, {"y": 2}]}, Reversed)
        assert_that(found).is_equal_to(
            "it carries 2 undeclared field(s) the model does not declare: ['f[0].x', 'f[1].y']"
        )

    def test_a_nesting_deeper_than_the_walk_follows_is_refused(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Rewrapped(BaseModel):
            f: A | list[typing.Any]

            @field_validator("f", mode="before")
            @classmethod
            def rewrapped(cls, value):
                depth = 0
                while isinstance(value, list):
                    depth, value = depth + 1, value[0]
                for _ in range(depth):
                    value = [value]
                return value

        deep: object = 0
        for _ in range(5_000):
            deep = [deep]
        found = self._refusal({"f": deep}, Rewrapped)
        assert_that(found).is_equal_to("<the payload> cannot be checked: it nests deeper than the walk can follow")


class TestExactnessReadsThePayloadAsItWasSent:
    """A validator that changed the payload in place hid what it removed, since the walk read what validation left.
    The plain dicts and lists of the payload are put back as they were sent for the check, and returned to what
    validation left once it is over."""

    @staticmethod
    def _failure(payload, model, **options):
        with pytest.raises(AssertionFailure) as caught:
            assert_conforms(payload, model, exact=True, **options)
        return str(caught.value)

    @staticmethod
    def _stripping():
        from pydantic import BaseModel, model_validator

        class Stripping(BaseModel):
            x: int

            @model_validator(mode="before")
            @classmethod
            def strip(cls, data):
                data.pop("extra", None)
                return data

        return Stripping

    def test_a_key_removed_in_place_is_named_and_the_payload_is_left_as_validation_left_it(self):
        needs("pydantic")
        stripping = self._stripping()
        payload = {"x": 1, "extra": 2}
        assert_that(self._failure(payload, stripping)).is_equal_to(
            "Expected <{'x': 1, 'extra': 2}> to conform exactly to <Stripping>, "
            "but it carries 1 undeclared field(s) the model does not declare: ['extra']"
        )
        assert_that(payload).is_equal_to({"x": 1})
        assert_conforms({"x": 1}, stripping, exact=True)

    @pytest.mark.parametrize("stamp", [{}, {"at": datetime.date(2026, 10, 1)}], ids=["copied whole", "by container"])
    def test_items_changed_and_dropped_in_place_are_read_as_sent(self, stamp):
        """Plain data is kept as one copy; a payload holding a date cannot be, and is kept container by container."""
        needs("pydantic")
        from pydantic import BaseModel, field_validator, model_validator

        class Row(BaseModel):
            x: int

        class Rows(BaseModel):
            rows: list[Row]
            at: datetime.date | None = None

            @field_validator("rows", mode="before")
            @classmethod
            def trimmed(cls, value):
                for row in value:
                    row.pop("extra", None)
                del value[1:]
                return value

        class Renaming(BaseModel):
            x: int
            at: datetime.date | None = None

            @model_validator(mode="before")
            @classmethod
            def renamed(cls, data):
                data["x"] = data.pop("old")
                return data

        class Paired(BaseModel):
            pair: tuple[Row, ...]
            at: datetime.date | None = None

            @model_validator(mode="before")
            @classmethod
            def strip(cls, data):
                for row in data["pair"]:
                    row.pop("extra", None)
                return data

        class Replacing(BaseModel):
            rows: list[Row]
            at: datetime.date | None = None

            @model_validator(mode="before")
            @classmethod
            def positive(cls, data):
                data["rows"] = [row for row in data["rows"] if row["x"] > 0]
                return data

        payloads = [
            {"rows": [{"x": 1, "extra": 2}, {"x": 2, "more": 3}], **stamp},
            {"old": 1, **stamp},
            {"pair": ({"x": 1, "extra": 2},), **stamp},
            {"rows": [{"x": 1}, {"x": -1, "extra": 2}], **stamp},
        ]
        carries = "undeclared field(s) the model does not declare: "
        found = [
            self._failure(payload, model).split("it carries ")[1]
            for payload, model in zip(payloads, (Rows, Renaming, Paired, Replacing), strict=True)
        ]
        assert_that(found).is_equal_to(
            [
                f"2 {carries}['rows[0].extra', 'rows[1].more']",
                f"1 {carries}['old']",
                f"1 {carries}['pair[0].extra']",
                f"1 {carries}['rows[1].extra']",
            ]
        )
        left = [{"rows": [{"x": 1}]}, {"x": 1}, {"pair": ({"x": 1},)}, {"rows": [{"x": 1}]}]
        assert_that(payloads).is_equal_to([{**payload, **stamp} for payload in left])

    @pytest.mark.parametrize("stamp", [{}, {"at": datetime.date(2026, 10, 1)}], ids=["copied whole", "by container"])
    def test_a_tuple_of_items_is_put_back_item_by_item(self, stamp):
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Stamped(BaseModel):
            x: int
            at: datetime.date | None = None

            @model_validator(mode="before")
            @classmethod
            def strip(cls, data):
                data.pop("extra", None)
                return data

        payload = ({"x": 1, "extra": 2, **stamp}, {"x": 2, **stamp})
        assert_that(self._failure(payload, Stamped, each=True)).ends_with("['[0].extra']")
        assert_that(payload).is_equal_to(({"x": 1, **stamp}, {"x": 2, **stamp}))
        mixed = (1, {"x": 1, "extra": 2, **stamp})
        sent = _contract.sent_record(mixed)
        mixed[1].pop("extra")
        left = _contract.put_as_sent(mixed, sent)
        assert_that(mixed).is_equal_to((1, {"x": 1, "extra": 2, **stamp}))
        _contract.put_back(left)
        assert_that(mixed).is_equal_to((1, {"x": 1, **stamp}))

    def test_what_a_validator_run_again_changes_is_put_back_before_the_walk(self):
        """The item class strips its input in place, and runs again on the payload itself: what it strips is put
        back before the walk reads it."""
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        stripping = self._stripping()

        class Kept(BaseModel):
            items: list[stripping]

            @field_validator("items")
            @classmethod
            def first(cls, value):
                return value[:1]

        class Emptied(BaseModel):
            items: list[stripping]

            @field_validator("items", mode="before")
            @classmethod
            def none(cls, value):
                return []

        for model, left in ((Kept, [{"x": 1}, {"x": 2}]), (Emptied, [{"x": 1, "extra": 2}, {"x": 2, "extra": 3}])):
            payload = {"items": [{"x": 1, "extra": 2}, {"x": 2, "extra": 3}]}
            assert_that(self._failure(payload, model)).ends_with("['items[0].extra', 'items[1].extra']")
            assert_that(payload).is_equal_to({"items": left})

    def test_each_item_is_kept_before_the_first_one_is_validated(self):
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        later = {"x": 2, "extra": 3}

        class Reaching(BaseModel):
            x: int

            @model_validator(mode="before")
            @classmethod
            def reach(cls, data):
                later.pop("extra", None)
                return data

        assert_that(self._failure([{"x": 1}, later], Reaching, each=True)).is_equal_to(
            "Expected every item to conform exactly to <Reaching>, "
            "but 1 undeclared field(s) the model does not declare: ['[1].extra']"
        )
        assert_that(later).is_equal_to({"x": 2})

    def test_a_retained_object_changed_in_place_and_a_payload_that_holds_itself(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator, model_validator

        class Keeping(BaseModel):
            data: typing.Any

            @field_validator("data")
            @classmethod
            def trim(cls, value):
                value.pop("b", None)
                return value

        payload = {"data": {"a": 1, "b": 2}}
        payload["data"]["self"] = payload
        validated = assert_conforms(payload, Keeping, exact=True).value
        assert_that((validated.data is payload["data"], sorted(payload["data"]))).is_equal_to((True, ["a", "self"]))

        class Looped(BaseModel):
            x: int
            back: typing.Any = None

            @model_validator(mode="before")
            @classmethod
            def renamed(cls, data):
                data["x"] = data.pop("old")
                return data

        # as many keys as were sent, and the one that leads back comes first: `==` on the two does not end
        looped = {"old": 1}
        looped["back"] = looped
        assert_that(self._failure(looped, Looped)).ends_with("['old']")
        assert_that(sorted(looped)).is_equal_to(["back", "x"])

    def test_the_payload_is_returned_when_the_check_itself_raises(self, monkeypatch):
        needs("pydantic")

        def broken(*args, **kwargs):
            raise RuntimeError("walk")

        monkeypatch.setattr("assertpy.assertpy.exactness_failure", broken)
        emptied = {"x": [1]}
        assert_that(_contract._validated_again(dict.clear, emptied, [emptied])).is_none()
        assert_that(emptied).is_equal_to({"x": [1]})
        for options in ({}, {"each": True}):
            payload = {"x": 1, "extra": 2}
            with pytest.raises(RuntimeError, match="walk"):
                assert_conforms([payload] if options else payload, self._stripping(), exact=True, **options)
            assert_that(payload).is_equal_to({"x": 1})

    def test_a_container_the_payload_holds_twice_is_left_as_validation_left_it(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        shared = {"x": 1, "extra": 2}
        assert_that(self._failure((shared, shared), self._stripping(), each=True)).ends_with(
            "['[0].extra', '[1].extra']"
        )
        assert_that(shared).is_equal_to({"x": 1})

        class Row(BaseModel):
            data: typing.Any

            @field_validator("data")
            @classmethod
            def strip(cls, value):
                value.pop("extra", None)
                return value

        class Rows(BaseModel):
            items: list[Row]
            side: typing.Any

            @field_validator("items", mode="before")
            @classmethod
            def none(cls, value):
                return []

        aliased = {"extra": 2}
        payload = {"items": [{"data": aliased}], "side": aliased}
        assert_conforms(payload, Rows, exact=True)
        assert_that((payload, payload["side"] is aliased, payload["items"][0]["data"] is aliased)).is_equal_to(
            ({"items": [{"data": {"extra": 2}}], "side": {"extra": 2}}, True, True)
        )

    def test_a_subclass_is_read_as_the_builtin_it_is(self):
        """Keeping the payload reads a subclass's storage, not through the methods it overrides."""
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Refusing(dict):
            def values(self):
                raise RuntimeError("values")

        class Listed(list):
            def __iter__(self):
                raise RuntimeError("iter")

        class Normalized(BaseModel):
            x: int
            rows: typing.Any = None

            @model_validator(mode="before")
            @classmethod
            def normalize(cls, data):
                return {"x": dict.__getitem__(data, "x")}

        nested = ({"a": 1},)
        assert_conforms(Refusing(x=1, rows=Listed([nested])), Normalized, exact=True)
        assert_that(_contract._held_now(Refusing(x=1, rows=Listed([nested])))).is_equal_to([({"a": 1}, {"a": 1})])

    def test_a_value_whose_comparison_raises_counts_as_a_change(self):
        """A validator can put a value of any kind into the payload, and comparing it with what was sent calls its
        own ``==``."""
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Bomb:
            def __eq__(self, other):
                raise RuntimeError("comparison")

            __hash__ = None

        class Replaced(BaseModel):
            value: typing.Any

            @model_validator(mode="before")
            @classmethod
            def replace(cls, data):
                data.pop("extra", None)
                data["value"] = Bomb()
                return data

        payload = {"value": 1, "extra": 2}
        assert_that(self._failure(payload, Replaced)).ends_with("['extra']")
        assert_that((sorted(payload), type(payload["value"]).__name__)).is_equal_to((["value"], "Bomb"))

    def test_a_subclass_changed_in_place_is_not_put_back(self):
        """Putting a subclass back would go through methods of its own, so what it lost stays unseen."""
        needs("pydantic")
        assert_conforms(collections.OrderedDict(x=1, extra=2), self._stripping(), exact=True)

    def test_a_model_with_no_code_of_its_own_keeps_no_record(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel

        class Plain(BaseModel):
            x: int
            rows: list[dict[str, int]] = []

        def refused(payload):
            raise RuntimeError("no record is needed")

        monkeypatch.setattr("assertpy.assertpy.sent_record", refused)
        assert_conforms({"x": 1, "rows": [{"a": 1}]}, Plain, exact=True)
        assert_conforms([{"x": 1}], Plain, exact=True, each=True)
        with pytest.raises(RuntimeError, match="no record"):
            assert_conforms({"x": 1}, self._stripping(), exact=True)
        assert_conforms({"x": 1}, self._stripping())

    @pytest.mark.parametrize("through", ["the class of a named tuple", "the _missing_ of an enum"])
    def test_a_dict_emptied_by_code_validation_calls_is_read_as_sent(self, through):
        """Neither is a validator: pydantic calls the class of a named tuple, and the constructor of an enum calls its
        `_missing_`.  The dict is held twice, so what either took out of it is gone from the model beside it."""
        needs("pydantic")
        from pydantic import BaseModel

        class Inner(BaseModel):
            a: int

        class Pair(typing.NamedTuple):
            held: typing.Any

        class Emptying(Pair):
            def __new__(cls, held):
                held.pop("grown", None)
                return super().__new__(cls, held)

        class Shade(enum.Enum):
            DARK = "dark"

            @classmethod
            def _missing_(cls, value):
                value.pop("grown", None)
                return cls.DARK

        shared = {"a": 1, "grown": 2}
        emptying, sent = {
            "the class of a named tuple": (Emptying, [shared]),
            "the _missing_ of an enum": (Shade, shared),
        }[through]
        holding = type("Holding", (BaseModel,), {"__annotations__": {"emptied": emptying, "inner": Inner}})
        try:
            assert_conforms({"emptied": sent, "inner": shared}, holding, exact=True)
            found = "passes"
        except AssertionFailure as failure:
            found = str(failure).split(", but ")[1]
        assert_that(found).is_equal_to("it carries 1 undeclared field(s) the model does not declare: ['inner.grown']")
        assert_that(shared).is_equal_to({"a": 1})

    def test_a_schema_says_which_code_runs_whatever_pydantic_wrote_it(self):
        """Schemas written out by hand: a named tuple was a called class, and an enum's schema named its `_missing_`,
        before pydantic gave the first a schema of its own and left the second to the enum's constructor."""

        class Forgiving(enum.Enum):
            @classmethod
            def _missing_(cls, value):
                return next(iter(cls))

        class Shade(Forgiving):
            DARK = "dark"

        class Plain(enum.Enum):
            DARK = "dark"

        class Counted(enum.IntEnum):
            ONE = 1

        class Flagged(enum.Flag):
            ONE = 1

        shut = []

        class Closed(enum.EnumMeta):
            def __getattribute__(cls, name):
                if shut and name in ("__mro__", "__dict__"):
                    raise RuntimeError(f"{name} is not to be read")
                return super().__getattribute__(name)

        class Shut(enum.Enum, metaclass=Closed):
            DARK = "dark"

        class ShutForgiving(Forgiving, metaclass=Closed):
            DARK = "dark"

        shut.append("from here on")

        def asked(schema):
            # the tree is read off the slots of `type`: asked of the class itself, this one raises
            try:
                return _contract.runs_own_code(type("Held", (), {"__pydantic_core_schema__": schema}))
            except RuntimeError as refusal:
                return str(refusal)

        assert_that(
            {
                "a called class": asked({"type": "call"}),
                "a named tuple": asked({"type": "named-tuple"}),
                "a named tuple under a list": asked({"type": "list", "items_schema": {"type": "named-tuple"}}),
                "an enum with a _missing_ of its own": asked({"type": "enum", "cls": Forgiving}),
                "an enum that inherits one": asked({"type": "enum", "cls": Shade}),
                "a flag": asked({"type": "enum", "cls": Flagged}),
                "an enum the schema names a _missing_ for": asked({"type": "enum", "cls": Plain, "missing": len}),
                "an enum whose class the schema does not name": asked({"type": "enum"}),
                "a plain enum": asked({"type": "enum", "cls": Plain}),
                "an int enum": asked({"type": "enum", "cls": Counted}),
                "a schema that is no enum": asked({"type": "int"}),
                "an enum schema over a class that is none": asked({"type": "enum", "cls": int}),
                "a plain enum whose metaclass refuses to be read": asked({"type": "enum", "cls": Shut}),
                "one with a _missing_ whose metaclass refuses": asked({"type": "enum", "cls": ShutForgiving}),
            }
        ).is_equal_to(
            {
                "a called class": True,
                "a named tuple": True,
                "a named tuple under a list": True,
                "an enum with a _missing_ of its own": True,
                "an enum that inherits one": True,
                "a flag": True,
                "an enum the schema names a _missing_ for": True,
                "an enum whose class the schema does not name": True,
                "a plain enum": False,
                "an int enum": False,
                "a schema that is no enum": False,
                "an enum schema over a class that is none": True,
                "a plain enum whose metaclass refuses to be read": False,
                "one with a _missing_ whose metaclass refuses": True,
            }
        )

    def test_which_models_run_code_of_their_own(self, monkeypatch):
        needs("pydantic")
        import pydantic
        from pydantic import AfterValidator, BaseModel, PrivateAttr, field_serializer, field_validator
        from pydantic.dataclasses import dataclass as pydantic_dataclass

        class Plain(BaseModel):
            x: int
            tags: list[str] = []
            missing: int = 0
            post_init: dict[str, int] = {}

        class Serialized(BaseModel):
            x: int

            @field_serializer("x")
            def render(self, value):
                return str(value)

        class Checked(BaseModel):
            x: int

            @field_validator("x")
            @classmethod
            def check(cls, value):
                return value

        class PostInit(BaseModel):
            x: int

            def model_post_init(self, context):
                pass

        class Private(BaseModel):
            x: int
            _cache: dict = PrivateAttr(default_factory=dict)

        class OwnInit(BaseModel):
            x: int

            def __init__(self, **data):
                super().__init__(**data)

        class Annotated(BaseModel):
            x: typing.Annotated[int, AfterValidator(lambda value: value)]

        @pydantic_dataclass
        class Posted:
            x: int

            def __post_init__(self):
                pass

        class Holding(BaseModel):
            inner: list[self._stripping()]
            plain: Plain

        class Dataclassed(BaseModel):
            posted: Posted

        class Unbuilt:
            __pydantic_core_schema__ = None

        class Point(typing.NamedTuple):
            x: int

        class Called(BaseModel):
            point: Point

        class Shade(enum.Enum):
            DARK = "dark"

            @classmethod
            def _missing_(cls, value):
                return cls.DARK

        class Shaded(BaseModel):
            shade: Shade

        ring: list = []
        ring.append(ring)

        class Defaulted(BaseModel):
            x: int
            held: typing.Any = ring

        class Listed(BaseModel):
            x: int
            rows: list[int] = pydantic.Field(default_factory=list)

        monkeypatch.setattr(_contract, "_OWN_CODE", dict.fromkeys(range(256)))
        assert_that(_contract.runs_own_code(Defaulted)).is_false()
        # a factory that takes no data is handed nothing of the payload
        assert_that(_contract.runs_own_code(Listed)).is_false()
        own = [Checked, PostInit, Private, OwnInit, Annotated, Holding, Dataclassed, Unbuilt, Called, Shaded]
        if hasattr(pydantic, "Discriminator"):
            tagged = typing.Annotated[
                typing.Annotated[Plain, pydantic.Tag("plain")] | typing.Annotated[Serialized, pydantic.Tag("other")],
                pydantic.Discriminator(lambda value: "plain"),
            ]

            class Discriminated(BaseModel):
                one: tagged

            own.append(Discriminated)
        if hasattr(pydantic.fields.FieldInfo, "default_factory_takes_validated_data"):

            class Derived(BaseModel):
                x: int
                twice: int = pydantic.Field(default_factory=lambda data: data["x"] * 2)

            own.append(Derived)
        answers = {model.__name__: _contract.runs_own_code(model) for model in [Plain, Serialized, *own]}
        assert_that(answers).is_equal_to(
            {"Plain": False, "Serialized": False} | {model.__name__: True for model in own}
        )
        assert_that((0 in _contract._OWN_CODE, _contract.runs_own_code(Plain))).is_equal_to((False, False))


class TestExactnessReachesDataclassesAndTypedDicts:
    """A dataclass and a `TypedDict` drop a key they do not declare as a model does, and passed for it: the walk
    read neither their own keys nor the models inside a dataclass."""

    CARRIES = "undeclared field(s) the model does not declare: "
    READ_FROM_X = "\n<f.x> is not read: its field was read from <X>"
    MIXED = (
        "<f> cannot be checked: one of its declared types keeps a key another ignores,"
        " and they do not say which built it"
    )

    @staticmethod
    def _found(payload, model):
        try:
            assert_conforms(payload, model, exact=True)
        except AssertionFailure as failure:
            return str(failure).split(", but ")[1].removeprefix("it carries ")
        return "passes"

    @staticmethod
    def _holding(annotation, **validators):
        from pydantic import BaseModel

        return type("Holding", (BaseModel,), {"__annotations__": {"f": annotation}, **validators})

    def test_a_record_that_keeps_extras_drops_a_name_where_pydantic_ignores_it(self):
        """Sent beside the alias its field is read from, a field's name is dropped by a record.  One that allows extras
        keeps it where pydantic puts what was sent there over the field, as an older one does, and drops it where
        pydantic ignores it, as a later one does.  What is expected is read off what pydantic built: the name was kept
        where the field holds what was sent under it, and another key where the record holds it."""
        needs("pydantic")
        from pydantic import ConfigDict, Field, TypeAdapter
        from pydantic.dataclasses import dataclass as pydantic_dataclass
        from typing_extensions import TypedDict

        def typed_dict(**config):
            class Record(TypedDict):
                first: typing.Annotated[int, Field(alias="firstName")]

            Record.__pydantic_config__ = ConfigDict(**config)
            return Record

        def dataclass(**config):
            plain = type(
                "Record", (), {"__annotations__": {"first": int}, "first": Field(default=0, alias="firstName")}
            )
            return pydantic_dataclass(config=ConfigDict(**config))(plain)

        sent = {"first": 1, "firstName": 2, "more": 3}

        def expected(record):
            built = TypeAdapter(record).validate_python(sent)
            held = built if isinstance(built, dict) else vars(built)
            dropped = [f"f.{key}" for key in ("first", "more") if held.get(key) != sent[key]]
            not_read = "\n<f.first> is not read: its field was read from <firstName>" if "f.first" in dropped else ""
            return f"{len(dropped)} {self.CARRIES}{dropped}{not_read}" if dropped else "passes"

        records = {
            (build.__name__, kept): build(**{"extra": kept} if kept else {})
            for build in (typed_dict, dataclass)
            for kept in ("", "allow")
        }
        try:

            class Declaring(TypedDict, extra_items=int):
                first: typing.Annotated[int, Field(alias="firstName")]

            self._holding(Declaring)
            records["typed_dict", "extra_items"] = Declaring
        # an older `TypedDict` takes no such argument, and an older pydantic builds no schema for one that does
        except TypeError:
            pass
        assert_that(expected(records["typed_dict", ""])).is_equal_to(
            f"2 {self.CARRIES}['f.first', 'f.more']\n<f.first> is not read: its field was read from <firstName>"
        )
        found = {key: self._found({"f": sent}, self._holding(record)) for key, record in records.items()}
        assert_that(found).is_equal_to({key: expected(record) for key, record in records.items()})

    def test_a_tag_an_extra_was_put_over_tells_no_typed_dict_apart(self):
        """Of two `TypedDict`s that read their tag through an alias, one keeps extras.  Where pydantic puts the tag's
        own name sent beside the alias over the tag it validated, as an older one does, what the dict holds there says
        nothing of which built it, and the one that drops extras would have ignored the name: it refuses.  Where
        pydantic ignores the name, as a later one does, the tag tells them apart and the name is named.  A tag nothing
        was put over tells them apart either way."""
        needs("pydantic")
        from pydantic import ConfigDict, Field
        from typing_extensions import TypedDict

        class Keeping(TypedDict):
            tag: typing.Annotated[typing.Literal["a"], Field(alias="kind")]

        Keeping.__pydantic_config__ = ConfigDict(extra="allow")

        class Dropping(TypedDict):
            tag: typing.Annotated[typing.Literal["b"], Field(alias="kind")]

        holding = self._holding(Keeping | Dropping)
        put_over = {"kind": "a", "tag": "b"}
        built = holding.model_validate({"f": put_over}).f
        assert_that(built).is_in({"tag": "b"}, {"tag": "a"})
        named = f"1 {self.CARRIES}['f.tag']\n<f.tag> is not read: its field was read from <kind>"
        assert_that(self._found({"f": put_over}, holding)).is_equal_to(self.MIXED if built == {"tag": "b"} else named)
        assert_that(self._found({"f": {"kind": "b", "grown": 1}}, holding)).is_equal_to(f"1 {self.CARRIES}['f.grown']")

        class Plain(TypedDict):
            tag: typing.Annotated[typing.Literal["a"], Field(alias="kind")]

        # neither keeps extras, so nothing was put over the tag: it tells which built the dict, and the name is named
        assert_that(self._found({"f": {"kind": "b", "tag": "a"}}, self._holding(Plain | Dropping))).is_equal_to(
            f"1 {self.CARRIES}['f.tag']\n<f.tag> is not read: its field was read from <kind>"
        )

        class KeepingByName(TypedDict):
            kind: typing.Literal["a"]

        KeepingByName.__pydantic_config__ = ConfigDict(extra="allow")

        class DroppingByName(TypedDict):
            kind: typing.Literal["b"]

        # a tag sent under its own name is the key validation read, whoever keeps extras: nothing was put over it
        by_name = self._holding(KeepingByName | DroppingByName)
        assert_that(self._found({"f": {"kind": "b", "grown": 1}}, by_name)).is_equal_to(f"1 {self.CARRIES}['f.grown']")

        class KeepingEither(TypedDict):
            tag: typing.Annotated[typing.Literal["a"], Field(alias="kind")]

        KeepingEither.__pydantic_config__ = ConfigDict(extra="allow", populate_by_name=True)

        class DroppingEither(TypedDict):
            tag: typing.Annotated[typing.Literal["b"], Field(alias="kind")]

        DroppingEither.__pydantic_config__ = ConfigDict(populate_by_name=True)

        # read by its name where no alias was sent, the name is the key validation read, and nothing was put over it
        either = self._holding(KeepingEither | DroppingEither)
        assert_that(self._found({"f": {"tag": "b", "grown": 1}}, either)).is_equal_to(f"1 {self.CARRIES}['f.grown']")

    def test_a_typed_dict_that_keeps_extras_lends_no_other_its_exemption(self):
        """One that keeps extras is ruled out by another tag.  The two left drop extras, read the name of the tag as
        another field, and are told apart by the tag itself, whichever the union names first."""
        needs("pydantic")
        from pydantic import ConfigDict, Field
        from typing_extensions import TypedDict

        class Keeping(TypedDict):
            tag: typing.Annotated[typing.Literal["a"], Field(alias="kind")]
            mode: typing.Literal["keep"]

        Keeping.__pydantic_config__ = ConfigDict(extra="allow")

        class First(TypedDict):
            tag: typing.Annotated[typing.Literal["b"], Field(alias="kind")]
            other: typing.Annotated[str, Field(alias="tag")]
            spare: typing.Annotated[str, Field(alias="alt")]
            mode: typing.Literal["drop"]

        class Second(TypedDict):
            tag: typing.Annotated[typing.Literal["a"], Field(alias="alt")]
            other: typing.Annotated[str, Field(alias="tag")]
            spare: typing.Annotated[str, Field(alias="kind")]
            mode: typing.Literal["drop"]

        sent = {"kind": "b", "tag": "a", "alt": "a", "mode": "drop"}
        built_by = {
            "the first": {"tag": "b", "other": "a", "spare": "a", "mode": "drop"},
            "the second": {"tag": "a", "other": "a", "spare": "b", "mode": "drop"},
        }
        for union in (Keeping | First | Second, Second | First | Keeping):
            holding = self._holding(union)
            assert_that(built_by.values()).contains(holding.model_validate({"f": sent}).f)
            assert_that(self._found({"f": sent}, holding)).is_equal_to("passes")

    def test_a_name_beside_its_alias_is_named_where_every_typed_dict_ignores_it(self):
        """Where the check knows which `TypedDict` built a dict it names a field's name sent beside the alias, and so
        where it does not but each of them ignores the name.  One that keeps extras keeps the name where pydantic puts
        it over the field, as an older one does: beside one that ignores it nothing tells which built the dict, and it
        refuses, whatever object the field holds."""
        needs("pydantic")
        from pydantic import ConfigDict, Field, TypeAdapter
        from typing_extensions import TypedDict

        class One(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]

        class Other(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]

        class Keeping(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]

        Keeping.__pydantic_config__ = ConfigDict(extra="allow")

        large = 10**30
        payloads = {"two objects": {"f": {"x": 1, "X": 2}}, "one object": {"f": {"x": large, "X": large}}}
        named = f"1 {self.CARRIES}['f.x']{self.READ_FROM_X}"
        kept = self.MIXED if TypeAdapter(Keeping).validate_python({"x": 1, "X": 2})["x"] == 1 else named
        kinds = {
            "one": (One, named),
            "two that drop it": (One | Other, named),
            "the other first": (Other | One, named),
            "one beside one that may keep it": (One | Keeping, kept),
            "the one that may keep it first": (Keeping | One, kept),
        }
        found = {
            (label, sent): self._found(payload, self._holding(kind))
            for label, (kind, _) in kinds.items()
            for sent, payload in payloads.items()
        }
        assert_that(found).is_equal_to(
            {(label, sent): verdict for label, (_, verdict) in kinds.items() for sent in payloads}
        )

    def test_a_typed_dict_under_a_container_the_walk_does_not_name_is_not_guessed(self):
        """A deque, an `OrderedDict` and a named tuple are no container the walk reads a `TypedDict` out of, nor a type
        it knows to build no dict.  A clean payload passes, and a key that grew refuses: read as building no dict, a
        named tuple hid the `TypedDict` in its field, and the grown key passed."""
        needs("pydantic")
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        class Pair(typing.NamedTuple):
            point: Point

        grown = {"x": 1, "grown": 2}
        shapes = {
            "in a deque": (collections.deque[Point], [{"x": 1}], [grown]),
            "in an OrderedDict": (collections.OrderedDict[str, Point], {"k": {"x": 1}}, {"k": grown}),
            "in a named tuple": (Pair, [{"x": 1}], [grown]),
            "beside a deque": (Point | collections.deque[int], {"x": 1}, grown),
        }
        found = {
            label: (self._found({"f": clean}, self._holding(kind)), self._found({"f": drifting}, self._holding(kind)))
            for label, (kind, clean, drifting) in shapes.items()
        }
        refused = "cannot be checked: it holds a key the dict built from it does not, and its declared types do not say"
        assert_that(
            {label: (clean, drifting.split("> ")[-1][:100]) for label, (clean, drifting) in found.items()}
        ).is_equal_to(dict.fromkeys(shapes, ("passes", refused)))

    def test_a_field_read_from_a_later_source_is_no_extra_a_model_lost(self):
        """A model that keeps typed extras is asked which of them it no longer holds, and a key a field was read
        from is none of them, whichever of the field's sources it is."""
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field

        class Row(BaseModel):
            x: int

        class Open(BaseModel):
            model_config = ConfigDict(extra="allow", populate_by_name=True)
            __pydantic_extra__: dict[str, Row]
            sub: Row = Field(alias="theSub")

        assert_that(self._found({"sub": {"x": 1}}, Open)).is_equal_to("passes")
        assert_that(self._found({"sub": {"x": 1}, "more": {"x": 1, "extra": 2}}, Open)).is_equal_to(
            f"1 {self.CARRIES}['more.extra']"
        )

    def test_a_typed_dict_is_checked_for_its_own_keys_and_walked(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field
        from typing_extensions import NotRequired, TypedDict

        class Row(BaseModel):
            x: int

        class Point(TypedDict):
            x: int
            y: NotRequired[int]

        class Open(TypedDict):
            __pydantic_config__ = ConfigDict(extra="allow")  # ty: ignore[invalid-typed-dict-statement]  # pydantic's hook
            x: int

        class Aliased(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]

        class Nested(TypedDict):
            row: Row
            points: NotRequired[list[Point]]
            inner: NotRequired[Point]

        class Wider(Point):
            z: int

        extra = {"x": 1, "extra": 2}
        cases = {
            "an undeclared key": (Point, extra),
            "an optional key and an undeclared one": (Point, {"x": 1, "y": 2, "extra": 3}),
            "a clean one": (Point, {"x": 1, "y": 2}),
            "one that allows extras": (Open, extra),
            "an alias": (Aliased, {"X": 1}),
            "an alias and an undeclared key": (Aliased, {"X": 1, "x": 2, "extra": 3}),
            "a model inside": (Nested, {"row": extra}),
            "a list of them inside": (Nested, {"row": {"x": 1}, "points": [{"x": 1}, extra], "more": 1}),
            "one inside another": (Nested, {"row": {"x": 1}, "inner": extra}),
            "an inherited key": (Wider, {"x": 1, "z": 2, "extra": 3}),
            "in a list": (list[Point], [{"x": 1}, extra]),
            "as a dict value": (dict[str, Point], {"k": extra}),
            "beside None": (Point | None, extra),
        }
        found = {label: self._found({"f": payload}, self._holding(kind)) for label, (kind, payload) in cases.items()}
        assert_that(found).is_equal_to(
            {
                "an undeclared key": f"1 {self.CARRIES}['f.extra']",
                "an optional key and an undeclared one": f"1 {self.CARRIES}['f.extra']",
                "a clean one": "passes",
                "one that allows extras": "passes",
                "an alias": "passes",
                "an alias and an undeclared key": f"2 {self.CARRIES}['f.extra', 'f.x']{self.READ_FROM_X}",
                "a model inside": f"1 {self.CARRIES}['f.row.extra']",
                "a list of them inside": f"2 {self.CARRIES}['f.more', 'f.points[1].extra']",
                "one inside another": f"1 {self.CARRIES}['f.inner.extra']",
                "an inherited key": f"1 {self.CARRIES}['f.extra']",
                "in a list": f"1 {self.CARRIES}['f[1].extra']",
                "as a dict value": f"1 {self.CARRIES}['f.k.extra']",
                "beside None": f"1 {self.CARRIES}['f.extra']",
            }
        )

    def test_a_typed_dict_declared_in_text_or_beside_another_is_read_off_the_schema(self, monkeypatch):
        """The plain dict built does not say which of two it became, so a key lost there refuses.  Declared in text,
        its own keys and aliases are read off the schema, and so is a `TypedDict` below it."""
        needs("pydantic")
        from pydantic import BaseModel, Field, field_validator
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        class Other(TypedDict):
            y: int

        class Texted(TypedDict):
            x: "int"
            inner: "Point"

        class TextedAlias(TypedDict):
            x: "typing.Annotated[int, Field(alias='X')]"

        class Emptied(BaseModel):
            f: list[Point]

            @field_validator("f", mode="before")
            @classmethod
            def none(cls, value):
                return []

        class HoldsTexted(BaseModel):
            f: Texted

        class HoldsTextedAlias(BaseModel):
            f: TextedAlias

        extra = {"x": 1, "extra": 2}
        found = [
            self._found({"f": extra}, self._holding(Point | Other)),
            self._found({"f": {"x": 1, "inner": {"x": 1}, "extra": 2}}, HoldsTexted),
            self._found({"f": {"x": 1, "inner": extra}}, HoldsTexted),
            self._found({"f": {"X": 1}}, HoldsTextedAlias),
            self._found({"f": {"X": 1, "x": 2, "extra": 3}}, HoldsTextedAlias),
            self._found({"f": [extra]}, Emptied),
            self._found({"f": [{"x": 1}]}, Emptied),
        ]

        # annotations that raise when read, as from 3.14 one naming what is defined only later does
        def unreadable(owner, **options):
            raise NameError("Later")

        holding = self._holding(Point)
        monkeypatch.setattr(_contract, "_RECORDS", {})
        monkeypatch.setattr(inspect, "get_annotations", unreadable)
        found.append(self._found({"f": extra}, holding))
        assert_that(found).is_equal_to(
            [
                "<f> cannot be checked: it holds a key the dict built from it does not, and its declared types do not"
                " say which built it",
                f"1 {self.CARRIES}['f.extra']",
                f"1 {self.CARRIES}['f.inner.extra']",
                "passes",
                f"2 {self.CARRIES}['f.extra', 'f.x']{self.READ_FROM_X}",
                f"1 {self.CARRIES}['f[0].extra']",
                "passes",
                f"1 {self.CARRIES}['f.extra']",
            ]
        )

    def test_a_record_is_read_as_the_schema_pydantic_built_says(self):
        """What no annotation tells is in the schema: which of several aliases wins, a config that reaches a
        `TypedDict` from the model above, an alias on a plain dataclass."""
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field, ValidationError
        from pydantic.dataclasses import dataclass as pydantic_dataclass
        from typing_extensions import TypedDict

        class Row(BaseModel):
            x: int

        class AliasedRow(TypedDict):
            row: typing.Annotated[Row, Field(alias="R")]

        class ByName(BaseModel):
            model_config = ConfigDict(populate_by_name=True)
            f: AliasedRow

        class HasDict:
            pass

        @dataclasses.dataclass(slots=True)
        class Slotted(HasDict):
            row: Row

        @pydantic_dataclass(config=ConfigDict(extra="allow"))
        class Open:
            x: int
            kind: typing.ClassVar[str] = "default"

        @pydantic_dataclass
        class Twice:
            x: int = Field(alias="A", validation_alias="V")

        @dataclasses.dataclass
        class PlainAliased:
            x: typing.Annotated[int, Field(alias="X")]

        class Several(TypedDict):
            x: typing.Annotated[int, Field(alias="A"), Field(alias="B")]

        extra = {"x": 1, "extra": 2}
        found = [
            self._found({"f": {"R": extra}}, ByName),
            self._found({"f": {"row": extra}}, self._holding(Slotted)),
            self._found({"f": {"x": 1, "kind": "other"}}, self._holding(Open)),
            self._found({"f": {"V": 1, "A": 2}}, self._holding(Twice)),
            self._found({"f": {"V": 1, "extra": 2}}, self._holding(Twice)),
        ]
        assert_that(found).is_equal_to(
            [
                f"1 {self.CARRIES}['f.row.extra']",
                f"1 {self.CARRIES}['f.row.extra']",
                "passes",
                f"1 {self.CARRIES}['f.A']\n<f.A> is not read: its field was read from <V>",
                f"1 {self.CARRIES}['f.extra']",
            ]
        )
        try:
            ByName.model_validate({"f": {"row": extra}})
        # pydantic 2.0 does not hand the model's config down to the `TypedDict`
        except ValidationError:
            pass
        else:
            assert_that(self._found({"f": {"row": extra}}, ByName)).is_equal_to(f"1 {self.CARRIES}['f.row.extra']")
        if "validate_by_alias" in ConfigDict.__annotations__:

            class ByNameOnly(TypedDict):
                __pydantic_config__ = ConfigDict(validate_by_alias=False, validate_by_name=True)  # ty: ignore[invalid-typed-dict-statement]  # pydantic's hook
                row: typing.Annotated[Row, Field(alias="R")]

            # read by name alone, the alias is dropped, and the mapping under the name is the one walked
            both = {"f": {"R": {"x": 1}, "row": extra}}
            assert_that(self._found(both, self._holding(ByNameOnly))).is_equal_to(
                f"2 {self.CARRIES}['f.R', 'f.row.extra']\n<f.R> is not read: its field was read from <row>"
            )

            class Incoming(TypedDict):
                __pydantic_config__ = ConfigDict(validate_by_alias=False, validate_by_name=True)  # ty: ignore[invalid-typed-dict-statement]  # pydantic's hook
                x: typing.Annotated[int, Field(validation_alias="X")]

            # an alias no dump shows: it is known for a spelling of the field by being its validation alias
            assert_that(self._found({"f": {"x": 1, "X": 2}}, self._holding(Incoming))).is_equal_to(
                f"1 {self.CARRIES}['f.X']\n<f.X> is not read: its field was read from <x>"
            )
        # which alias pydantic reads here differs by its version; whichever it takes is declared, the rest are not
        for kind, aliases in ((PlainAliased, ("X", "x")), (Several, ("B", "A"))):
            holding = self._holding(kind)
            for alias in aliases:
                try:
                    holding.model_validate({"f": {alias: 1}})
                except ValidationError:
                    continue
                assert_that(self._found({"f": {alias: 1}}, holding)).is_equal_to("passes")
                assert_that(self._found({"f": {alias: 1, "extra": 2}}, holding)).is_equal_to(
                    f"1 {self.CARRIES}['f.extra']"
                )
                break

    def test_a_record_no_schema_holds_is_read_as_its_annotations_are_written(self):
        """A plain dataclass validated again on its own, out of a list its validator cut, has no schema that holds it,
        and is read off its annotations; inside a union of containers the schema of its model reaches it.  A
        parametrized `TypedDict` is read off the schema of what its variable is."""
        needs("pydantic")
        from pydantic import BaseModel, BeforeValidator, Field, field_validator
        from typing_extensions import NotRequired, TypedDict

        class Row(BaseModel):
            x: int

        def plain(*several, aliased):
            @dataclasses.dataclass
            class Plain:
                x: typing.Annotated[(int, Field(alias="X"), *several)] = 0
                row: Row | None = None
                derived: int = dataclasses.field(default=0, init=False)
                y: int = aliased

            return Plain

        class Point(TypedDict):
            x: int

        item = typing.TypeVar("item")

        class Box(TypedDict, typing.Generic[item]):
            held: item
            count: typing.Annotated[int, Field(alias="n")]

        cut = {"cut": field_validator("f", mode="after")(classmethod(lambda cls, value: value[:1]))}
        try:
            full = plain(Field(description="the value"), aliased=Field(default=0, alias="Y"))
            either, trimmed = self._holding(list[full] | tuple[int, ...]), self._holding(list[full], **cut)
        # pydantic 2.0 takes one `Field` for a field, in its annotation or as its default
        except TypeError:
            lone = plain(aliased=0)
            either, trimmed = self._holding(list[lone] | tuple[int, ...]), self._holding(list[lone], **cut)
        sent = [{"extra": 2}, {"row": {"x": 1, "extra": 2}}, {"derived": 7}]
        expected = [f"1 {self.CARRIES}['f[0].{name}']" for name in ("extra", "row.extra", "derived")]
        # pydantic 2.0 reads neither alias off a plain dataclass, and drops both keys
        built = either.model_validate({"f": [{"X": 5, "Y": 6}]}).f[0]
        if (built.x, built.y) == (5, 6):
            sent.append({"X": 5, "Y": 6})
            expected.append("passes")
        found = [self._found({"f": [item]}, either) for item in sent]
        assert_that([self._found({"f": [item, {}]}, trimmed) for item in sent]).is_equal_to(expected)

        class Rows(TypedDict):
            rows: NotRequired[typing.Annotated[list[Row], BeforeValidator(lambda value: [])]]

        # the list is read again as the annotation says, which is read without what marks the key as optional
        found.append(self._found({"f": {"rows": [{"x": 1, "extra": 2}]}}, self._holding(Rows)))
        expected.append(f"1 {self.CARRIES}['f.rows[0].extra']")
        try:
            boxed = self._holding(Box[Point])
        # pydantic before 2.2 builds no schema for a parametrized `TypedDict`
        except TypeError:
            boxed = None
        if boxed is not None:
            found += [
                self._found({"f": {"held": {"x": 1}, "n": 1, "extra": 2}}, boxed),
                self._found({"f": {"held": {"x": 1, "extra": 2}, "n": 1}}, boxed),
            ]
            expected += [f"1 {self.CARRIES}['f.extra']", f"1 {self.CARRIES}['f.held.extra']"]
        assert_that(found).is_equal_to(expected)

    def test_a_dataclass_is_checked_for_its_own_keys_and_walked(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field
        from pydantic.dataclasses import dataclass as pydantic_dataclass

        class Row(BaseModel):
            x: int

        @pydantic_dataclass
        class Inner:
            x: int
            flag: dataclasses.InitVar[bool] = False
            derived: int = dataclasses.field(default=0, init=False)
            named: int = Field(default=0, alias="Named")
            kind: typing.ClassVar[str] = "inner"

        @pydantic_dataclass(config=ConfigDict(extra="allow"))
        class Open:
            x: int

        @dataclasses.dataclass
        class Plain:
            x: int
            row: "Row | None" = None
            rows: list[Row] = dataclasses.field(default_factory=list)

        @dataclasses.dataclass(slots=True)
        class Slotted:
            x: int
            inner: Inner

        class HoldsPlain(BaseModel):
            f: Plain

        class HoldsPlains(BaseModel):
            f: list[Plain]

        extra = {"x": 1, "extra": 2}
        cases = {
            "an undeclared key": (self._holding(Inner), extra),
            "an init-only key and an alias": (self._holding(Inner), {"x": 1, "flag": True, "Named": 5}),
            "a key for a field that is not set from input": (self._holding(Inner), {"x": 1, "derived": 7}),
            "a class variable's name": (self._holding(Inner), {"x": 1, "kind": "other"}),
            "one that allows extras": (self._holding(Open), extra),
            "a plain dataclass": (HoldsPlain, extra),
            "a model in a field declared in text": (HoldsPlain, {"x": 1, "row": extra}),
            "models in a list field": (HoldsPlain, {"x": 1, "rows": [{"x": 1}, extra]}),
            "a dataclass without a dict of its own": (self._holding(Slotted), {"x": 1, "inner": extra, "more": 3}),
            "in a list": (HoldsPlains, [{"x": 1}, extra]),
            "as a dict value": (self._holding(dict[str, Inner]), {"k": extra}),
            "a clean one": (HoldsPlain, {"x": 1, "row": {"x": 2}, "rows": [{"x": 3}]}),
        }
        found = {label: self._found({"f": payload}, model) for label, (model, payload) in cases.items()}
        assert_that(found).is_equal_to(
            {
                "an undeclared key": f"1 {self.CARRIES}['f.extra']",
                "an init-only key and an alias": "passes",
                "a key for a field that is not set from input": f"1 {self.CARRIES}['f.derived']",
                "a class variable's name": f"1 {self.CARRIES}['f.kind']",
                "one that allows extras": "passes",
                "a plain dataclass": f"1 {self.CARRIES}['f.extra']",
                "a model in a field declared in text": f"1 {self.CARRIES}['f.row.extra']",
                "models in a list field": f"1 {self.CARRIES}['f.rows[1].extra']",
                "a dataclass without a dict of its own": f"2 {self.CARRIES}['f.inner.extra', 'f.more']",
                "in a list": f"1 {self.CARRIES}['f[1].extra']",
                "as a dict value": f"1 {self.CARRIES}['f.k.extra']",
                "a clean one": "passes",
            }
        )

    def test_dataclasses_that_lost_their_order_or_their_count_are_validated_again(self):
        needs("pydantic")
        from pydantic import Json, field_validator
        from pydantic.dataclasses import dataclass as pydantic_dataclass

        @dataclasses.dataclass(frozen=True)
        class Tag:
            x: int

        @pydantic_dataclass(frozen=True)
        class Mark:
            x: int

        @dataclasses.dataclass(frozen=True, eq=False)
        class Loose:
            x: int

            def __eq__(self, other):
                return True

            def __hash__(self):
                return 0

        def first(cls, value):
            return value[:1]

        def wrapped(cls, value):
            return {"x": value[0]["x"]}

        def numbered(cls, value):
            return {"x": value}

        dropping = {"kept": field_validator("f")(classmethod(first))}
        wrapping = {"wrapped": field_validator("f", mode="before")(classmethod(wrapped))}
        numbering = {"numbered": field_validator("f", mode="before")(classmethod(numbered))}
        assert_that(self._found({"f": 5}, self._holding(Tag, **numbering))).is_equal_to("passes")
        extra = {"x": 2, "extra": 3}
        found = [
            self._found({"f": [{"x": 1}, extra]}, self._holding(set[Tag])),
            self._found({"f": [{"x": 1}, extra]}, self._holding(frozenset[Mark])),
            self._found({"f": [{"x": 1}, {"x": 2}]}, self._holding(set[Tag])),
            self._found({"f": [{"x": 1}, extra]}, self._holding(list[Tag], **dropping)),
            self._found({"f": ['{"x": 1, "extra": 2}']}, self._holding(set[Json[Mark]])),
            self._found({"f": [{"x": 1}, extra]}, self._holding(set[Loose])),
            self._found({"f": [extra]}, self._holding(Tag, **wrapping)),
        ]
        order = "cannot be checked: a set keeps no order to pair its items with the models they became"
        assert_that(found).is_equal_to(
            [
                f"1 {self.CARRIES}['f[1].extra']",
                f"1 {self.CARRIES}['f[1].extra']",
                "passes",
                f"1 {self.CARRIES}['f[1].extra']",
                f"1 {self.CARRIES}['f[0].extra']",
                f"<f> {order}",
                "<f> cannot be checked: the payload holds a list where a dataclass was built",
            ]
        )

    def test_a_record_is_read_once_per_class_and_a_choice_in_it_refuses_under_a_replay(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, field_validator
        from pydantic.dataclasses import dataclass as pydantic_dataclass

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        @dataclasses.dataclass
        class Either:
            one: A | B

        class Emptied(BaseModel):
            f: list[Either]

            @field_validator("f", mode="before")
            @classmethod
            def none(cls, value):
                return []

        if "coerce_numbers_to_str" in ConfigDict.__annotations__:

            @pydantic_dataclass(config=ConfigDict(coerce_numbers_to_str=True))
            class Coercing:
                rows: tuple[str, A]

                @field_validator("rows")
                @classmethod
                def none(cls, value):
                    return ()

            found = self._found({"f": {"rows": [1, {"x": 1, "extra": 2}]}}, self._holding(Coercing))
            assert_that(found).is_equal_to(f"1 {self.CARRIES}['f.rows[1].extra']")
        monkeypatch.setattr(_contract, "_RECORDS", dict.fromkeys(range(256)))
        record = _contract._Record(None, Either)
        first = _contract._record_reads(record)
        assert_that((0 in _contract._RECORDS, _contract._record_reads(record) is first)).is_equal_to((False, True))
        assert_that(self._found({"f": [{"one": {"y": 1}}]}, Emptied)).is_equal_to(
            "<f[0].one> cannot be checked: which of its declared types it became depends on validators not run again"
        )


class TestExactnessChecksAnExtraTheModelNoLongerHolds:
    """Only the extras a model still held were walked: one a validator removed after it was built took the keys its
    type had dropped with it, and the check passed."""

    CARRIES = "undeclared field(s) the model does not declare: "

    @staticmethod
    def _found(payload, model):
        try:
            assert_conforms(payload, model, exact=True)
        except AssertionFailure as failure:
            return str(failure).split(", but ")[1].removeprefix("it carries ")
        return "passes"

    def test_an_extra_removed_after_it_was_built_is_checked_as_its_declared_type(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, model_validator

        class Value(BaseModel):
            x: int

        def removing(removal):
            class Holding(BaseModel):
                model_config = ConfigDict(extra="allow")
                __pydantic_extra__: dict[str, Value]
                own: int = 0

                @model_validator(mode="after")
                def removed(self):
                    removal(self)
                    return self

            return Holding

        cleared = removing(lambda model: model.__pydantic_extra__.clear())
        replaced = removing(lambda model: setattr(model, "__pydantic_extra__", {}))
        listed = removing(lambda model: setattr(model, "__pydantic_extra__", ["anything"]))
        unset = removing(lambda model: setattr(model, "__pydantic_extra__", None))
        one = removing(lambda model: model.__pydantic_extra__.pop("first", None))
        kept = removing(lambda model: None)
        if not isinstance(kept.model_validate({"probe": {"x": 1}}).__pydantic_extra__["probe"], Value):
            pytest.skip("this pydantic keeps extras as sent, whatever `__pydantic_extra__` declares")

        class Outer(BaseModel):
            inner: cleared

        class Named(BaseModel):
            name: str

        class Beside(cleared):
            named: Named

        drifted = {"x": 1, "unexpected": 2}
        found = {
            # a field the model declares is no extra, whatever its value is built into
            "beside a declared field": self._found({"named": {"name": "a"}, "first": drifted}, Beside),
            "kept": self._found({"own": 1, "first": drifted}, kept),
            "cleared": self._found({"own": 1, "first": drifted}, cleared),
            "replaced": self._found({"own": 1, "first": drifted}, replaced),
            "replaced by what is no dict": self._found({"own": 1, "first": drifted}, listed),
            "unset": self._found({"own": 1, "first": drifted}, unset),
            "one of two": self._found({"first": drifted, "second": {"x": 2, "other": 3}}, one),
            "two of two": self._found({"first": drifted, "second": {"x": 2, "other": 3}}, cleared),
            "in a nested model": self._found({"inner": {"first": drifted}}, Outer),
            "clean": self._found({"own": 1, "first": {"x": 1}}, cleared),
            "no extra sent": self._found({"own": 1}, cleared),
        }
        assert_that(found).is_equal_to(
            {
                "beside a declared field": f"1 {self.CARRIES}['first.unexpected']",
                "kept": f"1 {self.CARRIES}['first.unexpected']",
                "cleared": f"1 {self.CARRIES}['first.unexpected']",
                "replaced": f"1 {self.CARRIES}['first.unexpected']",
                "replaced by what is no dict": f"1 {self.CARRIES}['first.unexpected']",
                "unset": f"1 {self.CARRIES}['first.unexpected']",
                "one of two": f"2 {self.CARRIES}['first.unexpected', 'second.other']",
                "two of two": f"2 {self.CARRIES}['first.unexpected', 'second.other']",
                "in a nested model": f"1 {self.CARRIES}['inner.first.unexpected']",
                "clean": "passes",
                "no extra sent": "passes",
            }
        )

    def test_an_extra_typed_as_a_typed_dict_loses_only_what_that_typed_dict_drops(self):
        """Under a model that allows extras a `TypedDict` takes that config and keeps a key it does not declare, so
        nothing was dropped, held or removed.  One with a config of its own drops it, and is named either way."""
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, model_validator
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        class Strict(TypedDict):
            __pydantic_config__ = ConfigDict(extra="ignore")  # ty: ignore[invalid-typed-dict-statement]  # pydantic's hook
            x: int

        def holding(kind, clear):
            class Holding(BaseModel):
                model_config = ConfigDict(extra="allow")
                __pydantic_extra__: dict[str, kind]

                @model_validator(mode="after")
                def after(self):
                    if clear:
                        self.__pydantic_extra__.clear()
                    return self

            return Holding

        sent = {"first": {"x": 1, "unexpected": 2}}
        if holding(Strict, False).model_validate(sent).__pydantic_extra__ != {"first": {"x": 1}}:
            pytest.skip("this pydantic does not build an extra as the `TypedDict` declared for it")
        kept = holding(Point, False).model_validate(sent).__pydantic_extra__ == sent
        found = [self._found(sent, holding(kind, clear)) for kind in (Point, Strict) for clear in (False, True)]
        inherited = "passes" if kept else f"1 {self.CARRIES}['first.unexpected']"
        assert_that(found).is_equal_to([inherited, inherited, *[f"1 {self.CARRIES}['first.unexpected']"] * 2])

    def test_where_the_declared_type_does_not_tell_it_refuses_and_where_nothing_hides_it_passes(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, model_validator

        class Value(BaseModel):
            x: int

        class Other(BaseModel):
            y: int

        def clearing(extras):
            namespace = {"__annotations__": {"own": int}, "own": 0, "model_config": ConfigDict(extra="allow")}
            if extras is not None:
                namespace["__annotations__"]["__pydantic_extra__"] = extras

            def cleared(self):
                self.__pydantic_extra__.clear()
                return self

            namespace["cleared"] = model_validator(mode="after")(cleared)
            return type("Clearing", (BaseModel,), namespace)

        either = clearing(dict[str, Value | Other])
        if not isinstance(
            type(
                "Kept",
                (BaseModel,),
                {
                    "__annotations__": {"__pydantic_extra__": dict[str, Value]},
                    "model_config": ConfigDict(extra="allow"),
                },
            )
            .model_validate({"probe": {"x": 1}})
            .__pydantic_extra__["probe"],
            Value,
        ):
            pytest.skip("this pydantic keeps extras as sent, whatever `__pydantic_extra__` declares")

        class Outer(BaseModel):
            inner: either

        gone = "cannot be checked: the model no longer holds 1 of the extras it was sent"
        found = {
            "a choice of types": self._found({"first": {"x": 1, "unexpected": 2}}, either),
            "a choice of types, clean": self._found({"first": {"x": 1}}, either),
            "a choice of types, nested": self._found({"inner": {"first": {"x": 1}}}, Outer),
            "untyped": self._found({"first": {"x": 1, "unexpected": 2}}, clearing(None)),
            "plain values": self._found({"first": 5, "second": "text"}, clearing(dict[str, int | str])),
            "any value": self._found({"first": {"x": 1, "unexpected": 2}}, clearing(dict[str, typing.Any])),
        }
        assert_that(found).is_equal_to(
            {
                "a choice of types": f"<the payload> {gone}",
                "a choice of types, clean": f"<the payload> {gone}",
                "a choice of types, nested": f"<inner> {gone}",
                "untyped": "passes",
                "plain values": "passes",
                "any value": "passes",
            }
        )


class TestExactnessReadsATypedDictOffTheSchema:
    """A `TypedDict` builds a plain dict, which names no class: under a union, under an annotation written as text and
    in the place of a type variable the walk had no declaration for it, and a key it dropped passed."""

    CARRIES = "undeclared field(s) the model does not declare: "
    UNSURE = (
        "cannot be checked: it holds a key the dict built from it does not,"
        " and its declared types do not say which built it"
    )

    @staticmethod
    def _found(payload, model):
        try:
            assert_conforms(payload, model, exact=True)
        except AssertionFailure as failure:
            return str(failure).split(", but ")[1].removeprefix("it carries ")
        return "passes"

    @staticmethod
    def _holding(annotation, **validators):
        from pydantic import BaseModel

        return type("Holding", (BaseModel,), {"__annotations__": {"f": annotation}, **validators})

    def test_one_typed_dict_beside_types_that_build_no_dict_is_that_record(self):
        needs("pydantic")
        from pydantic import BaseModel, RootModel
        from typing_extensions import NotRequired, TypedDict

        class Row(BaseModel):
            x: int

        class Point(TypedDict):
            x: int
            row: NotRequired[Row]

        class Defaulted(BaseModel):
            f: Point | int = 0

        class Linked(BaseModel):
            f: Point | int
            next: "Linked | None" = None

        extra = {"x": 1, "extra": 2}
        found = {
            "with a default": self._found({"f": extra}, Defaulted),
            "in a model that names itself": self._found({"f": 1, "next": {"f": extra}}, Linked),
            "beside a scalar": self._found({"f": extra}, self._holding(Point | int)),
            "beside a model and a list": self._found({"f": extra}, self._holding(Point | Row | list[int])),
            "a model under it": self._found({"f": {"x": 1, "row": extra}}, self._holding(Point | int)),
            "in a list": self._found({"f": [{"x": 1}, extra]}, self._holding(list[Point | int])),
            "at the root": self._found(extra, RootModel[Point | int]),
            "clean": self._found({"f": {"x": 1}}, self._holding(Point | int)),
            "the other member": self._found({"f": 5}, self._holding(Point | int)),
        }
        assert_that(found).is_equal_to(
            {
                "with a default": f"1 {self.CARRIES}['f.extra']",
                "in a model that names itself": f"1 {self.CARRIES}['next.f.extra']",
                "beside a scalar": f"1 {self.CARRIES}['f.extra']",
                "beside a model and a list": f"1 {self.CARRIES}['f.extra']",
                "a model under it": f"1 {self.CARRIES}['f.row.extra']",
                "in a list": f"1 {self.CARRIES}['f[1].extra']",
                "at the root": f"1 {self.CARRIES}['extra']",
                "clean": "passes",
                "the other member": "passes",
            }
        )

    def test_several_typed_dicts_are_told_apart_only_by_what_their_literals_rule_out(self):
        needs("pydantic")
        from pydantic import Field, field_validator
        from typing_extensions import NotRequired, TypedDict

        class Inner(TypedDict):
            x: int

        class A(TypedDict):
            tag: typing.Literal["a"]
            nested: Inner

        class B(TypedDict):
            tag: typing.Literal["b", "c"]
            nested: Inner
            more: NotRequired[int]

        def retagged(cls, value):
            return {**value, "tag": "z"}

        lost = {"tag": "a", "nested": {"x": 1, "extra": 2}}
        tagged = typing.Annotated[A | B, Field(discriminator="tag")]
        rewritten = self._holding(A | B, retagged=field_validator("f", mode="after")(classmethod(retagged)))
        found = {
            "a key lost below equal keys": self._found({"f": lost}, self._holding(A | B)),
            "a key of the one it is not": self._found(
                {"f": {"tag": "a", "nested": {"x": 1}, "more": 2}}, self._holding(A | B)
            ),
            "the other one keeps its key": self._found(
                {"f": {"tag": "c", "nested": {"x": 1}, "more": 2}}, self._holding(A | B)
            ),
            "by a discriminator": self._found({"f": lost}, self._holding(tagged)),
            "clean": self._found({"f": {"tag": "b", "nested": {"x": 1}}}, self._holding(A | B)),
            "a tag none of them lists": self._found({"f": lost}, rewritten),
        }
        assert_that(found).is_equal_to(
            {
                "a key lost below equal keys": f"1 {self.CARRIES}['f.nested.extra']",
                "a key of the one it is not": f"1 {self.CARRIES}['f.more']",
                "the other one keeps its key": "passes",
                "by a discriminator": f"1 {self.CARRIES}['f.nested.extra']",
                "clean": "passes",
                # nothing rules either out, both declare `nested` as one type, and that type names the key
                "a tag none of them lists": f"1 {self.CARRIES}['f.nested.extra']",
            }
        )

    def test_where_nothing_tells_them_apart_a_lost_key_refuses_and_a_clean_payload_passes(self):
        needs("pydantic")
        from pydantic import BeforeValidator, Field
        from typing_extensions import NotRequired, TypedDict

        class Point(TypedDict):
            x: int

        class Other(TypedDict):
            y: int

        class Aliased(TypedDict):
            x: typing.Annotated[int, Field(validation_alias="X")]

        class Left(TypedDict):
            nested: Point

        class Right(TypedDict):
            nested: Other

        class Wide(TypedDict):
            nested: Point
            more: NotRequired[int]

        class ByX(TypedDict):
            x: typing.Annotated[Point, Field(validation_alias="X")]

        class ByY(TypedDict):
            x: typing.Annotated[Point, Field(validation_alias="Y")]

        checked = typing.Annotated[Point | Other, BeforeValidator(lambda value: value)]
        found = {
            "below the alias of either": self._found({"f": {"Y": {"x": 1, "extra": 2}}}, self._holding(ByX | ByY)),
            "a key lost under a validator": self._found({"f": {"x": 1, "extra": 2}}, self._holding(checked)),
            "a key lost": self._found({"f": {"x": 1, "extra": 2}}, self._holding(Point | Other)),
            "clean": self._found({"f": {"x": 1}}, self._holding(Point | Other)),
            "clean by an alias": self._found({"f": {"X": 1}}, self._holding(Aliased | Other)),
            "a key lost beside an alias": self._found({"f": {"X": 1, "extra": 2}}, self._holding(Aliased | Other)),
            "lost below, declared apart": self._found(
                {"f": {"nested": {"x": 1, "extra": 2}}}, self._holding(Left | Right)
            ),
            "clean below, declared apart": self._found({"f": {"nested": {"y": 1}}}, self._holding(Left | Right)),
            "lost below, declared alike": self._found(
                {"f": {"nested": {"x": 1, "extra": 2}}}, self._holding(Left | Wide)
            ),
            "beside a dict": self._found({"f": {"x": 1, "extra": 2}}, self._holding(Point | dict[str, str])),
            "beside a dict, clean": self._found({"f": {"x": 1}}, self._holding(Point | dict[str, str])),
            "in a list": self._found({"f": [{"x": 1}, {"y": 1, "extra": 2}]}, self._holding(list[Point | Other])),
            "in either list": self._found({"f": [{"x": 1, "extra": 2}]}, self._holding(list[Point] | list[Other])),
            "in either list, clean": self._found({"f": [{"y": 1}]}, self._holding(list[Point] | list[Other])),
            "as a dict's values": self._found(
                {"f": {"k": {"x": 1, "extra": 2}}}, self._holding(dict[str, Point | Other])
            ),
            "in either dict": self._found(
                {"f": {"k": {"x": 1, "extra": 2}}}, self._holding(dict[str, Point] | dict[str, Other])
            ),
            "in a tuple": self._found({"f": [{"x": 1, "extra": 2}, 1]}, self._holding(tuple[Point | Other, int])),
        }
        assert_that(found).is_equal_to(
            {
                "below the alias of either": f"1 {self.CARRIES}['f.x.extra']",
                "a key lost under a validator": f"<f> {self.UNSURE}",
                "a key lost": f"<f> {self.UNSURE}",
                "clean": "passes",
                "clean by an alias": "passes",
                "a key lost beside an alias": f"<f> {self.UNSURE}",
                "lost below, declared apart": f"<f.nested> {self.UNSURE}",
                "clean below, declared apart": "passes",
                "lost below, declared alike": f"1 {self.CARRIES}['f.nested.extra']",
                "beside a dict": f"<f> {self.UNSURE}",
                "beside a dict, clean": "passes",
                "in a list": f"<f[1]> {self.UNSURE}",
                "in either list": f"<f[0]> {self.UNSURE}",
                "in either list, clean": "passes",
                "as a dict's values": f"<f.k> {self.UNSURE}",
                "in either dict": f"<f.k> {self.UNSURE}",
                "in a tuple": f"<f[0]> {self.UNSURE}",
            }
        )

    def test_two_keys_holding_one_object_are_still_two_places(self):
        """One reads the field by its alias and the other by its name, and each drops the key the other reads.  Sent
        one object under both keys, as two equal small ints are, the field is still read from two places, and nothing
        tells which key was dropped."""
        needs("pydantic")
        from pydantic import Field
        from typing_extensions import NotRequired, TypedDict

        class ByAlias(TypedDict):
            first: NotRequired[typing.Annotated[int, Field(alias="firstName")]]
            a: NotRequired[int]

        class ByName(TypedDict):
            first: NotRequired[int]
            b: NotRequired[str]

        large = 10**30
        sent = {
            "two equal small ints": {"firstName": 1, "first": 1},
            "one large int": {"firstName": large, "first": large},
            "two objects": {"firstName": 2, "first": 1},
        }
        found = {
            (label, order): self._found({"f": payload}, self._holding(kind))
            for label, payload in sent.items()
            for order, kind in (("alias first", ByAlias | ByName), ("name first", ByName | ByAlias))
        }
        assert_that(set(found.values())).is_equal_to({f"<f> {self.UNSURE}"})
        assert_that(found).is_length(6)

    def test_a_name_one_typed_dict_ignores_and_another_may_hold_refuses(self):
        """A key one `TypedDict` would have ignored and another, or a dict schema beside them, would have held refuses:
        a record that keeps extras and has no such field, a record that puts the name over its field, as an older
        pydantic does, and a dict schema all hold it.  Nothing in what the dict holds rules one of them out: not a
        default, not a key the dict lacks, not what a validator of the owner's did to it.  Where every one of them
        ignored the key it is named, and where none of them would have had it, only a validator could have put it
        there: it refuses.  A key the one that built the dict dropped and a validator put back, where another would
        have read it, is the documented limit: the dict holds it, and it passes.  Where releases differ, what was
        expected is read off what pydantic built."""
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator
        from typing_extensions import NotRequired, TypedDict

        class Aliased(TypedDict):
            first: NotRequired[typing.Annotated[int, Field(alias="firstName")]]

        class Defaulted(TypedDict):
            first: NotRequired[typing.Annotated[int, Field(default=5, alias="firstName")]]

        class Keeper(TypedDict):
            b: NotRequired[str]

        class Keeping(TypedDict):
            first: NotRequired[typing.Annotated[int, Field(alias="firstName")]]

        class Moving(TypedDict):
            first: typing.Annotated[int, Field(alias="firstName")]

        class Elsewhere(TypedDict):
            out: typing.Annotated[int, Field(alias="extra")]
            required: int

        for keeps in (Keeper, Keeping, Moving):
            keeps.__pydantic_config__ = ConfigDict(extra="allow")

        def grow(cls, value):
            value["grown"] = 0
            return value

        def move(cls, value):
            value["out"] = value.pop("extra")
            return value

        def recreate(cls, value):
            value["grown"] = 0
            return value

        def overwrite(cls, value):
            value["first"] = 0
            return value

        class Only(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]

        class Twin(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]
            o: NotRequired[int]

        class Reads(TypedDict):
            out: typing.Annotated[int, Field(alias="first")]

        class Grows(TypedDict):
            x: typing.Annotated[int, Field(alias="X")]
            grown: int
            missing: int

        def validated(kind, validator):
            body = {"__annotations__": {"f": kind}, "after": field_validator("f", mode="after")(classmethod(validator))}
            return type("Holding", (BaseModel,), body)

        mixed = TestExactnessReachesDataclassesAndTypedDicts.MIXED
        unsure = f"<f> {self.UNSURE}"

        def put_back(built):
            return (
                "<f> cannot be checked: it holds a key none of its declared types reads or keeps,"
                " which code of the owner's may have put"
            )

        not_sent = f"1 {self.CARRIES}['f.first']\n<f.first> is not read: validation reads its field from <firstName>"
        read_from = f"1 {self.CARRIES}['f.first']\n<f.first> is not read: its field was read from <firstName>"
        puts_over = TypeAdapter(Keeping).validate_python({"firstName": 2, "first": 1})["first"] == 1
        alone, beside = {"first": 1}, {"firstName": 2, "first": 1}

        def held(built):
            return mixed if "first" in built else unsure

        cases = {
            "a keeper, beside the alias": (self._holding(Aliased | Keeper), beside, held),
            "a keeper first, beside the alias": (self._holding(Keeper | Aliased), beside, held),
            "a keeper, alone": (self._holding(Aliased | Keeper), alone, held),
            "a keeper first, alone": (self._holding(Keeper | Aliased), alone, held),
            "a dict schema": (self._holding(Aliased | dict[str, int]), alone, held),
            "a dict schema first": (self._holding(dict[str, int] | Aliased), alone, held),
            "a default beside a keeper": (self._holding(Defaulted | Keeper), alone, held),
            "a keeper beside a default": (self._holding(Keeper | Defaulted), alone, held),
            "a default beside one that may put the name over": (
                self._holding(Defaulted | Keeping),
                alone,
                lambda built: unsure if "first" not in built else mixed if puts_over else not_sent,
            ),
            "one that may put the name over beside a default": (
                self._holding(Keeping | Defaulted),
                alone,
                lambda built: unsure if "first" not in built else mixed if puts_over else not_sent,
            ),
            "grown by a validator": (validated(Aliased | Keeper, grow), beside, held),
            "grown by a validator, the keeper first": (validated(Keeper | Aliased, grow), beside, held),
            "an extra moved by a validator": (
                validated(Moving | Elsewhere, move),
                {**beside, "extra": 3},
                lambda built: "passes" if puts_over else read_from,
            ),
            "an extra moved by a validator, the other first": (
                validated(Elsewhere | Moving, move),
                {**beside, "extra": 3},
                lambda built: "passes" if puts_over else read_from,
            ),
            "a dropped key a validator put back": (validated(Only | Twin, recreate), {"X": 2, "grown": 7}, put_back),
            "a dropped key a validator put back, the other first": (
                validated(Twin | Only, recreate),
                {"X": 2, "grown": 7},
                put_back,
            ),
            "a name another reads as its alias": (validated(Aliased | Reads, overwrite), alone, held),
            "a name another reads as its alias, the reader first": (validated(Reads | Aliased, overwrite), alone, held),
            "the limit: a dropped key put back that another reads": (
                validated(Only | Grows, recreate),
                {"X": 2, "grown": 0},
                lambda built: "passes",
            ),
            "the limit, the reader first": (
                validated(Grows | Only, recreate),
                {"X": 2, "grown": 0},
                lambda built: "passes",
            ),
        }
        found, expected = {}, {}
        for label, (holding, payload, verdict) in cases.items():
            found[label] = self._found({"f": dict(payload)}, holding)
            expected[label] = verdict(holding.model_validate({"f": dict(payload)}).f)
        assert_that(found).is_equal_to(expected)

    def test_what_is_declared_beside_them_declares_what_the_dict_holds_as_well(self):
        needs("pydantic")
        from pydantic import Field, Json
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        class Other(TypedDict):
            y: int

        class Record(TypedDict):
            nested: Point
            required: int

        class ByAlias(TypedDict):
            nested: typing.Annotated[Point, Field(validation_alias="X")]
            required: int

        either = self._holding(Record | dict[str, Other])
        alike = self._holding(Record | dict[str, Point])
        found = {
            # the dict took it; the record would have read `nested` from `X`, and the key's own value lost a key
            "a key the record reads from another": self._found(
                {"f": {"nested": {"y": 1, "extra": 2}, "X": {"y": 2}}}, self._holding(ByAlias | dict[str, Other])
            ),
            "a field both declare alike": self._found({"f": {"nested": {"x": 1, "extra": 2}, "required": 1}}, alike),
            # the record lacks a key it requires, so the dict took the payload, the record's alias as a plain key
            "the alias of the one as a key of the other": self._found(
                {"f": {"X": {"x": 1, "extra": 2}}}, self._holding(ByAlias | dict[str, Point])
            ),
            # the dict took it, and dropped the key the record's own field would have kept
            "a field of the one as a value of the other": self._found({"f": {"nested": {"x": 1, "y": 2}}}, either),
            "a key that is no field": self._found({"f": {"k": {"y": 1, "extra": 2}}}, either),
            "the record": self._found({"f": {"nested": {"x": 1, "extra": 2}, "required": 1}}, either),
            "clean as the dict": self._found({"f": {"k": {"y": 1}}}, either),
            "clean as the record": self._found({"f": {"nested": {"x": 1}, "required": 1}}, either),
            "json text, one record": self._found({"f": '{"x": 1, "extra": 2}'}, self._holding(Json[Point | int])),
            "json text, two": self._found({"f": '{"x": 1, "extra": 2}'}, self._holding(Json[Point | Other])),
            "json text, clean": self._found({"f": '{"y": 1}'}, self._holding(Json[Point | Other])),
        }
        assert_that(found).is_equal_to(
            {
                "a key the record reads from another": f"<f> {self.UNSURE}",
                "a field both declare alike": f"1 {self.CARRIES}['f.nested.extra']",
                "the alias of the one as a key of the other": f"1 {self.CARRIES}['f.X.extra']",
                "a field of the one as a value of the other": f"<f.nested> {self.UNSURE}",
                "a key that is no field": f"1 {self.CARRIES}['f.k.extra']",
                "the record": f"<f.nested> {self.UNSURE}",
                "clean as the dict": "passes",
                "clean as the record": "passes",
                "json text, one record": f"1 {self.CARRIES}['f.extra']",
                "json text, two": f"<f> {self.UNSURE}",
                "json text, clean": "passes",
            }
        )

    def test_what_could_mislead_the_choice_between_them_refuses(self):
        needs("pydantic")
        from pydantic import Field, field_validator
        from typing_extensions import NotRequired, TypedDict

        class Inner(TypedDict):
            x: int

        class ByX(TypedDict):
            nested: typing.Annotated[Inner, Field(validation_alias="X")]
            required: int

        class ByY(TypedDict):
            nested: typing.Annotated[Inner, Field(validation_alias="Y")]

        class A(TypedDict):
            tag: typing.Literal["a"]
            x: int

        class B(TypedDict):
            tag: typing.Literal["b"]
            extra: NotRequired[int]

        class Nullable(TypedDict):
            tag: typing.Literal["a"] | None
            x: int

        class Loose(TypedDict):
            tag: str | None
            extra: int

        def retagged(cls, value):
            return {**value, "tag": "b"}

        rewritten = self._holding(A | B, retagged=field_validator("f", mode="after")(classmethod(retagged)))
        found = {
            # the second took it, and dropped the key the first reads the same field from
            "two keys for one field": self._found(
                {"f": {"X": {"x": 1}, "Y": {"x": 1, "extra": 2}}}, self._holding(ByX | ByY)
            ),
            # the first took it and dropped the key, then the validator gave it the tag of the second, which keeps it
            "a tag rewritten after": self._found({"f": {"tag": "a", "x": 1, "extra": 2}}, rewritten),
            "a tag kept": self._found({"f": {"tag": "a", "x": 1, "extra": 2}}, self._holding(A | B)),
            # `None` is a value the first takes for its tag, so it is not ruled out by holding it
            "a tag that may be none": self._found(
                {"f": {"tag": None, "x": 1, "extra": "no number"}}, self._holding(Nullable | Loose)
            ),
            "a tag that is none, clean": self._found({"f": {"tag": None, "x": 1}}, self._holding(Nullable | Loose)),
            "a tag none rules the other out": self._found(
                {"f": {"tag": None, "x": 1, "extra": 2}}, self._holding(Nullable | B)
            ),
        }
        assert_that(found).is_equal_to(
            {
                "two keys for one field": f"<f> {self.UNSURE}",
                "a tag rewritten after": f"<f> {self.UNSURE}",
                "a tag kept": f"1 {self.CARRIES}['f.extra']",
                "a tag that may be none": f"<f> {self.UNSURE}",
                "a tag that is none, clean": "passes",
                "a tag none rules the other out": f"1 {self.CARRIES}['f.extra']",
            }
        )

    def test_a_typed_dict_inside_a_schema_that_does_not_say_what_it_builds_is_one_of_them(self):
        needs("pydantic")
        from pydantic_core import core_schema
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        def chained(inner, kind):
            class Chained:
                @classmethod
                def __get_pydantic_core_schema__(cls, source, handler):
                    return core_schema.chain_schema(
                        [handler.generate_schema(inner), core_schema.no_info_plain_validator_function(kind)]
                    )

            return Chained

        one, many = chained(Point, dict), chained(list[Point], list)
        lost = {"x": 1, "extra": 2}
        # a `TypedDict` two fields declare is held once in the schema, and named where each of them uses it
        twice = type("Twice", (self._holding(one),), {"__annotations__": {"g": Point | None}, "g": None})
        found = {
            "named by a reference": self._found({"f": lost}, twice),
            "a key lost": self._found({"f": lost}, self._holding(one)),
            "clean": self._found({"f": {"x": 1}}, self._holding(one)),
            "in a list": self._found({"f": [{"x": 1}, lost]}, self._holding(list[one])),
            "a list inside it": self._found({"f": [lost]}, self._holding(many)),
            "a list inside it, clean": self._found({"f": [{"x": 1}]}, self._holding(many)),
            "beside a list": self._found({"f": [lost]}, self._holding(list[int] | many)),
        }
        assert_that(found).is_equal_to(
            {
                "named by a reference": f"<f> {self.UNSURE}",
                "a key lost": f"<f> {self.UNSURE}",
                "clean": "passes",
                "in a list": f"<f[1]> {self.UNSURE}",
                "a list inside it": f"<f[0]> {self.UNSURE}",
                "a list inside it, clean": "passes",
                "beside a list": f"<f[0]> {self.UNSURE}",
            }
        )

    def test_what_no_reading_pairs_refuses_where_a_typed_dict_is_declared_for_it(self):
        needs("pydantic")
        from pydantic import field_validator
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        def before(reshape):
            return {"reshaped": field_validator("f", mode="before")(classmethod(lambda cls, value: reshape(value)))}

        keyed = self._holding(dict[str, Point], **before(lambda value: {"k": value[0]}))
        doubled = self._holding(list[Point], **before(lambda value: [value, value]))
        merged = "cannot be checked: validation changed its size, 2 keys became 1"
        reshaped = "cannot be checked: the payload holds a {} where a {} was built"
        found = {
            "a list made a mapping": self._found({"f": [{"x": 1, "extra": 2}]}, keyed),
            "a mapping made two items": self._found({"f": {"x": 1, "extra": 2}}, doubled),
            "a key lost under one of them": self._found(
                {"f": {"1": {"x": 1, "extra": 2}, "01": {"x": 2}}}, self._holding(dict[int, Point])
            ),
            "in the lists under them": self._found(
                {"f": {"1": [{"x": 1, "extra": 2}], "01": []}}, self._holding(dict[int, list[Point]])
            ),
            "plain values": self._found(
                {"f": {"1": {"x": 1}, "01": {"x": 2}}}, self._holding(dict[int, dict[str, int]])
            ),
            "no merge": self._found({"f": {"1": {"x": 1, "extra": 2}, "2": {"x": 2}}}, self._holding(dict[int, Point])),
        }
        assert_that(found).is_equal_to(
            {
                "a list made a mapping": f"<f> {reshaped.format('list', 'mapping')}",
                "a mapping made two items": f"<f> {reshaped.format('dict', 'sequence')}",
                "a key lost under one of them": f"<f> {merged}",
                "in the lists under them": f"<f> {merged}",
                "plain values": "passes",
                "no merge": f"1 {self.CARRIES}['f.1.extra']",
            }
        )

    def test_a_field_its_own_schema_validates_as_a_record_is_walked(self):
        needs("pydantic")
        from pydantic import BaseModel
        from typing_extensions import TypedDict

        class Row(BaseModel):
            x: int

        class Point(TypedDict):
            x: int

        def validated_as(kind):
            class As:
                def __get_pydantic_core_schema__(self, source, handler):
                    return handler.generate_schema(kind)

            return As()

        class Holder(TypedDict):
            inner: typing.Annotated[dict[str, int], validated_as(Point)]

        extra = {"x": 1, "extra": 2}
        found = {
            "a typed dict": self._found(
                {"f": extra}, self._holding(typing.Annotated[dict[str, int], validated_as(Point)])
            ),
            "a model": self._found({"f": extra}, self._holding(typing.Annotated[dict[str, int], validated_as(Row)])),
            "in a typed dict": self._found({"f": {"inner": extra}}, self._holding(Holder)),
            "clean": self._found({"f": {"x": 1}}, self._holding(typing.Annotated[dict[str, int], validated_as(Point)])),
        }
        assert_that(found).is_equal_to(
            {
                "a typed dict": f"1 {self.CARRIES}['f.extra']",
                "a model": f"1 {self.CARRIES}['f.extra']",
                "in a typed dict": f"1 {self.CARRIES}['f.inner.extra']",
                "clean": "passes",
            }
        )

    def test_a_type_that_may_build_a_dict_too_leaves_it_open(self):
        needs("pydantic")
        from pydantic import AfterValidator, PlainValidator
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        def marked(value):
            if not isinstance(value, dict) or "marked" not in value:
                raise ValueError("not marked")
            return dict(value)

        # a type whose schema does not say what it builds: here it takes none of these payloads, the others do
        unknown = typing.Annotated[typing.Any, PlainValidator(marked)]
        sent = {"x": 1, "extra": 2}
        holding = self._holding(Point | unknown)
        assert_that(holding.model_validate({"f": sent}).f).is_equal_to({"x": 1})
        assert_that(self._found({"f": sent}, holding)).is_equal_to(f"<f> {self.UNSURE}")
        assert_that(self._found({"f": {"x": 1}}, holding)).is_equal_to("passes")
        marked_too = {**sent, "marked": 1}
        # which of the two takes a payload both take is pydantic's to say, and it has said both
        kept = holding.model_validate({"f": marked_too}).f == marked_too
        assert_that(self._found({"f": marked_too}, holding)).is_equal_to("passes" if kept else f"<f> {self.UNSURE}")
        either = self._holding(list[Point] | unknown | None)
        assert_that(self._found({"f": [sent]}, either)).is_equal_to(f"<f[0]> {self.UNSURE}")
        assert_that(self._found({"f": [{"x": 1}]}, either)).is_equal_to("passes")
        keyed = self._holding(dict[str, Point] | unknown | None)
        assert_that(self._found({"f": {"k": sent}}, keyed)).is_equal_to(f"<f.k> {self.UNSURE}")
        assert_that(self._found({"f": {"k": {"x": 1}}}, keyed)).is_equal_to("passes")
        # a validator around a type is read as keeping its kind, so a dict beside a list does not open the list
        kept = typing.Annotated[dict[str, int], AfterValidator(lambda value: value)]
        beside = self._holding(list[Point] | kept | None)
        assert_that(self._found({"f": [{"x": 1, "extra": 2}]}, beside)).is_equal_to(f"1 {self.CARRIES}['f[0].extra']")

    def test_without_a_schema_to_read_the_type_declares_as_far_as_it_says(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel
        from typing_extensions import TypedDict

        class Row(BaseModel):
            x: int

        class Point(TypedDict):
            x: int

        class Holding(BaseModel):
            f: Point
            pair: tuple[Point, Row] | None = None

        monkeypatch.setattr(_contract, "_field_nodes", lambda model: {})
        monkeypatch.setattr(_contract, "_READS", {})
        extra = {"x": 1, "extra": 2}
        assert_that(self._found({"f": extra, "pair": [extra, extra]}, Holding)).is_equal_to(
            f"3 {self.CARRIES}['f.extra', 'pair[0].extra', 'pair[1].extra']"
        )

    def test_what_text_and_a_type_variable_stand_for_is_read_off_the_schema(self):
        needs("pydantic")
        from pydantic import BaseModel, Field
        from typing_extensions import TypedDict

        class Row(BaseModel):
            x: int

        class Point(TypedDict):
            x: int

        class Other(TypedDict):
            y: int

        class Named(TypedDict):
            x: typing.Annotated[int, Field(validation_alias="X")]

        class Texted(TypedDict):
            one: "Point"
            named: "Named"
            many: "list[Point]"
            pair: "tuple[Point, Row]"
            ragged: "tuple[Point, ...]"
            keyed: "dict[str, Point]"
            either: "Point | Other | None"
            both: "tuple[Point, Other]"
            row: "Row | None"

        class Holding(BaseModel):
            f: Texted

        item = typing.TypeVar("item")

        class Box(TypedDict, typing.Generic[item]):
            held: item
            many: list[item]

        extra = {"x": 1, "extra": 2}
        clean = {
            "one": {"x": 1},
            "named": {"X": 1},
            "many": [{"x": 1}],
            "pair": [{"x": 1}, {"x": 1}],
            "ragged": [{"x": 1}],
            "keyed": {"k": {"x": 1}},
            "either": None,
            "both": [{"x": 1}, {"y": 1}],
            "row": None,
        }
        found = {
            name: self._found({"f": {**clean, name: sent}}, Holding)
            for name, sent in (
                ("one", extra),
                ("many", [{"x": 1}, extra]),
                ("pair", [extra, extra]),
                ("ragged", [{"x": 1}, extra]),
                ("keyed", {"k": extra}),
                ("either", extra),
                ("both", [extra, {"y": 1, "x": 2}]),
                ("row", extra),
            )
        }
        found["clean"] = self._found({"f": clean}, Holding)
        assert_that(found).is_equal_to(
            {
                "one": f"1 {self.CARRIES}['f.one.extra']",
                "many": f"1 {self.CARRIES}['f.many[1].extra']",
                "pair": f"2 {self.CARRIES}['f.pair[0].extra', 'f.pair[1].extra']",
                "ragged": f"1 {self.CARRIES}['f.ragged[1].extra']",
                "keyed": f"1 {self.CARRIES}['f.keyed.k.extra']",
                "either": f"<f.either> {self.UNSURE}",
                "both": f"2 {self.CARRIES}['f.both[0].extra', 'f.both[1].x']",
                "row": f"1 {self.CARRIES}['f.row.extra']",
                "clean": "passes",
            }
        )
        try:

            class Boxes(BaseModel):
                points: Box[Point]
                others: Box[Other]

        # pydantic before 2.2 builds no schema for a parametrized `TypedDict`
        except TypeError:
            return
        both = {"x": 1, "y": 2}
        sent = {"points": {"held": both, "many": [both]}, "others": {"held": both, "many": [both]}}
        assert_that(self._found(sent, Boxes)).is_equal_to(
            f"4 {self.CARRIES}['others.held.x', 'others.many[0].x', 'points.held.y', 'points.many[0].y']"
        )

    def test_a_list_emptied_where_its_type_is_not_read_refuses(self):
        needs("pydantic")
        from pydantic import BaseModel, BeforeValidator
        from typing_extensions import TypedDict

        class Row(BaseModel):
            x: int

        def none(value):
            return []

        class Texted(TypedDict):
            rows: "typing.Annotated[list[Row], BeforeValidator(none)]"

        class Holding(BaseModel):
            f: Texted

        emptied = "cannot be checked: validation changed its length, 1 items became 0"
        assert_that(self._found({"f": {"rows": [{"x": 1, "extra": 2}]}}, Holding)).is_equal_to(f"<f.rows> {emptied}")

        item = typing.TypeVar("item")

        class Box(TypedDict, typing.Generic[item]):
            many: typing.Annotated[list[item], BeforeValidator(none)]

        try:
            boxed = self._holding(Box[Row])
        # pydantic before 2.2 builds no schema for a parametrized `TypedDict`
        except TypeError:
            return
        # read again as its annotation, the list would be one of anything, and hold whatever was sent
        assert_that(self._found({"f": {"many": [{"x": 1, "extra": 2}]}}, boxed)).is_equal_to(f"<f.many> {emptied}")

    def test_under_a_replay_a_type_that_is_not_read_counts_as_a_choice(self, monkeypatch):
        needs("pydantic")
        from pydantic import BaseModel, field_validator
        from typing_extensions import TypedDict

        class Point(TypedDict):
            x: int

        # a replay reads the text in the module of the class, so the name has to be there
        monkeypatch.setitem(globals(), "_TextedPoint", Point)

        @dataclasses.dataclass
        class Plain:
            point: "_TextedPoint"  # noqa: F821  # put into the module just above

        class Emptied(BaseModel):
            f: list[Plain]

            @field_validator("f", mode="after")
            @classmethod
            def none(cls, value):
                return []

        expected = (
            "<f[0].point> cannot be checked: which of its declared types it became depends on validators not run again"
        )
        # pydantic 2.0 reads the text only in the frame that asks, so no replay is built there
        if _contract._adapter((list[Plain], Emptied, None)) is None:
            expected = "<f> cannot be checked: validation changed its length, 1 items became 0"
        assert_that(self._found({"f": [{"point": {"x": 1}}]}, Emptied)).is_equal_to(expected)

    def test_a_dataclass_and_typed_extras_declared_in_text_are_read_off_the_schema(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict
        from typing_extensions import TypedDict

        class Point(TypedDict):
            # a `TypedDict` takes the config of the model above it, which here keeps extras
            __pydantic_config__ = ConfigDict(extra="ignore")  # ty: ignore[invalid-typed-dict-statement]  # pydantic's hook
            x: int

        @dataclasses.dataclass
        class Plain:
            point: "Point"
            points: "list[Point]"

        class Holding(BaseModel):
            f: Plain

        extra = {"x": 1, "extra": 2}
        assert_that(self._found({"f": {"point": extra, "points": [extra]}}, Holding)).is_equal_to(
            f"2 {self.CARRIES}['f.point.extra', 'f.points[0].extra']"
        )
        try:

            class Open(BaseModel):
                model_config = ConfigDict(extra="allow")
                __pydantic_extra__: "dict[str, Point]"

        # pydantic 2.0 takes no `__pydantic_extra__` written as text
        except TypeError:
            return
        assert_that(self._found({"more": extra}, Open)).is_equal_to(f"1 {self.CARRIES}['more.extra']")
        assert_that(self._found({"more": {"x": 1}}, Open)).is_equal_to("passes")


class TestAnExactFailureCarriesADiff:
    """An exact failure named its finds in the message alone: a reader of ``.diff`` got nothing, and one that wanted
    the value sent under an undeclared key had to parse the path back out of the text."""

    @staticmethod
    def _diff(payload, model, **options):
        with pytest.raises(AssertionFailure) as caught:
            assert_conforms(payload, model, exact=True, **options)
        return caught.value.diff

    @staticmethod
    def _reached(payload, steps):
        for step in steps:
            payload = step.value if step.kind == "item" else payload[step.value]
        return payload

    @staticmethod
    def _models():
        from pydantic import AliasPath, BaseModel, Field

        class Row(BaseModel):
            x: int

        class Order(BaseModel):
            rows: list[Row] = []
            by_name: dict[str, Row] = {}
            sub: Row | None = Field(default=None, alias="theSub")
            far: Row | None = Field(default=None, validation_alias=AliasPath("a", 0))

        return Row, Order

    def test_each_undeclared_field_is_an_entry_holding_what_was_sent_there(self):
        needs("pydantic")
        _, order = self._models()
        payload = {
            "rows": [{"x": 1}, {"x": 2, "extra": [3]}],
            "by_name": {"k": {"x": 1, "more": None}},
            "theSub": {"x": 1, "sub_extra": 4},
            "a": [{"x": 1, "far_extra": 5}],
            "top": {"any": 6},
        }
        diff = self._diff(payload, order)
        assert_that(diff.kind).is_equal_to("match")
        found = {entry.path: [(step.kind, step.value) for step in entry.steps] for entry in diff.entries}
        assert_that(found).is_equal_to(
            {
                "by_name.k.more": [("key", "by_name"), ("key", "k"), ("key", "more")],
                "far.far_extra": [("key", "a"), ("index", 0), ("key", "far_extra")],
                "rows[1].extra": [("key", "rows"), ("index", 1), ("key", "extra")],
                "sub.sub_extra": [("key", "theSub"), ("key", "sub_extra")],
                "top": [("key", "top")],
            }
        )
        assert_that([entry.absent for entry in diff.entries]).is_equal_to(["expected"] * 5)
        assert_that([entry.expected for entry in diff.entries]).is_equal_to([None] * 5)
        for entry in diff.entries:
            assert_that(self._reached(payload, entry.steps)).described_as(entry.path).is_same_as(entry.actual)

    def test_the_entries_name_what_the_message_names_in_its_order(self):
        needs("pydantic")
        row, order = self._models()
        payloads = [
            ({"zeta": 1, "rows": [{"x": 1, "b": 2, "a": 3}], "alpha": 4}, order, {}),
            ([{"x": 1}, {"x": 2, "extra": 3}], row, {"each": True}),
        ]
        for payload, model, options in payloads:
            with pytest.raises(AssertionFailure) as caught:
                assert_conforms(payload, model, exact=True, **options)
            named = str(caught.value).rsplit(": ", 1)[1]
            assert_that(repr([entry.path for entry in caught.value.diff.entries])).is_equal_to(named)
        each = self._diff([{"x": 1}, {"x": 2, "extra": 3}], row, each=True).entries[0]
        assert_that((each.path, each.actual, [tuple(step) for step in each.steps])).is_equal_to(
            ("[1].extra", 3, [("index", 1, None), ("key", "extra", None)])
        )

    def test_a_collection_that_keeps_no_positions_is_stepped_into_by_the_item(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Json

        class Row(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class Listed(BaseModel):
            f: list[Row]

        class Gathered(BaseModel):
            f: frozenset[Json[Row]]

        drifting = {"x": 1, "extra": 2}
        values = {"a": {"x": 0}, "b": drifting}.values()
        entry = self._diff({"f": values}, Listed).entries[0]
        assert_that((entry.path, entry.actual)).is_equal_to(("f[1].extra", 2))
        assert_that([step.kind for step in entry.steps]).is_equal_to(["key", "item", "key"])
        assert_that(entry.steps[1].value).is_same_as(drifting)

        queue = collections.deque([{"x": 0}, drifting])
        entry = self._diff({"f": queue}, Listed).entries[0]
        assert_that([tuple(step) for step in entry.steps]).is_equal_to(
            [("key", "f", None), ("index", 1, None), ("key", "extra", None)]
        )

        text = '{"x": 1, "extra": 2}'
        entry = self._diff({"f": {text}}, Gathered).entries[0]
        assert_that((entry.path, entry.actual)).is_equal_to(("f[0].extra", 2))
        assert_that([tuple(step) for step in entry.steps]).is_equal_to(
            [("key", "f", None), ("item", text, None), ("json", {"x": 1, "extra": 2}, None), ("key", "extra", None)]
        )

    def test_a_find_inside_a_key_or_a_record_or_an_extra_is_stepped_into_as_it_was_read(self):
        needs("pydantic")
        from pydantic import BaseModel, ConfigDict, Field, Json
        from pydantic.dataclasses import dataclass
        from typing_extensions import TypedDict

        class Row(BaseModel):
            model_config = ConfigDict(frozen=True)
            x: int

        class Point(TypedDict):
            row: typing.Annotated[Row, Field(alias="R")]

        @dataclass
        class Pair:
            row: Row

        class Keyed(BaseModel):
            f: dict[Json[Row], int]

        class Typed(BaseModel):
            f: Point

        class Paired(BaseModel):
            f: Pair

        class Open(BaseModel):
            model_config = ConfigDict(extra="allow")
            __pydantic_extra__: dict[str, Row]

        key = '{"x": 1, "extra": 2}'
        drifting = {"x": 1, "deep": [2]}
        cases = {
            "a key": (
                Keyed,
                {"f": {key: 1}},
                "f.extra",
                [("key", "f"), ("item", key), ("json", {"x": 1, "extra": 2}), ("key", "extra")],
            ),
            "a record's alias": (
                Typed,
                {"f": {"R": drifting}},
                "f.row.deep",
                [("key", "f"), ("key", "R"), ("key", "deep")],
            ),
            "a record's own key": (
                Typed,
                {"f": {"R": {"x": 1}, "more": drifting}},
                "f.more",
                [("key", "f"), ("key", "more")],
            ),
            "a dataclass": (
                Paired,
                {"f": {"row": drifting}},
                "f.row.deep",
                [("key", "f"), ("key", "row"), ("key", "deep")],
            ),
            "a dataclass's own key": (
                Paired,
                {"f": {"row": {"x": 1}, "more": 3}},
                "f.more",
                [("key", "f"), ("key", "more")],
            ),
            "an extra": (Open, {"more": drifting}, "more.deep", [("key", "more"), ("key", "deep")]),
        }
        if not isinstance(Open.model_validate({"more": {"x": 1}}).__pydantic_extra__["more"], Row):
            # this pydantic keeps extras as sent, whatever `__pydantic_extra__` declares
            del cases["an extra"]
        found = {}
        for label, (model, payload, _, _) in cases.items():
            (entry,) = self._diff(payload, model).entries
            found[label] = (entry.path, [(step.kind, step.value) for step in entry.steps])
        assert_that(found).is_equal_to({label: (path, steps) for label, (_, _, path, steps) in cases.items()})
        (entry,) = self._diff({"f": {"R": {"x": 1}, "more": drifting}}, Typed).entries
        assert_that(entry.actual).is_same_as(drifting)
        (entry,) = self._diff({"f": {"row": {"x": 1}, "more": drifting}}, Paired).entries
        assert_that(entry.actual).is_same_as(drifting)

    def test_json_text_is_entered_by_a_step_that_holds_what_it_decodes_to(self):
        """The steps led on into what the text decodes to without saying so: a reader that followed them through the
        payload met a string, and one that decoded it had an equal value and not the object the entry holds."""
        needs("pydantic")
        from pydantic import BaseModel, Json

        class Row(BaseModel):
            x: int

        class One(BaseModel):
            f: Json[Row]

        class Twice(BaseModel):
            f: Json[Json[Row]]

        class Many(BaseModel):
            f: Json[list[Row]]

        class Keyed(BaseModel):
            f: Json[dict[int, Row]]

        holds = {"x": 1, "extra": [2]}
        sent = {
            "text": (One, '{"x": 1, "extra": [2]}', "f.extra", ["key", "json", "key"], holds),
            "bytes": (One, b'{"x": 1, "extra": [2]}', "f.extra", ["key", "json", "key"], holds),
            "text that holds the text": (
                Twice,
                '"{\\"x\\": 1, \\"extra\\": [2]}"',
                "f.extra",
                ["key", "json", "key"],
                holds,
            ),
            "a list": (Many, '[{"x": 0}, {"x": 1, "extra": [2]}]', "f[1].extra", ["key", "json", "index", "key"], None),
        }
        for label, (model, text, path, kinds, decoded) in sent.items():
            (entry,) = self._diff({"f": text}, model).entries
            entered = entry.steps[1]
            assert_that((entry.path, [step.kind for step in entry.steps])).described_as(label).is_equal_to(
                (path, kinds)
            )
            assert_that(entered.value).described_as(label).is_equal_to(decoded or [{"x": 0}, holds])
            reached = entered.value
            for step in entry.steps[2:]:
                reached = reached[step.value]
            assert_that(reached).described_as(label).is_same_as(entry.actual)

        merged = '{"1": {"x": 1, "extra": 2}, "01": {"x": 2}}'
        (entry,) = self._diff({"f": merged}, Keyed).entries
        assert_that((entry.path, [step.kind for step in entry.steps])).is_equal_to(("f", ["key", "json"]))
        assert_that(entry.expected).is_equal_to("cannot be checked: validation changed its size, 2 keys became 1")
        assert_that(entry.actual).is_same_as(entry.steps[1].value)
        assert_that(entry.actual).is_equal_to({"1": {"x": 1, "extra": 2}, "01": {"x": 2}})

    def test_what_json_text_holds_is_not_copied_where_the_payload_was_changed_in_place(self):
        needs("pydantic")
        from pydantic import BaseModel, Json, model_validator

        class Row(BaseModel):
            x: int

        class Stripping(BaseModel):
            x: int
            row: Json[Row]

            @model_validator(mode="before")
            @classmethod
            def stripped(cls, value):
                value.pop("extra")["tags"].clear()
                return value

        payload = {"x": 1, "extra": {"tags": ["a"], "opaque": object()}, "row": '{"x": 1, "more": [2]}'}
        found = {entry.path: entry for entry in self._diff(payload, Stripping).entries}
        assert_that(payload).does_not_contain_key("extra")
        assert_that(found["extra"].actual["tags"]).is_equal_to(["a"])
        entered = found["row.more"].steps[1]
        assert_that(entered.kind).is_equal_to("json")
        # the entry keeps the very list the step holds: a copy would be equal, and no longer reached by the steps
        assert_that(found["row.more"].actual).is_same_as(entered.value["more"])

    def test_a_part_that_cannot_be_checked_is_an_entry_holding_the_part_against_the_reason(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator, model_validator
        from pydantic_core import core_schema

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Mixed(BaseModel):
            f: list[A | B]

            @field_validator("f", mode="after")
            @classmethod
            def first_two(cls, value):
                return value[:2]

        class Wrapped(BaseModel):
            x: int

            @model_validator(mode="before")
            @classmethod
            def unwrapped(cls, value):
                return value[0] if isinstance(value, list) else value

        items = [{"x": 1}, {"y": 2}, {"x": 3}]
        with pytest.raises(AssertionFailure) as caught:
            assert_conforms({"f": items}, Mixed, exact=True)
        reason = "cannot be checked: validation changed its length, 3 items became 2"
        assert_that(str(caught.value)).ends_with(f", but <f> {reason}")
        (entry,) = caught.value.diff.entries
        assert_that((entry.path, entry.expected, entry.absent)).is_equal_to(("f", reason, None))
        assert_that(entry.actual).is_same_as(items)
        assert_that([tuple(step) for step in entry.steps]).is_equal_to([("key", "f", None)])

        whole = [{"x": 1}]
        (entry,) = self._diff(whole, Wrapped).entries
        assert_that((entry.path, entry.steps)).is_equal_to((".", ()))
        assert_that(entry.actual).is_same_as(whole)
        assert_that(entry.expected).is_equal_to("cannot be checked: the payload holds a list where a model was built")

        class Own(BaseModel, frozen=True):
            x: int

            def __eq__(self, other):
                return isinstance(other, Own) and other.x == self.x

            def __hash__(self):
                return hash(self.x)

        class Bag(frozenset):
            @classmethod
            def __get_pydantic_core_schema__(cls, source, handler):
                return core_schema.no_info_after_validator_function(
                    cls, core_schema.frozenset_schema(handler.generate_schema(Own))
                )

        class Emptied(BaseModel):
            f: Bag

            @field_validator("f", mode="after")
            @classmethod
            def emptied(cls, value):
                return Bag()

        sent = [{"x": 1}]
        (entry,) = self._diff({"f": sent}, Emptied).entries
        assert_that(entry.expected).is_equal_to(
            "cannot be checked: a set keeps no order to pair its items with the models they became"
        )
        assert_that(entry.actual).is_same_as(sent)

    def test_a_payload_too_deep_to_walk_is_an_entry_at_the_item_that_was_being_walked(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class Rewrapped(BaseModel):
            f: A | list[typing.Any]

            @field_validator("f", mode="before")
            @classmethod
            def rewrapped(cls, value):
                depth = 0
                while isinstance(value, list):
                    depth, value = depth + 1, value[0]
                for _ in range(depth):
                    value = [value]
                return value

        deep: object = 0
        for _ in range(5_000):
            deep = [deep]
        reason = "cannot be checked: it nests deeper than the walk can follow"
        payload = {"f": deep}
        (entry,) = self._diff(payload, Rewrapped).entries
        assert_that((entry.path, entry.steps, entry.expected)).is_equal_to((".", (), reason))
        assert_that(entry.actual).is_same_as(payload)
        (entry,) = self._diff([{"f": [0]}, payload], Rewrapped, each=True).entries
        assert_that((entry.path, [tuple(step) for step in entry.steps])).is_equal_to(("[1]", [("index", 1, None)]))
        assert_that(entry.actual).is_same_as(payload)

    def test_the_entries_of_one_failure_share_the_copies_of_what_they_share(self):
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Emptying(BaseModel):
            x: int

            @model_validator(mode="before")
            @classmethod
            def emptied(cls, value):
                value["a"].clear()
                return value

        shared = [1, 2]
        deep: list = []
        for _ in range(100_000):
            deep = [deep]
        payload = {"x": 1, "a": shared, "b": {"again": shared}, "deep": deep, "opaque": object()}
        entries = {entry.path: entry.actual for entry in self._diff(payload, Emptying).entries}
        assert_that(shared).is_empty()
        assert_that(entries["a"]).is_equal_to([1, 2])
        assert_that(entries["b"]["again"]).is_same_as(entries["a"])
        assert_that(entries["deep"]).is_not_same_as(deep)

    def test_an_entry_keeps_what_was_sent_where_validation_changed_the_payload_in_place(self):
        needs("pydantic")
        from pydantic import BaseModel, model_validator

        class Stripping(BaseModel):
            x: int

            @model_validator(mode="before")
            @classmethod
            def stripped(cls, value):
                if isinstance(value, list):
                    return value.pop()
                dropped = value.pop("extra")
                dropped["tags"].clear()
                for held in dropped.get("pair", ())[1:]:
                    held.clear()
                return value

        # a payload holding what no copy is made of is kept container by container, and its own parts are walked
        opaque = object()
        frozen = (1, (2, opaque))
        extra = {"tags": ["a", "b"], "pair": (1, [2]), "opaque": opaque, frozen: frozen, "mixed": (frozen, [3])}
        extra["itself"] = extra
        payload = {"x": 1, "extra": extra}
        (entry,) = self._diff(payload, Stripping).entries
        assert_that(payload).is_equal_to({"x": 1})
        assert_that((extra["tags"], extra["pair"])).is_equal_to(([], (1, [])))
        kept = entry.actual
        assert_that(kept).is_not_same_as(extra)
        assert_that((kept["tags"], kept["pair"])).is_equal_to((["a", "b"], (1, [2])))
        assert_that(kept["itself"]).is_same_as(kept)
        assert_that(kept["opaque"]).is_same_as(opaque)
        # a tuple nothing under which can be refilled is the payload's own, as a key and as a value
        assert_that(kept[frozen]).is_same_as(frozen)
        assert_that(next(key for key in kept if key == frozen)).is_same_as(frozen)
        assert_that(kept["mixed"]).is_not_same_as(extra["mixed"])
        assert_that(kept["mixed"][0]).is_same_as(frozen)

        whole = [{"x": 1}]
        (entry,) = self._diff(whole, Stripping).entries
        assert_that(whole).is_empty()
        assert_that(entry.actual).is_equal_to([{"x": 1}])

        deep: list = [opaque]
        for _ in range(100_000):
            deep = [deep]
        nested: tuple = ([1],)
        for _ in range(5_000):
            nested = (nested,)
        extra = {"tags": [deep], "pair": (nested, [nested]), "both": (nested, nested)}
        payload = {"x": 1, "extra": extra}
        (entry,) = self._diff(payload, Stripping).entries
        assert_that((extra["tags"], extra["pair"][1])).is_equal_to(([], []))
        reached, depth = entry.actual["tags"][0], 0
        while isinstance(reached, list):
            reached, depth = reached[0], depth + 1
        assert_that((depth, reached)).is_equal_to((100_001, opaque))
        kept, again = entry.actual["pair"]
        assert_that(again).is_length(1)
        assert_that(again[0]).is_same_as(kept)
        assert_that(entry.actual["both"][0]).is_same_as(kept)
        assert_that(entry.actual["both"][1]).is_same_as(kept)
        depth = 0
        while isinstance(kept, tuple):
            kept, depth = kept[0], depth + 1
        assert_that((depth, kept)).is_equal_to((5_001, [1]))

    def test_a_key_named_by_nothing_joins_the_path_as_it_did(self):
        needs("pydantic")
        from pydantic import BaseModel, RootModel

        class Row(BaseModel):
            x: int

        class Rows(BaseModel):
            f: dict[str, list[Row]]

        drifting = [{"x": 1, "": 2, "extra": 3}]
        found = [
            [entry.path for entry in self._diff(payload, model).entries]
            for payload, model in (
                ({"": drifting}, RootModel[dict[str, list[Row]]]),
                ({"": {"": drifting[0]}}, RootModel[dict[str, dict[str, Row]]]),
                ({"f": {"": drifting}}, Rows),
            )
        ]
        assert_that(found).is_equal_to([["[0].", "[0].extra"], ["", "extra"], ["f.[0].", "f.[0].extra"]])

    def test_the_diff_renders_an_undeclared_field_as_what_only_the_payload_holds(self):
        needs("pydantic")
        from pydantic import BaseModel, field_validator

        class A(BaseModel):
            x: int

        class B(BaseModel):
            y: int

        class Halved(BaseModel):
            f: list[A | B]

            @field_validator("f", mode="after")
            @classmethod
            def halved(cls, value):
                return value[:2]

        drifting = self._diff({"x": 1, "extra": [2]}, A)
        assert_that(str(drifting)).is_equal_to("diff (match):\n  extra: - [2]")
        refused = self._diff({"f": [{"x": 1}, {"y": 2}, {"x": 3}]}, Halved)
        assert_that(str(refused)).is_equal_to(
            "diff (match):\n  f: expected cannot be checked: validation changed its length, 3 items became 2,"
            " but was [{'x': 1}, {'y': 2}, {'x': 3}]"
        )

    def test_a_soft_failure_carries_the_same_diff(self):
        needs("pydantic")
        row, _ = self._models()
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_conforms({"x": 1, "extra": 2}, row, exact=True)
        (failure,) = caught.value.failures
        assert_that([(entry.path, entry.actual) for entry in failure.diff.entries]).is_equal_to([("extra", 2)])


class TestExactnessWalksOnlyWhatCanHoldAModel:
    """A field whose type is made of plain parts, and a part pydantic kept as the payload's own object, hold nothing
    built from the payload, so `exact=True` does not walk them: a 300 by 300 grid of floats walked item by item cost
    forty times its validation, and a deep list under `Any` overflowed the stack."""

    @staticmethod
    def _model():
        needs("pydantic")
        from pydantic import BaseModel

        class A(BaseModel):
            x: int

        return A

    def test_which_types_can_hold_a_model(self):
        model = self._model()
        from pydantic import Json

        class Point(typing.NamedTuple):
            a: model

        class Shape(typing.TypedDict):
            a: model

        plain = {
            "a bare list": list,
            "a grid": list[list[float]],
            "a JSON object": dict[str, typing.Any],
            "a list of objects": list[object],
            "an iterable of ints": collections.abc.Iterable[int],
            "a tuple of ints": tuple[int, ...],
            "a literal": typing.Literal[1, "a"],
            "an annotated list": typing.Annotated[list[int], "meta"],
            "optional text": str | None,
            "an abstract mapping": collections.abc.Mapping[str, collections.abc.Sequence[bytes]],
        }
        holding = {
            "Any": typing.Any,
            "object": object,
            "optional Any": typing.Annotated[typing.Any | None, "meta"],
            "a model": model,
            "an optional model": model | None,
            "a model read from JSON": Json[model],
            "a model deep inside": dict[str, list[tuple[int, model]]],
            "a named tuple": Point,
            "a typed dict": Shape,
            "a type variable": typing.TypeVar("T"),
            "an unresolved name": "A",
        }
        verdicts = {name: _contract._may_hold_model(annotation) for name, annotation in {**plain, **holding}.items()}
        assert_that(verdicts).is_equal_to({**dict.fromkeys(plain, False), **dict.fromkeys(holding, True)})

    def test_json_text_inside_json_text_is_read_to_the_end(self):
        twice = '"{\\"x\\": 1}"'
        assert_that(_contract._holds([twice], _contract._is_mapping, read_text=True)).is_true()

    def test_a_field_that_cannot_hold_a_model_is_not_walked(self, monkeypatch):
        a = self._model()
        from pydantic import BaseModel, RootModel

        class Grid(BaseModel):
            cells: list[list[float]]
            tags: list[str]
            sub: a

        walked = []
        walk = _contract._value_drift
        monkeypatch.setattr(_contract, "_value_drift", lambda *args: walked.append(_placed(args[2])[0]) or walk(*args))
        assert_conforms({"cells": [[1.0, 2.0]], "tags": ["t"], "sub": {"x": 1}}, Grid, exact=True)
        assert_conforms([[1.0, 2.0]], RootModel[list[list[float]]], exact=True)
        assert_that(walked).is_equal_to(["sub"])

    def test_a_deep_part_kept_as_given_is_not_walked(self):
        a = self._model()
        deep: object = 0
        for _ in range(5_000):
            deep = [deep]
        loose = type("Loose", (a.__base__,), {"__annotations__": {"f": typing.Any}})
        either = type("Either", (a.__base__,), {"__annotations__": {"f": a | list[typing.Any]}})
        for model in (loose, either):
            assert_that(assert_conforms({"f": deep}, model, exact=True).value.f).is_length(1)

    def test_a_model_a_validator_put_under_any_is_walked(self):
        a = self._model()
        from pydantic import BaseModel, field_validator

        class Built(BaseModel):
            f: typing.Any

            @field_validator("f", mode="before")
            @classmethod
            def built(cls, value):
                return a.model_validate(value)

        assert_that(_drift({"f": {"x": 1, "extra": 2}}, Built)).is_equal_to(["f.extra"])


class TestAliasesOnDuckTypedModels:
    """pydantic mirrors `Field(alias=...)` into `validation_alias`, so on a pydantic model the two
    collectors always agree and neither can be tested apart from the other.  Duck-typed models can
    carry one without the other, which is what the two `getattr` defaults exist for."""

    @staticmethod
    def _model(**field_attrs):
        info = type("DuckField", (), {"annotation": int, **field_attrs})()
        return type("DuckModel", (), {"model_fields": {"id": info}})

    def test_an_alias_alone_is_where_the_field_is_read(self):
        model = self._model(alias="ID", validation_alias=None)
        assert_that(_paths(contract_drift({"ID": 1, "more": 2}, model()))).is_equal_to(["more"])
        assert_that(_paths(contract_drift({"ID": 1, "id": 2}, model()))).is_equal_to(["id"])

    def test_a_validation_alias_alone_is_where_the_field_is_read(self):
        model = self._model(alias=None, validation_alias="incoming")
        assert_that(_paths(contract_drift({"incoming": 1, "more": 2}, model()))).is_equal_to(["more"])
        assert_that(_paths(contract_drift({"incoming": 1, "id": 2}, model()))).is_equal_to(["id"])

    def test_a_field_carrying_neither_attribute_is_read_by_its_name(self):
        assert_that(_paths(contract_drift({"id": 1, "more": 2}, self._model()()))).is_equal_to(["more"])


class TestDriftOnDuckTypedModels:
    """The module is duck-typed on ``model_fields`` and never imports pydantic, so a class exposing
    that attribute without pydantic's ``model_config`` is a supported input, not a broken one."""

    def test_a_model_without_model_config_reports_drift(self):
        class DuckField:
            alias = None
            validation_alias = None
            annotation = int

        class DuckModel:
            model_fields: typing.ClassVar = {"id": DuckField()}

        assert_that(_paths(contract_drift({"id": 1, "surprise": 2}, DuckModel()))).is_equal_to(["surprise"])


class TestStructureWalkPathsAndCycles:
    """The walk builds a dotted path as it descends and refuses to follow a cycle.  Every mismatch
    below was reachable but unasserted, so the path could be built wrong, the cycle guard keyed on one
    side, or a `continue` turned into a `break`, without a test noticing."""

    def test_a_cycle_on_both_sides_is_marked_not_followed(self):
        value = {"a": 1}
        value["self"] = value
        spec = {"a": 1}
        spec["self"] = spec
        assert_that(_texts(StructureMatcher(spec).collect_mismatches(value))).is_equal_to(
            [("self", "<circular ref>", "<circular ref>")]
        )

    def test_a_missing_nested_key_carries_its_full_path(self):
        mismatches = StructureMatcher({"a": {"b": 1}}).collect_mismatches({"a": {}})
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["a.b"])

    def test_every_missing_key_is_reported_not_just_the_first(self):
        # the loop continues past a missing key; breaking instead would report one and hide the rest
        mismatches = StructureMatcher({"a": 1, "b": 2}).collect_mismatches({})
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["a", "b"])

    def test_a_non_dict_where_a_dict_was_specified_reports_the_value(self):
        assert_that(_texts(StructureMatcher({"a": {"b": 1}}).collect_mismatches({"a": 5}))).is_equal_to(
            [("a", 5, "a mapping")]
        )

    def test_a_matcher_whose_probe_raises_counts_as_a_mismatch(self):
        class Boom:
            def __eq__(self, other):
                raise TypeError("boom")

            __hash__ = object.__hash__

        boom = Boom()
        mismatches = StructureMatcher({"a": match.greater_than(1)}).collect_mismatches({"a": boom})
        assert_that([(path.text, expected) for path, _, expected in mismatches]).is_equal_to(
            [("a", "a value greater than <1>")]
        )
        assert_that(mismatches[0][1]).is_same_as(boom)

    def test_a_cycle_needs_both_sides_to_repeat(self):
        # keyed on the pair: on one side alone, a spec revisiting a value under a different sub-spec stops looking
        inner = {"n": 1}
        value = {"a": inner, "b": inner}
        mismatches = StructureMatcher({"a": {"n": 1}, "b": {"n": 2}}).collect_mismatches(value)
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["b.n"])

    def test_a_value_revisited_against_a_different_sub_spec_is_still_compared(self):
        # keyed on the pair. On the value alone, a cyclic payload against a finite spec reports a false
        # circular reference the second time a sub-value comes up, and the real mismatch is never reached.
        inner = {"n": 1}
        inner["a"] = inner
        mismatches = StructureMatcher({"a": {"a": {"n": 2}}}).collect_mismatches({"a": inner})
        assert_that(_texts(mismatches)).is_equal_to([("a.a.n", 1, "<2>")])

    def test_the_mismatch_detail_comes_from_the_matcher(self):
        # wording that differs from the generic "was <...>", or the two branches would render identically
        described = StructureMatcher({"a": match.is_even()}).describe_mismatch({"a": "x"})
        assert_that(described).is_equal_to(
            "at <a>: expected an even integer, but was <'x'> of type <str>, not an integer"
        )


class TestMatchesStructureAcceptsAnyMapping:
    """Every other dict assertion accepts a mapping that is not a `dict` subclass; this one refused
    them.  `MappingProxyType`, a `collections.abc.Mapping`, and 3.15's `frozendict` all landed on the
    same `isinstance(..., dict)` gate while `is_equal_to` and `contains_key` walked them happily."""

    class _Mapping(collections.abc.Mapping):
        def __init__(self, data):
            self._data = data

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    def test_a_mapping_proxy_is_matched(self):
        assert_that(types.MappingProxyType({"a": 1})).matches_structure({"a": match.is_positive()})

    def test_a_custom_mapping_is_matched(self):
        assert_that(self._Mapping({"a": 1})).matches_structure({"a": match.is_positive()})

    def test_a_nested_mapping_is_walked(self):
        value = types.MappingProxyType({"outer": self._Mapping({"inner": 1})})
        assert_that(value).matches_structure({"outer": {"inner": match.is_positive()}})

    def test_a_mismatch_inside_a_mapping_keeps_its_path(self):
        value = types.MappingProxyType({"outer": self._Mapping({"inner": -1})})
        mismatches = StructureMatcher({"outer": {"inner": match.is_positive()}}).collect_mismatches(value)
        assert_that([path.text for path, _, _ in mismatches]).is_equal_to(["outer.inner"])

    def test_a_non_mapping_is_still_refused(self):
        with pytest.raises(TypeError, match="mapping, a pydantic-style model, or an attrs instance"):
            assert_that([1, 2]).matches_structure({"a": 1})

    def test_the_matcher_form_declines_a_non_mapping(self):
        assert_that(match.structure({"a": 1}).matches(5)).is_false()


class TestALeafThatPrintsTheSame:
    """An id a payload holds as text read ``expected <7>, but was <7>``."""

    def test_is_told_apart_by_class(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"id": 7}).matches_structure({"id": "7"})
        assert_that(caught.value._message).ends_with("at <id>: expected <7:str>, but was <7:int>.")
        assert_that(match.structure({"id": 7}).describe_mismatch({"id": "7"})).is_equal_to(
            "at <id>: expected <7:int>, but was <7:str>"
        )

    def test_one_that_prints_otherwise_is_printed_as_it_was(self):
        assert_that(match.structure({"id": 7}).describe_mismatch({"id": 8})).is_equal_to(
            "at <id>: expected <7>, but was <8>"
        )

    def test_a_value_where_a_mapping_was_expected_is_printed_as_it_is(self):
        assert_that(match.structure({"a": {"b": 1}}).describe_mismatch({"a": 5})).is_equal_to(
            "at <a>: expected a mapping, but was <5>"
        )
