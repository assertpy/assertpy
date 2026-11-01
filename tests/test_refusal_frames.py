"""A refusal's traceback under pytest: the line of the test, and none of the library's.

A failed assertion showed the test line alone, since every assertion module hides its frames.  A refusal passed
through modules that did not: `match.each_item(str)` showed four frames of the library under the line that wrote
it, and `assert_that(5).is_length(1)` two.  A refusal now marks its own frame where it raises, with a name of
the library's own, and those modules hide their frames only for an exception born in a frame so marked.  Anything
else keeps them: what the caller's code or another library raised, and a defect of this one, whose frames are
what locate it.
"""

from __future__ import annotations

import ast
import datetime
import pathlib
import re

import pytest

from assertpy import BaseMatcher, assert_that, match, register_matcher, unregister_matcher
from assertpy._engine import _ordering, _require

_HERE = pathlib.Path(__file__)


def _shown(caught: pytest.ExceptionInfo[BaseException]) -> list[str]:
    """The files of the frames pytest prints for *caught*, the hidden ones left out as its report leaves them."""
    return [pathlib.Path(str(entry.path)).name for entry in caught.traceback.filter(caught)]


def _mine(value: object) -> bool:
    raise RuntimeError("mine")


def _mine_and_hidden(value: object) -> bool:
    __tracebackhide__ = True
    raise RuntimeError("mine")


async def _answers_later(value: object) -> bool:
    return True


def _register_twice() -> None:
    register_matcher("taken_for_this_test")(lambda: match.is_uuid())
    try:
        register_matcher("taken_for_this_test")(lambda: match.is_positive())
    finally:
        unregister_matcher("taken_for_this_test")


def _born_in_the_package(body: str):
    """A function running *body* in a frame of a module that answers pytest as the four modules do."""
    scope = {"__tracebackhide__": _require.raised_on_purpose}
    exec(compile(f"def born():\n    {body}\n", _require.__file__, "exec"), scope)
    return scope["born"]


def _blocks(node: ast.AST) -> list[list[ast.stmt]]:
    """Every list of statements *node* holds: its body, what follows an ``else``, its handlers' own."""
    return [block for name in ("body", "orelse", "finalbody") if isinstance(block := getattr(node, name, None), list)]


def _marks(statement: ast.stmt) -> bool:
    """Whether *statement* is a frame saying it refuses on purpose, inside a function."""
    return (
        isinstance(statement, ast.Assign)
        and statement.col_offset > 0
        and [ast.unparse(target) for target in statement.targets] == ["_assertpy_refusal"]
        and ast.unparse(statement.value) == "True"
    )


def _raises_what_is_in_hand(statement: ast.stmt) -> bool:
    """Whether *statement* raises a class, or a class called with literals and names alone."""
    if not isinstance(statement, ast.Raise):
        return False
    raised = statement.exc
    if isinstance(raised, ast.Name):
        return True
    return (
        isinstance(raised, ast.Call)
        and isinstance(raised.func, ast.Name)
        and not raised.keywords
        and all(isinstance(argument, (ast.Constant, ast.Name)) for argument in raised.args)
    )


class _Mine:
    """A matcher of the caller's own, whose verdict raises."""

    def __init__(self, *, hides_itself: bool = False) -> None:
        self._asked = _mine_and_hidden if hides_itself else _mine

    def matches(self, value: object) -> bool:
        return self._asked(value)

    def describe(self) -> str:
        return "mine"

    def describe_mismatch(self, value: object) -> str:
        return "was not mine"


