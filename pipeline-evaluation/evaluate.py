"""Extract and render evaluation metrics from saved text2schema runs."""

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from math import fsum, isfinite, isclose
import os
from pathlib import Path
from statistics import fmean
import sys
from tempfile import TemporaryDirectory

from dotenv import load_dotenv

MODULE_DIR = Path(__file__).resolve().parent
ROOT = MODULE_DIR.parent
sys.path.insert(0, str(ROOT))

from render_reports import render_reports
from schema_matches import extract_schema, score_schema_pairs
from similarity import SimilarityJudge


PIPELINE_RESULTS = ROOT / "pipeline/results"
TARGET_DATASET = ROOT / "dataset/RSchema/preprocessing/results/cleaned.jsonl"
RESULTS = MODULE_DIR / "results"
MAX_SCHEMA_ATTEMPTS = 10
ITERATION_BINS = ("0", "1-5", "6-10", "exhausted", "early-stop", "errors")
UNVERIFIED_STATUSES = {"exhausted", "early-stop"}
VERIFICATION_CRITERIA = {
    "2NF": "2NF",
    "3NF": "3NF",
    "lossless_decomposition": "Lossless join",
    "dependency_preservation": "Dependency preservation",
}
PRE_VERIFIER_FEEDBACK_PREFIXES = ("Invalid relational schema.", "Attribute coverage failed.")
TOKEN_KINDS = ("input", "output", "total")
TIME_KINDS = ("total", "python", "llm")
TOKEN_FIELDS = tuple(f"{kind}_tokens" for kind in TOKEN_KINDS)
RECORD_FIELDS = ("spec_id", "input_line", "status")
EVENT_FIELDS = ("stage", "iteration", "create_queries")
TIMING_FIELDS = ("elapsed_seconds", "llm_seconds", "pipeline_total_seconds")


def model_folders(root, selection):
    available = {
        folder.name: folder for folder in sorted(root.iterdir())
        if folder.is_dir() and folder.name.lower() != "debug"
    }
    if selection:
        missing = [name for name in selection if name not in available]
        if missing:
            raise ValueError(f"Unknown evaluation model folders: {', '.join(missing)}")
    folders = [available[name] for name in selection] if selection else list(available.values())
    if not folders:
        raise ValueError(f"No model folders found under {root}.")
    return folders


