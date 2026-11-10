"""Hold the generated verdict twins to what the generator produces from the protocols they mirror.

`check()` runs one assertion for its verdict instead of its failure, so every assertion is reachable
through it with the return type replaced.  Written by hand that is a second copy of 182 declarations
kept in step by nobody, and the copy drifts silently: a signature changes on one side and the check
surface keeps promising the old one.

Generated instead, and regenerated here.  A difference means the file on disk was edited or the
protocols moved without the twins following, and either way the answer is to run the generator.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

from assertpy import assert_that
from assertpy._engine import _check_typing, _typing
from assertpy._engine._operations import NOT_AN_OPERATION, WITHOUT_A_VERDICT
from tests.optional import needs

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _generator() -> ModuleType:
    """Import the generator, which lives outside the package, only where it is needed.

    Inline rather than at the top on purpose: `scripts/` is not copied into mutmut's mutants tree, and
    a module-level import of it fails at collection, which takes the whole mutation baseline with it.
    Reached from one test, so the run can deselect that test instead of losing the file.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    import generate_check_protocols

    return generate_check_protocols


def test_the_generated_twins_match_the_protocols_they_mirror() -> None:
    generator = _generator()
    on_disk = pathlib.Path(_check_typing.__file__).read_text(encoding="utf-8")
    # the generator formats through ruff after writing, so compare what ruff would make of both
    produced = _formatted(generator.generate())
    assert_that(produced).described_as(
        "the verdict twins are out of step; run python scripts/generate_check_protocols.py"
    ).is_equal_to(_formatted(on_disk))


