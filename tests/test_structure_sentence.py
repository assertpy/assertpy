"""The sentence of a failed `matches_structure`: the value and the spec with what matched left out.

A spec names a few keys of a record that holds many.  Printed whole, the record and the spec stood ahead of the one
leaf the failure is about: 2 658 characters for one wrong field of forty-two.  The sentence keeps the keys on the way
to a mismatch and writes ``..`` for the rest, as a failed `is_equal_to` does.  What the failure holds does not change.
"""

from __future__ import annotations

import ast
import collections
import collections.abc
import re
import types

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, errors, match
from assertpy.matchers import BaseMatcher, StructureMatcher
from tests.optional import needs

_RECORD = {
    "id": 7,
    "name": "Ann",
    "email": "a@b",
    "profile": {"city": "Oslo", "zip": "0150", "street": "x"},
    "tags": ["a"],
}
_WHOLE = str(_RECORD)


def _failed(value: object, spec: dict) -> AssertionFailure:
    with pytest.raises(AssertionFailure) as caught:
        assert_that(value).matches_structure(spec)
    return caught.value


def _raised(value: object, spec: dict) -> Exception:
    """Whatever the assertion raised, a failure of its own or not."""
    try:
        assert_that(value).matches_structure(spec)
    except Exception as raised:
        return raised
    raise AssertionError("the spec matched")


def _sentence(value: object, spec: dict) -> str:
    return _failed(value, spec)._message.split("\n")[0]


def _value_said(value: object, spec: dict) -> str:
    found = re.match(r"Expected <(.*)> to match structure ", _sentence(value, spec))
    assert found is not None
    return found[1]


def _spec_said(value: object, spec: dict) -> str:
    return _sentence(value, spec).split(" to match structure ", 1)[1].split(", but ", 1)[0]


class _CountedKey:
    """A key that counts what a lookup of it runs."""

    hashed = 0
    compared = 0

    def __hash__(self) -> int:
        _CountedKey.hashed += 1
        return 1

    def __eq__(self, other: object) -> bool:
        _CountedKey.compared += 1
        return self is other

    def __repr__(self) -> str:
        return "Counted()"


def _counts_of(run: collections.abc.Callable[[], object]) -> tuple[int, int]:
    _CountedKey.hashed = _CountedKey.compared = 0
    run()
    return _CountedKey.hashed, _CountedKey.compared


class _Never(BaseMatcher):
    """A matcher that fails and prints nothing of what it was asked about."""

    def matches(self, value: object) -> bool:
        return False

    def describe(self) -> str:
        return "nothing"

    def describe_mismatch(self, value: object) -> str:
        return "was something"


class _Shrinking:
    """A leaf whose repr takes a key out of the dict that holds it."""

    def __init__(self, holder: dict) -> None:
        self._holder = holder

    def __repr__(self) -> str:
        del self._holder[next(key for key in self._holder if key != "leaf")]
        return "Shrinking()"


class _Text(str):
    __slots__ = ()


class _Spec(dict):
    pass


class _Held(dict):
    pass


class _Keyed(collections.abc.Mapping):
    def __init__(self, held: dict) -> None:
        self._held = held

    def __getitem__(self, key: object) -> object:
        return self._held[key]

    def __iter__(self):
        return iter(self._held)

    def __len__(self) -> int:
        return len(self._held)

    def __repr__(self) -> str:
        return f"Keyed({self._held})"


class _Dumped:
    """A record by the one thing a model is known by here: it hands out a dict of itself."""

    dumps = 0

    def __init__(self, fields: dict) -> None:
        self._fields = fields

    def model_dump(self) -> dict:
        _Dumped.dumps += 1
        return dict(self._fields)

    def __repr__(self) -> str:
        return "Dumped(whole)"


