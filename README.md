# text2schema
formal verification guided db spec to db schema generation

The [RSchema dataset analysis](dataset-analysis/RSchema/report.md) covers file structure,
specification lengths, schema sizes, keys, types, reference quality, and project
implications. See [reproduction instructions](dataset-analysis/RSchema/README.md).
The [SQL execution error report](dataset-analysis/RSchema/results/sql_execution/errors.md)
lists exact errors for every failing schema and CREATE statement.

```bash
python3 dataset-analysis/RSchema/scripts/analyze_rschema.py
python3 dataset-analysis/RSchema/scripts/verify_rschema_analysis.py
python3 dataset-analysis/RSchema/scripts/inspect_sql_execution.py
```
