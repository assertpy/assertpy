import pytest

from tests.optional import needs

needs("pydantic")

import dataclasses
import json
from typing import Any, ClassVar

from hypothesis import example, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field, field_serializer

from assertpy import AssertionFailure, assert_that
from assertpy._snapshot_codec import _decode, _encode


class UserDto(BaseModel):
    id: int
    name: str


class UserDtoWithEmail(BaseModel):
    id: int
    name: str
    email: str


class AddressDto(BaseModel):
    city: str
    zip_code: str


class UserDtoWithAddress(BaseModel):
    id: int
    name: str
    address: AddressDto


class TestPydanticIgnore:
    def test_ignore_field(self):
        actual = UserDto(id=1, name="Alice")
        expected = UserDto(id=99, name="Alice")
        assert_that(actual).is_equal_to(expected, ignore="id")

    def test_nested_model_ignore(self):
        actual = UserDtoWithAddress(id=1, name="Alice", address=AddressDto(city="NYC", zip_code="10001"))
        expected = UserDtoWithAddress(id=1, name="Alice", address=AddressDto(city="NYC", zip_code="99999"))
        assert_that(actual).is_equal_to(expected, ignore=[("address", "zip_code")])


class TestPydanticInclude:
    def test_include_field(self):
        actual = UserDtoWithEmail(id=1, name="Alice", email="a@x.com")
        expected = UserDtoWithEmail(id=99, name="Alice", email="different@x.com")
        assert_that(actual).is_equal_to(expected, include="name")


class TestPydanticListOfObjects:
    def test_list_of_pydantic_ignore(self):
        actual = [UserDto(id=1, name="Alice"), UserDto(id=2, name="Bob")]
        expected = [UserDto(id=99, name="Alice"), UserDto(id=99, name="Bob")]
        assert_that(actual).is_equal_to(expected, ignore="id")


_addresses = st.builds(AddressDto, city=st.text(max_size=5), zip_code=st.text(max_size=5))
_users = st.builds(UserDtoWithAddress, id=st.integers(), name=st.text(max_size=5), address=_addresses)


class TestPydanticProperties:
    @settings(deadline=None)
    @given(left=_users, right=_users)
    def test_is_equal_to_consistent_with_eq(self, left, right):
        if left == right:
            assert_that(left).is_equal_to(right)
        else:
            with pytest.raises(AssertionError):
                assert_that(left).is_equal_to(right)

    @settings(deadline=None)
    @given(value=_users)
    def test_is_equal_to_reflexive(self, value):
        assert_that(value).is_equal_to(value.model_copy(deep=True))

    @settings(deadline=None)
    @given(value=st.builds(UserDto, id=st.integers(), name=st.text(max_size=5)), new_id=st.integers())
    def test_ignore_removes_field_difference(self, value, new_id):
        other = value.model_copy(update={"id": new_id})
        assert_that(value).is_equal_to(other, ignore="id")


class _Stringified(BaseModel):
    """A serialiser that makes `1` and `"1"` the same text, which is what `model_dump()` then compared."""

    f: Any
    g: int = 0

    @field_serializer("f")
    def _as_text(self, value: Any) -> Any:
        return str(value)


class _Prefixed(BaseModel):
    f: Any

    @field_serializer("f")
    def _prefixed(self, value: Any) -> Any:
        return "x" + str(value)


class _Listed(BaseModel):
    """An array field serialised as a list, which is what hid the array from the search that names it."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    a: Any

    @field_serializer("a")
    def _as_list(self, value: Any) -> Any:
        return value.tolist()


class _WithAnExcludedField(BaseModel):
    f: int
    secret: int = Field(default=0, exclude=True)


class _WithAComputedField(BaseModel):
    first: str
    last: str

    @computed_field
    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


class _Slotted:
    """Carries `model_dump()`, a `model_fields` meaning something else, and slots instead of a `__dict__`."""

    __slots__ = ("_value",)
    model_fields: ClassVar[dict[str, None]] = {"unrelated": None}

    def __init__(self, value: int) -> None:
        self._value = value

    def model_dump(self) -> dict[str, int]:
        return {"value": self._value}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Slotted) and other._value == self._value

    __hash__ = None


class _Impersonating:
    """Carries `model_dump()`, a `__dict__`, and pydantic's own `__pydantic_fields__` naming nothing it holds."""

    __pydantic_fields__: ClassVar[dict[str, None]] = {"absent": None}

    def __init__(self, value: int) -> None:
        self.value = value

    def model_dump(self) -> dict[str, int]:
        return {"value": self.value}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Impersonating) and other.value == self.value

    __hash__ = None


