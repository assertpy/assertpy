import os
import sys

import pytest
from hypothesis import HealthCheck, settings

from assertpy import errors as _errors
from assertpy import snapshot as _snapshot
from assertpy.assertpy import AssertionBuilder
from tests import optional

_UNINSTALLED: pytest.StashKey[str] = pytest.StashKey()

# for a runner that calls pytest twice in one process: a `@given` method then meets a second instance of its class
settings.register_profile("one_process_twice", suppress_health_check=[HealthCheck.differing_executors])

# a mutation runner's trampoline sits between a test and the package, so the call site is read past it
if (_trampoline := sys.modules.get("mutmut.mutation.trampoline")) is not None:
    _snapshot.ASSERTPY_FILES = _snapshot.ASSERTPY_FILES | {_trampoline.__file__}


@pytest.fixture(autouse=True)
def _plain_messages(monkeypatch):
    """Pin the diff off the failure message for the suite.

    The suite runs with the plugin disabled (``-p no:assertpy``), so the diff-in-message default (on)
    would append the structured diff to every ``str(exc)`` and break the exact-message assertions.  Off
    here it mirrors what plugin-on users see, where the plugin renders the diff as its own report section
    instead; the off-pytest diff-in-message path has its own targeted tests that opt back in.
    """
    monkeypatch.setattr(_errors, "_RENDER_DIFF_IN_MESSAGE", False)
    # and the cap on: at -vv the plugin lifts it, and a run of this suite at -vv must read as any other
    monkeypatch.setattr(_errors, "_WHOLE_VALUES", False)


@pytest.fixture(autouse=True)
def _snapshot_isolation(monkeypatch):
    """Per-test snapshot isolation.

    Baseline CI mode off: many tests intentionally *create* snapshots in ``tmp_path``; GitHub Actions
    sets ``CI=true``, which would auto-enable snapshot CI mode and turn those creations into failures.
    The tri-state flag has the highest precedence, so ``False`` forces CI mode off regardless of ambient
    env; the CI-mode tests opt back in explicitly.  Also restore the custom-serializer registry so a
    test that registers a serializer does not leak into later tests.
    """
    monkeypatch.setattr(_snapshot, "_CI_MODE", False)
    saved_serializers = list(_snapshot._SERIALIZERS)
    saved_touched = set(_snapshot._TOUCHED)
    yield
    _snapshot._SERIALIZERS[:] = saved_serializers
    _snapshot._TOUCHED.clear()
    _snapshot._TOUCHED.update(saved_touched)


@pytest.fixture
def builder() -> AssertionBuilder:
    """The builder as a host for its own private helpers, constructed rather than reached through the factory.

    These tests check `_fmt_items`, `_require_dict_like` and their neighbours, which are implementation
    and are meant to be.  They used to reach them through `assert_that(None)`, and that only worked
    because the factory handed back the builder itself with all 152 assertion names on it.  It no longer
    does for a value with no capability, and the fix is to say what the test is really doing: it wants
    the object, not an assertion.
    """
    return AssertionBuilder(None)


# A skipped gate reads as a green one, which cost two red CI runs in one day: `pytest-examples` was absent
# locally, so the whole doc-example file was skipped while the run was reported as passing.  Every skip for a
# missing module names it, through `tests.optional`, and two runs claim to know which modules are installed: the
# cell enforcing the coverage floor claims all of them, a delegated one aside, and a run told what is absent
# (`ASSERTPY_SUITE_ABSENT`, from `scripts/check_sdist.py`) claims the rest.  A skip that contradicts the claim fails it.
_ABSENT = "ASSERTPY_SUITE_ABSENT"
_IMPORT_SKIP = ("could not import", "no module named")
_missing_from: dict[str, list[str]] = {}


def pytest_sessionstart(session) -> None:
    # a runner that calls pytest twice in one process would otherwise hold the first run's reports against the second
    _missing_from.clear()


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "needs(module, **options): skip where the module is absent, see tests.optional")


def pytest_runtest_setup(item) -> None:
    for mark in item.iter_markers("needs"):
        optional.needs(*mark.args, **mark.kwargs)


def _record(report) -> None:
    """Both report kinds, because the two ways a module goes missing arrive as different ones.

    `needs()` at the top of a file raises while the file is being collected, so it never reaches a run report
    at all.  That is the shape that hid a whole skipped gate, so reading only the run reports would leave the
    guard blind to exactly what it was written for.  A collection report holds no `user_properties`.
    """
    for key, module in getattr(report, "user_properties", ()):
        if key == optional.RECORD:
            _note(report.nodeid, f"needs {module}: its cases were left out")
    if not report.skipped or not isinstance(report.longrepr, tuple):
        return
    _, _, reason = report.longrepr
    if optional.REASON.match(reason) or any(marker in reason.lower() for marker in _IMPORT_SKIP):
        _note(report.nodeid, reason)


def _note(nodeid: str, reason: str) -> None:
    """Every reason a test gives, since one it is allowed must not stand in for one it is not."""
    said = _missing_from.setdefault(nodeid, [])
    if reason not in said:
        said.append(reason)


def _contradicting(config) -> list[str]:
    """The skips and records the run's claim does not allow, or none where it makes no claim.

    A skip in pytest's own wording did not go through `needs()` and names no module that could be checked, and
    one for an older release than a test asks is no absence at all, so neither is ever allowed.
    """
    told = os.environ.get(_ABSENT)
    if told is None and config.getoption("cov_fail_under", None) is None:
        return []
    taken = set(filter(None, (told or "").split(",")))
    found = []
    for nodeid, reasons in sorted(_missing_from.items()):
        for reason in reasons:
            said = optional.REASON.match(reason)
            if said is None or said["minversion"] is not None:
                allowed = False
            elif told is None:
                allowed = said["delegated"] is not None
            else:
                allowed = not _enclosing(said["module"]).isdisjoint(taken)
            if not allowed:
                found.append(f"  {nodeid}: {reason}")
    return found


def _enclosing(module: str) -> set[str]:
    """The module and every package holding it: `ns.a` is absent where `ns` left, or only `ns.a` did."""
    parts = module.split(".")
    return {".".join(parts[:end]) for end in range(1, len(parts) + 1)}


def pytest_runtest_logreport(report) -> None:
    _record(report)


def pytest_collectreport(report) -> None:
    _record(report)


def pytest_sessionfinish(session, exitstatus) -> None:
    found = _contradicting(session.config)
    if not found:
        return
    session.config.stash[_UNINSTALLED] = "\n".join(found)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter) -> None:
    listed = terminalreporter.config.stash.get(_UNINSTALLED, None)
    if listed is not None:
        terminalreporter.write_sep("=", "gates skipped for a missing module", red=True)
        terminalreporter.write_line(listed)
        told = os.environ.get(_ABSENT)
        if told is None:
            terminalreporter.write_line("this run enforces the coverage floor, so it claims every gate ran")
        else:
            terminalreporter.write_line(f"this run was told that only these modules are absent: {told or 'none'}")
