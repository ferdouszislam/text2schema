from contextlib import closing
import json
import sqlite3
import unittest
from unittest.mock import patch

from create_query_generator.create_query_generator import generate_create_queries
from pipeline.llm import LLMResponse
from pipeline.run import ExtractionError, run_pipeline
from verifier.verify import verify_schema


SPECIFICATION = "A determines B, B determines C, and each record may have notes."
ATTRIBUTE_TYPES = {"A": "INTEGER", "B": "INTEGER", "C": "TEXT", "Notes": "TEXT"}
DEPENDENCIES = ["[A] -> [B]", "[B] -> [C]"]
EXTRACTION = json.dumps({
    "attribute_types": ATTRIBUTE_TYPES,
    "functional_dependencies": DEPENDENCIES,
})
FAILING_SCHEMA = "Record(<u>A</u>, B, C, <u>Notes</u>)"
PARTIALLY_REVISED_SCHEMA = "Record(<u>A</u>, <u>Notes</u>)\nMapping(<u>A</u>, B, C)"
VERIFIED_SCHEMA = """\
Record(<u>A</u>, <u>Notes</u>)
Mapping(<u>A</u>, B)
Description(<u>B</u>, C)"""


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return next(self.responses)


class PipelineTests(unittest.TestCase):
    def user_payload(self, messages):
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        return json.loads(messages[1]["content"])

    def assert_attempt_history(self, messages, *attempts):
        self.assertEqual(self.user_payload(messages)["attempt_history"], [
            {
                "iteration": attempt["iteration"],
                "relational_schema": attempt["relational_schema"],
                "feedback": attempt["feedback"],
            }
            for attempt in attempts
        ])

    def test_verifier_feedback_leads_to_executable_create_queries(self):
        raw_extraction = f"```json\n{EXTRACTION}\n```"
        raw_schema = f"```text\n{VERIFIED_SCHEMA}\n```"
        llm = ScriptedLLM(
            LLMResponse(raw_extraction, input_tokens=13, output_tokens=6, total_tokens=19),
            FAILING_SCHEMA,
            PARTIALLY_REVISED_SCHEMA,
            LLMResponse(text=raw_schema, input_tokens=43, output_tokens=0, total_tokens=43),
        )
        events = []
        result = run_pipeline(SPECIFICATION, llm, on_event=events.append)

        self.assertTrue(result["verified"])
        self.assertEqual(result["attribute_types"], ATTRIBUTE_TYPES)
        self.assertEqual(result["functional_dependencies"], DEPENDENCIES)
        self.assertEqual(result["relational_schema"], VERIFIED_SCHEMA)
        self.assertEqual(len(llm.calls), 4)
        event_statuses = [(event["stage"], event["iteration"], event["status"]) for event in events]
        self.assertEqual(event_statuses, [
            ("extraction", 0, "extracted"), ("schema", 1, "rejected"),
            ("schema", 2, "rejected"), ("schema", 3, "verified"),
        ])
        self.assertEqual([event["prompt"] for event in events], llm.calls)
        self.assertEqual([event["model_response"] for event in events],
                         [raw_extraction, FAILING_SCHEMA, PARTIALLY_REVISED_SCHEMA, raw_schema])
        token_columns = ("input_tokens", "output_tokens", "total_tokens")
        self.assertEqual([tuple(event.get(column) for column in token_columns) for event in events],
                         [(13, 6, 19), (None, None, None), (None, None, None), (43, 0, 43)])
        self.assertEqual(self.user_payload(llm.calls[0])["database_specification"], SPECIFICATION)
        self.assertNotIn("attempt_history", self.user_payload(llm.calls[1]))
        for messages in llm.calls[1:]:
            payload = self.user_payload(messages)
            self.assertEqual(payload["database_specification"], SPECIFICATION)
            self.assertCountEqual(payload["attributes"], ATTRIBUTE_TYPES)
            self.assertEqual(payload["functional_dependencies"], DEPENDENCIES)

        first_attempt, second_attempt, successful_attempt = result["attempts"]
        for iteration, schema, attempt in (
            (1, FAILING_SCHEMA, first_attempt),
            (2, PARTIALLY_REVISED_SCHEMA, second_attempt),
        ):
            with self.subTest(iteration=iteration):
                self.assertEqual(attempt["iteration"], iteration)
                self.assertEqual(attempt["relational_schema"], schema)
                expected_verification = verify_schema(schema, DEPENDENCIES)
                self.assertEqual(attempt["verification"], expected_verification)
                self.assertEqual(attempt["feedback"], expected_verification["feedback"])
        self.assertNotEqual(first_attempt["feedback"], second_attempt["feedback"])
        self.assert_attempt_history(llm.calls[2], first_attempt)
        self.assert_attempt_history(llm.calls[3], first_attempt, second_attempt)
        self.assertEqual(successful_attempt["iteration"], 3)
        self.assertTrue(successful_attempt["verification"]["verified"])

        rejected_queries = generate_create_queries(FAILING_SCHEMA, ATTRIBUTE_TYPES)
        self.assertEqual(first_attempt["create_queries"], rejected_queries)
        self.assertEqual(events[1]["create_queries"], rejected_queries)
        queries = result["create_queries"]
        self.assertEqual(successful_attempt["create_queries"], queries)
        self.assertEqual(events[3]["create_queries"], queries)
        self.assertEqual(len(queries), 3)
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.executescript("\n".join(queries))
            columns = connection.execute('PRAGMA table_info("Record")').fetchall()
            self.assertEqual([(row[1], row[2], row[5]) for row in columns],
                             [("A", "INTEGER", 1), ("Notes", "TEXT", 2)])

    def test_candidate_attribute_coverage_is_exact_even_for_attributes_without_fds(self):
        missing = "Mapping(<u>A</u>, B)\nDescription(<u>B</u>, C)"
        extra = VERIFIED_SCHEMA.replace("<u>Notes</u>", "<u>Notes</u>, UnexpectedField")
        self.assertTrue(verify_schema(missing, DEPENDENCIES)["verified"])
        llm = ScriptedLLM(EXTRACTION, missing, extra, VERIFIED_SCHEMA)
        result = run_pipeline(SPECIFICATION, llm, max_iterations=3)

        self.assertTrue(result["verified"])
        self.assertEqual(len(llm.calls), 4)
        missing_attempt, extra_attempt, _ = result["attempts"]
        self.assertIsNone(missing_attempt["verification"])
        self.assertIsNone(extra_attempt["verification"])
        self.assertIn("Notes", missing_attempt["feedback"])
        self.assertIn("UnexpectedField", extra_attempt["feedback"])
        self.assertEqual(missing_attempt["create_queries"], generate_create_queries(
            missing, {"A": "INTEGER", "B": "INTEGER", "C": "TEXT"},
        ))
        self.assertEqual(extra_attempt["create_queries"], [])
        self.assert_attempt_history(llm.calls[2], missing_attempt)
        self.assert_attempt_history(llm.calls[3], missing_attempt, extra_attempt)

    def test_malformed_schema_and_sqlite_name_failure_can_be_revised(self):
        invalid_name = VERIFIED_SCHEMA.replace("Record(", "sqlite_Record(")
        llm = ScriptedLLM(EXTRACTION, "This is not a schema", invalid_name, VERIFIED_SCHEMA)
        result = run_pipeline(SPECIFICATION, llm)

        self.assertTrue(result["verified"])
        malformed_attempt, reserved_name_attempt, _ = result["attempts"]
        self.assertIsNone(malformed_attempt["verification"])
        self.assertEqual(malformed_attempt["create_queries"], [])
        self.assertTrue(reserved_name_attempt["verification"]["verified"])
        self.assertEqual(reserved_name_attempt["create_queries"], [])
        self.assertIn("sqlite_Record", reserved_name_attempt["feedback"])
        self.assert_attempt_history(llm.calls[2], malformed_attempt)
        self.assert_attempt_history(llm.calls[3], malformed_attempt, reserved_name_attempt)

    def test_iteration_limit_counts_first_candidate_and_preserves_its_ddl(self):
        llm = ScriptedLLM(EXTRACTION, FAILING_SCHEMA)
        events = []
        result = run_pipeline(SPECIFICATION, llm, max_iterations=1, on_event=events.append)

        self.assertFalse(result["verified"])
        self.assertEqual(len(llm.calls), 2)
        self.assertEqual(len(result["attempts"]), 1)
        attempt = result["attempts"][0]
        self.assertEqual(attempt["iteration"], 1)
        expected_queries = generate_create_queries(FAILING_SCHEMA, ATTRIBUTE_TYPES)
        self.assertEqual(attempt["create_queries"], expected_queries)
        self.assertEqual(result["create_queries"], expected_queries)
        self.assertEqual(events[-1]["status"], "exhausted")
        self.assertEqual(events[-1]["create_queries"], expected_queries)
        self.assertIn("2NF", result["feedback"])

    def test_solver_error_event_keeps_generated_ddl(self):
        llm = ScriptedLLM(EXTRACTION, VERIFIED_SCHEMA)
        events = []
        with patch("pipeline.run.verify_schema", side_effect=RuntimeError("Inconclusive solver result.")):
            with self.assertRaisesRegex(RuntimeError, "Inconclusive solver result"):
                run_pipeline(SPECIFICATION, llm, on_event=events.append)

        self.assertEqual(events[-1]["status"], "error")
        self.assertEqual(events[-1]["create_queries"], generate_create_queries(VERIFIED_SCHEMA, ATTRIBUTE_TYPES))

    def test_invalid_extraction_does_not_start_schema_generation(self):
        invalid_responses = (
            "This is not JSON",
            json.dumps({"attribute_types": ATTRIBUTE_TYPES}),
            json.dumps({"attribute_types": ATTRIBUTE_TYPES,
                        "functional_dependencies": ["[A] -> [Unknown]"]}),
            json.dumps({"attribute_types": {"A": "TEXT NOT NULL"},
                        "functional_dependencies": []}),
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                llm = ScriptedLLM(response)
                with self.assertRaises(ExtractionError):
                    run_pipeline(SPECIFICATION, llm)
                self.assertEqual(len(llm.calls), 1)

    def test_iteration_limit_must_be_positive_integer(self):
        for limit in (0, -1, 1.5, True):
            with self.subTest(limit=limit):
                llm = ScriptedLLM()
                with self.assertRaises(ValueError):
                    run_pipeline(SPECIFICATION, llm, max_iterations=limit)
                self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
