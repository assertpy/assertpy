from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_ParserT = TypeVar("_ParserT", bound="Callable[[str], Any]")

_BOOL_TRUE: Final = frozenset({"true", "yes", "1", "on"})
_BOOL_FALSE: Final = frozenset({"false", "no", "0", "off"})


def _with_pattern(pattern: str) -> Callable[[_ParserT], _ParserT]:
    def decorator(func: _ParserT) -> _ParserT:
        # behave reads the pattern off the function object, which is not something a callable type carries
        cast("Any", func).pattern = pattern
        return func

    return decorator


@_with_pattern(r"\d+")
def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise ValueError(f"expected positive integer, got {value}")
    return value


@_with_pattern(r"\d+")
def _non_negative_int(text: str) -> int:
    return int(text)


@_with_pattern(r"\d+\.?\d*")
def _positive_float(text: str) -> float:
    value = float(text)
    if value <= 0:
        raise ValueError(f"expected positive float, got {value}")
    return value


@_with_pattern(r".+?")
def _non_empty_string(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("expected non-empty string, got blank")
    return stripped


@_with_pattern(r"\w+")
def _bool_like(text: str) -> bool:
    lower = text.strip().lower()
    if lower in _BOOL_TRUE:
        return True
    if lower in _BOOL_FALSE:
        return False
    raise ValueError(f"expected boolean-like value, got {text!r}")


ASSERTPY_TYPES: Final[Mapping[str, Callable[[str], Any]]] = MappingProxyType(
    {
        "PositiveInt": _positive_int,
        "NonNegativeInt": _non_negative_int,
        "PositiveFloat": _positive_float,
        "NonEmptyString": _non_empty_string,
        "BoolLike": _bool_like,
    }
)


def register_assertpy_types() -> None:
    """Register assertpy parameter types for Behave step definitions.

    Registers the following types for use in step patterns:

    - ``{param:PositiveInt}`` - positive integer (> 0)
    - ``{param:NonNegativeInt}`` - non-negative integer (>= 0)
    - ``{param:PositiveFloat}`` - positive float (> 0)
    - ``{param:NonEmptyString}`` - non-empty, stripped string
    - ``{param:BoolLike}`` - boolean from true/false/yes/no/1/0/on/off

    Requires ``behave`` to be installed (``pip install assertpy[behave]``).

    Raises:
        ImportError: if behave is not installed
    """
    try:
        from behave import register_type  # ty: ignore[unresolved-import]  # optional dependency
    except ImportError:
        raise ImportError(
            "behave is required for register_assertpy_types(). Install it with: pip install assertpy[behave]"
        ) from None
    register_type(**ASSERTPY_TYPES)
