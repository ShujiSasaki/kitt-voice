"""Simulator 統合フローのテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

from danjer_gaia.exchange.paper_client import PaperClient
from danjer_gaia.exchange.base import MarketSnapshot
from danjer_gaia.stance import Stance
from danjer_gaia.fast_guard import FastGuardSignal
from danjer_gaia.paper_trading.simulator import (
    PaperSimulator, SimulatorConfig, detect_fast_guard_signal,
)


def make_market(price=60000.0, **overrides):
    defaults = dict(
        symbol="BTCUSDT", last_price=price, mark_price=price,
        bid_top5_depth=50.0, ask_top5_depth=50.0,
        funding_rate=0.0001, open_interest=1000000.0, spread=2.0,
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def make_stance(now=None, **overrides):
    n = now or datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        direction=0.7, confidence=0.8, risk_level=0.2,
        valid_until=n + timedelta(minutes=15),
        max_lev=2.0, sl_atr_mult=1.5,
        tp_policy="trailing", stance="long_bias",
        notes="", issued_at=n,
    )
    defaults.update(overrides)
    return Stance(**defaults)


class TestDetectFastGuardSignal(unittest.TestCase):
    def test_normal(self):
        prev = make_market(60000.0)
        cur = make_market(60100.0)
        sig = detect_fast_guard_signal(cur, prev=prev, baseline_depth=50.0)
        self.assertEqual(sig, FastGuardSignal.NORMAL)

    def test_spike_up(self):
        prev = make_market(60000.0)
        cur = make_market(62000.0)  # +3.3%
        sig = detect_fast_guard_signal(cur, prev=prev, baseline_depth=50.0)
        self.assertEqual(sig, FastGuardSignal.PRICE_SPIKE_UP)

    def test_spike_down(self):
        prev = make_market(60000.0)
        cur = make_market(58000.0)  # -3.3%
        sig = detect_fast_guard_signal(cur, prev=prev, baseline_depth=50.0)
        self.assertEqual(sig, FastGuardSignal.PRICE_SPIKE_DOWN)

    def test_liquidity_drop(self):
        prev = make_market(60000.0)
        cur = make_market(60100.0, bid_top5_depth=10.0)  # 20% of baseline 50
        sig = detect_fast_guard_signal(cur, prev=prev, baseline_depth=50.0)
        self.assertEqual(sig, FastGuardSignal.LIQUIDITY_DROP)

    def test_api_error(self):
        cur = make_market(60000.0)
        sig = detect_fast_guard_signal(cur, api_latency_ms=1000.0)
        self.assertEqual(sig, FastGuardSignal.API_ERROR)


class TestSimulatorIntegration(unittest.TestCase):
    def setUp(self):
        self.exchange = PaperClient(initial_equity=10000.0)
        self.exchange.update_market(make_market(60000.0))
        self.sim = PaperSimulator(self.exchange)

    def test_no_stance_skips(self):
        """スタンス未受信 → LOCK_NEW_ENTRY → SKIP"""
        ev = self.sim.step(make_market(60100.0))
        self.assertEqual(ev.ttl_action, "lock_new_entry")
        self.assertIsNone(ev.order_result)

    def test_stance_received_long_executes(self):
        """long_bias スタンス + normal market → NEW_LONG → order placed"""
        self.sim.on_stance(make_stance(stance="long_bias", confidence=0.85))
        ev = self.sim.step(make_market(60100.0))
        self.assertEqual(ev.ttl_action, "use_stance")
        self.assertEqual(ev.final_action, "new_long")
        # order_result があるか
        self.assertIsNotNone(ev.order_result)
        if ev.order_result and ev.order_result.get("status") == "filled":
            pos = self.exchange.get_position("BTCUSDT")
            self.assertIsNotNone(pos)
            self.assertEqual(pos.side, "long")

    def test_price_spike_skips_new_entry(self):
        """急変時は新規エントリーをスキップ"""
        self.sim.on_stance(make_stance(stance="long_bias", confidence=0.85))
        # 1tick目で prev 設定
        self.sim.step(make_market(60000.0))
        # 急変 +5%
        ev = self.sim.step(make_market(63000.0))
        # SKIP_THIS_BAR or HOLD
        self.assertIn(ev.final_action, ["skip_this_bar", "hold"])


class TestSimulatorLogging(unittest.TestCase):
    def test_log_accumulates(self):
        ex = PaperClient(initial_equity=10000.0)
        ex.update_market(make_market(60000.0))
        sim = PaperSimulator(ex)
        sim.on_stance(make_stance())
        for i in range(3):
            sim.step(make_market(60000.0 + i * 10))
        log = sim.get_log()
        self.assertEqual(len(log), 3)

    def test_save_log_creates_file(self):
        import tempfile, os
        ex = PaperClient(initial_equity=10000.0)
        ex.update_market(make_market(60000.0))
        sim = PaperSimulator(ex)
        sim.on_stance(make_stance())
        sim.step(make_market(60100.0))
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            path = f.name
        try:
            sim.save_log(path)
            with open(path) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
