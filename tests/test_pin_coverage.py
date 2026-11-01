"""Every view a caller can hold has a pin for each member that changes the type.

Two gates ask about types and they ask different things. `test_typing_completeness.py` asks whether a
checker can *name* a type for each exported symbol, and `test_typing.py` pins that the name is the right
one. A symbol with a named but wrong type passes the first and, until something calls it, is not reached
by the second.

Not every method. Most return `Self`, and a pin on those answers nothing while costing maintenance
forever. The ones worth holding hand back something else, because a pivot returning the wrong view is
silent: the call runs and everything after it is read as a value it is not.

Three things make the set the observable one rather than every declaration:

* the views are resolved from the `assert_that` ladder and closed over what those views return, so a
  protocol nothing hands back is not asked for a pin nothing could write
* a member is taken from the protocol that declares it after MRO resolution, so a base declaration
  every child overrides is not required, and one inherited by seven views is asked for one pin
* a return that is a `TypeVar` is the subject's own type, which a pin necessarily spells concretely, so
  those are matched on the member alone
* a return naming the owner under its own parameters is `Self` by another spelling, which is how the
  capability facade writes it: it stands in for the builder and cannot use `Self`. `_CapableAssertion[_U]`
  from a `_CapableAssertion[_U | None]` receiver is not that, and is asked for a pin

Matched on the member *and* the view it claims, read out of the `assert_type` calls themselves. A member
name alone lets a new pivot ride on the pin for an existing one, and a text search for it matches a
comment.

Every overload return counts, rung by rung. `satisfies`, `is_not_none` and `is_instance_of` each carry
one per view they narrow to, and a rung is an independent mapping from the narrowed type onto the view:
changing one is invisible to a pin on any other.

Rungs returning one view are told apart by what they narrow on, since `satisfies(TypeIs[int])` and
`satisfies(TypeIs[float])` both hand back `_NumericAssertion` and one pin must not answer for both. The
ladders keep that in different places: `satisfies` in a `TypeIs[...]` argument, `is_instance_of` in a
`type[...]` one or in how many classes it is given, `is_not_none`, `eventually` and the pivots of a claimed
value in the protocol `self` is annotated with. A rung keyed on a type variable alone is the catch-all, and
a pin is its witness only where no named rung of the same view takes what the pin narrows on.

A rung with no portable pin is recorded in `_UNPINNABLE` with what refuses it: the badge promises zero
suppressions, so there is nowhere to put a difference between checkers but there.
"""

from __future__ import annotations

import ast
import builtins
import functools
import pathlib
import re
import sys

import pytest

