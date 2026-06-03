"""
Project danjer-GAIA — Slack Daily Approval
===============================================
3者会議 Phase 2 v2 Round 22 (Gemini指摘):
- 旧 (v1) : 1トレード毎承認 → Shujiさん精神崩壊リスク (R41)
- 新 (v2) : デイリー承認制 (朝7:00 JSTにまとめてSlack DM、 3択)

選択肢:
  ✅ 全部GO       (approve_all)
  🎯 上位3件のみGO (approve_top3 — Trade-EHR期待値順)
  ❌ 全部却下     (reject_all)

L0自律トレードは別経路 (デイリー承認の外)、 L2のみここで承認待ち。
緊急 (L3/L4) はデイリーの外で即時通知。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
from enum import Enum
import json
import os


ApprovalChoice = Literal["approve_all", "approve_top3", "reject_all"]


@dataclass
class ApprovalCandidate:
    """1件の承認候補"""
    proposal_id: str             # 短いID (例: 'a01', 'a02')
    side: Literal["long", "short"]
    size_btc: float
    leverage: float
    entry_price: float
    sl_price: float
    tp_price: Optional[float]
    max_loss_usd: float          # SL ヒット時の最大損失 (表示用)
    max_loss_pct_of_equity: float
    expected_ehr: float          # Trade-EHR 期待値 (MA30加算後)
    expected_value_usd: float    # 期待利益 (USD)
    confidence: float            # Slow Brain confidence
    risk_level: float            # Slow Brain risk
    regime: str                  # "calm_up" 等
    similar_danjer_count: int    # 類似 danjer ポスト数
    similar_pf: Optional[float]  # 類似ポストの過去PF
    reasoning: str               # 100文字以内 短い理由


@dataclass
class DailyApprovalRequest:
    """朝のデイリー承認 1セット"""
    request_id: str
    generated_at: datetime
    valid_until: datetime        # この時刻までに承認 (例: 朝9:00)
    candidates: list[ApprovalCandidate]
    current_equity: float
    cumulative_dd_pct: float


@dataclass
class ApprovalResponse:
    """Shujiさんの応答"""
    request_id: str
    choice: ApprovalChoice
    responded_at: datetime
    approved_proposal_ids: list[str]  # 承認された proposal_id


def build_slack_message(req: DailyApprovalRequest) -> dict:
    """
    Slack Block Kit メッセージ構築

    Returns: Slack API送信用 dict ({blocks: [...]})

    UI仕様 (Gemini指摘反映):
    - 損失上限は 赤字 で表示
    - 承認/却下 ボタンを離す
    - 各候補に Trade-EHR期待値+損失上限+類似PF を併記
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🌅 danjer-GAIA 本日の発注候補"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Equity*: ${req.current_equity:.2f}"},
                {"type": "mrkdwn", "text": f"*累計DD*: {req.cumulative_dd_pct:.2%}"},
                {"type": "mrkdwn", "text": f"*候補数*: {len(req.candidates)}"},
                {"type": "mrkdwn", "text": f"*承認期限*: {req.valid_until.strftime('%H:%M JST')}"},
            ],
        },
        {"type": "divider"},
    ]

    # 各候補 ブロック
    for c in req.candidates:
        side_emoji = "🔼" if c.side == "long" else "🔽"
        max_loss_str = f":red_circle: 最大損失 *${c.max_loss_usd:.2f}* ({c.max_loss_pct_of_equity:.2%} of Equity)"
        ehr_str = f"期待 EHR *{c.expected_ehr:+.6f}* / 期待利益 *${c.expected_value_usd:+.2f}*"
        similar_str = ""
        if c.similar_pf is not None:
            similar_str = f" / danjer類似 {c.similar_danjer_count}件 PF *{c.similar_pf:.2f}*"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*[{c.proposal_id}] {side_emoji} {c.side.upper()} {c.size_btc} BTC @ ${c.entry_price:.0f}*\n"
                    f"レバ {c.leverage}x / SL ${c.sl_price:.0f} / TP {('$' + format(c.tp_price, '.0f')) if c.tp_price else 'trail'}\n"
                    f"{max_loss_str}\n"
                    f"{ehr_str}{similar_str}\n"
                    f"レジーム *{c.regime}* / 確信度 {c.confidence:.2f} / 危険度 {c.risk_level:.2f}\n"
                    f"_{c.reasoning}_"
                ),
            },
        })

    blocks.append({"type": "divider"})

    # 3択ボタン (位置を離す = ✅ と ❌ を縦に配置)
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ 全部GO"},
                "value": f"approve_all|{req.request_id}",
                "action_id": "approve_all",
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "🎯 上位3件のみGO"},
                "value": f"approve_top3|{req.request_id}",
                "action_id": "approve_top3",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "❌ 全部却下"},
                "value": f"reject_all|{req.request_id}",
                "action_id": "reject_all",
                "style": "danger",
            },
        ],
    })

    return {"blocks": blocks}


def resolve_approval(req: DailyApprovalRequest,
                     choice: ApprovalChoice) -> ApprovalResponse:
    """
    Shujiさんの選択 → 承認された proposal_id リストへ変換

    approve_top3: expected_ehr 降順で上位3件
    """
    now = datetime.now(timezone.utc)
    if choice == "approve_all":
        approved = [c.proposal_id for c in req.candidates]
    elif choice == "approve_top3":
        sorted_c = sorted(req.candidates, key=lambda x: -x.expected_ehr)
        approved = [c.proposal_id for c in sorted_c[:3]]
    elif choice == "reject_all":
        approved = []
    else:
        raise ValueError(f"unknown choice: {choice}")
    return ApprovalResponse(
        request_id=req.request_id,
        choice=choice,
        responded_at=now,
        approved_proposal_ids=approved,
    )


def is_request_expired(req: DailyApprovalRequest, now: Optional[datetime] = None) -> bool:
    n = now or datetime.now(timezone.utc)
    return n > req.valid_until


# Slack API送信 (Webhook方式)
def send_to_slack(message: dict, webhook_url: str) -> bool:
    """Slack Webhook URL に POST送信"""
    import urllib.request
    import urllib.error
    data = json.dumps(message).encode('utf-8')
    req = urllib.request.Request(
        webhook_url, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False
