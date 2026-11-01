"""Group a run's failures by the difference they share, so a wall of red reads as one cause.

Forty failing tests are usually not forty problems.  A fixture that changed one field fails every test
that touches it, and pytest reports each one on its own because a rendered `AssertionError` is all it
has.  This library keeps the comparison as structure, so the same forty can be answered in a line:
*thirty-seven of them differ at `user.role`*.

The grouping is by equality, never by likeness.  Two failures share a cluster when their signatures are
equal, and a signature is built from the diff itself.  There is no similarity score to tune and no
ordering to depend on: the same run produces the same clusters.

Where a value is identified rather than compared, what stands for it is its stable repr, so two values
that print alike count as one difference.  That is a real limit and the honest one to state: a summary
cannot hold the values themselves without shipping a run's whole payload between processes.

**The key is the place, not the values, and that was measured rather than assumed.**  An earlier
edition put the values in the key, which reads as the safer choice and quietly narrows the feature to
one case: a broken constant, where all forty failures show the same pair.  A broken *formula* differs
at the same field with a value of its own per test, and keying on values scattered it into forty
clusters of one.  Both are ordinary, and only the first was covered.

So an entry is keyed on its path whenever the path is a coordinate (`key`, `index`, `attr` or `line`
steps).  Values are collected as examples instead, and a cluster whose values disagree says so rather
than printing one pair as though it explained every failure it holds.

**Three kinds of difference carry no coordinate at all**, which an audit of every diff kind this
library emits established:

* a `contains` failure names `missing` or `extra`, which is a label, not a place - an item that is not
  in a list has no position in it;
* a `set` entry's step holds the *member*, since a set has no index to give;
* a `scalar` entry is the whole value, and its path renders as `.`.

Keying those on their path would put every unrelated `contains` failure in one cluster called
`missing`.  They fall back to the diagnostic line the failure already carries - *every difference here
is one of surrounding whitespace* - which is the same difference stated as a kind rather than a place.

Without a diagnostic, only the kinds whose two fields really hold the compared values fall back to
them.  `contains` and `set` do not: there the fields hold *presence*, so a missing item reports `None`
on the actual side, and a heading built from that tells the reader their value was `None` when it was
a list of three.  Those two stay out of the summary rather than getting a second rendering, which was
the cheaper half of a measurement showing they clustered almost nothing.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final, NamedTuple

from .errors import _safe_repr

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .errors import DiffEntry, DiffResult

__tracebackhide__ = True

# steps that name a *place* in a value, as opposed to `item`, which names a member of a set
_COORDINATE: Final = frozenset({"key", "index", "attr", "line"})

# a position collapses to one placeholder: `users[0].role` and `users[7].role` are one difference on two rows
_POSITIONAL: Final = frozenset({"index", "line"})
_ANY_POSITION: Final = "[*]"

_VALUES_ARE_VALUES: Final = frozenset({"scalar", "string"})
"""Location-free kinds whose ``actual`` and ``expected`` hold the two values being compared.

For `contains` and `set` those fields hold *presence* instead: a missing item reports `None` on the
actual side, which as a cluster heading reads as a claim that the value under test was `None`.  Those
two group only on a diagnostic, and stay out of the summary entirely without one.  The alternative,
inventing a second rendering for them, buys a family that clustered almost nothing on measurement.
"""

_EXAMPLE_LIMIT: Final = 64
"""Distinct values a cluster keeps per side before it starts saying "and more" instead.

One past this many are actually held, so the length of the tuple is itself the answer to "was this
capped": at `_EXAMPLE_LIMIT + 1` the summary prints a floor rather than a count.

Twenty thousand failures differing at one field held twenty thousand example values, 888 KB, to print
one of them and a count.  The smallest value is tracked separately so the printed example stays the
same whatever order the failures arrived in, which is the property the sort was there for.
"""

_MAX_CLUSTERS: Final = 5
"""Clusters the summary prints, after which it says how many it left out.

Eligibility is a property of one cluster and is decided by `MINIMUM_SIZE`.  How much of the screen the
summary may take is a separate question, and a red run has already used the screen for tracebacks.
"""

_VALUE_LIMIT: Final = 200
"""Characters of a value the summary will print, and ship between xdist workers.

The message itself caps at 400 per side and 4000 overall.  A summary line is denser than a message and
sits in the last screen of the run, so it caps harder: three failures over a 500 KB response body
otherwise put a megabyte and a half on the terminal and the same again through execnet.
"""

MINIMUM_SIZE: Final = 3
"""Failures a cluster must hold before it is worth printing.

