"""The names this library had as assertpy2, read through the 2.x line as deprecated synonyms."""

from __future__ import annotations

import argparse
import textwrap
import warnings

import pytest
from _pytest.config.argparsing import Parser

from assertpy import _renamed, _satisfies, assert_that
from assertpy import snapshot as snapshot_module
from assertpy._dangling import ALLOW_MARKER, findings
from assertpy.pytest_plugin import _ini, _option, pytest_addoption


@pytest.fixture(autouse=True)
def _nothing_told_yet(monkeypatch):
    monkeypatch.setattr(_renamed, "_told", set())


class _Config:
    """A config answering only what the plugin registered, under the names given."""

    def __init__(self, *, ini=None, options=None):
        parser = Parser(_ispytest=True)
        pytest_addoption(parser)
        self._ini = {name: spec[-1] for name, spec in parser._inidict.items()} | dict(ini or {})
        self._options = vars(parser.parse([])) | dict(options or {})

    def getini(self, name):
        return self._ini[name]

    def getoption(self, name):
        return self._options[name]


class TestTheOldName:
    @pytest.mark.parametrize(
        ("current", "old"),
        [
            ("--assertpy-snapshot-update", "--assertpy2-snapshot-update"),
            ("assertpy_snapshot_update", "assertpy2_snapshot_update"),
            ("assertpy_diff", "assertpy2_diff"),
            ("ASSERTPY_SNAPSHOT_CI", "ASSERTPY2_SNAPSHOT_CI"),
            ("assertpy: allow-dangling", "assertpy2: allow-dangling"),
        ],
    )
    def test_each_spelling_gets_its_2_back(self, current, old):
        assert_that(_renamed.old_name(current)).is_equal_to(old)


