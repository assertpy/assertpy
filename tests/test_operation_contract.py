"""Hold the two proxies to the operations that actually reach a verdict.

`not_` inverts a verdict and `check()` reports one, so an operation that reaches neither means nothing
through either.  Both used to take them: `assert_that(1).not_.check()` failed with "Expected <1> to NOT
satisfy: check()", and `assert_that([1]).check().first()` answered `passed=True` for a pivot that had
asserted nothing at all.  The second is the worse of the two, because it reads as a verdict.

Two halves.  The register in `assertpy/_engine/_operations.py` is re-derived from the source here, so
an operation that stops asserting cannot quietly stay negatable.  And the refusals are exercised, so
the register is not just a list that agrees with itself.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from assertpy import add_extension, assert_that, assert_warn, remove_extension, soft_assertions
from assertpy._engine._operations import (
    ALSO_ASSERTS,
    CONFIGURES,
    DESCRIBES,
    HANDS_THE_SUBJECT_BACK,
    NOT_AN_OPERATION,
    POLLS,
    TRANSFORMS,
    WITHOUT_A_VERDICT,
)

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy"


def _self_calls(method: ast.FunctionDef) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    }


def _bodies() -> tuple[dict[str, ast.FunctionDef], set[str]]:
    """Every method of the classes `AssertionBuilder` is composed of, and the public names among them.

    Only the mixins.  Reading every class in the package puts the matcher API in the same namespace,
    where `equal_to` and `is_positive` exist too, and the last definition walked wins: the collision
    that made the first version of this classify `is_positive` as a describer.
    """
    bodies: dict[str, ast.FunctionDef] = {}
    public: set[str] = set()
    for path in sorted(_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for klass in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            # and the builder's own operations: the two polls live there, and a mixin-only walk called them asserting
            if not klass.name.endswith("Mixin") and klass.name != "AssertionBuilder":
                continue
            for method in (item for item in klass.body if isinstance(item, ast.FunctionDef)):
                bodies[method.name] = method
                if not method.name.startswith("_"):
                    public.add(method.name)
    return bodies, public


def _reaches_a_verdict(name: str, bodies: dict[str, ast.FunctionDef], seen: frozenset[str]) -> bool:
    """Whether *name* can reach `self.error()`, the one failure entry point every assertion goes through.

    Delegation is followed through public names as well as private ones, because an assertion often
    delegates to another: `is_positive()` calls `is_greater_than(0)` and reaches the failure through
    it.  Following only the private helpers read a third of the surface as asserting nothing.
    """
    if name in seen or name not in bodies:
        return False
    calls = _self_calls(bodies[name])
    if "error" in calls:
        return True
    return any(_reaches_a_verdict(call, bodies, seen | {name}) for call in calls)


def _hands_back_another_value(name: str, bodies: dict[str, ast.FunctionDef], seen: frozenset[str]) -> bool:
    """Whether *name* builds its next step around a value other than the one under test.

    Derived rather than judged, and it is the reliable half: a pivot is visible in the call it makes.
    Whether a pivot *also* tests an expectation on the way is not derivable, which is why the register
    names those and this gate refuses anything it has not been told about.
    """
    if name in seen or name not in bodies:
        return False
    for node in ast.walk(bodies[name]):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "builder"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.args
            and ast.unparse(node.args[0]) != "self.val"
        ):
            return True
    return any(_hands_back_another_value(call, bodies, seen | {name}) for call in _self_calls(bodies[name]))


@pytest.fixture(scope="module")
def derived() -> set[str]:
    """The public operations that reach no verdict, read from the source rather than from the register.

    Two signals, because one was not enough.  An operation that never reaches `self.error()` clearly
    reports nothing.  An operation that *pivots* reports nothing either, unless it tests an expectation
    on the way, and reaching the failure path does not tell those apart: `errors()` reaches it only
    through the gate that refuses a subject which is not a group.  Which pivots also assert is named in
    `ALSO_ASSERTS` rather than derived, and `test_every_operation_that_pivots_has_been_decided_about`
    is what stops that register from going stale.
    """
    bodies, public = _bodies()
    return {
        name
        for name in public
        if not _reaches_a_verdict(name, bodies, frozenset())
        or (_hands_back_another_value(name, bodies, frozenset()) and name not in ALSO_ASSERTS)
    }


class TestTheRegisterDescribesTheSurface:
    def test_the_derivation_itself_ran(self, derived):
        # a walk that found nothing would agree with any register, so the counts come first
        _bodies_unused, public = _bodies()
        assert_that(public).described_as("public operations found").is_length_between(120, 200)
        assert_that(derived).described_as("operations reaching no verdict").is_not_empty()

    def test_every_operation_without_a_verdict_is_registered(self, derived):
        assert_that(sorted(derived)).described_as(
            "an operation that asserts nothing and is not in WITHOUT_A_VERDICT would be negatable"
        ).is_equal_to(sorted(set(WITHOUT_A_VERDICT) | NOT_AN_OPERATION))

    def test_no_registered_operation_actually_asserts(self, derived):
        # what would be wrong is a non-pivot in the register that asserts: it has a verdict and is hidden
        bodies, _public = _bodies()
        asserting = [
            name
            for name in set(WITHOUT_A_VERDICT) | NOT_AN_OPERATION
            if _reaches_a_verdict(name, bodies, frozenset())
            and not _hands_back_another_value(name, bodies, frozenset())
        ]
        assert_that(asserting).described_as("registered as reaching no verdict, but it does").is_empty()

    def test_every_operation_that_pivots_has_been_decided_about(self):
        """The gate that would have caught `errors()`, which the first version could not.

        `errors()` hands the leaves of a caught group over as a list and takes no expectation, so once
        a group has been caught there is nothing it can be wrong about: `check().errors()` answered
        `passed=True` for every group and `not_.errors()` failed for every group.  It reached
        `self.error()` all the same, through the gate that refuses a subject which is not a group, and
        "reaches the failure path" cannot tell that apart from a verdict.

        So the derivation is narrowed to the half that is reliable, and the register carries the half
        that is not.  A new pivot lands here until someone says whether it also asserts.
        """
        bodies, public = _bodies()
        pivots = {name for name in public if _hands_back_another_value(name, bodies, frozenset())}
        decided = {name for name, kind in WITHOUT_A_VERDICT.items() if kind == TRANSFORMS} | ALSO_ASSERTS
        assert_that(sorted(pivots)).described_as(
            "an operation that hands back another value and nobody said whether it also asserts"
        ).is_equal_to(sorted(decided))

    def test_every_hybrid_can_be_wrong_about_something(self):
        """The other direction: a name in `ALSO_ASSERTS` that asserts nothing is `errors()` again.

        Read from the arguments rather than from the call graph.  An operation with an expectation to
        test takes it as a parameter, and `errors()` is the one that took none.
        """
        bodies, _public = _bodies()
        # every spelling, not the two in use: `def caused_by(self, *, ex: type)` would read as taking nothing
        without_an_expectation = [
            name
            for name in ALSO_ASSERTS
            if name in bodies
            and not (
                bodies[name].args.args[1:]
                or bodies[name].args.vararg
                or bodies[name].args.kwonlyargs
                or bodies[name].args.kwarg
            )
        ]
        assert_that(without_an_expectation).described_as(
            "registered as also asserting, but it takes nothing to be wrong about"
        ).is_empty()

    def test_each_category_has_members(self):
        # a category nothing uses is a category nobody maintains, and its message rots unread
        for category in (CONFIGURES, TRANSFORMS, DESCRIBES, POLLS):
            members = [name for name, kind in WITHOUT_A_VERDICT.items() if kind == category]
            assert_that(members).described_as(f"operations registered as {category}").is_not_empty()


class TestWhatHandsTheSubjectBack:
    """`HANDS_THE_SUBJECT_BACK` decides whether `assert assert_that(x).<name>` reads a value or a defect.

    Equality both ways, derived rather than listed.  A member missing from it turns working code into a
    dangling report, and anything in it the subject does not decide silences the loudest shape the
    check has.
    """

    def test_it_is_exactly_the_members_that_hand_the_subject_back(self):
        subject = object()
        builder = assert_that(subject)
        read = {
            name
            for name in dir(builder)
            if not name.startswith("_") and not callable(getattr(type(builder), name, None))
        }
        assert_that(read).described_as("members read rather than called").is_not_empty()
        assert_that(sorted(HANDS_THE_SUBJECT_BACK)).is_equal_to(
            sorted(n for n in read if getattr(builder, n) is subject)
        )

    def test_the_rest_is_truthy_whatever_the_subject_is_which_is_why_it_is_reported(self):
        # `logger` is the sharp one: every builder has it, so `assert assert_that(x).logger` is always green
        assert_that(bool(assert_that([]).logger)).described_as("truthy on an empty subject").is_true()
        assert_that(bool(assert_that([1]).logger)).described_as("truthy on a full one").is_true()
        assert_that(assert_that(1).not_).described_as("reading `not_` hands back more builder").not_.is_instance_of(int)


class TestWhatTheProxiesRefuse:
    """The other half: the register is exercised rather than only compared against itself."""

    @pytest.mark.parametrize(
        ("call", "expected"),
        [
            (lambda: assert_that(lambda: None).not_.raises(ValueError), "only sets an expectation"),
            (lambda: assert_that(lambda: None).not_.warns(UserWarning), "only sets an expectation"),
            (lambda: assert_that([1]).not_.first(), "hands back a different value"),
            (lambda: assert_that([1]).not_.mapped(str), "hands back a different value"),
            (lambda: assert_that(1).not_.described_as("x"), "only sets the failure description"),
            (lambda: assert_that(lambda: 1).not_.eventually(), "runs a whole chain"),
        ],
        ids=["configures", "configures-warning", "transforms", "transforms-pivot", "describes", "polls"],
    )
    def test_negating_an_operation_that_reaches_no_verdict_is_refused(self, call, expected):
        with pytest.raises(TypeError, match=expected) as caught:
            call()
        assert_that(str(caught.value)).described_as("the refusal has to say what to do instead").contains("instead")

    @pytest.mark.parametrize(
        ("call", "expected"),
        [
            (lambda: assert_that(lambda: None).check().raises(ValueError), "only sets an expectation"),
            (lambda: assert_that([1]).check().first(), "hands back a different value"),
            (lambda: assert_that(1).check().described_as("x"), "only sets the failure description"),
            (lambda: assert_that(lambda: 1).check().eventually(), "runs a whole chain"),
        ],
        ids=["configures", "transforms", "describes", "polls"],
    )
    def test_asking_for_a_verdict_where_there_is_none_is_refused(self, call, expected):
        # the worse half: `passed=True` reads as an assertion that ran and held, not one that never happened
        with pytest.raises(TypeError, match=expected):
            call()

    def test_the_proxies_refuse_each_other_where_the_order_is_wrong(self):
        with pytest.raises(TypeError, match=r"call check\(\)\.not_ before the assertion"):
            assert_that(1).not_.check()
        with pytest.raises(TypeError, match=r"one check\(\) is enough"):
            assert_that(1).check().check()

    def test_two_negations_are_refused_rather_than_cancelling_or_doubling(self):
        """They used to behave as one, which is neither what a reader expects nor an error.

        Refused rather than treated as the identity: `not_.not_` reads as a puzzle either way, and a
        silent no-op is the shape a generated or copy-pasted chain arrives in.
        """
        with pytest.raises(TypeError, match="two negations cancel"):
            _ = assert_that(1).not_.not_

    def test_what_the_proxies_still_accept(self):
        assert_that(-1).not_.is_positive()
        assert_that(assert_that(1).check().is_positive().passed).is_true()
        assert_that(assert_that(1).check().not_.is_positive().passed).is_false()
        assert_that(assert_that([1, 2]).first().check().is_positive().passed).is_true()
        # the configurer keeps working through the ordinary path, which is why it is refused and not removed
        assert_that(lambda: None).does_not_raise(ValueError).when_called_with()
        assert_that(assert_that(lambda: None).does_not_raise(ValueError).check().when_called_with().passed).is_true()


class TestTheRefusalHoldsInEveryMode:
    """A refusal that only fires in strict mode is a refusal half the suites never see.

    The proxies are reached the same way under `soft_assertions()` and `assert_warn()`, where a failure
    is collected rather than raised.  The refusal is not a failure of the assertion, though: it says the
    call itself is a mistake, so it raises in every mode rather than being collected as a result.
    """

    def test_a_refusal_raises_under_soft_assertions(self):
        with soft_assertions(), pytest.raises(TypeError, match="hands back a different value"):
            assert_that([1]).not_.first()

    def test_a_refusal_raises_under_assert_warn(self):
        with pytest.raises(TypeError, match="hands back a different value"):
            assert_warn([1]).not_.first()

    def test_a_refusal_raises_inside_the_check_proxy_too(self):
        with pytest.raises(TypeError, match="only sets the failure description"):
            assert_that(1).check().not_.described_as("x")

    def test_an_extension_is_negatable_because_it_asserts(self):
        """A registered extension reaches the failure path, so nothing here should stand in its way."""

        def is_five(self):
            if self.val != 5:
                self.error(f"Expected <{self.val}> to be five")
            return self

        add_extension(is_five)
        try:
            assert_that(4).not_.is_five()
            assert_that(assert_that(5).check().is_five().passed).is_true()
        finally:
            remove_extension(is_five)

    def test_an_override_takes_the_name_out_of_the_register(self):
        """The register describes *this library's* operations, and an override replaces one.

        `add_extension(..., override=True)` is documented, and an extension that asserts under a name
        the register calls a pivot has to stay negatable: refusing it would judge somebody else's
        method by what ours used to do.  Both registration paths are read, because a plain function
        lands on the extended builder through the descriptor protocol and a callable object does not.
        """

        def first(self):
            if not self.val:
                self.error("empty")
            return self

        class _Mapped:
            __name__ = "mapped"

            def __call__(self, builder, *args):
                builder.error("nope")
                return builder

        replaced_mapped = _Mapped()
        add_extension(first, override=True)
        add_extension(replaced_mapped, override=True)
        try:
            assert_that([]).not_.first()
            assert_that(assert_that([1]).check().first().passed).is_true()
            assert_that([1]).not_.mapped()
        finally:
            remove_extension(first)
            remove_extension(replaced_mapped)
        with pytest.raises(TypeError, match="hands back a different value"):
            assert_that([1]).not_.first()

    def test_a_callable_override_is_judged_per_builder_rather_than_per_registry(self):
        """The two ways an extension is applied have different lifetimes, and the guard follows them.

        A plain function is set on the extended builder and every instance sees it at once.  A
        non-function callable is grafted per instance at construction, so a builder made before the
        extension was registered keeps the built-in and one made before it was removed keeps the
        override.  Reading a global registry got both backwards, and the first of them then failed with
        `CollectionMixin.mapped() missing 1 required positional argument`, which describes nothing a
        caller did.
        """

        class _Mapped:
            __name__ = "mapped"

            def __call__(self, builder, *args):
                builder.error("nope")
                return builder

        override = _Mapped()
        made_before = assert_that([1])
        add_extension(override, override=True)
        made_during = assert_that([1])
        try:
            with pytest.raises(TypeError, match="hands back a different value"):
                made_before.not_.mapped()
            made_during.not_.mapped()
        finally:
            remove_extension(override)
        made_during.not_.mapped()

    def test_an_override_of_a_proxy_entry_follows_the_same_rule(self):
        """`check` and `not_` are refused as entrances, and an extension over one is not ours to refuse.

        Overriding them is a strange thing to write.  The point is that the rule is one rule: the guard
        judges what the builder holds, and applying it to the register while the proxy entries kept
        judging by name would have left exactly the inconsistency this contract exists to remove.
        """

        def check(self):
            if self.val != 5:
                self.error("not five")
            return self

        add_extension(check, override=True)
        try:
            assert_that(4).not_.check()
        finally:
            remove_extension(check)
        with pytest.raises(TypeError, match=r"call check\(\)\.not_ before the assertion"):
            assert_that(1).not_.check()
