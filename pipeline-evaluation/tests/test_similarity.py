import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import similarity
from pipeline.llm import LLMError


class SimilarityCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache_path = Path(self.enterContext(TemporaryDirectory())) / "similarity.sqlite3"
        self.client = self.enterContext(patch.object(similarity, "LLMClient")).return_value

    def judge(self, model="openai/test-model", batch_size=64):
        return similarity.SimilarityJudge(
            model, "test-api-key", batch_size=batch_size, cache_path=self.cache_path,
        )

    def sent_batches(self):
        return [json.loads(request.args[0][1]["content"]) for request in self.client.call_args_list]

    def test_reuses_positive_and_negative_pairs_across_judges(self):
        positive = ("Film", "Movie")
        negative = ("Ticket", "Genre")
        self.client.return_value = "[1, 0, 1]"
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
        self.client.return_value = "[0]"
        self.assertEqual(self.judge()("table", [cached]), [0])
        self.client.reset_mock()
        self.client.side_effect = ["[1, 0]", "[1]"]

        judge = self.judge(batch_size=2)
        self.assertEqual(judge("table", [first, cached, first, second, third]), [1, 0, 1, 0, 1])
        self.assertEqual(self.sent_batches(), [
            {"identifier_kind": "table", "pairs": [
                {"generated": "Film", "target": "Movie"},
                {"generated": "Actor", "target": "Performer"},
            ]},
            {"identifier_kind": "table", "pairs": [{"generated": "Theater", "target": "Cinema"}]},
        ])

    def test_keeps_model_kind_and_pair_direction_separate(self):
        pair = ("Film", "Movie")
        reverse = ("Movie", "Film")
        self.client.side_effect = ["[1]", "[0]", "[0]", "[0]"]
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
        self.client.side_effect = ["[1]", LLMError("Provider unavailable")]
        with self.assertRaisesRegex(LLMError, "Provider unavailable"):
            self.judge(batch_size=1)("table", pairs)

        self.client.reset_mock()
        self.client.side_effect = ["[0]"]
        self.assertEqual(self.judge()("table", pairs), [1, 0])
        self.assertEqual(self.sent_batches(), [
            {"identifier_kind": "table", "pairs": [{"generated": "Ticket", "target": "Genre"}]},
        ])

    def test_invalid_model_result_is_not_cached(self):
        pairs = [("Film", "Movie"), ("Ticket", "Genre")]
        self.client.side_effect = ["[1, false]", "[1, 0]"]
        with self.assertRaisesRegex(LLMError, "Expected a JSON array"):
            self.judge()("table", pairs)
        self.assertEqual(self.judge()("table", pairs), [1, 0])
        self.assertEqual(self.client.call_count, 2)
        self.assertEqual(self.sent_batches()[0], self.sent_batches()[1])
