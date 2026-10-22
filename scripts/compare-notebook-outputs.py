#!/usr/bin/env python
"""Compare the notebook outputs in the working tree against a committed baseline.

A library upgrade that leaves every notebook executing cleanly can still change
what readers see, because the site renders the outputs stored in each .ipynb.
"It runs" and "it still says the same thing" are different claims, and only the
second one matters for teaching material. This checks the second.

Changes are split three ways, because they need different responses:

* **numbers moved, structure identical** -- reported. Read the magnitudes.
* **structure changed** -- fails. A new warning block, a different plugin list, a
  disappeared table. Record it in scripts/accepted-output-changes.txt once you
  have read it and decided it is correct.
* **something from this machine leaked in** -- fails. Absolute paths, whether a
  .env exists, an interpreter's "not found" message, an object's address. These
  are published to the site, and none of them belong there.

Comparison is done on concatenated stream text and on a multiset of the non-text
outputs, so the run-to-run variation in how the kernel chunks stdout is not
mistaken for a structural change.

Usage:
    uv run python scripts/compare-notebook-outputs.py
    uv run python scripts/compare-notebook-outputs.py --base <ref>
    uv run python scripts/compare-notebook-outputs.py --group local
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import nbformat

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
LEDGER = REPO_ROOT / "scripts" / "accepted-output-changes.txt"

# Every one of these was actually committed to this repo at some point by
# regenerating outputs on someone's laptop.
LEAKS = [
    (re.compile(r"(?:/Users|/home)/[A-Za-z0-9._-]+/"), "an absolute path from someone's machine"),
    # The temp directory a kernel compiled a cell into; carries the pid too.
    (re.compile(r"/var/folders/\S+|ipykernel_\d+"), "the kernel's temp path"),
    (re.compile(r"cannot find \.env"), "whether a .env exists here"),
    (re.compile(r"Package\(s\) not found"), "what an interpreter that is not the kernel can see"),
    (re.compile(r"\bat 0x[0-9a-fA-F]{6,}"), "an object's memory address"),
    (re.compile(r"\.qiskit/qiskit-ibm\.json"), "a local credentials path"),
]

DIGITS = re.compile(r"\d+")


@dataclass
class Finding:
    notebook: str
    cell: int
    kind: str  # "numeric" | "structural" | "leak"
    detail: str = ""
    digest: str = ""
    accepted_reason: str = ""


@dataclass
class Ledger:
    entries: dict[tuple[str, int, str], str] = field(default_factory=dict)
    seen: set[tuple[str, int, str]] = field(default_factory=set)

    @classmethod
    def load(cls) -> "Ledger":
        ledger = cls()
        if not LEDGER.exists():
            return ledger
        for lineno, raw in enumerate(LEDGER.read_text().splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 3)
            if len(parts) < 4:
                sys.exit(
                    f"{LEDGER.name}:{lineno}: expected "
                    "'<notebook> <cell> <digest> <reason>'. A reason is required -- "
                    "an entry without one is a rubber stamp."
                )
            notebook, cell, digest, reason = parts
            ledger.entries[(notebook, int(cell), digest)] = reason
        return ledger

    def accepts(self, notebook: str, cell: int, digest: str) -> str | None:
        key = (notebook, cell, digest)
        reason = self.entries.get(key)
        if reason is not None:
            self.seen.add(key)
        return reason

    def stale(self) -> list[tuple[str, int, str]]:
        return sorted(set(self.entries) - self.seen)


def outputs_of(cell) -> tuple[str, list[str]]:
    """A cell's outputs as (all stream text, sorted digests of everything else).

    The stream text is concatenated because the kernel splits stdout into a
    different number of messages from run to run; the rest is a multiset because
    the order streams and display data arrive in also moves.
    """
    stream: list[str] = []
    other: list[str] = []
    for output in cell.get("outputs", []):
        kind = output.get("output_type")
        if kind == "stream":
            text = output.get("text", "")
            stream.append("".join(text) if isinstance(text, list) else text)
        elif kind in ("execute_result", "display_data"):
            for mime, payload in (output.get("data") or {}).items():
                if isinstance(payload, list):
                    payload = "".join(payload)
                if mime == "text/plain":
                    stream.append(str(payload))
                else:
                    digest = hashlib.sha256(str(payload).encode()).hexdigest()[:12]
                    other.append(f"{mime}:{digest}")
        elif kind == "error":
            stream.append(f"{output.get('ename')}: {output.get('evalue')}")
    return "".join(stream), sorted(other)


def baseline_notebook(ref: str, path: Path):
    relative = path.relative_to(REPO_ROOT)
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        return None
    return nbformat.reads(result.stdout, as_version=4)


def notebooks_for(group: str | None) -> list[Path]:
    manifest = REPO_ROOT / "scripts" / "notebooks.txt"
    chosen = []
    for raw in manifest.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        entry_group, name = line.split(None, 1)
        if group is None or entry_group == group:
            chosen.append(SRC / name.strip())
    return chosen


def compare(path: Path, ref: str, ledger: Ledger) -> list[Finding]:
    before = baseline_notebook(ref, path)
    if before is None:
        return [Finding(path.name, -1, "structural", f"not present in {ref}")]
    after = nbformat.read(path, as_version=4)
    findings: list[Finding] = []

    for index, (old, new) in enumerate(zip(before.cells, after.cells)):
        if new.cell_type != "code":
            continue
        new_stream, new_other = outputs_of(new)

        old_stream, old_other = outputs_of(old)

        for pattern, what in LEAKS:
            match = pattern.search(new_stream)
            if not match:
                continue
            # A leak already in the baseline is not something this change did.
            # Failing on it would make the check red from the first run, which is
            # how a gate becomes something people route around. Report it as debt
            # and fail only on what was just introduced.
            kind = "leak-existing" if pattern.search(old_stream) else "leak"
            findings.append(
                Finding(path.name, index, kind, f"{what}: {match.group(0)!r}")
            )
        if (old_stream, old_other) == (new_stream, new_other):
            continue

        digest = hashlib.sha256((new_stream + "".join(new_other)).encode()).hexdigest()[:12]
        structural = (
            DIGITS.sub("#", old_stream) != DIGITS.sub("#", new_stream)
            or old_other != new_other
        )
        if not structural:
            findings.append(Finding(path.name, index, "numeric", digest=digest))
            continue

        reason = ledger.accepts(path.name, index, digest)
        findings.append(
            Finding(path.name, index, "structural", digest=digest, accepted_reason=reason or "")
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="HEAD", help="git ref to compare against (default HEAD)")
    parser.add_argument("--group", help="only this manifest group, e.g. local")
    parser.add_argument("notebooks", nargs="*", help="notebooks to compare, bypassing the manifest")
    args = parser.parse_args()

    paths = [Path(n).resolve() for n in args.notebooks] or notebooks_for(args.group)
    ledger = Ledger.load()

    findings: list[Finding] = []
    for path in paths:
        findings.extend(compare(path, args.base, ledger))

    leaks = [f for f in findings if f.kind == "leak"]
    existing_leaks = [f for f in findings if f.kind == "leak-existing"]
    unaccepted = [f for f in findings if f.kind == "structural" and not f.accepted_reason]
    accepted = [f for f in findings if f.kind == "structural" and f.accepted_reason]
    numeric = [f for f in findings if f.kind == "numeric"]

    print(f"Comparing {len(paths)} notebook(s) against {args.base}\n")

    if leaks:
        print("## newly leaked from this machine -- these would be published")
        for f in leaks:
            print(f"  {f.notebook} cell {f.cell}: {f.detail}")
        print()

    if existing_leaks:
        print("## already in the baseline (not caused by this change, still published)")
        for f in existing_leaks:
            print(f"  {f.notebook} cell {f.cell}: {f.detail}")
        print()

    if unaccepted:
        print("## structure changed, not yet accepted")
        for f in unaccepted:
            print(f"  {f.notebook} cell {f.cell}  digest {f.digest}")
        print(
            f"\n  Read each one. To accept, add a line to {LEDGER.name}:\n"
            f"      {unaccepted[0].notebook} {unaccepted[0].cell} {unaccepted[0].digest} <why this is correct>\n"
            "  The digest ties the acceptance to this exact output, so a later change "
            "asks again.\n"
        )

    if accepted:
        print("## structure changed, accepted")
        for f in accepted:
            print(f"  {f.notebook} cell {f.cell}: {f.accepted_reason}")
        print()

    if numeric:
        print(f"## numbers moved, structure identical ({len(numeric)} cell(s))")
        for f in numeric:
            print(f"  {f.notebook} cell {f.cell}")
        print()

    stale = ledger.stale()
    if stale:
        print("## ledger entries that no longer match anything")
        for notebook, cell, digest in stale:
            print(f"  {notebook} {cell} {digest}")
        print("  Remove them, or find out why that output stopped changing.\n")

    if not findings:
        print("No differences.")
    failed = bool(leaks or unaccepted)
    print(
        f"{len(leaks)} new leak(s), {len(existing_leaks)} pre-existing, "
        f"{len(unaccepted)} unaccepted structural change(s), "
        f"{len(accepted)} accepted, {len(numeric)} numeric-only"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
