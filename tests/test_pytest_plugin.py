import contextlib
import copy
import dataclasses
import io
import json
import os
import pathlib
import pickle
import pprint
import subprocess
import sys
import types
import warnings
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from _pytest._code.code import TerminalRepr
from _pytest._io import TerminalWriter
from _pytest.config.argparsing import Parser
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from assertpy import (
    _clustering,
    _renamed,
    add_extension,
    assert_that,
    async_assertions,
    match,
    remove_extension,
    soft_assertions,
)
from assertpy import _satisfies as _satisfies_module
from assertpy import errors as errors_module
from assertpy import pytest_plugin as pytest_plugin
from assertpy import snapshot as snapshot_module
from assertpy._clustering import Observation, Signature
from assertpy._engine._diff import _sub_diff_entries
from assertpy._engine._introspection import TakenApart, laid_out
from assertpy._engine._path import _ROOT
from assertpy.errors import AssertionFailure, DiffEntry, DiffResult, PollSample, PollTrace
from assertpy.outcome import AssertionOutcome
from assertpy.pytest_plugin import (
    _COLORED,
    _PROFILES,
    _diff_to_json,
    _escalate,
    _format_diff,
    _format_trace,
    _is_full_run,
    _json_safe,
    _setting,
    _trace_to_json,
    _vacuous_guard,
    pytest_addoption,
    pytest_configure,
    pytest_runtest_makereport,
    pytest_runtest_setup,
    pytest_sessionfinish,
    pytest_testnodedown,
    pytest_unconfigure,
)
from tests.group_compat import ExceptionGroup

# a child starting in `tmp_path` otherwise imports the installed copy, which a cached 3.10 floor build left stale
_CHECKOUT = str(pathlib.Path(pytest_plugin.__file__).resolve().parents[1])


class _FakeOutcome:
    def __init__(self, report):
        self._report = report

    def get_result(self):
        return self._report


class _FailureRepr:
    """The part of pytest's failure representation the plugin writes to, as pytest itself stores it."""

    def __init__(self):
        self.sections: list[tuple[str, str, str]] = []

    def addsection(self, name, content, sep="-"):
        self.sections.append((name, content, sep))


def _make_report(*, when="call", failed=True, sections=None):
    report = MagicMock()
    report.when = when
    report.failed = failed
    report.sections = sections if sections is not None else []
    report.longrepr = _FailureRepr()
    return report


def _sections(report):
    """``(name, content)`` for what the plugin hung on the failure, the shape `_sections(report)` has."""
    return [(name, content) for name, content, _sep in report.longrepr.sections]


def _make_call(*, exc=None):
    call = MagicMock()
    if exc is None:
        call.excinfo = None
    else:
        call.excinfo = MagicMock()
        call.excinfo.value = exc
    return call


def _make_item(*, allure_mode="diff"):
    item = MagicMock()
    item.config._assertpy_allure_mode = allure_mode
    item.config._assertpy_diff_enabled = True
    item.config._assertpy_diff_max = 50
    item.config._assertpy_comparison_enabled = True
    return item


def _run_hook(report, call, *, item=None):
    if item is None:
        item = _make_item()
    gen = pytest_runtest_makereport(item=item, call=call)
    next(gen)
    with contextlib.suppress(StopIteration):
        gen.send(_FakeOutcome(report))
    return report


class TestPluginLoaded:
    def test_plugin_is_registered(self):
        pm = pytest.importorskip("assertpy.pytest_plugin")
        assert_that(hasattr(pm, "pytest_runtest_makereport")).is_true()

    def test_addoption_registers_ini(self):
        parser = MagicMock()
        pytest_addoption(parser)
        assert_that(parser.addini.call_count).described_as(
            "each setting under its name and its assertpy2 one"
        ).is_equal_to(20)
        names = [call[0][0] for call in parser.addini.call_args_list]
        assert_that(names).contains("assertpy2_diff", "assertpy2_dangling_entries")
        assert_that(names).contains("assertpy_allure")
        assert_that(names).contains("assertpy_diff")
        assert_that(names).contains("assertpy_diff_max_entries")
        assert_that(names).contains("assertpy_failure_clusters")
        assert_that(names).contains("assertpy_dangling")
        assert_that(names).contains("assertpy_dangling_entries")
        assert_that(names).contains("assertpy_profile")
        assert_that(names).contains("assertpy_vacuous")
        defaults = {call[0][0]: call[1].get("default") for call in parser.addini.call_args_list}
        assert_that([name for name in pytest_plugin._SETTINGS if defaults[name] not in ("", [])]).described_as(
            "registered blank, so a suite that wrote nothing is told from one that wrote the assertpy2 name"
        ).is_empty()
        assert_that(pytest_plugin._cluster_minimum("")).described_as(
            "clustering answers for itself, so a blank setting reads as its own default rather than a profile's"
        ).is_equal_to(_clustering.MINIMUM_SIZE)


class TestTheProfileAnswersForWhatTheSuiteDidNotName:
    """One line of config instead of three, and the three keep working on their own.

    The guards a new suite wants are the ones an inherited suite must not get without asking: each can
    turn a green run red.  So `compatible` is the default and `safe` is the line that turns them on,
    rather than the defaults moving under everybody.

    Failure clustering is deliberately not one of them.  It is asked for by name or not at all, and its
    default is on, because it reads a run that already failed and costs a passing one nothing.
    """

    @staticmethod
    def _config(**written):
        return SimpleNamespace(getini=lambda name: written.get(name, ""), getoption=lambda name: False)

    def test_an_unnamed_setting_takes_its_profile_answer(self):
        compatible, safe = self._config(), self._config(assertpy_profile="safe")
        assert_that(_setting(compatible, "assertpy_dangling")).is_equal_to("off")
        assert_that(_setting(safe, "assertpy_dangling")).is_equal_to("on")
        assert_that(_setting(safe, "assertpy_vacuous")).is_equal_to("on")

    def test_no_profile_answers_for_failure_clustering(self):
        """The separation itself, which a table with a third key would quietly undo.

        Clustering is on by default, so a profile listing it could only ever turn it off, and the one
        that would is `compatible`.  That is the bundling this was pulled out of: `compatible` speaks
        for what a guard costs a passing suite, and clustering costs one nothing.
        """
        for profile in _PROFILES.values():
            assert_that(profile).does_not_contain_key("assertpy_failure_clusters")

    def test_a_named_setting_wins_over_the_profile(self):
        config = self._config(assertpy_profile="safe", assertpy_dangling="off")
        assert_that(_setting(config, "assertpy_dangling")).described_as(
            "a suite that named a setting has said what it wants, whatever profile it picked"
        ).is_equal_to("off")
        assert_that(_setting(config, "assertpy_vacuous")).is_equal_to("on")

    def test_only_strict_writes_the_two_filters(self):
        """The wiring itself, called directly.

        The profile tests below drive a real run in a child process, where nothing measures this
        module, so the lines that add the filters would otherwise be held by nothing.
        """
        written = []
        for profile in ("compatible", "safe", "strict"):
            config = SimpleNamespace(
                getini=lambda name, profile=profile: {"assertpy_profile": profile}.get(name, ""),
                getoption=lambda name: False,
                addinivalue_line=lambda name, value: written.append((name, value)),
            )
            _escalate(config)
        assert_that(written).described_as("only `strict` escalates, and only its own two").is_equal_to(
            [
                ("filterwarnings", "error::assertpy.errors.DanglingAssertionWarning"),
                ("filterwarnings", "error::assertpy.errors.VacuousAssertionWarning"),
            ]
        )

    def test_a_profile_nobody_declared_is_refused_and_named(self):
        config = self._config(assertpy_profile="paranoid")
        with pytest.warns(UserWarning, match="assertpy_profile='paranoid' is not one of"):
            assert_that(_setting(config, "assertpy_dangling")).is_equal_to("off")

    def test_a_mistyped_guard_setting_falls_back_to_the_profile_rather_than_to_off(self):
        """`off` is the answer that hides a mistake, so a value nobody declared must not read as one."""
        config = self._config(assertpy_profile="safe", assertpy_vacuous="onn")
        with pytest.warns(UserWarning, match="assertpy_vacuous='onn' is not 'on' or 'off'"):
            assert_that(_vacuous_guard(config)).is_true()

    def test_a_profile_nobody_declared_is_named_once_rather_than_per_question(self):
        """Both settings ask, and one mistake is one mistake however many of them looked."""
        config = self._config(assertpy_profile="paranoid")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for name in ("assertpy_dangling", "assertpy_vacuous"):
                _setting(config, name)
        assert_that([str(one.message) for one in caught]).is_length(1)


class TestTheProfileFromAConfigFile:
    """The profile as a suite meets it: a config file, a run, and what it says.

    The three tests above hold `_setting()`, which is the resolution and not the wiring.  A refactor
    that stopped `pytest_configure` calling it would leave every one of them green while the profile
    did nothing at all, so this one writes the config and reads the warnings out of a real run.
    """

    _SUITE = (
        "from assertpy import assert_that\n\n\n"
        "def test_dangling_statement():\n    assert_that(1)\n\n\n"
        "def test_vacuous_quantifier():\n    assert_that([]).all_satisfy(lambda item: False)\n"
    )

    def _run(self, tmp_path, *settings, suite=None, **environment):
        (tmp_path / "test_guards.py").write_bytes(suite if suite is not None else self._SUITE.encode("utf-8"))
        (tmp_path / "pytest.ini").write_text("\n".join(["[pytest]", *settings, ""]), encoding="utf-8")
        return subprocess.run(
            # this interpreter, not `uv run`: the child starts in `tmp_path`, outside the project, where `uv run`
            # resolves whatever it finds. A 3.10 check answered from 3.14 with no plugin installed
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=180,
            # one of the three ways to ask for the vacuous guard, so a machine carrying it would answer for the suite
            env={
                **{key: value for key, value in os.environ.items() if key != "ASSERTPY_VACUOUS"},
                "PYTHONPATH": _CHECKOUT,
                **environment,
            },
        )

    @staticmethod
    def _reported(result):
        """The child's stdout, once the child is known to have run at all.

        Every case here reads stdout, and two of them read it for an absence: a child that died on
        startup prints no warning either, and would pass them both.
        """
        assert_that(result.returncode).described_as(f"the child run failed: {result.stderr}").is_equal_to(0)
        return assert_that(result.stdout).described_as(
            f"exit {result.returncode}, child stderr: {result.stderr.strip() or 'empty'}"
        )

    def test_the_default_leaves_a_run_as_it_found_it(self, tmp_path):
        result = self._run(tmp_path)
        self._reported(result).does_not_contain("DanglingAssertionWarning", "VacuousAssertionWarning")

    def test_the_safe_profile_turns_both_warnings_on(self, tmp_path):
        result = self._run(tmp_path, "assertpy_profile = safe")
        self._reported(result).contains("DanglingAssertionWarning", "VacuousAssertionWarning")

    def test_a_comment_that_is_not_utf8_leaves_the_run_standing(self, tmp_path):
        # a cp1251 comment and no declared encoding: 3.10 to 3.13 import it, and a strict read aborted the whole run
        suite = (
            b"# \xcf\xf0\xe8\xec\xe5\xf0\n"
            b"from assertpy import assert_that\n\n\ndef test_dangling():\n    assert_that(1)\n"
        )
        result = self._run(tmp_path, "assertpy_profile = safe", suite=suite)
        assert_that(result.stdout + result.stderr).does_not_contain("INTERNALERROR")
        try:
            compile(suite, "test_guards.py", "exec")
        except SyntaxError:
            # this interpreter refuses the source itself, so the module never reaches the check
            assert_that(result.returncode).is_equal_to(pytest.ExitCode.INTERRUPTED)
        else:
            self._reported(result).contains("DanglingAssertionWarning")

    def test_a_module_in_its_declared_encoding_is_read_in_it(self, tmp_path):
        # replacing what UTF-8 cannot decode would turn the identifier into U+FFFD, which does not parse
        suite = (
            "# coding: cp1251\nfrom assertpy import assert_that\n\n\n"
            "def test_dangling():\n    значение = 1\n    assert_that(значение)\n"
        ).encode("cp1251")
        result = self._run(tmp_path, "assertpy_profile = safe", suite=suite)
        self._reported(result).contains("DanglingAssertionWarning")

    def test_a_named_setting_wins_over_the_profile_in_a_real_run(self, tmp_path):
        result = self._run(tmp_path, "assertpy_profile = safe", "assertpy_dangling = off")
        self._reported(result).does_not_contain("DanglingAssertionWarning")
        self._reported(result).contains("VacuousAssertionWarning")

    def test_the_safe_profile_leaves_the_run_green(self, tmp_path):
        """What separates `safe` from `strict`, and the reason both exist.

        `safe` shows a suite what it has.  A run full of findings still exits zero, which is a fair
        first look and a poor gate.
        """
        result = self._run(tmp_path, "assertpy_profile = safe")
        assert_that(result.returncode).described_as("warnings alone do not fail a run").is_equal_to(0)

    def test_the_strict_profile_fails_the_run(self, tmp_path):
        result = self._run(tmp_path, "assertpy_profile = strict")
        assert_that(result.returncode).described_as(f"strict left the run green: {result.stdout}").is_not_equal_to(0)

    def test_strict_reports_each_finding_where_it_arrives(self, tmp_path):
        """A dangling finding is reported at setup, a vacuous one while the assertion runs.

        The chain is found while the module is collected, but the warning is raised from
        `pytest_runtest_setup`, which is why pytest calls it a setup error rather than a failure.
        Pinned because a reader who expects two failures and is shown one of each will think the plugin
        broke.
        """
        result = self._run(tmp_path, "assertpy_profile = strict")
        assert_that(result.stdout).described_as("the dangling one, found at collection").contains(
            "ERROR test_guards.py::test_dangling_statement"
        )
        assert_that(result.stdout).described_as("the vacuous one, found while running").contains(
            "FAILED test_guards.py::test_vacuous_quantifier"
        )

    def test_a_named_setting_still_wins_under_strict(self, tmp_path):
        """`strict` escalates the guards that are on, not the ones the suite turned off."""
        result = self._run(tmp_path, "assertpy_profile = strict", "assertpy_dangling = off")
        assert_that(result.stdout).does_not_contain("ERROR test_guards.py::test_dangling_statement")
        assert_that(result.stdout).contains("FAILED test_guards.py::test_vacuous_quantifier")

    def test_strict_leaves_another_library_s_warnings_alone(self, tmp_path):
        """Why this is not `filterwarnings = error`.

        A blanket escalation would fail a test for somebody else's `DeprecationWarning`, which is a
        change to the suite this library was never asked to make.
        """
        (tmp_path / "test_neighbour.py").write_text(
            "import warnings\n\n\n"
            "def test_someone_else_warns():\n"
            "    warnings.warn('unrelated', DeprecationWarning, stacklevel=1)\n",
            encoding="utf-8",
        )
        result = self._run(tmp_path, "assertpy_profile = strict")
        assert_that(result.stdout).does_not_contain("FAILED test_neighbour.py")

    def test_a_value_the_setting_does_not_know_is_refused_rather_than_read_as_off(self, tmp_path):
        """A guard whose setting was mistyped must not go quiet: the quiet answer is the dangerous one.

        The refusal is written at configure time, which is before pytest owns the streams, so it lands
        on stderr while the guard's own warning reaches the report.
        """
        result = self._run(tmp_path, "assertpy_profile = safe", "assertpy_vacuous = onn")
        self._reported(result).contains("VacuousAssertionWarning")
        assert_that(result.stderr).described_as("the mistyped setting, refused by name").contains(
            "assertpy_vacuous='onn' is not 'on' or 'off'"
        )

    def test_the_environment_cannot_outrank_a_suite_that_said_off(self, tmp_path):
        """The variable asks for the guard away from pytest, and a config file is the louder voice."""
        result = self._run(tmp_path, "assertpy_vacuous = off", ASSERTPY_VACUOUS="1")
        self._reported(result).does_not_contain("VacuousAssertionWarning")


class TestEveryPhaseGetsItsSections:
    """A fixture's failure is as much a failure of ours as the test's, and the message leaves it the diff."""

    @pytest.mark.parametrize("when", ["setup", "call", "teardown"])
    def test_the_diff_is_hung_on_the_failure_in_every_phase(self, when):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report(when=when)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff)))
        assert_that([title for title, _ in _sections(report)]).contains("Structured Diff")


class _OwnRepr(TerminalRepr):
    def toterminal(self, tw):
        tw.line("an item's own rendering")


class _UnreadableError(AssertionError):
    @property
    def diff(self):
        raise RuntimeError("a property that raises")


class TestEachFailureOfAGroupGetsItsOwn:
    """pytest groups two failing finalizers, and a task group wraps whatever its tasks raised."""

    @staticmethod
    def _failure(actual):
        return AssertionFailure(
            "fail", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=actual, expected=0)])
        )

    @staticmethod
    def _titles(report):
        return [title for title, _ in _sections(report)]

    def test_each_is_numbered_in_the_order_the_traceback_prints_it(self):
        report = _make_report(when="teardown")
        _run_hook(report, _make_call(exc=ExceptionGroup("teardown", [self._failure(111), self._failure(222)])))
        first, second = _sections(report)
        assert_that(first).is_equal_to(("Structured Diff (1 of 2)", match.contains("111")))
        assert_that(second).is_equal_to(("Structured Diff (2 of 2)", match.contains("222")))

    def test_a_member_that_is_not_ours_keeps_its_place_in_the_count(self):
        report = _make_report()
        _run_hook(report, _make_call(exc=ExceptionGroup("tasks", [ValueError("not ours"), self._failure(1)])))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (2 of 2)"])

    def test_a_nested_group_is_counted_flat(self):
        inner = ExceptionGroup("inner", [ValueError("not ours"), self._failure(2)])
        report = _make_report()
        _run_hook(report, _make_call(exc=ExceptionGroup("outer", [self._failure(1), inner])))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (1 of 3)", "Structured Diff (3 of 3)"])

    def test_a_group_with_nothing_of_ours_gets_nothing(self):
        report = _make_report()
        _run_hook(report, _make_call(exc=ExceptionGroup("tasks", [ValueError("not ours")])))
        assert_that(_sections(report)).is_empty()

    def test_one_failure_that_cannot_be_read_leaves_the_next_its_sections(self):
        report = _make_report()
        _run_hook(report, _make_call(exc=ExceptionGroup("teardown", [_UnreadableError("fail"), self._failure(1)])))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (2 of 2)"])

    def test_allure_gets_every_failure(self):
        mock = _mock_allure()
        group = ExceptionGroup("teardown", [self._failure(1), self._failure(2)])
        _run_hook_with_allure(_make_report(), _make_call(exc=group), mock)
        assert_that([one.kwargs for one in mock.attach.call_args_list]).is_equal_to(
            [
                {"body": match.contains('"actual": 1'), "name": "Structured Diff", "attachment_type": "json"},
                {"body": match.contains('"actual": 2'), "name": "Structured Diff", "attachment_type": "json"},
            ]
        )

    def test_an_attachment_refused_for_one_failure_leaves_the_next_its_own(self):
        mock = _mock_allure()
        mock.attach.side_effect = [RuntimeError("refused"), None]
        group = ExceptionGroup("teardown", [self._failure(1), self._failure(2)])
        _run_hook_with_allure(_make_report(), _make_call(exc=group), mock)
        assert_that(mock.attach.call_args_list).is_length(2)
        assert_that(mock.attach.call_args_list[1].kwargs["body"]).contains('"actual": 2')

    def test_the_same_failure_listed_twice_is_shown_twice_as_the_traceback_prints_it(self):
        mock = _mock_allure()
        failure = self._failure(1)
        report = _make_report()
        _run_hook_with_allure(report, _make_call(exc=ExceptionGroup("tasks", [failure, failure])), mock)
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (1 of 2)", "Structured Diff (2 of 2)"])
        assert_that(mock.attach.call_count).is_equal_to(2)


def _collected_from(*asks):
    """The failure a soft block raises once every ask in it has failed."""
    with pytest.raises(AssertionFailure) as raised, soft_assertions():
        for ask in asks:
            ask()
    return raised.value


def _entry(failure, number):
    """The numbered line of the summary for the failure collected at *number*, as the block printed it."""
    file, line = failure.failures[number - 1].location
    headline = failure.failures[number - 1].message.splitlines()[0]
    return f"{number}. {headline}  [{os.path.basename(file)}:{line}]"


def _wide(n):
    """A failure whose sections run to 26 309 characters: fifty rows of 300 characters."""
    return lambda: assert_that({f"k{i}": str(n) * 300 for i in range(50)}).is_equal_to(
        {f"k{i}": "x" * 300 for i in range(50)}
    )


class _UnsplittableMessage(str):
    def splitlines(self, keepends=False):
        raise RuntimeError("a message that cannot be split")


class _RefusesOnce(_FailureRepr):
    def __init__(self):
        super().__init__()
        self.refused = False

    def addsection(self, name, content, sep="-"):
        if not self.refused:
            self.refused = True
            raise RuntimeError("refused once")
        super().addsection(name, content, sep)


class _UnrenderableDiff:
    @property
    def entries(self):
        raise RuntimeError("a diff that cannot be read")


