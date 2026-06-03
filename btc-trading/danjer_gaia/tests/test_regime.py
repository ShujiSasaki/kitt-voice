"""レジーム判定 (Day 9-10) のユニットテスト"""
from __future__ import annotations
import math
import unittest
import random

from danjer_gaia.regime import (
    OHLCV, calc_atr, calc_slope, normalized_slope, percentile,
    detect_regime, regime_to_hint,
)


def make_candles(closes, opens=None, highs=None, lows=None, vols=None):
    candles = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else c * 0.99
        h = highs[i] if highs else c * 1.01
        l = lows[i] if lows else c * 0.98
        v = vols[i] if vols else 100.0
        candles.append(OHLCV(timestamp=i*3600, open=o, high=h, low=l, close=c, volume=v))
    return candles


class TestATR(unittest.TestCase):
    def test_insufficient_data(self):
        candles = make_candles([50000, 50100])
        self.assertTrue(math.isnan(calc_atr(candles, period=14)))

    def test_simple(self):
        # 価格が緩やかに変動
        closes = [50000 + i * 10 for i in range(20)]
        candles = make_candles(closes)
        atr = calc_atr(candles, period=14)
        self.assertGreater(atr, 0)
        self.assertTrue(math.isfinite(atr))


class TestSlope(unittest.TestCase):
    def test_uptrend(self):
        # close が +100 ずつ
        candles = make_candles([50000 + i * 100 for i in range(20)])
        s = calc_slope(candles, window=20)
        self.assertAlmostEqual(s, 100.0, places=1)

    def test_downtrend(self):
        candles = make_candles([50000 - i * 50 for i in range(20)])
        s = calc_slope(candles, window=20)
        self.assertAlmostEqual(s, -50.0, places=1)

    def test_flat(self):
        candles = make_candles([50000] * 20)
        s = calc_slope(candles, window=20)
        self.assertAlmostEqual(s, 0.0, places=3)


class TestNormalizedSlope(unittest.TestCase):
    def test_normalized(self):
        # slope=50, mean=50000 → 0.001 (0.1%/bar)
        self.assertAlmostEqual(normalized_slope(50.0, 50000.0), 0.001)

    def test_zero_mean_returns_nan(self):
        self.assertTrue(math.isnan(normalized_slope(50.0, 0)))


class TestPercentile(unittest.TestCase):
    def test_below_all(self):
        self.assertEqual(percentile([10, 20, 30, 40, 50], 5), 0.0)

    def test_above_all(self):
        self.assertEqual(percentile([10, 20, 30], 100), 1.0)

    def test_middle(self):
        # 30 は 5項目中で 真ん中(rank=2 of 4)= 0.5
        p = percentile([10, 20, 30, 40, 50], 30)
        self.assertAlmostEqual(p, 0.5, places=1)


class TestDetectRegime(unittest.TestCase):
    def test_insufficient_data(self):
        candles = make_candles([50000] * 50)
        r = detect_regime(candles, rolling_lookback_bars=720)
        self.assertEqual(r.label, "unknown")

    def test_calm_up(self):
        """純粋な上昇トレンド (ランダムなし) → up系のラベル"""
        # 800本、 確実に上昇
        closes = [50000 + i * 10 for i in range(800)]
        candles = make_candles(closes)
        r = detect_regime(candles, atr_period=14, slope_window=20,
                          rolling_lookback_bars=720)
        self.assertIn(r.label, ["calm_up", "storm_up"])

    def test_storm_down(self):
        """ボラ高 × 下降"""
        random.seed(2)
        closes = []
        price = 50000.0
        # 前半: 緩やか / 後半: 急下落+高ボラ
        for i in range(600):
            price += random.uniform(-20, 20)
            closes.append(price)
        # 後半 高ボラ急下落
        for i in range(220):
            price -= 50 + random.uniform(-100, 50)
            closes.append(price)
        candles = make_candles(closes)
        r = detect_regime(candles, atr_period=14, slope_window=20,
                          rolling_lookback_bars=720)
        # storm_down か少なくとも down trend (calm_down) が出るはず
        self.assertIn(r.label, ["storm_down", "calm_down"])

    def test_thresholds_dynamic(self):
        """価格スケールが変わってもラベル分類が機能 (normalized_slope で吸収)"""
        # 純粋上昇 (5万→50万) で動的閾値が機能するか
        closes_low = [50000 + i * 5 for i in range(800)]
        closes_high = [500000 + i * 50 for i in range(800)]

        r_low = detect_regime(make_candles(closes_low), rolling_lookback_bars=720)
        r_high = detect_regime(make_candles(closes_high), rolling_lookback_bars=720)
        # 両方とも 上昇 → up系のラベル
        self.assertIn(r_low.label, ["calm_up", "storm_up"])
        self.assertIn(r_high.label, ["calm_up", "storm_up"])
        # ラベルが一致 (スケールに依存しない)
        self.assertEqual(r_low.label, r_high.label)


class TestRegimeHint(unittest.TestCase):
    def test_all_labels_have_hint(self):
        for label in ["calm_up", "calm_down", "storm_up", "storm_down", "unknown"]:
            hint = regime_to_hint(label)
            self.assertIn("max_lev", hint)
            self.assertIn("stance", hint)

    def test_unknown_max_lev_zero(self):
        self.assertEqual(regime_to_hint("unknown")["max_lev"], 0.0)


if __name__ == "__main__":
    unittest.main()
