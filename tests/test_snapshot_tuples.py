"""Tuples round-trip through snapshots, and a registered serializer is asked before the codec for every value.

A tuple used to be written as an array and read back as a list, so a snapshot of `mock.method_calls` failed on
the run after it was recorded (assertpy#121).  It is tagged now.  The registry promised to be asked before the
built-ins, subclasses included, and was never asked for a subclass of a type ``json`` writes itself.
"""

import abc
import contextlib
import datetime
import enum
import json
import math
import pathlib
import shutil
import sys
import tempfile
import types
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy import (
    AssertionFailure,
    SnapshotCreatedWarning,
    SnapshotUpdatedWarning,
    assert_that,
    register_snapshot_serializer,
)
from assertpy._snapshot_codec import _decode, _encode, _load, _save
from tests.optional import needs
from tests.snapshot_types_2_35 import Box, Colour, Future, Holder, Nested, Point, Shaped

_FILES_2_35 = pathlib.Path(__file__).with_name("snapshot_files_2_35")


class _Mixed(enum.Enum):
    PAIR = (1, [2, 3])


def _round_trip(value, tmp_path=None):
    """*value* written to a snapshot file and read back, as `snapshot()` writes and reads it."""
    with contextlib.ExitStack() as stack:
        folder = pathlib.Path(tmp_path or stack.enter_context(_scratch()))
        _save(str(folder / "snap-round-trip.json"), value, keyed=False)
        return _load(str(folder / "snap-round-trip.json"))


@contextlib.contextmanager
def _scratch():
    with tempfile.TemporaryDirectory() as folder:
        yield folder


def _form(value):
    """A value with the kind of each container spelled out, so that a list read where a tuple was written differs
    although the two compare equal nowhere else either, and a set's members are compared as a set."""
    if isinstance(value, tuple):
        return ("tuple", *map(_form, value))
    if isinstance(value, list):
        return ("list", *map(_form, value))
    if isinstance(value, dict):
        return ("dict", frozenset((_form(key), _form(item)) for key, item in value.items()))
    if isinstance(value, set):
        return ("set", frozenset(map(_form, value)))
    return (type(value).__name__, value)


_scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=4)
_hashables = st.recursive(_scalars, lambda inner: st.tuples(inner, inner) | st.tuples(inner), max_leaves=6)
_values = st.recursive(
    _scalars,
    lambda inner: (
        st.lists(inner, max_size=3)
        | st.lists(inner, max_size=3).map(tuple)
        | st.dictionaries(st.text(max_size=4), inner, max_size=3)
        | st.dictionaries(_hashables, inner, max_size=3)
        | st.sets(_hashables, max_size=3)
    ),
    max_leaves=12,
)


@settings(deadline=None)
@given(value=_values)
def test_every_container_comes_back_the_kind_it_was(value):
    back = _round_trip(value)
    assert_that(back).is_equal_to(value)
    assert_that(_form(back)).is_equal_to(_form(value))


