# Fluent API

## Chaining

Assertions chain into a single statement that reads like a sentence:

```python
assert_that("foo").is_length(3).starts_with("f").ends_with("oo")
assert_that([1, 2, 3]).is_type_of(list).contains(1, 2).does_not_contain(4, 5)
assert_that(fred).has_first_name("Fred").has_last_name("Smith").has_shoe_size(12)
assert_that(people).is_length(2).extracting("first_name").contains("Fred", "Joe")
```

A generator, an iterator, a `zip` or a `map` hands its items out once. A chain over one reads the same
items at every link: the builder keeps what the value has handed out, and takes the rest only as far
as an assertion walks.

```python
assert_that(iter([1, 2, 3])).contains(1).does_not_contain(9).is_sorted()
```

`val` and `value` stay the iterator you passed, which the chain has read by then. The chain keeps what
its own assertions read, and nothing else:

- The chain does not see what you take from the iterator yourself: through `val` or another name, in a
  function you pass to an assertion, or in a method of the iterator's own class, such as an `__eq__` or
  `__len__` that reads it when an assertion or a matcher compares or measures it.
- A matcher that reads the items, such as `match.contains()` or `match.each_item()`, gets the items the
  chain keeps, the same for every link and every matcher combined with it.
- A matcher that asks about the value itself (type, identity, length, an attribute) is asked about the
  iterator: `match.is_instance_of(Iterator)` holds, `match.has_length(3)` does not. Your own matcher says
  which kind it is with [`reads_items`](matchers.md#a-one-shot-value).
- A `satisfies()` predicate gets the iterator itself, as does your own matcher that asks about the value.
  If a link has already read part of the value, reading past it raises `TypeError`. Assert on
  `list(...)` of the value instead.
- A matcher that is an operand of a comparison, as in `is_equal_to(match.contains(1))`,
  `match.equal_to(match.contains(1))` or `is_in(...)`, is handed the iterator as `==` hands it, and one
  that reads items takes them from it beside the chain, as a predicate does. Pass `match.contains(1)`
  to `satisfies()` itself to have it read the chain's items.
- A value that is not its own iterator and hands out one shared iterator each time it is asked is
  read once, as before.

## Universal negation

The `.not_` property inverts the next assertion in the chain, so there is no need for dedicated
`is_not_*` methods:

```python
assert_that(5).not_.is_none()
assert_that("abc123").not_.is_alpha()
assert_that([3, 1, 2]).not_.is_sorted()
assert_that(42).not_.is_in(1, 2, 3)
assert_that("hello").not_.is_instance_of(int)
```

Chaining continues normally after a negated assertion:

```python
assert_that(5).not_.is_none().is_positive()
assert_that("hello").not_.is_empty().is_length(5).is_alpha()
```

Static types survive the inversion too. A negated step hands back the type the chain had before
`.not_`, so the value type is kept, and a negated narrowing narrows nothing:

```python
value = assert_that(42).not_.is_equal_to(43).value  # int, not object


def check(payload: object) -> None:
    assert_that(payload).not_.is_instance_of(str)  # still the object view, not the str one
```

And a wrong-domain assertion after it is still caught:

<!-- docs-guard: type-error -->
```python
# type error: is_greater_than is not a string assertion
assert_that("x").not_.is_empty().is_greater_than(0)
```

`.not_` works with descriptions, soft assertions, warn mode, and matchers:

<!-- docs-guard: raises -->
```python
assert_that(5).described_as("my check").not_.is_positive()
# assertpy.AssertionFailure: [my check] Expected <5> to NOT satisfy: is_positive()

with soft_assertions():
    assert_that(5).not_.is_positive()    # collected, not raised

assert_warn("hello").not_.is_alpha()     # logs a warning

assert_that(-5).not_.satisfies(match.is_positive())
assert_that([1, -2, 3]).not_.each(match.is_positive())
```

`.not_` inverts the answer, never whether the question could be asked. When what an assertion
presupposes is missing, it fails under `.not_` with the message it fails with anyway: an existing path
for `is_readable()`, a file for `is_named()`, the field a `has_<name>()` assertion reads, an `include=`
key, the group `extracting_group()` names, an exception group for `contains_error()`.

<!-- docs-guard: raises -->
```python
assert_that("no/such/file.txt").not_.is_readable()
# assertpy.AssertionFailure: Expected <no/such/file.txt> to exist, but was not found.
```

!!! note
    Only assertions can be negated. Steps that configure or transform - not assert - raise a
    `TypeError` under `.not_`:

    - `described_as()`, `decoded_as()`, `at_json_path()`
    - the collection pipeline (`extracting()`, `filtered_on()`, `mapped()`, `first()`, ...)
    - `eventually()` / `eventually_sync()`.

    Place them before `.not_` (or negate the assertion that follows them) instead:

    ```python
    assert_that(1).described_as("desc").not_.is_none()          # description before not_
    assert_that(people).extracting("name").not_.contains("Zoe")  # negate after extracting
    ```

## Collection pipeline

Pipeline methods transform the value before asserting. Each returns a new builder, so the original
value is unchanged and steps chain freely.

### filtered_on(predicate)

Filter elements by a callable or matcher:

```python
assert_that([1, -2, 3, -4]).filtered_on(lambda x: x > 0).is_length(2)
assert_that(items).filtered_on(match.is_positive()).is_not_empty()
assert_that(users).filtered_on(match.has_property("active")).is_length(5)
```

### mapped(func)

Transform each element:

```python
assert_that(["a", "b", "c"]).mapped(str.upper).contains("A", "B")
assert_that(users).mapped(lambda u: u.name).contains("Alice", "Bob")
```

### flat_mapped(func)

Transform and flatten:

```python
assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "b", "c", "d")
assert_that(users).flat_mapped(lambda u: u.tags).contains("admin", "user")
```

### first() / last() / element(index) / single()

Navigate to a specific element and assert on it:

```python
assert_that([10, 20, 30]).first().is_equal_to(10)
assert_that([10, 20, 30]).last().is_equal_to(30)
assert_that([10, 20, 30]).element(1).is_equal_to(20)
assert_that([42]).single().is_equal_to(42)
```

!!! warning
    `first()`, `last()`, and `single()` raise `ValueError` on an empty collection (`single()` also on
    more than one element). `element(index)` raises `IndexError` when the index is out of range, a
    negative one included, and `TypeError` when it is not an integer, a `bool` included. A numpy
    integer is taken.

### Chaining pipeline steps

Pipeline methods return a new builder, so they chain with each other and with any assertion:

```python
assert_that(orders).filtered_on(lambda o: o.status == "FAILED").mapped(
    lambda o: o.total
).first().satisfies(match.is_positive())
assert_that(items).filtered_on(match.is_positive()).not_.is_empty()
```

!!! note "What the pipeline does to the static type"
    The two halves behave differently, and the difference is the useful part.

    `first()`, `last()`, `element()` and `single()` narrow the chain to the **element**, so a list of
    orders hands you an order and `.value` is typed as one. Every assertion is available on it,
    type-specific ones included.

    `mapped()` and `flat_mapped()` stay a collection, re-typed to whatever the function returns.

    ```python
    assert_that([10, 20, 30]).first().is_positive()      # element: numeric assertions apply
    assert_that(["a", "bb"]).mapped(len).contains(1, 2)  # still a collection, now of int
    ```

    See [typed narrowing](../concepts/type-safety.md#typed-narrowing-with-value) for the whole picture.
