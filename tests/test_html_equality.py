"""`is_html_equal_to()` and `match.html_equal_to()`: HTML compared as the trees it reads into (assertpy#140).

The labelled pairs are decided by hand from the WHATWG standard's rules for parsing and for each attribute, and
the verdicts Django's ``assertHTMLEqual`` gives on them were taken as a second reader: every pair where the two
differ is a rule the guide names under "Where it differs from Django".  ``"refused"`` is markup the comparison
declines to read.
"""

import random
import string

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from assertpy import AssertionFailure, assert_that, match
from assertpy._html import _Reader, read_html, rendered

CASES = [
    ("<p>a</p>", "<p>a</p>", True, True, "the same markup"),
    ("<div>\n  <p>a</p>\n</div>", "<div><p>a</p></div>", True, False, "indentation between block elements"),
    ("<p>a  b</p>", "<p>a b</p>", True, False, "a run of spaces in text"),
    ("<p>a\n\tb</p>", "<p>a b</p>", True, False, "a newline and a tab in text"),
    ("<p> a </p>", "<p>a</p>", True, False, "spaces at the edges of an element's text"),
    ("<b>a</b> <i>b</i>", "<b>a</b><i>b</i>", True, False, "lenient's known false equality: a separating space"),
    ("<span>a </span><span>b</span>", "<span>a</span><span>b</span>", True, False, "lenient's known false equality"),
    ("<p>a <b>b</b> c</p>", "<p>a<b>b</b>c</p>", True, False, "lenient's known false equality: mixed content"),
    ("<p>a\u00a0</p>", "<p>a</p>", False, False, "a non-breaking space is text, not whitespace"),
    ("<p>\u00a0</p>", "<p></p>", False, False, "a non-breaking space alone is text"),
    ("<p>a\u2003b</p>", "<p>a b</p>", False, False, "an em space is not ASCII whitespace"),
    ("<p>a\r\nb</p>", "<p>a\nb</p>", True, True, "CR LF is LF in HTML's input stream"),
    ("<p>a\rb</p>", "<p>a\nb</p>", True, True, "a lone CR is LF"),
    ("\n<p>a</p>\n", "<p>a</p>", True, False, "whitespace around the whole fragment"),
    ("<p>a</p>b", "<p>a</p> b", True, False, "a space before top-level text"),
    ("", "", True, True, "two empty fragments"),
    ("   ", "", True, False, "whitespace alone"),
    ("<pre>a  b</pre>", "<pre>a b</pre>", False, False, "spaces in pre are kept"),
    ("<pre>\na</pre>", "<pre>a</pre>", True, True, "the newline right after <pre> is dropped by the parser"),
    ("<pre>\n\na</pre>", "<pre>\na</pre>", False, False, "only the first newline after <pre> is dropped"),
    ("<pre>\n</pre>", "<pre></pre>", True, True, "a pre holding only the newline the parser drops"),
    ("<pre><!DOCTYPE html>\nx</pre>", "<pre>x</pre>", False, False, "a declaration is the first token after <pre>"),
    ("<pre><?pi?>\nx</pre>", "<pre>x</pre>", False, False, "so is a processing instruction"),
    ("<listing><![if x]>\nx</listing>", "<listing>x</listing>", "refused", "refused", "a marked section is refused"),
    ("<![foo]>x", "x", "refused", "refused", "an unknown one too, which a parser before 2025 failed on"),
    ("<listing>\nx</listing>", "<listing>x</listing>", True, True, "the newline after <listing> is dropped"),
    ("<p><![CDATA[x>y]]></p>", "<p>y]]&gt;</p>", "refused", "refused", "HTML ends a CDATA section at its first >"),
    ("<pre><b>x</b>\na</pre>", "<pre><b>x</b>a</pre>", False, False, "a newline after a child of pre is kept"),
    ("<pre><code>  x</code></pre>", "<pre><code>x</code></pre>", False, False, "text inside an element inside pre"),
    ("<textarea>\na</textarea>", "<textarea>a</textarea>", True, True, "the newline after <textarea> is dropped"),
    ("<textarea>a  b</textarea>", "<textarea>a b</textarea>", False, False, "textarea text is verbatim"),
    ("<textarea><b>x</b></textarea>", "<textarea>&lt;b&gt;x&lt;/b&gt;</textarea>", True, True, "textarea holds text"),
    ("<textarea>&amp;</textarea>", "<textarea>&</textarea>", True, True, "references in textarea are decoded"),
    ("<title>a  b</title>", "<title>a b</title>", True, False, "title is text, read like any text"),
    ("<title><b>x</b></title>", "<title>&lt;b&gt;x&lt;/b&gt;</title>", True, True, "title holds text"),
    ("<script>a  b</script>", "<script>a b</script>", False, False, "script text is verbatim"),
    ("<script>a &amp; b</script>", "<script>a & b</script>", False, False, "references in script are not decoded"),
    ("<script>if (a<b) {}</script>", "<script>if (a<b) {}</script>", True, True, "a < inside script is text"),
    ('<script>s = "</\u017fcript>"</script>', '<script>s = "</\u017fcript>"</script>', True, True, "a long s is no s"),
    ("<plaintext>a</plaintext>b", "<plaintext>a</plaintext>b", True, True, "plaintext runs to the end of the text"),
    ("<style>p  {}</style>", "<style>p {}</style>", False, False, "style text is verbatim"),
    ("<xmp><b>x</b></xmp>", "<xmp>&lt;b&gt;x&lt;/b&gt;</xmp>", False, False, "xmp is raw text, so a reference stays"),
    ("<xmp><b>x</b></xmp>", "<xmp><b>x</b></xmp>", True, True, "xmp holds its markup as text"),
    ('<p class="a b">x</p>', '<p class="b a">x</p>', True, True, "class tokens in any order"),
    ('<p class="a  b">x</p>', '<p class="a b">x</p>', True, True, "class tokens split on whitespace"),
    ('<p class="a a">x</p>', '<p class="a">x</p>', False, False, "a repeated class token is kept"),
    ('<p class="">x</p>', "<p>x</p>", False, False, "an empty class is still an attribute"),
    ('<p id="a" title="b">x</p>', '<p title="b" id="a">x</p>', True, True, "attribute order"),
    ('<p title="a  b">x</p>', '<p title="a b">x</p>', False, False, "attribute values are compared as written"),
    ("<p ID=a>x</p>", '<p id="a">x</p>', True, True, "names are case-insensitive, unquoted values"),
    ("<P>x</P>", "<p>x</p>", True, True, "element names are case-insensitive"),
    ('<p data-\u212a="1"></p>', '<p data-k="1"></p>', False, False, "only ASCII letters fold: a Kelvin sign stays"),
    ("<x-\u212a></x-\u212a>", "<x-k></x-k>", False, False, "in element names too"),
    ('<p title="&amp;">x</p>', '<p title="&">x</p>', True, True, "references in attribute values are decoded"),
    ('<a href="?a=1&not=2">x</a>', '<a href="?a=1&amp;not=2">x</a>', True, True, "&not= in a value is not a reference"),
    ('<p title="&copyright">x</p>', '<p title="&amp;copyright">x</p>', True, True, "nor is &copy followed by letters"),
    ('<p title="&copy">x</p>', '<p title="\u00a9">x</p>', True, True, "&copy alone at the end of a value is"),
    (
        "<p title=a\u00a0b>x</p>",
        '<p title="a\u00a0b">x</p>',
        "refused",
        "refused",
        "a non-breaking space in an unquoted value",
    ),
    ("<p data-x>x</p>", '<p data-x="">x</p>', True, True, "an attribute without a value is the empty string"),
    ('<p title="A">x</p>', '<p title="a">x</p>', False, False, "values are case-sensitive"),
    ("<input disabled>", '<input disabled="disabled">', True, True, "a boolean attribute is its presence"),
    ("<input disabled>", '<input disabled="false">', True, True, "any value of a boolean attribute is true"),
    ("<input disabled>", "<input>", False, False, "absent is false"),
    ('<x-widget disabled="false">', '<x-widget disabled="true">', False, False, "disabled is not boolean here"),
    ('<div disabled="a">', '<div disabled="b">', False, False, "disabled is boolean on form controls only"),
    ('<x-widget autofocus="a">', "<x-widget autofocus>", True, True, "autofocus is boolean on every element"),
    ('<script defer="">x</script>', "<script defer>x</script>", True, True, "defer is boolean on script"),
    ('<video controls="">', "<video controls>", True, True, "controls on video"),
    ('<img controls="a">', "<img controls>", True, True, "controls on img"),
    ("<div hidden>", '<div hidden="hidden">', True, True, "hidden: the empty string and hidden are one state"),
    ("<div hidden>", '<div hidden="until-found">', False, False, "until-found is another state"),
    ('<div hidden="x">', "<div hidden>", True, True, "an invalid hidden value is the hidden state"),
    ('<div hidden="UNTIL-FOUND">', '<div hidden="until-found">', True, True, "keywords are case-insensitive"),
    ("<br>", "<br/>", True, True, "a void element, with or without the slash"),
    ("<br></br>", "<br>", "refused", "refused", "an end tag for a void element closes nothing"),
    ("<div/>", "<div></div>", True, True, "the slash on a non-void HTML element is ignored, and the end closes it"),
    ("<div/><span>x</span>", "<div><span>x</span></div>", True, True, "so what follows is inside it"),
    ("<div/><span>x</span>", "<div></div><span>x</span>", False, False, "and not beside it"),
    ("<script/>a", "<script>a</script>", "refused", "refused", "a raw-text element written with a slash"),
    ("<p>a", "<p>a</p>", True, True, "an element left open at the end is closed"),
    ("<div><p>a</div>", "<div><p>a</p></div>", True, True, "an end tag closes the elements opened after its own"),
    ("<p>a</q>", "<p>a</p>", "refused", "refused", "an end tag that closes nothing"),
    ("</p>", "", "refused", "refused", "an end tag with nothing open"),
    ("<p>a<p>b", "<p>a</p><p>b</p>", False, False, "no tree construction: the second p nests"),
    ("<p>a<!-- c -->b</p>", "<p>ab</p>", True, True, "comments are not compared"),
    ("<p><![CDATA[x]]></p>", "<p></p>", "refused", "refused", "so a CDATA section is refused"),
    ('<p title=a"b\u00a0c">x</p>', "<p>x</p>", "refused", "refused", "a non-ASCII space inside an unquoted value"),
    ("<p a\u00a0b=1>x</p>", "<p>x</p>", "refused", "refused", "a non-ASCII space inside an attribute's name"),
    ("<p\u00a0a>x</p\u00a0a>", "<p\u00a0a>x</p\u00a0a>", True, True, "and in an element's name, which both read alike"),
    ("<p>a\x00</p>", "<p>a</p>", "refused", "refused", "a NUL character"),
    ("<!DOCTYPE html><p>a</p>", "<p>a</p>", True, True, "the doctype is not compared"),
    ("<p>a</p>", "<p>b</p>", False, False, "different text"),
    ("<p>a</p>", "<div>a</div>", False, False, "different elements"),
    ("<p>a</p><p>b</p>", "<p>b</p><p>a</p>", False, False, "order of elements"),
    ("<p>&lt;</p>", "<p>&#60;</p>", True, True, "named and numeric references"),
    ("<p>&nbsp;</p>", "<p>\u00a0</p>", True, True, "a reference and its character"),
    ("<p>&nbsp;</p>", "<p> </p>", False, False, "nbsp is not a space"),
    ('<p id="a" id="b">x</p>', '<p id="a">x</p>', "refused", "refused", "a repeated attribute"),
    ("<div class=", "<div>", "refused", "refused", "text that ends inside a tag"),
    ("<p>a<!-- c", "<p>a</p>", "refused", "refused", "text that ends inside a comment"),
    ("<script>a", "<script>a</script>", "refused", "refused", "a script left open"),
    ("<textarea>a", "<textarea>a</textarea>", "refused", "refused", "a textarea left open"),
    ("a < b", "a &lt; b", True, True, "a < that starts no tag is text"),
    ("a</", "a&lt;/", True, True, "a </ at the very end is text"),
    ("<p>a<!-->b</p>", "<p>ab</p>", "refused", "refused", "a comment closed by > right after <!--"),
    ("<p>a<!--->b</p>", "<p>ab</p>", "refused", "refused", "a comment closed by -> right after <!--"),
    ("<p>a<!-- c --!>b</p>", "<p>ab</p>", "refused", "refused", "a comment closed by --!>"),
    ("<p>a<!--x-- >b--></p>", "<p>a</p>", "refused", "refused", "-- > inside a comment an older parser closes at"),
    ("<p>a<!--x--\t>b</p>", "<p>ab</p>", "refused", "refused", "-- and a tab before >, where it closes too"),
    ("<p>a<!-- c --!> b --></p>", "<p>a</p>", "refused", "refused", "--!> inside a comment an older parser reads on"),
    ("<p>a</ p>", "<p>a</p>", "refused", "refused", "</ followed by a space"),
    ('<p>a</"></p>', "<p>a</p>", "refused", "refused", "</ followed by a quote"),
    ('<p>a</"', "<p>a</p>", "refused", "refused", "</ followed by a quote at the end"),
    ("<script>a</script x>", "<script>a</script>", "refused", "refused", "a raw-text end tag with more than its name"),
    ("<script></script x></script>", "<script></script>", "refused", "refused", "the same, closed later"),
    ("<style>a</style\n>", "<style>a</style>", True, True, "whitespace before the > of a raw-text end tag"),
    ("<svg><path/></svg>", "<svg><path></path></svg>", "refused", "refused", "SVG is not read"),
    ("<p><math><mi>x</mi></math></p>", "<p></p>", "refused", "refused", "MathML is not read"),
    ("<p>a</p>", "<SVG viewBox='0 0 1 1'></SVG>", "refused", "refused", "on either side, in any case"),
    ('<p a=="x y">x</p>', "<p>x</p>", "refused", "refused", "an = opening an unquoted value"),
    ("<p a=b<c>x</p>", "<p>x</p>", "refused", "refused", "a < inside an unquoted value"),
    ("<p a=b`c>x</p>", "<p>x</p>", "refused", "refused", "a backtick inside an unquoted value"),
    ("<p>&#1;</p>", "<p></p>", "refused", "refused", "a reference to a control character"),
    ('<p title="&#xfffe;">x</p>', "<p>x</p>", "refused", "refused", "or to a noncharacter, in a value too"),
    ("<p>&#x80;</p>", "<p>\u20ac</p>", True, True, "a reference into C1 is read as the standard remaps it"),
]


