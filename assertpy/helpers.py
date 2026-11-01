import collections
import collections.abc
import datetime
import decimal
import numbers
from typing import Any, Final, cast

from assertpy.errors import (
    DiffResult,
    _capped,
    _capped_format,
    _capped_repr,
    _ends_kept,
    _safe_repr,
    _truncated,
    _windowed,
)

from ._engine._compare import (
    _CompareConfig,
    _config_note,
    _is_nan,
    _node_decision,
    _spec_matches,
    _walked_equal,
    require_rel,
    zero_of,
)
from ._engine._diff import _aligned_match_indices, _graphs_differ, _sub_diff_entries, readable, run_nested
from ._engine._equality import (
    IncludeKeysMissingError,
    as_fields,
    carries_callable,
    comparable_fields,
    fields_pair,
    ignore_specs,
    include_specs,
    key_specs_given,
    mapping_differs,
    mapping_shaped,
    normalize_key_specs,
    supports_subscript,
)
from ._engine._introspection import (
    MappingLike,
    TakenApart,
    class_name,
    is_namedtuple,
    keyed_names,
    keyed_pair,
    keyed_snapshot,
)
from ._engine._mixin_base import _MixinBase
from ._engine._ordering import (
    UnorderableError,
    holds,
    lookup,
    nan_operand,
    numpy_duration,
    python_numbers,
    rational_overflow,
)
from ._engine._path import _ROOT
from ._engine._require import _shown, argument, raised_inside, refuse, require_type

__tracebackhide__ = True


def _both_list_like(left: object, right: object) -> bool:
    """Whether both values are plain sequences, so they compare element-by-element.

    Namedtuples are excluded on purpose: they carry field names and are compared field-wise.
    """
    return (
        isinstance(left, (list, tuple))
        and isinstance(right, (list, tuple))
        and not is_namedtuple(left)
        and not is_namedtuple(right)
    )


