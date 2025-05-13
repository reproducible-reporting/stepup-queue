#!/usr/bin/env python3
# SBATCH -J static
# SBATCH -N 1

from time import sleep

print("Hello from static job")
sleep(5)
print("Goodbye from static job")
