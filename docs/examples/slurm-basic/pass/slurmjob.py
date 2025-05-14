#!/usr/bin/env python3
#SBATCH --job-name pass
#SBATCH --nodes=1
#SBATCH --num-tasks=1
#SBATCH --cpus-per-task=1

from time import sleep

print("Hello from static job")
sleep(5)
print("Goodbye from static job")
