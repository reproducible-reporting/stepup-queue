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
"""StepUp Queue API functions to build workflows."""

import shlex
from collections.abc import Collection

from stepup.core.api import step
from stepup.core.utils import string_to_list

__all__ = ("sbatch",)


def sbatch(
    workdir: str,
    *,
    ext: str = ".sh",
    rc: str | None = None,
    inp: Collection[str] | str = (),
    env: Collection[str] | str = (),
    out: Collection[str] | str = (),
    vol: Collection[str] | str = (),
    onchange: str | None = None,
    optional: bool = False,
    pool: str | None = None,
    block: bool = False,
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

    See `step()` documentation in StepUp Core for all optional arguments.
    and the return value.
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
    action = "sbatch"
    if ext != ".sh":
        action += f" {ext}"
    if rc is not None:
        action += f" --rc={shlex.quote(rc)}"
    if onchange is not None:
        if onchange not in ["raise", "resubmit", "ignore"]:
            raise ValueError(f"Invalid onchange policy {onchange}.")
        action += f" --onchange={onchange}"
    return step(
        action,
        inp=[f"slurmjob{ext}", *string_to_list(inp)],
        env=env,
        out=["slurmjob.out", "slurmjob.err", "slurmjob.ret", *string_to_list(out)],
        vol=["slurmjob.log", *string_to_list(vol)],
        workdir=workdir,
        optional=optional,
        pool=pool,
        block=block,
    )
