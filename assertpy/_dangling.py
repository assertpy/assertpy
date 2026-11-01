"""Find `assert_that(...)` statements that assert nothing.

Two shapes pass every test runner in silence:

    assert_that(items)              # a builder is built and thrown away
    assert_that(items).is_empty     # the assertion is looked up and never called

Neither can happen with a bare ``assert``, so a fluent API owes its users a way to catch them.  The
second shape is already reported by ruff's B018 (useless attribute access); the first is not reported
by anything, because a call may have side effects and no linter can know this one does not.

The check is static and runs at collection.  A runtime version was tried first and rejected: marking
the builder from a wrapper adds a stack frame, which `snapshot()` / `matches_inline()` then had to
walk past to find the line they key and rewrite (see `_require_caller` in snapshot.py).  Reading the
source costs nothing at runtime and cannot shift a frame.

What it deliberately does not flag:

* a builder bound to a name (`b = assert_that(x)`), because whether `b` is used later is not a
  question about this statement, and ruff's F841 answers it when the answer is never;
* `assert_conforms()`, `fail()`, `soft_fail()`, which assert on their own rather than returning a
  builder, so a bare call to them is correct usage.

A chain ending on a pivot or a configurer is the same defect wearing a longer tail:
``assert_that(load).raises(ValueError)`` never calls anything, and ``assert_that(rows).extracting("id")``
throws the extracted value away.  Both were left out while the set of operations that reach no verdict
was only a runtime property; `assertpy/_engine/_operations.py` states it now, and a gate keeps it in
step with the source, so reading it here cannot rot.

An ``assert`` in front reads the chain instead of discarding it, and a builder and a bound method are
both truthy, so ``assert assert_that(items).is_empty`` is green on every value.  Neither B018 nor
coverage sees that one: the value is consumed rather than dropped, and the line does run.  What the
``assert`` reads is the whole question, since ``assert assert_that(x).val`` tests that value instead,
and the register names the members that hand it back.
"""

from __future__ import annotations

import ast
import io
import tokenize
from typing import TYPE_CHECKING, Final, NamedTuple

from . import _renamed
from ._engine._operations import (
    ALSO_ASSERTS,
    CONFIGURES,
    DESCRIBES,
    HANDS_THE_SUBJECT_BACK,
    POLLS,
    TRANSFORMS,
    WITHOUT_A_VERDICT,
)

if TYPE_CHECKING:
    import pathlib

__tracebackhide__ = True

# the builder factories and only those: everything else either asserts by itself or is not an entry point
_ENTRY: Final = frozenset({"assert_that", "assert_warn"})
_PACKAGES: Final = frozenset({"assertpy", "assertpy2"})

ALLOW_MARKER: Final = "assertpy: allow-dangling"
"""Comment that silences one statement, for the cases where asserting nothing is the point.

They exist and they are not mistakes: a benchmark measuring what building a builder costs, a test of
this library's own machinery, a snippet written to demonstrate the shape.  Without a way to say so, the
only answer to one deliberate line is turning the whole check off, and a check that has to be switched
off wholesale is a check nobody runs.
"""
_OLD_MARKER: Final = _renamed.old_name(ALLOW_MARKER)

_NO_ASSERTION: Final = "{name}() builds a builder here and asserts nothing"
"""Template rather than a sentence: the message names the call as the reader wrote it.

A project that registered its own wrapper reads `check(1)` on the offending line, and being told about
`assert_that()` there costs a moment of "that is not what my code says" on every finding.
"""
_NOT_CALLED: Final = "assertion is looked up and never called (missing parentheses)"
_ENDS_ON: Final = {
    CONFIGURES: "{name}() only sets an expectation here, and nothing calls it",
    TRANSFORMS: "{name}() hands back another value here, and nothing asserts on it",
    DESCRIBES: "{name}() only sets the failure description here, and asserts nothing",
    POLLS: "{name}() starts a polling chain here, and no assertion follows it",
}
"""What to say about a chain ending on an operation that reaches no verdict, one sentence per kind."""

