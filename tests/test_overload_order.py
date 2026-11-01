"""Hold the order of the `assert_that()` overloads, which nothing else announces when it breaks.

A `pandas.DataFrame` is assignable to *every* structural protocol, because pandas models column access
with a catch-all attribute.  So the frame overload works only while it is the first shape-keyed one: put
anything else above it and every frame silently resolves to that instead, with no error anywhere.  The
same catch-all is why a checker cannot be asked about it cheaply, and why this reads the source instead.

Two gates, deliberately apart.  This one is about what is written, needs no third-party library, and
runs everywhere.  `tests/test_typing.py` is about what a checker picks, and pins each shape to its view
with `assert_type`.  Neither replaces the other: source order can be right while a checker resolves
elsewhere, and a checker can agree today while an edit reorders the file tomorrow.

The public API snapshot records the overloads too, but it is re-recorded whenever the surface moves, so
a broken invariant travels through it as an ordinary diff.  This says the invariant out loud.
"""

from __future__ import annotations

import ast
import pathlib

from assertpy import assert_that

_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "assertpy" / "assertpy.py"


_TYPING = pathlib.Path(__file__).resolve().parent.parent / "assertpy" / "_engine" / "_typing.py"


def _overload_subjects() -> list[str]:
    """The annotation on ``val`` for each `assert_that` overload, in the order the file declares them."""
    module = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    subjects = []
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if not any(isinstance(item, ast.Name) and item.id == "overload" for item in node.decorator_list):
            continue
        subjects.append(ast.unparse(node.args.args[0].annotation))
    return subjects


def _shape_names(annotation: ast.expr) -> list[str]:
    """The shape names a bound is written with, or `[]` when it is not made of shapes.

    A bound is either one name or a union of them, and a union is an `ast.BinOp` tree rather than a
    list.  Anything with a non-shape in it reads as no shapes at all, so a bound that stops being
    structural stops being counted rather than being counted wrongly.
    """
    match annotation:
        case ast.Name(id=name) if name.endswith("Shape"):
            return [name]
        case ast.BinOp(left=left, op=ast.BitOr(), right=right):
            parts = _shape_names(left) + _shape_names(right)
            return parts if len(parts) == _union_width(annotation) else []
    return []


def _union_width(annotation: ast.expr) -> int:
    """How many operands a `|` tree has, so a union with one non-shape in it cannot read as clean."""
    match annotation:
        case ast.BinOp(left=left, op=ast.BitOr(), right=right):
            return _union_width(left) + _union_width(right)
    return 1


def _shape_bound_typevars() -> dict[str, str]:
    """``{type variable: the shape it is bound to}``, read from where the shapes are declared.

    The overloads key on a bound type variable rather than on the shape itself, so that the view can
    carry the subject type.  Reading the bounds is how this file still knows which overloads are the
    shape-keyed ones, rather than matching on a naming convention that an edit can quietly leave.
    """
    module = ast.parse(_TYPING.read_text(encoding="utf-8"))
    # a union of shapes may carry a name of its own, which the bound then names in its place
    named_unions = {
        node.targets[0].id: node.value
        for node in ast.walk(module)
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.BinOp)
    }
    bounds = {}
    for node in ast.walk(module):
        match node:
            case ast.Assign(
                targets=[ast.Name(id=name)],
                value=ast.Call(func=ast.Name(id="TypeVar"), keywords=keywords),
            ):
                for keyword in keywords:
                    if keyword.arg != "bound":
                        continue
                    # a bound is one name or a union written as a string; reading only the first form hid the umbrella
                    written = keyword.value
                    named = _shape_names(
                        named_unions.get(written.id, written) if isinstance(written, ast.Name) else written
                    )
                    if named:
                        bounds[name] = " | ".join(named)
    return bounds


def _shape_positions(subjects: list[str]) -> list[int]:
    """Where the shape-keyed overloads sit, by the bound of the variable each one keys on."""
    shapes = _shape_bound_typevars()
    return [index for index, name in enumerate(subjects) if name in shapes]


class TestTheOverloadOrder:
    """The frame overload first among the shapes, every shape before the fallback."""

    def test_the_file_declares_overloads_at_all(self):
        # finding nothing would make every assertion here vacuous, so the count is asserted before the order
        assert_that(_overload_subjects()).described_as("overloads of assert_that").is_length(18)

    def test_exactly_one_overload_keys_on_the_frame_shape(self):
        subjects = _overload_subjects()
        frames = [name for name in subjects if _shape_bound_typevars().get(name) == "_FrameShape"]
        assert_that(frames).is_length(1)

    def test_exactly_one_overload_is_the_generic_fallback(self):
        subjects = _overload_subjects()
        assert_that([name for name in subjects if name == "_T"]).is_length(1)

    def test_the_frame_shape_comes_before_every_other_shape(self):
        subjects = _overload_subjects()
        bounds = _shape_bound_typevars()
        frame = next(index for index, name in enumerate(subjects) if bounds.get(name) == "_FrameShape")
        assert_that(frame).described_as(
            "a pandas frame satisfies every shape, so it has to be claimed first"
        ).is_equal_to(min(_shape_positions(subjects)))

    def test_the_capability_umbrella_comes_last_among_the_shapes(self):
        """It matches anything with any capability, so a precise view below it would never be reached.

        The umbrella is the compatibility half of the narrowing: a value the library recognises but no
        overload names keeps the whole builder.  Its bound is a union, which is exactly why it has to
        sit under every shape that names one thing.
        """
        subjects = _overload_subjects()
        bounds = _shape_bound_typevars()
        umbrellas = [index for index, name in enumerate(subjects) if "|" in bounds.get(name, "")]
        assert_that(umbrellas).described_as("exactly one overload keys on a union of shapes").is_length(1)
        assert_that(umbrellas[0]).described_as("a precise shape below the umbrella is never reached").is_equal_to(
            max(_shape_positions(subjects))
        )

    def test_every_shape_comes_before_the_fallback(self):
        subjects = _overload_subjects()
        shapes = _shape_positions(subjects)
        assert_that(max(shapes)).described_as("a shape below the fallback is never reached").is_less_than(
            subjects.index("_T")
        )

    def test_the_shape_block_runs_without_a_wedge_in_it(self):
        """A shape reads only what the overloads above it left, so one wedged in changes every shape below.

        Under the block is a different question, and one overload lives there: the callable view.  It
        used to sit above the shapes and claimed an ASGI or WSGI response, which is a callable and is
        also the one thing an HTTP capability describes, so `has_status_code(200)` on a Starlette or a
        Flask response was a type error in all three checkers while the runtime answered it.
        """
        subjects = _overload_subjects()
        shapes = _shape_positions(subjects)
        block = subjects[min(shapes) : max(shapes) + 1]
        assert_that([name for name in block if name not in _shape_bound_typevars()]).described_as(
            "an overload wedged into the shape block, which changes what the shapes below it see"
        ).is_empty()

    def test_only_the_callable_view_and_the_fallback_follow_the_shapes(self):
        """Named rather than counted, so a second overload appended below the block has to be decided about."""
        subjects = _overload_subjects()
        below = subjects[max(_shape_positions(subjects)) + 1 :]
        assert_that(below).described_as("what a value no shape claimed reaches, in order").is_equal_to(
            ["Callable[..., _P]", "_T"]
        )
