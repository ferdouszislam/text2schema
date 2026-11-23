#!/bin/bash -l
#SBATCH --job-name=text2schema-qwen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=h100:1
#SBATCH --mem=48G
#SBATCH --time=3-00:00:00
#SBATCH --output=%x-%j.log

set -euo pipefail

# Submit from the text2schema project root with sbatch --account=YOUR_ACCOUNT.
cd "${SLURM_SUBMIT_DIR:?Submit this script with sbatch from the project root.}"
if [[ ! -f .env || ! -f run_pipeline.py || ! -x .venv/bin/python ]]; then
    echo 'The project root on Fir needs run_pipeline.py, .env, and a Fir-built .venv.' >&2
    exit 2
fi
module load StdEnv/2023 "${PYTHON_MODULE:-python/3.12}"
if ! .venv/bin/python -c 'import run_pipeline'; then
    echo 'Set up the project Python dependencies in .venv on Fir first.' >&2
    exit 2
fi

ollama_bin=${OLLAMA_BIN:-ollama}
if ! command -v "$ollama_bin" >/dev/null; then
    echo 'Put Ollama on PATH or set OLLAMA_BIN to its executable on Fir.' >&2
    exit 2
fi

models=(
    'qwen3.5:35b-a3b-q8_0'
    'qwen3.8:27b-q8_0'
    'qwen3.5:9b-q4_K_M'
)

export OLLAMA_MODELS="${OLLAMA_MODELS:-${SCRATCH:?Set SCRATCH or OLLAMA_MODELS.}/ollama-models}"
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-32768}"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_HOST="127.0.0.1:$((20000 + SLURM_JOB_ID % 40000))"
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}${no_proxy:+,$no_proxy}"
export no_proxy="$NO_PROXY"
mkdir -p "$OLLAMA_MODELS"

api_base="http://$OLLAMA_HOST"
ollama_log="ollama-${SLURM_JOB_ID}.log"
ollama_ready() {
    curl --noproxy '*' --fail --silent --max-time 2 "$api_base/api/version" >/dev/null
}

if ollama_ready; then
    echo "An Ollama server is already listening at $OLLAMA_HOST." >&2
    exit 2
fi
"$ollama_bin" serve >"$ollama_log" 2>&1 &
ollama_pid=$!
trap 'kill "$ollama_pid" 2>/dev/null || true; wait "$ollama_pid" 2>/dev/null || true' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

for attempt in {1..60}; do
    if ! kill -0 "$ollama_pid" 2>/dev/null || ollama_ready; then
        break
    fi
    sleep 1
done
if ! kill -0 "$ollama_pid" 2>/dev/null || ! ollama_ready; then
    echo "Ollama failed to start at $OLLAMA_HOST. See $ollama_log." >&2
    exit 2
fi

job_status=0
for model in "${models[@]}"; do
    if ! "$ollama_bin" show "$model" >/dev/null 2>&1; then
        if ! "$ollama_bin" pull "$model"; then
            echo "Could not download $model." >&2
            job_status=2
            continue
        fi
    fi

    printf '[%s] Running %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$model"
    if .venv/bin/python -u run_pipeline.py --backend ollama --model "$model" \
        --api-base "$api_base" --api-key ""; then
        echo "Finished $model. All records verified."
    else
        pipeline_status=$?
        if [[ $pipeline_status -eq 1 ]]; then
            echo "Finished $model. See the CSVs for unverified records and errors."
        else
            echo "The pipeline failed for $model (exit $pipeline_status)." >&2
            job_status=2
        fi
    fi
done
exit "$job_status"