def _verdict(check):
    try:
        check()
    except AssertionFailure:
        return False
    except ValueError:
        return "refused"
    return True


def _matched(matcher_factory, value):
    try:
        matcher = matcher_factory()
    except ValueError:
        return "refused"
    return matcher.matches(value)


@pytest.mark.parametrize(("actual", "expected", "lenient", "exact", "why"), CASES, ids=[case[4] for case in CASES])
class TestTheLabelledPairs:
    def test_the_assertion(self, actual, expected, lenient, exact, why):
        for mode, label in (("lenient", lenient), ("exact", exact)):
            said = _verdict(lambda mode=mode: assert_that(actual).is_html_equal_to(expected, whitespace=mode))
            assert_that(said).described_as(f"{why} ({mode})").is_equal_to(label)

    def test_the_negation_holds_where_the_assertion_fails_and_refuses_where_it_refuses(
        self, actual, expected, lenient, exact, why
    ):
        said = _verdict(lambda: assert_that(actual).not_.is_html_equal_to(expected))
        flipped = {True: False, False: True, "refused": "refused"}[lenient]
        assert_that(said).described_as(why).is_equal_to(flipped)

    def test_either_way_round(self, actual, expected, lenient, exact, why):
        said = _verdict(lambda: assert_that(expected).is_html_equal_to(actual))
        assert_that(said).described_as(why).is_equal_to(lenient)

    def test_the_matcher(self, actual, expected, lenient, exact, why):
        for mode, label in (("lenient", lenient), ("exact", exact)):
            said = _matched(lambda mode=mode: match.html_equal_to(expected, whitespace=mode), actual)
            if label == "refused" and said is False:
                continue  # an unreadable value does not match; an unreadable expected is refused when built
            assert_that(said).described_as(f"{why} ({mode})").is_equal_to(label)


