# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""An sbatch wrapper to submit only on the first call, and to wait until a job has finished."""

import argparse
import fcntl
import os
import random
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime

from path import Path

from stepup.core.extapi import record_subprocess, run_subprocess

from .log import (
    InpDigestError,
    InterruptedSubmissionError,
    NoSubmissionError,
    init_log,
    log_status,
    read_jobid_cluster_status,
    read_log,
    read_status,
)
from .utils import DONE_STATES, KNOWN_JOB_STATES, parse_sbatch

__all__ = ("sbatch",)


SBATCH_RETRY_NUM = int(os.getenv("STEPUP_SBATCH_RETRY_NUM", "5"))
SBATCH_RETRY_DELAY_MIN = int(os.getenv("STEPUP_SBATCH_RETRY_DELAY_MIN", "60"))
SBATCH_RETRY_DELAY_MAX = max(
    int(os.getenv("STEPUP_SBATCH_RETRY_DELAY_MAX", "120")), SBATCH_RETRY_DELAY_MIN
)
CACHE_TIMEOUT = int(os.getenv("STEPUP_SBATCH_CACHE_TIMEOUT", "30"))
POLLING_MIN = int(os.getenv("STEPUP_SBATCH_POLLING_MIN", "10"))
POLLING_MAX = max(int(os.getenv("STEPUP_SBATCH_POLLING_MAX", "20")), POLLING_MIN)
SACCT_START = os.getenv("STEPUP_SACCT_START_TIME", "now-7days")
UNLISTED_TIMEOUT = int(os.getenv("STEPUP_SBATCH_UNLISTED_TIMEOUT", "600"))
CANCEL_TIMEOUT = int(os.getenv("STEPUP_SBATCH_CANCEL_TIMEOUT", "600"))


def submit_once_and_wait(
    job_ext: str,
    sbatch_rc: str | None = None,
    validate_inp_digest: bool = True,
):
    """Submit a job and wait for it to complete. When called a second time, just wait.

    Parameters
    ----------
    job_ext
        The file extension of the job script to be submitted.
    sbatch_rc
        A resource configuration needed before calling sbatch.
        This is executed in the same shell, right before calling sbatch.
    validate_inp_digest
        If False, the input digest is not checked.
        This is useful when the job script is modified but the changes are harmless.
    """
    inp_digest = os.getenv("STEPUP_STEP_INP_DIGEST")
    if inp_digest is None:
        raise ValueError("The environment variable STEPUP_STEP_INP_DIGEST is not set.")
    start_time = time.time()

    # Read previously logged job states
    path_log = Path("slurmjob.log")
    previous_lines = (
        read_log(path_log, inp_digest if validate_inp_digest else None)
        if path_log.is_file()
        else []
    )

    # Go through or skip states.
    submit_time, status = read_status(previous_lines)
    if status == "Submitting":
        # A previous process wrote this marker right before calling sbatch.
        # The submission it describes is only known to be complete
        # when the next line records the job ID.
        submit_time, status = read_status(previous_lines)
        if status is None:
            raise InterruptedSubmissionError(f"No job ID was recorded in {path_log.absolute()}.")
    if status is None:
        # A new job must be submitted.
        # The marker goes into the log before sbatch runs,
        # so that a process which does not survive the call leaves a trace of the attempt.
        init_log(path_log, inp_digest)
        log_status(path_log, "Submitting")
        submit_time = time.time()
        try:
            sbatch_stdout = submit_job(job_ext, sbatch_rc)
        except Exception:
            # The job script was rejected or sbatch never accepted a job,
            # so nothing can be running and the marker must not block the next attempt.
            path_log.remove_p()
            raise
        log_status(path_log, f"Submitted {sbatch_stdout}")
        rndsleep()
    else:
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

    # The grace period for an unlisted job counts from the moment this process starts waiting.
    # Measured from the original submission, a job resumed from an older log
    # would run out of grace before sacct has been consulted even once.
    wait_since = max(submit_time, start_time)
    status = "UNDEFINED"
    done = False
    first = True
    while not done:
        status, done, called = _read_or_poll_status(
            wait_since, jobid, cluster, previous_lines, path_log, status, first
        )
        if called:
            first = False

    if status == "COMPLETED":
        # Get the return code from the job
        with open("slurmjob.ret") as fh:
            returncode = fh.read().strip()
        try:
            returncode = int(returncode)
        except ValueError as exc:
            raise ValueError(
                f"Could not parse return code from slurmjob.ret. Got '{returncode}'"
            ) from exc
        if returncode != 0:
            raise RuntimeError(f"Job ended with return code {returncode}.")
    else:
        raise RuntimeError(f"Job ended with status '{status}'.")


