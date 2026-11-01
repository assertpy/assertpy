"""Whether a value is a NaN or an infinity is asked in four helpers, and a value becomes a float in none.

The same defect shipped three times.  A site asked the question with `math.isnan` on the value itself,
which converts it to a float first, so a bignum, a huge `Fraction` or a signalling `Decimal` raised out
of the conversion instead of being answered.  The fix guarded `numeric.py`.  Then the tolerance path
turned up, screening a `float` NaN only, and then two validators still calling `math.isnan(tolerance)`.
Each fix was right where it landed and the next site was never looked at, so the rule is stated over
the source instead.

Outside `_HELPERS` the package may not:

- call `isnan`, `isinf`, `isfinite` or `isclose` from `math`, `cmath` or `numpy`, however imported,
- import any of them, `decimal` or `builtins` with `*`,
- convert with `float(...)` or `__float__`, unless the argument is a literal,
- ask `Decimal` itself whether a value is a NaN or an infinity,
- compare a value with itself, which is the NaN idiom, or with an infinity or NaN constant.

A guard in front does not excuse a site.  `isinstance(value, float) and math.isnan(value)` converts
nothing, and it is exactly the screen a `Decimal` NaN walked past.  A site that is right to ask in place
says why in `_EXCUSED`, a question only `float` has or text being parsed, and an excuse that stops
matching fails.

The walk is syntactic, so a call through a variable slips past it, and so does a constant built any way
but its literal spellings (a name such as `math.inf`, a literal such as `1e999`, or `float` and `Decimal`
given a string): `float.fromhex`, `Decimal.from_float` and the tuple form are not read.  An import binds
its name for the whole module, every import of it at once, so a name shadowing a module is flagged
rather than missed.  `test_hostile_values.py` covers a value asked about its own kind, and the number
properties are the sweeps this approximates.
"""

from __future__ import annotations

import ast
import cmath
import decimal
import functools
import math
import pathlib
import textwrap

from assertpy import assert_that

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "assertpy"

_HELPERS = frozenset(
    {
        ("_engine/_compare.py", "_is_nan"),
        ("_engine/_compare.py", "_is_infinite"),
        ("_engine/_compare.py", "_non_finite"),
        ("_engine/_ordering.py", "nan_operand"),
    }
)

_EXCUSED = {
    ("errors.py", "_json_native", "math.isfinite(value)"): (
        "whether json can write this float, a question only float has, and errors.py imports nothing of ours"
    ),
    ("_inline.py", "is_literalable", "math.isfinite(value)"): (
        "whether pprint writes this exact float as source, which only its nan and inf fail"
    ),
    ("async_assertions.py", "_seconds", "float(timeout)"): (
        "renders a timeout already added to a float deadline, where a bignum or a Decimal refuses"
    ),
    ("async_assertions.py", "_duration", "float(value)"): (
        "turns a timeout or interval, already known to be a Real, into the float the poll loop adds and sleeps"
    ),
    ("pytest_plugin.py", "_poll_threshold", "float(written)"): "parses ini text, not a value under test",
    ("behave_matchers.py", "_positive_float", "float(text)"): "parses step text behave matched as digits",
    **dict.fromkeys(
        (
            ("_engine/_compare.py", "plainly_within", "actual != actual"),
            ("_engine/_compare.py", "plainly_within", "expected != expected"),
            ("_engine/_compare.py", "plainly_within", "actual in (math.inf, -math.inf)"),
            ("_engine/_compare.py", "plainly_within", "expected in (math.inf, -math.inf)"),
        ),
        "its operands are exact ints and floats, the caller's condition, so the NaN and the infinity are float's",
    ),
}

_NUMBER_MODULES = frozenset({"math", "cmath", "numpy"})
_WATCHED_MODULES = _NUMBER_MODULES | {"decimal", "builtins"}
_FLOAT = frozenset({"float", "builtins.float"})

