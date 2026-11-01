"""Grouping a run's failures by the difference they share.

The two halves matter for different reasons. Getting the grouping right is what makes the summary
useful; getting the *non*-grouping right is what keeps it honest, because a diff entry that carries no
coordinate would otherwise put every unrelated failure of its kind under one meaningless heading.

The key is the place rather than the values, which was a correction: an applicability map over eleven
shapes of run showed that keying on values covers a broken constant and nothing else, and misses a
broken formula differing at the same field with a value of its own per test.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace

import pytest

from assertpy import AssertionFailure, assert_that, match, pytest_plugin
from assertpy._clustering import (
    _EXAMPLE_LIMIT,
    _VALUE_LIMIT,
    MINIMUM_SIZE,
    Observation,
    Signature,
    _bounded,
    _identity,
    _made_unique,
    _side,
    _spelled_out,
    clusters,
    is_well_formed,
    observations_of,
    render,
    render_path,
    signature,
    stable_repr,
)
from assertpy.errors import DiffEntry, DiffResult, Step
from assertpy.pytest_plugin import (
    _cluster_minimum,
    _observation_from_wire,
    _observation_to_wire,
    _record_for_clustering,
    pytest_terminal_summary,
)


def diff_of(case):
    """The `DiffResult` a failing assertion carries."""
    with pytest.raises(AssertionFailure) as failure:
        case()
    return failure.value.diff


def observations(case, label=None):
    return observations_of(diff_of(case), label)


def keys(case, label=None):
    """Just the cluster keys, for the tests about what counts as one difference."""
    return [one.signature for one in observations(case, label)]


def located(where, steps=(("key", "'role'"),)):
    """A located signature, spelled out rather than derived, so the tests state their own input."""
    return Signature(True, where, steps)


def recorded(count, signature, *, actual="'super'", expected="'admin'", prefix="test"):
    return [(f"{prefix}_{index}", [Observation(signature, actual, expected)]) for index in range(count)]


class TestWhatCountsAsOneDifference:
    def test_the_same_field_and_values_in_two_failures(self):
        first = keys(lambda: assert_that({"u": {"role": "super"}}).is_equal_to({"u": {"role": "admin"}}))
        second = keys(lambda: assert_that({"u": {"role": "super"}}).is_equal_to({"u": {"role": "admin"}}))
        assert_that(first).is_equal_to(second)

    def test_the_same_field_with_different_values_is_the_same_difference(self):
        """The correction the applicability map forced, and the reason for it.

        A broken constant gives every failure the same pair of values, and keying on values covers it.
        A broken formula gives each test a value of its own at the same field, and keying on values
        scattered a run of forty into forty clusters of one. Both are ordinary shapes.
        """
        first = keys(lambda: assert_that({"total": 7}).is_equal_to({"total": 8}))
        second = keys(lambda: assert_that({"total": 91}).is_equal_to({"total": 104}))
        assert_that(first).is_equal_to(second)

    def test_two_different_fields_are_still_two_differences(self):
        first = keys(lambda: assert_that({"role": "s"}).is_equal_to({"role": "a"}))
        second = keys(lambda: assert_that({"name": "s"}).is_equal_to({"name": "a"}))
        assert_that(first).is_not_equal_to(second)

    def test_the_row_index_is_generalised_away(self):
        # one difference reported against two rows, which a reader chasing a common cause wants on one line
        first = keys(lambda: assert_that({"users": [{"role": "super"}]}).is_equal_to({"users": [{"role": "x"}]}))
        second = keys(
            lambda: assert_that({"users": [{"role": "y"}, {"role": "super"}]}).is_equal_to(
                {"users": [{"role": "y"}, {"role": "x"}]}
            )
        )
        assert_that(first).is_equal_to(second)
        assert_that(first[0].where).is_equal_to("users[*].role")

    def test_a_mapping_key_is_taken_from_the_step_not_the_rendered_path(self):
        # the rendered path puts a key through `str()`, so {3: ...} and {"3": ...} must not share a cluster
        numeric = keys(lambda: assert_that({3: "a"}).is_equal_to({3: "b"}))
        textual = keys(lambda: assert_that({"3": "a"}).is_equal_to({"3": "b"}))
        assert_that(numeric).is_not_equal_to(textual)

    def test_one_failure_with_two_differing_fields_joins_two_clusters(self):
        found = keys(lambda: assert_that({"a": 1, "b": 2}).is_equal_to({"a": 9, "b": 8}))
        assert_that(found).is_length(2)
        assert_that([one.where for one in found]).is_equal_to(["a", "b"])

    def test_a_failure_with_no_diff_contributes_nothing(self):
        assert_that(observations_of(None)).is_empty()

    def test_the_values_are_kept_as_examples_even_though_they_are_not_the_key(self):
        found = observations(lambda: assert_that({"role": "super"}).is_equal_to({"role": "admin"}))
        assert_that(found[0].actual).is_equal_to("'super'")
        assert_that(found[0].expected).is_equal_to("'admin'")


class _Payload:
    """A value whose repr is longer than the summary prints, so identity and display come apart."""

    def __init__(self, tail):
        self.tail = tail

    def __repr__(self):
        return "<Payload " + "x" * 300 + self.tail + ">"

    def __eq__(self, other):
        return isinstance(other, _Payload) and other.tail == self.tail

    __hash__ = None


class TestEnteringJsonTextIsNoPlaceOfItsOwn:
    """A step that enters JSON text holds what the text decodes to, which is another object in every run.  Keyed on
    it, a difference inside the text had no location, and fell out of the summary."""

    def test_a_difference_inside_json_text_is_located_by_the_keys_around_the_step(self):
        decoded = {"x": 1, "extra": 2}
        inside = DiffEntry(
            path="f.extra",
            steps=(Step("key", "f"), Step("json", decoded), Step("key", "extra")),
            actual=2,
            absent="expected",
        )
        beside = DiffEntry(path="f.extra", steps=(Step("key", "f"), Step("key", "extra")), actual=2, absent="expected")
        found = [signature(DiffResult(kind="match", entries=[entry]), entry) for entry in (inside, beside)]
        assert_that(found[0]).is_equal_to(found[1])
        assert_that((found[0].located, found[0].where, is_well_formed(found[0]))).is_equal_to((True, "f.extra", True))
        only = DiffEntry(path=".", steps=(Step("json", decoded),), actual=decoded, expected="cannot be checked")
        assert_that(signature(DiffResult(kind="match", entries=[only]), only)).is_none()


class TestTheKindsThatHaveNoCoordinate:
    """An audit of every diff kind found three that name a label rather than a place. Keying those on
    their path would file every unrelated failure of that kind under one heading.

    Their fallback is the failure's own diagnostic line, which states the difference as a kind instead
    of a place. Only where there is no diagnostic either do the values become the key.
    """

    def test_containment_stays_out_of_the_summary_without_a_diagnostic(self):
        """Its two fields hold presence, not values, so a heading built from them lies.

        A missing item reports `None` on the actual side, and `actual: None` under a cluster heading
        reads as a claim about the value under test, which was a list of three. Reported by an
        independent review, reproduced, and answered by dropping the family rather than giving it a
        second rendering: it clustered almost nothing to begin with.
        """
        assert_that(observations(lambda: assert_that([1, 2]).contains(9))).is_empty()

    def test_a_set_difference_stays_out_for_the_same_reason(self):
        # two entries per failure printed two blocks under one heading and summed past the number of failures
        assert_that(observations(lambda: assert_that({1, 2}).is_equal_to({1, 3}))).is_empty()

    def test_a_diagnostic_still_lets_them_cluster(self):
        hint = "every difference here is one of surrounding whitespace"
        found = keys(lambda: assert_that({"a ", "b "}).is_equal_to({"a", "b"}), hint)
        assert_that(found).is_not_empty()
        assert_that(found[0].label).is_equal_to(hint)

    def test_two_long_values_that_start_alike_do_not_cluster(self):
        """The printed form is cut at 200 characters, and the key must not be.

        Two payloads that agree for their first two hundred characters and diverge after are two
        different failures.  Keying on the truncated text merged them, and the summary then announced a
        difference the two never shared.
        """
        first = keys(lambda: assert_that(_Payload("one")).is_equal_to(_Payload("expected")))
        second = keys(lambda: assert_that(_Payload("two")).is_equal_to(_Payload("expected")))
        assert_that(first).is_not_equal_to(second)

    def test_the_same_value_still_clusters_however_long_it_is(self):
        first = keys(lambda: assert_that(_Payload("same")).is_equal_to(_Payload("expected")))
        second = keys(lambda: assert_that(_Payload("same")).is_equal_to(_Payload("expected")))
        assert_that(first).is_equal_to(second)

    def test_two_scalar_failures_with_different_values_do_not_cluster(self):
        first = keys(lambda: assert_that(1).is_equal_to(2))
        second = keys(lambda: assert_that(5).is_equal_to(6))
        assert_that(first).is_not_equal_to(second)

    def test_a_diagnostic_makes_two_of_them_one_difference(self):
        """The half of the correction that the location-free family needed.

        Five uploads differing from their expected bodies only by a trailing newline are one bug, and
        their values are five different payloads. The diagnostic says what they share.
        """
        hint = "every difference here is one of surrounding whitespace"
        first = keys(lambda: assert_that(b"one\n").is_equal_to(b"one"), hint)
        second = keys(lambda: assert_that(b"two\n").is_equal_to(b"two"), hint)
        assert_that(first).is_equal_to(second)
        assert_that(first[0].label).is_equal_to(hint)
        assert_that(first[0].values).described_as("the label replaces the values, never joins them").is_empty()

    def test_two_diagnostics_that_differ_stay_apart(self):
        first = keys(lambda: assert_that(b"one\n").is_equal_to(b"one"), "one of surrounding whitespace")
        second = keys(lambda: assert_that(b"one\n").is_equal_to(b"one"), "one of line endings")
        assert_that(first).is_not_equal_to(second)

    def test_a_located_failure_ignores_the_diagnostic(self):
        # a place is the stronger signal: letting a label split one field into two clusters undoes the correction
        plain = keys(lambda: assert_that({"a": "x "}).is_equal_to({"a": "x"}))
        hinted = keys(lambda: assert_that({"a": "x "}).is_equal_to({"a": "x"}), "one of surrounding whitespace")
        assert_that(plain).is_equal_to(hinted)

    def test_a_key_holding_a_set_is_written_the_same_way_in_any_process(self):
        """The walk that pins set ordering has to reach a mapping *key*, not only the values.

        A key is hashable, so it can be a frozenset, and a frozenset reprs in hash order.  Two workers
        are two processes with two hash seeds, so the same failure keyed differently on each and the
        two never clustered - the exact symptom `stable_repr` exists to remove, one call site away.
        """
        key = frozenset({"b", "a", "c"})
        found = keys(lambda: assert_that({key: 1}).is_equal_to({key: 2}))
        assert_that(found[0].steps[0][1]).is_equal_to(stable_repr(key))

    def test_a_matcher_failure_keeps_its_path(self):
        found = keys(lambda: assert_that({"role": "super"}).matches_structure({"role": match.is_in("admin")}))
        assert_that(found[0].located).is_true()
        assert_that(found[0].where).is_equal_to("role")

    def test_a_changed_line_is_a_location_with_its_number_generalised(self):
        # two files differing on different lines are still "the same line changed", the number as incidental as an index
        first = keys(lambda: assert_that("a\nb").is_equal_to("a\nc"))
        second = keys(lambda: assert_that("x\ny\nb").is_equal_to("x\ny\nc"))
        assert_that(first[0].where).is_equal_to("line [n]")
        assert_that(first).is_equal_to(second)


class TestNothingHereMayRaise:
    """A summary is a convenience, and this code runs inside a pytest report hook.

    An exception raised there is answered with INTERNALERROR: the run reports nothing at all, not even
    the failures it had already collected. Both shapes below did exactly that, and both were already
    solved elsewhere in the library - the diff engine carries a `_seen` set, and `_safe_repr` exists
    for values whose own code raises. Walking containers here meant owning them again.
    """

    def test_a_value_that_contains_itself(self):
        node = {"name": "a"}
        node["self"] = node
        assert_that(stable_repr(node)).is_equal_to("{'name': 'a', 'self': ...}")

    def test_a_list_that_contains_itself(self):
        rows = [1]
        rows.append(rows)
        assert_that(stable_repr(rows)).is_equal_to("[1, ...]")

    def test_two_references_to_one_value_are_not_a_cycle(self):
        # the guard is per path, not global: a value used twice is printed twice, as `repr` does
        shared = {"x": 1}
        assert_that(stable_repr([shared, shared])).is_equal_to("[{'x': 1}, {'x': 1}]")

    def test_a_container_that_raises_when_iterated(self):
        class Detached(list):
            def __iter__(self):
                raise RuntimeError("not bound to a Session")

            def __repr__(self):
                return "<Detached>"

        assert_that(stable_repr([Detached()])).is_equal_to("[<Detached>]")

    def test_a_value_whose_repr_raises(self):
        class Hostile:
            def __repr__(self):
                raise ValueError("no repr for you")

        assert_that(stable_repr({"k": Hostile()})).contains("unreprable Hostile")


class TestValuesAreBounded:
    """The summary sits in the closing screen of a run and travels between xdist processes, so it caps
    harder than the failure message does: 200 characters a side against the message's 400.
    """

    def test_a_long_value_is_cut_with_its_length_named(self):
        found = observations(lambda: assert_that("x" * 5000).is_equal_to("y"))
        assert_that(found[0].actual).is_length(200 + len("... (4802 more chars)"))
        assert_that(found[0].actual).ends_with("more chars)")

    def test_an_ordinary_value_is_untouched(self):
        found = observations(lambda: assert_that({"role": "super"}).is_equal_to({"role": "admin"}))
        assert_that(found[0].actual).is_equal_to("'super'")


class TestASignatureReadsTheSameInAnyProcess:
    """A signature has to survive being built on two xdist workers, which are two processes with two
    hash seeds. A set reprs in iteration order, so identical failures produced different signatures
    and never clustered - the feature going silent on exactly the runs it exists for.
    """

    def test_a_set_is_ordered(self):
        assert_that(stable_repr({"b", "a", "c"})).is_equal_to("{'a', 'b', 'c'}")

    def test_a_set_nested_in_a_container_is_reached(self):
        assert_that(stable_repr({"tags": {"b", "a"}})).is_equal_to("{'tags': {'a', 'b'}}")
        assert_that(stable_repr([{"b", "a"}])).is_equal_to("[{'a', 'b'}]")

    def test_an_empty_set_keeps_its_own_repr(self):
        assert_that(stable_repr(set())).is_equal_to("set()")

    def test_a_one_element_tuple_keeps_its_comma(self):
        assert_that(stable_repr((1,))).is_equal_to("(1,)")
        assert_that(stable_repr((1, 2))).is_equal_to("(1, 2)")

    def test_everything_else_is_left_to_repr(self):
        assert_that(stable_repr("x")).is_equal_to("'x'")
        assert_that(stable_repr(None)).is_equal_to("None")
        assert_that(stable_repr(frozenset({2, 1}))).is_equal_to("{1, 2}")

    def test_a_dict_keeps_the_order_it_was_written_in(self):
        # not sorted: a dict's order is the reader's own, and pinning it would show what the message never did
        assert_that(stable_repr({"z": 1, "a": 2})).is_equal_to("{'z': 1, 'a': 2}")


class TestWhichClustersAreWorthPrinting:
    """The floor is a count, not a share, and that is a correction rather than a preference.

    Under a share every additional cause raises the bar for all the others, so a run of forty failures
    splitting cleanly into five causes of eight printed nothing at all. Measured across eleven shapes,
    the share was never better than the floor and worse on four of them.
    """

    def test_a_cluster_covering_most_of_the_run_is_reported(self):
        found = clusters(recorded(37, located("user.role")), 40)
        assert_that(found).is_length(1)
        assert_that(found[0].size).is_equal_to(37)

    def test_a_small_cluster_in_a_large_run_is_still_reported(self):
        # the case a share got wrong: five failures sharing a cause are five tests to fix, whatever the rest did
        assert_that(clusters(recorded(5, located("user.role")), 40)).is_length(1)

    def test_two_of_three_clears_any_ratio_and_is_still_refused(self):
        assert_that(clusters(recorded(2, located("user.role")), 3)).is_empty()
        assert_that(MINIMUM_SIZE).is_equal_to(3)

    def test_the_floor_can_be_raised(self):
        assert_that(clusters(recorded(4, located("a")), 40, minimum=5)).is_empty()
        assert_that(clusters(recorded(4, located("a")), 40, minimum=4)).is_length(1)

    def test_a_run_with_no_failures_reports_nothing(self):
        assert_that(clusters([], 0)).is_empty()

    def test_clusters_come_back_largest_first_and_ties_break_deterministically(self):
        rows = (
            recorded(4, located("b.field", (("key", "'b'"),)), prefix="b")
            + recorded(4, located("a.field", (("key", "'a'"),)), prefix="a")
            + recorded(9, located("z.field", (("key", "'z'"),)), prefix="z")
        )
        found = clusters(rows, 20)
        assert_that([one.signature.where for one in found]).is_equal_to(["z.field", "a.field", "b.field"])

    def test_a_cluster_collects_the_distinct_values_it_saw(self):
        rows = [
            ("t1", [Observation(located("total"), "7", "8")]),
            ("t2", [Observation(located("total"), "91", "8")]),
            ("t3", [Observation(located("total"), "7", "8")]),
        ]
        found = clusters(rows, 3)[0]
        assert_that(found.actuals).described_as("distinct, in order of appearance").is_equal_to(("7", "91"))
        assert_that(found.expecteds).described_as("one expected value across all three").is_equal_to(("8",))


class TestTheSummaryText:
    def test_it_names_the_share_the_place_and_both_values(self):
        lines = render(clusters(recorded(37, located("user.role")), 40), 40)
        assert_that(lines[0]).is_equal_to("37 of 40 failing tests differ at user.role")
        assert_that(lines[1]).contains("'super'")
        assert_that(lines[2]).contains("'admin'")
        assert_that(lines[3]).is_equal_to("3 of 40 outside any cluster of 3")

    def test_a_cluster_whose_values_disagree_says_so(self):
        """The one way a place-keyed summary could mislead, closed in the rendering.

        Printing the first pair as though it were the difference would let two causes at one field read
        as one fact to act on. A count says what it is: a place to look.
        """
        rows = [("t1", [Observation(located("total"), "7", "8")]), ("t2", [Observation(located("total"), "91", "104")])]
        rows.append(("t3", [Observation(located("total"), "5", "6")]))
        lines = render(clusters(rows, 3), 3)
        assert_that(lines[1]).is_equal_to("    actual:   5 and 2 other values")
        assert_that(lines[2]).is_equal_to("    expected: 104 and 2 other values")

    def test_the_printed_example_does_not_depend_on_who_finished_first(self):
        """Sorted, not first-seen: under xdist the order of arrival is the order workers finished in.

        The same failing run printed a different example on different runs, which is the hazard
        `stable_repr` exists for, moved from the key into the rendering.
        """
        one = [("a", [Observation(located("id"), "3", "9")]), ("b", [Observation(located("id"), "14", "9")])]
        one.append(("c", [Observation(located("id"), "7", "9")]))
        other = list(reversed(one))
        assert_that(render(clusters(other, 3), 3)).is_equal_to(render(clusters(one, 3), 3))

    def test_one_other_value_is_not_pluralised(self):
        rows = [("t1", [Observation(located("a"), "1", "2")]), ("t2", [Observation(located("a"), "9", "2")])]
        rows.append(("t3", [Observation(located("a"), "1", "2")]))
        assert_that(render(clusters(rows, 3), 3)[1]).is_equal_to("    actual:   1 and 1 other value")

    def test_a_cluster_keyed_on_a_diagnostic_prints_the_diagnostic(self):
        hint = "every difference here is one of surrounding whitespace"
        key = Signature(False, "string", label=hint)
        lines = render(clusters(recorded(4, key, actual="b'a\\n'", expected="b'a'"), 4), 4)
        assert_that(lines[0]).is_equal_to("4 of 4 failing tests share one string difference")
        assert_that(lines[1]).is_equal_to(f"    {hint}")
        assert_that(lines).described_as("the words replace the two value lines").is_length(2)

    def test_a_kind_without_a_place_is_marked_as_one(self):
        # keyed on its diagnostic, the only way `contains` reaches a cluster: its fields hold presence, not values
        key = Signature(False, "contains", label="every difference here is one of bytes against text")
        assert_that(render(clusters(recorded(5, key), 5), 5)[0]).is_equal_to(
            "5 of 5 failing tests share one contains difference"
        )

    def test_nothing_is_said_when_every_failure_is_covered(self):
        assert_that(render(clusters(recorded(5, located("a")), 5), 5)).is_length(3)

    def test_nothing_is_said_at_all_without_a_cluster(self):
        assert_that(render([], 40)).is_empty()

    def test_two_clusters_that_would_print_alike_are_spelled_out(self):
        numeric = observations(lambda: assert_that({3: "a"}).is_equal_to({3: "b"}))
        textual = observations(lambda: assert_that({"3": "a"}).is_equal_to({"3": "b"}))
        rows = [(f"n{index}", numeric) for index in range(4)] + [(f"t{index}", textual) for index in range(4)]
        headings = [line for line in render(clusters(rows, 8), 8) if "differ at" in line]
        assert_that(headings).is_length(2)
        assert_that(set(headings)).described_as("two clusters printed the same heading").is_length(2)
        assert_that(headings[0]).contains("key=")

    def test_two_long_locations_do_not_print_as_one(self):
        """The disambiguating spelling is cut at the same limit as the path it disambiguates.

        Two mapping keys agreeing for two hundred characters then printed identically, which hands the
        reader two blocks that look like a rendering bug and hides that they are different places.
        """
        shared = "k" * 300
        first = located("long", (("key", f"'{shared}one'"),))
        second = located("long", (("key", f"'{shared}two'"),))
        lines = render(clusters(recorded(3, first) + recorded(3, second, prefix="other"), 6), 6)
        headings = [line for line in lines if "differ at" in line]
        assert_that(headings).is_length(2)
        assert_that(headings[0]).is_not_equal_to(headings[1])

    def test_two_locations_that_even_spell_alike_are_still_told_apart(self):
        """The spelling is a join, so two different step tuples can produce the same text.

        `key=a.key=b` is what both a two-hop location and a one-hop location holding that very text come
        to.  They are different places and different clusters, and the summary has to show them as two.
        """
        first = Signature(True, "same", (("key", "a"), ("key", "b")))
        second = Signature(True, "same", (("key", "a.key=b"),))
        lines = render(clusters(recorded(3, first) + recorded(3, second, prefix="other"), 6), 6)
        headings = [line for line in lines if "differ at" in line]
        assert_that(headings).is_length(2)
        assert_that(headings[0]).is_not_equal_to(headings[1])

    def test_whatever_still_reads_alike_is_numbered(self):
        # neither the spelling nor its digest can promise two headings differ; this can, and it is the last line of that
        assert_that(_made_unique(["a", "a", "b"])).is_equal_to(["a #1", "a #2", "b"])
        assert_that(_made_unique(["only"])).described_as("one of a kind keeps its name").is_equal_to(["only"])

    def test_an_ordinary_summary_still_reads_as_a_path(self):
        found = observations(lambda: assert_that({"user": {"role": "s"}}).is_equal_to({"user": {"role": "a"}}))
        lines = render(clusters([(f"p{index}", found) for index in range(5)], 5), 5)
        assert_that(lines[0]).contains("differ at user.role").does_not_contain("key=")


class TestThePluginWiring:
    @staticmethod
    def _config(setting="3"):
        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = _cluster_minimum(setting)
        return config

    def test_the_summary_can_be_turned_off(self):
        assert_that(_cluster_minimum("off")).is_none()

    def test_a_blank_setting_is_the_default_and_not_a_mistake(self):
        """The one value that must not warn, because the warning would come out of `pytest_configure`.

        Under `-W error` a warning raised there fails the run at startup, so an empty line in an ini
        file would turn a suite red on upgrade.  That is the property the default rests on: clustering
        reads a run that already went red and can never be the reason one went red.
        """
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that(_cluster_minimum("")).is_equal_to(MINIMUM_SIZE)
            assert_that(_cluster_minimum("   ")).is_equal_to(MINIMUM_SIZE)
        assert_that(caught).described_as("a blank value said nothing wrong").is_empty()

    def test_off_records_nothing(self):
        config = self._config("off")
        _record_for_clustering(config, "t.py::test_x", diff_of(lambda: assert_that(1).is_equal_to(2)))
        assert_that(config._assertpy_failure_count).is_zero()

    def test_a_failure_that_is_not_an_assertion_at_all_still_counts(self):
        """A live suite fails on timeouts and transport errors far more often than on assertions.

        Counting only assertion failures made the summary a fraction of the wrong whole: four assertion
        failures in a run of fourteen printed as "4 of 4 failing tests differ at role", which reads as every
        failure sharing one cause.
        """
        config = self._config()
        for index in range(3):
            _record_for_clustering(config, f"t.py::test_{index}", TimeoutError("waiting for locator"))
        assert_that(config._assertpy_failure_count).is_equal_to(3)
        assert_that(config._assertpy_failures).described_as("nothing to cluster on").is_empty()

    def test_a_failure_without_a_diff_still_counts_toward_the_whole(self):
        config = self._config()
        _record_for_clustering(config, "t.py::test_x", AssertionFailure("no diff here"))
        assert_that(config._assertpy_failure_count).is_equal_to(1)
        assert_that(config._assertpy_failures).is_empty()

    def test_the_failures_own_diagnostic_reaches_the_key(self):
        config = self._config()
        for index in range(3):
            with pytest.raises(AssertionFailure) as failure:
                assert_that(f"payload-{index}\n".encode()).is_equal_to(f"payload-{index}".encode())
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)
        found = clusters(config._assertpy_failures, 3)
        assert_that(found).described_as("three different payloads, one difference").is_length(1)
        assert_that(found[0].signature.label).contains("surrounding whitespace")

    def test_an_unreadable_setting_falls_back_with_a_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that(_cluster_minimum("banana")).is_equal_to(MINIMUM_SIZE)
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("a count of 2 or more")

    def test_a_count_below_two_falls_back_too(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert_that(_cluster_minimum("1")).is_equal_to(MINIMUM_SIZE)

    def test_a_count_is_taken_as_written(self):
        assert_that(_cluster_minimum("10")).is_equal_to(10)
        assert_that(_cluster_minimum("  off  ")).is_none()

    def test_the_summary_is_written_once_the_run_has_a_cluster(self, capsys):
        config = self._config()
        for index in range(5):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({"role": "super"}).is_equal_to({"role": "admin"})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)
        reporter = SimpleNamespace(write_line=print)
        pytest_terminal_summary(reporter, 1, config)
        assert_that(capsys.readouterr().out).contains("assertpy failure clusters:").contains("role")

    def test_a_run_too_small_to_cluster_says_nothing(self, capsys):
        config = self._config()
        _record_for_clustering(config, "t.py::test_x", diff_of(lambda: assert_that(1).is_equal_to(2)))
        pytest_terminal_summary(SimpleNamespace(write_line=print), 1, config)
        assert_that(capsys.readouterr().out).is_empty()

    def test_a_run_where_nothing_repeats_says_nothing(self, capsys):
        config = self._config()
        for index in range(9):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({f"field{index}": 1}).is_equal_to({f"field{index}": 2})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)
        pytest_terminal_summary(SimpleNamespace(write_line=print), 1, config)
        assert_that(capsys.readouterr().out).is_empty()

    def test_an_observation_survives_the_trip_to_the_controller(self):
        """Under xdist the summary is written on the controller, which runs none of the failures.

        The first version recorded them on the worker's own config and nothing shipped them, so the
        run that most needs a summary - a big suite, in parallel - got none, silently.
        """
        original = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))[0]
        restored = _observation_from_wire(_observation_to_wire(original))
        assert_that(restored).is_equal_to(original)
        assert_that({restored.signature: 1}).contains_key(original.signature)

    def test_a_location_free_observation_survives_it_too(self):
        hint = "every difference here is one of surrounding whitespace"
        original = observations(lambda: assert_that(b"a\n").is_equal_to(b"a"), hint)[0]
        assert_that(_observation_from_wire(_observation_to_wire(original))).is_equal_to(original)

    def test_a_worker_observation_groups_with_a_local_one(self):
        original = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        shipped = [_observation_from_wire(_observation_to_wire(one)) for one in original]
        rows = [(f"local{index}", original) for index in range(2)] + [(f"worker{index}", shipped) for index in range(3)]
        assert_that(clusters(rows, 5)).is_length(1)

    def test_two_workers_reporting_the_same_test_are_two_failing_tests(self):
        """`--dist=each` runs the whole suite on every worker, so one node id legitimately fails twice.

        The denominator summed both executions while the cluster deduplicated them by node id, and the
        summary reported half the run as unexplained when none of it was.  Measured on a live run: 26
        failures over two workers read as `6 of 26` with `17 of 26 not clustered`.
        """
        from assertpy import pytest_plugin

        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0
        original = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        shipped = [_observation_to_wire(one) for one in original]
        for worker in ("gw0", "gw1"):
            node = SimpleNamespace(
                gateway=SimpleNamespace(id=worker),
                workeroutput={
                    "assertpy_failures": [[f"t.py::test_{index}", shipped] for index in range(3)],
                    "assertpy_failure_count": 3,
                },
            )
            pytest_plugin._collect_worker_failures(node)
        recorded = pytest_plugin._controller_failures
        assert_that(pytest_plugin._controller_failure_count[0]).is_equal_to(6)
        assert_that([nodeid for nodeid, _ in recorded]).does_not_contain_duplicates()
        assert_that(clusters(recorded, 6)[0].size).described_as("every execution in the cluster").is_equal_to(6)
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0

    @pytest.mark.parametrize(
        "output",
        [
            pytest.param({"assertpy_failures": [["t.py::test_x", [["not", "an", "observation"]]]]}, id="broken-row"),
            pytest.param({"assertpy_failures": [["t.py::test_x", []]]}, id="rows-without-a-count"),
            pytest.param({"assertpy_failure_count": "many"}, id="count-that-is-not-a-number"),
            pytest.param({"assertpy_failures": []}, id="one-half-of-the-payload"),
            pytest.param({"assertpy_failure_count": 4}, id="the-other-half-of-the-payload"),
            pytest.param(
                {
                    "assertpy_failures": [
                        ["t.py::test_x", [[True, "role", [["key", "'role'"]], "", [], ["a"], "'b'"]]]
                    ],
                    "assertpy_failure_count": 3,
                },
                id="a-row-of-the-right-length-holding-the-wrong-thing",
            ),
            pytest.param(
                {"assertpy_failures": [[7, []]], "assertpy_failure_count": 3},
                id="a-node-id-that-is-not-a-name",
            ),
            pytest.param(
                {"assertpy_failures": [], "assertpy_failure_count": 3.9},
                id="a-count-that-is-not-whole",
            ),
            pytest.param(
                {"assertpy_failures": [], "assertpy_failure_count": True},
                id="a-count-that-is-a-flag",
            ),
            pytest.param({}, id="a-worker-that-does-not-speak-this-protocol"),
            pytest.param(
                {
                    "assertpy_failures": [["t.py::test_x", [[True, "role", [], "", [], "'a'", "'b'"]]]],
                    "assertpy_failure_count": 3,
                },
                id="a-place-with-nowhere-in-it",
            ),
            pytest.param(
                {
                    "assertpy_failures": [["t.py::test_x", [[True, "", [], "", [], "'a'", "'b'"]]]],
                    "assertpy_failure_count": 3,
                },
                id="a-place-with-nowhere-in-it-and-nothing-to-say",
            ),
            pytest.param(
                {
                    "assertpy_failures": [
                        ["t.py::test_x", [[True, "role", [["key", "'role'"]], "a diagnostic", [], "'a'", "'b'"]]]
                    ],
                    "assertpy_failure_count": 3,
                },
                id="a-place-that-also-carries-a-diagnostic",
            ),
            pytest.param(
                {
                    "assertpy_failures": [
                        ["t.py::test_x", [[True, "elsewhere", [["key", "'role'"]], "", [], "1", "2"]]]
                    ],
                    "assertpy_failure_count": 3,
                },
                id="a-heading-that-is-not-what-its-steps-render-to",
            ),
            pytest.param(
                {
                    "assertpy_failures": [["t.py::test_x", [[False, "scalar", [], "", [], "'a'", "'b'"]]]],
                    "assertpy_failure_count": 3,
                },
                id="a-difference-with-neither-a-diagnostic-nor-values",
            ),
            pytest.param(
                {
                    "assertpy_failures": [
                        ["t.py::test_x", [[False, "scalar", [], "a diagnostic", ["1", "2"], "'a'", "'b'"]]]
                    ],
                    "assertpy_failure_count": 3,
                },
                id="a-difference-with-both",
            ),
            pytest.param(
                {
                    "assertpy_failures": [
                        ["t.py::test_x", [[False, "scalar", [["key", "'role'"]], "", ["1", "2"], "'a'", "'b'"]]]
                    ],
                    "assertpy_failure_count": 3,
                },
                id="a-difference-with-no-place-that-brought-one-anyway",
            ),
            pytest.param(
                {
                    "assertpy_failures": [["t.py::test_x", [[True, "role", [["item", "'role'"]], "", [], "1", "2"]]]],
                    "assertpy_failure_count": 3,
                },
                id="a-place-built-from-a-step-that-names-no-place",
            ),
            pytest.param(
                {
                    "assertpy_failures": [["t.py::test_x", []], ["t.py::test_y", []]],
                    "assertpy_failure_count": 1,
                },
                id="count-smaller-than-the-tests-it-shipped",
            ),
        ],
    )
    def test_a_worker_whose_payload_cannot_be_read_is_said_to_be_unreadable(self, output):
        """A controller on one version against a worker on another is an ordinary installation.

        Every way the payload has been wrong so far, and one outcome for all of them: the hook does not
        raise, nothing half-read reaches the summary, and the summary says its counts are partial.

        Two of these were found by taking the guard apart rather than by reading it.  Rows without a
        count add cluster members to a denominator they never raised, so the summary could report six of
        three.  A row of the right length holding a list where a value belongs unpacks happily and then
        raises out of the grouping, past the point where the worker could still be reported: the summary
        vanished and the run said nothing about why.
        """
        from assertpy import pytest_plugin

        pytest_plugin._controller_unreadable_workers[0] = 0
        node = SimpleNamespace(gateway=SimpleNamespace(id="gw0"), workeroutput=output)
        pytest_plugin._collect_worker_failures(node)
        assert_that(pytest_plugin._controller_unreadable_workers[0]).is_equal_to(1)
        assert_that(pytest_plugin._controller_failures).is_empty()
        assert_that(pytest_plugin._controller_failure_count[0]).is_zero()

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3)
        for index in range(4):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({"role": "super"}).is_equal_to({"role": "admin"})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)
        printed: list[str] = []
        pytest_terminal_summary(SimpleNamespace(write_line=printed.append), 1, config)
        assert_that(printed).contains(
            "  the failures of 1 worker could not be read, so these counts cover only the rest"
        )
        assert_that(printed).contains("  4 of 4 failing tests differ at role")
        pytest_plugin._controller_unreadable_workers[0] = 0

    def test_a_worker_that_died_is_not_also_called_unreadable(self):
        from assertpy import pytest_plugin

        pytest_plugin._controller_unreadable_workers[0] = 0
        node = SimpleNamespace(gateway=SimpleNamespace(id="gw0"), workeroutput={"assertpy_failure_count": "many"})
        pytest_plugin._collect_worker_failures(node, died=True)
        assert_that(pytest_plugin._controller_unreadable_workers[0]).is_zero()

    def test_a_worker_that_shipped_nothing_about_clusters_is_never_called_dead(self):
        from assertpy import pytest_plugin

        pytest_plugin._controller_lost_workers[0] = 0
        pytest_plugin._controller_unreadable_workers[0] = 0
        pytest_plugin._collect_worker_failures(SimpleNamespace(gateway=SimpleNamespace(id="gw0"), workeroutput={}))
        assert_that(pytest_plugin._controller_lost_workers[0]).is_zero()
        assert_that(pytest_plugin._controller_unreadable_workers[0]).is_equal_to(1)
        pytest_plugin._controller_unreadable_workers[0] = 0

    def test_one_readable_worker_beside_a_silent_one_says_the_count_is_partial(self):
        """The case the old early return got wrong, end to end.

        This version ships both wire values from every worker whether the summary is on or off, so a
        worker that shipped neither is one that does not speak this protocol.  Its failures are missing
        from the denominator, and saying nothing about that is how a run of twelve prints `6 of 6`.
        """
        from assertpy import pytest_plugin

        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0
        pytest_plugin._controller_unreadable_workers[0] = 0
        original = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        shipped = [_observation_to_wire(one) for one in original]
        speaking = SimpleNamespace(
            gateway=SimpleNamespace(id="gw0"),
            workeroutput={
                "assertpy_failures": [[f"t.py::test_{index}", shipped] for index in range(6)],
                "assertpy_failure_count": 6,
            },
        )
        silent = SimpleNamespace(gateway=SimpleNamespace(id="gw1"), workeroutput={})
        pytest_plugin.pytest_testnodedown(speaking, None)
        pytest_plugin.pytest_testnodedown(silent, None)

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3)
        printed: list[str] = []
        pytest_terminal_summary(SimpleNamespace(write_line=printed.append), 1, config)
        assert_that(printed).contains(
            "  the failures of 1 worker could not be read, so these counts cover only the rest"
        )
        assert_that(printed).contains("  6 of 6 failing tests differ at u.role")
        pytest_plugin._controller_failures.clear()
        pytest_plugin._controller_failure_count[0] = 0
        pytest_plugin._controller_unreadable_workers[0] = 0

    def test_a_second_session_in_one_process_does_not_inherit_the_first(self):
        """The controller's accumulators are module level, so nothing but an explicit release stops a
        run from opening with the previous run's failures already counted.

        Reproduced before the fix: two sessions gave 10 failures and two records where one session had
        produced 5 and one.
        """
        from assertpy import pytest_plugin

        wire = [["t.py::test_x", [[True, "user.role", [["key", "'user'"], ["key", "'role'"]], "", [], "'s'", "'a'"]]]]
        node = SimpleNamespace(workeroutput={"assertpy_failures": wire, "assertpy_failure_count": 5})
        released = SimpleNamespace(getoption=lambda name: False)

        pytest_plugin.pytest_testnodedown(node, None)
        pytest_plugin.pytest_unconfigure(released)
        pytest_plugin.pytest_testnodedown(node, None)
        assert_that(pytest_plugin._controller_failure_count[0]).is_equal_to(5)
        assert_that(pytest_plugin._controller_failures).is_length(1)
        pytest_plugin.pytest_unconfigure(released)

    def test_off_writes_nothing_even_with_failures_recorded(self, capsys):
        config = self._config("off")
        pytest_terminal_summary(SimpleNamespace(write_line=print), 1, config)
        assert_that(capsys.readouterr().out).is_empty()


class TestTheDenominatorCountsEveryRedResult:
    """A live red run is mostly not assertion failures, and the summary says how much of it it covers.

    This gate has now been wrong twice in the same way. First it counted only `AssertionError`, so four
    assertion failures in a run of fourteen printed "4 of 4". Then it counted only the `call` phase, so
    three assertion failures beside thirty errors from one broken fixture printed "3 of 3 failures
    differ at user.role" - a summary claiming one cause for a run that was thirty parts environment.
    """

    @staticmethod
    def _report(when, nodeid="t.py::test_x", failed=True):
        return SimpleNamespace(when=when, failed=failed, nodeid=nodeid)

    @staticmethod
    def _item(config):
        return SimpleNamespace(config=config, nodeid="t.py::test_x")

    def _run(self, when, exc):
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        outcome = SimpleNamespace(get_result=lambda: self._report(when))
        call = SimpleNamespace(excinfo=SimpleNamespace(value=exc), when=when)
        hook = pytest_plugin.pytest_runtest_makereport(self._item(config), call)
        next(hook)
        with pytest.raises(StopIteration):
            hook.send(outcome)
        return config

    @pytest.mark.parametrize("when", ["setup", "call", "teardown"])
    def test_a_failure_in_any_phase_counts(self, when):
        config = self._run(when, RuntimeError("service did not come up"))
        assert_that(config._assertpy_failure_count).is_equal_to(1)

    def test_a_red_report_with_no_exception_at_all_counts(self):
        """A test that passes under `xfail(strict=True)` is a failed report with no exception.

        pytest builds it in its own hook rather than from a raise, so `call.excinfo` is None while the
        report is red.  Counting only failures that carry an exception printed `3 of 3 failing tests`
        on a run pytest called `4 failed`.
        """
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        outcome = SimpleNamespace(get_result=lambda: self._report("call"))
        call = SimpleNamespace(excinfo=None, when="call")
        hook = pytest_plugin.pytest_runtest_makereport(self._item(config), call)
        next(hook)
        with pytest.raises(StopIteration):
            hook.send(outcome)
        assert_that(config._assertpy_failure_count).is_equal_to(1)
        assert_that(config._assertpy_failures).described_as("nothing to cluster on").is_empty()

    def test_a_passing_report_counts_nothing(self):
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        outcome = SimpleNamespace(get_result=lambda: self._report("call", failed=False))
        call = SimpleNamespace(excinfo=None, when="call")
        hook = pytest_plugin.pytest_runtest_makereport(self._item(config), call)
        next(hook)
        with pytest.raises(StopIteration):
            hook.send(outcome)
        assert_that(config._assertpy_failure_count).is_zero()

    def test_one_test_going_red_twice_is_one_test(self):
        """pytest counts a failed call and a broken teardown as a failure and an error, and it is right.

        The summary counts tests, because it answers "how much of this run is one cause", and a test
        whose teardown also blew up is one broken test rather than two.  The lines say `failing tests`
        so the two readings cannot be confused for each other.
        """
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        for when, exc in (("call", AssertionError("call")), ("teardown", RuntimeError("teardown"))):
            outcome = SimpleNamespace(get_result=lambda when=when: self._report(when))
            call = SimpleNamespace(excinfo=SimpleNamespace(value=exc), when=when)
            hook = pytest_plugin.pytest_runtest_makereport(self._item(config), call)
            next(hook)
            with pytest.raises(StopIteration):
                hook.send(outcome)
        assert_that(config._assertpy_failure_count).described_as("one test, two red reports").is_equal_to(1)

    @pytest.mark.parametrize("base", [RuntimeError, AssertionError], ids=["someone-elses", "one-of-ours"])
    def test_an_exception_that_fights_back_is_still_only_a_failure(self, base):
        """`diff` is this library's attribute name on somebody else's exception.

        Reading it runs their code, and a property that raises took the whole run down with
        INTERNALERROR: the reader lost every result to a summary they did not ask for.

        Both bases on purpose.  An `AssertionError` subclass goes further into the hook, past the point
        where the report sections are built from those same attributes, and that second set of reads was
        outside its own barrier until this test went looking for it.
        """
        from assertpy import pytest_plugin

        class HostileError(base):
            @property
            def diff(self):
                raise ValueError("reading this raises")

            @property
            def actual(self):
                raise ValueError("this one too")

        config = SimpleNamespace(
            _assertpy_failures=[],
            _assertpy_failure_count=0,
            _assertpy_cluster_minimum=3,
            _assertpy_diff_enabled=True,
            _assertpy_diff_max=50,
            option=SimpleNamespace(color="no"),
        )
        report = self._report("call")
        report.sections = []
        outcome = SimpleNamespace(get_result=lambda: report)
        call = SimpleNamespace(excinfo=SimpleNamespace(value=HostileError("hostile")), when="call")
        hook = pytest_plugin.pytest_runtest_makereport(self._item(config), call)
        next(hook)
        with pytest.raises(StopIteration):
            hook.send(outcome)
        assert_that(config._assertpy_failure_count).described_as("counted like any other red result").is_equal_to(1)
        assert_that(config._assertpy_failures).described_as("and clustered on nothing").is_empty()
        assert_that(report.sections).described_as("nothing decorated, and nothing raised").is_empty()

    def test_a_failed_collection_is_counted_apart_from_the_tests(self):
        """A collection failure never reaches a test report, and it is red.

        Under `--continue-on-collection-errors` pytest finishes `3 failed, 1 error` while the summary had
        seen three, so it printed `3 of 3` with nothing about the fourth. Said on its own line rather than
        added to the denominator, because `3 of 4 failing tests` would name a fourth test that never
        existed. Without that flag the run stops and no summary is written at all.
        """
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3)
        pytest_plugin._session_config[0] = config
        pytest_plugin._controller_collect_errors[0] = 0
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid="broken.py"))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_equal_to(1)
        assert_that(config._assertpy_failure_count).described_as("a module is not a test").is_zero()
        pytest_plugin._controller_collect_errors[0] = 0
        pytest_plugin._session_config[0] = None

    def test_a_collection_that_worked_counts_nothing(self):
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3)
        pytest_plugin._session_config[0] = config
        pytest_plugin._controller_collect_errors[0] = 0
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=False, nodeid="fine.py"))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_zero()
        pytest_plugin._session_config[0] = None

    def test_a_run_with_the_summary_off_does_not_count_collections_either(self):
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=None)
        pytest_plugin._session_config[0] = config
        pytest_plugin._controller_collect_errors[0] = 0
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid="broken.py"))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_zero()
        pytest_plugin._session_config[0] = None

    def test_a_worker_does_not_count_the_collection_every_worker_repeats(self):
        # under xdist each worker collects the whole suite: `3 of 6` on a run pytest called `3 failed, 1 error`
        from assertpy import pytest_plugin

        worker = SimpleNamespace(
            _assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3, workeroutput={}
        )
        pytest_plugin._session_config[0] = worker
        pytest_plugin._controller_collect_errors[0] = 0
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid="broken.py"))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_zero()
        pytest_plugin._session_config[0] = None

    def test_a_collection_failure_outside_a_session_is_ignored(self):
        from assertpy import pytest_plugin

        pytest_plugin._session_config[0] = None
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid="broken.py"))

    def test_a_setup_error_is_counted_but_never_clustered(self):
        config = self._run("setup", RuntimeError("service did not come up"))
        assert_that(config._assertpy_failures).is_empty()


class TestAWorkerThatDiedIsNotSilentlyIgnored:
    """A worker killed mid-run never reaches its `sessionfinish`, so nothing it recorded ships.

    Reproduced under `-n 2`: a run of thirteen failures, one of which killed its worker, printed
    `6 of 6 failing tests differ at user.role`. Every number in the summary was a share of the half the
    controller happened to receive, and nothing said so.
    """

    @staticmethod
    def _cluster():
        return clusters(recorded(6, located("user.role")), 6)

    def test_the_summary_says_the_counts_are_partial(self):
        lines = render(self._cluster(), 6, 1)
        assert_that(lines[0]).is_equal_to("1 worker died, so these counts cover only what was reported")
        assert_that(lines[1]).contains("6 of 6 failing tests differ at user.role")

    def test_two_of_them_read_as_plural(self):
        assert_that(render(self._cluster(), 6, 2)[0]).contains("2 workers died")

    def test_a_failed_collection_is_named_apart_from_the_tests(self):
        # red but not a test: measured as `3 of 4 failing tests` on a run pytest called `3 failed, 1 error`.
        # "collection error" rather than "module": a package or a plugin's collector can fail too
        lines = render(self._cluster(), 6, collect_errors=1)
        assert_that(lines[0]).is_equal_to("1 collection error, not counted below")
        assert_that(lines[1]).contains("6 of 6 failing tests")
        assert_that(render(self._cluster(), 6, collect_errors=2)[0]).is_equal_to(
            "2 collection errors, not counted below"
        )

    def test_an_unreadable_worker_is_not_reported_as_a_crash(self):
        lines = render(self._cluster(), 6, lost_workers=0, unreadable_workers=1)
        assert_that(lines[0]).is_equal_to(
            "the failures of 1 worker could not be read, so these counts cover only the rest"
        )
        assert_that(lines[0]).does_not_contain("died")

    def test_two_unreadable_workers_read_as_plural(self):
        lines = render(self._cluster(), 6, unreadable_workers=2)
        assert_that(lines[0]).contains("the failures of 2 workers could not be read")

    def test_both_kinds_of_loss_are_said_separately(self):
        lines = render(self._cluster(), 6, lost_workers=1, unreadable_workers=1)
        assert_that(lines[0]).contains("1 worker died")
        assert_that(lines[1]).contains("could not be read")

    def test_an_intact_run_says_nothing_about_workers(self):
        assert_that(render(self._cluster(), 6)[0]).does_not_contain("worker")

    def test_a_worker_that_finished_normally_is_not_counted_as_lost(self):
        from assertpy import pytest_plugin

        pytest_plugin._controller_lost_workers[0] = 0
        pytest_plugin.pytest_testnodedown(SimpleNamespace(workeroutput={}), None)
        assert_that(pytest_plugin._controller_lost_workers[0]).is_zero()

    def test_a_worker_that_died_is(self):
        from assertpy import pytest_plugin

        pytest_plugin._controller_lost_workers[0] = 0
        pytest_plugin.pytest_testnodedown(SimpleNamespace(workeroutput={}), "Node crashed")
        assert_that(pytest_plugin._controller_lost_workers[0]).is_equal_to(1)
        pytest_plugin.pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))
        assert_that(pytest_plugin._controller_lost_workers[0]).described_as("released with the rest").is_zero()

    def test_the_note_reaches_the_terminal(self, capsys):
        from assertpy import pytest_plugin

        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        for index in range(4):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({"role": "super"}).is_equal_to({"role": "admin"})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)
        pytest_plugin.pytest_testnodedown(SimpleNamespace(workeroutput={}), "Node crashed")
        pytest_terminal_summary(SimpleNamespace(write_line=print), 1, config)
        assert_that(capsys.readouterr().out).contains("1 worker died")
        pytest_plugin.pytest_unconfigure(SimpleNamespace(getoption=lambda name: False))


class TestTheSummaryHasBounds:
    """A diagnostic that grows with the run is a diagnostic that hurts the worst runs most.

    Raised by an external review: the value cap was there, but nothing bounded how many distinct values
    a cluster kept or how many clusters printed. Twenty thousand failures differing at one field held
    twenty thousand examples, 888 KB, to print one of them and a count.
    """

    @staticmethod
    def _many(count, *, expected="9"):
        key = located("total", (("key", "'total'"),))
        return [(f"t{index}", [Observation(key, str(index).zfill(6), expected)]) for index in range(count)]

    def test_a_side_keeps_one_past_the_cap_so_its_length_says_it_was_capped(self):
        found = clusters(self._many(500), 500)[0]
        assert_that(found.actuals).is_length(_EXAMPLE_LIMIT + 1)
        assert_that(found.expecteds).described_as("one expected value, kept whole").is_length(1)

    def test_a_capped_side_reads_as_a_floor_not_a_total(self):
        lines = render(clusters(self._many(500), 500), 500)
        assert_that(lines[1]).is_equal_to(f"    actual:   000000 and {_EXAMPLE_LIMIT}+ other values")

    def test_an_uncapped_side_still_gives_the_exact_count(self):
        lines = render(clusters(self._many(4), 4), 4)
        assert_that(lines[1]).is_equal_to("    actual:   000000 and 3 other values")

    def test_the_printed_example_survives_the_cap(self):
        # the cap must not undo the sort: under xdist the arrival order is whatever the workers did
        rows = self._many(500)
        assert_that(render(clusters(list(reversed(rows)), 500), 500)).is_equal_to(render(clusters(rows, 500), 500))

    def test_only_the_largest_clusters_print_and_the_rest_are_counted(self):
        rows = []
        for field in range(8):
            key = located(f"field{field}", (("key", f"'field{field}'"),))
            rows += [(f"f{field}t{index}", [Observation(key, "1", "2")]) for index in range(4)]
        lines = render(clusters(rows, 32), 32)
        assert_that([line for line in lines if "differ at" in line]).is_length(5)
        assert_that(lines[-1]).is_equal_to("3 more clusters not shown")

    def test_one_omitted_cluster_reads_as_one(self):
        rows = []
        for field in range(6):
            key = located(f"field{field}", (("key", f"'field{field}'"),))
            rows += [(f"f{field}t{index}", [Observation(key, "1", "2")]) for index in range(4)]
        assert_that(render(clusters(rows, 24), 24)[-1]).is_equal_to("1 more cluster not shown")

    def test_nothing_is_said_about_omissions_when_there_are_none(self):
        assert_that(render(clusters(recorded(4, located("a")), 4), 4)).does_not_contain("not shown")


class TestTheSummaryNeverTakesTheRunDown:
    """It is optional output written from a report hook, so it fails open.

    The parts have their own guards, and this is the barrier behind them: whatever else breaks, the
    reader keeps the run's actual results.
    """

    def test_a_broken_reporter_warns_instead_of_raising(self):
        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        for index in range(4):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({"role": "super"}).is_equal_to({"role": "admin"})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)

        def explode(_line):
            raise RuntimeError("terminal is gone")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pytest_terminal_summary(SimpleNamespace(write_line=explode), 1, config)
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("could not write its failure-cluster summary")
        assert_that(str(caught[0].message)).contains("terminal is gone")

    def test_the_notice_itself_cannot_raise_under_warnings_as_errors(self):
        # under `-W error` the barrier's own notice becomes an exception, replacing the failure it was catching
        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0)
        config._assertpy_cluster_minimum = 3
        for index in range(4):
            with pytest.raises(AssertionFailure) as failure:
                assert_that({"role": "super"}).is_equal_to({"role": "admin"})
            _record_for_clustering(config, f"t.py::test_{index}", failure.value)

        def explode(_line):
            raise RuntimeError("terminal is gone")

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            pytest_terminal_summary(SimpleNamespace(write_line=explode), 1, config)


class TestEveryCapAtItsOwnBoundary:
    """A cap is wrong at exactly its limit or nowhere, and that is the value no test was using."""

    def test_a_value_of_exactly_the_limit_is_kept_whole(self):
        assert_that(_bounded("x" * _VALUE_LIMIT)).is_equal_to("x" * _VALUE_LIMIT)

    def test_one_character_over_the_limit_is_cut(self):
        assert_that(_bounded("x" * (_VALUE_LIMIT + 1))).is_equal_to("x" * _VALUE_LIMIT + "... (1 more chars)")

    def test_the_dropped_count_is_what_was_dropped(self):
        assert_that(_bounded("x" * (_VALUE_LIMIT + 300))).ends_with("... (300 more chars)")

    def test_a_spelling_of_exactly_the_limit_keeps_no_digest(self):
        spelled = _spelled_out((("key", "x" * (_VALUE_LIMIT - len("key="))),))
        assert_that(spelled).is_length(_VALUE_LIMIT).does_not_contain("[")

    def test_a_spelling_one_over_the_limit_carries_one(self):
        spelled = _spelled_out((("key", "x" * (_VALUE_LIMIT - len("key=") + 1)),))
        assert_that(spelled).matches(r"^key=x{196}\.\.\. \[[0-9a-f]{8}\]$")

    def test_a_cluster_holding_exactly_the_example_limit_counts_them(self):
        assert_that(_side(tuple(f"v{index:03d}" for index in range(_EXAMPLE_LIMIT)))).is_equal_to(
            f"v000 and {_EXAMPLE_LIMIT - 1} other values"
        )

    def test_one_value_past_it_reads_as_a_floor(self):
        assert_that(_side(tuple(f"v{index:03d}" for index in range(_EXAMPLE_LIMIT + 1)))).is_equal_to(
            f"v000 and {_EXAMPLE_LIMIT}+ other values"
        )


class TestTheSpellingThatTellsTwoLocationsApart:
    """`key=3` against `key='3'`, which is the whole reason this spelling exists beside the path."""

    def test_the_hops_are_separated(self):
        assert_that(_spelled_out((("key", "'a'"), ("attr", "b")))).is_equal_to("key='a'.attr=b")

    def test_two_long_locations_sharing_a_prefix_stay_apart(self):
        first = _spelled_out((("key", "'" + "x" * 400 + "'"),))
        second = _spelled_out((("key", "'" + "x" * 399 + "y'"),))
        assert_that(first).is_not_equal_to(second)
        assert_that(first[:_VALUE_LIMIT]).is_equal_to(second[:_VALUE_LIMIT])


class TestNoRenderingRaisesOnASurrogate:
    """`repr` escapes a lone surrogate in a string, but a `__repr__` of somebody's own can return one.

    Both digests encode that text, and a codec asked to refuse would take the summary hook down.
    """

    class _LoneSurrogate:
        def __repr__(self):
            return "lone " + chr(0xD800) + " surrogate"

    def test_a_value_key_survives_it(self):
        assert_that(_identity(self._LoneSurrogate())).is_length(32)

    def test_a_spelling_survives_it(self):
        spelled = _spelled_out((("key", chr(0xD800) + "x" * 400),))
        assert_that(spelled).ends_with("]")

    def test_a_value_key_is_sixteen_bytes(self):
        assert_that(_identity("anything")).is_length(32).matches(r"^[0-9a-f]{32}$")


class TestALocationRendersForAReader:
    """Quotes come off a mapping key so the path reads as one, which two lengths of key get wrong."""

    def test_an_empty_key_loses_its_quotes(self):
        assert_that(render_path((("key", "''"),))).is_equal_to("")

    def test_a_key_that_is_one_quote_keeps_it(self):
        # arrives only over the wire: `repr` never makes a bare quote, and `is_well_formed` compares against the `where`
        assert_that(render_path((("key", "'"),))).is_equal_to("'")

    def test_a_quoted_key_loses_its_quotes(self):
        assert_that(render_path((("key", "'role'"),))).is_equal_to("role")

    def test_an_unquoted_key_is_left_alone(self):
        assert_that(render_path((("key", "3"),))).is_equal_to("3")


class TestALocationFreeSignatureCarriesExactlyTwoValues:
    """`signature()` sets a pair, so a payload with any other count describes a difference it cannot."""

    def test_a_pair_is_well_formed(self):
        assert_that(is_well_formed(Signature(False, "scalar", values=("a", "b")))).is_true()

    @pytest.mark.parametrize("values", [(), ("a",), ("a", "b", "c")])
    def test_any_other_count_is_not(self, values):
        assert_that(is_well_formed(Signature(False, "scalar", values=values))).is_false()

    @pytest.mark.parametrize("kind", ["contains", "set"])
    def test_a_kind_whose_fields_hold_presence_carries_no_values(self, kind):
        # `signature()` refuses to pair values here: a payload that did would print the `None` for a missing item
        assert_that(is_well_formed(Signature(False, kind, values=("a", "b")))).is_false()

    @pytest.mark.parametrize("kind", ["contains", "set", "scalar", "string"])
    def test_a_diagnostic_keys_any_kind(self, kind):
        assert_that(is_well_formed(Signature(False, kind, label="one of bytes"))).is_true()


class TestTheShapeOfAValueKeyedSignature:
    """The values family is the one `signature()` builds by hand, and every field of it was unasserted."""

    @staticmethod
    def _entry(actual, expected, absent=None):
        return SimpleNamespace(steps=(), actual=actual, expected=expected, absent=absent)

    def test_a_side_that_was_absent_keys_apart_from_one_that_holds_none(self):
        """Read as a value, an absent key printed as `None` and joined the cluster of real `None`s."""
        missing = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(None, 2, absent="actual"))
        really_none = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(None, 2))
        assert_that(missing).is_not_equal_to(really_none)

    def test_it_is_not_located_and_names_its_kind(self):
        key = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(1, 2))
        assert_that(key.located).is_equal_to(False)
        assert_that(key.where).is_equal_to("scalar")
        assert_that(key.values).is_length(2)

    def test_both_sides_decide_identity(self):
        one = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(1, 2))
        other = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(1, 3))
        assert_that(one).is_not_equal_to(other)

    def test_what_it_builds_is_well_formed(self):
        key = signature(SimpleNamespace(kind="scalar", entries=()), self._entry(1, 2))
        assert_that(is_well_formed(key)).is_true()


class _HashableList(list):
    """Mutable and hashable at once, which is what lets a cycle run through a set member or a dict key."""

    __hash__ = object.__hash__
    __eq__ = object.__eq__


class TestWalkingAValueThatReachesBackIntoItself:
    """A container holding itself has to be marked rather than followed, on every branch of the walk."""

    def test_a_tuple_that_reaches_itself(self):
        holder = []
        pair = (1, holder)
        holder.append(pair)
        assert_that(stable_repr(pair)).is_equal_to("(1, [...])")

    def test_a_list_that_reaches_itself(self):
        inner = [1]
        inner.append(inner)
        assert_that(stable_repr(inner)).is_equal_to("[1, ...]")

    def test_a_dict_that_reaches_itself(self):
        inner = {}
        inner["self"] = inner
        assert_that(stable_repr(inner)).is_equal_to("{'self': ...}")

    def test_a_set_member_that_reaches_the_set(self):
        """A mutable container is hashable when it borrows `object.__hash__`, so it can be a member."""
        member = _HashableList()
        outer = {member}
        member.append(outer)
        assert_that(stable_repr(outer)).is_equal_to("{[...]}")

    def test_a_dict_key_that_reaches_the_dict(self):
        key = _HashableList()
        mapping = {key: 0}
        key.append(mapping)
        assert_that(stable_repr(mapping)).is_equal_to("{[...]: 0}")

    def test_a_set_inside_a_tuple_is_still_ordered(self):
        assert_that(stable_repr((frozenset({2, 1}),))).is_equal_to("({1, 2},)")
        assert_that(stable_repr((frozenset({2, 1}), 3))).is_equal_to("({1, 2}, 3)")


class TestWhatTheDenominatorAllows:
    """`total_failures` is the run's own count, and a summary over nothing is not a summary."""

    @staticmethod
    def _recorded(count):
        key = Signature(True, "role", (("attr", "'role'"),))
        return [(f"t{index}", [Observation(key, "a", "b")]) for index in range(count)]

    def test_no_failures_means_no_clusters(self):
        assert_that(clusters(self._recorded(3), 0, minimum=1)).is_empty()

    def test_a_negative_count_means_the_same(self):
        assert_that(clusters(self._recorded(3), -1, minimum=1)).is_empty()

    def test_one_failure_can_still_be_a_cluster(self):
        assert_that(clusters(self._recorded(1), 1, minimum=1)).is_length(1)


