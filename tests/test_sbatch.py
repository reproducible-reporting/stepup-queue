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
"""Unit tests for the sbatch wrapper."""

import time

import pytest
from path import Path

from stepup.core.worker import WorkThread
from stepup.queue.sbatch import (
    cached_run,
    make_cache_header,
    parse_cache_header,
    parse_sacct_out,
    parse_sbatch,
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


def test_parse_sbatch():
    assert parse_sbatch("123") == (123, None)
    assert parse_sbatch("123;clu") == (123, "clu")


def test_cached_run(path_tmp: Path):
    path_out = path_tmp / "date.txt"
    work_thread = WorkThread("<test>")
    cache_time1, out1, ret1 = cached_run(work_thread, "date", path_out, 1)
    cache_time2, out2, ret2 = cached_run(work_thread, "date", path_out, 10)
    assert cache_time1 == pytest.approx(cache_time2, 1e-4)
    assert out1 != ""
    assert out1 == out2
    assert ret1 == ret2
    time.sleep(2)
    cache_time3, out3, ret3 = cached_run(work_thread, "date", path_out, 1)
    assert abs(cache_time1 - cache_time3) > 0.5
    assert out1 != out3
    assert ret1 == ret3


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