_ASKED = frozenset(
    {f"{module}.{name}" for module in _NUMBER_MODULES for name in ("isnan", "isinf", "isfinite", "isclose")}
    | {f"decimal.Decimal.{name}" for name in ("is_nan", "is_snan", "is_qnan", "is_infinite", "is_finite")}
)
_SPECIAL_CONSTANTS = frozenset({f"{module}.{name}" for module in _NUMBER_MODULES for name in ("inf", "nan")})


def _bindings(tree: ast.Module) -> dict[str, frozenset[str]]:
    """Every target an import anywhere in the module binds each local name to."""
    bound: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _WATCHED_MODULES:
                    bound.setdefault(alias.asname or alias.name, set()).add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in _WATCHED_MODULES:
            for alias in node.names:
                bound.setdefault(alias.asname or alias.name, set()).add(f"{node.module}.{alias.name}")
    return {name: frozenset(targets) for name, targets in bound.items()}


def _literal(node: ast.expr) -> bool:
    return isinstance(node.operand if isinstance(node, ast.UnaryOp) else node, ast.Constant)


def _builds_special(kind: str, text: str) -> bool:
    """Whether ``float(text)`` or ``Decimal(text)`` is a NaN or an infinity, asked of the type that builds it."""
    try:
        built = float(text) if kind in _FLOAT else decimal.Decimal(text)
    except (ValueError, ArithmeticError):
        return False
    return not math.isfinite(built) if isinstance(built, float) else not built.is_finite()


def _with_itself(node: ast.Call) -> bool:
    """`float.__ne__(value, value)` or `value.__ne__(value)`: the NaN idiom spelled as a call."""
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in ("__eq__", "__ne__"):
        return False
    sides = node.args if len(node.args) == 2 else [node.func.value, *node.args]
    return len(sides) == 2 and ast.dump(sides[0]) == ast.dump(sides[1])


class _Walk(ast.NodeVisitor):
    """Every special-number question one module asks, with the function it is asked in."""

    def __init__(self, tree: ast.Module) -> None:
        self._bound = _bindings(tree)
        self._scope: list[str] = []
        self.found: list[tuple[str, int, str]] = []

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node)

    def _dotted(self, node: ast.expr) -> frozenset[str]:
        """Every dotted name the expression may stand for: the name as written and each import of it."""
        if isinstance(node, ast.Name):
            return self._bound.get(node.id, frozenset()) | {node.id}
        if isinstance(node, ast.Attribute):
            return frozenset(f"{prefix}.{node.attr}" for prefix in self._dotted(node.value))
        return frozenset()

    def _record(self, node: ast.expr) -> None:
        self.found.append((".".join(self._scope) or "<module>", node.lineno, ast.unparse(node)))

    def _special(self, node: ast.expr) -> bool:
        if isinstance(node, ast.UnaryOp):
            return self._special(node.operand)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return any(self._special(element) for element in node.elts)
        if isinstance(node, ast.Call):
            kinds = self._dotted(node.func) & (_FLOAT | {"decimal.Decimal"})
            written = [*node.args[:1], *(keyword.value for keyword in node.keywords if keyword.arg == "value")]
            return any(
                isinstance(text, ast.Constant) and isinstance(text.value, str) and _builds_special(kind, text.value)
                for text in written
                for kind in kinds
            )
        if isinstance(node, ast.Constant) and isinstance(node.value, (float, complex)):
            return not cmath.isfinite(node.value)
        return bool(self._dotted(node) & _SPECIAL_CONSTANTS)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """A wildcard import of a number module binds names the walk cannot see, so it is refused."""
        if node.module in _WATCHED_MODULES and any(alias.name == "*" for alias in node.names):
            self._record(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._dotted(node.func)
        converts = bool(callee & _FLOAT) and not all(_literal(argument) for argument in node.args)
        dunder = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if callee & _ASKED or converts or dunder == "__float__" or _with_itself(node):
            self._record(node)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left, *node.comparators]
        with_itself = (
            len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Eq, ast.NotEq))
            and ast.dump(node.left) == ast.dump(node.comparators[0])
        )
        if with_itself or any(self._special(operand) for operand in operands):
            self._record(node)
        self.generic_visit(node)


