"""Run the JSONL-to-CSV pipeline. Omitted model options use values from .env."""

import argparse
from pathlib import Path
import sys

from dotenv import dotenv_values

from pipeline.batch import default_extraction_csv, run_batch
from pipeline.llm import LLMClient


_ROOT = Path(__file__).resolve().parent


def _required(settings: dict[str, str | None], key: str) -> str:
    value = settings.get(key)
    if not value or not value.strip():
        raise ValueError(f"Set {key} in the pipeline .env file.")
    return value.strip()


def _read_prompt(path: Path) -> str:
    prompt = path.read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError(f"The prompt file {path} is empty.")
    return prompt


def main(
    config_path: str | Path | None = None,
    *,
    model_overrides: dict[str, str] | None = None,
) -> int:
    """Run with root-relative paths and return a process exit status."""
    settings_path = _ROOT / ".env" if config_path is None else Path(config_path)
    api_key = None
    try:
        with settings_path.open(encoding="utf-8") as config:
            settings = dotenv_values(stream=config, interpolate=False)
        if model_overrides is not None:
            settings.update(model_overrides)
        api_key = settings.get("PIPELINE_API_KEY") or None
        debug_setting = (settings.get("debug", "false") or "").strip().lower()
        if debug_setting not in ("true", "false"):
            raise ValueError("Set debug to true or false in .env.")
        debug = debug_setting == "true"

        input_jsonl = _ROOT / _required(settings, "PIPELINE_INPUT_JSONL")
        output_csv = _ROOT / _required(settings, "PIPELINE_OUTPUT_CSV")
        extraction_csv_setting = (settings.get("PIPELINE_EXTRACTION_CSV") or "").strip()
        extraction_csv = (_ROOT / extraction_csv_setting if extraction_csv_setting
                          else default_extraction_csv(output_csv))
        if debug:
            full_report_paths = {output_csv.resolve(), extraction_csv.resolve()}
            output_csv = output_csv.with_name(f"debug_{output_csv.name}")
            extraction_csv = extraction_csv.with_name(f"debug_{extraction_csv.name}")
            if {output_csv.resolve(), extraction_csv.resolve()} & full_report_paths:
                raise ValueError("Debug CSV paths must be separate from the full-run CSV paths.")
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

        extraction_path = _ROOT / _required(settings, "PIPELINE_EXTRACTION_PROMPT")
        schema_path = _ROOT / _required(settings, "PIPELINE_SCHEMA_PROMPT")
        protected_paths = {settings_path.resolve(), extraction_path.resolve(), schema_path.resolve()}
        if {output_csv.resolve(), extraction_csv.resolve()} & protected_paths:
            raise ValueError("The output CSVs must be separate from the .env and prompt files.")
        extraction_prompt = _read_prompt(extraction_path)
        schema_prompt = _read_prompt(schema_path)
        llm = LLMClient(model, backend=backend, api_key=api_key, api_base=api_base, timeout=timeout)
        results = run_batch(
            input_jsonl,
            output_csv,
            llm,
            extraction_csv=extraction_csv,
            longest_specification_only=debug,
            max_iterations=max_iterations,
            specification_field=specification_field,
            id_field=id_field,
            extraction_prompt=extraction_prompt,
            schema_prompt=schema_prompt,
        )
    except (OSError, RuntimeError, ValueError) as error:
        message = str(error)
        if api_key:
            message = message.replace(api_key, "[redacted]")
        print(f"Pipeline stopped. {message}", file=sys.stderr)
        return 2

    print(
        f"Processed {results['records']} records with {results['verified']} verified, "
        f"{results['exhausted']} exhausted, and {results['errors']} errors."
    )
    if debug:
        print(f"Debug reports\n  {output_csv}\n  {extraction_csv}")
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
    parser.add_argument("--max-iterations", dest="PIPELINE_MAX_ITERATIONS", metavar="COUNT",
                        help="Maximum schema proposals per specification.")
    raise SystemExit(main(model_overrides=vars(parser.parse_args())))
