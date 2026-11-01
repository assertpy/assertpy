from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field
from types import UnionType
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeAlias

from ._engine._introspection import class_name, kind_of

if TYPE_CHECKING:
    from collections.abc import Callable

    from .outcome import AssertionOutcome, Requirement


def _safe_repr(value: object) -> str:
    """``repr(value)`` as an exact `str`, with any `Exception` from a broken ``__repr__`` turned into a marker.

    Error rendering must survive a broken user ``__repr__``.  An interrupt still propagates.
    """
    try:
        return str.__str__(repr(value))  # a `__repr__` may return a `str` subclass whose own methods raise
    except Exception:  # any user exception here must not shadow the assertion failure being rendered
        # the class a value taken apart was read from, since that is the one whose `__repr__` raised
        return f"<unreprable {class_name(kind_of(value))}>"


def _safe_str(value: object) -> str:
    """``str(value)`` as an exact `str`, falling back to `_safe_repr` on any `Exception`."""
    try:
        return str.__str__(str(value))
    except Exception:
        return _safe_repr(value)


def _capped_format(value: object) -> str:
    """``f"{value}"`` as an exact `str`, falling back to `_safe_repr` on any `Exception`.

    Not `_safe_str`: ``format()`` and ``str()`` disagree on a ``numpy.float32`` and, below 3.12, on a mixed-in
    enum, so an operand a message interpolated keeps the text it always had.  Capped (`_ends_kept`): every use
    is an operand in a message.
    """
    return _ends_kept(_formatted(value))


def _formatted(value: object) -> str:
    try:
        # a lone field hands back what `__format__` returned, which may be a `str` subclass formatting itself again
        return str.__str__(f"{value}")
    except Exception:
        return _safe_repr(value)


def _ends_kept(text: str) -> str:
    """*text* as a message prints a value: whole up to 4000 characters, past that its two ends.

    Whole, a value of 300 rows put 15 000 characters ahead of the predicate the message is about.  Both ends
    and not the head alone, since ``ends_with`` is about the end and a container closes there.
    """
    if len(text) <= 4000 or _WHOLE_VALUES:
        return text
    return f"{text[:3000]}... ({len(text) - 4000} more chars) ...{text[-1000:]}"


def _capped(value: object) -> str:
    """`_safe_str` of a value a message prints, capped (`_ends_kept`)."""
    return _ends_kept(_safe_str(value))


def _capped_repr(value: object) -> str:
    """`_safe_repr` of a value a message prints, capped (`_ends_kept`)."""
    return _ends_kept(_safe_repr(value))


def _parted(actual_text: str, other_text: str, at: int, other_at: int | None = None) -> tuple[str, str]:
    """Two texts a message holds against each other: whole up to 4000 characters, past that cut where they part.

    *at* is where the first parts from the second by the rule of the assertion that held them, and *other_at*
    the same place in the second where the two are not read in step.  Capped by their ends, two long texts
    that part in the middle read the same on both sides, and cut at the first raw difference a comparison
    that ignores case or spacing showed a difference it ignores.
    """
    return _around(actual_text, at), _around(other_text, at if other_at is None else other_at)


def _around(text: str, at: int) -> str:
    """*text* whole up to 4000 characters, past that the 4000 around *at*, with what is left out counted each side."""
    if len(text) <= 4000 or _WHOLE_VALUES:
        return text
    start = max(0, min(at - 2000, len(text) - 4000))
    after = len(text) - start - 4000
    before = f"({start} more chars) ..." if start else ""
    return f"{before}{text[start : start + 4000]}{f'... ({after} more chars)' if after else ''}"


def _callable_name(value: object) -> str:
    """A display name for a callable, tolerating those without ``__name__`` (partials, instances)."""
    return getattr(value, "__name__", None) or _safe_repr(value)


