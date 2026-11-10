"""The suite has to pass without any one optional dependency, and CI has to try each of them.

A distribution packages the suite with whatever subset of the optional libraries it carries, and the cells that
install everything cannot see a test that reads one of those libraries without saying so.  The `absent` job runs
the suite from the sdist once without each optional distribution, and `scripts/optional_dependencies.py` is what
says which distributions those are and what leaves with each.  What this file stops is a library added later that
gets no cell, a cell left behind for a library that is gone, and a wrong reading of the project file that would
make both lists agree on the wrong thing.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from assertpy import assert_that
from tests.optional import needs

if TYPE_CHECKING:
    from types import ModuleType

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_MATRIX = re.compile(
    r"^  absent:\n.*?^        distribution:\n(?P<cells>(?:^          - \S+\n)+)", re.MULTILINE | re.DOTALL
)


def _scripts(name: str) -> ModuleType:
    """Import a script, which lives outside the package, only where it is needed.

    A mutation run copies the package and the tests and not `scripts/`, so a module-level import of it fails at
    collection, which takes the whole mutation baseline with it.
    """
    sys.path.insert(0, str(_ROOT / "scripts"))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(_ROOT / "scripts"))


class _Dist:
    """What `closure()` reads of an installed distribution: its name, requirements, files and declared top level."""

    def __init__(self, name: str, requires: list[str] | None = None, files: list[str] | None = None) -> None:
        self.metadata = {"Name": name}
        self.requires = requires or []
        self.files = [pathlib.PurePosixPath(file) for file in files or []]

    def read_text(self, filename: str) -> str | None:
        return None


def _cells() -> list[str]:
    found = _MATRIX.search(_WORKFLOW.read_text(encoding="utf-8"))
    if found is None:
        raise RuntimeError(f"no `absent` matrix parsed out of {_WORKFLOW.name}, so this file proves nothing")
    return [line.removeprefix("          - ") for line in found["cells"].splitlines()]


@pytest.fixture(scope="module")
def dependencies() -> ModuleType:
    return _scripts("optional_dependencies")


def test_every_optional_distribution_has_a_cell_of_its_own(dependencies: ModuleType) -> None:
    """For the interpreter and the platform the cells run on."""
    optional = dependencies.optional(dependencies.environment("3.14", "linux"))
    assert_that(_cells()).described_as("the `absent` cells against the optional distributions").is_equal_to(optional)


class TestWhatIsOptional:
    """Read off `pyproject.toml`: the extras, opened up, and the groups the suite reads, less what it requires."""

    def test_an_extra_naming_the_projects_own_extras_brings_theirs(self, dependencies: ModuleType) -> None:
        extras = {"data": ["assertpy[numpy,pandas]"], "numpy": ["numpy>=1.26"], "pandas": ["pandas>=2.0"]}
        named = [requirement.name for requirement in dependencies._extra(extras, "data", set())]
        assert_that(named).is_equal_to(["numpy", "pandas"])

    def test_an_included_group_is_opened_up_once(self, dependencies: ModuleType) -> None:
        groups = {"test": ["pytest"], "dev": [{"include-group": "test"}, "ruff", {"include-group": "test"}]}
        named = [requirement.name for requirement in dependencies._group(groups, "dev", set())]
        assert_that(named).is_equal_to(["pytest", "ruff"])

    def test_the_test_group_and_the_projects_own_dependencies_are_never_optional(
        self, dependencies: ModuleType
    ) -> None:
        optional = dependencies.optional(dependencies.environment("3.14", "linux"))
        assert_that(optional).does_not_contain("pytest", "hypothesis", "assertpy").contains("jsonpath-ng", "ruff", "ty")

    def test_a_dependency_behind_a_marker_is_optional_only_where_the_marker_leaves_it_out(
        self, dependencies: ModuleType
    ) -> None:
        """`typing-extensions` is the package's own below 3.11 and only a test helper above."""
        assert_that(dependencies.optional(dependencies.environment("3.14", "linux"))).contains("typing-extensions")
        assert_that(dependencies.optional(dependencies.environment("3.10", "linux"))).does_not_contain(
            "typing-extensions"
        )


