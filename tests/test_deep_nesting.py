"""Values nested deeper than a walk by recursion reaches, compared as deep as Python's own ``==`` compares them.

Walked by recursion, each level of a pair cost the walkers two or three Python calls, so a pair nested a third
as deep as the recursion limit raised `RecursionError` in place of its verdict, and each level copied the set
of the ids above it.  The depth here is past that third and short of the limit itself, which Python's own
``==`` spends on 3.10 and 3.11.
"""

import dataclasses
import sys
import tracemalloc
import types

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match
from assertpy._engine._diff import _walk_leaves, run_nested
from assertpy._engine._path import _ROOT, _Path
from assertpy.errors import Step, _safe_str

_DEEP = sys.getrecursionlimit() * 3 // 5
_ON_FLOATS = {float: lambda actual, expected: actual == expected}
_OPTIONS = [
    pytest.param({}, id="plain"),
    pytest.param({"tolerance": 0.1}, id="tolerance"),
    pytest.param({"comparators": _ON_FLOATS}, id="comparator"),
    pytest.param({"strict_types": True}, id="strict_types"),
]


def _nested_list(leaf, depth=_DEEP):
    value = leaf
    for _ in range(depth):
        value = [value, 0]
    return value


def _nested_dict(leaf, depth=_DEEP):
    value = leaf
    for _ in range(depth):
        value = {"k": value, "n": 0}
    return value


@dataclasses.dataclass
class Holder:
    held: object
    stamp: int = 0


def _found(call):
    """The differences a failure reports, as ``(path, actual, expected)``."""
    with pytest.raises(AssertionFailure) as caught:
        call()
    diff = caught.value.diff
    assert diff is not None
    return [(entry.path, entry.actual, entry.expected) for entry in diff.entries]


class TestTheDepthOfAPair:
    @pytest.mark.parametrize("options", _OPTIONS)
    def test_two_equal_lists_pass(self, options):
        assert_that(_nested_list(1.5)).is_equal_to(_nested_list(1.5), **options)

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_a_difference_at_the_bottom_of_a_list_is_named(self, options):
        found = _found(lambda: assert_that(_nested_list(1.5)).is_equal_to(_nested_list(2.5), **options))
        assert_that(found).is_equal_to([("[0]" * _DEEP, 1.5, 2.5)])

    @pytest.mark.parametrize("options", _OPTIONS)
    def test_two_equal_mappings_pass(self, options):
        assert_that(_nested_dict(1.5)).is_equal_to(_nested_dict(1.5), **options)

    @pytest.mark.parametrize("options", [*_OPTIONS, pytest.param({"ignore": "n"}, id="ignore")])
    def test_a_difference_at_the_bottom_of_a_mapping_is_named(self, options):
        found = _found(lambda: assert_that(_nested_dict(1.5)).is_equal_to(_nested_dict(2.5), **options))
        assert_that(found).is_equal_to([("k" + ".k" * (_DEEP - 1), 1.5, 2.5)])

    def test_a_field_filter_reaches_a_value_nested_under_a_field(self):
        # the fields are still taken apart by recursion, a frame a level: through a generator it was three on
        # Python 3.10 and two elsewhere, which this depth is past
        depth = sys.getrecursionlimit() * 3 // 5
        actual, expected = Holder(_nested_list(1.5, depth), 1), Holder(_nested_list(2.5, depth), 2)
        assert_that(actual).is_equal_to(Holder(_nested_list(1.5, depth), 2), ignore="stamp")
        found = _found(lambda: assert_that(actual).is_equal_to(expected, ignore="stamp"))
        assert_that(found).is_equal_to([("held" + "[0]" * depth, 1.5, 2.5)])

    def test_a_matcher_answers(self):
        assert_that(match.equal_to(_nested_dict(1.55), tolerance=0.1).matches(_nested_dict(1.5))).is_true()
        assert_that(match.equal_to(_nested_dict(2.5), tolerance=0.1).matches(_nested_dict(1.5))).is_false()

    def test_a_leaf_assertion_reaches_the_bottom(self):
        found = _found(lambda: assert_that(_nested_list(None)).has_no_none_fields())
        assert_that(found).extracting(0).is_equal_to(["[0]" * _DEEP])

    def test_memory_grows_with_the_depth_and_not_with_its_square(self):
        def peak(depth):
            actual, expected = _nested_list(1.5, depth), _nested_list(2.5, depth)
            tracemalloc.start()
            try:
                assert_that(actual).check().is_equal_to(expected, tolerance=0.1)
                return tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()

        # an eighth of the depth: a square grows 64 times, the recursive walk measured 41 to 57, this one 7 to 16
        assert_that(peak(_DEEP) / peak(_DEEP // 8)).is_less_than(24)


class TestAValueReachedTwiceIsNotACycle:
    """Only a value among its own ancestors is circular, so the walks hold the path and not everything seen."""

    def test_a_diff_walks_a_shared_value_each_time(self):
        shared = [1]
        found = _found(lambda: assert_that([shared, shared]).is_equal_to([[2], [2]]))
        assert_that(found).is_equal_to([("[0][0]", 1, 2), ("[1][0]", 1, 2)])

    def test_a_mapping_message_renders_a_shared_value_each_time(self):
        shared = {"v": 1}
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"a": shared, "b": shared}).is_equal_to({"a": {"v": 2}, "b": {"v": 2}})
        assert_that(str(caught.value)).does_not_contain("circular")

    def test_a_leaf_walk_visits_a_shared_value_each_time(self):
        shared = [None]
        leaves = [(path.text, leaf) for path, leaf in _walk_leaves({"a": shared, "b": shared})]
        assert_that(leaves).is_equal_to([("a[0]", None), ("b[0]", None)])

    def test_a_value_built_on_each_read_is_not_taken_for_an_ancestor(self):
        class Fresh(list):
            """A list that builds a new mapping around an element each time one is read."""

            def __getitem__(self, index):
                return types.MappingProxyType({"k": list.__getitem__(self, index)})

        found = _found(lambda: assert_that(Fresh([Fresh([1])])).is_equal_to(Fresh([Fresh([2])])))
        assert_that(found).is_equal_to([("[0].k[0].k", 1, 2)])

    def test_a_cycle_is_still_one(self):
        looped = [1]
        looped.append(looped)
        leaves = [(path.text, leaf) for path, leaf in _walk_leaves(looped)]
        assert_that(leaves).is_equal_to([("[0]", 1)])


