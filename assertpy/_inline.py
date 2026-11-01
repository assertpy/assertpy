"""Inline-snapshot recording: locate the ``matches_inline()`` call in the test source and rewrite it
to carry the captured value as a literal.

Only update mode lives here and touches ``executing``/``asttokens``; the comparison path in
``snapshot.py`` is a plain equality check that needs none of this.

Every run of a call under update mode is seen, the ones that matched included, and what to write is
decided per call once the run is over.  Written as each run went, a parametrised call got both its
values in one place, ``matches_inline(12)`` for the cases ``1`` and ``2``, and a case that matched the
old literal was broken by the rewrite another case asked for.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import math
import os
import pprint
import token
import tokenize
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, TypeVar

from .errors import _truncated

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from types import FrameType

_LITERAL_TYPES = (str, int, float, bool, type(None))
_T = TypeVar("_T")


class Uncaptured:
    """What a copy that could not be made leaves behind: the run it belongs to takes no literal."""


UNCAPTURED: Final = Uncaptured()


def captured(state: _T) -> _T | Uncaptured:
    """A copy of *state* that a later change to it cannot reach, or `UNCAPTURED` where it cannot be copied.

    A run asked at the end of the session about a literal another run asked for is asked with its options
    as they were: the test may have changed the dictionary it passed by then.
    """
    try:
        return copy.deepcopy(state)
    except Exception:  # an object deepcopy refuses: its run then takes no literal, the conservative answer
        return UNCAPTURED


@dataclass(frozen=True, slots=True)
class _Run:
    """One run of a call under update mode."""

    text: str | None
    """The value as it would be written there, or ``None`` for a value that is no literal."""

    stale: bool
    """Whether the run asked for a rewrite: the call was empty, or its literal no longer matched."""

    value: object
    """The value rebuilt from its literal, asked about at the end of the session, so a later change to the object
    the test passed cannot move it, and the object itself for a value that is no literal.  When the run ran it was
    asked about the object itself, whose shared references a comparator may read."""

    accepts: Callable[[object, object], bool]
    """Whether this run's own comparison, with its own options, passes for a value against a candidate literal."""

    source: str
    """A digest of the file's text the call was located in, which every offset here is counted in."""

    later: bool = True
    """Whether the run may be asked at the end of the session about a literal asked for after it ran: only a
    literal value compared by plain data, since a comparator function or an object's own `==` can answer
    differently by then, through state the test changed."""

    judged: dict[str, bool] = field(default_factory=dict)
    """What the run answered, when it ran, about its own literal and every one asked for at its call so far."""


_SEEN: dict[tuple[str, int, int], list[_Run]] = {}
"""Every run under update mode, by file and the range of it a rewrite replaces (empty for an insertion)."""


def _ensure_inline_tooling():
    try:
        import asttokens  # noqa: F401  # optional dependency, imported to fail early with a clear message
        import executing
    except ImportError:
        raise ImportError(
            "recording inline snapshots requires the 'executing' and 'asttokens' packages."
            " Install them with: pip install assertpy[inline]"
        ) from None
    return executing


