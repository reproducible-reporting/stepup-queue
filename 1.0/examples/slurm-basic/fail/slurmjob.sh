#!/usr/bin/env bash
#SBATCH --job-name fail
#SBATCH --nodes=1
#SBATCH --num-tasks=1
#SBATCH --cpus-per-task=1

echo "This job will fail"
exit 1
