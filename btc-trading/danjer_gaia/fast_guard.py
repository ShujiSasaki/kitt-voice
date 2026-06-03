"""
Project danjer-GAIA — Fast Guard (反射神経)
==============================================
Phase 1 Round 7 (Claude) + Round 6 (Gemini) 合意:
- Fast Guard はブレーキのみ独自判断 (アクセル禁止)
- Slow Brain の方針に従って執行、 異常時のみ独自判断 (全閉のみ)
- 衝突マトリクス: Slow Brain判断 × Fast Guard判断 → 最終アクション

R30 (Slow Brain過信) 対策:
Fast Guard はアクセル禁止だが、 以下では Slow Brain許可内でも止める:
  - SL未設置 / 清算距離不足 / 取引所異常 / 日次DD超過 /
    スリッページ異常 / 急変ボラ / データ欠損
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .stance import Stance, StanceLabel


class FastGuardSignal(Enum):
    """Fast Guard が検出する状態"""
    NORMAL = "normal"
    PRICE_SPIKE_DOWN = "price_spike_down"  # 1分で-2%以上
    PRICE_SPIKE_UP = "price_spike_up"      # 1分で+2%以上
    LIQUIDITY_DROP = "liquidity_drop"      # 板厚 < 平常時30%
    API_ERROR = "api_error"                # 取引所API異常
    SL_MISSING = "sl_missing"              # 既存ポジにSLなし
    LIQ_DISTANCE_LOW = "liq_distance_low"  # 清算距離 < 1 ATR
    DAILY_DD_EXCEEDED = "daily_dd_exceeded"  # 日次DD超過 (-5%)
    DATA_GAP = "data_gap"                  # データ欠損 (>1分)


class FinalAction(Enum):
    """発注時の最終アクション"""
    NEW_LONG = "new_long"
    NEW_SHORT = "new_short"
    HOLD = "hold"                    # 既存ポジ保持、 新規なし
    REDUCE = "reduce"                # ポジション縮小
    CLOSE_ALL = "close_all"          # 全閉
    SKIP_THIS_BAR = "skip_this_bar"  # 新規見送り
    EMERGENCY_CLOSE = "emergency_close"  # 緊急全閉


@dataclass
class FastGuardDecision:
    """Fast Guard の最終決定"""
    action: FinalAction
    reason: str
    stance_used: Optional[Stance]
    fast_guard_signal: FastGuardSignal
    overrode_slow_brain: bool  # Slow Brain判断を上書きしたか


# 衝突マトリクス: (Slow Brain stance, Fast Guard signal) → 最終アクション
# Slow Brain許可外のアクセル禁止、 Fast Guard はブレーキのみ独自判断
def resolve_conflict(stance: Optional[Stance],
                     signal: FastGuardSignal,
                     has_existing_pos: bool = False) -> FastGuardDecision:
    """
    Slow Brain スタンス + Fast Guard 信号 → 最終アクション

    原則:
      1. 緊急停止系シグナルは無条件発動 (Fast Guard 緊急権限)
      2. それ以外は Slow Brain stance に従う
      3. Fast Guard は新規エントリー方向を逆転できない (アクセル禁止)
    """
    # 緊急停止系 (R30 — Fast Guardが独自判断で止める)
    EMERGENCY_SIGNALS = {
        FastGuardSignal.SL_MISSING,
        FastGuardSignal.LIQ_DISTANCE_LOW,
        FastGuardSignal.DAILY_DD_EXCEEDED,
        FastGuardSignal.API_ERROR,
        FastGuardSignal.DATA_GAP,
    }
    if signal in EMERGENCY_SIGNALS:
        if has_existing_pos:
            return FastGuardDecision(
                action=FinalAction.EMERGENCY_CLOSE,
                reason=f"Fast Guard emergency: {signal.value}",
                stance_used=stance,
                fast_guard_signal=signal,
                overrode_slow_brain=True,
            )
        else:
            return FastGuardDecision(
                action=FinalAction.SKIP_THIS_BAR,
                reason=f"Fast Guard skip (no pos): {signal.value}",
                stance_used=stance,
                fast_guard_signal=signal,
                overrode_slow_brain=True,
            )

    # 急変系 (PRICE_SPIKE / LIQUIDITY_DROP) は方向によって判断
    if signal == FastGuardSignal.PRICE_SPIKE_DOWN:
        if has_existing_pos and stance and stance.stance == "long_bias":
            return FastGuardDecision(
                action=FinalAction.REDUCE,
                reason="Fast Guard reduce: price spike down with long pos",
                stance_used=stance,
                fast_guard_signal=signal,
                overrode_slow_brain=True,
            )
        return FastGuardDecision(
            action=FinalAction.SKIP_THIS_BAR,
            reason="Fast Guard skip: price spike down",
            stance_used=stance,
            fast_guard_signal=signal,
            overrode_slow_brain=True,
        )

    if signal == FastGuardSignal.PRICE_SPIKE_UP:
        if has_existing_pos and stance and stance.stance == "short_bias":
            return FastGuardDecision(
                action=FinalAction.REDUCE,
                reason="Fast Guard reduce: price spike up with short pos",
                stance_used=stance,
                fast_guard_signal=signal,
                overrode_slow_brain=True,
            )
        return FastGuardDecision(
            action=FinalAction.SKIP_THIS_BAR,
            reason="Fast Guard skip: price spike up",
            stance_used=stance,
            fast_guard_signal=signal,
            overrode_slow_brain=True,
        )

    if signal == FastGuardSignal.LIQUIDITY_DROP:
        return FastGuardDecision(
            action=FinalAction.SKIP_THIS_BAR if not has_existing_pos else FinalAction.HOLD,
            reason="Fast Guard cautious: liquidity drop",
            stance_used=stance,
            fast_guard_signal=signal,
            overrode_slow_brain=True,
        )

    # NORMAL → Slow Brain stance に従う
    if stance is None:
        return FastGuardDecision(
            action=FinalAction.SKIP_THIS_BAR,
            reason="No stance available",
            stance_used=None,
            fast_guard_signal=signal,
            overrode_slow_brain=False,
        )

    if stance.stance == "long_bias":
        action = FinalAction.NEW_LONG
    elif stance.stance == "short_bias":
        action = FinalAction.NEW_SHORT
    elif stance.stance == "wait":
        action = FinalAction.SKIP_THIS_BAR
    else:  # neutral
        action = FinalAction.HOLD if has_existing_pos else FinalAction.SKIP_THIS_BAR

    return FastGuardDecision(
        action=action,
        reason=f"Follow Slow Brain stance: {stance.stance}",
        stance_used=stance,
        fast_guard_signal=signal,
        overrode_slow_brain=False,
    )
