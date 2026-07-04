# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Fixtures for testing StepUp Queue."""

import pytest
from path import Path


@pytest.fixture
def path_tmp(tmpdir: str) -> Path:
    return Path(tmpdir)
