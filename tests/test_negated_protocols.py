"""The negation twins, held to the rule they exist for rather than to a list of names.

`.not_` gives a view where positive narrowing is unavailable, and one assertion on it hands the positive
view back: `NegatedBuilder` inverts one assertion and returns the builder it wrapped.  One type used to
describe both states, and every route patched separately opened its neighbour, so these check the rule
across the whole reachable surface instead of case by case.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from assertpy import assert_that
from assertpy._engine._operations import (
    CONFIGURES,
    DESCRIBES,
    NOT_AN_OPERATION,
    POLLS,
    TRANSFORMS,
    WITHOUT_A_VERDICT,
)
from tests.test_capable_protocol import _formatted, _generator

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_VIEWS = _ROOT / "assertpy" / "_engine" / "_typing.py"
_TWINS = _ROOT / "assertpy" / "_engine" / "_negated_typing.py"
_ENTRY = _ROOT / "assertpy" / "assertpy.py"
_UMBRELLA = _ROOT / "assertpy" / "_engine" / "_capable_typing.py"

_NOT_AN_ASSERTION = set(NOT_AN_OPERATION) | set(WITHOUT_A_VERDICT)
"""What a negated view must not carry: `check`, `value`, the transforms, configurers, describers, polls."""


def _classes(path: pathlib.Path) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
    }


_POSITIVE = _classes(_VIEWS)
_NEGATED = _classes(_TWINS)
_UMBRELLA_CLASSES = _classes(_UMBRELLA)
_FACADE = "_CapableAssertion"
"""The surface a value no overload names by type is handed, which lives in its own module.

A gate reading only `_typing.py` called the whole class closed while the facade's twin still inherited
the facade, so `not_.described_as("x")` type-checked and `NegatedBuilder` refused it.
"""


def _bases(node: ast.ClassDef) -> list[str]:
    found = []
    for base in node.bases:
        target = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(target, ast.Name) and target.id in _POSITIVE:
            found.append(target.id)
    return found


def _lineage(name: str, seen: list[str] | None = None) -> list[str]:
    seen = [] if seen is None else seen
    if name in seen or name not in _POSITIVE:
        return seen
    seen.append(name)
    for base in _bases(_POSITIVE[name]):
        _lineage(base, seen)
    return seen


def _entry_views() -> list[str]:
    """What `assert_that` hands back, read from its overloads rather than from a list kept here."""
    tree = ast.parse(_ENTRY.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "assert_that" and node.returns is not None:
            name = ast.unparse(node.returns).split("[")[0]
            if name in _POSITIVE and name not in found:
                found.append(name)
    return found


def _reachable() -> set[str]:
    """Every view a chain can end on: the entry views and the closure of what their members return."""
    found, pending = set(_entry_views()), list(_entry_views())
    while pending:
        for protocol in _lineage(pending.pop()):
            for node in ast.walk(_POSITIVE[protocol]):
                if not isinstance(node, ast.FunctionDef) or node.returns is None:
                    continue
                for word in re.findall(r"_\w*Assertion", ast.unparse(node.returns)):
                    if word in _POSITIVE and word not in found:
                        found.add(word)
                        pending.append(word)
    return found


def _members(node: ast.ClassDef) -> dict[str, list[ast.FunctionDef]]:
    found: dict[str, list[ast.FunctionDef]] = {}
    for item in node.body:
        if isinstance(item, ast.FunctionDef):
            found.setdefault(item.name, []).append(item)
    return found


def _arguments(node: ast.FunctionDef) -> str:
    """Everything after `self`: names, annotations, order, kind and whether a default is there."""
    args = node.args
    parts = [f"pos:{arg.arg}:{ast.unparse(arg.annotation) if arg.annotation else '?'}" for arg in args.posonlyargs]
    offset = len(args.args) - 1 - len(args.defaults)
    for index, arg in enumerate(args.args[1:]):
        default = "=" if index >= offset else ""
        parts.append(f"arg:{arg.arg}:{ast.unparse(arg.annotation) if arg.annotation else '?'}{default}")
    if args.vararg:
        parts.append(f"var:{args.vararg.arg}:{ast.unparse(args.vararg.annotation) if args.vararg.annotation else '?'}")
    for arg, given in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        parts.append(f"kw:{arg.arg}:{ast.unparse(arg.annotation) if arg.annotation else '?'}{'=' if given else ''}")
    if args.kwarg:
        parts.append(f"kwargs:{args.kwarg.arg}")
    return ", ".join(parts)


class _Substituted(ast.NodeTransformer):
    """Rewrite the type parameters a base was reached by into the arguments it was given."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.expr:
        written = self.mapping.get(node.id)
        return ast.parse(written, mode="eval").body if written else node


