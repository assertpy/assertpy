"""The static check for `assert_that()` statements that assert nothing.

Both halves matter equally.  A check that misses the shape it exists for is useless, and a check that
reports a working chain gets switched off after the first false alarm and never switched back on, so
the negative cases below are the ones that keep it usable.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap
import warnings
from types import SimpleNamespace

import pytest

from assertpy import DanglingAssertionWarning, assert_that
from assertpy._dangling import (
    _ENDS_ON,
    _NO_ASSERTION,
    _NO_VERDICT,
    _NOT_AWAITED,
    _NOT_CALLED,
    _UNDER_ASSERT,
    ALLOW_MARKER,
    findings,
    read_module,
)
from assertpy._engine._operations import WHAT_IT_DOES
from assertpy.pytest_plugin import (
    _dangling_enabled,
    _dangling_entries,
    _item_scope,
    _report_dangling,
    pytest_collection_modifyitems,
)

PREAMBLE = "from assertpy import assert_that, assert_warn, fail, soft_assertions\n"


def scan(body: str, preamble: str = PREAMBLE):
    return findings(preamble + textwrap.dedent(body), "sample.py")


class TestTheShapesItReports:
    def test_a_builder_built_and_thrown_away(self):
        found = scan("""
            def test_x():
                assert_that([1, 2, 3])
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NO_ASSERTION.format(name="assert_that"))
        assert_that(found[0].scope).is_equal_to(("test_x",))

    def test_an_assertion_looked_up_and_never_called(self):
        found = scan("""
            def test_x():
                assert_that(1).is_equal_to
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_a_longer_chain_that_is_never_called(self):
        found = scan("""
            def test_x():
                assert_that(1).not_.is_none
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_assert_warn_is_an_entry_point_too(self):
        assert_that(scan("def test_x():\n    assert_warn('x')\n")).is_length(1)

    @pytest.mark.parametrize(
        ("preamble", "call"),
        [
            ("from assertpy import assert_that as at\n", "at(1)"),
            ("import assertpy\n", "assertpy.assert_that(1)"),
            ("import assertpy as ap\n", "ap.assert_that(1)"),
            ("from assertpy import *  # noqa: F403\n", "assert_that(1)  # noqa: F405"),
        ],
        ids=["aliased", "module", "aliased module", "star"],
    )
    def test_every_spelling_of_the_import_is_resolved(self, preamble, call):
        assert_that(scan(f"def test_x():\n    {call}\n", preamble)).is_length(1)

    def test_the_message_quotes_the_module_spelling_when_that_is_what_was_written(self):
        found = scan("def test_x():\n    ap.assert_that(1)\n", "import assertpy as ap\n")
        assert_that(found[0].message).is_equal_to(_NO_ASSERTION.format(name="ap.assert_that"))

    def test_a_finding_at_module_scope_belongs_to_no_test(self):
        found = scan("assert_that(1)\n")
        assert_that(found).is_length(1)
        assert_that(found[0].scope).described_as("nothing encloses it").is_empty()

    def test_a_nested_def_keeps_the_whole_chain(self):
        found = scan("""
            def test_x():
                def inner():
                    assert_that(1)
                inner()
            """)
        assert_that(found).extracting("scope").is_equal_to([("test_x", "inner")])

    def test_findings_come_back_in_source_order(self):
        found = scan("""
            def test_x():
                assert_that(2)
                assert_that(3)
            """)
        assert_that(found).extracting("lineno").is_equal_to(sorted(found and [f.lineno for f in found]))


class TestAChainThatEndsBeforeAnyVerdict:
    """The tail asserts nothing, which the bare-builder shape and this one have in common."""

    @pytest.mark.parametrize(
        ("body", "tail"),
        [
            ("assert_that(lambda: None).raises(ValueError)", "raises"),
            ("assert_that(lambda: None).does_not_raise(ValueError)", "does_not_raise"),
            ("assert_that([{'k': 1}]).extracting('k')", "extracting"),
            ("assert_that([1]).first()", "first"),
            ("assert_that(1).described_as('important')", "described_as"),
            ("assert_that(lambda: 1).eventually_sync()", "eventually_sync"),
        ],
        ids=["raises", "does_not_raise", "extracting", "pivot", "described_as", "sync poll"],
    )
    def test_the_finding_names_the_tail_and_what_it_does(self, body, tail):
        found = scan(f"def test_x():\n    {body}\n")
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_ENDS_ON[_NO_VERDICT[tail]].format(name=tail))

    def test_an_awaited_poll_with_no_assertion_on_it_is_reported(self):
        found = scan("async def test_x():\n    await assert_that(lambda: 1).eventually()\n")
        assert_that(found).is_length(1)
        assert_that(found[0].message).contains("eventually()")

    @pytest.mark.parametrize(
        "body",
        [
            "assert_that(lambda: None).raises(ValueError).when_called_with()",
            "assert_that(err).caused_by(ValueError)",
            "assert_that(err).has_root_cause(ValueError)",
        ],
        ids=["when_called_with", "caused_by", "has_root_cause"],
    )
    def test_a_hybrid_that_asserts_on_its_way_past_is_left_alone(self, body):
        assert_that(scan(f"def test_x():\n    {body}\n")).is_empty()

    def test_every_kind_the_register_names_has_a_sentence_here(self):
        assert_that(set(_ENDS_ON)).is_equal_to(set(WHAT_IT_DOES))