def read_targets(path):
    targets = {}
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                spec_id = row["id"]
                if type(spec_id) not in (int, str) or not str(spec_id).strip():
                    raise ValueError("Expected a nonempty dataset ID.")
                spec_id = str(spec_id)
                if spec_id in targets:
                    raise ValueError(f"Duplicate dataset ID {spec_id!r}.")
                targets[spec_id] = extract_schema(row["ddl_schema"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    if not targets:
        raise ValueError(f"No target schemas found in {path}.")
    return targets


def read_rows(path, required, optional=()):
    # Retry prompts can contain the full history and exceed the default CSV limit.
    csv.field_size_limit(max(csv.field_size_limit(), 64 * 1024 * 1024))
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        missing = set(required).difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing CSV fields: {', '.join(sorted(missing))}")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"{path}:{reader.line_num}: CSV row does not match its header.")
            yield {field: row.get(field, "") for field in (*required, *optional)}


def read_number(value, parse):
    if not value.strip():
        return None
    number = parse(value)
    if number < 0 or (parse is float and not isfinite(number)):
        raise ValueError(f"Expected a finite, nonnegative value, got {value!r}.")
    return number


def record_key(row):
    line = read_number(row["input_line"], int)
    if not row["spec_id"].strip() or not line:
        raise ValueError("Expected spec_id and a positive input_line in the pipeline report.")
    return row["spec_id"], line


def token_counts(row, extraction=None):
    counts = {}
    for kind, field in zip(TOKEN_KINDS, TOKEN_FIELDS, strict=True):
        count = read_number(row[field], int)
        counts[kind] = extraction[kind] if extraction is not None and count is None else count
    if counts["total"] is None and counts["input"] is not None and counts["output"] is not None:
        counts["total"] = counts["input"] + counts["output"]
    return counts


def read_extraction_tokens(path):
    if not path.exists():
        return {}
    extractions = {}
    for row in read_rows(path, RECORD_FIELDS, TOKEN_FIELDS):
        key = record_key(row)
        if key in extractions:
            raise ValueError(f"{path}: duplicate extraction for {key}.")
        extractions[key] = token_counts(row)
    return extractions


def required_iteration_result(status, iteration):
    """Return the LLM revision count for a verified proposal and its chart group."""
    if status == "error":
        return None, "errors"
    if iteration is not None and 1 <= iteration <= MAX_SCHEMA_ATTEMPTS:
        if status in UNVERIFIED_STATUSES:
            return None, "exhausted" if iteration == MAX_SCHEMA_ATTEMPTS else "early-stop"
        if status == "verified":
            revisions = iteration - 1
            if revisions == 0:
                return revisions, "0"
            return revisions, "1-5" if revisions <= 5 else "6-10"
    raise ValueError(f"Unexpected final status or iteration: {status!r}, {iteration!r}.")


def read_verification_checks(value):
    """Read pass/fail outcomes for the final proposal, with null for missing checks."""
    report = json.loads(value) if value.strip() else None
    if report is not None and not isinstance(report, dict):
        raise ValueError("Expected a JSON object for the verification report.")
    checks = report.get("checks") if report else None
    if checks is not None and not isinstance(checks, dict):
        raise ValueError("Expected a JSON object for verification checks.")
    outcomes = {}
    for criterion in VERIFICATION_CRITERIA:
        check = checks.get(criterion) if checks else None
        if check is not None and not isinstance(check, dict):
            raise ValueError(f"Expected a JSON object for the {criterion} verification check.")
        passed = check.get("passed") if check else None
        if passed is not None and type(passed) is not bool:
            raise ValueError(f"Expected a Boolean pass result for the {criterion} verification check.")
        outcomes[criterion] = passed
    return outcomes


def pre_verifier_rejection(row):
    """Return recorded schema-validation feedback when the verifier was skipped."""
    if (row["stage"] != "schema" or row["verification"].strip() not in ("", "null")
            or row["verification_seconds"].strip()):
        return None
    feedback = row["feedback"].strip()
    return feedback if feedback.startswith(PRE_VERIFIER_FEEDBACK_PREFIXES) else None


def known_sum(values):
    return fsum(values) if all(value is not None for value in values) else None


def measure_resources(rows, extraction):
    events = []
    for row in rows:
        stage = row["stage"]
        if stage not in {"input", "extraction", "schema"}:
            raise ValueError(f"Unexpected pipeline stage {stage!r}.")
        events.append({
            "stage": stage,
            "iteration": read_number(row["iteration"], int),
            "status": row["status"],
            "tokens": token_counts(row, extraction if stage == "extraction" else None),
            "elapsed_seconds": read_number(row["elapsed_seconds"], float),
            "llm_seconds": read_number(row["llm_seconds"], float),
        })
    requests = [event for event in events if event["stage"] != "input"]
    tokens = {}
    reporting = {}
    for kind in TOKEN_KINDS:
        values = [event["tokens"][kind] for event in requests if event["tokens"][kind] is not None]
        tokens[kind] = sum(values) if values or not requests else None
        reporting[kind] = len(values)

    total = read_number(rows[-1]["pipeline_total_seconds"], float)
    source = "pipeline_total_seconds" if total is not None else None
    if total is None:
        total = known_sum([event["elapsed_seconds"] for event in events])
        if total is not None:
            source = "sum_elapsed_seconds"
    llm = known_sum([event["llm_seconds"] for event in requests])
    python = None
    if total is not None and llm is not None:
        if llm > total and not isclose(llm, total, abs_tol=1e-6):
            raise ValueError("Summed LLM request time exceeds the total pipeline time.")
        python = max(0.0, total - llm)
    return {
        "tokens": tokens,
        "reported_token_events": reporting,
        "llm_event_count": len(requests),
        "seconds": {"total": total, "python": python, "llm": llm},
        "total_time_source": source,
        "events": events,
    }


def read_model(folder, targets):
    extractions = read_extraction_tokens(folder / "extraction_results.csv")
    by_record = {}
    for row in read_rows(
        folder / "results.csv", (*RECORD_FIELDS, *EVENT_FIELDS),
        (*TOKEN_FIELDS, *TIMING_FIELDS, "verification", "verification_seconds", "feedback"),
    ):
        by_record.setdefault(record_key(row), []).append(row)
    if not by_record:
        raise ValueError(f"{folder}/results.csv contains no pipeline events.")

    records = []
    for (spec_id, input_line), rows in sorted(by_record.items(), key=lambda item: item[0][1]):
        terminal = rows[-1]
        status = terminal["status"]
        try:
            if spec_id not in targets and status != "error":
                raise ValueError("ID was not found in the cleaned dataset.")
            ddl = json.loads(terminal["create_queries"]) if status != "error" and terminal["create_queries"] else None
            if ddl is not None and (not isinstance(ddl, list) or not all(isinstance(query, str) for query in ddl)):
                raise ValueError("Expected create_queries to be a JSON array of SQL statements.")
            iteration = read_number(terminal["iteration"], int)
            required_iterations, iteration_bin = required_iteration_result(status, iteration)
            unverified = status in UNVERIFIED_STATUSES
            records.append({
                "spec_id": spec_id,
                "input_line": input_line,
                "status": status,
                "terminal_iteration": iteration,
                "required_iterations": required_iterations,
                "required_iteration_bin": iteration_bin,
                "final_verification_checks": (
                    read_verification_checks(terminal["verification"]) if unverified else None
                ),
                "pre_verifier_rejection": pre_verifier_rejection(terminal) if unverified else None,
                "generated_schema": extract_schema(ddl) if ddl else {},
                "target_schema": targets.get(spec_id),
                **measure_resources(rows, extractions.get((spec_id, input_line))),
            })
        except ValueError as error:
            raise ValueError(f"{folder.name}, input line {input_line}, ID {spec_id!r}: {error}") from error
    return records


def mean_available(values):
    known = [value for value in values if value is not None]
    return fmean(known) if known else None


def summarize_unverified_criteria(records):
    unverified = [record for record in records if record["status"] in UNVERIFIED_STATUSES]
    checks = [record["final_verification_checks"] for record in unverified]
    failed = {
        criterion: sum(check[criterion] is False for check in checks) for criterion in VERIFICATION_CRITERIA
    }
    failed["others"] = sum(record["pre_verifier_rejection"] is not None for record in unverified)
    return {
        "record_count": len(unverified),
        "failed_counts": failed,
        "unavailable_counts": {
            criterion: sum(check[criterion] is None for check in checks) for criterion in VERIFICATION_CRITERIA
        },
    }


def summarize_model(model, records):
    counts = Counter(record["required_iteration_bin"] for record in records)
    token_means = {}
    for kind in TOKEN_KINDS:
        values = [record["tokens"][kind] for record in records if record["tokens"][kind] is not None]
        token_means[kind] = sum(values) / len(records) if values else None
    return {
        "model": model,
        "record_count": len(records),
        "required_iteration_counts": {group: counts[group] for group in ITERATION_BINS},
        "unverified_criteria": summarize_unverified_criteria(records),
        "mean_table_match_pct": {
            method: mean_available(record["tables"][f"{method}_pct"] for record in records)
            for method in ("exact", "similarity")
        },
        "mean_column_match_pct": {
            method: mean_available(record["columns"][f"{method}_pct"] for record in records)
            for method in ("exact", "similarity")
        },
        "mean_tokens": token_means,
        "reported_token_events": {
            kind: sum(record["reported_token_events"][kind] for record in records) for kind in TOKEN_KINDS
        },
        "llm_event_count": sum(record["llm_event_count"] for record in records),
        "mean_seconds": {
            kind: mean_available(record["seconds"][kind] for record in records) for kind in TIME_KINDS
        },
        "timed_record_counts": {
            kind: sum(record["seconds"][kind] is not None for record in records) for kind in TIME_KINDS
        },
    }


def save_json(path, value):
    with path.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def evaluate(folders, target_dataset, output_root, *, judge=None, similarity_model=None):
    started = datetime.now(timezone.utc)
    targets = read_targets(target_dataset)
    model_records = {}
    for folder in folders:
        print(f"Reading {folder.name}", flush=True)
        model_records[folder.name] = read_model(folder, targets)
    records = [record for records in model_records.values() for record in records]
    print(f"Scoring {len(records)} specifications across {len(folders)} model folders", flush=True)
    cases = [(record["generated_schema"], record["target_schema"] or {}) for record in records]
    for record, matches in zip(records, score_schema_pairs(cases, judge), strict=True):
        record.update(matches)

    summary = {
        "started_at": started.isoformat(),
        "target_dataset": str(target_dataset.relative_to(ROOT) if target_dataset.is_relative_to(ROOT) else target_dataset),
        "similarity_enabled": judge is not None,
        "similarity_model": similarity_model,
        "required_iteration_bins": list(ITERATION_BINS),
        "verification_criteria": {**VERIFICATION_CRITERIA, "others": "Others"},
        "models": [summarize_model(model, rows) for model, rows in model_records.items()],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / started.strftime("%Y-%m-%d_%H-%M-%S-%fZ")
    with TemporaryDirectory(prefix=".evaluation-", dir=output_root) as staged:
        stage = Path(staged)
        save_json(stage / "evaluation_metrics.json", summary)
        save_json(stage / "per_record_metrics.json", model_records)
        if judge is not None:
            save_json(stage / "similarity_decisions.json", judge.decisions())
        render_reports(stage)
        stage.rename(destination)
    return destination


def main():
    load_dotenv(ROOT / ".env")
    try:
        names = dict.fromkeys(name.strip() for name in os.getenv("EVALUATION_MODELS", "").split(",") if name.strip())
        setting = os.getenv("EVALUATION_ENABLE_SIMILARITY", "").strip().lower()
        if setting not in {"", "false", "true"}:
            raise ValueError("EVALUATION_ENABLE_SIMILARITY must be true or false.")
        folders = model_folders(PIPELINE_RESULTS, names)
        judge = None
        model = None
        if setting == "true":
            model = os.getenv("EVALUATION_SIMILARITY_MODEL", "").strip()
            api_key = os.getenv("EVALUATION_OPENAI_API_KEY", "").strip()
            if not model or not api_key:
                raise ValueError("Set EVALUATION_SIMILARITY_MODEL and EVALUATION_OPENAI_API_KEY in .env.")
            judge = SimilarityJudge(model, api_key)
        destination = evaluate(folders, TARGET_DATASET, RESULTS, judge=judge, similarity_model=model)
    except (OSError, csv.Error, ValueError, RuntimeError) as error:
        print(f"Evaluation failed. {error}", file=sys.stderr)
        return 1
    print(f"Evaluation saved to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
