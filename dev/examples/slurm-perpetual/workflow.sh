#!/usr/bin/env bash
#SBATCH --job-name perpetual-workflow
#SBATCH --nodes=1
#SBATCH --num-tasks=1
#SBATCH --cpus-per-task=1
#SBATCH --output=workflow-%j.out
#SBATCH --time=00:01:00

# In production, --time=00:12:00 is a reasonable time limit.

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
    sleep 30;  # In production, 39600 seconds is reasonable.
    touch ${STEPUP_QUEUE_FLAG_DIR}/resubmit;
    stepup shutdown;
    sleep 10;  # In production, 300 seconds is reasonable.
    stepup shutdown
) &
BGPID=$!
trap "kill $BGPID" EXIT

# Start StepUp with 5 workers.
# This means that at most 5 jobs will be submitted concurrently.
# You can adjust the number of workers based on your needs.
# In fact, because this example is simple, a single worker would be sufficient.
# Note that the number of workers is unrelated
# to the single core used by this workflow script.
echo "Starting stepup with a maximum of 5 concurrent jobs."
stepup boot -n 5

# Use the temporary file to determine if the workflow script must be resubmitted.
echo "Checking if stepup was forcibly stopped."
if [ -f ${STEPUP_QUEUE_FLAG_DIR}/resubmit ]; then
    echo "Resubmitting job script to let StepUp finalize the workflow."
    sbatch workflow.sh
else
    echo "Stepup was stopped gracefully."
fi
