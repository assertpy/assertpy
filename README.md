<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo.svg">
    <img src="docs/logo.svg" alt="assertpy" width="280">
  </picture>
  <br>
  <b>Fully typed fluent assertion library for Python</b>
</p>

<p align="center">
  <a href="https://github.com/assertpy/assertpy/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/assertpy/assertpy/ci.yml?branch=main&amp;label=CI" alt="CI"></a>
  <a href="https://codecov.io/gh/assertpy/assertpy"><img src="https://codecov.io/gh/assertpy/assertpy/graph/badge.svg" alt="Coverage"></a>
  <a href="https://pypi.org/project/assertpy/"><img src="https://img.shields.io/pypi/v/assertpy" alt="PyPI version"></a>
  <a href="https://pypi.org/project/assertpy/"><img src="https://img.shields.io/pypi/pyversions/assertpy" alt="Python"></a>
  <a href="https://pepy.tech/projects/assertpy"><img src="https://static.pepy.tech/badge/assertpy/month" alt="Downloads"></a>
  <br>
  <a href="https://assertpy.github.io/assertpy/concepts/type-safety/"><img src="https://img.shields.io/badge/overloads-ty%20%7C%20mypy%20%7C%20pyright%20%7C%20pyrefly-2ea043" alt="every public overload checked by ty, mypy --strict, pyright and pyrefly with zero suppressions"></a>
  <a href="https://assertpy.github.io/assertpy/"><img src="https://img.shields.io/badge/docs-online-black" alt="Documentation"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/assertpy/assertpy"><img src="https://img.shields.io/ossf-scorecard/github.com/assertpy/assertpy?label=OpenSSF%20Scorecard" alt="OpenSSF Scorecard"></a>
</p>

<h2 align="center"><a href="https://assertpy.github.io/assertpy/getting-started/quickstart/">Quick start</a></h2>

```bash
pip install assertpy
```

```python
from assertpy import assert_that

def test_user():
    user = {"name": "Alice", "age": 30, "roles": ["viewer", "editor"]}

    assert_that(user).contains_key("name", "age")
    assert_that(user).contains_entry({"name": "Alice"})
    assert_that(user["age"]).is_between(18, 120)
    assert_that(user["roles"]).contains("viewer").does_not_contain("admin")
```

