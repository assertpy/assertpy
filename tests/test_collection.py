import collections
import logging

import pytest

from assertpy import assert_that, assert_warn


def test_is_iterable():
    assert_that(["a", "b", "c"]).is_iterable()
    assert_that((1, 2, 3)).is_iterable()
    assert_that("foo").is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.keys()).is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.values()).is_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}.items()).is_iterable()


def test_is_iterable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_iterable()
    assert_that(str(exc_info.value)).is_equal_to("Expected iterable, but was not.")


def test_is_not_iterable():
    assert_that(123).is_not_iterable()
    assert_that({"a": 1, "b": 2, "c": 3}).is_iterable()


def test_is_not_iterable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_not_iterable()
    assert_that(str(exc_info.value)).is_equal_to("Expected not iterable, but was.")


def test_is_subset_of():
    assert_that(["a", "b", "c"]).is_subset_of(["a", "b", "c"])
    assert_that(["a", "b", "c"]).is_subset_of(["a", "b", "c", "d"])
    assert_that(["a", "b", "c"]).is_subset_of(["a"], ["b"], ["c"])
    assert_that(["a", "b", "c"]).is_subset_of("a", "b", "c")
    assert_that(["a", "b", "a"]).is_subset_of(["a", "a", "b"])
    assert_that((1, 2, 3)).is_subset_of((1, 2, 3))
    assert_that((1, 2, 3)).is_subset_of((1, 2, 3, 4))
    assert_that((1, 2, 3)).is_subset_of((1,), (2,), (3,))
    assert_that((1, 2, 3)).is_subset_of(1, 2, 3)
    assert_that((1, 2, 1)).is_subset_of(1, 1, 2)
    assert_that("foo").is_subset_of("abcdefghijklmnopqrstuvwxyz")
    assert_that("foo").is_subset_of("abcdef", {"m", "n", "o"}, ["x", "y"])
    assert_that({1, 2, 3}).is_subset_of({1, 2, 3, 4})
    assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 2, "c": 3})
    assert_that({"a": 1, "b": 2}).is_subset_of({"a": 3}, {"b": 2}, {"a": 1})


def test_is_subset_of_accepts_unhashable_items():
    # the contains family compares with ==; is_subset_of built a set and crashed with a raw TypeError
    assert_that([{"a": 1}]).is_subset_of([{"a": 1}, {"b": 2}])
    assert_that([[1]]).is_subset_of([[1], [2]])


def test_is_subset_of_unhashable_failure_is_a_clean_assertion():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([{"a": 1}, {"z": 9}]).is_subset_of([{"a": 1}, {"b": 2}])
    assert_that(str(exc_info.value)).contains("was missing")


def test_is_subset_of_single_item_superset():
    assert_that(["a"]).is_subset_of(["a"])
    assert_that((1,)).is_subset_of((1,))
    assert_that("ab").is_subset_of("ab")
    assert_that({1}).is_subset_of({1})
    assert_that({"a": 1}).is_subset_of({"a": 1})


def test_is_subset_of_failure_empty_superset():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of([])
    assert_that(str(exc_info.value)).contains("to be subset of <>")


def test_is_subset_of_failure_single_item_superset():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of(["x"])
    assert_that(str(exc_info.value)).contains("to be subset of <{'x'}>")
    assert_that(str(exc_info.value)).contains("but <'a', 'b', 'c'> were missing.")


def test_is_subset_of_failure_array():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of(["a", "b"])
    assert_that(str(exc_info.value)).contains("but <c> was missing.")


def test_is_subset_of_failure_set():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({1, 2, 3}).is_subset_of({1, 2})
    assert_that(str(exc_info.value)).contains("but <3> was missing.")


def test_is_subset_of_failure_string():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("abc").is_subset_of("abx")
    assert_that(str(exc_info.value)).contains("but <c> was missing.")


def test_is_subset_of_failure_dict_key():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "c": 3})
    assert_that(str(exc_info.value)).contains("but <{'b': 2}> was missing")


def test_is_subset_of_failure_dict_value():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 22})
    assert_that(str(exc_info.value)).contains("but <{'b': 2}> was missing.")


def test_is_subset_of_failure_single_key_dict_value():
    # a single-key superset dict previously crashed with KeyError while formatting the message
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": 5}).is_subset_of({"a": 3})
    assert_that(str(exc_info.value)).contains("to be subset of <{'a': 3}>").contains("missing")


