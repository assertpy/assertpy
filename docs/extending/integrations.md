# Integrations

## Allure

When `allure-pytest` is installed, the assertpy pytest plugin automatically attaches structured failure
data to Allure reports as JSON attachments. No code changes needed.

!!! note "Optional dependency"
    ```bash
    pip install assertpy[allure]
    ```

### Attachment modes

Control what gets attached via the `assertpy_allure` ini option:

| Mode | Structured Diff | Actual/Expected |
|---|:---:|:---:|
| `diff` (default) | Yes | No |
| `full` | Yes | Yes |
| `off` | No | No |

```toml
[tool.pytest.ini_options]
assertpy_allure = "full"
```

### What gets attached

A **Structured Diff** attachment (modes `diff`, `full`) with a path-level breakdown:

```json
{
  "format": 4,
  "kind": "dict",
  "entries": [
    {
      "path": "user.settings.theme",
      "actual": "dark",
      "expected": "light",
      "steps": [
        {"kind": "key", "value": "user"},
        {"kind": "key", "value": "settings"},
        {"kind": "key", "value": "theme"}
      ]
    }
  ]
}
```

Values are native JSON (numbers, strings, booleans, nested objects and arrays), so the Allure viewer
renders them as a collapsible tree and downstream tooling can parse them.

Anything JSON cannot express degrades to a marked fallback instead of failing the attachment:

- `{"__repr__": "..."}` for arbitrary objects, datetimes, non-finite floats, and circular references
- `{"__type__": "set", "__data__": [...]}` for sets
- `{"__type__": "dict", "__data__": [[key, value], ...]}` for a mapping with any non-string key, since a
  JSON object has string keys only and rendering `1` as `"1"` drops whichever of the two came second.

Caps on oversized values:

- Strings at 4000 characters, containers at 100 items. A mapping says how many keys it dropped under
  `"__truncated__"`.
- Nesting past six levels becomes `{"__repr__": ...}`.
- Entries stop at `assertpy_diff_max_entries` (50 by default), and `"truncated"` gives the number left out.
- A polling trace that dropped samples says how many under `"dropped"`.

An **AssertionFailure** attachment (mode `full` only) with what was asked of the value, and with the
actual and expected values the assertion named:

```json
{
  "format": 3,
  "actual": {"name": "Alice", "age": 30},
  "expected": {"name": "Alice", "age": 25},
  "requirement": {
    "operation": "is_equal_to",
    "parameters": {"other": {"name": "Alice", "age": 25}},
    "negated": false
  }
}
```

The version moved from 2 to 3 to carry it, so a consumer branching on `format` needs a case for 3.

`requirement` says what `actual` and `expected` cannot: which assertion ran, with which parameters, and
whether `not_` inverted it.

- Parameters are keyed by the assertion's own parameter names, with the values it ran with. One left out
  appears with its default, so two spellings of one call group as one.
- It is absent where no operation was asked: `fail()`, a bare `error()`, and a precondition of one of the
  few members that assert nothing on their own.
- A key appears only when the assertion named that side. Every failure carries the value under test, but
  most messages open with it (`Expected <[1, 2]> to contain ...`), so attaching it again would repeat what
  the reader already has.

An assertion comparing against `None` does name it, and there `"expected": null` is present rather than
omitted. The pytest terminal section below follows the same rule.

A `soft_assertions()` block's failure attaches each failure it collected under its number:
`Structured Diff (failure 2 of 3)`. A report has room for twenty, shared by every block that fails in it,
and each block with failures left out gets one more text attachment naming them.

