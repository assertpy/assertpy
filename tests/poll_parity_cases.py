"""One assignment per pair of (a value a chain can be over, a receiver arm a rung carries).

Read by `test_poll_parity.py`, which runs a checker over it to re-derive `REACHES` in
`poll_parity_baseline.py`.  Which chain reaches which rung is not something to argue about in a
docstring: it is whatever the checker resolves, and this is where it is asked.

Every arm is asked about, not only the ones that look open.  The chain is covariant in the value it
polls, so `bool` reaches a rung written for `int` and a `datetime` reaches one written for `date`,
and reading a rung named for a value as reachable by that value alone recorded a false zero for both.

Nothing here runs.  Every body is a call the checker reads and pytest never executes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    import datetime
    import pathlib
    from collections.abc import Callable, Iterable
    from pathlib import Path
    from typing import SupportsFloat, SupportsIndex

    from assertpy._engine._capable_typing import (
        _Callable,
        _Indexed,
        _Keyed,
        _KeyedWithItems,
        _KeyedWithValues,
        _Orderable,
        _PathLike,
    )
    from assertpy._engine._typing import _CapableT

_T = TypeVar("_T")
_U = TypeVar("_U")
_E = TypeVar("_E")
_K = TypeVar("_K")
_V = TypeVar("_V")
_P = TypeVar("_P")


class _FrameShaped:
    """The shape `_FrameT_co` is bound to, written out so no stand-in library is needed."""

    def pivot(self, *args: Any, **kwargs: Any) -> Any: ...
    @property
    def shape(self) -> Any: ...


class _ArrayShaped:
    """And the shape `_ArrayT_co` is bound to."""

    def __array__(self) -> Any: ...
    @property
    def strides(self) -> Any: ...
    def __len__(self) -> int: ...


class _FrameThatWalks(_FrameShaped):
    """And one that also walks, which every real frame does and the bound alone does not say."""

    def __iter__(self) -> Any: ...
    def __len__(self) -> int: ...


class _ArrayThatWalks(_ArrayShaped):
    """The same for an array: a real one is iterable, and the bound asks only for its length."""

    def __iter__(self) -> Any: ...


class _Everything:
    """Every structural member any receiver asks for, so a witness carrying it bounds the row above.

    A real frame or array sits between the bound and this: pandas declares `keys`, a lookup, the
    comparisons and the conversions, and each of those reaches rungs the bound alone does not.  Rather
    than depend on pandas to answer a typing question, the two ends are recorded and the real one is
    somewhere between them."""

    def __iter__(self) -> Any: ...
    def __len__(self) -> int: ...
    def __contains__(self, item: Any) -> bool: ...
    def __getitem__(self, key: Any, /) -> Any: ...
    def __lt__(self, other: Any, /) -> Any: ...
    def __float__(self) -> float: ...
    def __index__(self) -> int: ...
    def __fspath__(self) -> str: ...
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
    def keys(self) -> Any: ...
    def values(self) -> Any: ...
    def model_dump(self, *args: Any, **kwargs: Any) -> Any: ...


class _FrameCarryingEverything(_FrameShaped, _Everything):
    """A frame-shaped value carrying everything else as well, which bounds the frame row above."""


class _ArrayCarryingEverything(_ArrayShaped, _Everything):
    """And the same for an array."""


def _takes_a_call(value: Callable[..., _P]) -> None: ...


def _takes_any_call(value: Callable[..., object]) -> None: ...


def _takes_iterable(value: Iterable[_E]) -> None: ...


def _takes_none(value: None) -> None: ...


def _takes_path(value: Path) -> None: ...


def _takes_float(value: SupportsFloat) -> None: ...


def _takes_index(value: SupportsIndex) -> None: ...


def _takes_array(value: _ArrayShaped) -> None: ...


def _takes_callable_shape(value: _Callable) -> None: ...


def _takes_capable(value: _CapableT) -> None: ...


def _takes_frame(value: _FrameShaped) -> None: ...


def _takes_indexed(value: _Indexed[_E]) -> None: ...


def _takes_keyed(value: _Keyed) -> None: ...


def _takes_keyed_with_items(value: _KeyedWithItems) -> None: ...


def _takes_keyed_with_values(value: _KeyedWithValues) -> None: ...


def _takes_orderable(value: _Orderable) -> None: ...


def _takes_path_like(value: _PathLike) -> None: ...


def _takes_anything(value: _T) -> None: ...


def _takes_anything_else(value: _U) -> None: ...


def _takes_bool(value: bool) -> None: ...


def _takes_bytearray(value: bytearray) -> None: ...


def _takes_bytes(value: bytes) -> None: ...


def _takes_complex(value: complex) -> None: ...


def _takes_date(value: datetime.date) -> None: ...


def _takes_datetime(value: datetime.datetime) -> None: ...


def _takes_dict(value: dict[_K, _V]) -> None: ...


def _takes_float_value(value: float) -> None: ...


def _takes_frozenset(value: frozenset[_E]) -> None: ...


def _takes_int(value: int) -> None: ...


def _takes_list(value: list[_E]) -> None: ...


def _takes_a_path(value: pathlib.Path) -> None: ...


def _takes_set(value: set[_E]) -> None: ...


def _takes_str(value: str) -> None: ...


def _takes_tuple(value: tuple[_E, ...]) -> None: ...


def _case_001(value: str) -> None:
    _takes_a_call(value)


def _case_002(value: str) -> None:
    _takes_any_call(value)


def _case_003(value: str) -> None:
    _takes_iterable(value)


def _case_004(value: str) -> None:
    _takes_none(value)


def _case_005(value: str) -> None:
    _takes_path(value)


def _case_006(value: str) -> None:
    _takes_float(value)


def _case_007(value: str) -> None:
    _takes_index(value)


def _case_008(value: str) -> None:
    _takes_array(value)


def _case_009(value: str) -> None:
    _takes_callable_shape(value)


def _case_010(value: str) -> None:
    _takes_capable(value)


def _case_011(value: str) -> None:
    _takes_frame(value)


def _case_012(value: str) -> None:
    _takes_indexed(value)


def _case_013(value: str) -> None:
    _takes_keyed(value)


def _case_014(value: str) -> None:
    _takes_keyed_with_items(value)


def _case_015(value: str) -> None:
    _takes_keyed_with_values(value)


def _case_016(value: str) -> None:
    _takes_orderable(value)


def _case_017(value: str) -> None:
    _takes_path_like(value)


def _case_018(value: str) -> None:
    _takes_anything(value)


def _case_019(value: str) -> None:
    _takes_anything_else(value)


def _case_020(value: str) -> None:
    _takes_bool(value)


def _case_021(value: str) -> None:
    _takes_bytearray(value)


def _case_022(value: str) -> None:
    _takes_bytes(value)


def _case_023(value: str) -> None:
    _takes_complex(value)


def _case_024(value: str) -> None:
    _takes_date(value)


def _case_025(value: str) -> None:
    _takes_datetime(value)


def _case_026(value: str) -> None:
    _takes_dict(value)


def _case_027(value: str) -> None:
    _takes_float_value(value)


def _case_028(value: str) -> None:
    _takes_frozenset(value)


def _case_029(value: str) -> None:
    _takes_int(value)


def _case_030(value: str) -> None:
    _takes_list(value)


def _case_031(value: str) -> None:
    _takes_a_path(value)


def _case_032(value: str) -> None:
    _takes_set(value)


def _case_033(value: str) -> None:
    _takes_str(value)


def _case_034(value: str) -> None:
    _takes_tuple(value)


def _case_035(value: bool) -> None:
    _takes_a_call(value)


def _case_036(value: bool) -> None:
    _takes_any_call(value)


def _case_037(value: bool) -> None:
    _takes_iterable(value)


def _case_038(value: bool) -> None:
    _takes_none(value)


def _case_039(value: bool) -> None:
    _takes_path(value)


def _case_040(value: bool) -> None:
    _takes_float(value)


def _case_041(value: bool) -> None:
    _takes_index(value)


def _case_042(value: bool) -> None:
    _takes_array(value)


def _case_043(value: bool) -> None:
    _takes_callable_shape(value)


def _case_044(value: bool) -> None:
    _takes_capable(value)


def _case_045(value: bool) -> None:
    _takes_frame(value)


def _case_046(value: bool) -> None:
    _takes_indexed(value)


def _case_047(value: bool) -> None:
    _takes_keyed(value)


def _case_048(value: bool) -> None:
    _takes_keyed_with_items(value)


def _case_049(value: bool) -> None:
    _takes_keyed_with_values(value)


def _case_050(value: bool) -> None:
    _takes_orderable(value)


def _case_051(value: bool) -> None:
    _takes_path_like(value)


def _case_052(value: bool) -> None:
    _takes_anything(value)


def _case_053(value: bool) -> None:
    _takes_anything_else(value)


def _case_054(value: bool) -> None:
    _takes_bool(value)


def _case_055(value: bool) -> None:
    _takes_bytearray(value)


def _case_056(value: bool) -> None:
    _takes_bytes(value)


def _case_057(value: bool) -> None:
    _takes_complex(value)


def _case_058(value: bool) -> None:
    _takes_date(value)


def _case_059(value: bool) -> None:
    _takes_datetime(value)


def _case_060(value: bool) -> None:
    _takes_dict(value)


def _case_061(value: bool) -> None:
    _takes_float_value(value)


def _case_062(value: bool) -> None:
    _takes_frozenset(value)


def _case_063(value: bool) -> None:
    _takes_int(value)


def _case_064(value: bool) -> None:
    _takes_list(value)


def _case_065(value: bool) -> None:
    _takes_a_path(value)


def _case_066(value: bool) -> None:
    _takes_set(value)


def _case_067(value: bool) -> None:
    _takes_str(value)


def _case_068(value: bool) -> None:
    _takes_tuple(value)


def _case_069(value: int) -> None:
    _takes_a_call(value)


def _case_070(value: int) -> None:
    _takes_any_call(value)


def _case_071(value: int) -> None:
    _takes_iterable(value)


def _case_072(value: int) -> None:
    _takes_none(value)


def _case_073(value: int) -> None:
    _takes_path(value)


def _case_074(value: int) -> None:
    _takes_float(value)


def _case_075(value: int) -> None:
    _takes_index(value)


def _case_076(value: int) -> None:
    _takes_array(value)


def _case_077(value: int) -> None:
    _takes_callable_shape(value)


def _case_078(value: int) -> None:
    _takes_capable(value)


def _case_079(value: int) -> None:
    _takes_frame(value)


def _case_080(value: int) -> None:
    _takes_indexed(value)


def _case_081(value: int) -> None:
    _takes_keyed(value)


def _case_082(value: int) -> None:
    _takes_keyed_with_items(value)


def _case_083(value: int) -> None:
    _takes_keyed_with_values(value)


def _case_084(value: int) -> None:
    _takes_orderable(value)


def _case_085(value: int) -> None:
    _takes_path_like(value)


def _case_086(value: int) -> None:
    _takes_anything(value)


def _case_087(value: int) -> None:
    _takes_anything_else(value)


def _case_088(value: int) -> None:
    _takes_bool(value)


def _case_089(value: int) -> None:
    _takes_bytearray(value)


def _case_090(value: int) -> None:
    _takes_bytes(value)


def _case_091(value: int) -> None:
    _takes_complex(value)


def _case_092(value: int) -> None:
    _takes_date(value)


def _case_093(value: int) -> None:
    _takes_datetime(value)


def _case_094(value: int) -> None:
    _takes_dict(value)


def _case_095(value: int) -> None:
    _takes_float_value(value)


def _case_096(value: int) -> None:
    _takes_frozenset(value)


def _case_097(value: int) -> None:
    _takes_int(value)


def _case_098(value: int) -> None:
    _takes_list(value)


def _case_099(value: int) -> None:
    _takes_a_path(value)


def _case_100(value: int) -> None:
    _takes_set(value)


def _case_101(value: int) -> None:
    _takes_str(value)


def _case_102(value: int) -> None:
    _takes_tuple(value)


def _case_103(value: float) -> None:
    _takes_a_call(value)


def _case_104(value: float) -> None:
    _takes_any_call(value)


def _case_105(value: float) -> None:
    _takes_iterable(value)


def _case_106(value: float) -> None:
    _takes_none(value)


def _case_107(value: float) -> None:
    _takes_path(value)


def _case_108(value: float) -> None:
    _takes_float(value)


def _case_109(value: float) -> None:
    _takes_index(value)


def _case_110(value: float) -> None:
    _takes_array(value)


def _case_111(value: float) -> None:
    _takes_callable_shape(value)


def _case_112(value: float) -> None:
    _takes_capable(value)


def _case_113(value: float) -> None:
    _takes_frame(value)


def _case_114(value: float) -> None:
    _takes_indexed(value)


def _case_115(value: float) -> None:
    _takes_keyed(value)


def _case_116(value: float) -> None:
    _takes_keyed_with_items(value)


def _case_117(value: float) -> None:
    _takes_keyed_with_values(value)


def _case_118(value: float) -> None:
    _takes_orderable(value)


def _case_119(value: float) -> None:
    _takes_path_like(value)


def _case_120(value: float) -> None:
    _takes_anything(value)


def _case_121(value: float) -> None:
    _takes_anything_else(value)


def _case_122(value: float) -> None:
    _takes_bool(value)


def _case_123(value: float) -> None:
    _takes_bytearray(value)


def _case_124(value: float) -> None:
    _takes_bytes(value)


def _case_125(value: float) -> None:
    _takes_complex(value)


def _case_126(value: float) -> None:
    _takes_date(value)


def _case_127(value: float) -> None:
    _takes_datetime(value)


def _case_128(value: float) -> None:
    _takes_dict(value)


def _case_129(value: float) -> None:
    _takes_float_value(value)


def _case_130(value: float) -> None:
    _takes_frozenset(value)


def _case_131(value: float) -> None:
    _takes_int(value)


def _case_132(value: float) -> None:
    _takes_list(value)


def _case_133(value: float) -> None:
    _takes_a_path(value)


def _case_134(value: float) -> None:
    _takes_set(value)


def _case_135(value: float) -> None:
    _takes_str(value)


def _case_136(value: float) -> None:
    _takes_tuple(value)


def _case_137(value: complex) -> None:
    _takes_a_call(value)


def _case_138(value: complex) -> None:
    _takes_any_call(value)


def _case_139(value: complex) -> None:
    _takes_iterable(value)


def _case_140(value: complex) -> None:
    _takes_none(value)


def _case_141(value: complex) -> None:
    _takes_path(value)


def _case_142(value: complex) -> None:
    _takes_float(value)


def _case_143(value: complex) -> None:
    _takes_index(value)


def _case_144(value: complex) -> None:
    _takes_array(value)


def _case_145(value: complex) -> None:
    _takes_callable_shape(value)


def _case_146(value: complex) -> None:
    _takes_capable(value)


def _case_147(value: complex) -> None:
    _takes_frame(value)


def _case_148(value: complex) -> None:
    _takes_indexed(value)


def _case_149(value: complex) -> None:
    _takes_keyed(value)


def _case_150(value: complex) -> None:
    _takes_keyed_with_items(value)


def _case_151(value: complex) -> None:
    _takes_keyed_with_values(value)


def _case_152(value: complex) -> None:
    _takes_orderable(value)


def _case_153(value: complex) -> None:
    _takes_path_like(value)


def _case_154(value: complex) -> None:
    _takes_anything(value)


def _case_155(value: complex) -> None:
    _takes_anything_else(value)


def _case_156(value: complex) -> None:
    _takes_bool(value)


def _case_157(value: complex) -> None:
    _takes_bytearray(value)


def _case_158(value: complex) -> None:
    _takes_bytes(value)


def _case_159(value: complex) -> None:
    _takes_complex(value)


def _case_160(value: complex) -> None:
    _takes_date(value)


def _case_161(value: complex) -> None:
    _takes_datetime(value)


def _case_162(value: complex) -> None:
    _takes_dict(value)


def _case_163(value: complex) -> None:
    _takes_float_value(value)


def _case_164(value: complex) -> None:
    _takes_frozenset(value)


def _case_165(value: complex) -> None:
    _takes_int(value)


def _case_166(value: complex) -> None:
    _takes_list(value)


def _case_167(value: complex) -> None:
    _takes_a_path(value)


def _case_168(value: complex) -> None:
    _takes_set(value)


def _case_169(value: complex) -> None:
    _takes_str(value)


def _case_170(value: complex) -> None:
    _takes_tuple(value)


def _case_171(value: dict[str, int]) -> None:
    _takes_a_call(value)


def _case_172(value: dict[str, int]) -> None:
    _takes_any_call(value)


def _case_173(value: dict[str, int]) -> None:
    _takes_iterable(value)


def _case_174(value: dict[str, int]) -> None:
    _takes_none(value)


def _case_175(value: dict[str, int]) -> None:
    _takes_path(value)


def _case_176(value: dict[str, int]) -> None:
    _takes_float(value)


def _case_177(value: dict[str, int]) -> None:
    _takes_index(value)


def _case_178(value: dict[str, int]) -> None:
    _takes_array(value)


def _case_179(value: dict[str, int]) -> None:
    _takes_callable_shape(value)


def _case_180(value: dict[str, int]) -> None:
    _takes_capable(value)


def _case_181(value: dict[str, int]) -> None:
    _takes_frame(value)


def _case_182(value: dict[str, int]) -> None:
    _takes_indexed(value)


def _case_183(value: dict[str, int]) -> None:
    _takes_keyed(value)


def _case_184(value: dict[str, int]) -> None:
    _takes_keyed_with_items(value)


def _case_185(value: dict[str, int]) -> None:
    _takes_keyed_with_values(value)


def _case_186(value: dict[str, int]) -> None:
    _takes_orderable(value)


def _case_187(value: dict[str, int]) -> None:
    _takes_path_like(value)


def _case_188(value: dict[str, int]) -> None:
    _takes_anything(value)


def _case_189(value: dict[str, int]) -> None:
    _takes_anything_else(value)


def _case_190(value: dict[str, int]) -> None:
    _takes_bool(value)


def _case_191(value: dict[str, int]) -> None:
    _takes_bytearray(value)


def _case_192(value: dict[str, int]) -> None:
    _takes_bytes(value)


def _case_193(value: dict[str, int]) -> None:
    _takes_complex(value)


def _case_194(value: dict[str, int]) -> None:
    _takes_date(value)


def _case_195(value: dict[str, int]) -> None:
    _takes_datetime(value)


def _case_196(value: dict[str, int]) -> None:
    _takes_dict(value)


def _case_197(value: dict[str, int]) -> None:
    _takes_float_value(value)


def _case_198(value: dict[str, int]) -> None:
    _takes_frozenset(value)


def _case_199(value: dict[str, int]) -> None:
    _takes_int(value)


def _case_200(value: dict[str, int]) -> None:
    _takes_list(value)


def _case_201(value: dict[str, int]) -> None:
    _takes_a_path(value)


def _case_202(value: dict[str, int]) -> None:
    _takes_set(value)


def _case_203(value: dict[str, int]) -> None:
    _takes_str(value)


def _case_204(value: dict[str, int]) -> None:
    _takes_tuple(value)


def _case_205(value: list[int]) -> None:
    _takes_a_call(value)


def _case_206(value: list[int]) -> None:
    _takes_any_call(value)


def _case_207(value: list[int]) -> None:
    _takes_iterable(value)


def _case_208(value: list[int]) -> None:
    _takes_none(value)


def _case_209(value: list[int]) -> None:
    _takes_path(value)


def _case_210(value: list[int]) -> None:
    _takes_float(value)


def _case_211(value: list[int]) -> None:
    _takes_index(value)


def _case_212(value: list[int]) -> None:
    _takes_array(value)


def _case_213(value: list[int]) -> None:
    _takes_callable_shape(value)


def _case_214(value: list[int]) -> None:
    _takes_capable(value)


def _case_215(value: list[int]) -> None:
    _takes_frame(value)


def _case_216(value: list[int]) -> None:
    _takes_indexed(value)


def _case_217(value: list[int]) -> None:
    _takes_keyed(value)


def _case_218(value: list[int]) -> None:
    _takes_keyed_with_items(value)


def _case_219(value: list[int]) -> None:
    _takes_keyed_with_values(value)


def _case_220(value: list[int]) -> None:
    _takes_orderable(value)


def _case_221(value: list[int]) -> None:
    _takes_path_like(value)


def _case_222(value: list[int]) -> None:
    _takes_anything(value)


def _case_223(value: list[int]) -> None:
    _takes_anything_else(value)


def _case_224(value: list[int]) -> None:
    _takes_bool(value)


def _case_225(value: list[int]) -> None:
    _takes_bytearray(value)


def _case_226(value: list[int]) -> None:
    _takes_bytes(value)


def _case_227(value: list[int]) -> None:
    _takes_complex(value)


def _case_228(value: list[int]) -> None:
    _takes_date(value)


def _case_229(value: list[int]) -> None:
    _takes_datetime(value)


def _case_230(value: list[int]) -> None:
    _takes_dict(value)


def _case_231(value: list[int]) -> None:
    _takes_float_value(value)


def _case_232(value: list[int]) -> None:
    _takes_frozenset(value)


def _case_233(value: list[int]) -> None:
    _takes_int(value)


def _case_234(value: list[int]) -> None:
    _takes_list(value)


def _case_235(value: list[int]) -> None:
    _takes_a_path(value)


def _case_236(value: list[int]) -> None:
    _takes_set(value)


def _case_237(value: list[int]) -> None:
    _takes_str(value)


def _case_238(value: list[int]) -> None:
    _takes_tuple(value)


def _case_239(value: tuple[int, ...]) -> None:
    _takes_a_call(value)


def _case_240(value: tuple[int, ...]) -> None:
    _takes_any_call(value)


def _case_241(value: tuple[int, ...]) -> None:
    _takes_iterable(value)


def _case_242(value: tuple[int, ...]) -> None:
    _takes_none(value)


def _case_243(value: tuple[int, ...]) -> None:
    _takes_path(value)


def _case_244(value: tuple[int, ...]) -> None:
    _takes_float(value)


def _case_245(value: tuple[int, ...]) -> None:
    _takes_index(value)


def _case_246(value: tuple[int, ...]) -> None:
    _takes_array(value)


def _case_247(value: tuple[int, ...]) -> None:
    _takes_callable_shape(value)


def _case_248(value: tuple[int, ...]) -> None:
    _takes_capable(value)


def _case_249(value: tuple[int, ...]) -> None:
    _takes_frame(value)


def _case_250(value: tuple[int, ...]) -> None:
    _takes_indexed(value)


def _case_251(value: tuple[int, ...]) -> None:
    _takes_keyed(value)


def _case_252(value: tuple[int, ...]) -> None:
    _takes_keyed_with_items(value)


def _case_253(value: tuple[int, ...]) -> None:
    _takes_keyed_with_values(value)


def _case_254(value: tuple[int, ...]) -> None:
    _takes_orderable(value)


def _case_255(value: tuple[int, ...]) -> None:
    _takes_path_like(value)


def _case_256(value: tuple[int, ...]) -> None:
    _takes_anything(value)


def _case_257(value: tuple[int, ...]) -> None:
    _takes_anything_else(value)


def _case_258(value: tuple[int, ...]) -> None:
    _takes_bool(value)


def _case_259(value: tuple[int, ...]) -> None:
    _takes_bytearray(value)


def _case_260(value: tuple[int, ...]) -> None:
    _takes_bytes(value)


def _case_261(value: tuple[int, ...]) -> None:
    _takes_complex(value)


def _case_262(value: tuple[int, ...]) -> None:
    _takes_date(value)


def _case_263(value: tuple[int, ...]) -> None:
    _takes_datetime(value)


def _case_264(value: tuple[int, ...]) -> None:
    _takes_dict(value)


def _case_265(value: tuple[int, ...]) -> None:
    _takes_float_value(value)


def _case_266(value: tuple[int, ...]) -> None:
    _takes_frozenset(value)


def _case_267(value: tuple[int, ...]) -> None:
    _takes_int(value)


def _case_268(value: tuple[int, ...]) -> None:
    _takes_list(value)


def _case_269(value: tuple[int, ...]) -> None:
    _takes_a_path(value)


def _case_270(value: tuple[int, ...]) -> None:
    _takes_set(value)


def _case_271(value: tuple[int, ...]) -> None:
    _takes_str(value)


def _case_272(value: tuple[int, ...]) -> None:
    _takes_tuple(value)


def _case_273(value: set[int]) -> None:
    _takes_a_call(value)


def _case_274(value: set[int]) -> None:
    _takes_any_call(value)


def _case_275(value: set[int]) -> None:
    _takes_iterable(value)


def _case_276(value: set[int]) -> None:
    _takes_none(value)


def _case_277(value: set[int]) -> None:
    _takes_path(value)


def _case_278(value: set[int]) -> None:
    _takes_float(value)


def _case_279(value: set[int]) -> None:
    _takes_index(value)


def _case_280(value: set[int]) -> None:
    _takes_array(value)


def _case_281(value: set[int]) -> None:
    _takes_callable_shape(value)


def _case_282(value: set[int]) -> None:
    _takes_capable(value)


def _case_283(value: set[int]) -> None:
    _takes_frame(value)


def _case_284(value: set[int]) -> None:
    _takes_indexed(value)


def _case_285(value: set[int]) -> None:
    _takes_keyed(value)


def _case_286(value: set[int]) -> None:
    _takes_keyed_with_items(value)


def _case_287(value: set[int]) -> None:
    _takes_keyed_with_values(value)


def _case_288(value: set[int]) -> None:
    _takes_orderable(value)


def _case_289(value: set[int]) -> None:
    _takes_path_like(value)


def _case_290(value: set[int]) -> None:
    _takes_anything(value)


def _case_291(value: set[int]) -> None:
    _takes_anything_else(value)


def _case_292(value: set[int]) -> None:
    _takes_bool(value)


def _case_293(value: set[int]) -> None:
    _takes_bytearray(value)


def _case_294(value: set[int]) -> None:
    _takes_bytes(value)


def _case_295(value: set[int]) -> None:
    _takes_complex(value)


def _case_296(value: set[int]) -> None:
    _takes_date(value)


def _case_297(value: set[int]) -> None:
    _takes_datetime(value)


def _case_298(value: set[int]) -> None:
    _takes_dict(value)


def _case_299(value: set[int]) -> None:
    _takes_float_value(value)


def _case_300(value: set[int]) -> None:
    _takes_frozenset(value)


def _case_301(value: set[int]) -> None:
    _takes_int(value)


def _case_302(value: set[int]) -> None:
    _takes_list(value)


def _case_303(value: set[int]) -> None:
    _takes_a_path(value)


def _case_304(value: set[int]) -> None:
    _takes_set(value)


def _case_305(value: set[int]) -> None:
    _takes_str(value)


def _case_306(value: set[int]) -> None:
    _takes_tuple(value)


def _case_307(value: frozenset[int]) -> None:
    _takes_a_call(value)


def _case_308(value: frozenset[int]) -> None:
    _takes_any_call(value)


def _case_309(value: frozenset[int]) -> None:
    _takes_iterable(value)


def _case_310(value: frozenset[int]) -> None:
    _takes_none(value)


def _case_311(value: frozenset[int]) -> None:
    _takes_path(value)


def _case_312(value: frozenset[int]) -> None:
    _takes_float(value)


def _case_313(value: frozenset[int]) -> None:
    _takes_index(value)


def _case_314(value: frozenset[int]) -> None:
    _takes_array(value)


def _case_315(value: frozenset[int]) -> None:
    _takes_callable_shape(value)


def _case_316(value: frozenset[int]) -> None:
    _takes_capable(value)


def _case_317(value: frozenset[int]) -> None:
    _takes_frame(value)


def _case_318(value: frozenset[int]) -> None:
    _takes_indexed(value)


def _case_319(value: frozenset[int]) -> None:
    _takes_keyed(value)


def _case_320(value: frozenset[int]) -> None:
    _takes_keyed_with_items(value)


def _case_321(value: frozenset[int]) -> None:
    _takes_keyed_with_values(value)


def _case_322(value: frozenset[int]) -> None:
    _takes_orderable(value)


def _case_323(value: frozenset[int]) -> None:
    _takes_path_like(value)


def _case_324(value: frozenset[int]) -> None:
    _takes_anything(value)


def _case_325(value: frozenset[int]) -> None:
    _takes_anything_else(value)


def _case_326(value: frozenset[int]) -> None:
    _takes_bool(value)


def _case_327(value: frozenset[int]) -> None:
    _takes_bytearray(value)


def _case_328(value: frozenset[int]) -> None:
    _takes_bytes(value)


def _case_329(value: frozenset[int]) -> None:
    _takes_complex(value)


def _case_330(value: frozenset[int]) -> None:
    _takes_date(value)


def _case_331(value: frozenset[int]) -> None:
    _takes_datetime(value)


def _case_332(value: frozenset[int]) -> None:
    _takes_dict(value)


def _case_333(value: frozenset[int]) -> None:
    _takes_float_value(value)


def _case_334(value: frozenset[int]) -> None:
    _takes_frozenset(value)


def _case_335(value: frozenset[int]) -> None:
    _takes_int(value)


def _case_336(value: frozenset[int]) -> None:
    _takes_list(value)


def _case_337(value: frozenset[int]) -> None:
    _takes_a_path(value)


def _case_338(value: frozenset[int]) -> None:
    _takes_set(value)


def _case_339(value: frozenset[int]) -> None:
    _takes_str(value)


def _case_340(value: frozenset[int]) -> None:
    _takes_tuple(value)


def _case_341(value: datetime.datetime) -> None:
    _takes_a_call(value)


def _case_342(value: datetime.datetime) -> None:
    _takes_any_call(value)


def _case_343(value: datetime.datetime) -> None:
    _takes_iterable(value)


def _case_344(value: datetime.datetime) -> None:
    _takes_none(value)


def _case_345(value: datetime.datetime) -> None:
    _takes_path(value)


def _case_346(value: datetime.datetime) -> None:
    _takes_float(value)


def _case_347(value: datetime.datetime) -> None:
    _takes_index(value)


def _case_348(value: datetime.datetime) -> None:
    _takes_array(value)


def _case_349(value: datetime.datetime) -> None:
    _takes_callable_shape(value)


def _case_350(value: datetime.datetime) -> None:
    _takes_capable(value)


def _case_351(value: datetime.datetime) -> None:
    _takes_frame(value)


def _case_352(value: datetime.datetime) -> None:
    _takes_indexed(value)


def _case_353(value: datetime.datetime) -> None:
    _takes_keyed(value)


def _case_354(value: datetime.datetime) -> None:
    _takes_keyed_with_items(value)


def _case_355(value: datetime.datetime) -> None:
    _takes_keyed_with_values(value)


def _case_356(value: datetime.datetime) -> None:
    _takes_orderable(value)


def _case_357(value: datetime.datetime) -> None:
    _takes_path_like(value)


def _case_358(value: datetime.datetime) -> None:
    _takes_anything(value)


def _case_359(value: datetime.datetime) -> None:
    _takes_anything_else(value)


def _case_360(value: datetime.datetime) -> None:
    _takes_bool(value)


def _case_361(value: datetime.datetime) -> None:
    _takes_bytearray(value)


def _case_362(value: datetime.datetime) -> None:
    _takes_bytes(value)


def _case_363(value: datetime.datetime) -> None:
    _takes_complex(value)


def _case_364(value: datetime.datetime) -> None:
    _takes_date(value)


def _case_365(value: datetime.datetime) -> None:
    _takes_datetime(value)


def _case_366(value: datetime.datetime) -> None:
    _takes_dict(value)


def _case_367(value: datetime.datetime) -> None:
    _takes_float_value(value)


def _case_368(value: datetime.datetime) -> None:
    _takes_frozenset(value)


def _case_369(value: datetime.datetime) -> None:
    _takes_int(value)


def _case_370(value: datetime.datetime) -> None:
    _takes_list(value)


def _case_371(value: datetime.datetime) -> None:
    _takes_a_path(value)


def _case_372(value: datetime.datetime) -> None:
    _takes_set(value)


def _case_373(value: datetime.datetime) -> None:
    _takes_str(value)


def _case_374(value: datetime.datetime) -> None:
    _takes_tuple(value)


def _case_375(value: datetime.date) -> None:
    _takes_a_call(value)


def _case_376(value: datetime.date) -> None:
    _takes_any_call(value)


def _case_377(value: datetime.date) -> None:
    _takes_iterable(value)


def _case_378(value: datetime.date) -> None:
    _takes_none(value)


def _case_379(value: datetime.date) -> None:
    _takes_path(value)


def _case_380(value: datetime.date) -> None:
    _takes_float(value)


def _case_381(value: datetime.date) -> None:
    _takes_index(value)


def _case_382(value: datetime.date) -> None:
    _takes_array(value)


def _case_383(value: datetime.date) -> None:
    _takes_callable_shape(value)


def _case_384(value: datetime.date) -> None:
    _takes_capable(value)


def _case_385(value: datetime.date) -> None:
    _takes_frame(value)


def _case_386(value: datetime.date) -> None:
    _takes_indexed(value)


def _case_387(value: datetime.date) -> None:
    _takes_keyed(value)


def _case_388(value: datetime.date) -> None:
    _takes_keyed_with_items(value)


def _case_389(value: datetime.date) -> None:
    _takes_keyed_with_values(value)


def _case_390(value: datetime.date) -> None:
    _takes_orderable(value)


def _case_391(value: datetime.date) -> None:
    _takes_path_like(value)


def _case_392(value: datetime.date) -> None:
    _takes_anything(value)


def _case_393(value: datetime.date) -> None:
    _takes_anything_else(value)


def _case_394(value: datetime.date) -> None:
    _takes_bool(value)


def _case_395(value: datetime.date) -> None:
    _takes_bytearray(value)


def _case_396(value: datetime.date) -> None:
    _takes_bytes(value)


def _case_397(value: datetime.date) -> None:
    _takes_complex(value)


def _case_398(value: datetime.date) -> None:
    _takes_date(value)


def _case_399(value: datetime.date) -> None:
    _takes_datetime(value)


def _case_400(value: datetime.date) -> None:
    _takes_dict(value)


def _case_401(value: datetime.date) -> None:
    _takes_float_value(value)


def _case_402(value: datetime.date) -> None:
    _takes_frozenset(value)


def _case_403(value: datetime.date) -> None:
    _takes_int(value)


def _case_404(value: datetime.date) -> None:
    _takes_list(value)


def _case_405(value: datetime.date) -> None:
    _takes_a_path(value)


def _case_406(value: datetime.date) -> None:
    _takes_set(value)


def _case_407(value: datetime.date) -> None:
    _takes_str(value)


def _case_408(value: datetime.date) -> None:
    _takes_tuple(value)


def _case_409(value: pathlib.Path) -> None:
    _takes_a_call(value)


def _case_410(value: pathlib.Path) -> None:
    _takes_any_call(value)


def _case_411(value: pathlib.Path) -> None:
    _takes_iterable(value)


def _case_412(value: pathlib.Path) -> None:
    _takes_none(value)


def _case_413(value: pathlib.Path) -> None:
    _takes_path(value)


def _case_414(value: pathlib.Path) -> None:
    _takes_float(value)


def _case_415(value: pathlib.Path) -> None:
    _takes_index(value)


def _case_416(value: pathlib.Path) -> None:
    _takes_array(value)


def _case_417(value: pathlib.Path) -> None:
    _takes_callable_shape(value)


def _case_418(value: pathlib.Path) -> None:
    _takes_capable(value)


def _case_419(value: pathlib.Path) -> None:
    _takes_frame(value)


def _case_420(value: pathlib.Path) -> None:
    _takes_indexed(value)


def _case_421(value: pathlib.Path) -> None:
    _takes_keyed(value)


def _case_422(value: pathlib.Path) -> None:
    _takes_keyed_with_items(value)


def _case_423(value: pathlib.Path) -> None:
    _takes_keyed_with_values(value)


def _case_424(value: pathlib.Path) -> None:
    _takes_orderable(value)


def _case_425(value: pathlib.Path) -> None:
    _takes_path_like(value)


def _case_426(value: pathlib.Path) -> None:
    _takes_anything(value)


def _case_427(value: pathlib.Path) -> None:
    _takes_anything_else(value)


def _case_428(value: pathlib.Path) -> None:
    _takes_bool(value)


def _case_429(value: pathlib.Path) -> None:
    _takes_bytearray(value)


def _case_430(value: pathlib.Path) -> None:
    _takes_bytes(value)


def _case_431(value: pathlib.Path) -> None:
    _takes_complex(value)


def _case_432(value: pathlib.Path) -> None:
    _takes_date(value)


def _case_433(value: pathlib.Path) -> None:
    _takes_datetime(value)


def _case_434(value: pathlib.Path) -> None:
    _takes_dict(value)


def _case_435(value: pathlib.Path) -> None:
    _takes_float_value(value)


def _case_436(value: pathlib.Path) -> None:
    _takes_frozenset(value)


def _case_437(value: pathlib.Path) -> None:
    _takes_int(value)


def _case_438(value: pathlib.Path) -> None:
    _takes_list(value)


def _case_439(value: pathlib.Path) -> None:
    _takes_a_path(value)


def _case_440(value: pathlib.Path) -> None:
    _takes_set(value)


def _case_441(value: pathlib.Path) -> None:
    _takes_str(value)


def _case_442(value: pathlib.Path) -> None:
    _takes_tuple(value)


def _case_443(value: bytes) -> None:
    _takes_a_call(value)


def _case_444(value: bytes) -> None:
    _takes_any_call(value)


def _case_445(value: bytes) -> None:
    _takes_iterable(value)


def _case_446(value: bytes) -> None:
    _takes_none(value)


def _case_447(value: bytes) -> None:
    _takes_path(value)


def _case_448(value: bytes) -> None:
    _takes_float(value)


def _case_449(value: bytes) -> None:
    _takes_index(value)


def _case_450(value: bytes) -> None:
    _takes_array(value)


def _case_451(value: bytes) -> None:
    _takes_callable_shape(value)


def _case_452(value: bytes) -> None:
    _takes_capable(value)


def _case_453(value: bytes) -> None:
    _takes_frame(value)


def _case_454(value: bytes) -> None:
    _takes_indexed(value)


def _case_455(value: bytes) -> None:
    _takes_keyed(value)


def _case_456(value: bytes) -> None:
    _takes_keyed_with_items(value)


def _case_457(value: bytes) -> None:
    _takes_keyed_with_values(value)


def _case_458(value: bytes) -> None:
    _takes_orderable(value)


def _case_459(value: bytes) -> None:
    _takes_path_like(value)


def _case_460(value: bytes) -> None:
    _takes_anything(value)


def _case_461(value: bytes) -> None:
    _takes_anything_else(value)


def _case_462(value: bytes) -> None:
    _takes_bool(value)


def _case_463(value: bytes) -> None:
    _takes_bytearray(value)


def _case_464(value: bytes) -> None:
    _takes_bytes(value)


def _case_465(value: bytes) -> None:
    _takes_complex(value)


def _case_466(value: bytes) -> None:
    _takes_date(value)


def _case_467(value: bytes) -> None:
    _takes_datetime(value)


def _case_468(value: bytes) -> None:
    _takes_dict(value)


def _case_469(value: bytes) -> None:
    _takes_float_value(value)


def _case_470(value: bytes) -> None:
    _takes_frozenset(value)


def _case_471(value: bytes) -> None:
    _takes_int(value)


def _case_472(value: bytes) -> None:
    _takes_list(value)


def _case_473(value: bytes) -> None:
    _takes_a_path(value)


def _case_474(value: bytes) -> None:
    _takes_set(value)


def _case_475(value: bytes) -> None:
    _takes_str(value)


def _case_476(value: bytes) -> None:
    _takes_tuple(value)


def _case_477(value: bytearray) -> None:
    _takes_a_call(value)


def _case_478(value: bytearray) -> None:
    _takes_any_call(value)


def _case_479(value: bytearray) -> None:
    _takes_iterable(value)


def _case_480(value: bytearray) -> None:
    _takes_none(value)


def _case_481(value: bytearray) -> None:
    _takes_path(value)


def _case_482(value: bytearray) -> None:
    _takes_float(value)


def _case_483(value: bytearray) -> None:
    _takes_index(value)


def _case_484(value: bytearray) -> None:
    _takes_array(value)


def _case_485(value: bytearray) -> None:
    _takes_callable_shape(value)


def _case_486(value: bytearray) -> None:
    _takes_capable(value)


def _case_487(value: bytearray) -> None:
    _takes_frame(value)


def _case_488(value: bytearray) -> None:
    _takes_indexed(value)


def _case_489(value: bytearray) -> None:
    _takes_keyed(value)


def _case_490(value: bytearray) -> None:
    _takes_keyed_with_items(value)


def _case_491(value: bytearray) -> None:
    _takes_keyed_with_values(value)


def _case_492(value: bytearray) -> None:
    _takes_orderable(value)


def _case_493(value: bytearray) -> None:
    _takes_path_like(value)


def _case_494(value: bytearray) -> None:
    _takes_anything(value)


def _case_495(value: bytearray) -> None:
    _takes_anything_else(value)


def _case_496(value: bytearray) -> None:
    _takes_bool(value)


def _case_497(value: bytearray) -> None:
    _takes_bytearray(value)


def _case_498(value: bytearray) -> None:
    _takes_bytes(value)


def _case_499(value: bytearray) -> None:
    _takes_complex(value)


def _case_500(value: bytearray) -> None:
    _takes_date(value)


def _case_501(value: bytearray) -> None:
    _takes_datetime(value)


def _case_502(value: bytearray) -> None:
    _takes_dict(value)


def _case_503(value: bytearray) -> None:
    _takes_float_value(value)


def _case_504(value: bytearray) -> None:
    _takes_frozenset(value)


def _case_505(value: bytearray) -> None:
    _takes_int(value)


def _case_506(value: bytearray) -> None:
    _takes_list(value)


def _case_507(value: bytearray) -> None:
    _takes_a_path(value)


def _case_508(value: bytearray) -> None:
    _takes_set(value)


def _case_509(value: bytearray) -> None:
    _takes_str(value)


def _case_510(value: bytearray) -> None:
    _takes_tuple(value)


def _case_511(value: Callable[..., int]) -> None:
    _takes_a_call(value)


def _case_512(value: Callable[..., int]) -> None:
    _takes_any_call(value)


def _case_513(value: Callable[..., int]) -> None:
    _takes_iterable(value)


def _case_514(value: Callable[..., int]) -> None:
    _takes_none(value)


def _case_515(value: Callable[..., int]) -> None:
    _takes_path(value)


def _case_516(value: Callable[..., int]) -> None:
    _takes_float(value)


def _case_517(value: Callable[..., int]) -> None:
    _takes_index(value)


def _case_518(value: Callable[..., int]) -> None:
    _takes_array(value)


def _case_519(value: Callable[..., int]) -> None:
    _takes_callable_shape(value)


def _case_520(value: Callable[..., int]) -> None:
    _takes_capable(value)


def _case_521(value: Callable[..., int]) -> None:
    _takes_frame(value)


def _case_522(value: Callable[..., int]) -> None:
    _takes_indexed(value)


def _case_523(value: Callable[..., int]) -> None:
    _takes_keyed(value)


def _case_524(value: Callable[..., int]) -> None:
    _takes_keyed_with_items(value)


def _case_525(value: Callable[..., int]) -> None:
    _takes_keyed_with_values(value)


def _case_526(value: Callable[..., int]) -> None:
    _takes_orderable(value)


def _case_527(value: Callable[..., int]) -> None:
    _takes_path_like(value)


def _case_528(value: Callable[..., int]) -> None:
    _takes_anything(value)


def _case_529(value: Callable[..., int]) -> None:
    _takes_anything_else(value)


def _case_530(value: Callable[..., int]) -> None:
    _takes_bool(value)


def _case_531(value: Callable[..., int]) -> None:
    _takes_bytearray(value)


def _case_532(value: Callable[..., int]) -> None:
    _takes_bytes(value)


def _case_533(value: Callable[..., int]) -> None:
    _takes_complex(value)


def _case_534(value: Callable[..., int]) -> None:
    _takes_date(value)


def _case_535(value: Callable[..., int]) -> None:
    _takes_datetime(value)


def _case_536(value: Callable[..., int]) -> None:
    _takes_dict(value)


def _case_537(value: Callable[..., int]) -> None:
    _takes_float_value(value)


def _case_538(value: Callable[..., int]) -> None:
    _takes_frozenset(value)


def _case_539(value: Callable[..., int]) -> None:
    _takes_int(value)


def _case_540(value: Callable[..., int]) -> None:
    _takes_list(value)


def _case_541(value: Callable[..., int]) -> None:
    _takes_a_path(value)


def _case_542(value: Callable[..., int]) -> None:
    _takes_set(value)


def _case_543(value: Callable[..., int]) -> None:
    _takes_str(value)


def _case_544(value: Callable[..., int]) -> None:
    _takes_tuple(value)


def _case_545(value: _FrameShaped) -> None:
    _takes_a_call(value)


def _case_546(value: _FrameShaped) -> None:
    _takes_any_call(value)


def _case_547(value: _FrameShaped) -> None:
    _takes_iterable(value)


def _case_548(value: _FrameShaped) -> None:
    _takes_none(value)


def _case_549(value: _FrameShaped) -> None:
    _takes_path(value)


def _case_550(value: _FrameShaped) -> None:
    _takes_float(value)


def _case_551(value: _FrameShaped) -> None:
    _takes_index(value)


def _case_552(value: _FrameShaped) -> None:
    _takes_array(value)


def _case_553(value: _FrameShaped) -> None:
    _takes_callable_shape(value)


def _case_554(value: _FrameShaped) -> None:
    _takes_capable(value)


def _case_555(value: _FrameShaped) -> None:
    _takes_frame(value)


def _case_556(value: _FrameShaped) -> None:
    _takes_indexed(value)


def _case_557(value: _FrameShaped) -> None:
    _takes_keyed(value)


def _case_558(value: _FrameShaped) -> None:
    _takes_keyed_with_items(value)


def _case_559(value: _FrameShaped) -> None:
    _takes_keyed_with_values(value)


def _case_560(value: _FrameShaped) -> None:
    _takes_orderable(value)


def _case_561(value: _FrameShaped) -> None:
    _takes_path_like(value)


def _case_562(value: _FrameShaped) -> None:
    _takes_anything(value)


def _case_563(value: _FrameShaped) -> None:
    _takes_anything_else(value)


def _case_564(value: _FrameShaped) -> None:
    _takes_bool(value)


def _case_565(value: _FrameShaped) -> None:
    _takes_bytearray(value)


def _case_566(value: _FrameShaped) -> None:
    _takes_bytes(value)


def _case_567(value: _FrameShaped) -> None:
    _takes_complex(value)


def _case_568(value: _FrameShaped) -> None:
    _takes_date(value)


def _case_569(value: _FrameShaped) -> None:
    _takes_datetime(value)


def _case_570(value: _FrameShaped) -> None:
    _takes_dict(value)


def _case_571(value: _FrameShaped) -> None:
    _takes_float_value(value)


def _case_572(value: _FrameShaped) -> None:
    _takes_frozenset(value)


def _case_573(value: _FrameShaped) -> None:
    _takes_int(value)


def _case_574(value: _FrameShaped) -> None:
    _takes_list(value)


def _case_575(value: _FrameShaped) -> None:
    _takes_a_path(value)


def _case_576(value: _FrameShaped) -> None:
    _takes_set(value)


def _case_577(value: _FrameShaped) -> None:
    _takes_str(value)


def _case_578(value: _FrameShaped) -> None:
    _takes_tuple(value)


def _case_579(value: _FrameThatWalks) -> None:
    _takes_a_call(value)


def _case_580(value: _FrameThatWalks) -> None:
    _takes_any_call(value)


def _case_581(value: _FrameThatWalks) -> None:
    _takes_iterable(value)


def _case_582(value: _FrameThatWalks) -> None:
    _takes_none(value)


def _case_583(value: _FrameThatWalks) -> None:
    _takes_path(value)


def _case_584(value: _FrameThatWalks) -> None:
    _takes_float(value)


def _case_585(value: _FrameThatWalks) -> None:
    _takes_index(value)


def _case_586(value: _FrameThatWalks) -> None:
    _takes_array(value)


def _case_587(value: _FrameThatWalks) -> None:
    _takes_callable_shape(value)


def _case_588(value: _FrameThatWalks) -> None:
    _takes_capable(value)


def _case_589(value: _FrameThatWalks) -> None:
    _takes_frame(value)


def _case_590(value: _FrameThatWalks) -> None:
    _takes_indexed(value)


def _case_591(value: _FrameThatWalks) -> None:
    _takes_keyed(value)


def _case_592(value: _FrameThatWalks) -> None:
    _takes_keyed_with_items(value)


def _case_593(value: _FrameThatWalks) -> None:
    _takes_keyed_with_values(value)


def _case_594(value: _FrameThatWalks) -> None:
    _takes_orderable(value)


def _case_595(value: _FrameThatWalks) -> None:
    _takes_path_like(value)


def _case_596(value: _FrameThatWalks) -> None:
    _takes_anything(value)


def _case_597(value: _FrameThatWalks) -> None:
    _takes_anything_else(value)


def _case_598(value: _FrameThatWalks) -> None:
    _takes_bool(value)


def _case_599(value: _FrameThatWalks) -> None:
    _takes_bytearray(value)


def _case_600(value: _FrameThatWalks) -> None:
    _takes_bytes(value)


def _case_601(value: _FrameThatWalks) -> None:
    _takes_complex(value)


def _case_602(value: _FrameThatWalks) -> None:
    _takes_date(value)


def _case_603(value: _FrameThatWalks) -> None:
    _takes_datetime(value)


def _case_604(value: _FrameThatWalks) -> None:
    _takes_dict(value)


def _case_605(value: _FrameThatWalks) -> None:
    _takes_float_value(value)


def _case_606(value: _FrameThatWalks) -> None:
    _takes_frozenset(value)


def _case_607(value: _FrameThatWalks) -> None:
    _takes_int(value)


def _case_608(value: _FrameThatWalks) -> None:
    _takes_list(value)


def _case_609(value: _FrameThatWalks) -> None:
    _takes_a_path(value)


def _case_610(value: _FrameThatWalks) -> None:
    _takes_set(value)


def _case_611(value: _FrameThatWalks) -> None:
    _takes_str(value)


def _case_612(value: _FrameThatWalks) -> None:
    _takes_tuple(value)


def _case_613(value: _FrameCarryingEverything) -> None:
    _takes_a_call(value)


def _case_614(value: _FrameCarryingEverything) -> None:
    _takes_any_call(value)


def _case_615(value: _FrameCarryingEverything) -> None:
    _takes_iterable(value)


def _case_616(value: _FrameCarryingEverything) -> None:
    _takes_none(value)


def _case_617(value: _FrameCarryingEverything) -> None:
    _takes_path(value)


def _case_618(value: _FrameCarryingEverything) -> None:
    _takes_float(value)


def _case_619(value: _FrameCarryingEverything) -> None:
    _takes_index(value)


def _case_620(value: _FrameCarryingEverything) -> None:
    _takes_array(value)


def _case_621(value: _FrameCarryingEverything) -> None:
    _takes_callable_shape(value)


def _case_622(value: _FrameCarryingEverything) -> None:
    _takes_capable(value)


def _case_623(value: _FrameCarryingEverything) -> None:
    _takes_frame(value)


def _case_624(value: _FrameCarryingEverything) -> None:
    _takes_indexed(value)


def _case_625(value: _FrameCarryingEverything) -> None:
    _takes_keyed(value)


def _case_626(value: _FrameCarryingEverything) -> None:
    _takes_keyed_with_items(value)


def _case_627(value: _FrameCarryingEverything) -> None:
    _takes_keyed_with_values(value)


def _case_628(value: _FrameCarryingEverything) -> None:
    _takes_orderable(value)


def _case_629(value: _FrameCarryingEverything) -> None:
    _takes_path_like(value)


def _case_630(value: _FrameCarryingEverything) -> None:
    _takes_anything(value)


def _case_631(value: _FrameCarryingEverything) -> None:
    _takes_anything_else(value)


def _case_632(value: _FrameCarryingEverything) -> None:
    _takes_bool(value)


def _case_633(value: _FrameCarryingEverything) -> None:
    _takes_bytearray(value)


def _case_634(value: _FrameCarryingEverything) -> None:
    _takes_bytes(value)


def _case_635(value: _FrameCarryingEverything) -> None:
    _takes_complex(value)


def _case_636(value: _FrameCarryingEverything) -> None:
    _takes_date(value)


def _case_637(value: _FrameCarryingEverything) -> None:
    _takes_datetime(value)


def _case_638(value: _FrameCarryingEverything) -> None:
    _takes_dict(value)


def _case_639(value: _FrameCarryingEverything) -> None:
    _takes_float_value(value)


def _case_640(value: _FrameCarryingEverything) -> None:
    _takes_frozenset(value)


def _case_641(value: _FrameCarryingEverything) -> None:
    _takes_int(value)


def _case_642(value: _FrameCarryingEverything) -> None:
    _takes_list(value)


def _case_643(value: _FrameCarryingEverything) -> None:
    _takes_a_path(value)


def _case_644(value: _FrameCarryingEverything) -> None:
    _takes_set(value)


def _case_645(value: _FrameCarryingEverything) -> None:
    _takes_str(value)


def _case_646(value: _FrameCarryingEverything) -> None:
    _takes_tuple(value)


def _case_647(value: _ArrayShaped) -> None:
    _takes_a_call(value)


def _case_648(value: _ArrayShaped) -> None:
    _takes_any_call(value)


def _case_649(value: _ArrayShaped) -> None:
    _takes_iterable(value)


def _case_650(value: _ArrayShaped) -> None:
    _takes_none(value)


def _case_651(value: _ArrayShaped) -> None:
    _takes_path(value)


def _case_652(value: _ArrayShaped) -> None:
    _takes_float(value)


def _case_653(value: _ArrayShaped) -> None:
    _takes_index(value)


def _case_654(value: _ArrayShaped) -> None:
    _takes_array(value)


def _case_655(value: _ArrayShaped) -> None:
    _takes_callable_shape(value)


def _case_656(value: _ArrayShaped) -> None:
    _takes_capable(value)


def _case_657(value: _ArrayShaped) -> None:
    _takes_frame(value)


def _case_658(value: _ArrayShaped) -> None:
    _takes_indexed(value)


def _case_659(value: _ArrayShaped) -> None:
    _takes_keyed(value)


def _case_660(value: _ArrayShaped) -> None:
    _takes_keyed_with_items(value)


def _case_661(value: _ArrayShaped) -> None:
    _takes_keyed_with_values(value)


def _case_662(value: _ArrayShaped) -> None:
    _takes_orderable(value)


def _case_663(value: _ArrayShaped) -> None:
    _takes_path_like(value)


def _case_664(value: _ArrayShaped) -> None:
    _takes_anything(value)


def _case_665(value: _ArrayShaped) -> None:
    _takes_anything_else(value)


def _case_666(value: _ArrayShaped) -> None:
    _takes_bool(value)


def _case_667(value: _ArrayShaped) -> None:
    _takes_bytearray(value)


def _case_668(value: _ArrayShaped) -> None:
    _takes_bytes(value)


def _case_669(value: _ArrayShaped) -> None:
    _takes_complex(value)


def _case_670(value: _ArrayShaped) -> None:
    _takes_date(value)


def _case_671(value: _ArrayShaped) -> None:
    _takes_datetime(value)


def _case_672(value: _ArrayShaped) -> None:
    _takes_dict(value)


def _case_673(value: _ArrayShaped) -> None:
    _takes_float_value(value)


def _case_674(value: _ArrayShaped) -> None:
    _takes_frozenset(value)


def _case_675(value: _ArrayShaped) -> None:
    _takes_int(value)


def _case_676(value: _ArrayShaped) -> None:
    _takes_list(value)


def _case_677(value: _ArrayShaped) -> None:
    _takes_a_path(value)


def _case_678(value: _ArrayShaped) -> None:
    _takes_set(value)


def _case_679(value: _ArrayShaped) -> None:
    _takes_str(value)


def _case_680(value: _ArrayShaped) -> None:
    _takes_tuple(value)


def _case_681(value: _ArrayThatWalks) -> None:
    _takes_a_call(value)


def _case_682(value: _ArrayThatWalks) -> None:
    _takes_any_call(value)


def _case_683(value: _ArrayThatWalks) -> None:
    _takes_iterable(value)


def _case_684(value: _ArrayThatWalks) -> None:
    _takes_none(value)


def _case_685(value: _ArrayThatWalks) -> None:
    _takes_path(value)


def _case_686(value: _ArrayThatWalks) -> None:
    _takes_float(value)


def _case_687(value: _ArrayThatWalks) -> None:
    _takes_index(value)


def _case_688(value: _ArrayThatWalks) -> None:
    _takes_array(value)


def _case_689(value: _ArrayThatWalks) -> None:
    _takes_callable_shape(value)


def _case_690(value: _ArrayThatWalks) -> None:
    _takes_capable(value)


def _case_691(value: _ArrayThatWalks) -> None:
    _takes_frame(value)


def _case_692(value: _ArrayThatWalks) -> None:
    _takes_indexed(value)


def _case_693(value: _ArrayThatWalks) -> None:
    _takes_keyed(value)


def _case_694(value: _ArrayThatWalks) -> None:
    _takes_keyed_with_items(value)


def _case_695(value: _ArrayThatWalks) -> None:
    _takes_keyed_with_values(value)


def _case_696(value: _ArrayThatWalks) -> None:
    _takes_orderable(value)


def _case_697(value: _ArrayThatWalks) -> None:
    _takes_path_like(value)


def _case_698(value: _ArrayThatWalks) -> None:
    _takes_anything(value)


def _case_699(value: _ArrayThatWalks) -> None:
    _takes_anything_else(value)


def _case_700(value: _ArrayThatWalks) -> None:
    _takes_bool(value)


def _case_701(value: _ArrayThatWalks) -> None:
    _takes_bytearray(value)


def _case_702(value: _ArrayThatWalks) -> None:
    _takes_bytes(value)


def _case_703(value: _ArrayThatWalks) -> None:
    _takes_complex(value)


def _case_704(value: _ArrayThatWalks) -> None:
    _takes_date(value)


def _case_705(value: _ArrayThatWalks) -> None:
    _takes_datetime(value)


def _case_706(value: _ArrayThatWalks) -> None:
    _takes_dict(value)


def _case_707(value: _ArrayThatWalks) -> None:
    _takes_float_value(value)


def _case_708(value: _ArrayThatWalks) -> None:
    _takes_frozenset(value)


def _case_709(value: _ArrayThatWalks) -> None:
    _takes_int(value)


def _case_710(value: _ArrayThatWalks) -> None:
    _takes_list(value)


def _case_711(value: _ArrayThatWalks) -> None:
    _takes_a_path(value)


def _case_712(value: _ArrayThatWalks) -> None:
    _takes_set(value)


def _case_713(value: _ArrayThatWalks) -> None:
    _takes_str(value)


def _case_714(value: _ArrayThatWalks) -> None:
    _takes_tuple(value)


def _case_715(value: _ArrayCarryingEverything) -> None:
    _takes_a_call(value)


def _case_716(value: _ArrayCarryingEverything) -> None:
    _takes_any_call(value)


def _case_717(value: _ArrayCarryingEverything) -> None:
    _takes_iterable(value)


def _case_718(value: _ArrayCarryingEverything) -> None:
    _takes_none(value)


def _case_719(value: _ArrayCarryingEverything) -> None:
    _takes_path(value)


def _case_720(value: _ArrayCarryingEverything) -> None:
    _takes_float(value)


def _case_721(value: _ArrayCarryingEverything) -> None:
    _takes_index(value)


def _case_722(value: _ArrayCarryingEverything) -> None:
    _takes_array(value)


def _case_723(value: _ArrayCarryingEverything) -> None:
    _takes_callable_shape(value)


def _case_724(value: _ArrayCarryingEverything) -> None:
    _takes_capable(value)


def _case_725(value: _ArrayCarryingEverything) -> None:
    _takes_frame(value)


def _case_726(value: _ArrayCarryingEverything) -> None:
    _takes_indexed(value)


def _case_727(value: _ArrayCarryingEverything) -> None:
    _takes_keyed(value)


def _case_728(value: _ArrayCarryingEverything) -> None:
    _takes_keyed_with_items(value)


def _case_729(value: _ArrayCarryingEverything) -> None:
    _takes_keyed_with_values(value)


def _case_730(value: _ArrayCarryingEverything) -> None:
    _takes_orderable(value)


def _case_731(value: _ArrayCarryingEverything) -> None:
    _takes_path_like(value)


def _case_732(value: _ArrayCarryingEverything) -> None:
    _takes_anything(value)


def _case_733(value: _ArrayCarryingEverything) -> None:
    _takes_anything_else(value)


def _case_734(value: _ArrayCarryingEverything) -> None:
    _takes_bool(value)


def _case_735(value: _ArrayCarryingEverything) -> None:
    _takes_bytearray(value)


def _case_736(value: _ArrayCarryingEverything) -> None:
    _takes_bytes(value)


def _case_737(value: _ArrayCarryingEverything) -> None:
    _takes_complex(value)


def _case_738(value: _ArrayCarryingEverything) -> None:
    _takes_date(value)


def _case_739(value: _ArrayCarryingEverything) -> None:
    _takes_datetime(value)


def _case_740(value: _ArrayCarryingEverything) -> None:
    _takes_dict(value)


def _case_741(value: _ArrayCarryingEverything) -> None:
    _takes_float_value(value)


def _case_742(value: _ArrayCarryingEverything) -> None:
    _takes_frozenset(value)


def _case_743(value: _ArrayCarryingEverything) -> None:
    _takes_int(value)


def _case_744(value: _ArrayCarryingEverything) -> None:
    _takes_list(value)


def _case_745(value: _ArrayCarryingEverything) -> None:
    _takes_a_path(value)


def _case_746(value: _ArrayCarryingEverything) -> None:
    _takes_set(value)


def _case_747(value: _ArrayCarryingEverything) -> None:
    _takes_str(value)


def _case_748(value: _ArrayCarryingEverything) -> None:
    _takes_tuple(value)


def _case_749(value: object) -> None:
    _takes_a_call(value)


def _case_750(value: object) -> None:
    _takes_any_call(value)


def _case_751(value: object) -> None:
    _takes_iterable(value)


def _case_752(value: object) -> None:
    _takes_none(value)


def _case_753(value: object) -> None:
    _takes_path(value)


def _case_754(value: object) -> None:
    _takes_float(value)


def _case_755(value: object) -> None:
    _takes_index(value)


def _case_756(value: object) -> None:
    _takes_array(value)


def _case_757(value: object) -> None:
    _takes_callable_shape(value)


def _case_758(value: object) -> None:
    _takes_capable(value)


def _case_759(value: object) -> None:
    _takes_frame(value)


def _case_760(value: object) -> None:
    _takes_indexed(value)


def _case_761(value: object) -> None:
    _takes_keyed(value)


def _case_762(value: object) -> None:
    _takes_keyed_with_items(value)


def _case_763(value: object) -> None:
    _takes_keyed_with_values(value)


def _case_764(value: object) -> None:
    _takes_orderable(value)


def _case_765(value: object) -> None:
    _takes_path_like(value)


def _case_766(value: object) -> None:
    _takes_anything(value)


def _case_767(value: object) -> None:
    _takes_anything_else(value)


def _case_768(value: object) -> None:
    _takes_bool(value)


def _case_769(value: object) -> None:
    _takes_bytearray(value)


def _case_770(value: object) -> None:
    _takes_bytes(value)


def _case_771(value: object) -> None:
    _takes_complex(value)


def _case_772(value: object) -> None:
    _takes_date(value)


def _case_773(value: object) -> None:
    _takes_datetime(value)


def _case_774(value: object) -> None:
    _takes_dict(value)


def _case_775(value: object) -> None:
    _takes_float_value(value)


def _case_776(value: object) -> None:
    _takes_frozenset(value)


def _case_777(value: object) -> None:
    _takes_int(value)


def _case_778(value: object) -> None:
    _takes_list(value)


def _case_779(value: object) -> None:
    _takes_a_path(value)


def _case_780(value: object) -> None:
    _takes_set(value)


def _case_781(value: object) -> None:
    _takes_str(value)


def _case_782(value: object) -> None:
    _takes_tuple(value)
