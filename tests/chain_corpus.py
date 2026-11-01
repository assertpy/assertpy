"""The typing corpus: the chains the chain model takes, breadth first and bounded, written as typed calls.

Generated from the model's transition table and nothing else: which operations and pivots apply to which
kind of value.  Arguments are fixed literals per operation rather than drawn, so the same table always
writes the same text, byte for byte, and a change to how the machine samples cannot move it.  That is
why the text is written where the checkers read it and not kept: only what they said about it is.

A view is a subject kind followed by up to two pivots, or a function followed by an expectation and the
call.  Every view is written bare and once per operation that applies to it, positive and negated, with
the verdict last: a verdict hands back the view it was asked on, so a second would say nothing the first
did not.  Each chain is pinned on up to four surfaces: the value at its end, `check()` on its verdict, a
polled chain's `.val` and an awaited one's `.value`.  The pin is the type plain Python gives that value.

    python -m tests.chain_corpus    record what the four checkers say, into the baseline
"""

from __future__ import annotations

import json
import pathlib
import tempfile

from tests import chain_model as model
from tests import typing_harness

BASELINE = pathlib.Path(__file__).resolve().parent / "typing_chain_corpus_baseline.json"

STATIC = {
    "int": "int",
    "float": "float",
    "bool": "bool",
    "none": "None",
    "str": "str",
    "bytes": "bytes",
    "list": "list[int]",
    "tuple": "tuple[int, ...]",
    "set": "set[int]",
    "dict": "dict[str, int]",
    "records": "list[dict[str, int]]",
    "nested": "list[list[int]]",
    "datetime": "datetime.datetime",
    "function": "Callable[[int], int]",
}
LITERAL = {
    "int": "1",
    "float": "1.5",
    "bool": "True",
    "none": "None",
    "str": '"a"',
    "bytes": 'b"a"',
    "list": "[1]",
    "tuple": "(1,)",
    "set": "{1}",
    "dict": '{"a": 1}',
    "records": '[{"id": 1, "rank": 1}]',
    "nested": "[[1]]",
    "datetime": "datetime.datetime(2026, 1, 1)",
    "function": "call_me",
    "exception": 'ValueError("x")',
}
ELEMENT = {
    "str": ("str", "str"),
    "bytes": ("int", "int"),
    "list": ("int", "int"),
    "tuple": ("int", "int"),
    "set": ("int", "int"),
    "dict": ("str", "str"),
    "records": ("dict", "dict[str, int]"),
    "nested": ("list", "list[int]"),
}
"""What iterating a kind yields, as the kind it is and the type it has."""

OWN_CLASS = {
    "int": "int",
    "float": "float",
    "bool": "bool",
    "none": "type(None)",
    "str": "str",
    "bytes": "bytes",
    "list": "list",
    "tuple": "tuple",
    "set": "set",
    "dict": "dict",
    "records": "list",
    "nested": "list",
    "datetime": "datetime.datetime",
}


def _item(kind: str) -> str:
    return '"a"' if kind in ("str", "dict") else 'b"a"' if kind == "bytes" else LITERAL[ELEMENT[kind][0]]


def _number(kind: str) -> str:
    return "1.5" if kind == "float" else "1"


def _same(kind: str) -> str:
    return LITERAL[kind]


