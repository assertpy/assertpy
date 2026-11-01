"""The parts that are deliberately dynamic, used the way the documentation says to use them.

Matchers are registered at runtime and `add_extension` adds a method that no protocol declares.  Both
are documented holes in the typed surface, so what this project checks is that they still *work*, and
that nothing in the typed part broke reaching them.

`has_*` used to live here too.  It resolves through `__getattr__` on the builder, and a value with no
capability no longer reaches that builder, so the calls are type errors while the runtime answers them
exactly as before.  They moved to `dynamic_only/`, beside the other half no checker can see.
"""

from __future__ import annotations

from typing import Any

from assertpy import (
    BaseMatcher,
    assert_that,
    register_matcher,
    unregister_matcher,
)


class Account:
    def __init__(self, owner: str, balance: float) -> None:
        self.owner = owner
        self.balance = balance

    def is_overdrawn(self) -> bool:
        return self.balance < 0


class StartsWithVowel(BaseMatcher):
    """The matcher a typed consumer writes: a `BaseMatcher` subclass, which is what registration takes."""

    def matches(self, value: Any) -> bool:
        return isinstance(value, str) and value[:1].lower() in "aeiou"

    def describe(self) -> str:
        return "a word starting with a vowel"

    def describe_mismatch(self, value: Any) -> str:
        return f"<{value}> does not start with a vowel"


def test_a_registered_matcher_is_usable_by_name() -> None:
    register_matcher("starts_with_vowel")(StartsWithVowel)
    try:
        assert_that("alice").satisfies(StartsWithVowel())
        assert_that("bob").not_.satisfies(StartsWithVowel())
    finally:
        unregister_matcher("starts_with_vowel")


def test_the_negated_branch_still_answers() -> None:
    assert_that("alice").not_.is_empty()
    assert_that([1, 2]).not_.contains(3)
