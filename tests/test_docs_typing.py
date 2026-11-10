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
* ``<!-- docs-guard: type-error RULE, ... -->`` the block demonstrates a rejection, by the ty rules named, so
  each of its lines has to fail with one of them and nothing else in it may fail.  A counter-example that
  silently starts passing is how a page's promise rots unnoticed, and so is one that goes on failing for
  another reason, a name that no longer exists among them.

Anything else has to type-check, which also means this guard reports the reverse of what
test_protocol_parity.py reports: parity proves every declared method exists, this proves the methods
the docs actually use are declared.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import subprocess
import sys

import pytest

from tests.optional import needs

needs("pytest_examples")
needs("ty")
# what the typed blocks import: without one, every block reading it fails to resolve and nothing else is learnt
for _module in ("attrs", "numpy", "pandas", "polars", "pydantic", "typing_extensions"):
    needs(_module)

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
TYPE_ERROR = re.compile(r"docs-guard: type-error(?P<rules>[^>]*?)\s*-->")
_ERROR = re.compile(r"(?P<file>[\w.-]+\.py):(?P<line>\d+):\d+: error\[(?P<rule>[\w-]+)\]")
_SUMMARY = re.compile(r"^(?:Found \d+ diagnostics?|All checks passed!)$", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class CounterExample:
    """The lines of a generated file that must fail, and the rules they may fail with."""

    lines: frozenset[int]
    rules: frozenset[str]


def _markers(example: CodeExample) -> list[str]:
    lines = pathlib.Path(example.path).read_text(encoding="utf-8").splitlines()
    window = lines[max(0, example.start_line - 3) : example.start_line]
    return [line for line in window if "docs-guard:" in line]


def _snippet(example: CodeExample, doc: str) -> str:
    return PREAMBLE + PAGE_FIXTURES.get(doc, "") + example.source


def _write_snippets(target: pathlib.Path) -> tuple[int, dict[str, CounterExample]]:
    """Write every checkable block, and report the counter-examples by the file each was written to.

    Per line rather than per file, because a two-line counter-example was passing on one diagnostic:
    the second line could quietly start type-checking and nothing would say so.  The line numbers are
    the snippet's own, which is what a checker reports against.
    """
    written = 0
    must_fail: dict[str, CounterExample] = {}
    for doc in CHECKED_DOCS:
        for example in find_examples(doc):
            markers = _markers(example)
            if any(marker in line for line in markers for marker in SKIP_MARKERS):
                continue
            name = f"{doc.replace('/', '_').removesuffix('.md')}__{example.start_line}.py"
            snippet = _snippet(example, doc)
            (target / name).write_text(snippet, encoding="utf-8")
            written += 1
            marked = next((found for line in markers if (found := TYPE_ERROR.search(line))), None)
            if marked is not None:
                offset = len(snippet.splitlines()) - len(example.source.splitlines())
                lines = {
                    offset + number
                    for number, line in enumerate(example.source.splitlines(), 1)
                    if line.strip() and not line.lstrip().startswith("#")
                }
                rules = {rule for rule in re.split(r"[\s,]+", marked["rules"]) if rule}
                must_fail[name] = CounterExample(frozenset(lines), frozenset(rules))
    return written, must_fail


def _check(target: pathlib.Path) -> list[str]:
    return _errors(
        subprocess.run(
            # the interpreter named: run from an sdist there is no `.venv` and no `VIRTUAL_ENV` for ty to find
            [
                sys.executable,
                "-m",
                "ty",
                "check",
                "--python",
                sys.executable,
                "--output-format",
                "concise",
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    )


def _errors(result: subprocess.CompletedProcess[str]) -> list[str]:
    """ty's error lines, from a check it finished: 0 is clean, 1 is diagnostics, and anything else is ty failing.

    Read only off a run that printed its summary, since one that failed to start prints nothing to read and
    would leave every documented block passing.
    """
    if result.returncode not in (0, 1) or _SUMMARY.search(result.stdout) is None:
        raise AssertionError(f"ty did not finish the check, exit {result.returncode}:\n{result.stderr}{result.stdout}")
    return [line for line in result.stdout.splitlines() if ": error" in line]


def _judged(reported: list[str], must_fail: dict[str, CounterExample]) -> tuple[list[str], dict[str, list[int]]]:
    """The errors no counter-example accounts for, and the lines of each that no error it names fell on."""
    unexpected: list[str] = []
    met: dict[str, set[int]] = {name: set() for name in must_fail}
    for line in reported:
        found = _ERROR.search(line)
        counter = must_fail.get(found["file"]) if found is not None else None
        if (
            found is not None
            and counter is not None
            and int(found["line"]) in counter.lines
            and found["rule"] in counter.rules
        ):
            met[found["file"]].add(int(found["line"]))
        else:
            unexpected.append(line)
    accepted = {
        name: sorted(counter.lines - met[name]) for name, counter in must_fail.items() if counter.lines - met[name]
    }
    return unexpected, accepted


def test_doc_examples_type_check(tmp_path: pathlib.Path) -> None:
    written, must_fail = _write_snippets(tmp_path)
    # a broken extractor would make this guard pass by checking nothing
    assert_that(written).is_greater_than(20)
    unnamed = sorted(name for name, counter in must_fail.items() if not counter.rules)
    assert_that(unnamed).described_as("counter-examples that name no rule they are refused by").is_empty()
    unexpected, accepted = _judged(_check(tmp_path), must_fail)
    assert_that(unexpected).described_as("type errors in documented examples").is_empty()
    assert_that(accepted).described_as("counter-example lines not refused by a rule they name").is_empty()


_ONE = {"page__1.py": CounterExample(frozenset({4}), frozenset({"invalid-argument-type"}))}


class TestTheJudgement:
    """What the guard makes of what ty reports, on reports written out here."""

    def test_a_line_refused_by_the_rule_named_is_what_was_promised(self):
        reported = ["/tmp/page__1.py:4:5: error[invalid-argument-type] Argument is incorrect"]
        assert_that(_judged(reported, _ONE)).is_equal_to(([], {}))

    def test_a_line_refused_by_another_rule_is_reported_and_left_unrefused(self):
        """The block that stopped showing its rejection and fails on a name that no longer exists."""
        reported = ["/tmp/page__1.py:4:5: error[unresolved-reference] Name `gone` used when not defined"]
        assert_that(_judged(reported, _ONE)).is_equal_to((reported, {"page__1.py": [4]}))

    def test_an_error_elsewhere_in_a_counter_example_is_reported(self):
        reported = [
            "/tmp/page__1.py:2:1: error[invalid-argument-type] in the fixture",
            "/tmp/page__1.py:4:5: error[invalid-argument-type] Argument is incorrect",
        ]
        assert_that(_judged(reported, _ONE)).is_equal_to((reported[:1], {}))

    def test_a_ty_that_did_not_finish_fails_the_check(self):
        broken = subprocess.CompletedProcess([], 2, stdout="", stderr="error: unexpected argument '--nope' found")
        with pytest.raises(AssertionError, match="unexpected argument"):
            _errors(broken)

    def test_a_ty_that_printed_no_summary_fails_the_check(self):
        with pytest.raises(AssertionError, match="did not finish"):
            _errors(subprocess.CompletedProcess([], 0, stdout="", stderr=""))
