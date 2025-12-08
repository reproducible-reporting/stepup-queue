#!/usr/bin/env bash
#SBATCH --job-name stepup
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --output=stepup-%j.out

# The SBATCH parameters in this example are kept minimal for demonstration purposes.
# In production, they need to be scaled up appropriately.
# For example, for NWORKER=100, reasonable settings would be:
# --cpus-per-task=8 --time=12:00:00 --mem=16G

#SBATCH --cpus-per-task=1
#SBATCH --time=00:01:00
#SBATCH --mem=4G

# Number of concurrent StepUp workers, which corresponds to the number of
# concurrently submitted jobs in the Slurm queue:
NWORKER=5

# Time-out settings
# SOFT: In production, 1800 seconds (before the wall limit) is reasonable.
export STEPUP_SHUTDOWN_TIMEOUT_SOFT=30
# HARD: In production, 600 seconds (before the wall limit) is reasonable.
export STEPUP_SHUTDOWN_TIMEOUT_HARD=10

echo "StepUp workflow job starts:" $(date)

# If needed, load required modules and activate a relevant virtual environment.
# For example:
# module load Python/3.12.3
# activate venv/bin/activate

# Create a temporary directory to store a file that will be used as a flag
# to indicate that resubmission is needed.
STEPUP_QUEUE_FLAG_DIR=$(mktemp -d)
echo "Created temporary directory: $STEPUP_QUEUE_FLAG_DIR"
trap 'rm -rv "$STEPUP_QUEUE_FLAG_DIR"' EXIT

# Start a background process that will end stepup near the wall time limit.
# The first shutdown will wait for running steps to completed.
# The second will forcefully terminate remaining running steps.
echo "Starting background process to monitor wall time."
(
    sleep $((${SLURM_JOB_END_TIME} - ${SLURM_JOB_START_TIME} - ${STEPUP_SHUTDOWN_TIMEOUT_SOFT}))
    touch ${STEPUP_QUEUE_FLAG_DIR}/resubmit
    stepup shutdown
    sleep ${STEPUP_SHUTDOWN_TIMEOUT_HARD}
    stepup shutdown
) &
BGPID=$!
trap "kill $BGPID" EXIT

echo "Starting stepup with a maximum of ${NWORKER} concurrent jobs."
stepup boot -n ${NWORKER}
# This means that at most ${NWORKER} jobs will be submitted concurrently.
# You can adjust the number of workers based on your needs.
# In fact, because this example is simple, a single worker would be sufficient.
# Note that the number of workers is unrelated to the single core used by this workflow script.

# Use the temporary file to determine if the workflow script must be resubmitted.
echo "Checking if stepup was forcibly stopped."
if [ -f ${STEPUP_QUEUE_FLAG_DIR}/resubmit ]; then
    echo "Resubmitting job script to let StepUp finalize the workflow."
    sbatch workflow.sh
else
    echo "Stepup stopped by itself."
fi

echo "StepUp workflow job ends:" $(date)
