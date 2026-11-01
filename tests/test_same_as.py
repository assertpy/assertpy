import sys

import pytest

from assertpy import assert_that


def test_is_same_as():
    for obj in [object(), 1, "foo", True, None, 123.456]:
        assert_that(obj).is_same_as(obj)


def test_is_same_as_failure():
    with pytest.raises(AssertionError) as exc_info:
        obj = object()
        other = object()
        assert_that(obj).is_same_as(other)
    assert_that(str(exc_info.value)).matches("Expected <.+> to be identical to <.+>, but was not.")


def test_is_not_same_as():
    obj = object()
    other = object()
    assert_that(obj).is_not_same_as(other)
    assert_that(obj).is_not_same_as(1)
    assert_that(obj).is_not_same_as(True)
    assert_that(1).is_not_same_as(2)

    assert_that({"a": 1}).is_not_same_as({"a": 1})
    assert_that([1, 2, 3]).is_not_same_as([1, 2, 3])

    if sys.version_info[0] == 3 and sys.version_info[1] >= 7:
        assert_that((1, 2, 3)).is_same_as((1, 2, 3))  # tuples are identical in py 3.7
    else:
        assert_that((1, 2, 3)).is_not_same_as((1, 2, 3))


def test_is_not_same_as_failure():
    for obj in [object(), 1, "foo", True, None, 123.456]:
        with pytest.raises(AssertionError) as exc_info:
            assert_that(obj).is_not_same_as(obj)
        assert_that(str(exc_info.value)).matches("Expected <.+> to be not identical to <.+>, but was.")
