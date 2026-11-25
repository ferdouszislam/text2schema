from contextlib import redirect_stderr, redirect_stdout
import csv
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, call, patch

import run_pipeline as launcher
from pipeline.llm import LLMResponse


EXTRACTION = json.dumps({
    "attribute_types": {"A": "INTEGER", "B": "INTEGER", "C": "TEXT"},
    "functional_dependencies": ["[A] -> [B]", "[B] -> [C]"],
})
FAILING_SCHEMA = "Record(<u>A</u>, B, C)"
VERIFIED_SCHEMA = "Mapping(<u>A</u>, B)\nDescription(<u>B</u>, C)"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.config = self.directory / ".env"
        self.input = self.directory / "specs.jsonl"
        self.report_root = self.directory / "pipeline" / "results"
        self.report_dir = self.report_root / "test-model"
        self.debug_report_root = self.report_root / "debug"
        self.debug_report_dir = self.debug_report_root / "test-model"
        self.results = self.report_dir / "results.csv"
        self.extraction = self.report_dir / "extraction_results.csv"
        self.extraction_prompt = self.directory / "facts.txt"
        self.schema_prompt = self.directory / "schema.txt"
        self.extraction_prompt.write_text("Extract the database facts.\n", encoding="utf-8")
        self.schema_prompt.write_text("Propose a relational schema.\n", encoding="utf-8")
        self.write_records(
            "",
            {"case": "first", "requirements": "First case. A determines B and B determines C."},
            {"case": "second", "requirements": "Second case. A determines B and B determines C."},
        )

    def write_records(self, *records):
        lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
        self.input.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def configure(self, *, max_iterations=2, debug=None, request_delay=None, hosted_503_retries=None):
        settings = {
            "PIPELINE_INPUT_JSONL": self.input.name,
            "PIPELINE_SPEC_FIELD": "requirements",
            "PIPELINE_ID_FIELD": "case",
            "PIPELINE_BACKEND": "ollama",
            "PIPELINE_MODEL": "test-model",
            "PIPELINE_API_KEY": "file-key",
            "PIPELINE_API_BASE": "http://file.example",
            "PIPELINE_TIMEOUT_SECONDS": 12,
            "PIPELINE_MAX_ITERATIONS": max_iterations,
            "PIPELINE_EXTRACTION_PROMPT": self.extraction_prompt.name,
            "PIPELINE_SCHEMA_PROMPT": self.schema_prompt.name,
        }
        if debug is not None:
            settings["debug"] = debug
        if request_delay is not None:
            settings["PIPELINE_REQUEST_DELAY_SECONDS"] = request_delay
        if hosted_503_retries is not None:
            settings["PIPELINE_HOSTED_503_RETRIES"] = hosted_503_retries
        self.config.write_text("".join(f"{key}={value}\n" for key, value in settings.items()),
                               encoding="utf-8")

    def read_csv(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def copy_launcher(self):
        script = self.directory / "run_pipeline.py"
        script.write_bytes(Path(launcher.__file__).read_bytes())
        return script

    def test_debug_cli_samples_longest_shortest_and_middle_in_separate_reports(self):
        self.configure(debug="TrUe")
        longest_specification = "A   determines\tB and B determines C."
        shortest_specification = "Tiny spec."
        middle_specification = "The schema contains three attributes."
        self.write_records(
            "",
            {"case": "shortest", "requirements": shortest_specification},
            '{"requirements": "This malformed record has more words than the others",',
            {"case": "missing", "question": "This long specification uses the wrong input field."},
            {"case": "blank", "requirements": "\n\t "},
            {"case": "longest", "requirements": longest_specification},
            {"case": "longest-tie", "requirements": "These longer identifiers increase record word count."},
            {"case": "lower-middle", "requirements": "A brief schema description."},
            {"case": "middle", "requirements": middle_specification},
            {"case": "shortest-tie", "requirements": "Brief spec."},
        )
        existing_results = b"prior batch results\n"
        existing_extraction = b"prior extraction results\n"
        self.report_dir.mkdir(parents=True)
        self.results.write_bytes(existing_results)
        self.extraction.write_bytes(existing_extraction)

        # Run the CLI from a temporary project root containing only the fixture configuration.
        script = self.copy_launcher()
        llm = Mock(side_effect=[
            EXTRACTION, FAILING_SCHEMA, VERIFIED_SCHEMA, EXTRACTION, VERIFIED_SCHEMA, EXTRACTION, VERIFIED_SCHEMA,
        ])
        stdout = StringIO()
        with (patch("pipeline.llm.LLMClient", return_value=llm),
              patch.object(sys, "argv", [str(script)]), redirect_stdout(stdout)):
            with self.assertRaises(SystemExit) as exited:
                runpy.run_path(str(script), run_name="__main__")

        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(llm.call_count, 7)
        rows = self.read_csv(self.debug_report_dir / self.results.name)
        self.assertEqual([(row["spec_id"], row["input_line"], row["status"]) for row in rows], [
            ("longest", "6", "extracted"), ("longest", "6", "rejected"), ("longest", "6", "verified"),
            ("shortest", "2", "extracted"), ("shortest", "2", "verified"),
            ("middle", "9", "extracted"), ("middle", "9", "verified"),
        ])
        submitted_specifications = [
            json.loads(llm.call_args_list[index].args[0][1]["content"])["database_specification"]
            for index in (0, 3, 5)
        ]
        self.assertEqual(submitted_specifications, [longest_specification, shortest_specification, middle_specification])
        retry_messages = llm.call_args_list[2].args[0]
        retry_history = json.loads(retry_messages[1]["content"])["attempt_history"]
        self.assertEqual(len(retry_history), 1)
        self.assertEqual(retry_history[0]["iteration"], 1)
        self.assertEqual(retry_history[0]["relational_schema"], FAILING_SCHEMA)
        self.assertIn("3NF", retry_history[0]["feedback"])
        extraction_rows = self.read_csv(self.debug_report_dir / self.extraction.name)
        self.assertEqual([(row["spec_id"], row["input_line"]) for row in extraction_rows],
                         [("longest", "6"), ("shortest", "2"), ("middle", "9")])
        self.assertIn("Processed 3 records with 3 verified", stdout.getvalue())
        self.assertIn(str(self.debug_report_dir), stdout.getvalue())
        self.assertEqual(self.results.read_bytes(), existing_results)
        self.assertEqual(self.extraction.read_bytes(), existing_extraction)

    def test_debug_obeys_the_configured_proposal_limit(self):
        self.configure(max_iterations=1, debug="true")
        self.debug_report_dir.mkdir(parents=True)
        previous_results = self.debug_report_dir / self.results.name
        previous_results.write_bytes(b"prior debug results\n")
        llm = Mock(side_effect=[EXTRACTION, FAILING_SCHEMA, EXTRACTION, FAILING_SCHEMA])
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient", return_value=llm), redirect_stdout(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(llm.call_count, 4)
        debug_dir = self.debug_report_root / "test-model-1"
        rows = self.read_csv(debug_dir / self.results.name)
        self.assertEqual([(row["spec_id"], row["status"]) for row in rows], [
            ("first", "extracted"), ("first", "exhausted"), ("second", "extracted"), ("second", "exhausted"),
        ])
        self.assertTrue((debug_dir / self.extraction.name).is_file())
        self.assertEqual(previous_results.read_bytes(), b"prior debug results\n")

    def test_launcher_reports_early_stop_with_an_unverified_exit_code(self):
        self.configure(max_iterations=4)
        self.write_records({"case": "repeated", "requirements": "A determines B and B determines C."})
        llm = Mock(side_effect=[EXTRACTION, FAILING_SCHEMA, FAILING_SCHEMA, FAILING_SCHEMA])
        stdout = StringIO()
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient", return_value=llm), redirect_stdout(stdout)):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("1 early-stop", stdout.getvalue())
        self.assertEqual(llm.call_count, 4)

    def test_normal_launcher_processes_every_record_in_numbered_run_directories(self):
        for debug, folder in ((None, "test-model"), ("FaLsE", "test-model-1"), ("false", "test-model-2")):
            with self.subTest(debug=debug, folder=folder):
                self.configure(debug=debug)
                llm = Mock(side_effect=[EXTRACTION, VERIFIED_SCHEMA, EXTRACTION, VERIFIED_SCHEMA])
                with (patch.object(launcher, "_ROOT", self.directory),
                      patch.object(launcher, "LLMClient", return_value=llm),
                      redirect_stdout(StringIO())):
                    exit_code = launcher.main()

                self.assertEqual(exit_code, 0)
                self.assertEqual(llm.call_count, 4)
                report_dir = self.report_root / folder
                self.assertEqual([row["spec_id"] for row in self.read_csv(report_dir / self.results.name)],
                                 ["first", "first", "second", "second"])
                self.assertEqual([row["spec_id"] for row in self.read_csv(report_dir / self.extraction.name)],
                                 ["first", "second"])

    def test_cli_range_counts_nonblank_records_and_keeps_original_line_numbers(self):
        self.configure()
        specification = "A determines B and B determines C."
        self.write_records(
            "", {"case": "before", "requirements": specification}, "  ",
            {"case": "first", "requirements": specification}, "", "{malformed",
            {"case": "last", "requirements": specification},
            {"case": "after", "requirements": specification},
        )
        script = self.copy_launcher()
        args = [str(script), "--start-index", "2", "--end-index", "4"]
        expected_results = [
            ("first", "4", "extraction"), ("first", "4", "schema"),
            ("line-6", "6", "input"),
            ("last", "7", "extraction"), ("last", "7", "schema"),
        ]
        for folder in ("test-model-2_4", "test-model-1-2_4"):
            llm = Mock(side_effect=[EXTRACTION, VERIFIED_SCHEMA] * 2)
            with (patch("pipeline.llm.LLMClient", return_value=llm),
                  patch.object(sys, "argv", args), redirect_stdout(StringIO()),
                  self.assertRaises(SystemExit) as exited):
                runpy.run_path(str(script), run_name="__main__")

            self.assertEqual(exited.exception.code, 1)
            self.assertEqual(llm.call_count, 4)
            report_dir = self.report_root / folder
            rows = self.read_csv(report_dir / self.results.name)
            self.assertEqual([(row["spec_id"], row["input_line"], row["stage"]) for row in rows],
                             expected_results)
            extractions = self.read_csv(report_dir / self.extraction.name)
            self.assertEqual([(row["spec_id"], row["input_line"]) for row in extractions],
                             [("first", "4"), ("last", "7")])
        self.assertCountEqual([path.name for path in self.report_root.iterdir()],
                              ["test-model-2_4", "test-model-1-2_4"])

    def test_cli_rejects_invalid_ranges_before_any_model_requests(self):
        script = self.copy_launcher()
        cases = (
            (["--start-index", "1"], None, "together"),
            (["--end-index", "2"], None, "together"),
            (["--start-index", "0", "--end-index", "2"], None, "positive integers"),
            (["--start-index", "3", "--end-index", "2"], None, "less than or equal"),
            (["--start-index", "1", "--end-index", "3"], None, "nonblank input records (2)"),
            (["--start-index", "1", "--end-index", "2"], "true", "debug=false"),
        )
        for flags, debug, message in cases:
            error = StringIO()
            self.configure(debug=debug)
            with (self.subTest(flags=flags, debug=debug),
                  patch("pipeline.llm.LLMClient") as model,
                  patch.object(sys, "argv", [str(script), *flags]), redirect_stderr(error)):
                with self.assertRaises(SystemExit) as exited:
                    runpy.run_path(str(script), run_name="__main__")

                self.assertEqual(exited.exception.code, 2)
                model.return_value.assert_not_called()
                self.assertIn(message, error.getvalue())
                self.assertEqual(list(self.report_root.glob("*")), [])

    def test_configured_record_count_uses_nonblank_lines_and_rejects_debug(self):
        self.write_records("", "{malformed", "  ", {"case": "valid", "requirements": "A database."})
        self.configure()
        with patch.object(launcher, "_ROOT", self.directory):
            self.assertEqual(launcher.configured_input_record_count(), 2)
            self.configure(debug=" TrUe ")
            with self.assertRaisesRegex(ValueError, "debug=false"):
                launcher.configured_input_record_count()

    def test_debug_parent_is_reserved_for_case_insensitive_model_names(self):
        with patch.object(launcher, "_ROOT", self.directory):
            full_run = launcher._create_run_directory("Debug", debug=False)
            debug_run = launcher._create_run_directory("Debug", debug=True)

        self.assertEqual(full_run, self.report_root / "Debug-1")
        self.assertEqual(debug_run, self.debug_report_root / "Debug")

    def test_legacy_output_settings_do_not_change_where_reports_are_written(self):
        self.configure(debug="true")
        self.write_records({"case": "only", "requirements": "A determines B and B determines C."})
        legacy_results = self.directory / "legacy_results.csv"
        legacy_extraction = self.directory / "legacy_extraction.csv"
        with self.config.open("a", encoding="utf-8") as config:
            config.write(f"PIPELINE_OUTPUT_CSV={legacy_results.name}\n")
            config.write(f"PIPELINE_EXTRACTION_CSV={legacy_extraction.name}\n")
        existing_results = b"prior batch results\n"
        existing_extraction = b"prior extraction results\n"
        legacy_results.write_bytes(existing_results)
        legacy_extraction.write_bytes(existing_extraction)
        llm = Mock(side_effect=[EXTRACTION, VERIFIED_SCHEMA])
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient", return_value=llm),
              redirect_stdout(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 0)
        self.assertTrue((self.debug_report_dir / self.results.name).is_file())
        self.assertTrue((self.debug_report_dir / self.extraction.name).is_file())
        self.assertEqual(legacy_results.read_bytes(), existing_results)
        self.assertEqual(legacy_extraction.read_bytes(), existing_extraction)

    def test_debug_reports_setup_error_without_a_valid_specification(self):
        self.configure(debug="true")
        self.write_records("", "{invalid", {"case": "missing"}, {"requirements": "\t "})
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient") as model, redirect_stderr(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 2)
        model.return_value.assert_not_called()
        self.assertFalse(self.debug_report_dir.exists())

    def test_invalid_debug_flag_fails_before_model_setup(self):
        self.configure(debug="yes")
        error = StringIO()
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient") as model, redirect_stderr(error)):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 2)
        model.assert_not_called()
        self.assertIn("debug", error.getvalue().lower())

    def test_cli_model_options_override_dotenv_independently(self):
        self.configure(hosted_503_retries=3)
        script = self.copy_launcher()
        cases = [
            (
                ["--model", "other-local-model:latest"],
                ("other-local-model:latest", "ollama", "file-key", "http://file.example", 12.0, 2, 3, 176400.0),
                "other-local-model-latest",
            ),
            (
                ["--backend", "hosted", "--model", "openai/test-model", "--api-key", "cli-key",
                 "--api-base", "https://cli.example/v1", "--timeout-seconds", "4.5",
                 "--max-iterations", "5", "--hosted-503-retries", "0", "--batch-timeout-seconds", "95000"],
                ("openai/test-model", "hosted", "cli-key", "https://cli.example/v1", 4.5, 5, 0, 95000.0),
                "openai-test-model",
            ),
            (
                ["--api-key", "", "--api-base", ""],
                ("test-model", "ollama", None, None, 12.0, 2, 3, 176400.0),
                "test-model",
            ),
        ]
        batch_results = {"records": 1, "verified": 1, "exhausted": 0, "early-stop": 0, "errors": 0}
        for args, expected, folder in cases:
            model, backend, api_key, api_base, timeout, max_iterations, hosted_503_retries, batch_timeout = expected
            with (self.subTest(args=args), patch("pipeline.llm.LLMClient") as client,
                  patch("pipeline.batch.run_batch", return_value=batch_results) as batch,
                  patch.object(sys, "argv", [str(script), *args]), redirect_stdout(StringIO())):
                with self.assertRaises(SystemExit) as exited:
                    runpy.run_path(str(script), run_name="__main__")

                self.assertEqual(exited.exception.code, 0)
                client.assert_called_once_with(
                    model, backend=backend, api_key=api_key, api_base=api_base, timeout=timeout,
                    request_delay_seconds=3.0, hosted_503_retries=hosted_503_retries,
                    batch_timeout_seconds=batch_timeout,
                )
                report_dir = self.report_root / folder
                self.assertEqual(batch.call_args.args[1], report_dir / self.results.name)
                self.assertEqual(batch.call_args.kwargs["extraction_csv"], report_dir / self.extraction.name)
                self.assertEqual(batch.call_args.kwargs["max_iterations"], max_iterations)

    def test_hosted_503_retries_keep_extraction_and_schema_iterations(self):
        self.configure(max_iterations=1, request_delay=0)
        self.write_records({"case": "first", "requirements": "A determines B and B determines C."})
        failure = RuntimeError("temporarily unavailable")
        failure.status_code = 503
        completion = Mock(side_effect=[
            failure, {"choices": [{"message": {"content": EXTRACTION}}]},
            failure, {"choices": [{"message": {"content": VERIFIED_SCHEMA}}],
                      "usage": {"prompt_tokens": 8, "completion_tokens": 4}},
        ])
        overrides = {"PIPELINE_BACKEND": "hosted", "PIPELINE_MODEL": "gemini/test-model"}

        with (patch.object(launcher, "_ROOT", self.directory),
              patch.dict(sys.modules, {"litellm": SimpleNamespace(completion=completion)}),
              patch("pipeline.llm.sleep") as sleep, redirect_stdout(StringIO()),
              self.assertLogs("pipeline.llm", level="INFO") as progress):
            self.assertEqual(launcher.main(model_overrides=overrides), 0)

        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(len(progress.records), 2)
        for record in progress.records:
            self.assertIn("HTTP 503. Retrying request (1/2)", record.getMessage())
        sent_messages = [request.kwargs["messages"] for request in completion.call_args_list]
        self.assertEqual(len(sent_messages), 4)
        self.assertEqual(sent_messages[0], sent_messages[1])
        self.assertEqual(sent_messages[2], sent_messages[3])
        rows = self.read_csv(self.report_root / "gemini-test-model" / "results.csv")
        self.assertEqual([(row["stage"], row["iteration"], row["status"]) for row in rows],
                         [("extraction", "0", "extracted"), ("schema", "1", "verified")])
        self.assertEqual(rows[1]["total_tokens"], "12")

    def test_dotenv_request_delay_applies_between_stages_and_records(self):
        self.configure(request_delay=1.5)
        events = Mock()
        events.request.side_effect = [LLMResponse(EXTRACTION), LLMResponse(VERIFIED_SCHEMA)] * 2
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher.LLMClient, "_ollama", events.request),
              patch("pipeline.llm.monotonic", return_value=0),
              patch("pipeline.llm.sleep", events.sleep), redirect_stdout(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(events.mock_calls, [
            call.request(ANY), call.sleep(1.5), call.request(ANY),
            call.sleep(1.5), call.request(ANY), call.sleep(1.5), call.request(ANY),
        ])

    def test_invalid_request_delay_fails_before_model_setup(self):
        for value in ("", "-1", "nan", "inf", "invalid"):
            with self.subTest(value=value):
                self.configure(request_delay=value)
                error = StringIO()
                with (patch.object(launcher, "_ROOT", self.directory),
                      patch.object(launcher, "LLMClient") as model, redirect_stderr(error)):
                    exit_code = launcher.main()

                self.assertEqual(exit_code, 2)
                model.assert_not_called()
                self.assertIn("PIPELINE_REQUEST_DELAY_SECONDS", error.getvalue())

    def test_removed_dry_run_argument_is_rejected(self):
        self.configure(debug="true")
        script = self.copy_launcher()
        with (patch("pipeline.llm.LLMClient") as model,
              patch.object(sys, "argv", [str(script), "--dry-run"]), redirect_stderr(StringIO())):
            with self.assertRaises(SystemExit) as exited:
                runpy.run_path(str(script), run_name="__main__")

        self.assertEqual(exited.exception.code, 2)
        model.assert_not_called()
        self.assertFalse(self.report_root.exists())


if __name__ == "__main__":
    unittest.main()
