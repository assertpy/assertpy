"""Execute the copy-paste code examples in the guide docs so they cannot silently rot.

The guarded pages are the ones whose python blocks are mostly runnable. Illustrative pseudo-context
blocks (``repo.find(42)``, a bare ``response``, ...) carry an HTML comment ``<!-- docs-guard: skip -->``
directly above their fence; that comment is invisible in the rendered site and tells this guard to
skip them. A new example is therefore either runnable or explicitly marked - it cannot slip through
unchecked.

``<!-- docs-guard: raises -->`` marks a block that shows what a failure looks like, so running it here
would fail the suite for doing what the page says it does. It is the mirror of test_docs_typing's
``untyped`` marker, and both exist rather than widening ``skip`` so that neither takes a block out of
both guards.

One test per page, blocks in document order. A guide is written as a narrative and its blocks build on
each other through whatever the library holds process-wide: `matchers.md` registers a matcher in one
block and removes it in another, which passed only while the suite happened to run them in that order.
Under a shuffling runner two seeds in four went red. A failure names the block it came from.
"""

from __future__ import annotations

import ast
import builtins
import datetime
import inspect
import io
import json
import logging
import pathlib
import re
import sys
import tokenize
import traceback
import types

import pytest

pytest.importorskip("pytest_examples")

from pytest_examples import CodeExample, EvalExample, find_examples

import assertpy
from assertpy import assert_that, errors, matchers
from tests.docs_fixtures import PAGE_FIXTURES, documented_pages

# pages this guard does not run, with reasons: a hand-kept list of pages to check stops growing quietly
UNRUN_DOCS = {
    "docs/concepts/type-safety.md": "several blocks are counter-examples that are supposed to fail",
    "docs/guides/testing.md": "the examples write snapshot files, which would be left behind in the repo",
    "docs/extending/custom-assertions.md": "the page registers extensions process-wide and shows a failing call",
    "docs/extending/integrations.md": "the behave blocks need a library the coverage cell must not install",
}

GUARDED_DOCS = documented_pages(UNRUN_DOCS)

# the public API minus submodules shadowing builtins, plus the stdlib names a later block assumes
DOC_NAMESPACE = {
    name: getattr(assertpy, name)
    for name in dir(assertpy)
    if not name.startswith("_") and not isinstance(getattr(assertpy, name), types.ModuleType)
}
DOC_NAMESPACE.update(datetime=datetime, re=re, json=json, logging=logging, Path=pathlib.Path)

SKIP_MARKERS = {
    "docs-guard: skip": "illustrative example, marked non-executable in the docs",
    "docs-guard: raises": "demonstrates a failure, marked as raising in the docs",
    "docs-guard: type-error": "counter-example, marked as rejected by a type checker",
}
# grouped by page in document order: a block may register a matcher the block below removes.
# Python state is fresh per block, so only what the library holds process-wide carries over
_PAGES = {doc: sorted(find_examples(doc), key=lambda example: example.start_line) for doc in GUARDED_DOCS}


def _skip_reason(example: CodeExample) -> str | None:
    """The reason this fence is not executed, or None (indentation-agnostic, so it works for blocks
    nested in lists/admonitions too)."""
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return next((reason for marker, reason in SKIP_MARKERS.items() for line in window if marker in line), None)


def _namespace(doc: str) -> dict[str, object]:
    """The globals a block on this page runs with: the shared one, plus the page's own fixture."""
    namespace = dict(DOC_NAMESPACE)
    fixture = PAGE_FIXTURES.get(doc)
    if fixture is not None:
        exec(fixture, namespace)
    return namespace


def _run(example: CodeExample, eval_example: EvalExample) -> None:
    namespace = _namespace(pathlib.Path(example.path).as_posix())
    module = eval_example.run(example, module_globals=namespace)
    # an example written as a test only binds it, so the fixture-free ones are called and their bodies checked
    for name, value in module.items():
        if name.startswith("test_") and callable(value) and not inspect.signature(value).parameters:
            value()