from assertpy import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SURFACE = _ROOT / "assertpy" / "_engine" / "_typing.py"
_FACADE = _ROOT / "assertpy" / "_engine" / "_capable_typing.py"
_LADDER = _ROOT / "assertpy" / "assertpy.py"
_PINS = _ROOT / "tests" / "test_typing.py"
_UNCHANGED = frozenset({"Self", "None"})
_UNPINNABLE = {
    # no expression produces its receiver: a nullable capable value resolves to the object fallback,
    # measured, so `_CapableAssertion[_U | None]` is a `self` nothing hands back
    ("_CapableAssertion", "is_not_none", "_CapableAssertion", "*|None"),
    # keyed on text or bytes, which have overloads above the umbrella, so no value it claims reaches them
    ("_CapableAssertion", "decoded_as", "AssertionBuilder", ""),
    ("_CapableAssertion", "extracting_group", "AssertionBuilder", ""),
    ("_CapableAssertion", "matches_with_groups", "AssertionBuilder", ""),
    # the fallback for a bare `type` is ty's alone: mypy takes the first rung as `Never`, the others as `Unknown`
    ("_CapableAssertion", "raises", "_ExpectedRaiseAssertion[Any, BaseException]", ""),
    ("_InvokedAssertion", "error_of", "_InvokedAssertion[BaseException]", ""),
    # `not_` on every view, held by `test_negated_protocols.py` instead: it derives the pairs from the
    # reachable closure, so a view added later is covered without a pin being remembered for it
    ("_ArrayAssertion", "not_", "_NegatedArrayAssertion", "<the subject's own type>"),
    ("_BoolAssertion", "not_", "_NegatedBoolAssertion", "<the subject's own type>"),
    ("_BytesAssertion", "not_", "_NegatedBytesAssertion", "<the subject's own type>"),
    ("_CallableAssertion", "not_", "_NegatedCallableAssertion", "<the subject's own type>"),
    ("_CompletedAssertion", "not_", "_NegatedCompletedAssertion", "<the subject's own type>"),
    ("_ExpectedCompletionAssertion", "not_", "_NegatedExpectedCompletionAssertion", "<the subject's own type>"),
    ("_ExpectedRaiseAssertion", "not_", "_NegatedExpectedRaiseAssertion", "<the subject's own type>"),
    ("_ExpectedWarningAssertion", "not_", "_NegatedExpectedWarningAssertion", "<the subject's own type>"),
    ("_ComplexAssertion", "not_", "_NegatedComplexAssertion", "<the subject's own type>"),
    ("_CoreAssertion", "not_", "_NegatedCoreAssertion", "<the subject's own type>"),
    ("_DateAssertion", "not_", "_NegatedDateAssertion", "<the subject's own type>"),
    ("_DateTimeAssertion", "not_", "_NegatedDateTimeAssertion", "<the subject's own type>"),
    ("_DictAssertion", "not_", "_NegatedDictAssertion", "<the subject's own type>"),
    ("_FrameAssertion", "not_", "_NegatedFrameAssertion", "<the subject's own type>"),
    ("_InvokedAssertion", "not_", "_NegatedInvokedAssertion", "<the subject's own type>"),
    ("_IterableAssertion", "not_", "_NegatedIterableAssertion", "<the subject's own type>"),
    ("_ListAssertion", "not_", "_NegatedListAssertion", "<the subject's own type>"),
    ("_NumericAssertion", "not_", "_NegatedNumericAssertion", "<the subject's own type>"),
    ("_ObjectAssertion", "not_", "_NegatedObjectAssertion", "<the subject's own type>"),
    ("_PathAssertion", "not_", "_NegatedPathAssertion", "<the subject's own type>"),
    ("_StringAssertion", "not_", "_NegatedStringAssertion", "<the subject's own type>"),
    ("_TextAssertion", "not_", "_NegatedTextAssertion", "<the subject's own type>"),
    ("_WarnedAssertion", "not_", "_NegatedWarnedAssertion", "<the subject's own type>"),
}
"""Rungs no pin can claim, each with what refuses it written above."""
_THE_SUBJECT = "<the subject's own type>"
_CLASSES = "<{} classes>"
_UNREAD = "<unread>"
_NAME = re.compile(r"_[A-Za-z][A-Za-z0-9_]*")


