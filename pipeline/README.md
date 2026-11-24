# Text-to-schema pipeline

The pipeline reads database specifications from JSONL, extracts facts, and revises proposed schemas using verification feedback. It generates SQLite `CREATE TABLE` statements for each proposal it can translate and records model prompts, responses, and token usage in two CSVs. [Pipeline explained](PIPELINE-EXPLAINED.md)

## Run the batch

From the project root, activate `.venv`, install the project requirements, and edit the root `.env`. Copy `.env.example` to `.env` if you need a starting file. The default input is the cleaned RSchema JSONL. The `.env` file is ignored by Git. [Project setup](../README.md) · [Example configuration](../.env.example)

```bash
python run_pipeline.py
```

The script prints the batch counts. Exit status `0` means every record verified, `1` means at least one record was exhausted or had an error, and `2` means setup or the batch itself failed.

### Override model settings for one run

Each flag overrides its matching `.env` setting for that run. Omitted flags use the values from `.env`.

```bash
python run_pipeline.py --backend ollama --model qwen3:8b --timeout-seconds 60 --max-iterations 2
```

Pass `--api-key ""` or `--api-base ""` to clear a configured key or endpoint. Run `python run_pipeline.py --help` to list the available flags.

### Debug with up to three records

Set `debug=true` in the root `.env` and run the same command.

```bash
python run_pipeline.py
```

Debug mode runs the longest, shortest, and middle valid specifications by word count, in that order, using the configured model and retry limit. If only one or two valid specifications are available, it runs each once. It saves both CSVs under `pipeline/results/debug/<model-name>/`. [Debug mode details](PIPELINE-EXPLAINED.md#debug-mode)

The input is UTF-8 JSONL with one JSON object per line. The default fields match the cleaned RSchema records. `question` holds the specification and `id` identifies the record in the results.

```json
{"id": "employee-example", "question": "Each employee has a unique integer ID and a full name."}
```

| `.env` setting | Terminal flag | Purpose |
| --- | --- | --- |
| `debug` | | Use `false` for the full batch or `true` for up to three valid specifications selected by word count. Defaults to `false`. |
| `PIPELINE_INPUT_JSONL` | | Input dataset. |
| `PIPELINE_SPEC_FIELD`, `PIPELINE_ID_FIELD` | | Keys for the specification and record ID. The defaults are `question` and `id`. |
| `PIPELINE_BACKEND` | `--backend` | Select `ollama` or `hosted`. |
| `PIPELINE_MODEL` | `--model` | Set an installed Ollama model tag or a LiteLLM `provider/model` name. |
| `PIPELINE_API_KEY` | `--api-key` | Supply an API key when needed. |
| `PIPELINE_API_BASE` | `--api-base` | Override the model endpoint. |
| `PIPELINE_TIMEOUT_SECONDS` | `--timeout-seconds` | Set the model request timeout in seconds. |
| `PIPELINE_REQUEST_DELAY_SECONDS` | | Set the minimum pause between model requests in seconds. Defaults to `3`. Set `0` to disable the pause. |
| `PIPELINE_MAX_ITERATIONS` | `--max-iterations` | Set the total proposal limit per specification. |
| `PIPELINE_EXTRACTION_PROMPT`, `PIPELINE_SCHEMA_PROMPT` | | Select the editable prompt files. |

Relative paths are resolved from the project root.

The first model request starts immediately. The delay runs from the end of a request, including a failed request, to the start of the next request in the batch. Both backends accept finite, nonnegative values in seconds, including fractional values.

For the default Ollama configuration, start the server and run `ollama pull qwen3:8b`. The default endpoint is `http://127.0.0.1:11434`. For a hosted model, set `PIPELINE_BACKEND=hosted`, choose a model such as `openai/gpt-4o-mini`, and supply its credentials. For a custom OpenAI-compatible endpoint, use `openai/<model>` and set `PIPELINE_API_BASE` to the endpoint base URL. [Ollama API](https://docs.ollama.com/api/chat) · [LiteLLM providers and credentials](https://docs.litellm.ai/docs/providers) · [OpenAI-compatible endpoints](https://docs.litellm.ai/docs/providers/openai_compatible)

Edit the selected prompt files to change the model instructions. The pipeline fills `{{SUPPORTED_TYPES}}` in the extraction prompt with the generator's supported SQLite type names. [Extraction prompt](prompts/extract_fds_attributes_and_types_prompt.txt) · [Schema prompt](prompts/generate_relational_schema_prompt.txt)

## Read the results

Full runs save both CSVs under `pipeline/results/<model-name>/`, replacing characters such as `/` and `:` in the selected model name with hyphens. For example, `qwen3:8b` first uses `pipeline/results/qwen3-8b/`. If that folder exists, the launcher tries `pipeline/results/qwen3-8b-1/`, `pipeline/results/qwen3-8b-2/`, and so on until it finds an unused name. Debug runs use their own numbered folders under `pipeline/results/debug/`.

For a model named `debug` in any capitalization, full runs start at suffix `-1` because `pipeline/results/debug/` holds debug runs.

- `results.csv` records extraction at iteration `0`, schema proposals from iteration `1` onward, and any record-level errors. Schema rows include reported token counts, verification feedback, and any generated SQL in `create_queries`, including for rejected and exhausted proposals.
- `extraction_results.csv` records extraction attempts, including the attribute names, SQLite types, FDs, and reported extraction token counts.

Use `spec_id` and `input_line` to match rows across the reports. Both files record `prompt` as a JSON array of chat messages and `model_response` as raw text. See the detailed guide for field definitions and the Python API. [Pipeline explained](PIPELINE-EXPLAINED.md)
