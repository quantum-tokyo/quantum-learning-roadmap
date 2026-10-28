# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Japanese-language quantum computing learning site built by the [Quantum Tokyo](https://github.com/quantum-tokyo) community. Content is a set of Jupyter notebooks (Qiskit hands-on "Labs", mostly adapted from past IBM Quantum Challenge problems) rendered into a static website via **Jupyter Book 2 (MyST engine)** and deployed to GitHub Pages.

This is a content/教材 repo, not an application. "Code" here means notebook cells and the small helper modules under `src/`.

## Commands

Uses [uv](https://docs.astral.sh/uv/) for dependency and Python management (Python 3.12).

```bash
uv sync                 # install deps (uv provisions Python too); use --frozen in CI
uv sync --group authoring   # also install jupyter-collaboration, needed to edit notebooks via the Jupyter MCP server
uv run jupyter lab      # open notebooks to run/edit hands-on
uv run bash scripts/build.sh   # build the site locally -> src/_build/html (the script is not executable and calls bare `jupyter`, so run it under uv)

uv run python scripts/run-notebooks.py --group local   # execute the Labs that work offline
uv run python scripts/run-notebooks.py --list          # see the groups (local / hardware / known-broken)
```

`uv sync` is not quite enough to run every Lab: the transpilation Lab draws coupling maps, and qiskit's `plot_coupling_map` needs the **Graphviz binaries** (`dot`). The `graphviz` entry in `pyproject.toml` is only the Python binding — install Graphviz itself (`brew install graphviz`, `apt-get install graphviz`), which is what `.github/workflows/run-notebooks.yml` does.

`scripts/build.sh` exists because the MyST build must run from the directory containing the project `myst.yml` — it `cd`s into `src/` and runs `jupyter book build --html`. Do not run the build from the repo root; the root `myst.yml` is a stub and the real project config is `src/myst.yml`.

`jupyter-collaboration` lives in its own `authoring` group so CI's `uv sync` does not install it. A plain `uv sync` therefore **removes** it from your environment: re-run `uv sync --group authoring` afterwards, and restart the Jupyter server, or the MCP server's cell edits fail with a 404 on `/api/collaboration/session/...`. Start Jupyter from the repo root; the MCP server resolves notebook paths relative to wherever the server was started, so a server started in `src/` needs `ch02-grover.ipynb` instead of `src/ch02-grover.ipynb`.

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
- **Pinned Qiskit stack.** `pyproject.toml` pins exact versions (Qiskit 2.4.2, qiskit-ibm-runtime 0.50.0, qiskit-aer 0.18.0, qiskit-addon-cutting 0.10.0, qiskit-ibm-transpiler 0.14.2). Notebook code targets these versions — don't assume newer Qiskit APIs. Note the two renamed packages: `circuit-knitting-toolbox` caps qiskit at `<2.0` and became `qiskit-addon-cutting`; `qiskit-transpiler-service` became `qiskit-ibm-transpiler`. Qiskit is held at 2.4 (not the newer 2.5/2.6) on purpose, matching `docs/textbook-plan.md`. `qiskit-ibm-transpiler` is held at 0.14.2; whether 0.15.0 and later resolve against Qiskit 2.4 has not been checked. (0.14.2 already depends on `qiskit-serverless~=0.26.0`; what changes in 0.15.0 is that pin, to `~=0.28.0`. An earlier version of this note wrongly said the dependency itself was the reason.)
- **Deprecation warnings in stored outputs.** Several Labs still use APIs that Qiskit 2.4 / runtime 0.50 deprecate (`SamplerV2`/`EstimatorV2`, `mcx(mode=)`, `QFT`, `TwoLocal`). `--warnings-as-errors` fails on them; the default run does not. `--save-outputs` rewrites the kernel's temp path in warning text to `<kernel>` so the output stays reproducible.
- **Diagrams are standalone SVG files.** Write a diagram as an `.svg` in `src/resources/` and reference it from a markdown cell with `![alt text](./resources/<name>.svg)`. Do not inline `<svg>`/`<style>` in a markdown cell: MyST strips them and the page renders an empty `<div>`, while the build still passes, so the failure is silent. Do not emit the figure as a code cell's HTML output either: the page shows "Loading..." until a script runs, and the figure's source code is displayed above it. Two more traps in raw HTML inside markdown: a blank line ends the HTML block and breaks the build (`Cannot read properties of undefined (reading 'replace')`), and `data:` URIs in `<img>` fail with "Cannot find image".
- **Diagram style.** Give the SVG its own background panel (`#f6f7f9`, 1px `#c9ced6` border, rounded) and fixed colors so it reads on both the light and dark site themes; `prefers-color-scheme` does not reach an `<img>`. Use system fonts including `Hiragino Sans` / `Noto Sans JP`; labels and captions are Japanese. Keep one idea per figure and put the explanation in the text, not in the picture. A figure may only use words the reader has already met in the text above it. Do not copy English slide art (e.g. the old `2020-w1-b-*.png`); redraw it. Palette: green `#2f6f4f` for "+" and red `#c2362b` for "−"/the mean line, amber `#e0a800` for the winning item, greys for everything else. Check that captions fit inside the panel and that arrows do not cross boxes or text.
- **Generate numbers, don't type them.** When a figure shows quantities (amplitudes, probabilities), compute them with a script and write them into the SVG, and make the surrounding text agree with the computed values; the stored outputs and the figure must tell the same story. Check a figure by rendering it (headless Chrome screenshot of the built page), not by reading the SVG source.
- **IBM Quantum credentials.** Some Labs need an IBM Quantum API token, read from a root `.env` (see `.env.sample`: `QXToken`, `QXInstance`) via `python-dotenv`. Never commit real tokens.
- **End every new notebook with a version cell.** The last code cell lists the Qiskit packages the notebook itself imports (not ones pulled in indirectly), plus Python as `major.minor`. Put the code inline, not in a `src/utils/` helper: a notebook downloaded on its own would fail on `from utils... import`, and this cell is bookkeeping, not something the reader should depend on a second file for. Use exactly this cell (preceded by a `## 実行環境` heading):

  ```python
  import ast
  import platform
  from importlib.metadata import packages_distributions, version

  # このノートブックが import している Qiskit 系のパッケージだけを表示する
  used = set()
  for source in In:
      try:
          nodes = ast.walk(ast.parse(source))
      except SyntaxError:  # ! や % で始まるセルは読み飛ばす
          continue
      for node in nodes:
          if isinstance(node, ast.Import):
              tops = [a.name.split(".")[0] for a in node.names]
          elif isinstance(node, ast.ImportFrom) and node.level == 0:
              tops = [node.module.split(".")[0]]
          else:
              continue
          for top in tops:
              if top.startswith("qiskit"):
                  used.update(packages_distributions().get(top, []))

  print(f"{'python':<24} {'.'.join(platform.python_version().split('.')[:2])}")
  for name in sorted(used):
      print(f"{name:<24} {version(name)}")
  ```

  It relies on `In`, which only exists under IPython/ipykernel, and only sees cells that have already run, so it belongs after everything else. Its output is stable under `--save-outputs` (checked: two runs are byte-identical), so it needs no entry in `ENVIRONMENT_CELL`. It deliberately does not print numpy/matplotlib/etc.; their versions are fixed by `uv.lock`, not by the notebook.
- When adding a Lab: place the `.ipynb` in `src/`, put assets in `src/resources/`, register it in `src/myst.yml`'s `toc` with a title, and give it a group in `scripts/notebooks.txt` — the toc publishes it, the manifest gets it run, and `run-notebooks.py` fails until both agree.
