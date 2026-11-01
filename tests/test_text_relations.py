"""A text held against a text: the failure says what alone keeps the relation from holding.

``"done\\n"`` does not end with ``"done"``, and the sentence prints a line break nobody sees.  Where the relation
the assertion asked holds once one thing is set aside, a line under the sentence names that thing: whitespace
at that end, case, the kind or amount of whitespace.  Each line is about the relation asked, prefix, suffix or
holding, and is said only where it is so.
"""

from __future__ import annotations

import enum

import pytest
from hypothesis import given
from hypothesis import strategies as st

from assertpy import AssertionFailure, _hints, assert_that


def _lines(call) -> list[str]:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return caught.value._message.splitlines()


def _reason(call) -> str | None:
    """The line under the sentence, or ``None`` where the failure is its sentence alone."""
    lines = _lines(call)
    return lines[-1] if not lines[-1].startswith("Expected <") and not lines[-1].endswith((".", "not.")) else None


class TestATextThatDoesNotStartOrEndWithAnother:
    @pytest.mark.parametrize(
        ("value", "prefix", "said"),
        [
            ("  Order 12", "Order", "the value starts with whitespace, and starts with the prefix past it"),
            ("\nOrder 12", "Order", "the value starts with a line break, and starts with the prefix past it"),
            ("Order 12", "order", "the value starts with the prefix once case is ignored"),
            (
                "Order 12",
                "Order  ",
                "the prefix given starts or ends with whitespace, and the value starts with it without that",
            ),
            ("new order 12", "order", "the value holds the prefix, and not at its start"),
            ("Order 12", "Invoice", None),
            ("Order 12", "12 Order", None),
        ],
    )
    def test_starts_with(self, value, prefix, said):
        assert_that(_hints.not_at_an_end(value, prefix, start=True)).is_equal_to(said)
        lines = _lines(lambda: assert_that(value).starts_with(prefix))
        assert_that(lines[-1]).is_equal_to(said) if said else assert_that(lines[-1]).ends_with(", but did not.")

    @pytest.mark.parametrize(
        ("value", "suffix", "said"),
        [
            ("done\n", "done", "the value ends with a line break, and ends with the suffix before it"),
            ("done\r\n", "done", "the value ends with a line break, and ends with the suffix before it"),
            ("done\r", "done", "the value ends with a line break, and ends with the suffix before it"),
            ("done\u2028", "done", "the value ends with whitespace, and ends with the suffix before it"),
            ("done\n\r", "done", "the value ends with whitespace, and ends with the suffix before it"),
            ("done  ", "done", "the value ends with whitespace, and ends with the suffix before it"),
            ("done\n\n", "done", "the value ends with whitespace, and ends with the suffix before it"),
            ("report.PDF", ".pdf", "the value ends with the suffix once case is ignored"),
            (
                "report.pdf",
                " .pdf",
                "the suffix given starts or ends with whitespace, and the value ends with it without that",
            ),
            ("done, almost", "done", "the value holds the suffix, and not at its end"),
            ("done", "finished", None),
        ],
    )
    def test_ends_with(self, value, suffix, said):
        assert_that(_hints.not_at_an_end(value, suffix, start=False)).is_equal_to(said)
        lines = _lines(lambda: assert_that(value).ends_with(suffix))
        assert_that(lines[-1]).is_equal_to(said) if said else assert_that(lines[-1]).ends_with(", but did not.")

    def test_the_narrowest_fact_is_the_one_said(self):
        # whitespace at the end before case, case before the text held elsewhere
        assert_that(_hints.not_at_an_end("Done\n", "Done", start=False)).contains("a line break")
        assert_that(_hints.not_at_an_end("done DONE", "done", start=False)).contains("once case is ignored")
        assert_that(_hints.not_at_an_end("order ORDER", "ORDER", start=True)).contains("once case is ignored")
        # two things at once are no one fact
        assert_that(_hints.not_at_an_end(" Order", "order", start=True)).is_none()

    @pytest.mark.parametrize(
        ("ask", "said"),
        [
            (
                lambda: assert_that("DONE\n").ends_with_ignoring_case("done"),
                "the value ends with a line break, and ends with the suffix before it",
            ),
            (
                lambda: assert_that("  ORDER 12").starts_with_ignoring_case("order"),
                "the value starts with whitespace, and starts with the prefix past it",
            ),
            (
                lambda: assert_that("new ORDER").starts_with_ignoring_case("order"),
                "the value holds the prefix, and not at its start",
            ),
            (
                lambda: assert_that("ORDER 12").ends_with_ignoring_case("12 "),
                "the suffix given starts or ends with whitespace, and the value ends with it without that",
            ),
        ],
    )
    def test_the_twins_that_do_not_mind_case_say_all_but_case(self, ask, said):
        assert_that(_lines(ask)[-1]).is_equal_to(said)

    def test_nothing_is_said_where_the_relation_holds(self):
        assert_that(_hints.not_at_an_end("Order", "Order", start=True)).is_none()
        assert_that(_hints.not_at_an_end("Order", "order", start=True, cased=False)).is_none()
        assert_that(_hints.not_in_text("Hello", "ell")).is_none()
        assert_that(_hints.not_in_text("Hello", "ELL", cased=False)).is_none()

    def test_a_twin_that_does_not_mind_case_never_names_case(self):
        assert_that(_hints.not_at_an_end("ORDER 12", "invoice", start=True, cased=False)).is_none()
        assert_that(_lines(lambda: assert_that("an Order").starts_with_ignoring_case("order"))[-1]).is_equal_to(
            "the value holds the prefix, and not at its start"
        )


