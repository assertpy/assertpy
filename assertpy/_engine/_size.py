"""Size as one decision: how long a value is, or that it has no length at all.

`len()` answers both questions at once by raising, and the two callers need them apart.  A builder
refuses a value with no length, because a wrong subject there is a mistake in the test.  A matcher
answers "no match", because it feeds `==` and the combinators, where raising would be wrong.  Written
separately, the two used a different rule for what "has no length" means: one asked the protocol, the
other caught `TypeError` and so also swallowed a `__len__` of the user's own that raised.
"""

from __future__ import annotations

from collections.abc import Sized
from typing import cast

_SIZED = frozenset({list, tuple, dict, str, bytes, set, frozenset, bytearray})


def length_of(value: object) -> int | None:
    """The length of *value*, or ``None`` when it has none.

    Answered by the protocol rather than by catching `TypeError`, so a `__len__` that exists and raises
    travels out as its author wrote it: that is a bug in the value, not a value without a length, and
    reporting it as the latter sends the reader looking in the wrong file.  It also does not depend on a
    Python frame being pushed, which a `__len__` implemented in C does not do.
    """
    if type(value) in _SIZED:
        # `isinstance` against an ABC is the whole cost here, and it was paid per element on the extraction path
        return len(cast("Sized", value))
    if not isinstance(value, Sized):
        return None
    return len(value)