class TestARefusalShowsNoFrameOfTheLibrary:
    @pytest.mark.parametrize(
        ("ask", "refusal"),
        [
            pytest.param(lambda: match.each_item(str), TypeError, id="a factory handed no matcher"),
            pytest.param(lambda: match.has_property("id", 5), TypeError, id="a nested matcher that is none"),
            pytest.param(lambda: match.is_uuid() | 5, TypeError, id="an operator handed no matcher"),
            pytest.param(lambda: match.is_now(-5), ValueError, id="a negative delta"),
            pytest.param(lambda: match.between(5, 1), ValueError, id="bounds the wrong way round"),
            pytest.param(lambda: match.is_length("x"), TypeError, id="a length that is no integer"),
            pytest.param(lambda: assert_that(5).is_length(1), TypeError, id="a value with no size"),
            pytest.param(lambda: assert_that("a").is_length("x"), TypeError, id="an argument that is no integer"),
            pytest.param(lambda: assert_that({"a": 1}).matches_structure([1]), TypeError, id="a spec that is no dict"),
            pytest.param(lambda: assert_that(1).satisfies("no matcher"), TypeError, id="a predicate that is none"),
            pytest.param(lambda: assert_that([1]).contains(match.between(5, 1)), ValueError, id="inside an assertion"),
            pytest.param(lambda: register_matcher("not a name"), ValueError, id="a matcher name that is no name"),
            pytest.param(lambda: register_matcher("is_uuid"), ValueError, id="a matcher name already built in"),
            pytest.param(_register_twice, ValueError, id="a matcher name already taken"),
            pytest.param(lambda: unregister_matcher("never_registered"), KeyError, id="a matcher never registered"),
            pytest.param(lambda: match.never_registered, AttributeError, id="a matcher that is not there"),
            pytest.param(lambda: BaseMatcher().matches(1), NotImplementedError, id="a matcher with no verdict"),
            pytest.param(lambda: BaseMatcher().evaluate(1), NotImplementedError, id="a matcher with no evaluation"),
            pytest.param(lambda: BaseMatcher().describe(), NotImplementedError, id="a matcher with no description"),
            pytest.param(lambda: match.close_to(1, -1), ValueError, id="a negative tolerance"),
            pytest.param(lambda: match.is_length(-1), ValueError, id="a negative length"),
            pytest.param(lambda: match.is_divisible_by(0), ValueError, id="a divisor of zero"),
            pytest.param(lambda: match.contains(), ValueError, id="no item to contain"),
            pytest.param(lambda: match.contains_only(), ValueError, id="no item to contain only"),
            pytest.param(lambda: match.is_subset_of(), ValueError, id="no superset"),
            pytest.param(lambda: match.is_now(datetime.timedelta(seconds=-1)), ValueError, id="a negative span"),
            pytest.param(lambda: match.is_now(float("inf")), ValueError, id="a span no timedelta holds"),
            pytest.param(lambda: match.starts_with(""), ValueError, id="an empty prefix"),
            pytest.param(lambda: match.ends_with(b""), ValueError, id="an empty suffix"),
            pytest.param(lambda: match.matches_regex(""), ValueError, id="an empty pattern"),
            pytest.param(lambda: match.matches_regex(re.compile(b"x")), TypeError, id="a pattern of bytes"),
            pytest.param(lambda: assert_that("a").matches(re.compile("")), ValueError, id="an empty compiled pattern"),
            pytest.param(lambda: assert_that("a").matches(5), TypeError, id="a pattern that is no text"),
            pytest.param(lambda: assert_that(1).is_equal_to(1, tolerence=1), TypeError, id="an option misspelled"),
            pytest.param(lambda: assert_that(1).satisfies(_answers_later), TypeError, id="a verdict not awaited"),
            pytest.param(
                lambda: assert_that(1).satisfies(lambda value: match.is_positive()),
                TypeError,
                id="a matcher for a verdict",
            ),
        ],
    )
    def test_only_the_line_that_wrote_it_is_shown(self, ask, refusal):
        with pytest.raises(refusal) as caught:
            ask()

        assert_that(_shown(caught)).is_not_empty().contains_only(_HERE.name)

    def test_a_failed_assertion_shows_the_same(self):
        with pytest.raises(AssertionError) as caught:
            assert_that(1).is_equal_to(2)

        assert_that(_shown(caught)).is_not_empty().contains_only(_HERE.name)

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda: assert_that([1]).each(_mine), id="a predicate"),
            pytest.param(lambda: assert_that({"a": 1}).matches_structure({"a": _Mine()}), id="a matcher in a spec"),
            pytest.param(lambda: assert_that([1]).contains(_Mine()), id="a matcher in a membership"),
        ],
    )
    def test_code_of_the_callers_own_that_raises_is_where_the_traceback_ends(self, ask):
        with pytest.raises(RuntimeError, match="mine") as caught:
            ask()

        assert_that([entry.name for entry in caught.traceback.filter(caught)][-1]).is_equal_to("_mine")

    def test_what_the_callers_code_raised_keeps_the_frames_that_asked_it(self):
        with pytest.raises(RuntimeError, match="mine") as caught:
            assert_that({"a": 1}).matches_structure({"a": _Mine()})

        assert_that(_shown(caught)).contains("_matcher_impls.py")

    def test_the_frames_are_still_there_for_a_reader_who_asks_for_all_of_them(self):
        with pytest.raises(TypeError) as caught:
            match.each_item(str)

        every = [pathlib.Path(str(entry.path)).name for entry in caught.traceback]
        assert_that(every).contains("matchers.py", "_matcher_impls.py", "_require.py")


