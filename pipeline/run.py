"""Extract schema facts, refine a relational schema, and produce SQLite DDL."""

from collections.abc import Callable
import json
import logging
from pathlib import Path
import re
from time import monotonic

from create_query_generator.create_query_generator import (
    SUPPORTED_TYPE_NAMES,
    generate_create_queries,
    normalize_attribute_types,
)
from pipeline.llm import LLMClient, LLMError, LLMResponse
from util.relational_schema import parse_identifier, parse_relational_schema
from verifier.verify import parse_functional_dependencies, verify_schema


DEFAULT_MAX_ITERATIONS = 3
_LOGGER = logging.getLogger(__name__)
_PROMPT_DIRECTORY = Path(__file__).with_name("prompts")
_OUTER_FENCE = re.compile(r"```[^\r\n`]*\r?\n(.*?)\r?\n```", re.DOTALL)


class ExtractionError(ValueError):
    """The LLM's extracted attributes, types, or dependencies were invalid."""


def load_prompts(extraction_prompt: str | None = None, schema_prompt: str | None = None) -> tuple[str, str]:
    """Load the default instructions or use supplied prompt text."""
    if extraction_prompt is None:
        extraction_prompt = (_PROMPT_DIRECTORY / "extract_fds_attributes_and_types_prompt.txt").read_text(encoding="utf-8")
    if schema_prompt is None:
        schema_prompt = (_PROMPT_DIRECTORY / "generate_relational_schema_prompt.txt").read_text(encoding="utf-8")
    if not extraction_prompt.strip() or not schema_prompt.strip():
        raise ValueError("Both pipeline prompts must contain instructions.")
    supported_types = ", ".join(sorted(SUPPORTED_TYPE_NAMES))
    return extraction_prompt.strip().replace("{{SUPPORTED_TYPES}}", supported_types), schema_prompt.strip()


def validate_iteration_limit(max_iterations: int) -> None:
    if type(max_iterations) is not int or max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer.")


def _messages(instructions, data):
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
    ]


def _request(llm, messages):
    # Keep the recorded messages intact even if an adapter rewrites its copy.
    try:
        response = llm([message.copy() for message in messages])
    except LLMError as error:
        _LOGGER.info("Model request failed: %s", error)
        raise
    if isinstance(response, LLMResponse):
        return response
    return LLMResponse(text=response if isinstance(response, str) else "")


def _unwrap(text):
    text = text.strip()
    match = _OUTER_FENCE.fullmatch(text)
    return match[1].strip() if match else text


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r}.")
        result[key] = value
    return result


def _extract(response):
    try:
        if not isinstance(response, str):
            raise ValueError("Expected a JSON object in the model's text response.")
        data = json.loads(_unwrap(response), object_pairs_hook=_unique_json_object)
        if not isinstance(data, dict) or data.keys() != {"attribute_types", "functional_dependencies"}:
            raise ValueError("Expected exactly the attribute_types and functional_dependencies fields.")
        attribute_types = data["attribute_types"]
        if not isinstance(attribute_types, dict) or not attribute_types:
            raise ValueError("attribute_types must be a nonempty object mapping names to SQL types.")
        attributes = set(attribute_types)
        for name in attribute_types:
            if parse_identifier(name, "Extracted attribute") != name:
                raise ValueError(f"Extracted attribute {name!r} has surrounding whitespace.")
        types = normalize_attribute_types(attribute_types, attributes)
        dependencies = data["functional_dependencies"]
        if not isinstance(dependencies, list):
            raise ValueError("functional_dependencies must be a list of FD strings.")
        parsed = parse_functional_dependencies(dependencies, attributes, omit_empty_rhs=True)
        return types, tuple(dependency.source for dependency in parsed)
    except ValueError as error:
        raise ExtractionError(f"Invalid LLM extraction. {error}") from None


def _prepare_candidate(schema, attribute_types):
    """Return DDL, schema validation feedback, and DDL generation feedback."""
    try:
        _, attributes = parse_relational_schema(schema)
    except ValueError as error:
        return [], f"Invalid relational schema. {error}", ""

    missing = sorted(attribute_types.keys() - attributes)
    unexpected = sorted(attributes - attribute_types.keys())
    schema_feedback = ""
    if missing or unexpected:
        schema_feedback = f"Attribute coverage failed. Missing attributes: {missing}. Unexpected attributes: {unexpected}."
    if unexpected:
        return [], schema_feedback, ""

    candidate_types = {name: sql_type for name, sql_type in attribute_types.items() if name in attributes}
    try:
        queries = generate_create_queries(schema, candidate_types)
    except ValueError as error:
        return [], schema_feedback, f"Cannot generate SQLite DDL for this schema. {error}"
    return queries, schema_feedback, ""


