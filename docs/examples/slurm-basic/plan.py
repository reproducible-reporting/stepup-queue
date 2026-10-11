#!/usr/bin/env python3

from stepup.core.api import render_jinja, static
from stepup.queue.api import sbatch

# Two examples of a static job script, i.e. already present on disk.
static("pass/slurmjob.py")
sbatch("pass", ext=".py")
static("fail/slurmjob.sh")
sbatch("fail")

# Example of job scripts generated from a template.
static("dynamic-template.sh")
for i in range(1, 4):
    render_jinja("dynamic-template.sh", {"field": i}, f"dynamic{i}/slurmjob.sh")
    # You can use the rc option to load an environment before calling sbatch.
    # Use this only if it cannot be done in the job script itself.
    sbatch(f"dynamic{i}", rc="module swap cluster/doduo")

# Example of a job that computes several parts and skips parts that already exist.
# When NUM_PARTS is increased, the job script changes.
# The completeness check then finds missing parts, so the job is resubmitted,
# and the new job only computes the missing parts.
# Other changes to the job script, which do not add parts, do not lead to a resubmission.
NUM_PARTS = 3
static("parts-template.sh")
render_jinja(
    "parts-template.sh",
    # The wall time in minutes is estimated from the number of parts.
    {"num_parts": NUM_PARTS, "minutes": 1 + NUM_PARTS // 6},
    "parts/slurmjob.sh",
)
paths_part = [f"part{i}.txt" for i in range(NUM_PARTS)]
sbatch(
    "parts",
    out=paths_part,
    onchange="resubmit",
    complete=" && ".join(f"test -f {path}" for path in paths_part),
)