def _read_or_poll_status(
    wait_since: float,
    jobid: int,
    cluster: str,
    previous_lines: list[str],
    path_log: str,
    last_status: str,
    first: bool,
) -> tuple[str, bool, bool]:
    """One polling iteration. Before polling, previous lines from the log are parsed.

    Parameters
    ----------
    wait_since
        The timestamp from which the grace period for an unlisted job is counted.
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
    first
        True if this is the first call to _read_or_poll_status in this process.

    Returns
    -------
    status
        The status result obtained by polling the scheduler.
    done
        True when the waiting is over.
    called
        True if the scheduler was polled, False if the status was obtained from the log.
    """
    # First try to replay previously logged states
    called = False
    _, status = read_status(previous_lines)
    if status is None:
        # All previously logged states are processed.
        # Call sacct and parse its response.
        rndsleep()
        _, status, called = get_status(jobid, cluster, first)
        # Log only if the status changed, and is not invalid or unlisted.
        # These two statuses are (potentially) transient and should not be logged.
        if status != last_status and status not in ["invalid", "unlisted"]:
            log_status(path_log, status)
    if status not in KNOWN_JOB_STATES:
        raise ValueError(f"Unknown job status '{status}' obtained from scheduler.")

    # Determine if the job is done
    done = status in DONE_STATES
    if status == "unlisted" and time.time() > wait_since + UNLISTED_TIMEOUT:
        # If the job remains unlisted for too long, we declare it failed.
        # This prevents an infinite loop if the job ID was wrong or purged.
        done = True

    return status, done, called


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

# An option starts after whitespace, so that a value such as `--exclude=node-a`
# is not mistaken for the short option it happens to end with.
RE_SBATCH_STDOUT = re.compile(r"\s*#\s*SBATCH\b.*\s(--output|-o)\b")
RE_SBATCH_STDERR = re.compile(r"\s*#\s*SBATCH\b.*\s(--error|-e)\b")
RE_SBATCH_ARRAY = re.compile(r"\s*#\s*SBATCH\b.*\s(--array|-a)\b")
RE_SBATCH = re.compile(r"\s*#\s*SBATCH\b")
UNSUPPORTED_DIRECTIVES = [
    re.compile(r"\s*#\s*PBS\b"),
    re.compile(r"\s*#\s*BSUB\b"),
    re.compile(r"\s*#\s*COBALT\b"),
    re.compile(r"\s*#\$"),
]


def submit_job(job_ext: str, sbatch_rc: str | None = None) -> str:
    """Submit a job with sbatch."""
    # Verify that the job script is executable.
    path_job = f"slurmjob{job_ext}"
    if not os.access(path_job, os.X_OK):
        raise ValueError("The job script must be executable.")

    # Copy the #SBATCH lines from the job script and perform some checks.
    with open(path_job) as f:
        sbatch_header = []
        first_line = next(f, "")
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
    shell = False
    if sbatch_rc is not None:
        command = f"{sbatch_rc} < /dev/null && {command}"
        shell = True
    stdin = JOB_SCRIPT_WRAPPER.format(sbatch_header=sbatch_header, job_script=path_job)
    returncode = None
    for attempt in range(SBATCH_RETRY_NUM):
        if attempt > 0:
            # The delay precedes the retry, so that the last failure is reported without waiting.
            delay = random.randint(SBATCH_RETRY_DELAY_MIN, SBATCH_RETRY_DELAY_MAX)
            print(
                f"sbatch failed with return code {returncode}. Retrying in {delay} seconds.",
                file=sys.stderr,
            )
            time.sleep(delay)
        cp = run_subprocess(command, stdin=stdin, check=False, shell=shell)
        if cp.returncode == 0:
            return cp.stdout.strip()
        if not (cp.stderr is None or cp.stderr == ""):
            sys.stderr.write(cp.stderr)
        returncode = cp.returncode
    raise RuntimeError(f"sbatch failed {SBATCH_RETRY_NUM} times. Giving up.")


