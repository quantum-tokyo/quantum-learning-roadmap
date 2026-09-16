---
name: regenerating-notebook-outputs
description: Use when re-executing Jupyter notebooks whose outputs are committed to the repository - after a dependency or library version change, when a site or docs are rendered from stored outputs, or when running the notebooks again produces a large diff with no source change.
---

# Regenerating notebook outputs

## Overview

Committed notebook outputs are shipped content: readers see them, and a static-site build usually renders them without ever starting a kernel. So re-executing notebooks is a **write to published material**, not a verification step.

Two things follow, and both are routinely missed:

- Regeneration **imports your machine** into the repository — your paths, whether you have credentials, what your `PATH`'s `pip` can see, the date you ran it.
- Regeneration is **not repeatable** unless you make it so. Sampling, unseeded pipeline stages, `repr` output containing memory addresses, and the kernel's stdout chunking all move between runs.

The failure mode this skill exists to prevent is treating that movement as unavoidable noise and working around it — narrowing the diff, reverting untouched files, telling reviewers to ignore the churn. It is not unavoidable. **Byte-identical regeneration is achievable, and it is the gate.**

## When to use

- A dependency version changed and outputs must be refreshed to match
- `git diff` shows large notebook churn with no source change
- You are about to commit regenerated outputs
- You need to tell whether an output changed because of the upgrade or because of sampling

Not for: notebooks whose outputs are not committed, or repos that execute notebooks at build time.

## Checklist

**Create a todo for each item. Do them in order — step 5 is uninterpretable before step 3.**

### 1. Keep the pre-change outputs reachable, and decide what must NOT be regenerated

Step 5 compares old against new, so the old outputs have to still exist. In git they do — as long as you have not committed the regenerated ones. **Do not commit regenerated outputs until step 5 is done**, and if you already regenerated before reading this, save the current state (`git diff -- '*.ipynb' > /tmp/regen.patch`) and `git checkout HEAD -- '*.ipynb'` to get the baseline back.

Then decide what must not be regenerated at all: real-hardware runs, paid API calls, results needing credentials you lack, deliberately curated figures. Identify these **before** executing anything and exclude them. Silently overwriting them is the one irreversible mistake here.

### 2. Remove the non-determinism, before regenerating

| Source | Fix |
|---|---|
| Sampling / simulators | Seed every `run()` call |
| RNG for inputs or initial values | Seed the generator |
| Compiler, optimizer, or layout stages | Seed those too (easy to miss — they are not obviously random) |
| A cell ending on an expression whose `repr` holds a memory address | End the line with `;` |
| Execution timestamps written into cell metadata | Strip on save |
| Kernel splitting stdout into a variable number of stream outputs | Merge adjacent stream outputs on save |
| Cells reporting the machine (`!pip`, `%dotenv`) | Execute them, but keep the committed output |

The last three are not random and seeding will not touch them. Expect to iterate: seeding alone typically fixes most notebooks and leaves a few.

### 3. Prove it: generate twice, compare bytes

```bash
shasum -a 256 <notebooks> > /tmp/a
<regenerate>
shasum -a 256 <notebooks> > /tmp/b
diff /tmp/a /tmp/b      # must be empty
```

Any file that differs is still non-deterministic. Find the cause and return to step 2. **"The numbers looked the same" is not evidence.** Byte-identical is.

### 4. Scan for what you imported from your machine

Grep the regenerated outputs for: absolute paths, your username, `cannot find .env`, "not found" messages from an interpreter that is not the kernel's, memory addresses (`at 0x…`), today's date. Every hit is something you just published.

### 5. Compare old against new, and classify

Substitute every run of digits with `#` to get each output's skeleton. Identical skeleton = numbers moved only; different skeleton = structure changed. Read **every** structural change; scan the numeric ones for magnitude.

Now the diff means something: with steps 2–3 done, anything that moved was moved by the upgrade, not by sampling.

### 6. Check the prose still matches

Narration next to a changed output ("this table shows…", a quoted accuracy) can now contradict it.

## Red flags

- "The churn is unavoidable — I'll narrow the diff / revert the untouched notebooks"
- "Timestamps and execution counts are just noise"
- "I ran it twice and it looked the same"
- "It worked on my machine, so I'll commit what I got"
- "I'll regenerate everything and let the reviewer read the diff"

Each means: go back to step 2 or 3.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Reverting the unrelated notebooks is good enough" | It hides the non-determinism rather than removing it. The next person regenerates and it returns, and the diff can never be trusted again. |
| "Seeding is overkill for a minor version bump" | A minor bump is exactly the case that changes numbers without raising. Without determinism you cannot attribute the change. |
| "I seeded the sampler, so it's deterministic" | Memory addresses in `repr` and stdout chunking survive seeding. Only the byte comparison tells you. |
| "The absolute path is in a warning, not a result" | It is committed and it renders. |

## Implementation

`scripts/run-notebooks.py` in this repo does steps 2 and 3: `--save-outputs` seeds nothing itself but drops execution timestamps, merges adjacent stream outputs, and restores the committed output of machine-reporting cells, so running it twice is byte-identical. Seeds live in the notebooks.
