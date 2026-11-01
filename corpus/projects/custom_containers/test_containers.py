"""Containers the consumer wrote, not the ones Python ships.

This is the shape that refused every narrowing tried on the selector and filter types: a mapping whose
`__getitem__` accepts something unhashable, a sequence that is not a `list`, a mapping proxy.  Each
narrowing looked safe against builtin containers and broke here.
"""

from __future__ import annotations

import typing
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType

from assertpy import assert_that


class Registry(Mapping[str, int]):
    """A mapping of somebody else's making, with the interface and nothing more."""

    def __init__(self, entries: dict[str, int]) -> None:
        self._entries = entries

    def __getitem__(self, key: str) -> int:
        return self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


class Page(Sequence[str]):
    """A sequence that is not a list, which is how paginated results usually arrive."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    @typing.overload
    def __getitem__(self, index: int) -> str: ...

    @typing.overload
    def __getitem__(self, index: slice) -> Sequence[str]: ...

    def __getitem__(self, index: int | slice) -> str | Sequence[str]:
        return self._lines[index]

    def __len__(self) -> int:
        return len(self._lines)


def test_a_user_mapping_answers_the_mapping_assertions() -> None:
    registry = Registry({"alpha": 1, "beta": 2})
    assert_that(registry).is_length(2)
    assert_that(dict(registry)).contains_key("alpha").contains_value(2)


def test_a_user_sequence_answers_the_collection_assertions() -> None:
    page = Page(["first", "second"])
    assert_that(list(page)).is_length(2).contains("first")
    assert_that(list(page)).filtered_on(lambda line: line.startswith("s")).is_equal_to(["second"])


def test_a_mapping_proxy_is_accepted_where_a_mapping_is() -> None:
    proxy = MappingProxyType({"name": "alice", "role": "admin"})
    assert_that(dict(proxy)).contains_key("name")
    rows = [{"name": "alice", "role": "admin"}, {"name": "bob", "role": "user"}]
    assert_that(rows).extracting("name", filter=proxy).is_equal_to(["alice"])


def test_selectors_that_are_not_strings_still_work() -> None:
    rows = [(1, "alice"), (2, "bob")]
    assert_that(rows).extracting(0).is_equal_to([1, 2])
    assert_that(rows).extracting(-1).is_equal_to(["alice", "bob"])
    assert_that(rows).extracting(slice(0, 2)).is_length(2)
    keyed = [{("group", "name"): "alice"}]
    assert_that(keyed).extracting(("group", "name")).is_equal_to(["alice"])


def test_a_one_shot_iterable_is_read_once() -> None:
    assert_that(list(iter([1, 2, 3]))).is_length(3)
    assert_that([value for value in range(4) if value]).is_equal_to([1, 2, 3])


def test_subset_against_containers_of_our_own() -> None:
    assert_that(["first"]).is_subset_of(Page(["first", "second"]))
    assert_that({"alpha": 1}).is_subset_of(Registry({"alpha": 1, "beta": 2}))
    assert_that(b"ab").is_subset_of(bytearray(b"abc"))
