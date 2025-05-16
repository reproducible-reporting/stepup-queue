#!/usr/bin/env bash
#SBATCH --job-name 'dyn{{ field }}'
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1

echo "Hello from dynamic job {{ field }}"
sleep 5
echo "Goodbye from dynamic job {{ field }}"
