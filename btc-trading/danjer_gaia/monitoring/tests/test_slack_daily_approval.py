"""Slack Daily Approval のテスト"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import unittest

from danjer_gaia.monitoring.slack_daily_approval import (
    ApprovalCandidate, DailyApprovalRequest, ApprovalResponse,
    build_slack_message, resolve_approval, is_request_expired,
)


def make_candidate(proposal_id="a01", expected_ehr=0.001, **overrides):
    defaults = dict(
        proposal_id=proposal_id, side="long",
        size_btc=0.0001, leverage=2.0, entry_price=60000.0,
        sl_price=58000.0, tp_price=63000.0,
        max_loss_usd=0.20, max_loss_pct_of_equity=0.0025,
        expected_ehr=expected_ehr, expected_value_usd=0.30,
        confidence=0.80, risk_level=0.20, regime="calm_up",
        similar_danjer_count=5, similar_pf=2.1,
        reasoning="BTC上昇トレンド+danjer類似",
    )
    defaults.update(overrides)
    return ApprovalCandidate(**defaults)


def make_request(candidates=None):
    n = datetime(2026, 6, 3, 7, 0, tzinfo=timezone.utc)
    return DailyApprovalRequest(
        request_id="req_001",
        generated_at=n,
        valid_until=n + timedelta(hours=2),
        candidates=candidates or [make_candidate()],
        current_equity=10000.0,
        cumulative_dd_pct=0.01,
    )


class TestBuildSlackMessage(unittest.TestCase):
    def test_message_has_blocks(self):
        req = make_request([make_candidate(), make_candidate(proposal_id="a02")])
        msg = build_slack_message(req)
        self.assertIn("blocks", msg)
        self.assertGreater(len(msg["blocks"]), 5)  # header+section+divider+2candidate+divider+actions

    def test_action_buttons(self):
        req = make_request()
        msg = build_slack_message(req)
        actions = [b for b in msg["blocks"] if b.get("type") == "actions"]
        self.assertEqual(len(actions), 1)
        button_ids = [e.get("action_id") for e in actions[0]["elements"]]
        self.assertIn("approve_all", button_ids)
        self.assertIn("approve_top3", button_ids)
        self.assertIn("reject_all", button_ids)


class TestResolveApproval(unittest.TestCase):
    def test_approve_all(self):
        req = make_request([
            make_candidate("a01", expected_ehr=0.001),
            make_candidate("a02", expected_ehr=0.005),
            make_candidate("a03", expected_ehr=0.002),
        ])
        resp = resolve_approval(req, "approve_all")
        self.assertEqual(set(resp.approved_proposal_ids), {"a01", "a02", "a03"})

    def test_approve_top3(self):
        req = make_request([
            make_candidate(f"a0{i}", expected_ehr=0.001 * i) for i in range(1, 6)
        ])
        resp = resolve_approval(req, "approve_top3")
        # expected_ehr 降順で上位3件 = a05/a04/a03
        self.assertEqual(set(resp.approved_proposal_ids), {"a05", "a04", "a03"})

    def test_reject_all(self):
        req = make_request([make_candidate()])
        resp = resolve_approval(req, "reject_all")
        self.assertEqual(resp.approved_proposal_ids, [])

    def test_invalid_choice(self):
        req = make_request()
        with self.assertRaises(ValueError):
            resolve_approval(req, "invalid")


class TestExpired(unittest.TestCase):
    def test_not_expired(self):
        req = make_request()
        self.assertFalse(is_request_expired(req, now=datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)))

    def test_expired(self):
        req = make_request()
        # req.valid_until = 9:00 → 10:00で確実に超過
        self.assertTrue(is_request_expired(req, now=datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
