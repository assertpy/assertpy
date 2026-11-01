"""The names this package had as assertpy2, still read through the 2.x line.

Each is a deprecated synonym of its current name: it works, warns once per process with a
`FutureWarning`, and goes in 3.0.  The old name is read only where the current one is blank.

A `FutureWarning` rather than a `DeprecationWarning`, since the reader is whoever wrote the config, and
Python hides the other category outside code run as `__main__`.
"""

from __future__ import annotations

import os
import warnings

_told: set[str] = set()


def old_name(name: str) -> str:
    """The name a flag, setting, variable or marker had before the rename.

    Args:
        name: the current name, in any of the spellings the package uses.

    Returns:
        The same name with ``assertpy`` spelled ``assertpy2``, in the case it was written in.
    """
    return name.replace("assertpy", "assertpy2", 1).replace("ASSERTPY", "ASSERTPY2", 1)


def tell(old: str, new: str) -> None:
    """Warn, once per process, that a name from assertpy2 was used.

    Args:
        old: the name as it was given.
        new: the name to give instead.
    """
    if old in _told:
        return
    warnings.warn(
        f"{old} is the assertpy2 name of {new}. It keeps working until assertpy 3.0, use {new} instead.",
        FutureWarning,
        stacklevel=3,
    )
    _told.add(old)


def environ(name: str) -> str:
    """An environment variable, read by its assertpy2 name where its own is blank.

    Args:
        name: the variable's current name.

    Returns:
        Its value, else the value of its old name, else an empty string.
    """
    value = os.environ.get(name, "")
    if value.strip():
        return value
    old = old_name(name)
    before = os.environ.get(old, "")
    if not before.strip():
        return value
    tell(old, name)
    return before
