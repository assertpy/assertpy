from __future__ import annotations

import contextlib
import inspect
import os
import sys
import time
import warnings
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, NoReturn

from . import _inline, _renamed
from ._engine._compare import _build_compare_config
from ._engine._contract import shape, shape_diff
from ._engine._introspection import ASSERTPY_FILES, caller_stacklevel
from ._engine._mixin_base import _MixinBase
from ._snapshot_codec import _SERIALIZERS, _load, _save, _Serializer
from .errors import AssertionFailure, _safe_repr, _safe_str, _truncated
from .matchers import _apply_matcher, _describe_matcher, _is_matcher
from .outcome import MISSING

if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Generator, Mapping

    from ._engine._compat import Self
    from .matchers import Matcher

__tracebackhide__ = True

_UNSET: Final = object()


def _require_caller(frame: types.FrameType | None) -> types.FrameType:
    """The frame of the call as written: the first one outside this package, from ``frame`` outwards,
    which is what keys a snapshot by line and drives an inline rewrite.

    Read by file rather than by a count of hops.  One hop up answered the wrapper `check()` and `not_`
    run an assertion through, so a snapshot under either was keyed by a line of this package, two tests
    sharing one key, and an inline one was written into this package's source.  mutmut's trampoline
    adds hops of its own too.

    Raises:
        RuntimeError: if the interpreter exposes no calling frame.
    """
    caller = frame
    while caller is not None and caller.f_code.co_filename in ASSERTPY_FILES:
        caller = caller.f_back
    if caller is None:  # pragma: no cover - frame introspection always available in CPython
        raise RuntimeError("cannot determine caller frame")
    return caller


def _calls_back(state: object) -> bool:
    """Whether *state* holds something callable, which a copy hands back as itself, to answer as it likes later."""
    if isinstance(state, dict):
        return any(_calls_back(key) or _calls_back(item) for key, item in state.items())
    if isinstance(state, (list, tuple, set, frozenset)):
        return any(_calls_back(item) for item in state)
    return callable(state)


def _stale(builder: Callable[..., Any], value: object, stored: object, options: dict[str, Any]) -> bool:
    """Whether *stored* no longer matches *value* under the comparison *options*, decided via a strict
    throwaway builder (under soft/warn kinds ``self.is_equal_to`` would not raise)."""
    try:
        builder(value, "")._compared_to_stored(stored, **options)
    except AssertionError:
        return True
    return False


def register_snapshot_serializer(
    cls: type,
    # `Any`, not `object`: a codec only sees an instance of `cls`, and `object` rejected `pathlib.PurePath`
    encode: Callable[[Any], object],
    decode: Callable[[Any], object],
    *,
    tag: str | None = None,
) -> None:
    """Register a custom (encode, decode) pair for snapshotting values of type ``cls``.

    The typed codec covers common non-JSON types (``set``, ``complex``, ``datetime``/``date``/``time``,
    ``Decimal``, ``bytes``, ``uuid.UUID``, ``Enum``).  Register a serializer for anything else - a
    domain object, an ORM row, a ``pathlib.Path`` - so ``snapshot()`` stores and round-trips it instead
    of raising ``TypeError``.

    Matching is by ``isinstance`` (so subclasses are covered), the registry is consulted **before** the
    built-ins, and a later registration wins over an earlier one for overlapping types.

    Args:
        cls: the type (matched by ``isinstance``) the serializer applies to
        encode: ``value -> json_safe`` (the returned object must itself be JSON-serializable or
            handled by another serializer)
        decode: ``json_safe -> value`` (the inverse; runs your own code on snapshot load, so it is a
            trusted, explicit opt-in - unlike the automatic instance decode, which never imports)
        tag: a stable identifier stored in the snapshot to route decoding (defaults to the type's
            fully-qualified name); change it only deliberately, since existing snapshots key on it

    Examples:
        Usage:

            import pathlib

            register_snapshot_serializer(pathlib.PurePath, str, pathlib.PurePath)

    Raises:
        TypeError: if ``cls`` is not a type, or ``encode`` / ``decode`` are not callable
    """
    if not isinstance(cls, type):
        raise TypeError("cls must be a type")
    if not callable(encode) or not callable(decode):
        raise TypeError("encode and decode must be callable")
    _SERIALIZERS.insert(0, _Serializer(cls, encode, decode, tag or f"{cls.__module__}.{cls.__qualname__}"))


class SnapshotCreatedWarning(UserWarning):
    """Emitted when `snapshot()` writes a new snapshot instead of comparing.

    The first run of a snapshot assertion captures the current value and passes without comparing
    anything, so a wrong first capture would silently become the reference.  This warning makes that
    capture visible; suites running with ``-W error`` turn it into an explicit failure.
    """


class SnapshotKeyReusedWarning(UserWarning):
    """Emitted when one snapshot key was reached by more than one test.

    The default key is the line of the ``snapshot()`` call, so every case of a parametrised test shares
    it: the first case stores its value and the rest compare against that one.  Where the values differ
    the run fails with a message that names two unrelated cases, and where they agree it passes while
    checking one case out of however many - the second is the reason this warning exists, because
    nothing else reports it.

    Two calls inside one test are not this: a helper that snapshots twice asserts both values, so the
    metric is distinct tests rather than accesses.

    Its own category, so it can be raised to an error with a single ``filterwarnings`` entry.
    """


