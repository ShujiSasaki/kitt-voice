"""強制ストップ7条件 単体テスト

各ルール (rule_1〜rule_7) が想定通りに発火する/しないことを保証。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))

from stop_rules import (
    rule_1_no_stop_loss, rule_2_sl_too_close, rule_3_unfounded_rally,
    rule_4_insufficient_grounds, rule_5_thin_counter, rule_6_thin_or_extreme,
    rule_7_model_ambiguous, force_stop_check,
)


# テスト用ダミー candles (20本、 大体一定価格)
DUMMY_CANDLES = [
    {'open': 60000, 'high': 60500, 'low': 59500, 'close': 60000, 'volume': 100}
    for _ in range(20)
]


class TestRule1NoStopLoss(unittest.TestCase):
    def test_response_with_stop_loss(self):
        self.assertFalse(rule_1_no_stop_loss('損切りは戻り高値で。【スタンス】ショート'))

    def test_response_without_stop_loss(self):
        self.assertTrue(rule_1_no_stop_loss('上昇継続。【スタンス】ロング'))

    def test_response_with_se(self):
        self.assertFalse(rule_1_no_stop_loss('背を割れたら撤退。【スタンス】見送り'))


class TestRule3UnfoundedRally(unittest.TestCase):
    def test_rally_with_oi_mention(self):
        response = 'OI急増を伴った急騰なので継続性あり。【スタンス】ロング'
        self.assertFalse(rule_3_unfounded_rally('rally', response, DUMMY_CANDLES))

    def test_rally_without_oi_mention(self):
        response = '急騰しているのでロング。【スタンス】ロング'
        self.assertTrue(rule_3_unfounded_rally('rally', response, DUMMY_CANDLES))

    def test_non_rally_regime(self):
        response = '急騰中。【スタンス】ロング'
        self.assertFalse(rule_3_unfounded_rally('trend', response, DUMMY_CANDLES))


class TestRule4InsufficientGrounds(unittest.TestCase):
    def test_short_response(self):
        self.assertTrue(rule_4_insufficient_grounds(['材料1', '材料2'], '短い'))

    def test_long_response_2_materials(self):
        self.assertFalse(rule_4_insufficient_grounds(
            ['材料1', '材料2'],
            'これは十分長い回答であり、根拠となる材料も2点提示されている。【スタンス】ロング'
        ))

    def test_insufficient_materials(self):
        self.assertTrue(rule_4_insufficient_grounds(['材料1'], 'これは十分長い回答だが材料は1点だけ。'))


class TestRule5ThinCounter(unittest.TestCase):
    def test_crash_with_long(self):
        self.assertTrue(rule_5_thin_counter('crash', 'crash中だが買い向かう。【スタンス】ロング'))

    def test_crash_with_long_but_safe_msg(self):
        self.assertFalse(rule_5_thin_counter(
            'crash', 'crashで底打ち確認後に買う。【スタンス】見送り'
        ))

    def test_trend_neutral(self):
        self.assertFalse(rule_5_thin_counter('trend', '上昇継続。【スタンス】ロング'))


class TestRule7ModelAmbiguous(unittest.TestCase):
    def test_short_response(self):
        self.assertTrue(rule_7_model_ambiguous('短い'))

    def test_response_with_ambiguous_word(self):
        self.assertTrue(rule_7_model_ambiguous('判断が難しい、 不明な状況。 様子見が無難。'))

    def test_clear_response(self):
        self.assertFalse(rule_7_model_ambiguous(
            'OI急増と背の明確性から、 ショートを狙う構え。【スタンス】ショート'
        ))


class TestForceStopCheck(unittest.TestCase):
    def test_no_triggers_with_clear_response(self):
        result = force_stop_check(
            'trend',
            'OI急増と背の明確性から、 ショート狙い。 損切りは戻り高値で。【スタンス】ショート',
            ['上昇継続', 'OI急増', '背明確'],
            DUMMY_CANDLES,
        )
        # 完全 trigger 0 を期待
        self.assertFalse(result['triggered'], f"想定外: {result}")

    def test_triggers_with_dangerous_response(self):
        result = force_stop_check(
            'trend',
            'ロング',  # 短すぎ、 損切り無し、 根拠無し
            ['材料1'],
            DUMMY_CANDLES,
        )
        self.assertTrue(result['triggered'])
        self.assertGreater(len(result['rules_hit']), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
