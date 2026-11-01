from __future__ import annotations

import base64
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


def _prepare(value, _seen: frozenset[int] = frozenset()):
    """Pre-process a value so ``json`` round-trips dicts that it otherwise mangles: dicts with a
    non-string key (which ``json`` coerces to a string) and dicts that collide with the codec's markers
    (which the decoder would misread).  Both are wrapped in a ``{"__type__": "dict", "__data__": [[k,
    v], ...]}`` envelope; a plain string-keyed dict without markers is left as an ordinary object so
    existing snapshots stay byte-identical."""
    if isinstance(value, (dict, list, tuple)):
        if id(value) in _seen:
            # json cannot represent a cycle, so naming it beats a thousand frames of RecursionError
            raise ValueError("cannot snapshot a value that contains a circular reference")
        nested = _seen | {id(value)}
        if isinstance(value, dict):
            if all(isinstance(key, str) for key in value) and not _RESERVED_MARKERS.intersection(value):
                return {key: _prepare(item, nested) for key, item in value.items()}
            items = sorted(value.items(), key=lambda pair: repr(pair[0]))  # deterministic for mixed keys
            return {
                "__type__": "dict",
                "__data__": [[_prepare(key, nested), _prepare(item, nested)] for key, item in items],
            }
        # a tuple comes back a list: `_rehash_key` restores one only where it was a dict key
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


class _Encoder(json.JSONEncoder):
    # `o` is what `JSONEncoder` names it, and pyright reads an override by parameter name
    def default(self, o):
        for entry in _SERIALIZERS:
            if isinstance(o, entry.cls):
                return {"__type__": "custom", "__tag__": entry.tag, "__data__": entry.encode(o)}
        if isinstance(o, set):
            return {"__type__": "set", "__data__": list(o)}
        elif isinstance(o, complex):
            return {"__type__": "complex", "__data__": [o.real, o.imag]}
        elif isinstance(o, datetime.datetime):
            # each suffix is added only when the value carries it, so a snapshot with neither microseconds nor
            # `tzinfo` keeps the historical format and stays readable by an older version
            fmt = "%Y-%m-%d %H:%M:%S.%f" if o.microsecond else "%Y-%m-%d %H:%M:%S"
            if o.tzinfo is not None:
                fmt += "%z"
            return {"__type__": "datetime", "__data__": o.strftime(fmt)}
        elif isinstance(o, datetime.date):
            return {"__type__": "date", "__data__": o.isoformat()}
        elif isinstance(o, datetime.time):
            return {"__type__": "time", "__data__": o.isoformat()}
        elif isinstance(o, decimal.Decimal):
            return {"__type__": "decimal", "__data__": str(o)}
        elif isinstance(o, (bytes, bytearray)):
            return {"__type__": "bytes", "__data__": base64.b64encode(bytes(o)).decode("ascii")}
        elif isinstance(o, uuid.UUID):
            return {"__type__": "uuid", "__data__": str(o)}
        elif isinstance(o, enum.Enum):
            return {
                "__type__": "enum",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                "__data__": o.value,
            }
        elif _slot_aware(o) or is_pydantic_model(o) or ("__dict__" in dir(o) and type(o) is not type):
            return {
                "__type__": "instance",
                "__class__": o.__class__.__name__,
                "__module__": o.__class__.__module__,
                # prepared like any other mapping: a non-string key inside an attribute came back a string
                "__data__": _prepare(_held(o)),
                **_model_state(o),
            }
        return json.JSONEncoder.default(self, o)


class _Decoder(json.JSONDecoder):
    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self._object_hook)

    def _object_hook(self, decoded):
        if "__type__" in decoded and "__data__" in decoded:
            if decoded["__type__"] == "dict":
                return {_rehash_key(key): item for key, item in decoded["__data__"]}
            elif decoded["__type__"] == "set":
                return {_hashable(item) for item in decoded["__data__"]}
            elif decoded["__type__"] == "complex":
                return complex(decoded["__data__"][0], decoded["__data__"][1])
            elif decoded["__type__"] == "datetime":
                raw = decoded["__data__"]
                tail = raw[len("0000-00-00 00:00:00") :]  # the date part contains "-", so probe past the seconds
                fmt = "%Y-%m-%d %H:%M:%S"
                if "." in tail:
                    fmt += ".%f"
                if "+" in tail or "-" in tail:
                    fmt += "%z"
                return datetime.datetime.strptime(raw, fmt)
            elif decoded["__type__"] == "date":
                return datetime.date.fromisoformat(decoded["__data__"])
            elif decoded["__type__"] == "time":
                return datetime.time.fromisoformat(decoded["__data__"])
            elif decoded["__type__"] == "decimal":
                return decimal.Decimal(decoded["__data__"])
            elif decoded["__type__"] == "bytes":
                return base64.b64decode(decoded["__data__"])
            elif decoded["__type__"] == "uuid":
                return uuid.UUID(decoded["__data__"])
            elif decoded["__type__"] == "custom":
                tag = decoded.get("__tag__")
                for entry in _SERIALIZERS:
                    if entry.tag == tag:
                        return entry.decode(decoded["__data__"])
                return decoded  # no serializer registered for this tag this run - leave the marker as-is
            elif decoded["__type__"] == "enum":
                target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
                if target_class is None:
                    return decoded
                raw = decoded["__data__"]
                try:
                    return target_class(raw)
                except ValueError:
                    if not isinstance(raw, list):
                        raise
                    return target_class(_hashable(raw))
            elif decoded["__type__"] == "instance":
                target_class = _resolve_class(decoded["__module__"], decoded["__class__"])
                if target_class is None:
                    return decoded
                return _rebuilt(target_class, decoded)
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


def _model_state(value: object) -> dict:
    """What a pydantic model holds beside its ``__dict__``: the extras and the private state its ``==``
    compares, and the fields set, which ``model_dump(exclude_unset=True)`` reads.  Nothing for any other value."""
    if not is_pydantic_model(value):
        return {}
    extra, private = getattr(value, "__pydantic_extra__", None), getattr(value, "__pydantic_private__", None)
    return {
        "__extra__": None if extra is None else _prepare(dict(extra)),
        "__private__": None if private is None else _prepare(dict(private)),
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


def _save(name, val):
    # rendered whole first: `json.dump` calls `write` once per fragment where `dumps` joins them once, and
    # with `indent` neither reaches the C encoder.  Five thousand records: rendering to a string 1.4 ms
    # against 10.1 ms for the same rendering written fragment by fragment, 20.8 ms against 8.0 ms end to
    # end.  A value the encoder refuses now leaves no file behind either
    text = json.dumps(_prepare(val), indent=2, separators=(",", ": "), sort_keys=True, cls=_Encoder)
    tmp = f"{name}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as file_handle:
        file_handle.write(text)
    os.replace(tmp, name)


def _load(name):
    # as UTF-8 and not as the platform's default: a file a formatter left unescaped read as mojibake under cp1252
    with open(name, encoding="utf-8") as file_handle:
        return json.load(file_handle, cls=_Decoder)
