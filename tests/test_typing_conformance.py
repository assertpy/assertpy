"""Hold the typed surface and the runtime to the same signature, parameter by parameter.

`tests/test_protocol_parity.py` asks whether every declared method exists and whether the runtime
*accepts* what a declaration marks required.  That leaves six questions, and each of them is a way for
the two halves to drift while both gates stay green:

* the runtime accepts a parameter no declaration mentions, so a caller cannot pass it without a cast
* a declaration names one the runtime has not got, so the call type-checks and raises
* they disagree about how a parameter may be passed, so a keyword the checker allows is refused
* they disagree about whether it is required, so an omission the checker allows fails at run time
* between them the views refuse a value the runtime accepts, so no caller can write a working call
* a view offers one the runtime never promised, so the call type-checks on a signature that excludes it

The last two are a different kind of blindness from the first four.  Conformance to a protocol is
contravariant in parameters, so a view narrower than the runtime satisfies it however far it narrows,
and no checker has anything to report either way round.

This is the conformance half of the plan, and only its reporting half: it compares and complains and
generates nothing.  What it replaces is the audit that used to be done by hand, once, whenever somebody
remembered to wonder.
"""

from __future__ import annotations

import ast
import collections
import inspect
import pathlib

import pytest

from assertpy import _matcher_impls, assert_that
from assertpy._engine import _typing
from assertpy.assertpy import AssertionBuilder
from tests.test_protocol_parity import _PROTOCOLS, _VALUE_VIEWS, _declarations_of, _members_of

_KINDS = {
    inspect.Parameter.POSITIONAL_ONLY: "positional-only",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional",
    inspect.Parameter.KEYWORD_ONLY: "keyword-only",
    inspect.Parameter.VAR_POSITIONAL: "*args",
    inspect.Parameter.VAR_KEYWORD: "**kwargs",
}


def _declared(method: ast.FunctionDef) -> dict[str, tuple[str, bool]]:
    """``{parameter: (how it may be passed, whether it has a default)}`` for one declaration."""
    arguments = method.args
    positional = arguments.posonlyargs + arguments.args
    padding: list[ast.expr | None] = [None] * (len(positional) - len(arguments.defaults))
    defaults: dict[str, ast.expr | None] = dict(
        zip([argument.arg for argument in positional], padding + list(arguments.defaults), strict=True)
    )
    defaults.update(dict(zip([argument.arg for argument in arguments.kwonlyargs], arguments.kw_defaults, strict=True)))
    found = {}
    for group, kind in (
        (arguments.posonlyargs, "positional-only"),
        (arguments.args, "positional"),
        (arguments.kwonlyargs, "keyword-only"),
    ):
        for argument in group:
            found[argument.arg] = (kind, defaults.get(argument.arg) is not None)
    if arguments.vararg:
        found[arguments.vararg.arg] = ("*args", False)
    if arguments.kwarg:
        found[arguments.kwarg.arg] = ("**kwargs", False)
    return {name: value for name, value in found.items() if name != "self"}


def _concrete_signature(name: str) -> inspect.Signature | None:
    """The runtime method's signature, or ``None`` where there is nothing to read."""
    concrete = inspect.getattr_static(AssertionBuilder, name, None)
    if concrete is None or isinstance(concrete, property):
        return None
    try:
        return inspect.signature(concrete)
    except (TypeError, ValueError):
        return None


def _runtime(name: str) -> dict[str, tuple[str, bool]] | None:
    """The same reading of the concrete method, or ``None`` where there is nothing to compare."""
    signature = _concrete_signature(name)
    if signature is None:
        return None
    return {
        parameter.name: (_KINDS[parameter.kind], parameter.default is not inspect.Parameter.empty)
        for parameter in signature.parameters.values()
        if parameter.name != "self"
    }


