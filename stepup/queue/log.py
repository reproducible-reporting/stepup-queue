# StepUp Queue integrates queued jobs into a StepUp workflow.
# Copyright 2025-2026 Toon Verstraelen
#
# This file is part of StepUp Queue.
#
# StepUp Queue is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# StepUp Queue is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
# --
"""The job log file format and utilities to read and write it."""

from datetime import datetime

from path import Path

from .utils import parse_sbatch

__all__ = (
    "FIRST_LINE",
    "InpDigestError",
    "init_log",
    "log_status",
    "read_jobid_cluster_status",
    "read_log",
    "read_status",
)

FIRST_LINE = "StepUp Queue sbatch wait log format version 2"


class InpDigestError(ValueError):
    """The input digest in the log file does not match the one in the environment."""


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
    """Read the job ID, cluster, and job status from the job log file."""
    lines = read_log(path_log, None)
    if len(lines) < 1:
        raise ValueError(f"Incomplete file: {path_log}.")
    words = lines[0].split()
    if len(words) != 3:
        raise ValueError(f"Could not read job ID from first status line: {lines[0]}")
    _, status, job_id_cluster = words
    if status != "Submitted":
        raise ValueError(f"No 'Submitted' on first status line: {lines[0]}")
    job_id, cluster = parse_sbatch(job_id_cluster)
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
