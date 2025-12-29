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

from stepup.core.worker import WorkThread

FIRST_LINE = "StepUp Queue sbatch wait log format version 2"
SBATCH_RETRY_NUM = int(os.getenv("STEPUP_SBATCH_RETRY_NUM", "5"))
SBATCH_RETRY_DELAY_MIN = int(os.getenv("STEPUP_SBATCH_RETRY_DELAY_MIN", "60"))
SBATCH_RETRY_DELAY_MAX = int(os.getenv("STEPUP_SBATCH_RETRY_DELAY_MAX", "120"))
CACHE_TIMEOUT = int(os.getenv("STEPUP_SBATCH_CACHE_TIMEOUT", "30"))
POLLING_MIN = int(os.getenv("STEPUP_SBATCH_POLLING_MIN", "10"))
POLLING_MAX = max(int(os.getenv("STEPUP_SBATCH_POLLING_MAX", "20")), POLLING_MIN)
SACCT_START = os.getenv("STEPUP_SACCT_START_TIME", "now-7days")
UNLISTED_TIMEOUT = int(os.getenv("STEPUP_SBATCH_UNLISTED_TIMEOUT", "600"))


def submit_once_and_wait(
    work_thread: WorkThread,
    job_ext: str,
    sbatch_rc: str | None = None,
    validate_inp_digest: bool = True,
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
    validate_inp_digest
        If False, the input digest is not checked.
        This is useful when the job script is modified but the changes are harmless.

    Returns
    -------
    returncode
        The return code of the job.
        0 if successful, 1 if the job failed.
    """
    # Read previously logged job states
    path_log = Path("slurmjob.log")
    previous_lines = read_log(path_log, validate_inp_digest) if path_log.is_file() else []

    # Go through or skip states.
    submit_time, status = read_status(previous_lines)
    if status is None:
        # A new job must be submitted.
        submit_time = time.time()
        sbatch_stdout = submit_job(work_thread, job_ext, sbatch_rc)
        # Create a new log file after submitting the job.
        _init_log(path_log)
        log_status(path_log, f"Submitted {sbatch_stdout}")
        rndsleep()
    else:
        # The first state, if present in the log, is the submission.
        words = status.split()
        if len(words) != 2 or words[0] != "Submitted":
            raise ValueError(f"Expected 'Submitted' in log, found '{status}'")
        sbatch_stdout = words[1]
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

    if status == "COMPLETED":
        # Get the return code from the job
        with open("slurmjob.ret") as fh:
            returncode = fh.read().strip()
        try:
            return int(returncode)
        except ValueError as exc:
            raise ValueError(
                f"Could not parse return code from slurmjob.ret. Got '{returncode}'"
            ) from exc
    raise RuntimeError(f"Job ended with status '{status}'.")


def read_log(path_log: str, do_inp_digest: bool = True) -> list[str]:
    """Read lines from a previously created log file."""
    lines = []
    with open(path_log) as f:
        try:
            check_log_version(next(f).strip())
        except StopIteration as exc:
            raise ValueError("Existing log file is empty.") from exc
        try:
            inp_digest = next(f).strip()
        except StopIteration as exc:
            raise ValueError("Existing log file has no input digest.") from exc
        if do_inp_digest:
            check_log_inp_digest(inp_digest)
        for line in f:
            line = line.strip()
            lines.append(line)
    return lines


def check_log_version(line: str):
    """Validate the log version, abort if there is a mismatch."""
    if line != FIRST_LINE:
        raise ValueError(
            f"The first line of the log is wrong. Expected: '{FIRST_LINE}' Found: '{line}'"
        )


def _init_log(path_log: str):
    """Initialize a new log file."""
    inp_digest = os.getenv("STEPUP_STEP_INP_DIGEST")
    if inp_digest is None:
        raise ValueError("The environment variable STEPUP_STEP_INP_DIGEST is not set.")
    with open(path_log, "w") as fh:
        print(FIRST_LINE, file=fh)
        print(inp_digest, file=fh)


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
        The work thread to use for launching the sacct command.
    submit_time
        The timestamp when the job was submitted.
    jobid
        The job of which the status must be polled.
    cluster
        The cluster on which the job is submitted.
    previous_lines
        Lines from an existing log file to be processed first.
        (It will be gradually emptied.)
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
    # First try to replay previously logged states
    _, status = read_status(previous_lines)
    if status is None:
        # All previously logged states are processed.
        # Call sacct and parse its response.
        rndsleep()
        _, status = get_status(work_thread, jobid, cluster)
        # Log only if the status changed, and is not invalid or unlisted.
        # These two statuses are (potentially) transient and should not be logged.
        if status != last_status and status not in ["invalid", "unlisted"]:
            log_status(path_log, status)
    if status not in KNOWN_JOB_STATES:
        raise ValueError(f"Unknown job status '{status}' obtained from scheduler.")

    # Determine if the job is done
    done = status in DONE_STATES
    if status == "unlisted" and time.time() > submit_time + UNLISTED_TIMEOUT:
        # If the job remains unlisted for too long, we declare it failed.
        # This prevents an infinite loop if the job ID was wrong or purged.
        done = True

    return status, done


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


def read_status(lines: list[str]) -> tuple[float | None, str | None]:
    """Read a status from the log file."""
    if len(lines) == 0:
        return None, None
    line = lines.pop(0)
    words = line.split(maxsplit=1)
    if len(words) != 2:
        raise ValueError(f"Expected a status in log but found line '{line}'.")
    return datetime.fromisoformat(words[0]).timestamp(), words[1].strip()


def rndsleep():
    """Randomized sleep to distribute I/O load evenly."""
    sleep_seconds = random.randint(POLLING_MIN, POLLING_MAX)
    time.sleep(sleep_seconds)


JOB_SCRIPT_WRAPPER = """\
#!/usr/bin/env bash
{sbatch_header}

touch slurmjob.ret
./'{job_script}'
RETURN_CODE=$?
echo $RETURN_CODE > slurmjob.ret
exit $RETURN_CODE
"""

RE_SBATCH_STDOUT = re.compile(r"\s*#\s*SBATCH\b.*(--output|-o)\b")
RE_SBATCH_STDERR = re.compile(r"\s*#\s*SBATCH\b.*(--error|-e)\b")
RE_SBATCH_ARRAY = re.compile(r"\s*#\s*SBATCH\b.*(--array|-a)\b")
RE_SBATCH = re.compile(r"\s*#\s*SBATCH\b")
UNSUPPORTED_DIRECTIVES = [
    re.compile(r"\s*#\s*PBS\b"),
    re.compile(r"\s*#\s*BSUB\b"),
    re.compile(r"\s*#\s*COBALT\b"),
    re.compile(r"\s*#\$"),
]


def submit_job(work_thread: WorkThread, job_ext: str, sbatch_rc: str | None = None) -> str:
    """Submit a job with sbatch."""
    # Verify that the job script is executable.
    path_job = f"slurmjob{job_ext}"
    if not os.access(path_job, os.X_OK):
        raise ValueError("The job script must be executable.")

    # Copy the #SBATCH lines from the job script and perform some checks.
    with open(path_job) as f:
        sbatch_header = []
        first_line = next(f)
        if not first_line.startswith("#!"):
            raise ValueError("The job script must start with a shebang line.")
        for line in f:
            if RE_SBATCH_STDOUT.match(line):
                raise ValueError("The job script must not contain a #SBATCH --output/-o line.")
            if RE_SBATCH_STDERR.match(line):
                raise ValueError("The job script must not contain a #SBATCH --error/-e line.")
            if RE_SBATCH_ARRAY.match(line):
                raise ValueError("StepUp Queue does not support array jobs. (Found -a or --array)")
            if RE_SBATCH.match(line):
                sbatch_header.append(line.strip())
            else:
                for pattern in UNSUPPORTED_DIRECTIVES:
                    if pattern.match(line):
                        raise ValueError(
                            f"Detected unsupported scheduler directive: {line.strip()}."
                        )
        sbatch_header = "\n".join(sbatch_header)

    command = "sbatch --parsable -o slurmjob.out -e slurmjob.err"
    if sbatch_rc is not None:
        command = f"{sbatch_rc} < /dev/null && {command}"
    stdin = JOB_SCRIPT_WRAPPER.format(sbatch_header=sbatch_header, job_script=path_job)
    for _ in range(SBATCH_RETRY_NUM):
        returncode, stdout, stderr = work_thread.runsh(command, stdin=stdin)
        if returncode == 0:
            return stdout.strip()
        if not (stderr is None or stderr == ""):
            print(stderr)
        delay = random.randint(SBATCH_RETRY_DELAY_MIN, SBATCH_RETRY_DELAY_MAX)
        print(f"sbatch failed with return code {returncode}. Retrying in {delay} seconds.")
        time.sleep(delay)
    raise RuntimeError(f"sbatch failed {SBATCH_RETRY_NUM} times. Giving up.")


def log_status(path_log: Path, status: str):
    """Write a status to the log."""
    dt = datetime.now().isoformat()
    with open(path_log, "a") as f:
        line = f"{dt} {status}"
        f.write(f"{line}\n")


def parse_sbatch(stdout: str) -> tuple[int, str | None]:
    """Parse the 'parsable' output of sbatch."""
    words = stdout.split(";")
    if len(words) == 1:
        return int(words[0]), None
    if len(words) == 2:
        return int(words[0]), words[1]
    raise ValueError(f"Cannot parse sbatch output: {stdout}")


def get_status(work_thread: WorkThread, jobid: int, cluster: str | None) -> tuple[float, str]:
    """Load cached sacct output or run sacct if outdated.

    Parameters
    ----------
    work_thread
        The work thread to use for launching the sacct command.
    jobid
        The job to wait for.
    cluster
        The cluster to which the job was submitted.

    Returns
    -------
    timestamp
        The time when the status was last retrieved.
    status
        A status reported by sacct,
        or `invalid` if sacct failed (retry sacct later),
        or `unlisted` if the job is not found (probably ended long ago).
    """
    # Load cached output or run again
    command = f"sacct -o 'jobid,state' -PXn -S {SACCT_START}"
    path_out = Path(os.getenv("ROOT", ".")) / ".stepup/queue"
    if cluster is None:
        path_out /= "sbatch_wait_sacct.out"
    else:
        command += f" --cluster={cluster}"
        path_out /= f"sbatch_wait_sacct.{cluster}.out"
    status_time, sacct_out, returncode = cached_run(work_thread, command, path_out, CACHE_TIMEOUT)
    if returncode != 0:
        return status_time, "invalid"
    return status_time, parse_sacct_out(sacct_out, jobid)


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
        raise RuntimeError("ISO datetime string has unexpected length.")
    returnstr = f"{returncode:+04d}"
    if len(returnstr) != 4:
        raise RuntimeError("Return code string has unexpected length.")
    return f"v1 datetime={iso} returncode={returnstr}\n"


def parse_cache_header(header: str) -> tuple[float, int] | tuple[None, None]:
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


def parse_sacct_out(sacct_out: str, jobid: int) -> str:
    """Get the job state for a specific from from the output of ``sacct -o 'jobid,state' -PXn``.

    Parameters
    ----------
    sacct_out
        A string with the output of ``sacct -o 'jobid,state' -PXn``.
    jobid
        The jobid of interest.

    Returns
    -------
    status
        The status of the job. This can be:

        - Any of the SLURM job states.
        - `unlisted` if the job cannot be found,
          which practically means it has ended long ago.
        - `invalid` if the sacct output cannot be parsed.
    """
    try:
        for line in sacct_out.splitlines():
            columns = line.strip().split("|")
            if int(columns[0]) == jobid:
                return columns[1].strip().split()[0]
    except (ValueError, IndexError):
        return "invalid"
    return "unlisted"
