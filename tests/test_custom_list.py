import pytest

from assertpy import assert_that


class CustomList:
    def __init__(self, s):
        self._s = s
        self._idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            result = self._s[self._idx]
        except IndexError:
            raise StopIteration from None
        self._idx += 1
        return result

    def __getitem__(self, idx):
        return self._s[idx]


def test_custom_list():
    CustomList("foobar")
    assert_that([CustomList("foo"), CustomList("bar")]).extracting(0, -1).is_equal_to([("f", "o"), ("b", "r")])


def test_check_iterable(builder):
    custom_list = CustomList("foobar")
    builder._check_iterable(custom_list)
    builder._check_iterable(custom_list, check_getitem=True)
    builder._check_iterable(custom_list, check_getitem=False)


def test_check_iterable_not_iterable(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._check_iterable(123, name="my-int")
    assert_that(str(exc_info.value)).contains("my-int must be iterable")


def test_check_iterable_no_getitem(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._check_iterable({1}, name="my-set")
    assert_that(str(exc_info.value)).contains("my-set must be a value with a [] accessor")
