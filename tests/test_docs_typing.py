"""Type-check the code examples in the README and the guide docs.

The badge promises four type checkers with zero suppressions, and the README's own first listing used
to fail every one of them: `has_name` on a dict is resolved dynamically at runtime and no protocol declares it.
Executing the snippets (test_docs_examples.py) cannot catch that, because the code runs perfectly well.

Three markers steer this guard, all invisible in the rendered page:

* ``<!-- docs-guard: skip -->``       the block is illustrative and not runnable, so neither guard reads it
* ``<!-- docs-guard: untyped -->``    the block runs, and is excluded from here for a reason this guard
  cannot resolve: a dynamic assertion (``has_<attr>``), which is deliberately outside the typed surface,
  or a name that only exists above the supported floor. ``ty`` reads ``requires-python``, so a 3.11
  builtin like ``ExceptionGroup`` is undefined to it even where the example is correct.
* ``<!-- docs-guard: type-error -->`` the block demonstrates a rejection, so it has to fail the check.
  A counter-example that silently starts passing is how a page's promise rots unnoticed.

Anything else has to type-check, which also means this guard reports the reverse of what
test_protocol_parity.py reports: parity proves every declared method exists, this proves the methods
the docs actually use are declared.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

pytest.importorskip("pytest_examples")

from pytest_examples import CodeExample, find_examples

from assertpy import assert_that
from tests.docs_fixtures import PAGE_FIXTURES, documented_pages

# pages this guard does not read, with reasons; everything else is read, including a page added later
UNCHECKED_DOCS = {
    "docs/getting-started/comparison.md": "the blocks are the other library's API, not ours",
}

CHECKED_DOCS = documented_pages(UNCHECKED_DOCS)

# the same namespace as the executing guard, so a block cannot pass one and fail the other over an import
PREAMBLE = "import datetime, json, logging, re\nfrom pathlib import Path\nfrom assertpy import *  # noqa: F403\n"

SKIP_MARKERS = ("docs-guard: skip", "docs-guard: untyped")
TYPE_ERROR_MARKER = "docs-guard: type-error"


def _markers(example: CodeExample) -> list[str]:
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return [line for line in window if "docs-guard:" in line]


def _snippet(example: CodeExample, doc: str) -> str:
    return PREAMBLE + PAGE_FIXTURES.get(doc, "") + example.source


def _write_snippets(target: pathlib.Path) -> tuple[int, dict[str, set[int]]]:
    """Write every checkable block, and report the counter-examples as ``{file: lines that must fail}``.

    Per line rather than per file, because a two-line counter-example was passing on one diagnostic:
    the second line could quietly start type-checking and nothing would say so.  The line numbers are
    the snippet's own, which is what a checker reports against.
    """
    written = 0
    must_fail: dict[str, set[int]] = {}
    for doc in CHECKED_DOCS:
        for example in find_examples(doc):
            markers = _markers(example)
            if any(marker in line for line in markers for marker in SKIP_MARKERS):
                continue
            name = f"{doc.replace('/', '_').removesuffix('.md')}__{example.start_line}.py"
            snippet = _snippet(example, doc)
            (target / name).write_text(snippet, encoding="utf-8")
            written += 1
            if any(TYPE_ERROR_MARKER in line for line in markers):
                offset = len(snippet.splitlines()) - len(example.source.splitlines())
                must_fail[name] = {
                    offset + number
                    for number, line in enumerate(example.source.splitlines(), 1)
                    if line.strip() and not line.lstrip().startswith("#")
                }
    return written, must_fail


def _check(target: pathlib.Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "ty", "check", "--output-format", "concise", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if ": error" in line]


def _reported_lines(reported: list[str], name: str) -> set[int]:
    """The snippet line numbers a checker reported against, for one generated file."""
    found = set()
    for line in reported:
        match = re.search(rf"{re.escape(name)}:(\d+):", line)
        if match:
            found.add(int(match.group(1)))
    return found


def test_doc_examples_type_check(tmp_path: pathlib.Path) -> None:
    written, must_fail = _write_snippets(tmp_path)
    # a broken extractor would make this guard pass by checking nothing
    assert_that(written).is_greater_than(20)
    reported = _check(tmp_path)
    diagnostics = [line for line in reported if not any(name in line for name in must_fail)]
    assert_that(diagnostics).described_as("type errors in documented examples").is_empty()
    accepted = {
        name: sorted(expected - _reported_lines(reported, name))
        for name, expected in must_fail.items()
        if expected - _reported_lines(reported, name)
    }
    assert_that(accepted).described_as("counter-example lines a checker still accepts").is_empty()
