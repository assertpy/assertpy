"""What the package promises, in a form two revisions can be compared by.

The neighbouring guards each answer a different question. `test_public_surface` holds a hand-written
list of exported names and record fields, `test_protocol_parity` holds the typed surface against the
runtime, `test_typing` pins overload resolution. None of them notices a *signature* moving: a parameter
renamed, a default changed, a keyword becoming positional, two positional parameters swapping places,
an overload disappearing. Those break a caller silently, and they are what this module collects.

The collection is derived rather than hand-written, unlike the name list next door, and that is a
deliberate difference. A hand-written list of two hundred and fifty signatures would not be read on
review; a generated snapshot with a reviewable diff is. What keeps it honest is that the snapshot is
committed: changing the package without changing the snapshot fails, and changing the snapshot shows up
in the diff as its own decision.

One thing is deliberately outside: the *value* of an exported constant. The only ones are `__version__`,
which changes every release by design, and the `match` namespace, whose contents are collected in full
under `matchers`. Checking the value there would fail on every version bump and teach everyone to
re-record without reading, which is the failure mode this file exists to avoid.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import enum
import inspect
import pathlib
import types
from typing import Any

import assertpy
import assertpy._engine._capable_typing
import assertpy._engine._typing
import assertpy.assertpy
from assertpy.assertpy import AssertionBuilder
from assertpy.matchers import Matcher

_SIMPLE = (bool, int, float, str, bytes, type(None))
_DESCRIPTORS = (property, staticmethod, classmethod, types.MemberDescriptorType, types.GetSetDescriptorType)


def _value(value: Any, depth: int = 0) -> str:
    """A default value as a stable string, deep enough that two different values look different.

    `[]` and `[1]` reduced to the same text once, which made a changed default invisible, and the whole
    reason defaults are recorded is that `timeout=1` becoming `timeout=None` changes what an existing
    call does.  So containers are walked, enums are named by member, callables by qualified name, and
    only a genuinely opaque object falls back to its type, where the type at least is still compared.
    """
    if isinstance(value, _SIMPLE):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__module__}.{type(value).__qualname__}.{value.name}"
    if isinstance(value, (list, tuple, set, frozenset)) and depth < 3:
        items = [_value(item, depth + 1) for item in value]
        if isinstance(value, (set, frozenset)):
            items = sorted(items)
        return f"{type(value).__name__}[{', '.join(items)}]"
    if isinstance(value, dict) and depth < 3:
        pairs = ", ".join(f"{_value(key, depth + 1)}: {_value(item, depth + 1)}" for key, item in value.items())
        return f"dict[{pairs}]"
    if callable(value):
        module = getattr(value, "__module__", type(value).__module__)
        return f"<callable {module}.{getattr(value, '__qualname__', type(value).__name__)}>"
    return f"<{type(value).__module__}.{type(value).__name__}>"


def _default(parameter: inspect.Parameter) -> str | None:
    return None if parameter.default is inspect.Parameter.empty else _value(parameter.default)


def _parameters(target: Any) -> list[dict[str, Any]]:
    """Each parameter as the things a caller can break on, in the order they are declared."""
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return []
    return [
        {
            "name": name,
            "kind": parameter.kind.name,
            "required": parameter.default is inspect.Parameter.empty
            and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD),
            "default": _default(parameter),
            "annotation": _text(parameter.annotation, inspect.Parameter.empty),
        }
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


def _text(annotation: Any, empty: Any) -> str | None:
    """An annotation as a stable string, or ``None`` when there is none."""
    if annotation is empty:
        return None
    if isinstance(annotation, str):
        return annotation
    return getattr(annotation, "__name__", None) or str(annotation)


def _callable_entry(target: Any) -> dict[str, Any]:
    signature_return = inspect.Signature.empty
    with contextlib.suppress(TypeError, ValueError):
        signature_return = inspect.signature(target).return_annotation
    return {
        "kind": "callable",
        "parameters": _parameters(target),
        "returns": _text(signature_return, inspect.Signature.empty),
    }


def _member_entry(owner: type, name: str) -> dict[str, Any]:
    attribute = inspect.getattr_static(owner, name)
    if isinstance(attribute, property):
        returns = inspect.signature(attribute.fget).return_annotation if attribute.fget else None
        return {"kind": "property", "parameters": [], "returns": _text(returns, inspect.Signature.empty)}
    if isinstance(attribute, (staticmethod, classmethod)):
        return _callable_entry(attribute.__func__) | {"kind": type(attribute).__name__}
    return _callable_entry(attribute)


def _defining_module(exported: type) -> str:
    """Where the call is defined: this class, or whichever base first provides a constructor."""
    for base in exported.__mro__:
        if "__init__" in vars(base) or "__new__" in vars(base):
            return f"{base.__module__}.{base.__qualname__}"
    return "object"  # pragma: no cover - object always provides both


def _class_entry(exported: type) -> dict[str, Any]:
    """A class as its call signature plus what inheritance and construction promise.

    The signature comes from the class rather than from `__init__`, because calling a class may be
    defined by `__new__` or by a metaclass, and a caller writes the call, not the method that implements
    it.  Where the constructor comes from is recorded beside it, and that is not bookkeeping:
    `WarningLoggingAdapter` inherits `__init__` from `logging.LoggerAdapter`, which gained a parameter in
    3.13, so a snapshot that copied it disagreed with itself across the supported Python versions.  The
    comparison uses this to stay quiet about a signature the package does not own, while still reporting
    the day the base itself is swapped.
    """
    return _callable_entry(exported) | {
        "kind": "class",
        "construction": _defining_module(exported),
        "bases": [f"{base.__module__}.{base.__qualname__}" for base in exported.__mro__[1:] if base is not object],
        "fields": _fields(exported),
    }


def collect() -> dict[str, Any]:
    """The whole public surface, sorted so two snapshots differ only where the package does."""
    exported: dict[str, Any] = {}
    for name in sorted(assertpy.__all__):
        value = getattr(assertpy, name)
        if inspect.isclass(value):
            exported[name] = _class_entry(value)
        elif callable(value):
            exported[name] = _callable_entry(value)
        else:
            exported[name] = {"kind": f"{type(value).__module__}.{type(value).__name__}", "parameters": []}

    return {
        "exports": sorted(assertpy.__all__),
        "py_typed": _has_py_typed(),
        "exported": exported,
        "builder": {
            name: _member_entry(AssertionBuilder, name)
            for name in sorted(dir(AssertionBuilder))
            if not name.startswith("_")
        },
        "matchers": {
            name: _callable_entry(getattr(assertpy.match, name))
            for name in sorted(dir(assertpy.match))
            if not name.startswith("_")
        },
        "typed_views": _typed_views(),
        "view_shapes": _view_shapes(),
        "entry_overloads": _entry_overloads(),
        "matcher_protocol": _matcher_protocol(),
        "failure_attributes": _failure_attributes(),
    }


def _view_sources() -> str:
    """Both modules that declare a typed view, read as one.

    `_capable_typing.py` was missing, and the omission was invisible in exactly the way this file exists
    to prevent: narrowing six dict assertions on the umbrella façade produced no line here at all, while
    the same change to `_ObjectAssertion` produced eight. The façade IS the public surface of a value the
    umbrella claims, reached through an `assert_that` overload like any other view.
    """
    return "\n".join(
        pathlib.Path(module.__file__).read_text(encoding="utf-8")
        for module in (assertpy._engine._typing, assertpy._engine._capable_typing)
        if module.__file__ is not None
    )


def _typed_views() -> dict[str, list[str]]:
    """``{protocol: the assertions it offers}``, resolved through its bases.

    Recorded because the rest of this file could not see the commonest typing-breaking change there is.
    A name leaving a view stops a call type-checking while the runtime keeps answering it, and the
    snapshot noticed only when an `assert_that` overload moved: removing `is_alpha` from the string
    view left every section here identical.

    Resolved rather than declared, since a caller sees what a view inherits exactly as they see what it
    declares, and moving a name to a base is not a change to anybody.
    """
    source = _view_sources()
    declared: dict[str, tuple[set[str], list[str]]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or not node.name.endswith("Assertion"):
            continue
        names = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
        bases = []
        for base in node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if isinstance(target, ast.Name) and target.id.endswith("Assertion"):
                bases.append(target.id)
        declared[node.name] = (names, bases)

    def resolved(name: str, seen: frozenset[str]) -> set[str]:
        if name in seen or name not in declared:
            return set()
        names, bases = declared[name]
        return names.union(*(resolved(base, seen | {name}) for base in bases)) if bases else names

    return {name: sorted(resolved(name, frozenset())) for name in sorted(declared)}


def _view_shapes() -> dict[str, str]:
    """``{"View.method": how that view declares itself}``, resolved through bases.

    Names alone missed the other half of the same class: a parameter turning keyword-only breaks every
    caller who passed it positionally, and a pivot handing back a narrower view ends the chain earlier
    than it used to.

    Resolved rather than recorded where the declaration sits, and that distinction is the whole point.
    Keyed by the declaring class, a parameter narrowed by *adding* an override to a subclass produced a
    key that had not existed before, while the base's key stayed as it was, and a comparison over the
    intersection saw nothing.  This file already carries that pattern: `check` and `value` are
    redeclared in every leaf to narrow their type.

    Annotations as written, alias and all.  Recorded because kinds alone left a whole class of typing
    change unseen: narrowing the seven chronological methods from `datetime.date` to `datetime.datetime`
    moved nothing here, and that is exactly the tightening a minor has to name.  The price is that
    renaming an alias reads as a change to every signature that spells it, which is a re-record and a
    line in review rather than a defect.
    """
    source = _view_sources()
    declared: dict[str, tuple[dict[str, str], list[str]]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or not node.name.endswith("Assertion"):
            continue
        rungs: dict[str, list[str]] = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                rungs.setdefault(item.name, []).append(_spelled(item))
        bases = []
        for base in node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if isinstance(target, ast.Name) and target.id.endswith("Assertion"):
                bases.append(target.id)
        declared[node.name] = ({name: " | ".join(forms) for name, forms in rungs.items()}, bases)

    def resolved(name: str, seen: frozenset[str]) -> dict[str, str]:
        if name in seen or name not in declared:
            return {}
        own, bases = declared[name]
        found: dict[str, str] = {}
        for base in bases:
            found.update(resolved(base, seen | {name}))
        found.update(own)  # a view's own declaration wins over what it inherits, as it does at runtime
        return found

    return {
        f"{view}.{method}": shape
        for view in sorted(declared)
        for method, shape in sorted(resolved(view, frozenset()).items())
    }


def _spelled(method: ast.FunctionDef) -> str:
    """One declaration as what it takes and what it hands back.

    The return is here because a pivot is where a view differs from every other view offering the same
    name: `first()` takes no parameters at all, so four views declaring four different results recorded
    one identical empty string between them.

    A bare `self` is dropped and an ANNOTATED one is kept, because a restricted receiver is what decides
    whether the call is allowed at all.  Dropping it recorded a narrowing as no change: six dict
    assertions gained `self: _CapableAssertion[_Keyed]` and every line here stayed identical.
    """
    arguments = method.args
    parameters = ", ".join(
        [f"{_typed(argument)}/" for argument in arguments.posonlyargs if _carries(argument)]
        + [_typed(argument) for argument in arguments.args if _carries(argument)]
        + ([f"*{_typed(arguments.vararg)}"] if arguments.vararg else [])
        + [f"*{_typed(argument)}" for argument in arguments.kwonlyargs]
        + ([f"**{_typed(arguments.kwarg)}"] if arguments.kwarg else [])
    )
    return f"({parameters}) -> {ast.unparse(method.returns) if method.returns else '?'}"


def _carries(argument: ast.arg) -> bool:
    """Whether a parameter says something a caller can be refused by, which a bare `self` does not."""
    return argument.arg != "self" or argument.annotation is not None


def _typed(argument: ast.arg) -> str:
    return f"{argument.arg}: {ast.unparse(argument.annotation)}" if argument.annotation else argument.arg


def _overload_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The names `typing.overload` was actually imported under in this module.

    Guessing by suffix accepted `@custom_overload` and rejected `from typing import overload as ov`,
    which is two errors in opposite directions.  The imports say it exactly.
    """
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("typing", "typing_extensions"):
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "overload"}
        if isinstance(node, ast.Import):
            modules |= {
                alias.asname or alias.name for alias in node.names if alias.name in ("typing", "typing_extensions")
            }
    return names, modules