def _type_expression_name(expected: object) -> str:
    """A readable name for a type expression, on every Python this package supports.

    ``__name__`` is absent on a union below 3.14 and on a tuple of types on every version, so reading
    it directly turns a failure message into an ``AttributeError`` - raised on the failure path, which
    is the worst place for it.  ``str()`` renders a union as ``int | str`` verbatim, which also reads
    better than the bare ``Union`` that 3.14 started reporting.

    A tuple is the third thing ``isinstance`` accepts, and its ``str()`` is a wall of ``<class '...'>``;
    naming its members is what the reader is after.
    """
    if isinstance(expected, tuple):
        return ", ".join(_type_expression_name(member) for member in expected)
    if isinstance(expected, UnionType):
        return " | ".join(_type_expression_name(member) for member in expected.__args__)
    return expected.__name__ if isinstance(expected, type) else str(expected)


def _truncated(text: str, limit: int | None = None) -> str:
    """Cap *text* for embedding into a failure message; normal-sized values stay byte-identical.

    Bounds only the rendered message: the structured payload (`AssertionFailure.actual` /
    ``.expected`` / ``.diff``) always keeps the full data.  With no *limit* given the text is a value of a
    message, cut at 4000 characters and printed whole where `_WHOLE_VALUES` says so.
    """
    if limit is None:
        if _WHOLE_VALUES:
            return text
        limit = 4000
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text) - limit} more chars)"


def _disambiguated(actual: object, other: object) -> tuple[str, str]:
    """Render two *unequal* values, tagging each with its ``:type`` when their plain reprs would collide.

    So ``is_equal_to`` on ``"1"`` vs ``1`` reads ``<1:str>`` / ``<1:int>`` instead of a baffling
    ``<1>`` / ``<1>``, ``but was not`` - the difference is the type, and now the message says so.
    Two classes of one name are told apart by their modules.
    """
    actual_str, other_str = _truncated(_safe_str(actual)), _truncated(_safe_str(other))
    if actual_str == other_str:
        names = _class_names(actual, other) or (class_name(type(actual)), class_name(type(other)))
        return f"{actual_str}:{names[0]}", f"{other_str}:{names[1]}"
    return actual_str, other_str


def _class_names(actual: object, expected: object) -> tuple[str, str] | None:
    """What tells the classes of two values apart: their names, or their modules too where the names are one.

    ``None`` for two values of one class, and for two classes nothing a reader would see tells apart.  A value
    taken apart for a comparison answers with the class it was read from.
    """
    one, other = kind_of(actual), kind_of(expected)
    if one is other:
        return None
    names = class_name(one), class_name(other)
    if names[0] != names[1]:
        return names
    qualified = f"{_module_name(one)}.{names[0]}", f"{_module_name(other)}.{names[1]}"
    return qualified if qualified[0] != qualified[1] else None


def _module_name(kind: type) -> str:
    """The module a class says it is of, read off the slot, or ``?`` for a class made without one."""
    try:
        return _safe_str(type.__dict__["__module__"].__get__(kind))
    except AttributeError:
        return "?"


def _told_apart(actual_text: str, expected_text: str, actual: object, expected: object) -> tuple[str, str]:
    """Two renderings of a pair, each followed by ``:class`` where they read alike and the classes differ.

    A row of two sides that print the same says nothing, and the reader takes it for a fault of the diff: a dict
    of a class of its own against a plain one under ``strict_types``, two records of two modules' ``Row``.
    """
    if actual_text != expected_text:
        return actual_text, expected_text
    names = _class_names(actual, expected)
    if names is None:
        return actual_text, expected_text
    return f"{actual_text}:{names[0]}", f"{expected_text}:{names[1]}"


_JsonSafe: TypeAlias = bool | int | float | str | list["_JsonSafe"] | dict[str, "_JsonSafe"] | None
"""Declared rather than inferred: a recursive return type is resolved per call site, and moving one
call moved two unrelated diagnostics in another module.

Only the recursive reference is quoted.  Written as one string, ty ignores the alias and reads the
return as `Divergent`, and a misuse of the result went uncaught."""


