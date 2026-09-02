# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for stepup.queue.remove_jobs."""

import pytest
from path import Path

from stepup.queue.log import FIRST_LINE
from stepup.queue.remove_jobs import remove_jobs

INP_DIGEST = "2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f"


def setup_job(path_job: Path, status: str | None = "RUNNING", job_id: int = 40754228):
    """Create a job directory with a log file of a submitted job.

    Parameters
    ----------
    path_job
        The job directory to create.
    status
        The last state logged for the job.
        When None, the log stops right after the `Submitted` line.
    job_id
        The SLURM job ID written on the `Submitted` line.
    """
    path_job.makedirs_p()
    lines = [
        FIRST_LINE,
        INP_DIGEST,
        f"2026-01-01T00:15:08.451402 Submitted {job_id}",
    ]
    if status is not None:
        lines.append(f"2026-01-01T00:15:46.452136 {status}")
    with open(path_job / "slurmjob.log", "w") as fh:
        for line in lines:
            print(line, file=fh)


def test_dry_run(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["job1"])
    assert (path_tmp / "job1").is_dir()
    assert capsys.readouterr().out == (
        "# Note: No job directories are actually removed.\n"
        "# Use the --commit option to execute the removals.\n"
        "rm -rf job1  # state=FAILED\n"
    )


def test_commit(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", "job1"])
    assert not (path_tmp / "job1").exists()
    assert capsys.readouterr().out == "rm -rf job1  # state=FAILED\n"


@pytest.mark.parametrize("status", ["CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"])
def test_commit_failed_states(path_tmp: Path, monkeypatch, capsys, status: str):
    setup_job(path_tmp / "job1", status)
    monkeypatch.chdir(path_tmp)
    remove_jobs(["-c", "job1"])
    assert not (path_tmp / "job1").exists()
    assert capsys.readouterr().out == f"rm -rf job1  # state={status}\n"


def test_skip_not_failed(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "COMPLETED")
    setup_job(path_tmp / "job2", "RUNNING")
    setup_job(path_tmp / "job3", "PENDING")
    setup_job(path_tmp / "job4", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit"])
    assert (path_tmp / "job1").is_dir()
    assert (path_tmp / "job2").is_dir()
    assert (path_tmp / "job3").is_dir()
    assert not (path_tmp / "job4").exists()
    assert capsys.readouterr().out == "rm -rf job4  # state=FAILED\n"


def test_all(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "COMPLETED")
    setup_job(path_tmp / "job2", "RUNNING")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--all"])
    assert (path_tmp / "job1").is_dir()
    assert (path_tmp / "job2").is_dir()
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2:] == [
        "rm -rf job1  # state=COMPLETED",
        "rm -rf job2  # state=RUNNING",
    ]


def test_all_commit(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "COMPLETED")
    setup_job(path_tmp / "job2", "RUNNING")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["-a", "-c"])
    assert not (path_tmp / "job1").exists()
    assert not (path_tmp / "job2").exists()
    assert capsys.readouterr().out == (
        "rm -rf job1  # state=COMPLETED\nrm -rf job2  # state=RUNNING\n"
    )


