"""The exception-group classes, taken the way assertpy itself takes them.

Groups are a 3.11+ builtin, and below that the library falls back to the ``exceptiongroup`` backport
(``assertpy/_engine/_compat.py``).  The group tests used to skip on 3.10 outright, which left the
fallback path that ships there unexercised.  Resolving the classes here once keeps both the example-based
and the property-based suite pointed at whatever the interpreter under test actually has.

Both names shadow the builtins on purpose, the way ``_compat`` does inside the library: a test then reads
the same as the code it checks.  They are ``None`` only on a 3.10 install without the optional backport,
which is the one case where there is nothing to test against.
"""

from __future__ import annotations

import sys

import pytest

if sys.version_info >= (3, 11):
    ExceptionGroup = ExceptionGroup  # noqa: F821  # 3.11+ builtin, re-exported under the same name
    BaseExceptionGroup = BaseExceptionGroup  # noqa: F821  # 3.11+ builtin
else:
    try:
        from exceptiongroup import BaseExceptionGroup, ExceptionGroup
    except ImportError:  # pragma: no cover  # only on a 3.10 install without the optional backport
        ExceptionGroup = None
        BaseExceptionGroup = None

needs_groups = pytest.mark.skipif(
    ExceptionGroup is None, reason="needs exception groups: Python 3.11+, or the exceptiongroup backport"
)