class _Nested(BaseModel):
    """A model holding a model, a private attribute and an alias, which a snapshot has to carry back."""

    model_config = ConfigDict(populate_by_name=True)

    inner: _Stringified
    label: str = Field(default="", alias="Label")
    _secret: int = PrivateAttr(default=0)


class _NestedTwin(BaseModel):
    """The same fields as `_Stringified`, under another class."""

    f: Any
    g: int = 0


@dataclasses.dataclass
class _Point:
    x: int
    y: int


class _Container(BaseModel):
    item: Any
    label: str = ""


class _Counted(BaseModel):
    """A model whose `model_post_init` leaves a trace, which reading a snapshot must not add to."""

    runs: ClassVar[list[int]] = []
    n: int = 0

    def model_post_init(self, context: Any, /) -> None:
        _Counted.runs.append(self.n)


class _Hooked(BaseModel):
    """A model overriding the hooks pickle calls, which reading a snapshot must not call either."""

    calls: ClassVar[list[str]] = []
    n: int = 0

    def __new__(cls, *args: Any, **kwargs: Any) -> "_Hooked":
        _Hooked.calls.append("__new__")
        return super().__new__(cls)

    def __setstate__(self, state: dict[Any, Any]) -> None:
        _Hooked.calls.append("__setstate__")
        super().__setstate__(state)


class _WithExtras(BaseModel):
    model_config = ConfigDict(extra="allow")

    f: int


def _entries(chain) -> list[tuple[str, object, object]]:
    with pytest.raises(AssertionFailure) as caught:
        chain()
    assert caught.value.diff is not None
    return [(entry.path, entry.actual, entry.expected) for entry in caught.value.diff.entries]


