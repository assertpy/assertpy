"""Hold `exact=True` to pydantic itself on which keys of a payload validation drops.

A key pydantic drops is one a twin of the same model refuses once it forbids extras.  The check has to name those
keys and no other, for every way a field is named, every config that says which names validation reads, and every
payload sending the name, an alias, a path, or several of them.  Where it says a field was read from another key,
the value the model holds has to be the one sent there.

Written as a difference against pydantic and not as a list of expectations: which spelling wins is pydantic's to
decide, and it is asked under whichever pydantic the suite runs with.
"""

import copy
import functools
import itertools
import operator
import typing

import pytest
from hypothesis import HealthCheck, event, example, given, reject, settings
from hypothesis import strategies as st
from typing_extensions import NotRequired, TypedDict

from assertpy import AssertionFailure, assert_conforms, assert_that

pydantic = pytest.importorskip("pydantic", reason="pydantic not installed")
pydantic_dataclass = pytest.importorskip("pydantic.dataclasses").dataclass
AliasChoices, AliasPath, BaseModel, ConfigDict = (
    pydantic.AliasChoices,
    pydantic.AliasPath,
    pydantic.BaseModel,
    pydantic.ConfigDict,
)
Field, ValidationError = pydantic.Field, pydantic.ValidationError

_REFUSED_AS_EXTRA = {"extra_forbidden", "unexpected_keyword_argument"}

_NAMED = {
    "its name alone": {},
    "an alias": {"alias": "firstName"},
    "a validation alias": {"validation_alias": "firstName"},
    "an alias it is dumped under": {"serialization_alias": "firstName"},
    "an alias and another to validate by": {"alias": "first_name", "validation_alias": "firstName"},
    "a choice of two": {"validation_alias": AliasChoices("firstName", "first_name")},
    "a path": {"validation_alias": AliasPath("data", "value")},
    "a path by position": {"validation_alias": AliasPath("data", 0)},
    "a choice of a path and a key": {"validation_alias": AliasChoices(AliasPath("data", "value"), "first_name")},
}
_CONFIGS = {"default": {}, "populate_by_name": {"populate_by_name": True}}
if "validate_by_name" in ConfigDict.__annotations__:
    _CONFIGS |= {
        "validate_by_name": {"validate_by_name": True},
        "by name only": {"validate_by_name": True, "validate_by_alias": False},
        "by alias, said": {"validate_by_alias": True},
    }
_KEYS = {"first": 1, "firstName": 2, "first_name": 3}
_UNDER_DATA = [None, {"value": 4}, {"other": 5}, [6], []]


def _payloads():
    for size in range(len(_KEYS) + 1):
        for chosen in itertools.combinations(_KEYS, size):
            for data in _UNDER_DATA:
                yield {key: _KEYS[key] for key in chosen} | ({} if data is None else {"data": data})


def _model(named, config):
    body = {"__annotations__": {"first": int}, "first": Field(default=0, **named), "model_config": ConfigDict(**config)}
    return type("Read", (BaseModel,), body)


def _typed_dict(named, config):
    class Read(TypedDict):
        first: NotRequired[typing.Annotated[int, Field(**named)]]

    Read.__pydantic_config__ = ConfigDict(**config)
    return Read


def _dataclass(named, config):
    plain = type("Read", (), {"__annotations__": {"first": int}, "first": Field(default=0, **named)})
    return pydantic_dataclass(config=ConfigDict(**config))(plain)


def _held(kind, wrap):
    return type("Holding", (BaseModel,), {"__annotations__": {"held": wrap(kind)}})


_PLACES = {
    "a model": (_model, None),
    "a model in a list": (_model, lambda kind: list[kind]),
    "a TypedDict": (_typed_dict, lambda kind: kind),
    "a pydantic dataclass": (_dataclass, lambda kind: kind),
}


def _sent(place, payload):
    return {"a model": payload, "a model in a list": {"held": [payload]}}.get(place, {"held": payload})


def _dropped(twin, payload):
    """The places pydantic refuses once extras are forbidden, or ``None`` where it refuses the payload for more."""
    try:
        twin.model_validate(payload)
    except ValidationError as refusal:
        found = refusal.errors()
        return None if {item["type"] for item in found} - _REFUSED_AS_EXTRA else {tuple(item["loc"]) for item in found}
    return set()


def _named_by_the_check(model, payload):
    try:
        assert_conforms(payload, model, exact=True)
    except AssertionFailure as failure:
        return {tuple(step.value for step in entry.steps) for entry in failure.diff.entries}, str(failure)
    return set(), ""


def _reached(payload, spelt):
    for step in spelt.replace("[", ".").replace("]", "").split("."):
        payload = payload[int(step) if step.isdigit() else step]
    return payload


def _built(place, model, payload):
    built = model.model_validate(_sent(place, payload))
    if place == "a model":
        return built.first
    held = built.held[0] if place == "a model in a list" else built.held
    return held.get("first", 0) if isinstance(held, dict) else held.first


