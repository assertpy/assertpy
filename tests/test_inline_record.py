"""Recording tests run in-process (so coverage counts) without ever applying a rewrite to this file:
`_inline._SEEN` is monkeypatched to an isolated dict, and `apply` is exercised only on temp files.
`TestARealUpdateRun` runs pytest itself over a test file, records, and runs it again.
"""

import ast
import collections
import datetime
import os
import pathlib
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from tests.optional import needs

needs("executing")
needs("asttokens")

import assertpy._inline as _inline
import assertpy.pytest_plugin as _plugin
import assertpy.snapshot as _snap
from assertpy import AssertionFailure, assert_that, match, soft_assertions


def _now(filename):
    """The digest of *filename*'s text as it is now, which a row names the text it was located in by."""
    return [_inline._digest(_inline._read(filename)[0])]


def _written(filename, start, end, text, sources=None):
    """A row as one process ships it: a call settled on *text*, every run of it taking that literal, located
    in the file as it is now unless *sources* says otherwise."""
    return (filename, start, end, text, True, [text], _now(filename) if sources is None else sources, text)


def _runs():
    """Every run the recorder saw, in the order it saw them."""
    return [run for runs in _inline._SEEN.values() for run in runs]


def _site():
    """The one place the recorder saw, as ``(filename, start, end)``, with the text its first run would write."""
    ((place, runs),) = _inline._SEEN.items()
    return (*place, runs[0].text)


def _decided_texts():
    """What each place would be written with, ``None`` where nothing asked for a rewrite."""
    return [row[3] for row in _inline.shipped()]


def _controller_config(root):
    option = SimpleNamespace(keyword="", markexpr="", last_failed=False, failed_first=False)
    return SimpleNamespace(
        option=option, pluginmanager=SimpleNamespace(get_plugin=lambda name: None), rootpath=pathlib.Path(root)
    )


