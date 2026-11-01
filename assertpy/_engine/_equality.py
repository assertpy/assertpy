"""The equality decision itself, with nothing around it.

Equality was already computed in one place structurally: `_sub_diff_entries` walks both sides and the
compare config travels with it.  What was not in one place was the *entry* to that walk.  The recursive
mapping comparison, the ignore/include filtering and the dict-shape test lived on `HelpersMixin`, which
made them reachable from a builder and from nowhere else.  A matcher therefore could not offer
`tolerance`, `ignore`, `include`, `comparators` or `ignore_null` at all: `match.equal_to(x, tolerance=0.1)`
raised `TypeError` while `assert_that(v).is_equal_to(x, tolerance=0.1)` worked, and the two spellings of
one relation answered different questions.

Everything here is a free function over values.  The mixin keeps thin wrappers so that an extension
calling `self._dict_not_equal(...)` still works, and the matcher calls the same functions directly.
"""

from __future__ import annotations

import collections
import collections.abc
import dataclasses
import re
import types
from typing import TYPE_CHECKING, Any, cast

from ..errors import _capped_format
from ._compare import (
    _EQ_ATOMIC,
    _guarded_equal,
    _keyed_types_differ,
    _kinds_never_equal,
    _node_decision,
    _resolve_comparator,
    _spec_matches,
    _types_differ,
    _walked_equal,
)
from ._diff import _child_entries, _escaped_stop, _sub_diff_entries
from ._introspection import (
    TakenApart,
    basic_size,
    is_attrs_instance,
    is_model_dump_object,
    is_namedtuple,
    keyed_names,
    keyed_pair,
    model_field_values,
    own_fields,
    weakref_offset,
)
from ._ordering import REFUSALS, equals, lookup, member
from ._path import _ROOT
from ._require import refuse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ._compare import _CompareConfig
    from ._introspection import MappingLike

    _KeysFrame = tuple[Iterator[Any], tuple[int, int] | None]
    """A mapping's keys still to compare, and the pair it put on the path, which under key specs it does not."""


def normalize_key_specs(specs: object, param: str) -> list:
    """An ``ignore``/``include`` argument as a flat list of key-specs.

    A ``list``/``set``/``frozenset`` is a collection of specs and is expanded.  A ``str``/``bytes``/
    ``tuple`` (a single key, or a nested-path key) or any non-iterable hashable key is one spec.  Any
    other iterable is refused: it is one-shot or ambiguous, and would otherwise be mishandled in silence
    as a single opaque key.  A path of no keys names nothing and is left out.
    """
    if isinstance(specs, (list, set, frozenset)):
        return [spec for spec in specs if type(spec) is not tuple or spec]
    if isinstance(specs, (str, bytes, tuple)) or not isinstance(specs, collections.abc.Iterable):
        return [specs] if type(specs) is not tuple or specs else []
    refuse(specs, "a key, a nested-path tuple, or a list/set/frozenset of them", subject=param)


def key_specs_given(specs: object) -> bool:
    """Whether an ``ignore``/``include`` argument asks for anything, a falsy key such as ``0`` or ``""`` included.

    Truthiness answered this and dropped a single falsy key in silence.  An empty collection still asks
    for nothing, as it always did, and so does a path of no keys, which is an exact empty tuple: a tuple of a
    class of its own is a key.  A collection holding nothing but such paths is an option given all the same, with
    nothing left out of it once it is read.
    """
    if type(specs) is tuple:
        return bool(specs)
    return specs is not None and not (isinstance(specs, (list, set, frozenset)) and not specs)


