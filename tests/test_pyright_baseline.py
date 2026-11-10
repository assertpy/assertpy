"""Hold the package-wide pyright surface to what `pyright_baseline.py` records.

CI gates pyright on `tests/test_typing.py`. The package itself was ungated, so a diagnostic introduced
anywhere in it went unreported.

Skipped where pyright is absent: it lives in the `typecheck` group, so this runs in the type-check job
rather than in the main suite.
"""

from __future__ import annotations

import collections
import functools
import json
import pathlib
import re
import subprocess
import sys

from tests.optional import needs

needs("pyright", delegated_to="the lint job")

from typing import Final

from assertpy import assert_that
from tests import typing_harness
from tests.pyright_baseline import BASELINE, LADDER_OVERLAP

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Named rather than counted: a count of two stays green when one is replaced by an unrelated
# diagnostic of the same rule, and each refusal is about its TypeVar rather than about a number.
_REFUSED_VARIANCE: tuple[tuple[str, str, str, str], ...] = (
    ("assertpy/_engine/_typing.py", "_RepeatableAssertion", "_E", "contravariant"),
    # `returned()` hands back the invariant builder over it. Invariant, the covariant views that lead here would
    # be asked to follow, down to the callable one, whose rungs a subclass value reaches only through covariance
    ("assertpy/_engine/_typing.py", "_WarnedAssertion", "_P_co", "invariant"),
    # `_NumericAssertion` is out because `check()` reads `_N` back in a return position, answering the
    # suggestion. `_CheckDictAssertion` gains one: dropping the chaining return leaves `_V` read-only
    ("assertpy/_engine/_check_typing.py", "_CheckRepeatableAssertion", "_E", "contravariant"),
    ("assertpy/_engine/_check_typing.py", "_CheckNumericAssertion", "_N", "covariant"),
    ("assertpy/_engine/_check_typing.py", "_CheckDictAssertion", "_V", "contravariant"),
    # invariant, a subclass value misses the rung written for its base on all three checkers. Refused
    ("assertpy/_engine/_poll_typing.py", "_AsyncPoll", "_P_co", "invariant"),
    ("assertpy/_engine/_poll_typing.py", "_NegatedAsyncPoll", "_P_co", "invariant"),
)


# The target this baseline was recorded against, passed rather than read off the running interpreter:
# pyright reports 174 diagnostics against 3.10 and 169 against 3.14. CI runs 3.14, and 3.15 agrees
_TARGET: Final = "3.14"


@functools.cache
def _diagnostics() -> tuple[dict[str, str], ...]:
    """Every pyright diagnostic over the package, as ``{file, rule, message}``, run once for the module."""
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "--pythonversion", _TARGET, "assertpy/"],
        capture_output=True,
        text=True,
        check=False,
        cwd=_ROOT,
        env=typing_harness.checker_env(),
    )
    # pyright exits non-zero whenever it reports anything, so the payload is what to read, not the code
    report = json.loads(result.stdout)
    return tuple(
        {
            "file": pathlib.Path(item["file"]).resolve().relative_to(_ROOT).as_posix(),
            "rule": item.get("rule", item["severity"]),
            "message": item["message"],
        }
        for item in report["generalDiagnostics"]
    )


_LADDER_RULE: Final = "reportOverlappingOverload"


def _observed() -> dict[tuple[str, str], int]:
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for item in _diagnostics():
        if item["rule"] != _LADDER_RULE:
            counts[(item["file"], item["rule"])] += 1
    return dict(counts)


def test_no_unrecorded_pyright_diagnostics() -> None:
    observed = _observed()
    # not load bearing while the record is not empty: a lost run fails below as every entry at once
    assert_that(observed).described_as("pyright reported nothing at all").is_not_empty()

    appeared = {key: count for key, count in observed.items() if count > BASELINE.get(key, 0)}
    assert_that(appeared).described_as("pyright diagnostics not recorded in pyright_baseline.py").is_empty()

    resolved = {key: count for key, count in BASELINE.items() if count > observed.get(key, 0)}
    assert_that(resolved).described_as("recorded in pyright_baseline.py but no longer reported").is_empty()


def test_the_ladder_overlaps_are_the_ones_still_reported() -> None:
    """Hold the overlap policy to the methods it claims, rather than to a count per file.

    The rule is more than half of everything pyright says about this package, and three of the five
    files carrying it are generated, so a per-file count was a number with no owner: one method could
    stop overlapping and another start, and 48 would still be 48. The method is what a reader can act
    on, and it is in the message already.
    """
    read = [
        (item, re.search(r'Overload \d+ for "(\w+)"', item["message"]))
        for item in _diagnostics()
        if item["rule"] == _LADDER_RULE
    ]
    # an unreadable message would drop out silently with a real change, which keeps the variance gate honest
    unreadable = [item["message"] for item, found in read if found is None]
    assert_that(unreadable).described_as("overlap reports this test could not read").is_empty()

    observed = collections.Counter((item["file"], found.group(1)) for item, found in read if found)
    assert_that(observed).described_as("pyright reported no overlap at all").is_not_empty()

    appeared = {key: count for key, count in observed.items() if count > LADDER_OVERLAP.get(key, 0)}
    assert_that(appeared).described_as("an overlapping overload not recorded in LADDER_OVERLAP").is_empty()

    resolved = {key: count for key, count in LADDER_OVERLAP.items() if count > observed.get(key, 0)}
    assert_that(resolved).described_as("recorded in LADDER_OVERLAP but no longer reported").is_empty()


def test_the_recorded_variance_refusals_are_the_ones_still_reported() -> None:
    """Name the variance suggestions the package refuses, rather than counting them.

    The counting gate above cannot tell one diagnostic of a rule from another in the same file, so a new
    `reportInvalidTypeVarUse` could take the place of a resolved one and nothing would move.  Each is
    refused for a reason written down beside it, and each reason is about a specific TypeVar: `_N`
    would break its inputs if made covariant, and `_E` is used covariantly through `Matcher[_E]` despite
    appearing only in parameters, which `typing_cases.py` demonstrates on all three checkers.

    `_P_co` stays covariant because a polling rung is chosen by a `self` type written for a base class,
    and a subclass value (a string enum member, an `OrderedDict`) reaches it only through covariance.
    Made invariant, ty, mypy and pyright all refused those calls, and `test_typing.py` pins them now.
    The price is the one every covariant container pays: a chain widened on purpose to a base type
    accepts an operand of that base type, as `Sequence[Base]` accepts one in `in`.
    """
    read = [
        (item, re.search(r'variable "(\w+)".*Protocol "(\w+)".*should be (\w+)', item["message"], re.DOTALL))
        for item in _diagnostics()
        if item["rule"] == "reportInvalidTypeVarUse"
    ]
    # every one has to be classified, or an unreadable message drops out silently with a real change
    unreadable = [item["message"] for item, found in read if found is None]
    assert_that(unreadable).described_as("variance suggestions this test could not parse").is_empty()

    # the file and the suggested variance are part of the record, and a count would not know they changed
    reported = [(item["file"], found.group(2), found.group(1), found.group(3)) for item, found in read if found]
    assert_that(sorted(reported)).described_as("the variance suggestions pyright still reports").is_equal_to(
        sorted(_REFUSED_VARIANCE)
    )
