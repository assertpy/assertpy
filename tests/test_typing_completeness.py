"""Hold the package at full type completeness: every exported symbol has a type a checker can name.

A different question from the one `test_pyright_baseline.py` asks.  That gate reads what pyright says
about the code as it is written, from the inside.  This one reads the exported surface from the
outside: `--verifytypes` walks every symbol the package exports and reports the ones whose type it
cannot resolve to something concrete.  A package can check clean and still hand its users an
`Unknown` on a public method, and until this was written, ours did on 33 of them.

It reads this checkout, not a built wheel, and the two were measured to agree: a wheel built and
installed into a clean environment reports the same 412 exported symbols and the same 100%.  Whether
the wheel *contains* the typed surface at all is `test_typing_from_a_wheel.py`'s question, and
answering it costs a build and an environment, which is why this one does not ask it again.

`Any` is not `Unknown`.  A parameter declared `object` or `Any` is a decision the surface records, and
pyright counts it as known.  What it counts against us is a name with no annotation at all, a generic
left unparameterised, an attribute a subclass reassigns without saying to what.  Those are the ones a
reader cannot recover from the code.

`--ignoreexternal` is load bearing and not cosmetic.  Without it the score is 92.72%, and the 29
symbols it adds are pytest's own partially-typed internals arriving through our plugin hooks:
`TerminalWriter`, `ReprTraceback`, `Config`.  Annotating around somebody else's incomplete surface is
not what this gate is for.

Named rather than scored, for the reason the baseline gate names its overlaps: a score of 99.5% says
nothing about which symbol slipped, and two symbols trading places leave it unmoved.

Skipped where pyright is absent: it lives in the `typecheck` group, so this runs in the type-check job
rather than in the main suite.
"""

from __future__ import annotations

import functools
import json
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("pyright", reason="the lint job installs the typecheck group and this cell does not")

from typing import Any, Final

from assertpy import assert_that
from tests import typing_harness

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# pinned as the baseline gate pins it: the type-check job runs 3.14, so a failure prints that job's list.
# The verdict does not depend on it, 3.10 exports 406 symbols against 3.14's 412 and both are complete
_TARGET: Final = "3.14"


@functools.cache
def _report() -> dict[str, Any]:
    """The whole `--verifytypes` payload, run once for the module."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--outputjson",
            "--verifytypes",
            "assertpy",
            "--ignoreexternal",
            "--pythonversion",
            _TARGET,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=_ROOT,
        env=typing_harness.checker_env(),
    )
    # pyright exits non-zero whenever completeness is short of 100%, so the payload is what to read
    return json.loads(result.stdout)


def _completeness() -> dict[str, Any]:
    return _report()["typeCompleteness"]


def test_every_exported_symbol_has_a_type_a_checker_can_name() -> None:
    report = _completeness()
    symbols = report["symbols"]

    # a run resolving nothing would pass saying so, hence a name only the real walk produces, not a count
    walked = {symbol["name"] for symbol in symbols}
    assert_that(walked).described_as("the verifytypes run did not reach the package").contains("assertpy.assert_that")

    unresolved = sorted(
        symbol["name"]
        for symbol in symbols
        if symbol["isExported"] and (not symbol["isTypeKnown"] or symbol["isTypeAmbiguous"])
    )
    assert_that(unresolved).described_as("exported symbols whose type pyright cannot name").is_empty()


def test_the_package_it_read_is_this_checkout() -> None:
    """Which `assertpy` answered, rather than whether some `assertpy` did.

    An editable install is a `.pth` carrying an import hook, and static resolution cannot follow it, so a
    checker that does not find the package beside its working directory falls back to whatever is on the
    machine.  Measured while writing this: run from elsewhere, pyright read a stale copy out of the
    system's own `site-packages` and reported 71.1% for a tree that is at 100%.

    It reports the directory it chose, so the gate reads it rather than trusting the run.
    """
    report = _report()["typeCompleteness"]
    for field in ("packageRootDirectory", "moduleRootDirectory", "pyTypedPath"):
        found = pathlib.Path(str(report[field])).resolve()
        assert_that(str(found)).described_as(f"the {field} pyright read").starts_with(str(_ROOT / "assertpy"))


def test_the_engine_is_the_one_this_gate_was_recorded_against() -> None:
    """The wrapper falls back to whatever it has if the pin does not reach the subprocess.

    That fallback is silent, and a number recorded against one build and read from another is a number
    about nothing. The two agree on this package today, measured, which is why the check is on the version
    rather than on the count: agreement is what a drift would end.
    """
    assert_that(_report()["version"]).described_as("the pyright build that answered").is_equal_to(
        typing_harness.PYRIGHT_ENGINE
    )


def test_the_score_agrees_with_the_symbols() -> None:
    """The two readings of the same run, kept from drifting apart.

    The test above reads the symbol list, which is what a failure can be acted on.  The score is what
    pyright prints and what anyone comparing us to another package will quote.  Asserting one and
    reporting the other would let a future pyright count something the list does not show.
    """
    report = _completeness()
    assert_that(report["completenessScore"]).described_as("pyright's own score for the surface").is_equal_to(1.0)
    counts = report["exportedSymbolCounts"]
    # the count moves with every method added, and a gate reddening on a new feature teaches blind re-recording
    assert_that({key: value for key, value in counts.items() if value}).described_as(
        "the counts behind the score"
    ).contains_only("withKnownType")