def comparable_fields(obj: object) -> dict | None:
    """An object with introspectable fields as a dict of them, or ``None`` when it has no fields to compare.

    Dataclasses are converted by reference rather than through `dataclasses.asdict`, which deep-copies and
    crashes on a field that cannot be copied, and a field declared ``compare=False`` is left out, as the
    dataclass's own ``==`` leaves it out.  An attrs field declared ``eq=False`` is left out the same way, and
    one declared with a key, ``eq=str.lower``, is read through it: `attrs.asdict` read the raw value, and
    ``ignore=`` failed on two instances ``==`` holds equal.

    Any other object is read by its ``__dict__`` where it holds nothing else (`own_fields`): two lists of a
    class of the caller's own were equal under ``ignore=`` whatever they held, and so were two exceptions,
    whose ``args`` are not in it.

    An exception is read as its class, its ``args`` and the attributes in its ``__dict__``, where its class
    has no room in the instance for more (`_holds_only_its_args`): an `OSError` keeps a ``filename`` in
    neither, and stays with its own ``==``.  The class is a field of its own, ``__class__``, because what an
    error is starts with its class: read as a record is, a `ValueError` and a `TypeError` of one message were
    equal.  The two names are the reader's: an entry of the ``__dict__`` under either does not replace them.
    An exception that is a dataclass, an attrs class or a model is read as that record, by the fields it
    declares, as its own generated ``==`` reads it.
    """
    through = _read_through(obj)
    if through is not None:
        return cast("dict", _fields_through(obj, through))
    if is_namedtuple(obj):
        return TakenApart(type(obj), obj._asdict())
    if issubclass(type(obj), BaseException):
        if not _holds_only_its_args(type(obj)):
            return None
        # off the slots of `BaseException`: a class may give itself an ``args`` or a ``__dict__`` of its own
        slots = BaseException.__dict__
        read = {"__class__": type(obj), "args": slots["args"].__get__(obj)}
        return TakenApart(type(obj), {**read, **slots["__dict__"].__get__(obj), **read})
    held = own_fields(obj)
    return None if held is None else TakenApart(type(obj), held)


def fields_held(obj: object) -> collections.abc.Mapping | None:
    """The fields of a record as it holds them, one level deep, or ``None`` for a value that is no record.

    For a question asked of many rows about their own fields: taking each apart all the way down, as
    `comparable_fields` does, cost a failed ``contains`` over 300 records 0.72 ms against 0.58 ms read this way.
    """
    held = _held(obj, frozenset({"dataclass", "attrs", "model"}))
    if held is not None:
        return held[0]
    return obj._asdict() if is_namedtuple(obj) else None


def _holds_only_its_args(kind: type) -> bool:
    """Whether an exception of *kind* has no room in the instance past what `BaseException` has, by its layout.

    `BaseException` has the ``__dict__`` in it already, so past it a class of the caller's own adds a weak
    reference list and nothing else.  `OSError`, `ImportError`, `SyntaxError`, `StopIteration`, an exception
    group and a class with a slot add room, and what is in it is in neither ``args`` nor ``__dict__``.
    State a class keeps outside the instance, a property over a table of its own, is not seen by this or by
    any reading of the instance.
    """
    spare = basic_size(kind) - BaseException.__basicsize__
    return spare == tuple.__itemsize__ * (weakref_offset(kind) > 0)


class _NestedTooDeepError(Exception):
    """`_flattened` went deeper than a value that ends is expected to: it may lead back to itself."""


def _flattened(node: Any, through: frozenset[str], depth: int = 0) -> Any:
    """Fields by reference, as each value's ``==`` reads them, taken apart through the kinds *through* names.

    A nested value is taken apart where the conversion each kind used to go through took it apart, so a
    nested value is judged as it was: `dataclasses.asdict` went through dataclasses, `attrs.asdict` through
    attrs instances, and `model_dump()` through models and the dataclasses inside them.  What is read is
    what is held, though, not what a serialiser or a copy makes of it.

    Nothing met is remembered, so a value that leads back to itself would never end: past 64 levels this gives
    up with `_NestedTooDeepError`.  The number is where remembering starts to pay, not a promise about the stack:
    a ring of three records took 2.25 ms found by `RecursionError` and 0.9 ms found here.
    """
    if type(node) in _EQ_ATOMIC:
        return node
    deeper = depth + 1
    if deeper > 64:
        raise _NestedTooDeepError
    if "dataclass" in through and dataclasses.is_dataclass(node) and not isinstance(node, type):
        return TakenApart(
            type(node),
            {
                field.name: _flattened(getattr(node, field.name), through, deeper)
                for field in dataclasses.fields(node)
                if field.compare
            },
        )
    if "attrs" in through and is_attrs_instance(node):
        compared = [attribute for attribute in node.__attrs_attrs__ if attribute.eq is not False]
        keys = {attribute.name: _key_of(attribute) for attribute in compared}
        return TakenApart(
            type(node),
            {
                attribute.name: getattr(node, attribute.name)
                if keys[attribute.name] is not None
                else _flattened(getattr(node, attribute.name), through, deeper)
                for attribute in compared
            },
            {name: key for name, key in keys.items() if key is not None},
        )
    if "model" in through and is_model_dump_object(node):
        return TakenApart(
            type(node),
            {name: _flattened(value, through, deeper) for name, value in model_field_values(node).items()},
        )
    # what a value is, is asked of its class from here on: a value may answer `isinstance` itself
    held: Any = node
    kind = type(held)
    if issubclass(kind, tuple) and hasattr(held, "_fields"):
        return kind(*[_flattened(item, through, deeper) for item in held])
    if issubclass(kind, (list, tuple)):
        return kind(_flattened(item, through, deeper) for item in held)
    if issubclass(kind, dict):
        # a key stays as held: taken apart, a record used as one could not be hashed
        rebuilt = {key: _flattened(value, through, deeper) for key, value in held.items()}
        return rebuilt if kind is dict else _as_its_class(held, rebuilt)
    return node


