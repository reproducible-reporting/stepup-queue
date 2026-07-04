# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
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
