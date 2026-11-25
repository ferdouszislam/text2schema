"""Submit file-backed text requests to the Gemini Developer Batch API."""

from __future__ import annotations

import json
import logging
from os import getenv
import re
from tempfile import TemporaryFile
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pipeline.llm import LLMError, LLMResponse, _field, _model_response, _token_count

if TYPE_CHECKING:
    from pipeline.batch_api import BatchControl


_HOST = "generativelanguage.googleapis.com"
_API_ROOT = f"https://{_HOST}"
_MAX_INPUT_BYTES = 2_000_000_000
_TERMINAL = {"SUCCEEDED", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}
_ACTIVE = {"UNSPECIFIED", "QUEUED", "PENDING", "RUNNING", "CANCELLING"}
_LOGGER = logging.getLogger(__name__)


class GeminiBatchClient:
    """Run native Gemini text batches using a single Gemini API credential."""

    def __init__(self, model: str, *, api_key: str | None, control: BatchControl):
        self._model = model.removeprefix("models/")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", self._model):
            raise ValueError("Use a Gemini model ID for Batch API requests.")
        self._api_key = api_key or getenv("GOOGLE_API_KEY") or getenv("GEMINI_API_KEY")
        if not self._api_key or not self._api_key.strip() or any(c in self._api_key for c in "\r\n"):
            raise ValueError("Set PIPELINE_API_KEY, GOOGLE_API_KEY, or GEMINI_API_KEY for Gemini Batch API.")
        self._control = control

    def complete_batch(
        self, requests: dict[str, list[dict[str, str]]],
    ) -> dict[str, LLMResponse | LLMError]:
        results: dict[str, LLMResponse | LLMError] = {}
        with TemporaryFile() as batch_file:
            keys = set()
            for key, messages in requests.items():
                try:
                    row = _input_row(key, messages)
                except LLMError as error:
                    results[key] = error
                    continue
                if len(row) > _MAX_INPUT_BYTES:
                    results[key] = LLMError("The request exceeds the Gemini batch input file size limit.")
                    continue
                if batch_file.tell() + len(row) > _MAX_INPUT_BYTES:
                    results.update(self._run_file(batch_file, keys))
                    batch_file.seek(0)
                    batch_file.truncate()
                    keys.clear()
                batch_file.write(row)
                keys.add(key)
            if keys:
                results.update(self._run_file(batch_file, keys))
        return results

    def _request(self, path, *, method="GET", data=None, headers=None):
        request = Request(_API_ROOT + path, data=data, headers=headers or {}, method=method)
        request.add_unredirected_header("x-goog-api-key", self._api_key)
        return request

    def _request_json(self, description, request, *, retry_503=False):
        def read():
            with urlopen(request, timeout=self._control.timeout) as response:
                return _read_json(response)

        return self._control.call(description, read, retry_503=retry_503)

    def _upload(self, batch_file):
        size = batch_file.tell()
        batch_file.seek(0)

        def start():
            request = self._request(
                "/upload/v1beta/files",
                method="POST",
                data=json.dumps({"file": {"displayName": "text2schema-requests.jsonl"}}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(size),
                    "X-Goog-Upload-Header-Content-Type": "application/jsonl",
                },
            )
            with urlopen(request, timeout=self._control.timeout) as response:
                return response.headers.get("X-Goog-Upload-URL")

        upload_url = self._control.call("Gemini batch input upload setup", start)
        if not _valid_upload_url(upload_url):
            raise LLMError("Gemini batch input upload returned an invalid upload URL.")

        def finish():
            request = Request(
                upload_url,
                data=batch_file,
                headers={
                    "Content-Length": str(size),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
                method="POST",
            )
            with urlopen(request, timeout=self._control.timeout) as response:
                return _read_json(response)

        info = self._control.call("Gemini batch input upload", finish)
        return _resource(_field(info.get("file"), "name"), "files", "input file")

    def _run_file(self, batch_file, keys):
        self._control.before_submit()
        _LOGGER.info("Submitting %d requests to the Gemini Batch API", len(keys))
        file_name = self._upload(batch_file)
        payload = {"batch": {"displayName": "text2schema", "inputConfig": {"fileName": file_name}}}
        request = self._request(
            f"/v1beta/models/{self._model}:batchGenerateContent",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        # The job creation API is non-idempotent. A retry could submit the same paid job twice.
        created = self._request_json("Gemini batch creation", request)
        name = _resource(created.get("name"), "batches", "job")

        def retrieve():
            return self._request_json(
                f"Gemini batch job {name} status",
                self._request(f"/v1beta/{name}"),
                retry_503=True,
            )

        job = self._control.wait("Gemini", name, retrieve, _job_state, _TERMINAL)
        state = _job_state(job)
        file_name = _output_file(job)
        results = {}
        if file_name is not None:
            file_name = _resource(file_name, "files", f"result file for job {name}")

            def download():
                request = self._request(f"/download/v1beta/{file_name}:download?alt=media")
                with urlopen(request, timeout=self._control.timeout) as response:
                    return _read_results(response, keys, name)

            results = self._control.call(f"Gemini batch job {name} result download", download, retry_503=True)
        if not results:
            detail = _error_code(job.get("error"))
            raise LLMError(f"Gemini batch job {name} ended with status {state}{detail} and returned no usable results.")
        for key in keys - results.keys():
            results[key] = LLMError(f"Gemini batch job {name} ended with status {state} without a result for this request.")
        return results


def _input_row(key, messages):
    instructions = []
    contents = []
    for message in messages:
        role = message["role"]
        part = {"text": message["content"]}
        if role in {"system", "developer"}:
            instructions.append(part)
        elif role in {"user", "assistant"}:
            contents.append({"role": "model" if role == "assistant" else "user", "parts": [part]})
        else:
            raise LLMError("Gemini batch requests only support system, developer, user, and assistant messages.")
    request = {"contents": contents}
    if instructions:
        request["systemInstruction"] = {"parts": instructions}
    return (json.dumps({"key": key, "request": request}, ensure_ascii=False) + "\n").encode("utf-8")


def _read_json(response):
    try:
        body = json.load(response)
    except ValueError:
        raise LLMError("Gemini Batch API returned invalid JSON.") from None
    if not isinstance(body, dict):
        raise LLMError("Gemini Batch API returned an invalid response.")
    return body


def _valid_upload_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname == _HOST
            and parsed.port in {None, 443}
            and parsed.username is None
            and not parsed.fragment
        )
    except ValueError:
        return False


def _resource(value, prefix, description):
    if not isinstance(value, str) or not re.fullmatch(rf"{prefix}/[A-Za-z0-9_-]+", value):
        raise LLMError(f"Gemini Batch API returned an invalid {description} name.")
    return value


def _job_state(job):
    state = _field(job.get("metadata"), "state") or job.get("state")
    if isinstance(state, str):
        state = state.removeprefix("BATCH_STATE_").removeprefix("JOB_STATE_")
        if state in _TERMINAL or state in _ACTIVE:
            return state
    if job.get("done") is True:
        if job.get("error"):
            return "FAILED"
        if _output_file(job):
            return "SUCCEEDED"
    elif state is None:
        return "PENDING"
    raise LLMError("Gemini Batch API returned an unrecognized job status.")


def _output_file(job):
    metadata = job.get("metadata")
    response = job.get("response")
    return (
        _field(_field(metadata, "output"), "responsesFile")
        or _field(_field(response, "output"), "responsesFile")
        or _field(response, "responsesFile")
        or _field(_field(job, "dest"), "fileName")
    )


def _read_results(response, keys, job_name):
    results = {}
    for line in response:
        try:
            row = json.loads(line)
        except ValueError:
            _LOGGER.warning("Gemini batch job %s returned an invalid JSONL result line", job_name)
            continue
        key = _field(row, "key")
        if not isinstance(key, str) or key not in keys:
            _LOGGER.warning("Gemini batch job %s returned a result with an unexpected request ID", job_name)
            continue
        if key in results:
            results[key] = LLMError(f"Gemini batch job {job_name} returned duplicate results for this request.")
            continue
        try:
            results[key] = _parse_result(row, job_name)
        except LLMError as error:
            results[key] = error
    return results


def _error_code(error):
    code = _field(error, "code")
    return f" (code {code})" if type(code) is int and code > 0 else ""


def _parse_result(row, job_name):
    response = row.get("response")
    error = row.get("error") or row.get("status")
    if error and (response is None or _field(error, "code") != 0):
        raise LLMError(f"Gemini batch job {job_name} failed this request{_error_code(error)}.")

    candidates = _field(response, "candidates")
    if not isinstance(candidates, list) or not candidates:
        raise LLMError(f"Gemini batch job {job_name} returned no assistant response for this request.")
    parts = _field(_field(candidates[0], "content"), "parts")
    if not isinstance(parts, list):
        parts = []
    text = "".join(
        part["text"] for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought")
    )
    usage = _field(response, "usageMetadata")
    candidate_tokens = _token_count(_field(usage, "candidatesTokenCount"))
    thought_tokens = _token_count(_field(usage, "thoughtsTokenCount"))
    output_tokens = None
    if candidate_tokens is not None or thought_tokens is not None:
        output_tokens = (candidate_tokens or 0) + (thought_tokens or 0)
    return _model_response(
        {"content": text},
        _field(usage, "promptTokenCount"),
        output_tokens,
        _field(usage, "totalTokenCount"),
    )
