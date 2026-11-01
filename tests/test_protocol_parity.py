"""Parity between the typed Protocols and the concrete ``AssertionBuilder``.

The Protocols in :mod:`assertpy._engine._typing` are hand-maintained and exist only under ``TYPE_CHECKING``,
so nothing at runtime stops them from advertising a method the concrete builder does not have (or
whose signature no longer accepts the declared arguments).  These tests parse the module with ``ast``
and verify every declared method against the real class, so that drift fails the suite instead of
surfacing as a user's ``AttributeError`` on a method their IDE offered.

The reverse direction is asserted too, per mixin rather than against the whole surface.  Each Protocol
is the narrowed view ``assert_that`` returns for one family of types, so a method added to
``StringMixin`` and not to ``_StringAssertion`` is invisible to every caller holding a ``str`` - it
works at runtime and fails the type check.  A curated subset is still a subset of something, and which
methods are deliberately left out is written below as data rather than as a claim in this docstring.
"""

import ast
import inspect
import itertools
from pathlib import Path

import pytest

import assertpy._engine._typing
from assertpy import (
    _satisfies,
    assert_that,
    base,
    bytes_mixin,
    collection,
    contains,
    dataframe,
    date,
    dynamic,
    exception,
    extracting,
    file,
    helpers,
    http_mixin,
    json_mixin,
    numeric,
    snapshot,
    string,
    warning,
)
from assertpy import dict as dict_mixin
from assertpy.assertpy import AssertionBuilder

_SENTINEL = object()

# Pairs that say the same thing and must stay apart. The gate below would force a shared base,
# and one such base widened `contains` until `"abc".contains(123)` type-checked.
_SHARED_ON_PURPOSE: frozenset[tuple[str, str, str]] = frozenset(
    {
        # one spelling, three questions: keys, bytes, elements, and so its negation. A shared base would be untyped
        ("contains", "_BytesAssertion", "_DictAssertion"),
        ("contains", "_BytesAssertion", "_CollectionShapedAssertion"),
        ("contains", "_CollectionShapedAssertion", "_DictAssertion"),
        ("does_not_contain", "_BytesAssertion", "_DictAssertion"),
        ("does_not_contain", "_BytesAssertion", "_CollectionShapedAssertion"),
        ("does_not_contain", "_CollectionShapedAssertion", "_DictAssertion"),
        # `returned` binds the call's return through `self`, which ty solves on no base that hides the parameter
        ("returned", "_CompletedAssertion", "_WarnedAssertion"),
        # narrowing `satisfies` redeclares the whole pair, whose first half is the core's `TypeIs` form
        # everywhere. Only the second half narrows, to `Matcher[str]` and `Matcher[_N]`
        ("satisfies", "_NumericAssertion", "_TextAssertion"),
        # `matches_structure` takes a mapping, a model or an attrs instance. Only the mapping has a view
        # of its own, and since only mypy sees an attrs class, the object view carries the other two
        ("matches_structure", "_DictAssertion", "_ObjectAssertion"),
    }
)

_VALUE_VIEWS: frozenset[str] = frozenset(
    {
        "_CoreAssertion",
        "_ObjectAssertion",
        "_StringAssertion",
        "_NumericAssertion",
        "_ComplexAssertion",
        "_BoolAssertion",
        "_IterableAssertion",
        "_DictAssertion",
        "_DateAssertion",
        "_DateTimeAssertion",
        "_PathAssertion",
        "_BytesAssertion",
        "_CallableAssertion",
        "_FrameAssertion",
        "_ArrayAssertion",
        "_InvokedAssertion",
        # the other two landings of `when_called_with()`, and the three expectation views that reach them
        "_WarnedAssertion",
        "_CompletedAssertion",
        "_ExpectedRaiseAssertion",
        "_ExpectedWarningAssertion",
        "_ExpectedCompletionAssertion",
        # not a dispatch type but what every pipeline step hands back: always a `list`, whatever went in
        "_ListAssertion",
    }
)

