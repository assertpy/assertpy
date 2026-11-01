"""A value that hands its items out once is read alike by every link of a chain.

A generator, an iterator, a `zip` or a `map` was read by the first assertion that walked it, and the next one
passed or failed over nothing: ``assert_that(iter([1, 2, 3])).contains(1).does_not_contain(1)`` passed.  The builder
now keeps what such a value has handed out, and every walk starts at the first item.  The value itself stays
where it was, so `val`, `value` and an assertion about what the value is read the caller's own iterator.
"""

from __future__ import annotations

import ast
import collections.abc
import importlib.util
import itertools
import pathlib
from typing import Any

import pytest

import assertpy
from assertpy import AssertionFailure, BaseMatcher, assert_that, match, soft_assertions
from assertpy._engine._introspection import Replay
from assertpy.assertpy import AssertionBuilder


class _Counting:
    """Its own iterator over a few items, counting how many it has handed out."""

    def __init__(self, items: tuple[int, ...] = (1, 2, 3)) -> None:
        self.left = list(items)
        self.taken = 0

    def __iter__(self) -> _Counting:
        return self

    def __next__(self) -> int:
        if not self.left:
            raise StopIteration
        self.taken += 1
        return self.left.pop(0)


def _answer(ask) -> tuple[str, object]:
    """How a call came out: what it handed back, the failure it raised, or the class of what it refused with."""
    try:
        result = ask()
    except AssertionFailure as failure:
        return "failed", str(failure)
    except Exception as refusal:
        return "refused", type(refusal).__name__
    held = getattr(result, "val", result)
    return "held", None if isinstance(held, _Counting) else held


_SOURCES = {
    "iterator": lambda: iter([1, 2, 3]),
    "generator": lambda: (item for item in [1, 2, 3]),
    "map": lambda: map(int, [1, 2, 3]),
    "filter": lambda: filter(None, [1, 2, 3]),
    "chain": lambda: itertools.chain([1], [2, 3]),
}
_CHAINS = {
    "contains-then-not": lambda chain: chain.contains(1).does_not_contain(1),
    "contains-twice": lambda chain: chain.contains(1).contains(3),
    "not-then-not": lambda chain: chain.does_not_contain(9).does_not_contain(1),
    "contains-then-all": lambda chain: chain.contains(2).all_satisfy(lambda item: item < 0),
    "contains-then-each": lambda chain: chain.contains(2).each(match.greater_than(0)),
    "sorted-then-none": lambda chain: chain.is_sorted().none_satisfy(lambda item: item == 1),
    "contains-then-sorted": lambda chain: chain.contains(3).is_sorted(reverse=True),
    "exactly-then-only": lambda chain: chain.contains_exactly(1, 2, 3).contains_only(1, 2, 3),
    "starts-then-ends": lambda chain: chain.starts_with(1).ends_with(3),
    "ends-then-starts": lambda chain: chain.ends_with(3).starts_with(1),
    "sequence-then-order": lambda chain: chain.contains_sequence(2, 3).contains_in_order(1, 3),
    "duplicates-then-subset": lambda chain: chain.does_not_contain_duplicates().is_subset_of([1, 2, 3, 4]),
    "matcher-then-contains": lambda chain: chain.satisfies(match.contains(1)).contains(9),
    "exactly-in-any-order": lambda chain: chain.contains(1).contains_exactly_in_any_order(3, 2, 1),
    "any-then-satisfies-exactly": lambda chain: chain.any_satisfy(lambda item: item == 2).satisfies_exactly(
        match.equal_to(1), match.equal_to(2), match.equal_to(3)
    ),
    "zip-satisfies-twice": lambda chain: chain.zip_satisfies([1, 2, 3], lambda one, other: one == other).contains(3),
}


