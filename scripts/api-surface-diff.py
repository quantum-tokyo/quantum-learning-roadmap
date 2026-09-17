#!/usr/bin/env python
"""Report what a library version change did to a package's public API.

Release notes are the usual source for this and they are not sufficient. While
upgrading Qiskit here, fetching the 2.0 release notes truncated silently at the
same sentence twice, and two real breakages -- the removal of the ``stochastic``
routing plugin and the timeline drawer's new ``target`` requirement -- appeared
in neither the notes we could retrieve nor the two migration guides. Diffing the
installed packages answers the question directly instead.

Three kinds of change are reported, because each one broke something real here:

* **removed symbols** -- ``StochasticSwap``, ``CXCancellation``
* **changed signatures** -- ``generate_preset_pass_manager`` kept its name but
  lost its ``timing_constraints`` argument, so a name-only diff misses it
* **unresolvable ``__all__`` entries** -- qiskit 2.5.0 lists ``draw`` in
  ``qiskit.visualization.__all__`` without providing it, which makes
  ``from qiskit.visualization import *`` raise. These never appear in ``dir()``,
  so only ``__all__`` itself shows them.

Each side is dumped in its own throwaway environment, so any two released
versions can be compared without touching this project's environment.

Usage:
    uv run python scripts/api-surface-diff.py qiskit --old 2.0.3
    uv run python scripts/api-surface-diff.py qiskit --old 1.4.2 --new 2.0.3
    uv run python scripts/api-surface-diff.py qiskit --old 2.4.2 --new 2.5.2
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
import re
import subprocess
import sys
import warnings

# Object addresses differ between interpreters and mean nothing here.
ADDRESS = re.compile(r"at 0x[0-9a-fA-F]+")


def dump(package: str) -> dict:
    """Describe the public API of an installed package."""
    warnings.simplefilter("ignore")
    modules: dict[str, dict] = {}

    # A distribution name and its import name differ often enough to matter:
    # `qiskit-aer` installs from that name but imports as `qiskit_aer`. Passing the
    # hyphenated form used to yield a dump holding only an error, which compared
    # as "nothing changed" and exited 0 -- the exact silent false-clean this
    # script exists to prevent.
    candidates = [package.replace("-", "_"), package] if "-" in package else [package]
    root, failure = None, None
    for candidate in candidates:
        try:
            root = importlib.import_module(candidate)
            package = candidate
            break
        except Exception as exc:  # noqa: BLE001 - report rather than crash
            failure = exc
    if root is None:
        return {
            "package": package,
            "version": None,
            "error": f"{type(failure).__name__}: {failure}",
        }

    names = [package]
    if hasattr(root, "__path__"):
        names += [
            info.name
            for info in pkgutil.walk_packages(root.__path__, prefix=f"{package}.")
            # Private subpackages are not API and importing them is often slow.
            if not any(part.startswith("_") for part in info.name.split("."))
        ]

    for name in names:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            modules[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue

        declared = list(getattr(module, "__all__", []) or [])
        unresolvable = [n for n in declared if not hasattr(module, n)]

        symbols: dict[str, str | None] = {}
        for symbol in dir(module):
            if symbol.startswith("_"):
                continue
            try:
                value = getattr(module, symbol)
            except Exception:  # noqa: BLE001 - an unresolvable __all__ entry
                continue
            # Only classes and functions: module-level constants leaking through
            # (`pi`, `theta`, `rules`) are not API and were a large share of the
            # noise when this reported everything public.
            if not (inspect.isclass(value) or inspect.isroutine(value)):
                continue
            origin = getattr(value, "__module__", None)
            if origin is not None and not origin.startswith(package):
                continue
            # Report each symbol only where it is defined. Without this, Target
            # and Parameter show up in thirty modules that merely re-export
            # them, and one change is reported thirty times.
            if origin is not None and origin != name and not origin.startswith(f"{package}._"):
                continue
            symbols[symbol] = signature_of(value)

        modules[name] = {
            "declared": declared,
            "unresolvable": unresolvable,
            "symbols": symbols,
        }

    return {
        "package": package,
        "version": getattr(root, "__version__", None),
        "modules": modules,
    }


def signature_of(value) -> list[list] | None:
    """Parameters as [name, kind, default-repr], or None when uninspectable.

    Deliberately not the rendered signature string: comparing that reports every
    added type annotation as a change, which drowned the real findings when this
    was first run against qiskit 2.4 -> 2.5.
    """
    target = value
    if inspect.isclass(value):
        target = getattr(value, "__init__", None)
        if target is None:
            return None
    if not callable(target):
        return None
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        # Rust-backed callables and builtins often have no introspectable
        # signature. Absence is not a change, so record it as unknown.
        return None
    parameters = []
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        default = (
            None
            if parameter.default is inspect.Parameter.empty
            # A default's repr often carries the object's address, which differs
            # between two interpreters and says nothing. Same trap as notebook
            # outputs holding `at 0x…`.
            else ADDRESS.sub("at 0x…", repr(parameter.default))
        )
        parameters.append([name, parameter.kind.name, default])
    # A signature of exactly (*args, **kwargs) tells us nothing about the real
    # parameters -- it is what classes moved into Rust look like. Treat it as
    # uninspectable rather than as every parameter having been dropped.
    kinds = [p[1] for p in parameters]
    if kinds == ["VAR_POSITIONAL", "VAR_KEYWORD"]:
        return None
    return parameters


def dump_version(package: str, version: str | None) -> dict:
    """Dump `package` at `version`, in a throwaway environment when pinned."""
    if version is None:
        return dump(package)
    command = [
        "uv", "run", "--no-project", "--quiet",
        "--with", f"{package}=={version}",
        "python", __file__, package, "--dump",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(
            f"failed to dump {package}=={version}\n"
            + (result.stderr or result.stdout).strip()[-2000:]
        )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("package", help="package to inspect, e.g. qiskit")
    parser.add_argument("--old", help="version to compare from; required unless --dump")
    parser.add_argument(
        "--new",
        help="version to compare to; defaults to whatever is installed here",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="print this environment's API surface as JSON (used for the pinned side)",
    )
    parser.add_argument("--json", action="store_true", help="print the diff as JSON")
    args = parser.parse_args()

    if args.dump:
        print(json.dumps(dump(args.package)))
        return 0
    if not args.old:
        parser.error("--old is required")

    old = dump_version(args.package, args.old)
    new = dump_version(args.package, args.new)

    # Refuse to report on a dump that holds only an import error. Comparing one
    # produces "no removals" and exit 0, which reads as a clean bill of health.
    for side, dumped in (("--old", old), ("--new", new)):
        if dumped.get("error"):
            sys.exit(
                f"could not import {args.package!r} on the {side} side:"
                f" {dumped['error']}\n"
                "  Pass the import name rather than the distribution name"
                " (qiskit_aer, not qiskit-aer)."
            )

    diff = compare(old, new)
    if args.json:
        print(json.dumps(diff, indent=2))
    else:
        report(old, new, diff)
    # Unresolvable __all__ entries are a defect in the new version, not a
    # judgement call: a star import from that module cannot work.
    return 1 if diff["unresolvable"] else 0


def compare_parameters(before, after) -> dict | None:
    """What changed between two parameter lists, ignoring annotations."""
    if before is None or after is None:
        return None
    old_names = [p[0] for p in before]
    new_names = [p[0] for p in after]
    dropped = [n for n in old_names if n not in new_names]
    gained = [n for n in new_names if n not in old_names]
    # A changed default is the silent kind: callers keep working and start
    # getting different results. On a minor upgrade that is the main risk.
    old_defaults = {p[0]: p[2] for p in before}
    redefaulted = [
        {"parameter": p[0], "old": old_defaults[p[0]], "new": p[2]}
        for p in after
        if p[0] in old_defaults and old_defaults[p[0]] != p[2]
    ]
    if not (dropped or redefaulted):
        return None
    entry: dict = {}
    if dropped:
        entry["dropped"] = dropped
    if gained:
        entry["gained"] = gained
    if redefaulted:
        entry["redefaulted"] = redefaulted
    return entry


def compare(old: dict, new: dict) -> dict:
    removed: dict[str, list[str]] = {}
    changed: dict[str, list[dict]] = {}
    added: dict[str, list[str]] = {}
    unresolvable: dict[str, list[str]] = {}
    gone: list[str] = []

    for name, before in old.get("modules", {}).items():
        after = new.get("modules", {}).get(name)
        if after is None:
            gone.append(name)
            continue
        if "error" in before or "error" in after:
            continue
        removed_here = sorted(set(before["symbols"]) - set(after["symbols"]))
        added_here = sorted(set(after["symbols"]) - set(before["symbols"]))
        changed_here = []
        for symbol in sorted(set(before["symbols"]) & set(after["symbols"])):
            entry = compare_parameters(before["symbols"][symbol], after["symbols"][symbol])
            if entry:
                changed_here.append({"symbol": symbol, **entry})
        if removed_here:
            removed[name] = removed_here
        if added_here:
            added[name] = added_here
        if changed_here:
            changed[name] = changed_here

    for name, after in new.get("modules", {}).items():
        if after.get("unresolvable"):
            unresolvable[name] = after["unresolvable"]

    return {
        "removed": removed,
        "changed": changed,
        "added": added,
        "unresolvable": unresolvable,
        "modules_gone": sorted(gone),
    }


def report(old: dict, new: dict, diff: dict) -> None:
    print(f"{old['package']} {old['version']} -> {new['version']}")
    print(
        f"  modules compared: {len(old.get('modules', {}))}"
        f" / symbols: {sum(len(m.get('symbols', {})) for m in old.get('modules', {}).values())}"
    )

    if diff["unresolvable"]:
        print("\n## __all__ entries that do not resolve (a star import from these raises)")
        for module, names in sorted(diff["unresolvable"].items()):
            print(f"  {module}: {', '.join(names)}")

    if diff["modules_gone"]:
        print("\n## modules that no longer exist")
        for module in diff["modules_gone"]:
            print(f"  {module}")

    if diff["removed"]:
        print("\n## removed symbols")
        for module, names in sorted(diff["removed"].items()):
            print(f"  {module}: {', '.join(names)}")

    if diff["changed"]:
        print("\n## dropped parameters and changed defaults")
        for module, entries in sorted(diff["changed"].items()):
            print(f"  {module}")
            for entry in entries:
                print(f"    {entry['symbol']}")
                if entry.get("dropped"):
                    print(f"      dropped: {', '.join(entry['dropped'])}")
                if entry.get("gained"):
                    print(f"      gained:  {', '.join(entry['gained'])}")
                for change in entry.get("redefaulted", []):
                    # "no default" and "the default is None" both render as None
                    # otherwise, and they are different kinds of change: losing a
                    # default breaks callers, changing its value moves results.
                    old = "(required)" if change["old"] is None else change["old"]
                    new = "(required)" if change["new"] is None else change["new"]
                    print(f"      default: {change['parameter']} {old} -> {new}")

    total_added = sum(len(v) for v in diff["added"].values())
    print(f"\nadded symbols: {total_added} (not listed; additions do not break callers)")
    if not any((diff["removed"], diff["changed"], diff["unresolvable"], diff["modules_gone"])):
        print("No removals, signature changes, or unresolvable exports.")


if __name__ == "__main__":
    sys.exit(main())
