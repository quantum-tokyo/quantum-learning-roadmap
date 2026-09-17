#!/usr/bin/env python
"""Execute the Labs and report which ones break.

The site build (``scripts/build.sh``) renders the outputs stored in each
``.ipynb`` and never starts a kernel, so a notebook can be broken for months
without anything turning red. This script is the missing execution path: it
runs the notebooks listed in ``scripts/notebooks.txt`` and exits non-zero if
any of them raises.

Notebooks are executed with ``src/`` as the working directory, matching how
``jupyter lab`` is used, so ``from utils...`` imports and the relative paths
into ``resources/`` and ``data/`` resolve.

Nothing is written back to the ``.ipynb`` files unless ``--save-outputs`` is
given, which replaces each notebook's stored outputs with what this Qiskit
version actually produces. That matters because the site renders those stored
outputs: without it, the published pages keep showing results from whichever
version last ran.

Usage:
    uv run python scripts/run-notebooks.py                    # group "local"
    uv run python scripts/run-notebooks.py --group hardware
    uv run python scripts/run-notebooks.py --group local --warnings-as-errors
    uv run python scripts/run-notebooks.py --list
    uv run python scripts/run-notebooks.py src/2020-w1-a-adder-ja.ipynb
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import nbformat
import yaml
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
MANIFEST = REPO_ROOT / "scripts" / "notebooks.txt"
TOC = SRC / "myst.yml"
NONDET_LEDGER = REPO_ROOT / "scripts" / "known-nondeterministic.txt"

GROUPS = ("local", "hardware", "known-broken")

# ``!pip install`` / ``%pip install`` cells would mutate the uv-managed venv,
# so they are skipped rather than executed.
PIP_INSTALL = re.compile(r"^\s*[!%]\s*pip\s+install\b", re.MULTILINE)

# Some cells report the machine rather than Qiskit: what pip can see, whether a
# .env exists. Their output differs per checkout and would bake one person's
# paths and credentials state into the published page, so --save-outputs keeps
# whatever is committed. They still execute -- the hardware group needs the .env
# ones to.
ENVIRONMENT_CELL = re.compile(
    r"^\s*[!%]\s*(pip|conda)\b|^\s*%(load_ext\s+dotenv|dotenv)\b|load_dotenv|find_dotenv",
    re.MULTILINE,
)

# Turn Qiskit's own deprecation warnings into errors without tripping over
# unrelated ones from matplotlib, ipykernel, and friends.
WARNINGS_PREAMBLE = """\
import warnings
for _category in (DeprecationWarning, PendingDeprecationWarning):
    warnings.filterwarnings("error", message=r".*[Qq]iskit.*", category=_category)
del _category
"""

# For an inventory rather than a gate: show every warning, including the repeats
# Python would otherwise hide, so a count per Lab is possible.
WARNINGS_REPORT_PREAMBLE = """\
import warnings
warnings.simplefilter("always", DeprecationWarning)
warnings.simplefilter("always", PendingDeprecationWarning)
"""

WARNING_LINE = re.compile(r"\b(\w*(?:Deprecation)Warning): (.+)")

# A warning raised inside a cell is prefixed with the temp file ipykernel
# compiled that cell into, which carries the kernel's pid and the machine's temp
# directory: ".../T/ipykernel_96562/3663264877.py:19: DeprecationWarning: ...".
# The pid moves every run, so the output is never byte-identical, and the path is
# one more piece of this machine published to the site. Neither is content.
IPYKERNEL_PATH = re.compile(r"\S*ipykernel_\d+/\d+\.py")


@dataclass
class Entry:
    group: str
    path: Path
    note: str


@contextlib.contextmanager
def held_stderr():
    """Divert fd 2 -- the kernel's chatter -- into a file for the duration."""
    saved = os.dup(2)
    with tempfile.TemporaryFile(mode="w+") as sink:
        sys.stderr.flush()
        os.dup2(sink.fileno(), 2)
        try:
            yield sink
        finally:
            sys.stderr.flush()
            os.dup2(saved, 2)
            os.close(saved)


@dataclass
class Result:
    entry: Entry
    ok: bool
    seconds: float
    cell_index: int | None = None
    error: str = ""
    skipped_cells: int = 0
    kernel_stderr: str = ""
    warnings: list = field(default_factory=list)


def published_notebooks() -> list[str]:
    """The Labs src/myst.yml's toc publishes, which is what defines the scope."""
    toc = yaml.safe_load(TOC.read_text()).get("project", {}).get("toc", [])
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            target = node.get("file")
            if isinstance(target, str) and target.endswith(".ipynb"):
                found.append(target)
            walk(node.get("children"))
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(toc)
    return found


