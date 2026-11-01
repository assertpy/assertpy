"""Internal compatibility shims.

``Self`` entered the standard library's `typing` in Python 3.11; on 3.10 it is provided by
``typing_extensions``. Re-exporting it from one place lets every mixin import ``Self`` without repeating
the version gate, and lets ``typing_extensions`` be dropped as a runtime dependency on Python 3.11+.

``BaseExceptionGroup`` is a builtin from Python 3.11; on 3.10 it comes from the ``exceptiongroup``
backport when installed, and otherwise degrades to an empty tuple so ``isinstance`` is simply always
``False`` (a 3.10 interpreter without the backport cannot have produced a group anyway).

``LoggerAdapter`` gained ``__class_getitem__`` in 3.11.  A base class is an expression the interpreter
evaluates, which ``from __future__ import annotations`` does not defer, so spelling the argument
directly raised ``TypeError: 'type' object is not subscriptable`` on 3.10 at import.  Gated on
``TYPE_CHECKING`` rather than on the version, so a checker sees the argument whatever it targets: an
unparameterised base reads as ``LoggerAdapter[Unknown]`` and takes the whole class with it.
"""

import logging
import sys
from typing import TYPE_CHECKING

if sys.version_info >= (3, 11):
    from builtins import BaseExceptionGroup
    from typing import Self
else:  # pragma: no cover - exercised only on Python 3.10
    from typing_extensions import Self

    try:
        from exceptiongroup import BaseExceptionGroup  # ty: ignore[unresolved-import]  # optional 3.10 backport
    except ImportError:
        BaseExceptionGroup = ()

if TYPE_CHECKING:
    _LoggerAdapter = logging.LoggerAdapter[logging.Logger]
else:
    _LoggerAdapter = logging.LoggerAdapter

__all__ = ["BaseExceptionGroup", "Self", "_LoggerAdapter"]
