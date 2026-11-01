"""The floors job has to cover every range the package publishes, cell by cell.

`pyproject.toml` states a lower bound for each optional dependency, and a bound nobody installs is a
promise nobody checks. Three of them were wrong when this was first measured: `asttokens>=2.0` cannot
mark the tokens of the file it rewrites, `behave>=1.2.6` has no `ParseMatcher.TYPE_REGISTRY` for our
parser to register with, and `starlette>=0.40` reaches a function deprecated in 3.14.

Static, and deliberately so: the job itself is the thing that installs and runs. What this file stops is
a dependency added later that quietly escapes it, in either of the two ways it can. An extra no cell
installs is a range nobody checks, and a library a cell installs without naming it in that cell's import
probe can install, fail to import there, and turn its own tests into skips while the cell stays green.

Per cell rather than over their union, because the cells differ on purpose and a library dropped from one
probe is still named by the others.
"""

from __future__ import annotations

import importlib.metadata
import pathlib
import re

from packaging.requirements import Requirement

from assertpy import assert_that

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_PYPROJECT = _ROOT / "pyproject.toml"

_CELL = re.compile(
    r'- python-version: "(?P<python>[^"]+)"\s*\n'
    r'\s*extras: "(?P<extras>[^"]+)"\s*\n'
    r'\s*groups: "(?P<groups>[^"]+)"\s*\n'
    r'\s*imports: "(?P<imports>[^"]+)"'
    r'(?:\s*\n\s*reduced: "(?P<reduced>[^"]*)")?'
)
_INTEGRATIONS = re.compile(r"^integrations = \[(.*?)^\]", re.MULTILINE | re.DOTALL)
_TEST_MATRIX = re.compile(r"^\s*python-version: \[(?P<versions>[^\]]+)\]", re.MULTILINE)
_REQUIREMENT = re.compile(r"""^\s*['\"]([A-Za-z0-9._-]+)""", re.MULTILINE)
_PER_EXTRA = re.compile(r"^\"?(?P<dist>[A-Za-z0-9._-]+).*extra == '(?P<extra>[^']+)'")

_IMPORTED_AS = {"allure-pytest": "allure_commons"}
"""The one distribution whose module is not its own name.  `attrs` and `jsonpath-ng` normalise to theirs."""


def _cells() -> list[re.Match[str]]:
    found = list(_CELL.finditer(_WORKFLOW.read_text(encoding="utf-8")))
    if not found:
        raise RuntimeError(f"no floor cell parsed out of {_WORKFLOW.name}, so this file proves nothing")
    return found


def _named(field: str) -> set[str]:
    return {name.strip() for name in field.split(",")}


def _published_extras() -> set[str]:
    """Read from the installed metadata rather than the file, which is what a user actually gets."""
    return set(importlib.metadata.metadata("assertpy").get_all("Provides-Extra") or ())


def _dists_by_extra() -> dict[str, set[str]]:
    """What each published extra pulls in, already flattened: `data` arrives as its three."""
    by_extra: dict[str, set[str]] = {}
    for line in importlib.metadata.requires("assertpy") or ():
        match = _PER_EXTRA.match(line)
        if match is not None:
            by_extra.setdefault(match["extra"], set()).add(match["dist"])
    return by_extra


def _core_dists(python_version: str) -> set[str]:
    """The mandatory dependencies that apply to *python_version*, markers evaluated rather than read.

    `typing-extensions` is the only one today and it applies below 3.11, but a second one added later has
    to be probed too, and by the cells it actually lands on.

    `packaging` is not declared anywhere here and does not need to be: pytest requires it, so it is
    present wherever this suite runs, and reading a marker by hand is the worse of the two.
    """
    declared = importlib.metadata.requires("assertpy") or ()
    requirements = (Requirement(line) for line in declared if "extra ==" not in line)
    return {
        requirement.name
        for requirement in requirements
        if requirement.marker is None or requirement.marker.evaluate({"python_version": python_version})
    }


