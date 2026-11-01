"""A failed comparison's diff, held to explaining the failure, and a graph held to reading as the tree it is.

Two laws, asked of `is_equal_to` and of what answers the same question, `match.equal_to` and `check()`.

1. The diff explains the verdict.  A comparison that fails carries a diff with an entry in it.  An entry with
   two sides names a pair that fails on its own under the options that compare values, an entry with one side
   names a value the other side has nothing beside, and under ``ignore=`` no entry lies where the option told
   the comparison not to look.  An entry reached by keys, positions and fields alone leads from the two values
   compared back to the two it holds.

2. A graph is the tree it unfolds into.  Two values that lead back into themselves are compared as the two
   trees their graphs unfold into, cut off below the depth at which two graphs of their size can still differ.
   The expected verdict is not a second implementation of the comparison: it is the library's own answer on the
   trees, which hold no cycle.  Two nodes that can be told apart are told apart within as many steps as there
   are pairs of nodes, so nothing past that depth decides.  Where Python's own ``==`` is what compares, a cycle
   raises `RecursionError` as it does there, and that is the one difference allowed in the verdict.

   The paths of a graph's diff are among its tree's, with one exception.  Two lists of different lengths are
   aligned on what their elements print as, and a value that leads back prints ``[...]`` there, whatever it
   leads back to.  Two such elements may print alike and differ, and the trees they unfold into print apart: the
   graph is aligned as it prints and the tree as it does, and the two are paired otherwise.  The exception is
   what lies under two lists aligned so and no more: every other path of the graph is still held to the tree.
   Three ways of pairing the graph as its tree each paired some other graph, or some list with no cycle in it,
   worse than it was (`test_two_lists_matched_on_what_leads_back_are_aligned_as_they_print`).

The second law holds for options that read a value the same whether it is reached once or again: a comparator
that asks whether its operand holds itself answers differently on a tree by design, and is outside it.
"""

from __future__ import annotations

import array
import collections
import dataclasses
import functools
import itertools
import types
from typing import TYPE_CHECKING, Any, cast

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match, soft_assertions
from assertpy._engine import _diff, _introspection
from assertpy._engine._introspection import TakenApart, compares_by_parts
from assertpy.errors import DiffEntry, Step
from tests.test_duality import _PAIRS, Case

if TYPE_CHECKING:
    from collections.abc import Callable


_VALUE_OPTIONS = ("strict_types", "tolerance", "comparators")
"""The options that say how two values compare, which a pair taken out of the comparison is asked under again."""


def _outcome(call: Callable[[], object]) -> tuple[str, AssertionFailure | None]:
    """How a comparison ended: held, failed with its failure, ran out of stack, or was refused by a named error."""
    try:
        call()
    except AssertionFailure as failure:
        return "failed", failure
    except RecursionError:
        return "RecursionError", None
    except Exception as refusal:  # a refusal is an outcome here, whatever its class
        return f"refused: {type(refusal).__name__}", None
    return "held", None


_Regions = list[tuple[Step, ...]]
"""Where a comparison walked two sequences it had aligned on a print that stops short, each as the steps to it."""


def _printed(value: object) -> tuple[object, list[object]] | None:
    """What the print of *value* is made of: what it writes of its own, and the values it goes into in turn.

    ``None`` for a value whose print goes into nothing this knows of, which is then its print whole.  A dataclass
    with the print dataclasses write is gone into by the fields that print, and one with a print of its own is not.
    """
    kind = type(value)
    if kind.__repr__ is dict.__repr__:
        return ("dict", [repr(key) for key in cast("dict", value)]), list(cast("dict", value).values())
    if kind.__repr__ in (list.__repr__, tuple.__repr__):
        return (kind.__repr__, len(cast("list", value))), list(cast("list", value))
    if dataclasses.is_dataclass(value) and hasattr(kind.__repr__, "__wrapped__"):
        shown = [field.name for field in dataclasses.fields(value) if field.repr]
        return (kind.__qualname__, shown), [getattr(value, name) for name in shown]
    return None


def _print_apart_written_out(one: object, other: object) -> bool:
    """Whether two values print apart once what they lead back to is written out, however far: as their trees do.

    ``repr()`` stops at a value it is inside already and writes ``...`` for it.  Gone through side by side with
    each pair asked once, the two prints are followed past that, and they part where one writes what the other
    does not: another class, another length or key, or two values gone into nowhere that print apart.
    """
    met: set[tuple[int, int]] = set()
    pending = [(one, other)]
    while pending:
        left, right = pending.pop()
        if (id(left), id(right)) in met:
            continue
        met.add((id(left), id(right)))
        written, as_written = _printed(left), _printed(right)
        if written is None or as_written is None:
            if written is not as_written or repr(left) != repr(right):
                return True
        elif written[0] != as_written[0]:
            return True
        else:
            pending.extend(zip(written[1], as_written[1], strict=True))
    return False


def _walked_as_aligned(aligned: list[tuple[object, object]], walked: list[tuple[object, object, Any]]) -> _Regions:
    """The steps to each two sequences in *walked* that *aligned* holds as a pair, each on its own side."""
    return [steps for one, other, steps in walked if any(one is left and other is right for left, right in aligned)]


def _matched_apart(call: Callable[[], object]) -> tuple[str, AssertionFailure | None, _Regions]:
    """The outcome of *call*, and where it walked two sequences aligned on a print that stops at an elision.

    Two of their elements were matched on what they print as and then found unequal, and the two print apart
    once what they lead back to is written out (`_print_apart_written_out`), as their trees do: so a tree is
    not matched where the graph was.  Two that print alike however far they are written out are matched in a
    tree as well, and are no exception: with no value that leads back, with one their print leaves out or does
    not go into, or with three dots that are what a field holds.

    Where, and not which: an index under an aligned list is the actual side's, so the steps of an entry do not
    lead to its expected side, and the two lists are known by the place the walk took them at.
    """
    aligned: list[tuple[object, object]] = []
    walked: list[tuple[object, object, Any]] = []
    rechecked, sequence = _diff._rechecked_equal_runs, _diff._Walk.sequence

    def spied(opcodes: list, actual: Any, expected: Any) -> list:
        answered = rechecked(opcodes, actual, expected)
        matched = {index for tag, start, stop, _, _ in opcodes if tag == "equal" for index in range(start, stop)}
        if any(
            tag == "replace" and at in matched and _print_apart_written_out(actual[at], expected[at - start + other])
            for tag, start, stop, other, _ in answered
            for at in range(start, stop)
        ):
            aligned.append((actual, expected))
        return answered

    def followed(walk: Any, actual: Any, expected: Any, prefix: Any) -> Any:
        # a walk that may not align is one a pairing asks of two values, from a root of its own
        if walk.aligns:
            walked.append((actual, expected, prefix.entry().steps))
        return sequence(walk, actual, expected, prefix)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(_diff, "_rechecked_equal_runs", spied)
        patched.setattr(_diff._Walk, "sequence", followed)
        outcome, failure = _outcome(call)
    return outcome, failure, _walked_as_aligned(aligned, walked)


_UNREAD = object()
_NOTHING = object()


def _taken(value: Any, step: Step) -> object:
    """One step into *value*: `_NOTHING` where it holds nothing there, `_UNREAD` where it refuses the read."""
    try:
        return getattr(value, step.value) if step.kind == "attr" else value[step.value]
    except (LookupError, AttributeError):
        return _NOTHING
    except Exception:  # a value in the pool that refuses its own accessor, with whatever it raises
        return _UNREAD


def _led_to(root: object, entry: DiffEntry) -> object:
    """What the steps of *entry* lead to from *root*: `_NOTHING` where the last of them finds nothing there, and
    `_UNREAD` where a value on the way refuses the read or is not there to take the next step from."""
    value = root
    for position, step in enumerate(entry.steps):
        value = _taken(value, step)
        if value is _NOTHING or value is _UNREAD:
            return value if position == len(entry.steps) - 1 else _UNREAD
    return value


def _lies_under(regions: _Regions, entry: DiffEntry) -> bool:
    """Whether *entry* is at one of *regions* or under it."""
    return any(entry.steps[: len(region)] == region for region in regions)


def _hold_the_paths(failure: AssertionFailure, of_tree: set[str], regions: _Regions, said: str) -> None:
    """The paths of a graph's diff are among its tree's, but for what lies under one of *regions*."""
    assert failure.diff is not None
    apart = {entry.path for entry in failure.diff.entries if not _lies_under(regions, entry)}
    assert_that(apart).described_as(f"a path the tree does not differ at: {said}").is_subset_of(of_tree)


def _spec_paths(option: object) -> list[tuple[object, ...]]:
    """An ``ignore=`` option as the paths it names, a single key being a path of one."""
    specs = list(option) if isinstance(option, (list, set, frozenset)) else [option]
    return [spec if isinstance(spec, tuple) else (spec,) for spec in specs]