class TestRecord:
    def test_records_scalar_and_container(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that({"a": 1, "b": [2, 3]}).matches_inline()
        assert_that(_runs()).is_length(1)
        assert_that(_runs()[0].text).is_equal_to("{'a': 1, 'b': [2, 3]}")

    def test_wide_value_is_wrapped_multiline(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        wide = {"user": {"id": 1, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(wide).matches_inline()
        assert_that(_runs()[0].text).contains("\n")

    @pytest.mark.parametrize(
        "value", [frozenset({1, 2}), [frozenset({1})], set()], ids=["frozenset", "inside", "empty set"]
    )
    def test_a_set_written_as_a_call_is_recorded(self, monkeypatch, value):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(value).matches_inline()
        ((_name, _start, _end, written, settled, _texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled)).is_equal_to((repr(value), True))

    def test_non_literalable_is_rejected(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.raises(TypeError, match="use snapshot"):
            assert_that(datetime.datetime(2020, 1, 1)).matches_inline()
        assert_that(_inline._SEEN).is_empty()


class TestApply:
    def test_apply_inserts_at_offset(self, tmp_path, monkeypatch):
        target = tmp_path / "snap_me.py"
        target.write_text("at().matches_inline()\n", encoding="utf-8")
        assert_that(_inline.apply_inline_records([_written(str(target), 20, 20, "{'a': 1}")], str(tmp_path))).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline({'a': 1})\n")

    def test_apply_replaces_range(self, tmp_path, monkeypatch):
        target = tmp_path / "snap_upd.py"
        target.write_text("x = 1\n", encoding="utf-8")
        assert_that(_inline.apply_inline_records([_written(str(target), 4, 5, "2")], str(tmp_path))).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("x = 2\n")


class TestUpdate:
    def test_drift_under_update_records_replacement(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"a": 2}).matches_inline({"a": 1})
        assert_that(_runs()).is_length(1)
        assert_that(_runs()[0].text).is_equal_to("{'a': 2}")

    def test_no_drift_under_update_is_noop(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        assert_that({"a": 1}).matches_inline({"a": 1})
        assert_that(_decided_texts()).is_equal_to([None])

    def test_update_non_literalable_rejected(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.raises(TypeError, match="use snapshot"):
            assert_that(datetime.datetime(2020, 1, 1)).matches_inline(datetime.datetime(2019, 1, 1))


class TestXdist:
    def test_worker_ships_inline_records(self, monkeypatch):
        run = _inline._Run("{'a': 1}", True, {"a": 1}, lambda value, candidate: value == candidate, "d")
        monkeypatch.setattr(_inline, "_SEEN", {("/x/test_a.py", 5, 5): [run]})
        config = SimpleNamespace(workeroutput={})
        _plugin.pytest_sessionfinish(SimpleNamespace(config=config), 0)
        assert_that(config.workeroutput["assertpy_inline"]).is_equal_to(
            [["/x/test_a.py", 5, 5, "{'a': 1}", True, ["{'a': 1}"], ["d"], "{'a': 1}"]]
        )

    def test_controller_collects_worker_inline(self):
        _plugin._controller_inline.clear()
        node = SimpleNamespace(
            workeroutput={"assertpy_inline": [list(_written("/x/test_a.py", 5, 5, "{'a': 1}", ["d"]))]}
        )
        _plugin.pytest_testnodedown(node, None)
        assert_that(_plugin._controller_inline).contains(_written("/x/test_a.py", 5, 5, "{'a': 1}", ["d"]))
        _plugin._controller_inline.clear()

    def test_controller_applies_collected_inline(self, tmp_path, monkeypatch):
        target = tmp_path / "shipped.py"
        target.write_text("at().matches_inline()\n", encoding="utf-8")
        monkeypatch.setattr(_inline, "_SEEN", {})
        monkeypatch.setattr(_snap, "_TOUCHED", set())
        _plugin._controller_touched.clear()
        _plugin._controller_inline.clear()
        _plugin._controller_inline.append(_written(str(target), 20, 20, "{'a': 1}"))
        _plugin.pytest_sessionfinish(SimpleNamespace(config=_controller_config(tmp_path)), 0)
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline({'a': 1})\n")
        assert_that(_plugin._controller_inline).is_empty()


class TestTheControllerFailsTheRun:
    def test_a_call_it_cannot_write_is_named_and_the_run_goes_red(self, tmp_path, monkeypatch):
        target = tmp_path / "conflict.py"
        target.write_text("at().matches_inline()\n", encoding="utf-8", newline="")
        monkeypatch.setattr(_inline, "_SEEN", {})
        monkeypatch.setattr(_snap, "_TOUCHED", set())
        _plugin._controller_touched.clear()
        _plugin._controller_inline.clear()
        _plugin._controller_inline.append((str(target), 20, 20, None, False, ["1", "2"], _now(str(target)), None))
        lines = []
        config = _controller_config(tmp_path)
        reporter = SimpleNamespace(write_line=lambda line, **style: lines.append(line))
        config.pluginmanager = SimpleNamespace(get_plugin=lambda name: reporter)
        session = SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
        _plugin.pytest_sessionfinish(session, 0)
        assert_that(session.exitstatus).is_equal_to(pytest.ExitCode.TESTS_FAILED)
        assert_that(lines).contains(
            f"ERROR: {target}:1: matches_inline() saw values no one literal matches, so nothing was written:"
            " <1>, <2>. One literal stands for every case that reaches the call: give each case a call of its own,"
            " or use snapshot()"
        )
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline()\n")


class TestGuards:
    def test_is_literalable(self):
        assert_that(_inline.is_literalable({"a": [1, 2], "b": (3, None)})).is_true()
        assert_that(_inline.is_literalable({"a": datetime.date(2020, 1, 1)})).is_false()
        assert_that(_inline.is_literalable([1, object()])).is_false()

    @pytest.mark.parametrize(
        ("source", "literal"),
        [
            ("frozenset({1, 2})", True),
            ("frozenset()", True),
            ("set()", True),
            ("[frozenset([1])]", True),
            ("{'k': frozenset({1})}", True),
            ("(1, -2.5, 'a', None)", True),
            ("frozenset(x)", False),
            ("frozenset({1}, 2)", False),
            ("frozenset(iterable={1})", False),
            ("sorted({1})", False),
            ("module.frozenset({1})", False),
            ("{**base}", False),
            ("{'k': x}", False),
            ("[*items]", False),
            ("NAME", False),
        ],
    )
    def test_an_update_replaces_what_a_recording_writes(self, source, literal):
        assert_that(_inline._is_literal(ast.parse(source, mode="eval").body)).is_equal_to(literal)

    def test_missing_tooling(self):
        with patch.dict(sys.modules, {"executing": None}), pytest.raises(ImportError, match=r"assertpy\[inline\]"):
            _inline._ensure_inline_tooling()


class TestRecordedPosition:
    """Where the rewrite lands, and at what indentation.  The tests above assert the recorded *text*
    and never the offsets, so an off-by-one in either would rewrite the wrong characters and still
    pass every one of them.  Each check reads this file back and compares against what the source
    actually says, rather than restating the implementation's arithmetic.
    """

    @staticmethod
    def _source_of(filename):
        return pathlib.Path(filename).read_text(encoding="utf-8")

    def test_a_create_inserts_just_inside_the_closing_paren(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(1).matches_inline()
        filename, start, end, _text = _site()
        source = self._source_of(filename)
        assert_that(start).is_equal_to(end)
        assert_that(source[start]).is_equal_to(")")
        assert_that(source[start - len("matches_inline(") : start]).is_equal_to("matches_inline(")

    def test_an_update_replaces_exactly_the_old_literal(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"a": 2}).matches_inline({"a": 1})
        filename, start, end, _text = _site()
        assert_that(self._source_of(filename)[start:end]).is_equal_to('{"a": 1}')

    def test_a_created_multiline_literal_is_indented_to_the_call(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        wide = {"user": {"id": 1, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(wide).matches_inline()
        filename, start, _end, text = _site()
        source = self._source_of(filename)
        column = start - (source.rfind("\n", 0, start) + 1)
        assert_that(text).contains("\n")
        # the column is read off this file, so an off-by-one in the recorder surfaces as a different rendering
        assert_that(text).is_equal_to(_inline._format_literal(wide, column))

    def test_an_updated_multiline_literal_is_indented_to_the_literal(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})
        wide = {"user": {"id": 2, "name": "Alice", "roles": ["admin", "editor", "viewer"]}, "meta": {"total": 3}}
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that(wide).matches_inline({"user": 1})
        filename, start, _end, text = _site()
        source = self._source_of(filename)
        column = start - (source.rfind("\n", 0, start) + 1)
        assert_that(text).contains("\n")
        assert_that(text).is_equal_to(_inline._format_literal(wide, column))


class TestRecordingMessages:
    """What the recorder says it did, stated whole: the category alone left every word unasserted."""

    @pytest.fixture(autouse=True)
    def _recording(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})

    def test_a_value_that_cannot_be_a_literal_names_its_type_and_the_way_out(self):
        with pytest.raises(TypeError) as failure:
            assert_that(datetime.datetime(2020, 1, 1)).matches_inline()
        assert_that(str(failure.value)).is_equal_to(
            "an inline snapshot literal must be a dict/list/tuple/set of scalars, not"
            " datetime - use snapshot() to store it in a file instead"
        )

    def test_the_created_warning_states_what_it_did(self):
        with pytest.warns(_snap.SnapshotCreatedWarning) as caught:
            assert_that(1).matches_inline()
        assert_that(str(caught[0].message)).is_equal_to(
            "recorded inline snapshot: this run captured the value into the test source;"
            " subsequent runs compare against it"
        )

    def test_the_updated_warning_states_what_it_did(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning) as caught:
            assert_that({"a": 2}).matches_inline({"a": 1})
        assert_that(str(caught[0].message)).is_equal_to(
            "updated inline snapshot: this run overwrote the stored literal instead of comparing;"
            " subsequent runs compare against it"
        )

    def test_the_created_warning_points_at_the_calling_test(self):
        # under `-W error` a warning attributed to the library blames the wrong file
        with pytest.warns(_snap.SnapshotCreatedWarning) as caught:
            assert_that(1).matches_inline()
        assert_that(pathlib.Path(caught[0].filename).name).is_equal_to("test_inline_record.py")

    def test_the_updated_warning_points_at_the_calling_test(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning) as caught:
            assert_that({"a": 2}).matches_inline({"a": 1})
        assert_that(pathlib.Path(caught[0].filename).name).is_equal_to("test_inline_record.py")


class TestUpdateHonorsTheComparisonOptions:
    """A knob that makes the two values equal must also make them not stale, or update mode rewrites a
    literal that never drifted."""

    @pytest.fixture(autouse=True)
    def _recording(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})

    def test_ignore_keeps_the_literal(self):
        assert_that({"id": 99, "name": "Alice"}).matches_inline({"id": 0, "name": "Alice"}, ignore="id")
        assert_that(_decided_texts()).is_equal_to([None])

    def test_include_keeps_the_literal(self):
        assert_that({"id": 99, "name": "Alice"}).matches_inline({"id": 0, "name": "Alice"}, include="name")
        assert_that(_decided_texts()).is_equal_to([None])

    def test_tolerance_keeps_the_literal(self):
        assert_that({"x": 1.001}).matches_inline({"x": 1.0}, tolerance=0.01)
        assert_that(_decided_texts()).is_equal_to([None])

    def test_a_comparator_keeps_the_literal(self):
        assert_that({"name": "ALICE"}).matches_inline(
            {"name": "Alice"}, comparators={"name": lambda actual, expected: actual.lower() == expected.lower()}
        )
        assert_that(_decided_texts()).is_equal_to([None])


_EXPECTED_BY_NAME = {"expected": {"a": 1}}


class _Uncopyable:
    """A comparator or a value `copy.deepcopy` refuses."""

    def __deepcopy__(self, memo):
        raise TypeError("not this one")

    def __call__(self, actual, expected):
        return actual == expected

    def __eq__(self, other):
        return other == {"a": 1}

    __hash__ = object.__hash__


class TestTheRecorderReadsTheCallAsWritten:
    """Where the literal goes, read off the call itself, whatever arguments sit beside the empty slot."""

    @pytest.fixture(autouse=True)
    def _recording(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})

    def test_a_call_with_keywords_takes_the_literal_first(self):
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that({"id": 7}).matches_inline(ignore="id")
        filename, start, _end, text = _site()
        source = pathlib.Path(filename).read_text(encoding="utf-8")
        assert_that(source[start - len("matches_inline(") : start]).is_equal_to("matches_inline(")
        assert_that(text).is_equal_to("{'id': 7}, ")

    def test_check_records_into_the_test_and_not_into_the_package(self):
        with pytest.warns(_snap.SnapshotCreatedWarning):
            assert_that(assert_that(1).check().matches_inline().passed).is_true()
        assert_that(pathlib.Path(_site()[0]).name).is_equal_to("test_inline_record.py")

    def test_an_expected_keyword_is_the_literal_an_update_replaces(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"a": 2}).matches_inline(expected={"a": 1})
        filename, start, end, _text = _site()
        assert_that(pathlib.Path(filename).read_text(encoding="utf-8")[start:end]).is_equal_to('{"a": 1}')

    def test_a_name_is_not_rewritten_into_a_literal(self):
        expected = {"a": 1}
        with pytest.raises(TypeError) as refusal:
            assert_that({"a": 2}).matches_inline(expected)
        assert_that(str(refusal.value)).is_equal_to(
            "update mode cannot rewrite this matches_inline(): its expected value <expected> is not a literal,"
            " and writing one in its place would stop the test reading it - write the literal into the call,"
            " or update the value by hand"
        )
        assert_that(_inline._SEEN).is_empty()

    def test_a_name_that_still_matches_is_left_alone(self):
        expected = {"a": 1}
        assert_that({"a": 1}).matches_inline(expected)
        assert_that(_inline._SEEN).is_empty()

    @pytest.mark.parametrize(
        "call",
        [
            lambda: assert_that({"a": 2}).matches_inline(*[{"a": 1}]),
            pytest.param(
                lambda: assert_that({"a": 2}).matches_inline(**_EXPECTED_BY_NAME),
                marks=pytest.mark.skipif(sys.version_info < (3, 11), reason="below 3.11 the call is not found"),
            ),
        ],
        ids=["star", "double-star"],
    )
    def test_an_unpacked_literal_cannot_be_found(self, call):
        with pytest.raises(TypeError, match="passed through unpacking, so there is no literal to replace"):
            call()
        assert_that(_inline._SEEN).is_empty()

    def test_a_value_changed_after_its_run_is_judged_as_it_was(self):
        data = {}
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for n in (1, 2):
                data["n"] = n
                assert_that(data).matches_inline({"n": 0})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["{'n': 1}", "{'n': 2}"]))

    def test_a_value_changed_after_its_run_still_turns_down_what_it_refused(self):
        held = collections.OrderedDict(a=1)
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in (held, {"a": 2}):
                assert_that(value).matches_inline({"a": 1})
        held["a"] = 2
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, [None, "{'a': 2}"]))

    def test_options_changed_after_their_runs_are_judged_as_they_were(self):
        rules = {int: lambda actual, expected: actual == expected}
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in (1, 2):
                assert_that(value).matches_inline(0, comparators=rules)
        rules[int] = lambda actual, expected: True
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["1", "2"]))

    def test_options_that_cannot_be_copied_are_asked_as_the_run_ran(self):
        assert_that(_inline.captured({"comparators": {int: _Uncopyable()}})).is_same_as(_inline.UNCAPTURED)
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that(1).matches_inline(0, comparators={int: _Uncopyable()})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to(("1", True, ["1"]))

    def test_plain_options_changed_later_are_asked_as_they_were(self):
        ignored = ["id"]
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in ({"id": 1, "n": 1}, {"id": 2, "n": 2}):
                assert_that(value).matches_inline({"id": 0, "n": 1}, ignore=ignored)
        ignored.append("n")
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["{'id': 1, 'n': 1}", "{'id': 2, 'n': 2}"]))

    def test_a_run_is_asked_about_its_literal_not_the_object_it_holds(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that({"n": 1}).matches_inline(
                {"n": 0}, comparators={dict: lambda actual, expected: actual is expected}
            )
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["{'n': 1}"]))

    def test_a_tuple_a_copy_would_hand_back_as_itself_is_read_anew(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that(tuple(range(1, 3))).matches_inline(
                (0, 0), comparators={tuple: lambda actual, expected: actual is expected}
            )
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["(1, 2)"]))

    def test_a_run_is_asked_about_the_object_it_compared_with_its_shared_references(self):
        def aliasing(actual, expected):
            return (actual[0] is actual[1]) == (expected[0] is expected[1]) and actual == expected

        part = [1]
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that([part, part]).matches_inline([[0], [0]], comparators={list: aliasing})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["[[1], [1]]"]))

    def test_a_literal_is_asked_about_as_python_compiles_it(self):
        def aliasing(actual, expected):
            return (actual[0] is actual[1]) == (expected[0] is expected[1]) and actual == expected

        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that((tuple(range(1, 3)), tuple(range(1, 3)))).matches_inline(
                ((0, 0), (0, 0)), comparators={tuple: aliasing}
            )
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["((1, 2), (1, 2))"]))
        # the literal as this file compiles it: one inner tuple twice, which the value it would hold does not have
        assert_that(aliasing((tuple(range(1, 3)), tuple(range(1, 3))), ((1, 2), (1, 2)))).is_false()

    def test_a_literal_a_run_has_answered_is_not_asked_again(self):
        asked = []

        def counting(actual, expected):
            asked.append(expected)
            return actual == expected

        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for _ in range(5):
                assert_that(1).matches_inline(0, comparators={int: counting})
        # each run: once against the old literal, once against its own
        assert_that(asked).is_equal_to([0, 1] * 5)
        assert_that(_decided_texts()).is_equal_to(["1"])

    def test_a_comparator_s_own_state_changed_later_does_not_move_a_run(self):
        state = {"loose": False}
        rules = {int: lambda actual, expected: state["loose"] or actual == expected}
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in (1, 2):
                assert_that(value).matches_inline(0, comparators=rules)
        state["loose"] = True
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["1", "2"]))

    def test_a_run_with_a_comparator_takes_a_literal_asked_for_before_it(self):
        def lower(actual, expected):
            return actual.lower() == expected.lower()

        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in ("ALICE", "alice"):
                assert_that(value).matches_inline("bob", comparators={str: lower})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to(("'ALICE'", True, ["'ALICE'", "'alice'"]))

    def test_a_run_asked_only_as_it_ran_takes_no_literal_asked_for_after_it(self):
        def takes_all(value, candidate):
            return True

        runs = [
            _inline._Run(None, False, object(), takes_all, "d", later=False),
            _inline._Run("2", True, 2, takes_all, "d"),
        ]
        assert_that(_inline._settled(runs)).is_equal_to((None, False))
        runs[0].judged["2"] = True
        assert_that(_inline._settled(runs)).is_equal_to(("2", True))

    def test_a_value_that_is_no_literal_still_has_a_say(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            for value in (collections.OrderedDict(a=1), {"a": 2}):
                assert_that(value).matches_inline({"a": 1})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, [None, "{'a': 2}"]))

    def test_a_literal_its_own_comparison_turns_down_is_not_settled(self):
        with pytest.warns(_snap.SnapshotUpdatedWarning):
            assert_that(1).matches_inline(0, comparators={int: lambda actual, expected: False})
        ((_name, _start, _end, written, settled, texts, _sources, _held),) = _inline.shipped()
        assert_that((written, settled, texts)).is_equal_to((None, False, ["1"]))

    def test_an_installer_folder_is_found_in_any_case_the_file_system_ignores(self):
        spelled = os.path.join("project", "Site-Packages", "helper.py")
        assert_that(_inline._installed(spelled)).is_equal_to(os.path.normcase("A") == "a")

    @pytest.mark.parametrize("folder", ["site-packages", "dist-packages"])
    def test_a_call_in_an_installed_package_is_never_rewritten(self, tmp_path, folder):
        helper = tmp_path / folder / "helper.py"
        helper.parent.mkdir()
        helper.write_text(
            "def held(value, assert_that):\n"
            "    assert_that(value).matches_inline({'a': 1})\n"
            "def recorded(value, assert_that):\n"
            "    assert_that(value).matches_inline()\n",
            encoding="utf-8",
        )
        namespace = {}
        exec(compile(helper.read_text(encoding="utf-8"), str(helper), "exec"), namespace)
        namespace["held"]({"a": 1}, assert_that)
        with pytest.raises(RuntimeError) as refusal:
            namespace["recorded"]({"a": 1}, assert_that)
        assert_that(str(refusal.value)).is_equal_to(
            f"update mode does not rewrite {helper}, a file of an installed package:"
            " call matches_inline() from the test itself"
        )
        assert_that(_inline._SEEN).is_empty()
        assert_that(helper.read_text(encoding="utf-8")).contains("matches_inline()\n")

    @pytest.mark.skipif(sys.version_info >= (3, 11), reason="from 3.11 the call is found and refused as unpacked")
    def test_below_3_11_a_double_star_call_is_refused_found_or_not(self):
        # executing finds it on Linux and not on Windows, with the same versions of both packages
        refused = r"its value through \*\*, may not be found|its expected value is passed through unpacking"
        with pytest.raises((RuntimeError, TypeError), match=refused):
            assert_that({"a": 2}).matches_inline(**_EXPECTED_BY_NAME)
        assert_that(_inline._SEEN).is_empty()