def _as_its_class(node: dict, rebuilt: dict) -> dict:
    """*rebuilt* as a dict of the class *node* is of (`_of_its_class`)."""
    kept = _of_its_class(node)
    put = _put_into(kept)
    for key, value in rebuilt.items():
        put(kept, key, value)
    return kept


def _put_into(kept: dict) -> Any:
    """What puts an item into a dict being rebuilt, past a ``__setitem__`` its class may have of its own."""
    ordered = issubclass(type(kept), collections.OrderedDict)
    return collections.OrderedDict.__setitem__ if ordered else dict.__setitem__


def _of_its_class(node: dict) -> dict:
    """An empty dict to rebuild *node* into, which keeps what its class means for equality.

    An `OrderedDict` stays one: its ``==`` reads the order, and taken apart into a plain mapping two that hold
    the same items in another order were equal under a record.  Any other dict of a class of its own keeps the
    class as a `TakenApart`: rebuilt plain, ``strict_types`` held it equal to a dict.
    """
    if issubclass(type(node), collections.OrderedDict):
        return collections.OrderedDict.__new__(type(node))
    return TakenApart(type(node), {})


def _fields_through(node: object, through: frozenset[str]) -> Any:
    """*node* taken apart (`_flattened`), and where that goes too deep to be a value that ends, taken apart once
    per value met (`_flattened_once`).

    The second way is not the first one's price: remembering every value cost a fifth of a comparison under
    ``ignore``, which a value that holds itself, or one nested deeper than the first way goes, now pays alone.
    It also takes a frame a level where the first takes two, so it is tried where the first ran out of them.
    """
    try:
        return _flattened(node, through)
    except (_NestedTooDeepError, RecursionError):
        memo: dict[int, Any] = {}
        taken = _flattened_once(node, through, memo)
        _mend(memo)
        return taken


def _mend(memo: dict[int, Any]) -> None:
    """Put the rebuilt value where `_flattened_once` left one as it was, met again while still being rebuilt.

    Left there, a tuple led back to the values not taken apart, and a record behind it was compared whole.  A
    dict or a list is the place to put it.  A tuple holding one is made again, and tuples alone lead back to
    nothing, so that ends.  A field attrs compares through a key is held raw, and stays so.
    """
    for rebuilt in list(memo.values()):
        if issubclass(type(rebuilt), dict):
            raw = rebuilt.compared_by if isinstance(rebuilt, TakenApart) else ()
            for key, value in rebuilt.items():
                if key not in raw:
                    rebuilt[key] = _mended(value, memo)
        elif issubclass(type(rebuilt), list):
            rebuilt[:] = [_mended(item, memo) for item in rebuilt]


def _mended(value: Any, memo: dict[int, Any]) -> Any:
    """*value* as it was rebuilt where it was left as it was, or made again where it is a tuple holding such a one."""
    rebuilt = memo.get(id(value), value)
    if rebuilt is not value or not issubclass(type(value), tuple):
        return rebuilt
    items = [_mended(item, memo) for item in value]
    if all(new is old for new, old in zip(items, value, strict=True)):
        return value
    return _of_its_kind(value, items)


def _of_its_kind(node: Any, items: list) -> Any:
    """A sequence of the class *node* is of over *items*, handed to its constructor as `_flattened` hands them.

    A named tuple takes them as arguments.  Any other takes a generator and not the list: a class may be built
    differently from the two, and one value taken apart the two ways then came out as two.
    """
    return type(node)(*items) if hasattr(node, "_fields") else type(node)(item for item in items)


