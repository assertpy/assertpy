"""Hold the typed surface as a consumer receives it, from an installed wheel rather than this checkout.

Every other typing gate reads the working tree, where `py.typed` and the `_engine` package are present
because they are files on disk.  A consumer gets whatever the wheel contains, and the two are the same
only for as long as the packaging says so.  Dropping `py.typed` from the build, or excluding a
subpackage, turns the whole typed surface into `Unknown` for every user while every gate here stays
green: the checkers would still be reading the checkout.

Deliberately small.  What the overloads resolve to is `tests/typing_integrations.py`'s question and it
is answered against real libraries there.  This one asks whether a checker can see them at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import venv
from typing import TYPE_CHECKING

import pytest

from tests.optional import needs

if TYPE_CHECKING:
    import pathlib

needs("mypy", delegated_to="the lint job")

from assertpy import assert_that
from tests import typing_harness

# no capability, so the answer names the narrowed view: a checker reading nothing would answer `Any`
_CONSUMER = """from typing import assert_type

from assertpy import assert_that
from assertpy._engine._typing import _ObjectAssertion, _StringAssertion


class Plain:
    name: str


def resolution(plain: Plain, text: str) -> None:
    assert_type(assert_that(plain), _ObjectAssertion[Plain])
    assert_type(assert_that(text), _StringAssertion)
    assert_that(plain).is_positive()
"""


@pytest.fixture(scope="module")
def consumer(tmp_path_factory) -> tuple[pathlib.Path, pathlib.Path]:
    """A throwaway environment with the wheel installed, plus a file that uses the typed surface."""
    root = tmp_path_factory.mktemp("wheel")
    # the executable, not `-m uv`: uv is not a module in the environment it manages, and this skipped silently
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on PATH, so the wheel cannot be built here")
    built = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(root)],
        capture_output=True,
        text=True,
        cwd=typing_harness.ROOT,
        check=False,
    )
    wheels = sorted(root.glob("*.whl"))
    if built.returncode or not wheels:
        pytest.fail(f"the wheel could not be built: {(built.stderr or built.stdout)[-400:]}")
    environment = root / "venv"
    venv.create(environment, with_pip=True)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", str(wheels[0])], check=True)
    source = root / "consumer.py"
    source.write_text(_CONSUMER, encoding="utf-8")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "mypy"], check=True)
    return python, source


def test_a_checker_reading_the_installed_wheel_sees_the_typed_surface(consumer) -> None:
    python, source = consumer
    # `--follow-imports=silent`, as the other gates use: `--strict` would report the installed internals
    output = typing_harness.run(
        "mypy",
        "--strict",
        "--follow-imports=silent",
        "--python-executable",
        str(python),
        str(source),
        cwd=source.parent,
        python=str(python),
    )
    assert_that(output).described_as("the narrowing is not visible to a consumer").contains(
        '"_ObjectAssertion[Plain]" has no attribute "is_positive"'
    )
    # an unresolved import or a missing `py.typed` lands here, which is the packaging mistake this catches
    other = [
        line for line in output.splitlines() if ": error:" in line and source.name in line and "is_positive" not in line
    ]
    assert_that(other).described_as("the wheel is missing something a checker needs").is_empty()
