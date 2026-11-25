# How the text-to-schema pipeline works

`run_pipeline.py` reads its input path, prompt paths, and default model settings from the root `.env`. Run it with `python run_pipeline.py` and add terminal flags for any model settings you want to override. The configured input is UTF-8 JSONL, with one database specification per record. By default, the `question` field supplies the specification and `id` supplies the report ID. When the ID is missing, the ID uses the physical input line number, such as `line-3`. [Batch setup](README.md)

## Debug mode

Set `debug=true` in `.env` to process up to three valid specifications. The default `debug=false` runs the full batch, and the values `true` and `false` are case-insensitive.

The launcher scans the input and counts whitespace-separated words in each valid specification using `len(specification.split())`. It uses the field named by `PIPELINE_SPEC_FIELD` and skips malformed records and rows without a nonblank specification string. It selects the longest specification first and then the shortest from the remaining records, using the earliest input line for ties. It sorts the remaining records by word count and input line number and takes the middle record. If two records fall in the middle, it chooses the second in that order. With just one or two valid specifications, it processes each once. If the input has no valid specifications, the launcher reports an error.

Each selected record uses the configured model and schema proposal limit. The launcher saves both CSVs in `pipeline/results/debug/<model-name>/`, adding `-1`, `-2`, and later suffixes to the model folder name as needed for repeat debug runs.

## From specification to SQL

The pipeline is based on the workflow in Figure 1 of the project proposal. [Project proposal](../formal_verification_guided_text2schema.pdf)

1. The extraction prompt asks the model for one JSON object with `attribute_types` and `functional_dependencies`. `attribute_types` lists each attribute with its SQLite type. The pipeline derives the attribute list from those keys, including attributes absent from all functional dependencies (FDs). It validates the types and FD syntax before asking for a schema. If a dependency has an empty right-hand side, extraction validates the left-hand side and omits the dependency from the parsed list. Each specification has one extraction stage. [Extraction prompt](prompts/extract_fds_attributes_and_types_prompt.txt)
2. The schema prompt asks the model to construct relations over the extracted attributes using the FDs. The user message carries the original specification, attribute names, and FDs. Each revision also receives `attempt_history`, an ordered list of all completed proposals for that specification, with the latest proposal last. Each entry pairs its `iteration` and `relational_schema` with the `feedback` from evaluating that proposal. The extracted names and FDs stay fixed across attempts. The response uses one relation declaration per line and `<u>` tags around every column of a declared primary key. [Schema prompt](prompts/generate_relational_schema_prompt.txt)
3. The pipeline parses each proposal and uses the extracted types to generate SQLite `CREATE TABLE` statements for its relations. It can generate SQL for a proposal that omits an expected attribute if all the columns it declares have extracted types. Malformed proposals, attributes without extracted types, and invalid SQLite identifiers yield feedback and an empty query list. [CREATE query generator guide](../create_query_generator/README.md)
4. For proposals that contain exactly the extracted attributes, the verifier checks 2NF, 3NF, lossless decomposition, and dependency preservation under the extracted FDs. When verification and SQL generation succeed, the pipeline records `verified` and finishes that record. After a rejection, it matches relations by name and compares each relation's attribute set and declared primary-key columns. The comparison ignores relation order, attribute order, whitespace, and outer Markdown fences. A schema change or parse error breaks the streak. On the third consecutive matching rejection, the pipeline records the proposal's feedback and `early-stop`, even if that proposal reaches the iteration limit. Other rejections supply feedback to the next attempt or receive `exhausted` at the limit. The default `PIPELINE_MAX_ITERATIONS=3` includes the first proposal. [Verifier guide](../verifier/README.md)

Malformed input, invalid extraction, and individual model request failures are recorded against the affected record. The pipeline continues processing the other records. The formal checks apply to the extracted attributes and FDs.

### Provider Batch API jobs

Hosted OpenAI and Gemini use their Batch APIs on their native endpoints. Custom endpoints use standard requests. The launcher takes up to 1,000 selected input records at a time and completes all rounds for that group before starting the next group. Each valid record gets a separate request, and the launcher writes one request per line in a JSONL file for the selected provider.

1. **Extraction.** Each request contains the extraction instructions and that record's specification text, taken from `question` by default. The launcher waits for the results and validates each extraction.
2. **First schema proposal.** For each successful extraction, the launcher sends the schema instructions, the original specification, and the extracted attribute names and functional dependencies. It verifies each returned proposal locally.
3. **Revisions.** Only records that need another attempt enter the next round. Each revision request includes that record's previous proposals and their feedback in order. The launcher waits for the results of each round before building the next round's requests.

Suppose three records, A, B, and C, all pass extraction. The first job contains **three extraction requests** and the second contains **three schema requests**. If A and B verify on their first proposals and C needs a revision, the third job contains **one revision request**, for C, with C's first proposal and its feedback. If C then verifies, the group is complete.

