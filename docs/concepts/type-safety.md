# Type Safety

Type safety is what sets assertpy 2 apart from assertpy 1.x and most alternatives. `assert_that()` is
overloaded, so the value you pass decides which assertions you get back: a *type-specific* set, not one
generic `Any`.

```python
assert_that("hello").starts_with("he")  # string assertions
assert_that(42).is_positive()           # numeric assertions
assert_that([1, 2, 3]).contains(2)      # collection assertions
```

Your editor offers only the methods that fit the value, and a type checker rejects misuse before the
test ever runs.

## Type-aware autocomplete

Each value type gets its own typed Protocol, with a generic fallback for anything else. Your editor
then suggests only what fits the value under test rather than the whole surface:

| Value type | You get | Such as |
|---|---|---|
| `str` | string assertions | `starts_with`, `matches`, `is_alpha`, `is_lower` |
| `int` / `float` | numeric assertions | `is_positive`, `is_between`, `is_close_to` |
| `complex` | zero and the core, and no more | `is_zero`, `is_not_zero` |
| `list` / `tuple` / `set` / `frozenset` | collection assertions | `contains`, `contains_exactly`, `is_sorted`, `extracting` |
| `dict` | dict assertions | `contains_key`, `contains_entry`, `has_json_path` |
| `datetime.date` | date assertions | `is_less_than`, `is_greater_than`, `is_between` |
| `datetime.datetime` | the same, plus the chronological ones | `is_before`, `is_after`, `is_close_to`, `is_equal_to_ignoring_time` |
| `pathlib.Path` | path assertions | `exists`, `is_file`, `is_directory`, `is_readable` |
| `bytes` / `bytearray` | bytes assertions | `starts_with_bytes`, `is_valid_utf8`, `decoded_as` |
| a pandas or polars frame | frame assertions | `is_frame_equal`, `is_array_equal`, plus size, membership and iteration |
| a numpy array | array assertions, a zero-dimensional array included | `is_array_equal`, `is_array_close_to`, plus the same three |
| a numpy scalar | `np.float64` the `float` view, since it subclasses `float`, and any other the plain-class view below | `is_greater_than`, `is_close_to`, `is_zero` |
| any callable | callable assertions | `raises`, `warns`, `eventually` |
| a plain class | the core, plus structural matching and an ordering that refuses nothing | `is_greater_than`, `is_between`, `matches_structure` |

An assertion hands back the same view it was reached from, so the suggestions stay relevant from the
first call to the last.

Two kinds of step break that on purpose:

- a pivot such as `first()`, `mapped()` or `decoded_as()` hands back a view of what it produced
- `check()` reports a verdict instead of chaining

## Misuse caught before the test runs

Because each overload is typed, a type checker flags an assertion that does not apply to the value, or an
argument of the wrong type, without running anything:

<!-- docs-guard: type-error -->
```python
# type error: is_positive is not a string assertion
assert_that("foo").is_positive()
# type error: expected `type`, got `str`
assert_that(42).is_instance_of("int")
```

The same holds for a relation between two values. An argument is bound to the type of the value under
test, so a comparison that could never hold is a type error, not a runtime failure:

<!-- docs-guard: type-error -->
```python
assert_that([1, 2, 3]).contains("four")            # an item that cannot be in a list of int
assert_that({"id": 1}).contains_key(3.14)          # a key that cannot be in a dict[str, int]
assert_that(1).is_greater_than("wrong type")       # a number against text
assert_that(date.today()).is_before(5)             # a date against a number
assert_that(1).satisfies(match.starts_with("a"))   # a matcher built for another type
```

The ordering assertions have a limit. A number against text is caught because a numeric value reaches a
numeric view whose operand is bound. A value that reaches no view of its own keeps ordering with an
operand of any type, and nothing there is refused.

```python
def what_a_checker_allows(anything: object, someone: Person) -> None:
    assert_that(anything).is_greater_than("text")   # accepted: `object` claims no ordering of its own
    assert_that(someone).is_between(1, 10)          # accepted: so does a class with no view
```

Both type-check, and both raise at runtime with the library's own refusal rather than the operator's:

```text
given other arg must be comparable with val <...> (object), but was <'text'> (str)
val must be a number or a date, which is what an ordering is defined for, but was <...> (Person)
```

