# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Tool to remove failed jobs."""

import argparse
import shutil
from collections.abc import Callable

from path import Path
from rich.console import Console

from stepup.core.config import ConfigLoader

from .log import read_log, read_status
from .utils import search_jobs

__all__ = ()


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


def removejobs_tool(args: argparse.Namespace):
    """Iterate over all slurmjob.log files and remove their parent job directories."""
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

    for path_log, status in jobs:
        command = f"[cyan]rm -rf[/] {path_log.parent}  [bright_black]# state={status}[/]"
        console.print(command)
        if args.commit:
            shutil.rmtree(path_log.parent)


def read_last_status(path_log: str) -> str | None:
    """Read the last job status from the job log file."""
    lines = read_log(path_log, None)
    return read_status(lines[-1:])[1]


def removejobs_subcommand(subparsers, loader: ConfigLoader) -> Callable:
    parser = subparsers.add_parser(
        "removejobs",
        help="Remove directories of failed (and optionally all completed) jobs "
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
    loader.patch_parser(parser)
    return removejobs_tool
