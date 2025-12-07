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

from path import Path

from .sbatch import FIRST_LINE, parse_sbatch


def canceljobs_tool(args: argparse.Namespace) -> int:
    if len(args.paths) == 0:
        args.paths = [Path(".")]

    # Iterate over all slurmjob.log files in the specified directories, and kill them.
    job_ids = {}
    for path in args.paths:
        if not path.exists():
            print(f"Path {path} does not exist.")
            continue
        if not path.is_dir():
            print(f"Path {path} is not a directory.")
            continue
        print(f"Searching recursively in {path}")
        paths_log = list(path.glob("**/slurmjob.log"))
        if (path / "slurmjob.log").is_file():
            paths_log.append(path / "slurmjob.log")
        for job_log in paths_log:
            try:
                job_id, cluster = read_jobid_cluster(job_log)
                msg = f"Found job {job_id} in {job_log}"
                if cluster is not None:
                    msg += f" on cluster {cluster}"
                print(msg)
                job_ids.setdefault(cluster, []).append(job_id)
            except ValueError as e:
                print(f"Warning: Could not read job ID from {job_log}: {e}")
                continue

    returncode = 0
    # Cancel at most 100 at a time to avoid exceeding the command line length limit,
    # and to play nice with SLURM.
    for cluster, cluster_job_ids in job_ids.items():
        while len(cluster_job_ids) > 0:
            cancel_ids = cluster_job_ids[:100]
            cluster_job_ids[:] = cluster_job_ids[100:]

            command_args = ["scancel"]
            if cluster is not None:
                command_args.extend(["-M", cluster])
            command_args.extend(str(job_id) for job_id in cancel_ids)

            # Using subprocess.run for better control and error handling
            print(f"Executing: {' '.join(command_args)}")
            result = subprocess.run(command_args, check=False)
            if result.returncode != 0:
                returncode = 1
    return returncode


def read_jobid_cluster(job_log: Path) -> tuple[str, str]:
    """Read the job ID and cluster from the job log file."""
    with open(job_log) as f:
        lines = f.readlines()
        if len(lines) < 3 or lines[0][:-1] != FIRST_LINE:
            raise ValueError(f"Invalid first line in {job_log}.")
        return parse_sbatch(lines[2].split()[-1])


def canceljobs_subcommand(subparser: argparse.ArgumentParser) -> callable:
    parser = subparser.add_parser(
        "canceljobs",
        help="Cancel running jobs in the current StepUp workflow.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Paths to the jobs to cancel. Subdirectories are searched recursively. "
        "If not specified, the current directory is used.",
    )
    return canceljobs_tool