# Which protocol carries which capability, by equality and not containment: both directions fail
# quietly, and one of them offered `exists()` on the text of an exception.
_CAPABILITY_CARRIERS: dict[str, tuple[str, ...]] = {
    "_WalkAssertion": (
        "_StructureAssertion",
        "_IterableAssertion",
        "_ListAssertion",
        "_DictAssertion",
        "_CollectionShapedAssertion",
        "_ArrayLikeAssertion",
        "_FrameAssertion",
        "_ArrayAssertion",
    ),
    "_JsonAssertion": (
        "_StructureAssertion",
        "_IterableAssertion",
        "_ListAssertion",
        "_DictAssertion",
    ),
    "_CollectionShapedAssertion": ("_ArrayLikeAssertion", "_FrameAssertion", "_ArrayAssertion"),
    "_ArrayLikeAssertion": ("_FrameAssertion", "_ArrayAssertion"),
    "_SizedAssertion": (
        "_TextAssertion",
        "_StringAssertion",
        "_InvokedAssertion",
        "_WarnedAssertion",
        "_IterableAssertion",
        "_ListAssertion",
        "_DictAssertion",
        "_BytesAssertion",
        "_ArrayAssertion",
        "_ArrayLikeAssertion",
        "_CollectionShapedAssertion",
        "_FrameAssertion",
    ),
    "_FilesystemAssertion": ("_StringAssertion", "_PathAssertion"),
    "_RealNumberAssertion": ("_NumericAssertion", "_BoolAssertion"),
    "_ZeroAssertion": ("_NumericAssertion", "_BoolAssertion", "_ComplexAssertion"),
    "_MembershipAssertion": (
        "_TextAssertion",
        "_StringAssertion",
        "_InvokedAssertion",
        "_WarnedAssertion",
        "_IterableAssertion",
        "_ListAssertion",
        "_BytesAssertion",
        "_ArrayAssertion",
        "_ArrayLikeAssertion",
        "_CollectionShapedAssertion",
        "_FrameAssertion",
    ),
    "_StructureAssertion": ("_IterableAssertion", "_ListAssertion", "_DictAssertion"),
    "_RepeatableAssertion": (
        "_TextAssertion",
        "_StringAssertion",
        "_InvokedAssertion",
        "_WarnedAssertion",
        "_IterableAssertion",
        "_ListAssertion",
    ),
    # what a message and a string share, which is everything except reading the value as a path
    "_TextAssertion": ("_StringAssertion", "_InvokedAssertion", "_WarnedAssertion"),
}

# Where a protocol redeclares what it inherits in order to narrow it. The pair of overloads is
# repeated whole, so its unchanged half looks like a copy while `Matcher[str]` is the entire point.
_NARROWED_ON_PURPOSE: frozenset[tuple[str, str]] = frozenset(
    {
        ("_NumericAssertion", "satisfies"),
        ("_TextAssertion", "satisfies"),
        # the refinements answer with the factory's view for the refined type: the core pair with a ladder
        ("_ObjectAssertion", "is_not_none"),
        ("_ObjectAssertion", "is_instance_of"),
        ("_ObjectAssertion", "is_instance_of_any"),
        # the string view keeps its result type on the pivots, which lets one be read as a path and not the other
        ("_StringAssertion", "first"),
        ("_StringAssertion", "last"),
        ("_StringAssertion", "element"),
        ("_StringAssertion", "single"),
        # the quantifiers narrow to each view's element; the structure capability is shared, so there it is `Any`
        ("_IterableAssertion", "each"),
        ("_IterableAssertion", "all_satisfy"),
        ("_DictAssertion", "each"),
        ("_DictAssertion", "all_satisfy"),
    }
)

