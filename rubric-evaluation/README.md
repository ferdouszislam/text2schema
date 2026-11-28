# Rubric evaluation

This folder scores generated schemas on keys, foreign keys, and rules, which the [pipeline evaluation](../pipeline-evaluation/README.md) does not check. The pipeline evaluation compares table and column names with the reference and runs the normal-form verifier. Both use the same 375 cleaned RSchema specifications.

The scores come from Tanzim's repository ([thromel/text2schema](https://github.com/thromel/text2schema)). Results are in [`results/rubric_metrics.md`](results/rubric_metrics.md).

## What was added to this repository

| Path | Contents |
| --- | --- |
| `pipeline/results/qwen3.8-27b-q8_0-oneshot/` | Extraction and the first schema proposal from the saved `qwen3.8-27b-q8_0` run |
| `pipeline/results/qwen3.8-27b-q8_0-bernstein/` | The same extraction, then Bernstein's 3NF synthesis from the extracted FDs, with no schema LLM call |
| `pipeline/results/qwen3.8-27b-q8_0-contract/` | The contract pipeline: one LLM call returns the attributes, keys, foreign keys and rules, and a compiler writes the SQL |
| `pipeline/results/qwen3.8-27b-q8_0-contract-nf/` | The contract pipeline, then a normal-form loop that uses this repository's extraction prompt and verifier, with at most 3 proposals |
| `pipeline-evaluation/results/2026-11-28_16-15-50-128214Z/` | `pipeline-evaluation/evaluate.py` on all seven run folders, with the `gpt-6-luna` similarity check |
| `rubric-evaluation/` | This guide and the rubric results |

The contract runs use `qwen3.8:27b-q8_0` on Ollama with thinking off, the same as `qwen3.8-27b-q8_0`. Their CSV files use the same columns, and columns the contract pipeline does not produce, such as `prompt`, are empty. The `contract-nf` extraction rows hold token counts only.

In the contract folders, a run is `verified` when the four verifier checks pass on its final schema, using the FDs from this repository's extraction prompt. The `contract` run makes no extraction call of its own, so it uses the FDs from the `contract-nf` run for this check.

## Metrics

Each metric compares the generated SQL with the reference DDL. First, columns are paired by name, then by embedding similarity (bge-m3).

| Metric | Meaning |
| --- | --- |
| Strict | Z3 finds no database state that one schema allows and the other rejects. The check covers primary keys, unique keys, foreign keys, `NOT NULL` and implied FDs. |
| No NOT NULL | Strict, ignoring `NOT NULL` rules |
| Judged pass | A judge LLM labels each difference that Z3 finds. The schema passes when no difference is MISS or WRONG |
| Data-type accuracy | The share of matched columns whose type agrees with the reference (the metric of the RSchema paper) |
| Foreign keys | The number of `FOREIGN KEY` constraints over all specifications |

Strict counts every difference from the reference as an error, but the reference is only one valid design, so strict is a lower bound.

### The judge

1. Z3 lists each difference from the reference as a unit: a missing table (`T`), a missing column (`C`), or a rule that differs (`R`).
2. The judge (`gemma-4-31b`, medium reasoning, 5 votes) reads the specification, both schemas and the units. It gives each unit one label:
   - `MISS`: the specification requires the element and the generated schema lacks it.
   - `WRONG`: the generated rule contradicts the specification.
   - `CONV`: both designs are valid.
   - `SCORER`: the pairing missed an equivalent element.
   - `GOLD`: the reference element is not supported by the specification.
3. The prompt has fixed decision rules for common cases. For example, a natural key in place of a surrogate ID is `CONV`. A reference to another entity with no foreign key is `MISS` or `WRONG` when the specification names the link.

The judge gives the same verdict on 89 of 90 specifications when it votes again. It agrees with an audit of 60 specifications on 0.87 of them (kappa 0.68). Claude wrote those audit labels, not a person, so judged pass is a model-judged number. Labels from a person are in progress.

## Reading the results

The two evaluations measure different things.

- The pipeline evaluation rewards table and column names that match the reference.
- The rubric evaluation rewards keys and foreign keys that the specification requires. Runs with no `FOREIGN KEY` constraints fail almost every specification here, because almost every reference has links between tables.

Bernstein synthesis passes the verifier by construction. Its tables and keys come from the extracted FDs, so a wrong FD gives a wrong table.

## Reproduce

Run these from the root of [thromel/text2schema](https://github.com/thromel/text2schema), with this repository next to it as `../teammate-text2schema`.

```bash
source scripts/env.sh && PYTHONPATH=scripts uv run python scripts/t106_his_baselines.py
```

`scripts/t107_his_metrics.py build his` writes the `oneshot` and `bernstein` folders. `scripts/t104_latency.py` produced the contract runs.
