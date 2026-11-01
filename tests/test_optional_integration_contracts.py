"""Exercise the allure and behave integrations against the real libraries.

Everywhere else these two are tested against stand-ins: `test_pytest_plugin.py` patches
`assertpy.pytest_plugin.allure` with a `MagicMock`, and `test_behave_matchers.py` puts a mock in
`sys.modules`. That verifies our branching and nothing about the libraries. A mock accepts any call,
so a renamed parameter or a moved attribute in either package passes those tests untouched, and
Dependabot is configured to propose exactly such bumps.

These tests are the other half: they skip unless the real package is installed, and then call the
same code paths through it. The suite's coverage gate deliberately runs *without* allure installed
(with it present the `except ImportError` fallback in `pytest_plugin.py` goes unexecuted instead),
so this file earns its own CI cell rather than joining the gating one.
"""

from __future__ import annotations

import pytest

from assertpy import assert_that
from assertpy._engine._diff import _build_equality_diff
from assertpy.behave_matchers import ASSERTPY_TYPES, register_assertpy_types
from assertpy.errors import PollSample, PollTrace


class TestAllureContract:
    """What `_attach_allure` needs from the installed `allure` package."""

    @pytest.fixture(autouse=True)
    def _require_allure(self):
        pytest.importorskip("allure", reason="allure-pytest is an optional extra")

    def test_the_plugin_sees_allure_as_present(self):
        from assertpy import pytest_plugin

        assert_that(pytest_plugin._HAS_ALLURE).is_true()

    def test_the_json_attachment_type_we_pass_exists(self):
        import allure

        assert_that(dir(allure.attachment_type)).contains("JSON")

    @pytest.mark.parametrize("mode", ["full", "diff", "off"])
    def test_attaching_a_real_diff_does_not_raise(self, mode):
        # `allure.attach` outside a listener is a no-op, so this reaches the real function with real arguments
        from assertpy.pytest_plugin import _attach_allure

        diff = _build_equality_diff({"name": "alice", "age": 30}, {"name": "alice", "age": 31})
        _attach_allure({"age": 30}, {"age": 31}, diff, named_actual=True, named_expected=True, mode=mode)

    def test_attaching_a_polling_trace_does_not_raise(self):
        from assertpy.pytest_plugin import _attach_allure

        trace = PollTrace(
            samples=[
                PollSample(elapsed=0.0, outcome="error", value=None, detail="ConnectionError('boot')"),
                PollSample(elapsed=0.4, outcome="fail", value={"state": "PENDING"}, detail="Expected <...>"),
            ],
            total_polls=2,
            dropped=0,
            elapsed=0.4,
            summary="probe recovered",
        )
        _attach_allure(None, None, None, named_actual=False, named_expected=False, trace=trace)


class TestBehaveContract:
    """What `register_assertpy_types()` needs from the installed `behave` package."""

    @pytest.fixture(autouse=True)
    def _require_behave(self):
        pytest.importorskip("behave", reason="behave is an optional extra")

    def test_every_type_reaches_behave_own_registry(self):
        from behave.matchers import ParseMatcher

        register_assertpy_types()
        registered = {name: ParseMatcher.has_registered_type(name) for name in ASSERTPY_TYPES}
        assert_that(registered).does_not_contain_value(False)

    def test_a_registered_parser_is_the_one_we_wrote(self):
        from behave.matchers import ParseMatcher

        register_assertpy_types()
        assert_that(ParseMatcher.TYPE_REGISTRY["PositiveInt"]("7")).is_equal_to(7)
        assert_that(ParseMatcher.TYPE_REGISTRY["BoolLike"]("yes")).is_true()
        assert_that(ParseMatcher.TYPE_REGISTRY["NonEmptyString"](" x ")).is_equal_to("x")