class TestTheSentenceLeavesOutWhatMatched:
    def test_one_wrong_leaf(self):
        assert_that(_sentence(_RECORD, {"id": match.is_instance_of(str), "name": "Ann"})).is_equal_to(
            "Expected <{'id': 7, ..}> to match structure {id: an instance of <str>, ..},"
            " but at <id>: expected an instance of <str>, but was <7> of type <int>."
        )

    def test_a_leaf_below_is_reached_through_the_key_it_is_under(self):
        assert_that(_sentence(_RECORD, {"name": "Ann", "profile": {"city": "Paris", "zip": "0150"}})).is_equal_to(
            "Expected <{.., 'profile': {'city': 'Oslo', ..}, ..}> to match structure"
            " {.., profile: {city: <Paris>, ..}}, but at <profile.city>: expected <Paris>, but was <Oslo>."
        )

    def test_every_mismatch_stands_and_the_first_is_named(self):
        assert_that(_sentence(_RECORD, {"id": 8, "profile": {"city": "Paris"}, "name": "Ann"})).is_equal_to(
            "Expected <{'id': 7, .., 'profile': {'city': 'Oslo', ..}, ..}> to match structure"
            " {id: <8>, profile: {city: <Paris>}, ..}, but at <id>: expected <8>, but was <7>."
        )

    def test_a_key_the_value_does_not_hold_leaves_nothing_of_it_standing(self):
        assert_that(_sentence(_RECORD, {"name": "Ann", "phone": match.is_non_empty_string()})).is_equal_to(
            "Expected <{..}> to match structure {.., phone: a non-empty string}, but missing key <phone>."
        )

    def test_a_key_not_held_below_leaves_the_key_above_it(self):
        assert_that(_sentence(_RECORD, {"profile": {"country": "NO"}})).is_equal_to(
            "Expected <{.., 'profile': {..}, ..}> to match structure"
            " {profile: {country: <NO>}}, but missing key <profile.country>."
        )

    @pytest.mark.parametrize(
        ("value", "spec", "said"),
        [
            ({"id": 7}, {"id": 8}, "{'id': 7}"),
            ({}, {"id": 8}, "{}"),
            ({"a": 0, "b": 0, "c": 0}, {"a": 1}, "{'a': 0, ..}"),
            ({"a": 0, "b": 0, "c": 0}, {"b": 1}, "{.., 'b': 0, ..}"),
            ({"a": 0, "b": 0, "c": 0}, {"c": 1}, "{.., 'c': 0}"),
            ({"a": 0, "b": 0, "c": 0}, {"a": 1, "c": 1}, "{'a': 0, .., 'c': 0}"),
            ({"a": 0, "b": 0, "c": 0}, {"c": 1, "a": 1}, "{'a': 0, .., 'c': 0}"),
        ],
    )
    def test_the_mark_stands_where_keys_were_left_out_and_nowhere_else(self, value, spec, said):
        assert_that(_value_said(value, spec)).is_equal_to(said)

    def test_the_spec_keeps_its_own_order(self):
        assert_that(_spec_said({"a": 0, "b": 0, "c": 0}, {"c": 1, "b": 0, "a": 1})).is_equal_to("{c: <1>, .., a: <1>}")

    def test_a_value_that_is_no_mapping_where_the_spec_goes_on_is_printed_there(self):
        assert_that(_sentence(_RECORD, {"tags": {"first": "a"}, "name": "Ann"})).is_equal_to(
            "Expected <{.., 'tags': ['a']}> to match structure {tags: {first: <a>}, ..},"
            " but at <tags>: expected a mapping, but was <['a']>."
        )

    def test_a_dict_held_against_a_leaf_of_the_spec_is_printed_whole(self):
        assert_that(_value_said(_RECORD, {"profile": "x", "name": "Ann"})).is_equal_to(
            "{.., 'profile': {'city': 'Oslo', 'zip': '0150', 'street': 'x'}, ..}"
        )

    def test_a_structure_matcher_below_keeps_its_words(self):
        spec = {"name": "Ann", "profile": match.structure({"city": "Paris", "zip": "0150"})}
        assert_that(_spec_said(_RECORD, spec)).is_equal_to(
            "{.., profile: a mapping matching structure {city: <Paris>, ..}}"
        )
        assert_that(_value_said(_RECORD, spec)).is_equal_to("{.., 'profile': {'city': 'Oslo', ..}, ..}")

    def test_a_matcher_that_failed_is_described_whole(self):
        spec = {"name": "Ann", "tags": match.each_item(match.structure({"id": 1, "kind": "x"}))}
        assert_that(_spec_said(_RECORD, spec)).is_equal_to(
            "{.., tags: each item matching a mapping matching structure {id: <1>, kind: <x>}}"
        )

    def test_past_five_the_rest_are_counted(self):
        held = {f"k{i}": i for i in range(9)}
        assert_that(_sentence(held, {f"k{i}": -1 for i in range(8)})).is_equal_to(
            "Expected <{'k0': 0, 'k1': 1, 'k2': 2, 'k3': 3, 'k4': 4, ... and 3 more}> to match structure"
            " {k0: <-1>, k1: <-1>, k2: <-1>, k3: <-1>, k4: <-1>, ... and 3 more},"
            " but at <k0>: expected <-1>, but was <0>."
        )

    def test_one_wrong_field_of_a_wide_record_is_a_short_sentence(self):
        wide = {f"field_{i:02d}": f"value number {i} of the record" for i in range(40)}
        wide["count"] = {"clicks": "12", "positive_feedback": 3}
        spec: dict = {f"field_{i:02d}": match.is_type_of(str) for i in range(20)}
        spec["count"] = {"clicks": match.is_type_of(int), "positive_feedback": match.is_type_of(int)}
        sentence = _sentence(wide, spec)
        assert_that(sentence).is_equal_to(
            "Expected <{.., 'count': {'clicks': '12', ..}}> to match structure"
            " {.., count: {clicks: exactly type <int>, ..}}, but at <count.clicks>: expected exactly type <int>,"
            " but was <12> of type <str>."
        )

    def test_a_long_leaf_is_cut_and_whole_where_whole_values_are_asked_for(self, monkeypatch):
        held = {"page": 1, "items": list(range(3000))}
        cut = _value_said(held, {"items": [1]})
        assert_that(cut).starts_with("{.., 'items': [0, 1, 2,").ends_with("more chars)")
        assert_that(len(cut)).is_less_than(4100)
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        assert_that(_value_said(held, {"items": [1]})).is_equal_to(f"{{.., 'items': {list(range(3000))}}}")

    def test_what_matched_stays_out_where_whole_values_are_asked_for(self, monkeypatch):
        monkeypatch.setattr(errors, "_WHOLE_VALUES", True)
        assert_that(_value_said(_RECORD, {"id": 8})).is_equal_to("{'id': 7, ..}")

    def test_a_leaf_whose_repr_takes_a_key_out_of_the_value_still_fails_as_itself(self):
        held: dict = {"a": 1, "b": 2, "c": 3, "d": 4}
        held["leaf"] = _Shrinking(held)
        raised = _raised(held, {"leaf": _Never(), "d": 4})
        assert_that(type(raised)).is_same_as(AssertionFailure)
        assert_that(str(raised).split("\n")[0]).is_equal_to(
            "Expected <{.., 'leaf': Shrinking()}> to match structure {leaf: nothing, ..},"
            " but at <leaf>: expected nothing, but was something."
        )

    def test_a_value_that_holds_itself_is_followed_as_far_as_the_spec_goes(self):
        held: dict = {"a": {"name": "x"}}
        held["a"]["self"] = held["a"]
        assert_that(_value_said(held, {"a": {"name": "x", "self": {"name": "y"}}})).is_equal_to(
            "{'a': {.., 'self': {'name': 'x', ..}}}"
        )