def _json_safe(value, _depth=0, _seen=None) -> _JsonSafe:
    """Convert *value* to JSON-native data for an attachment: typed where possible, bounded and total.

    Scalars and containers pass through as real JSON values so the Allure viewer renders a tree and
    consumers can parse them.  Everything else degrades to a marked fallback instead of failing the
    attachment: ``{"__repr__": ...}`` for non-JSON values (objects, datetimes, non-finite floats,
    integers too long to print, values whose own methods raise, cycles, over-deep nesting), the snapshot
    codec's ``{"__type__": "set", "__data__": [...]}`` envelope for sets, and `_truncated` caps on strings
    and container sizes.

    Total means an `Exception` from a value's own method degrades that value alone.  An interrupt such as
    `KeyboardInterrupt` is not a value's failure and still propagates.  An object built to make the
    conversion's own reads raise, such as a key whose `__class__` property raises, can still cost the
    container holding it: that is a boundary, not a goal.
    """
    try:
        return _json_native(value, _depth, set() if _seen is None else _seen)
    except Exception:  # a value's own method raised, and one value must not cost the whole attachment
        return {"__repr__": _truncated(_safe_repr(value), 4000)}


def _json_native(value, depth: int, seen: set[int]) -> _JsonSafe:
    """The conversion itself, which `_json_safe` keeps total by catching what a value's own methods raise."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        int.__repr__(value)  # raises past `sys.get_int_max_str_digits()`, where `json.dumps` would
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"__repr__": repr(value)}
    if isinstance(value, str):
        return _truncated(value, 4000)
    if depth >= 6:
        return {"__repr__": _truncated(_safe_repr(value), 4000)}
    if id(value) in seen:
        return {"__repr__": "<circular ref>"}
    if isinstance(value, dict):
        inner = seen | {id(value)}
        items = list(value.items())
        shown, dropped = items[:100], max(0, len(items) - 100)
        if any(not isinstance(key, str) for key in value):
            # the codec's own envelope: rendered as text, `1` and `"1"` were the same key and one was lost
            envelope: dict[str, _JsonSafe] = {
                "__type__": "dict",
                "__data__": [
                    [_json_safe(key, depth + 1, inner), _json_safe(val, depth + 1, inner)] for key, val in shown
                ],
            }
            if dropped:
                envelope["__truncated__"] = f"... and {dropped} more keys"
            return envelope
        rendered: dict[str, _JsonSafe] = {str.__str__(key): _json_safe(val, depth + 1, inner) for key, val in shown}
        if dropped:
            rendered["__truncated__"] = f"... and {dropped} more keys"
        return rendered
    if isinstance(value, (list, tuple)):
        inner = seen | {id(value)}
        out = [_json_safe(item, depth + 1, inner) for item in value[:100]]
        if len(value) > 100:
            out.append({"__repr__": f"... and {len(value) - 100} more items"})
        return out
    if isinstance(value, (set, frozenset)):
        items = sorted(value, key=_safe_repr)
        return {"__type__": "set", "__data__": [_json_safe(item, depth + 1, seen) for item in items[:100]]}
    return {"__repr__": _truncated(_safe_repr(value), 4000)}


class DanglingAssertionWarning(UserWarning):
    """An ``assert_that()`` statement that asserts nothing.

    Found at collection under ``--assertpy-dangling`` and emitted when the test that contains it is
    set up, so pytest attributes it to that test rather than to whichever ran first.  A separate
    category so it can be turned into an error on its own with
    ``-W error::assertpy.DanglingAssertionWarning``, the same way the vacuity and snapshot-key
    warnings are escalated.
    """


class VacuousAssertionWarning(UserWarning):
    """Emitted when a universal assertion passes because there was nothing to check.

    ``all_satisfy`` over an empty collection is true the way ``all([])`` is true, so a query that
    returned no rows makes the assertion pass without examining anything.  That is the most common
    silent false pass in a test suite, and the one a green run never reveals.  Raise it to a failure
    with ``-W error::assertpy.VacuousAssertionWarning`` or silence it per call with ``allow_empty``.

    ``is_equal_to`` under ``ignore`` or ``include`` emits it too, when the filter left no key of the
    compared dict or object to compare.
    """


class Step(NamedTuple):
    """One hop from a value to one of its parts, as `DiffEntry.steps` records it.

    ``path`` is written for a person and is lossy by construction: a mapping key goes through ``str()``,
    so ``{3: ...}`` and ``{"3": ...}`` land on the same text, and a key holding a dot or a bracket
    cannot be read back out.  A step keeps the key itself, so a reader can walk back into the value it
    came from instead of parsing a string that was never a grammar.
    """

    kind: Literal["key", "index", "attr", "item", "line", "json"]
    """What kind of hop this is.

    ``key`` indexes a mapping, ``index`` a sequence, ``attr`` reads a field of a dataclass, namedtuple,
    attrs class or model.  ``item`` names a member of a set or of another collection that keeps no positions,
    and the mapping key a difference lies inside.
    ``line`` is the 1-based line number of a text or bytes diff.
    ``json`` stands where the value is JSON text and the difference lies in what it holds: the steps after it lead
    into what the text decodes to.
    """

    value: object
    """The key, index, field name, member or line number.  Not stringified: that is the whole point.

    For ``json`` it is what the text decodes to, the very object the steps after it lead into: decoding the text
    again would give an equal value and another object.
    """

    side: Literal["actual", "expected"] | None = None
    """Which sequence the index belongs to, when the two have shifted apart.

    Sequence alignment reports an inserted element against one side only, and once the two index spaces
    disagree an index without a side names two different elements.  ``None`` whenever both sides share
    the position, which is every step that is not a one-sided element of an aligned sequence.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class DiffEntry:
    """Single difference between actual and expected values at a specific path."""

    path: str
    actual: object = None
    expected: object = None
    absent: Literal["actual", "expected"] | None = None
    """Which side had no value here at all, as opposed to holding ``None``.

    Without this the two are indistinguishable, since both leave the field at ``None``, and a
    dictionary compared against one whose value is ``None`` renders exactly like a dictionary with an
    extra key.  Readers of a diff have to be able to tell "this key is not there" from "this key is
    there and its value is None", and so does anything reasoning about the diff afterwards.

    Defaults to ``None``, so an entry built the old way keeps its old meaning and only the producers
    that mean absence say so.
    """

    steps: tuple[Step, ...] = ()
    """The same location as ``path``, in the form a program can use.

    Empty at the root, which is the entry ``path`` renders as ``.``: the difference is the whole value.
    Also empty on an entry whose ``path`` is a label rather than a location, which is what a containment
    or matcher failure produces.
    """

    def __str__(self) -> str:
        actual = _truncated(_safe_str(self.actual))
        expected = _truncated(_safe_str(self.expected))
        return f"  at {self.path}: actual=<{actual}>, expected=<{expected}>"


