import pytest

from assertpy import assert_all, assert_that, soft_assertions, soft_fail


class TestGroupedSoftAssertions:
    def test_single_group(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa, sa.group("Numbers"):
            assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        msg = str(exc_info.value)
        assert_that(msg).contains("[Numbers]")
        assert_that(msg).contains("1. Expected <1>")
        assert_that(msg).contains("2. Expected <3>")

    def test_grouped_report_indents_items_and_locates_them(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa, sa.group("Body"):
            assert_that(1).is_equal_to(2)
        report = str(exc_info.value)
        assert_that(report).contains("\n  [Body]")
        assert_that(report).contains("\n    1. Expected <1>")
        assert_that(report).contains("test_grouped_soft.py:")

    def test_multiple_groups(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa:
            with sa.group("Headers"):
                assert_that("text/plain").is_equal_to("application/json")
            with sa.group("Body"):
                assert_that("error").is_equal_to("ok")
                assert_that(0).is_equal_to(1)
        msg = str(exc_info.value)
        assert_that(msg).contains("[Headers]")
        assert_that(msg).contains("[Body]")
        assert_that(msg).contains("1.")
        assert_that(msg).contains("2.")
        assert_that(msg).contains("3.")

    def test_mixed_grouped_and_ungrouped(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa:
            assert_that("a").is_equal_to("b")
            with sa.group("Group1"):
                assert_that("c").is_equal_to("d")
            assert_that("e").is_equal_to("f")
        msg = str(exc_info.value)
        assert_that(msg).contains("1. Expected <a>")
        assert_that(msg).contains("[Group1]")
        assert_that(msg).contains("2. Expected <c>")
        assert_that(msg).contains("3. Expected <e>")

    def test_no_groups_backward_compat(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        msg = str(exc_info.value)
        assert_that(msg).starts_with("soft assertion failures:")
        assert_that(msg).contains("\n1. Expected <1>")
        assert_that(msg).contains("\n2. Expected <3>")
        assert_that(msg).contains("test_grouped_soft.py:")

    def test_each_failure_is_located_at_its_own_line(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions():
            assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        report = str(exc_info.value).splitlines()
        first_location = report[1].rsplit("[", 1)[1]
        second_location = report[2].rsplit("[", 1)[1]
        assert_that(first_location).contains("test_grouped_soft.py:")
        assert_that(first_location).is_not_equal_to(second_location)

    def test_groups_success_no_error(self):
        with soft_assertions() as sa:
            with sa.group("Valid"):
                assert_that(1).is_equal_to(1)
            with sa.group("Also valid"):
                assert_that("foo").is_length(3)

    def test_nested_groups(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa, sa.group("Outer"):
            assert_that(1).is_equal_to(2)
            with sa.group("Inner"):
                assert_that(3).is_equal_to(4)
            assert_that(5).is_equal_to(6)
        msg = str(exc_info.value)
        assert_that(msg).contains("[Outer]")
        assert_that(msg).contains("[Inner]")
        assert_that(msg).contains("1. Expected <1>")
        assert_that(msg).contains("2. Expected <3>")
        assert_that(msg).contains("3. Expected <5>")

    def test_group_restores_after_exit(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa:
            with sa.group("G1"):
                assert_that(1).is_equal_to(2)
            assert_that(3).is_equal_to(4)
        msg = str(exc_info.value)
        assert_that(msg).contains("[G1]")
        assert_that(msg).contains("1. Expected <1>")
        assert_that(msg).contains("2. Expected <3>")


class TestGroupedWithNot:
    def test_not_inside_group(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa, sa.group("Negation"):
            assert_that(5).not_.is_positive()
        msg = str(exc_info.value)
        assert_that(msg).contains("[Negation]")
        assert_that(msg).contains("to NOT satisfy")


class TestGroupedWithSoftFail:
    def test_soft_fail_inside_group(self):
        with pytest.raises(AssertionError) as exc_info, soft_assertions() as sa, sa.group("Custom"):
            soft_fail("manual failure")
        msg = str(exc_info.value)
        assert_that(msg).contains("[Custom]")
        assert_that(msg).contains("Fail: manual failure!")


class TestAssertAll:
    def test_all_pass(self):
        assert_all(
            lambda: assert_that(1).is_positive(),
            lambda: assert_that("foo").is_length(3),
        )

    def test_collects_failures(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_all(
                lambda: assert_that(1).is_equal_to(2),
                lambda: assert_that("foo").is_empty(),
            )
        msg = str(exc_info.value)
        assert_that(msg).contains("1.")
        assert_that(msg).contains("2.")

    def test_single_failure(self):
        with pytest.raises(AssertionError) as exc_info:
            assert_all(
                lambda: assert_that(1).is_positive(),
                lambda: assert_that(-1).is_positive(),
                lambda: assert_that(2).is_positive(),
            )
        msg = str(exc_info.value)
        assert_that(msg).contains("1. Expected <-1>")
        assert_that(msg).does_not_contain("2.")

    def test_empty_callables(self):
        assert_all()