def _flattened_once(node: Any, through: frozenset[str], memo: dict[int, Any]) -> Any:
    """`_flattened`, with each value taken apart once: met again, it is what it came apart into the first time.

    So a value that holds itself comes apart into fields that hold themselves, and the walk over them meets the
    pair again as it does in a graph of dicts.  A dict or a list is on record before its items are rebuilt, so one
    met again inside itself is the rebuilt one: left as it was, it led back to the values not taken apart, and a
    record behind it was compared whole.  A tuple cannot be, having no items until it is made, so one met again
    while it is still being rebuilt stays as it is here, and `_mend` puts the rebuilt one in its place afterwards.
    Every value met is held by the one being taken apart, so its id stays its own.
    """
    if type(node) in _EQ_ATOMIC:
        return node
    if id(node) in memo:
        return memo[id(node)]
    held = _held(node, through)
    if held is not None:
        fields, compared_by = held
        taken = memo[id(node)] = TakenApart(type(node), {}, compared_by)
        for name, value in fields.items():
            taken[name] = value if name in taken.compared_by else _flattened_once(value, through, memo)
        return taken
    if not issubclass(type(node), (list, tuple, dict)):
        return node
    # no generator: through one a level was three frames on Python 3.10, 331 levels deep against 496
    rebuilt: Any
    if issubclass(type(node), dict):
        rebuilt = memo[id(node)] = {} if type(node) is dict else _of_its_class(node)
        put = _put_into(rebuilt)
        for key, value in node.items():
            put(rebuilt, key, _flattened_once(value, through, memo))
        return rebuilt
    if type(node) is list:
        rebuilt = memo[id(node)] = []
        for item in node:
            rebuilt.append(_flattened_once(item, through, memo))
        return rebuilt
    memo[id(node)] = node
    items = [_flattened_once(item, through, memo) for item in node]
    rebuilt = memo[id(node)] = _of_its_kind(node, items)
    return rebuilt


def _held(node: Any, through: frozenset[str]) -> tuple[collections.abc.Mapping, collections.abc.Mapping | None] | None:
    """The fields `_flattened` takes *node* apart into, as *node* holds them, and the keys attrs compares some of
    them through; ``None`` for a value it does not take apart."""
    if "dataclass" in through and dataclasses.is_dataclass(node) and not isinstance(node, type):
        return {field.name: getattr(node, field.name) for field in dataclasses.fields(node) if field.compare}, None
    if "attrs" in through and is_attrs_instance(node):
        compared = [attribute for attribute in node.__attrs_attrs__ if attribute.eq is not False]
        keys = {attribute.name: _key_of(attribute) for attribute in compared}
        held = {attribute.name: getattr(node, attribute.name) for attribute in compared}
        return held, {name: key for name, key in keys.items() if key is not None}
    if "model" in through and is_model_dump_object(node):
        return model_field_values(node), None
    return None


def _key_of(attribute: Any) -> Any:
    """The key an attrs field is compared through, given as ``eq=``, or ``None``: its value is then held raw."""
    return getattr(attribute, "eq_key", None)