class TestATupleComesBackATuple:
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param((1, 2), id="a tuple"),
            pytest.param([(1, (2, 3)), {"k": (4,)}, ()], id="nested"),
            pytest.param({(1, 2): (3, [4, (5,)])}, id="a tuple key and a tuple value"),
            pytest.param({(1, 2), (3, (4,))}, id="a set of tuples"),
            pytest.param(Holder((1, (2, 3))), id="an attribute holding a tuple"),
        ],
    )
    def test_through_a_snapshot_written_and_read_again(self, tmp_path, value):
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(value).snapshot(id="tuples", path=str(tmp_path))
        assert_that(value).snapshot(id="tuples", path=str(tmp_path))
        assert_that(_form(_load(str(next(tmp_path.glob("snap-*.json")))))).is_equal_to(_form(value))

    def test_mock_method_calls_compare_on_the_run_after_they_were_recorded(self, tmp_path):
        """The case of assertpy#121: `call.write('x')` is a tuple subclass, and was read back as a list."""
        stdout = mock.MagicMock()
        stdout.write("Something")
        stdout.write("\n")
        with pytest.warns(SnapshotCreatedWarning):
            assert_that(stdout.method_calls).snapshot(id="calls", path=str(tmp_path))
        assert_that(stdout.method_calls).snapshot(id="calls", path=str(tmp_path))
        assert_that(_load(str(tmp_path / "snap-calls.json"))).is_equal_to(
            [("write", ("Something",), {}), ("write", ("\n",), {})]
        )

    def test_a_subclass_comes_back_a_plain_tuple_equal_to_it(self):
        back = _round_trip(Point(1, 2))
        assert_that(type(back)).is_same_as(tuple)
        assert_that(back).is_equal_to(Point(1, 2))

    def test_an_enum_value_holding_a_list_comes_back(self):
        """Read back through `_hashable`, the list inside became a tuple and the member was not found."""
        try:
            back = _round_trip(_Mixed.PAIR)
        except ValueError as refused:
            back = refused
        assert_that(back).is_same_as(_Mixed.PAIR)

    def test_a_pydantic_model_holding_a_tuple_compares_after_reading(self, tmp_path):
        """Its `==` compares the field, a list read where the tuple was failed the run after it was recorded."""
        pydantic = needs("pydantic")
        model = pydantic.create_model("Paired", pair=(tuple[int, int], ...), __module__=__name__)
        globals()["Paired"] = model
        try:
            value = model(pair=(1, 2))
            with pytest.warns(SnapshotCreatedWarning):
                assert_that(value).snapshot(id="model", path=str(tmp_path))
            assert_that(value).snapshot(id="model", path=str(tmp_path))
        finally:
            del globals()["Paired"]


class TestTheRegistryIsAskedFirst:
    def test_for_a_tuple_list_dict_and_str_subclass_wherever_it_stands(self):
        class Bag(list):
            pass

        class Table(dict):
            pass

        class Code(str):
            pass

        register_snapshot_serializer(Point, lambda point: [point.x, point.y], lambda pair: Point(*pair), tag="point")
        register_snapshot_serializer(Bag, list, Bag, tag="bag")
        register_snapshot_serializer(Table, lambda table: sorted(table.items()), lambda items: Table(items), tag="t")
        register_snapshot_serializer(Code, str, Code, tag="code")
        value = {
            "point": Point(1, 2),
            "in a list": [Point(3, 4)],
            "in a set": {Point(5, 6)},
            "as a key": {Point(7, 8): "k"},
            "bag": Bag([1, [2, 3]]),
            "table": Table(a=1),
            "codes": {Code("c"): Code("v")},
        }
        back = _round_trip(value)
        assert_that(back).is_equal_to(value)
        assert_that(type(back["point"])).is_same_as(Point)
        assert_that(type(back["in a list"][0])).is_same_as(Point)
        assert_that(type(next(iter(back["in a set"])))).is_same_as(Point)
        assert_that(type(next(iter(back["as a key"])))).is_same_as(Point)
        assert_that(type(back["bag"])).is_same_as(Bag)
        assert_that(type(back["table"])).is_same_as(Table)
        key, item = next(iter(back["codes"].items()))
        assert_that((type(key), type(item))).is_equal_to((Code, Code))

    def test_a_serializer_for_a_type_json_writes_itself_takes_every_value_of_it(self):
        """Registered for `int`, it is asked for each int, and the ints of the codec's own records stay as they are."""
        register_snapshot_serializer(int, lambda number: str(number), lambda text: int(text) * 10, tag="ten")
        assert_that(_round_trip({"a": [1, (2,)]})).is_equal_to({"a": [10, (20,)]})

    def test_a_serializer_for_dict_or_list_takes_every_plain_one(self):
        register_snapshot_serializer(list, lambda items: len(items), lambda size: ["item"] * size, tag="list")
        assert_that(_round_trip({"a": [1, 2], "b": "s"})).is_equal_to({"a": ["item", "item"], "b": "s"})
        register_snapshot_serializer(
            dict, lambda mapping: sorted(mapping), lambda keys: dict.fromkeys(keys), tag="dict"
        )
        assert_that(_round_trip(({"k": 1},))).is_equal_to(({"k": None},))

    def test_the_last_registration_wins(self):
        register_snapshot_serializer(Point, lambda point: [point.x], lambda pair: ("first", *pair), tag="p1")
        register_snapshot_serializer(Point, lambda point: [point.y], lambda pair: ("second", *pair), tag="p2")
        assert_that(_round_trip(Point(1, 2))).is_equal_to(("second", 2))

    def test_the_file_itself_never_reaches_a_serializer(self, tmp_path):
        """A file holding several snapshots maps each line to its value, and that mapping is no value of the user's:
        a serializer registered for `dict` or `object` would have swallowed it."""
        register_snapshot_serializer(dict, lambda table: sorted(table.items()), lambda items: dict(items), tag="d")
        value = {"b": 1, "a": [2]}
        for creating in (True, False):
            with pytest.warns(SnapshotCreatedWarning) if creating else contextlib.nullcontext():
                assert_that(value).snapshot(path=str(tmp_path))
            with pytest.warns(SnapshotCreatedWarning) if creating else contextlib.nullcontext():
                assert_that(value).matches_contract_snapshot(path=str(tmp_path))
        for written in tmp_path.glob("snap-*.json"):
            stored = json.loads(written.read_text(encoding="utf-8"))
            assert_that(all(key.isdigit() for key in stored)).described_as(written.name).is_true()

    def test_what_a_serializer_returns_is_read_back_as_it_always_was(self):
        """Its `decode` is handed what it was handed before tuples were tagged: a tuple it returned is an array,
        and a dict shaped like the tuple tag is that dict."""
        handed = []

        def keep(data):
            handed.append(data)
            return Box(data)

        register_snapshot_serializer(Box, lambda box: box.content, keep, tag="box")
        _round_trip(Box((1, 2)))
        _round_trip(Box({"__type__": "tuple", "__data__": [1, 2]}))
        _round_trip(Box({"when": datetime.date(2026, 11, 5)}))
        assert_that(handed).is_equal_to(
            [[1, 2], {"__type__": "tuple", "__data__": [1, 2]}, {"when": datetime.date(2026, 11, 5)}]
        )


