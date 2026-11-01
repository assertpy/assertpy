"""Runtime-checkable protocols for duck-typed object introspection.

The comparison and diff code accepts arbitrary user objects, so it inspects them structurally: pydantic
models (``model_dump``), ``attrs`` classes (``__attrs_attrs__``) and namedtuples (``_fields`` /
``_asdict``).  Expressing those shapes as ``@runtime_checkable`` protocols lets the diff code use
``isinstance`` checks the type checker can follow - narrowing the value instead of probing it with
``hasattr`` and then suppressing the attribute access.
"""

from __future__ import annotations

import collections
import collections.abc
import dataclasses
import datetime
import enum
import itertools
import numbers
import os
import pathlib
import reprlib
import sys
import types
import uuid
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeGuard, TypeVar, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import CellType

_T = TypeVar("_T")

# absolute paths in a set: one hash lookup a frame, and a user file of the same name cannot shadow ours
ASSERTPY_FILES: Final = frozenset(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), name)
    for name in os.listdir(os.path.dirname(os.path.dirname(__file__)))
    if name.endswith(".py")
)


def caller_stacklevel() -> int:
    """The ``stacklevel`` that points a warning its caller raises at the first frame outside the package.

    Counted, not fixed: a builder a `log_passes()` block made runs each assertion through frames of its own, and a
    fixed count pointed into them.
    """
    frame = sys._getframe(1)  # the caller, which `warnings.warn(stacklevel=1)` names
    level = 1
    while frame is not None and frame.f_code.co_filename in ASSERTPY_FILES:
        frame = frame.f_back
        level += 1
    return level


# exact builtins carrying no `__dict__`, so the isinstance is skipped; a subclass takes the structural check
_ATOMIC_TYPES: Final = frozenset(
    {type(None), bool, int, float, complex, str, bytes, bytearray, list, tuple, set, frozenset}
)


@runtime_checkable
class SupportsModelDump(Protocol):
    """A pydantic-style model exposing ``model_dump()``."""

    def model_dump(self) -> dict[str, Any]: ...


@runtime_checkable
class NamedTupleLike(Protocol):
    """A ``collections.namedtuple`` / ``typing.NamedTuple`` instance."""

    _fields: tuple[str, ...]

    def _asdict(self) -> dict[str, Any]: ...


@runtime_checkable
class AttrsInstance(Protocol):
    """An ``attrs``-decorated instance exposing ``__attrs_attrs__``."""

    __attrs_attrs__: tuple[Any, ...]


class WarningLogger(Protocol):
    """What a warning-mode assertion asks of a logger: the one method it calls when an assertion fails.

    Structural rather than either concrete type, because both are promised and both work.  The
    docstring of `assert_warn` says `Logger`, the default the builder installs is a `LoggerAdapter`,
    and naming one of them in the signature refuses the other for no reason the runtime shares.

    Widest on both sides.  `str` because a logger declared to take only a string is a working one and
    the message here is always a string, and `object` because a return this never reads is not a
    reason to refuse a logger that has one.
    """

    def warning(self, msg: str) -> object: ...


@runtime_checkable
class Readable(Protocol):
    """A file-like object, recognised by the one method that reads it whole.

    The return is spelled out because the caller promises a `str`: a text handle answers with one and a
    binary handle with `bytes`, which is decoded, and a reader that answers with neither would be
    handed straight back through a signature that says `str`.
    """

    def read(self) -> str | bytes: ...


@runtime_checkable
class MappingLike(Protocol):
    """A dict-like object that can be iterated over and subscripted by key."""

    def keys(self) -> Any: ...

    def __iter__(self) -> Any: ...

    def __getitem__(self, key: Any, /) -> Any: ...  # positional, so a plain `dict` satisfies it


def is_model_dump_object(obj: object) -> TypeGuard[SupportsModelDump]:
    """Return whether ``obj``'s type exposes a callable ``model_dump()`` (e.g. a pydantic model)."""
    if type(obj) is dict or type(obj) in _ATOMIC_TYPES:
        return False
    # on the type first, which a `unittest.mock` object's fabricated attribute never reaches; then on the
    # value, because an ordinary method is a non-data descriptor and `obj.model_dump = None` shadows it
    return hasattr(type(obj), "model_dump") and callable(getattr(obj, "model_dump", None))


