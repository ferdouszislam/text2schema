"""Send text chat requests to a hosted model or an Ollama server."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from http.client import HTTPException
import logging
from math import isfinite
from os import getenv
from random import uniform
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_HOSTED_503_RETRIES = 2
DEFAULT_BATCH_TIMEOUT_SECONDS = 49 * 60 * 60
_LOGGER = logging.getLogger(__name__)
_NO_TEXT = "The model returned no assistant text. Check that it supports text chat."
_MISSING = object()


class LLMError(RuntimeError):
    """A model request failed or did not return usable assistant text."""


@dataclass(frozen=True)
class LLMResponse:
    """Exact assistant text and any token counts reported for a model call."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class LLMClient:
    """Call a hosted provider or a native Ollama server with chat messages.

    For ``backend="hosted"``, use LiteLLM's ``provider/model`` name and
    pass the provider key, or leave the key to the provider's environment.
    Standard hosted requests can supply a JSON Schema ``response_format`` for
    models that support it.
    For ``backend="ollama"``, use the model name as installed in Ollama.
    Ollama defaults to ``http://127.0.0.1:11434`` and accepts an optional
    bearer key for authenticated servers. Set ``ollama_think`` to enable or
    disable thinking for a supported model. Omit it to use the model's default.
    Supply a base URL to override the corresponding provider endpoint, and a
    positive timeout in seconds. Set
    ``request_delay_seconds`` to wait between calls made by this client.
    ``hosted_503_retries`` sets how many times to resend a hosted request
    after HTTP 503. Set it to zero for a single attempt.
    The pipeline uses ``batch_completion`` for native OpenAI and Gemini jobs.
    ``batch_timeout_seconds`` sets the polling limit per job.

    Call the client with a list of ``{"role": ..., "content": ...}`` messages
    to get nonblank assistant text. Use ``complete`` to also get token counts
    and inspect empty replies. Request and response errors raise ``LLMError``.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        backend: str = "hosted",
        api_base: str | None = None,
        timeout: float = 120,
        request_delay_seconds: float = 0,
        hosted_503_retries: int = DEFAULT_HOSTED_503_RETRIES,
        batch_timeout_seconds: float = DEFAULT_BATCH_TIMEOUT_SECONDS,
        ollama_think: bool | None = None,
        response_format: dict | None = None,
    ):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Provide an LLM model name.")
        if backend not in ("hosted", "ollama"):
            raise ValueError("The LLM backend must be hosted or ollama.")
        if ollama_think is not None and type(ollama_think) is not bool:
            raise ValueError("Ollama thinking must be a Boolean or None.")
        model = model.strip()
        if backend == "hosted":
            provider, _, model_name = model.partition("/")
            if not provider.strip() or not model_name.strip():
                raise ValueError("Use a provider/model name for the hosted backend.")
        if not isinstance(timeout, (float, int)) or not isfinite(timeout) or timeout <= 0:
            raise ValueError("The LLM timeout must be a positive number of seconds.")
        if (not isinstance(request_delay_seconds, (float, int)) or not isfinite(request_delay_seconds)
                or request_delay_seconds < 0):
            raise ValueError("The LLM request delay must be a finite, nonnegative number of seconds.")
        if type(hosted_503_retries) is not int or hosted_503_retries < 0:
            raise ValueError("The hosted HTTP 503 retry count must be a nonnegative integer.")
        if (not isinstance(batch_timeout_seconds, (float, int))
                or not isfinite(batch_timeout_seconds) or batch_timeout_seconds <= 0):
            raise ValueError("The provider batch timeout must be a positive number of seconds.")
        if api_key is not None and (
            not isinstance(api_key, str) or not api_key.strip() or "\r" in api_key or "\n" in api_key
        ):
            raise ValueError("Set the API key to a nonblank, single-line string or omit it.")
        if api_base is not None:
            api_base = _normalize_base(api_base)

        self.model = model
        self.backend = backend
        self.api_base = api_base
        self.timeout = timeout
        self._api_key = api_key
        self._request_delay_seconds = request_delay_seconds
        self._hosted_503_retries = hosted_503_retries
        self._batch_timeout_seconds = batch_timeout_seconds
        self._ollama_think = ollama_think
        self._response_format = response_format
        self._last_request_finished: float | None = None

    def batch_completion(self):
        """Return the native batch method for a supported hosted endpoint."""
        if self.backend != "hosted":
            return None
        provider, _, model = self.model.partition("/")
        if provider == "openai":
            api_base = self.api_base or getenv("OPENAI_BASE_URL") or getenv("OPENAI_API_BASE")
            if api_base and api_base.rstrip("/") != "https://api.openai.com/v1":
                return None
            from pipeline.openai_batch import OpenAIBatchClient

            client_type = OpenAIBatchClient
        elif provider == "gemini":
            api_base = self.api_base or getenv("GEMINI_API_BASE")
            if api_base and api_base.rstrip("/") not in (
                "https://generativelanguage.googleapis.com",
                "https://generativelanguage.googleapis.com/v1beta",
            ):
                return None
            from pipeline.gemini_batch import GeminiBatchClient

            client_type = GeminiBatchClient
        else:
            return None

        from pipeline.batch_api import BatchControl

        control = BatchControl(
            timeout=self.timeout, batch_timeout=self._batch_timeout_seconds,
            request_delay=self._request_delay_seconds, retries=self._hosted_503_retries,
        )
        return client_type(model, api_key=self._api_key, control=control).complete_batch

    def __call__(self, messages: list[dict[str, str]]) -> str:
        text = self.complete(messages).text
        if not text.strip():
            raise LLMError(_NO_TEXT)
        return text

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        """Return exact assistant text and token usage from the completed model request.

        An empty reply is retained. Token counts that the backend omits stay
        ``None``. The total falls back to the sum when both counts are known.
        """
        if self._last_request_finished is not None:
            elapsed = monotonic() - self._last_request_finished
            remaining = self._request_delay_seconds - elapsed
            if remaining > 0:
                sleep(remaining)

        try:
            if self.backend == "hosted":
                return self._hosted(messages)
            return self._ollama(messages)
        finally:
            if self._request_delay_seconds:
                self._last_request_finished = monotonic()

    def _hosted(self, messages: list[dict[str, str]]) -> LLMResponse:
        try:
            import litellm
        except ImportError:
            raise LLMError("The hosted backend needs LiteLLM. Install the project requirements.") from None

        wire_usage = None

        def capture_usage(details: dict) -> None:
            # LiteLLM can fill omitted OpenAI-format usage fields with zeros.
            # The per-call callback exposes the original field presence.
            nonlocal wire_usage
            if details.get("log_event_type") != "post_api_call":
                return
            body = details.get("original_response")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except ValueError:
                    return
            if (isinstance(body, Mapping) and body.get("object") == "chat.completion"
                    and isinstance(body.get("choices"), list)):
                raw_usage = body.get("usage")
                wire_usage = {key: _token_count(_field(raw_usage, key))
                              for key in ("prompt_tokens", "completion_tokens", "total_tokens")}

        options = {
            "model": self.model,
            "timeout": self.timeout,
            "stream": False,
            "num_retries": 0,
            "max_retries": 0,
            "logger_fn": capture_usage,
        }
        if self._api_key is not None:
            options["api_key"] = self._api_key
        if self.api_base is not None:
            options["api_base"] = self.api_base
        if self._response_format is not None and litellm.supports_response_schema(model=self.model):
            options["response_format"] = self._response_format

        backoff_limit = 4.0
        for attempt in range(self._hosted_503_retries + 1):
            wire_usage = None
            try:
                response = litellm.completion(messages=[message.copy() for message in messages], **options)
            except Exception as error:
                status = getattr(error, "status_code", None)
                if status == 503:
                    if attempt == self._hosted_503_retries:
                        raise LLMError("Hosted model returned HTTP 503 (Service Unavailable).") from None
                elif isinstance(error, TimeoutError) or "Timeout" in type(error).__name__:
                    raise LLMError(
                        "The hosted model request timed out. Check the provider or increase the timeout."
                    ) from None
                else:
                    raise LLMError(_request_error("Hosted model", status)) from None
            else:
                break

            delay = max(self._request_delay_seconds, uniform(backoff_limit / 2, backoff_limit))
            _LOGGER.info("Hosted model returned HTTP 503. Retrying request (%d/%d) in %.1fs.",
                         attempt + 1, self._hosted_503_retries, delay)
            sleep(delay)
            backoff_limit = min(backoff_limit * 2, 60.0)

        try:
            choice = _field(response, "choices")[0]
        except (IndexError, KeyError, TypeError):
            raise LLMError(_NO_TEXT) from None
        usage = wire_usage if wire_usage is not None else _field(response, "usage")
        return _model_response(
            _field(choice, "message"),
            _field(usage, "prompt_tokens"),
            _field(usage, "completion_tokens"),
            _field(usage, "total_tokens"),
        )

    def _ollama(self, messages: list[dict[str, str]]) -> LLMResponse:
        base = self.api_base or "http://127.0.0.1:11434"
        payload = {"model": self.model, "messages": messages, "stream": False}
        if self._ollama_think is not None:
            payload["think"] = self._ollama_think
        request = Request(
            f"{base}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self._api_key is not None:
            request.add_unredirected_header("Authorization", f"Bearer {self._api_key}")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as error:
            error.close()
            raise LLMError(_request_error("Ollama", error.code)) from None
        except (OSError, HTTPException) as error:
            cause = error.reason if isinstance(error, URLError) else error
            if isinstance(cause, TimeoutError):
                raise LLMError("The Ollama request timed out. Check the server or increase the timeout.") from None
            raise LLMError("Could not reach Ollama. Check that it is running and the API base is correct.") from None
        except (json.JSONDecodeError, UnicodeError):
            raise LLMError("Ollama returned invalid JSON. Check that the API base points to an Ollama server.") from None

        return _model_response(
            _field(payload, "message"),
            _field(payload, "prompt_eval_count"),
            _field(payload, "eval_count"),
            _field(payload, "total_tokens"),
        )


def _field(response, name, default=None):
    if isinstance(response, Mapping):
        return response.get(name, default)
    return getattr(response, name, default)


def _token_count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _model_response(message, input_tokens, output_tokens, total_tokens) -> LLMResponse:
    content = _field(message, "content", _MISSING)
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise LLMError(_NO_TEXT)

    input_count = _token_count(input_tokens)
    output_count = _token_count(output_tokens)
    total_count = _token_count(total_tokens)
    if total_count is None and input_count is not None and output_count is not None:
        total_count = input_count + output_count
    return LLMResponse(content, input_count, output_count, total_count)


def _normalize_base(value: str) -> str:
    error = "The API base must be an HTTP(S) URL without credentials, a query, or a fragment."
    if not isinstance(value, str):
        raise ValueError(error)
    value = value.strip()
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError(error) from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
            or parsed.query or parsed.fragment or any(character.isspace() for character in value)):
        raise ValueError(error)
    return value.rstrip("/")


def _request_error(source: str, status: int | None) -> str:
    if status in (401, 403):
        return f"{source} rejected authentication. Check your API key and model access."
    if status == 404:
        return f"{source} endpoint or model was not found. Check the model name and API base."
    if status == 429:
        return f"{source} rate limited the request. Check your quota or try again later."
    if status in (408, 504):
        return f"{source} request timed out. Check the endpoint or increase the timeout."
    if isinstance(status, int):
        return f"{source} returned HTTP {status}. Check the endpoint and model settings."
    return f"{source} request failed. Check the model name, provider credentials, API base, and connectivity."