def _integration_dists() -> set[str]:
    """Read line by line and refuse an unreadable one, rather than dropping it.

    TOML has more than one way to spell a string, and a requirement this cannot read would otherwise
    leave the group looking smaller than it is, which is the failure the file exists to prevent.
    """
    group = _INTEGRATIONS.search(_PYPROJECT.read_text(encoding="utf-8"))
    if group is None:
        raise RuntimeError("no integrations group in pyproject.toml, so this file proves nothing")
    names = set()
    for line in group.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        found = _REQUIREMENT.match(line)
        if found is None:
            raise RuntimeError(f"unreadable requirement in the integrations group, so it would go unprobed: {line!r}")
        names.add(found.group(1))
    return names


def test_every_published_extra_is_installed_at_its_floor() -> None:
    """The union is the right question here: one cell carries less than another on purpose."""
    installed = {name for cell in _cells() for name in _named(cell["extras"])}

    assert_that(installed).described_as(
        "extras the declared-floors cells install between them, which has to cover every published extra"
    ).contains(*_published_extras())


def test_every_cell_imports_everything_it_installs() -> None:
    """A library a cell installs without probing can fail to import there and only skip its own tests."""
    by_extra = _dists_by_extra()
    unprobed = {}
    for cell in _cells():
        installs = {dist for extra in _named(cell["extras"]) for dist in by_extra.get(extra, ())}
        installs |= _core_dists(cell["python"])
        if "--group integrations" in cell["groups"]:
            installs |= _integration_dists()
        probed = _named(cell["imports"])
        missing = sorted(name for name in installs if _IMPORTED_AS.get(name, name.replace("-", "_")) not in probed)
        if missing:
            unprobed[f"{cell['python']} {cell['groups']}"] = missing

    assert_that(unprobed).described_as(
        "installed by a floor cell and never imported by it, so a broken one skips instead of failing"
    ).is_empty()


def _supported_versions() -> set[str]:
    """The interpreters the ordinary test matrix runs, which is the list this job has to match."""
    found = _TEST_MATRIX.search(_WORKFLOW.read_text(encoding="utf-8"))
    if found is None:
        raise RuntimeError(f"no test matrix parsed out of {_WORKFLOW.name}, so this file proves nothing")
    return {version.strip().strip('"') for version in found["versions"].split(",")}


def test_a_cell_carrying_less_than_the_others_says_why() -> None:
    """Full unless declared otherwise, so a cell cannot quietly shrink.

    Both halves matter: a cell short of the full set without a reason is the silent reduction, and a
    reason on a cell that is already full is a note nobody will delete once it stops being true.
    """
    full_extras = _published_extras()
    unexplained, stale = [], []
    for cell in _cells():
        # covers rather than proper-subset: a cell missing one extra and carrying an unknown one is
        # incomparable with the full set, and `<` reads that as full
        missing_extras = not full_extras <= _named(cell["extras"])
        missing_group = any(group not in cell["groups"] for group in ("--group dev", "--group integrations"))
        reduced = missing_extras or missing_group
        stated = (cell["reduced"] or "").strip()
        if reduced and not stated:
            unexplained.append(f"{cell['python']} {cell['groups']}")
        if stated and not reduced:
            stale.append(f"{cell['python']} {cell['groups']}")

    assert_that(unexplained).described_as("floor cells carrying less than the rest without saying why").is_empty()
    assert_that(stale).described_as("floor cells explaining a reduction they no longer make").is_empty()


def test_every_supported_interpreter_has_a_floor_cell() -> None:
    """A version with no floor cell is a version where no bound is checked at its bottom.

    A cell may carry less than another, as 3.15 does while the data libraries publish no wheel for it.
    What it may not do is not exist.
    """
    covered = {cell["python"] for cell in _cells()}

    assert_that(covered).described_as(
        "interpreters with a floor cell, which has to be every one the test matrix runs"
    ).contains(*_supported_versions())


def test_the_declarations_are_not_empty() -> None:
    """Empty sets would make the two claims above vacuous rather than false."""
    assert_that(_published_extras()).is_not_empty()
    assert_that(_dists_by_extra()).is_not_empty()
    assert_that(_integration_dists()).is_not_empty()
    assert_that(_core_dists("3.10")).described_as("mandatory dependencies on the oldest supported").is_not_empty()
    assert_that(_supported_versions()).is_not_empty()
