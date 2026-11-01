"""Maximum pairing between two sides, for every assertion that says "these each, in any order"."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

__tracebackhide__ = True


def maximum_pairing(candidates: Sequence[set[int]]) -> dict[int, int]:
    """As many entries paired with distinct options as can be, returned as ``{option: entry}``.

    Kuhn's algorithm: every entry takes a free option first, and each one left over then tries to
    displace an owner along a chain of alternatives.
    """
    paired: dict[int, int] = {}
    unpaired = []
    for entry, options in enumerate(candidates):
        free = next((index for index in options if index not in paired), None)
        if free is None:
            unpaired.append(entry)
        else:
            paired[free] = entry
    return completed_pairing(paired, unpaired, candidates.__getitem__)


def completed_pairing(
    paired: dict[int, int], unpaired: Iterable[int], options_of: Callable[[int], Iterable[int]]
) -> dict[int, int]:
    """*paired*, any valid pairing, grown to a maximum one by the entries it left out, and returned.

    An entry no displacement reaches now cannot be reached later, so each is tried once.  *options_of* is
    asked only for the entries a chain of displacements meets, which lets a caller work them out on demand.
    """
    for entry in unpaired:
        _augmented(entry, options_of, paired)
    return paired


def _augmented(entry: int, options_of: Callable[[int], Iterable[int]], paired: dict[int, int]) -> bool:
    """Whether one entry can be paired by displacing others, updating `paired` when it can.

    Iterative, because the chain of displacements is as long as the input is wide rather than as deep:
    1100 entries against 1100 options every one of them accepts recursed past the limit and reported a
    `RecursionError` for a pairing that exists.
    """
    seen: set[int] = set()
    path: list[tuple[int, Iterator[int]]] = [(entry, iter(options_of(entry)))]
    taken: list[int] = []
    while path:
        options = path[-1][1]
        for index in options:
            if index in seen:
                continue
            seen.add(index)
            taken.append(index)
            if index not in paired:
                for step, (displaced, _) in reversed(list(enumerate(path))):
                    paired[taken[step]] = displaced
                return True
            path.append((paired[index], iter(options_of(paired[index]))))
            break
        else:
            path.pop()
            if taken:
                taken.pop()
    return False
