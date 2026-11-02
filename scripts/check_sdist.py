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

    python scripts/check_sdist.py [--developer] [--export=OPTIONS] [--work=DIR] -- PYTEST_ARGUMENTS
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

_ROOT = pathlib.Path(__file__).resolve().parent.parent

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


class SdistCheck:
    """Build, unpack and install the sdist, run the suite from both trees, and say how the two runs differ."""

    def __init__(self, work: pathlib.Path, export: list[str], developer: bool, arguments: list[str]) -> None:
        uv = shutil.which("uv")
        if uv is None:
            raise SystemExit("check_sdist: uv is not on PATH")
        self._uv = uv
        self._work = work
        self._export = export
        self._developer = developer
        self._arguments = arguments
        self._python = work / "venv" / "bin" / "python"

    def run(self) -> int:
        sdist = self._build()
        tree = self._unpack(sdist)
        self._install(sdist)
        environment = self._environment()
        runs = [self._suite(name, path, environment) for name, path in (("sdist", tree), ("checkout", _ROOT))]
        return self._verdict(*runs)

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
        requirements = self._work / "requirements.txt"
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
            *self._export,
            cwd=_ROOT,
        )
        self._call(self._uv, "venv", "--python", sys.executable, str(self._python.parent.parent))
        self._call(self._uv, "pip", "install", "--python", str(self._python), "--requirement", str(requirements))
        if not self._developer:
            self._call(self._uv, "pip", "install", "--python", str(self._python), str(sdist))

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
        environment = {name: value for name, value in os.environ.items() if name != "VIRTUAL_ENV"}
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


def main() -> int:
    if os.name == "nt":
        raise SystemExit("check_sdist: the uv shim is a shell script, so run this on POSIX (WSL works)")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--developer", action="store_true", help="editable installs, environment and a uv shim on the path"
    )
    parser.add_argument("--export", default="", help="options for `uv export`, such as '--extra json'")
    parser.add_argument("--work", type=pathlib.Path, help="an empty directory outside the checkout, kept afterwards")
    parser.add_argument("pytest", nargs=argparse.REMAINDER, help="after `--`, the arguments of both pytest runs")
    options = parser.parse_args()
    arguments = options.pytest[1:] if options.pytest[:1] == ["--"] else options.pytest
    work = (options.work or pathlib.Path(tempfile.mkdtemp(prefix="check_sdist-"))).resolve()
    if work.is_relative_to(_ROOT):
        raise SystemExit(f"check_sdist: {work} is inside the checkout, where the sdist's tree could reach its files")
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit(f"check_sdist: {work} is not empty")
    status = SdistCheck(work, shlex.split(options.export), options.developer, arguments).run()
    if status == 0 and options.work is None:
        shutil.rmtree(work)
    return status


if __name__ == "__main__":
    sys.exit(main())