A **Polling Trace** attachment (modes `diff`, `full`) when an
[`eventually()`](../guides/testing.md#polling-trace) assertion times out, with per-poll samples and diffs
between consecutive distinct values:

```json
{
  "format": 2,
  "kind": "polling-trace",
  "total_polls": 9,
  "elapsed": 5.0,
  "summary": "probe recovered after 2 raising polls; value then changed 1 time",
  "samples": [
    {"t": 0.0, "outcome": "error", "detail": "ConnectionError('boot')", "repeats": 2},
    {"t": 0.5, "outcome": "fail", "value": {"status": "PENDING"}, "detail": "Expected ...", "repeats": 2}
  ],
  "deltas": [
    {"from_t": 0.5, "to_t": 1.5, "entries": [{"path": "status", "actual": "PENDING", "expected": "SHIPPED"}]}
  ]
}
```

The `format` field versions the attachment schema, so downstream tooling can branch explicitly.
Attachments without the field are the oldest repr-string form, and `2` carries typed values.

The diff attachment is at `4`. Two things arrived after `2`, and each only ever added a key:

- `3` names a side that is genuinely absent, with `"absent": "actual"` or `"absent": "expected"`. Under
  `2` both that and a field whose value really is `null` were written as a bare `null`, and nothing
  downstream could tell a missing field from a null one. The key appears only where a side is absent.
- `4` adds `steps` beside `path`. `path` is written for a person and cannot be read back: a mapping key
  goes through `str()`, so `{3: ...}` and `{"3": ...}` render alike, and a key holding a dot or a
  bracket has no grammar to parse it with. Each step carries the key, index, field name, set member or
  line number itself.

```json
{
  "path": "users[0].roles.7",
  "actual": "admin",
  "expected": "guest",
  "steps": [
    {"kind": "key", "value": "users"},
    {"kind": "index", "value": 0},
    {"kind": "key", "value": "roles"},
    {"kind": "key", "value": 7}
  ]
}
```

`kind` is one of `key`, `index`, `attr`, `item` or `line`. A step carries `side` (`actual` or
`expected`) only where a sequence's two sides have shifted apart and an index alone would name two
different elements.

`steps` is absent where there is no location to give: the whole value differing, and a containment
entry whose path is a label rather than a coordinate. A step value that JSON cannot express degrades
the same way every other value in an attachment does.

Each attachment is versioned on its own. The diff attachment is at `4` and the `AssertionFailure`
attachment at `3`, each moved for a key of its own, while the polling-trace attachment stays at `2`
because nothing about it changed.

Regardless of Allure mode, the plugin always adds human-readable sections to the failure itself, where
the terminal, a JUnit report and an IDE runner all show them:

```
--- AssertionFailure ---
  actual:   {'name': 'Alice', 'age': 30}
  expected: {'name': 'Alice', 'age': 25}
--- Structured Diff ---
diff (dict):
  age:
    - 30
    + 25
```

!!! note
    If Allure is not installed or `allure.attach()` fails, the plugin silently continues. Test results
    are never affected. An invalid mode value falls back to `diff` with a warning.

## Behave

assertpy provides ready-made parameter types for [Behave](https://behave.readthedocs.io/) step
definitions that parse and validate step parameters automatically.

!!! note "Optional dependency"
    ```bash
    pip install assertpy[behave]
    ```

Register the types once, typically in `environment.py` or a step file:

```python
from assertpy.behave_matchers import register_assertpy_types

register_assertpy_types()
```

### Available types

| Type | Pattern | Description | Example input |
|---|---|---|---|
| `PositiveInt` | `\d+` | Integer > 0 | `1`, `42`, `100` |
| `NonNegativeInt` | `\d+` | Integer >= 0 | `0`, `1`, `42` |
| `PositiveFloat` | `\d+\.?\d*` | Float > 0 | `1.5`, `42`, `0.01` |
| `NonEmptyString` | `.+?` | Stripped non-blank string | `hello`, `foo bar` |
| `BoolLike` | `\w+` | Boolean from text | `true`, `yes`, `1`, `on`, `false`, `no`, `0`, `off` |

```python
@given("a user aged {age:PositiveInt}")
def step_user_aged(context, age):
    context.age = age  # int, guaranteed > 0

@given("the feature is {enabled:BoolLike}")
def step_feature_toggle(context, enabled):
    context.enabled = enabled  # bool

@when("the user searches for {query:NonEmptyString}")
def step_search(context, query):
    context.query = query  # str, stripped, non-blank
```

Invalid values raise `ValueError` with a descriptive message (for example, `expected positive integer,
got 0`).

### Using types directly

The `ASSERTPY_TYPES` dict exposes the parsers without Behave:

```python
from assertpy.behave_matchers import ASSERTPY_TYPES

parse_int = ASSERTPY_TYPES["PositiveInt"]
value = parse_int("42")  # 42
```

## Data frames and arrays

Fluent equality assertions for [pandas](https://pandas.pydata.org/),
[polars](https://pola.rs/) and [numpy](https://numpy.org/). These types compare element-wise, so a
plain `is_equal_to()` cannot reduce them to a single truth value.

Instead it raises a clear `TypeError` pointing you to the methods below, also when the array or frame
sits nested inside a dict, dataclass, or list under comparison.

!!! note "Optional dependency"
    Each library is its own extra, so you only install what you use (a polars user does not pull in
    pandas or numpy):
    ```bash
    pip install assertpy[pandas]    # or assertpy[polars], or assertpy[numpy]
    pip install assertpy[data]      # convenience: all three at once
    ```

### DataFrames and Series

`is_frame_equal()` works on both pandas and polars `DataFrame` and `Series`. Comparison **semantics are
the library's own**: it delegates to `pandas.testing.assert_frame_equal` /
`polars.testing.assert_frame_equal` (and the `assert_series_equal` variants), so dtype strictness, row
and column order, tolerance and categoricals behave exactly as that library defines.

Any keyword options are forwarded straight through.

```python
import pandas as pd
from assertpy import assert_that

assert_that(pd.DataFrame({"a": [1, 2]})).is_frame_equal(pd.DataFrame({"a": [1, 2]}))

# forward options to the underlying assert_frame_equal:
assert_that(actual).is_frame_equal(expected, check_dtype=False)
assert_that(actual).is_frame_equal(expected, check_exact=False, rtol=1e-3)
```

```python
import polars as pl

assert_that(pl.DataFrame({"a": [1, 2]})).is_frame_equal(pl.DataFrame({"a": [1, 2]}))
```

On failure the library's own detailed diff is carried in the assertion message.

A frame or a series is also a sized collection you can walk, so the size, membership and iteration
assertions apply to it as they do to a list. Each asks the library's own `len()`, `in` and iteration:
a pandas `DataFrame` walks its column labels, and `in` on a pandas `Series` looks at the index labels,
not the values.

```python
frame = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

assert_that(frame).is_length(2).contains("a", "b")
assert_that(frame["a"]).is_not_empty().contains(0)   # 0 is an index label of the series
```

### numpy arrays

Two array assertions, both accepting any array-like numpy can coerce:

- `is_array_equal()` is exact, through `numpy.testing.assert_array_equal`. The shapes are compared
  first, so a scalar is never broadcast over an array, and a NaN equals a NaN in the same position, as
  numpy has it. Options go through to numpy: `strict=True` compares the dtypes too.
- `is_array_close_to()` is float-tolerant, through `numpy.testing.assert_allclose`, for comparing
  computed arrays.
    - `rtol` and `atol` default to `1e-05` and `1e-08`, the defaults of `numpy.isclose`, where
      `assert_allclose` itself defaults to `1e-07` and `0`.
    - `equal_nan` defaults to `False`, where numpy's own default is `True`, so a NaN fails unless you
      pass `equal_nan=True`.
    - The shapes are numpy's to compare, so a scalar broadcasts over an array unless you pass
      `strict=True` (numpy 2).

```python
import numpy as np
from assertpy import assert_that

assert_that(np.array([1, 2, 3])).is_array_equal(np.array([1, 2, 3]))
assert_that(np.array([1, 2, 3])).is_array_equal([1, 2, 3])
assert_that(np.array([1.0, 2.0])).is_array_close_to(np.array([1.0, 2.0000001]))
computed = np.array([0.1, 0.2]) * 3
assert_that(computed).is_array_close_to(np.array([0.3, 0.6]))
assert_that(computed).is_array_close_to(np.array([0.3, 0.6]), rtol=1e-3, atol=1e-6)
assert_that(np.array([np.nan])).is_array_close_to(np.array([np.nan]), equal_nan=True)
```

<!-- docs-guard: raises -->
```python
assert_that(np.array([2, 2])).is_array_equal(2)
# AssertionFailure: Expected an array of shape <()>, but was of shape <(2,)>.
```

An array is a sized collection too, so `is_length()`, `contains()` and the rest apply to it. A
zero-dimensional array, `np.array(5)`, is still an array to both assertions and to a type checker, but
numpy refuses it a length: `is_length()` on one raises numpy's own `TypeError`.

### numpy scalars

A numpy scalar, such as `np.int64(5)` or `np.float32(0.1)`, is a number to every assertion. It is
compared by the exact value it holds, against a Python number, a `Decimal` or a `Fraction`, on its own,
inside a list or a tuple, in a set or as a dict key, and past the range a float can hold:

```python
from decimal import Decimal

import numpy as np
from assertpy import assert_that

assert_that(np.int64(5)).is_equal_to(Decimal(5))
assert_that(Decimal("4.5")).is_less_than(np.int64(5))
assert_that({np.int64(5): "a"}).is_equal_to({Decimal(5): "a"})
assert_that(np.float32(1)).is_less_than(10**400)
assert_that(np.uint8(200)).is_greater_than(100).is_close_to(200, 0.5)
```

Python raises on those pairs: a `Decimal` refuses a numpy integer at `==` and `<`, and on numpy 2 a
numpy float overflows converting an int past its range. The library answers them by exact value.

A numpy float NaN is a NaN, as a `float` one is. It is equal to nothing, not even itself, and it has no
place in an order:

```python
assert_that(np.float32("nan")).is_not_equal_to(np.float32("nan"))
```

<!-- docs-guard: raises -->
```python
assert_that([1.0, np.float32("nan"), 2.0]).is_sorted()
# AssertionFailure: Expected <[1.0, np.float32(nan), 2.0]> to be sorted, but subset <1.0, np.float32(nan)> at index 0 is not.
```

numpy compares a scalar with a list element by element and answers an array, so `np.int64(5) == [5]`
is `array([ True])`. Wherever the library compares the pair itself, a scalar against a list or a tuple is
unequal and unordered, as a Python number is:

```python
assert_that(np.int64(5)).is_not_equal_to([5])
assert_that(np.int64(5)).is_not_in([5], (5, 6))
```

<!-- docs-guard: raises -->
```python
assert_that(np.int64(6)).is_greater_than([5])
# TypeError: given other arg must be a number, but was <[5]> (list)
```

Inside a container's own `==` the answer stays numpy's. Python finds `[np.int64(5)] == [[5]]` true, so
`assert_that([np.int64(5)]).is_equal_to([[5]])` passes.

### Integer arguments

Every integer argument takes a numpy integer, an `IntEnum` member or any other `int`, and refuses a bool or
anything else by name. That covers:

- the index of `element()` and `has_byte_at()`
- the lengths and sizes of `is_length()`, `is_length_between()` and the `has_size_*` family
- the divisor of `is_divisible_by()`
- `match.is_length()`, `match.has_length()` and `match.is_divisible_by()`.

They are typed `SupportsIndex`, so a checker accepts any value with `__index__`. At run time only an `int` or
a numpy integer passes.

```python
assert_that(["a", "b"]).is_length(np.int64(2)).element(np.int64(1)).is_equal_to("b")
assert_that(12).is_divisible_by(np.int64(4))
```

<!-- docs-guard: raises -->
```python
assert_that(["a", "b"]).element(True)
# TypeError: given index arg must be an integer, but was <True> (bool)
```

### numpy durations

`np.timedelta64` is a duration, although numpy registers it as an integer. Closeness measures a
duration only against another duration, in any unit, in every spelling:

```python
assert_that(np.timedelta64(5, "s")).satisfies(match.close_to(np.timedelta64(5500, "ms"), np.timedelta64(1, "s")))
assert_that(np.timedelta64(90, "s")).is_greater_than(np.timedelta64(1, "m"))
```

`is_close_to()` and `tolerance=` measure the same pairs at run time. Their parameters are typed for
numbers, though, and the numpy stubs do not make a duration one, so ty and Pyright refuse the first call
below and every checker refuses the second. `match.close_to()` takes any expected value and tolerance,
which makes it the spelling that type-checks.

<!-- docs-guard: untyped -->
```python
assert_that(np.timedelta64(5, "s")).is_close_to(np.timedelta64(5500, "ms"), np.timedelta64(1, "s"))
assert_that({"wait": np.timedelta64(5, "h")}).is_equal_to(
    {"wait": np.timedelta64(6, "h")}, tolerance=np.timedelta64(1, "D")
)
```

A duration against a number has no distance:

- `is_close_to()` and `is_not_close_to()` refuse the pair.
- `match.close_to()` matches no such pair.
- Under `tolerance=`, a leaf of the other kind is compared by `==` alone.
- A negative duration tolerance is refused like a negative number, and a `NaT` is close to nothing.

<!-- docs-guard: raises -->
<!-- docs-guard: type-error -->
```python
assert_that(1).is_close_to(1, np.timedelta64(1, "s"))
# TypeError: given tolerance arg must be a number, to match val, but was <np.timedelta64(1,'s')> (timedelta64)
```

A type checker refuses that call as well.

- Durations order as numbers do, through `is_greater_than()`, `is_between()` and the rest.
- A `np.datetime64` value is not taken by `is_close_to()`, which measures a `datetime` under a
  `timedelta`.
- Comparing a duration with a bare number by `==` is numpy's own equality, which numpy 2 deprecates with
  a warning.

### Type checking data values

| Value | View a type checker offers |
|---|---|
| a pandas or polars frame or series | `is_frame_equal`, `is_array_equal`, plus size, membership and iteration |
| a numpy array, zero-dimensional or not | `is_array_equal`, `is_array_close_to`, plus the same three |
| `np.float64` | the `float` view, since it subclasses `float` |
| any other numpy scalar | the generic view, whose ordering, closeness and `is_zero` take a number |

On a numpy integer, `float32` or `bool_` value, `is_even()`, `is_positive()`, `is_nan()` and
`is_array_equal()` run, but the generic view does not declare them, so a checker refuses them. Convert
the value first, with `int()` or `float()`, to reach the numeric view:

<!-- docs-guard: type-error -->
```python
assert_that(np.int64(4)).is_even()
```

```python
assert_that(int(np.int64(4))).is_even()
```

A pandas `Series` matches every shape through the catch-all `__getattr__` in `pandas-stubs`, so the
checkers resolve it differently: mypy offers the frame view, ty another, and Pyright the untyped
builder. `is_frame_equal()` on a `Series` runs under all three, and only ty says it is not there.

!!! note "Delegated semantics"
    The frame and array assertions add only the fluent entry point and route failures through the
    standard assertpy error model (so soft assertions, `described_as`, and warn mode all apply). Their
    comparison is always the source library's, never a reimplementation. A numpy scalar outside them
    is compared by the library's own rules, as described above.
