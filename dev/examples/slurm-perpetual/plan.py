#!/usr/bin/env python3

from stepup.core.api import static
from stepup.queue.api import sbatch

static("step1/", "step1/slurmjob.sh", "step2/", "step2/slurmjob.sh")
sbatch("step1/", out="../intermediate.txt")
sbatch("step2/", inp="../intermediate.txt")
