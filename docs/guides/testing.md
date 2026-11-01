# Testing

## Soft assertions

By default a failure halts the test immediately. Soft assertions collect failures and raise them
together at the end, so one run reports every problem.

Each collected failure carries its `file:line`, so you can jump straight to the assertion that failed:

```python
from assertpy import assert_that, soft_assertions

with soft_assertions():
    assert_that("foo").is_length(4)
    assert_that("foo").is_empty()
    assert_that("foo").is_equal_to("bar")
```

??? failure "Collected failures raised at the end of the block"
    ```
    assertpy.AssertionFailure: soft assertion failures:
    1. Expected <foo> to be of length <4>, but was <3>.  [test_str.py:12]
    2. Expected <foo> to be empty string, but was not.  [test_str.py:13]
    3. Expected <foo> to be equal to <bar>, but was not.  [test_str.py:14]
    ```

!!! note
    Only assertion failures are collected. Errors like `TypeError`/`ValueError` and an explicit `fail()`
    halt immediately. Use `soft_fail()` to collect a forced failure. Soft state is thread-safe and
    async-safe (independent per thread and per `asyncio.Task` via `contextvars`).

The message is not the only copy. The raised `AssertionFailure` carries `failures`, one record per
collected failure: values, diff, group label and `(file, line)`. See
[What a soft block hands back](errors.md#what-a-soft-block-hands-back).

An exception raised inside the block still wins, unchanged: same type, message and traceback, so
`except TimeoutError` around the block keeps working. What the block had collected travels with it as a
note:

```text
TimeoutError: service did not answer

soft assertion failures:
1. Expected <1> to be equal to <2>, but was not.  [test_orders.py:14]
```

- On Python 3.10 the note is attached too and readable as `exc.__notes__`, but the traceback does not
  print notes there.
- Current pytest's `match=` searches notes as well, so `pytest.raises(..., match="^service did not answer$")`
  around a soft block stops matching once a note is attached. The message itself is unchanged.

## Grouped soft assertions

Bind the collector with `as sa` and group failures by section with `sa.group(label)`:

```python
with soft_assertions() as sa:
    with sa.group("Headers"):
        assert_that(headers["Content-Type"]).is_equal_to("application/json")
    with sa.group("Body"):
        assert_that(body["status"]).is_equal_to("ok")
```

??? failure "Grouped output"
    ```
    soft assertion failures:
      [Headers]
        1. Expected <text/html> to be equal to <application/json>, but was not.  [test_api.py:37]
      [Body]
        2. Expected <error> to be equal to <ok>, but was not.  [test_api.py:39]
    ```

!!! note
    Soft mode collects *assertion* failures only.

    After a failed `raises()` / `warns()` + `when_called_with()` there is no captured value left to
    assert on, so the rest of that one chain goes inert and is skipped silently. Independent
    assertions that follow are collected as usual.

### assert_all

A convenience wrapper for inline soft assertions, equivalent to wrapping the calls in
`with soft_assertions():`:

```python
from assertpy import assert_all, assert_that

assert_all(
    lambda: assert_that(x).is_positive(),
    lambda: assert_that(y).is_not_none(),
    lambda: assert_that(z).is_length(3),
)
```

## Async assertions

`eventually()` creates a polling assertion that retries until the condition holds or a timeout is
reached, useful for eventual consistency and reactive systems:

```python
async def test_status_converges():
    await assert_that(get_status).eventually().is_equal_to("ready")
```

By default it polls for 5 seconds every 0.5 seconds. Tune with `within()` and `every()`:

<!-- docs-guard: skip -->
```python
await assert_that(get_count).eventually().within(10).every(0.2).is_greater_than(100)
```

Both take seconds as a real number, checked where given (`eventually()`, `eventually_sync()`, `within()`,
`every()`):

- A bool, text or a `Decimal` raises `TypeError`. A negative or NaN one raises `ValueError`.
- An infinite timeout, or one past the float range, waits until the condition holds.
- The interval must be finite. One longer than the time left sleeps only to the deadline, so the poll
  fails on time after one last try.

The subject is a callable, by design. A value is refused: polling it would re-read nothing, and the
library cannot tell an immutable value from a live object. The callable says what to read again, so
`assert_that(lambda: element.text)` asks the element each round.

Both sync and async callables work, and any assertion method is available after `eventually()`:

<!-- docs-guard: skip -->
```python
await assert_that(async_get_status).eventually().is_equal_to("done")
await assert_that(get_name).eventually().starts_with("Al")
await assert_that(get_count).eventually().is_between(10, 20)
```

Every call on the chain, a step like `described_as()` or another assertion, is replayed against a fresh
probe on each poll, and the whole chain is awaited once at the end:

<!-- docs-guard: skip -->
```python
await assert_that(get_order).eventually(timeout=10).is_instance_of(Order).has_status("PAID")
```

Negation is part of that chain too, which is how you wait for something to stop being true:

<!-- docs-guard: skip -->
```python
await assert_that(get_status).eventually(timeout=10).not_.is_equal_to("pending")
```

- The `await` runs the chain: without it nothing is polled. A chain dropped without being awaited raises a
  `RuntimeWarning`, as a dropped coroutine does, and
  [`--assertpy-dangling`](assertions.md#assertions-that-never-ran) reports it from the source.
- Awaiting returns the ordinary builder over the settled value, so assertions after it are plain
  assertions, not a new wait.

By default only a failing assertion is retried, and any other exception from the probe propagates at once.
An `AssertionError` the probe raises itself is retried the same way, which suits a probe that asserts its
own preconditions. The timeout message names its type and count.

When "not ready yet" arrives as an exception, such as a refused connection while a service boots,
list those exception types in `ignoring`:

<!-- docs-guard: skip -->
```python
await assert_that(get_order).eventually(timeout=10, ignoring=ConnectionError).has_status(
    "PAID"
)

# or configure fluently, like within()/every()
await assert_that(get_order).eventually().within(10).ignoring(
    ConnectionError, TimeoutError
).has_status("PAID")
```

!!! note
    Only `AssertionError` (plus any `ignoring` types) is retried. Other exceptions propagate
    immediately. On timeout the last failure is chained for context. `ignoring` accepts only
    `Exception` subclasses, so `KeyboardInterrupt` and friends can never be swallowed.

    Polling itself is always strict, since retrying requires hard failures. Only the final timeout
    failure honors the builder's mode: inside `soft_assertions()` it is collected instead of
    raised, and under `assert_warn()` it is logged.

    The timeout bounds the retries, not a single call. A call in flight is never interrupted, so a
    probe that takes 30 seconds makes a 5-second poll take 30. Bound the call itself, with the timeout
    of the client it uses.

### Synchronous polling

`eventually_sync()` is the same polling assertion without asyncio. Its assertions block the thread (via
`time.sleep`) instead of returning coroutines, so it works in plain tests:

```python
def test_status_converges():
    assert_that(get_status).eventually_sync(timeout=10, interval=0.2).is_equal_to("ready")

# within()/every()/ignoring() work the same way
assert_that(get_order).eventually_sync().within(10).ignoring(ConnectionError).has_status(
    "PAID"
)
```

Retry rules, chaining, negation, soft/warn behavior, and the polling trace are identical to
`eventually()`:

<!-- docs-guard: skip -->
```python
assert_that(get_order).eventually_sync(timeout=10).is_instance_of(Order).has_status("PAID")
assert_that(get_status).eventually_sync(timeout=10).not_.is_equal_to("pending")
```

The probe must be a sync callable: one returning an awaitable raises `TypeError`. Poll async probes with
`eventually()` and `await`.

`asyncio.run()` around `eventually()` works only where nothing else owns a loop in that thread.
Playwright's sync API drives its own loop, and the call fails with `RuntimeError: asyncio.run() cannot be
called from a running event loop`. That is why `eventually_sync()` exists.

### Polling trace

Every poll is recorded, so a timeout failure diagnoses itself instead of just reporting that time ran
out. The message opens with a one-line trend that pins the failure mode:

| Trend line | What it means |
|---|---|
| `probe raised ConnectionError on all 12 polls` | the service never came up |
| `value unchanged across 12 polls` | it converged to the wrong value |
| `value changed 3 times; last change 0.4s before the deadline` | the timeout is too short |
| `value cycles between 2 states across 12 polls` | it keeps returning to earlier values, so waiting longer will not help |
| `value could not be compared across 12 polls` | the probe returns something that cannot be rendered, so movement is unknown |

Counts in that line cover the whole run, not only the samples kept: a long poll drops middle samples, and
a value that moved on all of a thousand polls reads as a thousand. A line about the *shape* of what was
kept says so: `value cycles between 2 states in the 25 polls kept`.

The raised `AssertionFailure` carries the timeline as `.trace`, a [`PollTrace`][assertpy.errors.PollTrace]
of per-poll samples, identical consecutive polls collapsed. The pytest report gets a `Polling Trace`
section: the one-line summary (polls, elapsed time, how the value moved), then every distinct poll with
its offset, repeat count and error or failure:

```text
  t=+0.0s error x2: ConnectionError('boot')
  t=+0.5s fail x2: Expected <PENDING> to be equal to <PAID>, but was not.
  t=+1.5s fail x5: Expected <SHIPPED> to be equal to <PAID>, but was not.
```

- Allure gets the same timeline as a `Polling Trace` JSON attachment, with diffs between consecutive
  distinct samples.
- Samples are point-in-time snapshots, correct even when the probe mutates and returns the same object.
  Long polls keep the first 5 and last 20 samples.
- In soft mode the message keeps the trend line, and a collected timeout keeps its trace as
  `failures[i].trace` on the aggregate. Warn mode logs the message and keeps nothing.
- `trace=False` turns the recorder off per assertion, on `eventually()` and `eventually_sync()`.

What the recorder costs:

- A poll that fails with a value reads it twice: once for the sample, once, whole, to tell whether it
  moved, so a change past the hundredth item is still seen.
- A passing poll, a poll whose probe raised, and a chain settling on its first probe walk nothing.
- So the cost is that of failing polls, growing with the payload: a few microseconds over a scalar, about
  2 ms over two hundred records.

Ten of them, which is what a timeout usually reaches:

| Ten failing polls over | recorder on | recorder off |
|---|---|---|
| a scalar | 118 µs | 85 µs |
| a payload of two hundred records | 22 ms | 1.2 ms |

Turn it off for the rare case of a near-zero interval over a heavy value. The timeout failure then reports
only the last failure.

Steps multiply by polls, since each poll replays the chain: a scalar probe settling on its eleventh call
took 117 µs with one step and 150 µs with five. A failing step ends the poll before the steps behind it,
so put the cheap check that catches the common failure first.

#### Polls that nearly timed out

A poll that converges on its fifth attempt is `eventually()` doing its job, so a retry on its own says
nothing.

Burning most of the budget before converging says a great deal. That run passed, and the next one on a
slower machine will not. Under pytest those are collected across the run and listed at the end:

```text
assertpy polls that nearly timed out:
  tests/test_orders.py::test_status: converged on attempt 41 at 0.81s of 1.0s (81% of the budget)
```

Only polls past 70% of their timeout are named, so a healthy suite prints nothing. The report is
advisory and never fails a run.

Move that bar or turn the report off with `assertpy_poll_report`. A slow CI box converges late on
every poll, where the default turns a signal into a line of noise per run.

```toml
[tool.pytest.ini_options]
assertpy_poll_report = "0.9"  # only polls past 90% of their timeout, or "off" to say nothing
```

Setting it to `off` also stops the samples being collected, so nothing is measured at the poll site.

Polls are attributed to the test that made them, including those a fixture makes in setup or teardown.
Under `pytest-xdist` the workers ship their findings to the controller, which prints the combined list.

### Waiting on a browser

A UI test asks the page before it is ready, and the answer settles a moment later. `eventually_sync()`
takes any callable, so a driver read is a probe like any other.

```python
def test_the_banner_settles():
    reads = iter(["", "", "Welcome, Alice"])  # a page that is not ready on the first two reads

    assert_that(lambda: next(reads)).eventually_sync(timeout=2, interval=0.1).is_equal_to(
        "Welcome, Alice"
    )
```

With a real driver the probe is the read itself. Selenium has no assertions of its own, so this
replaces a hand-written `WebDriverWait` and keeps the failure diagnostics:

<!-- docs-guard: skip -->
```python
assert_that(lambda: driver.find_element(By.CSS_SELECTOR, "#banner").text).eventually_sync(
    timeout=10, ignoring=(NoSuchElementException, StaleElementReferenceException)
).is_equal_to("Welcome, Alice")
```

**Use Playwright's own `expect()` for locator assertions.** It auto-waits, it retries, and it knows
things about the page that a generic poller cannot. What it does not cover is the data behind the
interface, and that is where an assertion library earns its place:

<!-- docs-guard: skip -->
```python
expect(page.get_by_role("heading")).to_have_text("Orders")  # Playwright's job

order = assert_conforms(api.get(f"/orders/{order_id}").json(), OrderModel).value
assert_that(order.total).is_close_to(page_total, 0.01)      # ours
```

The same split applies to Selenium once you leave the DOM: assert the page with the driver, assert the
payload, the database row or the extracted structure with `assert_that()`.

## Snapshot testing

Capture a data structure to disk as JSON and compare against it on every run.

```python
assert_that({"a": 1, "b": 2, "c": 3}).snapshot()
```

On the first run the snapshot file is created, a `SnapshotCreatedWarning` is emitted, and the test
passes. On later runs the value is compared to the stored snapshot and the test fails on any mismatch.

Supported: `dict`, `list`, `set`, objects, numbers, `None`, `complex`, `datetime`/`date`/`time`,
`Decimal` and `bytes`. Commit the `__snapshots` folder to source control.

!!! note
    The capture warning makes a first run visible. Without it a wrong first capture would silently
    become the reference.

    Under `-W error` (or `filterwarnings = ["error"]`) a new capture fails explicitly, which is
    usually what you want in CI.

### One id per case

Without an `id`, a snapshot is keyed by the line of the call. All cases of a parametrised test share that
line, so the first case stores its value and the rest are compared against it.

```python
@pytest.mark.parametrize("name", ["alice", "bob", "carol"])
def test_user(name):
    assert_that(load(name)).snapshot(id=f"user-{name}")  # without the id, all three share one key
```

A shared key fails loudly when the values differ. When they agree it passes silently, asserting one case
out of many, so a `SnapshotKeyReusedWarning` names the key and the line as soon as a second test reaches
it. Raise it to an error if you would rather not rely on reading warnings:

```toml
[tool.pytest.ini_options]
filterwarnings = ["error::assertpy.SnapshotKeyReusedWarning"]
```

What counts is two *tests* on one key, not two calls. A helper snapshotting twice in one test asserts both
values silently. If the second call fails, the failure says why the two values were compared:

```text
Expected <{'user': 'bob'}> to be equal to <{'user': 'alice'}>, but was not. This test reached
<__snapshots/snap-helper.json> more than once, so the value above was compared against what an
earlier call in the same test stored. Give each call its own snapshot(id=...).
```

Under `pytest-xdist` the cases of one parametrised test may land on different workers, where no single
process sees the second one, so that split is caught by a sweep at the end of the run instead.

### Updating snapshots

Run pytest with `--assertpy-snapshot-update` and every failing snapshot comparison overwrites the
stored value instead of failing.

- Each overwrite emits a `SnapshotUpdatedWarning`, so the run reports which snapshots changed.
- Matching snapshots are left untouched.
- The comparison options (`ignore`, `tolerance`, ...) decide whether a snapshot is stale.

```bash
pytest --assertpy-snapshot-update
```

For runners other than pytest, set `ASSERTPY_SNAPSHOT_UPDATE=1`. Deleting the snapshot files and
re-running works too, each fresh capture emitting a `SnapshotCreatedWarning`.

### CI mode

A first run *creates* a missing snapshot and passes. In CI that means a golden that was never committed is
created in the throwaway workspace, the test passes, and drift detection is silently off.

Enable CI mode to make a missing snapshot a hard failure instead:

```bash
pytest --assertpy-snapshot-ci
```

- It turns on by itself when a `CI` environment variable is set, or with `ASSERTPY_SNAPSHOT_CI=1`.
- `--assertpy-snapshot-no-ci` or `ASSERTPY_SNAPSHOT_CI=0` turns the autodetection off.
- Local runs are unaffected.

### Obsolete snapshots

When a test is deleted its stored snapshot lingers on disk. At the end of a run assertpy reports
snapshots it did not touch:

```text
assertpy snapshots:
  obsolete snapshot: __snapshots/snap-test_orders.json::42
  obsolete snapshot file: __snapshots/snap-test_legacy.json
```

Each line carries a short hint on how to remove it. Reporting is always safe.

Removal is conservative:

- An obsolete sub-snapshot (a line-number key in a file whose module still ran) is pruned only under
  update mode on a *full* run, so a run narrowed by `-k`, `-m`, `--lf` or `--ff` never deletes a snapshot
  whose test was merely deselected.
- A whole obsolete file is only reported, never deleted.
- Under `pytest-xdist` the workers' touched snapshots are merged on the controller first, so a snapshot
  used on another worker is never taken for an orphan.

### Inline snapshots

An inline snapshot keeps the expected value **in the test source**. Call `matches_inline()` empty, record
once with `--assertpy-snapshot-update`, and the literal is written into the call:

```python
# before recording
assert_that(client.get("/orders/1").json()).matches_inline()

# after `pytest --assertpy-snapshot-update`
assert_that(client.get("/orders/1").json()).matches_inline(
    {"id": 1, "status": "paid"}
)
```

Later runs compare against the literal, and update mode overwrites it on drift, just as `snapshot()`
does. The same selective knobs apply, so volatile fields never make the snapshot brittle:

```python
assert_that(order).matches_inline(
    {"id": 0, "total": 42.0}, placeholders={"id": match.is_uuid()}, tolerance=0.01
)
```

A recorded literal holds the value captured on that run, so a placeholder field shows the captured `id`
rather than the `0` above. The placeholder governs the comparison, not what is written.

Recording needs the `[inline]` extra (`pip install assertpy[inline]`). The **comparison** does not.
Below Python 3.11 a call written inside an `assert` statement, which pytest rewrites, cannot be found
to record, and one given its value through `**` may not be found either, depending on the platform.
Write `matches_inline()` on a line of its own there, with its literal in the call.

It is a plain equality check, so it runs under `pytest-xdist` and needs no source introspection or
assertion rewriting.

Under xdist, the recorded edits go to the controller and are applied once. A literal is written only if
every worker that ran the call accepts it. A worker that saw another value, or whose comparison rejects it,
stops the write, and the run says to record that call with `-n 0`.

One call holds one literal, so every case reaching it must accept it: the cases of a `parametrize`, the
turns of a loop.

- A case accepts a literal its own comparison passes, so cases differing only in an ignored field share one.
- If no literal satisfies them all, nothing is written and the run fails, naming the call and the values.
  Give each case its own call, or use `snapshot()`, which keys every case apart.
- The case that asked for a literal must accept it too. Under a comparator or tolerance by which the value
  is not equal to itself, nothing is written and the run fails saying so.

When cases are asked:

- When it runs, a case is asked about every literal its call has been asked for so far.
- A case compared by plain data (a literal value, options without functions) is also asked at the end of
  the run about literals later cases asked for, with its value and options as they were when it ran, so
  a `dict` the test changes afterwards does not move it.
- A case holding a comparator function, or a value that is not a literal, takes only literals asked for by
  the time it ran.

Literal details:

- A case is asked about the literal as Python builds it, so equal parts such as the two tuples in
  `((1, 2), (1, 2))` are one object, as at test time. Python also shares them with equal constants
  elsewhere in the file, so a comparator that compares by identity may answer differently next run.
- A recorded `set()` or `frozenset({...})` means Python's own types. A test that rebinds either name fails
  on the written call next run.

Where a literal is written:

- Only into files under pytest's rootdir, never under `site-packages` or `dist-packages`: a call there
  belongs to an installed package.
- Only into the text the call was found in. A file edited during the run is left alone and named.
- In the file's own encoding and line ending.

- A literal is written only into the call it was recorded from.
- The expected value must already be a literal: `matches_inline(EXPECTED)` is refused under update mode,
  since a literal in its place would stop the test reading the constant.
- Under `not_` nothing is recorded: the literal would be the value the negation must differ from.
- Only JSON-ish literals work: a `dict`, `list`, `tuple` or `set` of scalars. For a `datetime`, `Decimal`,
  `UUID` or a custom object use `snapshot()`, which shares the update flag, CI mode, selective comparison
  and structured diff.

### Custom types

For a type beyond the built-in codec (`set`, `complex`, `datetime`/`date`/`time`, `Decimal`, `bytes`,
`UUID`, `Enum`), register a serializer so `snapshot()` round-trips it instead of raising:

```python
from assertpy import register_snapshot_serializer
import pathlib

register_snapshot_serializer(pathlib.PurePath, str, pathlib.PurePath)
```

Matching is by `isinstance`, subclasses included. The registry is consulted before the built-ins, and
a later registration wins.

The `decode` half runs your own code on load, so it is a trusted, explicit opt-in. The automatic
instance decode never imports anything.

### Contract snapshots

`snapshot()` compares exact values, so a response full of generated ids and timestamps needs `ignore`
or `placeholders` to stay stable.

For the response's *shape* rather than its values, use `matches_contract_snapshot()`. It records paths and
type categories, never values, and fails only on **structural** drift: a field added, removed or retyped.

```python
assert_that(response.json()).matches_contract_snapshot()
```

It is value-tolerant by construction, so dynamic ids, timestamps, and amounts (and `5` vs `5.0`) change
freely. A real contract change fails with the drifted paths:

```text
Expected <{...}> to match contract snapshot, but the structure drifted:
  + promo_code
  ~ id number -> str
Contract snapshot <...>; rerun with --assertpy-snapshot-update to accept the new shape.
```

- No model is needed: the contract is inferred from the first response. Storage, update mode and CI mode
  are those of `snapshot()`.
- With a pydantic model at hand, use
  [`assert_conforms(..., exact=True)`](../concepts/type-safety.md#contract-drift-with-exacttrue) instead.
- One observation cannot tell which fields are optional, so a field that is legitimately sometimes absent
  reads as `removed`. Re-record with update mode when the contract really changed.

### Shape placeholders

`comparators` and `ignore` make the *comparison* tolerate volatile fields, but the golden still stores the
first run's value. `placeholders` stores a shape token instead, and asserts the shape on every run:

```python
from assertpy import match

assert_that(response).snapshot(
    id="order",
    placeholders={
        "id": match.is_uuid(),
        "created_at": lambda ts: isinstance(ts, str),
    },
)
```

- The golden reads `"id": {"__placeholder__": "a valid UUID string"}` instead of a specific id.
- Each run asserts the field is present and satisfies the matcher (a `Matcher` or a callable predicate),
  including the run that creates the snapshot and an update that rewrites it. A field failing its
  placeholder fails the run, and nothing is written.
- Every other field is compared exactly, so drift outside the placeholders is caught.
- Placeholders apply to top-level keys of a *dict-like* value and combine with `ignore`.

### Parameters

Snapshots are keyed by test filename plus line number by default. Override with `id` or `path`:

```python
assert_that({"a": 1}).snapshot(id="my-custom-id")
assert_that({"a": 1}).snapshot(path="my-custom-folder")
```

### Volatile fields and float noise

The comparison takes the options of `is_equal_to()`: `ignore`, `include`, `tolerance` and `comparators`.
The file always stores the full value, and the options only shape the comparison:

```python
assert_that(api_response).snapshot(
    id="order", ignore=["created_at", ("user", "session_id")]
)
assert_that(metrics).snapshot(id="latency", tolerance=0.001)
assert_that(payload).snapshot(
    id="user", comparators={"name": lambda a, e: a.lower() == e.lower()}
)
```

### Known limitations

Beyond the JSON natives, these types survive a round-trip:

| Type | Stored as |
|---|---|
| `set` | a tagged list |
| `complex` | a tagged pair |
| `datetime` / `date` / `time` | ISO text, microseconds and timezone kept |
| `Decimal` | exact text, never a float |
| `bytes` / `bytearray` | base64, both compared as `bytes` |
| `uuid.UUID`, `Enum` members | their canonical text form |
| any object with a `__dict__` | its attributes |

Anything else raises `TypeError` on capture. Teach the codec with
[`register_snapshot_serializer()`](#custom-types), which is what a `frozenset` or a domain class needs.

Three more things worth knowing:

- **A tuple comes back as a list**, since JSON has no tuple. A snapshot of `(1, 2)` compares as
  `[1, 2]` on the next run and fails, so convert tuples before snapshotting.
- **Snapshot ids are case-insensitive.** Filenames are lower-cased, so two ids differing only by case
  land in one file.
- **The write lock is not crash-safe.** A process killed mid-write leaves a stale `.lock` beside the
  snapshot. Delete it if snapshot writes start timing out.
