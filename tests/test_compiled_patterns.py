"""A pattern compiled with ``re.compile()`` goes wherever its text goes, flags and all."""

from __future__ import annotations

import functools
import itertools
import operator
import re

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match

_TEXT = "first line\nSecond Line"

# each is missed as plain text and found once compiled with its flag
_FLAGGED = [
    pytest.param(r"line.Second", re.DOTALL, id="dotall"),
    pytest.param(r"second line", re.IGNORECASE, id="ignorecase"),
    pytest.param(r"^Second", re.MULTILINE, id="multiline"),
]

_PATTERN_TAKERS = [
    pytest.param(lambda pattern: assert_that("text").matches(pattern), id="matches"),
    pytest.param(lambda pattern: assert_that("text").does_not_match(pattern), id="does_not_match"),
    pytest.param(lambda pattern: assert_that("text").extracting_group(pattern), id="extracting_group"),
    pytest.param(lambda pattern: assert_that("text").matches_with_groups(pattern), id="matches_with_groups"),
    pytest.param(match.matches_regex, id="match.matches_regex"),
]


class _Text(str):
    pass


class _Lookalike:
    """A third-party pattern: it searches, and it is no `re.Pattern`."""

    pattern = "t"

    def search(self, text: str) -> re.Match[str] | None:
        return re.search(self.pattern, text)


class TestTheFlagOfACompiledPatternDecidesTheVerdict:
    @pytest.mark.parametrize(("pattern", "flags"), _FLAGGED)
    def test_matches_and_does_not_match(self, pattern, flags):
        compiled = re.compile(pattern, flags)
        assert_that(_TEXT).does_not_match(pattern).matches(compiled)
        with pytest.raises(AssertionFailure, match="to not match pattern"):
            assert_that(_TEXT).does_not_match(compiled)

    @pytest.mark.parametrize(("pattern", "flags"), _FLAGGED)
    def test_negated_and_as_a_verdict(self, pattern, flags):
        compiled = re.compile(pattern, flags)
        assert_that(_TEXT).not_.does_not_match(compiled)
        assert_that(assert_that(_TEXT).check().matches(compiled).passed).is_true()
        assert_that(assert_that(_TEXT).check().matches(pattern).passed).is_false()

    @pytest.mark.parametrize(("pattern", "flags"), _FLAGGED)
    def test_the_groups(self, pattern, flags):
        compiled = re.compile(f"({pattern})", flags)
        found = compiled.search(_TEXT)
        assert_that(found).is_not_none()
        assert_that(_TEXT).extracting_group(compiled, 1).is_equal_to(found.group(1))
        assert_that(_TEXT).matches_with_groups(compiled).is_equal_to((found.group(1),))

    @pytest.mark.parametrize(("pattern", "flags"), _FLAGGED)
    def test_the_matcher(self, pattern, flags):
        assert_that(match.matches_regex(re.compile(pattern, flags)).matches(_TEXT)).is_true()
        assert_that(match.matches_regex(pattern).matches(_TEXT)).is_false()


class TestTheGroupsOfACompiledPattern:
    def test_a_named_group(self):
        assert_that(_TEXT).extracting_group(re.compile(r"(?P<word>second) line", re.IGNORECASE), "word").is_equal_to(
            "Second"
        )
        assert_that(_TEXT).matches_with_groups(
            re.compile(r"(?P<word>second) (?P<noun>line)", re.IGNORECASE)
        ).is_equal_to({"word": "Second", "noun": "Line"})

    def test_the_whole_match_of_a_pattern_without_a_group(self):
        assert_that(_TEXT).extracting_group(re.compile(r"second LINE", re.IGNORECASE)).is_equal_to("Second Line")
        assert_that(_TEXT).matches_with_groups(re.compile(r"second LINE", re.IGNORECASE)).is_equal_to(())

    def test_a_group_the_pattern_has_not_got(self):
        with pytest.raises(AssertionFailure, match="to have group <5>"):
            assert_that(_TEXT).extracting_group(re.compile(r"(line)", re.IGNORECASE), 5)

    def test_an_optional_group_left_unmatched(self):
        with pytest.raises(AssertionFailure, match="to be matched in"):
            assert_that(_TEXT).extracting_group(re.compile(r"FIRST(?:(\d+))?", re.IGNORECASE), 1)