class TestAFailure:
    def test_says_where_the_trees_part(self):
        try:
            assert_that('<div><p class="a">Hello</p><input disabled></div>').is_html_equal_to(
                '<div>\n  <p class="a">Hi</p>\n  <input>\n</div>'
            )
        except AssertionFailure as failure:
            caught = failure
        message = str(caught)
        assert_that(message).starts_with('Expected <.., line 2:   <p class="a">"Hello"</p>, line 3:   <input disabled>')
        assert_that(message).contains("as HTML, but was not.")
        assert_that([(entry.actual, entry.expected) for entry in caught.diff.entries]).is_equal_to(
            [
                ('  <p class="a">"Hello"</p>', '  <p class="a">"Hi"</p>'),
                ("  <input disabled>", "  <input>"),
            ]
        )

    def test_carries_what_was_given_and_hands_the_rendered_trees_to_the_ide(self):
        actual, expected = "<p>a</p>", "<p>b</p>"
        try:
            assert_that(actual).is_html_equal_to(expected)
        except AssertionFailure as failure:
            caught = failure
        assert_that(caught.actual).is_equal_to(actual)
        assert_that(caught.expected).is_equal_to(expected)
        assert_that(caught._compared).is_equal_to(('<p>"a"</p>', '<p>"b"</p>'))

    def test_shows_whitespace_that_counts(self):
        try:
            assert_that("<pre>a  b</pre>").is_html_equal_to("<pre>a b</pre>")
        except AssertionFailure as failure:
            message = str(failure)
        assert_that(message).contains('<pre>"a  b"</pre>', '<pre>"a b"</pre>')

    def test_keeps_a_newline_in_text_on_one_line(self):
        assert_that(rendered(read_html("<pre>a\nb</pre>", "exact", subject="val"))).is_equal_to('<pre>"a\\nb"</pre>')

    def test_spells_a_character_past_u_ffff_with_eight_digits_so_it_reads_as_one(self):
        apart = (rendered(("\U000e0001",)), rendered(("\ue000" + "1",)))
        assert_that(apart).is_equal_to(('"\\U000e0001"', '"\\ue0001"'))

    def test_spells_a_character_that_does_not_print(self):
        try:
            assert_that("<p>a&nbsp;b</p>").is_html_equal_to("<p>a b</p>")
        except AssertionFailure as failure:
            message = str(failure)
        assert_that(message).contains('"a\\u00a0b"')