# Which Protocols must between them declare every public method of a mixin. Several mixins are
# reachable from more than one view, so the requirement is coverage by the union, not membership.
_COVERAGE: dict[type, tuple[str, ...]] = {
    base.BaseMixin: ("_CoreAssertion",),
    bytes_mixin.BytesMixin: ("_BytesAssertion",),
    collection.CollectionMixin: ("_IterableAssertion",),
    contains.ContainsMixin: ("_IterableAssertion", "_StringAssertion"),
    # the datetime view alone: all seven refuse a plain date at run time, and pooling the two would let a name
    # dropped from one be supplied by the other.  The other direction, a view carrying *part* of a mixin, was
    # measured and refused: 55 of the 117 pairs are partial, holding 210 declarations, and "the runtime answers,
    # the view is silent" runs 19 to 35 per view, about 450 in all.  `tests/api_snapshot.json` already fails a
    # removal, so what stays open is an addition to a shared mixin, and deriving that needs a real argument for
    # each of the 157 methods: with a stand-in, a refusal about the argument reads the same as a type that
    # cannot answer
    date.DateMixin: ("_DateTimeAssertion",),
    dict_mixin.DictMixin: ("_DictAssertion",),
    exception.ExceptionMixin: (
        "_InvokedAssertion",
        "_CallableAssertion",
        "_ExpectedRaiseAssertion",
        "_ExpectedCompletionAssertion",
        "_CompletedAssertion",
    ),
    extracting.ExtractingMixin: ("_DictAssertion", "_IterableAssertion"),
    file.FileMixin: ("_PathAssertion",),
    json_mixin.JsonMixin: ("_DictAssertion", "_IterableAssertion"),
    numeric.NumericMixin: ("_NumericAssertion",),
    snapshot.SnapshotMixin: ("_CoreAssertion",),
    string.StringMixin: ("_StringAssertion",),
    warning.WarningMixin: ("_CallableAssertion", "_ExpectedWarningAssertion"),
    _satisfies.SatisfiesMixin: ("_IterableAssertion", "_CoreAssertion", "_DictAssertion"),
    dynamic.DynamicMixin: (),
    helpers.HelpersMixin: (),
    dataframe.DataFrameMixin: ("_FrameAssertion", "_ArrayAssertion"),
    http_mixin.HttpMixin: (),
}

# The two families with no narrowed view: neither a DataFrame nor an HTTP response matches an
# overload, so the call lands on the fallback, which is the class carrying these methods.
_UNTYPED: frozenset[str] = frozenset({"decoded_as_json"})

# The bases that carry no assertions, written out because anything not listed has to be either a
# protocol of this file or an error.
_NOT_A_PROTOCOL_BASE: frozenset[str] = frozenset({"Protocol", "Generic"})


def _base_name(base: ast.expr) -> str | None:
    """The name of a protocol base, whether it is written plain or parameterised.

    `_RepeatableAssertion[str]` is a `Subscript`, not a `Name`, and reading only names made this walk
    quietly skip an inherited capability: the reverse check then reported four methods as declared
    nowhere while a caller could reach all four.

    Anything else is refused out loud rather than skipped.  A base written `other.SomeAssertion` is an
    `ast.Attribute`, and returning ``None`` for it would erase an inheritance edge from the graph while
    every check in this file stayed green: the whole point here is that a lost edge is loud.
    """
    if isinstance(base, ast.Subscript):
        base = base.value
    if isinstance(base, ast.Name):
        if base.id in _NOT_A_PROTOCOL_BASE:
            return None
        if base.id.endswith("Assertion"):
            return base.id
    raise AssertionError(
        f"unrecognised base {ast.unparse(base)!r} in the typed surface: this walk resolves plain names "
        "only, so either name it locally or teach _base_name how to reach it"
    )


def _protocol_classes():
    """Return ``{name: (own_methods, protocol_bases)}`` for every Protocol in the typed surface."""
    source = Path(assertpy._engine._typing.__file__).read_text(encoding="utf-8")
    classes = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
            classes[node.name] = (methods, [name for base in node.bases if (name := _base_name(base))])
    return classes


_PROTOCOLS = _protocol_classes()


