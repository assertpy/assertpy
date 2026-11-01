"""Contract-drift detection for `assert_conforms(..., exact=True)`.

Reports fields a raw payload carries that its pydantic v2 model does **not** declare - the silent API
growth that `model_validate` drops by default.  Duck-typed on ``model_fields`` (no pydantic import),
alias-aware, and walked beside the validated instance, so every nested model is checked where pydantic put one.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import decimal
import enum
import fractions
import inspect
import json
import marshal
import operator
import pathlib
import sys
import types
import uuid
from functools import reduce
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ForwardRef,
    Literal,
    NamedTuple,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from ..errors import DiffEntry, Step
from ._introspection import definition_of

if TYPE_CHECKING:
    from collections.abc import Callable


def _alias_sources(alias: object) -> list[tuple[object, ...]]:
    """The payload paths an alias reads, in the order pydantic tries them (str, ``AliasChoices``, ``AliasPath``)."""
    if isinstance(alias, str):
        return [(alias,)]
    choices = getattr(alias, "choices", None)
    if choices is not None:
        return [source for choice in choices for source in _alias_sources(choice)]
    path = getattr(alias, "path", None)
    return [tuple(path)] if path else []


def _spellings(name: str, info: Any) -> list[object]:
    """Every key that spells a field: its name, the first key of each alias validation may read it by, and the alias
    it is dumped under.  Which of them validation reads is the config's to say (`_field_sources`)."""
    keys: list[object] = [name]
    for alias in (getattr(info, "alias", None), getattr(info, "validation_alias", None)):
        if alias is not None:
            keys += [source[0] for source in _alias_sources(alias)]
    shown = getattr(info, "serialization_alias", None)
    return [*keys, shown] if isinstance(shown, str) else keys


def _field_sources(name: str, info: Any, config: Any) -> tuple[tuple[object, ...], ...]:
    """Where pydantic reads field *name*, in the order it looks: its alias sources, then the name if allowed."""
    validation_alias = getattr(info, "validation_alias", None)
    alias = validation_alias if validation_alias is not None else getattr(info, "alias", None)
    if alias is None:
        return ((name,),)
    sources = _alias_sources(alias) if config.get("validate_by_alias") is not False else []
    by_name = config.get("validate_by_name")
    if by_name if by_name is not None else config.get("populate_by_name"):
        sources.append((name,))
    return tuple(sources)


_KEYLESS = (
    int,
    float,
    complex,
    str,
    bytes,
    bytearray,
    type(None),
    decimal.Decimal,
    fractions.Fraction,
    datetime.date,
    datetime.time,
    datetime.timedelta,
    uuid.UUID,
    enum.Enum,
    pathlib.PurePath,
)
_PLAIN_ORIGINS = {
    list,
    tuple,
    set,
    frozenset,
    dict,
    collections.abc.Sequence,
    collections.abc.MutableSequence,
    collections.abc.Set,
    collections.abc.MutableSet,
    collections.abc.Mapping,
    collections.abc.MutableMapping,
    collections.abc.Iterable,
    collections.abc.Iterator,
    collections.abc.Collection,
}


def _may_hold_model(annotation: object, outer: bool = True) -> bool:
    """Whether a model can be built anywhere under a field's *annotation*; only a type made of plain parts says no.

    ``Any`` says yes at the top of the field, where only a validator puts a model and the payload's own object kept
    there costs one identity check, and no inside a container, where passing each kept item costs what skipping saves.
    """
    if annotation is Any or annotation is object:
        return outer
    if annotation in (list, tuple, set, frozenset, dict):
        return False
    origin = get_origin(annotation)
    if origin is Literal:
        return False
    if origin is Annotated:
        return _may_hold_model(get_args(annotation)[0], outer)
    if origin is Union or origin is types.UnionType:
        return any(_may_hold_model(arg, outer) for arg in get_args(annotation))
    if origin in _PLAIN_ORIGINS:
        return any(_may_hold_model(arg, outer=False) for arg in get_args(annotation) if arg is not Ellipsis)
    return origin is not None or not isinstance(annotation, type) or not issubclass(annotation, _KEYLESS)


def _alternatives(annotation: object) -> tuple[object, ...]:
    """The members of a union, `Annotated` and nested unions opened, or the annotation alone."""
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if get_origin(annotation) in (Union, types.UnionType):
        return tuple(member for argument in get_args(annotation) for member in _alternatives(argument))
    return (annotation,)


_ITEM_ORIGINS = frozenset(
    {
        list,
        tuple,
        set,
        frozenset,
        collections.deque,
        collections.abc.Sequence,
        collections.abc.MutableSequence,
        collections.abc.Set,
        collections.abc.MutableSet,
        collections.abc.Collection,
        collections.abc.Iterable,
    }
)


_MAPPING_ORIGINS = frozenset({dict, collections.abc.Mapping, collections.abc.MutableMapping})

_Declared = tuple[object, object, Any]
"""A declared type, the model class whose field declared it, whose config its validation ran in, and the schema
pydantic built for it in that class, where the walk came by one.  The type is ``None`` where it cannot be read (text,
the place of a type variable), and the schema alone declares then."""


class _Record(NamedTuple):
    """A `TypedDict` or a dataclass as the walk came to it: by the schema that validates it, by its class, or both."""

    node: Any
    kind: Any


class _Unsure(NamedTuple):
    """The `TypedDict`s one of which may have built a dict, where its declaration names several, and the schemas
    declared *beside* them that may build a dict as well: a ``dict``, or one that does not say what it builds."""

    records: tuple[Any, ...]
    beside: tuple[Any, ...]


_ITEM_SCHEMAS = frozenset({"list", "set", "frozenset", "generator", "tuple", "tuple-positional", "tuple-variable"})
_NO_DICT = _ITEM_SCHEMAS | {
    "none",
    "bool",
    "int",
    "float",
    "decimal",
    "complex",
    "str",
    "bytes",
    "date",
    "time",
    "datetime",
    "timedelta",
    "literal",
    "enum",
    "url",
    "multi-host-url",
    "uuid",
    "model",
    "dataclass",
}
"""The schemas that never build a plain dict; any other beside a `TypedDict` leaves open which of them built one."""

_ANY: dict[str, Any] = {"type": "any"}
"""Stands for a schema that does not say what it builds."""

_Hop = tuple[Any, object, object] | None
"""Where the walk stands in the payload, ``None`` at its root: the hop this one was taken from, what it is named by,
and how it was taken (the keys followed for a field or a key, ``None`` for a position, a `Step` for a member of a
collection that keeps no positions).  A hop into a mapping's key, and one into what JSON text decodes to, is named
by nothing.  Read out only where something is found (`_placed`)."""

_Found = tuple[_Hop, object] | tuple[_Hop, object, str]
"""An undeclared field: where it stands and the value sent there, and, where the key spells a field of the model, why
validation did not read it."""

_DECLARED: dict[tuple[object, object], tuple[Any, Any]] = {}
"""What a declaration says a container built from it holds, per declaration and kind of container: worked out once,
since a list of 1000 orders asks it for each order.  At most 1024 entries (`_remember`)."""


def _remember(cache: dict[Any, tuple[Any, Any]], key: object, declared: object, answer: object, bound: int) -> None:
    """Keep *answer* for *declared* under *key*, beside the declaration so the id stays its own.  A full *cache* starts
    over rather than refusing new entries: a long run fills it early, and what it asks now is what it asks again."""
    if len(cache) >= bound:
        cache.clear()
    cache[key] = (declared, answer)


_REFS: dict[Any, tuple[object, dict[str, Any]]] = {}
"""Per class, beside the validator it was read with: each schema its core schema defines under a name.  At most 256
classes (`_remember`)."""


def _refs(holder: Any) -> dict[str, Any]:
    """The schemas the core schema of *holder* names, by the name a reference to them carries."""
    validator = getattr(holder, "__pydantic_validator__", None)
    known = _REFS.get(holder)
    if known is not None and known[0] is validator:
        return known[1]
    refs: dict[str, Any] = {}
    pending: list[Any] = [getattr(holder, "__pydantic_core_schema__", None)]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if isinstance(node.get("ref"), str):
                refs[node["ref"]] = node
            pending.extend(value for key, value in node.items() if key not in ("serialization", "metadata", "default"))
        elif isinstance(node, (list, tuple)):
            pending.extend(node)
    _remember(_REFS, holder, validator, refs, 256)
    return refs


def _schema_kind(node: object) -> object:
    return node.get("type") if isinstance(node, dict) else None


def _choices(node: object, owner: object) -> list[Any]:
    """The schemas validation chooses between at *node*, in the order it lists them, with what only wraps a schema
    opened: a default, ``None`` beside it, a reference to a definition, a union and the unions inside it, what JSON
    text is decoded into, and a validator around a schema, which is read as keeping the kind of what it validates, as
    one in `Annotated` is."""
    refs = _refs(owner)
    pending, leaves, met = [node], [], set()
    while pending:
        current: Any = pending.pop()
        kind = _schema_kind(current)
        if id(current) in met:
            continue
        met.add(id(current))
        if kind in ("default", "nullable", "definitions", "json", "function-before", "function-after", "function-wrap"):
            pending.append(current.get("schema"))
        elif kind == "definition-ref":
            pending.append(refs.get(current.get("schema_ref")))
        elif kind == "union":
            members = [choice[0] if isinstance(choice, tuple) else choice for choice in current.get("choices", ())]
            pending.extend(reversed(members))
        elif kind == "tagged-union":
            pending.extend(
                reversed([choice for choice in current.get("choices", {}).values() if isinstance(choice, dict)])
            )
        else:
            leaves.append(current)
    return leaves


def _either(nodes: list[Any]) -> Any:
    """One schema standing for a choice between *nodes*, or the only one of them."""
    return nodes[0] if len(nodes) == 1 else {"type": "union", "choices": nodes}


