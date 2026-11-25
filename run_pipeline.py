"""Run the JSONL-to-CSV pipeline. Omitted model options use values from .env."""

import argparse
from contextlib import suppress
import logging
from math import isfinite
from pathlib import Path
import re
import sys
from time import monotonic

from dotenv import dotenv_values

from pipeline.batch import count_input_records, default_extraction_csv, run_batch, validate_record_range
from pipeline.llm import DEFAULT_BATCH_TIMEOUT_SECONDS, DEFAULT_HOSTED_503_RETRIES, LLMClient


_ROOT = Path(__file__).resolve().parent
_LOGGER = logging.getLogger("pipeline")


def _required(settings: dict[str, str | None], key: str) -> str:
    value = settings.get(key)
    if not value or not value.strip():
        raise ValueError(f"Set {key} in the pipeline .env file.")
    return value.strip()


def _read_settings(config_path: str | Path | None) -> dict[str, str | None]:
    settings_path = _ROOT / ".env" if config_path is None else Path(config_path)
    with settings_path.open(encoding="utf-8") as config:
        return dotenv_values(stream=config, interpolate=False)


def _debug_enabled(settings: dict[str, str | None]) -> bool:
    debug_setting = (settings.get("debug", "false") or "").strip().lower()
    if debug_setting not in ("true", "false"):
        raise ValueError("Set debug to true or false in .env.")
    return debug_setting == "true"


def configured_input_record_count(config_path: str | Path | None = None) -> int:
    """Count the nonblank records in the configured input for a ranged run."""
    settings = _read_settings(config_path)
    if _debug_enabled(settings):
        raise ValueError("Set debug=false in .env before running with record indexes.")
    input_jsonl = _ROOT / _required(settings, "PIPELINE_INPUT_JSONL")
    return count_input_records(input_jsonl)


def _read_prompt(path: Path) -> str:
    prompt = path.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"The prompt file {path} is empty.")
    return prompt


def _create_run_directory(
    model: str, *, debug: bool, record_range: tuple[int, int] | None = None,
) -> Path:
    results_root = _ROOT / "pipeline" / "results"
    if debug:
        results_root /= "debug"
    results_root.mkdir(parents=True, exist_ok=True)
    model_name = re.sub(r"[^A-Za-z0-9._-]", "-", model).strip(".") or "model"
    range_suffix = "" if record_range is None else f"-{record_range[0]}_{record_range[1]}"
    # Reserve the debug parent even before the first debug run.
    suffix = 1 if not debug and not range_suffix and model_name.lower() == "debug" else 0
    while True:
        name = model_name if suffix == 0 else f"{model_name}-{suffix}"
        directory = results_root / f"{name}{range_suffix}"
        try:
            directory.mkdir()
        except FileExistsError:
            suffix += 1
        else:
            return directory


