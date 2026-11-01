from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from ._engine._mixin_base import _MixinBase
from ._engine._require import argument, require_type
from .errors import _capped

if TYPE_CHECKING:
    from ._engine._compat import Self
    from ._engine._introspection import Readable

__tracebackhide__ = True


def contents_of(file: str | bytes | os.PathLike[str] | os.PathLike[bytes] | Readable, encoding: str = "utf-8") -> str:
    """Helper to read the contents of the given file or path into a string with the given encoding.

    Args:
        file (str | os.PathLike | IO): a *path-like object* (aka a file name) or a *file-like object* (aka a file)
        encoding (str): the target encoding. Defaults to ``utf-8`` (others: ``ascii``, ``latin-1``).

    Examples:
        Usage:

            from assertpy import assert_that, contents_of

            contents = contents_of('foo.txt')
            assert_that(contents).starts_with('foo').ends_with('bar').contains('oob')

    Returns:
        str: returns the file contents as a string

    Raises:
        IOError: if file not found
        TypeError: if file is not a *path-like object* or a *file-like object*
    """
    try:
        # the `except` is what decides this: a path has no `read`, and asking first would not tell us more
        contents = cast("Readable", file).read()
    except AttributeError:
        try:
            path = cast("str | bytes | os.PathLike[str] | os.PathLike[bytes]", file)
            with open(path, encoding=encoding, errors="replace") as file_handle:
                contents = file_handle.read()
        except TypeError:
            raise ValueError(f"val must be file or path, but was type <{type(file).__name__}>") from None
        except OSError:
            if not isinstance(file, (str, bytes, os.PathLike)):
                raise ValueError(f"val must be file or path, but was type <{type(file).__name__}>") from None
            raise

    if isinstance(contents, (bytes, bytearray)):
        return contents.decode(encoding, "replace")
    return contents