def check_against_toc(entries: list[Entry]) -> None:
    """Refuse to run if the manifest and the toc disagree.

    Adding a Lab to the toc publishes it; adding it here is what gets it run.
    Nothing links the two, so without this check a new Lab is published and
    never executed -- exactly the blind spot this script exists to close.
    """
    published = published_notebooks()
    listed = {entry.path.name for entry in entries}
    unlisted = [name for name in published if name not in listed]
    stale = sorted(listed - set(published))
    if not unlisted and not stale:
        return

    toc_name = TOC.relative_to(REPO_ROOT)
    problems = []
    if unlisted:
        problems.append(
            f"  published by {toc_name} but not listed here, so nothing runs them:\n"
            + "".join(f"      {name}\n" for name in unlisted)
            + "  Add each one with the group it belongs to -- local, hardware, or\n"
            "  known-broken. The header of the manifest says what they mean.\n"
        )
    if stale:
        problems.append(
            f"  listed here but no longer published by {toc_name}:\n"
            + "".join(f"      {name}\n" for name in stale)
            + "  Drop the line, or put the Lab back in the toc.\n"
        )
    sys.exit(
        f"{MANIFEST.relative_to(REPO_ROOT)} is out of step with the toc:\n"
        + "\n".join(problems)
    )


def read_manifest() -> list[Entry]:
    entries: list[Entry] = []
    for lineno, raw in enumerate(MANIFEST.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split(None, 1)
        if len(fields) != 2:
            sys.exit(f"{MANIFEST}:{lineno}: expected '<group> <notebook>', got {raw!r}")
        group, name = fields[0], fields[1].strip()
        if group not in GROUPS:
            sys.exit(f"{MANIFEST}:{lineno}: unknown group {group!r} (expected one of {', '.join(GROUPS)})")
        note = raw.split("#", 1)[1].strip() if "#" in raw else ""
        path = SRC / name
        if not path.exists():
            sys.exit(f"{MANIFEST}:{lineno}: no such notebook: {path}")
        entries.append(Entry(group, path, note))
    check_against_toc(entries)
    return entries


def collect_warnings(nb) -> list[tuple[str, str]]:
    """Deprecation warnings a run left in the notebook's stderr, as (category, text).

    Read from the outputs rather than from the kernel: Python writes warnings to
    stderr, which nbclient stores as stream outputs, so nothing has to be handed
    back across the wire.
    """
    found: list[tuple[str, str]] = []
    for cell in nb.cells:
        for output in cell.get("outputs", []):
            if output.get("output_type") != "stream" or output.get("name") != "stderr":
                continue
            text = output.get("text", "")
            text = "".join(text) if isinstance(text, list) else text
            for match in WARNING_LINE.finditer(text):
                found.append((match.group(1), match.group(2).strip()))
    return found


def run_notebook(
    entry: Entry,
    timeout: int,
    warnings_as_errors: bool,
    save_outputs: bool = False,
    collect_warnings_too: bool = False,
) -> Result:
    nb = nbformat.read(entry.path, as_version=4)
    client = NotebookClient(
        nb,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(SRC)}},
        # Timestamps in cell metadata would write the run date into every commit.
        record_timing=False,
    )
    # Snapshot what is committed, so --save-outputs can put back the outputs of
    # cells whose result depends on the machine rather than on Qiskit. The copy
    # matters: execution mutates the very list these outputs live in.
    preserved = {
        index: copy.deepcopy(cell.get("outputs"))
        for index, cell in enumerate(nb.cells)
        if cell.cell_type == "code" and ENVIRONMENT_CELL.search(cell.source)
    }

    started = time.monotonic()
    skipped = 0
    with held_stderr() as kernel_output, client.setup_kernel():
        preamble = (
            WARNINGS_PREAMBLE if warnings_as_errors
            else WARNINGS_REPORT_PREAMBLE if collect_warnings_too else None
        )
        if preamble:
            client.execute_cell(nbformat.v4.new_code_cell(preamble), cell_index=-1)
        for index, cell in enumerate(nb.cells):
            if cell.cell_type != "code" or not cell.source.strip():
                continue
            if PIP_INSTALL.search(cell.source):
                skipped += 1
                continue
            try:
                client.execute_cell(cell, index)
            except CellExecutionError as exc:
                kernel_output.seek(0)
                return Result(
                    entry,
                    ok=False,
                    seconds=time.monotonic() - started,
                    cell_index=index,
                    error=summarise(exc),
                    skipped_cells=skipped,
                    kernel_stderr=kernel_output.read(),
                )
    if save_outputs:
        for index, outputs in preserved.items():
            nb.cells[index].outputs = outputs
        for cell in nb.cells:
            # record_timing keeps nbclient from adding these, but a notebook
            # saved by an earlier run may still carry them, and a run date does
            # not belong in the committed file.
            cell.get("metadata", {}).pop("execution", None)
            if cell.get("outputs"):
                cell.outputs = coalesce_streams(cell.outputs)
                for output in cell.outputs:
                    text = output.get("text")
                    if isinstance(text, str):
                        output["text"] = IPYKERNEL_PATH.sub("<ipykernel>.py", text)
        # Only on success: a half-executed notebook is worse than a stale one.
        nbformat.write(nb, entry.path)
    return Result(
        entry,
        ok=True,
        seconds=time.monotonic() - started,
        skipped_cells=skipped,
        warnings=collect_warnings(nb) if collect_warnings_too else [],
    )


