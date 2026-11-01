# Data frame & array assertions

Equality assertions for pandas and polars data frames and series and for numpy arrays, each handed to
the owning library's testing utilities. They need the ``data`` extra, or the ``pandas``, ``polars`` or
``numpy`` one.

| Assertion | Delegates to | What this layer adds |
|---|---|---|
| `is_frame_equal()` | `assert_frame_equal` / `assert_series_equal` of pandas or polars | nothing: every option goes through |
| `is_array_equal()` | `numpy.testing.assert_array_equal` | the shapes compared first, so a scalar is never broadcast |
| `is_array_close_to()` | `numpy.testing.assert_allclose` | `rtol=1e-05` and `atol=1e-08` by default, those of `numpy.isclose`, and `equal_nan=False`, where `assert_allclose` defaults to `1e-07`, `0` and `True` |

A plain `is_equal_to()` on a frame or an array raises a `TypeError` naming the method to use, also when
it sits nested in a dict, a dataclass or a list. A frame, a series and an array are sized collections
too, so the size, membership and iteration assertions apply to them through the library's own `len()`,
`in` and iteration.

How a numpy scalar, a numpy duration and a numpy integer argument are compared, and which view a type
checker offers on each value, is described in
[Data frames and arrays](../extending/integrations.md#data-frames-and-arrays).

::: assertpy.dataframe.DataFrameMixin
