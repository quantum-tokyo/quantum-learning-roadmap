# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Japanese-language quantum computing learning site built by the [Quantum Tokyo](https://github.com/quantum-tokyo) community. Content is a set of Jupyter notebooks (Qiskit hands-on "Labs", mostly adapted from past IBM Quantum Challenge problems) rendered into a static website via **Jupyter Book 2 (MyST engine)** and deployed to GitHub Pages.

This is a content/教材 repo, not an application. "Code" here means notebook cells and the small helper modules under `src/`.

## Commands

Uses [uv](https://docs.astral.sh/uv/) for dependency and Python management (Python 3.12).

```bash
uv sync                 # install deps (uv provisions Python too); use --frozen in CI
uv run jupyter lab      # open notebooks to run/edit hands-on
./scripts/build.sh      # build the site locally -> src/_build/html

uv run python scripts/run-notebooks.py --group local   # execute the Labs that work offline
uv run python scripts/run-notebooks.py --list          # see the groups (local / hardware / known-broken)
```

`scripts/` also holds `api-surface-diff.py`, `compare-notebook-outputs.py` and two ledgers, which exist for changing an installed version. **Read the `upgrading-a-dependency` skill before touching a version in `pyproject.toml`** — the procedure and the traps live there rather than here, because they are needed a few times a year and this file is read on every task.

`uv sync` is not quite enough to run every Lab: the transpilation Lab draws coupling maps, and qiskit's `plot_coupling_map` needs the **Graphviz binaries** (`dot`). The `graphviz` entry in `pyproject.toml` is only the Python binding — install Graphviz itself (`brew install graphviz`, `apt-get install graphviz`), which is what `.github/workflows/run-notebooks.yml` does.

`scripts/build.sh` exists because the MyST build must run from the directory containing the project `myst.yml` — it `cd`s into `src/` and runs `jupyter book build --html`. Do not run the build from the repo root; the root `myst.yml` is a stub and the real project config is `src/myst.yml`.

There is no linter. Verification = the notebooks execute cleanly and the site builds.

**The book build does not run notebooks.** `jupyter book build` renders the outputs already stored in each `.ipynb`, so a Lab can be broken without the build or the deploy workflow noticing. `scripts/run-notebooks.py` is the execution path, and `.github/workflows/run-notebooks.yml` runs its `local` group on every push and PR. Which Lab belongs to which group is recorded in `scripts/notebooks.txt`, and the script refuses to run unless that list matches `src/myst.yml`'s `toc` exactly — so **adding a Lab to the `toc` means giving it a group in `scripts/notebooks.txt` as well**, or CI fails with the mismatch named.

**Stored outputs must stay reproducible.** Regenerating them twice has to leave every file byte-identical, because that is the only thing that makes an output diff mean anything. So when adding a Lab, seed everything that samples — `seed_simulator=` on Aer `run()`, `seed=` on `StatevectorSampler`, `seed_transpiler=` on every pass manager, the last being the one people miss because routing does not look random — and do not end a cell on an expression whose `repr` contains a memory address (`plt.legend()` needs a trailing `;`).

## Architecture / structure

- **Two `myst.yml` files.** Root `myst.yml` is a near-empty MyST stub. The one that matters is `src/myst.yml` — it defines the site title, logo, and the **`toc:`** (table of contents) that determines which notebooks appear on the site and their display titles/chapter grouping (Chapter 0–3 + Chapter X). **A new Lab is not published until it is added to `src/myst.yml`'s `toc`.**
- **`src/*.ipynb`** — the Labs. Notebook filenames follow `YYYY-season-labN-topic[-ja].ipynb` (e.g. `2023-spring-lab3-iqpe.ipynb`); `-ja` marks Japanese-translated content. Files with a **`_bk` suffix** (e.g. `2020-w3-false-asteroids_bk.ipynb`) are backups/archived and are intentionally NOT in the toc — leave them out unless explicitly asked.
- **`src/intro.md`, `src/learning-roadmap.md`** — the landing/intro pages.
- **`src/resources/`** — images and data assets referenced from notebooks/markdown by relative path.
- **`src/utils/`, `src/data/`** — Python helper modules and datasets imported by specific Labs (e.g. `util_2024_spring_lab2.py`).
- **`.github/workflows/deploy-book.yml`** — on push to `main`: `uv sync --frozen` → `jupyter book build --html` in `src/` (with `BASE_URL=/quantum-learning-roadmap`) → deploy `src/_build/html` to GitHub Pages. `BASE_URL` sets the Pages subpath; keep it consistent if the repo is renamed.
- **`.github/workflows/run-notebooks.yml`** — on push and PR: runs `scripts/run-notebooks.py --group local`. This is the only job that executes notebook code; the deploy workflow above never starts a kernel. Both use `uv sync --frozen`, so `uv.lock` must be regenerated and committed alongside any `pyproject.toml` change.

## Working conventions

- **Content is Japanese.** Match the existing language and tone of surrounding notebooks/markdown when editing or adding explanations.
- **The Qiskit stack states floors, not exact versions; `uv.lock` is what pins.** Build tooling (`jupyter-book`, `pylatexenc`) keeps exact pins. Every cap in `pyproject.toml` carries its reason in a comment — never lift one without reading it.
- **`qiskit-ibm-transpiler` is not in the default install.** It pulls torch and the CUDA toolkit through `qiskit-gym`, and its only consumer is the AI transpiler Lab. `uv sync --group ai-transpiler` when you need it.
- **IBM Quantum credentials.** Some Labs need an IBM Quantum API token, read from a root `.env` (see `.env.sample`: `QXToken`, `QXInstance`) via `python-dotenv`. Never commit real tokens.
- When adding a Lab: place the `.ipynb` in `src/`, put assets in `src/resources/`, register it in `src/myst.yml`'s `toc` with a title, and give it a group in `scripts/notebooks.txt` — the toc publishes it, the manifest gets it run, and `run-notebooks.py` fails until both agree.
