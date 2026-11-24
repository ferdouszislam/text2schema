#!/bin/bash -l
#SBATCH --job-name=text2schema-qwen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=h100:1
#SBATCH --mem=48G
#SBATCH --time=1-00:00:00
#SBATCH --array=0-7%4
#SBATCH --output=%x-%A_%a.log

set -euo pipefail

# Interleave the two models within each of the four input chunks.
task_id=${SLURM_ARRAY_TASK_ID:-}
if [[ ! $task_id =~ ^[0-7]$ ]]; then
    echo 'Expected a Slurm array task ID from 0 to 7.' >&2
    exit 2
fi
models=('qwen3.5:35b-a3b-q8_0' 'qwen3.8:27b-q8_0')
model=${models[$((task_id % 2))]}
chunk_index=$((task_id / 2))

cd "${SLURM_SUBMIT_DIR:?Submit this script with sbatch from the project root.}"
source ./fir_slurm_shared.sh "$model" "$chunk_index"
