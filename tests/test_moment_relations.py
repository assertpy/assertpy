"""A moment held against a moment: the failure says how far apart the two are.

``2026-01-01 12:00:00+00:00`` is not before ``2026-01-01 13:30:00+02:00``, and the sentence shows two clocks
nobody subtracts at a glance.  A line under it gives the distance: half an hour after, the same moment, seven
seconds apart and two more than the tolerance.  The distance is the base type's own subtraction, exact to the
microsecond, and it is said only where the base type made the verdict and the line agrees with it.
"""

from __future__ import annotations

import datetime as dt
import importlib
import re
import sys
import zoneinfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from assertpy import AssertionFailure, _hints, assert_that
from assertpy.date import DateMixin

UTC = dt.timezone.utc
PLUS_ONE = dt.timezone(dt.timedelta(hours=1))
PLUS_TWO = dt.timezone(dt.timedelta(hours=2))
NOON = dt.datetime(2026, 1, 1, 12)
TICK = dt.timedelta(microseconds=1)
SAME = "the two are the same moment"
SAME_CLOCK = "the two read the same on the clock they share"


def _lines(call) -> list[str]:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return caught.value._message.splitlines()


def _passes(call) -> bool:
    try:
        call()
    except AssertionFailure:
        return False
    return True


def _later(**amount) -> dt.datetime:
    return NOON + dt.timedelta(**amount)


class TestAMomentOnTheWrongSide:
    @pytest.mark.parametrize(
        ("name", "value", "other", "said"),
        [
            ("is_before", _later(hours=3), NOON, "the value is 3:00:00 after the moment given"),
            ("is_before", NOON, NOON, SAME),
            ("is_before_or_equal_to", _later(seconds=1), NOON, "the value is 0:00:01 after the moment given"),
            ("is_after", NOON, _later(days=1, hours=2), "the value is 1 day, 2:00:00 before the moment given"),
            ("is_after", NOON, NOON, SAME),
            ("is_after_or_equal_to", NOON, _later(minutes=5), "the value is 0:05:00 before the moment given"),
            (
                "is_after",
                NOON.replace(microsecond=120001),
                NOON.replace(microsecond=123456),
                "the value is 0:00:00.003455 before the moment given",
            ),
        ],
    )
    def test_the_line_says_how_far(self, name, value, other, said):
        lines = _lines(lambda: getattr(assert_that(value), name)(other))
        assert_that(lines).is_length(2)
        assert_that(lines[1]).is_equal_to(said)

    def test_two_clocks_are_read_as_the_moments_they_are(self):
        value = NOON.replace(tzinfo=UTC)
        lines = _lines(lambda: assert_that(value).is_before(NOON.replace(hour=13, minute=30, tzinfo=PLUS_TWO)))
        assert_that(lines[0]).contains("<2026-01-01 12:00:00+00:00> to be before <2026-01-01 13:30:00+02:00>")
        assert_that(lines[1]).is_equal_to("the value is 0:30:00 after the moment given")
        lines = _lines(lambda: assert_that(value).is_after(NOON.replace(hour=13, tzinfo=PLUS_ONE)))
        assert_that(lines[1]).is_equal_to(SAME)

    @pytest.mark.parametrize(
        ("value", "other", "before", "strict"),
        [
            (NOON, _later(hours=1), True, True),
            (_later(hours=1), NOON, False, True),
            (NOON, NOON, True, False),
            (NOON, NOON, False, False),
            (_later(hours=1), NOON.replace(tzinfo=UTC), True, True),
            ("2026-01-01", NOON, True, True),
            (NOON, None, False, True),
        ],
        ids=["before as asked", "after as asked", "equal, or before", "equal, or after", "naive and aware", *"ab"],
    )
    def test_nothing_is_said_where_the_line_would_not_agree_with_the_verdict(self, value, other, before, strict):
        assert_that(_hints.out_of_order(value, other, before=before, strict=strict)).is_none()