def _pairs() -> list[tuple[str, str, dict[str, tuple[str, bool]], dict[str, tuple[str, bool]]]]:
    """Every declaration beside the runtime method it describes.

    An overload set is read as the union of what its rungs accept, since that is what it promises a
    caller.

    A runtime method taking `*args` or `**kwargs` is compared by its head rather than skipped whole.
    Skipping it cost 176 of the 996 pairs, and among the 31 names in them five carry named parameters
    that went unchecked along with the tail: `is_equal_to(other, **kwargs)`, `is_array_equal(expected,
    **options)`, `is_frame_equal(expected, **options)`, `is_array_close_to(expected, *, rtol, atol,
    equal_nan, **options)` and `is_subset_of(*supersets, allow_empty=False)`.  `is_equal_to` is the most
    used method in the library, and its `other` was compared on none of the four axes.

    What the tail buys is one exemption, and only one: a name a view declares and the runtime has not
    got is excused where a tail could really be where it went, which `_absorbed` decides from the
    runtime's own guard rather than from the presence of a tail.  The six keywords `is_equal_to` declares
    (`ignore`, `include`, `tolerance`, `comparators`, `ignore_null`, `strict_types`) exist in no runtime
    signature, since they arrive through `**kwargs`, and reporting them as invented is what a finer skip
    would have done.  Everything else about the head is compared as it is for any other method.
    """
    found = []
    for protocol in sorted(_PROTOCOLS):
        for name, methods in _declarations_of(protocol).items():
            concrete = _runtime(name)
            if concrete is None:
                continue
            promised: dict[str, tuple[str, bool]] = {}
            for method in methods:
                for parameter, value in _declared(method).items():
                    promised.setdefault(parameter, value)
            found.append((protocol, name, promised, concrete))
    return found


def _accepted_keywords() -> dict[str, frozenset[str]]:
    """``{method: the keywords its `**kwargs` really takes}``, read from the runtime's own guard.

    A `**kwargs` is not a promise to accept anything.  Three methods hand theirs to
    `reject_unknown_kwargs(kwargs, <a frozenset>, "<the method>")`, and that call names both halves, so
    the register is read out of the runtime rather than repeated here.
    """
    found: dict[str, frozenset[str]] = {}
    for path in sorted(pathlib.Path(_typing.__file__).parent.parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sets = {
            target.id: frozenset(
                element.value for element in node.value.args[0].elts if isinstance(element, ast.Constant)
            )
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "frozenset"
            and node.value.args
            and isinstance(node.value.args[0], ast.Set)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "reject_unknown_kwargs":
                allowed, method = node.args[1], node.args[2]
                if isinstance(allowed, ast.Name) and isinstance(method, ast.Constant):
                    found[method.value] = sets.get(allowed.id, frozenset())
    return found


_ACCEPTED = _accepted_keywords()


def _absorbed(name: str, parameter: str, kind: str, concrete: dict[str, tuple[str, bool]]) -> bool:
    """Whether a tail could really be where a declared parameter went.

    Two ways, and each was measured rather than assumed.  A `*args` takes a positional one, which is how
    `extracting("user")` reaches `extracting(*names)`; it takes nothing by keyword, and excusing every
    tail let a `strict: bool = ...` invented on `is_subset_of` pass while the call raised.  A `**kwargs`
    takes a keyword one, but only where the runtime does not screen it: `extracting(name="user")`
    type-checked in all three checkers and raised `unexpected keyword argument 'name'`, because the
    guard behind that tail accepts `filter` and `sort` and nothing else.
    """
    kinds = {kind for kind, _default in concrete.values()}
    if "*args" in kinds and kind == "positional-only":
        return True
    return "**kwargs" in kinds and parameter in _ACCEPTED.get(name, frozenset())


def _has_a_tail(concrete: dict[str, tuple[str, bool]]) -> bool:
    """Whether the runtime is variadic at all, which is what used to have it skipped."""
    return any(kind.startswith("*") for kind, _default in concrete.values())


@pytest.fixture(scope="module")
def pairs():
    return _pairs()


def test_the_comparison_itself_has_something_to_compare(pairs) -> None:
    # a walk that found nothing would pass every assertion below it
    assert_that(pairs).described_as("declarations with a runtime method to compare").is_length_between(600, 1600)


def test_the_methods_behind_a_variadic_tail_are_compared_by_their_head(pairs) -> None:
    """The five that carry a named parameter alongside the tail, `is_equal_to` first among them.

    Named rather than counted: a walk that stopped including them again would leave every assertion
    below it passing over a smaller surface, and the count alone would not say which names were lost.
    """
    compared = {name for _protocol, name, _promised, concrete in pairs if _has_a_tail(concrete)}
    assert_that(compared).described_as("methods with a tail, compared rather than skipped").contains(
        "is_equal_to", "is_array_equal", "is_frame_equal", "is_array_close_to", "is_subset_of"
    )


def test_no_parameter_is_accepted_at_runtime_without_being_declared(pairs) -> None:
    """One a caller cannot pass without a cast, though the runtime would take it."""
    undeclared = [
        f"{protocol}.{name}({parameter})"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, _default) in concrete.items()
        # a view spelling out the keywords it accepts instead of repeating `**kwargs` is the design, not an omission
        if parameter not in promised and not kind.startswith("*")
    ]
    assert_that(sorted(set(undeclared))).described_as("accepted at runtime, absent from the typed surface").is_empty()


def test_no_parameter_is_declared_without_existing_at_runtime(pairs) -> None:
    """The other direction, and the worse one: the call type-checks and then raises."""
    invented = [
        f"{protocol}.{name}({parameter})"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, _default) in promised.items()
        if parameter not in concrete and not kind.startswith("*") and not _absorbed(name, parameter, kind, concrete)
    ]
    assert_that(sorted(set(invented))).described_as("declared, and the runtime has no such parameter").is_empty()