def coalesce_streams(outputs: list) -> list:
    """Merge adjacent stream outputs, the way Jupyter renders them anyway.

    The kernel splits a cell's stdout into stream messages at boundaries that
    move from run to run, so a cell that prints in a loop produces a different
    number of stream outputs each time even when the text is identical. Merging
    them gives one canonical form, which is what makes --save-outputs idempotent.
    """
    merged: list = []
    for output in outputs:
        text = output.get("text")
        if isinstance(text, list):
            text = "".join(text)
        previous = merged[-1] if merged else None
        if (
            output.get("output_type") == "stream"
            and previous is not None
            and previous.get("output_type") == "stream"
            and previous.get("name") == output.get("name")
        ):
            previous["text"] = previous["text"] + text
            continue
        if text is not None:
            # Assign into the node rather than building a plain dict from it:
            # nbformat.write reaches for output.output_type, which a dict does
            # not have, and the write fails.
            output["text"] = text
        merged.append(output)
    return merged


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def summarise(exc: CellExecutionError) -> str:
    """Reduce a traceback to the exception line, which is what identifies the break."""
    lines = [ANSI.sub("", line).strip() for line in str(exc).splitlines() if line.strip()]
    for line in reversed(lines):
        if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Warning|Interrupt)\b", line):
            return line
    return lines[-1] if lines else "unknown failure"


def report_warnings(results: list[Result]) -> None:
    """One line per distinct deprecation, with where it fires.

    --warnings-as-errors stops at the first one, which makes it a gate but
    useless for taking stock of what the next major release will remove.
    """
    tally: dict[tuple[str, str], list[str]] = {}
    for result in results:
        for category, message in result.warnings:
            tally.setdefault((category, message.split(". ")[0]), []).append(
                result.entry.path.name
            )
    print()
    if not tally:
        print("No deprecation warnings.")
        return
    print(f"## deprecation warnings ({len(tally)} distinct)")
    for (category, message), notebooks in sorted(tally.items(), key=lambda kv: -len(kv[1])):
        where = sorted(set(notebooks))
        print(f"  [{category}] {message[:150]}")
        print(f"      {len(notebooks)}x in {', '.join(n.replace('.ipynb', '') for n in where)}")