class TestEachFailureASoftBlockCollectedGetsItsOwn:
    """A soft block raises one failure for many, and each of the many gets the sections a raised failure gets."""

    @staticmethod
    def _titles(report):
        return [title for title, _ in _sections(report)]

    def test_each_is_numbered_and_opened_as_the_summary_numbers_it(self):
        failure = _collected_from(
            lambda: assert_that({2: 4}).is_equal_to({2: 3}),
            lambda: assert_that([1, 2]).contains(3),
        )
        report = _run_hook(_make_report(), _make_call(exc=failure))
        first, second = _entry(failure, 1), _entry(failure, 2)
        assert_that(_sections(report)).is_equal_to(
            [
                ("AssertionFailure (failure 1 of 2)", f"{first}\n  actual:   {{2: 4}}\n  expected: {{2: 3}}"),
                ("Structured Diff (failure 1 of 2)", f"{first}\ndiff (dict):\n  2:\n    - 4\n    + 3"),
                ("Structured Diff (failure 2 of 2)", f"{second}\ndiff (contains):\n  missing: 3"),
            ]
        )
        assert_that(str(failure).splitlines()).contains(first, second)

    def test_a_grouped_failure_names_its_group(self):
        def asks():
            with soft_assertions() as block, block.group("billing"):
                assert_that({2: 4}).is_equal_to({2: 3})

        with pytest.raises(AssertionFailure) as raised:
            asks()
        report = _run_hook(_make_report(), _make_call(exc=raised.value))
        file, line = raised.value.failures[0].location
        where = f"[{os.path.basename(file)}:{line}]"
        assert_that(_sections(report)[0][1].splitlines()[0]).is_equal_to(
            f"1. [billing] Expected <{{2: 4}}> to be equal to <{{2: 3}}>, but was not.  {where}"
        )

    def test_an_expectation_of_none_is_shown_and_an_absent_one_is_not(self):
        named = AssertionOutcome(message="named", actual=1, actual_provided=True, expected=None)
        absent = AssertionOutcome(message="absent", actual=1, actual_provided=True)
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(named, absent))))
        assert_that(_sections(report)).is_equal_to(
            [
                ("AssertionFailure (failure 1 of 2)", "1. named\n  actual:   1\n  expected: None"),
                ("AssertionFailure (failure 2 of 2)", "2. absent\n  actual:   1"),
            ]
        )

    def test_a_failure_with_nothing_to_show_gets_no_section_and_keeps_its_number(self):
        failure = _collected_from(lambda: assert_that(False).is_true(), lambda: assert_that([1, 2]).contains(3))
        report = _run_hook(_make_report(), _make_call(exc=failure))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (failure 2 of 2)"])
        assert_that(failure.failures[0].diff).is_none()

    def test_a_failure_with_nothing_to_show_does_not_count_against_the_twenty(self):
        failure = _collected_from(
            lambda: assert_that(False).is_true(),
            *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(20)],
        )
        report = _run_hook(_make_report(), _make_call(exc=failure))
        titles = self._titles(report)
        assert_that(titles).is_length(40)
        assert_that(titles[-1]).is_equal_to("Structured Diff (failure 21 of 21)")

    def test_a_failure_with_nothing_to_show_after_the_twenty_is_not_left_out(self):
        failure = _collected_from(
            *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(20)],
            lambda: assert_that(False).is_true(),
        )
        report = _run_hook(_make_report(), _make_call(exc=failure))
        titles = self._titles(report)
        assert_that(titles).is_length(40)
        assert_that(titles[-1]).is_equal_to("Structured Diff (failure 20 of 21)")

    def test_a_timed_out_poll_gets_its_trace(self):
        timed_out = AssertionOutcome(message="never settled", trace=_make_trace())
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(timed_out,))))
        assert_that(_sections(report)).is_equal_to(
            [("Polling Trace (failure 1 of 1)", f"1. never settled\n{_format_trace(_make_trace())}")]
        )

    def test_a_block_inside_a_group_names_its_leaf(self):
        block = _collected_from(lambda: assert_that([1, 2]).contains(3))
        alone = AssertionFailure(
            "alone", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        )
        report = _run_hook(_make_report(when="teardown"), _make_call(exc=ExceptionGroup("teardown", [block, alone])))
        assert_that(self._titles(report)).is_equal_to(
            ["Structured Diff (leaf 1 of 2, failure 1 of 1)", "Structured Diff (2 of 2)"]
        )

    def test_past_twenty_one_section_names_the_rest(self):
        failure = _collected_from(*[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(25)])
        report = _run_hook(_make_report(), _make_call(exc=failure))
        titles = self._titles(report)
        assert_that(failure.failures).is_length(25)
        assert_that(str(failure.failures[24].diff).splitlines()).is_equal_to(
            ["diff (dict):", "  k:", "    - 24", "    + -1"]
        )
        assert_that(titles).is_length(41)
        assert_that(titles[-3:]).is_equal_to(
            [
                "AssertionFailure (failure 20 of 25)",
                "Structured Diff (failure 20 of 25)",
                "Left Out (failures 21 to 25)",
            ]
        )
        assert_that(_sections(report)[-1][1]).is_equal_to(
            "No section for lack of room: failures 21 to 25 of 25. The summary lists each, its diff in compact rows."
        )

    def test_past_the_budget_one_section_names_the_rest(self):
        # fifty rows of 300 characters: 26 309 characters of sections a failure, so two fit the budget and three do not
        wide = [
            lambda n=n: assert_that({f"k{i}": str(n) * 300 for i in range(50)}).is_equal_to(
                {f"k{i}": "x" * 300 for i in range(50)}
            )
            for n in range(1, 4)
        ]
        failure = _collected_from(*wide)
        report = _run_hook(_make_report(), _make_call(exc=failure))
        sizes = [len(content) for _, content in _sections(report)]
        assert_that(self._titles(report)[-1]).is_equal_to("Left Out (failure 3)")
        assert_that(sum(sizes[:-1])).is_less_than_or_equal_to(60_000)

    def test_two_blocks_in_one_report_share_its_budget(self):
        first = _collected_from(_wide(1), _wide(2))
        second = _collected_from(_wide(3), _wide(4))
        report = _run_hook(_make_report(when="teardown"), _make_call(exc=ExceptionGroup("teardown", [first, second])))
        assert_that(self._titles(report)).is_equal_to(
            [
                "AssertionFailure (leaf 1 of 2, failure 1 of 2)",
                "Structured Diff (leaf 1 of 2, failure 1 of 2)",
                "AssertionFailure (leaf 1 of 2, failure 2 of 2)",
                "Structured Diff (leaf 1 of 2, failure 2 of 2)",
                "Left Out (leaf 2 of 2, failures 1 to 2)",
            ]
        )

    def test_two_blocks_in_one_report_share_its_twenty(self):
        def block(start):
            return _collected_from(
                *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(start, start + 15)]
            )

        report = _run_hook(
            _make_report(when="teardown"), _make_call(exc=ExceptionGroup("teardown", [block(0), block(15)]))
        )
        titles = self._titles(report)
        assert_that(titles).is_length(41)
        assert_that(titles[-2:]).is_equal_to(
            ["Structured Diff (leaf 2 of 2, failure 5 of 15)", "Left Out (leaf 2 of 2, failures 6 to 15)"]
        )

    def test_a_failure_whose_line_cannot_be_written_leaves_the_others(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        broken = AssertionOutcome(message=_UnsplittableMessage("broken"), diff=diff)
        good = AssertionOutcome(message="good", diff=diff)
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(broken, good))))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (failure 2 of 2)"])

    def test_a_failure_whose_sections_were_all_refused_was_still_drawn(self):
        failure = _collected_from(*[lambda n=n: assert_that([n]).contains(-1) for n in range(21)])
        report = _make_report()
        report.longrepr = _RefusesOnce()
        _run_hook(report, _make_call(exc=failure))
        titles = self._titles(report)
        assert_that(titles).is_length(20)
        assert_that(titles[-2:]).is_equal_to(["Structured Diff (failure 20 of 21)", "Left Out (failure 21)"])

    def test_a_failure_too_wide_for_what_is_left_takes_one_of_the_twenty(self):
        failure = _collected_from(
            _wide(1), _wide(2), *[_wide(3) for _ in range(18)], lambda: assert_that([1]).contains(3)
        )
        with patch("assertpy.pytest_plugin._format_diff", wraps=_format_diff) as drawn:
            report = _run_hook(_make_report(), _make_call(exc=failure))
        assert_that(drawn.call_count).is_equal_to(2 * 20)
        assert_that(self._titles(report)[-1]).is_equal_to("Left Out (failures 3 to 21)")

    def test_a_representation_that_refuses_one_section_costs_that_section_alone(self):
        failure = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}), lambda: assert_that([2]).contains(3))
        report = _make_report()
        report.longrepr = _RefusesOnce()
        _run_hook(report, _make_call(exc=failure))
        assert_that(self._titles(report)).is_equal_to(
            ["Structured Diff (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]
        )

    def test_a_representation_that_refuses_one_section_costs_that_failure_alone(self):
        failure = _collected_from(lambda: assert_that([1]).contains(3), lambda: assert_that([2]).contains(3))
        report = _make_report()
        report.longrepr = _RefusesOnce()
        _run_hook(report, _make_call(exc=failure))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (failure 2 of 2)"])

    def test_one_that_cannot_be_rendered_leaves_the_others(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        good = AssertionOutcome(message="good", diff=diff)
        broken = AssertionOutcome(message="broken", diff=_UnrenderableDiff())
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(good, broken, good))))
        assert_that(self._titles(report)).is_equal_to(
            ["Structured Diff (failure 1 of 3)", "Structured Diff (failure 3 of 3)"]
        )

    def test_each_diff_keeps_a_coloured_copy_under_its_own_title(self):
        failure = _collected_from(
            lambda: assert_that({2: 4}).is_equal_to({2: 3}), lambda: assert_that({5: 6}).is_equal_to({5: 7})
        )
        report = _run_hook(_make_report(), _make_call(exc=failure))
        colored = vars(report).get(_COLORED, {})
        assert_that(sorted(colored)).is_equal_to(
            ["Structured Diff (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]
        )
        assert_that(colored["Structured Diff (failure 2 of 2)"]).starts_with(
            f"{_entry(failure, 2)}\n\x1b[36mdiff (dict):"
        )

    @pytest.mark.parametrize(
        "failures",
        [
            RuntimeError("a property that raises"),
            [AssertionOutcome(message="in a list", actual=1, actual_provided=True)],
        ],
        ids=["raises", "not-a-tuple"],
    )
    def test_failures_that_are_not_a_blocks_are_left_alone(self, failures):
        class Odd(AssertionFailure):
            @property
            def failures(self):
                if isinstance(failures, Exception):
                    raise failures
                return failures

            @failures.setter
            def failures(self, value):
                pass

        report = _make_report()
        try:
            _run_hook(report, _make_call(exc=Odd("odd")))
            raised = None
        except Exception as error:  # the report is built inside pytest's own hook, where this would end the run
            raised = error
        assert_that(raised).is_none()
        assert_that(_sections(report)).is_empty()

    def test_an_item_that_is_no_record_is_skipped(self):
        named = AssertionOutcome(message="named", actual=1, actual_provided=True)
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(object(), named))))
        assert_that(self._titles(report)).is_equal_to(["AssertionFailure (failure 1 of 1)"])

    def test_allure_gets_each_under_its_number(self):
        mock = _mock_allure()
        failure = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}), lambda: assert_that([1]).contains(3))
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        assert_that([one.kwargs["name"] for one in mock.attach.call_args_list]).is_equal_to(
            ["Structured Diff (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]
        )

    def test_allure_takes_the_first_twenty(self):
        mock = _mock_allure()
        failure = _collected_from(*[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(25)])
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        names = [one.kwargs["name"] for one in mock.attach.call_args_list]
        assert_that(names).is_length(21)
        assert_that(names[-2:]).is_equal_to(["Structured Diff (failure 20 of 25)", "Left Out (failures 21 to 25)"])
        assert_that(mock.attach.call_args_list[-1].kwargs["body"]).is_equal_to(
            "No attachment for lack of room: failures 21 to 25 of 25. The summary lists each, its diff in compact rows."
        )

    def test_an_attachment_refused_for_one_leaves_the_next_its_own(self):
        mock = _mock_allure()
        mock.attach.side_effect = [RuntimeError("refused"), None]
        failure = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}), lambda: assert_that([1]).contains(3))
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        assert_that(mock.attach.call_args_list).is_length(2)
        assert_that(mock.attach.call_args_list[1].kwargs["name"]).is_equal_to("Structured Diff (failure 2 of 2)")

    def test_one_too_wide_for_what_is_left_costs_no_later_one_its_sections(self):
        failure = _collected_from(_wide(1), _wide(2), _wide(3), lambda: assert_that([1]).contains(3))
        report = _run_hook(_make_report(), _make_call(exc=failure))
        assert_that(self._titles(report)).is_equal_to(
            [
                "AssertionFailure (failure 1 of 4)",
                "Structured Diff (failure 1 of 4)",
                "AssertionFailure (failure 2 of 4)",
                "Structured Diff (failure 2 of 4)",
                "Structured Diff (failure 4 of 4)",
                "Left Out (failure 3)",
            ]
        )
        assert_that(_sections(report)[-1][1]).is_equal_to(
            "No section for lack of room: failure 3 of 4. The summary lists each, its diff in compact rows."
        )

    def test_past_twenty_the_rest_are_not_drawn(self):
        failure = _collected_from(*[lambda n=n: assert_that([n]).contains(-1) for n in range(25)])
        with patch("assertpy.pytest_plugin._format_diff", wraps=_format_diff) as drawn:
            report = _run_hook(_make_report(), _make_call(exc=failure))
        assert_that(drawn.call_count).is_equal_to(40)
        assert_that(self._titles(report)[-1]).is_equal_to("Left Out (failures 21 to 25)")

    @pytest.mark.parametrize("escaping", [RuntimeError, AssertionError], ids=["error", "assert"])
    def test_an_exception_that_escaped_the_block_brings_what_it_had_collected(self, escaping):
        def asks():
            with soft_assertions():
                assert_that({2: 4}).is_equal_to({2: 3})
                assert_that(lambda: 1).eventually_sync(timeout=0.05, interval=0.01).is_equal_to(2)
                raise escaping("escaped")

        with pytest.raises(escaping) as raised:
            asks()
        report = _run_hook(_make_report(), _make_call(exc=raised.value))
        titles = self._titles(report)
        assert_that(titles).contains("Structured Diff (failure 1 of 2)", "Polling Trace (failure 2 of 2)")
        assert_that(titles).does_not_contain("AssertionFailure", "Structured Diff")

    def test_an_exception_that_refuses_attributes_still_brings_what_was_collected(self):
        class FrozenError(Exception):
            def __setattr__(self, name, value):
                raise AttributeError(name)

        def asks():
            with soft_assertions():
                assert_that([1]).contains(3)
                raise FrozenError("frozen")

        with pytest.raises(FrozenError) as raised:
            asks()
        report = _run_hook(_make_report(), _make_call(exc=raised.value))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (failure 1 of 1)"])

    def test_with_the_diff_turned_off_a_diff_alone_is_not_left_out(self):
        failure = _collected_from(
            *[lambda n=n: assert_that(n).is_equal_to(-1) for n in range(20)], lambda: assert_that([1]).contains(3)
        )
        item = _make_item()
        item.config._assertpy_diff_enabled = False
        report = _run_hook(_make_report(), _make_call(exc=failure), item=item)
        titles = self._titles(report)
        assert_that(titles).is_length(20)
        assert_that(titles[-1]).is_equal_to("AssertionFailure (failure 20 of 21)")

    def test_a_group_that_escaped_the_block_brings_what_it_had_collected(self):
        def asks():
            with soft_assertions():
                assert_that([1]).contains(3)
                raise ExceptionGroup("tasks", [RuntimeError("one"), RuntimeError("two")])

        with pytest.raises(ExceptionGroup) as raised:
            asks()
        report = _run_hook(_make_report(), _make_call(exc=raised.value))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff (group, failure 1 of 1)"])

    def test_an_aggregate_that_escaped_another_block_shows_its_own_and_the_notes(self):
        earlier = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}))

        def asks():
            with soft_assertions():
                assert_that([1]).contains(3)
                raise earlier

        with pytest.raises(AssertionFailure):
            asks()
        report = _run_hook(_make_report(), _make_call(exc=earlier))
        assert_that(self._titles(report)).is_equal_to(
            [
                "AssertionFailure (failure 1 of 1)",
                "Structured Diff (failure 1 of 1)",
                "Structured Diff (note, failure 1 of 1)",
            ]
        )

    def test_a_group_whose_dictionary_cannot_be_read_costs_nothing(self):
        class OpaqueGroup(ExceptionGroup):
            @property
            def __dict__(self):
                raise RuntimeError("no dictionary")

        report = _make_report()
        try:
            _run_hook(report, _make_call(exc=OpaqueGroup("tasks", [RuntimeError("one")])))
            raised = None
        except Exception as error:  # the report is built inside pytest's own hook, where this would end the run
            raised = error
        assert_that(raised).is_none()
        assert_that(_sections(report)).is_empty()

    def test_a_record_whose_class_cannot_be_asked_costs_nothing(self):
        class Sly:
            @property
            def __class__(self):
                raise RuntimeError("asked")

        report = _make_report()
        try:
            _run_hook(report, _make_call(exc=AssertionFailure("block", failures=(Sly(),))))
            raised = None
        except Exception as error:  # the report is built inside pytest's own hook, where this would end the run
            raised = error
        assert_that(raised).is_none()
        assert_that(_sections(report)).is_empty()

    def test_allure_counts_a_failure_whose_later_attachment_was_refused(self):
        mock = _mock_allure()

        def refuses_diffs(*, body, name, attachment_type):
            if name.startswith("Structured Diff"):
                raise RuntimeError("refused")

        mock.attach.side_effect = refuses_diffs
        failure = _collected_from(*[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(25)])
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock, allure_mode="full")
        names = [one.kwargs["name"] for one in mock.attach.call_args_list]
        kept = [name for name in names if not name.startswith("Structured Diff")]
        assert_that(kept).is_length(21)
        assert_that(kept[-2:]).is_equal_to(["AssertionFailure (failure 20 of 25)", "Left Out (failures 21 to 25)"])

    def test_allure_keeps_a_failures_diff_when_its_values_were_refused(self):
        mock = _mock_allure()

        def refuses_values(*, body, name, attachment_type):
            if name.startswith("AssertionFailure"):
                raise RuntimeError("refused")

        mock.attach.side_effect = refuses_values
        failure = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock, allure_mode="full")
        assert_that([one.kwargs["name"] for one in mock.attach.call_args_list]).is_equal_to(
            ["AssertionFailure (failure 1 of 1)", "Structured Diff (failure 1 of 1)"]
        )

    def test_allure_names_no_one_left_out_whose_diff_is_empty(self):
        mock = _mock_allure()
        empty = AssertionOutcome(message="empty", diff=DiffResult(kind="dict", entries=[]))
        diffs = [
            AssertionOutcome(
                message=f"m{n}", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=n, expected=0)])
            )
            for n in range(20)
        ]
        _run_hook_with_allure(_make_report(), _make_call(exc=AssertionFailure("block", failures=(*diffs, empty))), mock)
        assert_that(mock.attach.call_count).is_equal_to(20)

    def test_allure_tries_twenty_when_every_attachment_is_refused(self):
        mock = _mock_allure()
        mock.attach.side_effect = RuntimeError("refused")
        failure = _collected_from(*[lambda n=n: assert_that([n]).contains(-1) for n in range(25)])
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        assert_that(mock.attach.call_count).is_equal_to(21)

    def test_allure_names_no_one_left_out_who_had_nothing_to_attach(self):
        mock = _mock_allure()
        failure = _collected_from(
            *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(20)],
            lambda: assert_that(False).is_true(),
        )
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        names = [one.kwargs["name"] for one in mock.attach.call_args_list]
        assert_that(names).is_length(20)
        assert_that(names[-1]).is_equal_to("Structured Diff (failure 20 of 21)")

    def test_an_exception_that_escaped_two_blocks_brings_both_collections(self):
        error = RuntimeError("boom")

        def first():
            with soft_assertions():
                assert_that([1]).contains(3)
                raise error

        def second():
            with soft_assertions():
                assert_that({2: 4}).is_equal_to({2: 3})
                raise error

        with pytest.raises(RuntimeError):
            first()
        with pytest.raises(RuntimeError):
            second()
        report = _run_hook(_make_report(), _make_call(exc=error))
        assert_that(self._titles(report)).is_equal_to(
            [
                "Structured Diff (note 1 of 2, failure 1 of 1)",
                "AssertionFailure (note 2 of 2, failure 1 of 1)",
                "Structured Diff (note 2 of 2, failure 1 of 1)",
            ]
        )
        assert_that(error.__notes__).is_length(2)

    def test_a_broken_diff_costs_its_failure_neither_values_nor_trace_nor_the_next_failure(self):
        broken = AssertionOutcome(
            message="broken", actual=1, actual_provided=True, expected=2, diff=_UnrenderableDiff(), trace=_make_trace()
        )
        good = AssertionOutcome(
            message="good", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        )
        report = _run_hook(_make_report(), _make_call(exc=AssertionFailure("block", failures=(broken, good))))
        assert_that(self._titles(report)).is_equal_to(
            ["AssertionFailure (failure 1 of 2)", "Polling Trace (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]
        )

    @pytest.mark.parametrize(
        ("mode", "names"),
        [
            ("diff", ["Polling Trace (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]),
            (
                "full",
                [
                    "AssertionFailure (failure 1 of 2)",
                    "Polling Trace (failure 1 of 2)",
                    "Structured Diff (failure 2 of 2)",
                ],
            ),
        ],
    )
    def test_allure_keeps_a_broken_diffs_values_and_trace_and_the_next_failure(self, mode, names):
        mock = _mock_allure()
        broken = AssertionOutcome(
            message="broken", actual=1, actual_provided=True, expected=2, diff=_UnrenderableDiff(), trace=_make_trace()
        )
        good = AssertionOutcome(
            message="good", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        )
        failure = AssertionFailure("block", failures=(broken, good))
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock, allure_mode=mode)
        assert_that([one.kwargs["name"] for one in mock.attach.call_args_list]).is_equal_to(names)

    def test_allure_skips_a_record_that_raises_when_read_and_attaches_the_next(self):
        class Untold:
            def __bool__(self):
                raise RuntimeError("cannot be told")

        mock = _mock_allure()
        odd = AssertionOutcome(message="odd", actual=1, actual_provided=Untold())
        good = AssertionOutcome(
            message="good", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=0)])
        )
        failure = AssertionFailure("block", failures=(odd, good))
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock, allure_mode="full")
        assert_that([one.kwargs["name"] for one in mock.attach.call_args_list]).is_equal_to(
            ["Structured Diff (failure 2 of 2)"]
        )

    def test_a_raised_failure_keeps_its_values_and_trace_when_its_diff_cannot_be_drawn(self):
        exc = AssertionFailure("fail", actual=1, expected=2, diff=_UnrenderableDiff(), trace=_make_trace())
        report = _run_hook(_make_report(), _make_call(exc=exc))
        assert_that(self._titles(report)).is_equal_to(["AssertionFailure", "Polling Trace"])

    def test_values_that_cannot_be_drawn_cost_the_diff_nothing(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        with patch("assertpy.pytest_plugin._value_rows", side_effect=RuntimeError("cannot draw")):
            report = _run_hook(
                _make_report(), _make_call(exc=AssertionFailure("fail", actual=1, expected=2, diff=diff))
            )
        assert_that(self._titles(report)).is_equal_to(["Structured Diff"])

    def test_a_raised_failure_keeps_its_trace_when_the_report_will_not_keep_a_colour(self):
        class RefusesColour(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("no colour here")

        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        vars(report)[_COLORED] = RefusesColour()
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff, trace=_make_trace())))
        assert_that(self._titles(report)).is_equal_to(["Structured Diff", "Polling Trace"])

    def test_a_colour_that_cannot_be_drawn_costs_the_plain_diff_nothing(self):
        def plain_only(diff, *, color=False, max_entries=50):
            if color:
                raise RuntimeError("no colour drawn")
            return _format_diff(diff, max_entries=max_entries)

        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        with patch("assertpy.pytest_plugin._format_diff", side_effect=plain_only):
            _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff)))
        assert_that(_sections(report)).is_equal_to([("Structured Diff", "diff (dict):\n  k:\n    - 1\n    + 2")])
        assert_that(vars(report).get(_COLORED, {})).is_empty()

    def test_a_colour_the_report_will_not_keep_costs_no_section(self):
        class RefusesColour(dict):
            def __setitem__(self, key, value):
                raise RuntimeError("no colour here")

        failure = _collected_from(lambda: assert_that([1]).contains(3), lambda: assert_that([2]).contains(3))
        report = _make_report()
        vars(report)[_COLORED] = RefusesColour()
        _run_hook(report, _make_call(exc=failure))
        assert_that(self._titles(report)).is_equal_to(
            ["Structured Diff (failure 1 of 2)", "Structured Diff (failure 2 of 2)"]
        )

    def test_a_carried_record_reads_as_a_raised_one(self):
        def asks():
            with soft_assertions():
                assert_that({2: 4}).is_equal_to({2: 3})
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError) as raised:
            asks()
        carried = _run_hook(_make_report(), _make_call(exc=raised.value))
        aggregate = _collected_from(lambda: assert_that({2: 4}).is_equal_to({2: 3}))
        collected = _run_hook(_make_report(), _make_call(exc=aggregate))
        assert_that([body.split("\n", 1)[1] for _, body in _sections(carried)]).is_equal_to(
            [body.split("\n", 1)[1] for _, body in _sections(collected)]
        )

    @pytest.mark.parametrize(
        "carried", ["not a list", [("not a pair",)], [([object()], ())], [(("not a record",), ())]]
    )
    def test_something_else_under_the_carried_name_is_left_alone(self, carried):
        escaping = RuntimeError("boom")
        vars(escaping)["_assertpy_collected"] = carried
        report = _make_report()
        try:
            _run_hook(report, _make_call(exc=escaping))
            raised = None
        except Exception as error:  # the report is built inside pytest's own hook, where this would end the run
            raised = error
        assert_that(raised).is_none()
        assert_that(_sections(report)).is_empty()

    def test_a_failure_of_a_subclass_that_refuses_the_pairs_keeps_its_records(self):
        class Odd(AssertionFailure):
            @property
            def _compared_pairs(self):
                raise RuntimeError("a property that raises")

            @_compared_pairs.setter
            def _compared_pairs(self, value):
                pass

        named = AssertionOutcome(message="named", actual=1, actual_provided=True, expected=2)
        report = _make_report()
        try:
            _run_hook(report, _make_call(exc=Odd("odd", failures=(named,))))
            raised = None
        except Exception as error:  # the report is built inside pytest's own hook, where this would end the run
            raised = error
        assert_that(raised).is_none()
        assert_that(_sections(report)).is_equal_to(
            [("AssertionFailure (failure 1 of 1)", "1. named\n  actual:   1\n  expected: 2")]
        )

    def test_under_ignore_the_values_shown_are_the_pair_compared(self):
        def ask():
            assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 3}, ignore="a")

        with pytest.raises(AssertionFailure) as raised:
            ask()
        alone = dict(_sections(_run_hook(_make_report(), _make_call(exc=raised.value))))["AssertionFailure"]
        failure = _collected_from(ask)
        shown = dict(_sections(_run_hook(_make_report(), _make_call(exc=failure))))
        assert_that(shown["AssertionFailure (failure 1 of 1)"]).is_equal_to(f"{_entry(failure, 1)}\n{alone}")
        assert_that(alone).does_not_contain("'a'")

    def test_allure_shares_the_reports_twenty_across_its_blocks(self):
        def block(start):
            return _collected_from(
                *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(start, start + 15)]
            )

        mock = _mock_allure()
        group = ExceptionGroup("teardown", [block(0), block(15)])
        _run_hook_with_allure(_make_report(when="teardown"), _make_call(exc=group), mock)
        names = [one.kwargs["name"] for one in mock.attach.call_args_list]
        assert_that(names).is_length(21)
        assert_that(names[-2:]).is_equal_to(
            ["Structured Diff (leaf 2 of 2, failure 5 of 15)", "Left Out (leaf 2 of 2, failures 6 to 15)"]
        )

    def test_allure_takes_no_room_for_a_failure_that_attached_nothing(self):
        mock = _mock_allure()
        failure = _collected_from(
            lambda: assert_that(False).is_true(),
            *[lambda n=n: assert_that({"k": n}).is_equal_to({"k": -1}) for n in range(20)],
        )
        _run_hook_with_allure(_make_report(), _make_call(exc=failure), mock)
        names = [one.kwargs["name"] for one in mock.attach.call_args_list]
        assert_that(names).is_length(20)
        assert_that(names[-1]).is_equal_to("Structured Diff (failure 21 of 21)")


