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
"""StepUp Queue package."""

import argparse
import contextlib
import os
import shlex

from path import Path

from stepup.core.worker import WorkThread

from .canceljobs import read_jobid_cluster_status
from .sbatch import InpDigestError, submit_once_and_wait


def sbatch(argstr: str, work_thread: WorkThread) -> int:
    # Use argparse to parse the argstr
    parser = argparse.ArgumentParser()
    parser.add_argument("ext", nargs="?", default=".sh")
    parser.add_argument("--rc", default=None)
    default_onchange = os.getenv("STEPUP_QUEUE_ONCHANGE", "raise")
    parser.add_argument(
        "--onchange", default=default_onchange, choices=["raise", "resubmit", "ignore"]
    )
    args = parser.parse_args(shlex.split(argstr))

    if args.onchange == "resubmit":
        with contextlib.suppress(InpDigestError):
            return submit_once_and_wait(work_thread, args.ext, args.rc)
        # Cancel running job (if any), clean log and resubmit
        path_log = Path("slurmjob.log")
        job_id, cluster, _ = read_jobid_cluster_status(path_log)
        if cluster is None:
            work_thread.runsh(f"scancel {job_id}")
        else:
            work_thread.runsh(f"scancel -M {cluster} {job_id}")
        path_log.remove_p()
    return submit_once_and_wait(work_thread, args.ext, args.rc, args.onchange != "ignore")
