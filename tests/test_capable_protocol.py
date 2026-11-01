"""Hold the façade the capability umbrella hands back to what it is generated from.

`assert_that()` returns this for a value that answers to some capability and to no overload by name.
It used to return the builder itself, which meant every assertion on it, including the six that order
the value: `assert_that(a_mapping).is_positive()` type-checked on ty, mypy and Pyright, the three
gated then, and raised `TypeError` when it ran.

Two claims here, and they pull against each other, which is why both are written down. Nothing the
builder offers may be missing, because the umbrella exists for values the library could not name and a
narrowing by accident refuses a call that runs. And the six have to be restricted, because that is the
whole reason the façade exists.
"""

from __future__ import annotations

import ast
import builtins
import collections
import datetime
import functools
import numbers
import pathlib
import subprocess
import sys
from typing import TYPE_CHECKING, ClassVar

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import ModuleType

import assertpy.assertpy
from assertpy import AssertionFailure, assert_that
from assertpy._engine import _capable_typing
from assertpy._engine._operations import ALSO_ASSERTS, CONFIGURES, TRANSFORMS, WITHOUT_A_VERDICT
from assertpy.assertpy import AssertionBuilder

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SOURCE = pathlib.Path(_capable_typing.__file__).read_text(encoding="utf-8")


class _Capable:
    """The narrowest value the umbrella claims: one capability and nothing else."""

    def __iter__(self):
        return iter(("a",))


class _Maximal(_Capable):
    """Every capability the umbrella recognises, plus every operator a restricted assertion reads.

    Registered as a real number because that is what the numeric gate asks, and registration is the one
    thing no checker can see.  That is why the numeric family is the one left open: measured, `is_zero()`
    runs on a class registered without `__float__`, so every structural stand-in refused a working call.
    """

    def __float__(self):
        return 0.0

    def __lt__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __le__(self, other):
        return True

    def __ge__(self, other):
        return False

    def __fspath__(self):
        return "."

    def __call__(self, *args, **kwargs):
        raise ValueError("boom")

    # the other four capabilities, so an assertion reading a mapping, a model or a response is answered here
    def keys(self):
        return ("id",)

    def __getitem__(self, key):
        return 1

    def __len__(self):
        return 1

    def __contains__(self, item):
        return True

    def model_dump(self, *args, **kwargs):
        return {"id": 1}

    @property
    def status_code(self):
        return 200

    @property
    def headers(self):
        return {"content-type": "application/json"}

    def json(self):
        return {"id": 1}


numbers.Real.register(_Maximal)


class _Ordered(_Capable):
    """Capable and orderable, which is what the relational assertions read."""

    def __lt__(self, other):
        return True

    def __gt__(self, other):
        return False

    def __le__(self, other):
        return True

    def __ge__(self, other):
        return False


class _Numeric(_Ordered):
    """Capable, orderable and a real number, which is what the numeric gate reads.

    Ordering as well, because `is_between` and `is_close_to` order the pair after the number gate, and
    a subject with only the registration reads as refusing them.
    """

    def __float__(self):
        return 0.0


numbers.Real.register(_Numeric)


class _Convertible(_Capable):
    """Capable and a real number that converts through `__float__`, carrying no ordering."""

    def __float__(self):
        return 0.0


class _Indexed(_Capable):
    """The other way to convert: `math.isnan` falls back to `__index__` when there is no `__float__`."""

    def __index__(self):
        return 0


class _Opaque(_Capable):
    """Registered as a real and converting neither way, which is what isolates the conversion.

    Every other subject that lacks conversion also lacks the registration, so it refuses at the number
    gate and proves nothing about conversion. This one gets past that gate and is refused by `math.isnan`.
    """


numbers.Real.register(_Convertible)
numbers.Real.register(_Indexed)
numbers.Real.register(_Opaque)


class _Bound:
    """A closeness operand that compares back, so the subject needs no ordering of its own.

    Measured: with ordinary int bounds a convertible subject with no `__lt__` raises, which reads as the
    assertion needing an ordering. It needs one on either side, and this is the side the caller supplies.
    """

    def __init__(self, held):
        self.held = held

    def __float__(self):
        return float(self.held)

    def __sub__(self, other):
        return _Bound(self.held - float(other))

    def __add__(self, other):
        return _Bound(self.held + float(other))

    # answered without converting the subject: reading `float(other)` here would hand the subject the very
    # capability the rung is keyed on, and a subject that cannot convert would read as answering
    def __lt__(self, other):
        return self.held < 0

    def __gt__(self, other):
        return self.held > 0

    def __eq__(self, other):
        return False

    def __hash__(self):
        return hash(self.held)


numbers.Real.register(_Bound)


class _Keys(_Capable):
    """Capable and keyed, which is what the key pair reads: `keys()` plus the walk `_Capable` brings."""

    def keys(self):
        return ("a",)


class _KeysAndItems(_Keys):
    """And the lookup, which reading an entry needs and reading a key does not."""

    def __getitem__(self, key):
        return 1