class TestTheSectionsGoWhereEveryReaderLooks:
    """On the failure's own representation, which the terminal, a JUnit body and an IDE runner all render."""

    def test_nothing_is_left_on_the_captured_output_channel(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        _run_hook(report, _make_call(exc=AssertionFailure("fail", actual=1, expected=2, diff=diff)))
        assert_that(report.sections).is_empty()
        assert_that([title for title, _ in _sections(report)]).contains("AssertionFailure", "Structured Diff")

    def test_a_failure_rendered_as_a_string_carries_the_section_in_the_string(self):
        """What a custom item's `repr_failure` returns, and every reader prints it as it is."""
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        report.longrepr = "a failure some other plugin rendered"
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff)))
        assert_that(report.longrepr).starts_with("a failure some other plugin rendered\n").contains(
            " Structured Diff ", "diff (dict)"
        )
        assert_that(report.sections).is_empty()

    def test_a_representation_with_no_sections_is_carried_as_its_text(self):
        """A custom item's own representation, whose text is what JUnit and xdist read of it anyway."""
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        report.longrepr = _OwnRepr()
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff)))
        assert_that(report.longrepr).starts_with("an item's own rendering\n").contains(
            " Structured Diff ", "diff (dict)"
        )
        assert_that(report.sections).is_empty()

    def test_a_failure_with_no_representation_at_all_falls_back_to_the_report(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        report = _make_report()
        report.longrepr = None
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=diff)))
        assert_that([title for title, _ in report.sections]).contains("Structured Diff")

    def test_a_representation_that_refuses_a_section_still_gets_its_allure_attachment(self):
        mock = _mock_allure()
        report = _make_report()
        report.longrepr.addsection = MagicMock(side_effect=RuntimeError("no sections here"))
        exc = AssertionFailure(
            "fail", diff=DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        )
        _run_hook_with_allure(report, _make_call(exc=exc), mock)
        assert_that(mock.attach.call_count).is_equal_to(1)

    def test_skip_when_not_failed(self):
        report = _make_report(failed=False)
        call = _make_call(exc=AssertionError("x"))
        _run_hook(report, call)
        assert_that(_sections(report)).is_empty()

    def test_skip_when_excinfo_is_none(self):
        report = _make_report()
        call = _make_call(exc=None)
        _run_hook(report, call)
        assert_that(_sections(report)).is_empty()

    def test_skip_when_not_assertion_error(self):
        report = _make_report()
        call = _make_call(exc=ValueError("not assertion"))
        _run_hook(report, call)
        assert_that(_sections(report)).is_empty()

    def test_skip_when_no_structured_data(self):
        report = _make_report()
        call = _make_call(exc=AssertionError("plain error"))
        _run_hook(report, call)
        assert_that(_sections(report)).is_empty()


class TestHookActualExpected:
    def test_both_actual_and_expected(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in _sections(report)]
        assert_that(titles).contains("AssertionFailure")
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("expected")

    def test_only_actual(self):
        exc = AssertionFailure("fail", actual=42)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("42")
        assert_that(body).does_not_contain("expected")

    def test_only_expected(self):
        exc = AssertionFailure("fail", expected="abc")
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).contains("expected")
        assert_that(body).contains("abc")
        assert_that(body).does_not_contain("actual")


class TestTheValuesSectionShowsOnlyValuesTheAssertionNamed:
    """Every failure carries `actual` now, so "the attribute is set" stopped meaning "the reader has
    not seen this value yet".

    The section exists for values the message elided. A value filled in from the builder is the same
    one the message opens with, so rendering it would put a repeat under every single failure. The
    three tests above still construct the exception by hand, which is the case with no record at all,
    and those keep the older behaviour.
    """

    def test_a_failure_that_never_named_actual_gets_no_values_section(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).contains_key("x")
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        titles = [title for title, _ in _sections(report)]
        assert_that(failure.value.actual).is_equal_to({"a": 1})
        assert_that(titles).does_not_contain("AssertionFailure")

    def test_a_failure_that_named_its_values_still_gets_one(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to({"a": 2})
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).contains("actual")
        assert_that(body).contains("expected")

    def test_an_expected_of_none_is_shown_rather_than_read_as_unset(self):
        # `expected is not None` cannot tell "compared against None" from "no expected at all"
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to(None)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).contains("expected: None")


class TestHookDiff:
    def test_diff_section_added(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="key1", actual="a", expected="b"),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in _sections(report)]
        assert_that(titles).contains("Structured Diff")
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("key1")

    def test_diff_without_actual_expected(self):
        diff = DiffResult(
            kind="scalar",
            entries=[
                DiffEntry(path=".", actual=1, expected=2),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in _sections(report)]
        assert_that(titles).contains("Structured Diff")
        assert_that(titles).does_not_contain("AssertionFailure")

    def test_actual_expected_and_diff_together(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="x", actual=1, expected=2),
            ],
        )
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        titles = [title for title, _ in _sections(report)]
        assert_that(titles).contains("AssertionFailure")
        assert_that(titles).contains("Structured Diff")


class TestFormatDiff:
    def test_sequence_both_present(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[0]", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("[0]:")
        assert_that(body).contains("- 1")
        assert_that(body).contains("+ 2")

    def test_sequence_actual_only(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[1]", actual=99, expected=None, absent="expected")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("[1]: - 99")

    def test_sequence_expected_only(self):
        diff = DiffResult(kind="sequence", entries=[DiffEntry(path="[2]", actual=None, absent="actual", expected=42)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("[2]: + 42")

    def test_set_extra_and_missing(self):
        diff = DiffResult(
            kind="set",
            entries=[
                DiffEntry(path="extra", actual=5, expected=None, absent="expected"),
                DiffEntry(path="missing", actual=None, absent="actual", expected=10),
            ],
        )
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("extra:")
        assert_that(body).contains("5")
        assert_that(body).contains("missing:")
        assert_that(body).contains("10")

    def test_string_diff(self):
        diff = DiffResult(kind="string", entries=[DiffEntry(path="line 1", actual="foo", expected="bar")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("line 1:")
        assert_that(body).contains("foo")
        assert_that(body).contains("bar")

    def test_set_extra_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="extra", actual=5, expected=None, absent="expected")])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("extra:")
        assert_that(body).does_not_contain("missing")

    def test_set_missing_only(self):
        diff = DiffResult(kind="set", entries=[DiffEntry(path="missing", actual=None, absent="actual", expected=10)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Structured Diff"]
        assert_that(body).contains("missing:")
        assert_that(body).does_not_contain("extra")

    def test_a_diff_with_nothing_in_it_hangs_no_section(self):
        """An empty section read as a diff that found the two sides equal, under a message saying they differ.

        Issue 46 showed one: a model whose serialiser folded the two values into one text.  The JSON
        attachment already answered `None` for the same diff.
        """
        exc = AssertionFailure("fail", diff=DiffResult(kind="scalar", entries=[]))
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that([title for title, _ in _sections(report)]).does_not_contain("Structured Diff")


class TestDiffToJson:
    def test_returns_none_for_empty_entries(self):
        diff = DiffResult(kind="dict")
        assert_that(_diff_to_json(diff)).is_none()

    def test_payload_carries_format_version(self):
        # consumers branch on it: 1 repr strings, 2 typed values, 3 a named absent side, 4 a machine-readable path
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["format"]).is_equal_to(4)

    def test_an_entry_carries_the_steps_that_reached_it(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"users": [{"roles": {7: "admin"}}]}).is_equal_to({"users": [{"roles": {7: "guest"}}]})
        entry = json.loads(_diff_to_json(failure.value.diff))["entries"][0]
        assert_that(entry["path"]).is_equal_to("users[0].roles.7")
        assert_that(entry["steps"]).is_equal_to(
            [
                {"kind": "key", "value": "users"},
                {"kind": "index", "value": 0},
                {"kind": "key", "value": "roles"},
                {"kind": "key", "value": 7},
            ]
        )

    def test_a_step_names_its_side_only_where_the_two_have_shifted_apart(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that([1, 2, 3, 4]).is_equal_to([0, 1, 2, 3, 4])
        entries = json.loads(_diff_to_json(failure.value.diff))["entries"]
        sided = [step for entry in entries for step in entry.get("steps", []) if "side" in step]
        assert_that(sided).is_not_empty()
        assert_that({step["side"] for step in sided}).is_subset_of({"actual", "expected"})

    def test_an_entry_with_no_location_carries_no_steps(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path=".", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]).does_not_contain_key("steps")

    def test_a_step_value_that_json_cannot_express_degrades_rather_than_failing(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({(1, 2): "a"}).is_equal_to({(1, 2): "b"})
        step = json.loads(_diff_to_json(failure.value.diff))["entries"][0]["steps"][0]
        assert_that(step["kind"]).is_equal_to("key")
        assert_that(step["value"]).is_equal_to([1, 2])

    def test_an_absent_side_is_named_in_the_payload(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="b", actual=2, expected=None, absent="expected")])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]["absent"]).is_equal_to("expected")

    def test_a_value_that_is_none_carries_no_absent_key(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=None)])
        entry = json.loads(_diff_to_json(diff))["entries"][0]
        assert_that(entry).does_not_contain_key("absent")
        assert_that(entry["expected"]).is_none()

    def test_returns_valid_json(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="a", actual=1, expected=2)])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["kind"]).is_equal_to("dict")
        assert_that(result["entries"]).is_length(1)
        assert_that(result["entries"][0]["path"]).is_equal_to("a")
        assert_that(result["entries"][0]["actual"]).is_equal_to(1)
        assert_that(result["entries"][0]["expected"]).is_equal_to(2)

    def test_string_values_stay_native_strings(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual="<b>", expected="&")])
        result = json.loads(_diff_to_json(diff))
        assert_that(result["entries"][0]["actual"]).is_equal_to("<b>")
        assert_that(result["entries"][0]["expected"]).is_equal_to("&")

    def test_multiple_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[
                DiffEntry(path="x", actual=1, expected=2),
                DiffEntry(path="y", actual=3, expected=4),
            ],
        )
        result = json.loads(_diff_to_json(diff))
        assert_that(result["entries"]).is_length(2)
        assert_that(result["entries"][0]["path"]).is_equal_to("x")
        assert_that(result["entries"][1]["path"]).is_equal_to("y")

    def test_truncates_to_max_entries(self):
        diff = DiffResult(
            kind="dict",
            entries=[DiffEntry(path=f"k{i}", actual=i, expected=i + 1) for i in range(5)],
        )
        result = json.loads(_diff_to_json(diff, max_entries=2))
        assert_that(result["entries"]).is_length(2)
        assert_that(result["truncated"]).is_equal_to(3)


class _RaisingRepr:
    def __repr__(self):
        raise RuntimeError("broken repr")


class TestJsonSafe:
    """The attachment sanitizer is typed where possible, and total and bounded everywhere else."""

    def test_native_scalars_pass_through(self):
        assert_that(_json_safe(None)).is_none()
        assert_that(_json_safe(True)).is_true()
        assert_that(_json_safe(7)).is_equal_to(7)
        assert_that(_json_safe(1.5)).is_equal_to(1.5)
        assert_that(_json_safe("text")).is_equal_to("text")

    def test_non_finite_floats_become_markers(self):
        assert_that(_json_safe(float("nan"))).is_equal_to({"__repr__": "nan"})
        assert_that(_json_safe(float("inf"))).is_equal_to({"__repr__": "inf"})

    @pytest.fixture
    def printable_digits(self):
        """The interpreter's default cap, set explicitly so an environment that lifted it cannot hide the case."""
        if not hasattr(sys, "set_int_max_str_digits"):
            pytest.skip("the digit cap arrived in 3.10.7")
        previous = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(4300)
        yield
        sys.set_int_max_str_digits(previous)

    def test_an_integer_too_long_to_print_becomes_a_marker(self, printable_digits):
        assert_that(_json_safe(10**5000)).is_equal_to({"__repr__": "<unreprable int>"})

    def test_a_diff_holding_one_still_serialises(self, printable_digits):
        """`json.dumps` raised on it, and the plugin's barrier dropped the whole attachment without a word."""
        with pytest.raises(AssertionError) as failure:
            assert_that(10**5000).is_equal_to(1)
        entry = json.loads(_diff_to_json(failure.value.diff))["entries"][0]
        assert_that(entry["actual"]).is_equal_to({"__repr__": "<unreprable int>"})

    def test_a_repr_returning_a_refusing_string_is_read_as_plain_text(self):
        """The fallback itself reads the `repr`, so a string whose `len()` raises escaped the boundary."""

        class Loud(str):
            def __len__(self):
                raise RuntimeError("no length")

        class Odd:
            def __repr__(self):
                return Loud("odd")

        converted = _json_safe([Odd()])
        assert_that(converted).is_equal_to([{"__repr__": "odd"}])
        assert_that(type(converted[0]["__repr__"])).is_same_as(str)

    def test_a_type_whose_name_raises_is_still_named(self):
        """The marker for a broken `repr` names the type, and a metaclass can make that attribute raise too."""

        class Nameless(type):
            @property
            def __name__(cls):
                raise RuntimeError("no name")

        class Hostile(metaclass=Nameless):
            def __repr__(self):
                raise RuntimeError("no repr")

        assert_that(_json_safe([Hostile()])).is_equal_to([{"__repr__": "<unreprable Hostile>"}])

    def test_a_type_named_with_a_refusing_string_is_still_named(self):
        class Loud(str):
            def __format__(self, spec):
                raise RuntimeError("no format")

        class Hostile:
            def __repr__(self):
                raise RuntimeError("no repr")

        Hostile.__name__ = Loud("Hostile")
        assert_that(_json_safe([Hostile()])).is_equal_to([{"__repr__": "<unreprable Hostile>"}])

    def test_a_key_that_stopped_hashing_costs_nothing(self):
        """Its text is copied into an exact `str` before it keys the output, so its own `__hash__` never runs."""

        class Flaky(str):
            armed = False

            def __hash__(self):
                if self.armed:
                    raise RuntimeError("no hash")
                return str.__hash__(self)

        key = Flaky("k")
        source = {key: 1, "b": 2}
        Flaky.armed = True
        assert_that(_json_safe(source)).is_equal_to({"k": 1, "b": 2})

    def test_a_str_returning_a_refusing_string_is_read_as_plain_text(self):
        class Loud(str):
            def __len__(self):
                raise RuntimeError("no length")

        class Odd:
            def __str__(self):
                return Loud("odd")

        assert_that(type(errors_module._safe_str(Odd()))).is_same_as(str)

    def test_a_value_whose_own_method_raises_costs_only_itself(self):
        class Refusing(dict):
            def items(self):
                raise RuntimeError("no items")

        assert_that(_json_safe([1, Refusing(a=1)])).is_equal_to([1, {"__repr__": "{'a': 1}"}])

    def test_huge_string_is_truncated(self):
        result = _json_safe("x" * 10_000)
        assert_that(result).contains("more chars")
        assert_that(len(result)).is_less_than(5_000)

    def test_containers_stay_typed(self):
        assert_that(_json_safe({"a": [1, (2, 3)]})).is_equal_to({"a": [1, [2, 3]]})

    def test_a_mapping_with_a_non_string_key_is_written_as_pairs(self):
        """Rendered as text, `1` and `"1"` were the same key and one of the two was lost."""
        assert_that(_json_safe({1: "a", (2, 3): "b"})).is_equal_to(
            {"__type__": "dict", "__data__": [[1, "a"], [[2, 3], "b"]]}
        )
        assert_that(_json_safe({1: "a", "1": "b"})).is_equal_to(
            {"__type__": "dict", "__data__": [[1, "a"], ["1", "b"]]}
        )

    def test_a_string_keyed_mapping_is_written_as_it_was(self):
        assert_that(_json_safe({"a": 1, "b": [2]})).is_equal_to({"a": 1, "b": [2]})

    def test_oversized_dict_gets_truncation_marker(self):
        result = _json_safe({f"k{i:03d}": i for i in range(150)})
        assert_that(result["__truncated__"]).is_equal_to("... and 50 more keys")
        assert_that(result).is_length(101)

    def test_oversized_list_gets_truncation_marker(self):
        result = _json_safe(list(range(150)))
        assert_that(result).is_length(101)
        assert_that(result[-1]).is_equal_to({"__repr__": "... and 50 more items"})

    def test_set_uses_snapshot_envelope(self):
        assert_that(_json_safe({2, 1})).is_equal_to({"__type__": "set", "__data__": [1, 2]})
        assert_that(_json_safe(frozenset({"a"}))).is_equal_to({"__type__": "set", "__data__": ["a"]})

    def test_a_set_of_composites_still_recurses(self):
        assert_that(_json_safe({(1, 2)})).is_equal_to({"__type__": "set", "__data__": [[1, 2]]})

    def test_a_heterogeneous_set_sorts_by_repr(self):
        assert_that(_json_safe({1, "a"})).is_equal_to({"__type__": "set", "__data__": ["a", 1]})
        assert_that(_json_safe({2, 10})["__data__"]).is_equal_to([10, 2])

    def test_depth_cap_degrades_to_repr_marker(self):
        nested = {"level": 1}
        for _ in range(8):
            nested = {"level": nested}
        blob = json.dumps(_json_safe(nested))
        assert_that(blob).contains("__repr__")

    def test_the_depth_cap_holds_for_sequences_too(self):
        nested = [1]
        for _ in range(8):
            nested = [nested]
        blob = json.dumps(_json_safe(nested))
        assert_that(blob).contains("__repr__")

    def test_cycle_degrades_to_marker(self):
        cyclic = [1]
        cyclic.append(cyclic)
        assert_that(_json_safe(cyclic)).is_equal_to([1, {"__repr__": "<circular ref>"}])

    def test_arbitrary_object_becomes_repr_marker(self):
        class Point:
            def __repr__(self):
                return "Point(1, 2)"

        assert_that(_json_safe(Point())).is_equal_to({"__repr__": "Point(1, 2)"})

    def test_raising_repr_never_loses_the_attachment(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=_RaisingRepr(), expected=1)])
        body = json.loads(_diff_to_json(diff))
        assert_that(body["entries"][0]["actual"]).is_equal_to({"__repr__": "<unreprable _RaisingRepr>"})

    def test_output_is_strict_json(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=float("nan"), expected=1)])
        assert_that(json.loads(_diff_to_json(diff))["entries"][0]["actual"]).is_equal_to({"__repr__": "nan"})


