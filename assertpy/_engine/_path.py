"""Where a diff entry sits, in both the forms its two readers need.

`DiffEntry.path` is written for a person and is lossy on purpose: a mapping key goes through ``str()``,
so ``{3: ...}`` and ``{"3": ...}`` land on the same text, and a key holding a dot or a bracket cannot be
read back out.  That is the right trade for a message and the wrong one for anything that wants to walk
back into the value, which is what `DiffEntry.steps` is for.

Both forms are carried by one object so they cannot drift.  Nine producers build paths, and each of them
would otherwise have written the text and the steps separately, twice, in agreement only by hand.

The rendering rules are **not** uniform across producers and are not made uniform here.  A mapping key
renders bare at the root (``b``) while a field renders dotted (``.b``), because a top-level dict is
reported by `HelpersMixin._dict_err()` with bare keys and has been since before this file existed.
Each hop keeps its own rule, in one place, instead of at 35 call sites.

Building a path is deferred to the point where an entry is actually produced.  The walkers used to
format one per child before deciding whether the child differed, so a sequence of a thousand equal
elements paid for a thousand strings nobody read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..errors import DiffEntry, Step, _safe_str

__tracebackhide__ = True


_Joint = Literal["append", "dotted", "reset"]
"""How a hop's text meets the text before it: after it, after a dot unless nothing came before, or in its place."""


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class _Path:
    """A location inside a compared value, as rendered text plus the steps that reached it.

    Not a `NamedTuple`, though it is a pair: ``index`` and ``count`` are already taken by ``tuple``, and
    a hop named ``index`` is the one this is used for most.  It was tried, and it measured the same.

    Held as one hop and the path it was taken from, and read out only when an entry is made.  A node's path
    stays alive while its children are walked, so holding the whole text and every step at each hop made the
    paths of a walk quadratic in its depth: 48 MB for three thousand levels, against 0.6 MB held as hops.
    """

    piece: str = ""
    step: Step | None = None
    parent: _Path | None = None
    joint: _Joint = "reset"

    def key(self, key: object) -> _Path:
        """Into a mapping.  Bare at the root, dotted below it, and the key itself is kept unstringified."""
        rendered = _safe_str(key)
        if type(self.piece) is not str:
            text = self.text
            return _Path(f"{text}.{rendered}" if text else rendered, Step("key", key), self)
        return _Path(rendered, Step("key", key), self, "dotted")

    def attr(self, name: str, *, dotted_at_root: bool = True) -> _Path:
        """Into a field of a dataclass, namedtuple, attrs class or model.

        ``dotted_at_root`` is not a style knob.  The diff walkers render a root-level field as ``.name``
        and the leaf walker renders it as ``name``, and both are load-bearing: the first matches how the
        dict path has rendered nested keys since before either existed, the second feeds messages that
        name a field of the value under test.  Below the root the two agree.
        """
        if type(name) is not str or type(self.piece) is not str:
            text = self.text
            return _Path(f"{text}.{name}" if text or dotted_at_root else name, Step("attr", name), self)
        if dotted_at_root:
            return _Path(f".{name}", Step("attr", name), self, "append")
        return _Path(name, Step("attr", name), self, "dotted")

    def index(self, index: int) -> _Path:
        """Into a position both sequences share."""
        if type(self.piece) is not str:
            return _Path(f"{self.text}[{index}]", Step("index", index), self)
        return _Path(f"[{index}]", Step("index", index), self, "append")

    def side_index(self, side: Literal["actual", "expected"], index: int) -> _Path:
        """Into a position only one sequence has, once alignment has shifted the two apart."""
        if type(self.piece) is not str:
            return _Path(f"{self.text}{side}[{index}]", Step("index", index, side=side), self)
        return _Path(f"{side}[{index}]", Step("index", index, side=side), self, "append")

    def line(self, number: int) -> _Path:
        """Into one line of a text or bytes diff, numbered from 1."""
        return _Path(f"line {number}", Step("line", number), self)

    def member(self, item: object, label: str) -> _Path:
        """Into a member of a set, which has no position to name it by.

        The text stays the label the set renderer groups on (``extra`` / ``missing``), because a member
        has no coordinate to print.  The step carries the member itself, which is the only handle on it.
        """
        return _Path(label, Step("item", item), self)

    @property
    def text(self) -> str:
        """The location as a person reads it."""
        return self._read()[0]

    def _read(self) -> tuple[str, tuple[Step, ...]]:
        """Both forms of the location: the text joined from the nearest hop that starts it, the steps from the root.

        A hop that starts the text holds it whole.  Every hop where something other than an exact `str` meets the
        text is one: its text is worked out when it is taken, by 2.28.0's own f-string, whose ``__format__``,
        ``__bool__`` and order a `str` subclass can tell apart from a join.  Joining is only ever done over exact
        strings, where the two agree.
        """
        parent = self.parent
        if parent is _ROOT and self.step is not None:
            # one hop from the root reads as the hop itself: the join below cost such an entry 420 ns more
            return self.piece, (self.step,)
        hops: list[_Path] = []
        hop: _Path | None = self
        while hop is not None:
            hops.append(hop)
            hop = hop.parent
        steps = tuple(hop.step for hop in reversed(hops) if hop.step is not None)
        start = next(position for position, hop in enumerate(hops) if hop.joint == "reset")
        if start == 0:
            return self.piece, steps
        pieces = [hops[start].piece]
        written = bool(pieces[0])
        for hop in reversed(hops[:start]):
            if hop.joint == "dotted" and written:
                pieces.append(".")
            pieces.append(hop.piece)
            written = written or bool(hop.piece)
        return "".join(pieces), steps

    def entry(
        self,
        *,
        actual: object = None,
        expected: object = None,
        absent: Literal["actual", "expected"] | None = None,
    ) -> DiffEntry:
        """A `DiffEntry` at this location, carrying both forms of it."""
        text, steps = self._read()
        return DiffEntry(path=text, steps=steps, actual=actual, expected=expected, absent=absent)

    def leaf_entry(
        self,
        *,
        actual: object = None,
        expected: object = None,
        absent: Literal["actual", "expected"] | None = None,
    ) -> DiffEntry:
        """A `DiffEntry` for the whole value, whose text at the root is ``.`` rather than empty."""
        text, steps = self._read()
        return DiffEntry(path=text or ".", steps=steps, actual=actual, expected=expected, absent=absent)


_ROOT: _Path = _Path()
"""The value under comparison itself, before any hop into it."""
