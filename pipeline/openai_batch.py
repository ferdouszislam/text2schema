"""Submit and retrieve native OpenAI Batch API chat requests."""

from __future__ import annotations

from io import BytesIO
import json
import logging
import re
from typing import TYPE_CHECKING

from pipeline.llm import LLMError, LLMResponse, _field, _model_response, _request_error

if TYPE_CHECKING:
    from pipeline.batch_api import BatchControl


_LOGGER = logging.getLogger("pipeline")
_ENDPOINT = "/v1/chat/completions"
_MAX_REQUESTS = 50_000
_MAX_INPUT_BYTES = 200_000_000
_TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}


class OpenAIBatchClient:
    def __init__(self, model: str, *, api_key: str | None, control: BatchControl):
        try:
            from openai import OpenAI, OpenAIError
        except ImportError:
            raise LLMError("The OpenAI Batch API needs the OpenAI SDK. Install the project requirements.") from None

        try:
            self._client = OpenAI(
                api_key=api_key, base_url="https://api.openai.com/v1",
                timeout=control.timeout, max_retries=0,
            )
        except OpenAIError:
            raise LLMError("Could not configure the OpenAI Batch API. Set PIPELINE_API_KEY or OPENAI_API_KEY.") from None

        self._model = model
        self._control = control

    def complete_batch(
        self, requests: dict[str, list[dict[str, str]]],
    ) -> dict[str, LLMResponse | LLMError]:
        results: dict[str, LLMResponse | LLMError] = {}
        request_ids: set[str] = set()
        with BytesIO() as payload:
            for request_id, messages in requests.items():
                line = json.dumps({
                    "custom_id": request_id, "method": "POST", "url": _ENDPOINT,
                    "body": {"model": self._model, "messages": messages},
                }, ensure_ascii=False).encode("utf-8") + b"\n"
                if len(line) > _MAX_INPUT_BYTES:
                    results[request_id] = LLMError("This request exceeds the OpenAI batch input file size limit.")
                    continue
                if len(request_ids) == _MAX_REQUESTS or payload.tell() + len(line) > _MAX_INPUT_BYTES:
                    results.update(self._submit(payload, request_ids))
                    payload.seek(0)
                    payload.truncate()
                    request_ids.clear()
                payload.write(line)
                request_ids.add(request_id)
            if request_ids:
                results.update(self._submit(payload, request_ids))
        return results

    def _submit(self, payload: BytesIO, request_ids: set[str]) -> dict[str, LLMResponse | LLMError]:
        self._control.before_submit()
        _LOGGER.info("Submitting %d requests to the OpenAI Batch API", len(request_ids))
        payload.seek(0)
        uploaded = self._control.call("OpenAI batch input upload", lambda: self._client.files.create(
            file=("requests.jsonl", payload, "application/jsonl"), purpose="batch",
        ))
        submitted = self._control.call("OpenAI batch creation", lambda: self._client.batches.create(
            input_file_id=uploaded.id, endpoint=_ENDPOINT, completion_window="24h",
        ))
        batch_id = submitted.id

        def retrieve():
            if submitted.status in _TERMINAL_STATES:
                return submitted
            return self._control.call(
                f"OpenAI batch {batch_id} status check", lambda: self._client.batches.retrieve(batch_id),
                retry_503=True,
            )

        batch = self._control.wait("OpenAI", batch_id, retrieve, lambda job: job.status, _TERMINAL_STATES)
        return self._results(batch, request_ids)

    def _results(self, batch, request_ids: set[str]) -> dict[str, LLMResponse | LLMError]:
        results: dict[str, LLMResponse | LLMError] = {}
        for file_id in (batch.output_file_id, batch.error_file_id):
            if not file_id:
                continue
            output = self._control.call(
                f"OpenAI batch {batch.id} result download", lambda: self._client.files.content(file_id),
                retry_503=True,
            )
            for line in BytesIO(output.content):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    _LOGGER.warning("OpenAI batch %s returned an invalid JSONL result line", batch.id)
                    continue
                request_id = _field(row, "custom_id")
                if not isinstance(request_id, str) or request_id not in request_ids:
                    _LOGGER.warning("OpenAI batch %s returned a result with an unexpected request ID", batch.id)
                elif request_id in results:
                    results[request_id] = LLMError(f"OpenAI batch {batch.id} returned duplicate results for the request.")
                else:
                    results[request_id] = _read_response(row)

        if batch.status != "completed" and not results:
            errors = _field(_field(batch, "errors"), "data") or []
            reason = _error_code(errors[0]) if errors else ""
            raise LLMError(f"OpenAI batch {batch.id} {batch.status}{reason} without results.")
        for request_id in request_ids - results.keys():
            results[request_id] = LLMError(f"OpenAI batch {batch.id} {batch.status} without a result for the request.")
        return results


def _error_code(error) -> str:
    code = _field(error, "code")
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", code):
        return f" ({code})"
    return ""


def _read_response(row: dict) -> LLMResponse | LLMError:
    response = row.get("response")
    status = _field(response, "status_code")
    if type(status) is int and not 200 <= status < 300:
        return LLMError(_request_error("OpenAI batch request", status))
    if row.get("error") is not None:
        return LLMError(f"OpenAI batch request failed{_error_code(row['error'])}.")

    body = _field(response, "body")
    choices = _field(body, "choices")
    if not isinstance(choices, list) or not choices:
        return LLMError("OpenAI batch request returned no assistant text.")
    usage = _field(body, "usage")
    try:
        return _model_response(
            _field(choices[0], "message"),
            _field(usage, "prompt_tokens"),
            _field(usage, "completion_tokens"),
            _field(usage, "total_tokens"),
        )
    except LLMError as error:
        return error
