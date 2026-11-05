"""Where a snapshot without ``path=`` is kept: the working directory, or beside its test file (assertpy#88).

Two test files of one name in two folders shared one file in ``__snapshots`` of the working directory, and a
run started in another directory created a second one.  ``assertpy_snapshot_layout = beside`` keeps each
beside its own test file; the default stays as it was.
"""

import os
import pathlib
import subprocess
import sys

import pytest

from assertpy import SnapshotCreatedWarning, assert_that
from assertpy import snapshot as _snapshot


def _check(test_file: pathlib.Path, source: str) -> None:
    """Run ``check()`` from *source* as if it were written in *test_file*, which is the file a snapshot keys on."""
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(source, encoding="utf-8")
    namespace: dict = {"assert_that": assert_that}
    exec(compile(source, str(test_file), "exec"), namespace)
    namespace["check"]()


_LINE = "def check():\n    assert_that({'v': VALUE}).snapshot()\n"
_ID = "def check():\n    assert_that({'v': VALUE}).snapshot(id='shared')\n"
_CONTRACT = "def check():\n    assert_that({'v': VALUE}).matches_contract_snapshot()\n"


@pytest.fixture
def beside(monkeypatch):
    monkeypatch.setattr(_snapshot, "_LAYOUT", "beside")


@pytest.fixture
def working_directory(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.chdir(run)
    monkeypatch.setattr(_snapshot, "_CI_MODE", False)
    return run


def _files(root: pathlib.Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("snap-*.json"))


class TestTheDefault:
    def test_keeps_two_test_files_of_one_name_in_one_file_in_the_working_directory(self, tmp_path, working_directory):
        with pytest.warns(SnapshotCreatedWarning):
            _check(tmp_path / "a" / "test_same.py", _LINE.replace("VALUE", "1"))
        _check(tmp_path / "b" / "test_same.py", _LINE.replace("VALUE", "1"))
        assert_that(_files(tmp_path)).is_equal_to(["run/__snapshots/snap-test_same.json"])


class TestBeside:
    def test_keeps_each_test_files_snapshots_beside_it(self, tmp_path, working_directory, beside):
        for folder, value in (("a", "1"), ("b", "2")):
            with pytest.warns(SnapshotCreatedWarning):
                _check(tmp_path / folder / "test_same.py", _LINE.replace("VALUE", value))
        assert_that(_files(tmp_path)).is_equal_to(
            ["a/__snapshots/snap-test_same.json", "b/__snapshots/snap-test_same.json"]
        )
        _check(tmp_path / "a" / "test_same.py", _LINE.replace("VALUE", "1"))
        _check(tmp_path / "b" / "test_same.py", _LINE.replace("VALUE", "2"))

    def test_an_id_is_kept_beside_its_test_too(self, tmp_path, working_directory, beside):
        with pytest.warns(SnapshotCreatedWarning):
            _check(tmp_path / "a" / "test_one.py", _ID.replace("VALUE", "1"))
        assert_that(_files(tmp_path)).is_equal_to(["a/__snapshots/snap-shared.json"])

    def test_a_contract_is_kept_beside_its_test_too(self, tmp_path, working_directory, beside):
        with pytest.warns(SnapshotCreatedWarning):
            _check(tmp_path / "a" / "test_one.py", _CONTRACT.replace("VALUE", "1"))
        assert_that(_files(tmp_path)).is_equal_to(["a/__snapshots/snap-test_one.json"])

    def test_a_path_given_is_read_from_the_working_directory_as_before(self, tmp_path, working_directory, beside):
        source = "def check():\n    assert_that({'v': 1}).snapshot(path='kept')\n"
        with pytest.warns(SnapshotCreatedWarning):
            _check(tmp_path / "a" / "test_one.py", source)
        source = "def check():\n    assert_that({'v': 1}).snapshot(id='named', path='kept')\n"
        with pytest.warns(SnapshotCreatedWarning):
            _check(tmp_path / "a" / "test_one.py", source)
        assert_that(_files(tmp_path)).is_equal_to(["run/kept/snap-named.json", "run/kept/snap-test_one.json"])

    def test_the_same_run_from_another_directory_reads_the_same_file(self, tmp_path, monkeypatch, beside):
        monkeypatch.setattr(_snapshot, "_CI_MODE", False)
        for started_in in ("first", "second"):
            (tmp_path / started_in).mkdir()
            monkeypatch.chdir(tmp_path / started_in)
            if started_in == "first":
                with pytest.warns(SnapshotCreatedWarning):
                    _check(tmp_path / "a" / "test_one.py", _LINE.replace("VALUE", "1"))
            else:
                _check(tmp_path / "a" / "test_one.py", _LINE.replace("VALUE", "1"))
        assert_that(_files(tmp_path)).is_equal_to(["a/__snapshots/snap-test_one.json"])


class TestAFileThatIsNotOnDisk:
    @pytest.mark.parametrize("written_in", ["<string>", "relative/test_one.py"])
    def test_is_refused_a_place_beside_it(self, tmp_path, working_directory, beside, written_in):
        namespace: dict = {"assert_that": assert_that}
        exec(compile(_LINE.replace("VALUE", "1"), written_in, "exec"), namespace)
        raised: Exception | None = None
        try:
            namespace["check"]()
        except (ValueError, OSError) as refused:
            raised = refused
        assert_that(type(raised)).is_same_as(ValueError)
        assert_that(str(raised)).contains("is no file on disk: give this call a path=")
        assert_that(_files(tmp_path)).is_empty()


class TestTheObsoleteSweep:
    def test_reads_one_file_reached_by_two_spellings_as_one(self, tmp_path, working_directory):
        (working_directory / "__snapshots").mkdir()
        target = working_directory / "__snapshots" / "snap-test_one.json"
        target.write_text('{"2": 1, "5": 2}', encoding="utf-8")
        touched = {(str(target), "2"), ("__snapshots/snap-test_one.json", "5")}
        assert_that(_snapshot._find_orphans(touched)).is_equal_to(([], []))

    def test_still_finds_a_key_and_a_file_no_spelling_reached(self, tmp_path, working_directory):
        (working_directory / "__snapshots").mkdir()
        target = working_directory / "__snapshots" / "snap-test_one.json"
        target.write_text('{"2": 1, "5": 2, "9": 3}', encoding="utf-8")
        (working_directory / "__snapshots" / "snap-test_gone.json").write_text('{"1": 1}', encoding="utf-8")
        touched = {(str(target), "2"), ("__snapshots/snap-test_one.json", "5")}
        # reported by the spelling read first, the absolute one here
        assert_that(_snapshot._find_orphans(touched)).is_equal_to(
            ([(str(target), "9")], [str(working_directory / "__snapshots" / "snap-test_gone.json")])
        )


class TestTheObsoleteSweepAfterTheRun:
    def test_reads_a_name_where_it_was_reached_though_the_working_directory_moved(
        self, tmp_path, working_directory, monkeypatch
    ):
        (working_directory / "__snapshots").mkdir()
        target = working_directory / "__snapshots" / "snap-test_one.json"
        target.write_text('{"2": 1, "5": 2}', encoding="utf-8")
        monkeypatch.setattr(_snapshot, "_TOUCHED", set())
        _snapshot._record_access(str(target), "2", "test_one.py:2")
        _snapshot._record_access(os.path.join("__snapshots", "snap-test_one.json"), "5", "test_one.py:5")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        sub_orphans, whole_orphans = _snapshot._find_orphans(set(_snapshot._TOUCHED))
        assert_that(sub_orphans + whole_orphans).is_empty()

    def test_reads_one_file_reached_through_a_link_to_its_folder_as_one(self, tmp_path, working_directory):
        real = working_directory / "real"
        (real / "__snapshots").mkdir(parents=True)
        (real / "__snapshots" / "snap-test_one.json").write_text('{"2": 1, "5": 2}', encoding="utf-8")
        try:
            (working_directory / "alias").symlink_to(real, target_is_directory=True)
        except OSError:
            pytest.skip("this system does not let the test make a symbolic link")
        touched = {
            (str(real / "__snapshots" / "snap-test_one.json"), "2"),
            (str(working_directory / "alias" / "__snapshots" / "snap-test_one.json"), "5"),
        }
        assert_that(_snapshot._find_orphans(touched)).is_equal_to(([], []))


class TestALinkToASnapshotFile:
    @pytest.mark.parametrize("target_in", ["the same folder", "another folder"])
    def test_reached_through_the_link_is_live(self, tmp_path, working_directory, target_in):
        folder = working_directory / "__snapshots"
        folder.mkdir()
        target_folder = folder if target_in == "the same folder" else working_directory / "kept"
        target_folder.mkdir(exist_ok=True)
        target = target_folder / "snap-real.json"
        target.write_text('{"2": 1}', encoding="utf-8")
        try:
            (folder / "snap-alias.json").symlink_to(target)
        except OSError:
            pytest.skip("this system does not let the test make a symbolic link")
        touched = {(str(folder / "snap-alias.json"), "2")}
        assert_that(_snapshot._find_orphans(touched)).is_equal_to(([], []))

    def test_its_folder_is_read_once_beside_a_file_of_its_own(self, tmp_path, working_directory):
        folder = working_directory / "__snapshots"
        (working_directory / "kept").mkdir()
        folder.mkdir()
        target = working_directory / "kept" / "snap-real.json"
        target.write_text('{"2": 1}', encoding="utf-8")
        (folder / "snap-own.json").write_text('{"2": 1}', encoding="utf-8")
        (folder / "snap-gone.json").write_text('{"2": 1}', encoding="utf-8")
        try:
            (folder / "snap-alias.json").symlink_to(target)
        except OSError:
            pytest.skip("this system does not let the test make a symbolic link")
        touched = {(str(folder / "snap-alias.json"), "2"), (str(folder / "snap-own.json"), "2")}
        assert_that(_snapshot._find_orphans(touched)).is_equal_to(([], [str(folder / "snap-gone.json")]))

    def test_and_its_target_both_reached_read_both_folders_once_each(self, tmp_path, working_directory):
        alias_folder, target_folder = working_directory / "a", working_directory / "b"
        alias_folder.mkdir()
        target_folder.mkdir()
        target = target_folder / "snap-real.json"
        target.write_text('{"2": 1, "9": 1}', encoding="utf-8")
        (target_folder / "snap-gone.json").write_text('{"2": 1}', encoding="utf-8")
        try:
            (target_folder / "snap-link.json").symlink_to(target)
            (alias_folder / "snap-alias.json").symlink_to(target)
        except OSError:
            pytest.skip("this system does not let the test make a symbolic link")
        touched = {(str(alias_folder / "snap-alias.json"), "2"), (str(target), "2")}
        sub_orphans, whole_orphans = _snapshot._find_orphans(touched)
        assert_that([key for _, key in sub_orphans]).is_equal_to(["9"])
        assert_that(whole_orphans).is_equal_to([str(target_folder / "snap-gone.json")])


class TestASnapshotOfTheSameNameElsewhere:
    def test_kept_in_the_working_directory_is_named_by_a_run_that_keeps_it_beside(
        self, tmp_path, working_directory, beside
    ):
        (working_directory / "__snapshots").mkdir()
        (working_directory / "__snapshots" / "snap-test_one.json").write_text('{"2": {"v": 1}}', encoding="utf-8")
        with pytest.warns(SnapshotCreatedWarning) as warned:
            _check(tmp_path / "a" / "test_one.py", _LINE.replace("VALUE", "1"))
        message = str(warned[0].message)
        assert_that(message).contains(
            "A snapshot of this name is kept at <__snapshots", "move it here to keep its values"
        )

    def test_kept_beside_its_test_is_named_by_a_run_that_keeps_it_in_the_working_directory(
        self, tmp_path, working_directory
    ):
        (tmp_path / "a" / "__snapshots").mkdir(parents=True)
        (tmp_path / "a" / "__snapshots" / "snap-test_one.json").write_text('{"2": {"v": 1}}', encoding="utf-8")
        with pytest.warns(SnapshotCreatedWarning) as warned:
            _check(tmp_path / "a" / "test_one.py", _LINE.replace("VALUE", "1"))
        assert_that(str(warned[0].message)).contains("kept beside its test", "set that to read it")

    def test_is_named_for_a_contract_too(self, tmp_path, working_directory, beside):
        (working_directory / "__snapshots").mkdir()
        (working_directory / "__snapshots" / "snap-test_one.json").write_text('{"2": {}}', encoding="utf-8")
        with pytest.warns(SnapshotCreatedWarning) as warned:
            _check(tmp_path / "a" / "test_one.py", _CONTRACT.replace("VALUE", "1"))
        assert_that(str(warned[0].message)).contains("created contract snapshot", "move it here to keep its values")

    def test_is_named_where_ci_mode_refuses_to_create_one(self, tmp_path, working_directory, monkeypatch, beside):
        monkeypatch.setattr(_snapshot, "_CI_MODE", True)
        (working_directory / "__snapshots").mkdir()
        (working_directory / "__snapshots" / "snap-test_one.json").write_text('{"2": {"v": 1}}', encoding="utf-8")
        with pytest.raises(AssertionError) as refused:
            _check(tmp_path / "a" / "test_one.py", _LINE.replace("VALUE", "1"))
        assert_that(str(refused.value)).contains("CI mode forbids creating it", "move it here to keep its values")

    def test_is_not_named_where_the_setting_it_would_suggest_refuses_the_call(self, tmp_path, working_directory):
        (working_directory / "relative" / "__snapshots").mkdir(parents=True)
        (working_directory / "relative" / "__snapshots" / "snap-test_one.json").write_text("{}", encoding="utf-8")
        namespace: dict = {"assert_that": assert_that}
        exec(compile(_LINE.replace("VALUE", "1"), os.path.join("relative", "test_one.py"), "exec"), namespace)
        with pytest.warns(SnapshotCreatedWarning) as warned:
            namespace["check"]()
        assert_that(str(warned[0].message)).does_not_contain("A snapshot of this name")

    def test_is_not_named_where_the_test_file_sits_in_the_working_directory(self, tmp_path, working_directory, beside):
        with pytest.warns(SnapshotCreatedWarning) as warned:
            _check(working_directory / "test_one.py", _LINE.replace("VALUE", "1"))
        assert_that(str(warned[0].message)).does_not_contain("A snapshot of this name")


def test_a_run_reads_the_layout_from_its_settings(tmp_path):
    for folder, value in (("a", 1), ("b", 2)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "test_same.py").write_text(
            f"from assertpy import assert_that\n\n\ndef test_it():\n    assert_that({{'v': {value}}}).snapshot()\n",
            encoding="utf-8",
        )
    (tmp_path / "pytest.ini").write_text("[pytest]\nassertpy_snapshot_layout = beside\n", encoding="utf-8")
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--assertpy-snapshot-no-ci"]
    command += ["--rootdir", str(tmp_path), "-c", str(tmp_path / "pytest.ini"), "-W", "ignore::UserWarning"]
    command += ["--import-mode=importlib", str(tmp_path)]
    for _ in range(2):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=180, check=False)
        assert_that(result.returncode).described_as(result.stdout + result.stderr).is_zero()
    assert_that(_files(tmp_path)).is_equal_to(
        ["a/__snapshots/snap-test_same.json", "b/__snapshots/snap-test_same.json"]
    )
    stored = {name: (tmp_path / name).read_bytes() for name in _files(tmp_path)}
    for folder in ("a", "b"):
        test_file = tmp_path / folder / "test_same.py"
        test_file.write_text(test_file.read_text(encoding="utf-8").replace("'v': ", "'v': 10 + "), encoding="utf-8")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=180, check=False)
    assert_that(result.stdout).contains("2 failed")
    assert_that({name: (tmp_path / name).read_bytes() for name in _files(tmp_path)}).is_equal_to(stored)
    (tmp_path / "pytest.ini").write_text("[pytest]\nassertpy_snapshot_layout = elsewhere\n", encoding="utf-8")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=180, check=False)
    assert_that(result.stderr).contains("assertpy_snapshot_layout must be cwd or beside, not 'elsewhere'")