def _hold_the_diff(actual: object, expected: object, options: dict[str, Any], failure: AssertionFailure) -> None:
    """The first law, asked of one failure."""
    said = f"{actual!r} against {expected!r} under {options}"
    diff = failure.diff
    filtered = "ignore" in options or "include" in options
    # a key option reads each element of a sequence, so there a path it names starts past the index
    by_element = isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple))
    assert_that(diff).described_as(f"a failure with no diff: {said}").is_not_none()
    assert_that(diff.entries).described_as(f"a failure whose diff names nothing: {said}").is_not_empty()
    replayed = {name: options[name] for name in _VALUE_OPTIONS if name in options}
    ignored = _spec_paths(options["ignore"]) if "ignore" in options else []
    for entry in diff.entries:
        where = f"{entry.path!r} of {said}"
        keys = tuple(step.value for step in entry.steps)[by_element:]
        for path in ignored:
            assert_that(keys[: len(path)]).described_as(
                f"an entry where ignore= said not to look: {where}"
            ).is_not_equal_to(path)
        if any(step.kind == "line" for step in entry.steps) or diff.kind == "string":
            continue
        if entry.absent is None:
            verdict, _ = _outcome(lambda: assert_that(entry.actual).is_equal_to(entry.expected, **replayed))  # noqa: B023  # called before the loop moves on
            assert_that(verdict).described_as(f"an entry whose two sides do not differ: {where}").is_equal_to("failed")
        if filtered or not all(step.kind in ("key", "index", "attr") and step.side is None for step in entry.steps):
            continue
        sides = [("actual", actual, entry.actual)]
        indexed = [step.kind == "index" for step in entry.steps]
        if not any(indexed[:-1]) and not (entry.absent is None and any(indexed)):
            # two sequences that shifted apart are paired by alignment, and an index is then the actual side's
            sides.append(("expected", expected, entry.expected))
        for side, root, held in sides:
            led = _led_to(root, entry)
            if led is _UNREAD:
                continue
            if entry.absent == side:
                assert_that(led).described_as(f"a value on the {side} side, which {where} says has none").is_same_as(
                    _NOTHING
                )
            else:
                assert_that(led).described_as(f"the {side} side of {where}").is_same_as(held)


@settings(deadline=None, max_examples=3000, suppress_health_check=[HealthCheck.too_slow])
@given(case=_PAIRS["is_equal_to"].cases())
def test_a_failed_comparison_is_explained_by_its_diff(case: Case) -> None:
    (expected,) = case.args
    verdict, failure = _outcome(lambda: assert_that(case.value).is_equal_to(expected, **case.kwargs))
    if verdict == "failed":
        assert failure is not None
        _hold_the_diff(case.value, expected, case.kwargs, failure)


@dataclasses.dataclass
class _Record:
    """A node of a graph held as fields."""

    v: object = None
    next: object = None
    also: object = None


@dataclasses.dataclass(frozen=True)
class _Node:
    """One node of a graph, before it is built: what holds it, its own value, and the nodes it leads to.

    A list starts with *shift* items of no interest, so two lists of different lengths are paired by alignment.
    """

    kind: str
    value: object
    next: int | None = None
    also: int | None = None
    shift: int = 0


_Graph = tuple[_Node, ...]
_CUT = "<cut>"
_SHIFTED = ("first", "second")


def _built(graph: _Graph) -> object:
    """The graph as values that hold each other, the first node on top."""
    made: list[Any] = [{} if node.kind == "dict" else [] if node.kind == "list" else _Record(None) for node in graph]
    for node, value in zip(graph, made, strict=True):
        held = {"v": node.value, "next": _target(made, node.next), "also": _target(made, node.also)}
        if node.kind == "dict":
            value.update(held)
        elif node.kind == "list":
            value.extend([*_SHIFTED[: node.shift], *held.values()])
        else:
            vars(value).update(held)
    return made[0]


def _target(made: list[Any], index: int | None) -> object:
    return None if index is None else made[index]


def _unfolded(graph: _Graph, depth: int, index: int = 0) -> object:
    """The tree the graph unfolds into from *index*, cut off *depth* nodes down."""
    if depth == 0:
        return _CUT
    node = graph[index]
    held = {
        "v": node.value,
        "next": None if node.next is None else _unfolded(graph, depth - 1, node.next),
        "also": None if node.also is None else _unfolded(graph, depth - 1, node.also),
    }
    if node.kind == "dict":
        return held
    return [*_SHIFTED[: node.shift], *held.values()] if node.kind == "list" else _Record(**held)


def _reached(graph: _Graph) -> set[int]:
    found, pending = set(), [0]
    while pending:
        index = pending.pop()
        if index not in found:
            found.add(index)
            pending.extend(target for target in (graph[index].next, graph[index].also) if target is not None)
    return found


def _loops(graph: _Graph) -> bool:
    """Whether a node the top one reaches leads back to itself."""

    def back(start: int) -> bool:
        seen, pending = set(), [target for target in (graph[start].next, graph[start].also) if target is not None]
        while pending:
            index = pending.pop()
            if index == start:
                return True
            if index not in seen:
                seen.add(index)
                pending.extend(target for target in (graph[index].next, graph[index].also) if target is not None)
        return False

    return any(back(index) for index in _reached(graph))


def _may_run_out_of_stack(actual: _Graph, expected: _Graph, options: dict[str, Any]) -> bool:
    """Where a cycle is compared by Python's own ``==``, which raises on one: with no option at all."""
    return not options and (_loops(actual) or _loops(expected))


def _depth(actual: _Graph, expected: _Graph, options: dict[str, Any]) -> int:
    """Past this depth two graphs of these sizes hold no difference a shallower node did not show."""
    specs = [path for name in ("ignore", "include") if name in options for path in _spec_paths(options[name])]
    return len(actual) * len(expected) + max((len(path) for path in specs), default=0) + 2


def _size(graph: _Graph, depth: int) -> int:
    """How many nodes the tree cut at *depth* holds, counted without building it."""
    counts = dict.fromkeys(range(len(graph)), 1)
    for _ in range(depth):
        counts = {
            index: 1 + sum(counts[target] for target in (node.next, node.also) if target is not None)
            for index, node in enumerate(graph)
        }
    return counts[0]


def _same_case(left: str, right: object) -> bool:
    return isinstance(right, str) and left.lower() == right.lower()


_OPTIONS: dict[str, dict[str, Any]] = {
    "bare": {},
    "ignore a key": {"ignore": "v"},
    "ignore a path": {"ignore": ("next", "v")},
    "ignore two paths": {"ignore": [("next", "v"), ("next", "next", "v")]},
    "include a key": {"include": "next"},
    "include a path": {"include": ("next", "v")},
    "strict_types": {"strict_types": True},
    "tolerance": {"tolerance": 0.5},
    "comparators": {"comparators": {str: _same_case}},
    "ignore a key, strict_types": {"ignore": "v", "strict_types": True},
    "include a key, tolerance": {"include": "next", "tolerance": 0.5},
}


def _hold_the_graph(actual: _Graph, expected: _Graph, options: dict[str, Any]) -> str:
    """The second law, and the first on what it finds.  Answers how the comparison of the graphs ended."""
    said = f"{actual} against {expected} under {options}"
    left, right = _built(actual), _built(expected)
    depth = _depth(actual, expected, options)
    tree_left, tree_right = _unfolded(actual, depth), _unfolded(expected, depth)
    of_trees, tree_failure = _outcome(lambda: assert_that(tree_left).is_equal_to(tree_right, **options))
    of_graphs, failure, matched_apart = _matched_apart(lambda: assert_that(left).is_equal_to(right, **options))
    if of_graphs == "RecursionError":
        assert_that(_may_run_out_of_stack(actual, expected, options)).described_as(
            f"out of stack where the library compares: {said}"
        ).is_true()
        return of_graphs
    assert_that(of_graphs).described_as(f"a graph read otherwise than its tree: {said}").is_equal_to(of_trees)
    for surface, asked in (
        ("check()", lambda: assert_that(left).check().is_equal_to(right, **options).passed),
        ("match.equal_to", lambda: match.equal_to(right, **options).matches(left)),
    ):
        if of_graphs in ("held", "failed"):
            assert_that(asked()).described_as(f"{surface} on {said}").is_equal_to(of_graphs == "held")
    if failure is not None:
        _hold_the_diff(left, right, options, failure)
    if failure is not None and tree_failure is not None and failure.diff is not None:
        of_tree = {entry.path for entry in tree_failure.diff.entries}
        _hold_the_paths(failure, of_tree, matched_apart, said)
    return of_graphs


def _ring(kind: str, values: tuple[object, ...]) -> _Graph:
    """Nodes of one kind, each leading to the next and the last back to the first."""
    return tuple(_Node(kind, value, next=(index + 1) % len(values)) for index, value in enumerate(values))


def _chain(kind: str, values: tuple[object, ...]) -> _Graph:
    """Nodes of one kind, each leading to the next, the last to nothing."""
    last = len(values) - 1
    return tuple(_Node(kind, value, next=None if index == last else index + 1) for index, value in enumerate(values))


def _shared(kind: str, value: object) -> _Graph:
    """A node that reaches one node twice, which is a value held in two places and not a cycle."""
    return (_Node(kind, 0, next=1, also=1), _Node(kind, value))


def _through(kind: str, value: object) -> _Graph:
    """A dict that leads back to itself through a node of *kind*."""
    return (_Node("dict", 0, next=1), _Node(kind, value, next=0))


_KINDS = ("dict", "list", "record")
_SHAPES: dict[str, tuple[_Graph, _Graph, _Graph]] = {}
"""A shape as three graphs: one, one equal to it as a tree, and one that differs from it."""
for _kind in _KINDS:
    _SHAPES[f"a ring of one {_kind}"] = (_ring(_kind, (1,)), _ring(_kind, (1, 1)), _ring(_kind, (2,)))
    _SHAPES[f"a ring of two {_kind}s"] = (_ring(_kind, (1, 1)), _ring(_kind, (1,)), _ring(_kind, (1, 2)))
    _SHAPES[f"a ring of three {_kind}s"] = (_ring(_kind, (1, 1, 1)), _ring(_kind, (1, 1)), _ring(_kind, (1, 1, 2)))
    _SHAPES[f"a ring of {_kind}s against a chain"] = (
        _ring(_kind, (1,)),
        _ring(_kind, (1, 1, 1)),
        _chain(_kind, (1, 1, 1)),
    )
    _SHAPES[f"a chain of {_kind}s against a ring"] = (
        _chain(_kind, (1, 1)),
        _chain(_kind, (1, 1)),
        _ring(_kind, (1, 1)),
    )
    _SHAPES[f"a {_kind} held twice"] = (_shared(_kind, 1), _shared(_kind, 1), _shared(_kind, 2))
    _SHAPES[f"a cycle through a {_kind}"] = (_through(_kind, 1), _through(_kind, 1), _through(_kind, 2))