An absolute floor, deliberately, after a share of the run's failures was tried and measured strictly
worse.  A share means every additional cause raises the bar for all the others, so a run of forty
failures splitting cleanly into five causes of eight printed nothing at all - the summary went quiet
on exactly the runs that most needed one.  A floor does not have that property, and the
trailing line already tells the reader how much of the run fell outside a cluster of this size.
"""


class Signature(NamedTuple):
    """What makes two failures the same failure.

    ``located`` says which family the signature belongs to, and therefore how to read ``where``: a
    canonical path for a difference that has a position, and the diff's kind for one that does not.

    ``where`` is written for a reader and ``steps`` decides identity, because the two cannot be the
    same string.  A path renders a mapping key bare, so ``{3: ...}`` and ``{"3": ...}`` both read as
    ``3``, and grouping on that text would merge two differences that have nothing in common - the
    exact ambiguity `DiffEntry.steps` exists to remove.  ``steps`` keeps each key's repr, so the two
    stay apart while the summary still prints the readable form.

    ``label`` and ``values`` are what separate two location-free differences, and exactly one of them
    is ever set: the failure's own diagnostic line when it had one, the pair of values when it did
    not.  Both stay empty for a located signature, whose place is the whole key.
    """

    located: bool
    where: str
    steps: tuple[tuple[str, str], ...] = ()
    label: str = ""
    values: tuple[str, ...] = ()


class Observation(NamedTuple):
    """One failure's contribution to a cluster: what it is keyed on, and what it actually showed."""

    signature: Signature
    actual: str
    expected: str


class Cluster(NamedTuple):
    """One signature, the tests that produced it, and the values they showed.

    ``actuals`` and ``expecteds`` hold the distinct values *sorted*, so the summary can print the pair
    when a cluster agrees on one and say how many there are when it does not.  Sorted rather than in
    order of appearance, because under xdist that order is the order the workers happened to finish in,
    and the same failing run printed a different example each time.

    They are counted separately on purpose: forty tests differing at `role` can hold forty actual
    values against a single expected one, and reporting that expected value is the useful half.

    A side keeps at most one past `_EXAMPLE_LIMIT` distinct values, so the tuple's own length is what
    says the count was capped: see that constant for why the extra one is held.
    """

    signature: Signature
    nodeids: tuple[str, ...]
    actuals: tuple[str, ...] = ()
    expecteds: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return len(self.nodeids)


def stable_repr(value: object, _seen: frozenset[int] = frozenset()) -> str:
    """``repr`` with set ordering pinned, so the same value reads the same in any process.

    A set reprs in iteration order, which follows the hash seed, so two identical failures on two
    xdist workers - separate processes, separate seeds - produced different signatures and never
    clustered.  The symptom was the feature going silent on exactly the runs it exists for.

    Sets are sorted by their members' own stable repr, and containers are walked so a set nested
    inside one is reached.  Everything else keeps plain ``repr``: a dict's order is the reader's own,
    and pinning it here would print a value the failure message never showed.

    Walking containers means owning the two hazards `repr` already handles and the diff engine already
    guards: a value that contains itself, and a container that raises when iterated - a detached ORM
    collection, a lazy wrapper over a closed connection.  Both used to escape from a summary hook,
    which pytest answers with INTERNALERROR, so a whole run reported nothing at all.
    """
    if id(value) in _seen:
        return "..."  # `repr` marks the same thing, wrapped in the container's own brackets
    inner = _seen | {id(value)}
    try:
        if isinstance(value, (set, frozenset)):
            members = sorted(stable_repr(member, inner) for member in value)
            # an empty one falls back to `repr`: `{}` is a dict, so `set()` and the `frozenset()` it equals read apart
            return "{" + ", ".join(members) + "}" if value else _safe_repr(value)
        if isinstance(value, dict):
            pairs = (f"{stable_repr(key, inner)}: {stable_repr(item, inner)}" for key, item in value.items())
            return "{" + ", ".join(pairs) + "}"
        if isinstance(value, list):
            return "[" + ", ".join(stable_repr(item, inner) for item in value) + "]"
        if isinstance(value, tuple):
            walked = ", ".join(stable_repr(item, inner) for item in value)
            return f"({walked},)" if len(value) == 1 else f"({walked})"
    except Exception:  # iterating is the user's code, and it must not outrank the failure being reported
        return _safe_repr(value)
    return _safe_repr(value)


