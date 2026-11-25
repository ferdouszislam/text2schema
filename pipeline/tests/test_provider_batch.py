import csv
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import run_pipeline as launcher
from pipeline.batch import run_batch
from pipeline.llm import LLMClient, LLMError, LLMResponse
from pipeline.tests.test_batch import EXTRACTION, FAILING_SCHEMA, VERIFIED_SCHEMA


class ProviderBatchTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(environ, {"OPENAI_BASE_URL": "", "OPENAI_API_BASE": "", "GEMINI_API_BASE": ""}))
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.source = self.root / "specs.jsonl"
        self.config = self.root / ".env"
        self.revise = "The first schema will need a revision."
        self.verify = "The first schema will verify."
        self.fail = "The extraction request will fail."
        self.source.write_text("\n".join([
            json.dumps({"id": "same-id", "question": self.revise}),
            "{malformed",
            json.dumps({"id": "same-id", "question": self.verify}),
            json.dumps({"id": "failed", "question": self.fail}),
        ]) + "\n", encoding="utf-8")

    def configure(self, model):
        self.config.write_text(
            f"PIPELINE_MODEL={model}\n"
            "PIPELINE_BACKEND=hosted\n"
            "PIPELINE_API_KEY=test-key\n"
            "PIPELINE_INPUT_JSONL=specs.jsonl\n"
            "PIPELINE_SPEC_FIELD=question\n"
            "PIPELINE_ID_FIELD=id\n"
            "PIPELINE_TIMEOUT_SECONDS=10\n"
            "PIPELINE_BATCH_TIMEOUT_SECONDS=60\n"
            "PIPELINE_REQUEST_DELAY_SECONDS=0\n"
            "PIPELINE_MAX_ITERATIONS=2\n"
            "PIPELINE_EXTRACTION_PROMPT=extract.txt\n"
            "PIPELINE_SCHEMA_PROMPT=schema.txt\n",
            encoding="utf-8",
        )
        (self.root / "extract.txt").write_text("Extract the database facts.", encoding="utf-8")
        (self.root / "schema.txt").write_text("Propose a schema.", encoding="utf-8")

    def read_rows(self, path):
        with path.open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def test_launcher_batches_extraction_schema_and_verifier_revision(self):
        for provider, adapter in (
            ("openai", "pipeline.openai_batch.OpenAIBatchClient"),
            ("gemini", "pipeline.gemini_batch.GeminiBatchClient"),
        ):
            with self.subTest(provider=provider):
                self.configure(f"{provider}/test-model")
                rounds = []

                def complete_batch(requests):
                    payloads = {
                        key: json.loads(messages[-1]["content"])
                        for key, messages in requests.items()
                    }
                    rounds.append(list(payloads.values()))
                    results = {}
                    for key, payload in reversed(list(payloads.items())):
                        specification = payload["database_specification"]
                        if specification == self.fail:
                            results[key] = LLMError("Provider rejected this request.")
                        elif "attributes" not in payload:
                            results[key] = LLMResponse(EXTRACTION, 30, 15, 45)
                        elif specification == self.revise and "attempt_history" not in payload:
                            results[key] = LLMResponse(FAILING_SCHEMA, 50, 10, 60)
                        else:
                            results[key] = LLMResponse(VERIFIED_SCHEMA, 60, 15, 75)
                    return results

                with (
                    patch.object(launcher, "_ROOT", self.root),
                    patch(adapter) as batch_client,
                    patch.object(LLMClient, "_hosted", side_effect=AssertionError("standard hosted call")),
                    redirect_stdout(StringIO()),
                    redirect_stderr(StringIO()),
                ):
                    batch_client.return_value.complete_batch.side_effect = complete_batch
                    self.assertEqual(launcher.main(), 1)

                self.assertEqual(batch_client.call_args.args, ("test-model",))
                self.assertEqual(batch_client.call_args.kwargs["api_key"], "test-key")
                self.assertEqual([[payload["database_specification"] for payload in prompts] for prompts in rounds], [
                    [self.revise, self.verify, self.fail],
                    [self.revise, self.verify],
                    [self.revise],
                ])
                report_dir = self.root / "pipeline" / "results" / f"{provider}-test-model"
                rows = self.read_rows(report_dir / "results.csv")
                self.assertEqual([(row["input_line"], row["stage"], row["status"]) for row in rows], [
                    ("1", "extraction", "extracted"),
                    ("1", "schema", "rejected"),
                    ("1", "schema", "verified"),
                    ("2", "input", "error"),
                    ("3", "extraction", "extracted"),
                    ("3", "schema", "verified"),
                    ("4", "extraction", "error"),
                ])
                self.assertEqual(rows[0]["spec_id"], rows[4]["spec_id"])
                self.assertEqual(rounds[2][0]["attempt_history"], [{
                    "iteration": 1,
                    "relational_schema": FAILING_SCHEMA,
                    "feedback": rows[1]["feedback"],
                }])
                self.assertTrue(rows[1]["feedback"])
                self.assertTrue(json.loads(rows[2]["create_queries"]))
                self.assertEqual(rows[2]["total_tokens"], "75")
                self.assertIn("Provider rejected this request.", rows[-1]["feedback"])
                extractions = self.read_rows(report_dir / "extraction_results.csv")
                self.assertEqual([row["total_tokens"] for row in extractions], ["45", "45", ""])

    def test_custom_provider_bases_keep_standard_transport(self):
        proxy = "https://proxy.example/v1"
        for model, variable in (
            ("openai/test-model", "OPENAI_BASE_URL"),
            ("openai/test-model", "OPENAI_API_BASE"),
            ("gemini/test-model", "GEMINI_API_BASE"),
        ):
            with self.subTest(variable=variable), patch.dict(environ, {variable: proxy}):
                self.assertIsNone(LLMClient(model, api_key="test-key").batch_completion())
        self.assertIsNone(LLMClient("openai/test-model", api_base=proxy).batch_completion())

    def test_job_failure_preserves_existing_reports(self):
        results = self.root / "results.csv"
        extractions = self.root / "extraction_results.csv"
        results.write_text("previous results\n", encoding="utf-8")
        extractions.write_text("previous extractions\n", encoding="utf-8")
        llm = LLMClient("openai/test-model", api_key="test-key")

        with patch("pipeline.openai_batch.OpenAIBatchClient") as batch_client:
            batch_client.return_value.complete_batch.side_effect = LLMError("Batch status failed.")
            with self.assertRaisesRegex(LLMError, "Batch status failed"):
                run_batch(self.source, results, llm, extraction_csv=extractions)

        self.assertEqual(results.read_text(encoding="utf-8"), "previous results\n")
        self.assertEqual(extractions.read_text(encoding="utf-8"), "previous extractions\n")