class TestEveryLinkReadsWhatTheFirstRead:
    @pytest.mark.parametrize("source", list(_SOURCES))
    @pytest.mark.parametrize("chain", list(_CHAINS))
    def test_a_chain_answers_as_it_does_over_a_list(self, source, chain):
        over_a_list = _answer(lambda: _CHAINS[chain](assert_that([1, 2, 3])))
        answered = _answer(lambda: _CHAINS[chain](assert_that(_SOURCES[source]())))
        assert_that(answered[0]).is_equal_to(over_a_list[0])

    def test_the_chain_that_passed_over_nothing_fails(self):
        assert_that(lambda: assert_that(iter([1, 2, 3])).contains(1).does_not_contain(1)).raises(
            AssertionFailure
        ).when_called_with().contains("to not contain item <1>")

    def test_a_pivot_reads_the_same_items_as_the_link_after_it(self):
        chain = assert_that(iter([3, 1, 2]))
        pivots = [
            lambda: chain.first(),
            lambda: chain.last(),
            lambda: chain.element(1),
            lambda: chain.mapped(lambda item: item * 2),
            lambda: chain.flat_mapped(lambda item: [item, item]),
            lambda: chain.filtered_on(lambda item: item > 1),
            lambda: chain.extracting("real"),
            lambda: chain.extracting("real", sort=lambda item: item),
            lambda: chain.contains_exactly(3, 1, 2).first(),
        ]
        assert_that([_answer(pivot) for pivot in pivots]).is_equal_to(
            [
                ("held", 3),
                ("held", 2),
                ("held", 1),
                ("held", [6, 2, 4]),
                ("held", [3, 3, 1, 1, 2, 2]),
                ("held", [3, 2]),
                ("held", [3, 1, 2]),
                ("held", [1, 2, 3]),
                ("held", 3),
            ]
        )

    def test_a_function_that_hands_back_the_value_itself_reads_it_as_the_links_do(self):
        source = iter([1, 2, 3])
        chain = assert_that(source)
        answers = [
            _answer(lambda: chain.flat_mapped(lambda _: source)),
            _answer(lambda: chain.contains_exactly(1, 2, 3).first()),
            _answer(lambda: chain.contains_exactly(1))[0],
        ]
        over_a_list = _answer(lambda: assert_that([1, 2, 3]).flat_mapped(lambda _: [1, 2, 3]))
        assert_that(answers).is_equal_to([over_a_list, ("held", 1), "failed"])

    def test_a_soft_block_goes_on_over_the_same_items(self):
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(iter([1, 2, 3])).contains(9).contains(1).does_not_contain(1)
        said = str(caught.value)
        assert_that(said).contains("to contain item <9>").contains("to not contain item <1>")
        assert_that(said).does_not_contain("to contain item <1>, but did not")

    def test_each_attempt_of_a_poll_reads_its_own_value_whole(self):
        assert_that(lambda: iter([1, 2, 3])).eventually_sync(timeout=0.5, interval=0.01).contains(1).contains(3)
        assert_that(
            lambda: (
                assert_that(lambda: iter([1, 2, 3]))
                .eventually_sync(timeout=0.05, interval=0.01)
                .contains(1)
                .does_not_contain(1)
            )
        ).raises(AssertionFailure).when_called_with()


_ARGUMENTS: list[tuple[Any, ...]] = [
    (),
    (1,),
    (1, 2),
    (1, 2, 3),
    ([1, 2, 3],),
    ([1, 2, 3], lambda one, other: one == other),
    (lambda item: True,),
    (lambda item: item,),
    (lambda item: [item, item],),
    ("real",),
    (lambda one, two, three: True,),
    (match.greater_than(0),),
    (match.contains(1),),
    (match.is_not_none() & (match.is_instance_of(list) | match.contains(9)),),
    (match.equal_to(1), match.equal_to(2), match.equal_to(3)),
    (int,),
    ("a",),
    (3,),
    (0,),
]
_NOT_ASKED = frozenset(
    {
        # a poll, or an expectation another call tests: none of them reads the value handed to the builder
        "eventually",
        "eventually_sync",
        "raises",
        "does_not_raise",
        "when_called_with",
        "warns",
        "does_not_warn",
    }
)
_NAMES = sorted(
    name
    for name in dir(AssertionBuilder)
    if not name.startswith("_") and name not in _NOT_ASKED and callable(getattr(AssertionBuilder, name, None))
)


