# SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
# SPDX-License-Identifier: LGPL-3.0-or-later
"""StepUp Queue API functions to build workflows."""

import shlex
from collections.abc import Collection

from stepup.core.api import run
from stepup.core.path import StrPath, coerce_paths

__all__ = ("sbatch",)


def sbatch(
    workdir: StrPath,
    *,
    ext: str = ".sh",
    rc: str | None = None,
    inp: Collection[StrPath] | StrPath = (),
    env: Collection[str] | str = (),
    out: Collection[StrPath] | StrPath = (),
    vol: Collection[StrPath] | StrPath = (),
    onchange: str | None = None,
    optional: bool = False,
    resources: dict[str, int] | str | None = None,
    duration: float | None = None,
):
    """Submit a SLURM job script.

    The following filename conventions are used in the given working directory:

    - `slurmjob{ext}` is the job script to be submitted.
    - `slurmjob.log` is StepUp Queue's log file keeping track of the job's status.
    - `slurmjob.out` is the job's output file (written by SLURM).
    - `slurmjob.err` is the job's error file (written by SLURM).
    - `slurmjob.ret` is the job's return code (written by a wrapper script).

    Hence, you can only have one job script per working directory,
    and it is strongly recommended to use meaningful directory names.
    Within the directory, try to use as much as possible exactly the same file names for all jobs.

    When the step is executed, it will submit the job or skip this if it was done before.
    If submitted, the step will wait until the job is finished.
    If already finished, the step will essentially be a no-op.

    See `run()` documentation in StepUp Core for all optional arguments and return value.
    Note that the `inp`, `out` and `vol` arguments are extended
    with the files mentioned above and that any additional files you specify
    are interpreted relative to the working directory.

    Parameters
    ----------
    ext
        The filename extension of the jobscript.
        The full name is `f"slurmjob{ext}"`.
        Extensions `.log`, `.out`, `.err` and `.ret` are not allowed.
    rc
        A resource configuration to be executed before calling sbatch.
        This will be executed in the same shell, right before the sbatch command.
        For example, you can run `module swap cluster/something`
        or prepare other resources.
        If multiple instructions are needed, put them in a file, e.g. `rc.sh`
        and pass it here as `source rc.sh`.
        In this case, you usually also want to include `rc.sh` in the `inp` list.
    onchange
        Policy when a the inputs of a previously submitted job have changed.
        Must be one of `"raise"`, `"resubmit"` or `"ignore"`.
    """
    if ext == "":
        ext = ".sh"
    elif ext[0] != ".":
        ext = f".{ext}"
    if ext in [".log", ".out", ".err", ".ret"]:
        raise ValueError(f"Invalid extension {ext}. The extension must not be .log, .out or .err.")
    cmd = "sq-sbatch-and-wait"
    if ext != ".sh":
        cmd += f" {ext}"
    if rc is not None:
        cmd += f" --rc={shlex.quote(rc)}"
    if onchange is not None:
        if onchange not in ["raise", "resubmit", "ignore"]:
            raise ValueError(f"Invalid onchange policy {onchange}.")
        cmd += f" --onchange={onchange}"
    return run(
        cmd,
        inp=[f"slurmjob{ext}", *coerce_paths(inp)],
        env=env,
        out=["slurmjob.out", "slurmjob.err", "slurmjob.ret", *coerce_paths(out)],
        vol=["slurmjob.log", *coerce_paths(vol)],
        workdir=workdir,
        optional=optional,
        resources=resources,
        duration=duration,
    )
