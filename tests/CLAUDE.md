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