class TestATextThatDoesNotHoldAnother:
    @pytest.mark.parametrize(
        ("value", "item", "said"),
        [
            ("Hello World", "world", "the value holds it once case is ignored"),
            ("Total:\xa042 EUR", "Total: 42", "the value holds it once every run of whitespace is read as one space"),
            ("first name\nAnn", "name Ann", "the value holds it once every run of whitespace is read as one space"),
            ("a\tb", "a b", "the value holds it once every run of whitespace is read as one space"),
            ("a  b", "a b", "the value holds it once every run of whitespace is read as one space"),
            (
                "Total:\n 42 EUR",
                "total: 42",
                "the value holds it once case is ignored and every run of whitespace is read as one space",
            ),
            ("Hello World", "planet", None),
            ("Hello World", "  ", "the value holds it once every run of whitespace is read as one space"),
            ("ab", " ab", None),
            ("a  b", "a b ", None),
        ],
    )
    def test_contains(self, value, item, said):
        assert_that(_hints.not_in_text(value, item)).is_equal_to(said)
        lines = _lines(lambda: assert_that(value).contains(item))
        assert_that(lines[-1]).is_equal_to(said) if said else assert_that(lines[-1]).ends_with(", but did not.")

    def test_the_twin_that_does_not_mind_case_says_the_whitespace(self):
        lines = _lines(lambda: assert_that("Total:\xa042").contains_ignoring_case("total: 42"))
        assert_that(lines[-1]).is_equal_to("the value holds it once every run of whitespace is read as one space")
        assert_that(_lines(lambda: assert_that("Total").contains_ignoring_case("sum"))).is_length(1)
        assert_that(_hints.not_in_text("Hello", "hello", cased=False)).is_none()

    def test_several_texts_not_held_get_no_line(self):
        lines = _lines(lambda: assert_that("Hello World").contains("hello", "world"))
        assert_that(lines).is_length(1)

    def test_an_item_of_a_list_is_no_text_held_in_a_text(self):
        assert_that(_lines(lambda: assert_that(["Hello"]).contains("hello"))).is_length(1)


