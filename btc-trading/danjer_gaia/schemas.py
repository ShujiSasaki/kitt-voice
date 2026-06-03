"""
Project danjer-GAIA — Schemas
=============================
Trade-EHR / 報酬関数 / ガードペナルティ で使う dataclass 定義。
3者会議 Round 10 合意テーブル (logs/round_table_v3.md) 準拠。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime


@dataclass
class Trade:
    """1トレードの記録 (エントリー〜エグジット)"""

    trade_id: str
    symbol: str  # "BTCUSDT" 等
    side: Literal["long", "short"]

    entered_at: datetime
    exited_at: datetime
    elapsed_hours: float  # 待機時間込み (前トレード終了からこのトレード終了まで)

    entry_price: float
    exit_price: float

    size: float  # ポジションサイズ (base currency, 例: BTC)
    leverage: float

    # 損益
    gross_profit: float  # 名目損益
    fees: float  # 手数料
    slippage: float  # スリッページ
    net_profit: float  # 純損益 (gross - fees - slippage)

    # 資金
    avg_equity: float  # トレード期間中の平均口座残高 (USD)

    # ガード判定
    had_sl: bool = True  # SL注文を発注済みか
    was_liquidated: bool = False  # 強制ロスカット発生したか
    max_dd_during: float = 0.0  # トレード期間中の最大ドローダウン (絶対値、 fraction)

    # メタ
    slow_brain_decision_id: Optional[str] = None  # この発注の元になった Slow Brain スタンスID
    regime: Optional[str] = None  # "high_vol_up" など
    notes: str = ""


@dataclass
class TradingPeriod:
    """1期間 (日/週/月) のトレード集合"""

    period_start: datetime
    period_end: datetime
    trades: list[Trade] = field(default_factory=list)
    noop_hours_total: float = 0.0  # 期間内に「ノーポジで待機した」総時間


@dataclass
class GuardConfig:
    """ガード減算ペナルティの設定値 (Appendix-A〜E 準拠)"""

    epsilon_equity: float = 100.0  # USD (最小元手)
    epsilon_hours: float = 1.0  # h (最小経過時間)

    dd_limit: float = 0.05  # 5% (これを超えると二乗ペナルティ)
    max_dd_penalty_coef: float = 1.0  # 二乗係数

    liquidation_penalty_const: float = 100.0  # 強制ロスカット1回 = -100

    no_stop_penalty_const: float = 20.0  # SLなし注文1回 = -20

    overtrade_count_limit: int = 50  # 1期間内のトレード数上限
    overtrade_penalty_coef: float = 0.5

    slippage_penalty_coef: float = 10.0  # スリッページ過剰時の係数

    overleverage_threshold: float = 5.0  # 5xを超えるとペナルティ
    overleverage_penalty_coef: float = 2.0


@dataclass
class NoopConfig:
    """noop機会損失ペナルティ設定 (R28対策、 強制エントリーbug防止)"""

    base_penalty_per_hour: float = 0.001  # 静かな相場でも1h待機で-0.1%
    max_penalty_per_hour: float = 0.01  # 上限固定
    vol_multiplier_cap: float = 3.0  # ボラ倍率上限

    # 発動条件 (R28、 GPT R8で確定)
    require_high_confidence: float = 0.75  # 信頼度高
    require_low_risk: float = 0.4  # リスク低
    require_positive_ev: bool = True  # 期待値正
    require_subsequent_move: bool = True  # その後に大きな順行発生
