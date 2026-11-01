from __future__ import annotations

import datetime
import numbers
from typing import TYPE_CHECKING, SupportsFloat, SupportsIndex

from ._engine._compare import _is_infinite, _is_nan, within_either
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import UnorderableError, compare, holds, require_integer
from ._engine._require import _shown, argument, refuse, require_type
from ._hints import apart_in_time, out_of_order, under
from .errors import _capped, _capped_format

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


def _fmt_tolerance(tolerance: datetime.timedelta) -> str:
    """A timedelta tolerance as ``h:mm:ss``, its hours counted on past a day, with its fraction where it has one."""
    hours, remainder = divmod(tolerance.days * 86400 + tolerance.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    fraction = f".{tolerance.microseconds:06d}" if tolerance.microseconds else ""
    return f"{hours}:{minutes:02d}:{seconds:02d}{fraction}"


def _allowance(tolerance: object, rel: object) -> str:
    """The tolerances a closeness was asked within, in the words of its message."""
    relative = f"relative tolerance <{_capped_format(rel)}>"
    if tolerance is None:
        return relative
    absolute = f"tolerance <{_capped_format(tolerance)}>"
    return absolute if rel is None else f"{absolute} or {relative}"


class NumericMixin(_MixinBase):
    """Numeric assertions mixin."""

    _NUMERIC_COMPAREABLE = frozenset({datetime.datetime, datetime.timedelta, datetime.date, datetime.time})
    _NUMERIC_NON_COMPAREABLE = frozenset({complex})

    def _validate_compareable(self, other):
        """Refuse the pair when it cannot be ordered, in the wording this surface uses.

        Whether it can be is decided in `_engine._ordering`, which the matchers ask as well: the rule
        used to be written once here as a list of types and once there as a `try`/`except`, and one
        relation spelled twice is how the text matchers drifted apart on bytes.
        """
        try:
            compare(self.val, other)
        except UnorderableError as unordered:
            self._refuse_unordered(unordered, other, "other")

    def _refuse_unordered(self, unordered, other, name):
        """The refusal for a pair the ordering engine could not order, naming the argument it came from."""
        if unordered.kind == "value":
            refuse(self.val, "a value with an ordering (complex numbers have none)")
        kind_bound = unordered.wanted
        if unordered.kind == "kind":
            wanted = (
                "a number"
                if kind_bound is numbers.Number or kind_bound is None
                else f"a {kind_bound.__name__}, to match val"
            )
            refuse(other, wanted, subject=argument(name))
        # the pair cannot be ordered, not the value: two strings compare fine, so that was untrue of `"10" > 5`
        refuse(other, f"comparable with val {_shown(self.val)}", subject=argument(name))

    def _within(self, low, high, *, named=None):
        """Whether ``low <= val <= high``, asked through the ordering engine so a NaN answers rather than signals.

        A pair the engine cannot order is refused where it is met, in the words the single relations use,
        and only there: below the low bound the answer is known, and the high one is never asked.  Asked
        up front instead, a high bound the value could not be ordered against turned a passing
        `is_not_between` into a refusal.

        *named* is what a refusal names, as ``(argument, its name)``: a window's bounds are worked out from
        `other`, and `other` is what the caller wrote.
        """
        return self._holds(low, "ge", named or (low, "low")) and self._holds(high, "le", named or (high, "high"))

    def _close(self, other, tolerance, rel):
        """Whether val is within *tolerance* or *rel* of *other*, *rel* being a fraction of the size of *other*.

        A pair the ordering engine cannot order is refused, in the words the single relations use.
        """
        try:
            return within_either(self.val, other, tolerance, rel)
        except UnorderableError as unordered:
            self._refuse_unordered(unordered, other, "other")

    def _holds(self, bound, relation, named):
        """`holds` against one bound, with a pair the engine cannot order refused under *named*."""
        try:
            return holds(self.val, bound, relation)
        except UnorderableError as unordered:
            self._refuse_unordered(unordered, *named)

    def _validate_number(self):
        """Raise TypeError if val is not numeric."""
        require_type(self.val, numbers.Number, "a number")

    def _validate_real(self):
        """Raise TypeError if val is not real number."""
        require_type(self.val, numbers.Real, "a real number")

    def is_zero(self) -> Self:
        """Asserts that val is numeric and is zero.

        Examples:
            Usage:

                assert_that(0).is_zero()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** zero
        """
        self._validate_number()
        return self.is_equal_to(0)

    def is_not_zero(self) -> Self:
        """Asserts that val is numeric and is *not* zero.

        Examples:
            Usage:

                assert_that(1).is_not_zero()
                assert_that(123.4).is_not_zero()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** zero
        """
        self._validate_number()
        return self.is_not_equal_to(0)

    def is_nan(self) -> Self:
        """Asserts that val is real number and is ``NaN`` (not a number).

        Examples:
            Usage:

                assert_that(float('nan')).is_nan()
                assert_that(float('inf') * 0).is_nan()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** NaN
        """
        self._validate_number()
        self._validate_real()
        if not _is_nan(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to be <NaN>, but was not.")
        return self

    def is_not_nan(self) -> Self:
        """Asserts that val is real number and is *not* ``NaN`` (not a number).

        Examples:
            Usage:

                assert_that(0).is_not_nan()
                assert_that(123.4).is_not_nan()
                assert_that(float('inf')).is_not_nan()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** NaN
        """
        self._validate_number()
        self._validate_real()
        if _is_nan(self.val):
            return self.error("Expected not <NaN>, but was.")
        return self

    def is_inf(self) -> Self:
        """Asserts that val is real number and is ``Inf`` (infinity).

        Examples:
            Usage:

                assert_that(float('inf')).is_inf()
                assert_that(float('inf') * 1).is_inf()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** Inf
        """
        self._validate_number()
        self._validate_real()
        if not _is_infinite(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to be <Inf>, but was not.")
        return self

    def is_not_inf(self) -> Self:
        """Asserts that val is real number and is *not* ``Inf`` (infinity).

        Examples:
            Usage:

                assert_that(0).is_not_inf()
                assert_that(123.4).is_not_inf()
                assert_that(float('nan')).is_not_inf()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** Inf
        """
        self._validate_number()
        self._validate_real()
        if _is_infinite(self.val):
            return self.error("Expected not <Inf>, but was.")
        return self

    def is_greater_than(self, other: object) -> Self:
        """Asserts that val is numeric and is greater than other.

        Args:
            other: the other date, expected to be less than val

        Examples:
            Usage:

                assert_that(1).is_greater_than(0)
                assert_that(123.4).is_greater_than(111.1)

            For dates, behavior is identical to [`is_after()`][assertpy.date.DateMixin.is_after]:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_greater_than(yesterday)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** greater than other

        Note:
            A ``NaN`` value is unordered, so it **fails** every relational assertion here
            (``is_greater_than``, ``is_less_than``, ``is_between``, ``is_positive``, ...). This diverges
            from assertpy 1.x, where ``NaN`` silently passes.
        """
        self._validate_compareable(other)
        if not holds(self.val, other, "gt"):  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_capped_format(self.val)}> to be greater than <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=False, strict=True))}",
                expected=other,
            )
        return self

    def is_greater_than_or_equal_to(self, other: object) -> Self:
        """Asserts that val is numeric and is greater than or equal to other.

        Args:
            other: the other date, expected to be less than or equal to val

        Examples:
            Usage:

                assert_that(1).is_greater_than_or_equal_to(0)
                assert_that(1).is_greater_than_or_equal_to(1)
                assert_that(123.4).is_greater_than_or_equal_to(111.1)

            For dates, behavior is identical to [`is_after()`][assertpy.date.DateMixin.is_after] *except* when equal:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_greater_than_or_equal_to(yesterday)
                assert_that(today).is_greater_than_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** greater than or equal to other
        """
        self._validate_compareable(other)
        if not holds(self.val, other, "ge"):  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_capped_format(self.val)}> to be greater than or equal to"
                f" <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=False, strict=False))}",
                expected=other,
            )
        return self

    def is_less_than(self, other: object) -> Self:
        """Asserts that val is numeric and is less than other.

        Args:
            other: the other date, expected to be greater than val

        Examples:
            Usage:

                assert_that(0).is_less_than(1)
                assert_that(123.4).is_less_than(555.5)

            For dates, behavior is identical to [`is_before()`][assertpy.date.DateMixin.is_before]:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_less_than(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** less than other

        Note:
            A ``NaN`` value is unordered and **fails** here, diverging from assertpy 1.x where
            ``NaN`` silently passes relational assertions.
        """
        self._validate_compareable(other)
        if not holds(self.val, other, "lt"):  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_capped_format(self.val)}> to be less than <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=True, strict=True))}",
                expected=other,
            )
        return self

    def is_less_than_or_equal_to(self, other: object) -> Self:
        """Asserts that val is numeric and is less than or equal to other.

        Args:
            other: the other date, expected to be greater than or equal to val

        Examples:
            Usage:

                assert_that(1).is_less_than_or_equal_to(0)
                assert_that(1).is_less_than_or_equal_to(1)
                assert_that(123.4).is_less_than_or_equal_to(100.0)

            For dates, behavior is identical to [`is_before()`][assertpy.date.DateMixin.is_before]
            *except* when equal:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(yesterday).is_less_than_or_equal_to(today)
                assert_that(today).is_less_than_or_equal_to(today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** less than or equal to other
        """
        self._validate_compareable(other)
        if not holds(self.val, other, "le"):  # positive form so NaN (unordered) fails instead of slipping through
            return self.error(
                f"Expected <{_capped_format(self.val)}> to be less than or equal to"
                f" <{_capped_format(other)}>, but was not."
                f"{under(out_of_order(self.val, other, before=True, strict=False))}",
                expected=other,
            )
        return self

    def is_positive(self) -> Self:
        """Asserts that val is numeric and is greater than zero.

        Examples:
            Usage:

                assert_that(1).is_positive()
                assert_that(123.4).is_positive()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** positive

        Note:
            ``NaN`` is not positive, so this **fails** for ``float("nan")``. This diverges from the
            assertpy 1.x, where ``NaN`` silently passes relational assertions.
        """
        return self.is_greater_than(0)

    def is_negative(self) -> Self:
        """Asserts that val is numeric and is less than zero.

        Examples:
            Usage:

                assert_that(-1).is_negative()
                assert_that(-123.4).is_negative()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** negative

        Note:
            ``NaN`` is not negative, so this **fails** for ``float("nan")``. This diverges from the
            assertpy 1.x, where ``NaN`` silently passes relational assertions.
        """
        return self.is_less_than(0)

    def is_between(self, low: object, high: object) -> Self:
        """Asserts that val is numeric and is between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage:

                assert_that(1).is_between(0, 2)
                assert_that(123.4).is_between(111.1, 222.2)

            For dates, works as expected:

                import datetime

                today = datetime.datetime.now()
                middle = today - datetime.timedelta(hours=12)
                yesterday = today - datetime.timedelta(days=1)

                assert_that(middle).is_between(yesterday, today)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** between low and high

        Note:
            ``NaN`` is not within any range, so this **fails** for ``float("nan")``. This diverges from
            assertpy 1.x, where ``NaN`` silently passes relational assertions.
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if not self._within(low, high):  # positive form so NaN (unordered) fails instead of passing
            return self.error(
                f"Expected <{_capped_format(self.val)}> to be between"
                f" <{_capped_format(low)}> and <{_capped_format(high)}>, but was not.",
                expected=(low, high),
            )
        return self

    def is_not_between(self, low: object, high: object) -> Self:
        """Asserts that val is numeric and is *not* between low and high.

        Args:
            low: the low value
            high: the high value

        Examples:
            Usage:

                assert_that(1).is_not_between(2, 3)
                assert_that(1.1).is_not_between(2.2, 3.3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** between low and high
        """
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if self._within(low, high):
            return self.error(
                f"Expected <{_capped_format(self.val)}> to not be between"
                f" <{_capped_format(low)}> and <{_capped_format(high)}>, but was."
            )
        return self

    def _integer_value(self) -> int:
        value = self.val
        return value if type(value) is int else require_integer(value)

    def is_even(self) -> Self:
        """Asserts that val is an integer and is even.

        Examples:
            Usage:

                assert_that(0).is_even()
                assert_that(2).is_even()
                assert_that(-4).is_even()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** even
        """
        if self._integer_value() % 2 != 0:
            return self.error(f"Expected <{_capped(self.val)}> to be even, but was not.")
        return self

    def is_odd(self) -> Self:
        """Asserts that val is an integer and is odd.

        Examples:
            Usage:

                assert_that(1).is_odd()
                assert_that(3).is_odd()
                assert_that(-5).is_odd()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** odd
        """
        if self._integer_value() % 2 == 0:
            return self.error(f"Expected <{_capped(self.val)}> to be odd, but was not.")
        return self

    def is_divisible_by(self, divisor: SupportsIndex) -> Self:
        """Asserts that val is an integer and is divisible by divisor.

        Args:
            divisor: the divisor to check against (must be a non-zero integer)

        Examples:
            Usage:

                assert_that(10).is_divisible_by(5)
                assert_that(12).is_divisible_by(3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** divisible by divisor
        """
        value = self._integer_value()
        modulus = divisor if type(divisor) is int else require_integer(divisor, "divisor")
        if modulus == 0:
            raise ValueError("given divisor arg must not be zero")
        if value % modulus != 0:
            return self.error(
                f"Expected <{_capped(self.val)}> to be divisible by <{_capped_format(divisor)}>, but was not.",
                expected=divisor,
            )
        return self

    def is_close_to(
        self,
        other: SupportsFloat | SupportsIndex | datetime.datetime,
        tolerance: SupportsFloat | SupportsIndex | datetime.timedelta | None = None,
        *,
        rel: SupportsFloat | SupportsIndex | None = None,
    ) -> Self:
        """Asserts that val is numeric and is close to other within tolerance.

        The distance is taken three ways, the difference and the window around each side, and any of them
        holding is enough, so under ``tolerance`` the answer is the same whichever operand is val.  An
        infinity is close only to itself, whatever the tolerance, and a NaN to nothing.

        ``rel`` is a tolerance relative to the size of other, the expected value, as `pytest.approx` scales
        it, and so it reads one way round: ``rel=0.02`` allows ``2`` either side of ``100``, which ``98`` is
        within, while ``100`` is not within ``rel=0.02`` of ``98``.  It is then measured as ``tolerance`` is.
        Given beside ``tolerance``, either holding is enough, which is what keeps an expected value near
        zero, where any fraction of its size is tiny, within reach.

        Args:
            other (object): the other value, expected to be close to val within tolerance
            tolerance (object): the absolute tolerance, zero or more
            rel (object): the tolerance as a fraction of the size of other, zero or more; for numbers

        Examples:
            Usage:

                assert_that(123).is_close_to(100, 25)
                assert_that(123.4).is_close_to(123, 0.5)
                assert_that(101.5).is_close_to(100, rel=0.02)

            For dates, works as expected:

                import datetime

                today = datetime.datetime.now()
                yesterday = today - datetime.timedelta(days=1)

                assert_that(today).is_close_to(yesterday, datetime.timedelta(hours=36))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** close to other within tolerance
            TypeError: if val, other or tolerance is not a number (or a ``datetime`` and a ``timedelta``),
                or is a bool, or if a numpy duration meets a number, or if neither tolerance nor rel is given,
                or rel is given for a datetime
            ValueError: if tolerance or rel is negative or NaN
        """
        self._validate_close_to_args(self.val, other, tolerance, rel)

        # read through `math.isnan`, which converts the value: the gate the capable facade keys this on
        nan = not isinstance(self.val, datetime.datetime) and (_is_nan(self.val) or _is_nan(other))
        if nan or not self._close(other, tolerance, rel):
            if isinstance(tolerance, datetime.timedelta):
                return self.error(
                    f"Expected <{_capped_format(self.val)}> to be close to"
                    f" <{_capped_format(other)}> within tolerance"
                    f" <{_fmt_tolerance(tolerance)}>, but was not."
                    f"{under(apart_in_time(self.val, other, tolerance, close=True))}",
                    expected=(other, tolerance),
                )
            else:
                return self.error(
                    f"Expected <{_capped(self.val)}> to be close to <{_capped_format(other)}> within"
                    f" {_allowance(tolerance, rel)}, but was not.",
                    expected=(other, tolerance) if rel is None else (other, tolerance, rel),
                )
        return self

    def is_not_close_to(
        self,
        other: SupportsFloat | SupportsIndex | datetime.datetime,
        tolerance: SupportsFloat | SupportsIndex | datetime.timedelta | None = None,
        *,
        rel: SupportsFloat | SupportsIndex | None = None,
    ) -> Self:
        """Asserts that val is numeric and is *not* close to other within tolerance.

        Measured as [`is_close_to()`][assertpy.numeric.NumericMixin.is_close_to] measures, so an infinity
        is not close to anything but itself and a NaN to nothing.

        Args:
            other (object): the other value
            tolerance (object): the absolute tolerance, zero or more
            rel (object): the tolerance as a fraction of the size of other, zero or more; for numbers

        Examples:
            Usage:

                assert_that(123).is_not_close_to(100, 22)
                assert_that(123.4).is_not_close_to(123, 0.1)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** close to other within tolerance
            TypeError: if val, other or tolerance is not a number (or a ``datetime`` and a ``timedelta``),
                or is a bool, or if a numpy duration meets a number, or if neither tolerance nor rel is given,
                or rel is given for a datetime
            ValueError: if tolerance or rel is negative or NaN
        """
        self._validate_close_to_args(self.val, other, tolerance, rel)

        if self._close(other, tolerance, rel):
            if isinstance(tolerance, datetime.timedelta):
                return self.error(
                    f"Expected <{_capped_format(self.val)}> to not be close to"
                    f" <{_capped_format(other)}> within tolerance"
                    f" <{_fmt_tolerance(tolerance)}>, but was."
                    f"{under(apart_in_time(self.val, other, tolerance, close=False))}",
                )
            else:
                return self.error(
                    f"Expected <{_capped(self.val)}> to not be close to <{_capped_format(other)}> within"
                    f" {_allowance(tolerance, rel)}, but was.",
                )
        return self
