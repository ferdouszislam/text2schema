#!/bin/bash
# Shared worker sourced by the per-model Fir Slurm launchers.

model=$1
chunk_index=$2
if [[ ! $chunk_index =~ ^[0-3]$ ]]; then
    echo 'Expected a Slurm chunk index from 0 to 3.' >&2
    exit 2
fi
if [[ ! -f .env || ! -f run_pipeline.py || ! -x .venv/bin/python ]]; then
    echo 'The project root on Fir needs run_pipeline.py, .env, and a Fir-built .venv.' >&2
    exit 2
fi
module load StdEnv/2023 "${PYTHON_MODULE:-python/3.12}"

if ! record_count=$(.venv/bin/python - <<'PY'
from run_pipeline import configured_input_record_count

try:
    print(configured_input_record_count())
except (OSError, ValueError) as error:
    raise SystemExit(str(error)) from None
PY
); then
    echo 'Could not read the configured input with the project Python environment on Fir.' >&2
    exit 2
fi
if (( record_count < 4 )); then
    echo "Expected at least four input records for four chunks. Found $record_count." >&2
    exit 2
fi

chunk_size=$((record_count / 4))
larger_chunks=$((record_count % 4))
earlier_extra_records=$((chunk_index < larger_chunks ? chunk_index : larger_chunks))
start_index=$((chunk_index * chunk_size + earlier_extra_records + 1))
end_index=$((start_index + chunk_size + (chunk_index < larger_chunks) - 1))

ollama_bin=${OLLAMA_BIN:-ollama}
if ! command -v "$ollama_bin" >/dev/null; then
    echo 'Put Ollama on PATH or set OLLAMA_BIN to its executable on Fir.' >&2
    exit 2
fi

export OLLAMA_MODELS="${OLLAMA_MODELS:-${SCRATCH:?Set SCRATCH or OLLAMA_MODELS.}/ollama-models}"
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-32768}"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
# Other jobs can be adding models to this shared cache while Ollama starts.
export OLLAMA_NOPRUNE=1
export OLLAMA_HOST="127.0.0.1:$((20000 + SLURM_JOB_ID % 40000))"
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}${no_proxy:+,$no_proxy}"
export no_proxy="$NO_PROXY"
mkdir -p "$OLLAMA_MODELS"

api_base="http://$OLLAMA_HOST"
ollama_log="ollama-${SLURM_JOB_ID}.log"
printf '[%s] Starting task for %s, records %d–%d of %d. Ollama log %s\n' \
    "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$model" "$start_index" "$end_index" "$record_count" "$ollama_log"
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

model_cached() {
    "$ollama_bin" show "$model" >/dev/null 2>&1
}

if ! model_cached; then
    echo "Waiting for the shared model download lock for $model."
    # A second task may have downloaded this model while this task waited.
    if ! (
        .venv/bin/python -c 'import fcntl
fcntl.flock(9, fcntl.LOCK_EX)' || exit 2
        model_cached || "$ollama_bin" pull "$model"
    ) 9>>"$OLLAMA_MODELS/.text2schema-pull.lock"; then
        echo "Could not download $model into the shared cache." >&2
        exit 2
    fi
fi

if .venv/bin/python -u run_pipeline.py --backend ollama --model "$model" \
    --api-base "$api_base" --api-key "" --start-index "$start_index" --end-index "$end_index"; then
    echo "Finished $model. All records verified."
else
    pipeline_status=$?
    if [[ $pipeline_status -eq 1 ]]; then
        echo "Finished $model. See the CSVs for unverified records and errors."
    else
        echo "The pipeline failed for $model (exit $pipeline_status)." >&2
        exit 2
    fi
fi
