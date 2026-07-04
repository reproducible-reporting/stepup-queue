# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for stepup.queue.utils."""

from stepup.queue.utils import parse_sbatch


def test_parse_sbatch():
    assert parse_sbatch("123") == (123, None)
    assert parse_sbatch("123;clu") == (123, "clu")
