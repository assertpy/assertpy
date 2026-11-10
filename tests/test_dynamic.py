import collections
import types

import pytest

from assertpy import AssertionFailure, assert_that, soft_assertions
from assertpy import dynamic as dynamic_module
from assertpy._hints import _IDENTITY_FACT, _NAN_FACT, _UNSEEN_IDENTITY_FACT


class Person:
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    def say_hello(self):
        return f"Hello, {self.first_name}!"

    def say_goodbye(self, target):
        return f"Bye, {target}!"


fred = Person("Fred", "Smith", 12)


def test_dynamic_assertion():
    assert_that(fred).is_type_of(Person)
    assert_that(fred).is_instance_of(object)

    assert_that(fred.first_name).is_equal_to("Fred")
    assert_that(fred.last_name).is_equal_to("Smith")
    assert_that(fred.shoe_size).is_equal_to(12)

    assert_that(fred).has_first_name("Fred")
    assert_that(fred).has_last_name("Smith")
    assert_that(fred).has_shoe_size(12)


def test_dynamic_assertion_on_property():
    assert_that(fred.name).is_equal_to("Fred Smith")
    assert_that(fred).has_name("Fred Smith")


def test_dynamic_assertion_on_method():
    assert_that(fred.say_hello()).is_equal_to("Hello, Fred!")
    assert_that(fred).has_say_hello("Hello, Fred!")


def test_dynamic_assertion_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_first_name("Joe")
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <Fred> to be equal to <Joe> on attribute <first_name>, but was not."
    )


def test_dynamic_assertion_bad_name_failure():
    with pytest.raises(AttributeError) as exc_info:
        assert_that(fred).foo()
    assert_that(str(exc_info.value)).is_equal_to("assertpy has no assertion <foo()>")


def test_dynamic_assertion_unknown_attribute_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).has_foo()
    assert_that(str(exc_info.value)).is_equal_to("Expected attribute <foo>, but val has no attribute <foo>.")


def test_dynamic_assertion_no_args_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_first_name()
    assert_that(str(exc_info.value)).is_equal_to("assertion <has_first_name()> takes exactly 1 argument (0 given)")


def test_dynamic_assertion_too_many_args_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_first_name("Fred", "Joe")
    assert_that(str(exc_info.value)).is_equal_to("assertion <has_first_name()> takes exactly 1 argument (2 given)")


def test_dynamic_assertion_on_method_failure():
    with pytest.raises(TypeError) as exc_info:
        assert_that(fred).has_say_goodbye("Foo")
    assert_that(str(exc_info.value)).contains("val does not have zero-arg method <say_goodbye()>")


def test_chaining():
    assert_that(fred).has_first_name("Fred").has_last_name("Smith").has_shoe_size(12)


class TestDynamicDictAccess:
    """Dynamic ``has_<key>()`` access on dict values: wording, subscript access, and comparison."""

    def test_missing_dict_key_reports_key_wording(self):
        with pytest.raises(AssertionError, match="Expected key"):
            assert_that({"a": 1}).has_b()

    def test_present_dict_key_compares_via_subscript(self):
        assert_that({"name": "Alice"}).has_name("Alice")

    def test_dict_value_greater_than_expected_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"n": 5}).has_n(3)

    def test_method_name_key_absent_reports_key_not_keyerror(self):
        # "items" and "get" are methods but absent as keys, so the gate must report a key failure, not KeyError
        with pytest.raises(AssertionError, match="Expected key <items>"):
            assert_that({"status": "ok"}).has_items([1, 2, 3])
        with pytest.raises(AssertionError, match="Expected key <get>"):
            assert_that({"total": 5}).has_get("x")

    def test_method_name_key_present_compares_value(self):
        assert_that({"items": [1, 2]}).has_items([1, 2])

    def test_has_name_on_list_fails_cleanly(self):
        with pytest.raises(AssertionError):
            assert_that([1, 2, 3]).has_count(1)


def test_has_zero_arg_method_body_typeerror_not_masked():
    class Order:
        prices = None

        def total(self):
            return sum(self.prices)

    # the real TypeError must propagate, not be masked as "does not have zero-arg method"
    with pytest.raises(TypeError, match="not iterable"):
        assert_that(Order()).has_total(0)


def test_has_method_without_introspectable_signature():
    # a zero-arg builtin (int() -> 0) whose inspect.signature raises ValueError must still be called
    class Obj:
        action = staticmethod(int)

    assert_that(Obj()).has_action(0)