def canonical_steps(entry: DiffEntry) -> tuple[tuple[str, str], ...] | None:
    """The entry's location as ``(kind, repr)`` hops, or ``None`` when it has no location.

    Indices collapse to one placeholder, and every other hop keeps its value's repr rather than its
    text, so two keys that render alike stay apart.
    """
    # entering JSON text is no place of its own: what lies in it is found by the same keys from one run to the next
    steps = tuple(step for step in entry.steps if step.kind != "json")
    if not steps or any(step.kind not in _COORDINATE for step in steps):
        return None
    return tuple((step.kind, _ANY_POSITION if step.kind in _POSITIONAL else stable_repr(step.value)) for step in steps)


def render_path(steps: tuple[tuple[str, str], ...]) -> str:
    """The readable form of a canonical location: ``users[*].role``, ``line [n]``."""
    parts = []
    for kind, value in steps:
        if kind == "index":
            parts.append(_ANY_POSITION)
        elif kind == "line":
            parts.append("line [n]")
        else:
            plain = value[1:-1] if len(value) > 1 and value[0] == value[-1] == "'" else value
            parts.append(f".{plain}" if parts else plain)
    return _bounded("".join(parts))


def _bounded(text: str) -> str:
    """*text* cut to what a summary line can carry, saying how much it dropped."""
    return text if len(text) <= _VALUE_LIMIT else f"{text[:_VALUE_LIMIT]}... ({len(text) - _VALUE_LIMIT} more chars)"


def _shown(value: object) -> str:
    """A value as the summary will print it: stable across processes and bounded in length."""
    return _bounded(stable_repr(value))


class _Absent:
    """A side that held nothing at all.

    An absent key carries `None`, and read as a value it printed as ``None`` and keyed with every
    failure whose value really is `None`.
    """

    def __repr__(self) -> str:
        return "<absent>"


_ABSENT = _Absent()


def _side_of(entry: DiffEntry, side: str) -> object:
    """One side of an entry, or the absent marker where that side held nothing."""
    return _ABSENT if entry.absent == side else (entry.actual if side == "actual" else entry.expected)


