"""Optional fluent assertions for data-science containers (pandas / polars / numpy).

This is an *integration* layer in the same spirit as the Allure and Behave adapters: each library is its
own optional extra (``pip install assertpy[pandas]`` / ``[polars]`` / ``[numpy]``, or ``[data]`` for all
three), imported lazily by name, so the core stays free of runtime dependencies.  Comparison
**semantics** are delegated to each library's own testing utilities (``assert_frame_equal`` /
``assert_series_equal`` / ``assert_array_equal`` / ``assert_allclose``), so dtype, tolerance and NaN
handling are the library's, with the exceptions this layer adds: ``is_array_equal`` compares the shapes
before numpy does, and ``is_array_close_to`` defaults its tolerances to those of ``numpy.isclose`` and
takes no ``NaN`` as equal unless asked.  Otherwise this layer adds the fluent entry point and routes
failures through the standard assertpy error model.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ._engine._mixin_base import _MixinBase
from ._engine._require import refuse

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True

_FRAME_ROOTS = ("pandas", "polars")


def _ensure_module(name: str) -> Any:
    """Import optional library *name* by string, or raise a clear ImportError pointing at its extra."""
    try:
        return importlib.import_module(name)
    except ImportError:
        raise ImportError(
            f"{name} is required for these assertions. Install it with: pip install assertpy[{name}]"
        ) from None


def _load(root: str) -> tuple[Any, Any]:
    """Return ``(library, library.testing)`` for *root* (``pandas``/``polars``/``numpy``)."""
    library = _ensure_module(root)
    return library, importlib.import_module(f"{root}.testing")


class DataFrameMixin(_MixinBase):
    """Fluent assertions for pandas/polars frames and numpy arrays (optional ``[data]`` extra).

    Each hands the comparison to the owning library's testing utilities and reports a failure through the
    standard error model, so soft assertions, ``check()``, ``described_as()`` and warn mode all apply.
    """

    def is_frame_equal(self, expected: object, **options: Any) -> Self:
        """Asserts that a pandas/polars ``DataFrame`` or ``Series`` equals *expected*.

        Delegates to the owning library's own ``assert_frame_equal`` / ``assert_series_equal``, so all
        comparison semantics (dtype strictness, row/column order, tolerance, categoricals, ...) are the
        library's.  Any keyword options are passed straight through.  *expected* has to be of the same
        library and kind: a polars frame against a pandas one, or a ``DataFrame`` against a ``Series``, fails
        with the library's own message about the type.

        Args:
            expected: the expected frame/series (same library and kind as val)
            **options: keyword options forwarded to the library's ``assert_frame_equal`` /
                ``assert_series_equal`` (e.g. ``check_dtype=False``, ``check_exact=False``, ``rtol=1e-3``)

        Examples:
            Usage:

                import pandas as pd

                assert_that(pd.DataFrame({"a": [1, 2]})).is_frame_equal(pd.DataFrame({"a": [1, 2]}))
                assert_that(actual).is_frame_equal(expected, check_dtype=False)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the frames/series are not equal (carrying the library's own diff message)
            TypeError: if val is not a pandas or polars ``DataFrame``/``Series`` (an ``Index`` is refused too)
            ImportError: if the owning library is not installed
        """
        actual = self.val
        # walk the MRO so a user subclass resolves to the owning library through its base
        root = next(
            (
                base.__module__.split(".", 1)[0]
                for base in type(actual).__mro__
                if base.__module__.split(".", 1)[0] in _FRAME_ROOTS
            ),
            type(actual).__module__.split(".", 1)[0],
        )
        if root not in _FRAME_ROOTS:
            refuse(actual, "a pandas or polars DataFrame/Series")
        library, testing = _load(root)
        class_name = type(actual).__name__
        # isinstance handles real subclasses, the name check handles duck-typed frames a test may inject
        if isinstance(actual, library.Series) or class_name == "Series":
            assert_equal, label = testing.assert_series_equal, "Series"
        elif isinstance(actual, library.DataFrame) or class_name == "DataFrame":
            assert_equal, label = testing.assert_frame_equal, "DataFrame"
        else:
            # a pandas/polars object that is neither a DataFrame nor a Series (Index, Categorical, ...)
            refuse(actual, "a pandas or polars DataFrame/Series")
        try:
            assert_equal(actual, expected, **options)
        except AssertionError as exc:
            return self.error(
                f"Expected the {label} to equal the expected one, but they differ:\n{exc}",
                suppress_context=True,
                expected=expected,
            )
        return self

    def is_array_equal(self, expected: object, **options: Any) -> Self:
        """Asserts that val equals *expected* element-wise, via numpy's ``assert_array_equal``.

        Works on any array-likes numpy can coerce (``ndarray``, nested lists, ...).  The shapes are compared
        before numpy is asked, so a scalar is never broadcast over an array.  Then every element must match
        exactly, a ``NaN`` equal to a ``NaN`` in the same position, as numpy has it.

        Args:
            expected: the expected array-like
            **options: keyword options forwarded to numpy's ``assert_array_equal``
                (e.g. ``strict=True``, which compares the dtypes too, or ``err_msg="..."``)

        Examples:
            Usage:

                import numpy as np

                assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]))
                assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]), strict=True)
                assert_that(np.array([1, 2, 3])).is_array_equal([1, 2, 3])

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the shapes differ, or the arrays are not equal (carrying numpy's own diff message)
            ImportError: if numpy is not installed
        """
        numpy, testing = _load("numpy")
        # shape first: left to numpy a scalar broadcasts, so an empty array "equals" 5, against the shape
        # the docstring promises.  numpy's own `strict` is about dtype and is passed through untouched
        actual_shape, expected_shape = numpy.shape(self.val), numpy.shape(expected)
        if actual_shape != expected_shape:
            return self.error(
                f"Expected an array of shape <{expected_shape}>, but was of shape <{actual_shape}>.",
                expected=expected,
            )
        try:
            testing.assert_array_equal(self.val, expected, **options)
        except AssertionError as exc:
            return self.error(
                f"Expected the arrays to be equal, but they differ:\n{exc}", suppress_context=True, expected=expected
            )
        return self

    def is_array_close_to(
        self, expected: object, *, rtol: float = 1e-05, atol: float = 1e-08, equal_nan: bool = False, **options: Any
    ) -> Self:
        """Asserts that val is element-wise close to *expected*, via numpy's ``assert_allclose``.

        The float-tolerant counterpart to [`is_array_equal()`][assertpy.dataframe.DataFrameMixin.is_array_equal],
        for comparing computed arrays.  The shapes are numpy's to compare, so a scalar broadcasts over an
        array unless ``strict=True`` is passed, which numpy 2 accepts.  ``equal_nan`` defaults to ``False``,
        where numpy's own default is ``True``, so a ``NaN`` fails unless asked for.

        Args:
            expected: the expected array-like
            rtol: relative tolerance (``1e-05``, as ``numpy.isclose`` has it, where ``assert_allclose`` has ``1e-07``)
            atol: absolute tolerance (``1e-08``, as ``numpy.isclose`` has it, where ``assert_allclose`` has ``0``)
            equal_nan: whether ``NaN`` in the same position compares equal (``False`` here, ``True`` in numpy)
            **options: further keyword options forwarded to numpy's ``assert_allclose``
                (e.g. ``err_msg="..."``, ``strict=True``)

        Examples:
            Usage:

                import numpy as np

                assert_that(np.array([1.0, 2.0])).is_array_close_to(np.array([1.0, 2.0000001]))
                assert_that(np.array([np.nan])).is_array_close_to(np.array([np.nan]), equal_nan=True)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the arrays are not close (carrying numpy's own diff message)
            ImportError: if numpy is not installed
        """
        _, testing = _load("numpy")
        try:
            testing.assert_allclose(self.val, expected, rtol=rtol, atol=atol, equal_nan=equal_nan, **options)
        except AssertionError as exc:
            return self.error(
                f"Expected the arrays to be close, but they differ:\n{exc}", suppress_context=True, expected=expected
            )
        return self