def test_paths_default_is_current_directory(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    setup_job(path_tmp / "sub" / "job2", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit"])
    assert not (path_tmp / "job1").exists()
    assert not (path_tmp / "sub" / "job2").exists()
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2:] == [
        "rm -rf job1  # state=FAILED",
        "rm -rf sub/job2  # state=FAILED",
    ]


def test_paths_select_subset(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    setup_job(path_tmp / "job2", "FAILED")
    setup_job(path_tmp / "job3", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", "job1", "job3"])
    assert not (path_tmp / "job1").exists()
    assert (path_tmp / "job2").is_dir()
    assert not (path_tmp / "job3").exists()


def test_paths_search_recursively(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "sub" / "deeper" / "job1", "FAILED")
    setup_job(path_tmp / "sub" / "job2", "FAILED")
    setup_job(path_tmp / "other" / "job3", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", "sub"])
    assert not (path_tmp / "sub" / "deeper" / "job1").exists()
    assert not (path_tmp / "sub" / "job2").exists()
    assert (path_tmp / "other" / "job3").is_dir()


def test_paths_job_directory_itself(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", "job1/"])
    assert not (path_tmp / "job1").exists()
    assert capsys.readouterr().out == "rm -rf job1  # state=FAILED\n"


def test_paths_missing_and_not_a_directory(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    (path_tmp / "notadir.txt").write_text("")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", "job1", "nowhere", "notadir.txt"])
    out = capsys.readouterr().out
    assert "# WARNING: Path nowhere does not exist." in out
    assert "# WARNING: Path notadir.txt is not a directory." in out
    assert not (path_tmp / "job1").exists()
    assert (path_tmp / "notadir.txt").is_file()


def test_unreadable_log(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    setup_job(path_tmp / "job2", "FAILED")
    with open(path_tmp / "job2" / "slurmjob.log", "w") as fh:
        print("Some other file format", file=fh)
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit"])
    out = capsys.readouterr().out
    assert "# WARNING: Could not read job status from job2/slurmjob.log:" in out
    assert not (path_tmp / "job1").exists()
    assert (path_tmp / "job2").is_dir()


def test_unreadable_log_all(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", "FAILED")
    with open(path_tmp / "job1" / "slurmjob.log", "w") as fh:
        print("Some other file format", file=fh)
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--all", "--commit"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "rm -rf job1  # state=None"
    assert not (path_tmp / "job1").exists()


def test_no_status_yet(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp / "job1", None)
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit"])
    assert (path_tmp / "job1").is_dir()
    assert capsys.readouterr().out == ""


def test_interrupted_submission(path_tmp: Path, monkeypatch, capsys):
    # A job that may be queued under an unknown ID is not a failed job.
    setup_job(path_tmp / "job1", None)
    with open(path_tmp / "job1" / "slurmjob.log", "a") as fh:
        print("2026-01-01T00:15:07.451402 Submitting", file=fh)
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit"])
    assert (path_tmp / "job1").is_dir()
    assert capsys.readouterr().out == ""


def test_refuse_current_directory_dry_run(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs([])
    assert (path_tmp / "slurmjob.log").is_file()
    assert capsys.readouterr().out == (
        "# Note: No job directories are actually removed.\n"
        "# Use the --commit option to execute the removals.\n"
        "# WARNING: Refusing to remove the current directory.\n"
    )


def test_refuse_current_directory_commit(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--all", "--commit"])
    assert (path_tmp / "slurmjob.log").is_file()
    assert capsys.readouterr().out == "# WARNING: Refusing to remove the current directory.\n"


def test_refuse_parent_directory_dry_run(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    (path_tmp / "work").makedirs_p()
    monkeypatch.chdir(path_tmp / "work")
    remove_jobs([".."])
    assert (path_tmp / "slurmjob.log").is_file()
    assert capsys.readouterr().out == (
        "# Note: No job directories are actually removed.\n"
        "# Use the --commit option to execute the removals.\n"
        "# WARNING: Refusing to remove .., a parent of the current directory.\n"
    )


def test_refuse_parent_directory_commit(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    setup_job(path_tmp / "job1", "FAILED")
    (path_tmp / "work").makedirs_p()
    monkeypatch.chdir(path_tmp / "work")
    remove_jobs(["--commit", ".."])
    assert (path_tmp / "slurmjob.log").is_file()
    assert not (path_tmp / "job1").exists()
    assert capsys.readouterr().out == (
        "rm -rf ../job1  # state=FAILED\n"
        "# WARNING: Refusing to remove .., a parent of the current directory.\n"
    )


def test_refuse_grandparent_directory(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    (path_tmp / "sub" / "work").makedirs_p()
    monkeypatch.chdir(path_tmp / "sub" / "work")
    remove_jobs(["--commit", "../.."])
    assert (path_tmp / "slurmjob.log").is_file()
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "# WARNING: Refusing to remove ../.., a parent of the current directory."


def test_refuse_current_directory_absolute_path(path_tmp: Path, monkeypatch, capsys):
    setup_job(path_tmp, "FAILED")
    setup_job(path_tmp / "job1", "FAILED")
    monkeypatch.chdir(path_tmp)
    remove_jobs(["--commit", path_tmp.realpath()])
    assert (path_tmp / "slurmjob.log").is_file()
    assert not (path_tmp / "job1").exists()
    assert "# WARNING: Refusing to remove the current directory." in capsys.readouterr().out