def is_pydantic_model(obj: object) -> TypeGuard[SupportsModelDump]:
    """Whether *obj* is an instance of pydantic's ``BaseModel``, asked without importing pydantic.

    No model exists unless pydantic is loaded already, so an absent module answers no.
    """
    pydantic = sys.modules.get("pydantic")
    return pydantic is not None and isinstance(obj, pydantic.BaseModel)


def is_pydantic_model_class(candidate: object) -> bool:
    """Whether *candidate* is a subclass of pydantic's ``BaseModel``, asked without importing pydantic."""
    pydantic = sys.modules.get("pydantic")
    return pydantic is not None and isinstance(candidate, type) and issubclass(candidate, pydantic.BaseModel)


class TakenApart(dict):
    """The fields of one value as it holds them, with its class and the keys attrs compares fields through.

    Read as a plain mapping, a nested value of another class with the same fields passed a comparison
    under ``strict_types`` and ``ignore`` together, which the rule says holds at every depth.  A field
    declared with an ``eq=`` key is compared through it against the same field of another instance, as
    attrs' own ``==`` does, and as held against anything else, a payload's value included.

    Printed as the class it was read from, ``Row(name='a')`` for a record and ``Kept({'x': 1})`` for a dict of
    a class of its own, so a failure names what was compared.
    """

    __slots__ = ("compared_by", "kind")

    def __init__(
        self,
        kind: type,
        fields: collections.abc.Mapping,
        compared_by: collections.abc.Mapping[object, Callable[[object], object]] | None = None,
    ) -> None:
        super().__init__(fields)
        self.kind = kind
        self.compared_by = compared_by or {}

    @property
    def keyed(self) -> bool:
        """Whether the class this was read from is a dict's, whose parts are keys rather than fields."""
        return issubclass(self.kind, dict)

    @reprlib.recursive_repr()
    def __repr__(self) -> str:
        if self.keyed:
            return f"{class_name(self.kind)}({dict.__repr__(self)})"
        fields = ", ".join(f"{field}={value!r}" for field, value in self.items() if not self._says_its_class(field))
        return f"{class_name(self.kind)}({fields})"

    def _says_its_class(self, field: object) -> bool:
        """Whether *field* is the class an exception is read with, which the name ahead of the bracket has said."""
        return field == "__class__" and self[field] is self.kind and issubclass(self.kind, BaseException)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, dict):
            return NotImplemented
        if not self.compared_by and not (isinstance(other, TakenApart) and other.compared_by):
            return dict.__eq__(self, other)
        keyed = keyed_names(self, other)
        pairs = (keyed_pair(self, other, name) if name in keyed else (self[name], other[name]) for name in self)
        return self.keys() == other.keys() and all(left is right or bool(left == right) for left, right in pairs)


def laid_out(value: object) -> object:
    """*value* with every record taken apart turned into a plain dict of its fields, for a reader that lays
    containers out and prints anything else on one line.

    Followed through the values of a ``dict`` and the items of a ``list`` or a ``tuple``, each of exactly that
    class, told by identity so that no class is asked.  A mapping is turned only where every key in it is one
    the interpreter hashes and compares by code of its own: exactly a ``str``, an ``int``, a ``bool``, a
    ``float``, a ``bytes`` or ``None``.  Putting a value back looks its key up, and beside a key of any other
    class that runs the class's ``__hash__`` or ``__eq__``, so such a mapping stays as it is, a record among
    them.  A dict with nothing to turn comes back as the same object.  A part two places share is turned once,
    and a value that holds itself is left where the walk meets it again.
    """
    return _laid_out(value, {}, set())


def plainly_hashed(key: object) -> bool:
    """Whether *key* is exactly one of the six plain kinds, whose own hash and equality are the interpreter's.

    A lookup runs no other code only where every key the dict holds is one too: a key of another class that
    hashes the same is asked its own ``__eq__``.
    """
    kind = type(key)
    return kind is str or kind is int or kind is bool or kind is float or kind is bytes or key is None