class _KeysAndValues(_Keys):
    """And the values, which only the value pair reads.  A lookup is not enough: a subject carrying
    `keys`, the walk and `__getitem__` still refuses `contains_value`, measured."""

    def values(self):
        return (1,)


class _Shaped:
    """Claimed by the umbrella for a shape that is not a sequence, which is what isolates walking one.

    Every other subject here walks, `_Capable` being the base of all of them, so none of them can stand
    for a value the umbrella claims and `contains_in_order` refuses.  A dataclass is the cheapest of the
    four such shapes to write out.
    """

    __dataclass_fields__: ClassVar[dict[str, object]] = {}


class _Indexable(_Shaped):
    """A sequence the older way: integer lookup ending in `IndexError`, and no `__iter__`.

    `list(value)` walks it, so `contains_in_order()` runs on it, and a restriction asking only for
    `Iterable` refused a value that works.
    """

    def __getitem__(self, index: int, /) -> int:
        if index > 2:
            raise IndexError(index)
        return index


class _Pathish(_Capable):
    """Capable and a path, which is the structural half of `isinstance(val, (str, os.PathLike))`."""

    def __fspath__(self):
        return "."


class _Callish(_Capable):
    """Capable and callable, which is what `callable(val)` reads.

    A fixed signature rather than `*args, **kwargs`, so the rung is measured against a real callable
    instead of one written to match its own protocol.
    """

    def __call__(self, first: int = 0) -> int:
        raise ValueError("boom")


_CARRIES = {
    "_Orderable": (_Ordered,),
    "_PathLike": (_Pathish,),
    "_Callable": (_Callish,),
    "SupportsFloat | SupportsIndex": (_Convertible, _Indexed),
    "_Keyed": (_Keys,),
    "_KeyedWithItems": (_KeysAndItems,),
    "_KeyedWithValues": (_KeysAndValues,),
    "Iterable[_E] | _Indexed[_E]": (_Capable, _Indexable),
}
"""Subjects per shape, each carrying that shape and no other, so a wrong key cannot read as right.

The conversion key has two, one per half of the union: `math.isnan` reads `__float__` and falls back to
`__index__`, and a carrier for only one half would leave the other unmeasured.
"""

_WITHOUT = {
    "_Orderable": (_Capable, _Pathish, _Callish),
    "_PathLike": (_Capable, _Ordered, _Callish),
    "_Callable": (_Capable, _Ordered, _Pathish),
    "SupportsFloat | SupportsIndex": (_Capable, _Ordered, _Pathish, _Callish, _Opaque),
    "_Keyed": (_Capable, _Ordered, _Pathish, _Callish),
    # a subject with the keys and the walk but no lookup, and one with the values instead, are each a
    # genuine non-carrier here: measured, both refuse an entry
    "_KeyedWithItems": (_Capable, _Ordered, _Pathish, _Callish, _Keys, _KeysAndValues),
    "_KeyedWithValues": (_Capable, _Ordered, _Pathish, _Callish, _Keys, _KeysAndItems),
    "Iterable[_E] | _Indexed[_E]": (_Shaped,),
}
"""Subjects that genuinely lack each shape, listed rather than derived.

`_Numeric` carries an ordering as well, because the numeric assertions order the pair after the number
gate, so "every other subject" would have read the numeric one as answering an ordering it was never
keyed on.
"""


_ASKED_OF_THE_CHAIN = frozenset({"when_called_with"})
"""Gated on a call before it rather than on the value, so asking it alone proves nothing."""

_ARGUMENTS = [
    (),
    ("a",),
    ("id",),
    (0,),
    (1, 1),
    (0, 9),
    (_Bound(0), _Bound(9)),
    (ValueError,),
    ("utf-8",),
    (b"a",),
    (0, b"a"),
    ({"id": 1},),
    ("$.id",),
    (lambda item: True,),
    (str,),
]


def _answers(value, name) -> bool:
    """Whether *value* can be asked *name* at all, over every plausible argument tuple.

    A verdict counts as an answer and so does a pass: what it is looking for is the refusal a gate
    raises, which is `TypeError` or `ValueError` whatever the arguments were.
    """
    for args in _ARGUMENTS:
        try:
            getattr(assert_that(value), name)(*args)
        # the loop is over argument tuples, not over a workload: the cost of the `try` is not the point
        except AssertionFailure:  # noqa: PERF203
            return True
        except Exception:  # any refusal is one, and the next tuple may still answer
            continue
        else:
            return True
    return False


