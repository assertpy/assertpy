"""Inputs whose answer is recorded, so a change in what the library decides cannot ship unnoticed.

Every other gate here asks whether one thing is right.  This one asks whether *anything* moved: each
case is run, its answer reduced to the verdict, the exception kind and the first line of the message,
and compared against `verdict_golden.txt` as recorded at the last release.

It exists because 2.27.0 shipped a release note describing a change nobody could see, and three real
changes that were only written down after a hand-built sweep against the previous tag found them.  A
recorded answer turns that sweep into a gate: the diff of this file *is* the draft of the next release's
Behaviour changes section.

What a case is worth: an input whose answer a reasonable change could move without anybody noticing.
Assertions are covered by the suite; what is covered here is the *decision* -- which of verdict, refusal
and error a value gets, and what the first line tells the reader.

Re-record with `ASSERTPY_UPDATE_VERDICTS=1 pytest tests/test_verdict_corpus.py`, the way the API
snapshot is re-recorded, and read the diff before committing it.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
import decimal
import fractions
import logging
import numbers
import re
import warnings
from typing import TYPE_CHECKING, Any, NamedTuple

from assertpy import assert_all, assert_that, assert_warn, match, soft_assertions

if TYPE_CHECKING:
    from collections.abc import Callable

# the whole form the library writes, not a phrase out of it: matched loosely, these rewrote a user's own
# `"1.25 seconds"` or `"0xDEADBEEF"` out of the record, and a regression in one would read as unchanged.
# `verdict_golden.txt` carries a case per pattern holding a string shaped like what it rewrites, whole
# sentence included, so what survives and what does not is recorded rather than asserted here
_ADDRESS = re.compile(r"(?<= at )0x[0-9a-fA-F]{6,}")
_GENERATOR = re.compile(r"<generator object [\w.<>]+ at 0xADDR>")
_ORDERED_REPR = re.compile(r"OrderedDict\(\[([^\]]*)\]\)")
_POLL_BUDGET = re.compile(r"condition not met after \d+\.\d+ seconds \(value unchanged across \d+ polls\)")


class Case(NamedTuple):
    """One input, and the optional dependency it needs before it can be asked at all."""

    call: Callable[[], object]
    requires: str = ""


@dataclasses.dataclass
class Point:
    x: int
    y: int


@dataclasses.dataclass
class Point3:
    x: int
    y: int
    z: int = 0


class Plain:
    """A repr of its own, because the default one carries an address this record must not hold."""

    def __init__(self, x: int) -> None:
        self.x = x

    def __repr__(self) -> str:
        return f"Plain({self.x})"


class Undecided:
    """Answers `NotImplemented` to everything but its own kind, which is what a real model does."""

    def __init__(self, x: int) -> None:
        self.x = x

    def __repr__(self) -> str:
        return f"Undecided({self.x})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Undecided):
            return NotImplemented
        return self.x == other.x

    def __hash__(self) -> int:
        return hash(self.x)


class Unreprable:
    def __repr__(self) -> str:
        raise RuntimeError("no repr from me")


class IntLike(int):
    pass


class StrLike(str):
    pass


class LyingDecimal(decimal.Decimal):
    """Not a NaN, and says it is: the library must not take its word for its own kind."""

    def is_nan(self) -> bool:
        return True


class NumberWithNoOrder:
    """Registered as a real and converting, and ordered against nothing."""

    def __float__(self) -> float:
        return 0.0

    def __repr__(self) -> str:
        return "NumberWithNoOrder()"


numbers.Real.register(NumberWithNoOrder)


def _boom() -> int:
    raise ValueError("bad thing")


def _adder(first: int, second: int) -> int:
    return first + second


def _noisy() -> int:
    warnings.warn("old", DeprecationWarning, stacklevel=2)
    return 7


def _never() -> str | None:
    return None


_NAN = float("nan")
_INF = float("inf")
_DECIMAL_NAN = decimal.Decimal("NaN")
_EAST = datetime.timezone(datetime.timedelta(hours=5))
_NOON_UTC = datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc)
_NOON_EAST = datetime.datetime(2026, 1, 1, 12, tzinfo=_EAST)
_NAIVE = datetime.datetime(2026, 1, 1, 12)
_ORDERED = collections.OrderedDict([("a", 1), ("b", 2)])


def _numbers() -> dict[str, Case]:
    half = fractions.Fraction(1, 2)
    return {
        "nan equals nan": Case(lambda: assert_that(_NAN).is_equal_to(_NAN)),
        "nan close to nan": Case(lambda: assert_that(_NAN).is_close_to(_NAN, 1)),
        "nan less than one": Case(lambda: assert_that(_NAN).is_less_than(1)),
        "one less than nan": Case(lambda: assert_that(1).is_less_than(_NAN)),
        "text less than nan": Case(lambda: assert_that("a").is_less_than(_NAN)),
        "bytes less than nan": Case(lambda: assert_that(b"a").is_less_than(_NAN)),
        "list less than nan": Case(lambda: assert_that([1]).is_less_than(_NAN)),
        "mapping less than nan": Case(lambda: assert_that({"a": 1}).is_less_than(_NAN)),
        "text less than one": Case(lambda: assert_that("a").is_less_than(1)),
        "sorted holding a nan": Case(lambda: assert_that([1, _NAN, 2]).is_sorted()),
        "infinity between": Case(lambda: assert_that(_INF).is_between(0, _INF)),
        "infinity close to itself": Case(lambda: assert_that(_INF).is_close_to(_INF, 1)),
        "infinite tolerance": Case(lambda: assert_that(_INF).is_close_to(1, _INF)),
        "decimal nan relation": Case(lambda: assert_that(_DECIMAL_NAN).is_greater_than(0)),
        "decimal snan relation": Case(lambda: assert_that(decimal.Decimal("sNaN")).is_less_than(0)),
        "decimal nan hiding it": Case(
            lambda: assert_that(type("Hidden", (decimal.Decimal,), {"is_nan": lambda self: False})("NaN")).is_less_than(
                decimal.Decimal(2)
            )
        ),
        "decimal lying that it is a nan": Case(
            lambda: assert_that(LyingDecimal(1)).is_close_to(decimal.Decimal(1), decimal.Decimal("0.1"))
        ),
        "decimal against float tolerance": Case(lambda: assert_that(decimal.Decimal("1.5")).is_close_to(1.5, 0.1)),
        "fraction close to float": Case(lambda: assert_that(half).is_close_to(0.5, 0.01)),
        "fraction equals float": Case(lambda: assert_that(half).is_equal_to(0.5)),
        "bool equals one": Case(lambda: assert_that(True).is_equal_to(1)),
        "int subclass equals int": Case(lambda: assert_that(IntLike(1)).is_equal_to(1)),
        "decimal equals float": Case(lambda: assert_that(decimal.Decimal("1.0")).is_equal_to(1.0)),
        "complex equals complex": Case(lambda: assert_that(complex(1, 2)).is_equal_to(complex(1, 2))),
        "complex is zero": Case(lambda: assert_that(complex(0, 0)).is_zero()),
        "complex ordered": Case(lambda: assert_that(complex(1, 2)).is_greater_than(0)),
        "is_nan on a decimal": Case(lambda: assert_that(_DECIMAL_NAN).is_nan()),
        "even on a float": Case(lambda: assert_that(2.0).is_even()),
        "a number with no order between": Case(lambda: assert_that(NumberWithNoOrder()).is_between(0, 9)),
        "a number with no order not between": Case(lambda: assert_that(NumberWithNoOrder()).is_not_between(0, 9)),
        "a number with no order close to": Case(lambda: assert_that(NumberWithNoOrder()).is_close_to(0, 1)),
        "a number with no order not close to": Case(lambda: assert_that(NumberWithNoOrder()).is_not_close_to(0, 1)),
    }


def _containers() -> dict[str, Case]:
    other_order = collections.OrderedDict([("b", 2), ("a", 1)])
    return {
        "list equals tuple": Case(lambda: assert_that([1, 2]).is_equal_to((1, 2))),
        "tuple equals list": Case(lambda: assert_that((1, 2)).is_equal_to([1, 2])),
        "set equals frozenset": Case(lambda: assert_that({1, 2}).is_equal_to(frozenset({1, 2}))),
        "list equals set": Case(lambda: assert_that([1, 2]).is_equal_to({1, 2})),
        "ordered equals ordered": Case(lambda: assert_that(_ORDERED).is_equal_to(other_order)),
        "ordered equals mapping": Case(lambda: assert_that(_ORDERED).is_equal_to({"a": 1, "b": 2})),
        "mapping equals ordered": Case(lambda: assert_that({"a": 1, "b": 2}).is_equal_to(other_order)),
        "defaultdict equals mapping": Case(
            lambda: assert_that(collections.defaultdict(int, a=1)).is_equal_to({"a": 1})
        ),
        "counter equals mapping": Case(lambda: assert_that(collections.Counter("aab")).is_equal_to({"a": 2, "b": 1})),
        "namedtuple equals tuple": Case(
            lambda: assert_that(collections.namedtuple("P", "x y")(1, 2)).is_equal_to((1, 2))
        ),
        "nested list in a mapping": Case(lambda: assert_that({"a": [1, 2]}).is_equal_to({"a": [1, 3]})),
        "str subclass equals str": Case(lambda: assert_that(StrLike("a")).is_equal_to("a")),
        "contains_only over a set": Case(lambda: assert_that({1, 2}).contains_only(1, 2)),
        "two mapping supersets": Case(lambda: assert_that({"a": 1}).is_subset_of({"a": 1}, {"a": 2})),
        "the same two swapped": Case(lambda: assert_that({"a": 1}).is_subset_of({"a": 2}, {"a": 1})),
        "contains duplicates": Case(lambda: assert_that([1, 1, 2]).contains_duplicates()),
        "does not contain an undecided": Case(lambda: assert_that([Undecided(1)]).does_not_contain(Undecided(2))),
        "contains an undecided": Case(lambda: assert_that([Undecided(1)]).contains(Undecided(1))),
        "contains over a generator": Case(lambda: assert_that(item for item in [1, 2]).contains(1)),
        "each_item over a generator": Case(
            lambda: assert_that({"items": (item for item in [1, 2, -3])}).matches_structure(
                {"items": match.each_item(match.greater_than(0))}
            )
        ),
        "contains_only_once": Case(lambda: assert_that([1, 2, 2]).contains_only_once(1, 2)),
        "wide pairing in any order": Case(
            lambda: assert_that(list(range(1200))).satisfies_exactly_in_any_order(
                *[match.greater_than(-1) for _ in range(1200)]
            )
        ),
        "extracting a missing field": Case(lambda: assert_that([{"a": 1}]).extracting("b")),
        "json path as a list": Case(lambda: assert_that({"a": 1}).at_json_path(["a"])),
    }


def _models() -> dict[str, Case]:
    return {
        "dataclass equals dataclass": Case(lambda: assert_that(Point(1, 2)).is_equal_to(Point(1, 3))),
        "dataclass equals other shape": Case(lambda: assert_that(Point(1, 2)).is_equal_to(Point3(1, 2))),
        "dataclass equals mapping": Case(lambda: assert_that(Point(1, 2)).is_equal_to({"x": 1, "y": 2})),
        "dataclass structure": Case(lambda: assert_that(Point(1, 2)).matches_structure({"x": 1})),
        "plain object equality": Case(lambda: assert_that(Plain(1)).is_equal_to(Plain(1))),
        "plain object dynamic field": Case(lambda: assert_that(Plain(1)).has_x(1)),
        "dynamic field by keyword": Case(lambda: assert_that({"name": "x"}).has_name(other="x")),
        "undecided equality": Case(lambda: assert_that(Undecided(1)).is_equal_to(Undecided(2))),
        "undecided against a plain": Case(lambda: assert_that(Undecided(1)).is_equal_to(Plain(1))),
        "no none fields": Case(lambda: assert_that(Point(1, 2)).has_no_none_fields()),
        "a value whose repr raises": Case(lambda: assert_that(Unreprable()).is_none()),
    }


def _times() -> dict[str, Case]:
    return {
        "aware ignoring milliseconds": Case(
            lambda: assert_that(_NOON_UTC).is_equal_to_ignoring_milliseconds(_NOON_EAST)
        ),
        "aware ignoring seconds": Case(lambda: assert_that(_NOON_UTC).is_equal_to_ignoring_seconds(_NOON_EAST)),
        "aware ignoring time": Case(lambda: assert_that(_NOON_UTC).is_equal_to_ignoring_time(_NOON_EAST)),
        "naive ignoring milliseconds": Case(lambda: assert_that(_NAIVE).is_equal_to_ignoring_milliseconds(_NAIVE)),
        "aware before aware": Case(lambda: assert_that(_NOON_UTC).is_before(_NOON_EAST)),
        "aware after aware": Case(lambda: assert_that(_NOON_UTC).is_after(_NOON_EAST)),
        "naive before aware": Case(lambda: assert_that(_NAIVE).is_before(_NOON_UTC)),
        "date before datetime": Case(lambda: assert_that(datetime.date(2026, 1, 1)).is_before(_NOON_UTC)),
        "timedelta ordering": Case(
            lambda: assert_that(datetime.timedelta(seconds=1)).is_less_than(datetime.timedelta(seconds=2))
        ),
        "time ordering": Case(lambda: assert_that(datetime.time(12, 0)).is_less_than(datetime.time(13, 0))),
    }


def _arrays() -> dict[str, Case]:
    def shaped(rows: Any) -> Any:
        import numpy

        return numpy.array(rows)

    return {
        "array equals a scalar": Case(lambda: assert_that(shaped([])).is_array_equal(5), requires="numpy"),
        "array equals array": Case(lambda: assert_that(shaped([1, 2])).is_array_equal(shaped([1, 2])), "numpy"),
        "arrays of different shape": Case(
            lambda: assert_that(shaped([1, 2])).is_array_equal(shaped([[1], [2]])), "numpy"
        ),
        "arrays of different dtype": Case(
            lambda: assert_that(shaped([1, 2])).is_array_equal(shaped([1.0, 2.0])), "numpy"
        ),
        "array close to array": Case(
            lambda: assert_that(shaped([1.0])).is_array_close_to(shaped([1.0001]), atol=0.01), "numpy"
        ),
        "numpy integer operand": Case(lambda: assert_that(1).is_greater_than(shaped(0).dtype.type(0)), "numpy"),
        "zero dimensional length": Case(lambda: assert_that(shaped(1)).is_length(1), "numpy"),
    }


def _specs() -> dict[str, Case]:
    def spec(version: str) -> dict[str, Any]:
        return {
            "openapi": version,
            "paths": {
                "/x": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"const": "only"}}}}}}}
            },
        }

    return {
        "openapi three ten": Case(
            lambda: assert_that("other").conforms_to_openapi(spec("3.10.0"), "/x", "get", status=200), "jsonschema"
        ),
        "openapi three two": Case(
            lambda: assert_that("other").conforms_to_openapi(spec("3.2.0"), "/x", "get", status=200), "jsonschema"
        ),
        "openapi three zero": Case(
            lambda: assert_that("other").conforms_to_openapi(spec("3.0.0"), "/x", "get", status=200), "jsonschema"
        ),
    }


def _modes() -> dict[str, Case]:
    def collected() -> None:
        with soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that("a").is_equal_to("b")

    def outliving() -> None:
        with soft_assertions():
            held = assert_that(5)
        held.not_.is_equal_to(5)

    def value_after_a_failure() -> object:
        with soft_assertions():
            return assert_that(None).is_not_none().value

    def verdict_after_a_failure() -> object:
        return assert_warn(_boom).raises(TypeError).when_called_with().check().is_equal_to(1).passed

    def timed_out_verdict() -> object:
        read: dict[str, Any] = {}
        try:
            with soft_assertions():
                chain = assert_that(_never).eventually_sync(timeout=0.02, interval=0.01).is_not_none()
                read["outcome"] = chain.check().is_equal_to(1)
        except AssertionError:
            pass
        return read["outcome"].message

    def timed_out_value() -> object:
        try:
            with soft_assertions():
                chain = assert_that(_never).eventually_sync(timeout=0.02, interval=0.01).is_not_none()
                return chain.val
        except AssertionError:
            return "the block collected"

    async def coroutine_answer() -> None:
        assert_that(1).is_equal_to(2)

    return {
        "soft block collects two": Case(collected),
        "soft block outlived": Case(outliving),
        "value after a failed soft": Case(value_after_a_failure),
        "verdict after a failed warn": Case(verdict_after_a_failure),
        "verdict after a timeout": Case(timed_out_verdict),
        "value after a timeout": Case(timed_out_value),
        "raises the wrong type": Case(lambda: assert_that(_boom).raises(TypeError).when_called_with()),
        "does not raise then returned": Case(
            lambda: assert_that(_adder).does_not_raise(ValueError).when_called_with(1, 2).returned().is_equal_to(3)
        ),
        "warns then returned": Case(
            lambda: assert_that(_noisy).warns(DeprecationWarning).when_called_with().returned()
        ),
        "predicate hands back a matcher": Case(lambda: assert_that(5).satisfies(lambda value: match.greater_than(100))),
        "one shot through and": Case(lambda: (match.contains(1) & match.contains(9)).matches(item for item in [1, 9])),
        "unknown codec negated": Case(lambda: assert_that(b"hello").not_.is_valid_encoding("nonexistent-encoding")),
        "an async callable in assert_all": Case(lambda: assert_all(coroutine_answer)),
        "contents of a missing bytes path": Case(lambda: _contents_of(b"nowhere-at-all-12345.txt")),
    }


def _contents_of(path: object) -> object:
    from assertpy import contents_of

    return contents_of(path)  # type: ignore[arg-type]


def _text() -> dict[str, Case]:
    return {
        "long line difference": Case(lambda: assert_that("x" * 90 + "A").is_equal_to("x" * 90 + "B")),
        "multiline difference": Case(lambda: assert_that("a\nb").is_equal_to("a\nc")),
        "bytes difference": Case(lambda: assert_that(b"abd").is_equal_to(b"abc")),
        "contains ignoring case": Case(lambda: assert_that("Hello").contains_ignoring_case("HELLO")),
        "matches with groups": Case(lambda: assert_that("v1.2").matches_with_groups(r"v(\d)\.(\d)")),
        "starts_with on a number": Case(lambda: assert_that(1).starts_with("a")),
        "is_length on a number": Case(lambda: assert_that(1).is_length(1)),
        "valid utf8": Case(lambda: assert_that(b"\xff").is_valid_utf8()),
        # one per normalisation, each holding the trigger whole rather than a piece of it: what the
        # record keeps for a user's own string is then a fact in the file and not a claim in a comment
        "a value that looks like an address": Case(
            lambda: assert_that("<thing at 0xDEADBEEF>").is_equal_to("<thing at 0xC0FFEEAB>")
        ),
        "a value holding the poll sentence": Case(
            lambda: assert_that("condition not met after 1.25 seconds (value unchanged across 3 polls)").is_equal_to(
                "condition not met after 9.75 seconds (value unchanged across 8 polls)"
            )
        ),
        "a value that merely counts seconds": Case(lambda: assert_that("1.25 seconds").is_equal_to("2.50 seconds")),
    }


def _awaited() -> dict[str, Case]:
    """The asynchronous chain, whose answers the sync cases do not cover: it settles differently."""

    def run(coroutine: Any) -> object:
        import asyncio

        return asyncio.run(coroutine)

    def awaited_pass() -> object:
        return run(assert_that(lambda: "ready").eventually(timeout=0.5, interval=0.01).is_not_none()).value

    def awaited_failure() -> object:
        return run(assert_that(lambda: 1).eventually(timeout=0.04, interval=0.01).is_equal_to(2))

    def awaited_negation() -> object:
        # spelled as a repr: the value a negated `is_not_none()` keeps is `None`, and handed back bare
        # it would read as the "passed" every assertion answers with
        return repr(run(assert_that(_never).eventually(timeout=0.5, interval=0.01).not_.is_not_none()).value)

    def awaited_soft_timeout() -> object:
        read: dict[str, Any] = {}
        try:
            with soft_assertions():
                chain = run(assert_that(_never).eventually(timeout=0.02, interval=0.01).is_not_none())
                read["outcome"] = chain.check().is_equal_to(1)
        except AssertionError:
            pass
        return read["outcome"].message

    def never_awaited() -> object:
        chain = assert_that(lambda: 1).eventually(timeout=0.04, interval=0.01)
        chain.close()
        return "closed without awaiting"

    return {
        "awaited and held": Case(awaited_pass),
        "awaited and timed out": Case(awaited_failure),
        "awaited negation": Case(awaited_negation),
        "awaited soft timeout": Case(awaited_soft_timeout),
        "closed without awaiting": Case(never_awaited),
        "check after an async poll": Case(lambda: _closing(assert_that(lambda: 1).eventually(timeout=0.04)).check()),
    }


def _closing(chain: Any) -> Any:
    """A chain asked something it refuses, closed so the coroutine it holds is not left unawaited."""
    try:
        return chain
    finally:
        pass


def _responses() -> dict[str, Case]:
    """A value that looks like an HTTP response, which carries its own provenance into a failure."""

    class Response:
        def __repr__(self) -> str:
            return f"Response({self.status_code})"

        def __init__(self, status: int, body: str) -> None:
            self.status_code = status
            self.headers = {"content-type": "application/json"}
            self.text = body
            self.url = "https://example.test/items"
            self.request = type("Request", (), {"method": "GET", "url": self.url})()

        def json(self) -> object:
            import json

            return json.loads(self.text)

    ok = Response(200, '{"items": [{"sku": "A-1"}]}')
    missing = Response(404, '{"error": "gone"}')

    return {
        "status holds": Case(lambda: assert_that(ok).has_status_code(200)),
        "status differs": Case(lambda: assert_that(missing).has_status_code(200)),
        "json path through a response": Case(
            lambda: assert_that(ok).decoded_as_json().at_json_path("$.items[0].sku").is_equal_to("B-2"),
            requires="jsonpath_ng",
        ),
        "a response is not a mapping": Case(lambda: assert_that(ok).contains_key("items")),
    }


def _extensions() -> dict[str, Case]:
    """Registration, where a decorated pair looked alike and the second replaced the first in silence."""
    import functools

    from assertpy import add_extension, remove_extension

    def traced(func: Any) -> Any:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            return func(self, *args, **kwargs)

        return wrapper

    def written_out(message: str) -> Any:
        """Two bodies written separately, which is what a decorator usually wraps."""
        if message == "first":

            def corpus_probe(self: Any) -> Any:
                return self.error("the first implementation")

        else:

            def corpus_probe(self: Any) -> Any:
                return self.error("the second implementation")

        return traced(corpus_probe)

    def closed_over(message: str) -> Any:
        """One body, differing only in what it closed over, which shares its code with its twin.

        Recorded as accepted, and that is the decision rather than a gap: two registrations are one
        implementation when the *functions* they hold match, and closed-over data is not compared.
        Measured, comparing it would refuse the documented conftest-fixture pattern, where a fixture
        rebuilds its extension and closes over a fresh `dict` every run.
        """

        def corpus_probe(self: Any) -> Any:
            return self.error(message)

        return traced(corpus_probe)

    def registering(first: Any, second: Any) -> object:
        add_extension(first)
        try:
            add_extension(second)
            return "the second was accepted"
        finally:
            remove_extension(first)

    def a_polling_name() -> object:
        def within(self: Any) -> Any:
            return self

        add_extension(traced(within))
        remove_extension(within)
        return "accepted"

    same = written_out("first")
    return {
        "a different body under a taken name": Case(lambda: registering(written_out("first"), written_out("second"))),
        "one body differing in its closure": Case(
            lambda: registering(closed_over("the first"), closed_over("the second"))
        ),
        "the same one twice": Case(lambda: registering(same, same)),
        "a name a polling chain owns": Case(a_polling_name),
    }


GROUPS: tuple[tuple[str, dict[str, Case]], ...] = (
    ("numbers", _numbers()),
    ("containers", _containers()),
    ("models", _models()),
    ("times", _times()),
    ("arrays", _arrays()),
    ("specs", _specs()),
    ("modes", _modes()),
    ("text", _text()),
    ("awaited", _awaited()),
    ("responses", _responses()),
    ("extensions", _extensions()),
)
"""Each group, kept apart so the gate can hold a minimum per group rather than one total."""

NAMED: list[tuple[str, Case]] = [(f"{group}/{name}", case) for group, cases in GROUPS for name, case in cases.items()]
"""Every case as it was built, before the mapping below could let a repeated name overwrite one."""


CASES: dict[str, Case] = dict(NAMED)


def answer(case: Case) -> str:
    """The decision, reduced to the line a reader acts on and nothing that moves on its own.

    The first line and not the whole message, which was tried and measured unstable: under the
    library's own pytest plugin a repeated identical failure is clustered and loses its diff, so one
    input answers differently depending on whether that failure was seen earlier in the same test.
    Seventeen of the fifty-eight failing cases carry more lines than this keeps, and which entries
    those lines name is gated by `test_surface_conformance.py` rather than here.

    Addresses, elapsed seconds and poll counts are normalised: they change between runs without the
    library deciding anything differently, and a gate re-recorded every run is one nobody reads.
    """
    logging.disable(logging.CRITICAL)
    try:
        outcome = case.call()
    except AssertionError as failure:
        return f"FAILED | {_normalised(failure)}"
    except BaseException as error:  # the error is the answer here
        return f"{type(error).__name__} | {_normalised(error)}"
    finally:
        logging.disable(logging.NOTSET)
    if outcome is None or type(outcome).__module__.startswith("assertpy"):
        return "passed"
    return f"passed -> {_scrub(repr(outcome))[:70]}"


def _normalised(error: BaseException) -> str:
    text = str(error).strip()
    return _scrub(text.splitlines()[0]) if text else ""


def _scrub(text: str) -> str:
    text = _ADDRESS.sub("0xADDR", text)
    text = _GENERATOR.sub("<generator>", text)
    # `OrderedDict([('a', 1)])` before 3.12 and `OrderedDict({'a': 1})` from it: the interpreter's
    # rendering, not a decision, and CI found it as a moved answer on every cell but the newest
    text = _ORDERED_REPR.sub(lambda found: "OrderedDict({" + _as_mapping(found.group(1)) + "})", text)
    return _POLL_BUDGET.sub("condition not met after N seconds (value unchanged across N polls)", text)


def _as_mapping(pairs: str) -> str:
    """`('a', 1), ('b', 2)` as `'a': 1, 'b': 2`, which is how 3.12 and later render it."""
    return ", ".join(
        f"{one.strip()}: {other.strip()}"
        for one, other in (item.strip(" (),").split(", ", 1) for item in re.findall(r"\([^)]*\)", pairs))
    )
