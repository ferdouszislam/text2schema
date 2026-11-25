"""Exercise Gemini's native batch transport using mock HTTP responses."""

from io import BytesIO
import json
import unittest
from unittest.mock import patch

from pipeline.batch_api import BatchControl
from pipeline.gemini_batch import GeminiBatchClient
from pipeline.llm import LLMError, LLMResponse


_API = "https://generativelanguage.googleapis.com"
_UPLOAD = f"{_API}/upload/v1beta/files"
_UPLOAD_SESSION = f"{_UPLOAD}?upload_id=example"
_CREATE = f"{_API}/v1beta/models/gemini-test:batchGenerateContent"
_JOB = f"{_API}/v1beta/batches/job-id"
_DOWNLOAD = f"{_API}/download/v1beta/files/batch-result:download?alt=media"
_MESSAGES = [{"role": "system", "content": "Respond in JSON"}, {"role": "user", "content": "Data é"}]


class _Response(BytesIO):
    def __init__(self, body=None, *, headers=None):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        self.headers = headers or {}


class GeminiBatchTests(unittest.TestCase):
    def setUp(self):
        control = BatchControl(timeout=12, batch_timeout=5, request_delay=0, retries=0)
        self.client = GeminiBatchClient("gemini-test", api_key="mock-key", control=control)

    def test_upload_create_poll_and_resolve_partial_results_by_key(self):
        def finish_upload(request):
            data = request.data.read()
            self.assertEqual(int(request.get_header("Content-length")), len(data))
            self.assertIsNone(request.get_header("X-goog-api-key"))
            rows = [json.loads(line) for line in data.splitlines()]
            self.assertEqual([row["key"] for row in rows], ["record-1", "record-2", "record-3"])
            self.assertEqual(rows[0]["request"], {
                "systemInstruction": {"parts": [{"text": "Respond in JSON"}]},
                "contents": [{"role": "user", "parts": [{"text": "Data é"}]}],
            })
            return _Response({"file": {"name": "files/request-input"}})

        results = [
            {"key": "record-2", "status": {"code": 3, "message": "invalid record"}},
            {"key": "record-1", "response": {
                "candidates": [{"content": {"parts": [
                    {"text": "private reasoning", "thought": True}, {"text": "  {"}, {"text": "}\n"},
                ]}}],
                "usageMetadata": {
                    "promptTokenCount": 20, "candidatesTokenCount": 4, "thoughtsTokenCount": 7,
                    "totalTokenCount": 31,
                },
            }},
        ]
        responses = {
            _UPLOAD: _Response(headers={"X-Goog-Upload-URL": _UPLOAD_SESSION}),
            _CREATE: _Response({"name": "batches/job-id"}),
            _JOB: _Response({
                "done": True, "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
                "response": {"output": {"responsesFile": "files/batch-result"}},
            }),
            _DOWNLOAD: _Response(b"\n".join(json.dumps(row).encode("utf-8") for row in results)),
        }

        def open_url(request, *, timeout):
            self.assertEqual(timeout, 12)
            if request.full_url == _UPLOAD_SESSION:
                return finish_upload(request)
            self.assertEqual(request.get_header("X-goog-api-key"), "mock-key")
            if request.full_url == _CREATE:
                self.assertEqual(json.loads(request.data)["batch"]["inputConfig"]["fileName"],
                                 "files/request-input")
            return responses[request.full_url]

        with patch("pipeline.gemini_batch.urlopen", side_effect=open_url) as http:
            actual = self.client.complete_batch(dict.fromkeys(["record-1", "record-2", "record-3"], _MESSAGES))

        self.assertEqual([call.args[0].full_url for call in http.call_args_list],
                         [_UPLOAD, _UPLOAD_SESSION, _CREATE, _JOB, _DOWNLOAD])
        self.assertEqual(actual["record-1"], LLMResponse("  {}\n", 20, 11, 31))
        self.assertIsInstance(actual["record-2"], LLMError)
        self.assertIn("code 3", str(actual["record-2"]))
        self.assertIsInstance(actual["record-3"], LLMError)
        self.assertIn("without a result", str(actual["record-3"]))

    def test_terminal_job_without_results_raises(self):
        for state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED", "JOB_STATE_SUCCEEDED"):
            with self.subTest(state=state):
                responses = [
                    _Response(headers={"X-Goog-Upload-URL": _UPLOAD_SESSION}),
                    _Response({"file": {"name": "files/request-input"}}),
                    _Response({"name": "batches/job-id"}),
                    _Response({"state": state, "done": True}),
                ]
                with patch("pipeline.gemini_batch.urlopen", side_effect=responses) as http:
                    with self.assertRaisesRegex(LLMError, f"batches/job-id.*{state.removeprefix('JOB_STATE_')}"):
                        self.client.complete_batch({"record-1": _MESSAGES})
                self.assertEqual(http.call_count, 4)