@pytest.fixture
def _matchers_restored():
    """The registry a page's blocks write to, emptied first and put back after.

    Both halves matter: restoring keeps a page out of the rest of the suite, and emptying keeps the rest
    of the suite out of the page, so a name a guide registers cannot clash with one left behind.
    """
    saved = dict(matchers._custom_matchers)
    matchers._custom_matchers.clear()
    try:
        yield
    finally:
        matchers._custom_matchers.clear()
        matchers._custom_matchers.update(saved)


@pytest.mark.parametrize("doc", list(_PAGES), ids=str)
@pytest.mark.usefixtures("_matchers_restored")
def test_doc_examples_run(doc: str, eval_example: EvalExample) -> None:
    ran = 0
    for example in _PAGES[doc]:
        if _skip_reason(example) is not None:
            continue
        try:
            _run(example, eval_example)
        except Exception as failure:
            raise AssertionError(f"{doc}:{example.start_line}-{example.end_line}: {failure!r}") from failure
        ran += 1
    if ran == 0:
        pytest.skip("every block on this page is marked non-executable")


_BLOCK = "<docs block>"
_RAISES = SKIP_MARKERS["docs-guard: raises"]
_EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Failure|Warning)): (.*)$")


def _uncommented(text: str) -> str:
    """A comment's text without the ``#`` and the one space after it, keeping everything else it holds."""
    return text.lstrip().removeprefix("#").removeprefix(" ")


def _documented(source: str, statement: ast.stmt) -> list[str]:
    """What the page says *statement* produces: its trailing comment, or the comment lines directly under it."""
    comments = {
        token.start[0]: token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    }
    last = statement.end_lineno or statement.lineno
    if last in comments:
        return [_uncommented(comments[last])]
    lines = source.splitlines()
    below: list[str] = []
    for number in range(last + 1, len(lines) + 1):
        if number not in comments or not lines[number - 1].lstrip().startswith("#"):
            break
        below.append(_uncommented(lines[number - 1]))
    return below


def _says(documented: list[str], actual: str) -> bool:
    """Whether *documented* is *actual* as the page writes it.

    The leading lines of it, character for character, except that one long line may be wrapped over
    several comments, rejoined with a single space.  A single line may instead end in ``...`` for a
    message cut short on purpose, or add ``: why`` after the output.
    """
    if len(documented) == 1:
        (only,) = documented
        if only.startswith(f"{actual}: "):
            return True
        if only.endswith("..."):
            return actual.startswith(only.removesuffix("..."))
    remaining = list(documented)
    for line in actual.splitlines():
        if not remaining:
            return True
        joined = remaining.pop(0)
        while joined != line and remaining and line.startswith(f"{joined} "):
            joined = f"{joined} {remaining.pop(0)}"
        if joined != line:
            return False
    return not remaining


@pytest.mark.parametrize(
    ("documented", "actual", "said"),
    [
        (["a b"], "a b", True),
        (["a b"], "a  b", False),
        (["Expected <'a b'>"], "Expected <'a  b'>", False),
        (["  b:"], "   b:", False),
        (["x"], "x\ny", True),
        (["x", "y", "z"], "x\ny", False),
        (["one two", "three"], "one two three", True),
        (["one two", "three"], "one two  three", False),
        (["False: why"], "False", True),
        (["True: why"], "False", False),
        (["cut here; ..."], "cut here; and the rest", True),
        (["cut here; ..."], "cut here;and the rest", False),
        (["cut  here; ..."], "cut here; and the rest", False),
        (["a "], "a", False),
    ],
)
def test_the_comparison_is_exact_but_for_a_wrapped_line(documented: list[str], actual: str, said: bool) -> None:
    """Whitespace inside a rendered value is part of it, so evening it out let a changed value read as the old one."""
    assert_that(_says(documented, actual)).is_equal_to(said)


@pytest.mark.parametrize(
    ("source", "documented"),
    [
        ("print(1)  # 1 \n", ["1 "]),
        ("print(1)\n#   b: \n#     - 2\n", ["  b: ", "    - 2"]),
    ],
    ids=["on-the-line", "under-it"],
)
def test_a_documented_output_is_read_whole(source: str, documented: list[str]) -> None:
    """Only the ``#`` and the one space after it come off: an indent or a trailing space was printed too."""
    (statement,) = _prints(source)
    assert_that(_documented(source, statement)).is_equal_to(documented)