_KEYWORDS: list[dict[str, Any]] = [
    {},
    {"reverse": True},
    {"key": lambda item: -item},
    {"sort": lambda item: -item},
    {"filter": lambda item: item > 1},
    {"allow_empty": True},
    {"key": lambda item: -item, "reverse": True},
    {"sort": lambda item: -item, "filter": lambda item: item > 1},
]
"""The keywords of the assertions that walk, alone and together: a branch only they reach is a reading site too."""


def _asked_twice(
    name: str, arguments: tuple[Any, ...], keywords: dict[str, Any], items: tuple[int, ...]
) -> tuple[int, tuple[str, object], tuple[str, object]]:
    value = _Counting(items)
    chain = assert_that(value)
    first = _answer(lambda: getattr(chain, name)(*arguments, **keywords))
    second = _answer(lambda: getattr(chain, name)(*arguments, **keywords))
    return value.taken, first, second


class TestNoAssertionReadsBesideTheBuilder:
    """The gate: an assertion that takes an item of a one-shot value answers the same when asked again.

    A reading site added without going through the builder reads the iterator itself, the second call then
    walks nothing, and the two answers part.  Asked of every public assertion with every argument shape here.
    """

    def test_every_assertion_that_reads_answers_alike_when_asked_twice(self):
        read, parted, through_equality = set(), [], set()
        # the second run of items holds one twice, which the assertions about duplicates tell from a run of none
        shapes = itertools.product(_NAMES, _ARGUMENTS, _KEYWORDS, [(1, 2, 3), (1, 1, 2)])
        for name, arguments, keywords, items in shapes:
            taken, first, second = _asked_twice(name, arguments, keywords, items)
            if not taken:
                continue
            if name in _HANDED_BY_EQUALITY and any(isinstance(one, BaseMatcher) for one in arguments):
                if second != first:
                    through_equality.add(name)
                continue
            read.add(name)
            if second != first:
                parted.append(f"{name}{arguments!r} {sorted(keywords)} over {items}: {first} then {second}")
        assert_that(parted).described_as("answered otherwise the second time").is_empty()
        assert_that(sorted(read)).described_as("the assertions that read a one-shot value").is_equal_to(_READERS)
        # numpy is absent from a reduced cell, and `is_array_equal` refuses there before it reads anything
        handed = _HANDED_BY_EQUALITY if importlib.util.find_spec("numpy") else _HANDED_BY_EQUALITY - {"is_array_equal"}
        assert_that(through_equality).described_as("a matcher reading items handed the value by `==`").is_equal_to(
            handed
        )


_HANDED_BY_EQUALITY = frozenset(
    {"all_fields_satisfy", "is_array_equal", "is_equal_to", "is_in", "is_not_equal_to", "is_not_in", "matches_inline"}
)
"""Where a matcher is an operand the value is compared with, it is handed the value as ``==`` hands it.

Equality, membership among candidates, a field walk and numpy each ask ``matcher == value``, and a matcher that
reads items takes them from the iterator itself, beside the chain.  Named so it cannot grow unseen.
"""


_READERS = sorted(
    [
        "all_satisfy",
        "any_satisfy",
        "contains",
        "contains_duplicates",
        "contains_exactly",
        "contains_exactly_in_any_order",
        "contains_ignoring_case",
        "contains_in_order",
        "contains_only",
        "contains_only_once",
        "contains_sequence",
        "does_not_contain",
        "does_not_contain_duplicates",
        "each",
        "element",
        "ends_with",
        "extracting",
        "filtered_on",
        "first",
        "flat_mapped",
        "is_sorted",
        "is_subset_of",
        "last",
        "mapped",
        "none_satisfy",
        "satisfies",
        "satisfies_exactly",
        "satisfies_exactly_in_any_order",
        "single",
        "starts_with",
        "zip_satisfies",
    ]
)
"""Every assertion that takes an item of a one-shot value, named: one that starts to has to be listed, and held."""