class TestTwoMomentsAgainstATolerance:
    @pytest.mark.parametrize(
        ("other", "tolerance", "said"),
        [
            (_later(seconds=7), dt.timedelta(seconds=5), "the two are 0:00:07 apart, 0:00:02 more than the tolerance"),
            (_later(seconds=-7), dt.timedelta(seconds=5), "the two are 0:00:07 apart, 0:00:02 more than the tolerance"),
            (
                _later(milliseconds=900),
                dt.timedelta(milliseconds=500),
                "the two are 0:00:00.900000 apart, 0:00:00.400000 more than the tolerance",
            ),
            (
                _later(days=2),
                dt.timedelta(),
                "the two are 2 days, 0:00:00 apart, 2 days, 0:00:00 more than the tolerance",
            ),
        ],
    )
    def test_not_close_says_the_distance_and_what_is_past_the_tolerance(self, other, tolerance, said):
        lines = _lines(lambda: assert_that(NOON).is_close_to(other, tolerance))
        assert_that(lines).is_length(2)
        assert_that(lines[1]).is_equal_to(said)

    def test_two_zones_are_read_as_the_moments_they_are(self):
        other = NOON.replace(tzinfo=PLUS_ONE)
        lines = _lines(lambda: assert_that(NOON.replace(tzinfo=UTC)).is_close_to(other, dt.timedelta(minutes=5)))
        assert_that(lines[0]).contains("<2026-01-01 12:00:00+00:00> to be close to <2026-01-01 12:00:00+01:00>")
        assert_that(lines[1]).is_equal_to("the two are 1:00:00 apart, 0:55:00 more than the tolerance")

    @pytest.mark.parametrize(
        ("other", "tolerance", "said"),
        [
            (_later(seconds=3), dt.timedelta(seconds=5), "the two are 0:00:03 apart, 0:00:02 less than the tolerance"),
            (_later(seconds=-5), dt.timedelta(seconds=5), "the two are 0:00:05 apart, which is the tolerance"),
            (NOON, dt.timedelta(seconds=5), SAME),
            (NOON, dt.timedelta(), SAME),
        ],
    )
    def test_close_says_the_distance_and_what_is_left_of_the_tolerance(self, other, tolerance, said):
        lines = _lines(lambda: assert_that(NOON).is_not_close_to(other, tolerance))
        assert_that(lines).is_length(2)
        assert_that(lines[1]).is_equal_to(said)

    @pytest.mark.parametrize(
        ("other", "tolerance", "close"),
        [
            (NOON, dt.timedelta(seconds=5), True),
            (_later(seconds=3), dt.timedelta(seconds=5), True),
            (_later(seconds=5), dt.timedelta(seconds=5), True),
            (_later(seconds=7), dt.timedelta(seconds=5), False),
            (_later(seconds=7), 5, True),
            ("2026-01-01", dt.timedelta(seconds=5), True),
        ],
        ids=[
            "the same, asked close",
            "within, asked close",
            "on the edge, asked close",
            "past it, asked apart",
            "a number",
            "a text",
        ],
    )
    def test_nothing_is_said_where_the_line_would_not_agree_with_the_verdict(self, other, tolerance, close):
        assert_that(_hints.apart_in_time(NOON, other, tolerance, close=close)).is_none()

    def test_two_numbers_get_no_line(self):
        assert_that(_lines(lambda: assert_that(1.5).is_close_to(5, 1))).is_length(1)
        assert_that(_lines(lambda: assert_that(1.5).is_not_close_to(2, 1))).is_length(1)


_ORDERING = ("__lt__", "__le__", "__gt__", "__ge__")
_MEASURING = ("__eq__", "__sub__", "__rsub__", "__add__", "__radd__", "__float__")


def _writes(name: str) -> type[dt.datetime]:
    """A class of datetimes that writes *name* itself, as the base type has it."""
    return type("Own", (dt.datetime,), {name: getattr(dt.datetime, name, lambda self: 0.0)})


class _SubtractsItsOwnWay(dt.datetime):
    def __sub__(self, other):
        return dt.timedelta(hours=99)


class _AddsNothing(dt.datetime):
    def weekday_name(self) -> str:
        return self.strftime("%A")


class _Tolerance(dt.timedelta):
    pass


class _Key(str):
    __slots__ = ()


_ASKED: list[object] = []


class _Armed(str):
    """A key that lands where ``__lt__`` is looked up, and tells when a lookup asks it."""

    __slots__ = ()

    def __hash__(self) -> int:
        return hash("__lt__")

    def __eq__(self, other: object) -> bool:
        _ASKED.append(other)
        return False


class _FallsBack(dt.tzinfo):
    """Two hours east until its clocks read 03:00 on 1 November 2026, then 02:00 again and one hour east."""

    def utcoffset(self, moment):
        wall = moment.replace(tzinfo=None)
        if wall < dt.datetime(2026, 11, 1, 2) or (wall < dt.datetime(2026, 11, 1, 3) and not moment.fold):
            return dt.timedelta(hours=2)
        return dt.timedelta(hours=1)

    def tzname(self, moment):
        return "falls back"

    def dst(self, moment):
        return None


class _GivesNoOffset(dt.tzinfo):
    def utcoffset(self, moment):
        return None

    def tzname(self, moment):
        return None

    def dst(self, moment):
        return None


TURN = _FallsBack()


def _clock(hour: int, minute: int = 0, *, fold: int = 0) -> dt.datetime:
    """A reading of the clock that falls back, on the day it does."""
    return dt.datetime(2026, 11, 1, hour, minute, tzinfo=TURN, fold=fold)


_LINE_ASKED: list[dt.datetime] = []


class _TellsWhenTheLineAsks(dt.tzinfo):
    """An hour east, and a record of each time the line is the one asking, known by who is on the stack."""

    def utcoffset(self, moment):
        frame = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename.endswith("_hints.py"):
                _LINE_ASKED.append(moment)
            frame = frame.f_back
        return dt.timedelta(hours=1)

    def tzname(self, moment):
        return "east"

    def dst(self, moment):
        return None


def _oslo() -> zoneinfo.ZoneInfo | None:
    try:
        return zoneinfo.ZoneInfo("Europe/Oslo")
    except zoneinfo.ZoneInfoNotFoundError:
        return None


OSLO = _oslo()
needs_a_zone_database = pytest.mark.skipif(OSLO is None, reason="no zone database on this machine")


def _oslo_clock(hour: int, minute: int = 0, *, fold: int = 0) -> dt.datetime:
    """A reading of Oslo's clock on 25 October 2026, when 03:00 becomes 02:00."""
    return dt.datetime(2026, 10, 25, hour, minute, tzinfo=OSLO, fold=fold)


