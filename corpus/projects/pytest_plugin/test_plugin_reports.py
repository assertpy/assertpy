"""What the pytest plugin prints, read from a child run of a deliberately red suite.

Every other project here calls the library and checks the answer.  This one checks the half that has no
API: hooks that pytest calls, ini options a consumer sets in their own `pyproject.toml`, and the
worker-to-controller transport under `pytest-xdist`.  All of that is written against pytest's internals
and had been exercised only from the repository, where the plugin's own conftest pins its defaults.

The red suite is written into a temporary directory rather than kept beside this file, so this project's
own run stays green and nothing here has to be excluded from collection.
"""

import json
import subprocess
import sys
import textwrap

import pytest

from assertpy import assert_that

RED_SUITE = textwrap.dedent(
    """
    import itertools
    import time

    import pytest

    from assertpy import assert_that

    ROWS = [{"id": index, "role": "guest"} for index in range(4)]


    @pytest.mark.parametrize("row", ROWS)
    def test_role_is_admin(row):
        assert_that(row).is_equal_to({**row, "role": "admin"})


    def test_asserts_nothing():
        assert_that("this statement builds a builder and stops there")


    def test_converges_late():
        attempts = itertools.count(1)

        def probe():
            time.sleep(0.06)
            return "ready" if next(attempts) >= 3 else "waiting"

        # a budget wide enough that a loaded runner still converges inside it, and a threshold low
        # enough that the ratio qualifies whatever the machine's speed: pinning either to a wall-clock
        # figure is how this test would start failing for reasons that are not the plugin
        assert_that(probe).eventually_sync(timeout=5, interval=0.01).is_equal_to("ready")
    """
)

CAPTURING = ("--assertpy-snapshot-no-ci",)

REPORTS = (
    "-o",
    "assertpy_failure_clusters=3",
    "-o",
    "assertpy_dangling=on",
    "-o",
    "assertpy_poll_report=0.01",
)


def run_suite(tmp_path, source, *extra, filename="test_child.py", outcome=pytest.ExitCode.OK, tally="2 passed"):
    """Write a suite into a temporary directory, run it there, and hand back the finished process.

    Nothing here is read before the run's own outcome has been: a child that died in a hook, failed to
    collect, or lost a worker prints whatever was written before it did, and an assertion about a report
    would hold on that while the run it came from was broken.  Every caller says which outcome it
    expects and how the tally should read, because "it printed the heading" is not the same claim.
    """
    (tmp_path / filename).write_text(source, encoding="utf-8")
    command = [sys.executable, "-m", "pytest", filename, "-q", "-p", "no:cacheprovider", *extra]
    finished = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=300, check=False)
    finished.said = finished.stdout + finished.stderr
    assert_that(finished.said).described_as("the plugin took the run down").does_not_contain("INTERNALERROR")
    assert_that(finished.returncode).described_as("how the child ended").is_equal_to(outcome)
    assert_that(finished.said).described_as("what the child ran").contains(tally)
    return finished


def red_run(tmp_path, *extra):
    """Run the red suite in a child process and hand back everything it printed.

    The exit code is checked here rather than left to the caller: a run that died in a hook prints the
    sections that were already written and would satisfy every assertion below it, so "the text is
    there" is only worth reading once the run that produced it ended the way a red run ends.
    """
    finished = run_suite(
        tmp_path,
        RED_SUITE,
        *REPORTS,
        *extra,
        filename="test_red.py",
        outcome=pytest.ExitCode.TESTS_FAILED,
        tally="4 failed, 2 passed",
    )
    return finished.said


def test_the_failure_cluster_summary_needs_no_configuration(tmp_path):
    """The summary out of the box, from a project that wrote no ini file at all.

    Every other cluster test here passes `-o assertpy_failure_clusters=3`, which holds the setting and
    not the default.  A profile turning clustering off again, or the ini losing its default, would leave
    all of them green while an installing project saw nothing.
    """
    finished = run_suite(
        tmp_path,
        RED_SUITE,
        filename="test_red.py",
        outcome=pytest.ExitCode.TESTS_FAILED,
        tally="4 failed, 2 passed",
    )
    assert_that(finished.said).contains("assertpy failure clusters:")
    assert_that(finished.said).contains("4 of 4 failing tests differ at role")


def test_the_failure_cluster_summary_reaches_the_terminal(tmp_path):
    output = red_run(tmp_path)
    assert_that(output).contains("assertpy failure clusters:")
    assert_that(output).contains("4 of 4 failing tests differ at role")
    assert_that(output).contains("actual:   'guest'").contains("expected: 'admin'")


