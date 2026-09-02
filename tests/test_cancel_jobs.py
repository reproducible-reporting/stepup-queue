# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for stepup.queue.cancel_jobs."""

import subprocess

import pytest
from path import Path

from stepup.queue.cancel_jobs import cancel_jobs
from stepup.queue.log import FIRST_LINE

INP_DIGEST = "2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f"


def setup_job(
    path_job: Path,
    job_id: int,
    cluster: str | None = None,
    status: str | None = "RUNNING",
):
    """Create a job directory with a log file of a submitted job.

    Parameters
    ----------
    path_job
        The job directory to create.
    job_id
        The SLURM job ID written on the `Submitted` line.
    cluster
        The cluster name written on the `Submitted` line, or None for a single-cluster setup.
    status
        The last state logged for the job.
        When None, the log stops right after the `Submitted` line.
    """
    path_job.makedirs_p()
    job_id_cluster = str(job_id) if cluster is None else f"{job_id};{cluster}"
    lines = [
        FIRST_LINE,
        INP_DIGEST,
        f"2026-01-01T00:15:08.451402 Submitted {job_id_cluster}",
    ]
    if status is not None:
        lines.append(f"2026-01-01T00:15:46.452136 {status}")
    with open(path_job / "slurmjob.log", "w") as fh:
        for line in lines:
            print(line, file=fh)


@pytest.fixture
def scancel_calls(monkeypatch) -> list[list[str]]:
    """Replace `subprocess.run` by a stub that records the commands it is given."""
    calls = []

    def fake_run(command_args, **kwargs):
        calls.append(list(command_args))
        return subprocess.CompletedProcess(command_args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_dry_run(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 40754228)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["job1"])
    assert scancel_calls == []
    assert capsys.readouterr().out == (
        "# Note: No jobs are actually cancelled.\n"
        "# Use the --commit option to execute the cancellations.\n"
        "scancel 40754228  # job1/slurmjob.log RUNNING\n"
    )


def test_dry_run_cluster(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 40754228, "joltik", "PENDING")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["job1"])
    assert scancel_calls == []
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "scancel -M joltik 40754228  # job1/slurmjob.log PENDING"


def test_commit(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 40754228)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "job1"])
    assert scancel_calls == [["scancel", "40754228"]]
    assert capsys.readouterr().out == "scancel 40754228\n"


def test_commit_cluster(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 40754228, "joltik")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["-c", "job1"])
    assert scancel_calls == [["scancel", "-M", "joltik", "40754228"]]
    assert capsys.readouterr().out == "scancel -M joltik 40754228\n"


def test_commit_one_call_per_cluster(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    setup_job(path_tmp / "job1", 1, "joltik")
    setup_job(path_tmp / "job2", 2, "joltik")
    setup_job(path_tmp / "job3", 3, "wobbuffet")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "job1", "job2", "job3"])
    assert scancel_calls == [
        ["scancel", "-M", "joltik", "1", "2"],
        ["scancel", "-M", "wobbuffet", "3"],
    ]


def test_commit_batches_of_hundred(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    for job_id in range(101):
        setup_job(path_tmp / f"job{job_id:03d}", job_id)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit"])
    assert len(scancel_calls) == 2
    assert scancel_calls[0] == ["scancel", *(str(job_id) for job_id in range(100))]
    assert scancel_calls[1] == ["scancel", "100"]


def test_skip_done(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 1, status="COMPLETED")
    setup_job(path_tmp / "job2", 2, status="FAILED")
    setup_job(path_tmp / "job3", 3, status="RUNNING")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit"])
    assert scancel_calls == [["scancel", "3"]]
    assert capsys.readouterr().out == "scancel 3\n"


def test_all(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 1, status="COMPLETED")
    setup_job(path_tmp / "job2", 2, status="RUNNING")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--all"])
    assert scancel_calls == []
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2:] == [
        "scancel 1  # job1/slurmjob.log COMPLETED",
        "scancel 2  # job2/slurmjob.log RUNNING",
    ]


def test_all_commit(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 1, status="COMPLETED")
    setup_job(path_tmp / "job2", 2, status="RUNNING")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["-a", "-c"])
    assert scancel_calls == [["scancel", "1", "2"]]


def test_paths_default_is_current_directory(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    setup_job(path_tmp / "job1", 1)
    setup_job(path_tmp / "sub" / "job2", 2)
    monkeypatch.chdir(path_tmp)
    cancel_jobs([])
    assert scancel_calls == []
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2:] == [
        "scancel 1  # job1/slurmjob.log RUNNING",
        "scancel 2  # sub/job2/slurmjob.log RUNNING",
    ]


def test_paths_select_subset(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 1)
    setup_job(path_tmp / "job2", 2)
    setup_job(path_tmp / "job3", 3)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "job1", "job3"])
    assert scancel_calls == [["scancel", "1", "3"]]


def test_paths_search_recursively(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    setup_job(path_tmp / "sub" / "deeper" / "job1", 1)
    setup_job(path_tmp / "sub" / "job2", 2)
    setup_job(path_tmp / "other" / "job3", 3)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "sub"])
    assert scancel_calls == [["scancel", "1", "2"]]


def test_paths_job_directory_itself(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    setup_job(path_tmp / "job1", 1)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "job1/"])
    assert scancel_calls == [["scancel", "1"]]


def test_paths_missing_and_not_a_directory(
    path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]
):
    setup_job(path_tmp / "job1", 1)
    (path_tmp / "notadir.txt").write_text("")
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit", "job1", "nowhere", "notadir.txt"])
    out = capsys.readouterr().out
    assert "# WARNING: Path nowhere does not exist." in out
    assert "# WARNING: Path notadir.txt is not a directory." in out
    assert scancel_calls == [["scancel", "1"]]


def test_unreadable_log(path_tmp: Path, monkeypatch, capsys, scancel_calls: list[list[str]]):
    setup_job(path_tmp / "job1", 1)
    setup_job(path_tmp / "job2", 2)
    with open(path_tmp / "job2" / "slurmjob.log", "w") as fh:
        print(FIRST_LINE, file=fh)
        print(INP_DIGEST, file=fh)
        print("2026-01-01T00:15:08.451402 PENDING", file=fh)
    monkeypatch.chdir(path_tmp)
    cancel_jobs(["--commit"])
    out = capsys.readouterr().out
    assert "# WARNING: Could not read job ID from job2/slurmjob.log:" in out
    assert scancel_calls == [["scancel", "1"]]


def test_scancel_failure(path_tmp: Path, monkeypatch, capsys):
    def fake_run(command_args, **kwargs):
        return subprocess.CompletedProcess(command_args, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    setup_job(path_tmp / "job1", 1)
    monkeypatch.chdir(path_tmp)
    with pytest.raises(SystemExit) as exc_info:
        cancel_jobs(["--commit"])
    assert exc_info.value.code == 1
    assert "Some jobs could not be cancelled." in capsys.readouterr().out
