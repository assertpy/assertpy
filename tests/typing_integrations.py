"""What `assert_that()` hands back for values from the real libraries, pinned per case.

`tests/test_typing.py` pins the same relation against stand-in classes, which is what runs everywhere.
This file needs pandas, polars and numpy installed and is checked by `tests/test_typing_integrations.py`,
because a stand-in proves the overload is written correctly and says nothing about whether a real
`DataFrame` still matches it.  Both are needed: the shapes are structural, and the structures belong to
somebody else.

Each line carries its case name, and `tests/typing_integrations_baseline.py` records which checkers
report anything on it.  A case every checker agrees with records nothing.
"""

from __future__ import annotations

from typing import Any, assert_type

import numpy
import pandas
import polars

from assertpy import assert_that
from assertpy._engine._capable_typing import _CapableAssertion
from assertpy._engine._typing import _ArrayAssertion, _FrameAssertion


def resolution(
    frame: pandas.DataFrame,
    polars_frame: polars.DataFrame,
    series: pandas.Series,
    polars_series: polars.Series,
    array: numpy.ndarray[Any, Any],
    index: pandas.Index,
) -> None:
    """Which view each real value narrows to, written as the answer the runtime would justify."""
    assert_type(assert_that(frame), _FrameAssertion[pandas.DataFrame])  # case: pandas-frame
    assert_type(assert_that(polars_frame), _FrameAssertion[polars.DataFrame])  # case: polars-frame
    assert_type(assert_that(array), _ArrayAssertion[numpy.ndarray[Any, Any]])  # case: numpy-array
    # a series and an index buy no view: nothing separates them structurally and an index is outside
    # `is_frame_equal`. They reach the umbrella, which hands back its own surface rather than the builder
    assert_type(assert_that(series), _CapableAssertion[pandas.Series])  # case: pandas-series
    assert_type(assert_that(polars_series), _CapableAssertion[polars.Series])  # case: polars-series
    assert_type(assert_that(index), _CapableAssertion[pandas.Index])  # case: pandas-index


def calls_that_must_keep_working(frame: pandas.DataFrame, array: numpy.ndarray[Any, Any]) -> None:
    """Every family the runtime accepts for these values, which the narrowed view has to carry."""
    assert_that(frame).is_not_empty()  # case: frame-sized
    assert_that(frame).contains(1)  # case: frame-membership
    assert_that(frame).does_not_contain(1)  # case: frame-non-membership
    assert_that(frame).each(lambda item: True)  # case: frame-walk
    assert_that(frame).is_frame_equal(frame)  # case: frame-own
    assert_that(frame).is_array_equal(frame)  # case: frame-array
    assert_type(assert_that(frame).value.columns, pandas.Index[str])  # case: frame-value
    assert_that(array).is_not_empty()  # case: array-sized
    assert_that(array).does_not_contain(1)  # case: array-non-membership
    assert_that(array).is_array_close_to(array)  # case: array-own
    # `dtype` reads as `Any`, which is numpy's typing; this case holds that the chain reaches its members at all
    assert_type(assert_that(array).value.size, int)  # case: array-value


def calls_the_runtime_refuses(frame: pandas.DataFrame) -> None:
    """Families a frame is outside, measured from its refusals rather than assumed."""
    assert_that(frame).at_json_path("$.a")  # case: frame-not-a-document
    assert_that(frame).is_between(1, 2)  # case: frame-not-ordered
    assert_that(frame).is_alpha()  # case: frame-not-text
