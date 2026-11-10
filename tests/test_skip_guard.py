"""The guard that stops a skipped gate from reading as a passing one.

A dependency that is not installed does not fail a run, it skips it, and a skipped gate leaves no mark
in a green summary.  That cost two red CI runs in one day: `pytest-examples` lives in its own group,
was absent locally, and the whole doc-example file was skipped while the run was reported as passing.

The guard lives in `tests/conftest.py` and is loaded here as a plugin rather than copied, so what these
cases exercise is the shipped one.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

import pytest

from assertpy import assert_that
from tests import optional
from tests.optional import needs

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ABSENT = "a_module_that_is_not_installed"

_SUITE = f"""
from tests.optional import needs

needs("{_ABSENT}")


def test_never_reached():
    raise AssertionError
"""


_PASSES = """
def test_ok():
    assert True
"""

_WAYS = {
    "a whole file": _SUITE,
    "one test": f"""
from tests.optional import needs


def test_one():
    needs("{_ABSENT}")
""",
    "a marker": f"""
import pytest


@pytest.mark.needs("{_ABSENT}")
def test_one():
    raise AssertionError
""",
    "a case left out": f"""
from tests.optional import missing


def test_one(request):
    assert missing("{_ABSENT}", request.node)
""",
}
"""Each way a test can say it needs a module, as a file of its own."""


def _run(
    tmp_path: pathlib.Path, *extra: str, suite: str = _SUITE, told: str | None = None
) -> subprocess.CompletedProcess[str]:
    folder = tmp_path / "child"
    folder.mkdir()
    # a second passing file, so the exit code reports the guard and not pytest's "nothing was collected"
    (folder / "test_absent.py").write_text(suite, encoding="utf-8")
    (folder / "test_present.py").write_text(_PASSES, encoding="utf-8")
    # a root of its own: with none the child takes the folder it shares with this checkout and walks down from it
    (folder / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    # its own coverage database: the child runs from the root, and a shared one would pad the gate under test
    environment = {**os.environ, "COVERAGE_FILE": str(tmp_path / ".coverage")}
    # a cell that took a module away tells its own run, and this child is told only what the case says
    environment.pop("ASSERTPY_SUITE_ABSENT", None)
    if told is not None:
        environment["ASSERTPY_SUITE_ABSENT"] = told
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(folder), "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", *extra],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=environment,
        check=False,
    )


def _said(result: subprocess.CompletedProcess[str]) -> str:
    return f"exit code, the child having said: {result.stdout[-1500:]} {result.stderr[-1500:]}"


def test_a_run_claiming_completeness_fails_on_a_missing_module(tmp_path):
    """The coverage floor is the claim: only the cell that enforces it promises every gate ran."""
    needs("pytest_cov")
    result = _run(tmp_path, "--cov=assertpy", "--cov-fail-under=1")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains("gates skipped for a missing module", _ABSENT)


def test_a_delegated_skip_is_left_alone(tmp_path):
    """The seam between an accident and a decision: a gate run by another job names that job where it skips.

    The checkers are delegated to the lint job and allure and behave to their own, and writing the job down is
    what makes the difference visible in the source rather than in a register somewhere else.
    """
    needs("pytest_cov")
    delegated = _SUITE.replace(f'needs("{_ABSENT}")', f'needs("{_ABSENT}", delegated_to="another job")')
    result = _run(tmp_path, "--cov=assertpy", "--cov-fail-under=1", suite=delegated)
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


def test_a_skip_in_pytests_own_wording_fails_a_claiming_run(tmp_path):
    """It did not go through `needs()`, so it names no module the claim could be checked against."""
    needs("pytest_cov")
    raw = (
        f'import pytest\n\npytest.importorskip("{_ABSENT}")\n\n\ndef test_never_reached():\n    raise AssertionError\n'
    )
    result = _run(tmp_path, "--cov=assertpy", "--cov-fail-under=1", suite=raw)
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains("gates skipped for a missing module", _ABSENT)


def test_a_partial_run_is_left_alone(tmp_path):
    """Without that claim the same skip is an ordinary partial run, which contributors do all day."""
    result = _run(tmp_path, "-p", "no:pytest_cov")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


@pytest.mark.parametrize("way", sorted(_WAYS))
@pytest.mark.parametrize("workers", ["in-process", "distributed"])
def test_every_way_of_saying_it_reaches_the_guard(tmp_path, way, workers):
    """A collection skip, a runtime skip, a marker and a record, and each from an xdist worker as well."""
    distributed = ("-n", "2") if workers == "distributed" else ()
    if distributed:
        needs("xdist")
    result = _run(tmp_path, *distributed, suite=_WAYS[way], told="another_module")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains(
        "gates skipped for a missing module", _ABSENT, "only these modules are absent: another_module"
    )


@pytest.mark.parametrize("way", sorted(_WAYS))
def test_a_run_told_what_was_taken_away_allows_that(tmp_path, way):
    result = _run(tmp_path, suite=_WAYS[way], told=f"another_module,{_ABSENT}")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


_TWO_ABSENT = """
from tests.optional import missing, needs