class TestARefusal:
    @pytest.mark.parametrize(
        ("value", "expected", "message"),
        [
            ("<p>a</q>", "<p>a</p>", "val is not HTML that can be read: </q> closes no open <q>, at line 1, column 5"),
            (
                "<p>a</p>",
                "<p>\n<b>a</q>",
                "given other arg is not HTML that can be read: </q> closes no open <q>, at line 2, column 5",
            ),
            ('<p id="a" ID=b>', "<p>", "<p> has the attribute 'id' twice, at line 1, column 1"),
            ("<script>a", "<script>a</script>", "<script> is not closed, so the rest of the text would be its content"),
            ("<div class=", "<div>", "the text ends inside '<div class=', at line 1, column 1"),
            ("<!-- " + "x" * 40, "", "the text ends inside '<!-- xxxxxxxxxxxxxxxxxxxxxxxxx...'"),
            ("<p>a<!-->b", "<p>ab</p>", "a comment is closed by the > right after its <!--, at line 1, column 5"),
            ("<p>a<!-- c --!>b", "<p>ab</p>", "a comment is closed by --!>, at line 1, column 5"),
            ("<p>\na</ p>", "<p>a</p>", "</ is not followed by the name of an element, at line 2, column 2"),
            ("<script>a</script x>", "<script>a</script>", "the end tag of <script> holds more than its name"),
            ("<b>" * 257, "<b>", "elements are nested deeper than 256, at line 1, column 769"),
            # the first reason is kept: the start tag and the comment after it are not read
            ("<p id=a id=b><b><!-- x", "<p>", "<p> has the attribute 'id' twice, at line 1, column 1"),
        ],
    )
    def test_names_the_side_the_reason_and_the_place(self, value, expected, message):
        for check in (
            lambda: assert_that(value).is_html_equal_to(expected),
            lambda: assert_that(value).not_.is_html_equal_to(expected),
        ):
            assert_that(check).raises(ValueError).when_called_with().contains(message)

    def test_a_value_or_an_argument_that_is_not_a_string(self):
        for check, subject in (
            (lambda: assert_that(b"<p>").is_html_equal_to("<p>"), "val must be a string"),
            (lambda: assert_that("<p>").is_html_equal_to(None), "given other arg must be a string"),
            (lambda: match.html_equal_to(5), "given expected arg must be a string"),
        ):
            assert_that(check).raises(TypeError).when_called_with().starts_with(subject)

    @pytest.mark.parametrize(
        ("whitespace", "kind"), [("strict", ValueError), ("LENIENT", ValueError), (True, TypeError)]
    )
    def test_a_whitespace_mode_that_is_not_one(self, whitespace, kind):
        for check in (
            lambda: assert_that("<p>").is_html_equal_to("<p>", whitespace=whitespace),
            lambda: match.html_equal_to("<p>", whitespace=whitespace),
        ):
            assert_that(check).raises(kind).when_called_with().contains("'lenient' or 'exact'")