def _keyed_under(node: object, owner: object) -> list[Any]:
    """The schemas anywhere under *node* that take named keys and drop the rest: a `TypedDict`, a model, a dataclass,
    short of what each of them declares in turn."""
    refs = _refs(owner)
    pending, found, met = [node], [], set()
    while pending:
        current: Any = pending.pop()
        kind = _schema_kind(current)
        if id(current) in met:
            continue
        met.add(id(current))
        if kind in ("typed-dict", "model", "dataclass"):
            found.append(current)
        elif kind == "definition-ref":
            pending.append(refs.get(current.get("schema_ref")))
        elif isinstance(current, dict):
            pending.extend(
                value for key, value in current.items() if key not in ("serialization", "metadata", "default")
            )
        elif isinstance(current, (list, tuple)):
            pending.extend(current)
    return found


def _records_under(node: object, owner: object) -> list[Any]:
    """The `TypedDict` schemas anywhere under a schema, short of the models and dataclasses in it, which build no
    dict: what a schema that does not say what it builds may build a dict by."""
    return [found for found in _keyed_under(node, owner) if found.get("type") == "typed-dict"]


def _item_nodes(node: object, owner: object) -> tuple[tuple[Any, ...] | None, Any] | None:
    """What the schema *node* says the items of a sequence or a set built from it are: a schema per position of a fixed
    tuple, or one for every item, a choice between them where *node* offers several containers or a tuple with a
    variable part; ``None`` where it declares no such container and hides no `TypedDict`.

    A schema beside the containers that does not say what it builds is one of the choices as it is: a `TypedDict`
    inside it is looked for at whatever depth the walk meets a dict (`_records_under`).
    """
    leaves = [] if node is None else _choices(node, owner)
    holding = [leaf for leaf in leaves if _schema_kind(leaf) in _ITEM_SCHEMAS]
    unknown = [leaf for leaf in leaves if _schema_kind(leaf) not in _NO_DICT | {"typed-dict", "dict"}]
    if not holding and not any(_records_under(leaf, owner) for leaf in unknown):
        return None
    every: list[Any] = []
    for leaf in holding:
        items = leaf.get("items_schema", _ANY)
        every += items if isinstance(items, list) else [items]
    kind = _schema_kind(leaves[0])
    fixed = kind == "tuple-positional" or (kind == "tuple" and leaves[0].get("variadic_item_index") is None)
    if len(leaves) == 1 and fixed:
        return tuple(every), None
    return None, _either([*every, *unknown])


def _missing_is_its_own(cls: Any) -> bool:
    """Whether the enum *cls* answers a value it does not name by a `_missing_` other than `Enum`'s.

    Its constructor calls that method, and a schema names it only where pydantic calls it in the constructor's
    place.  A class that cannot be read says yes.
    """
    try:
        found = definition_of(cls, "_missing_")
    # no class: its tree is read off the slots of `type`, so nothing the class or its metaclass says is asked
    except TypeError:
        return True
    return found is None or found[0] is not enum.Enum


_OWN_CODE: dict[type, tuple[object, bool]] = {}
"""Per model class, beside the validator it was read with: whether validating by it runs code that is not pydantic's.
At most 256 classes (`_remember`)."""


def runs_own_code(model: Any) -> bool:
    """Whether validation by *model* runs code of its own anywhere in its schema: a validator, a `model_post_init`
    (private attributes bring one), a custom `__init__`, a dataclass `__post_init__`, a called class, a named tuple,
    whose class is called as well, an enum's own `_missing_`.

    Pydantic's own validation never changes the payload it is given, so only such a model can leave it other than
    it was sent.  A default factory that takes no data is not counted: validation hands it nothing of the payload.
    A schema that cannot be read says yes.
    """
    validator = getattr(model, "__pydantic_validator__", None)
    known = _OWN_CODE.get(model)
    if known is not None and known[0] is validator:
        return known[1]
    schema = getattr(model, "__pydantic_core_schema__", None)
    answer = True
    if isinstance(schema, dict):
        answer, pending = False, [schema]
        while pending and not answer:
            node = pending.pop()
            if isinstance(node, dict):
                kind = node.get("type")
                answer = isinstance(kind, str) and bool(
                    kind.startswith("function-")
                    or kind in ("call", "named-tuple")
                    or node.get("post_init")
                    or node.get("custom_init")
                    or node.get("default_factory_takes_data")
                    or node.get("missing")
                    or (kind == "enum" and _missing_is_its_own(node.get("cls")))
                    or callable(node.get("discriminator"))
                )
                # a serialiser runs at dump time, metadata is never validated, a default may hold itself
                pending.extend(
                    value for key, value in node.items() if key not in ("serialization", "metadata", "default")
                )
            elif isinstance(node, (list, tuple)):
                pending.extend(node)
    _remember(_OWN_CODE, model, validator, answer, 256)
    return answer


_Sent = tuple[Any, list[tuple[Any, Any]] | None]
"""A payload as it was before validation: an independent copy of it, or, where no such copy can be made, ``None``
and every plain `dict` and `list` inside it beside a copy of what it held."""


def sent_record(payload: Any) -> _Sent:
    """*payload* as it is now, before validation, to put it back by (`put_as_sent`).

    Plain data, which a decoded JSON document is, is copied whole by `marshal`: 1.2 us for an order and 125 us for a
    thousand lines, where recording each container took 2.2 us and 330 us.  A payload `marshal` refuses (a `datetime`,
    a `Decimal`, a subclass, one nested too deep) is recorded container by container (`_held_now`).
    """
    try:
        return marshal.loads(marshal.dumps(payload)), None
    except ValueError:
        return None, _held_now(payload)


def _held_now(payload: Any) -> list[tuple[Any, Any]]:
    """Every plain `dict` and `list` inside *payload*, each beside a copy of what it holds now.

    Reached through dicts, lists and tuples and their subclasses; only the plain ones are recorded, since putting
    a subclass back would go through methods of its own.
    """
    record: list[tuple[Any, Any]] = []
    pending: list[Any] = [payload]
    met: set[int] = set()
    while pending:
        node = pending.pop()
        plain = type(node) is dict or type(node) is list
        if not (plain or isinstance(node, (dict, list, tuple))) or id(node) in met:
            continue
        met.add(id(node))
        if plain:
            record.append((node, dict(node) if type(node) is dict else list(node)))
        # read as the builtin holds it: a subclass's own `values` or `__iter__` is not the check's to call
        if isinstance(node, dict):
            children: Any = dict.values(node)
        else:
            children = list.__iter__(node) if isinstance(node, list) else tuple.__iter__(node)
        pending += [child for child in children if type(child) not in (str, int, float, bool, types.NoneType)]
    return record


def put_as_sent(payload: Any, sent: _Sent) -> list[tuple[Any, Any]]:
    """Put what validation changed inside *payload* back as it was *sent*, and return each container this changed
    beside what validation left in it, for `put_back`.

    So the walk reads the payload as it was sent: a validator that changed its input in place is read as one that
    returned a changed copy.  Against a whole copy, changed means no longer equal, and the payload's own dicts and
    lists, reached through its tuples, are refilled from the copy.  Container by container, changed means another
    object under a key or at an index, or other keys, and each container is refilled with the objects it held, so
    what validation retained is still met as the payload's own.
    """
    whole, parts = sent
    left: list[tuple[Any, Any]] = []
    if parts is None:
        try:
            same = payload == whole
        # a payload that holds itself, or a value a validator put in whose own `==` raises: not what was sent
        except Exception:
            same = False
        pending, met = ([] if same else [(payload, whole)]), set()
        while pending:
            node, was = pending.pop()
            # a container the payload holds twice is refilled once, or what validation left in it is lost
            if id(node) in met:
                continue
            met.add(id(node))
            if type(node) is dict or type(node) is list:
                left.append((node, node.copy()))
                _refill(node, was)
            elif type(node) is tuple:
                pending += zip(node, was, strict=True)
        return left
    for node, was in parts:
        if type(node) is dict:
            same = node.keys() == was.keys() and all(map(operator.is_, node.values(), was.values()))
        else:
            same = len(node) == len(was) and all(map(operator.is_, node, was))
        if not same:
            left.append((node, node.copy()))
            _refill(node, was)
    return left


def kept_apart(entries: list[DiffEntry]) -> list[DiffEntry]:
    """*entries* holding copies of the plain dicts, lists and tuples they hold, which `put_back` is about to refill.

    One copy of each container for all of them, so what the entries share they still share, cycles are kept, and
    anything else stays the payload's own object.  Made without recursion: a payload nests deeper than the stack goes.
    What lies in JSON text is the walk's own reading of it, which nothing refills, and stays the object the steps
    after its ``json`` step lead to.
    """
    known: dict[int, Any] = {}
    pending: list[tuple[Any, Any]] = []
    read = [any(step.kind == "json" for step in entry.steps) for entry in entries]
    copies = [
        entry.actual if decoded else _copied(entry.actual, known, pending)
        for entry, decoded in zip(entries, read, strict=True)
    ]
    while pending:
        copy, source = pending.pop()
        if type(source) is dict:
            copy.update((key, _copied(part, known, pending)) for key, part in source.items())
        else:
            copy.extend(_copied(part, known, pending) for part in source)
    return [dataclasses.replace(entry, actual=copy) for entry, copy in zip(entries, copies, strict=True)]


def _copied(value: Any, known: dict[int, Any], pending: list[tuple[Any, Any]]) -> Any:
    """The copy *value* is known by: a dict or a list is made empty and left *pending* to be filled, a tuple is built
    at once from the copies of its items (`_tuple_copied`), anything else is itself."""
    kind = type(value)
    if kind is not dict and kind is not list and kind is not tuple:
        return value
    copy = known.get(id(value))
    if copy is None:
        if kind is tuple:
            return _tuple_copied(value, known, pending)
        copy = known[id(value)] = kind()
        pending.append((copy, value))
    return copy


