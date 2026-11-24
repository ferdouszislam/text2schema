#!/bin/bash -l
#SBATCH --job-name=text2schema-qwen-9b
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=h100:1
#SBATCH --mem=48G
#SBATCH --time=3-00:00:00
#SBATCH --array=0-3%4
#SBATCH --output=%x-%A_%a.log

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:?Submit this script with sbatch from the project root.}"
source ./fir_slurm_shared.sh 'qwen3.5:9b-q4_K_M' "${SLURM_ARRAY_TASK_ID:-}"
