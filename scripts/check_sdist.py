"""Run the test suite from the sdist as a distribution packager does, and hold it to the checkout's run.

The sdist ships the suite so that a packager can run it.  Every other job runs from the checkout, where a file the
sdist leaves out, or a test that works only inside the repository's own environment, never shows.

The sdist is built, unpacked outside the checkout, and given an environment of its own made from the lockfile.  The
suite runs twice in that environment, from the unpacked sdist and then from the checkout.  Both runs must pass, and
both must collect and skip the same tests, by pytest node id: a file left out can turn a test into a skip or empty a
parametrisation as well as fail it, and a check that only asked for a passing run would miss those.  The sdist runs
first, so nothing the checkout's run leaves behind can stand in for what the sdist lacks.

By default the run is the packager's: the package is installed from the sdist, and neither the environment nor
`uv` is on the path, so a test that launches `uv` fails here as it fails for a packager without it.  `--developer`
is the run of the type-checker gates, which need what `uv sync` and `uv run` give a developer: each tree installed
in editable mode, since one gate asks that pyright reads the tree under test, and the environment on the path, where
pyright finds its interpreter.  There `uv` is a shim that passes `uv build` through and refuses everything else, so
`uv run` fails whatever the environment holds.  The shim is a shell script, which makes this POSIX only.

A packager installs a subset of the optional dependencies, so two runs take them away rather than add them, and
run from the sdist alone.  `--bare` is the environment with none: the package's own dependencies and the `test`
group, so no xdist workers either.  `--without=DIST` is the one with everything but DIST and what requires it.
Either way the modules that left are checked gone before the suite starts, and the suite is told which they
are (`ASSERTPY_SUITE_ABSENT`), with the modules of the groups no run here installs, so its guard fails a skip
for any other module: an environment that is not the one meant.  What leaves
is read by `scripts/optional_dependencies.py` from a second environment holding everything.

    python scripts/check_sdist.py [--developer] [--export=OPTIONS] [--work=DIR] -- PYTEST_ARGUMENTS
    python scripts/check_sdist.py --bare [--work=DIR] -- PYTEST_ARGUMENTS
    python scripts/check_sdist.py --without=DIST[,DIST] [--work=DIR] -- PYTEST_ARGUMENTS
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DEPENDENCIES = _ROOT / "scripts" / "optional_dependencies.py"

_EVERYTHING = [
    "--all-extras",
    "--group",
    "dev",
    "--group",
    "integrations",
    "--group",
    "oracle",
    "--group",
    "docs-examples",
]
_BARE = ["--no-default-groups", "--group", "test"]
_ABSENT = "ASSERTPY_SUITE_ABSENT"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

_SHIM = """#!/bin/sh
if [ "$1" = build ]; then
    exec '{uv}' "$@"
fi
echo "check_sdist: the suite ran 'uv $*', which needs the repository's own environment: launch sys.executable" >&2
exit 97
"""

_RECORDER = """
import json
import sys

import pytest


class Recorder:
    def __init__(self):
        self.collected, self.skipped = set(), set()

    def pytest_runtest_logreport(self, report):
        self.collected.add(report.nodeid)
        if report.skipped:
            self.skipped.add(report.nodeid)

    def pytest_collectreport(self, report):
        if report.skipped:
            self.collected.add(report.nodeid)
            self.skipped.add(report.nodeid)


recorder = Recorder()
status = pytest.main(sys.argv[2:], plugins=[recorder])
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump({"collected": sorted(recorder.collected), "skipped": sorted(recorder.skipped)}, out)
sys.exit(status)
"""

_GONE = """
import importlib.util
import json
import sys

left = [module for module in json.loads(sys.argv[1]) if importlib.util.find_spec(module) is not None]
if left:
    raise SystemExit(f"check_sdist: still importable after they were taken away: {left}")
"""

_NAMES = """
import importlib.metadata
import re