class TestAChainAnAssertReads:
    """`assert` in front of a dangling chain, which is the same defect wearing a disguise.

    The wrapper is what makes it dangerous: a builder and a bound method are both truthy, so the line
    is green whatever the value is, while reading as though it asserted.  Nothing else sees it.  Ruff's
    useless-expression check does not apply to a value that is consumed, and coverage marks the line
    run.
    """

    @pytest.mark.parametrize(
        "body",
        [
            "assert assert_that(1)",
            "assert assert_that([1]).is_empty",
            "assert assert_that([{'k': 1}]).extracting('k')",
            "assert assert_that(lambda: None).raises(ValueError)",
            "assert assert_that(1).described_as('important')",
            "assert assert_that(lambda: 1).eventually_sync()",
            "assert assert_that({'id': 1}).has_id",
            "assert assert_that(1).not_",
            "assert assert_that(1).check",
            "assert assert_that(1).error",
            "assert assert_that(1).logger",
            "assert assert_that(1).description",
            "assert assert_that([1]).check().is_empty",
            "assert assert_that([1]).check().not_.is_none",
        ],
        ids=[
            "the builder itself",
            "an assertion left uncalled",
            "a pivot",
            "an expectation nothing calls",
            "a description",
            "a polling chain",
            "a dynamic assertion left uncalled",
            "the negation proxy, read and not driven",
            "the verdict entry, read and not called",
            "the failure entry, read and not called",
            "an adapter truthy on every subject there is",
            "builder state the value under test does not decide",
            "an assertion left uncalled behind a verdict",
            "the same through the negation proxy",
        ],
    )
    def test_it_is_reported(self, body):
        found = scan(f"def test_x():\n    {body}\n")
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_UNDER_ASSERT)

    @pytest.mark.parametrize(
        "body",
        [
            "assert assert_that([1]).is_empty()",
            "assert assert_that([1]).check().is_empty()",
            "assert assert_that([1]).check().is_empty().passed",
            "assert assert_that([1]).check().is_empty().description",
            "assert assert_that([1]).value",
            "assert assert_that([1]).val",
            "assert assert_that([1]).value == [1]",
            "assert [1]",
        ],
        ids=[
            "an assertion that ran",
            "a verdict, which is falsy when it failed",
            "a field of that verdict",
            "another field of the same verdict",
            "the value the builder holds",
            "the same under its compatibility name",
            "a comparison over that value",
            "nothing of ours at all",
        ],
    )
    def test_working_usage_is_left_alone(self, body):
        assert_that(scan(f"def test_x():\n    {body}\n")).is_empty()

    def test_the_shape_really_does_pass_on_a_value_that_should_fail(self):
        """The measurement the check exists for, kept here so it cannot rot into a story."""
        assert assert_that([1]).is_empty  # assertpy: allow-dangling
        assert assert_that([1])  # assertpy: allow-dangling
        with pytest.raises(AssertionError):
            assert assert_that([1]).is_empty()

    def test_a_verdict_is_falsy_when_it_failed_which_is_why_it_is_left_alone(self):
        assert_that(bool(assert_that([1]).check().is_empty())).is_false()
        assert_that(bool(assert_that([]).check().is_empty())).is_true()

    @pytest.mark.parametrize("name", sorted(_NO_VERDICT))
    def test_the_two_contexts_agree_on_every_registered_name(self, name):
        """Derived from the register rather than listed, so a new operation cannot reach only one path."""
        chain = f"assert_that(1).{name}()"
        assert_that(scan(f"def test_x():\n    {chain}\n")).described_as("as a statement").is_length(1)
        assert_that(scan(f"def test_x():\n    assert {chain}\n")).described_as("under assert").is_length(1)

    def test_an_assertion_left_uncalled_behind_a_verdict_really_does_pass(self):
        """The shape the first version of the exemption swallowed whole."""
        assert assert_that([1]).check().is_empty  # assertpy: allow-dangling

    def test_a_bare_check_is_left_alone_because_the_name_may_not_be_ours(self):
        """A recorded boundary, not an oversight.

        `assert assert_that(x).check()` is truthy and asserts nothing, but reporting it means deciding
        the name belongs to this library, and a project may register an extension called `check` that
        asserts by itself.  A read attribute needs no such guess, since nothing was called at all.
        """
        found = scan("""
            def test_x():
                assert assert_that([1]).check()
            """)
        assert_that(found).is_empty()

    def test_the_marker_silences_one(self):
        assert_that(scan(f"def test_x():\n    assert assert_that(1)  # {ALLOW_MARKER}\n")).is_empty()