class TestAnErrorLeavesNothingOpen:
    """An error deep in a walk closes what the levels above held open, as unwinding nested calls did."""

    def test_the_leaf_walk_closes_an_iterator_of_the_value(self):
        closed = []

        class Tracked(list):
            def __iter__(self):
                try:
                    yield from list.__iter__(self)
                finally:
                    closed.append("iterator")

        class Refusing(dict):
            def __getitem__(self, key):
                raise LookupError(key)

        with pytest.raises(LookupError) as caught:
            list(_walk_leaves(Tracked([Refusing(k=1)])))
        # the error is still held, and with it its traceback, which reached the walk's own frame
        assert_that(caught.value.__traceback__).is_not_none()
        assert_that(closed).is_equal_to(["iterator"])

    def test_a_nested_walk_closes_the_walks_above_it(self):
        closed = []

        def tracked():
            try:
                yield from (1, 2)
            finally:
                closed.append("iterator")

        def refusing():
            raise LookupError("inner")
            yield

        def outer():
            for _ in tracked():
                yield refusing()

        with pytest.raises(LookupError) as caught:
            run_nested(outer())
        assert_that(caught.value.__traceback__).is_not_none()
        assert_that(closed).is_equal_to(["iterator"])


class TestAPathReadsAsItWasWritten:
    """A path is joined when an entry is made, and reads as the per-hop f-strings wrote it."""

    def test_a_field_named_by_a_str_subclass_is_formatted_below_the_root(self):
        class Name(str):
            def __format__(self, spec):
                return "alias"

        assert_that(_Path("root").attr(Name("x"), dotted_at_root=False).text).is_equal_to("root.alias")
        assert_that(_ROOT.attr(Name("x"), dotted_at_root=False).text).is_equal_to("x")
        assert_that(_ROOT.attr(Name("x")).text).is_equal_to(".alias")

    def test_a_root_field_named_by_a_str_subclass_is_formatted_by_the_hop_after_it(self):
        class Name(str):
            def __format__(self, spec):
                return "alias"

        field = _ROOT.attr(Name("x"), dotted_at_root=False)
        assert_that(field.text).is_equal_to("x")
        assert_that(field.index(0).text).is_equal_to("alias[0]")
        assert_that(field.side_index("actual", 1).text).is_equal_to("aliasactual[1]")
        assert_that(field.key("k").text).is_equal_to("alias.k")
        assert_that(field.attr("f").text).is_equal_to("alias.f")
        assert_that(field.attr("f", dotted_at_root=False).text).is_equal_to("alias.f")

    def test_a_field_path_is_taken_before_the_field_is_read(self):
        @dataclasses.dataclass
        class Record:
            x: object = None

            def __getattribute__(self, name):
                value = object.__getattribute__(self, name)
                if name == "x":
                    dataclasses.fields(type(self))[0].name = "renamed"
                return value

        found = _found(lambda: assert_that(Record()).has_no_none_fields())
        assert_that(found).extracting(0).is_equal_to(["x"])

    def test_a_field_name_is_read_again_for_the_value_after_the_path(self):
        @dataclasses.dataclass
        class Record:
            x: object = None
            y: object = 1

        field = dataclasses.fields(Record)[0]

        class Name(str):
            def __format__(self, spec):
                field.name = "y"
                return "x"

        field.name = Name("x")
        assert_that({"record": Record()}).has_no_none_fields()

    def test_the_dot_is_decided_by_the_text_before_it_is_formatted(self):
        class Name(str):
            def __format__(self, spec):
                return ""

        @dataclasses.dataclass
        class Record:
            x: object

        dataclasses.fields(Record)[0].name = Name("x")
        found = _found(lambda: assert_that(Record({"k": None})).has_no_none_fields())
        assert_that(found).extracting(0).is_equal_to([".k"])


