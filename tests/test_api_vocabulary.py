"""The naming vocabulary, as a gate rather than as a convention.

A reader who has met `is_empty` and `contains_key` should be able to guess `is_not_empty` and
`does_not_contain_key` without looking, which holds only while every new name follows the same rules.
The rules here are not invented, they are what the surface already does. What this adds is that the
next name has to do it too, and that every name which does not says why.
"""

import pytest

from assertpy import assert_that, match
from assertpy.assertpy import AssertionBuilder

_PREFIXES = ("is_not_", "is_", "does_not_", "has_no_", "has_", "contains_", "all_", "any_", "none_")

# verbs and nouns that are the whole name: an action no `is_`/`has_` spelling improves
_BARE_NAMES = frozenset(
    {
        "contains",
        "each",
        "described_as",
        "exists",
        "extracting",
        "extracting_group",
        "matches",
        "matches_contract_snapshot",
        "matches_inline",
        "matches_json_schema",
        "matches_json_schema_from_file",
        "matches_structure",
        "matches_with_groups",
        "raises",
        "raised",
        "satisfies",
        "satisfies_exactly",
        "satisfies_exactly_in_any_order",
        "snapshot",
        "starts_with",
        "ends_with",
        "warns",
        "when_called_with",
        "zip_satisfies",
        "caused_by",
        "decoded_as",
        "element",
        "eventually",
        "eventually_sync",
        "filtered_on",
        "first",
        "last",
        "at_json_path",
        "conforms_to_openapi",
        "mapped",
        "flat_mapped",
        "single",
        "returned",
        "errors",
        "error_of",
        "builder",
        "check",
        "error",
        "not_",
        "value",
        "val",
    }
)

# Negation form per prefix, which is the half a reader actually has to guess.
_NEGATION = {"is_": "is_not_", "has_": "does_not_have_", "contains_": "does_not_contain_"}

# names breaking a rule on purpose, one line each saying why: an exception without a reason is a suggestion
_DOCUMENTED_EXCEPTIONS = {
    "is_unicode": "assertpy 1.1 compatibility; every str is unicode on Python 3, so this is is_instance_of(str)",
    "has_json_path": "a JSON path addresses lists too, so contains_ would claim a narrower relation than this has",
    "does_not_have_json_path": "the negation of has_json_path, and follows the has_ rule",
    "starts_with_bytes": "the bytes-only spelling of starts_with, kept for the code that already calls it",
    "contains_bytes": "the bytes-only spelling of contains, kept for the code that already calls it",
    "has_byte_at": "indexes a byte, which is neither a property of the value nor something inside it",
    "all_fields_satisfy": "quantifies over the leaves of an object graph, not over elements of a collection",
    "has_no_none_fields": "the named case of all_fields_satisfy, and its has_no_ reads as the English it is",
}


def _public_names():
    return sorted(name for name in dir(AssertionBuilder) if not name.startswith("_"))


class TestEveryNameFollowsThePrefixVocabulary:
    def test_the_surface_has_not_shrunk_below_what_the_rules_were_derived_from(self):
        # the corpus this file reasons about: if it collapses, the rules below would pass on an empty API
        assert_that(_public_names()).is_length_between(150, 250)

    @pytest.mark.parametrize("name", _public_names())
    def test_a_name_is_prefixed_or_a_bare_verb(self, name):
        if name in _DOCUMENTED_EXCEPTIONS or name in _BARE_NAMES:
            return
        # a modifier stays in the verb's family: `starts_with_ignoring_case` is `starts_with` relaxed
        if any(name.startswith(f"{verb}_") for verb in _BARE_NAMES):
            return
        assert_that(name.startswith(_PREFIXES)).described_as(
            f"{name!r} starts with none of {_PREFIXES}, is not a listed bare verb or a modifier on one,"
            " and has no recorded reason"
        ).is_true()


class TestEveryNegationMatchesItsPositive:
    @pytest.mark.parametrize("name", [n for n in _public_names() if n.startswith(("is_not_", "does_not_"))])
    def test_a_negation_has_the_positive_it_negates(self, name):
        if name in _DOCUMENTED_EXCEPTIONS:
            return
        names = set(_public_names())
        for prefix, negated in _NEGATION.items():
            if name.startswith(negated):
                positive = prefix + name[len(negated) :]
                assert_that(names).described_as(f"{name!r} negates {positive!r}, which does not exist").contains(
                    positive
                )
                return
        stem = name.removeprefix("does_not_")
        assert_that(any(candidate.startswith(stem[:5]) for candidate in names - {name})).described_as(
            f"{name!r} negates nothing that exists"
        ).is_true()


class TestEveryExceptionIsStillReal:
    """An exception list rots the moment a name leaves. These keep it honest."""

    @pytest.mark.parametrize("name", sorted(_DOCUMENTED_EXCEPTIONS))
    def test_the_name_still_exists(self, name):
        assert_that(_public_names()).described_as(f"{name!r} is listed as an exception but is gone").contains(name)

    @pytest.mark.parametrize(("name", "reason"), sorted(_DOCUMENTED_EXCEPTIONS.items()))
    def test_the_reason_says_something(self, name, reason):
        assert_that(reason).described_as(name).is_not_empty()
        assert_that(len(reason)).described_as(name).is_greater_than(20)


class TestOneRelationKeepsOneNameAcrossNamespaces:
    """A relation offered both fluently and as a matcher should answer to the same name in both."""

    def test_length_is_reachable_under_the_fluent_name_from_the_matcher_namespace(self):
        assert_that(match.is_length(3)).is_not_none()

    def test_the_quantifier_is_declared_wherever_the_one_it_delegates_to_is(self):
        # `all_satisfy` delegates to `each`, so being reachable in fewer places was a difference the runtime never had
        assert_that({"ab": 1}).each(lambda key: len(key) == 2)
        assert_that({"ab": 1}).all_satisfy(lambda key: len(key) == 2)