_NO_VERDICT: Final = {name: kind for name, kind in WITHOUT_A_VERDICT.items() if name not in ALSO_ASSERTS}
_NOT_AWAITED: Final = "eventually() chain is never awaited, so nothing is polled (missing await)"
_UNDER_ASSERT: Final = "nothing here asserts: assert reads the builder, whose truth says nothing about the value"
"""What to say about a dangling chain an `assert` reads.

The wrapper turns every shape below into the same defect and a worse one: a builder, a proxy and a
bound method are all truthy, so the line is green whatever the value is, and it reads as if it
asserted.  Neither ruff nor coverage sees it, since the value is consumed and the line does run.

The sentence stops at "says nothing" rather than promising the line passes, because a few of the
builder's own fields are falsy by default and turn the line red instead.  Green or red, neither
outcome was decided by the value under test.
"""


class Finding(NamedTuple):
    """One offending statement.

    ``path`` and ``lineno`` locate it and ``message`` says which shape it is.  ``scope`` is the chain of
    names around it, ``("TestOne", "test_same")``, so the report reaches the test that contains the line
    rather than another test of the same name: under ``filterwarnings = ["error"]`` the difference is
    which test goes red, and with two same-named methods it was the difference between a finding being
    reported and being dropped.

    Empty for a statement at module scope, which belongs to no test at all.
    """

    path: str
    lineno: int
    message: str
    scope: tuple[str, ...]


class _Bindings(NamedTuple):
    """The names in one module that reach an entry point: bare (`assert_that`) and dotted (`ap.`)."""

    direct: frozenset[str]
    modules: frozenset[str]

    def __bool__(self) -> bool:
        return bool(self.direct or self.modules)


class _Survey(NamedTuple):
    """Everything the checks need out of the tree, gathered in one walk.

    Six separate walks were measured before this: resolving the entry points, the names the module
    rebinds, the same two again for `pytest`, the blocks that demand a raise, and the statements that
    consume a builder.  Each is cheap on its own and the tree is walked whole every time, which came to
    624 ms over this repository's own 97 test modules against 166 ms of parsing.

    `statements` carries the scope each one sits in, as the chain of names around it.  A chain rather
    than one name because a bare name does not identify a test: two classes in one file may each define
    `test_same`, and matching on the name alone handed both findings to whichever ran first.
    """

    rebound: frozenset[str]
    imports: tuple[ast.Import | ast.ImportFrom, ...]
    blocks: tuple[ast.With | ast.AsyncWith, ...]
    statements: tuple[tuple[ast.Expr | ast.Assert, tuple[str, ...]], ...]


def _survey(tree: ast.Module) -> _Survey:
    """Walk once, keeping the four things the checks ask about.

    The walk is its own rather than `ast.walk` because the scope chain has to be carried down, and
    `ast.walk` hands back a flat stream with no way to know what encloses what.

    Two statements consume a builder on the spot.  An expression statement discards the value, and
    anywhere else it is bound, passed or returned, where whether *that* asserts is not a question about
    this statement.  An `assert` reads it for its truth, which a builder and a bound method answer the
    same way whatever the value is.
    """
    rebound: set[str] = set()
    imports: list[ast.Import | ast.ImportFrom] = []
    blocks: list[ast.With | ast.AsyncWith] = []
    statements: list[tuple[ast.Expr | ast.Assert, tuple[str, ...]]] = []
    stack: list[tuple[ast.AST, tuple[str, ...]]] = [(tree, ())]
    while stack:
        node, scope = stack.pop()
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                rebound.add(child.name)
                inner = (*scope, child.name)
            elif isinstance(child, ast.Expr | ast.Assert):
                statements.append((child, scope))
            elif isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Store):
                    rebound.add(child.id)
            elif isinstance(child, ast.arg):
                rebound.add(child.arg)
            # merging the branches is what ruff asks and a checker rejects: only the separate one narrows the name
            elif isinstance(child, ast.ExceptHandler) and child.name:
                rebound.add(child.name)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                imports.append(child)
            elif isinstance(child, (ast.With, ast.AsyncWith)):
                blocks.append(child)
            stack.append((child, inner))
    return _Survey(frozenset(rebound), tuple(imports), tuple(blocks), tuple(statements))


