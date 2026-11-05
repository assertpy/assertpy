# Type Assertions

`assert_that()` returns a type-specific set of assertions. The sections below group them by value type.

## Strings

```python
assert_that("").is_empty().is_false().is_type_of(str)
assert_that("foo").is_length(3).is_not_empty().is_alpha().is_lower()
assert_that("123").is_digit()
assert_that("FOO").is_upper()
assert_that("foo").is_equal_to("foo").is_not_equal_to("bar")
assert_that("foo").is_equal_to_ignoring_case("FOO")
assert_that("foo bar").is_equal_to_ignoring_whitespace("foobar")
assert_that("<p>foo</p>").is_html_equal_to("<p> foo </p>")
assert_that("foo").is_length_between(1, 5)
assert_that("foo123").is_alphanumeric()
assert_that("   ").is_whitespace()

assert_that("foo").contains("f", "oo")
assert_that("foo").contains_ignoring_case("F", "oO")
assert_that("foo").does_not_contain("x")
assert_that("foo").contains_only("f", "o")
assert_that("foo").contains_sequence("o", "o")
assert_that("foobar").contains_any_of("foo", "xyz")
assert_that("foobar").contains_none_of("xyz", "abc")
assert_that("foo").contains_duplicates()
assert_that("fox").does_not_contain_duplicates()

assert_that("foo").is_in("foo", "bar", "baz")
assert_that("foo").is_subset_of("abcdefghijklmnopqrstuvwxyz")
assert_that("foo").starts_with("f").ends_with("oo")
assert_that("FooBar").starts_with_ignoring_case("foo").ends_with_ignoring_case("BAR")

assert_that("foo").matches(r"\w")
assert_that("123-456-7890").matches(r"\d{3}-\d{3}-\d{4}")
assert_that("foo").does_not_match(r"\d+")
```

`contains_any_of()` and `contains_none_of()` ask a string about substrings. For the items of a
collection, `any_satisfy(match.is_in(2, 9))` holds when any item is one of them, and
`does_not_contain(8, 9)` when none is. Over an empty collection the first fails and the second passes.

!!! note "An empty prefix or suffix is refused"
    This one does not follow from Python, where `"foo".startswith("")` is `True`. An empty prefix holds
    for every value, so the assertion cannot fail and checks nothing. `starts_with()`, `ends_with()`,
    their `_ignoring_case` spellings and `starts_with_bytes()` raise `ValueError` rather than pass.

    <!-- docs-guard: raises -->
    ```python
    assert_that("foo").starts_with("")   # ValueError: given prefix arg must not be empty
    ```

    An empty **value** is refused the same way when the subject is a non-string iterable, since there is
    no first element to compare against.

!!! note "Regex matching"
    Use raw strings (`r"..."`) for patterns. `matches()` passes when the pattern is found anywhere in
    the string, as `re.search` finds it. Anchor the pattern with `\A` and `\Z` to match the whole string.
    `^...$` is not quite that: `$` also matches before a final newline. Flags go inline, such as `(?m)` and
    `(?s)`, or on a pattern compiled with `re.compile()`. `matches()`, `does_not_match()`,
    `extracting_group()`, `matches_with_groups()` and `match.matches_regex()` take a compiled pattern wherever
    they take its text.

    <!-- docs-guard: skip -->
    ```python
    assert_that("foo").matches(r"\w{2}")       # partial, passes
    assert_that("xfoo").matches(r"foo")        # not at the start, passes
    assert_that("foo").matches(r"\A\w{3}\Z")   # whole string, passes
    assert_that("foo").matches(r"\A\w{2}\Z")   # fails
    assert_that("foo\n").matches(r"^foo$")     # passes, $ matches before the final newline
    assert_that("a\nb").matches(re.compile(r"a.b", re.DOTALL))   # the flag on the pattern, passes
    ```

### HTML

`is_html_equal_to()` parses both strings as HTML and compares the element trees. Two strings that give
the same tree are equal, however each is written. `match.html_equal_to()` does the same comparison as a
matcher.

```python
assert_that('<p class="a b" id="x">Hi</p>').is_html_equal_to("<P ID=x CLASS='b a'>Hi</P>")
assert_that("<ul>\n  <li>one</li>\n  <li>two</li>\n</ul>").is_html_equal_to("<ul><li>one</li><li>two</li></ul>")
assert_that("<input disabled>").is_html_equal_to('<input disabled="disabled">')
assert_that("<p>&lt;3 &amp; more</p>").is_html_equal_to("<p>&#60;3 &#38; more</p>")
assert_that({"body": "<p>\n  Hi\n</p>"}).matches_structure({"body": match.html_equal_to("<p>Hi</p>")})
```

These differences are ignored:

- the order of attributes, and the order of the classes in `class`
- upper and lower case of ASCII letters in element and attribute names
- the quotes around an attribute value
- a character written as a reference, such as `&#233;` for `é`
- comments and the doctype
- the value of a boolean attribute, on elements where the HTML standard makes it boolean. `disabled` is
  boolean on form controls, so `<input disabled="false">` equals `<input disabled>`. On a `div` or a
  custom element the value is compared
- how the `hidden` state is spelled. `hidden`, `hidden=""` and `hidden="hidden"` are the same state, and
  `hidden="until-found"` is a different one

The `whitespace` argument sets how text is compared. The default, `whitespace="lenient"`, follows
Django's `assertHTMLEqual`:

- a run of whitespace counts as one space
- whitespace at the start and end of a text is ignored
- whitespace between two elements is ignored

This lets you write the expected HTML across indented lines. It also makes some markup equal that a
browser shows differently. All three of these pass:

<!-- docs-guard: skip -->
```python
assert_that("<b>a</b> <i>b</i>").is_html_equal_to("<b>a</b><i>b</i>")
assert_that("<i>a </i><i>b</i>").is_html_equal_to("<i>a</i><i>b</i>")
assert_that("<p>a <b>b</b> c</p>").is_html_equal_to("<p>a<b>b</b>c</p>")
```

With `whitespace="exact"`, text is compared as written, every space and newline included, so all three
fail. The expected HTML then needs exactly the spacing you mean.

In both modes:

- the text inside `pre`, `textarea`, `script` and `style` is compared as written
- only ASCII whitespace counts as whitespace. A non-breaking space is compared like any other character
- a newline right after `<pre>` or `<textarea>` is ignored, because the HTML parser drops it

A failure shows both trees written out one node to a line, with every text in quotes, and the lines where
they part:

<!-- docs-guard: raises -->
```python
assert_that('<div>\n  <p class="a">Hello</p>\n</div>').is_html_equal_to('<div><p class="a">Hi</p></div>')
```

