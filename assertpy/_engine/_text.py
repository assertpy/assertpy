"""Text relations as one decision: containment, prefix and suffix over `str` and `bytes` alike.

This is the family that already drifted.  The methods grew `bytes` support and the matchers kept
`isinstance(value, str)`, so `assert_that(b"hello").contains(b"ell")` passed while
`match.contains_string(b"ell")` said no, and the disagreement reached everything a matcher feeds:
`satisfies()`, nested specs and the `==` protocol.  It was found by measurement rather than by reading,
which is the argument for the rule living in one place from here on.

`str` and `bytes` are neighbours and never each other's operands.  Mixing them is answered "no" rather
than raised on, because that is what a matcher needs; a builder checks the pair before it asks.
"""

from __future__ import annotations

from typing import Any


def _comparable(value: object, operand: object) -> bool:
    """Whether the two are text of the same family: `str` with `str`, `bytes` with `bytes`."""
    if isinstance(value, str):
        return isinstance(operand, str)
    if isinstance(value, (bytes, bytearray)):
        return isinstance(operand, (bytes, bytearray))
    return False


def contains(value: Any, part: Any) -> bool:
    """Whether *part* appears in *value*, both being text of the same family."""
    return _comparable(value, part) and part in value


def starts_with(value: Any, prefix: Any) -> bool:
    """Whether *value* begins with *prefix*, both being text of the same family."""
    return _comparable(value, prefix) and value.startswith(prefix)


def ends_with(value: Any, suffix: Any) -> bool:
    """Whether *value* ends with *suffix*, both being text of the same family."""
    return _comparable(value, suffix) and value.endswith(suffix)