class SnapshotUpdatedWarning(UserWarning):
    """Emitted when `snapshot()` overwrites a stored snapshot in update mode.

    Update mode replaces failing snapshots with the current value instead of failing; turn it on with
    the ``--assertpy-snapshot-update`` pytest flag or the ``ASSERTPY_SNAPSHOT_UPDATE`` environment
    variable.

    Each overwrite emits this warning, so an update run reports exactly which snapshots changed instead
    of rewriting them silently.
    """


# set by the pytest plugin when --assertpy-snapshot-update is given; the env var covers other runners
_UPDATE_ALL: bool = False

# tri-state CI mode set by the pytest plugin flags (None = not set by a flag)
_CI_MODE: bool | None = None

# key is the lineno for a default-id sub-snap, or "" for a whole-file custom-id snapshot
_TOUCHED: set[tuple[str, str]] = set()

_ACCESS_NODES: dict[tuple[str, str], set[str]] = {}
"""Which tests reached each ``(snapname, key)``, by node id.

Counting *tests* rather than accesses is what separates the defect from the legitimate case.  Two
parametrised cases share a line, so they share the default key: the first stores its value and the
rest compare against it, and only one of them is ever asserted.  A helper that snapshots twice inside
one test also reaches a key twice, and asserts both times - counting accesses cannot tell those apart
and accuses the second.  Distinct node ids can.

Values, writes and differences are all useless as the metric: when the reused key happens to hold the
same value there is one write, no difference, and nothing fails.
"""

_CURRENT_NODE: str | None = None
"""Node id of the running test, set by the pytest plugin.  ``None`` off pytest, where there is no test
to attribute a reuse to and the sweep that would report it does not run either."""

_SCOPE: str | None = None
"""Whose keys ``_SCOPE_SEEN`` currently holds, so they can be dropped when the test changes.

Off pytest ``_CURRENT_NODE`` never moves, which makes the whole process one scope - the right reading
where there are no test boundaries to draw.
"""

_SCOPE_SEEN: set[tuple[str, str]] = set()
"""Keys the running test has already reached, which is how a repeat is spotted."""

_SCOPE_REPEATS: set[tuple[str, str]] = set()
"""Keys the running test reached more than once.

Two reaches inside one test are legitimate and deliberately unwarned, but when the second comparison
*fails*, the reader is looking at two unrelated values with nothing saying why they were compared.
This is the diagnostic for that message, not a second detection metric: it is read only on failure.
"""

_ACCESS_SITES: dict[tuple[str, str], str] = {}
"""Where each key was first reached, so the warning can name a source location rather than a key."""

_WARNED: set[tuple[str, str]] = set()
"""Keys already reported from inside a test, so the end-of-session sweep does not report them twice."""


def _reuse_message(snapname: str, key: str, site: str, tests: int | None = None) -> str:
    """Describe a reused key.  ``tests`` is the total, and only the end-of-run sweep ever has it.

    The warning raised from inside an assertion fires the moment a second test arrives, with a third
    and fourth still possible, and it cannot see the other xdist workers at all.  Any number it printed
    would read as a total, and a reader who fixes the two they went looking for would leave the rest of
    them sharing the key.  So it states the fact, and the sweep supplies the count.
    """
    reach = f" is shared by {tests} tests." if tests is not None else " is reached by more than one test."
    return (
        f"snapshot key <{snapname}::{key or '<whole file>'}>"
        f"{f' from {site}' if site else ''}{reach}"
        " Only the first value is stored, so the others are compared against it and their own values"
        " are never asserted. Give each test its own snapshot(id=...)."
    )


def _rewrapped(mismatch: AssertionFailure, message: str) -> AssertionFailure:
    """The same failure with a snapshot-aware message, keeping everything the original carried.

    A snapshot comparison is `is_equal_to` underneath, so the failure it raises already carries a
    composed record.  Building a fresh exception around a new message used to drop that record, which
    made a snapshot mismatch the only comparison failure without one: the flat ``actual``/``expected``/
    ``diff`` came across, the diagnostic hint and the provenance of the values did not.

    Assigned rather than guarded: both callers catch what `is_equal_to` raised, and every failure that
    goes through the builder's delivery carries a record.  A guard here would be dead, and would turn a
    future break of that invariant into a silently record-less failure instead of a loud one.
    """
    failure = AssertionFailure(
        message,
        actual=mismatch.actual,
        expected=mismatch.expected,
        diff=mismatch.diff,
        trace=mismatch.trace,
        requirement=mismatch.requirement,
    )
    # ty: ignore[invalid-argument-type]  # never None here: both callers catch what `is_equal_to` raised
    failure._outcome = replace(mismatch._outcome, message=message)
    return failure


def _shared_key_hint(snapname: str, key: str) -> str:
    """Say that this test reached the key before, when a comparison against it fails.

    Reuse inside one test is legitimate, so it raises no warning - but the failure it can produce
    reads as two unrelated values compared for no reason, and the reason is that both calls landed on
    one key.  Nothing else in the message carries that.
    """
    if (snapname, key) not in _SCOPE_REPEATS:
        return ""
    return (
        f" This test reached <{f'{snapname}::{key}' if key else snapname}> more than once, so the value"
        " above was compared against what an earlier call in the same test stored."
        " Give each call its own snapshot(id=...)."
    )


