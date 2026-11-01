"""Bring every generated and recorded artefact back in step with the runtime.

Four things go stale when an assertion is added or a signature changes, and finding out which one by
reading a red suite is the tax this script exists to remove.  Run it after editing a mixin or
`_engine/_typing.py`, then read the diff.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent

_STEPS: list[tuple[str, list[str], dict[str, str]]] = [
    (
        "polling, builder-check, capability and negation twins",
        [sys.executable, "scripts/generate_poll_protocols.py"],
        {},
    ),
    ("verdict twins", [sys.executable, "scripts/generate_check_protocols.py"], {}),
    (
        "the public surface snapshot",
        [sys.executable, "-m", "pytest", "tests/test_api_compatibility.py", "-q", "--no-cov", "-p", "no:randomly"],
        {"ASSERTPY_UPDATE_API": "1"},
    ),
    (
        "the table of sizes in ARCHITECTURE.md",
        [sys.executable, "-m", "pytest", "tests/test_architecture_doc.py", "-q", "--no-cov", "-p", "no:randomly"],
        {"ASSERTPY_UPDATE_ARCHITECTURE": "1"},
    ),
]


def main() -> int:
    for what, command, environment in _STEPS:
        print(f"-> {what}")
        result = subprocess.run(command, cwd=_ROOT, env={**os.environ, **environment}, check=False)
        if result.returncode:
            print(f"failed while regenerating {what}", file=sys.stderr)
            return result.returncode
    print("regenerated; read the diff before committing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