<!-- docs-guard: skip -->
```text
Expected <<div>
  <p class="a">"Hello"</p>
</div>> to be equal to <<div>
  <p class="a">"Hi"</p>
</div>> as HTML, but was not.
diff (string):
  line 2:
    -   <p class="a">"Hello"</p>
    ?                  ^^^^
    +   <p class="a">"Hi"</p>
    ?                  ^
```

!!! note "Markup that is refused"
    Some markup raises `ValueError` instead of being compared. This holds for either side, and under
    `not_` too.

    <!-- docs-guard: raises -->
    ```python
    assert_that("<p>a</q>").is_html_equal_to("<p>a</p>")
    # ValueError: val is not HTML that can be read: </q> closes no open <q>, at line 1, column 5
    ```

    Broken markup:

    - an end tag that closes no open element
    - an attribute given twice on one element
    - a `script`, `textarea` or other raw-text element that is never closed
    - a raw-text element written with a slash, such as `<script/>`
    - text that ends inside a tag or a comment
    - a NUL character
    - a numeric reference to a control character or a noncharacter, such as `&#1;`. Python's decoder
      drops the character, and a browser keeps it
    - elements nested more than 256 deep

    Markup this comparison does not read:

    - a marked section, such as `<![CDATA[x]]>` or `<![if x]>`. HTML ends it at the first `>`, and
      Python's parser at `]]>` or not at all
    - `svg` and `math`. SVG and MathML have their own rules for slashes, CDATA, text and attributes

    Spellings that Python's parser reads one way before its 2025 fixes and another way after. They are
    refused so that a comparison does not pass on one patch release and fail on the next:

    - a comment closed as `<!-->` or by `--!>`
    - a comment holding `--` and spaces before a `>`
    - a `</` not followed by a letter
    - a raw-text end tag with more than its name, such as `</script x>`
    - a non-ASCII space in an attribute name, or in a value without quotes
    - a value without quotes holding `"`, `'`, `=`, `<` or a backtick

    Not refused: an element left open at the end is closed, and an end tag closes every element opened
    after its own.

    Attribute values are decoded by the HTML standard's rules on every Python version. So
    `href="?a=1&not=2"` keeps `&not=2` as written.

    `match.html_equal_to()` parses the expected HTML when the matcher is built, and raises there. A value
    it cannot parse does not match.

!!! note "Where it differs from Django"
    The tree is built the way Django builds it, which is simpler than a browser. `<p>a<p>b` puts the
    second `p` inside the first, and a browser closes the first.

    The differences:

    - a slash on a non-void element is ignored, as the HTML standard says. `<div/>x` puts `x` inside the
      `div`, and Django closes the `div` at once
    - the text of `pre`, `textarea`, `script` and `style` is compared as written. Django collapses its
      whitespace
    - only ASCII whitespace is collapsed and trimmed. Django trims every Unicode space, the non-breaking
      one included
    - a boolean attribute counts by its presence. Django takes `disabled="false"` as a different value
      than `disabled`. Its list of boolean attributes also treats `disabled` as boolean on every element
      and lacks `defer`
    - `hidden` is compared by its state, so an unknown value means hidden, and `UNTIL-FOUND` equals
      `until-found`
    - a repeated attribute, markup that ends inside a tag, a comment or a raw-text element, and SVG and
      MathML are refused. Django reads them

    The content of `textarea`, `title`, `xmp`, `iframe`, `noembed`, `noframes` and `plaintext` is read as
    text on every Python version. Python's parser read markup inside them before its 2025 fixes, so
    Django's result on them depends on the Python patch release.

## Numbers

```python
assert_that(0).is_zero().is_false().is_type_of(int)
assert_that(1).is_not_zero().is_positive()
assert_that(-1).is_negative()
assert_that(4).is_even()
assert_that(3).is_odd()
assert_that(9).is_divisible_by(3)

assert_that(123).is_equal_to(123).is_not_equal_to(456)
assert_that(123).is_greater_than(100).is_greater_than_or_equal_to(123)
assert_that(123).is_less_than(200).is_less_than_or_equal_to(200)
assert_that(123).is_between(100, 200)
assert_that(123).is_close_to(100, 25)
assert_that(1).is_in(0, 1, 2, 3).is_not_in(-1, -2, -3)

# floats
assert_that(123.4).is_close_to(123, 0.5)
assert_that(123.4).is_between(100.1, 200.2)
assert_that(float("NaN")).is_nan()
assert_that(123.4).is_not_nan()
assert_that(float("Inf")).is_inf()
assert_that(123.4).is_not_inf()
```


`is_in()` and `is_not_in()` take each candidate as a separate argument, so unpack a collection with
`*`. A collection passed without `*` is a single candidate, and the value is compared with the
collection itself:

```python
allowed = [0, 1, 2, 3]

assert_that(1).is_in(*allowed)
assert_that(1).satisfies(match.is_in(*allowed))
assert_that(9).is_not_in(*allowed)
assert_that(1).is_not_in(allowed)   # passes: 1 is not equal to the list
```

A missing `*` is easy to overlook:

- `is_in(allowed)` fails for a value in the list, and the message shows the list, so you notice
- `is_not_in(allowed)` passes for a value in the list, and nothing tells you the check was wrong

`match.is_in()` takes its candidates the same way.

!!! warning "Floats and equality"
    Avoid `is_equal_to()` with `float` values. Use `is_close_to()` or `is_between()` instead.

How `is_close_to()` measures:

- It passes when any one of three checks holds: the difference is at most the tolerance, the value is
  within `expected ± tolerance`, or the expected value is within `value ± tolerance`.
- Float rounding at the boundary can differ between the three checks. So `-1.1` is close to `-0.9`
  within `0.2`, although `-0.9 - -1.1` is `0.20000000000000007`.
- With an absolute tolerance, swapping the value and the expected value gives the same answer.
- `match.close_to()` gives the same answer, `is_not_close_to()` the opposite, and
  `is_equal_to(..., tolerance=)` measures each pair the same way.

How particular pairs are measured:

- A pair Python's arithmetic refuses or overflows is measured by exact value: a `Decimal` against a `float` or a `numpy`
  integer, an `int` past the float range against a `float`. A `Decimal` context that traps `Overflow`
  still raises it.
- A `numpy` integer is measured and ordered as the `int` it holds, since its own arithmetic wraps:
  `numpy.uint8(3)` is 247 away from `250`, where `numpy.uint8(3) - 250` gives `9` and a warning.
