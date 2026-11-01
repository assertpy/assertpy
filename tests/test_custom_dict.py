import collections.abc
from unittest import mock

import pytest

from assertpy import assert_that
from assertpy._engine._equality import _reachable_call, carries_callable, supports_subscript
from assertpy._engine._introspection import is_attrs_instance, is_model_dump_object, is_namedtuple


def test_custom_dict():
    headers = CustomDict(
        {
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "User-Agent": "python-requests/2.9.1",
        }
    )

    assert_that(headers).is_not_none()

    assert_that(headers.keys()).contains("Accept-Encoding", "Connection", "Accept", "User-Agent")
    assert_that(headers).contains_key("Accept-Encoding", "Connection", "Accept", "User-Agent")

    assert_that(headers.values()).contains("gzip, deflate", "keep-alive", "application/json", "python-requests/2.9.1")
    assert_that(headers).contains_value("application/json")

    assert_that(headers["Accept"]).is_equal_to("application/json")
    assert_that(headers).contains_entry({"Accept": "application/json"})


def test_requests():
    requests = pytest.importorskip("requests")
    headers = requests.structures.CaseInsensitiveDict(
        {
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Accept": "application/json",
            "User-Agent": "python-requests/2.9.1",
        }
    )

    assert_that(headers).is_not_none()

    assert_that(headers.keys()).contains("Accept-Encoding", "Connection", "Accept", "User-Agent")
    assert_that(headers).contains_key("Accept-Encoding", "Connection", "Accept", "User-Agent")

    assert_that(headers.values()).contains("gzip, deflate", "keep-alive", "application/json", "python-requests/2.9.1")
    assert_that(headers).contains_value("application/json")

    assert_that(headers["Accept"]).is_equal_to("application/json")
    assert_that(headers).contains_entry({"Accept": "application/json"})


class CustomDict:
    def __init__(self, d):
        self._dict = d
        self._idx = 0

    def __iter__(self):
        return self

    def __next__(self):
        try:
            result = self.keys()[self._idx]
        except IndexError:
            raise StopIteration from None
        self._idx += 1
        return result

    def __contains__(self, key):
        return key in self.keys()

    def keys(self):
        return list(self._dict.keys())

    def values(self):
        return list(self._dict.values())

    def __getitem__(self, key):
        return self._dict.get(key)


def test_check_dict_like(builder):
    custom_dict = CustomDict({"a": 1})
    builder._require_dict_like(custom_dict)
    builder._require_dict_like(custom_dict, True, True, True)
    builder._require_dict_like(custom_dict, True, True, False)
    builder._require_dict_like(custom_dict, True, False, True)
    builder._require_dict_like(custom_dict, False, True, True)
    builder._require_dict_like(custom_dict, True, False, False)
    builder._require_dict_like(custom_dict, False, False, True)
    builder._require_dict_like(custom_dict, False, True, False)
    builder._require_dict_like(custom_dict, False, False, False)

    builder._require_dict_like(CustomDictNoKeys(), check_keys=False, check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoKeysCallable(), check_keys=False, check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoValues(), check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoValuesCallable(), check_values=False, check_getitem=False)
    builder._require_dict_like(CustomDictNoGetitem(), check_getitem=False)


def test_check_dict_like_bool(builder):
    assert_that(builder._is_dict_like(CustomDictNoKeys())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoKeysCallable())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoValues())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoValuesCallable())).is_false()
    assert_that(builder._is_dict_like(CustomDictNoGetitem())).is_false()