def _generator() -> ModuleType:
    """Import the generator, which lives outside the package, only where it is needed.

    Inline for the reason `test_check_protocols.py` gives: `scripts/` is not copied into mutmut's
    mutants tree, and a module-level import of it loses the whole baseline at collection.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    import generate_poll_protocols

    return generate_poll_protocols


def _formatted(source: str, path: str = _capable_typing.__file__) -> str:
    """*source* after the two steps the generator runs once it has written *path*: ruff format, then ruff's fixes."""
    for command in (
        ["ruff", "format", "--stdin-filename", path, "-"],
        ["ruff", "check", "--fix", "--quiet", "--stdin-filename", path, "-"],
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


def _declarations() -> dict[str, list[ast.FunctionDef]]:
    """`{name: its declarations}` off the façade, a list because the hand-written ones are ladders."""
    found: dict[str, list[ast.FunctionDef]] = {}
    for node in ast.walk(ast.parse(_SOURCE)):
        if isinstance(node, ast.ClassDef) and node.name == "_CapableAssertion":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    found.setdefault(item.name, []).append(item)
    return found


_RECEIVER = "«the receiver»"

_FOLLOWS_THE_RECEIVER = frozenset({"is_not_none"})
"""The one ladder whose return is the same value narrowed, so on the façade it stays on the façade.

Every other one here pivots: `is_instance_of` lands on a class the umbrella may not claim at all, and
`first`, `single` and `mapped` land on an element or a list.  Those hand back the builder on both sides,
so this is a named exception rather than a normalisation applied to every return.
"""


def _normalised(node: ast.FunctionDef) -> str:
    """One rung as text, with the receiver's own type spelled the same on both sides.

    The receiver is the one part that has to differ: a rung reached through the façade is written over
    `_CapableAssertion` where the builder writes `AssertionBuilder`, and a value the umbrella claims is
    only ever the first of those.  Everything else, parameters and return alike, is compared as written.
    """
    rendered = ast.parse(ast.unparse(node)).body[0]
    if not isinstance(rendered, ast.FunctionDef):  # pragma: no cover - every rung here is a function
        raise TypeError(node.name)
    rendered.body = [ast.Expr(value=ast.Constant(value=...))]
    rendered.decorator_list = []
    receiver = rendered.args.args[0] if rendered.args.args else None
    if receiver is not None and receiver.annotation is not None:
        receiver.annotation = ast.Name(id=_without_the_receiver(ast.unparse(receiver.annotation)))
    if node.name in _FOLLOWS_THE_RECEIVER and rendered.returns is not None:
        rendered.returns = ast.Name(id=_without_the_receiver(ast.unparse(rendered.returns)))
    return ast.unparse(rendered)


def _without_the_receiver(written: str) -> str:
    for spelling in ("AssertionBuilder", "_CapableAssertion"):
        written = written.replace(spelling, _RECEIVER)
    return written


def _attributes() -> set[str]:
    """The façade's non-callable members, which are declared rather than defined."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(_SOURCE)):
        if isinstance(node, ast.ClassDef) and node.name == "_CapableAssertion":
            found |= {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    return found


def _builder_ladders() -> dict[str, list[str]]:
    """`{name: its rungs}` for every assertion the builder declares for checkers only.

    These live in a `TYPE_CHECKING` block inside the class, so they are reached through the `if` rather
    than off the class body, and they are the ones a mixin's own signature cannot stand in for.
    """
    source = pathlib.Path(assertpy.assertpy.__file__).read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or node.name != "AssertionBuilder":
            continue
        for guard in (item for item in node.body if isinstance(item, ast.If)):
            for item in guard.body:
                if isinstance(item, ast.FunctionDef) and any(
                    ast.unparse(one) == "overload" for one in item.decorator_list
                ):
                    found.setdefault(item.name, []).append(_normalised(item))
    return found


def test_the_facade_matches_what_the_generator_produces() -> None:
    generator = _generator()
    assert_that(_formatted(generator.generate_capable())).described_as(
        "the façade is out of step; run python scripts/generate_poll_protocols.py"
    ).is_equal_to(_formatted(_SOURCE))


class TestNothingTheBuilderOffersIsMissing:
    """The half that decides whether this can ship at all.

    A value reaching the umbrella used to get the builder, so anything absent here is an assertion that
    stopped type-checking while still running, which is the expensive direction of the two.
    """

    def test_every_public_member_of_the_builder_is_declared(self) -> None:
        """Read off a builder itself, not off the generator's idea of where to look.

        Rewritten twice, and each version was green while something was missing.  Built from
        `_builder_surface() | _BY_HAND` it could not name what the generator does not read, and four
        members that live on the builder rather than on a mixin were absent.  Built from the class it
        could not name what `__init__` sets, and four more went the same way.
        """
        # built directly: `assert_that()` hands back a subclass, and a suite's four registered names read as dropped
        carried = {name for name in dir(AssertionBuilder({"id": 1})) if not name.startswith("_")}
        declared = set(_declarations()) | _attributes()
        assert_that(carried - declared).described_as("a member the umbrella used to offer").is_empty()

    def test_the_runtime_answers_every_name_the_facade_declares(self) -> None:
        """Declared and not there at run time would be the same defect read from the other end."""
        builder = assert_that({"id": 1})
        missing = [name for name in _declarations() if not name.startswith("__") and not hasattr(builder, name)]
        assert_that(missing).described_as("declared on the façade and absent from the builder").is_empty()


class TestWhatEachRestrictedAssertionAsksFor:
    """The whole reason the façade exists, derived from the runtime rather than compared against a list.

    Written twice as a comparison against the generator's own tables, and both times an injection went
    through: removing a name from a table un-restricted it silently, and swapping one key for another
    left both sides agreeing.  These ask the runtime instead, with one subject per shape.
    """

    def test_each_family_holds_what_it_was_measured_to_hold(self) -> None:
        """How many assertions each key claims, which is where a name silently leaving is caught.

        The probe below cannot prove this direction: showing that nothing *outside* the tables is
        unanswerable needs a hand-written call per assertion, and a generic argument tuple reads a
        mapping assertion or a JSON pivot as unanswerable when it is only unsupplied.  Counts instead,
        against the families as they were measured, so removing an entry fails here and nowhere else.
        """
        generator = _generator()
        counted = {
            "shape": collections.Counter(generator._ASKS_A_SHAPE.values()),
            "type": collections.Counter(generator._ASKS_A_TYPE.values()),
        }
        assert_that(counted).described_as("what each key claims").is_equal_to(
            {
                "shape": collections.Counter(
                    {
                        "_Orderable": 6,
                        "_PathLike": 9,
                        "_Callable": 7,
                        "SupportsFloat | SupportsIndex": 5,
                        "_Keyed": 2,
                        "_KeyedWithItems": 2,
                        "_KeyedWithValues": 2,
                        "Iterable[_E] | _Indexed[_E]": 1,
                    }
                ),
                "type": collections.Counter({"int": 3, "str": 14, "datetime.datetime": 7, "bytes | bytearray": 7}),
            }
        )

    def test_every_name_in_the_tables_is_one_the_builder_has(self) -> None:
        """A misspelling would restrict nothing and read as a restriction."""
        generator = _generator()
        builder = AssertionBuilder({"id": 1})
        tabled = set(generator._ASKS_A_SHAPE) | set(generator._ASKS_A_TYPE)
        assert_that([name for name in tabled if not hasattr(builder, name)]).described_as(
            "restricted, and not a name the builder has"
        ).is_empty()

    def test_every_restricted_assertion_is_answered_by_the_shape_it_asks_for(self) -> None:
        """And the direction that catches one key swapped for another."""
        generator = _generator()
        wrong = {
            name: asked
            for name, asked in generator._ASKS_A_SHAPE.items()
            if name not in _ASKED_OF_THE_CHAIN and not all(_answers(carrier(), name) for carrier in _CARRIES[asked])
        }
        assert_that(wrong).described_as("keyed on a shape that does not answer it").is_empty()

    def test_no_restricted_assertion_is_answered_without_its_shape(self) -> None:
        generator = _generator()
        loose = {
            name: asked
            for name, asked in generator._ASKS_A_SHAPE.items()
            if any(_answers(subject(), name) for subject in _WITHOUT[asked])
        }
        assert_that(loose).described_as("answered by a value that does not carry what it asks for").is_empty()

    @pytest.mark.parametrize(
        ("shape", "members"),
        [
            ("_Orderable", ["__lt__"]),
            ("_PathLike", ["__fspath__"]),
            ("_Callable", ["__call__"]),
            ("_Keyed", ["keys"]),
            ("_KeyedWithItems", ["__getitem__"]),
            ("_KeyedWithValues", ["values"]),
        ],
    )
    def test_each_shape_asks_for_what_the_runtime_reads(self, shape, members) -> None:
        """The names are the measurement, not the family's own vocabulary.

        Every relational assertion reaches `_engine._ordering.compare`, which orders the pair with `<`,
        so `_Orderable` asks for `__lt__` and not `__gt__`.  The filesystem gate is
        `isinstance(val, (str, os.PathLike))` and a `str` never reaches here, so what is left of it is
        `__fspath__`.  The exception and warning gate is `callable(val)`.  The conversion key is spelled
        with typing's own `SupportsFloat` and `SupportsIndex`, so there is no declaration of ours to read.
        """
        declared = next(
            node for node in ast.walk(ast.parse(_SOURCE)) if isinstance(node, ast.ClassDef) and node.name == shape
        )
        assert_that([item.name for item in declared.body if isinstance(item, ast.FunctionDef)]).is_equal_to(members)

    @pytest.mark.parametrize(("derived", "base"), [("_KeyedWithItems", "_Keyed"), ("_KeyedWithValues", "_Keyed")])
    def test_a_derived_shape_still_carries_the_one_it_was_built_on(self, derived, base) -> None:
        """The members test above reads what a shape DECLARES, so a derived one dropping its base reads
        as unchanged there: `_KeyedWithItems` would still declare `__getitem__` and nothing else, while
        quietly no longer asking for `keys()`."""
        declared = next(
            node for node in ast.walk(ast.parse(_SOURCE)) if isinstance(node, ast.ClassDef) and node.name == derived
        )
        assert_that([ast.unparse(one) for one in declared.bases]).contains(base)

    def test_the_one_asked_of_the_chain_answers_after_what_it_waits_for(self) -> None:
        """`when_called_with()` is gated on a call before it rather than on the value, measured.

        On its own it refuses everything, callable or not, because it wants an expectation set first.
        Asked after `raises()`, a callable capable value answers it, which is what puts it in the table.
        """
        assert_that(_Callish()).raises(ValueError).when_called_with()


class TestWhatIsAskedOfATypeInstead:
    """The other half of the narrowing: rungs a capable value can never satisfy, and why they exist."""

    def test_no_such_assertion_answers_the_widest_capable_value(self) -> None:
        """A subject carrying every capability the umbrella knows and every operator these reach for.

        This is what makes a type-keyed rung honest rather than plausible.  Four separate readings
        during this work were wrong because the fixture lacked the one thing the assertion asked for, so
        the fixture here carries all of them at once: a name that runs belongs in the other table.
        """
        answered = [name for name in _generator()._ASKS_A_TYPE if _answers(_Maximal(), name)]
        assert_that(answered).described_as("keyed on a type, and yet answerable by a capable value").is_empty()

    def test_they_are_declared_rather_than_left_out(self) -> None:
        """Leaving one out refuses nothing, because `__getattr__` answers a name the façade does not have.

        Measured: with these dropped instead of declared, text, dates and bytes all still type-checked on
        a capable value in all three checkers.  The rung is what refuses, not the absence.
        """
        missing = set(_generator()._ASKS_A_TYPE) - set(_declarations())
        assert_that(missing).described_as("keyed on a type and not declared, so the hook answers it").is_empty()

    def test_the_two_tables_do_not_overlap(self) -> None:
        generator = _generator()
        both = set(generator._ASKS_A_SHAPE) & set(generator._ASKS_A_TYPE)
        assert_that(both).described_as("in both tables").is_empty()


class TestTheLaddersTheBuilderDeclares:
    """The narrowings carried across by hand, which a flattened signature would have dropped."""

    def test_every_ladder_the_builder_declares_is_one_here_too(self) -> None:
        """Read off the builder rather than off the generator's own list of names to carry.

        Written the other way round first, and the difference is the whole value of this test: comparing
        against `_BY_HAND` proved the façade agreed with the generator, which is a tautology when both
        come from the same list.  Three ladders were missing that way and the test was green.
        `mapped()` claimed the input container, `single()` claimed the collection instead of its
        element, and `satisfies()` lost its `TypeIs` refinement.
        """
        here = {name: [_normalised(node) for node in nodes] for name, nodes in _declarations().items()}
        differing = {
            name: {"builder": rungs, "façade": here.get(name, [])}
            for name, rungs in _builder_ladders().items()
            if here.get(name, []) != rungs
        }
        assert_that(differing).described_as("a ladder the builder declares and the façade does not").is_empty()

    def test_the_verdict_pivot_hands_back_the_verdict_twin(self) -> None:
        checks = _declarations()["check"]
        assert_that([ast.unparse(node.returns) for node in checks if node.returns]).is_equal_to(
            ["_CheckAnyValue[_CapableT_co]"]
        )


_KEEPS_THE_SUBJECT = frozenset({"Self", "_CapableAssertion[_CapableT_co]"})
"""Both ways the façade says the subject comes back: `Self`, or its own name where a restricted `self` rules it out."""

_PIVOTS = {name for name, kind in WITHOUT_A_VERDICT.items() if kind == TRANSFORMS} | ALSO_ASSERTS
"""Every operation handing back another value, as `test_operation_contract.py` derives it from the source."""

_VIEWS = _ROOT / "assertpy" / "_engine" / "_typing.py"


def _written(path: pathlib.Path, protocol: str) -> ast.ClassDef:
    return next(
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef) and node.name == protocol
    )


def _after_self(node: ast.FunctionDef) -> str:
    """A rung's parameters after `self`, and what it hands back, as text."""
    rendered = ast.parse(ast.unparse(node)).body[0]
    if not isinstance(rendered, ast.FunctionDef):  # pragma: no cover - every rung here is a function
        raise TypeError(node.name)
    rendered.args.args = rendered.args.args[1:]
    rendered.body = [ast.Expr(value=ast.Constant(value=...))]
    rendered.decorator_list = []
    return ast.unparse(rendered)


class TestWhatEachAssertionHandsBack:
    """The return side, which every gate above leaves alone: they measure what a rung accepts.

    Flattened from the runtime, every pivot but `decoded_as_json()` said the subject came back, because the
    mixins write them `-> Self`.  `raises().when_called_with().matches()` was refused on an enum class that
    runs it, and `extracting()` kept a container's type over the list it hands back.
    """

    def test_every_pivot_is_declared_rather_than_left_to_the_hook(self) -> None:
        """`__getattr__` answers a name the façade lacks with `Self`, the very claim this class refuses."""
        missing = sorted(_PIVOTS - set(_declarations()) - _attributes())
        assert_that(missing).described_as("a pivot the hook would answer as handing the subject back").is_empty()

    def test_no_pivot_says_it_hands_the_subject_back(self) -> None:
        """Every rung of every pivot, except in a ladder the builder itself declares.

        There the rung saying `Self` is the one a value the pivot refuses reaches, and
        `TestTheLaddersTheBuilderDeclares` holds it rung for rung.  Anywhere else it is a flattened `-> Self`.
        """
        ladders = set(_builder_ladders())
        claiming = sorted(
            f"{name} -> {ast.unparse(node.returns)}"
            for name, nodes in _declarations().items()
            if name in _PIVOTS and name not in ladders
            for node in nodes
            if ast.unparse(node.returns) in _KEEPS_THE_SUBJECT
        )
        assert_that(claiming).described_as("a pivot the façade says hands the subject back").is_empty()

    def test_the_call_family_lands_where_the_callable_view_lands(self) -> None:
        """Held against the view written by hand, rung for rung, with only its return type opened to `Any`.

        `_Callable` names no return, so `_P_co` has nothing to bind to on the façade, and the receiver is
        restricted there where the view needs no restriction: those two differences and no others.
        """
        view = _written(_VIEWS, "_CallableAssertion")
        setters = sorted(name for name, kind in WITHOUT_A_VERDICT.items() if kind == CONFIGURES)
        on_the_view = {
            name: [
                _after_self(item).replace("_P_co", "Any")
                for item in view.body
                if isinstance(item, ast.FunctionDef) and item.name == name
            ]
            for name in setters
        }
        on_the_facade = {name: [_after_self(node) for node in _declarations().get(name, [])] for name in setters}
        assert_that(on_the_facade).described_as("an expectation set on a capable callable").is_equal_to(on_the_view)
        receivers = {ast.unparse(node.args.args[0].annotation) for name in setters for node in _declarations()[name]}
        assert_that(receivers).is_equal_to({"_CapableAssertion[_Callable]"})

    def test_a_call_with_no_expectation_is_refused_where_it_is_written(self) -> None:
        """Left out, `__getattr__` would answer it, and the run time refuses it until an expectation is set."""
        declared = {
            item.target.id: ast.unparse(item.annotation)
            for item in _written(pathlib.Path(_capable_typing.__file__), "_CapableAssertion").body
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
        }
        assert_that(declared).contains_entry({"when_called_with": "_NoExpectationOnAChain"})


def _umbrella() -> dict[str, set[str]]:
    """`{shape: its members}` for every shape `_CapableT` is bound to, which is what the umbrella claims a value by."""
    tree = ast.parse(_VIEWS.read_text(encoding="utf-8"))
    bound = next(
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and node.args and ast.unparse(node.args[0]) == "'_CapableT'"
        for keyword in node.keywords
        if keyword.arg == "bound"
    )
    # the bound is a name of its own, which the twins restrict a rung to where it lands where it stood
    union = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and [ast.unparse(target) for target in node.targets] == [ast.unparse(bound)]
    )
    shapes = {name.id for name in ast.walk(union) if isinstance(name, ast.Name)}
    return {
        node.name: {
            item.name if isinstance(item, ast.FunctionDef) else ast.unparse(item.target)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AnnAssign))
        }
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name in shapes
    }