That is deliberate. Binding the operand to a list of types rejected `numpy.int64`, which the library
supports. No annotation can name the capability an ordering needs, so the choice was between refusing
correct comparisons and accepting wrong ones, and refusing correct code is the worse of the two.

An `int` against a `float`, a matcher where an item is expected and every other ordinary combination keep
working. Which relations are refused is measured, not asserted:
[`tests/typing_cases.py`](https://github.com/assertpy/assertpy/blob/main/tests/typing_cases.py) holds the
spellings tried, and CI compares all four checkers against a recorded baseline in both directions.

[ty](https://github.com/astral-sh/ty), [mypy `--strict`](https://github.com/python/mypy),
[Pyright](https://github.com/microsoft/pyright) and [Pyrefly](https://github.com/facebook/pyrefly) all
report these in the editor and in CI, turning a class of test bugs into errors you see while typing.

- Every public `assert_that` overload is pinned by an `assert_type` check in
  [`tests/test_typing.py`](https://github.com/assertpy/assertpy/blob/main/tests/test_typing.py).
- CI runs four checkers against that file on every push, with **zero suppressions**. A changed or broadened
  return type fails the build.
- `ty` also checks the whole package.

!!! note "Callables and captured values stay typed too"
    `assert_that(func).raises(...).when_called_with(...)` exposes string assertions on the captured
    message. `returned()` and `raised()` hand back a builder whose `.value` is typed as the call's
    declared return and as the exception caught. That builder offers every assertion rather than the
    view of the value's type. See [Errors & Reporting](../guides/errors.md#expected-exceptions).

### Where the typed surface ends

A value the library cannot see a use for gets the core surface, not every assertion there is. So a
numeric assertion on a user class is a type error rather than a runtime one:

<!-- docs-guard: type-error -->
```python
assert_that(person).is_positive()   # type error: a plain class has no numeric assertions
```

"Cannot see a use for" is meant literally, and it is narrower than it sounds:

| | |
|---|---|
| **keeps the whole surface** | a value with a type of its own, which reaches its own protocol as it always did |
| | a value that answers to something the library uses: an iterable of your own, an HTTP response from any client, a pydantic-style model, a dataclass, a mapping that is not a `dict` |
| | anything typed `Any`, which is what an unannotated helper or a `json.loads()` result gives you |
| **gets the core surface** | a value annotated `object`, and a class that answers to nothing |

The second row errs on purpose. A class that defines `__iter__` for a reason of its own keeps every
assertion name, numeric ones included: a value the library might use keeps everything, and only a value it
certainly cannot use is narrowed. Erring the other way would reject calls that work, which is worse.

[Dynamic assertions](../guides/assertions.md#dynamic-assertions-on-objects) (`has_<attribute>()`) are
resolved at runtime from the value itself, so no overload can declare them ahead of time. They are
outside the typed surface by design, and a checker accepts them only where the value keeps the full
builder:

<!-- docs-guard: type-error -->
```python
assert_that(person).has_first_name("Fred")   # type error: a plain class has no dynamic assertions
```

The runtime accepts it, and only the checker differs. On a value with its own overload, use
`# type: ignore[attr-defined]` or the typed equivalent, for a dict [`contains_entry()`](../guides/assertions.md#dicts):

```python
assert_that({"first_name": "Fred"}).contains_entry({"first_name": "Fred"})
```

This is the cost of keeping the assertpy API unchanged. For a checker to accept `has_first_name` on a
dict, `_DictAssertion` would need a `__getattr__`, and that same declaration would stop it reporting
`contins_key` as a typo.

[Custom assertions](../extending/custom-assertions.md) registered with `add_extension()` sit on the same
line, for the same reason. The name is attached at runtime, so it reaches a checker through that one
`__getattr__` and nowhere else:

<!-- docs-guard: type-error -->
```python
assert_that(order).is_paid()  # type error: a plain class has no dynamically attached names
assert_that(5).is_5()         # type error: _NumericAssertion has no attribute is_5
```

Both lines run. An extension needs `# type: ignore[attr-defined]` at each call site, and the return
type a checker infers for it is `Any` rather than whatever the extension actually returns.

A checker accepts a dynamically attached name only where the value keeps the full builder, which is
narrower than either half of the example above:

- not a `list` or a `dict`, which have overloads of their own
- not a plain class, which has no capability
- what is left is a value with a capability and no overload, such as an iterable of your own or a
  mapping that is not a `dict`, and anything typed `Any`

## Typed narrowing with .value

The `value` property ends a chain by returning the checked value as-is, typed.

For object- and union-typed values, two assertions refine the static type on the way: `is_not_none()`
removes `None`, and `is_instance_of()` narrows to the checked class. No `assert x is not None` or `cast()`
is needed:

```python
order: Order | None = repo.find_order(42)

paid = assert_that(order).is_not_none().is_instance_of(PaidOrder).value
paid.refund()  # statically typed as PaidOrder, no cast, no bare assert
```

Alternatives narrow too, up to three of them, written as a tuple or as separate arguments:

```python
found = assert_that(order).is_instance_of((PaidOrder, Order)).value
either = assert_that(order).is_instance_of_any(PaidOrder, Order).value
```

Both give `PaidOrder | Order`. The same alternatives written as a union, `PaidOrder | Order`, are
accepted and do not narrow: the chain keeps the type it already had. The union reaches the assertion as
one `types.UnionType` value, and the only annotation that binds its members also accepts type
expressions `isinstance` refuses, such as `Literal[1]`.

On the per-type protocols `value` returns the family type (`str` for string assertions, `dict` for
dict assertions, ...), so extract-and-continue works after pivots too:

```python
name = assert_that(b"fred").decoded_as().is_length(4).value  # typed as str
```

Collection assertions are generic over the element type, so `first()`, `last()`, `element()` and
`single()` narrow the chain to the element, and a list of models stays typed all the way down:

```python
orders: list[Order] = repo.all_orders()
# first()/last()/element()/single(): Order
total = assert_that(orders).first().value.total
# re-typed to list[float]
mapped = assert_that(orders).mapped(lambda o: o.total).value
```

AssertJ approximates this at runtime with `asInstanceOf(InstanceOfAssertFactories...)`. Here the
narrowing is static, checked by ty, mypy, Pyright and Pyrefly, and costs nothing beyond returning the value.

!!! note "The narrowing is sound in every mode"
    `.value` never hands back a value that contradicts its narrowed type, in every mode, not just strict:

    - **Strict** (the `assert_that` default): a failed `is_not_none()` or `is_instance_of()` halts the
      chain before `.value` is reached, so the value genuinely matches the narrowed type.
    - **Soft / warn** (inside [`soft_assertions()`](../guides/testing.md#soft-assertions) or under
      `assert_warn()`): a failure is *collected* instead of halting, so `.value` would read past an
      unestablished fact. It **raises** `TypeError` instead, and a pivot like `first()` or
      `extracting()` rejects the untrusted value on its own input check.
        - `.val`, the name a polling chain hands its value back under, refuses the same way.
        - Both refusals name the failure that caused them.
        - `check()` answers rather than refusing, since a verdict is what it promises: it hands back
          `AssertionOutcome(passed=False)` carrying that failure.

    Either way nothing unsound escapes: in soft mode you get an exception, never a wrong-typed value.
    Read `.value` in strict mode, or after the soft block has closed.

    A **negated** assertion narrows nothing: `not_.is_not_none()` says the value *is* `None`, so what
    comes back keeps the type it already had.

    A refinement hands back the view `assert_that()` would give the refined type, so `is_not_none()` on a
    `str | None` continues as a string. A class the library does not name continues on the core surface,
    since there is no per-type protocol to hand back.

    Under `ty` the numeric and sequence refinements come back gradual rather than as their view, so the
    chain accepts everything from there on instead of narrowing.

### Refinement narrowing with a TypeIs predicate (advanced)

`satisfies()` extends narrowing to **your own** predicates: one typed with
[`TypeIs`](https://peps.python.org/pep-0742/) narrows the chain to the guarded type. Unlike
`is_instance_of()`, which narrows by class only, it narrows by any runtime condition:

```python
from typing_extensions import TypeIs  # or `from typing import TypeIs` on Python 3.13+

def is_paid(order: Order) -> TypeIs[PaidOrder]:
    return isinstance(order, PaidOrder) and order.status == "PAID"

paid = assert_that(order).is_not_none().satisfies(is_paid).value
# statically typed as PaidOrder, narrowed by a domain predicate, not just a class
paid.refund()
```

At runtime `satisfies()` just runs the predicate. The narrowing is purely static.

`is_not_none()` above is part of the assertion, not needed for narrowing. A concretely typed value
refines just as well:

```python
def is_paid_order(payload: object) -> TypeIs[PaidOrder]:
    return isinstance(payload, PaidOrder)

order: dict[str, Any] = response.json()
paid = assert_that(order).satisfies(is_paid_order).value   # statically PaidOrder
```

!!! warning "Checker support: not yet in PyCharm"
    **ty, mypy, Pyright and Pyrefly** solve this narrowing today, so it works in VS Code / Pylance and in CI.

    **PyCharm does not yet solve type variables through `TypeIs`.** There the result stays the
    un-narrowed type, and reading a narrowed-only member reports a false *Unresolved attribute
    reference*. It is tracked upstream in
    [JetBrains PY-89124](https://youtrack.jetbrains.com/issue/PY-89124). When that ships, the narrowing
    lights up in PyCharm with no change here.

    Until then, on PyCharm:

    - prefer `is_instance_of()` for class narrowing (which PyCharm *does* narrow)
    - treat `satisfies()`-based refinement narrowing as advanced / checker-dependent
    - don't disable the *Unresolved attribute reference* inspection to work around it, since it is a
      core check. Scope any workaround to the specific line.

### Contract narrowing with assert_conforms

`is_instance_of()` narrows a value that is *already* an instance. `assert_conforms()` **validates a raw
payload against a pydantic v2 model and continues over the validated instance**, narrowing the chain to
that model: parse, validate and type in one step.

<!-- docs-guard: skip -->
```python
from pydantic import BaseModel

from assertpy import assert_conforms, assert_that

class Order(BaseModel):
    id: int
    total: float

# .value: Order (validated and coerced)
order = assert_conforms(response.json(), Order).value
assert_that(order.total).is_greater_than(0)
```

`assert_conforms(payload, Order)` runs `Order.model_validate(payload)`: on failure the assertion fails
with pydantic's validation errors. On success it returns a builder over the validated, coerced
instance, so `.value` hands back a typed `Order`. It needs pydantic installed.

`assert_conforms` is a **function**, not a builder method, on purpose:

- A method (`assert_that(payload).conforms_to(Order)`) narrows only when the payload's own static type
  does, so the `Any` of `response.json()` would stay `Any` and a `dict`-typed payload would stay `dict`.
- The function takes its return type from `model`, so it narrows to `Order` for **every** input, `Any`
  included.
- It yields a class-narrowed builder, as `is_instance_of()` does, so the narrowing works in PyCharm too.

A **list endpoint** (a JSON array of objects) validates element-by-element with `each=True`, narrowing
the chain to `list[Order]`:

```python
orders = assert_conforms(response.json(), Order, each=True).value  # .value: list[Order]
assert_that(orders).extracting("total").contains(199.0)
```

`each=True` validates every item against `Order`, reporting `item [i]` on the first that fails, and
composes with `exact=True` for per-element drift (drift paths are prefixed with the element index, e.g.
`[3].promo_code`).

### Contract drift with `exact=True`

`model_validate` **silently drops** fields the model does not declare, so a stale model keeps passing
after the live API grows new fields: the test is green while the contract has drifted.

`exact=True` catches that: it fails when the payload carries any field the model does not declare,
in the models, dataclasses and `TypedDict`s the payload became inside lists, tuples, sets, dicts, unions
and root models, reporting the exact paths. A model inside a container of plain values is not reached (see
below).

```python
# response grew a `promo_code` field, and its nested customer grew `loyalty_tier`
assert_conforms(response.json(), OrderModel, exact=True)
```
```text
Expected <{...}> to conform exactly to <OrderModel>, but it carries 2 undeclared field(s)
the model does not declare: ['customer.loyalty_tier', 'promo_code']
```

The failure carries the same finds as a [structured diff](../guides/errors.md#paths-a-program-can-follow),
one entry per undeclared field with the value the payload sent there:

<!-- docs-guard: skip -->
```python
try:
    assert_conforms(response.json(), OrderModel, exact=True)
except AssertionFailure as failure:
    for entry in failure.diff.entries:
        print(entry.path, entry.actual, [step.value for step in entry.steps])
# customer.loyalty_tier gold ['customer', 'loyalty_tier']
# promo_code SPRING ['promo_code']
```

- Each entry has `absent == "expected"`.
- Its `steps` lead into the payload by the keys the walk read, so by the alias where the path names the
  field.
- Where a field holds JSON text, a step of kind `json` carries what the text decodes to, and the steps
  after it lead on from there.
- A part that cannot be checked is a single entry holding that part, with the reason in `expected`.

What the check reads, in short:

| Part of the payload | How it is read |
| --- | --- |
| the keys of every model, dataclass and `TypedDict` it became | as the payload sent them, aliases included |
| a plain dict or list a validator changed in place | as it was sent, put back for the check |
| items a validator filtered, wrapped into a list or gathered into a set | validated again by the one class they became, or by the type the field declares |
| a part no reading pairs with what it became | not guessed: the check fails with `<path> cannot be checked` |
| keys a validator renames, items it rewrites without changing their count | not seen: read under the name and at the position the payload sent |
| a dict one of several declared `TypedDict`s built | followed as whichever declares it, and a key it lost fails with `cannot be checked` |
| a model inside a container of plain values | not reached |

The details behind each row follow.

#### What counts as drift

- It is alias-aware: the key a field was read from is not mistaken for drift. Another spelling of that
  field is, since pydantic drops it like any other key: its name sent beside the alias, the later of two
  alias choices, a name the config does not read by, the key a path starts at where the path leads
  nowhere. The failure names it and says where the field was read from.
- It respects a model that opts into extras (`model_config = ConfigDict(extra="allow")`).
- It reports only structural drift, undeclared fields, and not type coercions. A `datetime` field
  legitimately arrives as a JSON string, so flagging coercions would be noise.

#### Beside pydantic's own `extra="forbid"`

pydantic 2.12 and later forbids extras for one call too,
`Model.model_validate(payload, extra="forbid")`, and names each one in its validation error. Where that
is all a test needs, it is the simpler tool. `exact=True` differs in what it leaves alone and in what it
still sees:

- It keeps a model's own `extra="allow"`, which the per-call setting overrides.
- It does not change which member of a union validates, where forbidding extras makes a member with an
  extra key fail.
- It finds a key a validator removed from the payload in place, which validation no longer sees.
- It hands the validated instance on to the chain.
- It works on every pydantic 2 release.

#### A container validation reshaped

Where validation reshaped a container, its raw items no longer pair one by one with the items built from
it. Two readings still check them.

Every built item is one model class, as in a set, a list a validator filtered, or an object a validator
wrapped into a list. Each raw item is validated again on its own by that class and checked beside what it
becomes:

- That runs the class's validators once more for those items, so a validator with side effects runs
  twice.
- The items are the ones the payload sent. In a filtered list, an item the validator dropped is checked
  too.
- A model read from JSON text (`Json[...]`) is checked against the original JSON input.

A validator left no built item to tell, as in a list it emptied. The raw items are checked against the
type the field declares: validated again as that type, in its model's config, and what that builds is
checked:

- The validators of the field itself are not run again, so one that would have built the items otherwise
  (another class, a subclass of the declared one, renamed keys) is not seen.
- The validators of the item's model do run for them, a second time where the field emptied the list
  after validating it.
- Where the field's validators could have decided what the items became, it fails with
  `cannot be checked`, on a clean payload too. That is so for items pydantic will not build the declared
  type from, and for a union of two or more types besides `None` or a named type alias, in the declared
  type or in a model built from it.

An extra that a typed `__pydantic_extra__` built and a validator then removed from the model is checked
the second way: validated again as the declared type and checked beside what that builds, or refused
with `cannot be checked` where the declared type is a union of two or more types. Untyped extras are the
model's to keep or drop.

#### What cannot be checked

Where neither reading works, it fails with `<path> cannot be checked:` and the reason rather than guess:

- items of mixed model classes in a set or a resized list
- an item that validates only through its parent
- dict keys merged by coercion
- a generator consumed during validation
- an `Iterable[Model]` validated lazily

A part in which no key can hide (a number, text that is not JSON, a model passed as is) is never refused.

#### The payload as it was sent

It reads the payload as it was sent:

- Where the model runs its own code during validation (a validator, `model_post_init`, a custom
  `__init__`), the payload is kept before validation.
- Plain dicts and lists that code changed in place are put back for the check, then returned to what
  validation left. A validator that pops a key is read like one that returns a copy without it.
- A dict or list subclass changed in place is not put back.

#### What it does not see

- What a validator does to bridge the payload to the model. A key it renames is reported under the name
  the payload sent, and items it reorders or rewrites without changing the size of their container are
  read by position.
- A validator that drops built items of one member of a union. It is read as if every raw item became
  the class the remaining ones became.
- A model a validator puts inside a container of plain values (`list[Any]`, `dict[str, int]`), and a
  model inside a class that is neither a model nor a dataclass. It follows the models where a field's
  type can hold one, and under `Any`.

#### Dataclasses

A dataclass, pydantic's or a plain one, is checked like a model: a key for every field its `__init__`
takes is declared, an `InitVar` among them and a field with `init=False` not, and what its fields hold
is followed. Its keys and aliases are read off the schema pydantic built.

#### `TypedDict`s

A `TypedDict` is checked for its own keys, and its values are followed, as the schema pydantic built
declares them. That holds where its annotation is text (`from __future__ import annotations`) and where
a type variable of a parametrized one stands for it.

A `TypedDict` builds a plain dict, which does not say what built it, so what the field declares decides
how the dict is read:

| The field declares | The dict is read as |
| --- | --- |
| a `TypedDict` beside types that never build a dict (`Point` or `int`, `Point` or `None`) | that `TypedDict` |
| several (`Point` or `Other`) | the one left once each whose `Literal` fields do not hold what the dict holds is ruled out, so a tag tells them apart, with a discriminator or without |
| several of which more than one is left, or one beside a type that may build a dict too (`dict[str, int]`, `Any`, a custom type) | not guessed: the check does not say which one validation took |

Ruling one out by its tag is done only in a model that runs no code of its own, since a validator can
rewrite the tag after the fact.

A `TypedDict` held in a `deque`, an `OrderedDict` or a named tuple, or declared beside a `deque`, is not
guessed either: the check takes those for types that may build a dict.

Where the check does not guess:

- A clean payload passes.
- A key the payload sent that the built dict lost fails with `<path> cannot be checked`. So does a field
  two of the types read from different keys, when the payload sends both.
- A key read through an alias is not lost.
- A field's name sent beside its alias is not named, as it is when the check knows which `TypedDict` built
  the dict: the built dict holds that name either way.
- What the dict holds is followed as each declared type says.

## Set up your type checker

Under mypy, one setting decides whether any of this reaches your tests. mypy does not look inside a
function with no annotations at all, and a test written as `def test_orders():` is exactly that.

So the one mistake below, written in two tests, is reported twice by Pyright, `ty` and Pyrefly out of
the box, once by mypy at its defaults, and twice by mypy once it is told to read those bodies:

<!-- docs-guard: skip -->

```python
def test_unannotated():        # mypy default: not checked at all
    assert_that("abc").is_greater_than(3)

def test_annotated() -> None:  # mypy default: checked
    assert_that("abc").is_greater_than(3)
```

Either annotate every test with `-> None`, or set `check_untyped_defs = true`, which `strict = true`
already includes. Pyright, `ty` and Pyrefly need neither.

Strict mode then surfaces the most - a wrong method called on a narrowed value, a missing return
annotation, a `.value` read where the type was never narrowed. Turn it on for your checker:

```toml
# pyproject.toml - mypy
[tool.mypy]
strict = true
```

```toml
# pyproject.toml - Pyright / Pylance  (or "typeCheckingMode": "strict" in pyrightconfig.json)
[tool.pyright]
typeCheckingMode = "strict"
```

`ty` and Pyrefly need no configuration - they read the types out of the box. All four pick up
`assertpy`'s types automatically via the `py.typed` marker below. There is no stub package to install.

## py.typed and PEP 561

`assertpy` ships a `py.typed` marker and is [PEP 561](https://peps.python.org/pep-0561/) compliant, so the
types are picked up automatically by any project that depends on it - no stub package, no extra config.

## Editor support

The overloads are plain typing with no runtime cost, so type-aware autocomplete works in PyCharm, VS Code
(Pylance), and any LSP-compatible editor out of the box.