class TestOnlyWhereTheBaseTypeMadeTheVerdict:
    def test_a_class_that_writes_no_operator_is_read(self):
        late = _AddsNothing(2026, 1, 1, 15)
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))[1]).is_equal_to(
            "the value is 3:00:00 after the moment given"
        )
        assert_that(_lines(lambda: assert_that(NOON).is_after(late))[1]).is_equal_to(
            "the value is 3:00:00 before the moment given"
        )
        assert_that(_lines(lambda: assert_that(late).is_close_to(NOON, dt.timedelta(hours=1)))[1]).is_equal_to(
            "the two are 3:00:00 apart, 2:00:00 more than the tolerance"
        )

    @pytest.mark.parametrize("name", _ORDERING)
    def test_a_class_that_orders_itself_gets_no_line(self, name):
        late = _writes(name)(2026, 1, 1, 15)
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))).is_length(1)
        assert_that(_lines(lambda: assert_that(NOON).is_after(late))).is_length(1)
        assert_that(_lines(lambda: assert_that(late).is_close_to(NOON, dt.timedelta(hours=1)))).is_length(1)
        assert_that(_lines(lambda: assert_that(NOON).is_not_close_to(late, dt.timedelta(hours=4)))).is_length(1)

    @pytest.mark.parametrize("name", _MEASURING)
    def test_a_class_that_measures_itself_is_read_for_order_and_not_for_distance(self, name):
        late = _writes(name)(2026, 1, 1, 15)
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))).is_length(2)
        assert_that(_lines(lambda: assert_that(NOON).is_after(late))).is_length(2)
        assert_that(_lines(lambda: assert_that(late).is_close_to(NOON, dt.timedelta(hours=1)))).is_length(1)
        assert_that(_lines(lambda: assert_that(NOON).is_close_to(late, dt.timedelta(hours=1)))).is_length(1)

    def test_the_distance_is_the_base_type_s_and_not_what_the_class_answers(self):
        late = _SubtractsItsOwnWay(2026, 1, 1, 15)
        assert_that(late - NOON).is_equal_to(dt.timedelta(hours=99))
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))[1]).is_equal_to(
            "the value is 3:00:00 after the moment given"
        )
        late, east = _SubtractsItsOwnWay(2026, 1, 1, 15, tzinfo=UTC), NOON.replace(tzinfo=PLUS_ONE)
        assert_that(late - east).is_equal_to(dt.timedelta(hours=99))
        assert_that(_lines(lambda: assert_that(late).is_before(east))[1]).is_equal_to(
            "the value is 4:00:00 after the moment given"
        )

    def test_a_tolerance_of_a_class_of_its_own_gets_no_line(self):
        assert_that(_lines(lambda: assert_that(NOON).is_close_to(_later(hours=3), _Tolerance(hours=1)))).is_length(1)
        assert_that(_lines(lambda: assert_that(NOON).is_not_close_to(NOON, _Tolerance(hours=1)))).is_length(1)

    def test_no_name_is_looked_up_in_a_class_keyed_by_a_text_of_its_own(self):
        keyed = type("Keyed", (dt.datetime,), {_Armed("note"): 1})
        late = keyed(2026, 1, 1, 15)
        _ASKED.clear()
        assert_that(_hints.out_of_order(late, NOON, before=True, strict=True)).is_none()
        assert_that(_hints.apart_in_time(late, NOON, dt.timedelta(hours=1), close=True)).is_none()
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))).is_length(1)
        assert_that(_ASKED).is_empty()
        assert_that("__lt__" in vars(keyed)).is_false()
        assert_that(set(_ASKED)).is_equal_to({"__lt__"})

    def test_a_class_keyed_by_a_text_of_its_own_gets_no_line(self):
        keyed = type("Keyed", (dt.datetime,), {_Key("note"): 1})
        assert_that(_lines(lambda: assert_that(keyed(2026, 1, 1, 15)).is_before(NOON))).is_length(1)

    def test_a_pandas_timestamp_keeps_what_the_base_type_cannot_measure(self):
        pandas = pytest.importorskip("pandas")
        late = pandas.Timestamp("2026-01-01 15:00:00.000000500")
        assert_that(_lines(lambda: assert_that(late).is_before(NOON))).is_length(1)
        assert_that(_lines(lambda: assert_that(late).is_close_to(NOON, dt.timedelta(hours=1)))).is_length(1)

    def test_a_tree_without_the_base_type_is_no_moment(self):
        assert_that(_hints._left_to_datetime(object, ("__sub__",))).is_false()


_SAYS = {
    "is_before": lambda: assert_that(_later(hours=1)).is_before(NOON),
    "is_after": lambda: assert_that(NOON).is_after(_later(hours=1)),
    "is_before_or_equal_to": lambda: assert_that(_later(hours=1)).is_before_or_equal_to(NOON),
    "is_after_or_equal_to": lambda: assert_that(NOON).is_after_or_equal_to(_later(hours=1)),
}
_SILENT = {
    "is_equal_to_ignoring_milliseconds": lambda: assert_that(NOON).is_equal_to_ignoring_milliseconds(_later(hours=1)),
    "is_equal_to_ignoring_seconds": lambda: assert_that(NOON).is_equal_to_ignoring_seconds(_later(hours=1)),
    "is_equal_to_ignoring_time": lambda: assert_that(NOON).is_equal_to_ignoring_time(_later(days=1)),
}


