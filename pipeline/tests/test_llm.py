import io
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError

from pipeline.llm import LLMClient, LLMError, LLMResponse


MESSAGES = [{"role": "user", "content": "Return the proposed relations."}]


class RequestDelayTests(unittest.TestCase):
    def test_spacing_uses_previous_completion_even_after_failure(self):
        for backend, model, adapter in (
            ("hosted", "openai/example-model", "_hosted"),
            ("ollama", "llama3.2", "_ollama"),
        ):
            with self.subTest(backend=backend):
                now = 10.0
                request_starts = []
                response = LLMResponse("Student(Id)")

                def advance(seconds):
                    nonlocal now
                    now += seconds

                def request(messages):
                    request_starts.append(now)
                    advance(5)
                    if len(request_starts) == 2:
                        raise LLMError("Provider unavailable")
                    return response

                client = LLMClient(model, backend=backend, request_delay_seconds=3)
                with (
                    patch("pipeline.llm.monotonic", side_effect=lambda: now),
                    patch("pipeline.llm.sleep", side_effect=advance) as sleep,
                    patch.object(client, adapter, side_effect=request),
                ):
                    self.assertEqual(client.complete(MESSAGES), response)
                    advance(1)
                    with self.assertRaisesRegex(LLMError, "Provider unavailable"):
                        client.complete(MESSAGES)
                    self.assertEqual(client.complete(MESSAGES), response)
                    advance(4)
                    self.assertEqual(client.complete(MESSAGES), response)

                self.assertEqual(request_starts, [10.0, 18.0, 26.0, 35.0])
                self.assertEqual(sleep.call_args_list, [call(2.0), call(3.0)])

    def test_zero_delay_does_not_sleep(self):
        client = LLMClient("openai/example-model", request_delay_seconds=0)
        response = LLMResponse("Student(Id)")
        with (
            patch("pipeline.llm.sleep") as sleep,
            patch.object(client, "_hosted", return_value=response) as request,
        ):
            client.complete(MESSAGES)
            client.complete(MESSAGES)
        self.assertEqual(request.call_args_list, [call(MESSAGES), call(MESSAGES)])
        sleep.assert_not_called()