@pytest.mark.parametrize("place", _PLACES)
@pytest.mark.parametrize("named", _NAMED)
def test_the_keys_named_are_the_keys_pydantic_drops(place, named):
    build, wrap = _PLACES[place]
    asked, apart = 0, {}
    for said, config in _CONFIGS.items():
        try:
            plain, strict = build(_NAMED[named], config), build(_NAMED[named], {**config, "extra": "forbid"})
        # an older pydantic takes a path for no field of a record, or one `Field` for a dataclass
        except (TypeError, pydantic.PydanticUserError):
            continue
        model, twin = (plain, strict) if wrap is None else (_held(plain, wrap), _held(strict, wrap))
        for payload in _payloads():
            dropped = _dropped(twin, _sent(place, payload))
            if dropped is None:
                continue
            asked += 1
            found, said_of_it = _named_by_the_check(model, _sent(place, payload))
            if found != dropped:
                apart[f"{said}, sent {payload}"] = f"pydantic drops {sorted(map(str, dropped))}, named {said_of_it}"
            for line in said_of_it.splitlines()[1:]:
                if "its field was read from" in line:
                    read_from = line.rsplit("<", 1)[1].rstrip(">")
                    if _built(place, model, payload) != _reached(payload, read_from):
                        apart[f"{said}, sent {payload}, the source"] = line
    assert_that(apart).described_as(f"{place}, a field read by {named}").is_empty()
    # a case pydantic refuses for more is no case, so a matrix that asked nothing would hold whatever the check does
    assert_that(asked).described_as("payloads pydantic validated").is_greater_than(20)


def _state(place, model, payload):
    """What validation built from *payload*, its field and its extras apart, so that an extra under the field's name
    does not hide the field as it does in a dump."""
    built = model.model_validate(_sent(place, payload))
    held = built if place == "a model" else built.held[0] if place == "a model in a list" else built.held
    if isinstance(held, BaseModel):
        return held.first, held.model_extra
    return dict(held) if isinstance(held, dict) else dict(vars(held))


def _ignored(place, model, payload):
    """Where pydantic ignored the field's name, told by sending it again with another value: a name it read or kept
    changes what it built, one it ignored does not.  Only the name is asked: an alias whose value a kept name was put
    over changes nothing either, and was read all the same."""
    if "first" not in payload:
        return set()
    same = _state(place, model, {**payload, "first": payload["first"] + 100}) == _state(place, model, payload)
    under = {"a model": (), "a model in a list": ("held", 0)}.get(place, ("held",))
    return {(*under, "first")} if same else set()


_OWN = (("a", int), ("b", str), ("c", bytes))


def _member(index, named, config):
    """The *index*-th member of a union: an optional field of its own, so that a payload of this file tells no member
    apart, and `first` read by *named*, or no `first` where *named* is ``None``."""
    own, kind = _OWN[index]
    fields: dict[str, object] = {own: NotRequired[kind]}
    if named is not None:
        fields["first"] = NotRequired[typing.Annotated[int, Field(**named)]]
    member = TypedDict(f"Read{own.upper()}", fields)
    member.__pydantic_config__ = ConfigDict(**config)
    return member


def _typed_dicts(count, *, reversed_order=False):
    """A builder of a union of *count* `TypedDict`s that read `first` alike."""

    def build(named, config):
        members = [_member(index, named, config) for index in range(count)]
        return functools.reduce(operator.or_, reversed(members) if reversed_order else members)

    return build


_UNIONS = {
    "one of two TypedDicts": (_typed_dicts(2), lambda kind: kind),
    "one of two TypedDicts, the other first": (_typed_dicts(2, reversed_order=True), lambda kind: kind),
    "one of three TypedDicts": (_typed_dicts(3), lambda kind: kind),
    "one of three TypedDicts, the last first": (_typed_dicts(3, reversed_order=True), lambda kind: kind),
}
_NAME_PLACES = _PLACES | _UNIONS


@pytest.mark.parametrize("extra", ["ignore", "allow"])
@pytest.mark.parametrize("place", _NAME_PLACES)
@pytest.mark.parametrize("named", _NAMED)
def test_the_name_is_named_where_pydantic_ignores_it(place, named, extra):
    """A field's name validation does not read the field by is named exactly where pydantic ignores it.  A record that
    keeps extras keeps the name unless pydantic ignores it, as a later one does, which the twin that forbids extras
    cannot tell apart, since it refuses what is kept as well.  Where a union of records that nothing tells apart built
    the dict, the check may also refuse, which is no verdict and is counted apart."""
    build, wrap = _NAME_PLACES[place]
    asked, refused, apart = 0, 0, {}
    for said, config in _CONFIGS.items():
        try:
            plain = build(_NAMED[named], {**config, "extra": extra})
        # an older pydantic takes a path for no field of a record, or one `Field` for a dataclass
        except (TypeError, pydantic.PydanticUserError):
            continue
        model = plain if wrap is None else _held(plain, wrap)
        for payload in _payloads():
            try:
                ignored = _ignored(place, model, payload)
            except ValidationError:
                continue
            asked += 1
            found, said_of_it = _named_by_the_check(model, _sent(place, payload))
            if "cannot be checked" in said_of_it and place in _UNIONS:
                refused += 1
                continue
            named_name = {spot for spot in found if spot[-1] == "first"}
            if named_name != ignored:
                apart[f"{said}, sent {payload}"] = f"pydantic ignores {sorted(map(str, ignored))}, named {said_of_it}"
    assert_that(apart).described_as(f"{place} with extra={extra}, a field read by {named}").is_empty()
    # the fewest a union decides, measured on pydantic 2.0, where it refuses most
    least = 4 if place in _UNIONS else 21
    decided = asked - refused
    assert_that(decided).described_as("payloads pydantic validated and the check decided").is_greater_than_or_equal_to(
        least
    )