def _tuple_copied(value: tuple, known: dict[int, Any], pending: list[tuple[Any, Any]]) -> tuple:
    """A tuple of the copies of what *value* holds, the tuples directly inside it built first; the tuple itself where
    nothing it holds was copied, which is every tuple a dict has for a key."""
    building: list[tuple[tuple, list[Any]]] = [(value, [])]
    while True:
        source, items = building[-1]
        if len(items) < len(source):
            item = source[len(items)]
            if type(item) is tuple and id(item) not in known:
                building.append((item, []))
            else:
                items.append(_copied(item, known, pending))
            continue
        unchanged = all(map(operator.is_, items, source))
        built = known[id(source)] = source if unchanged else tuple(items)
        building.pop()
        if not building:
            return built
        building[-1][1].append(built)


def put_back(left: list[tuple[Any, Any]]) -> None:
    """Return each container `put_as_sent` changed to what validation left in it."""
    for node, held in left:
        _refill(node, held)


def _refill(node: Any, content: Any) -> None:
    if type(node) is dict:
        node.clear()
        node.update(content)
    else:
        node[:] = content


def _validated_again(validate: Callable[[Any], Any], given: Any, held: collections.abc.Iterable[Any]) -> Any:
    """What *validate* builds from *given*, with each part in *held* put back as it was once it has run.

    *held* names the parts the walk already holds where the validator has code of its own, and nothing where it has
    none: run again on the payload, such a validator can change its input in place, which is what the walk is about
    to read.  The payload itself is given, not a copy, so what validation retains is still the payload's own object,
    and each part is recorded container by container, so a container it shares with the rest of the payload is put
    back as the very object it is.
    """
    records = [(part, (None, _held_now(part))) for part in held]
    try:
        return validate(given)
    finally:
        for part, record in records:
            put_as_sent(part, record)


def _declared_container(declared: _Declared | None) -> tuple[tuple[_Declared, ...] | None, _Declared | None] | None:
    """What *declared* says the items of a container built from it are declared as: one declaration per position of a
    fixed tuple, or one for every item; ``None`` where it does not say.

    Only a declaration that leaves validation no choice says (`_sole_member`): which member of a union validation took
    depends on what the field's own validators made of the payload, and the kind of container they left does not tell.
    """
    if declared is None:
        return None
    key = (id(declared), "items")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner, node = declared
    container = _sole_member(annotation)
    under = _item_nodes(node, owner)
    items = None
    if get_origin(container) in _ITEM_ORIGINS and get_args(container):
        arguments = get_args(container)
        if _is_fixed_tuple(container):
            told = None if under is None else under[0]
            placed: Any = told if told is not None and len(told) == len(arguments) else [None] * len(arguments)
            items = (tuple((argument, owner, schema) for argument, schema in zip(arguments, placed, strict=True)), None)
        else:
            items = (None, (arguments[0], owner, None if under is None else under[1]))
    elif under is not None:
        # the type is not read here, so the schema alone says what the items are
        positional, common = under
        items = (
            None if positional is None else tuple((None, owner, schema) for schema in positional),
            None if common is None else (None, owner, common),
        )
    _remember(_DECLARED, key, declared, items, 1024)
    return items


def _declared_mapping(declared: _Declared) -> tuple[_Declared | None, _Record | _Unsure | None]:
    """What *declared* says of a mapping built from it: the declaration of its values, or the `TypedDict` it is, which
    declares each key on its own; ``None`` for what it does not say.

    The schema says first.  One `TypedDict` among its choices, beside types that never build a dict, is that record.
    Several, or one beside a schema that may build a dict as well, are all that is known (`_Unsure`): the walk does not
    choose between them as validation did.  A `TypedDict` inside a schema that does not say what it builds is one of
    them.  Without a schema the type says, where it leaves validation no choice.
    """
    key = (id(declared), "values")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner, node = declared
    leaves = [] if node is None else _choices(node, owner)
    records = [leaf for leaf in leaves if _schema_kind(leaf) == "typed-dict"]
    beside = [leaf for leaf in leaves if _schema_kind(leaf) not in _NO_DICT | {"typed-dict"}]
    unknown = [leaf for leaf in beside if _schema_kind(leaf) != "dict"]
    hidden = [record for leaf in unknown for record in _records_under(leaf, owner)]
    mapping = _sole_member(annotation)
    kind = get_origin(mapping) or mapping
    written = kind if isinstance(kind, type) and issubclass(kind, dict) and hasattr(kind, "__required_keys__") else None
    answer: tuple[_Declared | None, _Record | _Unsure | None] = (None, None)
    if len(records) == 1 and not beside:
        answer = (None, _Record(records[0], written))
    elif records or hidden:
        answer = (None, _Unsure((*records, *hidden), tuple(beside)))
    elif written is not None:
        answer = (None, _Record(None, written))
    else:
        values = _values_beside(beside)
        under = _either(values) if len(unknown) < len(beside) else None
        if get_origin(mapping) in _MAPPING_ORIGINS and len(get_args(mapping)) == 2:
            answer = ((get_args(mapping)[1], owner, under), None)
        elif under is not None:
            answer = ((None, owner, under), None)
    _remember(_DECLARED, key, declared, answer, 1024)
    return answer


def _values_beside(beside: collections.abc.Iterable[Any]) -> list[Any]:
    """What the schemas *beside* a `TypedDict` say of the values of a dict they build: the values a ``dict`` declares,
    and a schema that does not say what it builds as it is, for what may lie inside it."""
    return [leaf.get("values_schema", _ANY) if _schema_kind(leaf) == "dict" else leaf for leaf in beside]


def _sole_member(annotation: object) -> object:
    """*annotation* without `Annotated` and without ``None`` beside it; ``None`` where a union leaves a choice."""
    members = [member for member in _alternatives(annotation) if member is not type(None)]
    return members[0] if len(members) == 1 else None


def _chooses(annotation: object) -> bool:
    """Whether validation chose anywhere in *annotation* above the models it names: between two or more members of a
    union besides ``None``, or inside a named type alias (`typing` or `typing_extensions`, plain or parametrized),
    which is not opened.  A type that is not read (``None``), and a type variable, count as a choice."""
    members = [member for member in _alternatives(annotation) if member is not type(None)]
    if any(member is None or isinstance(member, TypeVar) for member in members):
        return True
    aliases = tuple(
        kind
        for module in ("typing", "typing_extensions")
        if isinstance(kind := getattr(sys.modules.get(module), "TypeAliasType", None), type)
    )
    if len(members) > 1 or any(
        isinstance(named, aliases) for member in members for named in (member, get_origin(member))
    ):
        return True
    return any(_chooses(argument) for member in members for argument in get_args(member) if argument is not Ellipsis)


def _is_fixed_tuple(container: object) -> bool:
    arguments = get_args(container)
    return get_origin(container) is tuple and not (len(arguments) == 2 and arguments[1] is Ellipsis)


def _item_declarations(declared: _Declared | None, count: int) -> list[_Declared | None]:
    """The declaration of each of *count* items of a container built from *declared*, by position where a fixed tuple
    declares one."""
    items = _declared_container(declared)
    if items is None:
        return [None] * count
    positional, common = items
    if positional is None:
        return [common] * count
    return [positional[index] if index < len(positional) else None for index in range(count)]


_ADAPTERS: dict[int, tuple[_Declared, Any]] = {}
"""A pydantic `TypeAdapter` per declaration, or ``None`` where none can be built: building one costs a schema.  At
most 256 entries (`_remember`)."""


def _adapter(declared: _Declared) -> Any:
    """A `TypeAdapter` for a declared type, in the config of the model that declared it, from the pydantic the models
    came from; ``None`` where there is none."""
    known = _ADAPTERS.get(id(declared))
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner, _ = declared
    adapter_class = getattr(sys.modules.get("pydantic"), "TypeAdapter", None)
    adapter = None
    if adapter_class is not None:
        # a schema pydantic refuses: TypeError in 2.0, RuntimeError in 2.13, NameError for a forward reference
        try:
            config = getattr(owner, "model_config", None) or getattr(owner, "__pydantic_config__", None)
            adapter = adapter_class(annotation, config=config or None)
        except (TypeError, RuntimeError, NameError):
            adapter = None
    _remember(_ADAPTERS, id(declared), declared, adapter, 256)
    return adapter


_FieldReads = tuple[tuple[str, tuple[tuple[object, ...], ...], _Declared], ...]

_Sources = tuple[tuple[object, ...], ...]
_KeyReads = tuple[frozenset[object], tuple[_Sources, ...], dict[object, _Sources]]
"""Which keys of a payload a model or a record reads: the keys it reads wherever they are sent, the sources of each
field that may be read from another place, and every key that spells a field beside where validation reads that
field."""


def _key_reads(fields: collections.abc.Iterable[tuple[_Sources, collections.abc.Iterable[object]]]) -> _KeyReads:
    """The keys the *fields* are read from, each given as its sources in the order validation tries them and the
    keys that spell it.

    A field is read from the first of its sources a payload holds whole.  The first of them, where it is a key and
    no path, is read wherever it is sent.  A later one is read only where those before it are absent, and a path only
    where it leads somewhere, so those are told per payload (`_unread`): of two spellings sent validation drops the
    later, and the key a path starts at is dropped where the path leads nowhere.
    """
    sure: set[object] = set()
    chosen: list[_Sources] = []
    spelled: dict[object, _Sources] = {}
    for sources, spellings in fields:
        if sources and len(sources[0]) == 1:
            sure.add(sources[0][0])
        if len(sources) != 1 or len(sources[0]) != 1:
            chosen.append(sources)
        for key in (*(source[0] for source in sources), *spellings):
            spelled.setdefault(key, sources)
    return frozenset(sure), tuple(chosen), spelled