class TestTheMatcher:
    def test_reads_what_it_expects_once_and_refuses_it_when_built(self):
        try:
            match.html_equal_to("<p>a</q>")
        except ValueError as refused:
            assert_that(str(refused)).starts_with("given expected arg is not HTML that can be read")
        else:
            pytest.fail("an unreadable expected was taken")

    def test_says_what_it_wants_and_why_a_value_is_not_read(self):
        matcher = match.html_equal_to("<p>a</p>")
        assert_that(matcher.describe()).is_equal_to("HTML equal to <<p>a</p>>")
        assert_that(matcher.describe_mismatch("<p>a</q>")).is_equal_to(
            "was <<p>a</q>>, and it is not HTML that can be read: </q> closes no open <q>, at line 1, column 5"
        )
        assert_that(matcher.describe_mismatch("<p>b</p>")).is_equal_to("was <<p>b</p>>")
        assert_that(matcher.describe_mismatch(5)).is_equal_to("was <5>")

    def test_composes_and_stands_in_a_structure(self):
        assert_that("<p>a</p>").satisfies(match.html_equal_to("<p> a </p>") & match.contains_string("a"))
        assert_that({"body": "<p>\n  a\n</p>"}).matches_structure({"body": match.html_equal_to("<p>a</p>")})
        assert_that(5).satisfies(~match.html_equal_to("<p>a</p>"))


