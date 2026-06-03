"""
Project danjer-GAIA — Trade-EHR Metrics
=========================================
3者会議 Phase 1 合意:
- Trade-EHR = NetProfit / (AvgEquity × ElapsedHours)
- 分母ガード: max(AvgEquity, ε_equity) × max(ElapsedHours, ε_hours) (Appendix-A)
- 集計: MA30 (直近30トレードの移動平均)
- 待機時間込み: ElapsedHours = 前トレード終了〜今回トレード終了まで全経過時間
"""
from __future__ import annotations
import math
from typing import Iterable
from .schemas import Trade, TradingPeriod, GuardConfig, NoopConfig


def trade_ehr(trade: Trade, guard: GuardConfig | None = None) -> float:
    """
    1トレードの Trade-EHR を計算する。

    Trade-EHR = NetProfit / (max(AvgEquity, ε) × max(ElapsedHours, ε))

    Args:
        trade: Trade dataclass
        guard: 分母ガード設定。 デフォルトは GuardConfig() のデフォルト値

    Returns:
        Trade-EHR (単位: 1/時 × NetProfit/AvgEquity)

    Raises:
        ValueError: net_profit が NaN/Inf の場合
    """
    if guard is None:
        guard = GuardConfig()

    if not math.isfinite(trade.net_profit):
        raise ValueError(f"NetProfit is not finite: {trade.net_profit}")

    avg_equity_safe = max(trade.avg_equity, guard.epsilon_equity)
    elapsed_safe = max(trade.elapsed_hours, guard.epsilon_hours)

    return trade.net_profit / (avg_equity_safe * elapsed_safe)


def moving_average_ehr(trades: Iterable[Trade], window: int = 30,
                       guard: GuardConfig | None = None) -> float:
    """
    直近 window トレードの Trade-EHR 移動平均。

    Args:
        trades: Trade のイテラブル (時系列順、 古い→新しい)
        window: 移動平均ウィンドウ (デフォルト30)
        guard: GuardConfig

    Returns:
        移動平均 (トレード数が window 未満なら、 取得分の単純平均)
    """
    trade_list = list(trades)
    if not trade_list:
        return 0.0
    use = trade_list[-window:]
    return sum(trade_ehr(t, guard) for t in use) / len(use)


def noop_penalty(noop_hours: float, current_vol_atr: float,
                 mean_atr_baseline: float,
                 confidence: float, risk_level: float,
                 expected_value: float,
                 subsequent_favorable_move: float,
                 cfg: NoopConfig | None = None) -> float:
    """
    noop機会損失ペナルティ (R28対策: 強制エントリーbug防止条件付き)

    Args:
        noop_hours: 待機時間 (h)
        current_vol_atr: 現在のATR
        mean_atr_baseline: ATR ベースライン (例: 過去30日平均)
        confidence: Slow Brain 確信度 (0-1)
        risk_level: Slow Brain 危険度 (0-1)
        expected_value: 期待損益 (USD or % of equity)
        subsequent_favorable_move: 実際に発生した順行幅 (確認用、 過去評価時)
        cfg: NoopConfig

    Returns:
        ペナルティ値 (常に <= 0)
    """
    if cfg is None:
        cfg = NoopConfig()

    # 発動条件チェック (4条件全て満たさない場合は 0)
    if confidence < cfg.require_high_confidence:
        return 0.0
    if risk_level > cfg.require_low_risk:
        return 0.0
    if cfg.require_positive_ev and expected_value <= 0:
        return 0.0
    if cfg.require_subsequent_move and subsequent_favorable_move <= 0:
        return 0.0

    # ボラ倍率 (上限付き)
    vol_multiplier = min(
        current_vol_atr / max(mean_atr_baseline, 1e-9),
        cfg.vol_multiplier_cap,
    )

    # ペナルティ (上限固定)
    per_hour = min(
        cfg.base_penalty_per_hour * vol_multiplier,
        cfg.max_penalty_per_hour,
    )
    return -1.0 * noop_hours * per_hour


def period_summary(period: TradingPeriod,
                   guard: GuardConfig | None = None) -> dict:
    """
    1期間のサマリー (ダッシュボード表示用)

    Returns:
        dict with keys: total_trades, total_net_profit, avg_ehr,
                       ma30_ehr, total_noop_hours, max_dd, num_liquidations
    """
    if guard is None:
        guard = GuardConfig()

    trades = period.trades
    if not trades:
        return {
            "total_trades": 0,
            "total_net_profit": 0.0,
            "avg_ehr": 0.0,
            "ma30_ehr": 0.0,
            "total_noop_hours": period.noop_hours_total,
            "max_dd": 0.0,
            "num_liquidations": 0,
        }

    ehr_list = [trade_ehr(t, guard) for t in trades]

    return {
        "total_trades": len(trades),
        "total_net_profit": sum(t.net_profit for t in trades),
        "avg_ehr": sum(ehr_list) / len(ehr_list),
        "ma30_ehr": moving_average_ehr(trades, window=30, guard=guard),
        "total_noop_hours": period.noop_hours_total,
        "max_dd": max((t.max_dd_during for t in trades), default=0.0),
        "num_liquidations": sum(1 for t in trades if t.was_liquidated),
    }