_READS: dict[type, tuple[object, _KeyReads, _FieldReads, _Declared | None]] = {}
"""Per model class, with the validator they were read beside: the keys it reads, where each field is read, and
what a typed `__pydantic_extra__` declares its extra values as.

Worked out per level of every payload, it was most of the walk: a list of 1000 nested models asked for it 1000 times.
A field whose type cannot hold a model is left out: a 300 by 300 grid of floats cost 35 ms to walk and holds nothing.
A rebuild replaces the validator, and with it what the class reads, so an entry answers only for the validator it
was made with.  At most 256 classes are kept, so models made on the fly cannot grow it without bound."""


def _reads_of(model: Any) -> tuple[_KeyReads, _FieldReads, _Declared | None]:
    validator = getattr(model, "__pydantic_validator__", None)
    known = _READS.get(model)
    if known is None or known[0] is not validator:
        config = getattr(model, "model_config", {})
        nodes = _field_nodes(model)
        fields = tuple(
            (name, _field_sources(name, info, config), (getattr(info, "annotation", None), model, nodes.get(name)))
            for name, info in model.model_fields.items()
            # a schema of its own can validate a field as something its annotation does not name
            if _may_hold_model(getattr(info, "annotation", None)) or _keyed_under(nodes.get(name), model)
        )
        extras = _extra_values(model, nodes.get("__pydantic_extra__")) if config.get("extra") == "allow" else None
        keyed = _key_reads(
            (_field_sources(name, info, config), _spellings(name, info)) for name, info in model.model_fields.items()
        )
        known = (validator, keyed, fields, extras)
        if model in _READS or len(_READS) < 256:
            _READS[model] = known
    return known[1], known[2], known[3]


def _field_nodes(model: Any) -> dict[str, Any]:
    """The schema each field of *model* is validated by, as its core schema holds it, the one for its extra values
    under ``__pydantic_extra__`` and a root's under ``root``; empty where there is no such schema to read."""
    node: Any = getattr(model, "__pydantic_core_schema__", None)
    refs = _refs(model)
    while isinstance(node, dict):
        kind = node.get("type")
        if kind == "model-fields":
            nodes = {name: field.get("schema") for name, field in node.get("fields", {}).items()}
            # older pydantic names it `extra_validator`
            return {**nodes, "__pydantic_extra__": node.get("extras_schema", node.get("extra_validator"))}
        if kind == "model" and node.get("root_model"):
            return {"root": node.get("schema")}
        node = refs.get(node.get("schema_ref", "")) if kind == "definition-ref" else node.get("schema")
    return {}


def _extra_values(model: Any, node: object) -> _Declared | None:
    """The declaration a typed `__pydantic_extra__` gives the extra values of *model*, as written, beside the schema
    *node* pydantic built for them.

    The type is not read where it is text, which pydantic read in the namespace of the frame that defined the model,
    where a name can mean another type than in its module, and, from 3.14, where the annotations name what is defined
    only later, which reading them evaluates.  The schema declares alone then; ``None`` where there is neither.
    """
    unread = None if node is None else (None, model, node)
    try:
        for klass in getattr(model, "__mro__", ()):
            own = inspect.get_annotations(klass)
            if "__pydantic_extra__" in own:
                annotation = own["__pydantic_extra__"]
                if isinstance(annotation, str):
                    return unread
                values = _declared_mapping((annotation, model, None))[0]
                return values and (values[0], model, node)
    except NameError:
        return unread
    return None


_RecordReads = tuple[
    _KeyReads, frozenset[str], bool, tuple[tuple[str, tuple[tuple[object, ...], ...], _Declared | None], ...], _Declared
]
"""For a dataclass or a `TypedDict`: the payload keys it reads, the names of its fields, whether it keeps extras, the
fields worth walking with where each is read and what it declares, and the class as a declaration of its own."""

_RECORDS: dict[tuple[object, object], tuple[object, _RecordReads]] = {}
"""Per dataclass or `TypedDict`, by its schema or its class, and the class whose schema holds it, beside the schema or
the validator it was read with.  At most 256 entries (`_remember`)."""


def _record_reads(record: _Record, owner: object = None) -> _RecordReads:
    """How a dataclass or a `TypedDict` reads a payload: as `_reads_of` says of a model.

    The keys it takes and where each field is read come from the schema pydantic built, the one the walk came to it
    by, the record's own, or the one of the class that declared it (*owner*).  It holds what no annotation tells: an
    alias written as text, the one of several `Field`s that wins, a field ``init=False`` leaves out, and the config
    that says whether a name is read, which reaches a `TypedDict` from the model above.  Where no schema holds the
    record, the annotations are read as written (`_written_fields`), and a name counts as read after its aliases.

    What each field declares below it is the schema of that field, beside its annotation as pydantic resolved it or
    as written where that can be read.
    """
    node, kind = record
    if node is None:
        holder = kind if isinstance(getattr(kind, "__pydantic_core_schema__", None), dict) else owner
        key, read_with = (kind, holder), getattr(holder, "__pydantic_validator__", None)
    else:
        holder, key, read_with = owner, (id(node), owner), node
        kind = kind or node.get("cls")
    known = _RECORDS.get(key)
    if known is not None and known[0] is read_with:
        return known[1]
    # only later pydantic names the class in the schema of a `TypedDict`
    told = _written_fields(kind) if isinstance(kind, type) else ()
    written = {name: (sources, annotation, held) for name, sources, annotation, held in told}
    found = _record_node(_Record(node, kind), holder)
    said = found if isinstance(found, dict) else {}
    # an older pydantic says it in the config alone, and a `TypedDict` that declares its extras in the schema alone
    keeps = said.get("extra_behavior", (said.get("config") or {}).get("extra_fields_behavior")) == "allow"
    reads = _schema_fields(_Record(found, kind), holder)
    reads = reads or [(name, sources, held, None, ()) for name, (sources, _, held) in written.items()]
    keyed, fields = [], []
    for name, sources, held, schema, spellings in reads:
        keyed.append((sources, (name, *spellings)))
        annotation = written[name][1] if name in written else None
        if held and (annotation is None or _may_hold_model(annotation) or _keyed_under(schema, holder)):
            fields.append(
                (name, sources, None if annotation is None and schema is None else (annotation, holder, schema))
            )
    names = frozenset(name for name, *_ in reads)
    answer = (_key_reads(keyed), names, keeps, tuple(fields), (kind, None, None))
    _remember(_RECORDS, key, read_with, answer, 256)
    return answer


def _record_node(record: _Record, holder: object) -> Any:
    """The schema of a record: the one the walk came to it by, else the one the schema of *holder* has for its class,
    or ``None``.  A `TypedDict` is told by the id its ``ref`` ends in, since only later pydantic names its class
    there."""
    found, kind = record
    pending: list[Any] = [] if found is not None else [getattr(holder, "__pydantic_core_schema__", None)]
    while pending and found is None:
        node = pending.pop()
        if isinstance(node, dict):
            mine = node.get("cls") is kind or str(node.get("ref", "")).endswith(f":{id(kind)}")
            if node.get("type") in ("typed-dict", "dataclass") and mine:
                found = node
            pending.extend(value for key, value in node.items() if key not in ("serialization", "metadata", "default"))
        elif isinstance(node, (list, tuple)):
            pending.extend(node)
    return found


def _schema_fields(
    record: _Record, holder: object
) -> list[tuple[str, tuple[tuple[object, ...], ...], bool, Any, tuple[object, ...]]]:
    """Each key the schema says a record takes: its name, where it is read (its alias paths, then its name, each
    where the record's config reads by it), whether the record holds it, which an `InitVar` is not, the schema of its
    value, and the other keys that spell it.  Empty where no schema holds the record (`_record_node`).
    """
    found = _record_node(record, holder)
    config = (found.get("config") or {}) if isinstance(found, dict) else {}
    by_alias, by_name = config.get("validate_by_alias") is not False, config.get("validate_by_name")
    by_name = by_name if by_name is not None else config.get("populate_by_name")
    while isinstance(found, dict) and found.get("type") not in ("typed-dict", "dataclass-args"):
        found = found.get("schema")
    if not isinstance(found, dict):
        return []
    listed = found["fields"]
    named = listed.items() if isinstance(listed, dict) else [(field["name"], field) for field in listed]
    reads = []
    for name, field in named:
        if field.get("init") is not False:
            alias = field.get("validation_alias")
            paths = [alias] if isinstance(alias, str) or not alias or not isinstance(alias[0], list) else alias
            aliases = [(path,) if isinstance(path, str) else tuple(path) for path in paths if path]
            read_at = (*(aliases if by_alias else ()), *([(name,)] if by_name or not aliases else ()))
            shown = field.get("serialization_alias")
            spellings = (*(path[0] for path in aliases), *([shown] if isinstance(shown, str) else ()))
            reads.append((name, read_at, not field.get("init_only"), field.get("schema"), spellings))
    return reads


