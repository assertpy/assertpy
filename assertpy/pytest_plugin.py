from __future__ import annotations

import argparse
import contextlib
import json
import os
import warnings
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Final, Protocol, cast

import pytest

from . import _clustering, _dangling, _inline, _renamed, _satisfies, async_assertions, errors
from . import snapshot as _snapshot
from ._engine._compat import BaseExceptionGroup
from ._engine._diff import _sub_diff_entries
from ._engine._introspection import laid_out
from ._engine._path import _ROOT
from .assertpy import _located, _numbered, _Room
from .errors import _diff_side, _diff_sides, _json_safe, _render_diff, _safe_repr, _told_apart
from .exception import _leaves, _nodes
from .outcome import AssertionOutcome

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path


class _Stashing(Protocol):
    """The config with what this plugin keeps on it declared, for checkers only.

    A hook is handed the real `Config` and hangs its own state on it, which is how pytest's own
    plugins do it, and `Config` declares none of those names, nor can it be subclassed to add them:
    it is final.  Annotating the parameter and stashing an attribute are therefore not both
    spellable, and the alternative, moving all of this to `config.stash` with typed keys, reaches 101
    sites in the suite besides the plugin's own.

    A protocol rather than a wider view on purpose: what a hook reaches through it is the stash and
    nothing else.  Declared once so the set of names is in a single place rather than spread over the
    hooks that write them.  At run time the object is the `Config` pytest passed.
    """

    _assertpy_profile: str
    _assertpy_allure_mode: str
    _assertpy_dangling_enabled: bool
    _assertpy_dangling_entries: frozenset[str]
    _assertpy_dangling: dict[Path, list[_dangling.Finding]]
    _assertpy_diff_enabled: bool
    _assertpy_diff_max: int
    _assertpy_comparison_enabled: bool
    _assertpy_prev_diff_in_message: bool
    _assertpy_prev_whole_values: bool
    _assertpy_prev_vacuous: bool
    _assertpy_prev_layout: str
    _assertpy_cluster_minimum: int | None
    _assertpy_poll_threshold: float | None
    _assertpy_failed_ids: set[str]
    _assertpy_failure_count: int
    _assertpy_failures: list[tuple[str, list[_clustering.Observation]]]


class _Worker(Protocol):
    """The config as xdist extends it inside a worker process.

    `workeroutput` is xdist's channel back to the controller.  Declared rather than narrowed out of
    the `hasattr` guard that stands in front of every use: narrowing on `hasattr` needs a subclass to
    narrow to, and `Config` is final.
    """

    workeroutput: dict[str, Any]


try:
    import allure  # ty: ignore[unresolved-import]  # optional dependency

    _HAS_ALLURE = True  # pragma: no cover - only when allure-pytest is installed
except ImportError:
    _HAS_ALLURE = False

_ALLURE_MODES: Final = frozenset({"off", "diff", "full"})


_FLAGS: Final = (
    "--assertpy-snapshot-update",
    "--assertpy-vacuous",
    "--assertpy-dangling",
    "--assertpy-snapshot-ci",
    "--assertpy-snapshot-no-ci",
)
_SETTINGS: Final = (
    "assertpy_profile",
    "assertpy_vacuous",
    "assertpy_allure",
    "assertpy_dangling",
    "assertpy_dangling_entries",
    "assertpy_diff",
    "assertpy_comparison",
    "assertpy_diff_max_entries",
    "assertpy_failure_clusters",
    "assertpy_poll_report",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--assertpy-snapshot-update",
        action="store_true",
        default=False,
        help="Overwrite failing assertpy snapshots with the current values instead of failing",
    )
    parser.addoption(
        "--assertpy-vacuous",
        action="store_true",
        default=False,
        help="Warn when a universal assertion passes over an empty value, having checked nothing",
    )
    parser.addoption(
        "--assertpy-dangling",
        action="store_true",
        default=False,
        help="Warn when assert_that() is used as a statement without asserting anything",
    )
    parser.addoption(
        "--assertpy-snapshot-ci",
        action="store_true",
        default=False,
        help="Fail instead of creating a missing assertpy snapshot (auto-enabled when a CI env is detected)",
    )
    parser.addoption(
        "--assertpy-snapshot-no-ci",
        action="store_true",
        default=False,
        help="Disable CI mode / its autodetection, allowing missing snapshots to be created",
    )
    parser.addini(
        "assertpy_snapshot_layout",
        help=(
            "Where a snapshot without path= is kept: cwd (default, __snapshots in the working directory) or"
            " beside (__snapshots beside the test file)"
        ),
        default="",
    )
    parser.addini(
        "assertpy_profile",
        help=(
            "Which guards a suite gets without naming them one by one: compatible (default), safe,"
            " strict (safe, and their findings fail the test rather than warn)"
        ),
        default="",
    )
    parser.addini(
        "assertpy_vacuous",
        help="Warn when a universal assertion passes over an empty value: off (default), on",
        default="",
    )
    parser.addini(
        "assertpy_allure",
        help="Allure attachment mode: off, diff (default), full",
        default="",
    )
    parser.addini(
        "assertpy_dangling",
        help="Warn about assert_that() statements that assert nothing: off (default), on",
        default="",
    )
    parser.addini(
        "assertpy_dangling_entries",
        help="Names of your own assert_that wrappers the dangling check should also read as builders",
        type="args",
        default=[],
    )
    parser.addini(
        "assertpy_diff",
        help="Structured diff sections in failure reports: on (default), off",
        default="",
    )
    parser.addini(
        "assertpy_comparison",
        help=(
            "Hand the two values a failed is_equal_to() or has_<name>() compared to pytest_assertrepr_compare"
            " listeners, which is how an IDE's test runner opens its comparison window: on (default), off"
        ),
        default="",
    )
    parser.addini(
        "assertpy_diff_max_entries",
        help="Max diff entries to show (0 = unlimited, default 50)",
        default="",
    )
    parser.addini(
        "assertpy_failure_clusters",
        help=(
            "Group failures sharing one difference: off, or the failing tests a cluster must hold "
            f"(default {_clustering.MINIMUM_SIZE})"
        ),
        default="",
    )
    parser.addini(
        "assertpy_poll_report",
        help="Name polls that converged this close to their deadline: off, or a fraction (default 0.7)",
        default="",
    )
    for flag in _FLAGS:
        parser.addoption(_renamed.old_name(flag), action="store_true", default=False, help=argparse.SUPPRESS)
    for setting in _SETTINGS:
        parser.addini(
            _renamed.old_name(setting),
            help=f"Deprecated name of {setting}, read until assertpy 3.0",
            type="args" if setting == "assertpy_dangling_entries" else None,
            default=[] if setting == "assertpy_dangling_entries" else "",
        )


def _option(config, name: str) -> bool:
    """Whether a flag was given, by its own name or by its assertpy2 one."""
    if config.getoption(name):
        return True
    old = _renamed.old_name(name)
    if not config.getoption(old):
        return False
    _renamed.tell(f"--{old.replace('_', '-')}", f"--{name.replace('_', '-')}")
    return True


def _layout(config) -> str:
    """Where a snapshot without ``path=`` is kept, as ``assertpy_snapshot_layout`` says: ``cwd`` unless written."""
    written = config.getini("assertpy_snapshot_layout").strip().lower()
    if written not in ("", "cwd", "beside"):
        raise pytest.UsageError(f"assertpy_snapshot_layout must be cwd or beside, not {written!r}")
    return written or "cwd"


def _given(value: object) -> bool:
    """Whether a setting was written: a blank string and an empty list are not."""
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def _ini(config, name: str) -> Any:
    """A setting as the suite wrote it, read by its assertpy2 name where its own is blank.

    Blank rather than absent: pytest 9 deprecates `config.inicfg`, the one way to ask whether a key was
    written at all, so a current setting written empty does not clear an old one.
    """
    written = config.getini(name)
    old = _renamed.old_name(name)
    before = config.getini(old)
    if not _given(before):
        return written
    _renamed.tell(old, name)
    return written if _given(written) else before


_ALL_ON: Final = {"assertpy_dangling": "on", "assertpy_vacuous": "on"}

# What a profile answers for a setting the suite did not name.  Both guards are off under `compatible`,
# since they can turn an inherited suite green run red; `strict` turns them on and fails what they find.
# Failure clustering has its own default: it costs a passing suite nothing, it reads a run already red
_PROFILES: Final = {
    "compatible": {"assertpy_dangling": "off", "assertpy_vacuous": "off"},
    "safe": _ALL_ON,
    "strict": _ALL_ON,
}

