"""A complexity ratchet, so the measure cannot grow where nobody looks.

Twenty-six functions in the package sit above mccabe's default of 10, the worst four being `extracting`
at 32, `_dict_err` and `_object_hook` at 22 and `_build_equality_diff` at 17.

Getting them under 10 is deliberately NOT the goal. It fixes no defect, and rewriting
`_build_equality_diff` for the sake of a number would risk code the suite and mutation testing hold.

Recorded per function rather than as a count or a ceiling, because neither of those sees the growth that
matters: a function going from 11 to 32 leaves both unchanged.  `[tool.ruff.lint.mccabe]` still carries
`max-complexity = 32`, which stops a new worst before this file is read at all.

Re-record when a number drops, which is the ratchet turning. A commit that raises one should say which
function grew and why that was the cheaper answer.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

from assertpy import assert_that
from tests.optional import needs

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_REPORTED = re.compile(r"`([^`]+)` is too complex \((\d+)")

RECORDED: dict[str, int] = {
    "assertpy/extracting.py::extracting": 32,
    "assertpy/_engine/_diff.py::_build_equality_diff": 16,
    # a flag per matched run instead of a call per matched element, which cost a failing is_equal_to 15%
    "assertpy/helpers.py::_elided_walks": 21,
    "assertpy/_hints.py::diagnose": 17,
    # 16: a key the lookup refuses is found by `lookup`; through a helper per key a 50-key structure cost 10%
    "assertpy/_matcher_impls.py::_walk": 16,
    "assertpy/errors.py::_render_diff": 14,
    "assertpy/snapshot.py::snapshot": 13,
    # a mapping with a non-string key is written as pairs, since rendered as text `1` and `"1"` were one key
    "assertpy/errors.py::_json_native": 14,
    "assertpy/string.py::contains_ignoring_case": 13,
    "assertpy/_engine/_compare.py::_build_compare_config": 11,
    "assertpy/async_assertions.py::record": 12,
    "assertpy/dynamic.py::__getattr__": 12,
    "assertpy/_dangling.py::_survey": 11,
    "assertpy/_dangling.py::findings": 11,
    # 12: an unorderable window answers, the classes are asked in place. As helpers: close_to 8%, two float64 10%
    "assertpy/_engine/_compare.py::_within_tolerance": 12,
    # 12: a broadcast and the class kept are read in place. As helpers: a datetime 10%, a Decimal against an int 12%
    "assertpy/_engine/_ordering.py::compare": 12,
    # one more name refused by the poll chain: check() after a poll used to skip the wait and answer nothing
    # 13: the chain refuses `value` by name, where the hook used to record it as an assertion
    # 15: an attempt holds its passes for `log_passes()` behind guards in place; as calls, a poll passing at once 3-4%
    "assertpy/async_assertions.py::__getattr__": 15,
    "assertpy/contains.py::contains": 11,
    "assertpy/json_mixin.py::_openapi_resolve": 11,
    # 12: a signalling NaN is answered in place. Through `equals` it cost a list's prefix check 7%
    "assertpy/string.py::ends_with": 12,
    # 12: as `ends_with`, for the same measured 7%
    "assertpy/string.py::starts_with": 12,
}
"""Every function over mccabe's default, keyed by file and name, measured 2026-08-29."""


def _measured() -> dict[str, int]:
    """What ruff reports at the default threshold, read from its own JSON."""
    needs("ruff")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "assertpy/",
            "--select",
            "C901",
            "--config",
            "lint.mccabe.max-complexity = 10",
            "--output-format",
            "json",
            "--no-cache",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=_ROOT,
        check=False,
    )
    # refuse rather than read an empty list as zero: a ruff that failed to start would read as a clean sweep
    if result.returncode not in (0, 1) or not result.stdout.strip():
        raise RuntimeError(f"ruff did not report: exit {result.returncode} {result.stderr}")
    found = {}
    for row in json.loads(result.stdout):
        match = _REPORTED.search(row["message"])
        if match is None:
            raise RuntimeError(f"unreadable C901 message, so a real change could hide in it: {row['message']}")
        # relative to the repository, because both the checkout and the package are named `assertpy`
        # and splitting on the name landed on the first of the two
        where = pathlib.Path(row["filename"]).resolve().relative_to(_ROOT).as_posix()
        key = f"{where}::{match.group(1)}"
        # ruff names the function and not the class, so two same-named methods in one file share a key.
        # Silently overwriting would let one of them grow behind the other
        if key in found:
            raise RuntimeError(f"two entries share {key}, so the record cannot tell them apart")
        found[key] = int(match.group(2))
    return found


def test_no_function_grew_more_complex() -> None:
    measured = _measured()
    grown = {
        name: f"{RECORDED.get(name, 0)} -> {score}" for name, score in measured.items() if score > RECORDED.get(name, 0)
    }
    assert_that(grown).described_as(
        "more complex than recorded. Say which function grew and why that was the cheaper answer"
    ).is_empty()


def test_the_record_is_not_stale() -> None:
    """A record nobody is near stops being a ratchet, so it has to be what ruff reports today."""
    assert_that(_measured()).described_as("recorded complexity, which has to be the measured one").is_equal_to(RECORDED)