def _written_fields(kind: Any) -> collections.abc.Iterator[tuple[str, tuple[tuple[object, ...], ...], Any, bool]]:
    """Each key a dataclass or a `TypedDict` declares, as its own annotations tell it: its name, where it is read,
    its annotation where that is no text, and whether the record holds it.

    A dataclass takes a key for each field its `__init__` takes, an `InitVar` among them and one declared
    ``init=False`` not.  A `TypedDict` keeps an annotation written as text as a forward reference.
    """
    config = getattr(kind, "__pydantic_config__", None) or {}
    declared: list[tuple[str, Any, Any, bool]]
    if issubclass(kind, dict):
        hints: dict[str, Any] = {}
        try:
            for klass in reversed(kind.__mro__):
                hints.update(inspect.get_annotations(klass))
        except NameError:
            hints = {}
        keyed: Any = kind
        names = (*keyed.__required_keys__, *keyed.__optional_keys__)
        declared = [(name, hints.get(name), None, True) for name in names]
    else:
        infos = getattr(kind, "__pydantic_fields__", None) or {}
        # a plain dataclass may hold pydantic's `Field` as a default, which is where its alias then is
        declared = [
            (name, getattr(info, "annotation", None) or field.type, info, role == "_FIELD")
            for name, field in kind.__dataclass_fields__.items()
            for role in [getattr(getattr(field, "_field_type", None), "name", "_FIELD")]
            for info in [infos.get(name) or (field.default if hasattr(field.default, "validation_alias") else None)]
            if field.init and role != "_FIELD_CLASSVAR"
        ]
    for name, annotation, info, held in declared:
        while getattr(get_origin(annotation), "_name", None) in ("Required", "NotRequired", "ReadOnly"):
            annotation = get_args(annotation)[0]
        carried = get_args(annotation)[1:] if get_origin(annotation) is Annotated else ()
        # of several `Field`s pydantic keeps what the later ones set, so the alias is the last one given
        aliased = (
            extra
            for extra in reversed(carried)
            if getattr(extra, "validation_alias", None) or getattr(extra, "alias", None)
        )
        info = info or next(aliased, None)
        sources = ((name,),) if info is None else (*_field_sources(name, info, config), (name,))
        yield name, sources, None if isinstance(annotation, (str, ForwardRef)) else annotation, held


def _followed(payload: object, path: tuple[object, ...]) -> tuple[bool, object]:
    """What *path* reaches in *payload*, key by key and index by index, and whether it reached anything."""
    current: Any = payload
    for step in path:
        if isinstance(current, dict):
            if step not in current:
                return False, None
            current = current[step]
        elif not isinstance(current, str):
            # read as pydantic reads it, through whatever `__getitem__` the object has
            try:
                current = current[step]
            except (LookupError, TypeError):
                return False, None
        else:
            return False, None
    return True, current


def _raw_field(
    payload: collections.abc.Mapping, sources: tuple[tuple[object, ...], ...]
) -> tuple[tuple[object, ...] | None, object]:
    """The part of *payload* pydantic validated a field from, after the first of its sources that is there."""
    for source in sources:
        found, value = _followed(payload, source)
        if found:
            return source, value
    return None, None


def _unread(left: list[object], payload: collections.abc.Mapping, reads: _KeyReads) -> list[object]:
    """Those of the keys *left*, which no field is sure to read, that no field was read from in *payload*: the ones
    validation dropped, or kept as extras."""
    read = {source[0] for sources in reads[1] for source in [_raw_field(payload, sources)[0]] if source}
    return [key for key in left if key not in read]


def _undeclared(payload: collections.abc.Mapping, key: object, path: _Hop, reads: _KeyReads) -> _Found:
    """The find for a *key* of *payload* validation dropped, with the reason where the key spells a field: the
    source its field was read from in its place, or the ones validation reads it from where the payload sent none."""
    sources = reads[2].get(key)
    if not sources:
        return (path, key, (key,)), payload[key]
    read, _ = _raw_field(payload, sources)
    reason = (
        f"its field was read from <{_spelt(read)}>"
        if read is not None
        else f"validation reads its field from {' or '.join(f'<{_spelt(source)}>' for source in sources)}"
    )
    return (path, key, (key,)), payload[key], reason


def _spelt(source: tuple[object, ...]) -> str:
    """A source as a failure names it: a key, and the keys and positions a path goes on by."""
    return "".join(f"[{step}]" if isinstance(step, int) else f".{step}" for step in source).removeprefix(".")


def _placed(hop: _Hop) -> tuple[str, tuple[Step, ...]]:
    """Where *hop* stands, as the text a failure names it by and as the steps that reach it in the payload."""
    hops = []
    while hop is not None:
        hops.append(hop)
        hop = hop[0]
    # joined once: adding each piece to the text so far copied it again at every hop
    pieces, steps, written = [], [], False
    for _, piece, taken in reversed(hops):
        if type(taken) is tuple:
            named = f"{piece}"
            pieces.append(f".{named}" if written else named)
            written = written or bool(named)
            steps += [Step("index" if type(key) is int else "key", key) for key in taken]
        elif piece is None:
            steps.append(taken)
        else:
            pieces.append(f"[{piece}]")
            written = True
            steps.append(Step("index", piece) if taken is None else taken)
    return "".join(pieces), tuple(steps)


def _is_model(value: object) -> bool:
    return not isinstance(value, type) and hasattr(type(value), "model_fields")


def _is_record(value: object) -> bool:
    """A model or a dataclass instance: what validation builds from a mapping and holds field by field."""
    return _is_model(value) or (not isinstance(value, type) and hasattr(type(value), "__dataclass_fields__"))


_CONTAINERS = (dict, list, tuple, set, frozenset)

_REPLAYED = (0, -1)
"""In the pairs a walk has seen, where no pair of ids can be: the walk is under a replay (`_replayed`), where a field
whose type offers a choice cannot be read (`_steered`)."""


class UncheckableDriftError(Exception):
    """A part of the payload no reading pairs with the model it became, so whether it drifted cannot be told."""

    def __init__(self, path: _Hop, reason: str, part: object) -> None:
        self.path, self.steps = _placed(path)
        super().__init__(f"{self.path or 'the payload'}: {reason}")
        self.reason = reason
        self.part = part


def contract_drift(
    payload: object, instance: Any, path: _Hop = None, _seen: frozenset[tuple[int, int]] = frozenset()
) -> list[_Found]:
    """The fields ``payload`` carries that the model ``instance`` was validated into does not declare.

    Walked beside the instance rather than read off the annotations: which member of a union, which element type
    of a tuple and which dict value a part of the payload became is what pydantic decided, and the instance holds
    the answer.  A model whose config opts into extras (``extra="allow"``) keeps them intentionally, so its own
    level is skipped.

    Raises:
        UncheckableDriftError: where a part of the payload that could hide an undeclared key (a dict inside it, or
            inside the JSON text it is) cannot be paired with a model built from it: a set, a resized list or an
            object wrapped into either whose built items are not all one model class, or whose raw item that class
            refuses on its own, dict keys coercion merged, a part of another shape than what was built, an iterable
            validation read up or left lazy, raw items no built item is left for that their declared type does not
            build again or that it declares through a choice.  The payload is read as it is handed over, which
            `assert_conforms` does after putting back what validation changed in place: a validator renaming keys,
            or reordering or rewriting a container's items without changing its size, is not seen, and the walk
            reads those items by position.
    """
    model = type(instance)
    reads, fields, extras = _reads_of(model)
    replayed = _REPLAYED in _seen
    if getattr(model, "__pydantic_root_model__", False):
        return _declared_drift(payload, instance.root, path, _seen, fields[0][2], replayed) if fields else []
    if not isinstance(payload, (dict, collections.abc.Mapping)):
        _refuse_if_key_hides(
            payload, instance, path, f"the payload holds a {type(payload).__name__} where a model was built"
        )
        return []
    seen = _seen | {(id(payload), id(instance))}
    drift: list[_Found] = []
    sure = reads[0]
    left = [key for key in payload if key not in sure]
    if left:
        left = _unread(left, payload, reads)
    if getattr(model, "model_config", {}).get("extra") == "allow":
        drift += _extras_drift(payload, instance, path, seen, extras, replayed, left)
    elif left:
        drift += [_undeclared(payload, key, path, reads) for key in left]
    for name, sources, annotated in fields:
        source, raw = _raw_field(payload, sources)
        if source is None:
            continue
        if replayed and _chooses(annotated[0]):
            drift += _steered(raw, (path, name, source))
            continue
        value = getattr(instance, name, None)
        # a scalar built from a scalar holds nothing to pair
        if (value is None or isinstance(value, (str, int, float, bytes))) and not isinstance(raw, _CONTAINERS):
            continue
        drift += _value_drift(raw, value, (path, name, source), seen, annotated)
    return drift


def _extras_drift(
    payload: collections.abc.Mapping,
    instance: Any,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    declared: _Declared | None,
    replayed: bool,
    left: list[object],
) -> list[_Found]:
    """Drift under the extras of a model that allows them: built through a typed `__pydantic_extra__` and walked as it
    *declared* them; untyped ones are the payload's own objects.

    An extra the payload sent that the model no longer holds was built as that type and removed afterwards, by a
    validator.  What it was built into is gone, so it is validated again as the declared type and walked beside what
    that builds, or refused where that cannot tell (`_replayed`).  *left* are the keys no field was read from, which
    are the extras the model was sent.
    """
    held = getattr(instance, "__pydantic_extra__", None)
    # a validator can leave anything there: what is no dict holds no extra
    built = held if isinstance(held, dict) else {}
    drift = [
        entry
        for key, value in built.items()
        if key in payload
        for entry in _declared_drift(payload[key], value, (path, key, (key,)), seen, declared, replayed)
    ]
    if declared is not None:
        gone: list[tuple[_Hop, object]] = [((path, key, (key,)), payload[key]) for key in left if key not in built]
        if any(_holds(part, _is_mapping, read_text=True) for _, part in gone):
            reason = f"the model no longer holds {len(gone)} of the extras it was sent"
            drift += _replayed(payload, gone, path, seen, reason, _listed(declared))
    return drift


def _listed(declared: _Declared) -> _Declared:
    """A list of what *declared* declares: the type several values declared so are validated again as."""
    key = (id(declared), "listed")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner, node = declared
    listed = (
        None if annotation is None else types.GenericAlias(list, (annotation,)),
        owner,
        {"type": "list", "items_schema": node},
    )
    _remember(_DECLARED, key, declared, listed, 1024)
    return listed


def _declared_drift(
    raw: object,
    value: object,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    declared: _Declared | None,
    replayed: bool,
) -> list[_Found]:
    """Drift under a value its model declared, a root's or an extra's; `_steered` under a replay where validation built
    it through a declared type that offers a choice, or one that cannot be read."""
    if replayed and value is not raw and (declared is None or _chooses(declared[0])):
        return _steered(raw, path)
    return _value_drift(raw, value, path, seen, declared)


