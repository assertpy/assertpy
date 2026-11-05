"""Pyright diagnostics the package is known to carry, and why each group is there.

The package walks values whose static type really is `object`, guards optional imports, and composes
mixins, so pyright reports things that are not defects. Recording them per (file, rule) with a reason
lets the guard fail on a new one instead of on a total nobody can read.

A rule appearing where it was not recorded fails. So does one appearing more often, or fewer times
than recorded, which points here rather than at the code.

Line numbers are not part of the key: they move on every unrelated edit above them.

Two records, because they answer different questions. `BASELINE` is the exception list: each entry is
an oddity somebody decided about once. `LADDER_OVERLAP` is a policy, and it is kept apart because a
list of 96 entries of one rule stops reading as exceptions and starts reading as a total nobody can
act on, which is the failure the first paragraph warns about.
"""

from __future__ import annotations

BASELINE: dict[tuple[str, str], int] = {
    ("assertpy/_engine/_diff.py", "reportAttributeAccessIssue"): 12,
    ("assertpy/base.py", "reportArgumentType"): 2,
    ("assertpy/extracting.py", "reportArgumentType"): 1,
    ("assertpy/extracting.py", "reportCallIssue"): 1,
    ("assertpy/extracting.py", "reportIndexIssue"): 1,
    ("assertpy/helpers.py", "reportArgumentType"): 2,
    ("assertpy/helpers.py", "reportGeneralTypeIssues"): 1,
    ("assertpy/helpers.py", "reportIndexIssue"): 2,
    ("assertpy/helpers.py", "reportOperatorIssue"): 1,
    ("assertpy/behave_matchers.py", "reportAttributeAccessIssue"): 1,
    ("assertpy/behave_matchers.py", "reportMissingModuleSource"): 1,
    ("assertpy/pytest_plugin.py", "reportMissingImports"): 1,
    ("assertpy/pytest_plugin.py", "reportPossiblyUnboundVariable"): 6,
    # the twins mirror the protocols and their reports: the same suggestions, and one override for the same reason
    ("assertpy/_engine/_check_typing.py", "reportInvalidTypeVarUse"): 3,
    ("assertpy/_engine/_check_typing.py", "reportIncompatibleMethodOverride"): 2,
    ("assertpy/_engine/_poll_typing.py", "reportInvalidTypeVarUse"): 2,
    # refused: `_E` sits in a contravariant `Matcher` where flips cancel, and the warned view's parameter stays
    # covariant under the invariant builder `returned()` hands back, as the views that lead to it are
    ("assertpy/_engine/_typing.py", "reportInvalidTypeVarUse"): 2,
    ("assertpy/assertpy.py", "reportAttributeAccessIssue"): 1,
    # what a dynamic hook hands back: two of a former four went when the implementation's return became `Any`
    ("assertpy/assertpy.py", "reportReturnType"): 2,
    # the failure record is `| None` in general and never None at this call, as the comment there says
    ("assertpy/snapshot.py", "reportArgumentType"): 1,
}

LADDER_OVERLAP: dict[tuple[str, str], int] = {
    # the ladders the umbrella's façade carries over from the builder, which overlap there too
    ("assertpy/_engine/_capable_typing.py", "is_not_none"): 1,
    ("assertpy/_engine/_capable_typing.py", "is_instance_of"): 1,
    ("assertpy/_engine/_capable_typing.py", "is_instance_of_any"): 1,
    ("assertpy/_engine/_capable_typing.py", "satisfies"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_even"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_odd"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_divisible_by"): 1,
    ("assertpy/_engine/_poll_typing.py", "is_even"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_odd"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_divisible_by"): 4,
    ("assertpy/_engine/_builder_check_typing.py", "is_between"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_greater_than"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_greater_than_or_equal_to"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_instance_of"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_instance_of_any"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_less_than"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_less_than_or_equal_to"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_not_between"): 1,
    ("assertpy/_engine/_builder_check_typing.py", "is_not_none"): 2,
    ("assertpy/_engine/_builder_check_typing.py", "matches_structure"): 1,
    # the object view's conversion rungs, which overlap the numeric ones the twins already carry
    ("assertpy/_engine/_builder_check_typing.py", "is_close_to"): 1,
    ("assertpy/_engine/_poll_typing.py", "is_close_to"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_between"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_greater_than"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_greater_than_or_equal_to"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_instance_of"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_instance_of_any"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_less_than"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_less_than_or_equal_to"): 4,
    ("assertpy/_engine/_poll_typing.py", "is_not_between"): 4,
    ("assertpy/_engine/_poll_typing.py", "matches_structure"): 4,
    # only the negated chain's ladder is left: the positive chain strips `None` in one rung
    ("assertpy/_engine/_poll_typing.py", "is_not_none"): 4,
    ("assertpy/_engine/_typing.py", "is_instance_of"): 5,
    ("assertpy/_engine/_typing.py", "is_not_none"): 15,
    ("assertpy/_engine/_typing.py", "satisfies"): 9,
    ("assertpy/assertpy.py", "assert_that"): 5,
    # a bare `type` falls back to `BaseException` under the rung carrying the exception class it was given
    ("assertpy/_engine/_typing.py", "raises"): 1,
    ("assertpy/_engine/_typing.py", "error_of"): 2,
    ("assertpy/_engine/_capable_typing.py", "raises"): 1,
    ("assertpy/_engine/_check_typing.py", "error_of"): 1,
    ("assertpy/_engine/_negated_typing.py", "error_of"): 1,
    ("assertpy/_engine/_poll_typing.py", "error_of"): 3,
    # a cause falls back the same way, but its fallback takes a union or a tuple too, so pyright sees it used
    ("assertpy/_engine/_typing.py", "caused_by"): 1,
    ("assertpy/_engine/_typing.py", "has_root_cause"): 1,
    ("assertpy/_engine/_poll_typing.py", "caused_by"): 1,
    ("assertpy/_engine/_poll_typing.py", "has_root_cause"): 1,
}
"""Where a refinement ladder makes pyright call a later rung redundant, by the method it is on.

Not a debt and not a list of decisions. A ladder puts the narrower rung first so the narrower type
wins, and pyright reads the pair as an overlap wherever the wider rung still accepts what the narrower
one took: `bool` before `int` on the comparisons, `datetime` before `date`, a named rung before the
trailing umbrella one on the polling twins. `is_not_none` is a fifth of it on its own, because a
chain over `None` matches every rung there is.

Keyed by method rather than counted per file, which the rule was before. A per-file count of 48 stayed
green when one method stopped overlapping and another started, and the file it points at is generated,
so the number said nothing a reader could act on. The method name says which ladder moved.
"""
