from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._introspection import Replay, handed_away

if TYPE_CHECKING:
    from .._matcher_impls import ExceptionInfo, WarningInfo
    from ..errors import AssertionFailure, DiffResult, PollTrace
    from ..http_mixin import _Response
    from ..outcome import AssertionOutcome, Requirement
    from ._compare import _CompareConfig
    from ._compat import Self
    from ._introspection import WarningLogger


class _MixinBase:
    _response: _Response | None = None
    """The HTTP response this value came from, when it came from one.

    Carried by every pivot rather than looked up at the end, because the response is gone by the time a
    failure is composed over its parsed body.
    """

    _equality_comparison = False
    """Whether the failure being reported came from asking whether two values are equal.

    Read by the failure composer.  Only there does it follow from a type comparing by identity that
    nothing on the other side could have passed: a containment failure over the same values is about
    where they sit, and a comparator of the caller's own owns its leaves outright.
    """

    _comparators_took_part = False
    """Whether the comparison being reported was given ``comparators=``.

    Read by the failure composer for a pair inside the diff that prints the same on both sides: identity is
    the reason for it only where no predicate of the caller's could have been what turned it down.
    """

    _answering_another = False
    """Whether the assertion running on this builder answers another assertion rather than the caller.

    Set by `not_` around the assertion it inverts, and by a snapshot around its own comparison, so the
    vacuity guard leaves both alone.  On the builder rather than in a context variable: an assertion that
    a comparator or predicate of the caller's runs is on a builder of its own, and is the caller's own.
    """

    _unmet_prerequisite: AssertionOutcome | None = None
    """A verdict run's first failure when it is on something the question presupposes.

    Recorded by `_unmet()` and read by `not_`, which delivers it as it stands instead of inverting it.
    Inverted, a caught exception that is not a group passed `not_.contains_error(ValueError)`: "not a
    group" read as "holds no such error", where the question has no answer at all.  Only the first
    failure, since the strict run stops there: a prerequisite missed after an ordinary failure was
    never reached.  Cleared for each verdict run and put back after it, so one left behind outside a
    run is never read.
    """

    _answers_to: Any = None
    """The builder whose verdict run a pivot made during that run belongs to, or ``None`` for its own.

    A pivot inherits check mode, and its failures landed in a sink of its own that nobody read: an
    extension asserting on `extracting_group()` held under `check()` while its strict run failed, and
    failed under `not_` for the wrong reason.  Set by `builder()` and read through `_verdict_holder()`.
    The pivot takes `_answering_another` along too, since what it asserts answers the same run.
    """

    _run_pivots: list[Any] | None = None
    """The pivots made during the verdict run this builder holds, released by `_release_pivots()` when it ends."""

    _read: Replay | None = None
    """What a one-shot iterator held as the value has handed out, kept for the links of the chain that follow."""

    def _walked(self) -> Any:
        """The value as a walk reads it: a one-shot iterator through what it has handed out so far, else itself.

        Every assertion that walks the value reads it here, or the second link of a chain over a generator
        passed or failed over nothing.  Asked as `materialized` asks, ``iter(value) is value``.
        """
        value = self.val
        kind = type(value)
        if kind is list or kind is tuple or kind is str or kind is dict or kind is set or kind is frozenset:
            return value
        read = self._read
        if read is not None and read.source is value:
            if read.given_away:
                raise handed_away()
            return read
        try:
            one_shot = iter(value) is value
        except TypeError:
            return value
        if not one_shot:
            return value
        read = self._read = Replay(value)
        return read

    def _handed_out(self) -> Any:
        """The value itself, for code of the caller's, which may take from a one-shot iterator what no link sees."""
        read = self._read
        # what a link has read already is all that is looked at: asked for an iterator here, the value ran its
        # `__iter__` ahead of a predicate that may never walk it
        if read is not None and read.source is self.val:
            read.give_away()
        return self.val

    def _drained(self) -> Any:
        """The value, or the items of a one-shot iterator in a list of their own, the same items for every link."""
        value = self.val
        kind = type(value)
        # asked here as well: through `_walked` alone, `contains` on a list of 200 cost 11% more
        if kind is list or kind is tuple or kind is str or kind is dict or kind is set or kind is frozenset:
            return value
        walked = self._walked()
        return walked.drained() if type(walked) is Replay else walked

    _compared: tuple[object, object] | None = None
    """The two values a failed equality held against each other, set just ahead of `error()`, which takes it.

    The pair ``==`` alone decided: the value and the operand where nothing was left out, and the copies
    without the keys left out under ``ignore=`` or ``include=``.  Not set where something else decided, under
    ``tolerance=``, ``comparators=``, ``strict_types=`` or ``ignore_null=``.  Kept on the failure for a listener
    that shows two values side by side.
    """

    _compared_nothing = False
    """Whether a comparison under ``ignore``/``include`` passed with no key left to compare.

    Set by the comparison on the pass it decided, never on a failure, and read and cleared by
    `is_equal_to()` as soon as that comparison returns.
    """

    if TYPE_CHECKING:
        val: Any
        description: str
        kind: str | None
        expected: type[BaseException] | ExceptionInfo | None
        logger: WarningLogger
        _not_expected: bool
        _expected_warning: type[Warning] | WarningInfo | None
        _return_value: object
        _raised_exception: object
        _value_taint_reason: str | None

        def error(
            self,
            msg: str,
            *,
            actual: object = ...,
            expected: object = ...,
            diff: DiffResult | None = ...,
            requirement: Requirement | None = ...,
            suppress_context: bool = ...,
        ) -> Self: ...

        def _compose(
            self,
            msg: str,
            *,
            actual: object,
            expected: object,
            diff: DiffResult | None,
            trace: PollTrace | None,
            requirement: Requirement | None = ...,
        ) -> AssertionOutcome: ...

        def _unmet(
            self,
            msg: str,
            *,
            expected: object = ...,
            requirement: Requirement | None = ...,
            suppress_context: bool = ...,
        ) -> None: ...

        @staticmethod
        def _failure(outcome: AssertionOutcome) -> AssertionFailure: ...

        def builder(
            self,
            val: object,
            description: str = ...,
            kind: str | None = ...,
            expected: type[BaseException] | ExceptionInfo | None = ...,
            logger: WarningLogger | None = ...,
            origin: str | None = ...,
        ) -> Self: ...

        def _when_called_with_warning(
            self, expected: type[Warning] | WarningInfo, *some_args: object, **some_kwargs: object
        ) -> Self: ...

        def _when_called_with_not_warning(
            self, expected: type[Warning] | WarningInfo, *some_args: object, **some_kwargs: object
        ) -> Self: ...

        def _fmt_items(self, items: object) -> str: ...

        def _fmt_args_kwargs(self, *some_args: object, **some_kwargs: object) -> str: ...

        def _validate_between_args(self, val_type: type, low: object, high: object) -> None: ...

        def _validate_close_to_args(self, val: object, other: object, tolerance: object, rel: object = ...) -> None: ...

        def _is_dict_like(
            self,
            candidate: object,
            check_keys: bool = ...,
            check_values: bool = ...,
            check_getitem: bool = ...,
        ) -> bool: ...

        def _require_dict_like(
            self,
            candidate: object,
            check_keys: bool = ...,
            check_values: bool = ...,
            check_getitem: bool = ...,
            name: str = ...,
        ) -> None: ...

        def _check_iterable(self, val: object, check_getitem: bool = ..., name: str = ...) -> None: ...

        def _dict_not_equal(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
            config: _CompareConfig | None = ...,
        ) -> bool | None: ...

        def _dict_err(
            self,
            val: object,
            other: object,
            ignore: object = ...,
            include: object = ...,
            config: _CompareConfig | None = ...,
            held: tuple[object, object] | None = ...,
        ) -> None: ...

        @staticmethod
        def _to_comparable_dict(obj: object) -> dict[str, object] | None: ...

        _NUMERIC_COMPAREABLE: frozenset[type]
        _NUMERIC_NON_COMPAREABLE: frozenset[type]

        def contains(self, *items: object) -> Self: ...

        def does_not_contain(self, *items: object) -> Self: ...

        # `Any`, not `object`: the real one is annotated per value type, and a wider one here overrides incompatibly
        def starts_with(self, prefix: Any) -> Self: ...

        def is_equal_to(self, other: object, **kwargs: object) -> Self: ...

        def is_not_equal_to(self, other: object) -> Self: ...