def _is_overload(decorator: ast.expr, names: set[str], modules: set[str]) -> bool:
    """Only the real thing: `@overload`, its import alias, or `<known module alias>.overload`.

    A bare `endswith` accepted `@custom_overload`, and accepting any `X.overload` would accept a
    decorator from some other library that happens to have a method of that name.
    """
    if isinstance(decorator, ast.Name):
        return decorator.id in names
    return (
        isinstance(decorator, ast.Attribute)
        and decorator.attr == "overload"
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id in modules
    )


def _entry_overloads() -> list[str]:
    """The `assert_that` overloads as text, in declaration order.

    Order carries meaning: where two overloads both match, the first wins, so a reshuffle changes which
    protocol a caller gets while every declaration survives.  Hence a list compared as a sequence.

    The runtime knows nothing about any of it - it sees one implementation where a checker sees fourteen.
    `test_typing` pins the resolution of chosen calls, a different question: it would stay green if an
    overload nobody wrote an `assert_type` for disappeared.
    """
    tree = ast.parse(pathlib.Path(assertpy.assertpy.__file__).read_text(encoding="utf-8"))
    names, modules = _overload_names(tree)
    # from `tree.body`, not `ast.walk`: the latter has no documented order, and order is what this is compared by
    declared = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "assert_that"
        and any(_is_overload(decorator, names, modules) for decorator in node.decorator_list)
    ]
    return [_signature_text(node) for node in sorted(declared, key=lambda node: node.lineno)]