- A `numpy` float beside one is read as the `float` it holds, where a `float` holds the same number.
- A subclass of a `numpy` scalar uses its own operators and keeps its width. So does a `Fraction` built
  from a `numpy` integer.
- Two values, each an `int` or a `Fraction` of two `int`s, are close by their exact difference alone,
  since a window under a float tolerance rounds one past `2**53`.
- Other pairs are measured by their own arithmetic.
- An infinity is close only to an equal infinity, whatever the tolerance. A NaN is close to nothing and is
  neither less than, greater than nor between anything.

```python
assert_that(-1.1).is_close_to(-0.9, 0.2)
assert_that(10**400).is_close_to(10**400 + 1, 1)
assert_that(float("inf")).is_not_close_to(1e308, float("inf"))
assert_that(float("nan")).is_not_close_to(float("nan"), 1)
```

`rel=` is a tolerance relative to the expected value, as in `pytest.approx()` and
`numpy.testing.assert_allclose()`:

- `rel=0.02` allows `2` either side of `100`, whatever the value.
- Not the larger of the two, as `math.isclose()` takes it: then the value would widen its own allowance,
  and `10` would be within `rel=1` of `1`.
- Beside an absolute tolerance, either one holding is enough, which keeps an expected value near zero
  within reach. They are not added: `100` is not close to `103` within `1` and `rel=0.02`.
- A datetime has no size and refuses `rel`.
- `match.close_to()`, `match.equal_to()` and `is_equal_to()` take it too.

```python
assert_that(101.5).is_close_to(100, rel=0.02)
assert_that(98.0).is_close_to(100.0, rel=0.02)
assert_that(100.0).is_not_close_to(98.0, rel=0.02)
assert_that(10).is_not_close_to(1, rel=1)
assert_that(0.0).is_close_to(0.001, 0.01, rel=0.02)
assert_that(100).is_not_close_to(103, 1, rel=0.02)
```

A `bool` is refused as the value, the expected value or the tolerance, and so is a negative or NaN
tolerance:

<!-- docs-guard: raises -->
<!-- docs-guard: type-error -->
```python
assert_that(True).is_close_to(1, 0)
# TypeError: val must be a number other than a bool, or a datetime, but was <True> (bool)
```

## Lists

```python
assert_that([]).is_empty().is_type_of(list).is_iterable()
assert_that([]).is_instance_of((list, tuple))
assert_that(["a", "b"]).is_length(2).is_not_empty()
assert_that(["a", "b"]).is_equal_to(["a", "b"]).is_not_equal_to(["b", "a"])

assert_that(["a", "b"]).contains("b", "a")
assert_that(["a", "b"]).does_not_contain("x", "y")
assert_that([1, 2, 3]).does_not_contain(match.greater_than(99))   # matchers, same as contains
assert_that(["a", "b"]).contains_only("a", "b")
assert_that(["a", "b", "c"]).contains_sequence("b", "c")
assert_that(["a", "b", "c"]).contains_exactly("a", "b", "c")
assert_that(["c", "a", "b"]).contains_exactly_in_any_order("a", "b", "c")
assert_that(["a", "x", "b", "y", "c"]).contains_in_order("a", "b", "c")
assert_that(["a", "b"]).is_subset_of(["a", "b", "c"])
assert_that(["a", "b", "c"]).is_sorted()
assert_that(["c", "b", "a"]).is_sorted(reverse=True)
assert_that(["a", "x", "x"]).contains_duplicates()
assert_that(["a", "b", "c"]).does_not_contain_duplicates()
assert_that(["a", "b", "c"]).starts_with("a").ends_with("c")

assert_that([1, -2, 3]).any_satisfy(lambda x: x < 0)
assert_that([1, 2, 3]).all_satisfy(lambda x: x > 0)
assert_that([1, 2, 3]).none_satisfy(lambda x: x < 0)

assert_that([2, 4, 6]).satisfies_exactly(
    lambda x: x == 2, lambda x: x == 4, lambda x: x == 6
)
assert_that([4, 2]).satisfies_exactly_in_any_order(lambda x: x == 2, lambda x: x == 4)
assert_that([1, 2, 3]).zip_satisfies([2, 4, 6], lambda actual, other: other == actual * 2)
assert_that([1, 2, 3]).contains_only_once(1, 3)
assert_that([1, 2, 3]).has_same_size_as(("a", "b", "c"))
assert_that([1, 2, 3]).has_size_greater_than(2).has_size_less_than(4).has_size_between(
    1, 5
)
```

- `any_satisfy`, `all_satisfy` and `none_satisfy` accept callables and [matchers](matchers.md).
- `is_length()` takes a matcher for the length: `is_length(match.between(2, 5))`. So do
  `match.has_length()` and `match.is_length()`.
- `is_type_of()` asks for the exact class and takes one class, so a `bool` is no `int` there.
- `is_instance_of()` accepts subclasses, and a tuple or a union of classes.

#### Assertions that checked nothing

`all_satisfy` over an empty collection passes, the way `all([])` is true: no item failed.

This is logically right, but it is also the most common way a test passes without checking anything.
When a query returns no rows, the assertion has no items to check, and it passes.

Turn the guard on and those cases say so:

```bash
pytest --assertpy-vacuous
```

```text
VacuousAssertionWarning: all_satisfy() passed over an empty value, so nothing
was checked. Pass allow_empty=True if that is intended.
```

The warning points at your line, not at library code. To escalate or relocate it:

- `-W error::assertpy.VacuousAssertionWarning` turns it into a failure
- `ASSERTPY_VACUOUS=1` enables it for runners other than pytest

It is off by default for two reasons. A suite running `filterwarnings = ["error"]` would start failing
on upgrade, and a property-based test generates empty collections as a matter of course.

When emptiness is the point of the test, say so per call and the guard stays quiet:

```python
archived_orders = []  # a fixture that yields nothing on a clean database

assert_that(archived_orders).all_satisfy(lambda o: o["closed"], allow_empty=True)
```

`allow_empty` is accepted by the universal assertions:

- `each`, `all_satisfy`, `all_fields_satisfy`, `has_no_none_fields`
- `zip_satisfies`, `is_sorted`, `is_subset_of`

The same guard watches `is_equal_to` under `ignore` or `include`. A filter that removed every key of
the compared dict or object leaves it nothing to check:

```python
assert_that({"id": 7}).is_equal_to({"id": 8}, ignore="id")  # passes, and compared nothing
```

```text
VacuousAssertionWarning: is_equal_to() passed with ignore and include leaving no
key to compare, so nothing was checked.
```

Two empty dicts compared under a filter give no warning, because the comparison did check that both
are empty.
`snapshot()` gives no such warning: the keys it ignores include its placeholders, and their matchers
check those.

