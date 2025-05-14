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

The current status of the job is written to (and read from) the `slurmjob.log` file.
By default, the job is not resubmitted if `slurmjob.log` exists.
Instead, it waits for the job to complete without resubmitting it.
You can remove `slurmjob.log` to ensure that the job is resubmitted,
but this is obviously dangerous if the job is still running.

If the inputs of the job specified with `sbatch("compute/", inp=["inp.txt"])` have changed,
restarting the workflow will by default raise an exception.
Ideally, you should clean up old outputs before restarting the workflow,
and check that you really want to remove the data before doing so.
If you feel this is overly cautious, you can set the `STEPUP_QUEUE_RESUBMIT_CHANGED_INPUTS`
environment variable to `"yes"` to allow the workflow to resubmit jobs with changed inputs.
Old outputs are not removed before resubmission.
It is assumed that your job script will perform the necessary cleanup itself.

## Examples

- A simple example with static and dynamically generated job scripts
  can be found in the [`examples/slurm-basic/`](examples/slurm-basic/README.md).

- The example [`examples/slurm-perpetual/`](examples/slurm-perpetual/README.md)
  shows how to run StepUp itself as a job in the queue,
  which cancels and submits itself again when nearing the wall time limit,
  if the workflow has not yet completed.

## Killing running jobs

If you decide that you want to interrupt the workflow and cancel all running SLURM jobs,
it is not enough to simply kill or stop StepUp.
You must also cancel the jobs in the SLURM queue.
This can be done by running the following command from the top-level directory of the workflow:

```bash
stepup canceljobs
```

It is part of the design of StepUp Queue's not to automatically cancel jobs when the workflow is interrupted.
It is quite common for a workflow to be interrupted by accident or for technical reasons.
In this case, it would be inefficient to also cancel running jobs, which may still be doing useful work.
Instead, jobs continue to run and you can restart the StepUp workflow to pick up where it left off.

After having cancelled jobs, it is still your responsibility to clean up files in the workflow.
Removing them is not always desirable, so this is not done automatically.

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

- `STEPUP_SBATCH_POLLING_INTERVAL` = the minimal polling interval in seconds, default is `"10"`.
- `STEPUP_SBATCH_TIME_MARGIN` = the width of the uniform distribution for the polling interval
  in seconds, default is `"5"`.
