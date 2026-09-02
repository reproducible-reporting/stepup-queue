<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: LGPL-3.0-or-later
-->

# Job Files and the Submit-and-Wait Contract

## Job Lifecycle and Files

Every SLURM job lives in its own working directory, with these file conventions:

- `slurmjob{ext}`: the user-written job script.
  It must be executable and must have a shebang.
- `slurmjob.log`: the StepUp Queue log, tracking submission and SLURM state history.
- `slurmjob.out` and `slurmjob.err`: SLURM stdout and stderr, declared as `out`.
- `slurmjob.ret`: the exit code written by the wrapper script, declared as `out`.

`slurmjob.log` is declared as a `vol` (volatile) file in StepUp, not as `out`,
because its contents are timestamps and scheduler state,
which are not reproducible output.

## Idempotent Submit-and-Wait

`submit_once_and_wait()` in `sbatch.py` is the core function.
The contract it implements is that a step which is interrupted and re-run
attaches to the job it already submitted, instead of submitting a second one:

1. It reads `slurmjob.log` and compares the stored input digest
   against `STEPUP_STEP_INP_DIGEST`.
2. With no log, it submits a new job.
3. With a log whose digest matches, it resumes waiting for the existing job.
4. With a digest mismatch, the `onchange` policy decides
   between `raise`, `resubmit` and `ignore`.

This is why the digest is written into the log rather than derived at read time:
the log has to be interpretable by a process that never saw the original submission.

The invariant behind the contract is that at most one job runs per job directory,
because every job in it writes to the same `slurmjob.out`, `slurmjob.err` and `slurmjob.ret`.
Two places protect it:

- The `Submitting` marker is logged before `sbatch` runs and replaced by `Submitted <jobid>`
  once the job ID is known.
  A log that stops at the marker means the job ID may have been lost,
  so the next run refuses to submit rather than risk a second job next to an untracked one.
- `onchange="resubmit"` waits for the cancelled job to leave the queue before resubmitting,
  because `scancel` returns as soon as the request is accepted.

## sacct Caching

All concurrent `sq-sbatch-and-wait` processes share one cached `sacct` result per cluster,
guarded by an `fcntl.LOCK_EX` lock, so that only one process queries SLURM at a time.
Without this, a workflow with many parallel jobs hammers the scheduler
with one `sacct` call per job per polling interval,
which is the kind of load that gets a user throttled or banned on a shared cluster.
