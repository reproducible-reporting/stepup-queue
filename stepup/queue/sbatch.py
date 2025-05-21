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
"""An sbatch wrapper to submit only on the first call, and to wait until a job has finished."""

import fcntl
import os
import random
import re
import time
from datetime import datetime

from path import Path

from stepup.core.utils import string_to_bool
from stepup.core.worker import WorkThread

FIRST_LINE = "StepUp Queue sbatch wait log format version 2"
SCONTROL_FAILED = "The command `scontrol show job` failed!\n"
DEBUG = string_to_bool(os.getenv("STEPUP_SBATCH_DEBUG", "0"))
CACHE_TIMEOUT = int(os.getenv("STEPUP_SBATCH_CACHE_TIMEOUT", "30"))
POLLING_INTERVAL = int(os.getenv("STEPUP_SBATCH_POLLING_INTERVAL", "10"))
TIME_MARGIN = int(os.getenv("STEPUP_SBATCH_TIME_MARGIN", "5"))


def submit_once_and_wait(
    work_thread: WorkThread, job_ext: str, sbatch_rc: str | None = None
) -> int:
    """Submit a job and wait for it to complete. When called a second time, just wait.

    Parameters
    ----------
    work_thread
        The work thread to use for launching the subprocesses.
    job_ext
        The file extension of the job script to be submitted.
    sbatch_rc
        A resource configuration needed before calling sbatch.
        This is executed in the same shell, right before calling sbatch.

    Returns
    -------
    returncode
        The return code of the job.
        0 if successful, 1 if the job failed.
    """
    # Read previously logged steps
    path_log = Path("slurmjob.log")
    if path_log.is_file():
        previous_lines = _read_log(path_log)
    else:
        previous_lines = []
        _init_log(path_log)

    # Go through or skip steps.
    submit_time, status = read_step(previous_lines)
    if status is None:
        # A new job must be submitted.
        submit_time = time.time()
        sbatch_stdout = submit_job(work_thread, job_ext, sbatch_rc)
        log_step(path_log, f"Submitted {sbatch_stdout}")
        rndsleep()
    else:
        # The first step, if present in the log, is the submission.
        step, sbatch_stdout = status.split()
        if step != "Submitted":
            raise ValueError(f"Expected 'Submitted' in log, found '{step}'")
    jobid, cluster = parse_sbatch(sbatch_stdout)

    # Wait for the job to complete
    # The polling loop below is discouraged in the Slurm documentation,
    # yet this is also how the `sbatch --wait` command works internally.
    # See https://bugs.schedmd.com/show_bug.cgi?id=14638
    # The maximum sleep time between two calls in `sbatch --wait` is 32 seconds.
    # See https://github.com/SchedMD/slurm/blob/master/src/sbatch/sbatch.c
    # Here, we take a random sleep time, by default between 30 and 60 seconds to play nice.
    status = "UNDEFINED"
    done = False
    while not done:
        status, done = _read_or_poll_status(
            work_thread, submit_time, jobid, cluster, previous_lines, path_log, status
        )

    # Get the return code from the job
    with open("slurmjob.ret") as fh:
        returncode = fh.read().strip()
    if returncode == "":
        raise ValueError("The job did not return a return code, e.g. because it was cancelled.")
    return int(returncode)


def _read_log(path_log: str) -> list[str]:
    """Read lines from a previously created log file."""
    lines = []
    with open(path_log) as f:
        try:
            check_log_version(next(f).strip())
        except StopIteration as exc:
            raise ValueError("Existing log file is empty.") from exc
        try:
            check_log_inp_digest(next(f).strip())
        except StopIteration as exc:
            raise ValueError("Existing log file is empty.") from exc
        for line in f:
            line = line.strip()
            lines.append(line)
    return lines


def _init_log(path_log: str):
    """Initialize a new log file."""
    inp_digest = os.getenv("STEPUP_STEP_INP_DIGEST")
    if inp_digest is None:
        raise ValueError("The environment variable STEPUP_STEP_INP_DIGEST is not set.")
    with open(path_log, "w") as fh:
        print(FIRST_LINE, file=fh)
        print(inp_digest, file=fh)