class TestEveryAssertionOfTwoMoments:
    """By name, so a new assertion of two moments is entered here as saying a line or as not saying one."""

    def test_every_assertion_of_the_date_mixin_is_entered(self):
        written = {name for name, value in vars(DateMixin).items() if callable(value) and not name.startswith("_")}
        assert_that(written).is_equal_to(set(_SAYS) | set(_SILENT))

    @pytest.mark.parametrize("name", sorted(_SAYS))
    def test_it_says_how_far(self, name):
        assert_that(_lines(_SAYS[name])).described_as(name).is_length(2)

    @pytest.mark.parametrize("name", sorted(_SILENT))
    def test_it_says_nothing(self, name):
        assert_that(_lines(_SILENT[name])).described_as(name).is_length(1)

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that(NOON).not_.is_before(_later(hours=1)),
            lambda: assert_that(_later(hours=1)).not_.is_after(NOON),
            lambda: assert_that(NOON).not_.is_less_than(_later(hours=1)),
            lambda: assert_that(NOON).is_between(_later(hours=1), _later(hours=2)),
            lambda: assert_that(_later(hours=1)).is_not_between(NOON, _later(hours=2)),
            lambda: assert_that(dt.date(2026, 1, 2)).is_less_than(dt.date(2026, 1, 1)),
            lambda: assert_that(dt.timedelta(hours=2)).is_less_than(dt.timedelta(hours=1)),
            lambda: assert_that(5).is_less_than(3),
        ],
        ids=["not_.is_before", "not_.is_after", "not_.is_less_than", "is_between", "is_not_between", *"abc"],
    )
    def test_a_negation_a_range_and_what_is_no_datetime_say_nothing(self, ask):
        assert_that(_lines(ask)).is_length(1)


_TWINS = {
    "is_less_than": "is_before",
    "is_less_than_or_equal_to": "is_before_or_equal_to",
    "is_greater_than": "is_after",
    "is_greater_than_or_equal_to": "is_after_or_equal_to",
}
_NEVER_EQUAL = type("NeverEqual", (dt.datetime,), {"__eq__": lambda self, other: False, "__hash__": None})


def _asked_both_ways(name, value, other) -> tuple[list[str] | None, list[str] | None]:
    """What the relation of numbers says past its sentence, and what its twin of dates says: ``None`` for a pass."""
    said = []
    for each in (name, _TWINS[name]):
        if _passes(lambda each=each: getattr(assert_that(value), each)(other)):
            said.append(None)
        else:
            said.append(_lines(lambda each=each: getattr(assert_that(value), each)(other))[1:])
    return said[0], said[1]


class TestARelationOfNumbersOnTwoMoments:
    """`is_less_than` and its three kin take two datetimes, and say of them what `is_before` and its kin say."""

    @pytest.mark.parametrize("name", sorted(_TWINS))
    @pytest.mark.parametrize(
        ("value", "other"),
        [
            (_later(hours=3), NOON),
            (NOON, _later(hours=3)),
            (NOON, NOON),
            (NOON.replace(microsecond=123456), NOON.replace(microsecond=120001)),
            (NOON.replace(tzinfo=UTC), NOON.replace(hour=13, minute=30, tzinfo=PLUS_TWO)),
            (NOON.replace(tzinfo=UTC), NOON.replace(hour=13, tzinfo=PLUS_ONE)),
            (_clock(2, 30), _clock(2, 30, fold=1)),
            (_clock(0, 30), _clock(4, 30)),
            (_clock(4, 30), _clock(0, 30)),
            (_clock(0, 30), NOON.replace(tzinfo=UTC)),
            (NOON.replace(tzinfo=UTC), _clock(0, 30)),
            (_AddsNothing(2026, 1, 1, 15), NOON),
            (NOON, _AddsNothing(2026, 1, 1, 15)),
        ],
        ids=[
            "later",
            "earlier",
            "the same",
            "microseconds",
            "two zones",
            "two zones, one moment",
            "a repeated hour",
            "across a change, earlier",
            "across a change, later",
            "a zone from elsewhere",
            "against a zone from elsewhere",
            "a class that writes no operator",
            "against a class that writes no operator",
        ],
    )
    def test_it_says_what_its_twin_of_dates_says(self, name, value, other):
        said, twin = _asked_both_ways(name, value, other)
        assert_that(said).is_equal_to(twin)

    def test_each_of_the_four_says_a_line(self):
        said = {
            name: _asked_both_ways(name, *pair)[0]
            for name, pair in {
                "is_less_than": (_later(hours=3), NOON),
                "is_less_than_or_equal_to": (_later(hours=3), NOON),
                "is_greater_than": (NOON, _later(hours=3)),
                "is_greater_than_or_equal_to": (NOON, _later(hours=3)),
            }.items()
        }
        assert_that(said).is_equal_to(
            {
                "is_less_than": ["the value is 3:00:00 after the moment given"],
                "is_less_than_or_equal_to": ["the value is 3:00:00 after the moment given"],
                "is_greater_than": ["the value is 3:00:00 before the moment given"],
                "is_greater_than_or_equal_to": ["the value is 3:00:00 before the moment given"],
            }
        )
        assert_that(_asked_both_ways("is_less_than", NOON, NOON)[0]).is_equal_to([SAME])
        assert_that(_asked_both_ways("is_greater_than", NOON, NOON)[0]).is_equal_to([SAME])

    @pytest.mark.parametrize("name", sorted(_TWINS))
    @pytest.mark.parametrize("written", _ORDERING)
    def test_a_class_that_orders_itself_gets_no_line(self, name, written):
        late = _writes(written)(2026, 1, 1, 15)
        for value, other in ((late, NOON), (NOON, late)):
            if not _passes(lambda value=value, other=other: getattr(assert_that(value), name)(other)):
                lines = _lines(lambda value=value, other=other: getattr(assert_that(value), name)(other))
                assert_that(lines).is_length(1)

    @pytest.mark.parametrize("name", ["is_less_than_or_equal_to", "is_greater_than_or_equal_to"])
    def test_a_tie_its_class_calls_unequal_fails_and_is_not_called_the_same_moment(self, name):
        # the relation asks `==` at a tie and its twin of dates does not, so the two part here
        value = _NEVER_EQUAL(2026, 1, 1, 12)
        assert_that(_lines(lambda: getattr(assert_that(value), name)(NOON))).is_length(1)
        assert_that(_passes(lambda: getattr(assert_that(value), _TWINS[name])(NOON))).is_true()


