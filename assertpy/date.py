from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, cast

from ._engine._mixin_base import _MixinBase
from ._engine._require import argument, require_type
from ._hints import out_of_order, under
from .errors import _capped, _capped_format

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


def _require_datetime(value: object, label: str) -> None:
    """Raise ``TypeError`` unless *value* is exactly a `datetime.datetime`."""
    require_type(value, datetime.datetime, "a datetime", subject=label)


def _read_in_the_zone_of(value: datetime.datetime, reference: datetime.datetime) -> datetime.datetime:
    """*value* as the same instant reads on *reference*'s clock, so wall-clock fields compare like with like.

    The guide says making both sides aware is what makes these comparisons well defined.  Compared field
    by field they were not: two instants five hours apart in different zones read equal to the second.
    Both sides are aware or both naive by then, and a naive pair has no zone to be read in.  One wall time
    of a zone's repeated hour is two moments an hour apart, so the caller asks whether the two are one reading
    too (`_one_reading`) where the value was read on another clock.  Two on one zone object are left to their
    wall clocks, as `==` is.
    """
    return value.astimezone(reference.tzinfo) if reference.tzinfo is not None else value


def _one_reading(value: datetime.datetime, instant: datetime.datetime, other: datetime.datetime) -> bool:
    """Whether two that read alike on one clock are the same reading of it, where a clock reads a time twice.

    The offsets tell.  Equal ones are one reading.  Two readings of one time have the later moment at the
    smaller offset, since the clock went back between them, and the later moment at the larger one is a clock
    that went forward inside the unit, which reads it once.  Asked of the `fold` instead, a clock that goes
    back by less than the unit read two visits to one minute as one.
    """
    # both are aware here: a naive pair has no zone to be read in and is never asked
    held, read = cast("datetime.timedelta", value.utcoffset()), cast("datetime.timedelta", instant.utcoffset())
    return held == read or (held < read) is (value < other)


def _written_to(form: str, value: datetime.datetime, instant: datetime.datetime) -> tuple[str, str]:
    """The two in *form*, with their offsets where they read alike: a wall time of a repeated hour is two moments."""
    first, second = value.strftime(form), instant.strftime(form)
    if first != second:
        return first, second
    return first + _offset_of(value), second + _offset_of(instant)


def _offset_of(value: datetime.datetime) -> str:
    written = value.strftime("%z")
    return f"{written[:3]}:{written[3:]}"


def _require_comparable_datetimes(first: datetime.datetime, second: datetime.datetime) -> None:
    """Reject a naive-vs-aware pair with a clear message.

    The relational assertions would otherwise leak the raw ``TypeError`` from ``<``/``>``.  The
    ``ignoring_*`` ones compare wall-clock fields, which silently answers a different question: two
    instants hours apart read equal.  Both operands are already validated as `datetime.datetime`.
    """
    if (first.utcoffset() is None) != (second.utcoffset() is None):
        raise TypeError(
            "cannot compare a timezone-naive datetime with a timezone-aware one. Make both aware or both naive first"
        )


