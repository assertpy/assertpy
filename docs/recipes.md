# Patterns & recipes

Task-oriented recipes for common testing jobs. Each one is a small, copy-pasteable pattern. Follow the
links into the guides and [API reference](reference/overview.md) for the full surface.

## Test an HTTP API response

Assert the status, then validate the body's *shape* so dynamic fields (ids, timestamps) never make the
test brittle. Use a [matcher](guides/matchers.md) per volatile field and a literal for the fixed ones:

<!-- docs-guard: skip -->
```python
resp = client.get("/orders/42")

assert_that(resp).has_status_code(200)
assert_that(resp).decoded_as_json().matches_structure({
    "id": match.is_positive(),
    "status": match.is_in("paid", "pending", "shipped"),
    "customer": {"name": match.is_non_empty_string()},
})
```

Assert on the response rather than on `resp.status_code` and `resp.json()`, and every failure below
says which response it came from, with the request line where the client kept one:

```text
Expected <{.., 'status': 'refunded'}> to match structure ..., but at <status>: ...
from GET https://api.example.com/orders/42 -> 200
```

That line reads no body and starts no I/O, so a streaming response that has not been read is safe to
assert on.

`decoded_as_json()` is where the body gets read, because calling it is you asking for it. When the body
is not JSON, the failure names the content type and how the body starts, rather than handing you a
`JSONDecodeError` from your own test. A body that could not be read at all is reported as exactly that,
since an unread body may well have been JSON:

<!-- docs-guard: skip -->
```python
assert_that(resp).decoded_as_json()
# ValueError: the response body is not JSON: content-type is 'text/html; charset=utf-8'
#             and it starts with '<!doctype html><html><body>Login required</body></html>'
```

It works on any client that keeps a status code and headers. The suite exercises six of them against
the real library rather than a stand-in: httpx, httpx2, requests, Flask, Django and Starlette, whose
test client is what FastAPI's is. None of them is imported, and none has to be installed.

The body check itself is an ordinary value assertion, so it runs without a live server:

```python
body = {"id": 42, "status": "paid", "customer": {"name": "Alice"}}
assert_that(body).matches_structure({
    "id": match.is_positive(),
    "status": match.is_in("paid", "pending", "shipped"),
    "customer": {"name": match.is_non_empty_string()},
})
```