class TestTheOperandMayBeWrittenByName:
    """The signature says `other`, and `Requirement.parameters` reads that name, but writing it was refused."""

    def test_the_keyword_is_accepted(self):
        assert_that({"name": "x"}).has_name(other="x")
        assert_that(assert_that({"name": "x"}).check().has_name(other="y").passed).is_false()

    def test_the_requirement_names_the_operand_however_it_was_written(self):
        assert_that(assert_that({"a": 1}).check().has_a(other=2).requirement.parameters).is_equal_to({"other": 2})
        with pytest.raises(AssertionError) as failure:
            assert_that({"a": 1}).not_.has_a(1)
        assert_that(failure.value.requirement.parameters).is_equal_to({"other": 1})

    def test_a_missing_key_keeps_the_call_it_could_not_bind(self):
        asked = assert_that({"a": 1}).check().has_b(1, 2).requirement
        assert_that(asked.parameters).is_equal_to({"args": (1, 2), "kwargs": {}})

    def test_an_attribute_takes_it_too(self):
        class Holder:
            name = "x"

        assert_that(Holder()).has_name(other="x")

    @pytest.mark.parametrize(
        ("args", "kwargs", "given"),
        [
            pytest.param((), {}, 0, id="none"),
            pytest.param(("a", "b"), {}, 2, id="two-positional"),
            pytest.param((), {"nope": 1}, 1, id="a-name-it-does-not-take"),
        ],
    )
    def test_anything_else_is_still_refused(self, args, kwargs, given):
        with pytest.raises(TypeError, match=f"takes exactly 1 argument \\({given} given\\)"):
            assert_that({"name": "x"}).has_name(*args, **kwargs)


class _Held:
    def __init__(self, held):
        self.held = held

    def __repr__(self):
        return "held"


class _Rows(list):
    pass


