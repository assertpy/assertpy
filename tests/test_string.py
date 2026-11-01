import pytest

from assertpy import assert_that


def test_is_length():
    assert_that("foo").is_length(3)


def test_is_length_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_length(4)
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be of length <4>, but was <3>.")


def test_contains():
    assert_that("foo").contains("f")
    assert_that("foo").contains("o")
    assert_that("foo").contains("fo", "o")
    assert_that("fred").contains("d")
    assert_that("fred").contains("fr", "e", "d")


def test_contains_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").contains("x")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to contain item <x>, but did not.")


def test_contains_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").contains("f", "x", "z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo> to contain items <'f', 'x', 'z'>, but did not contain <'x', 'z'>."
    )


def test_contains_multi_item_single_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").contains("f", "o", "x")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo> to contain items <'f', 'o', 'x'>, but did not contain <x>."
    )


def test_contains_ignoring_case():
    assert_that("foo").contains_ignoring_case("f")
    assert_that("foo").contains_ignoring_case("F")
    assert_that("foo").contains_ignoring_case("Oo")
    assert_that("foo").contains_ignoring_case("f", "o", "F", "O", "Fo", "Oo", "FoO")


def test_contains_ignoring_case_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_ignoring_case("f")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string or an iterable, but was <123> (int)")


def test_contains_ignoring_case_missinge_item_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").contains_ignoring_case()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_ignoring_case_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").contains_ignoring_case("X")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to case-insensitive contain item <X>, but did not.")


def test_contains_ignoring_case_single_item_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_ignoring_case(12)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <12> (int)")


def test_contains_ignoring_case_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").contains_ignoring_case("F", "X", "Z")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo> to case-insensitive contain items <'F', 'X', 'Z'>, but did not contain <'X', 'Z'>."
    )


def test_contains_ignoring_case_multi_item_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_ignoring_case("F", 12)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <12> (int)")


def test_contains_ignoring_case_list():
    assert_that(["foo"]).contains_ignoring_case("Foo")
    assert_that(["foo", "bar", "baz"]).contains_ignoring_case("Foo")
    assert_that(["foo", "bar", "baz"]).contains_ignoring_case("Foo", "bAr")
    assert_that(["foo", "bar", "baz"]).contains_ignoring_case("Foo", "bAr", "baZ")


def test_contains_ignoring_case_generator_not_exhausted():
    # a one-shot iterable must be materialized so every arg is checked, not just the first
    assert_that(value for value in ["foo", "bar", "baz"]).contains_ignoring_case("Foo", "bAr", "baZ")


def test_contains_ignoring_case_list_elem_type_failure_order_independent():
    # a non-string element must raise regardless of whether a matching item is found before it
    with pytest.raises(TypeError, match="every item of val must be a string"):
        assert_that(["OK", 200]).contains_ignoring_case("ok")


def test_contains_ignoring_case_list_elem_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that([123]).contains_ignoring_case("f")
    assert_that(str(exc_info.value)).is_equal_to("every item of val must be a string, but was <123> (int)")


def test_contains_ignoring_case_list_multi_elem_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["foo", 123]).contains_ignoring_case("f")
    assert_that(str(exc_info.value)).is_equal_to("every item of val must be a string, but was <123> (int)")


def test_contains_ignoring_case_list_missinge_item_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that(["foo"]).contains_ignoring_case()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_ignoring_case_list_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["foo"]).contains_ignoring_case("X")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['foo']> to case-insensitive contain items <X>, but did not contain <X>."
    )


def test_contains_ignoring_case_list_single_item_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["foo"]).contains_ignoring_case(12)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <12> (int)")


def test_contains_ignoring_case_list_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(["foo", "bar"]).contains_ignoring_case("Foo", "X", "Y")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <['foo', 'bar']> to case-insensitive contain items <'Foo', 'X', 'Y'>, but did not contain <'X', 'Y'>."
    )


def test_contains_ignoring_case_list_multi_item_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["foo", "bar"]).contains_ignoring_case("F", 12)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <12> (int)")


def test_does_not_contain():
    assert_that("foo").does_not_contain("x")
    assert_that("foo").does_not_contain("x", "y")


def test_does_not_contain_single_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").does_not_contain("f")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to not contain item <f>, but did.")


def test_does_not_contain_list_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").does_not_contain("x", "y", "f")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo> to not contain items <'x', 'y', 'f'>, but did contain <f>."
    )


def test_does_not_contain_list_multi_item_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").does_not_contain("x", "f", "o")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo> to not contain items <'x', 'f', 'o'>, but did contain <'f', 'o'>."
    )


