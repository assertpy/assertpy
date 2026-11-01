# CodSpeed regression gate: micro-benchmarks of assertpy's hot paths, measured commit-over-commit under
# CPU simulation.  Run with `uv run --group benchmark pytest benchmarks/ --codspeed --no-cov`, which is
# what the CI job runs.  Not collected by the default suite, so machine noise never gates.
#
# The local "Time (best)" column is not a measurement: 95 us of wall clock was reported as 85 ns and two
# cases came out in the wrong order.  Read `Run time / Iters` instead.
from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from assertpy import assert_that, match
from assertpy._clustering import clusters, observations_of, render
from assertpy._hints import diagnose
from assertpy.errors import AssertionFailure


def _records(count: int) -> list[dict]:
    return [
        {
            "id": i,
            "name": f"user-{i}",
            "active": i % 2 == 0,
            "roles": ["admin", "user"] if i % 3 == 0 else ["user"],
            "profile": {"age": 20 + (i % 50), "city": f"city-{i % 20}", "score": i * 1.5},
        }
        for i in range(count)
    ]


@dataclass
class _Row:
    id: int
    name: str
    tags: list[str]


_SPEC = {"id": match.is_instance_of(int), "name": match.is_non_empty_string(), "active": match.is_instance_of(bool)}


def test_is_equal_to_nested_pass(benchmark):
    left, right = _records(200), _records(200)
    benchmark(lambda: assert_that(left).is_equal_to(right))


def test_is_equal_to_nested_diff(benchmark):
    left, right = _records(200), _records(200)
    right[199]["profile"]["city"] = "changed"

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_matches_structure_with_matchers(benchmark):
    records = _records(200)

    def run():
        for record in records:
            assert_that(record).matches_structure(_SPEC)

    benchmark(run)


def test_dataclass_diff(benchmark):
    left = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right = [_Row(i, f"n{i}", ["a", "b"]) for i in range(200)]
    right[199].tags = ["a", "c"]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_contains_exactly_large(benchmark):
    items = list(range(300))
    benchmark(lambda: assert_that(items).contains_exactly(*items))


def test_string_diff_with_carets(benchmark):
    # difflib.ndiff costs ~175x a plain pair of prints; str() has to be called or the carets never run
    left = "the quick brown fox jumps over the lazy dog " * 3
    right = left.replace("brown", "brawn", 1)

    def run():
        try:
            assert_that(left).is_equal_to(right)
        except AssertionFailure as failure:
            return str(failure)
        return None

    benchmark(run)


def test_wide_dict_diff(benchmark):
    left = {f"k{i}": i for i in range(200)}
    right = {f"k{i}": -i for i in range(200)}

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_extracting_large(benchmark):
    records = _records(300)
    benchmark(lambda: assert_that(records).extracting("id", "name").is_not_empty())


def test_contains_only_large(benchmark):
    items = list(range(300))
    benchmark(lambda: assert_that(items).contains_only(*items))


def test_shifted_list_diff(benchmark):
    # one element inserted at the head, which positional pairing reports as a difference at every later index
    left, right = list(range(500)), list(range(1, 500))

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_shifted_records_diff(benchmark):
    # the same shift over unhashable elements: alignment keys on reprs, and rendering 500 dict reprs is the price
    left = _records(500)
    right = _records(500)[1:]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_unshifted_list_diff(benchmark):
    # the alignment loses: no common run exists, so the opcodes are computed and thrown away
    left = [value * 2 for value in range(500)]
    right = [value * 2 + 1 for value in range(500)]

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_long_records_one_field_diff(benchmark):
    # the common QA failure: index pairing already yields the one entry, so this must not pay for difflib
    left = _records(200)
    right = _records(200)
    right[199]["profile"]["city"] = "changed"

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


def test_over_cap_list_diff(benchmark):
    # past `_ALIGN_MAX_ELEMENTS` the alignment is skipped, keeping a quadratic search off a large failure
    left, right = list(range(2000)), list(range(1, 2000))

    def run():
        with contextlib.suppress(AssertionFailure):
            assert_that(left).is_equal_to(right)

    benchmark(run)


