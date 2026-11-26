import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import similarity
from pipeline.llm import LLMError, LLMResponse
from similarity_cache import SimilarityCache


def decision_response(*matches):
    return LLMResponse(text=json.dumps({
        "decisions": [
            {"id": pair_id, "match": match} for pair_id, match in enumerate(matches, start=1)
        ],
    }))


class SimilarityCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache_path = Path(self.enterContext(TemporaryDirectory())) / "similarity.sqlite3"
        self.client = self.enterContext(patch.object(similarity, "LLMClient")).return_value.complete

    def judge(self, model="openai/test-model", batch_size=64):
        return similarity.SimilarityJudge(
            model, "test-api-key", batch_size=batch_size, cache_path=self.cache_path,
        )

    def sent_batches(self):
        return [json.loads(request.args[0][1]["content"]) for request in self.client.call_args_list]

    def test_reuses_positive_and_negative_pairs_across_judges(self):
        positive = ("Film", "Movie")
        negative = ("Ticket", "Genre")
        self.client.return_value = decision_response(1, 0, 1)
        self.assertEqual(self.judge()("table", [positive, negative, ("Cinema", "Theater")]), [1, 0, 1])
        self.client.reset_mock()

        judge = self.judge("test-model")
        self.assertEqual(judge.decisions(), [])
        self.assertEqual(judge("table", [negative, positive, negative]), [0, 1, 0])
        self.client.assert_not_called()
        self.assertCountEqual(judge.decisions(), [
            {"kind": "table", "generated": "Film", "target": "Movie", "match": 1},
            {"kind": "table", "generated": "Ticket", "target": "Genre", "match": 0},
        ])

    def test_batches_only_unique_uncached_pairs_and_preserves_result_order(self):
        cached = ("Ticket", "Genre")
        first = ("Film", "Movie")
        second = ("Actor", "Performer")
        third = ("Theater", "Cinema")
        self.client.return_value = decision_response(0)
        self.assertEqual(self.judge()("table", [cached]), [0])
        self.client.reset_mock()
        reordered = LLMResponse(text='{"decisions":[{"id":2,"match":0},{"id":1,"match":1}]}')
        self.client.side_effect = [reordered, decision_response(1)]

        judge = self.judge(batch_size=2)
        self.assertEqual(judge("table", [first, cached, first, second, third]), [1, 0, 1, 0, 1])
        self.assertEqual(self.sent_batches(), [
            {"identifier_kind": "table", "pairs": [
                {"id": 1, "generated": "Film", "target": "Movie"},
                {"id": 2, "generated": "Actor", "target": "Performer"},
            ]},
            {"identifier_kind": "table", "pairs": [{"id": 1, "generated": "Theater", "target": "Cinema"}]},
        ])

    def test_keeps_model_kind_and_pair_direction_separate(self):
        pair = ("Film", "Movie")
        reverse = ("Movie", "Film")
        self.client.side_effect = [decision_response(match) for match in (1, 0, 0, 0)]
        self.assertEqual(self.judge()("table", [pair]), [1])
        self.assertEqual(self.judge("openai/other-model")("table", [pair]), [0])
        self.assertEqual(self.judge()("column", [pair]), [0])
        self.assertEqual(self.judge()("table", [reverse]), [0])
        self.assertEqual(self.client.call_count, 4)

        self.client.reset_mock()
        self.assertEqual(self.judge()("table", [pair, reverse]), [1, 0])
        self.assertEqual(self.judge("openai/other-model")("table", [pair]), [0])
        self.assertEqual(self.judge()("column", [pair]), [0])
        self.client.assert_not_called()

    def test_keeps_earlier_batch_when_later_request_fails(self):
        pairs = [("Film", "Movie"), ("Ticket", "Genre")]
        self.client.side_effect = [decision_response(1), LLMError("Provider unavailable")]
        with self.assertRaisesRegex(LLMError, "Provider unavailable"):
            self.judge(batch_size=1)("table", pairs)

        self.client.reset_mock()
        self.client.side_effect = [decision_response(0)]
        self.assertEqual(self.judge()("table", pairs), [1, 0])
        self.assertEqual(self.sent_batches(), [
            {"identifier_kind": "table", "pairs": [{"id": 1, "generated": "Ticket", "target": "Genre"}]},
        ])

    def test_invalid_singleton_results_are_not_cached(self):
        malformed_responses = (
            "",
            "[1]",
            '{"decisions":[]}',
            '{"decisions":[{"id":2,"match":1}]}',
            '{"decisions":[{"id":true,"match":1}]}',
            '{"decisions":[{"id":1,"match":false}]}',
        )
        for index, text in enumerate(malformed_responses):
            with self.subTest(text=text):
                pair = (f"Film_{index}", "Movie")
                self.client.reset_mock()
                self.client.side_effect = [LLMResponse(text=text), decision_response(1)]
                with self.assertRaises(LLMError):
                    self.judge()("table", [pair])
                self.assertEqual(self.judge()("table", [pair]), [1])
                self.assertEqual(self.client.call_count, 2)
                first_request, second_request = self.sent_batches()
                self.assertEqual(first_request, second_request)

    def test_invalid_batch_splits_into_smaller_requests_and_keeps_successful_results(self):
        pairs = [("Film", "Movie"), ("Ticket", "Genre")]
        duplicate_ids = LLMResponse(text='{"decisions":[{"id":1,"match":1},{"id":1,"match":0}]}')
        self.client.side_effect = [duplicate_ids, decision_response(1), LLMResponse(text="")]
        with self.assertLogs("similarity", "WARNING"), self.assertRaises(LLMError):
            self.judge()("table", pairs)
        self.assertEqual([batch["pairs"] for batch in self.sent_batches()], [
            [
                {"id": 1, "generated": "Film", "target": "Movie"},
                {"id": 2, "generated": "Ticket", "target": "Genre"},
            ],
            [{"id": 1, "generated": "Film", "target": "Movie"}],
            [{"id": 1, "generated": "Ticket", "target": "Genre"}],
        ])

        self.client.reset_mock()
        self.client.side_effect = [decision_response(0)]
        self.assertEqual(self.judge()("table", pairs), [1, 0])
        self.assertEqual(self.sent_batches(), [
            {"identifier_kind": "table", "pairs": [{"id": 1, "generated": "Ticket", "target": "Genre"}]},
        ])

    def test_blank_batch_recovers_when_both_smaller_requests_are_valid(self):
        pairs = [("Film", "Movie"), ("Ticket", "Genre")]
        self.client.side_effect = [LLMResponse(text=""), decision_response(1), decision_response(0)]
        with self.assertLogs("similarity", "WARNING"):
            self.assertEqual(self.judge()("table", pairs), [1, 0])
        self.assertEqual([len(batch["pairs"]) for batch in self.sent_batches()], [2, 1, 1])

    def test_request_failure_does_not_split_batch(self):
        pairs = [("Film", "Movie"), ("Ticket", "Genre")]
        self.client.side_effect = LLMError("Provider unavailable")
        with self.assertRaisesRegex(LLMError, "Provider unavailable"):
            self.judge()("table", pairs)
        self.client.assert_called_once()

    def test_reuses_legacy_decision_for_only_its_original_scope(self):
        pair = ("Film", "Movie")
        legacy = SimilarityCache(
            self.cache_path, "openai/test-model",
            "e02770882b01e834a18190bd2f1a9e6e0eaea6a143d5b76f40ce71181cb1f302",
        )
        legacy.store({("table", *pair): 0})
        self.assertEqual(self.judge()("table", [pair]), [0])
        self.client.assert_not_called()

        self.client.return_value = decision_response(1)
        self.assertEqual(self.judge("openai/other-model")("table", [pair]), [1])
        self.assertEqual(self.judge()("column", [pair]), [1])
        new_pair = ("Cinema", "Theater")
        self.assertEqual(self.judge()("table", [new_pair]), [1])
        new_key = ("table", *new_pair)
        self.assertEqual(legacy.lookup([new_key]), {new_key: 1})
        self.assertEqual(self.client.call_count, 3)

    def test_prompt_shows_id_based_examples_for_tables_and_columns(self):
        self.client.return_value = decision_response(1)
        self.assertEqual(self.judge()("table", [("Film", "Movie")]), [1])
        system_prompt = self.client.call_args.args[0][0]["content"]
        kinds = re.findall(r'"identifier_kind"\s*:\s*"([^"]+)"', system_prompt)
        self.assertCountEqual(kinds, ["table", "column"])
        examples = re.findall(r'\{\s*"decisions"\s*:\s*\[[^\]]+\]\s*\}', system_prompt)
        self.assertEqual(len(examples), 2)
        for example in examples:
            decisions = json.loads(example)["decisions"]
            self.assertCountEqual([decision["id"] for decision in decisions], [1, 2])
            self.assertCountEqual([decision["match"] for decision in decisions], [0, 1])
