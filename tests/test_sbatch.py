# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for the sbatch wrapper."""

import subprocess
import time
from datetime import datetime

import pytest
from path import Path

from stepup.queue import sbatch as sbatch_mod
from stepup.queue.log import (
    FIRST_LINE,
    InpDigestError,
    InterruptedSubmissionError,
    init_log,
    log_status,
    read_log,
)
from stepup.queue.sbatch import (
    CACHE_HEADER_LENGTH,
    RE_SBATCH,
    RE_SBATCH_ARRAY,
    RE_SBATCH_STDERR,
    RE_SBATCH_STDOUT,
    UNSUPPORTED_DIRECTIVES,
    _read_or_poll_status,
    cached_run,
    cancel_and_wait,
    get_status,
    make_cache_header,
    parse_cache_header,
    parse_sacct_out,
    rndsleep,
    submit_job,
    submit_once_and_wait,
)

INP_DIGEST = "2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f"
OTHER_DIGEST = "0000000000000000000000000000000000000000000000000000000000000000"


#
# Cache header
#


def test_cache_header():
    cache_time1 = time.time()
    returncode1 = -23
    header = make_cache_header(cache_time1, returncode1)
    assert isinstance(header, str)
    assert header.endswith("\n")
    cache_time2, returncode2 = parse_cache_header(header)
    assert cache_time1 == pytest.approx(cache_time2, abs=1e-4)
    assert returncode1 == returncode2
    assert parse_cache_header("") == (None, None)
    with pytest.raises(ValueError):
        parse_cache_header("foobar")


def test_cache_header_length():
    assert len(make_cache_header(time.time(), 0)) == CACHE_HEADER_LENGTH


def test_cache_header_whole_second():
    # `time.time()` lands on a whole second about once in a million calls,
    # and then `make_cache_header` raises instead of writing the cache.
    # The same expression is evaluated at import time for `CACHE_HEADER_LENGTH`,
    # so this can also break the import of the module.
    cache_time = datetime(2026, 1, 1, 12, 0, 0).timestamp()
    header = make_cache_header(cache_time, 0)
    assert parse_cache_header(header) == (cache_time, 0)


def test_cache_header_wide_return_code():
    # The header has a fixed width, so it cannot hold a return code of more than three digits.
    # Process exit codes never get that large, which makes this a purely defensive check.
    with pytest.raises(RuntimeError, match="Return code string"):
        make_cache_header(time.time(), 10000)


def test_parse_cache_header_zeros():
    assert parse_cache_header("\x00" * CACHE_HEADER_LENGTH) == (None, None)


def test_parse_cache_header_wrong_version():
    header = "v2" + make_cache_header(time.time(), 0)[2:]
    with pytest.raises(ValueError, match="Invalid header"):
        parse_cache_header(header)


def test_parse_cache_header_wrong_length():
    with pytest.raises(ValueError, match="Cannot parse cache header"):
        parse_cache_header("v1 datetime=2026-01-01")


#
# cached_run
#


def test_cached_run(path_tmp: Path):
    path_out = path_tmp / "date.txt"
    cache_time1, out1, ret1, called1 = cached_run("date", path_out, 1, False)
    cache_time2, out2, ret2, called2 = cached_run("date", path_out, 10, False)
    assert cache_time1 == pytest.approx(cache_time2, 1e-4)
    assert out1 != ""
    assert out1 == out2
    assert ret1 == ret2
    assert called1 is True
    assert called2 is False
    time.sleep(2)
    cache_time3, out3, ret3, called3 = cached_run("date", path_out, 1, False)
    assert abs(cache_time1 - cache_time3) > 0.5
    assert out1 != out3
    assert ret1 == ret3
    assert called3 is True


def test_cached_run_creates_parent_directory(path_tmp: Path):
    path_out = path_tmp / "deeper" / "nested" / "out.txt"
    cached_run("echo hello", path_out, 10, False)
    assert path_out.is_file()
    text = path_out.read_text()
    assert text.startswith("v1 datetime=")
    assert text.endswith("hello\n")


def test_cached_run_bare_filename(path_tmp: Path, monkeypatch):
    monkeypatch.chdir(path_tmp)
    assert cached_run("echo hello", Path("out.txt"), 10, False)[1] == "hello\n"


def test_cached_run_reuses_zeroed_cache(path_tmp: Path):
    # A cache file of NUL bytes is treated as absent instead of as a corrupt header.
    path_out = path_tmp / "out.txt"
    path_out.write_text("\x00" * CACHE_HEADER_LENGTH)
    _, out, returncode, called = cached_run("echo hello", path_out, 10, False)
    assert out == "hello\n"
    assert returncode == 0
    assert called is True


