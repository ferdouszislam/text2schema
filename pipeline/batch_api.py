"""Timeouts, polling, and safe retries for provider Batch API jobs."""

from http.client import HTTPException
import logging
from random import uniform
from time import monotonic, sleep
from urllib.error import HTTPError, URLError

from pipeline.llm import LLMError, _request_error


_LOGGER = logging.getLogger(__name__)
_POLL_SECONDS = 30


class BatchControl:
    """Apply the pipeline's request and job timing settings to one provider."""

    def __init__(self, *, timeout, batch_timeout, request_delay, retries):
        self.timeout = timeout
        self.batch_timeout = batch_timeout
        self.request_delay = request_delay
        self.retries = retries
        self._last_job_finished = None

    def call(self, description, operation, *, retry_503=False):
        retries = self.retries if retry_503 else 0
        for attempt in range(retries + 1):
            try:
                return operation()
            except LLMError:
                raise
            except Exception as error:
                status = getattr(error, "status_code", None)
                if isinstance(error, HTTPError):
                    status = error.code
                    error.close()
                if status == 503 and attempt < retries:
                    limit = min(4 * 2 ** min(attempt, 4), 60)
                    delay = max(self.request_delay, uniform(limit / 2, limit))
                    _LOGGER.warning("%s returned HTTP 503. Retrying in %.1fs.", description, delay)
                    sleep(delay)
                    continue
                if (isinstance(error, TimeoutError) or "Timeout" in type(error).__name__
                        or isinstance(error, URLError) and isinstance(error.reason, TimeoutError)):
                    raise LLMError(f"{description} timed out.") from None
                if (status is not None or isinstance(error, (OSError, HTTPException))
                        or type(error).__module__.split(".")[0] == "openai"):
                    raise LLMError(_request_error(description, status)) from None
                raise

    def wait(self, provider, job_id, retrieve, status_of, terminal_states):
        """Poll a submitted job until it finishes or reaches the wait limit."""
        deadline = monotonic() + self.batch_timeout
        _LOGGER.info("%s batch job %s submitted", provider, job_id)
        status = None
        try:
            while status is None or monotonic() < deadline:
                job = retrieve()
                previous_status, status = status, status_of(job)
                if status != previous_status:
                    _LOGGER.info("%s batch job %s status: %s", provider, job_id, status)
                if status in terminal_states:
                    return job
                remaining = deadline - monotonic()
                if remaining > 0:
                    sleep(min(_POLL_SECONDS, remaining))
            raise LLMError(f"{provider} batch job {job_id} is still {status} after "
                           f"{self.batch_timeout:g}s. Check the job with the provider.")
        finally:
            self._last_job_finished = monotonic()

    def before_submit(self):
        """Pace successive provider jobs without delaying the first job."""
        if self._last_job_finished is not None:
            remaining = self.request_delay - (monotonic() - self._last_job_finished)
            if remaining > 0:
                sleep(remaining)
