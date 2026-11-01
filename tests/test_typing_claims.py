"""Guard the two claims the project makes about its own type checking.

The README badge and `docs/concepts/type-safety.md` promise that ty, mypy ``--strict``, Pyright and
Pyrefly all run against ``tests/test_typing.py`` **with zero suppressions**.  That is prose, and prose drifts: one
``# type: ignore`` added to silence an inconvenient checker would leave the badge saying something
untrue with nothing to notice.  The first test below turns the sentence into a gate.

The second is the project's own rule rather than a public claim: a suppression anywhere in the package
has to say why it is there, so the next reader can judge whether it still applies.  Both are cheap
checks over source text, which is exactly the shape of claim no other test can reach.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from assertpy import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# every form the four checkers honour, so silencing any one of them trips this
_SUPPRESSION = re.compile(r"#\s*(type:\s*ignore|ty:\s*ignore|pyright:\s*ignore|pyrefly:\s*ignore|mypy:)")

_PACKAGE_FILES = sorted((_ROOT / "assertpy").rglob("*.py"))


class TestThePinnedTypingSurfaceCarriesNoSuppressions:
    """`tests/test_typing.py` is the file the badge is about: an `assert_type` call pinning every
    public overload.  A suppression in it would hide the very regression it exists to catch."""

    _SURFACE = _ROOT / "tests" / "test_typing.py"

    def test_no_checker_is_silenced(self):
        offenders = [
            f"line {number}: {line.strip()}"
            for number, line in enumerate(self._SURFACE.read_text(encoding="utf-8").splitlines(), start=1)
            if _SUPPRESSION.search(line)
        ]
        assert_that(offenders).described_as("suppressions in the pinned typing surface").is_empty()

    def test_the_surface_is_not_empty(self):
        # a guard over an emptied file passes forever; this is what keeps the one above meaningful
        assert_that(self._SURFACE.read_text(encoding="utf-8")).contains("assert_type(")

    def test_the_claim_is_still_made(self):
        claim = (_ROOT / "docs" / "concepts" / "type-safety.md").read_text(encoding="utf-8")
        assert_that(claim).contains("zero suppressions").contains("tests/test_typing.py")


class TestEverySuppressionInThePackageSaysWhy:
    """A bare ``# ty: ignore[rule]`` is a decision with its reasoning thrown away.  Six months later
    nobody can tell whether the checker was wrong, the code was wrong, or the rule has since improved,
    so the suppression outlives whatever justified it."""

    @pytest.mark.parametrize("path", _PACKAGE_FILES, ids=lambda path: path.name)
    def test_the_rule_is_followed(self, path):
        unexplained = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _SUPPRESSION.search(line)
            if not match:
                continue
            trailing = line[match.end() :]
            # the rule name in brackets is part of the suppression, the reason is whatever follows the second `#`
            if "#" not in trailing.split("]", 1)[-1]:
                unexplained.append(f"{path.name} line {number}: {line.strip()}")
        assert_that(unexplained).described_as("suppressions with no stated reason").is_empty()

    def test_the_scan_actually_finds_suppressions(self):
        # the package does carry some; a scan that matched nothing would pass the check above vacuously
        found = sum(
            1
            for path in _PACKAGE_FILES
            for line in path.read_text(encoding="utf-8").splitlines()
            if _SUPPRESSION.search(line)
        )
        assert_that(found).is_greater_than(0)


_TYPE_TABLE = re.compile(r"^\| `?(?P<types>[^|]+?)`? \| (?P<gets>[^|]+?) \| (?P<examples>[^|]*?) \|$", re.MULTILINE)

_NAMED_IN_PROSE = {
    "a pandas or polars frame": "_FrameT_co",
    "a numpy array": "_ArrayT_co",
    "a numpy scalar": "_T",
    "any callable": "Callable",
    "a plain class": "_T",
}
"""Rows that name their subject in words, mapped to the head of the annotation the overload uses.