def test_cached_run_failing_command(path_tmp: Path):
    path_out = path_tmp / "out.txt"
    _, out, returncode, called = cached_run("false", path_out, 10, False)
    assert out == ""
    assert returncode == 1
    assert called is True
    # The failure is cached, so a concurrent process sees it until the cache expires.
    assert cached_run("echo hello", path_out, 10, False) == (
        pytest.approx(_, abs=1e-4),
        "",
        1,
        False,
    )


def test_cached_run_keeps_cache_on_failure(path_tmp: Path):
    # One transient sacct failure currently discards the good output for every waiting job.
    path_out = path_tmp / "out.txt"
    cached_run("echo hello", path_out, 0, False)
    assert cached_run("false", path_out, 0, False)[1] == "hello\n"


def test_cached_run_records_only_the_first_call(path_tmp: Path, monkeypatch):
    records = []
    monkeypatch.setattr(
        sbatch_mod,
        "record_subprocess",
        lambda cmd, returncode, **kwargs: records.append((cmd, returncode)),
    )
    path_out = path_tmp / "out.txt"
    cached_run("echo hello", path_out, 0, True)
    cached_run("echo hello", path_out, 0, False)
    assert records == [("echo hello  # first call only", 0)]


#
# get_status
#


def test_get_status_without_cluster(path_tmp: Path, monkeypatch):
    calls = []

    def fake_cached_run(command, path_out, cache_timeout, first):
        calls.append((command, path_out, cache_timeout, first))
        return 100.0, "40754228|COMPLETED\n", 0, True

    monkeypatch.setattr(sbatch_mod, "cached_run", fake_cached_run)
    monkeypatch.setenv("ROOT", path_tmp)
    assert get_status(40754228, None, True) == (100.0, "COMPLETED", True)
    command, path_out, cache_timeout, first = calls[0]
    assert command == f"sacct -o 'jobid,state' -PXn -S {sbatch_mod.SACCT_START}"
    assert path_out == path_tmp / ".stepup/queue/sbatch_wait_sacct.out"
    assert cache_timeout == sbatch_mod.CACHE_TIMEOUT
    assert first is True


def test_get_status_with_cluster(path_tmp: Path, monkeypatch):
    calls = []

    def fake_cached_run(command, path_out, cache_timeout, first):
        calls.append((command, path_out))
        return 100.0, "40754228|RUNNING\n", 0, False

    monkeypatch.setattr(sbatch_mod, "cached_run", fake_cached_run)
    monkeypatch.setenv("ROOT", path_tmp)
    assert get_status(40754228, "joltik", False) == (100.0, "RUNNING", False)
    command, path_out = calls[0]
    assert command.endswith(" --cluster=joltik")
    assert path_out == path_tmp / ".stepup/queue/sbatch_wait_sacct.joltik.out"


def test_get_status_command_failed(path_tmp: Path, monkeypatch):
    monkeypatch.setattr(
        sbatch_mod, "cached_run", lambda *args: (100.0, "40754228|COMPLETED\n", 1, True)
    )
    monkeypatch.setenv("ROOT", path_tmp)
    # A failing sacct is transient: the job status is unknown, not lost.
    assert get_status(40754228, None, True) == (100.0, "invalid", True)


#
# parse_sacct_out
#


sacct_out = """\
246748|CANCELLED by 2540019
246912|RUNNING
246913|COMPLETED
246914|FAILED
246916|COMPLETED
246917|COMPLETED
246918|COMPLETED
007|SHAKEN
"""


def test_parse_sacct_out():
    assert parse_sacct_out(sacct_out, 246748) == "CANCELLED"
    assert parse_sacct_out(sacct_out, 246912) == "RUNNING"
    assert parse_sacct_out(sacct_out, 246913) == "COMPLETED"
    assert parse_sacct_out(sacct_out, 246914) == "FAILED"
    assert parse_sacct_out(sacct_out, 246916) == "COMPLETED"
    assert parse_sacct_out(sacct_out, 246917) == "COMPLETED"
    assert parse_sacct_out(sacct_out, 246918) == "COMPLETED"
    assert parse_sacct_out(sacct_out, 7) == "SHAKEN"
    assert parse_sacct_out(sacct_out, 999999) == "unlisted"
    assert parse_sacct_out("blibli", 123456) == "invalid"


def test_parse_sacct_out_empty():
    assert parse_sacct_out("", 246912) == "unlisted"


def test_parse_sacct_out_heterogeneous_job():
    # sacct reports the components of a heterogeneous job as `<jobid>+<offset>`.
    # The output is shared by all waiting jobs, so one such line from an unrelated job
    # turns every later job into `invalid`, a status with no timeout to escape from.
    out = "246911+0|RUNNING\n246912|COMPLETED\n"
    assert parse_sacct_out(out, 246912) == "COMPLETED"