def main(
    config_path: str | Path | None = None,
    *,
    model_overrides: dict[str, str] | None = None,
    start_index: int | None = None,
    end_index: int | None = None,
) -> int:
    """Run with root-relative paths and return a process exit status."""
    api_key = None
    run_directory = None
    try:
        record_range = validate_record_range(start_index, end_index)
        settings = _read_settings(config_path)
        if model_overrides is not None:
            settings.update(model_overrides)
        api_key = settings.get("PIPELINE_API_KEY") or None
        debug = _debug_enabled(settings)
        if debug and record_range is not None:
            raise ValueError("Set debug=false in .env before running with record indexes.")

        input_jsonl = _ROOT / _required(settings, "PIPELINE_INPUT_JSONL")
        specification_field = _required(settings, "PIPELINE_SPEC_FIELD")
        id_field = _required(settings, "PIPELINE_ID_FIELD")
        backend = _required(settings, "PIPELINE_BACKEND")
        model = _required(settings, "PIPELINE_MODEL")
        api_base = settings.get("PIPELINE_API_BASE") or None
        timeout_text = _required(settings, "PIPELINE_TIMEOUT_SECONDS")
        iterations_text = _required(settings, "PIPELINE_MAX_ITERATIONS")
        try:
            timeout = float(timeout_text)
        except ValueError:
            raise ValueError("PIPELINE_TIMEOUT_SECONDS must be a positive number.") from None
        try:
            max_iterations = int(iterations_text)
        except ValueError:
            raise ValueError("PIPELINE_MAX_ITERATIONS must be a positive integer.") from None
        if max_iterations < 1:
            raise ValueError("PIPELINE_MAX_ITERATIONS must be a positive integer.")
        try:
            request_delay = float(settings.get("PIPELINE_REQUEST_DELAY_SECONDS", "3") or "")
            if not isfinite(request_delay) or request_delay < 0:
                raise ValueError
        except ValueError:
            raise ValueError("PIPELINE_REQUEST_DELAY_SECONDS must be a finite, nonnegative number.") from None
        try:
            hosted_503_retries = int(settings.get("PIPELINE_HOSTED_503_RETRIES", str(DEFAULT_HOSTED_503_RETRIES)) or "")
            if hosted_503_retries < 0:
                raise ValueError
        except ValueError:
            raise ValueError("PIPELINE_HOSTED_503_RETRIES must be a nonnegative integer.") from None
        try:
            batch_timeout = float(settings.get("PIPELINE_BATCH_TIMEOUT_SECONDS", str(DEFAULT_BATCH_TIMEOUT_SECONDS)) or "")
            if not isfinite(batch_timeout) or batch_timeout <= 0:
                raise ValueError
        except ValueError:
            raise ValueError("PIPELINE_BATCH_TIMEOUT_SECONDS must be a positive number.") from None

        extraction_path = _ROOT / _required(settings, "PIPELINE_EXTRACTION_PROMPT")
        schema_path = _ROOT / _required(settings, "PIPELINE_SCHEMA_PROMPT")
        extraction_prompt = _read_prompt(extraction_path)
        schema_prompt = _read_prompt(schema_path)
        llm = LLMClient(
            model, backend=backend, api_key=api_key, api_base=api_base, timeout=timeout,
            request_delay_seconds=request_delay, hosted_503_retries=hosted_503_retries,
            batch_timeout_seconds=batch_timeout,
        )
        run_directory = _create_run_directory(model, debug=debug, record_range=record_range)
        output_csv = run_directory / "results.csv"
        extraction_csv = default_extraction_csv(output_csv)
        _LOGGER.info(
            "Starting %s batch for %r (backend=%s, request timeout=%gs, request delay=%gs, "
            "hosted 503 retries=%d, max schema attempts=%d, input=%s)",
            "debug" if debug else "full", model, backend, timeout, request_delay,
            hosted_503_retries if backend == "hosted" else 0, max_iterations, input_jsonl,
        )
        started_at = monotonic()
        results = run_batch(
            input_jsonl,
            output_csv,
            llm,
            extraction_csv=extraction_csv,
            debug_sample=debug,
            start_index=start_index,
            end_index=end_index,
            max_iterations=max_iterations,
            specification_field=specification_field,
            id_field=id_field,
            extraction_prompt=extraction_prompt,
            schema_prompt=schema_prompt,
        )
    except (OSError, RuntimeError, ValueError) as error:
        if run_directory is not None:
            with suppress(OSError):
                run_directory.rmdir()
        message = str(error)
        if api_key:
            message = message.replace(api_key, "[redacted]")
        print(f"Pipeline stopped. {message}", file=sys.stderr)
        return 2

    _LOGGER.info("Batch finished in %.1fs", monotonic() - started_at)
    print(
        f"Processed {results['records']} records with {results['verified']} verified, "
        f"{results['exhausted']} exhausted, {results['early-stop']} early-stop, and {results['errors']} errors."
    )
    report_title = "Debug reports" if debug else "Reports"
    print(f"{report_title}\n  {output_csv}\n  {extraction_csv}")
    return 0 if results["records"] == results["verified"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, argument_default=argparse.SUPPRESS, allow_abbrev=False,
    )
    parser.add_argument("--backend", dest="PIPELINE_BACKEND", metavar="NAME",
                        help="Model backend (ollama or hosted).")
    parser.add_argument("--model", dest="PIPELINE_MODEL", metavar="NAME", help="Model name.")
    parser.add_argument("--api-key", dest="PIPELINE_API_KEY", metavar="KEY",
                        help="API key. Pass an empty string to clear it.")
    parser.add_argument("--api-base", dest="PIPELINE_API_BASE", metavar="URL",
                        help="API base URL. Pass an empty string to clear it.")
    parser.add_argument("--timeout-seconds", dest="PIPELINE_TIMEOUT_SECONDS", metavar="SECONDS",
                        help="Model request timeout in seconds.")
    parser.add_argument("--hosted-503-retries", dest="PIPELINE_HOSTED_503_RETRIES", metavar="COUNT",
                        help="Retries per hosted request after HTTP 503. Defaults to 2 if unset in .env.")
    parser.add_argument("--batch-timeout-seconds", dest="PIPELINE_BATCH_TIMEOUT_SECONDS", metavar="SECONDS",
                        help="Maximum wait per provider batch job. Defaults to 176400 seconds (49 hours).")
    parser.add_argument("--max-iterations", dest="PIPELINE_MAX_ITERATIONS", metavar="COUNT",
                        help="Maximum schema proposals per specification.")
    parser.add_argument("--start-index", type=int, metavar="INDEX",
                        help="First nonblank record (1-based, inclusive). Requires --end-index.")
    parser.add_argument("--end-index", type=int, metavar="INDEX",
                        help="Last nonblank record (1-based, inclusive). Requires --start-index.")
    model_overrides = vars(parser.parse_args())
    start_index = model_overrides.pop("start_index", None)
    end_index = model_overrides.pop("end_index", None)
    progress_handler = logging.StreamHandler()
    progress_handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%dT%H:%M:%S%z"))
    previous_level = _LOGGER.level
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.addHandler(progress_handler)
    try:
        raise SystemExit(main(model_overrides=model_overrides, start_index=start_index, end_index=end_index))
    finally:
        _LOGGER.removeHandler(progress_handler)
        _LOGGER.setLevel(previous_level)
