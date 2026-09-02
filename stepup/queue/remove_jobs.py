# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Remove the directories of failed jobs."""

import argparse
import os
import shutil
import sys
from collections.abc import Sequence

from path import Path
from rich.console import Console

from .log import read_log, read_status
from .utils import search_jobs

__all__ = ("remove_jobs",)


FAILED_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
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


def remove_jobs(argv: Sequence[str] | None = None):
    """Iterate over all slurmjob.log files and remove their parent job directories."""
    args = parse_args(argv)
    console = Console(highlight=False)
    if not args.commit:
        console.print("[yellow]# Note: No job directories are actually removed.[/]")
        console.print("[yellow]# Use the --commit option to execute the removals.[/]")

    jobs = []
    for path_log in search_jobs(args.paths, console):
        try:
            status = read_last_status(path_log)
        except ValueError as e:
            console.print(f"[red]# WARNING: Could not read job status from {path_log}: {e}[/]")
            status = None
        if args.all or status in FAILED_STATES:
            jobs.append((path_log, status))

    path_cwd = Path.cwd().realpath()
    for path_log, status in jobs:
        # `search_jobs` normalizes the paths it returns,
        # so a log file in a search path itself has an empty parent.
        path_job = path_log.parent or Path(".")
        path_full = path_job.absolute().realpath()
        if path_full == path_cwd:
            console.print("[red]# WARNING: Refusing to remove the current directory.[/]")
            continue
        if path_cwd.startswith(os.path.join(path_full, "")):
            console.print(
                f"[red]# WARNING: Refusing to remove {path_job}, "
                "a parent of the current directory.[/]"
            )
            continue
        command = f"[cyan]rm -rf[/] {path_job}  [bright_black]# state={status}[/]"
        console.print(command)
        if args.commit:
            shutil.rmtree(path_job)


def read_last_status(path_log: str) -> str | None:
    """Read the last job status from the job log file."""
    lines = read_log(path_log, None)
    return read_status(lines[-1:])[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="sq-remove-jobs",
        description="Remove directories of failed (and optionally all completed) jobs "
        "in the current StepUp workflow.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[Path(".")],
        type=Path,
        help="Paths to the jobs to remove. Subdirectories are searched recursively. "
        "If not specified, the current directory is used.",
    )
    parser.add_argument(
        "-c",
        "--commit",
        action="store_true",
        default=False,
        help="Execute the removal of jobs instead of only showing what would be done.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=False,
        help="Remove all jobs, not only failed jobs.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(remove_jobs())