@dataclass(frozen=True, slots=True, kw_only=True)
class DiffResult:
    """Structured diff between two values.

    ``kind`` names the diff *category* - the shape of comparison that produced the entries. It is one
    of ``"dict"``, ``"sequence"``, ``"dataclass"``, ``"namedtuple"``, ``"model"``, ``"attrs"``,
    ``"set"``, ``"string"``, ``"scalar"``, ``"contains"``, ``"match"``, or ``"openapi"``.

    It is unrelated to the assertion builder's ``kind`` argument, which selects the failure mode
    (``None``/``"soft"``/``"warn"``).
    """

    kind: str
    entries: list[DiffEntry] = field(default_factory=list)

    def __str__(self) -> str:
        return _render_diff(self)


def _diff_side(value: object, limit: int = 400) -> str:
    """Repr of one side of a diff entry, capped.

    A diff row is the detail beneath a message that already carries the elided value, so it is read on
    a terminal line and never needs the whole payload.  Uncapped it is the whole payload: two 500 KB
    strings used to render a megabyte per entry, and the structured `DiffEntry` still holds the
    untouched values for anything that wants them.
    """
    return _truncated(_safe_repr(value), limit)


def _diff_sides(actual: object, expected: object, limit: int = 400) -> tuple[str, str]:
    """Both sides of one comparison, capped onto the difference rather than from the start.

    `_diff_side` caps each side on its own, which is right for a row that stands alone.  A pair read
    together needs the pair's window: two 10 000-character strings differing in the middle were both
    cut at character 400, so the section printed two identical-looking values under a heading saying
    they were not equal, while the diff below it pointed straight at the change.  Two sides that read alike
    all through are told apart by their classes (`_told_apart`).
    """
    return _told_apart(*_windowed(_safe_repr(actual), _safe_repr(expected), limit), actual, expected)