def _make_trace():
    samples = [
        PollSample(elapsed=0.0, outcome="error", value=None, detail="ConnectionError('boot')", repeats=2),
        PollSample(elapsed=0.4, outcome="fail", value={"s": "PENDING"}, detail="Expected <...>"),
        PollSample(elapsed=0.8, outcome="fail", value={"s": "SHIPPED"}, detail="Expected <...>", repeats=3),
    ]
    return PollTrace(samples=samples, total_polls=6, dropped=0, elapsed=1.2, summary="probe recovered")


class TestPollingTrace:
    def test_terminal_section_renders_timeline(self):
        report = _make_report()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook(report, _make_call(exc=exc))
        body = dict(_sections(report))["Polling Trace"]
        assert_that(body).contains("polled 6 times over 1.2s; probe recovered")
        assert_that(body).contains("t=+0.0s error x2: ConnectionError('boot')")
        assert_that(body).contains("t=+0.8s fail x3:")

    def test_terminal_section_reports_dropped_samples(self):
        trace = PollTrace(samples=_make_trace().samples, total_polls=40, dropped=10, elapsed=9.0, summary="s")
        assert_that(_format_trace(trace)).contains("10 middle samples dropped")

    def test_trace_json_schema_and_deltas(self):
        body = json.loads(_trace_to_json(_make_trace()))
        assert_that(body["format"]).is_equal_to(2)
        assert_that(body["kind"]).is_equal_to("polling-trace")
        assert_that(body["total_polls"]).is_equal_to(6)
        assert_that(body["samples"]).is_length(3)
        assert_that(body["samples"][0]).does_not_contain_key("value")
        assert_that(body["samples"][0]["repeats"]).is_equal_to(2)
        assert_that(body["deltas"]).is_length(1)
        assert_that(body["deltas"][0]["entries"]).is_equal_to(
            [{"path": "s", "actual": "PENDING", "expected": "SHIPPED"}]
        )

    def test_trace_json_scalar_delta_falls_back_to_root_path(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.5, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=2, dropped=0, elapsed=1.0, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["deltas"][0]["entries"]).is_equal_to([{"path": ".", "actual": 1, "expected": 2}])

    def test_trace_json_reports_dropped_and_skips_equal_neighbors(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value={"s": 1}, detail="d"),
            PollSample(elapsed=0.4, outcome="error", value=None, detail="ConnectionError('x')"),
            PollSample(elapsed=0.8, outcome="fail", value={"s": 1}, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=30, dropped=7, elapsed=2.0, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["dropped"]).is_equal_to(7)
        assert_that(body).does_not_contain_key("deltas")

    def test_trace_json_without_changes_has_no_deltas(self):
        samples = [PollSample(elapsed=0.0, outcome="fail", value=1, detail="d", repeats=4)]
        trace = PollTrace(samples=samples, total_polls=4, dropped=0, elapsed=1.0, summary="s")
        assert_that(json.loads(_trace_to_json(trace))).does_not_contain_key("deltas")

    def test_trace_attached_to_allure(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).contains("Polling Trace")

    def test_trace_not_attached_when_off(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", trace=_make_trace())
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()


def _mock_allure():
    mock = MagicMock()
    mock.attachment_type.JSON = "json"
    return mock


def _run_hook_with_allure(report, call_obj, mock_allure, *, allure_mode="diff"):
    item = _make_item(allure_mode=allure_mode)
    with (
        patch("assertpy.pytest_plugin._HAS_ALLURE", True),
        patch("assertpy.pytest_plugin.allure", mock_allure, create=True),
    ):
        _run_hook(report, call_obj, item=item)


class TestAllureDiffMode:
    def test_no_actual_expected_in_diff_mode(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        mock.attach.assert_not_called()

    def test_diff_attached_in_diff_mode(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        assert_that(mock.attach.call_count).is_equal_to(1)
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("Structured Diff")
        assert_that(mock.attach.call_args_list[0].kwargs["attachment_type"]).is_equal_to("json")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["kind"]).is_equal_to("dict")
        assert_that(body["entries"][0]["path"]).is_equal_to("k")

    def test_diff_with_actual_expected_only_diff_attached(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        assert_that(mock.attach.call_count).is_equal_to(1)
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("Structured Diff")

    def test_empty_diff_entries_no_attachment(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        mock.attach.assert_not_called()

    def test_match_diff_from_real_failure_attaches_json(self):
        mock = _mock_allure()
        try:
            assert_that({"role": "superadmin"}).matches_structure(
                {"role": match.is_in("admin", "user"), "email": match.is_non_empty_string()}
            )
        except AssertionFailure as exc:
            _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock)
        else:
            raise AssertionError("expected AssertionFailure") from None
        assert_that(mock.attach.call_count).is_equal_to(1)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["kind"]).is_equal_to("match")
        actuals = {entry["path"]: entry["actual"] for entry in body["entries"]}
        assert_that(actuals).contains_key("role", "email")
        assert_that(actuals["role"]).is_equal_to("superadmin")
        assert_that(actuals["email"]).is_equal_to({"__repr__": "<missing>"})


class TestAllureFullMode:
    def test_actual_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        assert_that(mock.attach.call_count).is_equal_to(1)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 3, "actual": 1, "expected": 2})
        assert_that(mock.attach.call_args_list[0].kwargs["name"]).is_equal_to("AssertionFailure")
        assert_that(mock.attach.call_args_list[0].kwargs["attachment_type"]).is_equal_to("json")

    def test_only_actual_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=42)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 3, "actual": 42})

    def test_a_failure_that_names_no_value_still_attaches_what_was_asked(self):
        """`is_empty()` names neither side and builds no diff, which is the case the field exists for.

        The report path used to leave before attaching whenever nothing was named and no diff was built.
        """
        mock = _mock_allure()
        outcome = assert_that([1]).check().is_empty()
        exc = AssertionFailure(outcome.message, requirement=outcome.requirement)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to(
            {"format": 3, "requirement": {"operation": "is_empty", "parameters": {}, "negated": False}}
        )

    def test_only_expected_when_full(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", expected="abc")
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).is_equal_to({"format": 3, "expected": "abc"})

    def test_containers_attach_as_typed_json(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual={"a": 1}, expected=[1, 2])
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["actual"]).is_equal_to({"a": 1})
        assert_that(body["expected"]).is_equal_to([1, 2])

    def test_all_three_produces_two_attachments(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="full")
        assert_that(mock.attach.call_count).is_equal_to(2)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).contains("AssertionFailure")
        assert_that(names).contains("Structured Diff")

    def test_a_failure_with_no_diff_at_all_still_attaches_its_expected(self):
        """The case the sibling below does not reach: `contains_key` carries a diff, and a diff is its
        own reason to go on.  `is_true()` has neither a diff nor an actual of its own, so it is the one
        that says whether the early exit reads the record's flags or the terminal section's rule.
        """
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that(0).is_true()
        report = _make_report()
        _run_hook_with_allure(report, _make_call(exc=failure.value), mock, allure_mode="full")
        attached = {call.kwargs["name"]: call.kwargs["body"] for call in mock.attach.call_args_list}
        assert_that(json.loads(attached["AssertionFailure"])).is_equal_to(
            {"format": 3, "expected": True, "requirement": {"operation": "is_true", "parameters": {}, "negated": False}}
        )
        assert_that([title for title, _ in _sections(report)]).described_as(
            "the terminal stays quiet: the message already says what was expected"
        ).does_not_contain("AssertionFailure")

    def test_a_failure_that_named_only_an_expected_still_attaches_it(self):
        """Full mode is data, so the rule that keeps the terminal from repeating itself does not apply.

        The terminal section shows values the message did not, and every assertion names an expected
        now, so `expected` alone stopped meaning "the reader has not seen this".  A dashboard reading
        the attachment is in the other position: the message is prose to it, and the field is the value.
        """
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).contains_key("x")
        _run_hook_with_allure(_make_report(), _make_call(exc=failure.value), mock, allure_mode="full")
        attached = {call.kwargs["name"]: call.kwargs["body"] for call in mock.attach.call_args_list}
        assert_that(attached).contains_key("AssertionFailure", "Structured Diff")
        body = json.loads(attached["AssertionFailure"])
        assert_that(body).is_equal_to(
            {
                "format": 3,
                "expected": ["x"],
                "requirement": {"operation": "contains_key", "parameters": {"keys": ["x"]}, "negated": False},
            }
        )

    def test_an_expected_of_none_is_attached_rather_than_read_as_unset(self):
        mock = _mock_allure()
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).is_equal_to(None)
        _run_hook_with_allure(_make_report(), _make_call(exc=failure.value), mock, allure_mode="full")
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body).contains_key("expected")
        assert_that(body["expected"]).is_none()


class TestAllureOffMode:
    def test_no_attachments_when_off(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()

    def test_no_diff_attachment_when_off(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()

    def test_no_attachments_with_all_data_when_off(self):
        mock = _mock_allure()
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="x", actual=1, expected=2)])
        exc = AssertionFailure("fail", actual={"x": 1}, expected={"x": 2}, diff=diff)
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode="off")
        mock.attach.assert_not_called()


def _make_config(
    *,
    ini="diff",
    snapshot_update=False,
    poll_report="0.7",
    clusters="3",
    dangling="off",
    entries=(),
    profile="compatible",
    vacuous="off",
    comparison="on",
):
    config = MagicMock()
    # every key answered by name: a catch-all fed the allure mode to every other reader, and a guard was
    # handed `diff` for its own setting and refused it as a value it does not know
    per_key = {
        "assertpy_allure": ini,
        "assertpy_diff": "on",
        "assertpy_comparison": comparison,
        "assertpy_diff_max_entries": "50",
        "assertpy_poll_report": poll_report,
        "assertpy_failure_clusters": clusters,
        "assertpy_dangling": dangling,
        "assertpy_dangling_entries": entries,
        "assertpy_profile": profile,
        "assertpy_vacuous": vacuous,
    }
    per_key |= {_renamed.old_name(name): [] if name == "assertpy_dangling_entries" else "" for name in per_key}

    def answer(name):
        if name not in per_key:
            raise KeyError(f"{name} is read by the plugin and not answered by this fake config")
        return per_key[name]

    config.getini.side_effect = answer
    config.getoption.return_value = snapshot_update
    # the profile is cached here, and a mock answers an unset attribute with a mock, reading as a profile
    config._assertpy_profile = None
    return config


class TestPytestConfigure:
    def test_valid_mode_stored(self):
        config = _make_config(ini="full")
        pytest_configure(config)
        assert_that(config._assertpy_allure_mode).is_equal_to("full")

    def test_default_diff_mode_stored(self):
        config = _make_config(ini="diff")
        pytest_configure(config)
        assert_that(config._assertpy_allure_mode).is_equal_to("diff")

    def test_invalid_mode_warns_and_falls_back(self):
        config = _make_config(ini="unknown")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_configure(config)
        assert_that(config._assertpy_allure_mode).is_equal_to("diff")
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("unknown").contains("(diff, full, off)")

    def test_configure_disables_diff_in_message_and_unconfigure_restores(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", True)
        config = _make_config()
        pytest_configure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_false()
        pytest_unconfigure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_true()

    @pytest.mark.parametrize(("verbosity", "whole"), [(0, False), (1, False), (2, True), (3, True), (None, False)])
    def test_at_two_levels_of_verbosity_a_message_prints_its_values_whole(self, monkeypatch, verbosity, whole):
        monkeypatch.setattr(errors_module, "_WHOLE_VALUES", False)
        config = _make_config()
        config.getoption.side_effect = lambda name: verbosity if name == "verbose" else False
        pytest_configure(config)
        assert_that(errors_module._WHOLE_VALUES).is_equal_to(whole)
        pytest_unconfigure(config)
        assert_that(errors_module._WHOLE_VALUES).is_false()

    def test_unconfigure_puts_back_what_it_found_and_not_off(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_WHOLE_VALUES", True)
        config = _make_config()
        pytest_configure(config)
        assert_that(errors_module._WHOLE_VALUES).is_false()
        pytest_unconfigure(config)
        assert_that(errors_module._WHOLE_VALUES).is_true()

    def test_the_values_a_report_section_names_follow_the_same_switch(self, monkeypatch):
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": "x" * 3000}).is_equal_to({"a": "y" * 3000})
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        assert_that(dict(_sections(report))["AssertionFailure"]).contains("more chars)")
        monkeypatch.setattr(errors_module, "_WHOLE_VALUES", True)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure.value))
        body = dict(_sections(report))["AssertionFailure"]
        assert_that(body).is_equal_to(f"  actual:   {failure.value.actual!r}\n  expected: {failure.value.expected!r}")

    @pytest.mark.parametrize("option", [{"ignore": "page"}, {"include": "items"}], ids=["ignore=", "include="])
    def test_under_a_key_option_the_rows_are_the_two_views_that_were_compared(self, monkeypatch, option):
        # windowed over the whole values the rows parted at `page`, the key left out, and cut `Paris` away
        actual = {"page": 1, "items": [{"id": n, "name": f"user{n}", "city": "Oslo"} for n in range(40)]}
        expected = {"page": 2, "items": [dict(row) for row in actual["items"]]}
        expected["items"][17]["city"] = "Paris"
        failure = _failure_of(lambda: assert_that(actual).is_equal_to(expected, **option))
        assert_that(failure.actual).is_same_as(actual)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure))
        rows = dict(_sections(report))["AssertionFailure"].splitlines()
        assert_that(rows).is_length(2)
        assert_that(rows[0]).starts_with("  actual:   ...").contains("'city': 'Oslo'}, {'id': 18").does_not_contain(
            "page"
        )
        assert_that(rows[1]).starts_with("  expected: ...").contains("'city': 'Paris'}, {'id': 18").does_not_contain(
            "page"
        )
        monkeypatch.setattr(errors_module, "_WHOLE_VALUES", True)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to(
            f"  actual:   {failure._compared[0]!r}\n  expected: {failure._compared[1]!r}"
        )

    def test_a_record_under_a_key_option_is_a_row_of_the_fields_read_of_it(self):
        failure = _failure_of(
            lambda: assert_that(_Order(1, "Oslo", 5)).is_equal_to(_Order(1, "Paris", 9), ignore="seen_at")
        )
        report = _make_report()
        _run_hook(report, _make_call(exc=failure))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to(
            "  actual:   _Order(id=1, city='Oslo')\n  expected: _Order(id=1, city='Paris')"
        )

    def test_where_no_pair_was_kept_the_rows_are_the_values_named(self):
        actual, expected = {"page": 1, "price": 1.0}, {"page": 2, "price": 2.0}
        failure = _failure_of(lambda: assert_that(actual).is_equal_to(expected, ignore="page", tolerance=0.1))
        report = _make_report()
        _run_hook(report, _make_call(exc=failure))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to(
            f"  actual:   {actual!r}\n  expected: {expected!r}"
        )

    def test_each_failure_of_a_group_gets_the_rows_of_its_own_pair(self):
        one = _failure_of(lambda: assert_that({"a": 1, "at": 5}).is_equal_to({"a": 2, "at": 9}, ignore="at"))
        other = _failure_of(lambda: assert_that({"b": 1, "at": 5}).is_equal_to({"b": 2, "at": 9}, ignore="at"))
        report = _make_report()
        _run_hook(report, _make_call(exc=ExceptionGroup("teardown", [one, other])))
        sections = dict(_sections(report))
        assert_that(sections["AssertionFailure (1 of 2)"]).is_equal_to("  actual:   {'a': 1}\n  expected: {'a': 2}")
        assert_that(sections["AssertionFailure (2 of 2)"]).is_equal_to("  actual:   {'b': 1}\n  expected: {'b': 2}")

    def test_a_builder_used_again_gives_each_failure_the_rows_of_its_own_comparison(self):
        builder = assert_that({"page": 1, "city": "Oslo"})
        first = builder.check().is_equal_to({"page": 2, "city": "Paris"}, ignore="page")
        assert_that(first.passed).is_false()
        under_a_config = _failure_of(lambda: builder.is_equal_to({"page": 2, "city": "Rome"}, tolerance=0.1))
        another = _failure_of(lambda: builder.contains_key("zip"))
        plain = _failure_of(lambda: builder.is_equal_to({"page": 3, "city": "Bern"}))
        bodies = []
        for failure in (under_a_config, another, plain):
            report = _make_report()
            _run_hook(report, _make_call(exc=failure))
            bodies.append(dict(_sections(report)).get("AssertionFailure"))
        assert_that(bodies).is_equal_to(
            [
                "  actual:   {'page': 1, 'city': 'Oslo'}\n  expected: {'page': 2, 'city': 'Rome'}",
                None,
                "  actual:   {'page': 1, 'city': 'Oslo'}\n  expected: {'page': 3, 'city': 'Bern'}",
            ]
        )

    def test_a_failure_that_named_one_side_has_the_row_of_that_side(self):
        failure = AssertionFailure("built by hand", actual=1)
        failure._compared = (5, 6)
        report = _make_report()
        _run_hook(report, _make_call(exc=failure))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to("  actual:   1")

    def test_a_failure_that_cannot_be_asked_for_its_pair_keeps_the_rows_of_its_values(self):
        class GuardedError(AssertionFailure):
            @property
            def _compared(self):
                raise RuntimeError("no pair here")

            @_compared.setter
            def _compared(self, pair):
                pass

        report = _make_report()
        _run_hook(report, _make_call(exc=GuardedError("guarded", actual=1, expected=2)))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to("  actual:   1\n  expected: 2")

    def test_whole_a_side_named_alone_is_printed_alone_and_a_pair_that_reads_alike_is_told_apart(self, monkeypatch):
        text = "x" * 3000
        report = _make_report()
        _run_hook(report, _make_call(exc=AssertionFailure("fail", actual=text)))
        assert_that(dict(_sections(report))["AssertionFailure"]).ends_with("... (2602 more chars)")
        monkeypatch.setattr(errors_module, "_WHOLE_VALUES", True)
        for named, row in (({"actual": text}, f"  actual:   {text!r}"), ({"expected": text}, f"  expected: {text!r}")):
            report = _make_report()
            _run_hook(report, _make_call(exc=AssertionFailure("fail", **named)))
            assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to(row)
        report = _make_report()
        _run_hook(report, _make_call(exc=AssertionFailure("fail", actual=1, expected=_ReadsAsOne())))
        assert_that(dict(_sections(report))["AssertionFailure"]).is_equal_to(
            "  actual:   1:int\n  expected: 1:_ReadsAsOne"
        )


class _ReadsAsOne:
    def __repr__(self) -> str:
        return "1"