def _looked_up(self: object, key: object) -> object:
    """A key and the older sequence protocol at once, ending in `IndexError` so a walk through it stops."""
    if key == 0:
        return {"id": 1}
    if key == "id":
        return 1
    raise IndexError(key)


def _returning(self: object, *args: object, **kwargs: object) -> object:
    return 42


_CLAIMS: dict[str, dict[str, object]] = {
    # the elements are records, so `extracting()` has a field to hand back and not only a refusal
    "_CollectionShape": {"__iter__": lambda self: iter(({"id": 1},))},
    "_HttpResponseShape": {
        "status_code": 200,
        "headers": {"content-type": "application/json"},
        "json": lambda self: {"id": 1},
    },
    "_ModelShape": {"model_dump": lambda self, *args, **kwargs: {"id": 1}},
    "_DataclassShape": {"__dataclass_fields__": {}},
    "_MappingLikeShape": {"keys": lambda self: ("id",), "__getitem__": _looked_up},
}
"""One stand-in per shape the umbrella is bound to, keyed by that shape, so a drawn value is always one it claims."""

_EXTRAS: dict[str, dict[str, object]] = {
    "sized": {"__len__": lambda self: 1},
    "searched": {"__contains__": lambda self, item: True},
    "valued": {"values": lambda self: (1,)},
    # ordered as the number one, so a relation can pass and not only fail
    "ordered": {
        "__lt__": lambda self, other: 1 < other,
        "__gt__": lambda self, other: 1 > other,
        "__le__": lambda self, other: 1 <= other,
        "__ge__": lambda self, other: 1 >= other,
    },
    "converts": {"__float__": lambda self: 1.0},
    "indexes": {"__index__": lambda self: 1},
    "a path": {"__fspath__": lambda self: "."},
}
"""What the restricted assertions read on top of a claim, carried in any combination."""


