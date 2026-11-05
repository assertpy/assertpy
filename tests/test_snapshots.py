import collections
import contextlib
import datetime
import decimal
import enum
import functools
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import uuid
import warnings

import pytest

from assertpy import (
    AssertionFailure,
    SnapshotCreatedWarning,
    SnapshotUpdatedWarning,
    _snapshot_codec,
    assert_that,
    assert_warn,
    fail,
    match,
    register_snapshot_serializer,
    soft_assertions,
)
from assertpy import snapshot as _snapshot
from assertpy.snapshot import _ci_mode_enabled, _file_lock, _load, _save


class Color(enum.Enum):
    RED = 1
    GREEN = 2


# first pass re-captures every snapshot; the capture warnings are pinned in TestSnapshotCreatedWarning
@pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
@pytest.mark.parametrize("count", [1, 2])
def test_snapshot_roundtrip_all_types(count):
    # test runs twice
    if count == 1:
        # on first pass, delete old snapshots...so they are re-created and saved
        if os.path.exists("__snapshots"):
            shutil.rmtree("__snapshots")
    if count == 2:
        # on second pass, snapshots are loaded and checked
        assert_that("__snapshots").exists().is_directory()

    assert_that(None).snapshot()

    assert_that(True).snapshot()
    assert_that(False).snapshot()

    assert_that(123).snapshot()
    assert_that(-456).snapshot()

    assert_that(123.456).snapshot()
    assert_that(-987.654).snapshot()

    assert_that("").snapshot()
    assert_that("foo").snapshot()

    assert_that([1, 2, 3]).snapshot()

    assert_that(["a", "b", "c"]).snapshot()

    assert_that([[1, 2, 3], ["a", "b", "c"]]).snapshot()

    assert_that({"a", "b", "c"}).snapshot()

    assert_that({"a": 1, "b": 2, "c": 3}).snapshot()

    assert_that({"a": {"x": 1}, "b": {"y": 2}, "c": {"z": 3}}).snapshot()

    assert_that({"a": [1, 2], "b": [3, 4], "c": [5, 6]}).snapshot()

    assert_that({"a": {1, 2}, "b": {3, 4}, "c": {5, 6}}).snapshot()

    assert_that({"a": {"b": {"c": {"x": {"y": {"z": 1}}}}}}).snapshot()

    assert_that(collections.OrderedDict([("a", 1), ("c", 3), ("b", 2)])).snapshot()

    assert_that(datetime.datetime(2000, 11, 22, 3, 44, 55)).snapshot()

    assert_that(1 + 2j).snapshot()

    assert_that({"custom": "id"}).snapshot(id="mycustomid")

    assert_that({"custom": "path"}).snapshot(path="mycustompath")

    foo = Foo()
    foo2 = Foo(
        {
            "a": 1,
            "b": [1, 2, 3],
            "c": {"x": 1, "y": 2, "z": 3},
            "d": {-1, 2, -3},
            "e": datetime.datetime(2000, 11, 22, 3, 44, 55),
            "f": -1 - 2j,
        }
    )
    bar = Bar()

    assert_that(foo.x).is_equal_to(0)
    assert_that(foo.y).is_equal_to(1)

    assert_that(foo2.x["a"]).is_equal_to(1)
    assert_that(foo2.x["b"]).is_equal_to([1, 2, 3])
    assert_that(foo2.y).is_equal_to(1)

    assert_that(bar.x).is_equal_to(0)
    assert_that(bar.y).is_equal_to(1)

    assert_that(foo).snapshot()
    assert_that(foo2).snapshot()

    try:
        assert_that(bar).snapshot()
        if count == 2:
            fail("should have raised error")
    except AssertionError as ex:
        assert_that(str(ex)).contains("Expected ").contains(" to be equal to ").contains("test_snapshots.Bar").contains(
            ", but was not."
        )

    assert_that(
        {
            "none": None,
            "truthy": True,
            "falsy": False,
            "int": 123,
            "intneg": -456,
            "float": 123.456,
            "floatneg": -987.654,
            "empty": "",
            "str": "foo",
            "list": [1, 2, 3],
            "liststr": ["a", "b", "c"],
            "listmix": [1, "a", [2, 4, 6], {1, 2, 3}, 3 + 6j],
            "set": {1, 2, 3},
            "dict": {"a": 1, "b": 2, "c": 3},
            "time": datetime.datetime(2000, 11, 22, 3, 44, 55),
            "complex": 1 + 2j,
            "foo": foo,
            "foo2": foo2,
        }
    ).snapshot()

    assert_that({"__type__": "foo", "__data__": "bar"}).snapshot()


