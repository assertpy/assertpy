import sys

import pytest
from hypothesis import HealthCheck, settings

from assertpy import errors as _errors
from assertpy import snapshot as _snapshot
from assertpy.assertpy import AssertionBuilder

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
# locally, so the whole doc-example file was skipped while the run was reported as passing.  Only the cell
# enforcing the coverage floor promises every dependency is installed, so a module missing under that promise
# is a defect and anywhere else an ordinary partial run.  A gate delegated to another job says so in its own
# `importorskip` reason: the checkers are the case, the lint job installing the typecheck group and the
# coverage cell not.
_IMPORT_SKIP = ("could not import", "no module named")
_missing_from: dict[str, str] = {}


def _record(report) -> None:
    """Both report kinds, because the two ways a module goes missing arrive as different ones.

    `pytest.importorskip` at the top of a file raises while the file is being collected, so it never
    reaches a run report at all.  That is the shape that hid a whole skipped gate, so reading only the
    run reports would leave the guard blind to exactly what it was written for.
    """
    if not report.skipped or not isinstance(report.longrepr, tuple):
        return
    _, _, reason = report.longrepr
    if any(marker in reason.lower() for marker in _IMPORT_SKIP):
        _missing_from[report.nodeid] = reason


def pytest_runtest_logreport(report) -> None:
    _record(report)


def pytest_collectreport(report) -> None:
    _record(report)


def pytest_sessionfinish(session, exitstatus) -> None:
    if not _missing_from or session.config.getoption("cov_fail_under", None) is None:
        return
    listed = "\n".join(f"  {nodeid}: {reason}" for nodeid, reason in sorted(_missing_from.items()))
    session.config.stash[_UNINSTALLED] = listed
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter) -> None:
    listed = terminalreporter.config.stash.get(_UNINSTALLED, None)
    if listed is not None:
        terminalreporter.write_sep("=", "gates skipped for a missing module", red=True)
        terminalreporter.write_line(listed)
        terminalreporter.write_line("this run enforces the coverage floor, so it claims every gate ran")