def _read_through(obj: object) -> frozenset[str] | None:
    """The kinds of record `comparable_fields` takes *obj* apart through, all the way down, or ``None``.

    ``None`` for a value read one level deep or not at all: a named tuple, an object through its ``__dict__``.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return frozenset({"dataclass"})
    if is_namedtuple(obj):
        return None
    if is_model_dump_object(obj):
        return frozenset({"model", "dataclass"})
    if is_attrs_instance(obj):
        return frozenset({"attrs"})
    return None


def as_fields(value: object, beside: object = None) -> Any:
    """A dict or another mapping by its keys, anything else through `comparable_fields`.

    A dict *beside* a record taken apart all the way down is taken apart as deep.  Left as held, a record the
    dict holds was compared whole against the fields of the equal one the record holds, and the two differed.
    A dict that is a record as well stays as held: taken apart it was read by its fields, and a key it held
    beside them was gone.

    What is a dict is asked of the class, since a value may answer `isinstance` itself.  A mapping that is no
    dict and no record is its keys too: refused, a `MappingProxyType` beside a record was called not dict-like,
    and a `ChainMap` was read through the attribute it keeps its maps in.
    """
    if not issubclass(type(value), dict):
        own = _read_through(value)
        if own is not None:
            return _fields_through(value, own)
        return value if mapping_shaped(value, check_values=False) else comparable_fields(value)
    through = None if issubclass(type(beside), dict) else _read_through(beside)
    if through is None or _read_through(value) is not None:
        return value
    return _fields_through(value, through)


def fields_pair(value: object, other: object) -> tuple[Any, Any]:
    """Two values through their fields, each read beside the other (`as_fields`)."""
    return as_fields(value, other), as_fields(other, value)


def _plain_sequence(value: object) -> bool:
    return isinstance(value, (list, tuple)) and not is_namedtuple(value)


def ignore_specs(ignore: object) -> list:
    """Ignore-specs, keeping nested paths whole: a one-element tuple is just that key."""
    return [
        entry[0] if type(entry) is tuple and len(entry) == 1 else entry
        for entry in normalize_key_specs(ignore, "ignore")
    ]


def include_specs(include: object) -> list:
    """Include-specs for one level: a nested path selects its first segment here, the rest deeper down."""
    return [entry[0] if type(entry) is tuple else entry for entry in normalize_key_specs(include, "include")]


_NOT_DEFINED = object()


def _defined_on(cls: type, name: str) -> object:
    """What the interpreter's own type lookup finds for *name*, or `_NOT_DEFINED`.

    A walk of the MRO namespaces, which is what `_PyType_Lookup` does and what `getattr` on the class
    does not: the ordinary one runs through the metaclass, so a `__getattr__` there can fabricate a
    member the C slot never sees, and a `__getattribute__` there can hide one it does.  Reached through
    `type.__getattribute__` for the same reason.

    A `None` found this way is a definition and not an absence.  It is how a subclass takes a special
    member away, and the lookup stops on it exactly as it stops on a real one.
    """
    for base in type.__getattribute__(cls, "__mro__"):
        namespace = type.__getattribute__(base, "__dict__")
        if name in namespace:
            return namespace[name]
    return _NOT_DEFINED


_DIRECTLY_CALLABLE = (
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
    types.MethodWrapperType,
    types.WrapperDescriptorType,
    types.BuiltinMethodType,
)
"""Callables answered without resolving anything.  A class is deliberately not one: a metaclass can null
`__call__` out, and then `callable()` says yes and instantiating raises."""


def _bound_special(candidate: object, name: str, hops: int) -> object:
    """What the interpreter would call for *name* as a special member, or `_NOT_DEFINED`.

    The type lookup plus the descriptor step, which together are `_PyObject_LookupSpecial`.  A
    definition that cannot be resolved comes back as `None`, because that is what calling it amounts
    to: not callable, and the caller says so in its own words.
    """
    raw = _defined_on(type(candidate), name)
    if raw is _NOT_DEFINED:
        return _NOT_DEFINED
    binding = _defined_on(type(raw), "__get__")
    if binding is _NOT_DEFINED:
        return raw  # nothing to resolve through, so the definition found is the one called
    if not _reachable_call(binding, hops):
        return None  # a defined `__get__` is reached whatever it holds, so `__get__ = None` raises
    resolve = cast("Callable[[object, object, type], object]", binding)
    try:
        return resolve(raw, candidate, type(candidate))
    except Exception:
        # a binding that raises would raise on the real lookup too, and this question is asked while
        # rendering a failure, where a crash replaces the failure the reader came for
        return None


def _reachable_call(value: object, hops: int = 3) -> bool:
    """Whether calling *value* reaches an implementation rather than raising `TypeError`.

    `callable()` answers one level: it says the type has a call slot, and Python's own documentation
    says that is not a promise the call succeeds.  `__call__ = None` fills the slot and fails when
    reached, which is the same trick as `__getitem__ = None` one level down.

    Bounded rather than fully recursive, and the bound is not arbitrary: almost every callable is a
    function, a method or a class and is answered by the first test, so a chain deep enough to exhaust
    the hops is one built on purpose.  A value that does is called what `callable()` calls it.
    """
    if not callable(value):
        return False
    if isinstance(value, _DIRECTLY_CALLABLE) or hops == 0:
        return True
    return _reachable_call(_bound_special(value, "__call__", hops - 1), hops - 1)


def carries_callable(candidate: object, name: str) -> bool:
    """Whether calling `candidate.name()` reaches an implementation rather than raising `TypeError`.

    Deliberately no test for where the attribute came from.  Forwarding through `__getattr__` is how a
    proxy delegates, and a rule against it refuses every wrapper over a mapping.  Two attempts at such a
    rule were made and both were unsound: fabrication is not the offence, and no nominal test tells a
    `unittest.mock` attribute from a delegated one.

    A value that answers this and is then unreadable by key is handled where it shows, in `_dict_err`,
    which falls back to a plain repr rather than letting the shape guess replace the failure.
    """
    return _reachable_call(getattr(candidate, name, None))


def supports_subscript(candidate: object) -> bool:
    """Whether `candidate[key]` will reach an implementation instead of raising `TypeError`.

    Neither `hasattr` nor plain presence on the MRO answers this.  The operator is looked up on the
    type, so a `__getattr__` on the instance answers `hasattr` for a subscript the object does not
    have, and `__getitem__ = None` in a subclass shadows a working parent while still being present.

    The descriptor step is not decoration: a `__getitem__` written as a `property` really is resolved
    and really does work, measured against CPython.
    """
    return _reachable_call(_bound_special(candidate, "__getitem__", 3))


def mapping_shaped(
    candidate: object, *, check_keys: bool = True, check_values: bool = True, check_getitem: bool = True
) -> bool:
    """Whether *candidate* has the requested dict-like attributes.

    Deliberately structural rather than `isinstance(..., Mapping)`: the package accepts anything that
    answers `keys()`/`values()`/`[]`, which is what a config object or a lightweight row wrapper does.
    """
    if type(candidate) is dict:  # fast path: a real dict satisfies every check, skip the ABC isinstance
        return True
    if not isinstance(candidate, collections.abc.Iterable):
        return False
    if check_keys and not carries_callable(candidate, "keys"):
        return False
    if check_values and not carries_callable(candidate, "values"):
        return False
    return not check_getitem or supports_subscript(candidate)


def values_differ(value: object, other: object, config: _CompareConfig | None, *, at_root: bool = False) -> bool:
    """Whether two non-mapping values differ, delegating to the shared structural walker.

    Asking the walker keeps the equality *decision* and the rendered *diff* in agreement: every shape it
    can decompose (dataclass, attrs, namedtuple, model, sequence) is then compared under the compare
    config, instead of falling back to plain equality and silently dropping that config.  Without a
    config there is nothing to honour, so the plain check is kept exactly as it was.
    """
    if value is other and not at_root:
        # identity first, as Python's containers do.  Not at the root, where `nan` made `strict_types` the weaker rule
        return False
    if config is None:
        equal = _walked_equal(value, other)
        if equal is None:
            # a graph `==` cannot finish, reached under a key option: the walk reads it, a pair met again being equal
            return bool(_child_entries(value, other, _ROOT, descended_for="unanswered"))
        return not equal
    if at_root and config.comparators and _resolve_comparator(value, config, field=None) is not None:
        # a comparator owns the root too, where the walk below starts at the children
        return _node_decision(value, other, config, at_root=True) == "leaf"
    if _kinds_never_equal(value, other) and not _guarded_equal(value, other):
        return True
    entries = _sub_diff_entries(value, other, _ROOT, config=config)
    if entries is None:
        decision = _node_decision(value, other, config, at_root=at_root)
        if decision == "strict":
            # equal by its own `==`, with what it holds still to look at: an object by its fields, a leaf by nothing
            return bool(_child_entries(value, other, _ROOT, descended_for="strict", config=config))
        return decision != "equal"
    return bool(entries)


class IncludeKeysMissingError(LookupError):
    """An ``include`` naming a key the mapping does not have, at whatever depth it was found.

    Not a difference and not a refusal of types, so neither answer fits: the builder reports it as a
    failure in its own wording, and a matcher treats it as a non-match.  Carried as an exception because
    the recursion finds it several levels down, where the verdict `True`/`False` has no room for it.
    """

    def __init__(self, mapping: object, includes: list, missing: list) -> None:
        super().__init__(f"include names {_capped_format(missing)}, which {_capped_format(mapping)} does not have")
        self.mapping = mapping
        self.includes = includes
        self.missing = missing


def filtered_to_nothing(actual: object, expected: object, *, ignore: object, include: object) -> bool:
    """Whether ``ignore`` and ``include`` left none of the keys two mappings had to compare.

    Asked once a comparison under a key filter has passed, so both sides kept the same keys and reading
    one is enough.  Two empty mappings still checked that both are empty, and an include naming a key the
    actual side lacks is a failure of its own, so neither counts.  Only `dict` values are read a second
    time: another mapping may answer differently.
    """
    if not isinstance(actual, dict) or not isinstance(expected, dict) or not (actual or expected):
        return False
    ignores = ignore_specs(ignore) if key_specs_given(ignore) else []
    includes = include_specs(include) if key_specs_given(include) else []
    return not _kept_keys(actual, ignores, includes) and not missing_include_keys(actual, includes)


def missing_include_keys(mapping: MappingLike, includes: list) -> list:
    """Include-keys naming something the mapping does not have."""
    return [key for key in includes if not isinstance(key, (re.Pattern, type)) and not member(key, mapping)]


def mapping_differs(
    actual: object,
    expected: object,
    *,
    ignore: object = None,
    include: object = None,
    config: _CompareConfig | None = None,
) -> bool:
    """Whether two dict-like values differ under the given filtering and compare config.

    Normalization happens here rather than at the call sites, because the two spellings differ and the
    difference is easy to get wrong: at one level an `include` of `("user", "session")` selects `user`,
    while the recursion into `user` needs the whole path to strip its first segment from.

    Walked on a list of frames as the structural diff is, `_Walk`, and for the same reasons: a mapping nested
    past Python's recursion limit is answered, and the pairs on the path are one set rather than a copy a level.

    A pair met again inside itself is equal as far as that pair goes, where it is the same question: the pair
    compared whole.  Under key specs still to apply it is another question each time, since a spec applies at its
    own level and a path loses a segment a level, so such a pair is neither put on the path nor found there.  The
    specs run out after the longest path, which is where that ends.
    """
    on_path: set[tuple[int, int]] = set()
    opened = _mapping_opened(actual, expected, ignore, include, config, on_path, inside=False)
    if isinstance(opened, bool):
        return opened
    stack = [opened]
    while stack:
        keys, pair = stack[-1]
        try:
            nested = next(keys, None)
        except RuntimeError as error:
            escaped = _escaped_stop(error)
            if escaped is None:
                raise
        else:
            if nested is None:
                stack.pop()
                on_path.discard(pair)
            elif nested is True:
                return True
            else:
                stack.append(nested)
            continue
        raise escaped
    return False


def _mapping_opened(
    actual: object,
    expected: object,
    ignore: object,
    include: object,
    config: _CompareConfig | None,
    on_path: set[tuple[int, int]],
    *,
    inside: bool,
) -> bool | _KeysFrame:
    """The verdict on two mappings where it is reached before their keys, else the frame over the keys.

    *inside* says the pair was reached by a walk rather than handed to one.
    """
    # one cast at the top beats a suppression on each of the six lookups below
    left = cast("MappingLike", actual)
    right = cast("MappingLike", expected)
    ignoring, including = key_specs_given(ignore), key_specs_given(include)
    pair = None if ignoring or including else (id(actual), id(expected))
    if pair in on_path:
        return False

    if pair is not None and config is None:
        try:
            return not _guarded_equal(actual, expected)
        except RecursionError:
            # inside a walk, a graph `==` cannot finish is taken key by key below, where a pair met again is equal
            if not inside:
                raise

    ignores = ignore_specs(ignore) if ignoring else []
    includes = include_specs(include) if including else []
    # read once for the whole mapping: asked per key, a five-hundred path include normalised itself five
    # hundred times.  After `include_specs`, so a one-shot iterable is still refused under its own name
    nested_paths = ignore_specs(include) if including else []
    if includes:
        missing = missing_include_keys(left, includes)
        if missing:
            raise IncludeKeysMissingError(left, includes, missing)
    keys_in_actual = _kept_keys(left, ignores, includes)
    keys_in_expected = _kept_keys(right, ignores, includes)
    if not equals(keys_in_actual, keys_in_expected) or _order_differs(actual, expected, keys_in_actual):
        return True
    if (
        config is not None
        and config.strict_types
        and (
            # two elements taken apart reach here with no parent walk to have compared their classes
            _types_differ(actual, expected)
            or _keyed_types_differ(
                dict.fromkeys(key for key in left if key in keys_in_actual),
                dict.fromkeys(key for key in right if key in keys_in_expected),
            )
        )
    ):
        # `{True: "a"}` and `{1: "a"}` are equal to Python and not under strict types; only the keys still compared
        return True
    if pair is not None:
        on_path.add(pair)
    keys = _differing_keys(left, right, keys_in_actual, ignores, nested_paths, config, on_path, ignoring, including)
    return keys, pair


def _differing_keys(
    left: MappingLike,
    right: MappingLike,
    keys_in_actual: set,
    ignores: list,
    nested_paths: list,
    config: _CompareConfig | None,
    on_path: set[tuple[int, int]],
    ignoring: bool,
    including: bool,
) -> Iterator[bool | _KeysFrame]:
    """The keys of two mappings in turn: ``True`` where one differs, which ends the walk, or a mapping's frame."""
    keyed = keyed_names(left, right)
    # under strict types the decision has to know whether a path goes on into the pair it is asked of
    strict = config is not None and config.strict_types and (ignoring or including)
    paths = [entry for entry in (*ignores, *nested_paths) if type(entry) is tuple] if strict else ()
    for key in keys_in_actual:
        if key in keyed:
            nested_left, nested_right = keyed_pair(left, right, key)
        else:
            try:
                nested_left, nested_right = left[key], right[key]
            except REFUSALS as refusal:
                nested_left, nested_right = left[key], lookup(right, key, refusal)[1]
        if config is not None:
            keys_left_out = bool(paths) and any(equals(entry[0], key) for entry in paths)
            decision = _node_decision(nested_left, nested_right, config, field=key, keys_left_out=keys_left_out)
            if decision == "equal":
                continue
            if decision == "leaf":
                yield True
        nested_ignore = (
            [entry[1:] for entry in ignores if type(entry) is tuple and equals(entry[0], key)] if ignoring else None
        )
        # the nested half of an include keeps whole paths, and the level above already consumed the first segment
        nested_include = (
            [entry[1:] for entry in nested_paths if type(entry) is tuple and equals(entry[0], key)]
            if including
            else None
        )
        nested = _nested_differs(
            nested_left, nested_right, ignore=nested_ignore, include=nested_include, config=config, on_path=on_path
        )
        if nested is True:
            yield True
        elif nested is not False:
            yield nested