def _record_access(snapname: str, key: str, site: str) -> None:
    """Record which test reached ``key``, and report the second distinct one from here.

    Warning from inside the assertion is what makes it usable: pytest attributes it to the test that
    triggered it, it lands in the normal warnings summary, and under ``-W error`` it fails that test
    with a traceback pointing at the test rather than aborting a session-finish hook.  The end-of-run
    sweep still exists for the case this cannot see - parametrised cases split across xdist workers,
    where no single process sees two node ids and only the union does.
    """
    global _SCOPE
    _TOUCHED.add((snapname, key))
    _ACCESS_SITES.setdefault((snapname, key), site)
    if _SCOPE != _CURRENT_NODE:  # a new test: its predecessor's repeats say nothing about this one
        _SCOPE = _CURRENT_NODE
        _SCOPE_REPEATS.clear()
        _SCOPE_SEEN.clear()
    if (snapname, key) in _SCOPE_SEEN:
        _SCOPE_REPEATS.add((snapname, key))
    _SCOPE_SEEN.add((snapname, key))
    if _CURRENT_NODE is None:  # off pytest: nothing to attribute a reuse to, and no sweep to report it
        return
    nodes = _ACCESS_NODES.setdefault((snapname, key), set())
    nodes.add(_CURRENT_NODE)
    # `>= 2` with `_WARNED` doing the once-only work: `== 2` would drop warnings if anything repopulated the registry
    if len(nodes) >= 2 and (snapname, key) not in _WARNED:
        _WARNED.add((snapname, key))
        warnings.warn(
            _reuse_message(snapname, key, _ACCESS_SITES[snapname, key]),
            SnapshotKeyReusedWarning,
            stacklevel=caller_stacklevel(),
        )


_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})
_FALSY: Final = frozenset({"0", "false", "no", "off"})


def _update_enabled() -> bool:
    return _UPDATE_ALL or _renamed.environ("ASSERTPY_SNAPSHOT_UPDATE").strip().lower() in _TRUTHY


def _ci_mode_enabled() -> bool:
    """Whether snapshot creation is forbidden (a missing snapshot fails instead of being created).

    Precedence: the pytest ``--assertpy-snapshot-ci`` / ``--assertpy-snapshot-no-ci`` flags, then the
    ``ASSERTPY_SNAPSHOT_CI`` env var (explicit on/off), then autodetection of a CI environment (a
    truthy ``CI`` var, set by GitHub Actions, GitLab CI, CircleCI, and most others).
    """
    if _CI_MODE is not None:
        return _CI_MODE
    explicit = _renamed.environ("ASSERTPY_SNAPSHOT_CI").strip().lower()
    if explicit in _FALSY:
        return False
    if explicit in _TRUTHY:
        return True
    return os.environ.get("CI", "").strip().lower() in _TRUTHY


def _inline_literal_or_raise(value: object) -> None:
    """Reject values that cannot round-trip as a source literal (an inline snapshot rewrites source)."""
    if not _inline.is_literalable(value):
        raise TypeError(
            "an inline snapshot literal must be a dict/list/tuple/set of scalars, not"
            f" {type(value).__name__} - use snapshot() to store it in a file instead"
        )


def _combine_ignore(ignore, placeholders):
    """Merge the placeholder keys into the caller's ``ignore`` spec, so token fields are skipped by the
    equality comparison (their matcher is asserted separately)."""
    if not placeholders:
        return ignore
    keys = list(placeholders)
    if ignore is None:
        return keys
    if isinstance(ignore, (list, set, frozenset)):
        return [*keys, *ignore]
    return [*keys, ignore]  # a single key or a nested-path tuple


def _find_orphans(touched):
    """Given the ``(snapname, key)`` pairs touched this session, return obsolete snapshots as
    ``(sub_key_orphans, whole_file_orphans)``.

    A sub-key orphan is ``(snapname, lineno)`` still on disk in a *touched* default-id file whose test
    line was not exercised this run (that specific test was deleted).  A whole-file orphan is a snapshot
    file in a touched directory that was not touched at all (its test/module is gone).  Only directories
    that had at least one live snapshot this run are scanned, so an unrelated directory is never judged.
    """
    touched_files = {snapname for snapname, _ in touched}
    custom_touched = {snapname for snapname, key in touched if key == ""}
    touched_keys: dict[str, set[str]] = {}
    for snapname, key in touched:
        if key != "":
            touched_keys.setdefault(snapname, set()).add(key)

    sub_orphans: list[tuple[str, str]] = []
    whole_orphans: list[str] = []
    for directory in sorted({os.path.dirname(snapname) for snapname, _ in touched}):
        if not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not (fname.startswith("snap-") and fname.endswith(".json")):
                continue
            snapname = os.path.join(directory, fname)
            if snapname not in touched_files:
                whole_orphans.append(snapname)
                continue
            if snapname in custom_touched:
                continue  # a touched whole-file custom-id snapshot is live
            data = _load(snapname)
            live = touched_keys.get(snapname, set())
            sub_orphans.extend((snapname, key) for key in sorted(data) if key not in live)
    return sub_orphans, whole_orphans


