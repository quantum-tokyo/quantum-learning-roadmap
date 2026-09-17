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
uv run python scripts/api-surface-diff.py <pkg> --old <previous version>
```

Run it **for every package the lock moved**, not only qiskit. Release notes are not enough: fetching the Qiskit 2.0 notes truncated silently at the same sentence twice, and two real breakages were in neither the retrievable notes nor the migration guides.

Three things it reports, in descending order of urgency:

- **unresolvable `__all__`** — stop here. A star import from that module raises, which is exactly how qiskit 2.5.0 broke the toffoli Lab. The script exits non-zero on this.
- **removed symbols and modules** — check whether the Labs or the installed dependencies use them.
- **changed defaults** — the ones that move numbers while every call still works. This is where the explanation for step 7's numeric diffs comes from.

### 3. Shape the pins

`pyproject.toml` states floors for the qiskit stack; `uv.lock` carries reproducibility. Build tooling (`jupyter-book`, `pylatexenc`) keeps exact pins — a major bump there changes the site.

Every cap gets a comment with the concrete symptom and the condition for lifting it. A bare `<2.5` is a cap nobody will dare remove. Regenerate and commit `uv.lock` in the same change: both workflows use `uv sync --frozen`.

### 4. Run, and fix one failure at a time

```bash
uv run python scripts/run-notebooks.py --group local
```

Execution stops at the first error, so failures arrive serially.

### 5. Take stock of the deprecations, and count before deciding scope

```bash
uv run python scripts/run-notebooks.py --group local --warnings-report
```

This collects them. `--warnings-as-errors` stops at the first one, which makes it a
gate but useless for taking stock.

**Only the warnings that reach the saved output become part of the page.** In the
2.4 upgrade, 13 distinct deprecations fired but 3 reached the output — the rest are
raised inside libraries or suppressed as repeats and never land in a cell's stderr.
Those three force a decision; the rest are debt for an issue.

**Count the source sites, not the occurrences.** Three MCX deprecations fired 132
times each and came from two lines. A number that looks like the size of the job
usually is not.

For each warning that does reach the output, either fix the call or accept it in
`accepted-output-changes.txt` with the reason. Accepting is a legitimate answer:
dropping `mcx(mode=...)` changes how the multi-controlled X is synthesised, and the
Grover Lab teaches that circuit's structure.

**If you replace a deprecated class with its function form, an equivalence check is
necessary but not sufficient.** Matching parameter count, parameter order and the
unitary is worth doing — the VQE Labs bind `x0` positionally, so order matters — but
the same unitary built from a different gate sequence transpiles differently, and on
a noisy backend that gives a different answer. `TwoLocal` to `n_local` moved a VQE's
final energy from -2.81 to -2.41 with every equivalence check passing.

### 6. Make regeneration deterministic, and prove it

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

`known-nondeterministic.txt` is for what survives all of that **after you looked and could not find the cause**. It requires a reason that says what you ruled out. Do not reach for it instead of doing the work above. If it reports an entry that never moved, either the cause is gone and the line goes, or `--rounds` was too low.

### 7. Regenerate, then read the diff

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

### 8. Follow the prose

A changed output can contradict the Japanese text beside it — a quoted number, a plugin name, a class name the learner is told to call. Check the markdown around every changed cell.

**`!pip` cells are not regenerated.** Their output is preserved so nobody's machine ends up on the page, which means `!pip show` keeps its old version numbers while every other output updates. Check any cell that displays a version by eye.

### 9. Build the site, and look at the pages that changed

```bash
./scripts/build.sh
```

A successful build does not mean the pages are right. It renders whatever is stored,
so a cleared output renders as a gap, a timeline drawing can come out blank, and a
wide table can be clipped — all with the build exiting 0. Open the pages for the
Labs whose outputs moved and look at them.

### 10. Handle the groups CI does not run

`local` is the only group CI executes. The others need deciding on, not just
mentioning:

- **`hardware`** — three Labs that need an IBM Quantum account. Their stored outputs
  stay on whatever version last ran them, so **the gap widens with every upgrade
  they sit out**. Run them with a token if you have one
  (`--group hardware --save-outputs`), and if you do not, say in the PR which
  version their outputs are from. Do not ship a silent mix of old and new.
- **`known-broken`** — check whether the upgrade changed anything for it. An entry
  there is a claim about the current state, not a permanent exemption.
- **Reclassification** — if a Lab moved between groups (it now needs credentials, or
  it stopped working), update `scripts/notebooks.txt`. The manifest must match
  `src/myst.yml`'s toc or `run-notebooks.py` refuses to start.

### 11. Push, and let CI disagree with you

Green locally is not green in CI, and the difference is the environment rather than
the code. This upgrade's predecessor passed 15/15 on macOS and failed on the runner:
`plot_coupling_map` needs the Graphviz binaries, and the laptop happened to have
`dot` installed. `.github/workflows/run-notebooks.yml` now installs it, but the shape
of that mistake recurs — anything the Labs reach outside Python is a candidate.

Wait for the workflow before calling the upgrade done. And put the evidence in the PR
body: versions before and after, what `api-surface-diff.py` reported, the ledger lines
you added and why, the magnitude of the numeric-only moves and why they are
acceptable, the `--rounds` you used, and which groups ran.

## Red flags

- "The notebooks all ran, so the upgrade is done"
- "It was byte-identical, I checked once"
- "The churn is unavoidable — I'll narrow the diff"
- "The resolver succeeded, so the versions are compatible"
- "Only numbers changed, nothing structural"
- "The build succeeded, so the pages are fine"
- "It is green on my machine, so CI will be green"

Each means going back to the step that would have caught it.