_ESCALATING: Final = "strict"
"""The profile that turns the two guards' warnings into failures."""


def _profile(config) -> str:
    """Which profile answers, resolved once: an empty setting is the default rather than a mistake.

    Once, because both settings ask for it independently and a name nobody declared would otherwise
    warn once per question, which reads as two separate mistakes in one config.
    """
    cached = getattr(config, "_assertpy_profile", None)
    if cached is not None:
        return cached
    name = str(_ini(config, "assertpy_profile")).strip().lower()
    if name and name not in _PROFILES:
        warnings.warn(
            f"assertpy_profile={name!r} is not one of ({', '.join(sorted(_PROFILES))}), falling back to 'compatible'",
            stacklevel=1,
        )
        name = ""
    config._assertpy_profile = name or "compatible"
    return config._assertpy_profile


def _written(config, name: str) -> str:
    """What the suite wrote for a setting, empty where it wrote nothing.

    The two settings a profile answers for are registered with no default of their own, so this tells
    "the suite wrote off" from "the suite said nothing about it", which is the whole of the resolution.
    """
    return str(_ini(config, name)).strip()


def _setting(config, name: str) -> str:
    """What a setting resolves to: what the suite wrote, or what its profile answers for it.

    Named settings win over the profile, so `safe` plus `assertpy_dangling = off` is a suite that
    wants the other two and has said why in its own config rather than in a comment somewhere.
    """
    return _written(config, name) or _PROFILES[_profile(config)][name]


def _vacuous_guard(config) -> bool:
    """Whether the vacuous-quantifier guard runs, with the three ways of asking it ranked.

    The flag is the loudest and wins.  A written setting comes next, and it has to be able to say `off`:
    the environment variable is how the guard is turned on away from pytest, and a suite that inherited
    one from its CI image could not turn it off in its own config, which is where a reader looks.  Where
    the suite said nothing, `safe` turns it on and `compatible` leaves the variable as it found it.
    """
    if _option(config, "assertpy_vacuous"):
        return True
    written = _written(config, "assertpy_vacuous").lower()
    if written in ("on", "off"):
        return written == "on"
    if written:
        # a typo must not read as `off`: this is a guard, and the quiet answer is the dangerous one
        warnings.warn(
            f"assertpy_vacuous={written!r} is not 'on' or 'off', falling back to the profile",
            stacklevel=1,
        )
    return _PROFILES[_profile(config)]["assertpy_vacuous"] == "on" or _satisfies._VACUOUS_GUARD


def _poll_threshold(raw: object) -> float | None:
    """Parse the near-timeout reporting bar: ``off`` silences the report, a fraction moves it.

    A slow CI box converges late on every poll, where the default bar turns a signal into a line of
    noise per run.  ``None`` means the report is off, and collection is skipped with it.

    A blank value is the default and is not warned about, for the reason `_cluster_minimum` gives.
    """
    written = str(raw).strip()
    if written.lower() == "off":
        return None
    if not written:
        return 0.7
    try:
        value = float(written)
    except ValueError:
        value = 0.0
    if not 0.0 < value <= 1.0:
        warnings.warn(
            f"assertpy_poll_report={written!r} is not 'off' or a fraction in (0, 1], falling back to 0.7",
            stacklevel=1,
        )
        return 0.7
    return value


def _cluster_minimum(raw: object) -> int | None:
    """Parse how many failing tests a cluster must hold: ``off`` silences the summary, a count moves it.

    ``None`` means the summary is off, and the per-failure recording is skipped with it, so a run that
    does not want the summary pays nothing for it.

    A count rather than a share of the run, which was tried first and measured strictly worse: under a
    share every additional cause raises the bar for all the others, so a run splitting cleanly into
    five causes of eight printed nothing at all.

    A blank value is the default and not a mistake, so it is not warned about.  It has to be: a warning
    raised here would come out of `pytest_configure`, and under `-W error` a suite carrying an empty
    line for this setting would fail at startup having passed the day before.
    """
    written = str(raw).strip()
    if written.lower() == "off":
        return None
    if not written:
        return _clustering.MINIMUM_SIZE
    try:
        value = int(written)
    except ValueError:
        value = 0
    if value < 2:
        warnings.warn(
            f"assertpy_failure_clusters={written!r} is not 'off' or a count of 2 or more, "
            f"falling back to {_clustering.MINIMUM_SIZE}",
            stacklevel=1,
        )
        return _clustering.MINIMUM_SIZE
    return value


def _dangling_enabled(config) -> bool:
    """Whether the dangling check runs, from the flag or the ini setting.

    The flag wins: a run that asks for the check on the command line gets it whatever the file says,
    which is how somebody tries it once without editing a config they share with everybody else.
    """
    if _option(config, "assertpy_dangling"):
        return True
    setting = _setting(config, "assertpy_dangling").lower()
    if setting not in {"on", "off"}:
        warnings.warn(
            f"assertpy_dangling={setting!r} is not 'on' or 'off', falling back to 'off'",
            stacklevel=1,
        )
        return False
    return setting == "on"


def _dangling_entries(config) -> frozenset[str]:
    """The project's own wrapper names the dangling check should treat as builder factories.

    Only a plain name can bind through an import, so anything else is dropped with a warning rather
    than kept to match nothing: `helpers.check` in a config file looks like it works, and a check that
    silently covers none of what it was told to cover is worse than one that is off.
    """
    names = {str(name).strip() for name in _ini(config, "assertpy_dangling_entries") or ()}
    usable = {name for name in names if name.isidentifier()}
    if rejected := sorted(names - usable):
        warnings.warn(
            f"assertpy_dangling_entries: {', '.join(repr(name) for name in rejected)} "
            f"{'is not a plain name' if len(rejected) == 1 else 'are not plain names'} "
            f"and cannot be matched, ignoring",
            stacklevel=1,
        )
    return frozenset(usable)


def _escalate(config) -> None:
    """Under `strict`, make the two guards' warnings fail the test that raised one.

    Scoped to this library's own two categories rather than set as a blanket `filterwarnings = error`,
    which would change the meaning of every `DeprecationWarning` a suite's other dependencies raise.

    Both filters go in whether or not their guard is on, because a guard that is off raises nothing for
    the filter to catch.  Asking first read as a safeguard and was measured to change nothing.

    Failure clustering is not here and cannot be: it reads a run that already went red.
    """
    if _profile(config) != _ESCALATING:
        return
    for category in (errors.DanglingAssertionWarning, errors.VacuousAssertionWarning):
        config.addinivalue_line("filterwarnings", f"error::{category.__module__}.{category.__qualname__}")


def pytest_configure(config: pytest.Config) -> None:
    stashed = cast("_Stashing", config)
    mode = str(_ini(config, "assertpy_allure")).strip() or "diff"
    if mode not in _ALLURE_MODES:
        warnings.warn(
            f"assertpy_allure={mode!r} is not a valid mode "
            f"({', '.join(sorted(_ALLURE_MODES))}), falling back to 'diff'",
            stacklevel=1,
        )
        stashed._assertpy_allure_mode = "diff"
    else:
        stashed._assertpy_allure_mode = mode
    stashed._assertpy_dangling_enabled = _dangling_enabled(config)
    stashed._assertpy_dangling_entries = _dangling_entries(config)
    stashed._assertpy_diff_enabled = _ini(config, "assertpy_diff") != "off"
    stashed._assertpy_comparison_enabled = _ini(config, "assertpy_comparison") != "off"
    try:
        stashed._assertpy_diff_max = int(_ini(config, "assertpy_diff_max_entries"))
    except (ValueError, TypeError):
        stashed._assertpy_diff_max = 50
    # the plugin hangs the diff on the failure itself; the prior value is restored, not forced, so hooks stay balanced
    stashed._assertpy_prev_diff_in_message = errors._RENDER_DIFF_IN_MESSAGE
    errors._RENDER_DIFF_IN_MESSAGE = False
    # at -vv pytest stops shortening, and so does a message: what the cap left out is whole there
    stashed._assertpy_prev_whole_values = errors._WHOLE_VALUES
    errors._WHOLE_VALUES = int(config.getoption("verbose") or 0) >= 2
    stashed._assertpy_cluster_minimum = _cluster_minimum(_ini(config, "assertpy_failure_clusters"))
    _session_config[0] = config
    stashed._assertpy_failures = []
    stashed._assertpy_failure_count = 0
    stashed._assertpy_poll_threshold = _poll_threshold(_ini(config, "assertpy_poll_report"))
    # nothing reads the samples once the report is off, so stop paying for them at the poll site
    async_assertions._COLLECT_RETRIES = stashed._assertpy_poll_threshold is not None
    # save and restore rather than force back: the environment variable may have turned the guard on before import
    stashed._assertpy_prev_vacuous = _satisfies._VACUOUS_GUARD
    _satisfies._VACUOUS_GUARD = _vacuous_guard(config)
    _escalate(config)
    if _option(config, "assertpy_snapshot_update"):
        _snapshot._UPDATE_ALL = True
    stashed._assertpy_prev_layout = _snapshot._LAYOUT
    _snapshot._LAYOUT = _layout(config)
    if _option(config, "assertpy_snapshot_ci"):
        _snapshot._CI_MODE = True
    elif _option(config, "assertpy_snapshot_no_ci"):
        _snapshot._CI_MODE = False