class HostedClientTests(unittest.TestCase):
    def test_forwards_model_credentials_base_and_messages_with_sdk_retries_disabled(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Student(Id)"))])
        completion = Mock(return_value=response)
        client = LLMClient(
            "openai/example-model", api_key="test-hosted-key",
            api_base="https://example.invalid/v1/", timeout=20,
        )
        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
            self.assertEqual(client(MESSAGES), "Student(Id)")
        completion.assert_called_once()
        options = completion.call_args.kwargs
        self.assertTrue(callable(options["logger_fn"]))
        self.assertEqual({key: value for key, value in options.items() if key != "logger_fn"}, {
            "model": "openai/example-model", "messages": MESSAGES, "api_key": "test-hosted-key",
            "api_base": "https://example.invalid/v1", "timeout": 20, "stream": False,
            "num_retries": 0, "max_retries": 0,
        })

    def test_forwards_structured_response_format_only_for_supported_models(self):
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "decision",
                "strict": True,
                "schema": {"type": "object", "properties": {"match": {"type": "integer", "enum": [0, 1]}},
                           "required": ["match"], "additionalProperties": False},
            },
        }
        for model, supported in (("openai/gpt-6-luna", True), ("openai/gpt-3.5-turbo", False)):
            with self.subTest(model=model):
                completion = Mock(return_value={"choices": [{"message": {"content": '{"match":1}'}}]})
                supports_schema = Mock(return_value=supported)
                litellm = SimpleNamespace(completion=completion, supports_response_schema=supports_schema)
                with patch.dict(sys.modules, {"litellm": litellm}):
                    self.assertEqual(LLMClient(model, response_format=response_format)(MESSAGES), '{"match":1}')
                supports_schema.assert_called_once_with(model=model)
                completion.assert_called_once()
                if supported:
                    self.assertEqual(completion.call_args.kwargs["response_format"], response_format)
                else:
                    self.assertNotIn("response_format", completion.call_args.kwargs)

    def test_complete_retains_hosted_usage_and_exact_text(self):
        text = "\nStudent(Id)  "
        client = LLMClient("openai/example-model")
        for usage, expected in (
            (SimpleNamespace(prompt_tokens=9, completion_tokens=0, total_tokens=12),
             LLMResponse(text, input_tokens=9, output_tokens=0, total_tokens=12)),
            ({"prompt_tokens": 0, "completion_tokens": 4}, LLMResponse(text, 0, 4, 4)),
            ({"prompt_tokens": 0}, LLMResponse(text, 0)),
            ({"total_tokens": 0}, LLMResponse(text, total_tokens=0)),
            (None, LLMResponse(text)),
        ):
            with self.subTest(usage=usage):
                response = {"choices": [{"message": {"content": text}}], "usage": usage}
                completion = Mock(return_value=response)
                with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
                    self.assertEqual(client.complete(MESSAGES), expected)
                completion.assert_called_once()

    def test_complete_keeps_usage_on_empty_hosted_reply(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=0, total_tokens=5),
        )
        client = LLMClient("openai/example-model")
        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=Mock(return_value=response))}):
            self.assertEqual(client.complete(MESSAGES), LLMResponse("", 5, 0, 5))
            with self.assertRaisesRegex(LLMError, "no assistant text"):
                client(MESSAGES)

    def test_openai_usage_omissions_survive_sdk_zero_filling(self):
        client = LLMClient("openai/example-model")
        for body, sdk_usage, expected in (
            ({}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, LLMResponse("response")),
            ({"usage": {"prompt_tokens": 0}}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
             LLMResponse("response", 0)),
            ({"usage": {"prompt_tokens": 4, "completion_tokens": 6}},
             {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 0}, LLMResponse("response", 4, 6, 10)),
            ({"usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}},
             {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, LLMResponse("response", 0, 0, 0)),
        ):
            with self.subTest(body=body):
                response = {"object": "chat.completion", "choices": [{"message": {"content": "response"}}], **body}

                def completion(**options):
                    options["logger_fn"]({"log_event_type": "post_api_call", "original_response": json.dumps(response)})
                    return {**response, "usage": sdk_usage}

                with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
                    self.assertEqual(client.complete(MESSAGES), expected)

    def test_uses_normalized_counts_for_native_hosted_payload(self):
        def completion(**options):
            options["logger_fn"]({
                "log_event_type": "post_api_call",
                "original_response": '{"type":"message","usage":{"input_tokens":4,"output_tokens":6}}',
            })
            return {"choices": [{"message": {"content": "response"}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10}}

        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
            self.assertEqual(
                LLMClient("anthropic/example-model").complete(MESSAGES), LLMResponse("response", 4, 6, 10)
            )

    def test_rejects_malformed_hosted_response_and_defers_default_credentials(self):
        completion = Mock(return_value=SimpleNamespace(choices=[]))
        client = LLMClient("anthropic/example-model")
        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
            with self.assertRaisesRegex(LLMError, "no assistant text"):
                client(MESSAGES)
        self.assertNotIn("api_key", completion.call_args.kwargs)
        self.assertNotIn("api_base", completion.call_args.kwargs)

    def test_sanitizes_hosted_provider_error(self):
        failure = RuntimeError("test-hosted-key echoed in the provider error")
        failure.status_code = 401
        completion = Mock(side_effect=failure)
        with patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}):
            with self.assertRaisesRegex(LLMError, "rejected authentication") as caught:
                LLMClient("openai/example-model", api_key="test-hosted-key")(MESSAGES)
        self.assertNotIn("test-hosted-key", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        completion.assert_called_once()

    def test_hosted_503_retry_uses_fresh_messages_and_usage(self):
        failure = RuntimeError("temporarily unavailable")
        failure.status_code = 503
        sent_messages = []

        def completion(**options):
            messages = options["messages"]
            sent_messages.append([message.copy() for message in messages])
            if len(sent_messages) == 1:
                messages[0]["content"] = "Adapter changed its copy"
                options["logger_fn"]({
                    "log_event_type": "post_api_call",
                    "original_response": {"object": "chat.completion", "choices": [], "usage": {"prompt_tokens": 99}},
                })
                raise failure
            return {"choices": [{"message": {"content": "Student(Id)"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3}}

        client = LLMClient("gemini/test-model", request_delay_seconds=5)
        with (patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}),
              patch("pipeline.llm.uniform", return_value=3), patch("pipeline.llm.sleep") as sleep):
            self.assertEqual(client.complete([message.copy() for message in MESSAGES]),
                             LLMResponse("Student(Id)", 5, 3, 8))

        self.assertEqual(sent_messages, [MESSAGES, MESSAGES])
        sleep.assert_called_once_with(5)

    def test_hosted_retries_are_bounded_and_require_http_503(self):
        for status, options, calls, expected_sleeps, message in (
            (503, {}, 3, [call(4), call(8)], "HTTP 503"),
            (503, {"hosted_503_retries": 0}, 1, [], "HTTP 503"),
            (429, {}, 1, [], "rate limited"),
        ):
            failure = RuntimeError("provider error")
            failure.status_code = status
            completion = Mock(side_effect=failure)
            client = LLMClient("gemini/test-model", **options)

            with (self.subTest(status=status, options=options),
                  patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}),
                  patch("pipeline.llm.uniform", side_effect=lambda low, high: high),
                  patch("pipeline.llm.sleep") as sleep):
                with self.assertRaisesRegex(LLMError, message):
                    client.complete(MESSAGES)
                self.assertEqual(completion.call_count, calls)
                self.assertEqual(sleep.call_args_list, expected_sleeps)

    def test_missing_optional_package_gives_setup_error_on_use(self):
        client = LLMClient("openai/example-model")
        with patch.dict(sys.modules, {"litellm": None}):
            with self.assertRaisesRegex(LLMError, "Install the project requirements"):
                client(MESSAGES)


