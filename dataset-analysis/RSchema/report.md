# RSchema dataset analysis for the text2schema project

This audit analyzes the actual files in [`dataset/RSchema/`](../../dataset/RSchema/), in the context of the [project proposal](../../formal_verification_guided_text2schema.pdf). RSchema is a collection of English business specifications paired with reference relational schemas. It supplies schema definitions, not populated databases. It is suitable for evaluating schema reconstruction, but the proposed FD-based verification requires additional trusted annotations.

The local release has **518 distinct examples**. All have structured JSON schemas; **381** also have SQL DDL. These are overlapping representations, not disjoint datasets. Never add them to obtain a dataset size or join them by line number.

## 1. Files, provenance and record structure

| File | Records | Bytes | Answer representation | Fields |
|---|---:|---:|---|---|
| `annotation.jsonl` | 518 | 1,039,681 | JSON object | `id`, `question`, `answer` |
| `annotation_ddl.jsonl` | 381 | 908,416 | SQL string | The same three fields plus `remarks`, `assign_to`, `assign_to_round2`, `domain` |

Both are UTF-8 JSON Lines: each physical line contains a complete JSON object; newlines within specifications and SQL are escaped inside the JSON string. Both files have unique IDs, no blank lines, no duplicate object keys, no blank required fields, and no exact duplicate questions or answers. Casefolding and whitespace normalization also find no duplicate questions; this does not rule out semantic paraphrases.

All 381 DDL IDs occur in the JSON file, and every shared specification is byte-for-byte identical as decoded text. DDL preserves the JSON subset order, but skipped examples change line numbers. **137 examples have no DDL**; they contribute 688 tables and 3,252 attribute entries. No supplied field explains why these examples lack DDL.

