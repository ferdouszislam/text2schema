"""Run the pipeline for each JSONL specification and write CSV traces."""

from collections.abc import Callable, Iterable, Iterator
import csv
import json
import logging
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

from pipeline.llm import LLMResponse
from pipeline.run import (
    DEFAULT_MAX_ITERATIONS,
    ExtractionError,
    load_prompts,
    run_pipeline,
    validate_iteration_limit,
)


_LOGGER = logging.getLogger(__name__)
_TOKEN_COLUMNS = ("input_tokens", "output_tokens", "total_tokens")
CSV_COLUMNS = (
    "spec_id", "input_line", "stage", "iteration", "status", "database_specification",
    "prompt", "model_response", *_TOKEN_COLUMNS, "attributes", "attribute_types", "functional_dependencies",
    "relational_schema", "feedback", "verification", "create_queries",
    "elapsed_seconds", "llm_seconds", "schema_validation_seconds", "ddl_generation_seconds",
    "verification_seconds", "pipeline_total_seconds",
)
EXTRACTION_CSV_COLUMNS = (
    "spec_id", "input_line", "status", "database_specification", "prompt", "model_response",
    *_TOKEN_COLUMNS, "attributes", "attribute_types", "functional_dependencies", "feedback",
    "elapsed_seconds", "llm_seconds",
)
_JSON_COLUMNS = ("prompt", "attributes", "attribute_types", "functional_dependencies", "verification", "create_queries")


def _write_event(writers, spec_id, line_number, event, specification=""):
    row = {"spec_id": spec_id, "input_line": line_number, "database_specification": specification, **event}
    for column in _JSON_COLUMNS:
        if row.get(column) is not None:
            row[column] = json.dumps(row[column], ensure_ascii=False)
    results_writer, extraction_writer = writers
    if event["stage"] == "extraction":
        extraction_writer.writerow(row)
        for column in _TOKEN_COLUMNS:
            row.pop(column, None)
    results_writer.writerow(row)


def _parse_record(line):
    record = json.loads(line)
    if not isinstance(record, dict):
        raise ValueError("Expected a JSON object.")
    return record


def _read_specification(record, specification_field):
    specification = record.get(specification_field)
    if not isinstance(specification, str) or not specification.strip():
        raise ValueError(f"Field {specification_field!r} must contain a nonempty specification string.")
    return specification


def _nonblank_records(source: Iterable[str]) -> Iterator[tuple[int, str]]:
    for line_number, line in enumerate(source, start=1):
        if line.strip():
            yield line_number, line


def count_input_records(input_jsonl: str | Path) -> int:
    """Count the nonblank input records, including malformed records."""
    with Path(input_jsonl).open(encoding="utf-8-sig") as source:
        return sum(1 for _ in _nonblank_records(source))


def validate_record_range(start_index: int | None, end_index: int | None) -> tuple[int, int] | None:
    """Validate and return paired inclusive nonblank input indexes."""
    if start_index is None and end_index is None:
        return None
    if start_index is None or end_index is None:
        raise ValueError("Provide --start-index and --end-index together.")
    if type(start_index) is not int or type(end_index) is not int or min(start_index, end_index) < 1:
        raise ValueError("--start-index and --end-index must be positive integers.")
    if start_index > end_index:
        raise ValueError("--start-index must be less than or equal to --end-index.")
    return start_index, end_index


def _select_record_range(
    records: Iterable[tuple[int, str]], start_index: int, end_index: int,
) -> list[tuple[int, str]]:
    selected = []
    index = 0
    for index, record in enumerate(records, start=1):
        if index < start_index:
            continue
        selected.append(record)
        if index == end_index:
            return selected
    raise ValueError(f"--end-index {end_index} exceeds the number of nonblank input records ({index}).")


def _records_with_word_counts(
    records: Iterable[tuple[int, str]], specification_field: str,
) -> Iterator[tuple[int, int, str]]:
    for line_number, line in records:
        try:
            specification = _read_specification(_parse_record(line), specification_field)
        except ValueError:
            continue
        yield len(specification.split()), line_number, line