def _kept_keys(mapping: MappingLike, ignores: list, includes: list) -> set:
    """The keys a comparison looks at: those no ignore-spec names, and an include-spec does when there are any."""
    return {
        key
        for key in mapping
        if not (ignores and _spec_matches(key, mapping[key], ignores))
        and (not includes or _spec_matches(key, mapping[key], includes))
    }


def _order_differs(actual: object, expected: object, kept: set) -> bool:
    """Whether two `OrderedDict` values hold the compared keys in different orders, which their `==` reads."""
    if not (isinstance(actual, collections.OrderedDict) and isinstance(expected, collections.OrderedDict)):
        return False
    return not equals([key for key in actual if member(key, kept)], [key for key in expected if member(key, kept)])


def _nested_differs(
    left: object,
    right: object,
    *,
    ignore: object,
    include: object,
    config: _CompareConfig | None,
    on_path: set[tuple[int, int]],
) -> bool | _KeysFrame:
    """One value under a key, compared with the rest of the key path that reaches into it.

    A verdict, or the frame over the keys of a mapping still to compare, which `mapping_differs()` walks.
    """
    if mapping_shaped(left, check_values=False) and mapping_shaped(right, check_values=False):
        return _mapping_opened(left, right, ignore, include, config, on_path, inside=True)
    if key_specs_given(ignore) or key_specs_given(include):
        # a path that goes on into a value is followed through its fields, which for a mapping are its keys
        left_fields, right_fields = _keyed(left, right), _keyed(right, left)
        if left_fields is not None and right_fields is not None:
            return _mapping_opened(left_fields, right_fields, ignore, include, config, on_path, inside=True)
    return values_differ(left, right, config)


