# Getting Started

## Install

```bash
pip install assertpy
```

Optional extras:

- `assertpy[json]` - JSONPath, JSON Schema, and OpenAPI contracts
- `assertpy[inline]` - inline snapshots (`matches_inline()`)
- `assertpy[data]` - pandas, polars and numpy, or each under its own name
- `assertpy[allure]` - Allure reporting
- `assertpy[behave]` - Behave step matchers

!!! tip "Coming from assertpy 1.x?"
    2.x continues assertpy 1.1 on Python 3.10+. See [Upgrading from assertpy 1.x](migration.md) for what
    changes and what you gain.

## Your first assertion

Wrap a value in `assert_that()` and chain assertions that read like a sentence:

```python
from assertpy import assert_that

assert_that("foobar").is_length(6).starts_with("foo").ends_with("bar")
assert_that([1, 2, 3]).contains(1).does_not_contain(9).is_subset_of([1, 2, 3, 4])
```

Because every assertion is statically typed, your editor only suggests methods valid for the value's
type, and a type checker flags misuse before the test runs. See [Type Safety](../concepts/type-safety.md) for how the
overloads work.

Assertions also **return the value they checked**, statically narrowed, so you keep using it, correctly
typed, with no `cast`:

```python
# name is typed as str, the value the chain checked
name = assert_that("Alice").is_instance_of(str).is_not_empty().value
```

## When an assertion fails

A failing assertion raises an `AssertionFailure` with a precise message. It subclasses `AssertionError`,
so `pytest.raises(AssertionError)` and any existing `except AssertionError` keep catching it:

<!-- docs-guard: raises -->
```python
assert_that(5).is_greater_than(10)
# assertpy.AssertionFailure: Expected <5> to be greater than <10>, but was not.
```

For dicts, dataclasses, and other structures, the pytest plugin renders a path-level diff that points
straight at the differing field instead of dumping the whole value:

<!-- docs-guard: skip -->
```python
assert_that(actual).is_equal_to(expected)
```

![Colored dict diff: user.role shown with its path, removal in red and addition in green](../assets/diff-equal.svg)

The same path-level diff backs `matches_structure()`, `satisfies()`, and `each()`. See
[Errors & Reporting](../guides/errors.md) for the full diff format and configuration.

## Collect multiple failures

Use soft assertions to report every failure at once instead of stopping at the first:

<!-- docs-guard: raises -->
```python
from assertpy import assert_that, soft_assertions

with soft_assertions():
    assert_that("foo").is_length(3)
    assert_that("foo").starts_with("x")   # collected
    assert_that("foo").ends_with("z")     # collected
```

## Next steps

- [Matchers](../guides/matchers.md) for composable, reusable conditions.
- [Fluent API](../guides/fluent.md) for chaining, negation, and the collection pipeline.
- Browse the assertion reference in the navigation for every type-specific assertion.
