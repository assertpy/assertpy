"""The suite's optional dependencies, read from `pyproject.toml`, and what taking one away takes with it.

The suite requires the `test` group and the package's own dependencies.  Everything else the suite's groups and
the package's extras name is optional: a distribution may package any subset of it, and the suite has to pass
on each.  CI runs it once without each optional distribution in turn (`scripts/check_sdist.py --without`).

Taking one away has to take what requires it as well, because no installer leaves pandas behind without numpy.
That is read from the metadata of an environment holding everything, with markers evaluated for that
interpreter.  A requirement behind an extra is not followed: `assertpy[json]` asks for jsonpath-ng, and
assertpy without it is exactly the case being run.

    python scripts/optional_dependencies.py optional [--python-version 3.14 --platform linux]
    python scripts/optional_dependencies.py closure DIST...
    python scripts/optional_dependencies.py never
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import pathlib
import sys
from typing import TYPE_CHECKING

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

try:
    import tomllib
except ModuleNotFoundError:  # below 3.11, where pytest brings the backport
    import tomli as tomllib

if TYPE_CHECKING:
    from collections.abc import Iterable
    from importlib.metadata import Distribution

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJECT = "assertpy"
REQUIRED_GROUP = "test"
SUITE_GROUPS = ("dev", "integrations", "oracle", "docs-examples")
"""What the suite reads.  `typecheck` is the lint job's, `docs`, `mutation` and `benchmark` drive tools of their own."""

_PLATFORMS = {
    "linux": ("linux", "Linux", "posix"),
    "darwin": ("darwin", "Darwin", "posix"),
    "win32": ("win32", "Windows", "nt"),
}


def environment(python_version: str | None = None, platform: str | None = None) -> dict[str, str]:
    """The marker environment of this interpreter, or of the one named, where a marker is read for another."""
    marked = dict(default_environment())
    if python_version is not None:
        marked["python_version"] = python_version
        marked["python_full_version"] = f"{python_version}.0"
    if platform is not None:
        marked["sys_platform"], marked["platform_system"], marked["os_name"] = _PLATFORMS[platform]
    return marked


def optional(marked: dict[str, str] | None = None) -> list[str]:
    """Every distribution the suite can run without, canonically named, for the marker environment given."""
    marked = marked or environment()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = project["dependency-groups"]
    extras = project["project"]["optional-dependencies"]
    named = [requirement for extra in extras for requirement in _extra(extras, extra, set())]
    named += [requirement for group in SUITE_GROUPS for requirement in _group(groups, group, set())]
    required = [Requirement(line) for line in project["project"]["dependencies"]]
    required += _group(groups, REQUIRED_GROUP, set())
    return sorted(_applying(named, marked) - _applying(required, marked))


def never_installed() -> list[str]:
    """The modules of the groups no run of the suite installs, by the import name their distributions are known by.

    Their tests skip as delegated to the job that installs them, so a run told what is absent is told these too.
    The name is the distribution's, read as a module: right for the checkers, the one kind such a test skips for.
    """
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = project["dependency-groups"]
    others = [group for group in groups if group not in (*SUITE_GROUPS, REQUIRED_GROUP)]
    named = {canonicalize_name(requirement.name) for group in others for requirement in _group(groups, group, set())}
    return sorted(name.replace("-", "_") for name in named - set(optional()))


def closure(targets: list[str], installed: dict[str, Distribution] | None = None) -> dict[str, list[str]]:
    """What leaves this environment with *targets*, and the modules that go with it.

    Every target has to be installed, or a cell meant to run without it would run without nothing.  A module
    a distribution that stays also provides is not listed, since it does not leave, though the part of a shared
    namespace that only leaving distributions provide is.  *installed* stands in for this environment's
    distributions, by canonical name.
    """
    installed = _installed() if installed is None else installed
    wanted = [canonicalize_name(target) for target in targets]
    absent = sorted(set(wanted) - set(installed))
    if absent:
        raise SystemExit(f"optional_dependencies: not installed here, so taking them away proves nothing: {absent}")
    dependents: dict[str, set[str]] = {}
    for owner in installed:
        for name in _required(installed, owner, frozenset(), set()):
            dependents.setdefault(name, set()).add(owner)
    leaving, waiting = set(), list(wanted)
    while waiting:
        name = waiting.pop()
        if name not in leaving:
            leaving.add(name)
            waiting.extend(dependents.get(name, ()))
    kept = _required_closure(installed)
    if leaving & kept:
        raise SystemExit(
            f"optional_dependencies: {targets} cannot be absent, the suite requires {sorted(leaving & kept)}"
        )
    return {"distributions": sorted(leaving), "modules": _leaving_modules(installed, leaving)}


def _installed() -> dict[str, Distribution]:
    return {canonicalize_name(dist.metadata["Name"]): dist for dist in importlib.metadata.distributions()}