The head, because that is the key `_overloads()` files an annotation under: it is read down to the name
in front of its subscript, so `Callable[..., _P]` is stored as `Callable`.

Written out rather than parsed: a row saying "any callable" is prose, and guessing at it would make the
gate agree with whatever the page happened to say.
"""

_NOT_A_ROW = frozenset({"Value type", "---"})


def _overloads():
    """`{type name: the view assert_that returns for it}`, read from the entry module."""
    source = (_ROOT / "assertpy" / "assertpy.py").read_text(encoding="utf-8")
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or node.name != "assert_that":
            continue
        if not any(ast.unparse(one) == "overload" for one in node.decorator_list):
            continue
        annotation = ast.unparse(node.args.args[0].annotation)
        view = ast.unparse(node.returns).split("[")[0]
        for one in annotation.split("|"):
            found[one.strip().split("[")[0]] = view
    return found


def _offers(view):
    """Every method name a view offers, its protocol bases included."""
    source = (_ROOT / "assertpy" / "_engine" / "_typing.py").read_text(encoding="utf-8")
    declared = {node.name: node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ClassDef)}
    names, pending = set(), [view]
    while pending:
        node = declared.get(pending.pop())
        if node is None:
            continue
        names |= {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
        pending += [base.id for base in node.bases if isinstance(base, ast.Name)]
    return names


def _rows():
    """`(the row's subject, the annotation it names, the methods it names)` for every row of the table.

    The annotation an overload is written with, not the view a value of that type resolves to.  The two
    part where overload order decides: a callable HTTP response is claimed by the capability overload
    above the callable one, so it reaches `_CapableAssertion` and not `_CallableAssertion`.  Which view
    a value really lands on is held by `tests/test_overload_order.py` and by the `assert_type` cases,
    and this gate deliberately asks the cheaper question.
    """
    page = (_ROOT / "docs" / "concepts" / "type-safety.md").read_text(encoding="utf-8")
    found = []
    for match in _TYPE_TABLE.finditer(page):
        subject = match.group("types").strip()
        if subject in _NOT_A_ROW or subject.startswith("-"):
            continue
        examples = re.findall(r"`([a-z_][a-z_0-9]*)`", match.group("examples"))
        annotations = (
            [_NAMED_IN_PROSE[subject]]
            if subject in _NAMED_IN_PROSE
            else [one.strip().strip("`").split("[")[0] for one in subject.split(" / ")]
        )
        found.append((subject, annotations, examples))
    return found


class TestTheTypeTableNamesWhatTheSurfaceOffers:
    """The table on the type-safety page, held to the overloads it describes.

    It is authored, it moved in nearly half the commits that changed a public assertion's signature, and
    nothing held it.  It had already drifted when this was written: the `complex` row advertised
    `is_positive`, `is_between` and `is_close_to`, and `_ComplexAssertion` carries none of the three,
    because a complex number has neither an ordering nor a closeness.

    What this cannot check is the prose: a row saying "plus the same three" is a sentence, and a method
    the row should have named but did not is invisible to it.
    """

    def test_the_table_was_found_at_all(self):
        """Not load bearing while the rows below pass, and load bearing the day the table is reformatted."""
        assert_that(_rows()).described_as("rows of the type table").is_not_empty()

    def test_every_type_a_row_names_reaches_an_overload(self):
        overloads = _overloads()
        unclaimed = {
            subject: [one for one in claims if one not in overloads]
            for subject, claims, _ in _rows()
            if any(one not in overloads for one in claims)
        }
        assert_that(unclaimed).described_as("a row naming a type no overload claims").is_empty()

    def test_every_method_a_row_names_is_offered_by_the_view_it_reaches(self):
        overloads = _overloads()
        missing = {}
        for subject, claims, examples in _rows():
            for claimed in claims:
                view = overloads.get(claimed)
                if view is None:
                    continue
                absent = [one for one in examples if one not in _offers(view)]
                if absent:
                    missing[f"{subject} -> {view}"] = absent
        assert_that(missing).described_as("named in the table and not offered by the view").is_empty()
