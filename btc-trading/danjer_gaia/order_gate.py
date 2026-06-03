"""
Project danjer-GAIA — Order Gate (注文前検問所)
================================================
3者会議 Phase 1 Round 8 (GPT) 合意の 6ステップ検問:
  1. Trade Intent     — 発注意図の整合性 (stance × side × size)
  2. Risk Check       — Equity残・MaxDD・レバ上限
  3. Exchange Check   — API応答・流動性・価格乖離
  4. Cost Check       — 手数料+スリッページが期待値を食わないか
  5. Similar Pattern  — danjer類似局面の歴史 (PF/Calmar)
  6. Explainability   — 発注前情報のみで説明可能か (R15 偽装防止)

R14対策: 全注文に decision_trace_id を付与
R31対策: 「資料映え優先で実装が薄い」を避ける → 動くテスト+具体的ロジック
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal
from datetime import datetime, timezone
import uuid


class GateResult(Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass
class TradeIntent:
    """Order Gate に入る前の発注意図"""
    side: Literal["long", "short"]
    size: float  # base currency 量 (例: 0.001 BTC)
    leverage: float
    entry_price: float
    sl_price: float
    tp_price: Optional[float]  # None なら trailing
    symbol: str = "BTCUSDT"
    decision_trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class GateConfig:
    """検問所の閾値"""
    max_leverage: float = 10.0
    min_position_pct_of_equity: float = 0.001   # 0.1% 以上
    max_position_pct_of_equity: float = 0.10    # 10% 以下
    max_daily_dd: float = 0.05                  # 日次DD -5% で reject
    max_total_dd: float = 0.15                  # 累計DD -15% で reject

    # Exchange Check
    max_api_latency_ms: float = 500.0
    min_liquidity_depth_pct: float = 0.30       # 平常時の30% 以上
    max_price_deviation_pct: float = 0.005      # ±0.5% (mark vs last)

    # Cost Check
    max_total_cost_vs_ev_ratio: float = 0.3     # コスト/期待利益 < 30%
    sl_distance_min_atr: float = 0.5             # SL距離 >= 0.5 ATR
    sl_distance_max_atr: float = 5.0             # SL距離 <= 5.0 ATR

    # Similar Pattern
    require_similar_pattern: bool = False        # Phase 1.1 では False (DNAなし)
    min_historical_pf: float = 0.9               # PF >= 0.9 が「類似で勝ち越し」基準


@dataclass
class GateContext:
    """検問所への入力コンテキスト"""
    current_equity: float
    daily_pnl_pct: float        # 当日累計 (例: -0.02 = -2%)
    total_dd_pct: float         # 累計DD
    api_latency_ms: float
    bid_depth_top5: float
    bid_depth_baseline: float   # 平常時の bid_depth (比較用)
    ask_depth_top5: float
    ask_depth_baseline: float
    last_price: float
    mark_price: float
    expected_value: float       # 期待利益 (USD or PnL)
    fee_estimate: float
    slippage_estimate: float
    current_atr: float
    similar_pattern_pf: Optional[float] = None  # danjer DNA検索結果
    similar_pattern_count: int = 0
    explanation: str = ""       # 発注前に使った特徴量説明 (R15)


@dataclass
class GateDecision:
    """検問所の判定結果"""
    result: GateResult
    reason: str
    failed_step: Optional[str]  # 失敗ステップ名
    decision_trace_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================
# 6つの検問ステップ
# ============================================================

def step1_trade_intent(intent: TradeIntent, cfg: GateConfig) -> Optional[str]:
    """1. Trade Intent 整合性"""
    if intent.size <= 0:
        return "size must be > 0"
    if intent.leverage <= 0 or intent.leverage > cfg.max_leverage:
        return f"leverage {intent.leverage} out of (0, {cfg.max_leverage}]"
    if intent.side == "long":
        if intent.sl_price >= intent.entry_price:
            return "long: sl_price must be < entry_price"
        if intent.tp_price is not None and intent.tp_price <= intent.entry_price:
            return "long: tp_price must be > entry_price"
    else:  # short
        if intent.sl_price <= intent.entry_price:
            return "short: sl_price must be > entry_price"
        if intent.tp_price is not None and intent.tp_price >= intent.entry_price:
            return "short: tp_price must be < entry_price"
    return None


def step2_risk_check(intent: TradeIntent, ctx: GateContext, cfg: GateConfig) -> Optional[str]:
    """2. Risk Check"""
    notional = intent.size * intent.entry_price
    pos_pct = notional / max(ctx.current_equity, 1.0)
    if pos_pct < cfg.min_position_pct_of_equity:
        return f"position {pos_pct:.4%} below min {cfg.min_position_pct_of_equity:.4%}"
    if pos_pct > cfg.max_position_pct_of_equity:
        return f"position {pos_pct:.4%} above max {cfg.max_position_pct_of_equity:.4%}"
    if ctx.daily_pnl_pct <= -cfg.max_daily_dd:
        return f"daily DD {ctx.daily_pnl_pct:.2%} <= -{cfg.max_daily_dd:.2%}"
    if ctx.total_dd_pct >= cfg.max_total_dd:
        return f"total DD {ctx.total_dd_pct:.2%} >= {cfg.max_total_dd:.2%}"
    return None


def step3_exchange_check(ctx: GateContext, cfg: GateConfig) -> Optional[str]:
    """3. Exchange Check (API応答 / 流動性 / 価格乖離)"""
    if ctx.api_latency_ms > cfg.max_api_latency_ms:
        return f"API latency {ctx.api_latency_ms}ms > {cfg.max_api_latency_ms}ms"
    # 流動性
    bid_ratio = ctx.bid_depth_top5 / max(ctx.bid_depth_baseline, 1.0)
    ask_ratio = ctx.ask_depth_top5 / max(ctx.ask_depth_baseline, 1.0)
    if bid_ratio < cfg.min_liquidity_depth_pct:
        return f"bid liquidity {bid_ratio:.2%} below {cfg.min_liquidity_depth_pct:.2%}"
    if ask_ratio < cfg.min_liquidity_depth_pct:
        return f"ask liquidity {ask_ratio:.2%} below {cfg.min_liquidity_depth_pct:.2%}"
    # 価格乖離
    deviation = abs(ctx.last_price - ctx.mark_price) / max(ctx.mark_price, 1.0)
    if deviation > cfg.max_price_deviation_pct:
        return f"price deviation {deviation:.4%} > {cfg.max_price_deviation_pct:.4%}"
    return None


def step4_cost_check(intent: TradeIntent, ctx: GateContext, cfg: GateConfig) -> Optional[str]:
    """4. Cost Check (手数料+スリッページ vs 期待利益)"""
    total_cost = ctx.fee_estimate + ctx.slippage_estimate
    if ctx.expected_value <= 0:
        return f"expected_value {ctx.expected_value} <= 0"
    cost_ratio = total_cost / ctx.expected_value
    if cost_ratio > cfg.max_total_cost_vs_ev_ratio:
        return f"cost/EV ratio {cost_ratio:.2%} > {cfg.max_total_cost_vs_ev_ratio:.2%}"
    # SL距離チェック (ATR比)
    sl_dist = abs(intent.entry_price - intent.sl_price)
    if ctx.current_atr <= 0:
        return f"ATR invalid: {ctx.current_atr}"
    sl_atr_ratio = sl_dist / ctx.current_atr
    if sl_atr_ratio < cfg.sl_distance_min_atr:
        return f"SL too tight: {sl_atr_ratio:.2f} < {cfg.sl_distance_min_atr} ATR"
    if sl_atr_ratio > cfg.sl_distance_max_atr:
        return f"SL too far: {sl_atr_ratio:.2f} > {cfg.sl_distance_max_atr} ATR"
    return None


def step5_similar_pattern(ctx: GateContext, cfg: GateConfig) -> Optional[str]:
    """5. Similar Pattern Check (danjer DNA類似局面)
    Phase 1.1 では require_similar_pattern=False で skip 可能
    """
    if not cfg.require_similar_pattern:
        return None
    if ctx.similar_pattern_pf is None:
        return "no similar danjer pattern found (DNA required)"
    if ctx.similar_pattern_count < 3:
        return f"too few similar patterns ({ctx.similar_pattern_count} < 3)"
    if ctx.similar_pattern_pf < cfg.min_historical_pf:
        return f"similar pattern PF {ctx.similar_pattern_pf:.2f} < {cfg.min_historical_pf}"
    return None


def step6_explainability(ctx: GateContext) -> Optional[str]:
    """6. Explainability Check (R15 偽装防止)
    発注前に使った特徴量説明が空でないか
    """
    if not ctx.explanation or len(ctx.explanation.strip()) < 20:
        return "explanation too short or empty (R15: must explain pre-trade)"
    return None


# ============================================================
# メイン: 6ステップを順次通す
# ============================================================
def run_order_gate(intent: TradeIntent, ctx: GateContext,
                   cfg: Optional[GateConfig] = None) -> GateDecision:
    """
    Order Gate を実行。 6ステップを順次通し、 失敗すれば即 REJECT。

    Returns: GateDecision
    """
    if cfg is None:
        cfg = GateConfig()

    steps = [
        ("step1_trade_intent",  lambda: step1_trade_intent(intent, cfg)),
        ("step2_risk_check",    lambda: step2_risk_check(intent, ctx, cfg)),
        ("step3_exchange_check",lambda: step3_exchange_check(ctx, cfg)),
        ("step4_cost_check",    lambda: step4_cost_check(intent, ctx, cfg)),
        ("step5_similar_pattern",lambda: step5_similar_pattern(ctx, cfg)),
        ("step6_explainability",lambda: step6_explainability(ctx)),
    ]

    for name, fn in steps:
        err = fn()
        if err is not None:
            return GateDecision(
                result=GateResult.REJECT,
                reason=err,
                failed_step=name,
                decision_trace_id=intent.decision_trace_id,
            )

    return GateDecision(
        result=GateResult.APPROVE,
        reason="all 6 gates passed",
        failed_step=None,
        decision_trace_id=intent.decision_trace_id,
    )