_PINNED = [
    pytest.param(shape, option, id=f"{shape}, {option}") for shape, option in itertools.product(_SHAPES, _OPTIONS)
]


@pytest.mark.parametrize(("shape", "option"), _PINNED)
def test_a_shape_is_read_as_its_tree_under_every_option(shape: str, option: str) -> None:
    one, twin, other = _SHAPES[shape]
    for expected in (twin, other):
        _hold_the_graph(one, expected, _OPTIONS[option])
        _hold_the_graph(expected, one, _OPTIONS[option])


def _answers(shape: str, option: str) -> set[str]:
    one, twin, other = _SHAPES[shape]
    return {_hold_the_graph(one, expected, _OPTIONS[option]) for expected in (twin, other)}


@pytest.mark.parametrize("option", [name for name, options in _OPTIONS.items() if set(options) & set(_VALUE_OPTIONS)])
@pytest.mark.parametrize("shape", _SHAPES)
def test_an_option_that_compares_values_answers_every_shape_both_ways(shape: str, option: str) -> None:
    """The laws above are held to a verdict, so a shape that only ever ran out of stack would be held to nothing."""
    answered = _answers(shape, option)
    assert_that(answered - {"held", "failed"}).described_as(f"{shape} under {option}").is_empty()
    if option != "include a key, tolerance" and "against" not in shape:
        assert_that(answered).described_as(f"{shape} under {option}").is_equal_to({"held", "failed"})


@pytest.mark.parametrize("option", ["ignore a key", "ignore a path", "include a key", "include a path"])
@pytest.mark.parametrize("shape", [shape for shape in _SHAPES if "list" not in shape])
def test_a_key_option_answers_a_shape_that_no_list_is_in(shape: str, option: str) -> None:
    assert_that(_answers(shape, option) - {"held", "failed"}).described_as(f"{shape} under {option}").is_empty()


_SCALARS = st.sampled_from([0, 1, 2, 1.0, 1.4, True, "a", "A", None])


@st.composite
def _graphs(draw: st.DrawFn) -> _Graph:
    """Up to three nodes, each leading on to one, and one of them to a second: the tree stays small."""
    count = draw(st.integers(1, 3))
    targets = st.none() | st.integers(0, count - 1)
    twice = draw(st.none() | st.integers(0, count - 1))
    return tuple(
        _Node(
            draw(st.sampled_from(_KINDS)),
            draw(_SCALARS),
            draw(targets),
            draw(targets) if index == twice else None,
            draw(st.integers(0, len(_SHIFTED))),
        )
        for index in range(count)
    )


@st.composite
def _graph_pairs(draw: st.DrawFn) -> tuple[_Graph, _Graph]:
    """Two graphs, the second drawn afresh or made from the first by changing one node."""
    one = draw(_graphs())
    if draw(st.booleans()):
        return one, draw(_graphs())
    index = draw(st.integers(0, len(one) - 1))
    changed = draw(
        st.sampled_from(
            [
                dataclasses.replace(one[index], value=draw(_SCALARS)),
                dataclasses.replace(one[index], kind=draw(st.sampled_from(_KINDS))),
                dataclasses.replace(one[index], next=draw(st.none() | st.integers(0, len(one) - 1))),
                dataclasses.replace(one[index], shift=draw(st.integers(0, len(_SHIFTED)))),
                one[index],
            ]
        )
    )
    return one, (*one[:index], changed, *one[index + 1 :])


@settings(deadline=None, max_examples=1500, suppress_health_check=[HealthCheck.too_slow])
@example(pair=(_ring("dict", (1,)), _ring("dict", (2,))), option="ignore a key")
@example(pair=(_ring("record", (1,)), _ring("record", (2,))), option="include a path")
@example(pair=(_ring("list", (1, 2)), _ring("list", (1, 9))), option="bare")
@example(pair=(_through("list", 1), _through("list", 2)), option="strict_types")
@example(pair=((_Node("list", 1.0),), (_Node("list", 1), _Node("dict", 0))), option="ignore a key, strict_types")
@example(
    pair=((_Node("list", 0, 1), _Node("list", 1)), (_Node("list", 0, 1), _Node("list", 1.4))),
    option="include a key, tolerance",
)
@example(
    pair=(
        (_Node("dict", 0, 0),),
        (_Node("dict", 0, 1), _Node("dict", 0, 2), _Node("record", 0, 0)),
    ),
    option="ignore two paths",
)
@example(
    pair=(
        (_Node("dict", 0, 0),),
        (_Node("record", 0, 1), _Node("dict", 0, 2), _Node("record", 0, 1)),
    ),
    option="ignore a key",
)
@example(
    pair=(
        (_Node("dict", 0, 2), _Node("dict", 1, 0), _Node("dict", 0, 1)),
        (_Node("record", 1, 0),),
    ),
    option="ignore two paths",
)
@example(
    pair=((_Node("list", 0, 0, shift=2),), (_Node("list", 0, 0),)),
    option="tolerance",
)
@example(
    pair=(
        (_Node("list", 0, None, 1), _Node("dict", 0, 1), _Node("dict", 0)),
        (_Node("list", 0, 1, shift=1), _Node("dict", 0, 1)),
    ),
    option="bare",
)
@example(
    pair=((_Node("list", 0, 1, shift=2), _Node("dict", 0)), (_Node("list", 0, 1), _Node("dict", 0))),
    option="ignore a key",
)
@example(
    pair=(
        (_Node("list", 0, 0, 0),),
        (_Node("list", 0, 1, shift=1), _Node("list", 0, 1, 0)),
    ),
    option="comparators",
)
@example(
    pair=(
        (_Node("list", 2, 1, 0, 1), _Node("list", 2, 2, None, 2), _Node("list", 0, 0, None, 1)),
        (_Node("list", 2, 1, 2, 1), _Node("list", 2, 0, None, 2), _Node("list", 0, 0, None, 1)),
    ),
    option="bare",
)
@given(pair=_graph_pairs(), option=st.sampled_from(sorted(_OPTIONS)))
def test_a_graph_is_read_as_the_tree_it_unfolds_into(pair: tuple[_Graph, _Graph], option: str) -> None:
    actual, expected = pair
    options = _OPTIONS[option]
    depth = _depth(actual, expected, options)
    if _size(actual, depth) + _size(expected, depth) > 4000:
        return
    _hold_the_graph(actual, expected, options)


def test_two_lists_matched_on_what_leads_back_are_aligned_as_they_print() -> None:
    """Where the paths of a graph are not its tree's: both diffs are true, and they pair the lists otherwise.

    Tried and put back, each for a diff it made worse.  Joining the pieces around every pair that came apart
    read a list beside its near twin seven rows for four.  Joining around a pair whose print holds ``[...]``
    did the same wherever a ``__repr__`` writes those characters.  Joining around a pair that differs under
    where it leads back paired a list holding a record with a field left out of its print, and one beside an
    ordinary pair that came apart, otherwise than its tree, where they had been paired as it.
    """
    outer: list = ["s"]
    outer.append(["a", outer])
    inner: list = ["a"]
    inner.append(inner)
    assert_that(repr(outer)).is_equal_to(repr(["s", inner])).is_equal_to("['s', ['a', [...]]]")
    _, of_graphs = _outcome(lambda: assert_that(["a", "b", outer]).is_equal_to(["b", "a", ["s", inner], "a"]))
    tree, other_tree = ["s", ["a", ["s", ["a", _CUT]]]], ["s", ["a", ["a", ["a", _CUT]]]]
    _, of_trees = _outcome(lambda: assert_that(["a", "b", tree]).is_equal_to(["b", "a", other_tree, "a"]))
    assert_that([entry.path for entry in of_graphs.diff.entries]).is_equal_to(["[0]", "[1]", "[2][1][1][0]", "[3]"])
    assert_that([entry.path for entry in of_trees.diff.entries]).is_equal_to(["expected[0]", "[1]", "[2]"])