def test_is_subset_of_failure_bad_dict_arg1():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of("foo")
    assert_that(str(exc_info.value)).contains("arg #1").contains("must be dict-like")


def test_is_subset_of_failure_bad_dict_arg2():
    with pytest.raises(TypeError) as exc_info:
        assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1}, "foo")
    assert_that(str(exc_info.value)).contains("arg #2").contains("must be dict-like")


def test_is_subset_of_bad_val_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_subset_of(1234)
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_is_subset_of_bad_arg_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(["a", "b", "c"]).is_subset_of()
    assert_that(str(exc_info.value)).is_equal_to("one or more superset args must be given")


def test_is_sorted():
    assert_that([1, 2, 3]).is_sorted()
    assert_that((3, 2, 1)).is_sorted(reverse=True)
    assert_that(["a", "b", "c"]).is_sorted()
    assert_that(["c", "b", "a"]).is_sorted(reverse=True)
    assert_that("abcdefghijklmnopqrstuvwxyz").is_sorted()
    assert_that("zyxwvutsrqponmlkjihgfedcba").is_sorted(reverse=True)
    assert_that([{"a": 1}, {"a": 2}, {"a": 3}]).is_sorted(key=lambda value: value["a"])
    assert_that([{"a": 3}, {"a": 2}, {"a": 1}]).is_sorted(key=lambda value: value["a"], reverse=True)
    assert_that([("a", 2), ("b", 1)]).is_sorted(key=lambda value: value[0])
    assert_that([("a", 2), ("b", 1)]).is_sorted(key=lambda value: value[1], reverse=True)
    assert_that([1, 1, 1]).is_sorted()
    assert_that([1, 1, 1]).is_sorted(reverse=True)
    assert_that([]).is_sorted()
    assert_that([1]).is_sorted()

    ordered = collections.OrderedDict([("a", 2), ("b", 1)])
    assert_that(ordered).is_sorted()
    assert_that(ordered.keys()).is_sorted()


def test_is_sorted_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3, 4, 5, 6, -1, 7, 8, 9]).is_sorted()
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3, 4, 5, 6, -1, 7, 8, 9]> to be sorted, but subset <6, -1> at index 5 is not."
    )


def test_is_sorted_reverse_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([1, 2, 3]).is_sorted(reverse=True)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <[1, 2, 3]> to be sorted reverse, but subset <1, 2> at index 0 is not."
    )


def test_is_sorted_failure_bad_val():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_sorted()
    assert_that(str(exc_info.value)).is_equal_to("val must be iterable, but was <123> (int)")


def test_chaining():
    assert_that(["a", "b", "c"]).is_iterable().is_type_of(list).is_sorted().is_length(3)


def test_filter_that_empties_the_subject_says_so():
    # without the origin an empty derived value reads the same whether the input was empty or the filter emptied it
    with pytest.raises(AssertionError) as exc_info:
        assert_that([{"n": 1}, {"n": 2}]).filtered_on(lambda item: False).is_not_empty()
    assert_that(str(exc_info.value)).contains("filtered_on() kept 0 of 2 items")


def test_a_filter_that_keeps_something_adds_no_note():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([{"n": 1}, {"n": 2}]).filtered_on(lambda item: item["n"] == 1).is_length(5)
    assert_that(str(exc_info.value)).does_not_contain("filtered_on() kept")


def test_extracting_that_empties_the_subject_says_so():
    with pytest.raises(AssertionError) as exc_info:
        assert_that([]).extracting("name").is_not_empty()
    assert_that(str(exc_info.value)).contains("extracting() produced 0 of 0 items")


def test_the_source_is_walked_as_it_comes():
    """Counting the source must not turn the walk into two phases.

    Draining it first to count it moved every predicate call after the whole producer had run, which
    changes the order side effects happen in and which failure a broken producer surfaces.
    """
    order = []

    def watched():
        for index in range(3):
            order.append(f"produced {index}")
            yield index

    assert_that(watched()).filtered_on(lambda n: order.append(f"tested {n}") or n > 1).is_length(1)
    assert_that(order).is_equal_to(["produced 0", "tested 0", "produced 1", "tested 1", "produced 2", "tested 2"])