def _bindings(survey: _Survey, extra: frozenset[str] = frozenset()) -> _Bindings:
    """Resolve how this module spells the entry points, `as` aliases and star imports included.

    A module that never imports one is skipped whole: a user function of their own named
    `assert_that` must not be reported.

    ``extra`` holds the names a project declared for its own wrapper around `assert_that`.  Those come
    from the project rather than from here, so they are matched whatever module they are imported from,
    and only through `from ... import`: a wrapper reached as `helpers.check(...)` is not recognised, and
    neither is a local `def check` in a module that never imported one.  Requiring the import is the
    whole guard against claiming somebody else's identically named function.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    for node in survey.imports:
        if isinstance(node, ast.ImportFrom):
            ours = (node.module or "").split(".")[0] in _PACKAGES
            for alias in node.names:
                if alias.name == "*" and ours:
                    direct |= _ENTRY  # the docs' own preamble; a star import binds every entry point
                elif alias.name in extra or (ours and alias.name in _ENTRY):
                    direct.add(alias.asname or alias.name)
        else:
            for alias in node.names:
                if alias.name.split(".")[0] in _PACKAGES:
                    modules.add(alias.asname or alias.name.split(".")[0])
    shadowed = survey.rebound
    return _Bindings(frozenset(direct) - shadowed, frozenset(modules) - shadowed)


def _entry_call(node: ast.expr, bindings: _Bindings) -> str | None:
    """The call's name as written, for `assert_that(...)` however this module spells it, else ``None``.

    The name comes back rather than a flag so the report can quote the reader's own spelling, which is
    the only one they can search for.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id if func.id in bindings.direct else None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        reaches = func.attr in _ENTRY and func.value.id in bindings.modules
        return f"{func.value.id}.{func.attr}" if reaches else None
    return None


def _reaches_entry(node: ast.expr, bindings: _Bindings) -> bool:
    """True when an attribute chain bottoms out in an entry call, however deep it is nested.

    `assert_that(x).is_equal_to` is one hop, `assert_that(x).not_.is_none` is two, and a chain that
    starts anywhere else (`self.helper.attr`) is none.
    """
    current: ast.expr = node
    while True:
        if _entry_call(current, bindings):
            return True
        if isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Attribute):
            current = current.value
        else:
            return False


def _runs(node: ast.expr, name: str) -> bool:
    """True when an attribute chain calls *name* anywhere along it."""
    current: ast.expr = node
    while True:
        if isinstance(current, ast.Call):
            if isinstance(current.func, ast.Attribute) and current.func.attr == name:
                return True
            current = current.func
        elif isinstance(current, ast.Attribute):
            current = current.value
        else:
            return False


def _tail(node: ast.expr) -> str | None:
    """The name a statement ends on when that name reaches no verdict, else ``None``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _NO_VERDICT:
        return node.func.attr
    return None


def _reads_a_verdict_field(node: ast.Attribute) -> bool:
    """Whether the attribute reads a field off a verdict rather than leaving an assertion uncalled.

    Both sit behind `check()` and only the step before them tells them apart: `check().is_empty().passed`
    reads a field of what the assertion decided, while `check().is_empty` is that assertion with its
    parentheses missing, which is the shape this whole check exists for.
    """
    if not _runs(node, "check") or not isinstance(node.value, ast.Call):
        return False
    called = node.value.func
    return not (isinstance(called, ast.Attribute) and called.attr == "check")


def _reads_a_truthy_chain(node: ast.expr, bindings: _Bindings) -> bool:
    """Whether `assert <node>` reads a chain that decided nothing.

    An attribute handing the subject back is excluded, since `assert assert_that(x).val` tests that
    value rather than leaving an assertion uncalled, and so is a verdict's own field.  Nothing else is:
    reading the builder's state asserts as little as reading a method does, and `logger` is truthy on
    every subject there is.

    A chain ending on a bare `check()` is left alone deliberately.  It is truthy and asserts nothing,
    but calling it a defect means deciding the name is ours, and a project may register an extension
    called `check` that asserts by itself.  A read attribute needs no such guess, since nothing was
    called at all.  Measured before deciding: no bare `check()` under an `assert` in 524 files across
    this suite, the fixture projects and a consuming framework.
    """
    if not _reaches_entry(node, bindings):
        return False
    if _entry_call(node, bindings) or _tail(node) or (_runs(node, "eventually") and not _closed(node)):
        return True
    if not isinstance(node, ast.Attribute):
        return False
    return node.attr not in HANDS_THE_SUBJECT_BACK and not _reads_a_verdict_field(node)


def _closed(node: ast.expr) -> bool:
    """True when the statement ends in a bare ``close()``, the discard the chain itself stays quiet about."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
        and not node.args
        and not node.keywords
    )


