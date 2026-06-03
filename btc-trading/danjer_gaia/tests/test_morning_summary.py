"""朝サマリー雛形のユニットテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest
import json

from danjer_gaia.schemas import Trade, TradingPeriod
from danjer_gaia.regime import RegimeResult
from danjer_gaia.morning_summary import (
    OvernightDecision, CurrentPosition, PendingApproval, RiskAlert,
    MorningSummary, make_summary, to_markdown, to_dict,
)


def make_trade(net_profit=100.0, equity=10000.0, hours=2.0):
    now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    return Trade(
        trade_id="t1", symbol="BTCUSDT", side="long",
        entered_at=now, exited_at=now + timedelta(hours=1),
        elapsed_hours=hours, entry_price=60000, exit_price=60500,
        size=0.001, leverage=2.0, gross_profit=net_profit + 5,
        fees=3.0, slippage=2.0, net_profit=net_profit,
        avg_equity=equity,
    )


class TestMakeSummary(unittest.TestCase):
    def test_empty_period(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12),
            period_end=now,
            trades=[],
        )
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=None, risk_alerts=[], pending_approvals=[],
            now=now,
        )
        self.assertEqual(summary.overnight_pnl, 0.0)
        self.assertEqual(summary.overnight_trades, 0)
        self.assertEqual(summary.system_status, "healthy")
        self.assertEqual(len(summary.positions), 0)

    def test_with_trades_and_positions(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12),
            period_end=now,
            trades=[make_trade(100), make_trade(-50)],
        )
        positions = [CurrentPosition(
            symbol="BTCUSDT", side="long", size=0.001,
            entry_price=60000, current_price=60500,
            leverage=2.0, unrealized_pnl=50.0,
            sl_price=58000, tp_price=63000,
            opened_at=now,
        )]
        summary = make_summary(
            period=period, decisions=[], positions=positions,
            regime=None, risk_alerts=[], pending_approvals=[],
            now=now,
        )
        self.assertEqual(summary.overnight_pnl, 50.0)
        self.assertEqual(summary.overnight_trades, 2)
        self.assertEqual(len(summary.positions), 1)

    def test_with_regime(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12),
            period_end=now,
        )
        regime = RegimeResult(
            label="calm_up", atr=0.01, slope=0.0005,
            atr_percentile=0.5, slope_percentile=0.8,
            high_vol_threshold=0.02, up_trend_threshold=0.0002,
            down_trend_threshold=-0.0002, samples_used=720,
        )
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=regime, risk_alerts=[], pending_approvals=[],
            now=now,
        )
        self.assertEqual(summary.current_regime, "calm_up")
        self.assertIsNotNone(summary.regime_suggested_action)


class TestMarkdown(unittest.TestCase):
    def test_markdown_basic(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12), period_end=now,
        )
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=None, risk_alerts=[], pending_approvals=[],
            now=now,
        )
        md = to_markdown(summary)
        self.assertIn("# 🌅 danjer-GAIA 朝サマリー", md)
        self.assertIn("HEALTHY", md)
        self.assertIn("夜間トレード成果", md)
        self.assertIn("現在ポジション: なし", md)
        self.assertIn("リスク警告: なし", md)
        self.assertIn("承認待ち: なし", md)

    def test_markdown_with_alerts(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12), period_end=now,
        )
        alerts = [
            RiskAlert(now, "L1", "日次DD -2% 到達"),
            RiskAlert(now, "L3", "API異常 検出"),
        ]
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=None, risk_alerts=alerts, pending_approvals=[],
            now=now, system_status="warning",
        )
        md = to_markdown(summary)
        self.assertIn("[L1]", md)
        self.assertIn("[L3]", md)
        self.assertIn("WARNING", md)

    def test_markdown_with_approval(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12), period_end=now,
        )
        approvals = [PendingApproval(
            timestamp=now, proposed_action="LONG BTCUSDT 0.005",
            reason="confidence 0.85 + low risk 0.2",
            suggested_size=0.005, suggested_leverage=3.0,
            expected_value=150.0, risk_assessment="moderate",
        )]
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=None, risk_alerts=[], pending_approvals=approvals,
            now=now,
        )
        md = to_markdown(summary)
        self.assertIn("LONG BTCUSDT 0.005", md)
        self.assertIn("confidence 0.85", md)


class TestJSONDict(unittest.TestCase):
    def test_to_dict_serializable(self):
        now = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
        period = TradingPeriod(
            period_start=now - timedelta(hours=12), period_end=now,
        )
        summary = make_summary(
            period=period, decisions=[], positions=[],
            regime=None, risk_alerts=[], pending_approvals=[],
            now=now,
        )
        d = to_dict(summary)
        # JSON にシリアライズできるか
        s = json.dumps(d, ensure_ascii=False)
        # 再パース可能
        loaded = json.loads(s)
        self.assertIn("overnight_pnl", loaded)
        self.assertEqual(loaded["overnight_pnl"], 0.0)


if __name__ == "__main__":
    unittest.main()