def _steered(raw: object, path: _Hop) -> list[_Found]:
    """Nothing to read under a part a replay built where its type offered a choice, which the validators the replay
    skipped could have steered; a refusal where a key could hide in it."""
    if _holds(raw, _is_mapping, read_text=True):
        reason = "which of its declared types it became depends on validators not run again"
        raise UncheckableDriftError(path, reason, raw)
    return []


def exactness_failure(pairs: Any, *, carrier: str) -> tuple[str, list[DiffEntry]] | None:
    """What an exact check of ``(payload, instance, index)`` pairs found: the words a failure continues with, and the
    same as diff entries.  ``None`` when it found nothing.

    The undeclared fields, after *carrier*, each an entry holding the value sent there with nothing expected of it;
    or the first part that cannot be checked, an entry holding that part against the reason.  The steps of an entry
    lead into the payload, by the key the field was read from where its text names the field; where they enter JSON
    text, a ``json`` step holds what it decodes to.
    """
    drift: list[_Found] = []
    payload, start = None, None
    try:
        for payload, instance, index in pairs:
            start = None if index is None else (None, index, None)
            drift += contract_drift(payload, instance, start)
    except UncheckableDriftError as refusal:
        reason = f"cannot be checked: {refusal.reason}"
        entry = DiffEntry(path=refusal.path or ".", steps=refusal.steps, actual=refusal.part, expected=reason)
        return f"<{refusal.path or 'the payload'}> {reason}", [entry]
    except RecursionError:
        reason = "cannot be checked: it nests deeper than the walk can follow"
        where, steps = _placed(start)
        return f"<the payload> {reason}", [DiffEntry(path=where or ".", steps=steps, actual=payload, expected=reason)]
    if not drift:
        return None
    placed = sorted(((*_placed(hop), sent, why) for hop, sent, *why in drift), key=operator.itemgetter(0))
    entries = [DiffEntry(path=where, steps=steps, actual=sent, absent="expected") for where, steps, sent, _ in placed]
    paths = [entry.path for entry in entries]
    told = "".join(f"\n<{where}> is not read: {why[0]}" for where, _, _, why in placed if why)
    return f"{carrier}{len(entries)} undeclared field(s) the model does not declare: {paths}{told}", entries


def _value_drift(
    raw: object, value: object, path: _Hop, seen: frozenset[tuple[int, int]], declared: _Declared | None = None
) -> list[_Found]:
    """Drift under one validated value: a model's own keys, and every element or dict value that became a model.

    *declared* is the type the value was declared as and the model that declared it, where the walk knows them: what
    a model field or a root declares, and from it the item type of each container below.
    """
    # the payload's own object kept as it was, or a scalar: nothing was built from it
    if raw is value or value is None or isinstance(value, (str, int, float, bytes)):
        return []
    if isinstance(raw, (str, bytes, bytearray)):
        raw, path = _decoded_at(raw, path)
    # a pair already on the path is a cycle, the payload's own or one a validator built by assigning a model to itself
    pair = (id(raw), id(value))
    if pair in seen:
        return []
    seen = seen | {pair}
    if _is_model(value):
        return contract_drift(raw, value, path, seen)
    return _container_drift(raw, value, path, seen, declared)


def _container_drift(
    raw: object, value: object, path: _Hop, seen: frozenset[tuple[int, int]], declared: _Declared | None
) -> list[_Found]:
    """Drift under a built container, paired with the raw part it came from as its kind allows."""
    if isinstance(value, (list, tuple)):
        return _sequence_drift(raw, value, path, seen, declared)
    if isinstance(value, dict):
        return _mapping_drift(raw, value, path, seen, declared)
    if isinstance(value, (set, frozenset)):
        return _set_drift(raw, value, path, seen, declared)
    if isinstance(value, collections.abc.Mapping):
        return _mapping_drift(raw, dict(value), path, seen, declared)
    if isinstance(value, collections.abc.Iterator):
        if _holds(raw, _is_mapping, read_text=True):
            reason = "validation is lazy here and builds the models only as the value is read"
            raise UncheckableDriftError(path, reason, raw)
        return []
    if hasattr(type(value), "__dataclass_fields__"):
        if not isinstance(raw, (dict, collections.abc.Mapping)):
            reason = f"the payload holds a {type(raw).__name__} where a dataclass was built"
            _refuse_if_key_hides(raw, value, path, reason)
            return []
        kind: Any = type(value)
        owner = None if declared is None else declared[1]
        stored = {field.name for field in dataclasses.fields(kind)}
        built = {name: getattr(value, name) for name in stored if hasattr(value, name)}
        # a dataclass that allows extras keeps them beside its fields
        extras = [name for name in getattr(value, "__dict__", ()) if name not in stored]
        return _record_drift(raw, built, extras, path, seen, _Record(None, kind), owner)
    # a sequence validation kept as the payload's own kind, a deque under `Sequence[A]`
    items = _items_of(value)
    return [] if items is None else _sequence_drift(raw, items, path, seen, declared)


def _record_drift(
    raw: collections.abc.Mapping,
    built: collections.abc.Mapping,
    extras: collections.abc.Collection,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    record: _Record,
    owner: object,
) -> list[_Found]:
    """Drift under a dataclass or a `TypedDict`, which drop an undeclared key as a model does: the keys *raw* holds
    that the record neither read a field from nor keeps among its *extras*, where it allows them, and what lies under
    the fields it *built*.

    A key that is the name of a field is no extra by being in what was built, where every field is: it is kept only
    by a record that keeps extras, which puts what it was sent there over the field.
    """
    reads, names, keeps, fields, _ = _record_reads(record, owner)
    replayed = _REPLAYED in seen
    sure = reads[0]
    left = [key for key in raw if key not in sure]
    drift: list[_Found] = []
    if left:
        drift = [
            _undeclared(raw, key, path, reads)
            for key in _unread(left, raw, reads)
            if (not keeps if key in names else key not in extras)
        ]
    for name, sources, declared in fields:
        source, part = _raw_field(raw, sources)
        if source is not None and name in built:
            drift += _declared_drift(part, built[name], (path, name, source), seen, declared, replayed)
    return drift


def _unsure_drift(
    raw: collections.abc.Mapping,
    built: dict,
    unsure: _Unsure,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    owner: object,
) -> list[_Found]:
    """Drift under a dict one of several declared `TypedDict`s may have built.

    One whose `Literal` fields do not hold what the dict holds did not build it, where no code of the owner's could
    have rewritten them since and no extra was put over them (`_put_over`).  Where that leaves one, and nothing
    declared beside them may build a dict, the dict is
    read as that record.  Else nothing tells the rest apart, and the walk does not choose as validation did.  A key the
    payload sent that the dict holds neither under its name nor as the field one of them reads from it could have been
    dropped by any, so it refuses; so does a field two of them read from different parts of the payload.  What the
    dict does hold is followed as a choice between whatever each of them, and each schema beside them, declares it as.
    """
    records = unsure.records
    if not runs_own_code(owner):
        records = tuple(record for record in records if _may_have_built(raw, built, record, owner))
        if len(records) == 1 and not unsure.beside:
            return _record_drift(raw, built, built, path, seen, _Record(records[0], None), owner)
    read_as, fields, other = _shared_reads(records, unsure.beside, owner)
    reason = "it holds a key the dict built from it does not, and its declared types do not say which built it"
    for key in raw:
        if key not in built and not any(name in built for name in read_as.get(key, ())):
            raise UncheckableDriftError(path, reason, raw)
    replayed = _REPLAYED in seen
    drift: list[_Found] = []
    for name, readings, declared in fields:
        read = {
            id(part): (source, part) for sources in readings for source, part in [_raw_field(raw, sources)] if source
        }
        if name in built and len(read) > 1:
            raise UncheckableDriftError(path, reason, raw)
        for source, part in read.values() if name in built else ():
            drift += _declared_drift(part, built[name], (path, name, source), seen, declared, replayed)
    declared_fields = {name for name, _, _ in fields}
    for key in built if other is not None else ():
        if key not in declared_fields and key in raw:
            drift += _declared_drift(raw[key], built[key], (path, key, (key,)), seen, other, replayed)
    return drift


def _may_have_built(raw: collections.abc.Mapping, built: dict, record: Any, owner: object) -> bool:
    """Whether the `TypedDict` schema *record* may have built the dict *built* from *raw*: each of its `Literal` fields
    holds a value it takes, or one a key of the payload was put over."""
    over = _put_over(raw, record, owner)
    return all(
        name not in built or name in over or built[name] in allowed for name, allowed in _literals(record, owner)
    )


def _put_over(raw: collections.abc.Mapping, record: Any, owner: object) -> collections.abc.Collection[object]:
    """The fields of the `TypedDict` schema *record* that a key of *raw* was put over, if it built the dict.

    One that keeps extras keeps a key it read no field from, and where that key is the name of a field, as beside the
    alias the field was read from, it lands on what validation built there.  What the dict holds under that name is
    then what was sent, and does not say that this one did not build it.  One that drops extras had nothing put over
    its fields, so what another would have kept is nothing to it.
    """
    reads, names, keeps, _, _ = _record_reads(_Record(record, None), owner)
    if not keeps:
        return ()
    sure = reads[0]
    left = [key for key in raw if key in names and key not in sure]
    return _unread(left, raw, reads) if left else left


