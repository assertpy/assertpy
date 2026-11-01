"""An exception under ``ignore=`` or ``include=`` is read as its class, its ``args`` and its attributes.

Read through its ``__dict__`` alone, two exceptions were equal whatever their ``args`` held, a
``ValueError("a")`` and a ``ValueError("b")`` among them.  Left to its own ``==``, which is identity, no two
could be compared at all, and at the top the call raised `TypeError`.

Three things hold here.  ``args`` is read, so the message takes part.  The class is a field, ``__class__``, so
two errors of two classes differ unless that field is left out by name.  And an exception whose class keeps
state in neither ``args`` nor ``__dict__``, an `OSError` with its ``filename`` or a class with a slot, is not
read by fields: nothing would say what was left out.
"""

from __future__ import annotations

import dataclasses
import sys

import pytest

from assertpy import AssertionFailure, assert_that, match, soft_assertions
from assertpy._engine._equality import _holds_only_its_args, comparable_fields
from assertpy._engine._introspection import TakenApart


@dataclasses.dataclass
class User:
    id: int


class ApiError(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class SlottedError(Exception):
    __slots__ = ("code",)

    def __init__(self, code: int) -> None:
        super().__init__("slotted")
        self.code = code


class DerivedError(ApiError):
    pass


def _paths(call) -> list[str]:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return [entry.path for entry in caught.value.diff.entries]


class TestWhatIsRead:
    def test_the_message_takes_part_through_args(self):
        paths = _paths(lambda: assert_that(ValueError("a")).is_equal_to(ValueError("b"), ignore="unrelated"))
        assert_that(paths).is_equal_to(["args[0]"])

    def test_an_attribute_left_out_does_not_leave_out_the_args_that_repeat_it(self):
        one, other = ApiError(404, "a"), ApiError(404, "b")
        assert_that(_paths(lambda: assert_that(one).is_equal_to(other, ignore="detail"))).is_equal_to(["args[0]"])
        assert_that(one).is_equal_to(other, ignore=["detail", "args"])
        assert_that(one).is_equal_to(other, include="code")

    def test_two_that_hold_the_same_are_equal(self):
        assert_that(ApiError(404, "a")).is_equal_to(ApiError(404, "a"), ignore="unrelated")

    def test_an_attribute_that_differs_is_named(self):
        paths = _paths(lambda: assert_that(ApiError(404, "a")).is_equal_to(ApiError(500, "a"), ignore="args"))
        assert_that(paths).is_equal_to(["code"])

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="add_note() arrived in Python 3.11")
    def test_a_note_is_an_attribute_like_any_other(self):
        one, other = ValueError("x"), ValueError("x")
        one.add_note("first")
        other.add_note("second")
        assert_that(_paths(lambda: assert_that(one).is_equal_to(other, ignore="unrelated"))).is_equal_to(
            ["__notes__[0]"]
        )

    def test_an_args_the_class_spells_itself_is_not_what_is_read(self):
        class SpelledError(Exception):
            @property
            def args(self):
                raise RuntimeError("no args")

        assert_that(SpelledError("a")).is_equal_to(SpelledError("a"), ignore="unrelated")
        assert_that(comparable_fields(SpelledError("a"))["args"]).is_equal_to(("a",))

    def test_an_attribute_under_either_of_the_two_names_does_not_replace_what_is_read(self):
        one, other = ValueError("a"), ValueError("b")
        for error in (one, other):
            vars(error).update({"args": ("same",), "__class__": KeyError})
        fields = comparable_fields(one)
        assert_that((fields["args"], fields["__class__"])).is_equal_to((("a",), ValueError))
        assert_that(_paths(lambda: assert_that(one).is_equal_to(other, ignore="unrelated"))).is_equal_to(["args[0]"])
        assert_that(ValueError("a")).is_equal_to(one, ignore="unrelated")

    def test_a_dict_the_class_spells_itself_is_not_what_is_read(self):
        class HidingError(Exception):
            __dict__ = property(lambda self: {})

            def __init__(self, code: int) -> None:
                super().__init__("same")
                self.code = code

        assert_that(vars(HidingError(1))).is_empty()
        paths = _paths(lambda: assert_that(HidingError(1)).is_equal_to(HidingError(2), ignore="unrelated"))
        assert_that(paths).is_equal_to(["code"])

    def test_an_exception_that_is_a_record_is_read_as_the_record_it_declares(self):
        @dataclasses.dataclass
        class DeclaredError(Exception):
            code: int
            detail: str

        one, other = DeclaredError(404, "a"), DeclaredError(404, "b")
        assert_that((one.args, other.args)).is_equal_to(((404, "a"), (404, "b")))
        assert_that(dict(comparable_fields(one))).is_equal_to({"code": 404, "detail": "a"})
        assert_that(one).is_equal_to(other, ignore="detail")
        assert_that(_paths(lambda: assert_that(one).is_equal_to(other, ignore="unrelated"))).is_equal_to(["detail"])