class TestAnEnvironmentVariable:
    def test_the_current_name_is_read_without_a_word(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(_renamed.environ("ASSERTPY_SNAPSHOT_CI")).is_equal_to("1")

    def test_the_old_name_is_read_and_named(self, monkeypatch):
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_CI", raising=False)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "0")
        with pytest.warns(FutureWarning, match="ASSERTPY2_SNAPSHOT_CI is the assertpy2 name of ASSERTPY_SNAPSHOT_CI"):
            assert_that(_renamed.environ("ASSERTPY_SNAPSHOT_CI")).is_equal_to("0")

    def test_the_current_name_wins_where_both_are_set(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "1")
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "0")
        assert_that(_renamed.environ("ASSERTPY_SNAPSHOT_CI")).is_equal_to("1")

    def test_a_blank_current_name_falls_back_to_the_old_one(self, monkeypatch):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "")
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "0")
        with pytest.warns(FutureWarning, match="ASSERTPY2_SNAPSHOT_CI"):
            assert_that(_renamed.environ("ASSERTPY_SNAPSHOT_CI")).is_equal_to("0")

    def test_neither_name_reads_as_empty(self, monkeypatch):
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_CI", raising=False)
        monkeypatch.delenv("ASSERTPY2_SNAPSHOT_CI", raising=False)
        assert_that(_renamed.environ("ASSERTPY_SNAPSHOT_CI")).is_empty()

    def test_an_old_name_is_named_once_however_often_it_is_read(self, monkeypatch):
        monkeypatch.delenv("ASSERTPY_VACUOUS", raising=False)
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "1")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(3):
                _renamed.environ("ASSERTPY_VACUOUS")
        assert_that([str(one.message) for one in caught]).is_length(1)

    def test_a_warning_turned_into_an_error_is_raised_again_on_the_next_read(self, monkeypatch):
        monkeypatch.delenv("ASSERTPY_VACUOUS", raising=False)
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            for _ in range(2):
                with pytest.raises(FutureWarning):
                    _renamed.environ("ASSERTPY_VACUOUS")

    def test_the_filter_the_migration_page_gives_silences_it(self, monkeypatch):
        monkeypatch.delenv("ASSERTPY_VACUOUS", raising=False)
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "1")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            warnings.filterwarnings("ignore", message=".*is the assertpy2 name of", category=FutureWarning)
            assert_that(_renamed.environ("ASSERTPY_VACUOUS")).is_equal_to("1")

    def test_each_variable_the_library_reads_answers_to_its_old_name(self, monkeypatch):
        for current in ("ASSERTPY_SNAPSHOT_UPDATE", "ASSERTPY_SNAPSHOT_CI", "ASSERTPY_VACUOUS", "CI"):
            monkeypatch.delenv(current, raising=False)
        monkeypatch.setattr(snapshot_module, "_UPDATE_ALL", False)
        monkeypatch.setattr(snapshot_module, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_UPDATE", "1")
        monkeypatch.setenv("ASSERTPY2_SNAPSHOT_CI", "1")
        monkeypatch.setenv("ASSERTPY2_VACUOUS", "1")
        with pytest.warns(FutureWarning):
            assert_that(snapshot_module._update_enabled()).is_true()
            assert_that(snapshot_module._ci_mode_enabled()).is_true()
            assert_that(_satisfies._env_enabled()).is_true()


class TestAFlag:
    def test_the_old_flag_parses_and_stays_out_of_the_help(self):
        parser = Parser(_ispytest=True)
        pytest_addoption(parser)
        options = parser.parse(["--assertpy2-snapshot-update"])
        hidden = [option.attrs()["help"] for option in parser._anonymous.options if "--assertpy2-" in option.names()[0]]
        assert_that(options.assertpy2_snapshot_update).is_true()
        assert_that(hidden).is_length(5).contains_only(argparse.SUPPRESS)

    def test_the_old_flag_turns_the_switch_on_and_is_named(self):
        config = _Config(options={"assertpy2_dangling": True})
        with pytest.warns(FutureWarning, match="--assertpy2-dangling is the assertpy2 name of --assertpy-dangling"):
            assert_that(_option(config, "assertpy_dangling")).is_true()

    def test_the_current_flag_says_nothing_of_the_old_one(self):
        config = _Config(options={"assertpy_dangling": True})
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(_option(config, "assertpy_dangling")).is_true()

    def test_no_flag_is_off(self):
        assert_that(_option(_Config(), "assertpy_dangling")).is_false()


class TestASetting:
    def test_the_old_setting_is_read_where_the_current_one_is_not_written(self):
        config = _Config(ini={"assertpy2_diff": "off"})
        with pytest.warns(FutureWarning, match="assertpy2_diff is the assertpy2 name of assertpy_diff"):
            assert_that(_ini(config, "assertpy_diff")).is_equal_to("off")

    def test_the_current_setting_wins_and_the_old_one_is_still_named(self):
        config = _Config(ini={"assertpy_diff": "on", "assertpy2_diff": "off"})
        with pytest.warns(FutureWarning, match="assertpy2_diff"):
            assert_that(_ini(config, "assertpy_diff")).is_equal_to("on")

    def test_a_list_setting_is_read_by_its_old_name_too(self):
        config = _Config(ini={"assertpy2_dangling_entries": ["check"]})
        with pytest.warns(FutureWarning, match="assertpy2_dangling_entries"):
            assert_that(_ini(config, "assertpy_dangling_entries")).is_equal_to(["check"])

    def test_an_unwritten_setting_is_empty_under_both_names(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(_ini(_Config(), "assertpy_diff")).is_empty()
            assert_that(_ini(_Config(), "assertpy_dangling_entries")).is_empty()


class TestTheDanglingCheck:
    BODY = "def test_x():\n    assert_that(1)\n"

    def test_an_import_from_the_old_package_is_read_as_this_one(self):
        found = findings("from assertpy2 import assert_that\n" + self.BODY, "sample.py")
        assert_that(found).is_length(1)

    def test_a_module_imported_under_the_old_name_is_read_as_this_one(self):
        found = findings("import assertpy2\ndef test_x():\n    assertpy2.assert_that(1)\n", "sample.py")
        assert_that(found).is_length(1)

    def test_the_old_marker_silences_the_statement_without_a_warning(self):
        """No warning: the check runs at collection, where a warning under `-W error` aborts the run."""
        source = textwrap.dedent("""\
            from assertpy import assert_that
            def test_x():
                assert_that(1)  # assertpy2: allow-dangling
            """)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(findings(source, "sample.py")).is_empty()

    def test_the_current_marker_says_nothing_of_the_old_one(self):
        source = f"from assertpy import assert_that\ndef test_x():\n    assert_that(1)  # {ALLOW_MARKER}\n"
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert_that(findings(source, "sample.py")).is_empty()