The negative ones never warn. For `none_satisfy`, `does_not_contain` and `does_not_contain_duplicates`
an empty subject is the expected pass: "no errors were logged" is what such a test wants to hear.

The exact-pairing and multiset assertions:

- `satisfies_exactly` - pairs the i-th item with the i-th matcher (equal length required).
  `satisfies_exactly_in_any_order` - any one-to-one pairing instead.
- `zip_satisfies` - checks a two-arg predicate over items zipped with another iterable.
- `contains_only_once` - each given item must occur exactly once.
- `has_same_size_as` - compares lengths against another sized object.
- `contains_exactly_in_any_order` - multiset equality: exact items and counts, order ignored.

#### Assertions that never ran

The guard above catches an assertion that ran and examined nothing. The other half of the same problem
is an assertion that never ran at all:

<!-- docs-guard: skip -->
```python
async def test_the_user_is_active():
    assert_that(user)                              # builds a builder and asserts nothing
    assert_that(user.age).is_positive              # looked up, never called
    assert_that(probe).eventually().is_positive()  # never awaited, so it polls nothing
```

All three are green forever, and none of them is possible with a bare `assert`. That is the price of a
fluent API, so the library owes you a way to find them.

A fourth case needs no check, because it raises an error on the spot. Calling an `async def`
predicate returns a coroutine and runs nothing. A coroutine is truthy, so without the error the
assertion would pass for any value:

<!-- docs-guard: raises -->
```python
async def is_positive(value: int) -> bool:
    return value > 0

assert_that(-1).satisfies(is_positive)
# TypeError: predicate handed back a coroutine instead of an answer; ...
```

Await the call and assert on the result: `assert_that(await is_positive(-1)).is_true()`.

- Every place that reads an answer as truth refuses a coroutine: a plain callable, a custom matcher's
  `matches()`, a `comparators=` entry, directly or through a composed matcher.
- To poll an async probe, use `eventually()`.
- `raises()`, `does_not_raise()`, `warns()` and `does_not_warn()` refuse an `async def` too:
  `when_called_with()` raises `TypeError`, since the body has not run when the call returns. Await it
  inside `pytest.raises` or `pytest.warns` instead.
- An async generator is refused the same way. A plain generator is not: its body runs when consumed.

Ruff already covers part of it, and this check does not repeat what it does:

- the second line is ruff's [`B018`](https://docs.astral.sh/ruff/rules/useless-expression/)
- a builder bound to a name and never read is its `F841`

The other two are reported by nothing, because a call may have side effects and no linter can know
these do not.

Writing `assert` in front does not save you, and that shape is the worst of the family:

<!-- docs-guard: skip -->
```python
def test_the_user_is_active():
    assert assert_that(user.age).is_positive  # green whatever the age is
```

`assert` reads the bound method, and a bound method is truthy. The line passes on every value while
reading as though it checked one. `B018` does not apply here, since the value is consumed rather than
discarded, and coverage counts the line as run.

```bash
pytest --assertpy-dangling
```

```text
DanglingAssertionWarning: assert_that() builds a builder here and asserts nothing
```

For a project that wants it on every run, set it in the config instead. The flag still wins, so one
person can try it without editing a file the whole team shares:

```toml
[tool.pytest.ini_options]
assertpy_dangling = "on"
```

The check reads your test files rather than running anything, so it costs nothing at runtime and
cannot move a stack frame.

**A warning on its own leaves the run green.** pytest exits zero with warnings, so a finding that
should stop a merge has to be promoted to an error. The finding is attached to the test containing the
line, so promoting it fails that test and nothing else:

```toml
[tool.pytest.ini_options]
filterwarnings = [
    "error::assertpy.DanglingAssertionWarning",
]
```

Without that line the check is a report you have to go and read, which is a fair choice for a first
look and a poor one for CI.

When asserting nothing is the point - a benchmark measuring what building a builder costs, a test of
the assertion machinery itself - say so on the line and the check passes over it:

<!-- docs-guard: skip -->
```python
for index in range(1000):
    assert_that(index)  # assertpy: allow-dangling
```

The marker is assertpy's own, not ruff's `# noqa`. Silencing ruff on a line does not silence this
check, and the marker does not silence ruff. It covers the whole statement it is on, so on a call split
over several lines it can go on any of them, the closing line included.

Most suites of any size wrap `assert_that` in a helper of their own, and the check cannot see through
one it has never heard of. Name yours and it reads them the same way:

```toml
[tool.pytest.ini_options]
assertpy_dangling_entries = "check verify"
```

- List only a wrapper that **builds** something to assert on, as `assert_that` does. A helper that asserts
  inside its own body is complete, and listing it would report working code.
- The name must arrive through `from ... import check`, aliases included. A helper reached as
  `helpers.check(...)` is not read.

Two limits worth knowing before you rely on it:

- **a name this module binds itself is dropped for the whole file.** One `assert_that = something`
  anywhere in it turns the check off for that name everywhere in that file. The trade buys no false
  alarms at the cost of missed ones.
- **several dangling statements in one test arrive as a single warning** naming the extra lines. Under
  `filterwarnings = ["error"]` the first one ends the test, so a second warning would never be seen.

What it deliberately leaves alone:

- anything inside `pytest.raises()`, `pytest.warns()` or `pytest.deprecated_call()`. The silent pass
  this check exists for cannot happen there: the chain either raises, which is what the test asserts,
  or it does not and the block turns the test red by itself
- a builder bound to a name (`b = assert_that(x)`), because whether `b` is used later is a question
  about the rest of the function, not about that statement
- a chain ending on a bare `check()`, since reporting it would mean deciding that the name is this
  library's, and a project can register an extension called `check` that asserts by itself
- `assert_conforms()`, `fail()` and `soft_fail()`, which assert on their own, so a bare call is correct

A `soft_assertions()` block is not one of those: it collects failures and reaches its end, so a chain
that asserted nothing inside one leaves the test as green as it would anywhere else.

One limit worth knowing before you count on it: the check reads the test modules pytest collected, and
nothing else.

So a project that keeps its assertion layer in a package of its own, `framework/asserts/` rather than
the test files, gets no coverage of that package from a pytest run. Nothing warns you either, because
from inside a run a clean package and an uncollected one look identical.