def _laid_out(value: object, done: dict[int, object], above: set[int]) -> object:
    kind = type(value)
    if not (kind is TakenApart or kind is dict or kind is list or kind is tuple):
        return value
    mark = id(value)
    if mark in above:
        return value
    if mark in done:
        return done[mark]
    above.add(mark)
    made: object = value
    if kind is list or kind is tuple:
        items = cast("list[object] | tuple[object, ...]", value)
        parts = [_laid_out(part, done, above) for part in items]
        if any(new is not old for new, old in zip(parts, items, strict=True)):
            made = kind(parts)
    else:
        held = list(dict.items(cast("dict[object, object]", value)))
        if all(plainly_hashed(key) for key, _ in held):
            # a copy keeps the hashes it was made with, and putting a value back compares plain keys alone
            fields = dict.copy(cast("dict[object, object]", value))
            for key, old in held:
                if (new := _laid_out(old, done, above)) is not old:
                    fields[key] = new
            if kind is TakenApart or any(fields[key] is not old for key, old in held):
                made = fields
    above.discard(mark)
    done[mark] = made
    return made


_PART_READERS = tuple(
    type.__getattribute__(kind, "__dict__")["__eq__"]
    for kind in (
        list,
        tuple,
        dict,
        collections.OrderedDict,
        collections.abc.Mapping,
        types.MappingProxyType,
        TakenApart,
    )
)
"""The ``__eq__`` of each kind whose values are equal exactly as what they hold is."""


class KeyedValue:
    """One of two fields declared with an ``eq=`` key, for the one comparison of them: equal when the keys are.

    Built for the comparison and never kept, so what a failure hands out and prints is the value held.
    """

    __slots__ = ("held", "key")

    def __init__(self, held: object, key: Callable[[object], object]) -> None:
        self.held = held
        self.key = key

    def __eq__(self, other: object) -> bool:
        # read at the comparison: `ignore_null` looks at what is held first, and `str.lower(None)` raises
        return self.key(self.held) == other.key(other.held) if isinstance(other, KeyedValue) else NotImplemented


def keyed_names(fields: object, counterpart: object) -> collections.abc.Set[object]:
    """The fields two sides both compare through an attrs key, and none unless both are a `TakenApart`.

    Asked once for a pair of mappings rather than once per field: asked per field, a 200-key dict diff
    took 20% longer, on dicts that hold no key at all.
    """
    if type(fields) is TakenApart and type(counterpart) is TakenApart:
        return fields.compared_by.keys() & counterpart.compared_by.keys()
    return frozenset()


def keyed_pair(fields: Any, counterpart: Any, name: object) -> tuple[KeyedValue, KeyedValue]:
    """Field *name* of two sides, each read through its own key, for a name `keyed_names` answered."""
    return (
        KeyedValue(fields[name], fields.compared_by[name]),
        KeyedValue(counterpart[name], counterpart.compared_by[name]),
    )


def class_name(kind: type) -> str:
    """The name of a class as an exact `str`, read off the slot: a metaclass can make the attribute raise."""
    return str.__str__(type.__dict__["__name__"].__get__(kind))


def holds_only_its_dict(kind: type) -> bool:
    """Whether an instance of *kind* holds nothing but its ``__dict__``, read off the layout of its class.

    A slot, the items of a builtin container and the fields of a type written in C are all room in the instance
    past the object's own header, its ``__dict__`` and its weak reference list.  A list of kinds was the first
    answer, and each one found missing was a comparison that passed: `list`, `array.array`, an exception.
    """
    spare = basic_size(kind) - object.__basicsize__
    spare -= tuple.__itemsize__ * ((_dict_offset(kind) > 0) + (weakref_offset(kind) > 0))
    return spare == 0


# off the slots of `type`: a metaclass may spell a size or an offset of its own
basic_size, _dict_offset, weakref_offset = (
    type.__dict__[name].__get__ for name in ("__basicsize__", "__dictoffset__", "__weakrefoffset__")
)


def own_fields(obj: object) -> dict[str, Any] | None:
    """The ``__dict__`` of an object that holds nothing else, or ``None`` for a value that is no bag of fields.

    A value of a builtin kind is none even when it carries a ``__dict__``: a subclass of `Decimal` or `str` has
    an empty one, and reading it made every two such values compare equal.  Nor is any value that holds
    something outside its ``__dict__`` (`holds_only_its_dict`): two lists of a class of the caller's own were
    equal under ``ignore=`` whatever they held.
    """
    builtin_kinds = (
        type,
        numbers.Number,
        str,
        bytes,
        bytearray,
        datetime.date,
        datetime.time,
        datetime.timedelta,
        enum.Enum,
        uuid.UUID,
        pathlib.PurePath,
    )
    if hasattr(obj, "__dict__") and not isinstance(obj, builtin_kinds) and holds_only_its_dict(type(obj)):
        return vars(obj)
    return None


