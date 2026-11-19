# text2schema
formal verification guided db spec to db schema generation

Use one virtual environment and dependency file at the project root (Python 3.11 or later):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The environment is ignored by Git; `requirements.txt` records the project dependencies.

The [Z3 verifier guide](verifier/README.md) shows how to verify a proposed relational
schema and use the feedback to refine it.

The [RSchema dataset analysis](dataset/RSchema/analysis/report.md) covers file structure,
specification lengths, schema sizes, keys, types, reference quality, and project
implications. See [reproduction instructions](dataset/RSchema/analysis/README.md).
The [SQL execution error report](dataset/RSchema/analysis/results/sql_execution/errors.md)
lists exact errors for every failing schema and CREATE statement.

```bash
python3 dataset/RSchema/analysis/scripts/analyze_rschema.py
python3 dataset/RSchema/analysis/scripts/verify_rschema_analysis.py
python3 dataset/RSchema/analysis/scripts/inspect_sql_execution.py
```

The [RSchema preprocessing script and guide](dataset/RSchema/preprocessing/README.md)
merge the DDL-backed examples, repair identifier syntax errors, and drop rows that
still fail after three retries. The [cleaned dataset](dataset/RSchema/preprocessing/results/cleaned.jsonl)
contains 375 examples.

```bash
python3 dataset/RSchema/preprocessing/scripts/preprocess_rschema.py
python3 dataset/RSchema/preprocessing/scripts/plot_preprocessed_counts.py
```
