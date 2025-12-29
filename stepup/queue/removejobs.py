# StepUp Queue integrates queued jobs into a StepUp workflow.
# © 2025 Toon Verstraelen
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
"""Tool to remove failed jobs."""

import argparse
import shutil

from path import Path

from .sbatch import read_log, read_status
from .utils import search_jobs

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
    jobs = []
    for path_log in search_jobs(args.paths, verbose=True):
        try:
            status = read_last_status(path_log)
        except ValueError as e:
            print(f"Warning: Could not read job status from {path_log}: {e}")
            status = None
        if args.all or status in FAILED_STATES:
            jobs.append((path_log, status))

    for path_log, status in jobs:
        command = f"rm -rf {path_log.parent}  # state={status}"
        print(command)
        if args.commit:
            shutil.rmtree(path_log.parent)


def read_last_status(path_log: str) -> str | None:
    """Read the last job status from the job log file."""
    lines = read_log(path_log, False)
    return read_status(lines[-1:])[1]


def removejobs_subcommand(subparser: argparse.ArgumentParser) -> callable:
    parser = subparser.add_parser(
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
    return removejobs_tool