@functools.cache
def _shape(carried: frozenset[str], call: Callable[..., object] | None, registered: bool) -> type:
    """One class per combination, so a shape drawn again is neither rebuilt nor registered again."""
    members: dict[str, object] = {}
    for capability in sorted(carried):
        members.update(_CLAIMS.get(capability) or _EXTRAS[capability])
    if call is not None:
        members["__call__"] = call
    drawn = type("_Drawn", (), members)
    if registered:
        numbers.Real.register(drawn)
    return drawn


class _Relative:
    """An argument read off the value asked, since most verdicts pass only when asked about the value itself."""

    def __init__(self, shown: str, read: Callable[[object], object]) -> None:
        self.shown = shown
        self.read = read

    def __repr__(self) -> str:
        return self.shown


_ASKED_WITH = [
    *_ARGUMENTS,
    (1,),
    (2,),
    (lambda item: False,),
    (_Relative("<the value>", lambda value: value),),
    (_Relative("<its type>", type),),
]


def _resolved(arguments: tuple[object, ...], value: object) -> tuple[object, ...]:
    return tuple(one.read(value) if isinstance(one, _Relative) else one for one in arguments)


_REFUSALS = (AssertionFailure, TypeError, ValueError, LookupError, OSError, ImportError)
"""What asking answers with instead of a builder: a failed verdict, a refusal, a lookup the value's own
`__getitem__` stops, a path that is not there, and an optional library this cell does not install.
Anything else fails, which is how `UnorderableError` surfaced.  Judged by type and not by where it was
raised, so a bug raising one of these reads as a refusal: the claim here is what a builder hands back, not
that nothing crashes."""