def kind_of(value: object) -> type:
    """The class *value* was read from: its own, the one a `TakenApart` holds the fields of, or a keyed field's."""
    if type(value) is KeyedValue:
        return type(value.held)
    # by the type itself: `isinstance` reads a ``__class__`` the value may answer with code of its own
    return value.kind if type(value) is TakenApart else type(value)


def eq_keyed(attribute: Any, value: object) -> object:
    """An attrs field's value as its ``==`` compares it: through the key given as ``eq=``, when there is one."""
    key = getattr(attribute, "eq_key", None)
    return value if key is None else key(value)


def as_held(value: object) -> object:
    """*value* as the instance held it, past the `KeyedValue` one comparison reads it through."""
    return value.held if type(value) is KeyedValue else value


def model_field_values(model: SupportsModelDump) -> dict[Any, Any]:
    """A model's declared fields and extras as the values they hold, not what serialising makes of them.

    `model_dump()` runs every `field_serializer`, leaves out a field declared ``exclude=True`` and adds the
    computed ones, and pydantic's ``==`` does none of that.  Read through it, `M(f=1)` and `M(f="1")`
    compared equal under ``ignore=``, ``include=``, ``strict_types=`` and ``tolerance=`` while ``==`` told
    them apart, and the structured diff showed serialised values beside a message showing the held ones.

    Only a pydantic ``BaseModel`` is read this way.  A duck type may carry a ``model_fields`` of its own
    meaning, pydantic's own attribute names, or no ``__dict__`` at all, and is read through `model_dump()`,
    which is all the duck type promises.

    What pydantic's ``==`` compares beyond these is not read: the model's class, which a configured
    comparison leaves to ``strict_types``, and private attributes, so a pair differing only there fails
    plainly and passes a configured comparison, as it did through the dump.

    An extra named like a declared field is refused.  Validation never produces one, and the model then
    holds two values under one name, which no reading field by field can show: `model_dump()` keeps the
    extra's, ``==`` compares both.
    """
    if not is_pydantic_model(model):
        return model.model_dump()
    # `Any` because pydantic comes off `sys.modules`, and `model_fields` because `__pydantic_fields__` is 2.10+
    model_class: Any = type(model)
    declared = model_class.model_fields
    held = vars(model)
    values = {name: held[name] for name in declared if name in held}
    extra = getattr(model, "__pydantic_extra__", None)
    if isinstance(extra, collections.abc.Mapping):
        shadowing = next((name for name in extra if name in declared), None)
        if shadowing is not None:
            raise TypeError(
                f"{type(model).__name__} holds an extra named {shadowing!r} beside the field of that name,"
                " which validation never produces, so its fields cannot be read one by one"
            )
        values.update(extra)
    return values


def is_namedtuple(obj: object) -> TypeGuard[NamedTupleLike]:
    """Return whether ``obj`` is a namedtuple instance (a ``tuple`` whose type carries the whole surface).

    Both ``_fields`` and ``_asdict``, because the callers use both: a ``tuple`` subclass with a bare
    ``_fields`` is not one, and asking for only that let it through.

    Asked of the type and not the instance, as its two neighbours are and for the same reason.  A
    ``unittest.mock`` object fabricates every attribute through ``__getattr__``, so it answered all three
    of these and the diff walk read a call's own elements as field names, then as keys.  Its class
    carries none of them.

    Cheaper as well as narrower: a ``runtime_checkable`` protocol was measured here at 876 ns against
    41 ns for the attribute, on the walk that asks this about every differing element.
    """
    return isinstance(obj, tuple) and hasattr(type(obj), "_fields") and hasattr(type(obj), "_asdict")