class TestTheExceptionOfTheSecondLawReachesNoFurtherThanTheListsAlignedSo:
    """A dict that holds the pair Hypothesis found beside a value of its own: what lies under the two lists
    aligned on an elision is the exception, and the value beside them is held to the tree like any other."""

    _LISTS = (
        (_Node("list", 2, 1, 0, 1), _Node("list", 2, 2, None, 2), _Node("list", 0, 0, None, 1)),
        (_Node("list", 2, 1, 2, 1), _Node("list", 2, 0, None, 2), _Node("list", 0, 0, None, 1)),
    )

    @staticmethod
    def _under_a_parent(lists: _Graph, value: object, kind: str) -> _Graph:
        """The graph of *lists* a node further down, under a parent of *kind* that holds *value* beside it."""
        moved = tuple(
            dataclasses.replace(
                node,
                next=None if node.next is None else node.next + 1,
                also=None if node.also is None else node.also + 1,
            )
            for node in lists
        )
        return (_Node(kind, value, 1), *moved)

    @staticmethod
    def _paths_of_the_trees(actual: _Graph, expected: _Graph) -> set[str]:
        depth = _depth(actual, expected, {})
        _, failure = _outcome(lambda: assert_that(_unfolded(actual, depth)).is_equal_to(_unfolded(expected, depth)))
        assert failure is not None
        return {entry.path for entry in failure.diff.entries}

    def test_what_the_exception_covers_in_the_pair_alone(self):
        """The two lists aligned so are walked at two places of the pair.  Six of its twelve entries lie under
        them, the four its tree does not have among them, and the other six are paths of the tree."""
        actual, expected = self._LISTS
        left, right = _built(actual), _built(expected)
        _, failure, regions = _matched_apart(lambda: assert_that(left).is_equal_to(right))
        assert_that(sorted({"".join(f"[{step.value}]" for step in region) for region in regions})).is_equal_to(
            ["[2][3][2][2]", "[3][2]"]
        )
        of_tree = self._paths_of_the_trees(actual, expected)
        under = sorted(entry.path for entry in failure.diff.entries if _lies_under(regions, entry))
        assert_that(under).is_equal_to(
            [
                "[2][3][2][2][1]",
                "[2][3][2][2][2]",
                "[2][3][2][2][4]",
                "[3][2][1]",
                "[3][2][2]",
                "[3][2][4]",
            ]
        )
        assert_that(sorted(entry.path for entry in failure.diff.entries if entry.path not in of_tree)).is_equal_to(
            ["[2][3][2][2][1]", "[2][3][2][2][2]", "[3][2][1]", "[3][2][2]"]
        )
        assert_that(len(failure.diff.entries)).is_equal_to(12)

    @pytest.mark.parametrize(("kind", "beside"), [("dict", "v"), ("list", "[0]"), ("record", ".v")])
    def test_a_difference_beside_the_lists_is_held_to_the_tree(self, kind, beside):
        """Under a parent of each kind, the value beside the pair lies outside the exception, the four paths the
        tree does not have lie under it, and the law holds for the whole."""
        actual = self._under_a_parent(self._LISTS[0], "one", kind)
        expected = self._under_a_parent(self._LISTS[1], "other", kind)
        assert_that(_hold_the_graph(actual, expected, {})).is_equal_to("failed")
        left, right = _built(actual), _built(expected)
        _, failure, regions = _matched_apart(lambda: assert_that(left).is_equal_to(right))
        of_tree = self._paths_of_the_trees(actual, expected)
        under = {entry.path: _lies_under(regions, entry) for entry in failure.diff.entries}
        assert_that(under[beside]).is_false()
        apart = [path for path in under if path not in of_tree]
        assert_that(apart).is_length(4)
        assert_that([under[path] for path in apart]).is_equal_to([True] * 4)

    def test_a_path_the_tree_does_not_have_beside_them_is_refused(self):
        """A diff that named a place outside the two lists, which the tree does not differ at, would be a defect
        of the pairing somewhere else: the exception does not cover it."""
        actual = self._under_a_parent(self._LISTS[0], "one", "dict")
        expected = self._under_a_parent(self._LISTS[1], "other", "dict")
        left, right = _built(actual), _built(expected)
        _, failure, regions = _matched_apart(lambda: assert_that(left).is_equal_to(right))
        of_tree = self._paths_of_the_trees(actual, expected)
        _hold_the_paths(failure, of_tree, regions, "the pair under a dict")
        with pytest.raises(AssertionFailure, match="a path the tree does not differ at"):
            _hold_the_paths(failure, of_tree - {"v"}, regions, "the pair under a dict")
        with pytest.raises(AssertionFailure, match="a path the tree does not differ at"):
            _hold_the_paths(failure, of_tree, [], "the pair under a dict")

    def test_an_entry_is_under_a_place_by_the_steps_that_lead_to_it(self):
        region = (Step("key", "next"), Step("index", 2))
        under = DiffEntry(path="next[2][0]", steps=(*region, Step("index", 0)))
        one_sided = DiffEntry(path="next[2]expected[1]", steps=(*region, Step("index", 1, side="expected")))
        assert_that(_lies_under([region], under)).is_true()
        assert_that(_lies_under([region], one_sided)).is_true()
        assert_that(_lies_under([region], DiffEntry(path="next[2]", steps=region))).is_true()
        assert_that(_lies_under([region], DiffEntry(path="next[3][0]", steps=(region[0], Step("index", 3))))).is_false()
        assert_that(_lies_under([region], DiffEntry(path="next", steps=region[:1]))).is_false()
        assert_that(_lies_under([], under)).is_false()

    def test_the_two_lists_of_an_exception_are_a_pair_each_on_its_own_side(self):
        """One of them walked beside some other list is another comparison, and no place of the exception."""
        one, other, apart = ["a"], ["b"], ["c"]
        walked: Any = [(one, other, "as aligned"), (one, apart, "beside another"), (apart, other, "beside another")]
        assert_that(_walked_as_aligned([(one, other)], walked)).is_equal_to(["as aligned"])
        assert_that(_walked_as_aligned([(other, one)], walked)).is_empty()
        assert_that(_walked_as_aligned([], walked)).is_empty()

    def test_two_prints_are_followed_past_where_they_stop(self):
        outer: list = ["s"]
        outer.append(["a", outer])
        inner: list = ["a"]
        inner.append(inner)
        assert_that(repr(outer)).is_equal_to(repr(["s", inner]))
        assert_that(_print_apart_written_out(outer, ["s", inner])).is_true()
        keyed: dict = {}
        keyed["k"] = {"a": keyed}
        looped: dict = {}
        looped["a"] = looped
        assert_that(_print_apart_written_out(keyed, {"k": looped})).is_true()
        record = _Record("s")
        record.next = _Record("a", record)
        held = _Record("a")
        held.next = held
        assert_that(repr(record)).is_equal_to(repr(_Record("s", held)))
        assert_that(_print_apart_written_out(record, _Record("s", held))).is_true()
        longer: list = []
        longer.extend([[longer], None])
        shorter: list = []
        shorter.append(shorter)
        assert_that(_print_apart_written_out(longer, [shorter, None])).is_true()

    def test_two_that_print_alike_however_far_do_not_part(self):
        once: list = []
        once.append(once)
        twice: list = []
        twice.append([twice])
        shared = ["s"]
        for one, other in (
            (once, twice),
            (once, once),
            ([shared, shared], [["s"], ["s"]]),
            ("...", "..."),
            (["[...]"], ["[...]"]),
            ((1, [2, {"k": 3}]), (1, [2, {"k": 3}])),
            (_Record("r", _Record("s")), _Record("r", _Record("s"))),
        ):
            assert_that(_print_apart_written_out(one, other)).described_as(f"{one!r} and {other!r}").is_false()
        for one, other in (
            ([1], (1,)),
            ([1], [1, 2]),
            ({"a": 1}, {"b": 1}),
            (_Record(1), [1]),
            ("a", "b"),
            ([1], "[1]"),
        ):
            assert_that(_print_apart_written_out(one, other)).described_as(f"{one!r} and {other!r}").is_true()

    @pytest.mark.parametrize("shape", ["fields left out of the print", "a print of its own", "three dots in a field"])
    def test_two_that_lead_back_where_their_print_does_not_go_are_no_exception(self, shape):
        """A value that leads back in a field its print leaves out, or under a print that goes into nothing, with
        or without three dots that are what a field holds: the tree prints as the graph does, the two are
        matched there as here, and the law holds for them whole."""

        @dataclasses.dataclass
        class Holding:
            name: int = dataclasses.field(repr=False)
            back: object = dataclasses.field(default=None, repr=False)
            marker: str = dataclasses.field(default="...", repr=shape == "three dots in a field")

            if shape == "a print of its own":

                def __repr__(self) -> str:
                    return "held"

        def looped(name: int) -> Holding:
            value = Holding(name)
            value.back = [value]
            return value

        one, other = looped(1), looped(2)
        assert_that(cast("list", one.back)[0]).is_same_as(one)
        assert_that(repr(one)).is_equal_to(repr(other)).is_equal_to(
            {
                "fields left out of the print": f"{Holding.__qualname__}()",
                "a print of its own": "held",
                "three dots in a field": f"{Holding.__qualname__}(marker='...')",
            }[shape]
        )
        left, right = ["first", one, None], ["first", "second", other, None]
        assert_that([tag for tag, *_ in _diff._alignment_opcodes(left, right)]).contains("replace")
        _, failure, regions = _matched_apart(lambda: assert_that(left).is_equal_to(right))
        assert_that(failure).is_not_none()
        assert_that(regions).is_empty()

    @pytest.mark.parametrize("printed", ["Alike()", "Alike(...)", "[...]"])
    def test_two_that_print_alike_and_lead_nowhere_back_are_no_exception(self, printed):
        """Matched on their print and found unequal as well, and alike in a tree: the law holds for them whole,
        whatever the print says, and three dots in it are no elision."""

        class Alike:
            __hash__ = None

            def __init__(self, held: int) -> None:
                self.held = held

            def __eq__(self, other: object) -> bool:
                return isinstance(other, Alike) and self.held == other.held

            def __repr__(self) -> str:
                return printed

        actual = (_Node("list", Alike(1), None, None, 1),)
        expected = (_Node("list", Alike(2), None, None, 2),)
        left, right = _built(actual), _built(expected)
        came_apart = _diff._alignment_opcodes(left, right)
        assert_that([tag for tag, *_ in came_apart]).contains("replace")
        _, failure, regions = _matched_apart(lambda: assert_that(left).is_equal_to(right))
        assert_that(failure).is_not_none()
        assert_that(regions).is_empty()
        assert_that(_hold_the_graph(actual, expected, {})).is_equal_to("failed")


def _ring_of_pairs(size: int) -> tuple[list, list]:
    """Two rings of lists, each list holding itself and, in a list of another length than its twin's, the next."""
    left: list[list] = [[0] for _ in range(size)]
    right: list[list] = [[0] for _ in range(size)]
    for index in range(size):
        following = (index + 1) % size
        left[index] += [left[index], [left[following], 7]]
        right[index] += [right[index], [right[following]]]
    return left[0], right[0]


