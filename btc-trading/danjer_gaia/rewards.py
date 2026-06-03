"""
Project danjer-GAIA — Reward Function (報酬関数)
==================================================
Phase 1 Round 10 合意:
Reward = Trade-EHR_MA30 + noop機会損失ペナルティ + Σガード減算

GPT R5 / Gemini R6 / Claude R7 の収束:
- 主指標 = Trade-EHR (掛け算ではなく加算で学習安定化、 Gemini R6指摘)
- ガードは減算
- 月次/日次の Calmar/PF は報酬関数からは外す (ダッシュボード監視用)
"""
from __future__ import annotations
from typing import Iterable, Optional
from .schemas import Trade, TradingPeriod, GuardConfig, NoopConfig
from .metrics import moving_average_ehr, noop_penalty
from .guards import total_guard_penalty


def episode_reward(period: TradingPeriod,
                   ma_window: int = 30,
                   baseline_slippage: float = 5.0,
                   guard_cfg: Optional[GuardConfig] = None,
                   noop_cfg: Optional[NoopConfig] = None,
                   # noop計算用 (現在の相場状態と Slow Brain出力)
                   noop_context: Optional[dict] = None) -> dict:
    """
    1エピソードの報酬を計算する。

    Reward = MA30_EHR + Σ_noop_penalty + Σ_guard_penalty

    Args:
        period: TradingPeriod
        ma_window: Trade-EHR 移動平均ウィンドウ
        baseline_slippage: スリッページ基準値
        guard_cfg: GuardConfig
        noop_cfg: NoopConfig
        noop_context: dict with keys:
            - current_vol_atr (float)
            - mean_atr_baseline (float)
            - confidence (float)
            - risk_level (float)
            - expected_value (float)
            - subsequent_favorable_move (float)
          省略時は noop penalty を計算しない (0)

    Returns:
        dict with keys: ma30_ehr, noop_pen, guard_pen, total_reward, breakdown
    """
    if guard_cfg is None:
        guard_cfg = GuardConfig()
    if noop_cfg is None:
        noop_cfg = NoopConfig()

    ma30 = moving_average_ehr(period.trades, window=ma_window, guard=guard_cfg)

    if noop_context is not None and period.noop_hours_total > 0:
        np = noop_penalty(
            noop_hours=period.noop_hours_total,
            current_vol_atr=noop_context["current_vol_atr"],
            mean_atr_baseline=noop_context["mean_atr_baseline"],
            confidence=noop_context["confidence"],
            risk_level=noop_context["risk_level"],
            expected_value=noop_context["expected_value"],
            subsequent_favorable_move=noop_context["subsequent_favorable_move"],
            cfg=noop_cfg,
        )
    else:
        np = 0.0

    guard_breakdown = total_guard_penalty(period, baseline_slippage, guard_cfg)
    guard_total = guard_breakdown["total"]

    total = ma30 + np + guard_total

    return {
        "ma30_ehr": ma30,
        "noop_pen": np,
        "guard_pen": guard_total,
        "total_reward": total,
        "breakdown": {
            **guard_breakdown,
            "ma30_ehr_contribution": ma30,
            "noop_contribution": np,
        },
    }