def _parameters(node: ast.ClassDef) -> str | None:
    for base in node.bases:
        rendered = ast.unparse(base)
        if rendered.startswith("Protocol["):
            return rendered[len("Protocol[") : -1]
    return None


def _bound(name: str, known: dict[str, ast.ClassDef] | None = None) -> list[tuple[str, dict[str, str]]]:
    """*name* and every protocol above it, each with the arguments the path down to it gave.

    `_TextAssertion` inherits `_RepeatableAssertion[str]`, so its `contains_in_order` takes `str` and
    not a free `_E`.  Read without the substitution this file compared the twin against a signature
    nobody has, and `not_.contains_in_order(1)` was accepted where the positive method refuses it.
    """
    known = _POSITIVE if known is None else known
    found: list[tuple[str, dict[str, str]]] = []
    pending: list[tuple[str, dict[str, str]]] = [(name, {})]
    while pending:
        protocol, mapping = pending.pop(0)
        if protocol not in known or any(protocol == one for one, _ in found):
            continue
        found.append((protocol, mapping))
        for base in known[protocol].bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if not isinstance(target, ast.Name) or target.id not in known:
                continue
            asked = _parameters(known[target.id])
            if not isinstance(base, ast.Subscript) or asked is None:
                pending.append((target.id, {}))
                continue
            given = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
            written = [
                ast.unparse(_Substituted(mapping).visit(ast.parse(ast.unparse(one), mode="eval").body)) for one in given
            ]
            pending.append((target.id, dict(zip([one.strip() for one in asked.split(",")], written, strict=True))))
    return found


def _effective(item: ast.FunctionDef, mapping: dict[str, str]) -> ast.FunctionDef:
    """The declaration as the view carrying it reads, rather than as its owner wrote it."""
    copied = ast.parse(ast.unparse(item)).body[0]
    assert isinstance(copied, ast.FunctionDef)
    return _Substituted(mapping).visit(copied)


def _receivers(found: list[ast.FunctionDef]) -> set[str | None]:
    """What each rung restricts its receiver to, read on the positive view's own names."""
    seen: set[str | None] = set()
    for item in found:
        own = (item.args.posonlyargs or item.args.args)[0]
        seen.add(None if own.annotation is None else ast.unparse(own.annotation).replace("_Negated", "_"))
    return seen


def _restriction_lost(positive: dict[str, list[ast.FunctionDef]], twin: dict[str, list[ast.FunctionDef]]) -> list[str]:
    """The names where the twin takes a receiver the positive method refuses.

    Argument preservation alone reads nothing after `self`, so a generator that dropped every capability
    restriction would pass it while typing `not_.is_positive()` on a value with no ordering.
    """
    loosened = []
    for name, found in twin.items():
        if name not in positive:
            continue
        asked, offered = _receivers(positive[name]), _receivers(found)
        if offered - asked or (None in offered and None not in asked):
            loosened.append(name)
    return sorted(loosened)


_REACHABLE = sorted(_reachable())


def test_the_walk_found_the_surface() -> None:
    """A walk that found little would agree with every claim below it."""
    assert_that(_REACHABLE).described_as("views a chain can end on").is_length_between(10, 40)
    assert_that(_NEGATED).described_as("negation twins").is_not_empty()


@pytest.mark.parametrize("view", _REACHABLE)
def test_every_reachable_view_has_a_twin(view: str) -> None:
    """Entry views are only the starting points, and a pivot or a call reaches the rest.

    A twin set built from the `assert_that` overloads alone left `_InvokedAssertion` behind, where a
    negated `satisfies` typed a caught message as an `int` and returned the string.
    """
    assert_that(_NEGATED).described_as(f"a twin for {view}").contains_key(f"_Negated{view[1:]}")


@pytest.mark.parametrize("view", _REACHABLE)
def test_every_view_reaches_its_own_twin(view: str) -> None:
    """`not_` on a view has to name that view's twin, or the chain lands on the wrong surface."""
    declared = _members(_POSITIVE[view]).get("not_") or []
    assert_that(declared).described_as(f"{view}.not_").is_length(1)
    assert_that(ast.unparse(declared[0].returns)).described_as(f"{view}.not_ returns").starts_with(
        f"_Negated{view[1:]}"
    )


@pytest.mark.parametrize("view", _REACHABLE)
def test_every_twin_hands_the_positive_view_back(view: str) -> None:
    """The whole rule in one check: a negated assertion is one step, not a permanent state.

    The parameters as well as the name.  Read with `starts_with` this passed a twin handing back
    `_IterableAssertion[list[_E]]` from a receiver over `list[_E] | None`, which is the shape the
    polling twins were found narrowing: a negated `is_not_none()` answering with the type it denied.
    """
    twin = _NEGATED[f"_Negated{view[1:]}"]
    parameters = _own_parameters(twin)
    promised = f"{view}[{parameters}]" if parameters else view
    returns = {ast.unparse(item.returns) for item in twin.body if isinstance(item, ast.FunctionDef) and item.returns}
    unexpected = sorted(one for one in returns if one != promised)
    assert_that(unexpected).described_as(f"_Negated{view[1:]} members answering something but {promised}").is_empty()


