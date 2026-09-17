---
name: upgrading-a-dependency
description: Use when changing an installed version in this repository - bumping Qiskit or one of the qiskit ecosystem packages, refreshing uv.lock, or any pyproject.toml edit that moves a version.
---

# Upgrading a dependency

## Overview

The site renders the outputs stored in each `.ipynb`, and `jupyter book build` never starts a kernel. So a version change can leave every Lab executing cleanly while the published pages teach something different. **"It runs" is not the finish line. "It still says the same thing, and every change is attributable" is.**

The order below exists for attribution. Without a pre-change baseline and a regeneration that is byte-reproducible, a diff cannot tell you whether the upgrade moved a number or the run did — and a diff you cannot attribute is worthless.

## Checklist

Create a todo per item and work in order.

### 1. Find out whether the target is reachable — before reading any code

Registry metadata answers this. Which direct dependencies cap the target version? Are the ones that cap it renamed or abandoned? `circuit-knitting-toolbox` became `qiskit-addon-cutting`; `qiskit-transpiler-service` became `qiskit-ibm-transpiler`.

Watch for the interlocking case: a package can pin a second, which caps a third, so "everything at latest" has no solution and there are several exclusive answers that each give something up. Let the resolver find a set rather than hand-picking versions.

**A declared constraint is not compatibility.** `qiskit-ibm-transpiler` 0.13.0 declares no upper bound on qiskit and still imports a module qiskit 2.5 removed — the resolver produced a working-looking, broken environment. An unbounded ceiling on an old release is a promise nobody made. Always run after resolving.

Also weigh what a bump drags in. `qiskit-ibm-transpiler`'s qiskit-2.x releases pull `qiskit-gym`, torch and the CUDA toolkit: 116 packages become 211, for one Lab that CI never runs. That is what `[dependency-groups] ai-transpiler` is for.

### 2. Learn what actually changed

```bash
uv run python scripts/api-surface-diff.py <pkg> --old <前の版>
```

Run it **for every package the lock moved**, not only qiskit. Release notes are not enough: fetching the Qiskit 2.0 notes truncated silently at the same sentence twice, and two real breakages were in neither the retrievable notes nor the migration guides.

Three things it reports, in descending order of urgency:

- **unresolvable `__all__`** — stop here. A star import from that module raises, which is exactly how qiskit 2.5.0 broke the toffoli Lab. The script exits non-zero on this.
- **removed symbols and modules** — check whether the Labs or the installed dependencies use them.
- **changed defaults** — the ones that move numbers while every call still works. This is where the explanation for step 6's numeric diffs comes from.

### 3. Shape the pins

`pyproject.toml` states floors for the qiskit stack; `uv.lock` carries reproducibility. Build tooling (`jupyter-book`, `pylatexenc`) keeps exact pins — a major bump there changes the site.

Every cap gets a comment with the concrete symptom and the condition for lifting it. A bare `<2.5` is a cap nobody will dare remove. Regenerate and commit `uv.lock` in the same change: both workflows use `uv sync --frozen`.

### 4. Run, and fix one failure at a time

```bash
uv run python scripts/run-notebooks.py --group local
```

Execution stops at the first error, so failures arrive serially.

### 5. Make regeneration deterministic, and prove it

```bash
uv run python scripts/run-notebooks.py --group local --check-idempotent --rounds 3
```

Byte-identical across every round is the gate. **"The numbers looked the same" is not evidence, and neither is one round** — one Lab here moves in about half of runs, so a single pair of passes reports it stable and the gate goes green on luck. Raise `--rounds` rather than trusting two.

Where to look when something moves:

| Source | Fix |
|---|---|
| Sampling and simulators | `seed_simulator=12345`, `StatevectorSampler(seed=12345)`, `options={"simulator": {"seed_simulator": 12345}}` on runtime primitives |
| Compiler, layout, routing | `seed_transpiler=` — the one people miss, because routing does not look random |
| A cell ending on an expression whose `repr` holds an address | end the line with `;` |
| Timestamps, stdout chunking, the ipykernel temp path | already normalised on save; nothing to do |

`known-nondeterministic.txt` is for what survives all of that **after you looked and could not find the cause**. It requires a reason that says what you ruled out. Do not reach for it instead of step 5. If it reports an entry that never moved, either the cause is gone and the line goes, or `--rounds` was too low.

### 6. Regenerate, then read the diff

```bash
uv run python scripts/run-notebooks.py --group local --save-outputs
uv run python scripts/compare-notebook-outputs.py --group local --base HEAD
uv run python scripts/compare-notebook-outputs.py --group local --base main
```

Compare against `main` as well: that is the cumulative change a reader receives.

- **new leak** — no accept path exists, and rightly. Absolute paths, `ipykernel_<pid>`, `cannot find .env`, `Package(s) not found`, `at 0x…`. Fix the cell and re-run.
- **structural, not accepted** — open the notebook and read the output itself, not just the digest. Then add a line to `accepted-output-changes.txt` with a reason; the script refuses an entry without one. Start a new `# --- <old> -> <new> ---` section.
- **stale ledger entries** — a previous section's digests stop matching once the same cell moves again. Replace those lines; do not leave them.
- **numeric-only** — not blocked, and **the most dangerous category**. Read the magnitudes. A few percent on a noisy backend is fine. Broken is: Grover's peak no longer the maximum, an error-correction fidelity that stops supporting the claim, a VQE that no longer looks minimised, a counts distribution whose mode is not the answer. Nothing raised, and the Lab is wrong.

### 7. Follow the prose

A changed output can contradict the Japanese text beside it — a quoted number, a plugin name, a class name the learner is told to call. Check the markdown around every changed cell.

**`!pip` cells are not regenerated.** Their output is preserved so nobody's machine ends up on the page, which means `!pip show` keeps its old version numbers while every other output updates. Check any cell that displays a version by eye.

### 8. Say what CI did not cover

`hardware` Labs keep their old outputs unless you run them with a token. State in the PR which groups ran and which did not, rather than shipping a silent mix.

## Red flags

- "The notebooks all ran, so the upgrade is done"
- "It was byte-identical, I checked once"
- "The churn is unavoidable — I'll narrow the diff"
- "The resolver succeeded, so the versions are compatible"
- "Only numbers changed, nothing structural"

Each means going back to the step that would have caught it.