def test_parse_sacct_out_blank_line():
    assert parse_sacct_out("246911|RUNNING\n\n246912|COMPLETED\n", 246912) == "COMPLETED"


def test_parse_sacct_out_array_task():
    # sacct reports array tasks as `<jobid>_<task>`. Such a line does not fail to parse:
    # it silently becomes a different job ID, which may collide with a real one.
    out = "246913_1|PENDING\n"
    assert parse_sacct_out(out, 2469131) == "unlisted"


def test_parse_sacct_out_state_with_arguments():
    assert parse_sacct_out("246748|CANCELLED by 2540019\n", 246748) == "CANCELLED"


#
# Job script directive regexes
#


@pytest.mark.parametrize(
    "line",
    [
        "#SBATCH --output=out.txt",
        "# SBATCH --output out.txt",
        " #SBATCH -o out.txt",
    ],
)
def test_regexes_stdout(line):
    assert RE_SBATCH_STDOUT.match(line)
    assert not any(re.match(line) for re in UNSUPPORTED_DIRECTIVES)


@pytest.mark.parametrize(
    "line",
    [
        "#SBATCH --error=err.txt",
        "# SBATCH --error err.txt",
        " #SBATCH -e err.txt",
    ],
)
def test_regexes_stderr(line):
    assert RE_SBATCH_STDERR.match(line)
    assert not any(re.match(line) for re in UNSUPPORTED_DIRECTIVES)


def test_regexes_stderr_not():
    assert not RE_SBATCH_STDERR.match("#SBATCH --export=NONE")


@pytest.mark.parametrize(
    "line",
    [
        "#SBATCH --array=1-10",
        "# SBATCH --array 1-10",
        " #SBATCH -a 1-10",
    ],
)
def test_regexes_array(line):
    assert RE_SBATCH_ARRAY.match(line)
    assert not any(re.match(line) for re in UNSUPPORTED_DIRECTIVES)


def test_regexes_array_not():
    assert not RE_SBATCH_ARRAY.match("#SBATCH --account=special")


@pytest.mark.parametrize(
    ("pattern", "line"),
    [
        (RE_SBATCH_ARRAY, "#SBATCH --exclude=node-a,node-b"),
        (RE_SBATCH_STDOUT, "#SBATCH --partition=gpu-o"),
        (RE_SBATCH_STDERR, "#SBATCH --job-name=stage-e"),
    ],
)
def test_regexes_short_option_in_value(pattern, line):
    assert not pattern.match(line)


@pytest.mark.parametrize(
    "line",
    [
        "#SBATCH --time=1:00:00",
        "# SBATCH --time 1:00:00",
        " #SBATCH -t 1:00:00",
    ],
)
def test_regexes_sbatch(line):
    assert RE_SBATCH.match(line)
    assert not any(re.match(line) for re in UNSUPPORTED_DIRECTIVES)


@pytest.mark.parametrize(
    "line",
    [
        "#PBS -l walltime=1:00:00",
        " #PBS -l walltime=1:00:00",
        "# PBS -l walltime=1:00:00",
        "#BSUB -W 1:00",
        "# BSUB -W 1:00",
        " #BSUB -W 1:00",
        "#$ -l h_rt=1:00:00",
        "#COBALT -t 1:00:00",
        " #COBALT -t 1:00:00",
        "# COBALT -t 1:00:00",
    ],
)
def test_regexes_unsupported(line):
    assert any(re.match(line) for re in UNSUPPORTED_DIRECTIVES)


#
# submit_job
#


JOB_SCRIPT = """\
#!/usr/bin/env bash
#SBATCH --time=1:00:00
#SBATCH --nodes=1

echo "Hello"
"""


def write_job_script(path_tmp: Path, body: str = JOB_SCRIPT, executable: bool = True) -> Path:
    """Write a job script in `path_tmp` and make it executable unless told otherwise."""
    path_job = path_tmp / "slurmjob.sh"
    path_job.write_text(body)
    path_job.chmod(0o755 if executable else 0o644)
    return path_job


@pytest.fixture
def fake_sbatch(monkeypatch) -> list[dict]:
    """Replace `run_subprocess` by a stub that reports a successful submission."""
    calls = []

    def fake_run_subprocess(command, *, stdin=None, check=True, shell=False, **kwargs):
        calls.append({"command": command, "stdin": stdin, "shell": shell})
        return subprocess.CompletedProcess(command, 0, stdout="40754228;joltik\n", stderr="")

    monkeypatch.setattr(sbatch_mod, "run_subprocess", fake_run_subprocess)
    return calls