class TestWhatLeavesWithADistribution:
    """Read off the metadata of the environment this suite runs in."""

    def test_what_requires_it_leaves_with_it(self, dependencies: ModuleType) -> None:
        needs("pandas")
        leaving = dependencies.closure(["numpy"])
        assert_that(leaving["distributions"]).contains("numpy", "pandas")
        assert_that(leaving["modules"]).contains("numpy", "pandas")

    def test_what_it_requires_stays(self, dependencies: ModuleType) -> None:
        needs("pandas")
        assert_that(dependencies.closure(["pandas"])["distributions"]).does_not_contain("numpy")

    def test_a_distribution_that_is_not_installed_is_refused(self, dependencies: ModuleType) -> None:
        with pytest.raises(SystemExit, match="not installed here"):
            dependencies.closure(["a-distribution-nobody-installed"])

    def test_a_requirement_behind_an_extra_is_not_followed(self, dependencies: ModuleType) -> None:
        """`assertpy[json]` asks for jsonpath-ng, and assertpy without it is the very case a cell runs."""
        lines = ['jsonpath-ng>=1.8; extra == "json"', "packaging>=24", "colorama; sys_platform == 'nobody'"]
        held = [requirement.name for requirement in dependencies._holding(lines, frozenset())]
        assert_that(held).is_equal_to(["packaging"])

    def test_an_extra_asked_of_another_distribution_is_followed(self, dependencies: ModuleType) -> None:
        """`a` requires `b[feature]`, and `b` lists `c` under it: without `c`, `a` cannot stay, while `b` can."""
        installed = {
            "a": _Dist("a", requires=["b[feature]"]),
            "b": _Dist("b", requires=['c; extra == "feature"']),
            "c": _Dist("c"),
        }
        assert_that(dependencies.closure(["c"], installed)["distributions"]).is_equal_to(["a", "c"])

    def test_a_namespace_shared_with_what_stays_leaves_only_below_it(self, dependencies: ModuleType) -> None:
        installed = {
            "ns-a": _Dist("ns-a", files=["ns/a/__init__.py"]),
            "ns-b": _Dist("ns-b", files=["ns/b/__init__.py"]),
            "solo": _Dist("solo", requires=["ns-a"], files=["solo.cpython-314-x86_64-linux-gnu.so"]),
        }
        assert_that(dependencies.closure(["ns-a"], installed)["modules"]).is_equal_to(["ns.a", "solo"])

    def test_a_namespace_shared_further_down_is_opened_as_far_as_it_is_shared(self, dependencies: ModuleType) -> None:
        installed = {
            "ns-a": _Dist("ns-a", files=["ns/shared/a/__init__.py"]),
            "ns-b": _Dist("ns-b", files=["ns/shared/b/__init__.py", "ns/own.py"]),
        }
        assert_that(dependencies.closure(["ns-b"], installed)["modules"]).is_equal_to(["ns.own", "ns.shared.b"])

    def test_the_groups_no_run_installs_are_named_and_nothing_optional_is(self, dependencies: ModuleType) -> None:
        """The checkers' tests skip as delegated, and a run told what is absent is told of these."""
        never = dependencies.never_installed()
        assert_that(never).contains("pyright", "mypy", "pyrefly")
        optional = {name.replace("-", "_") for name in dependencies.optional()}
        assert_that(sorted(optional & set(never))).is_empty()

    @pytest.mark.parametrize("required", ["pytest", "packaging", "assertpy"])
    def test_what_the_suite_requires_cannot_leave(self, dependencies: ModuleType, required: str) -> None:
        """`packaging` by way of pytest, which requires it."""
        with pytest.raises(SystemExit, match="cannot be absent"):
            dependencies.closure([required])


def test_an_exported_line_for_what_leaves_is_dropped_and_the_rest_kept() -> None:
    check = _scripts("check_sdist")
    exported = "# header\nNumPy==2.1.0\n    # via pandas\npandas==2.3.3 ; python_version >= '3.10'\nsix==1.17.0\n"
    assert_that(check._kept(exported, {"numpy", "pandas"})).is_equal_to("# header\n    # via pandas\nsix==1.17.0\n")


def test_a_module_still_importable_after_it_was_taken_away_stops_the_cell() -> None:
    check = _scripts("check_sdist")
    gone = subprocess.run(
        [sys.executable, "-c", check._GONE, json.dumps(["json", "a_module_nobody_installed"])],
        capture_output=True,
        text=True,
        check=False,
    )
    assert_that(gone.returncode).is_not_equal_to(0)
    assert_that(gone.stderr).contains("still importable", "json").does_not_contain("a_module_nobody_installed")