def test_the_text_modes_do_not_depend_on_the_parsers_own_lists():
    """A Python released before mid 2025 reads markup inside textarea and title: the reader sets the modes itself."""

    class _Older(_Reader):
        CDATA_CONTENT_ELEMENTS = ("script", "style")  # ty: ignore[override-of-final-variable]  # an older parser's lists
        RCDATA_CONTENT_ELEMENTS = ()  # ty: ignore[override-of-final-variable]  # an older parser has none

    for markup, text in (
        ("<textarea><b>x</b></textarea>", "<b>x</b>"),
        ("<title><b>x</b></title>", "<b>x</b>"),
        ("<xmp><b>x</b></xmp>", "<b>x</b>"),
        ("<plaintext><b>x</b>", "<b>x</b>"),
    ):
        reader = _Older(markup)
        reader.feed(markup)
        reader.close()
        assert_that(reader.root.children[0].children).described_as(markup).is_equal_to([text])


class TestWhatAnOlderParserHandsTheReader:
    """html.parser before its 2025 fixes calls these handlers where a newer one does not, so they are called here."""

    def test_attribute_values_decoded_as_it_decoded_them(self):
        reader = _Reader('<a href="?x&not=1">')
        reader._HTMLParser__starttag_text = '<a href="?x&not=1">'
        reader.handle_starttag("a", [("href", "?x\u00ac=1")])
        assert_that(reader.root.children[0].attributes).is_equal_to((("href", "?x&not=1"),))

    def test_attributes_it_split_otherwise(self):
        reader = _Reader("<p title=a\u00a0b>")
        reader._HTMLParser__starttag_text = "<p title=a\u00a0b>"
        reader.handle_starttag("p", [("title", "a"), ("b", None)])
        assert_that(reader.problem).is_equal_to("<p> is not read alike on every Python version, at line 1, column 1")

    def test_an_end_tag_whose_name_does_not_follow_its_slash(self):
        reader = _Reader("</ p>")
        reader.handle_endtag("p")
        assert_that(reader.problem).is_equal_to("</ is not followed by the name of an element, at line 1, column 1")

    def test_a_start_tag_whose_name_it_folded_otherwise(self):
        reader = _Reader("<\u0130x>")
        reader._HTMLParser__starttag_text = "<\u0130x>"
        reader.handle_starttag("i\u0307x", [])
        assert_that(reader.problem).is_equal_to(
            "<i\u0307x> is not read alike on every Python version, at line 1, column 1"
        )

    def test_an_end_tag_it_names_otherwise(self):
        reader = _Reader("<ab></ab>")
        reader.handle_starttag("a", [])
        reader.lines, reader.text = [0], "</ab>"
        reader.handle_endtag("a")
        assert_that(reader.problem).is_equal_to("</ is not followed by the name of an element, at line 1, column 1")

    def test_a_marked_section_it_reads_as_one(self):
        reader = _Reader("<![if x]>")
        reader.unknown_decl("if x")
        assert_that(reader.problem).is_equal_to(
            "a marked section, which HTML ends at its first > and Python's parser does not, at line 1, column 1"
        )

    def test_a_marked_section_it_fails_on(self, monkeypatch):
        def fails(self, data):
            raise AssertionError("unknown status keyword 'foo' in marked section")

        monkeypatch.setattr(_Reader, "feed", fails)
        with pytest.raises(ValueError, match="a marked section, which HTML ends at its first >"):
            read_html("<![foo]>x", "exact", subject="val")

    def test_raw_text_holding_an_end_tag_with_more_than_its_name(self):
        reader = _Reader("<script>a</script x></script>")
        reader.handle_starttag("script", [])
        reader.handle_data("a</script x>")
        assert_that(reader.problem).is_equal_to("the end tag of <script> holds more than its name, at line 1, column 1")