def test_submit_job_not_executable(path_tmp: Path, monkeypatch):
    write_job_script(path_tmp, executable=False)
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match="must be executable"):
        submit_job(".sh")


def test_submit_job_no_shebang(path_tmp: Path, monkeypatch):
    write_job_script(path_tmp, "echo hello\n")
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match="shebang"):
        submit_job(".sh")


def test_submit_job_empty_script(path_tmp: Path, monkeypatch):
    write_job_script(path_tmp, "")
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match="shebang"):
        submit_job(".sh")


@pytest.mark.parametrize(
    ("directive", "message"),
    [
        ("#SBATCH --output=out.txt", "--output/-o"),
        ("#SBATCH -e err.txt", "--error/-e"),
        ("#SBATCH --array=1-10", "array jobs"),
        ("#PBS -l walltime=1:00:00", "unsupported scheduler directive"),
        ("#BSUB -W 1:00", "unsupported scheduler directive"),
        ("#COBALT -t 1:00:00", "unsupported scheduler directive"),
        ("#$ -l h_rt=1:00:00", "unsupported scheduler directive"),
    ],
)
def test_submit_job_rejected_directives(path_tmp: Path, monkeypatch, directive: str, message: str):
    write_job_script(path_tmp, f"#!/usr/bin/env bash\n{directive}\n\necho hello\n")
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match=message):
        submit_job(".sh")


def test_submit_job(path_tmp: Path, monkeypatch, fake_sbatch: list[dict]):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    assert submit_job(".sh") == "40754228;joltik"
    assert len(fake_sbatch) == 1
    assert fake_sbatch[0]["command"] == "sbatch --parsable -o slurmjob.out -e slurmjob.err"
    assert fake_sbatch[0]["shell"] is False
    assert fake_sbatch[0]["stdin"] == (
        "#!/usr/bin/env bash\n"
        "#SBATCH --time=1:00:00\n"
        "#SBATCH --nodes=1\n"
        "\n"
        "touch slurmjob.ret\n"
        "./'slurmjob.sh'\n"
        "RETURN_CODE=$?\n"
        "echo $RETURN_CODE > slurmjob.ret\n"
        "exit $RETURN_CODE\n"
    )


def test_submit_job_other_extension(path_tmp: Path, monkeypatch, fake_sbatch: list[dict]):
    path_job = path_tmp / "slurmjob.py"
    path_job.write_text("#!/usr/bin/env python\nprint('hello')\n")
    path_job.chmod(0o755)
    monkeypatch.chdir(path_tmp)
    submit_job(".py")
    assert "./'slurmjob.py'" in fake_sbatch[0]["stdin"]


def test_submit_job_rc(path_tmp: Path, monkeypatch, fake_sbatch: list[dict]):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    submit_job(".sh", "module swap cluster/joltik")
    assert fake_sbatch[0]["command"] == (
        "module swap cluster/joltik < /dev/null && sbatch --parsable "
        "-o slurmjob.out -e slurmjob.err"
    )
    assert fake_sbatch[0]["shell"] is True


@pytest.fixture
def fake_sleep(monkeypatch) -> list[float]:
    """Replace `time.sleep` by a stub that records the requested delays."""
    delays = []
    monkeypatch.setattr(time, "sleep", delays.append)
    return delays


def test_submit_job_retry(path_tmp: Path, monkeypatch, capsys, fake_sleep: list[float]):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    attempts = []

    def fake_run_subprocess(command, *, stdin=None, check=True, shell=False, **kwargs):
        attempts.append(command)
        if len(attempts) < 3:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="sbatch: busy\n")
        return subprocess.CompletedProcess(command, 0, stdout="40754228\n", stderr="")

    monkeypatch.setattr(sbatch_mod, "run_subprocess", fake_run_subprocess)
    assert submit_job(".sh") == "40754228"
    assert len(attempts) == 3
    assert len(fake_sleep) == 2
    assert all(
        sbatch_mod.SBATCH_RETRY_DELAY_MIN <= delay <= sbatch_mod.SBATCH_RETRY_DELAY_MAX
        for delay in fake_sleep
    )
    captured = capsys.readouterr()
    assert captured.err.count("sbatch: busy") == 2
    assert captured.err.count("Retrying in") == 2


def test_submit_job_gives_up(path_tmp: Path, monkeypatch, capsys, fake_sleep: list[float]):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    monkeypatch.setattr(sbatch_mod, "SBATCH_RETRY_NUM", 3)
    monkeypatch.setattr(
        sbatch_mod,
        "run_subprocess",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr=None),
    )
    with pytest.raises(RuntimeError, match="sbatch failed 3 times"):
        submit_job(".sh")


