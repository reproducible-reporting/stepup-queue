<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: LGPL-3.0-or-later
-->

# Test Structure

These are pure unit tests.
No SLURM cluster is needed to run them,
because everything that would talk to the scheduler is exercised through parsing
and file-format checks rather than through live `sbatch` or `sacct` calls.

## Coding Conventions

`tests/test_conventions.py` is a two-line subclass of `ConventionTests`,
which lives in `stepup/core/pytest.py` in the StepUp Core repo.
Add a new convention check there rather than here,
so that all StepUp extension packages inherit it.

`conftest.py` loads Stepup Core's `pytest` module as a pytest plugin with `pytest_plugins`,
as the docstring of `ConventionTests` asks.

## Platforms

The suite also runs on Windows, see `docs/development.md`,
to test that the package follows the path and text file conventions of StepUp Core.
`tests/test_sbatch.py` is skipped with `pytest.importorskip("fcntl")`,
because `sq-sbatch-and-wait` needs the `fcntl` lock and only supports POSIX systems.
The skip tests for `fcntl`, not for a failing import of `stepup.queue.sbatch`,
so that a broken import of that module still fails on Linux.