class TestSnapshotUpdateOption:
    def test_addoption_registers_flag(self):
        parser = MagicMock()
        pytest_addoption(parser)
        names = [call[0][0] for call in parser.addoption.call_args_list]
        assert_that(names).contains("--assertpy-snapshot-update")

    def test_the_boolean_flags_are_opt_in(self):
        parser = MagicMock()
        pytest_addoption(parser)
        registered = {call[0][0]: call[1] for call in parser.addoption.call_args_list}
        for name in (
            "--assertpy-snapshot-update",
            "--assertpy-vacuous",
            "--assertpy-snapshot-ci",
            "--assertpy-snapshot-no-ci",
        ):
            assert_that(registered).contains_key(name)
            assert_that(registered[name]).described_as(name).contains_entry(
                {"action": "store_true"}, {"default": False}
            )

    def test_flag_toggles_module_state_and_unconfigure_resets(self):
        config = _make_config(snapshot_update=True)
        try:
            pytest_configure(config)
            assert_that(snapshot_module._UPDATE_ALL).is_true()
        finally:
            pytest_unconfigure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()

    def test_without_flag_module_state_untouched(self):
        config = _make_config(snapshot_update=False)
        pytest_configure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()
        pytest_unconfigure(config)
        assert_that(snapshot_module._UPDATE_ALL).is_false()

    def test_ci_flag_sets_mode_true_and_unconfigure_resets(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", None)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy_snapshot_ci"
        pytest_configure(config)
        assert_that(snapshot_module._CI_MODE).is_true()
        pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()

    def test_no_ci_flag_sets_mode_false_and_unconfigure_resets(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", True)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy_snapshot_no_ci"
        pytest_configure(config)
        assert_that(snapshot_module._CI_MODE).is_false()
        pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()


def _controller_config(reporter, *, full=True):
    option = SimpleNamespace(keyword="" if full else "somekeyword", markexpr="", last_failed=False, failed_first=False)
    pluginmanager = SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None)
    return SimpleNamespace(option=option, pluginmanager=pluginmanager, rootpath=pathlib.Path.cwd())


class TestSnapshotOrphans:
    def test_worker_ships_touched_to_controller(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {("/x/snap-a.json", "10")})
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_touched"]).is_equal_to([["/x/snap-a.json", "10"]])

    def test_testnodedown_collects_worker_touches(self):
        pytest_plugin._controller_touched.clear()
        node = SimpleNamespace(workeroutput={"assertpy_touched": [["/x/snap-a.json", "10"]]})
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._controller_touched).contains(("/x/snap-a.json", "10"))
        pytest_plugin._controller_touched.clear()

    def test_testnodedown_collects_worker_failures(self):
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0
        node = SimpleNamespace(
            gateway=SimpleNamespace(id="gw3"),
            workeroutput={
                "assertpy_failures": [
                    [
                        "t.py::test_x",
                        [[True, "user.role", [["key", "'user'"], ["key", "'role'"]], "", [], "'s'", "'a'"]],
                    ]
                ],
                "assertpy_failure_count": 7,
            },
        )
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._controller_failures).is_length(1)
        assert_that(pytest_plugin._controller_failure_count[0]).is_equal_to(7)
        nodeid, found = pytest_plugin._controller_failures[0]
        assert_that(nodeid).is_equal_to("gw3::t.py::test_x")
        assert_that(found[0].signature.where).is_equal_to("user.role")
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0

    def test_sessionfinish_ships_the_failures_a_worker_recorded(self):
        config = SimpleNamespace(
            workeroutput={},
            _assertpy_failures=[("t.py::test_x", [Observation(Signature(True, "a.b", (("key", "'a'"),)), "1", "2")])],
            _assertpy_failure_count=4,
        )
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_failure_count"]).is_equal_to(4)
        assert_that(config.workeroutput["assertpy_failures"][0][0]).is_equal_to("t.py::test_x")

    def test_testnodedown_ignores_node_without_touches(self):
        pytest_plugin._controller_touched.clear()
        pytest_testnodedown(SimpleNamespace(workeroutput={}), None)
        assert_that(pytest_plugin._controller_touched).is_empty()

    def test_the_prune_locks_the_file_it_rewrites(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        locked = []
        real_lock = snapshot_module._file_lock
        monkeypatch.setattr(
            snapshot_module, "_file_lock", lambda target, **kw: locked.append(target) or real_lock(target, **kw)
        )
        snapshot_module._prune_sub_key_orphans([(snapname, "30")])
        assert_that(locked).is_equal_to([snapname])

    def test_is_full_run_variants(self):
        def config(**opt):
            base = {"keyword": "", "markexpr": "", "last_failed": False, "failed_first": False, "file_or_dir": []}
            return SimpleNamespace(option=SimpleNamespace(**{**base, **opt}))

        assert_that(_is_full_run(config())).is_true()
        assert_that(_is_full_run(config(keyword="k"))).is_false()
        assert_that(_is_full_run(config(markexpr="m"))).is_false()
        assert_that(_is_full_run(config(last_failed=True))).is_false()
        assert_that(_is_full_run(config(failed_first=True))).is_false()
        assert_that(_is_full_run(config(file_or_dir=["tests/test_x.py::test_a"]))).is_false()
        assert_that(_is_full_run(config(file_or_dir=["tests/test_x.py"]))).is_true()

    def test_sessionfinish_no_touches_is_quiet(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_TOUCHED", set())
        pytest_plugin._controller_touched.clear()
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        reporter.write_line.assert_not_called()

    def test_sessionfinish_no_orphans_is_quiet(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        reporter.write_line.assert_not_called()

    def test_reports_sub_key_orphan_without_pruning(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", False)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE", raising=False)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("::30").contains("full run to remove")
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

    def test_prunes_sub_key_under_update_full_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=True)), 0)
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("removed")
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).does_not_contain_key("30")

    def test_no_prune_on_filtered_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=False)), 0)
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

    def test_no_prune_on_nodeid_selected_run(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        option = SimpleNamespace(
            keyword="", markexpr="", last_failed=False, failed_first=False, file_or_dir=["tests/test_mod.py::test_a"]
        )
        pluginmanager = SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None)
        config = SimpleNamespace(option=option, pluginmanager=pluginmanager, rootpath=pathlib.Path.cwd())
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(json.loads((tmp_path / "snap-mod.json").read_text())).contains_key("30")

    def test_whole_file_orphan_is_report_only_even_under_update(self, tmp_path, monkeypatch):
        live = str(tmp_path / "snap-live.json")
        dead = str(tmp_path / "snap-dead.json")
        for target in (live, dead):
            with open(target, "w", encoding="utf-8") as handle:
                json.dump({"10": 1}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(live, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", True)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter, full=True)), 0)
        assert_that(os.path.isfile(dead)).is_true()
        text = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(text).contains("obsolete snapshot file")


class TestTheDiffTravelsWithTheFailure:
    """What a reader other than the terminal sees, read out of real runs.

    Every earlier check of this plugin read terminal text, and the diff lived on the channel for
    captured output: PyCharm's runner, a JUnit body, a failing fixture and `--show-capture=no` all got
    the message with nothing under it, and a CI log got raw escape codes.  Each case here is one of those.
    """

    _SUITE = (
        "import sys\n\n"
        "import pytest\n"
        "from assertpy import assert_that\n\n"
        "if sys.version_info < (3, 11):\n"
        "    from exceptiongroup import ExceptionGroup\n\n\n"
        "@pytest.fixture\n"
        "def broken_setup():\n"
        "    assert_that({'k': 0}).is_equal_to({'k': 1})\n\n\n"
        "@pytest.fixture\n"
        "def broken_teardown():\n"
        "    yield\n"
        "    assert_that({'k': 0}).is_equal_to({'k': 1})\n\n\n"
        "@pytest.fixture\n"
        "def second_broken_teardown():\n"
        "    yield\n"
        "    assert_that({'k': 2}).is_equal_to({'k': 3})\n\n\n"
        "def test_in_call():\n"
        "    assert_that({'k': 0}).is_equal_to({'k': 1})\n\n\n"
        "def test_in_setup(broken_setup):\n"
        "    pass\n\n\n"
        "def test_in_teardown(broken_teardown):\n"
        "    pass\n\n\n"
        "def test_in_two_teardowns(broken_teardown, second_broken_teardown):\n"
        "    pass\n\n\n"
        "def test_in_a_group():\n"
        "    try:\n"
        "        assert_that({'k': 4}).is_equal_to({'k': 5})\n"
        "    except AssertionError as failure:\n"
        "        raise ExceptionGroup('tasks', [ValueError('not ours'), failure]) from None\n"
    )

    _DUMP = (
        "import pytest\n\n"
        "import assertpy.pytest_plugin\n\n"
        "with open('plugin.txt', 'w', encoding='utf-8') as sink:\n"
        "    sink.write(assertpy.pytest_plugin.__file__)\n\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_runtest_logreport(report):\n"
        "    if report.failed:\n"
        "        with open('longreprtext.txt', 'a', encoding='utf-8') as sink:\n"
        "            sink.write(report.longreprtext + '\\n=====\\n')\n\n\n"
        "def pytest_terminal_summary(terminalreporter):\n"
        "    reports = terminalreporter.stats.get('failed', []) + terminalreporter.stats.get('error', [])\n"
        "    with open('summary.txt', 'w', encoding='utf-8') as sink:\n"
        "        for report in reports:\n"
        "            sink.write(str(report.longrepr))\n"
        "            sink.write(''.join(content for _, content, _ in getattr(report.longrepr, 'sections', [])))\n"
    )

    _AS_TEXT = (
        "\n\n@pytest.hookimpl(hookwrapper=True, trylast=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    report = outcome.get_result()\n"
        "    if report.failed:\n"
        "        report.longrepr = 'rendered as text'\n"
    )

    def _run(self, tmp_path, *arguments, conftest=""):
        (tmp_path / "test_travel.py").write_text(self._SUITE, encoding="utf-8")
        (tmp_path / "conftest.py").write_text(self._DUMP + conftest, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [
                *(sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-p", "no:randomly"),
                *("--junitxml", "junit.xml", *arguments),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHONPATH": _CHECKOUT},
        )
        assert_that(result.returncode).described_as(f"the child run: {result.stdout}{result.stderr}").is_equal_to(1)
        imported = pathlib.Path((tmp_path / "plugin.txt").read_text(encoding="utf-8")).resolve()
        assert_that(imported).described_as("the plugin the child ran").is_equal_to(
            pathlib.Path(pytest_plugin.__file__).resolve()
        )
        return result

    def test_a_failure_rendered_as_text_carries_it_too(self, tmp_path):
        """A custom item's `repr_failure` returns a string, which JUnit writes out as it is."""
        self._run(tmp_path, conftest=self._AS_TEXT)
        bodies = self._junit_bodies(tmp_path)
        assert_that(bodies).is_length(5).all_satisfy(match.contains("rendered as text", "diff (dict)"))

    @staticmethod
    def _junit_bodies(tmp_path):
        root = ET.parse(tmp_path / "junit.xml").getroot()
        return [one.text or "" for one in root.iter() if one.tag in {"failure", "error"}]

    def test_a_junit_body_carries_the_diff_for_every_phase(self, tmp_path):
        self._run(tmp_path)
        bodies = self._junit_bodies(tmp_path)
        assert_that(bodies).is_length(5)
        assert_that(bodies).described_as("JUnit bodies without the diff").all_satisfy(match.contains("diff (dict)"))

    def test_the_text_any_ide_runner_reads_carries_the_diff(self, tmp_path):
        """`longreprtext` is what a runner reading the failure renders; PyCharm's is one of those."""
        self._run(tmp_path)
        dumped = (tmp_path / "longreprtext.txt").read_text(encoding="utf-8").split("=====")[:-1]
        assert_that(dumped).is_length(5).all_satisfy(match.contains("diff (dict)"))

    def test_each_failure_of_a_group_gets_its_own_numbered_diff(self, tmp_path):
        self._run(tmp_path)
        bodies = self._junit_bodies(tmp_path)
        assert_that(bodies).any_satisfy(match.contains("Structured Diff (1 of 2)", "Structured Diff (2 of 2)"))
        assert_that(bodies).any_satisfy(
            match.all_of(match.contains("Structured Diff (2 of 2)"), match.not_(match.contains("(1 of 2)")))
        )

    def test_a_log_with_no_terminal_behind_it_gets_no_escape_codes(self, tmp_path):
        result = self._run(tmp_path)
        assert_that(result.stdout).contains("Structured Diff").does_not_contain("\x1b[")

    @pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["in-process", "distributed"])
    def test_forced_colour_reaches_the_terminal_and_no_other_reader(self, tmp_path, workers):
        if workers:
            pytest.importorskip("xdist", reason="the integration cell installs xdist and this one may not")
        result = self._run(tmp_path, "--color=yes", *workers)
        assert_that(result.stdout.count("\x1b[36mdiff (dict):")).described_as("coloured diffs").is_equal_to(6)
        readers = [
            *self._junit_bodies(tmp_path),
            (tmp_path / "longreprtext.txt").read_text(encoding="utf-8"),
            (tmp_path / "summary.txt").read_text(encoding="utf-8"),
        ]
        assert_that(readers).all_satisfy(
            match.all_of(
                match.contains("diff (dict)"), match.not_(match.contains("#x1B")), match.not_(match.contains("\x1b"))
            )
        )

    def test_hiding_captured_output_does_not_hide_the_diff(self, tmp_path):
        result = self._run(tmp_path, "--show-capture=no")
        assert_that(result.stdout.count("Structured Diff")).is_equal_to(6)

    def test_no_traceback_on_the_terminal_still_leaves_it_in_junit(self, tmp_path):
        self._run(tmp_path, "--tb=no")
        assert_that(self._junit_bodies(tmp_path)).all_satisfy(match.contains("diff (dict)"))

    def test_a_distributed_run_carries_it_to_the_controller(self, tmp_path):
        pytest.importorskip("xdist", reason="the integration cell installs xdist and this one may not")
        self._run(tmp_path, "-n", "2")
        bodies = self._junit_bodies(tmp_path)
        assert_that(bodies).is_length(5).all_satisfy(match.contains("diff (dict)"))


class TestASoftBlocksSectionsReachEveryReader:
    """The sections of a soft block's failures, read out of real runs: the terminal in colour, JUnit in plain text."""

    _SUITE = (
        "from assertpy import assert_that, soft_assertions\n\n\n"
        "def test_block():\n"
        "    with soft_assertions():\n"
        "        assert_that({'k': 0}).is_equal_to({'k': 1})\n"
        "        assert_that({'k': 2}).is_equal_to({'k': 3})\n"
    )

    def _run(self, tmp_path, *arguments):
        (tmp_path / "test_block.py").write_text(self._SUITE, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = subprocess.run(
            [
                *(sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-p", "no:randomly"),
                *("--junitxml", "junit.xml", *arguments),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHONPATH": _CHECKOUT},
        )
        assert_that(result.returncode).described_as(f"the child run: {result.stdout}{result.stderr}").is_equal_to(1)
        root = ET.parse(tmp_path / "junit.xml").getroot()
        return result, [one.text or "" for one in root.iter() if one.tag == "failure"]

    @pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["in-process", "distributed"])
    def test_the_terminal_gets_each_diff_in_colour_and_junit_in_plain_text(self, tmp_path, workers):
        if workers:
            pytest.importorskip("xdist", reason="the integration cell installs xdist and this one may not")
        result, bodies = self._run(tmp_path, "--color=yes", *workers)
        assert_that(result.stdout.count("\x1b[36mdiff (dict):")).described_as("coloured diffs").is_equal_to(2)
        assert_that(bodies).is_length(1)
        assert_that(bodies[0]).contains(
            "Structured Diff (failure 1 of 2)", "Structured Diff (failure 2 of 2)", "1. Expected <{'k': 0}>"
        ).does_not_contain("\x1b")


class TestAllureExceptionSafety:
    def test_allure_attach_failure_does_not_break_report(self):
        mock = _mock_allure()
        mock.attach.side_effect = RuntimeError("allure broken")
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual=1, expected=2)])
        exc = AssertionFailure("fail", diff=diff)
        report = _make_report()
        _run_hook_with_allure(report, _make_call(exc=exc), mock)
        assert_that(_sections(report)).is_length(1)
        assert_that(_sections(report)[0][0]).is_equal_to("Structured Diff")


class TestAllureNotAvailable:
    def test_no_attach_when_allure_missing(self):
        mock = _mock_allure()
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        with (
            patch("assertpy.pytest_plugin._HAS_ALLURE", False),
            patch("assertpy.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(report, _make_call(exc=exc))
        mock.attach.assert_not_called()

    def test_sections_still_added_without_allure(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(_sections(report)).is_length(1)
        assert_that(_sections(report)[0][0]).is_equal_to("AssertionFailure")


class TestNearTimeoutReport:
    """Retrying is what eventually() is for, so only a poll that burned its budget is worth naming."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        pytest_plugin._retried.clear()
        yield
        pytest_plugin._retried.clear()

    @staticmethod
    def _lines(rows):
        pytest_plugin._retried.extend(rows)
        reporter = MagicMock()
        config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter))
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_a_poll_against_the_deadline_is_named(self):
        lines = self._lines([("t.py::test_x", 41, 0.81, 1.0)])
        assert_that("\n".join(lines)).contains("t.py::test_x").contains("81% of the budget")

    def test_a_healthy_retry_is_not_named(self):
        assert_that(self._lines([("t.py::test_x", 3, 0.04, 2.0)])).is_empty()

    def test_nothing_collected_stays_quiet(self):
        assert_that(self._lines([])).is_empty()

    def test_a_zero_budget_is_not_divided_by(self):
        assert_that(self._lines([("t.py::test_x", 2, 0.0, 0.0)])).is_empty()

    def test_draining_tags_each_poll_with_its_test(self):
        async_assertions._RETRIES.append((41, 0.81, 1.0))
        pytest_plugin._drain_retries("t.py::test_x")
        assert_that(pytest_plugin._retried).is_equal_to([("t.py::test_x", 41, 0.81, 1.0)])
        assert_that(async_assertions._RETRIES).is_empty()

    def test_a_teardown_phase_retry_keeps_its_own_test(self):
        async_assertions._RETRIES.append((41, 0.81, 1.0))
        report = _make_report(when="teardown", failed=False)
        report.nodeid = "t.py::test_owner"
        _run_hook(report, _make_call())
        assert_that([row[0] for row in pytest_plugin._retried]).is_equal_to(["t.py::test_owner"])
        assert_that(async_assertions._RETRIES).is_empty()

    def test_worker_ships_retries_to_controller(self):
        pytest_plugin._retried.append(("t.py::test_x", 41, 0.81, 1.0))
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_retried"]).is_equal_to([["t.py::test_x", 41, 0.81, 1.0]])

    def test_testnodedown_collects_worker_retries(self):
        node = SimpleNamespace(workeroutput={"assertpy_retried": [["t.py::test_x", 41, 0.81, 1.0]]})
        pytest_testnodedown(node, None)
        assert_that(pytest_plugin._retried).contains(("t.py::test_x", 41, 0.81, 1.0))


class TestPollReportIni:
    """The report prints on its own; without a bar to move or an off switch it cannot be lived with."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        pytest_plugin._retried.clear()
        yield
        pytest_plugin._retried.clear()

    @staticmethod
    def _lines(rows, threshold):
        pytest_plugin._retried.extend(rows)
        reporter = MagicMock()
        config = SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter),
            _assertpy_poll_threshold=threshold,
        )
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_addini_registers_the_key(self):
        parser = MagicMock()
        pytest_addoption(parser)
        assert_that([call[0][0] for call in parser.addini.call_args_list]).contains("assertpy_poll_report")

    def test_off_silences_the_report(self):
        assert_that(self._lines([("t.py::test_x", 41, 0.81, 1.0)], None)).is_empty()

    def test_off_also_stops_collecting(self):
        config = _make_config(poll_report="off")
        try:
            pytest_configure(config)
            assert_that(config._assertpy_poll_threshold).is_none()
            assert_that(async_assertions._COLLECT_RETRIES).is_false()
        finally:
            pytest_unconfigure(config)

    def test_a_lower_bar_names_a_poll_the_default_would_not(self):
        rows = [("t.py::test_x", 5, 0.4, 1.0)]
        assert_that(self._lines(rows, 0.7)).is_empty()
        pytest_plugin._retried.clear()
        assert_that("\n".join(self._lines(rows, 0.3))).contains("t.py::test_x")

    def test_a_fraction_is_parsed_from_the_ini(self):
        config = _make_config(poll_report="0.95")
        try:
            pytest_configure(config)
            assert_that(config._assertpy_poll_threshold).is_equal_to(0.95)
            assert_that(async_assertions._COLLECT_RETRIES).is_true()
        finally:
            pytest_unconfigure(config)

    @pytest.mark.parametrize("raw", ["loud", "0", "-0.5", "1.5"])
    def test_an_unusable_value_warns_and_falls_back(self, raw):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            threshold = pytest_plugin._poll_threshold(raw)
        assert_that(threshold).is_equal_to(0.7)
        assert_that(str(caught[0].message)).contains("falling back to 0.7")


class TestVacuityGuardSwitch:
    """The environment is read once, so the plugin must not leave the module flag where it found it."""

    def test_env_switch_reads_truthy_spellings(self, monkeypatch):
        for raw in ("1", "true", "YES", " on "):
            monkeypatch.setenv("ASSERTPY_VACUOUS", raw)
            assert_that(_satisfies_module._env_enabled()).described_as(raw).is_true()

    def test_env_switch_rejects_anything_else(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY_VACUOUS", "maybe")
        assert_that(_satisfies_module._env_enabled()).is_false()
        monkeypatch.delenv("ASSERTPY_VACUOUS")
        assert_that(_satisfies_module._env_enabled()).is_false()

    def test_flag_sets_the_guard_and_unconfigure_restores_it(self, monkeypatch):
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", False)
        config = _make_config()
        config.getoption.side_effect = lambda name: name == "assertpy_vacuous"
        pytest_configure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()
        pytest_unconfigure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_false()

    def test_unconfigure_keeps_a_guard_the_environment_turned_on(self, monkeypatch):
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", True)
        config = _make_config()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()

    def test_unconfigure_without_configure_falls_back_to_the_environment(self, monkeypatch):
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", True)
        monkeypatch.delenv("ASSERTPY_VACUOUS", raising=False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(_satisfies_module._VACUOUS_GUARD).is_false()


@pytest.fixture
def _clean_registries(monkeypatch):
    """The snapshot access registries are module-level, so a test that fills them has to empty them."""
    monkeypatch.setattr(snapshot_module, "_ACCESS_NODES", {})
    monkeypatch.setattr(snapshot_module, "_ACCESS_SITES", {})
    monkeypatch.setattr(snapshot_module, "_WARNED", set())
    monkeypatch.setattr(snapshot_module, "_TOUCHED", set())
    monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_a")
    pytest_plugin._controller_accesses.clear()
    yield
    pytest_plugin._controller_accesses.clear()


@pytest.mark.usefixtures("_clean_registries")
class TestSnapshotKeyReuseWarning:
    """One key reached by two tests means only the first one's value was ever asserted."""

    def test_runtest_setup_names_the_running_test(self, monkeypatch):
        pytest_runtest_setup(SimpleNamespace(nodeid="test_mod.py::test_z"))
        assert_that(snapshot_module._CURRENT_NODE).is_equal_to("test_mod.py::test_z")

    def test_a_second_test_on_one_key_warns_where_it_happened(self, monkeypatch):
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_length(1)
        assert_that(caught[0].category).is_equal_to(snapshot_module.SnapshotKeyReusedWarning)
        assert_that(str(caught[0].message)).contains("test_mod.py:17").contains("reached by more than one test")
        assert_that(str(caught[0].message)).does_not_contain("shared by")
        assert_that(str(caught[0].message)).contains("snapshot(id=...)")

    def test_the_warning_points_at_the_line_that_reused_the_key(self, monkeypatch, tmp_path):
        # `catch_warnings` records the message, not where pytest attributes it, so the stack level could drift
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that({"u": 1}).snapshot(id="shared", path=str(tmp_path))
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            assert_that({"u": 1}).snapshot(id="shared", path=str(tmp_path))
        reuse = [w for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reuse).is_length(1)
        assert_that(reuse[0].filename).is_equal_to(__file__)

    def test_one_test_reaching_a_key_twice_is_left_alone(self):
        # the legitimate case: a helper that snapshots twice inside one test asserts both values
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(4):
                snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_empty()
        assert_that(snapshot_module._ACCESS_NODES["/x/snap.json", "17"]).is_length(1)

    def test_a_third_test_does_not_warn_again(self, monkeypatch):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for node in ("test_a", "test_b", "test_c"):
                monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", node)
                snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_length(1)

    def test_off_pytest_nothing_is_recorded(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
            snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        assert_that(caught).is_empty()
        assert_that(snapshot_module._ACCESS_NODES).is_empty()
        assert_that(snapshot_module._TOUCHED).contains(("/x/snap.json", "17"))

    def test_a_custom_id_reads_as_a_whole_file(self, monkeypatch):
        snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            monkeypatch.setattr(snapshot_module, "_CURRENT_NODE", "test_mod.py::test_b")
            snapshot_module._record_access("/x/snap.json", "", "id='payload'")
        assert_that(str(caught[0].message)).contains("<whole file>").contains("id='payload'")

    def test_worker_ships_node_ids_and_the_controller_unions_them(self):
        config = SimpleNamespace(workeroutput={})
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_accesses"]).is_equal_to(
            [["/x/snap.json", "17", ["test_mod.py::test_a"], "test_mod.py:17"]]
        )
        for node in ("test_mod.py::test_a", "test_mod.py::test_b"):
            pytest_testnodedown(
                SimpleNamespace(workeroutput={"assertpy_accesses": [["/x/s.json", "9", [node], "s:9"]]}), None
            )
        assert_that(pytest_plugin._controller_accesses["/x/s.json", "9"]).is_length(2)

    def test_the_sweep_reports_what_no_worker_could_see(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        snapshot_module._ACCESS_SITES["/x/s.json", "9"] = "test_mod.py:9"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("shared by 2 tests").does_not_contain("at least")

    def test_the_sweep_counts_a_key_a_test_already_reported(self):
        snapshot_module._WARNED.add(("/x/s.json", "9"))
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b", "test_c"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("shared by 3 tests")

    def test_a_key_reached_once_does_not_stop_the_sweep(self):
        pytest_plugin._controller_accesses[("/x/a.json", "1")] = {"test_a"}
        pytest_plugin._controller_accesses[("/x/b.json", "9")] = {"test_a", "test_b"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        reported = [str(w.message) for w in caught if w.category is snapshot_module.SnapshotKeyReusedWarning]
        assert_that(reported).is_length(1)
        assert_that(reported[0]).contains("/x/b.json")

    def test_an_escalated_sweep_warning_fails_the_run_rather_than_the_hook(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.TESTS_FAILED)
        printed = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(printed).contains("shared by 2 tests")

    def test_a_run_that_died_for_another_reason_keeps_its_own_exit_status(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=pytest.ExitCode.INTERRUPTED)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.INTERRUPTED)
        printed = " ".join(str(call) for call in reporter.write_line.call_args_list)
        assert_that(printed).contains("shared by 2 tests")

    def test_the_registries_are_drained(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a"}
        snapshot_module._record_access("/x/snap.json", "17", "test_mod.py:17")
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        assert_that(snapshot_module._ACCESS_NODES).is_empty()
        assert_that(snapshot_module._ACCESS_SITES).is_empty()
        assert_that(pytest_plugin._controller_accesses).is_empty()


_SHARED_KEY_MODULE = """\
import pathlib

import pytest
from assertpy import assert_that

SNAPS = pathlib.Path(__file__).parent / "snaps"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("alice", marks=pytest.mark.xdist_group("g1")),
        pytest.param("bob", marks=pytest.mark.xdist_group("g2")),
        pytest.param("carol", marks=pytest.mark.xdist_group("g3")),
    ],
)
def test_case(name):
    SNAPS.mkdir(exist_ok=True)
    assert_that({{"user": name}}).matches_contract_snapshot(id={id}, path=str(SNAPS))
"""


class TestSnapshotKeyReuseUnderXdist:
    """The reuse gate across real worker processes, rather than at the seam.

    Every other test here drives the hooks directly with a fake node, which pins the logic but takes
    the plumbing on trust: the ``workeroutput`` key names matching on both sides, the payload
    surviving xdist's serialisation, the controller sweep running late enough to have every worker's
    numbers and early enough for pytest to still collect the warning.  None of that is reachable
    without spawning workers, and all of it is what silently stops a cross-process guarantee from
    ever firing again.

    Three cases in three ``xdist_group``s over three workers puts exactly one case on each, so no
    worker sees a second reach and the warning can only come from the union on the controller.  That
    split is guaranteed rather than lucky: with as many groups as workers, xdist's scheduler hands out
    one work unit per node and the queue is empty afterwards.

    Deliberately not guarded by a skip on pytest-xdist being importable.  It is a dev dependency like
    hypothesis, and a guard here would turn "the dependency went missing" into a silently skipped
    check, which is the same blindness this class exists to remove.
    """

    def _run(self, tmp_path, snapshot_id, *extra):
        (tmp_path / "test_reuse.py").write_text(_SHARED_KEY_MODULE.format(id=snapshot_id), encoding="utf-8")
        try:
            return self._spawn(tmp_path, extra)
        except subprocess.TimeoutExpired as expired:
            raise AssertionError(
                f"the child run did not finish in {expired.timeout}s\n"
                f"stdout:\n{expired.stdout}\nstderr:\n{expired.stderr}"
            ) from expired

    def _spawn(self, tmp_path, extra):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(tmp_path / "test_reuse.py"),
                "-q",
                "--no-header",
                "--rootdir",
                str(tmp_path),
                "--confcutdir",
                str(tmp_path),
                "--assertpy-snapshot-no-ci",
                "-n",
                "3",
                "--dist",
                "loadgroup",
                "-p",
                "no:cacheprovider",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

    @staticmethod
    def _report(result):
        """The child's stdout, with everything a failure here needs to be explainable attached.

        These checks read stdout and nothing else, so a child that failed to start, lost a worker or
        rebuilt its environment showed up only as text that did not match. The reason was in the
        captured stderr, which no assertion ever surfaced.
        """
        context = f"exit {result.returncode}, child stderr:\n{result.stderr.strip() or '<empty>'}\n"
        return assert_that(result.stdout).described_as(context)

    def test_one_key_split_across_workers_still_warns(self, tmp_path):
        report = self._report(self._run(tmp_path, '"one-key"'))
        report.contains("3 passed")
        report.contains("SnapshotKeyReusedWarning").contains("shared by 3 tests")
        report.contains("pytest_plugin.py")

    def test_a_key_per_case_stays_silent(self, tmp_path):
        report = self._report(self._run(tmp_path, 'f"key-{name}"'))
        report.contains("3 passed")
        report.does_not_contain("SnapshotKeyReusedWarning")

    def test_the_filters_turning_it_into_an_error_fail_the_run_not_the_hook(self, tmp_path):
        result = self._run(tmp_path, '"one-key"', "-W", "error::assertpy.SnapshotKeyReusedWarning")
        report = self._report(result)
        report.does_not_contain("INTERNALERROR")
        report.contains("ERROR: snapshot key").contains("shared by 3 tests")
        report.contains("3 passed")
        assert_that(result.returncode).described_as(f"child stderr:\n{result.stderr}").is_equal_to(1)


def _registered_parser():
    """The plugin's options on the parser pytest itself hands to `pytest_addoption`.

    A `MagicMock` records any call at all, so it cannot tell a registration pytest accepts from one it
    refuses: an unknown action, an ini type outside the supported set, a missing help.
    """
    parser = Parser(_ispytest=True)
    pytest_addoption(parser)
    return parser


def _addoption_calls():
    """The switches as they were registered, which is where the action and the default are visible."""
    parser = MagicMock()
    pytest_addoption(parser)
    return parser.addoption.call_args_list


class _RegisteredConfig:
    """A config that answers only the keys the plugin registered, refusing others as pytest does."""

    def __init__(self, *, ini=None, options=None):
        parser = _registered_parser()
        self._ini = {name: spec[-1] for name, spec in parser._inidict.items()} | dict(ini or {})
        # `verbose` is pytest's own, the one option the plugin reads that it did not register
        self._options = {"verbose": 0} | vars(parser.parse([])) | dict(options or {})

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(f"unknown configuration value: {name!r}")
        return self._ini[name]

    def getoption(self, name):
        if name not in self._options:
            raise ValueError(f"no option named {name!r}")
        return self._options[name]


def _configured_item(**settings):
    """An item whose config carries exactly the attributes named, as a real config would."""
    return SimpleNamespace(config=SimpleNamespace(**settings))


def _diff_of(count):
    entries = [DiffEntry(path=f"k{index}", actual=index, expected=index + 1) for index in range(count)]
    return DiffResult(kind="dict", entries=entries)


def _one_sample_trace(**sample):
    base = {"elapsed": 0.0, "outcome": "fail", "value": 1, "detail": "d"}
    return PollTrace(samples=[PollSample(**(base | sample))], total_polls=1, dropped=0, elapsed=0.5, summary="s")


class TestTheOptionsRegisterWithPytestItself:
    """Every switch and ini key has to survive the parser pytest builds, not only a recording mock."""

    def test_the_switches_are_flags_the_parser_accepts_bare(self):
        options = _registered_parser().parse(["--assertpy-dangling", "--assertpy-snapshot-update"])
        assert_that(options.assertpy_dangling).is_true()
        assert_that(options.assertpy_snapshot_update).is_true()

    def test_every_switch_and_key_documents_itself(self):
        parser = _registered_parser()
        documented = [(option.names()[0], option.attrs().get("help")) for option in parser._anonymous.options]
        documented += [(name, spec[0]) for name, spec in parser._inidict.items()]
        assert_that([name for name, help_text in documented if not help_text]).is_empty()

    def test_the_wrapper_names_key_is_shell_split_rather_than_one_string(self):
        assert_that(_registered_parser()._inidict["assertpy_dangling_entries"][1]).is_equal_to("args")

    def test_the_dangling_switch_is_opt_in_like_the_others(self):
        registered = {call[0][0]: call[1] for call in _addoption_calls()}
        assert_that(registered).contains_key("--assertpy-dangling")
        assert_that(registered["--assertpy-dangling"]).contains_entry({"action": "store_true"}, {"default": False})


class TestTheSettingsAProjectGets:
    """What `pytest_configure` reads, against a config that refuses a key it never registered."""

    def test_a_project_that_configures_nothing_gets_the_documented_defaults(self):
        config = _RegisteredConfig()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            assert_that(config._assertpy_allure_mode).is_equal_to("diff")
            assert_that(config._assertpy_dangling_enabled).is_equal_to(False)
            assert_that(config._assertpy_dangling_entries).is_equal_to(frozenset())
            assert_that(config._assertpy_diff_enabled).is_equal_to(True)
            assert_that(config._assertpy_diff_max).is_equal_to(50)
            assert_that(config._assertpy_cluster_minimum).described_as(
                "clustering is the one report a project gets without configuring it"
            ).is_equal_to(_clustering.MINIMUM_SIZE)
            assert_that(config._assertpy_poll_threshold).is_equal_to(0.7)
        finally:
            pytest_unconfigure(config)

    def test_a_blank_value_for_any_setting_leaves_the_run_alone(self):
        """An ini line written and left empty has to resolve to the default, in silence.

        A warning raised while resolving settings comes out of `pytest_configure`, and under `-W error`
        that is an INTERNALERROR rather than a message, since pytest is inside its own hook with nothing
        to attribute the failure to.  Three settings were found doing it: the poll report and the Allure
        mode took the run down that way, and failure clustering joined them the moment it stopped being
        answered by a profile.

        Written against every string setting rather than those three, because the one to get this wrong
        next is the one nobody thought to check.  It compares the whole resolved state rather than the
        silence, so a setting that stops warning and lands on the wrong value fails here too.
        """
        registered = _registered_parser()._inidict
        blank = {name: "" for name, spec in registered.items() if isinstance(spec[-1], str)}
        assert_that(blank).described_as("the settings an empty ini line can reach").is_not_empty()
        assert_that(self._resolved(blank)).described_as(
            "what a blank ini line resolved to, against what writing nothing resolves to"
        ).is_equal_to(self._resolved({}))

    @staticmethod
    def _resolved(ini):
        """Everything `pytest_configure` settled, from a config that carries these ini values.

        Configured and unconfigured inside the call rather than two at a time: the hooks save and
        restore module state, and a second config configured over the first would restore what the
        first had already changed.
        """
        config = _RegisteredConfig(ini=ini)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            return {name: value for name, value in vars(config).items() if name.startswith("_assertpy_")}
        finally:
            pytest_unconfigure(config)

    def test_every_key_reaches_the_setting_it_names(self):
        config = _RegisteredConfig(
            ini={
                "assertpy_allure": "full",
                "assertpy_dangling": "on",
                "assertpy_dangling_entries": ["check_that"],
                "assertpy_diff": "off",
                "assertpy_diff_max_entries": "5",
                "assertpy_failure_clusters": "4",
                "assertpy_poll_report": "0.9",
            }
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_configure(config)
        try:
            assert_that(config._assertpy_allure_mode).is_equal_to("full")
            assert_that(config._assertpy_dangling_enabled).is_equal_to(True)
            assert_that(config._assertpy_dangling_entries).is_equal_to(frozenset({"check_that"}))
            assert_that(config._assertpy_diff_enabled).is_equal_to(False)
            assert_that(config._assertpy_diff_max).is_equal_to(5)
            assert_that(config._assertpy_cluster_minimum).is_equal_to(4)
            assert_that(config._assertpy_poll_threshold).is_equal_to(0.9)
        finally:
            pytest_unconfigure(config)

    def test_an_unusable_entry_cap_falls_back_to_the_documented_fifty(self):
        config = _RegisteredConfig(ini={"assertpy_diff_max_entries": "lots"})
        try:
            pytest_configure(config)
            assert_that(config._assertpy_diff_max).is_equal_to(50)
        finally:
            pytest_unconfigure(config)

    def test_configure_opens_the_run_with_an_empty_ledger_and_claims_the_session(self):
        config = _RegisteredConfig()
        try:
            pytest_configure(config)
            assert_that(config._assertpy_failures).is_equal_to([])
            assert_that(config._assertpy_failure_count).is_equal_to(0)
            assert_that(pytest_plugin._session_config[0]).is_same_as(config)
        finally:
            pytest_unconfigure(config)

    def test_the_no_ci_switch_forces_ci_mode_off_rather_than_back_to_autodetection(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_CI_MODE", True)
        config = _RegisteredConfig(options={"assertpy_snapshot_no_ci": True})
        try:
            pytest_configure(config)
            assert_that(snapshot_module._CI_MODE).is_equal_to(False)
        finally:
            pytest_unconfigure(config)
        assert_that(snapshot_module._CI_MODE).is_none()


class TestUnconfigureLeavesTheProcessAsItFoundIt:
    """A second session in the same process must not inherit the first one's state."""

    def test_the_diff_in_message_setting_goes_back_to_what_it_was_not_to_on(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", False)
        config = _RegisteredConfig()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_equal_to(False)

    def test_unconfigure_without_configure_leaves_the_diff_in_the_message(self, monkeypatch):
        monkeypatch.setattr(errors_module, "_RENDER_DIFF_IN_MESSAGE", False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(errors_module._RENDER_DIFF_IN_MESSAGE).is_equal_to(True)

    def test_poll_samples_stop_being_collected(self, monkeypatch):
        monkeypatch.setattr(async_assertions, "_COLLECT_RETRIES", False)
        config = _RegisteredConfig()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(async_assertions._COLLECT_RETRIES).is_false()

    def test_the_controller_tallies_are_released(self):
        pytest_plugin._controller_lost_workers[0] = 2
        pytest_plugin._controller_unreadable_workers[0] = 3
        pytest_plugin._controller_collect_errors[0] = 4
        pytest_plugin._controller_failure_count[0] = 5
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(
            [
                pytest_plugin._controller_lost_workers[0],
                pytest_plugin._controller_unreadable_workers[0],
                pytest_plugin._controller_collect_errors[0],
                pytest_plugin._controller_failure_count[0],
            ]
        ).is_equal_to([0, 0, 0, 0])

    def test_without_a_saved_value_the_vacuous_guard_comes_back_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY_VACUOUS", "1")
        monkeypatch.setattr(_satisfies_module, "_VACUOUS_GUARD", False)
        pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(_satisfies_module._VACUOUS_GUARD).is_true()


class TestTheBarsAtTheEdgeOfTheirRange:
    """Both parsers accept their extreme value rather than warning it away."""

    def test_a_poll_bar_of_one_means_only_a_poll_that_used_the_whole_budget(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(pytest_plugin._poll_threshold("1.0")).is_equal_to(1.0)

    def test_a_cluster_of_two_is_a_cluster(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(pytest_plugin._cluster_minimum("2")).is_equal_to(2)


class TestFullRunDetectionOnAStrippedDownConfig:
    """Every selector is read with a default, and only a namespace missing them can show it."""

    def test_a_run_whose_plugins_registered_none_of_the_selectors_is_still_a_full_run(self):
        assert_that(_is_full_run(SimpleNamespace(option=SimpleNamespace()))).is_true()


class TestTheNearTimeoutReportReachesTheTerminal:
    """The report goes to the terminal reporter by name, and measures a poll against its own budget."""

    @staticmethod
    def _lines(monkeypatch, rows, threshold=0.7):
        monkeypatch.setattr(pytest_plugin, "_retried", list(rows))
        reporter = MagicMock()
        config = SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter if name == "terminalreporter" else None),
            _assertpy_poll_threshold=threshold,
        )
        pytest_plugin._report_retries(config)
        return [call.args[0] for call in reporter.write_line.call_args_list]

    def test_the_report_names_itself_and_the_share_of_the_budget_the_poll_used(self, monkeypatch):
        lines = self._lines(monkeypatch, [("t.py::test_x", 7, 1.8, 2.0)])
        assert_that(lines[0]).described_as("held off the run's output by a blank line").is_empty()
        assert_that(lines).contains("assertpy polls that nearly timed out:")
        assert_that("\n".join(lines)).contains("90% of the budget")

    def test_a_poll_measured_against_its_own_budget_not_against_the_product(self, monkeypatch):
        assert_that(self._lines(monkeypatch, [("t.py::test_x", 3, 0.4, 2.0)])).is_empty()

    def test_a_poll_landing_exactly_on_the_bar_is_named(self, monkeypatch):
        lines = self._lines(monkeypatch, [("t.py::test_x", 3, 0.7, 1.0)])
        assert_that("\n".join(lines)).contains("t.py::test_x")


class TestTheDiffSectionReadsItsSettingsOffTheConfig:
    """Every setting the sections read comes off the config, including the defaults for a config
    that never went through configure."""

    def test_the_entry_cap_the_ini_set_reaches_the_section(self):
        report = _make_report()
        item = _configured_item(_assertpy_diff_enabled=True, _assertpy_diff_max=2)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=_diff_of(5))), item=item)
        assert_that(dict(_sections(report))["Structured Diff"]).contains("and 3 more entries")

    def test_turning_the_sections_off_drops_both_the_diff_and_the_trace(self):
        report = _make_report()
        item = _configured_item(_assertpy_diff_enabled=False, _assertpy_diff_max=50)
        exc = AssertionFailure("fail", diff=_diff_of(5), trace=_make_trace())
        _run_hook(report, _make_call(exc=exc), item=item)
        assert_that([title for title, _ in _sections(report)]).does_not_contain("Structured Diff", "Polling Trace")

    def test_a_config_that_never_configured_still_gets_its_sections(self):
        report = _make_report()
        exc = AssertionFailure("fail", diff=_diff_of(51), trace=_make_trace())
        _run_hook(report, _make_call(exc=exc), item=_configured_item())
        body = dict(_sections(report))
        assert_that(body).contains_key("Structured Diff", "Polling Trace")
        assert_that(body["Structured Diff"]).does_not_contain("\x1b[").contains("and 1 more entries")

    def test_the_failure_carries_plain_text_and_a_coloured_copy_beside_it(self):
        report = _make_report()
        item = _configured_item(_assertpy_diff_enabled=True, _assertpy_diff_max=2)
        _run_hook(report, _make_call(exc=AssertionFailure("fail", diff=_diff_of(5))), item=item)
        assert_that(dict(_sections(report))["Structured Diff"]).does_not_contain("\x1b[")
        assert_that(vars(report)["_assertpy_colored"]["Structured Diff"]).contains("\x1b[", "and 3 more entries")


class TestTheDiffIsColouredAsItIsDrawn:
    """Color reaches a writer that takes it and nothing else, as pytest's own traceback does."""

    @staticmethod
    def _logged(*, colored=True):
        try:
            raise AssertionFailure("fail")
        except AssertionFailure:
            longrepr = pytest.ExceptionInfo.from_current().getrepr()
        longrepr.addsection("AssertionFailure", "values")
        longrepr.addsection("Structured Diff", "plain")
        report = SimpleNamespace(longrepr=longrepr)
        if colored:
            report._assertpy_colored = {"Structured Diff": "\x1b[31mcoloured\x1b[0m"}
        pytest_plugin.pytest_runtest_logreport(report)
        return longrepr

    @staticmethod
    def _drawn(longrepr, *, markup):
        sink = io.StringIO()
        writer = TerminalWriter(file=sink)
        writer.hasmarkup = markup
        longrepr.toterminal(writer)
        return sink.getvalue()

    def test_a_writer_that_takes_colour_draws_the_coloured_copy(self):
        assert_that(self._drawn(self._logged(), markup=True)).contains("\x1b[31mcoloured").does_not_contain("plain")

    def test_every_other_reader_gets_the_plain_text(self):
        longrepr = self._logged()
        assert_that(self._drawn(longrepr, markup=False)).contains("plain").does_not_contain("\x1b[31m")
        assert_that(str(longrepr)).contains("plain").does_not_contain("\x1b[31m")

    def test_the_sections_are_plain_again_once_drawn(self):
        longrepr = self._logged()
        original = longrepr.sections
        self._drawn(longrepr, markup=True)
        assert_that(longrepr.sections).is_same_as(original)
        assert_that(original).is_equal_to([("AssertionFailure", "values", "-"), ("Structured Diff", "plain", "-")])

    def test_a_drawing_that_raises_still_puts_the_plain_text_back(self):
        longrepr = self._logged()
        original = longrepr.sections
        writer = MagicMock(hasmarkup=True)
        writer.sep.side_effect = RuntimeError("the terminal went away")
        with pytest.raises(RuntimeError):
            longrepr.toterminal(writer)
        assert_that(longrepr.sections).is_same_as(original)
        assert_that(original[-1]).is_equal_to(("Structured Diff", "plain", "-"))

    def test_a_failure_with_no_coloured_copy_is_drawn_as_pytest_draws_it(self):
        longrepr = self._logged(colored=False)
        assert_that(vars(longrepr)).does_not_contain_key("toterminal")

    def test_a_pickled_failure_still_draws_both(self):
        """A plugin that pickles its reports got a `PicklingError` from the closure this used to be."""
        restored = pickle.loads(pickle.dumps(self._logged()))
        assert_that(self._drawn(restored, markup=True)).contains("\x1b[31mcoloured")
        assert_that(self._drawn(restored, markup=False)).contains("plain").does_not_contain("\x1b[31m")

    def test_a_deep_copy_draws_its_own_sections(self):
        copied = copy.deepcopy(self._logged())
        copied.sections.append(("Captured log", "only on the copy", "-"))
        assert_that(self._drawn(copied, markup=True)).contains("\x1b[31mcoloured", "only on the copy")

    def test_a_failure_carried_as_text_is_left_alone(self):
        report = SimpleNamespace(longrepr="rendered as text", _assertpy_colored={"Structured Diff": "\x1b[31m"})
        pytest_plugin.pytest_runtest_logreport(report)
        assert_that(report.longrepr).is_equal_to("rendered as text")


class TestTheAllureAttachmentReadsItsSettingsOffTheConfig:
    """The attachment reads the same settings, and survives an allure that raises."""

    def test_a_config_that_never_configured_attaches_in_diff_mode(self):
        mock = _mock_allure()
        item = _configured_item()
        exc = AssertionFailure("fail", actual=1, expected=2, diff=_diff_of(51))
        with (
            patch("assertpy.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(_make_report(), _make_call(exc=exc), item=item)
        names = [call.kwargs["name"] for call in mock.attach.call_args_list]
        assert_that(names).is_equal_to(["Structured Diff"])
        assert_that(json.loads(mock.attach.call_args_list[0].kwargs["body"])["truncated"]).is_equal_to(1)

    def test_the_entry_cap_the_ini_set_reaches_the_attachment(self):
        mock = _mock_allure()
        item = _configured_item(_assertpy_allure_mode="diff", _assertpy_diff_max=2)
        exc = AssertionFailure("fail", diff=_diff_of(5))
        with (
            patch("assertpy.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy.pytest_plugin.allure", mock, create=True),
        ):
            _run_hook(_make_report(), _make_call(exc=exc), item=item)
        body = json.loads(mock.attach.call_args_list[0].kwargs["body"])
        assert_that(body["entries"]).is_length(2)
        assert_that(body["truncated"]).is_equal_to(3)

    def test_an_allure_that_raises_is_swallowed_where_it_happens(self):
        mock = _mock_allure()
        mock.attach.side_effect = RuntimeError("allure broken")
        report = _make_report()
        with (
            patch("assertpy.pytest_plugin._HAS_ALLURE", True),
            patch("assertpy.pytest_plugin.allure", mock, create=True),
        ):
            exc = AssertionFailure("f", actual=1, expected=2, diff=_diff_of(5))
            pytest_plugin._attach_report_sections(_make_item(), report, exc)
        assert_that(_sections(report)).is_length(2)


class TestTheValuesSectionOnAForeignException:
    """`actual` and friends are read off somebody else's `AssertionError`, which may carry only some."""

    def test_an_exception_carrying_only_actual_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.actual = 42
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(_sections(report))["AssertionFailure"]).contains("42")

    def test_an_exception_carrying_only_a_diff_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.diff = _diff_of(5)
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(_sections(report))).contains_key("Structured Diff")

    def test_an_exception_carrying_only_a_trace_still_gets_its_section(self):
        exc = AssertionError("fail")
        exc.trace = _make_trace()
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        assert_that(dict(_sections(report))).contains_key("Polling Trace")

    def test_the_pair_is_windowed_together_so_neither_side_is_dropped(self):
        exc = AssertionFailure("fail", actual="a" * 400 + "L", expected="a" * 400 + "R")
        report = _make_report()
        _run_hook(report, _make_call(exc=exc))
        lines = dict(_sections(report))["AssertionFailure"].splitlines()
        assert_that(lines).is_length(2)
        assert_that(lines[0].strip()).starts_with("actual:").contains("L")
        assert_that(lines[1].strip()).starts_with("expected:").contains("R")


class TestTheTerminalTimeline:
    """A repeat count is marked only where a sample was seen more than once, one line per sample."""

    def test_a_sample_seen_once_carries_no_repeat_count(self):
        lines = _format_trace(_one_sample_trace()).splitlines()
        assert_that(lines).is_length(2)
        assert_that(lines[1]).starts_with("  t=+").contains("fail: d")

    def test_a_sample_seen_twice_carries_one(self):
        assert_that(_format_trace(_one_sample_trace(repeats=2))).contains("fail x2: d")


class TestTheTraceAttachmentSchema:
    """The attachment is a documented wire format; a consumer branches on `format` and reads by name."""

    def test_every_field_a_consumer_reads_is_named(self):
        body = json.loads(_trace_to_json(_make_trace()))
        assert_that(body).contains_key("format", "kind", "total_polls", "elapsed", "summary", "samples")
        assert_that(body["samples"][0]).contains_key("t", "outcome", "detail", "repeats")
        assert_that(body["samples"][1]).contains_key("value")
        assert_that(body["deltas"][0]).contains_key("from_t", "to_t", "entries")

    def test_timings_are_rounded_to_the_millisecond(self):
        samples = [
            PollSample(elapsed=0.123456, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.987654, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=2, dropped=0, elapsed=1.234567, summary="s")
        body = json.loads(_trace_to_json(trace))
        assert_that(body["elapsed"]).is_equal_to(1.235)
        assert_that(body["samples"][0]["t"]).is_equal_to(0.123)
        assert_that(body["deltas"][0]["from_t"]).is_equal_to(0.123)
        assert_that(body["deltas"][0]["to_t"]).is_equal_to(0.988)

    def test_a_sample_seen_once_carries_its_value_and_no_repeat_count(self):
        sample = json.loads(_trace_to_json(_one_sample_trace()))["samples"][0]
        assert_that(sample["value"]).is_equal_to(1)
        assert_that(sample).does_not_contain_key("repeats")

    def test_an_unchanged_pair_is_skipped_without_ending_the_walk(self):
        samples = [
            PollSample(elapsed=0.0, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.4, outcome="fail", value=1, detail="d"),
            PollSample(elapsed=0.8, outcome="fail", value=2, detail="d"),
        ]
        trace = PollTrace(samples=samples, total_polls=3, dropped=0, elapsed=1.0, summary="s")
        assert_that(json.loads(_trace_to_json(trace))["deltas"]).is_length(1)

    def test_a_non_ascii_detail_stays_readable_in_the_attachment(self):
        assert_that(_trace_to_json(_one_sample_trace(detail="значение"))).contains("значение")

    def test_the_attachment_is_indented_for_a_person_to_read(self):
        assert_that(_trace_to_json(_make_trace())).contains('\n  "')

    def test_a_sample_value_json_cannot_express_is_refused_rather_than_written(self):
        with pytest.raises(ValueError):
            _trace_to_json(_one_sample_trace(value=float("nan")))


class TestTheDiffAttachmentOnForeignObjects:
    """`diff` is read off somebody else's exception, so every field is asked for rather than assumed."""

    def test_an_entry_with_no_fields_at_all_degrades_rather_than_raising(self):
        assert_that(pytest_plugin._entry_to_json(SimpleNamespace())).is_equal_to(
            {"path": "", "actual": None, "expected": None}
        )

    def test_a_diff_without_entries_attaches_nothing(self):
        assert_that(_diff_to_json(SimpleNamespace())).is_none()

    def test_a_diff_that_does_not_name_its_kind_is_marked_unknown(self):
        diff = SimpleNamespace(entries=[DiffEntry(path="k", actual=1, expected=2)])
        assert_that(json.loads(_diff_to_json(diff))["kind"]).is_equal_to("unknown")

    def test_a_cap_of_zero_means_unlimited(self):
        assert_that(json.loads(_diff_to_json(_diff_of(5), max_entries=0))["entries"]).is_length(5)

    def test_a_cap_of_one_shows_one_and_counts_the_rest(self):
        body = json.loads(_diff_to_json(_diff_of(3), max_entries=1))
        assert_that(body["entries"]).is_length(1)
        assert_that(body["truncated"]).is_equal_to(2)

    def test_the_default_cap_is_the_documented_fifty(self):
        assert_that(json.loads(_diff_to_json(_diff_of(51)))["entries"]).is_length(50)

    def test_a_non_ascii_value_stays_readable_in_the_attachment(self):
        diff = DiffResult(kind="dict", entries=[DiffEntry(path="k", actual="значение", expected="✓")])
        assert_that(_diff_to_json(diff)).contains("значение").contains("✓")

    def test_the_attachment_is_indented_for_a_person_to_read(self):
        assert_that(_diff_to_json(_diff_of(2))).contains('\n  "')


class TestTheAllureBodiesCarryWhatTheyClaim:
    """The name alone left the body and the attachment type of every attachment unasserted."""

    @staticmethod
    def _attached(exc, *, mode="diff"):
        mock = _mock_allure()
        _run_hook_with_allure(_make_report(), _make_call(exc=exc), mock, allure_mode=mode)
        return {call.kwargs["name"]: call.kwargs for call in mock.attach.call_args_list}

    def test_the_trace_attachment_carries_the_trace_as_typed_json(self):
        attached = self._attached(AssertionFailure("fail", trace=_make_trace()))["Polling Trace"]
        assert_that(attached["attachment_type"]).is_equal_to("json")
        assert_that(json.loads(attached["body"])["kind"]).is_equal_to("polling-trace")

    def test_a_non_ascii_value_stays_readable_in_the_values_attachment(self):
        exc = AssertionFailure("fail", actual="значение", expected="✓")
        assert_that(self._attached(exc, mode="full")["AssertionFailure"]["body"]).contains("значение").contains("✓")

    def test_the_values_attachment_is_indented_for_a_person_to_read(self):
        exc = AssertionFailure("fail", actual=1, expected=2)
        assert_that(self._attached(exc, mode="full")["AssertionFailure"]["body"]).contains('\n  "')


@pytest.mark.usefixtures("_clean_registries")
class TestTheSweepMessageIsActionable:
    """A count alone is not: the reader needs the key and the line that reached it."""

    @staticmethod
    def _swept():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_sessionfinish(SimpleNamespace(config=_controller_config(MagicMock())), 0)
        return [str(one.message) for one in caught if one.category is snapshot_module.SnapshotKeyReusedWarning]

    def test_it_names_the_key_and_where_it_was_reached(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        snapshot_module._ACCESS_SITES["/x/s.json", "9"] = "test_mod.py:9"
        assert_that(self._swept()[0]).contains("/x/s.json::9").contains("from test_mod.py:9")

    def test_a_key_whose_site_was_never_recorded_names_no_site(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        assert_that(self._swept()[0]).contains("/x/s.json::9").does_not_contain(" from ")

    def test_the_escalated_warning_is_printed_in_red(self):
        pytest_plugin._controller_accesses[("/x/s.json", "9")] = {"test_a", "test_b"}
        reporter = MagicMock()
        session = SimpleNamespace(config=_controller_config(reporter), exitstatus=0)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_sessionfinish(session, 0)
        written = reporter.write_line.call_args_list
        assert_that(written[0].args[0]).described_as("held off the run's output by a blank line").is_empty()
        error_line = [call for call in written if "ERROR" in str(call.args[0])]
        assert_that(error_line[0].kwargs).is_equal_to({"red": True})


@pytest.mark.usefixtures("_clean_registries")
class TestWhatAWorkerShipsWhenItRecordedNothing:
    """A worker that recorded nothing ships zeroes and empties, not invented values."""

    def test_a_worker_that_never_configured_ships_a_count_of_zero(self):
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_failure_count"]).is_equal_to(0)

    def test_an_access_whose_site_was_never_recorded_ships_an_empty_one(self, monkeypatch):
        monkeypatch.setattr(snapshot_module, "_ACCESS_NODES", {("/x/s.json", "9"): {"t.py::test_a"}})
        monkeypatch.setattr(snapshot_module, "_ACCESS_SITES", {})
        config = SimpleNamespace(workeroutput={})
        pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_accesses"]).is_equal_to([["/x/s.json", "9", ["t.py::test_a"], ""]])


@pytest.mark.usefixtures("_clean_registries")
class TestTheSnapshotReportNamesItself:
    """The orphan block opens with a blank separator and its own heading, read line by line."""

    def test_the_orphan_report_carries_its_own_heading(self, tmp_path, monkeypatch):
        snapname = str(tmp_path / "snap-mod.json")
        with open(snapname, "w", encoding="utf-8") as handle:
            json.dump({"10": 1, "30": 3}, handle)
        monkeypatch.setattr(snapshot_module, "_TOUCHED", {(snapname, "10")})
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", False)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE", raising=False)
        reporter = MagicMock()
        pytest_sessionfinish(SimpleNamespace(config=_controller_config(reporter)), 0)
        lines = [call.args[0] for call in reporter.write_line.call_args_list]
        assert_that(lines[0]).described_as("held off the run's output by a blank line").is_empty()
        assert_that(lines).contains("assertpy snapshots:")


class TestTheNearTimeoutReportIsPerSession:
    def test_unconfigure_clears_what_the_report_reads(self):
        """Module-level, so a second session in the same process opened with the first one's polls."""
        pytest_plugin._retried.append(("some_test", 3, 0.9, 1.0))
        config = _make_config()
        pytest_configure(config)
        pytest_unconfigure(config)
        assert_that(pytest_plugin._retried).is_empty()


@dataclasses.dataclass
class _Buyer:
    city: str
    zip: str = "0150"


@dataclasses.dataclass
class _Purchase:
    id: int
    buyer: _Buyer
    tags: list
    seen: int = 0


class _CountedKey:
    """A key in the slot of the number one, which counts each time its hash or its equality is asked."""

    hashed = 0
    compared = 0

    def __hash__(self) -> int:
        _CountedKey.hashed += 1
        return hash(1)

    def __eq__(self, other: object) -> bool:
        _CountedKey.compared += 1
        return self is other


def _failure_of(call):
    with pytest.raises(AssertionError) as caught:
        call()
    return caught.value


def _several():
    with soft_assertions():
        assert_that([1]).is_equal_to([2])


def is_seven(self):
    return self.is_equal_to(7)


def _handed(exc, *, item=None, report=None):
    """What the plugin handed to the comparison hook for *exc*: the calls the hook received."""
    item = _make_item() if item is None else item
    _run_hook(_make_report() if report is None else report, _make_call(exc=exc), item=item)
    return item.config.hook.pytest_assertrepr_compare.call_args_list


_KEYS = st.sampled_from(["id", "name", "at", "meta"])
_PAYLOADS = st.dictionaries(
    _KEYS,
    st.recursive(
        st.sampled_from([0, 1, 2, "a", "b", None, 1.5]),
        lambda inner: st.dictionaries(_KEYS, inner, max_size=3) | st.lists(inner, max_size=3),
        max_leaves=8,
    ),
    max_size=4,
)


@dataclasses.dataclass
class _Order:
    id: int
    city: str
    seen_at: int = 0


class TestAFailedEqualityKeepsWhatItCompared:
    """A failed equality keeps the two values it held against each other, `AssertionFailure._compared`.

    They are what a text comparison of two values is true of.  Where nothing was left out those are the value
    and the operand themselves.  Under ``ignore=`` or ``include=`` they are the two copies the diff is of,
    without the keys left out.  Where the comparison was by a tolerance, a comparator or a type no two texts
    say what was compared, and nothing is kept.
    """

    @pytest.mark.parametrize("kind", [dict, types.MappingProxyType], ids=["dict", "mappingproxy"])
    def test_the_value_and_the_operand_themselves_where_nothing_was_left_out(self, kind):
        # a mapping that is no dict is read through a copy to be compared: the pair kept is still the caller's own
        actual, expected = kind({"id": 1, "city": "Oslo"}), kind({"id": 1, "city": "Paris"})
        compared = _failure_of(lambda: assert_that(actual).is_equal_to(expected))._compared
        assert_that(compared[0]).is_same_as(actual)
        assert_that(compared[1]).is_same_as(expected)

    @pytest.mark.parametrize(
        ("actual", "expected", "options", "compared"),
        [
            pytest.param(
                {"id": 1, "city": "Oslo", "seen_at": 5},
                {"id": 1, "city": "Paris", "seen_at": 9},
                {"ignore": "seen_at"},
                ({"id": 1, "city": "Oslo"}, {"id": 1, "city": "Paris"}),
                id="a key left out",
            ),
            pytest.param(
                {"id": 1, "city": "Oslo", "seen_at": 5},
                {"id": 2, "city": "Paris", "seen_at": 9},
                {"include": "city"},
                ({"city": "Oslo"}, {"city": "Paris"}),
                id="one key looked at",
            ),
            pytest.param(
                {"order": {"city": "Oslo", "seen_at": 5}, "n": 1},
                {"order": {"city": "Paris", "seen_at": 9}, "n": 1},
                {"ignore": ("order", "seen_at")},
                ({"order": {"city": "Oslo"}, "n": 1}, {"order": {"city": "Paris"}, "n": 1}),
                id="a key left out by its path",
            ),
            pytest.param(
                [{"city": "Oslo", "seen_at": 5}],
                [{"city": "Paris", "seen_at": 9}],
                {"ignore": "seen_at"},
                ([{"city": "Oslo"}], [{"city": "Paris"}]),
                id="down a sequence",
            ),
        ],
    )
    def test_the_two_copies_without_the_keys_left_out(self, actual, expected, options, compared):
        failure = _failure_of(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(failure._compared).is_equal_to(compared)
        assert_that(failure.actual).is_same_as(actual)
        # the pair kept is the pair the diff is of
        again = _sub_diff_entries(*failure._compared, _ROOT, config=None)
        assert_that([entry.path for entry in again]).is_equal_to([entry.path for entry in failure.diff.entries])

    @settings(deadline=None, max_examples=400, suppress_health_check=[HealthCheck.too_slow])
    @given(actual=_PAYLOADS, expected=_PAYLOADS, left_out=st.sets(_KEYS, min_size=1, max_size=2))
    def test_whatever_is_left_out_the_pair_kept_is_the_pair_the_diff_is_of(self, actual, expected, left_out):
        try:
            assert_that(actual).is_equal_to(expected, ignore=sorted(left_out))
        except AssertionFailure as failure:
            kept, held = failure._compared
            assert_that(left_out & (set(kept) | set(held))).is_empty()
            assert_that(kept == held).is_false()
            again = _sub_diff_entries(kept, held, _ROOT, config=None)
            assert_that([entry.path for entry in again]).is_equal_to([entry.path for entry in failure.diff.entries])

    @pytest.mark.parametrize(
        "held",
        [lambda value: value, lambda value: [value], lambda value: {"a": value}],
        ids=["at the top", "in a list", "in a dict"],
    )
    def test_the_value_kept_is_the_value_compared_whatever_its_code_puts_on_the_builder(self, held):
        class Replacing:
            builder = None

            def __eq__(self, other: object) -> bool:
                Replacing.builder.val = "replaced"
                return False

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                Replacing.builder.val = "replaced"
                return "replacing"

        actual, expected = held(Replacing()), held(1)
        Replacing.builder = assert_that(actual)
        failure = _failure_of(lambda: Replacing.builder.is_equal_to(expected))
        assert_that(failure._compared[0]).is_same_as(actual)
        assert_that(failure._compared[1]).is_same_as(expected)
        assert_that(failure.actual).is_same_as(actual)
        assert_that(str(failure)).contains("replacing").does_not_contain("replaced")

    def test_a_record_under_a_key_option_is_kept_as_what_was_read_of_it(self):
        failure = _failure_of(
            lambda: assert_that(_Order(1, "Oslo", 5)).is_equal_to(_Order(1, "Paris", 9), ignore="seen_at")
        )
        assert_that([repr(side) for side in failure._compared]).is_equal_to(
            ["_Order(id=1, city='Oslo')", "_Order(id=1, city='Paris')"]
        )

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda: assert_that([1.0]).is_equal_to([2.0], tolerance=0.1), id="tolerance="),
            pytest.param(lambda: assert_that([1]).is_equal_to([1.0], strict_types=True), id="strict_types="),
            pytest.param(
                lambda: assert_that([1]).is_equal_to([2], comparators={int: lambda one, other: False}),
                id="comparators=",
            ),
            pytest.param(lambda: assert_that({"a": None}).is_equal_to({"a": 1}, ignore_null=True), id="ignore_null="),
            pytest.param(
                lambda: assert_that({"a": 1.0, "at": 1}).is_equal_to({"a": 2.0, "at": 2}, ignore="at", tolerance=0.1),
                id="a key left out beside a tolerance",
            ),
            pytest.param(
                lambda: assert_that({"a": 1}).is_equal_to({"a": True}, include="a", strict_types=True),
                id="a key looked at beside strict types",
            ),
            pytest.param(lambda: assert_that(1).not_.is_equal_to(1), id="a negation"),
            pytest.param(lambda: assert_that(1).is_not_equal_to(1), id="is_not_equal_to"),
            pytest.param(lambda: assert_that([1]).is_same_as([1]), id="is_same_as"),
            pytest.param(lambda: assert_that([1]).contains(2), id="contains"),
            pytest.param(lambda: assert_that([1]).is_in([2], [3]), id="is_in"),
            pytest.param(lambda: assert_that({"id": 1}).has_idd(2), id="has_<name> on a name that is not there"),
            pytest.param(lambda: assert_that([1]).is_length(2), id="is_length"),
            pytest.param(lambda: assert_that({"a": 1}).matches_structure({"a": 2}), id="matches_structure"),
            pytest.param(lambda: assert_that(1).satisfies(match.equal_to(2)), id="a matcher"),
            pytest.param(_several, id="a block of several"),
        ],
    )
    def test_nothing_is_kept_where_no_two_texts_say_what_was_compared(self, ask):
        assert_that(_failure_of(ask)._compared).is_none()

    def test_the_value_a_dynamic_assertion_read_and_its_operand(self):
        failure = _failure_of(lambda: assert_that(_Order(7, "Oslo")).has_id("7"))
        assert_that(failure._compared).is_equal_to((7, "7"))

    def test_the_last_value_of_a_poll_that_ran_out_of_time(self):
        failure = _failure_of(
            lambda: assert_that(lambda: [1]).eventually_sync().within(0.02).every(0.01).is_equal_to([2])
        )
        assert_that(failure._compared).is_equal_to(([1], [2]))

    def test_a_timeout_carries_the_pair_of_a_failure_of_this_library_and_of_no_other(self):
        class CarryingError(AssertionError):
            pass

        class GuardedError(AssertionFailure):
            @property
            def _compared(self):
                raise RuntimeError("no pair here")

            @_compared.setter
            def _compared(self, pair):
                pass

        carried = CarryingError("another library's")
        carried._compared = ([1], [2])
        assert_that(async_assertions._timed_out("out of time", None, carried)._compared).is_none()
        timed_out = async_assertions._timed_out("out of time", None, GuardedError("guarded"))
        assert_that((str(timed_out), timed_out._compared)).is_equal_to(("out of time", None))
        kept = _failure_of(lambda: assert_that([1]).is_equal_to([2]))
        assert_that(async_assertions._timed_out("out of time", None, kept)._compared).is_same_as(kept._compared)

    def test_an_equality_asked_by_an_extension_keeps_its_pair(self):
        add_extension(is_seven)
        try:
            failure = _failure_of(lambda: assert_that(8).is_seven())
        finally:
            remove_extension(is_seven)
        assert_that(failure.requirement.operation).is_equal_to("is_seven")
        assert_that(failure._compared).is_equal_to((8, 7))

    def test_a_pair_does_not_outlive_the_failure_it_was_kept_for(self):
        # collected and not raised, the failure takes the pair with it all the same
        with pytest.raises(AssertionError), soft_assertions():
            chain = assert_that([1]).is_equal_to([2])
        assert_that(chain._compared).is_none()
        assert_that(_failure_of(lambda: chain.contains(3))._compared).is_none()


class TestAFailedEqualityIsHandedToComparisonListeners:
    """`pytest_assertrepr_compare` is the hook pytest calls for a failed ``assert left == right``.

    A test runner that opens a comparison window listens to it, PyCharm's among them.  A failed equality is
    that comparison written another way, so the pair it kept is handed to the same listeners, the value on the
    left.  Nothing else is.
    """

    def test_the_value_and_the_operand_whole_and_in_that_order(self):
        actual, expected = [{"id": 1, "city": "Oslo"}], [{"id": 1, "city": "Paris"}]
        item = _make_item()
        calls = _handed(_failure_of(lambda: assert_that(actual).is_equal_to(expected)), item=item)
        assert_that(calls).is_length(1)
        assert_that(calls[0].args).is_empty()
        assert_that(set(calls[0].kwargs)).is_equal_to({"config", "op", "left", "right"})
        assert_that(calls[0].kwargs["config"]).is_same_as(item.config)
        assert_that(calls[0].kwargs["op"]).is_equal_to("==")
        assert_that(calls[0].kwargs["left"]).is_same_as(actual)
        assert_that(calls[0].kwargs["right"]).is_same_as(expected)

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda: assert_that(1).is_equal_to(2), id="two scalars"),
            pytest.param(lambda: assert_that("a\nb").is_equal_to("a\nc"), id="two texts"),
            pytest.param(lambda: assert_that({"a": 1}).is_equal_to({"a": 2}), id="two dicts"),
            pytest.param(lambda: assert_that(None).is_equal_to(0), id="None against a value"),
            pytest.param(lambda: assert_that(1).is_equal_to(None), id="a value against None"),
            pytest.param(lambda: assert_that(1).described_as("why").is_equal_to(2), id="described"),
            pytest.param(lambda: assert_that([{"a": 1}]).extracting("a").is_equal_to([2]), id="after a pivot"),
            pytest.param(
                lambda: assert_that(lambda: [1]).eventually_sync().within(0.02).every(0.01).is_equal_to([2]),
                id="the last value of a poll that ran out of time",
            ),
            pytest.param(
                lambda: assert_that({"a": 1, "at": 5}).is_equal_to({"a": 2, "at": 9}, ignore="at"), id="ignore="
            ),
            pytest.param(
                lambda: assert_that({"a": 1, "at": 5}).is_equal_to({"a": 2, "at": 9}, include="a"), id="include="
            ),
            pytest.param(lambda: assert_that({"id": 1}).has_id(2), id="has_<name>"),
        ],
    )
    def test_the_pair_a_failure_kept_is_the_pair_handed(self, ask):
        failure = _failure_of(ask)
        calls = _handed(failure)
        assert_that(calls).is_length(1)
        assert_that(calls[0].kwargs["left"]).is_same_as(failure._compared[0])
        assert_that(calls[0].kwargs["right"]).is_same_as(failure._compared[1])

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda: assert_that([1.0]).is_equal_to([2.0], tolerance=0.1), id="tolerance="),
            pytest.param(lambda: assert_that([1]).is_equal_to([1.0], strict_types=True), id="strict_types="),
            pytest.param(lambda: assert_that(1).not_.is_equal_to(1), id="a negation"),
            pytest.param(lambda: assert_that([1]).contains(2), id="contains"),
            pytest.param(_several, id="a block of several"),
        ],
    )
    def test_a_failure_that_kept_no_pair_hands_nothing(self, ask):
        assert_that(_handed(_failure_of(ask))).is_empty()

    def test_a_record_compared_by_its_fields_is_handed_as_the_dict_of_them(self):
        failure = _failure_of(
            lambda: assert_that(_Purchase(1, _Buyer("Oslo"), ["a"], seen=5)).is_equal_to(
                _Purchase(1, _Buyer("Paris"), ["a"], seen=9), ignore="seen"
            )
        )
        handed = _handed(failure)[0].kwargs

        assert_that(handed["left"]).is_equal_to({"id": 1, "buyer": {"city": "Oslo", "zip": "0150"}, "tags": ["a"]})
        assert_that(handed["right"]).is_equal_to({"id": 1, "buyer": {"city": "Paris", "zip": "0150"}, "tags": ["a"]})
        for side in (handed["left"], handed["right"]):
            assert_that(type(side)).is_same_as(dict)
            assert_that(type(side["buyer"])).is_same_as(dict)

    def test_a_dict_beside_a_record_is_handed_in_one_shape_and_laid_out_alike(self):
        payload = types.MappingProxyType({"id": 1, "buyer": {"city": "Oslo", "zip": "0150"}, "tags": ["a"], "seen": 5})
        handed = _handed(
            _failure_of(
                lambda: assert_that(payload).is_equal_to(_Purchase(1, _Buyer("Paris"), ["a"], seen=9), ignore="seen")
            )
        )[0].kwargs
        laid = [pprint.pformat(handed[side], width=30).splitlines() for side in ("left", "right")]

        assert_that(laid[0]).is_equal_to(
            ["{'buyer': {'city': 'Oslo',", "           'zip': '0150'},", " 'id': 1,", " 'tags': ['a']}"]
        )
        assert_that(laid[1]).is_equal_to([line.replace("Oslo", "Paris") for line in laid[0]])

    def test_records_inside_a_list_are_handed_as_dicts_in_a_list(self):
        handed = _handed(
            _failure_of(lambda: assert_that([_Buyer("Oslo")]).is_equal_to([_Buyer("Paris")], ignore="zip"))
        )[0].kwargs

        assert_that(handed["left"]).is_equal_to([{"city": "Oslo"}])
        assert_that(handed["right"]).is_equal_to([{"city": "Paris"}])
        assert_that(type(handed["left"][0])).is_same_as(dict)

    def test_the_failure_itself_keeps_the_record_it_compared(self):
        failure = _failure_of(lambda: assert_that(_Buyer("Oslo")).is_equal_to(_Buyer("Paris"), ignore="zip"))
        _handed(failure)

        assert_that(repr(failure._compared[0])).is_equal_to("_Buyer(city='Oslo')")
        assert_that(str(failure)).contains("_Buyer(city='Oslo')")

    def test_a_pair_too_deep_to_walk_is_handed_as_it_is(self, monkeypatch):
        def too_deep(value):
            raise RecursionError

        monkeypatch.setattr(pytest_plugin, "laid_out", too_deep)
        failure = _failure_of(lambda: assert_that(_Buyer("Oslo")).is_equal_to(_Buyer("Paris"), ignore="zip"))
        handed = _handed(failure)[0].kwargs

        assert_that(handed["left"]).is_same_as(failure._compared[0])
        assert_that(handed["right"]).is_same_as(failure._compared[1])


class TestARecordTakenApartIsLaidOut:
    """`laid_out` turns what a key option took apart into plain dicts, where a reader's `pprint` can break lines."""

    def test_a_value_with_nothing_to_turn_comes_back_as_itself(self):
        for value in ({"a": [1, (2, {"b": 3})]}, [1], (1,), "text", 7, None):
            assert_that(laid_out(value)).is_same_as(value)

    def test_a_record_at_any_depth_becomes_a_dict_and_its_container_is_built_anew(self):
        inner = TakenApart(_Buyer, {"city": "Oslo"})
        outer = TakenApart(_Purchase, {"id": 1, "buyer": inner, "tags": ["a"]})
        held = {"rows": [outer, (inner,)], "kept": [1]}

        made = laid_out(held)

        assert_that(made).is_equal_to(
            {"rows": [{"id": 1, "buyer": {"city": "Oslo"}, "tags": ["a"]}, ({"city": "Oslo"},)], "kept": [1]}
        )
        assert_that(type(made["rows"][0])).is_same_as(dict)
        assert_that(type(made["rows"][0]["buyer"])).is_same_as(dict)
        assert_that(type(made["rows"][1])).is_same_as(tuple)
        assert_that(made["kept"]).is_same_as(held["kept"])
        assert_that(type(held["rows"][0])).is_same_as(TakenApart)

    def test_a_container_of_a_class_of_its_own_is_left_as_it_is(self):
        class Rows(list):
            pass

        held = Rows([TakenApart(_Buyer, {"city": "Oslo"})])

        assert_that(laid_out(held)).is_same_as(held)

    def test_a_key_stays_what_it_is(self):
        key = (1, 2)
        made = laid_out({key: TakenApart(_Buyer, {"city": "Oslo"})})

        assert_that(next(iter(made))).is_same_as(key)

    def test_no_class_is_asked_what_it_is(self):
        class Loud(type):
            def __eq__(cls, other):
                raise RuntimeError("asked")

            __hash__ = type.__hash__

        class Held(metaclass=Loud):
            pass

        held = Held()

        assert_that(laid_out(held)).is_same_as(held)
        assert_that(laid_out([held])[0]).is_same_as(held)

    def test_a_mapping_holding_a_key_of_a_class_of_its_own_is_left_as_it_is(self):
        key = _CountedKey()
        record = TakenApart(_Buyer, {"city": "Oslo"})
        plain, keyed = {key: [1, {"a": 2}]}, {key: record, 1: record}
        taken = TakenApart(_Buyer, {key: record, "city": "Oslo"})
        hashed, compared = _CountedKey.hashed, _CountedKey.compared

        for held in (plain, keyed, taken):
            assert_that(laid_out(held)).is_same_as(held)

        assert_that((_CountedKey.hashed, _CountedKey.compared)).is_equal_to((hashed, compared))

    def test_a_plain_key_that_shares_a_slot_with_another_key_runs_none_of_its_code(self):
        key = _CountedKey()
        held = {key: 0, 1: TakenApart(_Buyer, {"city": "Oslo"})}
        hashed, compared = _CountedKey.hashed, _CountedKey.compared

        assert_that(laid_out(held)).is_same_as(held)
        assert_that((_CountedKey.hashed, _CountedKey.compared)).is_equal_to((hashed, compared))

    @pytest.mark.parametrize("key", ["a", 1, True, 1.5, b"a", None], ids=repr)
    def test_a_value_under_a_text_or_a_number_is_turned(self, key):
        made = laid_out({key: TakenApart(_Buyer, {"city": "Oslo"})})

        assert_that(type(made[key])).is_same_as(dict)

    def test_a_value_under_a_key_of_a_subclass_of_text_is_left(self):
        class Name(str):
            __slots__ = ()

        held = {Name("a"): TakenApart(_Buyer, {"city": "Oslo"})}

        assert_that(laid_out(held)).is_same_as(held)

    def test_a_part_two_places_share_is_turned_once(self):
        node: list = [TakenApart(_Buyer, {"city": "Oslo"})]
        for _ in range(18):
            node = [node, node]

        made = laid_out(node)

        for _ in range(18):
            assert_that(made[0]).is_same_as(made[1])
            made = made[0]
        assert_that(made).is_equal_to([{"city": "Oslo"}])

    def test_a_value_that_holds_itself_is_left_where_the_walk_meets_it_again(self):
        ring = TakenApart(_Buyer, {"city": "Oslo"})
        ring["again"] = ring
        rows: list = [TakenApart(_Buyer, {"city": "Oslo"})]
        rows.append(rows)

        made = laid_out(ring)
        listed = laid_out(rows)

        assert_that(type(made)).is_same_as(dict)
        assert_that(made["again"]).is_same_as(ring)
        assert_that(listed[0]).is_equal_to({"city": "Oslo"})
        assert_that(listed[1]).is_same_as(rows)

    @pytest.mark.parametrize(
        "exc",
        [
            AssertionFailure("built by hand", actual=1, expected=2),
            AssertionError("Expected <1> to be equal to <2>, but was not."),
            ValueError("not an assertion"),
        ],
        ids=["a failure built by hand", "an AssertionError of another library", "another exception"],
    )
    def test_a_failure_no_assertion_of_this_library_raised_is_not_handed(self, exc):
        assert_that(_handed(exc)).is_empty()

    @pytest.mark.parametrize("kept", [[1, 2], (1,), (1, 2, 3), "12", {"left": 1, "right": 2}])
    def test_anything_under_the_name_but_a_pair_is_not_handed(self, kept):
        failure = _failure_of(lambda: assert_that([1]).is_equal_to([2]))
        failure._compared = kept
        assert_that(_handed(failure)).is_empty()

    def test_an_exception_that_cannot_be_asked_for_its_pair_costs_nothing(self):
        class GuardedError(AssertionFailure):
            @property
            def _compared(self):
                raise RuntimeError("no pair here")

            @_compared.setter
            def _compared(self, pair):
                pass

        report = _make_report()
        assert_that(_handed(GuardedError("guarded"), report=report)).is_empty()
        assert_that(report.failed).is_true()

    def test_a_pair_on_an_exception_of_another_class_is_not_read(self):
        class CarryingError(AssertionError):
            pass

        carried = CarryingError("another library's")
        carried._compared = ([1], [2])
        assert_that(_handed(carried)).is_empty()

    def test_a_group_of_two_failures_hands_none_and_a_group_of_one_hands_it(self):
        one = _failure_of(lambda: assert_that([1]).is_equal_to([2]))
        other = _failure_of(lambda: assert_that([3]).is_equal_to([4]))
        assert_that(_handed(ExceptionGroup("teardown", [one, other]))).is_empty()
        assert_that(_handed(ExceptionGroup("teardown", [one, ValueError("not ours")]))).is_empty()
        assert_that(_handed(ExceptionGroup("teardown", [one]))).is_length(1)

    def test_a_test_that_did_not_fail_hands_nothing(self):
        failure = _failure_of(lambda: assert_that([1]).is_equal_to([2]))
        assert_that(_handed(failure, report=_make_report(failed=False))).is_empty()

    def test_turned_off_it_hands_nothing_and_the_diff_setting_is_not_asked(self):
        failure = _failure_of(lambda: assert_that([1]).is_equal_to([2]))
        item = _make_item()
        item.config._assertpy_comparison_enabled = False
        assert_that(_handed(failure, item=item)).is_empty()
        item = _make_item()
        item.config._assertpy_diff_enabled = False
        assert_that(_handed(failure, item=item)).is_length(1)

    @pytest.mark.parametrize(("written", "enabled"), [("on", True), ("off", False), ("", True), ("yes", True)])
    def test_the_setting_is_read_at_configure(self, written, enabled):
        config = _make_config(comparison=written)
        pytest_configure(config)
        try:
            assert_that(config._assertpy_comparison_enabled).is_equal_to(enabled)
        finally:
            pytest_unconfigure(config)

    def test_a_listener_that_raises_costs_neither_the_report_nor_its_sections(self):
        failure = _failure_of(lambda: assert_that({"a": 1}).is_equal_to({"a": 2}))
        item, report = _make_item(), _make_report()
        item.config.hook.pytest_assertrepr_compare.side_effect = RuntimeError("a listener of another plugin")
        calls = _handed(failure, item=item, report=report)
        assert_that(calls).is_length(1)
        assert_that(dict(_sections(report))).contains_key("AssertionFailure", "Structured Diff")


class TestTheHandoffInARealRun:
    """The hook as pytest dispatches it, heard by a plugin written as a runner's is."""

    _SUITE = (
        "from assertpy import assert_that\n\n\n"
        "ACTUAL = {'page': 1, 'items': [{'id': n, 'city': 'Oslo'} for n in range(3)]}\n"
        "EXPECTED = {'page': 2, 'items': [{'id': n, 'city': 'Oslo' if n != 1 else 'Paris'} for n in range(3)]}\n\n\n"
        "def test_plain():\n"
        "    assert_that(ACTUAL).is_equal_to(EXPECTED)\n\n\n"
        "def test_a_key_left_out():\n"
        "    assert_that(ACTUAL).is_equal_to(EXPECTED, ignore='page')\n\n\n"
        "def test_a_name_read():\n"
        "    assert_that(ACTUAL).has_page(2)\n\n\n"
        "def test_a_tolerance():\n"
        "    assert_that(ACTUAL).is_equal_to(EXPECTED, tolerance=0.5)\n\n\n"
        "def test_membership():\n"
        "    assert_that(ACTUAL['items']).contains({'id': 9})\n\n\n"
        "def test_passing():\n"
        "    assert_that(ACTUAL).is_equal_to(ACTUAL)\n"
    )

    # a listener the way a runner writes one: it keeps the pair when the hook is called, and reads it when the
    # report of that test is logged, which is after every report hook has run
    _LISTENER = (
        "import json\n\n"
        "import pytest\n\n"
        "import assertpy.pytest_plugin\n\n"
        "with open('plugin.txt', 'w', encoding='utf-8') as sink:\n"
        "    sink.write(assertpy.pytest_plugin.__file__)\n\n"
        "kept = {}\n\n\n"
        "def pytest_assertrepr_compare(config, op, left, right):\n"
        "    kept['pair'] = (op, left, right)\n\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_runtest_logreport(report):\n"
        "    if report.when == 'call':\n"
        "        with open('heard.jsonl', 'a', encoding='utf-8') as sink:\n"
        "            sink.write(json.dumps([report.nodeid.split('::')[-1], report.outcome, kept.pop('pair', None)]))\n"
        "            sink.write('\\n')\n"
    )

    def _run(self, tmp_path, *settings):
        (tmp_path / "test_handoff.py").write_text(self._SUITE, encoding="utf-8")
        (tmp_path / "conftest.py").write_text(self._LISTENER, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("\n".join(["[pytest]", *settings, ""]), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-p", "no:randomly"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHONPATH": _CHECKOUT},
        )
        assert_that(result.returncode).described_as(f"the child run: {result.stdout}{result.stderr}").is_equal_to(1)
        imported = pathlib.Path((tmp_path / "plugin.txt").read_text(encoding="utf-8")).resolve()
        assert_that(imported).described_as("the plugin the child ran").is_equal_to(
            pathlib.Path(pytest_plugin.__file__).resolve()
        )
        heard = [json.loads(line) for line in (tmp_path / "heard.jsonl").read_text(encoding="utf-8").splitlines()]
        return result, {name: (outcome, pair) for name, outcome, pair in heard}

    def test_a_listener_hears_the_pair_before_the_report_of_that_test_is_logged(self, tmp_path):
        result, heard = self._run(tmp_path)
        actual = {"items": [{"id": n, "city": "Oslo"} for n in range(3)]}
        expected = {"items": [{"id": n, "city": "Oslo" if n != 1 else "Paris"} for n in range(3)]}
        assert_that(heard).is_equal_to(
            {
                "test_plain": ("failed", ["==", {"page": 1, **actual}, {"page": 2, **expected}]),
                "test_a_key_left_out": ("failed", ["==", actual, expected]),
                "test_a_name_read": ("failed", ["==", 1, 2]),
                "test_a_tolerance": ("failed", None),
                "test_membership": ("failed", None),
                "test_passing": ("passed", None),
            }
        )
        # the failure is still this library's own, with what the plugin hangs on it
        assert_that(result.stdout).contains("assertpy.AssertionFailure: Expected <").contains("Structured Diff")

    def test_turned_off_in_the_ini_nothing_is_heard(self, tmp_path):
        _result, heard = self._run(tmp_path, "assertpy_comparison = off")
        assert_that({pair for _outcome, pair in heard.values()}).is_equal_to({None})