_TWO_MOMENTS = {
    "is_before": lambda value, other: assert_that(value).is_before(other),
    "is_after": lambda value, other: assert_that(value).is_after(other),
    "is_before_or_equal_to": lambda value, other: assert_that(value).is_before_or_equal_to(other),
    "is_after_or_equal_to": lambda value, other: assert_that(value).is_after_or_equal_to(other),
    "is_close_to": lambda value, other: assert_that(value).is_close_to(other, dt.timedelta(seconds=1)),
    "is_not_close_to": lambda value, other: assert_that(value).is_not_close_to(other, dt.timedelta(days=9)),
}


class TestNoZoneButTheStandardLibrarysIsAsked:
    """A line read past the verdict cannot know what a zone's code told the verdict, so it asks none of it."""

    @pytest.mark.parametrize("name", sorted(_TWO_MOMENTS))
    @pytest.mark.parametrize("hour", [9, 15])
    def test_two_zones_with_one_from_elsewhere_get_no_line_and_no_asking(self, name, hour):
        elsewhere = NOON.replace(tzinfo=_TellsWhenTheLineAsks())
        ours = NOON.replace(hour=hour, tzinfo=UTC)
        for value, other in ((elsewhere, ours), (ours, elsewhere), (elsewhere, NOON.replace(tzinfo=_FallsBack()))):
            _LINE_ASKED.clear()
            if not _passes(lambda value=value, other=other: _TWO_MOMENTS[name](value, other)):
                lines = _lines(lambda value=value, other=other: _TWO_MOMENTS[name](value, other))
                assert_that(lines).described_as(name).is_length(1)
            assert_that(_LINE_ASKED).described_as(name).is_empty()

    def test_a_zone_that_would_answer_the_line_another_way_is_not_asked(self):
        # read an hour east this is 11:00 on the other's clock: a line asked three hours east would say "the same"
        value = NOON.replace(tzinfo=_TellsWhenTheLineAsks())
        _LINE_ASKED.clear()
        lines = _lines(lambda: assert_that(value).is_before(NOON.replace(hour=9, tzinfo=UTC)))
        assert_that(lines).is_length(1)
        assert_that(lines[0]).contains("<2026-01-01 12:00:00+01:00> to be before <2026-01-01 09:00:00+00:00>")
        assert_that(_LINE_ASKED).is_empty()

    def test_the_record_tells_when_the_zone_is_asked_from_the_line(self):
        _LINE_ASKED.clear()
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(_hints, "_own_zone", lambda zone: True)
            _hints.out_of_order(
                NOON.replace(tzinfo=_TellsWhenTheLineAsks()), NOON.replace(tzinfo=UTC), before=True, strict=True
            )
        assert_that(_LINE_ASKED).is_not_empty()

    @pytest.mark.parametrize("name", sorted(_TWO_MOMENTS))
    def test_two_that_share_a_zone_from_elsewhere_get_the_line_of_their_clock_and_no_asking(self, name):
        zone = _TellsWhenTheLineAsks()
        early, late = NOON.replace(tzinfo=zone), NOON.replace(hour=15, tzinfo=zone)
        _LINE_ASKED.clear()
        value, other = (early, late) if name in ("is_after", "is_after_or_equal_to", "is_close_to") else (late, early)
        lines = _lines(lambda: _TWO_MOMENTS[name](value, other))
        assert_that(lines).described_as(name).is_length(2)
        assert_that(lines[1]).described_as(name).contains("3:00:00", "on the clock")
        assert_that(_LINE_ASKED).described_as(name).is_empty()

    def test_a_zone_that_gives_no_offset_is_a_clock_the_two_share(self):
        zone = _GivesNoOffset()
        late, early = NOON.replace(hour=15, tzinfo=zone), NOON.replace(tzinfo=zone)
        lines = _lines(lambda: assert_that(late).is_before(early))
        assert_that(lines[1]).is_equal_to("the value reads 3:00:00 after the moment given on the clock the two share")

    @needs_a_zone_database
    @pytest.mark.parametrize("written", [{}, {"__module__": "zoneinfo"}], ids=["as it is", "saying it is zoneinfo's"])
    def test_a_class_of_its_own_made_of_the_standard_library_s_zone_is_from_elsewhere(self, written):
        own = type("Own", (zoneinfo.ZoneInfo,), written)("Europe/Oslo")
        value, other = dt.datetime(2026, 6, 1, 15, tzinfo=own), dt.datetime(2026, 6, 1, 9, tzinfo=UTC)
        assert_that(_lines(lambda: assert_that(value).is_before(other))).is_length(1)
        lines = _lines(lambda: assert_that(value).is_before(value.replace(hour=12)))
        assert_that(lines[1]).is_equal_to("the value reads 3:00:00 after the moment given on the clock the two share")


_REAL = dt.datetime


class _EveryDatetimeIsOne(type):
    def __instancecheck__(cls, instance):
        return isinstance(instance, _REAL)


