from contextlib import redirect_stderr, redirect_stdout
import csv
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import run_pipeline as launcher


EXTRACTION = json.dumps({
    "attribute_types": {"A": "INTEGER", "B": "INTEGER", "C": "TEXT"},
    "functional_dependencies": ["[A] -> [B]", "[B] -> [C]"],
})
FAILING_SCHEMA = "Record(<u>A</u>, B, C)"
VERIFIED_SCHEMA = "Mapping(<u>A</u>, B)\nDescription(<u>B</u>, C)"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        self.config = self.directory / ".env"
        self.input = self.directory / "specs.jsonl"
        self.results = self.directory / "reports" / "results.csv"
        self.extraction = self.directory / "facts" / "extraction.csv"
        self.debug_results = self.results.with_name("debug_results.csv")
        self.debug_extraction = self.extraction.with_name("debug_extraction.csv")
        self.results.parent.mkdir()
        self.extraction.parent.mkdir()
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

    def configure(self, *, max_iterations=2, extraction=None, debug=None):
        settings = {
            "PIPELINE_INPUT_JSONL": self.input.name,
            "PIPELINE_OUTPUT_CSV": self.results.relative_to(self.directory),
            "PIPELINE_EXTRACTION_CSV": (extraction or self.extraction).relative_to(self.directory),
            "PIPELINE_SPEC_FIELD": "requirements",
            "PIPELINE_ID_FIELD": "case",
            "PIPELINE_BACKEND": "ollama",
            "PIPELINE_MODEL": "test-model",
            "PIPELINE_TIMEOUT_SECONDS": 12,
            "PIPELINE_MAX_ITERATIONS": max_iterations,
            "PIPELINE_EXTRACTION_PROMPT": self.extraction_prompt.name,
            "PIPELINE_SCHEMA_PROMPT": self.schema_prompt.name,
        }
        if debug is not None:
            settings["debug"] = debug
        self.config.write_text("".join(f"{key}={value}\n" for key, value in settings.items()),
                               encoding="utf-8")

    def read_csv(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def copy_launcher(self):
        script = self.directory / "run_pipeline.py"
        script.write_bytes(Path(launcher.__file__).read_bytes())
        return script

    def test_debug_cli_uses_first_longest_valid_specification_and_separate_reports(self):
        self.configure(debug="TrUe")
        longest_specification = "A   determines\tB and C."
        self.write_records(
            "",
            {"case": "first", "requirements": "A tiny case."},
            '{"requirements": "This malformed record has more words than the others",',
            {"case": "missing", "question": "This long specification uses the wrong input field."},
            {"case": "blank", "requirements": "\n\t "},
            {"case": "winner", "requirements": longest_specification},
            {"case": "tie", "requirements": "Longer identifiers increase character count."},
            {"case": "last", "requirements": "A brief case."},
        )
        existing_results = b"prior batch results\n"
        existing_extraction = b"prior extraction results\n"
        self.results.write_bytes(existing_results)
        self.extraction.write_bytes(existing_extraction)

        # Run the CLI from a temporary project root containing only the fixture configuration.
        script = self.copy_launcher()
        llm = Mock(side_effect=[EXTRACTION, FAILING_SCHEMA, VERIFIED_SCHEMA])
        stdout = StringIO()
        with (patch("pipeline.llm.LLMClient", return_value=llm),
              patch.object(sys, "argv", [str(script)]), redirect_stdout(stdout)):
            with self.assertRaises(SystemExit) as exited:
                runpy.run_path(str(script), run_name="__main__")

        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(llm.call_count, 3)
        rows = self.read_csv(self.debug_results)
        self.assertEqual([(row["spec_id"], row["input_line"], row["status"]) for row in rows], [
            ("winner", "6", "extracted"), ("winner", "6", "rejected"), ("winner", "6", "verified"),
        ])
        extraction_payload = json.loads(llm.call_args_list[0].args[0][1]["content"])
        self.assertEqual(extraction_payload["database_specification"], longest_specification)
        retry_messages = llm.call_args_list[-1].args[0]
        self.assertIn("3NF", json.loads(retry_messages[1]["content"])["feedback"])
        extraction_rows = self.read_csv(self.debug_extraction)
        self.assertEqual([(row["spec_id"], row["input_line"]) for row in extraction_rows],
                         [("winner", "6")])
        self.assertIn(self.debug_results.name, stdout.getvalue())
        self.assertIn(self.debug_extraction.name, stdout.getvalue())
        self.assertEqual(self.results.read_bytes(), existing_results)
        self.assertEqual(self.extraction.read_bytes(), existing_extraction)

    def test_debug_obeys_the_configured_proposal_limit(self):
        self.configure(max_iterations=1, debug="true")
        llm = Mock(side_effect=[EXTRACTION, FAILING_SCHEMA])
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient", return_value=llm), redirect_stdout(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 1)
        self.assertEqual(llm.call_count, 2)
        self.assertEqual([row["status"] for row in self.read_csv(self.debug_results)],
                         ["extracted", "exhausted"])

    def test_normal_launcher_processes_every_record_with_configured_reports(self):
        for debug in (None, "FaLsE"):
            with self.subTest(debug=debug):
                self.configure(debug=debug)
                llm = Mock(side_effect=[EXTRACTION, VERIFIED_SCHEMA, EXTRACTION, VERIFIED_SCHEMA])
                with (patch.object(launcher, "_ROOT", self.directory),
                      patch.object(launcher, "LLMClient", return_value=llm),
                      redirect_stdout(StringIO())):
                    exit_code = launcher.main()

                self.assertEqual(exit_code, 0)
                self.assertEqual(llm.call_count, 4)
                self.assertEqual([row["spec_id"] for row in self.read_csv(self.results)],
                                 ["first", "first", "second", "second"])
                self.assertEqual([row["spec_id"] for row in self.read_csv(self.extraction)],
                                 ["first", "second"])
                self.assertFalse(self.debug_results.exists())
                self.assertFalse(self.debug_extraction.exists())

    def test_debug_cannot_overwrite_configured_full_extraction_report(self):
        self.configure(extraction=self.debug_results, debug="true")
        existing_results = b"prior batch results\n"
        existing_extraction = b"prior extraction results\n"
        self.results.write_bytes(existing_results)
        self.debug_results.write_bytes(existing_extraction)
        llm = Mock(side_effect=[EXTRACTION, VERIFIED_SCHEMA])
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient", return_value=llm),
              redirect_stderr(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 2)
        llm.assert_not_called()
        self.assertEqual(self.results.read_bytes(), existing_results)
        self.assertEqual(self.debug_results.read_bytes(), existing_extraction)

    def test_debug_reports_setup_error_without_a_valid_specification(self):
        self.configure(debug="true")
        self.write_records("", "{invalid", {"case": "missing"}, {"requirements": "\t "})
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient") as model, redirect_stderr(StringIO())):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 2)
        model.return_value.assert_not_called()
        self.assertFalse(self.debug_results.exists())
        self.assertFalse(self.debug_extraction.exists())

    def test_invalid_debug_flag_fails_before_model_setup(self):
        self.configure(debug="yes")
        error = StringIO()
        with (patch.object(launcher, "_ROOT", self.directory),
              patch.object(launcher, "LLMClient") as model, redirect_stderr(error)):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 2)
        model.assert_not_called()
        self.assertIn("debug", error.getvalue().lower())

    def test_removed_dry_run_argument_is_rejected(self):
        self.configure(debug="true")
        script = self.copy_launcher()
        with (patch("pipeline.llm.LLMClient") as model,
              patch.object(sys, "argv", [str(script), "--dry-run"]), redirect_stderr(StringIO())):
            with self.assertRaises(SystemExit) as exited:
                runpy.run_path(str(script), run_name="__main__")

        self.assertEqual(exited.exception.code, 2)
        model.assert_not_called()
        self.assertFalse(self.debug_results.exists())
        self.assertFalse(self.debug_extraction.exists())


if __name__ == "__main__":
    unittest.main()
