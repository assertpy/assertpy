import os
from pathlib import Path
from unittest.mock import patch

import pytest

from assertpy import assert_that, contents_of


@pytest.fixture()
def tmpfile(tmpdir):
    tmp = tmpdir.join("test.txt")
    tmp.write(b"foobar")
    with tmp.open("rb") as handle:
        yield handle


def test_contents_of_path(tmpfile):
    contents = contents_of(tmpfile.name)
    assert_that(contents).is_equal_to("foobar").starts_with("foo").ends_with("bar")


def test_contents_of_path_ascii(tmpfile):
    contents = contents_of(tmpfile.name, "ascii")
    assert_that(contents).is_equal_to("foobar").starts_with("foo").ends_with("bar")


def test_contents_of_path_respects_encoding(tmp_path):
    # the encoding arg must apply when reading a path, not only when decoding a bytes result
    path = tmp_path / "data.txt"
    path.write_bytes(b"caf\xe9")
    assert_that(contents_of(path, encoding="latin-1")).is_equal_to("café")


def test_contents_of_return_type(tmpfile):
    contents = contents_of(tmpfile.name)
    assert_that(contents).is_type_of(str)


def test_contents_of_return_type_ascii(tmpfile):
    contents = contents_of(tmpfile.name, "ascii")
    assert_that(contents).is_type_of(str)


def test_contents_of_file(tmpfile):
    contents = contents_of(tmpfile)
    assert_that(contents).is_equal_to("foobar").starts_with("foo").ends_with("bar")


def test_contents_of_file_ascii(tmpfile):
    contents = contents_of(tmpfile, "ascii")
    assert_that(contents).is_equal_to("foobar").starts_with("foo").ends_with("bar")


def test_contains_of_bad_type_failure(tmpfile):
    with pytest.raises(ValueError) as exc_info:
        contents_of(123)
    assert_that(str(exc_info.value)).is_equal_to("val must be file or path, but was type <int>")


def test_contains_of_bad_type_list_failure(tmpfile):
    with pytest.raises(ValueError) as exc_info:
        contents_of([1, 2, 3])
    assert_that(str(exc_info.value)).is_equal_to("val must be file or path, but was type <list>")


def test_contains_of_missing_file_failure(tmpfile):
    with pytest.raises(OSError) as exc_info:
        contents_of("missing.txt")
    assert_that(str(exc_info.value)).contains_ignoring_case("no such file")


def test_exists(tmpfile):
    assert_that(tmpfile.name).exists()
    assert_that(os.path.dirname(tmpfile.name)).exists()


def test_exists_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing.txt").exists()
    assert_that(str(exc_info.value)).is_equal_to("Expected <missing.txt> to exist, but was not found.")


def test_exists_bad_val_failure(tmpfile):
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).exists()
    assert_that(str(exc_info.value)).is_equal_to("val must be a path, but was <123> (int)")


def test_does_not_exist():
    assert_that("missing.txt").does_not_exist()


def test_does_not_exist_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        assert_that(tmpfile.name).does_not_exist()
    assert_that(str(exc_info.value)).is_equal_to(f"Expected <{tmpfile.name}> to not exist, but was found.")


def test_does_not_exist_bad_val_failure(tmpfile):
    with pytest.raises(TypeError) as exc_info:
        assert_that(123).does_not_exist()
    assert_that(str(exc_info.value)).is_equal_to("val must be a path, but was <123> (int)")


def test_is_file(tmpfile):
    assert_that(tmpfile.name).is_file()


def test_is_file_exists_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing.txt").is_file()
    assert_that(str(exc_info.value)).is_equal_to("Expected <missing.txt> to exist, but was not found.")


def test_is_file_directory_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        dirname = os.path.dirname(tmpfile.name)
        assert_that(dirname).is_file()
    assert_that(str(exc_info.value)).matches("Expected <.*> to be a file, but was not.")


def test_is_directory(tmpfile):
    dirname = os.path.dirname(tmpfile.name)
    assert_that(dirname).is_directory()


def test_is_directory_exists_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing_dir").is_directory()
    assert_that(str(exc_info.value)).is_equal_to("Expected <missing_dir> to exist, but was not found.")


def test_is_directory_file_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        assert_that(tmpfile.name).is_directory()
    assert_that(str(exc_info.value)).matches("Expected <.*> to be a directory, but was not.")


def test_is_named(tmpfile):
    basename = os.path.basename(tmpfile.name)
    assert_that(tmpfile.name).is_named(basename)


def test_is_named_pathlike_arg(tmpfile):
    # the filename arg may be an os.PathLike, not just a str (it was compared raw and never matched)
    basename = os.path.basename(tmpfile.name)
    assert_that(tmpfile.name).is_named(Path(basename))


