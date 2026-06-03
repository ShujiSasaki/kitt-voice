"""TTL Manager のユニットテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

from danjer_gaia.stance import Stance
from danjer_gaia.ttl_manager import TTLManager, TTLConfig, TTLAction, TTLState


def make_stance(now=None, ttl_min=15, **overrides):
    n = now or datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        direction=0.5, confidence=0.8, risk_level=0.3,
        valid_until=n + timedelta(minutes=ttl_min),
        max_lev=2.0, sl_atr_mult=1.5,
        tp_policy="trailing", stance="long_bias",
        notes="",
        issued_at=n,
    )
    defaults.update(overrides)
    return Stance(**defaults)


class TestTTLManager(unittest.TestCase):
    def setUp(self):
        self.config = TTLConfig(
            ttl_seconds=900,
            decay_grace_seconds=300,
            halt_after_seconds=300,
            decay_per_minute=0.9,
            max_consecutive_failures=3,
        )
        self.mgr = TTLManager(self.config)
        self.now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)

    def test_initial_state_locks_new_entry(self):
        action, stance = self.mgr.decide_action(self.now)
        self.assertEqual(action, TTLAction.LOCK_NEW_ENTRY)
        self.assertIsNone(stance)

    def test_normal_use_stance(self):
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)
        action, stance = self.mgr.decide_action(self.now + timedelta(minutes=10))
        self.assertEqual(action, TTLAction.USE_STANCE)
        self.assertIsNotNone(stance)

    def test_ttl_expired_grace_period(self):
        """TTL切れ後 grace期間 (5分以内) は USE_DECAYED"""
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)
        # 17分後 (TTL 15min を 2min 超過)
        action, stance = self.mgr.decide_action(self.now + timedelta(minutes=17))
        self.assertEqual(action, TTLAction.USE_DECAYED)
        self.assertIsNotNone(stance)
        # confidence は decay されている
        self.assertLess(stance.confidence, 0.8)

    def test_ttl_grace_exceeded_locks_then_halts(self):
        """TTL切れ後 grace超え → LOCK or HALT"""
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)
        # 25分後 (15min + 5min grace + 5min)
        action, stance = self.mgr.decide_action(self.now + timedelta(minutes=25))
        # grace超えてhalt未満なら LOCK
        # halt以降なら HALT
        # 5min超 (grace+halt) で halt
        # 15(ttl) + 5(grace) + 5(halt) = 25分でちょうど halt境界
        # 26分で確実に halt
        self.assertIn(action, [TTLAction.LOCK_NEW_ENTRY, TTLAction.HALT_AND_CLOSE_ALL])

    def test_consecutive_failures_halt(self):
        """連続3回 parse失敗で halt"""
        self.mgr.on_parse_failure()
        self.mgr.on_parse_failure()
        action1, _ = self.mgr.decide_action(self.now)
        # 2回ではまだ halt しない
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)  # リセット
        self.assertFalse(self.mgr.state.is_halted)

        # 3回連続失敗で halt
        self.mgr.on_parse_failure()
        self.mgr.on_parse_failure()
        self.mgr.on_parse_failure()
        action, stance = self.mgr.decide_action(self.now)
        self.assertEqual(action, TTLAction.HALT_AND_CLOSE_ALL)
        self.assertIsNone(stance)

    def test_received_resets_failures(self):
        self.mgr.on_parse_failure()
        self.mgr.on_parse_failure()
        self.assertEqual(self.mgr.state.consecutive_failures, 2)
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)
        self.assertEqual(self.mgr.state.consecutive_failures, 0)

    def test_halt_persists_until_reset(self):
        for _ in range(3):
            self.mgr.on_parse_failure()
        self.assertTrue(self.mgr.state.is_halted)
        # スタンス受信で halt 解除
        s = make_stance(now=self.now)
        self.mgr.on_stance_received(s, self.now)
        action, _ = self.mgr.decide_action(self.now)
        self.assertEqual(action, TTLAction.USE_STANCE)


if __name__ == "__main__":
    unittest.main()
