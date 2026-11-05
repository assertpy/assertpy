from __future__ import annotations

import collections.abc
import decimal
from typing import TYPE_CHECKING

from ._engine._diff import _build_equality_diff
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import broadcasts, equal_past
from ._engine._require import argument, refuse, require_pattern, require_type, sized_len
from ._hints import but_for_case, but_for_whitespace, not_at_an_end, not_in_text, under
from .errors import (
    _capped,
    _capped_format,
    _capped_repr,
    _first_difference,
    _formatted,
    _parted,
    _safe_str,
    _truncated,
)
from .helpers import _elided_text_repr

if TYPE_CHECKING:
    import re
    from collections.abc import Callable
    from typing import Literal

    from ._engine._compat import Self

__tracebackhide__ = True


def _parted_from_the_end(text: str, ending: str) -> tuple[int, int]:
    """Where *text* stops matching *ending*, read from their ends: the place in each."""
    shared = _first_difference(text[::-1], ending[::-1])
    return len(text) - shared - 1, len(ending) - shared - 1


def _raw_place(text: str, lowered: str, place: int) -> int:
    """The place in *text* of the character that *place* in its lowered form came from.

    Lowering can lengthen a text, ``İ`` becoming two characters, so a place found in the lowered form runs
    ahead of the raw one by one for each such character before it: by 3000 after 3000 of them, which put the
    cut past the difference it was made for.
    """
    if len(lowered) == len(text):
        return place
    reached = 0
    for index, character in enumerate(text):
        reached += len(character.lower())
        if reached > place:
            return index
    return len(text)


def _parted_past_spacing(text: str, other: str) -> tuple[int, int]:
    """Where two texts first differ with whitespace left out, as the place in each."""
    at = other_at = 0
    while True:
        while at < len(text) and text[at].isspace():
            at += 1
        while other_at < len(other) and other[other_at].isspace():
            other_at += 1
        if at >= len(text) or other_at >= len(other) or text[at] != other[other_at]:
            return at, other_at
        at += 1
        other_at += 1


