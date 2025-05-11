#!/usr/bin/env bash
#SBATCH -J 'dynamic {{ field }}'
#SBATCH -N 1

echo "Hello from dynamic job {{ field }}"
sleep 5
echo "Goodbye from dynamic job {{ field }}"
