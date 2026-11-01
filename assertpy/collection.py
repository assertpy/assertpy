from __future__ import annotations

import collections.abc
import inspect
from typing import TYPE_CHECKING, Any, SupportsIndex, cast

from ._engine._introspection import is_mapping_like
from ._engine._membership import flattened_supersets, subset_faults
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import (
    UnorderableError,
    first_out_of_order,
    first_plainly_out_of_order,
    plainly_sortable,
    require_integer,
)
from ._engine._require import argument, refuse, require_type, sized_len, verdict
from ._hints import Roles
from ._satisfies import _warn_vacuous
from .contains import _one_not_found, _pair_why
from .errors import _capped, _capped_format
from .matchers import _is_matcher

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sized

    from ._engine._compat import Self
    from ._engine._introspection import MappingLike
    from .matchers import Matcher

__tracebackhide__ = True


class CollectionMixin(_MixinBase):
    """Collection assertions mixin."""

    def _as_list(self) -> list[Any]:
        """Returns val as a list, raising TypeError if val is not iterable."""
        require_type(self.val, collections.abc.Iterable, "iterable")
        return list(self._walked())

    def is_iterable(self) -> Self:
        """Asserts that val is iterable.

        Examples:
            Usage:

                assert_that('foo').is_iterable()
                assert_that(['a', 'b']).is_iterable()
                assert_that((1, 2, 3)).is_iterable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** iterable
        """
        if not isinstance(self.val, collections.abc.Iterable):
            return self.error("Expected iterable, but was not.")
        return self

    def is_not_iterable(self) -> Self:
        """Asserts that val is not iterable.

        Examples:
            Usage:

                assert_that(1).is_not_iterable()
                assert_that(123.4).is_not_iterable()
                assert_that(True).is_not_iterable()
                assert_that(None).is_not_iterable()

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val **is** iterable
        """
        if isinstance(self.val, collections.abc.Iterable):
            return self.error("Expected not iterable, but was.")
        return self

    def is_subset_of(self, *supersets: object, allow_empty: bool = False) -> Self:
        """Asserts that val is iterable and a subset of the given superset (or supersets).

        Args:
            *supersets (object): the expected superset (or supersets)

        Examples:
            Usage:

                assert_that('foo').is_subset_of('abcdefghijklmnopqrstuvwxyz')
                assert_that(['a', 'b']).is_subset_of(['a', 'b', 'c'])
                assert_that((1, 2, 3)).is_subset_of([1, 2, 3, 4])
                assert_that({'a': 1, 'b': 2}).is_subset_of({'a': 1, 'b': 2, 'c': 3})
                assert_that({'a', 'b'}).is_subset_of({'a', 'b', 'c'})

                # or multiple supersets (as comma-separated args)
                assert_that('aBc').is_subset_of('abc', 'ABC')
                assert_that((1, 2, 3)).is_subset_of([1, 3, 5], [2, 4, 6])

                assert_that({'a': 1, 'b': 2}).is_subset_of({'a': 1, 'c': 3})  # fails
                # Expected <{'a': 1, 'b': 2}> to be subset of <{'a': 1, 'c': 3}>, but <{'b': 2}> was missing.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** subset of given superset (or supersets)

        Note:
            Where one element of val is not found, the failure says what is nearest to it: the closest row among
            the items of the superset, and on a line under the message why it is not there, where one fact about
            it says so.
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        if len(supersets) == 0:
            raise ValueError("one or more superset args must be given")

        missing = []
        if is_mapping_like(self.val):
            # read whole first: a superset sharing this iterator leaves nothing, and a subset of nothing is anything
            entries = [(key, self.val[key]) for key in self.val]
            # each read once and kept apart: merging printed a value under a key no superset held it under
            subject = dict(entries)
            read = []
            for superset_index, superset in enumerate(supersets):
                self._require_dict_like(superset, check_values=False, name=f"arg #{superset_index + 1}")
                mapping = cast("MappingLike", superset)
                # a one-shot subject given as its own superset has nothing left to read, and is its own subset
                read.append(subject if superset is self.val else {key: mapping[key] for key in mapping})
            missing.extend(subset_faults(subject, read))
            searched_in = read[0] if len(read) == 1 else read
            if missing:
                return self.error(
                    f"Expected <{_capped(self.val)}> to be subset of <{_capped_format(searched_in)}>, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing."
                    + _pair_why(missing, read),
                    expected=searched_in,
                )
            if not entries:
                _warn_vacuous(self, "is_subset_of", allow_empty)
        else:
            walked = list(self._walked())
            # flattened once: a one-shot superset is drained by the first pass and reads empty to a second
            collected = flattened_supersets(supersets)
            # the same core the matcher uses: a bare `set()` called a value whose hash disagrees with `==` missing
            missing.extend(subset_faults(walked, (collected,)))
            try:
                # for the message only: the failure has always shown the superset as a set where that was possible
                superset_values: object = set(collected)
            except TypeError:
                superset_values = collected
            if missing:
                roles = Roles("the item missing", "an item of the superset")
                return self.error(
                    f"Expected <{_capped(self.val)}> to be subset of {self._fmt_items(superset_values)}, "
                    f"but {self._fmt_items(missing)} {'was' if len(missing) == 1 else 'were'} missing."
                    + _one_not_found(missing, collected, noun="item", item_is_actual=True, roles=roles),
                    expected=superset_values,
                )
            if not walked:
                _warn_vacuous(self, "is_subset_of", allow_empty)

        return self

    def is_sorted(
        self,
        key: Callable[[Any], Any] = lambda item: item,
        reverse: bool = False,
        *,
        allow_empty: bool = False,
    ) -> Self:
        """Asserts that val is iterable and is sorted.

        Args:
            key (function): the one-arg function to extract the sort comparison key.  Defaults to
                ``lambda x: x`` to just compare items directly.
            reverse (bool): if ``True``, then comparison key is reversed.  Defaults to ``False``.

        Examples:
            Usage:

                assert_that(['a', 'b', 'c']).is_sorted()
                assert_that((1, 2, 3)).is_sorted()

                # with a key function
                assert_that('aBc').is_sorted(key=str.lower)

                # reverse order
                assert_that(['c', 'b', 'a']).is_sorted(reverse=True)
                assert_that((3, 2, 1)).is_sorted(reverse=True)

                assert_that((1, 2, 3, 4, -5, 6)).is_sorted()  # fails
                # Expected <(1, 2, 3, 4, -5, 6)> to be sorted, but subset <4, -5> at index 3 is not.

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val is **not** sorted
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        if not callable(key):
            refuse(key, "callable", subject=argument("key"))

        walked = 0

        def _counted(items):
            nonlocal walked
            for item in items:
                walked += 1
                yield item

        broken = None
        try:
            if key is _UNKEYED and plainly_sortable(self.val):
                walked = len(self.val)
                broken = first_plainly_out_of_order(self.val, reverse=reverse)
            else:
                broken = first_out_of_order(_counted(self._walked()), key=key, reverse=reverse)
        except UnorderableError:
            # reported about the collection: Python's own message is about the operator and names neither side
            unorderable = True
        else:
            unorderable = False
        if unorderable:
            refuse(self.val, "a collection whose items can be ordered against each other")
        if broken is not None:
            index, earlier, later = broken
            direction = " reverse" if reverse else ""
            return self.error(
                f"Expected <{_capped(self.val)}> to be sorted{direction}, "
                f"but subset {self._fmt_items([earlier, later])} at index {index} is not."
            )
        if not walked:
            _warn_vacuous(self, "is_sorted", allow_empty)
        return self

    def has_same_size_as(self, other: Sized) -> Self:
        """Asserts that val has the same length as other.

        Args:
            other (object): a sized object whose ``len()`` is compared with val's

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_same_size_as((4, 5, 6))
                assert_that('foo').has_same_size_as([1, 2, 3])

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val and other do **not** have the same length
            TypeError: if other is not a sized object
        """
        # the subject first: reading the operand first let the operand's own `__len__` answer for both
        actual_len = sized_len(self.val)
        # `other` was left to `len()`, whose message is about the builtin and names neither operand
        other_len = sized_len(other, subject=argument("other"))
        if actual_len != other_len:
            return self.error(
                f"Expected <{_capped(self.val)}> to have same size as <{_capped_format(other)}>"
                f" of length <{other_len}>, but was length <{actual_len}>.",
                expected=other_len,
            )
        return self

    def has_size_greater_than(self, size: SupportsIndex) -> Self:
        """Asserts that val has a length strictly greater than the given size.

        Args:
            size: the size val's length must exceed

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_greater_than(2)
                assert_that('foo').has_size_greater_than(1)
                assert_that({'a': 1, 'b': 2}).has_size_greater_than(1)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** greater than the given size
            TypeError: if the given arg is not an int
            ValueError: if the given arg is negative
        """
        bound = size if type(size) is int else require_integer(size, "size")
        if bound < 0:
            raise ValueError("given arg must be a positive int")
        actual = sized_len(self.val)
        if actual <= bound:
            return self.error(
                f"Expected <{_capped(self.val)}> to have size greater than <{size}>, but was <{actual}>.",
                expected=size,
            )
        return self

    def has_size_less_than(self, size: SupportsIndex) -> Self:
        """Asserts that val has a length strictly less than the given size.

        Args:
            size: the size val's length must stay under

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_less_than(4)
                assert_that('foo').has_size_less_than(5)
                assert_that({'a': 1, 'b': 2}).has_size_less_than(3)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** less than the given size
            TypeError: if the given arg is not an int
            ValueError: if the given arg is negative
        """
        bound = size if type(size) is int else require_integer(size, "size")
        if bound < 0:
            raise ValueError("given arg must be a positive int")
        actual = sized_len(self.val)
        if actual >= bound:
            return self.error(
                f"Expected <{_capped(self.val)}> to have size less than <{size}>, but was <{actual}>.", expected=size
            )
        return self

    def has_size_between(self, low: SupportsIndex, high: SupportsIndex) -> Self:
        """Asserts that val has a length between low and high (both inclusive).

        Args:
            low: the inclusive lower size bound
            high: the inclusive upper size bound

        Examples:
            Usage:

                assert_that([1, 2, 3]).has_size_between(1, 5)
                assert_that('foo').has_size_between(3, 3)
                assert_that({'a': 1, 'b': 2}).has_size_between(0, 2)

        Returns:
            AssertionBuilder: returns this instance to chain to the next assertion

        Raises:
            AssertionError: if val's length is **not** between low and high
            TypeError: if a given arg is not an int
            ValueError: if a given arg is negative, or low is greater than high
        """
        least = low if type(low) is int else require_integer(low, "low")
        most = high if type(high) is int else require_integer(high, "high")
        if least < 0 or most < 0:
            raise ValueError("given args must be positive ints")
        if least > most:
            raise ValueError("given low arg must be less than given high arg")
        if not least <= sized_len(self.val) <= most:
            return self.error(
                f"Expected <{_capped(self.val)}> to have size between <{low}> "
                f"and <{high}>, but was <{sized_len(self.val)}>.",
                expected=(low, high),
            )
        return self

    def filtered_on(self, predicate: Matcher[Any] | Callable[[Any], bool]) -> Self:
        """Returns a new builder with elements matching the predicate.

        Args:
            predicate: callable or Matcher. If a Matcher, uses ``predicate.matches(item)``.

        Examples:
            Usage:

                assert_that([1, -2, 3]).filtered_on(lambda x: x > 0).is_length(2)
                assert_that(items).filtered_on(match.is_positive()).is_not_empty()

        Returns:
            AssertionBuilder: returns a new instance with the filtered list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        # the protocol test the other matcher-taking methods use: a duck-typed matcher was called as a function
        matches = predicate.matches if _is_matcher(predicate) else cast("Callable[..., object]", predicate)
        # counted in the pass: a generator is spent by it, and asking after made an emptied source read as empty
        seen = 0
        filtered = []
        for item in self._walked():
            seen += 1
            if verdict(matches(item)):
                filtered.append(item)
        return self.builder(
            filtered,
            self.description,
            self.kind,
            logger=self.logger,
            origin=f"filtered_on() kept {len(filtered)} of {seen} items",
        )

    def mapped(self, func: Callable[[Any], Any]) -> Self:
        """Returns a new builder with each element transformed by func.

        Args:
            func: callable applied to each element.

        Examples:
            Usage:

                assert_that(["a", "b"]).mapped(str.upper).contains("A")

        Returns:
            AssertionBuilder: returns a new instance with the mapped list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        mapped = [func(item) for item in self._walked()]
        return self.builder(mapped, self.description, self.kind, logger=self.logger)

    def flat_mapped(self, func: Callable[[Any], Iterable[Any]]) -> Self:
        """Returns a new builder with each element expanded and flattened by func.

        Args:
            func: callable returning an iterable for each element.

        Examples:
            Usage:

                assert_that(["ab", "cd"]).flat_mapped(list).contains("a", "c")

        Returns:
            AssertionBuilder: returns a new instance with the flattened list as val
        """
        require_type(self.val, collections.abc.Iterable, "iterable")
        walked, flat = self._walked(), []
        for item in walked:
            made = func(item)
            # the value itself handed back is read as every link reads it: taken from under them, it left the
            # next link the first item alone
            flat.extend(walked if made is self.val else made)
        return self.builder(flat, self.description, self.kind, logger=self.logger)

    def first(self) -> Self:
        """Returns a new builder with the first element of val.

        Examples:
            Usage:

                assert_that([10, 20, 30]).first().is_equal_to(10)

        Returns:
            AssertionBuilder: returns a new instance with the first element as val

        Raises:
            ValueError: if val is empty
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[0], self.description, self.kind, logger=self.logger)

    def last(self) -> Self:
        """Returns a new builder with the last element of val.

        Examples:
            Usage:

                assert_that([10, 20, 30]).last().is_equal_to(30)

        Returns:
            AssertionBuilder: returns a new instance with the last element as val

        Raises:
            ValueError: if val is empty
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected non-empty iterable, but was empty.")
        return self.builder(items[-1], self.description, self.kind, logger=self.logger)

    def element(self, index: SupportsIndex) -> Self:
        """Returns a new builder with the element at the given index.

        Args:
            index: zero-based index.

        Examples:
            Usage:

                assert_that([10, 20, 30]).element(1).is_equal_to(20)

        Returns:
            AssertionBuilder: returns a new instance with the selected element as val

        Raises:
            IndexError: if index is out of range
        """
        position = index if type(index) is int else require_integer(index, "index")
        items = self._as_list()
        if position < 0 or position >= len(items):
            raise IndexError(f"Expected index {index} to be in range [0, {len(items)}), but was out of range.")
        return self.builder(items[position], self.description, self.kind, logger=self.logger)

    def single(self) -> Self:
        """Returns a new builder with the only element of val.

        Examples:
            Usage:

                assert_that([42]).single().is_equal_to(42)

        Returns:
            AssertionBuilder: returns a new instance with the single element as val

        Raises:
            ValueError: if val is empty or has more than one element
        """
        items = self._as_list()
        if not items:
            raise ValueError("Expected iterable with single element, but was empty.")
        if len(items) > 1:
            raise ValueError(f"Expected iterable with single element, but had {len(items)} elements.")
        return self.builder(items[0], self.description, self.kind, logger=self.logger)


_UNKEYED = inspect.signature(CollectionMixin.is_sorted).parameters["key"].default
"""`is_sorted` without a `key`, which asks nothing of anybody's code and so may compare plain items in C."""
