from __future__ import annotations

from typing import TYPE_CHECKING, SupportsIndex

from ._engine._mixin_base import _MixinBase
from ._engine._ordering import require_integer
from ._engine._require import refuse, sized_len

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


class BytesMixin(_MixinBase):
    """Assertions for bytes and bytearray values."""

    def _check_bytes(self) -> None:
        if not isinstance(self.val, (bytes, bytearray)):
            refuse(self.val, "bytes or a bytearray")

    def is_valid_utf8(self) -> Self:
        """Assert that val is valid UTF-8.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is not valid UTF-8
        """
        self._check_bytes()
        try:
            self.val.decode("utf-8")
        except UnicodeDecodeError:
            return self.error("Expected valid UTF-8, but decoding failed.")
        return self

    def is_valid_encoding(self, encoding: str) -> Self:
        """Assert that val is valid in the given encoding.

        Args:
            encoding: the encoding to validate against (e.g. ``"ascii"``, ``"utf-16"``).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val cannot be decoded with the given encoding
            LookupError: if there is no such codec, which is a mistake in the call rather than a verdict
                about the value: reported as a failure, ``not_`` and ``check()`` said the value was fine
        """
        self._check_bytes()
        try:
            self.val.decode(encoding)
        except UnicodeDecodeError:
            return self.error(f"Expected valid {encoding} encoding, but decoding failed.", expected=encoding)
        return self

    def starts_with_bytes(self, prefix: bytes | bytearray) -> Self:
        """Assert that val starts with the given byte prefix.

        The bytes-only spelling of [`starts_with()`][assertpy.string.StringMixin.starts_with], which it
        delegates to.  It carried its own implementation until `starts_with` learned to handle ``bytes``:
        before that, a byte string fell through to the element-wise branch and ``b"foo"`` compared its
        first element, the int ``102``, against ``b"f"``.  Two implementations of one relation is how they
        drift, and these two already had: this one accepted an empty prefix, which asserts nothing.

        Args:
            prefix: the expected byte prefix.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            TypeError: if val is not ``bytes``/``bytearray``
            ValueError: if the prefix is empty, which no value can fail
            AssertionError: if val does not start with the prefix
        """
        self._check_bytes()
        return self.starts_with(prefix)

    def contains_bytes(self, sub: bytes | bytearray) -> Self:
        """Assert that val contains the given byte subsequence.

        The bytes-only spelling of [`contains()`][assertpy.contains.ContainsMixin.contains], which it
        delegates to.  Delegating is what gives the failure the value under test and a structured diff,
        neither of which its own implementation produced.

        Args:
            sub: the byte subsequence to find.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            TypeError: if val is not ``bytes``/``bytearray``
            AssertionError: if val does not contain the subsequence
        """
        self._check_bytes()
        return self.contains(sub)

    def has_byte_at(self, index: SupportsIndex, expected: SupportsIndex) -> Self:
        """Assert that the byte at the given index equals the expected value.

        Args:
            index: zero-based byte index.
            expected: expected byte value (0-255).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if the byte at index does not match
        """
        self._check_bytes()
        position = index if type(index) is int else require_integer(index, "index")
        if position < 0 or position >= sized_len(self.val):
            raise IndexError(f"Expected index {index} to be in range [0, {sized_len(self.val)}), but was out of range.")
        actual = self.val[position]
        if actual == expected:
            return self
        return self.error(
            f"Expected byte at index {index} to be <0x{expected:02x}>, but was <0x{actual:02x}>.", expected=expected
        )

    def is_hex_equal_to(self, expected_hex: str) -> Self:
        """Assert that val equals the given hex string.

        Args:
            expected_hex: hex string without prefix (e.g. ``"abcdef"``).

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does not match the hex string
        """
        self._check_bytes()
        expected = bytes.fromhex(expected_hex)
        if self.val == expected:
            return self
        return self.error(f"Expected hex <{expected_hex}>, but was <{self.val.hex()}>.", expected=expected_hex)

    def decoded_as(self, encoding: str = "utf-8") -> Self:
        """Decode val and return a new builder with the decoded string.

        Args:
            encoding: the encoding to use (default ``"utf-8"``).

        Returns:
            AssertionBuilder: a new instance with the decoded string as val

        Raises:
            UnicodeDecodeError: if val cannot be decoded
        """
        self._check_bytes()
        decoded = self.val.decode(encoding)
        return self.builder(decoded, self.description, self.kind, logger=self.logger)
