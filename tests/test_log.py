# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for stepup.queue.log."""

from datetime import datetime

import pytest
from path import Path

from stepup.queue.log import (
    FIRST_LINE,
    InpDigestError,
    InterruptedSubmissionError,
    NoSubmissionError,
    check_log_inp_digest,
    check_log_version,
    init_log,
    log_status,
    read_jobid_cluster_status,
    read_log,
    read_status,
)

INP_DIGEST = "2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f"
OTHER_DIGEST = "0000000000000000000000000000000000000000000000000000000000000000"

LOG_EXAMPLE = """\
StepUp Queue sbatch wait log format version 2
2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f
2026-01-01T00:15:07.451402 Submitting
2026-01-01T00:15:08.451402 Submitted 40754228;joltik
2026-01-01T00:15:46.452136 PENDING
2026-01-01T00:47:11.543280 RUNNING
2026-01-01T01:59:03.760998 COMPLETED
"""


def write_log(path_log: Path, text: str) -> Path:
    """Write `text` to `path_log` and return the path."""
    path_log.write_text(text)
    return path_log


#
# Version and digest checks
#


def test_check_log_version():
    check_log_version(LOG_EXAMPLE.splitlines()[0])
    with pytest.raises(ValueError):
        check_log_version("StepUp Queue sbatch wait log format version 1")


def test_check_log_inp_digest():
    check_log_inp_digest(INP_DIGEST, INP_DIGEST)
    with pytest.raises(InpDigestError):
        check_log_inp_digest(INP_DIGEST, OTHER_DIGEST)


@pytest.mark.parametrize("error", [InpDigestError, InterruptedSubmissionError, NoSubmissionError])
def test_log_errors_are_value_errors(error):
    # `sbatch` catches these errors specifically, while `cancel_jobs` and `remove_jobs`
    # catch `ValueError` to skip unreadable logs. Both rely on this relation.
    assert issubclass(error, ValueError)


#
# Writing logs
#


def test_init_log_and_read_log(path_tmp: Path):
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, INP_DIGEST)
    assert path_log.read_text() == f"{FIRST_LINE}\n{INP_DIGEST}\n"
    assert read_log(path_log, INP_DIGEST) == []


def test_init_log_truncates_existing_log(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE)
    init_log(path_log, OTHER_DIGEST)
    assert path_log.read_text() == f"{FIRST_LINE}\n{OTHER_DIGEST}\n"


def test_log_status_roundtrip(path_tmp: Path):
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, INP_DIGEST)
    before = datetime.now().timestamp()
    log_status(path_log, "Submitted 40754228")
    log_status(path_log, "PENDING")
    after = datetime.now().timestamp()
    lines = read_log(path_log, INP_DIGEST)
    assert len(lines) == 2
    stamp, status = read_status(lines)
    assert status == "Submitted 40754228"
    assert before <= stamp <= after
    assert read_status(lines) == (pytest.approx(stamp, abs=1.0), "PENDING")
    assert read_status(lines) == (None, None)


#
# read_log
#