def test_submit_job_no_sleep_after_last_attempt(
    path_tmp: Path, monkeypatch, capsys, fake_sleep: list[float]
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    monkeypatch.setattr(sbatch_mod, "SBATCH_RETRY_NUM", 3)
    monkeypatch.setattr(
        sbatch_mod,
        "run_subprocess",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr=""),
    )
    with pytest.raises(RuntimeError):
        submit_job(".sh")
    assert len(fake_sleep) == 2


def test_retry_delay_range_is_clipped():
    # Without the clipping, setting only STEPUP_SBATCH_RETRY_DELAY_MIN above the default maximum
    # would make random.randint raise in the middle of the retry loop.
    assert sbatch_mod.SBATCH_RETRY_DELAY_MAX >= sbatch_mod.SBATCH_RETRY_DELAY_MIN


#
# rndsleep
#


def test_rndsleep(monkeypatch, fake_sleep: list[float]):
    rndsleep()
    assert len(fake_sleep) == 1
    assert sbatch_mod.POLLING_MIN <= fake_sleep[0] <= sbatch_mod.POLLING_MAX


def test_polling_range_is_clipped():
    assert sbatch_mod.POLLING_MAX >= sbatch_mod.POLLING_MIN


#
# _read_or_poll_status
#


def setup_log(path_tmp: Path, *statuses: str, digest: str = INP_DIGEST, marker: bool = True):
    """Write a log file for a submitted job, followed by the given statuses.

    Parameters
    ----------
    path_tmp
        The job directory.
    statuses
        The states to log after the submission.
    digest
        The input digest to write in the log.
    marker
        Whether to write the `Submitting` marker before the submission.
        Logs written by older versions do not have it.
    """
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, digest)
    if marker:
        log_status(path_log, "Submitting")
    log_status(path_log, "Submitted 40754228;joltik")
    for status in statuses:
        log_status(path_log, status)
    return path_log


@pytest.fixture
def path_log(path_tmp: Path) -> Path:
    """An initialized log file with a submission line."""
    return setup_log(path_tmp)


def test_read_or_poll_status_replays_log(path_log: Path, monkeypatch):
    def no_polling(*args):
        raise AssertionError("The scheduler must not be polled while replaying the log.")

    monkeypatch.setattr(sbatch_mod, "get_status", no_polling)
    monkeypatch.setattr(sbatch_mod, "rndsleep", no_polling)
    previous_lines = ["2026-01-01T00:15:46.452136 RUNNING"]
    assert _read_or_poll_status(
        time.time(), 40754228, "joltik", previous_lines, path_log, "UNDEFINED", True
    ) == ("RUNNING", False, False)
    assert previous_lines == []
    # Replayed states are not logged again: only the submission lines are in the log.
    assert len(read_log(path_log, INP_DIGEST)) == 2


def test_read_or_poll_status_logs_new_status(path_log: Path, monkeypatch):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), "RUNNING", True))
    assert _read_or_poll_status(time.time(), 40754228, "joltik", [], path_log, "PENDING", True) == (
        "RUNNING",
        False,
        True,
    )
    assert read_log(path_log, INP_DIGEST)[-1].endswith(" RUNNING")


def test_read_or_poll_status_skips_unchanged_status(path_log: Path, monkeypatch):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), "RUNNING", True))
    _read_or_poll_status(time.time(), 40754228, "joltik", [], path_log, "RUNNING", False)
    assert len(read_log(path_log, INP_DIGEST)) == 2


@pytest.mark.parametrize("status", ["invalid", "unlisted"])
def test_read_or_poll_status_never_logs_transient_status(path_log: Path, monkeypatch, status: str):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), status, True))
    assert _read_or_poll_status(
        time.time(), 40754228, "joltik", [], path_log, "RUNNING", False
    ) == (status, False, True)
    assert len(read_log(path_log, INP_DIGEST)) == 2


def test_read_or_poll_status_done(path_log: Path, monkeypatch):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), "COMPLETED", True))
    assert _read_or_poll_status(
        time.time(), 40754228, "joltik", [], path_log, "RUNNING", False
    ) == ("COMPLETED", True, True)


def test_read_or_poll_status_unknown_status(path_log: Path, monkeypatch):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), "SHAKEN", True))
    with pytest.raises(ValueError, match="Unknown job status 'SHAKEN'"):
        _read_or_poll_status(time.time(), 40754228, "joltik", [], path_log, "RUNNING", False)


def test_read_or_poll_status_unlisted_timeout(path_log: Path, monkeypatch):
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)
    monkeypatch.setattr(sbatch_mod, "get_status", lambda *args: (time.time(), "unlisted", True))
    args = (40754228, "joltik", [], path_log, "RUNNING", False)
    assert _read_or_poll_status(time.time(), *args)[1] is False
    old = time.time() - sbatch_mod.UNLISTED_TIMEOUT - 1
    assert _read_or_poll_status(old, *args)[1] is True