def pytest_unconfigure(config: pytest.Config) -> None:
    errors._RENDER_DIFF_IN_MESSAGE = getattr(config, "_assertpy_prev_diff_in_message", True)
    errors._WHOLE_VALUES = getattr(config, "_assertpy_prev_whole_values", False)
    async_assertions._COLLECT_RETRIES = False
    async_assertions._RETRIES.clear()
    # the report reads this at the end of a session, so a second one in the same process reported the first
    _retried.clear()
    # module-level, so a second session would open with the first one's failures, consumed by a hook that may not run
    _controller_failures.clear()
    _controller_failure_count[0] = 0
    _controller_lost_workers[0] = 0
    _controller_unreadable_workers[0] = 0
    _controller_collect_errors[0] = 0
    _session_config[0] = None
    previous = getattr(config, "_assertpy_prev_vacuous", None)
    _satisfies._VACUOUS_GUARD = _satisfies._env_enabled() if previous is None else previous
    if _option(config, "assertpy_snapshot_update"):
        _snapshot._UPDATE_ALL = False
    _snapshot._LAYOUT = getattr(config, "_assertpy_prev_layout", "cwd")
    if _option(config, "assertpy_snapshot_ci") or _option(config, "assertpy_snapshot_no_ci"):
        _snapshot._CI_MODE = None


# snapshots touched by xdist workers, collected on the controller as each worker finishes
_controller_touched: set = set()

# workers must not rewrite shared source files in parallel
_controller_inline: list = []

# node ids that reached each snapshot key, shipped by xdist workers and unioned on the controller
_controller_accesses: dict = {}

# the summary is written on the controller, and a worker's own config is not the controller's
_controller_failures: list = []
_controller_failure_count: list = [0]
_controller_lost_workers: list = [0]
_controller_unreadable_workers: list = [0]
_controller_collect_errors: list = [0]

# the session's config, for the one hook that is handed a report and no way back to it
_session_config: list = [None]


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list[pytest.Item]) -> None:
    """Read every collected test file once and record the statements that assert nothing.

    Collection rather than runtime: the check is static (see `_dangling`), so a selected subset
    (`-k`, `--lf`) is the subset that gets read, and each path is read once however many items it
    contributed.  The findings are only *recorded* here; they are reported from `runtest_setup`,
    because a warning raised out of a collection hook under `-W error` aborts pytest with an
    INTERNALERROR instead of failing anything a reader can act on.
    """
    stashed = cast("_Stashing", config)
    stashed._assertpy_dangling = {}
    if not getattr(config, "_assertpy_dangling_enabled", False):
        return
    for item in items:
        path = getattr(item, "path", None)
        if path is None or path in stashed._assertpy_dangling:  # pragma: no cover - items carry a path
            continue
        try:
            source = _dangling.read_module(path)
            entries = getattr(config, "_assertpy_dangling_entries", frozenset())
            stashed._assertpy_dangling[path] = _dangling.findings(source, str(path), entries)
        except (OSError, SyntaxError):  # pragma: no cover - pytest imported the module, so it read and parsed
            stashed._assertpy_dangling[path] = []


def _item_scope(item) -> tuple[str, ...]:
    """The test's own scope chain, matching what the static pass recorded: ``("TestOne", "test_same")``.

    Read from `__qualname__` rather than assembled from `item.cls`, which names only the innermost
    class: a method of a class nested in another class is `TestOuter.TestInner.test_it` to the source
    and only `TestInner.test_it` to that attribute, and the two chains then failed to line up.

    A function name alone is worse than either: two classes in one file may each define `test_same`,
    and a finding matched by name went to whichever ran first.
    """
    qualname = getattr(getattr(item, "function", None), "__qualname__", None)
    if not qualname:
        return ()
    return tuple(part for part in qualname.split(".") if part != "<locals>")