def _signature_text(node: ast.FunctionDef) -> str:
    """The whole declared signature, not only the plain arguments.

    Positional-only, keyword-only, `*args` and `**kwargs` each change what a call may look like, and the
    first version of this collected `node.args.args` alone, which ignored every one of them.
    """
    arguments = node.args
    positional = arguments.posonlyargs + arguments.args
    # defaults line up with the tail of the positional arguments, which is how the grammar defines them
    padding: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    positional_defaults = padding + list(arguments.defaults)
    parts = [
        _argument_text(argument, default)
        for argument, default in zip(arguments.posonlyargs, positional_defaults, strict=False)
    ]
    if arguments.posonlyargs:
        parts.append("/")
    parts += [
        _argument_text(argument, default)
        for argument, default in zip(arguments.args, positional_defaults[len(arguments.posonlyargs) :], strict=False)
    ]
    if arguments.vararg:
        parts.append(f"*{_argument_text(arguments.vararg, None)}")
    elif arguments.kwonlyargs:
        parts.append("*")
    parts += [
        _argument_text(argument, default)
        for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=False)
    ]
    if arguments.kwarg:
        parts.append(f"**{_argument_text(arguments.kwarg, None)}")
    returns = ast.unparse(node.returns) if node.returns else "?"
    return f"({', '.join(parts)}) -> {returns}"