#
# submit_once_and_wait
#


@pytest.fixture
def inp_digest(monkeypatch):
    """Provide the input digest that StepUp passes to the step through the environment."""
    monkeypatch.setenv("STEPUP_STEP_INP_DIGEST", INP_DIGEST)


def fake_poller(statuses: list[str]):
    """Build a `get_status` stub that walks through `statuses`, repeating the last one."""

    def get_status(jobid, cluster, first):
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        return time.time(), status, True

    return get_status


@pytest.fixture
def no_polling_delay(monkeypatch):
    """Remove the randomized sleep between two polls."""
    monkeypatch.setattr(sbatch_mod, "rndsleep", lambda: None)


def test_submit_once_and_wait_no_inp_digest(path_tmp: Path, monkeypatch):
    monkeypatch.delenv("STEPUP_STEP_INP_DIGEST", raising=False)
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match="STEPUP_STEP_INP_DIGEST is not set"):
        submit_once_and_wait(".sh")


def test_submit_once_and_wait_new_job(
    path_tmp: Path, monkeypatch, inp_digest, no_polling_delay, fake_sbatch: list[dict]
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["PENDING", "RUNNING", "COMPLETED"]))
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert len(fake_sbatch) == 1
    lines = read_log(path_tmp / "slurmjob.log", INP_DIGEST)
    assert [line.split(maxsplit=1)[1] for line in lines] == [
        "Submitting",
        "Submitted 40754228;joltik",
        "PENDING",
        "RUNNING",
        "COMPLETED",
    ]


def test_submit_once_and_wait_resumes(
    path_tmp: Path, monkeypatch, inp_digest, no_polling_delay, fake_sbatch: list[dict]
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    path_log = setup_log(path_tmp, "RUNNING")
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["COMPLETED"]))
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert fake_sbatch == []
    assert read_log(path_log, INP_DIGEST)[-1].endswith(" COMPLETED")


def test_submit_once_and_wait_replays_completed_log(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    # A job that is done in the log needs neither a submission, nor a poll, nor a sleep.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    path_log = setup_log(path_tmp, "COMPLETED")
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert fake_sbatch == []
    assert len(read_log(path_log, INP_DIGEST)) == 3


def test_submit_once_and_wait_inp_digest_mismatch(path_tmp: Path, monkeypatch, inp_digest):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, digest=OTHER_DIGEST)
    with pytest.raises(InpDigestError):
        submit_once_and_wait(".sh")


def test_submit_once_and_wait_inp_digest_ignored(path_tmp: Path, monkeypatch, inp_digest):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, "COMPLETED", digest=OTHER_DIGEST)
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh", validate_inp_digest=False)


def test_submit_once_and_wait_marker_precedes_sbatch(
    path_tmp: Path, monkeypatch, inp_digest, no_polling_delay
):
    # The whole point of the marker is that it reaches the disk before sbatch can create a job.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)

    def fake_run_subprocess(command, **kwargs):
        assert read_log(path_tmp / "slurmjob.log", INP_DIGEST)[-1].endswith("Submitting")
        return subprocess.CompletedProcess(command, 0, stdout="40754228;joltik\n", stderr="")

    monkeypatch.setattr(sbatch_mod, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["COMPLETED"]))
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")


def test_submit_once_and_wait_interrupted_submission(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    # The scheduler may hold a job whose ID was never recorded,
    # so submitting a second one in the same directory is not an option.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, INP_DIGEST)
    log_status(path_log, "Submitting")
    with pytest.raises(InterruptedSubmissionError):
        submit_once_and_wait(".sh")
    assert fake_sbatch == []
    assert path_log.is_file()


def test_submit_once_and_wait_removes_log_of_rejected_script(
    path_tmp: Path, monkeypatch, inp_digest
):
    # A job script that sbatch never saw leaves no job behind,
    # so its marker must not block the next attempt.
    write_job_script(path_tmp, "echo hello\n")
    monkeypatch.chdir(path_tmp)
    with pytest.raises(ValueError, match="shebang"):
        submit_once_and_wait(".sh")
    assert not (path_tmp / "slurmjob.log").exists()


def test_submit_once_and_wait_resumes_log_without_marker(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    # Logs written before the marker existed must still be resumable.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, "COMPLETED", marker=False)
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert fake_sbatch == []


def test_submit_once_and_wait_unlisted_grace_after_resume(
    path_tmp: Path, monkeypatch, inp_digest, no_polling_delay, fake_sbatch: list[dict]
):
    # The grace period of a job resumed from an old log starts now, not at its submission,
    # so a scheduler that has not caught up yet does not fail the step on the first poll.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    (path_tmp / "slurmjob.log").write_text(
        f"{FIRST_LINE}\n{INP_DIGEST}\n"
        f"2026-01-01T00:15:08.451402 Submitting\n"
        "2026-01-01T00:15:09.451402 Submitted 40754228;joltik\n"
    )
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["unlisted", "COMPLETED"]))
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert fake_sbatch == []


