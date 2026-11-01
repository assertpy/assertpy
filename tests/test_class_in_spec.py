"""A class written where a matcher was meant: the failure says what stands there and which matcher was meant.

``{"id": int}`` reads as "an int" to anyone coming from a schema library.  A spec holds values, a class is a value,
and it is compared with ``==`` as any other, so the spec fails on the payloads it was written for.  Where the value
is an instance of the class the spec holds, a line under the sentence says so and names the matcher.  A factory
that takes a matcher refuses a class with the same matcher named.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import typing
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match

_MATCHER = "the matcher for an instance of a class is match.is_instance_of"
_LINE = f"the spec holds a class itself and the value is an instance of it: {_MATCHER}"


def _lines(payload: object, spec: dict) -> list[str]:
    with pytest.raises(AssertionFailure) as caught:
        assert_that(payload).matches_structure(spec)
    return caught.value._message.split("\n")


def _reason(payload: object, spec: dict) -> str | None:
    """The line under the sentence, or ``None`` where the failure is its sentence alone."""
    said = [line for line in _lines(payload, spec) if line.startswith("at <") and line.endswith(_MATCHER)]
    assert_that(len(said)).is_less_than(2)
    return said[0] if said else None


@dataclasses.dataclass
class _Row:
    id: int


class _Sized(collections.abc.Sized):
    def __len__(self) -> int:
        return 0


class _Keyed(typing.TypedDict):
    id: int


class _Shaped(typing.Protocol):
    def shape(self) -> int: ...


class _Unnameable(str):
    __slots__ = ()

    def isidentifier(self) -> bool:
        raise RuntimeError("asked")

    def __len__(self) -> int:
        raise RuntimeError("asked")

    def __format__(self, spec: str) -> str:
        raise RuntimeError("asked")

    def __str__(self) -> str:
        raise RuntimeError("asked")


class TestAClassInASpec:
    @pytest.mark.parametrize(
        ("value", "klass"),
        [
            (7, int),
            (1.5, float),
            ("a", str),
            (True, int),
            ([1], list),
            (_Row(1), _Row),
            (datetime.datetime(2026, 1, 1), datetime.date),
            (7, object),
            (int, type),
        ],
    )
    def test_an_instance_of_the_class_held_gets_the_line(self, value, klass):
        assert_that(_reason({"id": value}, {"id": klass})).is_equal_to(f"at <id> {_LINE}")

    def test_the_sentence_above_the_line_is_the_one_it_was(self):
        assert_that(_lines({"id": 7}, {"id": int})[0]).is_equal_to(
            "Expected <{'id': 7}> to match structure {id: <<class 'int'>>}, but at <id>:"
            " expected <<class 'int'>>, but was <7>."
        )

    def test_the_place_is_the_path_to_the_class(self):
        assert_that(_reason({"user": {"id": 7}}, {"user": {"id": int}})).is_equal_to(f"at <user.id> {_LINE}")

    def test_the_first_such_place_is_named_whatever_the_sentence_names(self):
        lines = _lines({"name": "a", "id": 7, "age": 3}, {"name": "b", "id": int, "age": int})
        assert_that(lines[0]).contains("but at <name>: expected <b>")
        assert_that(lines[1]).is_equal_to(f"at <id> {_LINE}")

    @pytest.mark.parametrize(
        ("value", "held"),
        [
            ("7", int),
            (7, str),
            (int, _Row),
            (7, int | None),
            ([1], list[int]),
            (["a"], [str]),
            (7, (int, str)),
            (7, "int"),
            (7, 8),
        ],
    )
    def test_anything_else_gets_no_line(self, value, held):
        assert_that(_reason({"id": value}, {"id": held})).is_none()

    def test_a_class_with_a_metaclass_of_its_own_gets_no_line(self):
        assert_that(_reason({"id": _Sized()}, {"id": _Sized})).is_none()
        assert_that(_reason({"id": _Sized()}, {"id": collections.abc.Sized})).is_none()

    def test_the_class_the_value_was_built_from_is_asked_and_not_the_value(self):
        assert_that(isinstance(mock.Mock(spec=int), int)).is_true()
        assert_that(_reason({"id": mock.Mock(spec=int)}, {"id": int})).is_none()

    def test_a_base_that_refuses_to_be_compared_is_not_compared(self):
        class Refusing(type):
            def __eq__(cls, other):
                raise RuntimeError("compared")

            __hash__ = type.__hash__

        class Base(metaclass=Refusing):
            pass

        class Held(Base):
            pass

        assert_that(_reason({"id": Held()}, {"id": object})).is_equal_to(f"at <id> {_LINE}")

    def test_a_class_named_by_a_text_that_cannot_be_read_is_not_asked_for_its_name(self):
        held = type("Held", (), {})
        held.__name__ = _Unnameable("Held")

        assert_that(_reason({"id": held()}, {"id": held})).is_equal_to(f"at <id> {_LINE}")

    def test_a_value_equal_to_the_class_passes_as_it_did(self):
        class Agreeing:
            def __eq__(self, other):
                return other is Agreeing

            __hash__ = object.__hash__

        assert_that({"id": Agreeing()}).matches_structure({"id": Agreeing})
        assert_that({"id": _Row}).matches_structure({"id": _Row})

    def test_a_matcher_used_as_a_matcher_says_the_sentence_alone(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"id": 7}).satisfies(match.structure({"id": int}))
        assert_that(caught.value._message).does_not_contain(_MATCHER)

    @given(
        value=st.one_of(st.integers(), st.floats(allow_nan=False), st.text(), st.booleans(), st.none(), st.binary()),
        klass=st.sampled_from([int, float, str, bool, bytes, object, list, type(None)]),
    )
    def test_the_line_is_said_exactly_where_the_matcher_it_names_takes_the_value(self, value, klass):
        said = _reason({"id": value}, {"id": klass})

        assert_that(said is not None).is_equal_to(isinstance(value, klass))
        if said is not None:
            assert_that({"id": value}).matches_structure({"id": match.is_instance_of(klass)})


def _sentence(payload: object, spec: dict) -> str:
    return _lines(payload, spec)[0]


class TestAValueOfAnotherTypeBesideAClass:
    """The sentence prints a value by its text, so the text ``'7'`` beside the class `int` read ``<7>``."""

    @pytest.mark.parametrize(
        ("value", "klass", "written"),
        [("7", int, "<7> of type <str>"), (7, str, "<7> of type <int>"), (None, int, "<None> of type <NoneType>")],
    )
    def test_the_sentence_says_the_type_of_a_value_that_is_no_instance(self, value, klass, written):
        assert_that(_sentence({"id": value}, {"id": klass})).ends_with(f"but was {written}.")

    def test_it_reads_as_the_matcher_for_an_instance_does(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"id": "7"}).matches_structure({"id": match.is_instance_of(int)})

        assert_that(caught.value._message).ends_with("but was <7> of type <str>.")
        assert_that(_sentence({"id": "7"}, {"id": int})).ends_with("but was <7> of type <str>.")

    def test_an_instance_gets_the_line_and_no_type(self):
        assert_that(_sentence({"id": 7}, {"id": int})).ends_with("expected <<class 'int'>>, but was <7>.")

    def test_a_class_with_a_metaclass_of_its_own_gets_the_type_whatever_the_value_is(self):
        assert_that(_sentence({"id": _Sized()}, {"id": collections.abc.Sized})).ends_with(" of type <_Sized>.")
        assert_that(_sentence({"id": 7}, {"id": collections.abc.Sized})).ends_with("but was <7> of type <int>.")

    def test_a_value_held_against_what_is_no_class_gets_none(self):
        assert_that(_sentence({"id": "7"}, {"id": 8})).ends_with("expected <8>, but was <7>.")
        assert_that(_sentence({"id": "7"}, {"id": int | None})).ends_with("but was <7>.")

    def test_two_sides_told_apart_by_their_classes_get_none(self):
        assert_that(_sentence({"id": "<class 'int'>"}, {"id": int})).ends_with(
            "expected <<class 'int'>:type>, but was <<class 'int'>:str>."
        )

    def test_the_class_the_value_was_built_from_is_named_and_not_the_one_it_claims(self):
        assert_that(_sentence({"id": mock.Mock(spec=int)}, {"id": int})).ends_with(" of type <Mock>.")

    def test_a_class_whose_name_cannot_be_asked_is_named_off_its_slot(self):
        class Lying(type):
            @property
            def __name__(cls):
                raise RuntimeError("asked")

        class Held(metaclass=Lying):
            def __repr__(self) -> str:
                return "held"

        assert_that(_sentence({"id": Held()}, {"id": int})).ends_with("but was <held> of type <Held>.")

    def test_a_matcher_used_as_a_matcher_says_it_too(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"id": "7"}).satisfies(match.structure({"id": int}))
        assert_that(caught.value._message).contains("but was <7> of type <str>")

    @given(
        value=st.one_of(st.integers(), st.floats(allow_nan=False), st.booleans(), st.none(), st.binary()),
        klass=st.sampled_from([int, float, str, bool, bytes, object, list, type(None)]),
    )
    def test_the_type_is_said_exactly_where_the_value_is_no_instance(self, value, klass):
        sentence = _sentence({"id": value}, {"id": klass})

        assert_that(sentence.endswith(f" of type <{type(value).__name__}>.")).is_equal_to(not isinstance(value, klass))


class TestAClassWhereAMatcherIsWanted:
    @pytest.mark.parametrize(
        "build",
        [
            lambda: match.each_item(str),
            lambda: match.has_property("id", str),
            lambda: match.not_(str),
            lambda: match.all_of(match.is_uuid(), str),
            lambda: match.any_of(str, match.is_uuid()),
        ],
    )
    def test_a_factory_names_the_matcher_for_an_instance(self, build):
        with pytest.raises(TypeError) as caught:
            build()
        assert_that(str(caught.value)).is_equal_to(
            f"given matcher arg must be a Matcher, but was <<class 'str'>> (type): {_MATCHER}"
        )

    @pytest.mark.parametrize(
        ("combine", "sign"), [(lambda: match.is_uuid() & str, "&"), (lambda: match.is_uuid() | str, "|")]
    )
    def test_an_operator_names_it_too(self, combine, sign):
        with pytest.raises(TypeError) as caught:
            combine()
        assert_that(str(caught.value)).is_equal_to(f"cannot combine a Matcher with <type> using '{sign}': {_MATCHER}")

    @pytest.mark.parametrize(("klass", "instance"), [(str, "a"), (_Row, _Row(1)), (object, 7), (type, int)])
    def test_the_matcher_named_takes_the_class_refused(self, klass, instance):
        with pytest.raises(TypeError, match=_MATCHER):
            match.each_item(klass)
        assert_that(match.is_instance_of(klass).matches(instance)).is_true()

    @pytest.mark.parametrize("klass", [_Keyed, _Shaped])
    def test_a_class_that_refuses_an_instance_check_is_refused_as_it_was(self, klass):
        with pytest.raises(TypeError):
            match.is_instance_of(klass)
        with pytest.raises(TypeError) as caught:
            match.each_item(klass)
        assert_that(str(caught.value)).does_not_contain(_MATCHER).ends_with(f"({type(klass).__name__})")

    @pytest.mark.parametrize("given_", [5, "str", int | None, list[int], (int, str), collections.abc.Sized, _Sized])
    def test_what_type_itself_did_not_build_is_refused_as_it_was(self, given_):
        with pytest.raises(TypeError) as caught:
            match.each_item(given_)
        assert_that(str(caught.value)).does_not_contain(_MATCHER).ends_with(f"({type(given_).__name__})")
        with pytest.raises(TypeError) as caught:
            match.is_uuid() | given_
        assert_that(str(caught.value)).is_equal_to(f"cannot combine a Matcher with <{type(given_).__name__}> using '|'")