# Everything above measures how the library walks a payload.  These measure the fixed price of one
# assertion, which is what most suites pay: thousands of them where nothing is walked.  A regression in
# `assert_that()`, in the soft-mode ContextVar read or in per-link chaining moves nothing above and
# everything in a real run.  One assertion is too small to time, so each case repeats a fixed count.
_ASSERTIONS = 1000


def test_builder_construction(benchmark):
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index)

    benchmark(run)


def test_scalar_equality_pass(benchmark):
    def run():
        for index in range(_ASSERTIONS):
            assert_that(index).is_equal_to(index)

    benchmark(run)


def test_short_chain_pass(benchmark):
    def run():
        for _ in range(_ASSERTIONS):
            assert_that("user-42").is_not_none().is_instance_of(str).starts_with("user").is_length(7)

    benchmark(run)


# The membership relations used to cost `len(a) * len(b)` comparisons, so a collection of a few thousand
# elements spent the whole assertion inside `in`.  Two sizes rather than one: the pair is what shows the
# shape, since a quadratic path grows 400x between them where a linear one grows 20x.
@pytest.mark.parametrize("size", [100, 2000])
def test_contains_only_pass(benchmark, size):
    values = list(range(size))
    items = tuple(range(size))
    benchmark(lambda: assert_that(values).contains_only(*items))


@pytest.mark.parametrize("size", [100, 2000])
def test_matcher_is_subset_of_pass(benchmark, size):
    values = list(range(size))
    superset = list(range(size + 1))
    benchmark(lambda: assert_that(values).satisfies(match.is_subset_of(superset)))


@pytest.mark.parametrize("size", [100, 2000])
def test_duplicates_reported(benchmark, size):
    # the failing side on purpose: naming the repeats is what used to count each element again. Swallowing
    # the failure would leave this green and timing a passing assertion if the duplicate stopped being found
    values = [*range(size), 0]

    def run():
        try:
            assert_that(values).does_not_contain_duplicates()
        except AssertionFailure:
            return
        raise RuntimeError("the duplicate was not reported, so this measures the wrong path")

    benchmark(run)


@pytest.mark.parametrize("size", [100, 2000])
def test_many_distinct_duplicates_reported(benchmark, size):
    # one repeat above hides a per-repeat re-walk; every element repeated is where it shows as a square
    values = [index for index in range(size) for _ in (0, 1)]

    def run():
        try:
            assert_that(values).does_not_contain_duplicates()
        except AssertionFailure:
            return
        raise RuntimeError("the duplicates were not reported, so this measures the wrong path")

    benchmark(run)


# Polling and clustering run per *poll* and per *failing test* rather than per assertion, so a loop nobody
# writes multiplies their cost.  The flight recorder is on by default and walks the probed value twice, once
# to sanitise a sample and once to key it for change: a failing poll over two hundred records measured 2.2 ms
# against 0.11 ms with it off.  Each case fixes the number of polls and checks it.
_POLLS = 10

_WIDE_FAIL, _WIDE_PASS = _records(200), _records(200)
_WIDE_FAIL[199]["profile"]["city"] = "changed"


def _replays(steps: int) -> int:
    """Link calls a chain of *steps* makes: each link polls once as it is added, then all are replayed."""
    links = steps - 1
    return sum(range(steps)) + (_POLLS + 1 - links) * links


def _polled(failing, settling, *, trace=True, steps=1):
    """A runnable poll, reporting the polls it spent and the link calls the replay made."""

    def run():
        seen = {"n": 0, "links": 0}

        def probe():
            seen["n"] += 1
            return settling if seen["n"] > _POLLS else failing

        def link(_):
            seen["links"] += 1
            return True

        builder = assert_that(probe).eventually_sync(timeout=3600, interval=0, trace=trace)
        for _ in range(steps - 1):
            builder = builder.satisfies(link)
        # the links count themselves, so a replay that skipped them cannot pass for one that ran
        builder.is_equal_to(settling)
        return seen["n"], seen["links"]

    return run