class _Elided:
    """Marker standing in a parts list for a run of elements equal to their counterpart.

    Handed to the join in its place among the parts rather than as one flag for the whole value, because
    such a flag can only put the ``..`` in front: a value differing from its counterpart by one extra
    leading element then printed as ``[.., 0]``, which is the shape of a changed *tail*.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return ".."


_ELIDED = _Elided()
_Part = str | _Elided


def _joined_parts(parts: list[_Part], *, opener: str = "", closer: str = "") -> str:
    """Assemble a collapsed repr, capping how many differing parts are spelled out.

    Collapsing only removes what matched, so a value where nearly everything differs still prints in
    full. The cap is what keeps that case from becoming a wall of text on one line.  `_ELIDED` entries
    mark where the matched runs were and never count against the cap.  Past the cap the count stands
    for everything that follows, so no marker is kept after it and none is left just before it.
    """
    kept: list[_Part] = []
    spelled = hidden = 0
    for part in parts:
        if part is _ELIDED:
            if not hidden:
                kept.append(part)
            continue
        spelled += 1
        if spelled > 5:
            hidden += 1
        else:
            kept.append(part)
    if hidden:
        if kept[-1] is _ELIDED:
            kept.pop()
        kept.append(f"... and {hidden} more")
    return f"{opener}{', '.join(str(part) for part in kept)}{closer}"


def _elided_text_repr(text: str, counterpart: str) -> str:
    """Collapse lines equal to their counterpart into ``..`` so only the changed ones are printed.

    Mirrors `_elided_seq_repr` for multi-line values: a one-line change in a long block should not put
    the whole block into the message twice.
    """
    # the cost of a multi-line value is vertical, and the message prints it twice, so this counts rows
    if len(text.splitlines()) <= 3:
        # a long line has no rows to collapse, and capping from the start printed 96% of a five-kilobyte
        # string with none of it near the change
        return _windowed(text, counterpart, width=320)[0] if len(text) > 320 else text
    other_lines = counterpart.splitlines()
    parts: list[_Part] = []
    pending = False
    for index, line in enumerate(text.splitlines()):
        if index < len(other_lines) and line == other_lines[index]:
            pending = True
            continue
        if pending:
            parts.append(_ELIDED)
            pending = False
        parts.append(f"line {index + 1}: {line}")
    if pending:
        parts.append(_ELIDED)
    return _joined_parts(parts)


def _elided_seq_repr(seq, counterpart) -> str:
    """Collapse elements equal to their counterpart into ``..`` so only the differing ones are printed.

    A one-element change in a forty-element list reads as ``[.., 999, ..]`` instead of dumping the list
    twice into a message the reader then has to diff by eye.

    Matched elements are found by the alignment the diff uses
    (`assertpy._engine._diff._aligned_match_indices()`), so a shifted sequence collapses in the message
    the same way it collapses in the diff.  Position is the fallback, for the pairs no alignment
    improves on.
    """
    items, others = readable(seq), readable(counterpart)
    # past 20 elements the rendering is over budget, so the value is never rendered just to be measured
    if len(items) <= 20:
        rendered = _safe_repr(seq)
        if len(rendered) <= 60:
            # on a two-element list the ".." form is the longer of the two
            return rendered
    aligned = _aligned_match_indices(items, others)
    parts: list[_Part] = []
    pending = False
    for index, value in enumerate(items):
        if aligned is not None:
            matched = index in aligned
        else:
            matched = index < len(others) and (
                (equal := _walked_equal(value, others[index]))
                or (equal is None and not _graphs_differ(value, others[index]))
            )
        if matched:
            pending = True
            continue
        if pending:
            parts.append(_ELIDED)
            pending = False
        parts.append(_safe_repr(value))
    if pending:
        parts.append(_ELIDED)
    if isinstance(seq, tuple):
        # a tuple of one takes its comma, or the text reads as that one element in brackets
        return _joined_parts(parts, opener="(", closer=",)" if len(items) == 1 else ")")
    return _joined_parts(parts, opener="[", closer="]")


def _spelling(mapping: object) -> tuple[str, str, collections.abc.Callable[[object, str], str]]:
    """How a mapping is written in a message: what opens it, what closes it, and one part of it.

    A dict is written as a dict.  A value taken apart is written as the class it was read from, as its own
    repr writes it: ``Row(name='a')`` for a record, ``Kept({'x': 1})`` for a mapping of a class of its own.
    """
    if type(mapping) is not TakenApart:
        return "{", "}", _entry_part
    name = class_name(mapping.kind)
    return (f"{name}({{", "})", _entry_part) if mapping.keyed else (f"{name}(", ")", _field_part)


def _entry_part(key: object, text: str) -> str:
    return f"{_capped_repr(key)}: {text}"


def _field_part(key: object, text: str) -> str:
    return f"{_capped(key)}={text}"


def _read_by_fields(value: object) -> object:
    """*value* as the mapping a key path reads it through, a snapshot of its keys or its fields, or ``None``."""
    return keyed_snapshot(value) if mapping_shaped(value, check_values=False) else comparable_fields(value)


def _keyed_pair(value: object, other: object) -> tuple[MappingLike, MappingLike] | None:
    """Both sides as something safe to walk by key, or `None` when either cannot be walked that way.

    Asked at every descent a message walks, not once at the top: a value that answers `keys` and cannot
    be indexed by what it yields can sit nested inside a pair whose outer halves are ordinary dicts.
    """
    if not (mapping_shaped(value, check_values=False) and mapping_shaped(other, check_values=False)):
        return None
    kept, kept_other = keyed_snapshot(value), keyed_snapshot(other)
    return None if kept is None or kept_other is None else (kept, kept_other)


def _informative(val: object, other: object, val_repr: str, other_repr: str, *, whole: bool) -> tuple[str, str]:
    """The two shape-aware renderings, or plain reprs when the walk rendered both sides the same.

    A value answering `keys()` and iterating empty, which is what a `MagicMock` does, made an unequal
    pair read `<{}>` against `<{}>`, and at the top level the diff was empty too, so the failure said
    nothing at all.  The shape guess is given up there the way `_dict_err` already gives it up for a
    value it cannot walk by key.

    Only when the halves rendered were the *whole* values.  Under `ignore`, `include` or a compare
    config they are a projection, and printing the originals put an ignored key back into the message:
    two values differing in a leaf whose repr is the same on both sides render alike, and the fallback
    then printed the key the caller had asked to keep out of the log.

    Compared before truncating and truncated after, since two values agreeing for the first 4000
    characters collide once cut, and the untruncated fallback then printed both in full.
    """
    if whole and val_repr == other_repr:
        return _truncated(_safe_repr(val)), _truncated(_safe_repr(other))
    return _truncated(val_repr), _truncated(other_repr)


def _zero_for(val, other, tolerance):
    """The zero *tolerance* is signed against, once *other* and it are numbers of *val*'s measure.

    A bool is refused, and so is a `numpy` duration measured against a number, either way round, since `numpy`
    registers one as an integer.  Asked of three plain numbers too, the duration check cost `is_close_to` 20%.
    """
    if isinstance(other, bool):
        refuse(other, "a number other than a bool", subject=argument("other"))
    require_type(other, numbers.Number, "a number", subject=argument("other"))
    if isinstance(tolerance, bool):
        refuse(tolerance, "a number other than a bool", subject=argument("tolerance"))
    require_type(tolerance, numbers.Number, "a number", subject=argument("tolerance"))
    duration = numpy_duration(val)
    for operand, name in ((other, "other"), (tolerance, "tolerance")):
        if numpy_duration(operand) != duration:
            kind = "a numpy timedelta64" if duration else "a number"
            refuse(operand, f"{kind}, to match val", subject=argument(name))
    return zero_of(tolerance)


def _swapped_as_ordered(low, high, refusal: Exception) -> bool:
    """Whether the bounds are the wrong way round as the ordering engine reads them, once ``>`` raised *refusal*.

    A `Decimal` NaN signals at ``>``, where the engine reads it as unordered.  Bounds with no ordering between
    them are refused here, under the name of the bound the engine stopped at: left to `_within`, a value below
    the low bound failed before the high one was ever asked.  A `TypeError` or an overflow raised inside a
    comparison of the value's own is a bug in the value and is handed on, unless `rational_overflow` names it,
    and so is a signal with no NaN among the bounds, which the operands decide as the engine does, since the
    traceback's depth differs between the C and the pure-Python `decimal`.  A signal is a verdict only where the
    engine reads the pair as a NaN it can answer.
    """
    if isinstance(refusal, (TypeError, OverflowError)):
        handed_on = raised_inside(refusal) and not rational_overflow(refusal)
    else:
        handed_on = not (nan_operand(low) or nan_operand(high))
    if handed_on:
        raise refusal
    try:
        return holds(low, high, "gt")
    except UnorderableError as unordered:
        failure = unordered
    if isinstance(refusal, decimal.InvalidOperation):
        raise refusal
    if failure.kind == "value":
        refuse(low, "a number", subject=argument("low"))
    if failure.kind == "kind":
        refuse(high, "a number", subject=argument("high"))
    refuse(high, f"comparable with given low arg {_shown(low)}", subject=argument("high"))


_ElidedWalk = collections.abc.Callable[[Any, Any], collections.abc.Generator[Any, Any, str]]


def _elided_walks(config: _CompareConfig | None) -> tuple[_ElidedWalk, _ElidedWalk]:
    """The two walks that render a pair with what matched left out: one of two mappings, one of two sequences.

    Both are walks for `run_nested()`, which sends each nested rendering back.  Made as a pair, for one failure:
    the two share the containers on the path, which is where a value that holds itself stops.
    """
    on_path: set[int] = set()

    def _dict_repr(mapping, counterpart):
        opener, closer, part_of = _spelling(mapping)
        if id(mapping) in on_path:
            return f"{opener}<circular ref>{closer}"
        on_path.add(id(mapping))
        keyed_fields = keyed_names(mapping, counterpart)
        parts: list[_Part] = []
        pending = False
        # left in the mapping's order, which the diff prints: sorting here made the two halves disagree
        for key, value in ((key, mapping[key]) for key in mapping):
            found, other_value = lookup(counterpart, key)
            if not found:
                part = part_of(key, _safe_repr(value))
            else:
                decision = (
                    _node_decision(*keyed_pair(mapping, counterpart, key), config, field=key)
                    if key in keyed_fields
                    else _node_decision(value, other_value, config, field=key)
                )
                if decision == "equal":
                    pending = True
                    continue
                if decision == "leaf":
                    part = part_of(key, _safe_repr(value))
                else:  # recurse
                    if (keyed := _keyed_pair(value, other_value)) is not None:
                        value_repr = yield _dict_repr(*keyed)
                    elif _both_list_like(value, other_value):
                        value_repr = yield _list_repr(value, other_value)
                    else:
                        value_repr = _safe_repr(value)
                    part = part_of(key, value_repr)
            if pending:
                parts.append(_ELIDED)
                pending = False
            parts.append(part)
        if pending:
            parts.append(_ELIDED)
        on_path.discard(id(mapping))
        return _joined_parts(parts, opener=opener, closer=closer)

    def _list_repr(seq, counterpart):
        """List counterpart of ``_dict_repr``: collapse equal elements to ``..`` and drill only into
        the differing ones, so a one-element change in a long list reads as ``[.., {.., 'v': 'y'}, ..]``
        instead of dumping the whole list.  Both are walks for `run_nested()`, which sends back each nested
        repr."""
        if id(seq) in on_path:
            return "[<circular ref>]"
        on_path.add(id(seq))
        parts: list[_Part] = []
        pending = False
        for index, value in enumerate(seq):
            if index >= len(counterpart):
                part = _safe_repr(value)  # extra element beyond the counterpart's length
            else:
                other_value = counterpart[index]
                decision = _node_decision(value, other_value, config, field=None)
                if decision == "equal":
                    pending = True
                    continue
                if decision == "leaf":
                    part = _safe_repr(value)
                elif (keyed := _keyed_pair(value, other_value)) is not None:
                    part = yield _dict_repr(*keyed)
                elif _both_list_like(value, other_value):
                    part = yield _list_repr(value, other_value)
                else:
                    part = _safe_repr(value)
            if pending:
                parts.append(_ELIDED)
                pending = False
            parts.append(part)
        if pending:
            parts.append(_ELIDED)
        on_path.discard(id(seq))
        # keep tuples looking like tuples, a tuple of one with its comma
        opener, closer = ("(", ",)" if len(seq) == 1 else ")") if isinstance(seq, tuple) else ("[", "]")
        return _joined_parts(parts, opener=opener, closer=closer)

    return _dict_repr, _list_repr


# built once: a passing `is_close_to` on datetimes paid 76 ns for the check with it built each time, 29 ns kept
_NO_SPAN: Final = datetime.timedelta()


def _validate_moments_close(other, tolerance, rel) -> None:
    """The arguments of a closeness of two datetimes: a datetime and a timedelta, and no `rel`."""
    require_type(other, datetime.datetime, "a datetime, to match val", subject=argument("other"))
    if rel is not None:
        refuse(rel, "None for a datetime, which has no size to take a fraction of", subject=argument("rel"))
    span = require_type(tolerance, datetime.timedelta, "a timedelta, to match val", subject=argument("tolerance"))
    if datetime.timedelta.__lt__(span, _NO_SPAN):
        raise ValueError("given tolerance arg must not be negative")


def _validate_numbers_close(val, other, tolerance, rel) -> None:
    """The arguments of a closeness of two numbers: a tolerance, a `rel` or both, neither negative nor NaN."""
    if tolerance is None and rel is None:
        refuse(tolerance, "a number, or a rel given instead", subject=argument("tolerance"))
    if rel is not None:
        require_rel(rel)
        if numpy_duration(val):
            refuse(rel, "None for a numpy duration, which has no size to take a fraction of", subject=argument("rel"))
    if tolerance is not None:
        plain = type(val) in (int, float) and type(other) in (int, float) and type(tolerance) in (int, float)
        zero = 0 if plain else _zero_for(val, other, tolerance)
        if _is_nan(tolerance):
            raise ValueError("given tolerance arg must not be NaN")
        if tolerance < zero:
            raise ValueError("given tolerance arg must not be negative")


class HelpersMixin(_MixinBase):
    """Helpers mixin.  For internal use only."""

    def _fmt_items(self, items):
        """Helper to format the given items."""
        if len(items) == 0:
            return "<>"
        elif len(items) == 1 and hasattr(items, "__getitem__"):
            return f"<{_capped_format(items[0])}>"
        elif type(items) is tuple or type(items) is list:
            try:
                return f"<{_ends_kept(str.__str__(str(items))[1:-1])}>"
            except Exception:
                # one element at a time, so one bad `__repr__` spoils only itself
                return f"<{_ends_kept(', '.join(map(_safe_repr, items)))}>"
        return f"<{_capped(items)}>"

    def _fmt_args_kwargs(self, *some_args, **some_kwargs):
        """Helper to convert the given args and kwargs into a string."""
        out_args = out_kwargs = ""
        if some_args:
            out_args = str(some_args).lstrip("(").rstrip(",)")
        if some_kwargs:
            out_kwargs = ", ".join(
                [
                    str(pair).lstrip("(").rstrip(")").replace(", ", ": ")
                    for pair in [(key, some_kwargs[key]) for key in sorted(some_kwargs.keys())]
                ]
            )

        if some_args and some_kwargs:
            return out_args + ", " + out_kwargs
        elif some_args:
            return out_args
        elif some_kwargs:
            return out_kwargs
        else:
            return ""

    def _validate_between_args(self, val_type, low, high):
        """Helper to validate given range args."""
        low_type = type(low)
        high_type = type(high)

        if val_type in self._NUMERIC_NON_COMPAREABLE:
            refuse(self.val, "a value with an ordering (complex numbers have none)")

        if val_type in self._NUMERIC_COMPAREABLE:
            if low_type is not val_type:
                refuse(low, f"a {val_type.__name__}, to match val", subject=argument("low"))
            if high_type is not val_type:
                refuse(high, f"a {val_type.__name__}, to match val", subject=argument("high"))
        elif isinstance(self.val, numbers.Number):
            require_type(low, numbers.Number, "a number", subject=argument("low"))
            require_type(high, numbers.Number, "a number", subject=argument("high"))
        else:
            refuse(self.val, "a number or a date, which is what an ordering is defined for")

        if low_type is not high_type:
            low, high = python_numbers(low, high)
        try:
            swapped = low > high
        except (TypeError, OverflowError, decimal.InvalidOperation) as refusal:
            swapped = _swapped_as_ordered(low, high, refusal)
        if swapped:
            raise ValueError("given low arg must be less than given high arg")

    def _validate_close_to_args(self, val, other, tolerance, rel=None):
        """Helper for validate given arg and delta."""
        for operand in (val, other, tolerance):
            if type(operand) is complex:
                refuse(operand, "a value with an ordering (complex numbers have none)")

        if isinstance(val, bool):
            refuse(val, "a number other than a bool, or a datetime")
        if not isinstance(val, (numbers.Number, datetime.datetime)):
            refuse(val, "a number or a datetime")

        if isinstance(val, datetime.datetime):
            _validate_moments_close(other, tolerance, rel)
        else:
            _validate_numbers_close(val, other, tolerance, rel)

    def _is_dict_like(self, candidate, check_keys=True, check_values=True, check_getitem=True):
        """Return whether *candidate* has the requested dict-like attributes."""
        return mapping_shaped(candidate, check_keys=check_keys, check_values=check_values, check_getitem=check_getitem)

    def _require_dict_like(self, candidate, check_keys=True, check_values=True, check_getitem=True, name="val"):
        """Raise ``TypeError`` unless *candidate* has the requested dict-like attributes.

        The same reading as `mapping_shaped`, one check at a time so each refusal can name what is
        missing.  Reading it any other way here would accept a value the renderer then crashes on.
        """
        if not isinstance(candidate, collections.abc.Iterable):
            refuse(candidate, "dict-like (this one is not iterable)", subject=name)
        if check_keys and not carries_callable(candidate, "keys"):
            refuse(candidate, "dict-like (this one has no keys())", subject=name)
        if check_values and not carries_callable(candidate, "values"):
            refuse(candidate, "dict-like (this one has no values())", subject=name)
        if check_getitem and not supports_subscript(candidate):
            refuse(candidate, "dict-like (this one has no [] accessor)", subject=name)

    def _check_iterable(self, val, check_getitem=True, name="val"):
        """Helper to check if given val is iterable with optional item access."""
        if not isinstance(val, collections.abc.Iterable):
            refuse(val, "iterable", subject=name)
        if check_getitem and not supports_subscript(val):
            refuse(val, "a value with a [] accessor", subject=name)

    def _dict_not_equal(self, val, other, ignore=None, include=None, config: _CompareConfig | None = None):
        """Whether two dict-like values differ, under optional ignore/include specs and a compare config.

        The decision lives in `_engine._equality`, where a matcher reaches it too.  What stays here is
        the one part that is not a comparison: an `include` naming a key the mapping does not have is a
        mistake in the call, and it is reported as a failure in the builder's own wording.  Reported as
        a prerequisite, since a comparison of keys that are not there has no answer to invert, and
        ``not_.is_equal_to(other, include="typo")`` passed on it.

        Returns ``None`` once that is reported rather than a verdict.
        """
        try:
            return mapping_differs(val, other, ignore=ignore, include=include, config=config)
        except IncludeKeysMissingError as found:
            absent = found
        # reported outside the except block: a failure raised inside carries the signal as its `__context__`
        keys_suffix = "" if len(absent.includes) == 1 else "s"
        missing_suffix = "" if len(absent.missing) == 1 else "s"
        includes_fmt = self._fmt_items(
            [".".join([str(segment) for segment in key]) if type(key) is tuple else key for key in absent.includes]
        )
        self._unmet(
            f"Expected <{_capped_format(absent.mapping)}> to include key{keys_suffix} {includes_fmt},"
            f" but did not include key{missing_suffix} {self._fmt_items(absent.missing)}."
        )
        # reported: falsy, so no second failure follows it, and `None` so a caller walking items stops there
        return None

    @staticmethod
    def _normalize_key_specs(specs, param):
        """An ``ignore``/``include`` kwarg as a flat list of key-specs; see `_engine._equality`."""
        return normalize_key_specs(specs, param)

    @staticmethod
    def _dict_ignore(ignore):
        """Ignore-specs for one comparison; see `_engine._equality`."""
        return ignore_specs(ignore)

    @staticmethod
    def _dict_include(include):
        """Include-specs for one comparison; see `_engine._equality`."""
        return include_specs(include)

    def _selected_keys_only(
        self, mapping: object, ignore: object, include: object, held_as: type = dict, beside: object = None
    ) -> object:
        """A copy of ``mapping`` holding only the keys the comparison actually looked at.

        `_dict_not_equal()` picks those keys to reach its verdict, and both the repr and the diff used
        to be built from the unfiltered pair.  A failure under ``include="b"`` then printed a diff
        whose first entry was a key that had never been compared, and one under ``ignore="a"`` named
        ``a`` as a difference in the same breath as saying it was ignored.

        Returns ``mapping`` itself when no filter is set, so the ordinary path allocates nothing.

        *held_as* is the class of the value ``mapping`` was read from.  The copy carries it, as a `TakenApart`,
        where it is not a plain dict: copied as one, a dict of a class of its own lost the class ``strict_types``
        had held it apart by, and the diff then had no entry where the comparison failed.

        *beside* is the mapping this one was compared with.  A value a key path goes on into is copied with its
        keys left out only where the value beside it was read by its fields too: compared whole, it is kept whole,
        or the copy differed from a counterpart the value itself equals.
        """
        ignoring, including = key_specs_given(ignore), key_specs_given(include)
        if not (ignoring or including):
            return mapping
        ignores = self._dict_ignore(ignore) if ignoring else []
        includes = self._dict_include(include) if including else []
        # an OrderedDict keeps its type and a TakenApart its class, both part of what was compared
        if isinstance(mapping, TakenApart):
            kept: dict = TakenApart(mapping.kind, {}, mapping.compared_by)
        elif isinstance(mapping, collections.OrderedDict):
            ordered = held_as if issubclass(held_as, collections.OrderedDict) else collections.OrderedDict
            kept = collections.OrderedDict.__new__(ordered)
        else:
            kept = {} if held_as is dict else TakenApart(held_as, {})
        for key in mapping:  # ty: ignore[not-iterable]  # only ever called on the dict-like branch
            value = mapping[key]  # ty: ignore[not-subscriptable]  # same
            if ignoring and _spec_matches(key, value, ignores):
                continue
            if including and not _spec_matches(key, value, includes):
                continue
            nested_ignore = [entry[1:] for entry in ignores if type(entry) is tuple and entry[0] == key] or None
            nested_include = [
                entry[1:] for entry in self._dict_ignore(include) if type(entry) is tuple and entry[0] == key
            ] or None
            if nested_ignore or nested_include:
                # the snapshot and not the value: recursing into the original would read it a third time
                kept_value = _read_by_fields(value)
                found, counterpart = (False, None) if beside is None else lookup(beside, key)
                other_value = _read_by_fields(counterpart) if found else None
                if kept_value is not None and (other_value is not None or not found):
                    value = self._selected_keys_only(
                        kept_value, nested_ignore, nested_include, type(value), other_value
                    )
            kept[key] = value
        return kept

    def _failure_views(
        self, val, other, ignore, include, config, dict_repr, list_repr
    ) -> tuple[str, list, str, str, tuple[object, object] | None]:
        """What a failed comparison shows, by the shape of the pair: the kind of diff, its entries, the two reprs,
        and under a key option the two copies the diff is of, without the keys left out.

        *dict_repr* and *list_repr* are `_dict_err`'s own walks, which render a pair with what matched left out.
        """
        filtered = key_specs_given(ignore) or key_specs_given(include)
        if (keyed := _keyed_pair(val, other)) is not None:
            reported_val = self._selected_keys_only(keyed[0], ignore, include, beside=keyed[1])
            reported_other = self._selected_keys_only(keyed[1], ignore, include, beside=keyed[0])
            val_repr, other_repr = _informative(
                val,
                other,
                run_nested(dict_repr(reported_val, reported_other)),
                run_nested(dict_repr(reported_other, reported_val)),
                # a compare config hides no key, so only a key filter keeps the whole values out of the message
                whole=not filtered,
            )
            entries = _sub_diff_entries(reported_val, reported_other, _ROOT, config=config) or []
            return "dict", entries, val_repr, other_repr, (reported_val, reported_other) if filtered else None
        if filtered and _both_list_like(val, other):
            actual_items, expected_items = cast("list | tuple", val), cast("list | tuple", other)
            reported_val = self._selected_items_only(actual_items, expected_items, ignore, include)
            reported_other = self._selected_items_only(expected_items, actual_items, ignore, include)
            entries = _sub_diff_entries(reported_val, reported_other, _ROOT, config=config) or []
            if _aligned_match_indices(reported_val, reported_other) is None:
                val_repr = run_nested(list_repr(reported_val, reported_other))
                other_repr = run_nested(list_repr(reported_other, reported_val))
            else:
                # two sequences that shifted apart are paired by alignment in the diff, so in the message too
                val_repr = _elided_seq_repr(reported_val, reported_other)
                other_repr = _elided_seq_repr(reported_other, reported_val)
            return "sequence", entries, val_repr, other_repr, (reported_val, reported_other)
        # the shape said keyed and the value is not, so the richer message is the thing given up here
        return "scalar", [], _safe_repr(val), _safe_repr(other), None

    def _selected_items_only(
        self, items: list | tuple, others: list | tuple, ignore: object, include: object
    ) -> list | tuple:
        """A copy of a sequence whose elements compared by their fields hold only the keys that were looked at.

        An element is compared by its fields where its counterpart in *others* has fields too, and whole where it
        has none.  Copied with keys left out all the same, a value its counterpart equals was shown as differing.
        Two sequences of different lengths have no counterparts: no element of them was compared, and the diff
        pairs them by alignment, so there every element with fields is copied without the keys left out.
        """
        paired = len(items) == len(others)
        kept = []
        for index, item in enumerate(items):
            fields, beside = fields_pair(item, others[index]) if paired else (as_fields(item), None)
            if fields is None or (paired and beside is None):
                kept.append(item)
            else:
                kept.append(self._selected_keys_only(fields, ignore, include, type(item), beside))
        return tuple(kept) if isinstance(items, tuple) else kept

    def _key_filter_note(self, ignore: object, include: object) -> str:
        """The ` ignoring keys ...` / ` including keys ...` tail of a dict failure, or an empty string."""
        note = ""
        for label, specs in (("ignoring", ignore), ("including", include)):
            if key_specs_given(specs):
                spelled = [
                    ".".join([str(segment) for segment in entry]) if type(entry) is tuple else entry
                    for entry in self._dict_ignore(specs)
                ]
                note += f" {label} keys {self._fmt_items(spelled)}"
        return note

    def _dict_err(
        self,
        val: object,
        other: object,
        ignore: object = None,
        include: object = None,
        config: _CompareConfig | None = None,
        held: tuple[object, object] | None = None,
    ) -> None:
        """Helper to construct error message for dict comparison, and for two sequences under a key option.

        A compare ``config`` is routed through both the textual repr (a tolerated / comparator-equal leaf is
        ellipsized, never shown) and the structured diff, so the message and diff agree on what differs.
        ``ignore`` / ``include`` are applied to both for the same reason.

        *held* is what the failure hands back as ``actual`` and ``expected`` where that is not what was walked:
        a dict taken apart to be read beside a record is a copy, and the failure holds the caller's own.
        """

        _dict_repr, _list_repr = _elided_walks(config)
        kind, diff_entries, val_repr, other_repr, copies = self._failure_views(
            val, other, ignore, include, config, _dict_repr, _list_repr
        )
        # the comparison has failed, so where the walk shows nothing under the pair, the pair is the entry
        diff = DiffResult(kind=kind, entries=diff_entries or [_ROOT.leaf_entry(actual=val, expected=other)])
        actual, expected = held or (val, other)
        message = (
            f"Expected <{val_repr}> to be equal to <{other_repr}>{self._key_filter_note(ignore, include)}, but was not."
            f"{_config_note(config)}"
        )
        # under a compare config `==` did not decide alone: a tolerated leaf differs in the two and held
        self._compared = None if config is not None else copies or (actual, expected)
        self.error(message, actual=actual, expected=expected, diff=diff)

    @staticmethod
    def _to_comparable_dict(obj):
        """Convert an object with introspectable fields to a dict for comparison; see `_engine._equality`.

        Returns None if the object cannot be converted.
        """
        return comparable_fields(obj)
