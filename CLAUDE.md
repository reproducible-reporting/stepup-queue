<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: LGPL-3.0-or-later
-->
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code)
when working with code in this repository.

Guidance that applies to only part of the repo lives next to the code it governs:

- `stepup/queue/CLAUDE.md`: job file conventions, the submit-and-wait contract, sacct caching.
- `tests/CLAUDE.md`: test layout and conventions.

## Project Overview

StepUp Queue is a [StepUp Core](https://github.com/reproducible-reporting/stepup-core)
extension that integrates the SLURM job scheduler into a StepUp workflow.
It lets workflows submit SLURM jobs, wait for them,
and resume from existing jobs after a restart,
which makes long-running HPC workflows resumable across interrupted sessions.

The related `stepup-core` repo is at `../stepup-core` and on GitHub.

## Architecture

The package is organized around two layers:

- **`stepup/queue/api.py`** is the Python API that users call in their `plan.py` build scripts.
  Its `sbatch()` function calls `stepup.core.api.run()`
  to register a `sq-sbatch-and-wait` step with StepUp Core.

- **Individual command modules** each implement a `main()` function that serves as a CLI tool.
  These are registered via `[project.scripts]` and the `stepup.tools` entry points
  in `pyproject.toml`, and are invoked by StepUp steps as external commands.
  When StepUp executes such a step, the command runs in the working directory of the job.

## Coding Conventions

- **En and em dashes** never appear in prose (comments, docstrings, Markdown),
  in neither glyph (–, —) nor ASCII (--) form.
  Use "which"/"because"/"that", or split the sentence.
- **Do not add `# noqa`**
  unless the violation is a genuine false positive that cannot be resolved by restructuring.

### Docstrings

Use **NumPy-style** sections (`Parameters`, `Returns`, `Raises`, ...)
Some conventions specific to this codebase:

- Docstrings are written in Markdown, not reStructuredText! Some important gotcha's:
    - Do not use italics for parameter names, return values, or exception names.
      Use single backticks instead.
    - Use single backticks for all inline code, not double backticks.
    - Use triple backticks for code blocks,
      and specify the language for syntax highlighting (e.g., ```python).
- Lines are wrapped using semantic breaks, per [Semantic Line Breaks](#semantic-line-breaks) below.
- Use the imperative mood for function descriptions
  (e.g., "Compute the hash of a file."),
  except for `@property` getters where the description should be a noun phrase
  (e.g., "The parent directory path.").
- Do not repeat type annotations in the docstring, they are already in the function signature.
- In `Parameters` sections, use the **parameter name** as the heading for each parameter.
  Grouping closely related parameters under a combined heading
  (e.g., `stdout, stderr`) is allowed when parameters are better described together.

- In `Returns` sections, use a **semantic name** for the return value, not the type,
  as these are already in the function signature.

    ```python
    # correct
    Returns
    -------
    parent
        The parent directory path.

    # wrong, the type is already in the signature
    Returns
    -------
    Path
        The parent directory path.
    ```

### Markdown

Section headings (`##`, `###`, ...) use **Title Case**
(capitalize nouns, verbs, adjectives, and adverbs; lowercase articles,
coordinating conjunctions, and prepositions regardless of length, e.g. "from", "with").
Inline code spans (e.g. `` `sbatch()` ``) keep their own casing and are never title-cased.

### Semantic Line Breaks

All English prose in this repo (comments, docstrings, Markdown documentation, commit messages, ...)
uses **semantic line breaks**.
See <https://sembr.org/>.
Prose diffs then stay small, because editing one sentence never reflows its neighbours.

- **Every sentence starts on a new line.**
- **Break inside a sentence only where a break is needed, and then at a clause boundary.**
  A sentence that fits within the 100-character line length stays on a single line.
  A longer one is broken before a conjunction or a relative pronoun
  ("and", "but", "because", "which", "if", ...),
  or after a leading subordinate clause.
- **Not every comma is a break.**
  Enumerated items, appositions and short parentheticals stay on the line they started on.

The 100-character line length is a hard cap, not a target to fill.
An extra break inside a long sentence is fine when it clarifies the structure,
but a sentence that already fits on one line is left alone.

### Prose That Ages Well

Stale prose is worse than no prose.
When writing comments, docstrings, or other prose, avoid:

- **Describing callers.** Don't note how other code uses a function or class.
  That's the caller's concern, and the remark silently rots when the caller changes.
- **Describing history.** Don't explain what the code used to do or how it changed.
  The current code should speak for itself; history belongs in commit messages.
- **Implementation details in docstrings.** Document the contract (how to use something),
  not how it works internally.
- **Line-number references.** They break as soon as the file changes.
  Point to a function, class, or file name instead.
- **Restating the code.** A comment should say something the code doesn't already say
  (the reason, the invariant, the non-obvious constraint) not paraphrase the next line.
  A purely redundant comment isn't wrong, so nothing forces it to be updated,
  and it drifts out of sync silently.
- **Repetitive and duplicate comments.**
  If a remark is repeated in multiple places, it will rot in one place when updated in another.
  Factor out the common remark into a single function or class docstring,
  or a Markdown file in `docs/`.
- **Timeless phrasing for point-in-time claims.**
  An empirical observation about an external tool or environment
  (e.g. "sacct always reports a terminal state") can stop being true after a version upgrade,
  with nothing to flag the comment as outdated.
  Say what was observed and, when it matters, on what
  (e.g. "as of SLURM 23.11, observed on a single-cluster setup").

### `__all__`

Wildcard imports are banned (ruff `F403`), so `__all__` does not describe a star-import
surface here. It is the module's **import contract**: the names that code outside the module
is meant to import.

- Every module in `stepup/queue/` declares `__all__`, placed directly after the imports
  and before any module-level constant.
  It is a tuple of string literals, sorted (enforced by ruff `RUF022`),
  and it is declared exactly once per module.
- List a name when it is imported by another `stepup` module, a downstream extension package,
  a user's `plan.py`, or a `pyproject.toml` entry point (e.g. `build_subcommand`).
- Do not list module-internal names, even when they lack a leading underscore:
  `logger`, helpers used only within the module.
  A public-looking name is not a claim that the name is exported.
- Tests may import names that are not in `__all__`; white-box testing does not make a name
  part of the contract.
- Do not re-export: a name in `__all__` must be defined in that same module.
  Import a name from the module that defines it, not from a module that happens to import it.
- `__all__ = ()` is a real claim, nothing outside the module may import from it,
  and is correct only for leaf modules.
