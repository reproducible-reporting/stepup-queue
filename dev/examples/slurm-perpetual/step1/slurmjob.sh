#!/usr/bin/env bash
#SBATCH --job-name step1
#SBATCH --nodes=1
#SBATCH --num-tasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:02:00

# Give the CPU a break...
sleep 30
echo Done > ../intermediate.txt