class _Level(enum.IntEnum):
    HIGH = 2


_RICH_HANDED = {
    "colour": Colour.RED,
    "holder": Holder({"t": [1, 2], 1: "a"}),
    "marker": {"__type__": "tuple", "__data__": [5]},
    "point": [3, 4],
    "set": {(1, 2)},
    "tuple": [6, 7],
    "when": datetime.datetime(2026, 11, 5, 12, 0),
    "numbers": {"2": "two", "10": "ten"},
}
"""What 2.35.0 handed the serializer's `decode` when it read `snap-custom-rich-payload.json` back."""


class TestWhatASerializerReturnsReadsAsItDid:
    """A serializer's payload goes through the codec as every value did before tuples were tagged, both ways."""

    @pytest.fixture
    def handed(self):
        received = []

        def keep(data):
            received.append(data)
            return Box(data)

        register_snapshot_serializer(Point, lambda point: [point.x, point.y], lambda pair: Point(*pair), tag="point")
        register_snapshot_serializer(Box, lambda box: box.content, keep, tag="rich")
        return received

    def test_a_file_the_last_release_wrote(self, handed):
        _load(str(_FILES_2_35 / "snap-custom-rich-payload.json"))
        assert_that(handed).is_equal_to([_RICH_HANDED])
        # the keys of a dict in it reach `decode` in the order 2.35.0 wrote them, ints sorted before turned to text
        assert_that(list(handed[0]["numbers"])).is_equal_to(["2", "10"])

    def test_one_written_now(self, handed, tmp_path):
        rich = {
            "set": {(1, 2)},
            "when": datetime.datetime(2026, 11, 5, 12, 0),
            "colour": Colour.RED,
            "holder": Holder({1: "a", "t": (1, 2)}),
            "point": Point(3, 4),
            "marker": {"__type__": "tuple", "__data__": [5]},
            "tuple": (6, 7),
            "numbers": {10: "ten", 2: "two"},
        }
        _round_trip(Box(rich), tmp_path)
        assert_that(handed).is_equal_to([_RICH_HANDED])
        assert_that(list(handed[0]["numbers"])).is_equal_to(["2", "10"])
        written = (tmp_path / "snap-round-trip.json").read_bytes().replace(b"\r\n", b"\n")
        assert_that(written).is_equal_to((_FILES_2_35 / "snap-custom-rich-payload.json").read_bytes())

    def test_a_class_or_a_tag_this_run_does_not_know_is_handed_on_as_written(self, handed):
        unknown = {
            "enum": {"__type__": "enum", "__class__": "Gone", "__module__": "no.such.module", "__data__": 1},
            "instance": {"__type__": "instance", "__class__": "Gone", "__module__": "no.such.module", "__data__": {}},
            "custom": {"__type__": "custom", "__tag__": "nobody", "__data__": [1]},
        }
        _decode({"__type__": "custom", "__tag__": "rich", "__data__": unknown})
        assert_that(handed).is_equal_to([unknown])

    def test_an_enum_value_no_member_holds_is_refused_as_it_was(self, handed):
        wrong = {"__type__": "enum", "__class__": "Colour", "__module__": Colour.__module__, "__data__": "pink"}
        try:
            _decode({"__type__": "custom", "__tag__": "rich", "__data__": {"colour": wrong}})
        except ValueError as refused:
            assert_that(str(refused)).contains("pink")
        else:
            pytest.fail("an enum value no member holds was read")

    def test_a_cycle_inside_it_is_named(self, handed):
        looped: list = []
        looped.append(looped)
        try:
            _encode(Box(Holder(looped)))
        except (ValueError, RecursionError) as refused:
            raised = refused
        assert_that(type(raised)).is_same_as(ValueError)
        assert_that(str(raised)).contains("circular reference")

    def test_a_tuple_key_a_registered_value_and_a_value_it_cannot_write_inside_it(self, handed):
        class Mark:
            def __init__(self, name):
                self.name = name

            def __eq__(self, other):
                return type(other) is Mark and other.name == self.name

            __hash__ = None

        register_snapshot_serializer(Mark, lambda mark: mark.name, Mark, tag="mark")
        _round_trip(Box({"keyed": Holder({(1, 2): "a"}), "mark": Mark("m")}))
        assert_that(handed).is_equal_to([{"keyed": Holder({(1, 2): "a"}), "mark": Mark("m")}])
        try:
            _encode(Box({"opaque": object()}))
        except TypeError as refused:
            assert_that(str(refused)).contains("is not JSON serializable")
        else:
            pytest.fail("a value the codec cannot write was written")


