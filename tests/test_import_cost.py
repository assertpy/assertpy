"""What `import assertpy` loads, held where a measurement decided it.

An import that one code path needs is deferred to that path, with what it costs written beside it.  Moved to
the top of its module it is paid by every run that imports the library, and no timing in the gate shows it:
`urllib.parse` added 1.6 ms that way and was found by hand.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import assertpy
from assertpy import assert_that

_DEFERRED = re.compile(r"^\s+(?:import ([\w.]+)|from ([\w.]+) import [^#\n]+?)\s+# [0-9.]+ ms\b", re.MULTILINE)
"""An import inside a function with its cost in milliseconds beside it."""


def _deferred_with_a_measurement() -> set[str]:
    sources = pathlib.Path(assertpy.__file__).parent.rglob("*.py")
    return {
        plain or source for path in sources for plain, source in _DEFERRED.findall(path.read_text(encoding="utf-8"))
    }


def test_the_imports_deferred_with_a_measurement_are_found():
    """A comment worded another way would leave its import out of the test below."""
    assert_that(_deferred_with_a_measurement()).is_equal_to({"idna", "ipaddress", "urllib.parse"})


def test_importing_the_library_loads_none_of_them():
    """Asked in an interpreter of its own: this one has run the suite and holds them all.

    `pathlib` loads `urllib.parse`, and `ipaddress` with it, by itself below Python 3.13.  There an import
    of either at the top of a module costs nothing, both being loaded already, and this says nothing of it.
    """
    asked = "import sys; import assertpy; print(sorted(set(sys.argv[1:]) & set(sys.modules)))"
    deferred = sorted(_deferred_with_a_measurement())
    ran = subprocess.run([sys.executable, "-c", asked, *deferred], capture_output=True, text=True, check=True)
    loaded_anyway = [] if sys.version_info >= (3, 13) else ["ipaddress", "urllib.parse"]
    assert_that(ran.stdout.strip()).is_equal_to(str(loaded_anyway))