class FileMixin(_MixinBase):
    """File assertions mixin."""

    def exists(self) -> Self:
        """Asserts that val is a path and that it exists.

        Examples:
            Usage:

                assert_that('myfile.txt').exists()
                assert_that('mydir').exists()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist
        """
        missing = self._missing()
        if missing is not None:
            return self.error(missing)
        return self

    def does_not_exist(self) -> Self:
        """Asserts that val is a path and that it does *not* exist.

        Examples:
            Usage:

                assert_that('missing.txt').does_not_exist()
                assert_that('missing_dir').does_not_exist()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** exist
        """
        require_type(self.val, (str, os.PathLike), "a path")
        if os.path.exists(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to not exist, but was found.")
        return self

    def is_file(self) -> Self:
        """Asserts that val is a *file* and that it exists.

        Nothing at the path is one of the answers rather than a question left unasked, so
        ``not_.is_file()`` holds for a path that does not exist.

        Examples:
            Usage:

                assert_that('myfile.txt').is_file()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a file
        """
        not_a_file = self._not_a_file()
        if not_a_file is not None:
            return self.error(not_a_file)
        return self

    def is_directory(self) -> Self:
        """Asserts that val is a *directory* and that it exists.

        Nothing at the path is one of the answers rather than a question left unasked, so
        ``not_.is_directory()`` holds for a path that does not exist.

        Examples:
            Usage:

                assert_that('mydir').is_directory()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a directory
        """
        missing = self._missing()
        if missing is not None:
            return self.error(missing)
        if not os.path.isdir(self.val):
            return self.error(f"Expected <{_capped(self.val)}> to be a directory, but was not.")
        return self

    def is_named(self, filename: str) -> Self:
        """Asserts that val is an existing path to a file and that file is named filename.

        A path that is not an existing file fails it with or without ``not_``: the name is asked of the file.

        Args:
            filename: the expected filename

        Examples:
            Usage:

                assert_that('/path/to/mydir/myfile.txt').is_named('myfile.txt')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** a file, or is **not** named the given filename
            TypeError: if filename is not a path, whatever val is
        """
        require_type(filename, (str, os.PathLike), "a path", subject=argument("filename"))
        if not self._require_file():
            return self
        val_filename = os.path.basename(os.path.abspath(self.val))
        expected_filename = os.fspath(filename)  # normalize an os.PathLike arg to its string form
        if val_filename == expected_filename:
            return self
        return self.error(
            f"Expected filename <{val_filename}> to be equal to <{expected_filename}>, but was not.",
            expected=filename,
        )

    def is_child_of(self, parent: object) -> Self:
        """Asserts that val is an existing path to a file and that file is a child of parent.

        A path that is not an existing file fails it with or without ``not_``: the parent is asked of the file.

        Args:
            parent: the expected parent directory

        Examples:
            Usage:

                assert_that('/path/to/mydir/myfile.txt').is_child_of('/path/to/mydir')
                assert_that('/path/to/mydir/myfile.txt').is_child_of('/path/to')
                assert_that('/path/to/mydir/myfile.txt').is_child_of('/path')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, is **not** a file, or is **not** a child of given directory
            TypeError: if parent is not a path, whatever val is
        """
        parent_path = require_type(parent, (str, os.PathLike), "a path", subject=argument("parent directory"))
        if not self._require_file():
            return self
        val_abspath = os.path.abspath(self.val)
        parent_abspath = os.path.abspath(parent_path)
        try:
            is_child = os.path.commonpath([val_abspath, parent_abspath]) == parent_abspath != val_abspath
        except ValueError:  # pragma: no cover - Windows-only: paths on different drives share no common path
            is_child = False
        if not is_child:
            return self.error(
                f"Expected file <{val_abspath}> to be a child of <{parent_abspath}>, but was not.", expected=parent_path
            )
        return self

    def is_readable(self) -> Self:
        """Asserts that val is an existing path and is readable.

        A path that does not exist fails it with or without ``not_``: a permission is asked of what is at
        the path.

        Examples:
            Usage:

                assert_that('/path/to/file.txt').is_readable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** readable
        """
        if not self._require_existing():
            return self
        if not os.access(self.val, os.R_OK):
            return self.error(f"Expected <{_capped(self.val)}> to be readable, but was not.")
        return self

    def is_writable(self) -> Self:
        """Asserts that val is an existing path and is writable.

        A path that does not exist fails it with or without ``not_``: a permission is asked of what is at
        the path.

        Examples:
            Usage:

                assert_that('/path/to/file.txt').is_writable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** writable
        """
        if not self._require_existing():
            return self
        if not os.access(self.val, os.W_OK):
            return self.error(f"Expected <{_capped(self.val)}> to be writable, but was not.")
        return self

    def is_executable(self) -> Self:
        """Asserts that val is an existing path and is executable.

        A path that does not exist fails it with or without ``not_``: a permission is asked of what is at
        the path.

        Examples:
            Usage:

                assert_that('/path/to/script.sh').is_executable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** exist, or is **not** executable
        """
        if not self._require_existing():
            return self
        if not os.access(self.val, os.X_OK):
            return self.error(f"Expected <{_capped(self.val)}> to be executable, but was not.")
        return self

    def _missing(self) -> str | None:
        """The failure for a path that does not exist, or ``None`` when it does.

        Composed once for both of its readings: `exists()` answers with it, and an assertion about what is
        at the path reports it as the prerequisite its question presupposes.
        """
        require_type(self.val, (str, os.PathLike), "a path")
        if os.path.exists(self.val):
            return None
        return f"Expected <{_capped(self.val)}> to exist, but was not found."

    def _not_a_file(self) -> str | None:
        """The failure for a path that is not an existing file, or ``None`` when it is one."""
        missing = self._missing()
        if missing is not None or os.path.isfile(self.val):
            return missing
        return f"Expected <{_capped(self.val)}> to be a file, but was not."

    def _require_existing(self) -> bool:
        """Whether val exists, after reporting as a prerequisite that it does not.

        A permission belongs to what is at the path, so with nothing there the question has no answer.
        Inverted, a mistyped path passed ``not_.is_readable()`` as a file nobody may read.
        """
        missing = self._missing()
        if missing is not None:
            self._unmet(missing)
        return missing is None

    def _require_file(self) -> bool:
        """Whether val is an existing file, after reporting as a prerequisite that it is not.

        A name and a parent are asked of the file at the path, so a missing path or a directory answers
        neither the question nor its negation.
        """
        not_a_file = self._not_a_file()
        if not_a_file is not None:
            self._unmet(not_a_file)
        return not_a_file is None