def test_read_log_empty_file(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", "")
    with pytest.raises(ValueError, match="empty"):
        read_log(path_log)


def test_read_log_without_inp_digest(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", f"{FIRST_LINE}\n")
    with pytest.raises(ValueError, match="no input digest"):
        read_log(path_log)


def test_read_log_wrong_version(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", f"other format\n{INP_DIGEST}\n")
    with pytest.raises(ValueError, match="first line of the log is wrong"):
        read_log(path_log)


def test_read_log_wrong_inp_digest(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE)
    with pytest.raises(InpDigestError):
        read_log(path_log, OTHER_DIGEST)


def test_read_log_inp_digest_not_checked(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE)
    assert len(read_log(path_log, None)) == 5
    assert len(read_log(path_log)) == 5


def test_read_log_returns_status_lines(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE)
    lines = read_log(path_log, INP_DIGEST)
    assert lines == [
        "2026-01-01T00:15:07.451402 Submitting",
        "2026-01-01T00:15:08.451402 Submitted 40754228;joltik",
        "2026-01-01T00:15:46.452136 PENDING",
        "2026-01-01T00:47:11.543280 RUNNING",
        "2026-01-01T01:59:03.760998 COMPLETED",
    ]


def test_read_log_keeps_blank_lines(path_tmp: Path):
    # A blank line is kept as an empty status line, which makes the log unreadable further on.
    # This is how a log truncated by a crashing process becomes a hard error.
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE + "\n")
    lines = read_log(path_log, INP_DIGEST)
    assert lines[-1] == ""
    with pytest.raises(ValueError, match="Expected a status in log"):
        read_status(lines[-1:])


#
# read_status
#


def test_read_status_empty():
    assert read_status([]) == (None, None)


def test_read_status_pops_first_line():
    lines = LOG_EXAMPLE.splitlines()[3:]
    assert len(lines) == 4
    assert read_status(lines)[1] == "Submitted 40754228;joltik"
    assert len(lines) == 3
    assert read_status(lines)[1] == "PENDING"
    assert len(lines) == 2


def test_read_status_timestamp():
    stamp, status = read_status(["2026-01-01T00:15:46.452136 PENDING"])
    assert stamp == datetime(2026, 1, 1, 0, 15, 46, 452136).timestamp()
    assert status == "PENDING"


def test_read_status_keeps_status_arguments():
    # sacct reports states such as `CANCELLED by 2540019`, which are logged verbatim.
    assert read_status(["2026-01-01T00:15:46.452136 CANCELLED by 2540019"])[1] == (
        "CANCELLED by 2540019"
    )


def test_read_status_without_status():
    with pytest.raises(ValueError, match="Expected a status in log"):
        read_status(["2026-01-01T00:15:46.452136"])


def test_read_status_bad_timestamp():
    with pytest.raises(ValueError):
        read_status(["not-a-timestamp PENDING"])


#
# read_jobid_cluster_status
#


def test_read_jobid_cluster_status(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE)
    assert read_jobid_cluster_status(path_log) == (40754228, "joltik", "COMPLETED")


def test_read_jobid_cluster_status_without_cluster(path_tmp: Path):
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n"
        f"2026-01-01T00:15:07.451402 Submitting\n"
        "2026-01-01T00:15:08.451402 Submitted 40754228\n"
        "2026-01-01T00:15:46.452136 RUNNING\n",
    )
    assert read_jobid_cluster_status(path_log) == (40754228, None, "RUNNING")


def test_read_jobid_cluster_status_without_marker(path_tmp: Path):
    # Logs written before the `Submitting` marker existed must still be readable.
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n"
        "2026-01-01T00:15:08.451402 Submitted 40754228;joltik\n"
        "2026-01-01T00:15:46.452136 RUNNING\n",
    )
    assert read_jobid_cluster_status(path_log) == (40754228, "joltik", "RUNNING")


def test_read_jobid_cluster_status_interrupted_submission(path_tmp: Path):
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n2026-01-01T00:15:07.451402 Submitting\n",
    )
    with pytest.raises(InterruptedSubmissionError):
        read_jobid_cluster_status(path_log)


def test_read_jobid_cluster_status_ignores_inp_digest(path_tmp: Path):
    # The digest is deliberately not validated here: the job of an outdated log
    # must still be cancellable and its directory removable.
    path_log = write_log(path_tmp / "slurmjob.log", LOG_EXAMPLE.replace(INP_DIGEST, OTHER_DIGEST))
    assert read_jobid_cluster_status(path_log)[0] == 40754228


def test_read_jobid_cluster_status_incomplete(path_tmp: Path):
    path_log = write_log(path_tmp / "slurmjob.log", f"{FIRST_LINE}\n{INP_DIGEST}\n")
    with pytest.raises(NoSubmissionError):
        read_jobid_cluster_status(path_log)


def test_read_jobid_cluster_status_not_submitted(path_tmp: Path):
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n2026-01-01T00:15:08.451402 Resumed 40754228\n",
    )
    with pytest.raises(ValueError, match="No 'Submitted' on status line"):
        read_jobid_cluster_status(path_log)


@pytest.mark.parametrize(
    "first_status_line",
    [
        "2026-01-01T00:15:08.451402 Submitted",
        "2026-01-01T00:15:08.451402 Submitted 40754228 joltik",
    ],
)
def test_read_jobid_cluster_status_wrong_word_count(path_tmp: Path, first_status_line: str):
    path_log = write_log(
        path_tmp / "slurmjob.log", f"{FIRST_LINE}\n{INP_DIGEST}\n{first_status_line}\n"
    )
    with pytest.raises(ValueError, match="Could not read job ID"):
        read_jobid_cluster_status(path_log)


def test_read_jobid_cluster_status_only_submitted(path_tmp: Path):
    # With no state logged yet, the last line is the submission itself,
    # so the status is the whole `Submitted <jobid>` string rather than a SLURM state.
    # Callers only compare it against sets of SLURM states, so it never matches a done state.
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n"
        f"2026-01-01T00:15:07.451402 Submitting\n"
        "2026-01-01T00:15:08.451402 Submitted 40754228;joltik\n",
    )
    assert read_jobid_cluster_status(path_log) == (
        40754228,
        "joltik",
        "Submitted 40754228;joltik",
    )


def test_read_jobid_cluster_status_unparsable_jobid(path_tmp: Path):
    path_log = write_log(
        path_tmp / "slurmjob.log",
        f"{FIRST_LINE}\n{INP_DIGEST}\n"
        f"2026-01-01T00:15:07.451402 Submitting\n"
        "2026-01-01T00:15:08.451402 Submitted x;y;z\n",
    )
    with pytest.raises(ValueError, match="Cannot parse sbatch output"):
        read_jobid_cluster_status(path_log)