def test_a_subclass_of_a_type_json_writes_itself_and_nobody_registered_is_written_as_it():
    assert_that(_round_trip(_Level.HIGH)).is_equal_to(2)


class TestAFileTheLastReleaseWrote:
    """Files assertpy 2.35.0 from PyPI wrote (`snapshot_types_2_35.py` holds the types), read as it read them."""

    @pytest.fixture(autouse=True)
    def _serializers(self):
        register_snapshot_serializer(Point, lambda point: [point.x, point.y], lambda pair: Point(*pair), tag="point")
        register_snapshot_serializer(Box, lambda box: (box.content, "boxed"), lambda pair: Box(pair[0]), tag="box")

    @pytest.mark.parametrize(
        ("name", "read"),
        [
            ("tuple", [1, 2]),
            ("nested", {"a": [1, [2, [3]]]}),
            ("tuple-keys", {(1, 2): "x", (3, (4, 5)): "y"}),
            ("set-of-tuples", {(1, 2), (3, (4,))}),
            ("enum-tuple", Colour.RED),
            ("instance-tuple", Holder([1, 2])),
            ("datetime", datetime.datetime(2026, 11, 5, 12, 30, 1)),
            # 2.35.0 never asked the serializer of a tuple subclass, and wrote the point as an array
            ("registered-namedtuple", [1, 2]),
            ("custom-tuple-payload", Box("c")),
            ("keyed", {"12": [1, 2], "13": "x"}),
            # 2.35.0 wrote an enum's value raw: one dict in it is shaped like the tuple tag, another like records
            ("enum-shaped-tagged", Shaped.TAGGED),
            ("enum-shaped-pair", Shaped.PAIR),
            ("enum-nested-records", Nested.ONLY),
        ],
    )
    def test_reads_as_it_did(self, name, read):
        back = _load(str(_FILES_2_35 / f"snap-{name}.json"))
        assert_that(back).is_equal_to(read)
        assert_that(_form(back)).is_equal_to(_form(read))

    def test_a_tuple_recorded_then_still_fails_until_it_is_rewritten(self, tmp_path, monkeypatch):
        shutil.copy(_FILES_2_35 / "snap-tuple.json", tmp_path / "snap-tuple.json")
        assert_that([1, 2]).snapshot(id="tuple", path=str(tmp_path))
        with pytest.raises(AssertionFailure):
            assert_that((1, 2)).snapshot(id="tuple", path=str(tmp_path))
        monkeypatch.setenv("ASSERTPY_SNAPSHOT_UPDATE", "1")
        with pytest.warns(SnapshotUpdatedWarning):
            assert_that((1, 2)).snapshot(id="tuple", path=str(tmp_path))
        monkeypatch.delenv("ASSERTPY_SNAPSHOT_UPDATE")
        assert_that(json.loads((tmp_path / "snap-tuple.json").read_text(encoding="utf-8"))).is_equal_to(
            {"__type__": "tuple", "__data__": [1, 2]}
        )
        assert_that((1, 2)).snapshot(id="tuple", path=str(tmp_path))
        with pytest.raises(AssertionFailure):
            assert_that([1, 2]).snapshot(id="tuple", path=str(tmp_path))

    def test_an_enum_whose_value_carries_the_codecs_markers_reads_as_it_did(self):
        # 2.35.0 wrote an enum's value raw, so a dict in it holding the markers is no record of the codec's
        try:
            back = _load(str(_FILES_2_35 / "snap-enum-marker-value.json"))
        except ValueError as refused:
            back = refused
        assert_that(back).is_same_as(Future.LATER)

    def test_a_file_written_now_stays_byte_for_byte_where_it_holds_no_tuple(self, tmp_path):
        enums = ("enum-tuple", "enum-marker-value", "enum-shaped-tagged", "enum-shaped-pair", "enum-nested-records")
        for name in ("tuple-keys", "set-of-tuples", "datetime", "keyed", "registered-namedtuple", *enums):
            source = _FILES_2_35 / f"snap-{name}.json"
            target = tmp_path / source.name
            _save(str(target), _load(str(source)), keyed=name == "keyed")
            written = target.read_bytes().replace(b"\r\n", b"\n")
            assert_that(written).described_as(name).is_equal_to(source.read_bytes())


