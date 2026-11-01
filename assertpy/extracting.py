from __future__ import annotations

import collections.abc
import difflib
import inspect
from typing import TYPE_CHECKING, cast

from ._engine._equality import mapping_shaped
from ._engine._introspection import is_model_dump_object, is_namedtuple
from ._engine._mixin_base import _MixinBase
from ._engine._require import argument, refuse, reject_unknown_kwargs, require_type, verdict

_EXTRACTING_OPTIONS = frozenset({"filter", "sort"})

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._engine._compat import Self
    from ._engine._introspection import MappingLike

__tracebackhide__ = True


_OURS = "_assertpy_extracting"


def _extraction_error(message: str) -> ValueError:
    """A ``ValueError`` tagged as this module's own.

    The localization wrapper re-raises only tagged errors, so a ``ValueError`` raised by user code (a
    property that fails, say) keeps its own traceback instead of being swallowed. The visible type
    stays ``ValueError``, exactly as before.
    """
    error = ValueError(message)
    setattr(error, _OURS, True)
    return error


class ExtractingMixin(_MixinBase):
    """Collection flattening mixin.

    It is often necessary to test collections of objects.  Use the ``extracting()`` helper to
    reduce the collection on a given attribute.  Reduce a list of objects:

        alice = Person('Alice', 'Alpha')
        bob = Person('Bob', 'Bravo')
        people = [alice, bob]

        assert_that(people).extracting('first_name').is_equal_to(['Alice', 'Bob'])
        assert_that(people).extracting('first_name').contains('Alice', 'Bob')
        assert_that(people).extracting('first_name').does_not_contain('Charlie')

    Additionally, the ``extracting()`` helper can accept a list of attributes to be extracted, and
    will flatten them into a list of tuples.  Reduce a list of objects on multiple attributes:

        assert_that(people).extracting('first_name', 'last_name').contains(('Alice', 'Alpha'), ('Bob', 'Bravo'))

    Also, ``extracting()`` works on not just attributes, but also properties, and even
    zero-argument methods.  Reduce a list of object on properties and zero-arg methods:

        assert_that(people).extracting('name').contains('Alice Alpha', 'Bob Bravo')
        assert_that(people).extracting('say_hello').contains('Hello, Alice!', 'Hello, Bob!')

    And ``extracting()`` even works on *dict-like* objects.  Reduce a list of dicts on key:

        alice = {'first_name': 'Alice', 'last_name': 'Alpha'}
        bob = {'first_name': 'Bob', 'last_name': 'Bravo'}
        people = [alice, bob]

        assert_that(people).extracting('first_name').contains('Alice', 'Bob')

    **Filtering**

    The ``extracting()`` helper can include a *filter* to keep only those items for which the given
    *filter* is truthy.  For example:

        users = [
            {'user': 'Alice', 'age': 36, 'active': True},
            {'user': 'Bob', 'age': 40, 'active': False},
            {'user': 'Charlie', 'age': 13, 'active': True}
        ]

        # filter the active users
        assert_that(users).extracting('user', filter='active').is_equal_to(['Alice', 'Charlie'])

    The *filter* can be a *dict-like* object and the extracted items are kept if and only if all
    corresponding key-value pairs are equal:

        assert_that(users).extracting('user', filter={'active': False}).is_equal_to(['Bob'])
        assert_that(users).extracting('user', filter={'age': 36, 'active': True}).is_equal_to(['Alice'])

    Or a *filter* can be any function (including an in-line ``lambda``) that accepts as its single
    argument each item in the collection, and the extracted items are kept if the function
    evaluates to ``True``:

        assert_that(users).extracting('user', filter=lambda x: x['age'] > 20)
            .is_equal_to(['Alice', 'Bob'])

    **Sorting**

    The ``extracting()`` helper can include a *sort* to enforce order on the extracted items.

    The *sort* can be the name of a key (or attribute, or property, or zero-argument method) and
    the extracted items are ordered by the corresponding values:

        assert_that(users).extracting('user', sort='age').is_equal_to(['Charlie', 'Alice', 'Bob'])

    The *sort* can be an iterable of names and the extracted items are ordered by
    corresponding value of the first name, ties are broken by the corresponding values of the
    second name, and so on:

        assert_that(users).extracting('user', sort=['active', 'age']).is_equal_to(['Bob', 'Charlie', 'Alice'])

    The *sort* can be any function (including an in-line ``lambda``) that accepts as its single
    argument each item in the collection, and the extracted items are ordered by the corresponding
    function return values:

        assert_that(users).extracting('user', sort=lambda x: -x['age']).is_equal_to(['Bob', 'Alice', 'Charlie'])
    """

    def extracting(self, *names: object, **kwargs: object) -> Self:
        """Asserts that val is iterable, then extracts the named attributes, properties, or
        zero-arg methods into a list (or list of tuples if multiple names are given).

        Args:
            *names: the attribute to be extracted (or property or zero-arg method)
            **kwargs (object): see below

        Keyword Args:
            filter (str | dict | Callable | None): extract only those items where filter is truthy
            sort (str | Iterable | Callable | None): order the extracted items by the sort key

        Examples:
            Usage:

                alice = User('Alice', 20, True)
                bob = User('Bob', 30, False)
                charlie = User('Charlie', 10, True)
                users = [alice, bob, charlie]

                assert_that(users).extracting('user').contains('Alice', 'Bob', 'Charlie')

            Works with *dict-like* objects too:

                users = [
                    {'user': 'Alice', 'age': 20, 'active': True},
                    {'user': 'Bob', 'age': 30, 'active': False},
                    {'user': 'Charlie', 'age': 10, 'active': True}
                ]

                assert_that(people).extracting('user').contains('Alice', 'Bob', 'Charlie')

            Filter:

                assert_that(users).extracting('user', filter='active').is_equal_to(['Alice', 'Charlie'])

            Sort:

                assert_that(users).extracting('user', sort='age').is_equal_to(['Charlie', 'Alice', 'Bob'])

        Returns:
            AssertionBuilder: returns a new instance (extracted list as val) to chain the next assertion
        """
        reject_unknown_kwargs(kwargs, _EXTRACTING_OPTIONS, "extracting")
        require_type(self.val, collections.abc.Iterable, "iterable")
        if isinstance(self.val, str):
            refuse(self.val, "a collection rather than a string")
        if len(names) == 0:
            raise ValueError("one or more name args must be given")

        def _attr_value(item, name):
            attr = getattr(item, name)
            if not callable(attr):
                return attr
            try:
                inspect.signature(attr).bind()
            except TypeError:  # the callable needs arguments, so it is not a zero-arg method
                raise _extraction_error(f"item method <{name}()> exists, but is not zero-arg method") from None
            except ValueError:  # some builtins expose no introspectable signature; fall back to calling
                pass
            return attr()  # a TypeError from here comes from the method body, not an arity mismatch

        def _extract(item, name):
            if mapping_shaped(item, check_values=False):
                if name in item:
                    return item[name]
                raise _extraction_error(f"item keys {list(item.keys())} did not contain key <{name}>")
            if is_namedtuple(item) and type(name) is str:
                if name in item._fields:
                    return getattr(item, name)
                if hasattr(item, name):  # a property or zero-arg method on the NamedTuple subclass
                    return _attr_value(item, name)
                raise _extraction_error(f"item attributes {item._fields} did not contain attribute <{name}>")
            if isinstance(item, collections.abc.Iterable) and not is_model_dump_object(item):
                self._check_iterable(item, name="item")
                return item[name]
            try:
                return _attr_value(item, name)
            except AttributeError as exc:
                # hasattr() reports a raising accessor as a missing one, and the two want different messages
                if hasattr(type(item), name):
                    raise _extraction_error(
                        f"item has property or zero-arg method <{name}>, but reading it raised AttributeError: {exc}"
                    ) from exc
                try:
                    available = sorted(attr for attr in dir(item) if not attr.startswith("_"))
                except Exception:  # a broken __dir__ must not replace the real diagnostic with its own
                    available = []
                # one suggestion: measured typos score ~0.9 while wrong neighbours sit at ~0.65
                close = difflib.get_close_matches(str(name), available, n=1)
                hint = f"; did you mean {close[0]!r}?" if close else ""
                raise _extraction_error(f"item does not have property or zero-arg method <{name}>{hint}") from None

        def _filter(item):
            if "filter" in kwargs:
                chosen = kwargs["filter"]
                if isinstance(chosen, str):
                    return bool(_extract(item, chosen))
                elif mapping_shaped(chosen, check_values=False):
                    mapping = cast("MappingLike", chosen)
                    return all(_extract(item, key) == mapping[key] for key in mapping if isinstance(key, str))
                elif callable(chosen):
                    return cast("Callable[[object], object]", chosen)(item)
                elif chosen is None:
                    return True
                refuse(chosen, "a str, a dict, or a callable", subject=argument("filter"))
            return True

        def _sort(item):
            # an explicit `sort=None` means no ordering, and 0 is a stable no-op for it
            sort = kwargs["sort"]
            if isinstance(sort, str):
                return _extract(item, sort)
            if isinstance(sort, collections.abc.Iterable):
                return tuple(_extract(item, key) for key in sort if isinstance(key, str))
            if callable(sort):
                return cast("Callable[[object], object]", sort)(item)
            if sort is None:
                return 0
            # silently returning unsorted items would surface as a confusing order mismatch further down the chain
            refuse(sort, "a str, an iterable, or a callable", subject=argument("sort"))

        # only pay the sort when one was requested, so the extractor sees the source at the same point
        source = sorted(self._walked(), key=_sort) if "sort" in kwargs else self._walked()
        extracted = []
        # counted here: the walk spends a generator, and asking a spent one said an emptied source had been empty
        seen = 0
        for index, item in enumerate(source):
            seen += 1
            if verdict(_filter(item), subject="the filter"):
                try:
                    extracted_values = [_extract(item, name) for name in names]
                except ValueError as exc:
                    if not getattr(exc, _OURS, False):
                        raise
                    localized = f"{exc} (at index {index}, item is <{type(item).__name__}>)"
                    raise _extraction_error(localized) from exc.__cause__
                extracted.append(tuple(extracted_values) if len(extracted_values) > 1 else extracted_values[0])

        return self.builder(
            extracted,
            self.description,
            self.kind,
            logger=self.logger,
            origin=f"extracting() produced {len(extracted)} of {seen} items",
        )