class TestARecordIsWrittenAsItsClass:
    def test_a_model_is_named_and_its_fields_are_written_as_fields(self):
        pydantic = needs("pydantic")

        class Address(pydantic.BaseModel):
            city: str
            zip: str

        class Customer(pydantic.BaseModel):
            id: int
            name: str
            address: Address
            tags: list[str]

        held = Customer(id=1, name="Ann", address=Address(city="Oslo", zip="0150"), tags=["a"])
        assert_that(_sentence(held, {"name": "Ann", "address": {"city": "Paris"}})).is_equal_to(
            "Expected <Customer(.., address={'city': 'Oslo', ..}, ..)> to match structure"
            " {.., address: {city: <Paris>}}, but at <address.city>: expected <Paris>, but was <Oslo>."
        )

    def test_an_attrs_instance_is_named_and_a_record_it_holds_is_printed_whole(self):
        attrs = needs("attrs")

        @attrs.define
        class Point:
            x: int
            y: int

        @attrs.define
        class Line:
            start: Point
            end: Point
            name: str

        assert_that(_value_said(Line(Point(1, 2), Point(3, 4), "l"), {"name": "l", "end": {"x": 9}})).is_equal_to(
            "Line(.., end=Point(x=3, y=4), ..)"
        )

    def test_a_record_is_read_once(self):
        _Dumped.dumps = 0
        assert_that(_value_said(_Dumped({"id": 7, "name": "Ann"}), {"id": 8})).is_equal_to("_Dumped(id=7, ..)")
        assert_that(_Dumped.dumps).is_equal_to(1)

    @pytest.mark.parametrize("key", [1, "x=1, y", "content-type", "a b", "line\nbreak", "", "1st", "a.b"], ids=repr)
    def test_a_record_with_a_key_to_show_that_is_no_name_is_printed_whole(self, key):
        assert_that(_value_said(_Dumped({key: "a", "other": "b"}), {key: "z"})).is_equal_to("Dumped(whole)")

    @pytest.mark.parametrize("key", ["name", "_private", "class", "имя", "x1"])
    def test_a_name_is_written_as_a_field_a_keyword_among_them(self, key):
        assert_that(_value_said(_Dumped({key: "a", "other": "b"}), {key: "z"})).is_equal_to(f"_Dumped({key}='a', ..)")

    def test_a_key_that_is_no_name_and_matched_does_not_cost_the_record_its_fields(self):
        assert_that(_value_said(_Dumped({"content-type": "a", "id": 7}), {"id": 8})).is_equal_to("_Dumped(.., id=7)")

    def test_a_record_that_hands_out_no_dict_is_printed_whole(self):
        class Odd:
            def model_dump(self) -> object:
                return types.MappingProxyType({"id": 7, "name": "Ann"})

            def __repr__(self) -> str:
                return "Odd(whole)"

        assert_that(_value_said(Odd(), {"id": 8})).is_equal_to("Odd(whole)")


