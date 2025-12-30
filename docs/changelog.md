<!-- markdownlint-disable no-duplicate-heading -->

# Changelog

All notable changes to StepUp Queue will be documented on this page.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Effort-based Versioning](https://jacobtomlinson.dev/effver/).
(Changes to features documented as "experimental" will not increment macro and meso version numbers.)

## [Unreleased][]

(no changes yet)

### Changed

- Make sbatch action fail early if input digest is missing.

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
  With `sact`, unlisted jobs are always (aboute to become) pending.
- Improved parsing of `#SBATCH` lines in job scripts.
  To avoid confusion `#STBATCH -o/--output` and `#SBATCH -e/--error` will raise an error.
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
[1.1.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.1.0
[1.0.7]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.7
[1.0.6]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.6
[1.0.5]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.5
[1.0.4]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.4
[1.0.3]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.3
[1.0.2]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.2
[1.0.1]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.1
[1.0.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.0
