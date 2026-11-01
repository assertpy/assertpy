# Upgrading from assertpy 1.x

`assertpy` 2.x is assertpy 1.1 rewritten: the same name, the same `assert_that(...)` API, now typed and
extended. It is a major release, so some answers, the failure class and many messages change.

!!! success "TL;DR"
    - On Python 3.10+, upgrade and run your tests. Your imports stay as they are.
    - To stay on 1.x, pin `assertpy<2`. Python 3.9 and older get 1.1 anyway.
    - Uninstall `types-assertpy`: its 1.1 stubs hide the 2.x types.
    - What can change, most serious first: [answers](#where-results-differ), [extensions](#extensions),
      [the failure class](#the-failure-class), [message text](#message-text).

## Before you start

- **Python 3.10 to 3.15.** On an older interpreter pip keeps installing 1.1.
- **No runtime dependencies** on 3.11+. On 3.10 one backport, `typing_extensions`. Extras stay opt-in:
  `[json]`, `[inline]`, `[data]`, `[numpy]`, `[pandas]`, `[polars]`, `[allure]`, `[behave]`.
- **How you pin decides when you get 2.x:**

| Your dependency | You get 2.x |
|---|---|
| `assertpy`, `assertpy>=1.1` | on the next fresh install |
| the same, through a lock file | the next time the lock upgrades `assertpy` |
| `assertpy==1.1`, `assertpy~=1.1`, Poetry's `^1.1` | never: you stay on 1.x |

## Remove the 1.1 stubs

`types-assertpy` describes 1.1, and a type checker reads stubs before the types a package ships. Take it
out of your dependencies and your lock file, then:

```bash
pip uninstall types-assertpy
```

## Where results differ

Some answers 1.1 gave were wrong. A test can change its outcome in either direction:

| Call | assertpy 1.1 | assertpy 2.x |
|---|---|---|
| `is_close_to()` with a `bool` value, expected value or tolerance | measured `True` as `1` | raises `TypeError` |
| `is_close_to()` with a NaN tolerance | passed | raises `ValueError` |
| `is_close_to()` and `is_not_close_to()` on datetimes with a negative `timedelta` tolerance | found nothing close, so `is_not_close_to()` passed for any two | raises `ValueError`, as a negative number does |
| a NaN as the value or the operand of `is_less_than()`, `is_greater_than()`, their `_or_equal_to` forms and `is_close_to()`, or as the value of `is_between()`, `is_positive()` and `is_negative()` | passed | fails |
| an infinity against a finite number under an infinite tolerance | passed | fails |
| `is_in()` and `is_not_in()` when the items hold the very NaN object under test | `is_in()` failed and `is_not_in()` passed | the reverse, as `in` answers |
| `is_equal_to()` on a type whose `__ne__` is not the negation of its `__eq__` | decided by `!=` | decided by `==` |
| `contains()` and `does_not_contain()` on a class iterated only through `__getitem__` | searched it | raise `TypeError` |
| `extracting()` with a `filter` or `sort` of a type it cannot use, such as a number | ignored it | raises `TypeError` |
| `add_extension()` with a name already in use, by a built-in or by another function | replaced it | raises `ValueError` unless `override=True` |

## Extensions

<!-- docs-guard: skip -->
```python
def is_equal_to(self, other):
    ...

add_extension(is_equal_to)                 # 1.1: replaced the built-in. 2.x: ValueError
add_extension(is_equal_to, override=True)  # 2.x: replaces it on purpose
```

- 2.x has many more assertion names than 1.1, so a name that was free may now be taken. A module that
  registers it at import then fails to import.
- Names a polling chain uses (`within`, `every`) and names starting with `_`, `cr_` or `gi_` are refused
  even under `override=True`.
- A builder made before `add_extension()` sees the extension (1.1 raised `AttributeError`). A builder kept
  past `remove_extension()` loses it (1.1 kept it).
- Private helpers of 1.1, such as `_check_dict_like()`, are gone.

See [Custom Assertions](../extending/custom-assertions.md).

## The failure class

Failures raise `AssertionFailure`, a subclass of `AssertionError`:

- `except AssertionError` and `pytest.raises(AssertionError)` keep working.
- `type(error) is AssertionError` no longer holds.

## Message text

Messages are reworded, and not only at the end. A test that compares a message, or matches part of one
with `match=` or `in`, may need updating:

| Failure | assertpy 1.1 | assertpy 2.x |
|---|---|---|
| `assert_that(False).is_true()` | `Expected <True>, but was not.` | `Expected <False> to be <True>, but was not.` |
| `contains_only(1, 4)` on `[1, 2, 3]` | `... but did contain <2, 3>.` | `... but did contain <2, 3> and did not contain <4>.` |
| `does_not_contain_duplicates()` on `[1, 2, 3, 3]` | `... but did.` | `... but <3> was repeated.` |
| `contains("a", "b", "z")` on a dict | `... but did not contain keys <z>.` | `... but did not contain key <z>.` |
| `is_equal_to()` on dicts | `Expected <{.., 'b': 2}> ...` | `Expected <{.., 'b': 2, ..}> ...` |
| a `datetime` in `is_before()`, `is_after()`, `is_between()`, `is_close_to()` and the other date comparisons | `<2026-10-28 21:22:29>`, without microseconds | `<2026-10-28 21:22:29.556697>` |
| `extracting("foo")` on items without it | `val does not have property ...` | `item does not have property ... (at index 0, item is <Person>)` |
| a soft block's failure | `1. Expected ...` | `1. Expected ...  [test_orders.py:14]` |
| a usage error, such as an argument of the wrong type (same exception class) | `val is not iterable` | `val must be iterable, but was <123> (int)` |

Many failures also add lines under the message: a diff, the distance to a bound, a reason. Under pytest
the diff goes to a report section instead. Rather than matching text, read `failure.actual`,
`failure.expected` and `failure.diff`.

## Coming from assertpy2

This library was published as `assertpy2` before it took over the `assertpy` name.

```diff
- assertpy2[json]
+ assertpy[json]
```

```diff
- from assertpy2 import assert_that
+ from assertpy import assert_that
```

- The last `assertpy2` release installs `assertpy` and hands out the same objects, so old imports keep
  working meanwhile.
- Flags, settings and environment variables drop the `2`: `--assertpy-snapshot-update`, `assertpy_diff`,
  `ASSERTPY_SNAPSHOT_CI`. Old names work through 2.x with a `FutureWarning` and go in 3.0. An old name is
  read only where the new one is blank.
- Under warnings-as-errors that warning stops the run. Rename, or filter it:

    ```toml
    [tool.pytest.ini_options]
    filterwarnings = ["error", "ignore:.*is the assertpy2 name of:FutureWarning"]
    ```

- The dangling marker is `# assertpy: allow-dangling`. `# assertpy2: allow-dangling` is still read,
  without a warning, until 3.0.
- No synonym for two names: the loggers are `assertpy` and `assertpy.passes`, and the plugin is
  `assertpy`, so `-p no:assertpy2` no longer turns it off.

## What improves automatically

No test code changes needed.

**A diff in every failure.** Nested values report the path that differs:

<!-- docs-guard: raises -->
```python
assert_that({"user": {"name": "Alice", "role": "superadmin"}}).is_equal_to(
    {"user": {"name": "Alice", "role": "admin"}}
)
# Expected <{'user': {.., 'role': 'superadmin'}}> to be equal to <{'user': {.., 'role': 'admin'}}>, but was not.
# diff (dict):
#   user.role:
#     - 'superadmin'
#     + 'admin'
```

Under pytest the diff goes to a report section, which the terminal, JUnit reports and IDE runners show.
`assertpy_diff = off` turns it off.

**Failures as data.** The failure carries what it compared:

```python
from assertpy import AssertionFailure

try:
    assert_that({"user": {"role": "superadmin"}}).is_equal_to({"user": {"role": "admin"}})
except AssertionFailure as failure:
    assert failure.diff is not None
    assert failure.diff.entries[0].path == "user.role"
```

**Failures that say why.** Where one fact explains a failure, a line says it:

<!-- docs-guard: raises -->
```python
assert_that({"id": "7"}).is_equal_to({"id": 7})
# Expected <{'id': '7'}> to be equal to <{'id': 7}>, but was not.
# every difference here is the same text against a value of another type
```

See [Some failures say why](../guides/errors.md#some-failures-say-why-not-only-what).

**Typed chains.** The editor offers only the assertions that fit the value, and a type checker flags the
rest before the tests run:

<!-- docs-guard: type-error -->
```python
assert_that("foo").is_positive()  # type error: is_positive is not a string assertion
```

See [Type Safety](../concepts/type-safety.md).

**The IDE comparison window.**

- A failed `is_equal_to()` or `has_<name>()` gets PyCharm's "Click to see difference" link.
- The window shows both values whole, side by side.

See [The comparison window of an IDE](../guides/errors.md#the-comparison-window-of-an-ide).

**Safe soft assertions.**

- Their state is per thread and per `asyncio.Task`.
- So they work under `pytest-xdist` and `asyncio`. Those of 1.1 were not thread-safe.

## What you can now adopt

- [Composable matchers](../guides/matchers.md), in assertions and inside plain `==`
- [Structural matching](../guides/matchers.md#structural-matching) for API responses
- [Typed narrowing](../concepts/type-safety.md#typed-narrowing-with-value) with `.value`, and [contract testing](../concepts/type-safety.md#contract-narrowing-with-assert_conforms)
- [Exception cause chains and groups](../guides/errors.md#expected-exceptions)
- The [collection pipeline](../guides/fluent.md#collection-pipeline) and [universal negation](../guides/fluent.md#universal-negation)
- [Async and blocking polling](../guides/testing.md#async-assertions)
- [JSON Path / Schema](../guides/data.md), [regex groups](../guides/data.md#regex-group-extraction), [bytes](../guides/assertions.md#bytes--bytearray)

What the compatibility promise covers: [stability](../concepts/stability.md).
