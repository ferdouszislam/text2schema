from email import policy
from email.parser import BytesParser
import json
import unittest
from unittest.mock import patch

import httpx2
import openai

from pipeline.batch_api import BatchControl
from pipeline.llm import LLMError, LLMResponse
from pipeline.openai_batch import OpenAIBatchClient


class OpenAIBatchTests(unittest.TestCase):
    def test_uploads_chat_requests_and_retrieves_partial_results_by_id(self):
        messages = [{"role": "user", "content": "Propose a relation for Café."}]
        prompts = {"line-9": messages, "line-1": messages, "line-2": messages}
        paths = []

        def handle(request):
            path = request.url.path
            paths.append((request.method, path))
            self.assertEqual(request.headers["authorization"], "Bearer test-key")
            if path == "/v1/files":
                headers = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
                form = BytesParser(policy=policy.default).parsebytes(headers + request.read())
                fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                          for part in form.iter_parts()}
                self.assertEqual(fields["purpose"], b"batch")
                self.assertEqual([json.loads(line) for line in fields["file"].splitlines()], [
                    {"custom_id": key, "method": "POST", "url": "/v1/chat/completions",
                     "body": {"model": "gpt-6-luna", "messages": messages}}
                    for key in prompts
                ])
                return httpx2.Response(200, json={"id": "file-input"})
            if path == "/v1/batches":
                self.assertEqual(json.loads(request.content), {
                    "input_file_id": "file-input", "endpoint": "/v1/chat/completions", "completion_window": "24h",
                })
                return httpx2.Response(200, json={"id": "batch-1", "status": "validating"})
            if path == "/v1/batches/batch-1":
                return httpx2.Response(200, json={
                    "id": "batch-1", "status": "expired", "output_file_id": "file-output",
                    "error_file_id": "file-errors",
                })
            if path == "/v1/files/file-output/content":
                rows = [{"custom_id": "line-2", "response": {"status_code": 200, "body": {
                    "choices": [{"message": {"content": " Café(Id)\u2028\n"}}],
                    "usage": {"completion_tokens": 0},
                }}, "error": None}]
            elif path == "/v1/files/file-errors/content":
                rows = [{"custom_id": "line-9", "response": None, "error": {"code": "batch_expired"}}]
            else:
                self.fail(f"Unexpected HTTP request to {path}")
            return httpx2.Response(200, text="".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))

        real_openai = openai.OpenAI
        control = BatchControl(timeout=1, batch_timeout=1, request_delay=0, retries=0)
        with (
            httpx2.Client(transport=httpx2.MockTransport(handle)) as http_client,
            patch.object(openai, "OpenAI", side_effect=lambda **options: real_openai(http_client=http_client, **options)),
        ):
            client = OpenAIBatchClient("gpt-6-luna", api_key="test-key", control=control)
            results = client.complete_batch(prompts)

        self.assertEqual(paths, [
            ("POST", "/v1/files"), ("POST", "/v1/batches"), ("GET", "/v1/batches/batch-1"),
            ("GET", "/v1/files/file-output/content"), ("GET", "/v1/files/file-errors/content"),
        ])
        self.assertEqual(results["line-2"], LLMResponse(" Café(Id)\u2028\n", output_tokens=0))
        self.assertIsInstance(results["line-9"], LLMError)
        self.assertIn("batch_expired", str(results["line-9"]))
        self.assertIsInstance(results["line-1"], LLMError)
        self.assertIn("expired without a result", str(results["line-1"]))