class TestSnapshotCreatedWarning:
    def test_first_capture_warns_and_second_run_compares(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning, match="captured the value instead of comparing"):
            assert_that({"a": 1}).snapshot(id="warn-first", path=str(tmp_path))
        # the suite runs with warnings-as-errors, so a silent pass here proves no second warning
        assert_that({"a": 1}).snapshot(id="warn-first", path=str(tmp_path))

    def test_new_line_in_existing_file_warns(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(path=str(tmp_path))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(2).snapshot(path=str(tmp_path))

    def test_same_line_second_iteration_compares(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            for value in [7, 7]:
                assert_that(value).snapshot(path=str(tmp_path))

    def test_same_line_second_iteration_fails_on_drift(self, tmp_path):
        values = iter([7, 8])
        with pytest.warns(SnapshotCreatedWarning), pytest.raises(AssertionError):
            for _ in range(2):
                assert_that(next(values)).snapshot(path=str(tmp_path))


class TestSharedKeyHint:
    """Reuse inside one test raises no warning, so the failure it causes has to explain itself."""

    def test_a_second_call_in_one_test_says_why_the_values_are_compared(self, tmp_path):
        def check(value):
            assert_that(value).snapshot(id="helper", path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            check({"user": "alice"})
        with pytest.raises(AssertionError) as failure:
            check({"user": "bob"})
        assert_that(str(failure.value)).contains("reached").contains("more than once")
        assert_that(str(failure.value)).contains("earlier call in the same test").contains("snapshot(id=...)")

    def test_a_default_key_names_its_line(self, tmp_path):
        values = iter([7, 8])
        with pytest.warns(SnapshotCreatedWarning), pytest.raises(AssertionError) as failure:
            for _ in range(2):
                assert_that(next(values)).snapshot(path=str(tmp_path))
        assert_that(str(failure.value)).matches(r"reached <.*snap-test_snapshots\.json::\d+> more than once")

    def test_a_mismatch_still_says_what_was_asked(self, tmp_path):
        """The failure is rebuilt around a new message, and the rebuild used to drop the requirement."""
        _save(str(tmp_path / "snap-asked.json"), {"a": 1}, keyed=False)
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 2}).snapshot(id="asked", path=str(tmp_path))
        assert_that(failure.value.requirement.operation).is_equal_to("snapshot")

    def test_a_first_and_only_call_says_nothing(self, tmp_path):
        _save(str(tmp_path / "snap-once.json"), {"a": 1}, keyed=False)
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 2}).snapshot(id="once", path=str(tmp_path))
        assert_that(str(failure.value)).does_not_contain("more than once")

    def test_the_hint_is_empty_when_the_key_was_reached_once(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_SCOPE_REPEATS", set())
        assert_that(_snapshot._shared_key_hint("snap-mod.json", "17")).is_equal_to("")

    def test_the_hint_spells_out_the_repeat(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_SCOPE_REPEATS", {("snap-mod.json", "17")})
        assert_that(_snapshot._shared_key_hint("snap-mod.json", "17")).is_equal_to(
            " This test reached <snap-mod.json::17> more than once, so the value above was compared"
            " against what an earlier call in the same test stored."
            " Give each call its own snapshot(id=...)."
        )

    def test_the_scope_is_dropped_when_the_test_changes(self, monkeypatch, tmp_path):
        _snapshot._record_access(str(tmp_path / "s.json"), "9", "s:9")
        _snapshot._record_access(str(tmp_path / "s.json"), "9", "s:9")
        assert_that(_snapshot._SCOPE_REPEATS).is_not_empty()
        monkeypatch.setattr(_snapshot, "_CURRENT_NODE", "test_mod.py::somewhere_else")
        _snapshot._record_access(str(tmp_path / "s.json"), "9", "s:9")
        assert_that(_snapshot._SCOPE_REPEATS).is_empty()


class TestSnapshotDatetimeMicroseconds:
    def test_microseconds_survive_the_roundtrip(self, tmp_path):
        timestamp = datetime.datetime(2026, 1, 1, 12, 0, 0, 123456)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(timestamp).snapshot(id="micro", path=str(tmp_path))
        assert_that(timestamp).snapshot(id="micro", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(timestamp.replace(microsecond=999999)).snapshot(id="micro", path=str(tmp_path))

    def test_zero_microseconds_keep_the_historical_format(self, tmp_path):
        timestamp = datetime.datetime(2000, 11, 22, 3, 44, 55)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(timestamp).snapshot(id="legacy", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-legacy.json").read_text())
        assert_that(raw["__data__"]).is_equal_to("2000-11-22 03:44:55")
        assert_that(timestamp).snapshot(id="legacy", path=str(tmp_path))


class TestSnapshotTypedCodec:
    def test_date_roundtrip(self, tmp_path):
        value = datetime.date(2026, 7, 4)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-date", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-date", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(datetime.date(2026, 7, 5)).snapshot(id="codec-date", path=str(tmp_path))

    def test_date_stored_as_iso_marker(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(datetime.date(2026, 7, 4)).snapshot(id="codec-date-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-date-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "date", "__data__": "2026-07-04"})

    def test_non_string_key_dict_roundtrip(self, tmp_path):
        value = {1: "a", 2: "b", None: "c", (3, 4): "d"}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-intkeys", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-intkeys", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({1: "a", 2: "CHANGED"}).snapshot(id="codec-intkeys", path=str(tmp_path))

    def test_marker_key_dict_is_not_mistaken_for_an_envelope(self, tmp_path):
        value = {"__type__": "date", "__data__": "not-a-date"}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-collide", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-collide", path=str(tmp_path))

    def test_normal_string_dict_stored_without_envelope(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1, "b": 2}).snapshot(id="codec-plain", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-plain.json").read_text())
        assert_that(raw).is_equal_to({"a": 1, "b": 2})

    def test_unknown_type_marker_decodes_as_is(self, tmp_path):
        snap = tmp_path / "snap-future.json"
        snap.write_text(json.dumps({"__type__": "future_type", "__data__": [1, 2]}))
        assert_that(_load(str(snap))).is_equal_to({"__type__": "future_type", "__data__": [1, 2]})

    def test_time_roundtrip(self, tmp_path):
        value = datetime.time(12, 34, 56, 789012)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-time", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-time", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(datetime.time(12, 34, 57)).snapshot(id="codec-time", path=str(tmp_path))

    def test_time_with_utc_offset_roundtrip(self, tmp_path):
        value = datetime.time(12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-time-tz", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-time-tz", path=str(tmp_path))

    def test_decimal_roundtrip(self, tmp_path):
        value = decimal.Decimal("1.10")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-decimal", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-decimal", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(decimal.Decimal("1.2")).snapshot(id="codec-decimal", path=str(tmp_path))

    def test_decimal_stored_as_exact_string(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(decimal.Decimal("1.10")).snapshot(id="codec-decimal-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-decimal-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "decimal", "__data__": "1.10"})

    def test_bytes_roundtrip(self, tmp_path):
        value = b"\x00\xffbinary"
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-bytes", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-bytes", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(b"other").snapshot(id="codec-bytes", path=str(tmp_path))

    def test_bytes_stored_base64(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(b"\x00\xff").snapshot(id="codec-bytes-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-codec-bytes-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "bytes", "__data__": "AP8="})

    def test_bytearray_compares_against_stored_bytes(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(bytearray(b"ab")).snapshot(id="codec-bytearray", path=str(tmp_path))
        assert_that(bytearray(b"ab")).snapshot(id="codec-bytearray", path=str(tmp_path))
        assert_that(b"ab").snapshot(id="codec-bytearray", path=str(tmp_path))

    def test_aware_datetime_roundtrip(self, tmp_path):
        zone = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(value + datetime.timedelta(hours=1)).snapshot(id="codec-aware", path=str(tmp_path))

    def test_aware_datetime_with_microseconds_roundtrip(self, tmp_path):
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-micro", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-micro", path=str(tmp_path))

    def test_negative_offset_datetime_roundtrip(self, tmp_path):
        zone = datetime.timezone(datetime.timedelta(hours=-5))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-neg", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-neg", path=str(tmp_path))

    def test_subminute_offset_datetime_roundtrip(self, tmp_path):
        zone = datetime.timezone(datetime.timedelta(minutes=5, seconds=30))
        value = datetime.datetime(2026, 7, 4, 10, 0, 0, tzinfo=zone)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-aware-subminute", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-aware-subminute", path=str(tmp_path))

    def test_nested_typed_values_roundtrip(self, tmp_path):
        value = {
            "day": datetime.date(2026, 7, 4),
            "at": datetime.time(9, 30),
            "price": decimal.Decimal("19.99"),
            "blob": b"\x01\x02",
        }
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="codec-nested", path=str(tmp_path))
        assert_that(value).snapshot(id="codec-nested", path=str(tmp_path))


class TestSnapshotCompareOptions:
    def test_ignore_volatile_field(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="opt-ignore", path=str(tmp_path))
        assert_that({"name": "Alice", "ts": 999}).snapshot(id="opt-ignore", path=str(tmp_path), ignore="ts")
        with pytest.raises(AssertionError):
            assert_that({"name": "Bob", "ts": 999}).snapshot(id="opt-ignore", path=str(tmp_path), ignore="ts")

    def test_first_capture_stores_full_value_despite_ignore(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="opt-full", path=str(tmp_path), ignore="ts")
        assert_that({"name": "Alice", "ts": 42}).snapshot(id="opt-full", path=str(tmp_path), ignore="ts")
        with pytest.raises(AssertionError):
            assert_that({"name": "Alice", "ts": 42}).snapshot(id="opt-full", path=str(tmp_path))

    def test_include_only_selected_keys(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1, "b": 2}).snapshot(id="opt-include", path=str(tmp_path))
        assert_that({"a": 1, "b": 999}).snapshot(id="opt-include", path=str(tmp_path), include="a")

    def test_nested_ignore_path(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"user": {"name": "Alice", "session": "s1"}}).snapshot(id="opt-nested", path=str(tmp_path))
        assert_that({"user": {"name": "Alice", "session": "s2"}}).snapshot(
            id="opt-nested", path=str(tmp_path), ignore=[("user", "session")]
        )

    def test_tolerance_absorbs_float_noise(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"price": 1.0}).snapshot(id="opt-tol", path=str(tmp_path))
        assert_that({"price": 1.0004}).snapshot(id="opt-tol", path=str(tmp_path), tolerance=0.001)
        with pytest.raises(AssertionError):
            assert_that({"price": 1.01}).snapshot(id="opt-tol", path=str(tmp_path), tolerance=0.001)

    def test_comparators_own_matching_fields(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice"}).snapshot(id="opt-cmp", path=str(tmp_path))
        assert_that({"name": "ALICE"}).snapshot(
            id="opt-cmp",
            path=str(tmp_path),
            comparators={"name": lambda actual, expected: actual.lower() == expected.lower()},
        )

    def test_bad_tolerance_fails_on_first_capture(self, tmp_path):
        with pytest.raises(TypeError, match="tolerance arg must be a real number"):
            assert_that({"a": 1}).snapshot(id="opt-bad-tol", path=str(tmp_path), tolerance="high")
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-opt-bad-tol.json"))).is_false()


class TestSnapshotUpdateMode:
    def test_stale_snapshot_updated_and_warns(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning, match="overwrote the stored value"):
            assert_that({"a": 2}).snapshot(id="upd", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        assert_that({"a": 2}).snapshot(id="upd", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({"a": 1}).snapshot(id="upd", path=str(tmp_path))

    def test_matching_snapshot_is_not_rewritten(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd-same", path=str(tmp_path))
        target = tmp_path / "snap-upd-same.json"
        stamp = os.stat(target).st_mtime_ns
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"a": 1}).snapshot(id="upd-same", path=str(tmp_path))
        assert_that(os.stat(target).st_mtime_ns).is_equal_to(stamp)

    def test_first_capture_in_update_mode_warns_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="upd-first", path=str(tmp_path))

    def test_lineno_subsnap_updates(self, tmp_path, monkeypatch):
        def snap(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap(7)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            snap(8)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        snap(8)
        with pytest.raises(AssertionError):
            snap(7)

    def test_update_preserves_sibling_subsnaps(self, tmp_path, monkeypatch):
        def snap_a(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        def snap_b(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap_a(1)
        with pytest.warns(SnapshotCreatedWarning):
            snap_b("keep")
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            snap_a(2)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        snap_a(2)
        snap_b("keep")

    def test_update_honors_ignore_option(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"name": "Alice", "ts": 1}).snapshot(id="upd-ign", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"name": "Alice", "ts": 999}).snapshot(id="upd-ign", path=str(tmp_path), ignore="ts")
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        with pytest.raises(AssertionError):
            assert_that({"name": "Alice", "ts": 999}).snapshot(id="upd-ign", path=str(tmp_path))

    def test_disabled_env_value_keeps_normal_failure(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(id="upd-off", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "0")
        with pytest.raises(AssertionError):
            assert_that(2).snapshot(id="upd-off", path=str(tmp_path))

    def test_update_inside_soft_assertions_collects_nothing(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(1).snapshot(id="upd-soft", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning), soft_assertions():
            assert_that(2).snapshot(id="upd-soft", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        assert_that(2).snapshot(id="upd-soft", path=str(tmp_path))


class TestSnapshotBuiltinCodecExtras:
    def test_uuid_roundtrip(self, tmp_path):
        value = uuid.uuid4()
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="uuid", path=str(tmp_path))
        assert_that(value).snapshot(id="uuid", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(uuid.uuid4()).snapshot(id="uuid", path=str(tmp_path))

    def test_uuid_stored_as_string(self, tmp_path):
        value = uuid.UUID("12345678-1234-5678-1234-567812345678")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="uuid-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-uuid-raw.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "uuid", "__data__": "12345678-1234-5678-1234-567812345678"})

    def test_enum_roundtrip(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(Color.RED).snapshot(id="enum", path=str(tmp_path))
        assert_that(Color.RED).snapshot(id="enum", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that(Color.GREEN).snapshot(id="enum", path=str(tmp_path))

    def test_enum_stored_by_value_and_class(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(Color.RED).snapshot(id="enum-raw", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-enum-raw.json").read_text())
        assert_that(raw["__type__"]).is_equal_to("enum")
        assert_that(raw["__data__"]).is_equal_to(1)
        assert_that(raw["__class__"]).is_equal_to("Color")

    def test_enum_unresolvable_module_returns_dict(self, tmp_path):
        payload = {"__type__": "enum", "__class__": "Nope", "__module__": "nonexistent_mod_xyz", "__data__": 1}
        snap_file = tmp_path / "snap-e.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)

    def test_enum_missing_class_returns_dict(self, tmp_path):
        payload = {"__type__": "enum", "__class__": "DoesNotExist", "__module__": "os", "__data__": 1}
        snap_file = tmp_path / "snap-e2.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)


class TestSnapshotSerializerRegistry:
    def test_custom_type_roundtrip(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c), tag="money")
        value = {"price": _Money(500)}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="ser-money", path=str(tmp_path))
        assert_that(value).snapshot(id="ser-money", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({"price": _Money(999)}).snapshot(id="ser-money", path=str(tmp_path))

    def test_stored_with_custom_marker_and_tag(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c), tag="money")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Money(7)).snapshot(id="ser-tag", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-tag.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "custom", "__tag__": "money", "__data__": 7})

    def test_default_tag_is_qualified_name(self):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c))
        assert_that(_snapshot._SERIALIZERS[0].tag).ends_with("._Money")

    def test_isinstance_matches_subclasses(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c), tag="money")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Cents(3)).snapshot(id="ser-sub", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-sub.json").read_text())
        assert_that(raw).is_equal_to({"__type__": "custom", "__tag__": "money", "__data__": 3})

    def test_last_registered_wins(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: "first", lambda d: _Money(0), tag="t1")
        register_snapshot_serializer(_Money, lambda model: "second", lambda d: _Money(0), tag="t2")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(_Money(0)).snapshot(id="ser-last", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-last.json").read_text())
        assert_that(raw["__tag__"]).is_equal_to("t2")

    def test_unknown_custom_tag_returns_marker(self, tmp_path):
        payload = {"__type__": "custom", "__tag__": "not-registered", "__data__": 5}
        snap_file = tmp_path / "snap-unk.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)

    def test_encode_skips_non_matching_serializer(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c), tag="money")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({1, 2, 3}).snapshot(id="ser-skip", path=str(tmp_path))
        raw = json.loads((tmp_path / "snap-ser-skip.json").read_text())
        assert_that(raw["__type__"]).is_equal_to("set")

    def test_decode_skips_non_matching_tag(self, tmp_path):
        register_snapshot_serializer(_Money, lambda model: model.cents, lambda c: _Money(c), tag="money")
        payload = {"__type__": "custom", "__tag__": "other-tag", "__data__": 5}
        snap_file = tmp_path / "snap-tagskip.json"
        snap_file.write_text(json.dumps(payload))
        assert_that(_load(str(snap_file))).is_equal_to(payload)

    def test_register_rejects_non_type(self):
        with pytest.raises(TypeError, match="cls must be a type"):
            register_snapshot_serializer("not a type", str, str)

    def test_register_rejects_non_callable_encode(self):
        with pytest.raises(TypeError, match="must be callable"):
            register_snapshot_serializer(int, "nope", str)

    def test_register_rejects_non_callable_decode(self):
        with pytest.raises(TypeError, match="must be callable"):
            register_snapshot_serializer(int, str, "nope")


class _Money:
    def __init__(self, cents):
        self.cents = cents

    def __eq__(self, other):
        return isinstance(other, _Money) and other.cents == self.cents


class _Cents(_Money):
    pass


_UUID_A = "550e8400-e29b-41d4-a716-446655440000"
_UUID_B = "11111111-2222-3333-4444-555555555555"


class TestSnapshotOrphanDetection:
    def _write(self, tmp_path, name, data):
        snap_file = tmp_path / f"snap-{name}.json"
        snap_file.write_text(json.dumps(data))
        return str(snap_file)

    def test_sub_key_orphan_in_touched_file(self, tmp_path):
        snapname = self._write(tmp_path, "mod", {"10": 1, "20": 2, "30": 3})
        sub, whole = _snapshot._find_orphans({(snapname, "10"), (snapname, "20")})
        assert_that(sub).is_equal_to([(snapname, "30")])
        assert_that(whole).is_empty()

    def test_whole_file_orphan_untouched(self, tmp_path):
        live = self._write(tmp_path, "live", {"10": 1})
        dead = self._write(tmp_path, "dead", {"10": 1})
        sub, whole = _snapshot._find_orphans({(live, "10")})
        assert_that(whole).is_equal_to([dead])
        assert_that(sub).is_empty()

    def test_custom_id_touched_not_orphan(self, tmp_path):
        snapname = self._write(tmp_path, "custom", {"any": "value"})
        sub, whole = _snapshot._find_orphans({(snapname, "")})
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_missing_directory_skipped(self, tmp_path):
        snapname = str(tmp_path / "gone" / "snap-x.json")
        sub, whole = _snapshot._find_orphans({(snapname, "10")})
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_non_snapshot_files_ignored(self, tmp_path):
        snapname = self._write(tmp_path, "mod", {"10": 1})
        (tmp_path / "readme.txt").write_text("x")
        sub, whole = _snapshot._find_orphans({(snapname, "10")})
        assert_that(sub).is_empty()
        assert_that(whole).is_empty()

    def test_the_whole_directory_is_scanned_past_every_kind_of_skip(self, tmp_path):
        """One run touching two directories, one of them gone, and a live directory holding in listing
        order a non-snapshot file, a plain .json, a dead snapshot, a live custom-id one, and a live
        default-id one with a stale key."""
        gone = str(tmp_path / "aaa_gone" / "snap-x.json")
        live_dir = tmp_path / "bbb_real"
        live_dir.mkdir()
        (live_dir / "aaa.txt").write_text("x")
        (live_dir / "other.json").write_text("{}")
        dead = self._write(live_dir, "a-dead", {"10": 1})
        custom = self._write(live_dir, "b-custom", {"any": "value"})
        live = self._write(live_dir, "c-live", {"10": 1, "20": 2})
        sub, whole = _snapshot._find_orphans({(gone, "10"), (custom, ""), (live, "10")})
        assert_that(whole).is_equal_to([dead])
        assert_that(sub).is_equal_to([(live, "20")])

    def test_prune_removes_key_keeping_others(self, tmp_path):
        keep = self._write(tmp_path, "keep", {"10": 1, "30": 3})
        _snapshot._prune_sub_key_orphans([(keep, "30")])
        assert_that(json.loads((tmp_path / "snap-keep.json").read_text())).is_equal_to({"10": 1})

    def test_prune_deletes_emptied_file(self, tmp_path):
        empty = self._write(tmp_path, "empty", {"10": 1})
        _snapshot._prune_sub_key_orphans([(empty, "10")])
        assert_that(os.path.isfile(empty)).is_false()


class TestSnapshotPlaceholders:
    def test_capture_stores_token_not_value(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        raw = json.loads((tmp_path / "snap-ph.json").read_text())
        assert_that(raw).is_equal_to({"id": {"__placeholder__": "a valid UUID string"}, "name": "Alice"})

    def test_different_volatile_value_passes(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph2", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        assert_that({"id": _UUID_B, "name": "Alice"}).snapshot(
            id="ph2", path=str(tmp_path), placeholders={"id": match.is_uuid()}
        )

    def test_non_matching_placeholder_fails(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph3", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match=r"placeholder <id> to satisfy a valid UUID string"):
            assert_that({"id": "not-a-uuid"}).snapshot(
                id="ph3", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )

    def test_missing_placeholder_key_fails(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph4", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match="but was missing"):
            assert_that({"other": 1}).snapshot(id="ph4", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_drift_in_non_placeholder_field_still_caught(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="ph5", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        with pytest.raises(AssertionError):
            assert_that({"id": _UUID_B, "name": "Bob"}).snapshot(
                id="ph5", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )

    def test_callable_placeholder(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"n": 5}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})
        assert_that({"n": 99}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})
        with pytest.raises(AssertionError):
            assert_that({"n": -1}).snapshot(id="ph6", path=str(tmp_path), placeholders={"n": lambda v: v > 0})

    def test_combines_with_list_ignore(self, tmp_path):
        placeholders = {"id": match.is_uuid()}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "other": 1, "keep": "x"}).snapshot(
                id="ph7", path=str(tmp_path), placeholders=placeholders, ignore=["other"]
            )
        assert_that({"id": _UUID_B, "other": 999, "keep": "x"}).snapshot(
            id="ph7", path=str(tmp_path), placeholders=placeholders, ignore=["other"]
        )

    def test_combines_with_single_key_ignore(self, tmp_path):
        placeholders = {"id": match.is_uuid()}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "other": 1, "keep": "x"}).snapshot(
                id="ph8", path=str(tmp_path), placeholders=placeholders, ignore="other"
            )
        assert_that({"id": _UUID_B, "other": 999, "keep": "x"}).snapshot(
            id="ph8", path=str(tmp_path), placeholders=placeholders, ignore="other"
        )

    def test_failure_collected_under_soft(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A}).snapshot(id="ph9", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that({"id": "bad"}).snapshot(id="ph9", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_update_mode_rewrites_keeping_token(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "v": 1}).snapshot(
                id="ph10", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            assert_that({"id": _UUID_B, "v": 2}).snapshot(
                id="ph10", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        raw = json.loads((tmp_path / "snap-ph10.json").read_text())
        assert_that(raw["v"]).is_equal_to(2)
        assert_that(raw["id"]).is_equal_to({"__placeholder__": "a valid UUID string"})

    def test_non_dict_val_raises(self, tmp_path):
        with pytest.raises(TypeError):
            assert_that([1, 2, 3]).snapshot(id="ph11", path=str(tmp_path), placeholders={"id": match.is_uuid()})

    def test_non_matcher_value_raises(self, tmp_path):
        with pytest.raises(TypeError, match="Matcher instances or callables"):
            assert_that({"id": _UUID_A}).snapshot(id="ph12", path=str(tmp_path), placeholders={"id": "not a matcher"})


def _recording(category, ask):
    """Run *ask* and return the warnings of *category* it raised, so an absence is asserted, not raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ask()
    return [warning for warning in caught if issubclass(warning.category, category)]


_NOT_A_UUID = {"id": "not-a-uuid", "name": "Alice"}
_UUID_ONLY = {"id": match.is_uuid()}


class TestAPlaceholderHoldsBeforeASnapshotIsRecorded:
    """The run that created a snapshot, or overwrote one in update mode, wrote the value without checking it."""

    def test_a_failing_placeholder_creates_no_file(self, tmp_path):
        def ask():
            assert_that(_NOT_A_UUID).snapshot(id="new", path=str(tmp_path), placeholders=_UUID_ONLY)

        assert_that(ask).raises(AssertionFailure).when_called_with().contains("placeholder <id>")
        assert_that(str(tmp_path / "snap-new.json")).does_not_exist()

    def test_a_missing_key_creates_no_file(self, tmp_path):
        def ask():
            assert_that({"name": "Alice"}).snapshot(id="gone", path=str(tmp_path), placeholders=_UUID_ONLY)

        assert_that(ask).raises(AssertionFailure).when_called_with().contains("but was missing")
        assert_that(str(tmp_path / "snap-gone.json")).does_not_exist()

    @pytest.mark.parametrize("soft", [False, True], ids=["asserted", "soft"])
    def test_a_failing_placeholder_adds_no_line_to_a_file_that_has_others(self, tmp_path, soft):
        # keyed by the line of the call, so the second call is a new entry in the file the first one wrote
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(path=str(tmp_path), placeholders=_UUID_ONLY)

        def second():
            with soft_assertions() if soft else contextlib.nullcontext():
                assert_that(_NOT_A_UUID).snapshot(path=str(tmp_path), placeholders=_UUID_ONLY)

        assert_that(second).raises(AssertionError).when_called_with().contains("placeholder <id>")
        stored = _load(str(next(tmp_path.glob("snap-*.json"))))
        assert_that(stored).is_length(1)

    def test_a_soft_block_collects_it_and_creates_nothing(self, tmp_path):
        def collected():
            with soft_assertions():
                assert_that(_NOT_A_UUID).snapshot(id="soft", path=str(tmp_path), placeholders=_UUID_ONLY)

        created = _recording(
            SnapshotCreatedWarning,
            lambda: assert_that(collected).raises(AssertionError).when_called_with().contains("placeholder <id>"),
        )
        assert_that(created).is_empty()
        assert_that(str(tmp_path / "snap-soft.json")).does_not_exist()

    @pytest.mark.parametrize("soft", [False, True], ids=["asserted", "soft"])
    def test_update_mode_leaves_the_stored_one_as_it_was(self, tmp_path, monkeypatch, soft):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="kept", path=str(tmp_path), placeholders=_UUID_ONLY
            )
        before = (tmp_path / "snap-kept.json").read_bytes()
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")

        def update():
            with soft_assertions() if soft else contextlib.nullcontext():
                assert_that({"id": "not-a-uuid", "name": "Bob"}).snapshot(
                    id="kept", path=str(tmp_path), placeholders=_UUID_ONLY
                )

        updated = _recording(
            SnapshotUpdatedWarning, lambda: assert_that(update).raises(AssertionError).when_called_with()
        )
        assert_that(updated).is_empty()
        assert_that((tmp_path / "snap-kept.json").read_bytes()).is_equal_to(before)

    def test_ci_mode_refuses_to_create_before_the_placeholder_is_asked(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)

        def ask():
            assert_that(_NOT_A_UUID).snapshot(id="ci", path=str(tmp_path), placeholders=_UUID_ONLY)

        assert_that(ask).raises(AssertionFailure).when_called_with().contains("CI mode forbids creating it")

    def test_not_refuses_to_create_before_the_placeholder_is_asked(self, tmp_path):
        def ask():
            assert_that(_NOT_A_UUID).not_.snapshot(id="neg", path=str(tmp_path), placeholders=_UUID_ONLY)

        assert_that(ask).raises(AssertionFailure).when_called_with().contains("not_ cannot create one")
        assert_that(str(tmp_path / "snap-neg.json")).does_not_exist()

    def test_a_stored_one_is_still_compared_after_a_collected_placeholder(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": _UUID_A, "name": "Alice"}).snapshot(
                id="both", path=str(tmp_path), placeholders=_UUID_ONLY
            )

        def collected():
            with soft_assertions():
                assert_that({"id": "not-a-uuid", "name": "Bob"}).snapshot(
                    id="both", path=str(tmp_path), placeholders=_UUID_ONLY
                )

        assert_that(collected).raises(AssertionError).when_called_with().contains("placeholder <id>", "Bob")


class TestARefusalIsStillAFailureYouCanRead:
    """The three refusals that used to raise a bare `AssertionError`.

    `docs/concepts/stability.md` promises that a failure raised by this library carries `actual`,
    `expected`, `diff`, `trace` and `failures`.  These three did not, so a consumer catching
    `AssertionFailure` to report structured failures missed them and got an unstructured crash.
    """

    def test_an_empty_inline_snapshot(self):
        with pytest.raises(AssertionFailure, match="inline snapshot is empty") as failure:
            assert_that(7).matches_inline()
        assert_that(failure.value.actual).is_equal_to(7)

    def test_an_empty_inline_snapshot_in_ci(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionFailure, match="CI mode forbids recording it") as failure:
            assert_that(7).matches_inline()
        assert_that(failure.value.actual).is_equal_to(7)

    def test_a_missing_file_snapshot_in_ci(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionFailure, match="CI mode forbids creating it") as failure:
            assert_that({"a": 1}).snapshot(id="ci-structured", path=str(tmp_path))
        assert_that(failure.value.actual).is_equal_to({"a": 1})

    @pytest.mark.parametrize(
        "call",
        [
            lambda tmp: assert_that(7).matches_inline(),
            lambda tmp: assert_that({"a": 1}).snapshot(id="ci-unnamed", path=str(tmp)),
        ],
        ids=["inline", "file"],
    )
    def test_none_of_them_names_an_expectation(self, tmp_path, monkeypatch, call):
        """`has_expected` has to read false: nothing was compared, so claiming one would be a lie."""
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionFailure) as failure:
            call(tmp_path)
        assert_that(failure.value.has_expected).is_false()
        assert_that(failure.value.expected).is_none()

    def test_an_existing_except_assertion_error_still_catches(self):
        """The compatibility half: `AssertionFailure` is an `AssertionError` and stays one."""
        try:
            assert_that(7).matches_inline()
        except AssertionError as caught:
            assert_that(caught).is_instance_of(AssertionFailure)
        else:  # pragma: no cover - the call above raises
            pytest.fail("the empty inline snapshot did not raise")

    def test_a_soft_block_does_not_swallow_the_refusal(self, tmp_path, monkeypatch):
        """The reason these raise instead of being collected.

        Each guards a line that writes a snapshot file.  Collected, the block would carry on to that
        line and write the file CI mode exists to prevent, which is the opposite of what it asks for.
        """
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionFailure, match="CI mode forbids creating it"), soft_assertions():
            assert_that({"a": 1}).snapshot(id="ci-soft", path=str(tmp_path))
        written = os.path.join(str(tmp_path), "snap-ci-soft.json")
        assert_that(os.path.isfile(written)).described_as("the file the guard refuses to create").is_false()

    @pytest.mark.parametrize(
        "start",
        [lambda: assert_warn(7), lambda: assert_that(7).check()],
        ids=["warn", "check"],
    )
    def test_the_other_collecting_modes_do_not_swallow_it_either(self, start):
        """`soft` is not the only mode that would have carried on to the write.

        Pinned per mode rather than once, since each reaches the failure through its own branch of the
        delivery and a later change could quieten one of them alone.
        """
        with pytest.raises(AssertionFailure, match="inline snapshot is empty"):
            start().matches_inline()

    def test_the_failure_description_reaches_the_message(self):
        """A consequence of composing rather than raising, and the reason to compose.

        `described_as()` is prepended by the composer, so these three refusals now read the way every
        other failure in the library does instead of ignoring what the caller named.
        """
        with pytest.raises(AssertionFailure, match=r"^\[the order id\] inline snapshot is empty"):
            assert_that(7).described_as("the order id").matches_inline()


class TestSnapshotCiMode:
    def test_ci_mode_enabled_precedence(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        assert_that(_ci_mode_enabled()).is_true()
        monkeypatch.setattr(_snapshot, "_CI_MODE", False)
        assert_that(_ci_mode_enabled()).is_false()
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "off")
        assert_that(_ci_mode_enabled()).is_false()
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "yes")
        assert_that(_ci_mode_enabled()).is_true()
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_CI")
        monkeypatch.setenv("CI", "1")
        assert_that(_ci_mode_enabled()).is_true()
        monkeypatch.setenv("CI", "")
        assert_that(_ci_mode_enabled()).is_false()

    def test_ci_flag_fails_on_missing_whole_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="does not exist and CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-missing", path=str(tmp_path))
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-ci-missing.json"))).is_false()

    def test_ci_env_fails_on_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "1")
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-env", path=str(tmp_path))

    def test_ci_autodetect_via_ci_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_CI", raising=False)
        monkeypatch.setenv("CI", "true")
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that({"a": 1}).snapshot(id="ci-auto", path=str(tmp_path))

    def test_ci_env_off_beats_autodetect(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_CI", "0")
        monkeypatch.setenv("CI", "true")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="ci-off", path=str(tmp_path))
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-ci-off.json"))).is_true()

    def test_ci_existing_snapshot_still_compares(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="ci-exist", path=str(tmp_path))
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        assert_that({"a": 1}).snapshot(id="ci-exist", path=str(tmp_path))
        with pytest.raises(AssertionError):
            assert_that({"a": 2}).snapshot(id="ci-exist", path=str(tmp_path))

    def test_ci_fails_on_missing_lineno_subsnap(self, tmp_path, monkeypatch):
        def snap(value):
            return assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap(1)
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(2).snapshot(path=str(tmp_path))


def test_snapshot_not_serializable(tmp_path):
    with pytest.raises(TypeError) as exc_info:
        assert_that(range(5)).snapshot(id="nonser", path=str(tmp_path))
    assert_that(str(exc_info.value)).ends_with("is not JSON serializable")


def test_snapshot_custom_id_int():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").snapshot(id=123)
    assert_that(str(exc_info.value)).starts_with("failed to create snapshot filename")


def test_snapshot_custom_path_not_a_string():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").snapshot(id="x", path=5)
    assert_that(str(exc_info.value)).starts_with("failed to create snapshot filename")


def test_snapshot_does_not_import_arbitrary_modules(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    snap_file = snap_dir / "snap-cve156.json"
    snap_file.write_text(
        json.dumps(
            {
                "__type__": "instance",
                "__class__": "Exploit",
                "__module__": "cve156_fake_module",
                "__data__": {"pwned": True},
            }
        )
    )

    assert_that(sys.modules).does_not_contain("cve156_fake_module")

    with contextlib.suppress(AssertionError):
        assert_that({"safe": True}).snapshot(id="cve156", path=str(snap_dir))

    assert_that(sys.modules).does_not_contain("cve156_fake_module")


def test_snapshot_returns_dict_for_unknown_module(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    payload = {
        "__type__": "instance",
        "__class__": "Nope",
        "__module__": "nonexistent_module_xyz",
        "__data__": {"x": 1},
    }
    snap_file = snap_dir / "snap-fallback.json"
    snap_file.write_text(json.dumps(payload))

    with contextlib.suppress(AssertionError):
        assert_that(payload).snapshot(id="fallback", path=str(snap_dir))

    assert_that(sys.modules).does_not_contain("nonexistent_module_xyz")


def test_snapshot_returns_dict_for_missing_class(tmp_path):
    snap_dir = tmp_path / "__snapshots"
    snap_dir.mkdir()
    payload = {
        "__type__": "instance",
        "__class__": "ClassThatDoesNotExist",
        "__module__": "os",
        "__data__": {},
    }
    snap_file = snap_dir / "snap-noclass.json"
    snap_file.write_text(json.dumps(payload))

    with contextlib.suppress(AssertionError):
        assert_that(payload).snapshot(id="noclass", path=str(snap_dir))


class Foo:
    def __init__(self, x=0):
        self.x = x
        self.y = 1

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented


class Bar(Foo):
    def __eq__(self, other):
        return NotImplemented


def test_file_lock_times_out_when_held(tmp_path):
    target = str(tmp_path / "data")
    with _file_lock(target), pytest.raises(TimeoutError), _file_lock(target, timeout=0.1, poll=0.02):
        pass


class _Clock:
    """Stands in for the lock's `time`: only its own sleeps move it, so a deadline falls on a known attempt."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class TestALockFileBeingDeleted:
    """Windows answers creating a lock file its last holder is still deleting with access denied.

    Read as a failure, it took a snapshot write down under xdist whenever two workers met on one key:
    three acquisitions in 1600 across four processes, measured on Windows.
    """

    @staticmethod
    def _refusing(monkeypatch, times):
        """`os.open` refusing the lock *times* times as access denied, then creating it."""
        calls = []
        real = os.open

        def refusing(path, flags, *mode):
            calls.append(path)
            if len(calls) <= times:
                raise PermissionError(13, "Permission denied", path)
            return real(path, flags, *mode)

        monkeypatch.setattr(os, "open", refusing)
        return calls

    @pytest.fixture
    def clock(self, monkeypatch):
        clock = _Clock()
        monkeypatch.setattr(_snapshot, "time", clock)
        return clock

    def test_windows_waits_for_it(self, tmp_path, monkeypatch, clock):
        monkeypatch.setattr(sys, "platform", "win32")
        calls = self._refusing(monkeypatch, times=2)
        with _file_lock(str(tmp_path / "data"), poll=0.25):
            pass
        assert_that(calls).is_length(3)
        assert_that(clock.now).is_equal_to(0.5)

    def test_windows_names_a_refusal_that_outlasts_the_wait(self, tmp_path, monkeypatch, clock):
        """A directory it may not write to is not a lock being released, and says so rather than timing out."""
        monkeypatch.setattr(sys, "platform", "win32")
        calls = self._refusing(monkeypatch, times=10_000)
        with pytest.raises(PermissionError), _file_lock(str(tmp_path / "data"), timeout=1.0, poll=0.25):
            pass
        assert_that(calls).is_length(5)
        assert_that(clock.now).is_equal_to(1.0)

    @pytest.mark.parametrize("platform", ["linux", "darwin"])
    def test_elsewhere_access_denied_is_what_it_says(self, tmp_path, monkeypatch, platform):
        monkeypatch.setattr(sys, "platform", platform)
        calls = self._refusing(monkeypatch, times=1)
        with pytest.raises(PermissionError), _file_lock(str(tmp_path / "data"), poll=0.001):
            pass
        assert_that(calls).is_length(1)


def test_a_snapshot_file_is_utf8_whatever_the_default_text_encoding_is(tmp_path):
    """A file a formatter left unescaped, `jq .` or an editor, holds raw UTF-8.  Read in the default encoding it
    compared unequal under cp1252.

    The child is held two ways.  An `open` that names no encoding is an error in it, whatever the platform.  And it
    asks for a default that is not UTF-8, which it gets wherever the platform has one to give: the code page on
    most of Windows, ASCII elsewhere.  What the library wrote is read back as UTF-8 before the file is replaced.
    """
    script = textwrap.dedent(
        """
        import json, pathlib, sys, warnings
        from assertpy import assert_that

        warnings.simplefilter("ignore")
        warnings.simplefilter("error", EncodingWarning)
        folder = pathlib.Path(sys.argv[1])
        value = {"name": "Zo\\u00eb"}
        assert_that(value).snapshot(id="names", path=str(folder))
        written = folder / "snap-names.json"
        assert json.loads(written.read_bytes().decode("utf-8")) == value, written.read_bytes()
        written.write_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        assert_that(value).snapshot(id="names", path=str(folder))
        print("read back equal")
        """
    )
    pinned = {
        **os.environ,
        "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
        "LC_ALL": "C",
        "ASSERTPY_SNAPSHOT_CI": "0",
        "ASSERTPY_SNAPSHOT_UPDATE": "",
    }
    ran = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-X", "warn_default_encoding", "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=pinned,
        check=False,
    )
    assert_that(ran.returncode).described_as(ran.stderr).is_zero()
    assert_that(ran.stdout.strip()).is_equal_to("read back equal")


def test_file_lock_serializes_concurrent_writes(tmp_path):
    target = str(tmp_path / "shared.json")
    with open(target, "w", encoding="utf-8") as fp:
        json.dump({}, fp)

    def worker(index):
        with _file_lock(target):
            with open(target, encoding="utf-8") as fp:
                data = json.load(fp)
            data[str(index)] = index
            time.sleep(0.005)
            with open(target, "w", encoding="utf-8") as fp:
                json.dump(data, fp)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(15)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with open(target, encoding="utf-8") as fp:
        final = json.load(fp)
    assert_that(final).is_length(15)


_CONTRACT_SAMPLE = {"id": 1, "total": 5, "created": None, "customer": {"name": "A"}, "items": [{"sku": "X", "qty": 1}]}


class TestContractSnapshot:
    def test_first_run_creates_and_warns(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning, match="captured the shape"):
            assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-first", path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_value_tolerant_same_structure_passes(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-tol", path=str(tmp_path))
        changed = {"id": 999, "total": 8.75, "created": "2026-07-06", "customer": {"name": "Z"}, "items": []}
        assert_that(changed).matches_contract_snapshot(id="c-tol", path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_added_field_drift_fails_with_report(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-add", path=str(tmp_path))
        grew = {**_CONTRACT_SAMPLE, "promo": "X", "customer": {"name": "A", "vip": True}}
        with pytest.raises(AssertionError) as exc_info:
            assert_that(grew).matches_contract_snapshot(id="c-add", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("structure").contains("+ promo").contains("+ customer.vip")

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_removed_and_retyped_drift_fails(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-rr", path=str(tmp_path))
        shrank = {k: v for k, v in _CONTRACT_SAMPLE.items() if k != "total"}
        with pytest.raises(AssertionError, match=r"- total"):
            assert_that(shrank).matches_contract_snapshot(id="c-rr", path=str(tmp_path))
        retyped = {**_CONTRACT_SAMPLE, "id": "1"}
        with pytest.raises(AssertionError, match="number -> str"):
            assert_that(retyped).matches_contract_snapshot(id="c-rr", path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_list_element_drift(self, tmp_path):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-list", path=str(tmp_path))
        drifted = {**_CONTRACT_SAMPLE, "items": [{"sku": "X", "qty": 1, "gift": True}]}
        with pytest.raises(AssertionError, match=r"items\[\*\]\.gift"):
            assert_that(drifted).matches_contract_snapshot(id="c-list", path=str(tmp_path))

    def test_lineno_based_create_then_compare(self, tmp_path):
        payloads = iter([{"a": 1}, {"a": 2}])
        with pytest.warns(SnapshotCreatedWarning):
            for _ in range(2):
                assert_that(next(payloads)).matches_contract_snapshot(path=str(tmp_path))

    def test_new_line_in_existing_file_creates(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(path=str(tmp_path))
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"b": 2}).matches_contract_snapshot(path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_update_mode_rewrites_drifted_id(self, tmp_path, monkeypatch):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-up", path=str(tmp_path))
        grew = {**_CONTRACT_SAMPLE, "promo": "X"}
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning, match="overwrote the stored shape"):
            assert_that(grew).matches_contract_snapshot(id="c-up", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        assert_that(grew).matches_contract_snapshot(id="c-up", path=str(tmp_path))

    def test_update_mode_rewrites_drifted_lineno(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        values = iter([{"a": 1}, {"a": 1, "b": 2}])
        for expected in (SnapshotCreatedWarning, SnapshotUpdatedWarning):
            with pytest.warns(expected):
                assert_that(next(values)).matches_contract_snapshot(path=str(tmp_path))

    @pytest.mark.filterwarnings("ignore::assertpy.snapshot.SnapshotCreatedWarning")
    def test_update_mode_leaves_matching_untouched(self, tmp_path, monkeypatch):
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-keep", path=str(tmp_path))
        target = os.path.join(str(tmp_path), "snap-c-keep.json")
        before = os.path.getmtime(target)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-keep", path=str(tmp_path))
        assert_that(os.path.getmtime(target)).is_equal_to(before)

    def test_ci_mode_forbids_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(_CONTRACT_SAMPLE).matches_contract_snapshot(id="c-ci", path=str(tmp_path))


class TestMismatchNamesItsSnapshot:
    """A mismatch must say which stored value it measured against, and how to accept the new one."""

    def test_named_snapshot_is_identified(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="named-snap", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": 99}).snapshot(id="named-snap", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("named-snap")
        assert_that(message).contains("--assertpy-snapshot-update")

    def test_line_keyed_snapshots_are_told_apart(self, tmp_path):
        def first(value):
            assert_that(value).snapshot(path=str(tmp_path))

        def second(value):
            assert_that(value).snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            first({"a": 1})
        with pytest.warns(SnapshotCreatedWarning):
            second({"b": 1})
        with pytest.raises(AssertionError) as first_failure:
            first({"a": 99})
        with pytest.raises(AssertionError) as second_failure:
            second({"b": 99})
        assert_that(str(first_failure.value)).contains("::")
        assert_that(str(first_failure.value)).is_not_equal_to(str(second_failure.value))

    def test_the_diff_survives_the_added_identity(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": {"b": 1}}).snapshot(id="diff-snap", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"a": {"b": 2}}).snapshot(id="diff-snap", path=str(tmp_path))
        assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a.b")

    def test_the_rewrap_keeps_the_values_the_comparison_measured(self, tmp_path):
        _save(os.path.join(str(tmp_path), "snap-rewrap.json"), {"a": 1}, keyed=False)
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 2}).snapshot(id="rewrap", path=str(tmp_path))
        assert_that(failure.value.actual).is_equal_to({"a": 2})
        assert_that(failure.value.expected).is_equal_to({"a": 1})


class TestContractSnapshotNamesItself:
    """The drift report says which contract it measured against, like both sibling snapshot kinds."""

    def test_named_contract_is_identified(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": 1, "tags": ["a"]}).matches_contract_snapshot(id="ct-named", path=str(tmp_path))
        with pytest.raises(AssertionError) as exc_info:
            assert_that({"id": "one", "extra": 2}).matches_contract_snapshot(id="ct-named", path=str(tmp_path))
        message = str(exc_info.value)
        assert_that(message).contains("ct-named")
        assert_that(message).contains("--assertpy-snapshot-update")
        assert_that(message).contains("+ extra")
        assert_that(message).contains("~ id number -> str")

    def test_line_keyed_contracts_are_told_apart(self, tmp_path):
        def first(value):
            assert_that(value).matches_contract_snapshot(path=str(tmp_path))

        def second(value):
            assert_that(value).matches_contract_snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            first({"a": 1})
        with pytest.warns(SnapshotCreatedWarning):
            second({"b": 1})
        with pytest.raises(AssertionError) as first_failure:
            first({"a": "one"})
        with pytest.raises(AssertionError) as second_failure:
            second({"b": "one"})
        assert_that(str(first_failure.value)).contains("::")
        assert_that(str(first_failure.value)).is_not_equal_to(str(second_failure.value))


class TestCyclicValues:
    """Every other walker in the library marks a cycle; these two used to recurse until the stack gave out."""

    def test_snapshot_names_the_cycle_instead_of_recursing(self, tmp_path):
        node = {"id": 1}
        node["self"] = node
        with pytest.raises(ValueError, match="circular reference"):
            assert_that(node).snapshot(id="cyc", path=str(tmp_path))

    def test_contract_snapshot_records_a_cycle_marker(self, tmp_path):
        node = {"id": 1}
        node["self"] = node
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(node).matches_contract_snapshot(id="cyc-shape", path=str(tmp_path))


class TestReuseMessage:
    """The reuse warning names the key, where it was first reached, and what sharing it costs."""

    def test_the_in_test_wording_states_the_fact_without_a_count(self):
        assert_that(_snapshot._reuse_message("snap-mod.json", "17", "test_mod.py:17")).is_equal_to(
            "snapshot key <snap-mod.json::17> from test_mod.py:17 is reached by more than one test."
            " Only the first value is stored, so the others are compared against it and their own values"
            " are never asserted. Give each test its own snapshot(id=...)."
        )

    def test_the_sweep_wording_carries_the_total(self):
        assert_that(_snapshot._reuse_message("snap-mod.json", "17", "test_mod.py:17", tests=4)).contains(
            "snapshot key <snap-mod.json::17> from test_mod.py:17 is shared by 4 tests."
        )

    def test_a_whole_file_key_without_a_site_still_names_itself(self):
        assert_that(_snapshot._reuse_message("snap-mod.json", "", "")).starts_with(
            "snapshot key <snap-mod.json::<whole file>> is reached by more than one test."
        )


class TestAccessRecord:
    """What a reached key records, and what the second test to reach it is told."""

    @pytest.fixture(autouse=True)
    def _clean_registries(self, monkeypatch):
        for name in ("_ACCESS_NODES", "_ACCESS_SITES"):
            monkeypatch.setattr(_snapshot, name, {})
        for name in ("_WARNED", "_SCOPE_SEEN", "_SCOPE_REPEATS", "_TOUCHED"):
            monkeypatch.setattr(_snapshot, name, set())
        monkeypatch.setattr(_snapshot, "_SCOPE", None)

    def test_the_second_test_on_one_key_warns_with_the_first_site(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CURRENT_NODE", "test_mod.py::one")
        _snapshot._record_access("snap-mod.json", "17", "test_mod.py:17")
        monkeypatch.setattr(_snapshot, "_CURRENT_NODE", "test_mod.py::two")
        with pytest.warns(_snapshot.SnapshotKeyReusedWarning) as caught:
            _snapshot._record_access("snap-mod.json", "17", "test_mod.py:99")
        assert_that(str(caught[0].message)).is_equal_to(
            _snapshot._reuse_message("snap-mod.json", "17", "test_mod.py:17")
        )

    def test_a_repeat_inside_one_test_survives_to_the_next_call(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CURRENT_NODE", "test_mod.py::one")
        _snapshot._record_access("snap-mod.json", "17", "test_mod.py:17")
        _snapshot._record_access("snap-mod.json", "17", "test_mod.py:17")
        assert_that(_snapshot._SCOPE_REPEATS).contains(("snap-mod.json", "17"))

    def test_a_custom_id_snapshot_records_its_file_key_and_site(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-site.json")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="site", path=str(tmp_path))
        assert_that(_snapshot._TOUCHED).contains((snapname, ""))
        assert_that(_snapshot._ACCESS_SITES[snapname, ""]).is_equal_to("id='site'")

    def test_a_custom_id_contract_snapshot_records_its_file_key_and_site(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-ct-site.json")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(id="ct-site", path=str(tmp_path))
        assert_that(_snapshot._TOUCHED).contains((snapname, ""))
        assert_that(_snapshot._ACCESS_SITES[snapname, ""]).is_equal_to("id='ct-site'")


class TestUpdateFlagVocabulary:
    """The environment switch reads words, and every existing test spelled it `1`."""

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", " Yes ", "on"])
    def test_every_truthy_spelling_turns_update_mode_on(self, monkeypatch, value):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", value)
        assert_that(_snapshot._update_enabled()).is_true()

    @pytest.mark.parametrize("value", ["0", "false", "OFF", "", "maybe"])
    def test_everything_else_leaves_it_off(self, monkeypatch, value):
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", value)
        assert_that(_snapshot._update_enabled()).is_false()


class TestCiRefusalMessage:
    """The refusal names the snapshot that is missing and both ways out, on all four paths."""

    def test_no_ci_marker_at_all_leaves_ci_mode_off(self, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", None)
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_CI", raising=False)
        monkeypatch.delenv("CI", raising=False)
        assert_that(_ci_mode_enabled()).is_false()

    def test_a_missing_whole_file_is_named_with_both_ways_out(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        snapname = os.path.join(str(tmp_path), "snap-ci-msg.json")
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 1}).snapshot(id="ci-msg", path=str(tmp_path))
        assert_that(str(failure.value)).is_equal_to(
            f"snapshot <{snapname}> does not exist and CI mode forbids creating it - commit the snapshot"
            " to source control, or run without CI mode (--assertpy-snapshot-no-ci, or unset CI /"
            " ASSERTPY_SNAPSHOT_CI)"
        )

    def test_a_missing_line_key_in_an_existing_file_names_that_file(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-test_snapshots.json")
        _save(snapname, {"1": "another call site"}, keyed=True)
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 1}).snapshot(path=str(tmp_path))
        assert_that(str(failure.value)).starts_with(f"snapshot <{snapname}> does not exist")

    def test_a_missing_contract_file_is_named(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        snapname = os.path.join(str(tmp_path), "snap-ci-ct.json")
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 1}).matches_contract_snapshot(id="ci-ct", path=str(tmp_path))
        assert_that(str(failure.value)).starts_with(f"snapshot <{snapname}> does not exist")

    def test_a_missing_contract_line_key_names_its_file(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-test_snapshots.json")
        _save(snapname, {"1": {}}, keyed=True)
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 1}).matches_contract_snapshot(path=str(tmp_path))
        assert_that(str(failure.value)).starts_with(f"snapshot <{snapname}> does not exist")


class TestSnapshotFilenames:
    """Where a snapshot lands and what it is called, read back off the filesystem."""

    def test_a_spaced_id_becomes_a_lowercased_underscored_filename(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="My Order Id", path=str(tmp_path))
        assert_that(os.listdir(str(tmp_path))).is_equal_to(["snap-my_order_id.json"])

    def test_the_default_directory_is_named_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="dflt")
        assert_that(os.listdir(".")).is_equal_to(["__snapshots"])

    def test_the_default_contract_directory_is_named_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(id="dflt-ct")
        assert_that(os.listdir(".")).is_equal_to(["__snapshots"])

    def test_a_default_key_contract_file_is_named_after_the_calling_module(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(path=str(tmp_path))
        assert_that(os.listdir(str(tmp_path))).is_equal_to(["snap-test_snapshots.json"])


class TestShapeDriftReport:
    """One line per entry, two-space indented, joined by a newline."""

    def test_each_entry_is_its_own_two_space_indented_line(self):
        rendered = _snapshot._format_shape_drift(
            [("added", "promo", ""), ("removed", "total", ""), ("retyped", "id", "number -> str")]
        )
        assert_that(rendered).is_equal_to("  + promo\n  - total\n  ~ id number -> str")


class TestUpdateModeHonorsEveryComparisonOption:
    """A knob that makes the two values equal must also make them not stale, or update mode rewrites a
    snapshot that never drifted."""

    def test_include_narrows_the_staleness_decision(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-upd-inc.json")
        _save(snapname, {"a": 1, "b": 2}, keyed=False)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"a": 1, "b": 999}).snapshot(id="upd-inc", path=str(tmp_path), include="a")
        assert_that(_load(snapname)).is_equal_to({"a": 1, "b": 2})

    def test_tolerance_absorbs_noise_before_the_rewrite(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-upd-tol.json")
        _save(snapname, {"price": 1.0}, keyed=False)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"price": 1.0004}).snapshot(id="upd-tol", path=str(tmp_path), tolerance=0.001)
        assert_that(_load(snapname)).is_equal_to({"price": 1.0})

    def test_a_comparator_owns_its_field_before_the_rewrite(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-upd-cmp.json")
        _save(snapname, {"name": "Alice"}, keyed=False)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"name": "ALICE"}).snapshot(
            id="upd-cmp",
            path=str(tmp_path),
            comparators={"name": lambda actual, expected: actual.lower() == expected.lower()},
        )
        assert_that(_load(snapname)).is_equal_to({"name": "Alice"})

    def test_bad_comparators_fail_on_the_capturing_first_run(self, tmp_path):
        with pytest.raises(TypeError, match="comparators arg must be a dict"):
            assert_that({"a": 1}).snapshot(id="opt-bad-cmp", path=str(tmp_path), comparators="nope")
        assert_that(os.path.isfile(os.path.join(str(tmp_path), "snap-opt-bad-cmp.json"))).is_false()


class TestSnapshotWarningsPointAtTheCaller:
    """A capture warning attributed to the library rather than the test is unusable under ``-W error``."""

    def test_the_created_warning_points_at_the_calling_test(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning) as caught:
            assert_that({"a": 1}).snapshot(id="stack-new", path=str(tmp_path))
        assert_that(os.path.basename(caught[0].filename)).is_equal_to("test_snapshots.py")

    def test_the_updated_warning_points_at_the_calling_test(self, tmp_path, monkeypatch):
        _save(os.path.join(str(tmp_path), "snap-stack-upd.json"), {"a": 1}, keyed=False)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning) as caught:
            assert_that({"a": 2}).snapshot(id="stack-upd", path=str(tmp_path))
        assert_that(os.path.basename(caught[0].filename)).is_equal_to("test_snapshots.py")

    def test_the_created_contract_warning_points_at_the_calling_test(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning) as caught:
            assert_that({"a": 1}).matches_contract_snapshot(id="stack-ct-new", path=str(tmp_path))
        assert_that(os.path.basename(caught[0].filename)).is_equal_to("test_snapshots.py")

    def test_the_updated_contract_warning_points_at_the_calling_test(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(id="stack-ct-upd", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning) as caught:
            assert_that({"a": 1, "b": 2}).matches_contract_snapshot(id="stack-ct-upd", path=str(tmp_path))
        assert_that(os.path.basename(caught[0].filename)).is_equal_to("test_snapshots.py")


class TestSnapshotFileLock:
    """The read-modify-write is serialized on the snapshot file itself, not on some other name."""

    def test_a_held_lock_on_the_snapshot_file_blocks_the_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "snap-locked.json.lock").write_text("held")
        monkeypatch.setattr(_snapshot, "_file_lock", functools.partial(_file_lock, timeout=0.05, poll=0.01))
        with pytest.raises(TimeoutError) as failure:
            assert_that({"a": 1}).snapshot(id="locked", path=str(tmp_path))
        assert_that(str(failure.value)).contains("snap-locked.json.lock")

    def test_a_held_lock_blocks_a_contract_snapshot_too(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "snap-ct-locked.json.lock").write_text("held")
        monkeypatch.setattr(_snapshot, "_file_lock", functools.partial(_file_lock, timeout=0.05, poll=0.01))
        with pytest.raises(TimeoutError) as failure:
            assert_that({"a": 1}).matches_contract_snapshot(id="ct-locked", path=str(tmp_path))
        assert_that(str(failure.value)).contains("snap-ct-locked.json.lock")


class TestContractLineKeys:
    """A line-keyed contract file has to stay a map of shapes through a create and through an update."""

    def test_a_new_line_key_stores_a_shape_the_next_run_compares_against(self, tmp_path):
        _save(os.path.join(str(tmp_path), "snap-test_snapshots.json"), {"1": {}}, keyed=True)
        payloads = iter([{"a": 1}, {"a": 2}])
        with pytest.warns(SnapshotCreatedWarning):
            for _ in range(2):
                assert_that(next(payloads)).matches_contract_snapshot(path=str(tmp_path))

    def test_an_update_leaves_the_line_key_holding_the_new_shape(self, tmp_path, monkeypatch):
        def snap(value):
            assert_that(value).matches_contract_snapshot(path=str(tmp_path))

        with pytest.warns(SnapshotCreatedWarning):
            snap({"a": 1})
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            snap({"a": 1, "b": 2})
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        snap({"a": 9, "b": 9})


class TestSnapshotMessages:
    """Every sentence the snapshot surface raises or warns with, stated whole rather than searched."""

    def test_the_registry_refuses_a_non_type_by_name(self):
        with pytest.raises(TypeError) as failure:
            register_snapshot_serializer("not a type", str, str)
        assert_that(str(failure.value)).is_equal_to("cls must be a type")

    def test_the_registry_refuses_a_non_callable_codec_by_name(self):
        with pytest.raises(TypeError) as failure:
            register_snapshot_serializer(int, "nope", str)
        assert_that(str(failure.value)).is_equal_to("encode and decode must be callable")

    def test_the_placeholder_failure_shows_the_value_it_rejected(self, tmp_path):
        _save(
            os.path.join(str(tmp_path), "snap-msg-ph.json"),
            {"id": {"__placeholder__": "a valid UUID string"}},
            keyed=False,
        )
        with pytest.raises(AssertionError) as failure:
            assert_that({"id": "not-a-uuid"}).snapshot(
                id="msg-ph", path=str(tmp_path), placeholders={"id": match.is_uuid()}
            )
        assert_that(str(failure.value)).is_equal_to(
            "Expected snapshot placeholder <id> to satisfy a valid UUID string, but was 'not-a-uuid'."
        )

    def test_a_non_matcher_placeholder_is_refused_by_name(self, tmp_path):
        with pytest.raises(TypeError) as failure:
            assert_that({"id": 1}).snapshot(id="msg-ph2", path=str(tmp_path), placeholders={"id": "nope"})
        assert_that(str(failure.value)).is_equal_to("placeholder values must be Matcher instances or callables")

    def test_a_non_dict_val_is_refused_as_val(self, tmp_path):
        with pytest.raises(TypeError) as failure:
            assert_that([1, 2, 3]).snapshot(id="msg-ph3", path=str(tmp_path), placeholders={"id": match.is_uuid()})
        assert_that(str(failure.value)).starts_with("val must be dict-like")

    def test_the_created_warning_states_what_it_did(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-msg-new.json")
        with pytest.warns(SnapshotCreatedWarning) as caught:
            assert_that({"a": 1}).snapshot(id="msg-new", path=str(tmp_path))
        assert_that(str(caught[0].message)).is_equal_to(
            f"created snapshot <{snapname}>: this run captured the value instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)"
        )

    def test_the_updated_warning_states_what_it_did(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-msg-upd.json")
        _save(snapname, {"a": 1}, keyed=False)
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning) as caught:
            assert_that({"a": 2}).snapshot(id="msg-upd", path=str(tmp_path))
        assert_that(str(caught[0].message)).is_equal_to(
            f"updated snapshot <{snapname}>: this run overwrote the stored value instead of comparing;"
            " subsequent runs compare against it"
        )

    def test_a_mismatch_ends_by_naming_the_snapshot_and_the_way_to_accept_it(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-msg-diff.json")
        _save(snapname, {"a": 1}, keyed=False)
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 2}).snapshot(id="msg-diff", path=str(tmp_path))
        assert_that(str(failure.value)).ends_with(
            f" Snapshot <{snapname}>; rerun with --assertpy-snapshot-update to accept the new value."
        )

    def test_the_created_contract_warning_states_what_it_did(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-ct-msg-new.json")
        with pytest.warns(SnapshotCreatedWarning) as caught:
            assert_that({"a": 1}).matches_contract_snapshot(id="ct-msg-new", path=str(tmp_path))
        assert_that(str(caught[0].message)).is_equal_to(
            f"created contract snapshot <{snapname}>: this run captured the shape instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)"
        )

    def test_the_updated_contract_warning_states_what_it_did(self, tmp_path, monkeypatch):
        snapname = os.path.join(str(tmp_path), "snap-ct-msg-upd.json")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(id="ct-msg-upd", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning) as caught:
            assert_that({"a": 1, "b": 2}).matches_contract_snapshot(id="ct-msg-upd", path=str(tmp_path))
        assert_that(str(caught[0].message)).is_equal_to(
            f"updated contract snapshot <{snapname}>: this run overwrote the stored shape instead of"
            " comparing; subsequent runs compare against it"
        )

    def test_a_contract_drift_shows_the_value_and_names_the_snapshot(self, tmp_path):
        snapname = os.path.join(str(tmp_path), "snap-ct-msg-drift.json")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": 1}).matches_contract_snapshot(id="ct-msg-drift", path=str(tmp_path))
        with pytest.raises(AssertionError) as failure:
            assert_that({"id": "one"}).matches_contract_snapshot(id="ct-msg-drift", path=str(tmp_path))
        assert_that(str(failure.value)).is_equal_to(
            "Expected <{'id': 'one'}> to match contract snapshot, but the structure drifted:\n"
            "  ~ id number -> str\n"
            f"Contract snapshot <{snapname}>; rerun with --assertpy-snapshot-update to accept the new shape."
        )

    def test_a_contract_drift_carries_the_value_it_measured(self, tmp_path):
        drifted = {"id": "one"}
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"id": 1}).matches_contract_snapshot(id="ct-actual", path=str(tmp_path))
        with pytest.raises(AssertionFailure) as failure:
            assert_that(drifted).matches_contract_snapshot(id="ct-actual", path=str(tmp_path))
        assert_that(failure.value.actual).is_equal_to(drifted)
        assert_that(failure.value._outcome.actual_provided).is_true()


class _TupleColour(enum.Enum):
    RED = (255, 0, 0)


class _Holder:
    def __init__(self, mapping):
        self.mapping = mapping

    def __eq__(self, other):
        return isinstance(other, _Holder) and other.mapping == self.mapping

    __hash__ = None


class TestWhatWasWrittenCanBeReadBack:
    """A value the codec writes and cannot read again fails every snapshot in that file, not only its own."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param({(1, 2), (3, 4)}, id="set-of-tuples"),
            pytest.param({((1, 2), 3)}, id="set-of-nested-tuples"),
            pytest.param({(1, 2), 3}, id="set-of-mixed"),
            pytest.param(_TupleColour.RED, id="enum-with-a-tuple-value"),
            pytest.param(_Holder({1: "a", "1": "b"}), id="instance-holding-a-non-string-keyed-dict"),
            pytest.param([{(1, 2)}, {"k": _TupleColour.RED}], id="nested-in-a-container"),
        ],
    )
    def test_a_value_round_trips_through_the_codec(self, value):
        written = json.dumps(_snapshot_codec._encode(value))
        assert_that(_snapshot_codec._decode(json.loads(written))).is_equal_to(value)

    def test_an_instance_without_odd_keys_is_written_as_it_always_was(self):
        """Preparing the attributes must not change what an ordinary snapshot file holds."""
        written = json.dumps(_snapshot_codec._encode(_Holder({"a": 1})))
        assert_that(json.loads(written)["__data__"]).is_equal_to({"mapping": {"a": 1}})

    def test_an_enum_whose_value_is_simply_wrong_still_says_so(self):
        marker = {
            "__type__": "enum",
            "__class__": "_TupleColour",
            "__module__": _TupleColour.__module__,
            "__data__": "not a colour",
        }
        with pytest.raises(ValueError, match="not a valid"):
            _snapshot_codec._decode(marker)


class TestASnapshotIdNamesOneFile:
    def test_a_separator_is_refused_by_name(self):
        """It reached the lock file first, and the reader met a FileNotFoundError naming a directory."""
        with pytest.raises(ValueError, match="cannot contain a path separator"):
            assert_that("foo").snapshot(id="group/case")

    def test_an_ordinary_id_still_works(self, tmp_path):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that("foo").snapshot(id="Group Case", path=str(tmp_path))
        assert_that(sorted(entry.name for entry in tmp_path.iterdir())).contains("snap-group_case.json")


class TestWhatIsWrittenIsWrittenWhole:
    """The file is rendered before it is opened, so a value that cannot be encoded leaves nothing behind."""

    def test_the_bytes_are_what_the_encoder_produces(self, tmp_path):
        value = {"a": [1, {2, 3}], "b": decimal.Decimal("1.5")}
        target = tmp_path / "snap.json"
        _save(str(target), value, keyed=False)
        expected = json.dumps(_snapshot_codec._encode(value), indent=2, separators=(",", ": "), sort_keys=True)
        assert_that(target.read_text()).is_equal_to(expected)

    def test_a_value_the_encoder_refuses_leaves_no_file(self, tmp_path):
        class Refusing:
            @property
            def __dict__(self):
                raise RuntimeError("no state from me")

        target = tmp_path / "snap.json"
        with contextlib.suppress(Exception):
            _save(str(target), {"a": Refusing()}, keyed=False)
        assert_that(sorted(entry.name for entry in tmp_path.iterdir())).is_empty()


class TestASnapshotThroughCheckOrNot:
    """`check()` and `not_` run an assertion through a wrapper of this package.

    One hop up from the snapshot was that wrapper, so `check().snapshot()` was keyed by a line of
    `assertpy.py` and every such call in a run shared one key.  Under `not_` the verdict is inverted, so a
    snapshot created or rewritten there holds the value the negation is asked to differ from.
    """

    def test_check_keys_it_by_the_line_of_the_test(self, tmp_path):
        line = sys._getframe().f_lineno + 2
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(assert_that(1).check().snapshot(path=str(tmp_path)).passed).is_true()
        assert_that(_load(_snapshot._name(str(tmp_path), "test_snapshots"))).is_equal_to({str(line): 1})

    def test_not_does_not_create_one(self, tmp_path):
        snapname = _snapshot._name(str(tmp_path), "never")
        with pytest.raises(AssertionFailure) as failure:
            assert_that(1).not_.snapshot(id="never", path=str(tmp_path))
        assert_that(failure.value._outcome.message).is_equal_to(
            f"snapshot <{snapname}> does not exist, and not_ cannot create one; create it without not_"
        )
        assert_that(os.path.exists(snapname)).is_false()

    def test_not_keeps_a_stale_one_under_update_mode(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).snapshot(id="kept", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"a": 2}).not_.snapshot(id="kept", path=str(tmp_path))
        assert_that(_load(_snapshot._name(str(tmp_path), "kept"))).is_equal_to({"a": 1})

    def test_not_does_not_create_a_contract(self, tmp_path):
        with pytest.raises(AssertionFailure, match="not_ cannot create one"):
            assert_that({"a": 1}).not_.matches_contract_snapshot(id="never", path=str(tmp_path))
        assert_that(os.path.exists(_snapshot._name(str(tmp_path), "never"))).is_false()

    def test_not_keeps_a_drifted_contract_under_update_mode(self, tmp_path, monkeypatch):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that({"a": 1}).matches_contract_snapshot(id="shape", path=str(tmp_path))
        stored = _load(_snapshot._name(str(tmp_path), "shape"))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        assert_that({"b": "x"}).not_.matches_contract_snapshot(id="shape", path=str(tmp_path))
        assert_that(_load(_snapshot._name(str(tmp_path), "shape"))).is_equal_to(stored)