def test_the_two_agree_about_how_a_parameter_may_be_passed(pairs) -> None:
    """`f(x)`, `f(x, /)` and `f(*, x)` are three different promises, and only one of them is true."""
    differing = [
        f"{protocol}.{name}({parameter}): {kind} at runtime, {promised[parameter][0]} declared"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, _default) in concrete.items()
        if parameter in promised and promised[parameter][0] != kind and not promised[parameter][0].startswith("*")
    ]
    assert_that(sorted(set(differing))).described_as("passed one way at runtime and another in the type").is_empty()


def test_the_two_agree_about_whether_a_parameter_is_required(pairs) -> None:
    """An omission a checker allows and the runtime refuses is a failure at the call site, not here."""
    differing = [
        f"{protocol}.{name}({parameter}): {'optional' if has_default else 'required'} at runtime"
        for protocol, name, promised, concrete in pairs
        for parameter, (kind, has_default) in concrete.items()
        if parameter in promised and promised[parameter][0] == kind and promised[parameter][1] != has_default
    ]
    assert_that(sorted(set(differing))).described_as("required in one half and optional in the other").is_empty()


def _aliases() -> dict[str, set[str]]:
    """``{alias: the heads it stands for}`` for the aliases the typed surface declares.

    Without this the comparison reports `_Number` against `SupportsFloat`, which is one type written
    two ways: the views spell the numeric bound through the alias and the runtime cannot, since the
    alias lives inside the `TYPE_CHECKING` block.

    Three shapes, because the surface uses three.  A plain `X = Y` names one thing.  An annotated one
    names several, written either as a string, which is parsed rather than evaluated, or as an
    expression, which `ClassInfo` is: only its recursive reference is quoted, since ty ignores an alias
    whose whole right-hand side is a string.  Reported as a name instead, it read as a runtime shape of
    its own and the gate compared `ClassInfo` against `type` as though they were different promises.

    The recursion needs nothing special: only top-level members are read, so the nested tuple yields the
    head `tuple` and the alias never names itself in the result.
    """
    found: dict[str, set[str]] = {}
    for source in (_typing.__file__, _matcher_impls.__file__):
        for node in ast.walk(ast.parse(pathlib.Path(source).read_text(encoding="utf-8"))):
            name, value, annotated = _alias_parts(node)
            if not name:
                continue
            if isinstance(value, ast.Name):
                found[name] = {value.id}
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                # parsed, never evaluated: the value is source text and running it would import whatever it names
                written = ast.parse(value.value, mode="eval").body
                found[name] = {member.split("[", 1)[0] for member in _members_of(written)}
            elif annotated and isinstance(value, ast.BinOp | ast.Subscript):
                found[name] = {member.split("[", 1)[0] for member in _members_of(value)}
    return found


def _alias_parts(node: ast.AST) -> tuple[str, ast.expr | None, bool]:
    """``(alias name, its value, whether it was annotated)``, or an empty name.

    The annotated form is read only when the annotation says `TypeAlias`: any other string-valued
    assignment in these modules is a value rather than a type, and parsing one as an expression fails.
    The flag matters because an expression-valued alias is only trustworthy when annotated: every
    `seen = seen | {pair_id}` in a walked module is an expression assigned to a name too.
    """
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id, node.value, False
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if _plain_annotation(node.annotation) == "TypeAlias":
            return node.target.id, node.value, True
    return "", None, False


def _plain_annotation(node: ast.expr) -> str:
    """The bare name an annotation carries, or an empty string for anything else."""
    return node.id if isinstance(node, ast.Name) else ""


_ALIASES = _aliases()