def _report_dangling(item):
    """Warn once per file, on the first test to run from it, so pytest attributes it to that node.

    `warn_explicit` rather than `warn`: the location that matters is the offending statement, not
    this line, and a reader jumping to the warning should land in their own test file.
    """
    config = getattr(item, "config", None)  # a hook driven directly in a test carries no config
    recorded = getattr(config, "_assertpy_dangling", {})
    found = recorded.get(getattr(item, "path", None))
    if not found:
        return
    here = _item_scope(item)
    # a finding outside any def has no test to attach to, so the first item takes it
    mine = [one for one in found if not one.scope or (here and one.scope[: len(here)] == here)]
    if not mine:
        return
    recorded[item.path] = [one for one in recorded[item.path] if one not in mine]
    # one warning per test: under `-W error` the first leaves this function, so a second is never reported
    first, rest = mine[0], mine[1:]
    message = first.message
    if rest:
        lines = ", ".join(str(one.lineno) for one in rest)
        message = f"{message} (and {len(rest)} more in this test, at line{'' if len(rest) == 1 else 's'} {lines})"
    warnings.warn_explicit(message, errors.DanglingAssertionWarning, first.path, first.lineno)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Name the running test, so a snapshot key reached by two of them can be told from a helper that
    snapshots twice inside one."""
    _snapshot._CURRENT_NODE = item.nodeid
    _report_dangling(item)


def pytest_collectreport(report: pytest.CollectReport) -> None:
    """Note a collection that failed, which is red and never reaches a test report.

    `--continue-on-collection-errors` runs the rest of the suite, so pytest ends with `3 failed, 1 error`
    while the summary saw only the three and said `3 of 3`.  Counted on its own line rather than into the
    denominator, because a collector is not a test and `3 of 4 failing tests` would name a fourth test
    that does not exist.  Without that flag the run stops and no summary is written, so this costs nothing in
    the ordinary case.

    The report arrives without its config, and this hook is the only place a collection failure is
    visible, which is what the session-level reference is for.
    """
    config = _session_config[0]
    if config is None or not report.failed or hasattr(config, "workeroutput"):
        # not on a worker: each collects the whole suite, so counting there made one broken module one result per worker
        return
    if getattr(config, "_assertpy_cluster_minimum", None) is not None:
        _controller_collect_errors[0] += 1


@pytest.hookimpl(optionalhook=True)  # xdist-provided hook: silently ignored when xdist is not installed
def pytest_testnodedown(node: Any, error: object) -> None:
    """xdist controller hook: collect the touched snapshots and inline edits each worker shipped.

    ``error`` is set when the worker died rather than finished.  Then it never ran its `sessionfinish`,
    so whatever it had recorded never left it, and the cluster summary would otherwise report a share
    of the failures it happened to receive as though that were the whole run.
    """
    if error is not None:
        _controller_lost_workers[0] += 1
    _collect_worker_failures(node, died=error is not None)
    touched = getattr(node, "workeroutput", {}).get("assertpy_touched")
    if touched:
        _controller_touched.update(tuple(item) for item in touched)
    retried = getattr(node, "workeroutput", {}).get("assertpy_retried")
    if retried:
        _retried.extend(tuple(row) for row in retried)
    inline = getattr(node, "workeroutput", {}).get("assertpy_inline")
    if inline:
        _controller_inline.extend(tuple(record) for record in inline)
    accesses = getattr(node, "workeroutput", {}).get("assertpy_accesses")
    if accesses:
        # unioned here: two parametrised cases on two workers are one node id each locally
        for snapname, key, nodes, site in accesses:
            _controller_accesses.setdefault((snapname, key), set()).update(nodes)
            _snapshot._ACCESS_SITES.setdefault((snapname, key), site)


def _is_full_run(config) -> bool:
    """Whether the run selected all tests (no ``-k`` / ``-m`` / ``--lf`` / ``--ff`` and no nodeid
    selection).  Orphan detection is only reliable on a full run, since a deselected or nodeid-selected
    live test would otherwise look obsolete."""
    opt = config.option
    if any("::" in str(arg) for arg in getattr(opt, "file_or_dir", None) or ()):
        return False  # a nodeid selection (path::test) runs only a subset of a file's tests
    return not (
        getattr(opt, "keyword", "")
        or getattr(opt, "markexpr", "")
        or getattr(opt, "last_failed", False)
        or getattr(opt, "failed_first", False)
    )


_retried: list[tuple[str, int, float, float]] = []


def _drain_retries(nodeid: str) -> None:
    """Move any retried polls this test performed onto the run-level list, tagged with the test."""
    for attempts, elapsed, budget in async_assertions._RETRIES:
        _retried.append((nodeid, attempts, elapsed, budget))
    async_assertions._RETRIES.clear()


def _report_retries(config) -> None:
    """Name the polls that converged against their deadline: that run passed, the next one may not.

    Retrying is what ``eventually()`` is for, so a retry on its own says nothing.  Spending most of the
    budget before converging is what turns into a failure on a slower machine.
    """
    threshold = getattr(config, "_assertpy_poll_threshold", 0.7)
    if threshold is None:
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    late = [row for row in _retried if row[3] and row[2] / row[3] >= threshold]
    if not late:
        return
    reporter.write_line("")
    reporter.write_line("assertpy polls that nearly timed out:")
    for nodeid, attempts, elapsed, budget in late:
        reporter.write_line(
            f"  {nodeid}: converged on attempt {attempts} at {elapsed:.2f}s of {budget:.1f}s"
            f" ({elapsed / budget:.0%} of the budget)"
        )


def _warn_on_reused_snapshot_keys(session) -> None:
    """Report every reused snapshot key, with the number of tests that reached it.

    `assertpy.snapshot._record_access()` raises the warning that is worth reading, from inside the
    assertion: pytest attributes it to a nodeid, puts it in the normal summary, and under ``-W error``
    fails that test rather than this hook.  What it cannot do is count.  It fires when the second test
    arrives, with more still to come, and it never sees the other xdist workers - parametrised cases
    split across them are one access each, so no worker sees a second reach and only the union does.

    The count therefore lives here, where every access has been collected, and this runs for every
    reused key rather than only for the ones no worker reported.  Two messages about one key is the
    price: the first says where it happened, this one says how big it is.
    """
    totals: dict = {key: set(nodes) for key, nodes in _snapshot._ACCESS_NODES.items()}
    for key, nodes in _controller_accesses.items():
        totals.setdefault(key, set()).update(nodes)
    _snapshot._ACCESS_NODES.clear()
    _controller_accesses.clear()
    _snapshot._WARNED.clear()
    for (snapname, key), nodes in sorted(totals.items()):
        if len(nodes) < 2:
            continue
        message = _snapshot._reuse_message(snapname, key, _snapshot._ACCESS_SITES.get((snapname, key), ""), len(nodes))
        try:
            warnings.warn(message, _snapshot.SnapshotKeyReusedWarning, stacklevel=1)
        except _snapshot.SnapshotKeyReusedWarning:
            _fail_the_run(session, message)
    _snapshot._ACCESS_SITES.clear()


def _fail_the_run(session, message: str) -> None:
    """Turn a problem found after the last test into a failed run instead of a broken hook.

    An escalated sweep warning, or an inline snapshot that could not be written.  An ``error`` entry in
    the warning filters raises here rather than at a test, and an exception out of a session-finish hook
    is an INTERNALERROR with this module's traceback in it - which buries the message the reader needs
    under a stack that points at the wrong place.  Print it and go red.
    """
    # only a run that otherwise succeeded: reached from a `finally`, so Ctrl-C and an internal error land here too
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    reporter.write_line("")
    reporter.write_line(f"ERROR: {message}", red=True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if hasattr(config, "workeroutput"):  # xdist worker: ship recorded work to the controller, defer the rest
        worker = cast("_Worker", config)
        worker.workeroutput["assertpy_touched"] = [list(item) for item in _snapshot._TOUCHED]
        worker.workeroutput["assertpy_inline"] = _inline.shipped()
        worker.workeroutput["assertpy_retried"] = [list(row) for row in _retried]
        worker.workeroutput["assertpy_failures"] = [
            [nodeid, [_observation_to_wire(one) for one in found]]
            for nodeid, found in getattr(config, "_assertpy_failures", [])
        ]
        worker.workeroutput["assertpy_failure_count"] = getattr(config, "_assertpy_failure_count", 0)
        worker.workeroutput["assertpy_accesses"] = [
            [snapname, key, sorted(nodes), _snapshot._ACCESS_SITES.get((snapname, key), "")]
            for (snapname, key), nodes in _snapshot._ACCESS_NODES.items()
        ]
        return
    # controller / single process: apply inline edits (workers' plus any recorded here) into source
    _report_retries(config)
    _warn_on_reused_snapshot_keys(session)
    rows = [*_inline.shipped(), *_controller_inline]
    _controller_inline.clear()
    for problem in _inline.apply_inline_records(rows, str(config.rootpath)):
        _fail_the_run(session, problem)
    touched = set(_snapshot._TOUCHED) | _controller_touched
    _controller_touched.clear()
    if not touched or not _is_full_run(config):
        # on a subset run the touched set is incomplete, so pruning would delete a live sibling
        return
    sub_orphans, whole_orphans = _snapshot._find_orphans(touched)
    if not sub_orphans and not whole_orphans:
        return
    pruned = []
    # prune obsolete sub-snaps only under update mode; whole files are always report-only
    if sub_orphans and _snapshot._update_enabled():
        _snapshot._prune_sub_key_orphans(sub_orphans)
        pruned, sub_orphans = sub_orphans, []
    _report_snapshot_orphans(config, sub_orphans, whole_orphans, pruned)


def _refuse(value: object) -> bool:
    """Raise, from inside a comprehension's condition, where a plain `raise` cannot go."""
    raise TypeError(value)


def _collect_worker_failures(node, died: bool = False) -> None:
    """Take one worker's recorded failures, or leave the worker counted as lost.

    Everything here came off the wire, and a controller running one version of this library against a
    worker running another is a real installation.  A row that does not unpack must not take down a hook
    that pytest answers with INTERNALERROR, and it must not be silently dropped either: the summary
    reports what share of the run it explains, so a worker whose failures went missing is the same
    situation as a worker that died.

    Unreadable is counted apart from dead (``died``), because the two are different claims about the run
    and a worker that finished must not be reported as having crashed.  A worker that already counted as
    dead is not looked at here at all: it has one thing wrong with it, not two.

    Both wire values are read outright rather than defaulted, which is what makes a worker that shipped
    neither unreadable rather than invisible.  This version ships both from every worker, summary on or
    off, so their absence is a worker that does not speak this protocol, and its failures are missing from
    the denominator: leaving that unsaid is how a run of twelve prints a confident `6 of 6`.

    Node ids are prefixed with the worker's own name because two workers can legitimately report the
    same test: `--dist=each` runs the whole suite on every worker.  Without the prefix the denominator
    counted both executions and the cluster counted one, and the summary reported a run half unexplained
    when nothing was unexplained at all.
    """
    if died:  # already counted, and a worker that never finished has nothing to have shipped
        return
    output = getattr(node, "workeroutput", {})
    worker = getattr(node, "gateway", None)
    prefix = getattr(worker, "id", "") or ""
    try:
        received = [
            (f"{prefix}::{nodeid}", [_observation_from_wire(one) for one in found])
            for nodeid, found in output["assertpy_failures"]
            if isinstance(nodeid, str) or _refuse(nodeid)
        ]
        counted = output["assertpy_failure_count"]
        # both halves or neither, checked rather than coerced, since `int()` would take `True` and `3.9`
        if isinstance(counted, bool) or not isinstance(counted, int):
            raise TypeError(counted)
        if counted < len({nodeid for nodeid, _ in received}):
            raise ValueError(counted)
    except Exception:  # pragma: no cover - the guard itself; a malformed payload is tested through it
        _controller_unreadable_workers[0] += 1
        return
    _controller_failures.extend(received)
    _controller_failure_count[0] += counted


