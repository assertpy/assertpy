# Data Navigation

## JSON Path / Schema

Navigate JSON structures with JSONPath and validate them against JSON Schema.

!!! note "Optional dependency"
    ```bash
    pip install assertpy[json]
    ```

### at_json_path

Navigate to a JSONPath and keep asserting on the extracted value:

```python
data = {"users": [{"name": "Alice"}, {"name": "Bob"}], "meta": {"total": 2}}

assert_that(data).at_json_path("$.meta.total").is_equal_to(2)
assert_that(data).at_json_path("$.users[0].name").is_equal_to("Alice")
assert_that(data).at_json_path("$.users[*].name").is_equal_to(["Alice", "Bob"])
```

Raises `ValueError` if the path does not exist.

### has_json_path / does_not_have_json_path

Assert that a path is present or absent:

<!-- docs-guard: skip -->
```python
assert_that(data).has_json_path("$.meta.total")
assert_that(data).does_not_have_json_path("$.error")
```

### matches_json_schema

Validate against a JSON Schema dict, or load it from a file:

<!-- docs-guard: skip -->
```python
schema = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    "required": ["name"],
}

assert_that({"name": "Alice", "age": 30}).matches_json_schema(schema)
assert_that(data).matches_json_schema_from_file("schemas/user.json")
```

JSON assertions chain and work with soft assertions:

<!-- docs-guard: skip -->
```python
with soft_assertions():
    assert_that(response).has_json_path("$.data")
    assert_that(response).at_json_path("$.data.id").satisfies(match.is_positive())
```

A path lands on whatever the document holds there, so what comes back offers the assertions every
value has. To reach further, either use a matcher as above, or state the type you expect and continue
in it.

The predicate below is a `TypeIs`, so the type checker takes its word. `satisfies()` runs it and reads
the verdict. Neither can confirm that the claim matches the check inside.

```python
from typing_extensions import TypeIs


def is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int)


payload = {"data": {"id": 7}}
assert_that(payload).at_json_path("$.data.id").satisfies(is_int).is_between(1, 99)
```

### conforms_to_openapi

Validate a response body against an OpenAPI operation's response schema - the one contract check none of
the other assertion libraries here offer.

Three spec dialects are read:

- **OpenAPI 3.1 and 3.2**, as written: both carry JSON Schema 2020-12
- **OpenAPI 3.0**, including its `nullable` keyword
- **Swagger 2.0**, where the schema sits directly on the response, including its `x-nullable` extension

A spec declaring any other `openapi` version is refused. Read as one of these it would validate against
the wrong dialect, which passes every keyword that dialect cannot spell.

The same holds inside a spec. OpenAPI 3.0 and Swagger 2.0 carry an older JSON Schema, which skips or
misreads keywords of a later one: a 3.0 schema with `const: a` used to take `b`.

- A schema the response reaches that holds such a keyword is refused with a `ValueError` naming the schema
  and the keyword, wherever it stands.
- The keywords: `const`, `contains`, `propertyNames`, `if`, `dependentRequired`, `dependentSchemas`,
  `unevaluatedProperties`, `unevaluatedItems`, `prefixItems`, `$dynamicRef`, `$recursiveRef`, and
  `exclusiveMinimum` or `exclusiveMaximum` written as a number.
- Fix: spell the constraint as 3.0 does, or move the whole spec to OpenAPI 3.1. With only the version line
  changed, `nullable` and a boolean `exclusiveMinimum` are what stop being read.
- A `$schema` inside a 3.0 or 2.0 document changes nothing: the document is one dialect throughout.

Inside any of them, `$ref`, `oneOf` / `allOf` / `anyOf` and `enum` validate with full JSON-Schema
semantics.

`multipleOf` divides the numbers as written:

- `19.99` is a multiple of `0.01`. As two floats it is not (`1998.9999999999998`), and jsonschema fails it.
- A float is read as the decimal it prints as, so `0.30000000000000004` is no multiple of `0.1`.
- Digits a float does not keep are gone before the check: `1.0000000000000001` parses as `1.0`. Where they
  matter, parse with `json.loads(text, parse_float=decimal.Decimal)`: a `Decimal` is divided exactly.
- A `multipleOf` that is not a number above zero is refused with a `ValueError`.

Two keywords of OpenAPI 3.0 are read as 3.0.3 words them, since the value is a response:

- `nullable: true` adds `null` to the `type` beside it and leaves every other keyword as written, so an
  `enum` beside them lets `null` through only where it lists it. With no `type` beside it the keyword
  does nothing, with the one exception below.
- A property marked `writeOnly: true` is not asked for by `required`, which for such a property "will
  take effect on the request only". One that did arrive is validated like any other. The mark is read
  through a `$ref`, and what stands beside a `$ref` is ignored, as 3.0 has it.

Both are read on the schemas the response reaches and never on a value: an `enum` member or an `example`
that looks like a schema is left as it is.

One reading is wider than the text on purpose:

- `nullable: true` on a `$ref`, `allOf`, `anyOf` or `oneOf` with no `type` of its own still allows `null`.
  That is how a nullable reference is usually written, and such a spec would otherwise fail on every `null`.
- Whatever else stands beside the `allOf`, `anyOf` or `oneOf` is still asked: an `enum` there lets `null`
  through only if it lists it.

`strict_nullable=True` holds `nullable` to the text. Without a `type` beside it the keyword does nothing,
and `null` is asked of the rest of the schema:

- a `$ref` to a string refuses it, one to a nullable string takes it
- an `anyOf` takes it where a branch does, a `oneOf` where exactly one does
- a schema with nothing else takes it as any value.