def _val_of_self(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "val"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def _walked_in_place(tree: ast.Module) -> set[tuple[str, str]]:
    """`(the function, how)` for every place a module walks ``self.val`` itself.

    A loop or a comprehension over it, a builtin that reads handed it, `in` against it, a star, a ``yield from``,
    and an assignment that takes it apart.
    """
    found = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if isinstance(node, (ast.For, ast.comprehension)) and _val_of_self(node.iter):
                found.add((function.name, "loop"))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _READS:
                if any(_val_of_self(argument) for argument in node.args):
                    found.add((function.name, node.func.id))
            elif isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                if any(_val_of_self(right) for right in node.comparators):
                    found.add((function.name, "in"))
            elif isinstance(node, (ast.Starred, ast.YieldFrom)) and _val_of_self(node.value):
                found.add((function.name, "unpacked"))
            elif isinstance(node, ast.Assign) and _val_of_self(node.value):
                if any(isinstance(target, (ast.Tuple, ast.List)) for target in node.targets):
                    found.add((function.name, "unpacked"))
    return found


_READS = frozenset(
    {
        "all",
        "any",
        "dict",
        "enumerate",
        "filter",
        "frozenset",
        "iter",
        "list",
        "map",
        "materialized",
        "max",
        "min",
        "next",
        "reversed",
        "searchable",
        "set",
        "sorted",
        "sum",
        "tuple",
        "zip",
    }
)
_READ_IN_PLACE: dict[tuple[str, str, str], str] = {
    ("collection.py", "is_subset_of", "loop"): "a mapping, asked on the line above it",
    ("dict.py", "contains_entry", "in"): "a mapping, which the assertion requires",
    ("dict.py", "does_not_contain_entry", "in"): "a mapping, which the assertion requires",
    ("dynamic.py", "__getattr__", "in"): "a mapping, asked on the line above it",
    ("snapshot.py", "_check_placeholders", "in"): "a mapping, which placeholders require",
    ("snapshot.py", "_with_placeholder_tokens", "dict"): "a mapping, which placeholders require",
    ("string.py", "contains_any_of", "in"): "a text, which the assertion requires",
    ("string.py", "contains_none_of", "in"): "a text, which the assertion requires",
}
"""Where an assertion still walks the value itself, each with why that value is never a one-shot one."""


def test_no_assertion_walks_the_value_itself_but_the_ones_named():
    """The other half of the gate: read off the source, so a branch no argument shape reaches is seen too.

    A walk through a name the value was bound to first is beyond it, and is the first half's to catch.
    """
    package = pathlib.Path(assertpy.__file__).parent
    modules = sorted(package.rglob("*.py"))
    assert_that([module.name for module in modules]).contains("_mixin_base.py", "contains.py")
    found = {
        (module.name, function, how)
        for module in modules
        for function, how in _walked_in_place(ast.parse(module.read_text(encoding="utf-8")))
    }
    assert_that(sorted(found)).is_equal_to(sorted(_READ_IN_PLACE))


@pytest.mark.parametrize(
    ("body", "how"),
    [
        ("for item in self.val: pass", "loop"),
        ("return [item for item in self.val]", "loop"),
        ("return list(self.val)", "list"),
        ("return sorted(self.val, key=len)", "sorted"),
        ("return 1 in self.val", "in"),
        ("return 1 not in self.val", "in"),
        ("return [*self.val]", "unpacked"),
        ("yield from self.val", "unpacked"),
        ("first, second = self.val", "unpacked"),
        ("[first, second] = self.val", "unpacked"),
    ],
)
def test_the_reading_of_the_source_sees_each_form_it_names(body, how):
    tree = ast.parse(f"class Mixin:\n    def walks(self):\n        {body}\n")
    assert_that(_walked_in_place(tree)).is_equal_to({("walks", how)})


def test_what_is_no_walk_is_not_taken_for_one():
    tree = ast.parse("class Mixin:\n    def asks(self):\n        held = self.val\n        return len(self.val), held\n")
    assert_that(_walked_in_place(tree)).is_empty()


class TestTheValueStaysTheCallersOwn:
    def test_val_and_value_are_the_iterator_handed_in(self):
        source = iter([1, 2, 3])
        chain = assert_that(source).contains(1).contains(3)
        assert_that(chain.val).is_same_as(source)
        assert_that(chain.value).is_same_as(source)
        chain.is_same_as(source).is_instance_of(collections.abc.Iterator)

    def test_a_value_read_more_than_once_already_is_handed_to_a_walk_as_it_is(self):
        for held in ([1, 2], (1, 2), "ab", {"a": 1}, {1, 2}, range(3), collections.deque([1])):
            assert_that(assert_that(held)._walked()).is_same_as(held)
            assert_that(assert_that(held)._drained()).is_same_as(held)
        assert_that(assert_that(5)._walked()).is_equal_to(5)

    def test_a_one_shot_value_is_drained_into_one_list_for_every_link(self):
        chain = assert_that(iter([1, 2, 3]))
        assert_that(chain._drained()).is_equal_to([1, 2, 3])
        assert_that(chain._drained()).is_equal_to([1, 2, 3])
        assert_that(type(chain._walked())).is_same_as(Replay)

    def test_another_value_put_on_the_builder_is_read_afresh(self):
        chain = assert_that(iter([1, 2, 3])).contains(1)
        chain.val = iter([7, 8])
        chain.contains(7).does_not_contain(1).contains(8)


class TestAWalkTakesNoMoreThanItDid:
    def test_an_endless_generator_is_read_as_far_as_the_verdict_needs(self):
        chain = assert_that(itertools.count())
        chain.starts_with(0).starts_with(0)
        said = assert_that(lambda: chain.each(match.less_than(3))).raises(AssertionFailure).when_called_with().value
        assert_that(said).contains("item at index 3 <3>")
        assert_that(lambda: chain.none_satisfy(lambda item: item == 5)).raises(AssertionFailure).when_called_with()
        chain.starts_with(0)

    def test_two_walks_at_once_each_start_at_the_first_item(self):
        read = Replay(iter([1, 2, 3]))
        one, other = iter(read), iter(read)
        assert_that([next(one), next(other), next(other), next(one), next(one), next(other)]).is_equal_to(
            [1, 1, 2, 2, 3, 3]
        )
        assert_that([list(read), list(read)]).is_equal_to([[1, 2, 3], [1, 2, 3]])
        assert_that(list(one)).is_empty()

    def test_a_generator_that_raised_is_at_its_end_and_what_it_handed_out_is_kept(self):
        def broken():
            yield 1
            raise ValueError("no more")

        chain = assert_that(broken())
        assert_that(_answer(lambda: chain.contains(9))).is_equal_to(("refused", "ValueError"))
        assert_that(_answer(lambda: chain.contains_exactly(1).first())).is_equal_to(("held", 1))

    def test_an_iterator_that_raises_once_and_goes_on_is_read_on(self):
        class Stumbling:
            def __init__(self) -> None:
                self.left = [1, ValueError("once"), 2]

            def __iter__(self) -> Stumbling:
                return self

            def __next__(self) -> int:
                if not self.left:
                    raise StopIteration
                taken = self.left.pop(0)
                if isinstance(taken, ValueError):
                    raise taken
                return taken

        chain = assert_that(Stumbling())
        assert_that(_answer(lambda: chain.contains(9))).is_equal_to(("refused", "ValueError"))
        assert_that(_answer(lambda: chain.contains_exactly(1, 2).last())).is_equal_to(("held", 2))

    def test_an_item_is_kept_before_the_callers_code_sees_it(self):
        def refusing(item: int) -> bool:
            if item == 2:
                raise ValueError("no")
            return True

        chain = assert_that(iter([1, 2, 3]))
        assert_that(lambda: chain.all_satisfy(refusing)).raises(ValueError).when_called_with()
        chain.contains_exactly(1, 2, 3)


class TestAPredicateHandedTheIteratorItself:
    def test_what_it_left_cannot_be_told_so_the_next_link_is_refused(self):
        chain = assert_that(iter([1, 2, 3])).starts_with(1).satisfies(lambda items: next(items) == 2)
        said = assert_that(lambda: chain.contains(3)).raises(TypeError).when_called_with().value
        assert_that(said).starts_with("val is a one-shot iterator that a predicate was handed after a part")

    def test_predicates_that_take_nothing_follow_one_another_and_the_link_that_reads_is_refused(self):
        chain = assert_that(iter([1, 2, 3])).starts_with(1)
        answered = _answer(lambda: chain.satisfies(lambda _: True).satisfies(lambda _: True).is_not_none())
        assert_that(answered[0]).is_equal_to("held")
        assert_that(_answer(lambda: chain.contains(2))).is_equal_to(("refused", "TypeError"))

    def test_a_value_is_not_asked_for_an_iterator_ahead_of_the_predicate(self):
        asked = []

        class Closed:
            def __iter__(self) -> Closed:
                asked.append("iter")
                raise ValueError("closed")

        held = Closed()
        assert_that(_answer(lambda: assert_that(held).satisfies(lambda value: value is held))[0]).is_equal_to("held")
        assert_that(asked).is_empty()

    def test_a_handoff_in_the_middle_of_a_walk_refuses_that_walk_and_is_not_taken_back(self):
        chain = assert_that(iter([1, 2, 3]))

        def taking(item: int) -> bool:
            if item == 1:
                chain.satisfies(lambda raw: next(raw) == 2)
            return item != 2

        answers = [
            _answer(lambda: chain.all_satisfy(taking)),
            _answer(lambda: chain.satisfies(lambda _: True).is_not_none())[0],
            _answer(lambda: chain.contains_exactly(1, 3)),
        ]
        assert_that(answers).is_equal_to([("refused", "TypeError"), "held", ("refused", "TypeError")])

    def test_a_value_that_raised_before_it_handed_anything_out_has_no_gap(self):
        class LateToStart:
            def __init__(self) -> None:
                self.left: list[object] = [ValueError("not yet"), 1, 2]

            def __iter__(self) -> LateToStart:
                return self

            def __next__(self) -> object:
                if not self.left:
                    raise StopIteration
                taken = self.left.pop(0)
                if isinstance(taken, ValueError):
                    raise taken
                return taken

        chain = assert_that(LateToStart())
        answers = [
            _answer(lambda: chain.contains(9)),
            _answer(lambda: chain.satisfies(lambda _: True).is_not_none())[0],
            _answer(lambda: chain.contains_exactly(1, 2).last()),
        ]
        assert_that(answers).is_equal_to([("refused", "ValueError"), "held", ("held", 2)])

    def test_with_nothing_read_before_it_the_next_link_reads_what_it_left(self):
        chain = assert_that(iter([1, 2, 3])).satisfies(lambda items: next(items) == 1)
        assert_that(_answer(lambda: chain.contains(2).contains(3).first())).is_equal_to(("held", 2))
        assert_that(_answer(lambda: chain.contains(1))[0]).is_equal_to("failed")

    def test_a_value_read_whole_before_it_has_nothing_left_to_take(self):
        chain = assert_that(iter([1, 2, 3])).contains(1)
        answered = _answer(lambda: chain.satisfies(lambda items: next(items, None) is None).contains(3).first())
        assert_that(answered).is_equal_to(("held", 1))

    def test_a_matcher_is_handed_the_items_and_takes_nothing(self):
        assert_that(iter([1, 2, 3])).satisfies(match.contains(1)).satisfies(~match.contains(9)).contains(3)

    def test_a_value_that_is_no_one_shot_iterator_is_handed_over_as_it_is(self):
        held = [1, 2, 3]
        assert_that(held).satisfies(lambda items: items is held).contains(3)