def _observation_to_wire(one):
    """An observation as plain lists, which is all execnet can carry between worker and controller."""
    key = one.signature
    steps = [list(step) for step in key.steps]
    return [key.located, key.where, steps, key.label, list(key.values), one.actual, one.expected]


def _observation_from_wire(row):
    """Rebuild an observation the controller can group by, refusing anything it could not group by.

    Tuples again, not lists: the signature *is* the cluster key, so it has to hash, and a list inside it
    would raise the moment the controller tried to group anything a worker sent.

    Each field is checked rather than trusted, because a row of the right length can still hold the wrong
    thing.  A list where a value belongs unpacks happily and then raises out of the grouping, past the
    point where the worker could be reported as unreadable: the summary simply vanished, and the run said
    nothing about why.
    """
    located, where, steps, label, values, actual, expected = row
    if not (
        isinstance(located, bool)
        and all(isinstance(field, str) for field in (where, label, actual, expected))
        and all(isinstance(one, str) for one in values)
        and all(len(step) == 2 and all(isinstance(part, str) for part in step) for step in steps)
    ):
        raise TypeError(row)
    key = _clustering.Signature(located, where, tuple(tuple(step) for step in steps), label, tuple(values))
    if not _clustering.is_well_formed(key):
        raise ValueError(key)
    return _clustering.Observation(key, actual, expected)


def _record_for_clustering(config, nodeid, exc):
    """Note what one failure differed at, for the end-of-run summary.

    Counted even when it carries no diff, and even when there is no exception to ask - a strict xfail
    that passed is red and holds nothing - because the summary reports how much of the run it accounts
    for, and that is only meaningful against every failure.

    The failure's own diagnostic line keys the differences that have no location, so it is asked for
    here, while the values are still at hand.
    """
    if getattr(config, "_assertpy_cluster_minimum", None) is None:
        return
    # node ids, not a counter: a retried test is reported failing once per attempt
    failed = getattr(config, "_assertpy_failed_ids", None)
    if failed is None:
        failed = config._assertpy_failed_ids = set()
    failed.add(nodeid)
    config._assertpy_failure_count = len(failed)
    try:
        # inside the guard: `diff` is our name on somebody else's exception, and one that raised took the run down
        diff = getattr(exc, "diff", None)
        # the hint the failure already computed; `_outcome` is absent on a failure raised outside the fluent path
        outcome = getattr(exc, "_outcome", None)
        label = getattr(outcome, "hint", None)
        found = _clustering.observations_of(diff, label)
    except Exception:
        # a report hook is no place to raise from: pytest answers with INTERNALERROR and the run's results are lost
        return
    if found:
        config._assertpy_failures.append((nodeid, found))


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    """Say in a line what the failures had in common, when enough of them had anything in common.

    This hook rather than `pytest_sessionfinish`, which runs before the tracebacks are printed and puts
    the summary above all of them.  Here it lands in the closing block, immediately above
    `short test summary info`.

    Not below it, and that is not a choice: the terminal reporter writes that list from the `finally`
    of its own wrapper around this hook, so every third-party implementation runs first.  Measured with
    a plain implementation, with `trylast`, and with a wrapper printing after its yield - all three
    land in the same place.
    """
    try:
        _write_cluster_summary(terminalreporter, config)
    except Exception as exc:  # pragma: no cover - the barrier itself; its parts are tested directly
        # `Exception`, not `BaseException`: a Ctrl-C or a SystemExit through here still has to travel
        with contextlib.suppress(Exception):
            # the notice is suppressed too: under `-W error` it would replace the failure with its own traceback
            warnings.warn(f"assertpy could not write its failure-cluster summary: {exc!r}", stacklevel=1)


def _write_cluster_summary(terminalreporter, config) -> None:
    """Build and print the summary, or return having printed nothing."""
    minimum = getattr(config, "_assertpy_cluster_minimum", None)
    # a worker's failures arrive through `pytest_testnodedown`, and the controller runs none of its own
    total = getattr(config, "_assertpy_failure_count", 0) + _controller_failure_count[0]
    recorded = [*getattr(config, "_assertpy_failures", []), *_controller_failures]
    if minimum is None or total < minimum:
        return
    found = _clustering.clusters(recorded, total, minimum=minimum)
    lines = _clustering.render(
        found,
        total,
        _controller_lost_workers[0],
        _controller_unreadable_workers[0],
        minimum=minimum,
        collect_errors=_controller_collect_errors[0],
    )
    if not lines:
        return
    terminalreporter.write_line("")
    terminalreporter.write_line("assertpy failure clusters:")
    for line in lines:
        terminalreporter.write_line(f"  {line}")


def _shown(snapname: str) -> str:
    """A snapshot file as the report names it: from the working directory where it lies under it."""
    relative = (
        os.path.relpath(snapname) if os.path.splitdrive(snapname)[0] == os.path.splitdrive(os.getcwd())[0] else ""
    )
    return relative if relative and not relative.startswith(os.pardir) else snapname