_DEMANDS_A_RAISE: Final = frozenset({"raises", "RaisesGroup"})
"""The `pytest` blocks that fail when their body reaches the end without raising.

`warns` and `deprecated_call` are deliberately not here.  They expect their body to finish normally,
so a chain that asserts nothing inside one is as silent as it would be anywhere else.  Measured: a
`pytest.warns` block whose body warns and then dangles passes.
"""


def _imported_as(survey: _Survey, package: str, wanted: frozenset[str]) -> tuple[frozenset[str], frozenset[str]]:
    """How this module spells names from *package*: bare after an import, and dotted through it.

    Resolved rather than matched on the bare name, for the reason `_bindings` resolves this library's
    own: a project helper that happens to be called `raises` or `fail` is not this one, and trusting
    the name alone would silence a real finding inside it.

    Three ways a spelling stops being the package's, all of them dropped:

    * the module rebinds it, which the survey's `rebound` set answers
    * another import binds the same spelling, where which one wins is the order they are written in
      rather than anything a name can be read for
    * it comes from somewhere else entirely

    What this cannot answer is a mutation at run time.  `pytest.raises = something_else` leaves the
    import reading exactly as it does here, and no static pass sees past that.  The boundary is the
    spelling, not the object it will hold.
    """
    direct: set[str] = set()
    modules: set[str] = set()
    elsewhere: set[str] = set()
    for node in survey.imports:
        if isinstance(node, ast.ImportFrom):
            ours = (node.module or "").split(".")[0] == package
            for alias in node.names:
                bound = alias.asname or alias.name
                (direct if ours and alias.name in wanted else elsewhere).add(bound)
        else:
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                (modules if alias.name.split(".")[0] == package else elsewhere).add(bound)
    taken = survey.rebound | elsewhere
    return frozenset(direct - taken), frozenset(modules - taken)


def _names_a_call(node: ast.expr, names: tuple[frozenset[str], frozenset[str]], wanted: frozenset[str]) -> bool:
    """Whether this call reaches one of *wanted* through the imports *names* resolved."""
    if not isinstance(node, ast.Call):
        return False
    direct, modules = names
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in wanted and isinstance(func.value, ast.Name) and func.value.id in modules
    return isinstance(func, ast.Name) and func.id in direct


def _demands_a_raise(node: ast.With | ast.AsyncWith, names: tuple[frozenset[str], frozenset[str]]) -> bool:
    """Whether this block fails when its body reaches the end quietly, and nothing else can end it.

    One item only.  A sibling manager gets its `__exit__` run after the body, so
    ``with pytest.raises(TypeError), Boom():`` is satisfied by `Boom` and the body never had to raise.
    """
    return len(node.items) == 1 and _names_a_call(node.items[0].context_expr, names, _DEMANDS_A_RAISE)


def _only_statement_of_a_raising_block(survey: _Survey) -> frozenset[int]:
    """The statements a `pytest.raises` block holds alone, by object identity.

    The exemption is this narrow because every wider one measured unsound.  A body of one statement
    leaves the argument with nothing to hide behind: that statement runs, and either it raises, which
    is what the test asserts, or the block itself raises `DID NOT RAISE`.

    What the block raises is where the promise stops.  An enclosing `try` that catches it, or a
    `finally` that returns, leaves the test green again, and no check reading one statement can see
    that.  The guarantee is about the immediate block, not about the test around it.

    Each condition is here for a shape that passed silently without it.  A second statement can supply
    the exception instead (`assert_that(x)` then `raise TypeError`), or make the chain unreachable
    (`raise TypeError` then the chain).  A sibling `with` item can raise from its own `__exit__`.

    Keyed on `id()` rather than on a line, because two statements share a line when they are written
    `assert_that(x); raise TypeError`, and exempting the line would exempt the chain as well.
    """
    names = _imported_as(survey, "pytest", _DEMANDS_A_RAISE)
    return frozenset(
        id(node.body[0]) for node in survey.blocks if len(node.body) == 1 and _demands_a_raise(node, names)
    )