class TestNotRecordsNothing:
    """Under `not_` the verdict is inverted: a literal written there is the value it is asked to differ from."""

    @pytest.fixture(autouse=True)
    def _recording(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})

    def test_an_empty_one_is_refused(self):
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).not_.matches_inline()
        assert_that(failure.value._outcome.message).is_equal_to(
            "inline snapshot is empty, and not_ cannot record one; record it without not_"
        )
        assert_that(_inline._SEEN).is_empty()

    def test_a_stale_one_is_compared_and_kept(self):
        assert_that(2).not_.matches_inline(1)
        assert_that(_inline._SEEN).is_empty()


class TestAPlaceholderHoldsBeforeAnythingIsRecorded:
    """A value whose placeholder fails is not a value to record: the next run would fail on it."""

    @pytest.fixture(autouse=True)
    def _recording(self, monkeypatch):
        monkeypatch.setattr(_snap, "_UPDATE_ALL", True)
        monkeypatch.setattr(_inline, "_SEEN", {})

    def test_a_create_fails_on_it(self):
        with pytest.raises(AssertionFailure, match="placeholder <id>"):
            assert_that({"id": "x"}).matches_inline(placeholders={"id": match.is_uuid()})
        assert_that(_inline._SEEN).is_empty()

    def test_an_update_fails_on_it(self):
        with pytest.raises(AssertionFailure, match="placeholder <id>"):
            assert_that({"id": "x", "n": 2}).matches_inline({"id": 0, "n": 1}, placeholders={"id": match.is_uuid()})
        assert_that(_inline._SEEN).is_empty()

    def test_in_a_soft_block_neither_is_recorded(self):
        with pytest.raises(AssertionError, match="placeholder <id>"), soft_assertions():
            assert_that({"id": "x"}).matches_inline(placeholders={"id": match.is_uuid()})
            assert_that({"id": "x", "n": 2}).matches_inline({"id": 0, "n": 1}, placeholders={"id": match.is_uuid()})
        assert_that(_inline._SEEN).is_empty()


