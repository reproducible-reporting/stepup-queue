#!/usr/bin/env python3

from stepup.core.api import mkdir, render_jinja, static
from stepup.queue.api import sbatch

# First an example of a static job script, i.e. already present on disk.
static("static/", "static/slurmjob.sh")
sbatch("static")

# Now an example of a job script that is generated from a template.
static("dynamic-template.sh")
for i in range(1, 4):
    mkdir(f"dynamic{i}/")
    render_jinja("dynamic-template.sh", {"field": i}, f"dynamic{i}/slurmjob.sh")
    sbatch(f"dynamic{i}/")
