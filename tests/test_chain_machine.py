"""A state machine over reachable assertion chains, holding every delivery surface to the same answer.

State: the value kind of the current view, whether the next step is negated, the live chain on each
surface (hard, soft, warn, polled hard/soft/warn, async polled), which soft/warn chain is tainted or inert,
and for the function kind the expectation set and what the call captured. Transitions are only the
reachable ones: an assertion applicable to the view (one in ten from any kind, to reach refusals), `not_`,
a pivot, `described_as`, `raises`/`does_not_raise` then `when_called_with` on a function, and the
proxy refusals. Each verdict step is asked on every surface and the answers compared.

Besides agreement between surfaces, a verdict step is held to: `not_` inverting it, the failure record
naming the call, plain Python where its answer is not in doubt, the matcher twin of the assertion, and
the opposite assertion. The one allowed disagreement with a twin is the boundary
`tests/test_matcher_parity.py` documents: `is_subset_of` refuses an argument on an empty subject that
its matcher, being total, answers with the vacuous match. Any other refusal of a matched value fails.
"""

from __future__ import annotations

import asyncio
import copy
from typing import TYPE_CHECKING, Any, NoReturn

from hypothesis import note, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from assertpy import assert_that, assert_warn, match, soft_assertions
from assertpy.exception import _InertBuilder
from tests import chain_model as model

if TYPE_CHECKING:
    from collections.abc import Callable
from tests.chain_surfaces import (
    WARN_LOGGER,
    Answer,
    Step,
    dup,
    key_of,
    parameters_key,
    run_async,
    run_check,
    run_hard,
    run_poll,
    run_soft,
    run_soft_check,
    run_warn,
    run_warn_check,
    same_value,
    shown,
)

FLIP = {"held": "failed", "failed": "held"}
TIMEOUT_HEAD = "Expected condition not met after "
FIELDS = ("message", "actual", "actual_provided", "expected", "diff", "requirement", "hint")


class DivergenceError(AssertionError):
    """Two surfaces, or two spellings, answered differently where the contract says they agree."""


def _differ(what: str, **detail: object) -> NoReturn:
    raise DivergenceError(" | ".join([what, *(f"{name}={shown(value)}" for name, value in detail.items())]))


_LIVE = ("hard", "soft", "warn", "poll", "soft_poll", "warn_poll")
"""The live chain on every surface, which no side probe may change."""


def _state(chain: object) -> dict[str, tuple[object, object]]:
    """Each attribute of *chain*, beside a deep copy of it where it is a container a call could change in place.

    A tuple is held by identity only: the steps a poll replays are one, and a matcher among their arguments,
    copied, would be compared by matching rather than by equality.
    """
    return {
        key: (held, copy.deepcopy(held) if isinstance(held, (list, dict, set)) else None)
        for key, held in getattr(chain, "__dict__", {}).items()
    }


def _moved(before: dict[str, tuple[object, object]], chain: object) -> list[str]:
    """The attributes of *chain* rebound, added, removed or filled in place since *before* was taken."""
    now = getattr(chain, "__dict__", {})
    return sorted(
        key
        for key in before.keys() | now.keys()
        if key not in now
        or key not in before
        or now[key] is not before[key][0]
        or (before[key][1] is not None and now[key] != before[key][1])
    )