def test_is_empty():
    assert_that("").is_empty()


def test_is_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be empty string, but was not.")


def test_is_not_empty():
    assert_that("foo").is_not_empty()


def test_is_not_empty_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("").is_not_empty()
    assert_that(str(exc_info.value)).is_equal_to("Expected not empty string, but was empty.")


def test_is_equal_ignoring_case():
    assert_that("FOO").is_equal_to_ignoring_case("foo")
    assert_that("foo").is_equal_to_ignoring_case("FOO")
    assert_that("fOO").is_equal_to_ignoring_case("foo")


def test_is_equal_ignoring_case_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_equal_to_ignoring_case("bar")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to be case-insensitive equal to <bar>, but was not.")


def test_is_equal_ignoring_case_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_case(12)
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_equal_ignoring_case_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").is_equal_to_ignoring_case(12)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a string, but was <12> (int)")


def test_is_equal_ignoring_whitespace():
    assert_that("foo bar").is_equal_to_ignoring_whitespace("foobar")
    assert_that("foo\nbar").is_equal_to_ignoring_whitespace("foo bar")
    assert_that("  foo  ").is_equal_to_ignoring_whitespace("foo")
    assert_that("foo\tbar baz").is_equal_to_ignoring_whitespace("foobarbaz")


def test_is_equal_ignoring_whitespace_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo bar").is_equal_to_ignoring_whitespace("foo baz")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foo bar> to be equal to <foo baz> ignoring whitespace, but was not."
    )


def test_is_equal_ignoring_whitespace_case_still_matters_failure():
    with pytest.raises(AssertionError):
        assert_that("foo bar").is_equal_to_ignoring_whitespace("FOOBAR")


def test_is_equal_ignoring_whitespace_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_equal_to_ignoring_whitespace("123")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_equal_ignoring_whitespace_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").is_equal_to_ignoring_whitespace(12)
    assert_that(str(exc_info.value)).is_equal_to("given other arg must be a string, but was <12> (int)")


def test_starts_with():
    assert_that("fred").starts_with("f")
    assert_that("fred").starts_with("fr")
    assert_that("fred").starts_with("fred")


def test_starts_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("fred").starts_with("bar")
    assert_that(str(exc_info.value)).is_equal_to("Expected <fred> to start with <bar>, but did not.")


def test_starts_with_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).starts_with(12)
    assert_that(str(exc_info.value)).is_equal_to("val must be a string or an iterable, but was <123> (int)")


def test_starts_with_bad_arg_none_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").starts_with(None)
    assert_that(str(exc_info.value)).is_equal_to(
        "given prefix arg must be a string or bytes, but was <None> (NoneType)"
    )


def test_starts_with_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").starts_with(123)
    assert_that(str(exc_info.value)).is_equal_to("given prefix arg must be a string, but was <123> (int)")


def test_starts_with_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").starts_with("")
    assert_that(str(exc_info.value)).is_equal_to("given prefix arg must not be empty")


def test_ends_with():
    assert_that("fred").ends_with("d")
    assert_that("fred").ends_with("ed")
    assert_that("fred").ends_with("fred")


def test_ends_with_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("fred").ends_with("bar")
    assert_that(str(exc_info.value)).is_equal_to("Expected <fred> to end with <bar>, but did not.")


def test_ends_with_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).ends_with(12)
    assert_that(str(exc_info.value)).is_equal_to("val must be a string or an iterable, but was <123> (int)")


def test_ends_with_bad_arg_none_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").ends_with(None)
    assert_that(str(exc_info.value)).is_equal_to(
        "given suffix arg must be a string or bytes, but was <None> (NoneType)"
    )


def test_ends_with_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").ends_with(123)
    assert_that(str(exc_info.value)).is_equal_to("given suffix arg must be a string, but was <123> (int)")


def test_ends_with_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").ends_with("")
    assert_that(str(exc_info.value)).is_equal_to("given suffix arg must not be empty")


def test_starts_with_ignoring_case():
    assert_that("FooBar").starts_with_ignoring_case("foo")
    assert_that("foobar").starts_with_ignoring_case("FOO")
    assert_that("fred").starts_with_ignoring_case("fred")


def test_starts_with_ignoring_case_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("FooBar").starts_with_ignoring_case("bar")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <FooBar> to case-insensitive start with <bar>, but did not."
        "\nthe value holds the prefix, and not at its start"
    )


def test_starts_with_ignoring_case_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b"]).starts_with_ignoring_case("a")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <['a', 'b']> (list)")