def _required(installed: dict[str, Distribution], name: str, extras: frozenset[str], seen: set) -> set[str]:
    """What *name* asked for with *extras* requires here, an extra it asks of another distribution included.

    `a` requiring `b[feature]` requires what `b` lists under `feature`, which `b` alone does not.
    """
    dist = installed.get(name)
    if dist is None or (name, extras) in seen:
        return set()
    seen.add((name, extras))
    found = set()
    for requirement in _holding(dist.requires or (), extras):
        target = canonicalize_name(requirement.name)
        found.add(target)
        if requirement.extras:
            found |= _required(installed, target, frozenset(requirement.extras), seen)
    return found


def _leaving_modules(installed: dict[str, Distribution], leaving: set[str]) -> list[str]:
    providers: dict[tuple[str, ...], set[str]] = {}
    for owner, dist in installed.items():
        for module in _top_level(dist):
            providers.setdefault((module,), set()).add(owner)
    return sorted(_leaving_below(installed, leaving, providers))


def _leaving_below(
    installed: dict[str, Distribution], leaving: set[str], providers: dict[tuple[str, ...], set[str]]
) -> set[str]:
    """The modules every provider of which leaves, a package shared with one that stays opened a level at a time."""
    found = set()
    for module, owners in providers.items():
        if owners <= leaving:
            found.add(".".join(module))
        elif owners & leaving:
            inner: dict[tuple[str, ...], set[str]] = {}
            for owner in owners:
                for part in _inside(installed[owner], module):
                    inner.setdefault((*module, part), set()).add(owner)
            found |= _leaving_below(installed, leaving, inner)
    return found


def _top_level(dist: Distribution) -> set[str]:
    """The importable names a distribution installs, declared or read off its files.

    Read here rather than through `packages_distributions()`, which below 3.11 knows only `top_level.txt`, and
    numpy 1.26 ships none.
    """
    declared = (dist.read_text("top_level.txt") or "").split()
    if declared:
        return set(declared)
    names = set()
    for file in dist.files or ():
        first = file.parts[0]
        if first in {"..", "__pycache__"} or first.endswith((".dist-info", ".data", ".egg-info")):
            continue
        name = first.partition(".")[0] if len(file.parts) == 1 else first
        if name.isidentifier():
            names.add(name)
    return names


def _inside(dist: Distribution, package: tuple[str, ...]) -> set[str]:
    """The names a distribution installs one level inside *package*."""
    names = set()
    depth = len(package)
    for file in dist.files or ():
        if len(file.parts) > depth and file.parts[:depth] == package:
            part = file.parts[depth] if len(file.parts) > depth + 1 else file.parts[depth].partition(".")[0]
            if part.isidentifier() and not part.startswith("__"):
                names.add(part)
    return names


def _extra(extras: dict[str, list[str]], extra: str, seen: set[str]) -> list[Requirement]:
    """An extra's requirements, with one that names the project's own extras opened up in place."""
    seen.add(extra)
    found = []
    for line in extras[extra]:
        requirement = Requirement(line)
        if canonicalize_name(requirement.name) == PROJECT:
            found += [item for inner in sorted(requirement.extras - seen) for item in _extra(extras, inner, seen)]
        else:
            found.append(requirement)
    return found


def _group(groups: dict[str, list[str | dict[str, str]]], group: str, seen: set[str]) -> list[Requirement]:
    """A group's requirements, with an `include-group` table opened up in place."""
    seen.add(group)
    found = []
    for entry in groups[group]:
        if isinstance(entry, dict):
            if entry["include-group"] not in seen:
                found += _group(groups, entry["include-group"], seen)
        else:
            found.append(Requirement(entry))
    return found


def _applying(requirements: list[Requirement], marked: dict[str, str]) -> set[str]:
    return {
        canonicalize_name(requirement.name)
        for requirement in requirements
        if requirement.marker is None or requirement.marker.evaluate({**marked, "extra": ""})
    }


def _holding(lines: Iterable[str], extras: frozenset[str]) -> list[Requirement]:
    """The requirements of an installed distribution that hold here, for the *extras* asked of it and no other."""
    requirements = [Requirement(line) for line in lines]
    return [
        item
        for item in requirements
        if item.marker is None or any(item.marker.evaluate({"extra": extra}) for extra in ("", *extras))
    ]


def _required_closure(installed: dict[str, Distribution]) -> set[str]:
    """The project, the `test` group and everything they require here, which no cell may take away."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    roots = {PROJECT} | _applying(_group(project["dependency-groups"], REQUIRED_GROUP, set()), environment())
    kept, waiting = set(), list(roots)
    while waiting:
        name = waiting.pop()
        if name in kept or name not in installed:
            continue
        kept.add(name)
        waiting.extend(_required(installed, name, frozenset(), set()))
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("optional", help="every distribution the suite can run without, one per line")
    listing.add_argument("--python-version", help="read the markers for this Python rather than the running one")
    listing.add_argument("--platform", choices=sorted(_PLATFORMS), help="and for this platform")
    taking = commands.add_parser("closure", help="what leaves with the distributions named, as JSON")
    taking.add_argument("distributions", nargs="+")
    commands.add_parser("never", help="the modules of the groups no run of the suite installs, one per line")
    options = parser.parse_args()
    if options.command == "optional":
        print("\n".join(optional(environment(options.python_version, options.platform))))
    elif options.command == "never":
        print("\n".join(never_installed()))
    else:
        print(json.dumps(closure(options.distributions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
