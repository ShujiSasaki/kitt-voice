"""報酬関数 episode_reward の統合テスト"""
from __future__ import annotations
from datetime import datetime, timedelta
import unittest

from danjer_gaia.schemas import Trade, TradingPeriod
from danjer_gaia.rewards import episode_reward


def make_trade(**overrides):
    now = datetime(2026, 6, 3, 12, 0)
    defaults = dict(
        trade_id="t1", symbol="BTCUSDT", side="long",
        entered_at=now, exited_at=now + timedelta(hours=1),
        elapsed_hours=2.0, entry_price=50000.0, exit_price=50500.0,
        size=0.01, leverage=2.0, gross_profit=105.0, fees=3.0,
        slippage=2.0, net_profit=100.0, avg_equity=10000.0,
        had_sl=True, was_liquidated=False, max_dd_during=0.0,
    )
    defaults.update(overrides)
    return Trade(**defaults)


class TestEpisodeReward(unittest.TestCase):

    def test_empty_period(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
        )
        result = episode_reward(period)
        self.assertEqual(result["ma30_ehr"], 0.0)
        self.assertEqual(result["noop_pen"], 0.0)
        self.assertEqual(result["guard_pen"], 0.0)
        self.assertEqual(result["total_reward"], 0.0)

    def test_normal_period(self):
        """通常取引、 ガード違反なし"""
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[make_trade(net_profit=100.0) for _ in range(10)],
        )
        result = episode_reward(period)
        # EHR=0.005 per trade、 ガード=0
        self.assertAlmostEqual(result["ma30_ehr"], 0.005)
        self.assertEqual(result["guard_pen"], 0.0)
        self.assertAlmostEqual(result["total_reward"], 0.005)

    def test_with_guard_violation(self):
        """強制ロスカット発生 → 大きなマイナス"""
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[
                make_trade(net_profit=100.0),
                make_trade(net_profit=-500.0, was_liquidated=True),
            ],
        )
        result = episode_reward(period)
        # 1件ロスカット = -100 ペナルティが効いて total_reward が大きく負
        self.assertLess(result["total_reward"], -90.0)

    def test_with_noop_penalty(self):
        """noop ペナルティ発動条件満たす場合"""
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[make_trade(net_profit=100.0) for _ in range(5)],
            noop_hours_total=20.0,
        )
        ctx = dict(
            current_vol_atr=100.0,
            mean_atr_baseline=80.0,
            confidence=0.9,
            risk_level=0.2,
            expected_value=50.0,
            subsequent_favorable_move=200.0,
        )
        result = episode_reward(period, noop_context=ctx)
        self.assertLess(result["noop_pen"], 0.0)

    def test_breakdown_keys(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[make_trade()],
        )
        result = episode_reward(period)
        expected_keys = {"liquidation", "max_dd", "no_stop", "slippage",
                         "overleverage", "overtrade", "total",
                         "ma30_ehr_contribution", "noop_contribution"}
        self.assertEqual(set(result["breakdown"].keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()