def test_starts_with_ignoring_case_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").starts_with_ignoring_case(123)
    assert_that(str(exc_info.value)).is_equal_to("given prefix arg must be a string, but was <123> (int)")


def test_starts_with_ignoring_case_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").starts_with_ignoring_case("")
    assert_that(str(exc_info.value)).is_equal_to("given prefix arg must not be empty")


def test_ends_with_ignoring_case():
    assert_that("FooBar").ends_with_ignoring_case("BAR")
    assert_that("foobar").ends_with_ignoring_case("Bar")
    assert_that("fred").ends_with_ignoring_case("fred")


def test_ends_with_ignoring_case_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("FooBar").ends_with_ignoring_case("foo")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <FooBar> to case-insensitive end with <foo>, but did not."
        "\nthe value holds the suffix, and not at its end"
    )


def test_ends_with_ignoring_case_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(["a", "b"]).ends_with_ignoring_case("b")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <['a', 'b']> (list)")


def test_ends_with_ignoring_case_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").ends_with_ignoring_case(123)
    assert_that(str(exc_info.value)).is_equal_to("given suffix arg must be a string, but was <123> (int)")


def test_ends_with_ignoring_case_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").ends_with_ignoring_case("")
    assert_that(str(exc_info.value)).is_equal_to("given suffix arg must not be empty")


def test_matches():
    assert_that("fred").matches(r"\w")
    assert_that("fred").matches(r"\w{2}")
    assert_that("fred").matches(r"\w+")
    assert_that("fred").matches(r"^\w{4}$")
    assert_that("fred").matches(r"^.*?$")
    assert_that("123-456-7890").matches(r"\d{3}-\d{3}-\d{4}")


def test_matches_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("fred").matches(r"\d+")
    assert_that(str(exc_info.value)).is_equal_to("Expected <fred> to match pattern <\\d+>, but did not.")


def test_matches_whole_string_is_anchored_by_a_and_z_not_by_caret_and_dollar():
    assert_that("foo").matches(r"\A\w{3}\Z").does_not_match(r"\A\w{2}\Z")
    assert_that("foo\n").matches(r"^foo$").does_not_match(r"\Afoo\Z")


def test_matches_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).matches(12)
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_matches_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").matches(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given pattern arg must be a string or a pattern compiled from one, but was <123> (int)"
    )


def test_matches_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").matches("")
    assert_that(str(exc_info.value)).is_equal_to("given pattern arg must not be empty")


def test_does_not_match():
    assert_that("fred").does_not_match(r"\d+")
    assert_that("fred").does_not_match(r"\w{5}")
    assert_that("123-456-7890").does_not_match(r"^\d+$")


def test_does_not_match_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("fred").does_not_match(r"\w+")
    assert_that(str(exc_info.value)).is_equal_to("Expected <fred> to not match pattern <\\w+>, but did.")


def test_does_not_match_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_match(12)
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_does_not_match_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("fred").does_not_match(123)
    assert_that(str(exc_info.value)).is_equal_to(
        "given pattern arg must be a string or a pattern compiled from one, but was <123> (int)"
    )


def test_does_not_match_bad_arg_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("fred").does_not_match("")
    assert_that(str(exc_info.value)).is_equal_to("given pattern arg must not be empty")


def test_is_alpha():
    assert_that("foo").is_alpha()


def test_is_alpha_digit_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo123").is_alpha()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo123> to contain only alphabetic chars, but did not.")


def test_is_alpha_space_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo bar").is_alpha()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo bar> to contain only alphabetic chars, but did not.")


def test_is_alpha_punctuation_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo,bar").is_alpha()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo,bar> to contain only alphabetic chars, but did not.")


def test_is_alpha_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_alpha()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_alpha_empty_value_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_alpha()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_is_digit():
    assert_that("123").is_digit()


def test_is_digit_alpha_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo123").is_digit()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo123> to contain only digits, but did not.")


def test_is_digit_space_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("1 000 000").is_digit()
    assert_that(str(exc_info.value)).is_equal_to("Expected <1 000 000> to contain only digits, but did not.")


def test_is_digit_punctuation_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("-123").is_digit()
    assert_that(str(exc_info.value)).is_equal_to("Expected <-123> to contain only digits, but did not.")


def test_is_digit_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_digit()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_digit_empty_value_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_digit()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_is_lower():
    assert_that("foo").is_lower()
    assert_that("foo 123").is_lower()
    assert_that("123 456").is_lower()


