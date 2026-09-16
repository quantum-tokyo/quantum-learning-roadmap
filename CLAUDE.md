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

`uv sync` is not quite enough to run every Lab: the transpilation Lab draws coupling maps, and qiskit's `plot_coupling_map` needs the **Graphviz binaries** (`dot`). The `graphviz` entry in `pyproject.toml` is only the Python binding — install Graphviz itself (`brew install graphviz`, `apt-get install graphviz`), which is what `.github/workflows/run-notebooks.yml` does.

`scripts/build.sh` exists because the MyST build must run from the directory containing the project `myst.yml` — it `cd`s into `src/` and runs `jupyter book build --html`. Do not run the build from the repo root; the root `myst.yml` is a stub and the real project config is `src/myst.yml`.

There is no linter. Verification = the notebooks execute cleanly and the site builds.

**The book build does not run notebooks.** `jupyter book build` renders the outputs already stored in each `.ipynb`, so a Lab can be broken without the build or the deploy workflow noticing. `scripts/run-notebooks.py` is the execution path, and `.github/workflows/run-notebooks.yml` runs its `local` group on every push and PR. Which Lab belongs to which group is recorded in `scripts/notebooks.txt`, and the script refuses to run unless that list matches `src/myst.yml`'s `toc` exactly — so **adding a Lab to the `toc` means giving it a group in `scripts/notebooks.txt` as well**, or CI fails with the mismatch named.

**Stored outputs are reproducible, and should stay that way.** Because the site renders them, `uv run python scripts/run-notebooks.py --group local --save-outputs` regenerates them, and running it twice leaves every file byte-identical. That holds only because the sampling is seeded — `seed_simulator=12345` on Aer `run()` calls, `seed=12345` on `StatevectorSampler`, `options={"simulator": {"seed_simulator": 12345}}` on the `qiskit-ibm-runtime` primitives, `seed_transpiler=` on every pass manager — and because the script drops execution timestamps, merges adjacent stream outputs, and keeps the committed output of cells that report the machine rather than Qiskit (`!pip`, `%dotenv`). When adding a Lab, seed anything that samples, and avoid ending a cell on an expression whose `repr` contains a memory address (`plt.legend()` needs a trailing `;`).

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
- **Pinned Qiskit stack.** `pyproject.toml` pins exact versions (Qiskit 2.0.3, qiskit-ibm-runtime 0.40.1, qiskit-aer 0.17.2, qiskit-addon-cutting 0.10.0, qiskit-ibm-transpiler 0.13.0). Notebook code targets these versions — don't assume newer Qiskit APIs. Note the two renamed packages: `circuit-knitting-toolbox` caps qiskit at `<2.0` and became `qiskit-addon-cutting`; `qiskit-transpiler-service` became `qiskit-ibm-transpiler`. `qiskit-ibm-transpiler` is held at 0.13.0 deliberately — 0.15.0 and later depend on `qiskit-serverless`, which drags the floor up to `qiskit>=2.2`, so bumping it means moving off 2.0 as well.
- **IBM Quantum credentials.** Some Labs need an IBM Quantum API token, read from a root `.env` (see `.env.sample`: `QXToken`, `QXInstance`) via `python-dotenv`. Never commit real tokens.
- When adding a Lab: place the `.ipynb` in `src/`, put assets in `src/resources/`, register it in `src/myst.yml`'s `toc` with a title, and give it a group in `scripts/notebooks.txt` — the toc publishes it, the manifest gets it run, and `run-notebooks.py` fails until both agree.