_EXPECTATION_VIEWS = frozenset({"_ExpectedRaiseAssertion", "_ExpectedWarningAssertion", "_ExpectedCompletionAssertion"})
"""Views over the callable itself, `value` being the callable on `_CallableAssertion`."""


def _promise(returns: str) -> Callable[[object, object], bool] | None:
    """What a rung's return says about the value handed back, or `None` where it says nothing checkable."""
    if returns in _KEEPS_THE_SUBJECT or returns.split("[", 1)[0] in _EXPECTATION_VIEWS:
        return lambda handed, subject: handed is subject
    if returns.startswith("_ListAssertion["):
        return lambda handed, subject: isinstance(handed, list)
    return None


def _a_class(written: str) -> bool:
    """Whether *written* names a class at run time, which a shape protocol declared for checkers does not."""
    module, _, name = written.strip().rpartition(".")
    found = vars(datetime).get(name) if module == "datetime" else vars(builtins).get(written.strip())
    return isinstance(found, type)


def _asks_a_type(node: ast.FunctionDef) -> bool:
    """Whether a rung is keyed on a class, which no value reaching the umbrella is: each has an overload above it."""
    receiver = node.args.args[0].annotation if node.args.args else None
    if not isinstance(receiver, ast.Subscript):
        return False
    return all(_a_class(part) for part in ast.unparse(receiver.slice).split("|"))