ARGUMENTS = {
    "is_equal_to": _same,
    "is_not_equal_to": _same,
    "is_same_as": _same,
    "is_not_same_as": _same,
    "is_instance_of": lambda kind: OWN_CLASS[kind],
    "is_type_of": lambda kind: OWN_CLASS[kind],
    "is_in": lambda kind: f"{LITERAL[kind]}, {LITERAL[kind]}",
    "is_not_in": lambda kind: f"{LITERAL[kind]}, {LITERAL[kind]}",
    "satisfies": lambda _kind: "bool",
    "is_greater_than": _number,
    "is_greater_than_or_equal_to": _number,
    "is_less_than": _number,
    "is_less_than_or_equal_to": _number,
    "is_between": lambda kind: f"{_number(kind)}, 2",
    "is_not_between": lambda kind: f"{_number(kind)}, 2",
    "is_close_to": lambda kind: f"{_number(kind)}, 1",
    "is_not_close_to": lambda kind: f"{_number(kind)}, 1",
    "is_divisible_by": lambda _kind: "2",
    "is_length": lambda _kind: "1",
    "is_length_between": lambda _kind: "0, 2",
    "contains": _item,
    "does_not_contain": _item,
    "starts_with": _item,
    "ends_with": _item,
    "matches": lambda _kind: '"a"',
    "does_not_match": lambda _kind: '"a"',
    "is_equal_to_ignoring_case": lambda _kind: '"A"',
    "contains_ignoring_case": lambda _kind: '"A"',
    "contains_only": _item,
    "contains_exactly": _item,
    "contains_sequence": _item,
    "is_subset_of": _same,
    "all_satisfy": lambda _kind: "bool",
    "any_satisfy": lambda _kind: "bool",
    "none_satisfy": lambda _kind: "bool",
    "contains_key": lambda _kind: '"a"',
    "does_not_contain_key": lambda _kind: '"a"',
    "contains_value": lambda _kind: "1",
    "does_not_contain_value": lambda _kind: "1",
    "contains_entry": lambda _kind: '{"a": 1}',
    "does_not_contain_entry": lambda _kind: '{"a": 1}',
    "is_before": lambda _kind: LITERAL["datetime"],
    "is_after": lambda _kind: LITERAL["datetime"],
}
"""A fixed argument list per operation, written for the kind it is asked of.  No entry means none."""

PIVOT_CALLS = {
    "first": ".first()",
    "last": ".last()",
    "element": ".element(0)",
    "single": ".single()",
    "mapped": ".mapped(double)",
    "filtered_on": ".filtered_on(is_even_int)",
    "flat_mapped": ".flat_mapped(identity)",
    "extracting": '.extracting("id")',
}

EXPECTATIONS = (
    (".raises(ValueError).when_called_with(1)", "str", "str"),
    (".raises(ValueError).when_called_with(1).raised()", "exception", "ValueError"),
    (".does_not_raise(ValueError).when_called_with(1).returned()", "int", "int"),
)
"""The calls a function view can take: ``(chain, kind landed on, its type)``."""


def _element_type(kind: str, static: str) -> str:
    """What iterating a value of *static* yields, read off the type rather than the kind.

    A kind's element is not always its type's: `extracting()` lands on a list of the kind the model
    knows, typed `list[Any]` because a field name is only a string to a checker.
    """
    if kind in ("str", "bytes"):
        return ELEMENT[kind][1]
    inner = static[static.index("[") + 1 : -1]
    depth = 0
    for index, character in enumerate(inner):
        depth += {"[": 1, "]": -1}.get(character, 0)
        if character == "," and depth == 0:
            return inner[:index]
    return inner


def _landing(pivot: str, kind: str, static: str) -> tuple[str, str]:
    """The kind and type a pivot lands on."""
    element_kind, element_type = ELEMENT[kind][0], _element_type(kind, static)
    if pivot in ("first", "last", "element", "single"):
        return element_kind, element_type
    if pivot == "flat_mapped":
        return "list", element_type
    if pivot == "extracting":
        return "list", "list[Any]"
    if pivot == "mapped":
        return "list", "list[int]"
    return "list", f"list[{element_type}]"


def _as_held(kind: str, static: str) -> str:
    """What `.value` hands back on the view `assert_that()` gives a subject of *kind*, where that is not *static*.

    Both are the library's answer rather than a gap: a sequence view is one view over four containers,
    and the callable view is written over what the call returns, not over its parameters.
    """
    if kind in ("list", "tuple", "set", "records", "nested"):
        return "list[{0}] | tuple[{0}, ...] | set[{0}] | frozenset[{0}]".format(ELEMENT[kind][1])
    return "Callable[..., int]" if kind == "function" else static


def views(depth: int = 2) -> list[tuple[str, str, str, str]]:
    """``(subject kind, view kind, view type, chain)`` for every view, in a fixed order."""
    found = [(kind, kind, STATIC[kind], "") for kind in STATIC]
    found += [("function", kind, static, chain) for chain, kind, static in EXPECTATIONS]
    frontier = found[: len(STATIC)]
    for _ in range(depth):
        reached = [
            (subject, *_landing(pivot.name, kind, static), chain + PIVOT_CALLS[pivot.name])
            for subject, kind, static, chain in frontier
            for pivot in model.PIVOTS
            if kind in pivot.kinds
        ]
        found += reached
        frontier = reached
    return found