def _formatted(source: str) -> str:
    """Both steps the generator runs after writing, so the comparison is of the same thing twice."""
    needs("ruff")
    # in the generator's order: formatting first collapses the blank lines between stub bodies
    for command in (
        ["ruff", "format", "--stdin-filename", _check_typing.__file__, "-"],
        ["ruff", "check", "--fix", "--quiet", "--stdin-filename", _check_typing.__file__, "-"],
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


class TestWhatTheTwinsCarry:
    """The generation is only worth its cost if the result says the right thing."""

    def test_a_twin_carries_the_assertions_of_the_protocol_it_mirrors(self) -> None:

        source = pathlib.Path(_typing.__file__).read_text(encoding="utf-8")
        twins = pathlib.Path(_check_typing.__file__).read_text(encoding="utf-8")
        for view in ("_StringAssertion", "_NumericAssertion", "_DictAssertion"):
            assert_that(twins).described_as(f"the twin of {view}").contains(f"class {view.replace('_', '_Check', 1)}(")
        assert_that(source).contains("def check(self) -> _CheckStringAssertion: ...")

    def test_no_twin_carries_an_operation_without_a_verdict(self) -> None:

        twins = pathlib.Path(_check_typing.__file__).read_text(encoding="utf-8")
        offered = [name for name in WITHOUT_A_VERDICT if f"    def {name}(" in twins]
        assert_that(offered).described_as(
            "an operation that reaches no verdict cannot be asked for one, so it has no twin"
        ).is_empty()

    @pytest.mark.parametrize(
        ("call", "expected"),
        [
            (lambda: assert_that(1).check().is_positive(), True),
            (lambda: assert_that(-1).check().is_positive(), False),
            (lambda: assert_that("x").check().starts_with("x"), True),
            (lambda: assert_that(-1).check().not_.is_positive(), True),
        ],
        ids=["numeric-holds", "numeric-fails", "string-holds", "negated"],
    )
    def test_the_runtime_still_answers_through_every_twin(self, call, expected) -> None:
        # the twins describe an object resolving names through `__getattr__`, so check the runtime, not the declaration
        assert_that(call().passed).is_equal_to(expected)


def test_every_twin_declaration_mirrors_the_one_it_was_generated_from() -> None:
    """Why the twins are not walked by `test_protocol_parity.py`, made a check rather than a claim.

    Parity proves every declared protocol method exists at runtime, and it reads `_typing.py` only.
    The twins are generated *from* those protocols, so a twin method exists at runtime exactly when
    its original does, and the generation gate above proves the file on disk is what the generator
    produces.  What is left is the step in between: whether the generator produced a mirror.

    Whole declarations, not name sets.  Comparing names caught an invented or dropped assertion and
    would have waved through a lost parameter, a changed default or a missing `@overload`, all of
    which the file comparison agrees with once the file is regenerated.  The generator is allowed two
    transformations, so those two are normalised away here: the return type, and the caught exception's
    parameter made covariant, since a verdict reads no exception back.
    """
    originals = _declared(pathlib.Path(_typing.__file__).read_text(encoding="utf-8"))
    twins = _declared(pathlib.Path(_check_typing.__file__).read_text(encoding="utf-8"))
    skip = set(WITHOUT_A_VERDICT) | NOT_AN_OPERATION

    expected = {
        _twin_name(name): (
            {
                method: [_as_a_verdict(node) for node in nodes]
                for method, nodes in methods.items()
                if method not in skip
            },
            [_twinned_base(base) for base in bases],
        )
        for name, (methods, bases) in originals.items()
    }
    # both directions over the classes: a twin for nothing and a protocol with no twin are each a difference
    assert_that(sorted(twins)).described_as("the set of twins").is_equal_to(sorted(expected))

    differing = {}
    for twin, (methods, bases) in twins.items():
        wanted_methods, wanted_bases = expected[twin]
        rendered = {name: [ast.unparse(node) for node in nodes] for name, nodes in methods.items() if name != "not_"}
        if rendered != wanted_methods:
            differing[f"{twin} declarations"] = {
                "only in the twin": sorted(set(rendered) - set(wanted_methods)),
                "missing from the twin": sorted(set(wanted_methods) - set(rendered)),
                "differing": sorted(n for n in set(rendered) & set(wanted_methods) if rendered[n] != wanted_methods[n]),
            }
        if bases != wanted_bases:
            differing[f"{twin} bases"] = {"mirrored": wanted_bases, "found": bases}
    assert_that(differing).described_as("a twin is not the mirror of the protocol it names").is_empty()


def _twin_name(name: str) -> str:
    return name.replace("_", "_Check", 1)


def _twinned_base(base: str) -> str:
    """A base as the twin should spell it: the assertion's name becomes its twin, and `_Exc` covariant."""
    base = re.sub(r"\b_Exc\b", "_Exc_co", base)
    head, _, rest = base.partition("[")
    if not head.endswith("Assertion"):
        return base
    return _twin_name(head) + ("[" + rest if rest else "")


def _as_a_verdict(node: ast.FunctionDef) -> str:
    """The declaration as the generator is allowed to render it: everything, with the return replaced."""
    copied = ast.parse(ast.unparse(node)).body[0]
    assert isinstance(copied, ast.FunctionDef)
    copied.returns = ast.Name(id="AssertionOutcome")
    copied.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
    copied.decorator_list = [d for d in copied.decorator_list if ast.unparse(d) != "property"]
    return ast.unparse(copied)


def _declared(source: str) -> dict[str, tuple[dict[str, list[ast.FunctionDef]], list[str]]]:
    """``{protocol: (its declarations by name, its assertion bases)}``, bases not resolved further.

    A list per name, not one node: `satisfies` and the two refinements are overload ladders, and a
    dict keyed by name kept only the last rung.  Comparing that would have waved through a ladder the
    generator rendered short.
    """
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or not node.name.endswith("Assertion"):
            continue
        methods: dict[str, list[ast.FunctionDef]] = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.setdefault(item.name, []).append(item)
        # every base written out: bare names would let a generator hand back `_CheckIterableAssertion[Any]` unnoticed
        found[node.name] = (methods, [ast.unparse(base) for base in node.bases])
    return found


def test_anything_landing_on_the_builder_reaches_its_own_check_rather_than_a_twin() -> None:
    """The measured edge of the typed `check()`, kept as a test rather than only as a comment.

    A pivot hands back `AssertionBuilder[_E]` instead of re-deriving the view for the element, so
    `last().check()` lands on the builder's untyped proxy.  A twin for the builder was tried and
    dropped: composing one from the capabilities it has puts the text and real-number protocols in one
    class, whose ordering assertions take different operands, and the runtime has no such conflict
    because its MRO picks one.  The builder is the widest surface on the ordinary path too, so this is
    the same width rather than a new hole.
    """
    written = pathlib.Path(_typing.__file__).read_text(encoding="utf-8")
    assert_that(written).described_as("the boundary has to be written where the declaration is").contains(
        "hands back `AssertionBuilder[_E]`", "capability umbrella claims"
    )

    # the runtime still names a typo, from both ways in: after a pivot, and on a value the umbrella claims
    @dataclasses.dataclass
    class _Point:
        x: int

    for reached in (assert_that([1, 2]).last().check(), assert_that(_Point(1)).check()):
        with pytest.raises(AttributeError, match="has no assertion"):
            reached.no_such_assertion()