def _emit(callback, stage, iteration, status, messages, response, *, started_at, **fields):
    _LOGGER.info(
        "%s finished (iteration=%d, status=%s, elapsed=%.1fs)",
        stage.capitalize(), iteration, status, monotonic() - started_at,
    )
    if callback is not None:
        callback({
            "stage": stage,
            "iteration": iteration,
            "status": status,
            "prompt": messages,
            "model_response": response.text if response is not None else "",
            "input_tokens": response.input_tokens if response is not None else None,
            "output_tokens": response.output_tokens if response is not None else None,
            "total_tokens": response.total_tokens if response is not None else None,
            **fields,
        })


def run_pipeline(
    database_specification: str,
    llm: Callable[[list[dict[str, str]]], str | LLMResponse],
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    extraction_prompt: str | None = None,
    schema_prompt: str | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """Generate and verify a SQLite schema from a nonempty natural-language specification.

    ``llm`` accepts chat messages with ``role`` and ``content`` and returns the
    assistant's text or an ``LLMResponse`` with token counts. Use ``LLMClient``
    to capture token usage from hosted providers or Ollama. The
    first call extracts attribute names, SQL types, and FDs. All subsequent
    calls use that fixed extraction and the original specification. Revisions
    also receive the numbered schema attempts and their feedback in order.

    ``max_iterations`` is the positive number of schema proposals permitted,
    including the initial one. Two consecutive rejected proposals with
    identical raw responses and feedback end the loop with status ``early-stop``.
    The returned JSON-serializable dictionary has the extraction, each
    attempted schema with feedback and ``create_queries``, and the final schema
    with its queries and status. The pipeline generates
    SQLite DDL whenever the proposal and its available types allow it. A
    successful outcome requires both DDL and passing verification.
    Supply custom instruction text with ``extraction_prompt`` or
    ``schema_prompt``. ``on_event``, if provided, receives a dictionary for
    extraction (iteration zero) and for each schema proposal, with status,
    submitted messages, raw model response, available token counts, and
    the parsed results or feedback.
    Invalid extraction raises ``ExtractionError``. Model and solver errors
    propagate to the caller.
    """
    if not isinstance(database_specification, str) or not database_specification.strip():
        raise ValueError("Database specification must be nonempty text.")
    validate_iteration_limit(max_iterations)
    extraction_prompt, schema_prompt = load_prompts(extraction_prompt, schema_prompt)
    if isinstance(llm, LLMClient):
        llm = llm.complete

    inputs = {"database_specification": database_specification}
    messages = _messages(extraction_prompt, inputs)
    response = None
    _LOGGER.info("Starting extraction request")
    started_at = monotonic()
    try:
        response = _request(llm, messages)
        types, dependencies = _extract(response.text)
    except (ExtractionError, RuntimeError) as error:
        _emit(on_event, "extraction", 0, "error", messages, response, started_at=started_at, feedback=str(error))
        raise

    attributes = list(types)
    _emit(on_event, "extraction", 0, "extracted", messages, response, started_at=started_at, attributes=attributes,
          attribute_types=types, functional_dependencies=list(dependencies))
    inputs.update(attributes=attributes, functional_dependencies=dependencies)

    attempts = []
    previous_response_text = None
    for iteration in range(1, max_iterations + 1):
        if attempts:
            inputs["attempt_history"] = [
                {
                    "iteration": attempt["iteration"],
                    "relational_schema": attempt["relational_schema"],
                    "feedback": attempt["feedback"],
                }
                for attempt in attempts
            ]
        messages = _messages(schema_prompt, inputs)
        response = None
        schema = ""
        queries = None
        _LOGGER.info("Starting schema attempt %d/%d", iteration, max_iterations)
        started_at = monotonic()
        try:
            response = _request(llm, messages)
            schema = _unwrap(response.text)
            queries, feedback, ddl_feedback = _prepare_candidate(schema, types)
            verification = None if feedback else verify_schema(schema, dependencies)
        except RuntimeError as error:
            _emit(on_event, "schema", iteration, "error", messages, response,
                  started_at=started_at, relational_schema=schema, feedback=str(error), create_queries=queries)
            raise
        verified = bool(verification and verification["verified"] and queries)
        if verification is not None and (not ddl_feedback or not verification["verified"]):
            feedback = verification["feedback"]
        if ddl_feedback:
            feedback = f"{feedback}\n{ddl_feedback}".strip()
        if verified:
            status = "verified"
        elif attempts and response.text == previous_response_text and feedback == attempts[-1]["feedback"]:
            status = "early-stop"
        else:
            status = "exhausted" if iteration == max_iterations else "rejected"

        attempt = {
            "iteration": iteration,
            "relational_schema": schema,
            "feedback": feedback,
            "verification": verification,
            "create_queries": queries,
        }
        attempts.append(attempt)
        _emit(on_event, "schema", iteration, status, messages, response, started_at=started_at, relational_schema=schema,
              feedback=feedback, verification=verification, create_queries=queries)
        if status != "rejected":
            break
        previous_response_text = response.text

    return {
        "status": status,
        "verified": verified,
        "attribute_types": types,
        "functional_dependencies": list(dependencies),
        "attempts": attempts,
        "relational_schema": schema,
        "create_queries": queries,
        "feedback": feedback,
    }
