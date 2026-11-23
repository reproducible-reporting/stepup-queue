# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""The `STEPUP_QUEUE_*` environment variables of StepUp Queue.

They are registered with StepUp Core through the `stepup.env_vars` entry point,
so that `stepup config` lists them and checks their values.
"""

import os
from typing import Any

from stepup.core.converters import positive_int
from stepup.core.env_vars import EnvVarInfo, EnvVarRegistry
from stepup.core.exceptions import StepUpError

__all__ = ("ONCHANGE_POLICIES", "env_vars", "onchange_policy", "read_env_var")


ONCHANGE_POLICIES = ("raise", "resubmit", "ignore")
"""The policies for a job whose inputs have changed since it was submitted."""


def onchange_policy(value: str) -> str:
    """Check that a string is one of the `ONCHANGE_POLICIES`.

    Parameters
    ----------
    value
        The name of the policy.

    Returns
    -------
    policy
        The unchanged name of the policy.

    Raises
    ------
    StepUpError
        If the name is not that of a policy.
    """
    if value not in ONCHANGE_POLICIES:
        raise StepUpError(f"must be one of {', '.join(ONCHANGE_POLICIES)}, got {value!r}")
    return value


def non_negative_int(value: str) -> int:
    """Convert a string to an integer, requiring it to be zero or positive.

    Parameters
    ----------
    value
        The value to convert, e.g. `"30"`.

    Returns
    -------
    number
        The non-negative integer.

    Raises
    ------
    StepUpError
        If the value is not an integer or is negative.
    """
    try:
        number = int(value)
    except ValueError as exc:
        raise StepUpError(f"not an integer: {value!r}") from exc
    if number < 0:
        raise StepUpError(f"must not be negative: {value!r}")
    return number


_ENV_VARS = {
    "STEPUP_QUEUE_CACHE_TIMEOUT": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_CANCEL_TIMEOUT": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_ONCHANGE": EnvVarInfo(secret=False, validator=onchange_policy),
    "STEPUP_QUEUE_POLLING_MAX": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_POLLING_MIN": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_RETRY_DELAY_MAX": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_RETRY_DELAY_MIN": EnvVarInfo(secret=False, validator=non_negative_int),
    "STEPUP_QUEUE_RETRY_NUM": EnvVarInfo(secret=False, validator=positive_int),
    "STEPUP_QUEUE_SACCT_START_TIME": EnvVarInfo(secret=False),
    "STEPUP_QUEUE_UNLISTED_TIMEOUT": EnvVarInfo(secret=False, validator=non_negative_int),
}


def env_vars() -> EnvVarRegistry:
    """Return the environment variables of StepUp Queue."""
    return EnvVarRegistry("StepUp Queue", dict(_ENV_VARS))


def read_env_var(name: str, default: str) -> Any:
    """Read a variable of StepUp Queue, converted by the validator it is registered with.

    Parameters
    ----------
    name
        The name of the variable, which must be registered in `env_vars()`.
    default
        The value to use when the variable is not set.
        It is converted in the same way as a value that is set.

    Returns
    -------
    value
        The value returned by the validator,
        or the string value for a variable without a validator.

    Raises
    ------
    StepUpError
        If the validator rejects the value.
    """
    value = os.getenv(name, default)
    validator = _ENV_VARS[name].validator
    if validator is None:
        return value
    try:
        return validator(value)
    except ValueError as exc:
        raise StepUpError(f"Invalid value of {name}: {exc}") from exc