def test_is_named_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        assert_that(tmpfile.name).is_named("foo.txt")
    assert_that(str(exc_info.value)).matches("Expected filename <.*> to be equal to <foo.txt>, but was not.")


def test_is_named_failure_name_sorts_after_basename(tmpfile):
    # a name that sorts after the basename (basename + an extra char) is still a mismatch
    larger_name = os.path.basename(tmpfile.name) + "x"
    with pytest.raises(AssertionError):
        assert_that(tmpfile.name).is_named(larger_name)


def test_is_named_bad_arg_type_failure(tmpfile):
    with pytest.raises(TypeError) as exc_info:
        assert_that(tmpfile.name).is_named(123)
    assert_that(str(exc_info.value)).matches("given filename arg must be a path")


def test_is_child_of(tmpfile):
    dirname = os.path.dirname(tmpfile.name)
    assert_that(tmpfile.name).is_child_of(dirname)


def test_is_child_of_failure(tmpfile):
    with pytest.raises(AssertionError) as exc_info:
        assert_that(tmpfile.name).is_child_of("foo_dir")
    assert_that(str(exc_info.value)).matches(r"Expected file <.*> to be a child of <.*[\\/]foo_dir>, but was not.")


def test_is_child_of_rejects_sibling_with_prefix_name(tmp_path):
    parent = tmp_path / "my"
    parent.mkdir()
    sibling = tmp_path / "myfile.txt"
    sibling.write_text("x")
    with pytest.raises(AssertionError):
        assert_that(str(sibling)).is_child_of(str(parent))


def test_is_child_of_bad_arg_type_failure(tmpfile):
    with pytest.raises(TypeError) as exc_info:
        assert_that(tmpfile.name).is_child_of(123)
    assert_that(str(exc_info.value)).matches("given parent directory arg must be a path")


def test_is_readable(tmpfile):
    assert_that(tmpfile.name).is_readable()


def test_is_readable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing.txt").is_readable()
    assert_that(str(exc_info.value)).contains("to exist, but was not found.")


def test_is_writable(tmpfile):
    assert_that(tmpfile.name).is_writable()


def test_is_writable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing.txt").is_writable()
    assert_that(str(exc_info.value)).contains("to exist, but was not found.")


def test_is_executable(tmpfile):
    os.chmod(tmpfile.name, 0o755)
    assert_that(tmpfile.name).is_executable()


def test_is_executable_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that("missing.txt").is_executable()
    assert_that(str(exc_info.value)).contains("to exist, but was not found.")


def test_is_readable_chaining(tmpfile):
    assert_that(tmpfile.name).is_file().is_readable().is_writable()


def test_exists_path_object(tmpfile):
    assert_that(Path(tmpfile.name)).exists()


def test_is_file_path_object(tmpfile):
    assert_that(Path(tmpfile.name)).is_file()


def test_is_directory_path_object(tmpfile):
    assert_that(Path(os.path.dirname(tmpfile.name))).is_directory()


def test_is_named_path_object(tmpfile):
    basename = os.path.basename(tmpfile.name)
    assert_that(Path(tmpfile.name)).is_named(basename)


def test_is_child_of_path_object(tmpfile):
    dirname = os.path.dirname(tmpfile.name)
    assert_that(Path(tmpfile.name)).is_child_of(dirname)


def test_contents_of_path_object(tmpfile):
    contents = contents_of(Path(tmpfile.name))
    assert_that(contents).is_equal_to("foobar")


def test_does_not_exist_path_object():
    assert_that(Path("missing.txt")).does_not_exist()


def test_contents_of_missing_path_object():
    with pytest.raises(OSError) as exc_info:
        contents_of(Path("missing.txt"))
    assert_that(str(exc_info.value)).contains_ignoring_case("no such file")


def test_is_readable_not_readable(tmpfile):
    with patch("os.access", return_value=False):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(tmpfile.name).is_readable()
        assert_that(str(exc_info.value)).matches("Expected <.*> to be readable, but was not.")


def test_is_writable_not_writable(tmpfile):
    with patch("os.access", return_value=False):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(tmpfile.name).is_writable()
        assert_that(str(exc_info.value)).matches("Expected <.*> to be writable, but was not.")


def test_is_executable_not_executable(tmpfile):
    with patch("os.access", return_value=False):
        with pytest.raises(AssertionError) as exc_info:
            assert_that(tmpfile.name).is_executable()
        assert_that(str(exc_info.value)).matches("Expected <.*> to be executable, but was not.")


def test_a_missing_bytes_path_is_reported_as_the_missing_file_it_is():
    """Only `str` and `PathLike` were re-checked, so a `bytes` path read as "not a file or path" instead."""
    with pytest.raises(FileNotFoundError):
        contents_of(b"nowhere-at-all-12345.txt")


def test_something_that_is_not_a_path_at_all_still_says_so():
    with pytest.raises(ValueError, match="val must be file or path"):
        contents_of(123)
