"""Which assertions a polling chain declares over a value, and which that value's own view declares.

A chain is not a second surface.  It replays the assertions recorded on it until they hold, so for a
concrete value type ``T`` it may declare only what `assert_that(T)` declares, beyond the few names
`_engine/_operations.py` says are no assertion at all, such as `not_`.  The verdict twin may declare
less again: nothing that register says reaches no verdict, the transforms `extracting` and `first`
among them.  Both lists are read from the register rather than written here, because a second list
drifts.

What is compared is the declared surface and nothing more.  All three answer a name nobody declares
through `__getattr__`, which a dynamic assertion such as `has_status` needs, so a name kept off every
declaration still type-checks there as an open call returning the chain or an outcome.
`typing_cases.py` records that as `a-name-that-exists-nowhere-on-a-chain`.

What the rule catches is a leak: `assert_that(text_probe).eventually_sync().is_positive()` type-checks
while the same call off the chain is refused, since a `str` orders and the rung asks only for an
ordering.  Overload resolution has no way to say "only if no earlier rung matched", so every rung whose
receiver a chain satisfies is one the chain reaches.  What that adds is recorded in
`poll_parity_baseline.py` and compared in both directions, so a new leak fails here and a closed one
fails too.

Which chain reaches which rung is not reasoned about here, and the reasoning was wrong twice before it
was measured.  A rung named for a value is not reachable by that value alone: the chain is covariant in
what it polls, so `bool` reaches a rung written for `int` and a `datetime` one written for `date`.  A
value spelled as a union needs a witness per member, since a tuple reaches the tuple rung and not the
list one.  A value named by a bound needs one for what a real value carries as well: a frame that walks
reaches forty-three names its view lacks where the bare bound reaches seven.

Every pair is measured instead, by a checker, over `poll_parity_cases.py`.

Three surfaces are read, not two: `check()` is generated from the same declarations through the same
rungs, so a leak into the chain is a leak into the verdict twin as well, except for the names the
register keeps off a verdict, such as the transforms `extracting` and `first`.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from assertpy import assert_that
from assertpy.assertpy import AssertionBuilder
from tests import typing_harness
from tests.optional import needs
from tests.poll_parity_baseline import DISPATCHES_TO, REACHES, RECORDED, WITNESSED_BY

if TYPE_CHECKING:
    from types import ModuleType

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_VIEWS = _ROOT / "assertpy" / "_engine" / "_typing.py"
_CASES_FILE = _ROOT / "tests" / "poll_parity_cases.py"

_SYNC = ("_SyncPoll", _ROOT / "assertpy" / "_engine" / "_poll_typing.py")
_ASYNC = ("_AsyncPoll", _ROOT / "assertpy" / "_engine" / "_poll_typing.py")
_VERDICT = ("_CheckAnyValue", _ROOT / "assertpy" / "_engine" / "_builder_check_typing.py")
_SURFACES = (_SYNC, _ASYNC, _VERDICT)
_BOUND_OF = {"_Capable": "_CapableT"}
"""An arm written as the bound of a type variable, to the variable the measurement file asks about."""


def _generator() -> ModuleType:
    """The generator module, which owns the register these surfaces were built from."""
    spec = importlib.util.spec_from_file_location(
        "generate_poll_protocols", _ROOT / "scripts" / "generate_poll_protocols.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - the path above is in the tree
        raise RuntimeError("the generator is not where this test expects it")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_GENERATOR = _generator()


def _classes(path: pathlib.Path) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
    }


_KNOWN = _classes(_VIEWS)


def _arms(node: ast.expr) -> list[ast.expr]:
    """The members of a union written with ``|``, or the annotation itself."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _arms(node.left) + _arms(node.right)
    return [node]


def _receivers(annotation: ast.expr, flavour: str) -> list[str]:
    """What a rung's ``self`` is a chain over, split both ways.

    A union is written either way in these files, ``_SyncPoll[A] | _SyncPoll[B]`` and
    ``_SyncPoll[A | B]``, and a checker resolves both, so both are flattened to the same arms.
    """
    found: list[str] = []
    for arm in _arms(annotation):
        if isinstance(arm, ast.Subscript) and isinstance(arm.value, ast.Name) and arm.value.id == flavour:
            written = (ast.unparse(one) for one in _arms(arm.slice))
            found.extend(_BOUND_OF.get(one, one) for one in written)
    return found


