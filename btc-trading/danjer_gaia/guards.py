"""
Project danjer-GAIA — Guard Penalties
========================================
報酬関数の減算ペナルティ群 (Phase 1合意):
  - Liquidation (強制ロスカット)
  - MaxDD超過 (二乗ペナルティ)
  - NoStop (SL未設置)
  - Slippage過剰
  - OverLeverage (5x超)
  - Overtrade (取引数上限超え)

3者会議 Round 4 GPT提案 + Round 6 Gemini監査 で「掛け算ではなく加算 (減算)」と確定。
"""
from __future__ import annotations
from typing import Iterable
from .schemas import Trade, TradingPeriod, GuardConfig


def liquidation_penalty(trades: Iterable[Trade], cfg: GuardConfig | None = None) -> float:
    """
    強制ロスカット 1回 = -100 ペナルティ (Appendix-A)
    """
    if cfg is None:
        cfg = GuardConfig()
    n = sum(1 for t in trades if t.was_liquidated)
    return -1.0 * n * cfg.liquidation_penalty_const


def max_dd_penalty(trades: Iterable[Trade], cfg: GuardConfig | None = None) -> float:
    """
    DD超過の 二乗ペナルティ (Appendix-A)
    penalty = -sum( max(0, dd - dd_limit) ** 2 ) per trade
    """
    if cfg is None:
        cfg = GuardConfig()
    total = 0.0
    for t in trades:
        excess = max(0.0, t.max_dd_during - cfg.dd_limit)
        total += cfg.max_dd_penalty_coef * (excess ** 2)
    return -1.0 * total


def no_stop_penalty(trades: Iterable[Trade], cfg: GuardConfig | None = None) -> float:
    """
    SL未設置トレード 1件 = -20
    """
    if cfg is None:
        cfg = GuardConfig()
    n = sum(1 for t in trades if not t.had_sl)
    return -1.0 * n * cfg.no_stop_penalty_const


def slippage_penalty(trades: Iterable[Trade],
                     baseline_slippage: float = 5.0,
                     cfg: GuardConfig | None = None) -> float:
    """
    スリッページが想定値を超えたトレードに減点。
    penalty = -coef × sum( max(0, slippage - baseline) )
    """
    if cfg is None:
        cfg = GuardConfig()
    total = 0.0
    for t in trades:
        excess = max(0.0, t.slippage - baseline_slippage)
        total += excess
    return -1.0 * cfg.slippage_penalty_coef * total


def overleverage_penalty(trades: Iterable[Trade], cfg: GuardConfig | None = None) -> float:
    """
    レバ閾値超え。 penalty = -coef × sum(max(0, lev - threshold))
    """
    if cfg is None:
        cfg = GuardConfig()
    total = 0.0
    for t in trades:
        excess = max(0.0, t.leverage - cfg.overleverage_threshold)
        total += excess
    return -1.0 * cfg.overleverage_penalty_coef * total


def overtrade_penalty(period: TradingPeriod, cfg: GuardConfig | None = None) -> float:
    """
    期間内の取引数が上限を超えた分にペナルティ。
    R28 強制エントリーbug防止策とセット。
    """
    if cfg is None:
        cfg = GuardConfig()
    excess = max(0, len(period.trades) - cfg.overtrade_count_limit)
    return -1.0 * cfg.overtrade_penalty_coef * excess


def total_guard_penalty(period: TradingPeriod,
                        baseline_slippage: float = 5.0,
                        cfg: GuardConfig | None = None) -> dict:
    """
    全ガードペナルティを集計。
    Returns: dict with each penalty + total
    """
    if cfg is None:
        cfg = GuardConfig()
    trades = period.trades
    results = {
        "liquidation": liquidation_penalty(trades, cfg),
        "max_dd": max_dd_penalty(trades, cfg),
        "no_stop": no_stop_penalty(trades, cfg),
        "slippage": slippage_penalty(trades, baseline_slippage, cfg),
        "overleverage": overleverage_penalty(trades, cfg),
        "overtrade": overtrade_penalty(period, cfg),
    }
    results["total"] = sum(results.values())
    return results