def _run_of(text, value, stale, accepts):
    """A run whose comparison *accepts* is asked about the candidate alone."""
    return _inline._Run(text, stale, value, lambda _value, candidate: accepts(candidate), "d")


class TestOneLiteralPerCall:
    """Every run of one call has to take the literal written there, or nothing is written."""

    def test_the_first_literal_every_run_takes_is_written(self):
        runs = [
            _run_of("{'id': 1, 'n': 2}", {"id": 1, "n": 2}, True, lambda candidate: candidate["n"] == 2),
            _run_of("{'id': 2, 'n': 2}", {"id": 2, "n": 2}, True, lambda candidate: candidate["n"] == 2),
        ]
        assert_that(_inline._settled(runs)).is_equal_to(("{'id': 1, 'n': 2}", True))

    def test_a_run_that_matched_the_old_literal_has_a_say(self):
        runs = [
            _run_of("1", 1, False, lambda candidate: candidate == 1),
            _run_of("2", 2, True, lambda candidate: candidate == 2),
        ]
        assert_that(_inline._settled(runs)).is_equal_to((None, False))

    def test_a_comparison_that_raises_takes_nothing(self):
        def raising(candidate):
            raise RuntimeError("a comparator of the caller's")

        runs = [_run_of("1", 1, True, lambda candidate: True), _run_of("2", 2, True, raising)]
        assert_that(_inline._settled(runs)).is_equal_to((None, False))

    def test_the_run_that_asked_for_the_literal_is_asked_too(self):
        runs = [_run_of("1", 1, True, lambda candidate: False)]
        assert_that(_inline._settled(runs)).is_equal_to((None, False))

    def test_each_run_is_asked_about_its_own_value(self):
        def own(value, candidate):
            return value == candidate

        runs = [_inline._Run("1", True, 1, own, "d"), _inline._Run("1", False, 2, own, "d")]
        assert_that(_inline._settled(runs)).is_equal_to((None, False))

    def test_nothing_stale_writes_nothing(self):
        assert_that(_inline._settled([_run_of("1", 1, False, lambda candidate: True)])).is_equal_to((None, True))


