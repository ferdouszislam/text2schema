# RSchema preprocessing

The [preprocessing script](scripts/preprocess_rschema.py) joins the two original RSchema files by `id`, keeps the DDL-backed examples, repairs the requested identifier errors, and drops SQL that still fails after three retries. The original files under `dataset/RSchema/` are read without modification.

## Run

From the repository root, using Python 3.10 or later:

```bash
python3 dataset/RSchema/preprocessing/scripts/preprocess_rschema.py
```

No third-party packages, model API, network connection or database server are needed. Defaults are resolved relative to the script, so invoking its absolute path from another directory also works. Override the input and output directories with:

```bash
python3 dataset/RSchema/preprocessing/scripts/preprocess_rschema.py --data-dir dataset/RSchema --out-dir /tmp/rschema-preprocessed
```

Expected results for the supplied snapshot, using SQLite 3.50.4:

```text
Merged 381 DDL-backed rows; excluded 137 JSON-only rows
Kept 375: 315 original SQL, 60 repaired SQL
Dropped 6 rows after 3 retries
```

## Processing rules

1. Read both JSONL files and join by `id`, preserving DDL-file order. A missing JSON counterpart, duplicate ID/object key or mismatched question raises an error instead of silently merging the wrong records.
2. Execute each original SQL answer in a fresh in-memory SQLite database with `PRAGMA foreign_keys=ON`.
3. For a failed answer, retry up to **three times after the initial attempt**, for at most four executions. Each retry uses a new empty database, so successful CREATE statements from an earlier partial run do not cause `table already exists` errors.
4. A `no such column:` error is retried with the SQL unchanged. Missing column names are never inferred, renamed or inserted to repair that error.
5. Otherwise, replace `-` and `/` with `_`, and remove every literal lowercase `'s`, in SQL identifier positions. This includes table declarations, columns, PK lists and FK source/target names. Preserve SQL clauses, data types, whitespace and statement order.
6. When SQLite reports `near "Transaction": syntax error`, double-quote that identifier wherever it occurs as an identifier: `Transaction` becomes `"Transaction"`. Apply this to the identifier reported by the current error; re-execution can expose another keyword requiring a later retry. SQL grammar words remain unchanged, including `TABLE` in `CREATE TABLE Table (...)`.
7. Keep examples whose SQL executes. Apply the same symbol/possessive substitutions recursively to their JSON schema names and references. JSON identifier values do not receive embedded SQL double quotes. Preserve JSON list order and duplicates, the question text, and the original annotation metadata.
8. Drop any answer still failing after the third retry. Save its exact final error and a full attempt log.

The SQL repair reader is scoped to the released RSchema layout: one CREATE header, column or PK/FK declaration per line, using its observed type vocabulary. Unsupported layout raises an error. It does not rewrite string literals or prose. Input, processing and JSON serialization must all succeed before output replacement; files are staged in the output directory before replacement.

## Outputs

All generated files are under [`results/`](results/):

| File | Contents |
|---|---|
| [cleaned.jsonl](results/cleaned.jsonl) | 375 merged, retained examples |
| [dropped.jsonl](results/dropped.jsonl) | Six rejected merged records, original DDL source lines and exact final errors |
| [audit.jsonl](results/audit.jsonl) | All 381 IDs, source lines, original/final SQL, identifier changes, and attempts numbered 0-3 |
| [summary.json](results/summary.json) | Counts, source checksums, script checksum, Python/SQLite versions and dropped IDs/errors |

Each cleaned record has these fields:

| Field | Value |
|---|---|
| `id` | Original shared example ID |
| `question` | Original specification text |
| `json_schema` | Structured schema object, with the requested identifier substitutions |
| `ddl_schema` | Original or successfully repaired SQL string |
| `remarks`, `assign_to`, `assign_to_round2`, `domain` | Original DDL annotation metadata |

The 315 already executable SQL answers remain unchanged. Of the 60 repaired answers, 58 succeed after one retry and two after two retries. Nineteen retained JSON schemas receive identifier spelling changes. The merge does not remove pre-existing duplicate JSON attributes or alter semantic labels beyond the requested name substitutions. Validation executes CREATE statements in an empty database; it does not test inserts or establish normalization.

## Dropped rows

These are 1-based physical lines in `dataset/RSchema/annotation_ddl.jsonl`. Their SQL remains unchanged throughout all four executions.

| DDL line | ID | Exact final error |
|---:|---|---|
| 5 | `67552f0a13602ec03b41a7aa` | `no such column: Device_ID` |
| 35 | `67552f0a13602ec03b41a81e` | `no such column: Record_ID` |
| 74 | `67552f0a13602ec03b41a8c7` | `no such column: Adding_time` |
| 83 | `67552f0a13602ec03b41a913` | `no such column: clock` |
| 137 | `67552f0a13602ec03b41a7e5` | `no such column: Employee_ID` |
| 175 | `67552f0a13602ec03b41a9f5` | `no such column: Information_ID` |

## Verify

Run the focused tests from the repository root:

```bash
python3 -m unittest discover -s dataset/RSchema/preprocessing/tests -v
```

The tests cover merging, substitutions in both representations, identifier-only keyword quoting, retry limits, unchanged missing-column errors, fresh databases between attempts, preservation of outputs on input/serialization failures, and execution of every retained schema from the real snapshot.