class TestTheSmallestExampleSurvivesTheCap:
    """Past the cap a cluster keeps the smallest value, whatever order the failures arrived in."""

    @staticmethod
    def _recorded(values):
        key = Signature(True, "role", (("attr", "'role'"),))
        return [(f"t{index}", [Observation(key, value, "b")]) for index, value in enumerate(values)]

    def test_a_later_smaller_value_replaces_the_largest(self):
        values = [f"v{index:03d}" for index in range(1, _EXAMPLE_LIMIT + 2)] + ["v000"]
        found = clusters(self._recorded(values), len(values))
        assert_that(found[0].actuals[0]).is_equal_to("v000")

    def test_a_repeat_of_the_smallest_evicts_nothing(self):
        values = [f"v{index:03d}" for index in range(_EXAMPLE_LIMIT + 1)] + ["v000"]
        found = clusters(self._recorded(values), len(values))
        assert_that(found[0].actuals).is_length(_EXAMPLE_LIMIT + 1)
        assert_that(found[0].actuals[-1]).is_equal_to(f"v{_EXAMPLE_LIMIT:03d}")


@pytest.fixture
def _released_controller_state():
    """The controller accumulators are module-level, so a test that fills them has to empty them."""
    counters = (
        pytest_plugin._controller_failure_count,
        pytest_plugin._controller_lost_workers,
        pytest_plugin._controller_unreadable_workers,
        pytest_plugin._controller_collect_errors,
    )

    def release():
        pytest_plugin._controller_failures.clear()
        for counter in counters:
            counter[0] = 0
        pytest_plugin._session_config[0] = None

    release()
    yield
    release()