class TestWhatTheControllerWrites:
    """Rows from several processes about one call, merged where the edits are applied."""

    @staticmethod
    def _file(tmp_path, body="at().matches_inline()\n"):
        target = tmp_path / "rows.py"
        target.write_text(body, encoding="utf-8", newline="")
        return target

    def test_two_workers_that_settled_alike_write_once(self, tmp_path):
        target = self._file(tmp_path)
        row = _written(str(target), 20, 20, "1")
        assert_that(_inline.apply_inline_records([row, row], str(tmp_path))).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline(1)\n")

    def test_a_call_no_run_asked_to_rewrite_is_left_alone(self, tmp_path):
        target = self._file(tmp_path, "at().matches_inline(1)\n")
        assert_that(
            _inline.apply_inline_records(
                [(str(target), 20, 21, None, True, ["1"], _now(str(target)), "1")], str(tmp_path)
            )
        ).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline(1)\n")

    def test_a_worker_that_saw_the_written_literal_agrees(self, tmp_path):
        target = self._file(tmp_path)
        rows = [_written(str(target), 20, 20, "1"), (str(target), 20, 20, None, True, ["1"], _now(str(target)), "1")]
        assert_that(_inline.apply_inline_records(rows, str(tmp_path))).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline(1)\n")

    @pytest.mark.parametrize(
        "other", [("2", True, ["2"]), (None, True, ["2"])], ids=["settled-otherwise", "saw-another"]
    )
    def test_workers_that_disagree_write_nothing(self, tmp_path, other):
        target = self._file(tmp_path)
        rows = [_written(str(target), 20, 20, "1"), (str(target), 20, 20, *other, _now(str(target)), other[0])]
        problems = _inline.apply_inline_records(rows, str(tmp_path))
        assert_that(problems).is_equal_to(
            [
                f"{target}:1: matches_inline() was not settled alike in every xdist worker, so nothing was"
                " written: <1>, <2>. Whether one literal matches every case depends on the call's comparison"
                " options, which only the process that ran a case can ask: record it with -n 0"
            ]
        )
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline()\n")

    def test_a_call_no_literal_settles_writes_nothing_and_says_so(self, tmp_path):
        target = self._file(tmp_path, "x = 1\nat().matches_inline()\n")
        row = (str(target), 26, 26, None, False, ["1", "2", "3", "4", "5", None], _now(str(target)), None)
        problems = _inline.apply_inline_records([row], str(tmp_path))
        assert_that(problems).is_equal_to(
            [
                f"{target}:2: matches_inline() saw values no one literal matches, so nothing was written:"
                " <1>, <2>, <3>, <4> and 1 more. One literal stands for every case that reaches the call: give each"
                " case a call of its own, or use snapshot()"
            ]
        )
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("x = 1\nat().matches_inline()\n")

    def test_a_rewrite_that_would_not_parse_is_not_written(self, tmp_path):
        target = self._file(tmp_path)
        problems = _inline.apply_inline_records([_written(str(target), 20, 20, "{")], str(tmp_path))
        assert_that(problems).is_length(1)
        assert_that(problems[0]).starts_with(f"{target}: the recorded literals would not parse (")
        assert_that(problems[0]).ends_with("), so nothing was written")
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline()\n")

    def test_the_new_whole_second_is_past_the_old_one(self, tmp_path):
        target = self._file(tmp_path, "at().matches_inline(0)\n")
        ahead = time.time_ns() + 100_000_000_000
        os.utime(target, ns=(ahead, ahead))
        assert_that(_inline.apply_inline_records([_written(str(target), 20, 21, "1")], str(tmp_path))).is_empty()
        # a cached `.pyc` is keyed on the whole second and the size, and this rewrite keeps the size
        assert_that(os.stat(target).st_mtime_ns).is_equal_to((ahead // 1_000_000_000 + 1) * 1_000_000_000)

    def test_a_rewrite_seconds_later_keeps_its_own_time(self, tmp_path):
        target = self._file(tmp_path, "at().matches_inline(0)\n")
        behind = time.time_ns() - 100_000_000_000
        os.utime(target, ns=(behind, behind))
        assert_that(_inline.apply_inline_records([_written(str(target), 20, 21, "1")], str(tmp_path))).is_empty()
        assert_that(os.stat(target).st_mtime_ns).is_greater_than(behind + 50_000_000_000)

    def test_a_literal_its_own_comparison_never_passes_is_not_written_and_says_why(self, tmp_path):
        target = self._file(tmp_path)
        problems = _inline.apply_inline_records(
            [(str(target), 20, 20, None, False, ["1"], _now(str(target)), None)], str(tmp_path)
        )
        assert_that(problems).is_equal_to(
            [
                f"{target}:1: matches_inline() would not pass against the literal it would write, <1>, under its own"
                " comparison options, so nothing was written: look at the comparators or the tolerance it is given"
            ]
        )

    def test_a_file_outside_the_rootdir_is_not_written(self, tmp_path):
        target = self._file(tmp_path)
        (tmp_path / "project").mkdir()
        problems = _inline.apply_inline_records([_written(str(target), 20, 20, "1")], str(tmp_path / "project"))
        assert_that(problems).is_equal_to(
            [
                f"{target}: outside the rootdir {tmp_path / 'project'}, so nothing was written:"
                " update mode writes only there"
            ]
        )
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline()\n")

    def test_a_file_changed_since_its_calls_were_located_is_not_written(self, tmp_path):
        target = self._file(tmp_path)
        row = _written(str(target), 20, 20, "1")
        target.write_text("x = 1\nat().matches_inline()\n", encoding="utf-8", newline="")
        problems = _inline.apply_inline_records([row], str(tmp_path))
        assert_that(problems).is_equal_to(
            [
                f"{target}: changed while the run went on, so the places recorded in it no longer hold the calls they"
                " were taken from, and nothing was written"
            ]
        )
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("x = 1\nat().matches_inline()\n")

    def test_a_file_without_a_final_newline_is_the_text_its_calls_were_located_in(self, tmp_path):
        target = self._file(tmp_path, "at().matches_inline()")
        located = [_inline._digest("at().matches_inline()\n")]
        assert_that(
            _inline.apply_inline_records([_written(str(target), 20, 20, "1", located)], str(tmp_path))
        ).is_empty()
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline(1)")

    def test_a_file_in_another_encoding_is_written_in_it(self, tmp_path):
        target = tmp_path / "latin.py"
        target.write_bytes("# -*- coding: latin-1 -*-\n# café\nat().matches_inline()\n".encode("latin-1"))
        insert_at = len("# -*- coding: latin-1 -*-\n# café\nat().matches_inline(")
        problems = _inline.apply_inline_records([_written(str(target), insert_at, insert_at, "'é'")], str(tmp_path))
        assert_that(problems).is_empty()
        assert_that(target.read_bytes()).is_equal_to(
            "# -*- coding: latin-1 -*-\n# café\nat().matches_inline('é')\n".encode("latin-1")
        )

    def test_a_literal_the_file_s_encoding_cannot_hold_is_not_written(self, tmp_path):
        target = tmp_path / "latin.py"
        written = "# -*- coding: latin-1 -*-\nat().matches_inline()\n".encode("latin-1")
        target.write_bytes(written)
        insert_at = len("# -*- coding: latin-1 -*-\nat().matches_inline(")
        problems = _inline.apply_inline_records([_written(str(target), insert_at, insert_at, "'ключ'")], str(tmp_path))
        assert_that(problems).is_length(1)
        assert_that(problems[0]).starts_with(f"{target}: a recorded literal cannot be written in the file's encoding (")
        assert_that(target.read_bytes()).is_equal_to(written)

    def test_a_file_it_cannot_read_is_named(self, tmp_path):
        target = tmp_path / "cookie.py"
        target.write_bytes(b"# -*- coding: no-such-codec -*-\nat().matches_inline()\n")
        problems = _inline.apply_inline_records([(str(target), 20, 20, "1", True, ["1"], ["d"], "1")], str(tmp_path))
        assert_that(problems).is_length(1)
        assert_that(problems[0]).starts_with(f"{target}: could not be read (")
        assert_that(problems[0]).ends_with("), so nothing was written")

    def test_a_worker_whose_own_comparison_turns_the_literal_down_stops_it(self, tmp_path):
        target = self._file(tmp_path)
        rows = [_written(str(target), 20, 20, "1"), (str(target), 20, 20, None, True, ["1"], _now(str(target)), None)]
        problems = _inline.apply_inline_records(rows, str(tmp_path))
        assert_that(problems).is_length(1)
        assert_that(problems[0]).contains("was not settled alike in every xdist worker")
        assert_that(target.read_text(encoding="utf-8")).is_equal_to("at().matches_inline()\n")

    def test_a_worker_offers_only_the_one_literal_all_its_runs_take(self):
        def takes_one(value, candidate):
            return candidate == 1

        _inline._SEEN.clear()
        _inline._SEEN[("f.py", 5, 6)] = [_inline._Run("1", False, 1, takes_one, "d")]
        _inline._SEEN[("f.py", 7, 8)] = [_inline._Run("2", False, 2, takes_one, "d")]
        _inline._SEEN[("f.py", 9, 10)] = [
            _inline._Run("1", False, 1, takes_one, "d"),
            _inline._Run("3", False, 3, takes_one, "d"),
        ]
        assert_that([row[7] for row in _inline.shipped()]).is_equal_to(["1", None, None])

    def test_a_write_that_fails_is_named(self, tmp_path, monkeypatch):
        target = self._file(tmp_path, "at().matches_inline(0)\n")
        ahead = time.time_ns() + 100_000_000_000
        os.utime(target, ns=(ahead, ahead))

        def refused(*args, **kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(_inline.os, "utime", refused)
        problems = _inline.apply_inline_records([_written(str(target), 20, 21, "1")], str(tmp_path))
        assert_that(problems).is_equal_to(
            [f"{target}: could not be written (denied), so it may hold part of the rewrite: check it"]
        )

    def test_a_file_with_nothing_to_write_or_report_is_not_opened(self, tmp_path):
        missing = tmp_path / "gone.py"
        assert_that(
            _inline.apply_inline_records([(str(missing), 1, 2, None, True, ["1"], ["d"], None)], str(tmp_path))
        ).is_empty()


_CHECKOUT = str(pathlib.Path(_inline.__file__).resolve().parents[1])

_SHAPES = {
    "keywords": (
        'assert_that({"id": 7, "n": 1}).matches_inline(ignore="id")',
        "matches_inline({'id': 7, 'n': 1}, ignore=\"id\")",
    ),
    "tolerance": ("assert_that(1.0).matches_inline(tolerance=0.1)", "matches_inline(1.0, tolerance=0.1)"),
    "trailing_comma": (
        'assert_that({"id": 7}).matches_inline(ignore="id",)',
        "matches_inline({'id': 7}, ignore=\"id\",)",
    ),
    "comment": ("assert_that([1]).matches_inline(  # record me\n    )", "matches_inline([1]  # record me"),
    "expected_keyword": (
        'assert_that({"a": 2}).matches_inline(expected={"a": 1})',
        "matches_inline(expected={'a': 2})",
    ),
    "positional_and_keyword": (
        'assert_that({"a": 2, "n": 1}).matches_inline({"a": 1, "n": 1}, ignore="n")',
        "matches_inline({'a': 2, 'n': 1}, ignore=\"n\")",
    ),
    "grouped_callee": ("(assert_that(1).matches_inline)()", "(assert_that(1).matches_inline)(1)"),
    "check": (
        "checked = assert_that(1).check().matches_inline()\n    assert checked.passed",
        "check().matches_inline(1)",
    ),
    "soft": ("with soft_assertions():\n        assert_that(1).matches_inline()", "assert_that(1).matches_inline(1)"),
    "warn": ("assert_warn(1).matches_inline()", "assert_warn(1).matches_inline(1)"),
    "ignored_field_across_cases": (
        "for case in (1, 2):\n        assert_that({'id': case, 'n': 2}).matches_inline({'id': 0, 'n': 1}, ignore='id')",
        "matches_inline({'id': 1, 'n': 2}, ignore='id')",
    ),
}


class TestARealUpdateRun:
    """pytest itself over a test file: recorded under update mode, then run again as it was written.

    The rewrite lands only at the end of a real session, and only a real next run parses and imports it,
    cached bytecode included.  The package's own files are compared before and after each run: through
    `check()` and `not_` a literal used to be written into them.
    """

    @staticmethod
    def _run(folder, *options):
        return subprocess.run(
            # this interpreter, not `uv run`: the child starts outside the project
            [
                *(sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"),
                *("--rootdir", str(folder), *options, "test_case.py"),
            ],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=180,
            env={**os.environ, "PYTHONPATH": _CHECKOUT, "ASSERTPY_SNAPSHOT_CI": "0"},
        )

    @staticmethod
    def _package():
        return {path.name: path.read_bytes() for path in pathlib.Path(_CHECKOUT, "assertpy").glob("*.py")}

    def _recorded(self, tmp_path, tests):
        (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        source = "from assertpy import assert_that, assert_warn, soft_assertions\n" + "".join(
            f"\n\ndef test_{name}():\n    {body}\n" for name, body in tests.items()
        )
        (tmp_path / "test_case.py").write_text(source, encoding="utf-8", newline="")
        package = self._package()
        update = self._run(tmp_path, "--assertpy-snapshot-update")
        assert_that(self._package()).described_as("the package after the update run").is_equal_to(package)
        return update, (tmp_path / "test_case.py").read_text(encoding="utf-8"), source

    def test_every_shape_records_a_call_that_parses_and_passes_the_next_run(self, tmp_path):
        update, written, _ = self._recorded(tmp_path, {name: body for name, (body, _) in _SHAPES.items()})
        assert_that(update.returncode).described_as(update.stdout + update.stderr).is_equal_to(0)
        ast.parse(written)
        assert_that(written).contains(*(fragment for _, fragment in _SHAPES.values()))
        rerun = self._run(tmp_path)
        assert_that(rerun.returncode).described_as(rerun.stdout + rerun.stderr).is_equal_to(0)
        assert_that(rerun.stdout).contains(f"{len(_SHAPES)} passed")

    def test_a_same_size_rewrite_is_read_by_the_next_run(self, tmp_path):
        update, written, _ = self._recorded(tmp_path, {"same_size": "assert_that(1).matches_inline(0)"})
        assert_that(update.returncode).described_as(update.stdout + update.stderr).is_equal_to(0)
        assert_that(written).contains("matches_inline(1)")
        rerun = self._run(tmp_path)
        assert_that(rerun.returncode).described_as(rerun.stdout + rerun.stderr).is_equal_to(0)

    def test_a_call_that_sees_two_values_is_left_as_it_was_and_fails_the_run(self, tmp_path):
        tests = {
            "created": "for case in (1, 2):\n        assert_that(case).matches_inline()",
            "one_matches": "for case in (1, 2):\n        assert_that(case).matches_inline(1)",
        }
        update, written, source = self._recorded(tmp_path, tests)
        assert_that(written).is_equal_to(source)
        assert_that(update.returncode).is_equal_to(1)
        errors = [line for line in update.stdout.splitlines() if line.startswith("ERROR: ")]
        assert_that(errors).is_length(2)
        assert_that(errors).all_satisfy(
            match.contains_string("saw values no one literal matches, so nothing was written")
        )

    def test_not_and_check_leave_the_package_alone(self, tmp_path):
        update, written, source = self._recorded(
            tmp_path,
            {"negated": "assert_that(1).not_.matches_inline()", "checked": "assert_that(1).check().matches_inline()"},
        )
        assert_that(update.stdout).contains("not_ cannot record one")
        assert_that(written).is_equal_to(source.replace("check().matches_inline()", "check().matches_inline(1)"))

    def test_every_kind_written_is_updated_and_read_back(self, tmp_path):
        kinds = {
            "text": ("'a'", "'bc'"),
            "number": ("-1.5", "2"),
            "flag": ("True", "False"),
            "nothing": ("None", "1"),
            "listed": ("[1, 2]", "[1, 3, 4]"),
            "paired": ("(1, 2)", "(1, 2, 3)"),
            "keyed": ("{'a': 1}", "{'a': 22}"),
            "set": ("{1, 2}", "{1, 3, 4}"),
            "empty_set": ("set()", "{3}"),
            "frozen": ("frozenset({1})", "frozenset({2, 3})"),
            "frozen_inside": ("[frozenset({1})]", "[frozenset({1, 2})]"),
            "frozen_keyed": ("{'k': frozenset({1})}", "{'k': frozenset()}"),
        }
        tests = {
            name: f"value = {first}\n    assert_that(value).matches_inline()" for name, (first, _) in kinds.items()
        }
        created, written, _ = self._recorded(tmp_path, tests)
        assert_that(created.returncode).described_as(created.stdout + created.stderr).is_equal_to(0)
        for first, second in kinds.values():
            assert_that(written).contains(f"matches_inline({first})")
            written = written.replace(f"value = {first}\n", f"value = {second}\n")
        (tmp_path / "test_case.py").write_text(written, encoding="utf-8", newline="")
        updated = self._run(tmp_path, "--assertpy-snapshot-update")
        assert_that(updated.returncode).described_as(updated.stdout + updated.stderr).is_equal_to(0)
        rewritten = (tmp_path / "test_case.py").read_text(encoding="utf-8")
        assert_that(rewritten).contains(*(f"matches_inline({second})" for _, second in kinds.values()))
        rerun = self._run(tmp_path)
        assert_that(rerun.returncode).described_as(rerun.stdout + rerun.stderr).is_equal_to(0)
        assert_that(rerun.stdout).contains(f"{len(kinds)} passed")


_SCALARS = st.one_of(
    st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=8)
)
_LITERALS = st.recursive(
    _SCALARS,
    lambda inner: st.one_of(
        st.lists(inner, max_size=4),
        st.tuples(inner, inner),
        st.dictionaries(st.one_of(st.text(max_size=6), st.integers()), inner, max_size=4),
    ),
    max_leaves=12,
)
_HASHABLE = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=6))
_WITH_SETS = st.recursive(
    _SCALARS | st.sets(_HASHABLE, max_size=4) | st.frozensets(_HASHABLE, max_size=4),
    lambda inner: st.one_of(st.lists(inner, max_size=4), st.dictionaries(st.text(max_size=6), inner, max_size=4)),
    max_leaves=12,
)


class TestARecordedLiteralReadsBack:
    @settings(deadline=None)
    @example(value={"user": {"id": 1, "name": "Alice", "roles": ["admin", "editor", "viewer"]}}, column=80)
    @given(value=_LITERALS, column=st.integers(0, 110))
    def test_whatever_its_column_it_parses_in_a_call_as_the_value_it_was(self, value, column):
        text = _inline._format_literal(value, column)
        assert_that(_inline.is_literalable(value)).is_true()
        assert_that(ast.literal_eval(text)).is_equal_to(value)
        call = ast.parse(f"at().matches_inline({text}, ignore='id')")
        assert_that(ast.literal_eval(call.body[0].value.args[0])).is_equal_to(value)

    @settings(deadline=None)
    @example(value=[frozenset({1, 2}), set(), {"a": {0.5}}], column=0)
    @given(value=_WITH_SETS, column=st.integers(0, 110))
    def test_whatever_it_holds_it_is_built_back_as_the_value_it_was(self, value, column):
        assert_that(_inline.is_literalable(value)).is_true()
        assert_that(_inline._built(_inline._format_literal(value, column))).is_equal_to(value)