class TestTwoTextsThatAreNotEqual:
    @pytest.mark.parametrize(
        ("value", "other", "apart"),
        [
            ("Oslo ", "oslo", "surrounding whitespace"),
            ("a\r\nb", "A\nB", "line endings"),
            ("a\r\nb ", "A\nB", "line endings and surrounding whitespace"),
            ("A\xa0b", "a B", "the kind or amount of whitespace"),
            ("a  b", "A B", "the kind or amount of whitespace"),
        ],
    )
    def test_ignoring_case_says_the_whitespace_that_holds_them_apart(self, value, other, apart):
        lines = _lines(lambda: assert_that(value).is_equal_to_ignoring_case(other))
        assert_that(lines[-1]).is_equal_to(f"the two are equal without regard to case but for {apart}")

    def test_ignoring_case_says_nothing_of_two_other_texts(self):
        assert_that(_lines(lambda: assert_that("Oslo").is_equal_to_ignoring_case("Bergen"))).is_length(1)
        # whitespace alone is looked for: what else `is_equal_to` names for two texts is not a thing of case
        assert_that(_lines(lambda: assert_that('{"a": 1}').is_equal_to_ignoring_case('{"A":1}'))).is_length(1)

    def test_ignoring_whitespace_says_case(self):
        lines = _lines(lambda: assert_that("Hello World").is_equal_to_ignoring_whitespace("hello  world"))
        assert_that(lines[-1]).is_equal_to("the two are equal ignoring whitespace once case is ignored too")
        assert_that(_lines(lambda: assert_that("Hello").is_equal_to_ignoring_whitespace("Bye"))).is_length(1)

    @pytest.mark.parametrize(
        ("value", "other", "said"),
        [
            ("Total:\xa042", "Total: 42", "the kind or amount of whitespace"),
            ("a  b", "a b", "the kind or amount of whitespace"),
            ("a\tb", "a b", "the kind or amount of whitespace"),
            ("a ", "a", "surrounding whitespace"),
            ("a\r\nb", "a\nb", "line endings"),
            ("a\r\nb ", "a\nb", "line endings and surrounding whitespace"),
            (b"a  b", "a b", "bytes against decoded text and the kind or amount of whitespace"),
        ],
    )
    def test_is_equal_to_names_the_narrowest_whitespace_and_the_kind_or_amount_last(self, value, other, said):
        lines = _lines(lambda: assert_that(value).is_equal_to(other))
        assert_that(lines[-1]).is_equal_to(f"every difference here is one of {said}")

    def test_an_enum_beside_text_that_differs_in_whitespace_is_two_facts(self):
        class Code(enum.Enum):
            OK = "all  good"

        lines = _lines(lambda: assert_that({"code": Code.OK}).is_equal_to({"code": "all good"}))
        assert_that(lines[-1]).is_equal_to(
            "every difference here is one of enum members against their values and the kind or amount of whitespace"
        )