@pytest.mark.usefixtures("_released_controller_state")
class TestTheSummaryOnAControllerThatRanNothingItself:
    """Under xdist every failure arrives over the wire, so the controller's own tallies stay empty."""

    @staticmethod
    def _shipped(count):
        found = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        pytest_plugin._controller_failures.extend((f"gw0::t.py::test_{index}", found) for index in range(count))
        pytest_plugin._controller_failure_count[0] = count

    def test_the_whole_run_is_what_the_workers_reported_and_nothing_more(self):
        self._shipped(3)
        printed: list[str] = []
        pytest_plugin._write_cluster_summary(
            SimpleNamespace(write_line=printed.append), SimpleNamespace(_assertpy_cluster_minimum=3)
        )
        assert_that(printed[0]).described_as("held off the run's output by a blank line").is_empty()
        assert_that(printed).contains("assertpy failure clusters:")
        assert_that(printed).contains("  3 of 3 failing tests differ at u.role")

    def test_a_run_of_exactly_the_configured_size_is_a_cluster(self):
        self._shipped(2)
        pytest_plugin._controller_collect_errors[0] = 1
        printed: list[str] = []
        pytest_plugin._write_cluster_summary(
            SimpleNamespace(write_line=printed.append), SimpleNamespace(_assertpy_cluster_minimum=2)
        )
        assert_that(printed).contains("  2 of 2 failing tests differ at u.role")
        assert_that(printed).contains("  1 collection error, not counted below")

    def test_a_config_the_hook_was_handed_without_configure_writes_nothing(self):
        printed: list[str] = []
        pytest_plugin._write_cluster_summary(SimpleNamespace(write_line=printed.append), SimpleNamespace())
        assert_that(printed).is_empty()


