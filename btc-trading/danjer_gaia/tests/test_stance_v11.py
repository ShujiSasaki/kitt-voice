"""Stance v11 (Round 43、 AI制約最小化) テスト"""
import unittest
from datetime import datetime, timedelta, timezone

from danjer_gaia.stance import Stance, STANCE_JSON_SCHEMA


def _make_stance(**overrides):
    n = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        direction=0.7, confidence=0.8, risk_level=0.2,
        valid_until=n + timedelta(minutes=15),
        max_lev=3.0, sl_atr_mult=1.5,
        tp_policy="trailing", stance="long_bias",
    )
    defaults.update(overrides)
    return Stance(**defaults)


class TestStanceV11MaxLev(unittest.TestCase):
    """v11: max_lev 上限 10.0 → 50.0 (Hyperliquid理論上限)"""

    def test_v11_max_lev_schema_50(self):
        self.assertEqual(STANCE_JSON_SCHEMA["properties"]["max_lev"]["maximum"], 50.0)

    def test_v11_high_leverage_allowed(self):
        """v11 で 10x超の自律判断レバを受容"""
        s = _make_stance(max_lev=30.0)
        self.assertEqual(s.max_lev, 30.0)

    def test_v11_extreme_leverage_50x(self):
        s = _make_stance(max_lev=50.0)
        self.assertEqual(s.max_lev, 50.0)


class TestStanceV11NewFields(unittest.TestCase):
    """v11 新フィールド (optional)"""

    def test_time_horizon_default_none(self):
        s = _make_stance()
        self.assertIsNone(s.time_horizon)

    def test_time_horizon_short(self):
        s = _make_stance(time_horizon="short_term")
        self.assertEqual(s.time_horizon, "short_term")

    def test_time_horizon_long(self):
        s = _make_stance(time_horizon="long_term")
        self.assertEqual(s.time_horizon, "long_term")

    def test_target_pool_allocation_default_none(self):
        s = _make_stance()
        self.assertIsNone(s.target_pool_allocation)

    def test_target_pool_allocation_pure_short(self):
        """1.0 = 全て短期プール"""
        s = _make_stance(target_pool_allocation=1.0)
        self.assertEqual(s.target_pool_allocation, 1.0)

    def test_target_pool_allocation_pure_long(self):
        """0.0 = 全て長期プール"""
        s = _make_stance(target_pool_allocation=0.0)
        self.assertEqual(s.target_pool_allocation, 0.0)

    def test_target_pool_allocation_balanced(self):
        s = _make_stance(target_pool_allocation=0.5)
        self.assertEqual(s.target_pool_allocation, 0.5)

    def test_recommended_exchange_auto(self):
        s = _make_stance(recommended_exchange="auto")
        self.assertEqual(s.recommended_exchange, "auto")

    def test_recommended_exchange_hyperliquid(self):
        s = _make_stance(recommended_exchange="hyperliquid")
        self.assertEqual(s.recommended_exchange, "hyperliquid")


class TestStanceV11JsonSchema(unittest.TestCase):
    """v11 JSON Schema 拡張"""

    def test_time_horizon_in_schema(self):
        self.assertIn("time_horizon", STANCE_JSON_SCHEMA["properties"])
        enum_vals = STANCE_JSON_SCHEMA["properties"]["time_horizon"]["enum"]
        self.assertIn("short_term", enum_vals)
        self.assertIn("long_term", enum_vals)

    def test_target_pool_allocation_in_schema(self):
        self.assertIn("target_pool_allocation", STANCE_JSON_SCHEMA["properties"])
        p = STANCE_JSON_SCHEMA["properties"]["target_pool_allocation"]
        self.assertEqual(p["minimum"], 0.0)
        self.assertEqual(p["maximum"], 1.0)

    def test_recommended_exchange_in_schema(self):
        self.assertIn("recommended_exchange", STANCE_JSON_SCHEMA["properties"])
        enum_vals = STANCE_JSON_SCHEMA["properties"]["recommended_exchange"]["enum"]
        self.assertIn("auto", enum_vals)
        self.assertIn("hyperliquid", enum_vals)
        self.assertIn("bitget", enum_vals)
        self.assertIn("exness", enum_vals)


class TestExchangeRouterAiDynamic(unittest.TestCase):
    """v11 ExchangeRouter 動的設定"""

    def test_ai_dynamic_config_specific(self):
        """AI が hyperliquid を指定 → 100% hyperliquid"""
        from danjer_gaia.exchange.exchange_router import ai_dynamic_config
        cfg = ai_dynamic_config(
            enabled_exchanges=["hyperliquid", "bitget", "exness"],
            stance_recommended="hyperliquid",
        )
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertEqual(weights["hyperliquid"].target_pct, 1.0)
        self.assertEqual(weights["bitget"].target_pct, 0.0)
        self.assertEqual(weights["exness"].target_pct, 0.0)

    def test_ai_dynamic_config_auto(self):
        """AI が auto → 均等配分"""
        from danjer_gaia.exchange.exchange_router import ai_dynamic_config
        cfg = ai_dynamic_config(
            enabled_exchanges=["hyperliquid", "bitget"],
            stance_recommended="auto",
        )
        weights = {w.exchange_name: w for w in cfg.weights}
        self.assertAlmostEqual(weights["hyperliquid"].target_pct, 0.5)
        self.assertAlmostEqual(weights["bitget"].target_pct, 0.5)

    def test_apply_dynamic_config_router(self):
        """Router.apply_dynamic_config() で 動的変更"""
        from danjer_gaia.exchange.exchange_router import (
            ExchangeRouter, phase_2_3_config,
        )
        from danjer_gaia.exchange.hyperliquid_client import (
            HyperliquidClient, HyperliquidConfig,
        )
        from danjer_gaia.exchange.base import Balance

        hl = HyperliquidClient(HyperliquidConfig(mock_mode=True))
        hl.set_mock_balance(Balance(equity=1000.0, available=1000.0,
                                     used=0.0, currency="USDC"))
        router = ExchangeRouter(
            exchanges={"hyperliquid": hl},
            config=phase_2_3_config(),
        )
        # 初期: phase_2_3 (Hyperliquid 100%)
        self.assertEqual(router.config.weights[0].target_pct, 1.0)
        # AI動的変更: bitget指定
        router.apply_dynamic_config(stance_recommended="hyperliquid")
        weights = {w.exchange_name: w for w in router.config.weights}
        self.assertEqual(weights["hyperliquid"].target_pct, 1.0)


if __name__ == "__main__":
    unittest.main()