def _prune_sub_key_orphans(sub_orphans):
    """Remove obsolete sub-snap keys from their files, deleting a file that becomes empty."""
    by_file: dict[str, set[str]] = {}
    for snapname, key in sub_orphans:
        by_file.setdefault(snapname, set()).add(key)
    for snapname, keys in by_file.items():
        with _file_lock(snapname):
            data = _load(snapname)
            for key in keys:
                data.pop(key, None)
            if data:
                _save(snapname, data)
            else:
                os.unlink(snapname)


@contextlib.contextmanager
def _file_lock(target: str, *, timeout: float = 10.0, poll: float = 0.05) -> Generator[None]:
    """Serialize snapshot read-modify-write across processes via an ``O_EXCL`` lock file.

    Not crash-safe: a process that dies while holding the lock leaves a stale lock file and other
    writers time out.  Accepted: snapshots are development-time files and crashes mid-write are rare.
    """
    lockpath = f"{target}.lock"
    deadline = time.monotonic() + timeout
    lock_fd = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lockpath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:  # noqa: PERF203  # retry the O_EXCL acquire each poll until the lock frees
            if time.monotonic() >= deadline:
                raise TimeoutError(f"could not acquire snapshot lock <{lockpath}> within {timeout}s") from None
            time.sleep(poll)
        except PermissionError:
            # Windows refuses to create a lock file its last holder is still deleting, as access denied
            if sys.platform != "win32" or time.monotonic() >= deadline:
                raise
            time.sleep(poll)
    try:
        yield
    finally:
        os.close(lock_fd)
        os.unlink(lockpath)


def _name(path, name):
    try:
        cleaned = name.replace(" ", "_").lower()
        if os.sep in cleaned or (os.altsep and os.altsep in cleaned):
            # it reached the lock file first, and the reader met a FileNotFoundError naming a directory nobody chose
            raise ValueError(f"snapshot id cannot contain a path separator, but was {name!r}")
        return os.path.join(path, f"snap-{cleaned}.json")
    except (TypeError, AttributeError):
        raise ValueError("failed to create snapshot filename, either bad path or bad name") from None


def _format_shape_drift(drift):
    """Render `shape_diff` entries as an aligned added/removed/retyped report."""
    glyph = {"added": "+", "removed": "-", "retyped": "~"}
    return "\n".join(f"  {glyph[kind]} {where} {detail}".rstrip() for kind, where, detail in drift)


def _update_hint(descriptor: str, action: str) -> str:
    """One sentence naming the snapshot and how to accept the new value, shared by both kinds."""
    return f"{descriptor}; rerun with --assertpy-snapshot-update to {action}."


