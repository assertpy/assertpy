"""The `assertpy2` bridge in `bridge/` hands out the `assertpy` objects under every name `assertpy2` 2.34 had.

Each question is asked in an interpreter of its own, with the bridge on its path: this one has the package
and its submodules loaded already, and a bare import would answer nothing here.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any

from assertpy import assert_that

_BRIDGE = pathlib.Path(__file__).resolve().parent.parent / "bridge"

_SUBMODULES_OF_2_34 = (
    "assertpy",
    "async_assertions",
    "base",
    "behave_matchers",
    "bytes_mixin",
    "collection",
    "contains",
    "dataframe",
    "date",
    "dict",
    "dynamic",
    "errors",
    "exception",
    "extracting",
    "file",
    "helpers",
    "http_mixin",
    "json_mixin",
    "matchers",
    "numeric",
    "outcome",
    "pytest_plugin",
    "snapshot",
    "string",
    "warning",
)


def _ask(script: str) -> Any:
    path = os.pathsep.join(filter(None, [str(_BRIDGE), os.environ.get("PYTHONPATH")]))
    ran = subprocess.run(
        [sys.executable, "-c", script, *_SUBMODULES_OF_2_34],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": path},
    )
    return json.loads(ran.stdout)


def test_every_old_submodule_is_the_module_of_the_new_name():
    """`from assertpy2.errors import Step` and `-W error::assertpy2.snapshot.<warning>` both rest on this."""
    asked = """
import importlib, json, sys
import assertpy, assertpy2
apart = [name for name in assertpy.__all__ if getattr(assertpy2, name) is not getattr(assertpy, name)]
for name in sys.argv[1:]:
    if importlib.import_module(f"assertpy2.{name}") is not importlib.import_module(f"assertpy.{name}"):
        apart.append(f"assertpy2.{name}")
    if getattr(assertpy2, name) is not getattr(assertpy, name):
        apart.append(f"attribute {name}")
print(json.dumps(apart))
"""
    assert_that(_ask(asked)).is_empty()


def test_a_bare_import_offers_the_submodules_a_bare_import_of_assertpy_offers():
    """`import assertpy2` then `assertpy2.errors.Step` worked in 2.34, the package having loaded the module.

    Read before any submodule is imported by name, which would bind the attribute whatever the bridge did.
    """
    canonical = _ask(
        "import json, sys\nimport assertpy\nprint(json.dumps([n for n in sys.argv[1:] if hasattr(assertpy, n)]))"
    )
    asked = """
import json, sys
import assertpy2
offered = [n for n in sys.argv[1:] if hasattr(assertpy2, n)]
print(json.dumps({n: getattr(assertpy2, n) is sys.modules.get(f"assertpy.{n}") for n in offered}))
"""
    bridged = _ask(asked)
    assert_that(sorted(bridged)).is_equal_to(sorted(canonical))
    assert_that([name for name, same in bridged.items() if not same]).is_empty()
    assert_that(sorted(set(_SUBMODULES_OF_2_34) - set(canonical))).is_equal_to(["behave_matchers", "pytest_plugin"])