class TestAFailureIsTheOneOfTheEqualityItAsked:
    """``has_<name>(x)`` compares the value read with ``x``, and fails as `is_equal_to` on that pair fails.

    It printed ``Expected <7> to be equal to <7> on attribute <id>, but was not`` for an id held as text, and
    carried neither the two values nor a diff of them.
    """

    def test_two_values_that_print_the_same_are_told_apart_by_class(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"id": 7}).has_id("7")
        assert_that(caught.value._message).is_equal_to(
            "Expected <7:int> to be equal to <7:str> on key <id>, but was not."
        )

    def test_two_that_print_otherwise_are_printed_as_they_were(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(fred).has_first_name("Joe")
        assert_that(caught.value._message).is_equal_to(
            "Expected <Fred> to be equal to <Joe> on attribute <first_name>, but was not."
        )

    @pytest.mark.parametrize("kind", [list, tuple, _Rows], ids=["list", "tuple", "a list of a class of its own"])
    def test_two_long_sequences_are_collapsed_as_is_equal_to_collapses_them(self, kind):
        rows = kind({"id": n, "city": "Oslo"} for n in range(40))
        other = kind({"id": n, "city": "Paris" if n == 17 else "Oslo"} for n in range(40))
        with pytest.raises(AssertionFailure) as plain:
            assert_that(rows).is_equal_to(other)
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": rows}).has_items(other)
        assert_that(caught.value._message).is_equal_to(
            plain.value._message.replace(", but was not.", " on key <items>, but was not.")
        )
        opener, closer = ("(", ")") if kind is tuple else ("[", "]")
        assert_that(caught.value._message).is_equal_to(
            f"Expected <{opener}.., {{'id': 17, 'city': 'Oslo'}}, ..{closer}> to be equal to"
            f" <{opener}.., {{'id': 17, 'city': 'Paris'}}, ..{closer}> on key <items>, but was not."
        )

    @pytest.mark.parametrize(
        ("rows", "other"),
        [
            (["x" * 5000, "kept"], ["y" * 5000, "kept"]),
            ([f"row {n}" for n in range(40)], [f"ROW {n}" for n in range(40)]),
        ],
        ids=["one element past the cap of a side", "every element differs"],
    )
    def test_two_sequences_are_cut_and_counted_as_is_equal_to_cuts_and_counts_them(self, rows, other):
        with pytest.raises(AssertionFailure) as plain:
            assert_that(rows).is_equal_to(other)
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": rows}).has_items(other)
        assert_that(plain.value._message).matches(r"\.\.\. \(1008 more chars\)>|\.\.\. and 35 more\]>")
        assert_that(caught.value._message).is_equal_to(
            plain.value._message.replace(", but was not.", " on key <items>, but was not.")
        )

    def test_where_the_collapsed_texts_read_alike_the_two_are_cut_around_the_place_they_part(self):
        # `is_equal_to` keeps the two texts that read alike there, cut at one place: this is where the two part
        rows, other = ["a" * 5000 + "x"], ["a" * 5000 + "y"]
        with pytest.raises(AssertionFailure) as plain:
            assert_that(rows).is_equal_to(other)
        sides = (
            plain.value._message.removeprefix("Expected <").removesuffix(">, but was not.").split("> to be equal to <")
        )
        assert_that(sides[0]).is_equal_to(sides[1])
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": rows}).has_items(other)
        message = caught.value._message
        assert_that(message).contains("ax']> to be equal to <", "ay']> on key <items>, but was not.")

    @pytest.mark.parametrize(
        ("held", "operand"),
        [
            ({"city": "Oslo", "zip": "0150"}, {"city": "Paris", "zip": "0150"}),
            ({f"k{n}": n for n in range(40)}, {**{f"k{n}": n for n in range(40)}, "k17": 99}),
            ({"a": {"b": {"c": 1, "d": 2}}, "e": [1, 2, 3]}, {"a": {"b": {"c": 9, "d": 2}}, "e": [1, 2, 3]}),
            ({"a": 1}, {"a": 1, "b": 2}),
            (collections.OrderedDict(a=1), {"a": 2}),
            (types.MappingProxyType({"a": 1, "b": 2}), {"a": 1, "b": 3}),
        ],
        ids=["two keys", "forty keys", "nested", "a key only one has", "an OrderedDict", "a mapping proxy"],
    )
    def test_two_mappings_are_printed_as_is_equal_to_prints_them(self, held, operand):
        with pytest.raises(AssertionFailure) as plain:
            assert_that(held).is_equal_to(operand)
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": held}).has_items(operand)
        assert_that(caught.value._message).is_equal_to(
            plain.value._message.replace(", but was not.", " on key <items>, but was not.")
        )

    def test_only_the_keys_that_differ_are_printed(self):
        held = {f"k{n}": n for n in range(40)}
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": held}).has_items({**held, "k17": 99})
        assert_that(caught.value._message).is_equal_to(
            "Expected <{.., 'k17': 17, ..}> to be equal to <{.., 'k17': 99, ..}> on key <items>, but was not."
        )

    def test_two_mappings_that_collapse_to_one_text_are_told_apart_as_two_texts_are(self):
        class Kept(dict):
            def __eq__(self, other: object) -> bool:
                return False

            __hash__ = None  # ty: ignore[invalid-assignment, incompatible-method-override]  # a dict is unhashable anyway

        held = Kept(a=1)
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": held}).has_items({"a": 1})
        assert_that(caught.value._message.splitlines()[0]).is_equal_to(
            "Expected <{'a': 1}:Kept> to be equal to <{'a': 1}:dict> on key <items>, but was not."
        )
        # the walk shows nothing under two mappings with the same entries, so the pair is the entry
        entries = caught.value.diff.entries
        assert_that([(entry.path, entry.actual is held, entry.expected) for entry in entries]).is_equal_to(
            [(".", True, {"a": 1})]
        )

    def test_a_value_the_verdict_never_asked_costs_neither_the_failure_nor_its_message(self):
        # `==` of two dicts stops at the first pair of values that differs: the collapsing and the diff go on
        class Refusing:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError("no equality")

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                return "refusing"

        held, other = {"a": 1, "b": Refusing()}, {"a": 2, "b": Refusing()}
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": held}).has_items(other)
        failure = caught.value
        assert_that(failure._message).is_equal_to(
            "Expected <{'a': 1, 'b': refusing}> to be equal to <{'a': 2, 'b': refusing}> on key <items>, but was not."
        )
        assert_that((failure.diff.kind, len(failure.diff.entries))).is_equal_to(("scalar", 1))
        assert_that(failure.diff.entries[0].actual).is_same_as(held)

    def test_the_collapsed_texts_are_kept_where_only_the_diff_cannot_be_built(self, monkeypatch):
        def refused(actual: object, expected: object) -> None:
            raise RuntimeError("no diff")

        monkeypatch.setattr(dynamic_module, "_build_equality_diff", refused)
        rows = [{"id": n} for n in range(40)]
        other = [{"id": 99 if n == 17 else n} for n in range(40)]
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": rows}).has_items(other)
        assert_that(caught.value._message).is_equal_to(
            "Expected <[.., {'id': 17}, ..]> to be equal to <[.., {'id': 99}, ..]> on key <items>, but was not."
        )
        assert_that([(entry.path, entry.actual is rows) for entry in caught.value.diff.entries]).is_equal_to(
            [(".", True)]
        )

    def test_two_short_sequences_are_printed_whole(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"ids": [1, 2]}).has_ids([1, 3])
        assert_that(caught.value._message).is_equal_to(
            "Expected <[1, 2]> to be equal to <[1, 3]> on key <ids>, but was not."
        )

    def test_two_sequences_that_collapse_to_one_text_are_told_apart_as_two_texts_are(self):
        class Kept(list):
            def __eq__(self, other: object) -> bool:
                return False

            __hash__ = None  # ty: ignore[invalid-assignment, incompatible-method-override]  # a list is unhashable anyway

        for held in ([1], list(range(40))):
            with pytest.raises(AssertionFailure) as caught:
                assert_that({"items": Kept(held)}).has_items(held)
            assert_that(caught.value._message.splitlines()[0]).is_equal_to(
                f"Expected <{held}:Kept> to be equal to <{held}:list> on key <items>, but was not."
            )

    @pytest.mark.parametrize("padding", [[], list(range(30))], ids=["short", "long"])
    def test_an_element_the_verdict_never_asked_costs_neither_the_failure_nor_its_message(self, padding):
        # `==` of two lists stops at the first pair that differs: the collapsing and the diff go on past it
        class Refusing:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError("no equality")

            __hash__ = None  # ty: ignore[invalid-assignment]  # a class that defines `__eq__` alone is unhashable anyway

            def __repr__(self) -> str:
                return "refusing"

        held, other = [1, *padding, Refusing()], [2, *padding, Refusing()]
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"items": held}).has_items(other)
        failure = caught.value
        assert_that(failure._message).is_equal_to(
            f"Expected <{held}> to be equal to <{other}> on key <items>, but was not."
        )
        # the diff is the pair itself, which reads nothing again
        assert_that((failure.diff.kind, len(failure.diff.entries))).is_equal_to(("scalar", 1))
        assert_that(failure.diff.entries[0].actual).is_same_as(held)
        assert_that(failure.diff.entries[0].expected).is_same_as(other)
        assert_that(str(failure.diff)).contains("- [1, ", "+ [2, ")
        assert_that(failure.actual).is_same_as(held)

    def test_it_carries_the_value_read_the_operand_and_their_diff(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"address": {"city": "Oslo", "zip": "1"}}).has_address({"city": "Paris", "zip": "1"})
        failure = caught.value
        assert_that((failure.actual, failure.expected)).is_equal_to(
            ({"city": "Oslo", "zip": "1"}, {"city": "Paris", "zip": "1"})
        )
        assert_that([(entry.path, entry.actual, entry.expected) for entry in failure.diff.entries]).is_equal_to(
            [("city", "Oslo", "Paris")]
        )

    def test_a_nan_is_said(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"rate": float("nan")}).has_rate(float("nan"))
        assert_that(caught.value._message.splitlines()).is_equal_to(
            ["Expected <nan> to be equal to <nan> on key <rate>, but was not.", _NAN_FACT]
        )

    def test_two_instances_compared_by_identity_are_said(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that({"token": _Held(1)}).has_token(_Held(1))
        assert_that(caught.value._message.splitlines()[1]).is_equal_to(_UNSEEN_IDENTITY_FACT)

    def test_nothing_is_asked_of_the_class_before_the_two_are_compared(self):
        # a descriptor run by a look at the class ahead of ``==`` installed an equality that failed a pair it held equal
        class Equality:
            def __get__(self, instance, owner):
                if instance is None:
                    owner.__eq__ = lambda self, other: False
                    return object.__eq__
                return lambda other: True

        class Token:
            __eq__ = Equality()
            __hash__ = object.__hash__

        assert_that(Token() == Token()).is_true()
        assert_that({"token": Token()}).has_token(Token())

    def test_an_equality_that_rewrites_itself_is_answered_as_an_equality_answers_it(self):
        class Rewriting:
            def __eq__(self, other):
                del type(self).__eq__
                return False

            __hash__ = None

            def __repr__(self):
                return "rewriting"

        with pytest.raises(AssertionFailure) as caught:
            assert_that({"held": Rewriting()}).has_held(Rewriting())
        assert_that(caught.value._message.splitlines()[1]).is_equal_to(_UNSEEN_IDENTITY_FACT)

    def test_a_difference_of_whitespace_is_named(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(fred).has_first_name("Fred ")
        assert_that(caught.value._message.splitlines()[1]).is_equal_to(
            "every difference here is one of surrounding whitespace"
        )

    def test_what_a_comparison_before_it_found_is_not_said_of_the_next(self):
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(_Held(1)).is_equal_to(_Held(1)).has_held(2)
        assert_that(str(caught.value)).contains("on attribute <held>")
        assert_that(str(caught.value).count(_IDENTITY_FACT)).is_equal_to(1)
