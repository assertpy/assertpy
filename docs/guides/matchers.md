# Matchers

Matchers are reusable, composable condition objects. Import the `match` namespace:

```python
from assertpy import assert_that, match
```

Combine them with `&` (and), `|` (or), `~` (not), and use them with `satisfies()`, `each()`,
`contains()`, `matches_structure()`, or plain `==`.

## Using matchers

### satisfies()

Test a value against a matcher or a composition:

```python
assert_that(42).satisfies(match.greater_than(0))
assert_that(42).satisfies(match.greater_than(0) & match.less_than(100))
assert_that("hello").satisfies(~match.equal_to("world"))
assert_that(150).satisfies(match.is_negative() | match.greater_than(100))
```

### each()

Check that every element of a collection matches:

```python
assert_that([18, 25, 30]).each(match.between(18, 120))
assert_that(["a", "bb", "ccc"]).each(match.is_instance_of(str))
```

`each()` also accepts a plain predicate:

```python
assert_that([2, 4, 6]).each(lambda x: x % 2 == 0)
```

A class is callable, so it is taken as a predicate too, and the predicate is the class called on the
item. `each(int)` asks whether `int(item)` is truthy: `"2"` and `3.5` pass, and `0` fails. The check
of the type is `each(match.is_instance_of(int))`. The same holds for `satisfies()` and the other
assertions that take a predicate.

### Inside contains()

A matcher passed to `contains()` is tested against each element:

```python
assert_that([3, 7, 12]).contains(match.greater_than(10))
assert_that(["foo", "bar"]).contains(match.matches_regex(r"^f"))
```

## Composition

Matchers support Python operators, including nesting:

```python
positive_and_small = match.is_positive() & match.less_than(10)
extreme = match.less_than(-100) | match.greater_than(100)
not_empty = ~match.is_empty()
complex_check = (match.greater_than(0) & match.less_than(100)) | match.equal_to(-1)
a_final_title = match.starts_with("Release") & ~match.contains_string("draft")

assert_that(50).satisfies(complex_check)
assert_that(-1).satisfies(complex_check)
assert_that("Release 2.33").satisfies(a_final_title)
```

A failure reports the part that failed, not the whole expression, and each part keeps the reason its own
matcher gave:

<!-- docs-guard: raises -->
```python
assert_that(50).satisfies(match.is_instance_of(str) & match.contains("z"))
# Expected (an instance of <str> and a collection containing 'z'), but <50> did not satisfy:
# an instance of <str> (was <50> of type <int>), a collection containing 'z' (was <50>, which cannot be searched).
```

Under `|` every alternative is reported, each narrowed to what failed inside it. For `<50>` against
`(> 0 and < 10) or (> 100 and < 200)` that is `a value less than <10> (was <50>) or a value greater than
<100> (was <50>)`, rather than both branches restated whole.

## Drop-in with plain `==`

Matchers implement `__eq__`, so they work with a bare `assert` and pytest introspection, with no
`assert_that()` wrapper:

```python
assert 42 == match.is_positive()
assert {"id": 5, "name": "Alice"} == {
    "id": match.is_positive(),
    "name": match.is_non_empty_string(),
}
assert [1, 2, 3] == [match.is_positive(), match.is_positive(), match.is_positive()]
assert 42 == (match.is_positive() & match.less_than(100))
```

