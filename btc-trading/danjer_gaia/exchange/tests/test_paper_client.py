"""Paper Trading Client のユニットテスト"""
from __future__ import annotations
from datetime import datetime, timezone
import unittest

from danjer_gaia.exchange.base import (
    OrderType, OrderSide, MarketSnapshot,
)
from danjer_gaia.exchange.paper_client import PaperClient, PaperConfig


def make_market(price=60000.0, symbol="BTCUSDT"):
    return MarketSnapshot(
        symbol=symbol, last_price=price, mark_price=price,
        bid_top5_depth=50.0, ask_top5_depth=50.0,
        funding_rate=0.0001, open_interest=1000000.0,
        spread=2.0,
    )


class TestBalance(unittest.TestCase):
    def test_initial(self):
        c = PaperClient(initial_equity=10000.0)
        b = c.get_balance()
        self.assertEqual(b.equity, 10000.0)
        self.assertEqual(b.available, 10000.0)


class TestPlaceOrder(unittest.TestCase):
    def setUp(self):
        self.c = PaperClient(initial_equity=10000.0)
        self.c.update_market(make_market(60000.0))

    def test_basic_long(self):
        r = self.c.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.001,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1", sl_price=58000.0,
        )
        self.assertEqual(r.status, "filled")
        self.assertGreater(r.filled_price, 60000.0)  # slippage で不利
        self.assertIsNotNone(r.sl_order_id)
        pos = self.c.get_position("BTCUSDT")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.side, "long")

    def test_basic_short(self):
        r = self.c.place_order(
            symbol="BTCUSDT", side=OrderSide.SELL, size=0.001,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1", sl_price=62000.0,
        )
        self.assertEqual(r.status, "filled")
        self.assertLess(r.filled_price, 60000.0)  # short は逆向き slippage
        pos = self.c.get_position("BTCUSDT")
        self.assertEqual(pos.side, "short")

    def test_min_size_reject(self):
        r = self.c.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.00001,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1",
        )
        self.assertEqual(r.status, "rejected")

    def test_insufficient_balance(self):
        """size 1 BTC × 60000 / lev 2 = 30000 USD > equity 10000"""
        r = self.c.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=1.0,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1",
        )
        self.assertEqual(r.status, "rejected")
        self.assertIn("insufficient", r.error)


class TestSLTrigger(unittest.TestCase):
    def setUp(self):
        self.c = PaperClient(initial_equity=10000.0)
        self.c.update_market(make_market(60000.0))

    def test_long_sl_hit(self):
        r = self.c.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1", sl_price=58000.0,
        )
        self.assertEqual(r.status, "filled")
        # 価格が SL以下に下落
        self.c.update_market(make_market(57500.0))
        # ポジション全閉されている
        pos = self.c.get_position("BTCUSDT")
        self.assertIsNone(pos)
        # 残高は減っている (損失計上)
        b = self.c.get_balance()
        self.assertLess(b.equity, 10000.0)


class TestClosePosition(unittest.TestCase):
    def test_full_close_with_profit(self):
        c = PaperClient(initial_equity=10000.0)
        c.update_market(make_market(60000.0))
        c.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="t1",
        )
        # 価格上昇
        c.update_market(make_market(62000.0))
        r = c.close_position("BTCUSDT", decision_trace_id="t2")
        self.assertEqual(r.status, "filled")
        pos = c.get_position("BTCUSDT")
        self.assertIsNone(pos)
        b = c.get_balance()
        self.assertGreater(b.equity, 10000.0)  # 利益


class TestHealthCheck(unittest.TestCase):
    def test_alive(self):
        c = PaperClient(initial_equity=10000.0)
        self.assertTrue(c.health_check())

    def test_dead_equity(self):
        c = PaperClient(initial_equity=0.0)
        self.assertFalse(c.health_check())


if __name__ == "__main__":
    unittest.main()