def _argument_text(argument: ast.arg, default: ast.expr | None) -> str:
    """One argument as declared, defaults included.

    Without the default, `description: str` gaining `= ""`, or `= ""` becoming `= None`, moved nothing in
    the snapshot while changing what an existing call does.
    """
    annotation = ast.unparse(argument.annotation) if argument.annotation else "?"
    return f"{argument.arg}: {annotation}" + (f" = {ast.unparse(default)}" if default is not None else "")


def _matcher_protocol() -> dict[str, Any]:
    """What a custom matcher must provide, with signatures rather than names alone.

    Names were not enough twice over: they were first repeated from a constant in this file, which made
    the check tautological, and then read without signatures, so `matches(self, value)` losing its
    argument would have passed.  The MRO is walked, because a protocol may inherit a member, and
    annotation-only members are recorded too, since a protocol may require an attribute rather than a
    method.
    """
    members: dict[str, Any] = {}
    for base in reversed(Matcher.__mro__):
        members.update(
            {name: _member_entry(Matcher, name) for name in vars(base) if not name.startswith("_")},
        )
        for name, annotation in getattr(base, "__annotations__", {}).items():
            # assigned, not `setdefault`: walking base to derived means the derived one has to win
            if not name.startswith("_"):
                members[name] = {"kind": "annotation", "annotation": _text(annotation, None)}
    return dict(sorted(members.items()))