def _literals(record: Any, owner: object) -> list[tuple[str, list[object]]]:
    """The fields of the `TypedDict` schema *record* that take nothing but the values a `Literal` lists, with those
    values, ``None`` among them where the field takes it too."""
    key = (id(record), "literals")
    known = _DECLARED.get(key)
    if known is not None and known[0] is record:
        return known[1]
    found = []
    for name, _, _, schema, _ in _schema_fields(_Record(record, None), owner):
        allowed: list[object] = []
        while _schema_kind(schema) == "nullable":
            allowed.append(None)
            schema = schema.get("schema")
        if _schema_kind(schema) == "literal":
            found.append((name, [*allowed, *schema.get("expected", ())]))
    _remember(_DECLARED, key, record, found, 1024)
    return found


_SharedReads = tuple[
    dict[object, list[str]],
    tuple[tuple[str, tuple[tuple[tuple[object, ...], ...], ...], _Declared], ...],
    _Declared | None,
]


def _shared_reads(records: tuple[Any, ...], beside: tuple[Any, ...], owner: object) -> _SharedReads:
    """What the `TypedDict` schemas *records* read between them: the fields each payload key is read into by one of
    them; each field with where each of them reads it, apart, and a choice between what they and the schemas *beside*
    them declare it as; and what those schemas declare a key that is no field of the records as."""
    key = (tuple(map(id, (*records, *beside))), "shared")
    known = _DECLARED.get(key)
    if known is not None and all(map(operator.is_, known[0], (*records, *beside))):
        return known[1]
    read_as: dict[object, list[str]] = {}
    read_at: dict[str, list[tuple[tuple[object, ...], ...]]] = {}
    schemas: dict[str, list[Any]] = {}
    for record in records:
        for name, sources, _, schema, _ in _schema_fields(_Record(record, None), owner):
            for source in sources:
                read_as.setdefault(source[0], []).append(name)
            read_at.setdefault(name, []).append(sources)
            schemas.setdefault(name, []).append(schema)
    values = _values_beside(beside)
    # what is declared beside them builds a key's value from that key alone, which is one more place to read it
    fields = tuple(
        (name, (*read_at[name], *([((name,),)] if values else [])), (None, owner, _either([*schemas[name], *values])))
        for name in read_at
    )
    answer = (read_as, fields, (None, owner, _either(values)) if values else None)
    _remember(_DECLARED, key, (*records, *beside), answer, 1024)
    return answer


def _sequence_drift(
    raw: object,
    value: list | tuple,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    declared: _Declared | None = None,
) -> list[_Found]:
    """Paired by index, a collection pydantic also takes for a sequence (a deque, a set, a dict's values) in the
    order it iterates, which is the order validation read it in."""
    sent = raw
    if not isinstance(raw, (list, tuple)):
        items = _items_of(raw)
        if items is None:
            reason = f"the payload holds a {type(raw).__name__} where a sequence was built"
            return _wrapped(raw, value, path, seen, reason, declared)
        raw = items
    if len(raw) != len(value) or not isinstance(sent, collections.abc.Sequence):
        parts = _numbered(sent, raw, path)
        if len(raw) != len(value):
            reason = f"validation changed its length, {len(raw)} items became {len(value)}"
            return _unpaired(sent, parts, value, path, seen, reason, declared=declared)
        declarations = _item_declarations(declared, len(value))
        return [
            entry
            for (place, part), element, item in zip(parts, value, declarations, strict=True)
            for entry in _value_drift(part, element, place, seen, item)
        ]
    items = _declared_container(declared)
    if items is None or items[0] is None:
        common = None if items is None else items[1]
        return [
            entry
            for index, (part, element) in enumerate(zip(raw, value, strict=True))
            for entry in _value_drift(part, element, (path, index, None), seen, common)
        ]
    declarations = _item_declarations(declared, len(value))
    return [
        entry
        for index, (part, element, item) in enumerate(zip(raw, value, declarations, strict=True))
        for entry in _value_drift(part, element, (path, index, None), seen, item)
    ]


def _numbered(sent: object, items: collections.abc.Iterable, path: _Hop) -> list[tuple[_Hop, object]]:
    """Each of the *items* a collection was *sent* holding, at the place a failure names it by: its number in the
    order it was read, which leads to it by position in a sequence and by the item itself in anything else."""
    if isinstance(sent, collections.abc.Sequence):
        return [((path, index, None), part) for index, part in enumerate(items)]
    return [((path, index, Step("item", part)), part) for index, part in enumerate(items)]


def _mapping_drift(
    raw: object, value: dict, path: _Hop, seen: frozenset[tuple[int, int]], declared: _Declared | None = None
) -> list[_Found]:
    """Paired by key where validation kept the keys (a `TypedDict` reorders them), else by order, which dict validation
    keeps while it coerces them; a key built into something other than text or a number is walked beside its raw key."""
    if not isinstance(raw, (dict, collections.abc.Mapping)):
        reason = f"the payload holds a {type(raw).__name__} where a mapping was built"
        _refuse_if_key_hides(raw, value, path, reason, declared)
        return []
    item, record = (None, None) if declared is None else _declared_mapping(declared)
    owner = None if declared is None else declared[1]
    if isinstance(record, _Unsure):
        return _unsure_drift(raw, value, record, path, seen, owner)
    if record is not None:
        return _record_drift(raw, value, value, path, seen, record, owner)
    if len(raw) != len(value):
        # an overwritten value may have become another member of a union than the one that survived
        reason = f"validation changed its size, {len(raw)} keys became {len(value)}"
        _refuse_if_key_hides(raw, value, path, reason, declared)
        return []
    if raw.keys() == value.keys():
        return [
            entry
            for key, part in raw.items()
            for entry in _value_drift(part, value[key], (path, key, (key,)), seen, item)
        ]
    drift: list[_Found] = []
    for (key, part), (built, element) in zip(raw.items(), value.items(), strict=True):
        if not isinstance(built, (str, int)):
            drift += _value_drift(key, built, (path, None, Step("item", key)), seen)
        drift += _value_drift(part, element, (path, key, (key,)), seen, item)
    return drift


def _set_drift(
    raw: object, value: set | frozenset, path: _Hop, seen: frozenset[tuple[int, int]], declared: _Declared | None
) -> list[_Found]:
    items = raw if isinstance(raw, (list, tuple)) else _items_of(raw)
    if items is None:
        reason = f"the payload holds a {type(raw).__name__} where a set was built"
        return _wrapped(raw, value, path, seen, reason, declared)
    reason = "a set keeps no order to pair its items with the models they became"
    return _unpaired(raw, _numbered(raw, items, path), value, path, seen, reason, merged=True, declared=declared)


def _wrapped(
    raw: object,
    value: object,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    reason: str,
    declared: _Declared | None,
) -> list[_Found]:
    """Drift under a mapping a validator turned into a sequence or a set, a single object sent where many may be.

    Only a mapping that became one item, or none, is that item; one that became several was expanded in a way no
    reading pairs.
    """
    if isinstance(raw, (dict, collections.abc.Mapping)) and len(_items_of(value) or ()) <= 1:
        return _unpaired(raw, [(path, raw)], value, path, seen, reason, declared=declared)
    _refuse_if_key_hides(raw, value, path, reason, declared)
    return []


def _unpaired(
    raw: object,
    parts: list[tuple[_Hop, object]],
    value: object,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    reason: str,
    *,
    merged: bool = False,
    declared: _Declared | None = None,
) -> list[_Found]:
    """Drift under a container whose raw items no reading pairs one by one with the items validation built.

    Where every built item is an instance of one model class, each raw item became one too, so each raw item that
    could hide a key is validated again on its own by that class and walked beside what it becomes.  Where validation
    kept no model at all, the raw items are validated again whole by the type the field *declared*, in its model's
    config, and what that builds is walked (`_replayed`).  Anything else refuses with *reason*: items of mixed classes,
    an item that does not validate on its own, which needed its parent, where equal items *merged*, a class whose own
    `__eq__` could have merged an item of another class into it, and raw items no replay can tell the type of.
    """
    if not _holds(raw, _is_mapping, read_text=True):
        return []
    if _holds(value, _builds_model):
        model = _sole_model_class(value)
        if model is None or (merged and not _equal_only_within_its_class(model)):
            raise UncheckableDriftError(path, reason, raw)
        return _revalidated(raw, parts, model, path, seen, reason)
    return _replayed(raw, parts, path, seen, reason, declared)


def _replayed(
    raw: object,
    parts: list[tuple[_Hop, object]],
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    reason: str,
    declared: _Declared | None,
) -> list[_Found]:
    """Drift under raw items validation left without a model: validated again whole as the *declared* type, in Python
    mode as validation read them (`_replay_target`).  All of them are replayed first, so a fixed tuple's positions
    see what validation saw; where pydantic refuses that, only the items that could hide a key.  What that builds is
    paired item by item; a set it builds tells the one class they became.

    The replay skips the validators of the field itself, so whatever they did to the payload is missing from it, and
    it refuses with *reason* wherever that leaves the type of the items open: a declaration that offers a choice
    (`_chooses`) or none at all, items pydantic builds nothing from, or no sequence of as many.
    """
    if declared is None or _chooses(declared[0]):
        raise UncheckableDriftError(path, reason, raw)
    replayed = _replay_target(declared)
    adapter = _adapter(replayed)
    if adapter is None:
        raise UncheckableDriftError(path, reason, raw)
    origin = get_origin(replayed[0])
    kind = origin if origin in (tuple, collections.deque) else list
    own = runs_own_code(replayed[1])
    rebuilt = _replay(adapter, parts, kind, own)
    if rebuilt is None:
        parts = [(label, part) for label, part in parts if _holds(part, _is_mapping, read_text=True)]
        rebuilt = _replay(adapter, parts, kind, own)
    seen = seen | {_REPLAYED}
    if isinstance(rebuilt, collections.abc.Set):
        return _unpaired(raw, parts, rebuilt, path, seen, reason, merged=True)
    elements = _items_of(rebuilt)
    if elements is None or len(elements) != len(parts):
        raise UncheckableDriftError(path, reason, raw)
    declarations = _item_declarations(replayed, len(elements))
    return [
        entry
        for (label, part), element, item in zip(parts, elements, declarations, strict=True)
        for entry in _value_drift(part, element, label, seen, item)
    ]


