"""What the three checkers make of `assert_that()` on real pandas, polars and numpy values, as measured.

`tests/test_typing.py` pins the same relation against stand-in classes, and that is the version which
runs everywhere.  A stand-in proves the overload is written correctly, and it cannot prove that a real
`DataFrame` still matches it, because the shapes are structural and the structures are somebody else's
to change.  A `pandas-stubs` release that stops declaring `pivot` would move every frame here to the
generic builder, and nothing in the stand-in file would notice.

**The measurement is only as good as the environment it ran in.**  `ty` takes its environment from
`VIRTUAL_ENV`, then from a `.venv` beside the project, and its target from `requires-python`'s lower
bound.  None of that shows up in the result, so a run against an interpreter without the stubs reads as
a clean sheet rather than as a broken measurement.  Every checker is therefore given its interpreter and
its target version explicitly, and `frame-value` is here as the witness: it pins a type only the stubs
can supply, so an environment without them goes red instead of quiet.

## The one disagreement, and what it costs

`assert_that(pandas.Series)` resolves three different ways.  A pandas `Series` reaches every member
through the catch-all `__getattr__` in `pandas-stubs`, so `series.pivot` and `series.strides` are both
`Any`, and an `Any` member satisfies any protocol member.  A `Series` therefore matches *every* shape
for every checker, and what separates the three answers is not the shapes but how each resolves an
overload set with more than one match: mypy takes the first, ty takes another, pyright treats it as
unresolved and hands back the builder.

No choice of discriminating member moves this, because none of them is ever anything but `Any`.  The
only lever that would is naming `pandas.Series` nominally in an overload, which means importing pandas
into the typed surface and giving up the zero-dependency property the shapes exist to keep.

## The other boundary, which is not a disagreement

`numpy.ndarray[Any, Any]` covers a zero-dimensional array, and one carries `__array__`, `strides` and `__len__`
like any other.  So `array-sized` reads clean here while `assert_that(numpy.array(1)).is_not_empty()`
raises: numpy answers `len()` with a `TypeError` of its own, and `length_of()` is written to let a
raising `__len__` through rather than to report the value as unsized.  The dimension is not in the
stubs, so no shape separates the two, and this file cannot state the boundary as a case.
`tests/test_dataframe.py` measures it instead.

The cost is bounded and it is one method.  `_FrameAssertion` and `_ArrayAssertion` carry the same
surface apart from `is_frame_equal`, so a ty user calling `is_frame_equal` on a `Series` is told it is
not there, while it works.  mypy and pyright users pay nothing.  Recorded rather than fixed, and
recorded here so that it stops being invisible.
"""

from __future__ import annotations

# Cases every checker accepts in silence: the view resolved as pinned, and it carries the call.
SILENT = frozenset(
    {
        "pandas-frame",
        "polars-frame",
        "numpy-array",
        "polars-series",
        "pandas-index",
        "frame-sized",
        "frame-membership",
        "frame-non-membership",
        "frame-walk",
        "frame-own",
        "frame-array",
        "frame-value",
        "array-sized",
        "array-non-membership",
        "array-own",
        "array-value",
    }
)

# The witness that the stubs resolved: it pins `pandas.Index[str]`, which is `Any` without them.
STUB_WITNESS = "frame-value"

# Disagreements kept on purpose, reasoned in the module docstring. A missing checker accepts the pinned answer.
DIVERGING = {
    "pandas-series": {"ty": {"type-assertion-failure"}, "mypy": {"assert-type"}},
}

# Calls outside the value's runtime domain, which the narrowed view refuses. On the generic builder
# every one of them type-checks and then raises.
REFUSED = {
    "frame-not-a-document": {
        "ty": {"missing-attribute"},
        "mypy": {"attr-defined"},
        "pyright": {"reportAttributeAccessIssue"},
    },
    "frame-not-ordered": {
        "ty": {"missing-attribute"},
        "mypy": {"attr-defined"},
        "pyright": {"reportAttributeAccessIssue"},
    },
    "frame-not-text": {
        "ty": {"missing-attribute"},
        "mypy": {"attr-defined"},
        "pyright": {"reportAttributeAccessIssue"},
    },
}
