"""The half no checker can see, kept apart from the half every checker must accept.

`add_extension` puts a method on the builder at runtime, and the typed surface deliberately does not
know about it: that hole is documented rather than closed.  So these calls live here, excluded from type
checking, and the exclusion is the point being recorded.  What is checked is that they still run.
"""

from __future__ import annotations

from typing import Any

from assertpy import add_extension, assert_that, remove_extension


def test_an_extension_adds_a_method_to_every_chain() -> None:
    def is_lucky(self: Any) -> Any:
        if self.val != 7:
            self.error(f"Expected <{self.val}> to be lucky")
        return self

    add_extension(is_lucky)
    try:
        assert_that(7).is_lucky()
        try:
            assert_that(3).is_lucky()
        except AssertionError as failure:
            assert_that(str(failure)).contains("to be lucky")
        else:  # pragma: no cover - the unlucky number is expected to fail
            raise AssertionError("expected the extension to fail on an unlucky number")
    finally:
        remove_extension(is_lucky)
