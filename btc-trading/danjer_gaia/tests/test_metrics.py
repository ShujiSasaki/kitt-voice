"""
Trade-EHR / noop ペナルティのユニットテスト
3者会議 Phase 1 合意 (Appendix-A) の数式が正しく実装されているか検証
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta
import unittest

from danjer_gaia.schemas import Trade, TradingPeriod, GuardConfig, NoopConfig
from danjer_gaia.metrics import (
    trade_ehr, moving_average_ehr, noop_penalty, period_summary,
)


def make_trade(net_profit=100.0, avg_equity=10000.0, elapsed_hours=2.0,
               liquidated=False, max_dd=0.0, had_sl=True, slippage=2.0,
               leverage=2.0):
    """テスト用 Trade ファクトリ"""
    now = datetime(2026, 6, 3, 12, 0)
    return Trade(
        trade_id="t1",
        symbol="BTCUSDT",
        side="long",
        entered_at=now,
        exited_at=now + timedelta(hours=1),
        elapsed_hours=elapsed_hours,
        entry_price=50000.0,
        exit_price=50500.0,
        size=0.01,
        leverage=leverage,
        gross_profit=net_profit + 5.0,
        fees=3.0,
        slippage=slippage,
        net_profit=net_profit,
        avg_equity=avg_equity,
        had_sl=had_sl,
        was_liquidated=liquidated,
        max_dd_during=max_dd,
    )


class TestTradeEHR(unittest.TestCase):

    def test_normal(self):
        """通常のEHR計算"""
        t = make_trade(net_profit=100.0, avg_equity=10000.0, elapsed_hours=2.0)
        # EHR = 100 / (10000 * 2) = 0.005
        self.assertAlmostEqual(trade_ehr(t), 0.005, places=6)

    def test_zero_elapsed_hours_guarded(self):
        """ElapsedHours=0 でもクラッシュしない (分母ガード)"""
        t = make_trade(net_profit=50.0, avg_equity=10000.0, elapsed_hours=0.0)
        # 分母: max(10000, 100) * max(0, 1) = 10000 * 1 = 10000
        # EHR = 50 / 10000 = 0.005
        result = trade_ehr(t)
        self.assertTrue(math.isfinite(result))
        self.assertAlmostEqual(result, 0.005, places=6)

    def test_zero_equity_guarded(self):
        """AvgEquity=0 でもクラッシュしない"""
        t = make_trade(net_profit=10.0, avg_equity=0.0, elapsed_hours=1.0)
        # 分母: max(0, 100) * max(1, 1) = 100 * 1 = 100
        result = trade_ehr(t)
        self.assertTrue(math.isfinite(result))
        self.assertAlmostEqual(result, 0.1, places=6)

    def test_negative_profit(self):
        """損失時もEHRは負の値で計算可能"""
        t = make_trade(net_profit=-200.0, avg_equity=10000.0, elapsed_hours=4.0)
        # EHR = -200 / (10000 * 4) = -0.005
        self.assertAlmostEqual(trade_ehr(t), -0.005, places=6)

    def test_nan_raises(self):
        """NetProfit が NaN の場合 ValueError"""
        t = make_trade(net_profit=float("nan"), avg_equity=10000.0, elapsed_hours=2.0)
        with self.assertRaises(ValueError):
            trade_ehr(t)

    def test_inf_raises(self):
        """NetProfit が Inf の場合 ValueError"""
        t = make_trade(net_profit=float("inf"), avg_equity=10000.0, elapsed_hours=2.0)
        with self.assertRaises(ValueError):
            trade_ehr(t)


class TestMovingAverageEHR(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(moving_average_ehr([]), 0.0)

    def test_single_trade(self):
        t = make_trade(net_profit=100.0, avg_equity=10000.0, elapsed_hours=2.0)
        self.assertAlmostEqual(moving_average_ehr([t]), 0.005)

    def test_window_smaller_than_count(self):
        """30トレード以上ある場合、 直近30だけが平均対象"""
        # 古いトレード: EHR=0.01
        old = [make_trade(net_profit=100.0, avg_equity=5000.0, elapsed_hours=2.0)
               for _ in range(50)]
        # 新しいトレード: EHR=0.005
        new = [make_trade(net_profit=100.0, avg_equity=10000.0, elapsed_hours=2.0)
               for _ in range(30)]
        trades = old + new
        # 直近30は new (0.005)
        self.assertAlmostEqual(moving_average_ehr(trades, window=30), 0.005)

    def test_mixed(self):
        """損益混在の平均"""
        trades = [
            make_trade(net_profit=200.0, avg_equity=10000.0, elapsed_hours=2.0),  # 0.01
            make_trade(net_profit=-100.0, avg_equity=10000.0, elapsed_hours=2.0),  # -0.005
        ]
        self.assertAlmostEqual(moving_average_ehr(trades), 0.0025)


class TestNoopPenalty(unittest.TestCase):
    """R28対策: 強制エントリーbug防止条件"""

    def _good_ctx(self, **overrides):
        ctx = dict(
            noop_hours=10.0,
            current_vol_atr=100.0,
            mean_atr_baseline=80.0,
            confidence=0.9,
            risk_level=0.2,
            expected_value=50.0,
            subsequent_favorable_move=200.0,
        )
        ctx.update(overrides)
        return ctx

    def test_all_conditions_met(self):
        """4条件全部満たす場合、 ペナルティ発動"""
        result = noop_penalty(**self._good_ctx())
        self.assertLess(result, 0.0)

    def test_low_confidence_no_penalty(self):
        """信頼度低 → ペナルティ 0"""
        result = noop_penalty(**self._good_ctx(confidence=0.5))
        self.assertEqual(result, 0.0)

    def test_high_risk_no_penalty(self):
        """リスク高 → ペナルティ 0"""
        result = noop_penalty(**self._good_ctx(risk_level=0.6))
        self.assertEqual(result, 0.0)

    def test_negative_ev_no_penalty(self):
        """期待値負 → ペナルティ 0"""
        result = noop_penalty(**self._good_ctx(expected_value=-10.0))
        self.assertEqual(result, 0.0)

    def test_no_subsequent_move_no_penalty(self):
        """順行発生なし → ペナルティ 0"""
        result = noop_penalty(**self._good_ctx(subsequent_favorable_move=0.0))
        self.assertEqual(result, 0.0)

    def test_penalty_caps_at_max(self):
        """ボラ倍率が大きすぎても 3.0倍 で上限固定 (NoopConfig.vol_multiplier_cap)"""
        result = noop_penalty(**self._good_ctx(current_vol_atr=10000.0, noop_hours=1.0))
        # vol_multiplier は cap で 3.0、 base 0.001 × 3.0 = 0.003 per hour
        # 1h × 0.003 = -0.003
        self.assertAlmostEqual(result, -0.003, places=5)

    def test_penalty_caps_at_absolute_max(self):
        """base_penalty が大きい場合、 絶対上限 max_penalty_per_hour=0.01 で固定"""
        # base を 0.01 にすると、 通常ボラでも 0.01 になり、 上限に達する
        from danjer_gaia.schemas import NoopConfig
        cfg = NoopConfig(base_penalty_per_hour=0.01, max_penalty_per_hour=0.01)
        ctx = self._good_ctx(current_vol_atr=1000.0, noop_hours=2.0)
        result = noop_penalty(**ctx, cfg=cfg)
        # vol_multiplier capped at 3.0、 0.01 * 3.0 = 0.03 → 絶対上限 0.01 で止まる
        # 2h × 0.01 = -0.02
        self.assertAlmostEqual(result, -0.02, places=5)


class TestPeriodSummary(unittest.TestCase):

    def test_empty_period(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
        )
        summary = period_summary(period)
        self.assertEqual(summary["total_trades"], 0)
        self.assertEqual(summary["total_net_profit"], 0.0)
        self.assertEqual(summary["num_liquidations"], 0)

    def test_with_trades(self):
        trades = [
            make_trade(net_profit=100.0, avg_equity=10000.0, elapsed_hours=2.0),
            make_trade(net_profit=-50.0, avg_equity=10000.0, elapsed_hours=1.0,
                       liquidated=True),
        ]
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=trades,
            noop_hours_total=24.0,
        )
        summary = period_summary(period)
        self.assertEqual(summary["total_trades"], 2)
        self.assertAlmostEqual(summary["total_net_profit"], 50.0)
        self.assertEqual(summary["num_liquidations"], 1)
        self.assertAlmostEqual(summary["total_noop_hours"], 24.0)


if __name__ == "__main__":
    unittest.main()