_ASKED: list[tuple[str, str]] = []


class _Name(str):
    """A name answering ``__format__`` and ``__bool__`` its own way, and noting each time it is asked."""

    def __new__(cls, value: str, formatted: str, truthy: bool):
        made = super().__new__(cls, value)
        made.formatted, made.truthy = formatted, truthy
        return made

    def __format__(self, spec):
        _ASKED.append(("format", str.__str__(self)))
        return self.formatted

    def __bool__(self):
        _ASKED.append(("bool", str.__str__(self)))
        return self.truthy


class _Written:
    """2.28.0's path as it wrote its text, hop by hop, copied from its rules: the oracle for the joined one."""

    def __init__(self, text="", steps=()):
        self.text, self.steps = text, steps

    def key(self, key):
        rendered = _safe_str(key)
        return _Written(f"{self.text}.{rendered}" if self.text else rendered, (*self.steps, Step("key", key)))

    def attr(self, name, *, dotted_at_root=True):
        text = f"{self.text}.{name}" if self.text or dotted_at_root else name
        return _Written(text, (*self.steps, Step("attr", name)))

    def index(self, index):
        return _Written(f"{self.text}[{index}]", (*self.steps, Step("index", index)))

    def side_index(self, side, index):
        return _Written(f"{self.text}{side}[{index}]", (*self.steps, Step("index", index, side=side)))

    def line(self, number):
        return _Written(f"line {number}", (*self.steps, Step("line", number)))

    def member(self, item, label):
        return _Written(label, (*self.steps, Step("item", item)))


_NAMES = st.one_of(
    st.sampled_from(["", "a", "b.c"]),
    st.builds(_Name, st.sampled_from(["", "x"]), st.sampled_from(["", "alias"]), st.booleans()),
)
_HOPS = st.one_of(
    st.tuples(st.just("key"), st.sampled_from(["", "k", 3])),
    st.tuples(st.just("attr"), _NAMES, st.booleans()),
    st.tuples(st.just("index"), st.integers(0, 2)),
    st.tuples(st.just("side_index"), st.sampled_from(["actual", "expected"]), st.integers(0, 2)),
    st.tuples(st.just("line"), st.integers(1, 2)),
    st.tuples(st.just("member"), st.just(1), st.sampled_from(["extra", "missing"])),
)


