import pytest

import assertpy._inline as _inline
import assertpy.snapshot as _snap
from assertpy import AssertionFailure, assert_that, match
from assertpy._inline import is_literalable


def _written(filename, start, end, text):
    """A row as one process ships it: a call settled on *text*, every run of it taking that literal, located
    in the file as it is now."""
    return (filename, start, end, text, True, [text], [_inline._digest(_inline._read(filename)[0])], text)


class TestCompare:
    def test_dict_pass_and_chains(self):
        assert_that({"id": 1, "name": "Alice"}).matches_inline({"id": 1, "name": "Alice"}).is_type_of(dict)

    def test_scalar_pass(self):
        assert_that(42).matches_inline(42)

    def test_list_pass(self):
        assert_that([1, 2, 3]).matches_inline([1, 2, 3])

    def test_drift_fails(self):
        with pytest.raises(AssertionError):
            assert_that({"id": 1}).matches_inline({"id": 2})


class TestSelective:
    def test_ignore(self):
        assert_that({"id": 99, "name": "Alice"}).matches_inline({"id": 0, "name": "Alice"}, ignore="id")

    def test_tolerance(self):
        assert_that({"x": 1.001}).matches_inline({"x": 1.0}, tolerance=0.01)

    def test_placeholders_pass(self):
        assert_that({"id": 123, "name": "Alice"}).matches_inline(
            {"id": 0, "name": "Alice"}, placeholders={"id": lambda value: isinstance(value, int)}
        )

    def test_placeholder_matcher_checked(self):
        with pytest.raises(AssertionError):
            assert_that({"id": "nope", "name": "Alice"}).matches_inline(
                {"id": 0, "name": "Alice"}, placeholders={"id": lambda value: isinstance(value, int)}
            )

    def test_placeholder_invalid_value(self):
        with pytest.raises(TypeError, match="Matcher instances or callables"):
            assert_that({"id": 1}).matches_inline({"id": 1}, placeholders={"id": 42})

    def test_a_non_matcher_placeholder_is_refused_by_name(self):
        with pytest.raises(TypeError) as failure:
            assert_that({"id": 1}).matches_inline({"id": 1}, placeholders={"id": "nope"})
        assert_that(str(failure.value)).is_equal_to("placeholder values must be Matcher instances or callables")

    def test_placeholder_requires_dict_like(self):
        with pytest.raises((TypeError, AssertionError)):
            assert_that([1, 2]).matches_inline([1, 2], placeholders={"id": lambda value: True})

    def test_a_non_dict_val_is_refused_as_val(self):
        with pytest.raises(TypeError) as failure:
            assert_that([1, 2]).matches_inline([1, 2], placeholders={"id": lambda value: True})
        assert_that(str(failure.value)).starts_with("val must be dict-like")

    def test_a_matcher_placeholder_is_accepted(self):
        # the shape the docs recommend, and a Matcher is not callable, so only the guard's first half admits it
        assert_that({"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Alice"}).matches_inline(
            {"id": "", "name": "Alice"}, placeholders={"id": match.is_uuid()}
        )

    def test_include_restricts_the_comparison(self):
        assert_that({"id": 99, "name": "Alice"}).matches_inline({"id": 0, "name": "Alice"}, include="name")

    def test_a_comparator_owns_its_field(self):
        assert_that({"name": "ALICE"}).matches_inline(
            {"name": "Alice"}, comparators={"name": lambda actual, expected: actual.lower() == expected.lower()}
        )


