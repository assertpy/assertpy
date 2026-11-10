"""The suite's optional dependencies, and the one way a test says it needs one.

The suite runs from the sdist on whatever a distribution packages, and the `test` dependency group is all it
requires.  Every other library is optional, and a test that reads one has to skip where it is absent rather than
fail.  `needs()`, or the `needs` marker, which calls it, is how a test says so.  Its skip names the module in a
fixed form, which the guard in `tests/conftest.py` reads back off the report: the reason is the one part of a
report that reaches the controller from a collection skip and from an xdist worker alike.

A module that is present and fails to import is not a skip.  Only the module itself being missing is: a library
installed without one of its own dependencies is a broken environment, and skipping there would hide it.
"""

from __future__ import annotations

import importlib
import re
from typing import TYPE_CHECKING, NoReturn

import pytest
from packaging.version import Version

if TYPE_CHECKING:
    from types import ModuleType

RECORD = "needs"
"""The `user_properties` key a test writes when it leaves cases out for an absent module instead of skipping."""

REASON = re.compile(
    r"(?:Skipped: )?needs (?P<module>[A-Za-z_][\w.]*)(?:>=(?P<minversion>\S+))?"
    r"(?: \(delegated to (?P<delegated>[^)]+)\))?: "
)
"""The reason `needs()` skips with, as the guard reads it: a runtime skip's reason arrives behind `Skipped: `."""


def needs(module: str, *, minversion: str | None = None, why: str = "", delegated_to: str = "") -> ModuleType:
    """Import *module*, or skip the test, or the whole file when called at its top, where it is missing.

    *minversion* skips where an older release is installed, read off its `__version__` as `importorskip`
    reads it.  *delegated_to* names the job that installs the module where this run does not: the coverage
    cell, which otherwise refuses every skip of this kind, accepts that one.
    """
    try:
        found = importlib.import_module(module)
    except ModuleNotFoundError as error:
        _skip(_absent(module, error), "", why or "not installed", delegated_to)
    if minversion is not None:
        installed = getattr(found, "__version__", None)
        if installed is None or Version(installed) < Version(minversion):
            _skip(module, minversion, why or f"{installed} is older than {minversion}", delegated_to)
    return found


def missing(module: str, node: pytest.Item) -> bool:
    """Whether *module* is absent, in which case the test leaves its cases out and *node* records that it did.

    For a test that runs on with fewer cases rather than skipping: the record is what the guard reads, so a
    case dropped quietly in a run that claims every dependency is installed still fails that run.
    """
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as error:
        node.user_properties.append((RECORD, _absent(module, error)))
        return True
    return False


def _absent(module: str, error: ModuleNotFoundError) -> str:
    """The module missing, where it is *module* or a package holding it, and the error raised again where not."""
    name = error.name or ""
    if name and (module == name or module.startswith(f"{name}.")):
        return name
    raise error


def _skip(module: str, minversion: str, why: str, delegated_to: str) -> NoReturn:
    required = f">={minversion}" if minversion else ""
    delegated = f" (delegated to {delegated_to})" if delegated_to else ""
    pytest.skip(f"needs {module}{required}{delegated}: {why}", allow_module_level=True)
