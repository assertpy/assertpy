# The typed surface

`assert_that()` hands back a different set of methods depending on what you gave it, and four checkers have to
agree on which set. Read this before changing a public signature. None of it is discoverable from the files.

## Two halves

The runtime is a stack of mixins. `AssertionBuilder` inherits `StringMixin`, `NumericMixin`, `DictMixin` and a
dozen more, so every assertion exists on every value and refuses what it cannot handle.

The typed surface is Protocols in `assertpy/_engine/_typing.py`, one per kind of value, picked by an overload
ladder on `assert_that` in `assertpy/assertpy.py`. A checker sees only the protocol, so
`assert_that({}).is_positive()` is a type error and `assert_that(1).is_positive()` is not.

Neither half knows about the other. Everything below keeps them from drifting apart.

Most of it is not yours to edit:

| file | protocols | declarations |
|---|---|---|
| `_engine/_typing.py` | 43 | 414 |
| `_engine/_check_typing.py` | 34 | 325 |
| `_engine/_builder_check_typing.py` | 1 | 319 |
| `_engine/_capable_typing.py` | 10 | 323 |
| `_engine/_poll_typing.py` | 22 | 1501 |
| `_engine/_negated_typing.py` | 23 | 1049 |

One is written by hand. `tests/test_architecture_doc.py` recomputes this table. No line counts, which
move on every edit to a generated file.

## What is generated

| file | written by | built from |
|---|---|---|
| `_engine/_typing.py` | hand | the protocols themselves |
| `assertpy.py` overload ladder | hand | which protocol each subject resolves to |
| `_engine/_poll_typing.py` | `scripts/generate_poll_protocols.py` | `_typing.py`, `assertpy.py`, `_engine/_operations.py` |
| `_engine/_builder_check_typing.py` | `scripts/generate_poll_protocols.py` | the same three |
| `_engine/_capable_typing.py` | `scripts/generate_poll_protocols.py` | the **runtime mixins** under `assertpy/*.py`, `_engine/_operations.py` |
| `_engine/_negated_typing.py` | `scripts/generate_poll_protocols.py` | `_typing.py` and `_engine/_operations.py` |
| `_engine/_check_typing.py` | `scripts/generate_check_protocols.py` | `_typing.py`, `_engine/_operations.py` |

One script writes four of them. That is the part people miss.

- **polling twins** answer `eventually()` and `eventually_sync()`, so every assertion hands back the chain.
- **verdict twins** answer `check()`, returning an `AssertionOutcome` instead of `Self`.
- **the capability façade** stands in for the builder itself, so it reads the mixins rather than the views:
  reading the views would narrow it to what one value type answers. It skips its own hand-written list, and
  takes which mixin methods pivot from `_engine/_operations.py`, since the mixins write those `-> Self` too.
- **negation twins** answer `.not_`, where one assertion hands back the view the chain had before it.

`_engine/_operations.py` decides what the first two leave out: `NOT_AN_OPERATION`, `WITHOUT_A_VERDICT`.

## Changing a signature

```bash
uv run python scripts/regenerate.py
```

That runs both generators, re-records `tests/api_snapshot.json`, which pins the public surface, and
re-records the table of sizes above. Read the diff it leaves.

**The generators carry hard-coded import lines.** A signature naming something the generated file did not
already import produces a file that will not compile, and ruff reports `F821 Undefined name` against a file you
never edited. Add the name to the import template in the generator.

## Adding a type of value

The runtime comes first, because the rest is generated or recorded from it.

1. Write the mixin, compose it into `AssertionBuilder`'s bases.
2. Add it to `_COVERAGE` in `tests/test_protocol_parity.py`, which has its own gate.
3. Declare the protocol in `_engine/_typing.py`.
4. Add the arm to the `assert_that` ladder in `assertpy.py`.
5. Pin it with `assert_type` in `tests/test_typing.py`, the file the README badge is about.
6. Regenerate.
7. Re-record the snapshot, last.

Regenerating before step 1 produces a stale façade. Recording the snapshot before the mixin is composed makes
its gate red again.

## Adding an assertion to a type that exists

The skipped step is the third.

1. Write the method on its mixin.
2. Declare it on the protocols it applies to in `_engine/_typing.py`, and on those only. A declaration
   on `_CoreAssertion` offers it to every value, which is the thing the typed surface exists to avoid.
3. Register it in `_engine/_operations.py` unless it is a plain assertion. No verdict goes in
   `WITHOUT_A_VERDICT` under what it does instead, since `check()` and `not_` mean nothing on it and
   both used to accept them. A pivot that also asserts goes in `ALSO_ASSERTS`, since reaching
   `self.error()` does not separate a verdict from a precondition.
