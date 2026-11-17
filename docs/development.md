---
description: >-
  Set up a StepUp Queue development environment with uv, direnv and pre-commit,
  and find out how to run the tests, build the documentation and make a release.
---

<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Developer Guide

If you would like to contribute, please read [CONTRIBUTING.md](https://github.com/reproducible-reporting/.github/blob/main/CONTRIBUTING.md).

## Development Environment

If you break your development environment, you can discard it
by running `git clean -dfX` in the project root and repeating the instructions below.

We use [uv](https://docs.astral.sh/uv/) to manage the development environment.
Install it by following the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

A local installation for testing and development can be set up
using the following commands:

```bash
git clone git@github.com:reproducible-reporting/stepup-queue.git
cd stepup-queue
uv sync --extra dev
pre-commit install
```

Put the following lines in `.envrc`:

```bash
source .venv/bin/activate
export XDG_CACHE_HOME="${VIRTUAL_ENV}/cache"
export STEPUP_DEBUG="1"
export STEPUP_BUILD_DURATION="0"
export STEPUP_SYNC_RPC_TIMEOUT="30"
```

Finally, run the following commands:

```bash
direnv allow
```

Alternatively, you can prefix commands with `uv run` (e.g. `uv run pytest`)
instead of activating the virtual environment.

Note that `uv.lock` is not committed to the repo.
For development and CI, the latest versions of dependencies are used instead of some locked versions.

## Tests

We use pytest, so you can run the tests as follows:

```bash
pytest -vv
```

StepUp Queue only supports POSIX systems,
but it follows the path and text file conventions of StepUp Core,
which are tested on Windows in a virtual machine.
This uses the `winvm.sh` script of StepUp Core,
for which you need a checkout of `stepup-core` next to this repository
and a VM created as explained in `tools/winvm/README.md` of StepUp Core.
From the root of this repository, run:

```bash
W=../stepup-core/tools/winvm/winvm.sh
$W start
$W test
WINVM_PYTHON=3.11 $W test
$W stop
```

The `test` command copies the working tree, including uncommitted changes, into the VM
and runs the test suite there.
`tests/test_sbatch.py` is skipped on Windows,
because `sq-sbatch-and-wait` needs the `fcntl` module, which only exists on POSIX systems.

## Documentation

The documentation is created using [Zensical](https://zensical.org/),
configured in `zensical.toml`.
Only the current version is published:
every commit on the main branch republishes the site with GitHub Pages.

Edit the documentation Markdown files with a live preview by running:

```bash
zensical serve
```

(Keep this running.)
Then open the live preview in your browser at
[http://localhost:8000/stepup-queue/](http://localhost:8000/stepup-queue/)
and edit Markdown files in your IDE.

The example pages include the files of the examples
with the block form of the [Snippets](https://facelessuser.github.io/pymdown-extensions/extensions/snippets/)
extension, using paths relative to `docs/`:

<!-- The leading semicolons escape the snippet markers and do not appear on the page. -->

````markdown
```python
;--8<--
examples/slurm-basic/plan.py
;--8<--
```
````

Do not use the single-line form `--8<-- "path"` in a Python code block,
because Ruff formats the code blocks in Markdown files and rewrites that line
as if it were a Python expression.
The block form is not valid Python, so Ruff leaves it alone.

Please use [Semantic Line Breaks](https://sembr.org/)
because it results in cleaner file diffs when editing documentation.

## How to Make a Release

- Mark the release in `docs/changelog.md`.
  Do not forget to extend the links at the bottom of the file.
- Make a new commit and tag it with `vX.Y.Z`.
- Trigger the PyPI GitHub Action: `git push origin main --tags`.