def is_attrs_instance(obj: object) -> TypeGuard[AttrsInstance]:
    """Return whether ``obj`` is an ``attrs``-decorated instance (not the class itself, which also
    carries ``__attrs_attrs__`` but has no field values to read).

    The atomic fast path is the same one its two neighbours above have, and it was the one predicate
    missing it.  That mattered out of proportion to the line: the diff walk asks this about every
    differing element, and a profile of a 2000-element sequence diff put 39% of the whole walk inside
    the ``runtime_checkable`` isinstance this skips.
    """
    if type(obj) in _ATOMIC_TYPES:
        return False
    return not isinstance(obj, type) and hasattr(type(obj), "__attrs_attrs__")


def is_mapping_like(obj: object) -> TypeGuard[MappingLike]:
    """Return whether ``obj`` is dict-like: iterable with ``keys()`` and ``[]`` access."""
    if type(obj) is dict:
        return True
    if type(obj) in _ATOMIC_TYPES:
        return False
    # read with a default: a value may say it is a dict through `__class__` and have no `keys` at all
    return isinstance(obj, MappingLike) and callable(getattr(obj, "keys", None))


def keyed_snapshot(candidate: object) -> MappingLike | None:
    """*candidate* as something safe to walk by key, or `None` when it cannot be walked that way.

    Iteration yields keys for a mapping and values for a sequence, and no test of the type tells which a
    duck-typed value does.  `unittest.mock.call_args` is a tuple subclass answering `keys`, so a renderer
    walked it for keys, got its items and indexed the tuple with one.

    A snapshot rather than a yes-or-no answer, because a probe and the walk that follows it are two
    readings of the same value: an iterator that yields `0` on the first pass and `"bad"` on the second
    passes the probe and raises in the walk.  Reading once and rendering from what was read closes that.

    Only a `dict` is handed back as it is, and a `TakenApart`, read once already and carrying the class
    ``strict_types`` compares.  Registering as a `Mapping` promises an interface and not stability between
    reads, so a custom one is snapshotted like anything else.
    """
    if type(candidate) is dict or type(candidate) is TakenApart:
        return cast("MappingLike", candidate)
    keyed = cast("MappingLike", candidate)
    try:
        # an OrderedDict stays one, since its `==` reads the order a plain dict would forget
        snapshot = collections.OrderedDict() if isinstance(candidate, collections.OrderedDict) else {}
        snapshot.update((key, keyed[key]) for key in keyed)
    except Exception:
        return None
    return snapshot


def is_same_implementation(existing: object, candidate: object) -> bool:
    """Whether two registrations are the same implementation rather than two claiming one name.

    Object identity is too strict.  A ``def`` inside a pytest fixture builds a new function object
    every time the fixture runs, and a module-scoped fixture in ``conftest.py`` is the documented way
    to share an extension across test files, so that shape would otherwise look like a clash on the
    second module.  CPython reuses the enclosing code object across those rebuilds, and it differs the
    moment the body does, which is exactly the line wanted here.

    Callables without a ``__code__`` (instances with ``__call__``, builtins, partials) fall back to
    identity, which is the strictest answer available for them.

    A decorator's wrapper shares its code with everything that decorator wraps, so the functions a
    wrapper holds, in its closure, its defaults or its ``__wrapped__``, are compared the same way: two
    wrappers are one implementation only if what they wrap is.  Anything else they hold is data and is
    not compared, a callable without code (a builtin, a partial, a mock) included.  A fixture rebuilding
    its function carries fresh data every time, and the latest registration replacing the earlier one
    is the point of accepting it.
    """
    return _same_implementation(existing, candidate, set())


def _same_implementation(existing: object, candidate: object, seen: set[tuple[int, int]]) -> bool:
    if existing is candidate:
        return True
    left = getattr(existing, "__code__", None)
    if left is None or left is not getattr(candidate, "__code__", None):
        return False
    # a closure that holds its own function reaches this pair again
    if (id(existing), id(candidate)) in seen:
        return True
    seen.add((id(existing), id(candidate)))
    return all(
        _same_implementation(inner, other, seen)
        for inner, other in _held(existing, candidate)
        if isinstance(inner, types.FunctionType) or isinstance(other, types.FunctionType)
    )


