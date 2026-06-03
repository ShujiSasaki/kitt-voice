"""Stance dataclass + parse_stance のユニットテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest
import json
import math

from danjer_gaia.stance import (
    Stance, parse_stance, decay_stance, STANCE_JSON_SCHEMA,
)


def make_stance(**overrides):
    now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        direction=0.5, confidence=0.7, risk_level=0.3,
        valid_until=now + timedelta(minutes=15),
        max_lev=2.0, sl_atr_mult=1.5,
        tp_policy="trailing", stance="long_bias",
        notes="",
        issued_at=now,
    )
    defaults.update(overrides)
    return Stance(**defaults)


class TestStanceBasics(unittest.TestCase):
    def test_to_dict_and_json(self):
        s = make_stance()
        d = s.to_dict()
        self.assertIn("direction", d)
        self.assertEqual(d["stance"], "long_bias")
        # ISO 文字列にシリアライズされる
        self.assertIsInstance(d["valid_until"], str)
        j = s.to_json()
        loaded = json.loads(j)
        self.assertEqual(loaded["stance"], "long_bias")

    def test_is_expired(self):
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(valid_until=now + timedelta(minutes=15), issued_at=now)
        # 14分後は期限内
        self.assertFalse(s.is_expired(now + timedelta(minutes=14)))
        # 16分後は期限切れ
        self.assertTrue(s.is_expired(now + timedelta(minutes=16)))

    def test_remaining_seconds(self):
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(valid_until=now + timedelta(minutes=15), issued_at=now)
        rem = s.remaining_seconds(now)
        self.assertAlmostEqual(rem, 900.0, places=0)
        rem2 = s.remaining_seconds(now + timedelta(minutes=20))
        self.assertLess(rem2, 0)


class TestParseStance(unittest.TestCase):
    def test_valid_full(self):
        raw = json.dumps({
            "direction": 0.7, "confidence": 0.8, "risk_level": 0.2,
            "valid_until": "2026-06-03T12:15:00+00:00",
            "max_lev": 2.5, "sl_atr_mult": 1.5,
            "tp_policy": "trailing", "stance": "long_bias",
            "notes": "BTC上昇継続シナリオ"
        })
        s = parse_stance(raw)
        self.assertEqual(s.stance, "long_bias")
        self.assertAlmostEqual(s.direction, 0.7)
        self.assertEqual(s.notes, "BTC上昇継続シナリオ")

    def test_missing_required(self):
        raw = json.dumps({"direction": 0.5})  # 他全部欠落
        with self.assertRaises(ValueError):
            parse_stance(raw)

    def test_out_of_range(self):
        raw = json.dumps({
            "direction": 1.5,  # > 1.0
            "confidence": 0.5, "risk_level": 0.3,
            "max_lev": 2.0, "sl_atr_mult": 1.5,
            "tp_policy": "trailing", "stance": "long_bias",
        })
        with self.assertRaises(ValueError):
            parse_stance(raw)

    def test_invalid_tp_policy(self):
        raw = json.dumps({
            "direction": 0.5, "confidence": 0.5, "risk_level": 0.3,
            "max_lev": 2.0, "sl_atr_mult": 1.5,
            "tp_policy": "invalid_policy", "stance": "long_bias",
        })
        with self.assertRaises(ValueError):
            parse_stance(raw)

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_stance("{not valid json")

    def test_dict_input(self):
        data = {
            "direction": 0.5, "confidence": 0.5, "risk_level": 0.3,
            "max_lev": 2.0, "sl_atr_mult": 1.5,
            "tp_policy": "trailing", "stance": "long_bias",
        }
        s = parse_stance(data)
        self.assertEqual(s.stance, "long_bias")

    def test_default_ttl_when_no_valid_until(self):
        data = {
            "direction": 0.5, "confidence": 0.5, "risk_level": 0.3,
            "max_lev": 2.0, "sl_atr_mult": 1.5,
            "tp_policy": "trailing", "stance": "long_bias",
        }
        s = parse_stance(data, default_ttl_seconds=900)
        rem = (s.valid_until - s.issued_at).total_seconds()
        self.assertAlmostEqual(rem, 900.0, places=0)


class TestDecayStance(unittest.TestCase):
    def test_no_decay_at_zero(self):
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(confidence=0.8, issued_at=now)
        d = decay_stance(s, 0.9, now=now)
        self.assertAlmostEqual(d.confidence, 0.8, places=3)

    def test_decay_one_minute(self):
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(confidence=1.0, issued_at=now)
        d = decay_stance(s, 0.9, now=now + timedelta(minutes=1))
        self.assertAlmostEqual(d.confidence, 0.9, places=3)

    def test_decay_to_neutral(self):
        """confidence が 0.3 未満になると stance が neutral に"""
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(confidence=0.5, stance="long_bias", issued_at=now)
        d = decay_stance(s, 0.5, now=now + timedelta(minutes=2))
        # 0.5 * 0.5^2 = 0.125 < 0.3 → neutral
        self.assertEqual(d.stance, "neutral")

    def test_risk_increases(self):
        now = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        s = make_stance(risk_level=0.3, issued_at=now)
        d = decay_stance(s, 0.9, now=now + timedelta(minutes=2))
        self.assertGreater(d.risk_level, 0.3)


class TestSchema(unittest.TestCase):
    def test_schema_required_fields(self):
        req = STANCE_JSON_SCHEMA["required"]
        self.assertIn("direction", req)
        self.assertIn("confidence", req)
        self.assertIn("risk_level", req)
        self.assertIn("stance", req)

    def test_schema_enums(self):
        props = STANCE_JSON_SCHEMA["properties"]
        self.assertEqual(set(props["tp_policy"]["enum"]),
                         {"fixed", "trailing", "scenario"})
        self.assertEqual(set(props["stance"]["enum"]),
                         {"long_bias", "short_bias", "neutral", "wait"})


if __name__ == "__main__":
    unittest.main()
