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

from assertpy import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent

_SUITE = """
import pytest

pytest.importorskip("a_module_that_is_not_installed")


def test_never_reached():
    raise AssertionError
"""


_PASSES = """
def test_ok():
    assert True
"""


def _run(tmp_path: pathlib.Path, *extra: str, suite: str = _SUITE) -> subprocess.CompletedProcess[str]:
    folder = tmp_path / "child"
    folder.mkdir()
    # a second passing file, so the exit code reports the guard and not pytest's "nothing was collected"
    (folder / "test_absent.py").write_text(suite, encoding="utf-8")
    (folder / "test_present.py").write_text(_PASSES, encoding="utf-8")
    # a root of its own: with none the child takes the folder it shares with this checkout and walks down from it
    (folder / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    # its own coverage database: the child runs from the root, and a shared one would pad the gate under test
    environment = {**os.environ, "COVERAGE_FILE": str(tmp_path / ".coverage")}
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(folder), "-q", "-p", "tests.conftest", "-p", "no:cacheprovider", *extra],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=environment,
        check=False,
    )


def test_a_run_claiming_completeness_fails_on_a_missing_module(tmp_path):
    """The coverage floor is the claim: only the cell that enforces it promises every gate ran."""
    result = _run(tmp_path, "--cov=assertpy", "--cov-fail-under=1")
    assert_that(result.returncode).described_as("exit code").is_equal_to(1)
    assert_that(result.stdout).described_as("the report").contains(
        "gates skipped for a missing module", "a_module_that_is_not_installed"
    )


def test_a_skip_that_says_why_is_left_alone(tmp_path):
    """The seam between an accident and a decision: a hand-written reason replaces pytest's own wording.

    A few gates are delegated on purpose, the checkers to the lint job and allure and behave to their own,
    and those say so where they skip.  Writing the reason is what makes the difference visible in the
    source rather than in a register somewhere else.
    """
    reasoned = _SUITE.replace(
        'importorskip("a_module_that_is_not_installed")',
        'importorskip("a_module_that_is_not_installed", reason="delegated to another job")',
    )
    result = _run(tmp_path, "--cov=assertpy", "--cov-fail-under=1", suite=reasoned)
    said = f"exit code, the child having said: {result.stdout[-1500:]} {result.stderr[-1500:]}"
    assert_that(result.returncode).described_as(said).is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


def test_a_partial_run_is_left_alone(tmp_path):
    """Without that claim the same skip is an ordinary partial run, which contributors do all day."""
    result = _run(tmp_path, "--no-cov")
    assert_that(result.returncode).described_as("exit code").is_equal_to(0)
    assert_that(result.stdout).described_as("the report").does_not_contain("gates skipped for a missing module")


def test_the_child_reads_nothing_above_its_own_folder(tmp_path):
    """What made these three fail about once in thirty runs of the suite, with exit code 2.

    Started on a folder elsewhere and given no configuration, the child took as its root the nearest folder
    it shares with this checkout, the user's home, and collected its way down from there through the system
    temp folder.  The type checker run by other tests makes and removes folders in it, and one that went
    between the listing and the look at it failed the collection.  A conftest above the child that cannot
    be imported stands in for that here: a child with a root of its own never reads it.
    """
    (tmp_path / "conftest.py").write_text("raise RuntimeError('a folder above the child was read')\n", encoding="utf-8")
    result = _run(tmp_path, "--no-cov")
    said = f"exit code, the child having said: {result.stdout[-1500:]} {result.stderr[-1500:]}"
    assert_that(result.returncode).described_as(said).is_equal_to(0)


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


# the checkers, named rather than read off the dependency groups, which do not line up: `typecheck` also
# holds stubs, `ty` sits in `dev`, and the coverage cell leaves `typecheck` out
_DELEGATED = frozenset({"pyright", "mypy", "pyrefly", "ty"})


def test_every_checker_skip_says_why_it_is_delegated() -> None:
    """The class, not the instance.

    Four files were given the reason by hand and two were missed, because the list was typed out rather
    than swept, and the guard went red in CI on exactly those two.  Read from the source instead, over
    the whole tree rather than its top level, so a file added later is read too.

    It recognises the one spelling this suite uses, `<anything>.importorskip("name", reason=...)`.  A
    bare `importorskip` imported from pytest, or a module name passed as a keyword or computed, goes
    unseen; a positional reason is seen and reported as missing.  Neither shape appears here.
    """
    tests = pathlib.Path(__file__).resolve().parent
    unexplained = []
    for path in sorted(tests.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "importorskip":
                continue
            first = node.args[0] if node.args else None
            named = isinstance(first, ast.Constant) and first.value in _DELEGATED
            if named and not any(keyword.arg == "reason" for keyword in node.keywords):
                unexplained.append(f"{path.name}:{node.lineno} {first.value}")
    assert_that(unexplained).described_as("checker skips with no reason written").is_empty()