When you have an OpenAPI spec, assert the whole body against the operation's response schema with
[`conforms_to_openapi()`](guides/data.md#conforms_to_openapi). With a Pydantic model, reach for
[`assert_conforms()`](concepts/type-safety.md#contract-narrowing-with-assert_conforms), which also
narrows the chain to the model's type.

## Ignore volatile fields (ids, timestamps)

For a full-value comparison where a few fields change every run, name them with `placeholders`
(asserted separately by a matcher) or drop them with `ignore`:

```python
actual = {"id": "3f9a", "name": "Alice", "created_at": "2026-01-01T00:00:00Z"}

assert_that(actual).matches_structure({
    "id": match.matches_regex(r"[0-9a-f]+"),
    "name": "Alice",
    "created_at": match.is_non_empty_string(),
})
```

`is_equal_to(ignore=...)` does the same for object graphs (dataclasses, attrs, Pydantic models), by key,
nested path, regex, or type - see [Selective comparison](guides/assertions.md#selective-comparison-ignore--include).

## Compare rows that arrive in any order

Where every row carries a key of its own, sort both sides by it and compare them as lists. `ignore`
leaves the volatile fields out, and a failure points at the row and the field:

```python
def by_id(row):
    return row["id"]


rows = [
    {"id": 3, "name": "Cy", "role": "reader", "updated_at": "2026-03-01T10:00:00Z"},
    {"id": 1, "name": "Ann", "role": "admin", "updated_at": "2026-03-01T10:00:02Z"},
    {"id": 2, "name": "Bo", "role": "reader", "updated_at": "2026-03-01T10:00:01Z"},
]
expected = [
    {"id": 1, "name": "Ann", "role": "admin"},
    {"id": 2, "name": "Bo", "role": "reader"},
    {"id": 3, "name": "Cy", "role": "reader"},
]

assert_that(sorted(rows, key=by_id)).is_equal_to(sorted(expected, key=by_id), ignore="updated_at")
```

Had the second row been expected as an editor:

```text
Expected <[.., {.., 'role': 'reader'}, ..]> to be equal to <[.., {.., 'role': 'editor'}, ..]> ignoring keys <updated_at>, but was not.
diff (sequence):
  [1].role:
    - 'reader'
    + 'editor'
```

This holds where every row has the key, the keys can be ordered against each other, and no two rows
share one. Two rows with the same key are paired in the order they arrived, which need not be the pair
you meant.

Where the rows have no such key,
[`contains_exactly_in_any_order()`](guides/assertions.md#lists) compares them as a multiset, and takes
`match.equal_to(row, ignore="updated_at")` in place of a row to leave a field out. Its failure lists the
rows it did not find and the rows nobody asked for, whole, and does not point into them.

## Choose a snapshot style

Store the expected value in a **file** with `snapshot()`, or **inline** in the test source with
`matches_inline()`. Both are recorded with `pytest --assertpy-snapshot-update`, and both honor the same
selective knobs and CI mode:

<!-- docs-guard: skip -->
```python
def test_report():
    # file snapshot -> __snapshots/snap-test_report.json
    assert_that(build_report()).snapshot()
    # inline snapshot -> the literal is written into this line
    assert_that(build_summary()).matches_inline()
```

- Inline suits small, literal-able values you want to read next to the test. It needs the `[inline]`
  extra (`pip install assertpy[inline]`).
- A file suits large payloads and values that need a custom serializer (`datetime`, `Decimal`, a domain
  object).

See [Snapshot testing](guides/testing.md#snapshot-testing).

## Assert on a filtered, mapped collection

Chain the collection pipeline to narrow a list before asserting, instead of writing a loop:

```python
orders = [
    {"id": 1, "total": 100, "status": "paid"},
    {"id": 2, "total": 50, "status": "pending"},
    {"id": 3, "total": 200, "status": "paid"},
]

assert_that(orders).filtered_on(lambda order: order["status"] == "paid").mapped(
    lambda order: order["total"]
).contains_only(100, 200)
```

`first()`, `last()`, `single()`, and `element(i)` pivot to one element. `flat_mapped()` flattens. See
[Collection pipeline](guides/fluent.md#collection-pipeline).

## Collect every failure in one run

A soft-assertion block reports all failures at once instead of stopping at the first, with a `file:line`
for each - ideal for validating many fields of one object:

```python
from assertpy import soft_assertions

user = {"name": "Alice", "age": 30, "email": "alice@example.com"}
with soft_assertions():
    assert_that(user["name"]).is_not_empty()
    assert_that(user["age"]).is_between(0, 120)
    assert_that(user["email"]).contains("@")
```

See [Soft assertions](guides/testing.md#soft-assertions).

## Assert on what was logged

`caplog` captures the records, and `extracting` reads the fields worth asserting on. A failure prints
every record it captured, so the one you expected is compared against the whole set rather than against
nothing:

```python
import logging

logger = logging.getLogger("billing")


def charge(order: dict[str, int]) -> None:
    logger.error("timeout talking to billing for order %s", order["id"])


def test_the_timeout_is_logged(caplog):
    with caplog.at_level(logging.INFO):
        charge({"id": 7})

    assert_that(caplog.records).extracting("levelname", "message").contains(
        ("ERROR", match.contains_string("timeout"))
    )
    assert_that(caplog.records).extracting("levelname").does_not_contain("WARNING")
```

A matcher works inside the extracted tuple, which is what keeps this readable when the message carries
an id or a duration you do not want to spell out.

## Test exceptions and their cause chain

Capture an exception with `raises().when_called_with()`, then keep asserting on it - the message, the
cause chain, or a member of an `ExceptionGroup`:

```python
def load(value):
    try:
        int(value)
    except ValueError as error:
        raise RuntimeError("load failed") from error

assert_that(load).raises(RuntimeError).when_called_with("x").caused_by(ValueError)
```

`raised()` pivots to the exception object, `has_root_cause()` walks the whole chain, and
`contains_error()` matches inside an `ExceptionGroup`, where `errors()` hands back the failures
themselves. See [Expected exceptions](guides/errors.md#expected-exceptions).

## Wait for eventual consistency

When a value settles asynchronously (a queue drains, a cache warms), poll with `eventually()` (async) or
`eventually_sync()` (blocking) instead of `sleep`. A timeout reports a convergence trace:

<!-- docs-guard: skip -->
```python
await assert_that(queue_depth).eventually().within(10).is_zero()
```

See [Polling assertions](guides/testing.md#async-assertions).

## Keep the value, statically narrowed

An assertion hands the value back, narrowed for the type checker, so you can assert and use it in one
step without a `cast` or a bare `assert`:

```python
value = assert_that("hello world").is_not_none().is_instance_of(str).value
assert_that(value.upper()).is_equal_to("HELLO WORLD")
```

`is_not_none()` strips `None`, `is_instance_of()` narrows to the class. The returned `.value` carries the
narrowed type. See [Typed narrowing](concepts/type-safety.md#typed-narrowing-with-value).

## Add a project-specific assertion

Register a reusable matcher for a domain rule once, then use it everywhere via `match.*` or `satisfies()`:

```python
from assertpy import assert_that, match, register_matcher

@register_matcher("is_valid_sku")
def is_valid_sku():
    return match.matches_regex(r"^[A-Z]{3}-\d{4}$")

assert_that("ABC-1234").satisfies(match.is_valid_sku())
```

For a whole family of chainable assertions on your own type, use `add_extension` - see
[Custom assertions](extending/custom-assertions.md).

## When full structural comparison is too much

For a very large object, comparing the whole thing is slow and the diff is noisy. Extract just the parts
you care about and assert on those:

```python
response = {
    "id": "abc-123",
    "items": [{"sku": "A"}, {"sku": "B"}],
    "meta": {"total": 2, "page": 1},
}

assert_that(response["items"]).is_length(2)
assert_that(response).has_json_path("$.meta.total")
assert_that(response["meta"]["total"]).is_equal_to(2)
```

`extracting()` pulls a key or an attribute off every element of a collection. `has_json_path()` and
`at_json_path()` navigate into a nested payload, and need the JSON extra
(`pip install assertpy[json]`). This keeps the failure focused on the field that broke.

What a failed comparison costs follows the two values, not the message:

- The sentence stays a few hundred characters and the report prints the first fifty differences, but the
  failure reads both values whole and keeps every difference in `failure.diff.entries`.
- For scale, on one machine and one row shape: two lists of 10 000 rows differing in every row took about
  90 ms and 8 MB to fail, where `==` answered in a microsecond. One differing row among 10 000 took 5 ms.
- A polling assertion pays that at every failed attempt, so
  [`eventually()`](guides/testing.md#async-assertions) over a value that large polls less often than its
  interval asks.

## Migrate an assertion from plain `assert`

Replace a cluster of bare asserts with one fluent chain - fewer statements, a structured diff on failure,
and type-aware autocomplete:

```python
items = ["viewer", "editor", "admin"]

# before: three statements, no diff, no autocomplete
assert isinstance(items, list)
assert len(items) == 3
assert "admin" in items

# after: one chain
assert_that(items).is_instance_of(list).is_length(3).contains("admin")
```

Coming from `assertpy` 1.x, see [Upgrading from assertpy 1.x](getting-started/migration.md) for what
changes.
