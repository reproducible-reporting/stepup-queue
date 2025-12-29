#!/usr/bin/env bash
#SBATCH --job-name step2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1

#SBATCH --time=00:02:00

# Give the CPU a break...
sleep 30
cat ../intermediate.txt