class TestAPairingAsksWhetherTwoGraphsDiffer:
    """Two lists of different lengths ask of their elements whether those differ, to choose between pairing them
    by index and by alignment.  The asking is a walk of its own.  A walk that chose a pairing in turn asked again
    from inside the asking, and two graphs that hold such lists asked it of each other until the stack ran out,
    under an option and without one.  A walk run by an asking pairs by index and asks nothing."""

    _OPTIONS = ({"tolerance": 0.5}, {"strict_types": True}, {"comparators": {str: _same_case}})

    def test_a_graph_that_reaches_its_own_asking_is_answered(self) -> None:
        one: list = [0]
        one += [one, one]
        inner: list = [0]
        other: list = ["first", 0, inner, None]
        inner += [inner, other]
        for options in ({}, *self._OPTIONS):
            verdict, failure = _outcome(lambda options=options: assert_that(one).is_equal_to(other, **options))
            assert_that(verdict).described_as(str(sorted(options))).is_equal_to("failed")
            assert_that(failure.diff.entries).is_not_empty()
        assert_that(_diff._graphs_differ(one, other)).is_true()
        assert_that(_diff._graphs_differ(one, one)).is_false()

    @pytest.mark.parametrize("size", [1, 2, 3, 40])
    def test_a_ring_of_pairs_that_reach_one_another_is_answered(self, size: int) -> None:
        """No pair comes round again until the ring closes, so remembering the pairs being asked did not end it:
        every asking still stood on the one before.  A ring of 1200, past the stack, is answered too, in minutes."""
        one, other = _ring_of_pairs(size)
        assert_that(_diff._graphs_differ(one, other)).is_true()
        for options in self._OPTIONS:
            verdict, failure = _outcome(lambda options=options: assert_that(one).is_equal_to(other, **options))
            assert_that(verdict).described_as(str(sorted(options))).is_equal_to("failed")
            assert_that(failure.diff.entries).described_as(str(sorted(options))).is_length(size)

    def test_an_asking_chooses_no_pairing(self, monkeypatch) -> None:
        def chosen(actual: object, expected: object) -> None:
            raise AssertionError("a walk run by an asking chose a pairing")

        one, other = _ring_of_pairs(3)
        monkeypatch.setattr(_diff, "_alignment_opcodes_if_useful", chosen)
        assert_that(_diff._graphs_differ(one, other)).is_true()
        assert_that(_diff._graphs_differ([1, [2, 3]], [1, [2]])).is_true()
        assert_that(_diff._graphs_differ([1, [2, 3]], [1, [2, 3]])).is_false()

    @settings(deadline=None, max_examples=600, suppress_health_check=[HealthCheck.too_slow])
    @given(pair=_graph_pairs())
    def test_an_asking_answers_by_index_what_it_answered_choosing_a_pairing(self, pair: tuple[_Graph, _Graph]) -> None:
        """The answer is whether the walk found anything, and that is one answer however two sequences are
        paired: two of one length are never aligned, two of different lengths leave an entry either way."""
        actual, expected = _built(pair[0]), _built(pair[1])
        try:
            aligned = bool(_diff._child_entries(actual, expected, _diff._ROOT, descended_for="unanswered"))
        except RecursionError:
            return
        by_index = _diff._child_entries(actual, expected, _diff._ROOT, descended_for="unanswered", aligns=False)
        assert_that(bool(by_index)).is_equal_to(aligned)


class TestAGraphInASequenceThatShifted:
    """Two sequences of different lengths are paired by alignment, which asks ``==`` of their elements before
    the walk does: a graph ``==`` cannot finish raised there, under the options that compare it everywhere else."""

    @staticmethod
    def _looped(value: object = 1) -> list:
        made: list = [value]
        made.append(made)
        return made

    @pytest.mark.parametrize(
        "options",
        [{"tolerance": 0.5}, {"strict_types": True}, {"comparators": {str: _same_case}}],
        ids=["tolerance", "strict_types", "comparators"],
    )
    def test_an_extra_element_beside_a_graph_is_the_entry(self, options):
        actual, expected = [self._looped()], [self._looped(), 0]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.expected, entry.absent) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("[1]", 0, "actual")])

    def test_a_graph_past_a_shift_is_paired_by_the_alignment(self):
        actual = [1, 2, self._looped(), 3]
        expected = [0, 1, 2, self._looped(), 3]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, tolerance=0.1))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.expected, entry.absent) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("expected[0]", 0, "actual")])

    def test_two_graphs_that_differ_past_where_equality_gives_up_are_shown_in_the_message(self):
        def looped(last):
            made: list = [1]
            made.extend([made, last])
            return made

        actual, expected = [0, looped(5), *range(30)], [9, looped(6), *range(30)]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["[0]", "[1][2]"])
        assert_that(failure._message).is_equal_to(
            "Expected <[0, [1, [...], 5], ..]> to be equal to <[9, [1, [...], 6], ..]>, but was not."
        )

    def test_two_equal_graphs_matched_by_the_alignment_stay_matched(self):
        # split back into a substitution they counted against the alignment, and the pairing went by position
        actual, expected = [self._looped(), "x"], [self._looped(), "q", "x"]
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, ignore="missing"))
        rows = [(entry.path, entry.expected, entry.absent) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("expected[1]", "q", "actual")])

    def test_two_equal_graphs_do_not_tip_the_pairing_towards_alignment(self):
        # counted as a difference, the pair made alignment look shorter, and it listed one removed, the other added
        actual, expected = [0, None, self._looped()], ["first", 0, self._looped(), None]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, ignore="missing"))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected, entry.absent) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to(
            [("[0]", 0, "first", None), ("[1]", None, 0, None), ("[3]", None, None, "actual")]
        )

    def test_the_message_of_a_failure_beside_a_graph_is_still_the_failure(self):
        # the elision of the message asks `==` of each pair too, and raised in place of the failure
        actual = [0, self._looped(), *range(30)]
        expected = [9, self._looped(), *range(30)]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("[0]", 0, 9)]
        )
        assert_that(failure._message).is_equal_to("Expected <[0, ..]> to be equal to <[9, ..]>, but was not.")


@dataclasses.dataclass
class _Row:
    id: int
    name: str
    price: float = 1.0


_ROWS = st.one_of(
    st.builds(dict, id=st.integers(0, 2), name=st.sampled_from(["a", "A", "b"]), price=st.sampled_from([1.0, 1.4, 3])),
    st.builds(_Row, st.integers(0, 2), st.sampled_from(["a", "A", "b"]), st.sampled_from([1.0, 1.4, 3])),
    st.sampled_from([1, 1.4, True, "a", "A", None]),
    st.lists(st.sampled_from([1, 1.4, "a", "A"]), max_size=2),
)
_KEY_OPTIONS: dict[str, dict[str, Any]] = {
    "ignore": {"ignore": "id"},
    "include": {"include": "name"},
    "ignore two": {"ignore": ["id", "price"]},
    "ignore, strict_types": {"ignore": "id", "strict_types": True},
    "ignore, tolerance": {"ignore": "id", "tolerance": 0.5},
    "include, comparators": {"include": "name", "comparators": {str: _same_case}},
}


def _fields_of(item: object) -> bool:
    return isinstance(item, (dict, _Row))


def _element_differs(one: object, other: object, options: dict[str, Any]) -> bool:
    """Whether two elements differ on their own: by their fields under the options where both have fields, and
    under the options that compare values where they do not."""
    asked = (
        options if _fields_of(one) and _fields_of(other) else {k: v for k, v in options.items() if k in _VALUE_OPTIONS}
    )
    return _outcome(lambda: assert_that(one).is_equal_to(other, **asked))[0] != "held"


