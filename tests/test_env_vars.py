# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Tests for stepup.queue.env_vars."""

import ast
import os
import re
import subprocess
import sys

import pytest

import stepup.queue
from stepup.core.cli.env_vars_loader import core_env_vars
from stepup.core.exceptions import StepUpError
from stepup.core.path import Path
from stepup.queue.env_vars import env_vars, non_negative_int, onchange_policy, read_env_var


def _string_constants(source: str) -> set[str]:
    """Return every string literal in a module that has the form of a StepUp variable name."""
    return {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch("STEPUP_[A-Z0-9_]+", node.value)
    }


def test_env_vars_are_registered():
    """Every variable that StepUp Queue reads is registered, and vice versa.

    A variable that is read but not registered would be listed by `stepup config`
    as being without effect.
    """
    path_package = Path(stepup.queue.__file__).parent
    found = set()
    for path in path_package.walkfiles("*.py"):
        if path.name != "env_vars.py":
            found.update(_string_constants(path.read_text(encoding="utf-8")))
    registered = set(env_vars().env_vars)
    assert found - registered <= set(core_env_vars().env_vars)
    assert registered - found == set()


def test_registry():
    registry = env_vars()
    assert registry.package == "StepUp Queue"
    for name, info in registry.env_vars.items():
        assert name.startswith("STEPUP_QUEUE_")
        assert not info.secret
        assert not info.overridden


@pytest.mark.parametrize("value", ["raise", "resubmit", "ignore"])
def test_onchange_policy(value):
    assert onchange_policy(value) == value


@pytest.mark.parametrize("value", ["", "Raise", "whatever"])
def test_onchange_policy_invalid(value):
    with pytest.raises(StepUpError, match="must be one of raise, resubmit, ignore"):
        onchange_policy(value)


@pytest.mark.parametrize(("value", "expected"), [("0", 0), ("30", 30)])
def test_non_negative_int(value, expected):
    assert non_negative_int(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [("-1", "must not be negative: '-1'"), ("1.5", "not an integer: '1.5'"), ("", "not an")],
)
def test_non_negative_int_invalid(value, message):
    with pytest.raises(StepUpError, match=re.escape(message)):
        non_negative_int(value)


def test_read_env_var_default(monkeypatch):
    monkeypatch.delenv("STEPUP_QUEUE_POLLING_MIN", raising=False)
    assert read_env_var("STEPUP_QUEUE_POLLING_MIN", "10") == 10


def test_read_env_var_set(monkeypatch):
    monkeypatch.setenv("STEPUP_QUEUE_POLLING_MIN", "3")
    assert read_env_var("STEPUP_QUEUE_POLLING_MIN", "10") == 3


def test_read_env_var_without_validator(monkeypatch):
    monkeypatch.setenv("STEPUP_QUEUE_SACCT_START_TIME", "now-4days")
    assert read_env_var("STEPUP_QUEUE_SACCT_START_TIME", "now-7days") == "now-4days"


def test_read_env_var_invalid(monkeypatch):
    monkeypatch.setenv("STEPUP_QUEUE_POLLING_MIN", "-3")
    with pytest.raises(
        StepUpError, match="Invalid value of STEPUP_QUEUE_POLLING_MIN: must not be negative"
    ):
        read_env_var("STEPUP_QUEUE_POLLING_MIN", "10")


def test_read_env_var_unregistered():
    with pytest.raises(KeyError):
        read_env_var("STEPUP_QUEUE_UNKNOWN", "")


def _stepup_config(path_tmp: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run `stepup config` in an environment with no other StepUp variables than those given.

    The home directory is replaced, so that a config file of the developer cannot interfere.
    """
    full_env = {name: value for name, value in os.environ.items() if not name.startswith("STEPUP_")}
    full_env.update(HOME=path_tmp, STEPUP_ROOT=path_tmp, **env)
    return subprocess.run(
        [sys.executable, "-m", "stepup.core", "config"],
        cwd=path_tmp,
        env=full_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_stepup_config(path_tmp: Path):
    cp = _stepup_config(path_tmp, {"STEPUP_QUEUE_ONCHANGE": "ignore"})
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert '# StepUp Queue environment variables:\n#   STEPUP_QUEUE_ONCHANGE = "ignore"\n' in (
        cp.stdout
    )
    assert "ERROR" not in cp.stdout


def test_stepup_config_invalid(path_tmp: Path):
    cp = _stepup_config(path_tmp, {"STEPUP_QUEUE_ONCHANGE": "whatever"})
    assert cp.returncode != 0
    assert (
        '#   STEPUP_QUEUE_ONCHANGE = "whatever"  '
        "<-- ERROR: must be one of raise, resubmit, ignore, got 'whatever'\n"
    ) in cp.stdout