class DateMixin(_MixinBase):
    """Date and time assertions mixin."""

    def is_before(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is before other date.

        Args:
            other (object): the other date, expected to be after val

        Examples:
            Usage:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_before(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** before the given date

        See Also:
            [`is_less_than()`][assertpy.numeric.NumericMixin.is_less_than] - numeric assertion, but
                also works with datetime
            [`is_less_than_or_equal_to()`][assertpy.numeric.NumericMixin.is_less_than_or_equal_to] -
                also works with datetime
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        if self.val >= other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be before <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=True, strict=True))}",
                expected=other,
            )
        return self

    def is_after(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is after other date.

        Args:
            other (object): the other date, expected to be before val

        Examples:
            Usage:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_after(yesterday)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** after the given date

        See Also:
            [`is_greater_than()`][assertpy.numeric.NumericMixin.is_greater_than] - numeric assertion,
                but also works with datetime
            [`is_greater_than_or_equal_to()`][assertpy.numeric.NumericMixin.is_greater_than_or_equal_to] -
                also works with datetime
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        if self.val <= other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be after <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=False, strict=True))}",
                expected=other,
            )
        return self

    def is_before_or_equal_to(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is before or equal to other date.

        Args:
            other (object): the other date, expected to be after or equal to val

        Examples:
            Usage:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_before_or_equal_to(today)
                assert_that(today).is_before_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** before or equal to the given date
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        if self.val > other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be before or equal to <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=True, strict=False))}",
                expected=other,
            )
        return self

    def is_after_or_equal_to(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is after or equal to other date.

        Args:
            other (object): the other date, expected to be before or equal to val

        Examples:
            Usage:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_after_or_equal_to(yesterday)
                assert_that(today).is_after_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** after or equal to the given date
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        if self.val < other:
            return self.error(
                f"Expected <{_capped(self.val)}> to be after or equal to <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=False, strict=False))}",
                expected=other,
            )
        return self

    def is_equal_to_ignoring_milliseconds(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is equal to other date to the second.

        Args:
            other (object): the other date, expected to be equal to the second

        Examples:
            Usage:

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5, 6)       # 2020-01-02 03:04:05.000006
                d2 = datetime.datetime(2020, 1, 2, 3, 4, 5, 777777)  # 2020-01-02 03:04:05.777777

                assert_that(d1).is_equal_to_ignoring_milliseconds(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date to the second
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        instant = _read_in_the_zone_of(other, self.val)
        if (
            self.val.date() == instant.date()
            and self.val.hour == instant.hour
            and self.val.minute == instant.minute
            and self.val.second == instant.second
            and (instant is other or _one_reading(self.val, instant, other))
        ):
            return self
        read, wanted = _written_to("%Y-%m-%d %H:%M:%S", self.val, instant)
        return self.error(f"Expected <{read}> to be equal to <{wanted}>, but was not.", expected=other)

    def is_equal_to_ignoring_seconds(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is equal to other date to the minute.

        Args:
            other (object): the other date, expected to be equal to the minute

        Examples:
            Usage:

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5)   # 2020-01-02 03:04:05
                d2 = datetime.datetime(2020, 1, 2, 3, 4, 55)  # 2020-01-02 03:04:55

                assert_that(d1).is_equal_to_ignoring_seconds(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date to the minute
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        instant = _read_in_the_zone_of(other, self.val)
        if (
            self.val.date() == instant.date()
            and self.val.hour == instant.hour
            and self.val.minute == instant.minute
            and (instant is other or _one_reading(self.val, instant, other))
        ):
            return self
        read, wanted = _written_to("%Y-%m-%d %H:%M", self.val, instant)
        return self.error(f"Expected <{read}> to be equal to <{wanted}>, but was not.", expected=other)

    def is_equal_to_ignoring_time(self, other: datetime.datetime) -> Self:
        """Asserts that val is a date and is equal to other date ignoring time.

        Args:
            other (object): the other date, expected to be equal ignoring time

        Examples:
            Usage:

                import datetime

                d1 = datetime.datetime(2020, 1, 2, 3, 4, 5)     # 2020-01-02 03:04:05
                d2 = datetime.datetime(2020, 1, 2, 13, 44, 55)  # 2020-01-02 13:44:55

                assert_that(d1).is_equal_to_ignoring_time(d2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** equal to the given date ignoring time
        """
        _require_datetime(self.val, "val")
        _require_datetime(other, argument("other"))
        _require_comparable_datetimes(self.val, other)
        instant = _read_in_the_zone_of(other, self.val)
        if self.val.date() == instant.date():
            return self
        return self.error(
            f"Expected <{self.val.strftime('%Y-%m-%d')}> to be equal to <{instant.strftime('%Y-%m-%d')}>, but was not.",
            expected=other,
        )