def test_one(request):
    missing("first_absent_module", request.node)
    needs("second_absent_module")
"""


@pytest.mark.parametrize("allowed", ["first_absent_module", "second_absent_module"])
@pytest.mark.parametrize("workers", ["in-process", "distributed"])
def test_one_allowed_absence_does_not_cover_another_of_the_same_test(tmp_path, allowed, workers):
    """A record and then a skip on one test: whichever the run was told of, the other still fails it."""
    distributed = ("-n", "2") if workers == "distributed" else ()
    if distributed:
        needs("xdist")
    result = _run(tmp_path, *distributed, suite=_TWO_ABSENT, told=allowed)
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    other = ({"first_absent_module", "second_absent_module"} - {allowed}).pop()
    assert_that(result.stdout).described_as("the report").contains(other)


def test_a_second_run_in_one_process_is_judged_on_its_own_reports(tmp_path):
    """A runner calling pytest twice in one process: a skip the first run was free to make is not the second's."""
    needs("pytest_cov")
    first, second = tmp_path / "first", tmp_path / "second"
    for folder, suite in ((first, _SUITE), (second, _PASSES)):
        folder.mkdir()
        (folder / "test_it.py").write_text(suite, encoding="utf-8")
        (folder / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    program = (
        "import sys, pytest; plugins = ['-p', 'tests.conftest', '-p', 'no:cacheprovider', '-q'];"
        f" pytest.main([{str(first)!r}, *plugins]);"
        f" sys.exit(pytest.main([{str(second)!r}, *plugins, '--cov=assertpy', '--cov-fail-under=0']))"
    )
    environment = {**os.environ, "COVERAGE_FILE": str(tmp_path / ".coverage")}
    environment.pop("ASSERTPY_SUITE_ABSENT", None)
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, cwd=_ROOT, env=environment, check=False
    )
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)


@pytest.mark.parametrize("workers", ["in-process", "distributed"])
def test_a_run_told_what_is_absent_allows_no_delegated_skip_it_was_not_told_of(tmp_path, workers):
    """A delegation is the coverage cell's exception: a run told what is absent was told of every module it lacks."""
    distributed = ("-n", "2") if workers == "distributed" else ()
    if distributed:
        needs("xdist")
    delegated = _SUITE.replace(f'needs("{_ABSENT}")', f'needs("{_ABSENT}", delegated_to="another job")')
    result = _run(tmp_path, *distributed, suite=delegated, told="numpy")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains("gates skipped for a missing module", _ABSENT)


def test_a_child_is_not_told_what_the_run_around_it_was_told(tmp_path, monkeypatch):
    """Told of nothing, the skip in the child is an ordinary partial run, whatever this run's own claim is."""
    monkeypatch.setenv("ASSERTPY_SUITE_ABSENT", "another_module")
    result = _run(tmp_path, "-p", "no:pytest_cov")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)


def test_an_older_release_than_a_test_asks_is_never_an_absence(tmp_path):
    """The module is there, so neither claim allows it, whatever the run was told."""
    older = 'from tests.optional import needs\n\nneeds("pytest", minversion="999")\n'
    result = _run(tmp_path, suite=older, told="pytest")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains("needs pytest>=999")


def test_the_child_reads_nothing_above_its_own_folder(tmp_path):
    """What made these three fail about once in thirty runs of the suite, with exit code 2.

    Started on a folder elsewhere and given no configuration, the child took as its root the nearest folder
    it shares with this checkout, the user's home, and collected its way down from there through the system
    temp folder.  The type checker run by other tests makes and removes folders in it, and one that went
    between the listing and the look at it failed the collection.  A conftest above the child that cannot
    be imported stands in for that here: a child with a root of its own never reads it.
    """
    (tmp_path / "conftest.py").write_text("raise RuntimeError('a folder above the child was read')\n", encoding="utf-8")
    result = _run(tmp_path, "-p", "no:pytest_cov")
    assert_that(result.returncode).described_as(_said(result)).is_equal_to(0)


