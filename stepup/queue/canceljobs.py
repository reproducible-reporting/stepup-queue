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
"""Tool to cancel jobs."""

import argparse
import subprocess
import sys

from path import Path

from .sbatch import DONE_STATES, parse_sbatch, read_log, read_status
from .utils import search_jobs


def canceljobs_tool(args: argparse.Namespace):
    """Iterate over all slurmjob.log files, read the SLURM job IDs, and cancel them."""
    jobs = {}
    for path_log in search_jobs(args.paths, verbose=True):
        try:
            job_id, cluster, status = read_jobid_cluster_status(path_log)
        except ValueError as e:
            print(f"# WARNING: Could not read job ID from {path_log}: {e}")
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
                print(" ".join(command_args))
                result = subprocess.run(command_args, check=False)
                all_good &= result.returncode == 0
        else:
            for job_id, path_log, status in cluster_jobs:
                command = "scancel"
                if cluster is not None:
                    command += f" -M {cluster}"
                command += f" {job_id}  # {path_log} {status}"
                print(command)
    if not all_good:
        print("Some jobs could not be cancelled. See messages above.")
        sys.exit(1)


def read_jobid_cluster_status(path_log: str) -> tuple[int, str | None, str | None]:
    """Read the job ID, cluster, and job status from the job log file."""
    lines = read_log(path_log, False)
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


def canceljobs_subcommand(subparser: argparse.ArgumentParser) -> callable:
    parser = subparser.add_parser(
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
    return canceljobs_tool
