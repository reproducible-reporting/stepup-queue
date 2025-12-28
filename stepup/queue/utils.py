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
"""Utility functions for the StepUp queue module."""

from itertools import chain

from path import Path

__all__ = ("search_jobs",)


def search_jobs(paths: list[Path], verbose: bool = False) -> list[Path]:
    """Recursively search for slurmjob.log files in the specified directories.

    Parameters
    ----------
    paths
        List of directories to search in.
    verbose
        Whether to print warnings when paths do not exist or are not directories.

    Returns
    -------
    paths_log
        Sorted list of found slurmjob.log file paths.
    """
    paths_log = set()
    for path in paths:
        if not path.exists():
            if verbose:
                print(f"# WARNING: Path {path} does not exist.")
            continue
        if not path.is_dir():
            if verbose:
                print(f"# WARNING: Path {path} is not a directory.")
            continue
        for path_sub in chain([path], path.walkdirs()):
            path_log = path_sub / "slurmjob.log"
            if path_log.is_file():
                paths_log.add(path_log)
    return sorted(paths_log)
