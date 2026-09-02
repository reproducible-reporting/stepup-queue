#!/usr/bin/env bash
#SBATCH --job-name stepup
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --output=stepup-%j.out
#SBATCH --cpus-per-task=1
#SBATCH --time=00:01:00
#SBATCH --mem=4G

# The SBATCH parameters above are kept minimal for demonstration purposes.
# In production, they need to be scaled up appropriately.
# For example, for NUM_JOBS=100, reasonable settings would be:
# --cpus-per-task=8 --time=12:00:00 --mem=16G

# Abort on an undefined variable,
# which catches a missing SLURM_JOB_END_TIME below.
# Do not add `set -e`: `sb` reports failed steps through its return code,
# which is inspected at the end of this script.
set -u

# Number of concurrent StepUp jobs,
# which corresponds to the number of concurrently running jobs in the SLURM queue.
# This is unrelated to the single core used by this workflow script itself.
# This example is simple enough for lower values to be sufficient.
NUM_JOBS=5

# How long before the wall time limit StepUp is told to stop.
# - SOFT: the first shutdown, for which 1800 seconds is reasonable in production.
SOFT_MARGIN=30
# - HARD: the second shutdown, for which 600 seconds is reasonable in production.
HARD_MARGIN=10

echo "StepUp workflow job starts: $(date)"

# If needed, load required modules and activate a relevant virtual environment.
# For example:
# module load Python/3.12.3
# activate venv/bin/activate

# Start a background process that ends StepUp before the wall time limit.
# The first shutdown waits for running steps to complete.
# The second one interrupts the steps that are still waiting.
# The SLURM jobs that these steps were waiting for stay in the queue
# and are picked up again by the resubmitted workflow.
# The delay is computed here rather than inside the background process,
# so that a missing SLURM_JOB_END_TIME stops this script
# instead of silently leaving it without a wall time monitor.
echo "Starting background process to monitor wall time."
SOFT_DELAY=$((SLURM_JOB_END_TIME - SOFT_MARGIN - $(date +%s)))
# Refuse margins that do not fit in the remaining wall time.
# A negative sleep would make the monitor shut down StepUp right away,
# and this script would then resubmit itself in a tight loop.
if ((SOFT_DELAY <= 0 || HARD_MARGIN > SOFT_MARGIN)); then
    echo "The shutdown margins do not fit in the wall time limit."
    echo "Raise the SBATCH time limit or lower SOFT_MARGIN and HARD_MARGIN."
    exit 1
fi
(
    sleep "${SOFT_DELAY}"
    stepup shutdown
    sleep $((SOFT_MARGIN - HARD_MARGIN))
    stepup shutdown
) &
WATCHDOG_PID=$!

echo "Starting stepup with a maximum of ${NUM_JOBS} concurrent jobs."
sb -j "${NUM_JOBS}"
RETURNCODE=$?

# Stop the wall time monitor,
# so that it cannot shut down an unrelated StepUp run later on.
kill "${WATCHDOG_PID}" 2>/dev/null

# StepUp sets the DRAINED bit when its scheduler was still draining,
# meaning it was stopped before it ran out of work.
# That is precisely when the workflow job has to be resubmitted.
DRAINED=$(python3 -c 'from stepup.core.enums import ReturnCode; print(ReturnCode.DRAINED.value)')
if ((RETURNCODE & DRAINED)); then
    echo "Resubmitting job script to let StepUp finalize the workflow."
    sbatch workflow.sh
    # The workflow is unfinished,
    # but this job did its part and hands over to the next one.
    RETURNCODE=0
else
    echo "Stepup stopped by itself."
fi

echo "StepUp workflow job ends: $(date)"
exit "${RETURNCODE}"
