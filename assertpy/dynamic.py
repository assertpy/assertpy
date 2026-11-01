from __future__ import annotations

import collections.abc
import inspect
from typing import Any, cast

from ._engine._diff import _build_equality_diff, _pair_itself
from ._engine._equality import mapping_shaped
from ._engine._introspection import is_namedtuple
from ._engine._mixin_base import _MixinBase
from ._engine._path import _ROOT
from ._hints import Roles, not_found
from .errors import DiffResult, _first_difference, _formatted, _parted, _told_apart, _truncated
from .helpers import _both_list_like, _elided_seq_repr, _elided_walks
from .http_mixin import response_of
from .outcome import MISSING, Requirement

__tracebackhide__ = True


_ONE_OPERAND = inspect.Signature([inspect.Parameter("other", inspect.Parameter.POSITIONAL_OR_KEYWORD)])


def _one_operand(args: tuple[object, ...], kwargs: dict[str, object]) -> dict[str, object]:
    """The operand by name, or the call as given when the arity is what the wrapper is about to refuse."""
    try:
        return dict(_ONE_OPERAND.bind_partial(*args, **kwargs).arguments)
    except TypeError:
        return {"args": args, "kwargs": kwargs}


def _near(name: str, value: object, *, keyed: bool) -> str:
    """A line, on a line of its own, on a key or an attribute of *value* that reads almost as *name*, or nothing.

    The keys are read by walking the value once, as `contains_key` walks it.  The attributes are the public
    names its ``__dir__`` lists that the object does hold, looked up without calling a property: a ``__dir__``
    of the value's own may list what is not there.  Asked of the type and not through `dir`, which sorts what
    it is given, and sorting compares names that may be no plain text.
    """
    try:
        if keyed:
            names = cast("collections.abc.Iterable[object]", value)
            line = not_found(name, names, Roles("the key not found", "a key", named=True))
        else:
            listed = type.__getattribute__(type(value), "__dir__")(value)
            public = [each for each in listed if type(each) is str and not each.startswith("_")]
            held = [each for each in public if inspect.getattr_static(value, each, MISSING) is not MISSING]
            line = not_found(name, held, Roles("the attribute not found", "an attribute", named=True))
    except Exception:  # a diagnostic must never outrank the failure it is describing
        return ""
    return "" if line is None else f"\n{line}"


def _read_again(builder: Any, actual: object, expected: object) -> tuple[tuple[str, str] | None, DiffResult]:
    """What `is_equal_to` reads of two values found unequal: their two collapsed texts, where they have any, and
    their diff.

    Two mappings, as the pair stands once ``==`` has answered, by the call `is_equal_to` fails with on two
    mappings (`_failure_views`): it renders each side and then builds the entries, three readings of the
    pair, and where the values refuse any of them the three are given up together, for no texts and the
    pair itself.  Two plain sequences are collapsed as `is_equal_to` collapses them, and there the texts
    and the diff are given up each on its own.  ``==`` of two lists stops at the first pair that differs,
    and every one of these readings goes on past it, to an element the verdict never asked.
    """
    if mapping_shaped(actual, check_values=False) and mapping_shaped(expected, check_values=False):
        try:
            kind, entries, actual_text, expected_text, _copies = builder._failure_views(
                actual, expected, None, None, None, *_elided_walks(None)
            )
        except Exception:  # a diagnostic must never outrank the failure it is describing
            return None, _pair_itself(actual, expected)
        diff = DiffResult(kind=kind, entries=entries or [_ROOT.leaf_entry(actual=actual, expected=expected)])
        return (actual_text, expected_text), diff
    texts = None
    if _both_list_like(actual, expected):
        try:
            texts = _truncated(_elided_seq_repr(actual, expected)), _truncated(_elided_seq_repr(expected, actual))
        except Exception:  # as above
            texts = None
    try:
        return texts, _build_equality_diff(actual, expected)
    except Exception:  # as above
        return texts, _pair_itself(actual, expected)


def _as_equality_fails(builder: Any, actual: object, expected: object) -> tuple[str, str, DiffResult]:
    """The two sides of a failed ``has_<name>()`` as its message prints them, and the diff it carries.

    Collapsed as `is_equal_to` collapses them where they are two mappings or two plain sequences
    (`_read_again`).  Any other pair as two texts cut around the place they part, which is also what those two
    fall back to where the collapsed texts read alike or could not be made.  So the message differs from the
    one `is_equal_to` prints exactly there: it keeps two texts that read alike.
    """
    collapsed, diff = _read_again(builder, actual, expected)
    if collapsed is not None and collapsed[0] != collapsed[1]:
        return *collapsed, diff
    actual_text, expected_text = _formatted(actual), _formatted(expected)
    parted = _parted(actual_text, expected_text, _first_difference(actual_text, expected_text))
    return *_told_apart(*parted, actual, expected), diff