class _Frozen(dt.datetime, metaclass=_EveryDatetimeIsOne):
    """What a library that freezes time puts at `datetime.datetime`: a class of its own that every datetime is."""


class _FrozenItsOwnWay(dt.datetime, metaclass=_EveryDatetimeIsOne):
    def __sub__(self, other):
        return dt.timedelta(hours=99)

    def __ge__(self, other):
        return _REAL.__ge__(self, other)


class TestTheStandardLibrarysClassesAreHeldAsTheyWere:
    def test_a_class_at_datetime_that_writes_operators_is_read_by_what_it_writes(self):
        late, frozen = _later(hours=3), _FrozenItsOwnWay(2026, 1, 1, 15)
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(dt, "datetime", _FrozenItsOwnWay)
            real = _lines(lambda: assert_that(late).is_before(NOON))
            its_own = _lines(lambda: assert_that(frozen).is_before(NOON))
        assert_that(real[1:]).is_equal_to(["the value is 3:00:00 after the moment given"])
        assert_that(its_own).is_length(1)

    def test_two_real_moments_are_read_while_another_class_stands_at_datetime(self):
        late, tolerance = _later(hours=3), dt.timedelta(hours=1)
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(dt, "datetime", _Frozen)
            ordered = _lines(lambda: assert_that(late).is_before(NOON))
            measured = _lines(lambda: assert_that(late).is_close_to(NOON, tolerance))
        assert_that(ordered[1:]).is_equal_to(["the value is 3:00:00 after the moment given"])
        assert_that(measured[1:]).is_equal_to(["the two are 3:00:00 apart, 2:00:00 more than the tolerance"])

    def test_a_moment_of_that_class_is_read_by_what_its_class_writes(self):
        late = _Frozen(2026, 1, 1, 15)
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(dt, "datetime", _Frozen)
            ordered = _lines(lambda: assert_that(late).is_before(NOON))
            other_way = _lines(lambda: assert_that(NOON).is_after(late))
        assert_that(ordered[1:]).is_equal_to(["the value is 3:00:00 after the moment given"])
        assert_that(other_way[1:]).is_equal_to(["the value is 3:00:00 before the moment given"])

    def test_no_attribute_of_the_module_is_the_class_itself(self):
        # such a library rewrites each module attribute that is the real class, for as long as time is frozen
        assert_that([name for name, held in vars(_hints).items() if held is _REAL]).is_empty()
        assert_that(_hints._MOMENT).is_equal_to((_REAL,))

    def test_the_real_class_is_read_off_the_tree_of_whatever_stands_at_datetime(self):
        hands_out_itself = type(
            "HandsOutItself",
            (_REAL,),
            {"utcoffset": lambda self: None, "__sub__": lambda self, other: dt.timedelta(hours=99)},
        )
        hands_out_itself.min = hands_out_itself(1, 1, 1)
        assert_that(type(hands_out_itself.min)).is_same_as(hands_out_itself)
        beside_a_mixin = type("BesideAMixin", (_REAL, type("Mixin", (), {"utcoffset": lambda self: None})), {})
        assert_that([base.__name__ for base in beside_a_mixin.__mro__]).is_equal_to(
            ["BesideAMixin", "datetime", "date", "Mixin", "object"]
        )
        for standing in (hands_out_itself, beside_a_mixin, _Frozen, _FrozenItsOwnWay, _REAL):
            assert_that(_hints._own_datetime(standing)).is_same_as(_REAL)
        assert_that(_hints._own_datetime(int)).is_same_as(int)

    @pytest.mark.parametrize("module", [__name__, "zoneinfo_helpers", "zoneinfo", "zoneinfo._zoneinfo", "_zoneinfo"])
    def test_a_class_put_at_the_export_of_zoneinfo_is_not_the_standard_library_s(self, module):
        kind = type("ZoneInfo", (_TellsWhenTheLineAsks,), {"__module__": module})
        value = NOON.replace(tzinfo=kind())
        other = NOON.replace(hour=9, tzinfo=UTC)
        _LINE_ASKED.clear()
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(zoneinfo, "ZoneInfo", kind)
            lines = _lines(lambda: assert_that(value).is_before(other))
        assert_that(lines).is_length(1)
        assert_that(_LINE_ASKED).is_empty()

    @needs_a_zone_database
    def test_the_standard_library_s_zone_written_in_python_is_its_own_too(self):
        written_in_python = importlib.import_module("zoneinfo._zoneinfo").ZoneInfo
        value = dt.datetime(2026, 6, 1, 15, tzinfo=written_in_python("Europe/Oslo"))
        lines = _lines(lambda: assert_that(value).is_before(dt.datetime(2026, 6, 1, 9, tzinfo=UTC)))
        assert_that(lines[1:]).is_equal_to(["the value is 4:00:00 after the moment given"])

    def test_a_class_put_there_is_not_asked_where_it_was_defined_through_a_key_of_its_own(self):
        armed = type(
            "Armed",
            (str,),
            {
                "__slots__": (),
                "__hash__": lambda self: hash("__module__"),
                "__eq__": lambda self, other: _ASKED.append(other) or False,
            },
        )
        kind = type("PutThere", (dt.tzinfo,), {armed("note"): 1})
        _ASKED.clear()
        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(zoneinfo, "ZoneInfo", kind)
            assert_that(_hints._own_zone(kind())).is_false()
        assert_that(_ASKED).is_empty()
        type.__dict__["__module__"].__get__(kind)
        assert_that(_ASKED).is_not_empty()