def _report_snapshot_orphans(config, sub_orphans, whole_orphans, pruned):
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:  # pragma: no cover - the terminal reporter is always present under pytest
        return
    lines = [f"removed obsolete snapshot: {_shown(snap)}::{key}" for snap, key in pruned]
    lines += [
        f"obsolete snapshot (run --assertpy-snapshot-update on a full run to remove): {_shown(snap)}::{key}"
        for snap, key in sub_orphans
    ]
    lines += [f"obsolete snapshot file (delete manually if its test is gone): {_shown(snap)}" for snap in whole_orphans]
    reporter.write_line("")
    reporter.write_line("assertpy snapshots:")
    for line in lines:
        reporter.write_line(f"  {line}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Generator[None, Any, None]:
    outcome = yield
    report = outcome.get_result()

    # every phase, not just "call": a fixture polling in teardown would tag its retries with the next test
    _drain_retries(report.nodeid)
    if not report.failed:
        return

    # ahead of the gates and without needing an exception: it counts an erroring fixture and a strict xpass too
    exc = call.excinfo.value if call.excinfo is not None else None
    _record_for_clustering(item.config, report.nodeid, exc)

    if exc is None:
        return

    # pytest groups two failing finalizers, and numbering follows the order the traceback prints them in
    leaves = _leaves(exc)
    room, attachments = _Room(), _Room()
    for position, leaf in enumerate(leaves, 1):
        if isinstance(leaf, AssertionError):
            suffix = f" ({position} of {len(leaves)})" if len(leaves) > 1 else ""
            # two barriers: a `diff` property that raised took the run down, and one refusal must not cost the other
            with contextlib.suppress(Exception):
                _attach_report_sections(item, report, leaf, suffix=suffix)
            with contextlib.suppress(Exception):
                _attach_to_allure(item, report, leaf)
        # any leaf: an exception of the caller's that escaped a soft block carries what the block had collected
        within = f"leaf {position} of {len(leaves)}, " if len(leaves) > 1 else ""
        _attach_collected(item, report, leaf, room, attachments, within)
    # and so does a group of the caller's, which no leaf is
    carriers = [node for node in _nodes(exc) if isinstance(node, BaseExceptionGroup) and _carries(node)]
    for position, node in enumerate(carriers, 1):
        within = "group, " if len(carriers) == 1 else f"group {position} of {len(carriers)}, "
        _attach_collected(item, report, node, room, attachments, within)

    # one pair is all a listener keeps, so a group of failures hands none
    if len(leaves) == 1 and getattr(item.config, "_assertpy_comparison_enabled", True):
        # the record is on an exception of anyone's and a listener is another plugin's code: neither costs the report
        with contextlib.suppress(Exception):
            compared = _compared_pair(leaves[0])
            if compared is not None:
                left, right = _for_a_listener(compared)
                item.config.hook.pytest_assertrepr_compare(config=item.config, op="==", left=left, right=right)


def _compared_pair(exc: BaseException) -> tuple[object, object] | None:
    """The two values a failed equality held against each other, or ``None`` for any other failure.

    `pytest_assertrepr_compare` is the hook pytest calls for a failed ``assert left == right``, and a test runner
    that shows the two sides in a comparison window listens to it: PyCharm's does.  It gave assertpy's failures
    that window by reading their message, which a failure of this class no longer matches.

    The pair is on the failure because the assertion that failed put it there, and only an equality does:
    ``is_equal_to()`` and a dynamic ``has_<name>()``.  It is the pair ``==`` alone decided.  Under ``ignore=``
    or ``include=`` that is the two copies without the keys left out, and under ``tolerance=``,
    ``comparators=``, ``strict_types=`` or ``ignore_null=`` there is none.  A negation, a membership and a
    block of several failures hold no pair that was compared.  A listener compares two texts, as for a plain
    ``assert``: ``1`` beside ``True`` differs there, two NaNs do not.

    A listener hears it once this hook's wrapper has resumed, which is before any report is logged: one that
    reads the pair in a report wrapper of its own that resumes earlier does not.
    """
    if not isinstance(exc, errors.AssertionFailure):
        # anything may sit under the name on another exception
        return None
    try:
        pair = exc._compared
    except Exception:  # a subclass may answer the name with code of its own, which must not cost the report
        return None
    return pair if type(pair) is tuple and len(pair) == 2 else None


def _for_a_listener(pair: tuple[object, object]) -> tuple[object, object]:
    """The pair as a listener can lay it out: a record taken apart under ``ignore=`` or ``include=`` is handed as
    the dict of its fields.

    A listener prints each side with `pprint`, which breaks a dict into lines and prints a class it does not know
    on one, whatever its length, so a record read `Row(...)` on a single line beside a dict sorted by key.  Under
    those options the two were compared by their fields.  A pair too deep to walk is handed as it is.
    """
    try:
        return laid_out(pair[0]), laid_out(pair[1])
    except Exception:
        return pair


def _named(exc) -> tuple[bool, bool]:
    """Which sides a failure named, read from its record where it has one.

    `expected` alone cannot tell "compared against None" from "no expected value".  A failure built by
    hand, by `eventually()` or by a snapshot re-wrap has no record, and its values are all there is.
    """
    outcome = getattr(exc, "_outcome", None)
    if outcome is None:
        return getattr(exc, "actual", None) is not None, getattr(exc, "expected", None) is not None
    return outcome.actual_provided, outcome.has_expected


_COLORED: Final = "_assertpy_colored"
"""The report attribute holding each diff section's colored text, which xdist carries like any attribute."""


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    # every report passes here, on a worker and again on the controller, which rebuilds the representation
    colored = vars(report).get(_COLORED)
    if colored and callable(getattr(report.longrepr, "addsection", None)):
        _color_when_drawn(report.longrepr, colored)


def _color_when_drawn(longrepr: Any, colored: dict[str, str]) -> None:
    longrepr.toterminal = _ColoredDrawing(longrepr, colored)


class _ColoredDrawing:
    """A representation's `toterminal`: the colored diff to a writer that takes color, the plain one to every other.

    A section is one string every reader prints as it is, so color written into it reached a JUnit body
    as escape codes.  pytest colors its own traceback as it draws it, and this does the same for ours:
    the sections change only for the length of one drawing, with no other code running in between.

    A class rather than a closure, because a closure made the representation refuse to pickle and kept a
    deep copy drawing the original.
    """

    def __init__(self, longrepr: Any, colored: dict[str, str]) -> None:
        self.longrepr = longrepr
        self.colored = colored

    def __call__(self, tw: Any) -> None:
        longrepr = self.longrepr
        draw = type(longrepr).toterminal
        if not getattr(tw, "hasmarkup", False):
            draw(longrepr, tw)
            return
        plain = longrepr.sections
        longrepr.sections = [(name, self.colored.get(name, content), *rest) for name, content, *rest in plain]
        try:
            draw(longrepr, tw)
        finally:
            longrepr.sections = plain


def _add_section(report: pytest.TestReport, name: str, content: str) -> None:
    """Hang *content* on the failure's own representation, which every reader of the report renders.

    `report.sections` is the channel for captured output.  Only the terminal prints it, and only when
    `--show-capture` allows, so PyCharm's runner, a JUnit body and a run hiding captured output all got
    the message with nothing under it.  A custom item or a plugin may render the failure as a string or
    as its own representation with no sections, and every reader prints its text, the one xdist sends
    too, so the section is written into that text.  A failure with no representation at all leaves the
    report as the only channel.
    """
    longrepr = report.longrepr
    add = getattr(longrepr, "addsection", None)
    if callable(add):
        add(name, content)
    elif longrepr is not None:
        report.longrepr = f"{longrepr}\n{f' {name} '.center(80, '-')}\n{content}"
    else:
        report.sections.append((name, content))


def _value_rows(actual: object, expected: object, *, paired: bool, named_actual: bool) -> list[str]:
    """The rows of a report section for the values a failure named, a side it did not name left unread.

    Cut like a diff row, the untouched values staying on the exception, and whole where `errors._WHOLE_VALUES`
    says so.  A pair is told apart by class where its two sides read alike, cut or whole.  For a failed
    equality the caller hands the pair compared (`_compared_pair`): under ``ignore=`` or ``include=`` alone the
    two views without the keys left out, in both modes.  Beside a compare option no pair is kept, and the rows
    are the two values.
    """
    if not paired:
        side = _safe_repr if errors._WHOLE_VALUES else _diff_side
        return [f"  actual:   {side(actual)}"] if named_actual else [f"  expected: {side(expected)}"]
    if errors._WHOLE_VALUES:
        left, right = _told_apart(_safe_repr(actual), _safe_repr(expected), actual, expected)
    else:
        # windowed as a pair: capping each side alone prints two values that look identical while saying they differ
        left, right = _diff_sides(actual, expected)
    return [f"  actual:   {left}", f"  expected: {right}"]


def _attach_report_sections(item, report, exc, *, suffix: str = "") -> None:
    """Add the readable detail a failure of ours carries: the named values, the diff, the poll trace.

    *suffix* tells one failure of a group from the next on every title.
    """
    actual = getattr(exc, "actual", None)
    expected = getattr(exc, "expected", None)
    named_actual, named_expected = _named(exc)

    # what decides is `actual` being named, a value other than the subject; no record is the older path
    named_values = named_actual if getattr(exc, "_outcome", None) is not None else (named_actual or named_expected)

    # windowed over whole values, a row could show a key left out and cut away what the failure is about
    compared = _compared_pair(exc) if named_values and named_actual and named_expected else None
    if compared is not None:
        actual, expected = compared
    sections = _sections_of(
        item,
        actual,
        expected,
        getattr(exc, "diff", None),
        getattr(exc, "trace", None),
        named_values=named_values,
        named_actual=named_actual,
        named_expected=named_expected,
        suffix=suffix,
    )
    _hang(report, sections)


def _sections_of(
    item, actual, expected, diff, trace, *, named_values: bool, named_actual: bool, named_expected: bool, suffix: str
) -> list[tuple[str, str, str | None]]:
    """The sections one failure gets, as ``(title, text, colored text or None)``, rendered and not yet attached.

    Each is drawn behind a barrier of its own, so a diff or a trace that cannot be drawn costs the others nothing.
    """
    sections: list[tuple[str, str, str | None]] = []
    if named_values:
        with contextlib.suppress(Exception):
            rows = _value_rows(actual, expected, paired=named_actual and named_expected, named_actual=named_actual)
            sections.append((f"AssertionFailure{suffix}", "\n".join(rows), None))

    if diff is not None and getattr(item.config, "_assertpy_diff_enabled", True):
        max_entries = getattr(item.config, "_assertpy_diff_max", 50)
        with contextlib.suppress(Exception):
            rendered = _format_diff(diff, max_entries=max_entries)
            # a diff with no entries renders as nothing, and the section around it read as a diff that found nothing
            if rendered:
                colored = None
                # the plain section stands without its coloured copy
                with contextlib.suppress(Exception):
                    colored = _format_diff(diff, color=True, max_entries=max_entries)
                sections.append((f"Structured Diff{suffix}", rendered, colored))

    if trace is not None and getattr(item.config, "_assertpy_diff_enabled", True):
        with contextlib.suppress(Exception):
            sections.append((f"Polling Trace{suffix}", _format_trace(trace), None))
    return sections


def _hang(report: pytest.TestReport, sections: list[tuple[str, str, str | None]]) -> None:
    for title, text, colored in sections:
        _add_section(report, title, text)
        _keep_colour(report, title, colored)


def _keep_colour(report: pytest.TestReport, title: str, colored: str | None) -> None:
    """Store the coloured copy of a section already on, behind a barrier: it is a copy for the terminal."""
    if colored is not None:
        with contextlib.suppress(Exception):
            vars(report).setdefault(_COLORED, {})[title] = colored


def _hang_each(report: pytest.TestReport, sections: list[tuple[str, str, str | None]]) -> int:
    """Attach a collected failure's *sections* in order, handing back how many characters went on.

    A representation refusing a section costs that section alone: the next one still goes on.
    """
    attached = 0
    for title, text, colored in sections:
        try:
            _add_section(report, title, text)
        except Exception:  # the representation is another plugin's or an item's own, and may refuse
            continue
        attached += len(text)
        _keep_colour(report, title, colored)
    return attached


_Pair = tuple[object, object] | None


_LISTED = "The summary lists each, its diff in compact rows."


def _carries(exc: BaseException) -> bool:
    """Whether a soft block left what it had collected on *exc*, the exception that escaped it."""
    try:
        return "_assertpy_collected" in vars(exc)
    except Exception:  # an exception without a dictionary carries nothing
        return False


def _attach_collected(item, report, exc: BaseException, room: _Room, attachments: _Room, within: str) -> None:
    """Hang the sections and the Allure attachments of every collection *exc* holds, behind one barrier each."""
    try:
        collections = _collections(exc)
    except Exception:  # a record of anyone's may raise when its class is asked, which must not cost the report
        return
    for label, collected in collections:
        with contextlib.suppress(Exception):
            _attach_collected_sections(item, report, collected, room, within=within + label)
        with contextlib.suppress(Exception):
            _attach_collected_to_allure(item, collected, attachments, within=within + label)


def _collections(exc: BaseException) -> list[tuple[str, tuple[tuple[AssertionOutcome, _Pair], ...]]]:
    """The failures a soft block collected that *exc* holds, each with the pair its equality compared.

    The failures a soft block raised as one, and those an exception of the caller's that escaped a block carries
    beside its note, one collection per block it escaped.  Carried ones are labelled as a note's, which numbers them
    on its own, wherever there is more than one collection to tell apart.
    """
    own: tuple[tuple[AssertionOutcome, _Pair], ...] = ()
    if isinstance(exc, errors.AssertionFailure):
        failures: object = ()
        pairs: object = ()
        # a subclass may answer the names with code of its own, which must not cost the report
        with contextlib.suppress(Exception):
            failures = exc.failures
        with contextlib.suppress(Exception):
            pairs = exc._compared_pairs
        own = _paired(failures, pairs)
    carried: list[tuple[tuple[AssertionOutcome, _Pair], ...]] = []
    if _carries(exc):
        with contextlib.suppress(Exception):
            for records, pairs in vars(exc)["_assertpy_collected"]:
                found = _paired(records, pairs)
                if found:
                    carried.append(found)
    collections = [("", own)] if own else []
    alone = "note, " if own else ""
    for position, found in enumerate(carried, 1):
        collections.append((f"note {position} of {len(carried)}, " if len(carried) > 1 else alone, found))
    return collections


def _paired(failures: object, pairs: object) -> tuple[tuple[AssertionOutcome, _Pair], ...]:
    """Each record of *failures* with its pair from *pairs*, or ``None`` where the two do not line up."""
    if type(failures) is not tuple:
        return ()
    if type(pairs) is not tuple or len(pairs) != len(failures):
        pairs = (None,) * len(failures)
    return tuple(
        (failure, pair if type(pair) is tuple and len(pair) == 2 else None)
        for failure, pair in zip(failures, pairs, strict=True)
        if isinstance(failure, AssertionOutcome)
    )


def _attach_collected_sections(
    item, report, collected: tuple[tuple[AssertionOutcome, _Pair], ...], room: _Room, *, within: str = ""
) -> None:
    """Give each failure a soft block collected the sections a raised one gets, numbered as its summary numbers it.

    Each section opens on the entry's line: its number, its group in brackets, its headline and its location, so a
    diff is never read against the wrong one.
    *within* names the leaf of an exception group the block's failure is.  *room* is the report's, so two blocks
    failing in one teardown share it: twenty failures drawn, and 60 000 characters of the sections that went on.  A
    failure with nothing to show takes none of it, and a section the representation refused takes no characters.
    Whether a failure fits is judged on all its sections before any goes on, since a refusal cannot be told in
    advance.  One that does not fit takes one of the twenty but no characters, so a smaller one after it still goes
    on.  One section at the end names those left out.
    """
    total = len(collected)
    left: list[int] = []
    for number, (outcome, compared) in enumerate(collected, 1):
        sections = _admitted(item, number, outcome, compared, room, f" ({within}failure {number} of {total})")
        if sections is None:
            left.append(number)
            continue
        room.characters -= _hang_each(report, sections)
    if left:
        notice = f"No section for lack of room: {_numbered(left)} of {total}. {_LISTED}"
        with contextlib.suppress(Exception):
            _add_section(report, f"Left Out ({within}{_numbered(left)})", notice)


def _admitted(
    item, number: int, outcome: AssertionOutcome, compared: _Pair, room: _Room, suffix: str
) -> list[tuple[str, str, str | None]] | None:
    """A collected failure's sections where the room takes them, ``[]`` where it has none to give, ``None`` where it
    is left out.  The room is asked before any drawing, and a failure drawn takes one of the twenty whether or not
    its sections fit."""
    # a collected failure that raises when read or drawn costs its own sections, not the next one's
    try:
        if not _shows_anything(item, outcome):
            return []
        if room.failures == 0:
            return None
        room.failures -= 1
        sections = _rendered(item, number, outcome, compared, suffix)
    except Exception:
        return []
    return None if sum(len(text) for _, text, _ in sections) > room.characters else sections


def _shows_anything(item, outcome: AssertionOutcome) -> bool:
    """Whether a collected failure would get a section at all, told without drawing one: named values, or a diff
    with entries or a poll's trace where the diff is not turned off."""
    if outcome.actual_provided:
        return True
    shown = getattr(item.config, "_assertpy_diff_enabled", True)
    return bool(shown and (_has_entries(outcome.diff) or outcome.trace is not None))


def _has_entries(diff: object) -> bool:
    """Whether *diff* has entries to show, a diff whose entries cannot be read having none."""
    try:
        return bool(getattr(diff, "entries", None))
    except Exception:  # a diff of anyone's, read where its failure's values and trace must still go on
        return False


def _rendered(
    item, number: int, outcome: AssertionOutcome, compared: _Pair, suffix: str
) -> list[tuple[str, str, str | None]]:
    """One collected failure's sections, each opening on the failure's own line of the summary.

    Its values are the pair its equality compared where one was kept, as for a raised failure: under ``ignore=`` or
    ``include=`` the two copies without the keys left out.
    """
    named = outcome.actual_provided and outcome.has_expected
    if named and compared is not None:
        actual, expected = compared
    else:
        actual, expected = outcome.actual, outcome.expected if outcome.has_expected else None
    sections = _sections_of(
        item,
        actual,
        expected,
        outcome.diff,
        outcome.trace,
        named_values=outcome.actual_provided,
        named_actual=outcome.actual_provided,
        named_expected=outcome.has_expected,
        suffix=suffix,
    )
    line = _entry_line(number, outcome)
    return [
        (title, f"{line}\n{text}", None if colored is None else f"{line}\n{colored}")
        for title, text, colored in sections
    ]


def _entry_line(number: int, outcome: AssertionOutcome) -> str:
    """The label a section opens on: the entry's number, its group in brackets, its headline and its location."""
    headline = outcome.message.splitlines()[0] if outcome.message else ""
    group = f"[{outcome.group}] " if outcome.group is not None else ""
    return f"{number}. {group}{_located(outcome.location, headline)}"


def _attach_to_allure(item, report, exc) -> None:
    """Attach the structured failure to the Allure report, when Allure is installed."""
    if not _HAS_ALLURE:
        return
    named_actual, named_expected = _named(exc)
    _attach_allure(
        getattr(exc, "actual", None),
        getattr(exc, "expected", None),
        getattr(exc, "diff", None),
        trace=getattr(exc, "trace", None),
        mode=getattr(item.config, "_assertpy_allure_mode", "diff"),
        max_entries=getattr(item.config, "_assertpy_diff_max", 50),
        requirement=getattr(exc, "requirement", None),
        # the record's flags, not the section's: a value already in the message is still what a dashboard reads
        named_actual=named_actual,
        named_expected=named_expected,
    )


def _attach_collected_to_allure(
    item, collected: tuple[tuple[AssertionOutcome, _Pair], ...], room: _Room, *, within: str = ""
) -> None:
    """Attach the failures a soft block collected, each under its number, on the report's room, when Allure is there.

    Twenty failures tried, shared by every block of the report as its sections share theirs: a failure with nothing
    to attach takes none of them, one whose attachments were refused takes one.  One text attachment at the end
    names the failures left out.  Each attachment is bounded on its own by the diff's rows.
    """
    if not _HAS_ALLURE:
        return
    total = len(collected)
    left: list[int] = []
    mode = getattr(item.config, "_assertpy_allure_mode", "diff")
    max_entries = getattr(item.config, "_assertpy_diff_max", 50)
    for number, (outcome, _) in enumerate(collected, 1):
        # a record of anyone's that raises when read costs its own attachments, not the next one's
        try:
            parts = _allure_parts(
                outcome.actual,
                outcome.expected if outcome.has_expected else None,
                outcome.diff,
                trace=outcome.trace,
                mode=mode,
                max_entries=max_entries,
                requirement=outcome.requirement,
                named_actual=outcome.actual_provided,
                named_expected=outcome.has_expected,
                suffix=f" ({within}failure {number} of {total})",
            )
        except Exception:
            continue
        if not parts:
            continue
        if room.failures == 0:
            left.append(number)
            continue
        room.failures -= 1
        _attach_parts(parts)
    if left:
        with contextlib.suppress(Exception):
            allure.attach(
                body=f"No attachment for lack of room: {_numbered(left)} of {total}. {_LISTED}",
                name=f"Left Out ({within}{_numbered(left)})",
                attachment_type=allure.attachment_type.TEXT,
            )


def _format_diff(diff, *, color: bool = False, max_entries: int = 50) -> str:
    return _render_diff(diff, color=color, max_entries=max_entries)


def _format_trace(trace) -> str:
    """Render a `PollTrace` as a compact per-poll timeline for the terminal report section."""
    lines = [f"polled {trace.total_polls} times over {trace.elapsed:.1f}s; {trace.summary}"]
    if trace.dropped:
        lines.append(f"  ... {trace.dropped} middle samples dropped")
    for sample in trace.samples:
        repeats = f" x{sample.repeats}" if sample.repeats > 1 else ""
        lines.append(f"  t=+{sample.elapsed:.1f}s {sample.outcome}{repeats}: {sample.detail}")
    return "\n".join(lines)


def _trace_to_json(trace):
    """Serialize a `PollTrace` to the typed attachment JSON, with diffs between distinct samples."""
    samples = []
    for sample in trace.samples:
        item = {"t": round(sample.elapsed, 3), "outcome": sample.outcome, "detail": sample.detail}
        if sample.value is not None:
            item["value"] = sample.value
        if sample.repeats > 1:
            item["repeats"] = sample.repeats
        samples.append(item)
    deltas = []
    fails = [sample for sample in trace.samples if sample.outcome == "fail"]
    for previous, current in pairwise(fails):
        if current.value == previous.value:
            continue
        entries = _sub_diff_entries(previous.value, current.value, _ROOT)
        if entries is None:
            entries_json = [{"path": ".", "actual": previous.value, "expected": current.value}]
        else:
            entries_json = [
                {"path": entry.path, "actual": entry.actual, "expected": entry.expected} for entry in entries
            ]
        deltas.append(
            {"from_t": round(previous.elapsed, 3), "to_t": round(current.elapsed, 3), "entries": entries_json}
        )
    payload = {
        "format": 2,
        "kind": "polling-trace",
        "total_polls": trace.total_polls,
        "elapsed": round(trace.elapsed, 3),
        "summary": trace.summary,
        "samples": samples,
    }
    if trace.dropped:
        payload["dropped"] = trace.dropped
    if deltas:
        payload["deltas"] = deltas
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _entry_to_json(entry):
    """One diff entry, with the side that had no value at all named rather than left to inference.

    ``format`` 2 wrote ``null`` for both an absent key and a key whose value really is ``None``, so a
    consumer of the attachment could not tell "this field is missing" from "this field is null" - the
    same ambiguity `assertpy.errors.DiffEntry.absent` exists to remove inside the library.  The key
    appears only where a side is genuinely absent, so an entry that simply holds ``None`` is
    unchanged, and the format is bumped because the meaning of a bare ``null`` is what changed.
    """
    item = {
        "path": str(getattr(entry, "path", "")),
        "actual": _json_safe(getattr(entry, "actual", None)),
        "expected": _json_safe(getattr(entry, "expected", None)),
    }
    absent = getattr(entry, "absent", None)
    if absent is not None:
        item["absent"] = absent
    steps = getattr(entry, "steps", ())
    if steps:
        # `path` is lossy, a mapping key goes through `str()`; absent at the root, which has no location
        item["steps"] = [_step_to_json(step) for step in steps]
    return item


def _step_to_json(step):
    """One hop of a diff entry's machine-readable path.

    ``side`` appears only where it means something: a sequence whose two sides have shifted apart, where
    an index without a side names two different elements.
    """
    item = {"kind": step.kind, "value": _json_safe(step.value)}
    if step.side is not None:
        item["side"] = step.side
    return item


def _diff_to_json(diff, max_entries=50):
    entries = getattr(diff, "entries", None)
    if not entries:
        return None
    kind = getattr(diff, "kind", "unknown")
    visible = entries[:max_entries] if max_entries > 0 and len(entries) > max_entries else entries
    truncated = len(entries) - len(visible)
    items = [_entry_to_json(entry) for entry in visible]
    payload = {"format": 4, "kind": kind, "entries": items}
    if truncated:
        payload["truncated"] = truncated
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _attach_allure(
    actual,
    expected,
    diff,
    *,
    named_actual,
    named_expected,
    trace=None,
    mode="diff",
    max_entries=50,
    requirement=None,
    suffix="",
) -> None:
    """Attach what a failure carries to the Allure report."""
    _attach_parts(
        _allure_parts(
            actual,
            expected,
            diff,
            named_actual=named_actual,
            named_expected=named_expected,
            trace=trace,
            mode=mode,
            max_entries=max_entries,
            requirement=requirement,
            suffix=suffix,
        )
    )


def _allure_parts(
    actual,
    expected,
    diff,
    *,
    named_actual,
    named_expected,
    trace=None,
    mode="diff",
    max_entries=50,
    requirement=None,
    suffix="",
) -> list[tuple[str, Callable[[], str | None], object]]:
    """The attachments a failure would get, as ``(name, its body when asked, type)``, none of them drawn yet."""
    # the flags say what the assertion named, not what the terminal shows, and are required rather than defaulted
    if mode == "off":
        return []
    parts: list[tuple[str, Callable[[], str | None], object]] = []
    if mode == "full" and (named_actual or named_expected or requirement is not None):

        def values() -> str:
            # format 3 adds `requirement`, so a consumer branching on the number keeps reading 2 as it did
            data: dict[str, object] = {"format": 3}
            if named_actual:
                data["actual"] = _json_safe(actual)
            if named_expected:
                data["expected"] = _json_safe(expected)
            if requirement is not None:
                data["requirement"] = {
                    "operation": requirement.operation,
                    "parameters": {name: _json_safe(value) for name, value in requirement.parameters.items()},
                    "negated": requirement.negated,
                }
            return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)

        parts.append((f"AssertionFailure{suffix}", values, allure.attachment_type.JSON))
    if _has_entries(diff):
        parts.append(
            (
                f"Structured Diff{suffix}",
                lambda: _diff_to_json(diff, max_entries=max_entries),
                allure.attachment_type.JSON,
            )
        )
    if trace is not None:
        parts.append((f"Polling Trace{suffix}", lambda: _trace_to_json(trace), allure.attachment_type.JSON))
    return parts


def _attach_parts(parts: list[tuple[str, Callable[[], str | None], object]]) -> None:
    """Draw and attach each part, one refused or broken costing that part alone."""
    for name, body, kind in parts:
        # the writer is Allure's, and the values are anyone's
        with contextlib.suppress(Exception):
            allure.attach(body=body(), name=name, attachment_type=kind)