def _marked_lines(source: str) -> frozenset[int]:
    """Line numbers whose *comment* carries the marker.

    Tokenised rather than searched for as text, which was the first implementation and silenced any
    statement holding the marker's own words in a string:
    ``assert_that("# assertpy: allow-dangling")`` reported nothing.  A test asserting on text that
    quotes the marker is exactly the kind of line a reader would never suspect of being exempt.

    A file that tokenises differently from how it parsed yields nothing rather than raising: the parse
    already succeeded, so the check goes on without the escape hatch instead of taking the run down.

    The text search in front is only to decide whether to tokenise at all.  A file without the marker's
    words anywhere cannot have it in a comment either, and two of this repository's 97 test modules
    carry one, so tokenising all 97 was 278 ms spent to read two.
    """
    if ALLOW_MARKER not in source and _OLD_MARKER not in source:
        return frozenset()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        comments = [one for one in tokens if one.type == tokenize.COMMENT]
    except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover - parse ran first
        return frozenset()
    return frozenset(one.start[0] for one in comments if ALLOW_MARKER in one.string or _OLD_MARKER in one.string)


def _silenced(statement: ast.stmt, marked: frozenset[int]) -> bool:
    """Whether the statement carries the marker on any of its own lines.

    Every line the statement spans counts, so the marker can sit at the end of a call broken over
    several lines, which is where a reader would naturally put it.
    """
    last = getattr(statement, "end_lineno", statement.lineno) or statement.lineno
    return any(line in marked for line in range(statement.lineno, last + 1))


def read_module(path: pathlib.Path) -> str:
    """A test module's text as the interpreter decodes it, which is what `findings` reads.

    The encoding a PEP 263 cookie or a BOM declares, found the way `tokenize` finds it, and UTF-8 where
    none is declared.  A byte that still does not decode is replaced rather than refused: 3.10 to 3.13
    import a module whose comment is not UTF-8, and reading it strictly aborted a whole run from the
    collection hook.  A comment's text is not something the check reads.
    """
    data = path.read_bytes()
    try:
        encoding = tokenize.detect_encoding(io.BytesIO(data).readline)[0]
    except SyntaxError:
        # a first line that is not UTF-8 and names no encoding, which 3.10 to 3.13 import all the same
        encoding = "utf-8"
    return data.decode(encoding, errors="replace")


def findings(source: str, path: str, extra_entries: frozenset[str] = frozenset()) -> list[Finding]:
    """Report the offending statements in one module's source.

    A statement carrying `ALLOW_MARKER` in a comment is left out: see that constant for why the
    escape hatch has to exist.

    ``extra_entries`` names a project's own wrappers around `assert_that`.  Only list a wrapper that
    *builds* something to assert on: a helper that asserts inside the call itself is not dangling when
    written as a statement, and listing it would report correct code.

    Raises:
        SyntaxError: if *source* does not parse; the caller decides whether that is its problem.
    """
    tree = ast.parse(source)
    survey = _survey(tree)
    bindings = _bindings(survey, extra_entries)
    if not bindings:
        return []
    marked = _marked_lines(source)
    alone = _only_statement_of_a_raising_block(survey)
    found: list[Finding] = []
    for statement, scope in survey.statements:
        if _silenced(statement, marked) or id(statement) in alone:
            continue
        if isinstance(statement, ast.Assert):
            if _reads_a_truthy_chain(statement.test, bindings):
                found.append(Finding(path, statement.lineno, _UNDER_ASSERT, scope))
            continue
        value = statement.value
        awaited = isinstance(value, ast.Await)
        while isinstance(value, ast.Await):  # `await assert_that(x).eventually()...` unwraps to the chain
            value = value.value
        if name := _entry_call(value, bindings):
            found.append(Finding(path, statement.lineno, _NO_ASSERTION.format(name=name), scope))
        elif isinstance(value, ast.Attribute) and _reaches_entry(value, bindings):
            found.append(Finding(path, statement.lineno, _NOT_CALLED, scope))
        elif not awaited and _runs(value, "eventually") and not _closed(value) and _reaches_entry(value, bindings):
            found.append(Finding(path, statement.lineno, _NOT_AWAITED, scope))
        elif (tail := _tail(value)) and _reaches_entry(value, bindings):
            found.append(Finding(path, statement.lineno, _ENDS_ON[_NO_VERDICT[tail]].format(name=tail), scope))
    return sorted(found, key=lambda finding: finding.lineno)