def test_a_nan_and_an_infinity_still_round_trip():
    back = _round_trip((math.nan, math.inf, [-math.inf]))
    assert_that(_form(back[1:])).is_equal_to(_form((math.inf, [-math.inf])))
    assert_that(type(back)).is_same_as(tuple)
    assert_that(math.isnan(back[0])).is_true()


class _Twins(enum.Enum):
    """Two members written alike, a tuple holding a list and a list holding a tuple, that no lookup tells apart."""

    TUPLE = (1, [2])
    LIST = [1, (2,)]  # noqa: RUF012  # an enum member, not a class attribute


def test_an_enum_member_written_like_another_is_refused_rather_than_guessed():
    for member in _Twins:
        try:
            back = _round_trip(member)
        except ValueError as refused:
            back = refused
        assert_that(type(back)).described_as(member.name).is_same_as(ValueError)


class _Unwritable(enum.Enum):
    """A member whose value cannot be written at all, beside one only the written form finds."""

    PAIR = (1, [2])
    OPAQUE = object()


def test_a_member_that_cannot_be_written_is_passed_over_when_the_written_form_is_sought():
    assert_that(_round_trip(_Unwritable.PAIR)).is_same_as(_Unwritable.PAIR)


class _Numbered(enum.Enum):
    """A member whose value has int keys: the file holds them as text, sorted as ints."""

    TWO_TEN = {2: "two", 10: "ten"}  # noqa: RUF012  # an enum member, not a class attribute


def test_a_member_whose_value_has_int_keys_is_found_by_its_written_form():
    try:
        back = _round_trip(_Numbered.TWO_TEN)
    except ValueError as refused:
        back = refused
    assert_that(back).is_same_as(_Numbered.TWO_TEN)


class _Hooked(abc.ABC):
    """A class whose subclass hook refuses to answer for a string."""

    @classmethod
    def __subclasshook__(cls, subclass):
        if subclass is str:
            raise TypeError("asked about str")
        return NotImplemented

    @abc.abstractmethod
    def kind(self): ...


class _Concrete(_Hooked):
    def kind(self):
        return "concrete"


def test_a_subclass_hook_that_raises_for_a_type_the_value_does_not_hold():
    register_snapshot_serializer(_Hooked, lambda _: "it", lambda _: _Concrete, tag="hooked")
    try:
        back = _round_trip([1, _Concrete(), None])
    except TypeError as refused:
        back = refused
    assert_that(back).is_equal_to([1, _Concrete, None])


