"""
Project danjer-GAIA — Exchange Base Class
==============================================
全取引所クライアントの抽象基底。
Bybit / Hyperliquid / paper (シミュレータ) の共通インターフェース。

3者会議 Phase 2 v2 仕様:
- reduce_only stop 必須 (R30対策)
- Mark Price 個別管理 (R37 Liquidation Cascade対策)
- WebSocket subscribe (Fast Guard用)
- decision_trace_id 全注文付与 (R14)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any
from datetime import datetime, timezone


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class OrderResult:
    """注文発注結果"""
    order_id: str
    decision_trace_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float]
    status: str  # "filled" / "open" / "rejected" / "cancelled"
    filled_size: float = 0.0
    filled_price: float = 0.0
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    fees: float = 0.0
    slippage: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


@dataclass
class Position:
    """現在保有ポジション"""
    symbol: str
    side: str  # "long" / "short"
    size: float  # 正値
    entry_price: float
    leverage: float
    unrealized_pnl: float
    liquidation_price: float
    sl_price: Optional[float]
    tp_price: Optional[float]
    opened_at: datetime


@dataclass
class Balance:
    """口座残高"""
    equity: float            # 純資産 (USD)
    available: float         # 利用可能証拠金
    used: float              # 使用中証拠金
    currency: str = "USDT"


@dataclass
class MarketSnapshot:
    """市場スナップショット (Fast Guard, Risk Engine用)"""
    symbol: str
    last_price: float
    mark_price: float        # 取引所固有 Mark (R37対策で個別管理)
    bid_top5_depth: float
    ask_top5_depth: float
    funding_rate: float
    open_interest: float
    spread: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExchangeError(Exception):
    """取引所API一般エラー"""
    pass


class APIRateLimitError(ExchangeError):
    """レート制限超過"""
    pass


class InsufficientBalanceError(ExchangeError):
    """残高不足"""
    pass


# ============================================================
# Exchange 抽象基底
# ============================================================
class ExchangeBase(ABC):
    """全取引所クライアントの共通インターフェース"""

    name: str  # "bybit" / "hyperliquid" / "paper"

    @abstractmethod
    def get_balance(self) -> Balance:
        """現在の口座残高"""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """指定銘柄の現在ポジション (なければNone)"""
        ...

    @abstractmethod
    def get_market(self, symbol: str) -> MarketSnapshot:
        """市場スナップショット (last/mark/depth/FR等)"""
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        size: float,
        order_type: OrderType,
        leverage: float,
        decision_trace_id: str,
        price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        sl_reduce_only: bool = True,  # R30対策デフォルト True
    ) -> OrderResult:
        """新規注文 (SL同時発注、 reduce_only stop デフォルト)"""
        ...

    @abstractmethod
    def close_position(
        self,
        symbol: str,
        size: Optional[float] = None,
        decision_trace_id: str = "",
    ) -> OrderResult:
        """ポジション全閉 or 部分閉 (size=None で全閉)"""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """注文キャンセル"""
        ...

    @abstractmethod
    def subscribe_market(self, symbol: str,
                         on_tick: Callable[[MarketSnapshot], None]) -> Any:
        """WebSocket subscribe (Fast Guard用、 戻り値は subscription handle)"""
        ...

    def health_check(self) -> bool:
        """API疎通+残高取得テスト"""
        try:
            b = self.get_balance()
            return b.equity > 0
        except Exception:
            return False