def test_a_broken_producer_does_not_replace_the_extraction_failure():
    # the reader is owed the error about their data, not the one that came of reading ahead to count
    def hostile():
        yield {"name": "first"}
        raise RuntimeError("the producer broke on the second item")

    with pytest.raises(ValueError, match="did not contain key <missing>"):
        assert_that(hostile()).extracting("missing")


@pytest.mark.parametrize("source", [iter, lambda rows: (row for row in rows)], ids=["iterator", "generator"])
def test_a_one_shot_source_is_still_counted(source):
    """The note exists to say the source had items and the step emptied it.

    Counted from a second pass over the value, it said the opposite: a generator is spent by the pass
    that filters it, so the source read as empty and the reader was pointed at the wrong cause.
    """
    rows = [{"n": 1}, {"n": 2}, {"n": 3}]
    with pytest.raises(AssertionError) as exc_info:
        assert_that(source(rows)).filtered_on(lambda item: False).is_not_empty()
    assert_that(str(exc_info.value)).contains("filtered_on() kept 0 of 3 items")

    with pytest.raises(AssertionError) as exc_info:
        assert_that(source(rows)).extracting("n", filter=lambda item: False).is_not_empty()
    assert_that(str(exc_info.value)).contains("extracting() produced 0 of 3 items")


def _navigations():
    """The four hops that hand back a new builder, each of which must carry the context forward."""
    return {
        "first": lambda builder: builder.first(),
        "element": lambda builder: builder.element(0),
        "flat_mapped": lambda builder: builder.flat_mapped(lambda item: [item]),
        "filtered_on": lambda builder: builder.filtered_on(lambda item: True),
    }


class TestNavigationKeepsTheBuilderContext:
    """`first()`, `element()`, `flat_mapped()` and `filtered_on()` hand back a new builder, and each
    has to carry the description, the kind and the logger forward.  Every test of them asserted on the
    navigated value only, so a navigation could quietly drop a `described_as()` prefix, or turn a
    warn-mode chain back into a raising one, without anything noticing.
    """

    @pytest.mark.parametrize("name", list(_navigations()))
    def test_the_description_survives_the_hop(self, name):
        navigate = _navigations()[name]
        with pytest.raises(AssertionError) as exc_info:
            navigate(assert_that([1]).described_as("my context")).is_equal_to(object())
        assert_that(str(exc_info.value)).starts_with("[my context]")

    @pytest.mark.parametrize("name", list(_navigations()))
    def test_warn_mode_survives_the_hop(self, name, caplog):
        # the kind is what decides raise-versus-warn: losing it turns a warning back into a failure
        navigate = _navigations()[name]
        navigate(assert_warn([1])).is_equal_to(object())
        assert_that(caplog.text).contains("to be equal to")


class TestSizeValidatorBoundaries:
    """Zero is a legal size everywhere.  Rejecting it would be indistinguishable from rejecting a
    negative one on any test that only ever passes a positive number."""

    def test_greater_than_zero_is_a_legal_bound(self):
        assert_that([1]).has_size_greater_than(0)

    def test_a_negative_bound_is_refused(self):
        with pytest.raises(ValueError, match="must be a positive int"):
            assert_that([1]).has_size_greater_than(-1)

    def test_between_zero_and_zero_is_a_legal_range(self):
        assert_that([]).has_size_between(0, 0)

    def test_a_negative_high_bound_is_refused(self):
        with pytest.raises(ValueError, match="must be positive ints"):
            assert_that([1]).has_size_between(0, -1)

    def test_the_last_index_is_addressable(self):
        assert_that([1, 2, 3]).element(2).is_equal_to(3)

    def test_one_past_the_end_is_refused_by_our_own_message(self):
        # a slack bound leaves a bare IndexError, which names neither the index nor the range
        with pytest.raises(IndexError, match=r"Expected index 3 to be in range \[0, 3\)"):
            assert_that([1, 2, 3]).element(3)

    @pytest.mark.parametrize("name", list(_navigations()))
    def test_a_custom_logger_survives_the_hop(self, name, caplog):
        # warn mode routes through the caller's logger; losing it on any hop warns where nobody is watching
        navigate = _navigations()[name]
        custom = logging.getLogger("assertpy.test.custom")
        navigate(assert_warn([1], logger=custom)).is_equal_to(object())
        assert_that([record.name for record in caplog.records]).contains("assertpy.test.custom")
