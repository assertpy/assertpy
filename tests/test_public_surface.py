"""Pin what `import assertpy` gives a caller.

The golden failure harness proves the text of a failure has not moved. It says nothing about the Python
contract, and nothing else did either: before this file, removing a name from `__all__` or a field from
a published record passed every gate in the repository.

The neighbours answer different questions. `test_protocol_parity` proves each declared protocol method
exists at runtime, `test_api_vocabulary` holds the naming rules, `test_typing` pins overload resolution.
None of them notices an export that disappeared.

Both lists below are written by hand. Deriving them from the package would agree with whatever the
package happens to say, which gates nothing: the point is that a human edits them on purpose.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import pathlib
import re
import subprocess
import sys

import pytest

import assertpy
from assertpy import assert_that


def _protocol_count(source: str) -> int:
    """How many Protocols the typed surface declares, asked of the syntax rather than of a name pattern.

    Counting class declarations whose name ends in ``Assertion`` by regex would count any class that
    happens to be named that way, protocol or not, while the page's claim is about protocols.
    """
    return sum(
        isinstance(node, ast.ClassDef)
        and node.name.endswith("Assertion")
        and any(_names_protocol(base) for base in node.bases)
        for node in ast.walk(ast.parse(source))
    )


def _kinds_listed(page: str) -> int:
    """How many kinds of minor change the page lists under the sentence that counts them.

    The sentence and the list are edited apart, so a kind added to one and not the other leaves the page
    promising a number it does not deliver, which is the one thing this page must not do.
    """
    listed = page.split("kinds of change ship in a minor", 1)[-1].splitlines()[2:]
    counted = 0
    for line in listed:
        if not line.strip():
            break
        counted += line.startswith("- **")
    return counted


def _names_protocol(base: ast.expr) -> bool:
    """Whether a base is ``Protocol``, written plain or parameterised."""
    if isinstance(base, ast.Subscript):
        base = base.value
    return isinstance(base, ast.Name) and base.id == "Protocol"


_WORDS = {
    5: "five",
    6: "six",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    21: "twenty-one",
    22: "twenty-two",
    23: "twenty-three",
    24: "twenty-four",
    25: "twenty-five",
    26: "twenty-six",
    27: "twenty-seven",
    28: "twenty-eight",
    29: "twenty-nine",
    30: "thirty",
    31: "thirty-one",
    34: "thirty-four",
    35: "thirty-five",
}

EXPECTED_EXPORTS = [
    "AssertionFailure",
    "DanglingAssertionWarning",
    "AssertionOutcome",
    "AsyncAssertionBuilder",
    "BaseMatcher",
    "CheckBuilder",
    "DiffEntry",
    "DiffResult",
    "MatchResult",
    "Matcher",
    "NegatedBuilder",
    "PollSample",
    "PollTrace",
    "Requirement",
    "SnapshotCreatedWarning",
    "SnapshotKeyReusedWarning",
    "SnapshotUpdatedWarning",
    "SoftAssertionCollector",
    "Step",
    "SyncAssertionBuilder",
    "VacuousAssertionWarning",
    "WarningLoggingAdapter",
    "__version__",
    "add_extension",
    "assert_all",
    "assert_conforms",
    "assert_that",
    "assert_warn",
    "clear_custom_matchers",
    "contents_of",
    "fail",
    "log_passes",
    "match",
    "register_matcher",
    "register_snapshot_serializer",
    "remove_extension",
    "soft_assertions",
    "soft_fail",
    "unregister_matcher",
]

# The records a consumer reads off a failure. `__all__` covers exported names and stops there, so a
# field dropped from one of these would go out in a release unremarked.
EXPECTED_FIELDS = {
    "AssertionOutcome": [
        "passed",
        "message",
        "actual",
        "actual_provided",
        "expected",
        "diff",
        "requirement",
        "trace",
        "group",
        "location",
        "hint",
    ],
    "Requirement": ["operation", "parameters", "negated"],
    "MatchResult": ["matched", "description", "mismatch", "diff"],
    "DiffEntry": ["path", "actual", "expected", "absent", "steps"],
    "DiffResult": ["kind", "entries"],
    "Step": ["kind", "value", "side"],
    "PollSample": ["elapsed", "outcome", "value", "detail", "repeats"],
    "PollTrace": ["samples", "total_polls", "dropped", "elapsed", "summary"],
}


def _fields(record: type) -> list[str]:
    """Field names in declaration order, for a dataclass or a NamedTuple alike."""
    if dataclasses.is_dataclass(record):
        return [field.name for field in dataclasses.fields(record)]
    return list(record._fields)


_DIRECTIVE = re.compile(r"^::: (\S+)\n((?:    .*\n)*)", re.MULTILINE)


def _resolve(path: str) -> object:
    """The object a mkdocstrings path names: the longest importable module, then attributes."""
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        try:
            found = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        for name in parts[split:]:
            found = getattr(found, name)
        return found
    raise LookupError(path)


def _headed_entries() -> dict[str, str]:
    """Reference directives that give their object a heading, the only kind a link can land on."""
    entries = {}
    for page in sorted(pathlib.Path("docs/reference").glob("*.md")):
        for path, options in _DIRECTIVE.findall(page.read_text(encoding="utf-8")):
            if re.search(r"^ +show_root_heading: true$", options, re.MULTILINE):
                entries[path.rsplit(".", 1)[-1]] = path
    return entries


class TestEveryExportHasAReferenceEntry:
    """An export without a heading of its own in the reference has no anchor a link can land on.

    Twelve had none, because a directive left at the site's default renders a class's members and not
    the class itself.
    """

    # a string, and a namespace whose class is private: its page is the list of its members
    WITHOUT_AN_ENTRY = frozenset({"__version__", "match"})

    def test_every_export_has_a_heading(self):
        missing = sorted(set(assertpy.__all__) - set(_headed_entries()) - self.WITHOUT_AN_ENTRY)
        assert_that(missing).described_as("exports with no heading in the reference").is_empty()

    def test_each_heading_documents_the_exported_object(self):
        entries = _headed_entries()
        elsewhere = {
            name: entries[name]
            for name in sorted(set(assertpy.__all__) & set(entries))
            if _resolve(entries[name]) is not getattr(assertpy, name)
        }
        assert_that(elsewhere).described_as("headings naming another object of the same name").is_empty()


class TestExports:
    def test_the_exported_names_are_the_recorded_ones(self):
        assert_that(sorted(assertpy.__all__)).is_equal_to(sorted(EXPECTED_EXPORTS))

    def test_every_exported_name_resolves(self):
        # a name left in `__all__` after its import was dropped fails only at `import *`, which nothing does
        missing = [name for name in assertpy.__all__ if not hasattr(assertpy, name)]
        assert_that(missing).described_as("names in __all__ with nothing behind them").is_empty()


class TestRecordFields:
    def test_each_published_record_keeps_its_fields(self):
        observed = {name: _fields(getattr(assertpy, name)) for name in EXPECTED_FIELDS}
        assert_that(observed).is_equal_to(EXPECTED_FIELDS)

    def test_every_pinned_record_is_exported(self):
        # a record dropped from `__all__` would keep passing the check above through this module's import path
        assert_that(sorted(EXPECTED_FIELDS)).is_subset_of(set(assertpy.__all__))


class TestTheCountsTheDocsQuote:
    """The pages state these as figures, and a figure in prose rots silently: it was written at 39
    matchers and was still saying so at 41.

    The pages are read here rather than trusted to a number repeated in this file. Pinning the count
    alone left the README saying 39 for two releases, because nothing connected the figure to the
    sentence carrying it.
    """

    QUOTED_MATCHER_COUNT = 46
    # the comparison page dropped the figure deliberately: it sold on inventory, our weakest pitch
    PAGES_QUOTING_THE_MATCHER_COUNT = ("README.md",)
    QUOTED_PROTOCOL_COUNT = 15

    def test_the_matcher_count(self):
        matchers = [name for name in dir(assertpy.match) if not name.startswith("_")]
        assert_that(matchers).described_as("matchers, quoted in the docs").is_length(self.QUOTED_MATCHER_COUNT)

    # a bare `(\d+) matchers` reads the "2" out of "assertpy matchers", and "41 composable matchers" must fit
    _QUOTED = re.compile(r"(?<![\w.])(\d+)\s+(?:\w+\s+)?matchers")

    def test_every_page_quoting_the_matcher_count_quotes_the_right_one(self):
        stale = {}
        for page in self.PAGES_QUOTING_THE_MATCHER_COUNT:
            quoted = self._QUOTED.findall(pathlib.Path(page).read_text(encoding="utf-8"))
            # a page that stopped quoting the figure drifts too: the guard would go on passing over a rewritten sentence
            if not quoted or set(quoted) != {str(self.QUOTED_MATCHER_COUNT)}:
                stale[page] = quoted
        assert_that(stale).described_as("pages quoting a matcher count that is not the real one").is_empty()

    def test_the_protocol_count(self):
        # counted from what `assert_that` dispatches to, which is the claim the pages make.
        # `_InvokedAssertion` is reached through `raised()`, so an IDE never offers it on the first call
        source = pathlib.Path("assertpy/assertpy.py").read_text(encoding="utf-8")
        returned = set(re.findall(r"-> (_[A-Za-z]+Assertion)\b", source))
        assert_that(returned).described_as("protocols assert_that returns, quoted in the docs").is_length(
            self.QUOTED_PROTOCOL_COUNT
        )
        quoted = re.findall(r"(?<![\w.])(\d+) type-specific Protocols", pathlib.Path("README.md").read_text("utf-8"))
        assert_that(quoted).described_as("the figure the README quotes").is_equal_to([str(self.QUOTED_PROTOCOL_COUNT)])

    def test_the_stability_page_counts_what_it_promises(self):
        """That page's whole claim is that every row is held by a test, so a wrong figure on it is
        worse than a wrong figure anywhere else. It was found saying 123 `assert_type` checks over a
        file holding 122.
        """
        page = pathlib.Path("docs/concepts/stability.md").read_text(encoding="utf-8")
        typing_suite = pathlib.Path("tests/test_typing.py").read_text(encoding="utf-8")
        protocols = pathlib.Path("assertpy/_engine/_typing.py").read_text(encoding="utf-8")
        quoted = {
            "exported names": (re.search(r"The (\d+) names", page), len(assertpy.__all__)),
            "assert_type checks": (re.search(r"(\d+) `assert_type` checks", page), typing_suite.count("assert_type(")),
            "protocols": (re.search(r"walks all ([\w-]+) protocols", page), _protocol_count(protocols)),
            "kinds of change": (re.search(r"([\w-]+) kinds of change", page), _kinds_listed(page)),
        }
        wrong = {}
        for what, (found, real) in quoted.items():
            said = found.group(1) if found else None
            if said is None or said.lower() not in {str(real), _WORDS.get(real)}:
                wrong[what] = f"page says {said}, real is {real}"
        assert_that(wrong).described_as("figures on the stability page").is_empty()

    def test_the_documented_allure_payloads_carry_the_version_the_plugin_emits(self):
        """The attachment schema is a promise to downstream tooling, so its version number is the one
        figure in the docs a consumer branches on. The diff attachment moved to 4 and the page went on
        printing 2, which is worse than no example: it reads as a contract.
        """
        plugin = pathlib.Path("assertpy/pytest_plugin.py").read_text(encoding="utf-8")
        page = pathlib.Path("docs/extending/integrations.md").read_text(encoding="utf-8")
        emitted = {int(number) for number in re.findall(r'"format":\s*(\d+)', plugin)}
        documented = {int(number) for number in re.findall(r'"format":\s*(\d+)', page)}
        assert_that(documented).described_as("attachment versions the page prints").is_equal_to(emitted)

    def test_the_assertion_count_clears_the_floor_the_docs_claim(self):
        # a floor: `add_extension` writes onto the builder, so a suite that registers one makes the exact
        # count depend on test order. The page says "over 100", and that is the claim worth holding
        builder = assertpy.assert_that(1)
        assertions = [
            name for name in dir(builder) if not name.startswith("_") and callable(getattr(builder, name, None))
        ]
        assert_that(len(assertions)).described_as("assertions, quoted in comparison.md as over 100").is_greater_than(
            100
        )


class TestNoOptionalDependencyIsImportedEagerly:
    """Importing the package must not drag in a library it only needs on one branch.

    The pytest plugin is auto-loaded, so `import assertpy` happens in every pytest run in the
    environment, whether or not a test ever calls an assertion. `attrs` sat at module level in
    `helpers.py` and cost 8.5 ms and 22 modules of a 39.8 ms import, a fifth of it, for a branch that
    fires only when an attrs instance reaches a comparison. Nothing in the suite noticed, because an
    eager import is invisible to every other gate here.

    Run in a subprocess: this process has already imported half of PyPI by the time a test runs.
    """

    OPTIONAL = ("attrs", "attr", "numpy", "pandas", "polars", "pydantic", "jsonschema", "jsonpath_ng", "executing")

    def test_none_of_them_arrives_with_the_package(self):
        program = (
            "import sys, json; import assertpy; "
            f"print(json.dumps([name for name in {self.OPTIONAL!r} if name in sys.modules]))"
        )
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=True)
        eager = json.loads(result.stdout)
        assert_that(eager).described_as("optional dependencies imported by `import assertpy`").is_empty()

    @pytest.mark.needs("attrs")
    def test_the_guard_can_see_an_eager_import(self):
        program = (
            "import sys, json; import attrs; import assertpy; "
            f"print(json.dumps([name for name in {self.OPTIONAL!r} if name in sys.modules]))"
        )
        result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, check=True)
        assert_that(json.loads(result.stdout)).contains("attrs")


class TestWhatAFailureLetsYouRead:
    """The failure itself, which the records above do not cover.

    `EXPECTED_FIELDS` pins dataclasses and named tuples, and an exception is neither, so nothing here
    held the attributes the errors guide teaches callers to read. The functional tests do exercise
    them, which is a different guarantee: they would notice a value going wrong, not a name going away.
    """

    READABLE = ("actual", "expected", "has_expected", "diff", "requirement", "trace", "failures")

    def test_it_stays_an_assertion_error(self):
        assert_that(issubclass(assertpy.AssertionFailure, AssertionError)).is_true()

    def test_a_plain_failure_carries_the_readable_surface(self):
        with pytest.raises(assertpy.AssertionFailure) as failure:
            assert_that(1).is_equal_to(2)
        missing = [name for name in self.READABLE if not hasattr(failure.value, name)]
        assert_that(missing).described_as("documented attributes missing from a failure").is_empty()
        assert_that(failure.value.actual).is_equal_to(1)
        assert_that(failure.value.expected).is_equal_to(2)

    def test_a_plain_failure_names_what_was_asked(self):
        with pytest.raises(assertpy.AssertionFailure) as failure:
            assert_that(1).is_equal_to(2)
        assert_that(failure.value.requirement).is_equal_to(
            assertpy.Requirement("is_equal_to", {"other": 2, "kwargs": {}})
        )

    def test_a_soft_block_reports_what_it_collected(self):
        with pytest.raises(assertpy.AssertionFailure) as failure, assertpy.soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that("a").is_equal_to("b")
        assert_that(failure.value.failures).is_length(2)
        assert_that([outcome.passed for outcome in failure.value.failures]).is_equal_to([False, False])

    def test_a_polling_failure_reports_its_trace(self):
        with pytest.raises(assertpy.AssertionFailure) as failure:
            assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)
        assert_that(failure.value.trace).is_not_none()
        assert_that(failure.value.trace.total_polls).is_greater_than_or_equal_to(1)

    def test_expected_alone_says_nothing_about_whether_an_operand_was_named(self):
        """Why `has_expected` had to exist, pinned from the outside.

        `expected` reads `None` for both "compared against None" and "named no expectation", so a
        reporter deciding whether to show an expected column could not tell them apart.  The
        distinction used to live only on the outcome the pytest plugin reads.
        """
        with pytest.raises(assertpy.AssertionFailure) as compared:
            assert_that(1).is_equal_to(None)
        with pytest.raises(assertpy.AssertionFailure) as unset:
            assert_that(1).is_none()
        assert_that(compared.value.expected).is_equal_to(unset.value.expected).is_none()
        assert_that(compared.value.actual).is_equal_to(unset.value.actual).is_equal_to(1)
        # `has_expected` does not separate these two: `is_none()` names an expectation as `is_equal_to(None)` does
        assert_that(compared.value.has_expected).is_equal_to(unset.value.has_expected).is_true()

    def test_has_expected_separates_an_assertion_that_names_no_expectation(self):
        """What `has_expected` is for, which is the other question `expected is None` cannot answer."""
        with pytest.raises(assertpy.AssertionFailure) as named:
            assert_that(1).is_equal_to(None)
        with pytest.raises(assertpy.AssertionFailure) as unnamed:
            assert_that([]).is_not_empty()
        assert_that(named.value.expected).is_equal_to(unnamed.value.expected).is_none()
        assert_that(named.value.has_expected).described_as("named an expectation").is_true()
        assert_that(unnamed.value.has_expected).described_as("named none").is_false()
