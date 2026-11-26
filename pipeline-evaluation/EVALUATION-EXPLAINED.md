# Pipeline evaluation scripts

| Script | Role |
| --- | --- |
| `evaluate.py` | Selects model folders, loads the dataset and pipeline reports, computes per-specification and per-model metrics, and saves JSON before rendering |
| `schema_matches.py` | Extracts table and column names from SQL and pairs exact and similar names |
| `similarity.py` | Sends batches of up to 64 same-kind identifier pairs to OpenAI, validates the binary replies, and caches decisions within the run |
| `render_reports.py` | Reads the saved aggregate JSON and writes four charts and two Markdown tables |

## Required iterations

Each model folder contributes one observation per specification in its
`results.csv`. The script groups events by `spec_id` and `input_line` and uses
the final event for the status and schema attempt number. Events can be
interleaved across specifications in a batch run. Required iterations count
the LLM revisions after its first schema proposal. A verified proposal on
schema attempt `n` required `n - 1` revisions.

| Chart group | Rule |
| --- | --- |
| `0` | The first proposal verified |
| `1-5`, `6-10` | The proposal verified after that many LLM revisions |
| `exhausted` | The tenth proposal failed to verify, including an early stop on attempt ten |
| `early-stop` | The run ended without verification before the tenth proposal |
| `errors` | Final status `error` |

With a ten-proposal limit, the largest possible revision count is nine.
The per-record JSON stores the original attempt number as
`terminal_iteration` and the revision count as `required_iterations`.
Unverified records have a null revision count and contribute to their
outcome group.

## Failed verification criteria

For each model, the chart counts exhausted and early-stop specifications whose
final proposal failed each criterion. The evaluator reads the `passed` flag in
the final event's `verification.checks` for 2NF, 3NF, lossless join, and
dependency preservation. A specification can contribute once to each failed
criterion, so the bars can overlap in which specifications they count.

The `Others` bar counts final proposals with a recorded schema-validation
rejection before formal verification. This includes empty or invalid schema
responses and proposals that fail attribute coverage. The per-record JSON
stores the original feedback as `pre_verifier_rejection` and unavailable formal
outcomes as `null`. The aggregate JSON reports the eligible specification count,
the failed counts for all bars, and unavailable counts for the four formal
criteria.

## Table and column matching

The evaluator joins the pipeline's `spec_id` to `id` in
[`cleaned.jsonl`](../dataset/RSchema/preprocessing/results/cleaned.jsonl).
Generated names come from `create_queries` on the last event. Target names
come from `ddl_schema`. The SQL parser reads table declarations and their
column declarations, including quoted identifiers. Error records and final
proposals without SQL contribute 0% for both table and column matching.

Exact matching consumes pairs one-to-one. It first pairs identical names,
then remaining names that are equal after lowercasing, and finally remaining
names that are equal after removing underscores and lowercasing. Exact
column matching is scoped to each exact table pair.

Similarity scoring starts with exact matches. The judge compares unmatched
table names in rounds, in SQL declaration order within each specification.
A decision of `1` pairs those names and removes them from further
comparisons in that specification. Column scoring runs the same exact and
similarity steps within each exact or similar table pair. Column pairs are
recorded as `[generated table, generated column, target table, target column]`.

For each specification, divide the table match count by the total target
table count and the column match count by the total target column count across
all target tables. Multiply by 100 and average the percentages across
specifications with equal weight. The similarity percentages include the
exact matches. Missing target IDs are reported as errors for non-error
pipeline outcomes. An input error with an unknown target ID contributes
0% matching.

The two matching charts group models under `Exact match` and
`With similarity check`. An unavailable score is marked `N/A`.

## Tokens and timing

Token totals per specification include the extraction request and all schema
attempts. Extraction tokens come from `extraction_results.csv` where they are
blank in `results.csv`. If the total field is blank for an event with known
input and output counts, the evaluator adds the two counts. Model means divide
the reported token totals by all specifications. With incomplete reporting,
these means reflect recorded consumption. If no count of a token type is
available, its mean is blank. The JSON includes reporting counts for each token
type.

Total time uses the final event's `pipeline_total_seconds`. If that field is
blank and all event durations are available, the evaluator adds the event
`elapsed_seconds` values. LLM time is the sum of `llm_seconds` across
extraction and schema attempts in `results.csv`. It includes recorded
request delays, retries, and provider batch waits. Verifier and other Python
time is the difference between total and LLM time, including local parsing,
DDL generation, checks, and pipeline bookkeeping. Each mean uses the
specifications with that timing measurement. The JSON records these sample
counts and the source of each total time.
