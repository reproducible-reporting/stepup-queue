# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StepUp Queue is a StepUp Core extension that integrates SLURM job scheduler workflows. It allows
StepUp workflows to submit SLURM jobs, wait for them, and resume from existing jobs after restarts
— making long-running HPC workflows resumable across interrupted sessions.

The related `stepup-core` repo is at `../stepup-core` and on GitHub.

## Development Environment

Uses [uv](https://docs.astral.sh/uv/) for environment management:

```bash
uv sync --extra dev
pre-commit install
direnv allow   # activates .venv and sets env vars from .envrc
```

The `.envrc` sets `STEPUP_DEBUG=1`, `STEPUP_BUILD_DURATION=0`, and `STEPUP_SYNC_RPC_TIMEOUT=30`.
Without `direnv`, prefix commands with `uv run`.

## Common Commands

```bash
# Run all tests (parallel by default via pytest-xdist, quite fast)
pytest -vv

# Run all linters
pre-commit run --all

# Docs live preview
mkdocs serve
```

## Architecture

### Package layout

```text
stepup/queue/
  api.py         — Public Python API: sbatch() for use in plan.py files
  sbatch.py      — sq-sbatch-and-wait CLI: submits, waits, polls, caches sacct output
  log.py         — slurmjob.log format (version 2): read/write/validate
  utils.py       — SLURM state sets, parse_sbatch(), search_jobs()
  canceljobs.py  — stepup canceljobs subcommand
  removejobs.py  — stepup removejobs subcommand
```

### How it fits into StepUp

`stepup.queue.api.sbatch()` is called from a user's `plan.py`. It calls
`stepup.core.api.run()` to register the `sq-sbatch-and-wait` step with StepUp Core.
When StepUp executes that step, `sq-sbatch-and-wait` (entry point for `stepup/queue/sbatch.py`)
runs in the working directory of the job.

### Job lifecycle and files

Every SLURM job lives in its own working directory. The conventions are:

- `slurmjob{ext}` — the user-written job script (must be executable, must have shebang)
- `slurmjob.log` — StepUp Queue's log (volatile; tracks submission + SLURM state history)
- `slurmjob.out` / `slurmjob.err` — SLURM stdout/stderr (declared as `out`)
- `slurmjob.ret` — exit code written by wrapper script (declared as `out`)

`slurmjob.log` is declared as a `vol` (volatile) file in StepUp, not `out`, so it is not
treated as reproducible output. It contains: a version header, an input digest (SHA-256 of
all step inputs), and timestamped status lines (`Submitted <jobid>[;cluster]`, then SLURM states).

### Idempotent submit-and-wait

`submit_once_and_wait()` in `sbatch.py` is the core function:

1. Reads `slurmjob.log` and checks the stored input digest against `STEPUP_STEP_INP_DIGEST`.
2. If no log exists → submits a new job via `sbatch --parsable`.
3. If log exists with a matching digest → resumes waiting for the existing job.
4. If digest mismatch → behaviour depends on `onchange` policy (`raise`/`resubmit`/`ignore`).
5. Polls status via `sacct`, using a **shared on-disk cache** at
   `.stepup/queue/sbatch_wait_sacct[.cluster].out` with `fcntl.LOCK_EX` to avoid
   hammering SLURM when many jobs run in parallel.

### sacct caching

`cached_run()` in `sbatch.py` manages the shared `sacct` cache. All concurrent `sq-sbatch-and-wait`
processes share a single cached file per cluster; only one process calls `sacct` at a time (via
`fcntl` lock). The cache file has a fixed-length header (`v1 datetime=... returncode=...`).

### Entry points

- `sq-sbatch-and-wait` — CLI that wraps `sbatch()` → `submit_once_and_wait()`
- `stepup canceljobs` — registered as `stepup.tools` entry point; cancels running SLURM jobs
  by reading `slurmjob.log` files recursively
- `stepup removejobs` — registered as `stepup.tools` entry point; removes directories of failed jobs

### Key environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `STEPUP_SBATCH_CACHE_TIMEOUT` | 30 | Seconds between sacct calls |
| `STEPUP_SBATCH_POLLING_MIN/MAX` | 10/20 | Random polling interval (seconds) |
| `STEPUP_SBATCH_RETRY_NUM` | 5 | sbatch retry attempts on transient failure |
| `STEPUP_SBATCH_RETRY_DELAY_MIN/MAX` | 60/120 | Retry delay range (seconds) |
| `STEPUP_SACCT_START_TIME` | now-7days | `-S` argument passed to sacct |
| `STEPUP_SBATCH_UNLISTED_TIMEOUT` | 600 | Seconds before unlisted job is declared failed |
| `STEPUP_QUEUE_ONCHANGE` | raise | Default `onchange` policy |

### Linting

Ruff with `line-length = 100`, targeting Python 3.11+. The `ruff.lint` section in
`pyproject.toml` selects many rule sets; several `PLR` (complexity) rules are deliberately
disabled. Imports are sorted with `stepup` as a known-first-party package.

### Testing

`pytest` is configured with `-n auto --dist worksteal -W error` — all warnings are errors,
tests run in parallel. The `conftest.py` provides only a `path_tmp` fixture wrapping `tmpdir`.
Tests are pure unit tests; no SLURM cluster is required.

## Release Process

1. Update `docs/changelog.md` with the new version.
2. Commit and tag: `git tag vX.Y.Z`.
3. Push with tags: `git push origin main --tags` (triggers PyPI GitHub Action).