@pytest.mark.parametrize("trace", [True, False], ids=["recorder-on", "recorder-off"])
def test_polling_a_scalar(benchmark, trace):
    run = _polled(41, 42, trace=trace)
    assert run() == (_POLLS + 1, _replays(1))
    benchmark(run)


@pytest.mark.parametrize("trace", [True, False], ids=["recorder-on", "recorder-off"])
def test_polling_a_wide_value(benchmark, trace):
    # the same loop where the assertion also walks the payload, so the pair isolates the recorder: 95% of
    # a failing poll here against a quarter of one over the scalar above
    run = _polled(_WIDE_FAIL, _WIDE_PASS, trace=trace)
    assert run() == (_POLLS + 1, _replays(1))
    benchmark(run)


@pytest.mark.parametrize("steps", [1, 5], ids=["one-step", "five-steps"])
def test_polling_replays_the_whole_chain(benchmark, steps):
    run = _polled(41, 42, steps=steps)
    assert run() == (_POLLS + 1, _replays(steps))
    benchmark(run)


def _wide_failure(differing: int):
    left, right = _records(200), _records(200)
    for index in range(differing):
        right[index]["profile"]["city"] = "changed"
    with pytest.raises(AssertionFailure) as failure:
        assert_that(left).is_equal_to(right)
    return failure.value.diff


def test_clustering_a_failure(benchmark):
    diff = _wide_failure(50)
    assert len(diff.entries) == 50
    benchmark(lambda: observations_of(diff))


def _diff_of(left, right):
    """The structured diff of one failure, built outside the measurement."""
    with pytest.raises(AssertionFailure) as failure:
        assert_that(left).is_equal_to(right)
    return failure.value.diff


# The hint ladder runs on every failure and grows a rung at a time, so what this guards is the growth
# rather than today's number. Separable from the diff by construction: `diagnose()` takes one already
# built, so nothing here measures the walk twice.
#
# Three cases, and together they show the shape, because the cost is NOT the distance travelled.
# Measured over forty differing entries: a step that succeeds by parsing costs 39 us, running out over
# text costs 15 us across all nineteen askings, and over numbers 8 us, where no rung is asked at all.
# A step that declines does so on the type and leaves at once, so the ceiling is a rung that does real
# work, not the length of the search.
def test_hint_found_on_the_first_rung(benchmark):
    diff = _diff_of(
        {f"k{index}": '{"id": 1}' for index in range(40)},
        {f"k{index}": {"id": 1} for index in range(40)},
    )
    assert diagnose(diff) is not None
    benchmark(lambda: diagnose(diff))


def test_hint_the_ladder_runs_out(benchmark):
    diff = _diff_of({f"k{index}": index for index in range(40)}, {f"k{index}": -index for index in range(40)})
    assert diagnose(diff) is None
    benchmark(lambda: diagnose(diff))


def test_hint_the_ladder_runs_out_on_text(benchmark):
    left = {f"k{index}": f"a{index}" for index in range(40)}
    diff = _diff_of(left, {f"k{index}": f"b{index}" for index in range(40)})
    assert diagnose(diff) is None
    benchmark(lambda: diagnose(diff))


# 200 rather than the 40 this started at: at 40 it was the smallest case in the file, 14.8 us against its
# neighbour's 114, so a few instructions of drift read as a large percentage. The path is linear, 66 us at
# 200 against 5.5 ms of setup, and 200 is the size the polling cases above already use.
def test_clustering_a_whole_run(benchmark):
    recorded = [(f"test_{index}", observations_of(_wide_failure(1))) for index in range(200)]
    assert len(clusters(recorded, 200)) == 1
    benchmark(lambda: render(clusters(recorded, 200), 200))


