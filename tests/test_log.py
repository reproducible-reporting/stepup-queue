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
"""Unit tests for stepup.queue.log."""

import pytest

from stepup.queue.log import check_log_version

LOG_EXAMPLE = """\
StepUp Queue sbatch wait log format version 2
2f49f43af482a27116cfeb3a87441a426fb41369cd04d0ca183c765ed0f1f68f
2026-01-01T00:15:08.451402 Submitted 40754228;joltik
2026-01-01T00:15:46.452136 PENDING
2026-01-01T00:47:11.543280 RUNNING
2026-01-01T01:59:03.760998 COMPLETED
"""


def test_check_log_version():
    check_log_version(LOG_EXAMPLE.splitlines()[0])
    with pytest.raises(ValueError):
        check_log_version("StepUp Queue sbatch wait log format version 1")