??? failure "What pytest shows on failure"
    ```
    AssertionError: assert -5 == a positive value
    ```

    The `==` form hands rendering to pytest, so you get pytest's own message without a path-level
    diff. For the rich `match` diff, use the fluent form (`satisfies()`, `matches_structure()`) -
    see [Errors & Reporting](errors.md#rich-pytest-diffs).

!!! tip
    This makes matchers a drop-in addition to an existing suite: add one import, use `match.*` in any
    `==` comparison, no rewrite required.

A built-in matcher's `==` does not raise over an operand its predicate cannot evaluate. A string
handed to `match.is_positive()`, or an object with no ordering, simply compares as not equal, so a
matcher that leaks into a membership check or a foreign comparison stays safe. What a custom matcher's
own `matches()` raises still propagates, and so does a coroutine handed back where a verdict belongs.

## Available matchers

| Matcher | Matches |
|---|---|
| `match.equal_to(val)` | a value equal to `val` |
| `match.greater_than(val)` | a value greater than `val` |
| `match.greater_than_or_equal_to(val)` | a value greater than or equal to `val` |
| `match.less_than(val)` | a value less than `val` |
| `match.less_than_or_equal_to(val)` | a value less than or equal to `val` |
| `match.between(low, high)` | a value in the inclusive range `low` to `high` |
| `match.close_to(val, tolerance)` | a value within `tolerance` of `val` |
| `match.is_none()` | `None` |
| `match.is_not_none()` | a non-`None` value |
| `match.is_instance_of(type)` | an instance of `type`, subclasses included |
| `match.is_type_of(type)` | exactly `type`, so `True` does not match `int` |
| `match.is_truthy()` | a truthy value |
| `match.is_falsy()` | a falsy value |
| `match.has_length(n)` | a value whose `len()` equals `n` (also `match.is_length(n)`, the name the fluent assertion uses) |
| `match.is_empty()` | an empty collection or string |
| `match.is_not_empty()` | a non-empty collection or string |
| `match.is_positive()` | a number greater than zero |
| `match.is_negative()` | a number less than zero |
| `match.is_zero()` | zero |
| `match.is_even()` | an even integer |
| `match.is_odd()` | an odd integer |
| `match.is_divisible_by(n)` | an integer divisible by `n` |
| `match.is_callable()` | a callable object |
| `match.is_in(*values)` | a value present in `values` |
| `match.contains(*items)` | a collection containing every one of `items`; a mapping is searched by key |
| `match.contains_only(*items)` | a collection holding these items and nothing else |
| `match.is_subset_of(*superset)` | a collection whose items all appear in `superset` |
| `match.is_sorted(key=None, reverse=False)` | a collection in order, optionally by `key` |
| `match.has_property(name, matcher?)` | an object with attribute `name`, optionally matching a nested matcher |
| `match.contains_string(sub)` | text containing `sub`, on `str` and on `bytes` |
| `match.matches_regex(pattern)` | a string where `pattern`, as text or compiled, is found (`re.search`) |
| `match.html_equal_to(expected, whitespace="lenient")` | a string holding the same HTML as `expected`, read as [`is_html_equal_to()`](assertions.md#html) reads it |
| `match.starts_with(prefix)` | text starting with `prefix`, on `str` and on `bytes` |
| `match.ends_with(suffix)` | text ending with `suffix`, on `str` and on `bytes` |
| `match.is_uuid()` | a string parseable as a UUID |
| `match.is_non_empty_string()` | a non-empty string |
| `match.is_now(delta=2)` | a `datetime` within `delta` (seconds or a `timedelta`, zero or more) of now. Handles naive and tz-aware values |
| `match.is_before(dt)` | a `datetime` strictly before `dt` (a non-comparable value never matches) |
| `match.is_after(dt)` | a `datetime` strictly after `dt` (a non-comparable value never matches) |
| `match.ignore()` | anything (placeholder for structural matching) |
| `match.each_item(matcher)` | an iterable whose every item matches `matcher` |
| `match.structure(spec)` | a dict or model matching a nested `spec` |
| `match.all_of(*matchers)` | a value matching all of `matchers` |
| `match.any_of(*matchers)` | a value matching any of `matchers` |
| `match.not_(matcher)` | a value not matching `matcher` |

`all_of()`, `any_of()`, and `not_()` are named function equivalents of the `&`, `|`, and `~`
operators from [Composition](#composition). Use whichever reads better.

A matcher checks its arguments when it is built, so a mistake raises where it is written:

- `match.between(10, 1)` and `match.close_to(1.0, -0.1)` raise `ValueError`.
- `match.has_length(2.5)` and `match.is_divisible_by("3")` raise `TypeError`.
- `has_property()`, `each_item()`, `not_()`, `all_of()` and `any_of()` refuse anything but a matcher where
  they take one, as `&` and `|` do:

<!-- docs-guard: raises -->
<!-- docs-guard: type-error -->
```python
match.each_item(lambda x: x > 0)
# TypeError: given matcher arg must be a Matcher, but was <<function <lambda> at ...
```

Wrap a plain predicate in a matcher of its own, or pass it to `satisfies()`, which takes a callable.

## Structural matching

Validate dict structure declaratively, ideal for API responses where some values are dynamic
(IDs, timestamps):

```python
response = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Alice",
    "age": 30,
    "active": True,
}

assert_that(response).matches_structure({
    "id": match.is_uuid(),
    "name": match.equal_to("Alice"),
    "age": match.between(18, 120),
    "active": match.equal_to(True),
})
```

A spec value that is neither a matcher nor a nested dict is compared with `==`: `"name": "Alice"` reads as
`match.equal_to("Alice")`.

- A class is such a value too. `{"id": int}` asks whether the value equals the class `int`, which `7` does
  not. For an instance use `match.is_instance_of(int)`.
- Where the value is an instance of the class in the spec, the failure names that matcher. Where it is
  not, it says the value's type: `but was <7> of type <str>`.
- Beside a class with its own metaclass, an abstract base class or a model, it always says the type: asking
  such a class about an instance would run its code.

A failure prints the value and the spec with what matched left out, as a failed `is_equal_to()` does,
so one wrong field of a wide record stays one short sentence:

```python
try:
    assert_that({"id": 7, "name": "Alice", "age": 15, "active": True}).matches_structure({
        "name": "Alice",
        "age": match.between(18, 120),
        "active": True,
    })
except AssertionError as failure:
    print(str(failure).splitlines()[0])
    # Expected <{.., 'age': 15, ..}> to match structure {.., age: a value between <18> and <120>, ..}, but at <age>: expected a value between <18> and <120>, but was <15>.
```

- A plain dict, a model and an attrs instance print that way, a record under its class name:
  `Customer(.., address={'city': 'Oslo', ..}, ..)`.
- That needs every key, the value's and the spec's, to be exactly `str`, `int`, `bool`, `float`, `bytes`
  or `None`, and record field names to read as names.
- Anything else prints whole: a mapping of another class, a record held by a dict or an attrs instance. A
  model's nested models are dicts once read, and collapse like any dict.
- The failure holds the whole value as `actual` either way.

The value under test can be a plain dict, a Pydantic model (anything exposing `model_dump()`), or an
attrs instance. A model or attrs instance is normalized to its dict first, so the same spec works
either way, including inside `satisfies()` and the `==` form.

Normalization applies at every level: a model nested in a plain dict matches too, and failure paths
still point at the leaf field (`address.city`):

```python
from pydantic import BaseModel

class User(BaseModel):
    id: str
    name: str

user = User(id="550e8400-e29b-41d4-a716-446655440000", name="Alice")

assert_that(user).matches_structure(
    {"id": match.is_uuid(), "name": match.equal_to("Alice")}
)
assert_that(user).satisfies(match.structure({"id": match.is_uuid()}))
assert user == match.structure({"id": match.is_uuid()})
```

An attrs instance matches the same way. One gotcha: a private attrs field keeps its leading underscore
in the spec key, even though attrs strips it from the generated `__init__`:

```python
from attrs import define

@define
class Address:
    city: str
    _zone: str  # the field name is "_zone", though attrs' __init__ takes zone=

assert_that(Address("Paris", "EU")).matches_structure(
    {"city": match.equal_to("Paris"), "_zone": match.is_not_none()}
)
```

!!! note
    A model is matched in its `model_dump()` form: nested models become dicts, `@field_serializer` and
    `@computed_field` outputs are applied, and spec keys are the model's field names (not aliases). The
    spec is matched against this serialized shape, not the live attributes. This is a runtime structural
    check. The spec keys and values are not type-checked against the model's schema.

### Nested structures

Use `match.structure()` for nested dicts:

```python
assert_that({
    "user": {"name": "Alice", "role": "admin"},
    "metadata": {"version": 2},
}).matches_structure({
    "user": match.structure({
        "name": match.is_non_empty_string(),
        "role": match.contains_string("admin"),
    }),
    "metadata": match.structure({"version": match.greater_than(0)}),
})
```

### Ignoring and collections

`match.ignore()` skips a field. `match.each_item()` checks every element of a nested collection:

```python
assert_that({"id": "abc-123", "tags": ["python", "testing"]}).matches_structure({
    "id": match.ignore(),
    "tags": match.each_item(match.is_instance_of(str)),
})
```

!!! note
    Keys present in the value but absent from the spec are ignored, so a structure spec validates a
    subset of fields rather than requiring an exact match.

### When the order does not matter

A payload that returns its records in whatever order the database felt like is the ordinary case, and
there is no `ignore_order` flag to reach for.

`match.contains_only()` is the one. It asks that the value hold only these items, in any order, and it
compares by equality, so records that cannot be hashed work too.

```python
assert_that({"tags": ["testing", "python"]}).is_equal_to({
    "tags": match.contains_only("python", "testing"),
})
```

Because a matcher composes, this works at any depth and at more than one level at once. Here the
customers arrive in any order, and so do the roles inside each of them:

```python
assert_that({
    "customers": [
        {"name": "Bob", "roles": ["reader"]},
        {"name": "Alice", "roles": ["editor", "reader"]},
    ]
}).is_equal_to({
    "customers": match.contains_only(
        match.structure({"name": "Alice", "roles": match.contains_only("reader", "editor")}),
        match.structure({"name": "Bob", "roles": ["reader"]}),
    ),
})
```

The order still holds everywhere it was not waived: an item missing, an extra one, or a wrong value
inside a record all fail as they would in an ordered comparison.

!!! warning "It does not count repeats"
    `contains_only` asks *which* items are there, not how many of each. `["reader"]` satisfies
    `match.contains_only("reader", "reader")`, and `[1, 1, 2]` satisfies `match.contains_only(1, 2)`.
    Where the counts are part of what you are asserting, use
    [`contains_exactly_in_any_order()`](assertions.md#lists) instead. It is multiset equality and it
    refuses both of those, but it applies to the collection itself, so reach it with
    [`extracting()`](assertions.md#lists) or a second assertion when the collection is nested.

When the whole value is the collection, the assertions say it directly and read better than a matcher:
[`contains_exactly_in_any_order()`](assertions.md#lists) for items and their counts, and
`satisfies_exactly_in_any_order()` for one predicate per item.

```python
assert_that([{"name": "Bob"}, {"name": "Alice"}]).contains_exactly_in_any_order(
    {"name": "Alice"}, {"name": "Bob"}
)
```

### What you see on failure

When fields do not match, the pytest plugin prints the exact path and the predicate that failed, for every
mismatch, not just the first:

![Colored match diff: user.name, user.role and user.age each shown with their path and the predicate that failed](../assets/diff-match.svg)

The same `match` diff is produced by [`satisfies()`](#satisfies) and [`each()`](#each) whenever a
matcher fails inside an assertion.

## Custom matchers

`register_matcher()` adds your own matcher to the `match` namespace. Custom matchers compose with
`&`, `|`, `~` and work everywhere matchers are accepted.

### Writing one from scratch

`register_matcher()` composes existing matchers, which covers most cases. When the rule cannot be
expressed that way, subclass `BaseMatcher` and supply the predicate and its two descriptions:

```python
from assertpy import BaseMatcher, assert_that

class IsEven(BaseMatcher):
    def matches(self, value):
        return isinstance(value, int) and value % 2 == 0

    def describe(self):
        return "an even number"

    def describe_mismatch(self, value):
        return f"<{value}> is odd"

assert_that(4).satisfies(IsEven())
```

`describe()` names what was required and `describe_mismatch()` what was seen, and the assertion
composes the sentence from both. Only `matches()` and `describe()` are required: the default
`describe_mismatch()` renders `was <value>`.

A subclass gets `&`, `|` and `~` for free, so it composes with the built-ins exactly like they compose
with each other.

### Answering in one call

`evaluate()` is the same matcher answering with a [`MatchResult`][assertpy.matchers.MatchResult]
instead of with three separate calls. Every matcher has it, including one written before it existed:
the default composes it from `matches()`, `describe()` and `describe_mismatch()`.

```python
from assertpy import match

result = match.is_positive().evaluate(-5)
print(result.matched)        # False
print(result.description)    # a positive value
print(result.mismatch)       # was <-5>
print(bool(result))          # False
```

Implement it instead of the three when finding the reason costs what finding the verdict already paid
for, which is any matcher that walks its value:

```python
from assertpy import BaseMatcher, MatchResult, assert_that

class HasEvenLength(BaseMatcher):
    def describe(self):
        return "an even number of items"

    def evaluate(self, value):
        size = sum(1 for _ in value)
        return MatchResult(
            matched=size % 2 == 0,
            description=self.describe(),
            mismatch=f"had {size} items",
        )

assert_that([1, 2]).satisfies(HasEvenLength())
```

The bridge runs both ways: implement `matches()` and `evaluate()` comes for free, implement
`evaluate()` and `matches()` comes for free. Implement neither and both say so, rather than recursing.

`matches()` stays the cheap primitive and the library keeps using it wherever it only needs a verdict:
it is what `==` calls, and a matcher is a dict value in `matches_structure()` and a snapshot
placeholder, so a comparison must not have to build a result object.

### A one-shot value

A generator or an iterator hands its items out once. Where several matchers share one, combined with
`&`, `|` or `~`, or where `satisfies()` asks one about the value of a chain, the library hands a
matcher either the items, read once and kept, or the value itself. `reads_items` on the class says
which:

```python
from collections.abc import Iterator

from assertpy import BaseMatcher, assert_that, match

class IsAnIterator(BaseMatcher):
    reads_items = False  # asks about the value itself

    def matches(self, value):
        return isinstance(value, Iterator)

    def describe(self):
        return "an iterator"

assert_that(iter([1, 2])).satisfies(IsAnIterator() & match.contains(2))
```

- `True` by default: the matcher gets the items in a list, as `satisfies()` always did.
- The built-in matchers that ask about the value (`is_instance_of()`, `is_type_of()`, `has_length()`,
  `equal_to()` and the rest) say `False`.
- A matcher that says `False` and walks the value anyway takes items from the iterator itself. After a
  link that read part of it, the links that follow are refused, as after a predicate, and so is a matcher
  combined with it that reads the items.
- `equal_to()` or `is_in()` holding a matcher, and `equal_to()` given `comparators=`, are treated the same
  way, since `==` hands the value to your code.

### Registering one on the `match` namespace

```python
from assertpy import assert_that, match, register_matcher

@register_matcher("is_valid_email")
def is_valid_email():
    return match.matches_regex(r"^[\w.-]+@[\w.-]+\.\w+$")

assert_that("alice@example.com").satisfies(match.is_valid_email())
```

Parametrised matchers take arguments:

<!-- docs-guard: skip -->
```python
@register_matcher("has_status")
def has_status(expected: str):
    return match.has_property("status", match.equal_to(expected))

assert_that(order).satisfies(match.has_status("active"))
```

They compose and nest like built-ins:

<!-- docs-guard: skip -->
```python
assert_that(email).satisfies(
    match.is_valid_email() & match.contains_string("@company.com")
)
assert_that(response).matches_structure({
    "email": match.is_valid_email(),
    "status": match.has_status("active"),
})
```

??? note "Removing a custom matcher"
    ```python
    from assertpy import unregister_matcher

    unregister_matcher("is_valid_email")
    ```

    `unregister_matcher(name)` removes one matcher by name (and raises `KeyError` if it is not
    registered). `clear_custom_matchers()` removes every custom matcher at once, handy for test
    teardown.