def _keyed(value: object, beside: object) -> Any:
    """A mapping as what a key path reads it through, its keys, and anything else through its fields."""
    if mapping_shaped(value, check_values=False) and not issubclass(type(value), dict):
        return value
    return as_fields(value, beside)


def filtered_differs(
    actual: object, expected: object, *, ignore: object, include: object, config: _CompareConfig | None
) -> bool:
    """`is_equal_to`'s verdict under ``ignore``/``include`` for a pair that is not two mappings.

    The builder takes a sequence pair element by element and anything else through its fields.  A matcher
    answering the same question takes the same route, or `match.equal_to(user, ignore="updated_at")`
    compared ``updated_at`` anyway.  An element with no fields is compared whole, as the builder compares
    it.  At the top a value with no fields is one the builder refuses with a `TypeError`, and a matcher,
    which must not raise, answers that it differs.
    """
    if _plain_sequence(actual) and _plain_sequence(expected):
        sequence_actual = cast("list | tuple", actual)
        sequence_expected = cast("list | tuple", expected)
        if len(sequence_actual) != len(sequence_expected) or _kinds_never_equal(actual, expected):
            return True
        return any(
            _filtered_pair_differs(item, counterpart, ignore=ignore, include=include, config=config, at_root=False)
            for item, counterpart in zip(sequence_actual, sequence_expected, strict=True)
        )
    return _filtered_pair_differs(actual, expected, ignore=ignore, include=include, config=config, at_root=True)


def _filtered_pair_differs(
    actual: object, expected: object, *, ignore: object, include: object, config: _CompareConfig | None, at_root: bool
) -> bool:
    left, right = fields_pair(actual, expected)
    if left is None or right is None:
        return at_root or values_differ(actual, expected, config)
    return mapping_differs(left, right, ignore=ignore, include=include, config=config)
