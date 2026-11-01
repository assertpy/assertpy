# Extending

Add your own assertions to `assertpy` with `add_extension()`.

## A custom assertion

<!-- docs-guard: untyped -->

```python
from assertpy import add_extension, assert_that

def is_5(self):
    if self.val != 5:
        return self.error(f"{self.val} is NOT 5!")
    return self

add_extension(is_5)

assert_that(5).is_5()
assert_that(6).is_5()  # fails!
```

Both lines run, but a type checker rejects the first one, since `5` resolves to the numeric protocol
and that declares no `is_5`.

A checker sees an extension only where the value keeps the whole builder:

- a value with a capability but no overload of its own, such as your own iterable or a non-`dict` mapping
- anything typed `Any`.

Everything else gets its own protocol or the core surface. Why, and the ways round it:
[Where the typed surface ends](../concepts/type-safety.md#where-the-typed-surface-ends).

`remove_extension()` takes the same function and unregisters it, so a temporary assertion does not
leak into other tests:

```python
from assertpy import remove_extension

remove_extension(is_5)
```

## When you want the assertion typed

`add_extension()` registers a name at run time. No checker learns that name or its signature: where a
value keeps the whole builder the call is accepted as `Any`, and everywhere else it is rejected.

Nothing adds it to the inferred type for you:

- You can declare your own `Protocol` with `is_5()` and `cast()` the builder to it. The call is typed, but
  only what you declare is: `is_5().is_greater_than(0)` needs `is_greater_than` on your protocol too.
- The protocols the views are built from are private and stay that way, so the typed surface can keep
  moving.

What is supported is writing the check as a matcher. It is typed end to end, it restricts the type it
accepts, and it imports nothing private:

```python
from assertpy import Matcher, assert_that


class MultipleOf:
    def __init__(self, other: int) -> None:
        self.other = other

    def matches(self, value: int) -> bool:
        return value % self.other == 0

    def describe(self) -> str:
        return f"a multiple of <{self.other}>"

    def describe_mismatch(self, value: int) -> str:
        return f"was <{value}>"


def multiple_of(other: int) -> Matcher[int]:
    return MultipleOf(other)


assert_that(24).satisfies(multiple_of(6)).is_greater_than(0)
```

The chain keeps the numeric assertions after `satisfies()`, and a checker refuses `multiple_of(6)` on a
string. What it does not do is narrow the value: `satisfies()` hands back the same view it was called
on, and only a `TypeIs` predicate changes that. What you give up is the spelling:
`satisfies(multiple_of(6))` rather than `is_multiple_of(6)`.

Call the factory directly rather than registering the matcher under a dynamic name, for the same reason
`add_extension` is untyped: a name resolved at run time is a name a checker cannot read.

## Project-wide reuse

An extension is registered for the whole process from the moment `add_extension()` runs, in every
module, until `remove_extension()` takes it away. To register it at a point you choose rather than
wherever a module happens to be imported, do it in a pytest fixture in `conftest.py`:

```python
import pytest
from assertpy import add_extension

def is_5(self):
    if self.val != 5:
        return self.error(f"{self.val} is NOT 5!")
    return self

@pytest.fixture(scope="module")
def my_extensions():
    add_extension(is_5)
```

Then request the fixture in any test that needs the extensions:

<!-- docs-guard: untyped -->

```python
from assertpy import assert_that

def test_foo(my_extensions):
    assert_that(5).is_5()
    assert_that(6).is_5()  # fails!
```

- A name already in use is refused with `ValueError`, whether a built-in such as `is_equal_to` holds it
  or another function added earlier, so an extension cannot replace an assertion by accident.
- `override=True` replaces it on purpose.
- Adding the same function again is not a clash, so the module-scoped fixture above can run once for
  every module that requests it.
- A name a polling chain uses for itself, such as `within` or `every`, or one starting with `_`, `cr_`
  or `gi_`, is refused with `ValueError` even under `override=True`, since after `eventually()` the
  extension could never be reached.

## Writing custom assertions

A few conventions keep custom assertions consistent with the built-ins:

1. Use `self` as the first parameter, as if the function were an instance method.
2. Read the actual value from `self.val`.
3. Test the negative case and fail if it holds.
4. Fail via `self.error(...)`, which raises `AssertionError` and prints your message.
5. Raise `TypeError`/`ValueError` for bad input (a programming error), not `self.error()`. The
   built-ins word every type refusal the same way, `<subject> must be <expectation>, but was
   <value> (<type>)`, so a custom assertion reads like one when it follows the same shape.
6. Always `return self` so the assertion chains.

```python
import numbers


def is_multiple_of(self, other):
    if isinstance(self.val, numbers.Integral) is False or self.val <= 0:
        raise TypeError(f"val must be a positive integer, but was <{self.val}> ({type(self.val).__name__})")
    if isinstance(other, numbers.Integral) is False or other <= 0:
        raise TypeError(
            f"given other arg must be a positive integer, but was <{other}> ({type(other).__name__})"
        )

    _, rem = divmod(self.val, other)
    if rem > 0:
        return self.error(
            f"Expected <{self.val}> to be multiple of <{other}>, but was not."
        )
    return self
```

### Wrapping a library that raises

When the assertion delegates to a library, the failure is usually caught and folded into the message.
Doing that inside `except` leaves the caught exception in the traceback, and the reader sees the same
diagnostic twice, once under "During handling of the above exception". Pass `suppress_context=True`
to drop it:

```python
def is_valid_config(self):
    try:
        some_library.validate(self.val)
    except some_library.ValidationError as exc:
        return self.error(
            f"Expected a valid config, but it was rejected:\n{exc}",
            suppress_context=True,
        )
    return self
```

Only pass it when the caught exception's text is already in your message, or carries nothing. Leave it
off when the caught exception is the caller's own, as in an assertion about a callable they gave you:
there its traceback is the point of the failure, not noise.