def _fields(record: type) -> list[str]:
    """Field names for a dataclass or a NamedTuple, in declaration order, empty for anything else."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(getattr(record, "_fields", []))


def _failure_attributes() -> dict[str, str]:
    """What a caller can read off a failure, each with what kind of member it is.

    Names alone let a property become a plain constant, or a read-only descriptor become a writable
    attribute, without a word from the gate.  The kind is recorded beside the name so those show up.

    Two sources.  The class side walks the MRO, because a property or a slot inherited from a base is as
    readable as one declared here and `vars()` on the leaf class sees neither.  The instance side raises
    three shapes of failure, because `trace` is filled only by polling and `failures` only by a soft
    block.

    What the standard library puts on every exception is left out: `args` and its neighbours move with
    the Python version rather than with this package, and a gate reporting them reports someone else's
    decision as though it were ours.
    """
    inherited = {name for name in dir(BaseException) if not name.startswith("_")}
    members: dict[str, str] = {}
    for base in reversed(assertpy.AssertionFailure.__mro__):
        for name, value in vars(base).items():
            if name.startswith("_") or inspect.isroutine(value) or name in inherited:
                continue
            members[name] = _member_kind(value)
    for name in sorted(_attributes_of_real_failures() - inherited):
        members.setdefault(name, "instance attribute")
    return dict(sorted(members.items()))


def _member_kind(value: object) -> str:
    if isinstance(value, property):
        return "property"
    if isinstance(value, _DESCRIPTORS):
        return type(value).__name__
    if hasattr(type(value), "__get__") or hasattr(type(value), "__set__"):
        return f"descriptor {type(value).__module__}.{type(value).__qualname__}"
    return f"class attribute ({type(value).__name__})"


def _attributes_of_real_failures() -> set[str]:
    return set().union(*(_attributes_of(raise_it) for raise_it in (_plain_failure, _soft_failure, _polling_failure)))


def _attributes_of(raise_it: Any) -> set[str]:
    try:
        raise_it()
    except assertpy.AssertionFailure as failure:
        return {name for name in vars(failure) if not name.startswith("_")}
    raise AssertionError("the probe did not fail")  # pragma: no cover - each probe always fails


def _plain_failure() -> None:
    assertpy.assert_that(1).is_equal_to(2)


def _soft_failure() -> None:
    with assertpy.soft_assertions():
        assertpy.assert_that(1).is_equal_to(2)


def _polling_failure() -> None:
    assertpy.assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)


def _has_py_typed() -> bool:
    """Whether the marker is in the tree.

    Whether it reaches the wheel is a different question, answered by the consumer run that installs the
    built artifact into a clean environment.  Asking it here would mean building the package inside the
    suite.
    """
    return (pathlib.Path(assertpy.__file__).parent / "py.typed").exists()
