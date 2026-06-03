"""
Project danjer-GAIA
====================
3者会議 v3 (logs/round_table_v3.md) 合意に基づく実装。
Day 1-2: 評価基盤 (Trade-EHR + ガード + 報酬関数)
"""
from .schemas import Trade, TradingPeriod, GuardConfig, NoopConfig
from .metrics import trade_ehr, moving_average_ehr, noop_penalty, period_summary
from .guards import (
    liquidation_penalty, max_dd_penalty, no_stop_penalty,
    slippage_penalty, overleverage_penalty, overtrade_penalty,
    total_guard_penalty,
)
from .rewards import episode_reward
from .regime import (
    OHLCV, RegimeResult, calc_atr, calc_slope, normalized_slope,
    detect_regime, regime_to_hint,
)
from .stance import (
    Stance, STANCE_JSON_SCHEMA, parse_stance, decay_stance,
)
from .ttl_manager import (
    TTLManager, TTLConfig, TTLAction, TTLState,
)
from .fast_guard import (
    FastGuardSignal, FinalAction, FastGuardDecision, resolve_conflict,
)

__version__ = "0.3.0"
__all__ = [
    "Trade", "TradingPeriod", "GuardConfig", "NoopConfig",
    "trade_ehr", "moving_average_ehr", "noop_penalty", "period_summary",
    "liquidation_penalty", "max_dd_penalty", "no_stop_penalty",
    "slippage_penalty", "overleverage_penalty", "overtrade_penalty",
    "total_guard_penalty",
    "episode_reward",
    "OHLCV", "RegimeResult", "calc_atr", "calc_slope", "normalized_slope",
    "detect_regime", "regime_to_hint",
]
