#!/usr/bin/env bash
#SBATCH -J fail
#SBATCH -N 1

echo "This job will fail"
exit 1
