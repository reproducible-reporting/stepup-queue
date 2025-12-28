# Usage

## The `sbatch()` Function

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
There are some constraints to keep in mind:

- You can only submit one job from a given directory.
- The job script must be called `slurmjob.sh`,
  or may have a different extension if it is not a shell script.
- The job script must be executable and have a shebang line (e.g. `#!/usr/bin/env bash`).
- The job script cannot specify an output or error file.
  These will be specified by the `sbatch()` function
  as `slurmjob.out` and `slurmjob.err`, respectively.
- Array jobs are not supported.
  Presence of the `--array` option in the `sbatch` command will raise an exception.

When the workflow is executed, the `sbatch` step will submit the job to the queue.
It will then wait for the job to complete, just like `sbatch --wait`.
Unlike `sbatch --wait`, it can also wait for a previously submitted job to complete.
This is useful when the workflow gets killed for some reason,
e.g. due to a wall time limit.

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
    it is assumed that your job script will handle any necessary cleanup.
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
This will stop StepUp immediately, but it may not have the chance to write its state to disk.
Normally, this should be fine, as it uses SQLite, which is robust against crashes.

## Killing Running Jobs

StepUp Queue will not cancel any jobs when the workflow is interrupted.
It is quite common for a workflow to be interrupted by accident or for technical reasons.
In this case, it would be inefficient to also cancel running jobs, which may still be doing useful work.
Instead, jobs continue to run, and you can restart the StepUp workflow to pick up where it left off.

If you want to cancel running SLURM jobs, typically after interrupting StepUp,
you can run the following command:

```bash
stepup canceljobs dir/to/running/jobs
```

This command will recursively look for all `slurmjob.log` files in the given paths
(or the current directory if no paths are given),
extract the corresponding job IDs of running jobs, and generate `scancel` commands to cancel them.
After each `scancel` command, the path of the `slurmjob.log` file
and the job status are added as a comment.
For example, the output may look like this:

```bash
scancel 123456  # path/to/job1/slurmjob.log RUNNING
scancel 123457  # path/to/job2/slurmjob.log PENDING
```

By default, this command will not perform any destructive actions
and will only print the `scancel` commands that would be executed.
You can pass the `--commit` option to actually execute the `scancel` commands.
Alternatively, you can select a subset of jobs to cancel with the `grep` and `xargs` commands, for example:

```bash
stepup canceljobs dir/to/running/jobs | grep "filename_pattern" | xargs sh -c
```

## Removing Directories of Cancelled or Failed Jobs

After a job was cancelled or has failed,
the corresponding files are not removed automatically.
This is to allow for inspection of the job's output and error files for debugging purposes.
You can remove the directories of cancelled or failed jobs
by running the following command:

```bash
stepup removejobs dir/to/jobs
```

This command will recursively look for all `slurmjob.log` files in the given paths
(or the current directory if no paths are given),
check the status of the corresponding jobs,
and remove the directories of jobs that have ended but were not successful.

By default, this command will not perform any destructive actions
and will only print the remove commands that would be executed.
You can pass the `--commit` option to actually remove the directories.

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

## Hints for writing Job Scripts

When writing job scripts for any type of workflow (not only StepUp),
and the cluster is using a distributed file system (like IBM Spectrum Scale or Lustre),
you should not assume that files created by one job are immediately visible to subsequent jobs.
When the cluster load is high, there can be significant delays
in the file metadata synchronization, sometimes several minutes.
To mitigate this issue, you can add a waiting function to your job scripts, like this:

```bash
wait_for_file() {
  # Waiting function to deal with file synchronization issues.
  local file="$1"
  local timeout="${2:-600}"   # timeout in seconds (default 10 min)
  local interval="${3:-5}"    # poll interval in seconds (default 5 sec)

  local elapsed=0

  while [[ ! -e "$file" ]]; do
    if (( elapsed >= timeout )); then
      echo "ERROR: Timeout waiting for file: $file" >&2
      return 1
    fi
    sleep "$interval"
    (( elapsed += interval ))
  done

  return 0
}
```

Further down in the job script, this function can be used as follows:

```bash
# Wait for input.dat to appear or exit with error after timeout.
wait_for_file "input.dat" || exit 1
```

## Technical Details of StepUp Queue's interaction with SLURM

The timestamps in the `slurmjob.log` are inherently inaccurate (order one minute)
due to the caching mechanism of SLURM.
Checking more job states frequently with `sacct` (SLURM accounting tool)
would also put too much load on SLURM, which is not desirable.
StepUp Queue will therefore run `sacct` only occasionally and cache its output on disk.
Furthermore, a `slurmjob.log` file is written for each job to keep track of
its submission time, job ID, and previous states.

The status of the jobs is inferred from `sacct -o 'jobidraw,state' -PXn`,
if relevant with a `--cluster` argument.
In addition, a configurable `-S` argument is passed to `sacct`.
Its output is cached in a subdirectory `.stepup/queue` of the workflow root.
The cached result is reused by all `sbatch` actions,
so the number of `sacct` calls is independent of the
number of jobs running in parallel.

The time between two `sacct` calls (per cluster) can be controlled with the
`STEPUP_SBATCH_CACHE_TIMEOUT` environment variable, which is `"30"` (seconds) by default.
Increase this value if you want to reduce the burden on SLURM.

The cached output of `sacct` is checked by the `sbatch` actions with a randomized polling interval.
If any of these actions needs notices that the cached file is too old,
it will acquire a lock on the cache file and update it by calling `sacct`.
The randomization guarantees that concurrent calls to `sacct` (for multiple clusters)
will not all coincide.
The polling time can be controlled with two additional environment variables:

- `STEPUP_SBATCH_POLLING_MIN` = the minimal polling interval in seconds, default is `10`.
- `STEPUP_SBATCH_POLLING_MAX` = the maximal polling interval in seconds, default is `20`.

By default, `sacct` queries job information of the last 7 days.
You can change this by setting the `STEPUP_SACCT_START_TIME` environment variable
to a different value understood by `sacct -S`, e.g., `now-4days` or `2025-01-01T00:00:00`.

To avoid an infinite loop for jobs that are unlisted for too long,
a job is considered to be failed if it is not listed for more than
`STEPUP_SBATCH_UNLISTED_TIMEOUT` seconds, which is `600` (10 minutes) by default.

Sometimes, job submission with `sbatch` can fail due to transient issues,
such as temporary communication problems with the SLURM controller.
To improve robustness, StepUp Queue will retry the `sbatch` command
a number of times before giving up.
You can control the retry behavior with the following environment variables:

- `STEPUP_SBATCH_RETRY_NUM`: Number of retry attempts (default is `5`).
- `STEPUP_SBATCH_RETRY_DELAY_MIN`: Minimum delay between retries in seconds (default is `60`).
- `STEPUP_SBATCH_RETRY_DELAY_MAX`: Maximum delay between retries in seconds (default is `120`).