def is_literalable(value: object) -> bool:
    """Whether ``value`` round-trips as a source literal (dict/list/tuple/set of scalars).

    By exact type, since a subclass renders as its own repr: an `IntEnum` is an `int` and writes
    ``<Status.ACTIVE: 1>``, which is not source at all.
    """
    if isinstance(value, dict):
        return type(value) is dict and all(is_literalable(key) and is_literalable(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return type(value) in (list, tuple, set, frozenset) and all(is_literalable(item) for item in value)
    if isinstance(value, float):
        return type(value) is float and math.isfinite(value)  # nan/inf/-inf render as bare names, not literals
    return type(value) in _LITERAL_TYPES


def _format_literal(value: object, column: int) -> str:
    """Render ``value`` as a source literal, wrapping wide values and indenting to ``column``."""
    raw = pprint.pformat(value, sort_dicts=False, width=max(20, 116 - column))
    lines = raw.split("\n")
    if len(lines) == 1:
        return raw
    pad = " " * column
    return lines[0] + "".join(f"\n{pad}{line}" for line in lines[1:])


def _opening(atok: Any, call: ast.Call) -> Any:
    """The token that opens *call*'s arguments: the bracket its last token closes.

    Not the token after the callee, which in ``(assert_that(v).matches_inline)()`` closes the group.
    """
    depth = 0
    tok = atok.get_token_from_offset(atok.get_text_range(call)[1] - 1)
    while True:
        if tok.type == token.OP and tok.string in ")]}":
            depth += 1
        elif tok.type == token.OP and tok.string in "([{":
            depth -= 1
        if depth == 0:
            return tok
        tok = atok.prev_token(tok)


def _expected_of(call: ast.Call) -> ast.expr | None:
    """The argument the call passes as ``expected``, or ``None`` where unpacking hides it."""
    if call.args:
        first = call.args[0]
        return None if isinstance(first, ast.Starred) else first
    return next((keyword.value for keyword in call.keywords if keyword.arg == "expected"), None)


def _is_literal(node: ast.expr) -> bool:
    """Whether *node* is a literal an update may replace: what `ast.literal_eval` reads, and what `_format_literal`
    writes besides, ``set()`` and ``frozenset(...)`` of a literal, anywhere inside one."""
    if isinstance(node, ast.Call):
        return (
            isinstance(node.func, ast.Name)
            and node.func.id in ("set", "frozenset")
            and not node.keywords
            and len(node.args) <= 1
            and all(_is_literal(argument) for argument in node.args)
        )
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _is_literal(key) for key in node.keys) and all(map(_is_literal, node.values))
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


def _installed(filename: str) -> bool:
    """Whether *filename* lies under a `site-packages` or `dist-packages` folder, where installers put packages.

    A folder name, not ownership: a package installed with ``pip install --target`` elsewhere is not told
    apart, and inside the rootdir it is written as the project's own source.
    """
    return not {"site-packages", "dist-packages"}.isdisjoint(os.path.normcase(os.path.normpath(filename)).split(os.sep))


def _digest(text: str) -> str:
    """A digest of a file's text as Python read it, less the final newline `linecache` adds to a file without one."""
    return hashlib.sha256(text.removesuffix("\n").encode("utf-8", "surrogatepass")).hexdigest()


def observe(
    frame: FrameType,
    value: object,
    *,
    creating: bool,
    stale: bool,
    accepts: Callable[[object, object], bool],
    pure: bool = True,
) -> None:
    """Note one run of the ``matches_inline()`` call executing at *frame*, for the decision at session end.

    *pure* says the run's comparison options hold no function, so it can be asked again later (`_Run.later`).

    A call in a file under an installer's folder (`_installed`) runs on behalf of a test and is shared by
    every test reaching it, so it is never rewritten: a literal written there would land in a third-party
    file, and in every project the installation serves.

    Raises:
        TypeError: where the run asks for a rewrite of an argument that is no literal, or one unpacking
            hides: rewritten, ``matches_inline(EXPECTED)`` would stop reading the constant it was written with
        RuntimeError: where the run asks for a rewrite of a call in an installed package
    """
    if _installed(frame.f_code.co_filename):
        if not stale:
            return
        raise RuntimeError(
            f"update mode does not rewrite {frame.f_code.co_filename}, a file of an installed package:"
            " call matches_inline() from the test itself"
        )
    executing = _ensure_inline_tooling()
    source = executing.Source.for_frame(frame)
    call = source.executing(frame).node
    if not isinstance(call, ast.Call):  # pragma: no cover - reached below 3.11 alone, which the coverage run is not
        raise RuntimeError(
            "could not locate the matches_inline() call to record the inline snapshot; below Python 3.11 a call"
            " inside an assert statement pytest rewrote, or one given its value through **, may not be found,"
            " so write it on a line of its own with its literal"
        )
    atok = source.asttokens()
    place = _place(atok, call, creating=creating, stale=stale)
    if place is None:
        return
    start, end, separator = place
    column = start - source.text.rfind("\n", 0, start) - 1
    if is_literalable(value):
        literal = _format_literal(value, column)
        text, seen = literal + separator, _built(literal)
    else:
        text, seen = None, value
    run = _Run(text, stale, seen, accepts, _digest(source.text), later=pure and text is not None)
    runs = _SEEN.setdefault((frame.f_code.co_filename, start, end), [])
    runs.append(run)
    if not run.later:
        for other in runs:
            if other.text is not None and other.text not in run.judged and (other is run or other.stale):
                run.judged[other.text] = _asks(accepts, value, other.text)


def _place(atok: Any, call: ast.Call, *, creating: bool, stale: bool) -> tuple[int, int, str] | None:
    """The range a literal takes in *call* and what follows it, or ``None`` for a run with nothing to write there.

    Raises:
        TypeError: where the run asks for a rewrite of an argument that is no literal, or one unpacking hides
    """
    if creating:
        start = _opening(atok, call).endpos
        return start, start, ", " if call.args or call.keywords else ""
    expected = _expected_of(call)
    if expected is not None and _is_literal(expected):
        start, end = atok.get_text_range(expected)
        return start, end, ""
    if not stale:
        return None
    if expected is None:
        raise TypeError(
            "update mode cannot rewrite this matches_inline(): its expected value is passed through"
            " unpacking, so there is no literal to replace - pass it as the first argument or as expected="
        )
    raise TypeError(
        f"update mode cannot rewrite this matches_inline(): its expected value <{atok.get_text(expected)}>"
        " is not a literal, and writing one in its place would stop the test reading it - write the"
        " literal into the call, or update the value by hand"
    )


def _built(literal: str) -> object:
    """The value *literal* builds in the test: compiled, as Python compiles the file it is written into.

    Compiling merges equal constants, so the inner tuples of ``((1, 2), (1, 2))`` are one object, which
    `ast.literal_eval` builds twice and a comparator reading shared references tells apart.  It also reads
    ``frozenset({1})``, which `ast.literal_eval` refuses.  The file merges them with its other constants too,
    which a literal compiled alone cannot show.  The text is this module's rendering of a literal value
    (`_format_literal`), which calls nothing but `set` and `frozenset`.
    """
    code = compile(literal, "<inline snapshot>", "eval")
    return eval(code, {"__builtins__": {}, "set": set, "frozenset": frozenset})


def _asks(accepts: Callable[[object, object], bool], actual: object, text: str) -> bool:
    """Whether *accepts* passes *actual* against the literal *text*: a comparison that raises takes nothing.

    Against the literal built anew, as the next run compares the test's value with the one in the source: a
    candidate that is the object the run holds, or a copy `deepcopy` hands back as itself, a tuple of numbers,
    is one object, which a comparator by identity takes.
    """
    candidate = _built(text.removesuffix(", "))  # no literal ends in the separator
    try:
        return accepts(actual, candidate)
    except Exception:  # a comparator of the caller's raised on the candidate, which is no reason to break the run
        return False


def _taken_by(run: _Run, text: str) -> bool:
    """Whether *run* takes the literal *text*: as it answered when it ran, or, where it may be asked later, now."""
    if text in run.judged:
        return run.judged[text]
    return run.later and _asks(run.accepts, run.value, text)


def _settled(runs: list[_Run]) -> tuple[str | None, bool]:
    """The literal to write for one call, if any, and whether every run of it takes that literal.

    A run takes a literal its own comparison passes against, so a case differing only in a field it
    ignores takes the literal another case asked for.  The run that asked for the literal is asked too:
    a comparator that holds nothing equal would otherwise get a literal written that fails the next run.
    """
    asking: dict[str, _Run] = {}
    for run in runs:
        if run.stale and run.text is not None:
            asking.setdefault(run.text, run)
    if not asking:
        return None, True
    for text in asking:
        if all(_taken_by(run, text) for run in runs):
            return text, True
    return None, False


def shipped() -> list[list[object]]:
    """What this process saw, settled per call as far as one process can: the form an xdist worker sends.

    One row per call: file, start, end, the literal to write or ``None``, whether that settled every run
    seen here, the distinct texts seen, the digests of the file's text the offsets were counted in, and the
    one literal every run here takes (`_held`), which is all another process can be told of their options.
    """
    rows: list[list[object]] = []
    for (filename, start, end), runs in _SEEN.items():
        written, settled = _settled(runs)
        texts = list(dict.fromkeys(run.text for run in runs))
        held = written if written is not None else _held(runs, texts)
        rows.append([filename, start, end, written, settled, texts, sorted({run.source for run in runs}), held])
    _SEEN.clear()
    return rows


def _held(runs: list[_Run], texts: list[str | None]) -> str | None:
    """The literal a process that asked for none would take: the one text it saw, where every run takes it.

    Only that one can be offered to it: a literal another worker asks for is written only where every
    worker takes it, and a worker that saw two texts, or one no run of its own takes, takes none.
    """
    if len(texts) != 1 or texts[0] is None:
        return None
    return texts[0] if all(_taken_by(run, texts[0]) for run in runs) else None


def _listed(texts: Iterable[object]) -> str:
    shown = [f"<{_truncated(str(text), 60)}>" for text in dict.fromkeys(texts) if text is not None]
    more = f" and {len(shown) - 4} more" if len(shown) > 4 else ""
    return ", ".join(shown[:4]) + more


def _decided(rows: Sequence[Sequence[Any]]) -> tuple[str | None, str]:
    """What one call gets written, from every process that saw it, or why it gets nothing."""
    seen = [text for row in rows for text in row[5]]
    if not all(row[4] for row in rows):
        if len(set(seen)) == 1 and seen[0] is not None:
            return None, (
                f"matches_inline() would not pass against the literal it would write, {_listed(seen)}, under its"
                " own comparison options, so nothing was written: look at the comparators or the tolerance it is given"
            )
        return None, (
            f"matches_inline() saw values no one literal matches, so nothing was written: {_listed(seen)}."
            " One literal stands for every case that reaches the call: give each case a call of its own,"
            " or use snapshot()"
        )
    written = {row[3] for row in rows if row[3] is not None}
    if not written:
        return None, ""
    text = next(iter(written))
    if len(written) == 1 and all(row[7] == text for row in rows):
        return text, ""
    return None, (
        f"matches_inline() was not settled alike in every xdist worker, so nothing was written: {_listed(seen)}."
        " Whether one literal matches every case depends on the call's comparison options, which only the"
        " process that ran a case can ask: record it with -n 0"
    )


def _within(filename: str, root: str) -> bool:
    """Whether *filename* lies under the folder *root*, both read through their links."""
    return os.path.normcase(os.path.realpath(filename)).startswith(
        os.path.join(os.path.normcase(os.path.realpath(root)), "")
    )


def _read(filename: str) -> tuple[str, str, str]:
    """A source file's text as Python reads it, its encoding, and the line ending to write it back with.

    Raises:
        OSError, UnicodeError, SyntaxError: where it cannot be read, or its coding line names no codec
    """
    with open(filename, "rb") as raw:
        encoding, _ = tokenize.detect_encoding(raw.readline)
    with open(filename, encoding=encoding) as handle:
        text = handle.read()
        newline = handle.newlines  # the file's own line ending, detected while reading
    return text, encoding, newline if isinstance(newline, str) else "\n"


def apply_inline_records(rows: Iterable[Sequence[Any]], root: str) -> list[str]:
    """Write what the run settled, one file at a time, and hand back what could not be written, one line each.

    Only a file under *root*, the rootdir, is written, only if its text is still the one the calls were
    located in, and only if it still parses with every literal in place.  A file with nothing to write or
    report is not opened.
    """
    by_file: dict[str, dict[tuple[int, int], list[Sequence[Any]]]] = {}
    for row in rows:
        by_file.setdefault(row[0], {}).setdefault((row[1], row[2]), []).append(row)
    problems: list[str] = []
    for filename, sites in by_file.items():
        decided = {site: _decided(site_rows) for site, site_rows in sites.items()}
        if any(text is not None or why for text, why in decided.values()):
            sources = {source for site_rows in sites.values() for row in site_rows for source in row[6]}
            problems.extend(_written(filename, decided, sources, root))
    return problems


def _written(
    filename: str, decided: dict[tuple[int, int], tuple[str | None, str]], sources: set[str], root: str
) -> list[str]:
    """Write the literals decided for one file, and hand back what could not be written or decided, one line each."""
    if not _within(filename, root):
        return [f"{filename}: outside the rootdir {root}, so nothing was written: update mode writes only there"]
    try:
        content, encoding, newline = _read(filename)
    except (OSError, UnicodeError, SyntaxError) as e:
        return [f"{filename}: could not be read ({e}), so nothing was written"]
    if sources != {_digest(content)}:
        return [
            f"{filename}: changed while the run went on, so the places recorded in it no longer hold the calls"
            " they were taken from, and nothing was written"
        ]
    problems = [
        f"{filename}:{content.count(chr(10), 0, start) + 1}: {why}" for (start, _), (_, why) in decided.items() if why
    ]
    edits = sorted(
        ((start, end, text) for (start, end), (text, why) in decided.items() if text and not why), reverse=True
    )
    if edits:
        problems.extend(_rewritten(filename, content, encoding, newline, edits))
    return problems


def _rewritten(
    filename: str, content: str, encoding: str, newline: str, edits: list[tuple[int, int, str]]
) -> list[str]:
    """Put the literals into one file, in its own encoding and line ending, or say why it was left as it was.

    Its new modification time is a whole second past the old one, since pytest and CPython both key a
    cached `.pyc` on the whole second and the size: a same-size rewrite within the second was read back
    as the old literal by the next run.
    """
    rewritten = content
    for start, end, text in edits:
        rewritten = rewritten[:start] + text + rewritten[end:]
    try:
        ast.parse(rewritten)
    except SyntaxError as e:
        return [f"{filename}: the recorded literals would not parse ({e.msg}, line {e.lineno}), so nothing was written"]
    try:
        data = rewritten.replace("\n", newline).encode(encoding)
    except UnicodeError as e:
        return [
            f"{filename}: a recorded literal cannot be written in the file's encoding ({e}), so nothing was written"
        ]
    try:
        before = os.stat(filename)
        with open(filename, "wb") as handle:
            handle.write(data)
        after = os.stat(filename)
        past = (int(before.st_mtime) + 1) * 1_000_000_000
        if after.st_mtime_ns < past:
            os.utime(filename, ns=(after.st_atime_ns, past))
    except OSError as e:
        return [f"{filename}: could not be written ({e}), so it may hold part of the rewrite: check it"]
    return []