class TestAModelIsReadByTheValuesItHolds:
    """The values a model's fields and extras hold, which pydantic's `==` compares, not what `model_dump()` serialises.

    Issue 46.  The message showed the held values and the structured diff the serialised ones, so a
    serialiser folding `1` and `"1"` into one text left the diff empty.  Worse, every configured comparison
    read the same serialised form, and passed where `==` did not.
    """

    def test_a_serialiser_folding_two_values_into_one_text_still_diffs_them(self):
        assert_that(_entries(lambda: assert_that(_Stringified(f=1)).is_equal_to(_Stringified(f="1")))).is_equal_to(
            [(".f", 1, "1")]
        )

    def test_the_hint_reads_the_values_held_as_well(self):
        """The hint engine read the dump too, and saw two equal texts where the model holds `1` and `"1"`."""
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_Stringified(f=1)).is_equal_to(_Stringified(f="1"))
        assert_that(str(caught.value)).contains(
            "every difference here is the same text against a value of another type"
        )

    @pytest.mark.parametrize(
        ("payload", "said"), [({"f": 1, "g": 0}, True), ({"f": "1", "g": 0}, False)], ids=["held", "serialised"]
    )
    def test_the_model_against_its_payload_hint_reads_the_values_held(self, payload, said):
        """Read through the dump, the hint said the contents matched a payload holding `"1"`, and said
        nothing against the payload holding the `1` the model does hold."""
        with pytest.raises(AssertionFailure) as caught:
            assert_that(_Stringified(f=1)).is_equal_to(payload)
        hinted = "the contents match field for field, and only the type of the two sides differs" in str(caught.value)
        assert_that(hinted).described_as(str(caught.value)).is_equal_to(said)

    def test_an_array_a_serialiser_turns_into_a_list_is_still_named(self):
        """Read through the dump, the array was a list by the time anything looked for it, and the refusal
        naming it gave way to the bare `ValueError` about an ambiguous truth value."""
        numpy = needs("numpy")
        with pytest.raises(TypeError) as caught:
            assert_that(_Listed(a=numpy.array([1, 2]))).is_equal_to(_Listed(a=numpy.array([1, 3])))
        assert_that(str(caught.value)).starts_with("is_equal_to() cannot directly compare <ndarray>")

    def test_the_diff_shows_what_the_message_shows_and_not_the_serialised_text(self):
        assert_that(_entries(lambda: assert_that(_Prefixed(f="2")).is_equal_to(_Prefixed(f="1")))).is_equal_to(
            [(".f", "2", "1")]
        )

    @pytest.mark.parametrize(
        "configured",
        [{"ignore": "g"}, {"include": "f"}, {"strict_types": True}, {"tolerance": 0.1}],
        ids=["ignore", "include", "strict_types", "tolerance"],
    )
    def test_a_configured_comparison_does_not_pass_what_equality_refuses(self, configured):
        """`f` alone differs, so each of these fails only if it reads `1` and `"1"` apart."""
        with pytest.raises(AssertionFailure):
            assert_that(_Stringified(f=1, g=0)).is_equal_to(_Stringified(f="1", g=0), **configured)

    def test_a_field_left_out_of_the_dump_is_still_compared_and_shown(self):
        entries = _entries(
            lambda: assert_that(_WithAnExcludedField(f=1, secret=1)).is_equal_to(
                _WithAnExcludedField(f=1, secret=2), ignore="f"
            )
        )
        assert_that(entries).is_equal_to([("secret", 1, 2)])

    def test_a_computed_field_is_not_compared_where_its_inputs_are_ignored(self):
        """`==` compares fields, so a value worked out from an ignored one is not a difference."""
        assert_that(_WithAComputedField(first="a", last="x")).is_equal_to(
            _WithAComputedField(first="a", last="y"), ignore="last"
        )

    def test_extra_fields_are_compared_as_equality_compares_them(self):
        with pytest.raises(AssertionFailure):
            assert_that(_WithExtras(f=1, z=1)).is_equal_to(_WithExtras(f=1, z=2), ignore="f")
        assert_that(_WithExtras(f=1, z=1)).is_equal_to(_WithExtras(f=2, z=1), ignore="f")

    def test_the_field_quantifiers_walk_the_values_held(self):
        """`all_fields_satisfy` walks what the diff walks, so a leaf is the value held and not its dump."""
        assert_that(_Prefixed(f="2")).all_fields_satisfy(lambda leaf: not str(leaf).startswith("x"))

    @pytest.mark.parametrize("configured", [{}, {"ignore": "zzz"}], ids=["plain", "ignore"])
    def test_an_extra_named_like_a_declared_field_is_refused(self, configured):
        """Validation never produces it.  Made by hand, the model holds two values under one name.

        Dropping the extra passed two models whose colliding extras differed, and letting it overwrite the
        field passed one against a model holding the extra's value.  Neither reading is the model.
        """
        left, right = _WithExtras(f=1), _WithExtras(f=1)
        assert left.__pydantic_extra__ is not None and right.__pydantic_extra__ is not None
        left.__pydantic_extra__["f"] = 2
        right.__pydantic_extra__["f"] = 3
        with pytest.raises(TypeError) as caught:
            assert_that(left).is_equal_to(right, **configured)
        assert_that(str(caught.value)).is_equal_to(
            "_WithExtras holds an extra named 'f' beside the field of that name, which validation never"
            " produces, so its fields cannot be read one by one"
        )

    @pytest.mark.parametrize(
        "duck", [lambda value: _Slotted(value), lambda value: _Impersonating(value)], ids=["slotted", "impersonating"]
    )
    def test_a_duck_type_is_still_read_through_its_dump(self, duck):
        """Nothing but `model_dump()` is promised, whatever else the object carries."""
        assert_that(duck(1)).is_equal_to(duck(1), ignore="zzz")
        with pytest.raises(AssertionFailure):
            assert_that(duck(1)).is_equal_to(duck(2), ignore="zzz")

    def test_a_dataclass_in_a_model_is_taken_apart_as_before(self):
        """`model_dump()` took a dataclass inside a model apart too, so it compared against a mapping."""
        assert_that(_Container(item=_Point(1, 2))).is_equal_to(_Container(item={"x": 1, "y": 2}), ignore="label")

    def test_a_nested_model_of_another_class_is_compared_by_contents_as_before(self):
        """`model_dump()` took nested models apart, so a configured comparison read their contents; kept."""
        assert_that(_Container(item=_Stringified(f=1))).is_equal_to(_Container(item=_NestedTwin(f=1)), ignore="label")

    def test_structure_matching_keeps_the_serialised_form_it_documents(self):
        """`matches_structure` is documented against `model_dump()`, serialisers applied, and stays so."""
        assert_that(_Stringified(f=1)).matches_structure({"f": "1"})
        assert_that(_WithAComputedField(first="a", last="b")).matches_structure({"full": "a b"})


# a few small integers and the same digits as text, so the serialiser folds two values into one text often
_folding = st.one_of(st.integers(min_value=-2, max_value=2), st.sampled_from(["-2", "-1", "0", "1", "2", "x"]))