@functools.cache
def _questions(package: pathlib.Path) -> tuple[tuple[str, str, int, str], ...]:
    """``(path, function, line, source)`` for every question asked under *package*, helpers included."""
    found: list[tuple[str, str, int, str]] = []
    for source in sorted(package.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        walk = _Walk(tree)
        walk.visit(tree)
        path = source.relative_to(package).as_posix()
        found += [(path, function, line, text) for function, line, text in walk.found]
    return tuple(found)


def _unexcused(questions: tuple[tuple[str, str, int, str], ...]) -> list[str]:
    return [
        f"assertpy/{path}:{line} {function}: {text}"
        for path, function, line, text in questions
        if (path, function) not in _HELPERS and (path, function, text) not in _EXCUSED
    ]


def test_no_special_number_question_is_asked_outside_the_helpers() -> None:
    """Route a new site through `_is_nan`, `_is_infinite`, `_non_finite` or `nan_operand`.

    Excuse it instead only when the question is about `float` alone, as a JSON or a source literal is,
    and say so in one line.  An answer for floats is an answer that a `Decimal` NaN walks past.
    """
    assert_that(_unexcused(_questions(_PACKAGE))).described_as("special-number questions asked in place").is_empty()


def test_every_helper_still_asks_the_question() -> None:
    """An exemption for a helper that no longer asks would hide a site renamed into its place."""
    asking = {(path, function) for path, function, _, _ in _questions(_PACKAGE)}
    assert_that(sorted(_HELPERS - asking)).described_as("helpers the walk found no question in").is_empty()


def test_every_excuse_still_matches_a_site() -> None:
    """An excuse outliving its site would silently cover the next one written under that name."""
    asked = {(path, function, text) for path, function, _, text in _questions(_PACKAGE)}
    assert_that(sorted(set(_EXCUSED) - asked)).described_as("excuses for sites that are gone").is_empty()


_SPELLINGS = textwrap.dedent(
    """
    import math
    import cmath as c
    import numpy as np
    import decimal
    import builtins
    from builtins import float as to_float
    from math import isinf as infinite, inf
    from decimal import Decimal

    def asked(value, other):
        math.isnan(value)  # asked
        infinite(value)  # asked
        c.isfinite(value)  # asked
        np.isclose(value, other)  # asked
        float(value)  # asked
        builtins.float(value)  # asked
        to_float(value)  # asked
        value == builtins.float("inf")  # asked
        value.__float__()  # asked
        decimal.Decimal.is_nan(value)  # asked
        Decimal.is_snan(value)  # asked
        value != value  # asked
        float.__ne__(value, value)  # asked
        value.__eq__(value)  # asked
        value == math.inf  # asked
        value in (1, -inf)  # asked
        value < float("-Infinity")  # asked
        value == Decimal("sNaN")  # asked
        value != decimal.Decimal("-sNaN4_2")  # asked
        value == Decimal("In_f")  # asked
        value == 1e999  # asked
        value == Decimal(value="NaN")  # asked
        value < decimal.Decimal(value="Infinity")  # asked
        value > -1e999j  # asked
        other.attr == other.attr  # asked

    def star():
        from math import *  # asked

    def one(value):
        import decimal as n
        n.Decimal.is_nan(value)  # asked

    def two(value):
        import math as n
        n.isnan(value)  # asked

    def three():
        from numpy import float32 as float

    def four(value):
        float(value)  # asked

    def not_asked(value, other):
        from os.path import *
        float("nan")
        value == Decimal("NaNa")
        value == Decimal(value="1")
        value == float("NaN_42")
        float(-1.5)
        float()
        math.inf
        value.is_nan()
        value != other
        value == 1.0
        value < 1e308
        math.floor(value)
    """
)


def test_the_walk_reads_every_spelling_of_the_question() -> None:
    """Without this, an alias the walk stopped resolving would pass the gate over any package."""
    tree = ast.parse(_SPELLINGS)
    walk = _Walk(tree)
    walk.visit(tree)
    marked = [number for number, line in enumerate(_SPELLINGS.splitlines(), 1) if line.endswith("# asked")]
    assert_that(sorted({line for _, line, _ in walk.found})).is_equal_to(marked)
