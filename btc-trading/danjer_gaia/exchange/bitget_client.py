"""
Project danjer-GAIA — Bitget Client (副取引所)
=================================================
3者会議 Round 30-38 (戦略Z v8) で副取引所に確定 (Phase 3後半-Phase 4)。

役割:
- Phase 3後半 (Day 100-167): read-only 並走テスト (障害退避準備)
- Phase 4 Cap 1+: 障害退避用待機 (Hyperliquid異常時に自動切替)
- Phase 4 Cap 4-5: 板厚補完 (Hyperliquid Cap 3超で板影響3%以上想定時)

手数料モデル (Round 34 検証済):
- spot: 0.01% / contract maker: 0.02% / contract taker: 0.06%
- BGB保有で最大80% off (BGB価格変動リスクあり、 v8では BGB保有しない方針)

R71対策 (Bitget FSA完全撤退リスク):
- 月次規制監視ジョブで撤退発表検知
- 撤退発表時90日避難計画 (Hyperliquid単独へ復帰)

公式 SDK:
- CCXT経由 (pip install ccxt)
- https://docs.bitget.com/api-doc/contract/intro
- 認証: API Key + Secret Key + Passphrase

mock_mode 対応:
- SDK 未インストール時のオフラインテスト
- Phase 3後半着手まで本接続不要
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Callable, Any
import uuid

from .base import (
    ExchangeBase, OrderType, OrderSide, OrderResult, Position, Balance,
    MarketSnapshot, ExchangeError,
)


# Bitget 手数料モデル (Round 34 検証済)
SPOT_MAKER_FEE_PCT = 0.0001     # 0.01%
SPOT_TAKER_FEE_PCT = 0.0001     # 0.01%
CONTRACT_MAKER_FEE_PCT = 0.0002  # 0.02%
CONTRACT_TAKER_FEE_PCT = 0.0006  # 0.06%


@dataclass
class BitgetConfig:
    """Bitget クライアント設定"""
    api_key: Optional[str] = None       # GCP Secret Manager 経由
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None
    sandbox: bool = False                # testnet モード
    mock_mode: bool = False              # SDK 不要のオフライン動作
    market_type: str = "swap"            # "spot" / "swap" (perp futures)
    min_size: float = 0.0001
    use_bgb_discount: bool = False       # v8では使用しない (R80類リスク)


class BitgetClient(ExchangeBase):
    """
    Bitget 副取引所クライアント (Phase 3後半-Phase 4)。

    使い方:
        # Phase 3後半 mock_mode (Wallet なしテスト)
        client = BitgetClient(BitgetConfig(mock_mode=True))

        # Phase 4 Cap 1 本接続
        from os import environ
        client = BitgetClient(BitgetConfig(
            api_key=environ["BITGET_API_KEY"],
            secret_key=environ["BITGET_SECRET_KEY"],
            passphrase=environ["BITGET_PASSPHRASE"],
            market_type="swap",
        ))
    """

    name = "bitget"

    def __init__(self, config: Optional[BitgetConfig] = None):
        self.config = config or BitgetConfig()
        self._exchange = None
        self._mock_positions: dict[str, Position] = {}
        self._mock_balance = Balance(equity=0, available=0, used=0, currency="USDT")
        self._mock_market_cache: dict[str, MarketSnapshot] = {}

        if not self.config.mock_mode:
            self._initialize_ccxt()

    def _initialize_ccxt(self):
        """CCXT 初期化"""
        try:
            import ccxt  # type: ignore
            self._exchange = ccxt.bitget({
                "apiKey": self.config.api_key,
                "secret": self.config.secret_key,
                "password": self.config.passphrase,  # CCXT は password として渡す
                "options": {"defaultType": self.config.market_type},
                "enableRateLimit": True,
            })
            if self.config.sandbox:
                self._exchange.set_sandbox_mode(True)
        except ImportError as e:
            raise ExchangeError(
                f"ccxt not installed. Run: pip install ccxt. Original: {e}"
            )

    # ==================== mock_mode helper ====================
    def set_mock_market(self, snapshot: MarketSnapshot):
        if not self.config.mock_mode:
            raise ExchangeError("set_mock_market is only available in mock_mode")
        self._mock_market_cache[snapshot.symbol] = snapshot

    def set_mock_balance(self, balance: Balance):
        if not self.config.mock_mode:
            raise ExchangeError("set_mock_balance is only available in mock_mode")
        self._mock_balance = balance

    # ==================== ExchangeBase 実装 ====================
    def get_balance(self) -> Balance:
        if self.config.mock_mode:
            return self._mock_balance
        if not self._exchange:
            raise ExchangeError("SDK not initialized")
        try:
            data = self._exchange.fetch_balance()
            usdt = data.get("USDT", {})
            return Balance(
                equity=float(usdt.get("total", 0)),
                available=float(usdt.get("free", 0)),
                used=float(usdt.get("used", 0)),
                currency="USDT",
            )
        except Exception as e:
            raise ExchangeError(f"get_balance failed: {e}")

    def get_position(self, symbol: str) -> Optional[Position]:
        if self.config.mock_mode:
            return self._mock_positions.get(symbol)
        if not self._exchange:
            raise ExchangeError("SDK not initialized")
        try:
            positions = self._exchange.fetch_positions([symbol])
            for p in positions:
                size = abs(float(p.get("contracts") or 0))
                if size == 0:
                    continue
                return Position(
                    symbol=symbol,
                    side="long" if p.get("side") == "long" else "short",
                    size=size,
                    entry_price=float(p.get("entryPrice", 0)),
                    leverage=float(p.get("leverage", 1)),
                    unrealized_pnl=float(p.get("unrealizedPnl", 0) or 0),
                    liquidation_price=float(p.get("liquidationPrice", 0) or 0),
                    sl_price=None, tp_price=None,
                    opened_at=datetime.now(timezone.utc),
                )
            return None
        except Exception as e:
            raise ExchangeError(f"get_position failed: {e}")

    def get_market(self, symbol: str) -> MarketSnapshot:
        if self.config.mock_mode:
            m = self._mock_market_cache.get(symbol)
            if not m:
                raise ExchangeError(f"No mock market data for {symbol}")
            return m
        if not self._exchange:
            raise ExchangeError("SDK not initialized")
        try:
            ticker = self._exchange.fetch_ticker(symbol)
            book = self._exchange.fetch_order_book(symbol, limit=5)
            bids = book.get("bids", [])[:5]
            asks = book.get("asks", [])[:5]
            bid_depth = sum(b[1] for b in bids)
            ask_depth = sum(a[1] for a in asks)
            return MarketSnapshot(
                symbol=symbol,
                last_price=float(ticker.get("last", 0)),
                mark_price=float(ticker.get("mark") or ticker.get("last") or 0),
                bid_top5_depth=bid_depth,
                ask_top5_depth=ask_depth,
                funding_rate=float(ticker.get("fundingRate") or 0),
                open_interest=float(ticker.get("info", {}).get("openInterest", 0) or 0),
                spread=float(ticker.get("ask", 0)) - float(ticker.get("bid", 0)),
            )
        except Exception as e:
            raise ExchangeError(f"get_market failed: {e}")

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
                error=f"size {size} < min {self.config.min_size}",
            )

        if self.config.mock_mode:
            return self._mock_place_order(
                symbol, side, size, order_type, leverage, decision_trace_id,
                price, sl_price, tp_price, sl_reduce_only,
            )

        if not self._exchange:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error="SDK not initialized",
            )

        try:
            # レバレッジ設定
            self._exchange.set_leverage(int(leverage), symbol)

            order_type_str = "market" if order_type == OrderType.MARKET else "limit"
            side_str = "buy" if side == OrderSide.BUY else "sell"

            params = {}
            if sl_price and sl_reduce_only:
                params["stopLoss"] = {"triggerPrice": sl_price, "reduceOnly": True}
            if tp_price:
                params["takeProfit"] = {"triggerPrice": tp_price, "reduceOnly": True}

            response = self._exchange.create_order(
                symbol, order_type_str, side_str, size,
                price=price, params=params,
            )

            filled_size = float(response.get("filled", 0))
            filled_price = float(response.get("average") or response.get("price") or 0)
            is_taker = (order_type == OrderType.MARKET)
            fee_pct = CONTRACT_TAKER_FEE_PCT if is_taker else CONTRACT_MAKER_FEE_PCT
            fee = abs(filled_size * filled_price) * fee_pct

            return OrderResult(
                order_id=str(response.get("id", "")),
                decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price,
                status="filled" if filled_size > 0 else "open",
                filled_size=filled_size, filled_price=filled_price,
                sl_order_id=None, fees=fee, slippage=0.0,
            )
        except Exception as e:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error=f"place_order failed: {e}",
            )

    def _mock_place_order(
        self, symbol, side, size, order_type, leverage, decision_trace_id,
        price, sl_price, tp_price, sl_reduce_only,
    ) -> OrderResult:
        """mock_mode 発注 (Phase 3後半テスト用)"""
        m = self._mock_market_cache.get(symbol)
        if not m:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=side, order_type=order_type,
                size=size, price=price, status="rejected",
                error="No mock market data",
            )
        is_buy = (side == OrderSide.BUY)
        fill_price = m.mark_price * (1.0005 if is_buy else 0.9995)
        is_taker = (order_type == OrderType.MARKET)
        fee_pct = CONTRACT_TAKER_FEE_PCT if is_taker else CONTRACT_MAKER_FEE_PCT
        fee = abs(size * fill_price) * fee_pct

        position_side = "long" if is_buy else "short"
        liq_price = fill_price * (1 - 1.0 / leverage * 0.9) if is_buy \
                    else fill_price * (1 + 1.0 / leverage * 0.9)
        self._mock_positions[symbol] = Position(
            symbol=symbol, side=position_side, size=size,
            entry_price=fill_price, leverage=leverage,
            unrealized_pnl=0.0, liquidation_price=liq_price,
            sl_price=sl_price, tp_price=tp_price,
            opened_at=datetime.now(timezone.utc),
        )
        self._mock_balance.equity -= fee
        margin = (size * fill_price) / leverage
        self._mock_balance.available -= margin
        self._mock_balance.used += margin

        return OrderResult(
            order_id=str(uuid.uuid4()), decision_trace_id=decision_trace_id,
            symbol=symbol, side=side, order_type=order_type,
            size=size, price=price,
            status="filled", filled_size=size, filled_price=fill_price,
            sl_order_id=str(uuid.uuid4()) if sl_price else None,
            fees=fee, slippage=abs(fill_price - m.mark_price) * size,
        )

    def close_position(
        self, symbol: str, size: Optional[float] = None,
        decision_trace_id: str = "",
    ) -> OrderResult:
        pos = self.get_position(symbol)
        if not pos:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=OrderSide.SELL,
                order_type=OrderType.MARKET, size=0, price=None,
                status="rejected", error="no position",
            )
        close_size = size if size and size < pos.size else pos.size
        close_side = OrderSide.SELL if pos.side == "long" else OrderSide.BUY

        if self.config.mock_mode:
            m = self._mock_market_cache[symbol]
            fill_price = m.mark_price * (0.9995 if pos.side == "long" else 1.0005)
            fee = abs(close_size * fill_price) * CONTRACT_TAKER_FEE_PCT
            pnl = (fill_price - pos.entry_price) * close_size if pos.side == "long" \
                  else (pos.entry_price - fill_price) * close_size
            self._mock_balance.equity += pnl - fee
            margin = (close_size * pos.entry_price) / pos.leverage
            self._mock_balance.available += margin + pnl - fee
            self._mock_balance.used -= margin
            if close_size >= pos.size:
                del self._mock_positions[symbol]
            else:
                pos.size -= close_size
            return OrderResult(
                order_id=str(uuid.uuid4()), decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="filled",
                filled_size=close_size, filled_price=fill_price,
                fees=fee, slippage=abs(fill_price - m.mark_price) * close_size,
            )

        if not self._exchange:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="rejected",
                error="SDK not initialized",
            )

        try:
            side_str = "buy" if close_side == OrderSide.BUY else "sell"
            response = self._exchange.create_order(
                symbol, "market", side_str, close_size,
                params={"reduceOnly": True},
            )
            filled_price = float(response.get("average", 0))
            fee = abs(close_size * filled_price) * CONTRACT_TAKER_FEE_PCT
            return OrderResult(
                order_id=str(response.get("id", "")),
                decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="filled",
                filled_size=close_size, filled_price=filled_price,
                fees=fee, slippage=0.0,
            )
        except Exception as e:
            return OrderResult(
                order_id="", decision_trace_id=decision_trace_id,
                symbol=symbol, side=close_side, order_type=OrderType.MARKET,
                size=close_size, price=None, status="rejected",
                error=f"close_position failed: {e}",
            )

    def cancel_order(self, order_id: str) -> bool:
        if self.config.mock_mode:
            return True
        if not self._exchange:
            return False
        try:
            self._exchange.cancel_order(order_id)
            return True
        except Exception:
            return False

    def subscribe_market(
        self, symbol: str,
        on_tick: Callable[[MarketSnapshot], None],
    ) -> Any:
        if self.config.mock_mode:
            return on_tick
        # CCXT pro が必要 (WebSocket)、 Phase 3後半で実装
        raise ExchangeError("subscribe_market not yet implemented for bitget (CCXT pro required)")

    def health_check(self) -> bool:
        if self.config.mock_mode:
            return self._mock_balance.equity >= 0
        try:
            balance = self.get_balance()
            return balance.equity >= 0
        except Exception:
            return False