_MEMBERS = st.lists(
    st.tuples(
        st.sampled_from([None, *_NAMED]), st.sampled_from(["ignore", "allow"]), st.sampled_from(sorted(_CONFIGS))
    ),
    min_size=2,
    max_size=len(_OWN),
)
# `first` always, since the name is what is judged and a payload without it has nothing to name
_SHARED = 10**30
"""One object every key may hold at once, which is what two equal small ints are."""

_SENT = st.builds(
    lambda chosen, data, grown, shared: (
        {key: _SHARED if shared else _KEYS[key] for key in sorted({"first", *chosen})}
        | ({} if _UNDER_DATA[data] is None else {"data": copy.deepcopy(_UNDER_DATA[data])})
        | ({"grown": 7} if grown else {})
    ),
    st.sets(st.sampled_from(sorted(_KEYS.keys() - {"first"}))),
    st.integers(0, len(_UNDER_DATA) - 1),
    st.booleans(),
    st.booleans(),
)


@settings(deadline=None, max_examples=300, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(members=_MEMBERS, payload=_SENT)
@example(members=[("an alias", "ignore", "default")] * 2, payload={"first": 1, "firstName": 2})
@example(
    members=[("an alias", "ignore", "default"), ("its name alone", "ignore", "default")],
    payload={"first": 1, "firstName": 1},
)
@example(members=[("an alias", "ignore", "default"), (None, "allow", "default")], payload={"first": 1, "firstName": 2})
@example(members=[(None, "allow", "default"), ("an alias", "ignore", "default")], payload={"first": 1})
@example(
    members=[("an alias", "allow", "default"), ("an alias", "ignore", "default")], payload={"first": 1, "firstName": 2}
)
@example(
    members=[("an alias", "ignore", "default"), ("an alias", "allow", "default")], payload={"first": 1, "firstName": 2}
)
def test_a_union_names_the_name_exactly_where_pydantic_ignores_it(members, payload):
    """Members that read `first` each their own way, keep or drop extras, or lack the field, under any config: where
    the check decides, it names `first` exactly where pydantic ignored it.  Where nothing tells the members apart it may
    refuse, which is no verdict."""
    try:
        union = functools.reduce(
            operator.or_,
            [
                _member(index, None if named is None else _NAMED[named], {**_CONFIGS[said], "extra": extra})
                for index, (named, extra, said) in enumerate(members)
            ],
        )
        model = _held(union, lambda kind: kind)
        ignored = _ignored("a union", model, payload)
    # an older pydantic takes a path for no field of a record, and a payload a member refuses is no case
    except (TypeError, pydantic.PydanticUserError, ValidationError):
        reject()
    found, said_of_it = _named_by_the_check(model, _sent("a union", payload))
    if "cannot be checked" in said_of_it:
        event("refused")
        return
    event("named" if ignored else "left alone")
    named_name = {spot for spot in found if spot[-1] == "first"}
    assert_that(named_name).described_as(f"{members}, sent {payload}: {said_of_it}").is_equal_to(ignored)


def test_keys_two_fields_share_are_read_once_and_dropped_once():
    crossed = {"a": (Field(default=0, alias="b"), int), "b": (Field(default=0), int)}
    shared = {"a": (Field(default=0, alias="k"), int), "b": (Field(default=0, alias="k"), int)}
    under_one_key = {
        "a": (Field(default=0, validation_alias=AliasPath("data", "a")), int),
        "b": (Field(default=0, validation_alias=AliasPath("data", "b")), int),
    }
    sent = {
        "an alias that is another field's name": (crossed, [{"b": 1}, {"a": 1}, {"a": 1, "b": 2}]),
        "one alias for two fields": (shared, [{"k": 1}, {"k": 1, "a": 2}, {"a": 1, "b": 2}]),
        "two paths under one key": (under_one_key, [{"data": {"a": 1}}, {"data": {"b": 1}}, {"data": {"c": 1}}, {}]),
    }
    apart = {}
    for label, (fields, payloads) in sent.items():
        body = {"__annotations__": {name: kind for name, (_, kind) in fields.items()}}
        body |= {name: field for name, (field, _) in fields.items()}
        model = type("Read", (BaseModel,), dict(body))
        twin = type("Read", (BaseModel,), {**body, "model_config": ConfigDict(extra="forbid")})
        for payload in payloads:
            dropped, (found, said_of_it) = _dropped(twin, payload), _named_by_the_check(model, payload)
            if found != dropped:
                apart[f"{label}, sent {payload}"] = f"pydantic drops {dropped}, named {said_of_it}"
    assert_that(apart).is_empty()