def get_status(jobid: int, cluster: str | None, first: bool) -> tuple[float, str, bool]:
    """Load cached sacct output or run sacct if outdated.

    Parameters
    ----------
    jobid
        The job to wait for.
    cluster
        The cluster to which the job was submitted.
    first
        True if this is the first call to get_status in this process.

    Returns
    -------
    timestamp
        The time when the status was last retrieved.
    status
        A status reported by sacct,
        or `invalid` if sacct failed (retry sacct later),
        or `unlisted` if the job is not found (probably ended long ago).
    called
        True if sacct was called, False if the status was obtained from the cache.
    """
    # Load cached output or run again
    command = f"sacct -o 'jobid,state' -PXn -S {SACCT_START}"
    path_out = Path(os.getenv("ROOT", ".")) / ".stepup/queue"
    if cluster is None:
        path_out /= "sbatch_wait_sacct.out"
    else:
        command += f" --cluster={cluster}"
        path_out /= f"sbatch_wait_sacct.{cluster}.out"
    status_time, sacct_out, returncode, called = cached_run(command, path_out, CACHE_TIMEOUT, first)
    if returncode != 0:
        return status_time, "invalid", called
    return status_time, parse_sacct_out(sacct_out, jobid), called


def cached_run(
    command: str, path_out: Path, cache_timeout: float, first: bool
) -> tuple[float, str, int, bool]:
    """Execute a command if its previous output is outdated.

    Parameters
    ----------
    command
        Command to run if the cached output is outdated.
    path_out
        The path where the output is cached.
    cache_timeout
        The waiting time between two actual calls.
    first
        True if this is the first call to cached_run in this process.

    Returns
    -------
    cache_time
        The time when the command was last executed.
    stdout
        The output of the file, either new or cached.
    returncode
        The return code of the (cached) command.
    called
        True if the command was executed, False if the output was read from the cache.

    Notes
    -----
    The cached output is updated only if the command has a zero exit code.
    In all other cases, the output of the call is ignored, assuming the error is transient,
    and the output of the last successful call is kept.
    The header is refreshed in either case,
    so that a failing command is not retried by every process at every polling interval.
    """
    if not path_out.exists():
        # The parent of a relative path without directory part is an empty path,
        # which only `absolute` turns into a directory that can be created.
        path_out.absolute().parent.makedirs_p()
        path_out.touch()

    with open(path_out, mode="r+") as fh:
        fcntl.lockf(fh, fcntl.LOCK_EX)
        fh.seek(0)
        header = fh.read(CACHE_HEADER_LENGTH)
        cache_time, returncode = parse_cache_header(header)
        if cache_time is None or time.time() > cache_time + cache_timeout:
            stdout = fh.read() if cache_time is not None else ""
            cp = subprocess.run(shlex.split(command), capture_output=True, text=True, check=False)
            if first:
                # Only the first call is recorded to avoid duplicate entries in StepUp's metadata.
                # Note that the recording of subprocesses is intended to be informative,
                # not authoritative.
                record_subprocess(
                    f"{command}  # first call only", cp.returncode, workdir=os.getcwd()
                )
            if cp.returncode == 0:
                stdout = cp.stdout
            # Go the the beginning of the file before truncating.
            # (Possibly related to issue with zero bytes at start of file.)
            fh.seek(0)
            fh.truncate(0)
            cache_time = time.time()
            header = make_cache_header(cache_time, cp.returncode)
            fh.write(header)
            fh.write(stdout)
            fh.flush()
            os.fsync(fh.fileno())
            return cache_time, stdout, cp.returncode, True
        return cache_time, fh.read(), returncode, False