def test_submit_once_and_wait_log_without_submission(
    path_tmp: Path, monkeypatch, inp_digest, no_polling_delay, fake_sbatch: list[dict]
):
    # A log that was initialized but never got a submission line is treated as a fresh start.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    init_log(path_tmp / "slurmjob.log", INP_DIGEST)
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["COMPLETED"]))
    (path_tmp / "slurmjob.ret").write_text("0\n")
    submit_once_and_wait(".sh")
    assert len(fake_sbatch) == 1


def test_submit_once_and_wait_bad_first_status(path_tmp: Path, monkeypatch, inp_digest):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, INP_DIGEST)
    log_status(path_log, "RUNNING")
    with pytest.raises(ValueError, match="Expected 'Submitted' in log"):
        submit_once_and_wait(".sh")


@pytest.mark.parametrize("status", ["FAILED", "TIMEOUT", "CANCELLED", "OUT_OF_MEMORY"])
def test_submit_once_and_wait_failed_job(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict], status: str
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    path_log = setup_log(path_tmp)
    log_status(path_log, status)
    with pytest.raises(RuntimeError, match=f"Job ended with status '{status}'"):
        submit_once_and_wait(".sh")


def test_submit_once_and_wait_nonzero_return_code(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, "COMPLETED")
    (path_tmp / "slurmjob.ret").write_text("3\n")
    with pytest.raises(RuntimeError, match="return code 3"):
        submit_once_and_wait(".sh")


def test_submit_once_and_wait_unparsable_return_code(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, "COMPLETED")
    (path_tmp / "slurmjob.ret").write_text("")
    with pytest.raises(ValueError, match="Could not parse return code"):
        submit_once_and_wait(".sh")


def test_submit_once_and_wait_missing_return_code_file(
    path_tmp: Path, monkeypatch, inp_digest, fake_sbatch: list[dict]
):
    # A completed job whose wrapper never wrote slurmjob.ret is reported as a missing file
    # rather than as a job failure.
    write_job_script(path_tmp)
    monkeypatch.chdir(path_tmp)
    setup_log(path_tmp, "COMPLETED")
    with pytest.raises(FileNotFoundError):
        submit_once_and_wait(".sh")


#
# The sq-sbatch-and-wait entry point
#


@pytest.fixture
def fake_submit(monkeypatch) -> list[tuple]:
    """Replace `submit_once_and_wait` by a stub that records its arguments."""
    calls = []
    monkeypatch.setattr(
        sbatch_mod,
        "submit_once_and_wait",
        lambda *args: calls.append(args),
    )
    return calls


def test_sbatch_defaults(fake_submit: list[tuple], monkeypatch):
    monkeypatch.delenv("STEPUP_QUEUE_ONCHANGE", raising=False)
    sbatch_mod.sbatch([])
    assert fake_submit == [(".sh", None, True)]


def test_sbatch_arguments(fake_submit: list[tuple], monkeypatch):
    monkeypatch.delenv("STEPUP_QUEUE_ONCHANGE", raising=False)
    sbatch_mod.sbatch([".py", "--rc=module swap cluster/joltik"])
    assert fake_submit == [(".py", "module swap cluster/joltik", True)]


def test_sbatch_onchange_ignore(fake_submit: list[tuple]):
    sbatch_mod.sbatch(["--onchange=ignore"])
    assert fake_submit == [(".sh", None, False)]


def test_sbatch_onchange_from_env(fake_submit: list[tuple], monkeypatch):
    monkeypatch.setenv("STEPUP_QUEUE_ONCHANGE", "ignore")
    sbatch_mod.sbatch([])
    assert fake_submit == [(".sh", None, False)]


def test_sbatch_onchange_invalid(monkeypatch):
    monkeypatch.delenv("STEPUP_QUEUE_ONCHANGE", raising=False)
    with pytest.raises(SystemExit):
        sbatch_mod.sbatch(["--onchange=whatever"])


def test_sbatch_resubmit_without_change(fake_submit: list[tuple]):
    sbatch_mod.sbatch(["--onchange=resubmit"])
    assert fake_submit == [(".sh", None)]