`x-nullable` and OpenAPI 3.1 read the same either way.

Three limits:

- `required` in one branch of an `allOf` and the `writeOnly` property in another are not brought
  together: the mark is looked for in the `properties` of the schema that holds the `required`.
- Swagger 2.0's `x-nullable` is an extension with no text of its own. It allows `null` past an `enum`
  and on any schema with no `type`, as it did.
- In 3.1 and 3.2 `writeOnly` is an annotation, and `required` asks for the property.

A `format` is checked where there is a check for it:

| `format` | Checked |
| --- | --- |
| `date`, `ipv4`, `ipv6`, `uuid`, `regex` | always, by jsonschema |
| `email` | always, as the mailbox of RFC 5321: atoms joined by dots or a quoted string, an `@`, then a host name or an address in brackets. `a@b.example`, `"a b"@c.example` and `a@[IPv6:::1]` pass. `@`, `a b@c.example` and `a..b@c.example` fail, and so does an address with a letter past ASCII, which is for `idn-email`. The domain has the lengths of a host name. The local part has none in the grammar, and the 64 characters SMTP allows it are not held |
| `time` | always, as the `full-time` of RFC 3339, which needs its offset: `10:00:00Z` and `10:00:00+02:00` pass, `10:00:00` fails. A second of `60` is taken in the last minute of a UTC day |
| `date-time` | always, by the grammar of RFC 3339: `"yesterday"` and `"2026-02-30T10:00:00Z"` fail. A second of `60` is taken in the last minute of a UTC month, where a leap second can fall. The check is the same one whether or not the package that gives jsonschema its own is installed |
| `int32`, `int64` | always, as the signed range: `2**40` is no `int32` |
| `uri` | always, by the grammar of RFC 3986: a scheme is required, so `/orders/7` is no `uri` (it is a `uri-reference`), and neither is a text with a space or a non-ASCII letter in it |
| `hostname` | always, as the syntax of RFC 1123: labels of ASCII letters, digits and hyphens, 63 characters each and 253 in all, with no dot after the last. Under OpenAPI 3.1, whose JSON Schema takes punycode into the format, a label that opens `xn--` has to be a valid A-label of IDNA 2008 as well: `xn--nxasmq6b` passes, `xn--X` fails. The `idna` package of the `json` extra judges it by the Unicode tables of the release installed, so a newer release takes code points assigned since. Under 3.0 and Swagger 2.0 the format is the syntax alone |
| `duration` | always, by the grammar RFC 3339 gives for it: `P1DT12H` and `P2W` pass, with the letters in either case. It is narrower than ISO 8601: `PT0.5S`, `P1Y2D` and `-P1D` fail. A fraction of a second, which Java and .NET print, is none: leave the format out for a field that carries one |
| `uri-reference`, `iri`, `idn-email`, `json-pointer`, `uri-template` and the others jsonschema checks beside a package of their own | where that package is installed, and not where it is missing. `jsonschema[format-nongpl]` brings them all |

Pass the parsed spec plus the operation's path and method. Loading the YAML or JSON is your job:

```python
schema = {
    "type": "object",
    "required": ["id", "total"],
    "properties": {
        "id": {"type": "integer"},
        "total": {"type": "number"},
        "email": {"type": "string", "format": "email", "nullable": True},
    },
}
spec = {
    "openapi": "3.0.3",
    "paths": {
        "/orders/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": schema}}}
                }
            }
        }
    },
}

body = {"id": 42, "total": 19.99, "email": None}
assert_that(body).conforms_to_openapi(spec, "/orders/{id}", "get")
```

`path` is the operation's key in the spec, not the request URL. A Swagger 2.0 `basePath` (or an OpenAPI 3
server prefix) is not part of it, so an endpoint served at `/api/v1/version` is looked up as `/version`.

- `status` defaults to `200`, then `201`, then the range `2XX`, then `default`. Pass `status=` to pick
  another.
- A status is looked up as the spec declares it: its own code first, then its range (`404` under `4XX`),
  then `default`. A status none of the three covers is refused with a `ValueError`.
- Swagger 2.0 has no ranges.

When the body does not conform, the message names the operation and counts the failures. Every one is
reported with its JSON path and the constraint it broke, not just the first:

```text
diff (openapi):
  $:
    - {'id': 'x7', 'email': 'not-an-email'}
    + 'all required properties present'
  $.email:
    - 'not-an-email'
    + 'email format'
  $.id:
    - 'x7'
    + 'type integer'
```

Needs the JSON extra: `pip install assertpy[json]`.

## Regex Group Extraction

### extracting_group()

Search the value for a pattern and continue asserting on the captured group:

```python
log = "2024-01-15 ERROR status=500 path=/api/users"

# by index
assert_that(log).extracting_group(r"status=(\d+)", 1).is_equal_to("500")
# by name
assert_that(log).extracting_group(r"(?P<level>\w+) status", "level").is_equal_to("ERROR")
# group 0 = whole match
assert_that("abc123").extracting_group(r"\d+").is_equal_to("123")
# chains
assert_that("count=42").extracting_group(r"count=(\d+)", 1).is_digit().is_length(2)
```

### matches_with_groups()

Return all groups as a tuple, or a dict for named groups:

```python
assert_that("2024-01-15 ERROR").matches_with_groups(
    r"(\d{4}-\d{2}-\d{2}) (\w+)"
).is_equal_to(("2024-01-15", "ERROR"))

assert_that("key=value").matches_with_groups(
    r"(?P<key>\w+)=(?P<val>\w+)"
).contains_entry({"key": "key"}).contains_entry({"val": "value"})
```
