# Run text2schema on Compute Canada Fir

[run_fir.slurm](run_fir.slurm) runs the pipeline on one full 80 GB H100. It starts Ollama on the allocated node and runs these models in order, one at a time. [Fir GPU documentation](https://ualberta-rcg.github.io/ragflow-wiki-data/base/software/fir/#gpu-instances)

1. `qwen3.8:27b-q8_0`
2. `qwen3.5:9b-q4_K_M`
3. `qwen3.5:4b-q4_K_M`

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

Check that `run_fir.slurm` is in the clone. If your copy of the script is still local, run this from the project root on your computer to transfer it to Fir.

```bash
scp run_fir.slurm YOUR_FIR_USERNAME@fir.alliancecan.ca:scratch/text2schema/
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

Set `debug=true` in `.env` for the first job. Set it back to `debug=false` before submitting the full run. The example configuration points to the 375-record cleaned RSchema dataset and the two prompt files included in the clone. It allows up to three schema proposals per record and sets a 300-second timeout per model request. [Example configuration](.env.example) · [Pipeline documentation](pipeline/README.md)

Leave the API key blank. `run_fir.slurm` supplies the Ollama backend, the model tag for each run, and the loopback endpoint. The job reads the dataset, prompts, retry limit, timeout, and debug setting from `.env`.

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

The check should print `$HOME/.local/ollama/bin/ollama` with your actual home directory. Future Bash logins pick up this path, and `run_fir.slurm` can find Ollama by name.

Allow more than 40 GB of free scratch space for the model cache. The job pulls missing models on the compute node and reuses the files in `$SCRATCH/ollama-models`. It sets an 8,192-token context by default. [Fir compute-node access and storage](https://ualberta-rcg.github.io/ragflow-wiki-data/base/software/fir/) · [Qwen 3.8 download size](https://ollama.com/library/qwen3.8:27b-q8_0) · [Qwen 3.5 download sizes](https://ollama.com/library/qwen3.5/tags)

## 5. Submit the job from the project root

Replace `YOUR_FIR_GPU_ACCOUNT` with the Slurm account for your Fir GPU project. To see your account associations, run `sshare -U -u "$USER" -P -o Account,User`. The project group name is also listed in CCDB under **My Projects → My Resources and Allocations**. [Alliance Slurm account guide](https://ualberta-rcg.github.io/ragflow-wiki-data/base/running-jobs/running_jobs/#accounts-and-projects)

For the first debug run, use `debug=true` and request four hours. Debug mode runs up to three specifications per model. Across all three models, the pipeline can make up to 36 requests. If each takes close to five minutes, that uses about three hours, leaving time for server startup and downloads.

```bash
cd "$SCRATCH/text2schema"
sbatch --account=YOUR_FIR_GPU_ACCOUNT --time=04:00:00 run_fir.slurm
```

For the full run, set `debug=false` and submit using the script's default three-day wall time. You can override it with `--time` if needed.

```bash
sbatch --account=YOUR_FIR_GPU_ACCOUNT run_fir.slurm
```

## 6. Check logs and results

Replace `JOB_ID` with the ID printed by `sbatch`. The log files are created in the project root once the job starts. [Slurm job accounting](https://slurm.schedmd.com/sacct.html)

```bash
squeue -j JOB_ID
tail -f text2schema-qwen-JOB_ID.log
```

Read `ollama-JOB_ID.log` in the same directory for Ollama startup and inference details. Press **Ctrl+C** to stop following the log, then check the job state.

```bash
sacct -j JOB_ID --format=JobID,State,ExitCode,Elapsed
```

Each completed model publishes `results.csv` and `extraction_results.csv` under its own directory in `pipeline/results/`. Debug jobs use `pipeline/results/debug/`. The launcher replaces the colon in a model tag with a hyphen and adds a numeric suffix on repeat runs. A model can complete with unverified records or per-record errors. The job continues to the next model, and the CSVs record those outcomes. [Pipeline results guide](pipeline/README.md#read-the-results)

A model download failure or a fatal pipeline failure makes the job exit with status `2` after it attempts the remaining models. Check the job log for the affected model.

## 7. Download the results to your computer

After the job finishes, run these commands on Fir to create a ZIP of the entire `pipeline/results/` folder. The command prints the archive filename when it finishes.

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