class TestASequenceUnderAKeyOptionFailsOnce:
    """A list or a tuple under ``ignore=`` or ``include=`` fails as a dict does: one failure for the two sequences,
    with every element that differs in its diff, at a path that starts at the sequence.

    It failed in words of its own: about the first element that differed, without saying where it stood, or about
    the length or a plain element with no diff at all.
    """

    @settings(deadline=None, max_examples=600, suppress_health_check=[HealthCheck.too_slow])
    @given(
        pairs=st.lists(st.tuples(_ROWS, _ROWS) | _ROWS.map(lambda row: (row, row)), max_size=4),
        option=st.sampled_from(sorted(_KEY_OPTIONS)),
        as_tuple=st.booleans(),
    )
    def test_the_entries_name_the_elements_that_differ_on_their_own(self, pairs, option, as_tuple):
        options = _KEY_OPTIONS[option]
        make = tuple if as_tuple else list
        actual, expected = make(one for one, _ in pairs), make(other for _, other in pairs)
        differing = [index for index, (one, other) in enumerate(pairs) if _element_differs(one, other, options)]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(verdict).described_as(f"{actual} against {expected} under {options}").is_equal_to(
            "failed" if differing else "held"
        )
        assert_that(match.equal_to(expected, **options).matches(actual)).is_equal_to(not differing)
        if failure is None:
            return
        _hold_the_diff(actual, expected, options, failure)
        assert_that(failure.actual).is_same_as(actual)
        assert_that(failure.expected).is_same_as(expected)
        named = sorted({entry.steps[0].value for entry in failure.diff.entries})
        assert_that(named).described_as(f"{actual} against {expected} under {options}").is_equal_to(differing)

    def test_the_message_names_both_sequences_and_leaves_out_what_matched(self):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
        other = [{"id": 9, "name": "a"}, {"id": 9, "name": "X"}, {"id": 9, "name": "Y"}]
        _, failure = _outcome(lambda: assert_that(rows).is_equal_to(other, ignore="id"))
        assert_that(failure._message).is_equal_to(
            "Expected <[.., {'name': 'b'}, {'name': 'c'}]> to be equal to <[.., {'name': 'X'}, {'name': 'Y'}]>"
            " ignoring keys <id>, but was not."
        )
        assert_that(failure.diff.kind).is_equal_to("sequence")
        rows_named = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows_named).is_equal_to([("[1].name", "b", "X"), ("[2].name", "c", "Y")])

    def test_a_tuple_reads_as_a_tuple(self):
        _, failure = _outcome(lambda: assert_that(({"id": 1, "n": 1},)).is_equal_to(({"id": 2, "n": 2},), include="n"))
        assert_that(failure._message).is_equal_to(
            "Expected <({'n': 1},)> to be equal to <({'n': 2},)> including keys <n>, but was not."
        )

    def test_a_longer_sequence_has_its_extra_element_as_an_entry(self):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        _, failure = _outcome(lambda: assert_that(rows).is_equal_to(rows[:1], ignore="id"))
        rows_named = [(entry.path, entry.actual, entry.absent) for entry in failure.diff.entries]
        assert_that(rows_named).is_equal_to([("[1]", {"name": "b"}, "expected")])
        _hold_the_diff(rows, rows[:1], {"ignore": "id"}, failure)

    def test_an_element_put_in_at_the_head_is_the_one_entry(self):
        # paired by position every row after it would differ: the elements are paired as the keys left in align
        rows = [{"id": number, "name": name} for number, name in enumerate("abc")]
        shifted = [{"id": 7, "name": "new"}, *({"id": 9, "name": row["name"]} for row in rows)]
        _, failure = _outcome(lambda: assert_that(rows).is_equal_to(shifted, ignore="id"))
        rows_named = [(entry.path, entry.expected, entry.absent) for entry in failure.diff.entries]
        assert_that(rows_named).is_equal_to([("expected[0]", {"name": "new"}, "actual")])
        assert_that(failure._message).contains("to be equal to <[{'name': 'new'}, ..]> ignoring keys <id>")

    def test_an_element_that_repeats_is_paired_once(self):
        row, other = {"id": 1, "name": "a"}, {"id": 2, "name": "b"}
        _, failure = _outcome(lambda: assert_that([row, row, other]).is_equal_to([row, other], ignore="id"))
        assert_that(failure.diff.entries).is_length(1)
        assert_that(failure.diff.entries[0].absent).is_equal_to("expected")

    def test_an_element_with_fields_is_read_by_them_whatever_its_own_equality_says(self):
        assert_that([_Never(), 1]).is_equal_to([_Never(), 1], ignore="missing")
        _, failure = _outcome(lambda: assert_that([_Never(1), 1]).is_equal_to([_Never(2), 1], ignore="missing"))
        rows_named = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows_named).is_equal_to([("[0].v", 1, 2)])

    def test_an_element_held_apart_by_its_own_equality_is_the_entry(self):
        actual, expected = [_OwnList([1])], [_OwnList([1])]
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, ignore="missing"))
        rows_named = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows_named).is_equal_to([("[0]", actual[0], expected[0])])

    def test_a_soft_block_collects_it_once(self):
        rows, other = [{"id": 1, "n": 1}, {"id": 2, "n": 2}, 3], [{"id": 1, "n": 8}, {"id": 2, "n": 9}, 4]
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(rows).is_equal_to(other, ignore="id")
        assert_that(str(caught.value).count("to be equal to")).is_equal_to(1)
        assert_that(str(caught.value)).contains("[0].n", "[1].n", "[2]")

    def test_a_key_the_comparison_is_told_to_include_and_an_element_lacks_is_still_a_prerequisite(self):
        with pytest.raises(AssertionFailure, match="to include key <n>, but did not include key <n>"):
            assert_that([{"n": 1}, {"m": 1}]).is_equal_to([{"n": 1}, {"m": 1}], include="n")


class _Numbers(array.array):
    def __new__(cls, items):
        return super().__new__(cls, "i", items)


class _Slotted:
    __slots__ = ("held",)


class _HalfSlotted(_Slotted):
    """A value with a slot and a ``__dict__``: what the slot holds is not in the ``__dict__``."""

    def __init__(self, items):
        self.held, self.note = items, "same"

    def __eq__(self, other):
        return isinstance(other, _HalfSlotted) and self.held == other.held

    __hash__ = None


class _FailedError(Exception):
    def __init__(self, items):
        super().__init__(*items)
        self.note = "same"

    def __eq__(self, other):
        return isinstance(other, _FailedError) and self.args == other.args

    __hash__ = None


class _Weak:
    __slots__ = ("__dict__", "__weakref__")


class TestAContainerOfAClassOfItsOwnIsNoBagOfFields:
    """A subclass of a builtin container carries a ``__dict__``, and its items are not in it: read as the fields
    of the value under a key option, it made any two such containers equal whatever they held.  The same goes
    for any value that holds something outside its ``__dict__``: a slot, the ``args`` of an exception."""

    KINDS = (type("Kept", (list,), {}), type("Pair", (tuple,), {}), type("Bag", (set,), {}), collections.deque)

    @pytest.mark.parametrize(
        ("kind", "only_its_dict"),
        [
            (type("Plain", (), {}), True),
            (type("Child", (type("Base", (), {}),), {}), True),
            (types.SimpleNamespace, True),
            (type("Space", (types.SimpleNamespace,), {}), True),
            (_Weak, True),
            (_HalfSlotted, False),
            (_FailedError, False),
            (_Numbers, False),
            (functools.partial, False),
            *((kind, False) for kind in KINDS),
            (type("Whole", (int,), {}), False),
            (type("Text", (str,), {}), False),
        ],
        ids=lambda value: getattr(value, "__name__", None),
    )
    def test_what_a_value_holds_is_read_off_the_layout_of_its_class(self, kind, only_its_dict):
        assert_that(_introspection.holds_only_its_dict(kind)).is_equal_to(only_its_dict)

    def test_the_layout_is_read_off_type_and_not_as_a_metaclass_spells_it(self):
        size = type.__dict__["__basicsize__"].__get__

        class Spelling(type):
            __basicsize__ = property(lambda cls: size(cls) - tuple.__itemsize__)

        class Slotted(metaclass=Spelling):
            __slots__ = ("__dict__", "__weakref__", "code")

            def __init__(self, code):
                self.code = code

        assert_that(Slotted.__basicsize__).is_equal_to(_Weak.__basicsize__)
        assert_that(_introspection.holds_only_its_dict(Slotted)).is_false()
        with pytest.raises(AssertionFailure):
            assert_that([Slotted(1)]).is_equal_to([Slotted(2)], ignore="unrelated")

    def test_a_value_that_is_its_dict_is_still_read_by_it(self):
        space = types.SimpleNamespace
        assert_that([space(id=1, n=1)]).is_equal_to([space(id=2, n=1)], ignore="id")
        verdict, failure = _outcome(
            lambda: assert_that([space(id=1, n=1)]).is_equal_to([space(id=2, n=2)], ignore="id")
        )
        assert_that(verdict).is_equal_to("failed")
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["[0].n"])

    @pytest.mark.parametrize(
        "kind",
        [
            *KINDS,
            type("Queue", (collections.deque,), {}),
            type("Fixed", (frozenset,), {}),
            _Numbers,
            _HalfSlotted,
            _FailedError,
        ],
    )
    def test_it_is_compared_by_what_it_holds(self, kind):
        for held_in, options in (
            (lambda value: [value], {"ignore": "missing"}),
            (lambda value: {"k": value, "n": 1}, {"ignore": ("k", "missing")}),
            (lambda value: {"k": value, "n": 1}, {"include": "k"}),
        ):
            same, other = held_in(kind([1])), held_in(kind([2]))
            assert_that(held_in(kind([1]))).is_equal_to(same, **options)
            assert_that(match.equal_to(same, **options).matches(held_in(kind([1])))).is_true()
            verdict, _ = _outcome(lambda: assert_that(same).is_equal_to(other, **options))  # noqa: B023  # called before the loop moves on
            assert_that(verdict).described_as(f"{kind.__name__} under {options}").is_equal_to("failed")
            assert_that(match.equal_to(other, **options).matches(same)).is_false()

    def test_a_set_of_a_class_of_its_own_at_the_top_is_refused_as_a_set_is(self):
        bag = self.KINDS[2]
        with pytest.raises(TypeError, match="ignore/include requires dict-like objects"):
            assert_that(bag([1])).is_equal_to(bag([2]), ignore="missing")
        with pytest.raises(TypeError, match="ignore/include requires dict-like objects"):
            assert_that({1}).is_equal_to({2}, ignore="missing")