def test_check_dict_like_no_keys(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._require_dict_like(CustomDictNoKeys())
    assert_that(str(exc_info.value)).contains("must be dict-like (this one has no keys())")


def test_check_dict_like_no_keys_callable(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._require_dict_like(CustomDictNoKeysCallable())
    assert_that(str(exc_info.value)).contains("must be dict-like (this one has no keys())")


def test_check_dict_like_no_values(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._require_dict_like(CustomDictNoValues())
    assert_that(str(exc_info.value)).contains("must be dict-like (this one has no values())")


def test_check_dict_like_no_values_callable(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._require_dict_like(CustomDictNoValuesCallable())
    assert_that(str(exc_info.value)).contains("must be dict-like (this one has no values())")


def test_check_dict_like_no_getitem(builder):
    with pytest.raises(TypeError) as exc_info:
        builder._require_dict_like(CustomDictNoGetitem())
    assert_that(str(exc_info.value)).contains("must be dict-like (this one has no [] accessor)")


class CustomDictNoKeys:
    def __iter__(self):
        return self

    def __next__(self):
        return 1


class CustomDictNoKeysCallable:
    def __init__(self):
        self.keys = "foo"

    def __iter__(self):
        return self

    def __next__(self):
        return 1


class CustomDictNoValues:
    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"


class CustomDictNoValuesCallable:
    def __init__(self):
        self.values = "foo"

    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"


class CustomDictNoGetitem:
    def __iter__(self):
        return self

    def __next__(self):
        return 1

    def keys(self):
        return "foo"

    def values(self):
        return "bar"


def test_dict_repr_survives_mapping_without_items():
    # the renderer builds entries from `keys()`: a minimal mapping may lack `items()` and must not crash
    class MinimalMapping:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    with pytest.raises(AssertionError):
        assert_that(MinimalMapping({"a": 1, "b": 2})).is_equal_to(MinimalMapping({"a": 1, "b": 3}))


def test_nested_mapping_without_values_still_takes_the_dict_path():
    # `check_values=False` on purpose: demanding `values()` would drop to plain equality and the ignore would stop
    class MinimalMapping:
        def __init__(self, data):
            self._data = data

        def keys(self):
            return self._data.keys()

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

    actual = {"d": MinimalMapping({"a": 1, "b": 2})}
    expected = {"d": MinimalMapping({"a": 1, "b": 999})}
    assert_that(actual).is_equal_to(expected, ignore=("d", "b"))


def test_a_sequence_that_answers_keys_is_not_read_as_a_mapping():
    """`unittest.mock.call_args` is a tuple subclass, and a Mock proxies `.keys` into a callable child.

    Duck typing alone therefore read it as keyed, and the renderer walked it for keys, got its items and
    indexed a tuple with a tuple: `TypeError: tuple indices must be integers or slices, not tuple`, on
    the failure path, which is the worst place for it.
    """
    called = mock.Mock()
    called("alice", 30)

    with pytest.raises(AssertionError) as failure:
        assert_that(called.call_args).is_equal_to(mock.call("alice", 31))

    assert_that(str(failure.value)).contains("call('alice', 30)", "call('alice', 31)")


def test_keys_written_as_a_property_is_still_read_as_a_mapping():
    """The static lookup only proves the attribute is really carried; what gets called is the bound
    value.  Reading the descriptor itself instead refuses this, since a `property` is not callable."""

    class Rowish:
        @property
        def keys(self):
            return lambda: ("a",)

        @property
        def values(self):
            return lambda: (1,)

        def __getitem__(self, key):
            return 1

        def __iter__(self):
            return iter(("a",))

    with pytest.raises(AssertionError) as failure:
        assert_that(Rowish()).is_equal_to({"a": 2})

    assert_that(str(failure.value)).contains("{'a': 1}", "{'a': 2}")


def test_a_subscript_answered_only_by_getattr_is_not_read_as_a_mapping():
    """`candidate[key]` looks the operator up on the type, so `hasattr` answering for one the object
    cannot actually be subscripted with would have been accepted and then crashed."""

    class Fabricating:
        def keys(self):
            return ("a",)

        def values(self):
            return (1,)

        def __iter__(self):
            return iter(("a",))

        def __getattr__(self, name):
            return lambda *args: 1

    with pytest.raises(AssertionError) as failure:
        assert_that(Fabricating()).is_equal_to({"a": 2})

    assert_that(str(failure.value)).does_not_contain("{'a': 1}")


def test_a_fabricated_subscript_is_refused_by_the_dict_assertions_too():
    """The equality reading and the refusal in front of the dict assertions have to agree.

    Reading the shape one way and refusing it another lets a value through the door that the code
    behind it cannot subscript, and `self.val[key]` raises `TypeError` from inside the assertion."""

    class Fabricating:
        def keys(self):
            return ("a",)

        def values(self):
            return (1,)

        def __iter__(self):
            return iter(("a",))

        def __getattr__(self, name):
            return lambda *args: 1

    for call in (
        lambda: assert_that(Fabricating()).contains_entry({"a": 1}),
        lambda: assert_that(Fabricating()).does_not_contain_entry({"a": 1}),
    ):
        with pytest.raises(TypeError) as refusal:
            call()

        assert_that(str(refusal.value)).contains("no [] accessor")


def test_a_subscript_nulled_out_on_the_class_is_not_read_as_a_mapping():
    """`__getitem__ = None` is how a subclass takes subscripting away, and the lookup stops there.

    Presence on the MRO would call this one subscriptable, and `candidate[key]` then raises
    `'NoneType' object is not callable`."""

    class Nulled:
        __getitem__ = None

        def keys(self):
            return ("a",)

        def values(self):
            return (1,)

        def __iter__(self):
            return iter(("a",))

    with pytest.raises(AssertionError) as failure:
        assert_that(Nulled()).is_equal_to({"a": 2})

    assert_that(str(failure.value)).does_not_contain("{'a': 1}")

    with pytest.raises(TypeError) as refusal:
        assert_that(Nulled()).contains_entry({"a": 1})

    assert_that(str(refusal.value)).contains("no [] accessor")


def test_a_sequence_that_really_carries_keys_is_still_read_as_a_mapping():
    """The reading is structural by design, so a row wrapper that is a `Sequence` and genuinely answers
    `keys()` keeps it.  Excluding every sequence would have refused this one; what is excluded instead is
    a `keys` that only exists because something answers any name at all.

    Deliberately NOT a `Mapping` subclass: inheriting one would pass any guard and prove nothing.
    """

    class Row(collections.abc.Sequence):
        def keys(self):
            return ("a",)

        def values(self):
            return (1,)

        def __getitem__(self, key):
            return 1 if key == "a" else "a"

        def __len__(self):
            return 1

        def __iter__(self):
            return iter(("a",))

    with pytest.raises(AssertionError) as failure:
        assert_that(Row()).is_equal_to({"a": 2})

    assert_that(str(failure.value)).contains("{'a': 1}", "{'a': 2}")


class _LyingMeta(type):
    """Fabricates `__get__` for its instances, which are classes, so the C slot never sees it."""

    def __getattr__(cls, name):
        if name == "__get__":
            return lambda raw, obj, owner: lambda key: "never reached"
        raise AttributeError(name)


class _HidingMeta(type):
    """Hides a `__get__` its instances really have, which the C slot still finds."""

    def __getattribute__(cls, name):
        if name == "__get__":
            raise AttributeError(name)
        return type.__getattribute__(cls, name)


class _NotADescriptor(metaclass=_LyingMeta):
    pass


class _RealDescriptor(metaclass=_HidingMeta):
    def __get__(self, obj, owner):
        return lambda key: "real"


class _RaisingDescriptor:
    def __get__(self, obj, owner):
        raise RuntimeError("resolving me is not free")


class _CallableWithoutGet:
    def __call__(self, key):
        return "called"


class _CallableWithGetNulled:
    __get__ = None

    def __call__(self, key):
        return "unreachable"


class _NulledCall:
    """`callable()` says yes, because the slot is filled.  Calling it raises."""

    __call__ = None


class _NulledCallOnceRemoved:
    __call__ = _NulledCall()


class _NulledMeta(type):
    """A class whose instantiation raises, while `callable()` says it is fine."""

    __call__ = None


class _NulledClass(metaclass=_NulledMeta):
    pass


class _StaticGet:
    """A `__get__` the interpreter reaches without binding, so it is handed the descriptor as well."""

    @staticmethod
    def __get__(raw, instance, owner):  # noqa: PLE0302 - unbound, so the descriptor arrives as an argument
        return lambda key: 1


class _StaticGetTakingTwo:
    @staticmethod
    def __get__(instance, owner):
        return lambda key: 1


class _ClassMethodGet:
    @classmethod
    def __get__(cls, instance, owner):
        return lambda key: 1


class _PropertyCall:
    """Callable, and the call works.  The `property` itself is not the thing that gets called."""

    @property
    def __call__(self):
        return lambda *args: "called through a property"


class _PlainSubscript:
    def __getitem__(self, key):
        return 1


def _subscript_reaches_an_implementation(subject: object) -> bool:
    """Whether `subject[key]` got as far as an implementation, whatever that implementation then did.

    A complaint about the key means the slot was reached, so it counts as reached: `'abc'['a']` raises
    about string indices and `str` is subscriptable.
    """
    try:
        subject["a"]
    except TypeError as error:
        return "not subscriptable" not in str(error) and "not callable" not in str(error)
    except Exception:
        return True  # anything else also means the implementation was reached
    return True


_SUBSCRIPT_SHAPES = {
    "a metaclass fabricating __get__": type("Fabricated", (), {"__getitem__": _NotADescriptor()}),
    "a metaclass hiding __get__": type("Hidden", (), {"__getitem__": _RealDescriptor()}),
    "a callable carrying no __get__": type("Called", (), {"__getitem__": _CallableWithoutGet()}),
    "a callable whose __get__ is nulled": type("Nulled__get__", (), {"__getitem__": _CallableWithGetNulled()}),
    "a subscript whose __call__ is nulled": type("Nulled__call__", (), {"__getitem__": _NulledCall()}),
    "the same one level further down": type("Deeper", (), {"__getitem__": _NulledCallOnceRemoved()}),
    "a subscript whose __call__ is a property": type("Propertied__call__", (), {"__getitem__": _PropertyCall()}),
    "a subscript that is a class nulled by its metaclass": type("Classy", (), {"__getitem__": _NulledClass}),
    "a subscript that is an ordinary class": type("Ordinary", (), {"__getitem__": dict}),
    "a __get__ written as a staticmethod": type("Static", (), {"__getitem__": _StaticGet()}),
    "a __get__ written as a classmethod": type("Classmethodly", (), {"__getitem__": _ClassMethodGet()}),
    "a subclass nulling the parent out": type("Nulled", (_PlainSubscript,), {"__getitem__": None}),
    "a plain parent": _PlainSubscript,
    "a property": type("Propertied", (), {"__getitem__": property(lambda self: lambda key: "property")}),
    "a slotted class": type("Slotted", (), {"__slots__": (), "__getitem__": lambda self, key: 1}),
    "no subscript at all": type("Bare", (), {}),
}


def test_the_reading_of_a_subscript_is_the_one_the_interpreter_does():
    """Sixteen shapes, each answered by trying the subscript rather than by a recorded expectation.

    `hasattr` and plain presence on the MRO each get some of these wrong, and both were shipped.  Asking
    the interpreter rather than recording an answer is also what keeps this honest across versions: the
    descriptor rules here are ones that have moved between releases."""
    read = {name: supports_subscript(shape()) for name, shape in _SUBSCRIPT_SHAPES.items()}
    truth = {name: _subscript_reaches_an_implementation(shape()) for name, shape in _SUBSCRIPT_SHAPES.items()}

    assert_that(read).is_equal_to(truth)


def test_the_table_of_shapes_is_not_empty():
    """A table of nothing would make the claim above vacuous rather than false."""
    assert_that(_SUBSCRIPT_SHAPES).is_not_empty()


def test_a_key_assigned_on_the_instance_is_really_carried():
    """Not every real `keys` is on the type.  One set per instance is carried just as much."""

    class Bare:
        pass

    subject = Bare()
    subject.keys = lambda: ("a",)
    subject.values = lambda: (1,)
    subject.__iter__ = lambda: iter(("a",))

    assert_that(carries_callable(subject, "keys")).is_true()


def test_a_sequence_delegating_its_keys_is_read_as_a_mapping_too():
    """Two rules against fabricated attributes were tried here and both were unsound.

    A `Sequence` subclass wrapping a mapping and forwarding `keys` is the counterexample to the second:
    it differs from an ordinary proxy only by what it inherits from, and it worked in 2.24.0."""

    class SequenceProxy(collections.abc.Sequence):
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __getitem__(self, key):
            return self._inner[key]

        def __len__(self):
            return len(self._inner)

        def __iter__(self):
            return iter(self._inner)

    row = SequenceProxy({"a": 1})

    assert_that(row).contains_key("a")
    assert_that(row).contains_entry({"a": 1})


def test_a_proxy_forwarding_its_keys_is_still_a_mapping():
    """Fabrication on its own is not a reason to refuse, or every delegating wrapper would be refused.

    The refusal is for a value that is already a sequence, where reading it as a mapping is a
    reinterpretation.  A proxy is not one, and it kept working from 2.24.0 through this."""

    class Proxy:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __getitem__(self, key):
            return self._inner[key]

        def __iter__(self):
            return iter(self._inner)

    row = Proxy({"a": 1})

    assert_that(row).contains_key("a")
    assert_that(row).contains_value(1)
    assert_that(row).contains_entry({"a": 1})

    with pytest.raises(AssertionError) as failure:
        assert_that(row).is_equal_to({"a": 2})

    assert_that(str(failure.value)).contains("{'a': 1}", "{'a': 2}")


@pytest.mark.parametrize(
    ("descriptor", "raised"),
    [(_RaisingDescriptor, RuntimeError), (_StaticGetTakingTwo, TypeError)],
    ids=["a __get__ that raises", "a __get__ one parameter short"],
)
def test_an_accessor_that_cannot_be_resolved_is_read_as_no_subscript_at_all(descriptor, raised):
    """Where the reading deliberately differs from the interpreter, which reaches the accessor and dies
    in it.

    This question gets asked while rendering a failure, so letting the exception through would replace
    the failure the reader came for with someone else's.  Answering `False` renders the value as a plain
    object instead, and a real subscript raises either way."""
    subject = type("Unresolvable", (), {"__getitem__": descriptor()})()

    with pytest.raises(raised):
        subject["a"]

    assert_that(supports_subscript(subject)).is_false()


def test_a_key_whose_call_is_nulled_is_not_a_key_either():
    """The same shallowness applies to `keys`, which the renderer calls rather than subscripts."""

    class NulledKeys:
        keys = _NulledCall()

        def values(self):
            return (1,)

        def __getitem__(self, key):
            return 1

        def __iter__(self):
            return iter(("a",))

    assert_that(carries_callable(NulledKeys(), "keys")).is_false()


def test_a_chain_built_to_outlast_the_hops_is_read_as_callable():
    """Where the reading stops, said out loud rather than left to be discovered.

    Resolving a call is bounded, so a chain built past the bound is answered the way `callable()`
    answers it.  Nothing in the wild builds one: every callable that is not a function, a method or a
    class is one hop deep."""
    deep = _NulledCall()
    for _ in range(6):
        deep = type("Wrapping", (), {"__call__": deep})()

    assert_that(_reachable_call(deep)).is_true()
    assert_that(callable(deep)).is_true()

    with pytest.raises(TypeError):
        deep()


def test_a_key_whose_call_is_a_property_is_still_a_key():
    """The refusals have to be able to say yes.  Resolving `__call__` without its descriptor step
    turned a mapping that works into one this library would not read."""

    class Rowish:
        keys = _PropertyCall()
        values = _PropertyCall()

        def __getitem__(self, key):
            return 1

        def __iter__(self):
            return iter(("a",))

    assert_that(carries_callable(Rowish(), "keys")).is_true()
    assert_that(callable(Rowish().keys)).is_true()


def test_a_key_that_is_a_class_nulled_by_its_metaclass_is_not_a_key():
    """A class is callable until its metaclass says otherwise, so it does not get to skip the reading."""

    class Rowish:
        keys = _NulledClass

        def values(self):
            return (1,)

        def __getitem__(self, key):
            return 1

        def __iter__(self):
            return iter(("a",))

    assert_that(callable(Rowish().keys)).is_true()
    assert_that(carries_callable(Rowish(), "keys")).is_false()


def test_an_ordinary_class_is_still_callable():
    """The refusal above has to be about the metaclass and not about being a class."""
    assert_that(_reachable_call(dict)).is_true()
    assert_that(_reachable_call(_PropertyCall)).is_true()


def test_a_value_unreadable_by_key_keeps_its_failure():
    """The guess about shape is allowed to be wrong.  It is not allowed to cost the failure.

    `unittest.mock.call_args` is a tuple subclass answering `keys`, so the renderer walked the tuple for
    keys, got its items and indexed the tuple with one.  It raised `TypeError` where the reader had come
    for an assertion failure."""
    recorder = mock.Mock()
    recorder("alice", 30)

    with pytest.raises(AssertionError) as failure:
        assert_that(recorder.call_args).is_equal_to(mock.call("alice", 31))

    assert_that(str(failure.value)).contains("call('alice', 30)", "call('alice', 31)")
    diff = failure.value.diff
    assert_that((diff.kind, [(entry.path, entry.actual, entry.expected) for entry in diff.entries])).is_equal_to(
        ("scalar", [(".", recorder.call_args, mock.call("alice", 31))])
    )


class _MixedKeys:
    """Yields an index that works and then a key that does not, so one probe is not enough."""

    def keys(self):
        return (0, "bad")

    def values(self):
        return (1, 2)

    def __getitem__(self, key):
        return [1, 2][key]

    def __iter__(self):
        return iter((0, "bad"))


class _Alternating:
    """Answers one way on the first pass and another on the second, which no probe can classify."""

    def __init__(self):
        self._passes = 0

    def _stream(self):
        self._passes += 1
        return (0,) if self._passes <= 1 else ("bad",)

    def keys(self):
        return self._stream()

    def values(self):
        return (1,)

    def __getitem__(self, key):
        return [1][key]

    def __iter__(self):
        return iter(self._stream())


def test_a_value_unreadable_at_a_later_key_keeps_its_failure():
    """The first key succeeding says nothing about the rest of the stream."""
    with pytest.raises(AssertionError) as failure:
        assert_that(_MixedKeys()).is_equal_to({0: 9})

    assert_that(str(failure.value)).contains("_MixedKeys")


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ({"x": _MixedKeys()}, {"x": _MixedKeys()}),
        ({"x": _MixedKeys()}, {"x": {0: 9}}),
    ],
    ids=["both sides nested", "against a real dict"],
)
def test_a_value_unreadable_by_key_keeps_its_failure_when_nested(actual, expected):
    """The guess is made at every descent, so an ordinary dict cannot smuggle one past the outer check.

    Two descents reach a nested value, the diff entries and the rendered text, and each was measured to
    crash on its own."""
    with pytest.raises(AssertionError) as failure:
        assert_that(actual).is_equal_to(expected)

    assert_that(str(failure.value)).contains("_MixedKeys")


def test_the_deliberate_type_error_is_not_swallowed():
    """A `try` around the whole rendering would pass this and it was written that way first.

    An element-wise array reached in the diff phase raises a `TypeError` this package promises, and it
    has to survive a renderer that is also guarding against unreadable shapes."""

    class ElementWise:
        def __eq__(self, other):
            raise ValueError("truth value of an array with more than one element is ambiguous")

        __hash__ = None

    with pytest.raises(ValueError, match="ambiguous"):
        assert_that({"a": ElementWise()}).is_equal_to({"a": ElementWise()})


def test_a_mock_answers_none_of_the_structural_predicates():
    """A `unittest.mock` object fabricates every attribute, so it answered all three of these.

    The diff walk then read a call's own elements as field names and handed one to `getattr`, and on
    another version as keys into a dict.  A mock's class carries none of the three."""
    recorder = mock.Mock()
    recorder("alice", 30)

    for subject in (recorder, recorder.call_args, mock.call("alice", 30)):
        assert_that(is_namedtuple(subject)).is_false()
        assert_that(is_model_dump_object(subject)).is_false()
        assert_that(is_attrs_instance(subject)).is_false()


def test_the_structural_predicates_still_say_yes():
    """Asking the type has to keep answering for the values these exist to recognise."""
    point = collections.namedtuple("point", ["x"])

    class Model:
        def model_dump(self):
            return {}

    class Attrsish:
        __attrs_attrs__ = ()

    assert_that(is_namedtuple(point(1))).is_true()
    assert_that(is_model_dump_object(Model())).is_true()
    assert_that(is_attrs_instance(Attrsish())).is_true()


def test_a_value_that_answers_differently_on_each_pass_is_rendered_from_one_reading():
    """A probe and the walk after it are two readings, and this value is free to differ between them.

    Reading once and rendering from what was read is what makes the second pass irrelevant.  The message
    names the pair that was actually compared, `{0: 1}`, rather than raising on `"bad"` later."""
    with pytest.raises(AssertionError) as failure:
        assert_that(_Alternating()).is_equal_to({0: 9})

    assert_that(str(failure.value)).contains("{0: 1}", "{0: 9}")


def test_a_tuple_carrying_only_fields_is_not_a_namedtuple():
    """Both halves of the surface, because the callers use both."""

    class FieldsOnly(tuple):
        _fields = ("x",)

    assert_that(is_namedtuple(FieldsOnly())).is_false()

    with pytest.raises(AssertionError) as failure:
        assert_that({"a": FieldsOnly()}).is_equal_to({"a": FieldsOnly((1,))})

    assert_that(str(failure.value)).contains("'a'")


def test_a_model_dump_shadowed_on_the_instance_is_not_a_model():
    """An ordinary method is a non-data descriptor, so the instance wins and the type is not the answer.

    The type is asked first, which is what excludes a mock, and then the bound value is asked whether it
    can be called at all."""

    class Model:
        def model_dump(self):
            return {}

    shadowed = Model()
    shadowed.model_dump = None

    assert_that(is_model_dump_object(shadowed)).is_false()
    assert_that(is_model_dump_object(Model())).is_true()

    with pytest.raises(AssertionError) as failure:
        assert_that({"a": shadowed}).is_equal_to({"a": Model()})

    assert_that(str(failure.value)).contains("'a'")


def test_a_custom_mapping_that_changes_between_reads_still_keeps_its_failure():
    """Registering as a `Mapping` promises an interface, not that two reads agree, so only a `dict`
    skips the snapshot.

    This one drifts before the message is even built, so there is no reading left to render from and it
    falls back to a plain repr.  What it must not do is raise the `KeyError` in place of the failure."""

    class Drifting(collections.abc.Mapping):
        def __init__(self):
            self._passes = 0

        def __iter__(self):
            self._passes += 1
            return iter(("a",) if self._passes <= 1 else ("gone",))

        def __getitem__(self, key):
            if key != "a":
                raise KeyError(key)
            return 1

        def __len__(self):
            return 1

    with pytest.raises(AssertionError) as failure:
        assert_that(Drifting()).is_equal_to({"a": 2})

    assert_that(str(failure.value)).contains("Drifting", "{'a': 2}")


def test_a_nested_filter_reads_the_value_once():
    """A nested `ignore` walks the value again, so it gets the snapshot rather than the original."""

    class Drifting:
        def __init__(self):
            self._passes = 0

        def _stream(self):
            self._passes += 1
            return ("keep", "drop") if self._passes <= 2 else ("gone",)

        def keys(self):
            return self._stream()

        def values(self):
            return (1, 2)

        def __getitem__(self, key):
            return {"keep": 1, "drop": 2}[key]

        def __iter__(self):
            return iter(self._stream())

    with pytest.raises(AssertionError) as failure:
        assert_that({"outer": Drifting()}).is_equal_to({"outer": {"keep": 9}}, ignore=("outer", "drop"))

    assert_that(str(failure.value)).contains("keep")


def test_a_value_the_shape_walk_renders_as_its_counterpart_falls_back_to_its_repr():
    """A `MagicMock` answers `keys()` and iterates empty, so the walk rendered an unequal pair alike.

    `Expected <{}> to be equal to <{}>, but was not.` is a message that contradicts itself, and at the
    top level the structured diff was empty as well, so the failure carried nothing a reader could act
    on.  The shape guess is given up there, exactly as it is for a value that cannot be walked at all.
    """
    with pytest.raises(AssertionError) as failure:
        assert_that(mock.MagicMock()).is_equal_to({})
    assert_that(str(failure.value)).contains("MagicMock").does_not_contain("<{}> to be equal to <{}>")


def test_the_fallback_reads_the_same_from_either_side():
    with pytest.raises(AssertionError) as failure:
        assert_that({}).is_equal_to(mock.MagicMock())
    assert_that(str(failure.value)).contains("MagicMock")


def test_a_nested_one_is_named_where_it_sits():
    """The nested case already had a correct diff and a headline that disagreed with it."""
    with pytest.raises(AssertionError) as failure:
        assert_that({"k": mock.MagicMock()}).is_equal_to({"k": {}})
    assert_that(str(failure.value).splitlines()[0]).contains("'k': <MagicMock", "to be equal to <{'k': {}}>")


def test_two_ordinary_mappings_keep_the_shape_aware_rendering():
    """The fallback is for renderings that agree, and two unequal dicts do not produce one."""
    with pytest.raises(AssertionError) as failure:
        assert_that({"a": 1, "b": 2}).is_equal_to({"a": 1, "b": 3})
    assert_that(str(failure.value).splitlines()[0]).contains("'b': 2", "'b': 3")


class _Alike:
    """Two of these are unequal and read the same, which is what makes a projection render alike."""

    def __init__(self, tag):
        self.tag = tag

    def __repr__(self):
        return "same"

    def __eq__(self, other):
        return isinstance(other, _Alike) and other.tag == self.tag

    def __hash__(self):
        return hash(self.tag)


def test_the_fallback_does_not_put_an_ignored_key_back_into_the_message():
    """`ignore` governs the report as well as the verdict, and the fallback has to honour that.

    The halves rendered under a filter are a projection, so printing the originals when they read alike
    hands back the key the caller asked to keep out of the log.
    """
    with pytest.raises(AssertionError) as failure:
        assert_that({"secret": "sk-live-LEFT", "shown": _Alike("a")}).is_equal_to(
            {"secret": "sk-live-RIGHT", "shown": _Alike("b")}, ignore="secret"
        )
    assert_that(str(failure.value)).does_not_contain("sk-live")


def test_the_fallback_stays_inside_the_length_cap():
    """Compared before truncating, or two values agreeing for the first 4000 characters collide once cut
    and the untruncated fallback prints both in full."""
    with pytest.raises(AssertionError) as failure:
        assert_that({"a": "x" * 5000 + "L"}).is_equal_to({"a": "x" * 5000 + "R"})
    assert_that(str(failure.value).splitlines()[0]).contains("more chars)")
