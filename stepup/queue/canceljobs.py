# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Tool to cancel jobs."""

import argparse
import subprocess
import sys
from collections.abc import Callable

from path import Path
from rich.console import Console

from stepup.core.config import ConfigLoader

from .log import read_jobid_cluster_status
from .utils import DONE_STATES, search_jobs

__all__ = ()


def canceljobs_tool(args: argparse.Namespace):
    """Iterate over all slurmjob.log files, read the SLURM job IDs, and cancel them."""
    console = Console(highlight=False)
    if not args.commit:
        console.print("[yellow]# Note: No jobs are actually cancelled.[/]")
        console.print("[yellow]# Use the --commit option to execute the cancellations.[/]")

    jobs = {}
    for path_log in search_jobs(args.paths, console):
        try:
            job_id, cluster, status = read_jobid_cluster_status(path_log)
        except ValueError as e:
            console.print(f"[red]# WARNING: Could not read job ID from {path_log}: {e}[/]")
            continue
        if args.all or status not in DONE_STATES:
            jobs.setdefault(cluster, []).append((job_id, path_log, status))

    all_good = True
    for cluster, cluster_jobs in jobs.items():
        if args.commit:
            # Cancel at most 100 at a time to avoid exceeding the command line length limit,
            # and to play nice with SLURM.
            while len(cluster_jobs) > 0:
                cancel_jobs = cluster_jobs[:100]
                cluster_jobs[:] = cluster_jobs[100:]

                command_args = ["scancel"]
                if cluster is not None:
                    command_args.extend(["-M", cluster])
                command_args.extend(str(job_id) for job_id, _, _ in cancel_jobs)

                # Using subprocess.run for better control and error handling
                print_cancel_command(
                    console, [job_id for job_id, _, _ in cancel_jobs], cluster, None
                )
                result = subprocess.run(command_args, check=False)
                all_good &= result.returncode == 0
        else:
            for job_id, path_log, status in cluster_jobs:
                print_cancel_command(console, [job_id], cluster, f"{path_log} {status}")
    if not all_good:
        console.print("[red]Some jobs could not be cancelled. See messages above.[/]")
        sys.exit(1)


def canceljobs_subcommand(subparsers, loader: ConfigLoader) -> Callable:
    parser = subparsers.add_parser(
        "canceljobs",
        help="Cancel running jobs in the current StepUp workflow.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[Path(".")],
        type=Path,
        help="Paths to the jobs to cancel. Subdirectories are searched recursively. "
        "If not specified, the current directory is used.",
    )
    parser.add_argument(
        "-c",
        "--commit",
        action="store_true",
        default=False,
        help="Execute the cancellation of jobs instead of only showing what would be done.",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=False,
        help="Select all jobs, including the ones that seem to be done already.",
    )
    loader.patch_parser(parser)
    return canceljobs_tool


def print_cancel_command(
    console: Console, job_ids: list[int], cluster: str | None, comment: str | None
) -> str:
    """Print the job cancellation command."""
    parts = ["[green]scancel[/]"]
    if cluster is not None:
        parts.append(f"[cyan]-M {cluster}[/]")
    parts.extend(str(job_id) for job_id in job_ids)
    if comment is not None:
        parts.append(f" [bright_black]# {comment}[/]")
    console.print(" ".join(parts))
