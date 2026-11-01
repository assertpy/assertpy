"""Source-level guard: every ``error()`` inside an ``except`` block decides about the caught exception.

``error()`` owns the ``raise``, so whether the exception being handled stays visible above the failure
is settled at the call site and nowhere else.  Nothing else enforces that.  A new wrapping assertion
written without the keyword passes lint, the whole suite and full coverage, which is how two of the
sites below went unnoticed once already.

Read from the source rather than watched at runtime, so a site no test happens to reach is found too,
and so ``builder.error(...)`` counts the same as ``self.error(...)``.  The runtime side of the same
invariant lives in ``TestExceptionContext`` in test_traceback.py.
"""

import ast
import pathlib

import assertpy
from assertpy import assert_that

# Sites that let the caught exception through. An entry without a reason is the bug this module catches.
KEEPS_THE_CAUGHT_EXCEPTION = {
    ("async_assertions.py", "_out_of_time"): (
        "soft/warn branch only, where error() collects or logs and never raises; the strict branch "
        "beside it already raises `from last_error`"
    ),
    ("bytes_mixin.py", "is_valid_utf8"): "the decode error names the offending byte and offset, our message does not",
    ("bytes_mixin.py", "is_valid_encoding"): "same, and it also names an unknown codec",
    ("exception.py", "when_called_with"): "the caught exception is the caller's own bug, its traceback is the point",
    ("exception.py", "_when_called_with_not_expected"): "same",
}


def _module_functions(tree):
    """The module's own top-level functions by name, so a call inside a handler can be followed."""
    return {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _error_calls_in_except_blocks(node, module, functions, function="<module>", in_handler=False, followed=frozenset()):
    """Yield ``(module, function, suppresses)`` for every ``error()`` call reached from an except block.

    Reached, not written: a handler that delegates to a helper still runs it with the exception being
    handled, so the helper is a site too.  One hop, and only into this module's own top-level functions,
    since deeper than that the call graph stops being readable from the syntax.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _error_calls_in_except_blocks(child, module, functions, child.name, in_handler, followed)
            continue
        if isinstance(child, ast.ExceptHandler):
            yield from _error_calls_in_except_blocks(child, module, functions, function, True, followed)
            continue
        if in_handler and isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr == "error":
                yield module, function, any(keyword.arg == "suppress_context" for keyword in child.keywords)
        elif (
            in_handler
            and isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id in functions
            and child.func.id not in followed
        ):
            target = functions[child.func.id]
            yield from _error_calls_in_except_blocks(
                target, module, functions, target.name, True, followed | {child.func.id}
            )
        yield from _error_calls_in_except_blocks(child, module, functions, function, in_handler, followed)


def _sites_keeping_the_caught_exception() -> set[tuple[str, str]]:
    package = pathlib.Path(assertpy.__file__).parent
    trees = [(source.name, ast.parse(source.read_text(encoding="utf-8"))) for source in sorted(package.rglob("*.py"))]
    return {
        (module, function)
        for name, tree in trees
        for module, function, suppresses in _error_calls_in_except_blocks(tree, name, _module_functions(tree))
        if not suppresses
    }


class TestEverySiteDecides:
    def test_the_walk_finds_something(self):
        # a walk that silently matched nothing would make both checks below pass forever
        assert_that(_sites_keeping_the_caught_exception()).is_not_empty()

    def test_no_site_keeps_a_context_by_accident(self):
        undeclared = _sites_keeping_the_caught_exception() - set(KEEPS_THE_CAUGHT_EXCEPTION)
        assert_that(undeclared).described_as("error() inside an except block, without suppress_context").is_empty()

    def test_no_stale_entries(self):
        stale = set(KEEPS_THE_CAUGHT_EXCEPTION) - _sites_keeping_the_caught_exception()
        assert_that(stale).described_as("declared above but no longer keeping a context").is_empty()
