# Run text2schema on Compute Canada Fir

Each Qwen model has its own Slurm script and runs in four chunks. Each task starts its own Ollama server on one full 80 GB H100. [Fir GPU documentation](https://ualberta-rcg.github.io/ragflow-wiki-data/base/software/fir/#gpu-instances)

| Model | Slurm script | Wall time per task |
| --- | --- | --- |
| `qwen3.8:27b-q8_0` | [run_fir_qwen_27b.slurm](run_fir_qwen_27b.slurm) | 24 hours |
| `qwen3.5:35b-a3b-q8_0` | [run_fir_qwen_35b.slurm](run_fir_qwen_35b.slurm) | 24 hours |
| `qwen3.5:9b-q4_K_M` | [run_fir_qwen_9b.slurm](run_fir_qwen_9b.slurm) | 72 hours |

## 1. Clone the project into Fir scratch

Replace `YOUR_FIR_USERNAME` with your Alliance login. Connect to Fir from your computer.

```bash
ssh YOUR_FIR_USERNAME@fir.alliancecan.ca
```

On the Fir login node, clone under your personal scratch directory.

```bash
cd "$SCRATCH"
git clone https://github.com/ferdouszislam/text2schema.git
cd text2schema
```

Use an up-to-date checkout on Fir. If the array changes are still local, run this from the project root on your computer to transfer the updated launchers and Python files to an existing Fir checkout.

```bash
fir_project=YOUR_FIR_USERNAME@fir.alliancecan.ca:scratch/text2schema
scp run_fir_qwen_27b.slurm run_fir_qwen_35b.slurm run_fir_qwen_9b.slurm \
    fir_slurm_shared.sh run_pipeline.py "$fir_project/"
scp pipeline/batch.py "$fir_project/pipeline/"
```

## 2. Create the Python environment on Fir

Use Python 3.12 to match the module loaded by the job. The two pins below come from [requirements.txt](requirements.txt) and cover the Ollama pipeline. [Alliance Python setup](https://ualberta-rcg.github.io/ragflow-wiki-data/en/software/python/)

```bash
cd "$SCRATCH/text2schema"
module load StdEnv/2023 python/3.12
virtualenv --no-download .venv
.venv/bin/python -m pip install 'python-dotenv==1.2.4' 'z3-solver==4.15.4.0'
.venv/bin/python -c 'import run_pipeline'
```

The import check should finish silently. Use `.venv/bin/python -m pip install -r requirements.txt` if you also need the hosted backend and plotting tools on Fir.

## 3. Create the pipeline configuration

```bash
test -f .env || cp .env.example .env
nano .env
```

Set `debug=false` in `.env` before submitting the arrays. The example configuration points to the 375-record cleaned RSchema dataset and the two prompt files included in the clone. It allows up to three schema proposals per record and sets a 300-second timeout per model request. [Example configuration](.env.example) · [Pipeline documentation](pipeline/README.md)

The scripts supply the Ollama backend, model tag, and loopback endpoint. Each task reads the rest of the configuration from `.env` when it starts. Keep the checkout, input dataset, `.env`, and prompts fixed while tasks are queued or running so every task uses the same inputs and range boundaries.

All three Fir Qwen models run with thinking disabled by default (`PIPELINE_QWEN_THINKING=false`). Set `PIPELINE_QWEN_THINKING=true` in the project's `.env` on Fir to enable thinking for extraction and every schema proposal. For example, a 27B task with thinking enabled covering records 1–94 writes to `pipeline/results/qwen3.8-27b-q8_0-te-1_94/`.

## 4. Find or install Ollama on Fir

Check for an executable with `command -v ollama`. If that returns a path, check its version with `ollama --version`. You can also use `module spider ollama` to check for a cluster module. Load the module before submission if you use it.

If you need a personal installation, extract the Linux AMD64 archive into your home directory. This command uses `curl`, GNU `tar`, and `zstd`. Paste the whole block into your Fir terminal. [Ollama Linux installation](https://docs.ollama.com/linux#manual-install)

```bash
mkdir -p "$HOME/.local/ollama"
(
    set -o pipefail
    curl -fL https://ollama.com/download/ollama-linux-amd64.tar.zst |
        tar --zstd -xf - -C "$HOME/.local/ollama"
)
export OLLAMA_BIN="$HOME/.local/ollama/bin/ollama"
"$OLLAMA_BIN" --version
```

A client version confirms that the executable runs. A server connection warning is expected when checking from the login node. The `OLLAMA_BIN` export above applies to the current login session.

### Make Ollama available in future logins

The archive installs Ollama in `$HOME/.local/ollama/bin`. Bash searches the directories in `PATH` when you run `command -v ollama`. On Fir, edit `~/.bash_profile` and prepend `$HOME/.local/ollama/bin` to the existing `PATH` assignment below the `.bashrc` block. If your profile already adds `$HOME/.local/bin` and `$HOME/bin`, the bottom of the file should read like this.

```bash
PATH="$HOME/.local/ollama/bin:$PATH:$HOME/.local/bin:$HOME/bin"
export PATH
```

Reload the profile and check that Bash finds the executable.

```bash
source ~/.bash_profile
command -v ollama
```

The check should print `$HOME/.local/ollama/bin/ollama` with your actual home directory. Future Bash logins pick up this path, and all three Slurm scripts can find Ollama by name.

Allow at least 85 GB of free scratch space for a fresh model cache. The three downloads total about 76 GB. Tasks reuse `$SCRATCH/ollama-models` by default. If models are missing, tasks download them on the compute nodes one at a time under a shared cache lock. [Fir compute-node access and storage](https://ualberta-rcg.github.io/ragflow-wiki-data/base/software/fir/) · [Qwen 3.8 download size](https://ollama.com/library/qwen3.8:27b-q8_0) · [Qwen 3.5 download sizes](https://ollama.com/library/qwen3.5/tags)

Each task sets a 32,768-token (32K) context by default. Set `OLLAMA_CONTEXT_LENGTH` in the submission environment to override it. [Ollama context settings](https://docs.ollama.com/context-length)

## 5. Submit the arrays from the project root

Replace `YOUR_FIR_GPU_ACCOUNT` with the Slurm account for your Fir GPU project. To see your account associations, run `sshare -U -u "$USER" -P -o Account,User`. The project group name is also listed in CCDB under **My Projects → My Resources and Allocations**. [Alliance Slurm account guide](https://ualberta-rcg.github.io/ragflow-wiki-data/base/running-jobs/running_jobs/#accounts-and-projects)

Run the `sbatch` command for each model you want to queue. Each array can run up to four tasks at once. If you submit all three arrays, up to 12 tasks can run concurrently, subject to Fir capacity and your account limits. [Slurm job arrays](https://slurm.schedmd.com/job_array.html)

```bash
cd "$SCRATCH/text2schema"
sbatch --account=YOUR_FIR_GPU_ACCOUNT run_fir_qwen_27b.slurm
sbatch --account=YOUR_FIR_GPU_ACCOUNT run_fir_qwen_35b.slurm
sbatch --account=YOUR_FIR_GPU_ACCOUNT run_fir_qwen_9b.slurm
```

Each array uses the same task IDs and computes four balanced chunks from the nonblank records in the configured JSONL. The default dataset uses these inclusive ranges.

| Task ID | Records |
| --- | --- |
| 0 | 1–94 |
| 1 | 95–188 |
| 2 | 189–282 |
| 3 | 283–375 |

To rerun a chunk, find its record range in the table and pass the corresponding task ID to the model's script with `--array`. This example reruns records 95–188 for the 27B on the default dataset.

```bash
sbatch --account=YOUR_FIR_GPU_ACCOUNT --array=1 run_fir_qwen_27b.slurm
```

## 6. Check logs and results

Set `array_job_id` to the ID printed by `sbatch` for the model you want to monitor. Use `27b`, `35b`, or `9b` for `model` and the chunk's task ID for `task_id`. The log files appear in the project root as tasks start. This example follows task `0` for the 27B. [Slurm job accounting](https://slurm.schedmd.com/sacct.html)

```bash
array_job_id=ARRAY_JOB_ID
model=27b
task_id=0
squeue --array -j "$array_job_id"
tail -f "text2schema-qwen-${model}-${array_job_id}_${task_id}.log"
```

Each task logs its model, record range, and separate Ollama log at startup. Press **Ctrl+C** to stop following the log, then check the task states.

```bash
sacct -j "$array_job_id" --format=JobID,State,ExitCode,Elapsed
```

Each completed task publishes `results.csv` and `extraction_results.csv` in its own directory, such as `pipeline/results/qwen3.8-27b-q8_0-1_94/`. The reports retain the original input IDs and line numbers. A repeated range gets a run counter before the range suffix. A task can finish with unverified records or per-record errors, so check both CSVs. A model download failure or a fatal pipeline error fails that task. [Pipeline results guide](pipeline/README.md#read-the-results)

## 7. Download the results to your computer

After the arrays you submitted finish, run these commands on Fir to create a ZIP of the entire `pipeline/results/` folder. The command prints the archive filename when it finishes.

```bash
cd "$SCRATCH/text2schema"
archive="text2schema-results-$(date +%Y%m%d-%H%M%S).zip"
zip -r "$archive" pipeline/results && printf '%s\n' "$archive"
```

In a terminal on your computer, go to the directory where you want to save the results. Replace `ARCHIVE_NAME.zip` with the filename printed on Fir and `YOUR_FIR_USERNAME` with your Alliance login.

```bash
archive=ARCHIVE_NAME.zip
scp "YOUR_FIR_USERNAME@fir.alliancecan.ca:scratch/text2schema/$archive" .
```

To extract the ZIP into a local folder named after the archive, run the following in the same terminal. The extracted folder contains `pipeline/results/`.

```bash
unzip "$archive" -d "${archive%.zip}"
```

Keep a local or backed-up copy of any results you need. Fir scratch files are subject to automatic purge. [Fir storage documentation](https://ualberta-rcg.github.io/ragflow-wiki-data/base/software/fir/#storage)