@pytest.mark.usefixtures("_released_controller_state")
class TestWhatTheSummaryDoesNotExplain:
    """The leftover count names the bar that left them out, so it has to be the run's own bar."""

    def test_the_leftover_is_counted_against_the_bar_the_run_configured(self):
        shared = observations(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        lonely = observations(lambda: assert_that({"other": 1}).is_equal_to({"other": 2}))
        pytest_plugin._controller_failures.extend(
            [("gw0::t.py::test_0", shared), ("gw0::t.py::test_1", shared), ("gw0::t.py::test_2", lonely)]
        )
        pytest_plugin._controller_failure_count[0] = 3
        printed: list[str] = []
        pytest_plugin._write_cluster_summary(
            SimpleNamespace(write_line=printed.append), SimpleNamespace(_assertpy_cluster_minimum=2)
        )
        assert_that(printed).contains("  1 of 3 outside any cluster of 2")


class TestWhatComesOffTheWireIsCheckedFieldByField:
    """A coordinate is two names, and both halves of that have to be checked or the summary raises."""

    def test_a_step_whose_parts_are_not_both_names_is_refused_as_a_type_error(self):
        # `len(step) == 2` alone lets a non-string coordinate through, and the summary then raises out of the grouping
        with pytest.raises(TypeError):
            _observation_from_wire([True, "role", [["key", 5]], "", [], "'a'", "'b'"])

    def test_a_step_of_the_wrong_length_is_refused_as_a_type_error(self):
        with pytest.raises(TypeError):
            _observation_from_wire([True, "role", [["key", "'role'", "extra"]], "", [], "'a'", "'b'"])


@pytest.mark.usefixtures("_released_controller_state")
class TestTheControllerSideBookkeeping:
    """What the controller records off a node, and what it records off a config that never configured."""

    def test_a_node_that_shipped_no_output_at_all_is_counted_rather_than_raising(self):
        # an exception out of `testnodedown` is answered with INTERNALERROR, which costs the whole run
        pytest_plugin._collect_worker_failures(SimpleNamespace())
        assert_that(pytest_plugin._controller_unreadable_workers[0]).is_equal_to(1)

    def test_two_unreadable_workers_are_two(self):
        for _ in range(2):
            pytest_plugin._collect_worker_failures(SimpleNamespace(workeroutput={}))
        assert_that(pytest_plugin._controller_unreadable_workers[0]).is_equal_to(2)

    def test_a_node_with_no_name_of_its_own_prefixes_with_nothing(self):
        # the prefix tells two workers running one test apart, and an invented one makes a node id nobody can look up
        wire = [["t.py::test_x", [[True, "user.role", [["key", "'user'"], ["key", "'role'"]], "", [], "'s'", "'a'"]]]]
        node = SimpleNamespace(workeroutput={"assertpy_failures": wire, "assertpy_failure_count": 1})
        pytest_plugin._collect_worker_failures(node)
        assert_that([nodeid for nodeid, _ in pytest_plugin._controller_failures]).is_equal_to(["::t.py::test_x"])

    def test_two_failed_collections_are_two(self):
        pytest_plugin._session_config[0] = SimpleNamespace(_assertpy_cluster_minimum=3)
        for name in ("broken.py", "also-broken.py"):
            pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid=name))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_equal_to(2)

    def test_a_session_config_from_before_the_summary_existed_is_tolerated(self):
        pytest_plugin._session_config[0] = SimpleNamespace()
        pytest_plugin.pytest_collectreport(SimpleNamespace(failed=True, nodeid="broken.py"))
        assert_that(pytest_plugin._controller_collect_errors[0]).is_zero()

    def test_a_failure_with_a_diff_but_no_record_behind_it_is_still_grouped(self):
        config = SimpleNamespace(_assertpy_failures=[], _assertpy_failure_count=0, _assertpy_cluster_minimum=3)
        failure = AssertionError("re-wrapped")
        failure.diff = diff_of(lambda: assert_that({"u": {"role": "s"}}).is_equal_to({"u": {"role": "a"}}))
        _record_for_clustering(config, "t.py::test_x", failure)
        assert_that(config._assertpy_failures).is_length(1)

    def test_a_config_the_hook_was_handed_without_configure_records_nothing(self):
        config = SimpleNamespace()
        _record_for_clustering(config, "t.py::test_x", AssertionError("x"))
        assert_that(vars(config)).is_empty()


class TestASideThatWasNotThereIsNotAValue:
    """Read as a value, an absent key printed as `None` and joined the cluster of the real ones."""

    def test_the_summary_says_it_was_absent(self):
        outcome = assert_that({"a": 1}).check().is_equal_to({"a": 1, "b": 2})
        actuals = [one.actual for one in observations_of(outcome.diff, outcome.hint)]
        assert_that(actuals).contains("<absent>").does_not_contain("None")

    def test_a_value_that_really_is_none_still_reads_as_none(self):
        outcome = assert_that({"a": 1, "b": None}).check().is_equal_to({"a": 1, "b": 2})
        actuals = [one.actual for one in observations_of(outcome.diff, outcome.hint)]
        assert_that(actuals).contains("None")
