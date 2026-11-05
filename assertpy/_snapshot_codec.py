from __future__ import annotations

import abc
import base64
import contextlib
import dataclasses
import datetime
import decimal
import enum
import json
import os
import sys
import types
import uuid
from typing import TYPE_CHECKING, Any, NamedTuple

from ._engine._introspection import (
    is_attrs_instance,
    is_pydantic_model,
    is_pydantic_model_class,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__tracebackhide__ = True


class _Serializer(NamedTuple):
    cls: type
    encode: Callable[[object], object]
    decode: Callable[[object], object]
    tag: str


# user-registered serializers, checked before the built-in codec (last registered wins)
_SERIALIZERS: list[_Serializer] = []

# a user dict carrying any of them is escaped so it is not mistaken for an envelope on load
_RESERVED_MARKERS = frozenset({"__type__", "__data__", "__tag__", "__class__", "__module__"})


_NATIVE = (str, int, float, bool, type(None))
_ORDINARY_CHECKS = (type.__instancecheck__, abc.ABCMeta.__instancecheck__)
_ORDINARY_SUBCLASS_CHECKS = (type.__subclasscheck__, abc.ABCMeta.__subclasscheck__)


def _encode(value: object) -> object:
    """A value as the JSON data a snapshot file holds for it, read back by `_decode` as the value it was."""
    return json.loads(json.dumps(_Writer().encode(value), sort_keys=True, cls=_LegacyEncoder))


class _Payload:
    """What a serializer's ``encode`` returned, left for `_LegacyEncoder` to write as every value was written
    before tuples were tagged: a tuple as an array, a dict's keys sorted before ``json`` makes them strings."""

    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value


class _Writer:
    """Writes values as JSON data, with the registry as it stands when it is made.

    A registered serializer is asked first, for any value: a subclass of ``tuple``, ``list``, ``dict`` or
    ``str`` included, which ``json`` would otherwise write itself.  What its ``encode`` returns is written as
    it was before tuples were tagged (`_Payload`), so its ``decode`` is handed what it always was.

    A tuple, a subclass the registry does not take included, is tagged and read back as a plain tuple.  A
    dict key and a member of a set keep the untagged form, an array, which only a tuple can have been there.
    A dict whose keys are not all strings, or that carries one of the codec's markers, is wrapped, so that a
    plain string-keyed dict stays an ordinary object and a file that round-trips stays byte for byte the same.
    """

    def __init__(self) -> None:
        self.entries = tuple(_SERIALIZERS)
        self.classes = tuple(entry.cls for entry in self.entries)
        # 2 000 records of plain JSON: a call and a registry search per scalar cost 35%, ten registrations 190%
        unclaimed = _unclaimed(self.classes)
        # by identity: the class of a value may not hash
        self.plain = frozenset(id(kind) for kind in unclaimed if kind in _NATIVE)
        walks = ((dict, self._dict), (list, self._list))
        self.walks: dict[int, Callable[[Any, frozenset[int]], object]] = {
            id(kind): walk for kind, walk in walks if kind in unclaimed
        }
        self.str_unclaimed = str in unclaimed

    def encode(self, value: object, seen: frozenset[int] = frozenset()) -> object:
        kind = id(type(value))
        if kind in self.plain:
            return value
        walk = self.walks.get(kind)
        if walk is not None:
            return walk(value, _entered(value, seen))
        if self.classes and isinstance(value, self.classes):
            entry = next(entry for entry in self.entries if isinstance(value, entry.cls))
            return {"__type__": "custom", "__tag__": entry.tag, "__data__": _Payload(entry.encode(value))}
        if value is None or isinstance(value, (str, int, float)):
            return value
        if isinstance(value, (dict, list, tuple, set)):
            return self._container(value, _entered(value, seen))
        scalar = _scalar(value)
        if scalar is not None:
            return scalar
        if isinstance(value, enum.Enum):
            # as an earlier version wrote it, raw, so a dict in it shaped like a record of the codec's stays one
            return {
                "__type__": "enum",
                "__class__": value.__class__.__name__,
                "__module__": value.__class__.__module__,
                "__data__": _Payload(value.value),
            }
        if _held_as_instance(value):
            seen = _entered(value, seen)
            return {
                "__type__": "instance",
                "__class__": value.__class__.__name__,
                "__module__": value.__class__.__module__,
                "__data__": self.encode(_held(value), seen),
                **_model_state(value, lambda state: self.encode(state, seen)),
            }
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def _container(self, value: dict | list | tuple | set, seen: frozenset[int]) -> object:
        if isinstance(value, dict):
            return self._dict(value, seen)
        if isinstance(value, set):
            return {"__type__": "set", "__data__": [self.key(item, seen) for item in value]}
        written = self._list(value, seen)
        return written if isinstance(value, list) else {"__type__": "tuple", "__data__": written}

    def _dict(self, value: dict, seen: frozenset[int]) -> object:
        plain, str_unclaimed = self.plain, self.str_unclaimed
        keys_plain = all(
            (str_unclaimed and type(key) is str) or (isinstance(key, str) and not self._registered(key))
            for key in value
        )
        if keys_plain and not _RESERVED_MARKERS.intersection(value):
            return {key: item if id(type(item)) in plain else self.encode(item, seen) for key, item in value.items()}
        items = sorted(value.items(), key=lambda pair: repr(pair[0]))  # deterministic for mixed keys
        return {
            "__type__": "dict",
            "__data__": [[self.key(key, seen), self.encode(item, seen)] for key, item in items],
        }

    def _list(self, value: list | tuple, seen: frozenset[int]) -> list:
        plain = self.plain
        return [item if id(type(item)) in plain else self.encode(item, seen) for item in value]

    def key(self, key: object, seen: frozenset[int]) -> object:
        """A dict key or a member of a set: as `encode` writes it, except a tuple, which stays an untagged array."""
        if isinstance(key, tuple) and not self._registered(key):
            return [self.key(item, seen) for item in key]
        return self.encode(key, seen)

    def _registered(self, value: object) -> bool:
        return bool(self.classes) and isinstance(value, self.classes)


def _unclaimed(classes: tuple[type, ...]) -> list[type]:
    """The natives, ``dict`` and ``list`` that no class in *classes* can take, read by ``issubclass``.

    None where a class checks instances or subclasses its own way, or its subclass hook raises: then each value
    is asked of the registry by ``isinstance``, as the registry promises.
    """
    ordinary = all(
        type(cls).__instancecheck__ in _ORDINARY_CHECKS and type(cls).__subclasscheck__ in _ORDINARY_SUBCLASS_CHECKS
        for cls in classes
    )
    if not ordinary:
        return []
    try:
        return [kind for kind in (*_NATIVE, dict, list) if not issubclass(kind, classes)]
    except Exception:  # a class's own __subclasshook__ may raise anything, and only the shortcut is lost
        return []


def _entered(value: object, seen: frozenset[int]) -> frozenset[int]:
    """*seen* with the container or instance *value* added, refused where it is already there."""
    if id(value) in seen:
        # json cannot represent a cycle, so naming it beats a thousand frames of RecursionError
        raise ValueError("cannot snapshot a value that contains a circular reference")
    return seen | {id(value)}


def _held_as_instance(value: object) -> bool:
    """Whether a value is written as an instance: a dataclass, an attrs or pydantic instance, or an object with a
    ``__dict__`` that is no class."""
    return _slot_aware(value) or is_pydantic_model(value) or ("__dict__" in dir(value) and type(value) is not type)


def _scalar(value: object) -> dict | None:
    """A value of the built-in codec that holds no other value, tagged; ``None`` for any other."""
    if isinstance(value, complex):
        return {"__type__": "complex", "__data__": [value.real, value.imag]}
    if isinstance(value, datetime.datetime):
        # each suffix is added only when the value carries it, so a snapshot with neither microseconds nor
        # `tzinfo` keeps the historical format and stays readable by an older version
        fmt = "%Y-%m-%d %H:%M:%S.%f" if value.microsecond else "%Y-%m-%d %H:%M:%S"
        if value.tzinfo is not None:
            fmt += "%z"
        return {"__type__": "datetime", "__data__": value.strftime(fmt)}
    if isinstance(value, datetime.date):
        return {"__type__": "date", "__data__": value.isoformat()}
    if isinstance(value, datetime.time):
        return {"__type__": "time", "__data__": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {"__type__": "decimal", "__data__": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"__type__": "bytes", "__data__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, uuid.UUID):
        return {"__type__": "uuid", "__data__": str(value)}
    return None


_NESTED = frozenset({list, dict})
"""What `json` reads that holds other values."""


def _decode(node: Any) -> Any:
    """A value as `_encode` wrote it, read from the top down, so that what a serializer's ``encode`` returned is
    read as it always was (`_legacy_decode`) and handed to its ``decode``.  A file written before tuples were
    tagged reads as it did then."""
    # json hands back a list, a dict or a scalar, and a scalar skipped in place read 2 000 records in 2.2 ms, not 2.6
    if type(node) is list:
        return [_decode(item) if type(item) in _NESTED else item for item in node]
    if type(node) is not dict:
        return node
    if "__type__" not in node or "__data__" not in node:
        return {key: _decode(item) if type(item) in _NESTED else item for key, item in node.items()}
    kind, data = node["__type__"], node["__data__"]
    if kind == "tuple":
        return tuple(_decode(item) if type(item) in _NESTED else item for item in data)
    if kind == "dict":
        return {_decode_key(key): _decode(item) for key, item in data}
    if kind == "set":
        return {_decode_key(item) for item in data}
    if kind == "instance":
        # every field first, as before: a serializer's decode inside may load the module the class is in
        written = {key: _decode(item) for key, item in node.items()}
        target_class = _resolve_class(node["__module__"], node["__class__"])
        return written if target_class is None else _rebuilt(target_class, written)
    # an enum, a serializer's payload, a scalar: each is written as before tuples were tagged, and read so
    return _legacy_decode(node)


def _decode_key(node: Any) -> Any:
    """A dict key or a member of a set as `_encode_key` wrote it: an array can only have been a tuple."""
    if isinstance(node, list):
        return tuple(_decode_key(item) for item in node)
    return _decode(node)


def _legacy_decode(node: Any) -> Any:
    """JSON data written the way every value was before tuples were tagged, read as it was then: each object from
    the bottom up."""
    if isinstance(node, list):
        return [_legacy_decode(item) for item in node]
    if isinstance(node, dict):
        return _legacy_hook({key: _legacy_decode(item) for key, item in node.items()}, node)
    return node


def _prepare(value, _seen: frozenset[int] = frozenset()):
    """What every value was written as before tuples were tagged, kept for what a serializer's ``encode`` returns:
    dicts with a non-string key or a codec marker wrapped, a tuple as an array."""
    if isinstance(value, (dict, list, tuple)):
        if id(value) in _seen:
            raise ValueError("cannot snapshot a value that contains a circular reference")
        nested = _seen | {id(value)}
        if isinstance(value, dict):
            if all(isinstance(key, str) for key in value) and not _RESERVED_MARKERS.intersection(value):
                return {key: _prepare(item, nested) for key, item in value.items()}
            items = sorted(value.items(), key=lambda pair: repr(pair[0]))
            return {
                "__type__": "dict",
                "__data__": [[_prepare(key, nested), _prepare(item, nested)] for key, item in items],
            }
        return [_prepare(item, nested) for item in value]
    return value


def _hashable(item):
    """An element as it was written: JSON has no tuple, and a list cannot have been one, since it cannot hash."""
    return tuple(_hashable(inner) for inner in item) if isinstance(item, list) else item


def _rehash_key(key):
    """Restore a hashable dict key from its json form: a list can only be a re-encoded tuple (a list is
    not hashable and so could never have been a key), so convert it back to a tuple recursively."""
    if isinstance(key, list):
        return tuple(_rehash_key(item) for item in key)
    return key


class _LegacyEncoder(json.JSONEncoder):
    """The encoder every value went through before tuples were tagged, kept for what a serializer's ``encode``
    returns (`_Payload`)."""

    # `o` is what `JSONEncoder` names it, and pyright reads an override by parameter name
    def default(self, o):
        if isinstance(o, _Payload):
            return o.value
        for entry in _SERIALIZERS:
            if isinstance(o, entry.cls):
                return {"__type__": "custom", "__tag__": entry.tag, "__data__": entry.encode(o)}
        if isinstance(o, set):
            return {"__type__": "set", "__data__": list(o)}
        scalar = _scalar(o)
        if scalar is not None:
            return scalar
        if isinstance(o, enum.Enum):
            return {
                "__type__": "enum",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": o.value,
            }
        if _held_as_instance(o):
            return {
                "__type__": "instance",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": _prepare(_held(o)),
                **_model_state(o, _prepare),
            }
        return json.JSONEncoder.default(self, o)


def _legacy_hook(decoded, written):
    """The decoding of one JSON object as every value was read before tuples were tagged, from the bottom up:
    *decoded* is the object with its fields read, *written* the object as the file holds it."""
    if "__type__" in decoded and "__data__" in decoded:
        if decoded["__type__"] == "dict":
            return {_rehash_key(key): item for key, item in decoded["__data__"]}
        if decoded["__type__"] == "set":
            return {_hashable(item) for item in decoded["__data__"]}
        if decoded["__type__"] == "custom":
            tag = decoded.get("__tag__")
            for entry in _SERIALIZERS:
                if entry.tag == tag:
                    return entry.decode(decoded["__data__"])
            return decoded  # no serializer registered for this tag this run - leave the marker as-is
        if decoded["__type__"] == "enum":
            return _member(decoded, written)
        if decoded["__type__"] == "instance":
            target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
            return decoded if target_class is None else _rebuilt(target_class, decoded)
        return _scalar_read(decoded)
    return decoded


def _member(decoded: dict, written: dict) -> object:
    """The member an enum's record names, looked up by its value as an earlier version looked it up.

    Where no lookup finds the value once read, as a tuple holding a list read back as a list of lists, the one
    member whose own value is written as the record holds it is the member.  The record itself comes back where
    its class is not loaded.
    """
    target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
    if target_class is None:
        return decoded
    raw = decoded["__data__"]
    try:
        return target_class(raw)
    except ValueError:
        if isinstance(raw, list):
            with contextlib.suppress(ValueError):
                return target_class(_hashable(raw))
        text = json.dumps(written["__data__"], sort_keys=True)
        found = [member for member in target_class if _written_as(member.value, text)]
        if len(found) != 1:
            raise
        return found[0]


def _written_as(value: object, text: str) -> bool:
    """Whether *value*, written as an earlier version wrote an enum's value and read back as JSON, is *text*.

    Read back before it is compared: the file sorted an int key before it became text, ``2`` before ``10``.
    """
    try:
        return json.dumps(json.loads(json.dumps(value, cls=_LegacyEncoder)), sort_keys=True) == text
    except (TypeError, ValueError):
        return False


def _scalar_read(decoded: dict) -> object:
    """A value `_scalar` wrote, read back; the object itself where its tag is none of them."""
    kind, data = decoded["__type__"], decoded["__data__"]
    if kind == "complex":
        return complex(data[0], data[1])
    if kind == "datetime":
        tail = data[len("0000-00-00 00:00:00") :]  # the date part contains "-", so probe past the seconds
        fmt = "%Y-%m-%d %H:%M:%S"
        if "." in tail:
            fmt += ".%f"
        if "+" in tail or "-" in tail:
            fmt += "%z"
        return datetime.datetime.strptime(data, fmt)
    if kind == "date":
        return datetime.date.fromisoformat(data)
    if kind == "time":
        return datetime.time.fromisoformat(data)
    if kind == "decimal":
        return decimal.Decimal(data)
    if kind == "bytes":
        return base64.b64decode(data)
    if kind == "uuid":
        return uuid.UUID(data)
    return decoded


def _slot_aware(value: object) -> bool:
    """An attrs instance or a dataclass, the two kinds this reads through slots as well as a ``__dict__``.

    Slotted by default in attrs and on request in dataclasses, and without a ``__dict__`` either raised
    `Object of type ... is not JSON serializable`.  Other slotted objects stay refused: a slot of the
    standard library's is state nobody vouched for rebuilding.
    """
    return is_attrs_instance(value) or (dataclasses.is_dataclass(value) and not isinstance(value, type))


def _slot_names(target_class: type) -> set[str]:
    """Every slot the class and its bases declare, under the name it is stored by, mangled or not."""
    return {
        name
        for klass in target_class.__mro__
        for name, member in vars(klass).items()
        if isinstance(member, types.MemberDescriptorType)
    }


def _held(value: object) -> dict:
    """What an instance holds: its ``__dict__`` and any slot set on it.

    A slot is read past ``__getattr__``, so one never set stays unwritten: attrs computes a
    ``cached_property`` of a slotted class there, and writing a snapshot would have run it.
    """
    held = dict(vars(value)) if hasattr(value, "__dict__") else {}
    for name in _slot_names(type(value)) if _slot_aware(value) else ():
        try:
            held[name] = object.__getattribute__(value, name)
        except AttributeError:  # noqa: PERF203  # a slot never set holds nothing to write
            continue
    return held


def _model_state(value: object, encode: Callable[[dict], object]) -> dict:
    """What a pydantic model holds beside its ``__dict__``: the extras and the private state its ``==``
    compares, and the fields set, which ``model_dump(exclude_unset=True)`` reads, each written by *encode*.
    Nothing for any other value."""
    if not is_pydantic_model(value):
        return {}
    extra, private = getattr(value, "__pydantic_extra__", None), getattr(value, "__pydantic_private__", None)
    return {
        "__extra__": None if extra is None else encode(dict(extra)),
        "__private__": None if private is None else encode(dict(private)),
        "__fields_set__": sorted(getattr(value, "model_fields_set", ())),
    }


def _rebuilt(target_class: Any, written: dict) -> object:
    """An instance of *target_class* holding what was written, built without running its ``__init__``.

    A slot is set attribute by attribute, since a ``__dict__`` cannot hold it.
    """
    if is_pydantic_model_class(target_class):
        return _rebuilt_model(target_class, written)
    held = written["__data__"]
    instance = target_class.__new__(target_class)
    slots = _slot_names(target_class)
    if hasattr(instance, "__dict__"):
        instance.__dict__ = {name: value for name, value in held.items() if name not in slots}
    for name in slots & held.keys():
        object.__setattr__(instance, name, held[name])
    return instance


def _rebuilt_model(target_class: Any, written: dict) -> object:
    """A pydantic model in the state it was written in, through pydantic's own ``__setstate__``.

    Assigned a ``__dict__`` alone it had none of the state its ``==`` reads, and every snapshot of a model
    failed on the run after it was written.  `model_construct` runs `model_post_init`, and a subclass may
    override ``__new__`` or ``__setstate__``: reading a snapshot runs none of the caller's code.  A file
    written before the rest of the state was stored holds the fields alone, and reads as a model holding
    them and nothing else.
    """
    model = object.__new__(target_class)
    sys.modules["pydantic"].BaseModel.__setstate__(
        model,
        {
            "__dict__": written["__data__"],
            "__pydantic_extra__": written.get("__extra__"),
            "__pydantic_fields_set__": set(written.get("__fields_set__", written["__data__"])),
            "__pydantic_private__": written.get("__private__"),
        },
    )
    return model


def _resolve_class(module_name, class_name):
    """Resolve a class by module+name without importing anything (never runs arbitrary imports, per the
    snapshot security model); returns ``None`` if the module is not already imported or the name is absent."""
    if module_name not in sys.modules:
        return None
    return getattr(sys.modules[module_name], class_name, None)


def _save(name: str, val: object, *, keyed: bool) -> None:
    """Write *val* to the file *name*: the value itself, or where *keyed* a mapping of the keys a file holds
    several values under to each value.  The mapping is the file's own and never reaches a serializer."""
    # rendered whole first: `json.dump` calls `write` once per fragment where `dumps` joins them once, and
    # with `indent` neither reaches the C encoder.  Five thousand records: rendering to a string 1.4 ms
    # against 10.1 ms for the same rendering written fragment by fragment, 20.8 ms against 8.0 ms end to
    # end.  A value the encoder refuses now leaves no file behind either
    writer = _Writer()
    data = (
        {key: writer.encode(item) for key, item in val.items()}
        if keyed and isinstance(val, dict)
        else writer.encode(val)
    )
    text = json.dumps(data, indent=2, separators=(",", ": "), sort_keys=True, cls=_LegacyEncoder)
    tmp = f"{name}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as file_handle:
        file_handle.write(text)
    os.replace(tmp, name)


def _load(name: str) -> Any:
    # as UTF-8 and not as the platform's default: a file a formatter left unescaped read as mojibake under cp1252
    with open(name, encoding="utf-8") as file_handle:
        text = file_handle.read()
    data = json.loads(text)
    # no record of the codec's and no escape that could spell one: 2 000 records read in 1.6 ms, not 2.5
    return data if '"__type__"' not in text and "\\u" not in text else _decode(data)