class TestTheOnlyStatementOfARaisingBlock:
    """The one place a dangling chain cannot leave a green test.

    A `pytest.raises` body of exactly one statement leaves the argument nothing to hide behind: that
    statement runs, and either it raises, which is what the test asserts, or the block turns the test
    red by itself.

    Every wider version of this exemption measured unsound, and each negative case below is a shape
    that passed in silence under one of them.
    """

    @pytest.mark.parametrize(
        ("preamble", "opener"),
        [
            ("import pytest\n", "pytest.raises(TypeError)"),
            ("import pytest as pt\n", "pt.raises(TypeError)"),
            ("from pytest import raises\n", "raises(TypeError)"),
            ("import pytest\n", "pytest.raises(TypeError, match='x')"),
            ("import pytest\n", "pytest.RaisesGroup(ValueError)"),
        ],
        ids=["pytest.raises", "aliased module", "imported by name", "with a match", "RaisesGroup"],
    )
    def test_a_chain_alone_in_one_is_left_alone(self, preamble, opener):
        body = f"def test_x():\n    with {opener}:\n        assert_that([1]).extracting('k')\n"
        assert_that(scan(body, PREAMBLE + preamble)).is_empty()

    def test_a_second_statement_can_supply_the_exception_instead(self):
        """Measured as a real run: the chain asserts nothing, the `raise` satisfies the block, green."""
        found = scan(
            "def test_x():\n    with pytest.raises(TypeError):\n        assert_that([1])\n        raise TypeError\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)

    def test_a_second_statement_can_leave_the_chain_unreachable(self):
        found = scan(
            "def test_x():\n    with pytest.raises(TypeError):\n        raise TypeError\n        assert_that([1])\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)

    def test_two_statements_on_one_line_are_still_two(self):
        """Why the exemption is keyed on the statement rather than on its line."""
        found = scan(
            "def test_x():\n    with pytest.raises(TypeError):\n        assert_that([1]); raise TypeError\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)

    def test_a_sibling_manager_can_raise_from_its_own_exit(self):
        """`with pytest.raises(TypeError), Boom():` is satisfied by `Boom`, so the body never had to."""
        found = scan(
            "def test_x():\n    with pytest.raises(TypeError), Boom():\n        assert_that([1])\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)

    @pytest.mark.parametrize(
        "opener",
        ["pytest.warns(UserWarning)", "pytest.deprecated_call()"],
        ids=["warns", "deprecated_call"],
    )
    def test_a_block_that_expects_its_body_to_finish_is_not_one_of_these(self, opener):
        """`warns` records what the body emits and wants it to run to the end, unlike `raises`."""
        body = f"def test_x():\n    with {opener}:\n        assert_that([1]).extracting('k')\n"
        assert_that(scan(body, PREAMBLE + "import pytest\n")).is_length(1)

    def test_a_helper_of_the_suites_own_named_raises_is_not_pytests(self):
        """Matched through the import rather than by name, the way the entry points are."""
        body = "def test_x():\n    with raises():\n        assert_that([1])\n"
        assert_that(scan(body, PREAMBLE + "from helpers import raises\n")).is_length(1)

    def test_a_module_that_rebinds_pytest_is_not_importing_it(self):
        """The same guard `_bindings` applies to this library's own names."""
        found = scan(
            "def test_x():\n    pytest = fake\n    with pytest.raises(TypeError):\n        assert_that([1])\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)

    @pytest.mark.parametrize(
        "preamble",
        [
            "from contextlib import nullcontext as raises\nfrom pytest import raises\n",
            "from pytest import raises\nfrom contextlib import nullcontext as raises\n",
        ],
        ids=["shadowed before", "shadowed after"],
    )
    def test_a_spelling_two_imports_bind_belongs_to_neither(self, preamble):
        """Which import wins is the order they are written in, which a name cannot be read for.

        At run time `raises` here is `nullcontext`, the block catches nothing, and the test passes with
        the chain having asserted nothing.
        """
        body = "def test_x():\n    with raises():\n        assert_that([1])\n"
        assert_that(scan(body, PREAMBLE + preamble)).is_length(1)

    def test_a_shadowed_pytest_module_is_not_pytest(self):
        found = scan(
            "def test_x():\n    with pytest.raises(TypeError):\n        assert_that([1])\n",
            PREAMBLE + "import pytest\nimport fake as pytest\n",
        )
        assert_that(found).is_length(1)

    def test_a_statement_after_the_block_is_still_reported(self):
        found = scan(
            "def test_x():\n"
            "    with pytest.raises(TypeError):\n"
            "        assert_that(1).is_length('x')\n"
            "    assert_that([1])\n",
            PREAMBLE + "import pytest\n",
        )
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NO_ASSERTION.format(name="assert_that"))

    def test_an_unrelated_with_block_is_not_exempt(self):
        assert_that(scan("def test_x():\n    with lock:\n        assert_that([1])\n")).is_length(1)

    def test_a_soft_block_is_not_one_of_them(self):
        """A soft block collects failures and reaches its end, so a dangling chain in one is silent."""
        body = "def test_x():\n    with soft_assertions():\n        assert_that([1]).extracting('k')\n"
        assert_that(scan(body)).is_length(1)


class TestWhatItLeavesAlone:
    @pytest.mark.parametrize(
        "body",
        [
            "assert_that(1).is_equal_to(1)",
            "assert_that(lambda: None).raises(ValueError).when_called_with()",
            "assert_that([{'k': 1}]).extracting('k').is_equal_to([1])",
            "assert_that(assert_that('x')).is_instance_of(object)",
            "builder = assert_that(1)",
            "print(assert_that(1).value)",
            "fail('boom')",
            "return assert_that(1)",
        ],
        ids=[
            "terminal assertion",
            "pivot then assertion",
            "extracting then assertion",
            "builder as the value under test",
            "bound to a name",
            "read as a value",
            "a function that asserts on its own",
            "returned to the caller",
        ],
    )
    def test_working_usage_is_not_reported(self, body):
        assert_that(scan(f"def test_x():\n    {body}\n")).is_empty()

    def test_a_soft_block_is_not_reported(self):
        found = scan("""
            def test_x():
                with soft_assertions():
                    assert_that(1).is_equal_to(2)
            """)
        assert_that(found).is_empty()

    def test_a_module_that_never_imports_the_package_is_skipped(self):
        # somebody else's `assert_that` is not ours to judge
        assert_that(findings("def assert_that(x): ...\n\ndef test_x():\n    assert_that(1)\n", "other.py")).is_empty()

    def test_a_call_through_an_unrelated_module_is_not_ours(self):
        assert_that(scan("def test_x():\n    other.assert_that(1)\n", "import other\n")).is_empty()

    def test_an_attribute_statement_unrelated_to_the_builder_is_not_ours(self):
        assert_that(scan("def test_x():\n    self.value.attr\n")).is_empty()

    def test_a_chain_whose_head_is_a_call_on_something_else_is_not_ours(self):
        assert_that(scan("def test_x():\n    helper(1).attr\n")).is_empty()

    def test_a_computed_callee_is_not_ours(self):
        # `funcs['assert_that'](1)` has no Name or Attribute to match, and guessing would be wrong
        assert_that(scan("def test_x():\n    funcs['assert_that'](1)\n")).is_empty()


class TestSilencingADeliberateOne:
    """Asserting nothing is sometimes the point: a benchmark measuring what a builder costs, a test of
    this library's own machinery. Without a per-line escape the only answer is turning the check off,
    and a check switched off wholesale is a check nobody runs.

    This project had exactly one such line, in its own benchmarks, found by widening the scan.
    """

    def test_a_marked_statement_is_left_out(self):
        found = scan("""
            def test_x():
                assert_that(1)  # assertpy: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_a_missing_call_can_be_marked_too(self):
        found = scan("""
            def test_x():
                assert_that(1).is_equal_to  # assertpy: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_the_marker_reaches_the_end_of_a_wrapped_call(self):
        found = scan("""
            def test_x():
                assert_that(
                    1
                )  # assertpy: allow-dangling
            """)
        assert_that(found).is_empty()

    def test_it_silences_only_the_statement_it_sits_on(self):
        found = scan("""
            def test_x():
                assert_that(1)  # assertpy: allow-dangling
                assert_that(2)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].lineno).described_as("the unmarked line, not the marked one").is_equal_to(5)

    def test_the_constant_is_what_the_docs_tell_people_to_write(self):
        assert_that(ALLOW_MARKER).is_equal_to("assertpy: allow-dangling")

    def test_a_bare_noqa_does_not_silence_it(self):
        # ruff's suppression belongs to ruff: borrowing it would silence this check and both tools at once
        found = scan("""
            def test_x():
                assert_that(1)  # noqa: F401
            """)
        assert_that(found).is_length(1)


class TestAwaitedChains:
    def test_an_awaited_dangling_builder_is_reported(self):
        found = scan("""
            async def test_x():
                await assert_that(1)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].scope).is_equal_to(("test_x",))

    def test_an_awaited_working_chain_is_not(self):
        found = scan("""
            async def test_x():
                await assert_that(1).eventually().is_equal_to(1)
            """)
        assert_that(found).is_empty()


def test_unparsable_source_raises_rather_than_reporting_nothing():
    with pytest.raises(SyntaxError):
        findings("def (:\n", "broken.py")


class TestReadingAModule:
    """The text of a test module as the interpreter decodes it, read here rather than in a child run."""

    def test_a_declared_encoding_is_the_one_it_is_read_in(self, tmp_path):
        module = tmp_path / "test_cp1251.py"
        module.write_bytes("# coding: cp1251\nимя = 1\n".encode("cp1251"))
        assert_that(read_module(module)).is_equal_to("# coding: cp1251\nимя = 1\n")

    def test_a_first_line_that_is_not_utf8_and_names_no_encoding_is_read_with_the_bytes_replaced(self, tmp_path):
        module = tmp_path / "test_undeclared.py"
        module.write_bytes(b"# \xcf\xf0\xe8\nx = 1\n")
        assert_that(read_module(module)).is_equal_to("# \ufffd\ufffd\ufffd\nx = 1\n")

    def test_a_byte_order_mark_is_not_part_of_the_text(self, tmp_path):
        module = tmp_path / "test_bom.py"
        module.write_bytes(b"\xef\xbb\xbfx = 1\n")
        assert_that(read_module(module)).is_equal_to("x = 1\n")


class TestAProjectsOwnWrapper:
    """Suites wrap `assert_that` in a helper of their own, and the check cannot see through it.

    `assertpy_dangling_entries` names those helpers.  The name has to be bound by an import, which is
    the only thing standing between "your wrapper" and "any function anywhere that happens to be called
    `check`", so every negative case below is load-bearing.
    """

    WRAPPED = "from project.helpers import check\n"

    def test_an_unconfigured_wrapper_is_invisible(self):
        assert_that(scan("def test_x():\n    check(1)\n", self.WRAPPED)).is_empty()

    def test_a_configured_wrapper_reads_as_a_builder(self):
        found = findings(self.WRAPPED + "def test_x():\n    check(1)\n", "sample.py", frozenset({"check"}))
        assert_that(found).is_length(1)
        assert_that(found[0].message).described_as("named as the reader wrote it").is_equal_to(
            _NO_ASSERTION.format(name="check")
        )
        assert_that(found[0].scope).is_equal_to(("test_x",))

    def test_a_configured_wrapper_that_does_assert_is_left_alone(self):
        found = findings(
            self.WRAPPED + "def test_x():\n    check(1).is_equal_to(1)\n", "sample.py", frozenset({"check"})
        )
        assert_that(found).is_empty()

    def test_a_missing_call_on_a_configured_wrapper_is_the_other_shape(self):
        found = findings(self.WRAPPED + "def test_x():\n    check(1).is_equal_to\n", "sample.py", frozenset({"check"}))
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_CALLED)

    def test_an_alias_on_the_import_is_followed(self):
        source = "from project.helpers import check as verify\n\ndef test_x():\n    verify(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(1)

    def test_a_relative_import_of_the_wrapper_counts(self):
        source = "from .helpers import check\n\ndef test_x():\n    check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(1)

    def test_a_local_function_of_the_same_name_is_not_claimed(self):
        # the guard that keeps this from becoming a linter for everybody's `check()`: no import, no claim
        source = "def check(value):\n    return value\n\n\ndef test_x():\n    check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_reaching_the_wrapper_through_its_module_is_not_recognised(self):
        # a documented limit: `helpers.check` would need the config to name a module, and suites use `from ... import`
        source = "import project.helpers\n\ndef test_x():\n    project.helpers.check(1)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_the_marker_silences_a_configured_wrapper_too(self):
        source = f"{self.WRAPPED}\ndef test_x():\n    check(1)  # {ALLOW_MARKER}\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_empty()

    def test_the_library_entry_points_still_work_alongside_one(self):
        source = f"{PREAMBLE}{self.WRAPPED}\ndef test_x():\n    assert_that(1)\n    check(2)\n"
        assert_that(findings(source, "sample.py", frozenset({"check"}))).is_length(2)


class TestThePluginWiring:
    """The check itself is pure, so these cover the part around it: reading each file once, and
    attaching a finding to the test that contains it.

    Driven by calling the hooks rather than through a nested pytest run, which is how the plugin's
    other hooks are tested here: the suite runs with `-p no:assertpy`, so nothing else reaches them.
    """

    @staticmethod
    def _config(enabled: bool, entries=frozenset()):
        return SimpleNamespace(_assertpy_dangling_enabled=enabled, _assertpy_dangling_entries=entries)

    @staticmethod
    def _item(config, path, function_name=None, nodeid="t.py::test_x"):
        # `__qualname__`, not `__name__`: the plugin reads the whole chain, so a fake item carries one too
        function = SimpleNamespace(__name__=function_name, __qualname__=function_name) if function_name else None
        return SimpleNamespace(config=config, path=path, function=function, nodeid=nodeid)

    def test_the_flag_off_records_nothing(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = self._config(enabled=False)
        pytest_collection_modifyitems(None, config, [self._item(config, source)])
        assert_that(config._assertpy_dangling).is_empty()

    def test_a_file_is_read_once_however_many_tests_it_contributed(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = self._config(enabled=True)
        items = [self._item(config, source, "test_x"), self._item(config, source, "test_y")]
        pytest_collection_modifyitems(None, config, items)
        assert_that(config._assertpy_dangling).is_length(1)
        assert_that(config._assertpy_dangling[source]).is_length(1)

    def test_the_finding_lands_on_the_test_that_contains_it(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(
            PREAMBLE
            + textwrap.dedent("""
                def test_clean():
                    assert_that(1).is_equal_to(1)


                def test_bare():
                    assert_that(1)
                """),
            encoding="utf-8",
        )
        config = self._config(enabled=True)
        clean = self._item(config, source, "test_clean")
        bare = self._item(config, source, "test_bare")
        pytest_collection_modifyitems(None, config, [clean, bare])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(clean)
            assert_that(caught).described_as("the clean test must not carry the other one's finding").is_empty()
            _report_dangling(bare)
        assert_that(caught).is_length(1)
        assert_that(caught[0].category).is_equal_to(DanglingAssertionWarning)
        assert_that(str(caught[0].filename)).is_equal_to(str(source))

    def test_a_finding_outside_any_def_goes_to_the_first_test_to_run(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "assert_that(1)\n\n\ndef test_x():\n    pass\n", encoding="utf-8")
        config = self._config(enabled=True)
        item = self._item(config, source, "test_x")
        pytest_collection_modifyitems(None, config, [item])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(caught).is_length(1)
        with warnings.catch_warnings(record=True) as again:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(again).is_empty()

    def test_the_configured_entries_reach_the_scan(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text("from project.helpers import check\n\ndef test_x():\n    check(1)\n", encoding="utf-8")
        config = self._config(enabled=True, entries=frozenset({"check"}))
        pytest_collection_modifyitems(None, config, [self._item(config, source, "test_x")])
        assert_that(config._assertpy_dangling[source]).is_length(1)

    def test_a_config_from_before_the_setting_existed_is_tolerated(self):
        # the plugin's other tests build configs by hand, and a missing attribute must mean "none"
        config = SimpleNamespace(_assertpy_dangling_enabled=False)
        pytest_collection_modifyitems(None, config, [])
        assert_that(config._assertpy_dangling).is_empty()

    def test_two_findings_in_one_test_become_one_warning(self, tmp_path):
        # under `-W error` the first warning leaves the hook, so reporting one by one would drop the rest
        source = tmp_path / "t.py"
        body = textwrap.dedent("""
            def test_x():
                assert_that(1)
                assert_that(2)
            """)
        source.write_text(PREAMBLE + body, encoding="utf-8")
        config = self._config(enabled=True)
        item = self._item(config, source, "test_x")
        pytest_collection_modifyitems(None, config, [item])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(caught).described_as("one warning, not two").is_length(1)
        assert_that(str(caught[0].message)).contains("and 1 more in this test, at line 5")
        assert_that(config._assertpy_dangling[source]).described_as("neither is left behind").is_empty()

    def test_an_item_with_no_function_still_takes_a_module_scope_finding(self, tmp_path):
        # a hook driven by hand has no function to name, and a finding belonging to no test must land somewhere
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "assert_that(1)\n", encoding="utf-8")
        config = self._config(enabled=True)
        item = self._item(config, source)
        pytest_collection_modifyitems(None, config, [item])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(item)
        assert_that(caught).is_length(1)

    def test_an_item_without_a_config_is_left_alone(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(SimpleNamespace(nodeid="t.py::test_x"))
        assert_that(caught).is_empty()


class TestTurningItOn:
    """The flag is for trying it once; the ini setting is for a project that wants it every run.

    The flag wins, so somebody can switch it on for one command without editing a config the whole
    team shares.
    """

    @staticmethod
    def _config(*, flag=False, ini="off"):
        return SimpleNamespace(
            getoption=lambda name: flag if name == "assertpy_dangling" else None,
            getini=lambda name: ini if name == "assertpy_dangling" else None,
        )

    def test_the_ini_setting_alone_turns_it_on(self):
        assert_that(_dangling_enabled(self._config(ini="on"))).is_true()

    def test_off_by_default(self):
        assert_that(_dangling_enabled(self._config())).is_false()

    def test_the_flag_wins_over_a_config_that_says_off(self):
        assert_that(_dangling_enabled(self._config(flag=True, ini="off"))).is_true()

    def test_the_setting_is_read_case_and_space_insensitively(self):
        assert_that(_dangling_enabled(self._config(ini="  ON  "))).is_true()

    def test_an_unreadable_setting_warns_and_stays_off(self):
        # silence would be wrong: a typo that quietly disables a check is how it stops running unnoticed
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            enabled = _dangling_enabled(self._config(ini="yes"))
        assert_that(enabled).is_false()
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("assertpy_dangling").contains("falling back to 'off'")

    def test_the_flag_still_wins_over_an_unreadable_setting(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert_that(_dangling_enabled(self._config(flag=True, ini="yes"))).is_true()


class TestReadingTheEntriesSetting:
    """`assertpy_dangling_entries` is a list of names, and a name that cannot bind is worth saying so.

    Silence on a bad value is the failure mode this check cannot afford: it would look configured and
    cover nothing.
    """

    @staticmethod
    def _config(*values):
        return SimpleNamespace(getini=lambda name: list(values) if name == "assertpy_dangling_entries" else None)

    def test_nothing_configured_reads_as_nothing(self):
        assert_that(_dangling_entries(self._config())).is_empty()

    def test_names_are_read_and_trimmed(self):
        assert_that(_dangling_entries(self._config("check", "  verify  "))).is_equal_to({"check", "verify"})

    def test_a_dotted_path_is_dropped_with_a_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            entries = _dangling_entries(self._config("check", "helpers.verify"))
        assert_that(entries).is_equal_to({"check"})
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("'helpers.verify'").contains(
            "is not a plain name and cannot be matched"
        )

    def test_several_bad_names_are_reported_together_and_read_as_plural(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert_that(_dangling_entries(self._config("a.b", "c d"))).is_empty()
        assert_that(caught).is_length(1)
        assert_that(str(caught[0].message)).contains("'a.b', 'c d'").contains(
            "are not plain names and cannot be matched"
        )


class TestANameThisModuleBindsItselfIsNotOurs:
    """Importing `assert_that` and then shadowing the name means the call in the body is somebody
    else's, and reporting it is a false alarm on their function.

    Raised by an external review. All three shapes reported before the fix.
    """

    @pytest.mark.parametrize(
        "body",
        [
            "def test_x(assert_that):\n    assert_that(1)\n",
            "def test_x():\n    assert_that = lambda value: value\n    assert_that(1)\n",
            "assert_that = print\n\n\ndef test_x():\n    assert_that(1)\n",
            "def test_x():\n    for assert_that in (print,):\n        assert_that(1)\n",
            "def test_x():\n    with open(__file__) as assert_that:\n        assert_that(1)\n",
        ],
        ids=["fixture parameter", "local lambda", "module rebinding", "loop target", "context manager"],
    )
    def test_a_shadowed_entry_point_is_left_alone(self, body):
        assert_that(scan(body)).is_empty()

    def test_shadowing_one_entry_point_does_not_silence_the_other(self):
        found = scan("def test_x(assert_warn):\n    assert_that(1)\n")
        assert_that(found).described_as("only the shadowed name is dropped").is_length(1)

    def test_an_exception_name_shadows_too(self):
        # `except ... as assert_that` holds a plain string rather than a `Name`, so it needs its own branch
        body = """
            def test_x():
                try:
                    pass
                except ValueError as assert_that:
                    assert_that(1)
            """
        assert_that(scan(body)).is_empty()

    def test_a_bare_except_is_not_mistaken_for_a_binding(self):
        # `except ValueError:` carries `name=None`, which must not be read as a shadowed name
        found = scan("""
            def test_x():
                try:
                    assert_that(1)
                except ValueError:
                    pass
            """)
        assert_that(found).is_length(1)

    def test_a_module_alias_can_be_shadowed_too(self):
        assert_that(scan("def test_x(assertpy):\n    assertpy.assert_that(1)\n", "import assertpy\n")).is_empty()


class TestTheMarkerIsAComment:
    """It is found by tokenising, not by searching the line for its own words.

    The first implementation searched the text, so a statement holding the marker inside a string was
    exempt without anybody writing a comment: an assertion *about* the marker's own wording silently
    stopped being checked.
    """

    def test_the_marker_inside_a_string_does_not_silence_anything(self):
        found = scan(f'def test_x():\n    assert_that("# {ALLOW_MARKER}")\n')
        assert_that(found).is_length(1)

    def test_nor_does_it_across_a_wrapped_call(self):
        found = scan(f'def test_x():\n    assert_that(\n        "{ALLOW_MARKER}"\n    )\n')
        assert_that(found).is_length(1)

    def test_a_real_comment_still_silences(self):
        assert_that(scan(f"def test_x():\n    assert_that(1)  # {ALLOW_MARKER}\n")).is_empty()

    def test_a_real_comment_on_the_closing_line_still_silences(self):
        assert_that(scan(f"def test_x():\n    assert_that(\n        1\n    )  # {ALLOW_MARKER}\n")).is_empty()

    def test_a_comment_on_a_neighbouring_statement_silences_only_that_one(self):
        found = scan(f"def test_x():\n    assert_that(1)  # {ALLOW_MARKER}\n    assert_that(2)\n")
        assert_that(found).is_length(1)
        assert_that(found[0].lineno).is_equal_to(4)


class TestUnderARealPytestRun:
    """Driven through an actual pytest process, not by calling the hooks.

    The rest of this file drives them directly, because the suite runs with `-p no:assertpy`. That
    misses everything about how findings are handed to items, which is where the defect lived: two
    classes defining `test_same` had their findings matched by function name, so both went to whichever
    ran first and the second test passed while holding a dangling assertion.
    """

    @staticmethod
    def _run(tmp_path, body: str, *flags: str) -> subprocess.CompletedProcess[str]:
        (tmp_path / "test_generated.py").write_text(body, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\nassertpy_dangling = on\n", encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(tmp_path),
                "-p",
                "assertpy",
                "-p",
                "no:randomly",
                "-q",
                "--tb=no",
                "-c",
                str(tmp_path / "pytest.ini"),
                *flags,
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )

    SAME_NAME = (
        "from assertpy import assert_that\n\n\n"
        "class TestOne:\n    def test_same(self):\n        assert_that(1)\n\n\n"
        "class TestTwo:\n    def test_same(self):\n        assert_that(2)\n"
    )

    def test_two_tests_of_the_same_name_each_get_their_own_finding(self, tmp_path):
        result = self._run(tmp_path, self.SAME_NAME, "-W", "error::assertpy.DanglingAssertionWarning")
        assert_that(result.stdout).contains("TestOne::test_same").contains("TestTwo::test_same")
        assert_that(result.stdout).described_as("neither may pass while holding one").contains("2 errors")

    def test_both_are_reported_as_warnings_without_the_escalation(self, tmp_path):
        result = self._run(tmp_path, self.SAME_NAME)
        assert_that(result.stdout.count("DanglingAssertionWarning")).is_equal_to(2)
        assert_that(result.stdout).contains("2 passed")

    def test_two_findings_in_one_test_arrive_together(self, tmp_path):
        # under `-W error` a second warning is never reached: one aggregated warning keeps the second line visible
        body = "from assertpy import assert_that\n\n\ndef test_two():\n    assert_that(1)\n    assert_that(2)\n"
        reported = self._run(tmp_path, body)
        assert_that(reported.stdout).contains("and 1 more in this test, at line 6")
        assert_that(reported.stdout.count("DanglingAssertionWarning")).described_as("one per test").is_equal_to(1)
        escalated = self._run(tmp_path, body, "-W", "error::assertpy.DanglingAssertionWarning")
        assert_that(escalated.stdout).contains("1 error")

    def test_a_finding_in_a_nested_class_reaches_its_own_test(self, tmp_path):
        # `item.cls` names only the innermost class, so the chains lined up once the plugin read `__qualname__`
        body = (
            "from assertpy import assert_that\n\n\n"
            "class TestOuter:\n    class TestInner:\n        def test_nested(self):\n            assert_that(1)\n"
        )
        result = self._run(tmp_path, body, "-W", "error::assertpy.DanglingAssertionWarning")
        assert_that(result.stdout).contains("TestInner::test_nested").contains("1 error")

    def test_a_clean_suite_says_nothing(self, tmp_path):
        body = "from assertpy import assert_that\n\n\ndef test_clean():\n    assert_that(1).is_equal_to(1)\n"
        result = self._run(tmp_path, body, "-W", "error::assertpy.DanglingAssertionWarning")
        assert_that(result.stdout).contains("1 passed").does_not_contain("Dangling")


class TestEveryFindingReachesExactlyOneTest:
    """The invariant behind the same-name defect, stated once and checked through a real run.

    Two properties together: nothing is reported twice, and nothing is silently dropped. The second is
    the one that broke, and it broke quietly - a test held a dangling assertion and passed.
    """

    MODULE = (
        "from assertpy import assert_that\n\n\n"
        "assert_that('module scope')\n\n\n"
        "class TestOne:\n"
        "    def test_same(self):\n        assert_that(1)\n\n"
        "    def test_two_lines(self):\n        assert_that(2)\n        assert_that(3)\n\n\n"
        "class TestTwo:\n"
        "    def test_same(self):\n        assert_that(4)\n\n"
        "    class TestNested:\n"
        "        def test_deep(self):\n            assert_that(5)\n\n\n"
        "def test_plain():\n    assert_that(6)\n"
    )

    def test_no_test_holding_a_dangling_assertion_can_pass(self, tmp_path):
        (tmp_path / "test_generated.py").write_text(self.MODULE, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\nassertpy_dangling = on\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(tmp_path),
                "-p",
                "assertpy",
                "-p",
                "no:randomly",
                "-q",
                "--tb=no",
                "-c",
                str(tmp_path / "pytest.ini"),
                "-W",
                "error::assertpy.DanglingAssertionWarning",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )
        for name in (
            "TestOne::test_same",
            "TestOne::test_two_lines",
            "TestTwo::test_same",
            "TestNested::test_deep",
            "test_plain",
        ):
            assert_that(result.stdout).described_as(f"{name} was not reported").contains(name)
        assert_that(result.stdout).described_as("none of them may pass").contains("5 errors")

    def test_every_statement_is_accounted_for_exactly_once(self, tmp_path):
        (tmp_path / "test_generated.py").write_text(self.MODULE, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\nassertpy_dangling = on\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(tmp_path),
                "-p",
                "assertpy",
                "-p",
                "no:randomly",
                "-q",
                "--tb=no",
                "-c",
                str(tmp_path / "pytest.ini"),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )
        source = (tmp_path / "test_generated.py").read_text(encoding="utf-8")
        expected = len(findings(source, "test_generated.py"))
        # one warning per test, naming the lines it stands for, so every finding is a warning or named inside one
        reported = result.stdout.count("DanglingAssertionWarning") + result.stdout.count("more in this test")
        assert_that(reported).described_as(f"{expected} findings in the file").is_equal_to(expected)


class TestAPollThatIsNeverAwaited:
    """The runtime warning needs the chain to be reclaimed; the source says it at collection."""

    def test_a_chain_written_without_await(self):
        found = scan("""
            async def test_x():
                assert_that(probe).eventually().is_equal_to(1)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_AWAITED)
        assert_that(found[0].scope).is_equal_to(("test_x",))

    def test_a_longer_chain_written_without_await(self):
        found = scan("""
            async def test_x():
                assert_that(probe).eventually(timeout=2).not_.is_empty().is_length(3)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_AWAITED)

    def test_an_awaited_chain_is_not_reported(self):
        assert_that(scan("async def test_x():\n    await assert_that(p).eventually().is_equal_to(1)\n")).is_empty()

    def test_the_synchronous_poll_needs_no_await(self):
        assert_that(scan("def test_x():\n    assert_that(p).eventually_sync().is_equal_to(1)\n")).is_empty()

    def test_a_chain_handed_to_a_runner_is_not_reported(self):
        """It is an argument rather than a statement, so whether it is awaited is that call's business."""
        assert_that(scan("def test_x():\n    asyncio.run(assert_that(p).eventually().is_equal_to(1))\n")).is_empty()

    def test_a_chain_bound_to_a_name_is_not_reported(self):
        assert_that(scan("async def test_x():\n    chain = assert_that(p).eventually().is_equal_to(1)\n")).is_empty()

    def test_a_chain_closed_on_the_spot_is_not_reported(self):
        """The chain itself stays quiet about a `close()`, so the two halves of the rule agree."""
        found = scan("""
            async def test_x():
                assert_that(p).eventually().is_equal_to(1).close()
            """)
        assert_that(found).is_empty()

    def test_a_close_that_takes_arguments_is_not_the_discard(self):
        """Only a bare `close()` is the coroutine one; anything taking arguments is somebody else's."""
        found = scan("""
            async def test_x():
                assert_that(p).eventually().is_equal_to(1).close(wait=True)
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_AWAITED)

    def test_a_chain_that_calls_something_else_is_still_reported(self):
        found = scan("""
            async def test_x():
                assert_that(p).eventually().is_equal_to(1).described_as("x")
            """)
        assert_that(found).is_length(1)
        assert_that(found[0].message).is_equal_to(_NOT_AWAITED)

    def test_the_marker_silences_it(self):
        found = scan("""
            async def test_x():
                assert_that(probe).eventually().is_equal_to(1)  # assertpy: allow-dangling
            """)
        assert_that(found).is_empty()


class TestTheScopeChainReadOffTheItem:
    """The chain has to line up with what the static pass recorded, part for part."""

    @staticmethod
    def _item(qualname):
        return SimpleNamespace(function=SimpleNamespace(__qualname__=qualname))

    def test_a_method_of_a_nested_class_keeps_every_class_in_the_chain(self):
        # `item.cls` names only the innermost, and the two chains then failed to line up
        assert_that(_item_scope(self._item("TestOuter.TestInner.test_it"))).is_equal_to(
            ("TestOuter", "TestInner", "test_it")
        )

    def test_the_locals_marker_a_nested_def_adds_is_dropped(self):
        assert_that(_item_scope(self._item("TestOne.helper.<locals>.test_it"))).is_equal_to(
            ("TestOne", "helper", "test_it")
        )

    def test_an_item_with_no_function_at_all_has_no_scope(self):
        assert_that(_item_scope(SimpleNamespace())).is_equal_to(())


class TestOneWarningNamesAllOfThem:
    """The head of the one warning is the first finding's own message, and the rest are listed after it."""

    def test_three_findings_in_one_test_are_one_warning_naming_the_rest(self, tmp_path):
        source = tmp_path / "t.py"
        body = textwrap.dedent("""
            def test_x():
                assert_that(1)
                assert_that(2)
                assert_that(3)
            """)
        source.write_text(PREAMBLE + body, encoding="utf-8")
        config = SimpleNamespace(_assertpy_dangling_enabled=True, _assertpy_dangling_entries=frozenset())
        item = SimpleNamespace(
            config=config, path=source, function=SimpleNamespace(__qualname__="test_x"), nodeid="t.py::test_x"
        )
        pytest_collection_modifyitems(None, config, [item])
        first = config._assertpy_dangling[source][0].message
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _report_dangling(item)
        message = str(caught[0].message)
        assert_that(message).starts_with(first)
        assert_that(message).contains("and 2 more in this test, at lines 5, 6")


class TestCollectionScansEveryFileItWasGiven:
    """Every file handed to collection is read, and the four getattr defaults on the way are live."""

    def test_a_second_file_is_still_read_after_one_that_was_already_seen(self, tmp_path):
        first, second = tmp_path / "a.py", tmp_path / "b.py"
        for path in (first, second):
            path.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = SimpleNamespace(_assertpy_dangling_enabled=True, _assertpy_dangling_entries=frozenset())
        items = [
            SimpleNamespace(config=config, path=first, function=None, nodeid="a"),
            SimpleNamespace(config=config, path=first, function=None, nodeid="a2"),
            SimpleNamespace(config=config, path=second, function=None, nodeid="b"),
        ]
        pytest_collection_modifyitems(None, config, items)
        assert_that(config._assertpy_dangling).contains_key(first, second)

    def test_an_item_that_carries_no_path_is_stepped_over(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = SimpleNamespace(_assertpy_dangling_enabled=True, _assertpy_dangling_entries=frozenset())
        pathless = SimpleNamespace(config=config, function=None, nodeid="?")
        real = SimpleNamespace(config=config, path=source, function=None, nodeid="t")
        pytest_collection_modifyitems(None, config, [pathless, real])
        assert_that(config._assertpy_dangling).contains_key(source)

    def test_a_config_that_never_configured_scans_nothing(self, tmp_path):
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = SimpleNamespace()
        pytest_collection_modifyitems(None, config, [SimpleNamespace(config=config, path=source, function=None)])
        assert_that(config._assertpy_dangling).is_empty()

    def test_the_scan_runs_without_the_wrapper_names_setting(self, tmp_path):
        # the setting arrived after the check did, and a config from before it must still scan
        source = tmp_path / "t.py"
        source.write_text(PREAMBLE + "def test_x():\n    assert_that(1)\n", encoding="utf-8")
        config = SimpleNamespace(_assertpy_dangling_enabled=True)
        pytest_collection_modifyitems(None, config, [SimpleNamespace(config=config, path=source, function=None)])
        assert_that(config._assertpy_dangling[source]).is_length(1)