@settings(max_examples=200, stateful_step_count=12, deadline=None)
class ChainMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        # a Windows loop holds a loopback socket pair, and one loop per async step ran out of ephemeral ports
        self.loop = asyncio.new_event_loop()

    # the function kind is listed four times: its expectation and call transitions need a head start to be reached
    @initialize(kind=st.sampled_from([*sorted(model.KINDS), "function", "function", "function"]), data=st.data())
    def start(self, kind: str, data: st.DataObject) -> None:
        value = data.draw(model.KINDS[kind], label="subject")
        self.current = value
        self.kind = kind
        self.probe = lambda: value
        self.hard = assert_that(value)
        with soft_assertions():
            self.soft = assert_that(value)
            self.soft_poll = assert_that(self.probe).eventually_sync(timeout=0, interval=0)
        self.warn = assert_warn(value, logger=WARN_LOGGER)
        self.warn_poll = assert_warn(self.probe, logger=WARN_LOGGER).eventually_sync(timeout=0, interval=0)
        self.poll = assert_that(self.probe).eventually_sync(timeout=0, interval=0)
        self.steps: list[Step] = []
        self.poll_passed = False
        self.soft_taint = self.warn_taint = False
        self.soft_inert = self.warn_inert = False
        self.soft_poll_inert = self.warn_poll_inert = False
        self.negate_next = False
        self.expectation: tuple[str, type[BaseException]] | None = None
        self.called: str | None = None
        self.captured_value: object = None

    def _start_async(self) -> Any:
        return assert_that(self.probe).eventually(timeout=0, interval=0)

    @precondition(lambda self: not self.negate_next)
    @rule()
    def negate(self) -> None:
        self.negate_next = True

    @rule(data=st.data())
    def assertion(self, data: st.DataObject) -> None:
        self._assertion(data)

    @rule(data=st.data())
    def assertion_again(self, data: st.DataObject) -> None:
        """A second rule for the same transition, so hypothesis picks verdict steps twice as often."""
        self._assertion(data)

    def _assertion(self, data: st.DataObject) -> None:
        applicable = [op for op in model.OPS if self.kind in op.kinds]
        cross = data.draw(st.integers(0, 9), label="cross") == 0
        op = data.draw(st.sampled_from(model.OPS if cross or not applicable else applicable), label="op")
        args, kwargs = op.args(self.current, data.draw)
        note(f"assertion {op.name}{shown(args)} negated={self.negate_next} on {shown(self.current)}")
        self._verdict_step(op.name, args, kwargs, op=op)

    @precondition(lambda self: self.kind in model.ITERABLE)
    @rule(data=st.data())
    def pivot(self, data: st.DataObject) -> None:
        applicable = [pivot for pivot in model.PIVOTS if self.kind in pivot.kinds]
        pivot = data.draw(st.sampled_from(applicable), label="pivot")
        args, kwargs = pivot.args(self.current, data.draw)
        note(f"pivot {pivot.name}{shown(args)} negated={self.negate_next} on {shown(self.current)}")
        self._refused_through_proxies(pivot.name, args, kwargs)
        if self.negate_next:
            self.negate_next = False
            return
        try:
            expected: object = pivot.oracle(self.current, *args)
            refusal = None
        except model.RefusalError as exc:
            expected, refusal = None, exc.args[0]
        self._transform(pivot.name, args, kwargs, expected, refusal)

    @rule(label=st.sampled_from(["", "lbl", "two words"]))
    def describe(self, label: str) -> None:
        note(f"described_as({label!r}) negated={self.negate_next}")
        self._refused_through_proxies("described_as", (label,), {})
        if self.negate_next:
            self.negate_next = False
            return
        self._transform("described_as", (label,), {}, self.current, None)

    @precondition(lambda self: self.kind == "function" and self.expectation is None)
    @rule(
        method=st.sampled_from(["raises", "does_not_raise"]),
        error=st.sampled_from([ValueError, KeyError, LookupError, Exception, TypeError]),
    )
    def expect(self, method: str, error: type[BaseException]) -> None:
        note(f"{method}({error.__name__}) negated={self.negate_next}")
        self._refused_through_proxies(method, (error,), {})
        if self.negate_next:
            self.negate_next = False
            return
        self._transform(method, (error,), {}, self.current, None)
        self.expectation = (method, error)

    @precondition(lambda self: self.expectation is not None and self.called is None and self.kind == "function")
    @rule(number=st.sampled_from([-2, 0, 3]))
    def call_with(self, number: int) -> None:
        note(f"when_called_with({number}) negated={self.negate_next}")
        self._verdict_step("when_called_with", (number,), {}, op=None)

    @precondition(lambda self: self.expectation is not None and self.called is None and self.kind == "function")
    @rule(number=st.sampled_from([-2, 0, 3]))
    def call_with_again(self, number: int) -> None:
        """Doubled for the same reason as `assertion_again`: reaching a capture takes three transitions."""
        self.call_with(number)

    @precondition(lambda self: self.called is not None)
    @rule()
    def captured(self) -> None:
        name = "raised" if self.called == "raised" else "returned"
        note(f"{name}() negated={self.negate_next}")
        self._refused_through_proxies(name, (), {})
        if self.negate_next:
            self.negate_next = False
            return
        expected = self.captured_value
        self.called = None
        self._transform(name, (), {}, expected, None)

    @rule(which=st.sampled_from(["not_.not_", "not_.check", "check.check", "poll.check", "poll.value"]))
    def proxy_refusal(self, which: str) -> None:
        def reach() -> object:
            match which:
                case "not_.not_":
                    return self.hard.not_.not_
                case "not_.check":
                    return self.hard.not_.check
                case "check.check":
                    return self.hard.check().check
                case "poll.check":
                    return self.poll.check
                case _:
                    return self.poll.value

        try:
            reach()
        except TypeError:
            pass
        else:
            _differ("a proxy misuse was not refused", which=which)
        if self.hard.kind is not None:
            _differ("a refused proxy left the builder in another mode", which=which, kind=self.hard.kind)

    @rule()
    def read_value(self) -> None:
        if not same_value(self.hard.value, self.current):
            _differ("hard .value is not the view", value=self.hard.value, view=self.current)
        for surface, builder, tainted, inert in (
            ("soft", self.soft, self.soft_taint, self.soft_inert),
            ("warn", self.warn, self.warn_taint, self.warn_inert),
        ):
            try:
                read = builder.value
            except TypeError:
                if not (tainted or inert):
                    _differ(f"{surface} .value refused on an untainted chain", view=self.current)
                continue
            if tainted or inert:
                _differ(f"{surface} .value handed back a value after a failure", read=read)
            if not same_value(read, self.current):
                _differ(f"{surface} .value is not the view", read=read, view=self.current)
        try:
            polled = self.poll.val
        except AttributeError:
            if self.poll_passed:
                _differ("polled .val missing after a passing step")
        else:
            if not self.poll_passed:
                _differ("polled .val present before any step passed", read=polled)
            if not same_value(polled, self.current):
                _differ("polled .val is not the view", read=polled, view=self.current)
        for surface, chain, inert in (
            ("soft-poll", self.soft_poll, self.soft_poll_inert),
            ("warn-poll", self.warn_poll, self.warn_poll_inert),
        ):
            if not inert:
                continue
            try:
                read = chain.val
            except TypeError:
                continue
            _differ(f"{surface} .val readable on an inert chain", read=read)

    @invariant()
    def hard_view_is_the_model(self) -> None:
        if not same_value(self.hard.val, self.current):
            _differ("hard .val drifted from the model", val=self.hard.val, view=self.current)

    def teardown(self) -> None:
        self.loop.close()

    def _refused_through_proxies(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """A transform, a configuration or a description has no verdict to invert or to report."""
        for proxy, reach in (("not_", lambda: self.hard.not_), ("check()", lambda: self.hard.check())):
            try:
                getattr(reach(), name)(*args, **kwargs)
            except TypeError:
                continue
            except Exception as exc:
                _differ(f"{proxy}.{name}() raised something other than TypeError", error=type(exc).__name__)
            _differ(f"{proxy}.{name}() was not refused", args=args)

    def _transform(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], expected: object, refusal: str | None
    ) -> None:
        """Apply a verdict-free step on every live surface. All must hand back the same value, or refuse alike."""
        hard = run_hard(self.hard, name, args, kwargs, False)
        answers: dict[str, Answer] = {"hard": hard}
        if not self.soft_inert:
            answers["soft"] = run_soft(self.soft, name, args, kwargs, False)
        if not self.warn_inert:
            answers["warn"] = run_warn(self.warn, name, args, kwargs, False)
        answers["poll"] = run_poll(self.poll, name, args, kwargs, False)
        if not self.soft_poll_inert:
            answers["soft-poll"] = run_soft(self.soft_poll, name, args, kwargs, False)
        if not self.warn_poll_inert:
            answers["warn-poll"] = run_warn(self.warn_poll, name, args, kwargs, False)
        steps: list[Step] = [*self.steps, (name, args, kwargs)]
        awaited = run_async(self.loop, self._start_async, steps)
        if all(step[0] == "described_as" for step in steps):
            # a chain that only describes asserts nothing, and awaiting it is refused as awaiting a bare one is
            if awaited.status != "refused" or awaited.error != "TypeError":
                _differ(f"{name}: an awaited chain of descriptions alone answered {awaited.brief()}")
        else:
            answers["async"] = awaited
        want = "refused" if refusal else "held"
        for surface, answer in answers.items():
            if answer.status != want or (refusal and answer.error != refusal):
                _differ(
                    f"{name}: {surface} answered {answer.brief()}, oracle says {want}",
                    refusal=refusal,
                    view=self.current,
                )
        if refusal:
            return
        direct_type = type(hard.result.val)
        for surface, answer in answers.items():
            try:
                got = answer.result.val
            except AttributeError as exc:
                _differ(f"{name}: {surface} .val unreadable after a passing step", error=str(exc))
            if not same_value(got, expected):
                _differ(f"{name}: {surface} view differs from the oracle", got=got, expected=expected)
            if type(got) is not direct_type:
                _differ(f"{name}: {surface} final type differs from direct", got=type(got), want=direct_type)
        self.hard = hard.result
        if "soft" in answers:
            self.soft = answers["soft"].result
        if "warn" in answers:
            self.warn = answers["warn"].result
        self.poll = answers["poll"].result
        self.poll_passed = True
        if "soft-poll" in answers:
            self.soft_poll = answers["soft-poll"].result
        if "warn-poll" in answers:
            self.warn_poll = answers["warn-poll"].result
        self.steps.append((name, args, kwargs))
        if name != "described_as":
            self.soft_taint = self.warn_taint = False
        if name not in ("described_as", "raises", "does_not_raise"):
            self.current = expected
            self.kind = model.kind_of(expected)
            self.expectation = None
            self.called = None

    def _verdict_step(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], op: model.Op | None) -> None:
        """Ask one verdict on every surface, positive and negated, then advance the live chains by the main one."""
        negated_main = self.negate_next
        self.negate_next = False
        value = self.current
        before = {surface: _state(getattr(self, surface)) for surface in _LIVE}
        positive = run_hard(dup(self.hard), name, args, kwargs, False)
        self._unmoved(name, before)
        negative = run_hard(dup(self.hard), name, args, kwargs, True)
        self._unmoved(name, before)
        self._negation_inverts(name, args, positive, negative)
        # the builder's own object: the model's may be an equal copy, and identity is part of what is asked
        self._matches_python(name, self.hard.val, args, kwargs, positive)
        for negated, reference in ((False, positive), (True, negative)):
            self._describes_the_call(name, args, kwargs, reference, negated)
            for surface, probe in self._probes(name, args, kwargs, negated):
                self._agrees(surface, reference, probe())
                self._unmoved(name, before)
        if name == "when_called_with":
            self._call_matches_the_oracle(args, positive)
        if op is not None:
            self._twin_agrees(op, value, args, kwargs, positive)
            self._unmoved(name, before)
            self._opposite_agrees(op, args, kwargs, positive)
        main = negative if negated_main else positive
        steps: list[Step] = [*self.steps, *((("not_", None, None),) if negated_main else ()), (name, args, kwargs)]
        self._agrees("async", main, run_async(self.loop, self._start_async, steps))
        self._unmoved(name, before)
        self._advance(name, args, kwargs, negated_main, main)

    def _probes(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool
    ) -> list[tuple[str, Callable[[], Answer]]]:
        """Every surface a verdict is asked on besides hard, each a call made only when it is asked."""
        probes: list[tuple[str, Callable[[], Answer]]] = [
            ("check", lambda: run_check(dup(self.hard), name, args, kwargs, negated))
        ]
        if not self.soft_inert:
            probes.append(("soft", lambda: run_soft(dup(self.soft), name, args, kwargs, negated)))
            probes.append(("check", lambda: run_soft_check(dup(self.soft), name, args, kwargs, negated)))
        if not self.warn_inert:
            probes.append(("warn", lambda: run_warn(dup(self.warn), name, args, kwargs, negated)))
            probes.append(("check", lambda: run_warn_check(dup(self.warn), name, args, kwargs, negated)))
        probes.append(("poll", lambda: run_poll(self.poll, name, args, kwargs, negated)))
        if not self.soft_poll_inert:
            probes.append(("soft-poll", lambda: run_soft(self.soft_poll, name, args, kwargs, negated)))
        if not self.warn_poll_inert:
            probes.append(("warn-poll", lambda: run_warn(self.warn_poll, name, args, kwargs, negated)))
        return probes

    def _unmoved(self, name: str, before: dict[str, dict[str, tuple[object, object]]]) -> None:
        """No probe so far changed a live chain: asked after every probe, before another could undo it."""
        for surface, held in before.items():
            moved = _moved(held, getattr(self, surface))
            if moved:
                _differ(f"{name}: a side probe changed the live {surface} builder", attributes=moved)

    def _advance(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], negated: bool, main: Answer) -> None:
        """Apply the main variant to the live chains, and move the model the way the contract says."""
        hybrid = name == "when_called_with"
        live = run_hard(self.hard, name, args, kwargs, negated)
        if live.status != main.status:
            _differ(f"{name}: the same call answered differently twice", first=main.brief(), second=live.brief())
        if live.status == "held" and not hybrid and live.result is not self.hard:
            _differ(f"{name}: an assertion handed back a different builder", got=type(live.result).__name__)
        if not self.soft_inert:
            soft = run_soft(self.soft, name, args, kwargs, negated)
            if soft.status == "failed":
                self.soft_taint = True
                if hybrid and not negated:
                    if not isinstance(soft.result, _InertBuilder):
                        _differ("soft failed call did not go inert", got=type(soft.result).__name__)
                    self.soft_inert = True
            if soft.status in ("held", "failed"):
                self.soft = soft.result
        if not self.warn_inert:
            warn = run_warn(self.warn, name, args, kwargs, negated)
            if warn.status == "failed":
                self.warn_taint = True
                if hybrid and not negated:
                    self.warn_inert = True
            if warn.status in ("held", "failed"):
                self.warn = warn.result
        polled = run_poll(self.poll, name, args, kwargs, negated)
        if polled.status == "held":
            self.poll = polled.result
            self.poll_passed = True
            try:
                polled_value = self.poll.val
            except AttributeError as exc:
                _differ(f"{name}: polled .val unreadable after a passing step", error=str(exc))
            if not hybrid and not same_value(polled_value, self.current):
                _differ(f"{name}: polled .val after a passing step is not the view", got=polled_value)
            if not hybrid and type(polled_value) is not type(live.result.val if live.result else self.current):
                _differ(f"{name}: polled final type differs from direct", got=type(polled_value))
        for surface in ("soft_poll", "warn_poll"):
            inert_flag = f"{surface}_inert"
            if getattr(self, inert_flag):
                continue
            runner = run_soft if surface == "soft_poll" else run_warn
            answer = runner(getattr(self, surface), name, args, kwargs, negated)
            if answer.status == "failed":
                if not isinstance(answer.result, _InertBuilder):
                    _differ(f"{surface}: a timed-out chain did not go inert", got=type(answer.result).__name__)
                setattr(self, inert_flag, True)
            if answer.status in ("held", "failed"):
                setattr(self, surface, answer.result)
        if main.status == "held":
            if negated:
                self.steps.append(("not_", None, None))
            self.steps.append((name, args, kwargs))
        if hybrid and live.status == "held" and not negated:
            self._after_call(args, live.result)
        elif hybrid:
            self.called = None

    def _after_call(self, args: tuple[Any, ...], captured_builder: Any) -> None:
        """Move the model past a call that held: onto the message it raised, or ready to read what it returned."""
        method, _error = self.expectation  # ty: ignore[not-iterable]  # set whenever a call is reachable
        try:
            returned: object = model.call_me(*args)
            raised: BaseException | None = None
        except Exception as exc:
            returned, raised = None, exc
        if method == "raises":
            self.hard = captured_builder
            self.current = str(raised)
            self.kind = "str"
            self.captured_value = raised
            self.called = "raised"
            self.expectation = None
            self.soft_taint = self.warn_taint = False
            for surface in ("soft", "warn"):
                builder = getattr(self, surface)
                if not isinstance(builder, _InertBuilder) and not same_value(builder.val, self.current):
                    _differ(f"{surface}: the captured message differs from direct", got=builder.val, want=self.current)
        else:
            self.captured_value = returned
            self.called = "returned" if raised is None else None

    def _negation_inverts(self, name: str, args: tuple[Any, ...], positive: Answer, negative: Answer) -> None:
        if positive.status == "refused":
            if (negative.status, negative.error, negative.text) != ("refused", positive.error, positive.text):
                _differ(f"{name}: not_ changed a refusal", positive=positive.brief(), negative=negative.brief())
            return
        if positive.status not in FLIP:
            _differ(f"{name}: positive took an illegal shape", positive=positive.brief())
        if negative.status != FLIP[positive.status]:
            _differ(
                f"{name}: not_ did not invert",
                args=args,
                positive=positive.brief(),
                negative=negative.brief(),
                value=self.current,
            )

    def _describes_the_call(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], reference: Answer, negated: bool
    ) -> None:
        """A failure names the operation and the arguments it was called with, bound by the signature."""
        if reference.status != "failed":
            return
        outcome = reference.outcome
        if outcome is None:
            _differ(f"{name}: a failure carries no record", negated=negated)
        asked = outcome.requirement
        if asked is None:
            _differ(f"{name}: a failure names no requirement", negated=negated)
        if (asked.operation, asked.negated) != (name, negated):
            _differ(f"{name}: requirement names another call", got=(asked.operation, asked.negated), negated=negated)
        want = model.bound_parameters(name, args, kwargs)
        if want is not None and parameters_key(asked.parameters) != parameters_key(want):
            _differ(
                f"{name}: requirement parameters are not the call's",
                got=dict(asked.parameters),
                want=want,
                negated=negated,
                value=self.current,
            )

    def _agrees(self, surface: str, reference: Answer, other: Answer) -> None:
        """Another surface's answer against hard's: the same status, and the same record where it delivers one."""
        if other.status != reference.status:
            _differ(f"{surface} answered {other.brief()} where hard answered {reference.brief()}", value=self.current)
        if reference.status == "refused":
            if (other.error, other.text) != (reference.error, reference.text):
                _differ(f"{surface} refused differently", got=(other.error, other.text), want=reference.error)
            return
        if reference.status != "failed":
            return
        want = key_of(reference.outcome)
        got = key_of(other.outcome)
        match surface:
            case "check" | "soft" | "poll" | "async":
                if surface == "soft" and other.count != 1:
                    _differ("soft collected more than one failure for one call", count=other.count)
                if got != want:
                    self._fields_apart(surface, got, want, skip=())
                if surface in ("poll", "async") and not (
                    other.text.startswith(TIMEOUT_HEAD) and other.text.endswith("Last failure: " + reference.text)
                ):
                    _differ(f"{surface} timeout does not quote the failure", got=other.text, want=reference.text)
            case "warn":
                if not other.text.startswith(reference.text):
                    _differ("warn logged another message", got=other.text, want=reference.text)
            case "soft-poll":
                if not (other.text.startswith(TIMEOUT_HEAD) and other.text.endswith("Last failure: " + reference.text)):
                    _differ("soft-poll collected another message", got=other.text, want=reference.text)
                self._fields_apart(surface, got, want, skip=("message",))
            case "warn-poll":
                if not (other.text.startswith(TIMEOUT_HEAD) and ("Last failure: " + reference.text) in other.text):
                    _differ("warn-poll logged another message", got=other.text, want=reference.text)

    def _fields_apart(
        self, surface: str, got: tuple[object, ...] | None, want: tuple[object, ...] | None, skip: tuple[str, ...]
    ) -> None:
        """Name every field of the two failure records that differs, outside the ones skipped."""
        if got is None or want is None:
            _differ(f"{surface} record missing", got=got, want=want)
        apart = [field for field, one, two in zip(FIELDS, got, want, strict=True) if one != two and field not in skip]
        if apart:
            _differ(
                f"{surface} record differs from hard in {apart}",
                got={field: got[FIELDS.index(field)] for field in apart},
                want={field: want[FIELDS.index(field)] for field in apart},
                value=self.current,
            )

    def _matches_python(
        self, name: str, value: object, args: tuple[Any, ...], kwargs: dict[str, Any], positive: Answer
    ) -> None:
        """Hard's verdict against Python's own answer, the one oracle that shares no code with any surface."""
        said = model.python_verdict(name, value, args, kwargs)
        if said is None or positive.status not in FLIP:
            return
        if said != (positive.status == "held"):
            _differ(f"{name} disagrees with Python", python=said, builder=positive.status, value=value, args=args)

    def _call_matches_the_oracle(self, args: tuple[Any, ...], positive: Answer) -> None:
        method, error = self.expectation  # ty: ignore[not-iterable]  # precondition
        try:
            model.call_me(*args)
            raised = None
        except Exception as exc:
            raised = exc
        caught = raised is not None and isinstance(raised, error)
        want = ("held" if caught else "failed") if method == "raises" else ("failed" if caught else "held")
        if positive.status != want:
            _differ(f"when_called_with under {method}({error.__name__})", got=positive.brief(), want=want)

    def _twin_agrees(
        self, op: model.Op, value: object, args: tuple[Any, ...], kwargs: dict[str, Any], positive: Answer
    ) -> None:
        """The assertion against its matcher twin, directly, through `satisfies()` and under `match.not_`.

        A refusal the matcher answers with a match is allowed on an empty subject only, where the match
        is the vacuous one.
        """
        twin = model.twin_of(op, value)
        if twin is None or positive.status not in ("held", "failed", "refused"):
            return
        try:
            matcher = twin(*args, **kwargs)
        except (TypeError, ValueError):
            return
        try:
            said = matcher.matches(value)
        except Exception as exc:
            _differ(f"match twin of {op.name} is not total", error=type(exc).__name__, value=value, args=args)
        if positive.status == "refused":
            if said and not (op.name == "is_subset_of" and model.is_empty_subject(value)):
                _differ(f"{op.name} refused a value its matcher accepts", value=value, args=args)
            return
        if bool(said) != (positive.status == "held"):
            _differ(
                f"{op.name} and its matcher disagree", builder=positive.status, matcher=said, value=value, args=args
            )
        through = run_hard(dup(self.hard), "satisfies", (matcher,), {}, False)
        if through.status != positive.status:
            _differ(f"satisfies(match twin of {op.name}) disagrees", got=through.brief(), want=positive.status)
        inverted = match.not_(matcher).matches(value)
        if bool(inverted) != (positive.status == "failed"):
            _differ(f"match.not_(twin of {op.name}) disagrees with not_", matcher=inverted, builder=positive.status)

    def _opposite_agrees(self, op: model.Op, args: tuple[Any, ...], kwargs: dict[str, Any], positive: Answer) -> None:
        if op.opposite is None or (op.single_only_opposite and len(args) != 1):
            return
        other = run_hard(dup(self.hard), op.opposite, args, kwargs, False)
        if positive.status == "refused" or other.status == "refused":
            if positive.status != other.status:
                _differ(f"{op.name} and {op.opposite} disagree on refusing", one=positive.brief(), two=other.brief())
            return
        if other.status != FLIP.get(positive.status):
            _differ(
                f"{op.name} and {op.opposite} are not opposites",
                args=args,
                one=positive.brief(),
                two=other.brief(),
                value=self.current,
            )


TestChains = ChainMachine.TestCase