class TestTheClassIsAField:
    def test_two_classes_of_one_message_differ_at_it(self):
        paths = _paths(lambda: assert_that(ValueError("x")).is_equal_to(TypeError("x"), ignore="unrelated"))
        assert_that(paths).is_equal_to(["__class__"])

    def test_a_subclass_is_another_class(self):
        with pytest.raises(AssertionFailure):
            assert_that(ApiError(404, "a")).is_equal_to(DerivedError(404, "a"), ignore="unrelated")

    def test_left_out_by_name_it_is_not_compared(self):
        assert_that(ValueError("x")).is_equal_to(TypeError("x"), ignore="__class__")
        assert_that(ValueError("x")).is_equal_to(TypeError("x"), include="args")

    def test_the_failure_names_the_class_once(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(ValueError("a")).is_equal_to(ValueError("b"), ignore="unrelated")
        assert_that(caught.value._message).is_equal_to(
            "Expected <ValueError(.., args=('a',))> to be equal to <ValueError(.., args=('b',))>"
            " ignoring keys <unrelated>, but was not."
        )
        assert_that(repr(comparable_fields(ApiError(404, "a")))).is_equal_to(
            "ApiError(args=('404: a',), code=404, detail='a')"
        )

    def test_a_field_of_that_name_on_anything_else_is_printed(self):
        assert_that(repr(TakenApart(ApiError, {"__class__": DerivedError, "code": 1}))).is_equal_to(
            "ApiError(__class__=<class 'test_exception_fields.DerivedError'>, code=1)"
        )
        assert_that(repr(TakenApart(User, {"__class__": User, "id": 1}))).is_equal_to(
            "User(__class__=<class 'test_exception_fields.User'>, id=1)"
        )

    def test_a_different_class_is_what_the_headline_shows(self):
        with pytest.raises(AssertionFailure) as caught:
            assert_that(ValueError("x")).is_equal_to(TypeError("x"), ignore="unrelated")
        assert_that(caught.value._message).starts_with(
            "Expected <ValueError(__class__=<class 'ValueError'>, ..)> to be equal to"
            " <TypeError(__class__=<class 'TypeError'>, ..)>"
        )


class TestWhereAKeyOptionReachesIt:
    def test_as_an_element_of_a_sequence(self):
        assert_that([ApiError(404, "a")]).is_equal_to([ApiError(404, "b")], ignore=["detail", "args"])
        paths = _paths(lambda: assert_that([ApiError(404, "a")]).is_equal_to([ApiError(500, "a")], ignore="args"))
        assert_that(paths).is_equal_to(["[0].code"])

    def test_under_a_path_that_enters_it(self):
        actual, expected = {"error": ApiError(404, "a")}, {"error": ApiError(404, "b")}
        assert_that(actual).is_equal_to(expected, ignore=[("error", "detail"), ("error", "args")])
        assert_that(_paths(lambda: assert_that(actual).is_equal_to(expected, ignore=("error", "detail")))).is_equal_to(
            ["error.args[0]"]
        )

    def test_under_two_dicts_with_no_path_into_it_its_own_equality_decides(self):
        with pytest.raises(AssertionFailure):
            assert_that({"error": ApiError(404, "a"), "n": 1}).is_equal_to(
                {"error": ApiError(404, "a"), "n": 2}, ignore="n"
            )

    def test_the_matcher_and_a_soft_block_answer_as_the_builder_does(self):
        assert_that(match.equal_to(ApiError(404, "b"), ignore=["detail", "args"]).matches(ApiError(404, "a"))).is_true()
        assert_that(match.equal_to(TypeError("x"), ignore="unrelated").matches(ValueError("x"))).is_false()
        with pytest.raises(AssertionError) as caught, soft_assertions():
            assert_that(ValueError("a")).is_equal_to(ValueError("b"), ignore="unrelated")
        assert_that(str(caught.value)).contains("args[0]: 'a' != 'b'")

    def test_without_a_key_option_nothing_changes(self):
        with pytest.raises(AssertionFailure, match="equality is identity"):
            assert_that(ApiError(404, "a")).is_equal_to(ApiError(404, "a"))


class TestAnExceptionThatHoldsMore:
    """State in neither ``args`` nor ``__dict__`` would be left out unseen, so such a class is not read by fields."""

    def test_an_os_error_keeps_its_filename_outside_both(self):
        one, other = OSError(2, "missing", "a.txt"), OSError(2, "missing", "b.txt")
        assert_that((one.args, vars(one))).is_equal_to((other.args, vars(other)))
        assert_that(comparable_fields(one)).is_none()
        with pytest.raises(TypeError, match="ignore/include requires"):
            assert_that(one).is_equal_to(other, ignore="unrelated")
        with pytest.raises(AssertionFailure):
            assert_that([one]).is_equal_to([other], ignore="unrelated")

    def test_a_class_with_a_slot(self):
        assert_that(comparable_fields(SlottedError(1))).is_none()
        with pytest.raises(TypeError, match="ignore/include requires"):
            assert_that(SlottedError(1)).is_equal_to(SlottedError(2), ignore="unrelated")

    @pytest.mark.parametrize(
        "kind",
        [
            BaseException,
            Exception,
            ValueError,
            TypeError,
            KeyError,
            RuntimeError,
            AssertionError,
            ApiError,
            DerivedError,
        ],
    )
    def test_a_class_that_holds_its_args_and_attributes_alone_is_read(self, kind):
        assert_that(_holds_only_its_args(kind)).is_true()

    @pytest.mark.parametrize(
        "kind",
        [
            OSError,
            FileNotFoundError,
            ImportError,
            SyntaxError,
            UnicodeDecodeError,
            StopIteration,
            SystemExit,
            SlottedError,
        ],
    )
    def test_a_class_that_holds_more_is_not(self, kind):
        assert_that(_holds_only_its_args(kind)).is_false()

    def test_the_layout_is_read_off_type_and_not_as_a_metaclass_spells_it(self):
        size = type.__dict__["__basicsize__"].__get__

        class Spelling(type):
            __basicsize__ = property(lambda cls: size(cls) - tuple.__itemsize__)

        class HidingError(Exception, metaclass=Spelling):
            __slots__ = ("code",)

            def __init__(self, code: int) -> None:
                super().__init__("same")
                self.code = code

        assert_that(HidingError.__basicsize__).is_equal_to(BaseException.__basicsize__)
        assert_that(_holds_only_its_args(HidingError)).is_false()
        with pytest.raises(AssertionFailure):
            assert_that([HidingError(1)]).is_equal_to([HidingError(2)], ignore="unrelated")

    @pytest.mark.skipif(sys.version_info < (3, 11), reason="exception groups arrived in Python 3.11")
    def test_a_group_holds_its_exceptions_outside_both(self):
        group = ExceptionGroup("several", [ValueError("a")])  # noqa: F821  # the name is a builtin from 3.11 on
        assert_that(comparable_fields(group)).is_none()
