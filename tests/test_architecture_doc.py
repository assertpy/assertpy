"""Hold `ARCHITECTURE.md` to the tree it describes.

The document exists because the model of the typed layer is not discoverable from the files, and a
document that stops being true is worse than none: it is read and believed. Two claims are cheap to keep
honest, and both are ways it rots in practice.

A path it names has to exist, which is what a rename breaks. A typing gate that exists has to be named,
which is what adding one and forgetting the table breaks. And the table of sizes is recomputed rather
than trusted, which is what any edit to the typed surface breaks.
"""

from __future__ import annotations

import ast
import os
import pathlib
import re

from assertpy import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DOCUMENT = _ROOT / "ARCHITECTURE.md"
_PATH = re.compile(r"`([A-Za-z0-9_./]+\.(?:py|json))`")
_A_TYPING_GATE = re.compile(r"^test_.*(typing|protocol).*\.py$")
_SIZE_ROW = re.compile(
    r"^\| `(?P<file>_engine/[a-z_]+\.py)` \| (?P<protocols>\d+) \| (?P<declarations>\d+) \|", re.MULTILINE
)
_TYPED_MODULES = sorted(f"_engine/{path.name}" for path in (_ROOT / "assertpy" / "_engine").glob("*_typing.py"))
"""Read off the tree rather than listed here, which let the negation twins go unrecorded."""


def _named_paths() -> set[str]:
    found = _PATH.findall(_DOCUMENT.read_text(encoding="utf-8"))
    if not found:
        raise RuntimeError(f"no path named in {_DOCUMENT.name}, so this file proves nothing")
    return set(found)


def _typing_gates() -> set[str]:
    return {path.name for path in (_ROOT / "tests").glob("test_*.py") if _A_TYPING_GATE.match(path.name)}


def _measured(module: str) -> tuple[int, int]:
    """Protocols and declarations, counted the way the table claims them."""
    tree = ast.parse((_ROOT / "assertpy" / module).read_text(encoding="utf-8"))
    protocols = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    declarations = sum(len([body for body in node.body if isinstance(body, ast.FunctionDef)]) for node in protocols)
    return len(protocols), declarations


def _rewritten(rows: list[tuple[str, str, str]]) -> None:
    """Put the measured counts back into the table, so the numbers are recorded and not typed."""
    text = _DOCUMENT.read_text(encoding="utf-8")
    for module, _, _ in rows:
        protocols, declarations = _measured(module)
        text = re.sub(
            rf"^\| `{re.escape(module)}` \| \d+ \| \d+ \|",
            f"| `{module}` | {protocols} | {declarations} |",
            text,
            flags=re.MULTILINE,
        )
    _DOCUMENT.write_text(text, encoding="utf-8", newline="")


def test_the_table_of_sizes_is_what_the_files_hold() -> None:
    """Recomputed rather than trusted: a number in prose is the first thing to stop being true.

    Row for row and file for file, since a deleted row and a duplicated one both leave a table that
    agrees with itself.

    Re-record with `ASSERTPY_UPDATE_ARCHITECTURE=1`, the way the API snapshot is re-recorded, so the
    counting rule has one implementation and the numbers are never typed by hand.
    """
    if os.environ.get("ASSERTPY_UPDATE_ARCHITECTURE"):
        _rewritten(_SIZE_ROW.findall(_DOCUMENT.read_text(encoding="utf-8")))
    rows = _SIZE_ROW.findall(_DOCUMENT.read_text(encoding="utf-8"))
    listed = [module for module, _, _ in rows]

    assert_that(sorted(listed)).described_as("modules the table has a row for").is_equal_to(_TYPED_MODULES)
    assert_that(listed).described_as("rows per module").does_not_contain_duplicates()
    assert_that({module: (int(protocols), int(declarations)) for module, protocols, declarations in rows}).described_as(
        "protocols and declarations per module, which ARCHITECTURE.md states outright"
    ).is_equal_to({module: _measured(module) for module in listed})


def test_every_path_the_document_names_exists() -> None:
    """Named as a bare file name or as a path from the root, and both spellings are used in it."""
    missing = sorted(
        named
        for named in _named_paths()
        if not (_ROOT / named).exists() and not (_ROOT / "tests" / named).exists() and not list(_ROOT.rglob(named))
    )

    assert_that(missing).described_as("paths ARCHITECTURE.md names that are not in the tree").is_empty()


def test_every_typing_gate_is_named_by_the_document() -> None:
    """A gate the table omits is a gate the next contributor does not know exists."""
    text = _DOCUMENT.read_text(encoding="utf-8")
    unlisted = sorted(gate for gate in _typing_gates() if gate not in text)

    assert_that(unlisted).described_as("typing gates missing from the table in ARCHITECTURE.md").is_empty()


def test_there_are_gates_to_find() -> None:
    """An empty set would make the claim above vacuous rather than false."""
    assert_that(_typing_gates()).is_not_empty()
