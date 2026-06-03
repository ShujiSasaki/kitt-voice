"""Order Gate 6ステップ検問のユニットテスト"""
from __future__ import annotations
import unittest

from danjer_gaia.order_gate import (
    TradeIntent, GateContext, GateConfig, GateResult,
    run_order_gate,
    step1_trade_intent, step2_risk_check, step3_exchange_check,
    step4_cost_check, step5_similar_pattern, step6_explainability,
)


def good_intent(**overrides):
    defaults = dict(
        side="long",
        size=0.001,
        leverage=2.0,
        entry_price=60000.0,
        sl_price=58000.0,
        tp_price=63000.0,
        symbol="BTCUSDT",
    )
    defaults.update(overrides)
    return TradeIntent(**defaults)


def good_ctx(**overrides):
    defaults = dict(
        current_equity=10000.0,
        daily_pnl_pct=0.0,
        total_dd_pct=0.0,
        api_latency_ms=100.0,
        bid_depth_top5=50.0,
        bid_depth_baseline=50.0,
        ask_depth_top5=50.0,
        ask_depth_baseline=50.0,
        last_price=60000.0,
        mark_price=60000.0,
        expected_value=100.0,
        fee_estimate=5.0,
        slippage_estimate=3.0,
        current_atr=600.0,  # 1% ATR
        similar_pattern_pf=1.2,
        similar_pattern_count=10,
        explanation="BTC上昇トレンド+danjer類似局面 (2024-03類似)+確信度0.7+危険度0.2",
    )
    defaults.update(overrides)
    return GateContext(**defaults)


class TestStep1(unittest.TestCase):
    def test_valid_long(self):
        self.assertIsNone(step1_trade_intent(good_intent(), GateConfig()))

    def test_negative_size(self):
        self.assertIsNotNone(step1_trade_intent(good_intent(size=-1), GateConfig()))

    def test_excessive_leverage(self):
        cfg = GateConfig(max_leverage=5.0)
        self.assertIsNotNone(step1_trade_intent(good_intent(leverage=10.0), cfg))

    def test_long_sl_above_entry(self):
        """long で SL >= entry はエラー"""
        i = good_intent(entry_price=60000, sl_price=61000)
        self.assertIsNotNone(step1_trade_intent(i, GateConfig()))

    def test_long_tp_below_entry(self):
        i = good_intent(entry_price=60000, sl_price=58000, tp_price=59000)
        self.assertIsNotNone(step1_trade_intent(i, GateConfig()))

    def test_short_valid(self):
        i = good_intent(side="short", entry_price=60000,
                        sl_price=62000, tp_price=57000)
        self.assertIsNone(step1_trade_intent(i, GateConfig()))

    def test_short_sl_below_entry(self):
        i = good_intent(side="short", entry_price=60000,
                        sl_price=58000, tp_price=57000)
        self.assertIsNotNone(step1_trade_intent(i, GateConfig()))


class TestStep2(unittest.TestCase):
    def test_normal(self):
        self.assertIsNone(step2_risk_check(good_intent(), good_ctx(), GateConfig()))

    def test_position_too_small(self):
        """size=0.0001 で notional=6 USD、 equity=10000 → 0.06% < 0.1%"""
        i = good_intent(size=0.0001)
        self.assertIsNotNone(step2_risk_check(i, good_ctx(), GateConfig()))

    def test_position_too_large(self):
        """size=0.5 で notional=30000 USD、 equity=10000 → 300% > 10%"""
        i = good_intent(size=0.5)
        self.assertIsNotNone(step2_risk_check(i, good_ctx(), GateConfig()))

    def test_daily_dd_limit(self):
        ctx = good_ctx(daily_pnl_pct=-0.06)  # -6% > -5%
        self.assertIsNotNone(step2_risk_check(good_intent(), ctx, GateConfig()))

    def test_total_dd_limit(self):
        ctx = good_ctx(total_dd_pct=0.20)
        self.assertIsNotNone(step2_risk_check(good_intent(), ctx, GateConfig()))


class TestStep3(unittest.TestCase):
    def test_normal(self):
        self.assertIsNone(step3_exchange_check(good_ctx(), GateConfig()))

    def test_high_latency(self):
        ctx = good_ctx(api_latency_ms=1000.0)
        self.assertIsNotNone(step3_exchange_check(ctx, GateConfig()))

    def test_low_liquidity(self):
        ctx = good_ctx(bid_depth_top5=10.0, bid_depth_baseline=100.0)  # 10%
        self.assertIsNotNone(step3_exchange_check(ctx, GateConfig()))

    def test_price_deviation(self):
        ctx = good_ctx(last_price=60000, mark_price=60500)  # 0.83% > 0.5%
        self.assertIsNotNone(step3_exchange_check(ctx, GateConfig()))


