# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""The job log file format and utilities to read and write it."""

from datetime import datetime

from path import Path

from .utils import parse_sbatch

__all__ = (
    "FIRST_LINE",
    "InpDigestError",
    "InterruptedSubmissionError",
    "NoSubmissionError",
    "init_log",
    "log_status",
    "read_jobid_cluster_status",
    "read_log",
    "read_status",
)

FIRST_LINE = "StepUp Queue sbatch wait log format version 2"


class InpDigestError(ValueError):
    """The input digest in the log file does not match the one in the environment."""


class NoSubmissionError(ValueError):
    """The log file holds no status lines, so no job was submitted yet."""


class InterruptedSubmissionError(ValueError):
    """A submission was interrupted before the job ID could be written to the log.

    The scheduler may or may not have accepted the job,
    so a job may be running that StepUp Queue cannot identify.
    Check the queue (e.g. with squeue) and remove the log file to submit again.
    """


def init_log(path_log: str, inp_digest: str):
    """Initialize a new log file."""
    with open(path_log, "w") as fh:
        print(FIRST_LINE, file=fh)
        print(inp_digest, file=fh)


def log_status(path_log: Path, status: str):
    """Write a status to the log."""
    dt = datetime.now().isoformat()
    with open(path_log, "a") as f:
        line = f"{dt} {status}"
        f.write(f"{line}\n")


def read_jobid_cluster_status(path_log: str) -> tuple[int, str | None, str | None]:
    """Read the job ID, cluster, and job status from the job log file.

    Raises
    ------
    NoSubmissionError
        When the log holds no status lines at all.
    InterruptedSubmissionError
        When the log stops at the `Submitting` marker.
    ValueError
        When the submission cannot be parsed.
    """
    lines = read_log(path_log, None)
    if len(lines) == 0:
        raise NoSubmissionError(f"No job was submitted according to {path_log}.")
    # The submission is logged on the first status line,
    # or on the second one when the first is the `Submitting` marker.
    i_submitted = 0
    words = lines[0].split()
    if len(words) == 2 and words[1] == "Submitting":
        if len(lines) == 1:
            raise InterruptedSubmissionError(f"No job ID was recorded in {path_log}.")
        i_submitted = 1
    words = lines[i_submitted].split()
    if len(words) != 3:
        raise ValueError(f"Could not read job ID from status line: {lines[i_submitted]}")
    if words[1] != "Submitted":
        raise ValueError(f"No 'Submitted' on status line: {lines[i_submitted]}")
    job_id, cluster = parse_sbatch(words[2])
    status = read_status(lines[-1:])[1]
    return job_id, cluster, status


def read_log(path_log: str, expected_inp_digest: str | None = None) -> list[str]:
    """Read lines from a previously created log file."""
    lines = []
    with open(path_log) as f:
        try:
            check_log_version(next(f).strip())
        except StopIteration as exc:
            raise ValueError("Existing log file is empty.") from exc
        try:
            actual_inp_digest = next(f).strip()
        except StopIteration as exc:
            raise ValueError("Existing log file has no input digest.") from exc
        if expected_inp_digest is not None:
            check_log_inp_digest(actual_inp_digest, expected_inp_digest)
        for line in f:
            line = line.strip()
            lines.append(line)
    return lines


def check_log_version(line: str):
    """Validate the log version, abort if there is a mismatch."""
    if line != FIRST_LINE:
        raise ValueError(
            f"The first line of the log is wrong. Expected: '{FIRST_LINE}' Found: '{line}'"
        )


def check_log_inp_digest(actual: str, expected: str):
    """Validate the log input digest, abort if there is a mismatch."""
    if actual != expected:
        raise InpDigestError(
            "The second line of the log contains the wrong input digest.\n"
            f"Actual:   {actual}\nExpected: {expected}\n"
        )


def read_status(lines: list[str]) -> tuple[float | None, str | None]:
    """Read a status from the log file."""
    if len(lines) == 0:
        return None, None
    line = lines.pop(0)
    words = line.split(maxsplit=1)
    if len(words) != 2:
        raise ValueError(f"Expected a status in log but found line '{line}'.")
    return datetime.fromisoformat(words[0]).timestamp(), words[1].strip()