class TestWhatCannotBeReadThatWayIsPrintedWhole:
    @pytest.mark.parametrize(
        "held",
        [
            types.MappingProxyType(_RECORD),
            collections.OrderedDict(_RECORD),
            _Held(_RECORD),
            _Keyed(_RECORD),
            collections.ChainMap(_RECORD),
        ],
        ids=["proxy", "ordered", "subclass", "mapping", "chain"],
    )
    def test_a_mapping_that_is_no_exact_dict(self, held):
        assert_that(_value_said(held, {"id": 8, "name": "Ann"})).is_equal_to(str(held))
        assert_that(_spec_said(held, {"id": 8, "name": "Ann"})).is_equal_to("{id: <8>, ..}")

    def test_a_dict_below_that_is_no_exact_dict_is_printed_whole_there(self):
        held = {"id": 7, "profile": collections.OrderedDict(city="Oslo", zip="0150")}
        assert_that(_value_said(held, {"profile": {"city": "Paris"}})).is_equal_to(
            f"{{.., 'profile': {held['profile']!r}}}"
        )

    @pytest.mark.parametrize(
        "key", [_Text("flag"), (1, 2), frozenset({1}), 1j], ids=["text", "tuple", "set", "complex"]
    )
    def test_a_value_with_a_key_that_is_none_of_the_plain_kinds(self, key):
        held = {"id": 7, "name": "Ann", key: 1}
        assert_that(_value_said(held, {"id": 8})).is_equal_to(str(held))

    @pytest.mark.parametrize("key", ["id", 1, True, 1.5, b"id", None], ids=repr)
    def test_each_of_the_plain_kinds_is_a_key_that_is_read(self, key):
        assert_that(_value_said({key: 7, "other": 1}, {key: 8})).is_equal_to(f"{{{key!r}: 7, ..}}")

    def test_a_key_of_a_class_of_its_own_in_the_value_is_asked_nothing_more_than_the_walk_asked(self):
        held = {"id": 7, "name": "Ann", _CountedKey(): 1}
        spec = {"id": 8, "name": "Ann"}
        walked = _counts_of(lambda: StructureMatcher(spec).walk_mismatches(held))
        assert_that(_counts_of(lambda: _failed(held, spec))).is_equal_to(walked)
        assert_that(_value_said(held, spec)).is_equal_to(str(held))

    def test_a_key_of_a_class_of_its_own_in_the_spec_is_asked_nothing_more_than_the_walk_asked(self):
        key = _CountedKey()
        held = {"id": 7, "name": "Ann", key: 1}
        spec = {key: 2, "name": "Ann"}
        walked = _counts_of(lambda: StructureMatcher(spec).walk_mismatches(held))
        assert_that(_counts_of(lambda: _failed(held, spec))).is_equal_to(walked)
        assert_that(_value_said(held, spec)).is_equal_to(str(held))
        assert_that(_spec_said(held, spec)).is_equal_to("{Counted(): <2>, ..}")

    def test_a_key_of_a_class_of_its_own_the_spec_asks_for_and_the_value_lacks(self):
        held = {"id": 7, "name": "Ann"}
        spec = {_CountedKey(): 2, "name": "Ann"}
        walked = _counts_of(lambda: StructureMatcher(spec).walk_mismatches(held))
        assert_that(_counts_of(lambda: _failed(held, spec))).is_equal_to(walked)
        assert_that(_value_said(held, spec)).is_equal_to(str(held))

    def test_a_key_of_the_spec_that_is_a_text_of_a_class_of_its_own(self):
        assert_that(_value_said(_RECORD, {_Text("id"): 8, "name": "Ann"})).is_equal_to(_WHOLE)

    def test_a_spec_that_is_no_exact_dict_is_described_whole(self):
        assert_that(_sentence(_RECORD, _Spec(id=8, name="Ann"))).is_equal_to(
            "Expected <{'id': 7, ..}> to match structure {id: <8>, name: <Ann>},"
            " but at <id>: expected <8>, but was <7>."
        )

    def test_a_spec_below_that_is_no_exact_dict_is_described_whole_there(self):
        spec = {"name": "Ann", "profile": _Spec(city="Paris", zip="0150")}
        assert_that(_spec_said(_RECORD, spec)).is_equal_to("{.., profile: {city: <Paris>, zip: <0150>}}")
        assert_that(_value_said(_RECORD, spec)).is_equal_to("{.., 'profile': {'city': 'Oslo', ..}, ..}")

    def test_a_structure_matcher_of_a_class_of_its_own_describes_itself(self):
        class Named(StructureMatcher):
            def describe(self) -> str:
                return "a profile"

        spec = {"name": "Ann", "profile": Named({"city": "Paris", "zip": "0150"})}
        assert_that(_spec_said(_RECORD, spec)).is_equal_to("{.., profile: a profile}")