The paper describes 381 final examples after refinement and review. Initial examples came from SchemaPile-derived DDL, constructed industry scenarios, and online database-design materials; some requirements were LLM-generated. These are paper-reported construction facts, not per-row provenance labels. The local files do not establish the review status of the additional 137 JSON-only examples. [Text2Schema paper, sections 3.1-3.4](https://arxiv.org/html/2503.23886v2#S3)

### Structured JSON

`question` is the database specification. `answer` maps table names to three fields. For example, the first record includes this table:

```json
{
  "Airplane": {
    "Attributes": ["Airplane Number", "Model", "Passenger Capacity"],
    "Primary key": ["Airplane Number"],
    "Foreign key": {}
  }
}
```

Another table in that answer encodes an FK as `"Airplane Number": {"Airplane": "Airplane Number"}`. PKs are lists to permit composite keys. FKs are usually single-column maps, with one composite-list exception described below. JSON supplies **names, attributes, PKs and FKs**, with no explicit data types, nullability, FDs or complete candidate-key sets. Every table has the same three fields.

### DDL

The same first example contains three `CREATE TABLE` statements. Its airplane declaration is:

```sql
CREATE TABLE Airplane (
    Airplane_Number INTEGER PRIMARY KEY,
    Model VARCHAR(255),
    Passenger_Capacity INTEGER
);
```

The DDL adds SQL types and explicit constraints, generally replacing name spaces with underscores. It contains only `CREATE TABLE` statements; there are no inserts, queries, indexes, triggers or stored procedures in these answers. The dataset does not label a specific SQL dialect. Treat it as SQL DDL with a small type vocabulary and separately test the chosen DBMS; it is not uniformly executable SQLite SQL.

Specifications are English on inspection. Neither question field contains CJK characters, and all table/attribute identifiers in both representations are ASCII. Some questions contain non-ASCII characters, mostly punctuation: 38 JSON records, including 30 DDL-backed records. Domain labels are Chinese, as are many annotation remarks. JSON is the serialization language; SQL is the executable schema language in the DDL file. Neither file is a Lean, Dafny, Z3 or SMT-LIB specification.

## 2. How large are the specifications?

Words below are whitespace-separated units, not LLM tokens. Characters are decoded Unicode code points. These are lengths of `question` alone.

| Specification metric | Full JSON set (518) | DDL-backed subset (381) |
|---|---:|---:|
| Words: minimum / median / mean / maximum | 37 / 122.5 / 138.59 / 476 | 37 / 120 / 138.11 / 440 |
| Words: 25th / 75th / 95th percentile | 89 / 164 / 302 | 87 / 165 / 308 |
| Characters: minimum / median / mean / maximum | 261 / 868.5 / 983.57 / 3,577 | 261 / 848 / 978.93 / 3,228 |
| Characters: 95th percentile | 2,091.5 | 2,125 |
| Total words | 71,792 | 52,619 |

The longest JSON specification is row 406, ID `67552f0a13602ec03b41a9cb`, with 476 words and 3,577 characters; it has no DDL. The longest DDL-backed specification by word count is DDL row 84, ID `67552f0a13602ec03b41a918`, at 440 words. By character count it is row 58, ID `67552f0a13602ec03b41a878`, at 3,228 characters. These are different examples.

The paper reports an average of 164 requirement words, whereas this local DDL subset averages 138.11 under the explicit whitespace rule. The files do not resolve whether this reflects a counting convention or another text version; use the measured values for this checkout. [Text2Schema paper, section 3](https://arxiv.org/html/2503.23886v2#S3)

For output budgeting, DDL answers contain 300-3,136 characters (median 1,044; mean 1,134.23). Compact canonical JSON answers contain 270-3,125 characters (median 831.5). These representation sizes are not tokenizer counts. Measure tokens with the actual model tokenizer and include prompts, extracted FDs, solver feedback and repeated attempts when estimating experiment cost.

## 3. How large are the schemas?

Count each table declaration separately and each explicitly declared attribute entry, including PK/FK columns. Table-level constraints are not columns. Preserve duplicate JSON attribute entries rather than silently repairing the reference.

| Metric | Full JSON set | DDL-backed SQL |
|---|---:|---:|
| Schemas | 518 | 381 |
| Tables, total | 2,436 | 1,748 |
| Attributes/columns, total | 11,708 entries | 8,453 declarations |
| Distinct column names summed within tables | 11,705 | 8,453 |
| Tables/schema: min / median / mean / max | 1 / 4 / 4.70 / 18 | 2 / 4 / 4.59 / 11 |
| Columns/schema: min / median / mean / max | 5 / 21 / 22.60 / 71 | 5 / 21 / 22.19 / 63 |
| Columns/table: min / median / mean / max | 1 / 4 / 4.81 / 18 | 1 / 5 / 4.84 / 18 |
| 95th percentile: tables/schema | 8 | 8 |
| 95th percentile: columns/schema | 41 | 39 |

The schemas are mostly small. These counts establish the available scale; they do not establish solver tractability for FD closure or candidate-key enumeration. The logical set has a larger upper tail than the DDL subset, so using only DDL changes the size distribution.

| Tables in a schema | JSON schemas | DDL schemas |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 23 | 18 |
| 3 | 143 | 106 |
| 4 | 107 | 84 |
| 5 | 107 | 78 |
| 6 | 54 | 41 |
| 7 | 43 | 27 |
| 8 | 20 | 16 |
| 9 | 9 | 7 |
| 10 | 2 | 2 |
| 11 | 4 | 2 |
| 12 | 3 | 0 |
| 13 | 1 | 0 |
| 18 | 1 | 0 |

Concrete extrema, using 1-based lines in the named source:

- **Largest JSON schema:** row 406, ID `67552f0a13602ec03b41a9cb`, 18 tables and 71 attributes. **One-table JSON schema:** row 319, ID `67552f0a13602ec03b41a8b8`.
- **Largest DDL table count:** 11 tables at rows 228 and 349, IDs `67552f0a13602ec03b41a886` and `67552f0b13602ec03b41ab17`.
- **Largest DDL column count:** row 80, ID `67552f0a13602ec03b41a8f3`, 8 tables and 63 columns. Counts by table are 10+10+7+8+12+4+5+7.
- **Smallest column count:** ID `67552f0a13602ec03b41a908`, JSON row 115 / DDL row 81: `Benchmark_Testing` has 2 columns and `Unit` has 3.
- **Widest tables:** `Recipe` and `Company`, 18 columns each, at DDL rows 57 and 58. **Narrowest DDL tables:** `Inspector` and `Prescription`, one column each, at rows 87 and 94. Some one-column JSON tables have inconsistent PK labels; see the issue outputs.

All ties and source IDs appear in [summary.json](results/summary.json); complete distributions appear in [histograms.csv](results/histograms.csv).

## 4. Keys, types and domains

| Constraint statistic | JSON | DDL |
|---|---:|---:|
| Declared PK constraints | 2,436 | 1,746 |
| Composite PK lists/constraints | 638 | 451 |
| Schemas with at least one composite PK | 379 | 274 |
| Parsed FK constraints | 2,146 | 1,496 |
| Composite FKs | 2 | 0 |
| Self-referencing FKs | 29 | 17 |
| Schemas with zero parsed FKs | 5 | 4 |

JSON contains 2,147 raw FK source-map entries and 2,148 target-map entries; two malformed nested targets cannot be interpreted as normal FK constraints, leaving 2,146 parsed FKs. One example correctly yields two composite FKs from list-valued target columns. Composite-PK statistics follow literal PK list lengths: a comma-separated string inside one list element is not silently split.

DDL contains **1,495 explicitly `NOT NULL` columns**. There are no explicit standalone `UNIQUE`, `CHECK` or `DEFAULT` clauses; primary-key uniqueness is counted through PKs. Absence of a JSON nullability field is missing supervision, not a label that a column is nullable. The DDL does not provide a broad benchmark of business rules such as range checks, conditional constraints or referential actions.

| Literal DDL type | Columns |
|---|---:|
| `VARCHAR(255)` | 3,598 |
| `INTEGER` | 3,191 |
| `DATETIME` | 1,062 |
| `FLOAT` | 494 |
| `BOOL` | 69 |
| `BLOB` | 29 |
| `null` | 10 |

The last category is the actual source spelling in DDL rows 82 and 313, not ten inferred SQL NULL values. Flag these as unresolved type labels. The other six spellings are the useful observed type vocabulary. Do not infer precision, domain ranges or intended types from them without separate annotation.

The 381 DDL rows carry **19 major domain labels** and **57 distinct major/minor pairs**. The largest categories are information/software/IT services (70), culture/sports/entertainment (43), education (38), wholesale/retail (37), and leasing/business services (33). Those five contain 221/381 examples (58.01%). These labels permit domain-stratified reporting on the DDL subset. Preserve their original spellings in [domains.csv](results/domains.csv); some labels may need human interpretation. Domain annotations are absent for the 137 JSON-only examples.

`remarks` is nonempty in 225 rows, including 189 with CJK characters. Each assignment field has 11 distinct assignee codes. These are annotation-process metadata, not model inputs or verification labels. There are no supplied train/validation/test partitions, source-origin labels, difficulty labels, execution results or formal proof certificates.

## 5. Reference consistency and execution quality

### The two schema representations nearly agree, but are not interchangeable

Using casefolding plus whitespace/underscore normalization, **381/381 table sets agree**, **378/381 column multisets agree**, and **376/381 complete parsed structures including PKs/FKs agree**. The 381 paired JSON schemas contain 8,456 attribute entries versus 8,453 SQL columns. Three JSON duplicates account for the entire column-count difference:

| ID | JSON line | DDL line | Duplicated JSON attribute |
|---|---:|---:|---|
| `67552f0a13602ec03b41a879` | 87 | 59 | `User.Number of Followers` |
| `67552f0a13602ec03b41a8f0` | 336 | 252 | `Product.Product Status` |
| `67552f0b13602ec03b41aad7` | 467 | 342 | `Delivery Order.Delivery Order ID` |

The remaining two key mismatches are DDL rows 123 and 260: the DDL omits a PK present in JSON. In both cases the JSON PK label is itself inconsistent with the attribute list. For example, JSON row 176 stores `"Ticket Order Number, Passenger ID, Flight ID"` as one PK-list element. Preserve these differences in a correction manifest if preparing evaluation references. See [paired_comparison.jsonl](results/paired_comparison.jsonl).

### Structural reference checks

Exact-name checks on parsed JSON references find 39 missing PK-column occurrences, 41 missing local FK-column occurrences, 51 missing target-column occurrences, 34 missing target-table occurrences and 3 duplicate attribute entries. Those parsed-reference findings affect **72 distinct schemas**; the separate whitespace/underscore/case heuristic reduces that to **63**. These are screening counts, not a claim that all other references are semantically correct. The two uninterpretable nested FK targets in JSON row 154 are separately flagged and excluded from this screen's FK interpretation.

In the DDL, 7 PK-column references are absent from the declared columns across 6 schemas; 2 additional tables lack PK declarations. The union covers 8 schemas. For example, row 5 declares `Equipment_ID` but names `Device_ID` in the maintenance-record PK. FKs can also target a strict subset of a composite PK; the analyzer flags this for review, separately from missing-name errors. Candidate-key semantics are not supplied, so this diagnostic is not automatically a correctness verdict.

### SQLite execution

**315/381 original DDL answers execute successfully (82.68%)** and match the independently counted table/column inventories. **66 fail (17.32%)**, commonly because of unquoted reserved words (`Order`, `Transaction`), punctuation/apostrophes in names, or nonexistent PK columns. SQL row 80, despite failing execution, still has countable declarations for 8 tables and 63 columns.

The execution test enables FK checking but creates empty databases only. SQLite can accept FK definitions that fail later during data modification. CREATE success therefore does not prove referential behavior, requirement fidelity, 3NF, dependency preservation or lossless decomposition. Keep executability and reference validity as separate evaluation measures. Every original example remains in the declaration-based size statistics. [issues.jsonl](results/issues.jsonl) records exact IDs, lines, tables and SQLite errors; categories overlap.

The [SQL execution error report](results/sql_execution/errors.md) expands all 66 failing examples
with their exact original error, failing table, statement index, SQL line range and unchanged SQL.
A separate pass continues through all 1,748 CREATE statements and finds 115 failing statements
across those 66 schemas (34 have more than one failing statement). Later errors from that scan
are labeled separately because the original script stops at its first failure. Reproduce with
`python3 dataset-analysis/RSchema/scripts/inspect_sql_execution.py`.

## 6. Implications for the proposed project

The proposal's Z3 loop checks normalization, decomposition and attribute coverage, then uses counterexamples for refinement. The dataset supports different parts of that evaluation to different degrees:

| Proposed evaluation/check | Available supervision and required work |
|---|---|
| Table/attribute F1 and exact match | Names and table membership exist for all 518; define identifier matching, duplicate handling and treatment of alternative valid decompositions. |
| PK/FK accuracy | Labels exist for all 518 but need the consistency review above; distinguish composite keys from separate single-column keys. |
| Data-type accuracy | Use the 381 DDL-backed examples, with a declared policy for the 10 literal `null` type labels. |
| Attribute coverage | Reference inventories support a coverage baseline. Use scoped identifiers: `Customer.Name` and `Product.Name` need not be the same attribute. Define mappings when comparing decompositions. |
| 3NF/BCNF | No explicit FD sets or complete candidate-key annotations. Extract and validate these before claiming gold normalization results. |
| Dependency preservation and lossless join | No labeled universal relation, original FD set or decomposition mapping. These must be defined for the verified subset. |
| Concrete counterexamples | No tuple data or expected counterexamples. Counterexample tuples must be synthesized under explicitly stated formal assumptions. |

**Do not use only `PK -> all other columns` as the FD oracle.** Those key-induced dependencies largely assume away the non-key dependencies that normalization is meant to detect. For example, key-only FDs miss `customer_id -> customer_address` inside `Order(order_id, customer_id, customer_address)`. An FK is generally an inclusion dependency, not an FD. Z3 acceptance establishes a property relative to the encoded FDs and assumptions; it does not establish that the English requirement was faithfully interpreted.

Recommended preparation:

1. Keep raw files immutable and join by `id`. Document an explicit reference policy before scoring: the paper-comparable 381 subset for the principal experiment, and optionally the additional 137 for a separately reported structural extension. All 518 are available for structural evaluation, but their review status should not be assumed identical.
2. Create a manually validated subset with scoped attributes, types where needed, trusted FDs, key semantics and decomposition intent. This supplies the missing inputs for configuration (iii) and the proposal's fallback. Freeze the FDs across refinement so a model cannot pass by deleting inconvenient dependencies.
3. Give Bernstein and the LLM decomposition methods the same FD inputs for a controlled comparison. Report an additional end-to-end experiment using extracted FDs to measure extraction error separately.
4. Freeze development/demo/evaluation IDs. Check paraphrase/template leakage beyond the exact-duplicate screen. Report results by size, composite-key presence and DDL domain where labels exist; the largest JSON examples are absent from the DDL subset.
5. Keep structural reference agreement, SQL executability, and solver-verified properties separate. An alternative valid decomposition may score below exact match; a high-reference-match schema may still fail the verifier. Report any curated exclusions and repairs by ID with reasons and denominators.
6. Measure runtime, actual tokenizer counts and refinement attempts in the experiment. Schema size alone cannot predict FD-closure or candidate-key cost. The dataset has no gold timing, token or refinement traces.

## 7. Reproduce and inspect the extraction

From the repository root:

```bash
python3 dataset-analysis/RSchema/scripts/analyze_rschema.py
python3 dataset-analysis/RSchema/scripts/verify_rschema_analysis.py
```

Both scripts use only the Python standard library. The analyzer regenerates the full statistical extraction and example-level audit; the verifier independently checks counts and question lengths, then compares a fresh run byte for byte. See [reproduction instructions and counting definitions](README.md), [generated statistics](results/statistics.md), and [the analyzer](scripts/analyze_rschema.py). Narrative recommendations in this report are interpretation; the extracted data lives in `results/`.