class TestOneClockAcrossAChange:
    """Two that share a zone object are compared on their wall clocks, which is not always the time between them."""

    def test_a_clock_from_elsewhere_is_what_the_line_speaks_of(self):
        first, second = _clock(2, 30), _clock(2, 30, fold=1)
        assert_that(first == second).is_true()
        assert_that(first.utcoffset() - second.utcoffset()).is_equal_to(dt.timedelta(hours=1))
        assert_that(_lines(lambda: assert_that(first).is_before(second))[1]).is_equal_to(SAME_CLOCK)
        tolerance = dt.timedelta(minutes=5)
        assert_that(_lines(lambda: assert_that(first).is_not_close_to(second, tolerance))[1]).is_equal_to(SAME_CLOCK)
        early, late = _clock(0, 30), _clock(4, 30)
        assert_that(_lines(lambda: assert_that(early).is_after(late))[1]).is_equal_to(
            "the value reads 4:00:00 before the moment given on the clock the two share"
        )
        assert_that(_lines(lambda: assert_that(early).is_close_to(late, dt.timedelta(hours=1)))[1]).is_equal_to(
            "the two read 4:00:00 apart on the clock they share, 3:00:00 more than the tolerance"
        )
        assert_that(_lines(lambda: assert_that(early).is_not_close_to(late, dt.timedelta(hours=4)))[1]).is_equal_to(
            "the two read 4:00:00 apart on the clock they share, which is the tolerance"
        )
        assert_that(_lines(lambda: assert_that(early).is_not_close_to(late, dt.timedelta(hours=6)))[1]).is_equal_to(
            "the two read 4:00:00 apart on the clock they share, 2:00:00 less than the tolerance"
        )

    @needs_a_zone_database
    def test_the_standard_library_s_clock_with_one_offset_is_read_as_moments(self):
        lines = _lines(lambda: assert_that(_oslo_clock(0, 30)).is_after(_oslo_clock(1, 30)))
        assert_that(lines[1]).is_equal_to("the value is 1:00:00 before the moment given")
        lines = _lines(lambda: assert_that(_oslo_clock(4)).is_before(_oslo_clock(3, 30)))
        assert_that(lines[1]).is_equal_to("the value is 0:30:00 after the moment given")
        lines = _lines(lambda: assert_that(_oslo_clock(4)).is_close_to(_oslo_clock(3, 30), dt.timedelta(minutes=10)))
        assert_that(lines[1]).is_equal_to("the two are 0:30:00 apart, 0:20:00 more than the tolerance")

    @needs_a_zone_database
    def test_the_two_readings_of_its_repeated_hour_read_the_same_and_are_not_the_same_moment(self):
        first, second = _oslo_clock(2, 30), _oslo_clock(2, 30, fold=1)
        assert_that(first == second).is_true()
        assert_that(first.utcoffset() - second.utcoffset()).is_equal_to(dt.timedelta(hours=1))
        lines = _lines(lambda: assert_that(first).is_before(second))
        assert_that(lines[0]).contains("<2026-10-25 02:30:00+02:00> to be before <2026-10-25 02:30:00+01:00>")
        assert_that(lines[1]).is_equal_to(SAME_CLOCK)

    @needs_a_zone_database
    def test_four_hours_on_its_clock_that_are_five_of_time_are_said_of_the_clock(self):
        early, late = _oslo_clock(0, 30), _oslo_clock(4, 30)
        assert_that(late - early).is_equal_to(dt.timedelta(hours=4))
        assert_that(_lines(lambda: assert_that(early).is_after(late))[1]).is_equal_to(
            "the value reads 4:00:00 before the moment given on the clock the two share"
        )

    @needs_a_zone_database
    def test_two_zones_of_the_standard_library_are_read_as_the_moments_they_are(self):
        # 00:30 two hours east is 22:30 UTC the day before, five hours before 03:30 UTC
        lines = _lines(lambda: assert_that(_oslo_clock(0, 30)).is_after(dt.datetime(2026, 10, 25, 3, 30, tzinfo=UTC)))
        assert_that(lines[1]).is_equal_to("the value is 5:00:00 before the moment given")

    @needs_a_zone_database
    def test_a_window_that_reaches_where_the_distance_does_not_gets_no_line(self):
        # two hours added to 01:30 on Oslo's clock read 03:30 one hour east, three hours of time later
        middle, tolerance = _oslo_clock(1, 30), dt.timedelta(hours=2)
        value = dt.datetime(2026, 10, 25, 2, tzinfo=UTC)
        assert_that(value - middle).is_equal_to(dt.timedelta(hours=2, minutes=30))
        assert_that(value).is_close_to(middle, tolerance)
        assert_that(_lines(lambda: assert_that(value).is_not_close_to(middle, tolerance))).is_length(1)


_SPAN = re.compile(r"(?:(\d+) days?, )?(\d+):(\d\d):(\d\d)(?:\.(\d{6}))?")
_MOMENTS = st.one_of(
    st.datetimes(min_value=dt.datetime(1990, 1, 1), max_value=dt.datetime(2090, 1, 1)),
    st.datetimes(min_value=dt.datetime(2026, 10, 24, 22), max_value=dt.datetime(2026, 10, 25, 6)),
    st.datetimes(min_value=dt.datetime(2026, 10, 31, 22), max_value=dt.datetime(2026, 11, 1, 6)),
)
_GAPS = st.one_of(
    st.just(dt.timedelta()),
    st.timedeltas(min_value=dt.timedelta(days=-3), max_value=dt.timedelta(days=3)),
    st.timedeltas(min_value=dt.timedelta(seconds=-2), max_value=dt.timedelta(seconds=2)),
)
_ZONES = st.sampled_from(
    [None, UTC, PLUS_ONE, dt.timezone(dt.timedelta(hours=-5, minutes=-30)), TURN, *([OSLO] if OSLO else [])]
)
_FOLDS = st.sampled_from([0, 1])
_PAIRS = st.tuples(_MOMENTS, _GAPS, _ZONES, _ZONES, _FOLDS, _FOLDS)