def _shapes(annotation: ast.expr) -> set[str]:
    """The names a top-level union offers, one per member, with any subscript dropped.

    The head rather than the whole spelling, because the two halves write one promise two ways: a view
    says `Collection[_E]` where the runtime says `Collection[Any]`, and comparing those as text would
    report every generic in the surface.  What is lost with the subscript is real and is the limit of
    this comparison: `list[str]` and `list[int]` read the same here.

    The split is on the syntax tree and not on the character, which is not a refinement either.  Reading
    the `|` inside `type[set[_E] | frozenset[_E]]` as a top-level union makes `frozenset` look like
    something the views offer and the runtime does not, and four of the first four findings this check
    ever produced were that and nothing else.
    """
    heads = (member.split("[", 1)[0] for member in _members_of(annotation))
    return {resolved for head in heads for resolved in _ALIASES.get(head, {head})}


def _covered() -> tuple[list[tuple[str, str, set[str], set[str]]], collections.Counter[str]]:
    """``(method, parameter, what the views offer between them, what the runtime declares)``, and the skips.

    The union across views rather than each view against the runtime, because narrowing per view is the
    design: `_TextAssertion.starts_with(prefix: str)` is deliberately narrower than a runtime that takes
    any element, and so is every other view of it.  What no set of views may do between them is leave a
    spelling the runtime accepts with nowhere to be written.
    """
    offered: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    for view in sorted(_VALUE_VIEWS):
        for name, methods in _declarations_of(view).items():
            for method in methods:
                arguments = method.args
                for argument in arguments.posonlyargs + arguments.args + arguments.kwonlyargs:
                    if argument.arg != "self" and argument.annotation is not None:
                        offered[name][argument.arg] |= _shapes(argument.annotation)

    pairs: list[tuple[str, str, set[str], set[str]]] = []
    skipped: collections.Counter[str] = collections.Counter()
    for name, parameters in sorted(offered.items()):
        concrete = _concrete_signature(name)
        if concrete is None:
            continue
        for parameter, declared in sorted(parameters.items()):
            found = concrete.parameters.get(parameter)
            if found is None:
                skipped["the runtime has no such parameter: it arrives through `**kwargs`"] += 1
                continue
            if found.annotation is inspect.Parameter.empty:
                skipped["the runtime declares no annotation at all, so there is nothing to disagree with"] += 1
                continue
            runtime = _runtime_shapes(found.annotation)
            if runtime is None:
                skipped["the runtime spells it in a form this walk cannot read"] += 1
                continue
            if runtime == {"object"}:
                skipped["the runtime takes `object`, which no narrowing can fail to be covered by"] += 1
                continue
            pairs.append((name, parameter, declared, runtime))
    return pairs, skipped


def _runtime_shapes(annotation: object) -> set[str] | None:
    """The runtime's side of the comparison, or ``None`` when it cannot be read as a spelling."""
    try:
        return _shapes(ast.parse(str(annotation), mode="eval").body)
    except SyntaxError:
        return None


@pytest.fixture(scope="module")
def covered():
    return _covered()


class TestWhatTheSpellingComparisonDistinguishes:
    """The depth of `_shapes`, shown rather than described.

    About `_shapes` and not about the gate as a whole, which is a narrower claim and the true one: the
    gate drops a pair before comparing it when the runtime side is exactly `object`, so two of the pairs
    below (`str` and `Sized` against `object`) never reach the comparison in a real run.  They are here
    because what they pin is the reading of a spelling, and a rung that stopped reading `object` as
    different from `str` would take the skip with it and pass unnoticed.

    `_shapes` keeps the head of each union member and drops what is under it, so `bytes` against
    `bytearray` reads as different and `list[str]` against `list[int]` does not.  That is written in the
    docstring there, and a sentence is not a demonstration: these say which spelling change is legible to
    it and which is not, so the boundary moves only when somebody moves it here.

    Going deeper was measured and refused.  Comparing the full spelling reports 17 of the 101 comparable
    parameters, and every one of the 17 is deliberate: the views bind the element the runtime leaves
    open (`Callable[[_E], object]` against `Callable[..., bool]`), the refinement ladders of
    `is_instance_of` and `satisfies`, and `dict` against `dict[Any, Any]`.  Telling those from a real
    narrowing needs subtype reasoning, which is what the three checkers already do on real calls.
    """

    @staticmethod
    def _seen(declared: str, runtime: str) -> bool:
        """Whether `_shapes` reads the two spellings as different."""
        shapes = (_shapes(ast.parse(declared, mode="eval").body), _shapes(ast.parse(runtime, mode="eval").body))
        return shapes[0] != shapes[1]

    @pytest.mark.parametrize(
        ("declared", "runtime"),
        [
            ("bytes", "bytes | bytearray"),
            ("datetime.date", "datetime.datetime"),
            ("str", "object"),
            ("Sized", "object"),
            ("int", "SupportsFloat"),
        ],
    )
    def test_a_different_type_is_seen(self, declared: str, runtime: str) -> None:
        assert_that(self._seen(declared, runtime)).described_as(f"{declared} against {runtime}").is_true()

    @pytest.mark.parametrize(
        ("declared", "runtime"),
        [
            ("list[str]", "list[int]"),
            ("Callable[[str], object]", "Callable[[int], object]"),
            ("Mapping[str, int]", "Mapping[int, str]"),
            ("type[set[_E] | frozenset[_E]]", "type[set[_E]]"),
        ],
    )
    def test_a_different_parameter_of_the_same_type_is_not(self, declared: str, runtime: str) -> None:
        assert_that(self._seen(declared, runtime)).described_as(f"{declared} against {runtime}").is_false()


