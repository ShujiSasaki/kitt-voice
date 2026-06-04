"""
PaperClient with Hyperliquid 手数料モデル統合テスト (v8反映)

R40 (paper 保守的) + R34 (maker rebate 検証) の動作確認。
"""
import unittest
from datetime import datetime, timezone

from danjer_gaia.exchange.base import (
    OrderSide, OrderType, MarketSnapshot,
)
from danjer_gaia.exchange.paper_client import (
    PaperClient, PaperConfig, BybitLegacyConfig,
)


def _mk_snapshot(symbol="BTCUSDT", price=100000.0):
    return MarketSnapshot(
        symbol=symbol, last_price=price, mark_price=price,
        bid_top5_depth=500.0, ask_top5_depth=500.0,
        funding_rate=0.0001, open_interest=1_000_000.0,
        spread=0.3, timestamp=datetime.now(timezone.utc),
    )


class TestPaperConfigHyperliquid(unittest.TestCase):
    """v8 反映: PaperConfig は Hyperliquid モデル"""

    def test_default_maker_is_rebate(self):
        cfg = PaperConfig()
        self.assertEqual(cfg.maker_fee_pct, -0.00001)
        self.assertLess(cfg.maker_fee_pct, 0)  # 負値 = rebate

    def test_default_taker_pct(self):
        cfg = PaperConfig()
        self.assertEqual(cfg.taker_fee_pct, 0.00035)

    def test_default_currency_usdc(self):
        cfg = PaperConfig()
        self.assertEqual(cfg.base_currency, "USDC")

    def test_bybit_legacy_config_preserved(self):
        """旧Bybit モデルがテスト互換性のため残置されているか"""
        cfg = BybitLegacyConfig()
        self.assertEqual(cfg.maker_fee_pct, -0.00025)
        self.assertEqual(cfg.taker_fee_pct, 0.00075)
        self.assertEqual(cfg.base_currency, "USDT")


class TestPaperClientHyperliquidFees(unittest.TestCase):
    """Hyperliquid 手数料計算の検証"""

    def setUp(self):
        self.client = PaperClient(initial_equity=10000.0)
        self.client.update_market(_mk_snapshot())

    def test_market_order_taker_fee(self):
        result = self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="taker-test",
        )
        self.assertEqual(result.status, "filled")
        # taker 0.035% × notional
        expected_fee = abs(result.filled_size * result.filled_price) * 0.00035
        self.assertAlmostEqual(result.fees, expected_fee, places=6)
        self.assertGreater(result.fees, 0)

    def test_limit_order_maker_rebate(self):
        result = self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.LIMIT, leverage=2.0,
            price=100000.0,
            decision_trace_id="maker-test",
        )
        # maker は負値 (rebate)
        self.assertLess(result.fees, 0)

    def test_currency_usdc(self):
        balance = self.client.get_balance()
        self.assertEqual(balance.currency, "USDC")


class TestPaperClientEdgeCases(unittest.TestCase):
    """境界値・edge case"""

    def setUp(self):
        self.client = PaperClient(initial_equity=100.0)  # 小残高
        self.client.update_market(_mk_snapshot())

    def test_insufficient_margin_rejected(self):
        """残高不足で reject"""
        # $100 残高で 1 BTC ($100k) 発注 → 拒否
        result = self.client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=1.0,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="insufficient",
        )
        self.assertEqual(result.status, "rejected")
        self.assertIn("insufficient", result.error.lower())

    def test_no_market_data_rejected(self):
        """市場データなしで reject"""
        client = PaperClient(initial_equity=10000.0)
        # update_market 呼ばず
        result = client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="no-market",
        )
        self.assertEqual(result.status, "rejected")

    def test_sl_only_no_tp(self):
        """SLのみ、 TPなし"""
        client = PaperClient(initial_equity=10000.0)
        client.update_market(_mk_snapshot())
        result = client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="sl-only",
            sl_price=99000.0,
        )
        self.assertIsNotNone(result.sl_order_id)
        pos = client.get_position("BTCUSDT")
        self.assertEqual(pos.sl_price, 99000.0)
        self.assertIsNone(pos.tp_price)

    def test_partial_close(self):
        """部分決済"""
        client = PaperClient(initial_equity=10000.0)
        client.update_market(_mk_snapshot())
        client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.02,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="open",
        )
        # 0.01だけ部分決済
        result = client.close_position("BTCUSDT", size=0.01,
                                        decision_trace_id="partial-close")
        self.assertEqual(result.status, "filled")
        pos = client.get_position("BTCUSDT")
        self.assertIsNotNone(pos)  # 残ポジあり
        self.assertAlmostEqual(pos.size, 0.01, places=6)

    def test_sl_trigger_long(self):
        """LONGポジでSL到達 → 自動決済"""
        client = PaperClient(initial_equity=10000.0)
        client.update_market(_mk_snapshot(price=100000.0))
        client.place_order(
            symbol="BTCUSDT", side=OrderSide.BUY, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="sl-trigger",
            sl_price=99000.0,
        )
        # SL価格を下回るtickを送る
        client.update_market(_mk_snapshot(price=98500.0))
        pos = client.get_position("BTCUSDT")
        self.assertIsNone(pos)  # SLでポジ消失

    def test_sl_trigger_short(self):
        """SHORTポジでSL到達 → 自動決済"""
        client = PaperClient(initial_equity=10000.0)
        client.update_market(_mk_snapshot(price=100000.0))
        client.place_order(
            symbol="BTCUSDT", side=OrderSide.SELL, size=0.01,
            order_type=OrderType.MARKET, leverage=2.0,
            decision_trace_id="sl-short",
            sl_price=101000.0,
        )
        # SL価格を上回るtick
        client.update_market(_mk_snapshot(price=101500.0))
        pos = client.get_position("BTCUSDT")
        self.assertIsNone(pos)


class TestPaperClientCostEquivalence(unittest.TestCase):
    """v8 コスト効果検証 (Hyperliquid vs Bybit)"""

    def test_hyperliquid_cheaper_than_bybit_taker(self):
        """Hyperliquid taker (0.035%) は Bybit taker (0.075%) より安い"""
        hl_config = PaperConfig()
        bybit_config = BybitLegacyConfig()
        self.assertLess(hl_config.taker_fee_pct, bybit_config.taker_fee_pct)

    def test_hyperliquid_maker_rebate_less_than_bybit(self):
        """Hyperliquid maker rebate (-0.001%) は Bybit maker rebate (-0.025%) より小さい"""
        hl_config = PaperConfig()
        bybit_config = BybitLegacyConfig()
        # 絶対値で比較: Hyperliquid のリベート率は小さい
        self.assertGreater(hl_config.maker_fee_pct, bybit_config.maker_fee_pct)


if __name__ == "__main__":
    unittest.main()
