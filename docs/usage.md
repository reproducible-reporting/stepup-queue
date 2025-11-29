# Usage

## The `sbatch` Function

If you want to submit a job to the queue as part of a StepUp workflow,
you must first prepare a directory with a job script called `slurmjob.sh`.
This can be either a static file or the output of a previous step in the workflow.
The function [`sbatch()`][stepup.queue.api.sbatch] will then submit the job to the queue.
For simplicity, the following example assumes that the job script is static:

```python
from stepup.core.api import static
from stepup.queue.api import sbatch

static("compute/", "compute/slurmjob.sh")
sbatch("compute/")
```

All arguments to the `sbatch` command of SLURM
must be included in the `slurmjob.sh` script with `#SBATCH` directives.
You can only submit one job from a given directory.

When the workflow is executed, the `sbatch` step will submit the job to the queue.
It will then wait for the job to complete, just like `sbatch --wait`.
Unlike `sbatch --wait`, it can also wait for a previously submitted job to complete.
This can be useful when the workflow gets killed for some reason.

The standard output and error of the job are written to `slurmjob.out` and `slurmjob.err`, respectively.

The current status of the job is stored in the `slurmjob.log` file,
which StepUp Queue both reads and writes.
When you restart StepUp and `slurmjob.log` exists for a given `sbatch()` step,
the job is not resubmitted; instead, StepUp waits for the existing job to finish.
To force a job to be resubmitted, you must delete `slurmjob.log`
and manually cancel the corresponding running job, before restarting StepUp.
Deleting `slurmjob.log` without cancelling the job
will cause inconsistencies that StepUp cannot detect.

If the job's inputs change and StepUp is restarted,
you can control how this situation is handled using
the `STEPUP_QUEUE_ONCHANGE` environment variable or the `onchange` argument of `sbatch()`:

1. `onchange="raise"` (default):
    Raises an exception and aborts the workflow.
    This is the safest option, ensuring the workflow does not continue with inconsistent data.
2. `onchange="resubmit"`:
    Cancels any running job and removes it from the queue,
    then resubmits the job with the new inputs.
    Old outputs are not deleted before resubmission;
    it is assumed your job script will handle any necessary cleanup.
3. `onchange="ignore"`:
    Does not resubmit the job; the workflow continues using any existing outputs.
    This is useful if input changes do not affect outputs,
    e.g., updating the job script to request more resources.
    If outputs are missing but `slurmjob.log` exists, the step will fail.
    If you manually remove `slurmjob.log` and cancel the running job,
    the job will be resubmitted with the new inputs.
    Use this option with caution, as it can lead to inconsistent workflow data.

## Examples

- A simple example with static and dynamically generated job scripts
  can be found in the [`examples/slurm-basic/`](examples/slurm-basic/README.md).

- The example [`examples/slurm-perpetual/`](examples/slurm-perpetual/README.md)
  shows how to run StepUp itself as a job in the queue,
  which cancels and submits itself again when nearing the wall time limit,
  if the workflow has not yet completed.

## Stopping the Workflow Gracefully

When running StepUp interactively, and the workflow is just waiting for jobs to complete,
you can stop it gracefully by pressing `q` twice.
This will interrupt the worker processes that are waiting for SLURM jobs to be completed.
The actual SLURM jobs will continue to run.
You can later restart StepUp to continue waiting for the jobs to complete.

If you are running StepUp itself also as a SLURM job, you have no keyboard interaction to stop it.
In this case, you can achieve the same effect by logging into the node where StepUp is running,
and running the `stepup shutdown` command twice in the directory where StepUp is running.
If this is needed often, e.g. when debugging, you can automate this with a script.
The following is a simple example, which you may need to adapt for your setup:

```bash
#!/usr/bin/bash
if [ -z "$1" ]; then echo "Usage: $0 <jobid>"; exit 1; fi
JOBID=$(echo "${1}" | tr -dc '0-9')
NODE=$(squeue -j ${JOBID} -h -o %N)
WORKDIR=$(squeue -j ${JOBID} -h -o %Z)
SCRIPT="cd ${WORKDIR}/.. && source activate && cd ${WORKDIR} && stepup shutdown && stepup shutdown"
COMMAND="bash -l -c '${SCRIPT}'"
echo "Executing on node ${NODE}: ${COMMAND}"
ssh ${NODE} "${COMMAND}"
```

The script takes a SLURM job ID (or the out file, like `slurm-<jobid>.out`) as an argument,
determines the node and working directory of the job,
and runs `stepup shutdown` twice in that directory via `ssh`.
The way the software environment is activated may differ from your setup.

A less sophisticated approach is to simply cancel the StepUp job via `scancel <jobid>`.
This will stop StepUp immediately but it may not have the chance to write its state to disk.
Normally, this should be fine, as it uses SQLite, which is robust against crashes.

## Killing Running Jobs

If you need to cancel all running SLURM jobs, typically after interrupting StepUp,
you can run the following command from the top-level directory of the workflow:

```bash
stepup canceljobs
```

It is part of the design of StepUp Queue's not to automatically cancel jobs when the workflow is interrupted.
It is quite common for a workflow to be interrupted by accident or for technical reasons.
In this case, it would be inefficient to also cancel running jobs, which may still be doing useful work.
Instead, jobs continue to run and you can restart the StepUp workflow to pick up where it left off.

After having cancelled jobs, it is still your responsibility to clean up files in the workflow.
Removing them is not always desirable, so this is not done automatically.

## Useful Settings when Developing Workflows

When developing and testing workflows that use `sbatch()`,
it can be useful to configure StepUp to be less rigorous about reproducibility and file cleaning.
The following environment variables can help with this:

```bash
# Do not remove outdated output files after a successful completion of the workflow.
export STEPUP_CLEAN=0
# Ignore changes in inputs to sbatch() steps and do not resubmit jobs.
# Just assume that existing outputs are still valid, despite changed inputs.
export STEPUP_QUEUE_ONCHANGE="ignore"
```

These settings are not recommended for production workflows.

## Technical Details

The timestamps in the log file have a low resolution of about 1 minute.
The job state is only checked every 30--40 seconds to avoid overloading the Job Scheduler.
Information from `slurmjob.log` is maximally reused to avoid unnecessary `scontrol` calls.

The status of the job is inferred from `scontrol show job`, if relevant with a `--cluster` argument.
To further minimize the number of `scontrol` calls in a parallel workflow,
its output is cached and stored in `~/.cache/stepup-queue`.
The cached results are reused by all `sbatch` actions,
so the number of `scontrol` calls is independent of the
number of jobs running in parallel.

The time between two `scontrol` calls (per cluster) can be controlled with the
`STEPUP_SBATCH_CACHE_TIMEOUT` environment variable, which is `"30"` (seconds) by default.
Increase this value if you want to reduce the burden on Slurm.

The cached output of `scontrol` is checked with a randomized polling interval.
The randomization guarantees that concurrent calls to `scontrol` (for multiple clusters)
will not all coincide.
The polling time can be controlled with two additional environment variables:

- `STEPUP_SBATCH_POLLING_INTERVAL` = the minimal polling interval in seconds, default is `10`.
- `STEPUP_SBATCH_TIME_MARGIN` = the width of the uniform distribution for the polling interval
  in seconds, default is `15`.