def _own_parameters(node: ast.ClassDef) -> str:
    """The type variables a protocol is written over, as it writes them."""
    for base in node.bases:
        rendered = ast.unparse(base)
        if rendered.startswith("Protocol["):
            return rendered[len("Protocol[") : -1]
    return ""


@pytest.mark.parametrize("view", _REACHABLE)
def test_every_twin_keeps_the_arguments_the_positive_method_takes(view: str) -> None:
    """The return type changes, the accepted operands do not.

    Keeping one rung of a ladder instead of transforming each would refuse operands the positive method
    takes, and the return type being right would hide it.
    """
    twin = _NEGATED[f"_Negated{view[1:]}"]
    negated = {name: [_arguments(item) for item in found] for name, found in _members(twin).items()}
    positive: dict[str, list[str]] = {}
    owner: dict[str, str] = {}
    for protocol, mapping in _bound(view):
        for name, found in _members(_POSITIVE[protocol]).items():
            if owner.setdefault(name, protocol) != protocol:
                continue
            # a `TypeIs` rung exists to pick the next view, which a negation has none of, and the plain
            # rung under it takes the same predicate: a `TypeIs` callable is a callable
            positive.setdefault(name, []).extend(
                _arguments(_effective(item, mapping)) for item in found if "TypeIs[" not in ast.unparse(item.args)
            )

    lost = {
        name: sorted(set(positive[name]) - set(shapes))
        for name, shapes in negated.items()
        if sorted(set(positive.get(name, [])) - set(shapes))
    }
    assert_that(lost).described_as(f"_Negated{view[1:]} refusing operands {view} accepts").is_equal_to({})


@pytest.mark.parametrize("view", _REACHABLE)
def test_no_twin_carries_what_is_not_an_assertion(view: str) -> None:
    """A negated `check()` or a negated transform means nothing, and the runtime proxy refuses both."""
    twin = _NEGATED[f"_Negated{view[1:]}"]
    carried = set(_members(twin))
    forbidden = sorted(carried & (_NOT_AN_ASSERTION | set(CONFIGURES) | set(DESCRIBES) | set(POLLS) | set(TRANSFORMS)))
    assert_that(forbidden).described_as(f"_Negated{view[1:]} carrying what reaches no verdict").is_empty()


def test_the_facade_reaches_its_own_twin() -> None:
    """The umbrella is a view like any other, and `.not_` on it has to leave the positive surface."""
    declared = _members(_UMBRELLA_CLASSES[_FACADE]).get("not_") or []
    assert_that(declared).described_as(f"{_FACADE}.not_").is_length(1)
    assert_that(ast.unparse(declared[0].returns)).described_as(f"{_FACADE}.not_ returns").starts_with(
        "_NegatedCapableAssertion"
    )


def test_the_facade_twin_inherits_nothing() -> None:
    """Inheriting the facade brought back `described_as`, `__getattr__` and a `Self` that never inverts."""
    twin = _UMBRELLA_CLASSES["_NegatedCapableAssertion"]
    inherited = [ast.unparse(base) for base in twin.bases if _FACADE in ast.unparse(base)]
    assert_that(inherited).described_as("what the facade twin inherits from the facade").is_empty()


def test_the_facade_twin_hands_the_facade_back() -> None:
    twin = _UMBRELLA_CLASSES["_NegatedCapableAssertion"]
    returns = {ast.unparse(item.returns) for item in twin.body if isinstance(item, ast.FunctionDef) and item.returns}
    assert_that(sorted(returns)).described_as("what the facade twin answers").is_equal_to([f"{_FACADE}[_CapableT_co]"])


def test_the_facade_twin_keeps_the_arguments_the_facade_takes() -> None:
    """Same rule as the per-view twins, on the surface `assert_that` hands a value it cannot name."""
    negated = {
        name: {_arguments(item) for item in found}
        for name, found in _members(_UMBRELLA_CLASSES["_NegatedCapableAssertion"]).items()
    }
    lost = {}
    for name, found in _members(_UMBRELLA_CLASSES[_FACADE]).items():
        if name not in negated:
            continue
        wanted = {_arguments(item) for item in found if "TypeIs[" not in ast.unparse(item.args)}
        if wanted - negated[name]:
            lost[name] = sorted(wanted - negated[name])
    assert_that(lost).described_as("the facade twin refusing operands the facade accepts").is_equal_to({})