class OllamaClientTests(unittest.TestCase):
    def test_posts_native_nonstreaming_chat_to_default_endpoint(self):
        response = io.BytesIO(b'{"message":{"content":"Student(Id)"}}')
        with patch("pipeline.llm.urlopen", return_value=response) as send:
            self.assertEqual(LLMClient("llama3.2:3b", backend="ollama")(MESSAGES), "Student(Id)")
        request, = send.call_args.args
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(json.loads(request.data), {
            "model": "llama3.2:3b", "messages": MESSAGES, "stream": False,
        })
        self.assertEqual(send.call_args.kwargs, {"timeout": 120})

    def test_complete_uses_ollama_eval_counts_and_keeps_blank_text(self):
        client = LLMClient("llama3.2:3b", backend="ollama")
        for counts, expected in (
            ({"prompt_eval_count": 0, "eval_count": 8}, LLMResponse("  \n", 0, 8, 8)),
            ({"prompt_eval_count": 6}, LLMResponse("  \n", 6)),
            ({"prompt_eval_count": 2, "eval_count": 3, "total_tokens": 9}, LLMResponse("  \n", 2, 3, 9)),
            ({}, LLMResponse("  \n")),
        ):
            with self.subTest(counts=counts):
                response = io.BytesIO(json.dumps({"message": {"content": "  \n"}, **counts}).encode())
                with patch("pipeline.llm.urlopen", return_value=response) as send:
                    self.assertEqual(client.complete(MESSAGES), expected)
                send.assert_called_once()

    def test_uses_custom_base_and_sends_bearer_key_in_header_only(self):
        client = LLMClient(
            "llama3.2", backend="ollama", api_base="https://example.invalid/local/",
            api_key="test-ollama-key",
        )
        response = io.BytesIO(b'{"message":{"content":"Student(Id)"}}')
        with patch("pipeline.llm.urlopen", return_value=response) as send:
            client(MESSAGES)
        request, = send.call_args.args
        self.assertEqual(request.full_url, "https://example.invalid/local/api/chat")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-ollama-key")
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn(b"test-ollama-key", request.data)

    def test_sanitizes_http_errors_and_closes_response(self):
        client = LLMClient("llama3.2", backend="ollama", api_key="test-ollama-key")
        response = io.BytesIO(b"test-ollama-key echoed in the response body")
        failure = HTTPError("http://127.0.0.1:11434/api/chat", 404, "missing", {}, response)
        with patch("pipeline.llm.urlopen", side_effect=failure):
            with self.assertRaisesRegex(LLMError, "model was not found") as caught:
                client(MESSAGES)
        self.assertNotIn("test-ollama-key", str(caught.exception))
        self.assertTrue(response.closed)

    def test_decodes_network_and_invalid_reply_failures(self):
        client = LLMClient("llama3.2", backend="ollama")
        for failure, message in (
            (URLError(TimeoutError()), "timed out"),
            (URLError(ConnectionRefusedError()), "Could not reach Ollama"),
        ):
            with self.subTest(failure=failure), patch("pipeline.llm.urlopen", side_effect=failure):
                with self.assertRaisesRegex(LLMError, message):
                    client(MESSAGES)
        for body, message in ((b"invalid", "invalid JSON"), (b'{"message":{"content":" "}}', "no assistant text")):
            with self.subTest(body=body), patch("pipeline.llm.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaisesRegex(LLMError, message):
                    client(MESSAGES)

    def test_rejects_invalid_configuration(self):
        for model, options in (
            ("not-qualified", {}),
            ("", {"backend": "ollama"}),
            ("example-model", {"backend": "unknown"}),
            ("example-model", {"backend": "ollama", "timeout": 0}),
            ("example-model", {"backend": "ollama", "api_base": "http://user:password@example.invalid"}),
            ("example-model", {"backend": "ollama", "api_base": "http://example.invalid:not-a-port"}),
            ("example-model", {"backend": "ollama", "api_key": "test-key\r\nbad-header"}),
        ):
            with self.subTest(model=model, options=options), self.assertRaises(ValueError):
                LLMClient(model, **options)


if __name__ == "__main__":
    unittest.main()