class DynamicMixin(_MixinBase):
    """Dynamic assertions mixin.

    When testing attributes of an object (or the contents of a dict), the
    [`is_equal_to()`][assertpy.base.BaseMixin.is_equal_to] assertion can be a bit verbose:

        fred = Person('Fred', 'Smith')

        assert_that(fred.first_name).is_equal_to('Fred')
        assert_that(fred.name).is_equal_to('Fred Smith')
        assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')

    Instead, use dynamic assertions in the form of ``has_<name>()`` where ``<name>`` is the name of
    any attribute, property, or zero-argument method on the given object. Dynamic equality
    assertions test if actual is equal to expected using the ``==`` operator. Using dynamic
    assertions, we can rewrite the above example as:

        assert_that(fred).has_first_name('Fred')
        assert_that(fred).has_name('Fred Smith')
        assert_that(fred).has_say_hello('Hello, Fred!')

    Similarly, dynamic assertions also work on any *dict-like* object:

        fred = {
            'first_name': 'Fred',
            'last_name': 'Smith',
            'shoe_size': 12
        }

        assert_that(fred).has_first_name('Fred')
        assert_that(fred).has_last_name('Smith')
        assert_that(fred).has_shoe_size(12)

    A name the value does not have fails with ``not_`` as well: negation inverts the comparison, never
    whether there is a field to compare, so ``not_.has_frist_name('Joe')`` does not pass on a typo.
    """

    def __getattr__(self, attr: str) -> Any:
        """Asserts that val has attribute attr and that its value is equal to other via a dynamic
        assertion of the form ``has_<attr>()``.

        The return stays ``Any`` on purpose, and the reason is written down because the annotation looks
        like an oversight worth fixing.  Two unrelated things resolve through this hook: a ``has_``
        wrapper, which takes one argument and hands back the builder, and any name registered with
        `add_extension`, which takes and returns whatever it declares.  No single signature is true of
        both.  Pinning the argument list reported a correct zero-argument extension call as too few
        arguments, and pinning the return type reported a correct extension result as the wrong type
        where it was used.  Both were measured against mypy, pyright and ty.

        The narrower annotation also bought less than it looked like.  It could not catch an assertion
        chained onto a dynamic step, because that access resolves back through this same hook; the only
        thing it added was a verdict in assignment position, which is where it was wrong for extensions.
        """
        if not attr.startswith("has_"):
            raise AttributeError(f"assertpy has no assertion <{attr}()>")

        attr_name = attr[4:]
        err_msg: str | None = None
        val_is_namedtuple = is_namedtuple(self.val)
        # a django response reads its headers by key, yet `has_status_code()` means the attribute, as on every client
        is_dict = (
            isinstance(self.val, collections.abc.Iterable)
            and hasattr(self.val, "__getitem__")
            and response_of(self.val) is None
        )

        if is_dict and not val_is_namedtuple:
            # dict-likes are read by key below, so a real method absent as a key would skip this gate and raise KeyError
            if attr_name not in self.val:
                err_msg = f"Expected key <{attr_name}>, but val has no key <{attr_name}>."
        elif not hasattr(self.val, attr_name):
            err_msg = f"Expected attribute <{attr_name}>, but val has no attribute <{attr_name}>."

        def _wrapper(*args, **kwargs):
            # named here rather than read off the stack: the operation is the attribute, not this closure
            asked = Requirement(attr, _one_operand(args, kwargs))
            if err_msg:
                # ok to raise now that we are inside wrapper
                near = _near(attr_name, self.val, keyed=is_dict and not val_is_namedtuple)
                self._unmet(err_msg + near, expected=asked.parameters.get("other", MISSING), requirement=asked)
                return self
            else:
                try:
                    # bound rather than counted: the signature says `other`, and writing it was refused
                    bound = _ONE_OPERAND.bind(*args, **kwargs)
                except TypeError:
                    given = len(args) + len(kwargs)
                    raise TypeError(f"assertion <{attr}()> takes exactly 1 argument ({given} given)") from None

                val_attr = self.val[attr_name] if is_dict and not val_is_namedtuple else getattr(self.val, attr_name)

                if callable(val_attr):
                    try:
                        inspect.signature(val_attr).bind()
                    except TypeError:  # the method needs arguments, so it is not a zero-arg method
                        raise TypeError(f"val does not have zero-arg method <{attr_name}()>") from None
                    except ValueError:  # some builtins expose no introspectable signature; just call it
                        pass
                    actual = val_attr()  # a TypeError from here comes from the method body, not arity
                else:
                    actual = val_attr

                expected = bound.arguments["other"]
                if actual == expected:
                    return self
                kind = "key" if is_dict else "attribute"
                actual_text, expected_text, diff = _as_equality_fails(self, actual, expected)
                self._compared = (actual, expected)
                return self.error(
                    f"Expected <{actual_text}> to be equal to <{expected_text}> on {kind} <{attr_name}>, but was not.",
                    actual=actual,
                    expected=expected,
                    diff=diff,
                    requirement=asked,
                )

        # the arity check above is the wrapper's own, so its signature says what a caller writes and
        # `Requirement.parameters` reads the same key whether the call was negated or not.  Through
        # `setattr` because typeshed declares no `__signature__` on a function, which both gates report
        setattr(_wrapper, "__signature__", _ONE_OPERAND)  # noqa: B010 - see above
        return _wrapper