class TestNeeds:
    """`needs()` itself: what it skips on, what it names, and what it lets through."""

    def test_a_missing_module_skips_and_names_itself(self):
        with pytest.raises(pytest.skip.Exception) as skipped:
            needs(_ABSENT)
        said = optional.REASON.match(str(skipped.value))
        assert_that(said).is_not_none()
        assert_that(said["module"]).is_equal_to(_ABSENT)

    def test_a_module_inside_a_missing_package_names_the_package(self):
        with pytest.raises(pytest.skip.Exception, match=f"^needs {_ABSENT}: not installed$"):
            needs(f"{_ABSENT}.inner")

    def test_a_present_module_that_cannot_import_a_dependency_of_its_own_raises(self, tmp_path, monkeypatch):
        """A broken environment, which a skip would hide."""
        (tmp_path / "broken_on_import.py").write_text(f"import {_ABSENT}\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        # a skip is caught too, or one taken for the error would leave this test skipped rather than failed
        with pytest.raises((ModuleNotFoundError, pytest.skip.Exception), match=_ABSENT) as raised:
            needs("broken_on_import")
        assert_that(raised.type).is_same_as(ModuleNotFoundError)

    def test_an_older_release_skips_and_says_what_it_asked(self):
        with pytest.raises(pytest.skip.Exception) as skipped:
            needs("pytest", minversion="999", delegated_to="the lint job")
        said = optional.REASON.match(str(skipped.value))
        assert_that(said).is_not_none()
        assert_that((said["module"], said["minversion"], said["delegated"])).is_equal_to(
            ("pytest", "999", "the lint job")
        )

    def test_a_present_module_is_handed_back(self):
        assert_that(needs("pytest")).is_same_as(pytest)


def _own(function: ast.AST) -> list[ast.AST]:
    """The nodes of a function that are its own: what a function written inside it holds is that one's."""
    found, waiting = [], list(ast.iter_child_nodes(function))
    while waiting:
        node = waiting.pop()
        found.append(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            waiting.extend(ast.iter_child_nodes(node))
    return found


def _says(node: ast.AST, word: str) -> bool:
    return any(getattr(part, "value", None) == word for part in ast.walk(node))


def _rootless(tree: ast.AST) -> list[str]:
    """The functions of a module that start a pytest of their own and give it no root.

    Starting one is a call into `subprocess` that says ``"pytest"``: among its own arguments, or in what the
    same function assigned to a name the call is handed.  A command built any other way is not seen.  Giving
    it a root is a ``(<folder> / "pytest.ini").write_text(...)`` in that same function, or ``--rootdir`` said
    where the command is.  A path that is only named gives nothing, and whether the folder written to is the
    one the child is started on is not read.
    """
    found = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        own = _own(function)
        assigned: dict[str, list[ast.AST]] = {}
        for node in own:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.setdefault(target.id, []).append(node.value)
        writes_one = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"write_text", "write_bytes"}
            and isinstance(node.func.value, ast.BinOp)
            and isinstance(node.func.value.op, ast.Div)
            and getattr(node.func.value.right, "value", None) == "pytest.ini"
            for node in own
        )
        for call in own:
            into_subprocess = (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and getattr(call.func.value, "id", "") == "subprocess"
            )
            if not into_subprocess:
                continue
            handed = [
                value for name in ast.walk(call) if isinstance(name, ast.Name) for value in assigned.get(name.id, [])
            ]
            command = [call, *handed]
            if any(_says(part, "pytest") for part in command) and not (
                writes_one or any(_says(part, "--rootdir") for part in command)
            ):
                found.append(f"{function.lineno} {function.name}")
    return found