class TestWhatASequenceFailureCopiesIsWhatWasCompared:
    """The diff of a sequence under a key option runs over copies of its elements with the keys left out removed.

    A copy has to stand for the element as the comparison read it: of the class ``strict_types`` compared, and
    whole where its pair was compared whole."""

    def test_a_dict_of_a_class_of_its_own_keeps_the_class_strict_types_compares(self):
        kept = type("Kept", (dict,), {})
        options: dict[str, Any] = {"ignore": "id", "strict_types": True}
        actual, expected = [kept(x=1), 0], [{"x": 1}, 9]
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(verdict).is_equal_to("failed")
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["[0]", "[1]"])
        assert_that(actual[:1]).is_equal_to(expected[:1], ignore="id")
        assert_that(match.equal_to(expected[:1], **options).matches(actual[:1])).is_false()

    def test_so_does_one_a_path_enters(self):
        kept = type("Kept", (dict,), {})
        options: dict[str, Any] = {"ignore": ("a", "missing"), "strict_types": True}
        verdict, failure = _outcome(
            lambda: assert_that({"a": kept(x=1), "b": 0}).is_equal_to({"a": {"x": 1}, "b": 9}, **options)
        )
        assert_that(verdict).is_equal_to("failed")
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["a", "b"])

    def test_a_dict_of_a_class_of_its_own_keeps_its_class_and_its_order(self):
        ordered = type("Ordered", (collections.OrderedDict,), {})
        options: dict[str, Any] = {"ignore": "id", "strict_types": True}
        actual, expected = [ordered(x=1), 0], [collections.OrderedDict(x=1), 9]
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["[0]", "[1]"])
        assert_that(type(failure.diff.entries[0].actual)).is_same_as(ordered)
        nested: dict[str, Any] = {"ignore": ("a", "missing"), "strict_types": True}
        _, failure = _outcome(
            lambda: assert_that({"a": ordered(x=1), "b": 0}).is_equal_to(
                {"a": collections.OrderedDict(x=1), "b": 9}, **nested
            )
        )
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["a", "b"])
        swapped = ordered(y=2, x=1)
        _, failure = _outcome(lambda: assert_that([ordered(x=1, y=2)]).is_equal_to([swapped], ignore="id"))
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("[0]", ["x", "y"], ["y", "x"])]
        )

    def test_a_dict_of_a_class_of_its_own_held_by_a_record_keeps_the_class(self):
        # taken apart, the record's dict was rebuilt plain, and under strict types it equalled a plain dict
        kept = type("Kept", (dict,), {})
        options: dict[str, Any] = {"ignore": "id", "strict_types": True}
        for held_in in (lambda value: [value], lambda value: value):
            actual, expected = held_in(_Record(kept(x=1))), held_in(_Record({"x": 1}))
            verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))  # noqa: B023  # called before the loop moves on
            assert_that(verdict).is_equal_to("failed")
            assert_that(failure.diff.entries).is_length(1)
            assert_that(failure.diff.entries[0].path).ends_with("v")
            assert_that(match.equal_to(expected, **options).matches(actual)).is_false()
            assert_that(actual).is_equal_to(expected, ignore="id")
        looped, plain = _Record(kept(x=1)), _Record({"x": 1})
        looped.next, plain.next = looped, plain
        verdict, _ = _outcome(lambda: assert_that(looped).is_equal_to(plain, **options))
        assert_that(verdict).is_equal_to("failed")

    def test_a_value_under_a_path_compared_whole_is_shown_whole(self):
        class Box:
            """A value with fields that calls itself equal to the number it holds."""

            def __init__(self) -> None:
                self.v = 1

            def __eq__(self, other: object) -> bool:
                return other == 1

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

        options: dict[str, Any] = {"ignore": ("a", "v")}
        assert_that({"a": Box()}).is_equal_to({"a": 1}, **options)
        for actual, expected, row in (
            ({"a": Box(), "b": 0}, {"a": 1, "b": 9}, ("b", 0, 9)),
            ({"a": 1, "b": 9}, {"a": Box(), "b": 0}, ("b", 9, 0)),
        ):
            verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))  # noqa: B023  # called before the loop moves on
            assert_that(verdict).is_equal_to("failed")
            assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
                [row]
            )

    def test_an_element_compared_whole_is_shown_whole(self):
        class Box:
            """A value with fields that calls itself equal to the number it holds."""

            def __init__(self) -> None:
                self.v = 1

            def __eq__(self, other: object) -> bool:
                return other == 1

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

        assert_that([Box()]).is_equal_to([1], ignore="v")
        verdict, failure = _outcome(lambda: assert_that([Box(), 0]).is_equal_to([1, 9], ignore="v"))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("[1]", 0, 9)]
        )


class TestOneVerdictOnEverySurface:
    """What the graphs found on values that hold no cycle: the builder and the matcher answering apart."""

    @pytest.mark.parametrize(
        ("actual", "expected", "options", "equal"),
        [
            ([1.0], [1], {"ignore": "v", "strict_types": True}, False),
            ([True], [1], {"include": "v", "strict_types": True}, False),
            ([{1}], [{1.0}], {"ignore": "v", "strict_types": True}, False),
            ([{1}], [{1}], {"ignore": "v", "strict_types": True}, True),
            ([[1]], [[1.4]], {"ignore": "v", "tolerance": 0.5}, True),
            ([[1]], [[1.6]], {"ignore": "v", "tolerance": 0.5}, False),
            ([(1,)], [(1.4,)], {"include": "v", "tolerance": 0.5}, True),
            ([["a"]], [["A"]], {"ignore": "v", "comparators": {str: _same_case}}, True),
            ([["a"]], [["b"]], {"ignore": "v", "comparators": {str: _same_case}}, False),
        ],
        ids=[
            "a float against an int under strict types",
            "a bool against an int under strict types",
            "a set of an int against a set of a float under strict types",
            "two sets that hold the same under strict types",
            "a nested list within the tolerance",
            "a nested list past the tolerance",
            "a nested tuple within the tolerance",
            "a nested list a comparator holds equal",
            "a nested list a comparator holds apart",
        ],
    )
    def test_an_element_of_a_sequence_under_a_key_option_is_compared_as_the_config_says(
        self, actual, expected, options, equal
    ):
        hard, _ = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(hard).is_equal_to("held" if equal else "failed")
        assert_that(assert_that(actual).check().is_equal_to(expected, **options).passed).is_equal_to(equal)
        assert_that(match.equal_to(expected, **options).matches(actual)).is_equal_to(equal)


@dataclasses.dataclass(eq=False)
class _Opaque:
    """A record Python compares by identity, so two that hold the same differ and no field says why."""

    v: object = 1
    next: object = None


class TestAPairNothingUnderAccountsFor:
    """Where ``==`` holds two values apart and no part of them differs, the pair is the entry."""

    def test_two_records_compared_by_identity(self):
        one, other = _Opaque(), _Opaque()
        verdict, failure = _outcome(lambda: assert_that(one).is_equal_to(other))
        assert_that(verdict).is_equal_to("failed")
        _hold_the_diff(one, other, {}, failure)
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [(".", one, other)]
        )

    @pytest.mark.parametrize(
        ("held_in", "path"),
        [(lambda value: [0, value], "[1]"), (lambda value: {"k": value}, "k"), (lambda value: _Record(value), ".v")],
        ids=["a list", "a dict", "a record"],
    )
    def test_the_pair_is_named_where_it_is_held(self, held_in, path):
        one, other = _Opaque(), _Opaque()
        actual, expected = held_in(one), held_in(other)
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        _hold_the_diff(actual, expected, {}, failure)
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [(path, one, other)]
        )

    def test_under_a_key_option(self):
        one, other = _Opaque(), _Opaque()
        actual, expected = {"k": one, "t": 1}, {"k": other, "t": 2}
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, ignore="t"))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("k", one, other)]
        )

    def test_a_list_against_a_tuple_of_the_same(self):
        verdict, failure = _outcome(lambda: assert_that([1]).is_equal_to((1,)))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [(".", [1], (1,))]
        )

    def test_a_pair_that_holds_itself(self):
        one, other = _Opaque(), _Opaque()
        one.next, other.next = one, other
        verdict, failure = _outcome(lambda: assert_that([one]).is_equal_to([other]))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("[0]", one, other)]
        )

    def test_a_pair_that_leads_back_to_one_that_differs_owes_nothing(self):
        # the lists differ as the dicts that hold them do, and the dicts' own row says how
        actual: dict = {"v": 1, "held": []}
        expected: dict = {"v": 2, "held": []}
        actual["held"].append(actual)
        expected["held"].append(expected)
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("v", 1, 2)]
        )

    @pytest.mark.parametrize("apart", [True, False], ids=["beside another difference", "alone"])
    def test_a_pair_compared_by_identity_that_leads_back_owes_all_the_same(self, apart):
        # the way back accounts for a pair that differs as its ancestor does, and identity is not that
        actual, expected = _Record(_Opaque(), next=0), _Record(_Opaque(), next=1 if apart else 0)
        actual.v.next, expected.v.next = actual, expected
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([(".v", actual.v, expected.v)] + ([(".next", 0, 1)] if apart else []))

    def test_a_pair_of_two_kinds_that_leads_back_owes_all_the_same(self):
        # a list and a tuple differ whatever they hold, so the way back into the root accounts for nothing
        actual: list = [None, 0]
        expected: list = [None, 1]
        actual[0], expected[0] = [actual], (expected,)
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("[0]", actual[0], expected[0]), ("[1]", 0, 1)])

    def test_a_pair_of_two_classes_that_leads_back_owes_all_the_same(self):
        @dataclasses.dataclass
        class Other:
            v: object
            next: object = None
            also: object = None

        actual, expected = _Record(0, _Record(1)), _Record(9, Other(1))
        actual.next.next, expected.next.next = actual, expected
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([(".v", 0, 9), (".next", actual.next, expected.next)])

    def test_a_pair_equal_under_a_config_is_not_one(self):
        # there the walk is the verdict, and two records that hold the same are equal to it
        assert_that([_Opaque()]).is_equal_to([_Opaque()], strict_types=True)


_ENTERING: dict[str, Any] = {"ignore": ("a", "missing")}


