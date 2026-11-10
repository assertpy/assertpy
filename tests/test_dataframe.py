import contextlib
import sys
import types
from unittest.mock import patch

import pytest

from assertpy import assert_that
from tests.optional import needs


@contextlib.contextmanager
def _fake_frame_lib(root, *, fail):
    """Inject a fake pandas/polars-like module so the delegation is covered without the real library.

    The fake ``DataFrame``/``Series`` classes carry ``__module__ == root`` (what the mixin routes on), and
    the fake ``testing.assert_*`` either pass or raise, echoing options so they can be asserted on.
    """
    series = type("Series", (), {"__module__": root})
    dataframe = type("DataFrame", (), {"__module__": root})
    library = types.ModuleType(root)
    testing = types.ModuleType(f"{root}.testing")

    def assert_frame_equal(actual, expected, **options):
        if fail:
            raise AssertionError(f"{root} frames differ; options={options}")

    def assert_series_equal(actual, expected, **options):
        if fail:
            raise AssertionError(f"{root} series differ")

    library.Series = series
    library.DataFrame = dataframe
    testing.assert_frame_equal = assert_frame_equal
    testing.assert_series_equal = assert_series_equal
    with patch.dict(sys.modules, {root: library, f"{root}.testing": testing}):
        yield series, dataframe


@contextlib.contextmanager
def _fake_numpy(*, fail):
    """Inject a fake numpy.testing so array assertions are covered without real numpy."""
    library = types.ModuleType("numpy")
    testing = types.ModuleType("numpy.testing")

    def assert_array_equal(actual, expected, **options):
        if fail:
            raise AssertionError(f"numpy arrays differ; options={options}")

    def assert_allclose(actual, expected, *, rtol, atol, equal_nan, **options):
        if fail:
            raise AssertionError(f"numpy not close; rtol={rtol} atol={atol} equal_nan={equal_nan} options={options}")

    def shape(value):
        """As numpy reads it: the attribute where there is one, and the length of each level otherwise."""
        held = getattr(value, "shape", None)
        if isinstance(held, tuple):
            return held
        if isinstance(value, (list, tuple)):
            inner = {shape(item) for item in value}
            return (len(value), *inner.pop()) if len(inner) == 1 else (len(value),)
        return ()

    library.shape = shape
    testing.assert_array_equal = assert_array_equal
    testing.assert_allclose = assert_allclose
    with patch.dict(sys.modules, {"numpy": library, "numpy.testing": testing}):
        yield


class TestLibraryFailureIsNotChained:
    """The library's own AssertionError is folded into our message, so it must not also head the
    traceback: pytest would print the same diff twice, once under "During handling of the above
    exception".  See TestExceptionContext in test_traceback.py for where the line is drawn."""

    def test_frame_failure_drops_the_library_exception(self):
        with _fake_frame_lib("polars", fail=True) as (_, dataframe), pytest.raises(AssertionError) as exc_info:
            assert_that(dataframe()).is_frame_equal(dataframe())
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_array_equal_failure_drops_the_library_exception(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError) as exc_info:
            assert_that([1]).is_array_equal([2])
        assert_that(exc_info.value.__suppress_context__).is_true()

    def test_array_close_failure_drops_the_library_exception(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError) as exc_info:
            assert_that([1.0]).is_array_close_to([2.0])
        assert_that(exc_info.value.__suppress_context__).is_true()


