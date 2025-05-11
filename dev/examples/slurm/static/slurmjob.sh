#!/usr/bin/env bash
#SBATCH -J static
#SBATCH -N 1

echo "Hello from static job"
sleep 5
echo "Goodbye from static job"
