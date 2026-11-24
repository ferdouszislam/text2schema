from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pipeline.batch import CSV_COLUMNS, EXTRACTION_CSV_COLUMNS, run_batch
from pipeline.llm import LLMError, LLMResponse


ATTRIBUTE_TYPES = {"A": "INTEGER", "B": "INTEGER", "C": "TEXT"}
DEPENDENCIES = ["[A] -> [B]", "[B] -> [C]"]
EXTRACTION = json.dumps({
    "attribute_types": ATTRIBUTE_TYPES,
    "functional_dependencies": DEPENDENCIES,
}, indent=2)
FAILING_SCHEMA = "Record(<u>A</u>, B, C)"
VERIFIED_SCHEMA = "Mapping(<u>A</u>, B)\nDescription(<u>B</u>, C)"
TOKEN_COLUMNS = ("input_tokens", "output_tokens", "total_tokens")


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


class BatchTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.source = directory / "examples.jsonl"
        self.output = directory / "report.csv"
        self.extraction = directory / "extraction_report.csv"

    def write_input(self, *records):
        lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
        self.source.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def read_rows(self, path=None, columns=CSV_COLUMNS):
        with (self.output if path is None else path).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, list(columns))
            return list(reader)

    def read_extractions(self, path=None):
        return self.read_rows(self.extraction if path is None else path, EXTRACTION_CSV_COLUMNS)

    def token_counts(self, row):
        return tuple(row[column] for column in TOKEN_COLUMNS)

    def assert_summary(self, report, *, records, verified, exhausted, errors, early_stop=0):
        counts = ("records", "verified", "exhausted", "errors", "early-stop")
        self.assertEqual([report[key] for key in counts], [records, verified, exhausted, errors, early_stop])

    def test_csv_column_order(self):
        self.assertEqual(tuple(CSV_COLUMNS), (
            "spec_id", "input_line", "stage", "iteration", "status", "database_specification",
            "prompt", "model_response", *TOKEN_COLUMNS,
            "attributes", "attribute_types", "functional_dependencies", "relational_schema",
            "feedback", "verification", "create_queries",
        ))
        self.assertEqual(tuple(EXTRACTION_CSV_COLUMNS), (
            "spec_id", "input_line", "status", "database_specification", "prompt", "model_response",
            *TOKEN_COLUMNS, "attributes", "attribute_types",
            "functional_dependencies", "feedback",
        ))

    def test_csv_records_raw_responses_revisions_and_final_status_for_each_spec(self):
        first_spec = 'Catalog "Éditions", with code A.\nA determines B; B determines C.'
        second_spec = "A different record with the same dependencies."
        self.write_input({"id": "paper,1", "question": first_spec},
                         {"id": 208, "question": second_spec})
        raw_extraction = f"  ```json\n{EXTRACTION}\n```\n"
        raw_schema = f"```text\n{VERIFIED_SCHEMA}\n```\n"
        exhausted_schema = FAILING_SCHEMA.replace("Record(", "UpdatedRecord(")
        llm = ScriptedLLM(
            LLMResponse(raw_extraction, input_tokens=40, output_tokens=12, total_tokens=52),
            LLMResponse(FAILING_SCHEMA, input_tokens=56, output_tokens=8, total_tokens=64),
            LLMResponse(text=raw_schema, input_tokens=0, output_tokens=0, total_tokens=0),
            EXTRACTION,
            FAILING_SCHEMA,
            LLMResponse(text=exhausted_schema, input_tokens=72, total_tokens=81),
        )
        report = run_batch(self.source, self.output, llm, max_iterations=2)

        self.assert_summary(report, records=2, verified=1, exhausted=1, errors=0)
        rows = self.read_rows()
        self.assertEqual([(row["spec_id"], row["input_line"], row["stage"],
                           row["iteration"], row["status"]) for row in rows], [
            ("paper,1", "1", "extraction", "0", "extracted"),
            ("paper,1", "1", "schema", "1", "rejected"),
            ("paper,1", "1", "schema", "2", "verified"),
            ("208", "2", "extraction", "0", "extracted"),
            ("208", "2", "schema", "1", "rejected"),
            ("208", "2", "schema", "2", "exhausted"),
        ])
        self.assertEqual(rows[0]["database_specification"], first_spec)
        self.assertEqual(rows[3]["database_specification"], second_spec)
        self.assertEqual([json.loads(row["prompt"]) for row in rows], llm.calls)
        self.assertEqual([self.token_counts(row) for row in rows], [
            ("", "", ""), ("56", "8", "64"), ("0", "0", "0"),
            ("", "", ""), ("", "", ""), ("72", "", "81"),
        ])
        self.assertEqual(rows[0]["model_response"], raw_extraction)
        self.assertEqual(rows[2]["model_response"], raw_schema)
        self.assertEqual(rows[2]["relational_schema"], VERIFIED_SCHEMA)
        self.assertCountEqual(json.loads(rows[0]["attributes"]), ATTRIBUTE_TYPES)
        self.assertEqual(json.loads(rows[0]["attribute_types"]), ATTRIBUTE_TYPES)
        self.assertEqual(json.loads(rows[0]["functional_dependencies"]), DEPENDENCIES)

        first_extraction, second_extraction = self.read_extractions()
        shared_columns = (
            "spec_id", "input_line", "status", "database_specification", "prompt", "model_response",
            "attributes", "attribute_types", "functional_dependencies",
        )
        for extraction, main_row in zip((first_extraction, second_extraction), (rows[0], rows[3])):
            for column in shared_columns:
                with self.subTest(extraction=extraction["spec_id"], column=column):
                    self.assertEqual(extraction[column], main_row[column])
        self.assertEqual(self.token_counts(first_extraction), ("40", "12", "52"))
        self.assertEqual(self.token_counts(second_extraction), ("", "", ""))

        rejection = json.loads(rows[1]["verification"])
        self.assertFalse(rejection["verified"])
        self.assertEqual(rows[1]["feedback"], rejection["feedback"])
        retry_payload = json.loads(llm.calls[2][1]["content"])
        self.assertEqual(retry_payload["functional_dependencies"], DEPENDENCIES)
        self.assertEqual(retry_payload["attempt_history"], [
            {"iteration": 1, "relational_schema": FAILING_SCHEMA, "feedback": rejection["feedback"]},
        ])
        next_case_payload = json.loads(llm.calls[4][1]["content"])
        self.assertEqual(next_case_payload["database_specification"], second_spec)
        self.assertNotIn("attempt_history", next_case_payload)

        self.assertTrue(json.loads(rows[2]["verification"])["verified"])
        self.assertFalse(json.loads(rows[5]["verification"])["verified"])
        for row_index, table in ((1, "Record"), (4, "Record"), (5, "UpdatedRecord")):
            with self.subTest(row_index=row_index), closing(sqlite3.connect(":memory:")) as connection:
                statements = json.loads(rows[row_index]["create_queries"])
                self.assertEqual(len(statements), 1)
                connection.executescript(statements[0])
                columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                self.assertEqual([(row[1], row[2], row[5]) for row in columns],
                                 [("A", "INTEGER", 1), ("B", "INTEGER", 0), ("C", "TEXT", 0)])

        statements = json.loads(rows[2]["create_queries"])
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.executescript("\n".join(statements))
            columns = connection.execute('PRAGMA table_info("Description")').fetchall()
            self.assertEqual([(row[1], row[2], row[5]) for row in columns],
                             [("B", "INTEGER", 1), ("C", "TEXT", 0)])

    def test_batch_reports_early_stop_and_continues_to_the_next_record(self):
        self.write_input({"id": "repeated", "question": "First specification."},
                         {"id": "next", "question": "Second specification."})
        llm = ScriptedLLM(EXTRACTION, FAILING_SCHEMA, FAILING_SCHEMA, EXTRACTION, VERIFIED_SCHEMA)

        report = run_batch(self.source, self.output, llm, max_iterations=4)

        self.assert_summary(report, records=2, verified=1, exhausted=0, errors=0, early_stop=1)
        rows = self.read_rows()
        self.assertEqual([(row["spec_id"], row["iteration"], row["status"]) for row in rows], [
            ("repeated", "0", "extracted"), ("repeated", "1", "rejected"), ("repeated", "2", "early-stop"),
            ("next", "0", "extracted"), ("next", "1", "verified"),
        ])
        self.assertEqual(rows[2]["model_response"], rows[1]["model_response"])
        self.assertEqual(rows[2]["feedback"], rows[1]["feedback"])

    def test_malformed_input_and_model_errors_are_logged_before_batch_continues(self):
        self.write_input(
            "{bad input",
            {"id": "missing-spec"},
            {"question": "Invalid extraction case."},
            {"id": "unavailable", "question": "Model call fails during generation."},
            {"id": "recovers", "question": "A candidate can be repaired."},
        )
        malformed_extraction = "```json\n{invalid\n```"
        malformed_candidate = "```text\nNo relation declaration\n```"
        llm = ScriptedLLM(
            LLMResponse(
                malformed_extraction, input_tokens=14, output_tokens=5, total_tokens=19,
            ),
            EXTRACTION, LLMError("Model unavailable."), EXTRACTION,
            LLMResponse(
                malformed_candidate, input_tokens=25, output_tokens=5, total_tokens=30,
            ),
            VERIFIED_SCHEMA,
        )
        report = run_batch(self.source, self.output, llm, max_iterations=2)

        self.assert_summary(report, records=5, verified=1, exhausted=0, errors=4)
        rows = self.read_rows()
        self.assertEqual([(row["spec_id"], row["stage"], row["status"]) for row in rows], [
            ("line-1", "input", "error"),
            ("missing-spec", "input", "error"),
            ("line-3", "extraction", "error"),
            ("unavailable", "extraction", "extracted"),
            ("unavailable", "schema", "error"),
            ("recovers", "extraction", "extracted"),
            ("recovers", "schema", "rejected"),
            ("recovers", "schema", "verified"),
        ])
        self.assertEqual(rows[2]["model_response"], malformed_extraction)
        self.assertIn("Model unavailable.", rows[4]["feedback"])
        self.assertEqual(json.loads(rows[4]["prompt"]), llm.calls[2])
        self.assertEqual(self.token_counts(rows[4]), ("", "", ""))
        self.assertEqual(rows[6]["model_response"], malformed_candidate)
        self.assertEqual(self.token_counts(rows[6]), ("25", "5", "30"))
        self.assertIn("Invalid relational schema", rows[6]["feedback"])
        self.assertTrue(json.loads(rows[-1]["verification"])["verified"])

        extractions = self.read_extractions()
        self.assertEqual([(row["spec_id"], row["status"]) for row in extractions], [
            ("line-3", "error"), ("unavailable", "extracted"), ("recovers", "extracted"),
        ])
        self.assertEqual(extractions[0]["model_response"], malformed_extraction)
        self.assertEqual(extractions[0]["feedback"], rows[2]["feedback"])
        self.assertEqual(json.loads(extractions[0]["prompt"]), llm.calls[0])
        self.assertEqual(self.token_counts(extractions[0]), ("14", "5", "19"))

    def test_batch_accepts_custom_input_fields_and_prompts(self):
        specification = "Generate relations from this text."
        self.write_input({"case": "case-10", "requirements": specification})
        extract_prompt = "Custom extraction prompt for this dataset."
        schema_prompt = "Custom schema prompt for this dataset."
        llm = ScriptedLLM(EXTRACTION, FAILING_SCHEMA, VERIFIED_SCHEMA)
        alternate_csv = self.output.parent / "facts" / "log.csv"

        report = run_batch(str(self.source), str(self.output), llm, max_iterations=2,
                           specification_field="requirements", id_field="case",
                           extraction_prompt=extract_prompt, schema_prompt=schema_prompt,
                           extraction_csv=str(alternate_csv))

        self.assert_summary(report, records=1, verified=1, exhausted=0, errors=0)
        self.assertEqual({row["spec_id"] for row in self.read_rows()}, {"case-10"})
        extraction_rows = self.read_extractions(alternate_csv)
        self.assertEqual([row["spec_id"] for row in extraction_rows], ["case-10"])
        self.assertFalse(self.extraction.exists())
        self.assertIn(extract_prompt, llm.calls[0][0]["content"])
        for messages in llm.calls[1:]:
            self.assertIn(schema_prompt, messages[0]["content"])
            payload = json.loads(messages[1]["content"])
            self.assertEqual(payload["database_specification"], specification)
            self.assertEqual(payload["functional_dependencies"], DEPENDENCIES)

    def test_setup_error_does_not_replace_an_existing_report(self):
        self.write_input({"question": "Sample specification."})
        previous_report = b"spec_id,status\nprior,verified\n"
        self.output.write_bytes(previous_report)
        self.extraction.write_bytes(previous_report)
        source_contents = self.source.read_bytes()
        llm = ScriptedLLM()

        for options in ({"max_iterations": 0}, {"extraction_csv": self.output},
                        {"extraction_csv": self.source}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_batch(self.source, self.output, llm, **options)

        self.assertEqual(self.output.read_bytes(), previous_report)
        self.assertEqual(self.extraction.read_bytes(), previous_report)
        self.assertEqual(self.source.read_bytes(), source_contents)
        self.assertEqual(llm.calls, [])

    def test_interrupted_batch_does_not_replace_an_existing_report(self):
        self.write_input({"id": "first", "question": "First specification."},
                         {"id": "second", "question": "Second specification."})
        previous_report = b"spec_id,status\nprior,verified\n"
        self.output.write_bytes(previous_report)
        self.extraction.write_bytes(previous_report)
        llm = ScriptedLLM(EXTRACTION, VERIFIED_SCHEMA, KeyboardInterrupt())

        with self.assertRaises(KeyboardInterrupt):
            run_batch(self.source, self.output, llm)

        self.assertEqual(len(llm.calls), 3)
        self.assertEqual(self.output.read_bytes(), previous_report)
        self.assertEqual(self.extraction.read_bytes(), previous_report)

    def test_results_publication_error_restores_prior_extraction_csv(self):
        self.write_input({"id": "fresh", "question": "New specification."})
        old_results = b"spec_id,status\nprior,verified\n"
        old_extraction = b"spec_id,status\nprior,extracted\n"
        self.output.write_bytes(old_results)
        self.extraction.write_bytes(old_extraction)
        replace = Path.replace

        def fail_results_publish(staged, destination):
            if destination == self.output:
                self.assertIn(b"fresh", self.extraction.read_bytes())
                raise OSError("Results publication failed.")
            return replace(staged, destination)

        llm = ScriptedLLM(EXTRACTION, VERIFIED_SCHEMA)
        with patch.object(Path, "replace", fail_results_publish):
            with self.assertRaisesRegex(OSError, "Results publication failed"):
                run_batch(self.source, self.output, llm)

        self.assertEqual(self.output.read_bytes(), old_results)
        self.assertEqual(self.extraction.read_bytes(), old_extraction)

    def test_running_the_batch_again_replaces_both_exports(self):
        self.write_input({"id": "first", "question": "First specification."})
        run_batch(self.source, self.output, ScriptedLLM(EXTRACTION, VERIFIED_SCHEMA))
        self.write_input({"id": "second", "question": "Second specification."})
        run_batch(self.source, self.output, ScriptedLLM(EXTRACTION, VERIFIED_SCHEMA))

        self.assertEqual([row["spec_id"] for row in self.read_rows()], ["second", "second"])
        self.assertEqual([row["spec_id"] for row in self.read_extractions()], ["second"])


if __name__ == "__main__":
    unittest.main()
