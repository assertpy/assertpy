"""Hold the generated polling twins to what the generator produces, and to what the runtime answers.

A polling chain resolves every assertion through `__getattr__`, so before these twins existed a
checker saw `Any` from the first assertion onwards and `eventually_sync().no_such_assertion()` passed
all three.  The twins describe the same surface the value's own view describes, keyed on the probe's
return type.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import itertools
import pathlib
import subprocess
import sys
import warnings
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

from assertpy import assert_that
from assertpy._engine import _builder_check_typing, _poll_typing, _typing
from assertpy._engine._operations import NOT_AN_OPERATION, POLLS, WITHOUT_A_VERDICT
from assertpy.assertpy import AssertionBuilder
from tests.group_compat import ExceptionGroup, needs_groups

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _generator() -> ModuleType:
    """Import the generator, which lives outside the package, only where it is needed.

    Inline rather than at the top on purpose: `scripts/` is not copied into mutmut's mutants tree, and
    a module-level import of it fails at collection, which takes the whole mutation baseline with it.
    Reached from three tests, so the run can deselect those three instead of losing the file.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    import generate_poll_protocols

    return generate_poll_protocols


def _formatted(source: str) -> str:
    for command in (
        ["ruff", "format", "--stdin-filename", _poll_typing.__file__, "-"],
        ["ruff", "check", "--fix", "--quiet", "--stdin-filename", _poll_typing.__file__, "-"],
    ):
        result = subprocess.run(
            [sys.executable, "-m", *command],
            input=source,
            capture_output=True,
            text=True,
            # named rather than left to the locale: a Windows runner is not UTF-8, and ruff refused the bytes
            encoding="utf-8",
            cwd=_ROOT,
            check=False,
        )
        # refuse rather than fall back: `--fix` exits 1 with violations left, so 1 would let rejected output through
        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(
                f"{' '.join(command)} exited {result.returncode}, so this gate would compare the wrong "
                f"thing: {result.stderr}"
            )
        source = result.stdout
    return source


def test_the_generated_twins_match_the_views_they_mirror() -> None:
    produced = _formatted(_generator().generate())
    assert_that(produced).described_as(
        "the polling twins are out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8")))


def test_only_the_exception_an_expectation_names_is_left_uncompared() -> None:
    """A landing view's other parameters are state a chain could mean, so a differing one is a pivot."""
    generator = _generator()
    known = generator._classes(
        ast.parse(
            "class _Held(Protocol[_P_co]):\n"
            "    @property\n"
            "    def value(self) -> _P_co: ...\n"
            "class _Waiting(_Held[_P_co], Protocol[_P_co, _Exc]): ...\n"
            "class _Tagged(_Held[_P_co], Protocol[_P_co, _Tag]): ...\n"
        )
    )
    assert_that(generator._keeps_its_value("_Waiting", ["_P_co", "_Landed"], "_Held", known)).is_true()
    assert_that(generator._keeps_its_value("_Tagged", ["_P_co", "_Tag"], "_Held", known)).is_true()
    assert_that(generator._keeps_its_value("_Tagged", ["_P_co", "_Other"], "_Held", known)).is_false()