# a tree of the elements whose text the whitespace rules read; verbatim ones are pinned by the labelled pairs
_NAMES = st.sampled_from(["div", "p", "span", "b", "ul", "li", "x-widget"])
_WORDS = st.text(alphabet=string.ascii_letters + "&<>\"'\u00a0é", min_size=1, max_size=4)
_ATTRIBUTES = st.dictionaries(
    st.sampled_from(["id", "title", "class", "data-x", "hidden", "autofocus"]),
    st.lists(_WORDS, min_size=0, max_size=3).map(" ".join),
    max_size=3,
)


def _trees(depth=2):
    leaf = st.tuples(st.just("text"), _WORDS)
    if depth == 0:
        return leaf
    element = st.tuples(st.just("element"), _NAMES, _ATTRIBUTES, st.lists(_trees(depth - 1), max_size=3))
    return leaf | element


def _merged(nodes):
    """*nodes* with neighbouring texts joined: two text nodes side by side are one text in any markup."""
    joined = []
    for node in nodes:
        if node[0] == "text" and joined and joined[-1][0] == "text":
            joined[-1] = ("text", joined[-1][1] + node[1])
        else:
            joined.append(node if node[0] == "text" else (*node[:3], _merged(node[3])))
    return joined


_FRAGMENTS = st.lists(_trees(), min_size=1, max_size=3).map(_merged)