def _held(existing: object, candidate: object) -> Iterator[tuple[object, object]]:
    """What two functions of one code object hold, side by side: closure cells, defaults, what they wrap."""
    # one code object, so one set of free variables on both sides
    cells = zip(
        getattr(existing, "__closure__", None) or (), getattr(candidate, "__closure__", None) or (), strict=True
    )
    yield from ((_cell_contents(mine), _cell_contents(theirs)) for mine, theirs in cells)
    yield from itertools.zip_longest(
        getattr(existing, "__defaults__", None) or (), getattr(candidate, "__defaults__", None) or ()
    )
    mine, theirs = getattr(existing, "__kwdefaults__", None) or {}, getattr(candidate, "__kwdefaults__", None) or {}
    yield from ((mine.get(name), theirs.get(name)) for name in mine.keys() | theirs.keys())
    yield getattr(existing, "__wrapped__", None), getattr(candidate, "__wrapped__", None)


def _cell_contents(cell: CellType) -> object:
    """What a closure cell holds, or ``None`` for one not yet filled."""
    try:
        return cell.cell_contents
    except ValueError:
        return None


def is_own_iterator(value: object) -> bool:
    """Whether *value* is an iterator, so the first pass over it is the only one there is.

    Asked of its type rather than through `iter()`: this is asked while a failure is being described,
    and a closed file answers `iter()` with `ValueError`.
    """
    return issubclass(type(value), collections.abc.Iterator)


class Replay:
    """What a one-shot iterator has handed out so far, with the iterator for the rest.

    A builder keeps one for a value that is its own iterator, so every link of a chain reads the same items:
    read by the first link alone, the second passed or failed over nothing.  Each walk starts at the first item
    and takes one from the iterator only past what was handed out, so a walk that stops early leaves the rest
    untaken and an endless generator is read no further than before.  An item is kept before it is handed on:
    code of the caller's that raises over it does not lose it for the next link.  An error the iterator
    itself raises is its own to repeat or not: asked again, a generator that raised is at its end, and an
    iterator that goes on is read on.
    """

    __slots__ = ("_rest", "_seen", "given_away", "source")

    def __init__(self, source: Iterator[Any]) -> None:
        self.source = source
        self._rest: Iterator[Any] | None = source
        self._seen: list[Any] = []
        self.given_away = False

    def give_away(self) -> None:
        """Note that code of the caller's is handed the iterator itself after a part of it was read here.

        What that code takes of the rest then goes missing between what was read and what is left, and stays
        missing: once noted, it is not taken back.  With nothing read yet, or all of it, there is no such gap.
        A walk still going when it is noted is refused at its next item past what was read, as the next link is.
        """
        if self._rest is not None and self._seen:
            self.given_away = True

    def drained(self) -> list[Any]:
        """Every item in a list of its own, the rest taken in one go: through `__iter__`, 200 cost 7 times more."""
        rest = self._rest
        if rest is not None:
            self._seen.extend(rest)
            self._rest = None
        return list(self._seen)

    def __iter__(self) -> Iterator[Any]:
        seen = self._seen
        index = 0
        while True:
            if index == len(seen):
                rest = self._rest
                if rest is None:
                    return
                if self.given_away:
                    raise handed_away()
                try:
                    seen.append(next(rest))
                except StopIteration:
                    self._rest = None
                    return
            yield seen[index]
            index += 1


def handed_away() -> TypeError:
    """The refusal of a read of a one-shot iterator past the part read before a predicate was handed it."""
    return TypeError(
        "val is a one-shot iterator that a predicate was handed after a part of it was read, so what"
        " is left of it cannot be told. Assert on list(...) of it instead"
    )


def materialized(value: Iterable[_T]) -> Iterable[_T]:
    """``value``, drained into a list when it is a one-shot iterator, handed back untouched otherwise.

    An object that is its own iterator (a generator, a file, ``map``/``filter``/``zip``) is consumed by
    the first pass over it.  Assertions that walk their subject more than once - once to decide and
    again to describe, or once per argument - therefore see an empty value on the second pass, and
    either report a wrong verdict or a message with the wrong contents in it.

    Re-iterable values are returned as they are, so nothing is copied on the ordinary path.  A value
    that cannot be iterated at all is also returned as it is, leaving the caller's own guard to produce
    the error message it wants.

    Being its own iterator is not the only way to have one position: a wrapper handing out one shared
    iterator answers no here and still loses what a first walk read, so ``satisfies()`` over one
    reports the remainder rather than the value.  That is left uncaught on purpose.  Copying anything
    that merely lacks a length instead turns a Pydantic model into a list of its field pairs, and
    walking one to find out costs the position when the position is shared.
    """
    try:
        return list(value) if iter(value) is value else value
    except TypeError:
        return value