def _identity(value: object) -> str:
    """A value as a cluster key: the whole of it, in a fixed number of characters.

    The printed form cannot serve: it is cut at `_VALUE_LIMIT`, so two payloads sharing a long prefix
    would key alike and the summary would announce a difference they do not share.  Keying on the whole
    text instead would put a megabyte on the wire per failure, which is what the cut is there to stop.
    A digest is both.  What it gives up is stated where the module says what "the same difference" means:
    identity is over the text a value prints as, and the chance of two different texts colliding in
    sixteen bytes is not one a test run reaches.
    """
    return hashlib.blake2b(stable_repr(value).encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


def signature(diff: DiffResult, entry: DiffEntry, label: str | None = None) -> Signature | None:
    """The cluster key for one entry of one failure, or ``None`` when it has nothing to share.

    ``label`` is the failure's diagnostic line, when it had one.  It keys the location-free family,
    where it is the only thing two differences can share once their values are set aside.
    """
    steps = canonical_steps(entry)
    if steps is not None:
        return Signature(True, render_path(steps), steps)
    if label:
        return Signature(False, diff.kind, label=label)
    if diff.kind not in _VALUES_ARE_VALUES:
        return None
    return Signature(
        False, diff.kind, values=(_identity(_side_of(entry, "actual")), _identity(_side_of(entry, "expected")))
    )


def is_well_formed(key: Signature) -> bool:
    """Whether a signature is one this module could have produced.

    A signature only ever arrives from outside over the xdist wire, and a payload whose every field has
    the right type can still describe a difference that cannot exist: a located key with no steps to
    locate it, or a location-free key holding a diagnostic and a pair of values at once.  Either prints a
    heading the structure behind it does not support, which is the one thing this summary must not do.
    """
    if key.located:
        return (
            bool(key.steps)
            and all(kind in _COORDINATE for kind, _ in key.steps)
            and not key.label
            and not key.values
            and key.where == render_path(key.steps)
        )
    if key.steps:
        return False
    # a pair of values only for the kinds whose fields hold them, or a `contains` payload prints a `None`
    if key.label:
        return not key.values
    return len(key.values) == 2 and key.where in _VALUES_ARE_VALUES


def observations_of(diff: DiffResult | None, label: str | None = None) -> list[Observation]:
    """Every distinct signature one failure contributes, each with the values that produced it.

    A failure differing at three fields belongs to three clusters, which is the useful reading: the
    cluster that grows is the field they all share, and the ones that do not grow fall below the floor
    and stay quiet.
    """
    if diff is None or not diff.entries:
        return []
    seen: dict[Signature, Observation] = {}
    for entry in diff.entries:
        key = signature(diff, entry, label)
        if key is not None:
            seen.setdefault(
                key, Observation(key, _shown(_side_of(entry, "actual")), _shown(_side_of(entry, "expected")))
            )
    return list(seen.values())


def clusters(
    recorded: Sequence[tuple[str, Iterable[Observation]]],
    total_failures: int,
    *,
    minimum: int = MINIMUM_SIZE,
) -> list[Cluster]:
    """The clusters worth reporting, largest first.

    ``recorded`` is one entry per failing test: its node id and what that failure contributed.
    ``total_failures`` counts every test that went red, including those whose failure carried no diff at
    all, because the summary reports how much of the run it accounts for.  Tests rather than reports: one
    test can go red twice, failing its assertion and then erroring in teardown, and pytest counts that as
    a failure and an error.  Counting both would let two numbers describe three tests.
    """
    if total_failures <= 0:
        return []
    # keyed on the node id: `pytest-rerunfailures` retries printed a cluster of six over two tests
    grouped: dict[Signature, dict[str, None]] = {}
    actuals: dict[Signature, dict[str, None]] = {}
    expecteds: dict[Signature, dict[str, None]] = {}
    for nodeid, found in recorded:
        for one in found:
            grouped.setdefault(one.signature, {})[nodeid] = None
            # one past the limit, so a full side is distinguishable from a capped one by its length alone
            for store, value in ((actuals, one.actual), (expecteds, one.expected)):
                seen = store.setdefault(one.signature, {})
                if len(seen) <= _EXAMPLE_LIMIT:
                    seen[value] = None
                elif value < min(seen):
                    seen.pop(max(seen))
                    seen[value] = None
    large = [
        Cluster(key, tuple(nodeids), tuple(sorted(actuals[key])), tuple(sorted(expecteds[key])))
        for key, nodeids in grouped.items()
        if len(nodeids) >= minimum
    ]
    # size first, then the signature: two clusters of equal size must not swap places between runs
    large.sort(key=lambda cluster: (-cluster.size, cluster.signature))
    return large


def _spelled_out(steps: tuple[tuple[str, str], ...]) -> str:
    """A location written so no two of them can read alike: ``key=3`` against ``key='3'``.

    Cutting it would undo that for two long keys sharing a prefix, which is the case this spelling exists
    for, so what is cut keeps a digest of the whole: the reader gets a short pair of headings that are
    still different from each other.
    """
    spelled = ".".join(f"{kind}={value}" for kind, value in steps)
    if len(spelled) <= _VALUE_LIMIT:
        return spelled
    digest = hashlib.blake2b(spelled.encode("utf-8", "surrogatepass"), digest_size=4).hexdigest()
    return f"{spelled[:_VALUE_LIMIT]}... [{digest}]"


def _headings(found: Sequence[Cluster]) -> list[str]:
    """One heading per cluster, disambiguated only where two would otherwise read the same.

    A readable path drops the quotes around a mapping key, so ``{3: ...}`` and ``{"3": ...}`` both
    print as ``3``.  They are correctly held apart as clusters, and printing them identically hands
    the reader two blocks that look like a rendering bug.  The precise spelling is used only for the
    clusters that collide, so the ordinary summary keeps reading as a path.
    """
    plain = [one.signature.where for one in found]
    clashing = {name for name in plain if plain.count(name) > 1}
    spelled = [
        _spelled_out(one.signature.steps) if name in clashing and one.signature.located else name
        for name, one in zip(plain, found, strict=True)
    ]
    return _made_unique(spelled)


def _made_unique(names: list[str]) -> list[str]:
    """Number whatever still reads alike, so two headings can never be one.

    The spelling above tells two locations apart by what they hold, and a location long enough to be cut
    keeps a digest of the rest, which identifies it but cannot promise uniqueness.  This can: the summary
    is one screen of text, and two lines the reader cannot tell apart is the failure mode either half was
    there to prevent.
    """
    seen: dict[str, int] = {}
    numbered = []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        numbered.append(name if names.count(name) == 1 else f"{name} #{seen[name]}")
    return numbered


def _headline(cluster: Cluster, where: str, total_failures: int) -> str:
    """A cluster's first line, in the grammar its family allows.

    A located cluster has somewhere to point at.  A location-free one does not, and saying they "differ
    at (string)" claims a place where the only thing shared is the shape of the difference: the reader is
    told they differ *in a string*, which is not what the cluster knows.  The line under it carries the
    substance either way, the diagnostic or the two values.
    """
    if cluster.signature.located:
        return f"{cluster.size} of {total_failures} failing tests differ at {where}"
    return f"{cluster.size} of {total_failures} failing tests share one {where} difference"


def _side(values: tuple[str, ...]) -> str:
    """One side of a cluster: the value when they agree, an example and a count when they do not.

    A cluster keyed on a place can hold failures whose values differ, and printing the first of them
    as though it were the difference is the one way this summary could mislead.  Saying how many there
    are keeps the reader's next move right: one value is a fact to act on, twelve is a place to look.
    """
    first, rest = values[0], len(values) - 1
    if not rest:
        return first
    if len(values) > _EXAMPLE_LIMIT:  # the side was capped, so the count is a floor rather than a total
        return f"{first} and {_EXAMPLE_LIMIT}+ other values"
    return f"{first} and {rest} other value{'' if rest == 1 else 's'}"


def render(
    found: Sequence[Cluster],
    total_failures: int,
    lost_workers: int = 0,
    unreadable_workers: int = 0,
    minimum: int = MINIMUM_SIZE,
    collect_errors: int = 0,
) -> list[str]:
    """The summary lines, or an empty list when there is nothing worth saying.

    ``lost_workers`` counts the xdist workers that died without shipping what they had recorded, and
    ``unreadable_workers`` those that finished and shipped something this version could not read.  Both
    leave failures out of every number below, and they are counted apart because they are different
    claims about the run: a summary that reports a crash where a worker merely spoke another dialect is
    itself the kind of false statement this one exists to avoid.  Either way the counts are partial, and
    saying so beats presenting a share of a run only partly seen: a crashed worker turned twenty failures
    into a confident `10 of 10`.

    Every count here is over *tests*, which is why the lines say so: a test that fails and then errors in
    teardown is two red results and one broken test, and the summary is about the second reading.

    ``collect_errors`` counts collection failures, which `--continue-on-collection-errors` lets a run
    carry past.  They are red and they are not tests, so they are said on their own line rather than
    folded into a count of tests that would then be larger than the tests there were.  Collection is not
    only modules either: a package or a plugin's own collector can fail, so the line says what it counts
    rather than guessing what was being collected.
    """
    if not found:
        return []
    shown, omitted = found[:_MAX_CLUSTERS], found[_MAX_CLUSTERS:]
    lines = []
    if lost_workers:
        plural = "" if lost_workers == 1 else "s"
        lines.append(f"{lost_workers} worker{plural} died, so these counts cover only what was reported")
    if unreadable_workers:
        plural = "" if unreadable_workers == 1 else "s"
        lines.append(
            f"the failures of {unreadable_workers} worker{plural} could not be read, "
            f"so these counts cover only the rest"
        )
    if collect_errors:
        one = collect_errors == 1
        lines.append(f"{collect_errors} collection error{'' if one else 's'}, not counted below")
    for cluster, where in zip(shown, _headings(shown), strict=True):
        lines.append(_headline(cluster, where, total_failures))
        # a cluster keyed on its diagnostic says the difference in words; the values are what varies inside it
        if cluster.signature.label:
            lines.append(f"    {cluster.signature.label}")
        else:
            lines.append(f"    actual:   {_side(cluster.actuals)}")
            lines.append(f"    expected: {_side(cluster.expecteds)}")
    if omitted:
        # said rather than dropped: "five of eleven" silently reads as "these are the causes".  "more" rather
        # than "smaller", since equal-sized clusters are ordered by signature
        lines.append(f"{len(omitted)} more cluster{'' if len(omitted) == 1 else 's'} not shown")
    covered = len({nodeid for cluster in found for nodeid in cluster.nodeids})
    if covered < total_failures:
        # what the number measures, not "not clustered": the summary declined to print a pair under the floor
        lines.append(f"{total_failures - covered} of {total_failures} outside any cluster of {minimum}")
    return lines