class TestStep4(unittest.TestCase):
    def test_normal(self):
        self.assertIsNone(step4_cost_check(good_intent(), good_ctx(), GateConfig()))

    def test_cost_too_high(self):
        """cost=50, EV=100 → 50% > 30%"""
        ctx = good_ctx(expected_value=100, fee_estimate=30, slippage_estimate=20)
        self.assertIsNotNone(step4_cost_check(good_intent(), ctx, GateConfig()))

    def test_negative_ev(self):
        ctx = good_ctx(expected_value=-10.0)
        self.assertIsNotNone(step4_cost_check(good_intent(), ctx, GateConfig()))

    def test_sl_too_tight(self):
        """SL距離 200 / ATR 600 = 0.33 < 0.5"""
        i = good_intent(entry_price=60000, sl_price=59800)
        ctx = good_ctx(current_atr=600.0)
        self.assertIsNotNone(step4_cost_check(i, ctx, GateConfig()))

    def test_sl_too_far(self):
        """SL距離 6000 / ATR 600 = 10 > 5"""
        i = good_intent(entry_price=60000, sl_price=54000)
        ctx = good_ctx(current_atr=600.0)
        self.assertIsNotNone(step4_cost_check(i, ctx, GateConfig()))


class TestStep5(unittest.TestCase):
    def test_disabled_passes(self):
        cfg = GateConfig(require_similar_pattern=False)
        ctx = good_ctx(similar_pattern_pf=None, similar_pattern_count=0)
        self.assertIsNone(step5_similar_pattern(ctx, cfg))

    def test_enabled_no_data_fails(self):
        cfg = GateConfig(require_similar_pattern=True)
        ctx = good_ctx(similar_pattern_pf=None)
        self.assertIsNotNone(step5_similar_pattern(ctx, cfg))

    def test_enabled_low_pf_fails(self):
        cfg = GateConfig(require_similar_pattern=True, min_historical_pf=1.0)
        ctx = good_ctx(similar_pattern_pf=0.7, similar_pattern_count=10)
        self.assertIsNotNone(step5_similar_pattern(ctx, cfg))

    def test_enabled_too_few_patterns(self):
        cfg = GateConfig(require_similar_pattern=True)
        ctx = good_ctx(similar_pattern_count=1)
        self.assertIsNotNone(step5_similar_pattern(ctx, cfg))


class TestStep6(unittest.TestCase):
    def test_valid_explanation(self):
        self.assertIsNone(step6_explainability(good_ctx()))

    def test_empty_explanation(self):
        ctx = good_ctx(explanation="")
        self.assertIsNotNone(step6_explainability(ctx))

    def test_too_short_explanation(self):
        ctx = good_ctx(explanation="少ない")
        self.assertIsNotNone(step6_explainability(ctx))


class TestRunOrderGate(unittest.TestCase):
    def test_all_pass(self):
        decision = run_order_gate(good_intent(), good_ctx())
        self.assertEqual(decision.result, GateResult.APPROVE)
        self.assertIsNone(decision.failed_step)
        self.assertTrue(decision.decision_trace_id)  # uuid付与済

    def test_step1_fails_first(self):
        """step1 失敗時は step2 以降は走らない"""
        i = good_intent(size=-1)  # step1で死ぬ
        decision = run_order_gate(i, good_ctx())
        self.assertEqual(decision.result, GateResult.REJECT)
        self.assertEqual(decision.failed_step, "step1_trade_intent")

    def test_step2_fails(self):
        ctx = good_ctx(daily_pnl_pct=-0.10)
        decision = run_order_gate(good_intent(), ctx)
        self.assertEqual(decision.result, GateResult.REJECT)
        self.assertEqual(decision.failed_step, "step2_risk_check")

    def test_step6_fails(self):
        ctx = good_ctx(explanation="")
        decision = run_order_gate(good_intent(), ctx)
        self.assertEqual(decision.result, GateResult.REJECT)
        self.assertEqual(decision.failed_step, "step6_explainability")

    def test_decision_trace_id_consistent(self):
        intent = good_intent()
        original_id = intent.decision_trace_id
        decision = run_order_gate(intent, good_ctx())
        self.assertEqual(decision.decision_trace_id, original_id)


if __name__ == "__main__":
    unittest.main()