def _read_or_poll_status(
    work_thread: WorkThread,
    submit_time: float,
    jobid: int,
    cluster: str,
    previous_lines: list[str],
    path_log: str,
    last_status: str,
) -> tuple[str, bool]:
    """One polling iteration. Before polling, previous lines from the log are parsed.

    Parameters
    ----------
    work_thread
        The work thread to use for launching the scontrol command.
    submit_time
        The timestamp when the job was submitted.
    jobid
        The job of which the status must be polled.
    cluster
        The cluster on which the job is submitted.
    previous_lines
        Lines from an existing log file to be processed first.
        (It will be gradually emptied.)
    path_log
        The log file to write new polling results to.
    last_status
        The status from the previous iteration.
        If the status does not change, nothing is added to the log file.

    Returns
    -------
    status
        The status result obtained by polling the scheduler.
    done
        True when the waiting is over.
    """
    # First try to replay previously logged steps
    status_time, status = read_step(previous_lines)
    if status is None:
        # All previously logged steps are processed.
        # Call scontrol and parse its response.
        rndsleep()
        status_time, status = get_status(work_thread, jobid, cluster)
        if status != last_status:
            log_step(path_log, status)
    done = (status_time > submit_time + TIME_MARGIN) and (
        status not in ["PENDING", "CONFIGURING", "RUNNING", "invalid"]
    )
    return status, done


def check_log_version(line: str):
    """Validate the log version, abort if there is a mismatch."""
    if line != FIRST_LINE:
        raise ValueError(
            f"The first line of the log is wrong. Expected: '{FIRST_LINE}' Found: '{line}'"
        )


class InpDigestError(ValueError):
    """The input digest in the log file does not match the one in the environment."""


def check_log_inp_digest(line: str):
    """Validate the log input digest, abort if there is a mismatch."""
    inp_digest = os.getenv("STEPUP_STEP_INP_DIGEST")
    if inp_digest is None:
        raise ValueError("The environment variable STEPUP_STEP_INP_DIGEST is not set.")
    if line != inp_digest:
        raise InpDigestError(
            "The second line of the log contains the wrong input digest.\n"
            f"Expected: {inp_digest}\nFound:    {line}"
        )


def read_step(lines: list[str]) -> str | None:
    """Read a step from the log file."""
    if len(lines) == 0:
        return None, None
    line = lines.pop(0)
    words = line.split(maxsplit=1)
    if len(words) != 2:
        raise ValueError(f"Expected a step in log but found line '{line}'.")
    return datetime.fromisoformat(words[0]).timestamp(), words[1]


def rndsleep():
    """Randomized sleep to distribute I/O load evenly."""
    sleep_seconds = 1 if DEBUG else random.randint(POLLING_INTERVAL, POLLING_INTERVAL + TIME_MARGIN)
    time.sleep(sleep_seconds)


JOB_SCRIPT_WRAPPER = """\
#!/usr/bin/env bash
{sbatch_header}

touch slurmjob.ret
chmod +x '{job_script}'
./'{job_script}'
RETURN_CODE=$?
echo $RETURN_CODE > slurmjob.ret
exit $RETURN_CODE
"""


def submit_job(work_thread: WorkThread, job_ext: str, sbatch_rc: str | None = None) -> str:
    """Submit a job with sbatch."""
    # Copy the #SBATCH lines from the job script.
    path_job = f"slurmjob{job_ext}"
    with open(path_job) as f:
        sbatch_header = "\n".join(line for line in f if line.startswith("#SBATCH"))

    command = "sbatch --parsable -o slurmjob.out -e slurmjob.err"
    if sbatch_rc is not None:
        command = f"{sbatch_rc} < /dev/null && {command}"
    returncode, stdout, stderr = work_thread.runsh(
        command,
        stdin=JOB_SCRIPT_WRAPPER.format(
            sbatch_header=sbatch_header,
            job_script=path_job,
        ),
    )
    if returncode != 0:
        if not (stderr is None or stderr == ""):
            print(stderr)
        raise RuntimeError(f"sbatch failed with return code {returncode}.")
    return stdout.strip()


def log_step(path_log: Path, step: str):
    """Write a step to the log."""
    dt = datetime.now().isoformat()
    with open(path_log, "a") as f:
        line = f"{dt} {step}"
        f.write(f"{line}\n")


def parse_sbatch(stdout: str) -> tuple[int, str | None]:
    """Parse the 'parsable' output of sbatch."""
    words = stdout.split(";")
    if len(words) == 1:
        return int(words[0]), None
    if len(words) == 2:
        return int(words[0]), words[1]
    raise ValueError(f"Cannot parse sbatch output: {stdout}")


