from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ._engine._mixin_base import _MixinBase
from ._engine._ordering import REFUSALS, equals, lookup, member
from ._engine._require import argument, refuse
from .contains import _entry_not_found, _value_not_found
from .errors import _capped

if TYPE_CHECKING:
    from ._engine._compat import Self

__tracebackhide__ = True


class DictMixin(_MixinBase):
    """Dict assertions mixin."""

    def contains_key(self, *keys: object) -> Self:
        """Asserts the val is a dict and contains the given key or keys.

        Alias for [`contains()`][assertpy.contains.ContainsMixin.contains].

        Checks if the dict contains the given key or keys using ``in`` operator.

        Args:
            *keys: the key or keys expected to be contained

        Examples:
            Usage:

                assert_that({'a': 1, 'b': 2}).contains_key('a')
                assert_that({'a': 1, 'b': 2}).contains_key('a', 'b')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the key or keys
        """
        self._require_dict_like(self.val, check_values=False, check_getitem=False)
        return self.contains(*keys)

    def does_not_contain_key(self, *keys: object) -> Self:
        """Asserts the val is a dict and does not contain the given key or keys.

        Alias for [`does_not_contain()`][assertpy.contains.ContainsMixin.does_not_contain].

        Checks if the dict excludes the given key or keys using ``in`` operator.

        Args:
            *keys: the key or keys expected to be excluded

        Examples:
            Usage:

                assert_that({'a': 1, 'b': 2}).does_not_contain_key('x')
                assert_that({'a': 1, 'b': 2}).does_not_contain_key('x', 'y')

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain the key or keys
        """
        self._require_dict_like(self.val, check_values=False, check_getitem=False)
        return self.does_not_contain(*keys)

    def contains_value(self, *values: object) -> Self:
        """Asserts that val is a dict and contains the given value or values.

        Checks if the dict contains the given value or values in *any* key.

        Args:
            *values: the value or values expected to be contained

        Examples:
            Usage:

                assert_that({'a': 1, 'b': 2}).contains_value(1)
                assert_that({'a': 1, 'b': 2}).contains_value(1, 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the value or values
        """
        self._require_dict_like(self.val, check_getitem=False)
        if len(values) == 0:
            raise ValueError("one or more value args must be given")
        missing = [value for value in values if not member(value, self.val.values())]
        if missing:
            return self.error(
                f"Expected <{_capped(self.val)}> to contain values {self._fmt_items(values)},"
                f" but did not contain {self._fmt_items(missing)}." + _value_not_found(self.val, missing),
                expected=values,
            )
        return self

    def does_not_contain_value(self, *values: object) -> Self:
        """Asserts that val is a dict and does not contain the given value or values.

        Checks if the dict excludes the given value or values across *all* keys.

        Args:
            *values: the value or values expected to be excluded

        Examples:
            Usage:

                assert_that({'a': 1, 'b': 2}).does_not_contain_value(3)
                assert_that({'a': 1, 'b': 2}).does_not_contain_value(3, 4)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain the value or values
        """
        self._require_dict_like(self.val, check_getitem=False)
        if len(values) == 0:
            raise ValueError("one or more value args must be given")
        else:
            found = [value for value in values if member(value, self.val.values())]
            if found:
                return self.error(
                    f"Expected <{_capped(self.val)}> to not contain values {self._fmt_items(values)},"
                    f" but did contain {self._fmt_items(found)}."
                )
        return self

    def contains_entry(self, *args: object, **kwargs: object) -> Self:
        """Asserts that val is a dict and contains the given entry or entries.

        Checks if the dict contains the given key-value pair or pairs.

        Args:
            *args (object): the entry or entries expected to be contained (as ``{k: v}`` args)
            **kwargs (object): the entry or entries expected to be contained (as ``k=v`` kwargs)

        Examples:
            Usage:

                # using args
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry({'a': 1})
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry({'a': 1}, {'b': 2})
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry({'a': 1}, {'b': 2}, {'c': 3})

                # using kwargs
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry(a=1)
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry(a=1, b=2)
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry(a=1, b=2, c=3)

                # or args and kwargs
                assert_that({'a': 1, 'b': 2, 'c': 3}).contains_entry({'c': 3}, a=1, b=2)


        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val does **not** contain the entry or entries

        Note:
            Where one entry is not found, the failure says what its key holds, or that the key is not there, and
            on a line under the message why the value held is not the one expected, where one fact says so.
        """
        self._require_dict_like(self.val, check_values=False)
        entries = list(args) + [{key: value} for key, value in kwargs.items()]
        if len(entries) == 0:
            raise ValueError("one or more entry args must be given")
        missing = []
        for entry in entries:
            if type(entry) is not dict:
                refuse(entry, "a dict", subject=argument("entry"))
            # `object` not `dict`: the check above is `type(entry) is dict`, so a subclass is refused here
            pair = cast("dict[Any, Any]", entry)
            if len(pair) != 1:
                raise ValueError("given entry args must contain exactly one key-value pair")
            entry_key = next(iter(pair))
            try:
                if entry_key in self.val and equals(self.val[entry_key], pair[entry_key]):
                    continue
            except REFUSALS as refusal:
                found, held = lookup(self.val, entry_key, refusal)
                if found and equals(held, pair[entry_key]):
                    continue
            missing.append(pair)
        if missing:
            return self.error(
                f"Expected <{_capped(self.val)}> to contain entries {self._fmt_items(entries)},"
                f" but did not contain {self._fmt_items(missing)}." + _entry_not_found(self.val, missing),
                expected=entries,
            )
        return self

    def does_not_contain_entry(self, *args: object, **kwargs: object) -> Self:
        """Asserts that val is a dict and does not contain the given entry or entries.

        Checks if the dict excludes the given key-value pair or pairs.

        Args:
            *args (object): the entry or entries expected to be excluded (as ``{k: v}`` args)
            **kwargs (object): the entry or entries expected to be excluded (as ``k=v`` kwargs)

        Examples:
            Usage:

                # using args
                assert_that({'a': 1, 'b': 2, 'c': 3}).does_not_contain_entry({'a': 2})
                assert_that({'a': 1, 'b': 2, 'c': 3}).does_not_contain_entry({'a': 2}, {'x': 4})

                # using kwargs
                assert_that({'a': 1, 'b': 2, 'c': 3}).does_not_contain_entry(a=2)
                assert_that({'a': 1, 'b': 2, 'c': 3}).does_not_contain_entry(a=2, x=4)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **does** contain the entry or entries
        """
        self._require_dict_like(self.val, check_values=False)
        entries = list(args) + [{key: value} for key, value in kwargs.items()]
        if len(entries) == 0:
            raise ValueError("one or more entry args must be given")
        found = []
        for entry in entries:
            if type(entry) is not dict:
                refuse(entry, "a dict", subject=argument("entry"))
            pair = cast("dict[Any, Any]", entry)
            if len(pair) != 1:
                raise ValueError("given entry args must contain exactly one key-value pair")
            entry_key = next(iter(pair))
            try:
                present = entry_key in self.val and equals(self.val[entry_key], pair[entry_key])
            except REFUSALS as refusal:
                held_there, held = lookup(self.val, entry_key, refusal)
                present = held_there and equals(held, pair[entry_key])
            if present:
                found.append(pair)
        if found:
            return self.error(
                f"Expected <{_capped(self.val)}> to not contain entries {self._fmt_items(entries)},"
                f" but did contain {self._fmt_items(found)}."
            )
        return self
