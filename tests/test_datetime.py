import datetime

import pytest

from assertpy import assert_that

# fixed, later moments are offsets from it: the wall clock read twice can step back (a DST fall-back, NTP)
reference_time = datetime.datetime(2026, 1, 1, 12, 0, 0, 123456)


def test_is_before():
    other_time = reference_time + datetime.timedelta(seconds=1)
    assert_that(reference_time).is_before(other_time)


def test_is_before_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(other_time).is_before(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be before "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_before_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_before(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be a datetime, but was <123> (int)")


def test_is_before_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_before(123)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a datetime, but was <123> (int)")


def test_is_after():
    other_time = reference_time + datetime.timedelta(seconds=1)
    assert_that(other_time).is_after(reference_time)


def test_is_after_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_after(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be after "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_after_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_after(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be a datetime, but was <123> (int)")


def test_is_after_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_after(123)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_milliseconds():
    assert_that(reference_time).is_equal_to_ignoring_milliseconds(reference_time)


def test_is_equal_to_ignoring_milliseconds_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_milliseconds(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_equal_to_ignoring_milliseconds_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_milliseconds(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_milliseconds_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_milliseconds(123)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_seconds():
    assert_that(reference_time).is_equal_to_ignoring_seconds(reference_time)


def test_is_equal_to_ignoring_seconds_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_seconds(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}>, but was not."
    )


def test_is_equal_to_ignoring_seconds_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_seconds(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_seconds_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_seconds(123)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_time():
    assert_that(reference_time).is_equal_to_ignoring_time(reference_time)


def test_is_equal_to_ignoring_time_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(days=1)
        assert_that(reference_time).is_equal_to_ignoring_time(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2}> to be equal to <\d{4}-\d{2}-\d{2}>, but was not."
    )


def test_is_equal_to_ignoring_time_bad_val_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_time(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be a datetime, but was <123> (int)")


def test_is_equal_to_ignoring_time_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_equal_to_ignoring_time(123)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a datetime, but was <123> (int)")


def test_is_greater_than():
    other_time = reference_time + datetime.timedelta(seconds=1)
    assert_that(other_time).is_greater_than(reference_time)


def test_is_greater_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_greater_than(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be greater than "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_greater_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_greater_than_or_equal_to():
    assert_that(reference_time).is_greater_than_or_equal_to(reference_time)


def test_is_greater_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_greater_than_or_equal_to(other_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be greater than or equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_greater_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_greater_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_less_than():
    other_time = reference_time + datetime.timedelta(seconds=1)
    assert_that(reference_time).is_less_than(other_time)


def test_is_less_than_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(other_time).is_less_than(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be less than "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_less_than_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_less_than_or_equal_to():
    assert_that(reference_time).is_less_than_or_equal_to(reference_time)


def test_is_less_than_or_equal_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(other_time).is_less_than_or_equal_to(reference_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be less than or equal to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_less_than_or_equal_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_less_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_between():
    other_time = reference_time + datetime.timedelta(seconds=1)
    third_time = reference_time + datetime.timedelta(seconds=2)
    assert_that(other_time).is_between(reference_time, third_time)


def test_is_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        third_time = reference_time + datetime.timedelta(seconds=2)
        assert_that(reference_time).is_between(other_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be between "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>"
        + r" and <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was not."
    )


def test_is_between_bad_arg1_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_between(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a datetime, to match val, but was <123> (int)")


def test_is_between_bad_arg2_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_between(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a datetime, to match val, but was <123> (int)")


def test_is_not_between():
    other_time = reference_time + datetime.timedelta(minutes=5)
    third_time = reference_time + datetime.timedelta(minutes=10)
    assert_that(reference_time).is_not_between(other_time, third_time)


def test_is_not_between_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(minutes=5)
        third_time = reference_time + datetime.timedelta(minutes=10)
        assert_that(other_time).is_not_between(reference_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to not be between "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> and <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?>, but was."
    )


def test_is_not_between_bad_arg1_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_not_between(123, 456)
    assert_that(str(exc_info.value)).is_equal_to("given low arg must be a datetime, to match val, but was <123> (int)")


def test_is_not_between_bad_arg2_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_not_between(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to("given high arg must be a datetime, to match val, but was <123> (int)")


def test_is_close_to():
    other_time = reference_time + datetime.timedelta(seconds=1)
    assert_that(reference_time).is_close_to(other_time, datetime.timedelta(minutes=5))


def test_is_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(minutes=5)
        assert_that(reference_time).is_close_to(other_time, datetime.timedelta(minutes=1))
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to be close to "
        + r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> within tolerance <\d+:\d+:\d+>, but was not."
    )


def test_is_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_close_to(123, 456)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_close_to(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given tolerance arg must be a timedelta, to match val, but was <123> (int)"
    )


def test_is_not_close_to():
    other_time = reference_time + datetime.timedelta(minutes=5)
    assert_that(reference_time).is_not_close_to(other_time, datetime.timedelta(minutes=4))


def test_is_not_close_to_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_not_close_to(other_time, datetime.timedelta(minutes=5))
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> to not be close to "
        r"<\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?> within tolerance <\d+:\d+:\d+>, but was."
    )


def test_is_not_close_to_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_time).is_not_close_to(123, 456)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a datetime, to match val, but was <123> (int)"
    )


def test_is_not_close_to_bad_tolerance_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        other_time = reference_time + datetime.timedelta(seconds=1)
        assert_that(reference_time).is_not_close_to(other_time, 123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given tolerance arg must be a timedelta, to match val, but was <123> (int)"
    )


reference_delta = datetime.timedelta(seconds=60)


def test_is_greater_than_timedelta():
    other_time = datetime.timedelta(seconds=120)
    assert_that(other_time).is_greater_than(reference_delta)


def test_is_greater_than_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(reference_delta).is_greater_than(other_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be greater than <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_greater_than(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a timedelta, to match val, but was <123> (int)"
    )


def test_is_greater_than_or_equal_to_timedelta():
    assert_that(reference_delta).is_greater_than_or_equal_to(reference_delta)


def test_is_greater_than_or_equal_to_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(reference_delta).is_greater_than_or_equal_to(other_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be greater than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_greater_than_or_equal_to_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_greater_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a timedelta, to match val, but was <123> (int)"
    )


def test_is_less_than_timedelta():
    other_delta = datetime.timedelta(seconds=90)
    assert_that(reference_delta).is_less_than(other_delta)


def test_is_less_than_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(other_delta).is_less_than(reference_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be less than <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_less_than(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a timedelta, to match val, but was <123> (int)"
    )


def test_is_less_than_or_equal_to_timedelta():
    assert_that(reference_delta).is_less_than_or_equal_to(reference_delta)


def test_is_less_than_or_equal_to_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_delta = datetime.timedelta(seconds=90)
        assert_that(other_delta).is_less_than_or_equal_to(reference_delta)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be less than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_less_than_or_equal_to_timedelta_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(reference_delta).is_less_than_or_equal_to(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given other arg must be a timedelta, to match val, but was <123> (int)"
    )


def test_is_between_timedelta():
    other_time = datetime.timedelta(seconds=90)
    third_time = datetime.timedelta(seconds=120)
    assert_that(other_time).is_between(reference_delta, third_time)


def test_is_between_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.timedelta(seconds=30)
        third_time = datetime.timedelta(seconds=40)
        assert_that(reference_delta).is_between(other_time, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to be between <\d{1,2}:\d{2}:\d{2}> and <\d{1,2}:\d{2}:\d{2}>, but was not."
    )


def test_is_not_between_timedelta():
    other_time = datetime.timedelta(seconds=90)
    third_time = datetime.timedelta(seconds=120)
    assert_that(reference_delta).is_not_between(other_time, third_time)


def test_is_not_between_timedelta_failure():
    with pytest.raises(AssertionError) as exc_info:
        other_time = datetime.timedelta(seconds=90)
        third_time = datetime.timedelta(seconds=120)
        assert_that(other_time).is_not_between(reference_delta, third_time)
    assert_that(str(exc_info.value)).matches(
        r"Expected <\d{1,2}:\d{2}:\d{2}> to not be between <\d{1,2}:\d{2}:\d{2}> and <\d{1,2}:\d{2}:\d{2}>, but was."
    )


class _DatetimeSubclass(datetime.datetime):
    pass


def test_datetime_subclass_is_accepted():
    earlier = _DatetimeSubclass(2026, 1, 1, 12, 0, 0)
    later = _DatetimeSubclass(2026, 1, 2, 12, 0, 0)
    assert_that(earlier).is_before(later)
    assert_that(later).is_after(earlier)
    assert_that(earlier).is_close_to(later, datetime.timedelta(days=2))


def test_datetime_subclass_still_fails_real_mismatch():
    earlier = _DatetimeSubclass(2026, 1, 1, 12, 0, 0)
    later = _DatetimeSubclass(2026, 1, 2, 12, 0, 0)
    with pytest.raises(AssertionError):
        assert_that(later).is_before(earlier)


@pytest.mark.parametrize("name", ["is_close_to", "is_not_close_to"])
@pytest.mark.parametrize("apart", [datetime.timedelta(), datetime.timedelta(seconds=1)], ids=["equal", "apart"])
@pytest.mark.parametrize("below", [datetime.timedelta(seconds=-5), datetime.timedelta(microseconds=-1)])
def test_closeness_refuses_a_timedelta_tolerance_below_nothing(name, apart, below):
    # as a negative number is refused: under it `is_not_close_to` passed for every two different moments
    with pytest.raises(ValueError, match=r"^given tolerance arg must not be negative$"):
        getattr(assert_that(reference_time), name)(reference_time + apart, below)


def test_closeness_takes_a_timedelta_tolerance_of_nothing():
    nothing = datetime.timedelta()
    assert_that(reference_time).is_close_to(reference_time, nothing)
    assert_that(reference_time).is_not_close_to(reference_time + datetime.timedelta(microseconds=1), nothing)


def test_a_tolerance_below_nothing_is_refused_by_what_it_holds_and_not_by_what_its_class_answers():
    class NeverLess(datetime.timedelta):
        def __lt__(self, other):
            return False

    with pytest.raises(ValueError, match="given tolerance arg must not be negative"):
        assert_that(reference_time).is_close_to(reference_time, NeverLess(seconds=-5))


def test_is_close_to_tolerance_format():
    base = datetime.datetime(2026, 1, 1, 0, 0, 0)
    other = datetime.datetime(2026, 1, 3, 0, 0, 0)
    tolerance = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4)
    with pytest.raises(AssertionError) as exc_info:
        assert_that(base).is_close_to(other, tolerance)
    assert_that(str(exc_info.value)).contains("within tolerance <26:03:04>")


_NOON = datetime.datetime(2026, 1, 1, 12)
_NOON_UTC = _NOON.replace(tzinfo=datetime.timezone.utc)
_EAST = datetime.timezone(datetime.timedelta(hours=2))
_FRACTION, _OTHER_FRACTION = _NOON.replace(microsecond=123456), _NOON.replace(microsecond=120001)


def _headline(call) -> str:
    with pytest.raises(AssertionError) as caught:
        call()
    return str(caught.value).splitlines()[0]


@pytest.mark.parametrize(
    ("ask", "said"),
    [
        (
            lambda: assert_that(_NOON).is_close_to(
                _NOON + datetime.timedelta(milliseconds=900), datetime.timedelta(milliseconds=500)
            ),
            "Expected <2026-01-01 12:00:00> to be close to <2026-01-01 12:00:00.900000>"
            " within tolerance <0:00:00.500000>, but was not.",
        ),
        (
            lambda: assert_that(_NOON_UTC).is_close_to(_NOON.replace(tzinfo=_EAST), datetime.timedelta(minutes=5)),
            "Expected <2026-01-01 12:00:00+00:00> to be close to <2026-01-01 12:00:00+02:00>"
            " within tolerance <0:05:00>, but was not.",
        ),
        (
            lambda: assert_that(_FRACTION).is_not_close_to(_OTHER_FRACTION, datetime.timedelta(seconds=1)),
            "Expected <2026-01-01 12:00:00.123456> to not be close to <2026-01-01 12:00:00.120001>"
            " within tolerance <0:00:01>, but was.",
        ),
        (
            lambda: assert_that(_FRACTION).is_less_than(_OTHER_FRACTION),
            "Expected <2026-01-01 12:00:00.123456> to be less than <2026-01-01 12:00:00.120001>, but was not.",
        ),
        (
            lambda: assert_that(_NOON_UTC).is_less_than(_NOON.replace(hour=13, minute=30, tzinfo=_EAST)),
            "Expected <2026-01-01 12:00:00+00:00> to be less than <2026-01-01 13:30:00+02:00>, but was not.",
        ),
        (
            lambda: assert_that(_FRACTION).is_less_than_or_equal_to(_OTHER_FRACTION),
            "Expected <2026-01-01 12:00:00.123456> to be less than or equal to <2026-01-01 12:00:00.120001>,"
            " but was not.",
        ),
        (
            lambda: assert_that(_OTHER_FRACTION).is_greater_than(_FRACTION),
            "Expected <2026-01-01 12:00:00.120001> to be greater than <2026-01-01 12:00:00.123456>, but was not.",
        ),
        (
            lambda: assert_that(_OTHER_FRACTION).is_greater_than_or_equal_to(_FRACTION),
            "Expected <2026-01-01 12:00:00.120001> to be greater than or equal to <2026-01-01 12:00:00.123456>,"
            " but was not.",
        ),
        (
            lambda: assert_that(_OTHER_FRACTION).is_between(_FRACTION, _NOON_UTC.replace(tzinfo=None, second=1)),
            "Expected <2026-01-01 12:00:00.120001> to be between <2026-01-01 12:00:00.123456>"
            " and <2026-01-01 12:00:01>, but was not.",
        ),
        (
            lambda: assert_that(_FRACTION).is_not_between(_OTHER_FRACTION, _NOON.replace(second=1)),
            "Expected <2026-01-01 12:00:00.123456> to not be between <2026-01-01 12:00:00.120001>"
            " and <2026-01-01 12:00:01>, but was.",
        ),
        (
            lambda: assert_that(datetime.datetime(999, 1, 2, 3, 4, 5)).is_less_than(datetime.datetime(998, 1, 2)),
            "Expected <0999-01-02 03:04:05> to be less than <0998-01-02 00:00:00>, but was not.",
        ),
    ],
)
def test_a_headline_prints_what_a_moment_holds_past_the_second(ask, said):
    assert_that(_headline(ask)).is_equal_to(said)


@pytest.mark.parametrize(
    ("ask", "said"),
    [
        (
            lambda: assert_that(_NOON).is_close_to(
                _NOON + datetime.timedelta(days=3), datetime.timedelta(hours=26, minutes=3, seconds=4)
            ),
            "Expected <2026-01-01 12:00:00> to be close to <2026-01-04 12:00:00>"
            " within tolerance <26:03:04>, but was not.",
        ),
        (
            lambda: assert_that(_NOON).is_not_close_to(_NOON.replace(second=1), datetime.timedelta(seconds=5)),
            "Expected <2026-01-01 12:00:00> to not be close to <2026-01-01 12:00:01>"
            " within tolerance <0:00:05>, but was.",
        ),
        (
            lambda: assert_that(_NOON).is_greater_than_or_equal_to(_NOON.replace(hour=15)),
            "Expected <2026-01-01 12:00:00> to be greater than or equal to <2026-01-01 15:00:00>, but was not.",
        ),
        (
            lambda: assert_that(_NOON).is_between(_NOON.replace(hour=13), _NOON.replace(hour=14)),
            "Expected <2026-01-01 12:00:00> to be between <2026-01-01 13:00:00>"
            " and <2026-01-01 14:00:00>, but was not.",
        ),
    ],
)
def test_a_headline_that_dropped_nothing_reads_as_it_did(ask, said):
    assert_that(_headline(ask)).is_equal_to(said)


@pytest.mark.parametrize(
    ("tolerance", "said"),
    [
        (datetime.timedelta(seconds=5), "0:00:05"),
        (datetime.timedelta(hours=26, minutes=3, seconds=4), "26:03:04"),
        (datetime.timedelta(days=400), "9600:00:00"),
        (datetime.timedelta(milliseconds=500), "0:00:00.500000"),
        (datetime.timedelta(microseconds=1), "0:00:00.000001"),
        (datetime.timedelta(days=1, hours=2, minutes=3, seconds=4, microseconds=500000), "26:03:04.500000"),
        (datetime.timedelta(days=10**6, microseconds=1), "24000000:00:00.000001"),
        (datetime.timedelta.max, "23999999999:59:59.999999"),
    ],
)
def test_a_tolerance_prints_exactly(tolerance, said):
    headline = _headline(lambda: assert_that(_NOON).is_not_close_to(_NOON, tolerance))
    assert_that(headline).ends_with(f"within tolerance <{said}>, but was.")


def test_is_before_after_reject_equal():
    moment = datetime.datetime(2026, 1, 1, 12, 0, 0)
    same = datetime.datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(AssertionError):
        assert_that(moment).is_before(same)
    with pytest.raises(AssertionError):
        assert_that(moment).is_after(same)


def test_is_equal_to_ignoring_milliseconds_each_component_mismatch():
    base = datetime.datetime(2020, 1, 2, 3, 4, 5, 123)
    for other in (
        datetime.datetime(2020, 1, 3, 3, 4, 5),
        datetime.datetime(2020, 1, 2, 9, 4, 5),
        datetime.datetime(2020, 1, 2, 3, 9, 5),
        datetime.datetime(2020, 1, 2, 3, 4, 9),
    ):
        with pytest.raises(AssertionError):
            assert_that(base).is_equal_to_ignoring_milliseconds(other)


def test_is_equal_to_ignoring_seconds_each_component_mismatch():
    base = datetime.datetime(2020, 1, 2, 3, 4, 5)
    for other in (
        datetime.datetime(2020, 1, 3, 3, 4, 5),
        datetime.datetime(2020, 1, 2, 9, 4, 5),
        datetime.datetime(2020, 1, 2, 3, 9, 5),
    ):
        with pytest.raises(AssertionError):
            assert_that(base).is_equal_to_ignoring_seconds(other)


class TestIsBeforeOrEqualTo:
    def test_before(self):
        reference_time = datetime.datetime(2020, 1, 1)
        other_time = datetime.datetime(2020, 1, 2)
        assert_that(reference_time).is_before_or_equal_to(other_time)

    def test_equal(self):
        reference_time = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(reference_time).is_before_or_equal_to(reference_time)

    def test_failure(self):
        reference_time = datetime.datetime(2020, 1, 2)
        other_time = datetime.datetime(2020, 1, 1)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(reference_time).is_before_or_equal_to(other_time)
        assert_that(str(exc_info.value)).contains("to be before or equal to")

    def test_bad_val_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that("foo").is_before_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be a datetime")

    def test_bad_arg_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_before_or_equal_to("foo")
        assert_that(str(exc_info.value)).contains("given other arg must be a datetime")

    def test_date_not_datetime_val(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.date(2020, 1, 1)).is_before_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be a datetime")

    def test_date_not_datetime_arg(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_before_or_equal_to(datetime.date(2020, 1, 1))
        assert_that(str(exc_info.value)).contains("given other arg must be a datetime")


class TestIsAfterOrEqualTo:
    def test_after(self):
        reference_time = datetime.datetime(2020, 1, 2)
        other_time = datetime.datetime(2020, 1, 1)
        assert_that(reference_time).is_after_or_equal_to(other_time)

    def test_equal(self):
        reference_time = datetime.datetime(2020, 1, 1, 12, 0, 0)
        assert_that(reference_time).is_after_or_equal_to(reference_time)

    def test_failure(self):
        reference_time = datetime.datetime(2020, 1, 1)
        other_time = datetime.datetime(2020, 1, 2)
        with pytest.raises(AssertionError) as exc_info:
            assert_that(reference_time).is_after_or_equal_to(other_time)
        assert_that(str(exc_info.value)).contains("to be after or equal to")

    def test_bad_val_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that("foo").is_after_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be a datetime")

    def test_bad_arg_type(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.datetime.now()).is_after_or_equal_to("foo")
        assert_that(str(exc_info.value)).contains("given other arg must be a datetime")

    def test_date_not_datetime_val(self):
        with pytest.raises(TypeError) as exc_info:
            assert_that(datetime.date(2020, 1, 1)).is_after_or_equal_to(datetime.datetime.now())
        assert_that(str(exc_info.value)).contains("val must be a datetime")


def test_naive_vs_aware_comparison_raises_clear_type_error():
    # mixing naive and aware must raise an actionable TypeError, not Python's raw "can't compare offset-naive"
    naive = datetime.datetime(2020, 1, 1, 12)
    aware = datetime.datetime(2020, 1, 1, 12, tzinfo=datetime.timezone.utc)
    for call in (
        lambda: assert_that(naive).is_before(aware),
        lambda: assert_that(naive).is_after(aware),
        lambda: assert_that(naive).is_before_or_equal_to(aware),
        lambda: assert_that(naive).is_after_or_equal_to(aware),
    ):
        with pytest.raises(TypeError, match=r"timezone-aware one\. Make both aware or both naive first"):
            call()


class TestNaiveAwareGuardCoversEqualityToo:
    """The relational half already refuses the mix; comparing wall-clock fields hides it silently."""

    @staticmethod
    def _pair():
        naive = datetime.datetime(2020, 1, 2, 3, 4, 5)
        moscow = datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
        return naive, moscow

    def test_ignoring_milliseconds_refuses_a_mixed_pair(self):
        naive, aware = self._pair()
        with pytest.raises(TypeError, match="timezone-naive"):
            assert_that(naive).is_equal_to_ignoring_milliseconds(aware)

    def test_ignoring_seconds_refuses_a_mixed_pair(self):
        # these two read equal to the minute yet stand three hours apart
        naive, aware = self._pair()
        with pytest.raises(TypeError, match="timezone-naive"):
            assert_that(naive).is_equal_to_ignoring_seconds(aware)

    def test_ignoring_time_refuses_a_mixed_pair(self):
        naive, aware = self._pair()
        with pytest.raises(TypeError, match="timezone-naive"):
            assert_that(naive).is_equal_to_ignoring_time(aware)

    def test_a_uniform_pair_still_compares(self):
        naive, aware = self._pair()
        assert_that(naive).is_equal_to_ignoring_seconds(naive)
        assert_that(aware).is_equal_to_ignoring_seconds(aware)


class TestDynamicComponentAssertions:
    """`has_<attr>()` reaching a datetime's own fields.

    A datetime has its own protocol, so the typed surface deliberately does not declare these and a
    checker rejects them. The runtime resolves them from the value like any other attribute, and that
    split is documented as the boundary of the typed surface, which makes it worth pinning.
    """

    def test_every_component_is_reachable(self):
        moment = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)
        assert_that(moment).has_year(1980)
        assert_that(moment).has_month(1)
        assert_that(moment).has_day(2)
        assert_that(moment).has_hour(3)
        assert_that(moment).has_minute(4)
        assert_that(moment).has_second(5)
        assert_that(moment).has_microsecond(6)

    def test_a_wrong_component_fails(self):
        # without this the check above passes just as well against a resolver that asserts nothing
        moment = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)
        with pytest.raises(AssertionError, match="year"):
            assert_that(moment).has_year(1981)


class TestAMessageNamesTheWholeInstant:
    """Rendered with `strftime`, two instants five hours apart read as "12:00 is not before 14:00"."""

    def test_the_offset_and_the_fraction_are_printed(self):
        east = datetime.timezone(datetime.timedelta(hours=3))
        later = datetime.datetime(2026, 1, 1, 14, tzinfo=datetime.timezone.utc)
        earlier = datetime.datetime(2026, 1, 1, 12, 0, 0, 500000, tzinfo=east)
        outcome = assert_that(later).check().is_before(earlier)
        assert_that(outcome.message).contains("+00:00").contains("+03:00").contains(".500000")

    def test_a_naive_pair_still_reads_as_it_always_did(self):
        outcome = assert_that(datetime.datetime(2026, 1, 1, 14)).check().is_before(datetime.datetime(2026, 1, 1, 12))
        assert_that(outcome.message).contains("<2026-01-01 14:00:00> to be before <2026-01-01 12:00:00>")

    @pytest.mark.parametrize("call", ["is_after", "is_before_or_equal_to", "is_after_or_equal_to"])
    def test_every_relational_message_carries_it(self, call):
        east = datetime.timezone(datetime.timedelta(hours=3))
        one = datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc)
        other = datetime.datetime(2026, 1, 1, 12, tzinfo=east)
        first, second = (other, one) if call.startswith("is_after") else (one, other)
        outcome = getattr(assert_that(first).check(), call)(second)
        assert_that(outcome.passed).described_as("the pair chosen to fail").is_false()
        assert_that(outcome.message).contains("+03:00")


class _Jumps(datetime.tzinfo):
    """A clock that changes its offset once, at a moment given in UTC: back for a repeated stretch, or forward."""

    def __init__(self, at: datetime.datetime, before: datetime.timedelta, after: datetime.timedelta) -> None:
        self.at, self.before, self.after = at, before, after

    def utcoffset(self, moment):
        wall = moment.replace(tzinfo=None)
        first_reading = wall < self.at + min(self.before, self.after)
        repeated = self.after < self.before and wall < self.at + self.before and not moment.fold
        return self.before if first_reading or repeated else self.after

    def tzname(self, moment):
        return "jumps"

    def dst(self, moment):
        return None

    def fromutc(self, moment):
        wall = moment.replace(tzinfo=None)
        if wall < self.at:
            return moment + self.before
        return (moment + self.after).replace(fold=wall < self.at + (self.before - self.after))


_HOUR = datetime.timedelta(hours=1)
_FALLS_BACK = _Jumps(datetime.datetime(2026, 11, 1, 1), 2 * _HOUR, _HOUR)
_BACK_A_MINUTE = _Jumps(datetime.datetime(2026, 11, 1, 11, 1), _HOUR, _HOUR - datetime.timedelta(minutes=1))
_BACK_BY_THIRTY = _Jumps(datetime.datetime(2026, 11, 1, 11, 1, 10), _HOUR, _HOUR - datetime.timedelta(seconds=30))
_ON_BY_TWENTY = _Jumps(datetime.datetime(2026, 11, 1, 11, 0, 30), _HOUR, _HOUR + datetime.timedelta(seconds=20))


class _OnePerOffset(datetime.tzinfo):
    """One object per offset of a zone that falls back at 01:00 UTC on 1 November 2026, as some libraries hand out."""

    def __init__(self, hours: int) -> None:
        self.hours = hours

    def utcoffset(self, moment):
        return datetime.timedelta(hours=self.hours)

    def tzname(self, moment):
        return f"+{self.hours}"

    def dst(self, moment):
        return None

    def fromutc(self, moment):
        zone = _SUMMER if moment.replace(tzinfo=None) < datetime.datetime(2026, 11, 1, 1) else _WINTER
        return (moment + datetime.timedelta(hours=zone.hours)).replace(tzinfo=zone)


_SUMMER, _WINTER = _OnePerOffset(2), _OnePerOffset(1)


class TestTwoZonesAreOneInstant:
    """The guide says making both sides aware is what makes these well defined, and field-by-field they were not."""

    @pytest.mark.parametrize(
        "call",
        ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"],
    )
    def test_the_same_wall_clock_in_two_zones_is_not_the_same_instant(self, call):
        east = datetime.timezone(datetime.timedelta(hours=5))
        outcome = getattr(assert_that(datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc)).check(), call)(
            datetime.datetime(2026, 1, 1, 12, tzinfo=east)
        )
        assert_that(outcome.passed).is_false()

    @pytest.mark.parametrize(
        "call",
        ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds", "is_equal_to_ignoring_time"],
    )
    def test_one_instant_written_two_ways_is_equal(self, call):
        east = datetime.timezone(datetime.timedelta(hours=5))
        getattr(assert_that(datetime.datetime(2026, 1, 1, 12, tzinfo=datetime.timezone.utc)), call)(
            datetime.datetime(2026, 1, 1, 17, tzinfo=east)
        )

    def test_a_day_is_the_day_of_the_value_under_test(self):
        """Read in the subject's zone: the same instant falls on a different date in another one."""
        east = datetime.timezone(datetime.timedelta(hours=5))
        assert_that(datetime.datetime(2026, 1, 1, 22, tzinfo=datetime.timezone.utc)).is_equal_to_ignoring_time(
            datetime.datetime(2026, 1, 2, 3, tzinfo=east)
        )

    @pytest.mark.parametrize("call", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"])
    def test_the_two_readings_of_a_repeated_hour_are_an_hour_apart(self, call):
        """Read on the value's clock, the other moment shows the same wall time and another offset."""
        first = datetime.datetime(2026, 11, 1, 2, 30, tzinfo=_FALLS_BACK)
        hour_later = first.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=1)
        outcome = getattr(assert_that(first).check(), call)(hour_later)
        assert_that(outcome.passed).is_false()
        assert_that(outcome.message).contains("02:30").contains("+02:00> to be equal to").contains("+01:00>")
        getattr(assert_that(first), call)(first.astimezone(datetime.timezone.utc))
        getattr(assert_that(first.replace(fold=1)), call)(hour_later)
        getattr(assert_that(first).not_, call)(hour_later)

    @pytest.mark.parametrize("call", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"])
    def test_two_on_one_zone_object_are_left_to_their_wall_clocks_as_equality_is(self, call):
        first = datetime.datetime(2026, 11, 1, 2, 30, tzinfo=_FALLS_BACK)
        second = first.replace(fold=1)
        assert_that(first == second).is_true()
        getattr(assert_that(first), call)(second)

    @pytest.mark.parametrize("call", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"])
    def test_a_fold_set_where_the_clock_reads_once_changes_nothing(self, call):
        noon = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=_FALLS_BACK, fold=1)
        getattr(assert_that(noon), call)(noon.astimezone(datetime.timezone.utc))

    @pytest.mark.parametrize("call", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"])
    def test_a_zone_that_hands_out_an_object_per_offset_is_told_by_the_offsets(self, call):
        first = datetime.datetime(2026, 11, 1, 2, 30, tzinfo=_SUMMER)
        hour_later = first.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=1)
        read = hour_later.astimezone(_SUMMER)
        assert_that([read.tzinfo is _WINTER, read.fold, read.hour, read.minute]).is_equal_to([True, 0, 2, 30])
        assert_that(getattr(assert_that(first).check(), call)(hour_later).passed).is_false()
        getattr(assert_that(first), call)(first.astimezone(datetime.timezone.utc))

    @pytest.mark.parametrize("call", ["is_equal_to_ignoring_milliseconds", "is_equal_to_ignoring_seconds"])
    def test_one_moment_read_through_two_objects_of_one_offset_is_one_reading(self, call):
        first = datetime.datetime(2026, 11, 1, 2, 30, tzinfo=_OnePerOffset(2))
        same = first.astimezone(datetime.timezone.utc)
        assert_that(same.astimezone(first.tzinfo).tzinfo).is_same_as(_SUMMER).is_not_same_as(first.tzinfo)
        getattr(assert_that(first), call)(same)

    def test_a_minute_the_clock_reads_twice_is_two_readings_however_close(self):
        """Twenty seconds apart, and each reads 12:00 on a clock that went back a minute between them."""
        first = datetime.datetime(2026, 11, 1, 12, 0, 50, tzinfo=_BACK_A_MINUTE)
        second = datetime.datetime(2026, 11, 1, 11, 1, 10, tzinfo=datetime.timezone.utc)
        read = second.astimezone(_BACK_A_MINUTE)
        assert_that([second - first, read.hour, read.minute, read.fold]).is_equal_to(
            [datetime.timedelta(seconds=20), 12, 0, 1]
        )
        assert_that(assert_that(first).check().is_equal_to_ignoring_seconds(second).passed).is_false()
        assert_that(first).is_equal_to_ignoring_seconds(second - datetime.timedelta(seconds=30))

    def test_a_minute_left_and_come_back_to_is_two_readings_with_no_fold_between_them(self):
        """12:01:05, back to 12:00:40 at 12:01:10, then 12:01:15: 40 seconds apart, neither in the stretch read twice"""
        first = datetime.datetime(2026, 11, 1, 11, 1, 5, tzinfo=datetime.timezone.utc)
        second = datetime.datetime(2026, 11, 1, 11, 1, 45, tzinfo=datetime.timezone.utc)
        early, late = first.astimezone(_BACK_BY_THIRTY), second.astimezone(_BACK_BY_THIRTY)
        assert_that([early.second, late.second, early.minute, late.minute, early.fold, late.fold]).is_equal_to(
            [5, 15, 1, 1, 0, 0]
        )
        assert_that(assert_that(early).check().is_equal_to_ignoring_seconds(second).passed).is_false()
        assert_that(assert_that(late).check().is_equal_to_ignoring_seconds(first).passed).is_false()
        assert_that(early).is_equal_to_ignoring_seconds(first)

    def test_a_clock_that_goes_forward_inside_a_minute_reads_it_once(self):
        """Twenty-five seconds apart and both read 12:00, on either side of a change of twenty seconds."""
        first = datetime.datetime(2026, 11, 1, 12, 0, 10, tzinfo=_ON_BY_TWENTY)
        second = datetime.datetime(2026, 11, 1, 11, 0, 35, tzinfo=datetime.timezone.utc)
        read = second.astimezone(_ON_BY_TWENTY)
        assert_that([second - first, read.minute, read.second, read.utcoffset() - first.utcoffset()]).is_equal_to(
            [datetime.timedelta(seconds=25), 0, 55, datetime.timedelta(seconds=20)]
        )
        assert_that(first).is_equal_to_ignoring_seconds(second)
        assert_that(first.replace(fold=1)).is_equal_to_ignoring_seconds(second)
        assert_that(read.replace(fold=1)).is_equal_to_ignoring_seconds(first.astimezone(datetime.timezone.utc))

    def test_a_fold_set_where_the_clock_reads_once_passes_two_moments_of_one_minute(self):
        noon = datetime.datetime(2026, 11, 1, 12, 0, 10, tzinfo=_FALLS_BACK, fold=1)
        later = noon.astimezone(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        earlier = noon.astimezone(datetime.timezone.utc) - datetime.timedelta(seconds=5)
        assert_that(noon).is_equal_to_ignoring_seconds(later).is_equal_to_ignoring_seconds(earlier)

    def test_a_day_holds_both_readings_of_its_repeated_hour(self):
        first = datetime.datetime(2026, 11, 1, 2, 30, tzinfo=_FALLS_BACK)
        hour_later = first.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=1)
        assert_that(first).is_equal_to_ignoring_time(hour_later)

    def test_a_naive_pair_is_left_as_it_is(self):
        assert_that(datetime.datetime(2026, 1, 1, 12, 0, 5)).is_equal_to_ignoring_seconds(
            datetime.datetime(2026, 1, 1, 12, 0, 55)
        )