def get_status(work_thread: WorkThread, jobid: int, cluster: str | None) -> str:
    """Load cached scontrol output or run scontrol if outdated.

    Parameters
    ----------
    work_thread
        The work thread to use for launching the scontrol command.
    jobid
        The job to wait for.
    cluster
        The cluster to which the job was submitted.

    Returns
    -------
    status
        A status reported by scontrol,
        or `invalid` if scontrol failed (retry scontrol later),
        or `unlisted` if the job is not found (probably ended long ago).
    """
    # Load cached output or run again
    command = "scontrol show job"
    path_out = Path(os.getenv("HOME")) / ".cache/stepup-queue"
    if cluster is None:
        path_out /= "sbatch_wait.out"
    else:
        command += f" --cluster={cluster}"
        path_out /= f"sbatch_wait.{cluster}.out"
    status_time, scontrol_out, returncode = cached_run(
        work_thread, command, path_out, CACHE_TIMEOUT
    )
    if returncode != 0:
        return status_time, "invalid"
    return status_time, parse_scontrol_out(scontrol_out, jobid)


def cached_run(
    work_thread: WorkThread, command: str, path_out: Path, cache_timeout
) -> tuple[float, str, int]:
    """Execute a command if its previous output is outdated.

    Parameters
    ----------
    work_thread
        The work thread to use for launching the command.
    command
        Command to run if the cached output is outdated.
    path_out
        The path where the output is cached.
    cache_timeout
        The waiting time between two actual calls.

    Returns
    -------
    cache_time
        The time when the command was last executed.
    stdout
        The output of the file, either new or cached.
    returncode
        The return code of the (cached) command.

    Notes
    -----
    The cached output is updated only if the command has a zero exit code.
    In all other cases, the result of the call is ignored, assuming the error is transient.
    """
    if not path_out.exists():
        path_out.parent.makedirs_p()
        path_out.touch()

    with open(path_out, mode="r+") as fh:
        fcntl.lockf(fh, fcntl.LOCK_EX)
        fh.seek(0)
        header = fh.read(CACHE_HEADER_LENGTH)
        cache_time, returncode = parse_cache_header(header)
        if cache_time is None or time.time() > cache_time + cache_timeout:
            returncode, stdout, _ = work_thread.runsh(command)
            # Go the the beginning of the file before truncating.
            # (Possibly related to issue with zero bytes at start of file.)
            fh.seek(0)
            fh.truncate(0)
            cache_time = time.time()
            header = make_cache_header(cache_time, returncode)
            fh.write(header)
            fh.write(stdout)
            fh.flush()
            os.fsync(fh.fileno())
            return cache_time, stdout, returncode
        return cache_time, fh.read(), returncode


def make_cache_header(cache_time: float, returncode: int):
    """Prepare a header for the file containing the cached output of a cached execution."""
    iso = datetime.fromtimestamp(cache_time).isoformat()
    if len(iso) != 26:
        raise AssertionError
    return f"v1 datetime={iso} returncode={returncode:+04d}\n"


def parse_cache_header(header: str) -> tuple[float, int]:
    """Read the header of a cached output and return the timestamp and returncode."""
    if len(header) == 0 or header == "\x00" * CACHE_HEADER_LENGTH:
        return None, None
    if len(header) == CACHE_HEADER_LENGTH:
        if not header.startswith("v1 datetime="):
            raise ValueError("Invalid header")
        cache_time = datetime.fromisoformat(header[12:38]).timestamp()
        returncode = int(header[50:54])
        return cache_time, returncode
    raise ValueError(f"Cannot parse cache header: {header}")


CACHE_HEADER_LENGTH = len(make_cache_header(time.time(), 0))


def parse_scontrol_out(scontrol_out: str, jobid: int) -> str:
    """Get the job state for a specific from from the output of ``scontrol show job``.

    Parameters
    ----------
    scontrol_out
        A string with the output of ``scontrol show job``.
    jobid
        The jobid of interest.

    Returns
    -------
    jobstate
        The status of the job. This can be:

        - Any of the SLURM job states.
        - `unlisted` if the job cannot be found,
          which practically means it has ended long ago.
    """
    match = re.search(
        f"JobId={jobid}.*?JobState=(?P<state>[A-Z]+)",
        scontrol_out,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is not None:
        return match.group("state")
    return "unlisted"
