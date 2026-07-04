# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Utility functions for the StepUp queue module."""

from itertools import chain

from path import Path
from rich.console import Console

__all__ = (
    "DONE_STATES",
    "KNOWN_JOB_STATES",
    "parse_sbatch",
    "search_jobs",
)


# From: https://slurm.schedmd.com/job_state_codes.html
KNOWN_JOB_STATES = {
    # -- Job states
    # done
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "TIMEOUT",
    # waiting or running
    "PENDING",
    "RUNNING",
    "SUSPENDED",
    # -- Job flags
    # done
    "LAUNCH_FAILED",
    "RECONFIG_FAIL",
    "REVOKED",
    "STOPPED",
    # waiting or running
    "COMPLETING",
    "CONFIGURING",
    "EXPEDITING",
    "POWER_UP_NODE",
    "REQUEUED",
    "REQUEUE_FED",
    "REQUEUE_HOLD",
    "RESIZING",
    "RESV_DEL_HOLD",
    "SIGNALING",
    "SPECIAL_EXIT",
    "STAGE_OUT",
    "UPDATE_DB",
    # -- Specific to this script
    # to be ignored (same as waiting or running), must not be logged
    "invalid",
    "unlisted",
}

DONE_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "TIMEOUT",
    "LAUNCH_FAILED",
    "RECONFIG_FAIL",
    "REVOKED",
    "STOPPED",
}


def search_jobs(paths: list[Path], console: Console | None = None) -> list[Path]:
    """Recursively search for slurmjob.log files in the specified directories.

    Parameters
    ----------
    paths
        List of directories to search in.
    console
        Rich console for printing warnings. If None, no warnings are printed.

    Returns
    -------
    paths_log
        Sorted list of found slurmjob.log file paths.
    """
    paths_log = set()
    for path in paths:
        if not path.exists():
            if console is not None:
                console.print(f"[red]# WARNING: Path {path} does not exist.[/]")
            continue
        if not path.is_dir():
            if console is not None:
                console.print(f"[red]# WARNING: Path {path} is not a directory.[/]")
            continue
        for path_sub in chain([path], path.walkdirs()):
            path_log = path_sub / "slurmjob.log"
            if path_log.is_file():
                paths_log.add(path_log)
    return sorted(paths_log)


def parse_sbatch(stdout: str) -> tuple[int, str | None]:
    """Parse the 'parsable' output of sbatch."""
    words = stdout.split(";")
    if len(words) == 1:
        return int(words[0]), None
    if len(words) == 2:
        return int(words[0]), words[1]
    raise ValueError(f"Cannot parse sbatch output: {stdout}")