def test_the_structured_diff_section_is_rendered(tmp_path):
    """The plugin's default output, and the only one here that every consumer gets without asking.

    Its section is built from the failure's own `DiffResult` inside a report hook, and until this project
    existed it had been read only from the repository's own test run.
    """
    output = red_run(tmp_path)
    assert_that(output).contains("Structured Diff")
    assert_that(output).contains("diff (dict)").contains("role:")


def test_the_dangling_statement_is_reported(tmp_path):
    output = red_run(tmp_path)
    assert_that(output).contains("asserts nothing")


def test_the_late_poll_is_named(tmp_path):
    output = red_run(tmp_path)
    assert_that(output).contains("assertpy polls that nearly timed out:")
    assert_that(output).contains("converged on attempt 3")


def test_the_summary_survives_the_trip_from_the_workers(tmp_path):
    """The half that only exists under xdist: the controller writes both reports and runs no tests.

    Everything the workers recorded travels as plain lists through execnet, is rebuilt on the controller
    and grouped there.  Both ends live in one file in the repository and are tested against each other;
    this is the only place the transport itself runs, and two different payloads cross it.
    """
    output = red_run(tmp_path, "-n", "2")
    assert_that(output).contains("assertpy failure clusters:")
    assert_that(output).contains("4 of 4 failing tests differ at role")
    assert_that(output).contains("assertpy polls that nearly timed out:")
    assert_that(output).contains("converged on attempt 3")


SHARED_KEY_SUITE = textwrap.dedent(
    """
    import pytest

    from assertpy import assert_that


    @pytest.mark.parametrize("name", ["alice", "bob"])
    def test_user(name):
        assert_that({"name": "same"}).snapshot()   # no id, so both cases key on this line
    """
)

TOUCHING_SUITE = textwrap.dedent(
    """
    from assertpy import assert_that


    def test_alice():
        assert_that({"name": "alice"}).snapshot()


    def test_bob():
        assert_that({"name": "bob"}).snapshot()
    """
)

INLINE_SUITE = textwrap.dedent(
    """
    from assertpy import assert_that


    def test_recorded_here():
        assert_that({"role": "admin"}).matches_inline()
    """
)


def test_a_key_two_workers_reached_is_counted_once_for_the_run(tmp_path):
    """The accesses each worker saw are unioned on the controller, and only the union can count.

    Two parametrised cases on one key are one access per worker under `-n 2`, so no worker ever sees a
    second reach: the warning that says how many tests met the key exists because of that, and this is
    the only place its transport runs.
    """
    finished = run_suite(tmp_path, SHARED_KEY_SUITE, "-n", "2", "-W", "always", *CAPTURING)
    assert_that(finished.said).contains("is shared by 2 tests")


def test_the_orphan_sweep_sees_what_every_worker_touched(tmp_path):
    """A snapshot nobody reaches is removed on an update run, and what was reached came from the workers.

    The controller does the removing and runs no tests, so a worker whose touches never arrived would
    take live snapshots with it.  Checked on the file, not on the report: the removal is the effect.
    """
    run_suite(tmp_path, TOUCHING_SUITE, "-n", "2", *CAPTURING)
    stored = tmp_path / "__snapshots" / "snap-test_child.json"
    recorded = json.loads(stored.read_text(encoding="utf-8"))
    assert_that(recorded).described_as("one key per snapshotting test, keyed by its line").is_length(2)

    recorded["nobody-reaches-this"] = {"stale": True}
    stored.write_text(json.dumps(recorded), encoding="utf-8")
    finished = run_suite(tmp_path, TOUCHING_SUITE, "-n", "2", "--assertpy-snapshot-update", *CAPTURING)
    swept = json.loads(stored.read_text(encoding="utf-8"))
    assert_that(sorted(swept)).described_as("the stale key is gone and the live ones stayed").is_equal_to(
        sorted(set(recorded) - {"nobody-reaches-this"})
    )
    assert_that(finished.said).contains("removed obsolete snapshot")


def test_an_inline_value_recorded_on_a_worker_reaches_the_file(tmp_path):
    """The edit is made by the controller from what the worker recorded, into the worker's own file.

    A worker must not write source: two of them editing one file is how a suite loses a line.  So the
    record travels, and the only proof that it travelled is the file afterwards.
    """
    run_suite(tmp_path, INLINE_SUITE, "-n", "2", "--assertpy-snapshot-update", *CAPTURING, tally="1 passed")
    written = (tmp_path / "test_child.py").read_text(encoding="utf-8")
    assert_that(written).contains("matches_inline({'role': 'admin'})")