names = {re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower() for dist in importlib.metadata.distributions()}
print("\\n".join(sorted(names)))
"""

_SHOWN = 40


@dataclasses.dataclass(frozen=True)
class Run:
    """One run of the suite from one tree: its exit status and the node ids it collected and skipped."""

    tree: str
    status: int
    collected: frozenset[str]
    skipped: frozenset[str]

    @classmethod
    def read(cls, tree: str, status: int, report: pathlib.Path) -> Run:
        recorded = json.loads(report.read_text(encoding="utf-8"))
        return cls(tree, status, frozenset(recorded["collected"]), frozenset(recorded["skipped"]))


@dataclasses.dataclass(frozen=True)
class Absence:
    """What an environment is run without: everything optional, or the distributions named and what needs them."""

    bare: bool
    without: tuple[str, ...]


class SdistCheck:
    """Build, unpack and install the sdist, run the suite from both trees, and say how the two runs differ."""

    def __init__(
        self, work: pathlib.Path, export: list[str], developer: bool, absence: Absence | None, arguments: list[str]
    ) -> None:
        uv = shutil.which("uv")
        if uv is None:
            raise SystemExit("check_sdist: uv is not on PATH")
        self._uv = uv
        self._work = work
        self._export = export
        self._developer = developer
        self._absence = absence
        self._arguments = arguments
        self._python = work / "venv" / "bin" / "python"

    def run(self) -> int:
        sdist = self._build()
        tree = self._unpack(sdist)
        if self._absence is None:
            self._install(sdist)
            environment = self._environment()
        else:
            environment = {**self._environment(), _ABSENT: ",".join(self._take_away(sdist, self._absence))}
        sdist_run = self._suite("sdist", tree, environment)
        if self._absence is not None:
            return self._alone(sdist_run)
        return self._verdict(sdist_run, self._suite("checkout", _ROOT, environment))

    def _build(self) -> pathlib.Path:
        out = self._work / "dist"
        self._call(self._uv, "build", "--sdist", "--out-dir", str(out), str(_ROOT))
        (sdist,) = out.glob("*.tar.gz")
        return sdist

    def _unpack(self, sdist: pathlib.Path) -> pathlib.Path:
        target = self._work / "unpacked"
        with tarfile.open(sdist) as archive:
            archive.extractall(target, filter="data")
        (tree,) = target.iterdir()
        return tree

    def _install(self, sdist: pathlib.Path) -> None:
        requirements = self._exported("requirements.txt", self._export)
        self._call(self._uv, "venv", "--python", sys.executable, str(self._python.parent.parent))
        self._call(self._uv, "pip", "install", "--python", str(self._python), "--requirement", str(requirements))
        if not self._developer:
            self._call(self._uv, "pip", "install", "--python", str(self._python), str(sdist))

    def _take_away(self, sdist: pathlib.Path, absence: Absence) -> list[str]:
        """Build the environment without what *absence* names, and return the modules that left with it.

        Read off an environment holding everything, which is then left alone: the run gets one of its own, made
        from pinned requirements with no resolution, so nothing a resolver would add back can arrive.
        """
        everything = self._exported("everything.txt", _EVERYTHING)
        probe = self._work / "probe" / "bin" / "python"
        self._populate(probe, everything, sdist)
        if absence.bare:
            self._populate(self._python, self._exported("requirements.txt", _BARE), sdist)
            # what the bare environment lacks is everything the probe holds beyond it, transitive ones included
            missing = sorted(set(self._names(probe)) - set(self._names(self._python)))
            leaving = json.loads(self._probe(probe, "closure", *missing))
        else:
            leaving = json.loads(self._probe(probe, "closure", *absence.without))
            requirements = self._work / "requirements.txt"
            requirements.write_text(
                _kept(everything.read_text(encoding="utf-8"), set(leaving["distributions"])), "utf-8"
            )
            self._populate(self._python, requirements, sdist)
        print(f"check_sdist: taken away {' '.join(leaving['distributions'])}", flush=True)
        subprocess.run([str(self._python), "-c", _GONE, json.dumps(leaving["modules"])], check=True)
        self._call(self._uv, "pip", "check", "--python", str(self._python))
        return [*leaving["modules"], *self._probe(probe, "never").split()]

    @staticmethod
    def _names(python: pathlib.Path) -> list[str]:
        return subprocess.run([str(python), "-c", _NAMES], stdout=subprocess.PIPE, text=True, check=True).stdout.split()

    def _populate(self, python: pathlib.Path, requirements: pathlib.Path, sdist: pathlib.Path) -> None:
        """A fresh environment with exactly the pinned *requirements* and the package, nothing resolved."""
        self._call(self._uv, "venv", "--python", sys.executable, str(python.parent.parent))
        for source in (("--requirement", str(requirements)), (str(sdist),)):
            self._call(self._uv, "pip", "install", "--no-deps", "--python", str(python), *source)

    def _probe(self, python: pathlib.Path, *arguments: str) -> str:
        return subprocess.run(
            [str(python), str(_DEPENDENCIES), *arguments], stdout=subprocess.PIPE, text=True, check=True
        ).stdout

    def _exported(self, name: str, options: list[str]) -> pathlib.Path:
        requirements = self._work / name
        self._call(
            self._uv,
            "export",
            "--quiet",
            "--locked",
            "--no-hashes",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--output-file",
            str(requirements),
            *options,
            cwd=_ROOT,
        )
        return requirements

    def _environment(self) -> dict[str, str]:
        inherited = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
        if self._developer:
            shims = self._work / "shim"
            shims.mkdir()
            shim = shims / "uv"
            shim.write_text(_SHIM.format(uv=self._uv), encoding="utf-8")
            shim.chmod(0o755)
            path = [str(shims), str(self._python.parent), *inherited]
            expected = str(shim)
        else:
            path = [
                entry for entry in inherited if not any((pathlib.Path(entry) / name).exists() for name in ("uv", "uvx"))
            ]
            expected = None
        joined = os.pathsep.join(path)
        if shutil.which("uv", path=joined) != expected:
            raise SystemExit(
                f"check_sdist: the runs would find uv at {shutil.which('uv', path=joined)}, not {expected}"
            )
        environment = {name: value for name, value in os.environ.items() if name not in {"VIRTUAL_ENV", _ABSENT}}
        environment["PATH"] = joined
        return environment

    def _suite(self, name: str, tree: pathlib.Path, environment: dict[str, str]) -> Run:
        if self._developer:
            self._call(self._uv, "pip", "install", "--python", str(self._python), "--no-deps", "--editable", str(tree))
        report = self._work / f"{name}.json"
        print(f"check_sdist: the suite from the {name}, {tree}", flush=True)
        finished = subprocess.run(
            [str(self._python), "-c", _RECORDER, str(report), *self._arguments, "-p", "no:cacheprovider"],
            cwd=tree,
            env=environment,
            check=False,
        )
        return Run.read(name, finished.returncode, report)

    @staticmethod
    def _alone(run: Run) -> int:
        problems = [f"the run from the {run.tree} exited {run.status}"] if run.status else []
        if not run.collected:
            problems.append(f"the run from the {run.tree} collected no test, so it proves nothing")
        print(f"check_sdist: {len(run.collected)} collected and {len(run.skipped)} skipped from the {run.tree}")
        for problem in problems:
            print(f"check_sdist: {problem}")
        return 1 if problems else 0

    @staticmethod
    def _verdict(sdist: Run, checkout: Run) -> int:
        problems = [f"the run from the {run.tree} exited {run.status}" for run in (sdist, checkout) if run.status]
        if not checkout.collected:
            problems.append("the checkout collected no test, so the comparison proves nothing")
        for kind in ("collected", "skipped"):
            ours, theirs = getattr(checkout, kind), getattr(sdist, kind)
            for side, nodes in (("only from the checkout", ours - theirs), ("only from the sdist", theirs - ours)):
                if nodes:
                    shown = "\n    ".join(sorted(nodes)[:_SHOWN])
                    more = f"\n    ... and {len(nodes) - _SHOWN} more" if len(nodes) > _SHOWN else ""
                    problems.append(f"{len(nodes)} {kind} {side}:\n    {shown}{more}")
        print(
            f"check_sdist: {len(sdist.collected)} collected and {len(sdist.skipped)} skipped from the sdist,"
            f" {len(checkout.collected)} and {len(checkout.skipped)} from the checkout"
        )
        for problem in problems:
            print(f"check_sdist: {problem}")
        return 1 if problems else 0

    @staticmethod
    def _call(*command: str, cwd: pathlib.Path | None = None) -> None:
        subprocess.run(command, cwd=cwd, check=True)


def _kept(requirements: str, leaving: set[str]) -> str:
    """The exported *requirements* without the lines that install what is *leaving*, its comments kept."""
    lines = []
    for line in requirements.splitlines():
        named = _NAME.match(line)
        if named is None or re.sub(r"[-_.]+", "-", named[0]).lower() not in leaving:
            lines.append(line)
    return "\n".join(lines) + "\n"


def main() -> int:
    if os.name == "nt":
        raise SystemExit("check_sdist: the uv shim is a shell script, so run this on POSIX (WSL works)")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--developer", action="store_true", help="editable installs, environment and a uv shim on the path"
    )
    parser.add_argument("--export", default="", help="options for `uv export`, such as '--extra json'")
    parser.add_argument("--bare", action="store_true", help="the package's own dependencies and the test group only")
    parser.add_argument("--without", default="", help="everything but these distributions and what requires them")
    parser.add_argument("--work", type=pathlib.Path, help="an empty directory outside the checkout, kept afterwards")
    parser.add_argument("pytest", nargs=argparse.REMAINDER, help="after `--`, the arguments of both pytest runs")
    options = parser.parse_args()
    without = tuple(name for name in options.without.split(",") if name)
    if (options.bare or without) and (options.developer or options.export):
        raise SystemExit(
            "check_sdist: --bare and --without build their own environment, without --developer or --export"
        )
    if options.bare and without:
        raise SystemExit("check_sdist: --bare already takes everything optional away")
    absence = Absence(options.bare, without) if options.bare or without else None
    arguments = options.pytest[1:] if options.pytest[:1] == ["--"] else options.pytest
    work = (options.work or pathlib.Path(tempfile.mkdtemp(prefix="check_sdist-"))).resolve()
    if work.is_relative_to(_ROOT):
        raise SystemExit(f"check_sdist: {work} is inside the checkout, where the sdist's tree could reach its files")
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit(f"check_sdist: {work} is not empty")
    status = SdistCheck(work, shlex.split(options.export), options.developer, absence, arguments).run()
    if status == 0 and options.work is None:
        shutil.rmtree(work)
    return status


if __name__ == "__main__":
    sys.exit(main())