The [full documentation](https://assertpy.github.io/assertpy/) covers every assertion, matcher, and integration.

<table>
<tr>
<td valign="top" width="50%">
<a href="#why-fluent-assertions"><b>Failures that point at the difference</b></a><br>
A recursive diff names the exact path that differs, in color, instead of dumping both structures
</td>
<td valign="top" width="50%">
<a href="#type-aware-autocomplete"><b>Type-aware autocomplete</b></a><br>
<code>assert_that()</code> returns a protocol per value type, so your IDE offers the methods that fit
</td>
</tr>
<tr>
<td valign="top">
<a href="#typed-narrowing"><b>Typed narrowing</b></a><br>
An assertion hands the value back statically narrowed, with no <code>cast</code> and no bare <code>assert</code>
</td>
<td valign="top">
<a href="#features"><b>Composable matchers</b></a><br>
45 matchers that combine with <code>&amp;</code>, <code>|</code>, <code>~</code> and nest inside the expected structure itself
</td>
</tr>
<tr>
<td valign="top">
<a href="#features"><b>Built for test suites</b></a><br>
Soft assertions, polling for eventual consistency, snapshots, and expected-exception chains
</td>
<td valign="top">
<a href="#integrations"><b>Integrations</b></a><br>
Allure, Behave, JSON Path and Schema, pandas, polars, numpy, and OpenAPI response contracts
</td>
</tr>
</table>

<h2 align="center"><a href="https://assertpy.github.io/assertpy/getting-started/comparison/">Why fluent assertions?</a></h2>

`assert` states a condition well. pytest reports it well.

What it cannot say is *where* two structures differ. It prints both and leaves the reading to you:

```text
assert response == expected
E   AssertionError: assert {'id': 1, ...} == {'id': 1, ...}
E     Omitting 1 identical items, use -vv to show
E     Differing items:
E     {'user': {'name': 'Alice', 'role': 'superadmin'}} != {'user': {'name': 'Alice', 'role': 'admin'}}
E     {'status': 'active'} != {'status': 'disabled'}
```

assertpy names the [exact path](https://assertpy.github.io/assertpy/guides/errors/#rich-pytest-diffs), in color:

<!-- docs-guard: skip -->
```python
assert_that(response).is_equal_to(expected)
```

<p align="center">
  <img src="https://raw.githubusercontent.com/assertpy/assertpy/main/docs/assets/diff-equal.png" width="300" alt="Structured diff in the terminal: user.role shown with its path, removal in red and addition in green">
</p>

It recurses through nested containers. Matcher predicates get the same treatment.

For dynamic fields like IDs, assert a subset with
[`matches_structure()`](https://assertpy.github.io/assertpy/guides/matchers/#structural-matching).

The chain is the other half. Your IDE offers only the
[methods that fit the value](https://assertpy.github.io/assertpy/concepts/type-safety/).

<!-- docs-guard: skip -->
```python
assert_that(items).is_instance_of(list).is_length(3).contains("admin")
```

Matchers are ordinary values that answer `==`, the way `unittest.mock.ANY` does.

Nothing is patched, so a matcher can sit inside the expected structure at any depth:

```python
response = {"id": 7, "user": {"name": "Alice", "age": 30}, "tags": ["a", "b"]}

assert_that(response).is_equal_to(
    {
        "id": match.greater_than(0),
        "user": {"name": "Alice", "age": match.between(18, 120)},
        "tags": ["a", "b"],
    }
)

# or keep the bare `assert`, and pytest's own rewriting reports it
assert response == {
    "id": match.greater_than(0),
    "user": match.ignore(),
    "tags": ["a", "b"],
}
```

The fluent form keeps the path-level diff, the bare form keeps pytest's.

There are [45 matchers](https://assertpy.github.io/assertpy/guides/matchers/), combining with `&`, `|` and `~`.

<p align="center">
  <img src="https://raw.githubusercontent.com/assertpy/assertpy/main/docs/assets/diff-gallery.png" width="640" alt="Structured diffs in the terminal: dict path, list element, set extra/missing, and structural-matcher predicate diffs, side by side">
</p>

<h2 align="center"><a href="https://assertpy.github.io/assertpy/concepts/type-safety/">Type-aware autocomplete</a></h2>

`assert_that()` uses `@overload` to return type-specific Protocols.<br>
Your IDE shows only methods relevant to the value you're testing, not the whole surface:

- `assert_that("hello").` &rarr; string methods: `starts_with`, `matches`, `is_alpha`, ...
- `assert_that(42).` &rarr; numeric methods: `is_positive`, `is_between`, `is_close_to`, ...
- `assert_that(Path("/tmp")).` &rarr; path methods: `exists`, `is_file`, `is_readable`, ...
- `assert_that(my_dict).` &rarr; dict methods: `contains_key`, `contains_entry`, `has_json_path`, ...
- `assert_that(b"\x89PNG").` &rarr; bytes methods: `starts_with_bytes`, `is_valid_utf8`, `decoded_as`, ...

15 type-specific Protocols instead of one `Any`<br>
Works in PyCharm, VS Code, and any editor that runs a type checker

<h2 align="center"><a href="https://assertpy.github.io/assertpy/concepts/type-safety/#typed-narrowing-with-value">Typed narrowing</a></h2>

An assertion hands the value back, statically narrowed.

`is_not_none()` strips `None`, `is_instance_of()` narrows to the class, and `.value` returns it:

<!-- docs-guard: skip -->
```python
order = assert_that(repo.find(42)).is_not_none().is_instance_of(PaidOrder).value
order.refund()  # statically PaidOrder - verified by ty, mypy, pyright and pyrefly
```

For API tests,
[`assert_conforms()`](https://assertpy.github.io/assertpy/concepts/type-safety/#contract-narrowing-with-assert_conforms)
validates a payload against a Pydantic model and narrows to it. `exact=True` catches contract drift:

<!-- docs-guard: skip -->
```python
data = assert_conforms(response.json(), OrderModel).value  # data: OrderModel
```

<h2 align="center"><a href="https://assertpy.github.io/assertpy/guides/errors/#asking-instead-of-asserting">A failure you can read from code</a></h2>

An exception is the right default. Reading the result means catching it.

`check()` runs the next assertion for its verdict instead:

```python
response = {"user": {"name": "Alice", "role": "superadmin"}, "status": "active"}
expected = {"user": {"name": "Alice", "role": "admin"}, "status": "active"}

outcome = assert_that(response).check().is_equal_to(expected)

if not outcome and outcome.diff:
    print(outcome.diff.entries[0].path)  # user.role
```

It is truthy when the assertion held. When it did not, it carries `.message`, `.actual`, `.expected`
and a walkable `.diff`. So does `AssertionFailure`.

So a reporter reads structure instead of parsing a string. That is how the
[Allure integration](https://assertpy.github.io/assertpy/extending/integrations/#allure) works.
Anything else you build can too.

<h2 align="center">Features</h2>

**Fluent API**

- [**Structural matching**](https://assertpy.github.io/assertpy/guides/matchers/#structural-matching): `matches_structure()` for declarative dict/API-response validation
- [**Recursive field assertions**](https://assertpy.github.io/assertpy/guides/assertions/#recursive-field-assertions): `all_fields_satisfy()` / `has_no_none_fields()` apply a predicate to every leaf of an object graph
- [**Universal negation**](https://assertpy.github.io/assertpy/guides/fluent/#universal-negation): `.not_` inverts any assertion, no dedicated `is_not_*` methods
- [**Collection pipeline**](https://assertpy.github.io/assertpy/guides/fluent/#collection-pipeline): `filtered_on()`, `mapped()`, `flat_mapped()`, `first()`, `last()`, `element()`, `single()`
- [**Positional & pairwise checks**](https://assertpy.github.io/assertpy/guides/assertions/#lists): `satisfies_exactly()`, `zip_satisfies()`, `contains_only_once()`, `has_same_size_as()`, plus `*_in_any_order` variants

**Type safety**

- [**Refinement predicates**](https://assertpy.github.io/assertpy/concepts/type-safety/#refinement-narrowing-with-a-typeis-predicate-advanced): `satisfies()` takes a `TypeIs` predicate, so a domain check narrows the chain too
- [**Contract testing**](https://assertpy.github.io/assertpy/concepts/type-safety/#contract-narrowing-with-assert_conforms): `assert_conforms()` validates a raw payload against a Pydantic model and narrows to it. [`exact=True`](https://assertpy.github.io/assertpy/concepts/type-safety/#contract-drift-with-exacttrue) catches contract drift, `each=True` validates list endpoints

**Built-in types**

- [Strings](https://assertpy.github.io/assertpy/guides/assertions/#strings), [numbers](https://assertpy.github.io/assertpy/guides/assertions/#numbers), [lists](https://assertpy.github.io/assertpy/guides/assertions/#lists), [tuples](https://assertpy.github.io/assertpy/guides/assertions/#tuples), [sets](https://assertpy.github.io/assertpy/guides/assertions/#sets), [dicts](https://assertpy.github.io/assertpy/guides/assertions/#dicts), [dates](https://assertpy.github.io/assertpy/guides/assertions/#dates), [booleans](https://assertpy.github.io/assertpy/guides/assertions/#booleans), [objects](https://assertpy.github.io/assertpy/guides/assertions/#objects), [bytes](https://assertpy.github.io/assertpy/guides/assertions/#bytes--bytearray), [files](https://assertpy.github.io/assertpy/guides/assertions/#files), [exceptions](https://assertpy.github.io/assertpy/guides/errors/#expected-exceptions)
- [**Bytes assertions**](https://assertpy.github.io/assertpy/guides/assertions/#bytes--bytearray): `is_valid_utf8()`, `starts_with_bytes()`, `is_hex_equal_to()`, `decoded_as()` for `bytes`/`bytearray`
- [**Dynamic assertions**](https://assertpy.github.io/assertpy/guides/assertions/#dynamic-assertions-on-objects): `has_<name>()` for any attribute, property, or zero-argument method
- [**Dict comparison**](https://assertpy.github.io/assertpy/guides/assertions/#selective-comparison-ignore--include): `is_equal_to(ignore=..., include=...)` for selective key/field matching by name, regex, or type
- [**Recursive comparison**](https://assertpy.github.io/assertpy/guides/assertions/#recursive-comparison-tolerance--custom-comparators): `is_equal_to()` with `tolerance`, `comparators`, or `ignore_null` for nested structures
- [**Extracting**](https://assertpy.github.io/assertpy/guides/assertions/#extracting-attributes-from-objects): flatten collections on attributes with `filter` and `sort` support
- [**Regex group extraction**](https://assertpy.github.io/assertpy/guides/data/#regex-group-extraction): `extracting_group()` and `matches_with_groups()` for regex captures

**Testing**

- [**Soft assertions**](https://assertpy.github.io/assertpy/guides/testing/#soft-assertions): thread-safe and async-safe via `contextvars`, each failure reported with its `file:line`. Group with `sa.group()` or `assert_all()`
- [**Polling assertions**](https://assertpy.github.io/assertpy/guides/testing/#async-assertions): `eventually()` (async) / `eventually_sync()` (blocking) retry for eventual consistency, with a convergence trace on timeout
- [**Expected exceptions**](https://assertpy.github.io/assertpy/guides/errors/#expected-exceptions): `raises().when_called_with()`, walk the cause chain (`caused_by()`, `has_root_cause()`), search an `ExceptionGroup` (`contains_error()`, `errors()`, `error_of()`), or pivot to the object (`raised()`)
- [**HTTP responses**](https://assertpy.github.io/assertpy/recipes/#test-an-http-api-response): assert on the response itself and every failure names the request it came from, with `decoded_as_json()` to step into the body. No client library is a dependency
- [**Snapshot testing**](https://assertpy.github.io/assertpy/guides/testing/#snapshot-testing): an external JSON file, an [inline](https://assertpy.github.io/assertpy/guides/testing/#inline-snapshots) value recorded into the test source, or a [value-tolerant contract](https://assertpy.github.io/assertpy/guides/testing/#contract-snapshots), all updated with `--assertpy-snapshot-update`
- [**OpenAPI response contracts**](https://assertpy.github.io/assertpy/reference/json/#assertpy.json_mixin.JsonMixin.conforms_to_openapi): `conforms_to_openapi()` checks a JSON body against an operation's response schema, reporting every violation with its JSON path

**Failure reporting**

- [**Structured errors**](https://assertpy.github.io/assertpy/guides/errors/#structured-errors): `AssertionFailure` carries `.actual`, `.expected` and `.diff`, and the diff renders into the message, so it shows off pytest too
- [**Assertions as values**](https://assertpy.github.io/assertpy/guides/errors/#asking-instead-of-asserting): `check()` runs the next assertion for its verdict instead of raising, handing back an `AssertionOutcome`
- [**Rich pytest diffs**](https://assertpy.github.io/assertpy/guides/errors/#rich-pytest-diffs): recursive diffs across containers, dataclasses, attrs and Pydantic models, with intra-line carets for strings
- [**Failures that say why**](https://assertpy.github.io/assertpy/guides/errors/#some-failures-say-why-not-only-what): where one fact explains a failure, a line under the message says it. An id the payload holds as text (`7` against `"7"`), a NaN, two instances compared by identity, surrounding whitespace. A failed `contains()` or `is_in()` names the closest row, and forty rows that differ in one field are named as one place

**Plugin for pytest**

Set from the command line or from `[tool.pytest.ini_options]`, not from a call

- [**Failure clustering**](https://assertpy.github.io/assertpy/guides/errors/#what-the-failures-had-in-common): forty failing tests are usually not forty problems. Where three or more differ at the same place, the run ends with a line saying where. On by default, `assertpy_failure_clusters = "off"` turns it off
- [**IDE comparison window**](https://assertpy.github.io/assertpy/guides/errors/#the-comparison-window-of-an-ide): a failed `is_equal_to()` or `has_<name>()` gets PyCharm's "Click to see difference" link, as a plain `assert` does, and the window shows the two values it compared. Under `ignore=` or `include=` those go without the keys left out. The plugin hands them to `pytest_assertrepr_compare`, the hook the IDE's runner listens to. On by default, `assertpy_comparison = "off"` turns it off
- [**Diagnostic profiles**](https://assertpy.github.io/assertpy/guides/errors/#configuration): `assertpy_profile` turns the guards below on in one line. `compatible` (default) leaves them off, `safe` warns, `strict` fails the tests they find. A setting you name yourself still wins
- [**Vacuous-assertion guard**](https://assertpy.github.io/assertpy/guides/assertions/#assertions-that-checked-nothing): `--assertpy-vacuous` warns when a universal assertion passes over an empty collection, having checked nothing
- [**Dangling-assertion detector**](https://assertpy.github.io/assertpy/guides/assertions/#assertions-that-never-ran): `--assertpy-dangling` warns when a chain builds an assertion and never runs it. `assert assert_that(x).is_positive` passes on any value, and neither ruff nor coverage sees it

**Extensibility**

- [**Custom matchers**](https://assertpy.github.io/assertpy/guides/matchers/#custom-matchers): `register_matcher()` composes existing ones, `BaseMatcher` carries its own predicate. Both compose with `&`, `|`, `~`
- [**Custom assertions**](https://assertpy.github.io/assertpy/extending/custom-assertions/): `add_extension()` adds a method to the builder

<h2 align="center"><a href="https://assertpy.github.io/assertpy/extending/integrations/">Integrations</a></h2>

- [**Allure**](https://assertpy.github.io/assertpy/extending/integrations/#allure) (`pip install assertpy[allure]`): the pytest plugin auto-attaches structured diff and actual/expected data to Allure reports, in three configurable modes
- [**Behave**](https://assertpy.github.io/assertpy/extending/integrations/#behave) (`pip install assertpy[behave]`): ready-made parameter types (`PositiveInt`, `NonEmptyString`, ...) for step definitions like `{age:PositiveInt}`
- [**JSON**](https://assertpy.github.io/assertpy/guides/data/#json-path--schema) (`pip install assertpy[json]`): JSONPath navigation (`at_json_path()`, `has_json_path()`) and JSON Schema validation (`matches_json_schema()`)
- [**Data frames**](https://assertpy.github.io/assertpy/extending/integrations/#data-frames-and-arrays) (`pip install assertpy[pandas]` / `[polars]` / `[numpy]`): fluent equality for pandas/polars frames and numpy arrays, carrying each library's own diff

---

<p align="center">
  <a href="https://github.com/assertpy/assertpy/blob/main/LICENSE">BSD 3-Clause License</a>
</p>