@pytest.fixture
def fake_scancel(monkeypatch) -> list[str]:
    """Replace `run_subprocess` by a stub that records the commands it is given."""
    commands = []

    def fake_run_subprocess(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(sbatch_mod, "run_subprocess", fake_run_subprocess)
    return commands


@pytest.fixture
def fake_resubmit(monkeypatch) -> list[tuple]:
    """Make the first call to `submit_once_and_wait` fail on the input digest."""
    calls = []

    def fake_submit_once_and_wait(*args):
        calls.append(args)
        if len(calls) == 1:
            raise InpDigestError("The input digest changed.")

    monkeypatch.setattr(sbatch_mod, "submit_once_and_wait", fake_submit_once_and_wait)
    return calls


@pytest.mark.parametrize(
    ("cluster", "command"),
    [(None, "scancel 40754228"), ("joltik", "scancel -M joltik 40754228")],
)
def test_sbatch_resubmit(
    path_tmp: Path,
    monkeypatch,
    fake_scancel: list[str],
    fake_resubmit: list[tuple],
    no_polling_delay,
    cluster: str | None,
    command: str,
):
    monkeypatch.chdir(path_tmp)
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, OTHER_DIGEST)
    job_id_cluster = "40754228" if cluster is None else f"40754228;{cluster}"
    log_status(path_log, "Submitting")
    log_status(path_log, f"Submitted {job_id_cluster}")
    log_status(path_log, "RUNNING")
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["RUNNING", "CANCELLED"]))
    sbatch_mod.sbatch(["--onchange=resubmit"])
    assert fake_scancel == [command]
    assert not path_log.exists()
    assert fake_resubmit == [(".sh", None), (".sh", None, True)]


def test_sbatch_resubmit_finished_job(
    path_tmp: Path, monkeypatch, fake_scancel: list[str], fake_resubmit: list[tuple]
):
    # There is nothing to cancel when the log says the job has ended.
    monkeypatch.chdir(path_tmp)
    path_log = setup_log(path_tmp, "COMPLETED", digest=OTHER_DIGEST)
    sbatch_mod.sbatch(["--onchange=resubmit"])
    assert fake_scancel == []
    assert not path_log.exists()
    assert len(fake_resubmit) == 2


def test_sbatch_resubmit_interrupted_submission(
    path_tmp: Path, monkeypatch, fake_scancel: list[str], fake_resubmit: list[tuple]
):
    # The job ID of an interrupted submission is unknown,
    # so the log must not be removed as if there were nothing to cancel.
    monkeypatch.chdir(path_tmp)
    path_log = path_tmp / "slurmjob.log"
    init_log(path_log, OTHER_DIGEST)
    log_status(path_log, "Submitting")
    with pytest.raises(InterruptedSubmissionError):
        sbatch_mod.sbatch(["--onchange=resubmit"])
    assert fake_scancel == []
    assert path_log.is_file()


def test_sbatch_resubmit_log_without_submission(
    path_tmp: Path, monkeypatch, fake_scancel: list[str], fake_resubmit: list[tuple]
):
    monkeypatch.chdir(path_tmp)
    path_log = path_tmp / "slurmjob.log"
    path_log.write_text(f"{FIRST_LINE}\n{OTHER_DIGEST}\n")
    sbatch_mod.sbatch(["--onchange=resubmit"])
    assert fake_scancel == []
    assert not path_log.exists()
    assert len(fake_resubmit) == 2


#
# cancel_and_wait
#


def test_cancel_and_wait(monkeypatch, fake_scancel: list[str], no_polling_delay):
    monkeypatch.setattr(
        sbatch_mod, "get_status", fake_poller(["RUNNING", "COMPLETING", "CANCELLED"])
    )
    cancel_and_wait(40754228, None)
    assert fake_scancel == ["scancel 40754228"]


def test_cancel_and_wait_cluster(monkeypatch, fake_scancel: list[str], no_polling_delay):
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["CANCELLED"]))
    cancel_and_wait(40754228, "joltik")
    assert fake_scancel == ["scancel -M joltik 40754228"]


def test_cancel_and_wait_ignores_scancel_failure(monkeypatch, no_polling_delay):
    # scancel fails when the scheduler no longer knows the job,
    # which is exactly the situation in which there is nothing left to wait for.
    def failing_run_subprocess(command, **kwargs):
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(sbatch_mod, "run_subprocess", failing_run_subprocess)
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["CANCELLED"]))
    cancel_and_wait(40754228, None)


def test_cancel_and_wait_timeout(monkeypatch, fake_scancel: list[str], no_polling_delay):
    # A job that never stops must not be replaced by a new job in the same directory.
    monkeypatch.setattr(sbatch_mod, "CANCEL_TIMEOUT", 0)
    monkeypatch.setattr(sbatch_mod, "get_status", fake_poller(["RUNNING"]))
    with pytest.raises(RuntimeError, match="still reported as 'RUNNING'"):
        cancel_and_wait(40754228, None)