def compares_by_parts(kind: type) -> bool:
    """Whether the ``==`` of *kind* is one known to read the parts a walk takes its values apart into.

    Known by being the thing itself, never by where it says it came from: the method a builtin container, `Mapping`
    or pydantic's ``BaseModel`` defines, or code that is what `dataclasses` or attrs writes for the fields the class
    has (`_written_again`).  Any other ``==`` may hold two values apart for a reason their parts do not show.

    Kept once found, for at most 256 classes, with the ``__eq__`` it was found for and the code that ran: building
    the twin cost a ring of a hundred records 15 ms, and a class given another ``__eq__``, or one given other code,
    is asked again.
    """
    owner, written = definition_of(kind, "__eq__") or (object, None)
    ran = getattr(written, "__code__", None)
    if kind in _COMPARED_BY_PARTS and _COMPARED_BY_PARTS[kind] == (id(written), id(ran)):
        return True
    pydantic = sys.modules.get("pydantic")
    known = (
        any(written is reader for reader in _PART_READERS)
        or (pydantic is not None and written is type.__getattribute__(pydantic.BaseModel, "__dict__").get("__eq__"))
        or _written_again(owner, written)
    )
    if known and len(_COMPARED_BY_PARTS) < 256:
        _COMPARED_BY_PARTS[kind] = (id(written), id(ran))
    return known


_COMPARED_BY_PARTS: dict[type, tuple[int, int]] = {}
"""What `compares_by_parts` has found: a class, and which ``__eq__`` and which code of it the answer was for.  The
class holds both, so neither id is taken by another object while the class is here."""


def _written_again(owner: type, written: object) -> bool:
    """Whether *written*, the ``__eq__`` *owner* defines, is the code `dataclasses` or attrs writes for its fields.

    Asked by having the same library write one for a twin with the same fields and comparing the two code objects.
    A file name would not do: the method `dataclasses` writes names none, and neither does one put there by ``exec``.
    Only a plain function is read: any other object can carry a ``__code__`` it does not run.  The keys attrs
    compares fields through are globals of the function it writes, so those are held to being the same objects.
    """
    namespace = type.__getattribute__(owner, "__dict__")
    attr = sys.modules.get("attr")
    if type(written) is not types.FunctionType:
        return False
    if "__dataclass_fields__" in namespace:
        fields = dataclasses.fields(cast("Any", owner))
        twin = dataclasses.dataclass(
            type(
                "twin",
                (),
                {
                    "__annotations__": dict.fromkeys((field.name for field in fields), object),
                    **{field.name: dataclasses.field(default=None, compare=field.compare) for field in fields},
                },
            )
        )
    elif "__attrs_attrs__" in namespace and attr is not None:
        twin = attr.make_class(
            "twin",
            {
                attribute.name: attr.ib(default=None, eq=attribute.eq if attribute.eq_key is None else attribute.eq_key)
                for attribute in namespace["__attrs_attrs__"]
            },
        )
    else:
        return False
    again = type.__getattribute__(twin, "__dict__")["__eq__"]
    code, ours = written.__code__, again.__code__
    keys = again.__globals__ if "__attrs_attrs__" in namespace else {}
    return (code.co_code, code.co_names, code.co_consts) == (ours.co_code, ours.co_names, ours.co_consts) and all(
        written.__globals__.get(name) is key for name, key in keys.items() if name in ours.co_names
    )


# off the slots of `type`: asked through the class, a metaclass may spell a tree or a namespace of its own
class_tree, class_namespace = (type.__dict__[name].__get__ for name in ("__mro__", "__dict__"))


def definition_of(klass: type, name: str) -> tuple[type, object] | None:
    """The class in *klass*'s tree that defines *name*, and the definition itself, or ``None``.

    Walked and read raw, which is the reading the interpreter does for an operator: no attribute access
    on the class, so neither a metaclass nor a descriptor of the class's own gets to answer for it.

    A definition of ``None`` reads as no definition, so a class declaring `__hash__ = None` reports the
    hashable base above it.  Callers that care ask the class about `__hash__` directly, which is the
    cheaper question anyway.
    """
    for base in class_tree(klass):
        found = class_namespace(base).get(name)
        if found is not None:
            return base, found
    return None
