"""ガード減算ペナルティのユニットテスト"""
from __future__ import annotations
from datetime import datetime, timedelta
import unittest

from danjer_gaia.schemas import Trade, TradingPeriod, GuardConfig
from danjer_gaia.guards import (
    liquidation_penalty, max_dd_penalty, no_stop_penalty,
    slippage_penalty, overleverage_penalty, overtrade_penalty,
    total_guard_penalty,
)


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


class TestLiquidationPenalty(unittest.TestCase):
    def test_no_liquidations(self):
        trades = [make_trade(was_liquidated=False) for _ in range(5)]
        self.assertEqual(liquidation_penalty(trades), 0.0)

    def test_one_liquidation(self):
        trades = [
            make_trade(was_liquidated=True),
            make_trade(was_liquidated=False),
        ]
        # default const = 100, so -100
        self.assertEqual(liquidation_penalty(trades), -100.0)

    def test_multiple_liquidations(self):
        trades = [make_trade(was_liquidated=True) for _ in range(3)]
        self.assertEqual(liquidation_penalty(trades), -300.0)


class TestMaxDDPenalty(unittest.TestCase):
    def test_below_limit_no_penalty(self):
        """DD < dd_limit (5%) ならペナルティなし"""
        trades = [make_trade(max_dd_during=0.03)]
        self.assertEqual(max_dd_penalty(trades), 0.0)

    def test_at_limit_no_penalty(self):
        trades = [make_trade(max_dd_during=0.05)]
        self.assertEqual(max_dd_penalty(trades), 0.0)

    def test_above_limit_squared(self):
        """DD超過の二乗ペナルティ"""
        # DD=0.10, limit=0.05 → excess=0.05 → penalty = 0.05^2 = 0.0025
        trades = [make_trade(max_dd_during=0.10)]
        self.assertAlmostEqual(max_dd_penalty(trades), -0.0025, places=6)


class TestNoStopPenalty(unittest.TestCase):
    def test_all_have_sl(self):
        trades = [make_trade(had_sl=True) for _ in range(5)]
        self.assertEqual(no_stop_penalty(trades), 0.0)

    def test_one_no_sl(self):
        trades = [make_trade(had_sl=False)]
        self.assertEqual(no_stop_penalty(trades), -20.0)


class TestSlippagePenalty(unittest.TestCase):
    def test_below_baseline_no_penalty(self):
        trades = [make_trade(slippage=3.0)]
        # baseline=5.0 → excess=0 → 0
        self.assertEqual(slippage_penalty(trades, baseline_slippage=5.0), 0.0)

    def test_above_baseline(self):
        trades = [make_trade(slippage=10.0)]
        # excess=5.0, coef=10 → -50
        self.assertEqual(slippage_penalty(trades, baseline_slippage=5.0), -50.0)


class TestOverLeveragePenalty(unittest.TestCase):
    def test_below_threshold(self):
        trades = [make_trade(leverage=3.0)]
        # threshold=5.0 → excess=0
        self.assertEqual(overleverage_penalty(trades), 0.0)

    def test_above_threshold(self):
        trades = [make_trade(leverage=8.0)]
        # excess=3.0, coef=2 → -6
        self.assertEqual(overleverage_penalty(trades), -6.0)


class TestOverTradePenalty(unittest.TestCase):
    def test_below_limit(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[make_trade() for _ in range(20)],
        )
        # default limit=50, 20<50 → 0
        self.assertEqual(overtrade_penalty(period), 0.0)

    def test_above_limit(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[make_trade() for _ in range(60)],
        )
        # excess=10, coef=0.5 → -5
        self.assertEqual(overtrade_penalty(period), -5.0)


class TestTotalGuardPenalty(unittest.TestCase):
    def test_combined(self):
        period = TradingPeriod(
            period_start=datetime(2026, 6, 1),
            period_end=datetime(2026, 6, 30),
            trades=[
                make_trade(was_liquidated=True, had_sl=False,
                           slippage=10.0, leverage=8.0, max_dd_during=0.10),
            ],
        )
        result = total_guard_penalty(period, baseline_slippage=5.0)
        # liquidation=-100, max_dd=-0.0025, no_stop=-20, slippage=-50, overlev=-6, overtrade=0
        self.assertAlmostEqual(result["liquidation"], -100.0)
        self.assertAlmostEqual(result["no_stop"], -20.0)
        self.assertAlmostEqual(result["slippage"], -50.0)
        self.assertAlmostEqual(result["overleverage"], -6.0)
        self.assertAlmostEqual(result["overtrade"], 0.0)
        self.assertAlmostEqual(result["total"], -176.0025, places=4)


if __name__ == "__main__":
    unittest.main()