class TestOnlyPlainTextIsRead:
    def test_a_text_of_a_class_of_its_own_gets_no_line(self):
        class Loud(str):
            __slots__ = ()

        value = Loud("Order 12")
        assert_that(_hints.not_at_an_end(value, "order", start=True)).is_none()
        assert_that(_hints.not_at_an_end("Order 12", Loud("order"), start=True)).is_none()
        assert_that(_hints.not_in_text(value, "order")).is_none()
        assert_that(_hints.not_in_text("Order 12", Loud("order"))).is_none()
        assert_that(_hints.but_for_whitespace(value, "order 12 ")).is_none()
        assert_that(_hints.but_for_whitespace("order 12 ", Loud("order 12"))).is_none()
        assert_that(_hints.but_for_case(value, "order 12")).is_none()
        assert_that(_hints.but_for_case("order 12", value)).is_none()
        assert_that(_lines(lambda: assert_that(value).starts_with("order"))).is_length(1)

    @pytest.mark.parametrize(
        "ask",
        [
            lambda text: assert_that(text("Oslo ")).is_equal_to_ignoring_case("oslo"),
            lambda text: assert_that("Oslo ").is_equal_to_ignoring_case(text("oslo")),
            lambda text: assert_that(text("Hello World")).is_equal_to_ignoring_whitespace("hello world"),
            lambda text: assert_that("Hello World").is_equal_to_ignoring_whitespace(text("hello world")),
            lambda text: assert_that(text("Hello World")).contains("world"),
            lambda text: assert_that("Hello World").contains(text("world")),
            lambda text: assert_that(text("a\xa0b")).contains_ignoring_case("A B"),
            lambda text: assert_that(text("done  ")).ends_with("done"),
            lambda text: assert_that("DONE  ").ends_with_ignoring_case(text("done")),
        ],
    )
    def test_no_assertion_says_a_line_of_one(self, ask):
        class Own(str):
            __slots__ = ()

        assert_that(_lines(lambda: ask(Own))).is_length(1)
        assert_that(len(_lines(lambda: ask(str)))).is_greater_than(1)

    def test_a_line_is_not_what_reads_a_text_of_a_class_of_its_own_again(self):
        class Once(str):
            __slots__ = ()
            asked = 0

            def split(self, *args, **kwargs):
                type(self).asked += 1
                return str.split(self, *args, **kwargs)

        lines = _lines(lambda: assert_that(Once("Hello World")).is_equal_to_ignoring_whitespace("hello world"))
        assert_that(lines).is_length(1)
        assert_that(Once.asked).is_equal_to(1)

    @pytest.mark.parametrize("method", ["split", "strip", "replace"])
    def test_equality_asks_the_text_and_not_what_its_class_answers(self, method):
        blue = type("Blue", (str,), {"__slots__": (), method: lambda self, *args, **kwargs: "blue"})
        lines = _lines(lambda: assert_that(blue("red")).is_equal_to("blue"))
        assert_that(lines).is_length(1)
        # and the text itself is still read, as before
        lines = _lines(lambda: assert_that(blue("a  b")).is_equal_to("a b"))
        assert_that(lines[-1]).is_equal_to("every difference here is one of the kind or amount of whitespace")

    @pytest.mark.parametrize("method", ["split", "strip", "replace"])
    def test_equality_asks_the_bytes_and_not_what_their_class_answers(self, method):
        blue = type("Blue", (bytes,), {"__slots__": (), method: lambda self, *args, **kwargs: b"blue"})
        assert_that(_lines(lambda: assert_that(blue(b"red")).is_equal_to(b"blue"))).is_length(1)
        lines = _lines(lambda: assert_that(blue(b"a ")).is_equal_to(b"a"))
        assert_that(lines[-1]).is_equal_to("every difference here is one of surrounding whitespace")

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that(b"Order").starts_with(b"order"),
            lambda: assert_that(b"done\n").ends_with(b"done"),
            lambda: assert_that(["Order", "x"]).starts_with("order"),
            lambda: assert_that(["x", "done\n"]).ends_with("done"),
        ],
        ids=["bytes at the start", "bytes at the end", "a list at the start", "a list at the end"],
    )
    def test_bytes_and_sequences_get_no_line_of_a_text(self, ask):
        assert_that(_lines(ask)).is_length(1)


class TestEveryAssertionThatHoldsATextAgainstAText:
    """By the name of the assertion, so one that holds two texts against each other and says nothing shows here."""

    @pytest.mark.parametrize(
        ("name", "ask"),
        [
            ("starts_with", lambda: assert_that("Order").starts_with("order")),
            ("ends_with", lambda: assert_that("done\n").ends_with("done")),
            ("starts_with_ignoring_case", lambda: assert_that(" ORDER").starts_with_ignoring_case("order")),
            ("ends_with_ignoring_case", lambda: assert_that("DONE\n").ends_with_ignoring_case("done")),
            ("contains", lambda: assert_that("Hello World").contains("world")),
            ("contains_ignoring_case", lambda: assert_that("a\xa0b").contains_ignoring_case("A B")),
            ("is_equal_to", lambda: assert_that("a  b").is_equal_to("a b")),
            ("is_equal_to_ignoring_case", lambda: assert_that("Oslo ").is_equal_to_ignoring_case("oslo")),
            ("is_equal_to_ignoring_whitespace", lambda: assert_that("A b").is_equal_to_ignoring_whitespace("a b")),
        ],
    )
    def test_it_says_why(self, name, ask):
        lines = _lines(ask)
        assert_that(len(lines)).described_as(name).is_greater_than(1)
        assert_that(lines[-1].startswith("Expected")).described_as(name).is_false()

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that("Hello").does_not_contain("Hello"),
            lambda: assert_that("Hello").is_not_equal_to("Hello"),
            lambda: assert_that("Order").not_.starts_with("Order"),
        ],
        ids=["does_not_contain", "is_not_equal_to", "not_.starts_with"],
    )
    def test_a_negation_says_nothing_of_it(self, ask):
        assert_that(_lines(ask)).is_length(1)