# Union spellings this file refuses to read: a name cannot be followed from the syntax alone, and
# the typed surface writes every union with `|`, so the cheap rule is to require it.
_LEGACY_UNIONS: tuple[str, str] = ("Optional", "Union")


def _visible(protocol: str) -> set[str]:
    """Everything ``protocol`` offers, its bases included.

    Resolving inheritance is what keeps the reverse check honest: ``is_in`` is declared once on
    ``_CoreAssertion`` and inherited by the rest, so comparing against one class in isolation would
    report methods as missing that every caller can already reach.
    """
    methods, parents = _PROTOCOLS[protocol]
    return set(methods).union(*(_visible(parent) for parent in parents)) if parents else set(methods)


def _public_methods(mixin: type) -> set[str]:
    return {
        name
        for name, value in vars(mixin).items()
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }


def _protocol_method_cases():
    """Yield ``(protocol_name, method_def)`` for every method declared in a Protocol class."""
    source = Path(assertpy._engine._typing.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Assertion"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node.name, item


_CASES = sorted(_protocol_method_cases(), key=lambda case: (case[0], case[1].name))


def _inherits(child: str, parent: str) -> bool:
    """Whether `child` reaches `parent` through protocol bases, which makes a repeat inheritance."""
    if child == parent:
        return False
    _methods, parents = _PROTOCOLS[child]
    return parent in parents or any(_inherits(grandparent, parent) for grandparent in parents)


def _declarations_of(protocol: str) -> dict[str, list]:
    """Every method a protocol offers, by name, with *all* declarations of it.

    A list rather than one node, because a name can be an overload group: keeping only the last one made
    every branch but the final invisible to the gates, and a narrowing pair is exactly where a conflict
    would hide.
    """
    declared: dict[str, list] = {}
    for name, method_def in _CASES:
        if name == protocol:
            declared.setdefault(method_def.name, []).append(method_def)
    for parent in _PROTOCOLS[protocol][1]:
        for name, method_defs in _declarations_of(parent).items():
            declared.setdefault(name, method_defs)
    return declared


_CASE_IDS = [f"{protocol}.{method.name}" for protocol, method in _CASES]


def _canonical(annotation) -> str:
    """An annotation as text, with a union folded into one form.

    `A | B` and `B | A` are one promise written two ways, nesting makes no difference, and a member
    repeated is still that member.  Without folding them, moving a copy between protocols and reordering
    its union would slip past the duplication gate while promising exactly the same thing.

    Only the `|` spelling is folded, and that is not an approximation: a separate check refuses
    `Optional` and `Union` in this file outright, so there is no second spelling to miss.  Everything
    outside a union is compared as written, which is the honest limit: an alias and the type it names
    read as different here, and so do `int` and a `TypeVar` bound to it.
    """
    if annotation is None:
        return "?"
    members = _union_members(annotation)
    if members is None:
        return ast.unparse(annotation)
    return " | ".join(sorted(set(members)))


def _members_of(annotation) -> list[str]:
    """One side of a union, itself flattened when it is a union again."""
    nested = _union_members(annotation)
    return nested if nested is not None else [ast.unparse(annotation)]


def _union_members(annotation) -> list[str] | None:
    """The members of a `|` union, flattened, or ``None`` when the annotation is not one."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _members_of(annotation.left) + _members_of(annotation.right)
    return None


def _is_overload_declaration(method_def) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == "overload" for decorator in method_def.decorator_list
    )


def _is_property(method_def):
    return any(isinstance(dec, ast.Name) and dec.id == "property" for dec in method_def.decorator_list)


def _required_arguments(method_def):
    """Return ``(positional_count, keyword_only_names)`` for the arguments a caller must supply."""
    arguments = method_def.args
    positional = arguments.posonlyargs + arguments.args
    required_positional = len(positional) - len(arguments.defaults) - 1
    required_keyword = [
        arg.arg for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True) if default is None
    ]
    return required_positional, required_keyword


class TestProtocolParity:
    def test_collected_a_meaningful_surface(self):
        # guards the collector itself: an ast/refactor slip yielding nothing would pass vacuously
        assert_that(len(_CASES)).is_greater_than(100)
        assert_that({protocol for protocol, _ in _CASES}).contains("_CoreAssertion", "_TextAssertion")

    @pytest.mark.parametrize(("protocol", "method_def"), _CASES, ids=_CASE_IDS)
    def test_declared_method_exists_on_concrete_builder(self, protocol, method_def):
        attribute = inspect.getattr_static(AssertionBuilder, method_def.name, _SENTINEL)
        assert_that(attribute).described_as(
            f"{protocol}.{method_def.name} is advertised to type checkers but missing on AssertionBuilder"
        ).is_not_same_as(_SENTINEL)
        if _is_property(method_def):
            assert_that(isinstance(attribute, property)).is_true()
        else:
            assert_that(callable(attribute)).is_true()

    @pytest.mark.parametrize(
        ("protocol", "method_def"),
        [case for case in _CASES if not _is_property(case[1])],
        ids=[case_id for case_id, case in zip(_CASE_IDS, _CASES, strict=True) if not _is_property(case[1])],
    )
    def test_concrete_signature_accepts_declared_required_arguments(self, protocol, method_def):
        concrete = inspect.getattr_static(AssertionBuilder, method_def.name)
        signature = inspect.signature(concrete)
        positional_count, keyword_names = _required_arguments(method_def)
        positional = [_SENTINEL] * (positional_count + 1)
        keyword = dict.fromkeys(keyword_names, _SENTINEL)
        try:
            signature.bind(*positional, **keyword)
        except TypeError as error:
            pytest.fail(f"{protocol}.{method_def.name} declares arguments the concrete method does not accept: {error}")


class TestReverseParity:
    """Every runtime assertion reaches the callers whose type it applies to."""

    def test_every_composed_mixin_is_mapped(self):
        # a new mixin added to the builder and not to the map would otherwise be checked by nothing
        composed = {cls for cls in AssertionBuilder.__mro__ if cls.__name__.endswith("Mixin")}
        assert_that(composed).is_not_empty()
        assert_that({cls.__name__ for cls in composed - set(_COVERAGE)}).described_as(
            "mixins composed into AssertionBuilder but absent from _COVERAGE"
        ).is_empty()
        assert_that({cls.__name__ for cls in set(_COVERAGE) - composed}).described_as(
            "mapped classes no longer composed into AssertionBuilder"
        ).is_empty()

    @pytest.mark.parametrize(
        ("mixin", "protocols"),
        sorted(_COVERAGE.items(), key=lambda item: item[0].__name__),
        ids=sorted(cls.__name__ for cls in _COVERAGE),
    )
    def test_mixin_methods_are_declared_on_its_protocols(self, mixin, protocols):
        covered = set().union(*(_visible(name) for name in protocols)) if protocols else set()
        uncovered = _public_methods(mixin) - covered - _UNTYPED
        assert_that(uncovered).described_as(
            f"{mixin.__name__} methods that work at runtime but no Protocol declares,"
            f" so a caller holding one of these types fails the type check: {sorted(uncovered)}"
        ).is_empty()

    def test_the_untyped_table_holds_only_what_is_still_untyped(self):
        # a stale exemption is the failure mode this whole file exists to prevent, one level up
        declared_anywhere = set().union(*(methods for methods, _ in _PROTOCOLS.values()))
        assert_that(_UNTYPED & declared_anywhere).described_as(
            "exempted from the reverse check but now declared on a Protocol; drop them from _UNTYPED"
        ).is_empty()
        runtime = set().union(*(_public_methods(cls) for cls in _COVERAGE))
        assert_that(_UNTYPED - runtime).described_as("exempted names that no longer exist at runtime").is_empty()

    def test_the_fallback_really_carries_the_untyped_methods(self):
        # the premise: no overload matches these types, and `tests/test_typing.py` pins that at the type level
        for name in _UNTYPED:
            assert_that(inspect.getattr_static(AssertionBuilder, name, _SENTINEL)).described_as(name).is_not_same_as(
                _SENTINEL
            )


class TestTheProtocolsStayComposed:
    """The capability protocols are only worth having if the duplication cannot quietly come back.

    Six of them exist because fifty-one declarations were copies of each other, and the cheapest way to
    undo that work is to paste a method into two protocols again rather than to give it a home.
    """

    @staticmethod
    def _shape(method_def) -> str:
        """A declaration reduced to what it promises, so formatting and comments do not matter.

        Each parameter carries its kind, because `f(x, /)`, `f(x)` and `f(*, x)` are three different
        promises to a caller, and its default, because a required parameter and one with a default are
        two more.  Flattening those into a list of names would let disagreeing bases pass as identical.

        The normalisation is syntactic, with one exception where syntax alone would let a copy through:
        every spelling of a union is folded to one form, nested ones included, and so are member order
        and repeats.  Everything else is compared as written, which is the honest limit: an alias and the
        type it aliases read as different here, and so do `int` and a `TypeVar` bound to it.
        """
        arguments = method_def.args
        positional = arguments.posonlyargs + arguments.args
        padding = [None] * (len(positional) - len(arguments.defaults))
        defaults = dict(zip(positional, padding + list(arguments.defaults), strict=True))
        defaults.update(dict(zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)))

        def one(argument, kind: str) -> str:
            annotation = _canonical(argument.annotation)
            default = defaults.get(argument)
            return f"{kind}:{argument.arg}:{annotation}" + (f"={ast.unparse(default)}" if default is not None else "")

        parts = [one(argument, "pos-only") for argument in arguments.posonlyargs]
        parts += [one(argument, "pos") for argument in arguments.args]
        if arguments.vararg is not None:
            parts.append(one(arguments.vararg, "var-pos"))
        parts += [one(argument, "kw-only") for argument in arguments.kwonlyargs]
        if arguments.kwarg is not None:
            parts.append(one(arguments.kwarg, "var-kw"))
        return f"({','.join(parts)})->{_canonical(method_def.returns)}"

    def test_no_declaration_is_repeated_across_sibling_protocols(self):
        """Every unrelated pair carrying the same signature, not "the group contains one related pair".

        Checking the group as a whole let a repeat between A and B pass whenever some C in the same
        group happened to inherit from A.
        """
        by_shape: dict[tuple[str, str], list[str]] = {}
        for protocol, method_def in _CASES:
            by_shape.setdefault((method_def.name, self._shape(method_def)), []).append(protocol)
        repeated = {
            f"{name} in {left} and {right}": shape
            for (name, shape), protocols in by_shape.items()
            for left, right in itertools.combinations(sorted(protocols), 2)
            if not _inherits(left, right)
            and not _inherits(right, left)
            and (name, left, right) not in _SHARED_ON_PURPOSE
        }
        assert_that(repeated).described_as(
            "identical declarations in protocols that do not inherit from each other: give them a"
            " capability protocol, or record the pair in _SHARED_ON_PURPOSE with the reason"
        ).is_empty()

    def test_a_child_does_not_redeclare_what_it_already_inherits(self):
        # the other way duplication returns: the test above ignores related pairs, leaving this route open
        redundant = {}
        for protocol, method_def in _CASES:
            for parent in _PROTOCOLS[protocol][1]:
                inherited = _declarations_of(parent).get(method_def.name) or []
                if (protocol, method_def.name) in _NARROWED_ON_PURPOSE:
                    continue
                if any(self._shape(one) == self._shape(method_def) for one in inherited):
                    redundant[f"{protocol}.{method_def.name}"] = f"already inherited from {parent}"
        assert_that(redundant).described_as("declarations a protocol repeats from its own base").is_empty()

    def test_a_name_carried_by_two_bases_means_the_same_thing_in_both(self):
        """Multiple inheritance is safe only while the bases agree about a shared name.

        Several protocols now have more than one base.  Two of them declaring the same method
        differently would leave which one wins to the resolution order, which is not something a reader
        should have to work out from the class line.
        """
        conflicts = {}
        for protocol, (_methods, parents) in _PROTOCOLS.items():
            shapes: dict[str, set[str]] = {}
            for parent in parents:
                for name, method_defs in _declarations_of(parent).items():
                    shapes.setdefault(name, set()).add(tuple(self._shape(one) for one in method_defs))
            disagreeing = {name: sorted(forms) for name, forms in shapes.items() if len(forms) > 1}
            if disagreeing:
                conflicts[protocol] = disagreeing
        assert_that(conflicts).described_as("bases of one protocol declaring one name in two shapes").is_empty()

    def test_a_protocol_declares_each_name_once_unless_it_is_an_overload(self):
        """Two plain `def`s of one name in one class: the second silently wins.

        The other gates compare protocols against each other and against their bases, so this way back
        into duplication was open. An overload group is the one legitimate repeat, and it is recognised
        by the decorator rather than allowed by name.
        """
        shadowed = {}
        for protocol in _PROTOCOLS:
            seen: dict[str, list] = {}
            for name, method_def in _CASES:
                if name == protocol:
                    seen.setdefault(method_def.name, []).append(method_def)
            for name, declarations in seen.items():
                plain = [one for one in declarations if not _is_overload_declaration(one)]
                if len(plain) > 1 or (len(declarations) > 1 and plain):
                    shadowed[f"{protocol}.{name}"] = f"{len(declarations)} declarations, {len(plain)} without @overload"
        assert_that(shadowed).described_as("names declared more than once inside one protocol").is_empty()

    @pytest.mark.parametrize(
        ("capability", "carriers"), sorted(_CAPABILITY_CARRIERS.items()), ids=sorted(_CAPABILITY_CARRIERS)
    )
    def test_every_capability_reaches_exactly_the_types_the_register_lists(self, capability, carriers):
        """The register and the inheritance graph say the same thing, so neither drifts in silence.

        Both directions matter and only one is obvious.  Dropping a base is a one-word edit that removes
        assertions from a whole family of values while every other guard stays green.  Adding one is the
        same edit in reverse and offers a value something it cannot do.

        What this does *not* claim is that the register is right.  A capability wrongly given to a type,
        and written down here as well, stays green: the register is a structural gate over the topology,
        not a judgement about it.  `_FilesystemAssertion` on `_InvokedAssertion` is the live example, and
        the comment on the register says where that edge came from.
        """
        actual = {name for name in _PROTOCOLS if _inherits(name, capability)}
        assert_that(actual).described_as(f"the types that carry {capability}").is_equal_to(set(carriers))

    def test_the_two_registers_describe_the_same_set_of_protocols(self):
        """Every protocol is either a value's own view or a capability, and the registers say which.

        The first version of this guessed by "is anybody's base" and then subtracted two names by hand,
        which is the shape of a rule that will be wrong the next time someone adds a protocol.  Two
        hand-written registers, checked against the classes the file actually declares, say it outright.
        """
        assert_that(set(_VALUE_VIEWS) | set(_CAPABILITY_CARRIERS)).described_as(
            "every protocol has to be registered as a value view or as a capability"
        ).is_equal_to(set(_PROTOCOLS))
        assert_that(set(_VALUE_VIEWS) & set(_CAPABILITY_CARRIERS)).described_as(
            "a protocol cannot be both a value view and a capability"
        ).is_empty()

    @pytest.mark.parametrize(
        ("name", "left", "right"),
        sorted(_SHARED_ON_PURPOSE),
        ids=[f"{name}:{left}:{right}" for name, left, right in sorted(_SHARED_ON_PURPOSE)],
    )
    def test_every_pair_excused_from_sharing_has_something_to_excuse(self, name, left, right):
        """An entry naming a declaration that does not exist excuses nothing and says so to nobody.

        Three entries here named `_ObjectAssertion.satisfies`, which that view has never declared: they
        were written from a description of the design rather than from the file, and the comment above
        them described a redeclaration that was implemented as the refinement ladder instead.  Nothing
        noticed, because a register of exclusions is read only by the check it silences.
        """
        for protocol in (left, right):
            assert_that(_PROTOCOLS).described_as(f"{protocol} has to be a protocol of the typed surface").contains_key(
                protocol
            )
            assert_that(_PROTOCOLS[protocol][0]).described_as(
                f"{protocol} is excused from sharing {name} with a view that declares it"
            ).contains(name)

    @pytest.mark.parametrize(
        ("protocol", "method"),
        sorted(_NARROWED_ON_PURPOSE),
        ids=[f"{protocol}.{method}" for protocol, method in sorted(_NARROWED_ON_PURPOSE)],
    )
    def test_every_narrowing_excused_as_deliberate_is_a_narrowing(self, protocol, method):
        """Both halves of the claim, since either alone would pass on an entry that means nothing.

        The register says a protocol redeclares what it inherits, so the protocol has to declare the
        method *and* reach a base that declares it too.  An entry where only the second half holds is
        the dead one this gate was written for.
        """
        assert_that(_PROTOCOLS[protocol][0]).described_as(
            f"{protocol} is excused for redeclaring {method}, so it has to declare it"
        ).contains(method)
        inherited = [base for base in _PROTOCOLS[protocol][1] if method in _declarations_of(base)]
        assert_that(inherited).described_as(
            f"{protocol}.{method} is excused as a narrowing, so a base has to declare it as well"
        ).is_not_empty()

    def test_every_base_the_walk_recorded_is_a_protocol_of_this_file(self):
        """The inheritance graph has no dangling parent, so a missing edge cannot pass as an absent one.

        Everything else here reasons over `_PROTOCOLS`, and a name in it that no class defines would make
        `_visible` raise rather than answer.  Asserting it directly says which of the two went wrong.
        """
        parents = {parent for _methods, bases in _PROTOCOLS.values() for parent in bases}
        assert_that(parents).described_as("every base has to be a protocol declared here").is_subset_of(set(_PROTOCOLS))

    @pytest.mark.parametrize("base", ["other.SomeAssertion", "other.SomeAssertion[str]", "make_base()"])
    def test_a_base_this_walk_cannot_resolve_is_refused_rather_than_skipped(self, base):
        """An unresolvable base is an error, not a shrug.

        Returning ``None`` for it would drop an inheritance edge, and every check in this file would then
        agree about a graph that is missing a line.  That is the exact failure this file exists to catch,
        so the walk refuses instead.
        """
        assert_that(_base_name).raises(AssertionError).when_called_with(ast.parse(base, mode="eval").body).starts_with(
            "unrecognised base"
        )

    def test_the_typed_surface_writes_every_union_with_a_pipe(self):
        """`Optional` and `Union` are refused here, and the refusal is what makes the folding sound.

        Reading what a name means at a point in a module cannot be done from syntax alone.  An import can
        be renamed, shadowed by a `def`, replaced through `setattr` or `tp.__dict__`, or arrive from one
        branch of an `if` and not the other, and a gate that guesses wrong folds a stranger's `Optional`
        into typing's.  That is worse than a gap: annotations are compared for *equality* below, so a
        wrong fold reports two different signatures as duplicates of one another.

        Requiring `|` removes the question instead of answering it.  The file already writes every union
        that way, so the rule costs nothing today and keeps the one spelling that `_canonical` folds
        exactly.
        """
        source = Path(assertpy._engine._typing.__file__).read_text(encoding="utf-8")
        legacy = {
            f"line {node.lineno}: {ast.unparse(node)}"
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Subscript)
            for name in [node.value]
            if (isinstance(name, ast.Name) and name.id in _LEGACY_UNIONS)
            or (isinstance(name, ast.Attribute) and name.attr in _LEGACY_UNIONS)
        }
        assert_that(legacy).described_as(
            "the typed surface spells unions with `|`, so this gate folds one form and reads no imports"
        ).is_empty()