class TestAFailureNamesTheCompiledPattern:
    def test_matches_prints_its_flags_and_keeps_the_object(self):
        compiled = re.compile("F", re.IGNORECASE)
        with pytest.raises(AssertionFailure) as caught:
            assert_that("bar").matches(compiled)
        assert_that(str(caught.value)).is_equal_to(
            "Expected <bar> to match pattern <re.compile('F', re.IGNORECASE)>, but did not."
        )
        assert_that(caught.value.expected).is_same_as(compiled)

    def test_does_not_match_prints_it_as_well(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that("foo").does_not_match(re.compile("F", re.IGNORECASE))
        assert_that(str(caught.value)).is_equal_to(
            "Expected <foo> to not match pattern <re.compile('F', re.IGNORECASE)>, but did."
        )

    @pytest.mark.parametrize(
        "ask",
        [
            pytest.param(lambda pattern: assert_that("bar").extracting_group(pattern), id="extracting_group"),
            pytest.param(lambda pattern: assert_that("bar").matches_with_groups(pattern), id="matches_with_groups"),
        ],
    )
    def test_a_pivot_that_found_nothing_keeps_the_object(self, ask):
        compiled = re.compile("(F)", re.IGNORECASE)
        with pytest.raises(AssertionFailure, match=re.escape("pattern <re.compile('(F)', re.IGNORECASE)>")) as caught:
            ask(compiled)
        assert_that(caught.value.expected).is_same_as(compiled)

    def test_the_matcher_describes_it(self):
        compiled = re.compile("F", re.IGNORECASE)
        assert_that(match.matches_regex(compiled).pattern).is_same_as(compiled)
        assert_that(match.matches_regex(compiled).describe()).is_equal_to(
            "a string matching pattern <re.compile('F', re.IGNORECASE)>"
        )
        with pytest.raises(AssertionFailure, match=re.escape("<re.compile('F', re.IGNORECASE)>")):
            assert_that(["bar"]).contains(match.matches_regex(compiled))


class TestWhatIsNoPatternOfText:
    @pytest.mark.parametrize("take", _PATTERN_TAKERS)
    @pytest.mark.parametrize(
        ("pattern", "shown"),
        [
            pytest.param(re.compile(b"t"), "<re.compile(b't')> (Pattern)", id="compiled-from-bytes"),
            pytest.param(b"t", "<b't'> (bytes)", id="bytes"),
            pytest.param(123, "<123> (int)", id="int"),
            pytest.param(None, "<None> (NoneType)", id="none"),
        ],
    )
    def test_is_refused_by_type(self, take, pattern, shown):
        with pytest.raises(TypeError) as caught:
            take(pattern)
        assert_that(str(caught.value)).is_equal_to(
            f"given pattern arg must be a string or a pattern compiled from one, but was {shown}"
        )

    @pytest.mark.parametrize("take", _PATTERN_TAKERS)
    def test_a_lookalike_from_another_library_is_refused(self, take):
        with pytest.raises(TypeError, match=r"given pattern arg must be a string or a pattern compiled from one"):
            take(_Lookalike())

    @pytest.mark.parametrize("take", _PATTERN_TAKERS)
    @pytest.mark.parametrize("pattern", [re.compile(""), "", _Text("")], ids=["compiled", "text", "subclass"])
    def test_an_empty_pattern_is_refused(self, take, pattern):
        with pytest.raises(ValueError) as caught:
            take(pattern)
        assert_that(str(caught.value)).is_equal_to("given pattern arg must not be empty")

    @pytest.mark.parametrize("take", _PATTERN_TAKERS)
    def test_text_that_is_no_pattern_still_raises_as_re_does(self, take):
        with pytest.raises(re.error):
            take("(")

    def test_a_subclass_of_str_is_text(self):
        assert_that("text").matches(_Text("^t")).does_not_match(_Text("z"))
        assert_that("text").extracting_group(_Text("(e)"), 1).is_equal_to("e")
        assert_that("text").matches_with_groups(_Text("(e)(x)")).is_equal_to(("e", "x"))
        assert_that(match.matches_regex(_Text("x$")).matches("text")).is_false()

    def test_the_value_is_refused_before_the_pattern(self):
        with pytest.raises(TypeError) as caught:
            assert_that(123).matches(re.compile(b"t"))
        assert_that(str(caught.value)).is_equal_to("val must be a string, but was <123> (int)")


_FLAG_LETTERS = [(re.IGNORECASE, "i"), (re.MULTILINE, "m"), (re.DOTALL, "s")]
_FLAG_SUBSETS = [list(chosen) for size in range(4) for chosen in itertools.combinations(_FLAG_LETTERS, size)]


def _answers(text: str, pattern: str | re.Pattern[str]) -> tuple[bool, object, object]:
    """The verdict of `matches()`, and what the two pivots hand on when it holds."""
    if not assert_that(text).check().matches(pattern).passed:
        return False, None, None
    return (
        True,
        assert_that(text).extracting_group(pattern).val,
        assert_that(text).matches_with_groups(pattern).val,
    )


@pytest.mark.parametrize("pattern", [r"a.b", r"^b", r"a$", r"(a)(b)?", r"(?P<run>[ab]+)\n?", r"A|B", r"(a)\n(B)"])
@pytest.mark.parametrize("chosen", _FLAG_SUBSETS, ids=lambda chosen: "".join(letter for _, letter in chosen) or "none")
@given(text=st.text(alphabet="abAB\n", max_size=8))
@example(text="a\nb")
@example(text="A\nB")
@example(text="b")
def test_a_compiled_pattern_answers_as_its_text_with_the_same_flags_inline(pattern, chosen, text):
    flags = functools.reduce(operator.or_, (flag for flag, _ in chosen), 0)
    inline = (f"(?{''.join(letter for _, letter in chosen)})" if chosen else "") + pattern
    assert_that(_answers(text, re.compile(pattern, flags))).is_equal_to(_answers(text, inline))