Another cost: the check is static, and a
[dynamic assertion](#dynamic-assertions-on-objects) is resolved at runtime, so
`assert_that(fred).has_first_name` without its parentheses is caught by `B018` rather than here.

Lists of lists can be flattened by index with `extracting` (see [dict flattening](#dict-flattening)):

```python
people = [["Fred", "Smith"], ["Bob", "Barr"]]
assert_that(people).extracting(0).is_equal_to(["Fred", "Bob"])
assert_that(people).extracting(-1).is_equal_to(["Smith", "Barr"])
```

## Tuples

Tuples support the same membership, ordering, and duplicate assertions as lists:

```python
assert_that(()).is_empty().is_type_of(tuple).is_iterable()
assert_that((1, 2, 3)).is_length(3).is_equal_to((1, 2, 3))
assert_that((1, 2, 3)).contains(3, 2, 1).contains_only(1, 2, 3)
assert_that((1, 2, 3)).contains_sequence(2, 3).contains_exactly(1, 2, 3)
assert_that((1, 5, 2, 8, 3)).contains_in_order(1, 2, 3)
assert_that((1, 2, 3)).is_subset_of((1, 2, 3, 4)).is_sorted()
assert_that((1, 2, 2)).contains_duplicates()
assert_that((1, 2, 3)).starts_with(1).ends_with(3)
```

Tuples of tuples flatten by index with `extracting`:

```python
points = ((1, 2, 3), (4, 5, 6))
assert_that(points).extracting(0).is_equal_to([1, 4])
assert_that(points).extracting(-1).is_equal_to([3, 6])
```

## Dicts

```python
assert_that({}).is_empty().is_type_of(dict)
assert_that({"a": 1, "b": 2}).is_length(2).is_not_empty()
assert_that({"a": 1, "b": 2}).is_equal_to({"b": 2, "a": 1})

assert_that({"a": 1, "b": 2}).contains("b", "a")
assert_that({"a": 1, "b": 2}).does_not_contain("x", "y")
assert_that({"a": 1, "b": 2}).contains_only("a", "b")
assert_that({"a": 1, "b": 2}).is_subset_of({"a": 1, "b": 2, "c": 3})

# contains_key / does_not_contain_key search the keys as contains / does_not_contain do,
# and refuse a value that is not dict-like
assert_that({"a": 1, "b": 2}).contains_key("b", "a")
assert_that({"a": 1, "b": 2}).does_not_contain_key("x", "y")

assert_that({"a": 1, "b": 2}).contains_value(2, 1)
assert_that({"a": 1, "b": 2}).does_not_contain_value(3, 4)

assert_that({"a": 1, "b": 2}).contains_entry({"a": 1}, {"b": 2})
assert_that({"a": 1, "b": 2}).does_not_contain_entry({"a": 2})
```

### Selective comparison (ignore / include)

`is_equal_to()` can ignore or include keys or fields of dicts, dataclasses, named tuples, Pydantic models,
attrs classes and plain objects.

- Any other mapping, such as `MappingProxyType` or `ChainMap`, is read by its keys.
- Sequences are compared element by element under the same filters. One failure covers both sequences,
  and its diff lists each differing element at a path from the sequence: `[1].name`.
- A key applies at the level it names. A nested-path tuple enters the value under its first key and reads
  it by fields (keys, for a mapping). Under `ignore=("user", "id")` a dict and a dataclass holding the same
  under `user` are equal.
- A record (dataclass, attrs instance, model) is read by its fields all the way down, and so is a dict held
  against one, whatever `==` the record has. Under two plain dicts a record is compared by its `==` unless a
  path enters it. An `OrderedDict` under a record keeps its order.
- On a failure, `failure.actual` and `failure.expected` are the compared fields for a record, and your own
  object for a dict or a sequence.
- A plain object is read by its attributes when they are all it holds. A subclass of a builtin container
  and a class with slots hold more, so they are compared by their own `==`, and refused at the top as a
  plain `set` is.

An exception is read as its class (under the name `__class__`), its `args` and its `__dict__` attributes:

- Two of different classes differ, and so do two with different messages, unless you leave `__class__` or
  `args` out by name.
- One with room for more, such as an `OSError` with `filename`, an exception group or a class with slots,
  is compared by its own `==`.
- One that is a dataclass, an attrs class or a model is read as that record, by its declared fields.

The filter accepts a single key, a nested-path tuple, or a `list`/`set`/`frozenset` of those. Any other
iterable (a generator, an iterator, `dict.keys()`) raises `TypeError`.

<!-- docs-guard: skip -->
```python
# ignore keys (single, list/set/frozenset, or nested tuple)
assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1}, ignore="b")
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1}, ignore={"b", "c"})
assert_that({"a": 1, "b": {"c": 2, "d": 3}}).is_equal_to(
    {"a": 1, "b": {"c": 2}}, ignore=("b", "d")
)

# include only specific keys
assert_that({"a": 1, "b": 2, "c": 3}).is_equal_to({"a": 1, "b": 2}, include=["a", "b"])

# objects with introspectable fields
@dataclass
class User:
    id: int
    name: str
    email: str

assert_that(User(1, "Alice", "a@x.com")).is_equal_to(
    User(99, "Alice", "a@x.com"), ignore="id"
)

# attrs instances work the same, including nested paths
@attrs.define
class Account:
    id: int
    owner: str

assert_that(Account(1, "Alice")).is_equal_to(Account(99, "Alice"), ignore="id")
```

`ignore` and `include` also accept a `re.Pattern` (matched against field names) or a `type` (matched
against field values):

<!-- docs-guard: skip -->
```python
import re

# ignore private-ish keys (matched against field names)
assert_that(payload).is_equal_to(expected, ignore=re.compile(r"^_"))
# ignore all float fields
assert_that(payload).is_equal_to(expected, ignore=float)
```

### Recursive comparison (tolerance / custom comparators)

`is_equal_to()` can compare two concrete nested structures with a numeric tolerance or with custom
comparators, anywhere in the graph:

- `tolerance`: an absolute tolerance for every pair of real-number leaves. A pair `==` holds equal stays
  equal, any other is measured as `is_close_to()` measures it (see [Numbers](#numbers)).
    - A `bool` leaf is compared exactly.
    - A numpy duration tolerance measures only numpy duration leaves, and a numeric one no duration leaf.
    - It reaches leaves in mappings, sequences, deques and records, but does not open an
      [object compared by its own `==`](#what-the-walk-takes-apart).
- `rel`: a tolerance relative to the expected leaf of each pair of real-number leaves, beside or instead
  of `tolerance`, either one holding being enough. `snapshot()` and `matches_inline()` take both.
- `comparators`: maps a `type` or a field name to an `(actual, expected) -> bool` predicate. A field-name
  key wins over a type key.
    - A matched node, a value or a whole container, is decided by the predicate alone, at any depth.
    - A container `==` holds equal is still walked, so a comparator stricter than `==` fails a pair inside a
      list, a dict or a deque.
    - Left to `==`: mapping keys, set members, whatever a container shared by both sides holds, and what an
      [object compared by its own `==`](#what-the-walk-takes-apart) holds apart.
    - The predicate may be asked about one pair more than once while a failure is reported. Keep it free
      of side effects.
- The walk reaches a few hundred levels deep. `==` alone goes deeper.

Tolerated or comparator-equal leaves are reported in neither the message nor the diff.

<!-- docs-guard: skip -->
```python
# absolute float tolerance, at any depth
assert_that({"point": {"x": 1.0001, "y": 2.0}}).is_equal_to(
    {"point": {"x": 1.0, "y": 2.0}}, tolerance=0.001
)

# comparator by type, or by field name
assert_that(order).is_equal_to(
    expected, comparators={float: lambda a, e: round(a, 2) == round(e, 2)}
)
# case-insensitive comparator by field name
assert_that(order).is_equal_to(
    expected, comparators={"name": lambda a, e: a.lower() == e.lower()}
)
```

Use `comparators` to change *how* a field or type is compared. To drop a field from the comparison
entirely, use `ignore` (above) rather than an always-true comparator (`ignore` also handles fields missing
on one side or with incomparable types).

`ignore_null=True` skips any named field the **expected** side leaves `None`, at any depth, which suits a
partial template. Only the expected side is skipped, so an unexpected `None` on the *actual* side is still
reported:

<!-- docs-guard: skip -->
```python
# compare only the fields the expected template sets;
# age and address, left None, are ignored
assert_that(user).is_equal_to(User(name="Alice"), ignore_null=True)
```

Sequence elements have no field name, so a `comparators` field-name key does not apply to them (use a type
key or `tolerance`). Sets compare by standard equality.

#### Requiring the same type

Python's `==` compares across types, and a payload keeps that property all the way down. A JSON `true`
read back as a `bool` equals `1`, a `Decimal` from a database column equals an `int`, and neither says a
word:

```python
from decimal import Decimal

assert_that({"active": True}).is_equal_to({"active": 1})  # passes
assert_that({"n": Decimal(1)}).is_equal_to({"n": 1})      # passes
assert_that({"a": {"b": [{"c": True}]}}).is_equal_to({"a": {"b": [{"c": 1}]}})  # passes, three levels down
```

`strict_types=True` requires both sides of every node to be the same type, at any depth:

<!-- docs-guard: skip -->
```python
assert_that({"active": True}).is_equal_to({"active": 1}, strict_types=True)  # fails
```

Being opt-in, it is blunt. It also rejects pairs some callers read as equal: `IntEnum` against `int`, a
`dict` subclass against `dict`, `float` against `int`.

##### What the walk takes apart

"Any depth" runs through every value the comparison takes apart:

- a mapping, a list, a tuple and a `collections.deque`
- a record: a dataclass, a named tuple, an attrs class, a Pydantic model
- an object compared by an `==` of its own, read by its attributes

- `tolerance` and `comparators` reach the first two kinds in full.
- An object of the last kind is asked its own `==` first, unless a comparator owns it by class or by the
  name it sits under. That `==` stays the judge: two objects it holds apart stay apart, under a tolerance
  and under a comparator for what they hold. Where it holds them equal, each attribute the two hold equal
  is then checked as any other node: its type, a comparator that owns it, what it holds. An attribute they
  differ on is left to that `==`.
- Under `ignore=` or `include=`, a plain object is
  [read by its attributes](#selective-comparison-ignore--include) and its own `==` is not asked, so a
  `tolerance` beside them reaches the attributes. Two objects of a class without its own `==`, holding `1.0`
  and `1.05`, differ under `tolerance=0.1` and are equal under `tolerance=0.1, ignore="absent"`.
- A dataclass is read by its fields either way.

```python
class User:
    def __init__(self, active):
        self.active = active

    def __eq__(self, other):
        return type(other) is User and self.active == other.active


assert_that(User(1)).is_equal_to(User(True))                             # passes: 1 == True
assert_that(User(1)).not_.is_equal_to(User(True), strict_types=True)     # an int is no bool
```

Four things stay with the object's own `==`:

- an attribute the two hold apart, which that `==` leaves out or reads its own way
- an attribute only one side has, such as a cache one instance has filled
- an object that keeps anything outside its `__dict__`: one with `__slots__`, one written in C, or a
  deque of a class of your own
- a value of a number, text, date, time, enum, UUID or path class, which is one value whatever
  attributes it carries

One attribute is walked in full, with every option: a value that holds itself, which `==` cannot
answer for, so nothing says whether the object holds it equal or apart.

When several comparison options meet on one leaf, they resolve in a fixed order:

**`ignore_null` &rarr; `comparators` &rarr; identity &rarr; `strict_types` &rarr; `tolerance`.**

It reads as two groups. The first two decide whether the leaf is compared at all (`ignore_null`) and
whether your own code replaces the comparison (`comparators`). The rest compute equality, from the most
decisive test to the most forgiving: the same object, then the same type, then a numeric allowance. Two
consequences:

- `tolerance` and `strict_types` only ever combine within one type, `float` against `float`. The
  classic tolerance case, a `Decimal` from a database column against a `float` from JSON, fails on the
  type before the tolerance is consulted.
- A matcher on the expected side is exempt, so composed matchers keep working, and a spec that mixes
  literals with matchers gets strictness on its literal half only.

```python
assert_that({"id": 7}).is_equal_to({"id": match.greater_than(0)}, strict_types=True)
```

Identity sits in that chain because forcing the walk would otherwise take it away. A subnode shared by
both sides is matched by identity and not walked again, exactly as Python does inside a container, so
a config object placed in two expected blocks stays cheap and a container holding the same `NaN` on
both sides keeps comparing equal.

Anything matched **by hash** is covered too, which means dictionary keys and set members.

`1`, `1.0` and `True` hash alike and compare equal, so a mapping finds the pair before anything looks
at its type. Reaching the type takes a second pass:

<!-- docs-guard: raises -->
```python
assert_that({True: "a"}).is_equal_to({1: "a"}, strict_types=True)   # fails
```

Sets read the same way: `{1}` against `{1.0}` fails a strict comparison for the same reason.

A tuple or a frozenset used as a key or as a member is read all the way in, so `{(1, 2): "a"}` against
`{(True, 2): "a"}` fails as well. Those two are the containers a hash reads through. A record used as
a key is compared by its class alone, and so is a tuple or a frozenset of a class with an `==` of its
own.

The one limit is cost. Strictness turns off the fast path, because a container's own `==` says nothing
about the types inside it, so every comparison walks the whole structure in Python.

On a list of 20 000 dicts that is 0.3 ms against 41 ms. It matters only if you compare large dumps in
a loop.

Inside a [structural spec](matchers.md#structural-matching) the same relation is spelled
`match.equal_to(value, strict_types=True)`, one matcher covering value and type together:

```python
assert_that({"active": True}).matches_structure({"active": match.equal_to(True, strict_types=True)})
```

To assert the type alone, `match.is_type_of()` rejects a subclass where `match.is_instance_of()`
accepts one:

```python
assert_that({"n": 1}).matches_structure({"n": match.is_type_of(int)})         # passes
assert_that({"n": True}).matches_structure({"n": match.is_instance_of(int)})  # passes: bool is an int
```

To negate it, invert the whole assertion with `.not_` rather than looking for the flag on
`is_not_equal_to`, which takes no comparison options:

```python
assert_that({"active": True}).not_.is_equal_to({"active": 1}, strict_types=True)
```

### Dict flattening

Lists of dicts can be flattened on a key with `extracting` (see
[extracting attributes](#extracting-attributes-from-objects)):

```python
people = [{"first_name": "Fred"}, {"first_name": "Bob"}]
assert_that(people).extracting("first_name").is_equal_to(["Fred", "Bob"])
```

### Dict key assertions

Assert against the value of a key by prepending `has_` to the key name (see
[dynamic assertions](#dynamic-assertions-on-objects)):

<!-- docs-guard: untyped -->
```python
fred = {"first_name": "Fred", "last_name": "Smith", "shoe_size": 12}
assert_that(fred).has_first_name("Fred").has_shoe_size(12)
```

## Sets

```python
assert_that(set()).is_empty().is_type_of(set)
assert_that({"a", "b"}).is_length(2).is_equal_to({"b", "a"})
assert_that({"a", "b"}).contains("b", "a").does_not_contain("x")
assert_that({"a", "b"}).contains_only("a", "b")
assert_that({"a", "b"}).is_subset_of({"a", "b", "c"})
assert_that({"a", "b"}).is_subset_of({"a"}, {"b"})
```

## Booleans

```python
assert_that(True).is_true()
assert_that(False).is_false()
assert_that(True).is_type_of(bool)
```

### None

```python
assert_that(None).is_none()
assert_that("").is_not_none()
assert_that(None).is_type_of(type(None))
```

## Dates

`assertpy` supports dates via the `datetime` type.

```python
import datetime

today = datetime.datetime.today()
yesterday = today - datetime.timedelta(days=1)

assert_that(yesterday).is_before(today)
assert_that(today).is_after(yesterday)
assert_that(today).is_before_or_equal_to(today)
assert_that(today).is_after_or_equal_to(yesterday)
```

`is_before()` and `is_after()` take a `datetime` and refuse a `date`. Two dates are ordered by the
assertions every ordered value has:

```python
day, later = datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)

assert_that(day).is_less_than(later).is_between(day, later)
```

Closeness of two datetimes takes a `timedelta`, `is_close_to(other, datetime.timedelta(seconds=2))`,
and refuses a number of seconds. `match.is_now()` takes either, seconds or a `timedelta`.

Both operands must agree on awareness.

Comparing a timezone-naive datetime with an aware one raises a `TypeError` rather than answering. The
naive value carries no zone, so there is no instant to compare it by.

This holds for the `ignoring_*` assertions too. They would otherwise compare wall-clock fields and call
two moments hours apart equal.

<!-- docs-guard: skip -->
```python
naive = datetime.datetime(2020, 1, 2, 3, 4, 5)
aware = datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)

assert_that(naive).is_before(aware)                      # TypeError
assert_that(naive).is_equal_to_ignoring_seconds(aware)   # TypeError
```

Make both aware or both naive first, then the comparison is well defined. Two aware values need not share
a zone: the `ignoring_*` assertions read the expected side on the subject's clock before comparing, so
`12:00Z` and `17:00+05:00` are the same instant to the second, and `12:00+05:00` is not.

Equality can ignore units of time, and the numeric comparisons work on dates too:

<!-- docs-guard: skip -->
```python
assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
assert_that(today).is_equal_to_ignoring_seconds(today_0s)
assert_that(today).is_equal_to_ignoring_time(today_0h)

assert_that(middle).is_between(yesterday, today)
# tolerance is a timedelta
assert_that(yesterday).is_close_to(today, datetime.timedelta(hours=24))
```

Date properties can be asserted dynamically with `has_<property>` (see
[dynamic assertions](#dynamic-assertions-on-objects)):

<!-- docs-guard: untyped -->
```python
x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)
assert_that(x).has_year(1980).has_month(1).has_day(2)
assert_that(x).has_hour(3).has_minute(4).has_second(5).has_microsecond(6)
```

## Files

<!-- docs-guard: skip -->
```python
assert_that("foo.txt").exists().is_file()
assert_that("missing.txt").does_not_exist()
assert_that("mydir").is_directory()

assert_that("foo.txt").is_named("foo.txt").is_child_of("mydir")
assert_that("foo.txt").is_readable().is_writable()
assert_that("/usr/bin/python").is_executable()
```

Read a file into a string with `contents_of()` (default encoding `utf-8`) and continue with string
assertions:

<!-- docs-guard: skip -->
```python
from assertpy import assert_that, contents_of

assert_that(contents_of("foo.txt", "ascii")).starts_with("foo").ends_with(
    "bar"
).contains("oob")
```

## Bytes / bytearray

Assertions for `bytes` and `bytearray` values:

```python
assert_that(b"hello world").is_valid_utf8()
assert_that(b"hello").is_valid_encoding("ascii")
assert_that(b"\x89PNG").has_byte_at(0, 0x89)            # IndexError if out of range
assert_that(b"\xab\xcd\xef").is_hex_equal_to("abcdef")
```

`starts_with()`, `ends_with()` and `contains()` handle byte strings themselves, so a prefix, a suffix
and a subsequence read the same way they do for text:

```python
assert_that(b"\x89PNG\r\n\x1a\n").starts_with(b"\x89PNG")
assert_that(b"hello world").ends_with(b"world")
assert_that(b"hello world").contains(b"world")
```

`starts_with_bytes()` and `contains_bytes()` are the bytes-only spellings of the first and the last, kept
for the code that already uses them. They delegate, so all four report the same way.

`decoded_as()` returns a new builder with the decoded string so string assertions can continue
(`UnicodeDecodeError` is raised if decoding fails):

```python
assert_that(b"hello").decoded_as("utf-8").starts_with("hel").is_length(5)
assert_that(b"hello").decoded_as().is_equal_to("hello")  # default encoding utf-8
```

It is also the way to a pattern. `matches()` and `match.matches_regex()` take text, and refuse bytes and
a bytes pattern:

- Text that arrived as bytes: `decoded_as("utf-8").matches(r"...")`.
- Binary data that is not valid text raises the codec's `UnicodeDecodeError` there. Check it with
  `starts_with()`, `ends_with()` or `contains()` and a bytes operand.

All bytes assertions work with soft assertions, warn mode, and `.not_` negation.

## Objects

<!-- docs-guard: skip -->
```python
fred = Person("Fred", "Smith")

assert_that(fred).is_not_none().is_type_of(Person).is_instance_of(object)
assert_that(fred).is_instance_of_any(Person, dict)
assert_that(fred).is_instance_of(Person | dict)            # a union
assert_that(fred).is_instance_of((Person, (dict, str)))    # a tuple, nested to any depth
assert_that(Person).is_subclass_of(object)
assert_that(fred).is_same_as(fred)
assert_that(fred.say_hello).is_callable()
assert_that(fred.first_name).is_not_callable()

assert_that(fred.first_name).is_equal_to("Fred")
assert_that(fred.name).is_equal_to("Fred Smith")          # property
assert_that(fred.say_hello()).is_equal_to("Hello, Fred!")  # method
```

`is_equal_to` compares values. It does not ask whether the corresponding parts of two structures are the
same object, so a copy that rebuilt what it should have shared still passes. To require two members to
be one object, compare them with `is_same_as`:

<!-- docs-guard: skip -->
```python
assert_that(config["primary"]).is_same_as(config["fallback"])
```

### Recursive field assertions

`all_fields_satisfy` walks the whole object graph (mappings, dataclasses, namedtuples, attrs classes,
Pydantic models, lists, tuples) and applies one [matcher](matchers.md) or callable to every scalar leaf, reporting the path
of each leaf that does not satisfy it. `has_no_none_fields` is the common special case:

<!-- docs-guard: skip -->
```python
assert_that({"a": 1, "nested": {"b": 2}}).all_fields_satisfy(match.is_positive())
assert_that([1, [2, 3]]).all_fields_satisfy(lambda x: x > 0)
assert_that({"id": 1, "profile": {"name": "Alice"}}).has_no_none_fields()

assert_that({"a": 1, "b": {"c": -2}}).all_fields_satisfy(match.is_positive())  # fails
# Expected all fields to satisfy a positive value, but 1 field did not.
# diff (match):
#   b.c: expected a positive value, but was -2
```

- Scalars, strings and sets are single leaves. For element-wise set checks use `each` / `all_satisfy`.
- A value met again inside itself is not walked a second time.
- A Pydantic model is walked through the values its fields hold, the way the diff reads it: a field
  declared `exclude=True` is walked, a `@computed_field` is not, and a `@field_serializer` does not apply.

### Extracting attributes from objects

Flatten a collection of objects on an attribute, property, or zero-argument method with `extracting`:

<!-- docs-guard: skip -->
```python
people = [Person("Fred", "Smith"), Person("Bob", "Barr")]

assert_that(people).extracting("first_name").contains("Fred", "Bob")
assert_that(people).extracting("first_name", "last_name").contains(
    ("Fred", "Smith"), ("Bob", "Barr")
)
# property
assert_that(people).extracting("name").contains("Fred Smith", "Bob Barr")
# zero-argument method
assert_that(people).extracting("say_hello").contains("Hello, Fred!", "Hello, Bob!")
```

It also works on collections of dicts (extracting by key), Pydantic models, and across subclasses in a mixed collection.

#### Filtering

`filter` keeps only items for which it is truthy. It may be a key/attribute name, a dict of
key-value pairs that must all match, or a predicate:

```python
users = [
    {"user": "Fred", "active": True, "age": 25},
    {"user": "Johnny", "active": True, "age": 18},
    {"user": "Bob", "active": False, "age": 30},
]

assert_that(users).extracting("user", filter="active").is_equal_to(["Fred", "Johnny"])
assert_that(users).extracting("user", filter={"active": False}).is_equal_to(["Bob"])
assert_that(users).extracting("user", filter=lambda x: x["age"] > 20).is_equal_to(
    ["Fred", "Bob"]
)
```

#### Sorting

`sort` orders the extracted items. It may be a key/attribute name, an iterable of names (tie-breaking
left to right), or a key function. `None` means no ordering. Anything else is a mistake and raises a
`TypeError`, rather than quietly handing back unsorted items for a later assertion to trip over:

<!-- docs-guard: skip -->
```python
assert_that(users).extracting("user", sort="age").is_equal_to(["Johnny", "Fred", "Bob"])
assert_that(users).extracting("user", sort=["active", "age"]).is_equal_to(
    ["Bob", "Johnny", "Fred"]
)
assert_that(users).extracting("user", sort=lambda x: -x["age"]).is_equal_to(
    ["Bob", "Fred", "Johnny"]
)
```

### Dynamic assertions on objects

`assertpy` exposes `has_<name>()` for any attribute, property, or zero-argument method on the value,
so attribute checks stay compact:

<!-- docs-guard: skip -->
```python
fred = Person("Fred", "Smith")

assert_that(fred).has_first_name("Fred")     # attribute
assert_that(fred).has_name("Fred Smith")     # property
assert_that(fred).has_say_hello("Hello, Fred!")  # zero-arg method
```

Dynamic assertions also work on dicts, keyed by entry name:

<!-- docs-guard: untyped -->
```python
assert_that(
    {"first_name": "Fred", "last_name": "Smith"}
).has_first_name("Fred").has_last_name("Smith")
```

A failure is the one `is_equal_to()` gives for the value read: `failure.actual` is that value,
`failure.expected` the operand, and `failure.diff` their diff.

## Exceptions

Exception and warning assertions wrap a *callable* rather than a value: you assert on what calling the
function does, then chain assertions on the resulting message.

<!-- docs-guard: skip -->
```python
assert_that(some_func).raises(RuntimeError).when_called_with("foo")
assert_that(deprecated_func).warns(DeprecationWarning).when_called_with("foo")
```

See [Errors & Reporting](errors.md) for the full set:

- [expected exceptions](errors.md#expected-exceptions) and [warnings](errors.md#expected-warnings)
- the cause chain (`caused_by()`, `has_root_cause()`) and exception groups (`contains_error()`,
  `does_not_contain_error()`, `matches_error_tree()`, `errors()`, `error_of()`)
- pivoting to the raised exception (`raised()`) or the call's return value (`returned()`).
