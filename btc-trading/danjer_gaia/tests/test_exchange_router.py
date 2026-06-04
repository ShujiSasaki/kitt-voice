"""ExchangeRouter テスト (Phase 4 動的切替の動作検証)"""
import unittest
from datetime import datetime, timezone

from danjer_gaia.exchange.base import (
    OrderSide, OrderType, Balance, MarketSnapshot,
)
from danjer_gaia.exchange.hyperliquid_client import (
    HyperliquidClient, HyperliquidConfig,
)
from danjer_gaia.exchange.exchange_router import (
    ExchangeRouter, ExchangeStatus, ExchangeWeight, RouterConfig,
    phase_2_3_config, phase_3_late_config, phase_4_cap1_config,
    phase_4_cap2_config, phase_5_cap5_config,
)


def _mk_snapshot(symbol="BTC", price=100000.0, depth=500.0):
    """板厚 $50M (500 BTC × $100k = $50M、 R72閾値 $30M超え)"""
    return MarketSnapshot(
        symbol=symbol, last_price=price, mark_price=price,
        bid_top5_depth=depth, ask_top5_depth=depth,
        funding_rate=0.0001, open_interest=1_000_000.0,
        spread=0.3, timestamp=datetime.now(timezone.utc),
    )


def _make_mock_hl_client(equity=1000.0, depth=500.0):
    """mock_mode HyperliquidClient セットアップ"""
    client = HyperliquidClient(HyperliquidConfig(mock_mode=True))
    client.set_mock_balance(Balance(
        equity=equity, available=equity, used=0.0, currency="USDC",
    ))
    client.set_mock_market(_mk_snapshot(depth=depth))
    return client


class TestPhaseConfigs(unittest.TestCase):
    """Phase別 デフォルト構成"""

    def test_phase_2_3_hyperliquid_only(self):
        cfg = phase_2_3_config()
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertTrue(weights["hyperliquid"].enabled)
        self.assertEqual(weights["hyperliquid"].target_pct, 1.0)
        self.assertFalse(weights["bitget"].enabled)
        self.assertFalse(weights["exness"].enabled)

    def test_phase_3_late_bitget_readonly(self):
        cfg = phase_3_late_config()
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertTrue(weights["hyperliquid"].enabled)
        self.assertTrue(weights["bitget"].enabled)  # read-only テスト
        self.assertEqual(weights["bitget"].target_pct, 0.0)

    def test_phase_4_cap1_split_60_40(self):
        cfg = phase_4_cap1_config()
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertEqual(weights["hyperliquid"].target_pct, 0.6)
        self.assertEqual(weights["exness"].target_pct, 0.4)

    def test_phase_4_cap2_split_50_50(self):
        cfg = phase_4_cap2_config()
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertEqual(weights["hyperliquid"].target_pct, 0.5)
        self.assertEqual(weights["exness"].target_pct, 0.5)

    def test_phase_5_cap5_with_lighter(self):
        cfg = phase_5_cap5_config()
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertEqual(weights["hyperliquid"].target_pct, 0.4)
        self.assertEqual(weights["exness"].target_pct, 0.4)
        self.assertEqual(weights["lighter"].target_pct, 0.2)


class TestExchangeRouterHealthCheck(unittest.TestCase):
    def setUp(self):
        self.hl = _make_mock_hl_client()
        self.router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=phase_2_3_config(),
        )

    def test_health_check_healthy(self):
        statuses = self.router.check_health()
        self.assertEqual(statuses["hyperliquid"], ExchangeStatus.HEALTHY)

    def test_get_status(self):
        self.router.check_health()
        self.assertEqual(
            self.router.get_status("hyperliquid"),
            ExchangeStatus.HEALTHY,
        )

    def test_unknown_exchange_outage(self):
        self.assertEqual(
            self.router.get_status("unknown"),
            ExchangeStatus.OUTAGE,
        )


class TestExchangeRouterAllocation(unittest.TestCase):
    def setUp(self):
        self.hl = _make_mock_hl_client()
        self.router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=phase_2_3_config(),
        )
        self.router.check_health()

    def test_single_exchange_full_allocation(self):
        alloc = self.router.compute_allocation(0.1)
        self.assertEqual(alloc.get("hyperliquid"), 0.1)

    def test_phase_4_cap1_split(self):
        # mock 環境では Exness/bitget は登録されてないので Hyperliquid のみ
        # ただし target_pct は正規化される
        router = ExchangeRouter(
            exchanges={
                "hyperliquid": self.hl,
                # 仮の Exness/bitget (mock)
                "exness": _make_mock_hl_client(equity=1000.0),  # mock扱い
            },
            config=phase_4_cap1_config(),
        )
        router.check_health()
        alloc = router.compute_allocation(0.1)
        # 60:40 比率 (Exness=Hyperliquid mock として代用)
        self.assertAlmostEqual(alloc["hyperliquid"], 0.06, places=4)
        self.assertAlmostEqual(alloc["exness"], 0.04, places=4)


class TestExchangeRouterPlaceOrder(unittest.TestCase):
    def setUp(self):
        self.hl = _make_mock_hl_client()
        self.router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=phase_2_3_config(),
        )
        self.router.check_health()

    def test_place_order_routes_to_hyperliquid(self):
        results = self.router.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-1",
            sl_price=99000.0,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "filled")
        self.assertGreater(results[0].filled_size, 0)

    def test_unknown_exchange_rejected(self):
        # 未登録 exchange に振り分けようとする状況
        cfg = RouterConfig(weights=[
            ExchangeWeight("unknown_ex", target_pct=1.0, enabled=True),
        ])
        router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=cfg,
        )
        # unknown_ex は exchanges に登録されてないので、 router._health に存在しない
        # → unhealthy扱い → fallback で Hyperliquidに振り分ける
        # ただし weight に unknown_ex しかないので、 fallback先がない
        # health check しても unknown は対象外
        router._health["unknown_ex"] = ExchangeStatus.HEALTHY  # 偽装
        results = router.place_order(
            symbol="BTC", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="trace-2",
        )
        # unknown_ex は exchanges に無いので rejected
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "rejected")


class TestSymbolTranslation(unittest.TestCase):
    def setUp(self):
        self.hl = _make_mock_hl_client()
        self.router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=phase_2_3_config(),
        )

    def test_hyperliquid_strips_quote(self):
        self.assertEqual(self.router._translate_symbol("hyperliquid", "BTCUSDT"), "BTC")
        self.assertEqual(self.router._translate_symbol("hyperliquid", "BTC"), "BTC")

    def test_bitget_uses_usdt(self):
        self.assertEqual(self.router._translate_symbol("bitget", "BTC"), "BTCUSDT")
        self.assertEqual(self.router._translate_symbol("bitget", "BTCUSD"), "BTCUSDT")

    def test_exness_uses_usd(self):
        self.assertEqual(self.router._translate_symbol("exness", "BTC"), "BTCUSD")
        self.assertEqual(self.router._translate_symbol("exness", "BTCUSDT"), "BTCUSD")


class TestTotalBalance(unittest.TestCase):
    def setUp(self):
        self.hl = _make_mock_hl_client(equity=5000.0)
        self.router = ExchangeRouter(
            exchanges={"hyperliquid": self.hl},
            config=phase_2_3_config(),
        )

    def test_get_total_balance(self):
        balances = self.router.get_total_balance()
        self.assertEqual(balances["hyperliquid"].equity, 5000.0)

    def test_get_total_equity(self):
        self.assertEqual(self.router.get_total_equity(), 5000.0)


if __name__ == "__main__":
    unittest.main()