def _taken(path, hop):
    kind, *arguments = hop
    if kind == "attr":
        return path.attr(arguments[0], dotted_at_root=arguments[1])
    return getattr(path, kind)(*arguments)


def _walked(start, hops):
    """Each location along *hops* with its text and steps, and what the names were asked on the way."""
    _ASKED.clear()
    path, seen = start, []
    for hop in hops:
        path = _taken(path, hop)
        seen.append((path.text, type(path.text), path.steps if isinstance(path, _Written) else path.entry().steps))
    return seen, list(_ASKED)


class TestTheJoinedPathAgreesWithTheWrittenOne:
    @settings(deadline=None, max_examples=400)
    @given(st.lists(_HOPS, max_size=5))
    @example([("attr", _Name("x", "alias", True), False), ("index", 0)])
    @example([("attr", _Name("x", "", True), False), ("key", "k")])
    @example([("attr", _Name("x", "x", False), False), ("key", "k")])
    def test_every_text_step_and_question_is_the_old_one(self, hops):
        assert_that(_walked(_ROOT, hops)).is_equal_to(_walked(_Written(), hops))


def _raises_stop():
    raise StopIteration("the value's own")


def _stops_inside_its_own_generator():
    def generator():
        _raises_stop()
        yield

    next(generator())


class TestTheValuesOwnStopIterationGetsOut:
    """A `StopIteration` from the value's code leaves as it did when the walks were calls, not as `RuntimeError`."""

    @pytest.mark.parametrize(
        ("raising", "expected"),
        [(_raises_stop, StopIteration), (_stops_inside_its_own_generator, RuntimeError)],
        ids=["its-own", "from-its-own-generator"],
    )
    def test_from_a_field_read_by_the_diff(self, raising, expected):
        @dataclasses.dataclass(eq=False, repr=False)
        class Record:
            x: int = 0

            def __getattribute__(self, name):
                if name == "x":
                    raising()
                return object.__getattribute__(self, name)

        with pytest.raises(expected, match=r"value's own|generator raised StopIteration"):
            assert_that(Record()).is_equal_to(Record())

    @pytest.mark.parametrize(
        ("raising", "expected"),
        [(_raises_stop, StopIteration), (_stops_inside_its_own_generator, RuntimeError)],
        ids=["its-own", "from-its-own-generator"],
    )
    def test_from_an_equality_asked_by_the_mapping_verdict(self, raising, expected):
        class Asked:
            def __eq__(self, other):
                raising()

            __hash__ = object.__hash__

        with pytest.raises(expected, match=r"value's own|generator raised StopIteration"):
            assert_that({"a": Asked()}).is_equal_to({"a": 1}, tolerance=0.1)

    @pytest.mark.parametrize(
        ("raising", "expected"),
        [(_raises_stop, StopIteration), (_stops_inside_its_own_generator, RuntimeError)],
        ids=["its-own", "from-its-own-generator"],
    )
    def test_from_a_nested_walk(self, raising, expected):
        def inner():
            raising()
            yield

        def outer():
            yield inner()

        with pytest.raises(expected, match=r"value's own|generator raised StopIteration"):
            run_nested(outer())

    def test_from_a_field_container_rebuilt_under_a_filter_it_stays_as_it_was(self):
        class Refusing(list):
            def __init__(self, items=()):
                raise StopIteration("constructor")

        value = list.__new__(Refusing)
        list.__init__(value, [1])

        @dataclasses.dataclass
        class Record:
            items: object
            stamp: int

        with pytest.raises(RuntimeError, match="generator raised StopIteration"):
            assert_that(Record([value], 1)).is_equal_to(Record([value], 2), ignore="stamp")

    def test_from_a_comparator_asked_about_an_aligned_pair(self):
        def stop(actual, expected):
            raise StopIteration("the value's own")

        actual = [*range(100), 0.5]
        expected = [-1, *actual]
        with pytest.raises(StopIteration, match="value's own"):
            assert_that(actual).is_equal_to(expected, comparators={float: stop})