class TestTheTypedSurfaceAndTheRuntimeAcceptTheSameThings:
    """The axis no checker can report, because conformance to a protocol is contravariant in parameters.

    A view narrower than the runtime satisfies it by construction, so nothing complains when every view
    between them refuses a value the runtime accepts.  `starts_with_bytes` declared `bytes` in the one
    view offering it while the runtime took a `bytearray` as well, and ty, mypy and pyright were clean on
    that for as long as it stood.  A view wider than the runtime is the same blindness from the other
    side: the call type-checks, and the runtime is under no obligation to do anything sensible with it.

    Both directions compare the head of each union member and nothing under it, so what a green run here
    means is narrower than the two test names read: `bytes` against `bytearray` is caught, `list[str]`
    against `list[int]` is not.  `_shapes` says why that is the honest limit rather than a shortcut.
    """

    def test_the_comparison_reached_most_of_what_the_views_declare(self, covered) -> None:
        pairs, skipped = covered
        # the headline must not outrun the check: a third of the declared parameters go uncompared for one of
        # four stated reasons, and a walk comparing nothing would pass both directions below without a word
        assert_that(pairs).described_as("parameters with a spelling on both sides").is_length_between(60, 250)
        assert_that(sum(skipped.values())).described_as("parameters skipped, each for a named reason").is_less_than(
            len(pairs)
        )

    def test_no_value_the_runtime_accepts_is_unwritable_through_every_view(self, covered) -> None:
        """The direction that caught `starts_with_bytes`: accepted at run time, refused by every view."""
        pairs, _skipped = covered
        unreachable = [
            f"{name}({parameter}): runtime takes {sorted(runtime)}, no view offers {sorted(runtime - declared)}"
            for name, parameter, declared, runtime in pairs
            if runtime - declared and "object" not in declared
        ]
        assert_that(sorted(unreachable)).described_as(
            "accepted at run time and unwritable in every typed view"
        ).is_empty()

    def test_the_alias_table_resolves_what_the_surface_writes(self) -> None:
        """Pins the resolver, which nothing else here reaches yet.

        `_covered()` walks the value views and the builder, and `ClassInfo` is written on the matcher
        surface, so deleting the resolution below would leave every other test in this file green while
        the gate quietly went back to comparing an alias name against the shapes it stands for.
        """
        assert_that(_ALIASES).described_as("aliases the surface declares").contains_key("ClassInfo", "_Number")
        assert_that(_ALIASES["ClassInfo"]).described_as("what ClassInfo stands for").is_equal_to(
            {"type", "UnionType", "tuple"}
        )
        assert_that(_ALIASES["_Number"]).described_as("the plain form still resolves").is_equal_to({"SupportsFloat"})

    def test_no_view_offers_what_the_runtime_does_not_declare(self, covered) -> None:
        """The other direction: a call every checker allows, on a signature that never promised it."""
        pairs, _skipped = covered
        overreaching = [
            f"{name}({parameter}): views offer {sorted(declared - runtime)}, runtime declares {sorted(runtime)}"
            for name, parameter, declared, runtime in pairs
            if declared - runtime
        ]
        assert_that(sorted(overreaching)).described_as(
            "promised by a typed view and absent from the runtime signature"
        ).is_empty()
