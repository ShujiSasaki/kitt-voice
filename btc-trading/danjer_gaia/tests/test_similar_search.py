"""類似検索のロジック部分テスト (API呼び出しは mock)"""
from __future__ import annotations
import unittest
import json
from danjer_gaia.similar_search import SimilarSearcher, SimilarMatch


class TestAggregateOutcomes(unittest.TestCase):
    def setUp(self):
        self.searcher = SimilarSearcher()

    def test_empty(self):
        result = self.searcher.aggregate_outcomes([])
        self.assertEqual(result['count'], 0)
        self.assertIsNone(result['pf_estimate'])

    def test_all_positive(self):
        matches = [
            SimilarMatch("t1", "2024-01-01", 0.9, "txt", "r", 0.01, 0.02, 0.03, 0.05),
            SimilarMatch("t2", "2024-01-02", 0.85, "txt", "r", 0.005, 0.01, 0.02, 0.03),
            SimilarMatch("t3", "2024-01-03", 0.8, "txt", "r", 0.015, 0.03, 0.04, 0.08),
        ]
        result = self.searcher.aggregate_outcomes(matches)
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['win_rate_1d'], 1.0)
        self.assertEqual(result['pf_estimate'], float('inf'))

    def test_mixed(self):
        matches = [
            SimilarMatch("t1", "2024-01-01", 0.9, "txt", "r", 0.01, 0.02, 0.05, 0.10),
            SimilarMatch("t2", "2024-01-02", 0.85, "txt", "r", -0.005, -0.01, -0.02, -0.05),
            SimilarMatch("t3", "2024-01-03", 0.8, "txt", "r", 0.015, 0.03, 0.04, 0.08),
        ]
        result = self.searcher.aggregate_outcomes(matches)
        self.assertEqual(result['count'], 3)
        self.assertAlmostEqual(result['win_rate_1d'], 2/3, places=3)
        # gains=0.05+0.04=0.09, losses=0.02 → PF=4.5
        self.assertAlmostEqual(result['pf_estimate'], 4.5, places=1)

    def test_none_returns_skipped(self):
        matches = [
            SimilarMatch("t1", "2024-01-01", 0.9, "txt", "r", 0.01, None, None, None),
        ]
        result = self.searcher.aggregate_outcomes(matches)
        self.assertEqual(result['count'], 1)
        self.assertIsNone(result['pf_estimate'])


class TestIsTradingDecision(unittest.TestCase):
    """data_pipeline.is_trading_decision のロジックテスト"""

    def test_json_true(self):
        from danjer_gaia.embed_posts import is_trading_decision
        record = {
            "readings": {
                "anthropic_new": {
                    "content": json.dumps({"is_trading_decision": True})
                }
            }
        }
        self.assertTrue(is_trading_decision(record))

    def test_json_false(self):
        from danjer_gaia.embed_posts import is_trading_decision
        record = {
            "readings": {
                "anthropic_new": {
                    "content": json.dumps({"is_trading_decision": False})
                }
            }
        }
        self.assertFalse(is_trading_decision(record))

    def test_keyword_fallback(self):
        """JSON でない場合は キーワード判定"""
        from danjer_gaia.embed_posts import is_trading_decision
        record = {
            "readings": {
                "gpt": {
                    "content": "danjer はロング示唆。 ターゲット 70k。 SL 60k。"
                }
            }
        }
        self.assertTrue(is_trading_decision(record))

    def test_no_reading_returns_false(self):
        from danjer_gaia.embed_posts import is_trading_decision
        record = {"readings": {}}
        self.assertFalse(is_trading_decision(record))


if __name__ == "__main__":
    unittest.main()