def _select_records_by_word_count(
    records: Iterable[tuple[int, str]], specification_field: str, *, longest_only: bool,
) -> list[tuple[int, str]]:
    candidates = _records_with_word_counts(records, specification_field)
    ranked = [] if longest_only else sorted(candidates)
    longest = max(candidates if longest_only else ranked, key=lambda record: record[0], default=None)
    if longest is None:
        raise ValueError(f"Input JSONL contains no nonempty specifications in field {specification_field!r}.")

    selected = [longest]
    if len(ranked) > 1:
        ranked.remove(longest)
        selected.append(ranked.pop(0))
        if ranked:
            selected.append(ranked[len(ranked) // 2])
    return [(line_number, line) for _, line_number, line in selected]


def _run_record(line, line_number, writers, llm, specification_field, id_field, pipeline_options):
    spec_id = f"line-{line_number}"
    try:
        record = _parse_record(line)
        record_id = record.get(id_field)
        if (isinstance(record_id, str) and record_id.strip()) or type(record_id) is int:
            spec_id = str(record_id)
        specification = _read_specification(record, specification_field)
    except ValueError as error:
        _LOGGER.info("Input error on line %d: %s", line_number, error)
        _write_event(writers, spec_id, line_number, {"stage": "input", "status": "error", "feedback": str(error)})
        return "errors"

    def record_event(event):
        source = specification if event["stage"] == "extraction" else ""
        _write_event(writers, spec_id, line_number, event, source)

    try:
        result = run_pipeline(specification, llm, on_event=record_event, **pipeline_options)
    except (ExtractionError, RuntimeError):
        # The pipeline has already emitted an event for the failed stage.
        return "errors"
    return result["status"]


def default_extraction_csv(output_csv: str | Path) -> Path:
    """Place the extraction CSV beside the results CSV by default."""
    path = Path(output_csv)
    return path.with_name(f"extraction_{path.name}")


def _publish_csvs(results_staged, output_path, extraction_staged, extraction_path):
    # Publish the results last and restore any prior extraction if that fails.
    previous_extraction = extraction_staged.with_name("previous.csv")
    had_extraction = extraction_path.exists() or extraction_path.is_symlink()
    if had_extraction:
        copy2(extraction_path, previous_extraction, follow_symlinks=False)
    extraction_staged.replace(extraction_path)
    try:
        results_staged.replace(output_path)
    except OSError:
        if had_extraction:
            previous_extraction.replace(extraction_path)
        else:
            extraction_path.unlink()
        raise


def run_batch(
    input_jsonl: str | Path,
    output_csv: str | Path,
    llm: Callable[[list[dict[str, str]]], str | LLMResponse],
    *,
    extraction_csv: str | Path | None = None,
    longest_specification_only: bool = False,
    debug_sample: bool = False,
    start_index: int | None = None,
    end_index: int | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    specification_field: str = "question",
    id_field: str = "id",
    extraction_prompt: str | None = None,
    schema_prompt: str | None = None,
) -> dict[str, int]:
    """Process JSONL specifications and publish two UTF-8 CSVs.

    The specification field contains the input text. The optional ID field
    supplies the source identifier, with ``line-N`` used when it is missing.
    The results CSV records the extraction and every attempted schema, with
    submitted prompts, raw replies, per-proposal token counts, and elapsed
    times in seconds. The final row for each pipeline run includes its total
    duration. The separate extraction CSV records extraction attempts with
    their token counts, request durations, and elapsed times.
    If omitted, ``extraction_csv`` defaults to ``extraction_<output name>``
    beside the results CSV. Both files are staged before publication. The
    return value counts records, verified schemas, exhausted records, early
    stops (``early-stop``), and errors.
    By default, process nonblank JSONL lines in input order. Provide both
    ``start_index`` and ``end_index`` to select a 1-based inclusive range of
    nonblank lines while preserving the original physical line numbers.
    With ``debug_sample``, select up to three valid records in longest, shortest,
    and upper-middle order by whitespace-separated word count. With
    ``longest_specification_only`` alone, select only the first valid record
    with the maximum word count.
    """
    validate_iteration_limit(max_iterations)
    record_range = validate_record_range(start_index, end_index)
    if record_range is not None and (debug_sample or longest_specification_only):
        raise ValueError("Record ranges cannot be combined with sampling.")
    extraction_prompt, schema_prompt = load_prompts(extraction_prompt, schema_prompt)
    pipeline_options = {
        "max_iterations": max_iterations,
        "extraction_prompt": extraction_prompt,
        "schema_prompt": schema_prompt,
    }

    source_path = Path(input_jsonl)
    output_path = Path(output_csv)
    extraction_path = Path(extraction_csv) if extraction_csv is not None else default_extraction_csv(output_path)
    if len({source_path.resolve(), output_path.resolve(), extraction_path.resolve()}) != 3:
        raise ValueError("The input JSONL and both output CSVs must be different files.")
    for path in (output_path, extraction_path):
        if path.exists() and not path.is_file():
            raise ValueError(f"Output CSV path is not a file: {path}")

    counts = {"records": 0, "verified": 0, "exhausted": 0, "early-stop": 0, "errors": 0}
    with source_path.open(encoding="utf-8-sig") as source:
        records: Iterable[tuple[int, str]] = _nonblank_records(source)
        if record_range is not None:
            records = _select_record_range(records, *record_range)
            _LOGGER.info("Selected nonblank input records %d-%d", *record_range)
        if debug_sample or longest_specification_only:
            records = _select_records_by_word_count(records, specification_field, longest_only=not debug_sample)
            _LOGGER.info("Selected %d record(s) by specification length", len(records))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        extraction_path.parent.mkdir(parents=True, exist_ok=True)
        with (TemporaryDirectory(dir=output_path.parent) as results_dir,
              TemporaryDirectory(dir=extraction_path.parent) as extraction_dir):
            results_staged = Path(results_dir) / "results.csv"
            extraction_staged = Path(extraction_dir) / "extraction.csv"
            with (results_staged.open("w", encoding="utf-8", newline="") as results_file,
                  extraction_staged.open("w", encoding="utf-8", newline="") as extraction_file):
                results_writer = csv.DictWriter(results_file, fieldnames=CSV_COLUMNS)
                extraction_writer = csv.DictWriter(
                    extraction_file, fieldnames=EXTRACTION_CSV_COLUMNS, extrasaction="ignore",
                )
                writers = results_writer, extraction_writer
                for writer in writers:
                    writer.writeheader()
                for line_number, line in records:
                    _LOGGER.info("Processing record %d (input line %d)", counts["records"] + 1, line_number)
                    status = _run_record(line, line_number, writers, llm, specification_field, id_field, pipeline_options)
                    counts["records"] += 1
                    counts[status] += 1
            if not counts["records"]:
                raise ValueError("Input JSONL contains no records.")
            _publish_csvs(results_staged, output_path, extraction_staged, extraction_path)
    return counts