def test_is_lower_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("FOO").is_lower()
    assert_that(str(exc_info.value)).is_equal_to("Expected <FOO> to contain only lowercase chars, but did not.")


def test_is_lower_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_lower()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_lower_empty_value_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_lower()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_is_upper():
    assert_that("FOO").is_upper()
    assert_that("FOO 123").is_upper()
    assert_that("123 456").is_upper()


def test_is_upper_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_upper()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to contain only uppercase chars, but did not.")


def test_is_upper_bad_value_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_upper()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_upper_empty_value_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_upper()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_is_unicode():
    assert_that("unicorn").is_unicode()
    assert_that("unicorn 123").is_unicode()


def test_is_unicode_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(123).is_unicode()
    assert_that(str(exc_info.value)).is_equal_to("Expected <123> to be unicode, but was <int>.")


def test_is_alphanumeric():
    assert_that("abc123").is_alphanumeric()
    assert_that("hello").is_alphanumeric()
    assert_that("42").is_alphanumeric()


def test_is_alphanumeric_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("abc 123").is_alphanumeric()
    assert_that(str(exc_info.value)).is_equal_to("Expected <abc 123> to contain only alphanumeric chars, but did not.")


def test_is_alphanumeric_special_chars_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("hello!").is_alphanumeric()
    assert_that(str(exc_info.value)).is_equal_to("Expected <hello!> to contain only alphanumeric chars, but did not.")


def test_is_alphanumeric_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_alphanumeric()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_alphanumeric_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_alphanumeric()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_is_whitespace():
    assert_that(" ").is_whitespace()
    assert_that("  ").is_whitespace()
    assert_that("\t").is_whitespace()
    assert_that("\n").is_whitespace()
    assert_that(" \t\n").is_whitespace()


def test_is_whitespace_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foo").is_whitespace()
    assert_that(str(exc_info.value)).is_equal_to("Expected <foo> to contain only whitespace, but did not.")


def test_is_whitespace_mixed_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(" foo ").is_whitespace()
    assert_that(str(exc_info.value)).is_equal_to("Expected < foo > to contain only whitespace, but did not.")


def test_is_whitespace_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).is_whitespace()
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_is_whitespace_empty_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("").is_whitespace()
    assert_that(str(exc_info.value)).is_equal_to("val is empty")


def test_contains_any_of():
    assert_that("foobar").contains_any_of("foo", "xxx")
    assert_that("foobar").contains_any_of("xxx", "bar")
    assert_that("foobar").contains_any_of("foo", "bar")
    assert_that("foobar").contains_any_of("xxx", "yyy", "foo")


def test_contains_any_of_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_any_of("xxx", "yyy")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foobar> to contain any of <'xxx', 'yyy'>, but did not.")


def test_contains_any_of_single():
    assert_that("foobar").contains_any_of("foo")


def test_contains_any_of_single_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_any_of("xxx")
    assert_that(str(exc_info.value)).is_equal_to("Expected <foobar> to contain any of <xxx>, but did not.")


def test_contains_any_of_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_any_of("foo")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_contains_any_of_empty_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").contains_any_of()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_any_of_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_any_of(123)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <123> (int)")


def test_contains_none_of():
    assert_that("foobar").contains_none_of("xxx", "yyy")
    assert_that("foobar").contains_none_of("baz")


def test_contains_none_of_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_none_of("foo", "xxx")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foobar> to contain none of <'foo', 'xxx'>, but did contain <foo>."
    )


def test_contains_none_of_multiple_found_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("foobar").contains_none_of("foo", "bar")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <foobar> to contain none of <'foo', 'bar'>, but did contain <'foo', 'bar'>."
    )


def test_contains_none_of_bad_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).contains_none_of("foo")
    assert_that(str(exc_info.value)).is_equal_to("val must be a string, but was <123> (int)")


def test_contains_none_of_empty_args_failure():
    with pytest.raises(ValueError) as exc_info:
        assert_that("foo").contains_none_of()
    assert_that(str(exc_info.value)).is_equal_to("one or more args must be given")


def test_contains_none_of_bad_arg_type_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that("foo").contains_none_of(123)
    assert_that(str(exc_info.value)).is_equal_to("given item arg must be a string, but was <123> (int)")


def test_chaining():
    assert_that("foo").is_type_of(str).is_length(3).contains("f").does_not_contain("x")
    assert_that("fred").starts_with("f").ends_with("d").matches(r"^f.*?d$").does_not_match(r"\d")


def test_chaining_new_methods():
    assert_that("abc123").is_alphanumeric().contains_any_of("abc", "xyz").contains_none_of("xyz", "qqq")