def _offered(holder: str, path: pathlib.Path) -> dict[str, set[str]]:
    """``{receiver arm: the names a rung carrying it offers}`` on one surface."""
    found: dict[str, set[str]] = {}
    for item in _classes(path)[holder].body:
        if not isinstance(item, ast.FunctionDef):
            continue
        own = (item.args.posonlyargs or item.args.args)[0]
        if own.annotation is None:
            continue
        for inner in _receivers(own.annotation, flavour=holder):
            found.setdefault(inner, set()).add(item.name)
    return found


def _view_offers(view: str) -> set[str]:
    """Every name a value's own view carries, its bases included."""
    return {
        item.name
        for protocol in _GENERATOR._lineage(view, _KNOWN)
        for item in _KNOWN[protocol].body
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
    }


def _dispatched() -> list[tuple[str, str]]:
    """``(value type, view)`` per concrete value `assert_that()` names, read off its overloads."""
    return [(value, view.split("[")[0]) for value, view in _GENERATOR._dispatch() if view.split("[")[0] in _KNOWN]


def _not_an_assertion() -> set[str]:
    """What the register says is no assertion at all, the only names a chain may add beyond its view."""
    return set(_GENERATOR._SKIP)


def _kept_off_a_verdict() -> set[str]:
    """What the register says reaches no verdict, which the verdict twin may not carry at all."""
    return set(_GENERATOR._SKIP_FOR_A_VERDICT) - _not_an_assertion()


def _added(holder: str, path: pathlib.Path, witness: str) -> set[str]:
    """What the rungs a chain over *witness* reaches put on it that its own view does not carry."""
    offered = _offered(holder, path)
    adds: set[str] = set()
    for arm in REACHES[witness]:
        adds |= offered.get(arm, set())
    return adds - _view_offers(DISPATCHES_TO[witness]) - _not_an_assertion()


