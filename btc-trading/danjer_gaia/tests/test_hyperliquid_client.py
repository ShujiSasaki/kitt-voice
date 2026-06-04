"""
Hyperliquid Client tests (mock_mode、 Phase 0 接続検証)

Shuji Wallet 準備前でも実行可能。 SDK インストール不要 (mock_mode のみテスト)。
mainnet/testnet 実接続は Phase 0 Day -4 以降、 Wallet 作成後に実施。
"""
import unittest
from datetime import datetime, timezone

from danjer_gaia.exchange.base import (
    OrderSide, OrderType, MarketSnapshot, Balance, ExchangeError,
)
from danjer_gaia.exchange.hyperliquid_client import (
    HyperliquidClient, HyperliquidConfig,
    MAINNET_API_URL, TESTNET_API_URL,
    MAKER_FEE_PCT, TAKER_FEE_PCT,
)


def _mk_snapshot(symbol="BTC", price=100000.0):
    return MarketSnapshot(
        symbol=symbol,
        last_price=price,
        mark_price=price,
        bid_top5_depth=50_000_000.0,
        ask_top5_depth=50_000_000.0,
        funding_rate=0.0001,
        open_interest=1_000_000.0,
        spread=0.30,
        timestamp=datetime.now(timezone.utc),
    )


class TestHyperliquidConfig(unittest.TestCase):
    def test_default_mainnet_url(self):
        cfg = HyperliquidConfig()
        self.assertEqual(cfg.base_url, MAINNET_API_URL)
        self.assertEqual(cfg.ws_url, "wss://api.hyperliquid.xyz/ws")
        self.assertFalse(cfg.mock_mode)

    def test_testnet_url_override(self):
        cfg = HyperliquidConfig(base_url=TESTNET_API_URL)
        self.assertEqual(cfg.base_url, TESTNET_API_URL)

    def test_fee_constants(self):
        # Round 34 検証値、 v8反映
        self.assertEqual(MAKER_FEE_PCT, -0.00001)
        self.assertEqual(TAKER_FEE_PCT, 0.00035)


class TestHyperliquidClientMockMode(unittest.TestCase):
    """mock_mode テスト (Phase 0 接続前の動作確認用)"""

    def setUp(self):
        self.client = HyperliquidClient(HyperliquidConfig(mock_mode=True))
        self.client.set_mock_balance(Balance(
            equity=1000.0, available=1000.0, used=0.0, currency="USDC",
        ))
        self.client.set_mock_market(_mk_snapshot())

    def test_name(self):
        self.assertEqual(self.client.name, "hyperliquid")

    def test_mock_balance(self):
        b = self.client.get_balance()
        self.assertEqual(b.equity, 1000.0)
        self.assertEqual(b.currency, "USDC")

    def test_mock_position_none(self):
        self.assertIsNone(self.client.get_position("BTC"))

    def test_mock_market(self):
        m = self.client.get_market("BTC")
        self.assertEqual(m.last_price, 100000.0)
        self.assertEqual(m.mark_price, 100000.0)

    def test_mock_market_missing_raises(self):
        with self.assertRaises(ExchangeError):
            self.client.get_market("ETH")

    def test_mock_place_buy_order(self):
        result = self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-123",
            sl_price=99000.0,
        )
        self.assertEqual(result.status, "filled")
        self.assertGreater(result.filled_price, 100000.0)  # 0.05% pessimistic
        self.assertIsNotNone(result.sl_order_id)
        # 手数料は taker (MARKET) なので 0.035% 課金
        self.assertGreater(result.fees, 0)

    def test_mock_place_sell_order(self):
        result = self.client.place_order(
            symbol="BTC", side=OrderSide.SELL, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-124",
        )
        self.assertEqual(result.status, "filled")
        self.assertLess(result.filled_price, 100000.0)  # SELL slippage

    def test_mock_position_after_buy(self):
        self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-125",
        )
        pos = self.client.get_position("BTC")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.side, "long")
        self.assertEqual(pos.size, 0.01)

    def test_mock_close_position(self):
        self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-126",
        )
        result = self.client.close_position("BTC", decision_trace_id="trace-127")
        self.assertEqual(result.status, "filled")
        self.assertIsNone(self.client.get_position("BTC"))

    def test_mock_close_no_position(self):
        result = self.client.close_position("BTC")
        self.assertEqual(result.status, "rejected")
        self.assertIn("no position", result.error)

    def test_mock_min_size_reject(self):
        result = self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.00001,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-128",
        )
        self.assertEqual(result.status, "rejected")
        self.assertIn("min", result.error)

    def test_mock_cancel_order(self):
        # mock では常に True
        self.assertTrue(self.client.cancel_order("any-id"))

    def test_mock_subscribe_noop(self):
        # mock では subscribe は呼ばれた値を返すだけ
        callback = lambda snap: None
        handle = self.client.subscribe_market("BTC", callback)
        self.assertEqual(handle, callback)

    def test_mock_health_check(self):
        self.assertTrue(self.client.health_check())

    def test_mock_health_check_zero_equity(self):
        self.client.set_mock_balance(Balance(
            equity=0.0, available=0.0, used=0.0, currency="USDC",
        ))
        self.assertFalse(self.client.health_check())


class TestHyperliquidClientFees(unittest.TestCase):
    """手数料計算ロジック検証 (Round 34 maker rebate 想定)"""

    def setUp(self):
        self.client = HyperliquidClient(HyperliquidConfig(mock_mode=True))
        self.client.set_mock_balance(Balance(
            equity=10000.0, available=10000.0, used=0.0, currency="USDC",
        ))
        self.client.set_mock_market(_mk_snapshot(price=100000.0))

    def test_taker_fee_positive(self):
        """MARKET order → taker、 手数料は正値"""
        result = self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="taker",
        )
        # 想定: filled_price ~ 100050、 size 0.01 → notional ~ $1000.5
        # taker 0.035% → fee ~ $0.35
        self.assertAlmostEqual(result.fees, abs(result.filled_size * result.filled_price) * TAKER_FEE_PCT, places=6)
        self.assertGreater(result.fees, 0)

    def test_maker_fee_rebate(self):
        """LIMIT order → maker、 手数料は負値 (rebate)"""
        result = self.client.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.LIMIT, leverage=2.0,
            price=100000.0,
            decision_trace_id="maker",
        )
        # maker -0.001% → fee 負値
        self.assertLess(result.fees, 0)


class TestHyperliquidClientSdkUnavailable(unittest.TestCase):
    """SDK インストール時のエラーハンドリング (Wallet 接続前)"""

    def test_mock_mode_does_not_require_sdk(self):
        """mock_mode なら SDK なしでも初期化可能"""
        client = HyperliquidClient(HyperliquidConfig(mock_mode=True))
        self.assertEqual(client.name, "hyperliquid")
        self.assertIsNone(client._info)
        self.assertIsNone(client._exchange)

    def test_mainnet_init_requires_sdk(self):
        """mock_mode=False で SDK 未インストールなら ExchangeError"""
        try:
            import hyperliquid  # noqa: F401
            self.skipTest("hyperliquid-python-sdk is installed, cannot test missing case")
        except ImportError:
            pass
        with self.assertRaises(ExchangeError) as ctx:
            HyperliquidClient(HyperliquidConfig(mock_mode=False))
        self.assertIn("hyperliquid-python-sdk", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
