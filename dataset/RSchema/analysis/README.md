# Reproducing the RSchema analysis

Read [the analysis report](report.md) for findings and their implications for the proposal. [Generated statistics](results/statistics.md) contain the detailed distributions. The original files in `dataset/RSchema/` are read without modification.

## Run

Use Python **3.10 or later** with its standard-library `sqlite3` module. No pip packages, model API, network access, or database server are required. The supplied results were generated with Python 3.14.7 and SQLite 3.50.4; the runtime and analyzer checksum are recorded in [environment.json](results/environment.json).

From the repository root:

```bash
python3 dataset/RSchema/analysis/scripts/analyze_rschema.py
python3 dataset/RSchema/analysis/scripts/verify_rschema_analysis.py
```

For the [exact SQL execution errors by example and table](results/sql_execution/errors.md):

```bash
python3 dataset/RSchema/analysis/scripts/inspect_sql_execution.py
```

This additional script runs each original SQL answer, then separately attempts every unchanged
CREATE statement while continuing after errors. It records the original first error and all
statement-scan errors separately, with IDs, source lines, tables, SQL line ranges and full SQL.
It finds 66 failing schemas and 115 failing statements; 34 schemas have multiple failing
statements. The complete schema runs still have 315 successes. These results use SQLite 3.50.4
and are saved under `results/sql_execution/` as `errors.md`, `schemas.csv`, `statements.csv`,
`errors.jsonl` and `summary.json`. Use `--input` and `--out-dir` to override its defaults.

Expected main output:

```text
logical: 518 schemas, 2436 tables, 11708 columns
ddl: 381 schemas, 1748 tables, 8453 columns
DDL: 315 SQLite CREATE successes; all 381 declaration inventories independently cross-checked
```

The scripts resolve their default paths from their own location, so they also work when invoked by absolute path from another directory. To use another input or output directory:

```bash
python3 dataset/RSchema/analysis/scripts/analyze_rschema.py --data-dir dataset/RSchema --out-dir /tmp/rschema-analysis
python3 dataset/RSchema/analysis/scripts/verify_rschema_analysis.py --data-dir dataset/RSchema --results-dir /tmp/rschema-analysis
```

The analyzer handles the CREATE TABLE grammar in this release. It fails on unsupported declarations instead of silently omitting them. Embedded apostrophes in bare identifiers are retained for counting, even though SQLite rejects them. The verifier is deliberately pinned to this audited release's checksums and independent expected counts; a changed dataset needs a new audit. Different SQLite versions can change error strings or acceptance behavior. Regenerate the results with your runtime before running the verifier; compare `environment.json` when comparing executions.

## Outputs

The analyzer regenerates the files directly under `results/`; the execution inspector
regenerates files under `results/sql_execution/`. Keep personal notes outside these output directories.

| File | Contents |
|---|---|
| `summary.json` | File sizes/checksums/fields, distributions, all extrema IDs, duplicate checks, issue counts, overlap, types and metadata |
| `statistics.md` | Readable generated statistical tables and domain counts |
| `schema_metrics.csv` | One row per input example per representation, with specification lengths, schema size, keys, domain and SQLite status |
| `table_metrics.csv` | One row per declared table, retaining original names and column counts |
| `column_metrics.csv` | One row per attribute entry or SQL column; type and explicit NOT NULL for DDL |
| `histograms.csv` | Exact frequency counts for tables/schema, columns/schema, columns/table and specification word lengths |
| `domains.csv` | Counts for all 57 original major/minor domain-label pairs |
| `issues.jsonl` | Exact-label reference findings, unusual FK encodings, literal `null` types and SQLite error messages, with source line and ID |
| `normalized_issues.jsonl` | A separate reference audit using the documented identifier normalization |
| `paired_comparison.jsonl` | One row per shared ID, comparing question text, tables, column multiplicities and keys |
| `examples.json` | Selected unmodified source records, including representative, extreme and problematic examples |
| `environment.json` | Python/SQLite versions and analyzer SHA-256 |

CSV is UTF-8 and includes the original Chinese domain labels. JSON files are UTF-8. `line` is the **1-based physical line in the corresponding source file**, not a cross-file index; use `id` to join representations. There are 899 representation rows but **518 distinct examples**. Missing types/nullability for logical JSON appear as blank CSV fields and JSON `null` summaries; they are not negative labels.

## Counting and audit definitions

- A nonblank JSONL row is one specification/schema example. A JSON table-map entry or SQL `CREATE TABLE` declaration is one table.
- JSON columns count entries in `Attributes`, including duplicate entries. SQL columns count explicitly declared columns, including PK/FK columns. Table-level PK/FK clauses are constraints, not extra columns. Names that merely resemble constraint keywords, such as `Check-in_Time`, are columns.
- Word counts use `len(question.split())`: whitespace-separated units, without a model tokenizer. Characters use Python Unicode code points; UTF-8 bytes are also recorded. Quantiles use linear interpolation at `(n-1)*p`; Markdown rounds to two decimals, JSON retains computed values. These sizes describe the specification text alone, excluding prompts and generated output.
- DDL answer size is the literal SQL text. JSON answer size is a compact, sorted-key serialization with `ensure_ascii=False`; it is a reproducible representation-size measure, not its on-disk escaped JSONL length.
- The main SQL reader splits statements and table items with nesting/quote awareness. A separate physical-line reader independently checks every table and column name in all 381 DDL answers. Every answer is also executed unchanged in a fresh in-memory SQLite database with `PRAGMA foreign_keys=ON`. Successful runs must match the parsed table/column inventory exactly. Failures remain in size statistics. No tuple data is inserted and no normalization property is proved by this check.
- Exact reference auditing checks PK column membership, FK source/target membership, FK arity, duplicate columns and absent PKs. It does not repair names. The separate normalization strips outer identifier quotes, trims, replaces runs of whitespace/underscores with `_`, and casefolds. It retains punctuation and other differences. Pair comparisons use that same rule and preserve column multiplicity; column/PK-list ordering is ignored, FK column order is retained.
- The JSON FK map normally encodes `source column -> {target table: target column}`. Each target entry counts separately, including multiple targets under one source. The one list-valued encoding is explicitly parsed as two composite FKs by splitting comma-separated source names and retaining the target lists. Two nested-dictionary targets are flagged and omitted from parsed FK totals. Commas inside a **PK list element** are retained literally, not interpreted as a repair.
- `schemas_with_exact_reference_issues` and `schemas_with_normalized_reference_issues` cover parsed membership/arity/duplicate/missing-PK findings. They exclude unparsed nested FK encodings, SQLite errors and the separate `fk_target_not_entire_declared_pk` diagnostic. Issue categories overlap; do not add schema counts to obtain a union.
- `fk_target_not_entire_declared_pk` is a review flag. A referenced attribute could be another candidate key whose semantics are absent from the labels; this flag alone is not a judgment of invalidity. Composite-PK counts use the actual PK list lengths, including any source mistakes.

The independent verification script checks exact source hashes, derives every table's column count from raw JSON lists or physical SQL lines, checks every specification length, then reruns extraction in a temporary directory and compares every output byte for byte. The report's project recommendations and external-paper discussion are authored interpretation; the `results/` files are the reproducible data extraction.