_WRITES = frozenset({"snapshot", "matches_inline", "matches_contract_snapshot"})
"""Asked with a generic argument these record a snapshot or rewrite the calling source."""


def _promised() -> dict[str, Callable[[object, object], bool]]:
    """Every name whose rungs all make one checkable promise, the writers and the type-keyed left out."""
    promised: dict[str, Callable[[object, object], bool]] = {}
    for name, nodes in _declarations().items():
        if name.startswith("_") or name in _WRITES or any(_asks_a_type(node) for node in nodes):
            continue
        returns = {ast.unparse(node.returns) for node in nodes}
        if len(returns) == 1 and (promise := _promise(returns.pop())) is not None:
            promised[name] = promise
    return promised


_PROMISED = _promised()


class _Emptied:
    """A claimed value holding nothing, keys included, which is what a verdict about absence passes on."""

    def __iter__(self) -> Iterator[object]:
        return iter(())

    def __len__(self) -> int:
        return 0

    def keys(self) -> tuple[()]:
        return ()

    def values(self) -> tuple[()]:
        return ()

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)


_FLOOR = [
    _shape(frozenset(_CLAIMS) | frozenset(_EXTRAS), _returning, True)(),
    *(_shape(frozenset({claim}), None, False)() for claim in sorted(_CLAIMS)),
    _Emptied(),
]
"""A value carrying everything, each claim alone, and one holding nothing: a verdict may need a capability absent."""

_REFUSED = object()


def _asked(name: str, subject: object, arguments: tuple[object, ...]) -> object:
    """What asking hands back, or `_REFUSED` for an answer that is not a builder."""
    try:
        return getattr(assert_that(subject), name)(*_resolved(arguments, subject))
    except _REFUSALS:
        return _REFUSED