def _spans(line: str) -> list[dt.timedelta]:
    return [
        dt.timedelta(days=int(days or 0), hours=int(hours), minutes=int(minutes), seconds=int(seconds))
        + dt.timedelta(microseconds=int(micro or 0))
        for days, hours, minutes, seconds, micro in _SPAN.findall(line)
    ]


def _pair(moment, gap, zone, other_zone, fold, other_fold):
    """Two moments, both naive or each on a clock, which may be one clock."""
    if zone is None or other_zone is None:
        return moment, moment + gap
    return moment.replace(tzinfo=zone, fold=fold), (moment + gap).replace(tzinfo=other_zone, fold=other_fold)


def _own(zone: dt.tzinfo | None) -> bool:
    return zone is None or type(zone) in (dt.timezone, zoneinfo.ZoneInfo)


def _reading(value: dt.datetime, other: dt.datetime) -> str | None:
    """What a line may speak of: the two moments, the clock the two share, or nothing."""
    if value.tzinfo is not other.tzinfo:
        return "moments" if _own(value.tzinfo) and _own(other.tzinfo) else None
    if value.tzinfo is None or (_own(value.tzinfo) and value.utcoffset() == other.utcoffset()):
        return "moments"
    return "clock"


def _on_the_utc_clock(moment: dt.datetime) -> dt.datetime:
    """The moment by its own offset, which is another way round than the subtraction the line makes."""
    return moment if moment.tzinfo is None else moment.replace(tzinfo=None) - moment.utcoffset()


def _between(value: dt.datetime, other: dt.datetime, reading: str) -> dt.timedelta:
    if reading == "clock":
        return value.replace(tzinfo=None) - other.replace(tzinfo=None)
    return _on_the_utc_clock(value) - _on_the_utc_clock(other)


class TestTheDistanceSaidIsTheDistance:
    """Each line is held against the two read another way: on the UTC clock by their own offsets, or off the wall."""

    @given(_PAIRS, st.sampled_from(sorted(_SAYS)))
    def test_a_moment_on_the_wrong_side(self, drawn, name):
        value, other = _pair(*drawn)
        if _passes(lambda: getattr(assert_that(value), name)(other)):
            return
        lines = _lines(lambda: getattr(assert_that(value), name)(other))
        reading = _reading(value, other)
        if reading is None:
            assert_that(lines).is_length(1)
            return
        assert_that(lines).is_length(2)
        between = _between(value, other, reading)
        assert_that("on the clock" in lines[1]).is_equal_to(reading == "clock")
        if not between:
            assert_that(lines[1]).is_equal_to(SAME if reading == "moments" else SAME_CLOCK)
            assert_that(name).does_not_contain("or_equal")
            return
        (span,) = _spans(lines[1])
        assert_that(span).is_greater_than(dt.timedelta())
        assert_that(between).is_equal_to(span if " after " in lines[1] else -span)
        assert_that(" after " in lines[1]).is_equal_to("before" in name)

    @given(_PAIRS, st.timedeltas(min_value=dt.timedelta(), max_value=dt.timedelta(days=2)))
    def test_two_moments_against_a_tolerance(self, drawn, tolerance):
        value, other = _pair(*drawn)
        reading = _reading(value, other)
        close = _passes(lambda: assert_that(value).is_close_to(other, tolerance))
        ask = assert_that(value).is_not_close_to if close else assert_that(value).is_close_to
        lines = _lines(lambda: ask(other, tolerance))
        if reading is None:
            assert_that(lines).is_length(1)
            return
        between = abs(_between(value, other, reading))
        told = (
            f"the two are {between} apart"
            if reading == "moments"
            else f"the two read {between} apart on the clock they share"
        )
        if not close:
            assert_that(lines[1:]).is_equal_to([f"{told}, {between - tolerance} more than the tolerance"])
            assert_that(value).is_close_to(other, between)
        elif between > tolerance:
            # past the tolerance and close all the same: a window round one of the two reached the other
            assert_that(reading).is_equal_to("moments")
            assert_that(lines).is_length(1)
        elif not between:
            assert_that(lines[1:]).is_equal_to([SAME if reading == "moments" else SAME_CLOCK])
        elif between == tolerance:
            assert_that(lines[1:]).is_equal_to([f"{told}, which is the tolerance"])
        else:
            assert_that(lines[1:]).is_equal_to([f"{told}, {tolerance - between} less than the tolerance"])

    @given(_PAIRS, st.sampled_from(sorted(_TWINS)))
    def test_a_relation_of_numbers_says_what_its_twin_of_dates_says(self, drawn, name):
        value, other = _pair(*drawn)
        said, twin = _asked_both_ways(name, value, other)
        if said is None:
            assert_that(twin).is_none()
        elif twin is None:
            # a tie of two zones that `==` does not call equal: the relation asks `==` and its twin does not
            assert_that(name).contains("or_equal")
            assert_that(said).is_empty()
        else:
            assert_that(said).is_equal_to(twin)
