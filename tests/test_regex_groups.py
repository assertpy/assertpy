from __future__ import annotations

import pytest

from assertpy import assert_that, soft_assertions


class TestExtractingGroup:
    def test_positional_group(self):
        assert_that("status=200 path=/api").extracting_group(r"status=(\d+)", 1).is_equal_to("200")

    def test_named_group(self):
        assert_that("2024-01-15 ERROR msg").extracting_group(r"(?P<level>\w+) msg$", "level").is_equal_to("ERROR")

    def test_group_zero_entire_match(self):
        assert_that("hello world").extracting_group(r"hello (\w+)", 0).is_equal_to("hello world")

    def test_default_group_zero(self):
        assert_that("abc123").extracting_group(r"\d+").is_equal_to("123")

    def test_chaining_after_extraction(self):
        assert_that("count=42").extracting_group(r"count=(\d+)", 1).is_digit().is_length(2)

    def test_extracts_to_new_builder(self):
        assert_that("code=404 msg=not_found").extracting_group(r"code=(\d+)", 1).starts_with("4").ends_with("4")

    def test_preserves_description(self):
        with pytest.raises(AssertionError, match=r"\[API check\]"):
            assert_that("status=200").described_as("API check").extracting_group(r"status=(\d+)", 1).is_equal_to("500")

    def test_no_match_fails(self):
        with pytest.raises(AssertionError, match="to match pattern"):
            assert_that("no numbers here").extracting_group(r"(\d+)", 1)

    def test_invalid_group_index(self):
        with pytest.raises(AssertionError, match="to have group"):
            assert_that("abc123").extracting_group(r"(\d+)", 5)

    def test_unmatched_optional_group(self):
        with pytest.raises(AssertionError, match="to be matched"):
            assert_that("hello").extracting_group(r"hello(?:(\d+))?", 1)

    def test_val_not_string(self):
        with pytest.raises(TypeError, match="val must be a string"):
            assert_that(123).extracting_group(r"\d+", 0)

    def test_pattern_not_string(self):
        with pytest.raises(TypeError, match="given pattern arg must be a string"):
            assert_that("hello").extracting_group(123, 0)

    def test_pattern_empty(self):
        with pytest.raises(ValueError, match="given pattern arg must not be empty"):
            assert_that("hello").extracting_group("", 0)

    def test_multiple_groups(self):
        assert_that("2024-01-15").extracting_group(r"(\d{4})-(\d{2})-(\d{2})", 1).is_equal_to("2024")
        assert_that("2024-01-15").extracting_group(r"(\d{4})-(\d{2})-(\d{2})", 2).is_equal_to("01")
        assert_that("2024-01-15").extracting_group(r"(\d{4})-(\d{2})-(\d{2})", 3).is_equal_to("15")

    def test_soft_assertions_mode(self):
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that("status=200").extracting_group(r"status=(\d+)", 1).is_equal_to("500")
            assert_that("code=404").extracting_group(r"code=(\d+)", 1).is_equal_to("200")


class TestMatchesWithGroups:
    def test_positional_groups_tuple(self):
        assert_that("2024-01-15 ERROR").matches_with_groups(r"(\d{4}-\d{2}-\d{2}) (\w+)").is_length(2)

    def test_positional_groups_values(self):
        assert_that("2024-01-15 ERROR").matches_with_groups(r"(\d{4}-\d{2}-\d{2}) (\w+)").is_equal_to(
            ("2024-01-15", "ERROR")
        )

    def test_named_groups_dict(self):
        assert_that("key=value").matches_with_groups(r"(?P<key>\w+)=(?P<val>\w+)").contains_key("key").contains_key(
            "val"
        )

    def test_named_groups_values(self):
        result = {"key": "status", "val": "200"}
        assert_that("status=200").matches_with_groups(r"(?P<key>\w+)=(?P<val>\w+)").is_equal_to(result)

    def test_chaining_on_dict(self):
        assert_that("name=Alice").matches_with_groups(r"(?P<key>\w+)=(?P<val>\w+)").contains_entry(
            {"key": "name"}
        ).contains_entry({"val": "Alice"})

    def test_no_match_fails(self):
        with pytest.raises(AssertionError, match="to match pattern"):
            assert_that("no match").matches_with_groups(r"(\d+)")

    def test_preserves_description(self):
        with pytest.raises(AssertionError, match=r"\[log parsing\]"):
            assert_that("no match").described_as("log parsing").matches_with_groups(r"(\d+)")

    def test_val_not_string(self):
        with pytest.raises(TypeError, match="val must be a string"):
            assert_that(42).matches_with_groups(r"(\d+)")

    def test_pattern_not_string(self):
        with pytest.raises(TypeError, match="given pattern arg must be a string"):
            assert_that("hello").matches_with_groups(42)

    def test_pattern_empty(self):
        with pytest.raises(ValueError, match="given pattern arg must not be empty"):
            assert_that("hello").matches_with_groups("")

    def test_single_group(self):
        assert_that("hello123").matches_with_groups(r"(\d+)").is_equal_to(("123",))

    def test_soft_assertions_mode(self):
        with pytest.raises(AssertionError, match="soft assertion failures"), soft_assertions():
            assert_that("a=1").matches_with_groups(r"(?P<k>\w+)=(?P<v>\w+)").contains_entry({"k": "x"})