# Everything above holds ints and strings, whose `==` and `hash()` are free, so the cost measured is the
# library's. These measure what the value costs instead: an expensive `__eq__`, a collection the hashing
# shortcut has to refuse, and an iterable that can be walked only once.


class _Costly:
    """A value whose `__eq__` is the expensive part, counted so a case can pin how often it was called.

    Two hundred of these: the passing path calls it once per element, the failing path 4.2 times, because
    composing the diff walks the pair again.
    """

    calls = 0
    hashes = 0

    def __init__(self, number: int) -> None:
        self.number = number

    def __eq__(self, other: object) -> bool:
        type(self).calls += 1
        return isinstance(other, _Costly) and self.number == other.number

    def __hash__(self) -> int:
        type(self).hashes += 1
        return hash(self.number)

    def __repr__(self) -> str:
        return f"_Costly({self.number})"


def test_expensive_equality_pass(benchmark):
    left = [_Costly(index) for index in range(200)]
    right = [_Costly(index) for index in range(200)]
    _Costly.calls = 0
    assert_that(left).is_equal_to(right)
    # one call per element, which is the floor: anything above means the passing path walks twice
    assert _Costly.calls == 200, f"the passing path called __eq__ {_Costly.calls} times, not 200"

    benchmark(lambda: assert_that(left).is_equal_to(right))


def test_expensive_equality_diff(benchmark):
    left = [_Costly(index) for index in range(200)]
    right = [_Costly(index) for index in range(200)]
    right[-1] = _Costly(-1)

    def run():
        try:
            assert_that(left).is_equal_to(right)
        except AssertionFailure:
            return
        raise RuntimeError("the arrays compared equal, so this measures the wrong path")

    run()
    benchmark(run)


@pytest.mark.parametrize(
    ("shape", "make"),
    [
        ("hashable", lambda size: [*range(size), 0]),
        ("unhashable", lambda size: [[index] for index in range(size)] + [[0]]),
        ("mixed", lambda size: [index if index % 2 else [index] for index in range(size)] + [1]),
    ],
    ids=["hashable", "unhashable", "mixed"],
)
def test_finding_duplicates_by_hashability(benchmark, shape, make):
    # `contains_duplicates` rather than its negation: the negation names every repeat, quadratic too for the
    # two unhashable shapes. 2001 elements through the check alone: 0.04 ms hashable, 10.9 mixed, 14.7
    # unhashable, against 0.18, 32 and 43 with the reporting attached
    values = make(2000)

    def run():
        assert_that(values).contains_duplicates()

    run()
    benchmark(run)


def test_a_class_with_its_own_equality_pays_the_quadratic_path(benchmark):
    """A hashable class is still walked pairwise when it defines `__eq__`, and that is on purpose.

    `_agrees` in `_engine/_membership.py` admits a type whose `__eq__` and `__hash__` both come from a
    known one, so a plain `class Money(int)` and a `StrEnum` are indexed.  This class defines both itself,
    which is where the two may disagree and a set would miss a duplicate.  2001 values: no hashes at all
    and 1 999 001 comparisons.
    """
    values = [_Costly(index) for index in range(2000)] + [_Costly(0)]
    _Costly.hashes = 0
    _Costly.calls = 0
    assert_that(values).contains_duplicates()
    assert _Costly.hashes == 0, f"the set path was taken after all, {_Costly.hashes} hashes"
    assert _Costly.calls > len(values), "the pairwise walk is what this case exists to time"

    benchmark(lambda: assert_that(values).contains_duplicates())


@pytest.mark.parametrize("walkable", [False, True], ids=["list", "single-use iterator"])
def test_a_single_use_iterable_is_read_once(benchmark, walkable):
    # an iterator is read whole in `materialized()`. Twenty thousand elements: 0.09 ms as a list against
    # 0.42 ms as an iterator for `contains`, so the cost is the materialisation and not the assertion
    size = 20000

    def run():
        values = (index for index in range(size)) if walkable else list(range(size))
        assert_that(values).contains(size - 1)

    benchmark(run)
