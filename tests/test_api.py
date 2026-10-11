# SPDX-FileCopyrightText: 2026 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Unit tests for the API functions used in plan.py."""

import shlex

import pytest

from stepup.queue import api as api_mod


@pytest.fixture
def fake_run(monkeypatch) -> list[tuple[str, dict]]:
    """Replace `run()` of StepUp Core by a stub that records its arguments."""
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))

    monkeypatch.setattr(api_mod, "run", run)
    return calls


def test_sbatch_defaults(fake_run: list[tuple[str, dict]]):
    api_mod.sbatch("job")
    assert fake_run[0][0] == "sq-sbatch-and-wait"
    assert fake_run[0][1]["workdir"] == "job"


def test_sbatch_options(fake_run: list[tuple[str, dict]]):
    api_mod.sbatch(
        "job",
        ext=".py",
        rc="module swap cluster/joltik",
        onchange="resubmit",
        complete="test -f out.txt && test -f done.txt",
    )
    assert shlex.split(fake_run[0][0]) == [
        "sq-sbatch-and-wait",
        ".py",
        "--rc=module swap cluster/joltik",
        "--onchange=resubmit",
        "--complete=test -f out.txt && test -f done.txt",
    ]


def test_sbatch_invalid_onchange(fake_run: list[tuple[str, dict]]):
    with pytest.raises(ValueError, match="Invalid onchange policy"):
        api_mod.sbatch("job", onchange="whatever")


@pytest.mark.parametrize("complete", ["", "  "])
def test_sbatch_empty_complete(fake_run: list[tuple[str, dict]], complete: str):
    with pytest.raises(ValueError, match="must not be empty"):
        api_mod.sbatch("job", complete=complete)