class TestIsFrameEqualDuckTyped:
    def test_non_frame_value_raises_type_error(self):
        with pytest.raises(TypeError, match="pandas or polars"):
            assert_that(5).is_frame_equal(5)

    def test_pandas_dataframe_equal_passes(self):
        with _fake_frame_lib("pandas", fail=False) as (_, dataframe):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_pandas_dataframe_not_equal_fails(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="DataFrame to equal"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_pandas_series_branch(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (series, _),
            pytest.raises(AssertionError, match="Series to equal"),
        ):
            assert_that(series()).is_frame_equal(series())

    def test_polars_dataframe_branch(self):
        with (
            _fake_frame_lib("polars", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="DataFrame to equal"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe())

    def test_options_are_passed_through(self):
        with (
            _fake_frame_lib("pandas", fail=True) as (_, dataframe),
            pytest.raises(AssertionError, match="check_dtype"),
        ):
            assert_that(dataframe()).is_frame_equal(dataframe(), check_dtype=False)

    def test_root_extracted_from_dotted_module(self):
        with _fake_frame_lib("pandas", fail=False):
            frame = type("DataFrame", (), {"__module__": "pandas.core.frame"})()
            assert_that(frame).is_frame_equal(frame)

    def test_non_frame_pandas_object_raises_type_error(self):
        # a pandas object that is neither frame nor series must be rejected, not routed to `assert_frame_equal`
        with _fake_frame_lib("pandas", fail=False):
            index = type("Index", (), {"__module__": "pandas.core.indexes.base"})()
            with pytest.raises(TypeError, match="pandas or polars"):
                assert_that(index).is_frame_equal(index)


class TestArrayAssertionsDuckTyped:
    def test_is_array_equal_passes(self):
        with _fake_numpy(fail=False):
            assert_that([1, 2, 3]).is_array_equal([1, 2, 3])

    def test_is_array_equal_fails(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="arrays to be equal"):
            assert_that([1, 2, 3]).is_array_equal([1, 2, 9])

    def test_is_array_close_to_passes(self):
        with _fake_numpy(fail=False):
            assert_that([1.0]).is_array_close_to([1.0], rtol=1e-3)

    def test_is_array_close_to_fails(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="arrays to be close"):
            assert_that([1.0]).is_array_close_to([2.0])

    def test_is_array_close_to_forwards_default_tolerances(self):
        # the defaults must match numpy's own (rtol=1e-05, atol=1e-08, equal_nan=False) and be forwarded unchanged
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match="rtol=1e-05 atol=1e-08 equal_nan=False"):
            assert_that([1.0]).is_array_close_to([2.0])

    def test_is_array_equal_forwards_options(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match=r"options=\{'strict': True\}"):
            assert_that([1, 2, 3]).is_array_equal([1, 2, 9], strict=True)

    def test_is_array_close_to_forwards_options(self):
        with _fake_numpy(fail=True), pytest.raises(AssertionError, match=r"options=\{'strict': True\}"):
            assert_that([1.0]).is_array_close_to([2.0], strict=True)


class TestMissingLibraries:
    def test_pandas_missing_raises_clear_importerror(self):
        frame = type("DataFrame", (), {"__module__": "pandas"})()
        with patch.dict(sys.modules, {"pandas": None}), pytest.raises(ImportError, match="pandas is required"):
            assert_that(frame).is_frame_equal(frame)

    def test_numpy_missing_raises_clear_importerror(self):
        with patch.dict(sys.modules, {"numpy": None}), pytest.raises(ImportError, match="numpy is required"):
            assert_that([1, 2]).is_array_equal([1, 2])


class TestRealLibraries:
    """Validate the real integration; skipped when the optional library is absent (CI without [data])."""

    def test_pandas_frame_equal_and_diff(self):
        pandas = needs("pandas")
        assert_that(pandas.DataFrame({"a": [1, 2]})).is_frame_equal(pandas.DataFrame({"a": [1, 2]}))
        with pytest.raises(AssertionError):
            assert_that(pandas.DataFrame({"a": [1, 2]})).is_frame_equal(pandas.DataFrame({"a": [1, 9]}))

    def test_pandas_options_passthrough(self):
        pandas = needs("pandas")
        actual = pandas.DataFrame({"a": [1, 2]}).astype("int64")
        expected = pandas.DataFrame({"a": [1, 2]}).astype("int32")
        assert_that(actual).is_frame_equal(expected, check_dtype=False)
        with pytest.raises(AssertionError):
            assert_that(actual).is_frame_equal(expected)

    def test_pandas_series(self):
        pandas = needs("pandas")
        assert_that(pandas.Series([1, 2, 3])).is_frame_equal(pandas.Series([1, 2, 3]))

    def test_pandas_dataframe_subclass_is_accepted(self):
        pandas = needs("pandas")

        class MyFrame(pandas.DataFrame):
            @property
            def _constructor(self):
                return MyFrame

        assert_that(MyFrame({"a": [1, 2]})).is_frame_equal(MyFrame({"a": [1, 2]}))
        with pytest.raises(AssertionError):
            assert_that(MyFrame({"a": [1, 2]})).is_frame_equal(MyFrame({"a": [1, 9]}))

    def test_pandas_index_is_rejected(self):
        pandas = needs("pandas")
        frame = pandas.DataFrame({"a": [1, 2]})
        with pytest.raises(TypeError, match="pandas or polars"):
            assert_that(frame.index).is_frame_equal(frame.index)

    def test_polars_frame_equal_and_diff(self):
        polars = needs("polars")
        assert_that(polars.DataFrame({"a": [1, 2]})).is_frame_equal(polars.DataFrame({"a": [1, 2]}))
        with pytest.raises(AssertionError):
            assert_that(polars.DataFrame({"a": [1, 2]})).is_frame_equal(polars.DataFrame({"a": [1, 9]}))

    def test_numpy_array_equal(self):
        numpy = needs("numpy")
        assert_that(numpy.array([1, 2, 3])).is_array_equal(numpy.array([1, 2, 3]))
        with pytest.raises(AssertionError):
            assert_that(numpy.array([1, 2, 3])).is_array_equal(numpy.array([1, 2, 9]))

    def test_numpy_array_close_to(self):
        numpy = needs("numpy")
        assert_that(numpy.array([1.0, 2.0])).is_array_close_to(numpy.array([1.0, 2.0000001]))
        with pytest.raises(AssertionError):
            assert_that(numpy.array([1.0, 2.0])).is_array_close_to(numpy.array([1.0, 2.5]))

    def test_a_zero_dimensional_array_has_no_length_and_no_iteration(self):
        """The boundary of the array view, kept as a measurement rather than as a claim in a comment.

        `numpy.array(1)` carries `__array__`, `strides` and a declared `__len__` like any other array, so it
        matches the shape the overload keys on and is offered the sized and walked families.  numpy answers those
        with its own `TypeError`, which is the value's `__len__` raising rather than a value without
        one, and `length_of()` is written to let that through.  Nothing static separates the two: the
        dimension is not in the stubs.
        """
        numpy = needs("numpy")
        scalar = numpy.array(1)
        for call in (
            lambda: assert_that(scalar).is_not_empty(),
            lambda: assert_that(scalar).is_length(1),
            lambda: assert_that(scalar).contains_only(1),
            lambda: assert_that(scalar).each(lambda item: True),
            lambda: assert_that(scalar).extracting("real"),
        ):
            with pytest.raises(TypeError, match=r"unsized object|0-d array"):
                call()
        # `contains` asks `in`, which numpy answers, and `contains_only` iterates, which it refuses
        assert_that(scalar).is_array_equal(numpy.array(1))
        assert_that(scalar).is_array_close_to(numpy.array(1))
        assert_that(scalar).contains(1)

    def test_numpy_array_equal_options_passthrough(self):
        numpy = needs("numpy")
        actual = numpy.array([1, 2], dtype="int32")
        expected = numpy.array([1, 2], dtype="int64")
        assert_that(actual).is_array_equal(expected)
        with pytest.raises(AssertionError):
            assert_that(actual).is_array_equal(expected, strict=True)


class TestAnArrayIsComparedByItsShape:
    """`is_array_equal` promises shape and every element, and numpy broadcasts a scalar over both."""

    def test_a_scalar_does_not_equal_an_array(self):
        numpy = needs("numpy")
        assert_that(assert_that(numpy.array([5, 5])).check().is_array_equal(5).passed).is_false()

    def test_an_empty_array_equals_nothing_but_an_empty_one(self):
        numpy = needs("numpy")
        assert_that(assert_that(numpy.array([])).check().is_array_equal(5).passed).is_false()
        assert_that(numpy.array([])).is_array_equal(numpy.array([]))

    def test_the_message_names_both_shapes(self):
        numpy = needs("numpy")
        outcome = assert_that(numpy.array([[1, 2]])).check().is_array_equal(numpy.array([1, 2]))
        assert_that(outcome.message).contains("(1, 2)").contains("(2,)")

    def test_numpys_strict_is_about_dtype_and_not_a_way_out_of_the_shape(self):
        """`strict=False` is numpy's default and says nothing about shape, which is what is promised here."""
        numpy = needs("numpy")
        assert_that(assert_that(numpy.array([5, 5])).check().is_array_equal(5, strict=False).passed).is_false()
        assert_that(numpy.array([1, 2])).is_array_equal(numpy.array([1.0, 2.0]), strict=False)

    def test_element_types_are_not_part_of_the_promise(self):
        numpy = needs("numpy")
        assert_that(numpy.array([1, 2])).is_array_equal(numpy.array([1.0, 2.0]))
