#!/usr/bin/env python3

from stepup.core.api import mkdir, render_jinja, static

from stepup.queue.api import sbatch

# Two examples of a static job script, i.e. already present on disk.
static("pass/", "pass/slurmjob.py")
sbatch("pass", ext=".py")
static("fail/", "fail/slurmjob.sh")
sbatch("fail")

# Example of job scripts generated from a template.
static("dynamic-template.sh")
for i in range(1, 4):
    mkdir(f"dynamic{i}/")
    render_jinja("dynamic-template.sh", {"field": i}, f"dynamic{i}/slurmjob.sh")
    # You can use the rc option to load an environment before calling sbatch.
    # Use this only if it cannot be done in the job script itself.
    sbatch(f"dynamic{i}/", rc="module swap cluster/doduo")