def _first_difference(actual: str, expected: str) -> int:
    """The index where the two texts first differ, or the length of the shorter one.

    By halving rather than by comparing character by character: the per-character loop runs in Python
    while a slice compares in C, and over a megabyte of shared prefix that is 12.7 ms against 0.2 ms.
    The cost is paid on the failure path only, and the worst case is small enough to accept: a difference
    in the first position costs 0.095 ms, where the character walk leaves at once.
    """
    low, high = 0, min(len(actual), len(expected))
    while low < high:
        middle = (low + high) // 2
        if actual[low : middle + 1] == expected[low : middle + 1]:
            low = middle + 1
        else:
            high = middle
    return low


def _windowed(actual: str, expected: str, width: int = 160) -> tuple[str, str]:
    """Both lines cut to a window around their first difference.

    Cutting a long line at its start hides the very thing being reported when the change is deep
    inside it, which is the common shape for a page source or a response body.
    """
    if len(actual) <= width and len(expected) <= width:
        return actual, expected
    first_change = _first_difference(actual, expected)
    start = max(0, first_change - width // 2)

    def cut(text: str) -> str:
        head = "..." if start else ""
        hidden = len(text) - min(start + width, len(text)) + start
        tail = f"... ({hidden} more chars)" if start + width < len(text) else ""
        return f"{head}{text[start : start + width]}{tail}"

    return cut(actual), cut(expected)


def _match_line(entry: DiffEntry, *, red: str, cyan: str, reset: str) -> str:
    """One row of a ``match`` diff: what was found against what was asked of it, or what nothing was asked of."""
    was = _diff_side(entry.actual)
    if entry.absent == "expected":
        return f"  {red}{entry.path}: - {was}{reset}"
    return f"  {cyan}{entry.path}{reset}: expected {entry.expected}, but was {red}{was}{reset}"


def _append_string_entry(lines: list[str], entry: DiffEntry, *, red: str, green: str, reset: str) -> None:
    """Render one string line-pair with difflib's intra-line caret guides, the way pytest does.

    A one-token change in a long line shows the exact span (``? ^^^``) instead of dumping both whole
    lines and leaving the reader to spot the difference.
    """
    if entry.absent == "expected":
        lines.append(f"  {red}{entry.path}: - {_diff_side(entry.actual)}{reset}")
        return
    if entry.absent == "actual":
        lines.append(f"  {green}{entry.path}: + {_diff_side(entry.expected)}{reset}")
        return
    # ndiff costs ~175x a plain pair, so it was skipped past 200 characters; the window bounds its input instead
    actual_line, expected_line = _windowed(_safe_str(entry.actual), _safe_str(entry.expected))
    lines.append(f"  {entry.path}:")
    for guide in difflib.ndiff([actual_line], [expected_line]):
        text = guide.rstrip("\n")
        if guide.startswith("-"):
            lines.append(f"    {red}{text}{reset}")
        elif guide.startswith("+"):
            lines.append(f"    {green}{text}{reset}")
        else:  # the "? ^^^" caret guide row (ndiff emits nothing else for a changed single line)
            lines.append(f"    {text}")


def _both_texts(actual: object, expected: object) -> bool:
    """Whether a diff entry pairs two text-like leaves, so a caret guide would mean something.

    A caret points at the character that moved.  That only reads as an answer when both sides are the
    same kind of text; against a number or a list it would point into a repr the reader is not
    comparing character by character.
    """
    # by the type itself: `isinstance` reads a ``__class__`` the value may answer with code of its own
    texts = (str, bytes, bytearray)
    return issubclass(type(actual), texts) and issubclass(type(expected), texts)


def _append_text_leaf(lines: list[str], entry: DiffEntry, *, red: str, green: str, reset: str) -> None:
    """Render a text leaf nested inside a container with the same caret guide a bare string gets.

    Without this, a one-character change deep inside a URL or a token printed as two near-identical
    rows and left the reader to spot it.  pytest only reaches this at ``-vv``, and then by diffing the
    whole pretty-printed structure, which loses the path; naming the path *and* the character is the
    reason to do it here.

    The reprs are what gets compared, not the raw values, so the quoting that separates ``"1"`` from
    ``1`` survives and the row still reads like every other row of the block.

    The window is taken over the *whole* repr rather than a capped one.  Capping first cuts at a fixed
    offset, and a difference past that offset leaves two identical strings: ndiff then reports them as
    one common row, and a failure renders as though nothing differed.  Windowing first puts the
    difference inside the window by construction, and the window is already short enough to bound the
    cost of the ndiff below.
    """
    actual_line, expected_line = _windowed(_safe_repr(entry.actual), _safe_repr(entry.expected))
    lines.append(f"  {entry.path}:")
    for guide in difflib.ndiff([actual_line], [expected_line]):
        text = guide.rstrip("\n")
        if guide.startswith("-"):
            lines.append(f"    {red}{text}{reset}")
        elif guide.startswith("+"):
            lines.append(f"    {green}{text}{reset}")
        else:  # the "? ^^^" caret row
            lines.append(f"    {text}")


def _within_budget(lines: list[str], limit: int = 20_000) -> str:
    """Join *lines*, cutting the block once it would outgrow a screenful of scrollback.

    The per-row cap in `_diff_side()` bounds one row, this bounds their sum: fifty rows of capped
    values still add up to more than anyone reads, and the block travels into CI logs and report
    attachments where the cost is paid again.

    The row that crosses the limit is truncated rather than dropped.  Dropping it whole is invisible
    on a block of many rows and catastrophic on a block of few: the ``set`` and ``contains`` kinds
    join every item into a single row, so a large set difference used to render as the header and a
    count, with not one item shown.
    """
    total = 0
    for index, line in enumerate(lines):
        remaining = limit - total
        total += len(line) + 1
        if total > limit:
            dropped = len(lines) - index - 1
            head = [*lines[:index]]
            if remaining > 1:
                head.append(_cut(line, remaining - 1))
            else:
                dropped += 1
            if not dropped:
                return "\n".join(head)  # the trailing `...` already says where it was cut
            return "\n".join([*head, f"  ... and {dropped} more diff lines"])
    return "\n".join(lines)


_SGR = re.compile("\x1b\\[[0-9;]*m")
_RESET = "\x1b[0m"


def _cut(line: str, width: int) -> str:
    """``line`` truncated to ``width`` characters, left safe to print.

    A colored row carries its reset at the end, so cutting one blind ends the block mid-color and
    stains everything printed after it.  The cut can also land inside an escape sequence, which the
    terminal then completes by swallowing whatever follows it.
    """
    kept = line[:width]
    last_escape = kept.rfind("\x1b")
    if last_escape != -1 and not _SGR.match(kept, last_escape):
        kept = kept[:last_escape]  # a half-written escape is worse than none
    sequences = _SGR.findall(kept)
    if sum(1 for sequence in sequences if sequence != _RESET) > sequences.count(_RESET):
        return f"{kept}...{_RESET}"
    return f"{kept}..."


def _render_diff(diff: object, *, color: bool = False, max_entries: int = 50) -> str:
    """Render a `DiffResult` as aligned ``- actual`` / ``+ expected`` lines, optionally colored.

    Single source of truth for every place a diff surfaces: the pytest report section, the plain-text
    `AssertionFailure` message off pytest, and ``str(DiffResult)``.  So the diff reads identically wherever
    it is shown.
    """
    entries = getattr(diff, "entries", None)
    if not entries:
        return ""
    kind = getattr(diff, "kind", "unknown")

    red = "\033[31m" if color else ""
    green = "\033[32m" if color else ""
    cyan = "\033[36m" if color else ""
    reset = "\033[0m" if color else ""

    truncated = 0
    visible = entries
    if max_entries > 0 and len(entries) > max_entries:
        truncated = len(entries) - max_entries
        visible = entries[:max_entries]

    lines = [f"{cyan}diff ({kind}):{reset}"]

    if kind == "string":
        for entry in visible:
            _append_string_entry(lines, entry, red=red, green=green, reset=reset)
    elif kind == "match":
        lines.extend(_match_line(entry, red=red, cyan=cyan, reset=reset) for entry in visible)
    elif kind in {"set", "contains"}:
        # `absent` rather than the rendered label: a mapping key spelled "extra" used to land in the wrong group
        extra = ", ".join(_diff_side(entry.actual) for entry in visible if entry.absent == "expected")
        missing = ", ".join(_diff_side(entry.expected) for entry in visible if entry.absent == "actual")
        # braces go round the members of a set: round a dict looked for in a list they read `{{'id': 99}}`
        opener, closer = ("{", "}") if kind == "set" else ("", "")
        if extra:
            lines.append(f"  {red}extra:   {opener}{extra}{closer}{reset}")
        if missing:
            lines.append(f"  {green}missing: {opener}{missing}{closer}{reset}")
    else:
        for entry in visible:
            path = entry.path
            if entry.absent == "expected":
                lines.append(f"  {red}{path}: - {_diff_side(entry.actual)}{reset}")
            elif entry.absent == "actual":
                lines.append(f"  {green}{path}: + {_diff_side(entry.expected)}{reset}")
            elif _both_texts(entry.actual, entry.expected) and _safe_repr(entry.actual) != _safe_repr(entry.expected):
                _append_text_leaf(lines, entry, red=red, green=green, reset=reset)
            else:
                # as a pair: each side capped alone, two long values differing past the cap printed alike
                actual_side, expected_side = _diff_sides(entry.actual, entry.expected)
                lines.append(f"  {path}:")
                lines.append(f"    {red}- {actual_side}{reset}")
                lines.append(f"    {green}+ {expected_side}{reset}")

    if truncated:
        lines.append(f"  ... and {truncated} more entries")

    return _within_budget(lines)


_WHOLE_VALUES: bool = False
"""Whether a message prints a value whole, whatever its length.

The pytest plugin turns it on at ``-vv``, where pytest stops shortening its own output.  The cap keeps a
failure readable, and what it leaves out has to be within reach of someone reading the report: a row of a
report section and a value of a message were the only places a response body was printed.
"""

_RENDER_DIFF_IN_MESSAGE: bool = True
"""Whether `AssertionFailure.__str__` appends the rendered diff to its message.

The pytest plugin hangs the diff on the failure as a section of its own, so it turns this off at
configure time to avoid showing the diff twice.  Off pytest (unittest, plain scripts, CI logs) it stays on,
so the structured diff travels with ``str(exc)`` instead of being lost.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class PollSample:
    """One recorded poll of an [`eventually()`][assertpy.assertpy.AssertionBuilder.eventually] probe.

    ``outcome`` is ``"fail"`` (the probe returned a value and the assertion on it failed) or
    ``"error"`` (the probe raised an ignored exception before producing a value).

    ``value`` is a JSON-safe point-in-time snapshot of the probed value, ``None`` for ``"error"``
    samples, and ``detail`` carries the failure message or the exception repr.

    Consecutive identical polls are collapsed into one sample: ``repeats`` counts the run, and
    ``elapsed`` is its first occurrence, in seconds from the start of polling.
    """

    elapsed: float
    outcome: str
    value: object
    detail: str
    repeats: int = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class PollTrace:
    """Convergence telemetry attached to an ``eventually()`` timeout failure.

    ``samples`` keeps the first and last polls, with middle entries beyond the retention window
    counted in ``dropped``, and ``total_polls`` is the real number of polls.

    ``summary`` is a one-line trend classification of why the condition never held.
    """

    samples: list[PollSample]
    total_polls: int
    dropped: int
    elapsed: float
    summary: str


class AssertionFailure(AssertionError):  # noqa: N818  # public exception name; kept for backward compatibility
    """Structured assertion failure with optional diff data.

    Subclasses AssertionError for full backward compatibility:
    existing ``except AssertionError`` handlers catch it transparently.
    """

    def __init__(
        self,
        message: str,
        *,
        actual: object = None,
        expected: object = None,
        diff: DiffResult | None = None,
        trace: PollTrace | None = None,
        requirement: Requirement | None = None,
        failures: tuple[AssertionOutcome, ...] = (),
    ):
        super().__init__(message)
        self._message = message
        self.actual = actual
        self.expected = expected
        self.diff = diff
        self.trace = trace
        self.requirement = requirement
        """What was asked of the value, as data: the operation, its parameters, and whether it was negated.

        ``None`` where no operation was asked: `fail()`, a bare `error()` carrying a message of the
        caller's own, and a precondition of one of the few members that assert nothing on their own.
        """
        self.failures = failures
        """The failures a soft block collected, in the order they were collected.

        Empty on a failure that is about one value, which is every failure except the aggregate a
        ``soft_assertions()`` block raises when it closes.  The aggregate's message is these rendered
        into a list; this is the same thing before it became a string.
        """
        self._compared: tuple[object, object] | None = None
        """The two values a failed equality held against each other, or ``None`` for any other failure.

        The value and the operand, or under ``ignore=`` / ``include=`` the copies without the keys left out:
        the pair ``==`` alone decided.  Read by the pytest plugin for a listener that shows two values side
        by side.
        """
        self._compared_pairs: tuple[tuple[object, object] | None, ...] = ()
        """Beside each of `failures`, the pair its equality held against each other, or ``None``.

        Under ``ignore=`` or ``include=`` that is the two copies without the keys left out, which a raised failure
        keeps as ``_compared``: the pytest plugin shows it, so a collected failure reads as the raised one does.
        Kept here rather than on the record so the published record's fields stay what they were.
        """
        self._soft_summary: Callable[[], str] | None = None
        """Draws a soft block's summary with each failure's diff in block form, for a message nobody else renders.

        Set by the block that raises this, and called at each read with the switch on, so the text shows the diffs as
        they are then, as a single failure's diff does.  Drawing it when raised cost a caught failure nobody printed
        8 us for one failure and 100 us for twenty.
        """
        self._outcome: AssertionOutcome | None = None
        """The record this failure was composed from, set by the delivery half of `error()`.

        Carries what the flat attributes cannot: whether ``actual`` and ``expected`` were named by the
        assertion or filled in from the value under test, which is what `has_expected` reads.  The
        polling and snapshot re-wraps carry the record of the failure they re-wrap.  It stays ``None``
        on a failure built without one, which `fail()` and the aggregate a soft block raises both are.

        Private, and not a constructor argument, because `AssertionOutcome` is still gaining a field
        per release.  It becomes public when a caller outside this package has a reason to read it.
        """

    __module__ = "assertpy"
    """Where the class says it lives, which is what a traceback prints in front of the message.

    Every failure is an `AssertionFailure` now, so this prefix is on every failure line a reader sees,
    and pytest's one-line summary is cut to the terminal width with the prefix counted first.  The
    canonical import is ``from assertpy import AssertionFailure``, so the shorter path is also the
    truer one.  The reference still documents it under `assertpy.errors`, which reads the source.
    """

    @property
    def has_expected(self) -> bool:
        """Whether the assertion named an expected value at all.

        ``expected is None`` cannot answer it: `is_equal_to(None)` names one and `is_not_empty()` names
        none, and both leave the attribute at ``None``.  A reporter deciding whether to show an expected
        column needs the difference, and had to read the private record to get it.

        Read from the record a failure composed through `error()` carries, which the polling and
        snapshot re-wraps preserve.  A failure built directly has none, and `fail()` and the aggregate a
        soft block raises are built that way: there the older reading is all there is, and an
        expectation counts as named when it is not ``None``.  Both of those name none and hold ``None``,
        so the fallback answers them correctly.
        """
        if self._outcome is not None:
            return self._outcome.has_expected
        return self.expected is not None

    def __str__(self) -> str:
        if _RENDER_DIFF_IN_MESSAGE and self._soft_summary is not None:
            return self._soft_summary()
        if _RENDER_DIFF_IN_MESSAGE and self.diff is not None:
            rendered = _render_diff(self.diff)
            if rendered:
                return f"{self._message}\n{rendered}"
        return self._message