4. If the polling twin is meant to leave it out, add the name to `_AFTER_A_CALL` in
   `tests/test_poll_protocols.py`. The whole caught-exception family is absent from that twin, and the
   list is what says so on purpose rather than by accident.
5. Regenerate. The generators emit what they find, so a missing declaration surfaces not here but in
   `test_protocol_parity.py::test_mixin_methods_are_declared_on_its_protocols`.

A signature naming a type the generated files do not import produces a file that does not compile. The
import lines are templates inside the generators.

## The gates

| gate | the question it answers |
|---|---|
| `test_typing.py` | does each subject resolve to the protocol it should, under all four checkers |
| `test_pin_coverage.py` | does every declaration that changes the type have a pin above |
| `test_protocol_parity.py` | does every declared method exist on the runtime builder |
| `test_typing_conformance.py` | do the declaration and the runtime agree parameter by parameter |
| `test_poll_protocols.py` | are the polling twins what the generator produces today |
| `test_check_protocols.py` | are the verdict twins |
| `test_capable_protocol.py` | is the façade |
| `test_api_compatibility.py` | has the public surface moved without the snapshot being re-recorded |
| `test_typing_completeness.py` | can a checker name a type for every exported symbol |
| `test_pyright_baseline.py` | has a new pyright diagnostic appeared in the package |
| `test_typing_promises.py` | is the object at the end of a chain the type the checker was promised |
| `test_negated_protocols.py` | does every reachable view have a negation twin that hands the view back, and is the file what the generator produces |
| `test_architecture_doc.py` | does this document still describe the tree, counts included |
| `test_typing_negative.py` | do the checkers still refuse what they should |
| `test_typing_chain_corpus.py` | do the chains the chain model takes, to two pivots, still type the way they were recorded |
| `test_typing_from_a_wheel.py` | does the typed surface survive packaging |
| `test_typing_integrations.py`, `test_typing_http.py` | do real pandas, polars, numpy and HTTP values still resolve |
| `test_typing_harness.py` | is pyright's report read off its output alone, and refused where that is not one report |
| `test_overload_order.py` | is the frame overload still above every other shape-keyed one |
| `test_operation_contract.py` | is the register of operations that reach no verdict still the true one |
| `test_typing_claims.py` | are the four checkers still run with zero suppressions, as the badge says |
| `test_docs_typing.py` | do the snippets in the README and the guides type-check |
| `test_public_surface.py` | does `import assertpy` still give what it gave |

Which one goes red tells you what you did:

- a declaration the runtime does not have: `test_protocol_parity.py`
- a declaration whose parameters the runtime does not match: `test_typing_conformance.py`
- a generated file edited by hand: that file's own gate, one of the four
- a protocol changed without regenerating: the polling, verdict and negation gates, never the facade one,
  which reads the mixins instead
- a subject resolving to the wrong protocol: `test_typing.py`, and only under whichever checker sees it
- a public name added or moved: `test_api_compatibility.py`, which is a snapshot rather than a rule

The four checkers are ty, mypy `--strict`, Pyright and Pyrefly. Where they disagree it is recorded, in
`tests/typing_negative_baseline.py`, `tests/typing_integrations_baseline.py` and
`tests/typing_chain_corpus_baseline.json`.

Pyright's engine is pinned in `tests/typing_harness.py`. The PyPI distribution is a launcher for a node package
and the two move at different speeds.

## True, though it looks wrong

- **`assert_that`'s implementation returns `Any`.** The real return made Pyright allocate four gigabytes against
  a protocol carrying the whole surface and die. The overloads are what callers see.
- **Some overlapping overloads are deliberate**, recorded per method in `tests/pyright_baseline.py`.
- **Some variance suggestions are refused**, recorded there too, per TypeVar.
- **`ty` is scoped to `assertpy/` and `tests/test_typing.py`.** Over the whole tree it reports hundreds of
  diagnostics from `tests/`, which is full of calls that must not type-check.

## Where the two halves may differ

**Which methods are offered.** At run time every assertion exists on every value; a typed view offers only the
ones that apply. That gap is the point of the typed surface.

**What an offered method accepts.** Here they must agree exactly, and both directions have shipped as defects:

- the type **refuses** what the runtime accepts, so working code is rejected
- the type **accepts** what the runtime refuses, so a checker approves a call that raises

The runtime is the fact and the declaration follows it. `ClassInfo` in `_matcher_impls.py` is the worked
example: recursive because `isinstance` accepts tuples nested to any depth.