class _Printed:
    """A block's ``print``: what each call wrote, by the block line it was called from."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def __call__(self, *values: object, sep: str = " ", end: str = "\n", **_options: object) -> None:
        written = io.StringIO()
        builtins.print(*values, sep=sep, end=end, file=written)
        self.calls.append((sys._getframe(1).f_lineno, written.getvalue().rstrip("\n")))


def _prints(source: str) -> list[ast.Expr]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "print"
    ]


@pytest.mark.parametrize(
    "doc",
    [doc for doc, examples in _PAGES.items() if any("print(" in one.source for one in examples)],
    ids=str,
)
@pytest.mark.usefixtures("_matchers_restored")
def test_what_a_block_prints_is_what_the_page_says(doc: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The run above executes a block and never reads the comment showing its output.

    So a message whose shape changed went on being shown in the old one.  Rendered the way the page
    describes it, off pytest, where the diff travels in the message.
    """
    monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
    checked = 0
    for example in _PAGES[doc]:
        if _skip_reason(example) is not None or "print(" not in example.source:
            continue
        printed = _Printed()
        exec(compile(example.source, _BLOCK, "exec"), _namespace(doc) | {"print": printed})
        for statement in _prints(example.source):
            documented = _documented(example.source, statement)
            if not documented:
                continue
            where = f"{doc}:{example.start_line + statement.lineno}"
            last = statement.end_lineno or statement.lineno
            ran = [text for line, text in printed.calls if statement.lineno <= line <= last]
            assert_that(ran).described_as(f"{where}: runs of the documented print").is_length(1)
            assert_that(_says(documented, ran[0])).described_as(
                f"{where}: printed {ran[0]!r}, the page says {documented!r}"
            ).is_true()
            checked += 1
    assert_that(checked).described_as("documented prints compared on the page").is_positive()


def _raising_line(failure: BaseException) -> int:
    return [frame.lineno for frame in traceback.extract_tb(failure.__traceback__) if frame.filename == _BLOCK][-1]


def _names(failure: BaseException) -> set[str]:
    return {
        name for kind in type(failure).__mro__ for name in (kind.__qualname__, f"{kind.__module__}.{kind.__qualname__}")
    }


@pytest.mark.parametrize(
    "doc",
    [doc for doc, examples in _PAGES.items() if any(_skip_reason(one) == _RAISES for one in examples)],
    ids=str,
)
@pytest.mark.usefixtures("_matchers_restored")
def test_a_raising_block_shows_the_failure_it_raises(doc: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A block marked as raising is skipped by the run above, so the failure its comment shows was never read.

    Compared where the comment names an exception or quotes a message; a comment in prose (``# fails``)
    says nothing to compare.
    """
    monkeypatch.setattr(errors, "_RENDER_DIFF_IN_MESSAGE", True)
    checked = 0
    for example in _PAGES[doc]:
        if _skip_reason(example) != _RAISES:
            continue
        where = f"{doc}:{example.start_line}"
        try:
            exec(compile(example.source, _BLOCK, "exec"), _namespace(doc))
        except Exception as failure:
            line = _raising_line(failure)
            statement = min(
                (
                    node
                    for node in ast.walk(ast.parse(example.source))
                    if isinstance(node, ast.stmt) and node.lineno <= line <= (node.end_lineno or node.lineno)
                ),
                key=lambda node: (node.end_lineno or node.lineno) - node.lineno,
            )
            documented = _documented(example.source, statement)
            named = _EXCEPTION.match(documented[0]) if documented else None
            if named is not None:
                assert_that(_names(failure)).described_as(f"{where}: the exception raised").contains(named.group(1))
                documented = [named.group(2), *documented[1:]]
            elif not documented or not documented[0].startswith(("Expected", "[")):
                continue
            assert_that(_says(documented, str(failure))).described_as(
                f"{where}: raised {str(failure)!r}, the page says {documented!r}"
            ).is_true()
            checked += 1
        else:
            pytest.fail(f"{where}: marked as raising, and ran clean")
    assert_that(checked).described_as("failures compared with what the page shows").is_positive()
