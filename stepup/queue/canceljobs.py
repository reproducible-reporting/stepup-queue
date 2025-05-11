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

import os
import argparse

from path import Path

from .sbatch import FIRST_LINE


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
        for job_log in path.glob("**/slurmjob.log"):
            with open(job_log, "r") as f:
                lines = f.readlines()
                if len(lines) < 2 or lines[0][:-1] != FIRST_LINE:
                    print(f"Invalid first line in {job_log}.")
                    continue
                job_id, cluster = lines[1].split()[-1].split(";")
                print(f"Found job {job_id} on cluster {cluster} in {job_log}")
                job_ids.setdefault(cluster, []).append(job_id)
    # Cancel 100 at a time to avoid exceeding the command line length limit.
    for cluster, job_ids in job_ids.items():
        while len(job_ids) > 0:
            command = f"scancel -M {cluster} " + " ".join(job_ids[:100])
            print(command)
            os.system(command)
            job_ids[:] = job_ids[100:]


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