class TestAPathEntersAValueThroughItsFields:
    """A key path that goes on into a value reads it by its fields, a mapping's being its keys: so a dict beside a
    record is compared as it is at the top and as an element of a sequence, not by an ``==`` that holds the two
    kinds apart whatever they hold."""

    @pytest.mark.parametrize(
        "mapping",
        [dict, types.MappingProxyType, collections.OrderedDict],
        ids=["a dict", "a mapping proxy", "an ordered dict"],
    )
    @pytest.mark.parametrize("turned", [False, True], ids=["mapping first", "record first"])
    def test_a_mapping_beside_a_record_with_the_same_fields_is_equal(self, mapping, turned):
        pair = [{"a": mapping({"v": 1, "next": None, "also": None})}, {"a": _Record(1)}]
        actual, expected = reversed(pair) if turned else pair
        for options in (_ENTERING, {"include": ("a", "v")}):
            assert_that(actual).is_equal_to(expected, **options)
            assert_that(assert_that(actual).check().is_equal_to(expected, **options).passed).is_true()
            assert_that(match.equal_to(expected, **options).matches(actual)).is_true()

    @pytest.mark.parametrize("turned", [False, True], ids=["mapping first", "record first"])
    def test_a_field_that_differs_is_the_entry(self, turned):
        pair = [{"a": {"v": 2, "next": None, "also": None}}, {"a": _Record(1)}]
        actual, expected = reversed(pair) if turned else pair
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **_ENTERING))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("a.v", 1, 2) if turned else ("a.v", 2, 1)])
        assert_that(match.equal_to(expected, **_ENTERING).matches(actual)).is_false()

    @pytest.mark.parametrize("turned", [False, True], ids=["mapping first", "record first"])
    def test_under_strict_types_the_two_kinds_are_the_entry(self, turned):
        pair = [{"a": {"v": 1, "next": None, "also": None}}, {"a": _Record(1)}]
        actual, expected = reversed(pair) if turned else pair
        options = {**_ENTERING, "strict_types": True}
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, **options))
        assert_that(verdict).is_equal_to("failed")
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["a"])
        assert_that(match.equal_to(expected, **options).matches(actual)).is_false()

    def test_a_key_option_that_does_not_enter_them_leaves_them_to_their_own_equality(self):
        actual, expected = {"a": {"v": 1, "next": None, "also": None}}, {"a": _Record(1)}
        verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected, ignore="missing"))
        assert_that(verdict).is_equal_to("failed")
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("a", actual["a"], expected["a"])])


@dataclasses.dataclass
class _Never:
    """A record whose ``==``, written by hand, answers no whatever it holds."""

    v: object = 1
    next: object = None

    def __eq__(self, other: object) -> bool:
        return False


_installed: dict[str, Any] = {}
exec(
    "def __eq__(self, other):\n    return False\n", _installed
)  # a method that names no file, as the one `dataclasses` writes


@dataclasses.dataclass
class _Installed:
    """A record whose ``==`` was put there by ``exec``: it names no file, as the one `dataclasses` writes does not."""

    v: object = 1
    next: object = None
    __eq__ = _installed["__eq__"]


class _OwnList(list):
    def __eq__(self, other: object) -> bool:
        return False


_Point = collections.namedtuple("_Point", "x y")


def _knot(make: Callable[[], Any], first: object) -> list:
    """A list of *first* and a record that leads back to the list: the lists differ where *first* does."""
    held = [first, make()]
    held[1].next = held
    return held


def _attrs_records() -> tuple[type, type]:
    attrs = pytest.importorskip("attrs", reason="attrs not installed")

    @attrs.define
    class Written:
        v: object = 1
        next: object = None
        low: str = attrs.field(default="a", eq=str.lower)
        out: object = attrs.field(default=None, eq=False)

    @attrs.define(eq=False)
    class Own:
        v: object = 1
        next: object = None

        def __eq__(self, other: object) -> bool:
            return False

    return Written, Own


def _model() -> type:
    pydantic = pytest.importorskip("pydantic", reason="pydantic not installed")

    class Model(pydantic.BaseModel):
        v: Any = 1
        next: Any = None

    return Model


class TestADebtIsDroppedOnlyWhereEqualityReadsTheParts:
    """A pair that leads back to one it is inside differs as that one does, where its ``==`` reads what it holds.

    An ``==`` written by hand may answer for a reason of its own, so its pair stays an entry.
    """

    @pytest.mark.parametrize(
        ("kind", "by_parts"),
        [
            (list, True),
            (tuple, True),
            (dict, True),
            (_Point, True),
            (collections.OrderedDict, True),
            (collections.UserDict, True),
            (collections.ChainMap, True),
            (types.MappingProxyType, True),
            (TakenApart, True),
            (type("Kept", (list,), {}), True),
            (_Record, True),
            (_OwnList, False),
            (collections.Counter, False),
            (_Opaque, False),
            (_Never, False),
            (_Installed, False),
            (object, False),
            (int, False),
        ],
        ids=lambda value: getattr(value, "__name__", None),
    )
    def test_an_equality_is_known_by_being_the_thing_itself(self, kind, by_parts):
        assert_that(compares_by_parts(kind)).is_equal_to(by_parts)
        # asked again, where a class found the first time is answered from what was kept
        assert_that(compares_by_parts(kind)).is_equal_to(by_parts)

    def test_what_attrs_writes_is_known_and_what_is_written_beside_it_is_not(self):
        written, own = _attrs_records()
        assert_that(compares_by_parts(written)).is_true()
        assert_that(compares_by_parts(own)).is_false()

    def test_what_pydantic_defines_is_known(self):
        model = _model()
        assert_that(compares_by_parts(model)).is_true()
        overridden = type("Overridden", (model,), {"__eq__": lambda self, other: False, "__annotations__": {}})
        assert_that(compares_by_parts(overridden)).is_false()

    def test_a_class_dressed_as_an_attrs_one_is_not_known(self):
        pytest.importorskip("attrs", reason="attrs not installed")
        dressed = type("Dressed", (), {"__attrs_attrs__": (), "__eq__": lambda self, other: False})
        assert_that(compares_by_parts(dressed)).is_false()

    def test_a_class_given_another_equality_is_asked_again(self):
        @dataclasses.dataclass
        class Later:
            v: object = 1
            next: object = None

        assert_that(compares_by_parts(Later)).is_true()
        actual, expected = _knot(Later, 0), _knot(Later, 1)
        Later.__eq__ = lambda self, other: False  # ty: ignore[invalid-assignment]  # replacing it is the case
        assert_that(compares_by_parts(Later)).is_false()
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        assert_that([entry.path for entry in failure.diff.entries]).is_equal_to(["[0]", "[1]"])

    def test_a_method_given_other_code_is_asked_again(self):
        @dataclasses.dataclass
        class Rewritten:
            v: object = 1
            next: object = None

        assert_that(compares_by_parts(Rewritten)).is_true()
        vars(Rewritten)["__eq__"].__code__ = (lambda self, other: False).__code__
        assert_that(compares_by_parts(Rewritten)).is_false()

    def test_an_object_that_carries_the_code_and_does_not_run_it_is_not_known(self):
        class Dressed:
            """Not a function: it shows the code `dataclasses` wrote, and answers no when called."""

            __code__ = vars(_Record)["__eq__"].__code__

            def __get__(self, instance: object, owner: type | None = None) -> object:
                return lambda other: False

        @dataclasses.dataclass
        class Forged:
            v: object = None
            next: object = None
            also: object = None

        Forged.__eq__ = Dressed()  # ty: ignore[invalid-assignment]  # replacing it is the case
        assert_that(compares_by_parts(_Record)).is_true()
        assert_that(compares_by_parts(Forged)).is_false()

    def test_a_function_that_closes_over_something_is_not_known(self):
        def closing(answer: bool):
            return lambda self, other: answer

        @dataclasses.dataclass
        class Closed:
            v: object = 1
            __eq__ = closing(False)

        assert_that(compares_by_parts(Closed)).is_false()

    def test_the_keys_attrs_compares_through_are_held_to_being_the_same(self):
        written, _ = _attrs_records()
        generated = vars(written)["__eq__"]
        swapped = {name: (str.upper if value is str.lower else value) for name, value in generated.__globals__.items()}
        assert_that(swapped).is_not_equal_to(dict(generated.__globals__))
        written.__eq__ = types.FunctionType(generated.__code__, swapped, "__eq__")
        assert_that(compares_by_parts(written)).is_false()
        written.__eq__ = generated
        assert_that(compares_by_parts(written)).is_true()

    def test_no_more_than_so_many_classes_are_kept(self, monkeypatch):
        full = dict.fromkeys((type(f"kind{number}", (), {}) for number in range(256)), None)
        monkeypatch.setattr(_introspection, "_COMPARED_BY_PARTS", full)
        fresh = type("Fresh", (list,), {})
        assert_that(compares_by_parts(fresh)).is_true()
        assert_that(full).is_length(256)

    @pytest.mark.parametrize("make", [_Opaque, _Never, _Installed], ids=["by identity", "written", "installed"])
    def test_a_pair_held_apart_for_a_reason_of_its_own_is_an_entry(self, make):
        for first in (1, 0):
            actual, expected = _knot(make, 0), _knot(make, first)
            verdict, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))  # noqa: B023  # called before the loop moves on
            assert_that(verdict).is_equal_to("failed")
            _hold_the_diff(actual, expected, {}, failure)
            rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
            ahead = [("[0]", 0, 1)] if first else []
            assert_that(rows).is_equal_to([*ahead, ("[1]", actual[1], expected[1])])

    def test_an_attrs_record_with_an_equality_of_its_own_is_an_entry(self):
        _, own = _attrs_records()
        actual, expected = _knot(own, 0), _knot(own, 1)
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("[0]", 0, 1), ("[1]", actual[1], expected[1])])

    @pytest.mark.parametrize(
        "kind_of_record",
        [lambda: _Record, lambda: _attrs_records()[0], _model],
        ids=["a dataclass", "an attrs record", "a model"],
    )
    def test_a_record_that_differs_as_its_ancestor_does_is_none(self, kind_of_record):
        make = kind_of_record()
        actual, expected = _knot(make, 0), _knot(make, 1)
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("[0]", 0, 1)])

    @pytest.mark.parametrize("plain", [False, True], ids=["against one of its class", "against a plain list"])
    def test_a_list_of_a_class_with_an_equality_of_its_own_is_an_entry(self, plain):
        def knot(first, kind):
            outer: list = [first]
            outer.append(kind([outer]))
            return outer

        actual, expected = knot(0, _OwnList), knot(1, list if plain else _OwnList)
        _, failure = _outcome(lambda: assert_that(actual).is_equal_to(expected))
        rows = [(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]
        assert_that(rows).is_equal_to([("[0]", 0, 1), ("[1]", actual[1], expected[1])])
