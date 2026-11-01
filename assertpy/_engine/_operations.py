"""Which public operations reach a verdict, and what the ones that do not do instead.

Both proxies need the same answer.  ``not_`` inverts a verdict and ``check()`` reports one, so an
operation that reaches no verdict means nothing through either, and both used to accept them:
``assert_that(1).not_.check()`` failed with "Expected <1> to NOT satisfy: check()", and
``assert_that([1]).check().first()`` answered that an assertion passed when none had run.

A verdict is ``self.error(...)``, the one failure entry point every assertion goes through.  What is
registered here is the complement: the operations that reach it through nothing, listed by what they
do instead.  Written as the exceptions rather than as the whole surface, because 134 of the 152 public
names assert and a register of those would be a second copy of the API, kept in step by hand.

`tests/test_operation_contract.py` re-derives this set from the source and fails on any difference, so
a new operation that asserts nothing cannot quietly become negatable or checkable.
"""

from __future__ import annotations

from typing import Final

CONFIGURES: Final = "configures"
TRANSFORMS: Final = "transforms"
DESCRIBES: Final = "describes"
POLLS: Final = "polls"

# the proxies word their own sentence: `not_` and `check()` refuse the same operation for different reasons
WHAT_IT_DOES: Final = {
    CONFIGURES: "only sets an expectation and asserts nothing on its own",
    TRANSFORMS: "hands back a different value instead of asserting",
    DESCRIBES: "only sets the failure description",
    POLLS: "runs a whole chain until it holds",
}

# the builder's own machinery, named rather than filtered, so a new one is declared before the gate takes it
NOT_AN_OPERATION: Final = frozenset({"builder", "check", "error", "not_", "value"})

# the members handing the subject back: no assertion left uncalled for the dangling check, none to wrap for a proxy
HANDS_THE_SUBJECT_BACK: Final = frozenset({"val", "value"})

# the hybrids: named, since "reaches `self.error()`" does not separate a verdict from a precondition
ALSO_ASSERTS: Final = frozenset(
    {
        "caused_by",
        "error_of",
        "extracting_group",
        "has_root_cause",
        "matches_with_groups",
        "when_called_with",
    }
)

WITHOUT_A_VERDICT: Final[dict[str, str]] = {
    "raises": CONFIGURES,
    "does_not_raise": CONFIGURES,
    "warns": CONFIGURES,
    "does_not_warn": CONFIGURES,
    "at_json_path": TRANSFORMS,
    "decoded_as": TRANSFORMS,
    "decoded_as_json": TRANSFORMS,
    "element": TRANSFORMS,
    "extracting": TRANSFORMS,
    "filtered_on": TRANSFORMS,
    "first": TRANSFORMS,
    "flat_mapped": TRANSFORMS,
    "last": TRANSFORMS,
    "mapped": TRANSFORMS,
    "raised": TRANSFORMS,
    "returned": TRANSFORMS,
    # `errors()` takes no expectation, so once a group is caught there is nothing it can be wrong about
    "errors": TRANSFORMS,
    "single": TRANSFORMS,
    "described_as": DESCRIBES,
    "eventually": POLLS,
    "eventually_sync": POLLS,
}
