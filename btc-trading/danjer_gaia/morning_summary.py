"""
Project danjer-GAIA — 朝サマリー雛形
======================================
3者会議 Phase 1 Round 1-8 合意:
Shujiさん起床時に1画面で確認できる項目:
  - 夜間判断履歴 (Slow Brain判断)
  - 現在ポジション
  - Trade-EHR (時給×元手効率)
  - danjer類似局面 (Phase 1.2 以降)
  - 現在レジーム
  - リスク警告
  - 今日の承認待ち事項 (L2 通知)

出力: JSON + Markdown両対応 (Shujiさんが iPhone Safari/Slack で見やすい)
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
from .schemas import Trade, TradingPeriod
from .metrics import moving_average_ehr, period_summary
from .stance import Stance
from .regime import RegimeResult, regime_to_hint


@dataclass
class OvernightDecision:
    """夜間の Slow Brain 判断 1件"""
    timestamp: datetime
    stance_label: str
    direction: float
    confidence: float
    risk_level: float
    action_taken: str  # "long_opened" / "short_opened" / "hold" / "closed_by_sl" 等
    pnl: float = 0.0


@dataclass
class CurrentPosition:
    """現在保有ポジション"""
    symbol: str
    side: Literal["long", "short"]
    size: float
    entry_price: float
    current_price: float
    leverage: float
    unrealized_pnl: float
    sl_price: float
    tp_price: Optional[float]
    opened_at: datetime


@dataclass
class PendingApproval:
    """L2 (Shujiさん承認待ち) 事項"""
    timestamp: datetime
    proposed_action: str
    reason: str
    suggested_size: float
    suggested_leverage: float
    expected_value: float
    risk_assessment: str


@dataclass
class RiskAlert:
    """L1/L3/L4 のリスク警告"""
    timestamp: datetime
    level: Literal["L1", "L3", "L4"]
    message: str


@dataclass
class MorningSummary:
    """1画面で Shujiさんが見るサマリー"""
    generated_at: datetime
    period_start: datetime
    period_end: datetime

    # トレード成果
    overnight_pnl: float
    overnight_trades: int
    overnight_ehr_ma30: float
    cumulative_dd: float

    # 判断履歴
    decisions: list[OvernightDecision]

    # 現在ポジション
    positions: list[CurrentPosition]

    # 相場状況
    current_regime: Optional[str]  # "calm_up" 等
    regime_suggested_action: Optional[str]

    # 危険・承認
    risk_alerts: list[RiskAlert]
    pending_approvals: list[PendingApproval]

    # 全体ステータス
    system_status: Literal["healthy", "warning", "halted"]
    notes: str = ""


def make_summary(
    period: TradingPeriod,
    decisions: list[OvernightDecision],
    positions: list[CurrentPosition],
    regime: Optional[RegimeResult],
    risk_alerts: list[RiskAlert],
    pending_approvals: list[PendingApproval],
    system_status: Literal["healthy", "warning", "halted"] = "healthy",
    notes: str = "",
    cumulative_dd: float = 0.0,
    now: Optional[datetime] = None,
) -> MorningSummary:
    """サマリー生成"""
    n = now or datetime.now(timezone.utc)
    psum = period_summary(period)

    return MorningSummary(
        generated_at=n,
        period_start=period.period_start,
        period_end=period.period_end,
        overnight_pnl=psum["total_net_profit"],
        overnight_trades=psum["total_trades"],
        overnight_ehr_ma30=psum["ma30_ehr"],
        cumulative_dd=cumulative_dd,
        decisions=decisions,
        positions=positions,
        current_regime=regime.label if regime else None,
        regime_suggested_action=(
            regime_to_hint(regime.label)["stance"] if regime else None
        ),
        risk_alerts=risk_alerts,
        pending_approvals=pending_approvals,
        system_status=system_status,
        notes=notes,
    )


def to_markdown(summary: MorningSummary) -> str:
    """
    Markdown形式で出力 (iPhone Safari / Slack 等で見やすい)
    """
    lines = []
    status_emoji = {
        "healthy": "✅ HEALTHY",
        "warning": "⚠️  WARNING",
        "halted":  "🛑 HALTED",
    }[summary.system_status]
    lines.append(f"# 🌅 danjer-GAIA 朝サマリー")
    lines.append(f"_生成: {summary.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append(f"_期間: {summary.period_start.strftime('%H:%M')} 〜 {summary.period_end.strftime('%H:%M')}_")
    lines.append("")
    lines.append(f"## システム状態: {status_emoji}")
    lines.append("")

    # トレード成果
    lines.append("## 💰 夜間トレード成果")
    lines.append(f"- PnL: **${summary.overnight_pnl:+.2f}**")
    lines.append(f"- 取引数: {summary.overnight_trades}件")
    lines.append(f"- Trade-EHR (MA30): {summary.overnight_ehr_ma30:.6f}")
    lines.append(f"- 累計DD: {summary.cumulative_dd:.2%}")
    lines.append("")

    # 相場
    lines.append("## 📊 現在の相場")
    if summary.current_regime:
        lines.append(f"- レジーム: **{summary.current_regime}**")
        lines.append(f"- 推奨: {summary.regime_suggested_action}")
    else:
        lines.append("- レジーム: 不明 (データ不足)")
    lines.append("")

    # 現在ポジション
    if summary.positions:
        lines.append("## 📈 現在ポジション")
        for p in summary.positions:
            side_emoji = "🔼" if p.side == "long" else "🔽"
            lines.append(f"- {side_emoji} {p.symbol} {p.side} {p.size} @ ${p.entry_price:.2f} "
                         f"(現在 ${p.current_price:.2f}, レバ {p.leverage}x)")
            lines.append(f"  - PnL未実現: **${p.unrealized_pnl:+.2f}**")
            lines.append(f"  - SL: ${p.sl_price:.2f} / TP: {('$' + str(p.tp_price)) if p.tp_price else 'trailing'}")
    else:
        lines.append("## 📈 現在ポジション: なし")
    lines.append("")

    # リスク警告
    if summary.risk_alerts:
        lines.append("## 🚨 リスク警告")
        for r in summary.risk_alerts:
            emoji = {"L1": "🟡", "L3": "🔴", "L4": "🔥"}[r.level]
            lines.append(f"- {emoji} [{r.level}] {r.message}")
    else:
        lines.append("## 🚨 リスク警告: なし")
    lines.append("")

    # 承認待ち
    if summary.pending_approvals:
        lines.append("## ⏳ Shujiさん承認待ち (L2)")
        for a in summary.pending_approvals:
            lines.append(f"- **{a.proposed_action}**")
            lines.append(f"  - 理由: {a.reason}")
            lines.append(f"  - サイズ: {a.suggested_size} / レバ: {a.suggested_leverage}x")
            lines.append(f"  - 期待値: ${a.expected_value:+.2f}")
            lines.append(f"  - リスク: {a.risk_assessment}")
    else:
        lines.append("## ⏳ Shujiさん承認待ち: なし")
    lines.append("")

    # 判断履歴
    if summary.decisions:
        lines.append(f"## 🧠 Slow Brain 判断履歴 (直近{min(5, len(summary.decisions))}件)")
        for d in summary.decisions[-5:]:
            lines.append(f"- {d.timestamp.strftime('%H:%M')} | {d.stance_label} "
                         f"(dir={d.direction:+.2f}, conf={d.confidence:.2f}, risk={d.risk_level:.2f}) "
                         f"→ {d.action_taken} (PnL: ${d.pnl:+.2f})")
    lines.append("")

    if summary.notes:
        lines.append(f"## 📝 備考\n{summary.notes}\n")

    return "\n".join(lines)


def to_dict(summary: MorningSummary) -> dict:
    """JSON serializable な dict に変換"""
    def conv(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, '__dataclass_fields__'):
            return {k: conv(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [conv(x) for x in obj]
        if isinstance(obj, dict):
            return {k: conv(v) for k, v in obj.items()}
        return obj
    return conv(summary)