class StringMixin(_MixinBase):
    """String assertions mixin."""

    def _assert_string_chars(self, is_valid: Callable[[str], bool], description: str) -> Self:
        """Shared shape for the character-class string assertions.

        Validates that val is a non-empty string, then emits a "contain only ``description``" error if
        ``is_valid(self.val)`` is falsy.
        """
        require_type(self.val, str, "a string")
        if sized_len(self.val) == 0:
            raise ValueError("val is empty")
        if not is_valid(self.val):
            return self.error(
                f"Expected <{_capped(self.val)}> to contain only {description}, but did not.", expected=description
            )
        return self

    def is_equal_to_ignoring_case(self, other: str) -> Self:
        """Asserts that val is a string and is case-insensitive equal to other.

        Checks actual is equal to expected using the ``==`` operator and ``str.lower()``.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that('foo').is_equal_to_ignoring_case('FOO')
                assert_that('FOO').is_equal_to_ignoring_case('foo')
                assert_that('fOo').is_equal_to_ignoring_case('FoO')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** case-insensitive equal to expected
        """
        require_type(self.val, str, "a string")
        require_type(other, str, "a string", subject=argument("other"))
        if self.val.lower() == other.lower():
            return self
        lowered, other_lowered = self.val.lower(), other.lower()
        parted = _first_difference(lowered, other_lowered)
        actual_text, other_text = _parted(
            _safe_str(self.val),
            _formatted(other),
            _raw_place(self.val, lowered, parted),
            _raw_place(other, other_lowered, parted),
        )
        return self.error(
            f"Expected <{actual_text}> to be case-insensitive equal to <{other_text}>, but was not."
            f"{under(but_for_whitespace(self.val, other))}",
            expected=other,
        )

    def is_equal_to_ignoring_whitespace(self, other: str) -> Self:
        """Asserts that val is a string and is equal to other ignoring all whitespace.

        All whitespace (spaces, tabs, newlines) is stripped from both strings before comparing with
        the ``==`` operator, so differences in spacing, indentation, or line breaks don't matter.
        Case still does.

        Args:
            other: the expected value

        Examples:
            Usage:

                assert_that('foo bar').is_equal_to_ignoring_whitespace('foobar')
                assert_that('foo\\nbar').is_equal_to_ignoring_whitespace('foo bar')
                assert_that('  foo  ').is_equal_to_ignoring_whitespace('foo')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** equal to expected ignoring whitespace
            TypeError: if val or the given arg is not a string
        """
        require_type(self.val, str, "a string")
        require_type(other, str, "a string", subject=argument("other"))
        if "".join(self.val.split()) == "".join(other.split()):
            return self
        actual_text, other_text = _parted(
            _safe_str(self.val), _formatted(other), *_parted_past_spacing(self.val, other)
        )
        return self.error(
            f"Expected <{actual_text}> to be equal to <{other_text}> ignoring whitespace, but was not."
            f"{under(but_for_case(self.val, other))}",
            expected=other,
        )

    def is_html_equal_to(self, other: str, *, whitespace: Literal["lenient", "exact"] = "lenient") -> Self:
        """Asserts that val is a string holding the same HTML as other: the same elements, attributes and text.

        Both are read into trees and the trees compared, so markup that differs only in how it is written
        is equal.  Attribute order and the order of ``class`` tokens do not count, nor do the case of names,
        quotes, character references against their characters, comments and the doctype.  A boolean
        attribute counts by its presence, on the elements the HTML standard makes it boolean on.

        ``whitespace`` decides how text is read:

        - ``"lenient"``, the default, reads it as Django's ``assertHTMLEqual`` does: runs of whitespace are
          one space, and whitespace at the edges of a text and between elements does not count.  That lets
          the expected value be written across indented lines.  It also makes a space that separates two
          elements count for nothing: ``<b>a</b> <i>b</i>`` equals ``<b>a</b><i>b</i>``.
        - ``"exact"`` compares text as written, every space and newline of it.

        Either way the text of ``pre``, ``textarea``, ``script`` and ``style`` is compared as written, and
        whitespace means ASCII whitespace: a non-breaking space is text.

        Args:
            other: the expected HTML
            whitespace: ``"lenient"`` or ``"exact"``

        Examples:
            Usage:

                assert_that('<p class="a b">Hi</p>').is_html_equal_to('<p class="b a">Hi</p>')
                assert_that('<ul>\\n  <li>one</li>\\n</ul>').is_html_equal_to('<ul><li>one</li></ul>')
                assert_that('<input disabled>').is_html_equal_to('<input disabled="disabled">')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if actual is **not** the same HTML as expected
            TypeError: if val or the given arg is not a string
            ValueError: if ``whitespace`` is not one of the two, or either side is markup that cannot be
                read: an end tag that closes no open element, an attribute given twice on one element, a
                ``script``, ``textarea`` or other element holding raw text left open, text that ends
                inside a tag or a comment, or a spelling Python's parser reads differently before and after
                its 2025 fixes (the guide lists them).  The refusal holds under ``not_`` too.
        """
        require_type(self.val, str, "a string")
        require_type(other, str, "a string", subject=argument("other"))
        # html.parser and html.entities cost 2.3 ms to import, and only markup read here needs them
        from ._html import read_html, rendered, whitespace_mode

        mode = whitespace_mode(whitespace)
        actual = read_html(self.val, mode, subject="val")
        expected = read_html(other, mode, subject=argument("other"))
        if actual == expected:
            return self
        actual_text, expected_text = rendered(actual), rendered(expected)
        self._compared = (actual_text, expected_text)
        return self.error(
            f"Expected <{_truncated(_elided_text_repr(actual_text, expected_text))}> to be equal to"
            f" <{_truncated(_elided_text_repr(expected_text, actual_text))}> as HTML, but was not.",
            actual=self.val,
            expected=other,
            diff=_build_equality_diff(actual_text, expected_text),
        )

    def contains_ignoring_case(self, *items: str) -> Self:
        """Asserts that val is string and contains the given item or items.

        Walks val and checks for item or items using the ``==`` operator and ``str.lower()``.

        Args:
            *items: the item or items expected to be contained

        Examples:
            Usage:

                assert_that('foo').contains_ignoring_case('F', 'oO')
                assert_that(['a', 'B']).contains_ignoring_case('A', 'b')
                assert_that({'a': 1, 'B': 2}).contains_ignoring_case('A', 'b')
                assert_that({'a', 'B'}).contains_ignoring_case('A', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the case-insensitive item or items
        """
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        if isinstance(self.val, str):
            if len(items) == 1:
                require_type(items[0], str, "a string", subject=argument("item"))
                if items[0].lower() not in self.val.lower():
                    return self.error(
                        f"Expected <{_capped(self.val)}> to case-insensitive contain item"
                        f" <{_capped_format(items[0])}>, but did not."
                        f"{under(not_in_text(self.val, items[0], cased=False))}",
                        expected=items[0],
                    )
            else:
                val_lower = self.val.lower()
                missing = []
                for item in items:
                    require_type(item, str, "a string", subject=argument("item"))
                    if item.lower() not in val_lower:
                        missing.append(item)
                if missing:
                    return self.error(
                        f"Expected <{_capped(self.val)}> to case-insensitive contain items"
                        f" {self._fmt_items(items)}, but did not contain {self._fmt_items(missing)}.",
                        expected=items,
                    )
        elif isinstance(self.val, collections.abc.Iterable):
            lowered_values = []
            for value in list(self._walked()):  # read whole: the items are asked for their text, then compared
                require_type(value, str, "a string", subject="every item of val")
                lowered_values.append(value.lower())
            missing = []
            for item in items:
                require_type(item, str, "a string", subject=argument("item"))
                if item.lower() not in lowered_values:
                    missing.append(item)
            if missing:
                return self.error(
                    f"Expected <{_capped(self.val)}> to case-insensitive contain items"
                    f" {self._fmt_items(items)}, but did not contain {self._fmt_items(missing)}.",
                    expected=items,
                )
        else:
            refuse(self.val, "a string or an iterable")
        return self

    # `object` and not `str`: the body takes text, bytes or any element, and the three typed views each narrow it
    def starts_with(self, prefix: object) -> Self:
        """Asserts that val is string or iterable and starts with prefix.

        Args:
            prefix: the prefix

        Examples:
            Usage:

                assert_that('foo').starts_with('fo')
                assert_that(['a', 'b', 'c']).starts_with('a')
                assert_that((1, 2, 3)).starts_with(1)
                assert_that(((1, 2), (3, 4), (5, 6))).starts_with((1, 2))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** start with prefix
        """
        if prefix is None:  # `None` is neither, and reaches the branch below only to confuse it
            refuse(prefix, "a string or bytes", subject=argument("prefix"))
        if isinstance(self.val, str):
            text_prefix = require_type(prefix, str, "a string", subject=argument("prefix"))
            if len(text_prefix) == 0:
                raise ValueError("given prefix arg must not be empty")
            if not self.val.startswith(text_prefix):
                parted = _first_difference(self.val, text_prefix)
                actual_text, prefix_text = _parted(_safe_str(self.val), _formatted(text_prefix), parted)
                return self.error(
                    f"Expected <{actual_text}> to start with <{prefix_text}>, but did not."
                    f"{under(not_at_an_end(self.val, text_prefix, start=True))}",
                    expected=prefix,
                )
        elif isinstance(self.val, (bytes, bytearray)):
            # bytes are iterable: `b"foo"` would yield 102, failing an assertion that should pass
            raw_prefix = require_type(prefix, (bytes, bytearray), "bytes", subject=argument("prefix"))
            if len(raw_prefix) == 0:
                raise ValueError("given prefix arg must not be empty")
            if not self.val.startswith(raw_prefix):
                return self.error(
                    f"Expected <{_capped_repr(self.val)}> to start with <{_capped_repr(raw_prefix)}>, but did not.",
                    expected=prefix,
                )
        elif isinstance(self.val, collections.abc.Iterable):
            iterator = iter(self._walked())
            try:
                first = next(iterator)
            except StopIteration:
                raise ValueError("val must not be empty") from None
            try:
                starts = first == prefix
                starts = starts if type(starts) is bool or not broadcasts(first, prefix, answer=starts) else False
            except (decimal.InvalidOperation, OverflowError, TypeError, ValueError) as refusal:
                starts = equal_past(first, prefix, refusal)
            if not starts:
                return self.error(
                    f"Expected {_capped(self.val)} to start with <{_capped_format(prefix)}>, but did not.",
                    expected=prefix,
                )
        else:
            refuse(self.val, "a string or an iterable")
        return self

    # `object` and not `str`, for the same reason as `starts_with`
    def ends_with(self, suffix: object) -> Self:
        """Asserts that val is string or iterable and ends with suffix.

        Args:
            suffix: the suffix

        Examples:
            Usage:

                assert_that('foo').ends_with('oo')
                assert_that(['a', 'b', 'c']).ends_with('c')
                assert_that((1, 2, 3)).ends_with(3)
                assert_that(((1, 2), (3, 4), (5, 6))).ends_with((5, 6))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** end with suffix
        """
        if suffix is None:
            refuse(suffix, "a string or bytes", subject=argument("suffix"))
        if isinstance(self.val, str):
            text_suffix = require_type(suffix, str, "a string", subject=argument("suffix"))
            if len(text_suffix) == 0:
                raise ValueError("given suffix arg must not be empty")
            if not self.val.endswith(text_suffix):
                actual_text, suffix_text = _parted(
                    _safe_str(self.val), _formatted(text_suffix), *_parted_from_the_end(self.val, text_suffix)
                )
                return self.error(
                    f"Expected <{actual_text}> to end with <{suffix_text}>, but did not."
                    f"{under(not_at_an_end(self.val, text_suffix, start=False))}",
                    expected=suffix,
                )
        elif isinstance(self.val, (bytes, bytearray)):
            # the mirror of the branch in `starts_with`: the last element of `b"foo"` is the int 111
            raw_suffix = require_type(suffix, (bytes, bytearray), "bytes", subject=argument("suffix"))
            if len(raw_suffix) == 0:
                raise ValueError("given suffix arg must not be empty")
            if not self.val.endswith(raw_suffix):
                return self.error(
                    f"Expected <{_capped_repr(self.val)}> to end with <{_capped_repr(raw_suffix)}>, but did not.",
                    expected=suffix,
                )
        elif isinstance(self.val, collections.abc.Iterable):
            items = list(self._walked())
            if not items:
                raise ValueError("val must not be empty")
            try:
                ends = items[-1] == suffix
                ends = ends if type(ends) is bool or not broadcasts(items[-1], suffix, answer=ends) else False
            except (decimal.InvalidOperation, OverflowError, TypeError, ValueError) as refusal:
                ends = equal_past(items[-1], suffix, refusal)
            if not ends:
                return self.error(
                    f"Expected {_capped(self.val)} to end with <{_capped_format(suffix)}>, but did not.",
                    expected=suffix,
                )
        else:
            refuse(self.val, "a string or an iterable")
        return self

    def starts_with_ignoring_case(self, prefix: str) -> Self:
        """Asserts that val is a string and starts with prefix, ignoring case.

        Like [`starts_with()`][assertpy.string.StringMixin.starts_with] but case-insensitive
        (via ``str.lower()``), and strings only.

        Args:
            prefix: the prefix

        Examples:
            Usage:

                assert_that('FooBar').starts_with_ignoring_case('foo')
                assert_that('foobar').starts_with_ignoring_case('FOO')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** case-insensitive start with prefix
            TypeError: if val or the given prefix is not a string
            ValueError: if the given prefix is empty
        """
        require_type(self.val, str, "a string")
        require_type(prefix, str, "a string", subject=argument("prefix"))
        if len(prefix) == 0:
            raise ValueError("given prefix arg must not be empty")
        if not self.val.lower().startswith(prefix.lower()):
            lowered, prefix_lowered = self.val.lower(), prefix.lower()
            parted = _first_difference(lowered, prefix_lowered)
            actual_text, prefix_text = _parted(
                _safe_str(self.val),
                _formatted(prefix),
                _raw_place(self.val, lowered, parted),
                _raw_place(prefix, prefix_lowered, parted),
            )
            return self.error(
                f"Expected <{actual_text}> to case-insensitive start with <{prefix_text}>, but did not."
                f"{under(not_at_an_end(self.val, prefix, start=True, cased=False))}",
                expected=prefix,
            )
        return self

    def ends_with_ignoring_case(self, suffix: str) -> Self:
        """Asserts that val is a string and ends with suffix, ignoring case.

        Like [`ends_with()`][assertpy.string.StringMixin.ends_with] but case-insensitive
        (via ``str.lower()``), and strings only.

        Args:
            suffix: the suffix

        Examples:
            Usage:

                assert_that('FooBar').ends_with_ignoring_case('BAR')
                assert_that('foobar').ends_with_ignoring_case('Bar')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** case-insensitive end with suffix
            TypeError: if val or the given suffix is not a string
            ValueError: if the given suffix is empty
        """
        require_type(self.val, str, "a string")
        require_type(suffix, str, "a string", subject=argument("suffix"))
        if len(suffix) == 0:
            raise ValueError("given suffix arg must not be empty")
        if not self.val.lower().endswith(suffix.lower()):
            lowered, suffix_lowered = self.val.lower(), suffix.lower()
            parted, suffix_parted = _parted_from_the_end(lowered, suffix_lowered)
            actual_text, suffix_text = _parted(
                _safe_str(self.val),
                _formatted(suffix),
                _raw_place(self.val, lowered, parted),
                _raw_place(suffix, suffix_lowered, suffix_parted),
            )
            return self.error(
                f"Expected <{actual_text}> to case-insensitive end with <{suffix_text}>, but did not."
                f"{under(not_at_an_end(self.val, suffix, start=False, cased=False))}",
                expected=suffix,
            )
        return self

    def matches(self, pattern: str | re.Pattern[str]) -> Self:
        """Asserts that val is string and matches the given regex pattern.

        Args:
            pattern: the regular expression pattern, as raw string (aka prefixed with ``r``) or compiled from one
                with ``re.compile()``

        Examples:
            Usage:

                assert_that('foo').matches(r'\\w')
                assert_that('123-456-7890').matches(r'\\d{3}-\\d{3}-\\d{4}')

            Match is partial unless anchored, so these assertion pass:

                assert_that('foo').matches(r'\\w')
                assert_that('foo').matches(r'oo')
                assert_that('foo').matches(r'\\w{2}')

            To match the entire string, anchor the pattern with ``\\A`` and ``\\Z``, which match the start and
            end of the string.  ``^`` and ``$`` match the start and end of a line, and ``$`` also matches before
            a final newline, so ``^\\w{3}$`` passes on ``'foo\\n'`` too:

                assert_that('foo').matches(r'\\A\\w{3}\\Z')
                assert_that('foo\\n').matches(r'^\\w{3}$')

            Regex flags, such as ``re.MULTILINE`` and ``re.DOTALL``, go in as *inline modifiers*, such as
            ``(?m)`` and ``(?s)``, or on a pattern compiled with them:

                s = '''bar
                foo
                baz'''

                # using multiline (?m)
                assert_that(s).matches(r'(?m)^foo$')

                # using dotall (?s)
                assert_that(s).matches(r'(?s)b(.*)z')

                # the same, compiled
                assert_that(s).matches(re.compile(r'b(.*)z', re.DOTALL))

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** match pattern
            TypeError: if val is not a string, or pattern is neither a string nor a pattern compiled from one
            ValueError: if pattern is empty

        Tip:
            Regular expressions are tricky.  Be sure to use raw strings (aka prefixed with ``r``).
            Also, note that the [`matches()`][assertpy.string.StringMixin.matches] assertion passes
            when the pattern is found anywhere in the string (it calls ``re.search``).  So, if you need
            to match the entire string, you must include anchors in the regex pattern.
        """
        require_type(self.val, str, "a string")
        if require_pattern(pattern).search(self.val) is None:
            return self.error(
                f"Expected <{_capped(self.val)}> to match pattern <{_capped_format(pattern)}>, but did not.",
                expected=pattern,
            )
        return self

    def does_not_match(self, pattern: str | re.Pattern[str]) -> Self:
        """Asserts that val is string and does not match the given regex pattern.

        Args:
            pattern: the regular expression pattern, as raw string (aka prefixed with ``r``) or compiled from one
                with ``re.compile()``

        Examples:
            Usage:

                assert_that('foo').does_not_match(r'\\d+')
                assert_that('123').does_not_match(r'\\w+')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** match pattern
            TypeError: if val is not a string, or pattern is neither a string nor a pattern compiled from one
            ValueError: if pattern is empty

        See Also:
            [`matches()`][assertpy.string.StringMixin.matches] - for more about regex patterns
        """
        require_type(self.val, str, "a string")
        if require_pattern(pattern).search(self.val) is not None:
            return self.error(
                f"Expected <{_capped(self.val)}> to not match pattern <{_capped_format(pattern)}>, but did."
            )
        return self

    def is_alpha(self) -> Self:
        """Asserts that val is non-empty string and all characters are alphabetic (using ``str.isalpha()``).

        Examples:
            Usage:

                assert_that('foo').is_alpha()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** alphabetic
        """
        return self._assert_string_chars(str.isalpha, "alphabetic chars")

    def is_digit(self) -> Self:
        """Asserts that val is non-empty string and all characters are digits (using ``str.isdigit()``).

        Examples:
            Usage:

                assert_that('1234567890').is_digit()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** digits
        """
        return self._assert_string_chars(str.isdigit, "digits")

    def is_lower(self) -> Self:
        """Asserts that val is non-empty string and all characters are lowercase (using ``str.lower()``).

        Examples:
            Usage:

                assert_that('foo').is_lower()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** lowercase
        """
        return self._assert_string_chars(lambda value: value == value.lower(), "lowercase chars")

    def is_upper(self) -> Self:
        """Asserts that val is non-empty string and all characters are uppercase (using ``str.upper()``).

        Examples:
            Usage:

                assert_that('FOO').is_upper()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** uppercase
        """
        return self._assert_string_chars(lambda value: value == value.upper(), "uppercase chars")

    def is_alphanumeric(self) -> Self:
        """Asserts that val is non-empty string and all characters are alphanumeric (using ``str.isalnum()``).

        Examples:
            Usage:

                assert_that('abc123').is_alphanumeric()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** alphanumeric
        """
        return self._assert_string_chars(str.isalnum, "alphanumeric chars")

    def is_whitespace(self) -> Self:
        """Asserts that val is non-empty string and all characters are whitespace (using ``str.isspace()``).

        Examples:
            Usage:

                assert_that('  ').is_whitespace()
                assert_that('\\t\\n').is_whitespace()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** whitespace
        """
        return self._assert_string_chars(str.isspace, "whitespace")

    def contains_any_of(self, *items: str) -> Self:
        """Asserts that val is a string and contains at least one of the given items.

        Args:
            *items: the items, at least one of which is expected to be contained

        Examples:
            Usage:

                assert_that('foobar').contains_any_of('foo', 'xxx')
                assert_that('foobar').contains_any_of('xxx', 'bar')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain any of the items
        """
        require_type(self.val, str, "a string")
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        for item in items:
            require_type(item, str, "a string", subject=argument("item"))
        if not any(item in self.val for item in items):
            return self.error(
                f"Expected <{_capped(self.val)}> to contain any of {self._fmt_items(items)}, but did not.",
                expected=items,
            )
        return self

    def contains_none_of(self, *items: str) -> Self:
        """Asserts that val is a string and contains none of the given items.

        Args:
            *items: the items, none of which should be contained

        Examples:
            Usage:

                assert_that('foobar').contains_none_of('xxx', 'yyy')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain any of the items
        """
        require_type(self.val, str, "a string")
        if len(items) == 0:
            raise ValueError("one or more args must be given")
        for item in items:
            require_type(item, str, "a string", subject=argument("item"))
        found = [item for item in items if item in self.val]
        if found:
            return self.error(
                f"Expected <{_capped(self.val)}> to contain none of {self._fmt_items(items)},"
                f" but did contain {self._fmt_items(found)}."
            )
        return self

    def is_unicode(self) -> Self:
        """Asserts that val is a ``str``.

        Retained for ``assertpy`` compatibility: every ``str`` is unicode on Python 3, so this is
        effectively an ``isinstance(val, str)`` check.

        Examples:
            Usage:

                assert_that('foo').is_unicode()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** a ``str``
        """
        if not isinstance(self.val, str):
            return self.error(f"Expected <{_capped(self.val)}> to be unicode, but was <{type(self.val).__name__}>.")
        return self

    def extracting_group(self, pattern: str | re.Pattern[str], group: int | str = 0) -> Self:
        """Search val for ``pattern`` and return a new builder whose val is the captured group.

        A group the pattern does not have fails it with or without ``not_``: that is a mistake in the call,
        found once the pattern matched, and not an answer about val.

        Args:
            pattern: the regular expression pattern, as a string or compiled from one
            group: the group index (int) or name (str) to extract. Defaults to ``0``
                (the entire match).

        Examples:
            Usage with positional groups:

                assert_that("status=200 path=/api").extracting_group(r"status=(\\d+)", 1).is_equal_to("200")

            Usage with named groups:

                assert_that("2024-01-15 ERROR").extracting_group(
                    r"(?P<level>\\w+)$", "level"
                ).is_equal_to("ERROR")

        Returns:
            AssertionBuilder: a **new** builder whose val is the extracted group string

        Raises:
            TypeError: if val is not a string, or pattern is neither a string nor a pattern compiled from one
            ValueError: if pattern is empty
            AssertionError: if the pattern does not match val or the group does not exist
        """
        require_type(self.val, str, "a string")
        match_obj = require_pattern(pattern).search(self.val)
        if match_obj is None:
            return self.error(
                f"Expected <{_capped(self.val)}> to match pattern <{_capped_format(pattern)}>, but did not.",
                expected=pattern,
            )
        try:
            extracted = match_obj.group(group)
        except IndexError:
            self._unmet(
                f"Expected pattern <{_capped_format(pattern)}> to have group <{_capped_format(group)}>,"
                " but it does not.",
                suppress_context=True,
                expected=pattern,
            )
            return self
        if extracted is None:
            return self.error(
                f"Expected group <{_capped_format(group)}> of pattern <{_capped_format(pattern)}> to be matched in"
                f" <{_capped(self.val)}>, but it was not.",
                expected=pattern,
            )
        return self.builder(extracted, self.description, self.kind, logger=self.logger)

    def matches_with_groups(self, pattern: str | re.Pattern[str]) -> Self:
        """Search val for ``pattern`` and return a new builder whose val is the tuple of all groups.

        If the pattern contains **named** groups, the builder val is a ``dict``
        of ``{name: value}`` for all named groups.  Otherwise it is the
        ``tuple`` returned by ``Match.groups()``, empty for a pattern without groups.

        Args:
            pattern: the regular expression pattern, as a string or compiled from one

        Examples:
            Positional groups:

                assert_that("2024-01-15 ERROR").matches_with_groups(
                    r"(\\d{4}-\\d{2}-\\d{2}) (\\w+)"
                ).is_length(2)

            Named groups:

                assert_that("status=200").matches_with_groups(
                    r"(?P<key>\\w+)=(?P<val>\\w+)"
                ).contains_key("key").contains_key("val")

        Returns:
            AssertionBuilder: a **new** builder whose val is the groups tuple or groupdict

        Raises:
            TypeError: if val is not a string, or pattern is neither a string nor a pattern compiled from one
            ValueError: if pattern is empty
            AssertionError: if the pattern does not match val
        """
        require_type(self.val, str, "a string")
        match_obj = require_pattern(pattern).search(self.val)
        if match_obj is None:
            return self.error(
                f"Expected <{_capped(self.val)}> to match pattern <{_capped_format(pattern)}>, but did not.",
                expected=pattern,
            )
        groupdict = match_obj.groupdict()
        result = groupdict or match_obj.groups()
        return self.builder(result, self.description, self.kind, logger=self.logger)