def _parsed(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _view(annotation: str, typevars: frozenset[str] = frozenset()) -> str:
    """The claim a return makes, with its parameters kept when they say something.

    `_NumericAssertion[int]` and `_NumericAssertion[float]` are two claims and must not collapse into
    one. `_ListAssertion[_E]` and `_ListAssertion[Any]` are one, so a parameter that is a `TypeVar` or
    `Any` is dropped. The last dotted segment, since a pin spells `pathlib.Path` where the declaration
    imported `Path`.
    """
    base, _, parameters = annotation.strip().partition("[")
    base = base.rsplit(".", 1)[-1]
    inside = parameters.rstrip("]").strip()
    if not inside or inside == "Any" or any(name in typevars for name in _NAME.findall(inside)):
        return base
    return f"{base}[{', '.join(part.strip().rsplit('.', 1)[-1] for part in inside.split(','))}]"


def _inside(annotation: str, opener: str) -> str:
    """What sits between the brackets of `opener[...]`, brackets inside it included."""
    inside = annotation.partition(opener)[2]
    if not inside:
        return ""
    depth, end = 0, 0
    for end, character in enumerate(inside):  # noqa: B007 - the index is the result
        depth += (character == "[") - (character == "]")
        if depth < 0:
            break
    return inside[:end]


def _flattened(written: str) -> str:
    """Module prefixes dropped and whitespace removed, the way both sides are compared."""
    return "".join(re.sub(r"[A-Za-z_][A-Za-z0-9_]*[.]", "", written).split())


def _narrowed_to(annotation: str, typevars: frozenset[str]) -> str:
    """What a rung narrows to, with type variables wildcarded so the declaration and a pin meet.

    Four shapes because the ladders keep it in four places: a `TypeIs[...]` argument, a `type[...]` one, the
    number of classes where a rung takes two or three, and the protocol `self` is annotated with, whatever its
    name.  A rung whose narrowing this cannot read carries an empty one, which any pin answers.
    """
    if annotation.count("type[") > 1:
        return _CLASSES.format(annotation.count("type["))
    inside = next((found for opener in ("TypeIs[", "type[") if (found := _inside(annotation, opener))), "")
    keyed = _NAME.match(annotation)
    if not inside and keyed is not None and annotation.startswith("[", keyed.end()):
        inside = _inside(annotation, f"{keyed.group()}[").removesuffix(" | None")
    if not inside:
        return ""
    written = inside
    for name in sorted(set(_NAME.findall(written)), key=len, reverse=True):
        if name in typevars:
            written = written.replace(name, "*")
    return _flattened(written)


def _predicates() -> dict[str, str]:
    """The `_is_*` helpers in the pin file, mapped to what each narrows to."""
    return {
        node.name: _narrowed_to(ast.unparse(node.returns), frozenset())
        for node in ast.walk(_parsed(_PINS))
        if isinstance(node, ast.FunctionDef) and node.returns is not None and "TypeIs[" in ast.unparse(node.returns)
    }


def _protocols() -> dict[str, ast.ClassDef]:
    """The views, and the two a pivot hands back that are declared elsewhere.

    `AssertionBuilder` is what a capability-keyed `satisfies` returns and `_CapableAssertion` is what
    `assert_that` returns for a value it recognises without naming, so both are reachable and neither
    lives in `_typing.py`. Their bases are the runtime mixins, which declare no views and are left out.
    """
    found = {node.name: node for node in ast.walk(_parsed(_SURFACE)) if isinstance(node, ast.ClassDef)}
    for path, wanted in ((_LADDER, "AssertionBuilder"), (_FACADE, "_CapableAssertion")):
        found.update(
            {
                node.name: node
                for node in ast.walk(_parsed(path))
                if isinstance(node, ast.ClassDef) and node.name == wanted
            }
        )
    return found


def _typevars() -> set[str]:
    """From all three files, since the facade declares its own and its returns are read here."""
    return {
        node.targets[0].id
        for path in (_SURFACE, _FACADE, _LADDER)
        for node in ast.walk(_parsed(path))
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "TypeVar"
    }


def _itself(owner: str, protocols: dict[str, ast.ClassDef]) -> set[str]:
    """How a protocol spells "the same view again", which is `Self` for everything that can say it.

    The facade and the builder cannot: one stands in for the other. Only the owner under its own
    parameters counts, so a rung narrowing `_CapableAssertion[_U | None]` to `_CapableAssertion[_U]`
    stays a pivot.
    """
    node = protocols.get(owner)
    if node is None:
        return {owner}
    own = [
        parameter
        for base in node.bases
        for parameter in _inside(ast.unparse(base), "Protocol[").split(",")
        + _inside(ast.unparse(base), "Generic[").split(",")
        if parameter.strip()
    ]
    return {owner, _flattened(f"{owner}[{','.join(parameter.strip() for parameter in own)}]")}


def _members(
    name: str, protocols: dict[str, ast.ClassDef], seen: frozenset[str] = frozenset()
) -> dict[str, tuple[str, list[str]]]:
    """Member to its owner and every overload's return, bases first so a child shadows what it overrides.

    The bases last to first, so that of two declaring one member the earlier wins, as it does for a caller.
    """
    if name in seen or name not in protocols:
        return {}
    node = protocols[name]
    found: dict[str, tuple[str, list[str]]] = {}
    for base in reversed(_NAME.findall(", ".join(ast.unparse(base) for base in node.bases))):
        found.update(_members(base, protocols, seen | {name}))
    declared: dict[str, list[tuple[str, str]]] = {}
    for body in node.body:
        if (
            isinstance(body, ast.FunctionDef)
            and body.returns is not None
            and (not body.name.startswith("_") or body.name == "not_")
        ):
            arguments = [
                ast.unparse(argument.annotation)
                for argument in (*body.args.posonlyargs, *body.args.args)
                if argument.annotation is not None
            ]
            narrows = " ".join(arguments)
            declared.setdefault(body.name, []).append((ast.unparse(body.returns), narrows))
    found.update({member: (name, returns) for member, returns in declared.items()})
    return found


def _views_a_caller_can_hold(protocols: dict[str, ast.ClassDef]) -> set[str]:
    """The ladder's own returns, then everything those views hand back, to a fixed point."""
    held = {
        name
        for node in ast.walk(_parsed(_LADDER))
        if isinstance(node, ast.FunctionDef) and node.name == "assert_that" and node.returns is not None
        for name in _NAME.findall(ast.unparse(node.returns))
        if name in protocols
    }
    frontier = set(held)
    while frontier:
        reached = {
            name
            for view in frontier
            for _, returns in _members(view, protocols).values()
            for returned, _narrows in returns
            for name in _NAME.findall(returned)
            if name in protocols and name not in held
        }
        held |= reached
        frontier = reached
    return held


def _rungs() -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Owner and member to every rung that changes the type: what it hands back and what it narrows on."""
    protocols = _protocols()
    typevars = frozenset(_typevars())
    found: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for view in _views_a_caller_can_hold(protocols):
        for member, (owner, returns) in _members(view, protocols).items():
            changing = [
                (
                    _THE_SUBJECT if returned.strip() in typevars else _view(returned, typevars),
                    _narrowed_to(narrows, typevars),
                )
                for returned, narrows in returns
                if returned not in _UNCHANGED and _flattened(returned) not in _itself(owner, protocols)
            ]
            if changing:
                found[owner, member] = changing
    return found


def _required() -> dict[tuple[str, str], set[tuple[str, str]]]:
    """Owner and member to what each rung hands back and what it narrows on, if anything."""
    claims = {key: set(rungs) for key, rungs in _rungs().items()}
    # a narrowing only earns its place where two rungs would otherwise be one requirement
    return {
        key: {
            (claim, narrowed if sum(1 for other, _ in rungs if other == claim) > 1 else "") for claim, narrowed in rungs
        }
        for key, rungs in claims.items()
    }


_SUBJECTS = {
    "Dict": "_DictAssertion",
    "List": "_IterableAssertion",
    "Set": "_IterableAssertion",
    "Tuple": "_IterableAssertion",
    "Lambda": "_CallableAssertion",
    "str": "_StringAssertion",
    "bool": "_BoolAssertion",
    "int": "_NumericAssertion",
    "float": "_NumericAssertion",
    "complex": "_ComplexAssertion",
    "bytes": "_BytesAssertion",
    # written as a call rather than a literal, keyed by what is called
    "object": "_ObjectAssertion",
    "bytearray": "_BytesAssertion",
    "frozenset": "_IterableAssertion",
    "set": "_IterableAssertion",
    "Path": "_PathAssertion",
    "date": "_DateAssertion",
    "datetime": "_DateTimeAssertion",
    # the stand-ins the pin file defines for a value the umbrella claims
    "_Countable": "_CapableAssertion",
    "_CallableResponse": "_CapableAssertion",
    "_FakeResponse": "_CapableAssertion",
    "_Rowish": "_CapableAssertion",
}
"""What `assert_that(<this>)` hands back, for the literal forms the pins are written with.

Only enough to tell the three `satisfies` ladders apart, which is where one pin covered three owners.
A receiver this cannot read counts for every owner, which is the permissive direction: it can leave a
rung unrequired, never require one that does not exist.
"""


def _chain(expression: ast.expr) -> list[str] | None:
    """The members reached, outermost last, or `None` if the chain does not start at `assert_that`."""
    steps: list[str] = []
    node = expression
    while True:
        if isinstance(node, ast.Call):
            if getattr(node.func, "id", None) == "assert_that":
                return steps[::-1]
            node = node.func
        elif isinstance(node, ast.Attribute):
            steps.append(node.attr)
            node = node.value
        else:
            return None


def _starting_view(expression: ast.expr) -> str | None:
    """What `assert_that(<this>)` hands back, read off the subject it was given.

    A literal by its kind, a call by what it calls, a `cast` by the shape it names: `_FrameShape` is what
    the frame view is keyed on, and the two are one rename apart.
    """
    for node in ast.walk(expression):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_that" and node.args):
            continue
        given = node.args[0]
        if isinstance(given, ast.Constant):
            return _SUBJECTS.get(type(given.value).__name__)
        if isinstance(given, ast.Call):
            called = getattr(given.func, "id", None) or getattr(given.func, "attr", None) or ""
            if called == "cast" and given.args:
                named = ast.literal_eval(given.args[0]) if isinstance(given.args[0], ast.Constant) else ""
                return named.replace("Shape", "Assertion") if named.endswith("Shape") else None
            return _SUBJECTS.get(called)
        return _SUBJECTS.get(type(given).__name__)
    return None


def _receiver_view(expression: ast.expr, protocols: dict[str, ast.ClassDef]) -> str | None:
    """The view the outermost member is reached on, followed step by step down the chain.

    `assert_that([...]).extracting(...).check()` reaches `check` on the list view, not on the iterable
    one it started from, and pinning the twin of the wrong view is exactly what this file is about.
    """
    view = _starting_view(expression)
    steps = _chain(expression)
    if view is None or steps is None:
        return None
    for step in steps[:-1]:
        _, returns = _members(view, protocols).get(step, (None, []))
        moved = {_view(returned).split("[", 1)[0] for returned, _narrows in returns}
        moved = {name for name in moved if name in protocols}
        if len(moved) != 1:
            return None
        view = moved.pop()
    return view


def _pin_narrowing(expression: ast.expr, member: str, predicates: dict[str, str]) -> str:
    """What this pin narrows on, taken from wherever the member keeps it.

    `satisfies` from the helper it is given, `is_instance_of` and the exception family from the class, or from
    how many classes where there are several, and everything else from the `cast` the subject was written as.
    A pin with none answers only a rung that has nothing to be told apart from.

    Only what the pin file itself establishes is read.  A name bound by assignment could be a tuple of classes
    or an alias of a mapping, and the cast a chain started from says nothing of the value after a pivot, so
    each of those is unread, which answers no rung that is told apart from another.
    """
    if member == "satisfies":
        given = expression.args[0] if isinstance(expression, ast.Call) and expression.args else None
        return predicates.get(getattr(given, "id", ""), "")
    several = _several_classes(expression, member)
    if several:
        return several
    if member in ("is_instance_of", "raises", "caused_by", "has_root_cause", "error_of"):
        given = expression.args[0] if isinstance(expression, ast.Call) and expression.args else None
        if isinstance(given, ast.Call) and getattr(given.func, "id", None) == "cast":
            return _flattened(_inside(ast.literal_eval(given.args[0]), "type["))
        if given is None:
            return ""
        return _flattened(ast.unparse(given)) if _names_a_class(given) else _UNREAD
    receiver = (
        expression.func.value
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
        else None
    )
    subject = _subject(expression)
    if isinstance(subject, ast.Call) and getattr(subject.func, "id", None) == "cast" and subject.args:
        written = ast.literal_eval(subject.args[0])
        reached_at_once = isinstance(receiver, ast.Call) and getattr(receiver.func, "id", None) == "assert_that"
        return _flattened(written.removesuffix(" | None")) if reached_at_once and _spelled_out(written) else _UNREAD
    return ""


@functools.cache
def _established() -> frozenset[str]:
    """The names the pin file did not make up: what it imports, the classes it declares, and the builtin types.

    Less every name it assigns anywhere: a class of one scope and a tuple of another can share a name, and the
    file is not read scope by scope.
    """
    tree = _parsed(_PINS)
    imported = {
        (alias.asname or alias.name).split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    declared = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    assigned = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
    builtin = {name for name, value in vars(builtins).items() if isinstance(value, type)}
    return frozenset((imported | declared | builtin) - assigned)


def _names_a_class(node: ast.expr) -> bool:
    """Whether an argument is a class by its own spelling: a name the file did not assign, or one off a module."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in _established()


def _spelled_out(written: str) -> bool:
    """Whether a type is written in names the file did not assign: an alias reads as nothing a rung is keyed on."""
    roots = {found.split(".", 1)[0] for found in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", written)}
    return roots <= _established() | {"None"}


def _several_classes(expression: ast.expr, member: str) -> str:
    """How many classes a pin hands `is_instance_of` in a tuple, or `is_instance_of_any` one by one, if several.

    A union or a tuple among them lands on the rung that takes any class info, and so may a name the file
    assigned: counted as two classes, `(A, (B, C))` answered for the rung of two that it never reached.
    """
    given = list(expression.args) if isinstance(expression, ast.Call) else []
    if member == "is_instance_of" and given and isinstance(given[0], ast.Tuple):
        given = given[0].elts
    elif member != "is_instance_of_any":
        return ""
    return _CLASSES.format(len(given)) if len(given) > 1 and all(map(_names_a_class, given)) else _UNREAD


def _starts_at_assert_that(expression: ast.expr) -> bool:
    """Whether a chain is one off `assert_that`, or off a name the pin file bound to such a chain."""
    node: ast.AST = expression
    while isinstance(node, (ast.Call, ast.Attribute, ast.Await)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_that":
            return True
        node = node.func if isinstance(node, ast.Call) else node.value
    return isinstance(node, ast.Name) and node.id in _chains_by_name()


@functools.cache
def _chains_by_name() -> frozenset[str]:
    """The names the pin file binds to a chain off `assert_that`, which several pins then go on from."""
    return frozenset(
        target.id
        for node in ast.walk(_parsed(_PINS))
        if isinstance(node, ast.Assign) and _still_a_view(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    )


def _still_a_view(expression: ast.expr) -> bool:
    """Whether a chain off `assert_that` ends on a view: read through `value` or `val` it is the subject."""
    outermost = expression
    while isinstance(outermost, ast.Call):
        outermost = outermost.func
    left = isinstance(outermost, ast.Attribute) and outermost.attr in ("value", "val")
    return _subject(expression) is not None and not left


def _subject(expression: ast.expr) -> ast.expr | None:
    """What the chain's own `assert_that` was given, reached down its receivers: a call in an argument is not it."""
    node: ast.AST = expression
    while True:
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_that":
            return node.args[0] if node.args else None
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, (ast.Attribute, ast.Await)):
            node = node.value
        else:
            return None


def _pinned(protocols: dict[str, ast.ClassDef]) -> set[tuple[str | None, str, str, str]]:
    """What each `assert_type` call pins: the owner it reaches the member on, and the view it claims.

    Only the outermost member of the chain. `assert_type(x.first().value, int)` pins `value`, and says
    nothing about `first` beyond that it exists.
    """
    pins: set[tuple[str | None, str, str, str]] = set()
    predicates = _predicates()
    for node in ast.walk(_parsed(_PINS)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "assert_type" and len(node.args) == 2:
            pins |= _pin(node.args[0], node.args[1], protocols, predicates)
    return pins


def _pin(
    pinned: ast.expr, claimed_as: ast.expr, protocols: dict[str, ast.ClassDef], predicates: dict[str, str]
) -> set[tuple[str | None, str, str, str]]:
    """What one `assert_type` pins, which is nothing where its chain is not one off `assert_that`.

    Off anything else, a member of the same name and shape on a protocol of one's own was a witness of the library's.
    """
    outermost = pinned
    while isinstance(outermost, ast.Call):
        outermost = outermost.func
    if not isinstance(outermost, ast.Attribute) or not _starts_at_assert_that(pinned):
        return set()
    view = _receiver_view(pinned, protocols)
    owner = None if view is None else _members(view, protocols).get(outermost.attr, (None, []))[0]
    claimed = _view(ast.unparse(claimed_as))
    narrowed = _pin_narrowing(pinned, outermost.attr, predicates)
    return {(owner, outermost.attr, claim, narrowed) for claim in (claimed, claimed.split("[", 1)[0], _THE_SUBJECT)}


def _answers(pattern: str, narrowed: str) -> bool:
    """A rung's `*` stands for a type variable, and a pin fills it in with something concrete.

    A rung narrowing on a union is answered by a pin narrowing on any one of its arms: `list[str]` is
    what a caller writes for a rung declared `list[_E] | tuple[_E, ...]`. A rung with nothing to be told
    apart from carries no pattern, and any pin answers it.  A type is never spelled with `<`, which is how a
    count of classes stays out of the reach of a rung that takes one.
    """
    return not pattern or any(
        re.fullmatch(re.escape(arm).replace(r"\*", "[^<]+"), narrowed) for arm in pattern.split("|")
    )


def _reaches(narrowed: str, pinned: str, claim: str, rungs: set[tuple[str, str]]) -> bool:
    """Whether a pin narrowing on *pinned* is a witness of this rung and not of a sibling handing back the same.

    The catch-all rung takes what no named rung does, as the overloads do: a pin on a mapping answers the
    rung keyed on a mapping, and counted for the catch-all too it stood in for a pin nobody wrote.  By
    spelling, which is all there is to read here: a mapping written as `MutableMapping[...]` is taken for the
    catch-all.
    """
    if not _answers(narrowed, pinned):
        return False
    named = [other for other_claim, other in rungs if other_claim == claim and other not in ("", "*")]
    return narrowed != "*" or not any(_answers(other, pinned) for other in named)


def _only_owner_of(
    member: str, claim: str, narrowed: str, required: dict[tuple[str, str], set[tuple[str, str]]]
) -> str | None:
    """The one owner declaring this member, claim and narrowing, or `None` when several do.

    A pin whose receiver could not be read counts only where there is nothing to confuse it with.
    """
    owners = {owner for (owner, name), claims in required.items() if name == member and (claim, narrowed) in claims}
    return owners.pop() if len(owners) == 1 else None


def test_every_type_changing_member_is_pinned() -> None:
    """Named rather than counted, so the failure says which pin to write."""
    pinned = _pinned(_protocols())
    required = _required()
    unpinned = sorted(
        f"{owner}.{member} -> {claim}" + (f" narrowing on {narrowed}" if narrowed else "")
        for (owner, member), claims in required.items()
        for claim, narrowed in claims
        if not any(
            (
                pinned_owner == owner
                or (pinned_owner is None and _only_owner_of(member, claim, narrowed, required) == owner)
            )
            and pinned_member == member
            and pinned_claim == claim
            and _reaches(narrowed, pinned_narrowing, claim, claims)
            for pinned_owner, pinned_member, pinned_claim, pinned_narrowing in pinned
        )
        and not any(
            (recorded_owner, recorded_member, recorded_claim) == (owner, member, claim)
            and _answers(narrowed, recorded_narrowing)
            for recorded_owner, recorded_member, recorded_claim, recorded_narrowing in _UNPINNABLE
        )
    )

    assert_that(unpinned).described_as(
        "members handing back something other than `Self` with no `assert_type` pinning what"
    ).is_empty()


def test_every_type_changing_rung_is_a_requirement_of_its_own() -> None:
    """Two rungs that hand back one view and narrow on one thing are one requirement, and either pin answers it.

    Seven rungs were held by no pin that way, with every test here green: the two and three classes of
    `is_instance_of` and `is_instance_of_any`, and the pivots of a claimed value that is a source of elements.
    A narrowing that cannot be read is empty, so a protocol `self` is keyed on, renamed, did the same once.
    """
    merged = sorted(
        f"{owner}.{member} -> {claim}" + (f" narrowing on {narrowed}" if narrowed else "")
        for (owner, member), rungs in _rungs().items()
        for claim, narrowed in set(rungs)
        if rungs.count((claim, narrowed)) > 1
    )
    assert_that(merged).described_as("rungs of one member that nothing tells apart").is_empty()


def test_a_pin_narrows_on_its_subject_and_not_on_a_cast_elsewhere() -> None:
    """A cast in an argument says nothing of the receiver: read as the narrowing, it answered for a rung unreached."""
    awaited = 'cast("Callable[..., Awaitable[int]]", later)'
    on_the_subject = ast.parse(f"assert_that({awaited}).eventually()", mode="eval").body
    in_an_argument = ast.parse(f"assert_that(count).eventually(timeout=({awaited}, 1.0)[1])", mode="eval").body
    assert_that(_pin_narrowing(on_the_subject, "eventually", {})).is_equal_to("Callable[...,Awaitable[int]]")
    assert_that(_pin_narrowing(in_an_argument, "eventually", {})).is_empty()


@pytest.mark.parametrize(
    ("pin", "narrowing"),
    [
        ('assert_that(cast("Mapping[str, int]", row)).first()', "Mapping[str,int]"),
        # after a pivot the value is another one, and the cast the chain started from says nothing of it
        ('assert_that(cast("Mapping[str, int]", row)).mapped(encode).first()', "<unread>"),
        # an alias the file assigned may be a mapping, so its spelling is no witness of the rung for anything else
        ('assert_that(cast("KeyMap", row)).first()', "<unread>"),
    ],
)
def test_a_pin_reads_its_subject_only_where_the_member_is_reached_on_it(pin: str, narrowing: str) -> None:
    """What a rung is keyed on is the receiver, so a cast is its narrowing only as the receiver's own subject."""
    assert_that(_pin_narrowing(ast.parse(pin, mode="eval").body, "first", {})).is_equal_to(narrowing)


def test_a_member_reached_off_anything_but_assert_that_is_no_pin() -> None:
    """A protocol of one's own with a member of the same name and shape was a witness of the library's rung."""
    claimed = ast.parse("AssertionBuilder[str | int]", mode="eval").body
    foreign = ast.parse('cast("Foreign", anything).is_instance_of((str, int))', mode="eval").body
    assert_that(_pin(foreign, claimed, _protocols(), {})).is_empty()
    off_a_name_never_bound_to_a_chain = ast.parse("rows.is_instance_of((str, int))", mode="eval").body
    assert_that(_pin(off_a_name_never_bound_to_a_chain, claimed, _protocols(), {})).is_empty()
    genuine = ast.parse("assert_that(_Countable()).is_instance_of((str, int))", mode="eval").body
    assert_that(_pin(genuine, claimed, _protocols(), {})).contains(
        ("_CapableAssertion", "is_instance_of", "AssertionBuilder", "<2 classes>")
    )
    assert_that(_chains_by_name()).contains("polled").does_not_contain("rows")
    assert_that(
        _still_a_view(ast.parse("assert_that(len).raises(KeyError).when_called_with()", mode="eval").body)
    ).is_true()
    # the subject read back is whatever it is, and a member of the same name on it is not the library's
    assert_that(_still_a_view(ast.parse('assert_that(cast("Foreign", anything)).value', mode="eval").body)).is_false()
    assert_that(_still_a_view(ast.parse("assert_that(rows).first().val", mode="eval").body)).is_false()


def test_a_name_the_file_assigns_is_not_established(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """A class of one scope and a tuple of another can share a name, so an assigned name is no class anywhere."""
    pins = tmp_path / "pins.py"
    pins.write_text(
        "import decimal\n\n\ndef scope():\n    class classes: ...\n\n\nclass Paid: ...\n\n\nclasses = (Paid, int)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "_PINS", pins)
    established = _established.__wrapped__()
    assert_that(established).contains("Paid", "decimal", "int").does_not_contain("classes")


def test_of_two_bases_declaring_one_member_the_earlier_is_its_owner() -> None:
    """As for a caller: resolved last base first, the later base won and a rung nobody reaches was asked for a pin."""
    source = (
        "class _First:\n    def pivot(self) -> int: ...\n\n\n"
        "class _Second:\n    def pivot(self) -> str: ...\n    def other(self) -> str: ...\n\n\n"
        "class _Both(_First, _Second): ...\n"
    )
    protocols = {node.name: node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ClassDef)}
    members = _members("_Both", protocols)
    assert_that(members["pivot"]).is_equal_to(("_First", [("int", "")]))
    assert_that(members["other"][0]).is_equal_to("_Second")


@pytest.mark.parametrize(
    ("pin", "narrowing"),
    [
        ("assert_that(order).is_instance_of((Paid, Refund))", "<2 classes>"),
        ("assert_that(order).is_instance_of((Paid, Refund, orders.Void))", "<3 classes>"),
        ("assert_that(order).is_instance_of_any(Paid, Refund, Void)", "<3 classes>"),
        ("assert_that(order).is_instance_of((Paid, (Refund, Void)))", "<unread>"),
        ("assert_that(order).is_instance_of_any(Paid, Refund | Void)", "<unread>"),
        ("assert_that(order).is_instance_of_any(Paid)", "<unread>"),
        ("assert_that(order).is_instance_of(Paid)", "Paid"),
        # a name the file assigned may hold a tuple of classes, so it is neither one class nor one of several
        ("assert_that(order).is_instance_of(classes)", "<unread>"),
        ("assert_that(order).is_instance_of_any(classes, Paid)", "<unread>"),
        ("assert_that(order).is_instance_of((classes, Paid))", "<unread>"),
    ],
)
def test_a_pin_on_several_classes_says_how_many(pin: str, narrowing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A union or a tuple among them is no class: it lands on the rung for any class info, and is not counted."""
    monkeypatch.setattr(sys.modules[__name__], "_established", lambda: frozenset({"Paid", "Refund", "Void", "orders"}))
    expression = ast.parse(pin, mode="eval").body
    assert isinstance(expression, ast.Call)
    member = expression.func.attr if isinstance(expression.func, ast.Attribute) else ""
    assert_that(_pin_narrowing(expression, member, {})).is_equal_to(narrowing)


def test_a_catch_all_rung_is_not_reached_by_a_pin_a_named_rung_takes() -> None:
    """A pin on a mapping is a witness of the rung keyed on a mapping, and of that one alone."""
    rungs = {("AssertionBuilder", "Mapping[*,*]"), ("AssertionBuilder", "*"), ("_ListAssertion", "*")}
    assert_that(_reaches("Mapping[*,*]", "Mapping[str,int]", "AssertionBuilder", rungs)).is_true()
    assert_that(_reaches("*", "Mapping[str,int]", "AssertionBuilder", rungs)).is_false()
    assert_that(_reaches("*", "Sequence[int]", "AssertionBuilder", rungs)).is_true()
    assert_that(_reaches("*", "Mapping[str,int]", "_ListAssertion", rungs)).is_true()
    assert_that(_reaches("*", "<2 classes>", "AssertionBuilder", rungs)).is_false()
    assert_that(_reaches("*", _UNREAD, "AssertionBuilder", rungs)).is_false()
    assert_that(_reaches("Mapping[*,*]", _UNREAD, "AssertionBuilder", rungs)).is_false()


def test_no_recorded_rung_became_pinnable() -> None:
    """Fails when somebody writes a pin for a rung recorded as unpinnable, and only then.

    It cannot notice ty growing the ability on its own: that shows up when someone tries the pin again.
    The record names what to try, and the four expressions are one line each.
    """
    pinned = _pinned(_protocols())
    stale = sorted(
        f"{owner}.{member} -> {claim}"
        for owner, member, claim, narrowed in _UNPINNABLE
        if any(
            pin_owner in (owner, None)
            and pin_member == member
            and pin_claim == claim
            and _answers(narrowed, pin_narrowing)
            for pin_owner, pin_member, pin_claim, pin_narrowing in pinned
        )
    )

    assert_that(stale).described_as("rungs recorded as unpinnable that something now pins").is_empty()


def test_there_is_something_on_both_sides() -> None:
    """Empty sets would make the claim above vacuous rather than false."""
    assert_that(_views_a_caller_can_hold(_protocols())).is_not_empty()
    assert_that(_required()).is_not_empty()
    assert_that(_pinned(_protocols())).is_not_empty()