class SnapshotMixin(_MixinBase):
    """Assertions that compare a value against a stored snapshot, recording it on the first run.

    Capture a python data structure to disk as JSON and compare the current value against it on every
    later run - a few well-placed snapshot tests cover a lot of surface with very little code.

    **On-disk format**

    Snapshots are stored as readable JSON.  For example:

        assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot()

    is stored as:

        {
            "a": 1,
            "b": 2,
            "c": 3
        }

    Most python structures are supported (dict, list, object, and so on).  Values without a native
    JSON form round-trip through typed markers: ``set``, ``complex``, ``datetime``/``date``/``time``
    (timezone-aware included), ``decimal.Decimal``, ``bytes`` (base64-encoded), ``uuid.UUID``, and
    ``Enum`` members.  Any other type can be handled by registering a serializer with
    [`register_snapshot_serializer()`][assertpy.snapshot.register_snapshot_serializer].

    **Updating**

    Run pytest with ``--assertpy-snapshot-update`` (or set ``ASSERTPY_SNAPSHOT_UPDATE`` for other
    runners) and every failing comparison overwrites the stored value instead of failing.

    Each overwrite emits a [`SnapshotUpdatedWarning`][assertpy.snapshot.SnapshotUpdatedWarning], and
    matching snapshots are left untouched.  Deleting the snapshot files and re-running works too - each
    fresh capture emits a [`SnapshotCreatedWarning`][assertpy.snapshot.SnapshotCreatedWarning].  So
    neither a first run nor an update run is ever silent, and both fail explicitly under ``-W error``.

    **CI mode**

    On a first run a missing snapshot is *created* and the test passes.  That is convenient locally,
    but a hazard in CI: a snapshot test whose golden was never committed would create it in the
    ephemeral workspace, pass, and silently disable drift detection for that test.

    In CI mode a missing snapshot is instead a hard failure.  Enable it with the
    ``--assertpy-snapshot-ci`` pytest flag or the ``ASSERTPY_SNAPSHOT_CI`` environment variable; it
    is also auto-enabled when a ``CI`` environment variable is set (the near-universal CI marker).
    Disable the autodetection with ``--assertpy-snapshot-no-ci`` or ``ASSERTPY_SNAPSHOT_CI=0``.
    Local runs are unaffected.
    """

    def _refuse(self, message: str) -> NoReturn:
        """Raise a composed failure, without offering it to the modes that collect one.

        These refusals are about the run's configuration rather than about the value, so they carry no
        expectation and `has_expected` reads false on them.  They still go through the composer, which
        is what puts the value under test on them and makes them readable the way every other failure
        this library raises is.

        Raising rather than collecting is the point.  Each of these guards a line that writes a
        snapshot file, so a soft block that collected one and carried on would write the file the guard
        exists to prevent.
        """
        raise self._failure(self._compose(message, actual=MISSING, expected=MISSING, diff=None, trace=None))

    def _forbid_creation(self, snapname: str) -> None:
        """In CI mode a missing snapshot is a hard failure, not a silent create - the golden was never
        committed, so drift detection for this test would be silently off.

        Under `not_` as well, whose verdict is inverted: a snapshot created there holds the very value it
        is asked to differ from, so the negation failed on the first run and on every run after it.
        """
        if _ci_mode_enabled():
            self._refuse(
                f"snapshot <{snapname}> does not exist and CI mode forbids creating it - commit the"
                " snapshot to source control, or run without CI mode (--assertpy-snapshot-no-ci, or"
                " unset CI / ASSERTPY_SNAPSHOT_CI)"
            )
        if self._answering_another:
            self._refuse(f"snapshot <{snapname}> does not exist, and not_ cannot create one; create it without not_")

    def _rewriting(self) -> bool:
        """Whether a stale snapshot is overwritten: under update mode, and never under `not_`, for the same reason."""
        return _update_enabled() and not self._answering_another

    def _with_placeholder_tokens(self, placeholders):
        """A shallow copy of the dict-like val with placeholder keys replaced by descriptive tokens, so
        the stored snapshot documents the expected shape instead of a volatile captured value."""
        stored = dict(self.val)
        for key, matcher in placeholders.items():
            stored[key] = {"__placeholder__": _describe_matcher(matcher)}
        return stored

    def _recorded(self, placeholders, record: Callable[[], None]) -> bool:
        """Record through *record* where the placeholders hold, checked as every other run checks them.

        Answers whether it recorded.  It does not where a soft block collected a placeholder that failed: a
        value a placeholder refused is never written, on the run that creates a snapshot or on an update.
        """
        if placeholders and not self._check_placeholders(placeholders):
            return False
        record()
        return True

    def _check_placeholders(self, placeholders) -> bool:
        """Assert each placeholder field of val is present and satisfies its matcher (shape, not value).

        Answers whether every one held, for a soft block, where a failure is collected and the caller
        must still not record the value it failed on.
        """
        held = True
        for key, matcher in placeholders.items():
            present = key in self.val
            if not present or not _apply_matcher(matcher, self.val[key]):
                held = False
                actual = _safe_repr(self.val[key]) if present else "missing"
                self.error(
                    f"Expected snapshot placeholder <{key}> to satisfy {_describe_matcher(matcher)}, but was {actual}."
                )
        return held

    def _compared_to_stored(self, stored: object, **options: object) -> Self:
        """`is_equal_to()` against what a snapshot stored, as an answer to the snapshot rather than the caller.

        The keys a snapshot ignores include the placeholders it checks with matchers of their own, so a
        comparison left with nothing to compare still checked them, and no word on it is due.
        """
        answering = self._answering_another
        self._answering_another = True
        try:
            return self.is_equal_to(stored, **options)
        finally:
            self._answering_another = answering

    def _inline_recorded(self, expected: object, placeholders: object, options: dict[str, Any]) -> bool:
        """Whether update mode took this run of `matches_inline()` as a value to write rather than to compare.

        Every run under update mode is handed to the recorder, the ones that still match included, since
        what one case asks to write has to suit every case reaching the call.  One whose placeholder fails
        is taken too, with the failure reported and nothing recorded: it is no value to write.
        """
        if expected is _UNSET:
            if _ci_mode_enabled():
                self._refuse(
                    "inline snapshot is empty and CI mode forbids recording it - record it locally with"
                    " --assertpy-snapshot-update and commit the source"
                )
            if not _update_enabled():
                self._refuse("inline snapshot is empty; run --assertpy-snapshot-update to record it")
            if not self._rewriting():
                self._refuse("inline snapshot is empty, and not_ cannot record one; record it without not_")
            stale = True
        elif self._rewriting():
            stale = self._snapshot_stale(expected, **options)
        else:
            return False
        if stale:
            _inline_literal_or_raise(self.val)
            if placeholders and not self._check_placeholders(placeholders):
                return True
        self._observed(creating=expected is _UNSET, stale=stale, options=options)
        if stale:
            warnings.warn(
                "recorded inline snapshot: this run captured the value into the test source;"
                " subsequent runs compare against it"
                if expected is _UNSET
                else "updated inline snapshot: this run overwrote the stored literal instead of comparing;"
                " subsequent runs compare against it",
                SnapshotCreatedWarning if expected is _UNSET else SnapshotUpdatedWarning,
                stacklevel=caller_stacklevel(),
            )
        return stale

    def _observed(self, *, creating: bool, stale: bool, options: dict[str, Any]) -> None:
        """Hand this run of `matches_inline()` to the recorder, with the comparison it would pass by.

        Options of plain data are copied as they are now, so the run can be asked again at the end of the
        session.  Options holding a function, or ones that cannot be copied, are used as they are, and the
        recorder asks that run only while it runs.
        """
        held = _inline.captured(options)
        pure = not isinstance(held, _inline.Uncaptured) and not _calls_back(options)
        compared = held if not isinstance(held, _inline.Uncaptured) and pure else options
        _inline.observe(
            _require_caller(inspect.currentframe()),
            self.val,
            creating=creating,
            stale=stale,
            accepts=lambda value, candidate: not _stale(self.builder, value, candidate, compared),
            pure=pure,
        )

    def _snapshot_stale(self, snapshot_value, *, ignore, include, tolerance, comparators, rel=None) -> bool:
        """Whether the stored snapshot no longer matches val."""
        options = {"ignore": ignore, "include": include, "tolerance": tolerance, "rel": rel, "comparators": comparators}
        return _stale(self.builder, self.val, snapshot_value, options)

    def snapshot(
        self,
        id: str | None = None,  # noqa: A002  # `id` is the public snapshot-identifier parameter
        path: str = "__snapshots",
        *,
        ignore: object = None,
        include: object = None,
        tolerance: float | None = None,
        rel: float | None = None,
        comparators: dict[Any, Callable[[Any, Any], Any]] | None = None,
        placeholders: Mapping[Any, Matcher[Any] | Callable[[Any], object]] | None = None,
    ) -> Self:
        """Asserts that val is identical to the on-disk snapshot stored previously.

        On the first run, before the snapshot file exists, the value is captured to disk, a
        [`SnapshotCreatedWarning`][assertpy.snapshot.SnapshotCreatedWarning] is emitted, and the test
        passes.  On every later run the value is compared to the stored snapshot and the test fails on
        any mismatch.

        Snapshots live in the ``__snapshots`` directory by default (commit them to source control) and
        are identified by test filename plus line number, unless you pass ``id`` or ``path``.

        In **update mode** (``--assertpy-snapshot-update``, or the ``ASSERTPY_SNAPSHOT_UPDATE`` env
        var) a failing comparison overwrites the stored snapshot and passes, emitting a
        [`SnapshotUpdatedWarning`][assertpy.snapshot.SnapshotUpdatedWarning]; a matching snapshot is
        left untouched.

        In **CI mode** (``--assertpy-snapshot-ci``, ``ASSERTPY_SNAPSHOT_CI``, or an auto-detected
        ``CI`` environment) a *missing* snapshot is a hard ``AssertionError`` instead of being created,
        so an uncommitted golden fails the build rather than silently disabling drift detection.

        The comparison accepts the same selective options as
        [`is_equal_to()`][assertpy.base.BaseMixin.is_equal_to], so volatile fields (timestamps,
        generated ids) or float noise don't break snapshots.  The snapshot file always stores the
        **full** value; the options only shape the comparison.

        Args:
            id: a custom snapshot identifier (defaults to test filename plus line number)
            path: the directory where snapshots are stored (defaults to ``__snapshots``)

        Keyword Args:
            ignore (Hashable | list | set | frozenset | None): the key/field (or collection of
                keys/fields) to ignore when comparing; accepts the same nested-path tuples,
                ``re.Pattern`` and ``type`` specs as ``is_equal_to()``.
            include (Hashable | list | set | frozenset | None): the key/field (or collection of
                keys/fields) to compare, everything else ignored.
            tolerance (float | None): an absolute tolerance that widens ``==`` for every pair of real-number
                leaves, as in ``is_equal_to()``.
            rel (float | None): a tolerance relative to the stored leaf of each pair of real-number leaves,
                either of the two holding being enough, as in ``is_equal_to()``.
            comparators (dict | None): a dict mapping a ``type`` or a field name to an
                ``(actual, expected) -> bool`` predicate that decides every leaf it matches, as in
                ``is_equal_to()``.
            placeholders (dict | None): a dict mapping a top-level key of a *dict-like* val to a
                ``Matcher`` (or callable predicate).  The stored snapshot records a descriptive token
                (``Any<...>``) for that field instead of the volatile value; each run then asserts the
                field is present and satisfies the matcher, not that it equals a fixed value - so a
                generated id or timestamp reads as its shape and never breaks the snapshot.

        Examples:
            Usage:

                assert_that(None).snapshot()
                assert_that(True).snapshot()
                assert_that(1).snapshot()
                assert_that(123.4).snapshot()
                assert_that('foo').snapshot()
                assert_that([1, 2, 3]).snapshot()
                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot()
                assert_that({'a', 'b', 'c'}).snapshot()
                assert_that(1 + 2j).snapshot()
                assert_that(someobj).snapshot()

            By default, snapshots are identified by test filename plus line number.
            Alternately, you can specify a custom identifier using the ``id`` arg:

                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot(id='foo-id')


            By default, snapshots are stored in the ``__snapshots`` directory.
            Alternately, you can specify a custom path using the ``path`` arg:

                assert_that({'a': 1, 'b': 2, 'c': 3}).snapshot(path='my-custom-folder')

            Ignore volatile fields, or tolerate float noise, without touching the stored snapshot:

                assert_that(api_response).snapshot(id='order', ignore=['created_at', ('user', 'session_id')])
                assert_that(metrics).snapshot(id='latency', tolerance=0.001)

            Store a shape token for a volatile field, and assert its shape on every run:

                from assertpy import match

                assert_that(response).snapshot(id='order', placeholders={'id': match.is_uuid()})
                # stored as {"id": {"__placeholder__": "a valid UUID string"}, ...}

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** equal to on-disk snapshot
            TypeError: if ``tolerance`` is not a real number, or ``comparators`` is not a dict of
                callables (validated on every run, including the capturing first one); or if
                ``placeholders`` is given for a non-dict-like val, or maps to a non-matcher value
            ValueError: if ``tolerance`` is ``NaN`` or negative

        Warns:
            SnapshotCreatedWarning: when this run captured a new snapshot instead of comparing
            SnapshotUpdatedWarning: when update mode overwrote a stale snapshot instead of failing
        """
        # a bad tolerance must fail the capturing first run too
        _build_compare_config(tolerance, comparators, rel=rel)
        if placeholders:
            self._require_dict_like(self.val, name="val")  # placeholders address keys of a dict-like value
            for matcher in placeholders.values():
                if not _is_matcher(matcher) and not callable(matcher):
                    raise TypeError("placeholder values must be Matcher instances or callables")
        # the stored snapshot documents placeholders as tokens, so a volatile field never breaks it
        stored_val = self._with_placeholder_tokens(placeholders) if placeholders else self.val
        effective_ignore = _combine_ignore(ignore, placeholders)
        lineno = ""
        if id:
            snapname = _name(path, id)
        else:
            caller = _require_caller(inspect.currentframe())
            file_path = os.path.basename(caller.f_code.co_filename)
            file_name = os.path.splitext(file_path)[0]
            lineno = str(caller.f_lineno)
            snapname = _name(path, file_name)

        _record_access(snapname, "" if id else lineno, f"id={id!r}" if id else f"{file_path}:{lineno}")
        os.makedirs(path, exist_ok=True)

        # serialised so parallel workers do not lose each other's entries; the rewrite decision stays inside the lock
        snapshot_value = _UNSET
        updated = False
        held = True
        with _file_lock(snapname):
            if os.path.isfile(snapname):
                snap = _load(snapname)
                if id:
                    snapshot_value = snap
                elif lineno in snap:
                    snapshot_value = snap[lineno]
                else:
                    self._forbid_creation(snapname)
                    held = self._recorded(placeholders, lambda: _save(snapname, {**snap, lineno: stored_val}))

                if (
                    snapshot_value is not _UNSET
                    and self._rewriting()
                    and self._snapshot_stale(
                        snapshot_value,
                        ignore=effective_ignore,
                        include=include,
                        tolerance=tolerance,
                        rel=rel,
                        comparators=comparators,
                    )
                ):
                    held = updated = self._recorded(
                        placeholders, lambda: _save(snapname, stored_val if id else {**snap, lineno: stored_val})
                    )
            else:
                self._forbid_creation(snapname)
                held = self._recorded(placeholders, lambda: _save(snapname, stored_val if id else {lineno: stored_val}))

        if not held:
            # a soft block collected the placeholder that failed, and a value it failed on is never recorded
            return self
        if updated:
            warnings.warn(
                f"updated snapshot <{snapname}>: this run overwrote the stored value instead of comparing;"
                " subsequent runs compare against it",
                SnapshotUpdatedWarning,
                stacklevel=caller_stacklevel(),
            )
            return self
        if snapshot_value is not _UNSET:
            if placeholders:
                self._check_placeholders(placeholders)
            try:
                return self._compared_to_stored(
                    snapshot_value,
                    ignore=effective_ignore,
                    include=include,
                    tolerance=tolerance,
                    rel=rel,
                    comparators=comparators,
                )
            except AssertionFailure as mismatch:
                # name the snapshot, or the failure reads as a plain `is_equal_to` with no file to open
                located = snapname if id else f"{snapname}::{lineno}"
                raise _rewrapped(
                    mismatch,
                    f"{mismatch._message}{_shared_key_hint(snapname, '' if id else lineno)}"
                    f" {_update_hint(f'Snapshot <{located}>', 'accept the new value')}",
                ) from None
        warnings.warn(
            f"created snapshot <{snapname}>: this run captured the value instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)",
            SnapshotCreatedWarning,
            stacklevel=caller_stacklevel(),
        )
        return self

    def matches_inline(
        self,
        expected: object = _UNSET,
        *,
        ignore: object = None,
        include: object = None,
        tolerance: float | None = None,
        rel: float | None = None,
        comparators: dict[Any, Callable[[Any, Any], Any]] | None = None,
        placeholders: Mapping[Any, Matcher[Any] | Callable[[Any], object]] | None = None,
    ) -> Self:
        """Asserts that val equals an inline snapshot literal written at the call site.

        Unlike [`snapshot()`][assertpy.snapshot.SnapshotMixin.snapshot], which stores the value in a
        separate file, an inline snapshot lives as a literal argument in the test source.

        Call it empty the first time and run with ``--assertpy-snapshot-update`` to record the value
        into the source; later runs compare against it. The same selective knobs as ``snapshot()``
        apply, so volatile fields never make the snapshot brittle.

        The comparison itself is an ordinary equality check with no source introspection, so it works
        under ``pytest-xdist`` and needs neither the ``[inline]`` extra nor any assertion rewriting;
        only recording (empty call under update mode) reads the source.

        Args:
            expected: the recorded literal; omit it to record on the next update run.
            ignore: key(s)/path(s) to skip in the comparison (as in ``is_equal_to``).
            include: restrict the comparison to these key(s)/path(s).
            tolerance: absolute numeric tolerance applied at every depth.
            rel: numeric tolerance relative to the leaf the literal holds, applied at every depth, either
                of the two holding being enough.
            comparators: per-type custom equality callables.
            placeholders: ``{key: matcher}`` for volatile fields - the key is ignored by the equality
                comparison and its matcher asserted separately.

        Examples:
            Usage:

                assert_that({"id": 1, "name": "Alice"}).matches_inline({"id": 1, "name": "Alice"})

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        One call holds one literal: every case that reaches it under update mode has to pass against
        the literal written there, or nothing is written and the run fails naming the call.  Under
        ``not_`` nothing is recorded, since the literal would be the value the negation differs from.

        Raises:
            AssertionError: if val does not equal the recorded literal, or the snapshot is still empty
            TypeError: if update mode has to rewrite an expected value that is not a literal written in
                the call, such as a name or an unpacked argument
        """
        if placeholders:
            self._require_dict_like(self.val, name="val")  # placeholders address keys of a dict-like value
            for matcher in placeholders.values():
                if not _is_matcher(matcher) and not callable(matcher):
                    raise TypeError("placeholder values must be Matcher instances or callables")
        effective_ignore = _combine_ignore(ignore, placeholders)
        options: dict[str, Any] = {
            "ignore": effective_ignore,
            "include": include,
            "tolerance": tolerance,
            "rel": rel,
            "comparators": comparators,
        }
        if self._inline_recorded(expected, placeholders, options):
            return self
        if placeholders:
            self._check_placeholders(placeholders)
        try:
            return self._compared_to_stored(expected, **options)
        except AssertionFailure as mismatch:
            # the stored snapshot lives in this very call, and updating rewrites it in place
            raise _rewrapped(
                mismatch, f"{mismatch._message} {_update_hint('Inline snapshot', 'rewrite the literal here')}"
            ) from None

    def matches_contract_snapshot(self, id: str | None = None, path: str = "__snapshots") -> Self:  # noqa: A002  # `id` is the public snapshot-identifier parameter
        """Asserts that val's *structure* matches a contract snapshot stored previously.

        Records the shape - paths and type categories, never values - on the first run, then on later
        runs fails only on **structural** drift: a field added, removed, or retyped.

        It is value-tolerant by construction, so dynamic ids, timestamps, and amounts change freely
        without breaking the snapshot, and it needs no hand-written model - the contract is inferred
        from the first response.  Numbers are one category (``5`` and ``5.0`` do not drift), and a
        ``null`` sample is a nullable wildcard.

        The model-driven counterpart is
        [`assert_conforms(..., exact=True)`][assertpy.assertpy.assert_conforms]: reach for that when you
        already have a pydantic model, and for this when you would rather capture the shape from a real
        response.

        Honors the same update mode (``--assertpy-snapshot-update``), CI mode
        (``--assertpy-snapshot-ci``), and storage layout as
        [`snapshot()`][assertpy.snapshot.SnapshotMixin.snapshot].

        Because a contract is inferred from a single observation it cannot know which fields are
        optional, so a legitimately sometimes-absent field reads as ``removed``; re-record with update
        mode when the contract really changed.

        Args:
            id: a custom snapshot identifier (defaults to test filename plus line number)
            path: the directory where snapshots are stored (defaults to ``__snapshots``)

        Examples:
            Usage:

                assert_that(response.json()).matches_contract_snapshot()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's structure drifts from the stored contract snapshot

        Warns:
            SnapshotCreatedWarning: when this run captured a new contract instead of comparing
            SnapshotUpdatedWarning: when update mode overwrote a drifted contract instead of failing
        """
        contract = shape(self.val)
        lineno = ""
        if id:
            snapname = _name(path, id)
        else:
            caller = _require_caller(inspect.currentframe())
            file_path = os.path.basename(caller.f_code.co_filename)
            file_name = os.path.splitext(file_path)[0]
            lineno = str(caller.f_lineno)
            snapname = _name(path, file_name)

        _record_access(snapname, "" if id else lineno, f"id={id!r}" if id else f"{file_path}:{lineno}")
        os.makedirs(path, exist_ok=True)

        stored = _UNSET
        updated = False
        with _file_lock(snapname):
            if os.path.isfile(snapname):
                snap = _load(snapname)
                if id:
                    stored = snap
                elif lineno in snap:
                    stored = snap[lineno]
                else:
                    self._forbid_creation(snapname)
                    snap[lineno] = contract
                    _save(snapname, snap)

                if stored is not _UNSET and self._rewriting() and shape_diff(stored, contract):
                    if id:
                        _save(snapname, contract)
                    else:
                        snap[lineno] = contract
                        _save(snapname, snap)
                    updated = True
            else:
                self._forbid_creation(snapname)
                _save(snapname, contract if id else {lineno: contract})

        if updated:
            warnings.warn(
                f"updated contract snapshot <{snapname}>: this run overwrote the stored shape instead of"
                " comparing; subsequent runs compare against it",
                SnapshotUpdatedWarning,
                stacklevel=caller_stacklevel(),
            )
            return self
        if stored is not _UNSET:
            drift = shape_diff(stored, contract)
            if drift:
                located = snapname if id else f"{snapname}::{lineno}"
                return self.error(
                    f"Expected <{_truncated(_safe_str(self.val))}> to match contract snapshot, but the structure"
                    f" drifted:\n{_format_shape_drift(drift)}\n"
                    f"{_update_hint(f'Contract snapshot <{located}>', 'accept the new shape')}",
                    actual=self.val,
                )
            return self
        warnings.warn(
            f"created contract snapshot <{snapname}>: this run captured the shape instead of comparing;"
            " subsequent runs compare against it (delete the file to re-capture)",
            SnapshotCreatedWarning,
            stacklevel=caller_stacklevel(),
        )
        return self
