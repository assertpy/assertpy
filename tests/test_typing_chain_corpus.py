"""Hold the chain model's bounded corpus to what the four checkers said about it when it was recorded.

The corpus is generated from the model's transition table (`tests/chain_corpus.py`) into a scratch folder
each run, and each checker's diagnostics on it have to be the recorded ones, in both directions and codes
included.  A declaration rewritten to say the same thing leaves this green, and one that says anything
else, better or worse, has to be recorded on purpose.

What is recorded is a pin the library does not meet yet: `is_not_none()` over `None`, a polled
`is_instance_of()` over a container and, under pyrefly alone, a polled `extracting()` followed by `filtered_on()`.

Skipped where the checkers are absent, like the other typing gates: the lint job runs it.
"""

from __future__ import annotations

import json

import pytest

from tests.optional import needs

needs("pyright", delegated_to="the lint job")
needs("mypy", delegated_to="the lint job")

from assertpy import assert_that
from tests import chain_corpus


@pytest.fixture(scope="module")
def found(tmp_path_factory) -> dict[str, dict[str, list[str]]]:
    return chain_corpus.disagreements(tmp_path_factory.mktemp("corpus"))


def test_every_checker_ran(found) -> None:
    assert_that(sorted(found.get("witness", {}))).is_equal_to(["mypy", "pyrefly", "pyright", "ty"])


def test_each_checker_says_what_was_recorded(found) -> None:
    recorded = json.loads(chain_corpus.BASELINE.read_text(encoding="utf-8"))
    assert_that(found).described_as("record a change with `python -m tests.chain_corpus`").is_equal_to(recorded)
