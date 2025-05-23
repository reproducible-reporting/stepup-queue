<!-- markdownlint-disable no-duplicate-heading -->

# Changelog

All notable changes to StepUp Queue will be documented on this page.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Effort-based Versioning](https://jacobtomlinson.dev/effver/).
(Changes to features documented as "experimental" will not increment macro and meso version numbers.)

## [Unreleased][]

(no changes yet)

## [1.0.5][] - 2025-05-23 {: #v1.0.4 }

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
[1.0.5]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.5
[1.0.4]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.4
[1.0.3]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.3
[1.0.2]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.2
[1.0.1]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.1
[1.0.0]: https://github.com/reproducible-reporting/stepup-queue/releases/tag/v1.0.0