class _Picky(tuple):
    """A tuple subclass whose equality asks for its own class: read back as a plain tuple, it compares unequal."""

    __slots__ = ()

    def __eq__(self, other):
        return type(other) is _Picky and tuple.__eq__(self, other)

    __hash__ = tuple.__hash__


def test_a_tuple_subclass_that_compares_by_class_needs_a_serializer():
    assert_that(_round_trip(_Picky((1, 2))) == _Picky((1, 2))).is_false()
    register_snapshot_serializer(_Picky, list, _Picky, tag="picky")
    assert_that(_round_trip(_Picky((1, 2))) == _Picky((1, 2))).is_true()


class _Above(type):
    def __instancecheck__(cls, instance):
        return type(instance) is int and instance > 5


class _BigNumber(metaclass=_Above):
    pass


class _Unhashable(type):
    __hash__ = None


class _Odd(metaclass=_Unhashable):
    def __eq__(self, other):
        return type(other) is _Odd

    __hash__ = None


class _NoSubclassCheck(type):
    def __subclasscheck__(cls, subclass):
        raise TypeError("asked of instances only")


class _Instances(metaclass=_NoSubclassCheck):
    pass


class TestTheRegistryIsAskedAsIsinstanceAsks:
    def test_a_class_that_decides_by_instance_takes_the_values_it_says_it_holds(self):
        register_snapshot_serializer(_BigNumber, lambda number: str(number), lambda text: int(text) + 1, tag="big")
        try:
            back = _round_trip([3, 7, None, "a", 1.5, True])
        except TypeError as refused:
            back = refused
        assert_that(back).is_equal_to([3, 8, None, "a", 1.5, True])

    def test_a_class_that_answers_isinstance_but_refuses_issubclass(self):
        register_snapshot_serializer(_Instances, lambda _: "it", lambda _: _Instances, tag="instances")
        try:
            back = _round_trip([1, _Instances(), "a"])
        except TypeError as refused:
            back = refused
        assert_that(back).is_equal_to([1, _Instances, "a"])

    def test_a_class_whose_class_cannot_hash_is_written(self):
        register_snapshot_serializer(_Odd, lambda odd: "odd", lambda text: _Odd(), tag="odd")
        try:
            back = _round_trip([_Odd(), {"a": _Odd()}])
        except TypeError as refused:
            back = refused
        assert_that(back).is_equal_to([_Odd(), {"a": _Odd()}])


def test_a_serializer_inside_a_record_is_read_before_the_records_class_is_looked_up():
    """2.35.0 read from the bottom up, so a ``decode`` inside an instance or an enum ran before its class was sought."""
    module = types.ModuleType("assertpy_test_late_module")

    class Late:
        def __init__(self, inner):
            self.inner = inner

    class LateKind(enum.Enum):
        ONLY = Box("only")

    Late.__module__ = LateKind.__module__ = module.__name__
    module.Late, module.LateKind = Late, LateKind

    def load_the_module(text):
        sys.modules[module.__name__] = module
        return Box(text)

    register_snapshot_serializer(Box, lambda box: box.content, load_the_module, tag="loads")
    sys.modules[module.__name__] = module
    try:
        written = [_encode(Late(Box("x"))), _encode(LateKind.ONLY)]
    finally:
        del sys.modules[module.__name__]
    read = []
    for record in written:
        try:
            read.append(_decode(record))
        finally:
            sys.modules.pop(module.__name__, None)
    assert_that(type(read[0])).is_same_as(Late)
    assert_that(read[1]).is_same_as(LateKind.ONLY)


def test_a_file_that_spells_a_marker_with_an_escape_is_read_as_the_record_it_is(tmp_path):
    target = tmp_path / "snap-escaped.json"
    target.write_bytes(rb'{"\u005f_type__": "tuple", "__data__": [1, 2]}')
    assert_that(_load(str(target))).is_equal_to((1, 2))


def test_a_cycle_through_a_tuple_is_named():
    held: list = []
    held.append((held,))
    try:
        _encode(held)
    except (ValueError, RecursionError) as refused:
        raised = refused
    assert_that(type(raised)).is_same_as(ValueError)
    assert_that(str(raised)).contains("circular reference")
