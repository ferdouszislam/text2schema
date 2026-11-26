# Pipeline evaluation

Evaluate saved runs in `pipeline/results/` against the cleaned RSchema DDL.

## Run

From the repository root, use the [project's Python environment](../README.md).

```bash
.venv/bin/python pipeline-evaluation/evaluate.py
```

The default run evaluates every model folder except `debug`. To select specific
runs or enable table and column similarity scoring, add the settings below to the
root `.env`. Folder names include any run number or range suffix.

```dotenv
# Comma-separated folder names. Blank includes all full runs.
EVALUATION_MODELS=

# Set to true to enable both similarity metrics.
EVALUATION_ENABLE_SIMILARITY=false
EVALUATION_SIMILARITY_MODEL=gpt-6-luna
EVALUATION_OPENAI_API_KEY=
```

With similarity enabled, supply an OpenAI API key. The judge sends identifier
pairs to OpenAI in batches and saves its binary decisions with the results.
Shell environment values override `.env` values.

## Results

Each completed run writes a UTC timestamp directory under
[`results/`](results/). It contains the following files.

| File | Contents |
| --- | --- |
| `evaluation_metrics.json` | Per-model iteration counts, verification-criterion failures, and means used by the charts and tables |
| `per_record_metrics.json` | Final status, criterion outcomes for unverified proposals, schema names, match pairs, and resource measurements for each specification |
| `similarity_decisions.json` | Unique identifier pairs judged by the model, available when similarity is enabled |
| `required_iterations.png` | Grouped bar chart of LLM revision counts and unverified outcomes for all evaluated runs |
| `verification_criteria_failures.png` | Grouped bar chart of formal criterion failures and pre-verifier rejections on final proposals from exhausted and early-stop records |
| `table_matching.png` and `column_matching.png` | Grouped charts of exact and similarity match percentages for all evaluated models |
| `token_consumption.md` and `timings.md` | Mean tokens and time per specification |

To regenerate the charts and tables from a saved run, replace `TIMESTAMP` with its
directory name.

```bash
.venv/bin/python pipeline-evaluation/render_reports.py pipeline-evaluation/results/TIMESTAMP
```

See the [script and metric definitions](EVALUATION-EXPLAINED.md).
