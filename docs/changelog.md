---
description: >-
  Release notes for every version of StepUp Queue,
  following Keep a Changelog and effort-based versioning.
---

<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Changelog

All notable changes to StepUp Queue will be documented on this page.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Effort-based Versioning](https://jacobtomlinson.dev/effver/).
(Changes to features documented as "experimental" will not increment macro and meso version numbers.)

## [Unreleased][]

(no changes yet)

## [2.0.0][] - 2026-09-02 {: #v2.0.0 }

Compatibility with StepUp Core 4, improved robustness and helper scripts.

Note that all changes of the `2.0.0rc*` release candidates are combined below.

### Added

- A `Submitting` line is written to `slurmjob.log` right before `sbatch` is called,
  so that a submission interrupted before the job ID was recorded can be detected.
  `sq-sbatch-and-wait` refuses to submit a second job in such a directory,
  because SLURM may still hold the job of the interrupted submission.
- The `STEPUP_SBATCH_CANCEL_TIMEOUT` environment variable defines the maximum time to wait
  for a job to be cancelled after `scancel` is called.
  The default is 10 minutes, which is usually enough for SLURM to cancel a job.

### Changed

- The StepUp Queue source code has been relicensed under `LGPL-3.0-or-later`.
  This clarifies that users of StepUp can assign any license of their choice
  to the workflows they create with StepUp (e.g., `plan.py` and related files).
  This has always been the intention, but with this change, it becomes legally explicit.
- Compatibility with StepUp Core 4.0.
  StepUp Queue 2.0 does not work with StepUp Core 3.
- The `sbatch()` function is built on `run()` instead of `step()`,
  so its `pool` and `block` arguments are replaced by `resources` and `duration`.
- The `sbatch` action is replaced by the `sq-sbatch-and-wait` command,
  because StepUp Core 4 no longer supports action plugins.
- The `stepup canceljobs` and `stepup removejobs` tools are replaced
  by the regular commands `sq-cancel-jobs` and `sq-remove-jobs`.
  These commands do not interact with the internals of StepUp,
  so there is no reason to implement them as StepUp tools.
- The perpetual workflow example resubmits itself
  based on the `DRAINED` bit in StepUp's exit code,
  instead of a flag file created by a background process.
  It also refuses to start when the shutdown margins do not fit in the wall time limit,
  which used to make the workflow resubmit itself in a tight loop.
- With `onchange="resubmit"`, `sq-sbatch-and-wait` waits for the cancelled job to stop
  before submitting its replacement, instead of submitting immediately after `scancel`.
  A job that already reached a terminal state is not cancelled at all.
  A failing `scancel` is no longer an error, because the job may already be gone.
- `STEPUP_SBATCH_RETRY_DELAY_MAX` is raised to `STEPUP_SBATCH_RETRY_DELAY_MIN`
  when it would otherwise be lower, as was already the case for the polling interval.
- The delay between two `sbatch` attempts is no longer applied after the last one.
- The period after which an unlisted job is declared failed
  is counted from the moment `sq-sbatch-and-wait` starts waiting,
  not from the submission of the job.
  A job resumed from an older log used to fail on its first poll.
- The metadata that StepUp keeps for a step records the `sacct` command,
  once per `sq-sbatch-and-wait` process.

### Fixed

- With `onchange="resubmit"`, a `slurmjob.log` that records no submission
  no longer aborts the step.
  The job is submitted instead.
- `sq-remove-jobs` refuses to remove the current directory or any of its parents,
  also when the `--commit` option is given.
- A line in the `sacct` output that is not a plain job record
  (an array task, a component of a heterogeneous job, or a blank line)
  no longer hides the jobs listed after it.
  Such a line used to make every job below it appear as `invalid`,
  a state that the polling loop retries indefinitely.
- An array task in the `sacct` output is no longer read as a different job.
  `int("123_4")` returns `1234`, because Python accepts the underscore as a digit separator,
  so an array task could report its state for an unrelated job.
- The header of the `sacct` cache is written with a fixed-width timestamp.
  A timestamp that happened to fall on a whole second made `sq-sbatch-and-wait` crash.
- A failing `sacct` call no longer replaces the cached output of the last successful call.
- An empty job script now reports that a shebang line is missing
  instead of raising `StopIteration`.
- The `#SBATCH` checks no longer reject a directive
  whose value ends in something that looks like a short option, such as `--exclude=node-a`.

## [1.1.1][] - 2026-01-02 {: #v1.1.1 }

Minor improvement and bug fix.

### Changed

- Make sbatch action fail early if input digest is missing.
- Colored screen output for `stepup canceljobs` and `stepup removejobs`.

## [1.1.0][] - 2025-12-29 {: #v1.1.0 }

Refactored tools to manage SLURM jobs.

### Added

- New `stepup removejobs` command to remove job directories,
  by default only of failed jobs.
  This command uses the same safeguards as `stepup clean`
  in the upcoming StepUp Core 3.2 release, i.e.,
  it only performs destructive actions when explicitly confirmed by the user
  with the `--commit` flag.
- Detect unsupported scheduler directives in job scripts
  (e.g., PBS, LSF, Cobalt) and raise an error.

### Changed

- Refactored `stepup canceljobs` to use the same safeguards as `stepup clean`
  in the upcoming StepUp Core 3.2 release.

### Fixed

- Corrected missing dependency and inconsistency with `.github/requirements-old.txt`.
- Filter jobs by status in `stepup canceljobs`,
  so it only cancels jobs that are not done, unless the `--all` flag is used.
- Fixed mistake in regular expressions to detect forbidden `#SBATCH` options.

## [1.0.7][] - 2025-12-07 {: #v1.0.7 }

Improved robustness for workflows with many concurrent jobs.

### Changed

- Improved perpetual workflow example.
- Increased StepUp Core dependency to >=3.1.4 because it fixes a bug that is likely to occur
  in combination with StepUp Queue.
- Explicitly raise an error for array jobs, as these are not supported.
- More intuitive environment variables for polling.
- Retry `sbatch` on failure before giving up. (Default is 5 attempts with 1-2 minute delays.)
- Improved usage documentation and hints.
- Check that job scripts are executable and have a shebang line.

### Fixed

- Improved robustness for workflow with many concurrent jobs, by using `sacct`
  instead of `scontrol` to query job states.
  This avoids the ambiguity that an unlisted job may either be pending or already finished long ago.
  With `sacct`, unlisted jobs are always (about to become) pending.
- Improved parsing of `#SBATCH` lines in job scripts.
  To avoid confusion `#SBATCH -o/--output` and `#SBATCH -e/--error` will raise an error.
  (StepUp Queue overrides these options internally to capture job output and error logs.)
- Fix parsing bug in `canceljobs` tool.
- Prevent infinite loop for jobs that are unlisted for too long.
- Make `stepup canceljobs` work correctly without arguments.

## [1.0.6][] - 2025-11-30 {: #v1.0.6 }

Documentation updates and one bug fix.

### Changed

- Document how to interrupt StepUp gracefully while jobs are running.
- Document convenient settings during workflow development or debugging.
- Increased the default value of `STEPUP_SBATCH_TIME_MARGIN` from 5 to 15 seconds.
- CI testing for Python 3.14 instead of 3.13.
- Smaller package size on PyPI.
- Increased StepUp Core dependency to >=3.1.3 to ensure usage instructions work.

### Fixed

- Removed logging of potentially transient job states.

## [1.0.5][] - 2025-05-23 {: #v1.0.5 }

### Changed

- Replaced the old `STEPUP_QUEUE_RESUBMIT_CHANGED_INPUTS` environment variable
  by the more powerful `STEPUP_QUEUE_ONCHANGE`.

## [1.0.4][] - 2025-05-21 {: #v1.0.4 }

### Fixed

- Minor typo fix in slurm wrapper script.
- Improved example perpetual workflow job script.

## [1.0.3][] - 2025-05-16 {: #v1.0.3 }

### Fixed

- Fixed errors in the example job scripts.
- Improved handling of `scontrol` failures.

### Added

## [1.0.2][] - 2025-05-14 {: #v1.0.2 }

### Added

- Option to specify the extension of the job script.
- Wrap all job scripts to record their return code.
- Detect when inputs of jobs have changed + optional resubmission.
- Option to load resource configurations before sbatch is called.
- More detailed examples, including a self-submitting workflow job.

## [1.0.1][] - 2025-05-11 {: #v1.0.1 }

This is a minor cleanup release, mainly testing the release process.

## [1.0.0][] - 2025-05-11 {: #v1.0.0 }

This is an initial and experimental release of StepUp Queue.

### Added

Initial release of StepUp Queue.
The initial package is based on the `sbatch-wait` script from Parman.
It was adapted to integrate well with StepUp Core 3.
This release also features the `stepup canceljobs` tool, which was not present in Parman.

[Unreleased]: https://github.com/reproducible-reporting/stepup-queue
[2.0.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v2.0.0
[1.1.1]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.1.1
[1.1.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.1.0
[1.0.7]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.7
[1.0.6]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.6
[1.0.5]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.5
[1.0.4]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.4
[1.0.3]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.3
[1.0.2]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.2
[1.0.1]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.1
[1.0.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.0