def _call(op: model.Op, kind: str) -> str:
    maker = ARGUMENTS.get(op.name)
    return f".{op.name}({maker(kind) if maker else ''})"


def verdicts(kind: str, *, pivoted: bool) -> list[str]:
    """The operations asked of a view of *kind*, with their fixed arguments.

    Every one that applies, positive and negated, on a view no pivot reached.  After a pivot, equality
    and the first operation only that kind has: whether the landing view still carries its own surface is
    the question there, and the signatures themselves were asked of the kind already.
    """
    applicable = [
        op
        for op in model.OPS
        if kind in op.kinds and not (kind in ("function", "exception") and op.name in ("is_instance_of", "is_type_of"))
    ]
    if not pivoted:
        return [written for op in applicable for written in (_call(op, kind), ".not_" + _call(op, kind))]
    own = [op for op in applicable if op.kinds != model.ALL][:1]
    return [_call(op, kind) for op in [model.OPS_BY_NAME["is_equal_to"], *own]]


HEADER = '''"""Generated by `python -m tests.chain_corpus` from the chain model.  Do not edit."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any, TypeVar, assert_type

from assertpy import assert_that
from assertpy.outcome import AssertionOutcome

_T = TypeVar("_T")


def call_me(number: int) -> int:
    return number * 2


def double(item: int) -> int:
    return item * 2


def is_even_int(item: object) -> bool:
    return isinstance(item, int) and item % 2 == 0


def identity(item: _T) -> _T:
    return item


def every_checker_refuses_this(number: int) -> None:
    assert_that(number).starts_with("x")  # case: witness
'''


def render() -> str:
    """The corpus, as the text of the file."""
    lines = [HEADER]
    number = 0
    for subject, kind, static, chain in views():
        for verdict in ["", *verdicts(kind, pivoted=any(call in chain for call in PIVOT_CALLS.values()))]:
            number += 1
            stem = f"c{number:04d}"
            written = chain + verdict
            lines.append(f"\n\ndef {stem}(subject: {STATIC[subject]}) -> None:")
            held = static if chain else _as_held(kind, static)
            lines.append(f"    assert_type(assert_that(subject){written}.value, {held})  # case: {stem}-direct")
            if verdict:
                checked = ".check()" + verdict
                if verdict.startswith(".not_."):
                    checked = ".check().not_." + verdict.removeprefix(".not_.")
                outcome = f"assert_that(subject){chain}{checked}"
                lines.append(f"    assert_type({outcome}, AssertionOutcome)  # case: {stem}-check")
            if written:
                polled = f"assert_that(lambda: subject).eventually_sync(){written}.val"
                lines.append(f"    assert_type({polled}, {static})  # case: {stem}-poll")
                lines.append(f"\n\nasync def {stem}_awaited(subject: {STATIC[subject]}) -> None:")
                awaited = f"(await assert_that(lambda: subject).eventually(){written}).value"
                lines.append(f"    assert_type({awaited}, {static})  # case: {stem}-await")
    return "\n".join(lines) + "\n"


def disagreements(folder: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    """Case to the codes each checker reported for it, for every case any checker reported at all.

    The file is written into *folder* and read from the project root, where the imports resolve.
    pyrefly is handed the project's configuration by name: outside the project it falls back to `basic`
    without a word.
    """
    corpus = folder / "typing_chain_corpus.py"
    corpus.write_bytes(render().encode("utf-8"))
    found = {
        "ty": typing_harness.ty(corpus, "--python-version", "3.14"),
        "mypy": typing_harness.mypy(corpus, "--python-version", "3.14"),
        "pyright": typing_harness.pyright(corpus, "--pythonversion", "3.14"),
        "pyrefly": typing_harness.pyrefly(corpus, "--config", str(typing_harness.ROOT / "pyrefly.toml")),
    }
    return {
        case: {checker: sorted(codes) for checker, codes in codes_by_checker.items() if codes}
        for case, codes_by_checker in sorted(typing_harness.by_case(found, corpus).items())
        if any(codes_by_checker.values())
    }


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as scratch:
        recorded = json.dumps(disagreements(pathlib.Path(scratch)), indent=1, sort_keys=True) + "\n"
    BASELINE.write_bytes(recorded.encode("utf-8"))