class TestADefectOfTheLibrarysOwnKeepsItsFrames:
    """An exception born inside the package by anything but a ``raise`` statement is no refusal."""

    def test_a_call_that_fails_inside_the_refusal_itself(self, monkeypatch):
        monkeypatch.setattr(_require, "_shown", 5)

        with pytest.raises(TypeError, match="not callable") as caught:
            match.each_item(str)

        assert_that(_shown(caught)).contains("matchers.py", "_matcher_impls.py", "_require.py")

    def test_a_call_that_fails_inside_the_integer_check(self, monkeypatch):
        monkeypatch.setattr(_ordering, "refuse", 5)

        with pytest.raises(TypeError, match="not callable") as caught:
            match.is_length("x")

        assert_that(_shown(caught)).contains("matchers.py", "_ordering.py")

    @pytest.mark.parametrize(
        ("body", "raised"),
        [
            pytest.param('raise RuntimeError("an invariant")', RuntimeError, id="an invariant"),
            pytest.param('raise ValueError("an invariant")', ValueError, id="an invariant raised as a refusal is"),
            pytest.param('assert 1 == 2, "an invariant"', AssertionError, id="an assert of the library's own"),
            pytest.param("return None + 1", TypeError, id="an operation that failed"),
            pytest.param('return __import__("inspect").signature(5)', TypeError, id="a call into another library"),
        ],
    )
    def test_what_is_born_in_an_unmarked_frame_of_the_package_keeps_it(self, body, raised):
        with pytest.raises(raised) as caught:
            _born_in_the_package(body)()

        assert_that([entry.name for entry in caught.traceback.filter(caught)]).contains("born")

    @pytest.mark.parametrize("raised", [TypeError, ValueError, KeyError, AttributeError, NotImplementedError])
    def test_what_a_frame_marked_as_a_refusal_raises_is_hidden(self, raised):
        body = f'_assertpy_refusal = True\n    raise {raised.__name__}("a refusal")'

        with pytest.raises(raised) as caught:
            _born_in_the_package(body)()

        assert_that([entry.name for entry in caught.traceback.filter(caught)]).does_not_contain("born")

    def test_a_mark_set_after_the_message_is_built_leaves_a_defect_in_building_it_shown(self):
        body = 'message = "a" + 5\n    _assertpy_refusal = True\n    raise TypeError(message)'

        with pytest.raises(TypeError, match="can only concatenate") as caught:
            _born_in_the_package(body)()

        assert_that([entry.name for entry in caught.traceback.filter(caught)]).contains("born")

    @pytest.mark.parametrize(
        "said",
        ["_assertpy_refusal = False", "__tracebackhide__ = True"],
        ids=["the mark set to no", "the flag of pytest's own"],
    )
    def test_only_the_mark_of_the_library_set_to_yes_is_a_refusal(self, said):
        scope = {"__tracebackhide__": _require.raised_on_purpose}
        source = f"def inner():\n    {said}\n    raise TypeError('no refusal')\ndef born():\n    inner()\n"
        exec(compile(source, _require.__file__, "exec"), scope)

        with pytest.raises(TypeError) as caught:
            scope["born"]()

        assert_that([entry.name for entry in caught.traceback.filter(caught)]).contains("born")

    def test_a_helper_of_the_callers_that_hides_itself_does_not_hide_the_frames_that_asked_it(self):
        with pytest.raises(RuntimeError, match="mine") as caught:
            assert_that({"a": 1}).matches_structure({"a": _Mine(hides_itself=True)})

        names = [entry.name for entry in caught.traceback.filter(caught)]
        assert_that(names).does_not_contain("_mine_and_hidden")
        assert_that(_shown(caught)).contains("_matcher_impls.py")

    def test_a_name_whose_repr_fails_while_the_refusal_is_worded_keeps_the_frame(self):
        class Name(str):
            __slots__ = ()

            def __repr__(self) -> str:
                raise RuntimeError("worded")

        with pytest.raises(RuntimeError, match="worded") as caught:
            register_matcher(Name("not a name"))

        assert_that(_shown(caught)).contains("matchers.py")

    @pytest.mark.parametrize("module", ["matchers.py", "_matcher_impls.py", "_engine/_require.py"])
    def test_nothing_is_evaluated_between_a_mark_and_its_raise(self, module):
        """A message is built before the mark, so a defect in building it is born in a frame not yet marked."""
        tree = ast.parse((_HERE.parents[1] / "assertpy" / module).read_text(encoding="utf-8"))
        blocks = [block for node in ast.walk(tree) for block in _blocks(node)]
        under = [block[index + 1] for block in blocks for index in range(len(block) - 1) if _marks(block[index])]
        evaluated = [ast.unparse(statement) for statement in under if not _raises_what_is_in_hand(statement)]

        assert_that(under).is_not_empty()
        assert_that(evaluated).is_empty()
        assert_that([block[-1] for block in blocks if block and _marks(block[-1])]).is_empty()

    @pytest.mark.parametrize("asked", [None, object()], ids=["nothing", "what holds no traceback"])
    def test_a_question_that_cannot_be_read_hides_as_before(self, asked):
        assert_that(_require.raised_on_purpose(asked)).is_true()