def make_cache_header(cache_time: float, returncode: int):
    """Prepare a header for the file containing the cached output of a cached execution."""
    # The format string is explicit because `isoformat` omits the microseconds when they are zero,
    # which would shorten the header that `parse_cache_header` slices at fixed positions.
    iso = f"{datetime.fromtimestamp(cache_time):%Y-%m-%dT%H:%M:%S.%f}"
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


RE_JOB_ID = re.compile(r"[0-9]+")


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
        - `invalid` if the state of the job cannot be read,
          or if none of the lines has the layout of a job record.

    Notes
    -----
    The output is shared by all jobs waiting on the same cluster,
    so a line that cannot be interpreted is skipped instead of invalidating the whole output.
    """
    num_lines = 0
    num_records = 0
    for line in sacct_out.splitlines():
        if line.strip() == "":
            continue
        num_lines += 1
        columns = [column.strip() for column in line.split("|")]
        if len(columns) < 2:
            continue
        num_records += 1
        # Array tasks (`123_4`) and components of heterogeneous jobs (`123+0`) are not jobs
        # submitted by StepUp Queue. They are skipped, also because `int` reads the underscore
        # in `123_4` as a digit separator and would silently return the state of job 1234.
        if RE_JOB_ID.fullmatch(columns[0]) is None:
            continue
        if int(columns[0]) == jobid:
            states = columns[1].split()
            return states[0] if len(states) > 0 else "invalid"
    if num_records == 0 and num_lines > 0:
        # This is probably not the output of the expected sacct command.
        return "invalid"
    return "unlisted"


def cancel_and_wait(job_id: int, cluster: str | None):
    """Cancel a job and wait until the scheduler stops reporting it as active.

    Parameters
    ----------
    job_id
        The job to cancel.
    cluster
        The cluster to which the job was submitted.

    Raises
    ------
    RuntimeError
        When the job is still active `CANCEL_TIMEOUT` seconds after the cancellation.

    Notes
    -----
    `scancel` returns as soon as the scheduler accepts the request,
    while the job may keep running for a while.
    Submitting a new job in the same directory before the old one has stopped
    would let two jobs write to the same output files.
    """
    command = "scancel" if cluster is None else f"scancel -M {cluster}"
    # A job that the scheduler no longer knows makes scancel fail,
    # which is not a problem here: the polling loop below decides whether the job is gone.
    run_subprocess(f"{command} {job_id}", check=False)
    deadline = time.time() + CANCEL_TIMEOUT
    while True:
        _, status, _ = get_status(job_id, cluster, False)
        if status in DONE_STATES:
            return
        if time.time() > deadline:
            raise RuntimeError(
                f"Job {job_id} is still reported as '{status}' "
                f"{CANCEL_TIMEOUT} seconds after scancel. "
                "Wait for it to stop or remove slurmjob.log to take over manually."
            )
        rndsleep()


def sbatch(argv: Sequence[str] | None = None):
    """Submit a job and wait for it to complete. When called a second time, just wait."""
    parser = argparse.ArgumentParser()
    parser.add_argument("ext", nargs="?", default=".sh")
    parser.add_argument("--rc", default=None)
    default_onchange = os.getenv("STEPUP_QUEUE_ONCHANGE", "raise")
    parser.add_argument(
        "--onchange", default=default_onchange, choices=["raise", "resubmit", "ignore"]
    )
    args = parser.parse_args(argv)

    if args.onchange == "resubmit":
        try:
            submit_once_and_wait(args.ext, args.rc)
            return
        except InpDigestError:
            pass
        # Cancel running job (if any), clean log and resubmit
        path_log = Path("slurmjob.log")
        try:
            job_id, cluster, status = read_jobid_cluster_status(path_log)
        except NoSubmissionError:
            pass
        else:
            if status not in DONE_STATES:
                cancel_and_wait(job_id, cluster)
        path_log.remove_p()
    submit_once_and_wait(args.ext, args.rc, args.onchange != "ignore")


if __name__ == "__main__":
    sys.exit(sbatch())