class TestAModelComparisonAgreesWithEquality:
    @settings(deadline=None)
    @example(f_left=1, f_right="1", g=0)
    @given(f_left=_folding, f_right=_folding, g=st.integers(min_value=0, max_value=1))
    def test_ignoring_a_field_both_sides_hold_equal_changes_no_verdict(self, f_left, f_right, g):
        """Ignoring what does not differ cannot turn a failure into a pass, whatever the serialiser folds."""
        left, right = _Stringified(f=f_left, g=g), _Stringified(f=f_right, g=g)
        if left == right:
            assert_that(left).is_equal_to(right, ignore="g")
        else:
            with pytest.raises(AssertionFailure):
                assert_that(left).is_equal_to(right, ignore="g")

    @settings(deadline=None)
    @example(f_left=1, f_right="1")
    @given(f_left=_folding, f_right=_folding)
    def test_a_failed_comparison_names_the_field_that_differs(self, f_left, f_right):
        """A model `==` tells apart always leaves a diff entry, so the section never comes out empty."""
        left, right = _Stringified(f=f_left), _Stringified(f=f_right)
        if left == right:
            return
        assert_that(_entries(lambda: assert_that(left).is_equal_to(right))).is_equal_to([(".f", f_left, f_right)])


def _round_trip(value: object) -> object:
    return _decode(json.loads(json.dumps(_encode({"v": value}))))["v"]


class TestAModelRoundTripsThroughASnapshot:
    """Written through its `__dict__` and read back by assigning one, a model had none of the slots its `==`
    reads, so every snapshot of a model failed on the run after it was written."""

    @pytest.mark.parametrize(
        "value",
        [_Stringified(f=1, g=2), _WithExtras(f=1, z=2), _Nested(inner=_Stringified(f="x"), Label="l")],
        ids=["plain", "extras", "nested"],
    )
    def test_what_is_written_is_what_is_read(self, value):
        assert_that(_round_trip(value)).is_equal_to(value)

    def test_reading_one_runs_none_of_the_model_s_code(self):
        """`model_construct` runs `model_post_init`, the caller's code, on every read of the snapshot."""
        value = _Counted(n=3)
        runs = list(_Counted.runs)
        assert_that(_round_trip(value)).is_equal_to(value)
        assert_that(_Counted.runs).is_equal_to(runs)

    def test_reading_one_calls_no_hook_the_model_overrides(self):
        value = _Hooked(n=2)
        _Hooked.calls.clear()
        assert_that(_round_trip(value)).is_equal_to(value)
        assert_that(_Hooked.calls).is_empty()

    def test_a_snapshot_written_before_runs_none_of_the_model_s_code_either(self):
        expected = _Counted(n=4)
        runs = list(_Counted.runs)
        written = json.dumps(
            {"v": {"__type__": "instance", "__class__": "_Counted", "__module__": __name__, "__data__": {"n": 4}}}
        )
        assert_that(_decode(json.loads(written))["v"]).is_equal_to(expected)
        assert_that(_Counted.runs).is_equal_to(runs)

    def test_the_private_state_and_the_fields_set_come_back(self):
        """`model_construct` alone reset the private state `==` compares and marked every field as set."""
        value = _Nested(inner=_Stringified(f=1))
        value._secret = 7
        back = _round_trip(value)
        assert_that(back).is_equal_to(value)
        assert_that(back.model_dump(exclude_unset=True)).is_equal_to(value.model_dump(exclude_unset=True))

    def test_a_nested_model_of_another_class_fails_under_strict_types(self):
        with pytest.raises(AssertionFailure):
            assert_that(_Container(item=_Stringified(f=1))).is_equal_to(
                _Container(item=_NestedTwin(f=1)), ignore="unrelated", strict_types=True
            )

    def test_a_snapshot_written_before_is_read_back(self):
        """The form the codec wrote until now, the model's `__dict__` alone, still reads as the model."""
        written = json.dumps(
            {
                "v": {
                    "__type__": "instance",
                    "__class__": "_Stringified",
                    "__module__": __name__,
                    "__data__": {"f": 1, "g": 2},
                }
            }
        )
        back = _decode(json.loads(written))["v"]
        assert_that(back).is_equal_to(_Stringified(f=1, g=2))
        assert_that(back.model_fields_set).is_equal_to({"f", "g"})


@settings(deadline=None)
@given(
    f=st.one_of(st.integers(), st.text(max_size=4), st.lists(st.integers(), max_size=3)),
    g=st.integers(),
    secret=st.integers(),
    label=st.none() | st.text(max_size=3),
)
def test_a_model_round_trips_through_the_snapshot_codec(f, g, secret, label):
    value = _Nested(inner=_Stringified(f=f, g=g)) if label is None else _Nested(inner=_Stringified(f=f), Label=label)
    value._secret = secret
    back = _round_trip(value)
    assert_that(back).is_equal_to(value)
    assert_that(back.model_fields_set).is_equal_to(value.model_fields_set)