def test_every_child_pytest_is_given_a_root_of_its_own() -> None:
    """The class, not the instance, read from the source as the sweep below is."""
    tests = pathlib.Path(__file__).resolve().parent
    rootless = [
        f"{path.name}:{spot}"
        for path in sorted(tests.rglob("*.py"))
        for spot in _rootless(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert_that(rootless).described_as("child pytest runs given no root of their own").is_empty()


_LAUNCH = 'subprocess.run([sys.executable, "-m", "pytest", str(folder)], cwd=ROOT)'


def test_what_the_sweep_of_child_runs_takes_for_a_root() -> None:
    def spots(*lines: str) -> list[str]:
        return _rootless(ast.parse("\n".join(["def run(folder):", *(f"    {line}" for line in lines)])))

    assert_that(spots(_LAUNCH)).is_equal_to(["1 run"])
    assert_that(spots('(folder / "pytest.ini").write_text("[pytest]")', _LAUNCH)).is_empty()
    assert_that(spots(_LAUNCH.replace("str(folder)]", 'str(folder), "--rootdir", str(folder)]'))).is_empty()
    # a name that is only mentioned, a path that is only named, a command put together from pieces or held in
    # a name, a root given by a function inside
    assert_that(spots('marker = "pytest.ini"', _LAUNCH)).is_equal_to(["1 run"])
    assert_that(spots('marker = folder / "pytest.ini"', _LAUNCH)).is_equal_to(["1 run"])
    assert_that(spots('(folder / "pytest.ini").exists()', _LAUNCH)).is_equal_to(["1 run"])
    assert_that(spots('(folder / "notes.txt").write_text("[pytest]")', _LAUNCH)).is_equal_to(["1 run"])
    held = 'command = [sys.executable, "-m", "pytest", str(folder)]'
    assert_that(spots(held, "subprocess.run(command, cwd=ROOT)")).is_equal_to(["1 run"])
    assert_that(spots(held, "subprocess.run([*command, '-q'], cwd=ROOT)")).is_equal_to(["1 run"])
    assert_that(
        spots(held.replace("str(folder)]", 'str(folder), "--rootdir", str(folder)]'), "subprocess.run(command)")
    ).is_empty()
    assert_that(spots('(folder / "pytest.ini").write_bytes(b"[pytest]")', held, "subprocess.run(command)")).is_empty()
    assert_that(spots('subprocess.run([sys.executable] + ["-m"] + ["pytest"], cwd=ROOT)')).is_equal_to(["1 run"])
    assert_that(spots('subprocess.Popen((sys.executable, *("-m", "pytest")))')).is_equal_to(["1 run"])
    inner = ("def write():", '    (folder / "pytest.ini").write_text("[pytest]")')
    assert_that(spots(*inner, _LAUNCH)).is_equal_to(["1 run"])
    assert_that(spots("def start():", f"    {_LAUNCH}")).is_equal_to(["2 start"])
    assert_that(spots('subprocess.run([sys.executable, "-m", "ruff", "check"])')).is_empty()


_DELEGATED = {
    "pyright": "the lint job",
    "mypy": "the lint job",
    "pyrefly": "the lint job",
    "allure": "the optional-integrations job",
    "behave": "the optional-integrations job",
}
"""What the cell enforcing the coverage floor leaves out, by the job that installs it instead."""


def _calls(name: str) -> list[tuple[str, ast.Call]]:
    """Every call of a function or method so named in the tests, over the whole tree, with where it is."""
    tests = pathlib.Path(__file__).resolve().parent
    return [
        (f"{path.name}:{node.lineno}", node)
        for path in sorted(tests.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and name in {getattr(node.func, "attr", None), getattr(node.func, "id", None)}
    ]


def test_no_test_skips_through_importorskip() -> None:
    """The class, not the instance: its reason is free text, and a reason of its own hid the module from the guard."""
    spots = [spot for spot, _ in _calls("importorskip")]
    assert_that(spots).described_as("skips that name no module the guard can read").is_empty()


def test_every_delegated_skip_names_its_job() -> None:
    """Swept rather than listed: given a reason by hand once, two files of six were missed and went red in CI.

    It reads `needs("name", delegated_to="...")` and the marker spelled the same way.  A module name passed as a
    keyword or computed goes unseen.  Neither shape appears here.
    """
    wrong = []
    for spot, call in _calls("needs"):
        first = call.args[0] if call.args else None
        if not isinstance(first, ast.Constant) or first.value not in _DELEGATED:
            continue
        job = next((keyword.value for keyword in call.keywords if keyword.arg == "delegated_to"), None)
        named = job.value if isinstance(job, ast.Constant) else None
        if named != _DELEGATED[first.value]:
            wrong.append(f"{spot} {first.value}: {named}")
    assert_that(wrong).described_as("delegated skips that do not name the job they are delegated to").is_empty()
