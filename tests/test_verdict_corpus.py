"""Hold every recorded answer to what it was at the last release.

A red run here is a decision, not a failure to paper over: read which case moved, decide whether the
change is meant to ship, and re-record with

    ASSERTPY_UPDATE_VERDICTS=1 pytest tests/test_verdict_corpus.py

The diff of `verdict_golden.txt` is then the draft of the release's Behaviour changes section, which is
the whole point: 2.27.0 shipped one note about a change nobody could see and three real changes that a
hand-built sweep against the previous tag found late.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re

import pytest

from assertpy import assert_that
from tests.verdict_corpus import CASES, GROUPS, NAMED, answer

_GOLDEN = pathlib.Path(__file__).resolve().parent / "verdict_golden.txt"


def _available(requires: str) -> bool:
    return not requires or importlib.util.find_spec(requires) is not None


def _recorded() -> dict[str, str]:
    found = {}
    for line in _GOLDEN.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, said = line.partition("\t")
            found[name] = said
    return found


def _write(answers: dict[str, str]) -> None:
    header = "# What each input decides, recorded at the last release. See test_verdict_corpus.py.\n"
    body = "".join(f"{name}\t{said}\n" for name, said in sorted(answers.items()))
    _GOLDEN.write_text(header + body, encoding="utf-8", newline="\n")


@pytest.fixture(scope="module")
def asked() -> dict[str, str]:
    """Every case whose dependencies are here, asked once for the module."""
    return {name: answer(case) for name, case in CASES.items() if _available(case.requires)}


@pytest.mark.parametrize(("group", "cases"), GROUPS, ids=lambda one: one if isinstance(one, str) else "")
def test_every_group_carries_enough_to_mean_something(group: str, cases: dict) -> None:
    """Held per group, not as one total: a total is satisfied while a whole category disappears."""
    assert_that(cases).described_as(f"inputs under {group}").is_length_between(3, 60)


def test_no_case_name_is_used_twice() -> None:
    """The mapping is built from eight group dicts, and a repeat would overwrite one without a word."""
    repeated = sorted({name for name, _ in NAMED if [one for one, _ in NAMED].count(name) > 1})
    assert_that(repeated).described_as("names used by more than one case").is_empty()
    assert_that(len(CASES)).described_as("cases that survived the mapping").is_equal_to(len(NAMED))


_RECORDING = bool(os.environ.get("ASSERTPY_UPDATE_VERDICTS"))
_WHILE_RECORDING = pytest.mark.skipif(_RECORDING, reason="the record is being rewritten by this run")


@_WHILE_RECORDING
def test_every_recorded_name_is_still_a_case() -> None:
    """A renamed case would otherwise leave its old answer frozen in the file forever."""
    assert_that(sorted(set(_recorded()) - set(CASES))).described_as("recorded but gone").is_empty()


@_WHILE_RECORDING
def test_every_case_is_recorded() -> None:
    """A new case must be recorded deliberately rather than silently ignored."""
    assert_that(sorted(set(CASES) - set(_recorded()))).described_as("a case with no recorded answer").is_empty()


def test_an_optional_dependency_that_is_here_is_asked() -> None:
    """The skip is about a cell without the extra, never about a case quietly dropping out."""
    silent = sorted(name for name, case in CASES.items() if case.requires and not _available(case.requires))
    if silent:
        pytest.skip(f"not installed here: {silent[0].split('/')[0]}")
    assert_that(silent).described_as("cases skipped for a missing dependency").is_empty()


def test_no_input_decides_differently(asked: dict[str, str]) -> None:
    """The gate itself.

    Compared only over the cases this cell could ask, so a run without an optional extra reports on
    what it ran rather than on what it could not.
    """
    if _RECORDING:
        missing = sorted({case.requires for case in CASES.values() if case.requires and not _available(case.requires)})
        # a partial re-record would leave the cases it could not ask frozen at whatever they said
        # before, which reads as "unchanged" for exactly the dependency nobody here can check
        assert_that(missing).described_as("install these before re-recording, or their answers go stale").is_empty()
        # a case that could not be asked here keeps what it said; one that no longer exists is dropped,
        # or a rename would leave its old answer in the file forever
        kept = {**_recorded(), **asked}
        _write({name: said for name, said in kept.items() if name in CASES})
        pytest.skip("verdicts re-recorded on request")
    recorded = _recorded()
    moved = {name: {"was": recorded[name], "now": said} for name, said in asked.items() if recorded.get(name) != said}
    assert_that(moved).described_as(
        "an input decides differently. Meant to ship? Re-record with ASSERTPY_UPDATE_VERDICTS=1"
    ).is_empty()


_VOLATILE = {
    "a raw address": re.compile(r"0x[0-9a-fA-F]{6,}"),
    "a pre-3.12 OrderedDict repr": re.compile(r"OrderedDict\(\["),
    "a generator's identity": re.compile(r"<generator object"),
}


@pytest.mark.parametrize("what", sorted(_VOLATILE), ids=lambda one: one)
def test_no_recorded_answer_holds_something_that_moves_on_its_own(what: str) -> None:
    """Asking twice in one process missed this class; CI found it on every cell but the newest.

    An address is a different length on another platform and a repr is rendered differently by another
    interpreter, so an answer holding either is re-recorded by whoever runs the suite next rather than
    by whoever changes a decision.  Held over the file, which is the only place all of them are.
    """
    pattern = _VOLATILE[what]
    holding = sorted(name for name, said in _recorded().items() if pattern.search(said))
    assert_that(holding).described_as(f"recorded answers holding {what}").is_empty()


def test_asking_twice_gives_the_same_answer(asked: dict[str, str]) -> None:
    """An answer that moves between two runs of one process would make every diff here noise."""
    again = {name: answer(case) for name, case in CASES.items() if _available(case.requires)}
    unstable = {name: (asked[name], again[name]) for name in asked if asked[name] != again[name]}
    assert_that(unstable).described_as("answers that differ between two runs").is_empty()