def test_the_generated_verdict_twin_matches_the_views_it_mirrors() -> None:
    assert_that(_formatted(_generator().generate_verdict())).described_as(
        "the builder's verdict twin is out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(pathlib.Path(_builder_check_typing.__file__).read_text(encoding="utf-8")))


class TestTheVerdictTwinOfAValueTheBuilderHolds:
    """What `check()` hands back after a pivot, where it used to hand back an untyped proxy."""

    def _declared(self) -> set[str]:
        return _names(pathlib.Path(_builder_check_typing.__file__).read_text(encoding="utf-8"), "_CheckAnyValue")

    def test_it_carries_no_operation_that_reaches_no_verdict(self) -> None:
        assert_that(self._declared() & set(WITHOUT_A_VERDICT)).described_as(
            "an operation that reaches no verdict cannot be asked for one"
        ).is_empty()

    def test_every_assertion_reaching_a_verdict_is_on_it(self) -> None:
        views = _names(pathlib.Path(_typing.__file__).read_text(encoding="utf-8"))
        # `when_called_with()` is absent for the reason the chain's own is: without an expectation the
        # call raises, and the umbrella is reached from the builder, where no expectation has been set.
        # A verdict after one is asked of the expectation view's own twin, which carries it
        skip = NOT_AN_OPERATION | set(WITHOUT_A_VERDICT) | _AFTER_A_CALL | {"when_called_with"}
        missing = {name for name in views - self._declared() - skip if not name.startswith("_")}
        assert_that(missing).described_as("asked of a value but not of a verdict on one").is_empty()

    def test_the_hook_and_the_negation_are_declared(self) -> None:
        assert_that(self._declared()).contains("not_", "__getattr__")

    @pytest.mark.parametrize(
        ("call", "passed"),
        [
            (lambda: assert_that([1, 2]).first().check().is_positive(), True),
            (lambda: assert_that([-1]).first().check().is_positive(), False),
            (lambda: assert_that(["ab"]).first().check().starts_with("a"), True),
            (lambda: assert_that([1]).first().check().not_.is_negative(), True),
        ],
        ids=["numeric-holds", "numeric-fails", "text", "negated"],
    )
    def test_the_runtime_answers_through_it(self, call, passed) -> None:
        assert_that(call().passed).is_equal_to(passed)

    def test_a_dynamic_assertion_still_reaches_the_proxy(self) -> None:
        # the reason the hook is declared, and the reason a typo stays the runtime's to name
        @dataclasses.dataclass
        class Order:
            status: str

        assert_that(assert_that(Order("PAID")).check().has_status("PAID").passed).is_true()
        with pytest.raises(AttributeError, match="has no assertion"):
            assert_that([1]).first().check().is_postive()


def _names(source: str, protocol: str | None = None) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        if not (node.name == protocol if protocol else node.name.endswith("Assertion")):
            continue
        found |= {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    return found


# reached through `when_called_with()` only. It adds these nine to the surface its value type would have:
# the landing declares the six that move the chain, and the three that keep it come off its hook
_AFTER_A_CALL = frozenset(
    {
        "caused_by",
        "contains_error",
        "does_not_contain_error",
        "error_of",
        "errors",
        "has_root_cause",
        "matches_error_tree",
        "raised",
        "returned",
    }
)

# the chain's own accessors, which are not steps replayed on a builder
_THE_CHAIN_ITSELF = frozenset({"within", "every", "ignoring", "val", "close"})


class TestWhatTheTwinsCarry:
    def test_every_assertion_a_view_declares_is_reachable_on_a_chain(self) -> None:
        source = pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8")
        views = _names(pathlib.Path(_typing.__file__).read_text(encoding="utf-8"))
        # `when_called_with()` lives on the state an expectation puts the chain in, which is the only
        # place a rung chosen by `self` can tell "an expectation was set" from the absence of one
        twins = _names(source, "_SyncPoll") | _names(source, "_SyncPollExpecting")
        skip = NOT_AN_OPERATION | _AFTER_A_CALL | {name for name, kind in WITHOUT_A_VERDICT.items() if kind == POLLS}
        missing = {name for name in views - twins - skip if not name.startswith("_")}
        assert_that(missing).described_as("declared for a value but not for a chain over one").is_empty()

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_a_chain_polls_again_only_over_a_callable(self, flavour) -> None:
        """A second poll asks the value the first hands back to be callable, and says so in every rung.

        Left undeclared the hook answered it, and `eventually_sync()` on a chain over a number type
        checked on all four while the run time refused the value.  Declared without a rung open to any
        chain, the refusal is the overload resolution itself.
        """
        source = ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))
        polls = {name for name, kind in WITHOUT_A_VERDICT.items() if kind == POLLS}
        rungs = [
            item
            for node in ast.walk(source)
            if isinstance(node, ast.ClassDef) and node.name == flavour
            for item in node.body
            if isinstance(item, ast.FunctionDef) and item.name in polls
        ]
        assert_that(rungs).described_as(f"the poll rungs {flavour} carries").is_length(4)
        receivers = {ast.unparse(item.args.args[0].annotation or ast.Constant(value=None)) for item in rungs}
        assert_that(sorted(receivers)).described_as("what each poll rung asks its chain to hold").is_equal_to(
            [f"{flavour}[Callable[..., _P]]", f"{flavour}[_Callable]"]
        )

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_a_negated_chain_never_narrows_the_value(self, flavour) -> None:
        """A negated assertion denies what the positive one claims, so it cannot narrow to it.

        Copied from the positive chain, `not_.is_not_none()` handed back a chain over the type without
        `None` while asserting the value *was* `None`, and `not_.is_instance_of(str)` handed back a
        chain over `str` while asserting the value was not one.  Every checker read `.val` as the
        denied type.  Stated here over the whole class rather than per assertion, since the ladders are
        generated and a new one would arrive with the same defect.
        """
        source = ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))
        twin = f"_Negated{flavour[1:]}"
        allowed = {f"{flavour}[_P_co]", f"{twin}[_P_co]", "_P_co", "None"}
        narrowed = [
            f"{item.name} -> {ast.unparse(item.returns)}"
            for node in ast.walk(source)
            if isinstance(node, ast.ClassDef) and node.name == twin
            for item in node.body
            if isinstance(item, ast.FunctionDef)
            and item.returns is not None
            and ast.unparse(item.returns) not in allowed
            and not item.name.startswith("__")
        ]
        assert_that(narrowed).described_as(f"{twin} rungs handing back something other than the chain").is_empty()

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_a_negated_chain_keeps_every_assertion_the_chain_offers(self, flavour) -> None:
        """Collapsing the ladders must cost arguments, not assertions.

        The fix for the narrowing above is to drop the *result* type, never the rung, so the negation
        offers the same names as the chain it negates.  What it drops is what is not an assertion.
        """
        source = pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8")
        chain = _names(source, flavour)
        twin = _names(source, f"_Negated{flavour[1:]}")
        missing = chain - twin - NOT_AN_OPERATION - set(WITHOUT_A_VERDICT) - _THE_CHAIN_ITSELF - {"__getattr__"}
        assert_that(missing).described_as("offered by the chain and lost by its negation").is_empty()

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_a_negated_chain_is_not_a_subclass_of_the_chain(self, flavour) -> None:
        """The twin carries the rungs rather than inheriting them, and the reason is a crash.

        A protocol inheriting the one whose `not_` hands it back overflowed ty's stack, so a reader
        tempted to shorten the generated file by inheriting instead would take the crash with it.
        Checked here rather than left to the gate, where it shows up as a checker dying and not as a
        statement about the shape.
        """
        source = ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))
        twin = f"_Negated{flavour[1:]}"
        bases = [
            ast.unparse(base)
            for node in ast.walk(source)
            if isinstance(node, ast.ClassDef) and node.name == twin
            for base in node.bases
        ]
        assert_that(bases).described_as(f"what {twin} is built from").is_equal_to(["Protocol[_P_co]"])

    @pytest.mark.parametrize("flavour", ["_SyncPoll", "_AsyncPoll"])
    def test_the_knobs_and_the_hook_are_declared(self, flavour) -> None:
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), flavour)
        assert_that(twins).contains("within", "every", "ignoring", "not_", "__getattr__")

    @pytest.mark.parametrize("chain", ["_SyncPoll", "_SyncPollInvoked", "_SyncPollWarned", "_SyncPollCompleted"])
    def test_every_declared_name_is_one_the_replay_can_answer(self, chain) -> None:
        # a chain answers any name off its hook, so parity is about the builder the steps are replayed on
        twins = _names(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"), chain)
        declared = {name for name in twins if not name.startswith("_") and name not in _THE_CHAIN_ITSELF}
        assert_that(sorted(declared - set(dir(AssertionBuilder)))).described_as(
            "promised on a chain and absent from the builder its steps replay on"
        ).is_empty()


class TestWhereAPivotLands:
    """A pivot keeps the chain's type where the view it lands on is one a value could have had."""

    def _returns(self, name: str) -> list[str]:
        found = []
        for node in ast.walk(ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and node.name == "_SyncPoll":
                found = [
                    ast.unparse(item.returns)
                    for item in node.body
                    if isinstance(item, ast.FunctionDef) and item.name == name and item.returns is not None
                ]
        return found

    def test_an_element_pivot_keeps_what_the_landing_view_holds(self) -> None:
        assert_that(self._returns("first")).contains("_SyncPoll[str]", "_SyncPoll[_K]")

    def test_the_call_lands_where_its_expectation_says(self) -> None:
        """Each expectation names its landing, and `when_called_with()` hands that back.

        The landing view adds names to the value it holds, `raised()` and `returned()` among them, so each
        landing declares those rather than leaving them to a hook over the message: a chain over text answered
        them off its own hook and claimed the caught message was whatever went in.  Before this every landing
        was a chain over `Any`.
        """
        tree = ast.parse(pathlib.Path(_poll_typing.__file__).read_text(encoding="utf-8"))
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

        def returns(klass: str, name: str) -> set[str]:
            return {
                ast.unparse(item.returns)
                for item in classes[klass].body
                if isinstance(item, ast.FunctionDef) and item.name == name and item.returns is not None
            }

        for flavour in ("_SyncPoll", "_AsyncPoll"):
            assert_that(returns(f"{flavour}Expecting", "when_called_with")).is_equal_to({"_L_co"})
            expecting = f"{flavour}Expecting[_P_co, {flavour}"
            landed = {name: returns(flavour, name) for name in ("raises", "does_not_raise", "warns", "does_not_warn")}
            assert_that(landed).described_as(flavour).is_equal_to(
                {
                    # several classes, any one of which may be raised, land on no one class
                    "raises": {f"{expecting}Invoked[_Landed]]", f"{expecting}Invoked[BaseException]]"},
                    "does_not_raise": {f"{expecting}Completed[_P]]"},
                    "warns": {f"{expecting}Warned[_P]]"},
                    "does_not_warn": {f"{expecting}Completed[_P]]"},
                }
            )
        assert_that(returns("_SyncPollInvoked", "raised")).is_equal_to({"_SyncPoll[_Exc_co]"})
        assert_that(returns("_SyncPollCompleted", "returned")).is_equal_to({"_SyncPoll[_R_co]"})
        assert_that(returns("_AsyncPollInvoked", "__await__")).is_equal_to(
            {"Generator[Any, None, _InvokedAssertion[_Exc]]"}
        )


def _failing_from_a_lookup(number: int) -> int:
    try:
        raise KeyError("missing")
    except KeyError as exc:
        raise ValueError("bad") from exc


def _doubling(number: int) -> int:
    return number * 2


def _failing_as_a_group(number: int) -> int:
    raise ExceptionGroup("two failed", [ValueError("bad"), KeyError("missing")])


def _noisy_doubling(number: int) -> int:
    warnings.warn("old", DeprecationWarning, stacklevel=2)
    return number * 2


class TestTheLandingsHoldWhatTheyDeclare:
    """What a polled call hands back at run time is what its landing's declaration names."""

    @pytest.mark.parametrize(
        ("probed", "call", "held"),
        [
            (_failing_from_a_lookup, lambda chain: chain.raises(ValueError).when_called_with(1).val, str),
            (
                _failing_from_a_lookup,
                lambda chain: chain.raises(ValueError).when_called_with(1).raised().val,
                ValueError,
            ),
            (
                _failing_from_a_lookup,
                lambda chain: chain.raises(ValueError).when_called_with(1).contains("ba").raised().val,
                ValueError,
            ),
            (
                _failing_from_a_lookup,
                lambda chain: chain.raises(ValueError).when_called_with(1).caused_by(KeyError).raised().val,
                KeyError,
            ),
            (
                _failing_from_a_lookup,
                lambda chain: chain.raises(ValueError).when_called_with(1).not_.caused_by(OSError).raised().val,
                ValueError,
            ),
            (_doubling, lambda chain: chain.does_not_raise(ValueError).when_called_with(1).val, type(_doubling)),
            (_doubling, lambda chain: chain.does_not_raise(ValueError).when_called_with(1).returned().val, int),
            (_doubling, lambda chain: chain.does_not_warn(UserWarning).when_called_with(1).returned().val, int),
            (_noisy_doubling, lambda chain: chain.warns(DeprecationWarning).when_called_with(1).val, str),
            (_noisy_doubling, lambda chain: chain.warns(DeprecationWarning).when_called_with(1).returned().val, int),
        ],
        ids=[
            "raises",
            "raised",
            "raised-after-an-assertion",
            "caused-by",
            "negated-caused-by",
            "does-not-raise",
            "returned",
            "does-not-warn-returned",
            "warns",
            "warns-returned",
        ],
    )
    def test_the_value_is_the_declared_type(self, probed, call, held) -> None:
        answer = call(assert_that(lambda: probed).eventually_sync(timeout=0.5, trace=False))
        assert_that(answer).is_instance_of(held)

    @needs_groups
    def test_errors_hands_back_the_members_of_the_group(self) -> None:
        chain = assert_that(lambda: _failing_as_a_group).eventually_sync(timeout=0.5, trace=False)
        members = chain.raises(ExceptionGroup).when_called_with(1).errors().val
        assert_that(members).is_instance_of(list).all_satisfy(lambda member: isinstance(member, BaseException))

    def test_a_probe_that_raises_only_later_lands_the_same(self) -> None:
        """A retried call still lands on the caught exception once it raises."""
        attempts = itertools.chain([_doubling, _doubling], itertools.repeat(_failing_from_a_lookup))
        chain = assert_that(lambda: next(attempts)).eventually_sync(timeout=2, interval=0, trace=False)
        assert_that(chain.raises(ValueError).when_called_with(1).raised().val).is_instance_of(ValueError)

    @pytest.mark.parametrize(
        ("probed", "call", "held"),
        [
            (_failing_from_a_lookup, lambda chain: chain.raises(ValueError).when_called_with(1).raised(), ValueError),
            (_doubling, lambda chain: chain.does_not_raise(ValueError).when_called_with(1).returned(), int),
            (_noisy_doubling, lambda chain: chain.warns(DeprecationWarning).when_called_with(1).returned(), int),
        ],
        ids=["raised", "returned", "warns-returned"],
    )
    def test_the_awaited_value_is_the_declared_type(self, probed, call, held) -> None:
        async def run() -> object:
            return (await call(assert_that(lambda: probed).eventually(timeout=0.5, trace=False))).value

        assert_that(asyncio.run(run())).is_instance_of(held)


class TestTheRuntimeAnswersThroughThem:
    @pytest.mark.parametrize(
        ("probe", "call"),
        [
            (lambda: 7, lambda chain: chain.is_positive()),
            (lambda: "ready", lambda chain: chain.starts_with("re")),
            (lambda: [1, 2], lambda chain: chain.contains(1)),
            (lambda: 7, lambda chain: chain.not_.is_negative()),
            (lambda: [1, 2], lambda chain: chain.within(1).every(0.01).is_length(2)),
        ],
        ids=["numeric", "text", "collection", "negated", "knobs"],
    )
    def test_a_declared_assertion_runs(self, probe, call) -> None:
        call(assert_that(probe).eventually_sync(timeout=0.5, trace=False))

    def test_a_name_no_declaration_lists_is_still_refused_at_run_time(self) -> None:
        """The measured cost of keeping the hook, written as a test rather than only as a comment.

        A dynamic assertion is resolved from the polled value's own attributes, so `has_status("PAID")`
        cannot be declared anywhere and the hook has to answer it.  With the hook there, a checker
        stops naming a typo, and only this is left to name it.
        """
        chain = assert_that(lambda: 7).eventually_sync(timeout=0.2, trace=False)
        with pytest.raises(AttributeError, match="has no assertion"):
            chain.no_such_assertion()

    def test_awaiting_a_chain_hands_back_a_builder_over_the_polled_value(self) -> None:
        async def probe() -> int:
            return 7

        async def run() -> None:
            settled = await assert_that(probe).eventually(timeout=0.5, trace=False).is_positive()
            assert_that(settled).is_instance_of(AssertionBuilder)
            assert_that(settled.val).is_equal_to(7)

        asyncio.run(run())

    def test_a_dynamic_assertion_still_polls(self) -> None:
        class _Order:
            def __init__(self) -> None:
                self.polls = 0

            @property
            def status(self) -> str:
                self.polls += 1
                return "PAID" if self.polls > 1 else "PENDING"

        order = _Order()
        assert_that(lambda: order).eventually_sync(timeout=1, interval=0.01, trace=False).has_status("PAID")
        assert_that(order.polls).is_greater_than(1)