_TEXTS = st.text(alphabet="aAbB \n\r\t\xa0", max_size=8)


def _one_space(text: str) -> str:
    read: list[str] = []
    for char in text:
        if not char.isspace():
            read.append(char)
        elif not read or read[-1] != " ":
            read.append(" ")
    return "".join(read)


def _passes(call) -> bool:
    try:
        call()
    except AssertionFailure:
        return False
    return True


class TestALineIsSaidOnlyWhereItIsSo:
    """Each line is checked by a way of asking that the line itself does not use."""

    @given(_TEXTS, _TEXTS.filter(bool), st.booleans())
    def test_at_an_end(self, value, piece, start):
        holds = str.startswith if start else str.endswith
        name = "starts_with" if start else "ends_with"
        said = _hints.not_at_an_end(value, piece, start=start)
        if holds(value, piece):
            assert_that(said).is_none()
        elif said is None:
            return
        elif "once case is ignored" in said:
            assert_that(_passes(lambda: getattr(assert_that(value), f"{name}_ignoring_case")(piece))).is_true()
        elif said.startswith("the value holds"):
            assert_that(piece in value).is_true()
        elif "given starts or ends with whitespace" in said:
            assert_that(piece[0].isspace() or piece[-1].isspace()).is_true()
            assert_that(_passes(lambda: getattr(assert_that(value), name)(piece.strip()))).is_true()
        else:
            cuts = range(1, len(value))
            gaps = [(value[:cut], value[cut:]) if start else (value[cut:], value[:cut]) for cut in cuts]
            past = [gap for gap, rest in gaps if gap.isspace() and holds(rest, piece)]
            assert_that(past).is_not_empty()
            assert_that("a line break" in said).is_equal_to(max(past, key=len) in ("\n", "\r\n", "\r"))

    @given(_TEXTS, _TEXTS.filter(bool))
    def test_held(self, value, piece):
        said = _hints.not_in_text(value, piece)
        if piece in value:
            assert_that(said).is_none()
        elif said == "the value holds it once case is ignored":
            assert_that(_passes(lambda: assert_that(value).contains_ignoring_case(piece))).is_true()
        elif said == "the value holds it once every run of whitespace is read as one space":
            assert_that(_one_space(piece) in _one_space(value)).is_true()
        elif said is not None:
            assert_that(_one_space(piece).lower() in _one_space(value).lower()).is_true()
            assert_that(_one_space(piece) in _one_space(value)).is_false()
            assert_that(_passes(lambda: assert_that(value).contains_ignoring_case(piece))).is_false()

    @given(_TEXTS, _TEXTS)
    def test_two_that_are_not_equal(self, value, other):
        spaced = _hints.but_for_whitespace(value, other)
        if spaced is not None:
            assert_that(value.lower()).is_not_equal_to(other.lower())
            assert_that(_one_space(value.lower()).strip()).is_equal_to(_one_space(other.lower()).strip())
        cased = _hints.but_for_case(value, other)
        if cased is not None:
            bare, other_bare = (_one_space(each).replace(" ", "") for each in (value, other))
            assert_that(bare.lower()).is_equal_to(other_bare.lower())
        if value != other and not _passes(lambda: assert_that(value).is_equal_to(other)):
            lines = _lines(lambda: assert_that(value).is_equal_to(other))
            if lines[-1].endswith("the kind or amount of whitespace"):
                assert_that(_one_space(value).strip()).is_equal_to(_one_space(other).strip())
                assert_that(value.strip().replace("\r\n", "\n")).is_not_equal_to(other.strip().replace("\r\n", "\n"))
