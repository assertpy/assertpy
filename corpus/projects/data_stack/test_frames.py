"""numpy scalars and pandas frames as operands, which is where the numeric bound broke a suite before.

A numpy integer is a `numbers.Number` at runtime and inherits nothing static, so every type written as a
list of concrete types refuses it.  That mistake shipped once; this project is what notices the next one.
"""

from __future__ import annotations

import numpy
import pandas

from assertpy import assert_that


def frame() -> pandas.DataFrame:
    return pandas.DataFrame({"id": [1, 2, 3], "total": [10.0, 20.5, 30.0], "customer": ["a", "b", "c"]})


def test_numpy_scalars_compare_against_builtin_numbers() -> None:
    assert_that(1).is_greater_than(numpy.int64(0))
    assert_that(1.5).is_greater_than(numpy.float64(1))
    assert_that(1).is_close_to(numpy.float64(1), numpy.float64(0.1))
    assert_that(int(numpy.int32(5))).is_between(1, 10)


def test_numpy_values_pass_through_the_assertions_that_take_them() -> None:
    total = numpy.float64(30.0)
    assert_that(float(total)).is_equal_to(30.0)
    assert_that(bool(numpy.bool_(True))).is_true()


def test_a_frame_reports_its_own_shape() -> None:
    assert_that(frame().shape).is_equal_to((3, 3))
    assert_that(list(frame().columns)).contains("id", "total", "customer")
    assert_that(frame()["total"].sum()).is_greater_than(60)


def test_frames_compare_with_the_frame_assertion() -> None:
    assert_that(frame()).is_frame_equal(frame())


def test_arrays_compare_with_the_array_assertions() -> None:
    values = numpy.array([1.0, 2.0, 3.0])
    assert_that(values).is_array_equal(numpy.array([1.0, 2.0, 3.0]))
    assert_that(values).is_array_close_to(numpy.array([1.0, 2.0, 3.001]), atol=0.01)


def test_a_column_walks_like_any_other_sequence() -> None:
    customers = list(frame()["customer"])
    assert_that(customers).is_length(3).contains("a")
    assert_that(customers).filtered_on(lambda name: name > "a").is_equal_to(["b", "c"])


def test_a_predicate_answering_with_a_numpy_bool_is_accepted() -> None:
    # the verdict is read for truth, and numpy answers comparisons with its own boolean
    assert_that([1, 2, 3]).each(lambda value: numpy.bool_(value > 0))