_NOT_HELD = frozenset(
    {
        # a value that is none, zero, a NaN, infinite or negative, which no claimed value built here is
        "is_none",
        "is_zero",
        "is_nan",
        "is_inf",
        "is_negative",
        # an operand the value does not hold or sits far from, where `__contains__` answers yes to everything
        "contains_none_of",
        "contains_any_of",
        "contains_sequence",
        "contains_duplicates",
        "is_not_close_to",
        # a document, a schema, a spec or a frame to compare against
        "has_json_path",
        "does_not_have_json_path",
        "matches_json_schema_from_file",
        "conforms_to_openapi",
        "is_frame_equal",
        # a path that is absent, a directory, named something, or under a directory that is not itself
        "does_not_exist",
        "is_directory",
        "is_named",
        "is_child_of",
        # a caught exception group
        "contains_error",
        "does_not_contain_error",
        "matches_error_tree",
        # text, or a class, as the value itself
        "is_unicode",
        "contains_ignoring_case",
        "is_subclass_of",
        # two operands of different kinds, an iterable and a predicate over pairs
        "zip_satisfies",
        # the failure entry point, which raises whatever it is asked
        "error",
    }
)
"""Promising names the property does not hold, because nothing on the floor answers them, with what each would need."""

_HELD = {name: promise for name, promise in _PROMISED.items() if name not in _NOT_HELD}
"""What the property holds: a promise it watches kept at least once on the floor, and never one it cannot."""


def test_the_floor_reaches_every_name_the_property_holds() -> None:
    """The floor counts answers, not attempts, so a name nothing on it answers is not held rather than held vacuously.

    Checked in both directions: a name the floor starts to reach has to move into the property, and one it
    stops reaching has to be excused here by name.  A name needing a library this cell lacks is left out of
    both sides, so the record reads the same wherever it runs: the array pair has no numpy on 3.15.
    """
    reached: set[str] = set()
    unavailable: set[str] = set()
    for subject in _FLOOR:
        for name in _PROMISED:
            for arguments in _ASKED_WITH:
                try:
                    getattr(assert_that(subject), name)(*_resolved(arguments, subject))
                # a refusal per question, and the next question may still be answered
                except ImportError:  # noqa: PERF203
                    unavailable.add(name)
                except _REFUSALS:
                    continue
                else:
                    reached.add(name)
    assert_that(sorted(set(_PROMISED) - reached - unavailable)).described_as(
        "promised and never answered on the floor"
    ).is_equal_to(sorted(_NOT_HELD - unavailable))


def test_the_claims_are_the_shapes_the_umbrella_is_bound_to() -> None:
    """A drawn value is one the umbrella claims while every claim carries a whole shape and every shape has one."""
    shapes = _umbrella()
    assert_that(sorted(_CLAIMS)).is_equal_to(sorted(shapes))
    short = {
        shape: sorted(members - set(_CLAIMS[shape]))
        for shape, members in shapes.items()
        if members - set(_CLAIMS[shape])
    }
    assert_that(short).described_as("a claim missing a member of its shape").is_empty()


_subjects = st.builds(
    lambda claims, extras, call, registered: _shape(claims | extras, call, registered)(),
    st.frozensets(st.sampled_from(sorted(_CLAIMS)), min_size=1),
    st.frozensets(st.sampled_from(sorted(_EXTRAS))),
    st.sampled_from([None, _returning]),
    st.booleans(),
)


def _pinning_the_floor(test: Callable[..., None]) -> Callable[..., None]:
    """Every name held, with every question, on every value of the floor, whatever the search draws."""
    for subject in _FLOOR:
        for name in _HELD:
            for arguments in _ASKED_WITH:
                test = example(name=name, subject=subject, arguments=arguments)(test)
    return test


@settings(deadline=None)
@_pinning_the_floor
@given(name=st.sampled_from(sorted(_HELD)), subject=_subjects, arguments=st.sampled_from(_ASKED_WITH))
def test_what_the_facade_promises_is_what_comes_back(name: str, subject: object, arguments: tuple[object, ...]) -> None:
    """A rung's promise about the value, held against the runtime on any value the umbrella claims.

    The subject itself where the rung says `Self` or lands on an expectation view, a list where it lands on
    the list view.  The runtime half of the static gates above: those trust the operation register, which
    is derived from `self.builder(...)` calls, and a pivot written any other way would slip past them.
    Found on its first run what the report did not name, `extracting()`, `filtered_on()` and
    `flat_mapped()`.  A crash is not a refusal: counting what it swallowed found `UnorderableError`
    escaping the four range assertions, which is why only `_REFUSALS` count as one.
    """
    handed_back = _asked(name, subject, arguments)
    if handed_back is _REFUSED:
        return
    assert_that(_HELD[name](handed_back.val, subject)).described_as(
        f"{name}{arguments!r} handed back {handed_back.val!r}"
    ).is_true()
