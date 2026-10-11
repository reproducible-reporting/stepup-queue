#!/usr/bin/env bash
#SBATCH --job-name parts
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time={{ minutes }}

# Compute all parts that do not exist yet.
# Parts completed by a previous job are skipped,
# so that this job can be resubmitted after more parts were added.
NUM_PARTS={{ num_parts }}
for ((i = 0; i < NUM_PARTS; i++)); do
    if [[ -f "part${i}.txt" ]]; then
        echo "Skipping part ${i}"
        continue
    fi
    echo "Computing part ${i}"
    sleep 5
    # The output is renamed at the end, so that an interrupted part is not mistaken as complete.
    echo "Result of part ${i}" > "part${i}.txt.tmp"
    mv "part${i}.txt.tmp" "part${i}.txt"
done