OpenAI receives the JSONL through its Files API and runs a Batch job of Chat Completions requests. Gemini receives a Gemini-formatted JSONL file and runs a `batchGenerateContent` job. The launcher polls the job, downloads the results, and matches each result by a key based on the physical source line, such as `line-42`. This matches results correctly even when they arrive out of order or multiple source records share the same dataset `id`. [OpenAI Batch API](https://developers.openai.com/api/docs/guides/batch) · [Gemini Batch API](https://ai.google.dev/gemini-api/docs/batch-api)

The launcher polls active jobs every 30 seconds and logs their job IDs and status changes. `PIPELINE_BATCH_TIMEOUT_SECONDS` or `--batch-timeout-seconds` sets the wait limit per job, with a default of 49 hours (176,400 seconds). `PIPELINE_TIMEOUT_SECONDS` bounds each HTTP request, and `PIPELINE_REQUEST_DELAY_SECONDS` sets the minimum pause between jobs. Keep the launcher running through the final round to collect results and publish both CSVs. If it stops while a job is active, the provider can keep processing that job. Use the logged ID to check its status.

### Hosted HTTP 503 retries

The hosted client retries standard extraction and schema requests and batch status checks and result downloads that return HTTP 503. The default allows two additional attempts per request. Set `PIPELINE_HOSTED_503_RETRIES` in `.env` or pass `--hosted-503-retries` with a nonnegative integer. A value of `0` disables these retries.

Each standard request retry sends the same prompt for the same stage and iteration. The wait uses exponential backoff with jitter and respects `PIPELINE_REQUEST_DELAY_SECONDS`. Batch retries read the same provider job or result file. Job creation runs once per submitted batch because repeating a creation request could create a second paid job. The launcher reports failed 503 requests in the live progress log and gives the wait time before each retry.

## CSV reports

The launcher writes `results.csv` and `extraction_results.csv` into a new directory based on the selected model. For example, full runs with `openai/gpt-4o-mini` use `pipeline/results/openai-gpt-4o-mini/`, followed by directories with `-1`, `-2`, and later suffixes as needed. [Results locations](README.md#read-the-results)

Both reports list full runs in input order and debug runs in longest, shortest, and middle selection order. Use `spec_id` and `input_line` together to identify the source record, including when IDs repeat. Unavailable values leave empty cells. Times are wall-clock seconds. A step that starts and fails still has a duration. Skipped steps and malformed input rows have blank timing cells.

### Batch results

`results.csv` has one extraction row per valid input record and one schema row per proposal attempted. It also records input errors.

| Column | Description |
| --- | --- |
| `spec_id` | Nonblank text or integer from the configured ID field, `id` by default. The fallback is `line-N`, where `N` is the physical input line number. |
| `input_line` | One-based line number in the source JSONL file, counting blank lines. |
| `stage` | `input` for a malformed input record, `extraction` for attribute, type, and FD extraction, or `schema` for a schema proposal attempt. |
| `iteration` | `0` for extraction. Schema attempts start at `1`. Input errors have a blank iteration. |
| `status` | `extracted` means extraction succeeded. `rejected` means another proposal will be requested. `exhausted` means a rejection reached the iteration limit without meeting the early-stop condition. `early-stop` marks the third consecutive rejection with matching relation names, attributes per relation, and declared primary keys. `verified` means a proposal passed verification and produced SQL. `error` means input, extraction, model, or solver processing failed for the record. |
| `database_specification` | Original natural-language specification from the configured specification field, `question` by default. Populated on extraction rows. |
| `prompt` | JSON array of the exact system and user messages passed to the model client. A revision prompt includes earlier proposals and their feedback in `attempt_history`. |
| `model_response` | Original assistant response text, including any Markdown code fences. |
| `input_tokens` | Number of tokens sent to the model for the schema request, when available. |
| `output_tokens` | Number of tokens generated by the model for the schema request, when available. |
| `total_tokens` | Total token count for the schema request. Uses the reported total or the sum of the available input and output counts when both are present. |
| `attributes` | JSON array of extracted attribute names, including names that appear in no FD. Populated on successful extraction rows. |
| `attribute_types` | JSON object mapping each extracted attribute name to its normalized SQLite type declaration. Populated on successful extraction rows. |
| `functional_dependencies` | JSON array of validated FD strings such as `[A] -> [B]`. The pipeline omits dependencies with an empty right-hand side. Populated on successful extraction rows. |
| `relational_schema` | Schema proposal text after removing surrounding whitespace and any outer Markdown code fence. Primary key columns use literal `<u>` tags. |
| `feedback` | Input, extraction, model, schema validation, SQL generation, or solver error details, or the verifier's success or violation messages. |
| `verification` | JSON report with `verified`, `checks`, and `feedback`. The `checks` record pass status and violations for 2NF, 3NF, lossless decomposition, and dependency preservation. Blank if the verifier returned no report. |
| `create_queries` | JSON array of generated SQLite `CREATE TABLE` statements, retained even if verification fails. `[]` means the evaluated proposal yielded no SQL. A blank cell means no query list was recorded. |
| `elapsed_seconds` | Full extraction stage or schema attempt, from starting the model request to recording the outcome. |
| `llm_seconds` | Time spent requesting the extraction or schema from the model, including request delays, HTTP 503 retries, and any wait for a shared provider batch job. |
| `schema_validation_seconds` | Time spent parsing the proposed schema and checking whether it covers the extracted attributes. |
| `ddl_generation_seconds` | Time spent in the SQLite `CREATE TABLE` query generator. |
| `verification_seconds` | Time spent in the formal verifier on that schema attempt. |
| `pipeline_total_seconds` | Total time per specification, from building the extraction prompt to the final outcome, including every attempt. Recorded on the specification's last row before final CSV publication. |

### Extraction results

`extraction_results.csv` records one row per extraction attempt, including failed attempts. Its timing values match the corresponding extraction rows in `results.csv`.

| Column | Description |
| --- | --- |
| `spec_id` | Nonblank text or integer from the configured ID field, `id` by default. The fallback is `line-N`, where `N` is the physical input line number. |
| `input_line` | One-based line number in the source JSONL file, counting blank lines. |
| `status` | `extracted` if the model output passed extraction validation, or `error` if the model request or extraction failed. |
| `database_specification` | Original natural-language specification from the configured specification field, `question` by default. |
| `prompt` | JSON array of the exact system and user messages passed to the model client for extraction. |
| `model_response` | Original assistant response text, including any Markdown code fences. |
| `input_tokens` | Number of tokens sent to the model for the extraction request, when available. |
| `output_tokens` | Number of tokens generated by the model for the extraction request, when available. |
| `total_tokens` | Total token count for the extraction request. Uses the reported total or the sum of the available input and output counts when both are present. |
| `attributes` | JSON array of extracted attribute names, including names that appear in no FD. |
| `attribute_types` | JSON object mapping each extracted attribute name to its normalized SQLite type declaration. |
| `functional_dependencies` | JSON array of validated FD strings such as `[A] -> [B]`. The pipeline omits dependencies with an empty right-hand side. |
| `feedback` | Details of a model request or extraction error. Blank on successful extraction. |
| `elapsed_seconds` | Full extraction stage, from starting the model request through parsing and validating its response or recording an error. |
| `llm_seconds` | Time spent requesting the extraction from the model, including request delays, HTTP 503 retries, and any wait for a shared provider batch job. |

OpenAI batch results use `prompt_tokens` and `completion_tokens` for input and output counts. Gemini batch results use `promptTokenCount` for input and include reported thinking tokens in the output count. Ollama uses `prompt_eval_count` and `eval_count`. Standard hosted requests use the original usage fields when LiteLLM exposes an OpenAI-format response and LiteLLM's normalized usage otherwise. Missing counters remain blank when the backend exposes them as missing. [LiteLLM response format](https://docs.litellm.ai/docs/learn/python_sdk_quickstart) · [Ollama chat response](https://docs.ollama.com/api/chat)

The batch stages both reports in their destination directories and finishes serializing them before publishing either. It replaces the extraction report first and the batch results second, with each replacement atomic. Setup or serialization errors preserve the previous reports. If replacing the batch results fails, the batch rolls back the extraction replacement.

## Call from Python

```python
from pipeline.llm import LLMClient
from pipeline.run import run_pipeline

spec = "Each employee has a unique integer ID and a full name."
client = LLMClient("qwen3:8b", backend="ollama")
result = run_pipeline(spec, client, max_iterations=3)

for attempt in result["attempts"]:
    print(f"Iteration {attempt['iteration']}")
    print(attempt["feedback"])
    for query in attempt["create_queries"]:
        print(query)
```

Each entry in `attempts` records the iteration, proposed schema, feedback, verification report, and `create_queries` list. The top-level result includes the extracted `attribute_types` and `functional_dependencies`, along with the final proposal's `relational_schema`, `create_queries`, and `feedback`. Its `status` is `verified`, `exhausted`, or `early-stop`. The top-level `verified` is true when the final proposal passes verification and produces SQL. The verification report is `None` when parsing or attribute coverage rejects a proposal before the formal checks. Invalid extraction raises `ExtractionError` before schema generation starts.

With a hosted OpenAI or Gemini client on its native endpoint, `run_pipeline` submits one provider job per stage for the single specification. Use `pipeline.batch.run_batch` to group requests from multiple specifications in a JSONL file.
