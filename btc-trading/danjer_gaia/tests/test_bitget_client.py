"""Bitget Client テスト (mock_mode、 Phase 3後半着手前の動作確認)"""
import unittest
from datetime import datetime, timezone

from danjer_gaia.exchange.base import (
    OrderSide, OrderType, MarketSnapshot, Balance, ExchangeError,
)
from danjer_gaia.exchange.bitget_client import (
    BitgetClient, BitgetConfig,
    CONTRACT_MAKER_FEE_PCT, CONTRACT_TAKER_FEE_PCT,
)


def _mk_snapshot(symbol="BTCUSDT", price=100000.0):
    return MarketSnapshot(
        symbol=symbol, last_price=price, mark_price=price,
        bid_top5_depth=2000.0, ask_top5_depth=2000.0,
        funding_rate=0.0001, open_interest=5_000_000.0,
        spread=0.5, timestamp=datetime.now(timezone.utc),
    )


class TestBitgetConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = BitgetConfig()
        self.assertEqual(cfg.market_type, "swap")
        self.assertFalse(cfg.sandbox)
        self.assertFalse(cfg.mock_mode)
        self.assertFalse(cfg.use_bgb_discount)  # v8 で BGB保有しない方針

    def test_fee_constants(self):
        # Round 34 検証値
        self.assertEqual(CONTRACT_MAKER_FEE_PCT, 0.0002)  # 0.02%
        self.assertEqual(CONTRACT_TAKER_FEE_PCT, 0.0006)  # 0.06%


class TestBitgetClientMockMode(unittest.TestCase):
    def setUp(self):
        self.client = BitgetClient(BitgetConfig(mock_mode=True))
        self.client.set_mock_balance(Balance(
            equity=2000.0, available=2000.0, used=0.0, currency="USDT",
        ))
        self.client.set_mock_market(_mk_snapshot())

    def test_name(self):
        self.assertEqual(self.client.name, "bitget")

    def test_mock_balance(self):
        b = self.client.get_balance()
        self.assertEqual(b.equity, 2000.0)
        self.assertEqual(b.currency, "USDT")

    def test_mock_position_none(self):
        self.assertIsNone(self.client.get_position("BTCUSDT"))

    def test_mock_market(self):
        m = self.client.get_market("BTCUSDT")
        self.assertEqual(m.last_price, 100000.0)

    def test_mock_market_missing_raises(self):
        with self.assertRaises(ExchangeError):
            self.client.get_market("ETHUSDT")

    def test_mock_place_buy_order(self):
        result = self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-b1",
            sl_price=99000.0,
        )
        self.assertEqual(result.status, "filled")
        self.assertGreater(result.filled_price, 100000.0)
        # Bitget taker 0.06% で fee
        expected_fee = abs(result.filled_size * result.filled_price) * CONTRACT_TAKER_FEE_PCT
        self.assertAlmostEqual(result.fees, expected_fee, places=6)

    def test_mock_position_after_buy(self):
        self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-b2",
        )
        pos = self.client.get_position("BTCUSDT")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.side, "long")

    def test_mock_close_position(self):
        self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-b3",
        )
        result = self.client.close_position("BTCUSDT", decision_trace_id="trace-b4")
        self.assertEqual(result.status, "filled")

    def test_mock_min_size_reject(self):
        result = self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.00001,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-b5",
        )
        self.assertEqual(result.status, "rejected")

    def test_mock_health_check(self):
        self.assertTrue(self.client.health_check())

    def test_mock_cancel_order(self):
        self.assertTrue(self.client.cancel_order("any-id"))

    def test_subscribe_not_implemented(self):
        """mock_mode では subscribe noop"""
        callback = lambda snap: None
        handle = self.client.subscribe_market("BTCUSDT", callback)
        self.assertEqual(handle, callback)


class TestBitgetClientFees(unittest.TestCase):
    """Bitget 手数料計算検証"""

    def setUp(self):
        self.client = BitgetClient(BitgetConfig(mock_mode=True))
        self.client.set_mock_balance(Balance(
            equity=10000.0, available=10000.0, used=0.0, currency="USDT",
        ))
        self.client.set_mock_market(_mk_snapshot())

    def test_taker_fee_higher_than_hyperliquid(self):
        """Bitget taker 0.06% > Hyperliquid taker 0.035%"""
        from danjer_gaia.exchange.hyperliquid_client import TAKER_FEE_PCT as HL_TAKER
        self.assertGreater(CONTRACT_TAKER_FEE_PCT, HL_TAKER)

    def test_maker_fee_no_rebate(self):
        """Bitget は maker rebate なし (Hyperliquid は rebate)"""
        from danjer_gaia.exchange.hyperliquid_client import MAKER_FEE_PCT as HL_MAKER
        self.assertGreater(CONTRACT_MAKER_FEE_PCT, 0)  # bitget は正値
        self.assertLess(HL_MAKER, 0)                    # Hyperliquid は負値 (rebate)


class TestBitgetClientSdkUnavailable(unittest.TestCase):
    def test_mock_mode_does_not_require_ccxt(self):
        client = BitgetClient(BitgetConfig(mock_mode=True))
        self.assertEqual(client.name, "bitget")
        self.assertIsNone(client._exchange)

    def test_mainnet_init_requires_ccxt(self):
        try:
            import ccxt  # noqa: F401
            self.skipTest("ccxt is installed, cannot test missing case")
        except ImportError:
            pass
        with self.assertRaises(ExchangeError) as ctx:
            BitgetClient(BitgetConfig(mock_mode=False))
        self.assertIn("ccxt", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