def _escaped(text, quote=False):
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return escaped.replace('"', "&quot;") if quote else escaped


def _markup(nodes, gap="", shuffle=None):
    """*nodes* written as markup, with *gap* between every two tokens and attributes in the order *shuffle* gives."""
    parts = []
    for node in nodes:
        if node[0] == "text":
            parts.append(_escaped(node[1]))
            continue
        _, name, attributes, children = node
        pairs = list(attributes.items())
        if shuffle is not None:
            shuffle.shuffle(pairs)
            pairs = [
                (key, " ".join(shuffle.sample(value.split(" "), len(value.split(" ")))) if key == "class" else value)
                for key, value in pairs
            ]
        written = "".join(f' {key}="{_escaped(value, quote=True)}"' for key, value in pairs)
        parts.append(f"<{name}{written}>{gap}{_markup(children, gap, shuffle)}{gap}</{name}>")
    return gap.join(parts)


def _same(one, other, mode):
    return read_html(one, mode, subject="val") == read_html(other, mode, subject="other")


@given(_FRAGMENTS, st.randoms(use_true_random=False))
@settings(max_examples=200, deadline=None)
@example([("element", "p", {"class": "b a", "id": "x"}, [("text", "a")])], random.Random(0))
def test_the_order_of_attributes_and_class_tokens_never_counts(nodes, shuffle):
    for mode in ("lenient", "exact"):
        assert_that(_same(_markup(nodes), _markup(nodes, shuffle=shuffle), mode)).is_true()


@given(_FRAGMENTS, st.sampled_from(["\n", "\n  ", " ", "\t\n\t"]))
@settings(max_examples=200, deadline=None)
@example([("element", "div", {}, [("element", "p", {}, [("text", "a")])])], "\n  ")
def test_whitespace_between_tokens_counts_only_where_whitespace_is_exact(nodes, gap):
    compact, spaced = _markup(nodes), _markup(nodes, gap=gap)
    assert_that(_same(compact, spaced, "lenient")).is_true()
    if spaced != compact:
        assert_that(_same(compact, spaced, "exact")).is_false()


@given(_FRAGMENTS, _FRAGMENTS)
@settings(max_examples=200, deadline=None)
@example([("text", "a")], [("element", "p", {}, [("text", "a")])])
def test_two_trees_render_alike_exactly_where_they_are_equal(one, other):
    for mode in ("lenient", "exact"):
        first = read_html(_markup(one), mode, subject="val")
        second = read_html(_markup(other), mode, subject="other")
        assert_that(rendered(first) == rendered(second)).is_equal_to(first == second)


@given(st.text(alphabet="<>/!-=\"' abp\n&;", max_size=30), st.text(alphabet="<>/!-=\"' abp\n&;", max_size=30))
@settings(max_examples=300, deadline=None)
@example("<p>a</q>", "<p>a</p>")
def test_any_text_is_compared_or_refused_the_same_way_round(one, other):
    forward = _verdict(lambda: assert_that(one).is_html_equal_to(other))
    backward = _verdict(lambda: assert_that(other).is_html_equal_to(one))
    assert_that(backward).is_equal_to(forward)
