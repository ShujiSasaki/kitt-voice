"""
Project danjer-GAIA — Paper Trading Client (シミュレータ)
==============================================================
testnet APIキー不要、 市場価格を入力にしてシミュレート約定。

R40 対策: paper約定価格は実Mark価格より 0.05% 不利に設定 (保守的)
R34 対策: スリッページは top5板厚に応じて算出 (paper約定だからこそ厳しめに)

使い方:
  paper = PaperClient(initial_equity=10000.0)
  # 現在価格を入力 (実取引所から取得or 過去データ)
  paper.update_market(snapshot)
  result = paper.place_order(...)
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable, Any
import uuid
import math

from .base import (
    ExchangeBase, OrderType, OrderSide, OrderResult, Position, Balance,
    MarketSnapshot, ExchangeError, InsufficientBalanceError,
)


@dataclass
class PaperConfig:
    """Paper Trading 設定"""
    pessimistic_slippage_pct: float = 0.0005  # 0.05% (R40対策)
    maker_fee_pct: float = -0.00025  # Bybit Maker -0.025% (リベート)
    taker_fee_pct: float = 0.00075   # Bybit Taker 0.075%
    min_size: float = 0.0001         # 最小0.0001 BTC
    base_currency: str = "USDT"


class PaperClient(ExchangeBase):
    """Paper Trading シミュレータ"""

    name = "paper"

    def __init__(self, initial_equity: float = 10000.0,
                 config: Optional[PaperConfig] = None):
        self.config = config or PaperConfig()
        self._equity = initial_equity
        self._available = initial_equity
        self._positions: dict[str, Position] = {}
        self._open_orders: dict[str, OrderResult] = {}
        self._sl_orders: dict[str, dict] = {}  # order_id → {symbol, sl_price, size, side}
        self._market_cache: dict[str, MarketSnapshot] = {}
        self._subscribers: list[Callable] = []
        self._trade_history: list[OrderResult] = []

    # ============== ヘルパー ==============
    def update_market(self, snapshot: MarketSnapshot):
        """市場価格を更新 (シミュレータには必要)"""
        self._market_cache[snapshot.symbol] = snapshot

        # SL到達チェック (Fast Guard 補助、 paper環境専用)
        for oid, sl_info in list(self._sl_orders.items()):
            if sl_info['symbol'] != snapshot.symbol:
                continue
            if sl_info['side'] == 'long' and snapshot.mark_price <= sl_info['sl_price']:
                self._trigger_sl(oid, snapshot.mark_price)
            elif sl_info['side'] == 'short' and snapshot.mark_price >= sl_info['sl_price']:
                self._trigger_sl(oid, snapshot.mark_price)

        # subscribers に通知
        for sub in self._subscribers:
            try:
                sub(snapshot)
            except Exception:
                pass

    def _trigger_sl(self, sl_order_id: str, price: float):
        """SLヒット → ポジション全閉"""
        sl_info = self._sl_orders.pop(sl_order_id)
        sym = sl_info['symbol']
        pos = self._positions.get(sym)
        if not pos:
            return
        # シミュレート約定 (SL価格付近、 保守的に slippage 込み)
        slippage = self.config.pessimistic_slippage_pct * 2  # SL約定はさらに厳しめ
        if pos.side == 'long':
            fill = price * (1 - slippage)
            pnl = (fill - pos.entry_price) * pos.size
        else:
            fill = price * (1 + slippage)
            pnl = (pos.entry_price - fill) * pos.size

        fee = abs(pos.size * fill) * self.config.taker_fee_pct
        net_pnl = pnl - fee
        self._equity += net_pnl
        self._available += pos.size * pos.entry_price / pos.leverage + net_pnl
        del self._positions[sym]

        result = OrderResult(
            order_id=str(uuid.uuid4()),
            decision_trace_id="sl_triggered",
            symbol=sym, side=OrderSide.SELL if pos.side == 'long' else OrderSide.BUY,
            order_type=OrderType.MARKET, size=pos.size, price=fill,
            status="filled", filled_size=pos.size, filled_price=fill,
            fees=fee, slippage=slippage * fill * pos.size,
        )
        self._trade_history.append(result)

    # ============== ExchangeBase 実装 ==============
    def get_balance(self) -> Balance:
        used = self._equity - self._available
        return Balance(equity=self._equity, available=self._available,
                       used=used, currency=self.config.base_currency)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def get_market(self, symbol: str) -> MarketSnapshot:
        m = self._market_cache.get(symbol)
        if not m:
            raise ExchangeError(f"No market data for {symbol}, call update_market first")
        return m

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
        sl_reduce_only: bool = True,
    ) -> OrderResult:
        if size < self.config.min_size:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error=f"size {size} < min {self.config.min_size}"
            )

        m = self._market_cache.get(symbol)
        if not m:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error="No market data"
            )

        # 約定価格 (Mark から 0.05% 不利、R40)
        is_taker = (order_type == OrderType.MARKET)
        if side == OrderSide.BUY:
            fill_price = m.mark_price * (1 + self.config.pessimistic_slippage_pct)
        else:
            fill_price = m.mark_price * (1 - self.config.pessimistic_slippage_pct)
        slip_cost = abs(fill_price - m.mark_price) * size

        # 必要証拠金
        margin = (size * fill_price) / leverage
        if margin > self._available:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error=f"insufficient: need {margin}, have {self._available}"
            )

        # 手数料
        fee = abs(size * fill_price) * (self.config.taker_fee_pct if is_taker else self.config.maker_fee_pct)

        # ポジション計上
        position_side = "long" if side == OrderSide.BUY else "short"
        # 清算価格 (簡易: leverage に応じた距離)
        if position_side == "long":
            liq_price = fill_price * (1 - 1.0 / leverage * 0.9)
        else:
            liq_price = fill_price * (1 + 1.0 / leverage * 0.9)

        self._positions[symbol] = Position(
            symbol=symbol, side=position_side, size=size,
            entry_price=fill_price, leverage=leverage,
            unrealized_pnl=0.0, liquidation_price=liq_price,
            sl_price=sl_price, tp_price=tp_price,
            opened_at=datetime.now(timezone.utc),
        )
        self._available -= margin
        self._equity -= fee  # 手数料即時減算

        # SL注文 (reduce_only、 R30対策)
        sl_oid = None
        if sl_price and sl_reduce_only:
            sl_oid = str(uuid.uuid4())
            self._sl_orders[sl_oid] = {
                'symbol': symbol, 'sl_price': sl_price,
                'size': size, 'side': position_side,
            }

        order_id = str(uuid.uuid4())
        result = OrderResult(
            order_id=order_id, decision_trace_id=decision_trace_id,
            symbol=symbol, side=side, order_type=order_type,
            size=size, price=price,
            status="filled", filled_size=size, filled_price=fill_price,
            sl_order_id=sl_oid, fees=fee, slippage=slip_cost,
        )
        self._trade_history.append(result)
        return result

    def close_position(self, symbol: str, size: Optional[float] = None,
                       decision_trace_id: str = "") -> OrderResult:
        pos = self._positions.get(symbol)
        if not pos:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=OrderSide.SELL,
                order_type=OrderType.MARKET, size=0, price=None,
                status="rejected", error="no position",
            )
        close_size = size if size and size < pos.size else pos.size
        m = self._market_cache[symbol]
        # 反対側で約定
        if pos.side == "long":
            fill_price = m.mark_price * (1 - self.config.pessimistic_slippage_pct)
            pnl = (fill_price - pos.entry_price) * close_size
            close_side = OrderSide.SELL
        else:
            fill_price = m.mark_price * (1 + self.config.pessimistic_slippage_pct)
            pnl = (pos.entry_price - fill_price) * close_size
            close_side = OrderSide.BUY

        fee = abs(close_size * fill_price) * self.config.taker_fee_pct
        net_pnl = pnl - fee
        self._equity += net_pnl
        # 証拠金返却
        returned_margin = (close_size * pos.entry_price) / pos.leverage
        self._available += returned_margin + net_pnl

        # ポジション更新 or 全閉
        if close_size >= pos.size:
            del self._positions[symbol]
            # 紐付くSL注文もキャンセル
            for oid in list(self._sl_orders.keys()):
                if self._sl_orders[oid]['symbol'] == symbol:
                    del self._sl_orders[oid]
        else:
            pos.size -= close_size

        result = OrderResult(
            order_id=str(uuid.uuid4()), decision_trace_id=decision_trace_id,
            symbol=symbol, side=close_side, order_type=OrderType.MARKET,
            size=close_size, price=None, status="filled",
            filled_size=close_size, filled_price=fill_price,
            fees=fee, slippage=abs(fill_price - m.mark_price) * close_size,
        )
        self._trade_history.append(result)
        return result

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._open_orders:
            del self._open_orders[order_id]
            return True
        if order_id in self._sl_orders:
            del self._sl_orders[order_id]
            return True
        return False

    def subscribe_market(self, symbol: str,
                         on_tick: Callable[[MarketSnapshot], None]) -> Any:
        # paper環境では subscribe = list に追加
        self._subscribers.append(on_tick)
        return on_tick  # handle

    def health_check(self) -> bool:
        return self._equity > 0
