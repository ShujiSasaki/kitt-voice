"""Fast Guard 衝突マトリクス のテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

from danjer_gaia.stance import Stance
from danjer_gaia.fast_guard import (
    FastGuardSignal, FinalAction, resolve_conflict,
)


def make_stance(stance_label="long_bias", **overrides):
    now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        direction=0.5, confidence=0.8, risk_level=0.3,
        valid_until=now + timedelta(minutes=15),
        max_lev=2.0, sl_atr_mult=1.5,
        tp_policy="trailing", stance=stance_label,
        notes="",
        issued_at=now,
    )
    defaults.update(overrides)
    return Stance(**defaults)


class TestNormalFollowSlowBrain(unittest.TestCase):
    def test_long_bias_new_long(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.NORMAL, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.NEW_LONG)
        self.assertFalse(r.overrode_slow_brain)

    def test_short_bias_new_short(self):
        s = make_stance(stance_label="short_bias")
        r = resolve_conflict(s, FastGuardSignal.NORMAL, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.NEW_SHORT)

    def test_wait_skips(self):
        s = make_stance(stance_label="wait")
        r = resolve_conflict(s, FastGuardSignal.NORMAL, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)

    def test_neutral_with_pos_holds(self):
        s = make_stance(stance_label="neutral")
        r = resolve_conflict(s, FastGuardSignal.NORMAL, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.HOLD)


class TestEmergencyOverrides(unittest.TestCase):
    """R30: Fast Guard が Slow Brain 許可内でも止める"""

    def test_sl_missing_with_pos_emergency_close(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.SL_MISSING, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.EMERGENCY_CLOSE)
        self.assertTrue(r.overrode_slow_brain)

    def test_sl_missing_no_pos_skips(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.SL_MISSING, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)
        self.assertTrue(r.overrode_slow_brain)

    def test_liq_distance_low(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.LIQ_DISTANCE_LOW, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.EMERGENCY_CLOSE)

    def test_daily_dd_exceeded(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.DAILY_DD_EXCEEDED, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.EMERGENCY_CLOSE)

    def test_api_error(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.API_ERROR, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.EMERGENCY_CLOSE)

    def test_data_gap(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.DATA_GAP, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)


class TestPriceSpikes(unittest.TestCase):
    def test_spike_down_with_long_reduces(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.PRICE_SPIKE_DOWN, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.REDUCE)
        self.assertTrue(r.overrode_slow_brain)

    def test_spike_down_no_pos_skips(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.PRICE_SPIKE_DOWN, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)

    def test_spike_up_with_short_reduces(self):
        s = make_stance(stance_label="short_bias")
        r = resolve_conflict(s, FastGuardSignal.PRICE_SPIKE_UP, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.REDUCE)


class TestLiquidityDrop(unittest.TestCase):
    def test_no_pos_skips(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.LIQUIDITY_DROP, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)

    def test_with_pos_holds(self):
        s = make_stance(stance_label="long_bias")
        r = resolve_conflict(s, FastGuardSignal.LIQUIDITY_DROP, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.HOLD)


class TestNoStance(unittest.TestCase):
    def test_no_stance_no_signal_skips(self):
        r = resolve_conflict(None, FastGuardSignal.NORMAL, has_existing_pos=False)
        self.assertEqual(r.action, FinalAction.SKIP_THIS_BAR)

    def test_no_stance_with_emergency(self):
        """スタンス無くても緊急時は止める"""
        r = resolve_conflict(None, FastGuardSignal.SL_MISSING, has_existing_pos=True)
        self.assertEqual(r.action, FinalAction.EMERGENCY_CLOSE)


if __name__ == "__main__":
    unittest.main()
