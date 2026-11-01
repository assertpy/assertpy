"""Hold `exact=True` to pydantic itself on which keys of a payload validation drops.

A key pydantic drops is one a twin of the same model refuses once it forbids extras.  The check has to name those
keys and no other, for every way a field is named, every config that says which names validation reads, and every
payload sending the name, an alias, a path, or several of them.  Where it says a field was read from another key,
the value the model holds has to be the one sent there.

Written as a difference against pydantic and not as a list of expectations: which spelling wins is pydantic's to
decide, and it is asked under whichever pydantic the suite runs with.
"""

import itertools
import typing

import pytest

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
    from typing_extensions import NotRequired, TypedDict

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