def _replay(
    adapter: Any, parts: list[tuple[_Hop, object]], kind: Callable[[list[object]], object], own: bool
) -> object:
    """What *adapter* builds from the raw items of *parts*, handed over as the *kind* of container a strict config
    takes for its type (`_validated_again`), or ``None`` where pydantic refuses them."""
    try:
        items = [part for _, part in parts]
        return _validated_again(adapter.validate_python, kind(items), items if own else ())
    # a validation error, or a schema pydantic builds only on first use and then refuses
    except (ValueError, TypeError, RuntimeError, NameError):
        return None


def _replay_target(declared: _Declared) -> _Declared:
    """The type raw items are validated again as: the one member of the *declared* type without the `Annotated`
    validators of the container itself, which are what emptied it, and a set as a list of its items, so no model is
    hashed and each item keeps its place."""
    key = (id(declared), "replay")
    known = _DECLARED.get(key)
    if known is not None and known[0] is declared:
        return known[1]
    annotation, owner, node = declared
    member = _sole_member(annotation) or annotation
    if member in (set, frozenset) or get_origin(member) in (
        set,
        frozenset,
        collections.abc.Set,
        collections.abc.MutableSet,
    ):
        member = types.GenericAlias(list, get_args(member) or (Any,))
    target = (member, owner, node)
    _remember(_DECLARED, key, declared, target, 1024)
    return target


def _revalidated(
    raw: object,
    parts: list[tuple[_Hop, object]],
    model: type,
    path: _Hop,
    seen: frozenset[tuple[int, int]],
    reason: str,
) -> list[_Found]:
    """Drift under each raw item that could hide a key, validated again on its own by *model*, JSON text in JSON mode
    as `Json[...]` read it.  A dataclass is validated through an adapter of its own."""
    validate = getattr(model, "model_validate", None)
    validate_json = getattr(model, "model_validate_json", None)
    if validate is None and hasattr(model, "__dataclass_fields__"):
        adapter = _adapter(_record_reads(_Record(None, model))[4])
        validate, validate_json = getattr(adapter, "validate_python", None), getattr(adapter, "validate_json", None)
    if validate is None or validate_json is None:
        raise UncheckableDriftError(path, reason, raw)
    drift: list[_Found] = []
    own = runs_own_code(model)
    for label, item in parts:
        part, place = _decoded_at(item, label) if isinstance(item, (str, bytes, bytearray)) else (item, label)
        held = (part,) if own else ()
        if _holds(part, _is_mapping, read_text=True):
            try:
                built = _validated_again(validate, part, held) if part is item else validate_json(item)
            except ValueError:
                raise UncheckableDriftError(path, reason, raw) from None
            drift += _value_drift(part, built, place, seen)
    return drift


def _equal_only_within_its_class(model: type | None) -> bool:
    """Whether equal instances of *model* share its class: its `__eq__` is pydantic's own, or the one `dataclasses`
    writes, both of which compare classes.

    A parametrized generic model does not: pydantic compares its origin, which every specialization shares.
    """
    if (getattr(model, "__pydantic_generic_metadata__", None) or {}).get("origin") is not None:
        return False
    owner = next((klass for klass in getattr(model, "__mro__", ()) if "__eq__" in vars(klass)), object)
    # the method `dataclasses` writes is compiled from text, so it names no file
    written = getattr(getattr(vars(owner)["__eq__"], "__code__", None), "co_filename", None) == "<string>"
    return owner.__module__.startswith("pydantic.") or (written and hasattr(owner, "__dataclass_fields__"))


def _sole_model_class(value: object) -> type | None:
    """The one model or dataclass class every item of a built container is an instance of, or ``None``."""
    items = _items_of(value) or []
    kinds = {type(item) for item in items}
    return kinds.pop() if len(kinds) == 1 and _is_record(items[0]) else None


def _decoded_at(text: str | bytes | bytearray, path: _Hop) -> tuple[object, _Hop]:
    """What JSON *text* decodes to (`_decoded_container`) and the place inside it, one hop past *path* that holds
    that very object; the text and *path* themselves where it is no JSON to enter."""
    decoded = _decoded_container(text)
    return (text, path) if decoded is text else (decoded, (path, None, Step("json", decoded)))


def _decoded_container(text: str | bytes | bytearray) -> object:
    """What JSON *text* decodes to, decoded again while that is text, when it ends in a mapping or a list; else *text*.

    A model read from JSON text (`Json[...]`) is walked beside what the text holds.  Text that is not JSON, or nests
    deeper than the decoder goes, is left as it is.
    """
    try:
        current = json.loads(text)
        while isinstance(current, str):
            current = json.loads(current)
    except (ValueError, RecursionError):
        return text
    return current if isinstance(current, (dict, list)) else text


def _refuse_if_key_hides(
    raw: object, value: object, path: _Hop, reason: str, declared: _Declared | None = None
) -> None:
    """Refuse a part no reading pairs with what it became, when a model was built there, or a dict a `TypedDict`
    *declared* for it builds, and a key could hide in it.

    A number, a model given as is, an object read by attributes and text that is not JSON hold no key to drift.
    """
    keyed = _holds(value, _builds_model) or (declared is not None and _records_under(declared[2], declared[1]))
    if keyed and _holds(raw, _is_mapping, read_text=True):
        raise UncheckableDriftError(path, reason, raw)


def _holds(value: object, found: Callable[[object], bool], *, read_text: bool = False) -> bool:
    """Whether *value*, or anything inside its containers (a dict's keys too), is *found*.

    With *read_text*, text counts as the JSON it decodes to, decoded again while that is text, and two things count
    as found, since what they hold cannot be told: text nesting deeper than the decoder goes, and an iterable that is
    no collection, which validation may have read up or may answer differently when read again.  Every part stays
    referenced until the search ends, so the id of one already seen is never taken by a part decoded later.
    """
    pending, visited = [value], {id(value): value}
    while pending:
        current = pending.pop()
        if read_text and isinstance(current, (str, bytes, bytearray)):
            try:
                pending.append(json.loads(current))
            except ValueError:
                pass
            except RecursionError:
                return True
            continue
        elif read_text and _read_once(current):
            return True
        if found(current):
            return True
        for part in _parts(current):
            if id(part) not in visited:
                visited[id(part)] = part
                pending.append(part)
    return False


def _is_mapping(value: object) -> bool:
    return isinstance(value, (dict, collections.abc.Mapping))


def _builds_model(value: object) -> bool:
    """A model or a dataclass, or an iterator validation left lazy, which builds its models only as it is read."""
    return _is_record(value) or isinstance(value, collections.abc.Iterator)


def _read_once(value: object) -> bool:
    """An iterable that is no collection and no model given as is: what it held cannot be read again."""
    return (
        isinstance(value, collections.abc.Iterable)
        and not isinstance(value, collections.abc.Collection)
        and not _is_model(value)
    )


def _items_of(value: object) -> list[Any] | None:
    """The items of a container read again as often as asked, not text and not a mapping; ``None`` for the rest."""
    if isinstance(value, collections.abc.Collection) and not isinstance(
        value, (str, bytes, bytearray, collections.abc.Mapping)
    ):
        return list(value)
    return None


def _parts(value: object) -> Any:
    """What a container holds, a mapping's keys too, or nothing for anything else."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return value
    if isinstance(value, (dict, collections.abc.Mapping)):
        return [*value, *value.values()]
    return _items_of(value) or ()


def shape(value: object, _seen: frozenset[int] = frozenset()) -> object:
    """The structural shape of a value: paths and type *categories*, never values.

    Numbers collapse to one category (so ``5`` and ``5.0`` do not read as drift) and ``None`` becomes
    ``"null"`` (a nullable wildcard).  A list becomes a single merged element shape.  This is what a
    contract snapshot stores, so later runs pass when values change but fail on structural drift.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (dict, list, tuple)):
        if id(value) in _seen:
            # a self-referential graph would otherwise recurse until the interpreter gives up
            return "<circular ref>"
        nested = _seen | {id(value)}
        if isinstance(value, dict):
            return {key: shape(item, nested) for key, item in value.items()}
        element_shapes = [shape(item, nested) for item in value]
        return [reduce(_merge, element_shapes)] if element_shapes else []
    return type(value).__name__


def _merge(left: Any, right: Any) -> Any:
    """Merge two element shapes into one representative shape (``null`` yields to a concrete type)."""
    if left == right:
        return left
    if left == "null":
        return right
    if right == "null":
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        return {key: _merge(left.get(key, "null"), right.get(key, "null")) for key in set(left) | set(right)}
    if isinstance(left, list) and isinstance(right, list):
        if not left:
            return right
        if not right:
            return left
        return [_merge(left[0], right[0])]
    return "mixed"


def _shape_name(part: object) -> str:
    if isinstance(part, str):
        return part
    return "object" if isinstance(part, dict) else "list"


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def shape_diff(old: Any, new: Any, path: str = "") -> list[tuple[str, str, str]]:
    """Structural drift between two shapes: ``(kind, path, detail)`` for added / removed / retyped leaves.

    A ``null`` on either side is a nullable wildcard and never counts as drift.
    """
    if old == new or old == "null" or new == "null":
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        drift: list[tuple[str, str, str]] = [("added", _join(path, key), "") for key in new if key not in old]
        for key in old:
            child = _join(path, key)
            if key not in new:
                drift.append(("removed", child, ""))
            else:
                drift += shape_diff(old[key], new[key], child)
        return drift
    if isinstance(old, list) and isinstance(new, list):
        if not old or not new:
            return []
        return shape_diff(old[0], new[0], f"{path}[*]")
    return [("retyped", path, f"{_shape_name(old)} -> {_shape_name(new)}")]