def test_the_facade_twin_carries_only_assertions() -> None:
    """A negated `check()`, `extracting()` or `described_as()` means nothing, and the proxy refuses each."""
    carried = set(_members(_UMBRELLA_CLASSES["_NegatedCapableAssertion"]))
    forbidden = sorted(carried & (_NOT_AN_ASSERTION | set(CONFIGURES) | set(DESCRIBES) | set(POLLS) | set(TRANSFORMS)))
    assert_that(forbidden).described_as("the facade twin carrying what reaches no verdict").is_empty()


def test_the_facade_twin_kept_every_assertion_the_facade_has() -> None:
    """The other half of the rule above: dropping an assertion would refuse a call that runs."""
    carried = set(_members(_UMBRELLA_CLASSES["_NegatedCapableAssertion"]))
    facade = {name for name in _members(_UMBRELLA_CLASSES[_FACADE]) if not name.startswith("_")}
    missing = sorted(facade - carried - _NOT_AN_ASSERTION)
    assert_that(missing).described_as("assertions the facade twin lost").is_empty()


@pytest.mark.parametrize("view", _REACHABLE)
def test_no_twin_takes_a_receiver_the_view_refuses(view: str) -> None:
    """The other half of argument preservation, which reads nothing before the first operand."""
    positive: dict[str, list[ast.FunctionDef]] = {}
    owner: dict[str, str] = {}
    for protocol, mapping in _bound(view):
        for name, found in _members(_POSITIVE[protocol]).items():
            if owner.setdefault(name, protocol) != protocol:
                continue
            positive.setdefault(name, []).extend(
                _effective(item, mapping) for item in found if "TypeIs[" not in ast.unparse(item.args)
            )
    loosened = _restriction_lost(positive, _members(_NEGATED[f"_Negated{view[1:]}"]))
    assert_that(loosened).described_as(f"_Negated{view[1:]} taking a receiver {view} refuses").is_empty()


@pytest.mark.parametrize("view", _REACHABLE)
def test_no_twin_invents_a_name(view: str) -> None:
    """A blacklist passes anything not on it, and the runtime proxy answers only what the view declares."""
    carried = set(_members(_NEGATED[f"_Negated{view[1:]}"]))
    declared = {name for protocol in _lineage(view) for name in _members(_POSITIVE[protocol])}
    assert_that(sorted(carried - declared)).described_as(f"_Negated{view[1:]} names {view} has not got").is_empty()


def test_the_facade_twin_takes_no_receiver_the_facade_refuses() -> None:
    """The capability restrictions are the reason this surface exists, so a twin cannot drop them."""
    positive = {
        name: [item for item in found if "TypeIs[" not in ast.unparse(item.args)]
        for name, found in _members(_UMBRELLA_CLASSES[_FACADE]).items()
    }
    loosened = _restriction_lost(positive, _members(_UMBRELLA_CLASSES["_NegatedCapableAssertion"]))
    assert_that(loosened).described_as("the facade twin taking a receiver the facade refuses").is_empty()


def test_the_facade_twin_invents_no_name() -> None:
    carried = set(_members(_UMBRELLA_CLASSES["_NegatedCapableAssertion"]))
    declared = set(_members(_UMBRELLA_CLASSES[_FACADE]))
    assert_that(sorted(carried - declared)).described_as("names the facade twin invented").is_empty()


def test_the_substitution_answers_a_hierarchy_written_out_by_hand() -> None:
    """A recorded answer, because the walk above and the generator's are the same algorithm twice.

    Two steps and a diamond: `_Wanted` reaches `_Held` through a base that passes `list[_Y]` on, and
    reaches `_Plain` twice.  A walk that composed the wrong way round would answer `list[_Y]` here.
    """
    written = """
class _Plain(Protocol): ...
class _Held(_Plain, Protocol[_X]): ...
class _Middle(_Held[list[_Y]], _Plain, Protocol[_Y]): ...
class _Wanted(_Middle[str], Protocol): ...
"""
    known = {node.name: node for node in ast.parse(written).body if isinstance(node, ast.ClassDef)}
    assert_that(_bound("_Wanted", known)).described_as("the substitution down each path").is_equal_to(
        [("_Wanted", {}), ("_Middle", {"_Y": "str"}), ("_Held", {"_X": "list[str]"}), ("_Plain", {})]
    )


def test_the_file_is_what_the_generator_writes() -> None:
    """Every test above checks the rule, so a hand edit that keeps it passed them all and a rerun erased it.

    The file as it stands against what the generator writes after ruff, so a formatting-only hand edit
    shows too: formatting both sides would even it out.  Line endings are read as text on both sides,
    so a file differing only in those still passes.
    """
    assert_that(_formatted(_generator().generate_negated(), str(_TWINS))).described_as(
        "the negation twins are out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_TWINS.read_text(encoding="utf-8"))
