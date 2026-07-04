# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for the sbatch wrapper."""

import time

import pytest
from path import Path

from stepup.queue.sbatch import (
    RE_SBATCH,
    RE_SBATCH_ARRAY,
    RE_SBATCH_STDERR,
    RE_SBATCH_STDOUT,
    UNSUPPORTED_DIRECTIVES,
    cached_run,
    make_cache_header,
    parse_cache_header,
    parse_sacct_out,
)


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