def _cases() -> tuple[list[tuple[str, str, ast.Name]], list[str]]:
    """``(the type asked about, the arm, the argument handed on)`` per case, and the cases not in that shape.

    A case is a plain undecorated function with one ordinary annotated parameter and nothing else in its
    signature, whose body is one call of a `_takes_` helper handing that parameter on.  Anything else is
    listed rather than skipped: a skipped case asks nothing, and the grid check cannot tell it from one
    that did.
    """
    takers = _takers()
    cases: list[tuple[str, str, ast.Name]] = []
    malformed: list[str] = []
    for node in ast.parse(_CASES_FILE.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or not node.name.startswith("_case_"):
            continue
        signature = node.args
        parameters = signature.args
        called = node.body[0].value if len(node.body) == 1 and isinstance(node.body[0], ast.Expr) else None
        if (
            isinstance(node, ast.AsyncFunctionDef)
            or node.decorator_list
            or signature.posonlyargs
            or signature.kwonlyargs
            or signature.vararg
            or signature.kwarg
            or len(parameters) != 1
            or parameters[0].annotation is None
            or not isinstance(called, ast.Call)
            or not isinstance(called.func, ast.Name)
            or called.func.id not in takers
            or called.keywords
            or len(called.args) != 1
            or not isinstance(called.args[0], ast.Name)
            or called.args[0].id != parameters[0].arg
        ):
            malformed.append(node.name)
            continue
        arm = takers[called.func.id]
        cases.append((ast.unparse(parameters[0].annotation), _STANDS_FOR.get(arm, arm), called.args[0]))
    return cases, malformed


def _case_pairs() -> set[tuple[str, str]]:
    """``(the type asked about, the arm it was asked against)`` for every case in the measurement file."""
    return {(written, arm) for written, arm, _argument in _cases()[0]}


def _takers() -> dict[str, str]:
    """``{helper name: the receiver arm it stands for}``, read off the helper's own annotation."""
    return {
        node.name: ast.unparse(node.args.args[0].annotation)
        for node in ast.parse(_CASES_FILE.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_takes_") and node.args.args[0].annotation
    }


_STANDS_FOR = {
    "_FrameShaped": "_FrameT_co",
    "_ArrayShaped": "_ArrayT_co",
}
"""The two arms asked about through a class rather than by name, since their bound is a shape."""


def _every_arm() -> set[str]:
    """Every receiver arm any rung carries, across the three surfaces."""
    return {arm for holder, path in _SURFACES for arm in _offered(holder, path)}


_WITNESSES = sorted(RECORDED)


def test_the_walk_found_the_surface() -> None:
    """A walk that found nothing would agree with every claim below it."""
    assert_that(_WITNESSES).described_as("witnesses the record covers").is_length_between(15, 40)
    assert_that(_every_arm()).described_as("receiver arms the rungs carry").is_length_between(20, 60)


def test_every_dispatched_value_has_a_witness() -> None:
    """A new `assert_that()` overload has to be decided about rather than skipped for want of a row."""
    dispatched = {value for value, _view in _dispatched()}
    assert_that(set(WITNESSED_BY)).described_as("values the measurement covers").is_equal_to(dispatched)
    witnesses = {one for found in WITNESSED_BY.values() for one in found}
    assert_that(set(RECORDED)).described_as("witnesses the record covers").is_equal_to(witnesses)
    assert_that(set(REACHES)).described_as("witnesses the measurement covers").is_equal_to(witnesses)
    assert_that(set(DISPATCHES_TO)).described_as("witnesses with a view").is_equal_to(witnesses)


def test_the_view_a_witness_is_handed_is_the_one_its_value_dispatches_to() -> None:
    """Derived from the overloads rather than trusted from the record.

    An overload starting to answer another view would otherwise leave the gate subtracting the old one
    and agreeing with itself.
    """
    handed = {
        witness: view
        for value, view in _dispatched()
        for witness in WITNESSED_BY.get(value, ())
        if value in WITNESSED_BY
    }
    assert_that(DISPATCHES_TO).described_as("the view each witness is handed").is_equal_to(handed)


def test_a_value_spelled_as_a_union_is_witnessed_member_by_member() -> None:
    """One member says nothing about the others: a tuple reaches the tuple rung and not the list one.

    Counted, the check passed over witnesses swapped between spellings.  Read off the measurement
    instead: a witness has to reach the arm it stands for, and every member has to be reached.
    """
    unwitnessed = {}
    for value, witnesses in WITNESSED_BY.items():
        members = {one.strip() for one in value.split("|")} & _every_arm()
        reached = {arm for witness in witnesses for arm in REACHES[witness]}
        if members - reached:
            unwitnessed[value] = sorted(members - reached)
    assert_that(unwitnessed).described_as("members of a spelling no witness reaches").is_equal_to({})


def test_an_arm_read_as_a_variable_is_written_as_that_variables_bound() -> None:
    """The umbrella rung names the bound where it lands where it stood, and the measurement asks the variable."""
    views = (_ROOT / "assertpy" / "_engine" / "_typing.py").read_text(encoding="utf-8")
    for bound, variable in _BOUND_OF.items():
        assert_that(views).contains(f'{variable} = TypeVar("{variable}", bound={bound})')


@pytest.mark.parametrize(("holder", "path"), (_SYNC, _ASYNC), ids=("sync", "async"))
@pytest.mark.parametrize("witness", _WITNESSES)
def test_a_chain_adds_exactly_what_is_recorded(holder: str, path: pathlib.Path, witness: str) -> None:
    """What a chain puts on a value beyond its own view, held to the record in both directions.

    Both chains, and by equality: the two are generated from one set of declarations, so a name on one
    and not the other is a defect in itself.
    """
    leaked = _added(holder, path, witness)
    assert_that(sorted(leaked)).described_as(f"what {holder} over {witness} adds").is_equal_to(
        sorted(RECORDED[witness])
    )


@pytest.mark.parametrize("witness", _WITNESSES)
def test_the_verdict_twin_adds_what_the_chain_does_less_what_reaches_no_verdict(witness: str) -> None:
    """Both directions, as for the chains: the record less what the register keeps off a verdict.

    Checked as a subset, a leak that dropped off the twin while staying on both chains went unnoticed,
    and the module's claim is that the twin declares every chain leak that can reach a verdict.
    """
    expected = RECORDED[witness] - _kept_off_a_verdict()
    added = _added(_VERDICT[0], _VERDICT[1], witness)
    assert_that(sorted(added)).described_as(f"what the verdict twin over {witness} adds").is_equal_to(sorted(expected))


def test_the_verdict_twin_declares_nothing_that_reaches_no_verdict() -> None:
    """Read off the whole class rather than per witness, so a rung no witness reaches is covered too.

    Declarations only: the name still reaches the twin through `__getattr__`, as the module says.
    """
    carried = {item.name for item in _classes(_VERDICT[1])[_VERDICT[0]].body if isinstance(item, ast.FunctionDef)}
    assert_that(sorted(carried & _kept_off_a_verdict())).described_as(
        "on the verdict twin, reaching no verdict"
    ).is_empty()


def test_every_recorded_name_is_one_the_builder_has() -> None:
    """A misspelling would record a leak that does not exist and hide one that does."""
    builder = AssertionBuilder("abc")
    unknown = sorted({name for names in RECORDED.values() for name in names if not hasattr(builder, name)})
    assert_that(unknown).described_as("recorded, and not a name the builder has").is_empty()


def test_every_case_is_one_call_handing_on_its_own_parameter() -> None:
    """Here rather than beside the measurement, which needs pyright and is skipped in most cells."""
    cases, malformed = _cases()
    assert_that(cases).described_as("cases read from the measurement file").is_not_empty()
    assert_that(malformed).described_as("cases that are not one call handing on their own parameter").is_empty()


def test_every_arm_was_measured_for_every_value() -> None:
    """The hole a recorded matrix has: an arm nobody measured contributes nothing and looks fine.

    So the file the measurement runs on carries the whole grid, and this reads it back.
    """
    asked = _case_pairs()
    missing = sorted((witness, arm) for witness in _WITNESSES for arm in _every_arm() if (witness, arm) not in asked)
    assert_that(missing).described_as("pairs the measurement file does not ask about").is_empty()


def test_the_measurement_still_says_what_is_recorded() -> None:
    """Re-derive `REACHES` rather than trust it: it is the one table nothing else here checks.

    Pyright, because the recorded matrix was taken with it and a second dialect would be a second
    answer rather than a check of this one.

    A refusal counts only as `reportArgumentType` on the case's own parameter, handed to the helper.
    Any error on a case's line used to count, so a misspelt argument read as a refused pair and the
    pair was never asked, which is why every other error in the file fails the test instead.
    """
    needs("pyright", delegated_to="the lint job")
    finished = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "--pythonversion", "3.14", str(_CASES_FILE)],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
        env=typing_harness.checker_env(),
    )
    payload = json.loads(finished.stdout[finished.stdout.index("{") :])
    errors = [one for one in payload["generalDiagnostics"] if one["severity"] == "error"]
    refused = {
        (one["range"]["start"]["line"] + 1, one["range"]["start"]["character"])
        for one in errors
        if one.get("rule") == "reportArgumentType"
    }
    cases, malformed = _cases()
    assert_that(malformed).described_as("cases that are not one call handing on their own parameter").is_empty()
    measured: dict[str, set[str]] = {}
    handed = {(argument.lineno, argument.col_offset) for _written, _arm, argument in cases}
    for written, arm, argument in cases:
        if (argument.lineno, argument.col_offset) not in refused:
            measured.setdefault(written, set()).add(arm)
    stray = [
        f"line {one['range']['start']['line'] + 1}: {one.get('rule')}"
        for one in errors
        if one.get("rule") != "reportArgumentType"
        or (one["range"]["start"]["line"] + 1, one["range"]["start"]["character"]) not in handed
    ]
    assert_that(stray).described_as("pyright errors that are not a refused argument").is_empty()
    expected = {witness: set(arms) for witness, arms in REACHES.items()}
    assert_that(measured).described_as("what pyright says each chain reaches").is_equal_to(expected)
