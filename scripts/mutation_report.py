"""Summarize a mutmut run as markdown for the CI job summary.

Reads the per-module ``.meta`` files mutmut writes rather than scraping its progress line, which
carries carriage returns, emoji and ANSI and would break on a locale change.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

import tomllib

# mutmut's exit-code table, imported rather than copied: only two codes mean "killed", 5 and 33 mean
# nothing covered the mutant and 36 and 255 a timeout, so reading every non-zero code as a kill inflates
# the score. The import loads mutmut's config, so this runs from the root where `[tool.mutmut]` lives
from mutmut.__main__ import status_by_exit_code

_RESULTS = pathlib.Path("mutants/assertpy")


def _excluded_tests() -> tuple[list[str], int]:
    """The test files and named tests the mutation run leaves out, from `[tool.mutmut]`.

    They are excluded because mutmut's trampoline breaks them, not because they are weak: whatever
    they would have killed still counts as a survivor here.
    """
    config = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["mutmut"]
    args = config.get("pytest_add_cli_args", [])
    files = [arg.removeprefix("--ignore=") for arg in args if arg.startswith("--ignore=")]
    by_name = args[args.index("-k") + 1].count(" and not ") + 1 if "-k" in args else 0
    by_id = sum(1 for arg in args if arg.startswith("--deselect="))
    return files, by_name + by_id


class _Tally:
    """Mutant counts sliced the three ways the report needs them."""

    def __init__(self) -> None:
        self.by_status: collections.Counter[str] = collections.Counter()
        self.per_module: collections.Counter[str] = collections.Counter()
        self.survivors: collections.Counter[str] = collections.Counter()
        self.unchecked: collections.Counter[str] = collections.Counter()

    def read(self, results: pathlib.Path) -> None:
        """Walk every ``.meta`` under ``results``, recursively so subpackages are included."""
        for meta in sorted(results.rglob("*.meta")):
            module = meta.relative_to(results).as_posix().removesuffix(".py.meta")
            codes = json.loads(meta.read_text(encoding="utf-8")).get("exit_code_by_key", {})
            for exit_code in codes.values():
                status = status_by_exit_code[exit_code]
                self.by_status[status] += 1
                self.per_module[module] += 1
                if status == "survived":
                    self.survivors[module] += 1
                elif status == "not checked":
                    self.unchecked[module] += 1

    @property
    def total(self) -> int:
        return sum(self.by_status.values())

    @property
    def judged(self) -> int:
        return self.total - self.by_status["not checked"]

    def wholly_unchecked_modules(self) -> list[str]:
        """Modules where not one mutant got a verdict.

        A red baseline looks exactly like this in the results.  mutmut runs the suite once against
        unmutated source to learn which tests cover which function, and a test that asserts on a line
        number, a traceback or a function name fails that run, because the trampoline renames every
        function and adds a stack frame.  mutmut then leaves the whole module unjudged, which a report
        that only prints a kill rate would show as a clean module.
        """
        return sorted(module for module, count in self.unchecked.items() if count == self.per_module[module])


def main() -> int:
    """Write the markdown summary to stdout.  Non-zero only when there is nothing to report."""
    if not _RESULTS.is_dir():
        print(f"no mutation results under {_RESULTS} - did `mutmut run` fail?", file=sys.stderr)
        return 1
    tally = _Tally()
    tally.read(_RESULTS)
    if tally.total == 0:
        print("no mutants were generated", file=sys.stderr)
        return 1

    if tally.judged == 0:
        # every mutant unjudged means the baseline never ran, which mutmut reports as "failed to collect stats"
        # and which reads downstream as a clean sweep.  It went unnoticed for two weeks
        print(f"none of the {tally.total} mutants got a verdict: the baseline did not run", file=sys.stderr)
        return 1

    killed, survived, unjudged = tally.by_status["killed"], tally.by_status["survived"], tally.by_status["not checked"]
    over = "judged mutants" if unjudged else "mutants"
    print("## Mutation testing\n")
    print(f"**{killed / max(tally.judged, 1):.1%}** of {over} killed, {killed} of {tally.judged}. {survived} survived.")
    if unjudged:
        print(f"\n{unjudged} of the {tally.total} generated mutants never got a verdict and are excluded above.")
    print("\nA survivor is a change to the source that no test noticed.  Most are equivalent mutants")
    print("(message text no test asserts on, formatting, `__repr__`), the rest are gaps worth a test.\n")

    excluded_files, deselected = _excluded_tests()
    if excluded_files or deselected:
        print("> **The survivor count is an over-estimate.**  This run leaves out")
        print(f"> {len(excluded_files)} test files and {deselected} named tests, because mutmut's trampoline")
        print("> renames functions and adds a stack frame, which breaks any test asserting on a line")
        print("> number, a traceback or a function name.  A mutant one of those would have killed is")
        print("> reported here as a survivor.")
        print(">")
        print("> The share that are false is large and moves with every test added, so no figure is")
        print("> quoted here: one nobody re-measures is worse than none.  Measure it when it matters,")
        print("> by re-running a suspect mutant against the unfiltered suite before calling it a gap.")
        print(">")
        print("".join(f"> - `{name}`\n" for name in excluded_files))

    blind = tally.wholly_unchecked_modules()
    if blind:
        print("> **Not one mutant of the modules below was judged.**  Either the run did not finish, or")
        print("> their baseline failed because a test asserts on a line number, a traceback or a function")
        print("> name, all of which the mutmut trampoline changes.  For the second case, add the test to")
        print("> `pytest_add_cli_args` in `pyproject.toml`.\n")
        print("".join(f"> - `{module}`\n" for module in blind))

    other = {name: count for name, count in tally.by_status.items() if name not in {"killed", "survived"}}
    if other:
        print("| status | mutants |")
        print("| --- | --- |")
        for name, count in sorted(other.items(), key=lambda item: -item[1]):
            print(f"| {name} | {count} |")
        print()

    print("| module | survivors | mutants |")
    print("| --- | --- | --- |")
    for module, count in tally.survivors.most_common():
        print(f"| `{module}` | {count} | {tally.per_module[module]} |")
    return 0


if __name__ == "__main__":  # pragma: no cover - a CI script, not library code
    raise SystemExit(main())
