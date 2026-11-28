# Rubric metrics per pipeline

375 specifications of the cleaned RSchema dataset. See the [rubric evaluation guide](../README.md) for the metric definitions.

| Run | No schema | Judged pass | Strict | No NOT NULL | Data-type accuracy | Foreign keys | LLM calls per spec | LLM s per spec |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| <code>qwen3.8-27b-q8_0</code> (final proposal) | 9 | 0.075 | 0.003 | 0.101 | 0.844 | 0 | 5.57 | 73.6 |
| <code>qwen3.8-27b-q8_0-oneshot</code> | 7 | 0.059 | 0.003 | 0.136 | 0.852 | 0 | 1.99 | 32.7 |
| <code>qwen3.8-27b-q8_0-oneshot-fk</code> | 7 | 0.301 | 0.059 | 0.264 | 0.852 | 591 | 1.99 | 32.7 |
| <code>qwen3.8-27b-q8_0-bernstein</code> | 5 | 0.379 | 0.051 | 0.205 | 0.820 | 1464 | 1.00 | 22.9 |
| <code>qwen3.8-27b-q8_0-contract</code> | 0 | 0.843 | 0.160 | 0.379 | 0.758 | 1362 | 1.00 | 52.6 |
| <code>qwen3.8-27b-q8_0-contract-nf</code> | 0 | 0.856 | 0.165 | 0.381 | 0.758 | 1387 | 2.62 | 109.0 |
| <code>contract-qwen35-122b-stored</code> | 4 | 0.760 | 0.179 | 0.387 | 0.703 | 1322 | 1.00 | n/a |

`oneshot-fk` is the one-shot run plus a foreign key from each column whose name matches the primary key of another table. It has no folder under `pipeline/results/`. `contract-qwen35-122b-stored` is the stored contract run with a larger model on another server, so it has no time.

LLM seconds come from each run's CSV files: the `qwen3.8-27b-q8_0` runs on their own hardware, and the contract runs on one L40S GPU.

Per-specification results are in [`per_record_metrics.json`](per_record_metrics.json). For each run and `spec_id`, the fields are:

| Field | Meaning |
| --- | --- |
| `judged` | `1.0` if the judge marks no difference as MISS or WRONG |
| `strict` | `1.0` if Z3 finds no difference from the reference schema |
| `no_nn` | Strict, ignoring `NOT NULL` rules |
| `none` | Number of differences that the judge did not label |
| `bad` | The differences that failed the schema, as `LABEL unit` (`C` column, `T` table, `R` rule), or `no schema` |
