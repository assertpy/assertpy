# Upgrading from assertpy 1.x

`assertpy` 2.x continues assertpy 1.1 under the same name and the same `assert_that(...)` API, now typed
and extended. It is a major release: a few answers, the failure class and many failure messages change.
Read this page before you upgrade, or stay on 1.x.

!!! success "TL;DR"
    - On Python 3.10+, upgrade and run your tests. Your imports stay as they are.
    - To stay on 1.x, pin `assertpy<2`. Python 3.9 and older keep getting 1.1 without a pin.
    - Uninstall `types-assertpy`. 2.x ships its own types, and the 1.1 stubs would hide them.
    - What can change, from most to least serious: [answers](#where-results-differ),
      [extensions](#extensions), [the failure class](#the-failure-class), [message text](#message-text).

## Before you start

- **Python 3.10+ is required**, 3.10 through 3.15. On an older interpreter pip keeps installing 1.1.
- **No runtime dependencies on Python 3.11+.** On 3.10 a single backport (`typing_extensions`) is pulled
  in. The extras (`[json]`, `[inline]`, `[data]` or one of `[numpy]`, `[pandas]`, `[polars]`, `[allure]`,
  `[behave]`) stay opt-in.
- **Check how you depend on it.** A bare `assertpy` or `assertpy>=1.1` takes 2.x on the next fresh
  install, and a lock file takes it the next time it upgrades `assertpy`. `assertpy==1.1`,
  `assertpy~=1.1` and Poetry's `^1.1` hold you on 1.x.

## Remove the 1.1 stubs

`types-assertpy`, the stub package from typeshed, describes 1.1. A type checker reads a stub package
before the types a package ships, so with it installed your checker sees the 1.1 API and none of the 2.x
one. Take it out of your dependencies and your lock file, then uninstall it:

```bash
pip uninstall types-assertpy
```

## Where results differ

A few answers 1.1 gave were wrong, and 2.x corrects them. A test can change its outcome in either
direction, and each row is measured against 1.1:

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

- **A name already in use is refused.** 1.1 let `add_extension()` replace a built-in or an earlier
  extension silently. 2.x raises `ValueError`, so a module registering such an extension at import fails
  to import. 2.x has many more assertion names than 1.1, so an extension name that was free may now be
  taken. Rename the extension, or pass `override=True` to replace the built-in on purpose.
- **A name a polling chain uses**, such as `within` or `every`, or one starting with `_`, `cr_` or
  `gi_`, is refused even under `override=True`.
- **Registration reaches builders already made.** A builder created before `add_extension()` sees the
  extension, where 1.1 raised `AttributeError`. A builder kept past `remove_extension()` loses it, where
  1.1 kept it.
- **Private helpers of 1.1 are gone.** An extension that called one, such as `_check_dict_like()`, needs
  a check of its own.

See [Custom Assertions](../extending/custom-assertions.md) for the rules in full.

## The failure class

A failing assertion raises `AssertionFailure`, a subclass of `AssertionError` that carries the compared
values and a structured diff.

- `except AssertionError` and `pytest.raises(AssertionError)` keep working.
- A check of the exact type, `type(error) is AssertionError`, no longer holds.

## Message text

Failure messages changed in wording, and not only at the end. A test that compares a whole message, or
matches a part of one with `match=` or `in`, may need updating:

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

- **Usage errors**, such as an argument of the wrong type, keep their exception class and read
  `<subject> must be <expectation>, but was <value> (<type>)`: `val must be iterable, but was <123> (int)`
  where 1.1 said `val is not iterable`.
- **Many failures add lines under the message**: a diff, the distance to a bound, a reason. Under pytest
  the diff goes to a report section instead.

Rather than matching text, assert on the data the failure carries: `AssertionFailure.actual`,
`.expected` and `.diff`.

## Coming from assertpy2

This library was published as `assertpy2` before it took over the `assertpy` name. Code written for
`assertpy2` runs on `assertpy` 2.x once its names are updated:

- **Package and imports.** Depend on `assertpy` and write `from assertpy import ...`. The last `assertpy2`
  release installs `assertpy` and hands you the same objects under the old name.
- **Flags, settings and environment variables** lose the `2`: `--assertpy-snapshot-update`,
  `assertpy_diff`, `ASSERTPY_SNAPSHOT_CI`. The old names keep working through 2.x with a `FutureWarning`
  and go in 3.0. The old name is read only where the new one is blank.
- **Under warnings-as-errors** that warning stops the run. Rename the setting, or filter it:
  `ignore:.*is the assertpy2 name of:FutureWarning`.
- **The dangling marker** is `# assertpy: allow-dangling`. The old `# assertpy2: allow-dangling` is read
  the same way through 2.x, without a warning, and goes in 3.0.
- **Two names have no synonym.** The loggers are `assertpy` and `assertpy.passes`, so a logging config
  naming `assertpy2` stops matching. The pytest plugin is `assertpy`, so `-p no:assertpy2` no longer
  turns it off.

## What improves automatically

You get these the moment you upgrade, without touching any test code:

- **Thread-safe and async-safe soft assertions.** State is isolated per thread and per `asyncio.Task`
  via `contextvars`, so soft assertions are safe under `pytest-xdist` and `asyncio`. The soft assertions
  of 1.1 were not thread-safe.
- **Structured failures and rich diffs.** Failures carry `.actual` / `.expected` / `.diff`, and the diff
  is rendered into the message itself, so it shows in `unittest`, plain scripts and CI logs. Under pytest
  the auto-registered plugin attaches it to the failure as a section instead, which the terminal, JUnit
  reports and IDE runners all show, recursive for lists, dicts, dataclasses, namedtuples, attrs classes
  and Pydantic models. Set `assertpy_diff` to `off` to turn that section off.
- **The comparison window of an IDE.** PyCharm's runner gave the failures of 1.1 its "Click to see
  difference" link by reading their message. A failed `is_equal_to()` or `has_<name>()` reaches the same
  runner through the hook pytest calls for a failed `assert left == right`, with the two values it
  compared. See [The comparison window of an IDE](../guides/errors.md#the-comparison-window-of-an-ide).
- **Failures that say why.** Where one fact explains a failure, a line under the message says it: an id
  the payload holds as text, a NaN, two instances compared by identity. See
  [Some failures say why](../guides/errors.md#some-failures-say-why-not-only-what).
- **Static typing.** With `py.typed` and `@overload` protocols your editor filters autocomplete by the
  value's type, and a type checker flags misuse before the tests run. See
  [Type Safety](../concepts/type-safety.md).

## What you can now adopt

New capabilities 1.1 never had, ready whenever you want them:

- [Composable matchers](../guides/matchers.md), reusable across assertions and the plain `==` form.
- [Structural matching](../guides/matchers.md#structural-matching) for API-response shapes.
- [Typed narrowing](../concepts/type-safety.md#typed-narrowing-with-value) (`.value`) and [contract testing](../concepts/type-safety.md#contract-narrowing-with-assert_conforms) for typed API responses.
- [Exception cause chains and groups](../guides/errors.md#expected-exceptions).
- The [collection pipeline](../guides/fluent.md#collection-pipeline) and [universal negation](../guides/fluent.md#universal-negation).
- [Async and blocking polling](../guides/testing.md#async-assertions) for eventual consistency.
- [JSON Path / Schema](../guides/data.md), [regex group extraction](../guides/data.md#regex-group-extraction), and [bytes assertions](../guides/assertions.md#bytes--bytearray).

See the [comparison](comparison.md) for how the two read side by side, and [stability](../concepts/stability.md)
for what is covered by a compatibility promise and what is not.