class TestTheFailureHoldsWhatItHeld:
    def test_the_value_the_spec_and_every_mismatch(self):
        spec = {"id": 8, "profile": {"city": "Paris"}, "name": "Ann"}
        failure = _failed(_RECORD, spec)
        assert_that(failure.actual).is_same_as(_RECORD)
        assert_that(failure.expected).is_same_as(spec)
        assert failure.diff is not None
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["id", "profile.city"])
        assert_that([(entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [(7, "<8>"), ("Oslo", "<Paris>")]
        )

    def test_the_line_under_the_sentence_still_follows_it(self):
        lines = _failed(_RECORD, {"id": int, "name": "Ann"})._message.split("\n")
        assert_that(lines[0]).starts_with("Expected <{'id': 7, ..}> to match structure")
        assert_that(lines[1]).starts_with("at <id> the spec holds a class itself")

    def test_a_spec_that_matches_says_nothing_and_reads_the_record_once(self):
        _Dumped.dumps = 0
        assert_that(_Dumped({"id": 7})).matches_structure({"id": 7})
        assert_that(_Dumped.dumps).is_equal_to(1)

    def test_the_other_ways_to_ask_a_structure_are_as_they_were(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_RECORD).satisfies(match.structure({"id": 8, "name": "Ann"}))
        assert_that(caught.value._message.split("\n")[0]).is_equal_to(
            "Expected a mapping matching structure {id: <8>, name: <Ann>}, but at <id>: expected <8>, but was <7>."
        )


_TOP = ("t0", "t1", "t2", "t3")
_BELOW = ("n0", "n1", "t0", "t1")


@st.composite
def _a_record_and_a_spec_it_fails(draw: st.DrawFn) -> tuple[dict, dict]:
    """A record of numbers and of dicts of numbers, and a spec of raw values some of which it does not hold.

    The names below repeat under every parent and two of them are names of the top level, so a key kept
    under the wrong parent, or by its name alone, is told.
    """
    record: dict = {}
    asked: list[tuple[str, object]] = []
    for name in draw(st.lists(st.sampled_from(_TOP), unique=True, min_size=1)):
        if draw(st.booleans()):
            inner = {key: draw(st.integers(0, 9)) for key in draw(st.lists(st.sampled_from(_BELOW), unique=True))}
            record[name] = inner
            below = [(key, held + draw(st.integers(0, 1))) for key, held in inner.items() if draw(st.booleans())]
            if draw(st.booleans()):
                below.append(("gone", 0))
            if draw(st.booleans()):
                asked.append((name, dict(draw(st.permutations(below)))))
        else:
            record[name] = draw(st.integers(0, 9))
            if draw(st.booleans()):
                asked.append((name, record[name] + draw(st.integers(0, 1))))
    if draw(st.booleans()):
        asked.append(("gone", 0))
    spec = dict(draw(st.permutations(asked)))
    assume(not match.structure(spec).matches(record))
    return record, spec


def _on_the_way(holder: dict, failure: AssertionFailure) -> dict:
    """What of *holder*, the record or the spec, lies on the way to the failure's mismatches, in its own order."""
    assert failure.diff is not None
    standing: dict = {}
    for entry in failure.diff.entries:
        value, kept = holder, standing
        for position, step in enumerate(entry.steps):
            if step.value not in value:
                break
            held = value[step.value]
            if position == len(entry.steps) - 1:
                kept[step.value] = held
                break
            kept = kept.setdefault(step.value, {})
            value = held
    return _in_the_order_of(holder, standing)


def _in_the_order_of(holder: dict, standing: dict) -> dict:
    return {
        key: _in_the_order_of(value, standing[key]) if type(standing[key]) is dict and type(value) is dict else value
        for key, value in holder.items()
        if key in standing
    }


def _read_back(said: str) -> dict:
    """A value or a spec as the sentence wrote it, with the marks taken out, as the dict it then spells."""
    spelled = re.sub(r"<(\d+)>", r"\1", re.sub(r"(?<![\w'])(\w+): ", r"'\1': ", said))
    return ast.literal_eval(re.sub(r"\.\., |, \.\.|\.\.", "", spelled))


class TestTheSentenceIsWhatLiesOnTheWayToItsMismatches:
    @given(_a_record_and_a_spec_it_fails())
    def test_read_back_the_value_said_is_the_record_on_the_way_and_nothing_else(self, pair):
        record, spec = pair
        standing = _on_the_way(record, _failed(record, spec))
        read_back = _read_back(_value_said(record, spec))
        assert read_back == standing
        assert repr(read_back) == repr(standing)

    @given(_a_record_and_a_spec_it_fails())
    def test_read_back_the_spec_said_is_the_spec_on_the_way_and_nothing_else(self, pair):
        record, spec = pair
        standing = _on_the_way(spec, _failed(record, spec))
        read_back = _read_back(_spec_said(record, spec))
        assert read_back == standing
        assert repr(read_back) == repr(standing)

    @given(_a_record_and_a_spec_it_fails())
    def test_the_mark_is_there_exactly_where_a_key_was_left_out(self, pair):
        record, spec = pair
        failure = _failed(record, spec)
        for holder, said in ((record, _value_said(record, spec)), (spec, _spec_said(record, spec))):
            outer = re.sub(r"\{[^{}]*\}", "{}", said[said.index("{") + 1 : -1])
            assert (".." in outer) == (len(_on_the_way(holder, failure)) < len(holder))