def read_nondeterministic() -> dict[str, str]:
    """Notebooks allowed to move, and why, from known-nondeterministic.txt."""
    known: dict[str, str] = {}
    if not NONDET_LEDGER.exists():
        return known
    for lineno, raw in enumerate(NONDET_LEDGER.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            sys.exit(
                f"{NONDET_LEDGER.name}:{lineno}: expected '<notebook> <reason>'. "
                "A reason is required -- what was ruled out, not that it moves."
            )
        known[parts[0]] = parts[1]
    return known


def check_idempotent(entries: list[Entry], timeout: int, rounds: int) -> int:
    """Regenerate twice per round and compare bytes; restore the files either way.

    More than one round because some non-determinism is intermittent: one Lab
    here moves in about half of runs, so a single pair of passes reports it as
    stable and the gate goes green on luck. That is the same shape of mistake as
    trusting "the numbers looked the same".
    """
    originals = {entry.path: entry.path.read_bytes() for entry in entries}
    known = read_nondeterministic()
    moved_in: dict[Path, int] = {path: 0 for path in originals}
    try:
        for round_no in range(1, rounds + 1):
            digests: list[dict[Path, str]] = []
            for attempt in (1, 2):
                print(f"  round {round_no}/{rounds}, pass {attempt}/2 ...", flush=True)
                for entry in entries:
                    result = run_notebook(entry, timeout, False, save_outputs=True)
                    if not result.ok:
                        print(
                            f"    {entry.path.name} failed at cell {result.cell_index}:"
                            f" {result.error}"
                        )
                        print("  cannot judge idempotence while a notebook is failing.")
                        return 1
                digests.append(
                    {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}
                )
            for path in originals:
                if digests[0][path] != digests[1][path]:
                    moved_in[path] += 1
    finally:
        for path, data in originals.items():
            path.write_bytes(data)

    unexpected = {p: n for p, n in moved_in.items() if n and p.name not in known}
    expected = {p: n for p, n in moved_in.items() if n and p.name in known}
    stale = [name for name in known if not any(p.name == name and n for p, n in moved_in.items())]

    print()
    for path in sorted(originals):
        count = moved_in[path]
        if not count:
            label = "same "
        elif path.name in known:
            label = "moved"
        else:
            label = "MOVED"
        suffix = f"  ({count}/{rounds} rounds)" if count else ""
        print(f"  {label} {path.name}{suffix}")

    if expected:
        print("\n## moved, and recorded as known")
        for path in sorted(expected):
            print(f"  {path.name}: {known[path.name][:120]}")

    if unexpected:
        print("\n## moved, not recorded")
        for path in sorted(unexpected):
            print(f"  {path.name}  ({moved_in[path]}/{rounds} rounds)")
        print(
            "\n  Find the cause and remove it. If you looked and could not, add a line to\n"
            f"  {NONDET_LEDGER.name} saying what you ruled out."
        )

    if stale:
        print("\n## recorded as non-deterministic but never moved here")
        for name in sorted(stale):
            print(f"  {name}")
        print("  Either the cause is gone and the line should go, or --rounds was too low.")

    steady = len(originals) - len(unexpected) - len(expected)
    print(f"\n{steady}/{len(originals)} byte-identical across every round")
    print("(the notebooks were restored; nothing was written)")
    return 1 if unexpected else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "notebooks",
        nargs="*",
        help="notebooks to run, bypassing the manifest (paths relative to the repo root)",
    )
    parser.add_argument(
        "--group",
        action="append",
        choices=[*GROUPS, "all"],
        help=f"manifest group to run (repeatable); default: local",
    )
    parser.add_argument("--timeout", type=int, default=600, help="per-cell timeout in seconds (default: 600)")
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="turn Qiskit deprecation warnings into errors, to surface what the next major release removes",
    )
    parser.add_argument(
        "--save-outputs",
        action="store_true",
        help="write the fresh outputs back into the .ipynb, so the built site shows what this Qiskit version produces",
    )
    parser.add_argument(
        "--warnings-report",
        action="store_true",
        help="inventory the deprecation warnings instead of failing on them",
    )
    parser.add_argument(
        "--check-idempotent",
        action="store_true",
        help="regenerate twice per round and report which notebooks are not byte-identical",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="rounds of two regenerations for --check-idempotent (default 2; one round "
        "cannot see intermittent non-determinism)",
    )
    parser.add_argument("--list", action="store_true", help="print the manifest and exit")
    args = parser.parse_args()

    if args.warnings_report and args.warnings_as_errors:
        sys.exit("--warnings-report and --warnings-as-errors ask for opposite things")
    if args.save_outputs and args.warnings_as_errors:
        sys.exit("--save-outputs and --warnings-as-errors do not mix: the preamble cell is not part of the notebook")

    if args.list:
        for entry in read_manifest():
            print(f"{entry.group:<13} {entry.path.name}" + (f"   # {entry.note}" if entry.note else ""))
        return 0

    if args.notebooks:
        entries = [Entry("ad-hoc", Path(name).resolve(), "") for name in args.notebooks]
        missing = [e.path for e in entries if not e.path.exists()]
        if missing:
            sys.exit("no such notebook: " + ", ".join(str(p) for p in missing))
    else:
        groups = set(args.group or ["local"])
        manifest = read_manifest()
        entries = manifest if "all" in groups else [e for e in manifest if e.group in groups]
        if not entries:
            sys.exit(f"no notebooks in group(s): {', '.join(sorted(groups))}")

    if args.check_idempotent:
        print(
            f"Regenerating {len(entries)} notebook(s) twice per round,"
            f" {args.rounds} round(s), to compare bytes\n"
        )
        return check_idempotent(entries, args.timeout, args.rounds)

    print(f"Running {len(entries)} notebook(s) from {SRC}", end="")
    if args.warnings_as_errors:
        print(" with Qiskit deprecation warnings as errors")
    elif args.save_outputs:
        print(", saving fresh outputs back into each file")
    else:
        print()
    print()

    results: list[Result] = []
    for entry in entries:
        result = run_notebook(
            entry,
            args.timeout,
            args.warnings_as_errors,
            args.save_outputs,
            collect_warnings_too=args.warnings_report,
        )
        results.append(result)
        status = "ok  " if result.ok else "FAIL"
        skipped = f", {result.skipped_cells} pip cell(s) skipped" if result.skipped_cells else ""
        print(f"  {status} {entry.path.name}  ({result.seconds:.0f}s{skipped})", flush=True)
        if not result.ok:
            print(f"         cell {result.cell_index}: {result.error}")

    if args.warnings_report:
        report_warnings(results)

    failed = [r for r in results if not r.ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print()
        print("Failures:")
        for result in failed:
            print(f"  {result.entry.path.name} (cell {result.cell_index}): {result.error}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
