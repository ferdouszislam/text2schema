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
4. For proposals that contain exactly the extracted attributes, the verifier checks 2NF, 3NF, lossless decomposition, and dependency preservation under the extracted FDs. When verification and SQL generation succeed, processing moves to the next record. After each rejection, the pipeline compares the raw model response and feedback with those of the previous proposal. If both match, it records `early-stop` on the second proposal and moves to the next record. Otherwise, the feedback goes to the next attempt, or the last proposal is marked `exhausted` when it reaches the limit. The default `PIPELINE_MAX_ITERATIONS=3` includes the first proposal. [Verifier guide](../verifier/README.md)

Malformed input, invalid extraction, and model call failures are recorded against the affected record. The batch continues processing subsequent records. The formal checks apply to the extracted attributes and FDs.

### Hosted HTTP 503 retries

The hosted client retries extraction and schema requests that return HTTP 503. The default allows two additional attempts per request. Set `PIPELINE_HOSTED_503_RETRIES` in `.env` or pass `--hosted-503-retries` with a nonnegative integer. A value of `0` disables these retries.

Each retry sends the same prompt for the same stage and iteration. The wait uses exponential backoff with jitter and respects `PIPELINE_REQUEST_DELAY_SECONDS`. The launcher reports failed 503 requests in the live progress log and gives the wait time before each retry. The CSVs record the eventual outcome for that stage and iteration, including reported token counts from the successful reply. If the retries are exhausted with HTTP 503, the row records an `error`.

## CSV reports

The launcher writes `results.csv` and `extraction_results.csv` into a new directory based on the selected model. For example, full runs with `openai/gpt-4o-mini` use `pipeline/results/openai-gpt-4o-mini/`, followed by directories with `-1`, `-2`, and later suffixes as needed. [Results locations](README.md#read-the-results)

Both reports follow processing order. Full batches process records in input order. Debug runs process the longest, shortest, and middle selections in that order. Use `spec_id` and `input_line` together to identify the source record, including when IDs repeat. In either report, `prompt` is a JSON array containing the exact system and user messages passed to the model client. `model_response` holds the original assistant text, including formatting such as Markdown fences if present. Unavailable values leave empty cells.

### Batch results

In `results.csv`, each valid record has an `extraction` row with iteration `0`, followed by one `schema` row per proposal starting at iteration `1`. Malformed input records have stage `input` and a blank iteration. Statuses include `extracted`, `rejected`, `exhausted`, `early-stop`, `verified`, and `error`. The `feedback` field gives the reason for a rejection or error. The `create_queries` field records any statements generated for that proposal, including when the proposal is rejected or the verifier raises an error. Token counts in this report apply to schema requests.

```text
spec_id,input_line,stage,iteration,status,database_specification,prompt,model_response,input_tokens,output_tokens,total_tokens,attributes,attribute_types,functional_dependencies,relational_schema,feedback,verification,create_queries
```

### Extraction results

`extraction_results.csv` records one row for each extraction attempt, including failed attempts. Each row can contain the source specification, chat messages, assistant text, token counts, and the extracted `attributes`, `attribute_types`, and `functional_dependencies`. The `status` and `feedback` fields describe the extraction outcome.

```text
spec_id,input_line,status,database_specification,prompt,model_response,input_tokens,output_tokens,total_tokens,attributes,attribute_types,functional_dependencies,feedback
```

Read `prompt`, `attributes`, `attribute_types`, `functional_dependencies`, `verification`, and `create_queries` as JSON when populated. `input_tokens` counts tokens sent to the model, and `output_tokens` counts tokens generated by the model. The pipeline reads these counts from `prompt_tokens` and `completion_tokens` for hosted calls, and from `prompt_eval_count` and `eval_count` for native Ollama. Hosted calls use the original usage fields when LiteLLM exposes an OpenAI-format response. Other hosted calls use LiteLLM's normalized usage, which may supply zero for an omitted counter. When the available metadata omits a total but supplies both counts, the pipeline adds them. Missing counters remain blank when the backend exposes them as missing. [LiteLLM response format](https://docs.litellm.ai/docs/learn/python_sdk_quickstart) · [Ollama chat response](https://docs.ollama.com/api/chat)

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