class TestEmpty:
    def test_empty_without_update_errors(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", False)
        with pytest.raises(AssertionError, match="run --assertpy-snapshot-update"):
            assert_that(1).matches_inline()

    def test_empty_in_ci_forbidden(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", True)
        with pytest.raises(AssertionError, match="CI mode forbids"):
            assert_that(1).matches_inline()

    def test_the_message_without_update_mode_is_exact(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", False)
        with pytest.raises(AssertionError) as failure:
            assert_that(1).matches_inline()
        assert_that(str(failure.value)).is_equal_to(
            "inline snapshot is empty; run --assertpy-snapshot-update to record it"
        )

    def test_the_ci_message_is_exact(self, monkeypatch):
        monkeypatch.setattr(_snap, "_CI_MODE", True)
        with pytest.raises(AssertionError) as failure:
            assert_that(1).matches_inline()
        assert_that(str(failure.value)).is_equal_to(
            "inline snapshot is empty and CI mode forbids recording it - record it locally with"
            " --assertpy-snapshot-update and commit the source"
        )


class TestLiteralable:
    def test_non_finite_floats_rejected(self):
        # nan/inf render as bare names (invalid source), so they must not be recordable as literals
        assert_that(is_literalable(float("nan"))).is_false()
        assert_that(is_literalable(float("inf"))).is_false()
        assert_that(is_literalable(float("-inf"))).is_false()
        assert_that(is_literalable({"r": float("nan")})).is_false()

    def test_finite_values_literalable(self):
        assert_that(is_literalable({"a": [1, 2.5], "b": "x", "c": True, "d": None})).is_true()

    def test_apply_records_preserves_crlf(self, tmp_path):
        source = tmp_path / "c.py"
        source.write_bytes(b"a = matches_inline()\r\nb = 1\r\n")
        normalized = "a = matches_inline()\nb = 1\n"
        insert_at = normalized.index("matches_inline(") + len("matches_inline(")
        assert_that(
            _inline.apply_inline_records([_written(str(source), insert_at, insert_at, "42")], str(tmp_path))
        ).is_empty()
        assert_that(source.read_bytes()).is_equal_to(b"a = matches_inline(42)\r\nb = 1\r\n")


def test_inline_mismatch_names_its_kind_and_the_update_flag():
    # the file-backed branch names its snapshot; the inline one must not word the same failure differently
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"id": 7, "status": "paid"}).matches_inline({"id": 7, "status": "pending"})
    message = str(exc_info.value)
    assert_that(message).contains("Inline snapshot")
    assert_that(message).contains("--assertpy-snapshot-update")


def test_the_inline_mismatch_ends_by_naming_its_kind_and_the_way_to_accept_it():
    with pytest.raises(AssertionError) as failure:
        assert_that({"id": 7}).matches_inline({"id": 8})
    assert_that(str(failure.value)).ends_with(
        " Inline snapshot; rerun with --assertpy-snapshot-update to rewrite the literal here."
    )


def test_inline_mismatch_keeps_the_diff():
    with pytest.raises(AssertionError) as exc_info:
        assert_that({"a": {"b": 1}}).matches_inline({"a": {"b": 2}})
    assert_that(exc_info.value.diff.entries[0].path).is_equal_to("a.b")


class TestFormatLiteral:
    """A value too wide for one line is wrapped and re-indented, which is what makes the rewritten
    test source still readable.  Nothing else exercised the multi-line branch."""

    def test_a_wide_value_wraps_and_keeps_its_first_line(self):
        value = {f"key_{index}": f"value_{index}" for index in range(12)}
        rendered = _inline._format_literal(value, column=0)
        lines = rendered.split("\n")
        assert_that(lines).is_not_empty()
        assert_that(lines[0]).starts_with("{'key_0': 'value_0'")

    def test_continuation_lines_are_indented_to_the_column(self):
        value = {f"key_{index}": f"value_{index}" for index in range(12)}
        rendered = _inline._format_literal(value, column=8)
        continuations = rendered.split("\n")[1:]
        assert_that(continuations).is_not_empty()
        for line in continuations:
            assert_that(line).starts_with(" " * 8)

    def test_the_first_line_is_not_indented(self):
        # it is spliced in where the call already sits, so padding it would double the indentation
        value = {f"key_{index}": f"value_{index}" for index in range(12)}
        assert_that(_inline._format_literal(value, column=8)[0]).is_equal_to("{")

    def test_dict_order_is_the_value_order_not_sorted(self):
        assert_that(_inline._format_literal({"b": 1, "a": 2}, column=0)).is_equal_to("{'b': 1, 'a': 2}")

    def test_the_wrap_width_shrinks_with_the_column(self):
        # 86 characters on one line: it fits the 116 budget at column 0 and not the 76 left at column 40
        value = list(range(24))
        assert_that(_inline._format_literal(value, column=0)).does_not_contain("\n")
        assert_that(_inline._format_literal(value, column=40)).contains("\n")

    def test_a_value_that_fits_stays_on_one_line(self):
        assert_that(_inline._format_literal({"a": 1}, column=0)).does_not_contain("\n")


class TestLiteralableKeys:
    def test_a_key_that_is_not_a_literal_rejects_the_dict(self):
        # the values are fine; only the key is not, and a dict is only rewritable when both are
        assert_that(is_literalable({object(): 1})).is_false()

    def test_literal_keys_are_accepted(self):
        assert_that(is_literalable({("a", 1): "x", 2: "y"})).is_true()


class TestApplyRecordsWithSeveralEdits:
    """Two recordings in one file. Applied in ascending order the first edit shifts every offset after
    it, so the second lands in the wrong place; they are applied highest-offset-first for that reason,
    and one edit per file could never show it."""

    def test_both_edits_land_where_they_were_recorded(self, tmp_path):
        source = tmp_path / "two.py"
        source.write_text("a = matches_inline()\nb = matches_inline()\n", encoding="utf-8", newline="")
        text = source.read_text(encoding="utf-8")
        first = text.index("matches_inline(") + len("matches_inline(")
        second = text.index("matches_inline(", first) + len("matches_inline(")
        assert_that(
            _inline.apply_inline_records(
                [_written(str(source), first, first, "'first'"), _written(str(source), second, second, "'second'")],
                str(tmp_path),
            )
        ).is_empty()
        assert_that(source.read_text(encoding="utf-8")).is_equal_to(
            "a = matches_inline('first')\nb = matches_inline('second')\n"
        )

    def test_a_non_ascii_literal_round_trips(self, tmp_path):
        # explicit encoding both ways: on a runner whose locale is not UTF-8 the default would mangle this
        source = tmp_path / "u.py"
        source.write_text("a = matches_inline()\n", encoding="utf-8", newline="")
        insert_at = source.read_text(encoding="utf-8").index("matches_inline(") + len("matches_inline(")
        assert_that(
            _inline.apply_inline_records([_written(str(source), insert_at, insert_at, "'ключ'")], str(tmp_path))
        ).is_empty()
        assert_that(source.read_bytes()).is_equal_to("a = matches_inline('ключ')\n".encode())


class TestASnapshotMismatchCarriesTheRecordTheComparisonComposed:
    """A snapshot comparison is `is_equal_to` underneath, and it re-raises with a snapshot-aware
    message. Building a fresh exception around that message used to drop the composed record, which
    made a snapshot mismatch the only comparison failure without one."""

    def test_the_record_survives_the_re_wrap(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).matches_inline({"a": 2})
        outcome = failure.value._outcome
        assert_that(outcome).is_not_none()
        assert_that(outcome.actual_provided).is_true()
        assert_that(outcome.has_expected).is_true()

    def test_the_record_holds_the_snapshot_aware_message_not_the_inner_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(AssertionFailure) as failure:
            assert_that({"a": 1}).matches_inline({"a": 2})
        # as with a directly raised failure: `__str__` appends the diff, the record holds the composed message
        assert_that(failure.value._outcome.message).contains("Inline snapshot")
        assert_that(str(failure.value)).starts_with(failure.value._outcome.message)


class TestOnlySourceGoesIntoSource:
    """An inline snapshot rewrites the test file, so what it writes has to be a literal that parses."""

    def test_a_subclass_of_a_literal_type_is_refused(self):
        """An `IntEnum` is an `int` and wrote `<Status.ACTIVE: 1>`, which is not source at all."""
        import enum

        class Status(enum.IntEnum):
            ACTIVE = 1

        assert_that(is_literalable(Status.ACTIVE)).described_as("the member").is_false()
        assert_that(is_literalable([Status.ACTIVE])).described_as("inside a list").is_false()
        assert_that(is_literalable({"state": Status.ACTIVE})).described_as("under a key").is_false()
        with pytest.raises(TypeError, match="must be a dict/list/tuple/set of scalars"):
            _snap._inline_literal_or_raise(Status.ACTIVE)

    def test_containers_of_their_own_kind_are_refused(self):
        import collections

        assert_that(is_literalable(collections.OrderedDict(a=1))).described_as("OrderedDict").is_false()
        assert_that(is_literalable(collections.namedtuple("Point", "x")(1))).described_as("namedtuple").is_false()

    def test_the_plain_literals_still_pass(self):
        assert_that(is_literalable({"a": [1, (2, 3), {4}], "b": None})).is_true()
        assert_that(is_literalable(True)).described_as("bool").is_true()
